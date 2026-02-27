import pandas as pd
import numpy as np
from datetime import datetime
import re
from pathlib import Path



def transform_budget_summary(file_path: str, legal_entity: str = None, report_id: str = None, created_at: str = None, report_month: str = None, long_format: bool = False) -> pd.DataFrame:
    print(f"Transforming Budget Summary from file: {file_path} ...")

    # Read the Excel file, skipping the first 5 rows which contain metadata
    df = pd.read_excel(file_path, skiprows=5, header=0)

    df.dropna(axis=0, how='all', inplace=True)  # Drop rows that are completely empty

    # Rename first column to 'Account' if it exists as 'Unnamed: 0'
    if 'Unnamed: 0' in df.columns:
        df = df.rename(columns={'Unnamed: 0': 'Account'})
    
    # Get value columns (all columns except Account)
    value_columns = [col for col in df.columns if col != 'Account']

    # Create Section column: rows where Account is NOT NaN and ALL value columns are NaN are section headers
    df['Section'] = np.where(
        df['Account'].notna() & df[value_columns].isna().all(axis=1),
        df['Account'],
        np.nan
    )

    # Make Net Profit and Gross Profit sections if they exist in the Account column
    df.loc[df['Account'] == 'Gross Profit', 'Section'] = 'Gross Profit'
    df.loc[df['Section'] == 'Gross Profit', 'Account'] = ''

    df.loc[df['Account'] == 'Net Profit', 'Section'] = 'Net Profit'
    df.loc[df['Section'] == 'Net Profit', 'Account'] = ''

    # Forward fill Section to propagate section names to all rows
    df['Section'] = df['Section'].ffill()

    # Drop rows where Account is NaN (empty rows)
    df = df.dropna(subset=['Account'])

    # Drop rows where Section has a value and all value columns are NaN (section header rows themselves)
    df = df[~(df['Section'].notna() & df[value_columns].isna().all(axis=1))]
    
    # Reset index
    df = df.reset_index(drop=True)

    # Add Section Order column - assign incrementing order to each unique section
    df['Section Order'] = pd.factorize(df['Section'])[0] + 1

    # Create Subsection column - where Account has a value and all value columns are NaN
    df['Subsection'] = np.where(
        df['Account'].notna() & df[value_columns].isna().all(axis=1),
        df['Account'],
        np.nan
    )

    # Forward fill Subsection within each Section
    df['Subsection'] = df.groupby('Section Order')['Subsection'].ffill()

    # Drop rows where Subsection == Account and all value columns are NaN
    df = df.drop(df[(df['Subsection'] == df['Account']) & df[value_columns].isna().all(axis=1)].index)

    # Reset index
    df = df.reset_index(drop=True)

    # Reorder columns: Section Order, Section, Subsection, Account, then all value columns
    df = df[['Section Order', 'Section', 'Subsection', 'Account'] + value_columns]

    # Add Subsection Order column - assign incrementing order to each unique subsection within each section (starts at 1 per section)
    df['Subsection Order'] = df.groupby('Section Order')['Subsection'].transform(lambda x: pd.factorize(x)[0] + 1)

    # Add Account Order column - incrementing from 1 to the last row
    df['Account Order'] = range(1, len(df) + 1)

    # Reorder columns: Section Order, Section, Subsection, Subsection Order, Account Order, Account, then all value columns
    df = df[['Section Order', 'Section', 'Subsection Order', 'Subsection', 'Account Order', 'Account'] + value_columns]

    # Fill NaN values in Section, Subsection, and Account with empty strings
    df[['Section', 'Subsection', 'Account']] = df[['Section', 'Subsection', 'Account']].fillna('')

    df['Legal Entity'] = legal_entity
    df['Report ID'] = report_id
    df['Created At'] = created_at
    df['Report Month'] = report_month

    if long_format:
        id_cols = ['Section Order', 'Section', 'Subsection Order', 'Subsection', 'Account Order', 'Account', 'Legal Entity', 'Report ID', 'Created At', 'Report Month']
        df = df.melt(id_vars=id_cols, value_vars=value_columns, var_name='Period', value_name='Amount')
        
        # Add period_order column to preserve original column order
        period_order_map = {col: idx + 1 for idx, col in enumerate(value_columns)}
        df['Period Order'] = df['Period'].map(period_order_map)

    print(f"Finished transforming Budget Summary. Resulting DataFrame has {len(df)} rows and {len(df.columns)} columns.")
    return df