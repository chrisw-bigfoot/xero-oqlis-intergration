import pandas as pd
import numpy as np
from datetime import datetime
import re
from pathlib import Path




def transform_profit_loss_ly(file_path: str, legal_entity: str = None, report_id: str = None, created_at: str = None, report_month: str = None, long_format: bool = False) -> pd.DataFrame:
    print(f"Transforming Profit and Loss LY from file: {file_path} ...")

    # Read the Excel file, skipping the first 4 rows which contain metadata
    df = pd.read_excel(file_path, skiprows=4, header=0)

    df.dropna(axis=0, how='all', inplace=True)  # Drop rows that are completely empty

    df = df.rename(columns={'Unnamed: 0': 'Section'})
    df['Section'] = df['Section'].ffill()  

    df = df.dropna(subset=df.columns.difference(['Section']), how='all')

    # Add Section Order column - assign incrementing order to each unique section
    df['Section Order'] = pd.factorize(df['Section'])[0] + 1

    # Get value columns (all columns except Section Order, Section, and Account)
    value_columns = [col for col in df.columns if col not in ['Section Order', 'Section', 'Account']]

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

    print(f"Finished transforming Profit and Loss LY. Resulting DataFrame has {len(df)} rows and {len(df.columns)} columns.")
    return df


# Legacy wrapper for backward compatibility - accepts old parameters
def transform_profit_and_loss_vs_py(
    file_path: str,
    drop_profit_rows: bool = True,
    melt_to_long: bool = False
) -> pd.DataFrame:
    """
    Legacy wrapper for transform_profit_loss_ly for backward compatibility.
    """
    return transform_profit_loss_ly(file_path=file_path, long_format=melt_to_long)