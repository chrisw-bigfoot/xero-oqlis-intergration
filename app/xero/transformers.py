"""
Financial Report Transformation Module

This module provides functions to transform various Xero financial reports 
into standardized long-format DataFrames suitable for database storage.

Supported Report Types:
- Balance Sheet
- Budget Summary
- Budget Variance
- Profit & Loss (PnL)
- Profit & Loss vs. Last Year (PnL LY)

Each transformation function:
1. Extracts metadata (report date, period, etc.)
2. Parses and normalizes the Excel layout
3. Identifies section hierarchies
4. Melts to long format for database compatibility
5. Assigns ordering and sequence numbers
6. Removes rows with missing sections
"""

import pandas as pd
import numpy as np
from datetime import datetime
import re
import os
from decouple import config
from uuid import uuid4


# ==============================================================================
# BALANCE SHEET REPORT
# ==============================================================================

def extract_balance_sheet_date(file_path: str) -> pd.Timestamp | None:
    """
    Extract the report date from Balance Sheet Excel file header.
    
    Looks for "As at" pattern in the first 4 rows of the spreadsheet.
    
    Args:
        file_path: Path to Balance Sheet Excel file
    
    Returns:
        Parsed date as pd.Timestamp, or None if not found
    """
    header_df = pd.read_excel(file_path, nrows=4, header=None)
    
    # Search in the first column (most common location)
    as_at_rows = header_df[0].astype(str).str.contains("As at", case=False, na=False)
    
    if not as_at_rows.any():
        # Fallback: try searching across all columns
        as_at_rows = header_df.astype(str).apply(
            lambda row: row.str.contains("As at", case=False).any(), axis=1
        )
        if not as_at_rows.any():
            return None
    
    matching_text = header_df.loc[as_at_rows, 0].iloc[0]
    
    try:
        date_part = (
            matching_text.lower()
            .split("as at", 1)[1]
            .strip(" ,.;")
        )
        
        # Try common Xero date formats
        for fmt in ["%d %B %Y", "%d %b %Y", "%d-%b-%Y"]:
            try:
                return pd.to_datetime(date_part, format=fmt, errors='raise')
            except ValueError:
                continue
        
        # Last resort: let pandas infer
        return pd.to_datetime(date_part, errors='coerce')
    
    except (IndexError, AttributeError):
        return None


def transform_balance_sheet(
    file_path: str,
    legal_entity: str = None,
    report_id: str = None,
    created_at: str = None
) -> pd.DataFrame:
    """
    Transform Balance Sheet Excel export to long format.
    
    Extracts balance sheet data with asset/liability/equity sections,
    parses the hierarchical structure (Section → Subsection → Account),
    and melts to long format with one row per account per period.
    
    Args:
        file_path: Path to Balance Sheet Excel file
        legal_entity: Optional legal entity name (added to all rows)
        report_id: Optional unique report identifier
        created_at: Optional creation timestamp
    
    Returns:
        DataFrame with columns:
        - section, section_order: Account classification (Assets, Liabilities, etc.)
        - subsection, subsection_order: Sub-category within section
        - account, account_order: Individual account name with sequence number
        - amount: Account balance value
        - period_str, period, year, month: Date information
        - legal_entity, report_date_at: Metadata
        - created_at, report_id: Optional metadata
    """
    report_date = extract_balance_sheet_date(file_path)

    # Read the Excel file, skipping 4 header rows
    df = pd.read_excel(file_path, skiprows=4, header=0)

    # Normalize first column → Section
    if 'Unnamed: 0' in df.columns:
        df = df.rename(columns={'Unnamed: 0': 'Section'})

    # ── Identify and mark section total rows ────────────────────────────────────
    # Rows starting with "Total" contain summary info in Section column
    mask = df["Section"].str.strip().str.startswith("Total", na=False)
    
    # Move the total label from Section to Account column
    df.loc[mask, "Account"] = df.loc[mask, "Section"]
    
    # Remove "Total " prefix from Section
    df.loc[mask, "Section"] = (
        df.loc[mask, "Section"]
            .str.strip()
            .str.replace(r"^Total\s+", "", regex=True)
    )

    # Forward-fill Section values (each account belongs to its preceding section)
    df['Section'] = df['Section'].ffill()

    # Get all numeric value columns (period columns after Account)
    value_cols = df.columns[df.columns.get_loc("Account") + 1:]

    # ── Identify subsection headers ────────────────────────────────────────────
    # Subsections are rows with Account value but all numeric columns are NaN
    subsection_start = (
        df["Section"].notna() &
        df["Account"].notna() &
        df[value_cols].isna().all(axis=1)
    )

    # Assign subsection values for all rows in each section
    df["Subsection"] = (
        df["Account"]
            .where(subsection_start)
            .groupby(df["Section"])
            .ffill()
    )

    # Keep only structured columns
    df = df[['Section', 'Subsection', 'Account'] + list(value_cols)]

    # ── Melt to long format ────────────────────────────────────────────────────
    id_cols = ["Section", "Subsection", "Account"]
    value_cols = df.columns[len(id_cols):]

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="period_str",
        value_name="amount",
    )

    # Parse period strings to datetime
    long_df["period"] = pd.to_datetime(
        long_df["period_str"],
        format="%d %b %Y",
        errors="coerce"
    )

    # Extract year and month
    long_df["year"] = long_df["period"].dt.year
    long_df["month"] = long_df["period"].dt.month

    # ── Assign ordering values ─────────────────────────────────────────────────
    # section_order: sequential numbering of unique sections in document order
    temp_section = long_df['Section'].fillna('__NAN__')
    changes = temp_section != temp_section.shift(1)
    long_df['section_order'] = changes.cumsum()

    # subsection_order: sequential numbering per section
    long_df['subsection_order'] = (
        long_df
        .groupby('section_order', group_keys=False)
        .apply(lambda g: 
            (g['Subsection'].fillna('__NAN__') != g['Subsection'].fillna('__NAN__').shift(1))
            .cumsum()
            .fillna(1)
            .astype(int)
        )
    )

    # account_order: global sequence number in final dataframe
    long_df['account_order'] = long_df.index + 1

    # ── Finalize structure ─────────────────────────────────────────────────────
    long_df = long_df[[
        'Section', 'section_order',
        'Subsection', 'subsection_order',
        'Account', 'account_order',
        'amount', 'period_str', 'period', 'year', 'month'
    ]]

    # Convert to snake_case
    long_df.columns = [x.lower().replace(" ", "_") for x in long_df.columns]

    # Add metadata
    if legal_entity:
        long_df['legal_entity'] = legal_entity

    long_df['report_date_at'] = report_date

    if created_at:
        long_df['created_at'] = created_at

    if report_id:
        long_df['report_id'] = report_id

    # Remove rows with missing section
    long_df = long_df.dropna(subset=['section'])
    
    # Convert categorical columns to object dtype to allow fillna with empty strings
    categorical_cols = long_df.select_dtypes(include=['category']).columns
    for col in categorical_cols:
        long_df[col] = long_df[col].astype(str)
    
    # Ensure numeric columns are float type and properly formatted for database
    if 'amount' in long_df.columns:
        long_df['amount'] = pd.to_numeric(long_df['amount'], errors='coerce')
        # Rename amount to value for database schema compatibility
        long_df = long_df.rename(columns={'amount': 'value'})
    
    # Replace NaN values with empty strings or 0 for database compatibility
    long_df = long_df.fillna({'value': 0} if 'value' in long_df.columns else {})
    long_df = long_df.fillna('')

    return long_df


# ==============================================================================
# BUDGET SUMMARY REPORT
# ==============================================================================

def extract_budget_summary_date(file_path: str) -> str | None:
    """
    Extract the report period from Budget Summary Excel file header.
    
    Looks for "For the period" pattern in the header rows.
    
    Args:
        file_path: Path to Budget Summary Excel file
    
    Returns:
        Period string (e.g., "1 January 2025 - 31 January 2025"), or None if not found
    """
    try:
        header_df = pd.read_excel(file_path, nrows=5, header=None)
        period = header_df[0].loc[2].split("For the period ")[1].strip()
        return period
    except (IndexError, AttributeError, KeyError):
        return None


def transform_budget_summary(
    file_path: str,
    legal_entity: str = None,
    report_id: str = None,
    created_at: str = None
) -> pd.DataFrame:
    """
    Transform Budget Summary Excel export to long format.
    
    Parses budgeted amounts across monthly periods, identifies sections
    (expense/income categories), and melts to long format suitable for
    database storage.
    
    Args:
        file_path: Path to Budget Summary Excel file
        legal_entity: Optional legal entity name
        report_id: Optional unique report identifier
        created_at: Optional creation timestamp
    
    Returns:
        DataFrame with columns:
        - section, section_order: Budget category
        - account, account_order: Account name with sequence number
        - budget_amount: Budgeted amount value
        - period, period_date, year, month: Period information
        - report_period: Original period string
        - legal_entity: Optional entity identifier
        - created_at, report_id: Optional metadata
    """
    report_period = extract_budget_summary_date(file_path)

    # Read data, skipping metadata rows
    df = pd.read_excel(file_path, skiprows=5, header=0)
    df.columns = df.columns.str.strip()

    df['section'] = pd.NA

    # Remove Total column if present
    if "Total" in df.columns:
        df = df.drop(columns=["Total"])

    # Identify value columns (monthly periods)
    exclude = ['Account', 'section']
    value_cols = [col for col in df.columns if col not in exclude]

    # ── Parse section structure ────────────────────────────────────────────────
    # Walk through rows to identify section headers, subsections, and accounts
    current_section = None
    i = 0
    while i < len(df):
        account_val = df.at[i, 'Account']

        # Handle empty Account cells (usually subtotals or spacing)
        if pd.isna(account_val):
            if current_section is not None:
                df.at[i, 'section'] = current_section
            i += 1
            continue

        account_str = str(account_val).strip()

        # Handle special summary rows
        if account_str in {"Gross Profit", "Net Profit"}:
            df.at[i, 'section'] = account_str
            i += 1
            continue

        # Detect section headers (all value cells are NaN)
        is_section_header = all(pd.isna(df.at[i, col]) for col in value_cols)
        if is_section_header:
            current_section = account_str
            df.at[i, 'section'] = current_section
            i += 1
            continue

        # Detect section totals (row starts with "Total ")
        if (current_section and
            account_str.startswith("Total ") and
            account_str[6:].strip() == current_section):
            df.at[i, 'section'] = current_section
            current_section = None
            i += 1
            continue

        # Regular account row
        if current_section is not None:
            df.at[i, 'section'] = current_section

        i += 1

    # ── Type conversion ────────────────────────────────────────────────────────
    for col in ['section', 'Account']:
        if col in df.columns:
            df[col] = df[col].astype('category')

    df[value_cols] = df[value_cols].apply(pd.to_numeric, errors='coerce')

    # Keep only relevant columns
    df = df[['section', 'Account'] + value_cols]

    # ── Melt to long format ────────────────────────────────────────────────────
    id_vars = ['section', 'Account']
    if legal_entity:
        df['legal_entity'] = legal_entity
        id_vars.append('legal_entity')

    if not value_cols:
        return df

    df_long = pd.melt(
        df,
        id_vars=id_vars,
        value_vars=value_cols,
        var_name='period',
        value_name='budget_amount',
        ignore_index=True
    )

    # Clean period and amount columns
    df_long['period'] = df_long['period'].astype(str).str.strip()
    df_long['budget_amount'] = df_long['budget_amount'].round(2).fillna(0)

    # ── Parse period into date components ──────────────────────────────────────
    def parse_period(p):
        """Parse period string to datetime object."""
        p = str(p).strip()
        if p.lower() == 'total':
            return pd.NaT
        try:
            return pd.to_datetime(p, format='%b %Y', errors='coerce')
        except ValueError:
            return pd.NaT

    df_long['period_date'] = df_long['period'].apply(parse_period)
    df_long['year'] = df_long['period_date'].dt.year.astype('Int16')
    df_long['month'] = df_long['period_date'].dt.month.astype('Int8')

    # ── Assign ordering ────────────────────────────────────────────────────────
    section_order_map = {}
    section_counter = 1
    for sec in df_long['section'].unique():
        if pd.notna(sec) and sec not in section_order_map:
            section_order_map[sec] = section_counter
            section_counter += 1

    df_long['section_order'] = df_long['section'].map(section_order_map).astype('Int16')

    # Sort by period and section order, then assign account_order
    df_long = df_long.sort_values(['period', 'section_order']).reset_index(drop=True)
    df_long['account_order'] = df_long.groupby(['period', 'section_order']).cumcount() + 1

    # Add metadata
    df_long['report_period'] = report_period
    df_long['legal_entity'] = legal_entity

    # Normalize column names
    df_long.columns = [col.lower().replace(' ', '_') for col in df_long.columns]

    # Reorder to final structure
    final_cols = [
        'section_order', 'section', 'account', 'account_order',
        'budget_amount', 'period', 'period_date', 'year', 'month',
        'report_period', 'legal_entity',
    ]

    if created_at:
        df_long['created_at'] = created_at
        final_cols.append('created_at')

    if report_id:
        df_long['report_id'] = report_id
        final_cols.append('report_id')

    df_long = df_long[final_cols]

    # Remove rows with missing section
    df_long = df_long.dropna(subset=['section'])
    
    # Convert categorical columns to object dtype to allow fillna with empty strings
    categorical_cols = df_long.select_dtypes(include=['category']).columns
    for col in categorical_cols:
        df_long[col] = df_long[col].astype(str)
    
    # Ensure numeric columns are float type and rename to value for database compatibility
    if 'budget_amount' in df_long.columns:
        df_long['budget_amount'] = pd.to_numeric(df_long['budget_amount'], errors='coerce')
        df_long = df_long.rename(columns={'budget_amount': 'value'})
    
    # Replace NaN values with empty strings or 0 for database compatibility
    df_long = df_long.fillna({'value': 0} if 'value' in df_long.columns else {})
    df_long = df_long.fillna('')

    return df_long


# ==============================================================================
# BUDGET VARIANCE REPORT
# ==============================================================================

def extract_budget_variance_date(file_path: str) -> str | None:
    """
    Extract the reporting month from Budget Variance Excel file header.
    
    Looks for "For the month ended" pattern.
    
    Args:
        file_path: Path to Budget Variance Excel file
    
    Returns:
        Date string, or None if not found
    """
    try:
        header_df = pd.read_excel(file_path, nrows=4, header=None)
        period = header_df[0].loc[2].split("For the month ended ")[1]
        return period
    except (IndexError, AttributeError, KeyError):
        return None


def transform_budget_variance(
    file_path: str,
    legal_entity: str = None,
    report_id: str = None,
    created_at: str = None
) -> pd.DataFrame:
    """
    Transform Budget Variance Excel export to long format.
    
    Compares actual results against budget, showing variances across
    accounts and periods. Parses hierarchical section structure and
    melts to long format.
    
    Args:
        file_path: Path to Budget Variance Excel file
        legal_entity: Optional legal entity name
        report_id: Optional unique report identifier
        created_at: Optional creation timestamp
    
    Returns:
        DataFrame with columns:
        - section, section_order: Category (Revenue, Expenses, etc.)
        - account, account_order: Account name
        - budget_amount: Variance amount value
        - report_period_str, report_period: Period information
        - legal_entity: Optional entity identifier
        - created_at, report_id: Optional metadata
    """
    report_date = extract_budget_variance_date(file_path)

    # Read data
    df = pd.read_excel(file_path, skiprows=4, header=0)
    df.columns = df.columns.str.strip()

    df['section'] = pd.NA

    if "Total" in df.columns:
        df = df.drop(columns=["Total"])

    # Identify value columns
    exclude = ['Account', 'section']
    if 'Total' in df.columns:
        exclude.append('Total')

    date_like_cols = [col for col in df.columns if col not in exclude]
    value_cols = date_like_cols + (['Total'] if 'Total' in df.columns else [])

    # ── Parse section structure ────────────────────────────────────────────────
    current_section = None
    i = 0
    while i < len(df):
        account_val = df.at[i, 'Account']
        
        if pd.isna(account_val):
            if current_section is not None:
                df.at[i, 'section'] = current_section
            i += 1
            continue

        account_str = str(account_val).strip()

        # Special summary rows
        if account_str in {"Gross Profit", "Net Profit"}:
            df.at[i, 'section'] = account_str
            i += 1
            continue

        # Section header detection
        is_section_header = all(pd.isna(df.at[i, col]) for col in value_cols)
        if is_section_header:
            current_section = account_str
            df.at[i, 'section'] = current_section
            i += 1
            continue

        # Section total detection
        if (current_section and 
            account_str.startswith("Total ") and 
            account_str[6:].strip() == current_section):
            df.at[i, 'section'] = current_section
            current_section = None
            i += 1
            continue

        # Regular account row
        if current_section is not None:
            df.at[i, 'section'] = current_section

        i += 1

    # ── Type conversion ────────────────────────────────────────────────────────
    categorical_cols = ['section', 'Account']
    for col in categorical_cols:
        if col in df.columns:
            df[col] = df[col].astype('category')

    df[value_cols] = df[value_cols].apply(pd.to_numeric, errors='coerce')
    df = df[categorical_cols + value_cols]

    # ── Melt to long format ────────────────────────────────────────────────────
    id_vars = ['section', 'Account']

    if value_cols:
        df_long = pd.melt(
            df,
            id_vars=id_vars,
            value_vars=value_cols,
            var_name='period',
            value_name='budget_amount',
            ignore_index=True
        )

        # Clean columns
        df_long['period'] = df_long['period'].astype(str).str.strip()
        df_long['budget_amount'] = df_long['budget_amount'].round(2)

        # ── Assign ordering ────────────────────────────────────────────────────
        unique_sections = df_long['section'].drop_duplicates(keep='first').tolist()
        section_map = {sec: i + 1 for i, sec in enumerate(unique_sections)}
        df_long['section_order'] = df_long['section'].map(section_map)
        df_long['account_order'] = range(1, len(df_long) + 1)

        # Add metadata
        df_long['report_period_str'] = report_date
        df_long['report_period'] = pd.to_datetime(df_long['report_period_str'], errors='coerce')
        df_long['legal_entity'] = legal_entity

        # Final structure
        df_long = df_long[[
            'section', 'section_order', 'Account', 'account_order',
            'budget_amount', 'report_period_str', 'report_period', 'legal_entity'
        ]]

        df_long.columns = [x.lower().replace(" ", "_") for x in df_long.columns]

        if created_at:
            df_long['created_at'] = created_at

        if report_id:
            df_long['report_id'] = report_id

    else:
        df_long = df.copy()

    # Remove rows with missing section
    df_long = df_long.dropna(subset=['section'])
    
    # Convert categorical columns to object dtype to allow fillna with empty strings
    categorical_cols = df_long.select_dtypes(include=['category']).columns
    for col in categorical_cols:
        df_long[col] = df_long[col].astype(str)
    
    # Ensure numeric columns are float type and rename to value for database compatibility
    if 'budget_amount' in df_long.columns:
        df_long['budget_amount'] = pd.to_numeric(df_long['budget_amount'], errors='coerce')
        df_long = df_long.rename(columns={'budget_amount': 'value'})
    
    # Replace NaN values with empty strings or 0 for database compatibility
    df_long = df_long.fillna({'value': 0} if 'value' in df_long.columns else {})
    df_long = df_long.fillna('')

    return df_long


# ==============================================================================
# PROFIT & LOSS (CURRENT PERIOD) REPORT
# ==============================================================================

def extract_profit_loss_date(file_path: str) -> str | None:
    """
    Extract the reporting month from Profit & Loss Excel file header.
    
    Looks for "For the month ended" pattern.
    
    Args:
        file_path: Path to Profit & Loss Excel file
    
    Returns:
        Date string, or None if not found
    """
    try:
        header_df = pd.read_excel(file_path, nrows=4, header=None)
        period = header_df[0].loc[2].split("For the month ended ")[1]
        return period
    except (IndexError, AttributeError, KeyError):
        return None


def transform_profit_loss(
    file_path: str,
    legal_entity: str = None,
    report_id: str = None,
    created_at: str = None
) -> pd.DataFrame:
    """
    Transform Profit & Loss Excel export to long format.
    
    Parses revenue and expense accounts with hierarchical sections,
    melts to long format, and assigns ordering values.
    
    Args:
        file_path: Path to Profit & Loss Excel file
        legal_entity: Optional legal entity name
        report_id: Optional unique report identifier
        created_at: Optional creation timestamp
    
    Returns:
        DataFrame with columns:
        - section, section_order: Revenue/Expense category
        - subsection, subsection_order: Sub-category within section
        - account, account_order: Account name with sequence number
        - amount: Account value
        - period_str, period, year, month: Period information
        - legal_entity: Optional entity identifier
        - report_date_at: Report as-at date
        - created_at, report_id: Optional metadata
    """
    report_date = extract_profit_loss_date(file_path)

    df = pd.read_excel(file_path, skiprows=4, header=0)

    # Normalize first column name
    if 'Unnamed: 0' in df.columns:
        df = df.rename(columns={'Unnamed: 0': 'Section'})

    # ── Identify and mark section totals ────────────────────────────────────────
    mask = df["Section"].str.strip().str.startswith("Total", na=False)
    df.loc[mask, "Account"] = df.loc[mask, "Section"]
    df.loc[mask, "Section"] = (
        df.loc[mask, "Section"]
            .str.strip()
            .str.replace(r"^Total\s+", "", regex=True)
    )

    df['Section'] = df['Section'].ffill()

    # Get value columns
    value_cols = df.columns[df.columns.get_loc("Account") + 1:]

    # ── Identify subsection headers ────────────────────────────────────────────
    subsection_start = (
        df["Section"].notna() &
        df["Account"].notna() &
        df[value_cols].isna().all(axis=1)
    )

    df["Subsection"] = (
        df["Account"]
            .where(subsection_start)
            .groupby(df["Section"])
            .ffill()
    )

    df = df[['Section', 'Subsection', 'Account'] + list(value_cols)]

    # ── Melt to long format ────────────────────────────────────────────────────
    id_cols = ["Section", "Subsection", "Account"]
    value_cols = df.columns[len(id_cols):]

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="period_str",
        value_name="amount",
    )

    # Parse period
    long_df["period"] = pd.to_datetime(
        long_df["period_str"],
        format="%b %Y",
        errors="coerce"
    )

    long_df["year"] = long_df["period"].dt.year
    long_df["month"] = long_df["period"].dt.month

    # ── Assign ordering values ─────────────────────────────────────────────────
    temp_section = long_df['Section'].fillna('__NAN__')
    changes = temp_section != temp_section.shift(1)
    long_df['section_order'] = changes.cumsum()

    long_df['subsection_order'] = (
        long_df
        .groupby('section_order', group_keys=False)
        .apply(lambda g: 
            (g['Subsection'].fillna('__NAN__') != g['Subsection'].fillna('__NAN__').shift(1))
            .cumsum()
            .fillna(1)
            .astype(int)
        )
    )

    long_df['account_order'] = long_df.index + 1

    # ── Finalize structure ─────────────────────────────────────────────────────
    long_df = long_df[[
        'Section', 'section_order',
        'Subsection', 'subsection_order',
        'Account', 'account_order',
        'amount', 'period_str', 'period', 'year', 'month'
    ]]

    long_df.columns = [x.lower().replace(" ", "_") for x in long_df.columns]

    # Add metadata
    if legal_entity:
        long_df['legal_entity'] = legal_entity

    long_df['report_date_at'] = report_date

    if created_at:
        long_df['created_at'] = created_at

    if report_id:
        long_df['report_id'] = report_id

    # Remove rows with missing section
    long_df = long_df.dropna(subset=['section'])
    
    # Convert categorical columns to object dtype to allow fillna with empty strings
    categorical_cols = long_df.select_dtypes(include=['category']).columns
    for col in categorical_cols:
        long_df[col] = long_df[col].astype(str)
    
    # Ensure numeric columns are float type and properly formatted for database
    if 'amount' in long_df.columns:
        long_df['amount'] = pd.to_numeric(long_df['amount'], errors='coerce')
        # Rename amount to value for database schema compatibility
        long_df = long_df.rename(columns={'amount': 'value'})
    
    # Replace NaN values with empty strings or 0 for database compatibility
    long_df = long_df.fillna({'value': 0} if 'value' in long_df.columns else {})
    long_df = long_df.fillna('')

    return long_df


# ==============================================================================
# PROFIT & LOSS VS. LAST YEAR REPORT
# ==============================================================================

def extract_profit_loss_ly_date(file_path: str) -> str | None:
    """
    Extract the reporting month from Profit & Loss vs LY Excel file header.
    
    Looks for "For the month ended" pattern.
    
    Args:
        file_path: Path to Profit & Loss vs LY Excel file
    
    Returns:
        Date string, or None if not found
    """
    try:
        header_df = pd.read_excel(file_path, nrows=4, header=None)
        period = header_df[0].loc[2].split("For the month ended ")[1]
        return period
    except (IndexError, AttributeError, KeyError):
        return None


def transform_profit_loss_ly(
    file_path: str,
    legal_entity: str = None,
    report_id: str = None,
    created_at: str = None
) -> pd.DataFrame:
    """
    Transform Profit & Loss vs Last Year Excel export to long format.
    
    Compares current period P&L against same period last year,
    with hierarchical section structure. Melts to long format.
    
    Args:
        file_path: Path to Profit & Loss vs LY Excel file
        legal_entity: Optional legal entity name
        report_id: Optional unique report identifier
        created_at: Optional creation timestamp
    
    Returns:
        DataFrame with columns:
        - section, section_order: Revenue/Expense category
        - subsection, subsection_order: Sub-category within section
        - account, account_order: Account name
        - amount: Account value
        - period_str, period, year, month: Period information
        - legal_entity, report_date_at: Metadata
        - created_at, report_id: Optional metadata
    """
    report_date = extract_profit_loss_ly_date(file_path)

    df = pd.read_excel(file_path, skiprows=4, header=0)

    # Normalize first column name
    if 'Unnamed: 0' in df.columns:
        df = df.rename(columns={'Unnamed: 0': 'Section'})

    # ── Identify and mark section totals ────────────────────────────────────────
    mask = df["Section"].str.strip().str.startswith("Total", na=False)
    df.loc[mask, "Account"] = df.loc[mask, "Section"]
    df.loc[mask, "Section"] = (
        df.loc[mask, "Section"]
            .str.strip()
            .str.replace(r"^Total\s+", "", regex=True)
    )

    df['Section'] = df['Section'].ffill()

    # Get value columns
    value_cols = df.columns[df.columns.get_loc("Account") + 1:]

    # ── Identify subsection headers ────────────────────────────────────────────
    subsection_start = (
        df["Section"].notna() &
        df["Account"].notna() &
        df[value_cols].isna().all(axis=1)
    )

    df["Subsection"] = (
        df["Account"]
            .where(subsection_start)
            .groupby(df["Section"])
            .ffill()
    )

    df = df[['Section', 'Subsection', 'Account'] + list(value_cols)]

    # ── Melt to long format ────────────────────────────────────────────────────
    id_cols = ["Section", "Subsection", "Account"]
    value_cols = df.columns[len(id_cols):]

    long_df = df.melt(
        id_vars=id_cols,
        value_vars=value_cols,
        var_name="period_str",
        value_name="amount",
    )

    # Parse period
    long_df["period"] = pd.to_datetime(
        long_df["period_str"],
        format="%b %Y",
        errors="coerce"
    )

    long_df["year"] = long_df["period"].dt.year
    long_df["month"] = long_df["period"].dt.month

    # ── Assign ordering values ─────────────────────────────────────────────────
    temp_section = long_df['Section'].fillna('__NAN__')
    changes = temp_section != temp_section.shift(1)
    long_df['section_order'] = changes.cumsum()

    long_df['subsection_order'] = (
        long_df
        .groupby('section_order', group_keys=False)
        .apply(lambda g: 
            (g['Subsection'].fillna('__NAN__') != g['Subsection'].fillna('__NAN__').shift(1))
            .cumsum()
            .fillna(1)
            .astype(int)
        )
    )

    long_df['account_order'] = long_df.index + 1

    # ── Finalize structure ─────────────────────────────────────────────────────
    long_df = long_df[[
        'Section', 'section_order',
        'Subsection', 'subsection_order',
        'Account', 'account_order',
        'amount', 'period_str', 'period', 'year', 'month'
    ]]

    long_df.columns = [x.lower().replace(" ", "_") for x in long_df.columns]

    # Add metadata
    if legal_entity:
        long_df['legal_entity'] = legal_entity

    long_df['report_date_at'] = report_date

    if created_at:
        long_df['created_at'] = created_at

    if report_id:
        long_df['report_id'] = report_id

    # Remove rows with missing section
    long_df = long_df.dropna(subset=['section'])
    
    # Convert categorical columns to object dtype to allow fillna with empty strings
    categorical_cols = long_df.select_dtypes(include=['category']).columns
    for col in categorical_cols:
        long_df[col] = long_df[col].astype(str)
    
    # Ensure numeric columns are float type and properly formatted for database
    if 'amount' in long_df.columns:
        long_df['amount'] = pd.to_numeric(long_df['amount'], errors='coerce')
        # Rename amount to value for database schema compatibility
        long_df = long_df.rename(columns={'amount': 'value'})
    
    # Replace NaN values with empty strings or 0 for database compatibility
    long_df = long_df.fillna({'value': 0} if 'value' in long_df.columns else {})
    long_df = long_df.fillna('')

    return long_df
