"""Syntax validation for generated code"""

import os
import re
import logging
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class SyntaxValidator:
    """Validates syntax for different programming languages"""

    def _extract_php_blocks(self, code: str) -> str:
        """Extract executable PHP snippets from mixed PHP/HTML output."""
        if not code:
            return ""

        php_blocks = re.findall(r'<\?php[\s\S]*?\?>', code, flags=re.IGNORECASE)
        if php_blocks:
            return '\n'.join(php_blocks)

        # If no explicit close tag exists, treat full payload as PHP fallback.
        return code

    def _strip_strings_and_comments(self, code: str) -> str:
        """Remove strings/comments before lightweight balance checks."""
        if not code:
            return ""

        # Strip block comments first, then line comments.
        sanitized = re.sub(r'/\*[\s\S]*?\*/', '', code)
        sanitized = re.sub(r'//.*?$', '', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'#.*?$', '', sanitized, flags=re.MULTILINE)

        # Remove quoted strings so bracket counting ignores string literals.
        sanitized = re.sub(r'"(?:\\.|[^"\\])*"', '""', sanitized)
        sanitized = re.sub(r"'(?:\\.|[^'\\])*'", "''", sanitized)
        return sanitized

    def _lint_with_php_binary(self, code: str):
        php_path = shutil.which('php')
        if not php_path:
            return None

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as tmp:
                tmp.write(code)
                temp_path = tmp.name

            completed = subprocess.run(
                [php_path, '-l', temp_path],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if completed.returncode == 0:
                return {'valid': True, 'errors': []}

            output = (completed.stderr or completed.stdout or '').strip()
            return {'valid': False, 'errors': [output or 'PHP lint failed.']}
        except Exception as lint_error:
            logger.debug('PHP binary lint unavailable: %s', lint_error)
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    
    def validate_php(self, code: str) -> dict:
        """Basic PHP syntax validation"""
        errors = []
        
        if not code or not isinstance(code, str):
            return {
                'valid': False,
                'is_valid': False,
                'errors': ['No PHP code provided'],
                'warnings': []
            }

        php_lint_result = self._lint_with_php_binary(code)
        if php_lint_result is not None and not php_lint_result['valid']:
            return {
                'valid': False,
                'errors': php_lint_result['errors'],
            }

        php_code_only = self._extract_php_blocks(code)
        php_code_sanitized = self._strip_strings_and_comments(php_code_only)
        
        # Check for opening PHP tag
        if '<?php' not in code:
            errors.append("Missing opening PHP tag")
        
        # Check for balanced braces
        if php_code_sanitized.count('{') != php_code_sanitized.count('}'):
            errors.append("Unbalanced curly braces")
        
        # Check for balanced parentheses
        if php_code_sanitized.count('(') != php_code_sanitized.count(')'):
            errors.append("Unbalanced parentheses")
        
        # Check for semicolons after statements (basic check)
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
                if stripped.endswith('{') or stripped.endswith('}') or stripped.startswith('<?php'):
                    continue
                if not stripped.endswith(';') and not stripped.endswith(':'):
                    if i < len(lines) and not lines[i].strip().startswith('}'):
                        # This is a simplified check
                        pass
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_html(self, code: str) -> dict:
        """Basic HTML syntax validation"""
        errors = []
        
        if not code or not isinstance(code, str):
            return {
                'is_valid': False,
                'errors': ['No HTML code provided'],
                'warnings': []
            }
        
        # Check for DOCTYPE
        if '<!DOCTYPE' not in code.upper():
            errors.append("Missing DOCTYPE declaration")
        
        # Check for html tag
        if '<html' not in code.lower():
            errors.append("Missing <html> tag")
        
        # Check for head and body
        if '<head' not in code.lower():
            errors.append("Missing <head> section")
        
        if '<body' not in code.lower():
            errors.append("Missing <body> section")
        
        # Check for balanced tags (simplified)
        opening_tags = re.findall(r'<(\w+)[^>]*>', code)
        closing_tags = re.findall(r'</(\w+)>', code)
        
        # Self-closing tags
        self_closing = ['img', 'br', 'hr', 'input', 'meta', 'link']
        
        for tag in opening_tags:
            if tag.lower() not in self_closing:
                if opening_tags.count(tag) != closing_tags.count(tag):
                    errors.append(f"Unbalanced <{tag}> tags")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_css(self, code: str) -> dict:
        """Basic CSS syntax validation"""
        errors = []
        
        # Check for balanced braces
        if code.count('{') != code.count('}'):
            errors.append("Unbalanced curly braces in CSS")
        
        # Check for semicolons in declarations (basic)
        lines = code.split('\n')
        in_rule = False
        for line in lines:
            stripped = line.strip()
            if '{' in stripped:
                in_rule = True
            if '}' in stripped:
                in_rule = False
            
            if in_rule and ':' in stripped and not stripped.endswith(';') and not stripped.endswith('{'):
                if stripped and not stripped.startswith('/*'):
                    # Simplified check
                    pass
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
    
    def validate_javascript(self, code: str) -> dict:
        """Basic JavaScript syntax validation"""
        errors = []
        
        # Check for balanced braces
        if code.count('{') != code.count('}'):
            errors.append("Unbalanced curly braces")
        
        # Check for balanced parentheses
        if code.count('(') != code.count(')'):
            errors.append("Unbalanced parentheses")
        
        # Check for balanced brackets
        if code.count('[') != code.count(']'):
            errors.append("Unbalanced square brackets")
        
        return {
            'valid': len(errors) == 0,
            'errors': errors
        }
