"""
Database Operations Module

Handles writing transformed financial report data to SingleStore database.
"""

import pandas as pd
from datetime import datetime
from decouple import config
import logging
import re
from .singlestore_client import SingleStoreClient

logger = logging.getLogger(__name__)


def infer_column_types(df: pd.DataFrame) -> dict:
    """
    Infer SQL column types from pandas DataFrame dtypes.
    
    Args:
        df: Pandas DataFrame to analyze
    
    Returns:
        Dictionary mapping column names to SQL data types
    """
    column_types = {}
    
    for col, dtype in df.dtypes.items():
        dtype_name = str(dtype)
        
        # Map pandas dtypes to SQL types
        if 'int' in dtype_name:
            column_types[col] = 'BIGINT'
        elif 'float' in dtype_name:
            column_types[col] = 'DOUBLE'
        elif 'bool' in dtype_name:
            column_types[col] = 'BOOLEAN'
        elif 'datetime' in dtype_name:
            column_types[col] = 'DATETIME'
        else:
            # Default to VARCHAR for object types and strings
            column_types[col] = 'VARCHAR(500)'
    
    return column_types


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
                    alter_sql = f"ALTER TABLE {table_name} ADD COLUMN `{col_name}` {col_type}"
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
        
        # Make a copy to avoid modifying original
        df = df.copy()
        
        # Normalize tenant name for use in table names (alphanumeric + underscore only)
        def normalize_tenant_name(name):
            """Convert tenant name to lowercase alphanumeric with underscores"""
            name = name.lower()
            name = name.replace(' ', '_')
            name = re.sub(r'[^a-z0-9_]', '', name)
            return name
        
        # Normalize the tenant name for table naming
        normalized_tenant = normalize_tenant_name(tenant_name)
        
        # Ensure tenant column exists
        if 'tenant' not in df.columns:
            df['tenant'] = tenant_name
        
        # Normalize column names to snake_case (e.g., 'Section Order' -> 'section_order')
        def to_snake_case(name):
            """Convert column names to snake_case"""
            name = name.replace(' ', '_')
            name = name.lower()
            name = re.sub(r'[^a-z0-9_]', '', name)
            return name
        
        # Rename all columns to snake_case FIRST (before table creation)
        df.columns = [to_snake_case(col) for col in df.columns]
        
        # Map DataFrame columns to database column names (handle naming mismatches)
        database_column_mapping = {
            'report_month': 'report_period',  # DataFrame uses report_month, DB uses report_period
            'amount': 'value',                 # DataFrame uses amount, DB uses value
            'period_order': 'period_order_seq' # Rename if period_order conflicts
        }
        
        # Apply the database column mapping for columns that exist
        rename_mapping = {df_col: db_col for df_col, db_col in database_column_mapping.items() 
                         if df_col in df.columns}
        
        if rename_mapping:
            df = df.rename(columns=rename_mapping)
            logger.info(f"Applied database column mappings: {rename_mapping}")
        
        # Get table name with normalized tenant prefix
        table_name = f"{normalized_tenant}_xero_{report_type}"
        
        # Check if table exists, if not create it
        if not client.table_exists(table_name):
            logger.info(f"Table '{table_name}' does not exist. Creating table...")
            
            # Infer column types from DataFrame (now with normalized column names)
            column_types = infer_column_types(df)
            logger.info(f"Inferred column types: {column_types}")
            
            # Create table
            if client.create_table(table_name, column_types, if_not_exists=True):
                logger.info(f"✓ Table '{table_name}' created successfully")
                
                # Create indexes for common query columns
                indexes = [
                    ('report_period', f"{table_name}_idx_report_period"),
                    ('legal_entity', f"{table_name}_idx_legal_entity"),
                    ('report_id', f"{table_name}_idx_report_id"),
                    ('period', f"{table_name}_idx_period"),
                ]
                
                for col, idx_name in indexes:
                    if col in df.columns:
                        success = client.create_index(table_name, [col], idx_name)
                        if success:
                            logger.info(f"✓ Created index '{idx_name}' on column '{col}'")
                        else:
                            logger.warning(f"Failed to create index '{idx_name}' on column '{col}'")
            else:
                logger.error(f"Failed to create table '{table_name}'")
                return False
        else:
            logger.info(f"Table '{table_name}' already exists")
        
        logger.info(f"Preparing to insert {len(df)} rows into table '{table_name}'")
        logger.info(f"Columns: {list(df.columns)}")
        
        # Convert DataFrame to list of tuples
        columns = list(df.columns)
        data = [tuple(row) for row in df.values]
        
        # Insert data in batches
        batch_size = 1000
        total_inserted = 0
        
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            if not client.insert_many(table_name, columns, batch):
                logger.error(f"Failed to insert batch {batch_num} for {report_type}")
                return False
            
            total_inserted += len(batch)
            logger.info(f"Inserted batch {batch_num} ({len(batch)} rows)")
        
        logger.info(f"✓ Successfully inserted {total_inserted} rows into {table_name}")
        return True
        
    except Exception as e:
        logger.error(f"Error writing {report_type} data to database: {str(e)}", exc_info=True)
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
