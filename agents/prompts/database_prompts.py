"""Database generation prompts"""

DATABASE_GENERATION_PROMPT = """
Generate MySQL database schema based on the following requirements.

Intent:
{intent_json}

Similar Database Patterns:
{db_patterns}

Company Standards:
{db_standards}

Requirements:
- Table Name: {table_name}
- Engine: {engine_type}
- Naming Convention: {naming_convention}
- Date: {current_date}

Generate:
1. CREATE TABLE statement with all fields
2. Appropriate data types and constraints
3. Primary key and indexes
4. Foreign key relationships (if any)
5. Default values where appropriate
6. Timestamps (created_at, updated_at)
7. Sample INSERT statements for testing

Ensure the schema follows best practices and company standards.
"""
