import pandas as pd
import numpy as np
from datetime import datetime
import re

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
        

def transform_profit_and_loss_vs_py(
    file_path: str,
    legal_entity: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads and processes the 'Profit and Loss - vs PY' sheet from management-reports.xlsx.

    Parameters:
        file_path: Path to the Excel file
        legal_entity: Legal entity identifier/name to include in output
        drop_profit_rows: If True, drop rows containing 'Gross Profit' or 'Net Profit'
        melt_to_long: If True, melt comparison/variance columns into long format
                      If False, keep wide format

    Returns:
        Transformed pandas DataFrame (wide or long)
    """
    xls = pd.ExcelFile(file_path)

    # Find the 'Profit and Loss - vs PY' sheet (case-insensitive)
    sheet_name = None
    for sheet in xls.sheet_names:
        lower = sheet.lower()
        if 'profit and loss - vs py' in lower or 'p&l - vs py' in lower:
            sheet_name = sheet
            break

    if sheet_name is None:
        raise ValueError("No sheet found containing 'Profit and Loss - vs PY' or 'P&L - vs PY'")

    print(f"Reading sheet: {sheet_name}")

    df = pd.read_excel(
        xls,
        sheet_name=sheet_name,
        skiprows=4,
        header=0
    )

    df = df.dropna(how="all").reset_index(drop=True)

    # Drop any 'Year to date' column (if present)
    ytd_cols = [col for col in df.columns if isinstance(col, str) and 'year to date' in col.lower()]
    if ytd_cols:
        print(f"Dropping YTD column(s): {ytd_cols}")
        df = df.drop(columns=ytd_cols)

    # Rename Unnamed: 0 → Section (assuming same structure)
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

    # Handle Gross/Net Profit rows
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

    # ────────────────────────────────────────────────────────────────
    # Final column reordering (wide format)
    # ────────────────────────────────────────────────────────────────
    if all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
        all_cols = df.columns.tolist()
        other_cols = [c for c in all_cols if c not in ['Section', 'Subsection', 'Account']]
        df = df[['Section', 'Subsection', 'Account'] + other_cols]

    # ────────────────────────────────────────────────────────────────
    # Melt to long format if requested
    # ────────────────────────────────────────────────────────────────
    if melt_to_long:
            if not all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
                raise ValueError("Cannot melt: missing required columns (Section, Subsection, Account)")

            id_vars = ['Section', 'Subsection', 'Account']
            value_vars = [c for c in df.columns if c not in id_vars]

            if not value_vars:
                raise ValueError("No value columns found to melt (e.g. Dec 2025, Dec 2024...)")

            df_long = pd.melt(
                df,
                id_vars=id_vars,
                value_vars=value_vars,
                var_name='period_str',
                value_name='amount'
            )

            # Drop rows with no amount
            df_long = df_long[df_long['amount'].notna() & (df_long['amount'] != 0)].reset_index(drop=True)

            # Convert amount to numeric (handle commas, spaces, etc.)
            df_long['amount'] = df_long['amount'].astype(str).str.replace(',', '.').replace('', np.nan)
            df_long['amount'] = pd.to_numeric(df_long['amount'], errors='coerce')
            df_long = df_long.dropna(subset=['amount']).reset_index(drop=True)

            # Parse period_str to date (expects "Dec 2025", "Dec 2024", etc.)
            df_long['period_date'] = df_long['period_str'].apply(parse_period_to_date)

            # Optional: add a clean year column
            df_long['year'] = df_long['period_date'].dt.year

            # Add legal_entity column
            df_long['legal_entity'] = legal_entity

            # Final column order
            df_long = df_long[[
                'legal_entity', 'Section', 'Subsection', 'Account',
                'period_str', 'period_date', 'year',
                'amount'
            ]]

            return df_long.reset_index(drop=True)
    
    # Add legal_entity column to wide format
    df['legal_entity'] = legal_entity
    return df.reset_index(drop=True)


def transform_profit_and_loss(
    file_path: str,
    legal_entity: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads and processes the 'Profit and Loss' sheet from management-reports.xlsx.

    Parameters:
        file_path: Path to the Excel file
        legal_entity: Legal entity identifier/name to include in output
        drop_profit_rows: If True, drop rows containing 'Gross Profit' or 'Net Profit'
        melt_to_long: If True, melt monthly columns into long format (better for DB/BI)
                       If False, keep wide format (current structure)

    Returns:
        Transformed pandas DataFrame
    """
    xls = pd.ExcelFile(file_path)

    # Find sheet
    pl_sheet_name = None
    for sheet in xls.sheet_names:
        lower = sheet.lower()
        if 'profit and loss' in lower or 'p&l' in lower:
            pl_sheet_name = sheet
            break

    if pl_sheet_name is None:
        raise ValueError("No sheet found containing 'Profit and Loss' or 'P&L'")

    print(f"Reading sheet: {pl_sheet_name}")

    df = pd.read_excel(
        xls,
        sheet_name=pl_sheet_name,
        skiprows=4,
        header=0
    )

    df = df.dropna(how="all").reset_index(drop=True)

    # Drop YTD
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

    # Handle Gross/Net Profit rows
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

    # ────────────────────────────────────────────────────────────────
    # Final column reordering (wide format)
    # ────────────────────────────────────────────────────────────────
    if all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
        all_cols = df.columns.tolist()
        other_cols = [c for c in all_cols if c not in ['Section', 'Subsection', 'Account']]
        df = df[['Section', 'Subsection', 'Account'] + other_cols]

    # ────────────────────────────────────────────────────────────────
    # Melt to long format if requested
    # ────────────────────────────────────────────────────────────────
    if melt_to_long:
        if not all(col in df.columns for col in ['Section', 'Subsection', 'Account']):
            raise ValueError("Cannot melt: missing required columns (Section, Subsection, Account)")

        # Identify month columns (exclude metadata columns)
        id_vars = ['Section', 'Subsection', 'Account']
        value_vars = [c for c in df.columns if c not in id_vars]

        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=value_vars,
            var_name='period_str',
            value_name='amount'
        )

        # Drop rows with no amount
        df_long = df_long.dropna(subset=['amount'])

        # Convert amount to numeric (handle commas, negatives, etc.)
        df_long['amount'] = pd.to_numeric(df_long['amount'], errors='coerce')
        df_long = df_long.dropna(subset=['amount'])

        # Parse period to date (first of month)
        df_long['period_date'] = df_long['period_str'].apply(parse_period_to_date)

        # Optional: drop original string period if you only want date
        # df_long = df_long.drop(columns=['period_str'])

        # Add legal_entity column
        df_long['legal_entity'] = legal_entity

        # Final column order for long format
        df_long = df_long[['legal_entity', 'Section', 'Subsection', 'Account', 'period_str', 'period_date', 'amount']]

        return df_long.reset_index(drop=True)

    # Add legal_entity column to wide format
    df['legal_entity'] = legal_entity
    return df.reset_index(drop=True)


def transform_balance_sheet(
    file_path: str,
    legal_entity: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads and processes the Balance Sheet sheet (e.g. 'PJM Balance Sheet') from management-reports.xlsx.

    Parameters:
        file_path: Path to the Excel file
        legal_entity: Legal entity identifier/name to include in output
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

        # Add legal_entity column
        df_long['legal_entity'] = legal_entity

        df_long = df_long[['legal_entity', 'Section', 'Subsection', 'Account', 'period_str', 'period_date', 'amount']]

        return df_long.reset_index(drop=True)

    # Add legal_entity column to wide format
    df['legal_entity'] = legal_entity
    return df.reset_index(drop=True)


def transform_budget_variance_report(
    file_path: str,
    legal_entity: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Loads the Budget Variance sheet, extracts report period, performs cleaning + section grouping.
    
    Parameters:
        file_path: Path to the Excel file
        legal_entity: Legal entity identifier/name to include in output
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

        # Add legal_entity column
        df_long['legal_entity'] = legal_entity

        # Final order for database-friendly structure
        df_long = df_long[['legal_entity', 'Period', 'Section', 'Account', 'metric', 'value']]

        return df_long.reset_index(drop=True)

    # Add legal_entity column to wide format
    df['legal_entity'] = legal_entity
    return df.reset_index(drop=True)


def process_management_report(file_path: str, legal_entity: str) -> dict[str, pd.DataFrame]:
    """
    Process the management report Excel file and return a dictionary of DataFrames for each section.
    
    Parameters:
        file_path: Path to the management report Excel file
        legal_entity: Legal entity identifier/name to include in all output DataFrames
    
    Returns:
        Dictionary with keys:
            - 'profit_loss_vs_py': P&L vs Prior Year comparison
            - 'profit_loss': Profit and Loss statement
            - 'balance_sheet': Balance Sheet
            - 'budget_variance': Budget Variance Report
        Each DataFrame includes the legal_entity column.
    """
    try:
        # Process Profit and Loss vs Prior Year
        profit_loss_vs_py_df = transform_profit_and_loss_vs_py(
            file_path=file_path,
            legal_entity=legal_entity,
            drop_profit_rows=True,
            melt_to_long=False
        )
    except Exception as e:
        print(f"Warning: Could not process Profit and Loss vs Prior Year: {str(e)}")
        profit_loss_vs_py_df = None
    
    try:
        # Process Profit and Loss
        profit_loss_df = transform_profit_and_loss(
            file_path=file_path,
            legal_entity=legal_entity,
            drop_profit_rows=True,
            melt_to_long=False
        )
    except Exception as e:
        print(f"Warning: Could not process Profit and Loss: {str(e)}")
        profit_loss_df = None
    
    try:
        # Process Balance Sheet
        balance_sheet_df = transform_balance_sheet(
            file_path=file_path,
            legal_entity=legal_entity,
            drop_profit_rows=False,
            melt_to_long=False
        )
    except Exception as e:
        print(f"Warning: Could not process Balance Sheet: {str(e)}")
        balance_sheet_df = None
    
    try:
        # Process Budget Variance Report
        budget_variance_df = transform_budget_variance_report(
            file_path=file_path,
            legal_entity=legal_entity,
            drop_profit_rows=False,
            melt_to_long=False
        )
    except Exception as e:
        print(f"Warning: Could not process Budget Variance Report: {str(e)}")
        budget_variance_df = None
    
    # Return dictionary of DataFrames
    return {
        'profit_loss_vs_py': profit_loss_vs_py_df,
        'profit_loss': profit_loss_df,
        'balance_sheet': balance_sheet_df,
        'budget_variance': budget_variance_df,
    }

