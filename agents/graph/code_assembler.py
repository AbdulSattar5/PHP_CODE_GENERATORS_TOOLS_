"""
Phase 2.2: CodeAssembler
Assembles final PHP code from generated sections and company template.
"""

import json
import os
import re
import tempfile
import logging
from collections import Counter
from typing import Dict, List, Optional

from agents.utils.company_form_blueprint import CompanyFormBlueprint

logger = logging.getLogger(__name__)


class CodeAssembler:
    """
    ✅ PHASE 2.2: CODE ASSEMBLER
    
    Responsibilities:
    1. Parse LLM-generated sections
    2. Merge sections with company template
    3. Inject framework components (CSS, scripts, HTML wrapper)
    4. Auto-repair missing critical blocks
    5. Assemble final PHP file
    
    This class consolidates all assembly logic from InlinePHPGenerator.
    """
    
    def __init__(self, template=None):
        self.template = template
        self.last_assembled_code = ""
        self.blueprint = CompanyFormBlueprint.load_default()
    
    def assemble(
        self,
        generated_code: str,
        contract: Dict,
        fixed_parts: Dict = None
    ) -> str:
        """
        Assemble final PHP code from generated sections.
        
        ✅ FIX 3: Validate AFTER template merge (not before)
        
        Args:
            generated_code: LLM-generated code sections
            contract: Merged contract with metadata
            fixed_parts: Fixed framework parts from company template
        
        Returns:
            Complete assembled PHP file
        """
        raw_size = len(generated_code)
        logger.info(f"🔧 CodeAssembler: Starting assembly (raw LLM output: {raw_size} chars)...")
        
        # Parse generated sections
        sections = self._parse_sections(generated_code)
        
        # ✅ FIX #2: Distribute php_logic into empty crud_operations/ajax_handlers
        sections = self._distribute_php_logic(sections)
        
        # Auto-repair missing critical blocks
        sections = self._auto_repair(sections, contract)
        sections = self._sanitize_sections_with_contract(sections, contract)
        sections = self._dedupe_sections(sections)
        strict_contract = (contract or {}).get('strict_contract')
        strict_contract_mode = bool((contract or {}).get('strict_contract_mode'))
        if isinstance(strict_contract, dict):
            strict_contract_mode = strict_contract_mode or bool(strict_contract.get('valid'))
        elif strict_contract:
            strict_contract_mode = True

        template_ready = bool(self.template)
        if template_ready:
            if hasattr(self.template, 'is_loaded_and_usable'):
                template_ready = bool(self.template.is_loaded_and_usable())
            elif hasattr(self.template, '_loaded'):
                template_ready = bool(getattr(self.template, '_loaded'))
        
        fixed_parts = fixed_parts or {}

        # ✅ FIX 3: Merge with template FIRST
        if template_ready:
            assembled = self._merge_with_template(sections, contract)
            
            # Verify template merge was effective
            assembled_size = len(assembled)
            expected_template_size = max(
                9000,
                len(str(getattr(self.template, '_html_head', '') or ''))
                + len(str(getattr(self.template, '_body_start', '') or ''))
                + len(str(getattr(self.template, '_body_end', '') or ''))
            )
            size_increase = assembled_size - raw_size
            min_expected_increase = max(5000, int(expected_template_size * 0.55))
            
            logger.info(f"📊 Size verification:")
            logger.info(f"   - Raw LLM output: {raw_size:,} chars")
            logger.info(f"   - After template merge: {assembled_size:,} chars")
            logger.info(f"   - Size increase: {size_increase:,} chars")
            logger.info(f"   - Expected template size: ~{expected_template_size:,} chars")
            logger.info(f"   - Minimum acceptable increase: {min_expected_increase:,} chars")
            
            # If template merge didn't add significant size, something is wrong
            if size_increase < min_expected_increase:
                error_msg = (
                    f"❌ TEMPLATE MERGE INEFFECTIVE: "
                    f"Raw={raw_size} chars, Assembled={assembled_size} chars, "
                    f"Increase={size_increase} chars (expected ~{expected_template_size} chars, "
                    f"minimum acceptable {min_expected_increase} chars). "
                    f"Template merge may have failed or template is not loaded properly."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            logger.info(f"✅ Template merge verified: added {size_increase:,} chars")
        else:
            assembled = self._merge_manual(sections, contract, fixed_parts)
            if strict_contract_mode:
                logger.warning(
                    "⚠️ DynamicFormTemplate unavailable; strict mode using deterministic manual merge fallback"
                )
            else:
                logger.warning("⚠️ No template available - using manual merge")

        assembled = self._sanitize_rendered_dynamic_values(assembled)
        assembled = self._repair_known_form_action_patterns(assembled)
        assembled = self._repair_compound_if_db_patterns(assembled)
        assembled = self._enforce_company_contract_output(assembled, contract)
        self._trace_assembled_form_state(assembled, "post-merge")
        pre_dedupe = assembled
        assembled = self._dedupe_maxid_in_final_output(assembled)
        post_dedupe_diagnostics = self._collect_form_diagnostics(assembled)
        if (
            not post_dedupe_diagnostics.get('has_form')
            or int(post_dedupe_diagnostics.get('form_open_count') or 0) < 1
            or int(post_dedupe_diagnostics.get('form_close_count') or 0) < 1
        ):
            logger.warning("⚠️ maxid() dedupe degraded form structure; reverting to pre-dedupe output")
            assembled = pre_dedupe
        self._trace_assembled_form_state(assembled, "post-dedupe")
        
        # ✅ FIX 3: Assert required sections AFTER merge (not before)
        self._assert_required_sections_after_merge(assembled, contract, sections)
        
        self.last_assembled_code = assembled
        
        logger.info(f"✅ CodeAssembler: Assembly complete ({len(assembled):,} chars)")
        return assembled
    
    def _sanitize_rendered_dynamic_values(self, code: str) -> str:
        """
        Normalize raw PHP value echoes in rendered controls so strict
        validation sees one escaped output shape.
        """
        rendered = str(code or '')
        if not rendered:
            return rendered

        original = rendered

        def _wrap_short_echo_value(match):
            expression = str(match.group(1) or '').strip()
            if not expression or 'htmlspecialchars(' in expression.lower():
                return match.group(0)
            return f'value="<?=htmlspecialchars({expression}, ENT_QUOTES);?>"'

        def _wrap_php_echo_value(match):
            expression = str(match.group(1) or '').strip()
            if not expression or 'htmlspecialchars(' in expression.lower():
                return match.group(0)
            return f'value="<?php echo htmlspecialchars({expression}, ENT_QUOTES); ?>"'

        def _wrap_short_echo_textarea(match):
            expression = str(match.group(1) or '').strip()
            if not expression or 'htmlspecialchars(' in expression.lower():
                return match.group(0)
            return f'><?=htmlspecialchars({expression}, ENT_QUOTES);?></textarea>'

        def _wrap_php_echo_textarea(match):
            expression = str(match.group(1) or '').strip()
            if not expression or 'htmlspecialchars(' in expression.lower():
                return match.group(0)
            return f'><?php echo htmlspecialchars({expression}, ENT_QUOTES); ?></textarea>'

        rendered = re.sub(
            r'value="\s*<\?=\s*(?!htmlspecialchars\()(.+?)\s*;\s*\?>"',
            _wrap_short_echo_value,
            rendered,
            flags=re.IGNORECASE | re.DOTALL
        )
        rendered = re.sub(
            r'value="\s*<\?php\s+echo\s+(?!htmlspecialchars\()(.+?)\s*;\s*\?>"',
            _wrap_php_echo_value,
            rendered,
            flags=re.IGNORECASE | re.DOTALL
        )
        rendered = re.sub(
            r'>\s*<\?=\s*(?!htmlspecialchars\()(.+?)\s*;\s*\?>\s*</textarea>',
            _wrap_short_echo_textarea,
            rendered,
            flags=re.IGNORECASE | re.DOTALL
        )
        rendered = re.sub(
            r'>\s*<\?php\s+echo\s+(?!htmlspecialchars\()(.+?)\s*;\s*\?>\s*</textarea>',
            _wrap_php_echo_textarea,
            rendered,
            flags=re.IGNORECASE | re.DOTALL
        )

        if rendered != original:
            logger.info("ðŸ§¼ Sanitized raw rendered field values with htmlspecialchars(...)")

        return rendered

    def _repair_known_form_action_patterns(self, code: str) -> str:
        """
        Repair known malformed form.action patterns produced by retries.
        """
        repaired = str(code or '')
        if not repaired:
            return repaired

        original = repaired

        repaired = re.sub(
            (
                r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']\s*;'
            ),
            'form.action = "<?php echo $form2; ?>";',
            repaired,
            flags=re.IGNORECASE
        )
        repaired = re.sub(
            r'(<form\b[^>]*\baction\s*=\s*["\']<\?=\$form2;\?>)\s*(>)',
            r'\1"\2',
            repaired,
            flags=re.IGNORECASE
        )

        if repaired != original:
            logger.info("🛠️ Repaired malformed form.action patterns before assertions")
        return repaired

    def _repair_compound_if_db_patterns(self, code: str) -> str:
        """
        Repair invalid PHP patterns where multiple statements are injected into if(...)
        conditions, e.g. if (a=1; b=2; db_insert(...)) { ... }.
        """
        repaired = str(code or '')
        if not repaired:
            return repaired

        original = repaired

        # Case 1: if (stmt; db_call(...)) { ... } -> stmt; if (db_call(...)) { ... }
        repaired = re.sub(
            r'(?ms)^(?P<indent>\s*)if\s*\(\s*(?P<stmts>[^\n\)]*?;\s*)(?P<db>db_(?:insert|update|delete)\s*\([^\)]*\))\s*\)\s*\{',
            lambda m: f"{m.group('indent')}{m.group('stmts').strip()}\n{m.group('indent')}if ({m.group('db').strip()}) {{",
            repaired,
        )

        # Case 2: if (db_delete(...); db_update(...)) { ... } -> db_delete(...); if (db_update(...)) { ... }
        repaired = re.sub(
            r'(?ms)^(?P<indent>\s*)if\s*\(\s*(?P<first>db_delete\s*\([\s\S]*?\)\s*;)\s*(?P<second>db_update\s*\([\s\S]*?\))\s*\)\s*\{',
            lambda m: f"{m.group('indent')}{m.group('first').strip()}\n{m.group('indent')}if ({m.group('second').strip()}) {{",
            repaired,
        )

        if repaired != original:
            logger.info("🛠️ Repaired invalid semicolon-based if(...) DB patterns before assertions")
        return repaired

    def _enforce_company_contract_output(self, code: str, contract: Dict) -> str:
        """
        Apply final compatibility repairs for company-form contract requirements.
        """
        patched = str(code or '')
        if not patched:
            return patched

        original = patched

        if 'include/formheader.php' not in patched.lower():
            updated = re.sub(
                r'(\?\>\s*<\?php\s*include\("include/sidemenu\.php"\);?\s*\?>)',
                r'\1\n<?php include("include/formheader.php"); ?>',
                patched,
                count=1,
                flags=re.IGNORECASE,
            )
            if updated == patched:
                updated = re.sub(
                    r'(<div\s+class="page\s+animsition"\s*>\s*)',
                    r'\1\n    <?php include("include/formheader.php"); ?>\n',
                    patched,
                    count=1,
                    flags=re.IGNORECASE,
                )
            if updated != patched:
                patched = updated
                logger.info("🛠️ Injected missing include/formheader.php")

        if 'success.form.fv' not in patched and '.formValidation(' in patched:
            updated = re.sub(
                r'(\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*;)',
                r"\1\n    }).on('success.form.fv', function(e) {\n        e.preventDefault();\n        btnsave_click();\n    });",
                patched,
                count=1,
                flags=re.IGNORECASE,
            )
            if updated != patched:
                patched = updated
                logger.info("🛠️ Injected missing success.form.fv submit chain")

        malformed_submit_chain_literals = [
            "); }).on('success.form.fv'",
            '); }).on("success.form.fv"',
            ");\n    }).on('success.form.fv'",
            ');\n    }).on("success.form.fv"',
        ]
        for bad_snippet in malformed_submit_chain_literals:
            if bad_snippet in patched:
                patched = patched.replace(bad_snippet, ").on('success.form.fv'" if 'success.form.fv' in bad_snippet else bad_snippet)
                logger.info("🛠️ Repaired malformed success.form.fv submit chain")
                break

        repaired = re.sub(
            r'\}\);\s*\}\)\.on\(\s*[\'\"]success\.form\.fv[\'\"]',
            ").on('success.form.fv'",
            patched,
            count=1,
            flags=re.IGNORECASE,
        )
        if repaired != patched:
            patched = repaired
            logger.info("🛠️ Repaired exact `}); }).on(success.form.fv)` submit chain")

        repaired = re.sub(
            r'\}\);\s*\n\s*\}\)\.on\(\s*[\'\"]success\.form\.fv[\'\"]',
            ").on('success.form.fv'",
            patched,
            count=1,
            flags=re.IGNORECASE,
        )
        if repaired != patched:
            patched = repaired
            logger.info("🛠️ Repaired newline variant of success.form.fv submit chain")

        if any(token not in patched.lower() for token in ('creationdatetime', 'userid', 'login_id')):
            updated = re.sub(
                r'(funStartTran\s*\(\s*\)\s*;\s*)',
                r"\1\n            $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));\n            $columns['UserId'] = $_SESSION['user_id'] ?? '';\n            $columns['Login_ID'] = $_SESSION['login_id'] ?? '';\n            ",
                patched,
                count=1,
                flags=re.IGNORECASE,
            )
            if updated != patched:
                patched = updated
                logger.info("🛠️ Injected canonical audit columns")

        if 'response.maxid' in patched.lower():
            patched = re.sub(r'response\s*\.\s*maxid', 'response', patched, flags=re.IGNORECASE)
            logger.info("🛠️ Normalized GetMaxID client response handling to scalar output")

        if patched != original:
            logger.info("🛠️ Applied final company contract repairs")
        return patched

    def _assert_required_sections_after_merge(self, assembled_code: str, contract: Dict, sections: Optional[Dict[str, str]] = None):
        """
        ✅ FIX 3: Validate assembled code (after template merge)
        """
        diagnostics = self._collect_form_diagnostics(assembled_code)
        self._log_form_diagnostics(diagnostics, "assert-boundary")
        errors = []
        strict_contract = (contract or {}).get('strict_contract')
        strict_contract_mode = bool((contract or {}).get('strict_contract_mode'))
        if isinstance(strict_contract, dict):
            strict_contract_mode = strict_contract_mode or bool(strict_contract.get('valid'))
        elif strict_contract:
            strict_contract_mode = True
        
        # Check for critical patterns in assembled code
        has_any_crud = any(func in assembled_code for func in ['db_insert', 'db_update', 'db_delete'])
        if not has_any_crud:
            if strict_contract_mode:
                errors.append("CRUD function missing")
            else:
                logger.warning("CRUD function missing in assembled output (non-strict mode)")
        if not diagnostics['has_form']:
            errors.append("Form HTML missing")
        if diagnostics['form_open_count'] != 1:
            errors.append(f"Expected exactly one opening <form> tag, found {diagnostics['form_open_count']}")
        if diagnostics['form_close_count'] != 1:
            errors.append(f"Expected exactly one closing </form> tag, found {diagnostics['form_close_count']}")
        if diagnostics['nested_forms']:
            errors.append("Nested form tags detected")
        if diagnostics['unmatched_form_tags']:
            errors.append("Unmatched <form>/</form> structure detected")
        if diagnostics['broken_form_action_quote']:
            errors.append("Broken form action attribute detected")
        if diagnostics.get('malformed_form_opening_suffix'):
            errors.append("Malformed form opening tag suffix detected")
        if diagnostics.get('broken_onkeydown_assignment'):
            errors.append("Malformed document.onkeydown assignment detected")
        if diagnostics.get('script_src_inline_mix'):
            errors.append("Inline JavaScript detected inside <script src=...> tag")

        opening_tag = self._extract_first_form_opening_tag(assembled_code)
        if opening_tag:
            if not re.search(r'\bid\s*=\s*["\']frm["\']', opening_tag, re.IGNORECASE):
                if strict_contract_mode:
                    errors.append("Form opening tag is missing id=\"frm\"")
                else:
                    logger.warning("Form opening tag missing id=\"frm\" in non-strict mode.")
            if not re.search(r'\bname\s*=\s*["\']frm["\']', opening_tag, re.IGNORECASE):
                logger.warning("Form opening tag missing name=\"frm\"; continuing with id=\"frm\" canonical marker.")
            if not re.search(r'\bmethod\s*=\s*["\']post["\']', opening_tag, re.IGNORECASE):
                errors.append("Form opening tag is missing method=\"POST\"")
        else:
            errors.append("Unable to parse form opening tag")

        if len(re.findall(r'function\s+maxid\s*\(', assembled_code, re.IGNORECASE)) > 1:
            errors.append("Duplicate maxid() function detected")
        if len(re.findall(r'\.formValidation\s*\(\s*\{', assembled_code, re.IGNORECASE)) > 1:
            errors.append("Duplicate formValidation initialization detected")
        if re.search(r'\?>\s*\?>', assembled_code):
            errors.append("Duplicate PHP closing tags detected")
        if re.search(r'<\?=\s*\$_(?:REQUEST|POST|GET)\s*\[', assembled_code, re.IGNORECASE):
            errors.append("Unescaped request echo detected in assembled HTML")
        if re.search(
            r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']',
            assembled_code,
            re.IGNORECASE
        ):
            errors.append("Malformed form.action JavaScript assignment detected")
        if re.search(
            r'\$filter\s*=\s*["\'][^;\n]*\.\s*(?:add(?:_slashes_new)?\s*\()?\s*\$_(?:REQUEST|POST|GET)',
            assembled_code,
            re.IGNORECASE
        ):
            errors.append("Unsafe SQL filter concatenation detected")
        if re.search(r'\b(?:mysql|mysqli)_(?:query|fetch_array|fetch_assoc|fetch_row)\s*\(', assembled_code, re.IGNORECASE):
            errors.append("Forbidden mysql/mysqli API detected")

        ajax_opens = len(re.findall(r'\$\.ajax\s*\(\s*\{', assembled_code, re.IGNORECASE))
        ajax_closes = len(re.findall(r'\}\s*\)\s*;', assembled_code, re.IGNORECASE))
        if ajax_opens > ajax_closes:
            errors.append("Unclosed $.ajax({ ... }); block detected")

        for maxid_match in re.finditer(r'function\s+maxid\s*\(\)\s*\{', assembled_code, re.IGNORECASE):
            window = assembled_code[maxid_match.start(): maxid_match.start() + 2500]
            if '$.ajax' in window and '});' not in window:
                errors.append("Malformed maxid() AJAX block detected")
                break
            if (
                '$.ajax' in window
                and re.search(r"data\s*:\s*\{[^}]*Action\s*:\s*['\"]GetMaxID['\"]", window, re.IGNORECASE)
                and 'success:' not in window
                and '.done(' not in window
            ):
                errors.append("maxid() AJAX handler is missing success callback handling")
                break
        
        if errors:
            error_msg = "❌ SECTION ASSERTION FAILED:\n" + "\n".join(f"  - {e}" for e in errors)
            snapshot_path = self._write_assembly_failure_snapshot(
                assertion_message=error_msg,
                assembled_code=assembled_code,
                sections=sections or {},
                contract=contract,
                diagnostics=diagnostics
            )
            if snapshot_path:
                error_msg += f"\n  - Snapshot: {snapshot_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _assert_required_sections(self, sections: Dict[str, str], contract: Dict):
        """
        DEPRECATED: Moved to _assert_required_sections_after_merge
        """
        pass
    
    def _parse_sections(self, generated_code: str) -> Dict[str, str]:
        """
        Parse LLM-generated code into sections.
        
        Looks for section markers like:
        - PHP variables ($form, $table, $title)
        - CRUD handlers (Save, Update, Delete, Edit)
        - AJAX handlers
        - Form fields HTML
        - Validation rules
        
        Returns:
            {
                'php_variables': str,
                'crud_handlers': str,
                'ajax_handlers': str,
                'form_fields': str,
                'validation_rules': str,
                'grid_logic': str
            }
        """
        sections = {
            'php_variables': '',
            'php_logic': '',
            'crud_handlers': '',
            'crud_operations': '',
            'ajax_handlers': '',
            'form_fields': '',
            'validation_rules': '',
            'form_validation_fields': '',
            'select2_handlers': '',
            'head_scripts': '',
            'grid_logic': '',
            'entity_js': ''
        }
        
        # Strip markdown code blocks
        code = self._strip_code_markers(generated_code)

        # Prefer the controlled tagged output when it is available.
        controlled_sections = [
            ('VARIABLE_INIT_PHP', 'php_variables'),
            ('CRUD_LOGIC_PHP', 'crud_handlers'),
            ('AJAX_HANDLERS_PHP', 'ajax_handlers'),
            ('FORM_FIELDS_HTML', 'form_fields'),
            ('FORM_VALIDATION_FIELDS', 'form_validation_fields'),
            ('SELECT2_HANDLERS', 'select2_handlers'),
            ('ENTITY_JS', 'entity_js'),
        ]
        controlled_hits = 0
        for section_name, target_key in controlled_sections:
            match = re.search(
                rf'<<<{section_name}>>>(.*?)<<<END_{section_name}>>>',
                code,
                re.DOTALL | re.IGNORECASE
            )
            if not match:
                match = re.search(
                    rf'<{section_name}>(.*?)</{section_name}>',
                    code,
                    re.DOTALL | re.IGNORECASE
                )
            if match:
                sections[target_key] = match.group(1).strip()
                controlled_hits += 1
                logger.info(
                    f"Extracted {section_name} into {target_key}: "
                    f"{len(sections[target_key])} chars"
                )
        
        # Extract PHP variables section
        if not sections['php_variables']:
            var_match = re.search(
                r'<\?php\s*(.*?)\s*(?:if\s*\(|switch\s*\(|\?>)',
                code,
                re.DOTALL | re.IGNORECASE
            )
            if var_match:
                sections['php_variables'] = var_match.group(1).strip()
        
        # Extract CRUD handlers
        if not sections['crud_handlers']:
            crud_match = re.search(
                r'(?:if|switch)\s*\([^)]*Action[^)]*\)(.*?)(?:\?>|<html)',
                code,
                re.DOTALL | re.IGNORECASE
            )
            if crud_match:
                sections['crud_handlers'] = crud_match.group(1).strip()
        
        # Extract form fields (HTML between <form> tags or after ?>)
        if not sections['form_fields']:
            form_match = re.search(
                r'\?>(.*?)(?:<script|$)',
                code,
                re.DOTALL
            )
            if form_match:
                sections['form_fields'] = form_match.group(1).strip()
        
        # Extract validation rules (JavaScript FormValidation)
        if not sections['validation_rules']:
            validation_match = re.search(
                r'formValidation\s*\([^)]*\)\s*\.addField\s*\((.*?)\)\s*;',
                code,
                re.DOTALL
            )
            if validation_match:
                sections['validation_rules'] = validation_match.group(0).strip()
        
        # ✅ FIX: Extract entity_js using TAG-BASED parsing (aligned with system architecture)
        # System uses <<<ENTITY_JS>>> tags, NOT generic <script> regex
        entity_js_match = re.search(
            r'<<<ENTITY_JS>>>(.*?)<<<END_ENTITY_JS>>>',
            code,
            re.DOTALL | re.IGNORECASE
        )
        if entity_js_match:
            sections['entity_js'] = entity_js_match.group(1).strip()
            logger.info(f"✅ Extracted ENTITY_JS section: {len(sections['entity_js'])} chars")
        else:
            logger.warning("⚠️ ENTITY_JS section not found in generated code")
        
        if not sections['entity_js']:
            script_match = re.search(
                r'<script\b[^>]*>(.*?)</script>',
                code,
                re.DOTALL | re.IGNORECASE
            )
            if script_match:
                sections['entity_js'] = script_match.group(1).strip()

        sections = self._sync_section_aliases(sections)
        return sections
    
    def _strip_code_markers(self, text: str) -> str:
        """Strip markdown code block markers"""
        cleaned = text.strip()
        
        # Remove ```php or ```
        cleaned = re.sub(r'^```(?:php)?\s*\n', '', cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r'\n```\s*$', '', cleaned, flags=re.MULTILINE)
        
        return cleaned.strip()

    def _sync_section_aliases(self, sections: Dict[str, str]) -> Dict[str, str]:
        """
        Keep legacy section keys and controlled-generation keys aligned.
        """
        alias_pairs = [
            ('php_variables', 'php_logic'),
            ('crud_handlers', 'crud_operations'),
        ]

        for legacy_key, modern_key in alias_pairs:
            legacy_value = sections.get(legacy_key, '') or ''
            modern_value = sections.get(modern_key, '') or ''

            if legacy_value and not modern_value:
                sections[modern_key] = legacy_value
            elif modern_value and not legacy_value:
                sections[legacy_key] = modern_value

        return sections
    
    def _distribute_php_logic(self, sections: Dict[str, str]) -> Dict[str, str]:
        """
        ✅ FIX #2: Distribute php_logic content into empty crud_operations/ajax_handlers.
        
        ROOT CAUSE: LLM puts ALL code in VARIABLE_INIT_PHP section (maps to php_logic).
        Validator checks crud_operations and ajax_handlers which are empty.
        
        SOLUTION: Extract CRUD/AJAX handlers from php_logic and populate empty sections.
        
        Args:
            sections: Parsed sections from LLM output
            
        Returns:
            Updated sections with distributed content
        """
        sections = self._sync_section_aliases(sections)

        php_logic = sections.get('php_logic', '') or sections.get('php_variables', '')
        crud_operations = sections.get('crud_operations', '') or sections.get('crud_handlers', '')
        ajax_handlers = sections.get('ajax_handlers', '')
        
        logger.info(f"📊 Before distribution: php_logic={len(php_logic)} chars, crud_operations={len(crud_operations)} chars, ajax_handlers={len(ajax_handlers)} chars")
        
        # Step 1: Extract CRUD handlers (Save, Update, Delete cases)
        if not crud_operations.strip() and php_logic:
            crud_patterns = [
                # Pattern: if($_REQUEST['Action'] == 'Save') or similar
                r'(if\s*\(\s*\$_(?:REQUEST|POST)\s*\[.{0,30}(?:save|Save|update|Update|delete|Delete).+?(?=if\s*\(\s*\$_(?:REQUEST|POST)|$))',
                # Pattern: case 'Save': or case "Save":
                r'(case\s+[\'"](?:Save|Update|Delete|save|update|delete)[\'"].+?break\s*;)',
                # Pattern: switch on action variable
                r'(switch\s*\(.+?\)\s*\{.+?\})',
            ]
            
            extracted_crud = []
            for pattern in crud_patterns:
                matches = re.findall(pattern, php_logic, re.DOTALL | re.IGNORECASE)
                extracted_crud.extend(matches)
            
            if extracted_crud:
                sections['crud_operations'] = '\n'.join(extracted_crud)
                logger.info(
                    f"✅ Extracted {len(extracted_crud)} CRUD blocks into crud_operations "
                    f"({len(sections['crud_operations'])} chars)"
                )
            else:
                # Fallback: copy entire php_logic to crud_operations
                # so validators can find db_insert, db_update, db_delete
                sections['crud_operations'] = php_logic
                logger.info(
                    f"✅ Copied php_logic to crud_operations (no specific CRUD blocks found) "
                    f"({len(sections['crud_operations'])} chars)"
                )
        
        # Step 2: Extract AJAX handlers (GetMaxID, getvalue cases)
        if not ajax_handlers.strip() and php_logic:
            ajax_patterns = [
                # Pattern: if($_POST['case'] == 'GetMaxID')
                r'(if\s*\(\s*\$_POST\s*\[.{0,20}[Cc]ase.+?exit\s*;)',
                # Pattern: case 'GetMaxID':
                r'(case\s+[\'"](?:GetMaxID|getMaxID|get_max_id).+?break\s*;)',
                # Pattern: getvalue() call
                r'(.{0,50}getvalue\s*\(.+?\).{0,100})',
            ]
            
            extracted_ajax = []
            for pattern in ajax_patterns:
                matches = re.findall(pattern, php_logic, re.DOTALL | re.IGNORECASE)
                extracted_ajax.extend(matches)
            
            if extracted_ajax:
                sections['ajax_handlers'] = '\n'.join(extracted_ajax)
                logger.info(
                    f"✅ Extracted {len(extracted_ajax)} AJAX blocks into ajax_handlers "
                    f"({len(sections['ajax_handlers'])} chars)"
                )
            else:
                # Fallback: also check entity_js for AJAX patterns
                entity_js = sections.get('entity_js', '') or ''
                if 'GetMaxID' in entity_js or 'getvalue' in php_logic:
                    sections['ajax_handlers'] = php_logic
                    logger.info(
                        f"✅ Copied php_logic to ajax_handlers (GetMaxID/getvalue found) "
                        f"({len(sections['ajax_handlers'])} chars)"
                    )
        
        logger.info(f"📊 After distribution: crud_operations={len(sections.get('crud_operations',''))} chars, ajax_handlers={len(sections.get('ajax_handlers',''))} chars")
        
        return sections
    
    def _auto_repair(self, sections: Dict[str, str], contract: Dict) -> Dict[str, str]:
        """
        Auto-repair missing critical blocks.
        
        FIX #7: Injects missing mandatory functions:
        1. Comp_Code filter if missing
        2. Session variables if missing
        3. Audit logging (fun_log) if missing
        4. Pre-delete checks if dependencies exist
        5. getvalue in AJAX handlers if missing (FIX #7)
        6. Transaction management (funStartTran/funEndTran) if missing (FIX #7)
        """
        logger.info("🔧 CodeAssembler: Auto-repairing missing blocks...")
        
        repaired = self._sync_section_aliases(sections.copy())
        repairs_made = []

        canonical_php_vars = self._enforce_canonical_php_variables(
            repaired.get('php_variables', '') or repaired.get('php_logic', ''),
            contract
        )
        if canonical_php_vars:
            repaired['php_variables'] = canonical_php_vars
            repaired['php_logic'] = canonical_php_vars
            repairs_made.append('Canonical php variables ($form/$form2/$table/$title)')
        
        # FIX #7: Check if getvalue is missing from ALL sections
        all_code = '\n'.join([
            repaired.get('crud_handlers', ''),
            repaired.get('ajax_handlers', ''),
            repaired.get('php_variables', '')
        ])
        
        # 1. Inject getvalue in AJAX handlers if missing (FIX #7)
        if 'getvalue' not in all_code:
            table_name = contract.get('table_name', 'tbl_unknown')
            pk_field = contract.get('primary_key', 'ID')
            
            getvalue_block = f"""
// GetMaxID AJAX Handler
if(isset($_POST['case']) && $_POST['case'] == 'GetMaxID') {{
    $sql = "SELECT IFNULL(MAX({pk_field}),'') FROM {table_name} WHERE Comp_Code='" . $_SESSION['Comp_Code'] . "'";
    $maxid = getvalue($sql);
    echo $maxid;
    exit;
}}
"""
            # Inject at start of AJAX section
            ajax_section = repaired.get('ajax_handlers', '')
            repaired['ajax_handlers'] = getvalue_block + ajax_section
            repairs_made.append('getvalue (GetMaxID handler)')

        ajax_handlers = str(repaired.get('ajax_handlers') or '').strip()
        if len(ajax_handlers) < 300:
            repaired['ajax_handlers'] = (
                self._build_default_ajax_handlers(contract)
                + "\n"
                + ajax_handlers
            ).strip()
            repairs_made.append('Expanded AJAX handlers (GetMaxID/GetCOSTCENTER)')
        
        # 2. Inject transaction management if missing (FIX #7)
        crud_section = repaired.get('crud_handlers', '')
        if 'funStartTran' not in crud_section and 'db_insert' in crud_section:
            crud_section = self._wrap_crud_with_transactions(crud_section)
            repaired['crud_handlers'] = crud_section
            repairs_made.append('Transaction management (funStartTran/funEndTran)')
        
        # 3. Inject Comp_Code if missing
        if 'Comp_Code' not in repaired.get('crud_handlers', ''):
            repaired['crud_handlers'] = self._inject_comp_code(repaired.get('crud_handlers', ''))
            repairs_made.append('Comp_Code filter')
        
        # 4. Inject session variables if missing
        if '$_SESSION' not in repaired.get('crud_handlers', ''):
            repaired['crud_handlers'] = self._inject_session_vars(repaired.get('crud_handlers', ''))
            repairs_made.append('Session variables')
        
        # 5. Inject audit logging if missing
        if 'fun_log' not in repaired.get('crud_handlers', ''):
            repaired['crud_handlers'] = self._inject_audit_logging(repaired.get('crud_handlers', ''))
            repairs_made.append('Audit logging')
        
        # 6. Inject pre-delete checks per dependency (not global getrows existence)
        dependencies = contract.get('dependencies') or []
        missing_dependencies = self._get_missing_dependency_checks(
            repaired.get('crud_handlers', ''),
            dependencies
        )
        if missing_dependencies:
            repaired['crud_handlers'] = self._inject_predelete_checks(
                repaired.get('crud_handlers', ''),
                missing_dependencies,
                contract.get('primary_key', 'Code')
            )
            repairs_made.append(f'Pre-delete checks ({len(missing_dependencies)})')

        repaired = self._normalize_session_key_casing(repaired)

        forbidden_var_repaired = False
        for section_key in ('php_variables', 'php_logic', 'crud_handlers', 'ajax_handlers'):
            section_content = str(repaired.get(section_key) or '')
            rewritten = self._rename_forbidden_php_variables(section_content)
            if rewritten != section_content:
                repaired[section_key] = rewritten
                forbidden_var_repaired = True
        if forbidden_var_repaired:
            repairs_made.append('Forbidden variable renaming ($record->$row_data)')

        repaired, master_detail_repairs = self._enforce_master_detail_contract(repaired, contract)
        repairs_made.extend(master_detail_repairs)
        
        if repairs_made:
            logger.info(f"✅ Auto-repaired: {', '.join(repairs_made)}")
        
        return self._sync_section_aliases(repaired)

    def _enforce_canonical_php_variables(self, php_variables: str, contract: Dict) -> str:
        """
        Force canonical variable assignments so generated code cannot drift to hallucinated form names.
        """
        content = str(php_variables or '').strip()
        file_name = str(contract.get('file_name') or 'frmEntity.php').strip() or 'frmEntity.php'
        table_name = str(contract.get('table_name') or 'tblentity').strip() or 'tblentity'
        title = str(contract.get('title') or 'Entity').strip() or 'Entity'
        case_type = str(contract.get('case_type') or title).strip() or title

        content = re.sub(r'^\s*\$(?:form|form2|table|title|case_type)\s*=\s*.*?;\s*$', '', content, flags=re.IGNORECASE | re.MULTILINE)
        canonical_lines = [
            f"$form = '{file_name}';",
            f"$form2 = '{file_name}';",
            f"$table = '{table_name}';",
            f"$title = '{title}';",
            f"$case_type = '{case_type}';",
        ]
        canonical_block = "\n".join(canonical_lines)
        return (canonical_block + ("\n" + content if content else "")).strip()
    
    def _wrap_crud_with_transactions(self, crud_section: str) -> str:
        """
        FIX #7: Wrap db_insert/db_update/db_delete calls with transaction management
        Handles both single-line and multi-line function calls
        """
        import re
        
        # Only wrap if not already wrapped
        if 'funStartTran' in crud_section:
            return crud_section
        
        lines = crud_section.split('\n')
        result_lines = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Detect start of db operation assignment
            db_call_match = re.match(
                r'^(\s*)\$(\w+)\s*=\s*(db_insert|db_update|db_delete)\s*\(',
                line
            )
            
            if db_call_match:
                indent = db_call_match.group(1)
                result_var = db_call_match.group(2)
                
                # Add funStartTran before
                result_lines.append(f'{indent}funStartTran();')
                result_lines.append(line)
                
                # Collect full call until closing );
                paren_depth = line.count('(') - line.count(')')
                while paren_depth > 0 and i + 1 < len(lines):
                    i += 1
                    next_line = lines[i]
                    result_lines.append(next_line)
                    paren_depth += next_line.count('(') - next_line.count(')')
                
                # Add funEndTran after
                result_lines.append(f'{indent}funEndTran(${result_var});')
            else:
                result_lines.append(line)
            
            i += 1
        
        return '\n'.join(result_lines)
    
    def _inject_comp_code(self, crud_handlers: str) -> str:
        """Inject Comp_Code filter in WHERE clauses"""
        # Add Comp_Code to WHERE clauses if missing
        repaired = crud_handlers
        
        # Pattern: WHERE Code = ? (add AND Comp_Code = ?)
        repaired = re.sub(
            r'WHERE\s+(\w+)\s*=\s*\?(?!\s+AND\s+Comp_Code)',
            r'WHERE \1 = ? AND Comp_Code = ?',
            repaired,
            flags=re.IGNORECASE
        )
        
        return repaired

    def _build_default_ajax_handlers(self, contract: Dict) -> str:
        table_name = str(contract.get('table_name') or 'tblentity').strip() or 'tblentity'
        primary_key = str(contract.get('primary_key') or 'Code').strip() or 'Code'
        return f"""
if (isset($_POST['Action']) && $_POST['Action'] == 'GetMaxID') {{
    $maxid = getvalue("SELECT IFNULL(MAX({primary_key}), 0) + 1 FROM {table_name} WHERE Comp_Code='" . add($_SESSION['comp_code'] ?? '') . "'");
    echo $maxid;
    exit;
}}

if (isset($_POST['Action']) && $_POST['Action'] == 'GetCOSTCENTER') {{
    $rows = getrows('tblcostcenter', ' Comp_Code', add($_SESSION['comp_code'] ?? ''));
    echo json_encode($rows);
    exit;
}}
""".strip()
    
    def _inject_session_vars(self, crud_handlers: str) -> str:
        """Inject session variables in INSERT/UPDATE"""
        repaired = crud_handlers
        
        # Add session variables to INSERT if missing
        if 'db_insert' in repaired and '$_SESSION' not in repaired:
            session_block = "$user_id = $_SESSION['user_id'] ?? 1;\n$comp_code = $_SESSION['comp_code'] ?? 1;\n"
            repaired = session_block + repaired
        
        return repaired
    
    def _inject_audit_logging(self, crud_handlers: str) -> str:
        """Inject audit logging calls"""
        repaired = crud_handlers
        
        # Add fun_log after successful operations
        if 'db_insert' in repaired and 'fun_log' not in repaired:
            repaired = repaired.replace(
                'db_insert(',
                'db_insert('
            )
            # Add fun_log after db_insert
            repaired = re.sub(
                r'(db_insert\([^)]+\);)',
                r"\1\n    $log_code = $Code ?? ($_POST['Code'] ?? ($_REQUEST['Code'] ?? ''));\n    fun_log($_SESSION['user_id'] ?? '', $_SESSION['comp_code'] ?? '', $title ?? '', $log_code, 'Save', db_dateFormat(date('Y-m-d')), $_SESSION['login_id'] ?? '');",
                repaired
            )
        
        return repaired

    def _rename_forbidden_php_variables(self, content: str) -> str:
        """Normalize forbidden legacy variable names to canonical equivalents."""
        text = str(content or '')
        if not text:
            return text
        edit_variable = self.blueprint.get_edit_binding_variable()
        text = re.sub(r'\$record\b', f'${edit_variable}', text)
        text = re.sub(r'\$row_data\b', f'${edit_variable}', text)
        return text

    def _normalize_session_key_casing(self, sections: Dict[str, str]) -> Dict[str, str]:
        """Enforce canonical session keys to avoid case-mismatch runtime bugs."""
        normalized = sections.copy()
        session_contract = self.blueprint.get_session_contract()
        replacements = (
            (r"\$_SESSION\[['\"]User_ID['\"]\]", f"$_SESSION['{session_contract.get('user', 'user_id')}']"),
            (r"\$_SESSION\[['\"]Comp_Code['\"]\]", f"$_SESSION['{session_contract.get('company', 'comp_code')}']"),
            (r"\$_SESSION\[['\"]Login_ID['\"]\]", f"$_SESSION['{session_contract.get('login', 'login_id')}']"),
        )
        for key in ('php_variables', 'php_logic', 'crud_handlers', 'ajax_handlers'):
            content = str(normalized.get(key) or '')
            if not content:
                continue
            for pattern, replacement in replacements:
                content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
            normalized[key] = content
        return normalized

    def _extract_master_detail_contract(self, contract: Dict) -> Dict[str, object]:
        strict_contract = (contract or {}).get('strict_contract') or {}
        fields = (contract or {}).get('fields') or strict_contract.get('fields') or []
        detail_table = str(
            (contract or {}).get('detail_table')
            or strict_contract.get('detail_table')
            or ''
        ).strip()
        primary_key = str(
            (contract or {}).get('primary_key')
            or strict_contract.get('primary_key')
            or 'Code'
        ).strip() or 'Code'

        def _field_name(entry) -> str:
            if isinstance(entry, dict):
                return str(entry.get('name') or '').strip()
            return str(entry or '').strip()

        master_fields_raw = (contract or {}).get('master_fields') or strict_contract.get('master_fields') or []
        detail_fields_raw = (contract or {}).get('detail_fields') or strict_contract.get('detail_fields') or []

        master_fields = [_field_name(item) for item in master_fields_raw if _field_name(item)]
        detail_fields = [_field_name(item) for item in detail_fields_raw if _field_name(item)]

        if fields and (not master_fields or not detail_fields):
            for field in fields:
                if not isinstance(field, dict):
                    continue
                field_name = _field_name(field)
                if not field_name:
                    continue
                section = str(field.get('section') or 'master').strip().lower()
                if section in {'detail', 'grid', 'child', 'line'}:
                    detail_fields.append(field_name)
                else:
                    master_fields.append(field_name)

        master_fields = list(dict.fromkeys(master_fields))
        detail_fields = [name for name in dict.fromkeys(detail_fields) if name.lower() != primary_key.lower()]
        if primary_key and primary_key not in master_fields:
            master_fields.insert(0, primary_key)

        return {
            'detail_table': detail_table,
            'primary_key': primary_key,
            'master_fields': master_fields,
            'detail_fields': detail_fields,
        }

    def _remove_detail_fields_from_master_columns(self, crud_handlers: str, detail_fields: List[str]) -> str:
        text = str(crud_handlers or '')
        if not text or not detail_fields:
            return text

        disallowed = {name.lower() for name in detail_fields if str(name).strip()}
        array_pattern = re.compile(r'(\$columns\s*=\s*\[\s*)([\s\S]*?)(\]\s*;)', re.IGNORECASE)

        def _array_replacer(match: re.Match) -> str:
            prefix, body, suffix = match.groups()
            filtered_lines = []
            for line in body.splitlines():
                line_name_match = re.search(r'["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*=>', line)
                if line_name_match and line_name_match.group(1).strip().lower() in disallowed:
                    continue
                filtered_lines.append(line)
            filtered_body = "\n".join(filtered_lines).strip("\n")
            if filtered_body:
                return f"{prefix}{filtered_body}\n{suffix}"
            return f"{prefix}{suffix}"

        return array_pattern.sub(_array_replacer, text)

    def _build_detail_loop_block(self, detail_table: str, primary_key: str, detail_fields: List[str]) -> str:
        detail_lines = [f"            '{primary_key}' => $_POST['{primary_key}'] ?? ($_REQUEST['{primary_key}'] ?? ''),"]
        for field_name in detail_fields:
            detail_lines.append(f"            '{field_name}' => $_POST['{field_name}' . $i] ?? '',")
        if not detail_fields:
            detail_lines.append("            'SR_NO' => $i,")

        detail_columns_block = "\n".join(detail_lines)
        return (
            "    $count = intval($_POST['TXTCOUNTACC'] ?? $_REQUEST['TXTCOUNTACC'] ?? 0);\n"
            "    for ($i = 1; $i <= $count; $i++) {\n"
            "        $detail_columns = [\n"
            f"{detail_columns_block}\n"
            "        ];\n"
            f"        db_insert('{detail_table}', $detail_columns);\n"
            "    }"
        )

    def _enforce_master_detail_contract(self, sections: Dict[str, str], contract: Dict) -> tuple[Dict[str, str], List[str]]:
        normalized = sections.copy()
        repairs: List[str] = []
        contract_bits = self._extract_master_detail_contract(contract)
        detail_table = str(contract_bits.get('detail_table') or '').strip()
        primary_key = str(contract_bits.get('primary_key') or 'Code').strip() or 'Code'
        detail_fields = [str(name).strip() for name in (contract_bits.get('detail_fields') or []) if str(name).strip()]
        if not detail_table:
            return normalized, repairs

        crud_handlers = str(normalized.get('crud_handlers') or '')
        if not crud_handlers:
            return normalized, repairs

        cleaned_crud = self._remove_detail_fields_from_master_columns(crud_handlers, detail_fields)
        if cleaned_crud != crud_handlers:
            repairs.append('Master columns cleaned of detail fields')
        crud_handlers = cleaned_crud

        has_detail_insert = bool(
            re.search(
                rf"db_insert\s*\(\s*['\"]{re.escape(detail_table)}['\"]\s*,",
                crud_handlers,
                re.IGNORECASE
            )
        )
        if not has_detail_insert:
            detail_loop = self._build_detail_loop_block(detail_table, primary_key, detail_fields)
            updated = re.sub(
                r"(db_insert\s*\(\s*\$table\s*,\s*\$columns\s*\)\s*;)",
                r"\1\n" + detail_loop,
                crud_handlers,
                count=1,
                flags=re.IGNORECASE
            )
            if updated != crud_handlers:
                crud_handlers = updated
                repairs.append('Detail insert loop injected (TXTCOUNTACC)')

        has_detail_delete = bool(
            re.search(
                rf"db_delete\s*\(\s*['\"]{re.escape(detail_table)}['\"]\s*,",
                crud_handlers,
                re.IGNORECASE
            )
        )
        if not has_detail_delete:
            updated = re.sub(
                r"(?m)^(?P<indent>\s*)(?P<call>(?:\$[A-Za-z_][A-Za-z0-9_]*\s*=\s*)?db_update\s*\(\s*\$table\s*,)",
                f"\\g<indent>db_delete('{detail_table}', \" {primary_key}='\" . add($_POST['{primary_key}'] ?? ($_REQUEST['{primary_key}'] ?? '')) . \"'\");\n\\g<indent>\\g<call>",
                crud_handlers,
                count=1,
                flags=re.IGNORECASE
            )
            if updated != crud_handlers:
                crud_handlers = updated
                repairs.append('Detail delete-before-update injected')

        normalized['crud_handlers'] = crud_handlers
        normalized['crud_operations'] = crud_handlers

        form_fields = str(normalized.get('form_fields') or '')
        if 'TXTCOUNTACC' not in form_fields:
            hidden_input = '\n<input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="0">\n'
            normalized['form_fields'] = (form_fields + hidden_input).strip()
            repairs.append('TXTCOUNTACC hidden field injected')

        return normalized, repairs
    
    def _get_missing_dependency_checks(self, crud_handlers: str, dependencies: List[Dict]) -> List[Dict]:
        """Return dependency checks that are still missing in CRUD code."""
        missing: List[Dict] = []
        crud_lower = (crud_handlers or '').lower()
        for dep in dependencies or []:
            table = str(dep.get('table') or '').strip()
            field = str(dep.get('field') or '').strip()
            if not table or not field:
                continue
            table_lower = table.lower()
            field_lower = field.lower()
            has_check = bool(
                re.search(
                    rf'getrows\s*\([^)]*{re.escape(table_lower)}[^)]*{re.escape(field_lower)}',
                    crud_lower,
                    re.IGNORECASE | re.DOTALL
                )
            )
            if not has_check:
                missing.append(dep)
        return missing

    def _build_predelete_block(self, dependencies: List[Dict], primary_key: str = 'Code', indent: str = "    ") -> str:
        """
        Build dependency checks that are safe to run only inside delete action handlers.
        """
        pk = str(primary_key or 'Code').strip() or 'Code'
        if not dependencies:
            return ""

        lines = [
            f"{indent}// PRE-DELETE DEPENDENCY CHECKS",
            f"{indent}$Code = htmlspecialchars($_POST['{pk}'] ?? $_REQUEST['{pk}'] ?? '');",
        ]

        for dep in dependencies:
            table = str(dep.get('table') or '').strip()
            field = str(dep.get('field') or pk).strip() or pk
            message = str(dep.get('message') or f"Cannot delete. Records exist in {table}.").strip().replace("'", "\\'")
            if not table:
                continue

            safe_var = re.sub(r'[^a-zA-Z0-9_]', '_', table).strip('_').lower() or 'dep'
            counter_var = f"$cnt_{safe_var}"
            lines.extend([
                f"{indent}{counter_var} = getrows('{table}', ' {field}', add($Code));",
                f"{indent}if ({counter_var} > 0) {{",
                f"{indent}    echo \"<script>alert('{message}');</script>\";",
                f"{indent}    exit;",
                f"{indent}}}",
            ])

        return "\n".join(lines).strip()

    def _inject_predelete_checks(self, crud_handlers: str, dependencies: List[Dict], primary_key: str = 'Code') -> str:
        """Inject pre-delete checks inside delete action block only."""
        repaired = crud_handlers or ""
        checks_code = self._build_predelete_block(dependencies, primary_key)
        if not checks_code:
            return repaired

        delete_block_pattern = re.compile(
            r'if\s*\(\s*(?:isset\(\s*\$_(?:POST|REQUEST)\s*\[\s*[\'"](?:action|Action)[\'"]\s*\]\s*\)\s*&&\s*)?'
            r'\$_(?:POST|REQUEST)\s*\[\s*[\'"](?:action|Action)[\'"]\s*\]\s*==\s*[\'"](?:delete|Delete)[\'"]\s*\)\s*\{',
            re.IGNORECASE
        )
        delete_match = delete_block_pattern.search(repaired)
        if delete_match:
            insertion_point = delete_match.end()
            return repaired[:insertion_point] + "\n" + checks_code + "\n" + repaired[insertion_point:]

        guarded_block = (
            "if (isset($_POST['action']) && $_POST['action'] == 'delete') {\n"
            f"{checks_code}\n"
            "}\n"
        )
        return guarded_block + repaired

    def _sanitize_sections_with_contract(self, sections: Dict[str, str], contract: Dict) -> Dict[str, str]:
        """Strip disallowed cross-entity field tokens from generated sections."""
        sanitized = sections.copy()
        field_entries = contract.get('fields', []) or []
        allowed_fields = {
            str(field.get('name') if isinstance(field, dict) else field).strip().lower()
            for field in field_entries
            if str(field.get('name') if isinstance(field, dict) else field).strip()
        }
        primary_key = str(contract.get('primary_key') or '').strip().lower()
        if primary_key:
            allowed_fields.add(primary_key)

        allowed_fields.update({
            'comp_code', 'user_id', 'login_id', 'action', 'txtcountacc',
            'sr_no', 'status', 'case_type', 'created_by', 'created_date',
            'updated_by', 'updated_date'
        })

        disallowed_tokens = {
            'customer_code', 'supplier_code', 'engineer_code', 'main_area', 'acc_code'
        }
        section_keys = ['crud_handlers', 'ajax_handlers', 'form_fields', 'entity_js', 'form_validation_fields']
        for key in section_keys:
            content = str(sanitized.get(key) or '')
            if not content:
                continue
            content_lines = []
            for line in content.splitlines():
                line_lower = line.lower()
                line_tokens = set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*', line_lower))
                remove_line = False
                for token in line_tokens:
                    if token in disallowed_tokens and token not in allowed_fields:
                        remove_line = True
                        break
                    if (
                        token not in allowed_fields and
                        re.match(r'^[a-z]+_[a-z0-9_]+$', token) and
                        token.endswith(('code', 'name', 'date', 'no', 'id')) and
                        token not in {'maxid', 'getmaxid'}
                    ):
                        if any(
                            marker in line_lower
                            for marker in ['$_request', '$_post', '$_get', 'name=', 'id=', '=>']
                        ):
                            remove_line = True
                            break
                if not remove_line:
                    content_lines.append(line)
            sanitized[key] = '\n'.join(content_lines)
        return self._sync_section_aliases(sanitized)

    def _dedupe_sections(self, sections: Dict[str, str]) -> Dict[str, str]:
        """Deduplicate critical JS function declarations in generated sections."""
        deduped = sections.copy()
        head_scripts = str(deduped.get('head_scripts') or '')
        entity_js = str(deduped.get('entity_js') or '')

        head_scripts = self._dedupe_js_functions(head_scripts)
        entity_js = self._dedupe_js_functions(entity_js)

        # If maxid() exists in head_scripts, remove duplicates from entity_js.
        if re.search(r'function\s+maxid\s*\(', head_scripts, re.IGNORECASE):
            entity_js = self._strip_js_function(entity_js, 'maxid')
        deduped['head_scripts'] = head_scripts.strip()
        deduped['entity_js'] = entity_js.strip()
        return deduped

    def _find_js_function_block_end(self, code: str, start_index: int) -> Optional[int]:
        """
        Find the end offset of a JS function declaration while ignoring braces
        inside strings and comments.
        """
        if start_index < 0 or start_index >= len(code):
            return None

        brace_start = None
        in_single = False
        in_double = False
        in_template = False
        in_line_comment = False
        in_block_comment = False
        escape_next = False

        idx = start_index
        while idx < len(code):
            ch = code[idx]
            nxt = code[idx + 1] if idx + 1 < len(code) else ''

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                idx += 1
                continue

            if in_block_comment:
                if ch == '*' and nxt == '/':
                    in_block_comment = False
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

            if in_template:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '`':
                    in_template = False
                idx += 1
                continue

            if ch == '/' and nxt == '/':
                in_line_comment = True
                idx += 2
                continue

            if ch == '/' and nxt == '*':
                in_block_comment = True
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

            if ch == '`':
                in_template = True
                idx += 1
                continue

            if ch == '{':
                brace_start = idx
                break

            idx += 1

        if brace_start is None:
            return None

        depth = 1
        idx = brace_start + 1
        in_single = in_double = in_template = in_line_comment = in_block_comment = False
        escape_next = False

        while idx < len(code):
            ch = code[idx]
            nxt = code[idx + 1] if idx + 1 < len(code) else ''

            if in_line_comment:
                if ch == '\n':
                    in_line_comment = False
                idx += 1
                continue

            if in_block_comment:
                if ch == '*' and nxt == '/':
                    in_block_comment = False
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

            if in_template:
                if escape_next:
                    escape_next = False
                elif ch == '\\':
                    escape_next = True
                elif ch == '`':
                    in_template = False
                idx += 1
                continue

            if ch == '/' and nxt == '/':
                in_line_comment = True
                idx += 2
                continue

            if ch == '/' and nxt == '*':
                in_block_comment = True
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

            if ch == '`':
                in_template = True
                idx += 1
                continue

            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    idx += 1
                    while idx < len(code) and code[idx] in ' \t\r\n':
                        idx += 1
                    if idx < len(code) and code[idx] == ';':
                        idx += 1
                    return idx
            idx += 1

        return None

    def _dedupe_js_functions(self, code: str) -> str:
        """Keep first declaration of each named JS function."""
        if not code:
            return ""
        original_code = code
        pattern = re.compile(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.IGNORECASE)
        seen = set()
        output: List[str] = []
        cursor = 0
        search_pos = 0
        while True:
            match = pattern.search(code, search_pos)
            if not match:
                output.append(code[cursor:])
                break
            block_end = self._find_js_function_block_end(code, match.start())
            if block_end is None:
                logger.warning("⚠️ JS dedupe aborted due to unmatched braces; preserving original section")
                return original_code
            output.append(code[cursor:match.start()])
            fn_name = match.group(1).lower()
            if fn_name not in seen:
                seen.add(fn_name)
                output.append(code[match.start():block_end])
            cursor = block_end
            search_pos = block_end
        return ''.join(output)

    def _strip_js_function(self, code: str, function_name: str) -> str:
        """Remove all declarations of a named JS function from code."""
        if not code:
            return ""
        original_code = code
        pattern = re.compile(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.IGNORECASE)
        output: List[str] = []
        cursor = 0
        search_pos = 0
        target = (function_name or '').strip().lower()
        while True:
            match = pattern.search(code, search_pos)
            if not match:
                output.append(code[cursor:])
                break
            block_end = self._find_js_function_block_end(code, match.start())
            if block_end is None:
                logger.warning("⚠️ JS strip aborted due to unmatched braces; preserving original section")
                return original_code
            output.append(code[cursor:match.start()])
            if match.group(1).lower() != target:
                output.append(code[match.start():block_end])
            cursor = block_end
            search_pos = block_end
        return ''.join(output)

    def _dedupe_maxid_in_final_output(self, code: str) -> str:
        """Keep only the first maxid() function declaration in final assembled output."""
        if not code:
            return ""

        matches = list(re.finditer(r'function\s+maxid\s*\(', code, re.IGNORECASE))
        if len(matches) <= 1:
            return code

        output: List[str] = []
        seen_maxid = False
        cursor = 0
        search_pos = 0
        pattern = re.compile(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.IGNORECASE)

        while True:
            match = pattern.search(code, search_pos)
            if not match:
                output.append(code[cursor:])
                break

            block_end = self._find_js_function_block_end(code, match.start())
            if block_end is None:
                logger.warning("⚠️ maxid() dedupe aborted due to unmatched braces; preserving original output")
                return code

            output.append(code[cursor:match.start()])
            fn_name = match.group(1).lower()
            block = code[match.start():block_end]
            if fn_name != 'maxid' or not seen_maxid:
                output.append(block)
            if fn_name == 'maxid':
                seen_maxid = True
            cursor = block_end
            search_pos = block_end

        deduped = ''.join(output)
        remaining = len(re.findall(r'function\s+maxid\s*\(', deduped, re.IGNORECASE))
        if remaining > 1:
            logger.warning("⚠️ maxid() dedupe guard could not reduce to single declaration")
            return code
        return deduped

    def _dedupe_js_functions(self, code: str) -> str:
        """Keep first declaration of each named JS function."""
        if not code:
            return ""

        original_code = code
        pattern = re.compile(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.IGNORECASE)
        function_matches = list(pattern.finditer(code))
        if not function_matches:
            return code

        name_counts = Counter(match.group(1).lower() for match in function_matches)
        if all(count <= 1 for count in name_counts.values()):
            return code

        seen = set()
        output: List[str] = []
        cursor = 0
        search_pos = 0
        while True:
            match = pattern.search(code, search_pos)
            if not match:
                output.append(code[cursor:])
                break

            block_end = self._find_js_function_block_end(code, match.start())
            if block_end is None:
                logger.debug("JS dedupe skipped due to unmatched braces; preserving original section")
                return original_code

            output.append(code[cursor:match.start()])
            fn_name = match.group(1).lower()
            if fn_name not in seen:
                seen.add(fn_name)
                output.append(code[match.start():block_end])
            cursor = block_end
            search_pos = block_end

        return ''.join(output)

    def _strip_js_function(self, code: str, function_name: str) -> str:
        """Remove all declarations of a named JS function from code."""
        if not code:
            return ""

        original_code = code
        pattern = re.compile(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.IGNORECASE)
        target = (function_name or '').strip().lower()
        if not target:
            return code

        function_matches = list(pattern.finditer(code))
        if not function_matches:
            return code
        if not any(match.group(1).lower() == target for match in function_matches):
            return code

        output: List[str] = []
        cursor = 0
        search_pos = 0
        while True:
            match = pattern.search(code, search_pos)
            if not match:
                output.append(code[cursor:])
                break

            block_end = self._find_js_function_block_end(code, match.start())
            if block_end is None:
                logger.debug("JS strip skipped due to unmatched braces; preserving original section")
                return original_code

            output.append(code[cursor:match.start()])
            if match.group(1).lower() != target:
                output.append(code[match.start():block_end])
            cursor = block_end
            search_pos = block_end

        return ''.join(output)

    def _extract_first_form_opening_tag(self, assembled_code: str) -> Optional[str]:
        """
        Return the first <form ...> opening tag using a linear scanner.
        This avoids catastrophic regex backtracking on malformed mixed PHP/HTML.
        """
        code = assembled_code or ''
        match = re.search(r'<form\b', code, re.IGNORECASE)
        if not match:
            return None

        start = match.start()
        idx = match.end()
        in_single = False
        in_double = False
        in_php = False
        escape_next = False

        while idx < len(code):
            ch = code[idx]
            nxt = code[idx + 1] if idx + 1 < len(code) else ''

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
                return code[start:idx + 1]

            idx += 1

        return None

    def _has_malformed_form_opening_suffix(self, assembled_code: str) -> bool:
        """
        Detect <form ...> followed by stray quote + '>' on following line/whitespace.
        """
        code = assembled_code or ''
        opening_tag = self._extract_first_form_opening_tag(code)
        if not opening_tag:
            return False

        start = code.lower().find(opening_tag.lower())
        if start < 0:
            start = code.find(opening_tag)
        if start < 0:
            return False

        idx = start + len(opening_tag)
        while idx < len(code) and code[idx].isspace():
            idx += 1
        if idx >= len(code) or code[idx] not in ("'", '"'):
            return False
        idx += 1
        while idx < len(code) and code[idx].isspace():
            idx += 1
        return idx < len(code) and code[idx] == '>'

    def _collect_form_diagnostics(self, assembled_code: str) -> Dict[str, object]:
        form_opens = list(re.finditer(r'<form\b', assembled_code, re.IGNORECASE))
        form_closes = list(re.finditer(r'</form>', assembled_code, re.IGNORECASE))

        tokens = [(m.start(), 'open') for m in form_opens] + [(m.start(), 'close') for m in form_closes]
        tokens.sort(key=lambda item: item[0])
        depth = 0
        nested = False
        unmatched = False
        for _, token_type in tokens:
            if token_type == 'open':
                if depth >= 1:
                    nested = True
                depth += 1
            else:
                if depth <= 0:
                    unmatched = True
                else:
                    depth -= 1
        if depth != 0:
            unmatched = True

        return {
            'assembled_size': len(assembled_code or ''),
            'has_form': bool(form_opens),
            'form_open_count': len(form_opens),
            'form_close_count': len(form_closes),
            'nested_forms': nested,
            'unmatched_form_tags': unmatched,
            'broken_form_action_quote': bool(
                re.search(r'action\s*=\s*["\']<\?=\$form2;\?>(?!["\'])', assembled_code or '', re.IGNORECASE)
                or re.search(
                    r'form\.action\s*=\s*["\']\s*<\?php\s+echo\s+\$form2\s*,\s*ENT_QUOTES\)\s*;\s*\?>\s*["\']',
                    assembled_code or '',
                    re.IGNORECASE
                )
            ),
            'malformed_form_opening_suffix': self._has_malformed_form_opening_suffix(assembled_code),
            'broken_onkeydown_assignment': bool(
                re.search(
                    r'document\.onkeydown\s*=\s*checkKeycode\s*(?:\r?\n|\s)*\{',
                    assembled_code or '',
                    re.IGNORECASE
                )
            ),
            'script_src_inline_mix': bool(
                re.search(
                    r'<script[^>]*\bsrc=["\'][^"\']+["\'][^>]*>\s*[^<\s]',
                    assembled_code or '',
                    re.IGNORECASE
                )
            ),
            'preview_start_3000': (assembled_code or '')[:3000],
            'preview_end_2000': (assembled_code or '')[-2000:] if assembled_code else '',
        }

    def _log_form_diagnostics(self, diagnostics: Dict[str, object], stage: str):
        logger.info(
            "🧭 Assembly form diagnostics (%s): size=%s has_form=%s opens=%s closes=%s nested=%s unmatched=%s broken_action_quote=%s",
            stage,
            diagnostics.get('assembled_size'),
            diagnostics.get('has_form'),
            diagnostics.get('form_open_count'),
            diagnostics.get('form_close_count'),
            diagnostics.get('nested_forms'),
            diagnostics.get('unmatched_form_tags'),
            diagnostics.get('broken_form_action_quote'),
        )
        logger.info("🧭 %s preview(start 3000): %s", stage, diagnostics.get('preview_start_3000', ''))
        logger.info("🧭 %s preview(end 2000): %s", stage, diagnostics.get('preview_end_2000', ''))

    def _trace_assembled_form_state(self, assembled_code: str, stage: str):
        diagnostics = self._collect_form_diagnostics(assembled_code)
        self._log_form_diagnostics(diagnostics, stage)

    def _write_assembly_failure_snapshot(
        self,
        assertion_message: str,
        assembled_code: str,
        sections: Dict[str, str],
        contract: Dict,
        diagnostics: Dict[str, object]
    ) -> str:
        try:
            section_sizes = {
                key: len(value or '')
                for key, value in (sections or {}).items()
            }
            snapshot = {
                'assertion_message': assertion_message,
                'assembled_size': diagnostics.get('assembled_size'),
                'section_sizes': section_sizes,
                'form_open_count': diagnostics.get('form_open_count'),
                'form_close_count': diagnostics.get('form_close_count'),
                'nested_forms': diagnostics.get('nested_forms'),
                'unmatched_form_tags': diagnostics.get('unmatched_form_tags'),
                'broken_form_action_quote': diagnostics.get('broken_form_action_quote'),
                'preview_start_5000': (assembled_code or '')[:5000],
                'preview_end_2000': (assembled_code or '')[-2000:] if assembled_code else '',
                'retrieval_top_candidates': contract.get('retrieval_top_candidates') or [],
            }
            stable_id = sum(ord(ch) for ch in (assertion_message or ''))
            temp_path = os.path.join(
                tempfile.gettempdir(),
                f"code_assembler_failure_{os.getpid()}_{stable_id}.json"
            )
            with open(temp_path, 'w', encoding='utf-8') as handle:
                json.dump(snapshot, handle, ensure_ascii=True, indent=2)
            logger.error("📎 Assembly failure snapshot saved: %s", temp_path)
            return temp_path
        except Exception as snapshot_error:
            logger.error("Failed to write assembly failure snapshot: %s", snapshot_error)
            return ""
    
    def _merge_with_template(self, sections: Dict[str, str], contract: Dict) -> str:
        """
        ✅ PHASE 2.3: Merge sections with DynamicFormTemplate.
        
        Uses the template's merge_with_generated() method which now includes
        topmenu, sidemenu, footer, and page container structure.
        """
        if not self.template:
            raise ValueError("Template not available for merging")
        
        logger.info("🔧 Merging sections with DynamicFormTemplate...")
        
        # ✅ Use template's merge_with_generated() which now injects layout includes
        sections = self._sync_section_aliases(sections.copy())
        entity_js = sections.get('entity_js', '')

        head_scripts = sections.get('head_scripts', '') or self._extract_head_scripts_from_entity_js(entity_js)
        select2_handlers = sections.get('select2_handlers', '') or self._extract_select2_handlers_from_entity_js(entity_js)
        head_scripts = self._dedupe_js_functions(head_scripts)
        entity_js = self._dedupe_js_functions(entity_js)
        if re.search(r'function\s+maxid\s*\(', head_scripts, re.IGNORECASE):
            entity_js = self._strip_js_function(entity_js, 'maxid')

        form_validation_fields = sections.get('form_validation_fields', '')
        if not form_validation_fields:
            raw_validation = sections.get('validation_rules', '')
            if raw_validation and 'formValidation' not in raw_validation and '.addField' not in raw_validation:
                form_validation_fields = raw_validation
            else:
                form_validation_fields = self._extract_formvalidation_fields_from_entity_js(entity_js)
        entity_js = self._strip_formvalidation_initializers(entity_js)

        body_onload = ''
        if re.search(r'function\s+maxid\s*\(', head_scripts or entity_js, re.IGNORECASE):
            body_onload = 'maxid();'

        return self.template.merge_with_generated(
            php_logic=sections.get('php_variables', '') or sections.get('php_logic', ''),
            form_fields=sections.get('form_fields', ''),
            form_validation_fields=form_validation_fields,
            ajax_handlers=sections.get('ajax_handlers', ''),
            crud_operations=sections.get('crud_handlers', '') or sections.get('crud_operations', ''),
            head_scripts=head_scripts,
            body_onload=body_onload,
            select2_handlers=select2_handlers,
            entity_js=entity_js
        )

    def _extract_named_js_function(self, entity_js: str, function_name: str) -> str:
        """
        Extract a named JavaScript function using brace-balanced parsing.
        """
        source = str(entity_js or '')
        if not source or not function_name:
            return ""

        pattern = re.compile(
            rf'function\s+{re.escape(function_name)}\s*\(',
            re.IGNORECASE
        )
        match = pattern.search(source)
        if not match:
            return ""

        block_end = self._find_js_function_block_end(source, match.start())
        if block_end is None:
            raise ValueError(
                f"Malformed {function_name}() JavaScript block detected: unmatched braces."
            )

        snippet = source[match.start():block_end].strip()
        if '$.ajax' in snippet and not re.search(r'\}\s*\)\s*;', snippet):
            raise ValueError(
                f"Malformed {function_name}() AJAX block detected: missing closing '}});'."
            )
        return snippet

    def _extract_head_scripts_from_entity_js(self, entity_js: str) -> str:
        """Extract reusable head-level helper functions from entity JS."""
        if not entity_js:
            return ""

        head_scripts = []
        for function_name in ('maxid', 'btnsave_click', 'checkKeycode'):
            snippet = self._extract_named_js_function(entity_js, function_name)
            if snippet and snippet not in head_scripts:
                head_scripts.append(snippet)

        return '\n\n'.join(head_scripts)

    def _extract_select2_handlers_from_entity_js(self, entity_js: str) -> str:
        """Extract Select2 init and close handlers from entity JS."""
        if not entity_js:
            return ""

        select2_handlers = []
        patterns = [
            r'\$\([^)]+\)\.on\(["\']select2:close["\'],[\s\S]*?\}\s*\);',
            r'\$\([^)]+\)\.select2\([^)]*\);',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, entity_js, re.IGNORECASE | re.DOTALL):
                snippet = match.group(0).strip()
                if snippet not in select2_handlers:
                    select2_handlers.append(snippet)

        return '\n'.join(select2_handlers)

    def _extract_formvalidation_fields_from_entity_js(self, entity_js: str) -> str:
        """Extract field definitions from either formValidation() or config-style JS."""
        if not entity_js:
            return ""

        fv_match = re.search(
            r'\.formValidation\s*\(\s*\{[\s\S]*?fields\s*:\s*\{([\s\S]*?)\}\s*(?:,|\})',
            entity_js,
            re.IGNORECASE
        )
        if fv_match:
            return fv_match.group(1).strip()

        config_match = re.search(
            r'window\.companyValidationFields\s*=\s*\{([\s\S]*?)\};',
            entity_js,
            re.IGNORECASE
        )
        if config_match:
            return config_match.group(1).strip()

        return ""

    def _strip_formvalidation_initializers(self, entity_js: str) -> str:
        """
        Remove direct .formValidation({...}) initializers from entity JS.
        Template bootstrap already initializes FormValidation once, so keeping
        LLM-generated initializers causes duplicate runtime initialization.
        """
        if not entity_js or '.formValidation' not in entity_js:
            return entity_js or ""

        lines = entity_js.splitlines()
        output: List[str] = []
        i = 0
        removed_any = False

        while i < len(lines):
            line = lines[i]
            if not re.search(r'\.formValidation\s*\(', line, re.IGNORECASE):
                output.append(line)
                i += 1
                continue

            removed_any = True
            paren_depth = line.count('(') - line.count(')')
            brace_depth = line.count('{') - line.count('}')
            i += 1

            while i < len(lines):
                current = lines[i]
                paren_depth += current.count('(') - current.count(')')
                brace_depth += current.count('{') - current.count('}')
                current_stripped = current.strip()
                i += 1
                if paren_depth <= 0 and brace_depth <= 0 and (
                    current_stripped.endswith(';')
                    or current_stripped.endswith(');')
                    or current_stripped.endswith('});')
                ):
                    break

            while i < len(lines):
                next_line = lines[i].strip()
                if not next_line:
                    i += 1
                    continue
                if next_line.startswith('.'):
                    i += 1
                    if next_line.endswith(';'):
                        break
                    continue
                break

        if removed_any:
            logger.info("🧹 Removed inline formValidation initializer from ENTITY_JS to avoid duplicates")

        return '\n'.join(output).strip()

    def _merge_manual(
        self, 
        sections: Dict[str, str], 
        contract: Dict,
        fixed_parts: Dict
    ) -> str:
        """
        ✅ ISSUE #2 FIX: Improved manual merge with complete HTML structure.
        
        Builds complete PHP file from sections when template not available.
        This is a safety fallback that generates working code.
        """
        parts = []
        includes = self.blueprint.get_required_includes()
        top_include = (includes.get('top') or ['include/config.inc.php'])[0]
        body_includes = includes.get('body') or []
        footer_include = (includes.get('footer') or ['include/footer.php'])[0]
        js_submit_chain = self.blueprint.get_js_submit_chain()
        form_contract = self.blueprint.get_form_contract()
        
        # PHP opening
        parts.append("<?php")
        parts.append("@session_start();")
        parts.append(f'include("{top_include}");')
        parts.append("")
        
        # PHP variables
        parts.append(f"$form = \"{contract.get('file_name', 'frmEntity.php')}\";")
        parts.append(f"$form2 = \"{contract.get('file_name', 'frmEntity.php')}\";")
        parts.append(f"$table = \"{contract.get('table_name', 'tblentity')}\";")
        parts.append(f"$title = \"{contract.get('title', 'Entity')}\";")
        parts.append(f"$case_type = \"{contract.get('title', 'Entity')}\";")
        parts.append("")
        
        # CRUD handlers
        if sections.get('crud_handlers'):
            parts.append(sections['crud_handlers'])
            parts.append("")
        
        # Close PHP
        parts.append("?>")
        parts.append("")
        
        # HTML with complete structure
        parts.append("<!DOCTYPE html>")
        parts.append("<html>")
        parts.append("<head>")
        parts.append(f"    <title>{contract.get('title', 'Entity')}</title>")
        parts.append("    <meta charset='utf-8'>")
        parts.append("    <meta name='viewport' content='width=device-width, initial-scale=1'>")
        parts.append("")
        parts.append("    <!-- Bootstrap CSS -->")
        parts.append("    <link rel='stylesheet' href='css/bootstrap.min.css'>")
        parts.append("    <link rel='stylesheet' href='css/formValidation.min.css'>")
        parts.append("    <link rel='stylesheet' href='css/select2.min.css'>")
        parts.append("</head>")
        parts.append("<body class=\"site-navbar-small \">")
        parts.append("")
        for include_file in body_includes[:2]:
            parts.append(f'<?php include("{include_file}");?>')
        parts.append("<div class=\"page animsition\" >")
        if len(body_includes) > 2:
            parts.append(f'    <?php include("{body_includes[2]}"); ?>')
        parts.append("    <div class=\"page-content padding-5\">")
        parts.append("      <div class=\"panel\">")
        parts.append("        <div class=\"panel-body container-fluid\">")
        parts.append("          <div class=\"row row-lg\">")
        parts.append("            <div class=\"col-sm-12 col-md-12\">")
        parts.append("")
        
        form_fields_content = sections.get('form_fields') or ''
        embedded_form = bool(re.search(r'<form\b', form_fields_content, re.IGNORECASE))
        if embedded_form:
            form_fields_content = re.sub(
                r'<form\b[^>]*>',
                '<form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">',
                form_fields_content,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            form_fields_content = re.sub(
                r'(<form\b[^>]*>)\s*"\s*>',
                r'\1',
                form_fields_content,
                count=1,
                flags=re.IGNORECASE
            )
            form_fields_content = re.sub(
                r'(multipart/form-data"\s*>)\s*"',
                r'\1',
                form_fields_content,
                count=1,
                flags=re.IGNORECASE
            )
            form_fields_content = re.sub(
                r'(multipart/form-data"\s*>)\s*>',
                r'\1',
                form_fields_content,
                count=1,
                flags=re.IGNORECASE
            )
            form_fields_content = re.sub(
                r"(multipart/form-data'\s*>)\s*'",
                r"\1",
                form_fields_content,
                count=1,
                flags=re.IGNORECASE
            )
            form_fields_content = re.sub(
                r"(multipart/form-data'\s*>)\s*>",
                r"\1",
                form_fields_content,
                count=1,
                flags=re.IGNORECASE
            )
        else:
            # ✅ ISSUE #2 FIX: Add complete form structure
            parts.append(
                f"    <form id='{form_contract.get('id', 'frm')}' "
                f"name='{form_contract.get('name', 'frm')}' "
                f"method='{form_contract.get('method', 'POST')}' "
                "action='<?=$form2;?>' "
                f"class='{form_contract.get('class', 'form-horizontal')}' "
                "enctype='multipart/form-data'>"
            )
            parts.append(
                f"        <input type='hidden' name='{js_submit_chain.get('hidden_mode_field', 'txtmode')}' "
                f"id='{js_submit_chain.get('hidden_mode_field', 'txtmode')}' value='new'>"
            )
            parts.append(
                f"        <input type='hidden' name='{js_submit_chain.get('hidden_action_field', 'CTRL_HID_VALUE')}' "
                f"id='{js_submit_chain.get('hidden_action_field', 'CTRL_HID_VALUE')}' value=''>"
            )
            parts.append("")
        
        # Form fields
        if form_fields_content:
            parts.append(form_fields_content)
        else:
            # ✅ Generate basic form fields from contract if missing
            for field in contract.get('fields', []):
                field_name = field.get('name', 'Field')
                field_label = field_name.replace('_', ' ')
                parts.append(f"        <div class='form-group'>")
                parts.append(f"            <label class='col-md-2 control-label'>{field_label}</label>")
                parts.append(f"            <div class='col-md-4'>")
                parts.append(f"                <input type='text' class='form-control' name='{field_name}' id='{field_name}'>")
                parts.append(f"            </div>")
                parts.append(f"        </div>")
        
        if not embedded_form:
            parts.append("")
            parts.append("        <!-- Buttons -->")
            parts.append("        <div class='form-group'>")
            parts.append("            <div class='col-md-offset-2 col-md-10'>")
            parts.append(
                f"                <button type='button' id='{js_submit_chain.get('button_id', 'btnSave')}' "
                "class='btn btn-primary' onclick='btnsave_click()'>Save</button>"
            )
            parts.append("                <button type='button' class='btn btn-default' onclick='window.history.back()'>Back</button>")
            parts.append("            </div>")
            parts.append("        </div>")
            parts.append("    </form>")
        parts.append("            </div>")
        parts.append("          </div>")
        parts.append("        </div>")
        parts.append("      </div>")
        parts.append("    </div>")
        parts.append("  </div>")
        parts.append("")
        parts.append(f'<?php include("{footer_include}");?>')
        parts.append("")
        
        # JavaScript
        parts.append("<script src='js/jquery.min.js'></script>")
        parts.append("<script src='js/bootstrap.min.js'></script>")
        parts.append("<script src='js/select2.min.js'></script>")
        parts.append("<script src='js/formValidation.min.js'></script>")
        parts.append("<script src='js/framework/bootstrap.min.js'></script>")
        parts.append("")
        parts.append("<script>")
        
        # ✅ Add JavaScript functions
        parts.append("function btnsave_click() {")
        parts.append(f"    document.frm.{js_submit_chain.get('hidden_mode_field', 'txtmode')}.value='save';")
        parts.append("    document.frm.action='<?php echo $form2;?>';")
        parts.append("    document.frm.method='post';")
        parts.append("    if (window.jQuery) {")
        parts.append("        $('#frm').submit();")
        parts.append("    } else {")
        parts.append("        document.frm.submit();")
        parts.append("    }")
        parts.append("}")
        parts.append("")
        
        # ✅ Add FormValidation if present
        if sections.get('validation_rules'):
            parts.append(sections['validation_rules'])
        else:
            # ✅ Generate basic validation from contract
            parts.append("$(document).ready(function() {")
            parts.append("    $('#frm').formValidation({")
            parts.append("        framework: 'bootstrap',")
            parts.append("        fields: {")
            for idx, field in enumerate(contract.get('fields', [])):
                field_name = field.get('name', 'Field')
                comma = "," if idx < len(contract.get('fields', [])) - 1 else ""
                parts.append(f"            {field_name}: {{")
                parts.append(f"                validators: {{")
                parts.append(f"                    notEmpty: {{ message: '{field_name} is required' }}")
                parts.append(f"                }}")
                parts.append(f"            }}{comma}")
            parts.append("        }")
            parts.append("    }).on('success.form.fv', function(e) {")
            parts.append("        e.preventDefault();")
            parts.append("        btnsave_click();")
            parts.append("    });")
            parts.append("});")
        
        parts.append("</script>")
        parts.append("")
        parts.append("</body>")
        parts.append("</html>")
        
        return "\n".join(parts)
    
    def get_last_assembled_code(self) -> str:
        """Get the last assembled code"""
        return self.last_assembled_code
