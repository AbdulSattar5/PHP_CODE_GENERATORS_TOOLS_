"""Pattern retrieval prompts"""

PATTERN_RETRIEVAL_PROMPT = """
You are analyzing actual code patterns retrieved from the company codebase.

IMPORTANT: These are REAL code examples from the company's existing projects.

Retrieved Code Patterns:
{retrieved_patterns}

Analyze these ACTUAL code examples and provide:

1. **Database Patterns**: 
   - Table naming conventions (e.g., tbl*, tbl*dtl)
   - Field naming patterns
   - Multi-table relationships

2. **AJAX Patterns**:
   - How AJAX calls are structured
   - URL patterns and endpoints
   - Data handling patterns

3. **Function Patterns**:
   - Common function names and their purposes
   - Parameter patterns
   - Return value patterns

4. **Validation Approaches**:
   - How validation is performed
   - Error handling patterns
   - Response formats

5. **Code Structure**:
   - Include/require patterns
   - Session management
   - Database connection patterns

Focus on extracting SPECIFIC, ACTIONABLE patterns that can be directly applied to new code generation.
Use the actual code examples as reference for naming conventions, structure, and best practices.
"""
