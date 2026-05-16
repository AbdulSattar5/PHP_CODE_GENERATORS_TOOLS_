"""
Dynamic Pattern Extractor - Hybrid Approach
Extracts patterns from analyzed_patterns with intelligent fallbacks
"""
import logging
import os
from typing import Dict, List, Set, Optional, Any

from agents.utils.runtime_config import get_csv_setting, get_int_setting

logger = logging.getLogger(__name__)


class DynamicPatternExtractor:
    """
    Extracts company-specific patterns dynamically from analyzed codebase
    Falls back to generic patterns when specific patterns not available
    
    ✅ HYBRID APPROACH:
    1. Try to extract from analyzed_patterns (company-specific)
    2. Fall back to generic patterns (universal)
    3. Combine both for maximum coverage
    """
    
    def __init__(self, analyzed_patterns: Optional[Dict] = None):
        self.analyzed_patterns = analyzed_patterns or {}
        self.php_patterns = self.analyzed_patterns.get('php', {})
        self.html_patterns = self.analyzed_patterns.get('html', {})
        self.js_patterns = self.analyzed_patterns.get('js', {})
        self.allow_generic_augmentation = str(
            os.getenv('CODEGEN_ALLOW_GENERIC_AUGMENTATION', 'false')
        ).strip().lower() in {'1', 'true', 'yes', 'on'}
        self._generic_fallback_events: List[Dict[str, str]] = []
        self._extraction_diagnostics: Dict[str, Dict[str, Any]] = {
            'database_functions': {
                'real_detected_count': 0,
                'synthetic_appended_count': 0,
                'final_total_count': 0,
                'mandatory_target_count': 0,
            }
        }

    def _register_generic_fallback(self, category: str, reason: str):
        event = {'category': category, 'reason': reason}
        self._generic_fallback_events.append(event)
        logger.warning(f"⚠️ Generic fallback used [{category}]: {reason}")

    def get_fallback_diagnostics(self) -> Dict[str, object]:
        return {
            'generic_fallback_events': list(self._generic_fallback_events),
            'generic_fallback_count': len(self._generic_fallback_events),
            'allow_generic_augmentation': self.allow_generic_augmentation
        }

    def get_extraction_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        return {
            key: dict(value)
            for key, value in self._extraction_diagnostics.items()
        }

    def _get_list_setting(self, setting_name: str, env_name: str, default: List[str]) -> List[str]:
        return get_csv_setting(setting_name, env_name, default=default)
    
    def get_database_functions(self) -> List[str]:
        """
        Extract database operation functions
        Priority: analyzed_patterns → generic fallback
        
        ✅ FIX #3: ALWAYS ensure minimum 8 DB functions with hard fallback
        Search for CALLS not just DEFINITIONS
        """
        functions = set()

        def _normalize_function_name(raw_name) -> str:
            token = str(raw_name or '').strip()
            if not token:
                return ''
            import re
            match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', token)
            if match:
                token = match.group(1)
            token = re.sub(r'[^A-Za-z0-9_]', '', token)
            return token
        
        # FIX #3: All known company DB function names
        known_db_functions = [
            'db_insert', 'db_update', 'db_delete', 'db_getRecord',
            'getrows', 'getvalue', 'funStartTran', 'funEndTran',
            'db_select', 'db_execute', 'getMaxID', 'db_query'
        ]
        
        # 1. Extract from analyzed patterns - search for USAGE (calls) not just definitions
        if self.php_patterns.get('functions'):
            all_funcs = self.php_patterns['functions']
            # Filter for database operations
            db_keywords = ['insert', 'update', 'delete', 'select', 'query', 'exec', 'getrecord', 'getrows', 'getvalue', 'tran']
            for func in all_funcs:
                raw_name = func
                if isinstance(func, dict):
                    raw_name = (
                        func.get('name')
                        or func.get('function')
                        or func.get('signature')
                        or func.get('type')
                        or ''
                    )
                func_name = _normalize_function_name(raw_name)
                if not func_name:
                    continue
                func_lower = func_name.lower()
                if any(kw in func_lower for kw in db_keywords):
                    functions.add(func_name)
            
            if functions:
                logger.info(f"✅ Extracted {len(functions)} database functions from analyzed patterns")
        
        # FIX #3: Search for function CALLS in code content (not just function names)
        if self.analyzed_patterns:
            import re
            for func_name in known_db_functions:
                # Match function calls: func_name( or func_name (
                call_pattern = rf'\b{re.escape(func_name)}\s*\('
                
                # Search in all code sections
                found_in_any = False
                for section_key in ['php', 'html', 'js']:
                    section = self.analyzed_patterns.get(section_key, {})
                    if isinstance(section, dict):
                        # Check in various subsections
                        for subsection_key in ['functions', 'code', 'content', 'patterns']:
                            subsection = section.get(subsection_key, [])
                            if isinstance(subsection, list):
                                for item in subsection:
                                    if isinstance(item, dict):
                                        code_text = (
                                            item.get('content', '')
                                            or item.get('code', '')
                                            or item.get('body', '')
                                            or item.get('signature', '')
                                            or item.get('name', '')
                                            or item.get('function', '')
                                            or item.get('type', '')
                                        )
                                    else:
                                        code_text = str(item)
                                    
                                    if re.search(call_pattern, code_text):
                                        found_in_any = True
                                        break
                            elif isinstance(subsection, str):
                                if re.search(call_pattern, subsection):
                                    found_in_any = True
                                    break
                        
                        if found_in_any:
                            break
                
                if found_in_any:
                    functions.add(func_name)
        
        logger.info(f"📊 Extracted {len(functions)} database functions from analyzed patterns")
        
        # ✅ FIX #3: APPEND missing mandatory ones (don't lose what we found)
        mandatory_functions = [
            'db_insert', 'db_update', 'db_delete', 'db_getRecord', 
            'getrows', 'getvalue', 'funStartTran', 'funEndTran'
        ]
        real_detected_count = len(functions)
        MIN_DB_FUNCTIONS = 8
        synthetic_appended_count = 0
        if len(functions) < MIN_DB_FUNCTIONS:
            logger.warning(f"⚠️ Only {len(functions)} DB functions detected (minimum {MIN_DB_FUNCTIONS} required)")
            logger.warning(f"⚠️ FIX #3: APPENDING missing mandatory functions (not replacing)")
            
            # APPEND missing mandatory ones
            missing_count = 0
            normalized_lookup = {func_name.lower() for func_name in functions}
            for func in mandatory_functions:
                if func.lower() not in normalized_lookup:
                    functions.add(func)
                    normalized_lookup.add(func.lower())
                    missing_count += 1
            synthetic_appended_count = missing_count
            self._register_generic_fallback(
                'database_functions',
                f'Only {len(functions) - missing_count} DB functions detected, APPENDED {missing_count} mandatory functions'
            )
            logger.info(f"✅ FIX #3: After APPEND: {len(functions)} database functions available")
        else:
            # Even if we have enough, still add mandatory functions to ensure they're present
            functions.update(mandatory_functions)
            logger.info(f"✅ Ensured mandatory functions present: {len(functions)} total")
        
        # 3. Additional generic patterns for fallback (if augmentation enabled)
        if self.allow_generic_augmentation:
            generic_functions = self._get_list_setting(
                'CODEGEN_GENERIC_DB_FUNCTIONS',
                'CODEGEN_GENERIC_DB_FUNCTIONS',
                default=[
                    'db_select', 'db_query',
                    'insert', 'update', 'delete', 'select', 'query',
                    'insertRecord', 'updateRecord', 'deleteRecord', 'getRecord',
                    'save', 'fetch', 'execute', 'run'
                ]
            )
            functions.update(generic_functions[:5])

        self._extraction_diagnostics['database_functions'] = {
            'real_detected_count': int(real_detected_count),
            'synthetic_appended_count': int(synthetic_appended_count),
            'final_total_count': int(len(functions)),
            'mandatory_target_count': int(len(mandatory_functions)),
        }

        return list(functions)
    
    def get_helper_functions(self) -> List[str]:
        """Extract helper/utility functions"""
        functions = set()
        
        # 1. Extract from analyzed patterns
        if self.php_patterns.get('functions'):
            all_funcs = self.php_patterns['functions']
            helper_keywords = ['get', 'fetch', 'find', 'check', 'validate', 'format']
            
            for func in all_funcs:
                func_name = func.get('name', func) if isinstance(func, dict) else str(func)
                func_lower = func_name.lower()
                if any(kw in func_lower for kw in helper_keywords):
                    functions.add(func_name)
        
        # 2. Fallback
        generic_helpers = self._get_list_setting(
            'CODEGEN_GENERIC_HELPER_FUNCTIONS',
            'CODEGEN_GENERIC_HELPER_FUNCTIONS',
            default=[
                'getrows', 'getvalue', 'getdata', 'fetchall', 'fetchone',
                'getValue', 'getData', 'getRows', 'checkExists'
            ]
        )
        
        if not functions:
            self._register_generic_fallback(
                'helper_functions',
                'No helper functions detected in analyzed patterns'
            )
            functions.update(generic_helpers)
        elif self.allow_generic_augmentation:
            functions.update(generic_helpers[:3])
        
        return list(functions)

    
    def get_transaction_functions(self) -> Dict[str, str]:
        """Extract transaction management functions"""
        transactions = {}
        
        # 1. Extract from analyzed patterns
        if self.php_patterns.get('transaction_management'):
            tm = self.php_patterns['transaction_management']
            transactions['start'] = tm.get('start', '')
            transactions['end'] = tm.get('end', '')
            transactions['commit'] = tm.get('commit', '')
            transactions['rollback'] = tm.get('rollback', '')
            
            if transactions['start']:
                logger.info(f"✅ Found transaction patterns: {transactions['start']}, {transactions['end']}")
                return transactions
        
        # 2. Fallback (configurable)
        fallback_start = self._get_list_setting(
            'CODEGEN_GENERIC_TRANSACTION_START',
            'CODEGEN_GENERIC_TRANSACTION_START',
            default=['funStartTran', 'beginTransaction', 'startTransaction', 'begin']
        )
        fallback_end = self._get_list_setting(
            'CODEGEN_GENERIC_TRANSACTION_END',
            'CODEGEN_GENERIC_TRANSACTION_END',
            default=['funEndTran', 'commitTransaction', 'endTransaction', 'commit']
        )
        fallback_commit = self._get_list_setting(
            'CODEGEN_GENERIC_TRANSACTION_COMMIT',
            'CODEGEN_GENERIC_TRANSACTION_COMMIT',
            default=['commit', 'commitTran']
        )
        fallback_rollback = self._get_list_setting(
            'CODEGEN_GENERIC_TRANSACTION_ROLLBACK',
            'CODEGEN_GENERIC_TRANSACTION_ROLLBACK',
            default=['rollback', 'rollbackTran']
        )
        return {
            'start': '|'.join(fallback_start),
            'end': '|'.join(fallback_end),
            'commit': '|'.join(fallback_commit),
            'rollback': '|'.join(fallback_rollback)
        }
    
    def get_ajax_functions(self) -> List[str]:
        """Extract AJAX function patterns"""
        ajax_funcs = set()
        
        # 1. Extract from analyzed patterns
        if self.php_patterns.get('ajax_functions'):
            for ajax in self.php_patterns['ajax_functions']:
                ajax_name = ajax.get('type', ajax) if isinstance(ajax, dict) else str(ajax)
                ajax_funcs.add(ajax_name)
            
            if ajax_funcs:
                logger.info(f"✅ Extracted {len(ajax_funcs)} AJAX functions from analyzed patterns")
        
        # 2. Fallback
        generic_ajax = self._get_list_setting(
            'CODEGEN_GENERIC_AJAX_FUNCTIONS',
            'CODEGEN_GENERIC_AJAX_FUNCTIONS',
            default=[
                '$.ajax', '$.post', '$.get', '$.getJSON',
                'fetch', 'XMLHttpRequest', 'ajaxSetup',
                'GetMaxID', 'getMaxId', 'getNextCode', 'autoIncrement'
            ]
        )
        
        if not ajax_funcs:
            self._register_generic_fallback(
                'ajax_functions',
                'No company AJAX patterns detected in analyzed patterns'
            )
            ajax_funcs.update(generic_ajax)
        elif self.allow_generic_augmentation:
            ajax_funcs.update(generic_ajax[:5])
        
        return list(ajax_funcs)
    
    def get_table_prefix(self) -> str:
        """Detect table naming prefix dynamically"""
        # 1. Extract from analyzed patterns
        if self.php_patterns.get('table_names'):
            tables = self.php_patterns['table_names']
            
            # Count prefix patterns
            prefix_count = {}
            for table in tables[:20]:  # Check first 20 tables
                table_name = table.get('name', table) if isinstance(table, dict) else str(table)
                table_lower = table_name.lower()
                
                # Check common prefixes
                for prefix in ['tbl', 'tb_', 't_', 'table_']:
                    if table_lower.startswith(prefix):
                        prefix_count[prefix] = prefix_count.get(prefix, 0) + 1
            
            # Return most common prefix
            if prefix_count:
                dominant_prefix = max(prefix_count, key=prefix_count.get)
                logger.info(f"✅ Detected table prefix: '{dominant_prefix}' ({prefix_count[dominant_prefix]} tables)")
                return dominant_prefix
        
        # 2. Fallback
        fallback_prefix = str(os.getenv('CODEGEN_TABLE_PREFIX_FALLBACK', 'tbl')).strip() or 'tbl'
        logger.info(f"⚠️ No table prefix detected, using default '{fallback_prefix}'")
        return fallback_prefix

    
    def get_field_naming_convention(self) -> Dict[str, any]:
        """Detect field naming convention"""
        # 1. Extract from analyzed patterns
        if self.php_patterns.get('naming_conventions'):
            conventions = self.php_patterns['naming_conventions']
            return {
                'style': conventions.get('dominant_style', 'PascalCase'),
                'uppercase_percent': conventions.get('uppercase_percent', 0),
                'lowercase_percent': conventions.get('lowercase_percent', 0),
                'camelcase_percent': conventions.get('camelcase_percent', 0),
                'snake_case_percent': conventions.get('snake_case_percent', 0)
            }
        
        # 2. Fallback - analyze field names
        if self.php_patterns.get('field_names'):
            fields = self.php_patterns['field_names'][:50]
            
            uppercase = 0
            lowercase = 0
            camelcase = 0
            snake_case = 0
            
            for field in fields:
                field_name = field.get('name', field) if isinstance(field, dict) else str(field)
                
                if field_name.isupper():
                    uppercase += 1
                elif field_name.islower():
                    lowercase += 1
                elif '_' in field_name:
                    snake_case += 1
                elif field_name[0].isupper():
                    camelcase += 1
            
            total = len(fields)
            if total > 0:
                dominant = max([
                    ('UPPERCASE', uppercase),
                    ('lowercase', lowercase),
                    ('PascalCase', camelcase),
                    ('snake_case', snake_case)
                ], key=lambda x: x[1])
                
                logger.info(f"✅ Detected naming convention: {dominant[0]} ({dominant[1]}/{total})")
                return {
                    'style': dominant[0],
                    'uppercase_percent': (uppercase / total) * 100,
                    'lowercase_percent': (lowercase / total) * 100,
                    'camelcase_percent': (camelcase / total) * 100,
                    'snake_case_percent': (snake_case / total) * 100
                }
        
        # 3. Fallback
        default_style = str(os.getenv('CODEGEN_DEFAULT_FIELD_STYLE', 'PascalCase')).strip() or 'PascalCase'
        return {
            'style': default_style,
            'uppercase_percent': 20,
            'lowercase_percent': 20,
            'camelcase_percent': 40,
            'snake_case_percent': 20
        }

    
    def get_css_classes(self) -> List[str]:
        """Extract CSS classes used in company codebase"""
        classes = set()
        
        # 1. Extract from analyzed patterns
        if self.html_patterns.get('css_classes'):
            for css_class in self.html_patterns['css_classes']:
                class_name = css_class.get('name', css_class) if isinstance(css_class, dict) else str(css_class)
                classes.add(class_name)
            
            if classes:
                logger.info(f"✅ Extracted {len(classes)} CSS classes from analyzed patterns")
        
        # 2. Fallback - Bootstrap 3/4/5 common classes
        generic_classes = self._get_list_setting(
            'CODEGEN_GENERIC_CSS_CLASSES',
            'CODEGEN_GENERIC_CSS_CLASSES',
            default=[
                'form-control', 'form-group', 'form-horizontal', 'form-row',
                'btn', 'btn-primary', 'btn-success', 'btn-danger',
                'col-md-2', 'col-md-4', 'col-md-6', 'col-md-12',
                'input-sm', 'input-lg', 'control-label',
                'table', 'table-striped', 'table-bordered',
                'container', 'row', 'col'
            ]
        )
        
        if not classes:
            self._register_generic_fallback(
                'css_classes',
                'No company CSS classes detected in analyzed patterns'
            )
            classes.update(generic_classes)
        elif self.allow_generic_augmentation:
            # Add common classes as backup
            classes.update(generic_classes[:10])
        
        return list(classes)
    
    def classify_file_by_size(self, file_size: int) -> str:
        """
        Classify file type based on size
        Returns: 'simple_form', 'complex_form', 'invoice', 'report'
        """
        simple_max = get_int_setting(
            'CODEGEN_SIMPLE_FORM_MAX_BYTES',
            'CODEGEN_SIMPLE_FORM_MAX_BYTES',
            15000,
            min_value=5000,
            max_value=200000
        )
        complex_max = get_int_setting(
            'CODEGEN_COMPLEX_FORM_MAX_BYTES',
            'CODEGEN_COMPLEX_FORM_MAX_BYTES',
            40000,
            min_value=simple_max + 1,
            max_value=300000
        )
        invoice_max = get_int_setting(
            'CODEGEN_INVOICE_MAX_BYTES',
            'CODEGEN_INVOICE_MAX_BYTES',
            100000,
            min_value=complex_max + 1,
            max_value=1000000
        )

        if file_size < simple_max:
            return 'simple_form'
        elif file_size < complex_max:
            return 'complex_form'
        elif file_size < invoice_max:
            return 'invoice'
        else:  # > 100KB
            return 'report'
    
    def get_simple_form_indicators(self) -> List[str]:
        """
        Get indicators for simple master forms
        Uses file size + pattern analysis
        """
        indicators = []
        
        # 1. Extract from analyzed patterns - find small files
        if self.php_patterns.get('table_names'):
            tables = self.php_patterns['table_names']
            
            # Extract entity names from table names
            for table in tables[:30]:
                table_name = table.get('name', table) if isinstance(table, dict) else str(table)
                # Remove prefix
                clean_name = table_name.lower()
                for prefix in ['tbl', 'tb_', 't_', 'table_']:
                    if clean_name.startswith(prefix):
                        clean_name = clean_name[len(prefix):]
                        break
                
                indicators.append(clean_name)
        
        # 2. Fallback - generic master form entities
        generic_indicators = self._get_list_setting(
            'CODEGEN_SIMPLE_FORM_INDICATORS',
            'CODEGEN_SIMPLE_FORM_INDICATORS',
            default=[
                'area', 'subarea', 'category', 'unit', 'type', 'group',
                'department', 'designation', 'branch', 'warehouse',
                'supplier', 'manufacturer', 'brand', 'model',
                'city', 'country', 'state', 'region'
            ]
        )
        
        if not indicators:
            indicators = generic_indicators
        
        return indicators

    
    def get_all_patterns_for_query(self) -> Dict[str, List[str]]:
        """
        Get all patterns for building search query
        Returns comprehensive pattern dictionary
        """
        return {
            'database_functions': self.get_database_functions(),
            'helper_functions': self.get_helper_functions(),
            'transaction_functions': self.get_transaction_functions(),
            'ajax_functions': self.get_ajax_functions(),
            'table_prefix': self.get_table_prefix(),
            'field_naming': self.get_field_naming_convention(),
            'css_classes': self.get_css_classes(),
            'simple_form_indicators': self.get_simple_form_indicators()
        }
    
    def get_core_keywords(self) -> List[str]:
        """
        Get CORE keywords for search query
        Combines analyzed patterns + generic fallbacks
        """
        keywords = []
        
        # Database operations
        keywords.extend(self.get_database_functions()[:6])
        
        # Helper functions
        keywords.extend(self.get_helper_functions()[:3])
        
        # Transaction management
        trans = self.get_transaction_functions()
        if trans.get('start'):
            keywords.append(trans['start'].split('|')[0])
        if trans.get('end'):
            keywords.append(trans['end'].split('|')[0])
        
        # AJAX patterns
        keywords.extend(self.get_ajax_functions()[:5])
        
        # Session/Audit keywords (configurable)
        session_keywords = self._get_list_setting(
            'CODEGEN_SESSION_AUDIT_KEYWORDS',
            'CODEGEN_SESSION_AUDIT_KEYWORDS',
            default=['session', 'User_ID', 'Comp_Code', 'Login_ID']
        )
        keywords.extend(session_keywords)
        
        return keywords
    
    def should_exclude_file(self, filename: str, file_size: int, intent_type: str) -> bool:
        """
        Dynamic file exclusion based on analyzed patterns + file size
        """
        filename_lower = filename.lower()
        
        # Classify file by size
        file_class = self.classify_file_by_size(file_size)
        
        # If generating FORM
        if intent_type == 'form':
            # Exclude large transaction files
            if file_class in ['invoice', 'report']:
                logger.info(f"   ⛔ Excluding {filename} (size: {file_size}, class: {file_class})")
                return True
            
            # Exclude files with transaction keywords
            transaction_keywords = self._get_list_setting(
                'CODEGEN_FORM_EXCLUDE_KEYWORDS',
                'CODEGEN_FORM_EXCLUDE_KEYWORDS',
                default=['invoice', 'sale', 'purchase', 'order', 'booking', 'quotation']
            )
            if any(kw in filename_lower for kw in transaction_keywords):
                return True
        
        # If generating INVOICE
        elif intent_type == 'invoice':
            # Exclude simple forms
            if file_class == 'simple_form':
                simple_indicators = self.get_simple_form_indicators()
                if any(indicator in filename_lower for indicator in simple_indicators):
                    logger.info(f"   ⛔ Excluding {filename} (simple form, size: {file_size})")
                    return True
        
        return False
