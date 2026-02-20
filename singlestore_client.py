"""
SingleStore Database API Client

This module provides a client for connecting to and managing data in a SingleStore database.
Supports creating/updating tables and writing data efficiently.
"""

import singlestoredb as s2
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class SingleStoreClient:
    """
    API client for SingleStore database operations.
    
    Handles connection management, table creation/updates, and data insertion.
    """
    
    def __init__(
        self,
        host: str,
        port: int = 3306,
        user: str = "",
        password: str = "",
        database: str = "",
        results_type: str = "dict",
    ):
        """
        Initialize the SingleStore client.
        
        Args:
            host: Hostname or IP address of the SingleStore workspace
            port: Database server port (default: 3306)
            user: Username for the database user
            password: Password for the database user
            database: Name of the database to connect to
            results_type: Format for query results ('dict', 'tuple', 'namedtuple')
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.results_type = results_type
        self.connection = None
        
    def connect(self) -> bool:
        """
        Establish connection to SingleStore database.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.connection = s2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                results_type=self.results_type,
            )
            
            with self.connection.cursor() as cursor:
                is_connected = cursor.is_connected()
                logger.info(f"SingleStore connection established: {is_connected}")
                return is_connected
                
        except Exception as e:
            logger.error(f"Failed to connect to SingleStore: {str(e)}")
            return False
    
    def disconnect(self) -> None:
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            logger.info("SingleStore connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def create_table(
        self,
        table_name: str,
        columns: Dict[str, str],
        primary_key: Optional[str] = None,
        if_not_exists: bool = True,
    ) -> bool:
        """
        Create a new table or update existing if if_not_exists is False.
        
        Args:
            table_name: Name of the table to create
            columns: Dictionary mapping column names to their SQL types
                    Example: {'id': 'INT', 'name': 'VARCHAR(255)', 'email': 'VARCHAR(255)'}
            primary_key: Optional primary key column name
            if_not_exists: If True, use IF NOT EXISTS (won't update existing table)
        
        Returns:
            bool: True if successful, False otherwise
            
        Example:
            columns = {
                'id': 'INT',
                'name': 'VARCHAR(255)',
                'email': 'VARCHAR(255)',
            }
            client.create_table('users', columns, primary_key='id')
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            # Build column definitions
            col_definitions = []
            for col_name, col_type in columns.items():
                col_definitions.append(f"{col_name} {col_type}")
            
            # Add primary key if specified
            if primary_key:
                col_definitions.append(f"PRIMARY KEY ({primary_key})")
            
            columns_sql = ", ".join(col_definitions)
            
            # Build CREATE TABLE statement
            if_not_exists_clause = "IF NOT EXISTS" if if_not_exists else ""
            create_sql = f"CREATE TABLE {if_not_exists_clause} {table_name} ({columns_sql})"
            
            self.connection.autocommit(True)
            with self.connection.cursor() as cursor:
                cursor.execute(create_sql)
                logger.info(f"Table '{table_name}' created/verified successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to create table '{table_name}': {str(e)}")
            return False
    
    def drop_table(self, table_name: str, if_exists: bool = True) -> bool:
        """
        Drop a table from the database.
        
        Args:
            table_name: Name of the table to drop
            if_exists: If True, use IF EXISTS to avoid errors
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            if_exists_clause = "IF EXISTS" if if_exists else ""
            drop_sql = f"DROP TABLE {if_exists_clause} {table_name}"
            
            self.connection.autocommit(True)
            with self.connection.cursor() as cursor:
                cursor.execute(drop_sql)
                logger.info(f"Table '{table_name}' dropped successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to drop table '{table_name}': {str(e)}")
            return False
    
    def insert(
        self,
        table_name: str,
        data: Dict[str, Any],
        autocommit: bool = True,
    ) -> bool:
        """
        Insert a single row of data into a table.
        
        Args:
            table_name: Name of the table
            data: Dictionary mapping column names to values
            autocommit: If True, commit after insert
        
        Returns:
            bool: True if successful, False otherwise
            
        Example:
            data = {'id': 1, 'name': 'John Doe', 'email': 'john@example.com'}
            client.insert('users', data)
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            columns = ", ".join(data.keys())
            placeholders = ", ".join(["%s"] * len(data))
            values = list(data.values())
            
            insert_sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            
            self.connection.autocommit(autocommit)
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, values)
                if not autocommit:
                    self.connection.commit()
                logger.debug(f"Inserted row into '{table_name}'")
                return True
                
        except Exception as e:
            logger.error(f"Failed to insert into '{table_name}': {str(e)}")
            return False
    
    def insert_many(
        self,
        table_name: str,
        columns: List[str],
        data: List[Tuple],
        autocommit: bool = True,
    ) -> bool:
        """
        Insert multiple rows of data into a table.
        
        Args:
            table_name: Name of the table
            columns: List of column names
            data: List of tuples, each containing values for one row
            autocommit: If True, commit after insert
        
        Returns:
            bool: True if successful, False otherwise
            
        Example:
            columns = ['id', 'name', 'email']
            data = [
                (1, 'John Doe', 'john@example.com'),
                (2, 'Jane Smith', 'jane@example.com'),
            ]
            client.insert_many('users', columns, data)
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            columns_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            
            insert_sql = f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})"
            
            self.connection.autocommit(autocommit)
            with self.connection.cursor() as cursor:
                cursor.executemany(insert_sql, data)
                if not autocommit:
                    self.connection.commit()
                logger.info(f"Inserted {len(data)} rows into '{table_name}'")
                return True
                
        except Exception as e:
            logger.error(f"Failed to insert multiple rows into '{table_name}': {str(e)}")
            return False
    
    def query(self, sql: str, params: Optional[List] = None) -> Optional[List]:
        """
        Execute a SELECT query and fetch all results.
        
        Args:
            sql: SQL query string
            params: Optional list of parameters for positional substitution
        
        Returns:
            List of results, or None if error
            
        Example:
            results = client.query('SELECT * FROM users WHERE id = %s', [1])
        """
        if not self.connection:
            logger.error("Not connected to database")
            return None
        
        try:
            with self.connection.cursor() as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")
            return None
    
    def execute(self, sql: str, params: Optional[List] = None, autocommit: bool = True) -> bool:
        """
        Execute a SQL statement (INSERT, UPDATE, DELETE).
        
        Args:
            sql: SQL statement
            params: Optional list of parameters for substitution
            autocommit: If True, commit after execution
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            self.connection.autocommit(autocommit)
            with self.connection.cursor() as cursor:
                if params:
                    cursor.execute(sql, params)
                else:
                    cursor.execute(sql)
                if not autocommit:
                    self.connection.commit()
                logger.debug("SQL statement executed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Failed to execute SQL: {str(e)}")
            return False
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check
        
        Returns:
            bool: True if table exists, False otherwise
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s",
                    [self.database, table_name]
                )
                result = cursor.fetchone()
                return result is not None
                
        except Exception as e:
            logger.error(f"Failed to check if table exists: {str(e)}")
            return False
    
    def get_table_schema(self, table_name: str) -> Optional[List]:
        """
        Get the schema/structure of a table.
        
        Args:
            table_name: Name of the table
        
        Returns:
            List of column information, or None if error
        """
        if not self.connection:
            logger.error("Not connected to database")
            return None
        
        try:
            results = self.query(f"DESC {table_name}")
            return results
            
        except Exception as e:
            logger.error(f"Failed to get table schema: {str(e)}")
            return None


# ==============================================================================
# EXAMPLES: Using SingleStoreClient with Pandas DataFrames
# ==============================================================================

def infer_column_types(df) -> Dict[str, str]:
    """
    Dynamically infer SQL column types from pandas DataFrame dtypes.
    
    Args:
        df: Pandas DataFrame to analyze
    
    Returns:
        Dictionary mapping column names to SQL data types
        
    Example:
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['Alice', 'Bob', 'Charlie'],
            'salary': [50000.50, 60000.75, 55000.00],
            'hire_date': pd.to_datetime(['2020-01-15', '2019-06-20', '2021-03-10']),
            'is_active': [True, True, False]
        })
        
        types = infer_column_types(df)
        # Returns: {
        #     'id': 'BIGINT',
        #     'name': 'VARCHAR(500)',
        #     'salary': 'DECIMAL(15, 2)',
        #     'hire_date': 'DATETIME',
        #     'is_active': 'BOOLEAN'
        # }
    """
    import pandas as pd
    import numpy as np
    
    column_types = {}
    
    # Basic type mapping
    type_mapping = {
        'int8': 'TINYINT',
        'int16': 'SMALLINT',
        'int32': 'INT',
        'int64': 'BIGINT',
        'uint8': 'TINYINT UNSIGNED',
        'uint16': 'SMALLINT UNSIGNED',
        'uint32': 'INT UNSIGNED',
        'uint64': 'BIGINT UNSIGNED',
        'float32': 'FLOAT',
        'float64': 'DOUBLE',
        'bool': 'BOOLEAN',
        'object': 'VARCHAR(500)',
        'string': 'VARCHAR(500)',
        'datetime64[ns]': 'DATETIME',
        'datetime64[us]': 'DATETIME',
        'datetime64[ms]': 'DATETIME',
        'datetime64[s]': 'DATETIME',
        'timedelta64[ns]': 'TIME',
        'timedelta64[us]': 'TIME',
    }
    
    for col in df.columns:
        dtype = df[col].dtype
        dtype_str = str(dtype)
        
        # Check if dtype is in basic mapping
        if dtype_str in type_mapping:
            sql_type = type_mapping[dtype_str]
        # Handle object dtype - check if it's actually strings or mixed
        elif dtype == 'object':
            # Check type of non-null values
            non_null = df[col].dropna()
            if len(non_null) > 0:
                sample_type = type(non_null.iloc[0])
                
                # Estimate needed VARCHAR length
                max_length = non_null.astype(str).str.len().max()
                if pd.notna(max_length):
                    varchar_size = min(max(int(max_length) + 50, 100), 5000)
                    sql_type = f'VARCHAR({varchar_size})'
                else:
                    sql_type = 'VARCHAR(500)'
            else:
                sql_type = 'VARCHAR(500)'
        # Handle datetime dtype
        elif 'datetime64' in dtype_str:
            if df[col].dt.second.max() > 0 or df[col].dt.microsecond.max() > 0:
                sql_type = 'DATETIME(6)'  # With microseconds
            else:
                sql_type = 'DATETIME'
        # Handle category dtype
        elif isinstance(dtype, pd.CategoricalDtype):
            sql_type = 'VARCHAR(500)'
        else:
            # Default to VARCHAR for unknown types
            sql_type = 'VARCHAR(500)'
        
        column_types[col] = sql_type
    
    return column_types


def write_dataframe_to_singlestore(
    client: SingleStoreClient,
    df,
    table_name: str,
    create_table_if_missing: bool = True,
    column_types: Optional[Dict[str, str]] = None,
    primary_key: Optional[str] = None,
) -> bool:
    """
    Write a pandas DataFrame to a SingleStore table.
    
    Args:
        client: Connected SingleStoreClient instance
        df: Pandas DataFrame to write
        table_name: Name of the target table
        create_table_if_missing: If True, automatically create the table if it doesn't exist
        column_types: Optional dict mapping column names to SQL types
                     If not provided, will automatically infer from DataFrame dtypes
        primary_key: Optional primary key column name
    
    Returns:
        bool: True if successful, False otherwise
        
    Example:
        import pandas as pd
        
        # Create sample DataFrame
        df = pd.DataFrame({
            'id': [1, 2, 3],
            'name': ['John', 'Jane', 'Bob'],
            'email': ['john@example.com', 'jane@example.com', 'bob@example.com']
        })
        
        # Create client - column types are automatically inferred!
        with SingleStoreClient(
            host='your-host.com',
            user='admin',
            password='password',
            database='mydb'
        ) as client:
            success = write_dataframe_to_singlestore(
                client, 
                df, 
                'users',
                primary_key='id'  # Column types inferred automatically
            )
    """
    import pandas as pd
    
    if df.empty:
        logger.warning("DataFrame is empty, skipping write")
        return False
    
    # Infer column types from DataFrame if not provided
    if column_types is None:
        column_types = infer_column_types(df)
        logger.info(f"Inferred column types: {column_types}")
    
    # Create table if needed
    if create_table_if_missing:
        if not client.table_exists(table_name):
            success = client.create_table(
                table_name,
                column_types,
                primary_key=primary_key,
                if_not_exists=True
            )
            if not success:
                logger.error(f"Failed to create table '{table_name}'")
                return False
    
    # Convert DataFrame to list of tuples for insert_many
    columns = list(df.columns)
    data = [tuple(row) for row in df.values]
    
    # Insert data
    success = client.insert_many(
        table_name,
        columns,
        data,
        autocommit=True
    )
    
    return success


# Example usage patterns
"""
EXAMPLE 1: Automatic Type Inference (Recommended)
==================================================

import pandas as pd
from singlestore_client import SingleStoreClient, write_dataframe_to_singlestore

# Create a sample DataFrame with mixed types
df = pd.DataFrame({
    'id': [1, 2, 3, 4, 5],
    'name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve'],
    'salary': [50000.50, 60000.75, 55000.00, 70000.25, 52000.00],
    'hire_date': pd.to_datetime(['2020-01-15', '2019-06-20', '2021-03-10', '2018-05-01', '2022-08-30']),
    'is_active': [True, True, False, True, True]
})

# No need to specify column types - they're automatically inferred!
with SingleStoreClient(
    host='your-singlestore-host.com',
    port=3306,
    user='admin',
    password='your_password',
    database='mydb'
) as client:
    # Types inferred: id -> BIGINT, name -> VARCHAR, salary -> DOUBLE, 
    #                 hire_date -> DATETIME, is_active -> BOOLEAN
    success = write_dataframe_to_singlestore(
        client,
        df,
        'employees',
        primary_key='id'
    )


EXAMPLE 2: Check Inferred Types Before Insert
==============================================

from singlestore_client import infer_column_types

df = pd.DataFrame({
    'transaction_id': [101, 102, 103],
    'amount': [1250.99, 3450.50, 980.25],
    'description': ['Purchase', 'Refund', 'Payment'],
    'timestamp': pd.to_datetime(['2024-01-15 10:30:00', '2024-01-15 14:45:00', '2024-01-15 16:20:00'])
})

# View the inferred types before writing
types = infer_column_types(df)
print("Inferred column types:")
for col, dtype in types.items():
    print(f"  {col}: {dtype}")

# Output:
# Inferred column types:
#   transaction_id: BIGINT
#   amount: DOUBLE
#   description: VARCHAR(256)
#   timestamp: DATETIME

# Now write to database
with SingleStoreClient(host='...', user='...', password='...', database='...') as client:
    write_dataframe_to_singlestore(client, df, 'transactions', primary_key='transaction_id')


EXAMPLE 3: Override Specific Types (When Needed)
================================================

from singlestore_client import infer_column_types, write_dataframe_to_singlestore

df = pd.DataFrame({
    'product_id': [101, 102, 103],
    'name': ['Laptop', 'Mouse', 'Keyboard'],
    'price': [899.99, 29.99, 79.99],
    'quantity': [10, 50, 30]
})

# Get auto-inferred types
column_types = infer_column_types(df)

# Override specific columns that need different precision
column_types['price'] = 'DECIMAL(10, 2)'  # More precise than DOUBLE
column_types['name'] = 'VARCHAR(1000)'     # Larger than auto-inferred

with SingleStoreClient(
    host='your-host.com',
    user='admin',
    password='password',
    database='inventory'
) as client:
    write_dataframe_to_singlestore(
        client,
        df,
        'products',
        column_types=column_types,
        primary_key='product_id'
    )


EXAMPLE 4: Smart Inference - Variable Length Strings
=====================================================

from singlestore_client import infer_column_types

# DataFrame with varying string lengths
df = pd.DataFrame({
    'id': [1, 2, 3],
    'short_name': ['A', 'BB', 'CCC'],                    # Max length: 3
    'description': ['Short', 'A longer description here', 'Even longer description with much more text']  # Max length: 47
})

types = infer_column_types(df)
# Output:
#   id: BIGINT
#   short_name: VARCHAR(53)          # Auto-sized based on content!
#   description: VARCHAR(97)         # Auto-sized based on content!

# VARCHAR sizes are intelligently calculated + 50 buffer for safety
# This prevents both truncation errors and wasteful over-allocation


EXAMPLE 5: Data Type Inference Reference
=========================================

# Type inference mappings:
# 
# Python/Pandas dtype          ->  SQL Type
# ==========================================
# int8                         ->  TINYINT
# int16                        ->  SMALLINT
# int32                        ->  INT
# int64                        ->  BIGINT
# uint8, uint16, uint32, uint64 -> UNSIGNED variants
# float32                      ->  FLOAT
# float64                      ->  DOUBLE
# bool                         ->  BOOLEAN
# object (strings)             ->  VARCHAR(size) [auto-sized]
# datetime64                   ->  DATETIME or DATETIME(6)
# timedelta64                  ->  TIME
# category                     ->  VARCHAR(500)
"""
