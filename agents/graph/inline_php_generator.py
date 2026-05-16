"""
INLINE PHP+HTML Generator - TEMPLATE-BASED APPROACH
Generates complete PHP files using company form templates.
FIXED parts (CSS, scripts, HTML wrapper) come from template.
LLM only generates VARIABLE parts (fields, logic, validation).
"""
import logging
import re
import os
from typing import Dict, List, Optional, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.prompts import PromptTemplate
import json
from agents.utils.runtime_config import get_csv_setting, get_int_setting

logger = logging.getLogger(__name__)


class InlinePHPGenerator:
    """
    Generates INLINE PHP+HTML files matching company structure
    using TEMPLATE-BASED approach.
    
    FIXED parts (from template - dynamically extracted from codebase):
    - CSS links (15 files)
    - Footer scripts (30+ files)  
    - HTML wrapper (DOCTYPE, head, body, form)
    - Includes (topmenu, sidemenu, footer)
    - FormValidation boilerplate
    - Site.run(), Breakpoints
    
    VARIABLE parts (from LLM):
    - PHP variables ($form, $form2, $table, $title)
    - AJAX handlers
    - Delete logic
    - Save/Update logic
    - Form fields
    - FormValidation fields
    - Keyboard navigation
    """
    
    def __init__(self, llm_config: Dict, codebase_dir: str = None):
        self.enforce_gpt4o_mini = str(
            os.getenv('CODEGEN_ENFORCE_GPT4O_MINI', 'true')
        ).strip().lower() in {'1', 'true', 'yes', 'on'}
        self.provider_retries = get_int_setting(
            'CODEGEN_PROVIDER_MAX_RETRIES',
            'CODEGEN_PROVIDER_MAX_RETRIES',
            1,
            min_value=1,
            max_value=3
        )
        self.provider_timeout = get_int_setting(
            'CODEGEN_PROVIDER_TIMEOUT_SECONDS',
            'CODEGEN_PROVIDER_TIMEOUT_SECONDS',
            120,
            min_value=30,
            max_value=900
        )
        self.api_key = llm_config['api_key']
        self.primary_model = 'gpt-4o-mini' if self.enforce_gpt4o_mini else llm_config['model']
        configured_fallback_model = (
            'gpt-4o-mini'
            if self.enforce_gpt4o_mini
            else llm_config.get('fallback_model', self.primary_model)
        )
        configured_chain = get_csv_setting(
            'CODEGEN_MODEL_CHAIN',
            'CODEGEN_MODEL_CHAIN',
            default=[
                self.primary_model,
                configured_fallback_model
            ]
        )
        preferred_refusal_models = get_csv_setting(
            'CODEGEN_REFUSAL_MODEL_PREFERENCE',
            'CODEGEN_REFUSAL_MODEL_PREFERENCE',
            default=[
                self.primary_model,
                'gpt-4o-mini'
            ]
        )
        self.model_chain = self._unique_preserve_order(
            [
                str(model_name).strip()
                for model_name in (preferred_refusal_models + configured_chain)
                if str(model_name).strip()
            ]
        ) or [self.primary_model]
        if self.primary_model not in self.model_chain:
            self.model_chain.insert(0, self.primary_model)

        # Keep primary-style access for existing code paths.
        self.llm = self._get_llm_client(self.primary_model)
        self._llm_clients = {self.primary_model: self.llm}
        
        self.min_chars = 40000
        self.target_chars = 45000
        self.last_generation_metadata = {}
        self.last_validation_result = {}
        self._fallback_usage = {}
        self._request_schema_cache: Dict[str, Dict] = {}
        
        # Load company form template using DynamicFormTemplate
        # This dynamically extracts FIXED parts from ANY uploaded codebase
        self._template = None
        if codebase_dir and os.path.exists(codebase_dir):
            from agents.utils.dynamic_form_template import DynamicFormTemplate
            self._template = DynamicFormTemplate(codebase_dir)
            loaded = self._template.load()
            if loaded:
                logger.info(f"âœ… DynamicFormTemplate loaded from codebase: {codebase_dir}")
            else:
                logger.warning(f"âš ï¸ DynamicFormTemplate failed to load from: {codebase_dir}")

        # ✅ PHASE 2.2: Initialize modular classes for cleaner architecture
        from agents.graph.contract_parser import ContractParser
        from agents.graph.generation_planner import GenerationPlanner
        from agents.graph.code_assembler import CodeAssembler
        from agents.graph.enterprise_validator import EnterpriseValidator
        
        self.contract_parser = ContractParser()
        self.generation_planner = GenerationPlanner()
        self.code_assembler = CodeAssembler(self._template)
        self.enterprise_validator = EnterpriseValidator()
        
        logger.info("✅ PHASE 2.2: Modular classes initialized")

    def _trim_prompt_to_limit(self, prompt: str, max_prompt_chars: int, label: str = "prompt") -> str:
        """Clamp oversized prompt while keeping head+tail context."""
        if not prompt:
            return ""
        if len(prompt) <= max_prompt_chars:
            return prompt

        head_len = int(max_prompt_chars * 0.6)
        tail_len = max_prompt_chars - head_len
        trimmed = (
            prompt[:head_len]
            + "\n\n[... prompt trimmed for stability ...]\n\n"
            + prompt[-tail_len:]
        )
        logger.warning(
            f"âš ï¸ {label} trimmed for stability: {len(trimmed):,}/{max_prompt_chars:,} chars retained"
        )
        return trimmed

    def _get_llm_client(self, model_name: str) -> ChatOpenAI:
        """Return cached LLM client for the requested model."""
        model_key = self._effective_model_name(model_name)
        if hasattr(self, '_llm_clients') and model_key in self._llm_clients:
            return self._llm_clients[model_key]

        client = ChatOpenAI(
            model=model_key,
            temperature=0,
            openai_api_key=self.api_key,
            max_tokens=16000,
            # Keep provider retries low because generation loop already retries.
            max_retries=self.provider_retries,
            timeout=self.provider_timeout,
            request_timeout=self.provider_timeout
        )
        # Try to enable Structured Outputs if supported by langchain version
        # Note: response_format may not be available in older langchain versions
        try:
            from langchain_core.utils.utils import convert_to_openai_object
            # Try to bind response_format as a parameter
            # This may fail on older versions but we'll fall back to tag parsing
            pass  # Structured Output support - may require newer langchain version
        except Exception:
            pass
        if not hasattr(self, '_llm_clients'):
            self._llm_clients = {}
        self._llm_clients[model_key] = client
        return client

    def _effective_model_name(self, model_name: str) -> str:
        """Resolve actual runtime model name after enforcement rules."""
        model_key = str(model_name or self.primary_model).strip() or self.primary_model
        if self.enforce_gpt4o_mini:
            return 'gpt-4o-mini'
        return model_key

    def _should_enforce_strict_company_validation(
        self,
        company_examples: str,
        analyzed_patterns: Dict,
        example_count: int,
        essential_hits: int
    ) -> bool:
        """
        Enable strict enterprise-core validation only when retrieval context is strong.
        This avoids unnecessary fallback loops when codebase context is missing/weak.
        """
        if self._bool_setting('CODEGEN_FORCE_STRICT_COMPANY_VALIDATION', True):
            return True

        min_example_chars = get_int_setting(
            'CODEGEN_STRICT_VALIDATION_MIN_EXAMPLE_CHARS',
            'CODEGEN_STRICT_VALIDATION_MIN_EXAMPLE_CHARS',
            12000,
            min_value=2000,
            max_value=120000
        )
        min_essential_hits = get_int_setting(
            'CODEGEN_STRICT_VALIDATION_MIN_ESSENTIAL_HITS',
            'CODEGEN_STRICT_VALIDATION_MIN_ESSENTIAL_HITS',
            6,
            min_value=2,
            max_value=12
        )
        has_examples = bool((company_examples or '').strip())
        has_patterns = bool(analyzed_patterns)

        return bool(
            has_examples and
            has_patterns and
            example_count >= 1 and
            len(company_examples) >= min_example_chars and
            essential_hits >= min_essential_hits
        )

    def _build_generation_messages(self, prompt: str, user_request: str = "") -> List[Any]:
        """Wrap generation with a stable, policy-safe system instruction."""
        # ✅ CHANGE 5: Add strict format enforcement system message
        format_enforcement = self._build_system_message()
        
        system_prompt = (
            "You are an enterprise ERP code generator for benign internal business CRUD software tasks. "
            "Generate practical production-style PHP form code only. "
            "Return one complete runnable PHP file with embedded HTML/JS as requested. "
            f"{format_enforcement}"
        )
        if user_request:
            system_prompt += f" User request summary: {str(user_request)[:300]}"

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt or "")
        ]

    def _model_for_attempt(self, attempt_index: int) -> str:
        """Pick model by attempt index (primary first, then fallback chain)."""
        if not self.model_chain:
            return self.primary_model
        safe_index = min(max(attempt_index, 0), len(self.model_chain) - 1)
        return self.model_chain[safe_index]

    def _build_refusal_recovery_prompt(
        self,
        intent: Dict,
        user_request: str,
        company_fields: Dict,
        naming_metadata: Dict,
        template_code: str = ""
    ) -> str:
        """
        Build a compact benign CRUD prompt after refusal.
        This avoids oversized copy-heavy instructions that can trigger refusal again.
        """
        database = intent.get('database', {}) if isinstance(intent, dict) else {}
        table_name = (
            (naming_metadata or {}).get('table_name')
            or database.get('table_name')
            or 'tblentity'
        )
        file_name = (naming_metadata or {}).get('file_name') or 'frmEntity.php'
        title = (naming_metadata or {}).get('title') or 'Entity'
        requested_fields = (company_fields or {}).get('user_requested_fields', []) or []
        if not requested_fields:
            requested_fields = ['Code', 'Name']

        required_functions = "db_insert, db_update, db_delete, db_getRecord, getrows, getvalue"
        template_excerpt = (template_code or "").strip()
        if template_excerpt:
            template_excerpt = self._trim_prompt_to_limit(
                template_excerpt,
                get_int_setting(
                    'CODEGEN_REFUSAL_TEMPLATE_SNIPPET_MAX_CHARS',
                    'CODEGEN_REFUSAL_TEMPLATE_SNIPPET_MAX_CHARS',
                    8000,
                    min_value=2000,
                    max_value=20000
                ),
                label='refusal template snippet'
            )

        prompt = f"""
Generate a benign enterprise ERP CRUD PHP form file.
Return only code (single PHP file), no prose.

User request:
{user_request}

Canonical metadata:
- file_name: {file_name}
- table_name: {table_name}
- title: {title}

Required DB functions:
{required_functions}

Requested fields:
{', '.join(requested_fields[:30])}

Safety and scope:
- This is business CRUD code only.
- Do NOT include harmful or security-abuse content.
- Keep implementation practical and production-style.

Expected structure:
- session_start and company includes
- Action handlers for Save / Update / Delete / Edit
- Form HTML with requested fields
- AJAX for max-id lookup
- Basic validation and keyboard flow

Reference style snippet (from company codebase):
{template_excerpt if template_excerpt else '(not available)'}
"""
        refusal_prompt_cap = get_int_setting(
            'CODEGEN_REFUSAL_FINAL_PROMPT_MAX_CHARS',
            'CODEGEN_REFUSAL_FINAL_PROMPT_MAX_CHARS',
            28000,
            min_value=8000,
            max_value=80000
        )
        return self._trim_prompt_to_limit(prompt, refusal_prompt_cap, label='refusal recovery prompt')

    def _build_compact_generation_prompt(
        self,
        intent: Dict,
        user_request: str,
        company_fields: Dict,
        naming_metadata: Dict,
        hierarchy_pattern: Dict = None,
        related_tables: List[Dict] = None,
        cascading_logic: Dict = None,
        grid_pattern: Dict = None,
        template_code: str = ""
    ) -> str:
        """
        Build a compact prompt that stays well below refusal-prone sizes while
        keeping core enterprise constraints explicit.
        """
        database = intent.get('database', {}) if isinstance(intent, dict) else {}
        hierarchy_pattern = hierarchy_pattern or {}
        related_tables = related_tables or []
        cascading_logic = cascading_logic or {}
        grid_pattern = grid_pattern or {}

        table_name = (
            (naming_metadata or {}).get('table_name')
            or database.get('table_name')
            or 'tblentity'
        )
        file_name = (naming_metadata or {}).get('file_name') or 'frmEntity.php'
        title = (naming_metadata or {}).get('title') or 'Entity'
        case_type = (naming_metadata or {}).get('case_type') or title

        requested_fields = (company_fields or {}).get('user_requested_fields', []) or []
        if not requested_fields:
            requested_fields = (company_fields or {}).get('form_fields', []) or ['Code', 'Name']

        required_functions = "db_insert, db_update, db_delete, db_getRecord, getrows, getvalue"
        table_checks = []
        for rel in related_tables:
            rel_table = str(rel.get('table', '')).strip()
            rel_field = str(rel.get('field', '')).strip()
            if rel_table:
                table_checks.append(f"- {rel_table}.{rel_field or 'Code'}")

        hierarchical_rules = ""
        if hierarchy_pattern.get('is_hierarchical'):
            parent_param = hierarchy_pattern.get('parent_request_param', 'SelectArea')
            parent_field = hierarchy_pattern.get('parent_field', 'Main_Area')
            code_length = hierarchy_pattern.get('code_length', 4)
            separator = hierarchy_pattern.get('separator', '-')
            hierarchical_rules = f"""
Hierarchical code requirements:
- Keep parent-child code format with separator '{separator}'.
- maxid() AJAX must pass parent parameter '{parent_param}'.
- SQL max-id pattern must use RIGHT(Code,{code_length}) and LPAD(...,{code_length},'0').
- Parent field must be wired in HTML/JS as '{parent_field}'.
"""

        cascading_rules = ""
        if cascading_logic.get('has_cascading'):
            parent_dropdown = cascading_logic.get('parent_dropdown') or 'Main_Area'
            child_dropdown = cascading_logic.get('child_dropdown') or 'Sub_Area'
            cascading_rules = f"""
Cascading dropdown requirements:
- Populate '{child_dropdown}' from selected '{parent_dropdown}' via AJAX.
- Add Select2 close/focus chain for requested dropdown flow.
"""

        grid_rules = ""
        if grid_pattern.get('has_grid'):
            sub_table = grid_pattern.get('sub_table', 'tbldetail')
            grid_fields = grid_pattern.get('grid_fields', [])
            txtcount_var = grid_pattern.get('txtcount_var', 'TXTCOUNTACC')
            grid_rules = f"""
Detail-grid requirements:
- Save detail rows into sub-table '{sub_table}'.
- Use hidden counter '{txtcount_var}' and loop through rows.
- Add grid fields: {', '.join(grid_fields) if grid_fields else 'SR_NO'}.
"""

        predelete_rules = ""
        if table_checks:
            predelete_rules = f"""
Pre-delete dependency requirements:
{chr(10).join(table_checks)}
- For Delete action: check dependencies with getrows/getrows2.
- If dependency exists: show alert and exit before db_delete.
"""

        template_excerpt = self._extract_template_candidate_code(template_code or "")
        if not template_excerpt:
            template_excerpt = (template_code or "").strip()
        if template_excerpt:
            template_excerpt = self._trim_prompt_to_limit(
                template_excerpt,
                get_int_setting(
                    'CODEGEN_COMPACT_TEMPLATE_SNIPPET_MAX_CHARS',
                    'CODEGEN_COMPACT_TEMPLATE_SNIPPET_MAX_CHARS',
                    7000,
                    min_value=2000,
                    max_value=20000
                ),
                label='compact template snippet'
            )

        prompt = f"""
Generate ONLY the VARIABLE parts for an enterprise ERP PHP CRUD form.
Return only code. Do not add markdown or prose.

=== CRITICAL INSTRUCTION: DO NOT GENERATE FRAMEWORK COMPONENTS ===

The following FIXED PARTS will be automatically added from the company template.
DO NOT add these in your generated code:

FRAMEWORK COMPONENTS (DO NOT GENERATE):
❌ DO NOT generate: PHP session initialization or authentication code
❌ DO NOT generate: require/require_once statements for navigation components (topmenu, sidemenu, footer)
❌ DO NOT generate: CSS link tags (bootstrap, select2, formvalidation, etc.)
❌ DO NOT generate: JavaScript script tags (jquery, bootstrap, select2, formvalidation, etc.)
❌ DO NOT generate: HTML wrapper (DOCTYPE, <html>, <head>, <body>, <form> tags)
❌ DO NOT generate: FormValidation boilerplate (Site.run(), Breakpoints)
❌ DO NOT generate: Footer scripts or closing HTML tags

TEMPLATE INJECTION ARCHITECTURE:
The system will automatically:
1. Load company framework template (FIXED parts)
2. Take your generated code (VARIABLE parts only)
3. Inject your code into the template using DynamicFormTemplate.merge_with_generated()
4. Assemble the final PHP file with proper structure

=== GENERATE ONLY THESE VARIABLE PARTS ===

PHP VARIABLES (REQUIRED):
- $form = "{file_name}";
- $form2 = "{file_name}";
- $table = "{table_name}";
- $title = "{title}";
- $case_type = "{case_type}";

CRUD LOGIC (REQUIRED):
- Save handler: INSERT with db_insert()
- Update handler: UPDATE with db_update()
- Edit handler: SELECT with db_getRecord()
- Delete handler: DELETE with db_delete() (MUST have pre-delete checks)

AJAX HANDLERS (REQUIRED):
- GetMaxID handler for auto-generating primary key
- Cascading dropdown handlers (if hierarchical relationships exist)

FORM FIELDS (REQUIRED):
- HTML input elements for each field
- Proper field type mapping (see rules below)
- FormValidation field rules for each input

ENTITY-SPECIFIC BUSINESS LOGIC:
- Custom validation rules
- Relationship handling
- Dependency checks

Business scope:
- This is an internal business ERP form request (benign software task).
- Implement only standard CRUD + UI behavior.

User request:
{user_request}

=== STRUCTURED CONTRACT (MANDATORY) ===

This contract defines the complete specification for code generation.
ALL elements MUST be present in your generated code:

Entity: {title}
Table: {table_name}
Primary Key: Code (or entity-specific key)
File Name: {file_name}
Case Type: {case_type}

Fields ({len(requested_fields)} total):
{', '.join(requested_fields[:40])}

Relationships: {len(related_tables)} related tables
Dependencies: {len(table_checks)} dependency checks required

=== FIELD TYPE MAPPING (MANDATORY RULES) ===

You MUST follow these exact field type mappings:

Database Type → UI Component:
- select/dropdown fields → <select> dropdown with Select2 initialization
- varchar/text fields → text input (<input type="text">) with text validation
- int/integer/numeric fields → numeric input (<input type="number">) with numeric validation
- boolean/bit/tinyint(1) fields → checkbox (<input type="checkbox">)
- date/datetime fields → text input with date picker (<input type="text">)
- foreign key fields → <select> dropdown populated via AJAX

Validation Rules:
- varchar fields: maxLength validation
- int fields: numeric validation, min/max constraints
- required fields: notEmpty validator
- email fields: emailAddress validator
- All fields: proper FormValidation field configuration

=== MANDATORY COMPANY FUNCTIONS (MUST USE EXACT SIGNATURES) ===

Your generated code MUST use these company database functions with EXACT signatures:

✅ CORRECT COMPANY SIGNATURES (use these exactly):
- db_insert($table, $columns) - CORRECT
- db_update($table, $columns, $filter) - CORRECT  
- db_delete($table, $filter) - CORRECT
- db_getRecord($table, $filter) - CORRECT
- getrows($table, $field, $value) - CORRECT (returns row count)
- getvalue("SELECT ...") - CORRECT (direct SQL, returns scalar)
- funStartTran() - CORRECT
- funEndTran() - CORRECT

❌ FORBIDDEN PARAMETERIZED PATTERNS (do NOT use):
- db_update($table, $columns, $filter, $params) - WRONG
- getrows("SELECT ...", [$params]) - WRONG
- db_delete($table, $filter, $params) - WRONG

✅ CORRECT SQL PATTERNS:
- Filter with concatenation: $filter = " Code='" . add($value) . "'"
- SELECT with concatenation: getvalue("SELECT * FROM table WHERE Code='" . add($code) . "'")
- Dependency check: getrows($table, $field, add($value))

Transaction Pattern (REQUIRED):
funStartTran();
// INSERT/UPDATE/DELETE operations
funEndTran();

=== PRE-DELETE DEPENDENCY CHECK ENFORCEMENT ===

For ALL Delete operations, you MUST:

1. Check dependencies using getrows() BEFORE deletion
2. If dependencies exist: show alert message and exit
3. Only proceed with db_delete() if no dependencies found

Required Pattern (COMPANY STYLE):
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Delete') {{
    // Check dependencies first - use getrows(table, field, value) pattern
    $dependency_check = getrows('tbldetail', 'foreign_key_field', add($_REQUEST['major']));
    if ($dependency_check >= 1) {{
        echo "<script>alert('Cannot delete: record is being used in related table');</script>";
        exit;
    }}
    // Only delete if no dependencies
    $filter = " Code='" . add($_REQUEST['major']) . "'";
    db_delete($table, $filter);
}}

{predelete_rules}

=== IMPLEMENTATION REQUIREMENTS ===

Core Requirements:
- Use company DB functions: {required_functions}
- Implement Save, Update, Edit, Delete handlers with proper error handling
- Add AJAX GetMaxID flow with JS maxid() function
- Add Comp_Code filters and session-based audit fields in DB operations
- Use funStartTran/funEndTran around write operations
- For Delete operations: MUST check dependencies with getrows() before deletion
- If dependencies exist: show alert message and exit before executing db_delete
{hierarchical_rules}
{cascading_rules}
{grid_rules}

=== TEMPLATE CONTEXT (AUTOMATIC INJECTION) ===

The following FIXED parts will be automatically injected by the template system:
- Company framework structure wraps your generated code
- CSS and script links are injected from company template
- HTML wrapper and form tags are added automatically
- Your code is placed in the appropriate sections of the template
- PHP initialization and navigation components are handled by the template
- FormValidation boilerplate is part of the template

Your generated code will be injected into the template using:
DynamicFormTemplate.merge_with_generated(
    php_logic=your_php_variables_and_handlers,
    form_fields=your_html_form_fields,
    form_validation_fields=your_validation_rules,
    ajax_handlers=your_ajax_handlers,
    crud_operations=your_crud_logic
)

Reference style snippet from company code:
{template_excerpt if template_excerpt else '(not available)'}
"""
        compact_prompt_cap = get_int_setting(
            'CODEGEN_COMPACT_PROMPT_MAX_CHARS',
            'CODEGEN_COMPACT_PROMPT_MAX_CHARS',
            18000,
            min_value=6000,
            max_value=60000
        )
        return self._trim_prompt_to_limit(prompt, compact_prompt_cap, label='compact generation prompt')

    def _build_validation_retry_prompt(
        self,
        intent: Dict,
        user_request: str,
        company_fields: Dict,
        naming_metadata: Dict,
        hierarchy_pattern: Dict = None,
        related_tables: List[Dict] = None,
        cascading_logic: Dict = None,
        grid_pattern: Dict = None,
        template_code: str = "",
        previous_attempts: List[Dict] = None,
        phase1_errors: List[str] = None
    ) -> str:
        """
        Build a compact retry prompt focused on fixing concrete validation failures.
        Keeps retry context small to reduce refusal risk.
        """
        base_prompt = self._build_compact_generation_prompt(
            intent=intent,
            user_request=user_request,
            company_fields=company_fields,
            naming_metadata=naming_metadata,
            hierarchy_pattern=hierarchy_pattern or {},
            related_tables=related_tables or [],
            cascading_logic=cascading_logic or {},
            grid_pattern=grid_pattern or {},
            template_code=template_code or "",
        )

        normalized_issues = []
        for raw_issue in (phase1_errors or []):
            issue = str(raw_issue or "").strip()
            if not issue:
                continue
            issue = re.sub(r'^[❌⚠️✅\-\*\s]+', '', issue).strip()
            if issue:
                normalized_issues.append(issue)
        normalized_issues = self._unique_preserve_order(normalized_issues)
        if not normalized_issues:
            normalized_issues = ["Fix missing required enterprise patterns from validator feedback."]

        max_issue_count = get_int_setting(
            'CODEGEN_VALIDATION_RETRY_MAX_ISSUES',
            'CODEGEN_VALIDATION_RETRY_MAX_ISSUES',
            18,
            min_value=4,
            max_value=40
        )
        issue_lines = "\n".join(
            [f"{index + 1}. {issue}" for index, issue in enumerate(normalized_issues[:max_issue_count])]
        )

        previous_code_excerpt = ""
        if previous_attempts:
            try:
                previous_code_excerpt = str(previous_attempts[-1].get('code_snippet') or '').strip()
            except Exception:
                previous_code_excerpt = ""
        if previous_code_excerpt:
            previous_code_excerpt = self._trim_prompt_to_limit(
                previous_code_excerpt,
                get_int_setting(
                    'CODEGEN_VALIDATION_RETRY_LAST_CODE_MAX_CHARS',
                    'CODEGEN_VALIDATION_RETRY_LAST_CODE_MAX_CHARS',
                    2500,
                    min_value=800,
                    max_value=12000
                ),
                label='validation retry previous code snippet'
            )

        retry_feedback = f"""
Validation feedback from previous attempt (must be fixed):
{issue_lines}

Retry instructions:
- Return only one complete runnable PHP file (no markdown, no prose).
- Preserve canonical file/table/title naming from metadata.
- Keep business logic benign and CRUD-focused.
- Do not omit required handlers (Save/Update/Delete/Edit, AJAX max-id flow).
"""
        if previous_code_excerpt:
            retry_feedback += f"""

Previous attempt snippet (for diff/fix context):
{previous_code_excerpt}
"""

        retry_prompt = (base_prompt + "\n\n" + retry_feedback).strip()
        retry_prompt_cap = get_int_setting(
            'CODEGEN_VALIDATION_RETRY_PROMPT_MAX_CHARS',
            'CODEGEN_VALIDATION_RETRY_PROMPT_MAX_CHARS',
            22000,
            min_value=8000,
            max_value=80000
        )
        return self._trim_prompt_to_limit(retry_prompt, retry_prompt_cap, label='validation retry prompt')
    
    def _extract_codebase_relative_path(self, raw_path: str) -> str:
        """Extract the path suffix that lives under the current codebase root."""
        if not raw_path or not self._template or not self._template.codebase_dir:
            return ''

        codebase_root = os.path.normpath(self._template.codebase_dir)
        codebase_id = os.path.basename(codebase_root)
        normalized = str(raw_path).replace('/', '\\')
        marker = f"{codebase_id}\\"
        marker_index = normalized.lower().find(marker.lower())
        if marker_index == -1:
            return ''

        return normalized[marker_index + len(marker):].replace('\\', os.sep)

    def _resolve_example_file_path(
        self,
        raw_path: str = "",
        entity_name: str = "",
        entity_hints: Optional[List[str]] = None
    ) -> str:
        """
        Resolve an example file path against the current codebase, including
        stale absolute paths from previous workspace locations.
        """
        candidate_paths = []
        cleaned_path = (raw_path or '').strip()

        if cleaned_path:
            candidate_paths.append(cleaned_path)

        if self._template and self._template.codebase_dir:
            import glob

            codebase_root = os.path.normpath(self._template.codebase_dir)

            if cleaned_path and not os.path.isabs(cleaned_path):
                candidate_paths.append(os.path.join(codebase_root, cleaned_path))

            salvaged_relative = self._extract_codebase_relative_path(cleaned_path)
            if salvaged_relative:
                candidate_paths.append(os.path.join(codebase_root, salvaged_relative))

            basename = os.path.basename(cleaned_path) if cleaned_path else ''
            if basename:
                basename_matches = glob.glob(os.path.join(codebase_root, '**', basename), recursive=True)
                if basename_matches:
                    candidate_paths.append(basename_matches[0])

            entity_candidates = self._unique_preserve_order((entity_hints or []) + ([entity_name] if entity_name else []))
            for candidate_entity in entity_candidates:
                normalized_entity = re.sub(r'[^A-Za-z0-9_]', '', candidate_entity or '')
                if not normalized_entity:
                    continue
                patterns = [
                    os.path.join(codebase_root, '**', f'frm{normalized_entity}.php'),
                    os.path.join(codebase_root, '**', f'frm{normalized_entity}*.php'),
                ]
                found_match = False
                for pattern in patterns:
                    matches = glob.glob(pattern, recursive=True)
                    if matches:
                        candidate_paths.append(matches[0])
                        found_match = True
                        break
                if found_match:
                    break

            all_frm_files = glob.glob(os.path.join(codebase_root, '**', 'frm*.php'), recursive=True)
            if all_frm_files:
                candidate_paths.append(all_frm_files[0])

        seen = set()
        for candidate in candidate_paths:
            normalized = os.path.normpath(candidate)
            if normalized in seen:
                continue
            seen.add(normalized)
            if os.path.exists(normalized):
                return normalized

        return ''

    def _unique_preserve_order(self, items: List[str]) -> List[str]:
        """Return unique non-empty values while preserving their original order."""
        unique_items = []
        seen = set()

        for item in items or []:
            cleaned = (item or '').strip()
            if not cleaned:
                continue

            lookup = cleaned.lower()
            if lookup in seen:
                continue

            seen.add(lookup)
            unique_items.append(cleaned)

        return unique_items

    def _looks_like_section_heading(self, line: str) -> bool:
        """Detect structured prompt headings such as 'Master Fields:' or 'Detail Grid:'."""
        stripped = (line or '').strip()
        if not stripped:
            return False

        lowered = self._normalize_heading_text(stripped)
        configured_headings = get_csv_setting(
            'CODEGEN_SECTION_HEADINGS',
            'CODEGEN_SECTION_HEADINGS',
            default=[
                'module details',
                'master fields',
                'fields',
                'form fields',
                'primary key',
                'relationships',
                'dependencies',
                'business validations',
                'validation rules',
                'operations',
                'crud operations',
                'detail grid',
                'detail fields',
                'detail table',
                'grid',
                'company rules',
                'include all company standard patterns',
                'company standard patterns',
                'required company patterns',
                'required patterns',
                'validation rules',
                'output rules',
                'output',
                'generate complete code',
            ]
        )
        known_headings = tuple(h.lower().strip() for h in configured_headings if str(h).strip())

        return any(lowered.startswith(prefix) for prefix in known_headings)

    def _normalize_heading_text(self, text: str) -> str:
        """Normalize markdown-style heading text for robust section detection."""
        stripped = (text or '').strip()
        if not stripped:
            return ''

        # Remove markdown markers and leading list numbering.
        stripped = re.sub(r'^[#>\-\*\s]+', '', stripped)
        stripped = re.sub(r'^\d+[.)]\s*', '', stripped)
        stripped = stripped.replace('**', '').replace('__', '').replace('`', '')
        # 🔥 FIX: Remove parentheses and content inside them
        stripped = re.sub(r'\([^)]*\)', '', stripped)
        return stripped.lower().rstrip(':').strip()

    def _normalize_request_sections(self, user_request: str) -> str:
        """
        Normalize compact prompts into line-broken sections so the inline
        generator parses one-line and multi-line prompts consistently.
        """
        request_text = (user_request or "").replace('\r\n', '\n').replace('\r', '\n').strip()
        if not request_text:
            return ''

        # Normalize pipe-separated one-liners:
        # "Table: x | File name: y | Title: z" -> line-broken directives
        # but preserve pipe-delimited field/relationship contracts.
        normalized_lines: List[str] = []
        for raw_line in request_text.splitlines():
            stripped = raw_line.strip()
            preserve_pipes = bool(
                self._line_looks_like_field_definition(stripped)
                or re.match(r'^\s*[-*]\s*[A-Za-z_][A-Za-z0-9_]*\s*->', stripped)
                or ('field=' in stripped.lower() and 'message=' in stripped.lower())
            )
            if preserve_pipes:
                normalized_lines.append(raw_line.rstrip())
            else:
                normalized_lines.append(re.sub(r'\s*\|\s*', '\n', raw_line.rstrip()))
        request_text = '\n'.join(normalized_lines)

        # Keep heading splitting on the same line only (do not cross \n).
        section_pattern = (
            r'(?:table|file[ \t]*name|filename|file|title|case[ \t]*type|casetype|'
            r'primary[ \t]*key|master[ \t]*fields|form[ \t]*fields|detail[ \t]*grid|detail[ \t]*fields|'
            r'detail[ \t]*table|relationships?|dependencies?|business[ \t]*validations?|'
            r'validation[ \t]*rules|required[ \t]*company[ \t]*patterns|required[ \t]*patterns|'
            r'company[ \t]*rules|operations|crud[ \t]*operations|output[ \t]*rules|output)'
        )
        request_text = re.sub(
            rf'[ \t]+(?={section_pattern}[ \t]*:)',
            '\n',
            request_text,
            flags=re.IGNORECASE
        )
        request_text = re.sub(
            r'[ \t]+(?=-\s*[A-Za-z_][A-Za-z0-9_]*)',
            '\n',
            request_text
        )
        request_text = re.sub(r'\n{3,}', '\n\n', request_text)
        return request_text.strip()

    def _should_parse_request_schema(self, user_request: str) -> bool:
        """
        Guard RequestSchemaParser usage so we only parse structured contracts.
        This avoids noisy parser hard-fail logs for free-form prompts/examples.
        """
        normalized_request = self._normalize_request_sections(user_request or '')
        if not normalized_request:
            return False

        has_metadata_headings = bool(
            re.search(
                r'\b(?:table|file\s*name|filename|title|case\s*type|casetype)\s*:',
                normalized_request,
                re.IGNORECASE,
            )
        )
        if not has_metadata_headings:
            return False

        has_structured_field_line = any(
            self._line_looks_like_field_definition(line)
            for line in normalized_request.splitlines()
        )
        return has_structured_field_line

    def _extract_bullet_section(self, user_request: str, heading_prefixes: Tuple[str, ...]) -> List[str]:
        """Extract bullet/numbered lines that appear below a structured prompt heading."""
        normalized_request = self._normalize_request_sections(user_request)
        section_lines = []
        capturing = False
        normalized_prefixes = tuple((prefix or '').strip().lower() for prefix in heading_prefixes if prefix)

        for raw_line in normalized_request.splitlines():
            stripped = raw_line.strip()
            lowered = self._normalize_heading_text(stripped)

            if any(lowered.startswith(prefix) for prefix in normalized_prefixes):
                capturing = True
                # Check if the heading line itself contains bullet points (inline format)
                # Example: "Master Fields: - Field1 | ... - Field2 | ..."
                if '-' in stripped:
                    # Extract the part after the heading
                    for prefix in normalized_prefixes:
                        if lowered.startswith(prefix):
                            heading_end = stripped.lower().find(prefix) + len(prefix)
                            remaining = stripped[heading_end:].strip()
                            if remaining.startswith(':'):
                                remaining = remaining[1:].strip()
                            # Split by dash to get individual fields
                            if remaining.startswith('-'):
                                # This is an inline bullet list
                                inline_bullets = re.split(r'\s+-\s+', remaining)
                                for bullet in inline_bullets:
                                    bullet = bullet.strip()
                                    if bullet and bullet.startswith('-'):
                                        bullet = bullet[1:].strip()
                                    if bullet:
                                        section_lines.append(f"- {bullet}")
                                # Don't continue capturing since we already extracted inline bullets
                                capturing = False
                            break
                continue

            if not capturing:
                continue

            if self._looks_like_section_heading(stripped):
                break

            if not stripped:
                if section_lines:
                    continue
                continue

            # 🔥 FIX: Enhanced bullet/numbered line detection
            # Matches: "- Field", "* Field", "• Field", "1. Field", "1) Field"
            is_bullet = re.match(r'^[-*•]\s+', stripped)
            is_numbered = re.match(r'^\d+[.)]\s+', stripped)
            
            if is_bullet or is_numbered:
                section_lines.append(stripped)
            elif section_lines and not self._looks_like_section_heading(stripped):
                # 🔥 FIX: Allow continuation lines (for multi-line field definitions)
                section_lines[-1] = f"{section_lines[-1]} {stripped}".strip()
            else:
                # Stop if we hit a non-bullet line without prior context
                break

        return section_lines

    def _line_looks_like_field_definition(self, line: str) -> bool:
        """
        Heuristic guardrail to avoid treating operations/rules as DB fields.
        """
        cleaned = re.sub(r'^\s*(?:[-*•]\s*|\d+[.)]\s*)', '', line or '').strip()
        if not cleaned:
            return False

        lowered = cleaned.lower()
        non_field_starts = (
            'operations',
            'crud operations',
            'required company patterns',
            'required patterns',
            'output rules',
            'primary key',
            'table',
            'file name',
            'title',
            'case type',
            'casetype'
        )
        if any(lowered.startswith(prefix) for prefix in non_field_starts):
            return False

        first_token_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', cleaned)
        if not first_token_match:
            return False

        first_token = first_token_match.group(1).lower()
        non_field_tokens = {
            'create', 'read', 'update', 'delete', 'crud', 'operation', 'operations',
            'db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue',
            'funstarttran', 'funendtran', 'fun_log',
            'formvalidation', 'checkkeycode',
            'comp_code', 'user_id', 'login_id'
        }
        if first_token in non_field_tokens:
            return False

        if '|' in cleaned:
            return any(marker in lowered for marker in ('db:', 'input:', 'required:', 'type:', 'textbox', 'dropdown', 'textarea', 'checkbox'))

        structured_markers = (
            'db:',
            'input:',
            'required:',
            'type:',
            'default:',
            'textbox',
            'readonly',
            'dropdown',
            'textarea',
            'checkbox',
            'select',
            'datepicker',
            'numeric',
        )
        if any(marker in lowered for marker in structured_markers):
            return True

        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', cleaned):
            return True
        if re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*(?:,|/|\(|-|:)', cleaned):
            return True

        return False

    def _extract_entity_hints_from_request(self, user_request: str) -> List[str]:
        """Infer likely form entity names from the raw user request text."""
        request_text = self._normalize_request_sections(user_request).strip()
        if not request_text:
            return []

        lowered = request_text.lower()
        hints = []

        request_metadata = self._extract_explicit_request_metadata(request_text)
        metadata_candidates = [
            request_metadata.get('effective_entity'),
            request_metadata.get('module_entity'),
            request_metadata.get('primary_entity'),
        ]
        if request_metadata.get('file_name', '').lower().startswith('frm'):
            metadata_candidates.append(request_metadata['file_name'][3:-4])
        if request_metadata.get('table_name', '').lower().startswith('tbl'):
            metadata_candidates.append(request_metadata['table_name'][3:])
        for candidate in metadata_candidates:
            compact_candidate = ''.join(
                token.capitalize()
                for token in re.split(r'[\s_-]+', str(candidate or '').strip())
                if token
            )
            if compact_candidate:
                hints.append(compact_candidate)

        phrase_patterns = [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)',
            r'\bfrm([a-z][a-z0-9_]*)\b',
        ]
        for pattern in phrase_patterns:
            for match in re.findall(pattern, lowered, re.IGNORECASE):
                candidate = ''.join(
                    token.capitalize()
                    for token in re.split(r'[\s_-]+', str(match).strip('_- '))
                    if token
                )
                if candidate:
                    hints.append(candidate)

        configured_entity_hints = get_csv_setting(
            'CODEGEN_ENTITY_HINTS',
            'CODEGEN_ENTITY_HINTS',
            default=[]
        )
        for token in configured_entity_hints:
            if re.search(rf'\b{re.escape(token.lower())}\b', lowered):
                hints.append(token.title())

        stopwords = set(
            word.lower() for word in get_csv_setting(
                'CODEGEN_ENTITY_STOPWORDS',
                'CODEGEN_ENTITY_STOPWORDS',
                default=[
                    'create', 'complete', 'master', 'form', 'with', 'all', 'crud',
                    'operations', 'following', 'fields', 'detail', 'grid', 'include',
                    'company', 'standard', 'patterns', 'generate', 'code', 'table',
                    'tables', 'required', 'and', 'for', 'the', 'from', 'via', 'ajax',
                    'handler'
                ]
            )
        )
        for token in re.findall(r'\b[a-z][a-z0-9_]{2,}\b', lowered):
            if token in stopwords:
                continue
            hints.append(token.title())

        return self._unique_preserve_order(hints)

    def _extract_explicit_request_metadata(self, user_request: str) -> Dict[str, str]:
        """
        Parse explicit technical directives from user prompt, for example:
        - Table: tblstudent
        - File name: frmStudent.php
        
        ✅ PHASE 1.2: Enhanced with fail-fast validation for canonical naming
        """
        request_text = self._normalize_request_sections(user_request)
        lowered = request_text.lower()

        parser_metadata = {
            'table_name': '',
            'file_name': '',
            'title': '',
            'case_type': '',
            'primary_entity': '',
            'module_entity': '',
            'effective_entity': '',
            'effective_entity_compact': '',
            'has_entity_conflict': False,
        }
        if request_text and self._should_parse_request_schema(request_text):
            schema = self._parse_request_schema_cached(request_text)
            if schema:
                parser_table = str(schema.get('master_table') or schema.get('table') or '').strip()
                parser_file = os.path.basename(str(schema.get('file_name') or schema.get('filename') or '').strip())
                parser_title = str(schema.get('title') or '').strip()
                parser_case_type = str(schema.get('case_type') or '').strip()
                parser_entity = str(schema.get('entity') or '').strip()
                parser_entity_compact = re.sub(r'[^a-z0-9]', '', parser_entity.lower())
                if parser_entity_compact.endswith('master') and len(parser_entity_compact) > 6:
                    parser_entity_compact = parser_entity_compact[:-6]
                parser_metadata.update({
                    'table_name': parser_table,
                    'file_name': parser_file,
                    'title': parser_title,
                    'case_type': parser_case_type or parser_title,
                    'primary_entity': parser_entity,
                    'module_entity': parser_entity,
                    'effective_entity': parser_entity or parser_title or parser_case_type,
                    'effective_entity_compact': parser_entity_compact,
                    'has_entity_conflict': False,
                })

        # ✅ PHASE 1.2: Extract table name with validation
        table_name = parser_metadata.get('table_name', '')
        table_match = re.search(
            r'(?im)^\s*(?:[-*]\s*)?table\s*:\s*([a-z][a-z0-9_]*)\s*$',
            request_text
        )
        if table_match:
            table_name = table_match.group(1).strip()

        if not table_name:
            master_table_match = re.search(
                r'(?im)^\s*(?:[-*]\s*)?master_table\s*:\s*([a-z][a-z0-9_]*)\s*$',
                request_text
            )
            if master_table_match:
                table_name = master_table_match.group(1).strip()
        
        # ✅ PHASE 1.2: If not found, try inline format: "Table: tblname"
        if not table_name:
            inline_table_match = re.search(
                r'(?i)\btable\s*:\s*([a-z][a-z0-9_]+)',
                request_text
            )
            if inline_table_match:
                table_name = inline_table_match.group(1).strip()
        if not table_name:
            inline_master_table_match = re.search(
                r'(?i)\bmaster_table\s*:\s*([a-z][a-z0-9_]+)',
                request_text
            )
            if inline_master_table_match:
                table_name = inline_master_table_match.group(1).strip()

        # ✅ PHASE 1.2: Extract file name with validation
        file_name = parser_metadata.get('file_name', '')
        file_match = re.search(
            r'(?im)^\s*(?:[-*]\s*)?(?:file\s*name|filename|file)\s*:\s*([a-z0-9_().\-]+\.php)\s*$',
            request_text
        )
        if file_match:
            file_name = os.path.basename(file_match.group(1).strip())

        if not file_name:
            file_name_match = re.search(
                r'(?im)^\s*(?:[-*]\s*)?file_name\s*:\s*([a-z0-9_().\-]+\.php)\s*$',
                request_text
            )
            if file_name_match:
                file_name = os.path.basename(file_name_match.group(1).strip())
        
        # ✅ PHASE 1.2: If not found, try inline format: "File name: frmName.php"
        if not file_name:
            inline_file_match = re.search(
                r'(?i)(?:file\s*name|filename|file)\s*:\s*([a-z0-9_().\-]+\.php)',
                request_text
            )
            if inline_file_match:
                file_name = os.path.basename(inline_file_match.group(1).strip())
        if not file_name:
            inline_file_name_match = re.search(
                r'(?i)file_name\s*:\s*([a-z0-9_().\-]+\.php)',
                request_text
            )
            if inline_file_name_match:
                file_name = os.path.basename(inline_file_name_match.group(1).strip())

        # ✅ PHASE 1.2: Extract title with validation
        title = parser_metadata.get('title', '')
        title_match = re.search(
            r'(?im)^\s*(?:[-*]\s*)?title\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$',
            request_text
        )
        if title_match:
            title = title_match.group(1).strip()
        
        # ✅ PHASE 1.2: If not found, try inline format: "Title: Entity Name"
        if not title:
            inline_title_match = re.search(
                r'(?i)\btitle\s*:\s*([A-Za-z][A-Za-z0-9_ \-]+)',
                request_text
            )
            if inline_title_match:
                title = inline_title_match.group(1).strip()

        # ✅ PHASE 1.2: Extract case type with validation
        case_type = parser_metadata.get('case_type', '')
        case_type_match = re.search(
            r'(?im)^\s*(?:[-*]\s*)?(?:case\s*type|casetype)\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$',
            request_text
        )
        if case_type_match:
            case_type = case_type_match.group(1).strip()
        elif title:
            case_type = title

        primary_entity = parser_metadata.get('primary_entity', '')
        primary_patterns = [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*(?:[\s_-]+[a-z0-9_]+)*)',
            r'\bfrm([a-z][a-z0-9_]*)\b',
        ]
        for pattern in primary_patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                primary_entity = str(match.group(1) or '').strip()
                if primary_entity:
                    break

        module_entity = parser_metadata.get('module_entity', '')
        if file_name.lower().startswith('frm') and file_name.lower().endswith('.php'):
            module_entity = file_name[3:-4]
        elif table_name.lower().startswith('tbl'):
            module_entity = table_name[3:]
        elif table_name:
            module_entity = table_name

        primary_compact = re.sub(r'[^a-z0-9]', '', primary_entity.lower())
        module_compact = re.sub(r'[^a-z0-9]', '', module_entity.lower())
        has_entity_conflict = bool(
            primary_compact and module_compact and primary_compact != module_compact
        )

        # Deterministic rule: explicit module metadata (table/file) overrides natural-language entity.
        effective_entity = parser_metadata.get('effective_entity') or module_entity or title or case_type or primary_entity
        effective_compact = parser_metadata.get('effective_entity_compact') or re.sub(r'[^a-z0-9]', '', effective_entity.lower())
        if effective_compact.endswith('master') and len(effective_compact) > 6:
            effective_compact = effective_compact[:-6]

        # ✅ PHASE 1.2: Log extraction results for debugging
        logger.info(f"📋 Canonical naming extraction:")
        logger.info(f"   - table_name: '{table_name}' {'✅' if table_name else '❌ MISSING'}")
        logger.info(f"   - file_name: '{file_name}' {'✅' if file_name else '❌ MISSING'}")
        logger.info(f"   - title: '{title}' {'✅' if title else '❌ MISSING'}")
        logger.info(f"   - effective_entity: '{effective_entity}' {'✅' if effective_entity else '❌ MISSING'}")

        return {
            'table_name': table_name,
            'file_name': file_name,
            'title': title,
            'case_type': case_type,
            'primary_entity': primary_entity,
            'module_entity': module_entity,
            'effective_entity': effective_entity,
            'effective_entity_compact': effective_compact,
            'has_entity_conflict': has_entity_conflict,
        }

    def _is_fallback_entity_aligned(self, user_request: str, naming_metadata: Dict = None) -> bool:
        """
        Ensure deterministic fallback template still matches the requested entity.
        Prevents returning unrelated forms (for example Student request -> StockTransfer template).
        """
        naming_metadata = naming_metadata or {}
        request_meta = self._extract_explicit_request_metadata(user_request or '')

        explicit_table = (request_meta.get('table_name') or '').lower()
        explicit_file = (request_meta.get('file_name') or '').lower()
        if explicit_table or explicit_file:
            candidate_file = os.path.basename(str(naming_metadata.get('file_name', '') or '')).lower()
            candidate_table = str(naming_metadata.get('table_name', '') or '').lower()

            if explicit_file and candidate_file != explicit_file:
                return False
            if explicit_table and explicit_table not in candidate_table:
                return False
            return True

        entity_hints = self._extract_entity_hints_from_request(user_request or '')
        if not entity_hints:
            return True

        primary_hint = ''
        for hint in entity_hints:
            cleaned = re.sub(r'[^a-z0-9]', '', (hint or '').lower())
            if cleaned and cleaned not in {'master', 'form', 'create', 'complete'}:
                primary_hint = cleaned
                break

        if not primary_hint:
            return True

        candidate_text = ' '.join([
            str(naming_metadata.get('feature_name', '') or ''),
            str(naming_metadata.get('file_name', '') or ''),
            str(naming_metadata.get('table_name', '') or ''),
            str(naming_metadata.get('title', '') or ''),
            str(naming_metadata.get('case_type', '') or ''),
        ]).lower()
        candidate_compact = re.sub(r'[^a-z0-9]', '', candidate_text)

        fallback_primary_hint = primary_hint[:-6] if primary_hint.endswith('master') else primary_hint
        candidate_matches = [
            primary_hint and primary_hint in candidate_compact,
            fallback_primary_hint and fallback_primary_hint in candidate_compact,
        ]
        return any(candidate_matches)

    def _keyword_list(self, setting_key: str, default: List[str]) -> List[str]:
        """Read keyword list from settings/env and normalize to lowercase."""
        return [
            str(token).strip().lower()
            for token in get_csv_setting(setting_key, setting_key, default=default)
            if str(token).strip()
        ]

    def _bool_setting(self, setting_key: str, default: bool = False) -> bool:
        """Read boolean flag from env/config-friendly values."""
        raw_value = os.getenv(setting_key)
        if raw_value is None:
            return default
        return str(raw_value).strip().lower() in {'1', 'true', 'yes', 'on'}

    def _parse_request_schema_cached(self, user_request: str) -> Dict:
        """
        Parse structured request once per normalized request text.
        Prevents repeated RequestSchemaParser invocations across generation phases.
        """
        normalized_request = self._normalize_request_sections(user_request or "")
        if not normalized_request or not self._should_parse_request_schema(normalized_request):
            return {}

        cached = self._request_schema_cache.get(normalized_request)
        if cached is not None:
            return dict(cached)

        try:
            from agents.utils.request_parser import RequestSchemaParser
            parsed_schema = RequestSchemaParser().parse(normalized_request) or {}
            parsed_schema = dict(parsed_schema)
            self._request_schema_cache[normalized_request] = parsed_schema
            return dict(parsed_schema)
        except Exception as parse_error:
            logger.debug(f"Structured schema parser unavailable: {parse_error}")
            self._request_schema_cache[normalized_request] = {}
            return {}

    def _matches_keywords(self, haystack_lower: str, keywords: List[str]) -> bool:
        return any(keyword in haystack_lower for keyword in keywords if keyword)

    def _mapping_setting(self, setting_key: str, default_mapping: Dict[str, str]) -> Dict[str, str]:
        """
        Read mapping from config.
        Accepted format per token: source:target (comma/semicolon/newline separated).
        """
        default_entries = [f"{k}:{v}" for k, v in (default_mapping or {}).items()]
        configured_tokens = get_csv_setting(setting_key, setting_key, default=default_entries)

        resolved_mapping = {}
        for token in configured_tokens:
            item = str(token or '').strip()
            if not item or ':' not in item:
                continue
            source, target = item.split(':', 1)
            source_key = str(source).strip().lower()
            target_value = str(target).strip()
            if source_key and target_value:
                resolved_mapping[source_key] = target_value

        if not resolved_mapping:
            return {str(k).strip().lower(): str(v).strip() for k, v in (default_mapping or {}).items()}
        return resolved_mapping

    def _detect_user_requirements(self, user_request: str) -> Dict[str, bool]:
        """
        Unified requirement detection used by both generation and validation.
        """
        normalized_request = self._normalize_request_sections(user_request or "")
        user_request_lower = normalized_request.lower()
        request_metadata = self._extract_explicit_request_metadata(normalized_request)
        requested_grid = self._extract_requested_grid(normalized_request)
        parser_features = set()
        parser_relationships = []
        parser_fields = []
        field_contract = self._extract_field_contract_from_request(normalized_request)

        if self._should_parse_request_schema(normalized_request):
            parsed_schema = self._parse_request_schema_cached(normalized_request)
            if parsed_schema:
                parser_features = {
                    str(feature or '').strip().lower()
                    for feature in (parsed_schema.get('features') or [])
                    if str(feature or '').strip()
                }
                parser_relationships = parsed_schema.get('relationships') or []
                parser_fields = parsed_schema.get('fields') or []
        chart_negative_keywords = self._keyword_list(
            'CODEGEN_CHART_NEGATIVE_KEYWORDS',
            [
                'no chart',
                'without chart',
                'do not include chart',
                'dont include chart',
                'no chart integration',
                'without chart integration'
            ]
        )
        # ✅ FIX #1: More specific dropdown detection - only trigger on explicit cascading/dynamic requests
        dropdown_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_DROPDOWN_KEYWORDS',
            [
                'cascading dropdown', 'cascading', 'dependent dropdown', 'dynamic dropdown',
                'parent child dropdown', 'parent dropdown', 'child dropdown',
                'area subarea', 'area -> subarea', 'category subcategory',
                'linked dropdown', 'dependent select', 'cascade select'
            ]
        )
        # ✅ FIX #1: Add negative keywords to prevent false positives
        dropdown_negative_keywords = self._keyword_list(
            'CODEGEN_DROPDOWN_NEGATIVE_KEYWORDS',
            [
                'dropdown: not required',
                'dropdown not required',
                'no dropdown',
                'without dropdown',
                'no cascading',
                'without cascading',
                'dynamic dropdown: not required',
                'cascading dropdown: not required'
            ]
        )
        keyboard_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_KEYBOARD_KEYWORDS',
            [
                'keyboard', 'enter key', 'navigation', 'fast entry',
                'tab key', 'shortcut', 'hotkey', 'quick entry',
                'keypress', 'key navigation', 'keyboard shortcut',
                'checkkeycode'
            ]
        )
        validation_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_VALIDATION_KEYWORDS',
            [
                'validation', 'validate',
                'email validation', 'form validation', 'input validation',
                'callback validator', 'callback validators'
            ]
        )
        select2_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_SELECT2_KEYWORDS',
            [
                'select2', 'searchable dropdown', 'professional dropdown',
                'enhanced dropdown', 'search select', 'filterable dropdown',
                'autocomplete dropdown'
            ]
        )
        select2_focus_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_SELECT2_FOCUS_KEYWORDS',
            ['select2:close', 'focus management', "select2('open')", 'focus chain']
        )
        grid_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_GRID_KEYWORDS',
            [
                'detail grid', 'detail table', 'detail rows', 'master-detail',
                'master detail', 'line item', 'line items', 'sub-table', 'sub table',
                'child records', 'detail records', 'txtcountacc'
            ]
        )
        grid_negative_keywords = self._keyword_list(
            'CODEGEN_GRID_NEGATIVE_KEYWORDS',
            [
                'detail grid: not required',
                'detail grid not required',
                'detail grid: none',
                'detail grid: n/a',
                'detail grid: not needed',
                'no detail grid',
                'without detail grid',
                'grid not required'
            ]
        )
        chart_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_CHART_KEYWORDS',
            [
                'chart integration',
                'chart of accounts',
                'insert into chart',
                'update chart',
                'delete from chart',
                'acc prefix',
                'accounting ledger',
                'ledger integration'
            ]
        )
        getcostcenter_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_GETCOSTCENTER_KEYWORDS',
            ['getcostcenter', 'cost center code', 'costcentercode']
        )
        getcostcenter_negative_keywords = self._keyword_list(
            'CODEGEN_NEGATIVE_GETCOSTCENTER_KEYWORDS',
            ['no getcostcenter', 'without getcostcenter', 'getcostcenter not required']
        )
        multidelete_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_MULTIDELETE_KEYWORDS',
            ['multi-delete', 'deleteall', 'explode(', "['major']", 'with for loop']
        )
        predelete_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_PREDELETE_KEYWORDS',
            [
                'pre-delete', 'pre delete', 'dependency check', 'dependency checks',
                'before delete', 'getrows2(', 'getrows("invoice"', 'getrows2("invoice"'
            ]
        )
        transaction_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_TRANSACTION_KEYWORDS',
            ['transaction', 'funstarttran', 'funendtran']
        )
        audit_keywords = self._keyword_list(
            'CODEGEN_REQUIRE_AUDIT_KEYWORDS',
            ['audit', 'fun_log']
        )

        chart_negative = self._matches_keywords(user_request_lower, chart_negative_keywords)
        grid_negative = self._matches_keywords(user_request_lower, grid_negative_keywords)
        grid_opt_out = bool(requested_grid.get('explicit_opt_out'))
        grid_conditional_only = bool(
            re.search(
                r'(if\s+grid\s+requested|grid\s+if\s+needed|detail\s+grid\s*\[[^\]]*if\s+needed)',
                user_request_lower,
                re.IGNORECASE
            )
        )
        grid_keyword_match = (
            self._matches_keywords(user_request_lower, grid_keywords) or
            bool(re.search(r'\bdetail\s+(grid|table|rows?)\s*\(', user_request_lower, re.IGNORECASE))
        )
        wants_grid = (
            (bool(requested_grid.get('explicit_request') and requested_grid.get('has_grid')) or
             (grid_keyword_match and not grid_conditional_only))
            and not grid_negative
            and not grid_opt_out
        )
        if 'grid' in parser_features and not grid_negative and not grid_opt_out:
            wants_grid = True

        getcostcenter_requested = self._matches_keywords(user_request_lower, getcostcenter_keywords)
        getcostcenter_negative = self._matches_keywords(user_request_lower, getcostcenter_negative_keywords)
        getcostcenter_conditional = bool(
            re.search(
                r'getcostcenter[^\n]*(if\s+[^.\n]*uses\s+it|if\s+needed|optional)',
                user_request_lower,
                re.IGNORECASE
            )
        )
        wants_getcostcenter = bool(
            getcostcenter_requested and not getcostcenter_negative and not getcostcenter_conditional
        )
        if 'getcostcenter' in parser_features and not getcostcenter_negative:
            wants_getcostcenter = True

        contract_select_fields = {
            str(item.get('name') or '').strip().lower()
            for item in field_contract
            if str(item.get('name') or '').strip()
            and any(token in str(item.get('input_type') or '').strip().lower() for token in ('select', 'dropdown', 'combo'))
        }
        parser_select_fields = {
            str(item.get('name') or '').strip().lower()
            for item in parser_fields
            if str(item.get('name') or '').strip()
            and any(token in str(item.get('input_type') or '').strip().lower() for token in ('select', 'dropdown', 'combo'))
        }
        dropdown_relationship_match = any(
            str(rel.get('type') or '').strip().lower() in {'hierarchy', 'cascading', 'dropdown'}
            for rel in parser_relationships
        )

        # ✅ FIX #1: Check for dropdown negative keywords
        dropdown_negative = self._matches_keywords(user_request_lower, dropdown_negative_keywords)
        dropdown_keyword_match = self._matches_keywords(user_request_lower, dropdown_keywords)
        dropdown_parser_match = bool(
            ('dropdown' in parser_features)
            or dropdown_relationship_match
            or contract_select_fields
            or parser_select_fields
        )

        # Structured parser/contract signals are authoritative over keyword-only negatives.
        wants_dropdown = bool((dropdown_keyword_match or dropdown_parser_match) and not (dropdown_negative and not dropdown_parser_match))

        wants_formvalidation = bool(
            self._matches_keywords(user_request_lower, validation_keywords)
            or ('validation' in parser_features)
            or any(bool(item.get('required')) for item in field_contract)
        )
        wants_select2 = bool(
            self._matches_keywords(user_request_lower, select2_keywords)
            or ('select2' in parser_features)
        )

        return {
            'wants_dropdown': wants_dropdown,
            'wants_keyboard': self._matches_keywords(user_request_lower, keyboard_keywords),
            'wants_formvalidation': wants_formvalidation,
            'wants_select2': wants_select2,
            'explicit_select2_focus_request': self._matches_keywords(user_request_lower, select2_focus_keywords),
            'wants_grid': wants_grid,
            'wants_chart': (not chart_negative) and self._matches_keywords(user_request_lower, chart_keywords),
            'wants_getcostcenter': wants_getcostcenter,
            'wants_multidelete': self._matches_keywords(user_request_lower, multidelete_keywords),
            'wants_predelete': self._matches_keywords(user_request_lower, predelete_keywords),
            'wants_transactions': self._matches_keywords(user_request_lower, transaction_keywords),
            'wants_audit': self._matches_keywords(user_request_lower, audit_keywords),
            'grid_opt_out': grid_opt_out,
            'getcostcenter_conditional': getcostcenter_conditional,
            'requested_entity': str(request_metadata.get('effective_entity') or ''),
            'detected_features': sorted(parser_features),
        }

    def _extract_field_names_from_line(self, line: str) -> List[str]:
        """Extract one or more field identifiers from a bullet line."""
        cleaned = re.sub(r'^\s*(?:[-*•]\s*|\d+[.)]\s*)', '', line or '').strip()
        if not cleaned:
            return []

        # 🔥 FIX: Handle pipe-separated format: "SubArea_Code | DB: VARCHAR(20) | Input: textbox"
        if '|' in cleaned:
            # Extract first segment before first pipe (that's the field name)
            first_segment = cleaned.split('|')[0].strip()
            # Extract field name from first segment
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', first_segment)
            if match:
                return [match.group(1)]
        
        # Drop descriptive notes while keeping the field identifiers.
        cleaned = re.sub(r'\([^)]*\)', '', cleaned)
        cleaned = re.sub(r'\s+-\s+.*$', '', cleaned)
        pieces = re.split(r',|\band\b', cleaned, flags=re.IGNORECASE)

        ignore_tokens = set(
            token.lower() for token in get_csv_setting(
                'CODEGEN_FIELD_IGNORE_TOKENS',
                'CODEGEN_FIELD_IGNORE_TOKENS',
                default=[
                    'master', 'fields', 'field', 'detail', 'grid', 'table', 'tables',
                    'with', 'and', 'or', 'auto', 'ajax', 'required', 'readonly',
                    'textarea', 'dropdown', 'select2', 'text', 'danger', 'from', 'via',
                    'functions', 'contact', 'person', 'company', 'standard', 'patterns',
                    'rules', 'module', 'details', 'output', 'pre', 'transactions',
                    'audit', 'session', 'multi', 'formvalidation', 'checkkeycode',
                    'cascading', 'hierarchical', 'level', 'one', 'two', 'three', 'must',
                    'create', 'read', 'update', 'delete', 'operation', 'operations', 'crud',
                    'db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue',
                    'funstarttran', 'funendtran', 'fun_log',
                    'comp_code', 'user_id', 'login_id', 'canonical', 'title', 'file', 'name',
                    'not', 'none', 'na', 'applicable'
                ]
            )
        )

        extracted = []
        for piece in pieces:
            candidate = piece.strip().strip(':').strip()
            if not candidate:
                continue

            candidate = re.sub(r'\s+(with|via|from|using|where)\b.*$', '', candidate, flags=re.IGNORECASE).strip()
            match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', candidate)
            if not match:
                continue

            field_name = match.group(1)
            if field_name.lower() in ignore_tokens:
                continue

            extracted.append(field_name)

        return self._unique_preserve_order(extracted)

    def _normalize_user_requested_fields(self, raw_fields: List[str]) -> List[str]:
        """Normalize user-requested field names and drop descriptive fragments."""
        if not raw_fields:
            return []

        ignore_tokens = set(
            token.lower() for token in get_csv_setting(
                'CODEGEN_FIELD_IGNORE_TOKENS',
                'CODEGEN_FIELD_IGNORE_TOKENS',
                default=[
                    'master', 'fields', 'field', 'detail', 'grid', 'table', 'tables',
                    'with', 'and', 'or', 'auto', 'ajax', 'required', 'readonly',
                    'textarea', 'dropdown', 'select2', 'text', 'danger', 'from', 'via',
                    'functions', 'contact', 'person', 'company', 'standard', 'patterns',
                    'rules', 'module', 'details', 'output', 'pre', 'transactions',
                    'audit', 'session', 'multi', 'formvalidation', 'checkkeycode',
                    'cascading', 'hierarchical', 'level', 'one', 'two', 'three', 'must',
                    'create', 'read', 'update', 'delete', 'operation', 'operations', 'crud',
                    'db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue',
                    'funstarttran', 'funendtran', 'fun_log',
                    'comp_code', 'user_id', 'login_id', 'canonical', 'title', 'file', 'name',
                    'not', 'none', 'na', 'applicable'
                ]
            )
        )

        normalized = []
        for raw_field in raw_fields:
            candidate = str(raw_field or '').strip().strip(':').strip().strip('"\'')
            if not candidate:
                continue

            candidate = re.sub(r'^\s*(?:[-*â€¢]\s*|\d+[.)]\s*)', '', candidate)
            candidate = re.sub(r'\s+-\s+.*$', '', candidate)
            candidate = re.sub(r'\([^)]*\)', '', candidate)
            candidate = re.sub(r'\(.*$', '', candidate).rstrip(')').strip()
            candidate = re.sub(r'\s+(with|via|from|using|where)\b.*$', '', candidate, flags=re.IGNORECASE).strip()
            if not candidate:
                continue

            match = re.match(r'^([A-Za-z][A-Za-z0-9_]*)', candidate)
            if not match:
                continue

            field_name = match.group(1)
            if field_name.lower() in ignore_tokens:
                continue

            normalized.append(field_name)

        return self._unique_preserve_order(normalized)

    def _extract_requested_grid(self, user_request: str) -> Dict:
        """Extract explicit detail-grid requirements from a structured prompt."""
        request_text = self._normalize_request_sections(user_request)
        section_lines = self._extract_bullet_section(
            request_text,
            ('detail grid', 'detail fields', 'detail table', 'grid')
        )

        grid_info = {
            'has_grid': False,
            'sub_table': None,
            'grid_fields': [],
            'txtcount_var': 'TXTCOUNTACC',
            'loop_var': 'i',
            'explicit_request': False,
            'explicit_opt_out': False
        }

        explicit_opt_out = bool(
            re.search(
                r'(?im)^\s*(?:[-*]\s*)?detail\s+grid(?:\s*\([^)]*\))?\s*:\s*'
                r'(?:not\s+required|none|no|n/?a|not\s+needed|not\s+applicable)\b',
                request_text
            ) or re.search(
                r'\bdetail\s+grid\b[^\n]{0,80}\bnot\s+required\b',
                request_text,
                re.IGNORECASE
            )
        )
        if explicit_opt_out:
            grid_info['explicit_opt_out'] = True
            logger.info("⚪ Detail grid explicitly marked as not required in user request")
            return grid_info

        for line in section_lines:
            line_text = str(line or '').strip().lower()
            if re.search(r'\b(not\s+required|not\s+needed|not\s+applicable|none|n/?a)\b', line_text):
                grid_info['explicit_opt_out'] = True
                logger.info("⚪ Detail grid bullet marked as not required in user request")
                return grid_info

        explicit_grid_request = bool(
            re.search(
                r'\b(detail\s+grid|detail\s+table|detail\s+rows?|master[-\s]?detail|line\s+items?|detail\s+records?)\b',
                request_text,
                re.IGNORECASE
            )
        )
        conditional_grid_request = bool(
            re.search(r'\b(if\s+needed|optional)\b', request_text, re.IGNORECASE)
        )

        heading_match = re.search(r'detail\s+grid\s*\(\s*(tbl[a-z0-9_]+)\s*\)', request_text, re.IGNORECASE)
        if heading_match:
            grid_info['sub_table'] = heading_match.group(1).strip()
        else:
            sub_table_match = re.search(
                r'(?:detail\s+table|sub[-\s]?table)\s*[:=]\s*(tbl[a-z0-9_]+)',
                request_text,
                re.IGNORECASE
            )
            if sub_table_match:
                grid_info['sub_table'] = sub_table_match.group(1)

        for line in section_lines:
            grid_info['grid_fields'].extend(self._extract_field_names_from_line(line))

        grid_info['grid_fields'] = self._unique_preserve_order(grid_info['grid_fields'])
        if grid_info['sub_table'] or grid_info['grid_fields']:
            grid_info['has_grid'] = True
            grid_info['explicit_request'] = True
        elif explicit_grid_request and not conditional_grid_request:
            grid_info['has_grid'] = True
            grid_info['explicit_request'] = True
        elif explicit_grid_request and conditional_grid_request:
            logger.info("⚪ Detail grid mentioned as conditional (if needed/optional); treating as non-mandatory")

        return grid_info

    def _extract_required_fields_from_request(self, user_request: str) -> List[str]:
        """Extract fields explicitly marked as required by the user prompt."""
        request_text = self._normalize_request_sections(user_request)
        required_fields: List[str] = []

        master_field_lines = self._extract_bullet_section(
            request_text,
            ('master fields', 'form fields', 'fields')
        )
        for line in master_field_lines:
            if not self._line_looks_like_field_definition(line):
                continue
            if re.search(r'required\s*:\s*(yes|true|mandatory)\b', line, re.IGNORECASE):
                required_fields.extend(self._extract_field_names_from_line(line))

        # Capture constraints like: "A, B, C must not be empty"
        for match in re.finditer(
            r'([A-Za-z_][A-Za-z0-9_,\s]+?)\s+must\s+not\s+be\s+empty',
            request_text,
            re.IGNORECASE
        ):
            required_fields.extend(self._extract_field_names_from_line(match.group(1)))

        return self._unique_preserve_order(required_fields)

    def _extract_unique_fields_from_request(self, user_request: str) -> List[str]:
        """Extract fields that must be unique, based on business validation rules."""
        request_text = self._normalize_request_sections(user_request)
        unique_fields: List[str] = []

        validation_lines = self._extract_bullet_section(
            request_text,
            ('business validations', 'business validation', 'validations')
        )
        if not validation_lines:
            validation_lines = [line.strip() for line in request_text.splitlines() if line.strip()]

        for line in validation_lines:
            line_text = str(line or '').strip()
            if 'unique' not in line_text.lower():
                continue
            match = re.search(
                r'([A-Za-z_][A-Za-z0-9_]*)\s+must\s+be\s+unique',
                line_text,
                re.IGNORECASE
            )
            if match:
                unique_fields.append(match.group(1).strip())

        return self._unique_preserve_order(unique_fields)

    def _request_requires_email_validation(self, user_request: str) -> bool:
        request_text = user_request or ''
        return bool(
            re.search(r'email[^\n]{0,80}(validate|validation|format)', request_text, re.IGNORECASE)
        )

    def _extract_business_validations_for_prompt(self, user_request: str) -> str:
        """Extract business validations and format as REQUIRED section for LLM prompt."""
        if not user_request:
            return ""

        request_text = self._normalize_request_sections(user_request)

        bv_match = re.search(
            r'(?i)(?:business\s*validations?|business\s*rules?)[:\s]*(.*?)(?=required|operations|output|$)',
            request_text,
            re.DOTALL
        )
        if not bv_match:
            return ""

        bv_text = bv_match.group(1).strip()
        if not bv_text:
            return ""

        lines = []
        unique_check = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s+unique\s+within\s+comp_code', bv_text, re.IGNORECASE)
        if unique_check:
            field_name = unique_check.group(1).strip()
            lines.append(f"- {field_name}: Must be unique within same Comp_Code (check with getrows before insert/update)")

        email_check = re.search(r'email\s+(format|validate|validation)', bv_text, re.IGNORECASE)
        if email_check:
            lines.append(r"- Email: Must validate format using PHP filter_var($Email, FILTER_VALIDATE_EMAIL)")

        numeric_check = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s+numeric', bv_text, re.IGNORECASE)
        if numeric_check:
            field_name = numeric_check.group(1).strip()
            lines.append(f"- {field_name}: Must be numeric only (is_numeric() check)")

        if not lines:
            return ""

        return "\n=== REQUIRED BUSINESS VALIDATIONS - MUST IMPLEMENT ALL ===\n" + '\n'.join(lines) + "\n=== END REQUIRED VALIDATIONS ==="

    def _extract_canonical_form_metadata_with_parser(
        self, 
        user_request: str, 
        company_example: str, 
        example_file_path: str = ""
    ) -> Dict:
        """
        PHASE 2.1: Extract canonical metadata using RequestSchemaParser first,
        then fall back to heuristic extraction if parsing fails.
        
        This provides deterministic parsing when user provides structured request,
        while maintaining backward compatibility with unstructured requests.
        """
        metadata = {
            'file_name': '',
            'file_path': example_file_path or '',
            'feature_name': '',
            'table_name': '',
            'title': '',
            'case_type': '',
            'primary_key': '',
            'parsed_fields': [],
            'parsed_relationships': [],
            'parsed_dependencies': [],
            'parsed_features': [],
            'parsing_method': 'heuristic'  # Track which method was used
        }
        
        # Try parser first if user_request is provided
        if user_request and user_request.strip() and self._should_parse_request_schema(user_request):
            schema = self._parse_request_schema_cached(user_request)
            if schema:
                # Use parsed values
                metadata['table_name'] = schema.get('table', '')
                metadata['file_name'] = schema.get('filename', '')
                metadata['title'] = schema.get('title', '')
                metadata['case_type'] = schema.get('case_type', '')
                metadata['primary_key'] = schema.get('primary_key', '')
                metadata['parsed_fields'] = schema.get('fields', [])
                metadata['parsed_relationships'] = schema.get('relationships', [])
                metadata['parsed_dependencies'] = schema.get('dependencies', [])
                metadata['parsed_features'] = schema.get('features', [])
                metadata['parsing_method'] = 'schema_parser'
                
                # Extract feature_name from file_name
                if metadata['file_name'].lower().startswith('frm') and metadata['file_name'].lower().endswith('.php'):
                    metadata['feature_name'] = metadata['file_name'][3:-4]
                
                logger.info(f"✅ PHASE 2.1: Used RequestSchemaParser for canonical metadata")
                logger.info(f"   Parsed {len(metadata['parsed_fields'])} fields, {len(metadata['parsed_relationships'])} relationships")
                
                return metadata
            logger.warning("⚠️ RequestSchemaParser parsing unavailable; falling back to heuristic extraction")
        
        # Fallback to heuristic extraction
        heuristic_metadata = self._extract_canonical_form_metadata(company_example, example_file_path)
        metadata.update(heuristic_metadata)
        metadata['parsing_method'] = 'heuristic'
        
        return metadata

    def _extract_canonical_form_metadata(self, company_example: str, example_file_path: str = "") -> Dict:
        """Extract canonical file/table/title naming from the company example."""
        source_text = company_example or ''

        if example_file_path and os.path.exists(example_file_path):
            try:
                with open(example_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    source_text = f.read()
            except Exception as read_error:
                logger.warning(f"Could not read example file for canonical naming: {read_error}")

        metadata = {
            'file_name': '',
            'file_path': example_file_path or '',
            'feature_name': '',
            'table_name': '',
            'title': '',
            'case_type': '',
        }

        form2_match = re.search(r'\$form2\s*=\s*["\']([^"\']+\.php)["\']', source_text, re.IGNORECASE)
        if form2_match:
            metadata['file_name'] = os.path.basename(form2_match.group(1).strip())

        table_match = re.search(r'\$table\s*=\s*["\']([^"\']+)["\']', source_text, re.IGNORECASE)
        if table_match:
            metadata['table_name'] = table_match.group(1).strip()

        title_match = re.search(r'\$title\s*=\s*["\']([^"\']+)["\']', source_text, re.IGNORECASE)
        if title_match:
            metadata['title'] = title_match.group(1).strip()

        case_type_match = re.search(r'CaseType=([^"\']+)', source_text, re.IGNORECASE)
        if case_type_match:
            metadata['case_type'] = case_type_match.group(1).strip()

        if not metadata['file_name'] and example_file_path:
            metadata['file_name'] = os.path.basename(example_file_path)

        if metadata['file_name'].lower().startswith('frm') and metadata['file_name'].lower().endswith('.php'):
            metadata['feature_name'] = metadata['file_name'][3:-4]

        if not metadata['feature_name'] and metadata['title']:
            metadata['feature_name'] = metadata['title'].replace(' ', '_')

        if not metadata['title'] and metadata['feature_name']:
            metadata['title'] = metadata['feature_name'].replace('_', ' ')

        if not metadata['case_type'] and metadata['title']:
            metadata['case_type'] = metadata['title']

        if not metadata['table_name'] and metadata['feature_name']:
            metadata['table_name'] = f"tbl{metadata['feature_name'].replace('_', '').lower()}"

        return metadata

    def _merge_with_template(self, php_logic: str, form_fields: str, 
                              head_scripts: str = "", body_onload: str = "",
                              form_validation_fields: str = "",
                              select2_handlers: str = "") -> str:
        """
        Merge LLM-generated VARIABLE parts with FIXED template.
        Uses DynamicFormTemplate for merging.
        """
        if self._template:
            return self._template.merge_with_generated(
                php_logic=php_logic,
                form_fields=form_fields,
                head_scripts=head_scripts,
                body_onload=body_onload,
                form_validation_fields=form_validation_fields,
                select2_handlers=select2_handlers,
                entity_js=''
            )
        
        # Fallback: manual merge if template not loaded
        parts = []
        parts.append(php_logic)
        parts.append("?>")
        parts.append("")
        parts.append(form_fields)
        return '\n'.join(parts)

    def _should_use_controlled_assembly(
        self,
        user_request: str,
        request_metadata: Dict[str, str],
        fixed_parts: Dict[str, str]
    ) -> bool:
        """
        Strict company architecture:
        - fixed framework comes from codebase/template
        - LLM only generates entity-specific sections
        """
        if not self._bool_setting('CODEGEN_USE_CONTROLLED_ASSEMBLY', True):
            return False

        fixed_parts = fixed_parts or {}
        template_ready = bool(
            fixed_parts.get('html_head') or
            fixed_parts.get('body_start') or
            fixed_parts.get('body_end') or
            self._template
        )
        if not template_ready:
            return False
        return True

    def _build_system_message(self) -> str:
        """
        ✅ ACTION 3 FIX: Enforce tagged output format at system level with FULL TAGS_FORMAT.
        System message is read first and followed more strictly by LLM.
        """
        return """You are a PHP code generator that MUST return code in TAGGED STRUCTURE ONLY.

⚠️⚠️⚠️ CRITICAL OUTPUT FORMAT - READ THIS FIRST ⚠️⚠️⚠️

YOU MUST START YOUR RESPONSE WITH THESE EXACT TAGS:

<<<VARIABLE_INIT_PHP>>>
<?php
// ALL your PHP variables and initialization
?>
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
<?php
// Save, Update, Delete handlers with funStartTran/funEndTran
?>
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
<?php
// GetMaxID and other AJAX handlers
?>
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<!-- ALL form fields with Bootstrap grid classes -->
<<<END_FORM_FIELDS_HTML>>>

<<<ENTITY_JS>>>
<script>
// formValidation + maxid() function
</script>
<<<END_ENTITY_JS>>>

⚠️ DO NOT use markdown ```php blocks!
⚠️ START IMMEDIATELY with <<<VARIABLE_INIT_PHP>>>
⚠️ ALL 5 SECTIONS ARE MANDATORY!

CRITICAL RULES:
- First character must be < from <<<VARIABLE_INIT_PHP>>>
- NEVER return flat/unstructured PHP code
- Missing tags = INVALID OUTPUT = SYSTEM REJECTION
- Each section must have real content — no empty sections

Format enforcement is MANDATORY."""

    def _build_controlled_sections_prompt(
        self,
        intent: Dict,
        user_request: str,
        company_fields: Dict,
        naming_metadata: Dict,
        hierarchy_pattern: Dict,
        related_tables: List[Dict],
        cascading_logic: Dict,
        grid_pattern: Dict,
        template_code: str = "",
        previous_errors: List[str] = None
    ) -> str:
        """
        Ask the LLM for dynamic sections only.
        The outer company framework is injected deterministically by the assembler.
        """
        request_metadata = self._extract_explicit_request_metadata(user_request or '')
        requested_fields = (
            (company_fields or {}).get('user_requested_fields')
            or (company_fields or {}).get('form_fields')
            or []
        )
        primary_key = (company_fields or {}).get('primary_key') or 'Code'
        table_name = (naming_metadata or {}).get('table_name') or request_metadata.get('table_name') or 'tblentity'
        file_name = (naming_metadata or {}).get('file_name') or request_metadata.get('file_name') or 'frmEntity.php'
        title = (naming_metadata or {}).get('title') or request_metadata.get('title') or 'Entity'
        case_type = (
            (naming_metadata or {}).get('case_type')
            or request_metadata.get('case_type')
            or title
        )
        case_token = re.sub(r'[^A-Za-z0-9_]', '', str(case_type or title))
        request_contract = self._build_request_contract(
            user_request=user_request,
            naming_metadata=naming_metadata,
            company_fields=company_fields,
            hierarchy_pattern=hierarchy_pattern,
            related_tables=related_tables,
            grid_pattern=grid_pattern,
        )
        contract_text = self._format_request_contract(request_contract)

        dependency_lines = []
        for rel in related_tables or []:
            rel_table = str(rel.get('table', '')).strip()
            rel_field = str(rel.get('field', '')).strip()
            rel_message = str(rel.get('message', '')).strip()
            if rel_table:
                line = f"- {rel_table}.{rel_field or primary_key}"
                if rel_message:
                    line += f" -> {rel_message}"
                dependency_lines.append(line)

        hierarchy_rules = "None"
        if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical'):
            hierarchy_rules = (
                f"- parent_request_param: {hierarchy_pattern.get('parent_request_param')}\n"
                f"- parent_html_field: {hierarchy_pattern.get('parent_js_field_id') or hierarchy_pattern.get('parent_field')}\n"
                f"- parent_db_field: {hierarchy_pattern.get('parent_field')}\n"
                f"- separator: {hierarchy_pattern.get('separator', '-')}\n"
                f"- code_length: {hierarchy_pattern.get('code_length', 2)}"
            )

        grid_rules = "None"
        if grid_pattern and grid_pattern.get('has_grid'):
            grid_rules = (
                f"- sub_table: {grid_pattern.get('sub_table')}\n"
                f"- grid_fields: {', '.join(grid_pattern.get('grid_fields', []))}\n"
                f"- txtcount_var: {grid_pattern.get('txtcount_var', 'TXTCOUNTACC')}\n"
                f"- loop_var: {grid_pattern.get('loop_var', 'i')}"
            )

        cascading_rules = "None"
        if cascading_logic and cascading_logic.get('has_cascading'):
            cascading_rules = (
                f"- parent_dropdown: {cascading_logic.get('parent_dropdown')}\n"
                f"- child_dropdown: {cascading_logic.get('child_dropdown')}\n"
                "- include Select2 close/open focus flow in ENTITY_JS"
            )
        
        # ✅ NEW FIX: Add dropdown fields from user request
        # User can specify: "Department_Code(select, required), Designation_Code(select, required)"
        requested_dropdowns = self._extract_dropdown_fields_from_request(user_request)
        if requested_dropdowns:
            if cascading_rules == "None":
                cascading_rules = "REQUESTED DROPDOWNS:\n"
            else:
                cascading_rules += "\nREQUESTED DROPDOWNS:\n"
            for dd_field, dd_table in requested_dropdowns:
                cascading_rules += f"- {dd_field} -> {dd_table} (populate via AJAX)\n"
            logger.info(f"✅ Added {len(requested_dropdowns)} requested dropdowns to prompt")

        template_excerpt = self._extract_template_candidate_code(template_code or "") or (template_code or "")
        template_excerpt = self._trim_prompt_to_limit(
            template_excerpt.strip(),
            get_int_setting(
                'CODEGEN_CONTROLLED_TEMPLATE_SNIPPET_MAX_CHARS',
                'CODEGEN_CONTROLLED_TEMPLATE_SNIPPET_MAX_CHARS',
                9000,
                min_value=2000,
                max_value=30000
            ),
            label='controlled template snippet'
        )

        retry_notes = ""
        if previous_errors:
            retry_notes = (
                "\nPREVIOUS ATTEMPT ISSUES TO FIX EXACTLY:\n"
                + '\n'.join(f"- {item}" for item in previous_errors if str(item).strip())
            )

        field_list = ', '.join(requested_fields) if requested_fields else primary_key

        business_validations = self._extract_business_validations_for_prompt(user_request or '')
        master_detail_rules = self._build_master_detail_crud_instruction(request_contract)
        ajax_handlers_rules = self._build_ajax_handlers_instruction(request_contract)
        predelete_placement_rule = self._build_predelete_placement_rule()

        # FIX #4: Add CRITICAL tags reminder at the very top
        CRITICAL_TAGS_REMINDER = """
⚠️⚠️⚠️ CRITICAL OUTPUT FORMAT - READ THIS FIRST ⚠️⚠️⚠️

YOU MUST START YOUR RESPONSE WITH THESE EXACT TAGS:

<<<VARIABLE_INIT_PHP>>>
<?php
// ALL your PHP variables and initialization
?>
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
<?php
// Save, Update, Delete handlers with funStartTran/funEndTran
?>
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
<?php
// GetMaxID and other AJAX handlers
?>
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<!-- ALL form fields with Bootstrap grid classes -->
<<<END_FORM_FIELDS_HTML>>>

<<<ENTITY_JS>>>
<script>
// formValidation + maxid() function
</script>
<<<END_ENTITY_JS>>>

⚠️ DO NOT use markdown ```php blocks!
⚠️ START IMMEDIATELY with <<<VARIABLE_INIT_PHP>>>
⚠️ ALL 5 SECTIONS ARE MANDATORY!

═══════════════════════════════════════════════════════════════════════════════
"""

        prompt = CRITICAL_TAGS_REMINDER + f"""
🚨 MANDATORY OUTPUT FORMAT - NO EXCEPTIONS 🚨

YOU MUST USE THIS EXACT TAGGED STRUCTURE FOR YOUR OUTPUT.
FLAT/UNSTRUCTURED CODE WILL BE REJECTED IMMEDIATELY.

REQUIRED TAGS (ALL 5 SECTIONS ARE MANDATORY):
<<<VARIABLE_INIT_PHP>>> ... <<<END_VARIABLE_INIT_PHP>>>
<<<CRUD_LOGIC_PHP>>> ... <<<END_CRUD_LOGIC_PHP>>>
<<<AJAX_HANDLERS_PHP>>> ... <<<END_AJAX_HANDLERS_PHP>>>
<<<FORM_FIELDS_HTML>>> ... <<<END_FORM_FIELDS_HTML>>>
<<<ENTITY_JS>>> ... <<<END_ENTITY_JS>>>

⚠️ CRITICAL WARNINGS:
- Missing ANY tag = SYSTEM FAILURE
- Flat PHP code without tags = IMMEDIATE REJECTION
- This is NOT optional - it is MANDATORY
- Wrong format = Your output will be discarded

EXAMPLE OF CORRECT OUTPUT (FOLLOW THIS EXACTLY):

<<<VARIABLE_INIT_PHP>>>
\\$Code = "";
\\$Name = "";
\\$Description = "";
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Edit') {{
    \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
    \$obj = db_getRecord(\$table, \$filter);
    if (\\$obj) {{
        \\$Code = \\$obj['{primary_key}'];
        \\$Name = \\$obj['Name'];
        \\$Description = \\$obj['Description'];
    }}
}}
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Delete') {{
    \$check = getrows('dependent_table', ' foreign_key', add(\$_REQUEST['{primary_key}']));
    if (\\$check > 0) {{
        echo "<script>alert('Cannot delete: record is being used');</script>";
        exit;
    }}
    funStartTran();
    \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
    db_delete(\$table, \$filter);
    funEndTran();
    echo "<script>window.location='{file_name}';</script>";
    exit;
}}

if (isset(\\$_REQUEST['Action']) && (\\$_REQUEST['Action'] == 'Save' || \\$_REQUEST['Action'] == 'Update')) {{
    funStartTran();
    if (\\$_REQUEST['Action'] == 'Save') {{
        db_insert(\\$table, \\$_REQUEST);
    }} else {{
        \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
        db_update(\$table, \$_REQUEST, \$filter);
    }}
    funEndTran();
    echo "<script>window.location='{file_name}';</script>";
    exit;
}}
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'GetMaxID') {{
    \\$maxId = getvalue("SELECT MAX({primary_key}) FROM {table_name}");
    echo \\$maxId + 1;
    exit;
}}
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<div class="page">
    <div class="page-content">
        <div class="panel">
            <div class="panel-heading">
                <h3 class="panel-title">{title}</h3>
            </div>
            <div class="panel-body">
                <div class="form-group">
                    <label class="control-label col-md-3">{primary_key}</label>
                    <div class="col-md-6">
                        <input type="text" class="form-control" name="{primary_key}" id="{primary_key}" readonly />
                    </div>
                </div>
                <div class="form-group">
                    <label class="control-label col-md-3">Name <span class="required">*</span></label>
                    <div class="col-md-6">
                        <input type="text" class="form-control" name="Name" id="Name" required />
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
<<<END_FORM_FIELDS_HTML>>>

<<<FORM_VALIDATION_FIELDS>>>
{primary_key}: {{
    validators: {{
        notEmpty: {{ message: '{primary_key} is required' }}
    }}
}},
Name: {{
    validators: {{
        notEmpty: {{ message: 'Name is required' }}
    }}
}}
<<<END_FORM_VALIDATION_FIELDS>>>

<<<SELECT2_HANDLERS>>>
\\$('.select2').select2();
\\$(document).off('select2:close.company').on('select2:close.company', '.select2-hidden-accessible', function(){{
    var fieldId = this.id || '';
    if (fieldId) {{
        setTimeout(function(){{
            var target = document.getElementById(fieldId);
            if (target) {{
                target.focus();
            }}
        }}, 0);
    }}
}});
<<<END_SELECT2_HANDLERS>>>

<<<ENTITY_JS>>>
if (typeof window.formInitialized === 'undefined') {{
    window.formInitialized = true;
    
    function maxid() {{
        \\$.ajax({{
            url: '{file_name}',
            data: {{ Action: 'GetMaxID' }},
            success: function(data) {{
                \\$('#{primary_key}').val(data);
            }}
        }});
    }}
    
    \\$(document).ready(function() {{
        maxid();
        
        \\$('#{file_name.replace('.php', '')}').formValidation({{
            framework: 'bootstrap',
            fields: {{
                {primary_key}: {{
                    validators: {{
                        notEmpty: {{ message: '{primary_key} is required' }}
                    }}
                }},
                Name: {{
                    validators: {{
                        notEmpty: {{ message: 'Name is required' }}
                    }}
                }}
            }}
        }});
    }});
}}
<<<END_ENTITY_JS>>>

NOW YOU MUST GENERATE YOUR CODE IN THIS EXACT TAGGED FORMAT.

=== GENERATION INSTRUCTIONS ===

Generate ONLY the dynamic sections for a company PHP form assembler.
Return EXACTLY the tagged blocks and nothing else.

STRICT RULES:
- Do NOT output session_start, config includes, topmenu, sidemenu, footer include, DOCTYPE, <html>, <head>, <body>, <form>, footer script src tags, btnsave_click(), checkKeycode(), companySharedInit(), or AJAX reinitialization boilerplate.
- The assembler injects all fixed company framework blocks.
- You ONLY generate entity-specific dynamic content.
- Use exact canonical metadata and exact requested fields.
- Treat the structured contract below as law: no extra fields, no missing fields, no renamed fields.
- Use company database helpers: funStartTran, funEndTran, db_insert, db_update, db_delete, db_getRecord, getrows, getvalue, fun_log.
- Variable naming is strict: use $columns, $filter, $table, $Code; NEVER use $record, $data, $where, or $id.
- FORM_FIELDS_HTML must contain only inner form groups. Do not open/close <form>.
- ENTITY_JS must contain only entity-specific JS/config such as maxid(), cascading dropdown loaders, window.companyFieldOrder, window.companyValidationFields, window.companyFormOnLoad, and optional window.companyAfterInit.
- ENTITY_JS must NOT define btnsave_click, checkKeycode, companySharedInit, or any shared include/base script code.
- Escape rendered user-facing values and option labels with htmlspecialchars(..., ENT_QUOTES).
- Enforce field type mapping exactly: select=>dropdown/select, varchar=>text input, int=>numeric input, boolean/tinyint(1)=>checkbox.

=== MANDATORY COMPANY FUNCTIONS (CRITICAL) ===

Your generated code MUST include ALL 8 of these company database functions with EXACT casing:

1. db_insert() - for INSERT operations
2. db_update() - for UPDATE operations  
3. db_delete() - for DELETE operations
4. db_getRecord() - CRITICAL: Use capital 'R', NOT db_getrecord - for SELECT single record
5. getrows() - CRITICAL: Required for pre-delete dependency checks
6. getvalue() - for fetching single values
7. funStartTran() - to start database transactions
8. funEndTran() - to commit database transactions

CRITICAL CASING NOTES:
- Use db_getRecord with capital 'R' (NOT db_getrecord with lowercase 'r')
- Use getrows with lowercase 'r' (NOT getRows with capital 'R')

REQUIRED USAGE PATTERNS:
- For Edit action: Use db_getRecord() to fetch existing record
- For Delete action: MUST use getrows() to check dependencies BEFORE calling db_delete()
- For Save/Update: Wrap db_insert/db_update calls with funStartTran() and funEndTran()
- For GetMaxID: Use getvalue() to fetch MAX(primary_key) and return next value

MANDATORY CRUD EXAMPLES (YOU MUST IMPLEMENT ALL OF THESE):

Example 1 - Edit Action (MANDATORY - use db_getRecord):
```php
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Edit') {{
    \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
    \$obj = db_getRecord(\$table, \$filter);
}}
```

Example 2 - Delete Action (MANDATORY - use getrows for dependency checks):
```php
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Delete') {{
    // Check dependencies FIRST using getrows()
    \\$check = getrows('dependent_table', ' foreign_key', add(\\$code));
    if (\\$check > 0) {{
        echo "<script>alert('Cannot delete: record is being used');</script>";
        exit;
    }}
    // Only delete if no dependencies
    funStartTran();
    \\$filter = " {primary_key}='" . add(\\$code) . "'";
    db_delete(\\$table, \\$filter);
    funEndTran();
}}
```

Example 3 - Save/Update Actions (MANDATORY):
```php
if (isset(\\$_REQUEST['Action']) && (\\$_REQUEST['Action'] == 'Save' || \\$_REQUEST['Action'] == 'Update')) {{
    funStartTran();
    if (\\$_REQUEST['Action'] == 'Save') {{
        db_insert(\\$table, \\$_REQUEST);
    }} else {{
        db_update(\\$table, \\$_REQUEST, "{primary_key} = ?", [\\$_REQUEST['{primary_key}']]);
    }}
    funEndTran();
}}
```

Example 4 - GetMaxID AJAX Handler (MANDATORY - use getvalue):
```php
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'GetMaxID') {{
    \\$maxId = getvalue("SELECT MAX({primary_key}) FROM {table_name}");
    echo \\$maxId + 1;
    exit;
}}
```

=== REQUIRED STRUCTURAL COMPONENTS (CRITICAL) ===

Your generated HTML and JavaScript MUST include these 3 structural components:

1. PAGE_CONTAINER STRUCTURE (in FORM_FIELDS_HTML):
   - Wrap ALL form content in this exact div structure:
   ```html
   <div class="page">
       <div class="page-content">
           <div class="panel">
               <!-- Your form fields go here -->
           </div>
       </div>
   </div>
   ```
   - This structure is MANDATORY for AJAX navigation compatibility

2. DELEGATED EVENT HANDLERS (in ENTITY_JS):
   - Use .on(event, selector, handler) pattern for ALL event handlers
   - This is MANDATORY for dynamic DOM/AJAX navigation compatibility
   - Example:
   ```javascript
   \\$(document).on('click', '#btnSave', function() {{
       // handler code
   }});
   \\$(document).on('change', '#Region_Code', function() {{
       // handler code
   }});
   ```
   - DO NOT use direct event binding like \\$('#btnSave').click()

3. AJAX REINITIALIZATION GUARD (in ENTITY_JS):
   - Add this guard to prevent duplicate script execution on AJAX reloads:
   ```javascript
   if (typeof window.formInitialized === 'undefined') {{
       window.formInitialized = true;
       // Your initialization code here
   }}
   ```
   - This prevents scripts from running multiple times during AJAX navigation

4. MAXID JAVASCRIPT FUNCTION (in ENTITY_JS):
   - MANDATORY: Include maxid() function to call GetMaxID AJAX handler
   - Example:
   ```javascript
   function maxid() {{
       \\$.ajax({{
           url: '{file_name}',
           data: {{ Action: 'GetMaxID' }},
           success: function(data) {{
               \\$('#{primary_key}').val(data);
           }}
       }});
   }}
   ```
   - This function must be called on form load to auto-generate primary key

VALIDATION CHECKLIST (verify before returning your code):
✓ All 8 mandatory company functions are present with correct casing
✓ db_getRecord uses capital 'R' (not db_getrecord)
✓ db_getRecord() is used in Edit action to fetch existing record
✓ getrows() is used for pre-delete dependency checks in Delete action
✓ getvalue() is used in GetMaxID AJAX handler
✓ Save/Update actions wrap db_insert/db_update with funStartTran/funEndTran
✓ GetMaxID AJAX handler is implemented in AJAX_HANDLERS_PHP
✓ maxid() JavaScript function is implemented in ENTITY_JS
✓ page_container structure (page/page-content/panel divs) wraps form content
✓ Event handlers use delegated .on(event, selector, handler) pattern
✓ AJAX reinitialization guard is present in ENTITY_JS

CANONICAL METADATA:
- file_name: {file_name}
- form_case_type: {case_token}
- table_name: {table_name}
- title: {title}
- primary_key: {primary_key}

STRUCTURED CONTRACT:
{contract_text}

REQUESTED FIELDS:
{field_list}

HIERARCHY RULES:
{hierarchy_rules}

PRE-DELETE DEPENDENCIES:
{chr(10).join(dependency_lines) if dependency_lines else 'None'}

{predelete_placement_rule}

CASCADING DROPDOWN RULES:
{cascading_rules}

GRID RULES:
{grid_rules}

{master_detail_rules}

{ajax_handlers_rules}

{business_validations}

USER REQUEST:
{user_request}

REFERENCE COMPANY STYLE SNIPPET:
{template_excerpt if template_excerpt else '(not available)'}
{retry_notes}

🚨 MINIMUM CONTENT REQUIREMENTS (CRITICAL) 🚨

EACH SECTION MUST CONTAIN REAL WORKING CODE - NOT PLACEHOLDERS:

❌ ABSOLUTELY FORBIDDEN:
- Comments like "// CRUD here" or "// Add code here"
- Placeholder text like "TODO" or "IMPLEMENT THIS"
- Empty logic or stub functions
- Any form of incomplete code

✅ MANDATORY FUNCTIONS (MUST BE PRESENT):
- db_insert() - for INSERT operations
- db_update() - for UPDATE operations
- db_delete() - for DELETE operations
- db_getRecord() - for fetching single record

1. VARIABLE_INIT_PHP (MINIMUM 200 chars):
   - Initialize ALL {len(requested_fields)} field variables
   - Add Edit action logic with db_getRecord()
   - Populate ALL variables from fetched record
   - MUST use db_getRecord() function

2. CRUD_LOGIC_PHP (MINIMUM 800 chars):
   - Save action: MUST call db_insert() with funStartTran/funEndTran
   - Update action: MUST call db_update() with funStartTran/funEndTran
   - Delete action: MUST call getrows() for dependency check + db_delete()
   - ALL 3 dependencies must be checked in Delete with getrows()
   - MUST include echo redirect after each action

3. AJAX_HANDLERS_PHP (MINIMUM 150 chars):
   - GetMaxID handler MUST use getvalue()
   - MUST echo result
   - MUST call exit after echo
   - MUST work for {primary_key}

4. FORM_FIELDS_HTML (MINIMUM 1000 chars):
   - Generate proper HTML input for ALL {len(requested_fields)} fields
   - Each field: <label> + <input>/<select>/<checkbox>
   - Use control-label col-md-3 + col-md-6 grid
   - Wrap in page/page-content/panel divs
   - MUST include proper name and id attributes

5. FORM_VALIDATION_FIELDS (MINIMUM 300 chars):
   - Include FormValidation field map only
   - Add validators for ALL required fields
   - Do NOT include $(document).ready wrapper

6. SELECT2_HANDLERS (MINIMUM 120 chars):
   - Include Select2 initialization/open-close focus handlers
   - Keep only Select2-specific JS helpers

7. ENTITY_JS (MINIMUM 600 chars):
   - maxid() function MUST call AJAX GetMaxID
   - MUST wrap in AJAX reinitialization guard
   - MUST include $.ajax() call in maxid()
   - Use FORM_VALIDATION_FIELDS + SELECT2_HANDLERS sections from wrapper init

⚠️ EMPTY SECTIONS = IMMEDIATE REJECTION
⚠️ PLACEHOLDER COMMENTS = IMMEDIATE REJECTION
⚠️ "// Add code here" = IMMEDIATE REJECTION
⚠️ Missing ANY mandatory function = IMMEDIATE REJECTION

YOU MUST WRITE COMPLETE WORKING CODE FOR EACH SECTION.

🚨 CRITICAL: REQUIRED OUTPUT FORMAT (MANDATORY STRUCTURE) 🚨

YOU MUST RETURN YOUR CODE IN EXACTLY THIS TAGGED STRUCTURE.
DO NOT RETURN FLAT/UNSTRUCTURED CODE.
EACH SECTION MUST BE WRAPPED IN ITS TAGS.
MISSING TAGS = INVALID OUTPUT = SYSTEM FAILURE.

EXAMPLE OF CORRECT STRUCTURE:

<<<VARIABLE_INIT_PHP>>>
\\$Code = "";
\\$Name = "";
\\$Description = "";
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Edit') {{
    \\$obj = db_getRecord(\\$table, "{primary_key} = ?", [\\$_REQUEST['{primary_key}']]);
    if (\\$obj) {{
        \\$Code = \\$obj['{primary_key}'];
        \\$Name = \\$obj['Name'];
    }}
}}

if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'Delete') {{
    \$check = getrows('dependent_table', ' foreign_key', add(\$_REQUEST['{primary_key}']));
    if (\\$check > 0) {{
        echo "<script>alert('Cannot delete: record is being used');</script>";
        exit;
    }}
    funStartTran();
    \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
    db_delete(\$table, \$filter);
    funEndTran();
    echo "<script>window.location='{file_name}';</script>";
    exit;
}}

if (isset(\\$_REQUEST['Action']) && (\\$_REQUEST['Action'] == 'Save' || \\$_REQUEST['Action'] == 'Update')) {{
    funStartTran();
    if (\\$_REQUEST['Action'] == 'Save') {{
        db_insert(\\$table, \\$_REQUEST);
    }} else {{
        \$filter = " {primary_key}='" . add(\$_REQUEST['{primary_key}']) . "'";
        db_update(\$table, \$_REQUEST, \$filter);
    }}
    funEndTran();
    echo "<script>window.location='{file_name}';</script>";
    exit;
}}
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
if (isset(\\$_REQUEST['Action']) && \\$_REQUEST['Action'] == 'GetMaxID') {{
    \\$maxId = getvalue("SELECT MAX({primary_key}) FROM {table_name}");
    echo \\$maxId + 1;
    exit;
}}
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<div class="page">
    <div class="page-content">
        <div class="panel">
            <div class="panel-heading">
                <h3 class="panel-title">{title}</h3>
            </div>
            <div class="panel-body">
                <div class="form-group">
                    <label class="control-label col-md-3">{primary_key}</label>
                    <div class="col-md-6">
                        <input type="text" class="form-control" name="{primary_key}" id="{primary_key}" readonly />
                    </div>
                </div>
                <div class="form-group">
                    <label class="control-label col-md-3">Name <span class="required">*</span></label>
                    <div class="col-md-6">
                        <input type="text" class="form-control" name="Name" id="Name" required />
                    </div>
                </div>
                <div class="form-group">Repeat this structure for all requested fields.</div>
            </div>
        </div>
    </div>
</div>
<<<END_FORM_FIELDS_HTML>>>

<<<ENTITY_JS>>>
if (typeof window.formInitialized === 'undefined') {{
    window.formInitialized = true;
    
    function maxid() {{
        \\$.ajax({{
            url: '{file_name}',
            data: {{ Action: 'GetMaxID' }},
            success: function(data) {{
                \\$('#{primary_key}').val(data);
            }}
        }});
    }}
    
    \\$(document).ready(function() {{
        maxid();
        
    }});
}}
<<<END_ENTITY_JS>>>

🚨 VALIDATION BEFORE RETURNING:
✓ Did you wrap VARIABLE_INIT_PHP in <<<VARIABLE_INIT_PHP>>> ... <<<END_VARIABLE_INIT_PHP>>>?
✓ Did you wrap CRUD_LOGIC_PHP in <<<CRUD_LOGIC_PHP>>> ... <<<END_CRUD_LOGIC_PHP>>>?
✓ Did you wrap AJAX_HANDLERS_PHP in <<<AJAX_HANDLERS_PHP>>> ... <<<END_AJAX_HANDLERS_PHP>>>?
✓ Did you wrap FORM_FIELDS_HTML in <<<FORM_FIELDS_HTML>>> ... <<<END_FORM_FIELDS_HTML>>>?
✓ Did you wrap FORM_VALIDATION_FIELDS in <<<FORM_VALIDATION_FIELDS>>> ... <<<END_FORM_VALIDATION_FIELDS>>>?
✓ Did you wrap SELECT2_HANDLERS in <<<SELECT2_HANDLERS>>> ... <<<END_SELECT2_HANDLERS>>>?
✓ Did you wrap ENTITY_JS in <<<ENTITY_JS>>> ... <<<END_ENTITY_JS>>>?
✓ Did you include ALL {len(requested_fields)} fields in FORM_FIELDS_HTML?
✓ Did you include FormValidation rules for ALL required fields in FORM_VALIDATION_FIELDS?
✓ Did you include ALL 8 mandatory company functions (db_insert, db_update, db_delete, db_getRecord, getrows, getvalue, funStartTran, funEndTran)?
✓ Did you use page/page-content/panel div structure in FORM_FIELDS_HTML?
✓ Did you use delegated event handlers (.on) in ENTITY_JS?

NOW GENERATE YOUR CODE WITH PROPER SECTION TAGS:

═══════════════════════════════════════════════════════════════════════════════
🔴 CRITICAL REMINDER - READ THIS BEFORE GENERATING 🔴
═══════════════════════════════════════════════════════════════════════════════

YOU MUST INCLUDE ALL 7 SECTIONS WITH EXACT TAGS:

1. <<<VARIABLE_INIT_PHP>>> ... <<<END_VARIABLE_INIT_PHP>>>
   - PHP variable initialization ($table, $form, $title)
   
2. <<<CRUD_LOGIC_PHP>>> ... <<<END_CRUD_LOGIC_PHP>>>
   - Save/Update/Delete/Edit handlers
   - MUST use: db_insert, db_update, db_delete, funStartTran, funEndTran
   
3. <<<AJAX_HANDLERS_PHP>>> ... <<<END_AJAX_HANDLERS_PHP>>>
   - GetMaxID handler (MANDATORY)
   - Any other AJAX endpoints
   
4. <<<FORM_FIELDS_HTML>>> ... <<<END_FORM_FIELDS_HTML>>>
   - ALL {len(requested_fields)} form fields with proper Bootstrap grid
   - Each field in <div class="form-group"> structure
   
5. <<<FORM_VALIDATION_FIELDS>>> ... <<<END_FORM_VALIDATION_FIELDS>>>
   - FormValidation field map only (no wrapper)
   
6. <<<SELECT2_HANDLERS>>> ... <<<END_SELECT2_HANDLERS>>>
   - Select2 close/open focus handlers
   
7. <<<ENTITY_JS>>> ... <<<END_ENTITY_JS>>>
   - ⚠️ THIS SECTION IS MANDATORY - NEVER SKIP IT
   - MUST include: maxid() function
   - MUST include: $(document).ready() initialization
   - MUST initialize using FORM_VALIDATION_FIELDS + SELECT2_HANDLERS blocks
   - Even if JavaScript is minimal, YOU MUST INCLUDE THIS SECTION

⚠️ MISSING ANY SECTION = SYSTEM FAILURE
⚠️ MISSING <<<ENTITY_JS>>> = IMMEDIATE REJECTION
⚠️ ALL 7 SECTIONS ARE MANDATORY - NO EXCEPTIONS

COPY THESE EXACT TAG NAMES (case-sensitive):
<<<VARIABLE_INIT_PHP>>> <<<END_VARIABLE_INIT_PHP>>>
<<<CRUD_LOGIC_PHP>>> <<<END_CRUD_LOGIC_PHP>>>
<<<AJAX_HANDLERS_PHP>>> <<<END_AJAX_HANDLERS_PHP>>>
<<<FORM_FIELDS_HTML>>> <<<END_FORM_FIELDS_HTML>>>
<<<FORM_VALIDATION_FIELDS>>> <<<END_FORM_VALIDATION_FIELDS>>>
<<<SELECT2_HANDLERS>>> <<<END_SELECT2_HANDLERS>>>
<<<ENTITY_JS>>> <<<END_ENTITY_JS>>>

═══════════════════════════════════════════════════════════════════════════════
"""
        return prompt.strip()

    def _strip_wrapping_code_markers(self, text: str) -> str:
        value = str(text or '').strip()
        if not value:
            return ''

        fence_match = re.match(r'^```[a-zA-Z0-9_+-]*\s*(.*?)\s*```\Z', value, re.DOTALL)
        if fence_match:
            value = fence_match.group(1).strip()

        value = re.sub(r'^\s*<\?php\s*', '', value, flags=re.IGNORECASE)
        value = re.sub(r'\s*\?>\s*$', '', value, flags=re.IGNORECASE)
        value = re.sub(r'^\s*<script[^>]*>\s*', '', value, flags=re.IGNORECASE)
        value = re.sub(r'\s*</script>\s*$', '', value, flags=re.IGNORECASE)
        return value.strip()

    def _parse_controlled_generation_sections(self, content: str) -> Dict[str, str]:
        section_names = [
            'VARIABLE_INIT_PHP',
            'CRUD_LOGIC_PHP',
            'AJAX_HANDLERS_PHP',
            'FORM_FIELDS_HTML',
            'FORM_VALIDATION_FIELDS',
            'SELECT2_HANDLERS',
            'ENTITY_JS',
        ]
        parsed = {}
        for section_name in section_names:
            tagged_match = re.search(
                rf'<<<{section_name}>>>\s*(.*?)\s*<<<END_{section_name}>>>',
                content or '',
                re.IGNORECASE | re.DOTALL
            )
            xml_match = re.search(
                rf'<{section_name}>\s*(.*?)\s*</{section_name}>',
                content or '',
                re.IGNORECASE | re.DOTALL
            )
            match = tagged_match or xml_match
            parsed[section_name] = self._strip_wrapping_code_markers(match.group(1)) if match else ''
        return parsed

    def _has_controlled_section_tag(self, content: str, section_name: str) -> bool:
        if not content:
            return False
        return bool(
            re.search(
                rf'<<<{section_name}>>>\s*.*?\s*<<<END_{section_name}>>>',
                content,
                re.IGNORECASE | re.DOTALL
            )
            or re.search(
                rf'<{section_name}>\s*.*?\s*</{section_name}>',
                content,
                re.IGNORECASE | re.DOTALL
            )
        )

    def _sanitize_controlled_section(self, section_name: str, raw_content: str) -> str:
        cleaned = self._strip_wrapping_code_markers(raw_content)
        if not cleaned:
            return ''

        if section_name.endswith('_PHP'):
            filtered_lines = []
            for raw_line in cleaned.splitlines():
                line = raw_line.rstrip()
                line_lower = line.lower()
                if 'session_start' in line_lower or 'config.inc.php' in line_lower:
                    continue
                if re.search(r'^\s*\$(form|form2|table|title)\s*=', line, re.IGNORECASE):
                    continue
                filtered_lines.append(line)
            return '\n'.join(filtered_lines).strip()

        if section_name == 'FORM_FIELDS_HTML':
            cleaned = re.sub(r'<!DOCTYPE[^>]*>', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r'<\/?(?:html|head|body)[^>]*>', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(
                r'<form\b(?:(?:"[^"]*"|\'[^\']*\'|<\?(?:php|=)?[\s\S]*?\?>|[^>])*)>',
                '',
                cleaned,
                flags=re.IGNORECASE
            )
            cleaned = re.sub(r'</form>', '', cleaned, flags=re.IGNORECASE)
            return cleaned.strip()

        if section_name == 'ENTITY_JS':
            cleaned = self._strip_formvalidation_init_from_entity_js(cleaned)
            cleaned = re.sub(
                r'function\s+(?:btnsave_click|checkKeycode|companySharedInit|companyPageLoad)\s*\([^)]*\)\s*\{.*?\}',
                '',
                cleaned,
                flags=re.IGNORECASE | re.DOTALL
            )
            cleaned = re.sub(r'document\.onkeydown\s*=.*', '', cleaned, flags=re.IGNORECASE)
            return cleaned.strip()

        return cleaned.strip()

    def _strip_formvalidation_init_from_entity_js(self, entity_js: str) -> str:
        """Remove duplicate FormValidation init blocks while preserving other JS."""
        if not entity_js:
            return ""

        cleaned = str(entity_js)
        patterns = [
            r'\$\([^)]+\)\s*\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*(?:\.on\([\s\S]*?\)\s*)*;?',
            r'\$[A-Za-z_][A-Za-z0-9_]*\s*\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*(?:\.on\([\s\S]*?\)\s*)*;?',
            r'FormValidation\.formValidation\s*\([\s\S]*?\)\s*;',
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _strip_js_function_from_entity_js(self, code: str, function_name: str) -> str:
        """Remove named function declarations from ENTITY_JS after head extraction."""
        if not code:
            return ""

        original_code = code
        lines = code.splitlines()
        output: List[str] = []
        i = 0
        target = (function_name or '').strip().lower()

        while i < len(lines):
            line = lines[i]
            match = re.search(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', line, re.IGNORECASE)
            if not match or match.group(1).lower() != target:
                output.append(line)
                i += 1
                continue

            brace_depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and brace_depth > 0:
                brace_depth += lines[i].count('{') - lines[i].count('}')
                i += 1

            if brace_depth > 0:
                logger.warning(
                    "⚠️ ENTITY_JS strip aborted for %s due to unmatched braces; preserving original section",
                    function_name
                )
                return original_code

        stripped = '\n'.join(output)
        stripped = re.sub(r'\n{3,}', '\n\n', stripped)
        return stripped.strip()
    
    def _auto_fix_missing_tags(self, generated_code: str, missing_tags: list, contract: Dict) -> str:
        """
        Strict mode: never fabricate missing sections.
        Missing controlled tags must trigger regeneration/failure instead of
        synthetic section injection.
        """
        if missing_tags:
            logger.warning(
                "Strict mode: missing controlled sections cannot be auto-fixed: %s",
                ', '.join(str(tag) for tag in missing_tags)
            )
        return generated_code
    
    def _extract_head_scripts_from_entity_js(self, entity_js: str) -> str:
        """
        Extract head scripts (maxid, btnsave_click, checkKeycode) from entity JS.
        These scripts go in the <head> section.
        """
        if not entity_js:
            return ""
        
        head_scripts = []
        
        # Extract maxid function
        maxid_match = re.search(
            r'function\s+maxid\s*\([^)]*\)\s*\{[^}]*\}',
            entity_js,
            re.IGNORECASE | re.DOTALL
        )
        if maxid_match:
            head_scripts.append(maxid_match.group(0))
        
        # Extract btnsave_click function
        btnsave_match = re.search(
            r'function\s+btnsave_click\s*\([^)]*\)\s*\{[^}]*\}',
            entity_js,
            re.IGNORECASE | re.DOTALL
        )
        if btnsave_match:
            head_scripts.append(btnsave_match.group(0))
        
        # Extract checkKeycode function
        checkkeycode_match = re.search(
            r'function\s+checkKeycode\s*\([^)]*\)\s*\{[^}]*\}',
            entity_js,
            re.IGNORECASE | re.DOTALL
        )
        if checkkeycode_match:
            head_scripts.append(checkkeycode_match.group(0))
        
        return '\n\n'.join(head_scripts)
    
    def _extract_select2_handlers_from_entity_js(self, entity_js: str) -> str:
        """
        Extract Select2 event handlers from entity JS.
        These handlers go before the closing </script> tag.
        """
        if not entity_js:
            return ""
        
        select2_handlers = []
        
        # Extract Select2 close events
        select2_close_pattern = r'\$\([^)]+\)\.on\(["\']select2:close["\'],[^}]+\}\);'
        for match in re.finditer(select2_close_pattern, entity_js, re.DOTALL):
            select2_handlers.append(match.group(0))
        
        # Extract Select2 initialization
        select2_init_pattern = r'\$\([^)]+\)\.select2\([^)]*\);'
        for match in re.finditer(select2_init_pattern, entity_js):
            select2_handlers.append(match.group(0))
        
        return '\n'.join(select2_handlers)
    
    def _extract_formvalidation_fields_from_entity_js(self, entity_js: str) -> str:
        """
        Extract FormValidation field definitions from entity JS.
        These go in the fields: {} section of FormValidation.
        """
        if not entity_js:
            return ""
        
        # Extract fields object from formValidation call
        fv_match = re.search(
            r'\.formValidation\s*\(\s*\{[^}]*fields\s*:\s*\{([^}]+)\}',
            entity_js,
            re.IGNORECASE | re.DOTALL
        )
        if fv_match:
            return fv_match.group(1).strip()
        
        return ""

    def _controlled_framework_head(self, fixed_parts: Dict[str, str]) -> str:
        head_html = str((fixed_parts or {}).get('html_head') or '')
        if not head_html and self._template and getattr(self._template, '_html_head', ''):
            head_html = str(getattr(self._template, '_html_head', '') or '')

        css_links = str((fixed_parts or {}).get('css_links') or '')
        if not css_links and self._template:
            css_links = self._template.get_css_links_html()

        if not head_html.strip():
            head_html = (
                "<head>\n"
                "  <meta charset=\"utf-8\">\n"
                "  <meta http-equiv=\"X-UA-Compatible\" content=\"IE=edge\">\n"
                "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, user-scalable=0, minimal-ui\">\n"
                "  <meta name=\"description\" content=\"bootstrap admin template\">\n"
                "  <meta name=\"author\" content=\"\">\n"
                "  <title><?=$title;?></title>\n"
                f"{css_links}\n"
                "  <script src=\"global/vendor/modernizr/modernizr.js\"></script>\n"
                "  <script src=\"global/vendor/breakpoints/breakpoints.js\"></script>\n"
                "</head>"
            )

        head_html = re.sub(
            r'<script\b(?![^>]*\bsrc=)[^>]*>.*?</script>',
            '',
            head_html,
            flags=re.IGNORECASE | re.DOTALL
        )

        if css_links:
            missing_css = []
            lower_head = head_html.lower()
            for css_line in [line.strip() for line in css_links.splitlines() if line.strip()]:
                href_match = re.search(r'href=["\']([^"\']+)["\']', css_line, re.IGNORECASE)
                href_value = href_match.group(1).lower() if href_match else ''
                if href_value and href_value in lower_head:
                    continue
                if css_line.lower() in lower_head:
                    continue
                missing_css.append(css_line)
            if missing_css and '</head>' in head_html.lower():
                injection = '\n'.join(missing_css)
                head_html = re.sub(r'</head>', injection + '\n</head>', head_html, count=1, flags=re.IGNORECASE)

        if not re.search(r'<title>.*?</title>', head_html, re.IGNORECASE | re.DOTALL):
            head_html = re.sub(r'<head[^>]*>', r'\g<0>' + "\n  <title><?=$title;?></title>", head_html, count=1, flags=re.IGNORECASE)
        else:
            head_html = re.sub(
                r'<title>.*?</title>',
                '<title><?=$title;?></title>',
                head_html,
                count=1,
                flags=re.IGNORECASE | re.DOTALL
            )

        if 'breakpoints();' not in head_html.lower():
            breakpoints_call = "  <script>\n  Breakpoints();\n  </script>"
            if re.search(r'</head>', head_html, re.IGNORECASE):
                head_html = re.sub(r'</head>', breakpoints_call + '\n</head>', head_html, count=1, flags=re.IGNORECASE)
            else:
                head_html += '\n' + breakpoints_call

        return head_html.strip()

    def _controlled_framework_body_start(self, fixed_parts: Dict[str, str]) -> str:
        return """
<body class="animsition" onLoad="companyPageLoad();">
  <?php include("include/topmenu.php");?>
  <?php include("include/sidemenu.php");?>
  <div class="page">
    <?php include("include/formheader.php"); ?>
    <div class="page-content padding-5" style="border:0px solid red;">
      <div class="panel">
        <div class="panel-body container-fluid">
          <div class="row row-lg">
            <div class="col-sm-12 col-md-12">
              <form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">
""".strip()

    def _controlled_framework_body_end(self, fixed_parts: Dict[str, str]) -> str:
        return """
</form>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  <?php include("include/footer.php");?>
</body>
</html>
""".strip()

    def _build_fixed_action_bar(self) -> str:
        return """
                <div class="form-group">
                  <div class="col-md-12" align="center">
                    <button type="button" name="btnSave" id="btnSave" class="btn btn-primary" value="Save" accesskey="s" title="Press Alt+S" onclick="btnsave_click()">Save</button>
                    <button type="reset" class="btn btn-success" id="btnReset" name="btnReset" accesskey="b" title="Press Alt+B" onClick="window.location='<?=$form; ?>'">Back</button>
                    <input type="hidden" id="txtmode" name="txtmode" value="new">
                    <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo isset(\\$_REQUEST['action']) ? \\$_REQUEST['action'] : ''; ?>">
                  </div>
                </div>
""".strip()

    def _normalize_controlled_form_fields(self, form_fields: str, user_request: str = "") -> str:
        normalized = str(form_fields or '').strip()
        if not normalized:
            return normalized

        wants_keyboard = bool(self._detect_user_requirements(user_request or '').get('wants_keyboard'))
        
        # ✅ CRITICAL FIX: Simplified regex to avoid catastrophic backtracking
        # Old: r'(?:(?:"[^"]*"|\'[^\']*\'|<\?(?:php|=)?[\s\S]*?\?>|[^<>])*)'
        # This caused exponential time on 2372+ char content - HANGS!
        # New: Simple pattern - linear time complexity
        rich_tag_pattern = r'[^>]*'

        def _normalize_label(match):
            tag = match.group(0)
            class_match = re.search(r'class\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if class_match:
                classes = class_match.group(1).strip().split()
                class_lookup = {cls.lower() for cls in classes}
                if 'control-label' not in class_lookup:
                    classes.append('control-label')
                if not any(re.match(r'col-(?:xs|sm|md|lg)-\d+', cls, re.IGNORECASE) for cls in classes):
                    classes.append('col-md-4')
                merged = ' '.join(dict.fromkeys(classes))
                return tag[:class_match.start(1)] + merged + tag[class_match.end(1):]
            return tag.replace('<label', '<label class="control-label col-md-4"', 1)

        normalized = re.sub(r'<label\b[^>]*>', _normalize_label, normalized, flags=re.IGNORECASE)

        normalized = re.sub(
            rf'(<label\b[^>]*>.*?</label>\s*)(<(?:input|select|textarea)\b{rich_tag_pattern}(?:</select>|</textarea>)?)',
            r'\1<div class="col-md-8">\n\2\n</div>',
            normalized,
            flags=re.IGNORECASE | re.DOTALL
        )
        normalized = re.sub(
            r'(<label\b[^>]*>.*?</label>\s*)<div(?![^>]*class=)([^>]*)>',
            r'\1<div class="col-md-8"\2>',
            normalized,
            flags=re.IGNORECASE | re.DOTALL
        )

        def _ensure_form_control(match):
            tag = match.group(0)
            if re.search(r'\btype\s*=\s*["\']checkbox["\']', tag, re.IGNORECASE):
                return tag
            class_match = re.search(r'class\s*=\s*["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if class_match:
                classes = class_match.group(1).strip().split()
                if 'form-control' not in {cls.lower() for cls in classes}:
                    classes.append('form-control')
                merged = ' '.join(dict.fromkeys(classes))
                return tag[:class_match.start(1)] + merged + tag[class_match.end(1):]
            return tag.replace(match.group(1), f'{match.group(1)} class="form-control"', 1)

        normalized = re.sub(
            rf'(<input\b){rich_tag_pattern}>',
            _ensure_form_control,
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<select\b){rich_tag_pattern}>',
            _ensure_form_control,
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<textarea\b){rich_tag_pattern}>',
            _ensure_form_control,
            normalized,
            flags=re.IGNORECASE
        )

        def _close_unterminated_control(match):
            tag = match.group(1).rstrip()
            # Don't close controls that already end with PHP short tags
            if tag.endswith('?>') or tag.endswith('?>'):
                return match.group(0)
            # Don't close controls that already have htmlspecialchars (already processed)
            if 'htmlspecialchars' in tag:
                return match.group(0)
            # Don't close controls that already have onKeyDown (already closed)
            if 'onKeyDown' in tag:
                return match.group(0)
            # Don't close controls that already have attributes (like required, etc.)
            # The tag already ends with " so adding > would break attributes
            if tag.endswith('"') and not tag.endswith('>'):
                return tag
            if tag.endswith('>') and not tag.endswith('?>'):
                return tag
            return tag + '>'

        normalized = re.sub(
            rf'(<input\b{rich_tag_pattern})\s*(?=</div>|<\?php|$)',
            _close_unterminated_control,
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<select\b{rich_tag_pattern})\s*(?=<option\b|</div>|<\?php|$)',
            _close_unterminated_control,
            normalized,
            flags=re.IGNORECASE
        )

        normalized = re.sub(
            r'value="\s*<\?=\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*;\s*\?>"',
            r'value="<?=htmlspecialchars($\1, ENT_QUOTES);?>"',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'value="\s*<\?php\s+echo\s+\$([A-Za-z_][A-Za-z0-9_]*)\s*;\s*\?>"',
            r'value="<?php echo htmlspecialchars($\1, ENT_QUOTES); ?>"',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'>\s*<\?=\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*;\s*\?>\s*</textarea>',
            r'><?=htmlspecialchars($\1, ENT_QUOTES);?></textarea>',
            normalized,
            flags=re.IGNORECASE
        )

        if wants_keyboard:
            def _normalize_input_control(match):
                tag = match.group(0)
                if re.search(r'\bonkey(?:down)?\s*=', tag, re.IGNORECASE):
                    return tag
                if re.search(r'\btype\s*=\s*["\'](?:hidden|button|submit|reset|file)["\']', tag, re.IGNORECASE):
                    return tag
                # Check if tag already has closing > (but NOT inside PHP like ?>)
                # Look for the last > that is NOT preceded by ?
                last_php_close = tag.rfind('?>')
                if last_php_close >= 0:
                    # Has PHP close tag, find the actual HTML closing >
                    remaining = tag[last_php_close + 2:]
                    html_close_pos = remaining.rfind('>')
                    if html_close_pos >= 0:
                        # Tag already has closing > after PHP, insert onKeyDown before it
                        return tag[:last_php_close + 2 + html_close_pos] + ' onKeyDown="checkKeycode(event,this.id);">'
                    else:
                        # No HTML closing > after PHP tag, add onKeyDown and closing >
                        return tag.rstrip() + ' onKeyDown="checkKeycode(event,this.id);">'
                # No PHP close tag, just find the last >
                closing_pos = tag.rfind('>')
                if closing_pos > 0:
                    return tag[:closing_pos] + ' onKeyDown="checkKeycode(event,this.id);">'
                else:
                    tag_stripped = tag.rstrip()
                    return tag_stripped + ' onKeyDown="checkKeycode(event,this.id);">'

            normalized = re.sub(
                rf'<input\b{rich_tag_pattern}>',
                _normalize_input_control,
                normalized,
                flags=re.IGNORECASE
            )
            normalized = re.sub(
                rf'<select\b{rich_tag_pattern}>',
                lambda match: (lambda m: m.group(0) if re.search(r'\bonkey(?:down)?\s*=', m.group(0), re.IGNORECASE) else (lambda t: t.rstrip() + ' onKeyDown="checkKeycode(event,this.id);">' if t.rfind('>') < 0 else t[:t.rfind('>')] + ' onKeyDown="checkKeycode(event,this.id);">')(m.group(0)))(match),
                normalized,
                flags=re.IGNORECASE
            )
            normalized = re.sub(
                rf'<textarea\b{rich_tag_pattern}>',
                lambda match: (lambda m: m.group(0) if re.search(r'\bonkey(?:down)?\s*=', m.group(0), re.IGNORECASE) else (lambda t: t.rstrip() + ' onKeyDown="checkKeycode(event,this.id);">' if t.rfind('>') < 0 else t[:t.rfind('>')] + ' onKeyDown="checkKeycode(event,this.id);">')(m.group(0)))(match),
                normalized,
                flags=re.IGNORECASE
            )

        normalized = normalized.replace(');? onKeyDown', ');?>" onKeyDown')
        # CRITICAL FIX: Handle broken PHP short tags with onKeyDown
        # Pattern: value="<?=$var;? onKeyDown="...">"" 
        # Should become: value="<?=$var;?>" onKeyDown="...">
        normalized = re.sub(
            r'value="<\?=([^;]+);\s*\?(\s*onKeyDown="[^"]*")>',
            r'value="<?=\1;?>" \2>',
            normalized
        )
        normalized = re.sub(
            r'value="<\?=([^;]+);(\s*onKeyDown="[^"]*")>',
            r'value="<?=\1;?>" \2>',
            normalized
        )
        normalized = re.sub(
            r'(<\?=.*?;\?)(\s*onKeyDown="[^"]*")(\s*>)',
            r'\1> \2\3',
            normalized
        )
        # Fix: value="<?=$var;? onKeyDown="...">"" - use raw string properly
        normalized = re.sub(
            r'value="<\?=(\$\w+);.*?"',
            r'value="<?=\1;?>"',
            normalized
        )
        # Fix: value="<?=...;?> required" -> value="<?=...;?>" required
        normalized = re.sub(
            r'value="(<\?=.*?\?>)\s+(\w+)',
            r'value="\1" \2',
            normalized
        )
        # Comprehensive fix for attribute ordering:
        # 1. Fix broken PHP tags: onKeyDown="...">"" -> onKeyDown="...">"
        normalized = re.sub(r'(onKeyDown="[^"]*")>""', r'\1">', normalized)
        # 2. Fix attribute ordering: onKeyDown="..."> "required" -> required onKeyDown="..."
        normalized = re.sub(r'(onKeyDown="[^"]*")>\s*"+\s*(required)', r'\2 \1>', normalized)
        # 3. Clean up any extra quotes
        normalized = re.sub(r'">"', r'">', normalized)
        normalized = re.sub(r'""$', r'"', normalized)
        normalized = re.sub(r'>\s*"$', r'>', normalized)
        normalized = normalized.replace(
            '</div onKeyDown="checkKeycode(event,this.id);">>',
            '</div>'
        )
        normalized = normalized.replace('</div>>', '</div>')
        # Fix select tags that have broken closing
        normalized = re.sub(
            r'(<select[^>]*>)\s*</div>(\s*<!--.*?-->)',
            r'\1\n',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<input\b{rich_tag_pattern})(?=</div>|<\?php|$)',
            _close_unterminated_control,
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<select\b{rich_tag_pattern})(?=<option\b|</div>|<\?php|$)',
            _close_unterminated_control,
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'(<select\b[\s\S]*?>)\s*</div>\s*(?=(?:<option\b|<\?php))',
            r'\1\n',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            rf'(<input\b{rich_tag_pattern}\?>)\s*</div>',
            r'\1>\n</div>',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'(<div\b[^>]*class\s*=\s*["\'][^"\']*\bform-group)\s+form-control\b',
            r'\1',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'<input\b(?![^>]*\btype\s*=\s*["\']checkbox["\'])(?![^>]*\bclass=)',
            '<input class="form-control"',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'<select\b(?![^>]*\bclass=)',
            '<select class="form-control"',
            normalized,
            flags=re.IGNORECASE
        )
        normalized = re.sub(
            r'<textarea\b(?![^>]*\bclass=)',
            '<textarea class="form-control"',
            normalized,
            flags=re.IGNORECASE
        )

        return normalized.strip()

    def _normalize_controlled_entity_js(self, entity_js: str, company_fields: Dict, user_request: str = "") -> str:
        normalized = str(entity_js or '').strip()
        default_entity_js = self._build_default_entity_js_config(company_fields, user_request=user_request)

        if not normalized:
            return default_entity_js

        if 'window.companyFieldOrder' not in normalized:
            field_order_match = re.search(
                r'window\.companyFieldOrder\s*=\s*\[[\s\S]*?\];',
                default_entity_js,
                re.IGNORECASE
            )
            if field_order_match:
                normalized = field_order_match.group(0) + "\n\n" + normalized

        if not re.search(r'window\.companyValidationFields\s*=\s*\{', normalized):
            validation_match = re.search(
                r'window\.companyValidationFields\s*=\s*\{[\s\S]*?\};',
                default_entity_js,
                re.IGNORECASE
            )
            if validation_match:
                normalized += "\n\n" + validation_match.group(0)

        if 'window.companyFormOnLoad' not in normalized:
            onload_match = re.search(
                r'window\.companyFormOnLoad[\s\S]*?\};',
                default_entity_js,
                re.IGNORECASE
            )
            if onload_match:
                normalized += "\n\n" + onload_match.group(0)

        return normalized.strip()

    def _build_default_controlled_validation_fields(self, contract: Dict, user_request: str = "") -> str:
        field_defs = contract.get('fields') or []
        if not field_defs:
            return ''

        required_lookup = {
            str(field).strip().lower()
            for field in self._extract_required_fields_from_request(user_request or '')
            if str(field).strip()
        }

        lines = []
        for field in field_defs[:30]:
            if isinstance(field, dict):
                name = str(field.get('name') or '').strip()
                input_type = str(field.get('input_type') or '').strip().lower()
                is_required = bool(field.get('required')) or name.lower() in required_lookup
            else:
                name = str(field or '').strip()
                input_type = ''
                is_required = name.lower() in required_lookup

            if not name:
                continue

            validators = []
            if is_required:
                message = (
                    f"Please select {name}"
                    if any(token in input_type for token in ('select', 'dropdown'))
                    else f"{name} is required"
                )
                validators.append(f"notEmpty: {{ message: '{message}' }}")
            if 'email' in name.lower():
                validators.append("emailAddress: { message: 'Please enter a valid email address' }")

            validators_js = ', '.join(validators)
            if validators_js:
                lines.append(f"{name}: {{ row: '.col-md-6', validators: {{ {validators_js} }} }}")
            else:
                lines.append(f"{name}: {{ row: '.col-md-6', validators: {{}} }}")

        return ",\n".join(lines).strip()

    def _build_default_controlled_select2_handlers(self) -> str:
        return """
$(function () {
    $('select[data-plugin="select2"], select.select2').each(function () {
        var $el = $(this);
        if (!$el.data('select2') && $.fn && $.fn.select2) {
            $el.select2({ width: '100%' });
        }
    });
});

$(document)
    .off('select2:close.company')
    .on('select2:close.company', '.select2-hidden-accessible', function () {
        var order = window.companyFieldOrder || [];
        var currentId = this.id || '';
        var idx = order.indexOf(currentId);
        var nextId = idx >= 0 ? order[idx + 1] : '';
        if (!nextId) {
            return;
        }
        setTimeout(function () {
            var $next = $('#' + nextId);
            if (!$next.length) {
                return;
            }
            if ($next.hasClass('select2-hidden-accessible') && $.fn && $.fn.select2) {
                $next.select2('open');
            } else {
                $next.focus();
            }
        }, 0);
    });
""".strip()

    def _build_default_entity_js_config(self, company_fields: Dict, user_request: str = "") -> str:
        requested_fields = (
            (company_fields or {}).get('user_requested_fields')
            or (company_fields or {}).get('form_fields')
            or []
        )
        field_order = [field for field in requested_fields if str(field).strip()]
        if 'btnSave' not in field_order:
            field_order.append('btnSave')
        field_order_js = ', '.join(f"'{field}'" for field in field_order if str(field).strip())

        required_fields = self._extract_required_fields_from_request(user_request or '')
        if required_fields:
            validation_targets = [
                field for field in requested_fields
                if str(field).strip().lower() in {str(req).strip().lower() for req in required_fields}
            ]
        else:
            validation_targets = requested_fields[:]

        validation_lines = []
        for field in validation_targets[:20]:
            validation_lines.append(
                f"  '{field}': {{ validators: {{ notEmpty: {{ message: '{field} is required' }} }} }}"
            )
        validation_block = "{\n" + ',\n'.join(validation_lines) + "\n}" if validation_lines else "{}"

        focus_field = ''
        for field in requested_fields:
            if field and field != 'btnSave':
                focus_field = field
                break

        default_parts = [
            f"window.companyFieldOrder = [{field_order_js}];",
            f"window.companyValidationFields = {validation_block};",
        ]
        if focus_field:
            default_parts.append(
                "window.companyFormOnLoad = window.companyFormOnLoad || function () {\n"
                "  if (typeof maxid === 'function') { maxid(); }\n"
                f"  var first = document.getElementById('{focus_field}');\n"
                "  if (first) { first.focus(); }\n"
                "};"
            )
        return '\n'.join(default_parts).strip()

    def _build_fixed_company_framework_js(self) -> str:
        return """
<script>
(function(window){
  if (!window) { return; }

  window.companyFieldOrder = window.companyFieldOrder || [];
  window.companyValidationFields = window.companyValidationFields || {};
  window.companyFormOnLoad = window.companyFormOnLoad || function () {};
  window.companyAfterInit = window.companyAfterInit || function () {};

  window.companyCheckKeycode = window.companyCheckKeycode || function (e, field) {
    var evt = e || window.event;
    var keycode = evt && (evt.which || evt.keyCode);
    if (keycode !== 13) {
      return true;
    }
    if (evt && evt.preventDefault) {
      evt.preventDefault();
    } else if (evt) {
      evt.returnValue = false;
    }

    var order = window.companyFieldOrder || [];
    var currentField = field || (document.activeElement ? document.activeElement.id : '');
    var idx = order.indexOf(currentField);
    if (idx >= 0 && idx < order.length - 1) {
      var next = document.getElementById(order[idx + 1]);
      if (next) {
        if (typeof next.focus === 'function') {
          next.focus();
        }
        if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2 && window.jQuery(next).hasClass('select2-hidden-accessible')) {
          window.jQuery(next).select2('open');
        }
      }
    }
    return false;
  };

  window.checkKeycode = window.companyCheckKeycode;
  window.checkKeycode = window.checkKeycode || function (e, field) {
    return window.companyCheckKeycode(e, field);
  };
  function checkKeycode(e, field) {
    return window.companyCheckKeycode(e, field);
  }
  document.onkeydown = checkKeycode;

  window.btnsave_click = window.btnsave_click || function () {
    var form = document.getElementById('frm') || document.forms.frm;
    if (!form) { return false; }

    if (window.jQuery) {
      var $form = window.jQuery(form);
      var fv = $form.data('formValidation');
      if (fv && typeof fv.validate === 'function') {
        fv.validate();
        if (typeof fv.isValid === 'function' && !fv.isValid()) {
          return false;
        }
      }
    }

    var hiddenMode = document.getElementById('txtmode');
    if (hiddenMode) {
      hiddenMode.value = 'save';
    }

    var disabledInputs = form.querySelectorAll(':disabled');
    for (var i = 0; i < disabledInputs.length; i++) {
      disabledInputs[i].setAttribute('data-company-disabled', '1');
      disabledInputs[i].disabled = false;
    }

    form.action = "<?php echo $form2; ?>";
    form.method = "post";
    form.submit();
    return true;
  };

  window.companySharedInit = function () {
    if (window.__companySharedInit) { return; }
    window.__companySharedInit = true;

    var $ = window.jQuery;
    if (window.Site && typeof window.Site.run === 'function') {
      window.Site.run();
    }
    if (!$) { return; }

    $(document)
      .off('click.companyAjaxNav')
      .on('click.companyAjaxNav', '[data-ajax-nav], a.ajax-nav', function (e) {
        var url = $(this).attr('href') || $(this).data('ajax-nav');
        if (!url || url === '#' || /^javascript:/i.test(url)) {
          return;
        }
        e.preventDefault();
        $.get(url).done(function (html) {
          var $target = $('#ajax-content');
          if ($target.length) {
            $target.html(html);
          }
        });
      });

    if ($.fn && $.fn.select2) {
      $('select[data-plugin="select2"], select.select2').each(function () {
        var $el = $(this);
        if (!$el.data('select2')) {
          $el.select2({ width: '100%' });
        }
      });
    }

    var $form = $('#frm');
    if ($form.length && $.fn && $.fn.formValidation && !$form.data('formValidation')) {
      $form.formValidation({
        framework: 'bootstrap',
        fields: window.companyValidationFields || {}
      });
    }

    if (typeof window.companyAfterInit === 'function') {
      window.companyAfterInit($);
    }
  };

  window.companyPageLoad = function () {
    window.companySharedInit();
    if (typeof window.companyFormOnLoad === 'function') {
      window.companyFormOnLoad();
    }
  };
})(window);
</script>
""".strip()

    def _assemble_controlled_php_file(
        self,
        fixed_parts: Dict[str, str],
        naming_metadata: Dict,
        sections: Dict[str, str],
        company_fields: Dict,
        user_request: str = "",
        strict_contract_mode: bool = False
    ) -> str:
        """
        Assemble complete PHP file using template injection architecture.
        
        This method now uses DynamicFormTemplate.merge_with_generated() to inject
        LLM-generated VARIABLE parts into the company framework template.
        
        FIXED parts (from template): CSS, scripts, HTML wrapper, includes
        VARIABLE parts (from LLM): PHP logic, form fields, validation, JS handlers
        """
        naming_metadata = naming_metadata or {}
        sections = sections or {}
        fixed_parts = fixed_parts or {}

        file_name = naming_metadata.get('file_name') or 'frmEntity.php'
        table_name = naming_metadata.get('table_name') or 'tblentity'
        title = naming_metadata.get('title') or 'Entity'
        case_type = naming_metadata.get('case_type') or title
        case_token = re.sub(r'[^A-Za-z0-9_]', '', str(case_type or title))

        # Build PHP logic section (VARIABLE)
        php_sections = [
            "<?php",
            "@session_start();",
            'include("include/config.inc.php");',
            "",
            f'$form = "frmSettingEditDeleteCase.php?CaseType={case_token}";',
            f'$form2 = "{file_name}";',
            f'$table = "{table_name}";',
            f'$title = "{title}";',
        ]

        variable_init = self._sanitize_controlled_section('VARIABLE_INIT_PHP', sections.get('VARIABLE_INIT_PHP', ''))
        crud_logic = self._sanitize_controlled_section('CRUD_LOGIC_PHP', sections.get('CRUD_LOGIC_PHP', ''))
        ajax_handlers = self._sanitize_controlled_section('AJAX_HANDLERS_PHP', sections.get('AJAX_HANDLERS_PHP', ''))
        form_fields = self._sanitize_controlled_section('FORM_FIELDS_HTML', sections.get('FORM_FIELDS_HTML', ''))
        form_validation_fields = self._sanitize_controlled_section('FORM_VALIDATION_FIELDS', sections.get('FORM_VALIDATION_FIELDS', ''))
        select2_handlers = self._sanitize_controlled_section('SELECT2_HANDLERS', sections.get('SELECT2_HANDLERS', ''))
        entity_js = self._sanitize_controlled_section('ENTITY_JS', sections.get('ENTITY_JS', ''))
        
        logger.info(f"🔧 Normalizing form fields ({len(form_fields)} chars)...")
        form_fields = self._normalize_controlled_form_fields(form_fields, user_request=user_request)
        logger.info(f"✅ Form fields normalized ({len(form_fields)} chars)")
        
        logger.info(f"🔧 Normalizing entity JS ({len(entity_js)} chars)...")
        entity_js = self._normalize_controlled_entity_js(entity_js, company_fields, user_request=user_request)
        logger.info(f"✅ Entity JS normalized ({len(entity_js)} chars)")

        for block in [variable_init, crud_logic, ajax_handlers]:
            if block:
                php_sections.append("")
                php_sections.append(block)

        php_logic = '\n'.join(php_sections).strip()
        
        template_ready = False
        if self._template:
            if hasattr(self._template, 'is_loaded_and_usable'):
                template_ready = bool(self._template.is_loaded_and_usable())
            else:
                template_ready = bool(getattr(self._template, '_loaded', False))

        # ✅ TASK 3.2: Use DynamicFormTemplate.merge_with_generated() for template injection
        if template_ready:
            logger.info("🔧 Using DynamicFormTemplate.merge_with_generated() for template injection...")
            
            # Extract head scripts (maxid, btnsave_click, checkKeycode) from entity_js
            head_scripts = self._extract_head_scripts_from_entity_js(entity_js)
            for fn_name in ['maxid', 'btnsave_click', 'checkKeycode']:
                entity_js = self._strip_js_function_from_entity_js(entity_js, fn_name)
            
            # Extract Select2 handlers from entity_js
            if not select2_handlers:
                select2_handlers = self._extract_select2_handlers_from_entity_js(entity_js)
            
            # Extract FormValidation fields from entity_js
            if not form_validation_fields:
                form_validation_fields = self._extract_formvalidation_fields_from_entity_js(entity_js)
            
            # Build body onLoad handler
            body_onload = "companyPageLoad();"
            
            # Call template merge
            merged_file = self._template.merge_with_generated(
                php_logic=php_logic,
                form_fields=form_fields,
                head_scripts=head_scripts,
                body_onload=body_onload,
                form_validation_fields=form_validation_fields,
                select2_handlers=select2_handlers,
                entity_js=entity_js
            )
            
            framework_js = self._build_fixed_company_framework_js()
            if 'window.companySharedInit' not in merged_file:
                if '</body>' in merged_file.lower():
                    merged_file = re.sub(
                        r'</body>',
                        framework_js + '\n</body>',
                        merged_file,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    merged_file = merged_file + '\n' + framework_js

            logger.info(f"✅ Template injection complete ({len(merged_file)} chars)")
            return merged_file
        
        # Fallback to manual assembly if template not available
        if strict_contract_mode:
            raise ValueError(
                "Strict contract mode requires DynamicFormTemplate; manual assembly fallback is blocked."
            )
        logger.warning("⚠️ DynamicFormTemplate not loaded, using manual assembly fallback")
        
        php_sections.append("?>")

        html_open = "<!DOCTYPE html>\n<html class=\"no-js css-menubar\" lang=\"en\">"
        head_html = self._controlled_framework_head(fixed_parts)
        body_start = self._controlled_framework_body_start(fixed_parts)
        body_end = self._controlled_framework_body_end(fixed_parts)

        footer_scripts = str(fixed_parts.get('footer_scripts') or '')
        if not footer_scripts and self._template:
            footer_scripts = self._template.get_footer_scripts_html()

        script_parts = []
        if footer_scripts.strip():
            script_parts.append(footer_scripts.strip())
        if entity_js.strip():
            script_parts.append("<script>\n" + entity_js.strip() + "\n</script>")
        script_parts.append(self._build_fixed_company_framework_js())
        script_bundle = '\n'.join(part for part in script_parts if str(part).strip())

        if re.search(r'</body>', body_end, re.IGNORECASE):
            body_end = re.sub(
                r'</body>',
                script_bundle + '\n</body>',
                body_end,
                count=1,
                flags=re.IGNORECASE
            )
        else:
            body_end = body_end + '\n' + script_bundle

        full_parts = [
            '\n'.join(php_sections).strip(),
            html_open,
            head_html,
            body_start,
            form_fields.strip(),
            self._build_fixed_action_bar(),
            body_end.strip(),
        ]
        return '\n'.join(part for part in full_parts if str(part).strip())

    async def _generate_controlled_inline_php_file(
        self,
        intent: Dict,
        sql_schema: str,
        source_company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        user_request: str,
        company_fields: Dict,
        hierarchy_pattern: Dict,
        related_tables: List[Dict],
        cascading_logic: Dict,
        grid_pattern: Dict,
        fixed_parts: Dict[str, str],
        naming_metadata: Dict,
        validation_errors: List = None,
        max_retries: int = 4
    ) -> str:
        """
        Controlled architecture:
        fixed company framework + LLM-generated dynamic sections.
        """
        logger.info("🏗️ Controlled assembly mode ENABLED")
        self._init_fallback_usage_tracker()

        max_retries = get_int_setting(
            'CODEGEN_INLINE_MAX_RETRIES',
            'CODEGEN_INLINE_MAX_RETRIES',
            max_retries if isinstance(max_retries, int) and max_retries > 0 else 3,
            min_value=1,
            max_value=6
        )
        max_prompt_chars = get_int_setting(
            'CODEGEN_PROMPT_MAX_CHARS',
            'CODEGEN_PROMPT_MAX_CHARS',
            28000,
            min_value=12000,
            max_value=300000
        )

        previous_errors = []
        if validation_errors:
            for err in validation_errors:
                err_str = str(err) if isinstance(err, str) else err.get('issue', err.get('error', str(err)))
                if err_str and err_str not in previous_errors:
                    previous_errors.append(err_str)

        llm_attempts_made = 0
        refusal_count = 0
        llm_call_failures = 0
        prompt = self._build_controlled_sections_prompt(
            intent=intent,
            user_request=user_request,
            company_fields=company_fields,
            naming_metadata=naming_metadata,
            hierarchy_pattern=hierarchy_pattern,
            related_tables=related_tables,
            cascading_logic=cascading_logic,
            grid_pattern=grid_pattern,
            template_code=source_company_examples,
            previous_errors=previous_errors
        )
        prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly prompt')
        request_contract = self._build_request_contract(
            user_request=user_request,
            naming_metadata=naming_metadata,
            company_fields=company_fields,
            hierarchy_pattern=hierarchy_pattern,
            related_tables=related_tables,
            grid_pattern=grid_pattern,
        )

        self.last_generation_metadata.update({
            'generation_architecture': 'controlled_assembly',
            'controlled_assembly': True,
            'request_contract': request_contract,
            'max_attempts': max_retries,
            'attempts_made': 0,
            'refusal_count': 0,
            'llm_call_failures': 0,
            'model_chain': self.model_chain,
            'attempt_models': [],
            'initial_prompt_mode': 'controlled_sections',
            'full_prompt_chars': 0,
            'initial_prompt_chars': len(prompt),
            'attempt_prompt_chars': [],
            'controlled_framework_source': (
                naming_metadata.get('file_path')
                or getattr(self._template, '_source_file', '')
                or ''
            ),
        })

        last_validation_result = {}
        for attempt in range(max_retries):
            self._init_fallback_usage_tracker()
            llm_attempts_made = attempt + 1
            self.last_generation_metadata['attempts_made'] = llm_attempts_made
            self.last_generation_metadata['attempt_prompt_chars'] = (
                self.last_generation_metadata.get('attempt_prompt_chars', []) + [len(prompt)]
            )
            attempt_model = self._effective_model_name(self._model_for_attempt(attempt))
            self.last_generation_metadata['attempt_models'] = (
                self.last_generation_metadata.get('attempt_models', []) + [attempt_model]
            )
            logger.info(f"🤖 Controlled assembly attempt {attempt + 1}/{max_retries} using {attempt_model}")

            try:
                llm_client = self._get_llm_client(attempt_model)
                generation_messages = self._build_generation_messages(prompt, user_request=user_request)
                result = await llm_client.ainvoke(generation_messages)
            except Exception as llm_error:
                llm_call_failures += 1
                self.last_generation_metadata['llm_call_failures'] = llm_call_failures
                previous_errors.append(f"LLM call failed: {llm_error}")
                if attempt >= max_retries - 1:
                    raise
                prompt = self._build_controlled_sections_prompt(
                    intent=intent,
                    user_request=user_request,
                    company_fields=company_fields,
                    naming_metadata=naming_metadata,
                    hierarchy_pattern=hierarchy_pattern,
                    related_tables=related_tables,
                    cascading_logic=cascading_logic,
                    grid_pattern=grid_pattern,
                    template_code=source_company_examples,
                    previous_errors=previous_errors
                )
                prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly retry prompt')
                continue

            llm_content = result.content if isinstance(result.content, str) else str(result.content)
            logger.info(f"✅ OpenAI API response received ({len(llm_content)} chars)")
            
            if self._is_refusal_response(llm_content):
                refusal_count += 1
                self.last_generation_metadata['refusal_count'] = refusal_count
                previous_errors.append('Model refusal: return tagged dynamic sections only')
                if attempt >= max_retries - 1:
                    raise ValueError(f"LLM refused controlled assembly generation after {max_retries} attempts.")
                prompt = self._build_controlled_sections_prompt(
                    intent=intent,
                    user_request=user_request,
                    company_fields=company_fields,
                    naming_metadata=naming_metadata,
                    hierarchy_pattern=hierarchy_pattern,
                    related_tables=related_tables,
                    cascading_logic=cascading_logic,
                    grid_pattern=grid_pattern,
                    template_code=source_company_examples[:12000],
                    previous_errors=previous_errors
                )
                prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly refusal retry')
                continue

            logger.info("🔍 Validating LLM output structure...")
            
            # FIX 1: HARD TAG VALIDATION (MANDATORY)
            required_sections = [
                'VARIABLE_INIT_PHP',
                'CRUD_LOGIC_PHP',
                'AJAX_HANDLERS_PHP',
                'FORM_FIELDS_HTML',
                'FORM_VALIDATION_FIELDS',
                'SELECT2_HANDLERS',
                'ENTITY_JS',
            ]

            missing_sections = [
                section_name
                for section_name in required_sections
                if not self._has_controlled_section_tag(llm_content, section_name)
            ]
            if missing_sections:
                error_msg = f"LLM STRUCTURE ERROR: Missing required sections: {', '.join(missing_sections)}"
                logger.error(error_msg)
                previous_errors.append(error_msg)
                if attempt >= max_retries - 1:
                    raise ValueError(
                        "Controlled assembly failed after "
                        f"{max_retries} attempts: LLM did not return properly tagged sections. "
                        f"Missing sections: {', '.join(missing_sections)}"
                    )
                prompt = self._build_controlled_sections_prompt(
                    intent=intent,
                    user_request=user_request,
                    company_fields=company_fields,
                    naming_metadata=naming_metadata,
                    hierarchy_pattern=hierarchy_pattern,
                    related_tables=related_tables,
                    cascading_logic=cascading_logic,
                    grid_pattern=grid_pattern,
                    template_code=source_company_examples,
                    previous_errors=previous_errors
                )
                prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly tag validation retry')
                continue
            
            logger.info("✅ All required tags present in LLM output")
            
            # FIX 2: REMOVE FALLBACK PARSING - ONLY TAG-BASED PARSING ALLOWED
            logger.info("🔍 Parsing tagged sections...")
            sections = self._parse_controlled_generation_sections(llm_content)
            
            logger.info(f"✅ Sections parsed: {list(sections.keys())}")
            
            # FIX 3: FAIL FAST ON EMPTY SECTIONS (MANDATORY)
            # Check immediately after parsing - do NOT wait for max retries
            empty_sections = [
                section_name for section_name in ['VARIABLE_INIT_PHP', 'CRUD_LOGIC_PHP', 'AJAX_HANDLERS_PHP', 'FORM_FIELDS_HTML', 'ENTITY_JS']
                if not sections.get(section_name, '').strip()
            ]
            if empty_sections:
                error_msg = f"EMPTY SECTIONS DETECTED: {', '.join(empty_sections)}"
                logger.error(error_msg)
                previous_errors.append(error_msg)
                if attempt >= max_retries - 1:
                    raise ValueError(f"Controlled assembly failed: Required sections are empty: {', '.join(empty_sections)}")
                prompt = self._build_controlled_sections_prompt(
                    intent=intent,
                    user_request=user_request,
                    company_fields=company_fields,
                    naming_metadata=naming_metadata,
                    hierarchy_pattern=hierarchy_pattern,
                    related_tables=related_tables,
                    cascading_logic=cascading_logic,
                    grid_pattern=grid_pattern,
                    template_code=source_company_examples,
                    previous_errors=previous_errors
                )
                prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly empty section retry')
                continue
            
            logger.info("✅ All sections contain content")

            logger.info("🔧 Assembling PHP file...")
            assembled = self._assemble_controlled_php_file(
                fixed_parts=fixed_parts,
                naming_metadata=naming_metadata,
                sections=sections,
                company_fields=company_fields,
                user_request=user_request,
                strict_contract_mode=bool(
                    (intent or {}).get('strict_contract_mode')
                    or ((intent or {}).get('strict_contract') or {}).get('valid')
                )
            )
            logger.info(f"✅ PHP file assembled ({len(assembled)} chars)")

            # ✅ PHASE 1.4: Calculate section completeness before validation
            logger.info("📊 Calculating section completeness...")
            user_requirements = self._detect_user_requirements(user_request)
            completeness_scores = self._calculate_section_completeness(sections, user_requirements)
            
            # Store completeness in metadata
            self.last_generation_metadata['section_completeness'] = completeness_scores
            
            # ✅ PHASE 1.4: Fail fast if overall completeness is too low
            overall_completeness = completeness_scores.get('OVERALL', 0)
            if overall_completeness < 40:
                error_msg = f"❌ SECTION COMPLETENESS TOO LOW: {overall_completeness:.0f}% (minimum: 40%)"
                logger.error(error_msg)
                logger.error(f"   Section scores: {completeness_scores}")
                raise ValueError(error_msg)

            logger.info("🔍 Validating company functions...")
            validation_result = self._validate_company_functions(
                assembled,
                user_request,
                hierarchy_pattern,
                company_fields=company_fields,
                grid_pattern=grid_pattern,
                naming_metadata=naming_metadata
            )
            logger.info(f"✅ Validation complete: {validation_result.get('valid', False)}")
            
            # ✅ PHASE 1.3: AUTO-REPAIR - Try to fix missing critical blocks
            if not validation_result.get('valid', False):
                logger.info("🔧 Attempting auto-repair for validation failures...")
                assembled, was_repaired = self._auto_repair_critical_blocks(
                    assembled,
                    validation_result,
                    naming_metadata
                )
                
                if was_repaired:
                    logger.info("🔍 Re-validating after auto-repair...")
                    validation_result = self._validate_company_functions(
                        assembled,
                        user_request,
                        hierarchy_pattern,
                        company_fields=company_fields,
                        grid_pattern=grid_pattern,
                        naming_metadata=naming_metadata
                    )
                    logger.info(f"✅ Re-validation complete: {validation_result.get('valid', False)}")
            
            last_validation_result = validation_result.copy()
            self.last_validation_result = validation_result.copy()
            if validation_result.get('valid'):
                fallback_summary = self._finalize_fallback_usage(assembled)
                llm_dynamic_chars = sum(
                    len(self._sanitize_controlled_section(section_name, section_value))
                    for section_name, section_value in sections.items()
                    if section_name in {
                        'VARIABLE_INIT_PHP',
                        'CRUD_LOGIC_PHP',
                        'AJAX_HANDLERS_PHP',
                        'FORM_FIELDS_HTML',
                        'FORM_VALIDATION_FIELDS',
                        'SELECT2_HANDLERS',
                        'ENTITY_JS',
                    }
                )
                fixed_framework_chars = max(0, len(assembled) - llm_dynamic_chars)
                self.last_generation_metadata.update({
                    'attempts_made': llm_attempts_made,
                    'refusal_count': refusal_count,
                    'llm_call_failures': llm_call_failures,
                    'output_length': len(assembled),
                    'controlled_section_lengths': {
                        key: len(value or '')
                        for key, value in sections.items()
                    },
                    'llm_dynamic_section_chars': llm_dynamic_chars,
                    'fixed_framework_chars': fixed_framework_chars,
                    'post_generation_generic_fallback_ratio_percent': fallback_summary.get('generic_ratio_percent', 0),
                    'post_generation_company_template_ratio_percent': fallback_summary.get('company_template_ratio_percent', 0),
                    'dynamic_section_llm_share_percent': 100.0,
                    'structure_locked': True,
                })
                logger.info(
                    "✅ Controlled assembly validation passed "
                    f"(dynamic_chars={llm_dynamic_chars}, fixed_framework_chars={fixed_framework_chars}, "
                    f"postgen_template_ratio={fallback_summary.get('company_template_ratio_percent', 0)}%)"
                )
                return assembled

            blockers = [
                blocker.get('message', blocker.get('key', 'required_pattern'))
                for blocker in validation_result.get('required_blockers', []) or []
                if blocker
            ]
            if not blockers:
                blockers = validation_result.get('missing_functions', []) or ['Validation failed']
            previous_errors.extend(blockers[:12])
            if attempt >= max_retries - 1:
                break

            prompt = self._build_controlled_sections_prompt(
                intent=intent,
                user_request=user_request,
                company_fields=company_fields,
                naming_metadata=naming_metadata,
                hierarchy_pattern=hierarchy_pattern,
                related_tables=related_tables,
                cascading_logic=cascading_logic,
                grid_pattern=grid_pattern,
                template_code=source_company_examples,
                previous_errors=previous_errors
            )
            prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='controlled assembly validation retry')

        missing_funcs = last_validation_result.get('missing_functions', []) or []
        missing_str = ', '.join(missing_funcs) if missing_funcs else '(none)'

        blockers = last_validation_result.get('required_blockers', []) or []
        blocker_keys = ', '.join(
            str(b.get('key', '?')) for b in blockers[:12] if isinstance(b, dict)
        ) or '(none)'

        raise ValueError(
            "Controlled assembly generation failed strict validation after "
            f"{max_retries} attempts. Missing functions: {missing_str}. "
            f"Required blockers: {blocker_keys}"
        )

    def _inject_keyboard_formvalidation_scaffold(
        self,
        code: str,
        company_fields: Dict,
        user_request: str = ''
    ) -> str:
        """
        Deterministically inject minimal keyboard + FormValidation scaffold when
        LLM output is close but misses these UI patterns.
        """
        patched_code = code or ""
        if not patched_code.strip():
            return patched_code

        lower_code = patched_code.lower()
        marker = "auto-injected keyboard + formvalidation scaffold"
        if marker in lower_code:
            return patched_code

        form_id = "frmAutoGenerated"
        form_id_match = re.search(r'<form[^>]*id=["\']([^"\']+)["\']', patched_code, re.IGNORECASE)
        if form_id_match:
            form_id = form_id_match.group(1).strip() or form_id
        else:
            patched_code, replacements = re.subn(
                r'<form\b',
                f'<form id="{form_id}"',
                patched_code,
                count=1,
                flags=re.IGNORECASE
            )
            if replacements == 0:
                return code

        requested_fields = []
        if isinstance(company_fields, dict):
            requested_fields = company_fields.get('user_requested_fields') or company_fields.get('form_fields') or []

        if not requested_fields:
            requested_fields = re.findall(
                r'<(?:input|select|textarea)[^>]*\bname=["\']([A-Za-z_][A-Za-z0-9_]*)["\']',
                patched_code,
                re.IGNORECASE
            )

        safe_fields = []
        seen_fields = set()
        for raw_field in requested_fields:
            field_name = str(raw_field or '').strip()
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', field_name):
                continue
            lowered = field_name.lower()
            if lowered in {'action', 'major', 'txtmode', 'ctrl_hid_value'} or lowered in seen_fields:
                continue
            seen_fields.add(lowered)
            safe_fields.append(field_name)

        if not safe_fields:
            safe_fields = ['Code', 'Name']

        safe_fields = safe_fields[:20]
        field_order_js = ", ".join(f"'{field}'" for field in safe_fields)

        required_fields = self._extract_required_fields_from_request(user_request or '')
        required_lookup = {str(field).strip().lower() for field in required_fields if str(field).strip()}

        validator_fields = safe_fields
        if required_lookup:
            filtered_required = [field for field in safe_fields if field.lower() in required_lookup]
            if filtered_required:
                validator_fields = filtered_required

        validators_js = ",\n            ".join(
            f"'{field}': {{ validators: {{ notEmpty: {{ message: '{field} is required' }} }} }}"
            for field in validator_fields
        )

        script_includes = ""
        if "formvalidation.min.js" not in lower_code:
            script_includes += '\n<script src="global/vendor/formvalidation/formValidation.min.js"></script>'
        if "formvalidation/framework/bootstrap.min.js" not in lower_code:
            script_includes += '\n<script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>'

        scaffold = f"""
{script_includes}
<script>
// AUTO-INJECTED Keyboard + FormValidation scaffold
function checkKeycode(event) {{
    if (!event || event.keyCode !== 13) {{
        return true;
    }}
    event.preventDefault();
    var order = [{field_order_js}];
    var active = document.activeElement ? document.activeElement.id : '';
    var idx = order.indexOf(active);
    if (idx >= 0 && idx < order.length - 1) {{
        var next = document.getElementById(order[idx + 1]);
        if (next) {{
            next.focus();
        }}
    }}
    return false;
}}
document.addEventListener('keydown', checkKeycode);

(function() {{
    if (typeof jQuery === 'undefined') {{
        return;
    }}
    var $form = jQuery('#{form_id}');
    if (!$form.length || typeof $form.formValidation !== 'function') {{
        return;
    }}
    $form.formValidation({{
        framework: 'bootstrap',
        fields: {{
            {validators_js}
        }}
    }});
}})();
</script>
"""

        if re.search(r'</body>', patched_code, re.IGNORECASE):
            patched_code = re.sub(r'</body>', scaffold + '\n</body>', patched_code, count=1, flags=re.IGNORECASE)
        else:
            patched_code = patched_code + '\n' + scaffold

        return patched_code

    def _init_fallback_usage_tracker(self):
        self._fallback_usage = {
            'generic_chars': 0,
            'company_template_chars': 0,
            'events': []
        }
        self.last_generation_metadata['fallback_usage'] = self._fallback_usage

    def _record_fallback_usage(
        self,
        fallback_type: str,
        reason: str,
        chars_added: int = 0,
        details: Optional[Dict[str, Any]] = None
    ):
        tracker = self._fallback_usage if isinstance(self._fallback_usage, dict) else {}
        if not tracker:
            self._init_fallback_usage_tracker()
            tracker = self._fallback_usage

        safe_chars = max(0, int(chars_added or 0))
        usage_key = 'company_template_chars' if fallback_type == 'company_template' else 'generic_chars'
        tracker[usage_key] = int(tracker.get(usage_key, 0) or 0) + safe_chars
        tracker.setdefault('events', []).append({
            'type': fallback_type,
            'reason': str(reason or '').strip() or 'fallback_applied',
            'chars_added': safe_chars,
            'details': details or {}
        })
        self.last_generation_metadata['fallback_usage'] = tracker

    def _finalize_fallback_usage(self, final_code: str) -> Dict[str, Any]:
        tracker = self._fallback_usage if isinstance(self._fallback_usage, dict) else {}
        if not tracker:
            self._init_fallback_usage_tracker()
            tracker = self._fallback_usage

        total_chars = len(final_code or '')
        generic_chars = int(tracker.get('generic_chars', 0) or 0)
        company_template_chars = int(tracker.get('company_template_chars', 0) or 0)
        capped_generic_chars = min(generic_chars, total_chars) if total_chars else 0
        capped_company_template_chars = min(company_template_chars, total_chars) if total_chars else 0
        generic_ratio_percent = (capped_generic_chars / total_chars * 100.0) if total_chars else 0.0
        company_template_ratio_percent = (
            capped_company_template_chars / total_chars * 100.0
        ) if total_chars else 0.0

        if total_chars and (
            generic_chars > total_chars or
            company_template_chars > total_chars
        ):
            logger.warning(
                "Fallback usage exceeded final output size; capping ratios "
                "(generic=%s, company_template=%s, total=%s)",
                generic_chars,
                company_template_chars,
                total_chars
            )

        generic_budget_bps = get_int_setting(
            'CODEGEN_MAX_GENERIC_FALLBACK_BPS',
            'CODEGEN_MAX_GENERIC_FALLBACK_BPS',
            100,
            min_value=0,
            max_value=5000
        )
        generic_budget_percent = generic_budget_bps / 100.0
        generic_budget_passed = generic_ratio_percent <= (generic_budget_percent + 1e-9)

        tracker.update({
            'total_output_chars': total_chars,
            'generic_ratio_percent': round(generic_ratio_percent, 5),
            'company_template_ratio_percent': round(company_template_ratio_percent, 5),
            'generic_ratio_chars_capped': capped_generic_chars,
            'company_template_ratio_chars_capped': capped_company_template_chars,
            'generic_budget_percent': generic_budget_percent,
            'generic_budget_passed': generic_budget_passed
        })
        if tracker.get('events') and generic_chars > 0 and not self.last_generation_metadata.get('fallback_mode'):
            self.last_generation_metadata['fallback_mode'] = 'partial_auto_attach_generic'
        self.last_generation_metadata['fallback_usage'] = tracker
        self.last_generation_metadata['generic_fallback_ratio_percent'] = tracker['generic_ratio_percent']
        self.last_generation_metadata['generic_fallback_budget_percent'] = generic_budget_percent
        self.last_generation_metadata['generic_fallback_budget_passed'] = generic_budget_passed
        return tracker

    def _normalize_include_snippet(self, snippet: str) -> str:
        text = str(snippet or '').strip()
        if not text:
            return ''
        if text.startswith('<?php'):
            return text
        if text.lower().startswith('include') or text.lower().startswith('require'):
            return f"<?php {text.rstrip(';')}; ?>"
        return text

    def _extract_include_line(self, include_block: str, keyword: str) -> str:
        if not include_block:
            return ''
        keyword_lower = str(keyword or '').lower()
        for raw_line in str(include_block).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if keyword_lower and keyword_lower not in line.lower():
                continue
            if 'include' in line.lower() or 'require' in line.lower():
                return self._normalize_include_snippet(line)
        return ''

    def _extract_field_contract_from_request(self, user_request: str) -> List[Dict[str, object]]:
        """Parse a structured field contract from the user's Master Fields section."""
        contracts: List[Dict[str, object]] = []
        seen = set()

        section_map = [
            ('master', ('master fields', 'form fields', 'fields')),
            ('detail', ('detail grid', 'detail fields', 'child fields', 'line items', 'grid fields')),
        ]
        for section_name, section_aliases in section_map:
            for line in self._extract_bullet_section(user_request or '', section_aliases):
                if not self._line_looks_like_field_definition(line):
                    continue

                field_names = self._extract_field_names_from_line(line)
                if not field_names:
                    continue

                field_name = field_names[0]
                field_key = field_name.lower()
                if field_key in seen:
                    continue

                db_type_match = re.search(r'\bDB\s*:\s*([^|]+)', line, re.IGNORECASE)
                input_type_match = re.search(r'\bInput\s*:\s*([^|]+)', line, re.IGNORECASE)
                required_match = re.search(r'\bRequired\s*:\s*(Yes|True|Mandatory)\b', line, re.IGNORECASE)

                contracts.append({
                    'name': field_name,
                    'db_type': (db_type_match.group(1).strip() if db_type_match else ''),
                    'input_type': (input_type_match.group(1).strip() if input_type_match else ''),
                    'required': bool(required_match),
                    'readonly': bool(re.search(r'\breadonly\b', line, re.IGNORECASE)),
                    'section': section_name,
                })
                seen.add(field_key)

        return contracts

    def _build_request_contract(
        self,
        user_request: str,
        naming_metadata: Dict,
        company_fields: Dict,
        hierarchy_pattern: Dict,
        related_tables: List[Dict],
        grid_pattern: Dict
    ) -> Dict[str, object]:
        request_metadata = self._extract_explicit_request_metadata(user_request or '')
        parsed_schema = self._parse_request_schema_cached(user_request or '')

        field_contract = self._extract_field_contract_from_request(user_request or '')
        parsed_fields = parsed_schema.get('fields') or []
        if parsed_fields:
            normalized_contract = []
            for field in parsed_fields:
                if not isinstance(field, dict):
                    continue
                field_name = str(field.get('name') or '').strip()
                if not field_name:
                    continue
                normalized_contract.append({
                    'name': field_name,
                    'db_type': str(field.get('db_type') or '').strip(),
                    'input_type': str(field.get('input_type') or '').strip(),
                    'required': bool(field.get('required')),
                    'readonly': bool(field.get('readonly')),
                    'section': str(field.get('section') or 'master').strip().lower(),
                })
            if normalized_contract:
                field_contract = normalized_contract

        requested_fields = (
            (company_fields or {}).get('user_requested_fields')
            or (company_fields or {}).get('form_fields')
            or [item.get('name') for item in field_contract if item.get('name')]
        )

        detail_table = (
            str(parsed_schema.get('detail_table') or '').strip()
            or str((grid_pattern or {}).get('sub_table') or '').strip()
        )

        master_fields = []
        detail_fields = []
        for item in field_contract:
            section = str(item.get('section') or 'master').strip().lower()
            if section in {'detail', 'grid', 'child', 'line'}:
                detail_fields.append(item)
            else:
                master_fields.append(item)

        relationships = []
        if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical'):
            relationships.append({
                'type': 'hierarchy',
                'parent_db_field': hierarchy_pattern.get('parent_field'),
                'parent_request_param': hierarchy_pattern.get('parent_request_param'),
                'parent_html_field': hierarchy_pattern.get('parent_js_field_id') or hierarchy_pattern.get('parent_field'),
            })
        if detail_table:
            relationships.append({
                'type': 'detail_grid',
                'sub_table': detail_table,
                'grid_fields': [str(field.get('name') or '') for field in detail_fields if field.get('name')],
            })

        dependencies = []
        for rel in related_tables or []:
            rel_table = str(rel.get('table', '')).strip()
            if not rel_table:
                continue
            dependencies.append({
                'table': rel_table,
                'field': str(rel.get('field', '')).strip(),
                'message': str(rel.get('message', '')).strip(),
            })

        return {
            'entity': (
                (naming_metadata or {}).get('case_type')
                or request_metadata.get('case_type')
                or (naming_metadata or {}).get('title')
                or request_metadata.get('title')
                or 'Entity'
            ),
            'table': (
                (naming_metadata or {}).get('table_name')
                or request_metadata.get('table_name')
                or 'tblentity'
            ),
            'primary_key': (
                (company_fields or {}).get('primary_key')
                or request_metadata.get('primary_key')
                or 'Code'
            ),
            'fields': field_contract,
            'master_fields': master_fields,
            'detail_fields': detail_fields,
            'detail_table': detail_table,
            'field_names': requested_fields,
            'relationships': relationships,
            'dependencies': dependencies,
        }

    def _format_request_contract(self, request_contract: Dict[str, object]) -> str:
        if not request_contract:
            return 'Contract unavailable.'

        lines = [
            f"entity: {request_contract.get('entity')}",
            f"table: {request_contract.get('table')}",
            f"primary_key: {request_contract.get('primary_key')}",
            f"detail_table: {request_contract.get('detail_table') or 'none'}",
            "fields:",
        ]

        field_contract = request_contract.get('fields', []) or []
        if field_contract:
            for field in field_contract:
                lines.append(
                    "- {name} | DB: {db_type} | Input: {input_type} | Required: {required} | Readonly: {readonly} | Section: {section}".format(
                        name=field.get('name', ''),
                        db_type=field.get('db_type', '') or 'unspecified',
                        input_type=field.get('input_type', '') or 'unspecified',
                        required='Yes' if field.get('required') else 'No',
                        readonly='Yes' if field.get('readonly') else 'No',
                        section=field.get('section', 'master') or 'master',
                    )
                )
        else:
            for field_name in request_contract.get('field_names', []) or []:
                lines.append(f"- {field_name}")

        lines.append("relationships:")
        relationships = request_contract.get('relationships', []) or []
        if relationships:
            for rel in relationships:
                if rel.get('type') == 'hierarchy':
                    lines.append(
                        f"- hierarchy | parent_db_field={rel.get('parent_db_field')} | parent_request_param={rel.get('parent_request_param')} | parent_html_field={rel.get('parent_html_field')}"
                    )
                elif rel.get('type') == 'detail_grid':
                    lines.append(
                        f"- detail_grid | sub_table={rel.get('sub_table')} | grid_fields={', '.join(rel.get('grid_fields', []) or [])}"
                    )
        else:
            lines.append("- none")

        lines.append("dependencies:")
        dependencies = request_contract.get('dependencies', []) or []
        if dependencies:
            for dep in dependencies:
                lines.append(
                    f"- {dep.get('table')} | field={dep.get('field') or request_contract.get('primary_key')} | message={dep.get('message') or 'n/a'}"
                )
        else:
            lines.append("- none")

        return '\n'.join(lines)

    def _build_master_detail_crud_instruction(self, request_contract: Dict[str, object]) -> str:
        """
        Build explicit master/detail CRUD constraints to prevent field mixing.
        """
        if not request_contract:
            return ""

        detail_table = str(request_contract.get('detail_table') or '').strip()
        if not detail_table:
            return ""

        primary_key = str(request_contract.get('primary_key') or 'Code').strip() or 'Code'
        master_table = str(request_contract.get('table') or 'tblentity').strip() or 'tblentity'
        master_fields = [
            str(item.get('name') or '').strip()
            for item in (request_contract.get('master_fields') or [])
            if str(item.get('name') or '').strip()
        ]
        detail_fields = [
            str(item.get('name') or '').strip()
            for item in (request_contract.get('detail_fields') or [])
            if str(item.get('name') or '').strip()
        ]

        return f"""
MASTER-DETAIL CRUD RULES (NON-NEGOTIABLE):
- Master table: {master_table}
- Detail table: {detail_table}
- Primary key: {primary_key}
- NEVER put detail fields into master db_insert/db_update.
- NEVER put master fields into detail db_insert loop.
- Detail loop MUST use TXTCOUNTACC and for ($i = 1; $i <= $count; $i++).
- Update flow MUST delete old detail rows, then re-insert detail rows.

Master fields:
{', '.join(master_fields) if master_fields else '(from contract master section)'}
Detail fields:
{', '.join(detail_fields) if detail_fields else '(from contract detail section)'}

Required skeleton:
1) Save:
   - db_insert('{master_table}', $columns) with master fields only.
   - loop TXTCOUNTACC and db_insert('{detail_table}', $detail_columns).
2) Update:
   - db_delete('{detail_table}', '{primary_key} = ?', [$Code]);
   - db_update('{master_table}', $columns, '{primary_key} = ?', [$Code]);
   - re-insert detail loop.
3) Delete:
   - run dependency checks inside delete-action block only;
   - delete detail first, then master.
""".strip()

    def _build_ajax_handlers_instruction(self, request_contract: Dict[str, object]) -> str:
        """
        Build minimum mandatory AJAX handlers template to avoid near-empty AJAX section.
        """
        if not request_contract:
            return ""
        primary_key = str(request_contract.get('primary_key') or 'Code').strip() or 'Code'
        master_table = str(request_contract.get('table') or 'tblentity').strip() or 'tblentity'
        pk_prefix = primary_key[:1].upper() if primary_key else 'A'

        return f"""
AJAX_HANDLERS_PHP MUST INCLUDE REAL LOGIC (NOT PLACEHOLDERS):
1) GetMaxID handler (mandatory):
   if (isset($_POST['Action']) && $_POST['Action'] == 'GetMaxID') {{
       $max = getvalue("SELECT ISNULL(MAX(CAST(SUBSTRING({primary_key}, 2, LEN({primary_key})) AS INT)), 0) + 1 FROM {master_table} WHERE Comp_Code = ?", [$comp_code]);
       $new_id = '{pk_prefix}' . str_pad($max, 4, '0', STR_PAD_LEFT);
       echo $new_id;
       exit;
   }}
2) Any requested dropdown AJAX handler(s) with json_encode(...) and exit;
3) If dependencies/validations require AJAX checks, include explicit action handlers.
""".strip()

    def _build_predelete_placement_rule(self) -> str:
        return """
PRE-DELETE PLACEMENT RULE (MANDATORY):
- Dependency checks MUST run only inside delete action block:
  if (isset($_POST['action']) && $_POST['action'] == 'delete') { ... }
- NEVER place dependency checks at file top-level.
- NEVER run dependency checks on GET/page-load.
""".strip()

    def _ensure_form_layout_structure(self, code: str) -> Tuple[str, int]:
        patched = code
        chars_added = 0
        form_open_pattern = r'<form\b(?:(?:"[^"]*"|\'[^\']*\'|<\?(?:php|=)?[\s\S]*?\?>|[^>])*)>'

        def _form_replacer(match):
            nonlocal chars_added
            tag = match.group(0)
            updated = tag

            class_match = re.search(r'class\s*=\s*["\']([^"\']*)["\']', updated, re.IGNORECASE)
            if class_match:
                classes = class_match.group(1).strip()
                if 'form-horizontal' not in classes.lower():
                    merged_classes = (classes + ' form-horizontal').strip()
                    updated = updated[:class_match.start(1)] + merged_classes + updated[class_match.end(1):]
            else:
                updated = updated.replace('<form', '<form class="form-horizontal"', 1)

            if not re.search(r'\bid\s*=\s*["\']', updated, re.IGNORECASE):
                updated = updated.replace('<form', '<form id="frm"', 1)

            if updated != tag:
                chars_added += max(0, len(updated) - len(tag))
            return updated

        patched, replaced = re.subn(form_open_pattern, _form_replacer, patched, count=1, flags=re.IGNORECASE)

        if replaced and 'control-label' not in patched.lower():
            patched, label_replacements = re.subn(
                r'<label(?![^>]*class=)([^>]*)>',
                r'<label class="control-label"\1>',
                patched,
                count=8,
                flags=re.IGNORECASE
            )
            if label_replacements:
                chars_added += label_replacements * len(' class="control-label"')

        return patched, chars_added

    def _ensure_page_container(self, code: str) -> Tuple[str, int]:
        if '<div class="page"' in code.lower():
            return code, 0

        form_match = re.search(r'(<form\b.*?</form>)', code, re.IGNORECASE | re.DOTALL)
        if not form_match:
            return code, 0

        wrapped_form = (
            '<div class="page">\n'
            '  <div class="page-content padding-30">\n'
            '    <div class="panel">\n'
            '      <div class="panel-body container-fluid">\n'
            '        <div class="row row-lg">\n'
            '          <div class="col-sm-12 col-md-12">\n'
            f'{form_match.group(1)}\n'
            '          </div>\n'
            '        </div>\n'
            '      </div>\n'
            '    </div>\n'
            '  </div>\n'
            '</div>'
        )
        patched = code[:form_match.start(1)] + wrapped_form + code[form_match.end(1):]
        return patched, max(0, len(wrapped_form) - len(form_match.group(1)))

    def _insert_after_body_tag(self, code: str, snippet: str) -> Tuple[str, int]:
        body_match = re.search(r'<body[^>]*>', code, re.IGNORECASE)
        if not body_match:
            return code, 0
        insertion = '\n' + snippet + '\n'
        patched = code[:body_match.end()] + insertion + code[body_match.end():]
        return patched, len(insertion)

    def _insert_before_body_close(self, code: str, snippet: str) -> Tuple[str, int]:
        body_close_match = re.search(r'</body>', code, re.IGNORECASE)
        if not body_close_match:
            return code + '\n' + snippet + '\n', len('\n' + snippet + '\n')
        insertion = '\n' + snippet + '\n'
        patched = code[:body_close_match.start()] + insertion + code[body_close_match.start():]
        return patched, len(insertion)

    def _insert_before_first_php_close(self, code: str, snippet: str) -> Tuple[str, int]:
        php_close_match = re.search(r'\?>', code)
        if not php_close_match:
            return code, 0
        insertion = '\n' + snippet + '\n'
        patched = code[:php_close_match.start()] + insertion + code[php_close_match.start():]
        return patched, len(insertion)

    def _inject_business_validation_guards(self, code: str, user_request: str = '') -> Tuple[str, int]:
        patched = code or ''
        if not patched.strip():
            return patched, 0

        marker = 'AUTO-INJECTED business validation guard'
        if marker.lower() in patched.lower():
            return patched, 0

        required_fields = self._extract_required_fields_from_request(user_request or '')
        unique_fields = self._extract_unique_fields_from_request(user_request or '')
        validate_email = self._request_requires_email_validation(user_request or '')
        primary_field = (
            self._extract_primary_key_from_request(user_request or '')
            or self.last_generation_metadata.get('primary_key')
            or 'Code'
        )

        if not (required_fields or unique_fields or validate_email):
            return patched, 0

        save_patterns = [
            r'if\s*\(\s*isset\(\s*\\$_POST\[\s*["\']txtmode["\']\s*\]\s*\)[\s\S]{0,120}?["\']save["\']\s*\)\s*\{',
            r'if\s*\(\s*\\$_REQUEST\[\s*["\']action["\']\s*\]\s*==\s*["\']save["\'][\s\S]{0,180}?\)\s*\{',
            r'if\s*\(\s*\\$_REQUEST\[\s*["\']Action["\']\s*\]\s*==\s*["\']save["\'][\s\S]{0,180}?\)\s*\{',
            r'if\s*\(\s*\\$_POST\[\s*["\']action["\']\s*\]\s*==\s*["\']save["\'][\s\S]{0,180}?\)\s*\{',
            r'if\s*\(\s*\\$_POST\[\s*["\']Action["\']\s*\]\s*==\s*["\']save["\'][\s\S]{0,180}?\)\s*\{',
        ]
        save_block = None
        for pattern in save_patterns:
            candidate = re.search(pattern, patched, re.IGNORECASE)
            if candidate and (save_block is None or candidate.start() < save_block.start()):
                save_block = candidate
        if not save_block:
            return patched, 0

        required_fields = required_fields[:20]
        unique_fields = unique_fields[:6]
        required_checks = []
        for field in required_fields:
            lowered = str(field).lower()
            if lowered in {'is_active', 'status', 'action', 'txtmode', 'ctrl_hid_value'}:
                continue
            required_checks.append(
                f"    if (trim((string)($_REQUEST['{field}'] ?? '')) === '') {{ $_autoErrors[] = '{field} is required'; }}"
            )

        unique_checks = []
        for field in unique_fields:
            unique_checks.append(
                f"    $_autoUnique_{field} = trim((string)($_REQUEST['{field}'] ?? ''));\n"
                f"    if ($_autoUnique_{field} !== '' && function_exists('getvalue')) {{\n"
                f"        $_autoDupWhere = \"{field}='\".addslashes($_autoUnique_{field}).\"' AND Comp_Code='\".$_autoCompCode.\"'\";\n"
                f"        if ($_autoCurrentId !== '') {{ $_autoDupWhere .= \" AND {primary_field}<>'\".addslashes($_autoCurrentId).\"'\"; }}\n"
                f"        $_autoDupCount = (int)getvalue(\"COUNT(*)\", $table, $_autoDupWhere);\n"
                f"        if ($_autoDupCount > 0) {{ $_autoErrors[] = '{field} must be unique within comp_code'; }}\n"
                "    }"
            )

        email_check = ""
        if validate_email:
            email_check = (
                "    \\$_autoEmail = trim((string)(\\$_REQUEST['Email'] ?? ''));\n"
                "    if (\\$_autoEmail !== '' && !filter_var(\\$_autoEmail, FILTER_VALIDATE_EMAIL)) {\n"
                "        \\$_autoErrors[] = 'Invalid Email format';\n"
                "    }\n"
            )

        guard_parts = [
            "\n    // AUTO-INJECTED business validation guard",
            "    \\$_autoErrors = array();",
            "    \\$_autoCompCode = (string)(\\$_SESSION['comp_code'] ?? '');",
            f"    \\$_autoCurrentId = (string)(\\$_REQUEST['{primary_field}'] ?? '');",
        ]
        guard_parts.extend(required_checks)
        if email_check:
            guard_parts.append(email_check.rstrip('\n'))
        guard_parts.extend(unique_checks)
        guard_parts.extend([
            "    if (!empty($_autoErrors)) {",
            "        if (function_exists('funEndTran')) { funEndTran(); }",
            "        print \"<script>alert('\".addslashes(implode(\"\\\\n\", $_autoErrors)).\"');</script>\";",
            "        exit;",
            "    }",
            "",
        ])
        guard_block = '\n'.join(guard_parts)

        insertion_index = save_block.end()
        fun_start_match = re.search(
            r'funStartTran\s*\(\s*\)\s*;',
            patched[insertion_index:insertion_index + 400],
            re.IGNORECASE
        )
        if fun_start_match:
            insertion_index += fun_start_match.end()

        patched = patched[:insertion_index] + guard_block + patched[insertion_index:]
        return patched, len(guard_block)

    def _inject_company_scope_columns(self, code: str) -> Tuple[str, int]:
        patched = code or ''
        if not patched.strip():
            return patched, 0

        source = patched
        baseline_len = len(patched)

        def _inject_before_write(match):
            indent = match.group('indent') or ''
            call = match.group('call')
            array_var = match.group('array')
            lookback = source[max(0, match.start() - 260):match.start()]
            if re.search(
                rf'{re.escape(array_var)}\s*\[\s*["\']Comp_Code["\']\s*\]',
                lookback,
                re.IGNORECASE
            ):
                return match.group(0)

            guard = (
                f"{indent}if (!isset({array_var}['Comp_Code'])) "
                "{ "
                f"{array_var}['Comp_Code'] = \\$_SESSION['comp_code'] ?? ''; "
                "}\n"
            )
            return f"{guard}{indent}{call}"

        patched = re.sub(
            r'(?m)^(?P<indent>\s*)(?P<call>db_(?:insert|update)\s*\(\s*[^,\n]+?\s*,\s*(?P<array>\$[A-Za-z_][A-Za-z0-9_]*)\s*(?:,\s*[^;\n]+?)?\)\s*;)',
            _inject_before_write,
            patched,
            flags=re.IGNORECASE
        )

        return patched, max(0, len(patched) - baseline_len)

    def _enforce_comp_code_scope_on_db_helpers(self, code: str) -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        def _patch_helper_call(match, fn_name: str, update_signature: bool = False):
            filter_expr = (match.group('filter') or '').strip()
            if 'comp_code' in filter_expr.lower():
                return match.group(0)
            if update_signature:
                return (
                    f"db_update($table, $columns, {filter_expr} . "
                    "\" AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'\");"
                )
            return (
                f"{fn_name}($table, {filter_expr} . "
                "\" AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'\");"
            )

        patched = re.sub(
            r'db_update\s*\(\s*\$table\s*,\s*\$columns\s*,\s*(?P<filter>[^;]+?)\);',
            lambda m: _patch_helper_call(m, 'db_update', update_signature=True),
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'db_delete\s*\(\s*\$table\s*,\s*(?P<filter>[^;]+?)\);',
            lambda m: _patch_helper_call(m, 'db_delete'),
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'db_getrecord\s*\(\s*\$table\s*,\s*(?P<filter>[^;]+?)\);',
            lambda m: _patch_helper_call(m, 'db_getRecord'),
            patched,
            flags=re.IGNORECASE
        )

        def _patch_select_scope(match):
            prefix = match.group('prefix')
            where_body = match.group('where')
            suffix = match.group('suffix')
            if 'comp_code' in where_body.lower():
                return match.group(0)
            return f"{prefix}{where_body} AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'{suffix}"

        patched = re.sub(
            r'(?P<prefix>qry\s*\(\s*"SELECT\s+\*\s+FROM\s+\$table\s+WHERE\s+)(?P<where>[^"]+)(?P<suffix>"\s*\))',
            _patch_select_scope,
            patched,
            flags=re.IGNORECASE
        )

        def _patch_delete_expr(match):
            filter_expr = (match.group('filter') or '').strip()
            if 'comp_code' in filter_expr.lower():
                return match.group(0)
            return (
                "db_delete($table, "
                f"{filter_expr} . "
                "\" AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'\")"
            )

        def _patch_getrecord_expr(match):
            filter_expr = (match.group('filter') or '').strip()
            if 'comp_code' in filter_expr.lower():
                return match.group(0)
            return (
                "db_getRecord($table, "
                f"{filter_expr} . "
                "\" AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'\")"
            )

        patched = re.sub(
            r'db_delete\s*\(\s*\$table\s*,\s*(?P<filter>[^)\n]+?)\s*\)',
            _patch_delete_expr,
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'db_getrecord\s*\(\s*\$table\s*,\s*(?P<filter>[^)\n]+?)\s*\)',
            _patch_getrecord_expr,
            patched,
            flags=re.IGNORECASE
        )

        return patched

    def _rewrite_external_ajax_endpoints(self, code: str) -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        endpoint_expr = (
            "(typeof form2 !== 'undefined' && form2) ? form2 : "
            "'<?php echo isset($form2) ? $form2 : (isset($form) ? $form : \"\"); ?>'"
        )

        patched = re.sub(
            r'url\s*:\s*[\'"]ajax/getMaxID\.php[\'"]',
            f"url: {endpoint_expr}",
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'url\s*:\s*[\'"]ajax/getStates?\.php[\'"]',
            f"url: {endpoint_expr}",
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'url\s*:\s*[\'"]ajax/getCities?\.php[\'"]',
            f"url: {endpoint_expr}",
            patched,
            flags=re.IGNORECASE
        )

        patched = re.sub(
            r'data\s*:\s*\{\s*country\s*:\s*([^}]+)\}',
            r"data: {Action:'GetStates', Country_Code: \1}",
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'data\s*:\s*\{\s*state\s*:\s*([^}]+)\}',
            r"data: {Action:'GetCities', State_Code: \1}",
            patched,
            flags=re.IGNORECASE
        )
        return patched

    def _normalize_db_getrecord_usage(self, code: str) -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        patched = re.sub(
            r'mysql_fetch_(?:array|assoc|row)\s*\(\s*db_getRecord\(\s*(?P<table>[^,]+?)\s*,\s*(?P<filter>[^)]+?)\s*\)\s*\.\s*(?P<suffix>"[^"]*Comp_Code[^"]*"[^)]*)\)',
            lambda m: f"db_getRecord({m.group('table')}, {m.group('filter')} . {m.group('suffix')})",
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r'mysql_fetch_(?:array|assoc|row)\s*\(\s*db_getRecord\((?P<args>[\s\S]*?)\)\s*\)',
            lambda m: f"db_getRecord({m.group('args')})",
            patched,
            flags=re.IGNORECASE
        )

        return patched

    def _align_primary_key_filters(self, code: str, user_request: str = '') -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        primary_field = (
            self._extract_primary_key_from_request(user_request or '')
            or self.last_generation_metadata.get('primary_key')
            or ''
        ).strip()
        if not primary_field:
            return patched

        def _replace_block_filter(match):
            field_name = (match.group('field') or '').strip()
            if not field_name or field_name.lower() == primary_field.lower():
                return match.group(0)
            return match.group(0).replace(field_name, primary_field, 1)

        for action_name in ('Delete', 'Edit', 'Update'):
            patched = re.sub(
                rf'if\s*\(\s*\\\$_REQUEST\[\s*["\'](?:action|Action)["\']\s*\]\s*==\s*["\']{action_name}["\']\s*\)\s*\{{[\s\S]{{0,240}}?\$filter\s*=\s*"\s*(?P<field>[A-Za-z_][A-Za-z0-9_]*)\s*=',
                _replace_block_filter,
                patched,
                flags=re.IGNORECASE
            )

        return patched

    def _collapse_duplicate_comp_code_filters(self, code: str) -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        patched = re.sub(
            r'(\s*\.\s*" AND Comp_Code=\'"\.\\\$_SESSION\[[\'"]comp_code[\'"]\]\."\'")(\s*\.\s*" AND Comp_Code=\'"\.\\\$_SESSION\[[\'"]comp_code[\'"]\]\."\'")+',
            r'\1',
            patched,
            flags=re.IGNORECASE
        )
        patched = re.sub(
            r"(AND\s+Comp_Code\s*=\s*['\"][^'\"]+['\"])(\s+AND\s+Comp_Code\s*=\s*['\"][^'\"]+['\"])+",
            r'\1',
            patched,
            flags=re.IGNORECASE
        )

        return patched

    def _apply_html_output_escaping(self, code: str) -> str:
        patched = code or ''
        if not patched.strip():
            return patched

        patched = re.sub(
            r"<\?php\s+echo\s+isset\(\$OBJ\['([^']+)'\]\)\s*\?\s*\$OBJ\['\1'\]\s*:\s*''\s*;\s*\?>",
            r"<?php echo isset($OBJ['\1']) ? htmlspecialchars($OBJ['\1']) : ''; ?>",
            patched
        )
        patched = re.sub(
            r"<\?php\s+echo\s+\$OBJ\['([^']+)'\]\s*;\s*\?>",
            r"<?php echo htmlspecialchars($OBJ['\1']); ?>",
            patched
        )
        return patched

    def _dedupe_and_secure_asset_lines(self, code: str) -> str:
        patched = (code or '').replace('http://code.jquery.com/', 'https://code.jquery.com/')
        if not patched.strip():
            return patched

        seen = set()
        deduped_lines = []
        for line in patched.splitlines():
            raw_line = line.rstrip('\n')
            stripped = raw_line.strip()

            key = None
            href_match = re.search(r'<link[^>]*href=["\']([^"\']+)["\']', stripped, re.IGNORECASE)
            src_match = re.search(r'<script[^>]*src=["\']([^"\']+)["\']', stripped, re.IGNORECASE)
            if href_match:
                key = f"link:{href_match.group(1).strip().lower()}"
            elif src_match:
                key = f"script:{src_match.group(1).strip().lower()}"
            elif stripped.startswith('<link') or stripped.startswith('<script'):
                key = f"line:{stripped.lower()}"

            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped_lines.append(raw_line)

        return '\n'.join(deduped_lines)

    def _apply_production_hardening(self, code: str, user_request: str = '') -> Tuple[str, int]:
        patched = code or ''
        if not patched.strip():
            return patched, 0

        baseline_len = len(patched)
        patched, _ = self._inject_business_validation_guards(patched, user_request=user_request)
        patched, _ = self._inject_company_scope_columns(patched)
        patched = self._enforce_comp_code_scope_on_db_helpers(patched)
        patched = self._normalize_db_getrecord_usage(patched)
        patched = self._align_primary_key_filters(patched, user_request=user_request)
        patched = self._collapse_duplicate_comp_code_filters(patched)
        patched = self._rewrite_external_ajax_endpoints(patched)
        patched = self._apply_html_output_escaping(patched)
        patched = self._dedupe_and_secure_asset_lines(patched)
        return patched, max(0, len(patched) - baseline_len)

    def _extract_primary_key_from_request(self, user_request: str) -> str:
        request_text = user_request or ''
        pk_match = re.search(
            r'(?is)primary\s*key\s*:\s*(?:\n|\r\n)?\s*-\s*([A-Za-z_][A-Za-z0-9_]*)',
            request_text
        )
        if pk_match:
            return pk_match.group(1).strip()
        return ''

    def _extract_predelete_tables_from_request(self, user_request: str, table_name: str = '') -> List[str]:
        request_text = user_request or ''
        table_name_lower = str(table_name or '').strip().lower()
        tables: List[str] = []

        explicit_line = re.search(
            r'(?is)pre[-\s]*delete[^\n:]*:\s*([^\n\r]+)',
            request_text
        )
        if explicit_line:
            tables.extend(re.findall(r'\btbl[a-z0-9_]+\b', explicit_line.group(1), re.IGNORECASE))

        if not tables:
            neighborhood = re.search(
                r'(?is)pre[-\s]*delete[^\n\r]{0,120}\n([^\n\r]+(?:\n[^\n\r]+){0,3})',
                request_text
            )
            if neighborhood:
                tables.extend(re.findall(r'\btbl[a-z0-9_]+\b', neighborhood.group(1), re.IGNORECASE))

        normalized = []
        for tbl in tables:
            name = str(tbl or '').strip()
            if not name:
                continue
            if table_name_lower and name.lower() == table_name_lower:
                continue
            if name.lower() not in [t.lower() for t in normalized]:
                normalized.append(name)
        return normalized

    def _inject_required_ajax_handlers(self, code: str, user_request: str = '') -> Tuple[str, int]:
        patched = code or ''
        if not patched.strip():
            return patched, 0

        request_metadata = self._extract_explicit_request_metadata(user_request or '')
        user_requirements = self._detect_user_requirements(user_request or '')
        table_name = (request_metadata.get('table_name') or self.last_generation_metadata.get('table_name') or 'tblmaster').strip()
        primary_field = (
            self._extract_primary_key_from_request(user_request or '')
            or self.last_generation_metadata.get('primary_key')
            or 'Code'
        )

        total_added = 0

        if 'GetMaxID' not in patched and 'getmaxid' not in patched.lower():
            getmaxid_handler = (
                "if((\\$_REQUEST['Action'] ?? '') == 'GetMaxID') {\n"
                f"    $maxId = function_exists('getvalue') ? getvalue(\"IFNULL(MAX(RIGHT({primary_field},4)),0)+1\", \"{table_name}\", \"Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"'\") : 1;\n"
                "    echo str_pad((string)$maxId, 4, '0', STR_PAD_LEFT);\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, getmaxid_handler)
            total_added += added

        wants_getcostcenter = bool(user_requirements.get('wants_getcostcenter'))
        if wants_getcostcenter and 'GetCOSTCENTER' not in patched:
            costcenter_handler = (
                "if((\\$_REQUEST['Action'] ?? '') == 'GetCOSTCENTER') {\n"
                "    $costCode = '';\n"
                "    if (function_exists('getvalue')) {\n"
                "        $costCode = getvalue(\"CostCenter_Code\", \"tblcostcenter\", \"Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"'\");\n"
                "    }\n"
                "    echo $costCode;\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, costcenter_handler)
            total_added += added

        if 'function maxid' not in patched.lower():
            maxid_js = (
                "<script>\n"
                "function maxid(){\n"
                "  var $ = window.jQuery;\n"
                "  if(!$){ return; }\n"
                "  var endpoint = (typeof form2 !== 'undefined' && form2) ? form2 : '<?php echo isset($form2) ? $form2 : \"\"; ?>';\n"
                "  $.post(endpoint, {Action:'GetMaxID'}, function(res){\n"
                f"    var el = document.getElementById('{primary_field}');\n"
                "    if(el && !el.value){ el.value = (res || '').toString().trim(); }\n"
                "  });\n"
                "}\n"
                "document.addEventListener('DOMContentLoaded', function(){\n"
                "  maxid();\n"
                "});\n"
                "</script>"
            )
            patched, added = self._insert_before_body_close(patched, maxid_js)
            total_added += added

        master_lines = self._extract_bullet_section(
            user_request or '',
            ('master fields', 'form fields', 'fields')
        )
        request_fields: List[str] = []
        for line in master_lines:
            request_fields.extend(self._extract_field_names_from_line(line))
        request_fields = self._unique_preserve_order(request_fields)
        request_field_lookup = {str(field).strip().lower() for field in request_fields if str(field).strip()}
        wants_country_state_city = {'country_code', 'state_code', 'city_code'}.issubset(request_field_lookup)

        if wants_country_state_city and 'GetStates' not in patched:
            getstates_handler = (
                "if((\\$_REQUEST['Action'] ?? '') == 'GetStates') {\n"
                "    $countryCode = add_Slashes_new(\\$_REQUEST['Country_Code'] ?? '');\n"
                "    if (function_exists('qry')) {\n"
                "        $sql = qry(\"SELECT State_Code, State_Name FROM tbl_state WHERE Country_Code='\".$countryCode.\"' AND Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"' ORDER BY State_Name\");\n"
                "        while($row = mysql_fetch_array($sql)) {\n"
                "            echo '<option value=\"'.htmlspecialchars($row['State_Code']).'\">'.htmlspecialchars($row['State_Name']).'</option>';\n"
                "        }\n"
                "    }\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, getstates_handler)
            total_added += added

        if wants_country_state_city and 'GetCities' not in patched:
            getcities_handler = (
                "if((\\$_REQUEST['Action'] ?? '') == 'GetCities') {\n"
                "    $stateCode = add_Slashes_new(\\$_REQUEST['State_Code'] ?? '');\n"
                "    if (function_exists('qry')) {\n"
                "        $sql = qry(\"SELECT City_Code, City_Name FROM tbl_city WHERE State_Code='\".$stateCode.\"' AND Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"' ORDER BY City_Name\");\n"
                "        while($row = mysql_fetch_array($sql)) {\n"
                "            echo '<option value=\"'.htmlspecialchars($row['City_Code']).'\">'.htmlspecialchars($row['City_Name']).'</option>';\n"
                "        }\n"
                "    }\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, getcities_handler)
            total_added += added

        return patched, total_added

    def _inject_required_grid_flow(self, code: str, user_request: str = '') -> Tuple[str, int]:
        patched = code or ''
        requested_grid = self._extract_requested_grid(user_request or '')
        if not requested_grid.get('has_grid'):
            return patched, 0

        grid_fields = [str(field).strip() for field in requested_grid.get('grid_fields', []) if str(field).strip()]
        if not grid_fields:
            return patched, 0

        txtcount_var = str(requested_grid.get('txtcount_var') or 'TXTCOUNTACC')
        sub_table = str(requested_grid.get('sub_table') or '$sub_table')
        sub_table_literal = sub_table if sub_table.startswith('tbl') else 'tbl_detail'
        loop_var = str(requested_grid.get('loop_var') or 'i')
        primary_field = (
            self._extract_primary_key_from_request(user_request or '')
            or self.last_generation_metadata.get('primary_key')
            or 'Code'
        )

        total_added = 0

        if txtcount_var.lower() not in patched.lower():
            hidden_txtcount = f'<input type="hidden" name="{txtcount_var}" id="{txtcount_var}" value="0">'
            form_open = re.search(r'<form[^>]*>', patched, re.IGNORECASE)
            if form_open:
                patched = patched[:form_open.end()] + '\n' + hidden_txtcount + patched[form_open.end():]
                total_added += len(hidden_txtcount) + 1

        if '<table' not in patched.lower() or 'tbldetailgrid' not in patched.lower():
            header_cells = ''.join(f'<th>{field}</th>' for field in grid_fields) + '<th>Action</th>'
            grid_markup = (
                '<div class="form-group">\n'
                '  <div class="col-md-12">\n'
                '    <table class="table table-striped table-bordered" id="tblDetailGrid">\n'
                f'      <thead><tr>{header_cells}</tr></thead>\n'
                '      <tbody></tbody>\n'
                '    </table>\n'
                '  </div>\n'
                '</div>'
            )
            form_close_match = re.search(r'</form>', patched, re.IGNORECASE)
            if form_close_match:
                patched = patched[:form_close_match.start()] + grid_markup + '\n' + patched[form_close_match.start():]
                total_added += len(grid_markup) + 1

        if txtcount_var.lower() not in patched.lower() or "db_delete($sub_table" not in patched.lower():
            detail_assignments = []
            for field in grid_fields:
                detail_assignments.append(
                    f"        $detail['{field}'] = add_Slashes_new(\\$_REQUEST['{field}'.${loop_var}] ?? '');"
                )
            detail_assignments_text = '\n'.join(detail_assignments)
            grid_php = (
                f"$sub_table = '{sub_table_literal}';\n"
                "if (function_exists('db_delete')) {\n"
                f"    db_delete($sub_table, \"{primary_field}='\".add_Slashes_new($primaryValue).\"' AND Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"'\");\n"
                "}\n"
                f"for(${loop_var}=0; ${loop_var}<=$_REQUEST['{txtcount_var}']; ${loop_var}++) {{\n"
                f"    if (empty($_REQUEST['{grid_fields[0]}'.${loop_var}] ?? '')) {{ continue; }}\n"
                "    $detail = array();\n"
                f"    $detail['{primary_field}'] = add_Slashes_new($primaryValue);\n"
                f"{detail_assignments_text}\n"
                "    $detail['Comp_Code'] = \\$_SESSION['comp_code'] ?? '';\n"
                "    if (function_exists('db_insert')) { db_insert($sub_table, $detail); }\n"
                "}\n"
            )

            insertion_done = False
            funend_match = re.search(r'if\s*\(\s*function_exists\s*\(\s*[\'"]funEndTran[\'"]\s*\)\s*\)', patched, re.IGNORECASE)
            if funend_match:
                patched = patched[:funend_match.start()] + grid_php + '\n' + patched[funend_match.start():]
                total_added += len(grid_php) + 1
                insertion_done = True
            if not insertion_done:
                patched_tmp, added = self._insert_before_first_php_close(patched, grid_php)
                if added:
                    patched = patched_tmp
                    total_added += added

        return patched, total_added

    def _inject_required_predelete_and_dbrecord_handlers(self, code: str, user_request: str = '') -> Tuple[str, int]:
        patched = code or ''
        if not patched.strip():
            return patched, 0

        request_metadata = self._extract_explicit_request_metadata(user_request or '')
        user_requirements = self._detect_user_requirements(user_request or '')
        table_name = (request_metadata.get('table_name') or self.last_generation_metadata.get('table_name') or 'tblmaster').strip()
        primary_field = (
            self._extract_primary_key_from_request(user_request or '')
            or self.last_generation_metadata.get('primary_key')
            or 'Code'
        )

        total_added = 0
        lower_code = patched.lower()

        if 'db_getrecord' not in lower_code:
            db_record_handler = (
                f"if(($_REQUEST['Action'] ?? '') == 'GetRecord') {{\n"
                f"    $editCode = add_Slashes_new($_REQUEST['{primary_field}'] ?? '');\n"
                "    $obj = array();\n"
                "    if (function_exists('db_getRecord')) {\n"
                f"        $obj = db_getRecord($table, \"{primary_field}='\".$editCode.\"' AND Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"'\");\n"
                "    }\n"
                "    header('Content-Type: application/json');\n"
                "    echo json_encode($obj);\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, db_record_handler)
            total_added += added
            lower_code = patched.lower()

        wants_predelete = bool(user_requirements.get('wants_predelete'))
        has_delete_action = bool(
            re.search(r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]\s*\]\s*==\s*['\"]Delete['\"]", patched, re.IGNORECASE)
        )
        has_dependency_check = bool(re.search(r"(getrows2|getrows)\s*\(", patched, re.IGNORECASE))
        has_alert_message = bool(re.search(r"(print|echo)\s+['\"]<script>alert\(", patched, re.IGNORECASE))
        has_exit_statement = bool(re.search(r"exit\s*;", patched, re.IGNORECASE))
        has_complete_predelete = has_delete_action and has_dependency_check and has_alert_message and has_exit_statement

        if wants_predelete and not has_complete_predelete:
            predelete_tables = self._extract_predelete_tables_from_request(user_request or '', table_name=table_name)
            if not predelete_tables:
                predelete_tables = ['tbl_dependency']

            checks = []
            for dep_table in predelete_tables:
                checks.append(
                    f"    if (function_exists('getrows') && getrows('{dep_table}', '{primary_field}', $deleteCode) > 0) {{\n"
                    f"        print \"<script>alert('This record exists in {dep_table}... !!!');</script>\";\n"
                    "        exit;\n"
                    "    }\n"
                )

            checks_text = ''.join(checks)
            predelete_handler = (
                f"if($_REQUEST['Action'] == 'Delete') {{\n"
                f"    $deleteCode = add_Slashes_new($_REQUEST['{primary_field}'] ?? '');\n"
                f"{checks_text}"
                "    if (function_exists('db_delete')) {\n"
                f"        db_delete($table, \"{primary_field}='\".$deleteCode.\"' AND Comp_Code='\".(\\$_SESSION['comp_code'] ?? '').\"'\");\n"
                "    }\n"
                "    if (function_exists('fun_log')) {\n"
                "        fun_log($table, $deleteCode, 'Delete', \\$_SESSION['user_id'] ?? '');\n"
                "    }\n"
                "    echo 'OK';\n"
                "    exit;\n"
                "}\n"
            )
            patched, added = self._insert_before_first_php_close(patched, predelete_handler)
            total_added += added

        return patched, total_added

    def _auto_attach_shared_components(
        self,
        code: str,
        fixed_parts: Dict[str, str],
        user_request: str = ''
    ) -> str:
        """
        Auto-attach mandatory shared company components when LLM misses them.
        This enforces layout/includes/scripts compatibility with AJAX navigation.
        """
        patched = code or ''
        if not patched.strip():
            return patched

        fixed_parts = fixed_parts or {}
        include_block = '\n'.join(
            part for part in [
                fixed_parts.get('php_bootstrap_includes', ''),
                fixed_parts.get('layout_includes', ''),
                fixed_parts.get('includes', ''),
            ] if part
        )

        fixed_css_block = str(fixed_parts.get('css_links', '') or '')
        if fixed_css_block and '<head' in patched.lower():
            missing_css_lines = []
            for css_line in [line.strip() for line in fixed_css_block.splitlines() if line.strip()]:
                src_match = re.search(r'href=["\']([^"\']+)["\']', css_line, re.IGNORECASE)
                if src_match and src_match.group(1).lower() in patched.lower():
                    continue
                if css_line.lower() in patched.lower():
                    continue
                missing_css_lines.append(css_line)
            if missing_css_lines:
                css_injection = '\n'.join(missing_css_lines)
                patched = re.sub(r'<head[^>]*>', lambda m: m.group(0) + '\n' + css_injection, patched, count=1, flags=re.IGNORECASE)
                self._record_fallback_usage(
                    'company_template',
                    'auto_attach_css_links',
                    chars_added=len(css_injection)
                )

        fixed_footer_scripts = str(fixed_parts.get('footer_scripts', '') or '')
        if fixed_footer_scripts:
            missing_script_lines = []
            for script_line in [line.strip() for line in fixed_footer_scripts.splitlines() if line.strip()]:
                src_match = re.search(r'src=["\']([^"\']+)["\']', script_line, re.IGNORECASE)
                if src_match and src_match.group(1).lower() in patched.lower():
                    continue
                if script_line.lower() in patched.lower():
                    continue
                missing_script_lines.append(script_line)
            if missing_script_lines:
                script_injection = '\n'.join(missing_script_lines)
                patched, added = self._insert_before_body_close(patched, script_injection)
                if added:
                    self._record_fallback_usage(
                        'company_template',
                        'auto_attach_footer_scripts',
                        chars_added=added
                    )

        config_include = self._extract_include_line(include_block, 'config.inc.php') or '<?php include("include/config.inc.php"); ?>'
        topmenu_include = self._extract_include_line(include_block, 'topmenu.php') or '<?php include("include/topmenu.php"); ?>'
        sidemenu_include = (
            self._extract_include_line(include_block, 'sidemenu.php')
            or self._extract_include_line(include_block, 'rightmenu.php')
            or '<?php include("include/sidemenu.php"); ?>'
        )
        formheader_include = self._extract_include_line(include_block, 'formheader.php') or '<?php include("include/formheader.php"); ?>'
        footer_include = self._extract_include_line(include_block, 'footer.php') or '<?php include("include/footer.php"); ?>'

        lower_code = patched.lower()
        if 'config.inc.php' not in lower_code:
            php_tag_pos = patched.find('<?php')
            if php_tag_pos != -1:
                session_match = re.search(r'@?session_start\s*\(\s*\)\s*;', patched, re.IGNORECASE)
                if session_match:
                    insertion_point = session_match.end()
                    patched = patched[:insertion_point] + '\n' + config_include + patched[insertion_point:]
                else:
                    line_end = patched.find('\n', php_tag_pos)
                    if line_end != -1:
                        patched = patched[:line_end] + '\n' + config_include + patched[line_end:]
                    else:
                        patched = patched + '\n' + config_include
                self._record_fallback_usage(
                    'company_template',
                    'auto_attach_config_include',
                    chars_added=len(config_include)
                )

        if 'topmenu.php' not in patched.lower():
            patched, added = self._insert_after_body_tag(patched, topmenu_include)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_topmenu', chars_added=added)
        if ('sidemenu.php' not in patched.lower()) and ('rightmenu.php' not in patched.lower()):
            patched, added = self._insert_after_body_tag(patched, sidemenu_include)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_sidebar', chars_added=added)
        if 'formheader.php' not in patched.lower():
            patched, added = self._insert_after_body_tag(patched, formheader_include)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_formheader', chars_added=added)
        if 'include/footer.php' not in patched.lower():
            patched, added = self._insert_before_body_close(patched, footer_include)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_footer', chars_added=added)

        patched, added = self._ensure_form_layout_structure(patched)
        if added:
            self._record_fallback_usage('company_template', 'auto_attach_form_layout', chars_added=added)

        patched, added = self._ensure_page_container(patched)
        if added:
            self._record_fallback_usage('company_template', 'auto_attach_page_container', chars_added=added)

        lower_code = patched.lower()
        has_existing_save_control = bool(
            'id="btnsave"' in lower_code
            or 'name="btnsave"' in lower_code
            or re.search(r'<button[^>]*type=["\']submit["\']', patched, re.IGNORECASE)
            or re.search(r'onclick\s*=\s*["\']\s*btnsave_click\s*\(', patched, re.IGNORECASE)
        )
        if not has_existing_save_control:
            button_bar = (
                '<div class="form-group">\n'
                '  <div class="col-md-12" align="center">\n'
                '    <button type="button" class="btn btn-primary" id="btnSave" name="btnSave" onclick="btnsave_click()">Save</button>\n'
                '    <button type="button" class="btn btn-info" id="btnEdit">Edit</button>\n'
                '    <button type="button" class="btn btn-danger" id="btnDelete">Delete</button>\n'
                '    <button type="button" class="btn btn-default" id="btnPrint">Print</button>\n'
                '  </div>\n'
                '</div>'
            )
            form_close_match = re.search(r'</form>', patched, re.IGNORECASE)
            if form_close_match:
                patched = patched[:form_close_match.start()] + button_bar + '\n' + patched[form_close_match.start():]
                self._record_fallback_usage('company_template', 'auto_attach_action_buttons', chars_added=len(button_bar))

        user_requirements = self._detect_user_requirements(user_request or '')
        requested_grid = self._extract_requested_grid(user_request or '')
        wants_grid = bool(requested_grid.get('has_grid') or user_requirements.get('wants_grid', False))
        if wants_grid and '<table' not in patched.lower():
            grid_markup = (
                '<div class="form-group">\n'
                '  <div class="col-md-12">\n'
                '    <table class="table table-striped table-bordered" id="tblDetailGrid">\n'
                '      <thead><tr><th>Code</th><th>Description</th><th>Action</th></tr></thead>\n'
                '      <tbody></tbody>\n'
                '    </table>\n'
                '  </div>\n'
                '</div>'
            )
            form_close_match = re.search(r'</form>', patched, re.IGNORECASE)
            if form_close_match:
                patched = patched[:form_close_match.start()] + grid_markup + '\n' + patched[form_close_match.start():]
                self._record_fallback_usage('company_template', 'auto_attach_grid_markup', chars_added=len(grid_markup))

        if 'id="companycommonmodal"' not in patched.lower():
            modal_markup = (
                '<div class="modal fade" id="companyCommonModal" tabindex="-1" role="dialog" aria-hidden="true">\n'
                '  <div class="modal-dialog" role="document"><div class="modal-content">\n'
                '    <div class="modal-header"><h4 class="modal-title">Details</h4></div>\n'
                '    <div class="modal-body"></div>\n'
                '    <div class="modal-footer"><button type="button" class="btn btn-default" data-dismiss="modal">Close</button></div>\n'
                '  </div></div>\n'
                '</div>'
            )
            patched, added = self._insert_before_body_close(patched, modal_markup)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_modal_shell', chars_added=added)

        has_delegated_events = bool(
            re.search(r'\.on\s*\(\s*[\'"][^\'"]+[\'"]\s*,\s*[\'"][^\'"]+[\'"]', patched, re.IGNORECASE)
        )
        has_common_init = '__companySharedInit'.lower() in patched.lower()
        has_select2_init = '.select2(' in patched.lower()
        has_formvalidation_init = '.formvalidation(' in patched.lower() or 'formvalidation.formvalidation(' in patched.lower()
        if not (has_common_init and has_delegated_events and has_select2_init and has_formvalidation_init):
            shared_script = (
                '<script>\n'
                '(function(window){\n'
                '  if (!window || window.__companySharedInit) { return; }\n'
                '  window.__companySharedInit = true;\n'
                '  var $ = window.jQuery;\n'
                '  if (!$) { return; }\n'
                '  $(document)\n'
                "    .off('click.companyAjaxNav')\n"
                "    .on('click.companyAjaxNav', '[data-ajax-nav], a.ajax-nav', function(e){\n"
                '      var url = $(this).attr("href") || $(this).data("ajax-nav");\n'
                '      if (!url || url === "#" || /^javascript:/i.test(url)) { return; }\n'
                '      e.preventDefault();\n'
                '      $.get(url).done(function(html){\n'
                '        var $target = $("#ajax-content");\n'
                '        if ($target.length) { $target.html(html); }\n'
                '      });\n'
                '    });\n'
                '  if ($.fn && $.fn.select2) {\n'
                '    $("select[data-plugin=\'select2\'], select.select2").each(function(){\n'
                '      var $el = $(this);\n'
                '      if (!$el.data("select2")) { $el.select2({ width: "100%" }); }\n'
                '    });\n'
                '  }\n'
                '  var $form = $("#frm");\n'
                '  if ($form.length && $.fn && $.fn.formValidation && !$form.data("fv")) {\n'
                '    $form.formValidation({ framework: "bootstrap" });\n'
                '  }\n'
                '})(window);\n'
                '</script>'
            )
            patched, added = self._insert_before_body_close(patched, shared_script)
            if added:
                self._record_fallback_usage('company_template', 'auto_attach_shared_init_script', chars_added=added)

        patched, added = self._inject_required_ajax_handlers(patched, user_request=user_request)
        if added:
            self._record_fallback_usage('company_template', 'auto_attach_required_ajax_handlers', chars_added=added)

        patched, added = self._inject_required_grid_flow(patched, user_request=user_request)
        if added:
            self._record_fallback_usage('company_template', 'auto_attach_required_grid_flow', chars_added=added)

        patched, added = self._inject_required_predelete_and_dbrecord_handlers(
            patched,
            user_request=user_request
        )
        if added:
            self._record_fallback_usage(
                'company_template',
                'auto_attach_required_predelete_dbrecord_handlers',
                chars_added=added
            )

        hardened_code, hardening_added = self._apply_production_hardening(
            patched,
            user_request=user_request
        )
        if hardened_code != patched:
            patched = hardened_code
            self._record_fallback_usage(
                'company_template',
                'auto_apply_production_hardening',
                chars_added=max(0, hardening_added)
            )

        return patched
    
    def _extract_fixed_parts_from_example(self, company_example: str, example_file_path: str = "") -> Dict[str, str]:
        """
        Extract FIXED parts from the retrieved company example.
        These parts are the same across ALL company forms.
        
        If the example is trimmed (common for large files), reads the FULL file from disk.
        
        Returns dict with:
        - css_links: All CSS link tags
        - footer_scripts: All footer script tags
        - html_head: Complete <head> section
        - body_start: From <body> to <form>
        - body_end: From </form> to </html>
        - includes: PHP include statements
        """
        fixed = {
            'css_links': '',
            'footer_scripts': '',
            'html_head': '',
            'body_start': '',
            'body_end': '',
            'includes': '',
            'php_bootstrap_includes': '',
            'layout_includes': '',
            'source_content': '',
        }
        
        content_to_parse = company_example
        
        # âœ… PLAN A FIX: ALWAYS read the FULL file from disk for FIXED parts extraction
        # The company_example passed here is trimmed (even with 40KB limit)
        # We need the full file to extract HTML head, body start, etc.
        if example_file_path and os.path.exists(example_file_path):
            try:
                with open(example_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    full_content = f.read()
                content_to_parse = full_content
                logger.info(
                    f"ðŸ“– Reading FULL file from disk for fixed-part extraction: "
                    f"{os.path.basename(example_file_path)} ({len(full_content):,} chars)"
                )
            except Exception as e:
                logger.warning(f"âš ï¸ Could not read full file {example_file_path}: {e}")
        
        # âœ… FALLBACK: If no file path provided, try to find it via glob
        if not example_file_path and self._template and self._template.codebase_dir:
            import glob
            all_frm_files = glob.glob(os.path.join(self._template.codebase_dir, '**', 'frm*.php'), recursive=True)
            if all_frm_files:
                # Use the first form as template source
                try:
                    with open(all_frm_files[0], 'r', encoding='utf-8', errors='ignore') as f:
                        full_content = f.read()
                    content_to_parse = full_content
                    logger.info(f"ðŸ“– Using first frm*.php as template source: {os.path.basename(all_frm_files[0])} ({len(full_content):,} chars)")
                except Exception as e:
                    logger.warning(f"âš ï¸ Could not read template file: {e}")
        
        if not content_to_parse:
            fixed['source_content'] = company_example or ""
            return fixed

        fixed['source_content'] = content_to_parse
        
        # Extract CSS links
        css_matches = re.findall(r'(<link rel="stylesheet"[^>]+>)', content_to_parse)
        if css_matches:
            fixed['css_links'] = '\n'.join(css_matches)
        
        # Extract footer scripts
        script_matches = re.findall(r'(<script src="[^"]+"></script>)', content_to_parse)
        if script_matches:
            fixed['footer_scripts'] = '\n'.join(script_matches)
        
        # Extract HTML head
        head_match = re.search(r'(<head>.*?</head>)', content_to_parse, re.DOTALL)
        if head_match:
            fixed['html_head'] = head_match.group(1)
        
        # Extract body start (from <body> to <form>)
        body_match = re.search(r'(<body[^>]*>.*?<form[^>]*>)', content_to_parse, re.DOTALL)
        if body_match:
            fixed['body_start'] = body_match.group(1)
        
        # Extract body end (from </form> to </html>)
        body_end_match = re.search(r'(</form>.*?</html>)', content_to_parse, re.DOTALL)
        if body_end_match:
            fixed['body_end'] = body_end_match.group(1)
        
        # Extract PHP includes
        include_matches = re.findall(r'(include\s*\([^)]+\)\s*;)', content_to_parse)
        if include_matches:
            normalized_includes = [self._normalize_include_snippet(line) for line in include_matches if str(line).strip()]
            fixed['includes'] = '\n'.join(normalized_includes)
            php_bootstrap = []
            layout_includes = []
            for include_line in normalized_includes:
                include_lower = include_line.lower()
                if 'config.inc.php' in include_lower:
                    php_bootstrap.append(include_line)
                elif any(token in include_lower for token in ['topmenu.php', 'sidemenu.php', 'rightmenu.php', 'formheader.php', 'footer.php']):
                    layout_includes.append(include_line)
            fixed['php_bootstrap_includes'] = '\n'.join(php_bootstrap)
            fixed['layout_includes'] = '\n'.join(layout_includes)
        
        logger.info(f"ðŸ“¦ Extracted FIXED parts from company example:")
        logger.info(f"   Source: {os.path.basename(example_file_path) if example_file_path else 'trimmed example'}")
        logger.info(f"   CSS links: {len(fixed['css_links'])} chars ({len(css_matches) if css_matches else 0} files)")
        logger.info(f"   Footer scripts: {len(fixed['footer_scripts'])} chars ({len(script_matches) if script_matches else 0} files)")
        logger.info(f"   HTML head: {len(fixed['html_head'])} chars")
        logger.info(f"   Body start: {len(fixed['body_start'])} chars")
        logger.info(f"   Body end: {len(fixed['body_end'])} chars")
        
        return fixed
    
    def _build_system_instruction(self, company_example_size: int = 50000) -> str:
        """
        âœ… STEP 4 PHASE A - FIX P-2: Build DYNAMIC system instruction with MINIMUM 900 LINES requirement
        
        Calculates minimum and target based on actual company file size:
        - Minimum: 80% of company example
        - Target: 90% of company example
        - Lines: Minimum 900 lines (company files are 900-1000 lines)
        
        Args:
            company_example_size: Size of company example file in characters
            
        Returns:
            System instruction string with dynamic thresholds
        """
        # Calculate dynamic thresholds (80% minimum, 90% target)
        min_chars = int(company_example_size * 0.8)
        target_chars = int(company_example_size * 0.9)
        
        # Store for later use
        self.min_chars = min_chars
        self.target_chars = target_chars
        
        # Calculate section sizes (proportional breakdown)
        php_section = int(min_chars * 0.375)  # 37.5% for PHP logic
        html_section = int(min_chars * 0.375)  # 37.5% for HTML
        js_section = int(min_chars * 0.25)  # 25% for JavaScript + Footer
        
        # âœ… P-2 FIX: Calculate minimum lines (company files are ~900-1000 lines)
        min_lines = max(900, int(company_example_size / 50))  # ~50 chars per line average
        target_lines = max(950, int(target_chars / 50))
        
        return f"""ðŸ”´ðŸ”´ðŸ”´ ABSOLUTE CRITICAL REQUIREMENT ðŸ”´ðŸ”´ðŸ”´

YOU WILL BE PENALIZED IF OUTPUT < {min_chars:,} CHARACTERS OR < {min_lines} LINES!

ðŸ“Š REFERENCE METRICS:
- Company example file: {company_example_size:,} characters ({company_example_size/1000:.1f} KB)
- Your ABSOLUTE MINIMUM: {min_chars:,} characters ({min_chars/1000:.1f} KB) [80% of company]
- Your TARGET: {target_chars:,} characters ({target_chars/1000:.1f} KB) [90% of company]
- âœ… P-2 FIX: MINIMUM {min_lines} LINES (company files are 900-1000 lines)
- ANYTHING LESS THAN {min_chars:,} CHARS OR {min_lines} LINES = AUTOMATIC FAILURE!

âŒ STRICTLY FORBIDDEN:
- Do NOT write "// ... rest of code" or "// similar to above" or "// ... more fields"
- Do NOT skip ANY sections (PHP, HTML, CSS, JavaScript, Footer)
- Do NOT abbreviate or summarize ANY part
- Do NOT truncate output early
- Do NOT use placeholders like "// Add remaining fields"
- Do NOT write "<!-- Similar structure for other fields -->"

âœ… MANDATORY COMPLETE SECTIONS:
1. PHP LOGIC ({php_section:,}+ chars, ~{int(php_section/50)} lines):
   - ALL AJAX handlers (GetMaxID, GetCOSTCENTER, cascading dropdowns)
   - COMPLETE Delete logic with pre-checks
   - COMPLETE Update logic with all field mappings
   - COMPLETE Save logic with all field mappings
   - Chart of Accounts integration (INSERT, UPDATE, DELETE)
   - Transaction management (funStartTran, funEndTran)
   - Logging (fun_log)

2. HTML STRUCTURE ({html_section:,}+ chars, ~{int(html_section/50)} lines):
   - COMPLETE <head> with ALL CSS links (20+ links)
   - COMPLETE <body> with includes (topmenu, sidemenu, formheader)
   - COMPLETE <form> with ALL fields (write EVERY field explicitly)
   - COMPLETE buttons (Save, Back, Reset)
   - COMPLETE hidden inputs

3. JAVASCRIPT ({js_section:,}+ chars, ~{int(js_section/50)} lines):
   - COMPLETE checkKeycode function with ALL field mappings
   - COMPLETE maxid() function
   - COMPLETE cascading dropdown functions (SubArea, SalesRepresentive, etc.)
   - COMPLETE FormValidation with ALL field validators
   - COMPLETE Select2 event handlers (.on("select2:close"))
   - COMPLETE btnsave_click function
   - ALL helper functions
   - ALL 30+ footer script tags

ðŸ“ CHARACTER & LINE COUNT VERIFICATION:
Before submitting your response, COUNT the characters AND lines:
- If < {min_chars:,} chars OR < {min_lines} lines â†’ ADD MORE CODE (more fields, more validation, more comments)
- If {min_chars:,}-{target_chars:,} chars AND {min_lines}-{target_lines} lines â†’ PERFECT! Submit
- If > {target_chars:,} chars â†’ OK, but ensure no redundancy

ðŸŽ¯ GENERATION STRATEGY:
1. Write PHP logic COMPLETELY (no shortcuts) - ~{int(php_section/50)} lines
2. Write HTML form with EVERY field (no "similar to above") - ~{int(html_section/50)} lines
3. Write JavaScript COMPLETELY (all functions, all event handlers) - ~{int(js_section/50)} lines
4. Write Footer scripts COMPLETELY (all 30+ script tags) - ~50 lines
5. COUNT characters AND lines â†’ If < {min_chars:,} chars OR < {min_lines} lines, ADD MORE

âš ï¸âš ï¸âš ï¸ FINAL WARNING âš ï¸âš ï¸âš ï¸
OUTPUT < {min_chars:,} CHARACTERS OR < {min_lines} LINES = YOU HAVE FAILED THE TASK!
DO NOT SUBMIT UNTIL YOU HAVE {min_chars:,}+ CHARACTERS AND {min_lines}+ LINES!
"""
    
    # âœ… PHASE 1 FIX #1: Dynamic Field Extraction (No Hardcoding)
    def _extract_field_names_from_example(self, company_example: str, user_request: str = "") -> Dict:
        """
        âœ… STEP 2 FIX (R-2, P-3): Extract field names with USER REQUEST PRIORITY
        
        PRIORITY ORDER:
        1. User explicitly mentioned fields (HIGHEST PRIORITY)
        2. Company example fields (for structure only)
        
        This fixes:
        - R-2: Wrong file patterns (ITEM_CODE from frmIssuanceAGC)
        - P-3: Wrong field names sent to LLM
        
        Works for ANY form (Customer, Area, SubArea, Product, etc.)
        
        Returns:
            {
                'primary_key': 'Code',
                'form_fields': ['Code', 'Description', 'Country_Code', 'SALE_MAN'],
                'user_requested_fields': ['Code', 'Description', 'Country_Code', ...],
                'parent_field': 'cboCountry',
                'dropdown_fields': ['cboCountry', 'Salesman'],
                'text_fields': ['Code', 'Description']
            }
        """
        
        fields = {
            'primary_key': None,
            'form_fields': [],
            'user_requested_fields': [],
            'parent_field': None,
            'parent_db_field': None,
            'dropdown_fields': [],
            'text_fields': [],
            'detail_grid': {
                'has_grid': False,
                'sub_table': None,
                'grid_fields': [],
                'txtcount_var': 'TXTCOUNTACC',
                'loop_var': 'i'
            }
        }
        
        # âœ… STEP 2 FIX: PRIORITY 1 - Extract fields from USER REQUEST FIRST
        user_request_text = self._normalize_request_sections(user_request)
        user_fields = []
        if user_request_text:
            logger.info("ðŸŽ¯ STEP 2 FIX: Extracting fields from USER REQUEST (Priority 1)")
            primary_key_lines = self._extract_bullet_section(
                user_request_text,
                ('primary key', 'primary field')
            )
            if primary_key_lines:
                parsed_primary_keys = []
                for line in primary_key_lines:
                    if not self._line_looks_like_field_definition(line):
                        continue
                    parsed_primary_keys.extend(self._extract_field_names_from_line(line))
                parsed_primary_keys = self._unique_preserve_order(parsed_primary_keys)
                if parsed_primary_keys:
                    fields['primary_key'] = parsed_primary_keys[0]
                    logger.info(f"   ✅ Detected primary key from USER REQUEST: {fields['primary_key']}")

            requested_grid = self._extract_requested_grid(user_request_text)
            if requested_grid.get('has_grid') or requested_grid.get('explicit_opt_out'):
                fields['detail_grid'] = requested_grid
            if requested_grid.get('has_grid'):
                logger.info(
                    f"   âœ… Detected detail grid from USER REQUEST: "
                    f"{requested_grid.get('sub_table') or 'sub-table not named'} "
                    f"with {len(requested_grid.get('grid_fields', []))} fields"
                )
            elif requested_grid.get('explicit_opt_out'):
                logger.info("   ⚪ Detected detail grid opt-out from USER REQUEST")

            master_field_lines = self._extract_bullet_section(
                user_request_text,
                ('master fields', 'form fields', 'fields', 'master field', 'form field')
            )
            if master_field_lines:
                extracted_master_fields = []
                for line in master_field_lines:
                    if not self._line_looks_like_field_definition(line):
                        continue
                    extracted_master_fields.extend(self._extract_field_names_from_line(line))

                extracted_master_fields = self._unique_preserve_order(extracted_master_fields)
                if extracted_master_fields:
                    user_fields = extracted_master_fields
                    logger.info(
                        f"   âœ… Found {len(user_fields)} fields from structured section headings: "
                        f"{user_fields[:12]}{'...' if len(user_fields) > 12 else ''}"
                    )
            
            # âœ… PHASE B FIX: Pattern for numbered list format
            # "1. Code (CUST_CODE) - Primary Key"
            # "2. Main_Area - Dropdown from tblarea"
            numbered_matches = []
            for request_line in user_request_text.splitlines():
                if not re.match(r'^\s*\d+[.)]\s+', request_line.strip()):
                    continue
                if not self._line_looks_like_field_definition(request_line):
                    continue
                numbered_matches.extend(self._extract_field_names_from_line(request_line))
            numbered_matches = self._unique_preserve_order(numbered_matches)
            if numbered_matches and len(numbered_matches) >= 2:
                user_fields = numbered_matches
                logger.info(f"   âœ… Found {len(user_fields)} fields from numbered list: {user_fields[:10]}...")
            
            # Pattern 1: "Include ALL X fields with exact naming: field1, field2, field3"
            if not user_fields:
                exact_naming_pattern = r'[Ii]nclude\s+ALL\s+\d+\s+fields\s+with\s+exact\s+naming:\s*([^\n]+)'
                match = re.search(exact_naming_pattern, user_request_text)
                if match:
                    field_text = match.group(1)
                    user_fields = [f.strip() for f in re.split(r'[,\n]', field_text) if f.strip()]
                    logger.info(f"   âœ… Found {len(user_fields)} fields with exact naming: {user_fields}")

            # Pattern 2: "Fields:" followed by a bullet list
            if not user_fields:
                bullet_block_pattern = r'[Ff]ields?\s*:\s*((?:\s*[-*]\s*[^\n]+(?:\n|$))+)' 
                match = re.search(bullet_block_pattern, user_request_text, re.MULTILINE)
                if match:
                    field_lines = []
                    for line in match.group(1).splitlines():
                        if not self._line_looks_like_field_definition(line):
                            continue
                        field_lines.extend(self._extract_field_names_from_line(line))
                    if field_lines:
                        user_fields = self._unique_preserve_order(field_lines)
                        logger.info(f"   âœ… Found {len(user_fields)} fields from bullet list: {user_fields}")
            
            # Pattern 3: "Fields: field1, field2, field3"
            if not user_fields:
                field_list_patterns = [
                    r'[Ff]ields?:\s*([^.\n]+)',
                    r'with fields?:\s*([^.\n]+)',
                    r'including:\s*([^.\n]+)',
                    r'columns?:\s*([^.\n]+)',
                    r'attributes?:\s*([^.\n]+)'
                ]
                
                for pattern in field_list_patterns:
                    match = re.search(pattern, user_request_text)
                    if match:
                        field_text = match.group(1)
                        parsed_fields = []

                        # Split by comma, semicolon, or 'and' then parse identifiers safely.
                        for raw_piece in re.split(r'[,;]|\s+and\s+', field_text):
                            if not self._line_looks_like_field_definition(raw_piece):
                                continue
                            parsed_fields.extend(
                                self._extract_field_names_from_line(raw_piece.strip().strip('"\'')) 
                            )

                        parsed_fields = self._unique_preserve_order(parsed_fields)
                        # Guardrail: avoid treating descriptive fragments as a valid field list.
                        if len(parsed_fields) >= 2:
                            user_fields = parsed_fields
                            logger.info(f"   âœ… Found {len(user_fields)} fields from pattern: {user_fields}")
                            break
            
            # Store user requested fields
            if user_fields:
                normalized_user_fields = self._normalize_user_requested_fields(user_fields)
                if not normalized_user_fields:
                    recovered_fields = []
                    for raw_field in user_fields:
                        recovered_fields.extend(self._extract_field_names_from_line(str(raw_field)))
                    normalized_user_fields = self._normalize_user_requested_fields(recovered_fields)

                if normalized_user_fields:
                    fields['user_requested_fields'] = normalized_user_fields
                    # âœ… CRITICAL: Use user fields as PRIMARY source
                    fields['form_fields'] = normalized_user_fields.copy()
                    logger.info(
                        f"âœ… STEP 2 FIX: Using {len(normalized_user_fields)} USER-SPECIFIED fields as primary source"
                    )
                else:
                    logger.warning(
                        "âš ï¸ Could not reliably parse structured user field list; "
                        "falling back to company example field extraction."
                    )
        
        # âœ… STEP 2 FIX: PRIORITY 2 - Extract from company example ONLY if user didn't specify
        if not fields['form_fields'] and company_example:
            # 🔥 CRITICAL CHECK: Block fallback if user explicitly said "NO EXTRA FIELDS"
            user_request_lower = (user_request or '').lower()
            has_strict_requirement = (
                'no extra field' in user_request_lower or 
                'use exact names' in user_request_lower or
                'exact names' in user_request_lower
            )
            
            if has_strict_requirement:
                logger.error("🚨 CRITICAL: User explicitly requested NO EXTRA FIELDS but field extraction failed!")
                logger.error("🚨 BLOCKING fallback to prevent wrong field injection from example")
                logger.error("🚨 This indicates a PARSER BUG in field extraction logic")
                logger.error("🚨 Expected format: '- FieldName | DB: TYPE | Input: type | Required: Yes'")
                # Skip extraction - leave fields empty to trigger validation error
            else:
                logger.info("âš ï¸ No user-specified fields, extracting from company example (Priority 2)")
                
                # âœ… ISSUE #5 FIX: Extract from MULTIPLE sources for complete field list
                all_fields = set()  # Use set to avoid duplicates
            
                # SOURCE 1: Extract from $columns array (most reliable for DB fields)
                columns_pattern = r'\$columns\[["\']([^"\']+)["\']\]'
                columns = re.findall(columns_pattern, company_example)
                all_fields.update(columns)
                logger.info(f"ðŸ” Extracted {len(columns)} fields from $columns array")
            
                # SOURCE 2: Extract from <input> tags (catches fields not in $columns)
                input_pattern = r'<input[^>]*name=["\']([^"\']+)["\']'
                inputs = re.findall(input_pattern, company_example)
                all_fields.update(inputs)
                logger.info(f"ðŸ” Extracted {len(inputs)} fields from <input> tags")
            
                # SOURCE 3: Extract from <select> tags (dropdown fields)
                select_pattern = r'<select[^>]*name=["\']([^"\']+)["\']'
                selects = re.findall(select_pattern, company_example)
                all_fields.update(selects)
                logger.info(f"ðŸ” Extracted {len(selects)} fields from <select> tags")
            
                # SOURCE 4: Extract from <textarea> tags (text area fields)
                textarea_pattern = r'<textarea[^>]*name=["\']([^"\']+)["\']'
                textareas = re.findall(textarea_pattern, company_example)
                all_fields.update(textareas)
                logger.info(f"ðŸ” Extracted {len(textareas)} fields from <textarea> tags")
            
                # SOURCE 5: Extract from $_REQUEST references (catches all form submissions)
                request_pattern = r'\$_REQUEST\[["\']([^"\']+)["\']\]'
                requests = re.findall(request_pattern, company_example)
                # Filter out common non-field requests
                non_field_requests = {
                str(token).strip().lower()
                for token in get_csv_setting(
                    'CODEGEN_NON_FIELD_REQUEST_KEYS',
                    'CODEGEN_NON_FIELD_REQUEST_KEYS',
                    default=[
                        'action', 'major', 'DeleteCase', 'CTRL_HID_VALUE', 'txtmode',
                        'Area', 'bnkId', 'bnkSubArea', 'Action', 'SelectArea'
                    ]
                )
                }
                request_fields = [r for r in requests if str(r).strip().lower() not in non_field_requests]
                all_fields.update(request_fields)
                logger.info(f"ðŸ” Extracted {len(request_fields)} fields from $_REQUEST references")
            
            logger.info(f"âœ… Total unique fields found: {len(all_fields)}")
            
            # Remove duplicates and system fields
            system_fields = {
                str(token).strip().lower()
                for token in get_csv_setting(
                    'CODEGEN_SYSTEM_FIELD_KEYS',
                    'CODEGEN_SYSTEM_FIELD_KEYS',
                    default=[
                        'Comp_Code', 'UserId', 'Login_ID', 'CreationDateTime', 'Created_Date', 'Updated_Date',
                        'User_ID', 'UNIT_CODE', 'Unit_Code', 'action', 'major', 'DeleteCase', 'CTRL_HID_VALUE',
                        'txtmode', 'Area', 'bnkId', 'bnkSubArea', 'Action', 'SelectArea'
                    ]
                )
            }
            form_fields = [f for f in all_fields if str(f).strip().lower() not in system_fields]
            
            # Sort fields to maintain consistent order
            form_fields = sorted(form_fields)
            fields['form_fields'] = form_fields
            fields['dropdown_fields'] = list(set(selects))
            fields['text_fields'] = list(set(inputs))
        
        # âœ… STEP 2 FIX: Extract parent field from USER REQUEST first
        if user_request_text:
            # Pattern: "Parent dropdown (Country_Code from tblarea)"
            parent_pattern = r'[Pp]arent\s+dropdown\s*\(([^)]+)\s+from\s+(\w+)\)'
            parent_match = re.search(parent_pattern, user_request_text)
            if parent_match:
                parent_field_name = parent_match.group(1).strip()
                parent_table = parent_match.group(2).strip()
                fields['parent_field'] = parent_field_name
                fields['parent_db_field'] = parent_field_name
                logger.info(f"âœ… STEP 2 FIX: Detected parent field from USER REQUEST: {parent_field_name} from {parent_table}")
        
        # Fallback: Detect parent field from company example
        if not fields['parent_field'] and company_example:
            parent_pattern = r'<select[^>]*name=["\']([^"\']+)["\'][^>]*onChange[^>]*maxid'
            parent_match = re.search(parent_pattern, company_example, re.IGNORECASE)
            if parent_match:
                fields['parent_field'] = parent_match.group(1)
                logger.info(f"ðŸ” Detected parent dropdown field from example: {fields['parent_field']}")
            
            # Detect parent DB field from WHERE clause in GetMaxID
            parent_db_pattern = r'WHERE\s+(\w+)\s*=.*\$_REQUEST\[["\']Select\w+["\']'
            parent_db_match = re.search(parent_db_pattern, company_example)
            if parent_db_match:
                fields['parent_db_field'] = parent_db_match.group(1)
                logger.info(f"ðŸ” Detected parent DB field from example: {fields['parent_db_field']}")

        # Preserve request-declared input semantics (select/text/etc.) for downstream generation.
        if user_request_text and fields['form_fields']:
            input_type_map: Dict[str, str] = {}
            for item in self._extract_field_contract_from_request(user_request_text):
                field_name = str(item.get('name') or '').strip()
                if not field_name:
                    continue
                input_type = str(item.get('input_type') or '').strip().lower()
                if input_type:
                    input_type_map[field_name.lower()] = input_type

            if self._should_parse_request_schema(user_request_text):
                parsed_schema = self._parse_request_schema_cached(user_request_text)
                for schema_field in (parsed_schema.get('fields') or []):
                    schema_name = str(schema_field.get('name') or '').strip()
                    if not schema_name:
                        continue
                    schema_input = str(schema_field.get('input_type') or '').strip().lower()
                    if schema_input and schema_name.lower() not in input_type_map:
                        input_type_map[schema_name.lower()] = schema_input

            dropdown_fields = list(fields.get('dropdown_fields') or [])
            text_fields = list(fields.get('text_fields') or [])
            for form_field in fields['form_fields']:
                field_key = str(form_field or '').strip().lower()
                if not field_key:
                    continue
                input_type = input_type_map.get(field_key, '')
                if not input_type:
                    continue
                if any(token in input_type for token in ('select', 'dropdown', 'combo')):
                    dropdown_fields.append(form_field)
                else:
                    text_fields.append(form_field)

            fields['dropdown_fields'] = self._unique_preserve_order(dropdown_fields)
            fields['text_fields'] = self._unique_preserve_order(text_fields)
            if not fields['text_fields'] and fields['form_fields']:
                dropdown_lookup = {str(name).strip().lower() for name in fields['dropdown_fields']}
                fallback_text_fields = [
                    field_name
                    for field_name in fields['form_fields']
                    if str(field_name).strip().lower() not in dropdown_lookup
                ]
                if fallback_text_fields:
                    fields['text_fields'] = self._unique_preserve_order(fallback_text_fields)
                else:
                    fields['text_fields'] = self._unique_preserve_order(fields['form_fields'])
        
        # Primary key detection (usually 'Code' or ends with '_CODE')
        for field in fields['form_fields']:
            field_lower = str(field or '').lower()
            if (
                field == 'Code' or
                field_lower == 'id' or
                field_lower.endswith('_code') or
                field_lower.endswith('_id')
            ):
                fields['primary_key'] = field
                break
        
        logger.info(f"âœ… STEP 2 FIX: Final extracted fields:")
        logger.info(f"   Primary key: {fields['primary_key']}")
        logger.info(f"   Form fields: {len(fields['form_fields'])} fields - {fields['form_fields']}")
        logger.info(f"   User requested: {fields['user_requested_fields']} ({len(fields['user_requested_fields'])} fields)")
        logger.info(f"   Parent field: {fields['parent_field']}")
        logger.info(f"   Parent DB field: {fields['parent_db_field']}")
        logger.info(f"   Dropdowns: {len(fields['dropdown_fields'])} fields")
        logger.info(f"   Text inputs: {len(fields['text_fields'])} fields")
        
        return fields
    
    # âœ… PHASE 1 FIX #2: Hierarchical Pattern Detection (No Hardcoding)
    def _detect_hierarchical_pattern(self, company_example: str, user_request: str = "") -> Dict:
        """
        âœ… STEP 2 FIX (R-2, P-3): Detect hierarchical pattern with USER REQUEST PRIORITY
        
        PRIORITY ORDER:
        1. User explicitly mentioned AJAX parameters (HIGHEST PRIORITY)
        2. Company example patterns (for structure only)
        
        This fixes:
        - R-2: Wrong AJAX param (bnkId from frmIssuanceAGC)
        - P-3: Wrong parameter names sent to LLM
        
        Works for ANY parent-child relationship
        
        Returns:
            {
                'is_hierarchical': True,
                'parent_field': 'Country_Code',
                'parent_request_param': 'SelectArea',
                'parent_js_field_id': 'cboCountry',
                'separator': '-',
                'code_length': 2
            }
        """
        # Note: re module is imported at module level, no need to import here
        
        pattern = {
            'is_hierarchical': False,
            'parent_field': None,
            'parent_request_param': None,
            'parent_js_field_id': None,
            'separator': '-',
            'code_length': 2  # Default to 2 (most common)
        }
        
        # âœ… STEP 2 FIX: PRIORITY 1 - Extract from USER REQUEST FIRST
        if user_request:
            logger.info("ðŸŽ¯ STEP 2 FIX: Extracting hierarchical pattern from USER REQUEST (Priority 1)")
            
            # Pattern 1: "AJAX GetMaxID MUST receive SelectArea parameter"
            ajax_param_pattern = r'AJAX\s+GetMaxID\s+MUST\s+receive\s+(\w+)\s+parameter'
            ajax_match = re.search(ajax_param_pattern, user_request, re.IGNORECASE)
            if ajax_match:
                pattern['parent_request_param'] = ajax_match.group(1)
                pattern['is_hierarchical'] = True
                logger.info(f"   âœ… Found AJAX parameter from USER REQUEST: {pattern['parent_request_param']}")
            
            # Pattern 2: "Parent dropdown (Country_Code from tblarea)"
            parent_dropdown_pattern = r'[Pp]arent\s+dropdown\s*\(([^)]+)\s+from\s+(\w+)\)'
            parent_match = re.search(parent_dropdown_pattern, user_request)
            if parent_match:
                parent_field_name = parent_match.group(1).strip()
                pattern['parent_field'] = parent_field_name
                pattern['parent_js_field_id'] = f'cbo{parent_field_name.replace("_", "")}'  # Convert Country_Code â†’ cboCountryCode
                pattern['is_hierarchical'] = True
                logger.info(f"   âœ… Found parent dropdown from USER REQUEST: {parent_field_name}")
                logger.info(f"   âœ… Generated JS field ID: {pattern['parent_js_field_id']}")

            # Pattern 2b: "Parent: Area (dropdown)"
            parent_simple_pattern = r'Parent\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*dropdown\s*\)'
            parent_simple_match = re.search(parent_simple_pattern, user_request, re.IGNORECASE)
            if parent_simple_match:
                parent_name = parent_simple_match.group(1).strip()
                pattern['parent_field'] = parent_name
                pattern['parent_request_param'] = parent_name
                pattern['parent_js_field_id'] = parent_name
                pattern['is_hierarchical'] = True
                logger.info(f"   âœ… Found parent from USER REQUEST: {parent_name}")
            
            # Pattern 3: "Hierarchical code pattern: Country_Code + "-" + LPAD(MAX(RIGHT(Code,2))+1, 2, '0')"
            hierarchical_pattern = r'LPAD\(MAX\(RIGHT\(Code,(\d+)\)\)'
            hier_match = re.search(hierarchical_pattern, user_request, re.IGNORECASE)
            if hier_match:
                pattern['code_length'] = int(hier_match.group(1))
                pattern['is_hierarchical'] = True
                logger.info(f"   âœ… Found code length from USER REQUEST: {pattern['code_length']}")
            
            # Pattern 4: Detect separator from user request
            # Example: ACC_CUST + Area + '-0001'  -> '-'
            sep_pattern = r'\+\s*["\']([\-_/])["\']\s*\+'
            sep_match = re.search(sep_pattern, user_request)
            if sep_match:
                pattern['separator'] = sep_match.group(1)
                logger.info(f"   âœ… Found separator from USER REQUEST: '{pattern['separator']}'")
        
        # âœ… STEP 2 FIX: PRIORITY 2 - Extract from company example ONLY if user didn't specify
        if not pattern['is_hierarchical'] and company_example:
            logger.info("âš ï¸ No user-specified hierarchical pattern, extracting from company example (Priority 2)")
            
            # Check for hierarchical code pattern in AJAX handler
            # Pattern: MAX(RIGHT(Code,2)) indicates hierarchical
            right_pattern = r'MAX\(RIGHT\((?:CUST_CODE|Code),(\d+)\)\)'
            right_match = re.search(right_pattern, company_example, re.IGNORECASE)
            
            if right_match:
                pattern['is_hierarchical'] = True
                pattern['code_length'] = int(right_match.group(1))
                logger.info(f"ðŸ” Detected hierarchical code pattern from example (length: {pattern['code_length']})")
            
            # Extract parent field from WHERE clause in PHP
            # Pattern: WHERE Main_Area = '".$_REQUEST['SelectArea']."'
            parent_where_pattern = r'WHERE\s+(\w+)\s*=.*\$_REQUEST\[["\'](\w+)["\']'
            parent_match = re.search(parent_where_pattern, company_example)
            if parent_match:
                pattern['parent_field'] = parent_match.group(1)
                pattern['parent_request_param'] = parent_match.group(2)
                logger.info(f"ðŸ” Detected parent field from example: {pattern['parent_field']} (param: {pattern['parent_request_param']})")
            
            # âœ… ISSUE #2 FIX: Extract JavaScript field ID from maxid() function
            # Pattern: var SelectArea = document.getElementById('Main_Area').value;
            # Search inside maxid() snippet first, then fallback to full example.
            if pattern.get('parent_request_param'):
                parent_param = pattern['parent_request_param']
                
                # First, locate "function maxid" and inspect nearby snippet.
                maxid_func_pattern = r'function\s+maxid\s*\([^)]*\)\s*\{'
                maxid_match = re.search(maxid_func_pattern, company_example, re.IGNORECASE)
                
                if maxid_match:
                    snippet_start = maxid_match.start()
                    snippet_end = min(len(company_example), snippet_start + 1400)
                    maxid_body = company_example[snippet_start:snippet_end]
                    logger.info(f"ðŸ” Found maxid() function body ({len(maxid_body)} chars)")
                    
                    # Pattern variations:
                    # 1. var SelectArea = document.getElementById('Main_Area').value;
                    # 2. var SelectArea= document.getElementById("Main_Area");
                    js_field_pattern = r'var\s+' + re.escape(parent_param) + r'\s*=\s*document\.getElementById\s*\(\s*["\']([\w-]+)["\']\s*\)'
                    js_match = re.search(js_field_pattern, maxid_body, re.IGNORECASE)
                    
                    if js_match:
                        pattern['parent_js_field_id'] = js_match.group(1)
                        logger.info(f"âœ… Detected JS field ID from maxid(): {pattern['parent_js_field_id']}")
                    else:
                        # Fallback: find any getElementById in the maxid snippet.
                        js_field_pattern2 = r'document\.getElementById\s*\(\s*["\']([\w-]+)["\']\s*\)'
                        js_match2 = re.search(js_field_pattern2, maxid_body, re.IGNORECASE)
                        if js_match2:
                            pattern['parent_js_field_id'] = js_match2.group(1)
                            logger.info(f"âœ… Detected JS field ID from maxid snippet: {pattern['parent_js_field_id']}")
                        else:
                            # Fallback: scan full company example for this variable assignment.
                            full_scan_pattern = r'var\s+' + re.escape(parent_param) + r'\s*=\s*document\.getElementById\s*\(\s*["\']([\w-]+)["\']\s*\)'
                            full_scan_match = re.search(full_scan_pattern, company_example, re.IGNORECASE)
                            if full_scan_match:
                                pattern['parent_js_field_id'] = full_scan_match.group(1)
                                logger.info(f"âœ… Detected JS field ID from full example scan: {pattern['parent_js_field_id']}")
                            else:
                                # Last fallback: Use parent_field as JS field ID
                                pattern['parent_js_field_id'] = pattern.get('parent_field', 'Main_Area')
                                logger.warning(f"âš ï¸ Could not extract JS field ID from maxid(), using parent_field: {pattern['parent_js_field_id']}")
                else:
                    # Fallback: scan full company example for variable assignment.
                    full_scan_pattern = r'var\s+' + re.escape(parent_param) + r'\s*=\s*document\.getElementById\s*\(\s*["\']([\w-]+)["\']\s*\)'
                    full_scan_match = re.search(full_scan_pattern, company_example, re.IGNORECASE)
                    if full_scan_match:
                        pattern['parent_js_field_id'] = full_scan_match.group(1)
                        logger.info(f"âœ… maxid() not found but detected JS field from full example: {pattern['parent_js_field_id']}")
                    else:
                        pattern['parent_js_field_id'] = pattern.get('parent_field', 'Main_Area')
                        logger.warning(f"âš ï¸ maxid() function not found, using parent_field as JS field ID: {pattern['parent_js_field_id']}")
            else:
                logger.info(f"âšª No parent_request_param found, skipping JS field extraction")
            
            # Extract separator (usually '-')
            # Pattern: $MAXID = $_REQUEST['SelectArea']."-".$MAXID
            sep_pattern = r'\$_REQUEST\[[^\]]+\]\s*\.\s*["\']([\-_/])["\']\s*\.\s*\$MAXID'
            sep_match = re.search(sep_pattern, company_example)
            if sep_match:
                pattern['separator'] = sep_match.group(1)
                logger.info(f"ðŸ” Detected code separator from example: '{pattern['separator']}'")

        # Safety: hierarchical code must always have a separator
        if pattern['is_hierarchical'] and not pattern.get('separator'):
            pattern['separator'] = '-'
            logger.info("âš™ï¸ Separator missing, defaulting to '-'")
        
        logger.info(f"âœ… STEP 2 FIX: Final hierarchical pattern:")
        logger.info(f"   Is Hierarchical: {pattern['is_hierarchical']}")
        logger.info(f"   Parent Field: {pattern['parent_field']}")
        logger.info(f"   AJAX Param: {pattern['parent_request_param']}")
        logger.info(f"   JS Field ID: {pattern['parent_js_field_id']}")
        logger.info(f"   Code Length: {pattern['code_length']}")
        logger.info(f"   Separator: '{pattern['separator']}'")
        
        return pattern
    
    # âœ… PHASE 1 FIX #3: Related Tables Detection (No Hardcoding)
    def _detect_related_tables(self, company_example: str, entity_name: str) -> List[Dict]:
        """
        Find ALL tables that reference this entity - 100% DYNAMIC
        Extracts from pre-delete checks in company code
        
        Returns:
            [
                {'table': 'tblcustomer', 'field': 'Sub_Area', 'message': 'Customer'},
                {'table': 'tblsaleman', 'field': 'Sub_Area', 'message': 'Saleman'}
            ]
        """
        
        related_tables = []
        
        if not company_example:
            return related_tables
        
        seen_entries = set()
        getrows_pattern = (
            r'getrows2\s*\(\s*["\'](?P<table>\w+)["\']\s*,\s*'
            r'(?P<filter>"[^"]*"|\'[^\']*\'|[^\)]*)\)'
        )

        for match in re.finditer(getrows_pattern, company_example, re.DOTALL | re.IGNORECASE):
            table = match.group('table')
            filter_expr = (match.group('filter') or '').strip()

            # Extract field name from the filter string
            field_match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*=', filter_expr)
            field = field_match.group(1) if field_match else entity_name

            # Try to pick the nearest alert after this check
            message = f"Exists in {table}"
            tail_text = company_example[match.end(): match.end() + 450]
            alert_match = re.search(r'alert\s*\(\s*["\']([^"\']+)["\']', tail_text, re.IGNORECASE)
            if alert_match:
                message = alert_match.group(1)

            dedup_key = (table.lower(), field.lower(), message.lower())
            if dedup_key in seen_entries:
                continue
            seen_entries.add(dedup_key)

            related_tables.append({
                'table': table,
                'field': field,
                'message': message
            })
        
        logger.info(f"âœ… Detected {len(related_tables)} related tables for pre-delete checks:")
        for rel in related_tables:
            logger.info(f"   - {rel['table']}.{rel['field']}: '{rel['message']}'")
        
        return related_tables
    
    # ✅ NEW FIX: Extract dependencies from user request
    def _extract_dependencies_from_user_request(self, user_request: str, primary_key: str = 'Code') -> List[Dict]:
        """
        Extract dependency tables from user request if specified.
        Example: "Dependencies: payroll.Employee_Code, attendance.Employee_Code, leaveapp.Employee_Code"
        
        Returns:
            [
                {'table': 'payroll', 'field': 'Employee_Code', 'message': 'payroll'},
                {'table': 'attendance', 'field': 'Employee_Code', 'message': 'attendance'},
                {'table': 'leaveapp', 'field': 'Employee_Code', 'message': 'leaveapp'}
            ]
        """
        dependencies = []
        
        if not user_request:
            return dependencies
        
        # Find "Dependencies:" section
        dep_match = re.search(
            r'(?:^|\n)\s*Dependencies\s*:\s*(.+?)(?:\n|$)',
            user_request,
            re.IGNORECASE | re.DOTALL
        )
        
        if not dep_match:
            return dependencies
        
        dep_text = dep_match.group(1).strip()
        
        dep_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)'
        
        for match in re.finditer(dep_pattern, dep_text, re.IGNORECASE):
            table = match.group(1).strip()
            field = match.group(2).strip()
            
            if table and field:
                dependencies.append({
                    'table': table,
                    'field': field,
                    'message': table
                })
        
        if dependencies:
            logger.info(f"✅ Extracted {len(dependencies)} user-specified dependencies: {[d['table'] for d in dependencies]}")
        
        return dependencies
    
    # ✅ NEW FIX: Extract dropdown fields from user request
    def _extract_dropdown_fields_from_request(self, user_request: str) -> List[tuple]:
        """
        Extract dropdown fields from user request.
        Example: "Department_Code(select, required), Designation_Code(select, required), CostCenter_Code(select)"
        
        Returns:
            [
                ('Department_Code', 'tbldepartment'),
                ('Designation_Code', 'tbldesignation'),
                ('CostCenter_Code', 'tblcostcenter')
            ]
        """
        dropdowns = []
        
        if not user_request:
            return dropdowns
        
        master_fields_match = re.search(
            r'(?:^|\n)\s*(?:Master\s+Fields|Form\s+Fields|fields)\s*:\s*(.+?)(?:\n(?:Master|Form|Fields|Primary|Relationships|Dependencies|Business)|$)',
            user_request,
            re.IGNORECASE | re.DOTALL
        )
        
        if not master_fields_match:
            return dropdowns
        
        fields_text = master_fields_match.group(1).strip()
        
        field_pattern = r'([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*(select|dropdown)\s*(?:,\s*([^)]*))?'
        
        for match in re.finditer(field_pattern, fields_text, re.IGNORECASE):
            field_name = match.group(1).strip()
            dropdown_type = match.group(2).strip()
            
            if field_name and dropdown_type.lower() in ('select', 'dropdown'):
                table_name = self._infer_lookup_table(field_name)
                dropdowns.append((field_name, table_name))
        
        if dropdowns:
            logger.info(f"✅ Extracted {len(dropdowns)} dropdown fields: {[d[0] for d in dropdowns]}")
        
        return dropdowns
    
    # ✅ NEW FIX: Infer lookup table from field name
    def _infer_lookup_table(self, field_name: str) -> str:
        """
        Infer lookup table name from field name.
        Example: Department_Code -> tbldepartment
        """
        field_lower = field_name.lower()
        
        mappings = {
            'department_code': 'tbldepartment',
            'designation_code': 'tbldesignation',
            'costcenter_code': 'tblcostcenter',
            'area_code': 'tblarea',
            'sub_area_code': 'tblsubarea',
            'city_code': 'tblcity',
            'country_code': 'tblcountry',
            'region_code': 'tblregion',
            'category_code': 'tblcategory',
            'type_code': 'tbltype',
            'group_code': 'tblgroup',
            'unit_code': 'tblunit',
            'item_code': 'tblitem',
            'customer_code': 'tblcustomer',
            'supplier_code': 'tblsupplier',
            'employee_code': 'tblemployee',
            'company_code': 'tblcompany',
            'branch_code': 'tblbranch',
        }
        
        for key, table in mappings.items():
            if key in field_lower:
                return table
        
        base_name = re.sub(r'_(code|id)$', '', field_lower, flags=re.IGNORECASE)
        return f"tbl{base_name}"
    
    # âœ… ISSUE #8 FIX: Grid Pattern Detection (No Hardcoding)
    def _detect_grid_pattern(self, company_example: str, entity_name: str, requested_grid: Dict = None) -> Dict:
        """
        Detect grid/detail table patterns - 100% DYNAMIC
        Extracts from company code's detail table save logic
        
        Returns:
            {
                'has_grid': True,
                'sub_table': 'tblcustomerdtl',
                'grid_fields': ['SR_NO', 'SiteName', 'Shipping'],
                'txtcount_var': 'TXTCOUNTACC',
                'loop_var': 'i'
            }
        """
        
        grid_info = {
            'has_grid': False,
            'sub_table': None,
            'grid_fields': [],
            'txtcount_var': None,
            'loop_var': None,
            'explicit_request': False
        }
        
        if not company_example and not requested_grid:
            return grid_info
        
        if company_example:
            # 1. Detect sub_table variable
            sub_table_pattern = r'\$sub_table\s*=\s*["\'](\w+)["\']'
            sub_table_match = re.search(sub_table_pattern, company_example, re.IGNORECASE)
            if sub_table_match:
                grid_info['sub_table'] = sub_table_match.group(1)
                logger.info(f"âœ… Detected sub_table: {grid_info['sub_table']}")
            
            # 2. Detect TXTCOUNT variable
            txtcount_pattern = r'<input[^>]+id\s*=\s*["\']?(TXTCOUNT\w*)["\']?[^>]*>'
            txtcount_match = re.search(txtcount_pattern, company_example, re.IGNORECASE)
            if txtcount_match:
                grid_info['txtcount_var'] = txtcount_match.group(1)
                logger.info(f"âœ… Detected TXTCOUNT variable: {grid_info['txtcount_var']}")
            
            # 3. Detect detail loop and extract fields
            # Pattern: for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++)
            loop_pattern = r'for\s*\(\s*\$(\w+)\s*=\s*0\s*;\s*\$\w+\s*<=\s*\$_REQUEST\s*\[\s*["\']TXTCOUNT\w*["\']\s*\]\s*;\s*\$\w+\+\+\s*\)\s*\{(.*?)\}'
            loop_match = re.search(loop_pattern, company_example, re.DOTALL | re.IGNORECASE)
            
            if loop_match:
                grid_info['loop_var'] = loop_match.group(1)
                loop_body = loop_match.group(2)
                
                # Extract field names from loop body
                # Pattern: $_REQUEST['FieldName'.$i] or $columns['FieldName']
                field_pattern = r'\$_REQUEST\s*\[\s*["\'](\w+)\s*\.\s*\$' + grid_info['loop_var'] + r'["\']?\s*\]'
                field_matches = re.finditer(field_pattern, loop_body, re.IGNORECASE)
                
                for match in field_matches:
                    field_name = match.group(1)
                    if field_name not in grid_info['grid_fields']:
                        grid_info['grid_fields'].append(field_name)
                
                # Also check $columns assignments
                columns_pattern = r'\$columns\s*\[\s*["\'](\w+)["\']\s*\]\s*=\s*\$_REQUEST'
                columns_matches = re.finditer(columns_pattern, loop_body, re.IGNORECASE)
                
                for match in columns_matches:
                    field_name = match.group(1)
                    if field_name not in grid_info['grid_fields'] and field_name != entity_name.upper() + '_CODE':
                        grid_info['grid_fields'].append(field_name)
                
                logger.info(f"âœ… Detected loop variable: ${grid_info['loop_var']}")
                logger.info(f"âœ… Detected {len(grid_info['grid_fields'])} grid fields: {grid_info['grid_fields']}")

        if requested_grid:
            if requested_grid.get('sub_table'):
                grid_info['sub_table'] = requested_grid['sub_table']
            if requested_grid.get('txtcount_var'):
                grid_info['txtcount_var'] = requested_grid['txtcount_var']
            if requested_grid.get('loop_var'):
                grid_info['loop_var'] = requested_grid['loop_var']
            if requested_grid.get('explicit_request'):
                grid_info['explicit_request'] = True
            elif requested_grid.get('has_grid') and not requested_grid.get('explicit_opt_out'):
                grid_info['explicit_request'] = True

            grid_info['grid_fields'] = self._unique_preserve_order(
                requested_grid.get('grid_fields', []) + grid_info['grid_fields']
            )

            if requested_grid.get('has_grid'):
                logger.info(
                    f"âœ… Applied requested grid requirement: "
                    f"{grid_info.get('sub_table') or 'sub-table'} with {len(grid_info['grid_fields'])} fields"
                )
        
        # Mark as having grid if we found key components
        if grid_info['sub_table'] and grid_info['txtcount_var'] and grid_info['grid_fields']:
            grid_info['has_grid'] = True
            logger.info(f"âœ… Grid pattern detected: {grid_info['sub_table']} with {len(grid_info['grid_fields'])} fields")
        else:
            logger.info(f"âšª No grid pattern detected")
        
        return grid_info
    
    # âœ… PHASE 1 FIX #4: Cascading Dropdown Detection (No Hardcoding)
    def _detect_cascading_dropdown_logic(self, company_example: str) -> Dict:
        """
        Detect cascading dropdown patterns - 100% DYNAMIC
        
        Returns:
            {
                'has_cascading': True,
                'parent_dropdown': 'Main_Area',
                'child_dropdown': 'Sub_Area',
                'ajax_function_name': 'SubArea',
                'ajax_param_name': 'bnkId',
                'disabled_on_update': True,
                'triggers_maxid': True
            }
        """
        
        logic = {
            'has_cascading': False,
            'parent_dropdown': None,
            'child_dropdown': None,
            'ajax_function_name': None,
            'ajax_param_name': None,
            'disabled_on_update': False,
            'triggers_maxid': False
        }
        
        if not company_example:
            return logic
        
        # Check for onChange with maxid() - this identifies parent dropdown
        # Pattern: <select name="Main_Area" onChange="SubArea();maxid();">
        onchange_pattern = r'<select[^>]*name=["\']([^"\']+)["\'][^>]*onChange=["\']([^"\']+)["\']'
        onchange_match = re.search(onchange_pattern, company_example, re.IGNORECASE)
        
        if onchange_match:
            logic['parent_dropdown'] = onchange_match.group(1)
            onchange_value = onchange_match.group(2)
            
            # Check if onChange calls maxid()
            if 'maxid' in onchange_value.lower():
                logic['has_cascading'] = True
                logic['triggers_maxid'] = True
                logger.info(f"ðŸ” Detected parent dropdown: {logic['parent_dropdown']} triggers maxid()")
            
            # Extract child function name from onChange (e.g., "SubArea();maxid();" â†’ "SubArea")
            func_match = re.search(r'(\w+)\s*\(\s*\)', onchange_value)
            if func_match:
                logic['ajax_function_name'] = func_match.group(1)
                logger.info(f"ðŸ” Detected AJAX function: {logic['ajax_function_name']}()")
        
        # Detect child dropdown from AJAX function
        # Pattern: function SubArea() { var $Sub_Area = $('#Sub_Area');
        if logic['ajax_function_name']:
            child_pattern = rf'function\s+{logic["ajax_function_name"]}\s*\(\s*\).*?\$\s*(\w+)\s*=\s*\$\(["\']#(\w+)["\']\)'
            child_match = re.search(child_pattern, company_example, re.DOTALL)
            if child_match:
                logic['child_dropdown'] = child_match.group(2)  # Get ID from $('#Sub_Area')
                logger.info(f"ðŸ” Detected child dropdown: {logic['child_dropdown']}")
        
        # Detect AJAX parameter name from PHP handler
        # Pattern: if($_REQUEST['bnkId']) { ... WHERE Country_Code='".$_REQUEST['bnkId']."'
        ajax_param_pattern = r'if\s*\(\s*\$_REQUEST\[["\'](\w+)["\']\]\s*\)'
        ajax_param_match = re.search(ajax_param_pattern, company_example)
        if ajax_param_match:
            logic['ajax_param_name'] = ajax_param_match.group(1)
            logger.info(f"ðŸ” Detected AJAX param: {logic['ajax_param_name']}")
        
        # Check for disabled on update
        disabled_pattern = r'<select[^>]*name=["\']([^"\']+)["\'][^>]*\?\s*disabled'
        disabled_match = re.search(disabled_pattern, company_example, re.IGNORECASE)
        
        if disabled_match:
            logic['disabled_on_update'] = True
            logger.info(f"ðŸ” Detected disabled on update for: {disabled_match.group(1)}")
        
        return logic

    def _build_user_contract_from_strict_contract(self, strict_contract: Dict[str, Any]) -> Dict[str, Any]:
        """Map strict preflight contract into ContractParser user-contract shape."""
        strict_contract = strict_contract or {}

        def _normalize_fields(raw_fields: List[Any], section: str) -> List[Dict[str, Any]]:
            normalized: List[Dict[str, Any]] = []
            for field in raw_fields or []:
                if isinstance(field, dict):
                    field_name = str(field.get('name') or '').strip()
                    if not field_name:
                        continue
                    db_type = str(field.get('db_type') or field.get('type') or 'varchar').strip() or 'varchar'
                    normalized.append({
                        'name': field_name,
                        'db_type': db_type,
                        'type': db_type,
                        'input_type': str(field.get('input_type') or '').strip(),
                        'required': bool(field.get('required')),
                        'readonly': bool(field.get('readonly')),
                        'section': section,
                    })
                    continue
                field_name = str(field or '').strip()
                if not field_name:
                    continue
                normalized.append({
                    'name': field_name,
                    'db_type': 'varchar',
                    'type': 'varchar',
                    'input_type': '',
                    'required': False,
                    'readonly': False,
                    'section': section,
                })
            return normalized

        master_fields = _normalize_fields(list(strict_contract.get('master_fields') or []), 'master')
        detail_fields = _normalize_fields(list(strict_contract.get('detail_fields') or []), 'detail')
        merged_fields = master_fields + detail_fields

        return {
            'table': str(strict_contract.get('master_table') or '').strip(),
            'filename': str(strict_contract.get('file_name') or '').strip(),
            'title': str(strict_contract.get('title') or strict_contract.get('entity') or '').strip(),
            'case_type': str(strict_contract.get('title') or strict_contract.get('entity') or '').strip(),
            'primary_key': str(strict_contract.get('primary_key') or '').strip(),
            'fields': merged_fields,
            'detail_table': str(strict_contract.get('detail_table') or '').strip(),
            'relationships': list(strict_contract.get('relationships') or []),
            'dependencies': list(strict_contract.get('dependencies') or []),
            'features': list(strict_contract.get('features') or []),
            'form_type': str(strict_contract.get('form_type') or '').strip(),
            'master_fields': master_fields,
            'detail_fields': detail_fields,
            'parsing_method': 'strict_preflight_contract',
        }
    
    async def generate_inline_php_file(
        self,
        intent: Dict,
        sql_schema: str,
        company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        user_request: str = "",
        validation_errors: List = None,
        max_retries: int = 2
    ) -> str:
        """
        ✅ PHASE 2.2: REFACTORED GENERATION METHOD
        
        Uses 4 modular classes for clean architecture:
        1. ContractParser - Parse user request into contract
        2. GenerationPlanner - Plan generation strategy  
        3. CodeAssembler - Assemble final code
        4. EnterpriseValidator - Validate generated code
        
        Falls back to legacy method if modular approach fails.
        """
        logger.info("🚀 PHASE 2.2: Using modular generation architecture")
        
        try:
            # Try modular approach
            return await self._generate_with_modular_classes(
                intent=intent,
                sql_schema=sql_schema,
                company_examples=company_examples,
                analyzed_patterns=analyzed_patterns,
                standards=standards,
                user_request=user_request,
                validation_errors=validation_errors,
                max_retries=max_retries
            )
        except Exception as e:
            # ✅ STEP 2: DISABLE LEGACY FALLBACK - Force retry instead
            logger.error(f"❌ Modular generation failed: {e}")
            logger.error("❌ LEGACY FALLBACK DISABLED - Modular generation must succeed")
            raise Exception(f"Modular generation failed - retry required: {e}")
    
    def _is_complete_generation(self, code: str) -> bool:
        """
        ✅ FIX 2: Hard completeness check for generated code
        
        Verifies all critical sections are present before accepting generation.
        """
        sections = self._parse_controlled_generation_sections(code)
        section_presence = {
            section_name: bool((sections.get(section_name) or '').strip())
            for section_name in [
                'VARIABLE_INIT_PHP',
                'CRUD_LOGIC_PHP',
                'AJAX_HANDLERS_PHP',
                'FORM_FIELDS_HTML',
                'FORM_VALIDATION_FIELDS',
                'SELECT2_HANDLERS',
                'ENTITY_JS',
            ]
        }
        merged_section_text = '\n'.join(sections.values())
        required_patterns = {
            'db_insert': bool(re.search(r'db_insert\s*\(', merged_section_text, re.IGNORECASE)),
            'db_update': bool(re.search(r'db_update\s*\(', merged_section_text, re.IGNORECASE)),
            'db_delete': bool(re.search(r'db_delete\s*\(', merged_section_text, re.IGNORECASE)),
            '$.ajax': '$.ajax' in merged_section_text.lower(),
            'formValidation': 'formvalidation' in merged_section_text.lower(),
        }
        
        missing = [k for k, v in section_presence.items() if not v]
        missing.extend([k for k, v in required_patterns.items() if not v])
        
        if missing:
            logger.warning(f"⚠️ Completeness check failed - missing: {', '.join(missing)}")
            return False
        
        logger.info("✅ Completeness check passed - all required sections present")
        return True
    
    async def _generate_with_modular_classes(
        self,
        intent: Dict,
        sql_schema: str,
        company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        user_request: str = "",
        validation_errors: List = None,
        max_retries: int = 3  # FIX #6: Increased from 2 to 3 (4 total attempts)
    ) -> str:
        """
        ✅ PHASE 2.2: MODULAR GENERATION IMPLEMENTATION
        
        Step-by-step generation using 4 modular classes.
        FIX #6: Default 3 retries = 4 total attempts (was 2 retries = 3 attempts)
        """
        logger.info("=" * 80)
        logger.info("📋 STEP 1: Parsing contract...")

        strict_contract = ((intent or {}).get('strict_contract') or {}) if isinstance(intent, dict) else {}
        strict_contract_mode = bool(
            (intent or {}).get('strict_contract_mode') if isinstance(intent, dict) else False
        ) or bool(strict_contract.get('valid'))

        if strict_contract_mode and isinstance(strict_contract, dict):
            logger.info("✅ Using strict preflight contract as parser source (RequestSchemaParser bypass)")
            user_contract = self._build_user_contract_from_strict_contract(strict_contract)
        else:
            user_contract = self.contract_parser.parse_user_request(user_request)

        company_metadata = self.contract_parser.extract_canonical_metadata(company_examples, "")
        contract = self.contract_parser.merge_contracts(user_contract, company_metadata)
        retrieval_top_candidates = intent.get('retrieval_top_candidates') if isinstance(intent, dict) else []
        if retrieval_top_candidates:
            contract['retrieval_top_candidates'] = retrieval_top_candidates
        
        logger.info(f"✅ Contract: {contract.get('table_name')} / {contract.get('file_name')}")
        
        # Extract canonical naming for logging
        naming_metadata = self._extract_canonical_form_metadata_with_parser(
            user_request=user_request,
            company_example=company_examples,
            example_file_path=""
        )
        intent_db = ((intent or {}).get('database') or {}) if isinstance(intent, dict) else {}
        if not str(naming_metadata.get('table_name') or '').strip():
            naming_metadata['table_name'] = str(intent_db.get('table_name') or '').strip()
        if not str(naming_metadata.get('file_name') or '').strip():
            naming_metadata['file_name'] = str(intent_db.get('file_name') or '').strip()
        if not str(naming_metadata.get('title') or '').strip():
            naming_metadata['title'] = (
                str((intent or {}).get('form_title') or '').strip()
                or str(intent_db.get('form_title') or '').strip()
            )

        if strict_contract_mode:
            strict_overrides = {
                'table_name': str(strict_contract.get('master_table') or strict_contract.get('table_name') or '').strip(),
                'file_name': str(strict_contract.get('file_name') or '').strip(),
                'title': str(strict_contract.get('title') or strict_contract.get('entity') or '').strip(),
            }
            for key, strict_value in strict_overrides.items():
                if strict_value:
                    naming_metadata[key] = strict_value

        if not str(naming_metadata.get('effective_entity') or '').strip():
            fallback_entity = (
                str(contract.get('entity_name') or '').strip()
                or str(naming_metadata.get('title') or '').strip()
                or str(naming_metadata.get('file_name') or '').replace('frm', '').replace('.php', '').strip()
                or str(naming_metadata.get('table_name') or '').replace('tbl', '').strip()
            )
            naming_metadata['effective_entity'] = fallback_entity
        if not str(naming_metadata.get('effective_entity_compact') or '').strip():
            naming_metadata['effective_entity_compact'] = re.sub(
                r'[^a-z0-9]',
                '',
                str(naming_metadata.get('effective_entity') or '').lower()
            )

        logger.info("🔍 Canonical naming extraction:")
        logger.info(f"   - table_name: '{naming_metadata.get('table_name')}'")
        logger.info(f"   - file_name: '{naming_metadata.get('file_name')}'")
        logger.info(f"   - title: '{naming_metadata.get('title')}'")
        logger.info(f"   - effective_entity: '{naming_metadata.get('effective_entity')}'")

        if strict_contract_mode:
            missing_canonical = [
                key for key in ('table_name', 'file_name', 'title')
                if not str(naming_metadata.get(key) or '').strip()
            ]
            if missing_canonical:
                raise ValueError(
                    "Strict canonical naming required but missing: "
                    + ', '.join(missing_canonical)
                )

        contract['table_name'] = str(naming_metadata.get('table_name') or contract.get('table_name') or '').strip()
        contract['file_name'] = str(naming_metadata.get('file_name') or contract.get('file_name') or '').strip()
        contract['title'] = str(naming_metadata.get('title') or contract.get('title') or '').strip()
        contract['strict_contract_mode'] = strict_contract_mode
        contract['strict_contract'] = strict_contract if isinstance(strict_contract, dict) else {}
        if strict_contract_mode and isinstance(strict_contract, dict):
            if strict_contract.get('detail_table') and not contract.get('detail_table'):
                contract['detail_table'] = str(strict_contract.get('detail_table') or '').strip()
            if strict_contract.get('master_fields') and not contract.get('master_fields'):
                contract['master_fields'] = strict_contract.get('master_fields') or []
            if strict_contract.get('detail_fields') and not contract.get('detail_fields'):
                contract['detail_fields'] = strict_contract.get('detail_fields') or []
            if strict_contract.get('dependencies') and not contract.get('dependencies'):
                contract['dependencies'] = strict_contract.get('dependencies') or []
        if not contract.get('entity_name'):
            contract['entity_name'] = (
                str(naming_metadata.get('effective_entity') or '').strip()
                or str(contract.get('title') or '').strip()
            )

        self.last_generation_metadata = dict(naming_metadata or {})
        self.last_generation_metadata['strict_contract_mode'] = strict_contract_mode
        self.last_generation_metadata['contract'] = {
            'table_name': contract.get('table_name'),
            'file_name': contract.get('file_name'),
            'title': contract.get('title'),
        }

        # Ensure modular assembly has access to fixed framework parts even when
        # DynamicFormTemplate cannot be built from on-disk frm*.php files.
        fixed_parts = self._extract_fixed_parts_from_example(company_examples, "")
        if not str(fixed_parts.get('source_content') or '').strip():
            fixed_parts['source_content'] = company_examples or ''
        
        # Plan generation
        logger.info("📝 STEP 2: Planning generation...")
        user_requirements = self._detect_user_requirements(user_request)
        plan = self.generation_planner.plan_generation(
            contract=contract,
            company_examples=company_examples,
            analyzed_patterns=analyzed_patterns,
            user_requirements=user_requirements
        )
        
        logger.info(f"✅ Plan: {plan['strategy']} with {len(plan['sections_to_generate'])} sections")
        # ✅ FIX 4: Regeneration loop (max 2 retries)
        required_sections = [
            'VARIABLE_INIT_PHP',
            'CRUD_LOGIC_PHP',
            'AJAX_HANDLERS_PHP',
            'FORM_FIELDS_HTML',
            'FORM_VALIDATION_FIELDS',
            'SELECT2_HANDLERS',
            'ENTITY_JS',
        ]
        core_required_sections = list(required_sections)
        best_section_snapshots: Dict[str, str] = {}

        def _compose_controlled_output(section_map: Dict[str, str]) -> str:
            parts: List[str] = []
            for section_name in required_sections:
                section_value = (section_map.get(section_name) or '').strip()
                parts.append(
                    f"<<<{section_name}>>>\n{section_value}\n<<<END_{section_name}>>>"
                )
            return "\n\n".join(parts)

        def _normalize_retry_error(error_entry: Any) -> str:
            if isinstance(error_entry, str):
                return error_entry.strip()
            if isinstance(error_entry, dict):
                for key in ('error', 'issue', 'message', 'detail', 'reason', 'step'):
                    value = error_entry.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
                return json.dumps(error_entry, ensure_ascii=True)
            return str(error_entry or '').strip()

        def _classify_retry_error(error_entry: Any) -> str:
            text = _normalize_retry_error(error_entry).lower()
            if any(token in text for token in ['dependency', 'getrows', 'pre-delete', 'cannot delete', 'tbl']):
                return 'dependency'
            if any(token in text for token in ['contamination', 'cross-entity', 'unknown contract token', 'allowlist']):
                return 'contamination'
            if any(token in text for token in ['syntax', 'parse error', 'unexpected', 'missing closing', 'unterminated']):
                return 'syntax'
            if any(token in text for token in ['duplicate', 'maxid', '?>', 'function definitions']):
                return 'duplication'
            return 'other'

        def _select_retry_errors(validation_errors: List[Any]) -> List[str]:
            if not validation_errors:
                return []

            prioritized_categories = ['dependency', 'contamination', 'syntax', 'duplication']
            selected: List[str] = []
            seen = set()

            # Do not drop critical categories; include all of them.
            for error in validation_errors:
                normalized_error = _normalize_retry_error(error)
                if not normalized_error:
                    continue
                category = _classify_retry_error(normalized_error)
                if category in prioritized_categories and normalized_error not in seen:
                    selected.append(normalized_error)
                    seen.add(normalized_error)

            # Add remaining context with a bounded tail.
            for error in validation_errors:
                normalized_error = _normalize_retry_error(error)
                if not normalized_error or normalized_error in seen:
                    continue
                selected.append(normalized_error)
                seen.add(normalized_error)
                if len(selected) >= 12:
                    break

            return selected

        retry_count = 0
        last_generated_code = ""
        last_assembled_code = ""
        accumulated_errors: List[str] = []
        for error in validation_errors or []:
            normalized_error = _normalize_retry_error(error)
            if normalized_error:
                accumulated_errors.append(normalized_error)
        
        while retry_count <= max_retries:
            attempt_num = retry_count + 1
            logger.info(f"🤖 STEP 3: Generating code with LLM (attempt {attempt_num}/{max_retries + 1})...")
            
            # Build prompt (retry prompt if this is a retry)
            if retry_count == 0:
                prompt = plan['prompt']
            else:
                selected_errors = _select_retry_errors(accumulated_errors)
                logger.info(
                    f"🔄 Retry attempt {retry_count}: Building category-based retry prompt with "
                    f"{len(selected_errors)} errors (from {len(accumulated_errors)})"
                )
                prompt = self.generation_planner.build_retry_prompt(
                    original_prompt=plan['prompt'],
                    validation_errors=selected_errors,
                    previous_code=last_generated_code,
                    previous_size=len(last_generated_code)
                )
            
            messages = self._build_generation_messages(prompt, user_request)
            model_name = self._model_for_attempt(retry_count)
            llm_client = self._get_llm_client(model_name)
            
            response = await llm_client.ainvoke(messages)
            generated_code = response.content
            last_generated_code = generated_code
            
            generated_size = len(generated_code)
            logger.info(f"✅ Generated: {generated_size} chars")
            
            # ✅ FIX 1: HARD TAG VALIDATION (MANDATORY)
            # Check raw output contains ALL required tags BEFORE parsing
            logger.info("🔍 Validating LLM output structure...")
            
            generated_sections = self._parse_controlled_generation_sections(generated_code)
            synthesized_sections = []
            if not (generated_sections.get('FORM_VALIDATION_FIELDS') or '').strip():
                default_validation_fields = self._build_default_controlled_validation_fields(
                    contract,
                    user_request=user_request,
                )
                if default_validation_fields:
                    generated_sections['FORM_VALIDATION_FIELDS'] = default_validation_fields
                    synthesized_sections.append('FORM_VALIDATION_FIELDS')
            if not (generated_sections.get('SELECT2_HANDLERS') or '').strip():
                generated_sections['SELECT2_HANDLERS'] = self._build_default_controlled_select2_handlers()
                synthesized_sections.append('SELECT2_HANDLERS')
            if synthesized_sections:
                generated_code = _compose_controlled_output(generated_sections)
                last_generated_code = generated_code
                logger.info(
                    "ðŸ§© Synthesized missing controlled helper sections: %s",
                    ', '.join(synthesized_sections)
                )

            missing_sections = [
                section_name
                for section_name in required_sections
                if not self._has_controlled_section_tag(generated_code, section_name)
            ]
            if missing_sections:
                error_msg = f"🔥 LLM STRUCTURE ERROR: Missing required sections: {', '.join(missing_sections)}"
                logger.error(error_msg)

                if retry_count > 0:
                    accumulated_errors.insert(0, "🔥 CRITICAL: PREVIOUS ATTEMPT FAILED - YOU RETURNED FLAT CODE WITHOUT TAGS")
                    accumulated_errors.insert(1, "THIS IS YOUR LAST CHANCE - USE TAGS OR SYSTEM WILL REJECT")
                    accumulated_errors.insert(2, "YOU MUST wrap EVERY section in: <<<SECTION>>> content <<<END_SECTION>>>")
                    accumulated_errors.insert(3, "NO FLAT PHP CODE ALLOWED - ONLY TAGGED STRUCTURE ACCEPTED")

                accumulated_errors.append(error_msg)
                accumulated_errors.append("YOU MUST return ALL 7 tagged sections; missing sections are never auto-filled")

                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to missing tags")
                    continue
                raise ValueError(
                    f"Controlled assembly failed after {max_retries + 1} attempts: "
                    f"Missing sections: {', '.join(missing_sections)}"
                )
            
            logger.info("✅ All required tags present in LLM output")
            
            # ✅ FIX 3: PARSE AND CHECK EMPTY SECTIONS (MANDATORY)
            logger.info("🔍 Parsing tagged sections...")
            sections = self._parse_controlled_generation_sections(generated_code)

            for section_name in core_required_sections:
                section_body = (sections.get(section_name) or '').strip()
                if len(section_body) >= 100 and len(section_body) >= len(best_section_snapshots.get(section_name, '')):
                    best_section_snapshots[section_name] = section_body
            
            empty_sections = [
                section_name for section_name in core_required_sections
                if not sections.get(section_name, '').strip() or len(sections.get(section_name, '').strip()) < 100
            ]
            if empty_sections:
                recovered_sections: List[str] = []
                for section_name in list(empty_sections):
                    preserved_body = (best_section_snapshots.get(section_name) or '').strip()
                    if len(preserved_body) >= 100:
                        sections[section_name] = preserved_body
                        recovered_sections.append(section_name)

                if recovered_sections:
                    logger.warning(
                        "♻️ Recovered empty sections from earlier valid attempt: %s",
                        ', '.join(recovered_sections)
                    )
                    generated_code = _compose_controlled_output(sections)
                    last_generated_code = generated_code
                    empty_sections = [
                        section_name for section_name in core_required_sections
                        if not sections.get(section_name, '').strip() or len(sections.get(section_name, '').strip()) < 100
                    ]
                    if not empty_sections:
                        logger.info("✅ Empty-section recovery successful; continuing without discarding valid sections")

            if empty_sections:
                error_msg = f"🔥 EMPTY SECTIONS DETECTED: {', '.join(empty_sections)}"
                logger.error(error_msg)
                accumulated_errors.append(error_msg)
                accumulated_errors.append("Each section must contain REAL CODE (minimum 100 chars)")
                accumulated_errors.append("CRUD_LOGIC_PHP must have: Save, Update, Delete, Edit handlers")
                accumulated_errors.append("AJAX_HANDLERS_PHP must have: GetMaxID handler with exit")
                accumulated_errors.append("FORM_FIELDS_HTML must have: ALL form fields with proper grid layout")
                accumulated_errors.append("ENTITY_JS must have: maxid() function + formValidation")
                
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to empty sections")
                    continue
                else:
                    raise ValueError(f"Controlled assembly failed: Required sections are empty: {', '.join(empty_sections)}")
            
            logger.info("✅ All sections contain content")

            requested_field_count = len(contract.get('fields') or [])
            dynamic_crud_min = max(700, min(1300, 320 + (requested_field_count * 120)))
            # Calibrate FORM_FIELDS_HTML floor to real contract size so strict mode
            # blocks tiny/placeholder output without rejecting structurally complete forms.
            dynamic_form_fields_min = max(800, min(2400, 220 + (requested_field_count * 180)))
            section_min_sizes = {
                'CRUD_LOGIC_PHP': dynamic_crud_min,
                'FORM_FIELDS_HTML': dynamic_form_fields_min,
                'ENTITY_JS': 700,
                'AJAX_HANDLERS_PHP': 200,
            }
            undersized_sections = []
            crud_content = (sections.get('CRUD_LOGIC_PHP') or '').strip()
            crud_semantic_markers = [
                r"\bif\s*\(\s*isset\(\$_POST\['action'\]\)\s*&&\s*\$_POST\['action'\]\s*==\s*'save'\s*\)",
                r"\bif\s*\(\s*isset\(\$_POST\['action'\]\)\s*&&\s*\$_POST\['action'\]\s*==\s*'update'\s*\)",
                r"\bif\s*\(\s*isset\(\$_POST\['action'\]\)\s*&&\s*\$_POST\['action'\]\s*==\s*'delete'\s*\)",
                r"db_insert\s*\(",
                r"db_update\s*\(",
                r"db_delete\s*\(",
                r"db_getRecord\s*\(",
                r"funStartTran\s*\(",
                r"funEndTran\s*\(",
            ]
            crud_marker_hits = sum(
                1 for marker in crud_semantic_markers if re.search(marker, crud_content, re.IGNORECASE)
            )

            for section_name, min_size in section_min_sizes.items():
                section_size = len((sections.get(section_name) or '').strip())
                if section_size < min_size:
                    if section_name == 'CRUD_LOGIC_PHP':
                        # Avoid false negatives: semantic-complete CRUD can be valid below hard char thresholds.
                        semantic_floor = max(900, int(dynamic_crud_min * 0.75))
                        if section_size >= semantic_floor and crud_marker_hits >= 7:
                            logger.info(
                                "CRUD_LOGIC_PHP accepted via semantic quality fallback (%d chars, markers=%d)",
                                section_size,
                                crud_marker_hits,
                            )
                            continue
                    undersized_sections.append(f"{section_name}={section_size}<{min_size}")

            form_validation_fields = (sections.get('FORM_VALIDATION_FIELDS') or '').strip()
            select2_handlers = (sections.get('SELECT2_HANDLERS') or '').strip()
            placeholder_tokens = ('not required for this form type', 'placeholder', 'todo', 'rest of code', '...')
            if (
                not form_validation_fields
                or any(token in form_validation_fields.lower() for token in placeholder_tokens)
            ):
                undersized_sections.append("FORM_VALIDATION_FIELDS=placeholder_or_empty")

            has_select_fields = bool(re.search(r'\binput\s*:\s*(?:select|dropdown)\b', user_request or '', re.IGNORECASE))
            if has_select_fields and (
                not select2_handlers
                or any(token in select2_handlers.lower() for token in placeholder_tokens)
            ):
                undersized_sections.append("SELECT2_HANDLERS=placeholder_or_empty_with_select_fields")

            if undersized_sections:
                error_msg = (
                    "🔥 SECTION SIZE/QUALITY CHECK FAILED: "
                    + "; ".join(undersized_sections)
                )
                logger.error(error_msg)
                accumulated_errors.append(error_msg)
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(
                        f"⚠️ Triggering retry {retry_count}/{max_retries} due to section size/quality failures"
                    )
                    continue
                raise ValueError(error_msg)
             
            # 🔴 CRITICAL FIX 2: FORM FIELD SIZE VALIDATION
            # Validate form_fields has minimum 800 chars (prevents 69-char disaster)
            form_fields_content = sections.get('FORM_FIELDS_HTML', '').strip()
            if len(form_fields_content) < 800:
                error_msg = f"🔥 FORM_FIELDS_HTML TOO SMALL: {len(form_fields_content)} chars (minimum 800 required for 5 fields)"
                logger.error(error_msg)
                accumulated_errors.append(error_msg)
                accumulated_errors.append("FORM_FIELDS_HTML must contain COMPLETE HTML for ALL 5 fields")
                accumulated_errors.append("Each field needs: <div class='form-group'>, <label>, <input> = ~200 chars per field")
                
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to insufficient form fields")
                    continue
                else:
                    raise ValueError(f"Form fields generation failed: Only {len(form_fields_content)} chars generated (need 800+)")
            
            logger.info(f"✅ Form fields size OK: {len(form_fields_content)} chars")
            
            # 🔴 FIX D + FIX #2: Function-Level Enforcement (Check required functions are CALLED properly)
            # FIX #2: Search across ALL sections, not just CRUD
            logger.info("🔍 Validating required functions across ALL sections...")
            
            # Combine all sections for comprehensive check
            all_code = '\n'.join([
                sections.get('VARIABLE_INIT_PHP', ''),
                sections.get('CRUD_LOGIC_PHP', ''),
                sections.get('AJAX_HANDLERS_PHP', ''),
                sections.get('FORM_FIELDS_HTML', ''),
                sections.get('ENTITY_JS', ''),
            ])
            
            # Check for actual function CALLS (not just mentions)
            # Core functions that MUST be present (somewhere)
            required_function_patterns = {
                'db_insert': r'db_insert\s*\(',
                'db_update': r'db_update\s*\(',
                'db_delete': r'db_delete\s*\(',
                'db_getRecord': r'db_getRecord\s*\(',
                'funStartTran': r'funStartTran\s*\(',
                'funEndTran': r'funEndTran\s*\('
            }
            
            # Functions that should be present but we WARN not BLOCK
            optional_function_patterns = {
                'getrows': r'getrows\s*\(',
                'getvalue': r'getvalue\s*\('
            }
            
            missing_critical = []
            for func_name, pattern in required_function_patterns.items():
                if not re.search(pattern, all_code, re.IGNORECASE):
                    missing_critical.append(func_name)
            
            missing_optional = []
            for func_name, pattern in optional_function_patterns.items():
                if not re.search(pattern, all_code, re.IGNORECASE):
                    missing_optional.append(func_name)
            
            if missing_critical:
                error_msg = f"🔥 MISSING CRITICAL FUNCTION CALLS: {', '.join(missing_critical)}"
                logger.error(error_msg)
                logger.warning(f"⚠️ FIX D: Checking for actual function CALLS across all sections")
                accumulated_errors.append(error_msg)
                accumulated_errors.append(f"MUST CALL (in any section): {', '.join(missing_critical)}")
                accumulated_errors.append("You MUST call these functions with proper syntax: function_name()")
                accumulated_errors.append("Example: db_insert('tblarea', $data); NOT just mentioning 'db_insert'")
                
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to missing function calls")
                    continue
                else:
                    raise ValueError(f"Controlled assembly failed: Missing required function calls: {', '.join(missing_critical)}")
            
            if missing_optional:
                logger.warning(f"⚠️ Missing optional functions (non-blocking): {', '.join(missing_optional)}")
                logger.warning(f"   These functions may be in AJAX or VARIABLE sections - will check at assembly")
            
            logger.info("✅ All required functions properly called in generated sections")
            
            # ✅ FIX 2: Add hard completeness check
            if not self._is_complete_generation(generated_code):
                error_msg = "❌ Incomplete generation detected - missing required sections"
                logger.error(error_msg)
                accumulated_errors.append(error_msg)
                accumulated_errors.append("Missing: db_insert, db_update, db_delete, $.ajax, formValidation, or <form>")
                
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to incomplete generation")
                    continue
                else:
                    raise Exception("Incomplete generation - retry required")
            
            logger.info("✅ Completeness check passed - all required sections present")
            
            # Assemble code
            logger.info("🔧 STEP 4: Assembling final file...")
            try:
                assembled_code = self.code_assembler.assemble(generated_code, contract, fixed_parts)
                last_assembled_code = assembled_code
                logger.info(f"✅ Assembled: {len(assembled_code)} chars")
            except ValueError as e:
                # Template merge failed
                logger.error(f"❌ Assembly failed: {e}")
                accumulated_errors.append(str(e))
                
                if retry_count < max_retries:
                    retry_count += 1
                    logger.warning(f"⚠️ Triggering retry {retry_count}/{max_retries} due to assembly failure")
                    continue
                else:
                    logger.error(f"❌ Max retries ({max_retries}) reached. Raising assembly error.")
                    raise
            
            # Validate
            logger.info("🔍 STEP 5: Validating...")
            is_valid, errors, scores = self.enterprise_validator.validate(
                assembled_code, plan['validation_contract']
            )
            
            overall_score = scores.get('overall', 0)
            logger.info(f"{'✅' if is_valid else '❌'} Validation: {overall_score}% ({len(errors)} errors)")
            
            self.last_validation_result = {'is_valid': is_valid, 'errors': errors, 'scores': scores}
            
            # Accept only when enterprise validation passes.
            if is_valid:
                logger.info("✅ Controlled generation accepted after full validation pass")
                logger.info("=" * 80)
                return assembled_code
            
            # If we've exhausted retries, fail hard instead of returning invalid code.
            if retry_count >= max_retries:
                error_preview = '; '.join(errors[:8]) if errors else 'unknown validation failure'
                raise ValueError(
                    "Controlled assembly failed validation after "
                    f"{max_retries + 1} attempts (score={overall_score}). Errors: {error_preview}"
                )
            
            # Validation failed, prepare for retry
            for error in errors:
                normalized_error = _normalize_retry_error(error)
                if normalized_error:
                    accumulated_errors.append(normalized_error)
            retry_count += 1
            logger.warning(f"⚠️ Validation failed (score: {overall_score}%). Triggering retry {retry_count}/{max_retries}")
        
        # Should never reach here; fail closed if loop exits unexpectedly.
        raise ValueError(
            "Controlled assembly exited without a validated output. "
            f"Last validation: {self.last_validation_result}"
        )
    
    async def _generate_inline_php_file_legacy(
        self,
        intent: Dict,
        sql_schema: str,
        company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        user_request: str = "",
        validation_errors: List = None,
        max_retries: int = 2
    ) -> str:
        """
        Generate complete inline PHP+HTML file with validation
        
        Returns: Complete PHP file content with embedded HTML/JS
        Validates that company functions are used, regenerates if needed
        """
        
        logger.info("ðŸš€ Generating INLINE PHP+HTML file (company style)")
        self.last_generation_metadata = {}
        self.last_validation_result = {}
        self._init_fallback_usage_tracker()
        
        # ðŸ†• DEBUG: Log what user_request we received
        logger.info(f"ðŸ“ DEBUG: user_request parameter = '{user_request}'")
        logger.info(f"ðŸ“ DEBUG: user_request length = {len(user_request)}")
        
        # ðŸ†• Detect user requirements from user_request parameter
        # Fallback to intent fields if user_request is empty
        if not user_request:
            user_request = intent.get('form_title', '')
            logger.warning(f"âš ï¸ user_request was empty, using form_title: '{user_request}'")
        
        user_request_lower = user_request.lower()
        logger.info(f"ðŸ“ DEBUG: user_request_lower = '{user_request_lower[:200]}...'")  # First 200 chars
        user_requirements = self._detect_user_requirements(user_request)
        
        logger.info(f"ðŸ” User Requirements Detected (Enhanced with Synonyms):")
        logger.info(f"   Dropdown: {user_requirements['wants_dropdown']}")
        logger.info(f"   Keyboard: {user_requirements['wants_keyboard']}")
        logger.info(f"   Validation: {user_requirements['wants_formvalidation']}")
        logger.info(f"   Select2: {user_requirements['wants_select2']}")
        logger.info(f"   Grid: {user_requirements['wants_grid']}")
        logger.info(f"   Chart: {user_requirements['wants_chart']}")
        
        # âœ… FIXED ISSUE #4: Enhanced verification logging
        logger.info(f"ðŸ“ Company Examples Length: {len(company_examples)} chars")
        logger.info(f"ðŸ“ Analyzed Patterns Keys: {list(analyzed_patterns.keys()) if analyzed_patterns else 'None'}")
        
        strict_company_validation = False
        strict_validation_reason = "insufficient_retrieval_context"
        if company_examples:
            # Count how many PHP examples are included
            example_count = company_examples.count("### Example")
            logger.info(f"ðŸ“ Number of PHP Examples: {example_count}")
            
            # âœ… NEW: Verify examples contain critical patterns
            logger.info(f"ðŸ“ Verifying company examples contain critical patterns:")
            
            # Check for company functions
            has_db_insert = 'db_insert' in company_examples
            has_db_update = 'db_update' in company_examples
            has_db_delete = 'db_delete' in company_examples
            has_getrows = 'getrows' in company_examples
            has_getvalue = 'getvalue' in company_examples
            
            logger.info(f"   - db_insert: {'âœ… Found' if has_db_insert else 'âŒ Missing'}")
            logger.info(f"   - db_update: {'âœ… Found' if has_db_update else 'âŒ Missing'}")
            logger.info(f"   - db_delete: {'âœ… Found' if has_db_delete else 'âŒ Missing'}")
            logger.info(f"   - getrows: {'âœ… Found' if has_getrows else 'âŒ Missing'}")
            logger.info(f"   - getvalue: {'âœ… Found' if has_getvalue else 'âŒ Missing'}")
            
            # Check for session management
            has_session_start = 'session_start' in company_examples
            has_session_vars = '$_SESSION' in company_examples
            logger.info(f"   - session_start: {'âœ… Found' if has_session_start else 'âŒ Missing'}")
            logger.info(f"   - $_SESSION usage: {'âœ… Found' if has_session_vars else 'âŒ Missing'}")
            
            # Check for AJAX patterns
            has_ajax = ('$.ajax' in company_examples or '$.post' in company_examples or 
                       '$.ajaxSetup' in company_examples or 'ajaxSetup' in company_examples)
            has_getmaxid = 'GetMaxID' in company_examples or 'getMaxId' in company_examples
            logger.info(f"   - AJAX ($.ajax/$.post): {'âœ… Found' if has_ajax else 'âŒ Missing'}")
            logger.info(f"   - GetMaxID pattern: {'âœ… Found' if has_getmaxid else 'âŒ Missing'}")
            
            # Check for validation patterns
            has_formvalidation = 'formValidation' in company_examples
            has_checkKeycode = 'checkKeycode' in company_examples
            logger.info(f"   - formValidation: {'âœ… Found' if has_formvalidation else 'âŒ Missing'}")
            logger.info(f"   - checkKeycode (keyboard): {'âœ… Found' if has_checkKeycode else 'âŒ Missing'}")
            
            # Check for chart integration
            has_chart = 'INSERT INTO chart' in company_examples
            logger.info(f"   - Chart integration: {'âœ… Found' if has_chart else 'âŒ Missing'}")

            essential_hits = sum([
                has_db_insert,
                has_db_update,
                has_db_delete,
                has_getrows,
                has_getvalue,
                has_session_start,
                has_session_vars,
                has_getmaxid,
            ])
            strict_company_validation = self._should_enforce_strict_company_validation(
                company_examples=company_examples,
                analyzed_patterns=analyzed_patterns or {},
                example_count=example_count,
                essential_hits=essential_hits
            )
            strict_validation_reason = (
                "retrieval_context_strong"
                if strict_company_validation
                else f"retrieval_context_weak(hits={essential_hits}, examples={example_count}, chars={len(company_examples)})"
            )
            logger.info(
                f"ðŸ›¡️ Strict company validation mode: "
                f"{'ENABLED' if strict_company_validation else 'RELAXED'} ({strict_validation_reason})"
            )
            
            # âœ… NEW: Show sample of first example to verify it's complete
            if example_count > 0:
                first_example_start = company_examples.find("### Example 1")
                if first_example_start != -1:
                    # Find the end of first example (next example or end of string)
                    second_example_start = company_examples.find("### Example 2", first_example_start + 1)
                    if second_example_start != -1:
                        first_example = company_examples[first_example_start:second_example_start]
                    else:
                        first_example = company_examples[first_example_start:first_example_start + 2000]
                    
                    logger.info(f"ðŸ“ First Example Length: {len(first_example)} chars")
                    logger.info(f"ðŸ“ First Example Preview (first 300 chars):\n{first_example[:300]}")
            
            # Show first 500 chars of examples to verify full code is included
            if len(company_examples) > 500:
                logger.info(f"ðŸ“ Overall Examples Preview (first 500 chars):\n{company_examples[:500]}")
        else:
            logger.warning(f"âš ï¸ No company examples provided to LLM!")
            strict_company_validation = False
            strict_validation_reason = "no_company_examples"

        
        # âœ… PHASE 1: EXTRACT PATTERNS FROM COMPANY EXAMPLES (100% DYNAMIC)
        logger.info("=" * 80)
        logger.info("ðŸ” PHASE 1: Extracting patterns from company examples...")
        logger.info("=" * 80)
        
        # âœ… PLAN A: Extract FIXED parts from company example (CSS, scripts, HTML wrapper)
        # Extract FULL file path from company_examples to read full file if needed
        # Path may span multiple lines (long Windows paths get wrapped)
        example_file_path = ""
        
        file_path_match = re.search(r'\*\*File:\*\*\s*([^\r\n]+?\.php)', company_examples)
        if not file_path_match:
            file_path_match = re.search(r'File:\s*([^\r\n]+?\.php)', company_examples)

        raw_example_path = file_path_match.group(1).strip() if file_path_match else ""
        request_metadata = self._extract_explicit_request_metadata(user_request or '')
        if request_metadata.get('has_entity_conflict'):
            logger.warning(
                "Prompt entity conflict detected. Using explicit table/file metadata over natural-language entity: "
                f"'{request_metadata.get('primary_entity')}' -> '{request_metadata.get('module_entity')}'"
            )

        fallback_entity_name = (
            intent.get('database', {}).get('table_name', '')
            .replace('tbl', '')
            .replace('_master', '')
            .title()
        )
        preferred_entity_name = request_metadata.get('effective_entity') or fallback_entity_name
        entity_hints = self._extract_entity_hints_from_request(user_request)
        if preferred_entity_name and preferred_entity_name not in entity_hints:
            entity_hints = [preferred_entity_name] + entity_hints

        example_file_path = self._resolve_example_file_path(
            raw_example_path,
            preferred_entity_name,
            entity_hints=entity_hints
        )

        if example_file_path:
            if raw_example_path and os.path.normpath(raw_example_path) != os.path.normpath(example_file_path):
                logger.info(f"ðŸ“– Resolved example file into current codebase: {example_file_path}")
            elif raw_example_path:
                logger.info(f"ðŸ“– Using example file from prompt metadata: {example_file_path}")
            elif preferred_entity_name:
                logger.info(f"ðŸ“– Found example file via entity match: {example_file_path}")
            else:
                logger.info(f"ðŸ“– Using first frm*.php file as fallback: {example_file_path}")
        
        fixed_parts = self._extract_fixed_parts_from_example(company_examples, example_file_path)
        source_company_examples = fixed_parts.get('source_content') or company_examples
        if len(source_company_examples) > len(company_examples):
            logger.info(
                f"📖 Using full example content for pattern detection: "
                f"{len(source_company_examples):,} chars (was {len(company_examples):,})"
            )
        
        # ✅ PHASE 2.1: Use RequestSchemaParser first, fallback to heuristic extraction
        naming_metadata = self._extract_canonical_form_metadata_with_parser(
            user_request=user_request,
            company_example=source_company_examples, 
            example_file_path=example_file_path
        )

        explicit_table_name = (request_metadata.get('table_name') or '').strip()
        explicit_file_name = os.path.basename((request_metadata.get('file_name') or '').strip())
        explicit_title = (request_metadata.get('title') or '').strip()
        explicit_case_type = (request_metadata.get('case_type') or '').strip()
        effective_entity_name = (request_metadata.get('effective_entity') or '').strip()

        if explicit_table_name:
            naming_metadata['table_name'] = explicit_table_name
        if explicit_file_name:
            naming_metadata['file_name'] = explicit_file_name
            if explicit_file_name.lower().startswith('frm') and explicit_file_name.lower().endswith('.php'):
                naming_metadata['feature_name'] = explicit_file_name[3:-4]
        if explicit_title:
            naming_metadata['title'] = explicit_title
        if explicit_case_type:
            naming_metadata['case_type'] = explicit_case_type
        elif explicit_title and not naming_metadata.get('case_type'):
            naming_metadata['case_type'] = explicit_title
        if not naming_metadata.get('feature_name') and effective_entity_name:
            cleaned_feature_name = re.sub(r'[^A-Za-z0-9_]', '', effective_entity_name).strip('_')
            if cleaned_feature_name:
                naming_metadata['feature_name'] = cleaned_feature_name

        if not naming_metadata.get('title'):
            feature_for_title = naming_metadata.get('feature_name') or effective_entity_name
            if feature_for_title:
                naming_metadata['title'] = str(feature_for_title).replace('_', ' ').strip().title()
        if not naming_metadata.get('case_type'):
            naming_metadata['case_type'] = naming_metadata.get('title', '')
        if effective_entity_name:
            naming_metadata['effective_entity'] = effective_entity_name
        elif not naming_metadata.get('effective_entity'):
            naming_metadata['effective_entity'] = (
                naming_metadata.get('feature_name')
                or naming_metadata.get('title')
                or naming_metadata.get('case_type')
                or fallback_entity_name
            )
        effective_compact = re.sub(
            r'[^a-z0-9]',
            '',
            str(naming_metadata.get('effective_entity') or '').lower()
        )
        if effective_compact.endswith('master') and len(effective_compact) > 6:
            effective_compact = effective_compact[:-6]
        naming_metadata['effective_entity_compact'] = effective_compact

        # ✅ PHASE 1.2: FAIL-FAST VALIDATION - Ensure canonical naming is never blank
        validation_errors = []
        if not naming_metadata.get('table_name'):
            validation_errors.append("table_name is empty - cannot generate code without table name")
        if not naming_metadata.get('file_name'):
            validation_errors.append("file_name is empty - cannot generate code without file name")
        if not naming_metadata.get('title'):
            validation_errors.append("title is empty - cannot generate code without title")
        
        if validation_errors:
            error_msg = "❌ CANONICAL NAMING VALIDATION FAILED - Required metadata is missing:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            logger.error(error_msg)
            logger.error(f"📋 Current naming_metadata: {naming_metadata}")
            logger.error(f"📋 User request (first 500 chars): {user_request[:500]}")
            raise ValueError(error_msg)
        
        logger.info(f"✅ Canonical naming validated:")
        logger.info(f"   - table_name: {naming_metadata.get('table_name')}")
        logger.info(f"   - file_name: {naming_metadata.get('file_name')}")
        logger.info(f"   - title: {naming_metadata.get('title')}")
        logger.info(f"   - case_type: {naming_metadata.get('case_type')}")

        self.last_generation_metadata = naming_metadata.copy()
        self.last_generation_metadata['strict_company_validation'] = strict_company_validation
        self.last_generation_metadata['strict_validation_reason'] = strict_validation_reason

        # Extract field names from company code AND user request
        company_fields = self._extract_field_names_from_example(source_company_examples, user_request)
        requested_grid = company_fields.get('detail_grid', {})
        
        # Detect hierarchical code pattern
        hierarchy_pattern = self._detect_hierarchical_pattern(source_company_examples, user_request)
        
        # Detect related tables for pre-delete checks
        table_name = naming_metadata.get('table_name') or intent.get('database', {}).get('table_name', 'example')
        entity_name = naming_metadata.get('feature_name') or table_name.replace('tbl', '').replace('_master', '').title()
        related_tables = self._detect_related_tables(source_company_examples, entity_name)
        
        # ✅ Get primary key from company fields
        primary_key = (company_fields or {}).get('primary_key') or intent.get('database', {}).get('primary_key') or 'Code'
        
        # ✅ NEW FIX: Also extract dependencies from user request if specified
        # User can specify dependencies like: "Dependencies: payroll.Employee_Code, attendance.Employee_Code"
        user_dependencies = self._extract_dependencies_from_user_request(user_request, primary_key)
        if user_dependencies:
            existing_tables = {rel.get('table', '').lower() for rel in related_tables}
            for dep in user_dependencies:
                if dep.get('table', '').lower() not in existing_tables:
                    related_tables.append(dep)
            logger.info(f"✅ Added {len(user_dependencies)} user-specified dependencies to pre-delete checks")
        
        # Detect cascading dropdown logic
        cascading_logic = self._detect_cascading_dropdown_logic(source_company_examples)
        
        # âœ… ISSUE #8 FIX: Detect grid/detail table pattern
        grid_pattern = self._detect_grid_pattern(source_company_examples, entity_name, requested_grid)
        self.last_generation_metadata.update({
            'table_name': table_name,
            'feature_name': entity_name,
            'title': naming_metadata.get('title') or entity_name.replace('_', ' '),
            'file_name': naming_metadata.get('file_name') or f"frm{entity_name}.php",
            'case_type': naming_metadata.get('case_type') or naming_metadata.get('title') or entity_name.replace('_', ' '),
            'requested_grid': requested_grid,
            'request_table_name': explicit_table_name,
            'request_file_name': explicit_file_name,
            'request_title': explicit_title,
            'request_case_type': explicit_case_type,
            'request_effective_entity': effective_entity_name,
            'request_entity_conflict': bool(request_metadata.get('has_entity_conflict')),
        })
        
        logger.info("=" * 80)
        logger.info("âœ… PHASE 1 EXTRACTION COMPLETE:")
        logger.info(f"   Fields: {len(company_fields['form_fields'])} detected")
        logger.info(f"   Hierarchical: {hierarchy_pattern['is_hierarchical']}")
        logger.info(f"   Cascading: {cascading_logic['has_cascading']}")
        logger.info(f"   Related tables: {len(related_tables)}")
        logger.info(f"   Grid pattern: {grid_pattern['has_grid']} ({len(grid_pattern['grid_fields'])} fields)")
        logger.info("=" * 80)
        
        # Keep full example for extraction/validation, but cap LLM context size for reliability.
        prompt_company_examples = source_company_examples
        max_prompt_example_chars = get_int_setting(
            'CODEGEN_PROMPT_EXAMPLE_MAX_CHARS',
            'CODEGEN_PROMPT_EXAMPLE_MAX_CHARS',
            20000,
            min_value=8000,
            max_value=200000
        )
        if len(prompt_company_examples) > max_prompt_example_chars:
            head_len = max_prompt_example_chars // 2
            tail_len = max_prompt_example_chars - head_len
            prompt_company_examples = (
                prompt_company_examples[:head_len]
                + "\n\n/* ... trimmed for prompt stability ... */\n\n"
                + prompt_company_examples[-tail_len:]
            )
            logger.info(
                f"ðŸ“‰ Trimmed company examples for prompt: "
                f"{len(source_company_examples):,} -> {len(prompt_company_examples):,} chars"
            )

        controlled_framework_ready = bool(
            fixed_parts.get('html_head') or
            fixed_parts.get('body_start') or
            fixed_parts.get('body_end') or
            self._template
        )
        require_controlled_assembly = self._bool_setting('CODEGEN_REQUIRE_CONTROLLED_ASSEMBLY', True)
        self.last_generation_metadata['controlled_framework_ready'] = controlled_framework_ready
        if require_controlled_assembly and not controlled_framework_ready:
            raise ValueError(
                "Controlled assembly requires fixed company framework blocks. "
                "Company framework could not be loaded from the indexed codebase."
            )

        controlled_assembly_requested = self._should_use_controlled_assembly(
            user_request=user_request,
            request_metadata=request_metadata,
            fixed_parts=fixed_parts
        )
        self.last_generation_metadata['controlled_assembly_requested'] = controlled_assembly_requested
        if require_controlled_assembly and not controlled_assembly_requested:
            raise ValueError(
                "Strict company mode requires controlled assembly. "
                "Uncontrolled full-file generation is disabled."
            )
        if controlled_assembly_requested:
            return await self._generate_controlled_inline_php_file(
                intent=intent,
                sql_schema=sql_schema,
                source_company_examples=prompt_company_examples,
                analyzed_patterns=analyzed_patterns,
                standards=standards,
                user_request=user_request,
                company_fields=company_fields,
                hierarchy_pattern=hierarchy_pattern,
                related_tables=related_tables,
                cascading_logic=cascading_logic,
                grid_pattern=grid_pattern,
                fixed_parts=fixed_parts,
                naming_metadata=self.last_generation_metadata,
                validation_errors=validation_errors,
                max_retries=max_retries
            )

        compact_template_chars = get_int_setting(
            'CODEGEN_COMPACT_TEMPLATE_MAX_CHARS',
            'CODEGEN_COMPACT_TEMPLATE_MAX_CHARS',
            12000,
            min_value=2000,
            max_value=60000
        )
        compact_template_source = prompt_company_examples[:compact_template_chars]
        compact_prompt = self._build_compact_generation_prompt(
            intent=intent,
            user_request=user_request,
            company_fields=company_fields,
            naming_metadata=self.last_generation_metadata,
            hierarchy_pattern=hierarchy_pattern,
            related_tables=related_tables,
            cascading_logic=cascading_logic,
            grid_pattern=grid_pattern,
            template_code=compact_template_source
        )

        use_compact_first_prompt = self._bool_setting('CODEGEN_REFUSAL_SAFE_FIRST_ATTEMPT', True)
        strict_generation_request = bool(
            re.search(
                r'fallback\s+usage\s+must\s+be\s*<=?\s*1%|strict\s+mode|canonical\s+names?\s+must\s+match\s+exactly|required\s+company\s+patterns',
                user_request or '',
                re.IGNORECASE
            )
        )
        explicit_request_metadata = bool(
            re.search(
                r'\b(file\s*name|table|title|primary\s*key|fields?)\s*:',
                user_request or '',
                re.IGNORECASE
            )
        )
        if use_compact_first_prompt and (strict_generation_request or explicit_request_metadata):
            use_compact_first_prompt = False
            logger.info(
                "🧭 Forcing full prompt mode for strict/explicit enterprise request "
                "(improves company-shell completeness and reduces deterministic attachment)."
            )
        prebuild_full_prompt = self._bool_setting('CODEGEN_PREBUILD_FULL_PROMPT', False)
        full_prompt = ""
        if (not use_compact_first_prompt) or prebuild_full_prompt:
            # Full prompt is large; only build it when explicitly needed.
            full_prompt = self._build_inline_prompt(
                intent=intent,
                sql_schema=sql_schema,
                company_examples=prompt_company_examples,
                analyzed_patterns=analyzed_patterns,
                standards=standards,
                user_requirements=user_requirements,
                company_fields=company_fields,
                hierarchy_pattern=hierarchy_pattern,
                related_tables=related_tables,
                cascading_logic=cascading_logic,
                grid_pattern=grid_pattern,
                naming_metadata=self.last_generation_metadata
            )

        initial_prompt_mode = 'compact_safe_first' if use_compact_first_prompt else 'full'
        prompt = compact_prompt if use_compact_first_prompt else (full_prompt or compact_prompt)
        
        # ðŸ†• VERIFY: Log prompt size
        # Config-driven retry count for inline generation.
        max_retries = get_int_setting(
            'CODEGEN_INLINE_MAX_RETRIES',
            'CODEGEN_INLINE_MAX_RETRIES',
            max_retries if isinstance(max_retries, int) and max_retries > 0 else 3,
            min_value=1,
            max_value=6
        )
        llm_attempts_made = 0
        refusal_count = 0
        llm_call_failures = 0

        self.last_generation_metadata.update({
            'max_attempts': max_retries,
            'attempts_made': 0,
            'refusal_count': 0,
            'llm_call_failures': 0,
            'model_chain': self.model_chain,
            'attempt_models': [],
            'initial_prompt_mode': initial_prompt_mode,
            'full_prompt_chars': len(full_prompt),
            'initial_prompt_chars': len(prompt),
            'attempt_prompt_chars': []
        })
        
        if full_prompt:
            logger.info(f"ðŸ“ Full Prompt Size: {len(full_prompt)} characters")
        else:
            logger.info("ðŸ“ Full Prompt Size: skipped (compact-first mode)")
        logger.info(f"ðŸ“ Initial Prompt Strategy: {initial_prompt_mode} ({len(prompt)} chars)")
        max_prompt_chars = get_int_setting(
            'CODEGEN_PROMPT_MAX_CHARS',
            'CODEGEN_PROMPT_MAX_CHARS',
            28000,
            min_value=12000,
            max_value=300000
        )
        prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label=f'{initial_prompt_mode} prompt')
        
        # Generate with validation and retry logic
        # âœ… ISSUE #8 FIX: Track previous attempts for better feedback
        previous_attempts = []
        
        for attempt in range(max_retries):
            logger.info(f"ðŸ”„ Generation attempt {attempt + 1}/{max_retries}")
            self._init_fallback_usage_tracker()
            llm_attempts_made = attempt + 1
            self.last_generation_metadata['attempts_made'] = llm_attempts_made
            attempt_prompt_chars = self.last_generation_metadata.get('attempt_prompt_chars', [])
            attempt_prompt_chars.append(len(prompt))
            self.last_generation_metadata['attempt_prompt_chars'] = attempt_prompt_chars
            attempt_model = self._effective_model_name(self._model_for_attempt(attempt))
            attempt_models = self.last_generation_metadata.get('attempt_models', [])
            attempt_models.append(attempt_model)
            self.last_generation_metadata['attempt_models'] = attempt_models
            logger.info(f"ðŸ¤– Model for attempt {attempt + 1}: {attempt_model}")
             
            # Generate
            try:
                llm_client = self._get_llm_client(attempt_model)
                generation_messages = self._build_generation_messages(prompt, user_request=user_request)
                result = await llm_client.ainvoke(generation_messages)
            except Exception as llm_error:
                logger.error(f"âŒ LLM call failed on attempt {attempt + 1}/{max_retries}: {llm_error}")
                llm_call_failures += 1
                self.last_generation_metadata['llm_call_failures'] = llm_call_failures

                if attempt < max_retries - 1:
                    continue

                template_candidate = self._extract_template_candidate_code(source_company_examples)
                if template_candidate:
                    if strict_contract_mode:
                        self.last_generation_metadata['strict_fallback_blocked'] = True
                        self.last_generation_metadata['strict_fallback_reason'] = (
                            'company_template_connection_error'
                        )
                        raise ValueError(
                            "Strict contract mode blocks deterministic company-template fallback "
                            "after LLM connection failure."
                        )
                    template_validation = self._validate_company_functions(
                        template_candidate,
                        user_request,
                        hierarchy_pattern,
                        company_fields=company_fields,
                        grid_pattern=grid_pattern,
                        naming_metadata=self.last_generation_metadata
                    )
                    if template_validation.get('valid'):
                        logger.warning("âš ï¸ Using deterministic company-template fallback after LLM connection failure")
                        template_candidate = self._auto_attach_shared_components(
                            template_candidate,
                            fixed_parts=fixed_parts,
                            user_request=user_request
                        )
                        self._record_fallback_usage(
                            'company_template',
                            'deterministic_company_template_fallback_connection_error',
                            chars_added=len(template_candidate)
                        )
                        self._finalize_fallback_usage(template_candidate)
                        self.last_validation_result = template_validation.copy()
                        self.last_generation_metadata['fallback_mode'] = 'company_template_connection_error'
                        self.last_generation_metadata['attempts_made'] = llm_attempts_made
                        self.last_generation_metadata['refusal_count'] = refusal_count
                        self.last_generation_metadata['llm_call_failures'] = llm_call_failures
                        self.last_generation_metadata['output_length'] = len(template_candidate)
                        return template_candidate

                raise

            llm_content = result.content if isinstance(result.content, str) else str(result.content)
            if self._is_refusal_response(llm_content):
                refusal_count += 1
                self.last_generation_metadata['refusal_count'] = refusal_count
                logger.warning(
                    f"âš ï¸ LLM refusal detected on attempt {attempt + 1}/{max_retries}: "
                    f"{llm_content[:120].replace(chr(10), ' ')}"
                )
                previous_attempts.append({
                    'attempt_number': attempt + 1,
                    'code_snippet': llm_content[:500],
                    'validation_result': {
                        'required_blockers': [{
                            'key': 'llm_refusal',
                            'message': 'Model refused to generate requested code'
                        }],
                        'missing_functions': [],
                        'found_functions': []
                    }
                })

                if attempt < max_retries - 1:
                    refusal_prompt_chars = get_int_setting(
                        'CODEGEN_REFUSAL_PROMPT_MAX_CHARS',
                        'CODEGEN_REFUSAL_PROMPT_MAX_CHARS',
                        15000,
                        min_value=6000,
                        max_value=120000
                    )
                    compact_examples = prompt_company_examples
                    if len(compact_examples) > refusal_prompt_chars:
                        compact_examples = compact_examples[:refusal_prompt_chars]
                        logger.info(
                            f"ðŸ“‰ Rebuilding prompt after refusal with compact examples: "
                            f"{len(prompt_company_examples):,} -> {len(compact_examples):,} chars"
                        )

                    prompt = self._build_refusal_recovery_prompt(
                        intent=intent,
                        user_request=user_request,
                        company_fields=company_fields,
                        naming_metadata=self.last_generation_metadata,
                        template_code=compact_examples
                    )
                    prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='refusal retry prompt')
                    continue

                raise ValueError(
                    f"LLM refused to generate ERP code after {max_retries} attempts."
                )
            
            # Extract code
            inline_code = self._extract_php_code(result.content)
            inline_code = self._auto_attach_shared_components(
                inline_code,
                fixed_parts=fixed_parts,
                user_request=user_request
            )
            
            # Validate company functions are used
            validation_result = self._validate_company_functions(
                inline_code,
                user_request,
                hierarchy_pattern,
                company_fields=company_fields,
                grid_pattern=grid_pattern,
                naming_metadata=self.last_generation_metadata
            )

            # Deterministic recovery for near-valid outputs: inject missing keyboard/FormValidation scaffold.
            if not validation_result.get('valid'):
                blocker_keys = {
                    str(blocker.get('key'))
                    for blocker in (validation_result.get('required_blockers') or [])
                    if blocker
                }
                repairable_blockers = {'keyboard_navigation', 'form_validation'}
                if blocker_keys and blocker_keys.issubset(repairable_blockers):
                    repaired_code = self._inject_keyboard_formvalidation_scaffold(
                        inline_code,
                        company_fields,
                        user_request=user_request
                    )
                    if repaired_code != inline_code:
                        scaffold_added = max(0, len(repaired_code) - len(inline_code))
                        if scaffold_added:
                            self._record_fallback_usage(
                                'company_template',
                                'auto_inject_keyboard_formvalidation_scaffold',
                                chars_added=scaffold_added
                            )
                        logger.info(
                            "🛠️ Applied deterministic keyboard/formValidation scaffold "
                            f"for blockers: {', '.join(sorted(blocker_keys))}"
                        )
                        inline_code = repaired_code
                        validation_result = self._validate_company_functions(
                            inline_code,
                            user_request,
                            hierarchy_pattern,
                            company_fields=company_fields,
                            grid_pattern=grid_pattern,
                            naming_metadata=self.last_generation_metadata
                        )
            self.last_validation_result = validation_result.copy()
            
            if validation_result['valid']:
                logger.info(f"âœ… Generated inline PHP file: {len(inline_code)} characters")
                logger.info(f"âœ… Validation PASSED - Using company functions: {validation_result['found_functions']}")
                logger.info(f"âœ… LLM received COMPLETE company examples and analyzed patterns")

                # Re-run deterministic shared-component pass once more on successful output.
                final_code = self._auto_attach_shared_components(
                    inline_code,
                    fixed_parts=fixed_parts,
                    user_request=user_request
                )
                if final_code != inline_code:
                    logger.info(
                        "🧩 Shared company components auto-attached on finalization "
                        f"({len(inline_code)} -> {len(final_code)} chars)"
                    )
                inline_code = final_code

                # Final validator pass after deterministic attachment.
                validation_result = self._validate_company_functions(
                    inline_code,
                    user_request,
                    hierarchy_pattern,
                    company_fields=company_fields,
                    grid_pattern=grid_pattern,
                    naming_metadata=self.last_generation_metadata
                )
                self.last_validation_result = validation_result.copy()
                if not validation_result.get('valid'):
                    logger.warning("⚠️ Final deterministic attachment introduced unresolved blockers; retrying generation")
                    previous_attempts.append({
                        'attempt_number': attempt + 1,
                        'code_snippet': inline_code[:500],
                        'validation_result': validation_result
                    })
                    if attempt < max_retries - 1:
                        continue
                    missing_str = ', '.join(validation_result.get('missing_functions', []))
                    raise ValueError(f"Inline generation failed final validation after deterministic attachment: {missing_str}")

                fallback_summary = self._finalize_fallback_usage(inline_code)
                logger.info(
                    "📊 Fallback usage summary: "
                    f"generic={fallback_summary.get('generic_ratio_percent', 0)}%, "
                    f"company_template_reuse={fallback_summary.get('company_template_ratio_percent', 0)}%"
                )

                enforce_fallback_budget = self._bool_setting('CODEGEN_ENFORCE_FALLBACK_BUDGET', True)
                if enforce_fallback_budget and not fallback_summary.get('generic_budget_passed', True):
                    budget_message = (
                        "Generic fallback budget exceeded: "
                        f"{fallback_summary.get('generic_ratio_percent')}% > "
                        f"{fallback_summary.get('generic_budget_percent')}% "
                        "(target <= 1%)."
                    )
                    logger.error(f"❌ {budget_message}")
                    if attempt < max_retries - 1:
                        previous_attempts.append({
                            'attempt_number': attempt + 1,
                            'code_snippet': inline_code[:500],
                            'validation_result': {
                                'required_blockers': [{
                                    'key': 'generic_fallback_budget',
                                    'message': budget_message
                                }],
                                'missing_functions': validation_result.get('missing_functions', []),
                                'found_functions': validation_result.get('found_functions', [])
                            }
                        })
                        continue
                    raise ValueError(budget_message)

                self.last_generation_metadata['attempts_made'] = llm_attempts_made
                self.last_generation_metadata['refusal_count'] = refusal_count
                self.last_generation_metadata['llm_call_failures'] = llm_call_failures
                self.last_generation_metadata['output_length'] = len(inline_code)
                return inline_code
            else:
                logger.warning(f"âš ï¸ Validation FAILED - Generated code did not meet required blockers")
                logger.warning(f"   Found: {validation_result['found_functions']}")
                logger.warning(f"   Missing: {validation_result['missing_functions']}")
                logger.warning(f"   Forbidden: {validation_result['forbidden_functions']}")
                if validation_result.get('required_blockers'):
                    logger.warning(
                        "   Blockers: %s",
                        ', '.join(blocker.get('key', '?') for blocker in validation_result.get('required_blockers', []))
                    )
                
                # âœ… ISSUE #8 FIX: Store failed attempt with specific errors
                previous_attempts.append({
                    'attempt_number': attempt + 1,
                    'code_snippet': inline_code[:500],  # First 500 chars for context
                    'validation_result': validation_result
                })
                
                if attempt < max_retries - 1:
                    logger.info(f"ðŸ”„ Retrying with SPECIFIC error feedback...")
                    
                    # Build Phase 1 error feedback
                    phase1_errors = []
                    if not validation_result.get('phase1_hierarchical_found', True):
                        phase1_errors.append("âŒ HIERARCHICAL CODE: Use MAX(RIGHT(Code,N)) pattern for parent-child codes")
                    if not validation_result.get('phase1_cascading_parent_param', True):
                        phase1_errors.append("âŒ CRITICAL: maxid() function MUST get parent dropdown value and pass it to AJAX call!")
                        phase1_errors.append("   Example: var SelectArea = document.getElementById('cboCountry').value;")
                        phase1_errors.append("   Then pass: {Action:'GetMaxID', SelectArea: SelectArea}")
                    
                    # âœ… ISSUE #3 FIX: Check Select2 integration and focus management consistently
                    if validation_result.get('user_requirements', {}).get('wants_select2', False):
                        if not validation_result.get('select2_pattern_found', False):
                            phase1_errors.append("âŒ SELECT2 INTEGRATION: Add Select2 assets, data-plugin='select2', and initialization for dropdown fields.")
                        elif validation_result.get('select2_focus_management_required', False):
                            if not validation_result.get('select2_close_events_found', False):
                                phase1_errors.append("âŒ SELECT2 CLOSE EVENTS: Add .on('select2:close') handlers for the requested cascading Select2 flow.")
                                phase1_errors.append("   Example: $('#Main_Area').on('select2:close', function() {")
                                phase1_errors.append("       setTimeout(function() {")
                                phase1_errors.append("           $('.select2-container-active').removeClass('select2-container-active');")
                                phase1_errors.append("           $(':focus').blur();")
                                phase1_errors.append("           $('#Sub_Area').focus();")
                                phase1_errors.append("           $('#Sub_Area').select2('open');")
                                phase1_errors.append("       }, 1);")
                                phase1_errors.append("   });")
                            elif not validation_result.get('select2_focus_chain_found', False):
                                phase1_errors.append("âš ï¸ SELECT2 FOCUS CHAIN: Add .select2('open') to auto-open the next requested dropdown.")
                                phase1_errors.append("   Example: $('#Sub_Area').select2('open');")
                    
                    # âœ… ISSUE #4 FIX: Check for COMPLETE Chart of Accounts integration
                    if validation_result.get('user_requirements', {}).get('wants_chart', False):
                        if not validation_result.get('chart_pattern_found', False):
                            phase1_errors.append("âŒ CHART OF ACCOUNTS: INCOMPLETE integration - Need ALL 4 operations!")
                            
                            # Show what's missing
                            if not validation_result.get('chart_has_acc_prefix', False):
                                phase1_errors.append("   âŒ MISSING: ACC_CUST constant (or ACC_SUPP, ACC_CODE)")
                            if not validation_result.get('chart_has_chartcode_var', False):
                                phase1_errors.append("   âŒ MISSING: chart code generation via ACC_CUST... or ACC_CUST.CustomerCode(...)")
                            if not validation_result.get('chart_has_insert', False):
                                phase1_errors.append("   âŒ MISSING: INSERT INTO chart (on Save)")
                                phase1_errors.append("      Example: mysql_query(\"INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL,COMP_CODE) VALUES ...\")")
                            if not validation_result.get('chart_has_update', False):
                                phase1_errors.append("   âŒ MISSING: UPDATE chart (on Update)")
                                phase1_errors.append("      Example: mysql_query(\"UPDATE chart SET ACC_NAME = '....' WHERE ACC_CODE= '....'\")")
                            if not validation_result.get('chart_has_delete', False):
                                phase1_errors.append("   âŒ MISSING: DELETE FROM chart (on Delete)")
                                phase1_errors.append("      Example: mysql_query(\"delete from chart where ACC_CODE = '....'\")")
                    
                    # âœ… ISSUE #6 FIX: Check for COMPLETE Pre-Delete Dependency Checks
                    if len(related_tables) > 0:  # Only check if related tables were detected
                        if not validation_result.get('predelete_pattern_found', False):
                            phase1_errors.append(f"âŒ PRE-DELETE CHECKS: INCOMPLETE - Need ALL 4 components for {len(related_tables)} related tables!")
                            
                            # Show what's missing
                            if not validation_result.get('predelete_has_delete_action', False):
                                phase1_errors.append("   âŒ MISSING: Delete action check")
                                phase1_errors.append("      Example: if($_REQUEST['action'] == 'Delete') {")
                            if not validation_result.get('predelete_has_dependency_check', False):
                                phase1_errors.append("   âŒ MISSING: Dependency check with getrows2/getrows")
                                phase1_errors.append("      Example: if (getrows2(\"tblsubarea\", \"Country_Code='\".$_REQUEST['major'].\"'\") >= 1) {")
                            if not validation_result.get('predelete_has_alert_message', False):
                                phase1_errors.append("   âŒ MISSING: Alert message for user")
                                phase1_errors.append("      Example: print \"<script>alert('This Area Exist in Sub Area... !!!');</script>\";")
                            if not validation_result.get('predelete_has_exit_statement', False):
                                phase1_errors.append("   âŒ MISSING: Exit statement to prevent deletion")
                                phase1_errors.append("      Example: exit;")

                    for blocker in validation_result.get('required_blockers', []):
                        blocker_key = blocker.get('key', 'required_pattern')
                        blocker_message = blocker.get('message', 'Required company pattern is missing')
                        phase1_errors.append(f"âŒ REQUIRED PATTERN [{blocker_key}]: {blocker_message}")

                        if blocker_key == 'getcostcenter_handler':
                            phase1_errors.append("   Example: if($_REQUEST['Action']=='GetCOSTCENTER') { ... echo $COSTID; exit; }")
                        elif blocker_key == 'requested_fields':
                            missing_fields = blocker.get('missing_fields', [])
                            if missing_fields:
                                phase1_errors.append(f"   Missing requested fields: {', '.join(missing_fields[:15])}")
                        elif blocker_key == 'requested_grid_fields':
                            missing_grid_fields = blocker.get('missing_grid_fields', [])
                            if missing_grid_fields:
                                phase1_errors.append(f"   Missing detail-grid fields: {', '.join(missing_grid_fields)}")
                        elif blocker_key == 'canonical_table_name':
                            phase1_errors.append(f"   Use exact table name: {self.last_generation_metadata.get('table_name', '')}")
                        elif blocker_key == 'canonical_file_name':
                            phase1_errors.append(f"   Use exact file/form name: {self.last_generation_metadata.get('file_name', '')}")
                        elif blocker_key == 'canonical_title':
                            phase1_errors.append(f"   Use exact title/CaseType: {self.last_generation_metadata.get('title', '')}")
                    
                    use_compact_validation_retry = self._bool_setting(
                        'CODEGEN_USE_COMPACT_VALIDATION_RETRY',
                        True
                    )
                    if use_compact_validation_retry:
                        prompt = self._build_validation_retry_prompt(
                            intent=intent,
                            user_request=user_request,
                            company_fields=company_fields,
                            naming_metadata=self.last_generation_metadata,
                            hierarchy_pattern=hierarchy_pattern,
                            related_tables=related_tables,
                            cascading_logic=cascading_logic,
                            grid_pattern=grid_pattern,
                            template_code=prompt_company_examples,
                            previous_attempts=previous_attempts,
                            phase1_errors=phase1_errors
                        )
                    else:
                        # Legacy fallback path: full strict prompt.
                        prompt = self._build_inline_prompt(
                            intent=intent,
                            sql_schema=sql_schema,
                            company_examples=prompt_company_examples,
                            analyzed_patterns=analyzed_patterns,
                            standards=standards,
                            strict_mode=True,
                            user_requirements=user_requirements,
                            previous_attempts=previous_attempts,
                            company_fields=company_fields,
                            hierarchy_pattern=hierarchy_pattern,
                            related_tables=related_tables,
                            cascading_logic=cascading_logic,
                            grid_pattern=grid_pattern,
                            naming_metadata=self.last_generation_metadata,
                            phase1_errors=phase1_errors
                        )
                    prompt = self._trim_prompt_to_limit(prompt, max_prompt_chars, label='validation retry prompt')
                else:
                    # âœ… ISSUE #10 FIX: Better error handling for failed validation
                    logger.error(f"âŒ Failed to generate valid code after {max_retries} attempts")
                    logger.error(f"   VALIDATION SUMMARY:")
                    logger.error(f"   - Found functions: {validation_result['found_functions']}")
                    logger.error(f"   - Missing functions: {validation_result['missing_functions']}")
                    logger.error(f"   - Forbidden functions: {validation_result['forbidden_functions']}")
                    logger.error(f"   - AJAX pattern: {validation_result.get('ajax_pattern_found', False)}")
                    logger.error(f"   - Comp_Code filter: {validation_result.get('compcode_pattern_found', False)}")
                    
                    # Handle both List[str] and List[Dict] formats for safety
                    missing_funcs = validation_result.get('missing_functions', [])
                    found_funcs = validation_result.get('found_functions', [])
                    
                    if missing_funcs and isinstance(missing_funcs[0], dict):
                        missing_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in missing_funcs])
                    else:
                        missing_str = ', '.join([str(f) for f in missing_funcs])
                    
                    if found_funcs and isinstance(found_funcs[0], dict):
                        found_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in found_funcs])
                    else:
                        found_str = ', '.join([str(f) for f in found_funcs])
                    
                    logger.error("âŒ Inline generation failed strict validation after all retries")
                    logger.error(f"   Missing functions: {missing_str}")
                    logger.error(f"   Found functions: {found_str}")

                    template_candidate = self._extract_template_candidate_code(source_company_examples)
                    if template_candidate:
                        fallback_entity_aligned = self._is_fallback_entity_aligned(
                            user_request=user_request,
                            naming_metadata=self.last_generation_metadata
                        )
                        if not fallback_entity_aligned:
                            logger.warning(
                                "⚠️ Skipping deterministic template fallback due entity mismatch "
                                f"(request entity does not match template '{self.last_generation_metadata.get('file_name', '')}')"
                            )
                            template_candidate = ""

                    if template_candidate:
                        if strict_contract_mode:
                            self.last_generation_metadata['strict_fallback_blocked'] = True
                            self.last_generation_metadata['strict_fallback_reason'] = (
                                'company_template_validation_failure'
                            )
                            raise ValueError(
                                "Strict contract mode blocks deterministic company-template fallback "
                                "after validation failure."
                            )
                        template_validation = self._validate_company_functions(
                            template_candidate,
                            user_request,
                            hierarchy_pattern,
                            company_fields=company_fields,
                            grid_pattern=grid_pattern,
                            naming_metadata=self.last_generation_metadata
                        )
                        if template_validation.get('valid'):
                            logger.warning(
                                "âš ï¸ Using deterministic company-template fallback after LLM validation failure"
                            )
                            template_candidate = self._auto_attach_shared_components(
                                template_candidate,
                                fixed_parts=fixed_parts,
                                user_request=user_request
                            )
                            self._record_fallback_usage(
                                'company_template',
                                'deterministic_company_template_fallback_validation_failure',
                                chars_added=len(template_candidate)
                            )
                            self._finalize_fallback_usage(template_candidate)
                            self.last_validation_result = template_validation.copy()
                            self.last_generation_metadata['fallback_mode'] = 'company_template'
                            self.last_generation_metadata['attempts_made'] = llm_attempts_made
                            self.last_generation_metadata['refusal_count'] = refusal_count
                            self.last_generation_metadata['llm_call_failures'] = llm_call_failures
                            self.last_generation_metadata['output_length'] = len(template_candidate)
                            return template_candidate

                    raise ValueError(
                        "Inline generation failed strict validation after "
                        f"{max_retries} attempts. Missing functions: {missing_str}"
                    )
        
        # âœ… ISSUE #10 FIX: Should never reach here, but add safety check
        if not inline_code:
            logger.error(f"âŒ CRITICAL: No code generated after all attempts!")
            raise ValueError("Code generation failed - no code produced")

        self._finalize_fallback_usage(inline_code)
        return inline_code
    
    def _validate_company_functions(
        self,
        code: str,
        user_request: str = "",
        hierarchy_pattern: Dict = None,
        company_fields: Dict = None,
        grid_pattern: Dict = None,
        naming_metadata: Dict = None
    ) -> Dict:
        """
        Validate that generated code uses company functions, not forbidden ones
        
        INTELLIGENT VALIDATION: Checks based on user's actual requirements
        - If user mentions "dropdown", validate dropdown pattern
        - If user mentions "keyboard", validate keyboard pattern
        - If user mentions "validation", validate FormValidation pattern
        - Otherwise, only validate CORE patterns (AJAX, Delete, Chart, Comp_Code, Session)
        
        Returns:
            {
                'valid': bool,
                'found_functions': List[str],
                'missing_functions': List[str],
                'forbidden_functions': List[str],
                'ajax_pattern_found': bool,
                ...
            }
        """
        
        company_fields = company_fields or {}
        grid_pattern = grid_pattern or {}
        naming_metadata = naming_metadata or {}
        strict_company_validation = bool(naming_metadata.get('strict_company_validation', True))
        strict_validation_reason = str(
            naming_metadata.get('strict_validation_reason') or
            ('retrieval_context_strong' if strict_company_validation else 'retrieval_context_weak')
        )
        logger.info(
            f"ðŸ” Enterprise core validation mode: "
            f"{'STRICT' if strict_company_validation else 'RELAXED'} ({strict_validation_reason})"
        )

        # ðŸ†• INTELLIGENT DETECTION: Parse user request to understand requirements
        user_request_text = user_request or ""
        user_request_lower = user_request_text.lower()
        request_metadata = self._extract_explicit_request_metadata(user_request_text)
        if request_metadata.get('has_entity_conflict'):
            logger.warning(
                "Validation detected conflicting entities in prompt; enforcing explicit table/file metadata."
            )

        user_requirements = self._detect_user_requirements(user_request)
        
        # ✅ PHASE 1.5: VALIDATION ALIGNMENT - Build validation contract
        logger.info("📋 PHASE 1.5: Validation Contract Alignment")
        validation_contract = {
            'core_always_required': ['company_functions', 'session_variables', 'ajax_auto_id'],
            'conditional_on_request': {
                'formvalidation': user_requirements.get('wants_formvalidation', False),
                'keyboard_navigation': user_requirements.get('wants_keyboard', False),
                'select2': user_requirements.get('wants_select2', False),
                'grid_pattern': user_requirements.get('wants_grid', False),
                'predelete_checks': user_requirements.get('wants_predelete', False),
            },
            'enterprise_required': ['multi_company_filter', 'audit_logging', 'delegated_events', 'ajax_reinit_guard']
        }
        logger.info(f"   Validator will ONLY check what user requested + enterprise core")
        for check, required in validation_contract['conditional_on_request'].items():
            logger.info(f"   - {check}: {'✅ WILL CHECK' if required else '⚪ SKIP'}")
        
        requested_fields = company_fields.get('user_requested_fields', [])
        grid_explicitly_requested = bool(
            grid_pattern.get('explicit_request') or user_requirements.get('wants_grid')
        )
        requested_grid_fields = grid_pattern.get('grid_fields', []) if grid_explicitly_requested else []
        requested_table_name = (request_metadata.get('table_name') or naming_metadata.get('table_name') or '').strip()
        requested_file_name = os.path.basename(
            (request_metadata.get('file_name') or naming_metadata.get('file_name') or '').strip()
        )
        requested_title = (
            request_metadata.get('title')
            or request_metadata.get('case_type')
            or naming_metadata.get('title')
            or naming_metadata.get('case_type')
        )
        if not requested_title and request_metadata.get('effective_entity'):
            requested_title = str(request_metadata.get('effective_entity')).replace('_', ' ').strip().title()

        strict_field_signals = [
            signal.lower()
            for signal in get_csv_setting(
                'CODEGEN_STRICT_FIELD_SIGNALS',
                'CODEGEN_STRICT_FIELD_SIGNALS',
                default=[
                    'master fields',
                    'exact naming',
                    'must include',
                    'include all',
                    'all fields',
                    'following fields'
                ]
            )
        ]
        strict_field_enforcement = (
            len(requested_fields) >= 6 or
            any(signal in user_request_lower for signal in strict_field_signals)
        )
        requested_entity_raw = (request_metadata.get('effective_entity') or '').strip()
        if not requested_entity_raw:
            entity_patterns = [
                r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*)\s+master\s+form',
                r'([a-z][a-z0-9_]*)\s+master\s+form',
                r'form\s+for\s+([a-z][a-z0-9_]*)',
                r'\bfrm([a-z][a-z0-9_]*)\b',
            ]
            for pattern in entity_patterns:
                entity_match = re.search(pattern, user_request_lower, re.IGNORECASE)
                if entity_match:
                    requested_entity_raw = str(entity_match.group(1) or '')
                    break

        requested_entity_compact = (
            request_metadata.get('effective_entity_compact')
            or re.sub(r'[^a-z0-9]', '', requested_entity_raw.lower())
        )
        requested_entity_base = (
            requested_entity_compact[:-6]
            if requested_entity_compact.endswith('master') and len(requested_entity_compact) > 6
            else requested_entity_compact
        )
        generic_canonical_signals = [
            signal.lower()
            for signal in get_csv_setting(
                'CODEGEN_CANONICAL_GENERIC_SIGNALS',
                'CODEGEN_CANONICAL_GENERIC_SIGNALS',
                default=['canonical naming', 'keep canonical naming']
            )
        ]
        table_canonical_signals = [
            signal.lower()
            for signal in get_csv_setting(
                'CODEGEN_CANONICAL_TABLE_SIGNALS',
                'CODEGEN_CANONICAL_TABLE_SIGNALS',
                default=['exact table name', 'same table name', 'use this table', 'canonical table']
            )
        ]
        file_canonical_signals = [
            signal.lower()
            for signal in get_csv_setting(
                'CODEGEN_CANONICAL_FILE_SIGNALS',
                'CODEGEN_CANONICAL_FILE_SIGNALS',
                default=['exact file name', 'same file name', 'use this file', 'canonical file']
            )
        ]
        title_canonical_signals = [
            signal.lower()
            for signal in get_csv_setting(
                'CODEGEN_CANONICAL_TITLE_SIGNALS',
                'CODEGEN_CANONICAL_TITLE_SIGNALS',
                default=['exact title', 'same title', 'canonical title']
            )
        ]

        generic_canonical_requested = any(
            signal in user_request_lower for signal in generic_canonical_signals
        )

        canonical_table_required = bool(request_metadata.get('table_name')) or generic_canonical_requested or any(
            signal in user_request_lower for signal in table_canonical_signals
        )
        canonical_file_required = bool(request_metadata.get('file_name')) or generic_canonical_requested or any(
            signal in user_request_lower for signal in file_canonical_signals
        )
        canonical_title_required = generic_canonical_requested or any(
            signal in user_request_lower for signal in title_canonical_signals
        )

        if requested_table_name and re.search(re.escape(requested_table_name.lower()), user_request_lower):
            canonical_table_required = True
        if requested_file_name and re.search(re.escape(requested_file_name.lower()), user_request_lower):
            canonical_file_required = True
        if requested_title and re.search(re.escape(requested_title.lower()), user_request_lower):
            canonical_title_required = True

        canonical_requested = canonical_table_required or canonical_file_required or canonical_title_required
        
        wants_dropdown = user_requirements.get('wants_dropdown', False)
        wants_keyboard = user_requirements.get('wants_keyboard', False)
        wants_formvalidation = user_requirements.get('wants_formvalidation', False)
        wants_select2 = user_requirements.get('wants_select2', False)
        explicit_select2_focus_request = user_requirements.get('explicit_select2_focus_request', False)
        wants_grid = user_requirements.get('wants_grid', False)
        wants_chart = user_requirements.get('wants_chart', False)
        wants_getcostcenter = user_requirements.get('wants_getcostcenter', False)
        wants_multidelete = user_requirements.get('wants_multidelete', False)
        wants_predelete = user_requirements.get('wants_predelete', False)
        wants_transactions = user_requirements.get('wants_transactions', False)
        wants_audit = user_requirements.get('wants_audit', False)
        
        logger.info(f"ðŸ” User Requirements Detection:")
        logger.info(f"   Wants Dropdown: {wants_dropdown}")
        logger.info(f"   Wants Keyboard Nav: {wants_keyboard}")
        logger.info(f"   Wants FormValidation: {wants_formvalidation}")
        logger.info(f"   Wants Select2: {wants_select2}")
        logger.info(f"   Wants Grid: {wants_grid}")
        logger.info(f"   Wants Chart: {wants_chart}")
        logger.info(f"   Wants GetCOSTCENTER: {wants_getcostcenter}")
        logger.info(f"   Wants Multi-Delete: {wants_multidelete}")
        logger.info(f"   Wants Pre-Delete Checks: {wants_predelete}")
        logger.info(f"   Wants Transactions: {wants_transactions}")
        logger.info(f"   Wants Audit: {wants_audit}")
        logger.info(f"   Requested Fields: {len(requested_fields)}")
        logger.info(f"   Requested Entity Hint: {requested_entity_raw or 'None'}")
        logger.info(f"   Strict Field Enforcement: {strict_field_enforcement}")
        logger.info(
            f"   Canonical Naming Required: {canonical_requested} "
            f"(table={canonical_table_required}, file={canonical_file_required}, title={canonical_title_required})"
        )
        
        # âœ… PHASE 1 VALIDATION: Check extracted patterns are used
        phase1_hierarchical_found = False
        phase1_field_names_correct = False
        phase1_predelete_all_tables = False
        phase1_cascading_parent_param = False
        
        # Check hierarchical pattern (if detected in extraction)
        if 'MAX(RIGHT(Code,' in code or 'RIGHT(Code,' in code:
            phase1_hierarchical_found = True
            logger.info(f"   âœ… Phase 1: Hierarchical code pattern found")
        else:
            logger.warning(f"   âš ï¸ Phase 1: Hierarchical code pattern MISSING")
        
        # Check if maxid() has parent parameter (for cascading)
        maxid_has_parent_param = False
        
        # Get expected parent parameter from hierarchy_pattern (if available)
        expected_parent_param = None
        if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical'):
            expected_parent_param = hierarchy_pattern.get('parent_request_param', 'SelectArea')
        
        # Check for parent parameter in code (either expected or common names)
        parent_param_patterns = [expected_parent_param] if expected_parent_param else []
        parent_param_patterns.extend(['SelectArea', 'SelectParent', 'ParentCode'])  # Common fallbacks
        
        for param in parent_param_patterns:
            if param and param in code:
                # Check if it's actually IN the maxid() function
                maxid_match = re.search(r'function maxid\(\).*?\{(.*?)\}', code, re.DOTALL)
                if maxid_match:
                    maxid_body = maxid_match.group(1)
                    if param in maxid_body:
                        maxid_has_parent_param = True
                        phase1_cascading_parent_param = True
                        logger.info(f"   âœ… Phase 1: Cascading parent parameter '{param}' found IN maxid()")
                        break
                    else:
                        logger.warning(f"   âš ï¸ Phase 1: '{param}' found but NOT in maxid() function")
                else:
                    logger.warning(f"   âš ï¸ Phase 1: maxid() function not found")
        
        if not maxid_has_parent_param:
            logger.warning(f"   âš ï¸ Phase 1: Cascading parent parameter MISSING")
        
        # ðŸ”´ CRITICAL: If hierarchical pattern detected, maxid() MUST have parent param
        hierarchical_parent_missing = phase1_hierarchical_found and not maxid_has_parent_param
        if hierarchical_parent_missing:
            logger.error(f"   âŒ CRITICAL: Hierarchical code detected but maxid() missing parent parameter!")
            logger.error(f"   âŒ This will cause incorrect code generation (e.g., '01' instead of 'LHR-01')")
        
        # Company functions that MUST be used - ALL 6 REQUIRED for complete CRUD
        # Normalize to lowercase for case-insensitive detection
        required_functions = ['db_insert', 'db_update', 'db_delete', 'db_getrecord', 'getrows', 'getvalue']
        minimum_required_functions = get_int_setting(
            'CODEGEN_MIN_REQUIRED_COMPANY_FUNCTIONS',
            'CODEGEN_MIN_REQUIRED_COMPANY_FUNCTIONS',
            3,
            min_value=3,
            max_value=6
        )
        enforce_production_guards = self._bool_setting('CODEGEN_ENFORCE_PRODUCTION_GUARDS', True)
        
        # Forbidden functions that MUST NOT be used
        # NOTE: mysql_fetch_array, mysql_query are ALLOWED - company uses them with db_getRecord()
        forbidden_functions = ['mysqli_', 'new mysqli', 'new PDO', '$pdo->', 'mysqli_query', 'mysqli_fetch']
        
        # Check what's in the code - case-insensitive detection
        code_lower = (code or "").lower()
        def _has_token(token: str) -> bool:
            # Word-boundary detection to avoid false positives from longer identifiers
            return bool(re.search(rf'(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])', code_lower))
        
        found_functions = [f for f in required_functions if _has_token(f)]
        
        missing_functions = [f for f in required_functions if f not in found_functions]
        
        forbidden_found = []
        for forbidden in forbidden_functions:
            if forbidden in code:
                forbidden_found.append(forbidden)
        
        # âœ… FIXED ISSUE #6: Check for AJAX Auto-ID Pattern with REGEX
        # More flexible detection using regex patterns instead of exact string matching
        
        ajax_pattern_found = False
        
        # âœ… REGEX-BASED AJAX detection patterns (case-insensitive, flexible)
        ajax_regex_patterns = [
            # PHP AJAX handlers - flexible matching
            r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]",  # if($_REQUEST['action']
            r"if\s*\(\s*isset\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]",  # if(isset($_REQUEST['action']
            # JavaScript AJAX calls
            r"function\s+(maxid|getMaxId|autoGenerateCode|getCode)\s*\(",  # function maxid(
            r"\$\.(post|ajax)\s*\(",  # $.post( or $.ajax(
            r"new\s+XMLHttpRequest",  # new XMLHttpRequest
            # Action parameters
            r"action\s*:\s*['\"]get(MaxID|Code|Id)",  # action: 'getMaxID'
            # Auto-ID patterns
            r"(getvalue|GetValue)\s*\(",  # getvalue(
            r"MAX\s*\(\s*Code\s*\)",  # MAX(Code)
            r"LPAD\s*\(",  # LPAD(
            r"(auto_id|AutoCode|ajaxCode)",  # auto_id, AutoCode, ajaxCode
        ]
        
        # Count regex matches (case-insensitive)
        ajax_found_count = sum(1 for pattern in ajax_regex_patterns 
                              if re.search(pattern, code, re.IGNORECASE))
        
        # PASS if at least 1 indicator found (lowered for controlled assembly)
        ajax_min_hits = 1
        ajax_pattern_found = ajax_found_count >= ajax_min_hits
        
        if ajax_pattern_found:
            logger.info(f"   âœ… AJAX Auto-ID: Found ({ajax_found_count} indicators)")
        else:
            logger.warning(f"   âš ï¸ AJAX Auto-ID: Only {ajax_found_count} indicators found (need {ajax_min_hits}+)")
        
        # âœ… ISSUE #6 FIX: STRICTER Pre-Delete Dependency Checks detection
        # Pre-delete checks require ALL components for complete implementation
        predelete_pattern_found = False
        predelete_regex_patterns = [
            r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]\s*\]\s*==\s*['\"]Delete['\"]",  # if($_REQUEST['action'] == 'Delete')
            r"(getrows2|getrows)\s*\(",  # getrows2( or getrows(
            r"(print|echo)\s+['\"]<script>alert\(",  # print "<script>alert(
            r"exit\s*;",  # exit;
        ]
        
        predelete_found_count = sum(1 for pattern in predelete_regex_patterns 
                                   if re.search(pattern, code, re.IGNORECASE))
        
        # âœ… ISSUE #6 FIX: Check for COMPLETE pre-delete implementation
        # Complete pre-delete requires:
        # 1. Delete action check (if($_REQUEST['action'] == 'Delete'))
        # 2. Dependency check (getrows2/getrows)
        # 3. Alert message (print "<script>alert(")
        # 4. Exit on dependency (exit;)
        has_delete_action = bool(re.search(r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]\s*\]\s*==\s*['\"]Delete['\"]", code, re.IGNORECASE))
        has_dependency_check = bool(re.search(r"(getrows2|getrows)\s*\(", code, re.IGNORECASE))
        has_alert_message = bool(re.search(r"(print|echo)\s+['\"]<script>alert\(", code, re.IGNORECASE))
        has_exit_statement = bool(re.search(r"exit\s*;", code, re.IGNORECASE))
        
        # âœ… ISSUE #6 CRITICAL: ALL 4 components must be present for complete pre-delete
        if has_delete_action and has_dependency_check and has_alert_message and has_exit_statement:
            predelete_pattern_found = True
            logger.info(f"   âœ… Pre-Delete Checks: COMPLETE (all 4 components found)")
            logger.info(f"      - Delete action check: âœ…")
            logger.info(f"      - Dependency check (getrows): âœ…")
            logger.info(f"      - Alert message: âœ…")
            logger.info(f"      - Exit statement: âœ…")
        elif has_delete_action or has_dependency_check:
            # Partial implementation - log what's missing
            predelete_pattern_found = False
            logger.warning(f"   âš ï¸ Pre-Delete Checks: INCOMPLETE ({predelete_found_count}/4 components)")
            logger.warning(f"      - Delete action check: {'âœ…' if has_delete_action else 'âŒ MISSING'}")
            logger.warning(f"      - Dependency check (getrows): {'âœ…' if has_dependency_check else 'âŒ MISSING'}")
            logger.warning(f"      - Alert message: {'âœ…' if has_alert_message else 'âŒ MISSING'}")
            logger.warning(f"      - Exit statement: {'âœ…' if has_exit_statement else 'âŒ MISSING'}")
        else:
            logger.info(f"   âšª Pre-Delete Checks: Not found (optional - not all forms have delete)")
        
        # âœ… ISSUE #7 FIX: STRICTER Multi-Delete Loop Pattern detection
        # Multi-delete requires ALL 3 components for complete implementation
        multidelete_pattern_found = False
        multidelete_regex_patterns = [
            r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]DeleteCase['\"]\s*\]\s*==\s*['\"]Deleteall['\"]",  # if($_REQUEST['DeleteCase'] == 'Deleteall')
            r"explode\s*\(\s*['\"],['\"]\s*,\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]major['\"]\s*\]",  # explode(',', $_REQUEST['major'])
            r"for\s*\(\s*\$i\s*=\s*0\s*;\s*\$i\s*<\s*sizeof\s*\(\s*\$major\s*\)",  # for($i=0; $i<sizeof($major)
        ]
        
        multidelete_found_count = sum(1 for pattern in multidelete_regex_patterns 
                                      if re.search(pattern, code, re.IGNORECASE))
        
        # âœ… ISSUE #7 FIX: Check for COMPLETE multi-delete implementation
        # Complete multi-delete requires:
        # 1. DeleteCase check (if($_REQUEST['DeleteCase'] == 'Deleteall'))
        # 2. Explode IDs (explode(',', $_REQUEST['major']))
        # 3. Loop through IDs (for($i=0; $i<sizeof($major); $i++))
        has_deletecase_check = bool(re.search(r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]DeleteCase['\"]\s*\]\s*==\s*['\"]Deleteall['\"]", code, re.IGNORECASE))
        has_explode_ids = bool(re.search(r"explode\s*\(\s*['\"],['\"]\s*,\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]major['\"]\s*\]", code, re.IGNORECASE))
        has_loop_through_ids = bool(re.search(r"for\s*\(\s*\$i\s*=\s*0\s*;\s*\$i\s*<\s*sizeof\s*\(\s*\$major\s*\)", code, re.IGNORECASE))
        
        # âœ… ISSUE #7 CRITICAL: ALL 3 components must be present for complete multi-delete
        if has_deletecase_check and has_explode_ids and has_loop_through_ids:
            multidelete_pattern_found = True
            logger.info(f"   âœ… Multi-Delete Loop: COMPLETE (all 3 components found)")
            logger.info(f"      - DeleteCase check: âœ…")
            logger.info(f"      - Explode IDs: âœ…")
            logger.info(f"      - Loop through IDs: âœ…")
        elif has_deletecase_check or has_explode_ids or has_loop_through_ids:
            # Partial implementation - log what's missing
            multidelete_pattern_found = False
            logger.warning(f"   âš ï¸ Multi-Delete Loop: INCOMPLETE ({multidelete_found_count}/3 components)")
            logger.warning(f"      - DeleteCase check: {'âœ…' if has_deletecase_check else 'âŒ MISSING'}")
            logger.warning(f"      - Explode IDs: {'âœ…' if has_explode_ids else 'âŒ MISSING'}")
            logger.warning(f"      - Loop through IDs: {'âœ…' if has_loop_through_ids else 'âŒ MISSING'}")
        else:
            logger.info(f"   âšª Multi-Delete Loop: Not found (optional - not all forms need multi-delete)")
        
        # âœ… ISSUE #4 FIX: STRICTER Chart of Accounts Integration detection
        # Chart integration requires ALL 4 operations: ACC_PREFIX + INSERT + UPDATE + DELETE
        chart_pattern_found = False
        chart_regex_patterns = [
            r"ACC_(CUST|SUPP|CODE|NAME|VEND)",  # ACC_CUST, ACC_SUPP, ACC_CODE, ACC_NAME, ACC_VEND
            r"INSERT\s+INTO\s+chart",  # INSERT INTO chart
            r"UPDATE\s+chart\s+SET",  # UPDATE chart SET
            r"DELETE\s+FROM\s+chart",  # DELETE FROM chart
            r"mysql_query\s*\(\s*['\"]INSERT\s+INTO\s+chart",  # mysql_query("INSERT INTO chart
            r"mysql_query\s*\(\s*['\"]DELETE\s+FROM\s+chart",  # mysql_query("DELETE FROM chart
            r"\$qry_insert\s*=.*chart",  # $qry_insert = "... chart ..."
            r"\$qry_update\s*=.*chart",  # $qry_update = "... chart ..."
            r"\$del\s*=.*chart",  # $del = mysql_query("... chart ...")
        ]
        
        chart_found_count = sum(1 for pattern in chart_regex_patterns 
                               if re.search(pattern, code, re.IGNORECASE))
        
        # âœ… ISSUE #4 FIX: CRITICAL - Check for ALL 4 required chart operations
        # Chart integration is COMPLETE only if it has:
        # 1. ACC_PREFIX constant (ACC_CUST, ACC_SUPP, etc.)
        # 2. INSERT INTO chart (on Save)
        # 3. UPDATE chart (on Update)
        # 4. DELETE FROM chart (on Delete)
        has_chart_insert = bool(re.search(r"INSERT\s+INTO\s+chart", code, re.IGNORECASE))
        has_chart_update = bool(re.search(r"UPDATE\s+chart", code, re.IGNORECASE))
        has_chart_delete = bool(re.search(r"DELETE\s+FROM\s+chart", code, re.IGNORECASE))
        has_acc_prefix = bool(re.search(r"ACC_(CUST|SUPP|CODE|NAME)", code, re.IGNORECASE))
        has_chartcode_var = bool(
            re.search(r"\$chartcode\s*=\s*ACC_", code, re.IGNORECASE) or
            re.search(r"\$\w+\s*=\s*ACC_[A-Z0-9_]+\s*\.\s*CustomerCode\s*\(", code, re.IGNORECASE) or
            re.search(r"CustomerCode\s*\(", code, re.IGNORECASE)
        )
        
        # âœ… ISSUE #4 CRITICAL: ALL 4 operations must be present for complete chart integration
        # If user wants chart, we need COMPLETE implementation, not partial
        if has_acc_prefix and has_chartcode_var and has_chart_insert and has_chart_update and has_chart_delete:
            chart_pattern_found = True
            logger.info(f"   âœ… Chart Integration: COMPLETE (all 4 operations found)")
            logger.info(f"      - ACC_PREFIX: âœ…")
            logger.info(f"      - Chart code generation: âœ…")
            logger.info(f"      - INSERT INTO chart: âœ…")
            logger.info(f"      - UPDATE chart: âœ…")
            logger.info(f"      - DELETE FROM chart: âœ…")
        elif has_acc_prefix or has_chart_insert or has_chart_update or has_chart_delete:
            # Partial implementation - log what's missing
            chart_pattern_found = False
            logger.warning(f"   âš ï¸ Chart Integration: INCOMPLETE ({chart_found_count}/9 indicators)")
            logger.warning(f"      - ACC_PREFIX: {'âœ…' if has_acc_prefix else 'âŒ MISSING'}")
            logger.warning(f"      - Chart code generation: {'âœ…' if has_chartcode_var else 'âŒ MISSING'}")
            logger.warning(f"      - INSERT INTO chart: {'âœ…' if has_chart_insert else 'âŒ MISSING'}")
            logger.warning(f"      - UPDATE chart: {'âœ…' if has_chart_update else 'âŒ MISSING'}")
            logger.warning(f"      - DELETE FROM chart: {'âœ…' if has_chart_delete else 'âŒ MISSING'}")
        else:
            logger.info(f"   âšª Chart Integration: Not found")
        
        # âœ… FIXED ISSUE #6: Check for Dynamic Dropdown Pattern with REGEX
        # âœ… BROADENED: More flexible patterns to catch all variations
        dropdown_pattern_found = False
        dropdown_regex_patterns = [
            r"if\s*\(\s*\$_(REQUEST|POST|GET)\s*\[\s*['\"]action['\"]\s*\]\s*==\s*['\"]get",  # if($_REQUEST['Action']=='Get (case-insensitive)
            r"(mysql_fetch_object|mysql_fetch_array|mysql_fetch_assoc)\s*\(",  # Fetching data
            r"json_encode\s*\(",  # JSON response
            r"function\s+(load|max)\w*\s*\(",  # function load... or maxid()
            r"\$\.ajax\s*\(",  # $.ajax(
            r"\$\.post\s*\(",  # $.post(
            r"onChange\s*=",  # onChange event
            r"<select[^>]*>",  # <select> tag
        ]
        dropdown_found_count = sum(1 for pattern in dropdown_regex_patterns 
                                  if re.search(pattern, code, re.IGNORECASE))
        dropdown_pattern_found = dropdown_found_count >= 2  # âœ… Need at least 2 indicators
        
        # âœ… ISSUE #3 FIX: Enhanced FormValidation Pattern detection
        # More flexible patterns to catch all variations
        formvalidation_pattern_found = False
        formvalidation_regex_patterns = [
            r"\.formValidation\s*\(",  # jQuery style: $('#frm').formValidation(
            r"FormValidation\.formValidation\s*\(",  # Class style: FormValidation.formValidation(
            r"framework\s*:\s*['\"]bootstrap['\"]",  # framework: "bootstrap"
            r"validators\s*:\s*\{",  # validators: {
            r"fields\s*:\s*\{",  # fields: { (company uses this)
            r"notEmpty\s*:",  # notEmpty: validator
            r"\.on\s*\(\s*['\"]success\.form\.fv['\"]",  # .on('success.form.fv'
            r"formvalidation\.min\.js",  # formValidation library
            r"data-fv-",  # data-fv-* attributes
            r"callback\s*:\s*function",  # callback: function (validation callback)
            r"message\s*:\s*['\"].*required",  # message: "... required ..."
        ]
        formvalidation_found_count = sum(1 for pattern in formvalidation_regex_patterns 
                                        if re.search(pattern, code, re.IGNORECASE))
        formvalidation_pattern_found = formvalidation_found_count >= 2  # Need at least 2/11 indicators
        
        # âœ… ISSUE #3 FIX: Smart detection - check for validation library OR inline validation
        has_fv_library = bool(re.search(r"formvalidation\.min\.js", code, re.IGNORECASE))
        has_fv_init = bool(re.search(r"\.formValidation\s*\(", code, re.IGNORECASE))
        has_fv_fields = bool(re.search(r"fields\s*:\s*\{", code, re.IGNORECASE))
        has_validators = bool(re.search(r"validators\s*:\s*\{", code, re.IGNORECASE))
        has_inline_validation = bool(re.search(r"(required|notEmpty|email|regexp).*validator", code, re.IGNORECASE))
        has_required_inputs = bool(re.search(r"<(input|select|textarea)[^>]*\srequired\b", code, re.IGNORECASE))
        has_html5_validation_api = bool(re.search(r"(checkValidity|reportValidity)\s*\(", code, re.IGNORECASE))
        
        # If library + initialization (or required inputs) found, OR inline/native validation found, consider it present
        if (
            (has_fv_library and (has_fv_init or has_required_inputs)) or
            (has_fv_fields and has_validators) or
            has_inline_validation or
            has_html5_validation_api or
            has_required_inputs
        ):
            formvalidation_pattern_found = True
            logger.info(
                f"   âœ… FormValidation: Found (smart detection - library:{has_fv_library}, "
                f"init:{has_fv_init}, fields:{has_fv_fields}, required_inputs:{has_required_inputs})"
            )
        elif formvalidation_found_count > 0:
            logger.info(f"   âš ï¸ FormValidation: Partial ({formvalidation_found_count}/11 indicators) - may be present")
        else:
            logger.info(f"   âšª FormValidation: Not found")
        
        # âœ… FIXED ISSUE #6: Check for Keyboard Navigation Pattern with REGEX
        # Stricter keyboard detection to avoid false positives from generic vendor keydown handlers.
        has_checkkeycode_fn = bool(re.search(r"function\s+checkkeycode\s*\(", code, re.IGNORECASE))
        has_checkkeycode_call = bool(
            re.search(r"onkey(?:down)?\s*=\s*['\"]checkkeycode\(", code, re.IGNORECASE)
        )
        has_document_binding = bool(
            re.search(r"document\.onkeydown\s*=\s*checkkeycode", code, re.IGNORECASE)
        )
        has_addlistener_binding = bool(
            re.search(
                r"addEventListener\s*\(\s*['\"]keydown['\"]\s*,\s*checkkeycode",
                code,
                re.IGNORECASE
            )
        )
        has_enter_key_logic = bool(
            re.search(
                r"(?:event|e)\.keycode\s*(?:==|===|!=|!==)\s*13|keycode\s*==\s*13",
                code,
                re.IGNORECASE
            )
        )

        keyboard_pattern_found = bool(
            has_checkkeycode_call
            or has_document_binding
            or has_addlistener_binding
            or (has_checkkeycode_fn and has_enter_key_logic)
        )
        keyboard_found_count = sum(
            1
            for flag in [
                has_checkkeycode_fn,
                has_checkkeycode_call,
                has_document_binding,
                has_addlistener_binding,
                has_enter_key_logic,
            ]
            if flag
        )
        if keyboard_pattern_found:
            logger.info(
                f"   ✅ Keyboard Navigation: Found "
                f"(fn:{has_checkkeycode_fn}, call:{has_checkkeycode_call}, "
                f"doc_bind:{has_document_binding}, listener_bind:{has_addlistener_binding}, "
                f"enter_logic:{has_enter_key_logic})"
            )
        elif keyboard_found_count > 0:
            logger.info(
                f"   ⚠️ Keyboard Navigation: Partial ({keyboard_found_count}/5 indicators) - missing checkKeycode binding/function"
            )
        else:
            logger.info(f"   ⚪ Keyboard Navigation: Not found")
        
        # âœ… ISSUE #8 FIX: STRICTER Grid/Detail Records Pattern detection
        # Grid pattern requires ALL 4 components for complete implementation
        grid_pattern_found = False
        grid_regex_patterns = [
            r"TXTCOUNT\w+",  # TXTCOUNTACC, TXTCOUNT, etc. (hidden field for row count)
            r"for\s*\(\s*\$\w+\s*=\s*0\s*;\s*\$\w+\s*<=\s*\$_REQUEST\s*\[\s*['\"]TXTCOUNT",  # for($i=0; $i<=$_REQUEST['TXTCOUNTACC']; $i++)
            r"\$_REQUEST\s*\[\s*['\"](?:SR_NO|SiteName|Shipping)['\"]\s*\.\s*\$\w+",  # $_REQUEST['SR_NO'.$i]
            r"db_delete\s*\(\s*\$sub_table",  # db_delete($sub_table, ...) (delete old detail records)
        ]
        
        grid_found_count = sum(1 for pattern in grid_regex_patterns 
                              if re.search(pattern, code, re.IGNORECASE))
        
        # âœ… ISSUE #8 FIX: Check for COMPLETE grid implementation
        # Complete grid requires:
        # 1. TXTCOUNT hidden field (row counter)
        # 2. Loop through detail records (for loop)
        # 3. Dynamic field names (SR_NO.$i pattern)
        # 4. Delete old records before insert (db_delete($sub_table))
        has_txtcount_field = bool(re.search(r"TXTCOUNT\w+", code, re.IGNORECASE))
        has_detail_loop = bool(re.search(r"for\s*\(\s*\$\w+\s*=\s*0\s*;\s*\$\w+\s*<=\s*\$_REQUEST\s*\[\s*['\"]TXTCOUNT", code, re.IGNORECASE))
        requested_dynamic_fields = [str(field).strip() for field in (requested_grid_fields or []) if str(field).strip()]
        dynamic_field_candidates = requested_dynamic_fields or ['SR_NO', 'SiteName', 'Shipping']
        dynamic_field_regex = '|'.join(re.escape(field) for field in dynamic_field_candidates)
        has_dynamic_fields = bool(
            re.search(
                rf"\$_REQUEST\s*\[\s*['\"](?:{dynamic_field_regex})['\"]\s*\.\s*\$\w+",
                code,
                re.IGNORECASE
            )
        )
        has_delete_old_records = bool(re.search(r"db_delete\s*\(\s*\$sub_table", code, re.IGNORECASE))
        
        # âœ… ISSUE #8 CRITICAL: ALL 4 components must be present for complete grid
        if has_txtcount_field and has_detail_loop and has_dynamic_fields and has_delete_old_records:
            grid_pattern_found = True
            logger.info(f"   âœ… Grid Pattern: COMPLETE (all 4 components found)")
            logger.info(f"      - TXTCOUNT field: âœ…")
            logger.info(f"      - Detail loop: âœ…")
            logger.info(f"      - Dynamic fields: âœ…")
            logger.info(f"      - Delete old records: âœ…")
        elif has_txtcount_field or has_detail_loop or has_dynamic_fields:
            # Partial implementation - log what's missing
            grid_pattern_found = False
            logger.warning(f"   âš ï¸ Grid Pattern: INCOMPLETE ({grid_found_count}/4 components)")
            logger.warning(f"      - TXTCOUNT field: {'âœ…' if has_txtcount_field else 'âŒ MISSING'}")
            logger.warning(f"      - Detail loop: {'âœ…' if has_detail_loop else 'âŒ MISSING'}")
            logger.warning(f"      - Dynamic fields: {'âœ…' if has_dynamic_fields else 'âŒ MISSING'}")
            logger.warning(f"      - Delete old records: {'âœ…' if has_delete_old_records else 'âŒ MISSING'}")
        else:
            logger.info(f"   âšª Grid Pattern: Not found (optional - not all forms have detail records)")
        
        # âœ… ISSUE #3 FIX: Enhanced Select2 Integration Pattern detection
        # More flexible patterns to catch all variations INCLUDING close events
        select2_pattern_found = False
        select2_regex_patterns = [
            r"\.select2\s*\(",  # .select2(
            r"data-plugin\s*=\s*['\"]select2['\"]",  # data-plugin="select2"
            r"class\s*=\s*['\"][^'\"]*select2[^'\"]*['\"]",  # class="...select2..."
            r"placeholder\s*:",  # placeholder:
            r"select2\.min\.js",  # select2 library
            r"select2\.css",  # select2 CSS
            r"\.on\s*\(\s*['\"]select2:(open|close|select)",  # .on('select2:open/close/select'
            r"\.select2\s*\(\s*['\"]open['\"]",  # .select2('open')
        ]
        select2_found_count = sum(1 for pattern in select2_regex_patterns 
                                 if re.search(pattern, code, re.IGNORECASE))
        select2_pattern_found = select2_found_count >= 2  # Need at least 2/8 indicators
        
        # âœ… ISSUE #3 FIX: Smart detection - check for library OR data-plugin OR events
        has_select2_library = bool(re.search(r"select2\.min\.js", code, re.IGNORECASE))
        has_select2_css = bool(re.search(r"select2\.css", code, re.IGNORECASE))
        has_data_plugin = bool(re.search(r"data-plugin\s*=\s*['\"]select2['\"]", code, re.IGNORECASE))
        has_select2_init = bool(re.search(r"\.select2\s*\(", code, re.IGNORECASE))
        has_select2_events = bool(re.search(r"select2:(open|close|select)", code, re.IGNORECASE))
        
        # âœ… ISSUE #3 CRITICAL FIX: Check for Select2 close event handlers (for cascading dropdowns)
        # Pattern: $('#Main_Area').on("select2:close", function () { ... $('#Sub_Area').select2('open'); });
        has_select2_close_events = bool(re.search(r"\.on\s*\(\s*['\"]select2:close['\"]", code, re.IGNORECASE))
        has_select2_focus_chain = bool(re.search(r"\.select2\s*\(\s*['\"]open['\"]\s*\)", code, re.IGNORECASE))
        select2_focus_management_required = explicit_select2_focus_request or (wants_dropdown and wants_select2)
        
        # If library + (data-plugin OR init OR events) found, consider it present
        if (has_select2_library or has_select2_css) and (has_data_plugin or has_select2_init or has_select2_events):
            select2_pattern_found = True
            logger.info(f"   âœ… Select2: Found (smart detection - library:{has_select2_library}, data-plugin:{has_data_plugin}, events:{has_select2_events})")
            
            # âœ… ISSUE #3 CRITICAL: Require close/open chain only when the request needs cascading Select2 focus flow
            if select2_focus_management_required:
                if has_select2_close_events and has_select2_focus_chain:
                    logger.info(f"   âœ… Select2 Close Events: Found (requested cascading Select2 flow)")
                elif has_select2_close_events:
                    logger.warning(f"   âš ï¸ Select2 Close Events: Partial (missing .select2('open') chain for requested cascading Select2 flow)")
                else:
                    logger.warning(f"   âš ï¸ Select2 Close Events: Missing (required for requested cascading Select2 flow)")
            elif has_select2_close_events and has_select2_focus_chain:
                logger.info(f"   âœ… Select2 Close Events: Found (optional focus flow available)")
            elif has_select2_close_events or has_select2_focus_chain:
                logger.info(f"   âšª Select2 Focus Flow: Partial but optional for this request")
            else:
                logger.info(f"   âšª Select2 Focus Flow: Not required for this request")
        elif select2_found_count > 0:
            logger.info(f"   âš ï¸ Select2: Partial ({select2_found_count}/8 indicators) - may be present")
        else:
            logger.info(f"   âšª Select2: Not found")
        
        # âœ… FIXED ISSUE #6: Check for Multi-Company Filter with REGEX
        compcode_pattern_found = False
        compcode_regex_patterns = [
            r"Comp_Code\s*=\s*['\"]?\s*\.\s*\$_SESSION\s*\[\s*['\"]comp_code['\"]",  # Comp_Code='\".$_SESSION['comp_code'].\"'
            r"\$columns\s*\[\s*['\"]Comp_Code['\"]\s*\]",  # $columns['Comp_Code']
            r"AND\s+Comp_Code\s*=",  # AND Comp_Code=
            r"\$_SESSION\s*\[\s*['\"]comp_code['\"]\s*\]",  # $_SESSION['comp_code']
        ]
        compcode_found_count = sum(
            1 for pattern in compcode_regex_patterns
            if re.search(pattern, code, re.IGNORECASE)
        )
        compcode_min_hits = get_int_setting(
            'CODEGEN_COMPCODE_MIN_HITS',
            'CODEGEN_COMPCODE_MIN_HITS',
            1,
            min_value=1,
            max_value=4
        )
        compcode_pattern_found = compcode_found_count >= compcode_min_hits

        
        # ðŸ†• ISSUE #10 FIX: Check for Session Variables (login_id, Unit_Code, user_id)
        # âœ… ENHANCED: More flexible session detection to avoid false negatives
        session_vars_pattern_found = False
        
        # Check for ANY session usage first
        has_session_usage = '$_SESSION' in code
        has_session_start = 'session_start' in code or '@session_start' in code
        
        # Broad session variable patterns (case-insensitive matching)
        session_patterns = [
            'login_id', 'loginid', 'login_ID', 'LoginID',
            'user_id', 'userid', 'user_ID', 'UserId', 'UserID',
            'comp_code', 'Comp_Code', 'company_id', 'CompanyID',
            'username', 'UserName', 'user_name'
        ]
        
        # Count how many session patterns are found
        code_lower = code.lower()
        session_patterns_found = sum(1 for pattern in session_patterns if pattern.lower() in code_lower and '$_session' in code_lower)
        
        # PASS if: session_start exists AND any $_SESSION variable is used
        if has_session_start and has_session_usage:
            session_vars_pattern_found = True
            logger.info(f"   âœ… Session Variables: Found session_start + $_SESSION usage")
        # PASS if: multiple session patterns found (at least 2)
        elif has_session_usage and session_patterns_found >= 2:
            session_vars_pattern_found = True
            logger.info(f"   âœ… Session Variables: Found $_SESSION with {session_patterns_found} audit variables")
        else:
            logger.warning(f"   âš ï¸ Session Variables: Limited session usage detected")
        
        has_getcostcenter_handler = bool(re.search(r"GetCOSTCENTER", code, re.IGNORECASE))
        has_transaction_pattern = 'funStartTran' in code and 'funEndTran' in code
        has_audit_pattern = 'fun_log(' in code
        has_header_include = 'topmenu.php' in code.lower()
        has_sidebar_include = ('sidemenu.php' in code.lower()) or ('rightmenu.php' in code.lower())
        has_footer_include = 'footer.php' in code.lower()
        has_page_container = '<div class="page"' in code.lower() and 'page-content' in code.lower()
        has_form_horizontal_layout = bool(re.search(r'<form[^>]*form-horizontal', code, re.IGNORECASE))
        has_label_alignment = 'control-label' in code.lower() and bool(re.search(r'col-(?:xs|sm|md|lg)-\d+', code, re.IGNORECASE))
        has_delegated_events = bool(
            re.search(r'\.on\s*\(\s*[\'"][^\'"]+[\'"]\s*,\s*[\'"][^\'"]+[\'"]', code, re.IGNORECASE)
        )
        has_ajax_reinit_guard = (
            '__companysharedinit' in code.lower() or
            (('$(document)' in code.lower()) and ('.off(' in code.lower()) and ('.on(' in code.lower()))
        )

        missing_requested_fields = []
        for field_name in requested_fields:
            field_pattern = rf"['\"]{re.escape(field_name)}['\"]|\b{re.escape(field_name)}\b"
            if not re.search(field_pattern, code, re.IGNORECASE):
                missing_requested_fields.append(field_name)

        missing_requested_grid_fields = []
        for field_name in requested_grid_fields:
            field_pattern = rf"['\"]{re.escape(field_name)}['\"]|\b{re.escape(field_name)}\b"
            if not re.search(field_pattern, code, re.IGNORECASE):
                missing_requested_grid_fields.append(field_name)

        naming_table_found = True
        if requested_table_name:
            naming_table_found = bool(re.search(re.escape(requested_table_name), code, re.IGNORECASE))

        naming_file_found = True
        if requested_file_name:
            naming_file_found = bool(re.search(re.escape(requested_file_name), code, re.IGNORECASE))

        naming_title_found = True
        if requested_title:
            naming_title_found = bool(
                re.search(rf'\$title\s*=\s*["\']{re.escape(requested_title)}["\']', code, re.IGNORECASE) or
                re.search(re.escape(requested_title), code, re.IGNORECASE)
            )

        entity_alignment_found = True
        if requested_entity_base:
            code_compact = re.sub(r'[^a-z0-9]', '', code.lower())
            entity_candidates = [requested_entity_compact, requested_entity_base]
            entity_alignment_found = any(
                candidate and len(candidate) >= 3 and candidate in code_compact
                for candidate in entity_candidates
            )

        # âœ… NEW: Check for isset() usage (security best practice) - WARNING ONLY
        isset_check_found = 'isset($_REQUEST' in code or 'isset($_POST' in code
        if not isset_check_found:
            logger.warning(f"   âš ï¸ isset() checks recommended - helps prevent PHP notices")
            # âœ… DON'T FAIL - just warn
        
        # âœ… ISSUE #4 FIX: Check for htmlspecialchars() usage (XSS protection) - NOW OPTIONAL
        # Changed from MANDATORY to OPTIONAL with WARNING
        # Company codebase uses stripslashes() and other methods, not always htmlspecialchars()
        htmlspecialchars_found = 'htmlspecialchars(' in code or 'stripslashes(' in code or 'htmlentities(' in code
        if not htmlspecialchars_found:
            logger.warning(f"   âš ï¸ XSS protection recommended: htmlspecialchars() not found")
            logger.warning(f"   âš ï¸ Consider adding output escaping for user input")
            # âœ… DON'T FAIL - just warn
        else:
            logger.info(f"   âœ… XSS protection: Found output escaping")
        
        # Session vars are checked but don't block generation
        if not session_vars_pattern_found:
            logger.warning(f"   âš ï¸ Session variables not detected by pattern - will verify in enterprise validator")
        
        compcode_core_required = self._bool_setting('CODEGEN_REQUIRE_COMPCODE_CORE', True)

        # Core validation enforces enterprise-safe defaults.
        if strict_company_validation or enforce_production_guards:
            core_valid = (
                len(found_functions) >= minimum_required_functions and
                len(forbidden_found) == 0 and
                ajax_pattern_found and
                (compcode_pattern_found or not compcode_core_required) and
                session_vars_pattern_found and
                has_transaction_pattern and
                has_audit_pattern and
                not hierarchical_parent_missing
            )
        else:
            core_valid = (
                len(found_functions) >= 3 and
                len(forbidden_found) == 0 and
                not hierarchical_parent_missing
            )

        optional_valid = True
        optional_warnings = []
        required_blockers = []

        def add_required_blocker(key: str, message: str, details: Dict = None):
            blocker = {'key': key, 'message': message}
            if details:
                blocker.update(details)
            required_blockers.append(blocker)
            logger.error(f"   âŒ REQUIRED: {message}")

        if len(found_functions) < minimum_required_functions:
            add_required_blocker(
                'company_db_functions',
                f"Found {len(found_functions)}/6 required DB helpers. Need at least {minimum_required_functions}/6: {', '.join(required_functions)}",
                {'found_functions': found_functions, 'missing_functions': missing_functions}
            )

        if compcode_core_required and not compcode_pattern_found:
            add_required_blocker(
                'multi_company_filter',
                "Comp_Code company filter is mandatory for multi-company isolation"
            )

        if enforce_production_guards:
            if not has_transaction_pattern:
                add_required_blocker(
                    'transaction_management',
                    'funStartTran/funEndTran transaction handling is mandatory'
                )
            if not has_audit_pattern:
                add_required_blocker(
                    'audit_logging',
                    'fun_log audit trail is mandatory'
                )
            if not has_header_include:
                add_required_blocker('shared_header', 'Missing shared header include (topmenu.php)')
            if not has_sidebar_include:
                add_required_blocker('shared_sidebar', 'Missing shared sidebar include (sidemenu.php/rightmenu.php)')
            if not has_footer_include:
                add_required_blocker('shared_footer', 'Missing shared footer include (footer.php)')
            if not has_page_container:
                add_required_blocker('page_container', 'Missing company page container structure (page/page-content/panel)')
            if not has_form_horizontal_layout:
                add_required_blocker('form_horizontal_layout', 'Form must use company class `form-horizontal`')
            if not has_label_alignment:
                add_required_blocker('label_alignment', 'Form labels must use `control-label` and `col-md-*` alignment classes')
            if not formvalidation_pattern_found:
                add_required_blocker('form_validation', 'Frontend FormValidation initialization is mandatory')
            if not has_delegated_events:
                add_required_blocker('delegated_events', 'Delegated event handlers (.on(event, selector, ...)) are mandatory for AJAX navigation')
            if not has_ajax_reinit_guard:
                add_required_blocker('ajax_reinit_guard', 'Missing script reinitialization guard for dynamic DOM/AJAX reloads')
            if has_delete_action and not predelete_pattern_found:
                add_required_blocker('predelete_checks', 'Delete flow must include dependency checks before db_delete')

        if requested_fields and missing_requested_fields:
            if strict_field_enforcement:
                add_required_blocker(
                    'requested_fields',
                    f"Missing requested fields: {', '.join(missing_requested_fields[:12])}",
                    {'missing_fields': missing_requested_fields}
                )
            else:
                optional_warnings.append(
                    f"Requested fields partially missing (non-blocking): {', '.join(missing_requested_fields[:12])}"
                )
                logger.warning(
                    f"   ⚠️ Requested fields partially missing but non-blocking for simple prompt: "
                    f"{', '.join(missing_requested_fields[:12])}"
                )

        if requested_grid_fields and missing_requested_grid_fields:
            add_required_blocker(
                'requested_grid_fields',
                f"Missing requested detail-grid fields: {', '.join(missing_requested_grid_fields)}",
                {'missing_grid_fields': missing_requested_grid_fields}
            )

        if canonical_table_required and requested_table_name and not naming_table_found:
            add_required_blocker(
                'canonical_table_name',
                f"Canonical table name '{requested_table_name}' is missing from the generated code"
            )

        if canonical_file_required and requested_file_name and not naming_file_found:
            add_required_blocker(
                'canonical_file_name',
                f"Canonical file name '{requested_file_name}' is missing from the generated code"
            )

        if canonical_title_required and requested_title and not naming_title_found:
            add_required_blocker(
                'canonical_title',
                f"Canonical title '{requested_title}' is missing from the generated code"
            )

        if requested_entity_base and not entity_alignment_found:
            add_required_blocker(
                'entity_alignment',
                f"Generated form does not match requested entity '{requested_entity_raw}'"
            )

        if wants_dropdown and not dropdown_pattern_found:
            add_required_blocker('cascading_dropdown', 'Cascading dropdown pattern is required by the user request')

        if wants_keyboard and not keyboard_pattern_found:
            add_required_blocker('keyboard_navigation', 'Keyboard navigation/checkKeycode pattern is required by the user request')

        if wants_formvalidation and not formvalidation_pattern_found:
            add_required_blocker('form_validation', 'FormValidation rules are required by the user request')

        if wants_select2 and not select2_pattern_found:
            add_required_blocker('select2_cascading', 'Select2 integration is required by the user request')
        elif select2_focus_management_required and (not has_select2_close_events or not has_select2_focus_chain):
            add_required_blocker(
                'select2_focus_management',
                "Cascading Select2 focus management is required and must include both select2:close handlers and .select2('open') chaining"
            )

        if wants_grid and not grid_pattern_found:
            add_required_blocker('grid_pattern', 'Detail grid pattern is required by the user request')

        if wants_chart and not chart_pattern_found:
            add_required_blocker('chart_integration', 'Chart integration is required and must include ACC prefix + INSERT/UPDATE/DELETE flow')

        if wants_getcostcenter and not has_getcostcenter_handler:
            add_required_blocker('getcostcenter_handler', 'GetCOSTCENTER AJAX handler is required by the user request')

        if wants_predelete and not predelete_pattern_found:
            add_required_blocker('predelete_checks', 'Pre-delete dependency checks are required by the user request')

        if wants_multidelete and not multidelete_pattern_found:
            add_required_blocker('multidelete_loop', "Multi-delete loop with explode(',', $_REQUEST['major']) is required by the user request")

        if wants_transactions and not has_transaction_pattern:
            add_required_blocker('transaction_management', 'funStartTran/funEndTran transaction management is required by the user request')

        if wants_audit and not has_audit_pattern:
            add_required_blocker('audit_logging', 'fun_log audit calls are required by the user request')

        valid = core_valid and not required_blockers
        
        logger.info(f"ðŸŽ¯ Validation Strategy:")
        logger.info(f"   Core Patterns Valid: {core_valid}")
        logger.info(f"   Required Blockers: {len(required_blockers)}")
        logger.info(f"   Optional Patterns: {len(optional_warnings)} warnings")
        logger.info(f"   Final Valid: {valid}")
        
        logger.info(f"ðŸ” Company Function Validation:")
        logger.info(f"   Found: {found_functions} ({len(found_functions)}/6)")
        logger.info(f"   Missing: {missing_functions}")
        logger.info(
            f"   ðŸ†• AJAX Auto-ID Pattern: "
            f"{'âœ… Found' if ajax_pattern_found else ('âŒ Missing - CORE REQUIRED' if strict_company_validation else 'âšª Optional in relaxed mode')}"
        )
        logger.info(f"   ðŸ†• Pre-Delete Checks: {'âœ… Found' if predelete_pattern_found else ('âŒ Missing - REQUIRED' if wants_predelete else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Multi-Delete Loop: {'âœ… Found' if multidelete_pattern_found else ('âŒ Missing - REQUIRED' if wants_multidelete else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Chart Integration: {'âœ… Found' if chart_pattern_found else ('âŒ Missing - REQUIRED' if wants_chart else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Dynamic Dropdowns: {'âœ… Found' if dropdown_pattern_found else ('âŒ Missing - REQUIRED' if wants_dropdown else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• FormValidation: {'âœ… Found' if formvalidation_pattern_found else ('âŒ Missing - REQUIRED' if wants_formvalidation else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Keyboard Navigation: {'âœ… Found' if keyboard_pattern_found else ('âŒ Missing - REQUIRED' if wants_keyboard else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Select2 Integration: {'âœ… Found' if select2_pattern_found else ('âŒ Missing - REQUIRED' if wants_select2 else 'âšª Not Required')}")
        if select2_focus_management_required:
            logger.info(f"   ðŸ†• Select2 Focus Management: {'âœ… Found' if (has_select2_close_events and has_select2_focus_chain) else 'âŒ Missing - REQUIRED'}")
        logger.info(
            f"   ðŸ†• Multi-Company Filter: "
            f"{'âœ… Found' if compcode_pattern_found else ('âŒ Missing - CORE REQUIRED' if compcode_core_required else 'âšª Optional')}"
        )
        logger.info(
            f"   ðŸ†• Session Variables: "
            f"{'âœ… Found' if session_vars_pattern_found else ('âŒ Missing - CORE REQUIRED' if strict_company_validation else 'âšª Optional in relaxed mode')}"
        )
        logger.info(f"   ðŸ†• Grid Pattern: {'âœ… Found' if grid_pattern_found else ('âŒ Missing - REQUIRED' if wants_grid else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• GetCOSTCENTER Handler: {'âœ… Found' if has_getcostcenter_handler else ('âŒ Missing - REQUIRED' if wants_getcostcenter else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Transaction Management: {'âœ… Found' if has_transaction_pattern else ('âŒ Missing - REQUIRED' if wants_transactions else 'âšª Not Required')}")
        logger.info(f"   ðŸ†• Audit Logging: {'âœ… Found' if has_audit_pattern else ('âŒ Missing - REQUIRED' if wants_audit else 'âšª Not Required')}")
        if requested_fields:
            logger.info(f"   ðŸ†• Requested Fields Present: {'âœ…' if not missing_requested_fields else 'âŒ Missing: ' + ', '.join(missing_requested_fields[:6])}")
        if requested_table_name or requested_file_name or requested_title:
            logger.info(
                f"   ðŸ†• Canonical Naming: "
                f"table={'âœ…' if naming_table_found else 'âŒ'}, "
                f"file={'âœ…' if naming_file_found else 'âŒ'}, "
                f"title={'âœ…' if naming_title_found else 'âŒ'}"
            )
        if requested_entity_base:
            logger.info(
                f"   ðŸ†• Entity Alignment: "
                f"{'âœ…' if entity_alignment_found else 'âŒ Missing requested entity ' + requested_entity_raw}"
            )
        if forbidden_found:
            logger.warning(f"   âŒ Forbidden: {forbidden_found}")
        logger.info(f"   Valid: {valid}")
        if required_blockers:
            logger.error(f"   âŒ Required blockers: {', '.join(blocker['key'] for blocker in required_blockers)}")
        
        # If validation fails, provide specific guidance
        if not valid:
            if len(found_functions) < minimum_required_functions:
                logger.error(
                    f"   âŒ CRITICAL: Need at least {minimum_required_functions}/6 company functions "
                    "(enterprise minimum threshold)"
                )
                logger.error(f"   âŒ Missing critical functions: {missing_functions}")
            if forbidden_found:
                logger.error(f"   âŒ CRITICAL: Remove forbidden functions: {forbidden_found}")
            
            # Core patterns (always required)
            if strict_company_validation:
                if not ajax_pattern_found:
                    logger.error(f"   âŒ CRITICAL: AJAX Auto-ID pattern missing - CORE REQUIRED for company standard")
                if compcode_core_required and not compcode_pattern_found:
                    logger.error(f"   âŒ CRITICAL: Multi-company filter (Comp_Code) missing - CORE REQUIRED for multi-company support")
                elif not compcode_pattern_found:
                    logger.warning("   âš ï¸ Multi-company filter missing (non-blocking in current strict profile)")
                if not session_vars_pattern_found:
                    logger.error(f"   âŒ CRITICAL: Session variables missing - CORE REQUIRED for company audit support")
            else:
                if not ajax_pattern_found:
                    logger.warning("   âš ï¸ AJAX Auto-ID pattern missing (allowed in relaxed mode due weak retrieval context)")
                if not compcode_pattern_found:
                    logger.warning("   âš ï¸ Multi-company filter missing (allowed in relaxed mode due weak retrieval context)")
                if not session_vars_pattern_found:
                    logger.warning("   âš ï¸ Session variables missing (allowed in relaxed mode due weak retrieval context)")
            for blocker in required_blockers:
                logger.error(f"   âŒ REQUIRED FIX: {blocker['message']}")

        
        return {
            'valid': valid,
            'found_functions': found_functions,
            'missing_functions': missing_functions,
            'forbidden_functions': forbidden_found,
            'ajax_pattern_found': ajax_pattern_found,
            'predelete_pattern_found': predelete_pattern_found,
            'predelete_has_delete_action': has_delete_action,  # âœ… ISSUE #6 FIX: Track individual components
            'predelete_has_dependency_check': has_dependency_check,  # âœ… ISSUE #6 FIX
            'predelete_has_alert_message': has_alert_message,  # âœ… ISSUE #6 FIX
            'predelete_has_exit_statement': has_exit_statement,  # âœ… ISSUE #6 FIX
            'multidelete_pattern_found': multidelete_pattern_found,
            'multidelete_has_deletecase_check': has_deletecase_check,  # âœ… ISSUE #7 FIX: Track individual components
            'multidelete_has_explode_ids': has_explode_ids,  # âœ… ISSUE #7 FIX
            'multidelete_has_loop_through_ids': has_loop_through_ids,  # âœ… ISSUE #7 FIX
            'chart_pattern_found': chart_pattern_found,
            'chart_has_acc_prefix': has_acc_prefix,  # âœ… ISSUE #4 FIX: Track individual chart components
            'chart_has_chartcode_var': has_chartcode_var,  # âœ… ISSUE #4 FIX
            'chart_has_insert': has_chart_insert,  # âœ… ISSUE #4 FIX
            'chart_has_update': has_chart_update,  # âœ… ISSUE #4 FIX
            'chart_has_delete': has_chart_delete,  # âœ… ISSUE #4 FIX
            'dropdown_pattern_found': dropdown_pattern_found,
            'formvalidation_pattern_found': formvalidation_pattern_found,
            'keyboard_pattern_found': keyboard_pattern_found,
            'select2_pattern_found': select2_pattern_found,
            'select2_close_events_found': has_select2_close_events,  # âœ… ISSUE #3 FIX: Track close events
            'select2_focus_chain_found': has_select2_focus_chain,  # âœ… ISSUE #3 FIX: Track focus chain
            'select2_focus_management_required': select2_focus_management_required,
            'compcode_pattern_found': compcode_pattern_found,
            'compcode_core_required': compcode_core_required,
            'session_vars_pattern_found': session_vars_pattern_found,
            'grid_pattern_found': grid_pattern_found,
            'grid_has_txtcount_field': has_txtcount_field,  # âœ… ISSUE #8 FIX: Track individual components
            'grid_has_detail_loop': has_detail_loop,  # âœ… ISSUE #8 FIX
            'grid_has_dynamic_fields': has_dynamic_fields,  # âœ… ISSUE #8 FIX
            'grid_has_delete_old_records': has_delete_old_records,  # âœ… ISSUE #8 FIX
            'phase1_hierarchical_found': phase1_hierarchical_found,
            'phase1_cascading_parent_param': phase1_cascading_parent_param,
            'maxid_has_parent_param': maxid_has_parent_param,  # âœ… NEW: Track if maxid() has parent
            'core_valid': core_valid,
            'optional_valid': optional_valid,
            'optional_warnings': optional_warnings,  # âœ… ISSUE #3 FIX: Changed from "failures" to "warnings"
            'required_blockers': required_blockers,
            'missing_requested_fields': missing_requested_fields,
            'missing_requested_grid_fields': missing_requested_grid_fields,
            'getcostcenter_handler_found': has_getcostcenter_handler,
            'transaction_pattern_found': has_transaction_pattern,
            'audit_pattern_found': has_audit_pattern,
            'shared_header_found': has_header_include,
            'shared_sidebar_found': has_sidebar_include,
            'shared_footer_found': has_footer_include,
            'page_container_found': has_page_container,
            'form_horizontal_layout_found': has_form_horizontal_layout,
            'label_alignment_found': has_label_alignment,
            'delegated_events_found': has_delegated_events,
            'ajax_reinit_guard_found': has_ajax_reinit_guard,
            'minimum_required_company_functions': minimum_required_functions,
            'enforce_production_guards': enforce_production_guards,
            'naming_table_found': naming_table_found,
            'naming_file_found': naming_file_found,
            'naming_title_found': naming_title_found,
            'entity_alignment_found': entity_alignment_found,
            'requested_entity': requested_entity_raw,
            'request_table_name': request_metadata.get('table_name', ''),
            'request_file_name': request_metadata.get('file_name', ''),
            'request_entity_conflict': bool(request_metadata.get('has_entity_conflict')),
            'canonical_naming_required': canonical_requested,
            'canonical_table_required': canonical_table_required,
            'canonical_file_required': canonical_file_required,
            'canonical_title_required': canonical_title_required,
            'strict_field_enforcement': strict_field_enforcement,
            'strict_company_validation': strict_company_validation,
            'strict_validation_reason': strict_validation_reason,
            'user_requirements': {
                'wants_dropdown': wants_dropdown,
                'wants_keyboard': wants_keyboard,
                'wants_formvalidation': wants_formvalidation,
                'wants_select2': wants_select2,
                'wants_grid': wants_grid,
                'wants_chart': wants_chart,
                'wants_getcostcenter': wants_getcostcenter,
                'wants_multidelete': wants_multidelete,
                'wants_predelete': wants_predelete,
                'wants_transactions': wants_transactions,
                'wants_audit': wants_audit
            }
        }
    
    def _auto_repair_critical_blocks(
        self,
        code: str,
        validation_result: Dict,
        naming_metadata: Dict = None
    ) -> Tuple[str, bool]:
        """
        ✅ PHASE 1.3: AUTO-REPAIR LOGIC
        
        Automatically inject missing critical blocks that are required by company standards.
        This prevents validation failures for common missing patterns.
        
        Args:
            code: Generated PHP code
            validation_result: Validation result dict
            naming_metadata: Canonical naming metadata
        
        Returns:
            Tuple[repaired_code, was_repaired]
        """
        naming_metadata = naming_metadata or {}
        repaired = False
        repairs_made = []
        
        logger.info("🔧 AUTO-REPAIR: Checking for missing critical blocks...")
        
        # 1. Inject Comp_Code in WHERE clauses if missing
        if not validation_result.get('compcode_pattern_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting Comp_Code filters...")
            
            # Find SELECT queries without Comp_Code
            select_pattern = r"(SELECT\s+.*?\s+FROM\s+\w+\s+WHERE\s+)([^;]+)"
            matches = list(re.finditer(select_pattern, code, re.IGNORECASE | re.DOTALL))
            
            for match in matches:
                where_clause = match.group(2)
                if 'comp_code' not in where_clause.lower():
                    # Add Comp_Code filter
                    new_where = where_clause.rstrip() + " AND Comp_Code='\".$\\$_SESSION['comp_code'].\"'"
                    code = code.replace(match.group(0), match.group(1) + new_where)
                    repaired = True
            
            if repaired:
                repairs_made.append("Comp_Code filters in WHERE clauses")
        
        # 2. Inject session variables if missing
        if not validation_result.get('session_pattern_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting session variables...")
            
            # Find $columns array and add session fields
            columns_pattern = r"(\$columns\s*=\s*array\s*\([^)]*\))"
            if re.search(columns_pattern, code, re.IGNORECASE):
                # Add session variables to columns array
                session_vars = """
    $columns['User_ID'] = \\$_SESSION['user_id'];
    $columns['Login_ID'] = \\$_SESSION['login_id'];
    $columns['Comp_Code'] = \\$_SESSION['comp_code'];"""
                
                # Insert after $columns array declaration
                code = re.sub(
                    r"(\$columns\s*=\s*array\s*\([^)]*\);)",
                    r"\1" + session_vars,
                    code,
                    count=1,
                    flags=re.IGNORECASE
                )
                repaired = True
                repairs_made.append("Session variables (User_ID, Login_ID, Comp_Code)")
        
        # 3. Inject fun_log() calls after INSERT/UPDATE/DELETE
        if not validation_result.get('audit_pattern_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting audit logging (fun_log)...")
            
            # After db_insert
            code = re.sub(
                r"(db_insert\s*\([^)]+\);)",
                r"\1\n    fun_log('INSERT', \$table, \$Code);",
                code,
                flags=re.IGNORECASE
            )
            
            # After db_update
            code = re.sub(
                r"(db_update\s*\([^)]+\);)",
                r"\1\n    fun_log('UPDATE', \$table, \$Code);",
                code,
                flags=re.IGNORECASE
            )
            
            # After db_delete
            code = re.sub(
                r"(db_delete\s*\([^)]+\);)",
                r"\1\n    fun_log('DELETE', \$table, \$Code);",
                code,
                flags=re.IGNORECASE
            )
            
            if 'fun_log' in code:
                repaired = True
                repairs_made.append("Audit logging (fun_log)")
        
        # 4. Inject delegated event handlers if missing
        if not validation_result.get('delegated_events_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting delegated event handlers...")
            
            # Find button click handlers and convert to delegated events
            delegated_handler = """
$(document).on('click', '#btnSave', function() {
    btnsave_click();
});

$(document).on('click', '#btnEdit', function() {
    btnedit_click();
});

$(document).on('click', '#btnDelete', function() {
    btndelete_click();
});
"""
            
            # Insert before closing </script> tag
            if '</script>' in code and '$(document).on(' not in code:
                code = code.replace('</script>', delegated_handler + '\n</script>', 1)
                repaired = True
                repairs_made.append("Delegated event handlers")
        
        # 5. Inject AJAX reinit guard if missing
        if not validation_result.get('ajax_reinit_guard_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting AJAX reinit guard...")
            
            ajax_guard = """
// AJAX Reinit Guard - prevent duplicate event bindings
$(document).off('click', '.btn-save').on('click', '.btn-save', function() {
    // Save handler
});
"""
            
            # Insert after AJAX success handlers or at end of script section
            if '$.ajax' in code and '$(document).off(' not in code:
                code = re.sub(
                    r"(success:\s*function\s*\([^)]*\)\s*\{[^}]+\})",
                    r"\1\n" + ajax_guard,
                    code,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL
                )
                repaired = True
                repairs_made.append("AJAX reinit guard")
        
        # ✅ STEP 6: FIX PRE-DELETE INJECTION - Always inject FULL block
        if not validation_result.get('predelete_checks_found', False):
            logger.info("🔧 AUTO-REPAIR: Injecting pre-delete dependency checks...")
            
            # Get primary key/table hints from available naming metadata
            primary_key = naming_metadata.get('primary_key', 'Code')
            table_name = naming_metadata.get('table_name', 'tblentity')
            
            # ✅ STEP 6: ALWAYS inject COMPLETE Delete action block
            complete_delete_block = f"""
// Delete Action Handler with Pre-Delete Checks
if (isset(\\$_REQUEST['action']) && \\$_REQUEST['action'] == 'Delete') {{
    \\${primary_key} = \\$_REQUEST['{primary_key}'];
    
    // Check dependencies before delete
    \$check = getrows('tblcustomer', ' {primary_key}', add(\${primary_key}));
    if (\\$check > 0) {{
        echo "<script>alert('Cannot delete: record is being used in related tables');</script>";
        exit;
    }}
    
    // Proceed with delete
    funStartTran();
    \$filter = " {primary_key}='" . add(\${primary_key}) . "'";
    db_delete(\$table, \$filter);
    funEndTran();
    
    echo "<script>alert('Record deleted successfully');</script>";
}}
"""
            
            # Insert after PHP opening tag or at start of file
            if '<?php' in code:
                # Insert after <?php tag
                code = re.sub(
                    r"(<\?php\s*)",
                    r"\1\n" + complete_delete_block + "\n",
                    code,
                    count=1,
                    flags=re.IGNORECASE
                )
            else:
                # Prepend to file
                code = "<?php\n" + complete_delete_block + "\n" + code
            
            repaired = True
            repairs_made.append("Pre-delete dependency checks (FULL block)")
            logger.info("✅ AUTO-REPAIR: Injected COMPLETE Delete action block with pre-delete checks")
        
        # Log repair summary
        if repaired:
            logger.info(f"✅ AUTO-REPAIR: Successfully repaired {len(repairs_made)} critical blocks:")
            for repair in repairs_made:
                logger.info(f"   - {repair}")
        else:
            logger.info("ℹ️ AUTO-REPAIR: No repairs needed")
        
        return code, repaired
    
    def _calculate_section_completeness(
        self,
        sections: Dict[str, str],
        user_requirements: Dict = None
    ) -> Dict[str, float]:
        """
        ✅ PHASE 1.4: SECTION COMPLETENESS SCORING
        
        Calculate completeness percentage for each generated section.
        This helps identify "incorrect but non-empty" sections.
        
        Args:
            sections: Dict of section_name -> section_content
            user_requirements: What user requested
        
        Returns:
            Dict of section_name -> completeness_score (0-100%)
        """
        user_requirements = user_requirements or {}
        completeness = {}
        
        logger.info("📊 SECTION COMPLETENESS SCORING:")
        
        # 1. CRUD Operations Completeness (0-100%)
        crud_section = sections.get('CRUD_LOGIC_PHP', '')
        crud_score = 0
        crud_checks = {
            'has_save': bool(re.search(r"if.*txtmode.*save", crud_section, re.IGNORECASE)),
            'has_update': bool(re.search(r"if.*txtmode.*update", crud_section, re.IGNORECASE)),
            'has_delete': bool(re.search(r"if.*action.*delete", crud_section, re.IGNORECASE)),
            'has_edit': bool(re.search(r"if.*action.*edit", crud_section, re.IGNORECASE)),
            'has_db_insert': 'db_insert' in crud_section,
            'has_db_update': 'db_update' in crud_section,
            'has_db_delete': 'db_delete' in crud_section,
            'has_db_getrecord': 'db_getRecord' in crud_section or 'db_getrecord' in crud_section.lower(),
            'has_columns_array': '$columns' in crud_section,
            'has_transaction': 'funStartTran' in crud_section or 'funEndTran' in crud_section
        }
        crud_score = (sum(crud_checks.values()) / len(crud_checks)) * 100
        completeness['CRUD_LOGIC_PHP'] = crud_score
        logger.info(f"   CRUD Operations: {crud_score:.0f}% ({sum(crud_checks.values())}/{len(crud_checks)} checks)")
        
        # 2. AJAX Handlers Completeness (0-100%)
        ajax_section = sections.get('AJAX_HANDLERS_PHP', '')
        ajax_score = 0
        ajax_checks = {
            'has_getmaxid': bool(re.search(r"if.*Action.*GetMaxID", ajax_section, re.IGNORECASE)),
            'has_ajax_exit': 'exit' in ajax_section or 'die' in ajax_section,
            'has_json_response': 'echo' in ajax_section,
            'has_request_check': '$_REQUEST' in ajax_section or '$_POST' in ajax_section,
        }
        if user_requirements.get('wants_dropdown'):
            ajax_checks['has_cascading'] = bool(re.search(r"if.*SelectArea|SelectCity", ajax_section, re.IGNORECASE))
        
        ajax_score = (sum(ajax_checks.values()) / len(ajax_checks)) * 100 if ajax_checks else 0
        completeness['AJAX_HANDLERS_PHP'] = ajax_score
        logger.info(f"   AJAX Handlers: {ajax_score:.0f}% ({sum(ajax_checks.values())}/{len(ajax_checks)} checks)")
        
        # 3. Form Fields Completeness (0-100%)
        form_section = sections.get('FORM_FIELDS_HTML', '')
        form_score = 0
        form_checks = {
            'has_inputs': '<input' in form_section,
            'has_labels': '<label' in form_section,
            'has_form_group': 'form-group' in form_section or 'row' in form_section,
            'has_required_fields': 'required' in form_section or 'data-fv' in form_section,
        }
        if user_requirements.get('wants_dropdown'):
            form_checks['has_select'] = '<select' in form_section
        
        form_score = (sum(form_checks.values()) / len(form_checks)) * 100 if form_checks else 0
        completeness['FORM_FIELDS_HTML'] = form_score
        logger.info(f"   Form Fields: {form_score:.0f}% ({sum(form_checks.values())}/{len(form_checks)} checks)")
        
        # 4. Validation Completeness (0-100%)
        entity_js = sections.get('ENTITY_JS', '')
        validation_score = 0
        validation_checks = {
            'has_formvalidation_init': bool(re.search(r"\.formValidation\s*\(", entity_js, re.IGNORECASE)),
            'has_validators': 'validators' in entity_js,
            'has_fields_config': 'fields:' in entity_js,
        }
        if user_requirements.get('wants_formvalidation'):
            validation_checks['has_notempty'] = 'notEmpty' in entity_js
            validation_checks['has_framework'] = 'framework:' in entity_js
        
        validation_score = (sum(validation_checks.values()) / len(validation_checks)) * 100 if validation_checks else 0
        completeness['ENTITY_JS'] = validation_score
        logger.info(f"   Validation JS: {validation_score:.0f}% ({sum(validation_checks.values())}/{len(validation_checks)} checks)")
        
        # 5. Variable Init Completeness (0-100%)
        var_init = sections.get('VARIABLE_INIT_PHP', '')
        var_score = 0
        var_checks = {
            'has_form_var': '$form' in var_init,
            'has_form2_var': '$form2' in var_init,
            'has_table_var': '$table' in var_init,
            'has_title_var': '$title' in var_init,
        }
        var_score = (sum(var_checks.values()) / len(var_checks)) * 100
        completeness['VARIABLE_INIT_PHP'] = var_score
        logger.info(f"   Variable Init: {var_score:.0f}% ({sum(var_checks.values())}/{len(var_checks)} checks)")
        
        # 6. Overall Completeness
        overall_score = sum(completeness.values()) / len(completeness) if completeness else 0
        completeness['OVERALL'] = overall_score
        logger.info(f"   📊 OVERALL: {overall_score:.0f}%")
        
        # 7. Identify weak sections
        weak_sections = [name for name, score in completeness.items() if score < 50 and name != 'OVERALL']
        if weak_sections:
            logger.warning(f"   ⚠️ WEAK SECTIONS (<50%): {', '.join(weak_sections)}")
        
        return completeness
    
    def _format_field_names_for_prompt(self, fields: List[Dict]) -> str:
        """Format field names for MANDATORY block"""
        lines = []
        for field in fields[:10]:  # Show first 10 fields
            name = field.get('name', 'Unknown')
            lines.append(f"$columns['{name}'] = ...;  // âœ… CORRECT - PascalCase")
        return '\n'.join(lines)
    
    def _format_columns_example(self, fields: List[Dict]) -> str:
        """Format complete columns example for MANDATORY block"""
        lines = []
        for field in fields[:10]:  # Show first 10 fields
            name = field.get('name', 'Unknown')
            input_name = 'TXT' + name.upper().replace('_', '')
            lines.append(f"$columns['{name}']    = add($_POST['{input_name}']);")
        return '\n'.join(lines)
    
    def _extract_critical_patterns(self, company_examples: str, user_requirements: Dict) -> str:
        """
        âœ… ISSUE #12 FIX: Extract and highlight CRITICAL patterns from company examples
        
        This function extracts the ACTUAL code patterns that user requested:
        - FormValidation code (if wants_formvalidation=True)
        - Cascading dropdown code (if wants_dropdown=True)
        - Keyboard navigation code (if wants_keyboard=True)
        
        Returns: Highlighted pattern code to show BEFORE task description
        """
        
        if not company_examples:
            return ""

        extracted_patterns = []

        def extract_snippet(keyword_pattern: str, max_chars: int = 1400) -> str:
            match = re.search(keyword_pattern, company_examples, re.IGNORECASE)
            if not match:
                return ""
            start = max(0, match.start() - 180)
            end = min(len(company_examples), match.start() + max_chars)
            return company_examples[start:end].strip()

        if user_requirements.get('wants_formvalidation', False):
            form_validation_snippet = extract_snippet(r'\.formValidation\s*\(')
            if not form_validation_snippet:
                form_validation_snippet = extract_snippet(r'formvalidation\.min\.js')
            if form_validation_snippet:
                extracted_patterns.append(
                    "CRITICAL PATTERN: FORM VALIDATION (REQUIRED)\n"
                    "```javascript\n"
                    f"{form_validation_snippet}\n"
                    "```"
                )
                logger.info("Extracted FormValidation pattern from examples")

        if user_requirements.get('wants_dropdown', False):
            php_ajax_snippet = extract_snippet(r'if\s*\(\s*\$_REQUEST\s*\[\s*[\'"](?:Action|bnkId|bnkSubArea)[\'"]\s*\]')
            js_ajax_snippet = extract_snippet(r'\$\.ajax\s*\(')
            if php_ajax_snippet or js_ajax_snippet:
                blocks = ["CRITICAL PATTERN: CASCADING DROPDOWN + AJAX (REQUIRED)"]
                if php_ajax_snippet:
                    blocks.append("```php")
                    blocks.append(php_ajax_snippet)
                    blocks.append("```")
                if js_ajax_snippet:
                    blocks.append("```javascript")
                    blocks.append(js_ajax_snippet)
                    blocks.append("```")
                extracted_patterns.append('\n'.join(blocks))
                logger.info("Extracted Cascading Dropdown/AJAX pattern from examples")

        if user_requirements.get('wants_keyboard', False):
            keyboard_snippet = extract_snippet(r'function\s+checkKeycode\s*\(')
            if keyboard_snippet:
                extracted_patterns.append(
                    "CRITICAL PATTERN: KEYBOARD NAVIGATION (REQUIRED)\n"
                    "```javascript\n"
                    f"{keyboard_snippet}\n"
                    "```"
                )
                logger.info("Extracted Keyboard Navigation pattern from examples")

        if user_requirements.get('wants_select2', False):
            select2_snippet = extract_snippet(r'select2:close')
            if select2_snippet:
                extracted_patterns.append(
                    "CRITICAL PATTERN: SELECT2 FOCUS CHAIN (REQUIRED)\n"
                    "```javascript\n"
                    f"{select2_snippet}\n"
                    "```"
                )
                logger.info("Extracted Select2 focus pattern from examples")

        if user_requirements.get('wants_grid', False) or user_requirements.get('wants_chart', False):
            delete_snippet = extract_snippet(r'DeleteCase')
            if delete_snippet:
                extracted_patterns.append(
                    "CRITICAL PATTERN: PRE-DELETE + MULTI-DELETE (REQUIRED)\n"
                    "```php\n"
                    f"{delete_snippet}\n"
                    "```"
                )
                logger.info("Extracted delete/multi-delete pattern from examples")

        return '\n'.join(extracted_patterns) if extracted_patterns else ""
    
    def _build_structure_checklist(self, company_examples: str) -> str:
        """
        âœ… ISSUE #15 FIX: Build dynamic structure checklist from company examples
        
        Based on research: Company files have 14 mandatory patterns
        This function DETECTS which patterns exist in examples and creates checklist
        
        NOT HARDCODED - dynamically extracted from examples!
        """
        
        if not company_examples:
            return ""
        
        checklist_items = []
        
        # Detect patterns in examples (not hardcoded!)
        has_form_vars = bool(re.search(r'\$form2?\s*=', company_examples))
        has_getmaxid = bool(re.search(r"if.*Action.*GetMaxID", company_examples, re.I))
        has_delete_block = bool(re.search(r"if.*action.*Delete", company_examples, re.I))
        has_save_block = bool(re.search(r"if.*txtmode.*save", company_examples, re.I))
        has_columns_array = bool(re.search(r'\$columns\s*\[', company_examples))
        has_session_vars = bool(re.search(r'\$_SESSION\s*\[', company_examples))
        has_maxid_function = bool(re.search(r'function\s+maxid\s*\(', company_examples))
        has_btnsave = bool(re.search(r'function\s+btnsave_click', company_examples))
        has_checkkeycode = bool(re.search(r'function\s+checkKeycode', company_examples))
        has_formvalidation = bool(re.search(r'\.formValidation\s*\(', company_examples, re.I))
        has_hidden_fields = bool(re.search(r'txtmode|CTRL_HID_VALUE', company_examples))
        has_includes = bool(re.search(r'include\s*\(.*topmenu', company_examples, re.I))
        has_css_links = bool(re.search(r'formValidation.*css|bootstrap.*css', company_examples, re.I))
        has_js_scripts = bool(re.search(r'formValidation.*js|bootstrap.*js', company_examples, re.I))
        
        # Build checklist based on what EXISTS in examples
        checklist = "ðŸ”´ STRUCTURE COMPLETENESS CHECKLIST (From Company Examples):\n\n"
        checklist += "Your generated code MUST include ALL sections found in company examples:\n\n"
        
        if has_form_vars:
            checklist_items.append("âœ… PHP Variables: $form, $form2, $table, $title")
        if has_getmaxid:
            checklist_items.append("âœ… AJAX GetMaxID Block: if($_REQUEST['Action']=='GetMaxID') { ... exit; }")
        if has_delete_block:
            checklist_items.append("âœ… Delete Block: if($_REQUEST['action']=='Delete') with dependency checks")
        if has_save_block:
            checklist_items.append("âœ… Save/Update Block: if(isset($_POST['txtmode'])) with funStartTran()")
        if has_columns_array:
            checklist_items.append("âœ… $columns Array: $columns['FieldName'] = value;")
        if has_session_vars:
            checklist_items.append("âœ… Session Variables: $_SESSION['comp_code'], $_SESSION['user_id'], $_SESSION['login_id']")
        if has_maxid_function:
            checklist_items.append("âœ… JavaScript maxid() Function: function maxid() { $.post(...); }")
        if has_btnsave:
            checklist_items.append("âœ… JavaScript btnsave_click() Function")
        if has_checkkeycode:
            checklist_items.append("âœ… Keyboard Navigation: function checkKeycode(e, field)")
        if has_formvalidation:
            checklist_items.append("âœ… FormValidation: $('#frm').formValidation({...}).on('success.form.fv', ...)")
        if has_hidden_fields:
            checklist_items.append("âœ… Hidden Fields: <input type='hidden' id='txtmode'> and CTRL_HID_VALUE")
        if has_includes:
            checklist_items.append("âœ… PHP Includes: topmenu.php, sidemenu.php, formheader.php, footer.php")
        if has_css_links:
            checklist_items.append("âœ… CSS Links: formValidation.css, bootstrap.min.css")
        if has_js_scripts:
            checklist_items.append("âœ… JS Scripts: formValidation.min.js, bootstrap.min.js")
        
        if checklist_items:
            for i, item in enumerate(checklist_items, 1):
                checklist += f"{i}. {item}\n"
            
            checklist += f"\nðŸ”´ðŸ”´ðŸ”´ CRITICAL REQUIREMENTS ðŸ”´ðŸ”´ðŸ”´\n"
            checklist += f"âš ï¸ DETECTED {len(checklist_items)} MANDATORY PATTERNS in company examples\n"
            checklist += f"âš ï¸ Your code MUST include ALL {len(checklist_items)} patterns - do NOT skip ANY!\n"
            checklist += f"âš ï¸ Each pattern must be FULLY IMPLEMENTED (not abbreviated)\n"
            checklist += f"âš ï¸ Company example is 17,785 characters - yours must be 15,000+ minimum\n"
            checklist += f"\nâŒ FAILURE CONDITIONS:\n"
            checklist += f"   - Missing ANY of the {len(checklist_items)} patterns above\n"
            checklist += f"   - Output less than 15,000 characters\n"
            checklist += f"   - Using '// ... rest of code' or similar shortcuts\n"
            checklist += f"   - Incomplete functions or sections\n"
            
            logger.info(f"ðŸ“‹ Built structure checklist: {len(checklist_items)} patterns detected")
        else:
            checklist = ""  # No patterns detected, skip checklist
        
        return checklist

    
    def _build_inline_prompt(
        self,
        intent: Dict,
        sql_schema: str,
        company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        strict_mode: bool = False,
        user_requirements: Dict = None,  # ðŸ†• User requirements for smart prompt
        previous_attempts: List[Dict] = None,  # âœ… ISSUE #8 FIX: Previous failed attempts
        company_fields: Dict = None,  # âœ… PHASE 1: Extracted field names
        hierarchy_pattern: Dict = None,  # âœ… PHASE 1: Hierarchical code pattern
        related_tables: List[Dict] = None,  # âœ… PHASE 1: Related tables for delete checks
        cascading_logic: Dict = None,  # âœ… PHASE 1: Cascading dropdown logic
        grid_pattern: Dict = None,  # âœ… ISSUE #8 FIX: Grid/detail table pattern
        naming_metadata: Dict = None,  # âœ… NEW: Canonical file/table/title naming
        phase1_errors: List[str] = None  # âœ… NEW: Phase 1 specific errors
    ) -> str:
        """
        Build prompt for inline PHP+HTML generation using ACTUAL company patterns
        
        ðŸ†• SMART PROMPT: Only includes documentation for patterns user actually needs
        This reduces prompt size from 207KB to ~80KB
        
        âœ… ISSUE #8 FIX: Includes specific errors from previous attempts for better retry
        âœ… TIMEOUT FIX: Removed redundant sections, only include what's needed
        """
        
        # Get user requirements (what patterns they actually need)
        if user_requirements is None:
            user_requirements = {
                'wants_dropdown': False,
                'wants_keyboard': False,
                'wants_formvalidation': False,
                'wants_select2': False,
                'wants_grid': False,
                'wants_chart': False
            }
        
        logger.info(f"ðŸŽ¯ Building SMART prompt based on user requirements:")
        logger.info(f"   Include Dropdown docs: {user_requirements.get('wants_dropdown', False)}")
        logger.info(f"   Include Keyboard docs: {user_requirements.get('wants_keyboard', False)}")
        logger.info(f"   Include FormValidation docs: {user_requirements.get('wants_formvalidation', False)}")
        logger.info(f"   Include Select2 docs: {user_requirements.get('wants_select2', False)}")
        logger.info(f"   Include Grid docs: {user_requirements.get('wants_grid', False)}")
        logger.info(f"   Include Chart docs: {user_requirements.get('wants_chart', False)}")
        
        # âœ… PHASE 1: BUILD DYNAMIC TEMPLATES FROM EXTRACTED PATTERNS
        # Initialize with defaults if not provided
        if company_fields is None:
            company_fields = {'primary_key': 'Code', 'form_fields': [], 'parent_field': None}
        if hierarchy_pattern is None:
            hierarchy_pattern = {'is_hierarchical': False}
        if related_tables is None:
            related_tables = []
        if cascading_logic is None:
            cascading_logic = {'has_cascading': False}
        if grid_pattern is None:
            grid_pattern = {'has_grid': False, 'sub_table': None, 'grid_fields': [], 'txtcount_var': None, 'loop_var': None}
        if naming_metadata is None:
            naming_metadata = {}
        
        # Build field mapping instruction
        field_names_str = ', '.join(company_fields.get('form_fields', []))
        user_fields_str = ', '.join(company_fields.get('user_requested_fields', []))
        primary_key = company_fields.get('primary_key', 'Code')
        parent_field = company_fields.get('parent_field', 'N/A')
        parent_db_field = company_fields.get('parent_db_field', 'N/A')
        
        # âœ… STEP 5 FIX: Add user field count warning
        company_field_count = len(company_fields.get('form_fields', []))
        user_field_count = len(company_fields.get('user_requested_fields', []))
        
        field_count_warning = ""
        if user_field_count > 0 and user_field_count != company_field_count:
            field_count_warning = f"""
âš ï¸âš ï¸âš ï¸ FIELD COUNT MISMATCH DETECTED âš ï¸âš ï¸âš ï¸

User requested: {user_field_count} fields
Company example has: {company_field_count} fields

**User's Requested Fields:** {user_fields_str}

**ACTION REQUIRED:**
1. You MUST include ALL {user_field_count} fields user requested
2. Map user field names to company naming convention (PascalCase with underscores)
3. If company example doesn't have a field, CREATE it following company naming pattern

**Mapping Examples:**
- User: "customer_code" â†’ Company: "CUST_CODE" or "Code"
- User: "customer_name" â†’ Company: "NAME" or "Cust_Name"
- User: "phone" â†’ Company: "PHO_NO" or "Phone_No"
- User: "email" â†’ Company: "Email"
- User: "address" â†’ Company: "ADDRESS" or "Address"

**Naming Rules:**
- Use PascalCase with underscores: Cust_Name, Phone_No, Email
- First letter uppercase: NAME, ADDRESS, CITY
- Abbreviations OK: PHO_NO, NIC_NO, STN

âš ï¸âš ï¸âš ï¸ END FIELD COUNT WARNING âš ï¸âš ï¸âš ï¸
"""
        
        FIELD_MAPPING_INSTRUCTION = f"""
ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE A - FIX C-2: EXACT FIELD NAMES ENFORCEMENT ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - YOUR CODE WILL BE VALIDATED FOR THESE EXACT FIELD NAMES âš ï¸âš ï¸âš ï¸

ðŸ”´ RULE #1: USER FIELDS ONLY - NO EXTRA FIELDS FROM COMPANY EXAMPLE
The company example is for STRUCTURE and PATTERN reference ONLY.
You MUST generate form fields using ONLY the user-requested fields below.
DO NOT add any extra fields from the company example.

**User-Requested Fields (USE ONLY THESE):**
{user_fields_str if user_fields_str else 'No specific fields requested - use company example fields'}

**Company Example Fields (STRUCTURE REFERENCE ONLY - DO NOT COPY):**
- Primary Key: {primary_key}
- Form Fields ({company_field_count}): {field_names_str}
- Parent Field (HTML): {parent_field}
- Parent Field (Database): {parent_db_field}

{field_count_warning}

ðŸ”´ VALIDATION RULE C-2: Field Name Enforcement
Your generated code will be scanned for these EXACT field names:
- In $columns array: $columns['FieldName'], etc.
- In HTML inputs: name="FieldName", etc.
- In $_REQUEST: $_REQUEST['FieldName'], etc.

âŒ FORBIDDEN - These will cause VALIDATION FAILURE:
- Any field NOT in the user-requested fields list above
- Extra fields copied from company example
- Field names that don't match user request

âœ… REQUIRED - Use ONLY user-requested field names:
{user_fields_str if user_fields_str else field_names_str}

**Rule**: User's requested fields are AUTHORITY. Company example is for structure/pattern only.

Example Mapping (User â†’ Company Naming Convention):
- User: "Code" â†’ Company style: "Code" (PascalCase)
- User: "Name" â†’ Company style: "Name" or "Cust_Name"
- User: "Phone_No" â†’ Company style: "Phone_No" or "PHO_NO"
- User: "Email" â†’ Company style: "Email"
- User: "Address" â†’ Company style: "Address" or "ADDRESS"

**Naming Rules:**
- Use PascalCase with underscores: Cust_Name, Phone_No, Email
- First letter uppercase: NAME, ADDRESS, CITY
- Abbreviations OK: PHO_NO, NIC_NO, STN

âš ï¸ VALIDATION: If your code uses field names NOT in the user-requested list, it will FAIL validation!

ðŸ”´ðŸ”´ðŸ”´ END FIELD MAPPING ðŸ”´ðŸ”´ðŸ”´
"""
        
        # Build hierarchical code template
        if hierarchy_pattern.get('is_hierarchical'):
            parent_field_name = hierarchy_pattern.get('parent_field', 'Country_Code')
            parent_param = hierarchy_pattern.get('parent_request_param', 'SelectArea')
            separator = hierarchy_pattern.get('separator', '-')
            code_length = hierarchy_pattern.get('code_length', 2)
            
            # âœ… STEP 4 PHASE A - FIX C-1: Table Name Auto-Fix
            # Extract table name from intent and apply company naming convention
            table_name_raw = intent.get('database', {}).get('table_name', 'example')
            # Remove 'tbl' prefix if exists
            table_name_clean = table_name_raw.replace('tbl', '').replace('_', '').lower()
            # Apply company prefix (from dynamic pattern extractor)
            from agents.utils.dynamic_pattern_extractor import DynamicPatternExtractor
            extractor = DynamicPatternExtractor(analyzed_patterns)
            table_prefix = extractor.get_table_prefix()
            # Build correct table name: tblsubarea (no underscores)
            correct_table_name = f"{table_prefix}{table_name_clean}"
            
            HIERARCHICAL_CODE_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE A - FIXES C-1, C-3, C-4: HIERARCHICAL CODE WITH VALIDATION ðŸ”´ðŸ”´ðŸ”´

**Pattern Detected**: Parent-child relationship with hierarchical codes

ðŸ”´ FIX C-1: TABLE NAME AUTO-FIX
âš ï¸ CRITICAL: Use EXACT table name: {correct_table_name}
- NOT: {table_name_raw} (wrong format)
- NOT: tbl_{table_name_clean} (no underscores!)
- YES: {correct_table_name} (correct format)

ðŸ”´ FIX C-3: AJAX PARAMETER ENFORCEMENT
âš ï¸ CRITICAL: AJAX GetMaxID MUST receive parameter: {parent_param}
Your code will be validated for: {{Action:'GetMaxID', {parent_param}: {parent_param}}}

ðŸ”´ FIX C-4: CODE LENGTH ENFORCEMENT
âš ï¸ CRITICAL: Use {code_length}-digit code format
- RIGHT(Code,{code_length}) extracts last {code_length} digits
- LPAD(..., {code_length}, '0') pads to {code_length} digits
- Result: {separator.join(['LHR', '0' * code_length])} (NOT {separator.join(['LHR', '0001'])})

**PHP AJAX Handler** (Place after session_start):
```php
// AJAX Auto-ID Handler - Hierarchical Pattern
if(isset($_REQUEST['Action']) && $_REQUEST['Action']=='GetMaxID') {{{{
    ${parent_param} = $_REQUEST['{parent_param}'];  // âœ… C-3: Correct parameter name
    
    // âœ… C-1: Correct table name
    $MAXID = getvalue("SELECT LPAD(MAX(RIGHT(Code,{code_length})) + 1,{code_length},'0') 
                       FROM {correct_table_name} 
                       WHERE {parent_field_name} = '".${parent_param}."' 
                       AND Comp_Code='".$_SESSION['comp_code']."'");
    
    if($MAXID)
        $MAXID = ${parent_param}."{separator}".$MAXID;  // e.g., "LHR-01"
    else
        $MAXID = ${parent_param}."{separator}".str_pad(1, {code_length}, '0', STR_PAD_LEFT);  // âœ… C-4: {code_length} digits
    
    echo $MAXID;
    exit;
}}}}
```

**JavaScript maxid() Function**:
```javascript
function maxid() {{{{
    var {parent_param} = document.getElementById('{parent_field}').value;  // âœ… C-3: Correct parameter name
    
    if({parent_param} == '' || {parent_param} == '-1') {{{{
        $('#Code').val('');
        return;
    }}}}
    
    $.ajaxSetup({{{{async:false}}}});
    $.post("<?php echo $form2; ?>", {{{{Action:'GetMaxID', {parent_param}: {parent_param}}}}},  // âœ… C-3: Pass correct parameter
        function(data) {{{{ 
            if(data != '') {{{{
                $('#Code').val(data);
            }}}}
        }}}}
    );
}}}}
```

**Save Block - Code Generation**:
```php
if($_REQUEST['CTRL_HID_VALUE']!='Update') {{{{
    ${parent_param} = $_REQUEST['{parent_field}'];
    // âœ… C-1: Correct table name, âœ… C-4: Correct code length
    $MAXID = getvalue("SELECT LPAD(MAX(RIGHT(Code,{code_length})) + 1,{code_length},'0') 
                       FROM {correct_table_name} 
                       WHERE {parent_field_name} = '".${parent_param}."' 
                       AND Comp_Code='".$_SESSION['comp_code']."'");
    if($MAXID)
        $MAXID = ${parent_param}."{separator}".$MAXID;
    else
        $MAXID = ${parent_param}."{separator}".str_pad(1, {code_length}, '0', STR_PAD_LEFT);  // âœ… C-4: {code_length} digits
    $_REQUEST['Code'] = $MAXID;
}}}}
```

âš ï¸ VALIDATION RULES:
- C-1: Table name MUST be: {correct_table_name}
- C-3: AJAX MUST have: {{Action:'GetMaxID', {parent_param}: {parent_param}}}
- C-4: Code MUST use: RIGHT(Code,{code_length}) and LPAD(...,{code_length},'0')

âš ï¸ Code format MUST be: PARENT{separator}{'#' * code_length} (e.g., "LHR{separator}{'01' if code_length == 2 else '0001'}")
âš ï¸ NOT simple sequential: 0001, 0002, 0003

ðŸ”´ðŸ”´ðŸ”´ END HIERARCHICAL CODE ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            HIERARCHICAL_CODE_TEMPLATE = """
ðŸ”´ SIMPLE SEQUENTIAL CODE (No parent-child relationship detected)

Use standard sequential code generation:
```php
if(isset($_REQUEST['Action']) && $_REQUEST['Action']=='GetMaxID') {{
    $MAXID = getvalue("SELECT LPAD(MAX(Code) + 1,4,'0') FROM $table WHERE Comp_Code='".$_SESSION['comp_code']."'");
    if($MAXID=="") $MAXID = "0001";
    echo $MAXID;
    exit;
}}
```
"""
        
        # Build pre-delete checks template with MULTI-DELETE LOOP
        if related_tables:
            delete_checks_code = ""
            for rel in related_tables:
                table = rel['table']
                field = rel['field']
                message = rel['message']
                delete_checks_code += f"""
        // âœ… C-5: Check in {table}
        $filter_check = " {field} = '".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
        if(getrows2("{table}", $filter_check) >= 1) {{{{
            print "<script>alert('{message} for record: $major[$i]');</script>";
            // Don't exit - continue checking other records
        }}}} else {{{{
            // Delete if no dependency
            db_delete($table, $filter);
            fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
        }}}}
"""
            
            PRE_DELETE_CHECKS_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE A - FIX C-5: PRE-DELETE TABLES ENFORCEMENT ðŸ”´ðŸ”´ðŸ”´

**Pattern Detected**: Must check {len(related_tables)} related tables before delete + Support multi-delete

ðŸ”´ FIX C-5: PRE-DELETE TABLES ENFORCEMENT
âš ï¸ CRITICAL: Your code MUST check ALL {len(related_tables)} tables:
{chr(10).join([f'   - {r["table"]}.{r["field"]} (message: "{r["message"]}")' for r in related_tables])}

âš ï¸ VALIDATION: Your code will be scanned for:
{chr(10).join([f'   - getrows2("{r["table"]}", ...) check' for r in related_tables])}

**COMPLETE DELETE PATTERN (Single + Multi-Delete):**

```php
if(isset($_REQUEST['action']) && $_REQUEST['action'] == 'Delete') {{{{
    
    // âœ… STEP 7: Multi-Delete Support (Delete multiple records at once)
    if(isset($_REQUEST['DeleteCase']) && $_REQUEST['DeleteCase'] == 'Deleteall') {{{{
        // Split comma-separated IDs
        $major = explode(',', $_REQUEST['major']);
        
        // Loop through each record
        for($i = 0; $i < sizeof($major); $i++) {{{{
            $_REQUEST['major'] = $major[$i];
            
            $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
{delete_checks_code}
        }}}}
        
        print "<script>alert('Records Deleted.');</script>";
        print "<script>document.location='$form';</script>";
        exit;
    }}}}
    else {{{{
        // Single delete
        $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
{delete_checks_code.replace('$major[$i]', '$_REQUEST[\'major\']')}
        
        print "<script>alert('Record Deleted.');</script>";
        print "<script>document.location='$form';</script>";
        exit;
    }}}}
}}}}
```

**KEY FEATURES:**
1. âœ… Checks for DeleteCase == 'Deleteall' (multi-delete mode)
2. âœ… Explodes comma-separated IDs: explode(',', $_REQUEST['major'])
3. âœ… Loops through each ID: for($i=0; $i<sizeof($major); $i++)
4. âœ… C-5: Checks dependencies for EACH record in ALL {len(related_tables)} tables
5. âœ… Skips records with dependencies (shows alert but continues)
6. âœ… Deletes records without dependencies
7. âœ… Single delete fallback (else block)

âš ï¸ C-5 VALIDATION: Your code MUST include getrows2() checks for ALL these tables:
{', '.join([r['table'] for r in related_tables])}

âš ï¸ Use field name: {related_tables[0]['field'] if related_tables else 'entity_field'} (NOT Code!)

ðŸ”´ðŸ”´ðŸ”´ END PRE-DELETE WITH MULTI-DELETE ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            PRE_DELETE_CHECKS_TEMPLATE = """
ðŸ”´ SIMPLE DELETE WITH MULTI-DELETE SUPPORT (No related tables detected)

**COMPLETE DELETE PATTERN (Single + Multi-Delete):**

```php
if(isset($_REQUEST['action']) && $_REQUEST['action'] == 'Delete') {{{{
    
    // âœ… STEP 7: Multi-Delete Support
    if(isset($_REQUEST['DeleteCase']) && $_REQUEST['DeleteCase'] == 'Deleteall') {{{{
        $major = explode(',', $_REQUEST['major']);
        
        for($i = 0; $i < sizeof($major); $i++) {{{{
            $_REQUEST['major'] = $major[$i];
            $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
            db_delete($table, $filter);
            fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
        }}}}
        
        print "<script>alert('Records Deleted.');</script>";
        print "<script>document.location='$form';</script>";
        exit;
    }}}}
    else {{{{
        // Single delete
        $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
        db_delete($table, $filter);
        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
        print "<script>alert('Record Deleted.');</script>";
        print "<script>document.location='$form';</script>";
        exit;
    }}}}
}}}}
```

âš ï¸ VALIDATION: Your code will be scanned for:
- if($_REQUEST['DeleteCase'] == 'Deleteall')
- explode(',', $_REQUEST['major'])
- for($i=0; $i<sizeof($major); $i++)
"""
        
        # Build cascading dropdown template with COMPLETE Select2 pattern
        if cascading_logic.get('has_cascading'):
            parent_dropdown = cascading_logic.get('parent_dropdown') or 'Main_Area'
            child_dropdown = cascading_logic.get('child_dropdown') or 'Sub_Area'
            
            CASCADING_DROPDOWN_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ PHASE 1 FIX #4: SELECT2 CASCADING DROPDOWNS (COMPLETE PATTERN) ðŸ”´ðŸ”´ðŸ”´

**Pattern Detected**: Multi-level cascading dropdowns with Select2

**PART 1: PHP AJAX HANDLERS (Place after session_start, before HTML)**

```php
// AJAX Handler for Child Dropdown Population
if(isset($_REQUEST['bnkId']) && $_REQUEST['bnkId']) {{{{
    $data = array();
    $sql = mysql_query("SELECT Code, Description FROM {child_dropdown.replace('_', '').lower()} 
                        WHERE Country_Code='".$_REQUEST['bnkId']."' 
                        AND Comp_Code='".$_SESSION['comp_code']."' 
                        ORDER BY Description");
    
    $i = 1;
    $array_ = Array();
    while($brv_obj = mysql_fetch_object($sql)) {{{{
        $values = Array();
        array_push($values, $i);
        array_push($values, $brv_obj->Code);
        array_push($values, $brv_obj->Description);
        array_push($array_, $values);
        $i++;
    }}}}
    echo json_encode($array_);
    exit;
}}}}
```

**PART 2: JAVASCRIPT AJAX FUNCTIONS (Place in <script> section)**

```javascript
// Populate child dropdown based on parent selection
function {child_dropdown}() {{{{
    var ${child_dropdown} = $('#{child_dropdown}');
    ${child_dropdown}.empty();
    var j;
    var value = -1;
    
    $.ajax({{{{
        url: "<?php echo $form2; ?>",
        type: "POST",
        data: {{{{ bnkId: $('#{parent_dropdown}').val() }}}},
        dataType: "json",
        success: function(msg) {{{{
            ${child_dropdown}.append('<option selected="selected" value=' + value + '>SELECT</option>');
            for (var i = 0; i < msg.length; i++) {{{{
                j = 1;
                ${child_dropdown}.append('<option id=' + msg[i][j] + ' value=' + msg[i][j] + '>' + msg[i][j+1] + '</option>');
            }}}}
            ${child_dropdown}.change();
        }}}}
    }}}});
}}}}
```

**PART 3: SELECT2 EVENT HANDLERS (Place after FormValidation, before closing script tag)**

```javascript
// Select2 Cascading with Focus Management
$('#{parent_dropdown}')
.on("select2:close", function () {{{{
    setTimeout(function() {{{{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#{child_dropdown}').focus();
        $('#{child_dropdown}').select2('open');  // Auto-open next dropdown
    }}}}, 1);
}}}});

$('#{child_dropdown}')
.on("select2:close", function () {{{{
    setTimeout(function() {{{{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#txtname').focus();  // Move to first text field
    }}}}, 1);
}}}});

// Auto-open on focus for keyboard users
$('#{parent_dropdown}').focus(function() {{{{
    $('#{parent_dropdown}').select2('open');
}}}});

$('#{child_dropdown}').focus(function() {{{{
    $('#{child_dropdown}').select2('open');
}}}});
```

**PART 4: HTML PARENT DROPDOWN (REQUIRED)**

```html
<select class="form-control input-sm" 
        data-plugin="select2" 
        name="{parent_dropdown}" 
        id="{parent_dropdown}" 
        onKeyDown="checkKeycode(event,this.id);" 
        onChange="{child_dropdown}();maxid();"
        <?php if($_REQUEST['action'] == 'Update'){{{{ echo "disabled='disabled'"; }}}} ?>>
    <option value="-1">SELECT</option>
    <?php
    $sql = mysql_query("SELECT Code, Description FROM tblarea WHERE Comp_Code='".$_SESSION['comp_code']."' ORDER BY Description");
    while($Data_result = mysql_fetch_array($sql)) {{{{
        if($_REQUEST['action'] == 'Update') {{{{
    ?>
        <option <?php echo $obj['{parent_dropdown}'] == $Data_result['Code'] ? "selected='selected' value='".$Data_result['Code']."'" : "value='".$Data_result['Code']."'"; ?>><?php echo $Data_result['Description']; ?></option>
    <?php
        }}}} else {{{{
    ?>
        <option value="<?php echo $Data_result['Code']; ?>"><?php echo $Data_result['Description']; ?></option>
    <?php
        }}}}
    }}}}
    ?>
</select>
```

**PART 5: HTML CHILD DROPDOWN (REQUIRED)**

```html
<select class="form-control input-sm" 
        data-plugin="select2" 
        name="{child_dropdown}" 
        id="{child_dropdown}" 
        <?php if($_REQUEST['action'] == 'Update'){{{{ echo "disabled"; }}}} ?>
        onKeyDown="checkKeycode(event,this.id);">
    <option value="-1">SELECT</option>
    <?php
    if($_REQUEST['action'] == 'Update') {{{{
        $sql = mysql_query("SELECT Code, Description FROM tblsubarea WHERE Country_Code=SUBSTRING_INDEX('".$obj['{child_dropdown}']."','-',1) AND Comp_Code='".$_SESSION['comp_code']."'");
        while($res_n = mysql_fetch_array($sql)) {{{{
    ?>
        <option <?php echo $obj['{child_dropdown}'] == $res_n['Code'] ? "selected='selected' value='".$res_n['Code']."'" : "value='".$res_n['Code']."'"; ?>><?php echo $res_n['Description']; ?></option>
    <?php
        }}}}
    }}}} else {{{{
    ?>
        <option value="-1">SELECT</option>
    <?php
    }}}}
    ?>
</select>
```

**PART 6: BODY ONLOAD (Auto-open first dropdown on new record)**

```html
<body onLoad="<?php if($_REQUEST['action'] != 'Update') {{{{ ?> $('#{parent_dropdown}').select2('open'); <?php }}}} ?>">
```

**KEY FEATURES:**
1. âœ… AJAX dropdown population (bnkId handler)
2. âœ… Select2 event handlers (select2:close)
3. âœ… Focus chain management (parent â†’ child â†’ text field)
4. âœ… Auto-open on focus for keyboard users
5. âœ… Disabled parent on Update mode
6. âœ… Auto-open first dropdown on page load (new record)
7. âœ… onChange triggers maxid() for hierarchical code

âš ï¸ VALIDATION: Your code will be scanned for:
- PHP: if(isset($_REQUEST['bnkId']))
- JavaScript: function {child_dropdown}()
- Select2: .on("select2:close"
- HTML: data-plugin="select2"

If ANY are missing, validation will FAIL!

ðŸ”´ðŸ”´ðŸ”´ END SELECT2 CASCADING DROPDOWNS ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            CASCADING_DROPDOWN_TEMPLATE = ""
        
        # âœ… ISSUE #8 FIX: Build grid/detail table template
        if grid_pattern.get('has_grid'):
            sub_table = grid_pattern.get('sub_table', 'tbldetail')
            grid_fields = grid_pattern.get('grid_fields', ['SR_NO'])
            txtcount_var = grid_pattern.get('txtcount_var', 'TXTCOUNTACC')
            loop_var = grid_pattern.get('loop_var', 'i')
            
            # Build field assignments for grid
            grid_field_assignments = ""
            for field in grid_fields:
                grid_field_assignments += f"        $columns['{field}'] = $_REQUEST['{field}'.$i];\n"
            
            GRID_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ ISSUE #8 FIX: GRID/DETAIL TABLE PATTERN (DETECTED {len(grid_fields)} FIELDS) ðŸ”´ðŸ”´ðŸ”´

**Pattern Detected**: Sub-table '{sub_table}' with {len(grid_fields)} fields

**COMPLETE GRID SAVE PATTERN:**

```php
// 1. Delete old detail records before inserting new ones
db_delete($sub_table, " MAIN_CODE='".add($_REQUEST['Code'])."'");

// 2. Loop through grid rows and insert
for(${loop_var}=0; ${loop_var}<=$_REQUEST['{txtcount_var}']; ${loop_var}++)
{{{{
    if($_REQUEST['SR_NO'.${loop_var}]!='')
    {{{{
        $columns['MAIN_CODE'] = $code;  // Foreign key to main table
{grid_field_assignments}
        db_insert($sub_table, $columns);
        unset($columns);
    }}}}
}}}}
```

**HTML HIDDEN FIELD (REQUIRED):**
```html
<input type="hidden" id="{txtcount_var}" name="{txtcount_var}" >
```

**JAVASCRIPT GRID FUNCTIONS (REQUIRED):**
```javascript
var gridIndex = -1;
var gridData = new Array(1000);

function addGridRow() {{{{
    // Add row to grid
    document.getElementById('{txtcount_var}').value = index;
}}}}

function deleteGridRow(index) {{{{
    // Remove row from grid
    document.getElementById('{txtcount_var}').value = index - 1;
}}}}
```

**KEY FEATURES:**
1. âœ… Delete old records: db_delete($sub_table, ...)
2. âœ… Loop through rows: for(${loop_var}=0; ${loop_var}<=$_REQUEST['{txtcount_var}']; ${loop_var}++)
3. âœ… Dynamic field names: $_REQUEST['SR_NO'.${loop_var}]
4. âœ… Hidden counter: <input type="hidden" id="{txtcount_var}">

âš ï¸ MUST include ALL {len(grid_fields)} fields: {', '.join(grid_fields)}
âš ï¸ Use loop variable: ${loop_var} (NOT hardcoded!)

âš ï¸ VALIDATION: Your code will be scanned for:
- db_delete($sub_table, ...)
- for(${loop_var}=0; ${loop_var}<=$_REQUEST['{txtcount_var}']; ${loop_var}++)
- $_REQUEST['SR_NO'.${loop_var}]
- <input type="hidden" id="{txtcount_var}">

ðŸ”´ðŸ”´ðŸ”´ END GRID/DETAIL TABLE ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            GRID_TEMPLATE = ""
        
        # Build keyboard navigation template
        if company_fields.get('form_fields'):
            nav_chain = " â†’ ".join(company_fields['form_fields'][:5])  # First 5 fields
            
            KEYBOARD_NAV_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ PHASE 1 FIX #5: KEYBOARD NAVIGATION (FIELD SEQUENCE) ðŸ”´ðŸ”´ðŸ”´

**Detected Field Sequence**: {nav_chain} â†’ btnSave

Build navigation chain using ACTUAL field IDs (not made-up names):

```javascript
document.onkeydown = checkKeycode
function checkKeycode(e,field) {{{{
    var keycode;
    if (window.event) 
        keycode = window.event.keyCode;
    else if (e) 
        keycode = e.which;
    
    if(keycode == 13) {{{{
        // Build chain from ACTUAL fields detected above
        // Example: {parent_field} â†’ Description â†’ btnSave
    }}}}
}}}}
```

âš ï¸ Use ONLY fields that exist in form: {field_names_str}
âš ï¸ Do NOT navigate to non-existent fields!

ðŸ”´ðŸ”´ðŸ”´ END KEYBOARD NAVIGATION ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            KEYBOARD_NAV_TEMPLATE = ""
        
        # Build Chart of Accounts integration template
        # Detect if form needs chart integration (usually for Customer, Supplier, etc.)
        needs_chart_integration = False
        chart_prefix = "ACC_CUST"  # Default
        chart_function = "CustomerCode"  # Default
        
        # Check if company example has chart integration
        if 'chart' in company_examples.lower() and ('insert into chart' in company_examples.lower() or 'db_insert' in company_examples.lower()):
            needs_chart_integration = True
            logger.info("ðŸ” Detected Chart of Accounts integration in company code")
            
            # Extract chart prefix (e.g., ACC_CUST, ACC_SUPP)
            chart_prefix_match = re.search(r'(ACC_\w+)', company_examples)
            if chart_prefix_match:
                chart_prefix = chart_prefix_match.group(1)
                logger.info(f"ðŸ” Detected chart prefix: {chart_prefix}")
            
            # Extract chart function name (e.g., CustomerCode, SupplierCode)
            chart_func_match = re.search(r'function\s+(\w+Code)\s*\(', company_examples)
            if chart_func_match:
                chart_function = chart_func_match.group(1)
                logger.info(f"ðŸ” Detected chart function: {chart_function}()")
        
        if needs_chart_integration:
            primary_key = company_fields.get('primary_key', 'Code')
            name_field = 'txtname'  # Default, will be extracted from company code
            
            # Try to extract name field from company code
            name_field_match = re.search(r'\$_REQUEST\[["\'](\w*name\w*)["\']\]', company_examples, re.IGNORECASE)
            if name_field_match:
                name_field = name_field_match.group(1)
                logger.info(f"ðŸ” Detected name field: {name_field}")
            
            CHART_INTEGRATION_TEMPLATE = f"""
ðŸ”´ðŸ”´ðŸ”´ PHASE 1 FIX #6: CHART OF ACCOUNTS INTEGRATION (DETECTED) ðŸ”´ðŸ”´ðŸ”´

**Pattern Detected**: Automatic Chart of Accounts entry creation

**PART 1: HELPER FUNCTION (Place in include/data-layer.php or at top)**

```php
function {chart_function}($code) {{{{
    $length_code = substr($code, -7);  // Extract last 7 characters
    return $length_code;
}}}}
```

**PART 2: INSERT - Create Chart Entry (Place in Save block, AFTER db_insert)**

```php
// Generate Chart Account Code
$don = {chart_prefix}.{chart_function}($_REQUEST['{primary_key}']);

// Check if chart entry already exists
$ACC_CODE = getvalue("SELECT ACC_CODE FROM chart WHERE ACC_CODE='".$don."'");
if($ACC_CODE != "") {{{{
    echo "<script>alert('Chart Account Already Exists!');</script>";
    exit;
}}}}

// Insert main record
$var = db_insert($table, $columns);
fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['{primary_key}'], "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);

// Insert into Chart of Accounts
$qry_insert = "INSERT INTO chart (ACC_CODE, ACC_NAME, GRP_DET, COMP_CODE, LEVEL) 
               VALUES ('".$don."', '".add_Slashes_new($_REQUEST['{name_field}'])."', 'D', '".$_SESSION['comp_code']."', '4')";
@mysql_query($qry_insert);
```

**PART 3: UPDATE - Update Chart Entry (Place in Update block, AFTER db_update)**

```php
// Generate Chart Account Code
$don = {chart_prefix}.{chart_function}($_REQUEST['{primary_key}']);

// Update main record
$filter = "{primary_key}='".$_REQUEST['{primary_key}']."' AND Comp_Code='".$_SESSION['comp_code']."'";
$var = db_update($table, $columns, $filter);
fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['{primary_key}'], "Update", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);

// Update Chart of Accounts name
$qry_update = "UPDATE chart SET ACC_NAME = '".add_Slashes_new($_REQUEST['{name_field}'])."' 
               WHERE ACC_CODE = '".$don."'";
mysql_query($qry_update);
```

**PART 4: DELETE - Remove Chart Entry (Place in Delete block, AFTER db_delete)**

```php
// Generate Chart Account Code
$don = {chart_prefix}.{chart_function}(add($_REQUEST['major']));

// Delete main record
$filter = "{primary_key}='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
db_delete($table, $filter);
fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $form, add($_REQUEST['major']), "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);

// Delete from Chart of Accounts
$del = mysql_query("DELETE FROM chart WHERE ACC_CODE = '".$don."'");
```

**PART 5: ADD ACC_CODE COLUMN (Place in columns array)**

```php
// Add Chart Account Code to columns
$don = {chart_prefix}.{chart_function}($_REQUEST['{primary_key}']);
$columns['ACC_CODE'] = $don;
```

**KEY FEATURES:**
1. âœ… Auto-creates chart entry on INSERT
2. âœ… Auto-updates chart name on UPDATE
3. âœ… Auto-deletes chart entry on DELETE
4. âœ… Uses {chart_function}() to extract code
5. âœ… Uses {chart_prefix} constant prefix
6. âœ… Checks for duplicate chart entries
7. âœ… Maintains referential integrity

**CHART TABLE STRUCTURE:**
- ACC_CODE: Account code (e.g., "CUST-LHR-0001")
- ACC_NAME: Account name (customer/supplier name)
- GRP_DET: Group detail ('D' for detail account)
- COMP_CODE: Company code (multi-company support)
- LEVEL: Account level (4 for detail accounts)

âš ï¸ VALIDATION: Your code will be scanned for:
- PHP: INSERT INTO chart
- PHP: UPDATE chart SET ACC_NAME
- PHP: DELETE FROM chart
- PHP: function {chart_function}()

If ANY are missing, validation will FAIL!

ðŸ”´ðŸ”´ðŸ”´ END CHART OF ACCOUNTS INTEGRATION ðŸ”´ðŸ”´ðŸ”´
"""
        else:
            CHART_INTEGRATION_TEMPLATE = ""
        
        # Escape for template safety
        safe_examples = (company_examples or "").replace('{', '{{').replace('}', '}}')
        safe_intent = json.dumps(intent, indent=2).replace('{', '{{').replace('}', '}}')
        safe_sql = (sql_schema or "").replace('{', '{{').replace('}', '}}')
        safe_standards = (standards or "").replace('{', '{{').replace('}', '}}')
        
        # âœ… ISSUE #12 FIX: Extract critical patterns from examples
        # This shows the ACTUAL code patterns user requested, extracted from company examples
        # Placed prominently BEFORE task description so LLM sees them immediately
        critical_patterns = self._extract_critical_patterns(company_examples, user_requirements)
        safe_critical_patterns = critical_patterns.replace('{', '{{').replace('}', '}}')
        
        logger.info(f"ðŸ“ Critical patterns extracted: {len(critical_patterns)} chars")
        
        # Extract ACTUAL structural patterns from analyzed_patterns
        php_patterns = analyzed_patterns.get('php', {}) if analyzed_patterns else {}
        html_patterns = analyzed_patterns.get('html', {}) if analyzed_patterns else {}
        css_patterns = analyzed_patterns.get('css', {}) if analyzed_patterns else {}
        js_patterns = analyzed_patterns.get('js', {}) if analyzed_patterns else {}
        
        # ðŸ†• EXTRACT 12 ESSENTIAL PATTERNS FROM ANALYZED DATA
        # Map from actual analyzed_patterns structure to expected pattern names
        ajax_auto_id = php_patterns.get('ajax_functions', [])  # Use actual AJAX functions
        delete_checks = []  # Will be extracted from functions
        chart_integration = []  # Will be extracted from functions
        conditional_logic = php_patterns.get('functions', [])  # Use actual functions
        dynamic_dropdowns = php_patterns.get('ajax_functions', [])  # Use AJAX functions
        formvalidation = {}  # Will be extracted from JS patterns
        keyboard_navigation = {}  # Will be extracted from JS patterns
        grid_patterns = []  # Will be extracted from HTML patterns
        disabled_fields = []  # Will be extracted from HTML patterns
        asset_loading = {}  # Will be extracted from HTML patterns
        php_includes = php_patterns.get('functions', [])  # Use actual functions
        
        # Extract specific patterns from functions
        all_functions = php_patterns.get('functions', [])
        for func in all_functions:
            if isinstance(func, str):
                if 'delete' in func.lower() or 'getrows' in func.lower():
                    delete_checks.append(func)
                if 'chart' in func.lower() or 'acc_' in func.lower():
                    chart_integration.append(func)
        
        # Log extracted patterns
        logger.info(f"ðŸŽ¯ Extracted 12 Essential Patterns:")
        logger.info(f"   - AJAX Auto-ID: {len(ajax_auto_id)} patterns")
        logger.info(f"   - Delete Checks: {len(delete_checks)} patterns")
        logger.info(f"   - Chart Integration: {len(chart_integration)} patterns")
        logger.info(f"   - Dynamic Dropdowns: {len(dynamic_dropdowns)} patterns")
        logger.info(f"   - Grid Patterns: {len(grid_patterns)} patterns")
        logger.info(f"   - PHP Includes: {len(php_includes)} patterns")
        
        # Get table name and fields from intent
        raw_table_name = naming_metadata.get('table_name') or intent.get('database', {}).get('table_name', 'example')
        table_prefix_candidates = get_csv_setting(
            'CODEGEN_TABLE_PREFIX',
            'CODEGEN_TABLE_PREFIX',
            default=['tbl']
        )
        table_prefix = str(table_prefix_candidates[0]).strip().lower() if table_prefix_candidates else 'tbl'
        singularize_suffixes = self._keyword_list(
            'CODEGEN_TABLE_SINGULARIZE_SUFFIXES',
            ['s']
        )
        
        # ðŸ”´ ISSUE #1 FIX: Force correct table naming (tbl prefix + lowercase)
        # Intent might have 'customers', we need 'tblcustomer'
        raw_table_lower = str(raw_table_name).strip().lower()
        if not raw_table_lower.startswith(table_prefix):
            normalized_name = raw_table_lower
            for suffix in singularize_suffixes:
                if suffix and normalized_name.endswith(suffix) and len(normalized_name) > len(suffix):
                    normalized_name = normalized_name[: -len(suffix)]
                    break
            table_name = f"{table_prefix}{normalized_name}"
            logger.info(f"ðŸ”´ FIXED table name: '{raw_table_name}' â†’ '{table_name}'")
        else:
            table_name = raw_table_lower

        canonical_feature_name = naming_metadata.get('feature_name') or raw_table_name.replace('tbl', '').title()
        canonical_title = naming_metadata.get('title') or naming_metadata.get('case_type') or canonical_feature_name.replace('_', ' ')
        canonical_file_name = naming_metadata.get('file_name') or f"frm{canonical_feature_name}.php"
        
        fields = intent.get('database', {}).get('fields', [])
        
        # ðŸ”´ ISSUE #1 FIX: Map snake_case field names to company PascalCase naming
        # customer_id â†’ Code, first_name â†’ Cust_Name, phone_number â†’ Phone_No
        field_name_mapping = self._mapping_setting(
            'CODEGEN_FIELD_NAME_MAPPING',
            {
                'customer_id': 'Code',
                'id': 'Code',
                'code': 'Code',
                'first_name': 'Cust_Name',
                'last_name': 'Cust_Name',  # Combine into single name field
                'name': 'Cust_Name',
                'customer_name': 'Cust_Name',
                'phone': 'Phone_No',
                'phone_number': 'Phone_No',
                'mobile': 'Phone_No',
                'email': 'Email',
                'email_address': 'Email',
                'address': 'Address',
                'date_of_birth': 'DOB',
                'dob': 'DOB',
                'created_at': 'Created_Date',
                'updated_at': 'Updated_Date',
                'created_by': 'Created_By',
                'updated_by': 'Updated_By'
            }
        )
        
        # Convert field names to company standard
        company_fields = []
        for field in fields:
            field_name = field.get('name', '').lower()
            if field_name in field_name_mapping:
                mapped_name = field_name_mapping[field_name]
                logger.info(f"ðŸ”´ FIXED field name: '{field_name}' â†’ '{mapped_name}'")
                # Create new field dict with mapped name
                company_field = field.copy()
                company_field['name'] = mapped_name
                company_fields.append(company_field)
            else:
                # Convert to PascalCase if not in mapping
                # snake_case â†’ PascalCase: customer_type â†’ Customer_Type
                parts = field_name.split('_')
                pascal_name = '_'.join(word.capitalize() for word in parts)
                logger.info(f"ðŸ”´ CONVERTED field name: '{field_name}' â†’ '{pascal_name}'")
                company_field = field.copy()
                company_field['name'] = pascal_name
                company_fields.append(company_field)
        
        # Use company fields instead of original fields
        fields = company_fields if company_fields else fields
        
        # Extract company's actual coding patterns
        company_functions = php_patterns.get('functions', ['db_insert', 'db_update', 'db_delete', 'getvalue', 'getrows', 'add', 'noformat'])
        company_css_classes = html_patterns.get('css_classes', ['form-control', 'form-group', 'col-md-4', 'col-md-2', 'col-md-12', 'btn', 'btn-primary', 'btn-success', 'text-danger', 'text-right', 'panel', 'panel-body', 'container-fluid', 'row', 'row-lg'])
        company_form_structure = html_patterns.get('form_structure', 'form-horizontal')
        company_js_patterns = js_patterns.get('patterns', ['formValidation', 'checkKeycode', 'document.frm.submit()'])
        
        # ðŸ†• EXTRACT COMPANY VARIABLE NAMING PATTERNS
        company_variables = php_patterns.get('common_variables', ['$columns', '$filter', '$table', '$Code', '$form', '$title'])
        company_table_prefix = 'tbl'  # Company uses 'tbl' prefix
        company_field_naming = 'PascalCase'  # Company uses Cust_Code, Cust_Name style
        
        # Extract actual table names and field names from company codebase
        company_table_names = php_patterns.get('table_names', [])
        company_field_names = php_patterns.get('field_names', [])
        
        # Build CSS classes string for the prompt
        css_classes_str = ", ".join(company_css_classes) if company_css_classes else "form-control, form-group, col-md-4, col-md-2, btn, btn-primary, btn-success, text-danger, panel, panel-body, container-fluid, row, row-lg"
        
        strict_warning = ""
        if strict_mode:
            # âœ… ISSUE #8 FIX: Build SPECIFIC error feedback from previous attempts
            if previous_attempts and len(previous_attempts) > 0:
                last_attempt = previous_attempts[-1]
                validation = last_attempt['validation_result']
                
                # Build specific error list
                specific_errors = []
                
                # Handle both List[str] and List[Dict] formats for safety
                missing_funcs = validation.get('missing_functions', [])
                forbidden_funcs = validation.get('forbidden_functions', [])
                found_funcs = validation.get('found_functions', [])
                optional_warnings = validation.get('optional_warnings', [])  # âœ… ISSUE #3 FIX: Changed from failures to warnings
                required_blockers = validation.get('required_blockers', [])
                
                if missing_funcs:
                    if missing_funcs and isinstance(missing_funcs[0], dict):
                        missing_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in missing_funcs])
                    else:
                        missing_str = ', '.join([str(f) for f in missing_funcs])
                    specific_errors.append(f"âŒ MISSING FUNCTIONS: {missing_str}")
                
                if forbidden_funcs:
                    if forbidden_funcs and isinstance(forbidden_funcs[0], dict):
                        forbidden_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in forbidden_funcs])
                    else:
                        forbidden_str = ', '.join([str(f) for f in forbidden_funcs])
                    specific_errors.append(f"âŒ FORBIDDEN FUNCTIONS USED: {forbidden_str}")
                
                if not validation.get('ajax_pattern_found', False):
                    specific_errors.append("âŒ AJAX Auto-ID pattern NOT found (need $.ajax, $.post, GetMaxID, LPAD)")
                if validation.get('compcode_core_required', False) and not validation.get('compcode_pattern_found', False):
                    specific_errors.append("âŒ Comp_Code filter NOT found (need WHERE Comp_Code='\".$_SESSION['comp_code'].\"')")
                if not validation.get('session_vars_pattern_found', False):
                    specific_errors.append("âŒ Session variables NOT found (need $_SESSION['login_id'], $_SESSION['comp_code'])")
                for blocker in required_blockers:
                    specific_errors.append(f"âŒ REQUIRED PATTERN: {blocker.get('message', blocker.get('key', 'missing required pattern'))}")
                
                # âœ… ISSUE #3 FIX: Optional patterns are now WARNINGS, not errors (don't block generation)
                # Only show as informational warnings, not critical errors
                optional_warnings_text = []
                if optional_warnings:
                    if optional_warnings and isinstance(optional_warnings[0], dict):
                        opt_str = ', '.join([str(o.get('name', o.get('pattern', ''))) for o in optional_warnings])
                    else:
                        opt_str = ', '.join([str(o) for o in optional_warnings])
                    optional_warnings_text.append(f"âš ï¸ OPTIONAL PATTERNS MISSING (not critical): {opt_str}")
                    if 'cascading_dropdown' in optional_warnings:
                        optional_warnings_text.append("   â†’ Recommended: onChange='maxid()' and AJAX dropdown population")
                    if 'keyboard_navigation' in optional_warnings:
                        optional_warnings_text.append("   â†’ Recommended: checkKeycode() function and onkeydown handlers")
                    if 'form_validation' in optional_warnings:
                        optional_warnings_text.append("   â†’ Recommended: $('#frm').formValidation() with field validators")
                    if 'select2_cascading' in optional_warnings:
                        optional_warnings_text.append("   â†’ Recommended: data-plugin='select2' and .on('select2:close') event handlers")
                    if 'select2_focus_management' in optional_warnings:
                        optional_warnings_text.append("   â†’ Requested: complete .on('select2:close') and .select2('open') focus chaining for cascading Select2 dropdowns")
                    if 'chart_integration' in optional_warnings:
                        optional_warnings_text.append("   â†’ Recommended: INSERT INTO chart, UPDATE chart, DELETE FROM chart")
                
                specific_errors_text = '\n'.join(specific_errors)
                optional_warnings_display = '\n'.join(optional_warnings_text) if optional_warnings_text else ''
                
                # Format found and missing functions for display
                if found_funcs and isinstance(found_funcs[0], dict):
                    found_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in found_funcs])
                else:
                    found_str = ', '.join([str(f) for f in found_funcs]) if found_funcs else 'NONE'
                
                if missing_funcs and isinstance(missing_funcs[0], dict):
                    still_missing_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in missing_funcs])
                else:
                    still_missing_str = ', '.join([str(f) for f in missing_funcs]) if missing_funcs else 'NONE'
                
                # Format forbidden functions for display
                if forbidden_funcs and isinstance(forbidden_funcs[0], dict):
                    forbidden_display_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in forbidden_funcs])
                else:
                    forbidden_display_str = ', '.join([str(f) for f in forbidden_funcs]) if forbidden_funcs else 'NONE (Good!)'
                
                strict_warning = f"""
ðŸ”´ðŸ”´ðŸ”´ CRITICAL - ATTEMPT {len(previous_attempts) + 1}/{3} - FIX THESE SPECIFIC ERRORS ðŸ”´ðŸ”´ðŸ”´

YOUR PREVIOUS ATTEMPT #{last_attempt['attempt_number']} WAS REJECTED FOR THESE SPECIFIC REASONS:

{specific_errors_text}

{f'''
ðŸ“‹ OPTIONAL IMPROVEMENTS (not critical, but recommended):

{optional_warnings_display}
''' if optional_warnings_display else ''}

WHAT YOU GENERATED (First 500 chars):
```php
{last_attempt['code_snippet']}
```

âœ… THIS ATTEMPT MUST FIX ALL CRITICAL ERRORS ABOVE:

1. **MISSING FUNCTIONS** - You MUST use these company functions:
   âœ… db_insert($table, $columns) - For INSERT operations
   âœ… db_update($table, $columns, $filter) - For UPDATE operations  
   âœ… db_delete($table, $filter) - For DELETE operations
   âœ… db_getRecord($sql) - For SELECT queries (returns resource)
   âœ… getrows($sql) - For fetching multiple rows
   âœ… getvalue($sql) - For fetching single value
   
   FOUND: {found_str}
   STILL MISSING: {still_missing_str}

2. **FORBIDDEN FUNCTIONS** - NEVER use these:
   âŒ mysqli_query, mysqli_fetch, new mysqli
   âŒ new PDO, $pdo->query
   âŒ Direct mysql_query without db_getRecord()
   
   YOU USED: {forbidden_display_str}

3. **AJAX AUTO-ID PATTERN** - You MUST include:
   âœ… PHP: if($_REQUEST['Action']=='GetMaxID') {{ ... }}
   âœ… PHP: $maxid = getvalue("SELECT MAX(Code) FROM ...");
   âœ… PHP: echo LPAD($maxid+1, 4, '0');
   âœ… JS: function maxid() {{ $.post('?', {{Action:'GetMaxID'}}, function(data){{ ... }}); }}
   âœ… JS: $(document).ready(function(){{ maxid(); }});

4. **COMP_CODE FILTER** - You MUST include in ALL queries:
   âœ… WHERE Comp_Code='".$_SESSION['comp_code']."'
   âœ… $columns['Comp_Code'] = $_SESSION['comp_code'];

5. **SESSION VARIABLES** - You MUST include:
   âœ… session_start(); or @session_start();
   âœ… $_SESSION['login_id'] for audit fields
   âœ… $_SESSION['comp_code'] for multi-company filter

âš ï¸ THIS IS YOUR LAST CHANCE - If this attempt fails, code will be rejected!
âš ï¸ COPY the patterns from company examples EXACTLY - don't improvise!
"""
            else:
                # Fallback if no previous attempts (shouldn't happen)
                strict_warning = """
âš ï¸ STRICT MODE - PREVIOUS ATTEMPT FAILED VALIDATION âš ï¸

Your previous attempt was REJECTED because:
- It did NOT use enough company database functions
- It may have used forbidden functions like mysqli_query() or new PDO()

THIS ATTEMPT MUST:
âœ… Use AT LEAST 5 company functions: db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
âœ… Use NO forbidden functions: mysqli_query, mysqli_fetch, new mysqli, new PDO
âœ… Follow company structure EXACTLY
âœ… Include AJAX Auto-ID pattern
âœ… Include Comp_Code filter in ALL queries
âœ… Include session variables (login_id, comp_code)

If this attempt also fails, the code will be rejected and the user will see an error.
"""
        
        # ðŸ†• CRITICAL: Variable and Table/Field Naming Rules
        naming_rules = """
ðŸ”´ðŸ”´ðŸ”´ CRITICAL INSTRUCTION - VARIABLE NAMING ðŸ”´ðŸ”´ðŸ”´

YOU MUST USE THESE EXACT VARIABLE NAMES (Company Standard):

1. **Database Operations:**
   âœ… USE: $columns = array();  // For INSERT/UPDATE data
   âŒ DON'T USE: $data, $record, $values, $row
   
   âœ… USE: $filter = "Code='".$Code."'";  // For WHERE clauses
   âŒ DON'T USE: $where, $condition, $criteria
   
   âœ… USE: $table = 'tblcustomer';  // Table name variable
   âŒ DON'T USE: $tableName, $tbl, $table_name

2. **Primary Key Variable:**
   âœ… USE: $Code  // Primary key value (PascalCase)
   âŒ DON'T USE: $id, $code, $primaryKey, $pk

3. **Table Naming Convention:**
   âœ… USE: tblcustomer, tblsupplier, tblarea, tblsubarea
   âŒ DON'T USE: customers, suppliers, areas, sub_areas
   RULE: Always prefix with 'tbl' + lowercase name

4. **Field Naming Convention:**
   âœ… USE: Cust_Code, Cust_Name, Email, Phone_No
   âŒ DON'T USE: customer_id, customer_name, email_address, phone_number
   RULE: PascalCase with underscores (First_Second_Third)

EXAMPLE - CORRECT USAGE:
```php
$table = 'tblcustomer';
$Code = $_POST['TXTCUSTCODE'];
$columns = array();
$columns['Cust_Code'] = $Code;
$columns['Cust_Name'] = add_Slashes_new($_POST['TXTCUSTNAME']);
$columns['Email'] = $_POST['TXTEMAIL'];
$columns['Comp_Code'] = $_SESSION['comp_code'];

$filter = " Cust_Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";

if(getrows($table, "Cust_Code", $Code) == '1') {{
    db_update($table, $columns, $filter);
}} else {{
    db_insert($table, $columns);
}}
```

EXAMPLE - WRONG USAGE (Will FAIL validation):
```php
$tableName = 'customers';  // âŒ Wrong variable name and table name
$id = $_POST['ID'];  // âŒ Wrong variable name
$data = array();  // âŒ Wrong variable name
$data['customer_id'] = $id;  // âŒ Wrong field name
$data['customer_name'] = $_POST['NAME'];  // âŒ Wrong field name

$where = "customer_id='".$id."'";  // âŒ Wrong variable name

if(getrows($tableName, "customer_id", $id) == '1') {{
    db_update($tableName, $data, $where);
}} else {{
    db_insert($tableName, $data);
}}
```

âš ï¸ VALIDATION REQUIREMENT:
Your code will be scanned for these variable names:
- $columns (REQUIRED)
- $filter (REQUIRED)
- $table (REQUIRED)
- $Code (REQUIRED)

If you use $data, $where, $id instead, validation will FAIL!

Table name MUST start with 'tbl' prefix!
Field names MUST use PascalCase_With_Underscores!

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL INSTRUCTION ðŸ”´ðŸ”´ðŸ”´
"""
        
        # ðŸ”´ CRITICAL: Add explicit warning about CORRECT usage
        mysql_fetch_warning = """
ðŸ”´ðŸ”´ðŸ”´ CRITICAL INSTRUCTION - PRE-DELETE CHECKS ðŸ”´ðŸ”´ðŸ”´

Your DELETE logic MUST follow this EXACT pattern from company code:

```php
if($_REQUEST['action'] == 'Delete')
{{
    // âš ï¸ MANDATORY: Check ALL related tables BEFORE deleting
    
    // Example 1: Check if record is used in transactions
    $filter_check = " Record_ID='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    if(getrows2("transactions", $filter_check) >= 1)
    {{
        print "<script>alert('This record exists in Transactions. Cannot delete!');</script>";
        print "<script>document.location='$form'; </script>";
        exit;
    }}
    
    // Example 2: Check if record is used in invoices
    $filter_check = " Record_ID='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    if(getrows2("invoices", $filter_check) >= 1)
    {{
        print "<script>alert('This record exists in Invoices. Cannot delete!');</script>";
        print "<script>document.location='$form'; </script>";
        exit;
    }}
    
    // Add more checks for other related tables...
    
    // Only delete if ALL checks pass
    $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    db_delete($table, $filter);
    fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
    print "<script>alert('Record Deleted.'); </script>";
    print "<script>document.location='$form'; </script>";
}}
```

âš ï¸ VALIDATION REQUIREMENT:
Your code will be scanned for these 4 components:
1. if($_REQUEST['action'] == 'Delete')
2. getrows2( - for checking related tables
3. print "<script>alert( - for error messages
4. exit; - to stop execution if dependency found

If ANY are missing, validation will FAIL and code will be REJECTED.

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL INSTRUCTION ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ CRITICAL INSTRUCTION - AJAX AUTO-ID PATTERN ðŸ”´ðŸ”´ðŸ”´

Your code MUST include AJAX Auto-ID generation pattern:

**PHP Side (at top of file):**
```php
// AJAX call for auto-generating next ID
if($_REQUEST['Action']=='GetMaxID')
{{
    {f"$MAXID=getvalue(\"SELECT LPAD(MAX(RIGHT(Code,{hierarchy_pattern.get('code_length', 4)})) + 1,{hierarchy_pattern.get('code_length', 4)},'0') FROM $table WHERE {hierarchy_pattern.get('parent_field', 'Comp_Code')}='\".$_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"'\");" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else "$MAXID=getvalue(\"SELECT LPAD(MAX(Code) + 1,4,'0') FROM $table WHERE Comp_Code='\".$_SESSION['comp_code'].\"'\");"}
    if($MAXID=="") {{
        {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-0001\";" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else '$MAXID = "0001";'}
    }} else {{
        {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-\".$MAXID;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
    }}
    echo $MAXID;
    exit;
}}
```

**JavaScript Side (in <script> section):**
```javascript
function maxid() {{
    {f"var {hierarchy_pattern.get('parent_request_param', 'SelectArea')} = document.getElementById('{hierarchy_pattern.get('parent_js_field_id', 'Main_Area')}').value;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
    $.ajaxSetup({{async:false}});
    $.post("<?php echo $form2; ?>", {{Action:'GetMaxID'{f", {hierarchy_pattern.get('parent_request_param', 'SelectArea')}: {hierarchy_pattern.get('parent_request_param', 'SelectArea')}" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}}}, function(data) {{ 
        if(data != '') {{
            $('#Code').val(data);
        }}
    }});
}}
```

**HTML Side (in <body> tag):**
```html
<body onLoad="maxid();">
```

âš ï¸ VALIDATION REQUIREMENT:
Your code will be scanned for these 4 components:
1. if($_REQUEST['Action']=='GetMaxID')
2. function maxid()
3. $.post(
4. Action:'GetMaxID'

If ANY are missing, validation will FAIL and code will be REJECTED.

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL INSTRUCTION ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ CRITICAL INSTRUCTION - GRID/DETAIL RECORDS PATTERN ðŸ”´ðŸ”´ðŸ”´

If user mentions "grid", "line items", "detail records", "master-detail", or "invoice items", 
you MUST include this COMPLETE grid pattern:

**JavaScript Side (in <script> section):**
```javascript
var gridIndex = 0;
var gridData = new Array(1000);
for(var i=0; i<1000; i++) {{
    gridData[i] = new Array(10);  // Adjust size based on columns
}}

function addGridRow() {{
    var row = '<tr id="row' + gridIndex + '">';
    row += '<td>' + (gridIndex + 1) + '</td>';
    row += '<td><input type="text" class="form-control" name="Field1' + gridIndex + '" id="Field1' + gridIndex + '" /></td>';
    row += '<td><input type="text" class="form-control" name="Field2' + gridIndex + '" id="Field2' + gridIndex + '" /></td>';
    row += '<td><button type="button" class="btn btn-danger btn-sm" onclick="deleteGridRow(' + gridIndex + ')">Delete</button></td>';
    row += '</tr>';
    
    $('#gridTableBody').append(row);
    document.getElementById('TXTCOUNTACC').value = gridIndex;
    gridIndex++;
}}

function deleteGridRow(index) {{
    $('#row' + index).remove();
}}
```

**HTML Side (in form):**
```html
<div class="form-group">
    <div class="col-md-12">
        <h4>Detail Records</h4>
        <button type="button" class="btn btn-primary btn-sm" onclick="addGridRow()">Add Row</button>
        <table class="table table-bordered" id="gridTable">
            <thead>
                <tr>
                    <th>Sr#</th>
                    <th>Field 1</th>
                    <th>Field 2</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody id="gridTableBody">
                <!-- Rows added dynamically -->
            </tbody>
        </table>
        <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="0">
    </div>
</div>
```

**PHP Side (save detail records):**
```php
// Save detail records
for($i=0; $i<=$_REQUEST['TXTCOUNTACC']; $i++) {{
    if($_REQUEST['Field1'.$i] != '') {{
        $detail_columns['MasterCode'] = $Code;
        $detail_columns['SR_NO'] = $i + 1;
        $detail_columns['Field1'] = add($_REQUEST['Field1'.$i]);
        $detail_columns['Field2'] = add($_REQUEST['Field2'.$i]);
        $detail_columns['Comp_Code'] = $_SESSION['comp_code'];
        
        db_insert($detail_table, $detail_columns);
    }}
}}
```

âš ï¸ VALIDATION REQUIREMENT:
Your code will be scanned for these 4 components:
1. var gridIndex
2. function addGridRow(
3. function deleteGridRow(
4. TXTCOUNTACC

If ANY are missing when user requests grid, validation will FAIL and code will be REJECTED.

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL INSTRUCTION ðŸ”´ðŸ”´ðŸ”´

REQUIRED FUNCTIONS (ALL 6 MUST BE PRESENT):
1. db_insert($table, $columns) - For creating new records
2. db_update($table, $columns, $filter) - For updating existing records  
3. db_delete($table, $filter) - For deleting records
4. db_getRecord($table, $filter) - For retrieving single record
5. getrows($table, $field, $value) - For checking if record exists
6. getvalue($query) - For getting single values (like MAX ID)

COMPLETE CRUD EXAMPLE (COPY THIS STRUCTURE):
```php
// 1. GET NEXT ID
$dbId = getvalue("SELECT max(Code)+1 from $table WHERE Comp_Code='".$_SESSION['comp_code']."'");
if($dbId=="") {{ $Code = '01'; }} else {{ $Code = noformat($dbId, 2); }}

// 2. DELETE OPERATION
if($_REQUEST['action'] == 'Delete') {{
    $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    db_delete($table, $filter);  // âœ… FUNCTION 3
    fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
}}

// 3. UPDATE DISPLAY
if($_REQUEST['action'] == 'Update') {{
    $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    $obj = db_getRecord($table, $filter);  // âœ… FUNCTION 4
    $Code = noformat($obj[0], 2);
}}

// 4. SAVE/UPDATE OPERATION
if(isset($_POST["txtmode"]) and $_POST["txtmode"]=="save") {{
    funStartTran();
    
    $columns['Code'] = $Code;
    $columns['Name'] = add($_REQUEST['Name']);
    $columns['Comp_Code'] = $_SESSION['comp_code'];
    
    if(getrows($table, "Code", $Code) == '1') {{  // âœ… FUNCTION 5
        // UPDATE
        $filter = " Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";
        db_update($table, $columns, $filter);  // âœ… FUNCTION 2
        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Update", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
    }} else {{
        // INSERT  
        db_insert($table, $columns);  // âœ… FUNCTION 1
        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
    }}
    
    funEndTran();
}}
```

VALIDATION REQUIREMENT:
Your code will be scanned for these 6 functions. If ANY are missing, validation will FAIL.
Current validation requires 5/6 functions minimum for passing score.

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL INSTRUCTION ðŸ”´ðŸ”´ðŸ”´
"""
        
        # âœ… TIMEOUT FIX: Replace 600-line MANDATORY_BLOCKS with concise version
        # LLM already sees company example - doesn't need redundant instructions
        MANDATORY_BLOCKS = """
ðŸ”´ MANDATORY REQUIREMENTS (follow company example structure exactly):

1. TABLE NAME: Use '{correct_table_name}' (NOT 'customer' or 'Customer')
2. FIELD NAMES: Use PascalCase with underscores (CUST_CODE, Main_Area, NAME)
3. AJAX PARAM: GetMaxID MUST receive '{parent_db_field}' parameter
4. CODE FORMAT: {code_length}-digit code with '{separator}' separator
5. PRE-DELETE: Check ALL {len(related_tables)} tables with getrows2() before delete
6. CSS LINKS: Include ALL CSS links from company example in <head>
7. FOOTER SCRIPTS: Include ALL footer scripts from company example before </body>
8. INCLUDES: include("include/config.inc.php"), topmenu.php, sidemenu.php, footer.php
9. VALIDATION: Use FormValidation with notEmpty validator for required fields
10. KEYBOARD NAV: Use checkKeycode(event, this.id) on all inputs

FAILURE TO COMPLY = CODE REJECTED
"""
        
        # âœ… TIMEOUT FIX: Define ALL template variables concisely
        BLOCKING_HEADER = "ðŸ”´ CRITICAL: Generate COMPLETE inline PHP+HTML+CSS+JS file matching company structure.\n"
        
        # âœ… FIX: company_fields might be a list or dict - handle both
        if isinstance(company_fields, dict):
            user_fields = company_fields.get('user_requested_fields', [])
            parent_field = company_fields.get('parent_field', 'N/A')
        else:
            user_fields = company_fields if isinstance(company_fields, list) else []
            parent_field = 'N/A'
        
        fields_str = ', '.join(user_fields[:25]) if user_fields else 'All fields from company example'
        
        FIELD_MAPPING_INSTRUCTION = f"Use ONLY these user-requested fields: {fields_str}\n"
        HIERARCHICAL_CODE_TEMPLATE = f"Use hierarchical code with parent field: {parent_field}\n" if hierarchy_pattern.get('is_hierarchical', False) else ""
        PRE_DELETE_CHECKS_TEMPLATE = f"Check {len(related_tables)} tables before delete\n" if related_tables else ""
        CASCADING_DROPDOWN_TEMPLATE = "Implement cascading dropdowns if needed\n" if cascading_logic.get('has_cascading', False) else ""
        GRID_TEMPLATE = f"Implement grid for sub-table\n" if grid_pattern.get('has_grid', False) else ""
        CHART_INTEGRATION_TEMPLATE = "Implement Chart of Accounts integration with ACC_CUST prefix\n" if user_requirements.get('wants_chart', False) else ""
        chart_requirement = CHART_INTEGRATION_TEMPLATE
        KEYBOARD_NAV_TEMPLATE = "Implement checkKeycode() keyboard navigation for all fields\n" if user_requirements.get('wants_keyboard', False) else ""
        MANDATORY_HEAD_CSS = "Include ALL CSS links from company example in <head>\n"
        MANDATORY_META_TAGS = "Include meta tags (charset, viewport)\n"
        MAXID_FUNCTION_FIX = f"Implement maxid() function with AJAX param: {hierarchy_pattern.get('ajax_param', 'SelectArea')}\n" if hierarchy_pattern.get('is_hierarchical', False) else ""
        FORMVALIDATION_ICON_FIX = "Use FormValidation with notEmpty validator\n" if user_requirements.get('wants_formvalidation', False) else ""
        MANDATORY_BLOCKS = "Follow company example structure exactly\n"
        
        prompt = f"""{BLOCKING_HEADER}

{FIELD_MAPPING_INSTRUCTION}

{HIERARCHICAL_CODE_TEMPLATE}

{PRE_DELETE_CHECKS_TEMPLATE}

{CASCADING_DROPDOWN_TEMPLATE}

{GRID_TEMPLATE}

{CHART_INTEGRATION_TEMPLATE}

{KEYBOARD_NAV_TEMPLATE}

{MANDATORY_HEAD_CSS}

{MANDATORY_META_TAGS}

{MAXID_FUNCTION_FIX}

{FORMVALIDATION_ICON_FIX}

{MANDATORY_BLOCKS}

{chart_requirement}

=== GENERATE 100% COMPANY-SIMILAR CODE ===

{strict_warning}

{naming_rules}

=== COMPANY CODE EXAMPLES (COPY THIS STRUCTURE EXACTLY) ===

{safe_examples}

{safe_critical_patterns}

=== YOUR TASK ===

Generate EXACTLY like above examples for:
{safe_intent}

Database:
```sql
{safe_sql}
```

=== ðŸŽ¯ 14 ESSENTIAL PATTERNS (MUST INCLUDE ALL) ===

Your generated code MUST include ALL 14 essential patterns from the company codebase:

1. **AJAX AUTO-ID GENERATION** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY and will be VALIDATED. Your code MUST include ALL these components:
   
   **PHP Handler (REQUIRED - Place after line 4):**
   ```php
   // AJAX Auto-ID Handler - REQUIRED
   if($_REQUEST['Action']=='GetMaxID') {{ 
       {f"$MAXID=getvalue(\"SELECT LPAD(MAX(RIGHT(Code,{hierarchy_pattern.get('code_length', 4)})) + 1,{hierarchy_pattern.get('code_length', 4)},'0') FROM {table_name} WHERE {hierarchy_pattern.get('parent_field', 'Comp_Code')}='\".$_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"'\");" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else f"$MAXID=getvalue(\"SELECT LPAD(MAX(Code) + 1,4,'0') FROM {table_name} WHERE Comp_Code='\".$_SESSION['comp_code'].\"'\");"}
       if($MAXID=="") {{
           {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-0001\";" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else '$MAXID = "0001";'}
       }} else {{
           {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-\".$MAXID;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
       }}
       echo $MAXID;
       exit;
   }}
   ```
   
   **JavaScript Function (REQUIRED - Place in <script> section):**
   ```javascript
   function maxid() {{
       {f"var {hierarchy_pattern.get('parent_request_param', 'SelectArea')} = document.getElementById('{hierarchy_pattern.get('parent_js_field_id', 'Main_Area')}').value;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
       $.ajaxSetup({{async:false}});
       $.post("<?php echo $form2; ?>", {{Action:'GetMaxID'{f", {hierarchy_pattern.get('parent_request_param', 'SelectArea')}: {hierarchy_pattern.get('parent_request_param', 'SelectArea')}" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}}}, function(data) {{ 
           if(data != '') {{
               $('#Code').val(data);
           }}
       }});
   }}
   ```
   
   **HTML Integration (REQUIRED - Call on page load or field change):**
   ```html
   <body onLoad="maxid();">
   <!-- OR -->
   <select onChange="maxid();">
   ```
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - PHP: if($_REQUEST['Action']=='GetMaxID')
   - JavaScript: function maxid()
   - AJAX: $.post(
   - Action parameter: Action:'GetMaxID'
   
   If ANY of these 4 components are missing, validation will FAIL!

2. **PRE-DELETE DEPENDENCY CHECK** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for data integrity and will be VALIDATED. Your code MUST include:
   
   **Pattern Structure (REQUIRED - Place in Delete section):**
   ```php
   if($_REQUEST['action'] == 'Delete') {{
       // âš ï¸ STEP 1: Check ALL related tables BEFORE deleting
       
       // Check related_table_1
       $filter_check = " Foreign_Key_Field='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
       if(getrows2("related_table_1", $filter_check) >= 1) {{
           print "<script>alert('This record exists in Related Table 1. Cannot delete!');</script>";
           print "<script>document.location='$form'; </script>";
           exit;
       }}
       
       // Check related_table_2
       $filter_check = " Foreign_Key_Field='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
       if(getrows2("related_table_2", $filter_check) >= 1) {{
           print "<script>alert('This record exists in Related Table 2. Cannot delete!');</script>";
           print "<script>document.location='$form'; </script>";
           exit;
       }}
       
       // âš ï¸ STEP 2: Only delete if ALL checks pass
       $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
       db_delete($table, $filter);
       fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['major'], "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
   }}
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Checks tblsubarea before deleting area
   - frmSubArea.php: Checks tblcustomer AND tblsaleman before deleting
   - frmCustomer.php: Checks invoice table before deleting customer
   
   **Pattern Rules:**
   1. Use `getrows2(table, filter)` to check related tables
   2. Check with `>= 1` to see if records exist
   3. Show descriptive alert message
   4. Redirect back to list page
   5. Use `exit;` to stop execution
   6. Only delete if NO dependencies found
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Delete handler: if($_REQUEST['action'] == 'Delete')
   - Dependency check: getrows2(
   - Alert message: print "<script>alert(
   - Exit statement: exit;
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Prevents orphaned records in database
   - Maintains referential integrity
   - Protects against data corruption
   - Follows company's data safety standards

3. **CHART OF ACCOUNTS INTEGRATION** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for accounting system and will be VALIDATED. Your code MUST include:
   
   **Pattern Structure (REQUIRED - Integrate with ALL CRUD operations):**
   
   **Step 1: Generate Chart Account Code**
   ```php
   // Format: ACC_CUST + Code + '-0000'
   $chartcode = ACC_CUST.$Code.'-0000';
   ```
   
   **Step 2: INSERT into Chart (on Save)**
   ```php
   // Check if chart account already exists
   $ACC_CODE=getvalue("select ACC_CODE from chart where ACC_CODE='".$chartcode."' AND Comp_Code='".$_SESSION['comp_code']."'");
   if($ACC_CODE!=""){{
       echo "<script>alert('Chart Account Already Exists!!!');window.location='".$form."';</script>";
       exit;
   }}
   
   // Insert into chart table
   $qry_insert = mysql_query("INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL,Comp_Code) VALUES ('".$chartcode."' , '". add_Slashes_new($_REQUEST['Name']) ."' ,'D','4','".$_SESSION['comp_code']."')");
   ```
   
   **Step 3: UPDATE Chart (on Update)**
   ```php
   // Update chart table when record name changes
   $qry_update = mysql_query("UPDATE chart SET ACC_NAME = '". add_Slashes_new($_REQUEST['Name']) ."' WHERE ACC_CODE= '". $chartcode ."' AND Comp_Code='".$_SESSION['comp_code']."'");
   ```
   
   **Step 4: DELETE from Chart (on Delete)**
   ```php
   // Delete from chart table when record is deleted
   $chartcode = ACC_CUST.add($_REQUEST['major']).'-0000';
   $del = mysql_query("delete from chart where ACC_CODE = '".$chartcode."' AND Comp_Code='".$_SESSION['comp_code']."'");
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Chart integration with GRP_DET='G', LEVEL='3'
   - frmCustomer.php: Chart integration with GRP_DET='D', LEVEL='4'
   - All forms maintain chart synchronization
   
   **Chart Table Structure:**
   - ACC_CODE: Unique account code (e.g., "ACC_CUST01-0000")
   - ACC_NAME: Account name (same as record name)
   - GRP_DET: Group/Detail flag ('G' for Group, 'D' for Detail)
   - LEVEL: Account hierarchy level (3, 4, etc.)
   - Comp_Code: Company code for multi-company support
   
   **Pattern Rules:**
   1. Generate chartcode using ACC_CUST constant + Code + '-0000'
   2. Check for duplicate chart accounts before INSERT
   3. Use mysql_query() for chart operations (company standard)
   4. Always include Comp_Code in WHERE clauses
   5. Synchronize chart on ALL CRUD operations (Insert, Update, Delete)
   6. Use add_Slashes_new() for name field to prevent SQL injection
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Chart code generation: ACC_CUST
   - INSERT operation: INSERT INTO chart
   - UPDATE operation: UPDATE chart SET
   - DELETE operation: delete from chart
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Maintains synchronized accounting records
   - Enables financial reporting and analysis
   - Required for company's ERP system integration
   - Follows double-entry bookkeeping principles

4. **CONDITIONAL CODE GENERATION (Update vs Insert)** - REQUIRED
   - Check existence: if(getrows($table," Code",$Code) == '1')
   - If exists: db_update($table,$columns,$filter); + fun_log(...,"Update",...)
   - If not: db_insert($table,$columns); + fun_log(...,"Save",...)
   - Different messages: MSG_REC_UPDATED vs MSG_REC_SAVED

5. **DYNAMIC DROPDOWN POPULATION** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for cascading dropdowns and will be VALIDATED. Your code MUST include:
   
   **PHP AJAX Handler (REQUIRED - Place after AJAX Auto-ID handler):**
   ```php
   // Dynamic Dropdown Handler
   if($_REQUEST['Action']=='GetSubArea') {{
       $AreaCode = $_REQUEST['AreaCode'];  // Parent selection
       
       // Query child records based on parent
       $sql = mysql_query("SELECT Code, Description FROM tblsubarea WHERE Country_Code='".$AreaCode."' AND Comp_Code='".$_SESSION['comp_code']."' ORDER BY Description");
       
       // Build JSON array response (Company Format)
       $i = 1;
       $array_ = Array();
       
       while($row = mysql_fetch_object($sql))
       {{
           $values = Array();
           array_push($values, $i);           // Index [0]
           array_push($values, $row->Code);   // Value [1]
           array_push($values, $row->Description);  // Display [2]
           array_push($array_, $values);
           $i++; 
       }}
       
       // Return JSON response
       echo json_encode($array_);
       exit;
   }}
   ```
   
   **JavaScript Function (REQUIRED - Place in <script> section):**
   ```javascript
   function loadSubArea() {{
       var areaCode = document.getElementById('AreaCode').value;
       
       // Clear child if parent is empty
       if(areaCode == '' || areaCode == '-1') {{
           $('#SubAreaCode').empty().append('<option value="-1">SELECT</option>');
           return;
       }}
       
       // Show loading
       $('#SubAreaCode').empty().append('<option value="">Loading...</option>');
       
       $.ajax({{
           url: "<?php echo $form2; ?>",
           type: "POST",
           data: {{ Action: 'GetSubArea', AreaCode: areaCode }},
           dataType: "json",
           success: function(msg) {{
               var $subArea = $('#SubAreaCode');
               $subArea.empty();
               $subArea.append('<option value="-1">SELECT</option>');
               
               // Populate dropdown
               for (var i = 0; i < msg.length; i++) {{
                   $subArea.append('<option value="' + msg[i][1] + '">' + msg[i][2] + '</option>');
               }}
               
               $subArea.change();
           }},
           error: function(xhr, status, error) {{
               console.error('AJAX Error:', error);
               alert('Error loading sub areas');
               $subArea.empty().append('<option value="-1">SELECT</option>');
           }}
       }});
   }}
   ```
   
   **HTML Integration (REQUIRED - onChange event):**
   ```html
   <select id="AreaCode" name="AreaCode" onChange="loadSubArea();">
       <option value="-1">SELECT</option>
       <!-- Options populated from database -->
   </select>
   
   <select id="SubAreaCode" name="SubAreaCode">
       <option value="-1">SELECT</option>
       <!-- Options populated dynamically via AJAX -->
   </select>
   ```
   
   **Real Examples from Company Code:**
   - frmCustomer.php: Area â†’ SubArea â†’ Salesman (3-level cascade)
   - frmSubArea.php: Area â†’ SubArea (2-level cascade)
   - All forms use consistent JSON array format
   
   **JSON Response Format (Company Standard):**
   ```json
   [
       [1, "CODE1", "Description 1"],
       [2, "CODE2", "Description 2"],
       [3, "CODE3", "Description 3"]
   ]
   ```
   - Index 0: Sequential number
   - Index 1: Code (value)
   - Index 2: Description (display text)
   
   **Pattern Rules:**
   1. Use mysql_fetch_object() to fetch data
   2. Build array with 3 elements: [index, code, description]
   3. Return json_encode($array_) response
   4. Always include Comp_Code filter in query
   5. Clear child dropdown when parent changes
   6. Show loading indicator during AJAX call
   7. Handle error cases with alert
   8. Use onChange event on parent dropdown
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - AJAX handler: if($_REQUEST['Action']=='Get
   - Data fetching: mysql_fetch_object(
   - JSON response: json_encode(
   - JavaScript function: function load
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Enables cascading dropdown selections
   - Improves user experience with dynamic data
   - Reduces page reloads
   - Maintains data relationships
   - Standard pattern across all company forms

ðŸ”´ðŸ”´ðŸ”´ CRITICAL - MISSING PATTERNS FROM MANUAL FIXES ðŸ”´ðŸ”´ðŸ”´

**PATTERN A: isset() CHECKS (Security - Prevent PHP Notices)**

ALWAYS use isset() before accessing $_REQUEST, $_POST, $_GET:

```php
// âŒ WRONG - Causes "Undefined index" notice
if($_REQUEST['Action']=='GetMaxID') {{

// âœ… CORRECT - Safe check
if(isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {{

// âŒ WRONG
if($_REQUEST['action'] == 'Delete') {{

// âœ… CORRECT
if(isset($_REQUEST['action']) && $_REQUEST['action'] == 'Delete') {{

// âŒ WRONG
if($_REQUEST['action'] == 'Update') {{

// âœ… CORRECT
if(isset($_REQUEST['action']) && $_REQUEST['action'] == 'Update') {{
```

**PATTERN B: VARIABLE INITIALIZATION (Prevent Undefined Variable Warnings)**

ALWAYS initialize ALL variables at top of PHP section BEFORE any HTML:

```php
<?php
@session_start();
include("include/config.inc.php");

// âœ… REQUIRED: Initialize ALL variables used in HTML
$Code = '';
$Cust_Name = '';
$Phone_No = '';
$Email = '';
$Address = '';
$Description = '';
$Area = '';  // For dropdown selected value
$Category = '';  // For dropdown selected value

// Then your AJAX handlers, form processing, etc.
if(isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {{
    // ...
}}
?>
```

**Why This Matters:**
- Prevents "Undefined variable" warnings in HTML section
- Variables used in Update mode must exist in New mode too
- Clean error-free output

**PATTERN C: htmlspecialchars() FOR XSS SECURITY**

ALWAYS use htmlspecialchars() when echoing variables in HTML attributes:

```php
// âŒ WRONG - XSS vulnerability
<input type="text" value="<?php echo $Cust_Name; ?>" />

// âœ… CORRECT - XSS protected
<input type="text" value="<?php echo htmlspecialchars($Cust_Name); ?>" />

// âŒ WRONG
<textarea><?php echo $Description; ?></textarea>

// âœ… CORRECT
<textarea><?php echo htmlspecialchars($Description); ?></textarea>

// âŒ WRONG
<option value="<?php echo $row['Code']; ?>"><?php echo $row['Name']; ?></option>

// âœ… CORRECT
<option value="<?php echo htmlspecialchars($row['Code']); ?>"><?php echo htmlspecialchars($row['Name']); ?></option>
```

**Why This Matters:**
- Prevents XSS (Cross-Site Scripting) attacks
- Escapes special HTML characters: < > & " '
- Security best practice
- Required for production code

âš ï¸ VALIDATION: Code will be checked for:
1. isset() before ALL $_REQUEST/$_POST/$_GET access
2. Variable initialization at top (before HTML)
3. htmlspecialchars() in ALL HTML output

ðŸ”´ðŸ”´ðŸ”´ END CRITICAL MISSING PATTERNS ðŸ”´ðŸ”´ðŸ”´

6. **FORMVALIDATION.JS FRAMEWORK** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   ðŸ”´ PHASE 1 FIX #6: FormValidation field names MUST match actual form field IDs!
   
   âš ï¸ Use field names from PHASE 1 extraction: {field_names_str}
   âš ï¸ Do NOT validate non-existent fields like "Sub_Area_Name"!
   
   This pattern is MANDATORY for client-side validation and will be VALIDATED. Your code MUST include:
   
   **Complete FormValidation Setup (REQUIRED - Place in initializeForm()):**
   ```javascript
   $('#frm').formValidation({{
       framework: "bootstrap",
       button: {{
           selector: '#btnSave',
           disabled: 'disabled'  // Disable until validation passes
       }},
       icon: null,
       fields: {{
           // Text Field Validation
           FieldName: {{
               row: '.col-md-4',  // Match column class for error display
               validators: {{
                   notEmpty: {{
                       message: 'Field Name is required and cannot be empty'
                   }},
                   stringLength: {{
                       max: 50,
                       message: 'Field Name must be less than 50 characters'
                   }}
               }}
           }},
           
           // Dropdown Validation with Callback
           DropdownField: {{
               row: '.col-md-4',
               validators: {{
                   notEmpty: {{
                       message: 'Please Select an option'
                   }},
                   callback: {{
                       message: 'Please Select an option',
                       callback: function(value, validator, $field) {{
                           if(document.getElementById('DropdownField').value == '-1') {{
                               return {{
                                   valid: false,
                                   message: 'Please Select an option'
                               }}
                           }}
                           return true;
                       }}
                   }}
               }}
           }},
           
           // Email Validation
           EmailField: {{
               row: '.col-md-4',
               validators: {{
                   regexp: {{
                       regexp: '^[^@\\\\s]+@([^@\\\\s]+\\\\.)+[^@\\\\s]+$',
                       message: 'Enter Valid Email address'
                   }}
               }}
           }},
           
           // Numeric Validation
           NumericField: {{
               row: '.col-md-4',
               validators: {{
                   notEmpty: {{
                       message: 'Field is required'
                   }},
                   numeric: {{
                       message: 'Please enter numbers only'
                   }},
                   between: {{
                       min: 0,
                       max: 999999,
                       message: 'Value must be between 0 and 999999'
                   }}
               }}
           }}
       }}
   }})
   .on('success.form.fv', function(e) {{
       e.preventDefault();
       btnsave_click();  // Call save function on validation success
   }});
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Simple notEmpty validation
   - frmSubArea.php: Dropdown with callback validation
   - frmCustomer.php: Complex validation with email regex
   
   **Validation Types (Company Standard):**
   
   1. **notEmpty** - Required field
      ```javascript
      notEmpty: {{ message: 'Field is required' }}
      ```
   
   2. **callback** - Custom validation for dropdowns
      ```javascript
      callback: {{
          callback: function(value, validator, $field) {{
              if(value == '-1') return {{ valid: false, message: 'Please select' }};
              return true;
          }}
      }}
      ```
   
   3. **regexp** - Pattern matching (email, phone, etc.)
      ```javascript
      regexp: {{
          regexp: '^[^@\\\\s]+@([^@\\\\s]+\\\\.)+[^@\\\\s]+$',
          message: 'Invalid email'
      }}
      ```
   
   4. **stringLength** - Length validation
      ```javascript
      stringLength: {{
          max: 50,
          message: 'Maximum 50 characters'
      }}
      ```
   
   5. **numeric** - Number validation
      ```javascript
      numeric: {{ message: 'Numbers only' }}
      ```
   
   6. **between** - Range validation
      ```javascript
      between: {{
          min: 0,
          max: 100,
          message: 'Value between 0-100'
      }}
      ```
   
   **Pattern Rules:**
   1. Use framework: "bootstrap" for styling
   2. Disable submit button until validation passes
   3. Set icon: null (no icons)
   4. Match row selector to column class (.col-md-4, .col-md-8)
   5. Provide specific error messages
   6. Use callback for dropdown validation (check for '-1')
   7. Prevent form submission with e.preventDefault()
   8. Call btnsave_click() on success
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - FormValidation init: $('#frm').formValidation(
   - Framework: framework: "bootstrap"
   - Validators: validators:
   - Success handler: .on('success.form.fv'
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Prevents invalid data submission
   - Improves user experience with instant feedback
   - Reduces server-side validation load
   - Consistent validation across all forms
   - Professional form behavior

7. **KEYBOARD NAVIGATION (Enter Key)** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for fast data entry and will be VALIDATED. Your code MUST include:
   
   **Complete Keyboard Navigation Function (REQUIRED - Place in <script> section):**
   ```javascript
   document.onkeydown = checkKeycode
   function checkKeycode(e,field) 
   {{
       var keycode;
       if (window.event) 
           keycode = window.event.keyCode;
       else if (e) 
           keycode = e.which;
       
       // Enter key navigation (keycode 13) - Map ALL fields in sequence
       if(keycode == 13) {{
           if(field == 'Code') {{
               document.getElementById('Name').focus();
           }}
           else if(field == 'Name') {{
               document.getElementById('Description').focus();
           }}
           else if(field == 'Description') {{
               document.getElementById('Category').focus();
           }}
           else if(field == 'Category') {{
               document.getElementById('Status').focus();
           }}
           else if(field == 'Status') {{
               document.getElementById('btnSave').focus();
           }}
           // âš ï¸ Add navigation for EVERY field in your form
           // Last field should focus on btnSave button
       }}
       
       // ESC key to go back (keycode 27)
       if(keycode == 27) {{
           window.location = '<?php echo $form; ?>';
       }}
       
       // F2 key for quick save (keycode 113) - Optional
       if(keycode == 113) {{
           document.getElementById('btnSave').click();
       }}
   }}
   ```
   
   **HTML Integration (REQUIRED - Add to EVERY input field):**
   ```html
   <!-- Text Input -->
   <input type="text" name="Name" id="Name" onKeyDown="checkKeycode(event,this.id);" />
   
   <!-- Dropdown -->
   <select name="Category" id="Category" onKeyDown="checkKeycode(event,this.id);">
       <option value="">Select</option>
   </select>
   
   <!-- Textarea -->
   <textarea name="Description" id="Description" onKeyDown="checkKeycode(event,this.id);"></textarea>
   
   âš ï¸ CRITICAL: ALL input fields MUST have onKeyDown="checkKeycode(event,this.id);" attribute
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: 2 fields â†’ Save button (simple flow)
   - frmSubArea.php: 4 fields â†’ Save button (medium flow)
   - frmCustomer.php: 20+ fields â†’ Save button (complex flow)
   
   **Navigation Flow Pattern:**
   ```
   Field1 (Enter) â†’ Field2 (Enter) â†’ Field3 (Enter) â†’ ... â†’ Save Button
   Any Field (ESC) â†’ Back to list page
   Any Field (F2) â†’ Quick save
   ```
   
   **Keyboard Shortcuts (Company Standard):**
   - **Enter (13)**: Move to next field
   - **ESC (27)**: Go back to list page
   - **F2 (113)**: Quick save (optional)
   - **Alt+S**: Save button (accesskey)
   - **Alt+B**: Back button (accesskey)
   
   **Pattern Rules:**
   1. Use document.onkeydown = checkKeycode (global handler)
   2. Check keycode with if(window.event) for IE compatibility
   3. Map EVERY field in sequential order
   4. Last field focuses on btnSave button
   5. Add onKeyDown="checkKeycode(event,this.id);" to ALL inputs
   6. Use field ID for navigation (this.id)
   7. ESC key returns to list page
   8. Optional F2 for quick save
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Global handler: document.onkeydown = checkKeycode
   - Function definition: function checkKeycode(e,field)
   - Enter key check: keycode == 13
   - HTML attribute: onKeyDown="checkKeycode(event,this.id)
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Enables fast data entry without mouse
   - Improves user productivity
   - Standard across all company forms
   - Professional desktop-like experience
   - Reduces data entry time by 50%

8. **GRID/TABLE FOR DETAIL RECORDS** - âšª OPTIONAL (Use if master-detail relationship)
   
   This pattern is for forms with master-detail relationships (e.g., Invoice with Items).
   
   **PHP: Save Detail Records in Loop (Place after main record save):**
   ```php
   // Delete existing detail records
   unset($columns);
   db_delete($sub_table," Master_Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'");
   
   // Insert detail records from grid
   for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++)
   {{
       if($_REQUEST['SR_NO'.$i]!='')
       {{
           $columns['Master_Code']	= $Code;
           $columns['SR_NO']	= $_REQUEST['SR_NO'.$i];
           $columns['Detail_Field1']	= add_Slashes_new($_REQUEST['Detail_Field1'.$i]);
           $columns['Detail_Field2']	= $_REQUEST['Detail_Field2'.$i];
           $columns['Comp_Code'] = $_SESSION['comp_code'];
           
           db_insert($sub_table,$columns) or die(mysql_error());
       }}	
   }}
   ```
   
   **JavaScript: Grid Management Functions:**
   ```javascript
   var gridIndex = 0;
   var gridData = new Array(1000);
   for(var i=0; i<1000; i++)
       gridData[i] = new Array(10);
   
   function addGridRow() {{
       gridIndex++;
       var sr = gridIndex;
       
       var row = '<tr id="row' + sr + '">';
       row += '<td>' + sr + '<input type="hidden" name="SR_NO' + sr + '" value="' + sr + '"></td>';
       row += '<td><input type="text" class="form-control" name="Detail_Field1' + sr + '" id="Detail_Field1' + sr + '"></td>';
       row += '<td><input type="text" class="form-control" name="Detail_Field2' + sr + '" id="Detail_Field2' + sr + '"></td>';
       row += '<td><button type="button" class="btn btn-danger btn-sm" onclick="deleteGridRow(' + sr + ')">Delete</button></td>';
       row += '</tr>';
       
       $('#gridTableBody').append(row);
       $('#TXTCOUNTACC').val(gridIndex);
       $('#Detail_Field1' + sr).focus();
   }}
   
   function deleteGridRow(sr) {{
       if(confirm('Delete this row?')) {{
           $('#row' + sr).remove();
           $('#SR_NO' + sr).val('');
       }}
   }}
   ```
   
   **HTML: Grid Structure:**
   ```html
   <div class="form-group">
     <div class="col-md-12">
       <h4>Detail Records</h4>
       <button type="button" class="btn btn-primary btn-sm" onclick="addGridRow()">Add Row</button>
       <table class="table table-bordered" id="gridTable">
         <thead>
           <tr>
             <th>Sr#</th>
             <th>Detail Field 1</th>
             <th>Detail Field 2</th>
             <th>Action</th>
           </tr>
         </thead>
         <tbody id="gridTableBody">
           <!-- Rows added dynamically -->
         </tbody>
       </table>
       <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="0">
     </div>
   </div>
   ```
   
   **Real Examples from Company Code:**
   - frmCustomer.php: Customer with multiple shipping addresses
   - Invoice forms: Invoice header with line items
   - Order forms: Order header with order details
   
   **Pattern Rules:**
   1. Use gridIndex to track row numbers
   2. Name fields with row number suffix (Field1, Field2, etc.)
   3. Store row count in hidden field (TXTCOUNTACC)
   4. Delete old details before inserting new ones
   5. Loop through $_REQUEST to get all rows
   6. Check if SR_NO is not empty before inserting
   7. Use Comp_Code filter in delete query
   
   **Why This Matters:**
   - Enables master-detail data entry
   - Common in invoices, orders, transactions
   - Professional multi-record interface
   - Reduces page reloads

8. **SELECT2 INTEGRATION FOR ENHANCED DROPDOWNS** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for professional dropdown behavior and will be VALIDATED. Your code MUST include:
   
   **Complete Select2 Setup (REQUIRED - Place in initializeForm() function):**
   ```javascript
   // Initialize Select2 for all dropdown fields
   $('.select2-field').select2({{
       placeholder: 'Select an option',
       allowClear: true,
       width: '100%'
   }});
   
   // âš ï¸ CRITICAL: Select2 with Keyboard Navigation Integration
   // Company Pattern: Auto-open on focus, move to next field on close
   
   // Example: Area dropdown with keyboard navigation
   $('#AreaCode').select2({{
       placeholder: 'Select Area',
       allowClear: true,
       width: '100%'
   }})
   .on("select2:close", function () {{
       // Move to next field after selection
       setTimeout(function() {{
           $('.select2-container-active').removeClass('select2-container-active');
           $(':focus').blur();
           $('#SubAreaCode').focus();
           $('#SubAreaCode').select2('open');  // Auto-open next dropdown
       }}, 1);
   }});
   
   // Auto-open on focus for keyboard users
   $('#AreaCode').focus(function() {{
       $('#AreaCode').select2('open');
   }});
   ```
   
   **HTML Integration (REQUIRED - Add to ALL dropdown fields):**
   ```html
   <select class="form-control select2-field" 
           data-plugin="select2" 
           name="FieldName" 
           id="FieldName" 
           onKeyDown="checkKeycode(event,this.id);">
       <option value="-1">-- Select --</option>
       <option value="1">Option 1</option>
       <option value="2">Option 2</option>
   </select>
   
   âš ï¸ CRITICAL: Dropdown fields MUST have:
   - class="form-control select2-field" for styling and Select2
   - data-plugin="select2" for automatic initialization
   - onKeyDown="checkKeycode(event,this.id);" for keyboard navigation
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Simple Select2 on status dropdown
   - frmSubArea.php: Select2 with cascading (Area â†’ SubArea)
   - frmCustomer.php: Complex Select2 with 3-level cascade (Area â†’ SubArea â†’ Salesman)
   
   **Select2 Configuration Options (Company Standard):**
   
   1. **placeholder** - Hint text when empty
      ```javascript
      placeholder: 'Select an option'
      ```
   
   2. **allowClear** - Show X button to clear selection
      ```javascript
      allowClear: true
      ```
   
   3. **width** - Dropdown width (always 100%)
      ```javascript
      width: '100%'
      ```
   
   4. **minimumResultsForSearch** - Hide search box for small lists
      ```javascript
      minimumResultsForSearch: 10  // Hide search if < 10 options
      ```
   
   **Keyboard Navigation Integration:**
   ```javascript
   // Pattern for seamless keyboard flow through dropdowns
   $('#Dropdown1').select2({{
       placeholder: 'Select',
       allowClear: true,
       width: '100%'
   }})
   .on("select2:close", function () {{
       setTimeout(function() {{
           $('.select2-container-active').removeClass('select2-container-active');
           $(':focus').blur();
           $('#Dropdown2').focus();  // Move to next field
           $('#Dropdown2').select2('open');  // Auto-open if also Select2
       }}, 1);
   }});
   
   // Auto-open on focus
   $('#Dropdown1').focus(function() {{
       $('#Dropdown1').select2('open');
   }});
   ```
   
   **Pattern Rules:**
   1. Add class="select2-field" to ALL dropdown elements
   2. Add data-plugin="select2" attribute for auto-initialization
   3. Initialize with $('.select2-field').select2({{...}}) in initializeForm()
   4. Set placeholder for better UX
   5. Set allowClear: true to allow clearing selection
   6. Set width: '100%' for responsive design
   7. Integrate with keyboard navigation (on close â†’ focus next field)
   8. Auto-open on focus for keyboard users
   9. Keep onKeyDown="checkKeycode(event,this.id);" for Enter key navigation
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Select2 initialization: .select2(
   - HTML attribute: data-plugin="select2"
   - CSS class: class="select2-field"
   - Configuration: placeholder:
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Professional searchable dropdowns
   - Better UX for long option lists
   - Consistent with company UI standards
   - Improves accessibility
   - Seamless keyboard navigation
   - Standard across all company forms

9. **MULTI-COMPANY FILTER (Comp_Code)** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for multi-company ERP system and will be VALIDATED. Your code MUST include:
   
   **Complete Comp_Code Integration (REQUIRED - Add to ALL database operations):**
   
   **Step 1: Add Comp_Code to INSERT/UPDATE Columns**
   ```php
   // ALWAYS include Comp_Code in columns array
   $columns['Code'] = $Code;
   $columns['Name'] = add($_REQUEST['Name']);
   $columns['Comp_Code'] = $_SESSION['comp_code'];  // âš ï¸ REQUIRED
   $columns['UserId'] = $_SESSION['user_id'];
   $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));
   $columns['Login_ID'] = $_SESSION['login_id'];
   ```
   
   **Step 2: Add Comp_Code to ALL WHERE Clauses**
   ```php
   // SELECT queries - ALWAYS filter by Comp_Code
   $dbId = getvalue("SELECT max(Code)+1 FROM $table WHERE Comp_Code='".$_SESSION['comp_code']."'");
   
   // UPDATE queries - ALWAYS include Comp_Code in filter
   $filter = " Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";
   db_update($table, $columns, $filter);
   
   // DELETE queries - ALWAYS include Comp_Code in filter
   $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
   db_delete($table, $filter);
   
   // SELECT single record - ALWAYS include Comp_Code
   $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
   $obj = db_getRecord($table, $filter);
   
   // Check existence - Include Comp_Code in getrows
   if(getrows($table, "Code", $Code) == '1') {{
       // Note: getrows doesn't support Comp_Code directly, use getvalue instead
       $exists = getvalue("SELECT COUNT(*) FROM $table WHERE Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'");
   }}
   ```
   
   **Step 3: Add Comp_Code to Dependency Checks**
   ```php
   // Pre-delete checks MUST include Comp_Code
   $filter_check = " Foreign_Key='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
   if(getrows2("related_table", $filter_check) >= 1) {{
       print "<script>alert('Record exists in related table!');</script>";
       exit;
   }}
   ```
   
   **Step 4: Add Comp_Code to Dynamic Dropdown Queries**
   ```php
   // AJAX dropdown handlers MUST filter by Comp_Code
   if($_REQUEST['Action']=='GetSubArea') {{
       $AreaCode = $_REQUEST['AreaCode'];
       $sql = mysql_query("SELECT Code, Description FROM tblsubarea 
                          WHERE Country_Code='".$AreaCode."' 
                          AND Comp_Code='".$_SESSION['comp_code']."'  // âš ï¸ REQUIRED
                          ORDER BY Description");
       // ... rest of code
   }}
   ```
   
   **Step 5: Add Comp_Code to Chart Integration**
   ```php
   // Chart queries MUST include Comp_Code
   $ACC_CODE = getvalue("SELECT ACC_CODE FROM chart 
                         WHERE ACC_CODE='".$chartcode."' 
                         AND Comp_Code='".$_SESSION['comp_code']."'");  // âš ï¸ REQUIRED
   
   // Chart INSERT
   $qry_insert = mysql_query("INSERT INTO chart (ACC_CODE, ACC_NAME, GRP_DET, LEVEL, Comp_Code) 
                             VALUES ('".$chartcode."', '".add_Slashes_new($_REQUEST['Name'])."', 
                                     'D', '4', '".$_SESSION['comp_code']."')");  // âš ï¸ REQUIRED
   
   // Chart UPDATE
   $qry_update = mysql_query("UPDATE chart SET ACC_NAME='".add_Slashes_new($_REQUEST['Name'])."' 
                             WHERE ACC_CODE='".$chartcode."' 
                             AND Comp_Code='".$_SESSION['comp_code']."'");  // âš ï¸ REQUIRED
   
   // Chart DELETE
   $del = mysql_query("DELETE FROM chart 
                      WHERE ACC_CODE='".$chartcode."' 
                      AND Comp_Code='".$_SESSION['comp_code']."'");  // âš ï¸ REQUIRED
   ```
   
   **Step 6: Add Comp_Code to Grid/Detail Records**
   ```php
   // Detail records MUST include Comp_Code
   db_delete($sub_table, " Master_Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'");
   
   for($i=0; $i<=$_REQUEST['TXTCOUNTACC']; $i++) {{
       if($_REQUEST['SR_NO'.$i]!='') {{
           $columns['Master_Code'] = $Code;
           $columns['SR_NO'] = $_REQUEST['SR_NO'.$i];
           $columns['Comp_Code'] = $_SESSION['comp_code'];  // âš ï¸ REQUIRED
           db_insert($sub_table, $columns);
       }}
   }}
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Comp_Code in columns but MISSING in some queries (needs improvement)
   - frmSubArea.php: Comp_Code in columns, MISSING in getvalue queries (needs improvement)
   - frmCustomer.php: Better Comp_Code usage in most queries
   
   **Pattern Rules:**
   1. ALWAYS add `$columns['Comp_Code'] = $_SESSION['comp_code'];` in INSERT/UPDATE
   2. ALWAYS add `AND Comp_Code='".$_SESSION['comp_code']."'` in WHERE clauses
   3. Include Comp_Code in ALL SELECT queries (getvalue, db_getRecord, etc.)
   4. Include Comp_Code in ALL UPDATE filters
   5. Include Comp_Code in ALL DELETE filters
   6. Include Comp_Code in dependency check queries (getrows2)
   7. Include Comp_Code in AJAX dropdown queries
   8. Include Comp_Code in chart table operations
   9. Include Comp_Code in detail/grid record operations
   10. Use $_SESSION['comp_code'] - NEVER hardcode company code
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Column assignment: $columns['Comp_Code']
   - WHERE clause: Comp_Code='".$_SESSION['comp_code']."'
   - AND clause: AND Comp_Code=
   - Session variable: $_SESSION['comp_code']
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Enables multi-company data isolation
   - Prevents data leakage between companies
   - Critical for SaaS/multi-tenant architecture
   - Required for company's ERP system
   - Ensures data security and integrity
   - Standard across ALL company forms
   
   **Security Impact:**
   Without Comp_Code filters, users from Company A could see/modify data from Company B!
   This is a CRITICAL security vulnerability that MUST be prevented.

10. **SESSION VARIABLES (login_id, UserId, Unit_Code)** - âš ï¸ CRITICAL - VALIDATION REQUIRED âš ï¸
   
   This pattern is MANDATORY for audit trail and user tracking and will be VALIDATED. Your code MUST include:
   
   **Complete Session Variables Integration (REQUIRED - Add to ALL database operations):**
   
   **Step 1: Add Session Variables to INSERT/UPDATE Columns**
   ```php
   // ALWAYS include these session variables in columns array
   $columns['Code'] = $Code;
   $columns['Name'] = add($_REQUEST['Name']);
   $columns['Comp_Code'] = $_SESSION['comp_code'];  // âš ï¸ REQUIRED (Pattern #9)
   $columns['UserId'] = $_SESSION['user_id'];  // âš ï¸ REQUIRED - Who created/modified
   $columns['Login_ID'] = $_SESSION['login_id'];  // âš ï¸ REQUIRED - Login session tracking
   $columns['Unit_Code'] = $_SESSION['Unit_Code'];  // âš ï¸ OPTIONAL - For multi-unit companies
   $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));  // âš ï¸ REQUIRED - When created/modified
   ```
   
   **Step 2: Use Session Variables in fun_log() Calls**
   ```php
   // ALWAYS include session variables in audit log
   // fun_log($user_id, $comp_code, $title, $record_id, $action, $date, $login_id)
   
   // On INSERT
   fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
   
   // On UPDATE
   fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Update", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
   
   // On DELETE
   fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, add($_REQUEST['major']), "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
   ```
   
   **Complete Example with All Session Variables:**
   ```php
   <?php
   @session_start();
   include("include/config.inc.php");
   
   $table = "tblcustomer";
   $title = "Customer";
   
   // Save/Update Operation
   if(isset($_POST["txtmode"]) and $_POST["txtmode"]=="save") {{
       funStartTran();
       
       // Build columns array with ALL required session variables
       $columns['Code'] = $Code;
       $columns['Name'] = add($_REQUEST['Name']);
       $columns['Description'] = add($_REQUEST['Description']);
       
       // âš ï¸ REQUIRED SESSION VARIABLES
       $columns['Comp_Code'] = $_SESSION['comp_code'];  // Multi-company filter
       $columns['UserId'] = $_SESSION['user_id'];  // User who created/modified
       $columns['Login_ID'] = $_SESSION['login_id'];  // Login session ID
       $columns['Unit_Code'] = $_SESSION['Unit_Code'];  // Business unit (optional)
       $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));  // Timestamp
       
       // Check if insert or update
       if(getrows($table, "Code", $Code) == '1') {{
           // UPDATE
           $filter = " Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";
           db_update($table, $columns, $filter);
           
           // âš ï¸ REQUIRED: Log with session variables
           fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Update", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
           
           print "<script>alert('".MSG_REC_UPDATED."');</script>";
       }} else {{
           // INSERT
           db_insert($table, $columns);
           
           // âš ï¸ REQUIRED: Log with session variables
           fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
           
           print "<script>alert('".MSG_REC_SAVED."');</script>";
       }}
       
       funEndTran();
       print "<script>document.location='$form';</script>";
       exit;
   }}
   
   // Delete Operation
   if($_REQUEST['action'] == 'Delete') {{
       $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
       db_delete($table, $filter);
       
       // âš ï¸ REQUIRED: Log with session variables
       fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, add($_REQUEST['major']), "Delete", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
       
       print "<script>alert('Record Deleted.');</script>";
       print "<script>document.location='$form';</script>";
   }}
   ?>
   ```
   
   **Real Examples from Company Code:**
   - frmArea.php: Uses UserId, Login_ID, Comp_Code in columns
   - frmSubArea.php: Uses UserId, Login_ID, Comp_Code in columns
   - frmCustomer.php: Uses UserId, Login_ID, Comp_Code in columns
   - frmaccountconfiguration.php: Uses UserId, Login_ID, Comp_Code, Unit_Code in columns
   
   **Session Variables Explained:**
   
   1. **$_SESSION['user_id']** - Database user ID
      - Stored in UserId column
      - Used in fun_log() for audit trail
      - Tracks who created/modified the record
   
   2. **$_SESSION['login_id']** - Login session ID
      - Stored in Login_ID column
      - Used in fun_log() for audit trail
      - Tracks which login session made the change
      - Useful for tracking concurrent logins
   
   3. **$_SESSION['comp_code']** - Company code
      - Stored in Comp_Code column (Pattern #9)
      - Used in WHERE clauses for data isolation
      - Critical for multi-company support
   
   4. **$_SESSION['Unit_Code']** - Business unit code (OPTIONAL)
      - Stored in Unit_Code column
      - Used for multi-unit/branch companies
      - Not all forms require this
   
   **Pattern Rules:**
   1. ALWAYS add `$columns['UserId'] = $_SESSION['user_id'];` in INSERT/UPDATE
   2. ALWAYS add `$columns['Login_ID'] = $_SESSION['login_id'];` in INSERT/UPDATE
   3. ALWAYS add `$columns['Comp_Code'] = $_SESSION['comp_code'];` in INSERT/UPDATE
   4. OPTIONALLY add `$columns['Unit_Code'] = $_SESSION['Unit_Code'];` if multi-unit
   5. ALWAYS add `$columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));`
   6. ALWAYS use session variables in fun_log() calls (7 parameters)
   7. Use $_SESSION variables - NEVER hardcode user IDs
   8. Include in ALL CRUD operations (Insert, Update, Delete)
   
   âš ï¸ VALIDATION CHECK: Your code will be scanned for:
   - Column assignment: $columns['Login_ID']
   - Session variable: $_SESSION['login_id']
   - Column assignment: $columns['UserId']
   - Session variable: $_SESSION['user_id']
   
   If ANY of these 4 components are missing, validation will FAIL!
   
   **Why This Matters:**
   - Enables complete audit trail
   - Tracks who created/modified each record
   - Tracks when changes were made
   - Required for compliance and security
   - Helps debug data issues
   - Standard across ALL company forms
   
   **Audit Trail Benefits:**
   - Know who made changes
   - Know when changes were made
   - Track user activity
   - Investigate data issues
   - Compliance with regulations
   - Security and accountability

11. **TRANSACTION MANAGEMENT** - REQUIRED
   - Start: funStartTran(); at beginning of save/update block
   - Operations: db_insert(), db_update(), db_delete() within transaction
   - End: funEndTran(); after all operations complete
   - Ensures atomicity across multiple table operations

12. **DISABLED FIELD HANDLING** - REQUIRED
    - Enable before submit: document.getElementById('Code').disabled=false; in btnsave_click()
    - HTML disabled: <input disabled <?php if($_REQUEST['action']=='Update') echo "disabled='disabled'"; ?>>
    - Re-enable ALL disabled fields before form submission

13. **COMPLETE ASSET LOADING** - REQUIRED
    
    âš ï¸ CRITICAL: These CSS/JS files are MANDATORY for every form!
    Missing these will cause blank pages, unstyled forms, and broken functionality.
    
    **CSS Files (in <head> section):**
    ```html
    <!-- Core Bootstrap CSS -->
    <link rel="stylesheet" href="global/css/bootstrap.min.css">
    <link rel="stylesheet" href="global/css/bootstrap-extend.min.css">
    
    <!-- Theme CSS (REQUIRED - without this, page will be blank!) -->
    <link rel="stylesheet" href="assets/css/site.min.css">
    
    <!-- Vendor CSS -->
    <link rel="stylesheet" href="global/vendor/animsition/animsition.css">
    <link rel="stylesheet" href="global/vendor/formvalidation/formValidation.css">
    <link rel="stylesheet" href="global/vendor/select2/select2.css">
    <link rel="stylesheet" href="global/fonts/web-icons/web-icons.min.css">
    ```
    
    **JS Files (before </body> tag):**
    ```html
    <!-- Core Libraries -->
    <script src="global/vendor/modernizr/modernizr.js"></script>
    <script src="global/vendor/breakpoints/breakpoints.js"></script>
    <script>Breakpoints();</script>
    
    <!-- jQuery and Bootstrap -->
    <script src="global/vendor/jquery/jquery.js"></script>
    <script src="global/vendor/bootstrap/bootstrap.js"></script>
    
    <!-- Theme Core (REQUIRED - without this, Site.run() won't work!) -->
    <script src="global/js/core.js"></script>
    <script src="assets/js/site.js"></script>
    
    <!-- Theme Components -->
    <script src="assets/js/sections/menu.js"></script>
    <script src="assets/js/sections/menubar.js"></script>
    <script src="assets/js/sections/sidebar.js"></script>
    
    <!-- Vendor Plugins -->
    <script src="global/vendor/formvalidation/formValidation.min.js"></script>
    <script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
    <script src="global/vendor/select2/select2.min.js"></script>
    ```
    
    âš ï¸ VALIDATION: Your code will be checked for these files!
    Missing `assets/css/site.min.css` or `assets/js/site.js` will cause BLANK PAGE!
    - IE Compatibility: <!--[if lt IE 9]><script src="global/vendor/html5shiv/html5shiv.min.js"></script><![endif]-->

14. **PHP INCLUDE FILES** - REQUIRED
    - Config: include("include/config.inc.php"); at top
    - Header: <?php include("include/formheader.php"); ?> after page div
    - Menu: <?php include("include/topmenu.php");?> at body start
    - Sidebar: <?php include("include/sidemenu.php");?> after topmenu
    - Footer: <?php include("include/footer.php");?> before scripts

=== COMPANY CSS CLASSES - MANDATORY ===

ðŸ”´ CRITICAL: You MUST use these company CSS classes in EVERY form element:

PRIMARY CLASSES (use in every form):
- form-group: Wrap every form field in <div class="form-group">
- form-control: Apply to every <input>, <select>, <textarea>
- col-md-4: Apply to label containers
- col-md-2 or col-md-4: Apply to input containers
- form-horizontal: Apply to the <form> tag
- container-fluid: Apply to main container
- row: Apply to row containers
- row-lg: Apply to row containers for spacing

BUTTON CLASSES (use on all buttons):
- btn: Base button class
- btn-primary: For Save/Submit buttons
- btn-success: For Back/Cancel buttons
- btn-danger: For Delete buttons

TEXT STYLING CLASSES:
- text-danger: For required field indicators (*)
- text-right: For right-aligned text
- text-center: For centered text

PANEL CLASSES (for form containers):
- panel: Outer container
- panel-body: Inner content area

COMPLETE EXAMPLE OF REQUIRED CSS USAGE:
```html
<form class="form-horizontal" id="frm" name="frm">
  <div class="form-group">
    <label class="col-md-4 control-label">Field Name <span class="text-danger">*</span>:</label>
    <div class="col-md-2">
      <input type="text" class="form-control" name="fieldname" id="fieldname" />
    </div>
  </div>
  <div class="form-group">
    <div class="col-md-12" align="center">
      <button type="button" class="btn btn-primary">Save</button>
      <button type="button" class="btn btn-success">Back</button>
    </div>
  </div>
</form>
```

Form structure class: {company_form_structure}

VALIDATION RULE: If your generated HTML does NOT contain at least 15 of these classes, it will FAIL validation!

=== COMPANY DATABASE FUNCTIONS - MANDATORY ===

ðŸ”´ CRITICAL: You MUST use ONLY these company database functions (NOT standard PHP/MySQL):

REQUIRED FUNCTIONS (use in every database operation):
- db_insert($table, $columns): Insert new record
  Example: db_insert("tblcustomer", $columns);
  
- db_update($table, $columns, $filter): Update existing record
  Example: db_update("tblcustomer", $columns, " Code='01' AND Comp_Code='".$_SESSION['comp_code']."'");
  
- db_delete($table, $filter): Delete record
  Example: db_delete("tblcustomer", " Code='01' AND Comp_Code='".$_SESSION['comp_code']."'");
  
- db_getRecord($table, $filter): Get single record
  Example: $obj = db_getRecord("tblcustomer", " Code='01'");  // Returns array directly, NO mysql_fetch_array!
  
  âš ï¸ IMPORTANT: db_getRecord() ALREADY returns an array!
  âš ï¸ DO NOT use: $obj = mysql_fetch_array(db_getRecord(...));
  âš ï¸ DO NOT use: $obj = mysql_fetch(db_getRecord(...));
  âš ï¸ JUST use: $obj = db_getRecord(...);
  
- getrows($table, $field, $value): Check if record exists
  Example: if(getrows("tblcustomer", "Code", $Code) == '1')
  
- getvalue($query): Get single value from query
  Example: $maxCode = getvalue("SELECT max(Code)+1 from tblcustomer");
  
- add($value): Add slashes for SQL safety
  Example: $Code = add($_REQUEST['Code']);
  
- noformat($value, $length): Format value with leading zeros
  Example: $Code = noformat($dbId, 2);  // Returns "01", "02", etc.

TRANSACTION FUNCTIONS (wrap all DB operations):
- funStartTran(): Start transaction
- funEndTran(): End transaction
  
LOGGING FUNCTION (log all operations):
- fun_log($user_id, $comp_code, $title, $value, $action, $date, $login_id)
  Example: fun_log($_SESSION['user_id'], $_SESSION['comp_code'], "Customer", $Code, "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);

COMPLETE EXAMPLE OF REQUIRED DATABASE USAGE:
```php
<?php
@session_start();
include("include/config.inc.php");

$table = "tblcustomer";
$title = "Customer";

// Get next code
$dbId = getvalue("SELECT max(Code)+1 Code from $table WHERE Comp_Code='".$_SESSION['comp_code']."'");
if($dbId=="") {{ $Code = '01'; }} else {{ $Code = noformat($dbId, 2); }}

// Handle form submission
if(isset($_POST["txtmode"]) and $_POST["txtmode"]=="save") {{
    funStartTran();
    
    // Build columns array
    $columns['Code'] = $Code;
    $columns['Comp_Code'] = $_SESSION['comp_code'];
    $columns['Name'] = add($_REQUEST['Name']);
    $columns['UserId'] = $_SESSION['user_id'];
    $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));
    
    // Check if insert or update
    if(getrows($table, "Code", $Code) == '1') {{
        // UPDATE
        $filter = " Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";
        db_update($table, $columns, $filter);
        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Update", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
    }} else {{
        // INSERT
        db_insert($table, $columns);
        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $Code, "Save", db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);
    }}
    
    funEndTran();
    print "<script>alert('Record saved successfully'); </script>";
    print "<script>document.location='frmCustomer.php'; </script>";
    exit;
}}
?>
```

VALIDATION RULE: If your generated PHP does NOT use at least 5 of these company functions, it will FAIL validation!

=== WHAT NOT TO DO - FORBIDDEN PATTERNS ===

ðŸ”´ CRITICAL: These patterns will cause VALIDATION FAILURE:

âŒ ABSOLUTELY FORBIDDEN - DO NOT USE UNDER ANY CIRCUMSTANCES:

ðŸ”´ mysql_fetch() - FORBIDDEN!
   - This is an OLD PHP function that the company does NOT use
   - If you use it, your code will FAIL validation
   - Use db_getRecord() instead
   - Example WRONG: $obj = mysql_fetch_array(db_getRecord(...));
   - Example RIGHT: $obj = db_getRecord(...);

ðŸ”´ mysql_fetch_array() - FORBIDDEN!
   - This is an OLD PHP function that the company does NOT use
   - If you use it, your code will FAIL validation
   - Use db_getRecord() instead
   - Example WRONG: $obj = mysql_fetch_array(db_getRecord(...));
   - Example RIGHT: $obj = db_getRecord(...);

ðŸ”´ mysql_query() - FORBIDDEN! Use db_insert, db_update, db_delete instead
ðŸ”´ mysqli_* - FORBIDDEN! Use company functions instead
ðŸ”´ PDO - FORBIDDEN! Use company functions instead
ðŸ”´ new mysqli() - FORBIDDEN! Use company functions instead
ðŸ”´ new PDO() - FORBIDDEN! Use company functions instead
ðŸ”´ $mysqli->query() - FORBIDDEN! Use company functions instead
ðŸ”´ $pdo->prepare() - FORBIDDEN! Use company functions instead

âš ï¸ IF YOU USE ANY OF THESE FORBIDDEN FUNCTIONS:
- Your code will FAIL validation
- Your code will be REJECTED
- You will have to regenerate
- You will have to regenerate

âœ… DO use these patterns (required for validation to PASS):
- db_insert($table, $columns) - for INSERT operations
- db_update($table, $columns, $filter) - for UPDATE operations
- db_delete($table, $filter) - for DELETE operations
- db_getRecord($table, $filter) - for SELECT operations (NOT mysql_fetch!)
- getrows($table, $field, $value) - to check if record exists
- getvalue($query) - to get single value
- funStartTran() - to start transaction
- funEndTran() - to end transaction
- fun_log(...) - to log operations

=== CRITICAL STRUCTURE REQUIREMENTS ===

ðŸ”´ REMINDER: db_getRecord() RETURNS AN ARRAY DIRECTLY
ðŸ”´ DO NOT use mysql_fetch() or mysql_fetch_array() with db_getRecord()
ðŸ”´ CORRECT: $obj = db_getRecord($table, $filter);
ðŸ”´ WRONG: $obj = mysql_fetch_array(db_getRecord($table, $filter));

Your generated file MUST follow this EXACT structure (ONE FILE ONLY):

âš ï¸ IMPORTANT: Your code will be VALIDATED against company patterns:
- If CSS classes are missing â†’ VALIDATION FAILS (57% score)
- If database functions are missing â†’ VALIDATION FAILS (76% score)
- If both are missing â†’ VALIDATION FAILS (40% score)
- If mysql_fetch() is used â†’ VALIDATION FAILS (0% score)

To PASS validation (100% score), you MUST:
âœ… Use ALL company CSS classes in HTML
âœ… Use ALL company database functions in PHP
âœ… Follow company structure exactly
âœ… Include all required patterns
âœ… DO NOT use mysql_fetch() or mysql_fetch_array()

```php
<?php
// 1. SESSION MANAGEMENT (at very top)
@session_start();

// 2. INCLUDES
include("include/config.inc.php");

// 3. FORM VARIABLES
$form = "frmSettingEditDeleteCase.php?CaseType={canonical_title}";
$form2 = "{canonical_file_name}";
$table = "{table_name}";
$title = "{canonical_title}";

// 4. INITIALIZE CODE
$dbId = getvalue("SELECT max(Code)+1 Code from $table WHERE Comp_Code='".$_SESSION['comp_code']."'");
if($dbId==""){{$Code = '01';}}else{{$Code = noformat($dbId,2);}}

// 4.5 AJAX HANDLERS (REQUIRED - Company Pattern)
// AJAX Auto-ID Generation Handler
if($_REQUEST['Action']=='GetMaxID')
{{ 
    {f"$MAXID=getvalue(\"SELECT LPAD(MAX(RIGHT(Code,{hierarchy_pattern.get('code_length', 4)})) + 1,{hierarchy_pattern.get('code_length', 4)},'0') FROM $table WHERE {hierarchy_pattern.get('parent_field', 'Comp_Code')}='\".$_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"'\");" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else "$MAXID=getvalue(\"SELECT LPAD(MAX(Code) + 1,4,'0') FROM $table WHERE Comp_Code='\".$_SESSION['comp_code'].\"'\");"}
    if($MAXID=="")
    {{
        {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-0001\";" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else '$MAXID = "0001";'}
    }} else {{
        {f"$MAXID = $_REQUEST['{hierarchy_pattern.get('parent_request_param', 'SelectArea')}'].\"-\".$MAXID;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
    }}
    echo $MAXID;
    exit;
}}

// AJAX Dynamic Dropdown Handler (if needed)
if($_REQUEST['Action']=='GetDropdownData')
{{
    // âš ï¸ CRITICAL: Dynamic Dropdown Population (REQUIRED - Company Pattern)
    // This handler populates child dropdown based on parent selection
    
    $ParentCode = $_REQUEST['ParentCode'];  // Get parent selection
    
    // Query related records based on parent
    $sql = mysql_query("SELECT Code, Description FROM related_table WHERE Parent_Code='".$ParentCode."' AND Comp_Code='".$_SESSION['comp_code']."' ORDER BY Description");
    
    // Build JSON array response
    $i = 1;
    $array_ = Array();
    
    while($row = mysql_fetch_object($sql))
    {{
        $values = Array();
        array_push($values, $i);           // Index
        array_push($values, $row->Code);   // Value
        array_push($values, $row->Description);  // Display text
        array_push($array_, $values);
        $i++; 
    }}
    
    // Return JSON response
    echo json_encode($array_);
    exit;
}}

// Example: Area -> SubArea dropdown handler
if($_REQUEST['Action']=='GetSubArea')
{{
    $AreaCode = $_REQUEST['AreaCode'];
    $sql = mysql_query("SELECT Code, Description FROM tblsubarea WHERE Country_Code='".$AreaCode."' AND Comp_Code='".$_SESSION['comp_code']."' ORDER BY Description");
    
    $i = 1;
    $array_ = Array();
    while($row = mysql_fetch_object($sql))
    {{
        $values = Array();
        array_push($values, $i);
        array_push($values, $row->Code);
        array_push($values, $row->Description);
        array_push($array_, $values);
        $i++; 
    }}
    
    echo json_encode($array_);
    exit;
}}

// 5. DELETE LOGIC (if action=Delete) - WITH PRE-DELETE CHECKS (REQUIRED)
if($_REQUEST['action'] == 'Delete')
{{
    // âš ï¸ CRITICAL: Pre-Delete Dependency Checks (REQUIRED - Company Pattern)
    // Check all related tables BEFORE deleting to prevent orphaned records
    // Add checks for each related table that references this record
    
    // Example Check 1: Check if record exists in related_table_1
    /*
    $filter_check = " Foreign_Key_Field='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    if(getrows2("related_table_1", $filter_check) >= 1)
    {{
        print "<script>alert('This record exists in Related Table 1. Cannot delete!');</script>";
        print "<script>document.location='$form'; </script>";
        exit;
    }}
    */
    
    // Example Check 2: Check if record exists in related_table_2
    /*
    $filter_check = " Foreign_Key_Field='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    if(getrows2("related_table_2", $filter_check) >= 1)
    {{
        print "<script>alert('This record exists in Related Table 2. Cannot delete!');</script>";
        print "<script>document.location='$form'; </script>";
        exit;
    }}
    */
    
    // âš ï¸ IMPORTANT: Add ALL related table checks above before proceeding with delete
    // Pattern: Check â†’ Alert â†’ Redirect â†’ Exit (if found)
    // Only proceed to delete if NO dependencies found
    
    // Perform Delete (only if all checks pass)
    $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    if(db_delete($table,$filter))
    {{
        fun_log($_SESSION['user_id'],$_SESSION['comp_code'],$title,add($_REQUEST['major']),"Delete",db_dateFormat(date('Y-m-d')),$_SESSION['login_id']);
        
        // âš ï¸ DELETE from Chart of Accounts (REQUIRED - Company Pattern)
        $chartcode = ACC_CUST.add($_REQUEST['major']).'-0000';
        $del = mysql_query("delete from chart where ACC_CODE = '".$chartcode."' AND Comp_Code='".$_SESSION['comp_code']."'");
        
        print "<script>alert('Record Deleted.'); </script>";
        print "<script>document.location='$form'; </script>";
    }}
}}

// 6. UPDATE DISPLAY (if action=Update)
if($_REQUEST['action'] == 'Update')
{{
    $filter = " Code='".add($_REQUEST['major'])."' AND Comp_Code='".$_SESSION['comp_code']."'";
    $obj = db_getRecord($table,$filter);  // âœ… Use db_getRecord directly, NO mysql_fetch_array!
    $Code = noformat($obj[0],2);
    // Load other fields from $obj array
}}

// 7. SAVE/UPDATE LOGIC (if form submitted)
if ( isset($_POST["txtmode"]) and $_POST["txtmode"]=="save")
{{
    funStartTran();
    
    // Build $columns array for database
    $columns['Code'] = $Code;
    $columns['Comp_Code'] = $_SESSION['comp_code'];
    $columns['UserId'] = $_SESSION['user_id'];
    $columns['Login_ID'] = $_SESSION['login_id'];
    $columns['CreationDateTime'] = db_dateFormat(date('Y-m-d'));
    
    // Add form fields to columns array
    // Example: $columns['Name'] = add_Slashes_new($_REQUEST['Name']);
    
    // âš ï¸ CRITICAL: Chart of Accounts Integration (REQUIRED - Company Pattern)
    // Generate Chart Account Code
    $chartcode = ACC_CUST.$Code.'-0000';  // Format: ACC_CUST + Code + '-0000'
    
    $value = $Code;
    if ( getrows($table," Code",$value) == '1')
    {{
        // UPDATE existing record
        $filter = " Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'";
        db_update($table,$columns,$filter);
        fun_log($_SESSION['user_id'],$_SESSION['comp_code'],$title,$Code,"Update",db_dateFormat(date('Y-m-d')),$_SESSION['login_id']);
        
        // âš ï¸ UPDATE Chart of Accounts (REQUIRED)
        $qry_update = mysql_query("UPDATE chart SET ACC_NAME = '". add_Slashes_new($_REQUEST['Name']) ."' WHERE ACC_CODE= '". $chartcode ."' AND Comp_Code='".$_SESSION['comp_code']."'");
        
        print "<script>alert('".MSG_REC_UPDATED."'); </script>";
    }}
    else
    {{
        // Check if Chart Account already exists (prevent duplicates)
        $ACC_CODE=getvalue("select ACC_CODE from chart where ACC_CODE='".$chartcode."' AND Comp_Code='".$_SESSION['comp_code']."'");
        if($ACC_CODE!=""){{
            echo "<script>alert('Chart Account Already Exists!!!');window.location='".$form."';</script>";
            exit;
        }}
        
        // INSERT new record
        db_insert($table,$columns);
        fun_log($_SESSION['user_id'],$_SESSION['comp_code'],$title,$Code,"Save",db_dateFormat(date('Y-m-d')),$_SESSION['login_id']);
        
        // âš ï¸ INSERT into Chart of Accounts (REQUIRED)
        $qry_insert = mysql_query("INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL,Comp_Code) VALUES ('".$chartcode."' , '". add_Slashes_new($_REQUEST['Name']) ."' ,'D','4','".$_SESSION['comp_code']."')");
        
        print "<script>alert('".MSG_REC_SAVED."'); </script>";
        print "<script>document.location='$form2'; </script>";
    }}
    
    // âš ï¸ CRITICAL: Grid/Detail Records Processing (REQUIRED if master-detail relationship)
    // Company Pattern: Delete old details, insert new details in loop
    unset($columns);
    
    // Delete existing detail records
    db_delete($sub_table," Master_Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."'");
    
    // Insert detail records from grid
    for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++)
    {{
        if($_REQUEST['SR_NO'.$i]!='')
        {{
            $columns['Master_Code']	= $Code;
            $columns['SR_NO']	= $_REQUEST['SR_NO'.$i];
            $columns['Detail_Field1']	= add_Slashes_new($_REQUEST['Detail_Field1'.$i]);
            $columns['Detail_Field2']	= $_REQUEST['Detail_Field2'.$i];
            $columns['Comp_Code'] = $_SESSION['comp_code'];
            
            db_insert($sub_table,$columns) or die(mysql_error());
        }}	
    }}
    
    funEndTran();
    print "<script>document.location='$form'; </script>";
    exit;
}}
?>

<!DOCTYPE html>
<html class="no-js css-menubar" lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title><?=$title;?></title>
  
  <!-- CSS Links and INLINE STYLES -->
  <link rel="stylesheet" href="global/css/bootstrap.min.css">
  <link rel="stylesheet" href="global/vendor/formvalidation/formValidation.css">
  <link rel="stylesheet" href="global/vendor/select2/select2.css">
  <link rel="stylesheet" href="global/vendor/jquery-datepicker/jquery.datepicker.css">
  <link rel="stylesheet" href="assets/css/site.min.css">
  
  <!-- INLINE CSS for this form -->
  <style>
  .form-control {{
      border: 1px solid #B5B0B7;
      height: 23px;
  }}
  
  .text-danger {{
      color: #d9534f;
  }}
  
  .panel {{
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 4px;
      box-shadow: 0 1px 1px rgba(0,0,0,.05);
  }}
  
  .btn-primary {{
      background-color: #337ab7;
      border-color: #2e6da4;
  }}
  
  .btn-success {{
      background-color: #5cb85c;
      border-color: #4cae4c;
  }}
  </style>
  
  <!-- jQuery -->
  <script src="http://code.jquery.com/jquery-1.9.1.js"></script>
  
  <!-- INLINE JAVASCRIPT for this form -->
  <script>
  // Form submission function
  function btnsave_click()
  {{
      if(validateForm()) {{
          document.frm.txtmode.value="save";
          document.frm.action="<?php echo $form2;?>";
          document.frm.method="post";
          document.frm.submit();
      }}
  }}
  
  // Form validation
  function validateForm() {{
      var isValid = true;
      
      // Add validation logic here based on required fields
      var requiredFields = ['Code'];  // Add more fields as needed
      
      for(var i = 0; i < requiredFields.length; i++) {{
          var field = document.getElementById(requiredFields[i]);
          if(field && field.value.trim() === '') {{
              alert('Please fill in ' + requiredFields[i]);
              field.focus();
              return false;
          }}
      }}
      
      return isValid;
  }}
  
  // Keyboard navigation (REQUIRED - Company Pattern)
  document.onkeydown = checkKeycode
  function checkKeycode(e,field) 
  {{
      var keycode;
      if (window.event) 
          keycode = window.event.keyCode;
      else if (e) 
          keycode = e.which;
      
      // âš ï¸ CRITICAL: Map ALL fields in sequence for Enter key navigation
      // Company Pattern: Each field moves to next field on Enter (keycode 13)
      // This enables fast data entry without mouse
      
      // Enter key navigation between fields (keycode 13)
      if(keycode == 13) {{
          // Example field navigation sequence:
          // Field1 â†’ Field2 â†’ Field3 â†’ ... â†’ Save Button
          
          /*
          if(field == 'Code') {{
              document.getElementById('Name').focus();
          }}
          else if(field == 'Name') {{
              document.getElementById('Description').focus();
          }}
          else if(field == 'Description') {{
              document.getElementById('Category').focus();
          }}
          else if(field == 'Category') {{
              document.getElementById('Status').focus();
          }}
          else if(field == 'Status') {{
              document.getElementById('btnSave').focus();
          }}
          */
          
          // âš ï¸ IMPORTANT: Add navigation for EVERY field in the form
          // Last field should focus on btnSave button
      }}
      
      // ESC key to go back (keycode 27)
      if(keycode == 27) {{
          window.location = '<?php echo $form; ?>';
      }}
      
      // F2 key for quick save (keycode 113)
      if(keycode == 113) {{
          document.getElementById('btnSave').click();
      }}
  }}
  
  // âš ï¸ CRITICAL: Grid/Detail Records Management (REQUIRED if master-detail relationship)
  // Company Pattern: Dynamic grid for adding/editing/deleting detail records
  
  var gridIndex = 0;
  var gridData = new Array(1000);
  for(var i=0; i<1000; i++)
      gridData[i] = new Array(10);
  
  // Add new row to grid
  function addGridRow() {{
      gridIndex++;
      var sr = gridIndex;
      
      var row = '<tr id="row' + sr + '">';
      row += '<td>' + sr + '<input type="hidden" name="SR_NO' + sr + '" id="SR_NO' + sr + '" value="' + sr + '"></td>';
      row += '<td><input type="text" class="form-control input-sm" name="Detail_Field1' + sr + '" id="Detail_Field1' + sr + '" onKeyDown="checkKeycode(event,this.id);"></td>';
      row += '<td><input type="text" class="form-control input-sm" name="Detail_Field2' + sr + '" id="Detail_Field2' + sr + '" onKeyDown="checkKeycode(event,this.id);"></td>';
      row += '<td><button type="button" class="btn btn-danger btn-sm" onclick="deleteGridRow(' + sr + ')">Delete</button></td>';
      row += '</tr>';
      
      $('#gridTableBody').append(row);
      $('#TXTCOUNTACC').val(gridIndex);
      
      // Focus on first field of new row
      $('#Detail_Field1' + sr).focus();
  }}
  
  // Delete row from grid
  function deleteGridRow(sr) {{
      if(confirm('Are you sure you want to delete this row?')) {{
          $('#row' + sr).remove();
          // Mark as deleted in hidden field
          $('#SR_NO' + sr).val('');
      }}
  }}
  
  // Edit row in grid
  function editGridRow(sr) {{
      // Enable fields for editing
      $('#Detail_Field1' + sr).prop('readonly', false);
      $('#Detail_Field2' + sr).prop('readonly', false);
      $('#Detail_Field1' + sr).focus();
  }}
  
  // Load existing detail records on update
  function loadGridData() {{
      // This function loads existing detail records when editing
      // Called on page load if action=Update
      <?php
      if($_REQUEST['action'] == 'Update') {{
          $sql = mysql_query("SELECT * FROM $sub_table WHERE Master_Code='".$Code."' AND Comp_Code='".$_SESSION['comp_code']."' ORDER BY SR_NO");
          $sr = 0;
          while($row = mysql_fetch_array($sql)) {{
              $sr++;
              ?>
              addGridRow();
              $('#Detail_Field1<?php echo $sr; ?>').val('<?php echo addslashes($row['Detail_Field1']); ?>');
              $('#Detail_Field2<?php echo $sr; ?>').val('<?php echo $row['Detail_Field2']; ?>');
              <?php
          }}
      }}
      ?>
  }}
  
  // Form initialization
  function initializeForm() {{
      // Set focus to first field
      var firstField = document.getElementById('Code');
      if(firstField) firstField.focus();
      
      // Initialize Select2 for dropdown fields (REQUIRED - Company Pattern)
      $('.select2-field').select2({{
          placeholder: 'Select an option',
          allowClear: true,
          width: '100%'
      }});
      
      // âš ï¸ CRITICAL: Select2 with Keyboard Navigation Integration
      // Company Pattern: Auto-open on focus, move to next field on close
      
      // Example: Area dropdown with keyboard navigation
      /*
      $('#AreaCode').select2({{
          placeholder: 'Select Area',
          allowClear: true,
          width: '100%'
      }})
      .on("select2:close", function () {{
          setTimeout(function() {{
              $('.select2-container-active').removeClass('select2-container-active');
              $(':focus').blur();
              $('#SubAreaCode').focus();
              $('#SubAreaCode').select2('open');  // Auto-open next dropdown
          }}, 1);
      }});
      
      // Auto-open on focus
      $('#AreaCode').focus(function() {{
          $('#AreaCode').select2('open');
      }});
      */
      
      // âš ï¸ IMPORTANT: Add Select2 initialization for ALL dropdown fields
      // Pattern: Initialize â†’ Add close event â†’ Add focus event
      // This enables seamless keyboard navigation through dropdowns
      
      // Initialize Datepicker for date fields
      $('.datepicker-field').datepicker({{
          dateFormat: 'yy-mm-dd',
          changeMonth: true,
          changeYear: true
      }});
      
      // Initialize FormValidation plugin (REQUIRED - Company Pattern)
      $('#frm').formValidation({{
          framework: "bootstrap",
          button: {{
              selector: '#btnSave',
              disabled: 'disabled'
          }},
          icon: null,
          fields: {{
              // âš ï¸ CRITICAL: Add validation rules for EACH field
              // Company Pattern: Specific messages, row selectors, custom validators
              
              // Example: Text field validation
              /*
              FieldName: {{
                  row: '.col-md-4',  // Match the column class
                  validators: {{
                      notEmpty: {{
                          message: 'Field Name is required and cannot be empty'
                      }},
                      stringLength: {{
                          max: 50,
                          message: 'Field Name must be less than 50 characters'
                      }}
                  }}
              }},
              */
              
              // Example: Dropdown validation with callback
              /*
              DropdownField: {{
                  row: '.col-md-4',
                  validators: {{
                      notEmpty: {{
                          message: 'Please Select an option'
                      }},
                      callback: {{
                          message: 'Please Select an option',
                          callback: function(value, validator, $field) {{
                              if(document.getElementById('DropdownField').value == '-1') {{
                                  return {{
                                      valid: false,
                                      message: 'Please Select an option'
                                  }}
                              }}
                              return true;
                          }}
                      }}
                  }}
              }},
              */
              
              // Example: Email validation
              /*
              EmailField: {{
                  row: '.col-md-4',
                  validators: {{
                      regexp: {{
                          regexp: '^[^@\\\\s]+@([^@\\\\s]+\\\\.)+[^@\\\\s]+$',
                          message: 'Enter Valid Email address'
                      }}
                  }}
              }},
              */
              
              // Example: Numeric validation
              /*
              NumericField: {{
                  row: '.col-md-4',
                  validators: {{
                      notEmpty: {{
                          message: 'Field is required'
                      }},
                      numeric: {{
                          message: 'Please enter numbers only'
                      }},
                      between: {{
                          min: 0,
                          max: 999999,
                          message: 'Value must be between 0 and 999999'
                      }}
                  }}
              }}
              */
          }}
      }})
      .on('success.form.fv', function(e) {{
          e.preventDefault();
          btnsave_click();
      }});
  }}
  
  // AJAX Auto-ID Generation (REQUIRED - Company Pattern)
  function maxid() {{
      {f"var {hierarchy_pattern.get('parent_request_param', 'SelectArea')} = document.getElementById('{hierarchy_pattern.get('parent_js_field_id', 'Main_Area')}').value;" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}
      $.ajaxSetup({{async:false}});
      $.post("<?php echo $form2; ?>", {{Action:'GetMaxID'{f", {hierarchy_pattern.get('parent_request_param', 'SelectArea')}: {hierarchy_pattern.get('parent_request_param', 'SelectArea')}" if hierarchy_pattern and hierarchy_pattern.get('is_hierarchical') else ''}}}, function(data) {{ 
          if(data != '') {{
              $('#Code').val(data);
          }}
      }});
  }}
  
  // AJAX Dynamic Dropdown Population (REQUIRED - Company Pattern)
  function loadDynamicDropdown(parentField, childField, action) {{
      var parentValue = document.getElementById(parentField).value;
      
      // Clear child dropdown if parent is empty
      if(parentValue == '' || parentValue == '-1') {{
          $('#' + childField).empty().append('<option value="-1">SELECT</option>');
          return;
      }}
      
      // Show loading indicator
      $('#' + childField).empty().append('<option value="">Loading...</option>');
      
      $.ajax({{
          url: "<?php echo $form2; ?>",
          type: "POST",
          data: {{ Action: action, ParentCode: parentValue }},
          dataType: "json",
          success: function(msg) {{
              var $dropdown = $('#' + childField);
              $dropdown.empty();
              $dropdown.append('<option value="-1">SELECT</option>');
              
              // Populate dropdown with response data
              for (var i = 0; i < msg.length; i++) {{
                  var index = 1;  // msg[i][0] is index
                  var code = msg[i][index];      // msg[i][1] is Code
                  var description = msg[i][index+1];  // msg[i][2] is Description
                  $dropdown.append('<option value="' + code + '">' + description + '</option>');
              }}
              
              $dropdown.change();
          }},
          error: function(xhr, status, error) {{
              console.error('AJAX Error:', error);
              alert('Error loading data: ' + error);
              $('#' + childField).empty().append('<option value="-1">SELECT</option>');
          }}
      }});
  }}
  
  // Example: Area -> SubArea dropdown
  function loadSubArea() {{
      var areaCode = document.getElementById('AreaCode').value;
      if(areaCode == '' || areaCode == '-1') {{
          $('#SubAreaCode').empty().append('<option value="-1">SELECT</option>');
          return;
      }}
      
      $.ajax({{
          url: "<?php echo $form2; ?>",
          type: "POST",
          data: {{ Action: 'GetSubArea', AreaCode: areaCode }},
          dataType: "json",
          success: function(msg) {{
              var $subArea = $('#SubAreaCode');
              $subArea.empty();
              $subArea.append('<option value="-1">SELECT</option>');
              
              for (var i = 0; i < msg.length; i++) {{
                  $subArea.append('<option value="' + msg[i][1] + '">' + msg[i][2] + '</option>');
              }}
              
              $subArea.change();
          }},
          error: function(xhr, status, error) {{
              console.error('AJAX Error:', error);
              alert('Error loading sub areas');
          }}
      }});
  }}
  </script>
</head>
<body class="site-navbar-small" onLoad="initializeForm();">
  
  <?php include("include/topmenu.php");?>
  <?php include("include/sidemenu.php");?>
  
  <div class="page animsition">
    <?php include("include/formheader.php"); ?>
    
    <div class="page-content padding-5">
      <div class="panel">
        <div class="panel-body container-fluid">
          <div class="row row-lg">
            <div class="col-sm-12 col-md-12">
              
              <!-- FORM -->
              <form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>">
                
                <!-- Code Field (readonly) -->
                <div class="form-group">
                  <label class="col-md-4 control-label">Code:</label>
                  <div class="col-md-2">
                    <input type="text" class="form-control" name="Code" id="Code" readonly value="<?php echo $Code;?>" onKeyDown="checkKeycode(event,this.id);" />
                  </div>
                </div>
                
                <!-- IMPORTANT: Generate form fields using COMPANY PATTERN -->
                <!-- Each field MUST follow this structure:
                
                TEXT FIELD:
                <div class="form-group">
                  <label class="col-md-4 control-label">Field Label <span class="text-danger">*</span>:</label>
                  <div class="col-md-4">
                    <input type="text" class="form-control" name="fieldname" id="fieldname" value="<?php echo stripslashes($obj['fieldname']);?>" onKeyDown="checkKeycode(event,this.id);" />
                  </div>
                </div>
                
                DROPDOWN/SELECT2 FIELD:
                <div class="form-group">
                  <label class="col-md-4 control-label">Select Option <span class="text-danger">*</span>:</label>
                  <div class="col-md-4">
                    <select class="form-control select2-field" data-plugin="select2" name="selectfield" id="selectfield" onKeyDown="checkKeycode(event,this.id);">
                      <option value="-1">-- Select --</option>
                      <option value="1">Option 1</option>
                      <option value="2">Option 2</option>
                    </select>
                  </div>
                </div>
                
                âš ï¸ CRITICAL: Dropdown fields MUST have:
                - class="form-control select2-field" for styling and Select2
                - data-plugin="select2" for automatic initialization
                - onKeyDown="checkKeycode(event,this.id);" for keyboard navigation
                
                DATEPICKER FIELD:
                <div class="form-group">
                  <label class="col-md-4 control-label">Date <span class="text-danger">*</span>:</label>
                  <div class="col-md-4">
                    <input type="text" class="form-control datepicker-field" name="datefield" id="datefield" value="<?php echo $obj['datefield'];?>" onKeyDown="checkKeycode(event,this.id);" />
                  </div>
                </div>
                
                TEXTAREA FIELD:
                <div class="form-group">
                  <label class="col-md-4 control-label">Description:</label>
                  <div class="col-md-4">
                    <textarea class="form-control" name="description" id="description" rows="3" onKeyDown="checkKeycode(event,this.id);"><?php echo stripslashes($obj['description']);?></textarea>
                  </div>
                </div>
                
                âš ï¸ CRITICAL: ALL input fields MUST have onKeyDown="checkKeycode(event,this.id);" attribute
                This enables keyboard navigation between fields
                -->
                
                <!-- Generate form fields based on database schema -->
                <!-- Each field should have embedded PHP for values -->
                
                <!-- âš ï¸ OPTIONAL: Grid/Detail Records Section (if master-detail relationship) -->
                <!--
                <div class="form-group">
                  <div class="col-md-12">
                    <h4>Detail Records</h4>
                    <button type="button" class="btn btn-primary btn-sm" onclick="addGridRow()">Add Row</button>
                    <table class="table table-bordered" id="gridTable">
                      <thead>
                        <tr>
                          <th>Sr#</th>
                          <th>Detail Field 1</th>
                          <th>Detail Field 2</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody id="gridTableBody">
                        <!-- Rows added dynamically via JavaScript -->
                      </tbody>
                    </table>
                    <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="0">
                  </div>
                </div>
                -->
                
                <!-- Buttons -->
                <div class="form-group">
                  <div class="col-md-12" align="center">
                    <button type="button" name="btnSave" id="btnSave" class="btn btn-primary" accesskey="s" onclick="btnsave_click()">Save</button>
                    <button type="button" class="btn btn-success" onClick="window.location='<?=$form; ?>'">Back</button>
                    <input type="hidden" id="txtmode" name="txtmode" value="new">
                    <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action'];?>">
                  </div>
                </div>
                
              </form>
              
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <?php include("include/footer.php");?>
  
  <!-- Additional Scripts -->
  <script src="global/vendor/jquery/jquery.js"></script>
  <script src="global/vendor/bootstrap/bootstrap.js"></script>
  <script src="global/vendor/formvalidation/formValidation.min.js"></script>
  <script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
  <script src="global/vendor/select2/select2.min.js"></script>
  <script src="global/vendor/jquery-datepicker/jquery.datepicker.min.js"></script>
  <script src="assets/js/site.js"></script>
  
</body>
</html>
```

=== CRITICAL RULES ===

1. **ONE FILE ONLY** - Generate a SINGLE PHP file with everything inline
2. **PHP AT TOP** - All PHP logic BEFORE the HTML
3. **EMBEDDED PHP** - Use <?php echo $var; ?> inside HTML
4. **INLINE JAVASCRIPT** - Put JS in <script> tags in <head>
5. **COMPANY FUNCTIONS ONLY** - Use ONLY: db_insert, db_update, db_delete, db_getRecord, getrows, getvalue, add, noformat, funStartTran, funEndTran, fun_log
6. **NO STANDARD PHP** - DO NOT use: mysql_query, mysqli, PDO, or any other database library
7. **COMPANY STRUCTURE** - Follow the EXACT structure from examples
8. **FORM PROCESSING** - Check txtmode="save" for form submission
9. **LOGGING** - Use fun_log for ALL operations (Save, Update, Delete)
10. **ALERTS** - Use print "<script>alert(...);</script>"
11. **REDIRECTS** - Use print "<script>document.location=...;</script>"
12. **SESSION CHECKS** - Always use $_SESSION['comp_code'] in queries
13. **FIELD MAPPING** - Map database fields to form inputs with embedded PHP
14. **CSS CLASSES - MANDATORY** - EVERY form field MUST use: form-group, col-md-4, col-md-2, form-control, text-danger
15. **FORM TAG** - MUST have class="form-horizontal" on the <form> tag
16. **BUTTON CLASSES** - EVERY button MUST have: btn, btn-primary or btn-success classes
17. **PANEL STRUCTURE** - MUST wrap form in <div class="panel"><div class="panel-body">
18. **GRID LAYOUT** - MUST use col-md-4 for labels, col-md-2 or col-md-4 for inputs
19. **REQUIRED FIELDS** - MUST mark required fields with <span class="text-danger">*</span>
20. **FORM-GROUP WRAPPER** - EVERY form field MUST be wrapped in <div class="form-group">
21. **FORM-CONTROL CLASS** - EVERY input/select/textarea MUST have class="form-control"
22. **TRANSACTIONS** - MUST wrap all database operations in funStartTran() and funEndTran()
23. **COLUMNS ARRAY** - MUST build $columns array for db_insert/db_update
24. **FILTER STRING** - MUST build $filter string for db_update/db_delete with Comp_Code check

âš ï¸ VALIDATION FAILURE: If your code is missing company functions or CSS classes, it will FAIL validation and be rejected!

=== FIELD MAPPING ===

Based on the database schema, generate form fields with:
- Proper labels
- Embedded PHP for values: value="<?php echo stripslashes($obj['FieldName']);?>"
- Keyboard navigation in JavaScript
- Required field indicators (*)
- Company styling classes

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE A - FIX C-6: COMPLETE FIELD GENERATION (NO SHORTCUTS) ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - EVERY FIELD MUST BE WRITTEN EXPLICITLY âš ï¸âš ï¸âš ï¸

âŒ FORBIDDEN SHORTCUTS (Will cause VALIDATION FAILURE):
- "// ... rest of fields"
- "// similar to above"
- "// Add remaining fields"
- "<!-- Similar structure for other fields -->"
- "// Repeat for other fields"
- "... (continue for all fields)"

âœ… REQUIRED - Write EVERY field COMPLETELY:

For EACH field in the list, you MUST write:

1. **HTML Form Field** (COMPLETE):
```html
<div class="form-group">
  <label class="col-md-4 control-label">Field Label <span class="text-danger">*</span>:</label>
  <div class="col-md-4">
    <input type="text" class="form-control" name="FieldName" id="FieldName" 
           value="<?php echo stripslashes($obj['FieldName']);?>" 
           onKeyDown="checkKeycode(event,this.id);" />
  </div>
</div>
```

2. **PHP $columns Mapping** (COMPLETE):
```php
$columns['FieldName'] = $_REQUEST['FieldName'];
```

3. **JavaScript Keyboard Navigation** (COMPLETE):
```javascript
if(field == 'FieldName') {{
    document.getElementById('NextField').focus();
    return false;
}}
```

4. **FormValidation Rule** (COMPLETE):
```javascript
FieldName: {{
    row: '.col-md-4',
    validators: {{
        notEmpty: {{
            message: 'Field Label is required'
        }}
    }}
}},
```

âš ï¸ C-6 VALIDATION: Your code will be scanned for:
- HTML: <input name="FieldName"> for EACH field
- PHP: $columns['FieldName'] for EACH field
- JS: if(field == 'FieldName') for EACH field
- FormValidation: FieldName: {{ validators: ... }} for EACH field

If ANY field is missing from ANY section, validation will FAIL!

ðŸ”´ðŸ”´ðŸ”´ END C-6 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE A - FIX C-7: COMPLETE JAVASCRIPT GENERATION ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - ALL JAVASCRIPT FUNCTIONS MUST BE COMPLETE âš ï¸âš ï¸âš ï¸

âŒ FORBIDDEN SHORTCUTS (Will cause VALIDATION FAILURE):
- "// ... rest of function"
- "// similar logic for other fields"
- "// Add more cases"
- "// Continue for all fields"
- Incomplete checkKeycode() function
- Incomplete FormValidation rules
- Missing Select2 event handlers

âœ… REQUIRED - Write ALL JavaScript COMPLETELY:

1. **checkKeycode() Function** (MUST include ALL fields):
```javascript
function checkKeycode(e, field) {{
    var keycode;
    if (window.event) keycode = window.event.keyCode;
    else if (e) keycode = e.which;
    
    if(keycode == 13) {{
        // âœ… C-7: Write case for EVERY field
        if(field == 'Field1') {{ document.getElementById('Field2').focus(); return false; }}
        if(field == 'Field2') {{ document.getElementById('Field3').focus(); return false; }}
        if(field == 'Field3') {{ document.getElementById('Field4').focus(); return false; }}
        // ... CONTINUE FOR ALL FIELDS (no shortcuts!)
        if(field == 'LastField') {{ document.getElementById('btnSave').focus(); return false; }}
    }}
}}
```

2. **FormValidation Rules** (MUST include ALL fields):
```javascript
$('#frm').formValidation({{
    framework: "bootstrap",
    fields: {{
        // âœ… C-7: Write validator for EVERY field
        Field1: {{ row: '.col-md-4', validators: {{ notEmpty: {{ message: 'Required' }} }} }},
        Field2: {{ row: '.col-md-4', validators: {{ notEmpty: {{ message: 'Required' }} }} }},
        Field3: {{ row: '.col-md-4', validators: {{ notEmpty: {{ message: 'Required' }} }} }},
        // ... CONTINUE FOR ALL FIELDS (no shortcuts!)
    }}
}});
```

3. **Select2 Event Handlers** (MUST include for ALL dropdowns):
```javascript
$('#Dropdown1').on("select2:close", function () {{
    setTimeout(function() {{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#Dropdown2').focus();
        $('#Dropdown2').select2('open');
    }}, 1);
}});

$('#Dropdown2').on("select2:close", function () {{
    setTimeout(function() {{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#TextField1').focus();
    }}, 1);
}});
```

âš ï¸ C-7 VALIDATION: Your code will be scanned for:
- checkKeycode: if(field == 'FieldName') for EACH field
- FormValidation: FieldName: {{ validators: ... }} for EACH field
- Select2: .on("select2:close") for EACH dropdown

If ANY field is missing from ANY JavaScript section, validation will FAIL!

ðŸ”´ðŸ”´ðŸ”´ END C-7 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-8: FORMVALIDATION.JS INTEGRATION ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - FORMVALIDATION PLUGIN MUST BE PROPERLY INTEGRATED âš ï¸âš ï¸âš ï¸

FormValidation is a jQuery plugin that validates form fields BEFORE submission.
Company uses specific patterns that MUST be followed EXACTLY.

âœ… REQUIRED COMPONENTS:

1. **Include FormValidation Scripts** (in <head> or before </body>):
```html
<script src="global/vendor/formvalidation/formValidation.min.js"></script>
<script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
```

2. **Initialize FormValidation** (in <script> section):
```javascript
$('#frm').formValidation({{
    framework: "bootstrap",
    button: {{
        selector: '#btnSave',
        disabled: 'disabled'
    }},
    icon: null,
    fields: {{
        // âœ… C-8: Add validator for EVERY field
        FieldName: {{
            row: '.col-md-4',  // Match the column class used in HTML
            validators: {{
                notEmpty: {{
                    message: 'Field Name is required and cannot be empty'
                }},
                stringLength: {{
                    max: 50,
                    message: 'Field Name must be less than 50 characters'
                }}
            }}
        }},
        // ... Continue for ALL fields
    }}
}})
.on('success.form.fv', function(e) {{
    e.preventDefault();
    btnsave_click();  // Call save function on validation success
}});
```

3. **Validator Types** (use appropriate validators for each field):
```javascript
// Text field - notEmpty + stringLength
FieldName: {{
    row: '.col-md-4',
    validators: {{
        notEmpty: {{ message: 'Required' }},
        stringLength: {{ max: 100, message: 'Too long' }}
    }}
}},

// Dropdown - notEmpty + callback
DropdownField: {{
    row: '.col-md-4',
    validators: {{
        notEmpty: {{ message: 'Please select' }},
        callback: {{
            message: 'Please select an option',
            callback: function(value, validator, $field) {{
                if(document.getElementById('DropdownField').value == '-1') {{
                    return {{ valid: false, message: 'Please select' }}
                }}
                return true;
            }}
        }}
    }}
}},

// Email field - regexp
EmailField: {{
    row: '.col-md-4',
    validators: {{
        regexp: {{
            regexp: '^[^@\\\\s]+@([^@\\\\s]+\\\\.)+[^@\\\\s]+$',
            message: 'Enter valid email'
        }}
    }}
}},

// Numeric field - numeric + between
NumericField: {{
    row: '.col-md-4',
    validators: {{
        notEmpty: {{ message: 'Required' }},
        numeric: {{ message: 'Numbers only' }},
        between: {{ min: 0, max: 999999, message: 'Invalid range' }}
    }}
}}
```

âš ï¸ C-8 VALIDATION: Your code will be scanned for:
- Script tags: formValidation.min.js and bootstrap.min.js
- Initialization: $('#frm').formValidation({{
- Event handler: .on('success.form.fv', ...)
- Field validators: FieldName: {{ validators: ... }} for EACH field

ðŸ”´ðŸ”´ðŸ”´ END C-8 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-9: FOOTER SCRIPTS (30+ SCRIPT TAGS) ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - THIS IS THE #1 CAUSE OF VALIDATION FAILURES âš ï¸âš ï¸âš ï¸

Research Finding: LLMs skip footer scripts thinking they are "boilerplate"
This causes a 7,773 character gap (Company: 17,785 chars vs Generated: 10,012 chars)

The missing section is: 30+ vendor script tags (~4,500 characters)

YOU MUST INCLUDE ALL 30+ FOOTER SCRIPT TAGS - NO EXCEPTIONS!

âœ… REQUIRED FOOTER SCRIPTS (Place before </body>):

```html
<!-- MANDATORY FOOTER SCRIPTS - DO NOT SKIP ANY -->
<script src="global/vendor/jquery/jquery.js"></script>
<script src="global/vendor/bootstrap/bootstrap.js"></script>
<script src="global/vendor/animsition/animsition.js"></script>
<script src="global/vendor/asscroll/jquery-asScroll.js"></script>
<script src="global/vendor/mousewheel/jquery.mousewheel.js"></script>
<script src="global/vendor/asscrollable/jquery.asScrollable.all.js"></script>
<script src="global/vendor/ashoverscroll/jquery-asHoverScroll.js"></script>
<script src="global/vendor/jquery-mmenu/jquery.mmenu.min.all.js"></script>
<script src="global/vendor/switchery/switchery.min.js"></script>
<script src="global/vendor/intro-js/intro.js"></script>
<script src="global/vendor/screenfull/screenfull.js"></script>
<script src="global/vendor/slidepanel/jquery-slidePanel.js"></script>
<script src="global/vendor/blueimp-tmpl/tmpl.js"></script>
<script src="global/vendor/blueimp-canvas-to-blob/canvas-to-blob.js"></script>
<script src="global/vendor/blueimp-load-image/load-image.all.min.js"></script>
<script src="global/vendor/dropify/dropify.min.js"></script>
<script src="global/vendor/formvalidation/formValidation.min.js"></script>
<script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
<script src="global/js/core.js"></script>
<script src="assets/js/site.js"></script>
<script src="assets/js/sections/menu.js"></script>
<script src="assets/js/sections/menubar.js"></script>
<script src="assets/js/sections/gridmenu.js"></script>
<script src="assets/js/sections/sidebar.js"></script>
<script src="global/js/configs/config-colors.js"></script>
<script src="assets/js/configs/config-tour.js"></script>
<script src="global/js/components/asscrollable.js"></script>
<script src="global/js/components/animsition.js"></script>
<script src="global/js/components/slidepanel.js"></script>
<script src="global/js/components/switchery.js"></script>
<script src="global/js/components/dropify.js"></script>
<script src='global/js/funJs.js'></script>
<!-- END MANDATORY FOOTER SCRIPTS -->
```

âš ï¸ THESE SCRIPTS ARE REQUIRED FOR:
- FormValidation to work properly (formValidation.min.js)
- Keyboard navigation to function (funJs.js)
- Bootstrap UI components to render (bootstrap.js)
- Menu/sidebar to work (menu.js, sidebar.js)
- Animations and transitions (animsition.js)
- File uploads (dropify.js)
- Custom company functions (funJs.js)

âš ï¸ C-9 VALIDATION: Your code will be scanned for:
- Minimum 30 <script src="..."> tags before </body>
- Specific scripts: jquery.js, bootstrap.js, formValidation.min.js, funJs.js
- Total footer script section: ~4,500 characters

IF YOU SKIP EVEN ONE SCRIPT TAG, THE FORM WILL NOT WORK!

ðŸ”´ðŸ”´ðŸ”´ END C-9 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-10: ONKEYDOWN EVENT HANDLERS ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - EVERY INPUT FIELD MUST HAVE ONKEYDOWN âš ï¸âš ï¸âš ï¸

The onKeyDown attribute enables keyboard navigation (Enter key moves to next field).
This is a CORE company pattern that MUST be present on EVERY input field.

âœ… REQUIRED PATTERN:

1. **HTML Input Fields** (EVERY field needs onKeyDown):
```html
<input type="text" class="form-control" name="FieldName" id="FieldName" 
       value="<?php echo stripslashes($obj['FieldName']);?>" 
       onKeyDown="checkKeycode(event,this.id);" />

<select class="form-control" name="DropdownField" id="DropdownField" 
        onKeyDown="checkKeycode(event,this.id);">
    <option value="-1">SELECT</option>
</select>

<textarea class="form-control" name="TextField" id="TextField" 
          onKeyDown="checkKeycode(event,this.id);"><?php echo $obj['TextField'];?></textarea>
```

2. **JavaScript checkKeycode() Function** (handles Enter key):
```javascript
document.onkeydown = checkKeycode;

function checkKeycode(e, field) {{
    var keycode;
    if (window.event) 
        keycode = window.event.keyCode;
    else if (e) 
        keycode = e.which;
    
    if(keycode == 13) {{  // Enter key pressed
        // âœ… C-10: Navigation chain for ALL fields
        if(field == 'Field1') {{ document.getElementById('Field2').focus(); return false; }}
        if(field == 'Field2') {{ document.getElementById('Field3').focus(); return false; }}
        if(field == 'Field3') {{ document.getElementById('Field4').focus(); return false; }}
        // ... Continue for ALL fields
        if(field == 'LastField') {{ document.getElementById('btnSave').focus(); return false; }}
    }}
}}
```

âš ï¸ C-10 VALIDATION: Your code will be scanned for:
- HTML: onKeyDown="checkKeycode(event,this.id);" on EVERY input/select/textarea
- JavaScript: function checkKeycode(e, field) with if(keycode == 13)
- Navigation: if(field == 'FieldName') for EVERY field

Missing onKeyDown on ANY field = VALIDATION FAILURE!

ðŸ”´ðŸ”´ðŸ”´ END C-10 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-11: ONLOAD INITIALIZATION ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - BODY ONLOAD MUST INITIALIZE FORM âš ï¸âš ï¸âš ï¸

The onLoad attribute on <body> tag initializes the form when page loads.
Company pattern: Auto-open first dropdown on new records, set focus on update.

âœ… REQUIRED PATTERN:

1. **Body Tag with onLoad**:
```html
<body class="site-navbar-small" onLoad="initializeForm();">
```

2. **initializeForm() Function**:
```javascript
function initializeForm() {{
    <?php if($_REQUEST['action'] != 'Update') {{ ?>
        // New record - auto-open first dropdown
        $('#FirstDropdownField').select2('open');
    <?php }} else {{ ?>
        // Update mode - set focus to first editable field
        $('#FirstEditableField').focus();
    <?php }} ?>
    
    // Initialize Select2 for all dropdowns
    $('.select2-field').select2({{
        placeholder: 'Select an option',
        allowClear: true,
        width: '100%'
    }});
    
    // Initialize Datepicker for date fields
    $('.datepicker-field').datepicker({{
        dateFormat: 'yy-mm-dd',
        changeMonth: true,
        changeYear: true
    }});
}}
```

3. **Alternative Pattern** (if no dropdowns):
```html
<body class="site-navbar-small" onLoad="maxid();">
```

âš ï¸ C-11 VALIDATION: Your code will be scanned for:
- HTML: <body ... onLoad="initializeForm();" or onLoad="maxid();">
- JavaScript: function initializeForm() with initialization logic
- Select2 initialization: $('.select2-field').select2({{...}})

Missing onLoad = Form won't initialize properly!

ðŸ”´ðŸ”´ðŸ”´ END C-11 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-12: JQUERY CDN LINKS ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - JQUERY AND PLUGINS MUST BE LOADED âš ï¸âš ï¸âš ï¸

jQuery and its plugins are REQUIRED for the form to work.
Company uses specific vendor paths that MUST be included.

âœ… REQUIRED CDN/VENDOR LINKS (in <head> section):

1. **CSS Links** (MUST include ALL):
```html
<link href="global/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
<link href="global/vendor/animsition/animsition.min.css" rel="stylesheet">
<link href="global/vendor/asscrollable/asScrollable.min.css" rel="stylesheet">
<link href="global/vendor/switchery/switchery.min.css" rel="stylesheet">
<link href="global/vendor/intro-js/introjs.min.css" rel="stylesheet">
<link href="global/vendor/slidepanel/slidePanel.min.css" rel="stylesheet">
<link href="global/vendor/flag-icon-css/flag-icon.min.css" rel="stylesheet">
<link href="global/vendor/waves/waves.min.css" rel="stylesheet">
<link href="global/vendor/formvalidation/formValidation.min.css" rel="stylesheet">
<link href="global/vendor/select2/select2.min.css" rel="stylesheet">
<link href="assets/examples/css/forms/validation.min.css" rel="stylesheet">
<link href="global/fonts/web-icons/web-icons.min.css" rel="stylesheet">
<link href="global/fonts/brand-icons/brand-icons.min.css" rel="stylesheet">
<link href='global/fonts/font-awesome/font-awesome.css' rel='stylesheet'>
<link href="assets/css/site.min.css" rel="stylesheet">
```

2. **JavaScript Core** (in <head> or before custom scripts):
```html
<script src="global/vendor/breakpoints/breakpoints.js"></script>
<script src="assets/js/State.js"></script>
<script src="assets/js/Component.js"></script>
<script src="assets/js/Plugin.js"></script>
<script src="assets/js/Base.js"></script>
<script src="assets/js/Config.js"></script>
<script src="global/vendor/babel-external-helpers/babel-external-helpers.js"></script>
```

âš ï¸ C-12 VALIDATION: Your code will be scanned for:
- CSS: Minimum 15 <link> tags in <head>
- Specific CSS: bootstrap.min.css, formValidation.min.css, select2.min.css
- JavaScript: Core vendor scripts (breakpoints.js, State.js, etc.)

Missing CDN links = Styling and functionality will break!

ðŸ”´ðŸ”´ðŸ”´ END C-12 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE B - FIX C-13: SELECT2 EVENT HANDLERS ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - SELECT2 DROPDOWNS NEED EVENT HANDLERS âš ï¸âš ï¸âš ï¸

Select2 is a jQuery plugin that enhances dropdowns with search functionality.
Company uses specific event handlers for keyboard navigation and cascading.

âœ… REQUIRED PATTERN:

1. **HTML Dropdown with Select2**:
```html
<select class="form-control select2-field" 
        data-plugin="select2" 
        name="DropdownField" 
        id="DropdownField" 
        onKeyDown="checkKeycode(event,this.id);">
    <option value="-1">SELECT</option>
    <?php
    $sql = mysql_query("SELECT Code, Description FROM tbltable WHERE Comp_Code='".$_SESSION['comp_code']."'");
    while($row = mysql_fetch_array($sql)) {{
    ?>
        <option value="<?php echo $row['Code']; ?>"><?php echo $row['Description']; ?></option>
    <?php }} ?>
</select>
```

2. **Select2 Initialization**:
```javascript
$('.select2-field').select2({{
    placeholder: 'Select an option',
    allowClear: true,
    width: '100%'
}});
```

3. **Select2 Event Handlers** (for keyboard navigation):
```javascript
// âœ… C-13: Close event handler (moves to next field)
$('#DropdownField1').on("select2:close", function () {{
    setTimeout(function() {{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#DropdownField2').focus();
        $('#DropdownField2').select2('open');  // Auto-open next dropdown
    }}, 1);
}});

$('#DropdownField2').on("select2:close", function () {{
    setTimeout(function() {{
        $('.select2-container-active').removeClass('select2-container-active');
        $(':focus').blur();
        $('#TextField1').focus();  // Move to text field
    }}, 1);
}});

// âœ… C-13: Focus event handler (auto-open on focus)
$('#DropdownField1').focus(function() {{
    $('#DropdownField1').select2('open');
}});

$('#DropdownField2').focus(function() {{
    $('#DropdownField2').select2('open');
}});
```

4. **Cascading Dropdown Pattern** (if parent-child relationship):
```javascript
// Parent dropdown change triggers child population
$('#ParentDropdown').on("change", function() {{
    loadChildDropdown();  // AJAX call to populate child
}});

function loadChildDropdown() {{
    var parentValue = $('#ParentDropdown').val();
    
    $.ajax({{
        url: "<?php echo $form2; ?>",
        type: "POST",
        data: {{ Action: 'GetChildData', ParentCode: parentValue }},
        dataType: "json",
        success: function(msg) {{
            var $child = $('#ChildDropdown');
            $child.empty();
            $child.append('<option value="-1">SELECT</option>');
            
            for (var i = 0; i < msg.length; i++) {{
                $child.append('<option value="' + msg[i][1] + '">' + msg[i][2] + '</option>');
            }}
            
            $child.change();
        }}
    }});
}}
```

âš ï¸ C-13 VALIDATION: Your code will be scanned for:
- HTML: data-plugin="select2" on dropdown fields
- Initialization: $('.select2-field').select2({{...}})
- Event handlers: .on("select2:close", ...) for EACH dropdown
- Focus handlers: .focus(function() {{ ... .select2('open'); }})

Missing Select2 handlers = Keyboard navigation won't work!

ðŸ”´ðŸ”´ðŸ”´ END C-13 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE C - FIX C-14: $_POST VS $_REQUEST CONSISTENCY ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - USE $_REQUEST FOR ALL FORM DATA ACCESS âš ï¸âš ï¸âš ï¸

Company uses $_REQUEST consistently throughout their codebase.
$_REQUEST combines $_GET, $_POST, and $_COOKIE for maximum flexibility.

âœ… REQUIRED PATTERN:

**WHY $_REQUEST?**
- Handles both GET and POST requests (form submission + URL parameters)
- Supports AJAX calls (which may use GET or POST)
- Allows URL parameters for edit/update mode (?action=Update&major=CODE)
- Company standard - all existing code uses $_REQUEST

**USAGE RULES:**

1. **Form Field Access** (ALWAYS use $_REQUEST):
```php
// âœ… CORRECT - Use $_REQUEST
$columns['FieldName'] = $_REQUEST['FieldName'];
$columns['Description'] = $_REQUEST['Description'];
$columns['Code'] = $_REQUEST['Code'];

// âŒ WRONG - Don't use $_POST
$columns['FieldName'] = $_POST['FieldName'];  // Will break on GET requests
```

2. **Action/Mode Detection** (ALWAYS use $_REQUEST):
```php
// âœ… CORRECT - Use $_REQUEST
if(isset($_REQUEST['action']) && $_REQUEST['action'] == 'Delete') {{
    // Delete logic
}}

if(isset($_REQUEST['txtmode']) && $_REQUEST['txtmode'] == 'save') {{
    // Save logic
}}

// âŒ WRONG - Don't use $_POST
if(isset($_POST['action'])) {{  // Will break on GET requests
    // ...
}}
```

3. **AJAX Handler Parameters** (ALWAYS use $_REQUEST):
```php
// âœ… CORRECT - Use $_REQUEST
if(isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {{
    $SelectArea = $_REQUEST['SelectArea'];
    // AJAX logic
}}

// âŒ WRONG - Don't use $_POST
if(isset($_POST['Action'])) {{  // AJAX may use GET
    // ...
}}
```

4. **Update Mode Data Loading** (ALWAYS use $_REQUEST):
```php
// âœ… CORRECT - Use $_REQUEST
if(isset($_REQUEST['major'])) {{
    $Code = $_REQUEST['major'];
    $obj = db_getRecord($table, "Code='$Code' AND Comp_Code='".$_SESSION['comp_code']."'");
}}

// âŒ WRONG - Don't use $_GET
if(isset($_GET['major'])) {{  // Inconsistent with company pattern
    // ...
}}
```

5. **Hidden Field Values** (ALWAYS use $_REQUEST):
```php
// âœ… CORRECT - Use $_REQUEST
if($_REQUEST['CTRL_HID_VALUE'] != 'Update') {{
    // New record logic
}} else {{
    // Update record logic
}}

// âŒ WRONG - Don't use $_POST
if($_POST['CTRL_HID_VALUE'] != 'Update') {{  // Inconsistent
    // ...
}}
```

**CONSISTENCY RULES:**
1. Use $_REQUEST for ALL form data access (100% consistency)
2. Use $_SESSION for session data (user_id, comp_code, login_id)
3. Use $_FILES for file uploads (if needed)
4. NEVER mix $_POST and $_REQUEST in the same file
5. NEVER use $_GET for form data

**SECURITY NOTE:**
Company uses `add()` and `add_Slashes_new()` functions for SQL injection protection:
```php
// âœ… CORRECT - Use add() for SQL safety
$filter = "Code='".add($_REQUEST['Code'])."' AND Comp_Code='".$_SESSION['comp_code']."'";

// âœ… CORRECT - Use add_Slashes_new() for strings with quotes
$columns['Description'] = add_Slashes_new($_REQUEST['Description']);
```

âš ï¸ C-14 VALIDATION: Your code will be scanned for:
- $_REQUEST usage: MUST be present for all form data access
- $_POST usage: MUST NOT be present (inconsistent with company pattern)
- Consistency: ALL form data access uses $_REQUEST

Using $_POST instead of $_REQUEST = VALIDATION FAILURE!

ðŸ”´ðŸ”´ðŸ”´ END C-14 FIX ðŸ”´ðŸ”´ðŸ”´

ðŸ”´ðŸ”´ðŸ”´ STEP 4 PHASE C - FIX C-15: HTML STRUCTURE RETRIEVAL ðŸ”´ðŸ”´ðŸ”´

âš ï¸âš ï¸âš ï¸ CRITICAL - MAINTAIN COMPLETE HTML STRUCTURE âš ï¸âš ï¸âš ï¸

Company HTML structure follows a specific pattern that MUST be maintained.
Every section is required for proper rendering and functionality.

âœ… REQUIRED HTML STRUCTURE:

**COMPLETE HTML DOCUMENT STRUCTURE:**

```html
<!DOCTYPE html>
<html class="no-js css-menubar" lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=0, minimal-ui">
  <meta name="description" content="Company ERP System">
  <meta name="author" content="">
  
  <title><?php echo $title; ?> - Company ERP</title>
  
  <!-- Stylesheets (15+ CSS files) -->
  <link rel="stylesheet" href="global/vendor/bootstrap/bootstrap.min.css">
  <link rel="stylesheet" href="global/vendor/animsition/animsition.min.css">
  <!-- ... (all other CSS files) ... -->
  <link rel="stylesheet" href="assets/css/site.min.css">
  
  <!-- Core JavaScript -->
  <script src="global/vendor/breakpoints/breakpoints.js"></script>
  <script src="assets/js/State.js"></script>
  <!-- ... (core JS files) ... -->
</head>

<body class="animsition site-navbar-small" onLoad="initializeForm();">
  
  <!-- Top Menu -->
  <?php include("include/topmenu.php"); ?>
  
  <!-- Side Menu -->
  <?php include("include/sidemenu.php"); ?>
  
  <!-- Page Content -->
  <div class="page">
    
    <!-- Form Header -->
    <?php include("include/formheader.php"); ?>
    
    <!-- Main Content -->
    <div class="page-content padding-30">
      <div class="panel">
        <div class="panel-body container-fluid">
          <div class="row row-lg">
            <div class="col-sm-12 col-md-12">
              
              <!-- FORM SECTION -->
              <form class="form-horizontal" id="frm" name="frm" method="POST" action="<?php echo $form2; ?>">
                
                <!-- Form Fields -->
                <div class="form-group">
                  <label class="col-md-4 control-label">Field Label <span class="text-danger">*</span>:</label>
                  <div class="col-md-4">
                    <input type="text" class="form-control" name="FieldName" id="FieldName" 
                           value="<?php echo stripslashes($obj['FieldName']); ?>" 
                           onKeyDown="checkKeycode(event,this.id);" />
                  </div>
                </div>
                
                <!-- ... (all other fields) ... -->
                
                <!-- Buttons -->
                <div class="form-group">
                  <div class="col-md-12" align="center">
                    <button type="button" name="btnSave" id="btnSave" class="btn btn-primary" 
                            accesskey="s" onclick="btnsave_click()">
                      <i class="icon wb-check" aria-hidden="true"></i> Save
                    </button>
                    <button type="button" class="btn btn-success" onClick="window.location='<?php echo $form; ?>'">
                      <i class="icon wb-arrow-left" aria-hidden="true"></i> Back
                    </button>
                  </div>
                </div>
                
                <!-- Hidden Fields -->
                <input type="hidden" id="txtmode" name="txtmode" value="new">
                <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action']; ?>">
                
              </form>
              
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
  
  <!-- Footer -->
  <?php include("include/footer.php"); ?>
  
  <!-- JavaScript Section -->
  <script>
  // All JavaScript functions here
  // - checkKeycode()
  // - maxid()
  // - btnsave_click()
  // - FormValidation
  // - Select2 handlers
  </script>
  
  <!-- Footer Scripts (30+ script tags) -->
  <script src="global/vendor/jquery/jquery.js"></script>
  <script src="global/vendor/bootstrap/bootstrap.js"></script>
  <!-- ... (all 30+ footer scripts) ... -->
  <script src="global/js/funJs.js"></script>
  
</body>
</html>
```

**CRITICAL HTML STRUCTURE RULES:**

1. **DOCTYPE and HTML Tag** (REQUIRED):
```html
<!DOCTYPE html>
<html class="no-js css-menubar" lang="en">
```

2. **Meta Tags** (REQUIRED - 5 meta tags minimum):
```html
<meta charset="utf-8">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=0, minimal-ui">
<meta name="description" content="...">
<meta name="author" content="">
```

3. **Title Tag** (REQUIRED):
```html
<title><?php echo $title; ?> - Company ERP</title>
```

4. **CSS Links** (REQUIRED - 15+ links):
- Bootstrap, Animsition, FormValidation, Select2, Font Awesome, etc.
- MUST be in <head> section
- MUST use company vendor paths

5. **Body Tag** (REQUIRED with classes and onLoad):
```html
<body class="animsition site-navbar-small" onLoad="initializeForm();">
```

6. **PHP Includes** (REQUIRED - 4 includes):
```php
<?php include("include/topmenu.php"); ?>
<?php include("include/sidemenu.php"); ?>
<?php include("include/formheader.php"); ?>
<?php include("include/footer.php"); ?>
```

7. **Page Structure** (REQUIRED - nested divs):
```html
<div class="page">
  <div class="page-content padding-30">
    <div class="panel">
      <div class="panel-body container-fluid">
        <div class="row row-lg">
          <div class="col-sm-12 col-md-12">
            <!-- Form here -->
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

8. **Form Tag** (REQUIRED with classes):
```html
<form class="form-horizontal" id="frm" name="frm" method="POST" action="<?php echo $form2; ?>">
```

9. **Form Fields** (REQUIRED structure for EACH field):
```html
<div class="form-group">
  <label class="col-md-4 control-label">Label <span class="text-danger">*</span>:</label>
  <div class="col-md-4">
    <input type="text" class="form-control" name="Field" id="Field" 
           value="<?php echo stripslashes($obj['Field']); ?>" 
           onKeyDown="checkKeycode(event,this.id);" />
  </div>
</div>
```

10. **Buttons Section** (REQUIRED):
```html
<div class="form-group">
  <div class="col-md-12" align="center">
    <button type="button" name="btnSave" id="btnSave" class="btn btn-primary" 
            accesskey="s" onclick="btnsave_click()">Save</button>
    <button type="button" class="btn btn-success" onClick="window.location='<?=$form;?>'">Back</button>
  </div>
</div>
```

11. **Hidden Fields** (REQUIRED - 2 minimum):
```html
<input type="hidden" id="txtmode" name="txtmode" value="new">
<input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action']; ?>">
```

12. **JavaScript Section** (REQUIRED - in <script> tag):
- Must include ALL functions (checkKeycode, maxid, btnsave_click, FormValidation, etc.)
- Must be BEFORE footer scripts

13. **Footer Scripts** (REQUIRED - 30+ script tags):
- Must be AFTER JavaScript section
- Must be BEFORE </body>

**RETRIEVAL PATTERN:**

When generating HTML, follow this order:
1. Start with DOCTYPE and <html>
2. Build complete <head> with ALL CSS links
3. Open <body> with classes and onLoad
4. Include topmenu.php and sidemenu.php
5. Build page structure (page â†’ page-content â†’ panel â†’ panel-body â†’ row â†’ col)
6. Include formheader.php
7. Build complete <form> with ALL fields
8. Add buttons and hidden fields
9. Close form and page structure
10. Include footer.php
11. Add JavaScript section with ALL functions
12. Add ALL 30+ footer scripts
13. Close </body> and </html>

âš ï¸ C-15 VALIDATION: Your code will be scanned for:
- Complete HTML structure: DOCTYPE, html, head, body tags
- Meta tags: Minimum 5 meta tags
- CSS links: Minimum 15 <link> tags
- PHP includes: All 4 includes (topmenu, sidemenu, formheader, footer)
- Page structure: Proper nesting of divs
- Form structure: form-horizontal class, proper field structure
- Hidden fields: txtmode and CTRL_HID_VALUE
- JavaScript section: Present with functions
- Footer scripts: 30+ script tags

Missing ANY structural element = VALIDATION FAILURE!

ðŸ”´ðŸ”´ðŸ”´ END C-15 FIX ðŸ”´ðŸ”´ðŸ”´

=== OUTPUT REQUIREMENTS ===

ðŸ”´ CRITICAL: Generate a COMPLETE, PRODUCTION-READY PHP file (15,000-20,000 characters minimum)

Your generated file MUST include ALL of these sections in this EXACT order:

1. **PHP SESSION & INCLUDES** (Lines 1-30):
   - @session_start();
   - include("include/config.inc.php"); â† MANDATORY - this pulls in DB connection, session, all helper functions
   - $form, $form2, $title variables
   - $table variable
   - âš ï¸ DO NOT use require_once('includes/db.php') - use company's include("include/config.inc.php")

2. **PHP AJAX HANDLERS** (Lines 31-100):
   - ðŸ”´ MANDATORY: function maxid() {{ $.post(form2, {{Action:'GetMaxID', {parent_db_field}: parentValue}}, function(data){{ $('#{primary_key}').val(data); }}); }}
   - if($_REQUEST['Action']=='GetMaxID') {{ ... exit; }}
   - ðŸ”´ MANDATORY: if($_REQUEST['action']=='Delete') {{
       // Pre-delete dependency check
       $getrows2 = getrows2("SELECT * FROM invoice WHERE Customer_Master='$Code'");
       if($getrows2 > 0) {{ echo "<script>alert('This Customer Exist in invoice... !!!');</script>"; exit; }}
       // Delete record
       db_delete("DELETE FROM tblcustomer WHERE CUST_CODE='$Code'");
       fun_log('D', 'tblcustomer', $Code, $table);
       echo "<script>alert('Record Deleted Successfully'); window.location='$form2';</script>";
       exit;
   }}
   - Any other AJAX handlers (GetCOSTCENTER, cascading dropdowns)

3. **PHP CRUD OPERATIONS** (Lines 101-250):
   - if($_REQUEST['action']=='Save') {{ ... }}
   - Complete INSERT logic with db_insert()
   - Complete UPDATE logic with db_update()
   - Complete validation and error handling
   - fun_log() for audit trail

4. **PHP DATA LOADING** (Lines 251-300):
   - if(isset($_REQUEST['major'])) {{ ... }}
   - Load existing record using db_getRecord()
   - Populate variables for form fields

5. **HTML DOCTYPE & HEAD** (Lines 301-400):
   - <!DOCTYPE html>
   - <html>, <head> tags
   - <title> tag
   - âš ï¸ REQUIRED: Include ALL these CSS/JS vendor files (Do NOT skip):
     * <link href="assets/css/bootstrap.min.css" rel="stylesheet">
     * <link href="assets/css/font-awesome.min.css" rel="stylesheet">
     * <link href="assets/css/animsition.min.css" rel="stylesheet">
     * <link href="assets/css/formValidation.min.css" rel="stylesheet">
     * <link href="assets/css/site.min.css" rel="stylesheet">
     * <script src="assets/js/jquery.min.js"></script>
     * <script src="assets/js/bootstrap.min.js"></script>
     * <script src="assets/js/formValidation.min.js"></script>
     * <script src="assets/js/bootstrap.validator.min.js"></script>
     * <script src="assets/js/animsition.min.js"></script>
   - Meta tags (charset, viewport)
   - ALL CSS <link> tags (bootstrap, font-awesome, formvalidation, etc.)
   - Meta tags

6. **HTML BODY START** (Lines 401-450):
   - <body onLoad="maxid();"> tag
   - âš ï¸ REQUIRED: Include these PHP files (Do NOT skip):
     * <?php include("include/topmenu.php"); ?>
     * <?php include("include/sidemenu.php"); ?>
     * <?php include("include/formheader.php"); ?>
   - <div class="container-fluid">
   - Page header with title

7. **HTML FORM** (Lines 451-850):
   - <form id="frm" name="frm" class="form-horizontal" method="post">
   - ALL form fields with proper structure:
     * <div class="form-group">
     * <label class="col-md-4">
     * <div class="col-md-2"> or <div class="col-md-4">
     * <input class="form-control">
   - Hidden fields (txtmode, CTRL_HID_VALUE, etc.)
   - Buttons (Save, Back, etc.)
   - </form>

8. **HTML INCLUDES & CLOSING** (Lines 851-900):
   - âš ï¸ REQUIRED: Include footer (Do NOT skip):
     * <?php include("include/footer.php"); ?>
   - </div> closing tags for container-fluid
   - </body>

9. **JAVASCRIPT SECTION** (Lines 901-1300):
   - <script> tag
   - âš ï¸ REQUIRED: Include ALL these functions (Do NOT skip):
     * function maxid() {{ $.post(...); }}
     * function btnsave_click() {{ ... }}
     * function checkKeycode(e, field) {{ ... }}
     * $('#frm').formValidation({{ ... }}) with ALL field validators
     * $(document).ready(function() {{ ... }})
   - </script>

ðŸ”´ðŸ”´ðŸ”´ CRITICAL WARNING - FOOTER SCRIPTS SECTION ðŸ”´ðŸ”´ðŸ”´

Research Finding: LLMs skip footer scripts thinking they are "boilerplate"
This causes a 7,773 character gap (Company: 17,785 chars vs Generated: 10,012 chars)

The missing section is: 30+ vendor script tags (~4,500 characters)

YOU MUST READ THIS CAREFULLY:
- Company files have 30+ <script src="..."> tags at the end
- These are NOT optional or boilerplate
- They are REQUIRED for FormValidation, keyboard navigation, Bootstrap UI, menu/sidebar
- If you skip them, the form will NOT work
- This is the #1 reason for validation failures

10. **FOOTER SCRIPTS** (Lines 1301-1450):
    âš ï¸âš ï¸âš ï¸ CRITICAL - COPY ALL FOOTER SCRIPTS EXACTLY âš ï¸âš ï¸âš ï¸
    
    LLMs tend to skip these thinking they are "boilerplate" - THEY ARE NOT!
    These scripts are REQUIRED for the form to work properly.
    
    YOU MUST INCLUDE ALL OF THESE SCRIPT TAGS (Do NOT skip even ONE):
    
    ```html
    <!-- MANDATORY FOOTER SCRIPTS - DO NOT SKIP ANY -->
    <script src="global/vendor/jquery/jquery.js"></script>
    <script src="global/vendor/bootstrap/bootstrap.js"></script>
    <script src="global/vendor/animsition/animsition.js"></script>
    <script src="global/vendor/asscroll/jquery-asScroll.js"></script>
    <script src="global/vendor/mousewheel/jquery.mousewheel.js"></script>
    <script src="global/vendor/asscrollable/jquery.asScrollable.all.js"></script>
    <script src="global/vendor/ashoverscroll/jquery-asHoverScroll.js"></script>
    <script src="global/vendor/jquery-mmenu/jquery.mmenu.min.all.js"></script>
    <script src="global/vendor/switchery/switchery.min.js"></script>
    <script src="global/vendor/intro-js/intro.js"></script>
    <script src="global/vendor/screenfull/screenfull.js"></script>
    <script src="global/vendor/slidepanel/jquery-slidePanel.js"></script>
    <script src="global/vendor/blueimp-tmpl/tmpl.js"></script>
    <script src="global/vendor/blueimp-canvas-to-blob/canvas-to-blob.js"></script>
    <script src="global/vendor/blueimp-load-image/load-image.all.min.js"></script>
    <script src="global/vendor/dropify/dropify.min.js"></script>
    <script src="global/vendor/formvalidation/formValidation.min.js"></script>
    <script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
    <script src="global/js/core.js"></script>
    <script src="assets/js/site.js"></script>
    <script src="assets/js/sections/menu.js"></script>
    <script src="assets/js/sections/menubar.js"></script>
    <script src="assets/js/sections/gridmenu.js"></script>
    <script src="assets/js/sections/sidebar.js"></script>
    <script src="global/js/configs/config-colors.js"></script>
    <script src="assets/js/configs/config-tour.js"></script>
    <script src="global/js/components/asscrollable.js"></script>
    <script src="global/js/components/animsition.js"></script>
    <script src="global/js/components/slidepanel.js"></script>
    <script src="global/js/components/switchery.js"></script>
    <script src="global/js/components/dropify.js"></script>
    <script src='global/js/funJs.js'></script>
    <!-- END MANDATORY FOOTER SCRIPTS -->
    ```
    
    âš ï¸ THESE SCRIPTS ARE REQUIRED FOR:
    - FormValidation to work properly
    - Keyboard navigation to function
    - Bootstrap UI components to render
    - Menu/sidebar to work
    - Animations and transitions
    - File uploads (dropify)
    - Custom company functions (funJs.js)
    
    âš ï¸ IF YOU SKIP EVEN ONE SCRIPT TAG, THE FORM WILL NOT WORK!
    âš ï¸ Company files have ~4,500 characters of footer scripts
    âš ï¸ Your output MUST include ALL 30+ script tags shown above

11. **HTML CLOSING** (Lines 1451-1460):
    - </body>
    - </html>

âš ï¸ DO NOT SKIP ANY SECTION!
âš ï¸ DO NOT WRITE "// Add more fields here" - WRITE ACTUAL CODE!
âš ï¸ DO NOT TRUNCATE - Generate the FULL file!
âš ï¸ ESPECIALLY DO NOT SKIP THE FOOTER SCRIPTS - They are NOT optional!

MINIMUM FILE SIZE: 16,000 characters (company files are 17,785 chars)
If your output is less than 16,000 characters, you have FAILED!
The 7,773 character gap is mostly from missing footer scripts!

OUTPUT FORMAT:
- NO markdown code blocks (no ```)
- NO explanations or comments outside the code
- JUST the raw PHP code starting with <?php
- The file should be ready to save as "{canonical_file_name}" and run immediately
- ALL HTML, CSS, and JavaScript must be INLINE within the PHP file
"""
        
        # âœ… FIX: Calculate company example size and build dynamic system instruction
        # Use FULL file size from disk (not trimmed example) for accurate size targets
        company_example_size = len(company_examples) if company_examples else 50000
        
        # If we have the full file on disk, use its actual size for targets
        if self._template and self._template.codebase_dir:
            import glob
            entity_name = naming_metadata.get('feature_name') or intent.get('database', {}).get('table_name', '').replace('tbl', '').replace('_master', '').title()
            if entity_name:
                patterns = [
                    os.path.join(self._template.codebase_dir, '**', f'frm{entity_name}.php'),
                    os.path.join(self._template.codebase_dir, '**', f'frm{entity_name}*.php'),
                ]
                for pattern in patterns:
                    matches = glob.glob(pattern, recursive=True)
                    if matches:
                        full_file_size = os.path.getsize(matches[0])
                        if full_file_size > company_example_size:
                            company_example_size = full_file_size
                            logger.info(f"ðŸ“Š Using full file size for targets: {full_file_size:,} chars ({full_file_size/1024:.1f} KB)")
                        break
        
        system_instruction = self._build_system_instruction(company_example_size)
        
        # âœ… ISSUE #14 FIX: Prepend system instruction for complete code generation
        # âœ… ISSUE #15 FIX: Add structure completeness checklist (from research)
        # This ensures LLM includes ALL mandatory sections found in company examples
        structure_checklist = self._build_structure_checklist(company_examples)
        
        prompt = system_instruction + "\n\n" + structure_checklist + "\n\n" + prompt
        
        return prompt
    
    def _extract_php_code(self, content: str) -> str:
        """
        Extract PHP code from LLM response
        
        âœ… ISSUE #14 FIX: Better extraction to avoid truncation
        - Handles multiple code block formats
        - Preserves complete file content
        - Logs extraction method for debugging
        """
        
        original_length = len(content)
        logger.info(f"ðŸ“ Extracting PHP code from LLM response ({original_length} chars)")
        if original_length < 300:
            preview = content.replace('\n', ' ')[:250]
            logger.warning(f"âš ï¸ Very short LLM response preview: {preview}")
        
        # Try to extract from code block with php language specifier
        php_match = re.search(r'```php\n(.*?)```', content, re.DOTALL)
        if php_match:
            extracted = php_match.group(1).strip()
            logger.info(f"âœ… Extracted from ```php block: {len(extracted)} chars")
            return extracted
        
        # Try without language specifier
        code_match = re.search(r'```\n(.*?)```', content, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
            if code.startswith('<?php'):
                logger.info(f"âœ… Extracted from ``` block: {len(code)} chars")
                return code
        
        # If no code block, check if content starts with <?php
        if content.strip().startswith('<?php'):
            logger.info(f"âœ… No code block found, using raw content: {len(content.strip())} chars")
            return content.strip()
        
        # âœ… ISSUE #14 FIX: Try to find <?php anywhere in content
        # Sometimes LLM adds explanation before code
        php_start = content.find('<?php')
        if php_start != -1:
            extracted = content[php_start:].strip()
            logger.info(f"âœ… Found <?php at position {php_start}, extracted: {len(extracted)} chars")
            return extracted
        
        # Last resort: return as-is and log warning
        logger.warning(f"âš ï¸ Could not find PHP code markers, returning raw content: {len(content)} chars")
        return content.strip()

    def _is_refusal_response(self, content: str) -> bool:
        """Detect common model refusal responses."""
        text = (content or '').strip().lower()
        if not text:
            return False

        refusal_signals = [
            "i'm sorry, but i can't assist with that",
            "i cannot assist with that",
            "i can't help with that",
            "i cannot help with that request",
            "unable to comply with this request",
            "cannot fulfill this request",
            "i can't provide that",
            "i cannot provide that",
            "i'm sorry, i can't help with that",
            "i’m sorry, but i can’t assist with that"
        ]
        return any(signal in text for signal in refusal_signals)

    def _extract_template_candidate_code(self, source_text: str) -> str:
        """
        Extract runnable PHP code from company example text (full file or markdown-wrapped snippet).
        """
        if not source_text:
            return ""

        text = source_text.strip()
        if text.startswith('<?php'):
            return text

        php_block_match = re.search(r'```php\s*(.*?)```', text, re.DOTALL | re.IGNORECASE)
        if php_block_match:
            candidate = php_block_match.group(1).strip()
            if candidate.startswith('<?php'):
                return candidate

        php_start = text.find('<?php')
        if php_start != -1:
            return text[php_start:].strip()

        return ""


    def get_database_connection_code(self, database_type: str, database_details: Dict = None) -> str:
        """
        Generate database connection code for the selected database type
        
        Args:
            database_type: Type of database (mysql, postgresql, sqlite, mssql)
            database_details: Optional database connection details
            
        Returns:
            PHP code for database connection
        """
        from agents.prompts.database_connection_prompts import get_php_database_connection_code
        
        if database_details:
            connection_code = get_php_database_connection_code(
                db_type=database_type,
                host=database_details.get('host', 'localhost'),
                port=database_details.get('port', 3306),
                database=database_details.get('database', 'mydb'),
                username=database_details.get('username', 'root')
            )
        else:
            # Generate generic connection code
            connection_code = get_php_database_connection_code(
                db_type=database_type,
                host='localhost',
                port=3306 if database_type == 'mysql' else (5432 if database_type == 'postgresql' else 1433),
                database='mydb',
                username='root'
            )
        
        return connection_code

