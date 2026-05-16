"""
Database connection prompts for GenCode AI
Handles SQL generation for different database types
"""


def get_database_specific_sql_prompt(db_type: str, user_request: str, schema_info: str = "") -> str:
    """
    Get database-specific SQL generation prompt
    
    Args:
        db_type: Database type (mysql, postgresql, sqlite, mssql)
        user_request: User's request for SQL generation
        schema_info: Optional schema information
        
    Returns:
        Formatted prompt for SQL generation
    """
    
    base_prompt = f"""Generate SQL code for the following request:
{user_request}

Database Type: {db_type.upper()}
"""
    
    if schema_info:
        base_prompt += f"\nSchema Information:\n{schema_info}\n"
    
    # Database-specific instructions
    db_specific = {
        'mysql': """
Database-Specific Guidelines for MySQL:
- Use backticks for identifiers: `table_name`, `column_name`
- Use AUTO_INCREMENT for auto-incrementing primary keys
- Use CHARSET utf8mb4 COLLATE utf8mb4_unicode_ci for better Unicode support
- Use InnoDB engine for transactions and foreign keys
- Use DATETIME for timestamps, not TIMESTAMP
- Use VARCHAR(255) for string fields unless longer is needed
- Use INT for integers, BIGINT for large numbers
- Use DECIMAL(10,2) for monetary values
- Use TEXT for large text content
- Use JSON data type for complex nested data
- Use ENUM for fixed set of values
- Use INDEX for frequently queried columns
- Use FOREIGN KEY constraints for referential integrity
- Use CHECK constraints for data validation
- Use DEFAULT values for common cases
- Use NOT NULL for required fields
- Use UNIQUE constraints for unique fields
- Use COMMENT for documentation
""",
        'postgresql': """
Database-Specific Guidelines for PostgreSQL:
- Use double quotes for identifiers: "table_name", "column_name"
- Use SERIAL or BIGSERIAL for auto-incrementing primary keys
- Use SERIAL GENERATED ALWAYS AS IDENTITY for newer versions
- Use TEXT for strings (no length limit needed)
- Use VARCHAR(n) only when length restriction is needed
- Use SMALLINT, INTEGER, BIGINT for integers
- Use NUMERIC(precision, scale) for monetary values
- Use JSONB for JSON data (better than JSON)
- Use ARRAY types for collections
- Use ENUM types for fixed set of values
- Use UUID type for unique identifiers
- Use TIMESTAMP WITH TIME ZONE for timestamps
- Use BOOLEAN for true/false values
- Use CREATE INDEX for frequently queried columns
- Use FOREIGN KEY constraints with ON DELETE CASCADE/SET NULL
- Use CHECK constraints for data validation
- Use DEFAULT values for common cases
- Use NOT NULL for required fields
- Use UNIQUE constraints for unique fields
- Use COMMENT ON for documentation
- Use SCHEMA for organizing tables
""",
        'sqlite': """
Database-Specific Guidelines for SQLite:
- SQLite is simpler and has fewer data types
- Use INTEGER for integers (including auto-increment with AUTOINCREMENT)
- Use REAL for floating-point numbers
- Use TEXT for strings
- Use BLOB for binary data
- Use NUMERIC for decimal numbers
- Use BOOLEAN (stored as 0/1)
- Use PRIMARY KEY AUTOINCREMENT for auto-incrementing IDs
- Use FOREIGN KEY constraints (enable with PRAGMA foreign_keys = ON)
- Use CHECK constraints for data validation
- Use DEFAULT values for common cases
- Use NOT NULL for required fields
- Use UNIQUE constraints for unique fields
- Use CREATE INDEX for frequently queried columns
- SQLite doesn't support ALTER TABLE ADD COLUMN with NOT NULL (use DEFAULT)
- SQLite doesn't support DROP COLUMN (use CREATE TABLE AS SELECT)
- SQLite doesn't support RENAME COLUMN (use CREATE TABLE AS SELECT)
- Use PRAGMA statements for optimization
""",
        'mssql': """
Database-Specific Guidelines for SQL Server:
- Use square brackets for identifiers: [table_name], [column_name]
- Use IDENTITY(1,1) for auto-incrementing primary keys
- Use NVARCHAR for Unicode strings
- Use VARCHAR for ASCII strings
- Use INT for integers, BIGINT for large numbers
- Use SMALLINT for small integers
- Use DECIMAL(precision, scale) for monetary values
- Use DATETIME2 for timestamps (better precision than DATETIME)
- Use BIT for boolean values
- Use JSON data type for JSON data
- Use XML data type for XML data
- Use UNIQUEIDENTIFIER for GUIDs
- Use CREATE INDEX for frequently queried columns
- Use PRIMARY KEY constraints
- Use FOREIGN KEY constraints with ON DELETE CASCADE/SET NULL
- Use CHECK constraints for data validation
- Use DEFAULT values for common cases
- Use NOT NULL for required fields
- Use UNIQUE constraints for unique fields
- Use CONSTRAINT names for all constraints
- Use sp_executesql for parameterized queries
- Use BEGIN TRANSACTION / COMMIT / ROLLBACK for transactions
"""
    }
    
    base_prompt += db_specific.get(db_type.lower(), "")
    
    base_prompt += """
Requirements:
1. Generate valid SQL for the specified database type
2. Include proper data types for the database
3. Include primary keys and foreign keys
4. Include indexes for performance
5. Include constraints for data integrity
6. Add comments explaining complex queries
7. Use proper naming conventions (snake_case for tables/columns)
8. Ensure the SQL is production-ready
9. Include error handling where applicable
10. Optimize for the specific database engine

Generate the SQL code now:
"""
    
    return base_prompt


def get_php_database_connection_code(db_type: str, host: str, port: int, 
                                     database: str, username: str) -> str:
    """
    Generate PHP code for database connection
    
    Args:
        db_type: Database type
        host: Database host
        port: Database port
        database: Database name
        username: Database username
        
    Returns:
        PHP connection code
    """
    
    connection_code = {
        'mysql': f"""<?php
// MySQL Database Connection
$host = '{host}';
$port = {port};
$database = '{database}';
$username = '{username}';
$password = ''; // Set your password here

try {{
    $connection = new mysqli($host, $username, $password, $database, $port);
    
    // Check connection
    if ($connection->connect_error) {{
        die("Connection failed: " . $connection->connect_error);
    }}
    
    // Set charset to utf8mb4
    $connection->set_charset("utf8mb4");
    
    echo "Connected successfully to MySQL database";
}} catch (Exception $e) {{
    die("Connection error: " . $e->getMessage());
}}
?>""",
        
        'postgresql': f"""<?php
// PostgreSQL Database Connection
$host = '{host}';
$port = {port};
$database = '{database}';
$username = '{username}';
$password = ''; // Set your password here

try {{
    $connection_string = "host=$host port=$port dbname=$database user=$username password=$password";
    $connection = pg_connect($connection_string);
    
    if (!$connection) {{
        die("Connection failed: " . pg_last_error());
    }}
    
    echo "Connected successfully to PostgreSQL database";
}} catch (Exception $e) {{
    die("Connection error: " . $e->getMessage());
}}
?>""",
        
        'sqlite': f"""<?php
// SQLite Database Connection
$database = '{database}';

try {{
    $connection = new PDO("sqlite:$database");
    $connection->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    
    // Enable foreign keys
    $connection->exec("PRAGMA foreign_keys = ON");
    
    echo "Connected successfully to SQLite database";
}} catch (PDOException $e) {{
    die("Connection error: " . $e->getMessage());
}}
?>""",
        
        'mssql': f"""<?php
// SQL Server Database Connection
$host = '{host}';
$port = {port};
$database = '{database}';
$username = '{username}';
$password = ''; // Set your password here

try {{
    $connection_string = "Driver={{ODBC Driver 17 for SQL Server}};Server=$host,$port;Database=$database;UID=$username;PWD=$password";
    $connection = odbc_connect($connection_string, $username, $password);
    
    if (!$connection) {{
        die("Connection failed: " . odbc_error());
    }}
    
    echo "Connected successfully to SQL Server database";
}} catch (Exception $e) {{
    die("Connection error: " . $e->getMessage());
}}
?>"""
    }
    
    return connection_code.get(db_type.lower(), "")


def get_database_selection_prompt() -> str:
    """
    Get prompt for database selection in code generation
    """
    return """
When generating code that involves database operations:
1. Check if a specific database type was selected
2. Generate SQL syntax specific to that database
3. Generate PHP connection code for that database
4. Include database-specific optimizations
5. Use database-specific data types
6. Follow database-specific naming conventions
7. Include database-specific error handling
8. Provide database-specific deployment instructions
"""
