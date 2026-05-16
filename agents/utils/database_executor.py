"""
Multi-database executor for GenCode AI.
Supports MySQL, PostgreSQL, SQLite, and SQL Server.
"""

import logging
import sqlite3

try:
    import mysql.connector as mysql_connector
    from mysql.connector import Error as MySQLError
except ImportError:
    mysql_connector = None

    class MySQLError(Exception):
        """Fallback error type when mysql-connector is unavailable."""


try:
    import psycopg2
    from psycopg2 import Error as PostgresError
except ImportError:
    psycopg2 = None

    class PostgresError(Exception):
        """Fallback error type when psycopg2 is unavailable."""


try:
    import pyodbc
except ImportError:
    pyodbc = None


logger = logging.getLogger(__name__)


class DatabaseExecutor:
    """
    Executes SQL queries on multiple database types.
    """

    OPTIONAL_DRIVERS = {
        'mysql': (lambda: mysql_connector, 'mysql-connector-python', 'MySQL'),
        'postgresql': (lambda: psycopg2, 'psycopg2-binary', 'PostgreSQL'),
        'mssql': (lambda: pyodbc, 'pyodbc', 'SQL Server'),
    }

    def __init__(self, db_type: str, host: str, port: int, database: str,
                 username: str, password: str):
        self.db_type = db_type.lower()
        self.host = host
        self.port = port
        self.database = database
        self.username = username
        self.password = password
        self.connection = None

    def _missing_driver_error(self, package_name: str, display_name: str) -> str:
        return (
            f"{display_name} driver is not installed. "
            f"Install `{package_name}` to use {display_name} connections."
        )

    def _get_optional_driver(self, db_type: str):
        driver_info = self.OPTIONAL_DRIVERS.get(db_type)
        if not driver_info:
            return None, None

        module = driver_info[0]()
        if module is None:
            error = self._missing_driver_error(driver_info[1], driver_info[2])
            logger.warning(error)
            return None, error

        return module, None

    def test_connection(self) -> dict:
        """
        Test database connection.
        """
        try:
            if self.db_type == 'mysql':
                return self._test_mysql()
            if self.db_type == 'postgresql':
                return self._test_postgresql()
            if self.db_type == 'sqlite':
                return self._test_sqlite()
            if self.db_type == 'mssql':
                return self._test_mssql()
            return {'connected': False, 'error': f'Unsupported database type: {self.db_type}'}
        except Exception as e:
            logger.error(f"Connection test error: {str(e)}")
            return {'connected': False, 'error': str(e)}

    def _test_mysql(self) -> dict:
        """Test MySQL connection."""
        driver, driver_error = self._get_optional_driver('mysql')
        if driver_error:
            return {'connected': False, 'error': driver_error}

        try:
            logger.info(f"Testing MySQL connection to {self.host}:{self.port}")
            conn = driver.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                connection_timeout=5
            )
            if conn.is_connected():
                db_info = conn.get_server_info()
                conn.close()
                return {'connected': True, 'server_version': db_info}
            return {'connected': False, 'error': 'Unable to establish MySQL connection'}
        except driver.errors.ProgrammingError as e:
            return {'connected': False, 'error': f'Authentication failed: {str(e)}'}
        except driver.errors.DatabaseError as e:
            return {'connected': False, 'error': f'Database error: {str(e)}'}
        except driver.errors.InterfaceError as e:
            return {'connected': False, 'error': f'Connection error: {str(e)}'}
        except MySQLError as e:
            return {'connected': False, 'error': f'MySQL error: {str(e)}'}
        except Exception as e:
            return {'connected': False, 'error': f'Connection timeout or error: {str(e)}'}

    def _test_postgresql(self) -> dict:
        """Test PostgreSQL connection."""
        driver, driver_error = self._get_optional_driver('postgresql')
        if driver_error:
            return {'connected': False, 'error': driver_error}

        try:
            conn = driver.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                connect_timeout=5
            )
            conn.close()
            return {'connected': True, 'server_version': 'PostgreSQL'}
        except PostgresError as e:
            return {'connected': False, 'error': str(e)}
        except Exception as e:
            return {'connected': False, 'error': f'Connection timeout or error: {str(e)}'}

    def _test_sqlite(self) -> dict:
        """Test SQLite connection."""
        try:
            conn = sqlite3.connect(self.database)
            conn.close()
            return {'connected': True, 'server_version': 'SQLite'}
        except Exception as e:
            return {'connected': False, 'error': str(e)}

    def _test_mssql(self) -> dict:
        """Test SQL Server connection."""
        driver, driver_error = self._get_optional_driver('mssql')
        if driver_error:
            return {'connected': False, 'error': driver_error}

        try:
            conn_str = (
                f'Driver={{ODBC Driver 17 for SQL Server}};'
                f'Server={self.host},{self.port};'
                f'Database={self.database};'
                f'UID={self.username};PWD={self.password}'
            )
            conn = driver.connect(conn_str)
            conn.close()
            return {'connected': True, 'server_version': 'SQL Server'}
        except Exception as e:
            return {'connected': False, 'error': str(e)}

    def execute(self, sql_code: str) -> dict:
        """
        Execute SQL code.
        """
        try:
            if self.db_type == 'mysql':
                return self._execute_mysql(sql_code)
            if self.db_type == 'postgresql':
                return self._execute_postgresql(sql_code)
            if self.db_type == 'sqlite':
                return self._execute_sqlite(sql_code)
            if self.db_type == 'mssql':
                return self._execute_mssql(sql_code)
            return {'success': False, 'error': f'Unsupported database type: {self.db_type}'}
        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _execute_mysql(self, sql_code: str) -> dict:
        """Execute SQL on MySQL."""
        driver, driver_error = self._get_optional_driver('mysql')
        if driver_error:
            return {'success': False, 'error': driver_error}

        connection = None
        cursor = None
        try:
            connection = driver.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                connection_timeout=5
            )

            cursor = connection.cursor()
            statements = self._split_sql_statements(sql_code)
            results = []

            for statement in statements:
                if statement.strip():
                    try:
                        cursor.execute(statement)
                        if statement.strip().upper().startswith('SELECT'):
                            results.append({
                                'query': statement[:100],
                                'rows': cursor.fetchall(),
                                'columns': [desc[0] for desc in cursor.description]
                            })
                        else:
                            results.append({
                                'query': statement[:100],
                                'affected_rows': cursor.rowcount
                            })
                    except MySQLError as e:
                        logger.error(f"MySQL error: {str(e)}")
                        results.append({'query': statement[:100], 'error': str(e)})

            connection.commit()
            return {'success': True, 'statements_executed': len(statements), 'results': results}
        except MySQLError as e:
            logger.error(f"MySQL connection error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"MySQL error: {str(e)}")
            return {'success': False, 'error': f'Connection timeout or error: {str(e)}'}
        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    def _execute_postgresql(self, sql_code: str) -> dict:
        """Execute SQL on PostgreSQL."""
        driver, driver_error = self._get_optional_driver('postgresql')
        if driver_error:
            return {'success': False, 'error': driver_error}

        connection = None
        cursor = None
        try:
            connection = driver.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database,
                connect_timeout=5
            )

            cursor = connection.cursor()
            statements = self._split_sql_statements(sql_code)
            results = []

            for statement in statements:
                if statement.strip():
                    try:
                        cursor.execute(statement)
                        if statement.strip().upper().startswith('SELECT'):
                            results.append({
                                'query': statement[:100],
                                'rows': cursor.fetchall(),
                                'columns': [desc[0] for desc in cursor.description]
                            })
                        else:
                            results.append({
                                'query': statement[:100],
                                'affected_rows': cursor.rowcount
                            })
                    except PostgresError as e:
                        logger.error(f"PostgreSQL error: {str(e)}")
                        results.append({'query': statement[:100], 'error': str(e)})

            connection.commit()
            return {'success': True, 'statements_executed': len(statements), 'results': results}
        except PostgresError as e:
            logger.error(f"PostgreSQL connection error: {str(e)}")
            return {'success': False, 'error': str(e)}
        except Exception as e:
            logger.error(f"PostgreSQL error: {str(e)}")
            return {'success': False, 'error': f'Connection timeout or error: {str(e)}'}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _execute_sqlite(self, sql_code: str) -> dict:
        """Execute SQL on SQLite."""
        connection = None
        cursor = None
        try:
            connection = sqlite3.connect(self.database)
            cursor = connection.cursor()
            statements = self._split_sql_statements(sql_code)
            results = []

            for statement in statements:
                if statement.strip():
                    try:
                        cursor.execute(statement)
                        if statement.strip().upper().startswith('SELECT'):
                            rows = cursor.fetchall()
                            results.append({
                                'query': statement[:100],
                                'rows': rows,
                                'columns': [desc[0] for desc in cursor.description] if cursor.description else []
                            })
                        else:
                            results.append({
                                'query': statement[:100],
                                'affected_rows': cursor.rowcount
                            })
                    except Exception as e:
                        logger.error(f"SQLite error: {str(e)}")
                        results.append({'query': statement[:100], 'error': str(e)})

            connection.commit()
            return {'success': True, 'statements_executed': len(statements), 'results': results}
        except Exception as e:
            logger.error(f"SQLite connection error: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _execute_mssql(self, sql_code: str) -> dict:
        """Execute SQL on SQL Server."""
        driver, driver_error = self._get_optional_driver('mssql')
        if driver_error:
            return {'success': False, 'error': driver_error}

        connection = None
        cursor = None
        try:
            conn_str = (
                f'Driver={{ODBC Driver 17 for SQL Server}};'
                f'Server={self.host},{self.port};'
                f'Database={self.database};'
                f'UID={self.username};PWD={self.password}'
            )
            connection = driver.connect(conn_str)
            cursor = connection.cursor()
            statements = self._split_sql_statements(sql_code)
            results = []

            for statement in statements:
                if statement.strip():
                    try:
                        cursor.execute(statement)
                        if statement.strip().upper().startswith('SELECT'):
                            rows = cursor.fetchall()
                            results.append({
                                'query': statement[:100],
                                'rows': rows,
                                'columns': [desc[0] for desc in cursor.description] if cursor.description else []
                            })
                        else:
                            results.append({
                                'query': statement[:100],
                                'affected_rows': cursor.rowcount
                            })
                    except Exception as e:
                        logger.error(f"SQL Server error: {str(e)}")
                        results.append({'query': statement[:100], 'error': str(e)})

            connection.commit()
            return {'success': True, 'statements_executed': len(statements), 'results': results}
        except Exception as e:
            logger.error(f"SQL Server connection error: {str(e)}")
            return {'success': False, 'error': str(e)}
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def _split_sql_statements(self, sql_code: str) -> list:
        """
        Split SQL code into individual statements.
        """
        statements = []
        current_statement = []

        for line in sql_code.split('\n'):
            if line.strip().startswith('--') or line.strip().startswith('#'):
                continue

            current_statement.append(line)
            if ';' in line:
                statements.append('\n'.join(current_statement))
                current_statement = []

        if current_statement:
            statements.append('\n'.join(current_statement))

        return statements
