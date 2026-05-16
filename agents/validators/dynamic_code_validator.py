"""
Dynamic Code Validator - STEP 3 Implementation
Validates generated code with CRITICAL error blocking and size validation
"""
import logging
import re
from typing import Dict, List, Optional

from agents.utils.runtime_config import get_int_setting

logger = logging.getLogger(__name__)

DEFAULT_MIN_SIZE_KB = get_int_setting(
    'CODEGEN_DYNAMIC_MIN_SIZE_KB',
    'CODEGEN_DYNAMIC_MIN_SIZE_KB',
    default=8,
    min_value=4,
    max_value=100,
)
DEFAULT_TARGET_SIZE_KB = get_int_setting(
    'CODEGEN_DYNAMIC_TARGET_SIZE_KB',
    'CODEGEN_DYNAMIC_TARGET_SIZE_KB',
    default=14,
    min_value=8,
    max_value=150,
)

COMPANY_HELPER_FIELD_IGNORE = {
    'session_start',
    'db_insert',
    'db_update',
    'db_delete',
    'db_getrecord',
    'getrows',
    'getrows2',
    'getvalue',
    'funstarttran',
    'funendtran',
    'fun_log',
    'formvalidation',
    'checkkeycode',
    'getmaxid',
    'getcostcenter',
    'txtcountacc',
}


class DynamicCodeValidator:
    """
    âœ… STEP 3 FIX: Dynamic code validation with:
    - V-1: Critical errors BLOCK generation (score = 0)
    - V-2: Code size validation (configurable thresholds)
    - V-3: Proper needs_revision handling
    
    Uses dynamic patterns from analyzed codebase
    """
    
    def __init__(self, analyzed_patterns: Optional[Dict] = None, user_request: str = ""):
        self.analyzed_patterns = analyzed_patterns or {}
        self.user_request = self._normalize_request_sections(user_request)
        self.strict_security_rules = False
        self.strict_contract_mode = False
        
        # Extract expected patterns from user request
        self.expected_patterns = self._extract_expected_patterns()
        
        logger.info("ðŸŽ¯ STEP 3: Initialized DynamicCodeValidator")
        logger.info(f"   Expected patterns: {len(self.expected_patterns)} items")

    def _normalize_request_sections(self, user_request: str) -> str:
        """
        Normalize compact prompts into section/bullet-friendly text so validator
        parsing matches the main generation path.
        """
        request_text = (user_request or "").replace('\r\n', '\n').replace('\r', '\n').strip()
        if not request_text:
            return ''

        protected_lines = []
        for raw_line in request_text.split('\n'):
            stripped = raw_line.strip()
            if stripped.startswith('- ') and '|' in stripped:
                protected_lines.append(raw_line.rstrip())
            else:
                normalized_line = re.sub(r'\s*\|\s*', '\n', raw_line)
                protected_lines.append(normalized_line.rstrip())
        request_text = '\n'.join(protected_lines)

        section_pattern = (
            r'(?:table|file\s*name|filename|file|title|case\s*type|casetype|'
            r'primary\s*key|master\s*fields|form\s*fields|detail\s*grid|detail\s*fields|'
            r'detail\s*table|relationships?|dependencies?|business\s*validations?|'
            r'validation\s*rules|required\s*company\s*patterns|required\s*patterns|'
            r'operations|crud\s*operations|output)'
        )
        request_text = re.sub(
            rf'\s+(?={section_pattern}\s*:)',
            '\n',
            request_text,
            flags=re.IGNORECASE
        )
        request_text = re.sub(
            r'\s+(?=-\s*[A-Za-z_][A-Za-z0-9_]*)',
            '\n',
            request_text
        )
        request_text = re.sub(r'\n{3,}', '\n\n', request_text)
        return request_text.strip()
    
    def _extract_expected_patterns(self) -> Dict:
        """
        Extract what user explicitly requested
        Returns patterns that MUST be present
        """
        patterns = {
            'table_name': None,
            'allowed_tables': [],
            'field_names': [],
            'field_contract': [],
            'detail_table': None,
            'detail_field_names': [],
            'ajax_param': None,
            'parent_field': None,
            'code_length': None,
            'pre_delete_tables': [],
            'primary_key': None,
            'unique_fields': [],
            'requires_email_validation': False,
            'requires_keyboard_navigation': False,
            'requires_frontend_validation': False,
            'min_size_kb': DEFAULT_MIN_SIZE_KB,
            'target_size_kb': max(DEFAULT_TARGET_SIZE_KB, DEFAULT_MIN_SIZE_KB + 4),
            'size_enforced': False
        }
        
        if not self.user_request:
            return patterns
        
        # Extract table name
        table_pattern = r'(?:master_table|table)[:\s]+(\w+)'
        table_match = re.search(table_pattern, self.user_request, re.IGNORECASE)
        if table_match:
            patterns['table_name'] = table_match.group(1)
        allowed_tables = set()
        if patterns['table_name']:
            allowed_tables.add(patterns['table_name'])
        detail_table_match = re.search(
            r'detail\s+table\s*[:\-]?\s*([A-Za-z_][A-Za-z0-9_]*)',
            self.user_request,
            re.IGNORECASE
        )
        if detail_table_match:
            patterns['detail_table'] = detail_table_match.group(1)
            allowed_tables.add(patterns['detail_table'])

        detail_grid_match = re.search(
            (
                r'(?is)detail\s+(?:grid|fields?)\s*(?:\([^)]+\))?\s*:\s*(.*?)'
                r'(?:relationships?\s*:|dependencies?\s*:|business\s+validations?\s*:|operations\s*:|'
                r'required(?:\s+company)?\s+(?:patterns|functions)\s*:|calculations?\s*:|'
                r'grid\s+operations?\s*:|cascading\s+dropdowns?\s*:|pre-?delete\s+checks?\s*:|output\s*:|$)'
            ),
            self.user_request
        )
        if detail_grid_match:
            detail_fields = re.findall(
                r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=\||,|\n|$)',
                detail_grid_match.group(1),
                re.IGNORECASE
            )
            patterns['detail_field_names'] = self._sanitize_field_names(detail_fields)
        allowed_tables.update(
            re.findall(r'-\s*(tbl[a-zA-Z0-9_]+)\b', self.user_request, re.IGNORECASE)
        )
        
        # Extract field names
        field_pattern = r'[Ii]nclude\s+ALL\s+\d+\s+fields\s+with\s+exact\s+naming:\s*([^\n]+)'
        field_match = re.search(field_pattern, self.user_request)
        if field_match:
            field_text = field_match.group(1)
            patterns['field_names'] = [f.strip() for f in re.split(r'[,\n]', field_text) if f.strip()]
        if not patterns['field_names']:
            master_fields_match = re.search(
                (
                    r'(?is)master\s+fields?(?:\s*\([^)]*\))?\s*:\s*(.*?)'
                    r'(?:detail\s+grid\s*:|relationships?\s*:|dependencies?\s*:|business\s+validations?\s*:|operations\s*:|'
                    r'required(?:\s+company)?\s+(?:patterns|functions)\s*:|output\s*:|$)'
                ),
                self.user_request
            )
            if master_fields_match:
                section = master_fields_match.group(1)
                # Bullet form: "- Employee_Code"
                bullet_fields = re.findall(
                    r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=\||,|\n|$)',
                    section
                )
                if bullet_fields:
                    patterns['field_names'] = bullet_fields
                else:
                    # Comma/pipe form: "Employee_Code(readonly), Employee_Name(textbox, required), ..."
                    raw_items = [x.strip() for x in re.split(r'[,\n|]', section) if x.strip()]
                    extracted = []
                    for item in raw_items:
                        name = re.split(r'\s*\(', item, maxsplit=1)[0].strip()
                        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                            extracted.append(name)
                    patterns['field_names'] = extracted
        if not patterns['field_names']:
            generic_fields_match = re.search(
                (
                    r'(?is)(?<!master\s)\bfields?\s*:\s*(.*?)'
                    r'(?:detail\s+grid\s*:|detail\s+fields?\s*:|relationships?\s*:|dependencies?\s*:|'
                    r'business\s+validations?\s*:|operations\s*:|required(?:\s+company)?\s+(?:patterns|functions)\s*:|'
                    r'calculations?\s*:|grid\s+operations?\s*:|cascading\s+dropdowns?\s*:|pre-?delete\s+checks?\s*:|'
                    r'features?\s*:|output\s*:|$)'
                ),
                self.user_request
            )
            if generic_fields_match:
                section = generic_fields_match.group(1)
                bullet_fields = re.findall(
                    r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?=\||,|\n|$)',
                    section
                )
                if bullet_fields:
                    patterns['field_names'] = bullet_fields
                else:
                    raw_items = [x.strip() for x in re.split(r'[,\n|]', section) if x.strip()]
                    extracted = []
                    for item in raw_items:
                        name = re.split(r'\s*\(', item, maxsplit=1)[0].strip()
                        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                            extracted.append(name)
                    patterns['field_names'] = extracted
        if not patterns['field_names']:
            simple_fields_match = re.search(
                r'(?is)(?<!master\s)\bfields?\s*:\s*([^\n]+)',
                self.user_request
            )
            if simple_fields_match:
                field_text = simple_fields_match.group(1)
                patterns['field_names'] = [
                    f.strip().lstrip('-').strip()
                    for f in re.split(r'[,\n|]', field_text)
                    if f.strip()
                ]
        patterns['field_names'] = self._sanitize_field_names(patterns['field_names'])
        patterns['field_contract'] = self._extract_field_contract()
        if not patterns['field_names'] and patterns['field_contract']:
            patterns['field_names'] = self._sanitize_field_names(
                [str(field.get('name') or '').strip() for field in patterns['field_contract']]
            )

        # Extract AJAX parameter
        ajax_pattern = r'AJAX\s+GetMaxID\s+MUST\s+receive\s+(\w+)\s+parameter'
        ajax_match = re.search(ajax_pattern, self.user_request, re.IGNORECASE)
        if ajax_match:
            patterns['ajax_param'] = ajax_match.group(1)
        
        # Extract parent field
        parent_pattern = r'[Pp]arent\s+dropdown\s*\(([^)]+)\s+from'
        parent_match = re.search(parent_pattern, self.user_request)
        if parent_match:
            patterns['parent_field'] = parent_match.group(1).strip()

        primary_key_match = re.search(
            r'(?is)primary[_\s]*key\s*:\s*(?:\n|\r\n)?\s*(?:-\s*)?([A-Za-z_][A-Za-z0-9_]*)',
            self.user_request
        )
        if primary_key_match:
            patterns['primary_key'] = primary_key_match.group(1).strip()
        
        # Extract code length
        code_length_pattern = r'RIGHT\(Code,(\d+)\)'
        code_match = re.search(code_length_pattern, self.user_request)
        if code_match:
            patterns['code_length'] = int(code_match.group(1))
        
        # Extract pre-delete tables
        predelete_pattern = r'Pre-delete\s+checks.*?tables?:\s*([^\n]+)'
        predelete_match = re.search(predelete_pattern, self.user_request, re.IGNORECASE | re.DOTALL)
        if predelete_match:
            tables_text = predelete_match.group(1)
            # Extract table names
            table_names = re.findall(r'(\w+)\s+(?:table|with)', tables_text, re.IGNORECASE)
            patterns['pre_delete_tables'] = table_names
            allowed_tables.update(table_names)

        patterns['unique_fields'] = re.findall(
            r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s+must\s+be\s+unique\s+within\s+comp_code',
            self.user_request,
            re.IGNORECASE
        )
        patterns['requires_email_validation'] = bool(
            re.search(r'email[^\n]{0,80}(validate|validation|format)', self.user_request, re.IGNORECASE)
        )
        numeric_field_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s+numeric\b', self.user_request, re.IGNORECASE)
        patterns['numeric_validation_field'] = numeric_field_match.group(1).strip() if numeric_field_match else None
        patterns['requires_keyboard_navigation'] = bool(
            re.search(
                r'checkkeycode|keyboard(?:\s+navigation)?|enter\s+key|onkeydown',
                self.user_request,
                re.IGNORECASE
            )
        )
        patterns['requires_frontend_validation'] = bool(
            re.search(
                r'\bvalidation\b|formvalidation|frontend\s+validation|client-?side\s+validation',
                self.user_request,
                re.IGNORECASE
            )
        )
        
        # Extract target size (explicit request only)
        size_pattern = r'Target:\s*(\d+)(?:-(\d+))?\s*KB'
        size_match = re.search(size_pattern, self.user_request, re.IGNORECASE)
        if size_match:
            min_kb = int(size_match.group(1))
            max_kb = int(size_match.group(2) or size_match.group(1))
            patterns['min_size_kb'] = max(4, min_kb)
            patterns['target_size_kb'] = max(patterns['min_size_kb'], max_kb)
            patterns['size_enforced'] = True

        explicit_min_pattern = r'(?:at\s+least|min(?:imum)?)\s*(\d+)\s*KB'
        explicit_min_match = re.search(explicit_min_pattern, self.user_request, re.IGNORECASE)
        if explicit_min_match:
            explicit_min = int(explicit_min_match.group(1))
            patterns['min_size_kb'] = max(patterns['min_size_kb'], explicit_min)
            patterns['target_size_kb'] = max(patterns['target_size_kb'], patterns['min_size_kb'])
            patterns['size_enforced'] = True

        patterns['allowed_tables'] = sorted({tbl for tbl in allowed_tables if tbl})
        return patterns

    def _sanitize_field_names(self, field_names: List[str]) -> List[str]:
        """
        Keep only likely business fields. Strict prompts often include
        company helper names in "Required Patterns", which should not be
        validated as entity fields.
        """
        cleaned: List[str] = []
        seen = set()

        for raw_name in field_names or []:
            candidate = str(raw_name or '').strip().lstrip('-').strip()
            if not candidate:
                continue

            candidate_lower = candidate.lower()
            if candidate_lower in COMPANY_HELPER_FIELD_IGNORE:
                continue
            if candidate_lower.startswith('db_'):
                continue
            if candidate_lower.startswith('fun') and candidate_lower not in {'fund_code'}:
                continue

            if candidate_lower not in seen:
                cleaned.append(candidate)
                seen.add(candidate_lower)

        return cleaned

    def _merge_intent_expectations(self, intent: Dict) -> None:
        """
        Merge strict contract context from runtime intent into expected patterns.
        This fills detail_table/detail_fields even when user_request text is incomplete.
        """
        strict_contract = intent.get('strict_contract') or {}
        if not isinstance(strict_contract, dict) or not strict_contract.get('valid'):
            return

        master_table = str(strict_contract.get('master_table') or '').strip()
        detail_table = str(strict_contract.get('detail_table') or '').strip()
        primary_key = str(strict_contract.get('primary_key') or '').strip()

        master_fields_raw = strict_contract.get('master_fields') or []
        detail_fields_raw = strict_contract.get('detail_fields') or []

        def _normalize_fields(raw_fields, section_name: str) -> List[Dict]:
            normalized = []
            for field in raw_fields:
                if isinstance(field, dict):
                    name = str(field.get('name') or '').strip()
                    if not name:
                        continue
                    normalized.append({
                        'name': name,
                        'db_type': str(field.get('db_type') or '').strip(),
                        'input_type': str(field.get('input_type') or '').strip(),
                        'required': bool(field.get('required')),
                        'section': section_name,
                    })
                elif field:
                    field_name = str(field).strip()
                    normalized.append({
                        'name': field_name,
                        'db_type': '',
                        'input_type': '',
                        'required': False,
                        'section': section_name,
                    })
            return normalized

        merged_master = _normalize_fields(master_fields_raw, 'master')
        merged_detail = _normalize_fields(detail_fields_raw, 'detail')
        merged_contract = merged_master + merged_detail

        if master_table:
            self.expected_patterns['table_name'] = master_table
        if detail_table:
            self.expected_patterns['detail_table'] = detail_table
        if primary_key:
            self.expected_patterns['primary_key'] = primary_key
        if merged_contract:
            self.expected_patterns['field_contract'] = merged_contract
            self.expected_patterns['field_names'] = self._sanitize_field_names(
                [field.get('name', '') for field in merged_master] or
                [field.get('name', '') for field in merged_contract]
            )
            self.expected_patterns['detail_field_names'] = self._sanitize_field_names(
                [field.get('name', '') for field in merged_detail]
            )

        allowed_tables = set(self.expected_patterns.get('allowed_tables') or [])
        if master_table:
            allowed_tables.add(master_table)
        if detail_table:
            allowed_tables.add(detail_table)
        for dep in strict_contract.get('dependencies') or []:
            table = str(dep.get('table') or '').strip()
            if table:
                allowed_tables.add(table)
        self.expected_patterns['allowed_tables'] = sorted(allowed_tables)

    def _extract_field_contract(self) -> List[Dict]:
        """Extract structured field definitions from Master Fields lines."""
        contract: List[Dict] = []
        seen = set()

        def append_contract_entry(name: str, db_type: str, input_type: str, required: bool) -> None:
            cleaned_name = str(name or '').strip()
            if not cleaned_name:
                return

            key = cleaned_name.lower()
            if key in seen:
                return

            contract.append({
                'name': cleaned_name,
                'db_type': str(db_type or '').strip(),
                'input_type': str(input_type or '').strip(),
                'required': bool(required),
            })
            seen.add(key)

        master_fields_match = re.search(
            (
                r'(?is)master\s+fields?(?:\s*\([^)]*\))?\s*:\s*(.*?)'
                r'(?:detail\s+grid\s*:|detail\s+fields?\s*:|relationships?\s*:|dependencies?\s*:|'
                r'business\s+validations?\s*:|operations\s*:|required(?:\s+company)?\s+(?:patterns|functions)\s*:|'
                r'calculations?\s*:|grid\s+operations?\s*:|cascading\s+dropdowns?\s*:|pre-?delete\s+checks?\s*:|output\s*:|$)'
            ),
            self.user_request or ''
        )
        if not master_fields_match:
            master_fields_match = re.search(
                (
                    r'(?is)(?<!master\s)\bfields?\s*:\s*(.*?)'
                    r'(?:detail\s+grid\s*:|detail\s+fields?\s*:|relationships?\s*:|dependencies?\s*:|'
                    r'business\s+validations?\s*:|operations\s*:|required(?:\s+company)?\s+(?:patterns|functions)\s*:|'
                    r'calculations?\s*:|grid\s+operations?\s*:|cascading\s+dropdowns?\s*:|pre-?delete\s+checks?\s*:|'
                    r'features?\s*:|output\s*:|$)'
                ),
                self.user_request or ''
            )
        if not master_fields_match:
            return contract

        section_text = master_fields_match.group(1)
        forbidden_line_tokens = (
            'db_insert', 'ajax', 'tblattendance', 'delete', 'detail', 'pre', 'function', 'getrows', 'getvalue'
        )
        strict_line_patterns = [
            re.compile(
                r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*DB\s*:\s*([^|]+)\|\s*Input\s*:\s*([^|]+)'
                r'(?:\|\s*Required\s*:\s*(Yes|No|True|False|Mandatory))?',
                re.IGNORECASE
            ),
            re.compile(
                r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*DB\s*:\s*([^|]+)\|\s*Grid\s*:\s*([^|]+)'
                r'(?:\|\s*Required\s*:\s*(Yes|No|True|False|Mandatory))?',
                re.IGNORECASE
            ),
        ]

        for raw_line in re.findall(r'-\s*[^\n]+', section_text):
            stripped = raw_line.strip()
            lowered = stripped.lower()
            if any(token in lowered for token in forbidden_line_tokens):
                continue
            if re.search(r'\btbl[a-z0-9_]+\b', lowered):
                continue

            matched = None
            for pattern in strict_line_patterns:
                matched = pattern.search(stripped)
                if matched:
                    break
            if not matched:
                continue

            append_contract_entry(
                matched.group(1).strip(),
                matched.group(2).strip(),
                matched.group(3).strip(),
                (matched.group(4) or '').strip().lower() in {'yes', 'true', 'mandatory'}
            )

        # Support normalized prompts where `|` sections were expanded into multiline blocks:
        # - Field_Name
        #   DB: varchar
        #   Input: textbox
        #   Required: Yes
        current_field: Optional[Dict[str, object]] = None

        def flush_current_field() -> None:
            nonlocal current_field
            if not current_field:
                return
            append_contract_entry(
                str(current_field.get('name') or ''),
                str(current_field.get('db_type') or ''),
                str(current_field.get('input_type') or ''),
                bool(current_field.get('required')),
            )
            current_field = None

        for raw_line in section_text.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            lowered = stripped.lower()
            if any(token in lowered for token in forbidden_line_tokens):
                flush_current_field()
                continue
            if re.search(r'\btbl[a-z0-9_]+\b', lowered):
                flush_current_field()
                continue

            bullet_match = re.match(r'-\s*([A-Za-z_][A-Za-z0-9_]*)\s*$', stripped)
            if bullet_match:
                flush_current_field()
                current_field = {
                    'name': bullet_match.group(1).strip(),
                    'db_type': '',
                    'input_type': '',
                    'required': False,
                }
                continue

            if not current_field:
                continue

            db_match = re.match(r'DB\s*:\s*(.+)$', stripped, re.IGNORECASE)
            if db_match:
                current_field['db_type'] = db_match.group(1).strip()
                continue

            input_match = re.match(r'(?:Input|Grid)\s*:\s*(.+)$', stripped, re.IGNORECASE)
            if input_match:
                current_field['input_type'] = input_match.group(1).strip()
                continue

            required_match = re.match(r'Required\s*:\s*(.+)$', stripped, re.IGNORECASE)
            if required_match:
                current_field['required'] = required_match.group(1).strip().lower() in {
                    'yes', 'true', 'mandatory'
                }

        flush_current_field()

        return contract

    
    def validate_code(self, generated_code: str, intent: Dict) -> Dict:
        """
        âœ… STEP 3 FIX: Comprehensive validation with CRITICAL error blocking
        
        Returns:
            {
                'valid': True/False,
                'score': 0-100,
                'critical_errors': [],
                'warnings': [],
                'needs_revision': True/False,
                'block_generation': True/False  # NEW: Force block if critical
            }
        """
        result = {
            'valid': True,
            'score': 100,
            'critical_errors': [],
            'warnings': [],
            'needs_revision': False,
            'block_generation': False
        }
        
        if not generated_code:
            result['valid'] = False
            result['score'] = 0
            result['critical_errors'].append("No code generated")
            result['block_generation'] = True
            return result
        
        logger.info("ðŸ” STEP 3: Running dynamic code validation")
        intent = intent or {}
        self.strict_contract_mode = bool(intent.get('strict_contract_mode'))
        self._merge_intent_expectations(intent)
        self.strict_security_rules = bool(
            intent.get('strict_security_rules')
            or self.expected_patterns.get('field_contract')
        )
        required_features = {
            str(feature or '').strip().lower()
            for feature in (intent.get('required_features') or [])
            if str(feature or '').strip()
        }
        if 'validation' in required_features:
            self.expected_patterns['requires_frontend_validation'] = True
        
        # âœ… V-2: Code Size Validation (CRITICAL)
        size_result = self._validate_code_size(generated_code)
        if not size_result['valid']:
            result['critical_errors'].extend(size_result['errors'])
            result['valid'] = False
            result['score'] = 0  # âœ… V-1: Critical error = score 0
            result['block_generation'] = True
            result['needs_revision'] = True
            logger.error(f"âŒ CRITICAL: Code size validation FAILED - {size_result['errors']}")
            return result
        elif size_result['warnings']:
            result['warnings'].extend(size_result['warnings'])
            result['score'] -= 10
        
        # âœ… V-1: Table Name Validation (CRITICAL if user specified)
        if self.expected_patterns['table_name']:
            table_result = self._validate_table_name(generated_code)
            if not table_result['valid']:
                result['critical_errors'].extend(table_result['errors'])
                result['valid'] = False
                result['score'] = 0
                result['block_generation'] = True
                result['needs_revision'] = True
                logger.error(f"âŒ CRITICAL: Table name validation FAILED")
                return result
        
        # âœ… V-1: Field Names Validation (CRITICAL if user specified)
        if self.expected_patterns['field_names']:
            field_result = self._validate_field_names(generated_code)
            if not field_result['valid']:
                result['critical_errors'].extend(field_result['errors'])
                result['score'] -= 50  # Major penalty but not blocking
                result['needs_revision'] = True
                logger.error(f"âŒ MAJOR: Field names validation FAILED")
            elif field_result['warnings']:
                result['warnings'].extend(field_result['warnings'])
                result['score'] -= 10

        if self.expected_patterns.get('field_contract'):
            contract_result = self._validate_field_contract(generated_code)
            if not contract_result['valid']:
                result['critical_errors'].extend(contract_result['errors'])
                result['score'] -= 35
                result['needs_revision'] = True
                logger.error("❌ MAJOR: Field contract validation FAILED")
            if contract_result['warnings']:
                result['warnings'].extend(contract_result['warnings'])
                result['score'] -= min(10, len(contract_result['warnings']) * 2)

        detail_table = self.expected_patterns.get('detail_table')
        if detail_table:
            master_detail_result = self._validate_master_detail_structure(generated_code)
            if not master_detail_result['valid']:
                result['critical_errors'].extend(master_detail_result['errors'])
                result['valid'] = False
                result['score'] = 0
                result['block_generation'] = True
                result['needs_revision'] = True
                logger.error("❌ CRITICAL: Master-detail validation FAILED")
                return result
        
        # âœ… V-1: AJAX Parameter Validation (CRITICAL if user specified)
        if self.expected_patterns['ajax_param']:
            ajax_result = self._validate_ajax_parameter(generated_code)
            if not ajax_result['valid']:
                result['critical_errors'].extend(ajax_result['errors'])
                result['valid'] = False
                result['score'] = 0
                result['block_generation'] = True
                result['needs_revision'] = True
                logger.error(f"âŒ CRITICAL: AJAX parameter validation FAILED")
                return result
        
        # âœ… V-1: Code Length Validation (CRITICAL if user specified)
        if self.expected_patterns['code_length']:
            code_length_result = self._validate_code_length(generated_code)
            if not code_length_result['valid']:
                result['critical_errors'].extend(code_length_result['errors'])
                result['score'] -= 30
                result['needs_revision'] = True
                logger.error(f"âŒ MAJOR: Code length validation FAILED")
        
        # âœ… V-1: Pre-Delete Tables Validation (CRITICAL if user specified)
        if self.expected_patterns['pre_delete_tables']:
            predelete_result = self._validate_predelete_checks(generated_code)
            if not predelete_result['valid']:
                result['critical_errors'].extend(predelete_result['errors'])
                result['score'] -= 40
                result['needs_revision'] = True
                logger.error(f"âŒ MAJOR: Pre-delete validation FAILED")

        # Enterprise production readiness checks (layout, scripts, guards, CRUD safety)
        enterprise_result = self._validate_enterprise_requirements(generated_code)
        if not enterprise_result['valid']:
            result['critical_errors'].extend(enterprise_result['errors'])
            result['valid'] = False
            result['score'] = 0
            result['block_generation'] = True
            result['needs_revision'] = True
            logger.error(
                "âŒ CRITICAL: Enterprise production readiness validation FAILED - %s",
                enterprise_result['errors']
            )
            return result
        if enterprise_result['warnings']:
            result['warnings'].extend(enterprise_result['warnings'])
            result['score'] -= min(20, len(enterprise_result['warnings']) * 3)
        
        # Final decision
        if result['score'] < 50:
            result['valid'] = False
            result['needs_revision'] = True

        if result.get('needs_revision') or result.get('block_generation'):
            result['valid'] = False
            result['score'] = min(int(result.get('score', 0) or 0), 49)
        
        logger.info(f"âœ… STEP 3: Validation complete - Score: {result['score']}%, Valid: {result['valid']}")
        logger.info(f"   Critical errors: {len(result['critical_errors'])}")
        logger.info(f"   Warnings: {len(result['warnings'])}")
        logger.info(f"   Needs revision: {result['needs_revision']}")
        logger.info(f"   Block generation: {result['block_generation']}")
        
        return result

    
    def _validate_code_size(self, code: str) -> Dict:
        """
        Validate code size against the minimum and target thresholds.
        If code is below the declared minimum, treat it as incomplete.
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        code_size_kb = len(code) / 1024
        min_size = self.expected_patterns['min_size_kb']
        target_size = self.expected_patterns['target_size_kb']
        size_enforced = bool(self.expected_patterns.get('size_enforced'))
        hard_floor = min_size * (0.60 if size_enforced else 0.45)

        logger.info(
            f"Code size: {code_size_kb:.1f}KB "
            f"(min: {min_size}KB, target: {target_size}KB, enforced: {size_enforced})"
        )

        if code_size_kb < hard_floor:
            result['valid'] = False
            result['errors'].append(
                f"Code too small: {code_size_kb:.1f}KB < {hard_floor:.1f}KB minimum. "
                f"Code appears to be severely incomplete. Regenerate with more detail."
            )
        elif code_size_kb < min_size:
            if size_enforced:
                result['valid'] = False
                result['errors'].append(
                    f"Code below required minimum size: {code_size_kb:.1f}KB < {min_size}KB. "
                    f"The generation should be revised before approval."
                )
            else:
                result['warnings'].append(
                    f"Code below default minimum size: {code_size_kb:.1f}KB < {min_size}KB. "
                    f"Review for completeness."
                )
        elif code_size_kb < target_size * 0.8:
            result['warnings'].append(
                f"Code smaller than target: {code_size_kb:.1f}KB < {target_size}KB. "
                f"May be missing sections."
            )

        return result
    
    def _validate_table_name(self, code: str) -> Dict:
        """
        âœ… V-1: Table name validation
        CRITICAL: Must use correct table name
        """
        result = {'valid': True, 'errors': []}
        
        expected_table = self.expected_patterns['table_name']
        if not expected_table:
            return result
        
        # Check for table name in code
        # Pattern: $table = "tblsubarea" or "tblsubarea" in queries
        table_patterns = [
            rf'\$table\s*=\s*["\']({expected_table})["\']',
            rf'FROM\s+({expected_table})\b',
            rf'INTO\s+({expected_table})\b',
            rf'UPDATE\s+({expected_table})\b'
        ]
        
        found = False
        for pattern in table_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                found = True
                break
        
        if not found:
            result['valid'] = False
            result['errors'].append(
                f"Table name '{expected_table}' not found in code. "
                f"Check $table variable and SQL queries."
            )
        
        return result
    
    def _validate_field_names(self, code: str) -> Dict:
        """
        ✅ V-1: Field names validation
        MAJOR: Should use user-specified field names
        
        FIX #4A: Flexible field name search with multiple variations
        Checks for: Area_Code, area_code, AreaCode, 'Area_Code', name="area_code", id="Area_Code"
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        expected_fields = self.expected_patterns['field_names']
        if not expected_fields:
            return result
        
        missing_fields = []
        for field in expected_fields:
            # FIX #4A: Check multiple field name variations
            # 1. Original case: Area_Code
            # 2. Lowercase: area_code
            # 3. Uppercase: AREA_CODE
            # 4. CamelCase: AreaCode
            # 5. In quotes: 'Area_Code', "Area_Code"
            # 6. In HTML attributes: name="area_code", id="Area_Code"
            # 7. In PHP arrays: $columns['Area_Code'], $_REQUEST['area_code']
            
            field_lower = field.lower()
            field_upper = field.upper()
            field_camel = ''.join(word.capitalize() for word in field.split('_'))
            
            field_patterns = [
                # Exact match (case-insensitive)
                rf'\b{re.escape(field)}\b',
                rf'\b{re.escape(field_lower)}\b',
                rf'\b{re.escape(field_upper)}\b',
                rf'\b{re.escape(field_camel)}\b',
                
                # In quotes
                rf'["\']({re.escape(field)})["\']',
                rf'["\']({re.escape(field_lower)})["\']',
                rf'["\']({re.escape(field_upper)})["\']',
                
                # HTML attributes
                rf'name\s*=\s*["\']({re.escape(field)})["\']',
                rf'name\s*=\s*["\']({re.escape(field_lower)})["\']',
                rf'id\s*=\s*["\']({re.escape(field)})["\']',
                rf'id\s*=\s*["\']({re.escape(field_lower)})["\']',
                
                # PHP arrays
                rf'\$columns\s*\[\s*["\']({re.escape(field)})["\']\s*\]',
                rf'\$columns\s*\[\s*["\']({re.escape(field_lower)})["\']\s*\]',
                rf'\$_REQUEST\s*\[\s*["\']({re.escape(field)})["\']\s*\]',
                rf'\$_REQUEST\s*\[\s*["\']({re.escape(field_lower)})["\']\s*\]',
                rf'\$_POST\s*\[\s*["\']({re.escape(field)})["\']\s*\]',
                rf'\$_POST\s*\[\s*["\']({re.escape(field_lower)})["\']\s*\]',
            ]
            
            found = False
            for pattern in field_patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    found = True
                    break
            
            if not found:
                missing_fields.append(field)
        
        if missing_fields:
            if len(missing_fields) > len(expected_fields) * 0.5:
                # More than 50% missing = critical
                result['valid'] = False
                result['errors'].append(
                    f"Missing {len(missing_fields)}/{len(expected_fields)} required fields: {', '.join(missing_fields[:5])}"
                )
            else:
                # Less than 50% missing = warning
                result['warnings'].append(
                    f"Some fields missing: {', '.join(missing_fields)}"
                )
        
        return result

    def _validate_field_contract(self, code: str) -> Dict:
        """
        Enforce strict contract rules:
        - no extra business fields
        - control type matches requested field type
        - security escaping is present for rendered values
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        field_contract = self.expected_patterns.get('field_contract') or []
        if not field_contract:
            return result

        expected_names = {item.get('name', '').lower() for item in field_contract if item.get('name')}
        form_scope_match = re.search(
            r'<form\b[^>]*(?:id|name)\s*=\s*["\']frm["\'][^>]*>[\s\S]*?</form>',
            code,
            re.IGNORECASE
        )
        scoped_code = form_scope_match.group(0) if form_scope_match else code
        rendered_names = set(
            match.lower()
            for match in re.findall(
                r'<(?:input|select|textarea)[^>]*\bname=["\']([A-Za-z_][A-Za-z0-9_]*)["\']',
                scoped_code,
                re.IGNORECASE
            )
        )
        allowed_extras = {
            'action',
            'major',
            'deletecase',
            'txtmode',
            'ctrl_hid_value',
            'comp_code',
            'user_id',
            'login_id',
            'txtcountacc',
            'case_type',
            'created_by',
            'created_date',
            'updated_by',
            'updated_date',
            'btnsave',
            'btnreset',
            'btnedit',
            'btndelete',
            'btnprint',
        }
        def normalize_rendered_name(name: str) -> str:
            return re.sub(r'(?:_?\d+)$', '', name.strip().lower())

        extra_fields = sorted(
            name for name in rendered_names
            if name not in expected_names
            and normalize_rendered_name(name) not in expected_names
            and name not in allowed_extras
        )
        if extra_fields:
            threshold = max(3, int(len(expected_names) * 0.35))
            if len(extra_fields) > threshold:
                result['warnings'].append(
                    "Additional non-contract fields detected (allowed for enterprise scaffolding): "
                    + ', '.join(extra_fields[:6])
                )
            else:
                result['warnings'].append(
                    f"Potential extra fields found outside the contract: {', '.join(extra_fields[:6])}"
                )

        for item in field_contract:
            field_name = item.get('name', '')
            if not field_name:
                continue

            section = str(item.get('section') or '').strip().lower()
            is_detail_field = section in {'detail', 'grid', 'child', 'line'}
            scoped_name_pattern = (
                rf'{re.escape(field_name)}(?:_?\d+)?'
                if is_detail_field
                else re.escape(field_name)
            )

            input_type = str(item.get('input_type', '') or '').lower()
            db_type = str(item.get('db_type', '') or '').lower()

            if 'select' in input_type or 'dropdown' in input_type:
                if not re.search(rf'<select[^>]*\bname=["\']{scoped_name_pattern}["\']', scoped_code, re.IGNORECASE):
                    result['valid'] = False
                    result['errors'].append(f"Field '{field_name}' must render as a dropdown/select.")
            elif 'checkbox' in input_type or 'boolean' in db_type or 'tinyint(1)' in db_type:
                if not re.search(rf'<input[^>]*type=["\']checkbox["\'][^>]*\bname=["\']{scoped_name_pattern}["\']', scoped_code, re.IGNORECASE):
                    result['valid'] = False
                    result['errors'].append(f"Field '{field_name}' must render as a checkbox.")
            elif re.search(r'\bint\b|\binteger\b|\bbigint\b|\bsmallint\b', db_type):
                numeric_ok = bool(
                    re.search(rf'<input[^>]*type=["\']number["\'][^>]*\bname=["\']{scoped_name_pattern}["\']', scoped_code, re.IGNORECASE)
                    or re.search(rf'<input[^>]*\bname=["\']{scoped_name_pattern}["\'][^>]*isNumberKey', scoped_code, re.IGNORECASE)
                )
                if not numeric_ok:
                    result['warnings'].append(f"Field '{field_name}' is integer-like and should prefer a numeric input.")
            else:
                text_like_ok = bool(
                    re.search(rf'<input[^>]*\bname=["\']{scoped_name_pattern}["\']', scoped_code, re.IGNORECASE)
                    or re.search(rf'<textarea[^>]*\bname=["\']{scoped_name_pattern}["\']', scoped_code, re.IGNORECASE)
                )
                if not text_like_ok:
                    result['valid'] = False
                    result['errors'].append(f"Field '{field_name}' must render as a text-like input control.")

        expected_field_vars = {
            item.get('name', '').strip().lower()
            for item in field_contract
            if item.get('name')
        }
        unsafe_echo_bodies = []
        for match in re.finditer(r'<\?=\s*(.*?)\s*\?>', code, re.IGNORECASE | re.DOTALL):
            echo_body = (match.group(1) or '').strip()
            echo_body_lower = echo_body.lower()
            if 'htmlspecialchars(' in echo_body_lower:
                continue
            if '$_request[' in echo_body_lower or '$_post[' in echo_body_lower or '$_get[' in echo_body_lower:
                unsafe_echo_bodies.append(echo_body)
                continue
            if re.match(r'\$[A-Za-z_][A-Za-z0-9_]*$', echo_body):
                variable_name = echo_body[1:].lower()
                if variable_name in expected_field_vars:
                    unsafe_echo_bodies.append(echo_body)
        if unsafe_echo_bodies:
            result['warnings'].append(
                "Detected inline output without htmlspecialchars(...). "
                "Prefer escaping rendered dynamic field values."
            )
        elif self.strict_security_rules and 'htmlspecialchars(' not in code.lower():
            result['warnings'].append(
                "No htmlspecialchars(...) usage detected. Ensure dynamic outputs are escaped where user data is rendered."
            )

        return result

    def _validate_master_detail_structure(self, code: str) -> Dict:
        """Validate strict master-detail separation and required detail flow."""
        result = {'valid': True, 'errors': [], 'warnings': []}
        detail_table = str(self.expected_patterns.get('detail_table') or '').strip()
        detail_fields = [str(field or '').strip() for field in self.expected_patterns.get('detail_field_names', []) if str(field or '').strip()]
        master_table = str(self.expected_patterns.get('table_name') or '').strip()
        code_lower = (code or '').lower()

        if not detail_table:
            return result

        if not master_table or master_table.lower() == detail_table.lower():
            result['valid'] = False
            result['errors'].append("Master/detail tables are missing or conflated.")
            return result

        if detail_table.lower() not in code_lower:
            result['valid'] = False
            result['errors'].append(f"Detail table '{detail_table}' is missing in generated code.")

        if not re.search(r'name\s*=\s*["\']TXTCOUNTACC["\']', code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append("Missing TXTCOUNTACC hidden/input field for detail row count.")
        elif not re.search(
            r'<input[^>]*type\s*=\s*["\']hidden["\'][^>]*name\s*=\s*["\']TXTCOUNTACC["\']',
            code,
            re.IGNORECASE
        ):
            result['valid'] = False
            result['errors'].append("TXTCOUNTACC must be rendered as hidden input in master-detail forms.")

        loop_ok = bool(
            re.search(
                r'\$count\s*=\s*\$_(?:REQUEST|POST)\s*\[\s*["\']TXTCOUNTACC["\']\s*\].*?for\s*\(\s*\$i\s*=\s*1\s*;[\s\S]{0,300}?\$i\+\+',
                code,
                re.IGNORECASE
            )
        )
        if not loop_ok:
            loop_ok = bool(
                re.search(r'TXTCOUNTACC', code, re.IGNORECASE)
                and re.search(r'for\s*\(\s*\$i\s*=\s*(?:0|1)\s*;[\s\S]{0,200}?\$i\+\+', code, re.IGNORECASE)
            )
        if not loop_ok:
            result['valid'] = False
            result['errors'].append("Missing detail insert loop driven by TXTCOUNTACC.")

        has_detail_delete = bool(
            re.search(
                rf'db_delete\s*\(\s*(?:["\']{re.escape(detail_table)}["\']|\$?detail_table)',
                code,
                re.IGNORECASE
            )
        )
        has_detail_insert = bool(
            re.search(
                rf'db_insert\s*\(\s*["\']{re.escape(detail_table)}["\']',
                code,
                re.IGNORECASE
            )
        )
        update_has_delete_reinsert = has_detail_delete and has_detail_insert
        if not update_has_delete_reinsert:
            result['valid'] = False
            result['errors'].append("Master-detail update flow must delete old detail rows and reinsert.")

        if detail_fields:
            field_contract = self.expected_patterns.get('field_contract') or []
            master_field_names = {
                str(item.get('name') or '').strip().lower()
                for item in field_contract
                if isinstance(item, dict) and str(item.get('section') or '').strip().lower() == 'master'
            }
            shared_key_allowlist = {
                str(self.expected_patterns.get('primary_key') or '').strip().lower()
            }
            detail_only_fields = [
                field for field in detail_fields
                if field.lower() not in master_field_names and field.lower() not in shared_key_allowlist
            ]

            leaked_fields = set()
            columns_blocks = list(
                re.finditer(
                    r'\$columns\s*=\s*\[(?P<body>[\s\S]*?)\]\s*;',
                    code,
                    re.IGNORECASE
                )
            )
            for block in columns_blocks:
                block_tail = code[block.end(): block.end() + 220]
                is_master_columns = bool(
                    re.search(
                        rf'db_(?:insert|update)\s*\(\s*(?:["\']{re.escape(master_table)}["\']|\$table)\s*,\s*\$columns',
                        block_tail,
                        re.IGNORECASE
                    )
                )
                if not is_master_columns:
                    continue
                body_text = block.group('body') or ''
                body_keys = {
                    str(match.group(1) or '').strip().lower()
                    for match in re.finditer(
                        r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*=>',
                        body_text,
                        re.IGNORECASE
                    )
                    if str(match.group(1) or '').strip()
                }
                body_keys.update({
                    str(match.group(1) or '').strip().lower()
                    for match in re.finditer(
                        r'(?<![\$\'"\w])([A-Za-z_][A-Za-z0-9_]*)\s*=>',
                        body_text,
                        re.IGNORECASE
                    )
                    if str(match.group(1) or '').strip()
                })
                for field in detail_only_fields:
                    if field.lower() in body_keys:
                        leaked_fields.add(field)
            if leaked_fields:
                result['valid'] = False
                result['errors'].append(
                    "Detail fields leaked into master insert context: " + ', '.join(sorted(leaked_fields))
                )

        return result
    
    def _validate_ajax_parameter(self, code: str) -> Dict:
        """
        âœ… V-1: AJAX parameter validation
        CRITICAL: Must use correct AJAX parameter name
        """
        result = {'valid': True, 'errors': []}
        
        expected_param = self.expected_patterns['ajax_param']
        if not expected_param:
            return result
        
        # Check for AJAX parameter in code
        # Pattern: {Action:'GetMaxID', SelectArea: SelectArea}
        ajax_pattern = rf'\{{[^}}]*Action\s*:\s*["\']GetMaxID["\'][^}}]*({expected_param})\s*:'
        
        if not re.search(ajax_pattern, code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append(
                f"AJAX parameter '{expected_param}' not found in GetMaxID call. "
                f"Must pass parent dropdown value to AJAX."
            )
        
        return result
    
    def _validate_code_length(self, code: str) -> Dict:
        """
        âœ… V-1: Hierarchical code length validation
        MAJOR: Should use correct digit count (2 vs 4)
        """
        result = {'valid': True, 'errors': []}
        
        expected_length = self.expected_patterns['code_length']
        if not expected_length:
            return result
        
        # Check for LPAD pattern
        # Pattern: LPAD(MAX(RIGHT(Code,2)), 2, '0')
        lpad_pattern = r'LPAD\s*\(\s*MAX\s*\(\s*RIGHT\s*\(\s*Code\s*,\s*(\d+)\s*\)\s*\)'
        
        match = re.search(lpad_pattern, code, re.IGNORECASE)
        if match:
            actual_length = int(match.group(1))
            if actual_length != expected_length:
                result['valid'] = False
                result['errors'].append(
                    f"Code length mismatch: using {actual_length} digits, expected {expected_length} digits. "
                    f"This will generate wrong code format (e.g., LHR-0001 vs LHR-01)."
                )
        else:
            result['errors'].append(
                f"Hierarchical code pattern not found. Expected LPAD(MAX(RIGHT(Code,{expected_length})))."
            )
            result['valid'] = False
        
        return result
    
    def _validate_predelete_checks(self, code: str) -> Dict:
        """
        âœ… V-1: Pre-delete checks validation
        MAJOR: Should check all specified tables
        """
        result = {'valid': True, 'errors': []}
        
        expected_tables = self.expected_patterns['pre_delete_tables']
        if not expected_tables:
            return result
        
        missing_tables = []
        for table in expected_tables:
            # Check for getrows2 call with this table
            # Pattern: getrows2("tblcustomer", ...)
            predelete_pattern = rf'getrows2?\s*\(\s*["\']({table})["\']'
            
            if not re.search(predelete_pattern, code, re.IGNORECASE):
                missing_tables.append(table)
        
        if missing_tables:
            result['valid'] = False
            result['errors'].append(
                f"Missing pre-delete checks for {len(missing_tables)} tables: {', '.join(missing_tables)}. "
                f"Must check dependencies before deletion."
            )
        
        return result

    def _extract_first_form_opening_tag(self, code: str) -> Optional[str]:
        text = code or ''
        match = re.search(r'<form\b', text, re.IGNORECASE)
        if not match:
            return None

        start = match.start()
        idx = match.end()
        in_single = False
        in_double = False
        in_php = False
        escape_next = False

        while idx < len(text):
            ch = text[idx]
            nxt = text[idx + 1] if idx + 1 < len(text) else ''

            if in_php:
                if ch == '?' and nxt == '>':
                    in_php = False
                    idx += 2
                    continue
                idx += 1
                continue

            if in_single:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == "'":
                    in_single = False
                idx += 1
                continue

            if in_double:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '"':
                    in_double = False
                idx += 1
                continue

            if ch == '<' and nxt == '?':
                in_php = True
                idx += 2
                continue

            if ch == "'":
                in_single = True
                idx += 1
                continue

            if ch == '"':
                in_double = True
                idx += 1
                continue

            if ch == '>':
                return text[start:idx + 1]

            idx += 1

        return None

    def _has_malformed_form_opening_suffix(self, code: str) -> bool:
        text = code or ''
        opening_tag = self._extract_first_form_opening_tag(text)
        if not opening_tag:
            return False

        start = text.lower().find(opening_tag.lower())
        if start < 0:
            start = text.find(opening_tag)
        if start < 0:
            return False

        idx = start + len(opening_tag)
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text) or text[idx] not in ("'", '"'):
            return False
        idx += 1
        while idx < len(text) and text[idx].isspace():
            idx += 1
        return idx < len(text) and text[idx] == '>'

    def _validate_enterprise_requirements(self, code: str) -> Dict:
        """
        Enterprise hard checks for production-ready inline PHP output.
        These checks ensure shared layout/scripts and mandatory company flows exist.
        
        NOTE: Some of these patterns are AUTO-INJECTED by production hardening
        (in inline_php_generator.py), so we check if the hardening was applied.
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        code_lower = (code or '').lower()

        required_company_functions = ['db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue']
        missing_funcs = [func for func in required_company_functions if func not in code_lower]
        if missing_funcs:
            # Check if production hardening will inject these
            # The _inject_company_scope_columns and other methods handle this
            result['warnings'].extend(
                [f"Missing {func} - will be checked by production hardening" for func in missing_funcs]
            )
            # Don't block on missing DB functions - production hardening handles this
            # result['valid'] = False
            # result['errors'].append(
            #     "Missing required company DB helpers: " + ', '.join(missing_funcs)
            # )

        if 'funstarttran' not in code_lower or 'funendtran' not in code_lower:
            # Transaction handling can be injected by production hardening
            result['warnings'].append(
                "Transaction handling not detected - production hardening will verify/inject"
            )

        if 'fun_log(' not in code_lower:
            # Audit logging - production hardening verifies
            result['warnings'].append(
                "Audit logging (fun_log) not detected - production hardening will verify"
            )

        if 'comp_code' not in code_lower:
            # Multi-company filter - production hardening enforces
            result['warnings'].append(
                "Comp_Code filter not detected - production hardening will enforce"
            )

        if not re.search(r'(?:\$[A-Za-z_][A-Za-z0-9_]*\s*\[\s*[\'"]Comp_Code[\'"]\s*\])|(?:[\'"]Comp_Code[\'"]\s*=>)', code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append("Missing Comp_Code write-column assignment for db_insert/db_update operations.")

        if 'topmenu.php' not in code_lower:
            result['valid'] = False
            result['errors'].append("Missing shared header include (topmenu.php).")
        if ('sidemenu.php' not in code_lower) and ('rightmenu.php' not in code_lower):
            result['valid'] = False
            result['errors'].append("Missing shared sidebar include (sidemenu.php/rightmenu.php).")
        if 'footer.php' not in code_lower:
            result['valid'] = False
            result['errors'].append("Missing shared footer include (footer.php).")

        has_page_wrapper = bool(
            re.search(r'<div[^>]+class\s*=\s*["\'][^"\']*\bpage\b', code, re.IGNORECASE)
        )
        has_page_content = bool(
            re.search(r'class\s*=\s*["\'][^"\']*\bpage-content\b', code, re.IGNORECASE)
        )
        if not has_page_wrapper or not has_page_content:
            result['valid'] = False
            result['errors'].append("Missing company page container structure (page/page-content).")

        if not re.search(r'<form[^>]*form-horizontal', code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append("Form must use company layout class `form-horizontal`.")
        
        # FIX #3: Grid alignment check - WARN but don't block
        # Template already provides grid structure, so partial fields can still work
        has_grid = any([
            'control-label' in code_lower,
            re.search(r'col-(?:xs|sm|md|lg)-\d+', code, re.IGNORECASE),
            'form-group' in code_lower
        ])
        if not has_grid:
            result['warnings'].append(
                "Form labels/fields should follow company grid alignment (control-label + col-md-*). "
                "Verify grid classes are present."
            )

        if 'checkkeycode' not in code_lower:
            if self.expected_patterns.get('requires_keyboard_navigation'):
                result['valid'] = False
                result['errors'].append("Missing keyboard navigation handler checkKeycode(...).")
            else:
                result['warnings'].append(
                    "Keyboard navigation handler checkKeycode(...) was not detected."
                )

        if self.expected_patterns.get('requires_frontend_validation') and '.formvalidation(' not in code_lower and 'formvalidation.formvalidation(' not in code_lower:
            result['valid'] = False
            result['errors'].append("Missing frontend validation initialization (.formValidation).")

        has_delegated_events = bool(
            re.search(r'\.on\s*\(\s*[\'"][^\'"]+[\'"]\s*,\s*[\'"][^\'"]+[\'"]', code, re.IGNORECASE)
        )
        if not has_delegated_events:
            result['warnings'].append(
                "Delegated event bindings for dynamic DOM/AJAX pages were not detected."
            )

        has_reinit_guard = (
            '__companysharedinit' in code_lower or
            (('$(document)' in code_lower) and ('.off(' in code_lower) and ('.on(' in code_lower))
        )
        if not has_reinit_guard:
            result['warnings'].append(
                "Script reinitialization guard for AJAX navigation was not detected."
            )

        if re.search(r"['\"]action['\"]\s*\]\s*==\s*['\"]delete['\"]", code, re.IGNORECASE):
            has_dependency_check = bool(re.search(r'getrows2?\s*\(', code, re.IGNORECASE))
            if not has_dependency_check:
                result['valid'] = False
                result['errors'].append("Delete flow missing dependency checks (getrows/getrows2) before delete.")

        if re.search(r'mysql_fetch_(?:array|assoc|row)\s*\(\s*db_getRecord', code, re.IGNORECASE):
            result['warnings'].append(
                "db_getRecord() is wrapped in mysql_fetch_*; legacy company forms allow this, but direct usage is preferred."
            )

        primary_key = self.expected_patterns.get('primary_key')
        if primary_key:
            delete_block = re.search(
                r'if\s*\(\s*\$_REQUEST\[\s*[\'"](?:action|Action)[\'"]\s*\]\s*==\s*[\'"]Delete[\'"]\s*\)\s*\{(?P<body>[\s\S]{0,320}?)\}',
                code,
                re.IGNORECASE
            )
            if delete_block and primary_key.lower() not in delete_block.group('body').lower():
                result['warnings'].append(
                    f"Delete flow does not appear to use the requested primary key '{primary_key}'."
                )

        unique_fields = self.expected_patterns.get('unique_fields', [])
        if unique_fields:
            for field in unique_fields:
                has_unique_guard = (
                    f"{field} must be unique within comp_code".lower() in code_lower
                    or bool(re.search(rf'{re.escape(field)}[^\n]{{0,120}}count\(\*\)', code, re.IGNORECASE))
                    or bool(re.search(rf'count\(\*\)[\s\S]{{0,200}}{re.escape(field)}', code, re.IGNORECASE))
                )
                if not has_unique_guard:
                    result['valid'] = False
                    result['errors'].append(
                        f"Missing uniqueness validation for required field '{field}'."
                    )

        if self.expected_patterns.get('requires_email_validation'):
            has_email_validation = (
                'filter_var' in code_lower
                or ('preg_match' in code_lower and 'email' in code_lower)
                or ('regexp' in code_lower and 'email' in code_lower)
                or ('email' in code_lower and ('valid' in code_lower or 'check' in code_lower))
                or ('function' in code_lower and 'email' in code_lower)
            )
            has_email_field = 'email' in code_lower
            if not has_email_validation and has_email_field:
                result['warnings'].append("Consider adding email format validation.")

        numeric_field = self.expected_patterns.get('numeric_validation_field')
        if numeric_field:
            has_numeric_check = (
                f'is_numeric(${numeric_field})' in code_lower
                or f'is_numeric($_{numeric_field.lower()}' in code_lower
                or f'is_numeric($_REQUEST' in code_lower and numeric_field.lower() in code_lower
                or 'is_numeric' in code_lower and numeric_field.lower() in code_lower
            )
            has_numeric_field = numeric_field.lower() in code_lower
            if not has_numeric_check and has_numeric_field:
                result['warnings'].append(f"Consider adding numeric validation for {numeric_field}.")

        if ('select' in code_lower) and ('select2' not in code_lower):
            result['warnings'].append("Select elements detected without Select2 initialization.")

        strict_security_rules = bool(self.strict_security_rules)

        if re.search(
            (
                r'\$filter\s*=\s*["\'][^;\n]*'
                r'\.\s*(?:add(?:_slashes_new)?\s*\(\s*)?'
                r'\$_(?:REQUEST|GET|POST)\s*\['
            ),
            code,
            re.IGNORECASE
        ):
            msg = "Unsafe SQL filter concatenation detected. Use `$filter = \"... = ?\"` with params array."
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        has_update_delete = ('db_update(' in code_lower or 'db_delete(' in code_lower)
        has_supported_filter = bool(
            re.search(
                r'\$filter\s*=\s*["\'][^"\']*\?[^"\']*["\']',
                code,
                re.IGNORECASE
            )
            or re.search(
                r'db_update\s*\([^,\n]+,\s*[^,\n]+,\s*["\'][^"\']*\?[^"\']*["\']\s*,',
                code,
                re.IGNORECASE
            )
            or re.search(
                r'db_delete\s*\([^,\n]+,\s*["\'][^"\']*\?[^"\']*["\']\s*,',
                code,
                re.IGNORECASE
            )
            or re.search(
                r'\$filter\s*=\s*\[\s*["\'][A-Za-z_][A-Za-z0-9_]*["\']\s*=>',
                code,
                re.IGNORECASE
            )
            or re.search(
                r'\$filter\s*=\s*["\'][^"\']+["\']\s*;',
                code,
                re.IGNORECASE
            )
            or (
                bool(re.search(r'\$filter\s*=', code, re.IGNORECASE))
                and bool(re.search(r'db_update\s*\([^\n]*,\s*\$filter\s*\)', code, re.IGNORECASE))
            )
            or (
                bool(re.search(r'\$filter\s*=', code, re.IGNORECASE))
                and bool(re.search(r'db_delete\s*\([^\n]*,\s*\$filter\s*\)', code, re.IGNORECASE))
            )
        )
        if has_update_delete and not has_supported_filter:
            msg = "Missing supported `$filter` pattern for db_update/db_delete."
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        if re.search(r'<\?=\s*\$_(?:REQUEST|GET|POST)\s*\[', code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append(
                "Unescaped request variable echo detected. Wrap with htmlspecialchars(..., ENT_QUOTES, 'UTF-8')."
            )

        if re.search(r'\?>\s*\?>', code):
            result['valid'] = False
            result['errors'].append("Duplicate PHP closing tags detected.")

        if len(re.findall(r'function\s+maxid\s*\(', code, re.IGNORECASE)) > 1:
            result['valid'] = False
            result['errors'].append("Duplicate maxid() JavaScript function detected.")

        form_validation_init_count = len(
            re.findall(
                r'(?:\.formValidation|formValidation\.formValidation)\s*\(\s*\{',
                code,
                re.IGNORECASE
            )
        )
        if form_validation_init_count > 1:
            result['valid'] = False
            result['errors'].append("Duplicate formValidation initialization detected.")

        ajax_opens = len(re.findall(r'\$\.ajax\s*\(\s*\{', code, re.IGNORECASE))
        ajax_closes = len(re.findall(r'\}\s*\)\s*;', code, re.IGNORECASE))
        if ajax_opens > ajax_closes:
            result['valid'] = False
            result['errors'].append("Unclosed $.ajax({ ... }); block detected.")

        script_srcs = re.findall(r'<script[^>]*\bsrc=["\']([^"\']+)["\']', code, re.IGNORECASE)
        duplicate_script_srcs = sorted({src for src in script_srcs if script_srcs.count(src) > 1})
        if duplicate_script_srcs:
            duplicate_msg = "Duplicate script includes detected: " + ', '.join(duplicate_script_srcs[:5])
            vendor_script_prefixes = (
                'global/vendor/',
                'assets/examples/',
                'global/js/',
                'assets/js/',
            )
            non_vendor_duplicates = [
                src for src in duplicate_script_srcs
                if not src.lower().startswith(vendor_script_prefixes)
            ]
            if non_vendor_duplicates:
                result['valid'] = False
                result['errors'].append(duplicate_msg)
            else:
                result['warnings'].append(duplicate_msg)

        if re.search(r'action\s*=\s*["\']<\?=\$form2;\?>(?!["\'])', code, re.IGNORECASE):
            result['valid'] = False
            result['errors'].append("Malformed form action attribute (missing closing quote).")

        if re.search(
            r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']',
            code,
            re.IGNORECASE
        ):
            result['valid'] = False
            result['errors'].append("Malformed form.action JavaScript assignment (invalid PHP echo syntax).")

        if self._has_malformed_form_opening_suffix(code):
            result['valid'] = False
            result['errors'].append("Malformed form opening tag detected (stray quote after <form ...>).")

        if re.search(
            r'document\.onkeydown\s*=\s*checkKeycode\s*(?:\r?\n|\s)*\{',
            code,
            re.IGNORECASE
        ):
            result['valid'] = False
            result['errors'].append("Malformed document.onkeydown assignment detected.")

        if re.search(
            r'<script[^>]*\bsrc=["\'][^"\']+["\'][^>]*>\s*[^<\s]',
            code,
            re.IGNORECASE
        ):
            result['valid'] = False
            result['errors'].append("Inline JavaScript detected inside <script src=...> tag.")

        for maxid_match in re.finditer(r'function\s+maxid\s*\(\)\s*\{', code, re.IGNORECASE):
            maxid_window = code[maxid_match.start(): maxid_match.start() + 2500]
            if '$.ajax' in maxid_window and '});' not in maxid_window:
                result['valid'] = False
                result['errors'].append("Malformed maxid() AJAX block detected (missing closure).")
                break
            if (
                '$.ajax' in maxid_window
                and re.search(r"data\s*:\s*\{[^}]*Action\s*:\s*['\"]GetMaxID['\"]", maxid_window, re.IGNORECASE)
                and 'success:' not in maxid_window
                and '.done(' not in maxid_window
            ):
                result['valid'] = False
                result['errors'].append("maxid() AJAX block missing success callback handling.")
                break

        form_open_count = len(re.findall(r'<form\b', code, re.IGNORECASE))
        form_close_count = len(re.findall(r'</form>', code, re.IGNORECASE))
        if form_open_count != 1 or form_close_count != 1:
            result['valid'] = False
            result['errors'].append(
                f"Form structure invalid: expected exactly one <form> pair, found opens={form_open_count}, closes={form_close_count}."
            )

        if re.search(
            r'(?im)^\s*(?:\/\/\s*)?(?:rest\s+of\s+code\s+here|populate\s+options|todo\b|tbd\b|to\s+be\s+implemented|implement\s+this|placeholder\b)',
            code,
            re.IGNORECASE
        ) or re.search(r'(?i)(?:<\.\.\.|TODO:|FIXME:|TBD:)', code):
            msg = "Placeholder or truncated content detected."
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        forbidden_db_calls = re.findall(
            r'\b(?:mysql|mysqli)_(?:query|multi_query|fetch_array|fetch_assoc|fetch_row)\s*\(',
            code,
            re.IGNORECASE
        )
        if forbidden_db_calls:
            msg = "Forbidden mysql/mysqli database functions detected."
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        session_keys = re.findall(r'\$_SESSION\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]', code, re.IGNORECASE)
        if session_keys:
            allowed_session_keys = {'user_id', 'comp_code', 'login_id'}
            normalized_session_keys = {key.lower() for key in session_keys}
            unexpected_keys = sorted(normalized_session_keys - allowed_session_keys)
            if unexpected_keys and strict_security_rules:
                result['valid'] = False
                result['errors'].append(
                    "Non-standard session keys detected: " + ', '.join(unexpected_keys[:6])
                )

        contamination_tokens = [
            'customer_code',
            'supplier_code',
            'engineer_code',
            'main_area',
            'acc_code',
        ]
        request_context_tokens = {
            str(self.expected_patterns.get('table_name') or '').strip().lower(),
            str(self.expected_patterns.get('primary_key') or '').strip().lower(),
        }
        allowed_tables = {
            str(tbl).strip().lower()
            for tbl in self.expected_patterns.get('allowed_tables', [])
            if str(tbl).strip()
        }
        allowed_fields = {
            field.strip().lower()
            for field in self.expected_patterns.get('field_names', [])
            if field and field.strip()
        }
        allowed_fields.update({
            str(field.get('name') or '').strip().lower()
            for field in (self.expected_patterns.get('field_contract') or [])
            if str(field.get('name') or '').strip()
        })
        allowed_fields.update({
            str(field or '').strip().lower()
            for field in (self.expected_patterns.get('detail_field_names') or [])
            if str(field or '').strip()
        })
        allowed_fields.update(token for token in request_context_tokens if token)
        allowed_fields.update(allowed_tables)
        allowed_fields.update({'comp_code', 'user_id', 'login_id', 'action', 'txtcountacc'})

        safe_non_entity_tokens = set(COMPANY_HELPER_FIELD_IGNORE)
        safe_non_entity_tokens.update({
            'success', 'message', 'status', 'error', 'errors', 'result', 'data',
            'case_type', 'created_by', 'created_date', 'updated_by', 'updated_date',
            'maxid', 'getmaxid', 'id', 'name', 'code'
        })

        request_keys = re.findall(
            r'\$_(?:REQUEST|POST|GET)\s*\[\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*\]',
            code,
            re.IGNORECASE
        )
        form_keys = re.findall(
            r'(?:name|id)\s*=\s*[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]',
            code,
            re.IGNORECASE
        )
        column_keys = re.findall(
            r'[\'"]([A-Za-z_][A-Za-z0-9_]*)[\'"]\s*=>',
            code,
            re.IGNORECASE
        )
        unknown_contract_tokens = []
        for token in sorted(set(request_keys + form_keys + column_keys)):
            token_lower = token.lower()
            if token_lower in allowed_fields or token_lower in safe_non_entity_tokens:
                continue
            if (
                re.match(r'^[a-z]+_[a-z0-9_]+$', token_lower) and
                token_lower.endswith(('code', 'name', 'date', 'no', 'id', 'type'))
            ):
                unknown_contract_tokens.append(token_lower)
            elif (
                token_lower.startswith('tbl')
                and token_lower not in allowed_fields
                and token_lower not in allowed_tables
            ):
                unknown_contract_tokens.append(token_lower)

        leaked_tokens = [
            token for token in contamination_tokens
            if token in code_lower and token not in allowed_fields
        ]
        if leaked_tokens:
            msg = "Possible cross-entity contamination detected: " + ', '.join(sorted(set(leaked_tokens)))
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        if unknown_contract_tokens:
            msg = (
                "Unknown contract tokens detected (possible cross-entity contamination): "
                + ', '.join(sorted(set(unknown_contract_tokens)))
            )
            if strict_security_rules:
                result['valid'] = False
                result['errors'].append(msg)
            else:
                result['warnings'].append(msg)

        return result
