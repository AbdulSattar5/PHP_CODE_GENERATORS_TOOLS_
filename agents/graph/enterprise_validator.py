"""
Phase 2.2: EnterpriseValidator
Validates generated code against company standards and validation contract.

PHASE 3.1 INTEGRATION: Uses FailureTaxonomy for structured failure classification.
"""

import re
import logging
from typing import Dict, List, Tuple
from agents.utils.failure_taxonomy import FailureTaxonomy, FailureCategory

logger = logging.getLogger(__name__)


class EnterpriseValidator:
    """
    ✅ PHASE 2.2: ENTERPRISE VALIDATOR
    
    Responsibilities:
    1. Validate against validation contract (only check what was requested)
    2. Check company function usage
    3. Verify CRUD handlers exist
    4. Check field completeness
    5. Validate dependencies are checked
    6. Calculate completeness scores
    
    This class consolidates all validation logic from InlinePHPGenerator.
    """
    
    def __init__(self):
        self.last_validation_result = {}
        # PHASE 3.1: Initialize Failure Taxonomy
        self.taxonomy = FailureTaxonomy()
        logger.info("✅ EnterpriseValidator initialized with FailureTaxonomy")
    
    def validate(
        self,
        generated_code: str,
        validation_contract: Dict
    ) -> Tuple[bool, List[str], Dict]:
        """
        Validate generated code against validation contract.
        
        Args:
            generated_code: The assembled PHP code
            validation_contract: Contract defining what to validate
        
        Returns:
            (is_valid, errors, scores)
            - is_valid: True if code passes validation
            - errors: List of validation error messages
            - scores: Dict of completeness scores by section
        """
        logger.info("🔍 EnterpriseValidator: Starting validation...")
        
        errors = []
        scores = {}
        
        # 1. Validate company functions
        function_errors = self._validate_company_functions(
            generated_code,
            validation_contract.get('required_functions', [])
        )
        errors.extend(function_errors)
        
        # 2. Validate CRUD handlers
        handler_errors = self._validate_crud_handlers(
            generated_code,
            validation_contract.get('required_handlers', [])
        )
        errors.extend(handler_errors)
        
        # 3. Validate AJAX handlers
        ajax_errors = self._validate_ajax_handlers(
            generated_code,
            validation_contract.get('required_ajax', [])
        )
        errors.extend(ajax_errors)
        
        # 4. Validate fields
        field_errors, field_score = self._validate_fields(
            generated_code,
            validation_contract.get('required_fields', [])
        )
        errors.extend(field_errors)
        scores['fields'] = field_score
        
        # 5. Validate dependencies (if required)
        if validation_contract.get('required_dependencies'):
            dep_errors = self._validate_dependencies(
                generated_code,
                validation_contract['required_dependencies']
            )
            errors.extend(dep_errors)
        
        # 6. Validate FormValidation (if required)
        if validation_contract.get('required_validation'):
            validation_errors = self._validate_formvalidation(generated_code)
            errors.extend(validation_errors)

        # 6.5 Strict production checks (enabled by planner/runtime contract)
        if validation_contract.get('strict_production_checks'):
            safety_errors = self._validate_production_safety(
                generated_code,
                validation_contract
            )
            errors.extend(safety_errors)
        
        # 7. Calculate completeness scores
        scores['crud'] = self._calculate_crud_completeness(generated_code)
        scores['ajax'] = self._calculate_ajax_completeness(generated_code)
        scores['overall'] = self._calculate_overall_completeness(scores)
        
        is_valid = len(errors) == 0 and scores['overall'] >= 40
        
        # PHASE 3.1: Classify failure if validation failed
        failure_classification = None
        if not is_valid:
            failure_classification = self._classify_validation_failure(
                errors=errors,
                scores=scores,
                generated_code=generated_code
            )
            logger.info(f"🔍 Failure classified as: {failure_classification['category'].value}")
            logger.info(f"   Severity: {failure_classification['severity'].value}")
            logger.info(f"   Recovery: {failure_classification['recovery_strategy']}")
        
        self.last_validation_result = {
            'is_valid': is_valid,
            'errors': errors,
            'scores': scores,
            'failure_classification': failure_classification  # PHASE 3.1
        }
        
        if is_valid:
            logger.info(f"✅ Validation passed (score: {scores['overall']}%)")
        else:
            logger.warning(f"❌ Validation failed: {len(errors)} errors (score: {scores['overall']}%)")
        
        return is_valid, errors, scores
    
    def _get_php_code(self, sections: Dict[str, str]) -> str:
        """
        ✅ PROMPT 3 REQUIREMENT: Get all PHP code from sections for validation.
        
        NOTE: This method is provided per prompt specification, but in practice
        the validator receives 'assembled_code' (string) not 'sections' (dict).
        
        The code_assembler.py (Fix #2) already distributes php_logic into
        crud_operations and ajax_handlers before assembly, so the assembled_code
        string contains all PHP code merged together.
        
        This helper would be used if validator signature changes to accept sections.
        """
        return '\n'.join([
            sections.get('crud_operations', '') or '',
            sections.get('ajax_handlers', '') or '',
            sections.get('php_logic', '') or '',
            sections.get('php_variables', '') or '',
            sections.get('variable_init', '') or '',
        ])
    
    def _get_js_code(self, sections: Dict[str, str]) -> str:
        """
        ✅ PROMPT 3 REQUIREMENT: Get all JavaScript code from sections for validation.
        
        NOTE: This method is provided per prompt specification, but in practice
        the validator receives 'assembled_code' (string) not 'sections' (dict).
        
        This helper would be used if validator signature changes to accept sections.
        """
        return '\n'.join([
            sections.get('entity_js', '') or '',
            sections.get('head_scripts', '') or '',
        ])
    
    def _validate_company_functions(
        self,
        code: str,
        required_functions: List[str]
    ) -> List[str]:
        """
        Validate that required company functions are used.
        
        ✅ FIX #3: Validator receives COMPLETE ASSEMBLED CODE from CodeAssembler.
        
        The code parameter contains ALL sections merged together:
        - php_logic + crud_operations + ajax_handlers (merged by CodeAssembler)
        - form_fields (merged by template)
        - entity_js + validation_rules (merged by template)
        
        Fix #2 in code_assembler.py ensures crud_operations and ajax_handlers
        are populated from php_logic before merging, so validator sees complete code.
        
        Returns list of error messages.
        """
        errors = []
        
        for func in required_functions:
            if func not in code:
                errors.append(f"Missing required company function: {func}()")
        
        return errors
    
    def _validate_crud_handlers(
        self,
        code: str,
        required_handlers: List[str]
    ) -> List[str]:
        """
        Validate that CRUD handlers exist.
        
        Checks for: Save, Update, Delete, Edit handlers
        
        FIX #2: REAL FIX - Flexible CRUD handler detection
        The validator receives COMPLETE ASSEMBLED CODE (all sections merged).
        
        PROBLEM: Previous pattern was too strict:
        - Only matched: Action == 'Save' or case 'Save':
        - Missed: $_REQUEST['Action'] == 'Save'
        - Missed: isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Save'
        
        SOLUTION: Check multiple patterns for real-world PHP code
        """
        errors = []
        code_lower = code.lower()
        
        for handler in required_handlers:
            handler_variants = sorted({str(handler or '').strip(), str(handler or '').strip().lower()}, key=len, reverse=True)
            # FIX #2: Check multiple CRUD handler patterns
            patterns = []
            for variant in handler_variants:
                patterns.extend([
                    # Pattern 1: case 'save': or case "Save":
                    rf"case\s+['\"]?{variant}['\"]?\s*:",

                    # Pattern 2: Action == 'Save' / === / lowercase variants
                    rf"['\"]?Action['\"]?\s*={2,3}\s*['\"]?{variant}['\"]?",

                    # Pattern 3: $_REQUEST['Action'] == 'Save'
                    rf"\$_REQUEST\s*\[\s*['\"](?:Action|action)['\"]\s*\]\s*={2,3}\s*['\"]?{variant}['\"]?",

                    # Pattern 4: $_POST['Action'] == 'Save'
                    rf"\$_POST\s*\[\s*['\"](?:Action|action)['\"]\s*\]\s*={2,3}\s*['\"]?{variant}['\"]?",

                    # Pattern 5: isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Save'
                    rf"isset\s*\(\s*\$_REQUEST\s*\[\s*['\"](?:Action|action)['\"]\s*\]\s*\)\s*&&\s*\$_REQUEST\s*\[\s*['\"](?:Action|action)['\"]\s*\]\s*={2,3}\s*['\"]?{variant}['\"]?",

                    # Pattern 6: normalized action variable: $action === 'save'
                    rf"\$action\s*={2,3}\s*['\"]{variant}['\"]",
                ])
            
            found = False
            for pattern in patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    found = True
                    break

            if not found:
                handler_key = str(handler or '').strip().lower()
                handler_db_markers = {
                    'save': 'db_insert(',
                    'update': 'db_update(',
                    'delete': 'db_delete(',
                    'edit': 'db_getrecord(',
                }
                expected_db_marker = handler_db_markers.get(handler_key)
                action_source_detected = any(
                    marker in code_lower
                    for marker in (
                        '$action',
                        "$_post['action']",
                        '$_post["action"]',
                        "$_request['action']",
                        '$_request["action"]',
                        'switch ($_post',
                        'switch($_post',
                        'switch ($_request',
                        'switch($_request',
                    )
                )
                if expected_db_marker and expected_db_marker in code_lower and handler_key in code_lower and action_source_detected:
                    found = True
            
            if not found:
                errors.append(f"Missing CRUD handler: {handler}")
        
        return errors
    
    def _validate_ajax_handlers(
        self,
        code: str,
        required_ajax: List[str]
    ) -> List[str]:
        """
        Validate that AJAX handlers exist.
        
        Checks for: GetMaxID, cascading dropdowns, etc.
        """
        errors = []
        
        for ajax_handler in required_ajax:
            patterns = [
                rf'case\s+["\']?{ajax_handler}["\']?\s*:',
                rf'["\']?Action["\']?\s*==\s*["\']?{ajax_handler}["\']?',
                rf'\$_REQUEST\s*\[\s*["\']Action["\']\s*\]\s*==\s*["\']?{ajax_handler}["\']?',
                rf'\$_REQUEST\s*\[\s*["\']action["\']\s*\]\s*==\s*["\']?{ajax_handler}["\']?',
                rf'isset\s*\(\s*\$_REQUEST\s*\[\s*["\'](?:Action|action)["\']\s*\]\s*\)\s*&&\s*\$_REQUEST\s*\[\s*["\'](?:Action|action)["\']\s*\]\s*==\s*["\']?{ajax_handler}["\']?',
            ]
            if not any(re.search(pattern, code, re.IGNORECASE) for pattern in patterns):
                errors.append(f"Missing AJAX handler: {ajax_handler}")
        
        return errors
    
    def _validate_fields(
        self,
        code: str,
        required_fields: List[str]
    ) -> Tuple[List[str], int]:
        """
        Validate that required fields are present in form.
        
        Returns (errors, completeness_score)
        """
        errors = []
        found_count = 0
        
        for field in required_fields:
            # Check for field in HTML (name= or id=)
            pattern = rf'(?:name|id)\s*=\s*["\']?{field}["\']?'
            if re.search(pattern, code, re.IGNORECASE):
                found_count += 1
            else:
                errors.append(f"Missing form field: {field}")
        
        # Calculate completeness score
        if required_fields:
            score = int((found_count / len(required_fields)) * 100)
        else:
            score = 100
        
        return errors, score
    
    def _validate_dependencies(
        self,
        code: str,
        required_dependencies: List[Dict]
    ) -> List[str]:
        """
        Validate that pre-delete dependency checks exist.
        
        Checks for getrows() calls before db_delete()
        """
        errors = []
        code_lower = code.lower()
        getrows_windows = [
            code_lower[m.start(): m.start() + 700]
            for m in re.finditer(r'getrows\s*\(', code_lower, re.IGNORECASE)
        ]

        for dep in required_dependencies:
            table = str(dep.get('table', '') or '').strip()
            field = str(dep.get('field', '') or '').strip()
            if not table or not field:
                continue

            table_lower = table.lower()
            field_lower = field.lower()
            has_dep_check = any(
                table_lower in window and field_lower in window
                for window in getrows_windows
            )
            if not has_dep_check:
                errors.append(f"Missing pre-delete check for {table}.{field}")

        return errors
    
    def _validate_formvalidation(self, code: str) -> List[str]:
        """
        Validate that FormValidation is properly configured.
        
        Checks for:
        - formValidation() initialization
        - .addField() calls
        - validators configuration
        """
        errors = []

        has_formvalidation_init = 'formValidation' in code
        has_company_validation_fields = (
            'window.companyValidationFields' in code
            or re.search(r'companyValidationFields\s*=', code, re.IGNORECASE) is not None
        )

        if not has_formvalidation_init:
            errors.append("Missing FormValidation initialization")
        
        has_add_field = '.addField(' in code
        has_fields_object = bool(re.search(r'fields\s*:\s*\{', code, re.IGNORECASE))
        if not has_add_field and not has_fields_object and not has_company_validation_fields:
            errors.append("Missing FormValidation field definitions")
        
        return errors

    def _validate_production_safety(self, code: str, validation_contract: Dict) -> List[str]:
        """
        Strict anti-pattern checks for production blocking issues.
        """
        errors: List[str] = []
        code_lower = code.lower()

        if re.search(
            r'\$filter\s*=\s*["\'][^;\n]*\.\s*\$_(?:REQUEST|POST|GET)',
            code,
            re.IGNORECASE
        ) and not re.search(
            r'\$filter\s*=\s*["\'][^;\n]*\.\s*(?:add(?:_slashes_new)?\s*\()?\s*\$_(?:REQUEST|POST|GET)',
            code,
            re.IGNORECASE
        ):
            errors.append("Unsafe SQL filter concatenation detected. Wrap request values with add(...).")

        has_update_delete = ('db_update(' in code_lower or 'db_delete(' in code_lower)
        has_parameterized_filter = bool(
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
        if has_update_delete and not has_parameterized_filter:
            errors.append("Missing `$filter` pattern for update/delete flow.")

        if re.search(r'<\?=\s*\$_(?:REQUEST|GET|POST)\s*\[', code, re.IGNORECASE):
            errors.append("Unescaped request echo detected. Use htmlspecialchars(..., ENT_QUOTES, 'UTF-8').")

        if re.search(r'\?>\s*\?>', code):
            errors.append("Duplicate PHP closing tags detected.")

        if re.search(r'action\s*=\s*["\']<\?=\$form2;\?>(?!["\'])', code, re.IGNORECASE):
            errors.append("Malformed form action attribute detected (missing closing quote).")

        if re.search(
            r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']',
            code,
            re.IGNORECASE
        ):
            errors.append("Malformed form.action JavaScript assignment detected (invalid PHP echo syntax).")

        if len(re.findall(r'function\s+maxid\s*\(', code, re.IGNORECASE)) > 1:
            errors.append("Duplicate JavaScript maxid() function definitions detected.")

        placeholder_match = re.search(
            r'(?im)^\s*(?:\/\/\s*)?(?:rest\s+of\s+code\s+here|populate\s+options|todo\b|tbd\b|to\s+be\s+implemented|implement\s+this|placeholder\b)',
            code,
            re.IGNORECASE
        ) or re.search(
            r'(?i)(?:<\.\.\.|TODO:|FIXME:|TBD:)',
            code
        )
        if placeholder_match:
            matched_text = placeholder_match.group(0).strip().replace('\n', ' ')
            logger.warning("⚠️ Placeholder marker detected by production safety rule: %s", matched_text[:120])
            errors.append("Placeholder/truncated content detected in generated output.")

        required_fields = {
            str(field).strip().lower()
            for field in (validation_contract.get('required_fields') or [])
            if str(field).strip()
        }
        contamination_tokens = [
            'acc_code',
            'customer_code',
            'supplier_code',
            'engineer_code',
            'main_area',
            'saleman_code',
            'salesman_code',
        ]
        sensitive_line_markers = (
            '$_request',
            '$_post',
            '$_get',
            'name=',
            'id=',
            '=>',
            'db_insert',
            'db_update',
            'db_delete',
            'db_getrecord',
            'getrows',
            'getvalue',
            'where ',
            'select ',
        )
        leaked = []
        for token in contamination_tokens:
            if token in required_fields:
                continue
            if token not in code_lower:
                continue
            for line in code.splitlines():
                line_lower = line.lower()
                if token in line_lower and any(marker in line_lower for marker in sensitive_line_markers):
                    leaked.append(token)
                    break
        if leaked:
            errors.append(
                "Possible cross-entity contamination detected: " + ', '.join(sorted(set(leaked)))
            )

        return errors
    
    def _calculate_crud_completeness(self, code: str) -> int:
        """
        Calculate CRUD completeness score (0-100%).
        
        Checks for:
        - Save handler
        - Update handler
        - Delete handler
        - Edit handler
        - db_insert usage
        - db_update usage
        - db_delete usage
        - db_getRecord usage
        """
        checks = [
            ('Save handler', r'case\s+["\']?Save["\']?:|Action\s*==\s*["\']?Save["\']?'),
            ('Update handler', r'case\s+["\']?Update["\']?:|Action\s*==\s*["\']?Update["\']?'),
            ('Delete handler', r'case\s+["\']?Delete["\']?:|Action\s*==\s*["\']?Delete["\']?'),
            ('Edit handler', r'case\s+["\']?Edit["\']?:|Action\s*==\s*["\']?Edit["\']?'),
            ('db_insert', r'db_insert\s*\('),
            ('db_update', r'db_update\s*\('),
            ('db_delete', r'db_delete\s*\('),
            ('db_getRecord', r'db_getRecord\s*\(')
        ]
        
        found = sum(1 for name, pattern in checks if re.search(pattern, code, re.IGNORECASE))
        return int((found / len(checks)) * 100)
    
    def _calculate_ajax_completeness(self, code: str) -> int:
        """
        Calculate AJAX completeness score (0-100%).
        
        Checks for:
        - GetMaxID handler
        - AJAX response (echo/JSON)
        - JavaScript maxid() function
        - $.ajax or $.post calls
        """
        checks = [
            ('GetMaxID handler', r'case\s+["\']?GetMaxID["\']?:|Action\s*==\s*["\']?GetMaxID["\']?'),
            ('AJAX response', r'echo\s+[^;]+;|json_encode'),
            ('maxid function', r'function\s+maxid\s*\('),
            ('AJAX call', r'\$\.(?:ajax|post)\s*\(')
        ]
        
        found = sum(1 for name, pattern in checks if re.search(pattern, code, re.IGNORECASE))
        return int((found / len(checks)) * 100)
    
    def _calculate_overall_completeness(self, scores: Dict[str, int]) -> int:
        """
        Calculate overall completeness score.
        
        Weighted average of all section scores.
        """
        weights = {
            'crud': 0.4,
            'ajax': 0.2,
            'fields': 0.4
        }
        
        total = 0
        weight_sum = 0
        
        for section, weight in weights.items():
            if section in scores:
                total += scores[section] * weight
                weight_sum += weight
        
        if weight_sum > 0:
            return int(total / weight_sum)
        return 0
    
    def get_last_validation_result(self) -> Dict:
        """Get the last validation result"""
        return self.last_validation_result
    
    def _classify_validation_failure(
        self,
        errors: List[str],
        scores: Dict[str, int],
        generated_code: str
    ) -> Dict:
        """
        PHASE 3.1: Classify validation failure using FailureTaxonomy.
        
        Returns failure classification with category, severity, and recovery strategy.
        """
        # Build error context for taxonomy
        error_message = " | ".join(errors[:5])  # First 5 errors
        
        # Add score context
        score_context = f"Overall score: {scores.get('overall', 0)}% | " \
                       f"CRUD: {scores.get('crud', 0)}% | " \
                       f"AJAX: {scores.get('ajax', 0)}% | " \
                       f"Fields: {scores.get('fields', 0)}%"
        
        # Classify using taxonomy
        classification = self.taxonomy.classify_failure(
            error_message=error_message,
            validation_errors=errors,
            log_context=score_context,
            generated_code=generated_code[:1000]  # First 1000 chars
        )
        
        return classification
