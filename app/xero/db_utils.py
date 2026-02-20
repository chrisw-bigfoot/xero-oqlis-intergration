"""
Database Utility Functions

Provides utility functions for managing SingleStore database operations
such as dropping tables, deleting records, clearing data, etc.
"""

import logging
from decouple import config
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


def drop_table(table_name: str, confirm: bool = False) -> bool:
    """
    Drop a single table from the database.
    
    Args:
        table_name: Name of the table to drop (e.g., 'xero_balance_sheet')
        confirm: If True, drops without warning. If False, logs warning.
    
    Returns:
        bool: True if successful, False otherwise
    """
    client = None
    try:
        client = get_database_client()
        
        if not confirm:
            logger.warning(f"About to drop table '{table_name}'. Pass confirm=True to proceed.")
            return False
        
        drop_sql = f"DROP TABLE IF EXISTS {table_name}"
        client.connection.autocommit(True)
        with client.connection.cursor() as cursor:
            cursor.execute(drop_sql)
        
        logger.info(f"Successfully dropped table '{table_name}'")
        return True
        
    except Exception as e:
        logger.error(f"Error dropping table '{table_name}': {str(e)}")
        return False
    finally:
        if client:
            client.disconnect()


def drop_all_report_tables(confirm: bool = False) -> dict:
    """
    Drop all report tables from the database.
    
    Args:
        confirm: If True, drops all tables. If False, logs warning and returns False.
    
    Returns:
        dict: Dictionary mapping table_name to success status
              Example: {'xero_balance_sheet': True, 'xero_profit_and_loss': True}
    """
    report_types = [
        'balance_sheet',
        'budget_summary',
        'budget_variance',
        'profit_and_loss',
        'profit_and_loss_vs_ly'
    ]
    
    results = {}
    
    for report_type in report_types:
        table_name = f"xero_{report_type}"
        results[table_name] = drop_table(table_name, confirm=confirm)
    
    return results


def delete_table_records(table_name: str, where_clause: str = None, confirm: bool = False) -> int:
    """
    Delete records from a table.
    
    Args:
        table_name: Name of the table
        where_clause: Optional WHERE clause for conditional deletion
                     Example: "report_id = '202302-abc123'"
                     If None, deletes ALL records
        confirm: If True, performs the deletion. If False, logs warning.
    
    Returns:
        int: Number of rows affected (or -1 if failed)
    """
    client = None
    try:
        client = get_database_client()
        
        if not confirm:
            logger.warning(f"About to delete records from '{table_name}'. Pass confirm=True to proceed.")
            return -1
        
        if where_clause:
            delete_sql = f"DELETE FROM {table_name} WHERE {where_clause}"
            logger.warning(f"Deleting records from '{table_name}' WITH condition: {where_clause}")
        else:
            delete_sql = f"DELETE FROM {table_name}"
            logger.warning(f"Deleting ALL records from '{table_name}'")
        
        client.connection.autocommit(True)
        with client.connection.cursor() as cursor:
            cursor.execute(delete_sql)
            rows_affected = cursor.rowcount
        
        logger.info(f"Deleted {rows_affected} rows from '{table_name}'")
        return rows_affected
        
    except Exception as e:
        logger.error(f"Error deleting records from '{table_name}': {str(e)}")
        return -1
    finally:
        if client:
            client.disconnect()


def clear_table(table_name: str, confirm: bool = False) -> bool:
    """
    Clear all records from a table but keep the table structure.
    
    Args:
        table_name: Name of the table to clear
        confirm: If True, clears the table. If False, logs warning.
    
    Returns:
        bool: True if successful, False otherwise
    """
    client = None
    try:
        client = get_database_client()
        
        if not confirm:
            logger.warning(f"About to clear all records from '{table_name}'. Pass confirm=True to proceed.")
            return False
        
        # Use TRUNCATE for faster clearing (removes all records but keeps structure)
        # Fallback to DELETE if TRUNCATE doesn't work
        try:
            truncate_sql = f"TRUNCATE TABLE {table_name}"
            client.connection.autocommit(True)
            with client.connection.cursor() as cursor:
                cursor.execute(truncate_sql)
            logger.info(f"Successfully truncated table '{table_name}'")
            return True
        except Exception as truncate_error:
            logger.warning(f"TRUNCATE failed for '{table_name}': {str(truncate_error)}. Trying DELETE...")
            # Fallback to DELETE
            delete_sql = f"DELETE FROM {table_name}"
            with client.connection.cursor() as cursor:
                cursor.execute(delete_sql)
            logger.info(f"Successfully cleared table '{table_name}' using DELETE")
            return True
        
    except Exception as e:
        logger.error(f"Error clearing table '{table_name}': {str(e)}")
        return False
    finally:
        if client:
            client.disconnect()


def get_table_record_count(table_name: str) -> int:
    """
    Get the number of records in a table.
    
    Args:
        table_name: Name of the table
    
    Returns:
        int: Number of records (or -1 if failed)
    """
    client = None
    try:
        client = get_database_client()
        
        count_sql = f"SELECT COUNT(*) as count FROM {table_name}"
        result = client.query(count_sql, [])
        
        if result and len(result) > 0:
            count = result[0].get('count', 0) if isinstance(result[0], dict) else result[0][0]
            logger.debug(f"Table '{table_name}' has {count} records")
            return count
        
        return 0
        
    except Exception as e:
        logger.error(f"Error getting record count for '{table_name}': {str(e)}")
        return -1
    finally:
        if client:
            client.disconnect()


def get_all_tables() -> list:
    """
    Get list of all tables in the database.
    
    Returns:
        list: List of table names
    """
    client = None
    try:
        client = get_database_client()
        
        show_sql = "SHOW TABLES"
        result = client.query(show_sql, [])
        
        if result:
            tables = [row.get('Tables_in_bigfoot', '') if isinstance(row, dict) else row[0] 
                     for row in result]
            return [t for t in tables if t]  # Filter out empty strings
        
        return []
        
    except Exception as e:
        logger.error(f"Error getting table list: {str(e)}")
        return []
    finally:
        if client:
            client.disconnect()


def get_table_schema(table_name: str) -> dict:
    """
    Get the schema (column information) of a table.
    
    Args:
        table_name: Name of the table
    
    Returns:
        dict: Dictionary mapping column_name to column_type
    """
    client = None
    try:
        client = get_database_client()
        
        schema_sql = f"DESCRIBE {table_name}"
        result = client.query(schema_sql, [])
        
        schema = {}
        if result:
            for row in result:
                col_name = row.get('Field', '') if isinstance(row, dict) else row[0]
                col_type = row.get('Type', '') if isinstance(row, dict) else row[1]
                schema[col_name] = col_type
        
        return schema
        
    except Exception as e:
        logger.error(f"Error getting schema for '{table_name}': {str(e)}")
        return {}
    finally:
        if client:
            client.disconnect()


def recreate_report_table(report_type: str, drop_existing: bool = True, confirm: bool = False) -> bool:
    """
    Drop and recreate a single report table with fresh schema.
    
    Args:
        report_type: Type of report (balance_sheet, profit_and_loss, etc.)
        drop_existing: If True, drops the existing table before recreating
        confirm: If True, proceeds with recreation. If False, logs warning.
    
    Returns:
        bool: True if successful, False otherwise
    """
    from .database import create_report_tables
    
    client = None
    try:
        if not confirm:
            logger.warning(f"About to recreate table for '{report_type}'. Pass confirm=True to proceed.")
            return False
        
        client = get_database_client()
        
        if drop_existing:
            table_name = f"xero_{report_type}"
            if not drop_table(table_name, confirm=True):
                return False
        
        # Create the table with fresh schema
        if not create_report_tables(client, report_type):
            return False
        
        logger.info(f"Successfully recreated table for report type '{report_type}'")
        return True
        
    except Exception as e:
        logger.error(f"Error recreating table for '{report_type}': {str(e)}")
        return False
    finally:
        if client:
            client.disconnect()


def recreate_all_report_tables(confirm: bool = False) -> dict:
    """
    Drop and recreate all report tables with fresh schema.
    
    Args:
        confirm: If True, proceeds with recreation. If False, logs warning.
    
    Returns:
        dict: Dictionary mapping report_type to success status
    """
    report_types = [
        'balance_sheet',
        'budget_summary',
        'budget_variance',
        'profit_and_loss',
        'profit_and_loss_vs_ly'
    ]
    
    results = {}
    
    for report_type in report_types:
        results[report_type] = recreate_report_table(report_type, confirm=confirm)
    
    return results
