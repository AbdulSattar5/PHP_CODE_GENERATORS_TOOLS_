"""Code integration prompts"""

CODE_LINKING_PROMPT = """
Review and integrate the following generated code files to ensure proper linking.

SQL Schema:
{sql_code}

PHP Backend:
{php_code}

HTML Form:
{html_code}

CSS Styling:
{css_code}

JavaScript:
{js_code}

Feature Name: {feature_name}

Verify and correct:
1. API endpoint URLs match between HTML/JS and PHP
2. Form field names match database columns
3. Form IDs match JavaScript selectors
4. CSS class names match HTML elements
5. File paths are correct in HTML (CSS/JS links)
6. Database table name is consistent
7. All required fields are validated in both client and server
8. CORS headers are properly set in PHP
9. JSON response format is consistent

Return corrected code if any issues found, or confirm all links are correct.
"""
