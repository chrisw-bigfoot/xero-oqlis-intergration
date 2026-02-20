"""
Database Operations Module

Handles writing transformed financial report data to SingleStore database.
"""

import pandas as pd
from datetime import datetime
from decouple import config
import logging
from .singlestore_client import SingleStoreClient

logger = logging.getLogger(__name__)


def get_database_client():
    """
    Create and return a SingleStore database client using environment variables.
    
    Returns:
        SingleStoreClient: Connected database client
    """
    client = SingleStoreClient(
        host=config('IP'),
        port=config('PORT', cast=int, default=3306),
        user=config('USER'),
        password=config('PASSWORD'),
        database=config('DATABASE'),
        results_type='dict'
    )
    
    if not client.connect():
        raise Exception("Failed to connect to SingleStore database")
    
    return client


def create_report_tables(client: SingleStoreClient, report_type: str) -> bool:
    """
    Create table for a specific report type if it doesn't exist.
    Automatically adds missing columns to existing tables.
    
    Args:
        client: SingleStoreClient instance
        report_type: Type of report (balance_sheet, profit_and_loss, etc.)
    
    Returns:
        bool: True if successful, False otherwise
    """
    table_name = f"xero_{report_type}"
    
    # Define common columns that all report types share
    columns = {
        'id': 'BIGINT AUTO_INCREMENT',
        'report_id': 'VARCHAR(100)',
        'legal_entity': 'VARCHAR(500)',
        'tenant': 'VARCHAR(500)',
        'section': 'VARCHAR(500)',
        'section_order': 'INT',
        'subsection': 'VARCHAR(500)',
        'subsection_order': 'INT',
        'account': 'VARCHAR(500)',
        'account_order': 'INT',
        'value': 'DECIMAL(18, 4)',
        'period_str': 'VARCHAR(50)',
        'period': 'VARCHAR(100)',
        'period_date': 'VARCHAR(50)',
        'year': 'INT',
        'month': 'INT',
        'report_period': 'VARCHAR(255)',
        'report_period_str': 'VARCHAR(255)',
        'report_date_at': 'VARCHAR(100)',
        'created_at': 'VARCHAR(100)',
    }
    
    # Try to create the table if it doesn't exist
    if not client.create_table(
        table_name=table_name,
        columns=columns,
        primary_key='id',
        if_not_exists=True
    ):
        return False
    
    # Add any missing columns to existing table
    try:
        if client.table_exists(table_name):
            # Get existing columns using information_schema - try different queries
            existing_cols = set()
            
            try:
                # Try standard MySQL information_schema query
                existing_cols_result = client.query(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    [table_name]
                )
                
                if existing_cols_result:
                    existing_cols = {row['COLUMN_NAME'] if isinstance(row, dict) else row[0] 
                                    for row in existing_cols_result}
            except Exception as query_error:
                logger.warning(f"Could not query existing columns: {str(query_error)}")
                # Fallback: try to get columns by attempting a simple SELECT
                try:
                    result = client.query(f"SELECT * FROM {table_name} LIMIT 1", [])
                    if result and len(result) > 0:
                        existing_cols = set(result[0].keys() if isinstance(result[0], dict) else [])
                except:
                    existing_cols = set()
            
            logger.info(f"Existing columns in '{table_name}': {existing_cols}")
            
            # Add any missing columns (skip 'id' as it may have AUTO_INCREMENT constraints)
            for col_name, col_type in columns.items():
                # Skip 'id' column - exists in all tables and can't be re-added with AUTO_INCREMENT
                if col_name == 'id':
                    continue
                    
                if col_name not in existing_cols:
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                    try:
                        client.connection.autocommit(True)
                        with client.connection.cursor() as cursor:
                            cursor.execute(alter_sql)
                        logger.info(f"Successfully added missing column '{col_name}' (type: {col_type}) to table '{table_name}'")
                    except Exception as add_col_error:
                        logger.error(f"Error adding column '{col_name}' to '{table_name}': {str(add_col_error)}")
                        # Don't continue - this is a critical error
                        return False
                            
    except Exception as e:
        logger.error(f"Critical error updating table schema for '{table_name}': {str(e)}")
        return False
    
    return True


def write_dataframe_to_database(
    df: pd.DataFrame,
    report_type: str,
    report_id: str,
    tenant_name: str,
    dataset_type_name: str = None
) -> bool:
    """
    Write transformed DataFrame to SingleStore database.
    
    Args:
        df: Transformed DataFrame with report data
        report_type: Type of report (balance_sheet, profit_and_loss, etc.)
        report_id: Unique report identifier
        tenant_name: Name of the tenant
        dataset_type_name: Optional dataset type name for logging
    
    Returns:
        bool: True if successful, False otherwise
    """
    client = None
    try:
        client = get_database_client()
        
        # Create table if it doesn't exist (includes schema migration)
        if not create_report_tables(client, report_type):
            logger.error(f"Failed to create/update table for {report_type}")
            return False
        
        # Prepare data for insertion
        table_name = f"xero_{report_type}"
        
        # Create a copy to avoid modifying original
        df = df.copy()
        
        # Ensure tenant column exists in DataFrame
        if 'tenant' not in df.columns:
            df['tenant'] = tenant_name
        
        # Get all columns from the DataFrame
        columns = list(df.columns)
        
        # Convert data types for database compatibility
        # Known datetime columns that need special handling
        datetime_columns = ['report_date_at', 'created_at', 'period', 'period_date']
        
        def safe_datetime_convert(val, col_name):
            """Safely convert a value to datetime string or None"""
            if pd.isna(val) or val is None:
                return None
            try:
                # Convert to string to handle all types uniformly
                val_str = str(val).strip()
                
                # If it's an empty string or 'NaT', return None
                if not val_str or val_str.lower() in ['nat', 'none', '']:
                    return None
                
                # Return the string as-is, let database parse the datetime format
                # (e.g., "31 December 2025" will be parsed by SingleStore)
                return val_str
                    
            except (ValueError, AttributeError, TypeError) as e:
                logger.warning(f"Could not process {col_name}={val}: {str(e)}")
                return None
        
        for col in df.columns:
            # Convert datetime columns to ISO format strings
            if pd.api.types.is_datetime64_any_dtype(df[col]) or col in datetime_columns:
                try:
                    df[col] = df[col].apply(lambda val: safe_datetime_convert(val, col))
                except Exception as dt_error:
                    logger.warning(f"Error converting datetime column '{col}': {str(dt_error)}. Setting to None.")
                    df[col] = None
                    
            # Convert numeric columns, filling NaN with 0
            elif col in ['value', 'section_order', 'subsection_order', 'account_order', 'year', 'month']:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            # Fill NaN in string columns with empty string
            elif df[col].dtype == 'object':
                df[col] = df[col].fillna('')
            else:
                # For any remaining columns, handle NaN
                df[col] = df[col].fillna('')
        
        # Convert DataFrame to list of tuples for insertion
        data_tuples = [
            tuple(row) for row in df[columns].values
        ]
        
        # Log information about the data being inserted
        logger.info(f"Preparing to insert {len(data_tuples)} rows for {report_type}")
        logger.info(f"Columns: {columns}")
        
        # Log data types for debugging
        for col in columns:
            if col in df.columns:
                logger.debug(f"Column '{col}' dtype: {df[col].dtype}, sample values: {df[col].head(3).tolist()}")
        
        if len(data_tuples) > 0:
            logger.debug(f"Sample row: {data_tuples[0]}")
        
        # Insert data in batches
        batch_size = 1000
        total_inserted = 0
        
        for i in range(0, len(data_tuples), batch_size):
            batch = data_tuples[i:i + batch_size]
            
            if not client.insert_many(table_name, columns, batch):
                logger.error(f"Failed to insert batch {i // batch_size + 1} for {report_type}")
                return False
            
            total_inserted += len(batch)
        
        logger.info(f"Successfully inserted {total_inserted} rows into {table_name} for report {report_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing {report_type} data to database: {str(e)}")
        return False
    finally:
        if client:
            client.disconnect()


def write_reports_to_database(
    reports_data: dict,
    report_id: str,
    tenant_name: str
) -> dict:
    """
    Write multiple report DataFrames to the database.
    
    Args:
        reports_data: Dictionary mapping report_type to DataFrame
                     Example: {'balance_sheet': df1, 'profit_and_loss': df2}
        report_id: Unique report identifier
        tenant_name: Name of the tenant
    
    Returns:
        dict: Dictionary mapping report_type to success status
              Example: {'balance_sheet': True, 'profit_and_loss': False}
    """
    results = {}
    
    for report_type, df in reports_data.items():
        if df is None or len(df) == 0:
            results[report_type] = False
            logger.warning(f"Skipping empty DataFrame for {report_type}")
            continue
        
        success = write_dataframe_to_database(
            df=df,
            report_type=report_type,
            report_id=report_id,
            tenant_name=tenant_name,
            dataset_type_name=report_type
        )
        
        results[report_type] = success
    
    return results
