import pandas as pd
import numpy as np
import re
from datetime import datetime


def parse_report_period(text: str) -> pd.Timestamp | None:
    """
    Extract month-end date from strings containing:
    "For the month ended 31 December 2025" or similar.
    """
    if not isinstance(text, str):
        return None
    
    text_lower = text.lower()
    if 'for the month ended' not in text_lower and 'for the period ended' not in text_lower:
        return None
    
    match = re.search(r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})', text)
    if not match:
        return None
    
    date_str = match.group(1).strip()
    
    try:
        dt = datetime.strptime(date_str, "%d %B %Y")
        return pd.Timestamp(dt)
    except ValueError:
        try:
            dt = datetime.strptime(date_str, "%d %b %Y")
            return pd.Timestamp(dt)
        except ValueError:
            return None


def transform_budget_variance_report(
    file_path: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads the Budget Variance sheet, extracts report period, performs cleaning + section grouping.
    
    Parameters:
        file_path: Path to the Excel file
        drop_profit_rows: If True, removes Gross Profit / Net Profit rows
        melt_to_long: If True, melts variance columns into long format (ideal for DB)
                      If False, returns wide format (current structure)
    
    Returns:
        Transformed DataFrame (wide or long depending on melt_to_long)
    """
    xls = pd.ExcelFile(file_path)

    # Find the sheet name
    budget_sheet_name = next(
        (sheet for sheet in xls.sheet_names if 'budget variance' in sheet.lower()),
        None
    )
    if budget_sheet_name is None:
        raise ValueError("No sheet found containing 'Budget Variance' in its name")

    # ── Step 1: Extract report period ───────────────────────────────────────────
    header_df = pd.read_excel(
        xls,
        sheet_name=budget_sheet_name,
        nrows=10,
        header=None
    )

    report_period = None
    for _, row in header_df.iterrows():
        for cell in row:
            if isinstance(cell, str):
                parsed = parse_report_period(cell)
                if parsed is not None:
                    report_period = parsed
                    break
        if report_period is not None:
            break

    if report_period is None:
        print("Warning: Could not find/parse 'For the month ended ...' in top rows.")
        report_period = pd.NaT

    # ── Step 2: Read the actual data ─────────────────────────────────────────────
    df = pd.read_excel(
        xls,
        sheet_name=budget_sheet_name,
        skiprows=4,
        header=0
    )

    df = df.dropna(how="all").reset_index(drop=True)

    total_cols = [col for col in df.columns if isinstance(col, str) and col.strip().lower() == 'total']
    if total_cols:
        df = df.drop(columns=total_cols)

    possible_account_cols = [
        'account', 'gl account', 'account description', 'description',
        'account name', 'ledger account', 'account code'
    ]
    account_col = next(
        (col for col in df.columns if str(col).strip().lower() in possible_account_cols),
        None
    )
    if account_col is None:
        raise ValueError(f"Could not find account column. Available: {list(df.columns)}")

    df[account_col] = df[account_col].astype(str).str.strip().replace('', np.nan)

    df = df[~df[account_col].str.lower().str.startswith('total', na=False)].reset_index(drop=True)

    other_cols = [c for c in df.columns if c != account_col]
    is_section_header = (
        df[account_col].notna()
        & df[account_col].ne('')
        & df[other_cols].isna().all(axis=1)
    )

    df['Section'] = np.where(is_section_header, df[account_col], np.nan)
    df['Section'] = df['Section'].ffill()

    df = df[~is_section_header].reset_index(drop=True)

    if not drop_profit_rows:
        profit_mask = df[account_col].str.contains(r'gross\s*profit|net\s*profit', case=False, na=False, regex=True)
        df.loc[profit_mask, 'Section'] = df.loc[profit_mask, account_col]

    df['Section'] = df['Section'].astype(str).str.strip().replace('nan', np.nan)

    # Add the extracted period to every row
    df['Period'] = report_period

    # Standardize account column name
    if account_col != 'Account' and 'Account' not in df.columns:
        df = df.rename(columns={account_col: 'Account'})

    # ── Final column selection (wide format base) ────────────────────────────────
    desired_cols = [
        'Period', 'Section', 'Account', 'Actual', 'Budget', 'Variance',
        'Variance %', 'YTD Actual', 'YTD Budget', 'Variance.1', 'Variance %.1'
    ]
    existing = [c for c in desired_cols if c in df.columns]
    df = df[existing].reset_index(drop=True)

    # ── Melt to long format if requested ─────────────────────────────────────────
    if melt_to_long:
        id_vars = ['Period', 'Section', 'Account']
        value_vars = [c for c in df.columns if c not in id_vars]

        if not value_vars:
            raise ValueError("No value columns found to melt (e.g. Actual, Budget, Variance...)")

        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=value_vars,
            var_name='metric',
            value_name='value'
        )

        # Drop rows with missing values
        df_long = df_long.dropna(subset=['value'])

        # Convert value to numeric (handle commas, %, etc. if needed)
        df_long['value'] = pd.to_numeric(df_long['value'], errors='coerce')
        df_long = df_long.dropna(subset=['value'])

        # Optional: clean metric names (remove spaces, make consistent)
        df_long['metric'] = df_long['metric'].str.strip().str.replace(r'\s+', ' ', regex=True)

        # Final order for database-friendly structure
        df_long = df_long[['Period', 'Section', 'Account', 'metric', 'value']]

        return df_long.reset_index(drop=True)

    return df.reset_index(drop=True)



# # Wide format (default)
# df_wide = transform_budget_variance_report('files/management-report.xlsx', drop_profit_rows=False, melt_to_long=False)
# df_wide.to_excel('budget_variance_wide.xlsx', index=False)

# # Long format (ready for PostgreSQL)
# df_long = transform_budget_variance_report('files/management-report.xlsx', drop_profit_rows=False, melt_to_long=True)
# df_long.to_excel('budget_variance_long.xlsx', index=False)
# # df_long.to_sql("budget_variance", engine, if_exists="replace", index=False)