"""
Code validator for GenCode AI
Validates generated code for quality, security, and standards compliance
"""

import re
import logging
from typing import Dict, Any, List
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class CodeValidator:
    """
    Validates generated code for quality and security
    """
    
    async def validate_code(self, code: Dict[str, str], standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate all generated code files
        
        Args:
            code: Dict of {language: code_content}
            standards: Company coding standards
            
        Returns:
            Dict with validation results
        """
        try:
            validation_results = {}
            all_issues = {
                'critical': [],
                'major': [],
                'minor': [],
                'suggestions': []
            }
            
            # Validate each code file
            for language, code_content in code.items():
                if code_content and code_content.strip():
                    result = await self._validate_language_code(
                        code_content, language, standards
                    )
                    validation_results[language] = result
                    
                    # Aggregate issues
                    for severity in all_issues.keys():
                        all_issues[severity].extend(result.get(severity, []))
            
            # Calculate overall score
            overall_score = self._calculate_overall_score(all_issues)
            
            # Generate summary
            summary = self._generate_validation_summary(all_issues, overall_score)
            
            logger.info(f"Code validation completed. Overall score: {overall_score}")
            
            return {
                'overall_score': overall_score,
                'summary': summary,
                'by_language': validation_results,
                'all_issues': all_issues,
                'recommendations': self._generate_recommendations(all_issues)
            }
            
        except Exception as e:
            logger.error(f"Error validating code: {str(e)}")
            return {
                'overall_score': 0.0,
                'summary': 'Validation failed',
                'error': str(e)
            }
    
    async def _validate_language_code(self, code: str, language: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate code for a specific language
        """
        if language == 'php':
            return self._validate_php_code(code, standards)
        elif language == 'html':
            return self._validate_html_code(code, standards)
        elif language == 'css':
            return self._validate_css_code(code, standards)
        elif language == 'js':
            return self._validate_js_code(code, standards)
        elif language == 'sql':
            return self._validate_sql_code(code, standards)
        else:
            return {'score': 50.0, 'issues': []}
    
    def _validate_php_code(self, code: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate PHP code
        """
        issues = {
            'critical': [],
            'major': [],
            'minor': [],
            'suggestions': []
        }
        
        # Critical security checks
        if 'mysql_query(' in code or 'mysql_connect(' in code:
            issues['critical'].append({
                'issue': 'Using deprecated mysql_* functions',
                'line': self._find_line_number(code, 'mysql_query'),
                'suggestion': 'Use PDO or mysqli with prepared statements'
            })
        
        if '$_GET' in code or '$_POST' in code:
            # Check if input is being used directly without validation
            if not re.search(r'filter_var|htmlspecialchars|strip_tags', code):
                issues['critical'].append({
                    'issue': 'Direct use of user input without validation/sanitization',
                    'suggestion': 'Always validate and sanitize user input'
                })
        
        # SQL injection check
        if re.search(r'\$_[GET|POST].*?SELECT|INSERT|UPDATE|DELETE', code, re.IGNORECASE):
            if 'prepare(' not in code:
                issues['critical'].append({
                    'issue': 'Potential SQL injection vulnerability',
                    'suggestion': 'Use prepared statements for database queries'
                })
        
        # Major issues
        if not code.strip().startswith('<?php'):
            issues['major'].append({
                'issue': 'Missing PHP opening tag',
                'suggestion': 'Start PHP files with <?php'
            })
        
        if 'error_reporting' not in code and 'ini_set' not in code:
            issues['minor'].append({
                'issue': 'No error reporting configuration',
                'suggestion': 'Configure error reporting for development'
            })
        
        # Naming convention checks
        naming_conventions = standards.get('naming_conventions', {})
        if naming_conventions.get('variables') == 'camelCase':
            # Check for snake_case variables (should be camelCase)
            snake_case_vars = re.findall(r'\$[a-z]+_[a-z_]+', code)
            if snake_case_vars:
                issues['minor'].append({
                    'issue': f'Variables not following camelCase convention: {", ".join(snake_case_vars[:3])}',
                    'suggestion': 'Use camelCase for variable names'
                })
        
        # Calculate score
        score = 100.0
        score -= len(issues['critical']) * 25
        score -= len(issues['major']) * 10
        score -= len(issues['minor']) * 5
        score = max(0, score)
        
        return {
            'score': score,
            'critical': issues['critical'],
            'major': issues['major'],
            'minor': issues['minor'],
            'suggestions': issues['suggestions']
        }
    
    def _validate_html_code(self, code: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate HTML code
        """
        issues = {
            'critical': [],
            'major': [],
            'minor': [],
            'suggestions': []
        }
        
        try:
            soup = BeautifulSoup(code, 'html.parser')
            
            # Critical issues
            if not soup.find('!doctype'):
                issues['major'].append({
                    'issue': 'Missing DOCTYPE declaration',
                    'suggestion': 'Add <!DOCTYPE html> at the beginning'
                })
            
            # Check for forms without CSRF protection
            forms = soup.find_all('form')
            for form in forms:
                if form.get('method', '').lower() == 'post':
                    csrf_input = form.find('input', {'name': re.compile(r'csrf|token')})
                    if not csrf_input:
                        issues['major'].append({
                            'issue': 'Form missing CSRF protection',
                            'suggestion': 'Add CSRF token to forms'
                        })
            
            # Accessibility checks
            images = soup.find_all('img')
            for img in images:
                if not img.get('alt'):
                    issues['minor'].append({
                        'issue': 'Image missing alt attribute',
                        'suggestion': 'Add alt attributes to all images for accessibility'
                    })
            
            # Form validation
            inputs = soup.find_all('input')
            for input_elem in inputs:
                input_type = input_elem.get('type', 'text')
                if input_type in ['email', 'url', 'number'] and not input_elem.get('pattern') and not input_elem.get('required'):
                    issues['suggestions'].append({
                        'issue': f'{input_type} input without validation attributes',
                        'suggestion': 'Add validation attributes like required, pattern, etc.'
                    })
            
            # Meta tags check
            if not soup.find('meta', {'name': 'viewport'}):
                issues['minor'].append({
                    'issue': 'Missing viewport meta tag',
                    'suggestion': 'Add viewport meta tag for responsive design'
                })
            
        except Exception as e:
            issues['major'].append({
                'issue': f'HTML parsing error: {str(e)}',
                'suggestion': 'Check HTML syntax'
            })
        
        # Calculate score
        score = 100.0
        score -= len(issues['critical']) * 25
        score -= len(issues['major']) * 10
        score -= len(issues['minor']) * 5
        score = max(0, score)
        
        return {
            'score': score,
            'critical': issues['critical'],
            'major': issues['major'],
            'minor': issues['minor'],
            'suggestions': issues['suggestions']
        }
    
    def _validate_css_code(self, code: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate CSS code
        """
        issues = {
            'critical': [],
            'major': [],
            'minor': [],
            'suggestions': []
        }
        
        # Check for !important overuse
        important_count = code.count('!important')
        if important_count > 3:
            issues['major'].append({
                'issue': f'Overuse of !important ({important_count} instances)',
                'suggestion': 'Avoid !important, use more specific selectors instead'
            })
        
        # Check for responsive design
        if '@media' not in code:
            issues['minor'].append({
                'issue': 'No responsive design media queries',
                'suggestion': 'Add media queries for responsive design'
            })
        
        # Check for vendor prefixes
        if 'transform:' in code and '-webkit-transform:' not in code:
            issues['suggestions'].append({
                'issue': 'Missing vendor prefixes for transform',
                'suggestion': 'Add vendor prefixes for better browser compatibility'
            })
        
        # Check for CSS reset/normalize
        if 'box-sizing' not in code:
            issues['suggestions'].append({
                'issue': 'No CSS reset or normalize',
                'suggestion': 'Consider adding CSS reset for consistent styling'
            })
        
        # Calculate score
        score = 100.0
        score -= len(issues['critical']) * 25
        score -= len(issues['major']) * 10
        score -= len(issues['minor']) * 5
        score = max(0, score)
        
        return {
            'score': score,
            'critical': issues['critical'],
            'major': issues['major'],
            'minor': issues['minor'],
            'suggestions': issues['suggestions']
        }
    
    def _validate_js_code(self, code: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JavaScript code
        """
        issues = {
            'critical': [],
            'major': [],
            'minor': [],
            'suggestions': []
        }
        
        # Check for var usage (should use let/const)
        var_matches = re.findall(r'\bvar\s+\w+', code)
        if var_matches:
            issues['major'].append({
                'issue': f'Using var instead of let/const: {", ".join(var_matches[:3])}',
                'suggestion': 'Use let or const instead of var'
            })
        
        # Check for eval usage
        if 'eval(' in code:
            issues['critical'].append({
                'issue': 'Using eval() function',
                'suggestion': 'Avoid eval() for security reasons'
            })
        
        # Check for error handling
        if 'try' not in code and ('fetch(' in code or 'XMLHttpRequest' in code):
            issues['major'].append({
                'issue': 'AJAX calls without error handling',
                'suggestion': 'Add try-catch blocks for AJAX calls'
            })
        
        # Check for strict mode
        if "'use strict'" not in code and '"use strict"' not in code:
            issues['minor'].append({
                'issue': 'Missing strict mode',
                'suggestion': 'Add "use strict"; at the beginning'
            })
        
        # Check for console.log (should be removed in production)
        console_logs = code.count('console.log')
        if console_logs > 2:
            issues['suggestions'].append({
                'issue': f'Multiple console.log statements ({console_logs})',
                'suggestion': 'Remove console.log statements in production'
            })
        
        # Calculate score
        score = 100.0
        score -= len(issues['critical']) * 25
        score -= len(issues['major']) * 10
        score -= len(issues['minor']) * 5
        score = max(0, score)
        
        return {
            'score': score,
            'critical': issues['critical'],
            'major': issues['major'],
            'minor': issues['minor'],
            'suggestions': issues['suggestions']
        }
    
    def _validate_sql_code(self, code: str, standards: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate SQL code
        """
        issues = {
            'critical': [],
            'major': [],
            'minor': [],
            'suggestions': []
        }
        
        # Check for proper engine
        if 'CREATE TABLE' in code.upper():
            if 'ENGINE=InnoDB' not in code and 'ENGINE = InnoDB' not in code:
                issues['minor'].append({
                    'issue': 'Tables not using InnoDB engine',
                    'suggestion': 'Use ENGINE=InnoDB for better performance and features'
                })
        
        # Check for charset
        if 'CREATE DATABASE' in code.upper() or 'CREATE TABLE' in code.upper():
            if 'utf8mb4' not in code:
                issues['minor'].append({
                    'issue': 'Not using utf8mb4 charset',
                    'suggestion': 'Use utf8mb4 charset for full Unicode support'
                })
        
        # Check for primary keys
        create_table_matches = re.findall(r'CREATE TABLE.*?\((.*?)\);', code, re.DOTALL | re.IGNORECASE)
        for table_def in create_table_matches:
            if 'PRIMARY KEY' not in table_def.upper() and 'AUTO_INCREMENT' not in table_def.upper():
                issues['major'].append({
                    'issue': 'Table without primary key',
                    'suggestion': 'Add primary key to all tables'
                })
        
        # Check for timestamps
        if 'CREATE TABLE' in code.upper():
            if 'created_at' not in code and 'updated_at' not in code:
                issues['suggestions'].append({
                    'issue': 'Tables without timestamp columns',
                    'suggestion': 'Consider adding created_at and updated_at columns'
                })
        
        # Calculate score
        score = 100.0
        score -= len(issues['critical']) * 25
        score -= len(issues['major']) * 10
        score -= len(issues['minor']) * 5
        score = max(0, score)
        
        return {
            'score': score,
            'critical': issues['critical'],
            'major': issues['major'],
            'minor': issues['minor'],
            'suggestions': issues['suggestions']
        }
    
    def _find_line_number(self, code: str, search_term: str) -> int:
        """
        Find line number of a search term in code
        """
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            if search_term in line:
                return i
        return 0
    
    def _calculate_overall_score(self, all_issues: Dict[str, List]) -> float:
        """
        Calculate overall validation score
        """
        total_deductions = 0
        total_deductions += len(all_issues['critical']) * 25
        total_deductions += len(all_issues['major']) * 10
        total_deductions += len(all_issues['minor']) * 5
        
        score = max(0, 100 - total_deductions)
        return round(score, 1)
    
    def _generate_validation_summary(self, all_issues: Dict[str, List], overall_score: float) -> str:
        """
        Generate validation summary
        """
        total_issues = sum(len(issues) for issues in all_issues.values())
        
        if overall_score >= 90:
            status = "Excellent"
        elif overall_score >= 70:
            status = "Good"
        elif overall_score >= 50:
            status = "Fair"
        else:
            status = "Needs Improvement"
        
        summary = f"Overall Score: {overall_score}% ({status})\n"
        summary += f"Total Issues: {total_issues}\n"
        
        if all_issues['critical']:
            summary += f"Critical Issues: {len(all_issues['critical'])}\n"
        if all_issues['major']:
            summary += f"Major Issues: {len(all_issues['major'])}\n"
        if all_issues['minor']:
            summary += f"Minor Issues: {len(all_issues['minor'])}\n"
        
        return summary
    
    def _generate_recommendations(self, all_issues: Dict[str, List]) -> List[str]:
        """
        Generate top recommendations based on issues
        """
        recommendations = []
        
        # Priority recommendations based on critical issues
        critical_issues = all_issues.get('critical', [])
        for issue in critical_issues[:3]:  # Top 3 critical issues
            recommendations.append(f"🔴 CRITICAL: {issue.get('suggestion', 'Fix critical issue')}")
        
        # Major issues
        major_issues = all_issues.get('major', [])
        for issue in major_issues[:2]:  # Top 2 major issues
            recommendations.append(f"🟡 MAJOR: {issue.get('suggestion', 'Fix major issue')}")
        
        # General recommendations
        if not recommendations:
            recommendations.append("✅ Code quality looks good! Consider the minor suggestions for improvement.")
        
        return recommendations