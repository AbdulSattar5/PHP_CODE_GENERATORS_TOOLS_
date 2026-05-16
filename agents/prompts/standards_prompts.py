"""Standards loading prompts"""

MD_STANDARDS_PROMPT = """
Process the following company coding standards document and extract CRITICAL patterns that MUST be followed.

Standards Document:
{md_file_content}

Technical Requirements:
- PHP Version: {php_version}
- Database Connection: {db_connection_method}
- Framework: {framework}
- CSS Framework: {css_framework}
- JavaScript Libraries: {js_libraries}

CRITICAL TASK:
Extract and list ALL the specific function names, patterns, and conventions that MUST be used in code generation.

Focus on:
1. **Exact Function Names** - List all custom functions (e.g., funsession(), funStartTran(), vchMaxNo1(), etc.)
2. **Naming Conventions** - How variables, fields, and functions should be named
3. **Required Patterns** - Patterns that ALWAYS must be used together (e.g., session + transaction + logging)
4. **Code Structure** - The exact order and structure of code blocks
5. **Database Patterns** - Specific database functions and methods
6. **Validation Patterns** - Custom validation functions
7. **Grid/Dynamic Patterns** - Array declarations and grid management functions
8. **Amount Calculation Patterns** - Specific calculation functions and their sequence
9. **Security Patterns** - Required security checks and functions
10. **Response Patterns** - How to format responses and redirects

Provide a structured summary that emphasizes:
- MUST USE these exact function names
- MUST FOLLOW these exact patterns
- MUST INCLUDE these required elements
- DO NOT use standard/generic approaches

This summary will be used to enforce strict adherence to company standards in code generation.
"""
