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
        """
        if not self.connection:
            logger.error("Not connected to database")
            return False
        
        try:
            col_definitions = []
            for col_name, col_type in columns.items():
                col_definitions.append(f"{col_name} {col_type}")
            
            if primary_key:
                col_definitions.append(f"PRIMARY KEY ({primary_key})")
            
            columns_sql = ", ".join(col_definitions)
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
