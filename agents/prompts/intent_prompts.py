"""Intent analysis prompts"""

INTENT_ANALYSIS_PROMPT = """
Analyze the following user request and extract structured intent for code generation.

User Request: {user_request}

Extract:
1. Feature type (form, CRUD, report, dashboard, etc.)
2. Form/module title
3. All required fields with:
   - Field name (snake_case)
   - Display label
   - Database type (VARCHAR, INT, TEXT, DATE, etc.)
   - Field length
   - HTML input type (text, email, number, date, select, textarea, etc.)
   - Validation rules
   - Whether required
4. Database schema:
   - Table name (snake_case)
   - Primary key
   - Indexes
   - Relationships
5. Required CRUD operations (create, read, update, delete)
6. UI layout preference

{format_instructions}
"""
