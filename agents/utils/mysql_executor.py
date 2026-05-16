"""
MySQL executor for GenCode AI
Executes SQL queries safely (optional feature)
"""

import mysql.connector
from mysql.connector import Error
from django.conf import settings
import logging
import os

logger = logging.getLogger(__name__)


class MySQLExecutor:
    """
    Executes MySQL queries safely
    """
    
    def __init__(self):
        self.host = os.getenv('MYSQL_HOST', 'localhost')
        self.port = int(os.getenv('MYSQL_PORT', 3306))
        self.user = os.getenv('MYSQL_USER', 'root')
        self.password = os.getenv('MYSQL_PASSWORD', '')
        self.database = os.getenv('MYSQL_DATABASE', '')
    
    def execute(self, sql_code: str, database_name: str = None):
        """
        Execute SQL code
        
        Args:
            sql_code: SQL statements to execute
            database_name: Optional database name
            
        Returns:
            Dict with execution results
        """
        connection = None
        
        try:
            # Connect to MySQL
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=database_name or self.database
            )
            
            if connection.is_connected():
                cursor = connection.cursor()
                
                # Split SQL into individual statements
                statements = self._split_sql_statements(sql_code)
                
                results = []
                
                for statement in statements:
                    if statement.strip():
                        try:
                            cursor.execute(statement)
                            
                            # Get results if SELECT query
                            if statement.strip().upper().startswith('SELECT'):
                                results.append({
                                    'query': statement,
                                    'rows': cursor.fetchall(),
                                    'columns': [desc[0] for desc in cursor.description]
                                })
                            else:
                                results.append({
                                    'query': statement,
                                    'affected_rows': cursor.rowcount
                                })
                                
                        except Error as e:
                            logger.error(f"Error executing statement: {statement[:100]}... - {str(e)}")
                            results.append({
                                'query': statement,
                                'error': str(e)
                            })
                
                # Commit changes
                connection.commit()
                
                logger.info(f"Executed {len(statements)} SQL statements")
                
                return {
                    'success': True,
                    'statements_executed': len(statements),
                    'results': results
                }
                
        except Error as e:
            logger.error(f"MySQL connection error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
            
        finally:
            if connection and connection.is_connected():
                cursor.close()
                connection.close()
    
    def _split_sql_statements(self, sql_code: str) -> list:
        """
        Split SQL code into individual statements
        """
        # Simple split by semicolon (can be enhanced for complex cases)
        statements = []
        current_statement = []
        
        for line in sql_code.split('\n'):
            # Skip comments
            if line.strip().startswith('--') or line.strip().startswith('#'):
                continue
            
            current_statement.append(line)
            
            # Check if statement ends
            if ';' in line:
                statements.append('\n'.join(current_statement))
                current_statement = []
        
        # Add remaining statement if any
        if current_statement:
            statements.append('\n'.join(current_statement))
        
        return statements
    
    def test_connection(self):
        """
        Test MySQL connection
        """
        try:
            connection = mysql.connector.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password
            )
            
            if connection.is_connected():
                db_info = connection.get_server_info()
                connection.close()
                return {
                    'connected': True,
                    'server_version': db_info
                }
            
        except Error as e:
            return {
                'connected': False,
                'error': str(e)
            }