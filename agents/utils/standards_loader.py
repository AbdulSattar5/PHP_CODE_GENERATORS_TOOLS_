"""
Standards loader for GenCode AI
Loads and processes company coding standards
"""

import os
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from models.project import CompanyStandards

logger = logging.getLogger(__name__)


class StandardsLoader:
    """
    Loads company coding standards for code generation
    """
    
    async def load_standards(self, user_id: str, standards_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Load coding standards for a user
        
        Args:
            user_id: User ID
            standards_id: Optional specific standards ID
            
        Returns:
            Dict containing standards information
        """
        try:
            # Get active standards from database
            if standards_id:
                try:
                    standards = CompanyStandards.objects.get(
                        id=standards_id,
                        user_id=user_id
                    )
                except CompanyStandards.DoesNotExist:
                    logger.warning(f"Standards {standards_id} not found")
                    return self.get_default_standards()
            else:
                try:
                    standards = CompanyStandards.objects.get(
                        user_id=user_id,
                        is_active=True
                    )
                except CompanyStandards.DoesNotExist:
                    logger.info(f"No active standards found for user {user_id}")
                    return self.get_default_standards()
            
            # Load standards content
            standards_data = {
                'name': standards.name,
                'content': standards.content,
                'php_version': standards.php_version or '8.0+',
                'framework': standards.framework or 'Custom',
                'css_framework': standards.css_framework or 'Custom',
                'db_engine': standards.db_engine or 'InnoDB',
                'charset': 'utf8mb4',
                'created_at': standards.created_at.isoformat(),
                'is_active': standards.is_active
            }
            
            # Parse additional rules from content
            parsed_rules = self._parse_standards_content(standards.content)
            standards_data.update(parsed_rules)
            
            logger.info(f"Loaded standards: {standards.name}")
            
            return standards_data
            
        except Exception as e:
            logger.error(f"Error loading standards: {str(e)}")
            return self.get_default_standards()
    
    def get_default_standards(self) -> Dict[str, Any]:
        """
        Get default coding standards when no custom standards are available
        """
        return {
            'name': 'Default Standards',
            'content': self._get_default_standards_content(),
            'php_version': '8.0+',
            'framework': 'Custom',
            'css_framework': 'Custom',
            'db_engine': 'InnoDB',
            'charset': 'utf8mb4',
            'is_active': True,
            'security_rules': {
                'use_prepared_statements': True,
                'escape_output': True,
                'validate_input': True,
                'use_csrf_protection': True
            },
            'naming_conventions': {
                'variables': 'camelCase',
                'functions': 'camelCase',
                'classes': 'PascalCase',
                'constants': 'UPPER_CASE',
                'tables': 'snake_case'
            },
            'code_style': {
                'indentation': 4,
                'line_length': 120,
                'use_type_hints': True,
                'require_docblocks': True
            }
        }
    
    def _parse_standards_content(self, content: str) -> Dict[str, Any]:
        """
        Parse standards content to extract structured rules
        """
        import re
        
        parsed = {
            'security_rules': {},
            'naming_conventions': {},
            'code_style': {},
            'database_rules': {},
            'frontend_rules': {}
        }
        
        # Security rules
        if 'prepared statement' in content.lower():
            parsed['security_rules']['use_prepared_statements'] = True
        if 'escape' in content.lower() and 'output' in content.lower():
            parsed['security_rules']['escape_output'] = True
        if 'csrf' in content.lower():
            parsed['security_rules']['use_csrf_protection'] = True
        if 'validate' in content.lower() and 'input' in content.lower():
            parsed['security_rules']['validate_input'] = True
        
        # Naming conventions
        camel_case_match = re.search(r'variables?[:\s]+camelCase', content, re.IGNORECASE)
        if camel_case_match:
            parsed['naming_conventions']['variables'] = 'camelCase'
        
        pascal_case_match = re.search(r'classes?[:\s]+PascalCase', content, re.IGNORECASE)
        if pascal_case_match:
            parsed['naming_conventions']['classes'] = 'PascalCase'
        
        upper_case_match = re.search(r'constants?[:\s]+UPPER_CASE', content, re.IGNORECASE)
        if upper_case_match:
            parsed['naming_conventions']['constants'] = 'UPPER_CASE'
        
        # Code style
        indent_match = re.search(r'indent(?:ation)?[:\s]+(\d+)', content, re.IGNORECASE)
        if indent_match:
            parsed['code_style']['indentation'] = int(indent_match.group(1))
        
        # Database rules
        if 'innodb' in content.lower():
            parsed['database_rules']['engine'] = 'InnoDB'
        if 'utf8mb4' in content.lower():
            parsed['database_rules']['charset'] = 'utf8mb4'
        
        # Frontend rules
        if 'responsive' in content.lower():
            parsed['frontend_rules']['responsive_design'] = True
        if 'accessibility' in content.lower() or 'aria' in content.lower():
            parsed['frontend_rules']['accessibility'] = True
        
        return parsed
    
    def _get_default_standards_content(self) -> str:
        """
        Get default standards content as markdown
        """
        return """# Default Coding Standards

## General Guidelines
- Write clean, maintainable code
- Follow SOLID principles
- Use meaningful variable names
- Add comments for complex logic

## PHP Standards
### Version & Configuration
- PHP Version: 8.0+
- Error Reporting: Enabled in development
- Display Errors: Disabled in production

### Database
- Engine: InnoDB
- Charset: utf8mb4
- Use prepared statements for all queries
- Implement proper error handling

### Security
- SQL Injection: Use prepared statements
- XSS: Escape all output
- CSRF: Implement token validation
- Password: Use password_hash()

### Naming Conventions
- Variables: `$camelCase`
- Functions: `camelCase()`
- Classes: `PascalCase`
- Constants: `UPPER_CASE`

## HTML Standards
- Use semantic HTML5 elements
- Include ARIA attributes for accessibility
- Proper nesting and indentation
- Close all tags

## CSS Standards
- Mobile-first responsive design
- Use CSS variables for theming
- Avoid !important
- Consistent naming conventions

## JavaScript Standards
- Version: ES6+
- Use const/let, not var
- Implement error handling
- Validate on both client and server

## Database Standards
- Table names: snake_case
- Primary key: id (INT AUTO_INCREMENT)
- Timestamps: created_at, updated_at
- Soft deletes: deleted_at (if applicable)
"""
    
    async def validate_standards(self, standards_content: str) -> Dict[str, Any]:
        """
        Validate standards content for completeness
        """
        validation_result = {
            'is_valid': True,
            'warnings': [],
            'suggestions': []
        }
        
        required_sections = [
            'php', 'database', 'security', 'html', 'css', 'javascript'
        ]
        
        content_lower = standards_content.lower()
        
        for section in required_sections:
            if section not in content_lower:
                validation_result['warnings'].append(
                    f"Missing {section.upper()} standards section"
                )
        
        # Check for security guidelines
        security_keywords = ['sql injection', 'xss', 'csrf', 'prepared statement']
        missing_security = [kw for kw in security_keywords if kw not in content_lower]
        
        if missing_security:
            validation_result['suggestions'].append(
                f"Consider adding security guidelines for: {', '.join(missing_security)}"
            )
        
        # Check for naming conventions
        if 'naming' not in content_lower and 'convention' not in content_lower:
            validation_result['suggestions'].append(
                "Consider adding naming convention guidelines"
            )
        
        return validation_result