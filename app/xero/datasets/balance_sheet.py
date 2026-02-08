import pandas as pd
import numpy as np
from datetime import datetime


def parse_period_to_date(period_str: str) -> pd.Timestamp | None:
    """
    Convert month-year strings like 'Mar 2025', 'Apr 2025' → datetime (first of month)
    Returns None if parsing fails.
    """
    if not isinstance(period_str, str):
        return None
    period_str = period_str.strip()
    try:
        dt = datetime.strptime(period_str, "%b %Y")
        return pd.Timestamp(year=dt.year, month=dt.month, day=1)
    except ValueError:
        try:
            dt = datetime.strptime(period_str, "%B %Y")
            return pd.Timestamp(year=dt.year, month=dt.month, day=1)
        except ValueError:
            return None


def transform_balance_sheet(
    file_path: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads and processes the Balance Sheet sheet (e.g. 'PJM Balance Sheet') from management-reports.xlsx.

    Parameters:
        file_path: Path to the Excel file
        drop_profit_rows: If True, drop rows containing 'Gross Profit' or 'Net Profit'
        melt_to_long: If True, melt columns (e.g. Current, Prior, Variance) into long format
                      If False, keep wide format

    Returns:
        Transformed pandas DataFrame
    """
    xls = pd.ExcelFile(file_path)

    # Find sheet containing "balance sheet" (case-insensitive)
    bs_sheet_name = None
    for sheet in xls.sheet_names:
        lower = sheet.lower()
        if 'balance sheet' in lower:
            bs_sheet_name = sheet
            break

    if bs_sheet_name is None:
        raise ValueError("No sheet found containing 'Balance Sheet' in its name")

    print(f"Reading sheet: {bs_sheet_name}")

    df = pd.read_excel(
        xls,
        sheet_name=bs_sheet_name,
        skiprows=4,
        header=0
    )

    df = df.dropna(how="all").reset_index(drop=True)

    # Drop YTD (if present)
    ytd_cols = [col for col in df.columns if isinstance(col, str) and 'year to date' in col.lower()]
    if ytd_cols:
        print(f"Dropping YTD column(s): {ytd_cols}")
        df = df.drop(columns=ytd_cols)

    # Rename → Section
    if 'Unnamed: 0' in df.columns:
        df = df.rename(columns={'Unnamed: 0': 'Section'})

    # Clean & filter Section
    if 'Section' in df.columns:
        df['Section'] = df['Section'].astype(str).str.strip().replace(['', 'nan', 'NaN', 'None'], np.nan)
        total_section_mask = df['Section'].str.lower().str.startswith('total', na=False)
        if total_section_mask.any():
            df = df[~total_section_mask].reset_index(drop=True)
        df['Section'] = df['Section'].ffill()

    # Remove pure section headers
    if 'Section' in df.columns:
        other_cols = [c for c in df.columns if c not in ['Section', 'Account']]
        is_pure_header = (
            df['Section'].notna() &
            df['Section'].ne('') &
            df[other_cols].isna().all(axis=1) &
            (df['Account'].isna() | (df['Account'].astype(str).str.strip() == ''))
        )
        if is_pure_header.any():
            df = df[~is_pure_header].reset_index(drop=True)

    # Create Subsection
    df['Subsection'] = np.nan
    if 'Section' in df.columns and 'Account' in df.columns:
        other_cols = [c for c in df.columns if c not in ['Section', 'Account', 'Subsection']]
        is_subsection_header = (
            df['Section'].notna() &
            df['Account'].notna() &
            df['Account'].ne('') &
            df[other_cols].isna().all(axis=1)
        )
        df.loc[is_subsection_header, 'Subsection'] = df.loc[is_subsection_header, 'Account']
        df['Subsection'] = df.groupby('Section', group_keys=False)['Subsection'].apply(lambda x: x.ffill())
        no_subsection_mask = df['Subsection'].isna()
        df.loc[no_subsection_mask, 'Subsection'] = df.loc[no_subsection_mask, 'Section']

    # Handle Gross/Net Profit rows (if any exist in balance sheet)
    if 'Account' in df.columns:
        profit_mask = (
            df['Account'].notna() &
            df['Account'].astype(str).str.contains('gross\s*profit|net\s*profit', case=False, na=False, regex=True)
        )
        if drop_profit_rows:
            if profit_mask.any():
                df = df[~profit_mask].reset_index(drop=True)
        else:
            if profit_mask.any():
                df.loc[profit_mask, 'Section'] = df.loc[profit_mask, 'Account']
                df.loc[profit_mask, 'Subsection'] = df.loc[profit_mask, 'Account']

    # Remove label/subtotal rows (Section + Subsection + Account filled, no numbers)
    if all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
        non_meta_cols = [c for c in df.columns if c not in ['Section', 'Subsection', 'Account']]
        if non_meta_cols:
            is_label_only = (
                df['Section'].notna() &
                df['Subsection'].notna() &
                df['Account'].notna() &
                df[non_meta_cols].isna().all(axis=1)
            )
            if is_label_only.any():
                df = df[~is_label_only].reset_index(drop=True)

    # Clean Account
    if 'Account' in df.columns:
        df['Account'] = df['Account'].astype(str).str.strip().replace('nan', np.nan)

    # Remove total-starting Account rows
    df = df[~df['Account'].str.lower().str.startswith('total', na=False)].copy().reset_index(drop=True)

    # Final column reordering (wide format)
    if all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
        all_cols = df.columns.tolist()
        other_cols = [c for c in all_cols if c not in ['Section', 'Subsection', 'Account']]
        df = df[['Section', 'Subsection', 'Account'] + other_cols]

    # Melt to long format if requested
    if melt_to_long:
        if not all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
            raise ValueError("Cannot melt: missing required columns (Section, Subsection, Account)")

        id_vars = ['Section', 'Subsection', 'Account']
        value_vars = [c for c in df.columns if c not in id_vars]

        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=value_vars,
            var_name='period_str',
            value_name='amount'
        )

        df_long = df_long.dropna(subset=['amount'])
        df_long['amount'] = pd.to_numeric(df_long['amount'], errors='coerce')
        df_long = df_long.dropna(subset=['amount'])

        df_long['period_date'] = df_long['period_str'].apply(parse_period_to_date)

        df_long = df_long[['Section', 'Subsection', 'Account', 'period_str', 'period_date', 'amount']]

        return df_long.reset_index(drop=True)

    return df.reset_index(drop=True)


# file = 'files/management-report.xlsx'

# # Wide format
# df_wide = transform_balance_sheet(file, drop_profit_rows=False, melt_to_long=False)
# df_wide.to_excel("balance_sheet_wide.xlsx", index=False)

# # Long format
# df_long = transform_balance_sheet(file, drop_profit_rows=False, melt_to_long=True)
# df_long.to_excel("balance_sheet_long.xlsx", index=False)