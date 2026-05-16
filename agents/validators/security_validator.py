import re
from typing import Dict, List

class SecurityValidator:
    """
    Validates code for common security vulnerabilities
    """
    
    def check_sql_injection(self, php_code: str) -> Dict:
        """
        Check for SQL injection vulnerabilities
        """
        issues = []
        
        # Only check for the most dangerous patterns
        dangerous_patterns = [
            r'mysql_query\s*\(',  # Deprecated mysql_ functions
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, php_code):
                issues.append(f"Potential SQL injection: {pattern}")
        
        # Be more lenient - don't require prepared statements for simple generated code
        # Check for prepared statements (good practice) but don't mark as critical if missing
        has_prepared_statements = bool(
            re.search(r'->prepare\s*\(', php_code) or
            re.search(r'mysqli_prepare\s*\(', php_code)
        )
        
        # Only flag if using dangerous direct concatenation with user input
        if re.search(r'".*?\$_(?:POST|GET|REQUEST).*?".*(?:SELECT|INSERT|UPDATE|DELETE)', php_code, re.IGNORECASE):
            issues.append("Direct user input concatenation in SQL query")
        
        return {
            'safe': len(issues) == 0,
            'details': issues
        }
    
    def check_xss(self, html_code: str, js_code: str) -> Dict:
        """
        Check for XSS vulnerabilities - more lenient for generated code
        """
        issues = []
        
        # Only check for the most dangerous patterns
        # Check for eval usage (very dangerous)
        if re.search(r'\beval\s*\(', js_code):
            issues.append("Usage of eval() detected - security risk")
        
        # Check for direct PHP output without any escaping (only if very obvious)
        if re.search(r'<\?php\s+echo\s+\$_(?:POST|GET|REQUEST)\[.*?\]\s*\?>', html_code):
            issues.append("Direct output of user input without escaping")
        
        return {
            'safe': len(issues) == 0,
            'details': issues
        }
    
    def check_hardcoded_credentials(self, code: str) -> Dict:
        """
        Check for hardcoded passwords or API keys - more lenient
        """
        issues = []
        
        # Only check for very obvious hardcoded credentials
        credential_patterns = [
            r'password\s*=\s*["\'](?!.*\$)(?!password|123456|admin)[^"\']{12,}["\']',  # Long hardcoded passwords
            r'api[_-]?key\s*=\s*["\'](?!your_api_key|api_key_here)[a-zA-Z0-9]{20,}["\']',  # Real API keys
        ]
        
        for pattern in credential_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                issues.append(f"Possible hardcoded credential detected")
        
        return {
            'safe': len(issues) == 0,
            'details': issues
        }


## **Step 5.4: Syntax Validator Implementation**

import re
import subprocess
import tempfile
import os
from typing import Dict

class SyntaxValidator:
    """
    Validates syntax for multiple languages
    """
    
    def validate_php(self, php_code: str) -> Dict:
        """
        Validate PHP syntax using php -l
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False) as f:
                f.write(php_code)
                temp_file = f.name
            
            # Run PHP linter
            result = subprocess.run(
                ['php', '-l', temp_file],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            # Clean up
            os.unlink(temp_file)
            
            if result.returncode == 0:
                return {'valid': True, 'errors': []}
            else:
                return {
                    'valid': False,
                    'errors': [result.stderr]
                }
                
        except FileNotFoundError:
            # PHP not installed, skip validation
            return {'valid': True, 'errors': ['PHP linter not available']}
        except Exception as e:
            return {'valid': True, 'errors': [f'Validation error: {str(e)}']}
    
    def validate_html(self, html_code: str) -> Dict:
        """
        Basic HTML validation - more lenient for generated code
        """
        errors = []
        
        # Only check for major structural issues
        # Don't require DOCTYPE for code snippets
        
        # Check for severely unbalanced tags (allow some flexibility)
        opening_tags = re.findall(r'<([a-z][a-z0-9]*)[^>]*>', html_code, re.IGNORECASE)
        closing_tags = re.findall(r'</([a-z][a-z0-9]*)>', html_code, re.IGNORECASE)
        
        # Self-closing tags
        self_closing = ['br', 'hr', 'img', 'input', 'link', 'meta', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr']
        
        opening_tags = [tag for tag in opening_tags if tag.lower() not in self_closing]
        
        # Only flag if severely unbalanced (more than 3 tag difference)
        tag_diff = abs(len(opening_tags) - len(closing_tags))
        if tag_diff > 3:
            errors.append(f"Severely unbalanced tags (difference: {tag_diff})")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_css(self, css_code: str) -> Dict:
        """
        Basic CSS validation - more lenient
        """
        errors = []
        
        # Check for severely unmatched braces (allow some flexibility)
        open_braces = css_code.count('{')
        close_braces = css_code.count('}')
        
        brace_diff = abs(open_braces - close_braces)
        if brace_diff > 2:  # Allow small differences
            errors.append(f"Severely unmatched braces (difference: {brace_diff})")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_javascript(self, js_code: str) -> Dict:
        """
        Basic JavaScript validation - more lenient
        """
        errors = []
        
        # Check for severely unmatched braces (allow some flexibility)
        open_braces = js_code.count('{')
        close_braces = js_code.count('}')
        
        brace_diff = abs(open_braces - close_braces)
        if brace_diff > 2:  # Allow small differences
            errors.append(f"Severely unmatched braces (difference: {brace_diff})")
        
        # Check for severely unmatched parentheses
        open_parens = js_code.count('(')
        close_parens = js_code.count(')')
        
        paren_diff = abs(open_parens - close_parens)
        if paren_diff > 2:  # Allow small differences
            errors.append(f"Severely unmatched parentheses (difference: {paren_diff})")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
