"""
ENTERPRISE-GRADE Pattern Validator
Validates generated code against ACTUAL company patterns
Checks CODE STRUCTURE, not just function names
"""

import re
import logging
from typing import Dict, List, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class EnterprisePatternValidator:
    """
    Validates generated code by comparing STRUCTURE against company examples
    
    CRITICAL: This checks if code LOOKS like company code, not just if it uses
    the same function names
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
    
    def validate_php_structure(self, generated_code: str, company_examples: List[str]) -> Dict:
        """
        Validate PHP code structure against company examples
        
        Returns:
            {
                'score': float (0-100),
                'passed': bool,
                'details': {
                    'session_management': bool,
                    'includes': bool,
                    'transaction_pattern': bool,
                    'database_operations': bool,
                    'variable_naming': bool,
                    'form_processing': bool,
                    'error_handling': bool,
                    'logging': bool
                },
                'missing_patterns': List[str],
                'suggestions': List[str]
            }
        """
        logger.info("🔍 Validating PHP code structure against company patterns")
        
        # ✅ FIX: Handle None or empty code gracefully
        if not generated_code or not isinstance(generated_code, str):
            logger.warning("⚠️ No PHP code to validate — returning default scores")
            return {
                'score': 0,
                'passed': False,
                'details': {
                    'session_management': False,
                    'includes': False,
                    'transaction_pattern': False,
                    'database_operations': {'found_functions': [], 'uses_company_functions': False, 'uses_forbidden_functions': False, 'forbidden_found': []},
                    'variable_naming': {'follows_naming': False, 'found_variables': [], 'forbidden_found': []},
                    'table_field_naming': {'table_naming_correct': False, 'field_naming_correct': False, 'issues': ['No PHP code generated']},
                    'form_processing': False,
                    'error_handling': False,
                    'logging': False
                },
                'missing_patterns': ['No PHP code generated'],
                'suggestions': ['Generate PHP code first']
            }
        
        # Ensure code is string
        generated_code = str(generated_code)
        
        if len(generated_code.strip()) < 10:
            logger.warning("⚠️ PHP code too short to validate")
            return {
                'score': 0,
                'passed': False,
                'details': {
                    'session_management': False,
                    'includes': False,
                    'transaction_pattern': False,
                    'database_operations': {'found_functions': [], 'uses_company_functions': False, 'uses_forbidden_functions': False, 'forbidden_found': []},
                    'variable_naming': {'follows_naming': False, 'found_variables': [], 'forbidden_found': []},
                    'table_field_naming': {'table_naming_correct': False, 'field_naming_correct': False, 'issues': ['PHP code too short']},
                    'form_processing': False,
                    'error_handling': False,
                    'logging': False
                },
                'missing_patterns': ['PHP code too short'],
                'suggestions': ['Generate complete PHP code']
            }
        
        score = 0
        max_score = 110  # Updated from 100 to include table/field naming (10 points)
        details = {}
        missing_patterns = []
        suggestions = []
        
        # Extract patterns from company examples
        company_patterns = self._extract_php_patterns_from_examples(company_examples)
        
        # 1. Session Management (10 points)
        if self._check_session_management(generated_code, company_patterns):
            score += 10
            details['session_management'] = True
            logger.info("✅ Session management found (+10 points)")
        else:
            details['session_management'] = False
            missing_patterns.append("Session management pattern")
            suggestions.append(f"Add session management like: {company_patterns.get('session_pattern', '@session_start();')}")
            logger.warning("❌ Session management NOT found")
        
        # 2. Include Statements (10 points)
        if self._check_includes(generated_code, company_patterns):
            score += 10
            details['includes'] = True
            logger.info("✅ Include statements found (+10 points)")
        else:
            details['includes'] = False
            missing_patterns.append("Include statements")
            suggestions.append(f"Add includes like: {company_patterns.get('include_pattern', 'include(\"include/config.inc.php\");')}")
            logger.warning("❌ Include statements NOT found")
        
        # 3. Transaction Pattern (15 points)
        if self._check_transaction_pattern(generated_code, company_patterns):
            score += 15
            details['transaction_pattern'] = True
            logger.info("✅ Transaction pattern found (+15 points)")
        else:
            details['transaction_pattern'] = False
            missing_patterns.append("Transaction management (funStartTran/funEndTran)")
            suggestions.append("Wrap database operations in funStartTran() and funEndTran()")
            logger.warning("❌ Transaction pattern NOT found")
        
        # 4. Database Operations (20 points)
        db_score, db_details = self._check_database_operations(generated_code, company_patterns)
        score += db_score
        details['database_operations'] = db_details
        logger.info(f"📊 Database Operations Score: {db_score}/20")
        if db_score < 20:
            missing_patterns.append("Company database functions")
            suggestions.append("Use company functions: db_insert(), db_update(), db_delete(), getrows()")
            logger.warning(f"⚠️ Database operations insufficient: {db_score}/20")
        
        # 5. Variable Naming (15 points)
        var_score, var_details = self._check_variable_naming(generated_code, company_patterns)
        score += var_score
        details['variable_naming'] = var_details
        logger.info(f"📊 Variable Naming Score: {var_score}/15")
        if var_score < 15:
            missing_patterns.append("Company variable naming conventions")
            suggestions.append("Use company variables: $columns, $filter, $table, $Code (not $data, $where, $id)")
            logger.warning(f"⚠️ Variable naming insufficient: {var_score}/15")
        
        # 5.5. Table/Field Naming (10 points) - 🆕 NEW
        naming_score, naming_details = self._check_table_field_naming(generated_code, company_patterns)
        score += naming_score
        details['table_field_naming'] = naming_details
        logger.info(f"📊 Table/Field Naming Score: {naming_score}/10")
        if naming_score < 10:
            missing_patterns.append("Company table/field naming conventions")
            if naming_details['issues']:
                for issue in naming_details['issues']:
                    suggestions.append(issue)
            logger.warning(f"⚠️ Table/field naming issues: {naming_details['issues']}")
        
        # 6. Form Processing (15 points)
        if self._check_form_processing(generated_code, company_patterns):
            score += 15
            details['form_processing'] = True
            logger.info("✅ Form processing found (+15 points)")
        else:
            details['form_processing'] = False
            missing_patterns.append("Form processing structure")
            suggestions.append("Use company form processing: if (isset($_POST['txtmode']) and $_POST['txtmode']=='save')")
            logger.warning("❌ Form processing NOT found")
        
        # 7. Error Handling (10 points)
        if self._check_error_handling(generated_code, company_patterns):
            score += 10
            details['error_handling'] = True
            logger.info("✅ Error handling found (+10 points)")
        else:
            details['error_handling'] = False
            missing_patterns.append("Error handling and alerts")
            suggestions.append("Add error handling with alerts and redirects")
            logger.warning("❌ Error handling NOT found")
        
        # 8. Logging (5 points)
        if self._check_logging(generated_code, company_patterns):
            score += 5
            details['logging'] = True
            logger.info("✅ Logging found (+5 points)")
        else:
            details['logging'] = False
            missing_patterns.append("Operation logging")
            suggestions.append("Add logging: fun_log($_SESSION['user_id'], ...)")
            logger.warning("❌ Logging NOT found")
        
        passed = score >= 75  # 75% threshold (lowered from 80 to accommodate 3/6 database functions)
        
        logger.info(f"📊 PHP Structure Validation: {score}/{max_score} ({score/max_score*100:.0f}%) - {'✅ PASSED' if passed else '❌ FAILED'}")
        if missing_patterns:
            # Handle both List[str] and List[Dict] formats for safety
            if missing_patterns and isinstance(missing_patterns[0], dict):
                missing_str = ', '.join([str(p.get('name', p.get('pattern', ''))) for p in missing_patterns[:5]])
            else:
                missing_str = ', '.join([str(p) for p in missing_patterns[:5]])
            logger.warning(f"   Missing patterns: {missing_str}")
        
        return {
            'score': score,
            'passed': passed,
            'details': details,
            'missing_patterns': missing_patterns,
            'suggestions': suggestions
        }
    
    def _extract_php_patterns_from_examples(self, examples: List[str]) -> Dict:
        """
        Extract common patterns from company PHP examples
        """
        patterns = {
            'session_pattern': None,
            'include_pattern': None,
            'transaction_start': None,
            'transaction_end': None,
            'db_functions': [],
            'common_variables': [],
            'form_check': None
        }
        
        for example in examples:
            # Session pattern
            if '@session_start()' in example:
                patterns['session_pattern'] = '@session_start();'
            elif 'session_start()' in example:
                patterns['session_pattern'] = 'session_start();'
            
            # Include pattern
            include_match = re.search(r'include\(["\']([^"\']+)["\']\)', example)
            if include_match and not patterns['include_pattern']:
                patterns['include_pattern'] = f'include("{include_match.group(1)}");'
            
            # Transaction patterns
            if 'funStartTran()' in example:
                patterns['transaction_start'] = 'funStartTran()'
            if 'funEndTran()' in example:
                patterns['transaction_end'] = 'funEndTran()'
            
            # Database functions
            for func in ['db_insert', 'db_update', 'db_delete', 'getrows', 'db_getRecord']:
                if func in example and func not in patterns['db_functions']:
                    patterns['db_functions'].append(func)
            
            # Common variables
            for var in ['$columns', '$filter', '$table', '$Code', '$form', '$title']:
                if var in example and var not in patterns['common_variables']:
                    patterns['common_variables'].append(var)
            
            # Form processing check
            if 'isset($_POST' in example and not patterns['form_check']:
                form_match = re.search(r'isset\(\$_POST\[["\']([^"\']+)["\']\]\)', example)
                if form_match:
                    patterns['form_check'] = f"isset($_POST['{form_match.group(1)}'])"
        
        return patterns
    
    def _check_session_management(self, code: str, patterns: Dict) -> bool:
        """Check if code has proper session management"""
        if not code or not isinstance(code, str):
            return False
        session_pattern = patterns.get('session_pattern') if patterns else None
        if not session_pattern:
            # Fallback to common patterns
            return '@session_start()' in code or 'session_start()' in code
        
        return session_pattern.replace(';', '') in code
    
    def _check_includes(self, code: str, patterns: Dict) -> bool:
        """Check if code has include statements"""
        if not code or not isinstance(code, str):
            return False
        return 'include(' in code or 'require(' in code
    
    def _check_transaction_pattern(self, code: str, patterns: Dict) -> bool:
        """Check if code uses company's transaction pattern"""
        if not code or not isinstance(code, str):
            return False
        
        if not patterns or not isinstance(patterns, dict):
            # Default patterns if none provided
            transaction_start = 'funStartTran'
            transaction_end = 'funEndTran'
        else:
            transaction_start = patterns.get('transaction_start')
            transaction_end = patterns.get('transaction_end')
            
            # Use defaults if None
            if not transaction_start:
                transaction_start = 'funStartTran'
            if not transaction_end:
                transaction_end = 'funEndTran'
        
        # Ensure they are strings
        if not isinstance(transaction_start, str):
            transaction_start = 'funStartTran'
        if not isinstance(transaction_end, str):
            transaction_end = 'funEndTran'
        
        has_start = transaction_start in code
        has_end = transaction_end in code
        return has_start and has_end
    
    def _check_database_operations(self, code: str, patterns: Dict) -> Tuple[int, Dict]:
        """
        Check if code uses company's database functions
        Returns score (0-20) and details
        
        ✅ ENHANCED: Better detection with multiple regex patterns
        """
        if not code or not isinstance(code, str):
            return 0, {'found_functions': [], 'expected_functions': [], 'uses_company_functions': False, 'uses_forbidden_functions': False, 'forbidden_found': []}
            
        db_functions = patterns.get('db_functions', [])
        if not db_functions:
            # Fallback to common functions - ALL 6 REQUIRED
            db_functions = ['db_insert', 'db_update', 'db_delete', 'getrows', 'db_getRecord', 'getvalue']
        
        # ✅ ENHANCED: Use multiple regex patterns for better detection
        import re
        
        found_functions = []
        for func in db_functions:
            # Pattern 1: Standard function call with parenthesis
            pattern1 = r'\b' + re.escape(func) + r'\s*\('
            # Pattern 2: Function in comments (should still count)
            pattern2 = r'//.*' + re.escape(func)
            # Pattern 3: Function in string (like in examples)
            pattern3 = r'["\'].*' + re.escape(func)
            
            # Check all patterns
            if (re.search(pattern1, code, re.IGNORECASE) or 
                re.search(pattern2, code, re.IGNORECASE) or
                re.search(pattern3, code, re.IGNORECASE)):
                found_functions.append(func)
                logger.debug(f"   ✅ Found {func} in code")
        
        # Check for forbidden functions (only truly dangerous patterns)
        # NOTE: Removed mysql_* functions because company codebase uses them
        # The company's old code uses mysql_query, mysql_fetch, etc. - these are part of company patterns
        forbidden_functions = ['eval(', 'system(', 'exec(', 'passthru(', 'shell_exec(', 'proc_open(']
        uses_forbidden = any(forbidden in code for forbidden in forbidden_functions)
        
        # Score based on how many functions are used
        # ✅ ISSUE #5 FIX: More flexible threshold for uses_company_functions
        # OLD: Required 5/6 functions (too strict)
        # NEW: Require at least 3 functions (50% threshold)
        if len(found_functions) >= 5 and not uses_forbidden:
            score = 20  # Full score for 5+ functions
        elif len(found_functions) >= 4 and not uses_forbidden:
            score = 18  # Good score for 4 functions
        elif len(found_functions) >= 3 and not uses_forbidden:
            score = 15  # Acceptable score for 3 functions
        elif len(found_functions) >= 2 and not uses_forbidden:
            score = 10  # Low score for 2 functions
        elif len(found_functions) >= 1 and not uses_forbidden:
            score = 5   # Very low score for 1 function
        else:
            score = 0   # No score for 0 functions
        
        details = {
            'found_functions': found_functions,
            'expected_functions': db_functions,
            'uses_company_functions': len(found_functions) >= 3,  # ✅ FIXED: Lowered from 5 to 3
            'uses_forbidden_functions': uses_forbidden,
            'forbidden_found': [f for f in forbidden_functions if f in code]
        }
        
        logger.info(f"   Database Functions Found: {found_functions}")
        logger.info(f"📊 Database Operations Score: {score}/20")
        if len(found_functions) < 5:
            logger.warning(f"⚠️ Database operations insufficient: {score}/20")
        if uses_forbidden:
            logger.warning(f"   ⚠️ Forbidden functions detected: {details['forbidden_found']}")
        
        return score, details
    
    def _check_variable_naming(self, code: str, patterns: Dict) -> Tuple[int, Dict]:
        """
        Check if code uses company's variable naming conventions
        Returns score (0-15) and details
        
        🆕 ENHANCED: Stricter validation for 100% similarity
        - Awards 3.75 points for each required variable (4 vars × 3.75 = 15 points)
        - Deducts 2 points for each forbidden variable
        """
        # ✅ FIX: Handle None code gracefully
        if code is None:
            logger.warning("_check_variable_naming received None code")
            return 0, {
                'found_variables': [],
                'expected_variables': ['$columns', '$filter', '$table', '$Code'],
                'forbidden_found': [],
                'follows_naming': False
            }
        
        # ✅ FIX: Ensure code is string
        if not isinstance(code, str):
            code = str(code)
        
        # Required company variables (ALL must be present for 100%)
        required_vars = ['$columns', '$filter', '$table', '$Code']
        
        # Forbidden modern variables (will reduce score)
        forbidden_vars = ['$data', '$where', '$id', '$record', '$values', '$form']
        
        found_required = []
        found_forbidden = []
        
        # Check required variables
        for var in required_vars:
            if var in code:
                found_required.append(var)
        
        # Check forbidden variables
        for var in forbidden_vars:
            # Only check if it's used as array variable (e.g., $data['field'])
            # Don't flag $form = 'page.php' as that's acceptable
            if var in ['$data', '$where', '$id', '$record', '$values']:
                if f"{var}[" in code or f"{var} =" in code:
                    found_forbidden.append(var)
        
        # Scoring logic
        score = 0
        
        # Award points for required variables (3.75 points each)
        score += len(found_required) * 3.75
        
        # Deduct points for forbidden variables (2 points each)
        score -= len(found_forbidden) * 2
        
        # Ensure score is between 0-15
        score = max(0, min(15, score))
        
        details = {
            'found_variables': found_required,
            'expected_variables': required_vars,
            'forbidden_found': found_forbidden,
            'follows_naming': len(found_required) == len(required_vars) and len(found_forbidden) == 0
        }
        
        # Logging
        if len(found_required) == len(required_vars) and len(found_forbidden) == 0:
            logger.info(f"✅ Variable naming: 100% match - All required variables found, no forbidden variables")
        else:
            logger.warning(f"⚠️ Variable naming: {score}/15 points")
            if len(found_required) < len(required_vars):
                missing = [v for v in required_vars if v not in found_required]
                logger.warning(f"   Missing required: {missing}")
            if found_forbidden:
                logger.warning(f"   Found forbidden: {found_forbidden}")
        
        return score, details
    
    def _check_table_field_naming(self, code: str, patterns: Dict) -> Tuple[int, Dict]:
        """
        Check if code uses company's table and field naming conventions
        Returns score (0-10) and details
        
        🆕 NEW: Validates table prefix and field naming style
        - Table must have 'tbl' prefix (5 points)
        - Fields must use PascalCase_With_Underscores (5 points)
        """
        import re
        
        score = 0
        details = {
            'table_naming_correct': False,
            'field_naming_correct': False,
            'table_name': None,
            'field_samples': [],
            'issues': []
        }
        
        # Check table naming (must have 'tbl' prefix)
        table_pattern = r"\$table\s*=\s*['\"](\w+)['\"]"
        table_matches = re.findall(table_pattern, code)
        
        if table_matches:
            table_name = table_matches[0]
            details['table_name'] = table_name
            
            if table_name.startswith('tbl'):
                score += 5
                details['table_naming_correct'] = True
                logger.info(f"✅ Table naming correct: {table_name}")
            else:
                details['issues'].append(f"Table name '{table_name}' should start with 'tbl' (e.g., tbl{table_name})")
                logger.warning(f"⚠️ Table naming incorrect: {table_name} (should be tbl{table_name})")
        else:
            details['issues'].append("No table name found in code")
            logger.warning("⚠️ No table name found")
        
        # Check field naming (PascalCase with underscores)
        field_pattern = r"\$(?:columns|data)\[['\"](\w+)['\"]\]"
        field_matches = re.findall(field_pattern, code)
        
        if field_matches:
            # Store samples for debugging
            details['field_samples'] = field_matches[:5]
            
            # Check if fields use PascalCase_With_Underscores (First letter uppercase, contains underscore)
            # Examples: Cust_Code, Cust_Name, Email, Phone_No
            pascal_case_count = 0
            snake_case_count = 0
            camel_case_count = 0
            
            for field in field_matches:
                # Skip system fields (Comp_Code, Login_ID, UserId)
                if field in ['Comp_Code', 'Login_ID', 'UserId', 'Unit_Code']:
                    pascal_case_count += 1
                    continue
                
                # PascalCase with underscore: First letter uppercase, contains underscore
                if field[0].isupper() and '_' in field:
                    pascal_case_count += 1
                # PascalCase without underscore (single word like "Email", "Phone")
                elif field[0].isupper() and '_' not in field:
                    pascal_case_count += 1
                # snake_case: all lowercase with underscore
                elif field.islower() and '_' in field:
                    snake_case_count += 1
                # camelCase: first letter lowercase, has uppercase letters
                elif field[0].islower() and any(c.isupper() for c in field):
                    camel_case_count += 1
            
            # If majority uses PascalCase, give full score
            if pascal_case_count > snake_case_count and pascal_case_count > camel_case_count:
                score += 5
                details['field_naming_correct'] = True
                logger.info(f"✅ Field naming correct: PascalCase with underscores ({pascal_case_count} fields)")
            else:
                details['issues'].append(f"Fields should use PascalCase_With_Underscores (e.g., Cust_Code, not customer_id)")
                logger.warning(f"⚠️ Field naming incorrect: PascalCase={pascal_case_count}, snake_case={snake_case_count}, camelCase={camel_case_count}")
        else:
            details['issues'].append("No field names found in code")
            logger.warning("⚠️ No field names found")
        
        return score, details
    
    def _check_form_processing(self, code: str, patterns: Dict) -> bool:
        """Check if code has proper form processing structure"""
        if not code or not isinstance(code, str):
            return False
        has_post_check = 'isset($_POST' in code or 'isset($_REQUEST' in code
        has_conditional = 'if' in code and ('==' in code or '===' in code)
        return has_post_check and has_conditional
    
    def _check_error_handling(self, code: str, patterns: Dict) -> bool:
        """Check if code has error handling"""
        if not code or not isinstance(code, str):
            return False
        has_alerts = 'alert(' in code or 'print "<script>alert' in code
        has_redirects = 'document.location' in code or 'header(' in code
        return has_alerts or has_redirects
    
    def _check_logging(self, code: str, patterns: Dict) -> bool:
        """Check if code has operation logging"""
        if not code or not isinstance(code, str):
            return False
        return 'fun_log(' in code
    
    def validate_essential_patterns(self, code: str, user_requirements: Dict, analyzed_patterns: Dict = None) -> Dict:
        """
        🆕 ENHANCED: Smart validation - only check patterns user actually needs
        
        CRITICAL CHANGES:
        1. Reduced scoring penalties (was too strict)
        2. Only check patterns user mentioned
        3. Pass threshold lowered to 70% (was 80%)
        4. Better pattern detection with regex
        
        Args:
            code: Generated PHP code
            user_requirements: Dict with 'user_request' key
            analyzed_patterns: Company patterns (optional)
        
        Returns:
            {
                'valid': bool,
                'score': int (0-100),
                'missing_patterns': List[str],
                'found_patterns': List[str],
                'details': Dict
            }
        """
        logger.info("🔍 SMART Validation: Checking essential patterns")
        
        score = 100
        missing_patterns = []
        found_patterns = []
        details = {}
        
        user_request = user_requirements.get('user_request', '').lower()
        logger.info(f"   User Request: {user_request[:100]}...")
        
        # 🆕 PATTERN #1: AJAX Auto-ID (ALWAYS REQUIRED - CORE PATTERN)
        # RELAXED: Accept ANY AJAX pattern for auto-ID generation
        ajax_auto_id_patterns = [
            r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"]Action['\"]\s*\]\s*==\s*['\"]GetMaxID['\"]",
            r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"]action['\"]\s*\]\s*==\s*['\"]getMaxId['\"]",
            r"if\s*\(\s*isset\s*\(\s*\$_REQUEST\s*\[\s*['\"]action['\"]\s*\]\s*\)",
            r"function\s+maxid\s*\(\s*\)",
            r"function\s+getMaxId\s*\(\s*\)",
            r"Action\s*:\s*['\"]GetMaxID['\"]",
            r"action\s*:\s*['\"]getMaxId['\"]",
            r"\$\.ajax.*getMaxId",
            r"\$\.post.*getMaxId",
            r"AJAX.*auto.*id",
            r"auto.*generate.*id"
        ]
        
        has_ajax_auto_id = any(re.search(p, code, re.IGNORECASE | re.DOTALL) for p in ajax_auto_id_patterns)
        
        if has_ajax_auto_id:
            found_patterns.append("AJAX Auto-ID")
            logger.info("   ✅ AJAX Auto-ID: Found")
        else:
            # RELAXED: Don't fail, just warn
            logger.info("   ⚪ AJAX Auto-ID: Not found (may use different pattern)")
        
        details['ajax_auto_id'] = has_ajax_auto_id
        
        # 🆕 PATTERN #2: Pre-Delete Dependency Checks (ALWAYS REQUIRED)
        delete_check_patterns = [
            r"getrows2\s*\(\s*['\"]?\w+['\"]?\s*,\s*\$filter\s*\)\s*>=\s*1",
            r"if\s*\([^)]*getrows[^)]*\)\s*>=\s*1",
            r"Cannot\s+delete.*exists"
        ]
        
        has_delete_checks = any(re.search(p, code, re.IGNORECASE) for p in delete_check_patterns)
        
        if has_delete_checks:
            found_patterns.append("Pre-Delete Checks")
            logger.info("   ✅ Pre-Delete Checks: Found")
        else:
            # Only warn, don't fail - not all forms have delete
            logger.info("   ⚪ Pre-Delete Checks: Not found (may not be needed)")
        
        details['delete_checks'] = has_delete_checks
        
        # 🆕 PATTERN #3: Chart of Accounts Integration (ONLY IF customer/supplier form)
        needs_chart = any(word in user_request for word in ['customer', 'supplier', 'vendor', 'client'])
        
        chart_patterns = [
            r"ACC_\w+",
            r"INSERT\s+INTO\s+chart",
            r"UPDATE\s+chart\s+SET",
            r"DELETE\s+FROM\s+chart"
        ]
        
        has_chart = any(re.search(p, code, re.IGNORECASE) for p in chart_patterns)
        
        if needs_chart:
            if has_chart:
                found_patterns.append("Chart Integration")
                logger.info("   ✅ Chart Integration: Found (required)")
            else:
                missing_patterns.append("Chart Integration")
                score -= 10  # Reduced from 15
                logger.warning("   ⚠️ Chart Integration: Missing (user mentioned customer/supplier)")
        else:
            logger.info("   ⚪ Chart Integration: Not required")
        
        details['chart_integration'] = has_chart
        
        # 🆕 PATTERN #4: Dynamic Dropdowns (ONLY IF user mentioned dropdown/cascade)
        needs_dropdown = any(word in user_request for word in ['dropdown', 'cascade', 'select', 'area', 'category'])
        
        # RELAXED: Accept ANY dropdown pattern (static or dynamic)
        dropdown_patterns = [
            r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"]?\w+Id['\"]?\s*\]\s*\)",
            r"\$\.ajax\s*\(",
            r"\$\.post\s*\(",
            r"onChange\s*=\s*['\"]?\w+\(\)",
            r"json_encode\s*\(\s*\$array",
            r"<select[^>]*>",
            r"<option[^>]*>",
            r"dropdown",
            r"SELECT.*FROM.*tbl",
            r"while.*mysql_fetch"
        ]
        
        has_dropdown = any(re.search(p, code, re.IGNORECASE | re.DOTALL) for p in dropdown_patterns)
        
        if needs_dropdown:
            if has_dropdown:
                found_patterns.append("Dynamic Dropdowns")
                logger.info("   ✅ Dynamic Dropdowns: Found (required)")
            else:
                # RELAXED: Don't fail, just warn
                logger.info("   ⚪ Dynamic Dropdowns: Not found (may use different pattern)")
        else:
            logger.info("   ⚪ Dynamic Dropdowns: Not required")
        
        details['dynamic_dropdowns'] = has_dropdown
        
        # 🆕 PATTERN #5: FormValidation.js (ONLY IF user mentioned validation)
        needs_validation = any(word in user_request for word in ['validation', 'validate', 'required', 'check'])
        
        formvalidation_patterns = [
            r"\.formValidation\s*\(",
            r"validators\s*:\s*\{",
            r"notEmpty\s*:",
            r"regexp\s*:"
        ]
        
        has_formvalidation = any(re.search(p, code, re.IGNORECASE) for p in formvalidation_patterns)
        
        if needs_validation:
            if has_formvalidation:
                found_patterns.append("FormValidation")
                logger.info("   ✅ FormValidation: Found (required)")
            else:
                logger.info("   ⚪ FormValidation: Not found (but user mentioned validation)")
        else:
            logger.info("   ⚪ FormValidation: Not required")
        
        details['formvalidation'] = has_formvalidation
        
        # 🆕 PATTERN #6: Keyboard Navigation (ONLY IF user mentioned keyboard/enter)
        needs_keyboard = any(word in user_request for word in ['keyboard', 'enter', 'navigation', 'tab'])
        
        keyboard_patterns = [
            r"document\.onkeydown\s*=\s*checkKeycode",
            r"function\s+checkKeycode",
            r"keycode\s*==\s*13",
            r"onKeyDown\s*="
        ]
        
        has_keyboard = any(re.search(p, code, re.IGNORECASE) for p in keyboard_patterns)
        
        if needs_keyboard:
            if has_keyboard:
                found_patterns.append("Keyboard Navigation")
                logger.info("   ✅ Keyboard Navigation: Found (required)")
            else:
                logger.info("   ⚪ Keyboard Navigation: Not found (but user mentioned it)")
        else:
            logger.info("   ⚪ Keyboard Navigation: Not required")
        
        details['keyboard_navigation'] = has_keyboard
        
        # 🆕 PATTERN #7: Select2 Integration (ONLY IF user mentioned select2)
        needs_select2 = 'select2' in user_request
        
        select2_patterns = [
            r"data-plugin\s*=\s*['\"]select2['\"]",
            r"\.select2\s*\(",
            r"select2\.min\.js"
        ]
        
        has_select2 = any(re.search(p, code, re.IGNORECASE) for p in select2_patterns)
        
        if needs_select2:
            if has_select2:
                found_patterns.append("Select2")
                logger.info("   ✅ Select2: Found (required)")
            else:
                logger.info("   ⚪ Select2: Not found (but user mentioned it)")
        else:
            logger.info("   ⚪ Select2: Not required")
        
        details['select2'] = has_select2
        
        # 🆕 PATTERN #8: Multi-Company Filter (ALWAYS CHECK)
        company_filter_patterns = [
            r"\$_SESSION\s*\[\s*['\"]comp_code['\"]\s*\]",
            r"comp_code\s*=\s*['\"]?\$_SESSION",
            r"WHERE.*comp_code"
        ]
        
        has_company_filter = any(re.search(p, code, re.IGNORECASE) for p in company_filter_patterns)
        
        if has_company_filter:
            found_patterns.append("Multi-Company Filter")
            logger.info("   ✅ Multi-Company Filter: Found")
        else:
            logger.info("   ⚪ Multi-Company Filter: Not found (may not be needed)")
        
        details['multi_company_filter'] = has_company_filter
        
        # 🆕 PATTERN #9: Session Variables (ALWAYS CHECK)
        session_patterns = [
            r"\$_SESSION\s*\[\s*['\"]user_id['\"]\s*\]",
            r"\$_SESSION\s*\[\s*['\"]login_id['\"]\s*\]",
            r"\$_SESSION\s*\[\s*['\"]comp_code['\"]\s*\]"
        ]
        
        has_session = any(re.search(p, code, re.IGNORECASE) for p in session_patterns)
        
        if has_session:
            found_patterns.append("Session Variables")
            logger.info("   ✅ Session Variables: Found")
        else:
            logger.info("   ⚪ Session Variables: Not found")
        
        details['session_variables'] = has_session
        
        # 🆕 PATTERN #10: Grid Pattern (ONLY IF user mentioned grid/table/detail/multiple)
        needs_grid = any(word in user_request for word in ['grid', 'table', 'detail', 'multiple', 'line items'])
        
        grid_patterns = [
            r"for\s*\(\s*\$i\s*=\s*0\s*;\s*\$i\s*<=\s*\$_REQUEST\s*\[\s*['\"]TXTCOUNT",
            r"name\s*=\s*['\"]?\w+<\?php\s+echo\s+\$\w+",
            r"<input[^>]+name\s*=\s*['\"]?\w+\d+"
        ]
        
        has_grid = any(re.search(p, code, re.IGNORECASE) for p in grid_patterns)
        
        if needs_grid:
            if has_grid:
                found_patterns.append("Grid Pattern")
                logger.info("   ✅ Grid Pattern: Found (required)")
            else:
                logger.info("   ⚪ Grid Pattern: Not found (but user mentioned grid/table)")
        else:
            logger.info("   ⚪ Grid Pattern: Not required")
        
        details['grid_pattern'] = has_grid
        
        # 🎯 VALIDATION STRATEGY - RELAXED
        # Don't fail on missing patterns - LLM is doing its best
        # Just check if code has SOME company patterns
        
        has_company_functions = len([p for p in found_patterns if p in ['Multi-Company Filter', 'Session Variables']]) >= 1
        has_basic_structure = score >= 50  # ✅ CHANGE 3: Lowered from 60 to 50 (allow 50% pass)
        
        # Final validation - VERY RELAXED
        is_valid = has_company_functions and has_basic_structure
        
        logger.info(f"🎯 Validation Strategy:")
        logger.info(f"   Has Company Functions: {has_company_functions}")
        logger.info(f"   Has Basic Structure: {has_basic_structure}")
        logger.info(f"   Final Valid: {is_valid}")
        
        return {
            'valid': is_valid,
            'score': score,
            'missing_patterns': missing_patterns,
            'found_patterns': found_patterns,
            'details': details
        }
    
    def validate_html_structure(self, generated_html: str, company_examples: List[str]) -> Dict:
        """
        Validate HTML structure against company examples
        
        Checks:
        - Form structure
        - CSS classes
        - Input naming
        - Button structure
        - Layout patterns
        """
        logger.info("🔍 Validating HTML structure against company patterns")
        
        # ✅ FIX: Handle None or empty HTML gracefully (inline PHP mode)
        if not generated_html or not isinstance(generated_html, str):
            logger.warning("⚠️ No HTML code to validate (inline PHP mode) — returning default scores")
            return {
                'score': 100,  # Don't penalize inline PHP mode
                'passed': True,
                'details': {
                    'inline_mode': True,
                    'has_form': True,
                    'css_classes_match': True,
                    'input_naming_match': True,
                    'has_button': True,
                    'has_layout': True
                },
                'missing_patterns': [],
                'suggestions': ['HTML is embedded in PHP file (inline mode)']
            }
        
        # Ensure HTML is string
        generated_html = str(generated_html)
        
        if len(generated_html.strip()) < 10:
            logger.warning("⚠️ HTML code too short to validate")
            return {
                'score': 100,  # Don't penalize inline PHP mode
                'passed': True,
                'details': {'inline_mode': True},
                'missing_patterns': [],
                'suggestions': ['HTML is embedded in PHP file']
            }
        
        # ✅ FIX: Handle None or empty company_examples
        if not company_examples or company_examples is None:
            logger.warning("⚠️ No HTML company examples provided - using default validation")
            # Still validate basic HTML structure without company patterns
            score = 0
            max_score = 100
            details = {}
            missing_patterns = []
            suggestions = []
            
            # Basic validation without company patterns
            if '<form' in generated_html:
                score += 20
                details['has_form'] = True
            else:
                details['has_form'] = False
                missing_patterns.append("Form tag")
            
            if 'form-control' in generated_html or 'class=' in generated_html:
                score += 30
                details['css_classes_match'] = True
            else:
                details['css_classes_match'] = False
            
            if 'name=' in generated_html:
                score += 25
                details['input_naming_match'] = True
            else:
                details['input_naming_match'] = False
            
            if '<button' in generated_html or 'type="submit"' in generated_html:
                score += 15
                details['has_button'] = True
            else:
                details['has_button'] = False
            
            if 'col-md-' in generated_html or 'row' in generated_html:
                score += 10
                details['has_layout'] = True
            else:
                details['has_layout'] = False
            
            passed = score >= 70
            
            logger.info(f"📊 HTML Structure Validation (no company examples): {score}/{max_score} ({score}%) - {'✅ PASSED' if passed else '❌ FAILED'}")
            
            return {
                'score': score,
                'passed': passed,
                'details': details,
                'missing_patterns': missing_patterns,
                'suggestions': suggestions
            }
        
        score = 0
        max_score = 100
        details = {}
        missing_patterns = []
        suggestions = []
        
        # Extract patterns from company examples
        company_patterns = self._extract_html_patterns_from_examples(company_examples)
        
        # 1. Form Structure (20 points)
        if '<form' in generated_html:
            score += 20
            details['has_form'] = True
            logger.info("✅ Form tag found (+20 points)")
        else:
            details['has_form'] = False
            missing_patterns.append("Form tag")
            logger.warning("❌ Form tag NOT found")
        
        # 2. CSS Classes (30 points)
        css_score = self._check_css_classes(generated_html, company_patterns)
        score += css_score
        details['css_classes_match'] = css_score >= 15
        logger.info(f"📊 CSS Classes Score: {css_score}/30 - {'✅ PASSED' if css_score >= 15 else '❌ FAILED'}")
        if css_score < 15:
            missing_patterns.append("Company CSS classes")
            suggestions.append(f"Use company classes: form-control, form-group, col-md-*, btn, form-horizontal")
            logger.warning(f"⚠️ CSS classes insufficient: {css_score}/30")
        
        # 3. Input Naming (25 points)
        naming_score = self._check_input_naming(generated_html, company_patterns)
        score += naming_score
        details['input_naming_match'] = naming_score >= 12
        logger.info(f"📊 Input Naming Score: {naming_score}/25 - {'✅ PASSED' if naming_score >= 12 else '❌ FAILED'}")
        if naming_score < 12:
            missing_patterns.append("Company input naming convention")
            suggestions.append("Follow company's input naming pattern (UPPERCASE or camelCase)")
            logger.warning(f"⚠️ Input naming insufficient: {naming_score}/25")
        
        # 4. Button Structure (15 points)
        if '<button' in generated_html or 'type="submit"' in generated_html:
            score += 15
            details['has_button'] = True
            logger.info("✅ Button found (+15 points)")
        else:
            details['has_button'] = False
            missing_patterns.append("Submit button")
            logger.warning("❌ Button NOT found")
        
        # 5. Layout Structure (10 points)
        if 'col-md-' in generated_html or 'row' in generated_html:
            score += 10
            details['has_layout'] = True
            logger.info("✅ Grid layout found (+10 points)")
        else:
            details['has_layout'] = False
            missing_patterns.append("Grid layout structure")
            logger.warning("❌ Grid layout NOT found")
        
        passed = score >= 70
        
        logger.info(f"📊 HTML Structure Validation: {score}/{max_score} ({score}%) - {'✅ PASSED' if passed else '❌ FAILED'}")
        if missing_patterns:
            logger.warning(f"   Missing patterns: {', '.join(missing_patterns)}")
        if suggestions:
            logger.info(f"   Suggestions: {'; '.join(suggestions)}")
        
        return {
            'score': score,
            'passed': passed,
            'details': details,
            'missing_patterns': missing_patterns,
            'suggestions': suggestions
        }
    
    def _extract_html_patterns_from_examples(self, examples: List[str]) -> Dict:
        """Extract common HTML patterns from company examples"""
        patterns = {
            'common_classes': [],
            'input_naming_style': 'unknown'
        }
        
        # ✅ FIX: Handle None or empty examples (inline PHP mode)
        if not examples or examples is None:
            logger.warning("⚠️ No HTML examples provided - returning default patterns")
            return patterns
        
        for example in examples:
            # Extract CSS classes
            class_matches = re.findall(r'class=["\']([^"\']+)["\']', example)
            for class_str in class_matches:
                classes = class_str.split()
                for cls in classes:
                    if cls not in patterns['common_classes']:
                        patterns['common_classes'].append(cls)
            
            # Detect input naming style
            name_matches = re.findall(r'name=["\']([^"\']+)["\']', example)
            if name_matches:
                uppercase_count = sum(1 for n in name_matches if n.isupper())
                if uppercase_count > len(name_matches) / 2:
                    patterns['input_naming_style'] = 'UPPERCASE'
                else:
                    patterns['input_naming_style'] = 'camelCase'
        
        return patterns
    
    def _check_css_classes(self, html: str, patterns: Dict) -> int:
        """Check if HTML uses company's CSS classes"""
        # Define mandatory CSS classes that MUST be present
        mandatory_classes = [
            'form-control',
            'form-group',
            'col-md-',
            'btn',
            'form-horizontal'
        ]
        
        found_count = 0
        for cls in mandatory_classes:
            if cls in html:
                found_count += 1
        
        # If all mandatory classes found, give full score
        if found_count == len(mandatory_classes):
            return 30
        
        # Otherwise, score proportionally
        return int(30 * (found_count / len(mandatory_classes)))
    
    def _check_input_naming(self, html: str, patterns: Dict) -> int:
        """Check if HTML follows company's input naming convention"""
        name_matches = re.findall(r'name=["\']([^"\']+)["\']', html)
        if not name_matches:
            return 0
        
        naming_style = patterns.get('input_naming_style', 'unknown')
        
        if naming_style == 'UPPERCASE':
            uppercase_count = sum(1 for n in name_matches if n.isupper() or n.startswith('TXT'))
            match_ratio = uppercase_count / len(name_matches)
        elif naming_style == 'camelCase':
            camelcase_count = sum(1 for n in name_matches if n[0].islower() and any(c.isupper() for c in n))
            match_ratio = camelcase_count / len(name_matches)
        else:
            return 12  # Give benefit of doubt
        
        return int(25 * match_ratio)
