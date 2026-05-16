"""Validation prompts"""

VALIDATION_PROMPT = """
Perform comprehensive validation of the following generated code bundle.

Complete Code Bundle:
{complete_code_bundle}

Company Standards:
{md_standards}

Validate:
1. Security:
   - SQL injection prevention (prepared statements)
   - XSS protection (input sanitization)
   - CSRF protection
   - No hardcoded credentials
   - Proper error handling without exposing sensitive info

2. Code Quality:
   - Consistent naming conventions
   - Proper indentation and formatting
   - Comments where necessary
   - No dead code
   - DRY principle followed

3. Functionality:
   - All CRUD operations implemented correctly
   - Validation on both client and server
   - Proper error messages
   - Success feedback
   - Edge cases handled

4. Standards Compliance:
   - Follows company coding standards
   - Uses specified PHP version features
   - Matches database conventions
   - CSS/JS best practices

5. Integration:
   - All files properly linked
   - API endpoints match
   - Field names consistent
   - No broken references

Return a JSON object with:
{{
  "overall_score": 85,
  "critical_issues": [],
  "major_issues": [],
  "minor_issues": []
}}
"""
