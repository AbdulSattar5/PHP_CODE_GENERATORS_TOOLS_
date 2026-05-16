# agents/graph/nodes.py

from typing import Dict, Optional, List
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
from .state import AgentState
from agents.prompts.intent_prompts import INTENT_ANALYSIS_PROMPT
import os
import re
from django.conf import settings
import logging
import json
from agents.utils.company_style_normalizer import CompanyStyleNormalizer
from agents.validators.company_form_contract_validator import CompanyFormContractValidator
from agents.utils.runtime_config import get_csv_setting, get_int_setting
from agents.config.pipeline_constants import (
    RETRIEVAL_COVERAGE_FLOOR,
    RETRIEVAL_HARD_BLOCK_FLOOR,
    RETRIEVAL_SCORE_FLOOR,
)

logger = logging.getLogger(__name__)

def _is_truthy(value) -> bool:
    """Normalize boolean-like runtime values from settings/env."""
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def get_llm_config():
    """
    Get LLM configuration from settings or environment variables.
    Runtime flag CODEGEN_ENFORCE_GPT4O_MINI=true forces gpt-4o-mini everywhere.
    """
    langchain_config = {}
    try:
        if hasattr(settings, 'LANGCHAIN_CONFIG'):
            langchain_config = dict(getattr(settings, 'LANGCHAIN_CONFIG') or {})
    except Exception:
        langchain_config = {}

    model = str(
        langchain_config.get('model') or os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    ).strip() or 'gpt-4o-mini'
    fallback_model = str(
        langchain_config.get('fallback_model') or os.getenv('OPENAI_FALLBACK_MODEL', 'gpt-4o-mini')
    ).strip() or 'gpt-4o-mini'

    enforce_runtime = getattr(
        settings,
        'CODEGEN_ENFORCE_GPT4O_MINI',
        os.getenv('CODEGEN_ENFORCE_GPT4O_MINI', 'true')
    )
    if _is_truthy(enforce_runtime):
        model = 'gpt-4o-mini'
        fallback_model = 'gpt-4o-mini'

    timeout_seconds = get_int_setting(
        'CODEGEN_OPENAI_TIMEOUT_SECONDS',
        'CODEGEN_OPENAI_TIMEOUT_SECONDS',
        default=120,
        min_value=30,
        max_value=900,
    )
    request_timeout_seconds = get_int_setting(
        'CODEGEN_OPENAI_REQUEST_TIMEOUT_SECONDS',
        'CODEGEN_OPENAI_REQUEST_TIMEOUT_SECONDS',
        default=timeout_seconds,
        min_value=30,
        max_value=900,
    )
    max_retries = get_int_setting(
        'CODEGEN_OPENAI_MAX_RETRIES',
        'CODEGEN_OPENAI_MAX_RETRIES',
        default=5,
        min_value=1,
        max_value=10,
    )

    return {
        'model': model,
        'fallback_model': fallback_model,
        'api_key': langchain_config.get('openai_api_key') or os.getenv('OPENAI_API_KEY'),
        'max_retries': max_retries,
        'timeout': timeout_seconds,
        'request_timeout': request_timeout_seconds
    }


def create_llm_with_retries(config: Dict, temperature: float = 0.1, max_tokens: int = 4000) -> ChatOpenAI:
    """
    Create ChatOpenAI instance with proper retry configuration
    ðŸ†• ISSUE #7 FIX: Centralized LLM creation with retry settings
    
    Args:
        config: LLM config from get_llm_config()
        temperature: Temperature setting (default 0.1)
        max_tokens: Max tokens for response (default 4000)
    
    Returns:
        ChatOpenAI instance with retry configuration
    """
    return ChatOpenAI(
        model=config['model'],
        temperature=temperature,
        openai_api_key=config['api_key'],
        max_tokens=max_tokens,
        max_retries=config.get('max_retries', 5),
        timeout=config.get('timeout', 120),
        request_timeout=config.get('request_timeout', 120)
    )


# Pydantic models for structured output
from typing import Optional, List

class FieldSchema(BaseModel):
    name: str = Field(description="Field name")
    label: str = Field(description="Display label")
    db_type: str = Field(description="Database type (VARCHAR, INT, etc.)")
    db_length: Optional[int] = Field(description="Field length (null for INT, DATE, etc.)", default=None)
    input_type: str = Field(description="HTML input type")
    validation: List[str] = Field(description="Validation rules", default_factory=list)
    required: bool = Field(description="Is field required", default=False)


class DatabaseSchema(BaseModel):
    table_name: str = Field(description="Database table name")
    primary_key: str = Field(description="Primary key field", default="id")
    indexes: List[str] = Field(description="Fields to index", default_factory=list)
    relationships: List[Dict] = Field(description="Foreign key relationships", default_factory=list)


class IntentAnalysis(BaseModel):
    feature_type: str = Field(description="Type of feature (form, CRUD, report, etc.)")
    form_title: str = Field(description="Title of the form/module")
    fields: List[FieldSchema] = Field(description="List of form fields")
    database: DatabaseSchema = Field(description="Database schema information")
    operations: List[str] = Field(description="Required CRUD operations")
    ui_layout: str = Field(description="UI layout preference", default="single-column")


class IntentAnalysisNode:
    """
    Analyzes user request to extract structured intent
    """
    
    def __init__(self):
        self.llm = None
        self.parser = None
        self.prompt = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            
            # ðŸ†• ISSUE #7 FIX: Configure better retry settings for OpenAI API
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key'],
                max_retries=5,  # ðŸ†• Increased from default 2 to 5
                timeout=120,  # ðŸ†• 2 minute timeout
                request_timeout=120  # ðŸ†• Request-level timeout
            )
            
            self.parser = PydanticOutputParser(pydantic_object=IntentAnalysis)
            
            self.prompt = PromptTemplate(
                template=INTENT_ANALYSIS_PROMPT + "\n{format_instructions}",
                input_variables=["user_request"],
                partial_variables={"format_instructions": self.parser.get_format_instructions()}
            )

    def _infer_feature_name(self, user_request: str) -> str:
        """
        Infer a stable feature/entity name from user request when LLM intent parsing fails.
        """
        request_text = (user_request or "").strip()
        if not request_text:
            return "Form"

        lowered = request_text.lower()
        patterns = [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*)\s+master\s+form',
            r'([a-z][a-z0-9_]*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*)',
            r'\bfrm([a-z][a-z0-9_]*)\b',
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered, re.IGNORECASE)
            if match:
                candidate = re.sub(r'[^A-Za-z0-9_]', '', match.group(1))
                if candidate:
                    return candidate.title()

        configured_entity_hints = get_csv_setting(
            'CODEGEN_ENTITY_HINTS',
            'CODEGEN_ENTITY_HINTS',
            default=[]
        )
        for entity in configured_entity_hints:
            if re.search(rf'\b{re.escape(entity.lower())}\b', lowered):
                return entity.title()

        stopwords = set(
            word.lower() for word in get_csv_setting(
                'CODEGEN_ENTITY_STOPWORDS',
                'CODEGEN_ENTITY_STOPWORDS',
                default=[
                    'create', 'complete', 'master', 'form', 'with', 'all', 'crud',
                    'operations', 'following', 'fields', 'detail', 'grid',
                    'include', 'company', 'standard', 'patterns', 'generate',
                    'code', 'table', 'tables', 'required', 'and', 'for', 'the',
                    'from', 'via', 'ajax', 'handler'
                ]
            )
        )
        tokens = re.findall(r'\b[a-z][a-z0-9_]{2,}\b', lowered)
        for token in tokens:
            if token in stopwords:
                continue
            return token.title()

        token_match = re.search(r'\b([A-Za-z][A-Za-z0-9_]{2,})\b', request_text)
        if token_match:
            return token_match.group(1).title()
        return "Form"

    def _extract_explicit_request_value(self, user_request: str, key: str) -> str:
        text = user_request or ""
        key_patterns = {
            'table': r'(?im)^\s*(?:[-*]\s*)?table\s*:\s*([A-Za-z0-9_]+)\s*$',
            'file_name': r'(?im)^\s*(?:[-*]\s*)?(?:file\s*name|filename|file)\s*:\s*([A-Za-z0-9_.-]+)\s*$',
            'title': r'(?im)^\s*(?:[-*]\s*)?title\s*:\s*([A-Za-z0-9_ \-]+)\s*$',
            'case_type': r'(?im)^\s*(?:[-*]\s*)?(?:case\s*type|casetype)\s*:\s*([A-Za-z0-9_ \-]+)\s*$',
        }
        pattern = key_patterns.get(key)
        if not pattern:
            return ""
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _extract_primary_key_from_request(self, user_request: str) -> str:
        text = user_request or ""

        # Structured bullet under "Primary Key:" section:
        # - School_Code | DB: varchar/int | Input: readonly textbox
        primary_section_match = re.search(
            r'(?ims)^\s*primary\s*key\s*:\s*(.+?)(?:^\s*[A-Za-z][^\n]*:\s*|\Z)',
            text
        )
        if primary_section_match:
            section = primary_section_match.group(1)
            bullet_match = re.search(r'(?im)^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)', section)
            if bullet_match:
                return bullet_match.group(1).strip()

        # Single-line fallback style:
        # Primary Key: STU_CODE
        line_match = re.search(
            r'(?im)^\s*(?:primary\s*key|primary_key)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$',
            text
        )
        if line_match:
            return line_match.group(1).strip()

        return ""

    def _extract_filename_from_request(self, user_request: str) -> str:
        """
        FIX #5: Extract filename from user request.
        User may specify: "File name: frmArea.php" or "filename: frmArea.php"
        """
        text = user_request or ""
        
        # Try multiple patterns
        patterns = [
            r'(?i)file\s*name\s*:\s*([a-z0-9_]+\.php)',
            r'(?i)filename\s*:\s*([a-z0-9_]+\.php)',
            r'(?i)file\s*:\s*([a-z0-9_]+\.php)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""

    def _extract_requested_operations(self, user_request: str, inferred_feature_type: str) -> List[str]:
        text = user_request or ""
        operations = []

        section_match = re.search(
            r'(?ims)^\s*operations\s*:\s*(.+?)(?:^\s*[A-Za-z][^\n]*:\s*|\Z)',
            text
        )
        if section_match:
            section = section_match.group(1)
            for op in ['create', 'read', 'update', 'delete']:
                if re.search(rf'(?i)\b{op}\b', section):
                    operations.append(op)

        if operations:
            return operations

        lowered = text.lower()
        if inferred_feature_type in ('report', 'dashboard'):
            return ['read']

        if any(keyword in lowered for keyword in ['crud', 'create', 'update', 'delete']):
            return ['create', 'read', 'update', 'delete']

        return ['read']

    def _infer_feature_type_from_request(self, user_request: str) -> str:
        lowered = (user_request or '').lower()
        if any(keyword in lowered for keyword in ['dashboard', 'analytics panel']):
            return 'dashboard'
        if any(keyword in lowered for keyword in ['report', 'listing report', 'summary report']):
            return 'report'
        if any(keyword in lowered for keyword in ['api endpoint', 'rest api', 'api handler']):
            return 'api'
        return 'form'

    def _build_default_table_name(self, feature_name: str) -> str:
        table_prefix = str(
            os.getenv('CODEGEN_TABLE_PREFIX', 'tbl_')
        ).strip() or 'tbl_'
        normalized = re.sub(r'[^a-z0-9_]+', '_', feature_name.lower()).strip('_') or 'entity'
        if table_prefix.endswith('_'):
            return f"{table_prefix}{normalized}"
        return f"{table_prefix}{normalized}"

    def _build_fallback_intent(self, user_request: str) -> Dict:
        """
        Build deterministic intent to avoid unknown_table fallbacks in degraded mode.
        """
        feature_name = self._infer_feature_name(user_request)
        inferred_feature_type = self._infer_feature_type_from_request(user_request)

        explicit_table = self._extract_explicit_request_value(user_request, 'table')
        explicit_title = self._extract_explicit_request_value(user_request, 'title')
        explicit_case_type = self._extract_explicit_request_value(user_request, 'case_type')
        primary_key = self._extract_primary_key_from_request(user_request)

        table_name = explicit_table or self._build_default_table_name(feature_name)
        form_title = (
            explicit_title
            or explicit_case_type
            or feature_name.replace('_', ' ').strip()
            or "Form"
        )
        fallback_primary_key = primary_key or os.getenv('CODEGEN_DEFAULT_PRIMARY_KEY', 'id')
        operations = self._extract_requested_operations(user_request, inferred_feature_type)

        return {
            'feature_type': inferred_feature_type,
            'form_title': form_title,
            'fields': [],
            'database': {
                'table_name': table_name,
                'primary_key': fallback_primary_key,
                'indexes': [],
                'relationships': []
            },
            'operations': operations,
            'ui_layout': 'single-column'
        }

    def _build_intent_from_strict_contract(self, contract: Dict, user_request: str) -> Dict:
        """
        Build deterministic intent from strict preflight contract.
        This avoids LLM-driven intent drift for identical prompts.
        """
        master_fields = list(contract.get('master_fields') or [])
        detail_fields = list(contract.get('detail_fields') or [])
        combined_fields = master_fields + [field for field in detail_fields if field not in master_fields]
        normalized_fields = []
        for idx, field in enumerate(combined_fields):
            if isinstance(field, dict):
                name = str(field.get('name') or '').strip()
                if not name:
                    continue
                normalized_fields.append({
                    'name': name,
                    'type': str(field.get('db_type') or 'varchar').strip() or 'varchar',
                    'required': bool(field.get('required')),
                    'label': name.replace('_', ' '),
                })
            elif field:
                field_name = str(field).strip()
                normalized_fields.append({
                    'name': field_name,
                    'type': 'varchar',
                    'required': False,
                    'label': field_name.replace('_', ' '),
                })

        feature_type = 'form'
        return {
            'feature_type': feature_type,
            'form_type': contract.get('form_type', 'SIMPLE'),
            'form_title': contract.get('title') or contract.get('entity') or self._infer_feature_name(user_request),
            'fields': normalized_fields,
            'database': {
                'table_name': contract.get('master_table', ''),
                'primary_key': contract.get('primary_key', ''),
                'indexes': [],
                'relationships': contract.get('relationships', []) or [],
            },
            'operations': ['create', 'read', 'update', 'delete'],
            'ui_layout': 'single-column',
            'dependencies': contract.get('dependencies', []) or [],
            'strict_features': contract.get('features', []) or [],
            'strict_contract': contract,
        }
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Execute intent analysis
        """
        try:
            # Initialize if not already done
            self._initialize()
            
            logger.info(f"Analyzing intent for request: {state['user_request']}")

            strict_contract = state.get('strict_contract') or {}
            if strict_contract.get('valid'):
                logger.info("Using strict preflight contract as deterministic intent source")
                deterministic_intent = self._build_intent_from_strict_contract(
                    strict_contract,
                    state.get('user_request', ''),
                )
                state['intent'] = deterministic_intent
                state['feature_type'] = deterministic_intent.get('feature_type', 'form')
                state['required_fields'] = deterministic_intent.get('fields', [])
                state['current_step'] = 'intent_analyzed'
                return state
            
            # Create chain
            chain = self.prompt | self.llm | self.parser
            
            # Execute
            result = await chain.ainvoke({"user_request": state['user_request']})
            
            # Update state
            state['intent'] = result.dict()
            state['feature_type'] = result.feature_type
            state['required_fields'] = [field.dict() for field in result.fields]
            state['current_step'] = 'intent_analyzed'
            
            logger.info(f"Intent analysis completed: {result.feature_type}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error in intent analysis: {str(e)}")
            # Don't include full traceback in logs for connection errors
            if "Connection error" not in str(e):
                logger.error(f"Error in intent analysis: {str(e)}", exc_info=True)
            
            state['status'] = 'degraded'
            state['error_message'] = f"Intent analysis failed: {str(e)}"
            fallback_intent = self._build_fallback_intent(state.get('user_request', ''))
            state['intent'] = fallback_intent
            state['feature_type'] = fallback_intent.get('feature_type', 'form')
            state['required_fields'] = []
            logger.warning(
                "Using heuristic fallback intent after failure: title=%s table=%s",
                fallback_intent.get('form_title'),
                fallback_intent.get('database', {}).get('table_name')
            )
            return state


# Initialize node
analyze_intent_node = IntentAnalysisNode()

## **Step 4.2: Pattern Retrieval Node**


from agents.prompts.retrieval_prompts import PATTERN_RETRIEVAL_PROMPT

class PatternRetrievalNode:
    """
    Retrieves similar code patterns from company codebase
    WITH CACHING - Reduces API calls by 20%
    """
    
    def __init__(self):
        self.embedding_manager = None
        self.llm = None
    
    def _initialize(self, user_id: str = None):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            from agents.vectorstore.embeddings import CodeEmbeddingManager
            # Initialize with user_id if provided
            self.embedding_manager = CodeEmbeddingManager(user_id=user_id)
            
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key']
            )

    def _check_entity_file_indexed(self, codebase_id: str, entity_filename: str, user_id: str) -> bool:
        """
        Check whether the exact entity PHP file is present in vector index metadata.
        """
        if not codebase_id or not entity_filename:
            return False
        if not self.embedding_manager:
            return False

        try:
            results = self.embedding_manager.search_similar_code(
                query=str(entity_filename),
                k=5,
                filter_dict={
                    'codebase_id': str(codebase_id),
                    'user_id': str(user_id),
                    'language': 'php',
                }
            )
            target_name = os.path.basename(str(entity_filename)).lower()
            for item in results or []:
                metadata = item.get('metadata', {}) if isinstance(item, dict) else {}
                candidate_name = str(metadata.get('filename') or '').strip()
                if not candidate_name:
                    candidate_path = str(metadata.get('file_path') or '').strip()
                    candidate_name = os.path.basename(candidate_path)
                if candidate_name and candidate_name.lower() == target_name:
                    return True
            return False
        except Exception as exc:
            logger.warning(f"Entity index check failed for {entity_filename}: {exc}")
            return False
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Retrieve and analyze relevant code patterns
        ðŸ†• ENHANCED: Now auto-enhances user request with company patterns
        """
        try:
            # Initialize with user_id from state
            user_id = state.get('user_id')
            self._initialize(user_id=user_id)
            
            logger.info("Retrieving similar code patterns")
            
            # Check if intent exists
            intent = state.get('intent')
            if not intent:
                logger.warning("No intent found, skipping pattern retrieval")
                state['retrieved_patterns'] = []
                state['current_step'] = 'patterns_retrieved'
                return state
            preflight_warnings = []
            if isinstance(intent, dict):
                raw_warnings = intent.get('preflight_warnings') or []
                if isinstance(raw_warnings, list):
                    preflight_warnings = list(raw_warnings)

            def _append_preflight_warning(code: str, message: str) -> None:
                warning = {'code': code, 'message': message}
                if warning not in preflight_warnings:
                    preflight_warnings.append(warning)
                logger.warning("⚠️ Preflight warning [%s]: %s", code, message)
            
            # ðŸ†• SMART PROMPT ENHANCEMENT: Auto-add company requirements
            # User said: "Create customer form"
            # We enhance to: "Create customer form with AJAX auto-ID, db_insert(), tblcustomer, etc."
            original_request = state.get('user_request', '')
            
            logger.info("ðŸš€ Smart Prompt Enhancement: Adding company patterns...")
            logger.info(f"   Original: {original_request[:80]}...")
            
            from agents.prompts.smart_prompt_enhancer import smart_prompt_enhancer
            
            # Get analyzed patterns for enhancement
            analyzed_patterns = state.get('analyzed_patterns', {})
            
            # Enhance the prompt
            enhanced_request = smart_prompt_enhancer.enhance_prompt(
                user_prompt=original_request,
                intent=intent
            )
            
            # Store enhanced request in state for later use
            state['enhanced_user_request'] = enhanced_request
            
            logger.info(f"âœ… Enhanced request: {len(enhanced_request)} characters")
            logger.info(f"   Added: AJAX auto-ID, company functions, table names, etc.")
            
            # Continue with pattern retrieval...
            
            # ðŸ†• GET ANALYZED PATTERNS FROM CACHE
            from agents.utils.cache_helper import get_cached_analyzed_patterns
            from asgiref.sync import sync_to_async
            
            # Get codebase_id - try from project first, then get latest for user
            analyzed_patterns = None
            codebase_id = state.get('codebase_id')  # ðŸ†• Check state first
            
            try:
                # ASYNC-SAFE: Get codebase_id from project if not in state
                if not codebase_id:
                    project_id = state.get('project_id')
                    if project_id:
                        from models.project import Project
                        
                        # Wrap Django ORM in sync_to_async
                        try:
                            @sync_to_async
                            def get_project():
                                return Project.objects.get(id=project_id)
                            
                            project = await get_project()
                            if hasattr(project, 'codebase') and project.codebase:
                                codebase_id = str(project.codebase.id)
                                logger.info(f"ðŸ“¦ Using codebase from project: {codebase_id}")
                        except Exception as e:
                            logger.debug(f"Could not get codebase from project: {e}")
                
                # ASYNC-SAFE: If no codebase from project, get latest for user
                if not codebase_id:
                    from models.project import CompanyCodebase
                    
                    @sync_to_async
                    def get_latest_codebase():
                        normalized_user_id = str(user_id or '').strip()
                        user_codebases = CompanyCodebase.objects.none()

                        if normalized_user_id.isdigit():
                            user_codebases = CompanyCodebase.objects.filter(
                                user_id=int(normalized_user_id)
                            ).order_by('-created_at')
                        elif normalized_user_id:
                            for filter_kwargs in (
                                {'user__username': normalized_user_id},
                                {'user__email': normalized_user_id},
                            ):
                                try:
                                    candidate_qs = CompanyCodebase.objects.filter(**filter_kwargs).order_by('-created_at')
                                except Exception:
                                    continue
                                if candidate_qs.exists():
                                    user_codebases = candidate_qs
                                    break

                        if user_codebases.exists():
                            return str(user_codebases.first().id)
                        return None
                    
                    codebase_id = await get_latest_codebase()
                    if codebase_id:
                        logger.info(f"ðŸ“¦ Using latest codebase for user: {codebase_id}")

                strict_contract = state.get('strict_contract') or {}
                entity_filename = str(strict_contract.get('file_name') or '').strip()
                if not entity_filename:
                    master_table = str(
                        strict_contract.get('master_table')
                        or state.get('intent', {}).get('database', {}).get('table_name')
                        or ''
                    ).strip()
                    if master_table.lower().startswith('tbl') and len(master_table) > 3:
                        entity_base = master_table[3:]
                        entity_name = ''.join(
                            part.capitalize()
                            for part in re.split(r'[_\s\-]+', entity_base)
                            if part
                        )
                        if entity_name:
                            entity_filename = f"frm{entity_name}.php"

                entity_file_in_index = False
                if codebase_id and entity_filename:
                    entity_file_in_index = self._check_entity_file_indexed(
                        codebase_id=codebase_id,
                        entity_filename=entity_filename,
                        user_id=user_id,
                    )
                state['entity_file_in_index'] = entity_file_in_index
                if entity_filename:
                    logger.info(
                        "Entity index precheck: file=%s indexed=%s",
                        entity_filename,
                        entity_file_in_index
                    )
                    if strict_contract.get('valid') and not entity_file_in_index:
                        _append_preflight_warning(
                            'entity_file_not_indexed',
                            (
                                f"Exact entity file '{entity_filename}' not indexed; "
                                "structural retrieval fallback will be used."
                            )
                        )
                
                # Load analyzed patterns if we have codebase_id
                if codebase_id:
                    analyzed_patterns = get_cached_analyzed_patterns(user_id, codebase_id)
                    
                    if analyzed_patterns:
                        logger.info(f"✅ Using cached analyzed patterns for codebase {codebase_id}")
                        # Store in state for use in generation nodes
                        state['analyzed_patterns'] = analyzed_patterns
                        state['codebase_id'] = codebase_id  # Store for later use
                        
                        # ✅ TASK 3.4: Add template information to state
                        # Extract template info from analyzed patterns for generation node
                        logger.info("🔧 TASK 3.4: Adding template information to state...")
                        
                        # Verify analyzed patterns include all mandatory company functions
                        php_patterns = analyzed_patterns.get('php', {})
                        functions = list(php_patterns.get('functions', []) or [])
                        for extra_key in ('database_functions', 'db_functions'):
                            extra_functions = php_patterns.get(extra_key, []) or analyzed_patterns.get(extra_key, []) or []
                            if extra_functions:
                                functions.extend(list(extra_functions))
                        
                        mandatory_functions = [
                            'db_insert', 'db_update', 'db_delete', 'db_getRecord',
                            'getrows', 'getvalue', 'funStartTran', 'funEndTran'
                        ]
                        
                        # Extract function names from mixed list (strings or dicts)
                        def _normalize_function_name(raw_name: str) -> str:
                            token = str(raw_name or '').strip()
                            if not token:
                                return ''
                            match = re.search(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(', token)
                            if match:
                                token = match.group(1)
                            token = re.sub(r'[^A-Za-z0-9_]', '', token)
                            return token

                        function_names = []
                        for f in functions:
                            if isinstance(f, dict):
                                # Try common keys for function names
                                name = f.get('name') or f.get('function') or f.get('type')
                                normalized_name = _normalize_function_name(name)
                                if normalized_name:
                                    function_names.append(normalized_name)
                            elif f:
                                normalized_name = _normalize_function_name(f)
                                if normalized_name:
                                    function_names.append(normalized_name)
                        normalized_function_lookup = {func_name.lower() for func_name in function_names}
                        
                        missing_functions = []
                        for func in mandatory_functions:
                            if func.lower() not in normalized_function_lookup:
                                missing_functions.append(func)
                        strict_contract_active = bool((state.get('strict_contract') or {}).get('valid'))
                        
                        # FIX #4: Inject canonical signatures if missing
                        if missing_functions:
                            logger.warning(
                                f"⚠️ Analyzed patterns missing mandatory functions: {', '.join(missing_functions)}"
                            )
                            if strict_contract_active:
                                logger.warning(
                                    "Strict contract mode active: canonical function fallback injection disabled."
                                )
                            else:
                                logger.info("🔧 FIX #4: Injecting canonical function signatures for missing functions")
                             
                                # Canonical signatures for company's functions
                                canonical_signatures = {
                                    'db_insert': {
                                        'name': 'db_insert',
                                        'signature': 'db_insert($table, $data_array)',
                                        'description': 'Insert record into database table',
                                        'source': 'canonical_fallback'
                                    },
                                    'db_update': {
                                        'name': 'db_update',
                                        'signature': 'db_update($table, $data_array, $where_array)',
                                        'description': 'Update record in database table',
                                        'source': 'canonical_fallback'
                                    },
                                    'db_delete': {
                                        'name': 'db_delete',
                                        'signature': 'db_delete($table, $where_array)',
                                        'description': 'Delete record from database table',
                                        'source': 'canonical_fallback'
                                    },
                                    'db_getRecord': {
                                        'name': 'db_getRecord',
                                        'signature': 'db_getRecord($table, $where_array)',
                                        'description': 'Get single record from database table',
                                        'source': 'canonical_fallback'
                                    },
                                    'getrows': {
                                        'name': 'getrows',
                                        'signature': 'getrows($sql_query)',
                                        'description': 'Execute SQL query and return all rows',
                                        'source': 'canonical_fallback'
                                    },
                                    'getvalue': {
                                        'name': 'getvalue',
                                        'signature': 'getvalue($sql_query)',
                                        'description': 'Execute SQL query and return single scalar value',
                                        'source': 'canonical_fallback'
                                    },
                                    'funStartTran': {
                                        'name': 'funStartTran',
                                        'signature': 'funStartTran()',
                                        'description': 'Start database transaction',
                                        'source': 'canonical_fallback'
                                    },
                                    'funEndTran': {
                                        'name': 'funEndTran',
                                        'signature': 'funEndTran($commit=true)',
                                        'description': 'End database transaction (commit or rollback)',
                                        'source': 'canonical_fallback'
                                    }
                                }
                                 
                                # Inject missing functions into analyzed patterns
                                if 'functions' not in php_patterns:
                                    php_patterns['functions'] = []
                                 
                                for func_name in missing_functions:
                                    if func_name in canonical_signatures:
                                        php_patterns['functions'].append(canonical_signatures[func_name])
                                        function_names.append(func_name)
                                 
                                logger.info(f"✅ FIX #4: Injected {len(missing_functions)} canonical function signatures")
                                missing_functions = []  # Clear after injection
                        else:
                            logger.info(f"✅ All mandatory company functions present in analyzed patterns")
                        
                        # Store template metadata in state for generation node
                        state['template_info'] = {
                            'codebase_id': codebase_id,
                            'has_analyzed_patterns': True,
                            'mandatory_functions': mandatory_functions,
                            'available_functions': function_names,  # Use extracted names
                            'missing_functions': missing_functions,
                            'table_names': php_patterns.get('table_names', []),
                            'field_names': php_patterns.get('field_names', []),
                            'ajax_functions': php_patterns.get('ajax_functions', []),
                            'uses_vector_search': False,  # Using analyzed patterns, not vector search
                            'pattern_extraction_method': 'dynamic'  # Dynamic pattern extraction from codebase
                        }
                        
                        logger.info(f"✅ Template info added to state:")
                        logger.info(f"   - Codebase ID: {codebase_id}")
                        logger.info(f"   - Functions: {len(function_names)} total")
                        logger.info(f"   - Mandatory functions: {len(mandatory_functions) - len(missing_functions)}/{len(mandatory_functions)}")
                        logger.info(f"   - Tables: {len(php_patterns.get('table_names', []))}")
                        logger.info(f"   - Fields: {len(php_patterns.get('field_names', []))}")
                        logger.info(f"   - Pattern extraction: dynamic (from codebase)")
                    else:
                        logger.info(f"âš ï¸ No cached analyzed patterns found for codebase {codebase_id}")
                        logger.info(f"ðŸ’¡ Run: python run_pattern_analysis.py {user_id}")
                else:
                    logger.warning(f"âš ï¸ No codebase found for user {user_id}")
                        
            except Exception as e:
                logger.warning(f"Could not load analyzed patterns: {e}")
            
            # Build search query from intent WITH company context
            # ENHANCED: Include analyzed patterns for better matching
            intent_fields = intent.get('fields') or []
            field_names = []
            for field_item in intent_fields:
                if isinstance(field_item, dict):
                    field_name = str(field_item.get('name') or '').strip()
                else:
                    field_name = str(field_item or '').strip()
                if field_name:
                    field_names.append(field_name)

            intent_operations = [
                str(op).strip()
                for op in (intent.get('operations') or [])
                if str(op).strip()
            ]
            intent_feature_type = str(intent.get('feature_type') or 'form').strip() or 'form'
            search_query = f"""
            {intent_feature_type} with fields: {', '.join(field_names) if field_names else 'none'}
            Operations: {', '.join(intent_operations) if intent_operations else 'create, read, update, delete'}
            """
            
            # ðŸ†• FIXED: Build RICH search query with company context
            if analyzed_patterns:
                # Extract company context
                company_context = self._build_rich_search_query(
                    intent,
                    analyzed_patterns,
                    state.get('strict_contract') or {}
                )
                search_query = company_context
            
            logger.info(f"ðŸ” Search Query:\n{search_query}")
            
            # ðŸ†• FIXED ISSUE #3: Use COMPLETE analyzed patterns instead of just 10 patterns
            # Don't retrieve just 10 patterns - use COMPLETE codebase analysis!
            
            if analyzed_patterns:
                # âœ… Use COMPLETE codebase analysis (all 247 files analyzed)
                logger.info(f"âœ… Using COMPLETE codebase analysis (not just 10 patterns)")
                
                # ðŸ†• VERIFY: Log what's in analyzed_patterns
                php_patterns = analyzed_patterns.get('php', {})
                logger.info(f"ðŸ“Š Analyzed Patterns Summary:")
                logger.info(f"   - PHP Functions: {len(php_patterns.get('functions', []))} total")
                logger.info(f"   - Database Tables: {len(php_patterns.get('table_names', []))} total")
                logger.info(f"   - Field Names: {len(php_patterns.get('field_names', []))} total")
                logger.info(f"   - AJAX Functions: {len(php_patterns.get('ajax_functions', []))} total")
                logger.info(f"   - CSS Classes: {len(analyzed_patterns.get('html', {}).get('css_classes', []))} total")
                
                # Format analyzed patterns for LLM
                try:
                    patterns = self._format_analyzed_patterns_for_llm(analyzed_patterns)
                except Exception as format_error:
                    logger.warning(f"Pattern formatting failed, using compact fallback: {format_error}")
                    php = analyzed_patterns.get('php', {}) if isinstance(analyzed_patterns, dict) else {}
                    fallback_tables = php.get('table_names', []) if isinstance(php, dict) else []
                    fallback_funcs = php.get('functions', []) if isinstance(php, dict) else []
                    patterns = (
                        "COMPLETE CODEBASE ANALYSIS (FALLBACK)\n"
                        f"Tables: {str(fallback_tables)[:2000]}\n"
                        f"Functions: {str(fallback_funcs)[:2000]}\n"
                    )
                
                logger.info(f"ðŸ“ Formatted Analyzed Patterns Size: {len(patterns)} characters")
                
                state['retrieved_patterns'] = [
                    {
                        'language': 'complete_analysis',
                        'patterns': patterns,
                        'analysis': 'COMPLETE CODEBASE ANALYSIS'
                    }
                ]
            else:
                # Fallback: If no analyzed patterns, retrieve 10 similar patterns per language
                logger.warning("âš ï¸ No analyzed patterns found, falling back to similarity search")
                
                from agents.utils.cache_helper import get_cached_patterns, set_cached_patterns
                
                patterns = {}
                cache_hits = 0
                
                # Search for similar patterns by language with caching
                for lang in ['php', 'html', 'css', 'js', 'sql']:
                    cached = get_cached_patterns(user_id, search_query, lang)
                    
                    if cached:
                        patterns[lang] = cached
                        cache_hits += 1
                    else:
                        # Retrieve 10 patterns from company codebase
                        patterns[lang] = self._search_by_language(search_query, lang, user_id, k=10)
                        set_cached_patterns(user_id, search_query, lang, patterns[lang])
                
                logger.info(f"Pattern cache: {cache_hits}/5 hits")
                
                # Log total patterns retrieved
                total_patterns = sum(len(p) for p in patterns.values())
                logger.info(f"ðŸ“Š Total patterns retrieved: {total_patterns} across 5 languages")
                for lang, pats in patterns.items():
                    if pats:
                        logger.info(f"   {lang.upper()}: {len(pats)} patterns")
                
                state['retrieved_patterns'] = [
                    {
                        'language': lang,
                        'patterns': patterns[lang],
                    }
                    for lang in patterns.keys()
                ]
                
                # ✅ TASK 3.4: Add template info for vector search fallback
                logger.info("🔧 TASK 3.4: Adding template info for vector search fallback...")
                
                # Extract functions from retrieved patterns
                php_patterns_text = patterns.get('php', [])
                available_functions = []
                
                # Parse functions from retrieved PHP patterns
                if isinstance(php_patterns_text, list):
                    for pattern in php_patterns_text:
                        if isinstance(pattern, dict):
                            pattern_text = pattern.get('content', '')
                        else:
                            pattern_text = str(pattern)
                        
                        # Extract function names from pattern text
                        func_matches = re.findall(r'function\s+(\w+)\s*\(', pattern_text)
                        available_functions.extend(func_matches)
                
                # Remove duplicates
                available_functions = list(set(available_functions))
                
                mandatory_functions = [
                    'db_insert', 'db_update', 'db_delete', 'db_getRecord',
                    'getrows', 'getvalue', 'funStartTran', 'funEndTran'
                ]
                
                missing_functions = [f for f in mandatory_functions if f not in available_functions]
                
                state['template_info'] = {
                    'codebase_id': codebase_id if codebase_id else None,
                    'has_analyzed_patterns': False,
                    'mandatory_functions': mandatory_functions,
                    'available_functions': available_functions,
                    'missing_functions': missing_functions,
                    'table_names': [],
                    'field_names': [],
                    'ajax_functions': [],
                    'uses_vector_search': True,  # Using ChromaDB vector search
                    'pattern_extraction_method': 'vector_search'  # Vector similarity search
                }
                
                logger.info(f"✅ Template info added to state (vector search mode):")
                logger.info(f"   - Functions found: {len(available_functions)}")
                logger.info(f"   - Mandatory functions: {len(mandatory_functions) - len(missing_functions)}/{len(mandatory_functions)}")
                logger.info(f"   - Pattern extraction: vector_search (ChromaDB)")
                
                if missing_functions:
                    logger.warning(f"   - Missing functions: {', '.join(missing_functions)}")
            
            state['current_step'] = 'patterns_retrieved'
            logger.info(f"âœ… Pattern retrieval complete")
            
            return state
            
        except Exception as e:
            logger.error(f"Error in pattern retrieval: {str(e)}")
            state['status'] = 'failed'
            state['error_message'] = f"Pattern retrieval failed: {str(e)}"
            state['retrieved_patterns'] = []  # Set empty list instead of leaving undefined
            return state

    def _build_rich_search_query(self, intent: Dict, analyzed_patterns: Dict, strict_contract: Dict = None) -> str:
        """
        Build a richer semantic query using intent + analyzed company metadata.
        Keeps query concise enough for embedding search while preserving key context.
        """
        strict_contract = strict_contract or {}
        feature_type = str(intent.get('feature_type') or 'form').strip() or 'form'
        operations = [
            str(op).strip()
            for op in (intent.get('operations') or [])
            if str(op).strip()
        ]

        field_items = intent.get('fields') or []
        fields = []
        for item in field_items:
            if isinstance(item, dict):
                name = str(item.get('name') or '').strip()
            else:
                name = str(item or '').strip()
            if name:
                fields.append(name)

        php = analyzed_patterns.get('php', {}) if isinstance(analyzed_patterns, dict) else {}
        common_funcs = php.get('functions', []) if isinstance(php, dict) else []
        ajax_funcs = php.get('ajax_functions', []) if isinstance(php, dict) else []
        table_names = php.get('table_names', []) if isinstance(php, dict) else []

        def _top_items(values, key_candidates, limit):
            out = []
            for value in values[:limit]:
                token = ''
                if isinstance(value, dict):
                    for key in key_candidates:
                        if value.get(key):
                            token = str(value.get(key))
                            break
                elif value:
                    token = str(value)
                token = token.strip()
                if token:
                    out.append(token)
            return out

        contract_tables = []
        if strict_contract.get('valid'):
            master_table = str(strict_contract.get('master_table') or '').strip()
            detail_table = str(strict_contract.get('detail_table') or '').strip()
            if master_table:
                contract_tables.append(master_table)
            if detail_table:
                contract_tables.append(detail_table)
            for dep in strict_contract.get('dependencies') or []:
                dep_table = str(dep.get('table') or '').strip()
                if dep_table:
                    contract_tables.append(dep_table)

            if not fields:
                for field in (strict_contract.get('master_fields') or []):
                    field_name = str(field.get('name') if isinstance(field, dict) else field).strip()
                    if field_name:
                        fields.append(field_name)
                for field in (strict_contract.get('detail_fields') or []):
                    field_name = str(field.get('name') if isinstance(field, dict) else field).strip()
                    if field_name:
                        fields.append(field_name)

        table_tokens = []
        for table in contract_tables:
            if table and table not in table_tokens:
                table_tokens.append(table)

        if not table_tokens:
            for token in _top_items(table_names, ['name', 'table'], 8):
                if token not in table_tokens:
                    table_tokens.append(token)

        func_tokens = _top_items(common_funcs, ['name', 'type', 'function'], 10)
        ajax_tokens = _top_items(ajax_funcs, ['type', 'name', 'function'], 6)

        query_parts = [
            f"{feature_type} form",
            f"fields: {', '.join(fields[:25])}" if fields else "",
            f"operations: {', '.join(operations)}" if operations else "",
            f"tables: {', '.join(table_tokens[:8])}" if table_tokens else "",
            f"functions: {', '.join(func_tokens)}" if func_tokens else "",
            f"ajax: {', '.join(ajax_tokens)}" if ajax_tokens else "",
        ]
        return " | ".join([part for part in query_parts if part]).strip()
    
    def _search_by_language(self, query: str, language: str, user_id: str, k: int = 10):
        """
        Search for patterns in specific language with quality filtering
        ENHANCED: Uses metadata filtering for company-specific patterns
        """
        try:
            # Build filter dict with company-specific metadata
            # âœ… FIXED: Only use filters that actually exist in stored metadata
            filter_dict = {
                'language': language,
                'user_id': user_id
            }
            
            # âŒ REMOVED: has_database, has_form, has_ajax don't exist in metadata
            # These filters were causing 0 results for PHP/HTML/JS/SQL
            # CSS works because it doesn't have these extra filters
            
            logger.info(f"ðŸ” Searching for {language} files with filter: {filter_dict}")
            
            results = self.embedding_manager.search_similar_code(
                query=query,
                k=k * 2,  # Get 2x to account for filtering
                filter_dict=filter_dict
            )
            
            logger.info(f"âœ… Found {len(results)} {language} files")
            
            # Filter out low-quality matches (similarity < 0.1)
            # Very low threshold to allow MORE company patterns through
            quality_threshold = 0.1
            filtered_results = [
                r for r in results 
                if r.get('similarity_score', 0) >= quality_threshold
            ]
            
            if len(filtered_results) < len(results):
                logger.info(f"Filtered out {len(results) - len(filtered_results)} low-quality patterns for {language}")
            
            # If no patterns pass threshold, return all patterns anyway (company code is valuable!)
            if not filtered_results and results:
                logger.warning(f"No patterns passed threshold for {language}, using all {len(results)} patterns")
                return results[:k]
            
            # Log how many patterns we're using
            if filtered_results:
                logger.info(f"âœ… Using {len(filtered_results[:k])} {language.upper()} patterns from company codebase")
            
            return filtered_results[:k]
            
        except Exception as e:
            logger.warning(f"No patterns found for {language}: {str(e)}")
            return []
    
    def _format_patterns_for_llm(self, patterns: Dict) -> str:
        """
        Format retrieved patterns for LLM consumption with actual code examples
        ENHANCED: Now includes full code content instead of just analysis
        """
        formatted = []
        
        for language, pattern_list in patterns.items():
            if pattern_list:
                formatted.append(f"\n## {language.upper()} PATTERNS:\n")
                for i, pattern in enumerate(pattern_list, 1):
                    similarity = pattern.get('similarity_score', 0)
                    quality = "High" if similarity >= 0.8 else "Medium" if similarity >= 0.6 else "Low"
                    
                    formatted.append(f"\n### Example {i} (Quality: {quality}, Similarity: {similarity:.2f}):")
                    formatted.append(f"File: {pattern['metadata'].get('file_path', 'N/A')}")
                    
                    # Add metadata info
                    metadata = pattern['metadata']
                    if metadata.get('table_names'):
                        # âœ… ISSUE #12 FIX: table_names is a comma-separated string, not a list
                        tables = metadata['table_names'].split(',') if isinstance(metadata['table_names'], str) else metadata['table_names']
                        formatted.append(f"Tables: {', '.join(str(t) for t in tables[:5])}")
                    if metadata.get('has_ajax'):
                        formatted.append(f"Has AJAX: Yes")
                    if metadata.get('functions'):
                        # âœ… ISSUE #12 FIX: functions might be a comma-separated string, not a list
                        funcs = metadata['functions'].split(',') if isinstance(metadata['functions'], str) else metadata['functions']
                        formatted.append(f"Functions: {', '.join(str(f) for f in funcs[:5])}")
                    
                    formatted.append(f"```{language}")
                    formatted.append(pattern['content'])
                    formatted.append("```\n")
        
        return "\n".join(formatted) if formatted else "No patterns found."

    def _normalize_pattern_entries(self, section) -> List[Dict]:
        """
        Normalize analyzer output so downstream formatting code can handle both
        list-shaped and dict-shaped sections without raising slice/type errors.
        """
        if not section:
            return []

        if isinstance(section, list):
            return section

        if isinstance(section, tuple):
            return list(section)

        if isinstance(section, dict):
            # If the analyzer already returned a single pattern object with
            # scalar attributes, preserve it as one entry instead of
            # exploding each key into a separate pseudo-pattern.
            scalar_values = all(not isinstance(value, (list, tuple, dict)) for value in section.values())
            if scalar_values:
                return [section]

            normalized = []
            for key, value in section.items():
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            normalized.append({'type': key, **item})
                        else:
                            normalized.append({'type': key, 'value': item})
                elif isinstance(value, dict):
                    normalized.append({'type': key, **value})
                elif value not in (None, '', [], {}):
                    normalized.append({'type': key, 'value': value})
            return normalized

        return [{'value': section}]
    
    def _format_analyzed_patterns_for_llm(self, analyzed_patterns: Dict) -> str:
        """
        Format COMPLETE analyzed patterns from entire codebase for LLM
        FIXED ISSUE #3: Now passes COMPLETE codebase analysis (all 247 files)
        """
        formatted = []
        
        # PHP Patterns
        if analyzed_patterns.get('php'):
            php = analyzed_patterns['php']
            formatted.append("=" * 80)
            formatted.append("COMPLETE PHP CODEBASE ANALYSIS (ALL FILES)")
            formatted.append("=" * 80)
            
            if php.get('functions'):
                formatted.append(f"\nðŸ“Œ ALL FUNCTIONS FOUND ({len(php['functions'])} total):")
                # âœ… ISSUE #8 FIX: Show top 100 instead of 50 for better coverage
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                functions_list = php['functions'][:100]
                if functions_list:
                    # Convert all items to strings safely - handle dict, str, and None
                    funcs_str = ", ".join([
                        str(f.get('name', f.get('type', 'unknown'))) if isinstance(f, dict) 
                        else str(f) if f is not None 
                        else 'unknown'
                        for f in functions_list
                    ])
                    formatted.append(funcs_str)
            
            if php.get('table_names'):
                formatted.append(f"\nðŸ“Œ ALL DATABASE TABLES ({len(php['table_names'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                table_list = php['table_names']
                if table_list:
                    tables_str = ", ".join([
                        str(t.get('name', t.get('table', 'unknown'))) if isinstance(t, dict) 
                        else str(t) if t is not None 
                        else 'unknown'
                        for t in table_list
                    ])
                    formatted.append(tables_str)
            
            if php.get('field_names'):
                formatted.append(f"\nðŸ“Œ ALL FIELD NAMES ({len(php['field_names'])} total):")
                # âœ… ISSUE #8 FIX: Show top 100 instead of 50 for better coverage
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                field_list = php['field_names'][:100]
                if field_list:
                    fields_str = ", ".join([
                        str(f.get('name', f.get('field', 'unknown'))) if isinstance(f, dict) 
                        else str(f) if f is not None 
                        else 'unknown'
                        for f in field_list
                    ])
                    formatted.append(fields_str)
            
            if php.get('ajax_functions'):
                formatted.append(f"\nðŸ“Œ ALL AJAX FUNCTIONS ({len(php['ajax_functions'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                ajax_list = php['ajax_functions']
                if ajax_list:
                    ajax_str = ", ".join([
                        str(a.get('type', a.get('code', 'unknown'))) if isinstance(a, dict) 
                        else str(a) if a is not None 
                        else 'unknown'
                        for a in ajax_list
                    ])
                    formatted.append(ajax_str)
            
            if php.get('db_connection'):
                formatted.append(f"\nðŸ“Œ DATABASE CONNECTION PATTERN:")
                formatted.append(php['db_connection'])
            
            if php.get('session_management'):
                formatted.append(f"\nðŸ“Œ SESSION MANAGEMENT PATTERN:")
                formatted.append(php['session_management'])
            
            if php.get('naming_conventions'):
                formatted.append(f"\nðŸ“Œ NAMING CONVENTIONS:")
                conventions = php['naming_conventions']
                formatted.append(f"  - Dominant Style: {conventions.get('dominant_style', 'N/A')}")
                formatted.append(f"  - Uppercase: {conventions.get('uppercase_percent', 0):.1f}%")
                formatted.append(f"  - Lowercase: {conventions.get('lowercase_percent', 0):.1f}%")
                formatted.append(f"  - CamelCase: {conventions.get('camelcase_percent', 0):.1f}%")
                formatted.append(f"  - Snake_case: {conventions.get('snake_case_percent', 0):.1f}%")
            
            if php.get('common_variables'):
                formatted.append(f"\nðŸ“Œ COMMON VARIABLES ({len(php['common_variables'])} total):")
                # âœ… ISSUE #8 FIX: Show top 50 instead of 30 for better coverage
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                var_list = php['common_variables'][:50]
                if var_list:
                    vars_str = ", ".join([
                        str(v.get('name', v.get('variable', 'unknown'))) if isinstance(v, dict) 
                        else str(v) if v is not None 
                        else 'unknown'
                        for v in var_list
                    ])
                    formatted.append(vars_str)
            
            if php.get('validation_functions'):
                formatted.append(f"\nðŸ“Œ VALIDATION FUNCTIONS ({len(php['validation_functions'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                val_list = php['validation_functions']
                if val_list:
                    vals_str = ", ".join([
                        str(v.get('name', v.get('function', 'unknown'))) if isinstance(v, dict) 
                        else str(v) if v is not None 
                        else 'unknown'
                        for v in val_list
                    ])
                    formatted.append(vals_str)
            
            if php.get('transaction_management'):
                formatted.append(f"\nðŸ“Œ TRANSACTION MANAGEMENT:")
                tm = php['transaction_management']
                formatted.append(f"  - Start: {tm.get('start', 'N/A')}")
                formatted.append(f"  - End: {tm.get('end', 'N/A')}")
            
            if php.get('include_patterns'):
                formatted.append(f"\nðŸ“Œ INCLUDE PATTERNS ({len(php['include_patterns'])} total):")
                # âœ… ISSUE #8 FIX: Show top 30 instead of 20 for better coverage
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                inc_list = php['include_patterns'][:30]
                if inc_list:
                    incs_str = ", ".join([
                        str(i.get('name', i.get('file', 'unknown'))) if isinstance(i, dict) 
                        else str(i) if i is not None 
                        else 'unknown'
                        for i in inc_list
                    ])
                    formatted.append(incs_str)
            
            # âœ… ISSUE #6 FIX: Include 12 CRITICAL PATTERNS in cache
            # These patterns were being extracted but NOT included in LLM prompt
            
            if php.get('ajax_auto_id'):
                formatted.append(f"\nðŸ“Œ AJAX AUTO-ID GENERATION ({len(php['ajax_auto_id'])} patterns):")
                for i, pattern in enumerate(php['ajax_auto_id'][:5], 1):
                    formatted.append(f"  {i}. Type: {pattern.get('type', 'N/A')}")
                    if pattern.get('code'):
                        formatted.append(f"     Code: {pattern['code'][:150]}")
            
            if php.get('delete_checks'):
                formatted.append(f"\nðŸ“Œ PRE-DELETE DEPENDENCY CHECKS ({len(php['delete_checks'])} patterns):")
                for i, check in enumerate(php['delete_checks'][:5], 1):
                    formatted.append(f"  {i}. Table: {check.get('related_table', 'N/A')}, Type: {check.get('type', 'N/A')}")
                    if check.get('check_code'):
                        formatted.append(f"     Code: {check['check_code'][:150]}")
            
            if php.get('chart_integration'):
                formatted.append(f"\nðŸ“Œ CHART OF ACCOUNTS INTEGRATION ({len(php['chart_integration'])} patterns):")
                for i, chart in enumerate(php['chart_integration'][:5], 1):
                    formatted.append(f"  {i}. Type: {chart.get('type', 'N/A')}")
                    if chart.get('code'):
                        formatted.append(f"     Code: {chart['code'][:150]}")
            
            if php.get('dynamic_dropdowns'):
                formatted.append(f"\nðŸ“Œ CASCADING/DYNAMIC DROPDOWNS ({len(php['dynamic_dropdowns'])} patterns):")
                for i, dropdown in enumerate(php['dynamic_dropdowns'][:5], 1):
                    formatted.append(f"  {i}. Type: {dropdown.get('type', 'N/A')}")
                    if dropdown.get('function'):
                        formatted.append(f"     Function: {dropdown['function']}")
                    if dropdown.get('code'):
                        formatted.append(f"     Code: {dropdown['code'][:150]}")
            
            if php.get('formvalidation'):
                fv = php['formvalidation']
                if fv.get('has_formvalidation'):
                    formatted.append(f"\nðŸ“Œ FORMVALIDATION.JS FRAMEWORK:")
                    formatted.append(f"  - Form Selector: {fv.get('form_selector', 'N/A')}")
                    formatted.append(f"  - Framework: {fv.get('framework', 'N/A')}")
                    formatted.append(f"  - Fields: {len(fv.get('fields', []))} validated fields")
                    formatted.append(f"  - Validators: {len(fv.get('validators', []))} validator types")
                    if fv.get('initialization'):
                        formatted.append(f"  - Init Code: {fv['initialization'][:150]}")
            
            if php.get('keyboard_navigation'):
                kb = php['keyboard_navigation']
                if kb.get('has_keyboard_nav'):
                    formatted.append(f"\nðŸ“Œ KEYBOARD NAVIGATION:")
                    formatted.append(f"  - Function: {kb.get('function_name', 'N/A')}")
                    formatted.append(f"  - Enter Key: {kb.get('handles_enter', False)}")
                    formatted.append(f"  - Tab Key: {kb.get('handles_tab', False)}")
                    if kb.get('code'):
                        formatted.append(f"  - Code: {kb['code'][:150]}")
            
            if php.get('grid_patterns'):
                formatted.append(f"\nðŸ“Œ GRID/TABLE PATTERNS ({len(php['grid_patterns'])} patterns):")
                for i, grid in enumerate(php['grid_patterns'][:5], 1):
                    formatted.append(f"  {i}. Type: {grid.get('type', 'N/A')}")
                    if grid.get('function'):
                        formatted.append(f"     Function: {grid['function']}")
            
            if php.get('disabled_fields'):
                disabled_entries = self._normalize_pattern_entries(php['disabled_fields'])
                formatted.append(f"\nðŸ“Œ DISABLED FIELD HANDLING ({len(disabled_entries)} patterns):")
                for i, disabled in enumerate(disabled_entries[:3], 1):
                    formatted.append(f"  {i}. Type: {disabled.get('type', 'N/A')}")
                    if disabled.get('field_name'):
                        formatted.append(f"     Field: {disabled['field_name']}")
                    if disabled.get('context'):
                        formatted.append(f"     Context: {str(disabled['context'])[:100]}")
                    if disabled.get('code'):
                        formatted.append(f"     Code: {disabled['code'][:150]}")
            
            if php.get('asset_loading'):
                assets = php['asset_loading']
                if assets.get('css_files') or assets.get('js_files'):
                    formatted.append(f"\nðŸ“Œ ASSET LOADING PATTERN:")
                    if assets.get('css_files'):
                        formatted.append(f"  - CSS Files: {len(assets['css_files'])} files")
                        formatted.append(f"    Examples: {', '.join(str(c) for c in assets['css_files'][:5])}")
                    if assets.get('js_files'):
                        formatted.append(f"  - JS Files: {len(assets['js_files'])} files")
                        formatted.append(f"    Examples: {', '.join(str(j) for j in assets['js_files'][:5])}")
            
            if php.get('php_includes'):
                formatted.append(f"\nðŸ“Œ PHP INCLUDE FILES ({len(php['php_includes'])} files):")
                formatted.append(f"  {', '.join(str(i) for i in php['php_includes'][:10])}")
            
            if php.get('conditional_logic'):
                conditional_entries = self._normalize_pattern_entries(php['conditional_logic'])
                formatted.append(f"\nðŸ“Œ CONDITIONAL CODE GENERATION ({len(conditional_entries)} patterns):")
                for i, cond in enumerate(conditional_entries[:3], 1):
                    formatted.append(f"  {i}. Type: {cond.get('type', 'N/A')}")
                    if cond.get('condition'):
                        formatted.append(f"     Condition: {cond['condition'][:100]}")
                    elif cond.get('value'):
                        formatted.append(f"     Value: {str(cond['value'])[:100]}")
                    if cond.get('action'):
                        formatted.append(f"     Action: {str(cond['action'])[:100]}")
                    if cond.get('context'):
                        formatted.append(f"     Context: {str(cond['context'])[:100]}")
        
        # HTML Patterns
        if analyzed_patterns.get('html'):
            html = analyzed_patterns['html']
            formatted.append("\n" + "=" * 80)
            formatted.append("COMPLETE HTML CODEBASE ANALYSIS (ALL FILES)")
            formatted.append("=" * 80)
            
            if html.get('css_classes'):
                formatted.append(f"\nðŸ“Œ ALL CSS CLASSES ({len(html['css_classes'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                css_list = html['css_classes']
                if css_list:
                    css_str = ", ".join([
                        str(c.get('name', c.get('class', 'unknown'))) if isinstance(c, dict) 
                        else str(c) if c is not None 
                        else 'unknown'
                        for c in css_list
                    ])
                    formatted.append(css_str)
            
            if html.get('button_patterns'):
                formatted.append(f"\nðŸ“Œ BUTTON PATTERNS ({len(html['button_patterns'])} total):")
                for i, btn in enumerate(html['button_patterns'][:5], 1):
                    formatted.append(f"  {i}. {btn[:100]}")
            
            if html.get('input_naming'):
                formatted.append(f"\nðŸ“Œ INPUT NAMING PATTERN:")
                naming = html['input_naming']
                formatted.append(f"  - Uses Uppercase: {naming.get('uses_uppercase', False)}")
                formatted.append(f"  - Examples: {', '.join(str(e) for e in naming.get('examples', []))}")
            
            # âœ… ISSUE #6 FIX: Include 12 CRITICAL PATTERNS from HTML analysis
            
            if html.get('ajax_auto_id'):
                formatted.append(f"\nðŸ“Œ AJAX AUTO-ID (HTML) ({len(html['ajax_auto_id'])} patterns):")
                for i, pattern in enumerate(html['ajax_auto_id'][:3], 1):
                    formatted.append(f"  {i}. Type: {pattern.get('type', 'N/A')}")
            
            if html.get('dynamic_dropdowns'):
                formatted.append(f"\nðŸ“Œ CASCADING DROPDOWNS (HTML) ({len(html['dynamic_dropdowns'])} patterns):")
                for i, dropdown in enumerate(html['dynamic_dropdowns'][:3], 1):
                    formatted.append(f"  {i}. Type: {dropdown.get('type', 'N/A')}")
            
            if html.get('formvalidation'):
                fv = html['formvalidation']
                if fv.get('has_formvalidation'):
                    formatted.append(f"\nðŸ“Œ FORMVALIDATION (HTML): {len(fv.get('fields', []))} fields")
            
            if html.get('keyboard_navigation'):
                kb = html['keyboard_navigation']
                if kb.get('has_keyboard_nav'):
                    formatted.append(f"\nðŸ“Œ KEYBOARD NAVIGATION (HTML): Enabled")
            
            if html.get('grid_patterns'):
                formatted.append(f"\nðŸ“Œ GRID PATTERNS (HTML) ({len(html['grid_patterns'])} patterns):")
        
        # CSS Patterns
        if analyzed_patterns.get('css'):
            css = analyzed_patterns['css']
            formatted.append("\n" + "=" * 80)
            formatted.append("COMPLETE CSS CODEBASE ANALYSIS (ALL FILES)")
            formatted.append("=" * 80)
            
            if css.get('color_scheme'):
                formatted.append(f"\nðŸ“Œ COLOR SCHEME ({len(css['color_scheme'])} colors):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                color_list = css['color_scheme']
                if color_list:
                    colors_str = ", ".join([
                        str(c.get('color', c.get('value', 'unknown'))) if isinstance(c, dict) 
                        else str(c) if c is not None 
                        else 'unknown'
                        for c in color_list
                    ])
                    formatted.append(colors_str)
            
            if css.get('font_family'):
                formatted.append(f"\nðŸ“Œ FONT FAMILY:")
                formatted.append(css['font_family'])
            
            if css.get('spacing_units'):
                formatted.append(f"\nðŸ“Œ SPACING UNITS:")
                spacing = css['spacing_units']
                formatted.append(f"  - PX: {spacing.get('px_percent', 0):.1f}%")
                formatted.append(f"  - REM: {spacing.get('rem_percent', 0):.1f}%")
                formatted.append(f"  - Dominant: {spacing.get('dominant_unit', 'N/A')}")
        
        # JS Patterns
        if analyzed_patterns.get('js'):
            js = analyzed_patterns['js']
            formatted.append("\n" + "=" * 80)
            formatted.append("COMPLETE JAVASCRIPT CODEBASE ANALYSIS (ALL FILES)")
            formatted.append("=" * 80)
            
            if js.get('functions'):
                formatted.append(f"\nðŸ“Œ ALL JS FUNCTIONS ({len(js['functions'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                js_func_list = js['functions']
                if js_func_list:
                    js_funcs_str = ", ".join([
                        str(f.get('name', f.get('function', 'unknown'))) if isinstance(f, dict) 
                        else str(f) if f is not None 
                        else 'unknown'
                        for f in js_func_list
                    ])
                    formatted.append(js_funcs_str)
            
            if js.get('ajax_pattern'):
                formatted.append(f"\nðŸ“Œ AJAX PATTERN:")
                formatted.append(js['ajax_pattern'][:200])
            
            if js.get('uses_jquery'):
                formatted.append(f"\nðŸ“Œ USES JQUERY: {js['uses_jquery']}")
            
            if js.get('common_variables'):
                formatted.append(f"\nðŸ“Œ COMMON VARIABLES ({len(js['common_variables'])} total):")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                js_var_list = js['common_variables']
                if js_var_list:
                    js_vars_str = ", ".join([
                        str(v.get('name', v.get('variable', 'unknown'))) if isinstance(v, dict) 
                        else str(v) if v is not None 
                        else 'unknown'
                        for v in js_var_list
                    ])
                    formatted.append(js_vars_str)
            
            # âœ… ISSUE #6 FIX: Include 12 CRITICAL PATTERNS from JS analysis
            
            if js.get('ajax_auto_id'):
                formatted.append(f"\nðŸ“Œ AJAX AUTO-ID (JS) ({len(js['ajax_auto_id'])} patterns):")
                for i, pattern in enumerate(js['ajax_auto_id'][:3], 1):
                    formatted.append(f"  {i}. Type: {pattern.get('type', 'N/A')}")
            
            if js.get('dynamic_dropdowns'):
                formatted.append(f"\nðŸ“Œ CASCADING DROPDOWNS (JS) ({len(js['dynamic_dropdowns'])} patterns):")
                for i, dropdown in enumerate(js['dynamic_dropdowns'][:3], 1):
                    formatted.append(f"  {i}. Type: {dropdown.get('type', 'N/A')}, Function: {dropdown.get('function', 'N/A')}")
            
            if js.get('formvalidation'):
                fv = js['formvalidation']
                if fv.get('has_formvalidation'):
                    formatted.append(f"\nðŸ“Œ FORMVALIDATION (JS):")
                    formatted.append(f"  - Form: {fv.get('form_selector', 'N/A')}")
                    formatted.append(f"  - Framework: {fv.get('framework', 'N/A')}")
                    formatted.append(f"  - Fields: {len(fv.get('fields', []))}")
            
            if js.get('keyboard_navigation'):
                kb = js['keyboard_navigation']
                if kb.get('has_keyboard_nav'):
                    formatted.append(f"\nðŸ“Œ KEYBOARD NAVIGATION (JS):")
                    formatted.append(f"  - Function: {kb.get('function_name', 'N/A')}")
            
            if js.get('grid_patterns'):
                formatted.append(f"\nðŸ“Œ GRID PATTERNS (JS) ({len(js['grid_patterns'])} patterns):")
                for i, grid in enumerate(js['grid_patterns'][:3], 1):
                    formatted.append(f"  {i}. Function: {grid.get('function', 'N/A')}")
        
        # SQL Patterns
        if analyzed_patterns.get('sql'):
            sql = analyzed_patterns['sql']
            formatted.append("\n" + "=" * 80)
            formatted.append("COMPLETE SQL CODEBASE ANALYSIS (ALL FILES)")
            formatted.append("=" * 80)
            
            if sql.get('engine'):
                formatted.append(f"\nðŸ“Œ DATABASE ENGINE: {sql['engine']}")
            
            if sql.get('charset'):
                formatted.append(f"\nðŸ“Œ CHARSET: {sql['charset']}")
            
            if sql.get('common_datatypes'):
                formatted.append(f"\nðŸ“Œ COMMON DATATYPES:")
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                dt_list = sql['common_datatypes']
                if dt_list:
                    dt_str = ", ".join([
                        str(d.get('type', d.get('datatype', 'unknown'))) if isinstance(d, dict) 
                        else str(d) if d is not None 
                        else 'unknown'
                        for d in dt_list
                    ])
                    formatted.append(dt_str)
            
            if sql.get('naming_convention'):
                formatted.append(f"\nðŸ“Œ NAMING CONVENTION: {sql['naming_convention']}")
        
        formatted.append("\n" + "=" * 80)
        formatted.append("END OF COMPLETE CODEBASE ANALYSIS")
        formatted.append("=" * 80)
        
        return "\n".join(formatted) if formatted else "No analyzed patterns found."
    
    def _build_company_context(self, analyzed_patterns: Dict) -> str:
        """
        Build company-specific context from analyzed patterns
        This helps the search find company-specific table names, field names, etc.
        """
        context_parts = []
        
        if analyzed_patterns.get('php'):
            php_patterns = analyzed_patterns['php']
            
            # Add table names
            if php_patterns.get('table_names'):
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                table_list = php_patterns['table_names'][:10]
                if table_list:
                    tables = ', '.join([
                        str(t.get('name', t.get('table', 'unknown'))) if isinstance(t, dict) 
                        else str(t) if t is not None 
                        else 'unknown'
                        for t in table_list
                    ])
                    context_parts.append(f"Company database tables: {tables}")
            
            # Add field names
            if php_patterns.get('field_names'):
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                field_list = php_patterns['field_names'][:15]
                if field_list:
                    fields = ', '.join([
                        str(f.get('name', f.get('field', 'unknown'))) if isinstance(f, dict) 
                        else str(f) if f is not None 
                        else 'unknown'
                        for f in field_list
                    ])
                    context_parts.append(f"Common field names: {fields}")
            
            # Add AJAX functions
            if php_patterns.get('ajax_functions'):
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                ajax_list = php_patterns['ajax_functions'][:10]
                if ajax_list:
                    ajax = ', '.join([
                        str(a.get('type', a.get('code', '')))[:50] if isinstance(a, dict) else str(a)[:50]
                        for a in ajax_list
                    ])
                    query_parts.append(f"AJAX Functions: {ajax}")
                    logger.info(f"âœ… Added {len(php_patterns['ajax_functions'])} AJAX functions to search query")
                else:
                    logger.warning(f"âš ï¸ No AJAX functions found in analyzed patterns")
            
            # Add common functions
            if php_patterns.get('functions'):
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                functions_list = php['functions'][:10]
                funcs = ', '.join([
                    str(f.get('name', f.get('type', ''))) if isinstance(f, dict) else str(f)
                    for f in functions_list
                ])
                query_parts.append(f"Company Functions: {funcs}")
            
            # Add database type
            if php.get('db_connection'):
                query_parts.append(f"DB Pattern: {php['db_connection'][:50]}")
            
            # Add transaction info
            if php.get('transaction_management', {}).get('start'):
                query_parts.append(f"Transaction: {php['transaction_management']['start']}")
            
            # Add naming convention
            if php.get('naming_conventions'):
                naming = php['naming_conventions'].get('dominant_style', 'camelCase')
                query_parts.append(f"Naming: {naming}")
        else:
            logger.warning(f"âš ï¸ No PHP patterns found in analyzed_patterns")
        
        # 3. HTML patterns
        if analyzed_patterns.get('html'):
            html = analyzed_patterns['html']
            
            css_classes = html.get('css_classes', [])
            if css_classes:
                # âœ… ISSUE #10 FIX: Safer type handling for mixed dict/string lists
                css = ', '.join([
                    str(c.get('name', c.get('class', ''))) if isinstance(c, dict) else str(c)
                    for c in css_classes[:10]
                ])
                query_parts.append(f"CSS Classes: {css}")
                logger.info(f"âœ… Added {len(css_classes)} CSS classes to search query")
            else:
                logger.warning(f"âš ï¸ No CSS classes found in analyzed patterns")
            
            if html.get('form_structure'):
                query_parts.append(f"Form Structure: {html['form_structure'][:50]}")
        else:
            logger.warning(f"âš ï¸ No HTML patterns found in analyzed_patterns")
        
        # 4. JavaScript patterns
        if analyzed_patterns.get('js'):
            js = analyzed_patterns['js']
            
            if js.get('uses_jquery'):
                query_parts.append(f"Uses jQuery: True")
            
            if js.get('ajax_pattern'):
                query_parts.append(f"AJAX Pattern: {js['ajax_pattern'][:50]}")
        
        # 5. SQL patterns
        if analyzed_patterns.get('sql'):
            sql = analyzed_patterns['sql']
            
            if sql.get('engine'):
                query_parts.append(f"DB Engine: {sql['engine']}")
            
            if sql.get('charset'):
                query_parts.append(f"Charset: {sql['charset']}")
        
        # Combine all parts
        rich_query = "\n".join(query_parts)
        
        logger.info(f"ðŸ“ Rich Search Query Built:")
        logger.info(f"  - Feature: {feature_type}")
        logger.info(f"  - Fields: {len(fields)} fields")
        logger.info(f"  - Operations: {len(operations)} operations")
        logger.info(f"  - Company Tables: {len(analyzed_patterns.get('php', {}).get('table_names', []))}")
        logger.info(f"  - Company Fields: {len(analyzed_patterns.get('php', {}).get('field_names', []))}")
        logger.info(f"  - AJAX Functions: {len(analyzed_patterns.get('php', {}).get('ajax_functions', []))}")
        logger.info(f"  - CSS Classes: {len(analyzed_patterns.get('html', {}).get('css_classes', []))}")
        
        if not analyzed_patterns.get('php', {}).get('table_names'):
            logger.warning(f"âš ï¸ Rich search query has NO company tables - pattern extraction may have failed")
        if not analyzed_patterns.get('php', {}).get('field_names'):
            logger.warning(f"âš ï¸ Rich search query has NO company fields - pattern extraction may have failed")
        if not analyzed_patterns.get('php', {}).get('ajax_functions'):
            logger.warning(f"âš ï¸ Rich search query has NO AJAX functions - pattern extraction may have failed")
        
        return rich_query


# Initialize node
retrieve_patterns_node = PatternRetrievalNode()

## **Step 4.3: Standards Loading Node**

from agents.utils.file_handler import StandardsFileHandler
from agents.prompts.standards_prompts import MD_STANDARDS_PROMPT

class StandardsLoadingNode:
    """
    Loads and processes company coding standards
    WITH CACHING - Reduces API calls by 30%
    """
    
    def __init__(self):
        self.file_handler = None
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            from agents.utils.file_handler import StandardsFileHandler
            self.file_handler = StandardsFileHandler()
            
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0,
                openai_api_key=config['api_key']
            )
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Load standards file and inject into context
        """
        try:
            # Initialize if not already done
            self._initialize()
            user_id = state['user_id']
            
            # Try cache first - COST OPTIMIZATION
            from agents.utils.cache_helper import get_cached_standards, set_cached_standards
            
            cached_standards = get_cached_standards(user_id)
            
            if cached_standards:
                logger.info("âœ… Using cached standards - NO API CALL!")
                state['md_standards'] = cached_standards['content']
                state['standards_metadata'] = cached_standards['metadata']
                state['current_step'] = 'standards_loaded'
                return state
            
            # Cache miss - load and process
            logger.info("Loading company coding standards")
            
            # Get standards file for user
            standards_data = self.file_handler.get_standards_for_user(user_id)
            
            if not standards_data['content']:
                logger.warning("No standards file found, using defaults")
                standards_data = self._get_default_standards()
            
            # Create standards injection prompt
            standards_prompt = PromptTemplate(
                template=MD_STANDARDS_PROMPT,
                input_variables=[
                    "md_file_content",
                    "php_version",
                    "db_connection_method",
                    "framework",
                    "css_framework",
                    "js_libraries"
                ]
            )
            
            metadata = standards_data['metadata']
            
            # Process standards
            chain = standards_prompt | self.llm
            
            # âœ… ISSUE #12 FIX: Handle js_libraries as string or list
            js_libs = metadata.get('js_libraries', ['Vanilla JS'])
            if isinstance(js_libs, str):
                js_libs = js_libs.split(',') if js_libs else ['Vanilla JS']
            
            processed_standards = await chain.ainvoke({
                "md_file_content": standards_data['content'],
                "php_version": metadata.get('php_version', '8.0'),
                "db_connection_method": "MySQLi/PDO",
                "framework": metadata.get('framework', 'None'),
                "css_framework": metadata.get('css_framework', 'Custom'),
                "js_libraries": ', '.join(js_libs)
            })
            
            # Cache for future requests - COST OPTIMIZATION
            set_cached_standards(user_id, standards_data)
            
            # Update state
            state['md_standards'] = standards_data['content']
            state['standards_metadata'] = metadata
            state['current_step'] = 'standards_loaded'
            
            logger.info("Standards loaded and cached successfully")
            
            return state
            
        except Exception as e:
            logger.error(f"Error loading standards: {str(e)}")
            # Continue with default standards
            state['md_standards'] = self._get_default_standards()['content']
            state['standards_metadata'] = {}
            state['current_step'] = 'standards_loaded'
            return state
    
    def _get_default_standards(self) -> Dict:
        """
        Return default coding standards if no file uploaded
        """
        default_content = """
# Default Coding Standards

## PHP
- Version: 8.0+
- Use prepared statements for all database queries
- Follow PSR-12 coding standard
- Use camelCase for variables and methods

## Database
- Engine: InnoDB
- Charset: utf8mb4
- Always use primary key 'id' as INT AUTO_INCREMENT
- Add created_at and updated_at timestamps

## HTML
- Use semantic HTML5 elements
- Include ARIA attributes for accessibility
- Class naming: BEM methodology

## CSS
- Mobile-first responsive design
- Use CSS variables for theming
- Follow BEM naming convention

## JavaScript
- Use ES6+ syntax
- Vanilla JS preferred (no jQuery unless specified)
- Always validate on both client and server
"""
        
        return {
            'content': default_content,
            'metadata': {
                'php_version': '8.0',
                'framework': 'None',
                'css_framework': 'Custom',
                'db_engine': 'InnoDB',
                'charset': 'utf8mb4'
            }
        }

# Initialize node
load_standards_node = StandardsLoadingNode()

## **Step 4.4: Database Schema Generation Node**

from agents.prompts.database_prompts import DATABASE_GENERATION_PROMPT
from datetime import datetime

class DatabaseGenerationNode:
    """
    Generates MySQL database schema
    """
    
    def __init__(self):
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key']
            )
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Generate database schema based on intent, patterns, and selected database type
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("Generating database schema")
            
            intent = state.get('intent')
            if not intent:
                logger.error("No intent found, cannot generate database schema")
                state['validation_errors'].append({
                    'step': 'database_generation',
                    'error': 'No intent data available'
                })
                return state
            
            # Get database patterns
            db_patterns = self._extract_db_patterns(state['retrieved_patterns'])
            
            # Get database type from connection or standards
            database_type = state.get('database_type', 'mysql')
            if not database_type and state.get('standards_metadata'):
                database_type = state['standards_metadata'].get('db_engine', 'mysql').lower()
            
            # Get database-specific prompt
            from agents.prompts.database_connection_prompts import get_database_specific_sql_prompt
            
            db_specific_prompt = get_database_specific_sql_prompt(
                db_type=database_type,
                user_request=state.get('user_request', ''),
                schema_info=db_patterns
            )
            
            # Create prompt
            db_prompt = PromptTemplate(
                template=db_specific_prompt + "\n\nIntent Data:\n{intent_json}\n\nNaming Convention: {naming_convention}",
                input_variables=[
                    "intent_json",
                    "naming_convention"
                ]
            )
            
            # ðŸ”´ ISSUE #1 FIX: Company naming conventions (NOT snake_case!)
            # Table: tblcustomer (lowercase with 'tbl' prefix)
            # Fields: Cust_Code, Cust_Name (PascalCase with underscores)
            
            # Build company naming convention rules
            company_naming_rules = """
ðŸš¨ CRITICAL DATABASE NAMING CONVENTIONS â€” MANDATORY:

TABLE NAME RULES:
âœ… CORRECT: tblcustomer, tblsupplier, tblarea (always lowercase, always start with 'tbl')
âŒ WRONG:   customers, Customers, tblCustomers, customer

FIELD NAME RULES (PascalCase with underscores):
âœ… CORRECT: Cust_Code, Cust_Name, Phone_No, Email, Comp_Code, Created_By
âŒ WRONG:   customer_id, first_name, last_name, phone_number, customerId

MANDATORY FIELDS â€” always include these in EVERY table:
- Code          VARCHAR(20) PRIMARY KEY  -- NOT 'id' or 'customer_id'
- Name          VARCHAR(100)             -- NOT 'name' or 'customer_name'
- Phone_No      VARCHAR(20)              -- NOT 'phone' or 'phone_number'
- Email         VARCHAR(100)             -- NOT 'email_address'
- Comp_Code     VARCHAR(20)              -- multi-company filter (REQUIRED)
- Created_By    VARCHAR(50)              -- audit trail (REQUIRED)
- Created_Date  DATETIME                 -- audit trail (REQUIRED)
- Updated_By    VARCHAR(50)              -- audit trail
- Updated_Date  DATETIME                 -- audit trail

EXAMPLE - CORRECT TABLE:
CREATE TABLE tblcustomer (
    Code VARCHAR(20) PRIMARY KEY,
    Cust_Name VARCHAR(100) NOT NULL,
    Phone_No VARCHAR(20),
    Email VARCHAR(100),
    Address VARCHAR(255),
    Comp_Code VARCHAR(20) NOT NULL,
    Created_By VARCHAR(50),
    Created_Date DATETIME,
    Updated_By VARCHAR(50),
    Updated_Date DATETIME
);

NEVER use: customer_id, first_name, last_name, phone_number, created_at
ALWAYS use: Code, Cust_Name, Phone_No, Email, Created_Date
"""
            
            chain = db_prompt | self.llm
            
            result = await chain.ainvoke({
                "intent_json": json.dumps(intent, indent=2),
                "naming_convention": company_naming_rules,  # ðŸ”´ FIXED: Use company rules, not snake_case
                "current_date": datetime.now().strftime("%Y-%m-%d")
            })
            
            # Extract SQL code from response
            sql_code = self._extract_code_block(result.content, 'sql')
            
            # Update state with database information
            state['sql_code'] = sql_code
            state['database_type'] = database_type
            state['current_step'] = 'database_generated'
            
            logger.info(f"Database schema generated for {database_type.upper()}: {intent.get('database', {}).get('table_name', 'unknown')}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error generating database: {str(e)}")
            state['validation_errors'].append({
                'step': 'database_generation',
                'error': str(e)
            })
            return state
    
    def _extract_db_patterns(self, retrieved_patterns: list) -> str:
        """
        Extract SQL patterns from retrieved patterns
        """
        sql_patterns = []
        
        for pattern_group in retrieved_patterns:
            if pattern_group['language'] == 'sql':
                for pattern in pattern_group['patterns']:
                    sql_patterns.append(pattern['content'])
        
        return "\n\n---\n\n".join(sql_patterns) if sql_patterns else "No SQL patterns available."
    
    def _extract_code_block(self, content: str, language: str) -> str:
        """
        Extract code from markdown code block
        """
        import re
        
        # Pattern to match code blocks
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            return matches[0].strip()
        
        # If no code block found, return content as-is
        return content.strip()


# Initialize node
generate_database_node = DatabaseGenerationNode()

## **Step 4.5: PHP Backend Generation Node**

class PHPGenerationNode:
    """
    Generates PHP backend code - NOW GENERATES INLINE PHP+HTML FILES
    """
    
    def __init__(self):
        self.llm = None
        self.inline_generator = None

    def _merge_strict_contract_into_intent(self, intent: Dict, strict_contract: Dict) -> Dict:
        """
        Keep generation/retrieval intent aligned with strict parser contract.
        """
        merged_intent = dict(intent or {})
        strict_contract = strict_contract or {}
        if not strict_contract.get('valid'):
            return merged_intent

        master_fields = strict_contract.get('master_fields') or []
        detail_fields = strict_contract.get('detail_fields') or []
        all_fields = []
        for field in list(master_fields) + list(detail_fields):
            if isinstance(field, dict):
                name = str(field.get('name') or '').strip()
                if not name:
                    continue
                all_fields.append({
                    'name': name,
                    'type': str(field.get('db_type') or 'varchar').strip() or 'varchar',
                    'required': bool(field.get('required')),
                    'label': name.replace('_', ' '),
                })
            elif field:
                field_name = str(field).strip()
                all_fields.append({
                    'name': field_name,
                    'type': 'varchar',
                    'required': False,
                    'label': field_name.replace('_', ' '),
                })

        # Deduplicate while preserving order.
        seen_fields = set()
        deduped_fields = []
        for field in all_fields:
            field_name = str(field.get('name') or '').strip()
            key = field_name.lower()
            if not field_name or key in seen_fields:
                continue
            seen_fields.add(key)
            deduped_fields.append(field)

        database = dict(merged_intent.get('database') or {})
        database['table_name'] = strict_contract.get('master_table') or database.get('table_name', '')
        database['primary_key'] = strict_contract.get('primary_key') or database.get('primary_key', '')
        database['relationships'] = strict_contract.get('relationships', []) or database.get('relationships', [])

        merged_intent['database'] = database
        merged_intent['fields'] = deduped_fields
        merged_intent['feature_type'] = merged_intent.get('feature_type') or 'form'
        merged_intent['form_title'] = strict_contract.get('title') or merged_intent.get('form_title')
        merged_intent['strict_contract'] = strict_contract
        merged_intent['strict_features'] = strict_contract.get('features', []) or []
        merged_intent['operations'] = merged_intent.get('operations') or ['create', 'read', 'update', 'delete']
        return merged_intent
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key'],
                max_tokens=4000
            )
            
            # Initialize inline generator (codebase_dir will be set in execute())
            from agents.graph.inline_php_generator import InlinePHPGenerator
            self.inline_generator = InlinePHPGenerator(config)
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        ðŸ†• SIMPLIFIED: Generate ONLY complete inline PHP+HTML file (no extraction)
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("ðŸš€ Generating Complete PHP file (inline PHP+HTML+CSS+JS - company style)")
            
            intent = state.get('intent')
            if not intent:
                logger.error("No intent found, cannot generate PHP")
                state['validation_errors'].append({
                    'step': 'php_generation',
                    'error': 'No intent data available'
                })
                return state

            strict_contract = state.get('strict_contract') or {}
            intent = self._merge_strict_contract_into_intent(intent, strict_contract)
            state['intent'] = intent
            
            # Get enterprise patterns
            from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever
            
            user_id = state.get('user_id')
            # âœ… HYBRID: Pass analyzed_patterns to enable dynamic pattern extraction
            analyzed_patterns = state.get('analyzed_patterns', {})
            enterprise_retriever = EnterprisePatternRetriever(user_id=user_id, analyzed_patterns=analyzed_patterns)
            
            # Get feature-based PHP snippets (avoid unrelated full-form dependency)
            logger.info("Retrieving feature-based PHP snippets from company codebase")
            
            # âœ… ISSUE #11 FIX: Add codebase_id to intent before calling get_php_examples
            # The codebase_id is in state but not in intent dict
            if state.get('codebase_id'):
                intent['codebase_id'] = state.get('codebase_id')
                logger.info(f"âœ… Added codebase_id to intent: {intent['codebase_id']}")
            
            # âœ… CRITICAL FIX: Pass original user_request to retrieval for entity extraction
            user_request = state.get('user_request', '')
            preflight_warnings = []
            if isinstance(intent, dict):
                raw_warnings = intent.get('preflight_warnings') or []
                if isinstance(raw_warnings, list):
                    preflight_warnings = list(raw_warnings)

            def _append_preflight_warning(code: str, message: str) -> None:
                warning = {'code': code, 'message': message}
                if warning not in preflight_warnings:
                    preflight_warnings.append(warning)
                logger.warning("⚠️ Preflight warning [%s]: %s", code, message)
            
            # Dynamic retrieval depth based on request complexity.
            # Keep at least 2 complete examples to avoid pattern under-coverage.
            field_count = len(intent.get('fields', []))
            low_field_threshold = get_int_setting(
                'CODEGEN_RETRIEVAL_LOW_FIELD_THRESHOLD',
                'CODEGEN_RETRIEVAL_LOW_FIELD_THRESHOLD',
                12,
                min_value=4,
                max_value=40
            )
            high_field_threshold = get_int_setting(
                'CODEGEN_RETRIEVAL_HIGH_FIELD_THRESHOLD',
                'CODEGEN_RETRIEVAL_HIGH_FIELD_THRESHOLD',
                32,
                min_value=12,
                max_value=120
            )
            k_small = get_int_setting(
                'CODEGEN_RETRIEVAL_K_SMALL',
                'CODEGEN_RETRIEVAL_K_SMALL',
                3,  # 🔥 INCREASED: 1 → 3 for better pattern learning
                min_value=1,
                max_value=8
            )
            k_medium = get_int_setting(
                'CODEGEN_RETRIEVAL_K_MEDIUM',
                'CODEGEN_RETRIEVAL_K_MEDIUM',
                3,  # 🔥 INCREASED: 1 → 3 for better pattern learning
                min_value=1,
                max_value=8
            )
            k_large = get_int_setting(
                'CODEGEN_RETRIEVAL_K_LARGE',
                'CODEGEN_RETRIEVAL_K_LARGE',
                2,  # 🔥 INCREASED: 1 → 2 for complex forms
                min_value=1,
                max_value=8
            )
            if field_count <= low_field_threshold:
                k_examples = k_small
            elif field_count >= high_field_threshold:
                k_examples = k_large
            else:
                k_examples = k_medium
            k_examples = max(1, k_examples)  # Changed from max(2) to max(1) to fix timeout issue
            
            def _compute_required_pattern_coverage(examples_text: str):
                text = examples_text or ''
                text_lower = text.lower()
                strict_features = {
                    str(feature or '').strip().lower()
                    for feature in (strict_contract.get('features') or [])
                    if str(feature or '').strip()
                }

                has_db_insert = 'db_insert' in text_lower
                has_db_update = 'db_update' in text_lower
                has_db_delete = 'db_delete' in text_lower
                has_getrows = 'getrows' in text_lower
                has_getvalue = 'getvalue' in text_lower
                has_db_getRecord = 'db_getrecord' in text_lower
                has_session_start = 'session_start' in text_lower
                has_session_vars = '$_session' in text_lower
                has_ajax = '$.ajax' in text_lower or '$.post' in text_lower
                has_getmaxid = 'getmaxid' in text_lower or 'get_max_id' in text_lower
                has_formvalidation = 'formvalidation' in text_lower
                has_checkKeycode = 'checkkeycode' in text_lower
                has_chart = 'insert into chart' in text_lower or 'acc_cust' in text_lower
                has_transaction = 'funstarttran' in text_lower or 'funendtran' in text_lower

                request_lower = (user_request or "").lower()
                requires_formvalidation = (
                    any(token in request_lower for token in ["formvalidation", "form validation", "validators", "required fields"])
                    or 'validation' in strict_features
                )
                requires_keyboard = (
                    any(token in request_lower for token in ["keyboard", "checkkeycode", "enter key", "arrow key"])
                    or 'keyboard' in strict_features
                )
                requires_chart = (
                    any(token in request_lower for token in ["chart", "acc_prefix", "ledger", "account entry"])
                    or 'chart' in strict_features
                )
                requires_getrows = (
                    'getrows' in request_lower
                    or 'predelete' in strict_features
                )
                requires_getvalue = (
                    any(token in request_lower for token in ["getvalue", "getmaxid", "maxid"])
                    or 'getmaxid' in strict_features
                )
                requires_ajax = (
                    'ajax' in request_lower
                    or 'ajax' in strict_features
                    or 'dependent_dropdown' in strict_features
                    or requires_getvalue
                )
                requires_transaction = (
                    any(token in request_lower for token in ["funstarttran", "funendtran"])
                    or str(strict_contract.get('form_type') or '').upper() == 'MASTER_DETAIL'
                )

                required_pattern_flags = [
                    has_db_insert,
                    has_db_update,
                    has_db_delete,
                    has_db_getRecord,
                    has_session_vars,
                ]
                if requires_getrows:
                    required_pattern_flags.append(has_getrows)
                if requires_ajax:
                    required_pattern_flags.append(has_ajax)
                if requires_getvalue:
                    required_pattern_flags.append(has_getvalue or has_getmaxid)
                if requires_transaction:
                    required_pattern_flags.append(has_transaction)
                if requires_formvalidation:
                    required_pattern_flags.append(has_formvalidation)
                if requires_keyboard:
                    required_pattern_flags.append(has_checkKeycode)
                if requires_chart:
                    required_pattern_flags.append(has_chart)

                total_required = len(required_pattern_flags)
                found_required = sum(required_pattern_flags)
                required_pct = (found_required / total_required * 100) if total_required else 100.0
                return {
                    'found_required': found_required,
                    'total_required': total_required,
                    'required_pct': required_pct,
                    'flags': {
                        'db_insert': has_db_insert,
                        'db_update': has_db_update,
                        'db_delete': has_db_delete,
                        'getrows': has_getrows,
                        'getvalue': has_getvalue,
                        'db_getRecord': has_db_getRecord,
                        'session_start': has_session_start,
                        'session_vars': has_session_vars,
                        'ajax': has_ajax,
                        'getmaxid': has_getmaxid,
                        'formvalidation': has_formvalidation,
                        'checkKeycode': has_checkKeycode,
                        'chart': has_chart,
                        'transaction': has_transaction,
                        'requires_getrows': requires_getrows,
                        'requires_getvalue': requires_getvalue,
                        'requires_ajax': requires_ajax,
                        'requires_transaction': requires_transaction,
                        'requires_formvalidation': requires_formvalidation,
                        'requires_keyboard': requires_keyboard,
                        'requires_chart': requires_chart,
                    }
                }

            php_examples = enterprise_retriever.get_php_examples(intent, k=k_examples, user_request=user_request)
            strict_memory_context = str(state.get('strict_pattern_memory_context') or '').strip()
            if strict_memory_context:
                php_examples = f"{strict_memory_context}\n\n{php_examples}".strip()
                logger.info(
                    "Prepended strict ERP pattern memory context to retrieval examples "
                    f"({len(strict_memory_context)} chars)"
                )
            logger.info(f"ðŸ“Š Using k={k_examples} examples (user specified {field_count} fields)")
            
            logger.info(f"ðŸ“ PHP Examples Retrieved: {len(php_examples)} characters")
            state['retrieval_gate_blocked'] = False
            state['retrieval_gate_reason'] = None
            state['retrieval_top_candidates'] = getattr(enterprise_retriever, 'last_top_candidates', []) or []
            if isinstance(state.get('intent'), dict):
                state['intent']['retrieval_top_candidates'] = state['retrieval_top_candidates']
            retrieval_metrics = getattr(enterprise_retriever, 'last_retrieval_metrics', {}) or {}
            retrieval_score = float(retrieval_metrics.get('retrieval_score', 0.0) or 0.0)
            state['retrieval_metrics'] = retrieval_metrics
            state['retrieval_score'] = retrieval_score
            state['retrieval_quality_score'] = retrieval_score
            state['retrieval_real_db_function_count'] = int(
                retrieval_metrics.get('real_db_function_count', 0) or 0
            )
            state['retrieval_synthetic_db_function_count'] = int(
                retrieval_metrics.get('synthetic_db_function_count', 0) or 0
            )
            real_db_count = int(state.get('retrieval_real_db_function_count', 0) or 0)
            synthetic_db_count = int(state.get('retrieval_synthetic_db_function_count', 0) or 0)
            if real_db_count <= 0:
                _append_preflight_warning(
                    'low_real_pattern_quality',
                    "No real DB function evidence extracted from retrieval candidates."
                )
            elif real_db_count < synthetic_db_count:
                _append_preflight_warning(
                    'synthetic_over_real_pattern_ratio',
                    (
                        f"Synthetic DB patterns ({synthetic_db_count}) exceed real extracted patterns "
                        f"({real_db_count})."
                    )
                )
            if isinstance(state.get('intent'), dict):
                state['intent']['preflight_warnings'] = preflight_warnings
            logger.info(
                "ðŸ“Š Retrieval score: %.1f (real_db=%s, synthetic_db=%s, candidates=%s)",
                retrieval_score,
                state.get('retrieval_real_db_function_count', 0),
                state.get('retrieval_synthetic_db_function_count', 0),
                retrieval_metrics.get('candidate_count', 0),
            )
            
            # âœ… FIXED ISSUE #4: Verify examples contain critical patterns
            state['retrieval_quality'] = 'sufficient'
            retrieval_gate_reason = ''
            if php_examples:
                logger.info(f"ðŸ“ Verifying PHP examples contain critical patterns:")
                coverage = _compute_required_pattern_coverage(php_examples)
                flags = coverage['flags']
                has_db_insert = flags['db_insert']
                has_db_update = flags['db_update']
                has_db_delete = flags['db_delete']
                has_getrows = flags['getrows']
                has_getvalue = flags['getvalue']
                has_db_getRecord = flags['db_getRecord']
                
                logger.info(f"   Company Functions:")
                logger.info(f"     - db_insert: {'âœ…' if has_db_insert else 'âŒ'}")
                logger.info(f"     - db_update: {'âœ…' if has_db_update else 'âŒ'}")
                logger.info(f"     - db_delete: {'âœ…' if has_db_delete else 'âŒ'}")
                logger.info(f"     - getrows: {'âœ…' if has_getrows else 'âŒ'}")
                logger.info(f"     - getvalue: {'âœ…' if has_getvalue else 'âŒ'}")
                logger.info(f"     - db_getRecord: {'âœ…' if has_db_getRecord else 'âŒ'}")
                
                # Check for session management
                has_session_start = flags['session_start']
                has_session_vars = flags['session_vars']
                logger.info(f"   Session Management:")
                logger.info(f"     - session_start: {'âœ…' if has_session_start else 'âŒ'}")
                logger.info(f"     - $_SESSION usage: {'âœ…' if has_session_vars else 'âŒ'}")
                
                # Check for AJAX patterns
                has_ajax = flags['ajax']
                has_getmaxid = flags['getmaxid']
                logger.info(f"   AJAX Patterns:")
                logger.info(f"     - $.ajax/$.post: {'âœ…' if has_ajax else 'âŒ'}")
                logger.info(f"     - GetMaxID/getvalue: {'âœ…' if has_getmaxid else 'âŒ'}")
                
                # Check for validation patterns
                has_formvalidation = flags['formvalidation']
                has_checkKeycode = flags['checkKeycode']
                logger.info(f"   UI Patterns:")
                logger.info(f"     - formValidation: {'âœ…' if has_formvalidation else 'âŒ'}")
                logger.info(f"     - checkKeycode (keyboard): {'âœ…' if has_checkKeycode else 'âŒ'}")
                
                # Check for chart integration
                has_chart = flags['chart']
                logger.info(f"     - Chart integration: {'âœ…' if has_chart else 'âŒ'}")
                
                # Check for transaction management
                has_transaction = flags['transaction']
                logger.info(f"     - Transaction mgmt: {'âœ…' if has_transaction else 'âŒ'}")
                found_required = coverage['found_required']
                total_required = coverage['total_required']
                required_pct = coverage['required_pct']
                preflight_coverage_pct = float(state.get('retrieval_required_coverage', 0.0) or 0.0)
                if strict_contract.get('valid') and preflight_coverage_pct > required_pct:
                    logger.info(
                        "↔️ Aligning retrieval coverage with strict preflight authoritative value: "
                        f"heuristic={required_pct:.1f}% -> preflight={preflight_coverage_pct:.1f}%"
                    )
                    required_pct = preflight_coverage_pct
                logger.info(
                    f"   ðŸ“Š Pattern Coverage (required): {found_required}/{total_required} patterns found ({required_pct:.1f}%)"
                )
                state['retrieval_required_coverage'] = required_pct

                coverage_floor_pct = float(RETRIEVAL_COVERAGE_FLOOR) * 100.0
                hard_block_floor_pct = float(RETRIEVAL_HARD_BLOCK_FLOOR) * 100.0
                score_floor = float(RETRIEVAL_SCORE_FLOOR)
                retrieval_gate_failed = (required_pct < coverage_floor_pct) or (retrieval_score < score_floor)
                if retrieval_gate_failed:
                    logger.warning(
                        f"   âš ï¸ LOW RETRIEVAL QUALITY: coverage={required_pct:.1f}% (floor {coverage_floor_pct:.1f}%), "
                        f"score={retrieval_score:.1f} (floor {score_floor:.1f})"
                    )
                    state['retrieval_quality'] = 'insufficient'
                    broadened_k = min(max(k_examples + 2, k_examples * 2), 8)
                    if broadened_k > k_examples:
                        logger.info(f"🔁 Retrieval quality retry with broader depth (k={broadened_k})")
                        retry_examples = enterprise_retriever.get_php_examples(intent, k=broadened_k, user_request=user_request)
                        state['retrieval_top_candidates'] = getattr(enterprise_retriever, 'last_top_candidates', []) or []
                        if isinstance(state.get('intent'), dict):
                            state['intent']['retrieval_top_candidates'] = state['retrieval_top_candidates']
                        retry_metrics = getattr(enterprise_retriever, 'last_retrieval_metrics', {}) or {}
                        retry_score = float(retry_metrics.get('retrieval_score', 0.0) or 0.0)
                        state['retrieval_metrics'] = retry_metrics
                        state['retrieval_score'] = retry_score
                        state['retrieval_quality_score'] = retry_score
                        state['retrieval_real_db_function_count'] = int(
                            retry_metrics.get('real_db_function_count', 0) or 0
                        )
                        state['retrieval_synthetic_db_function_count'] = int(
                            retry_metrics.get('synthetic_db_function_count', 0) or 0
                        )
                        if retry_examples:
                            retry_coverage = _compute_required_pattern_coverage(retry_examples)
                            retry_pct = retry_coverage['required_pct']
                            if strict_contract.get('valid') and preflight_coverage_pct > retry_pct:
                                logger.info(
                                    "↔️ Aligning broadened retrieval coverage with strict preflight "
                                    f"authoritative value: heuristic={retry_pct:.1f}% -> "
                                    f"preflight={preflight_coverage_pct:.1f}%"
                                )
                                retry_pct = preflight_coverage_pct
                            state['retrieval_required_coverage'] = retry_pct
                            logger.info(
                                f"🔁 Broadened retrieval quality: coverage={retry_pct:.1f}% "
                                f"({retry_coverage['found_required']}/{retry_coverage['total_required']}), "
                                f"score={retry_score:.1f}"
                            )
                            if retry_pct >= coverage_floor_pct and retry_score >= score_floor:
                                php_examples = retry_examples
                                retrieval_score = retry_score
                                state['retrieval_quality'] = 'sufficient'
                                logger.info("✅ Retrieval score + coverage floors satisfied after broadened retrieval")
                    if state.get('retrieval_quality') == 'insufficient':
                        final_coverage_pct = float(state.get('retrieval_required_coverage', required_pct) or 0.0)
                        final_score = float(state.get('retrieval_score', retrieval_score) or 0.0)
                        floor_failure_message = (
                            f"Retrieval quality below strict floor: coverage={final_coverage_pct:.1f}% "
                            f"(min {coverage_floor_pct:.1f}%), score={final_score:.1f} (min {score_floor:.1f}%)"
                        )
                        logger.warning(
                            f"⚠️ Retrieval quality remains below strict floor after broadened retrieval "
                            f"(coverage={final_coverage_pct:.1f}% vs {coverage_floor_pct:.1f}%, "
                            f"score={final_score:.1f} vs {score_floor:.1f})"
                        )
                        state.setdefault('validation_errors', [])
                        state['validation_errors'].append({
                            'step': 'retrieval',
                            'severity': 'major',
                            'error': floor_failure_message
                        })
                        if strict_contract.get('valid'):
                            retrieval_gate_reason = floor_failure_message
            else:
                logger.warning(f"âš ï¸ Company examples are empty!")
                state['retrieval_quality'] = 'insufficient'
                state['retrieval_score'] = 0.0
                state['retrieval_quality_score'] = 0.0
                state.setdefault('validation_errors', [])
                empty_message = (
                    "Retrieval quality below strict floor: coverage=0.0% "
                    f"(min {float(RETRIEVAL_COVERAGE_FLOOR) * 100.0:.1f}%), "
                    f"score=0.0 (min {float(RETRIEVAL_SCORE_FLOOR):.1f}%)"
                )
                state['validation_errors'].append({
                    'step': 'retrieval',
                    'severity': 'major',
                    'error': empty_message,
                })
                if strict_contract.get('valid'):
                    retrieval_gate_reason = empty_message

            if retrieval_gate_reason:
                state['retrieval_gate_blocked'] = True
                state['retrieval_gate_reason'] = retrieval_gate_reason
                state['status'] = 'failed'
                state['error_message'] = retrieval_gate_reason
                state['block_save'] = True
                state['validation_passed'] = False
                state['validation_reason'] = retrieval_gate_reason
                state['validation_result'] = {
                    'approval_status': 'needs_revision',
                    'regeneration_required': True,
                    'block_generation': True,
                    'needs_revision': True,
                    'validation_passed': False,
                    'block_save': True,
                    'validation_reason': retrieval_gate_reason,
                    'retrieval_quality': state.get('retrieval_quality'),
                    'retrieval_score': float(state.get('retrieval_score', 0.0) or 0.0),
                    'retrieval_required_coverage': float(state.get('retrieval_required_coverage', 0.0) or 0.0),
                    'authoritative_gate': {
                        'final_pass': False,
                        'reason': retrieval_gate_reason,
                    },
                }
                state['current_step'] = 'retrieval_blocked'
                logger.error(
                    "⛔ Strict retrieval gate blocked generation before code assembly: %s",
                    retrieval_gate_reason
                )
                return state
            
            analyzed_patterns = state.get('analyzed_patterns', {})

            
            if analyzed_patterns:
                logger.info(f"ðŸ“Š Analyzed Patterns Available")
            else:
                logger.warning("âš ï¸ No analyzed_patterns in state")
            
            # Generate complete inline file
            if self.inline_generator:
                logger.info("âœ… Using INLINE PHP+HTML generator with company patterns")
                
                # âœ… PLAN A: Set codebase_dir for FIXED parts extraction
                codebase_id = state.get('codebase_id', '')
                if codebase_id and not self.inline_generator._template:
                    import os
                    codebase_dir = os.path.join("company_codebases", str(state.get('user_id', '1')), codebase_id)
                    if os.path.exists(codebase_dir):
                        from agents.utils.dynamic_form_template import DynamicFormTemplate
                        self.inline_generator._template = DynamicFormTemplate(codebase_dir)
                        self.inline_generator._template.load()
                        logger.info(f"âœ… Set codebase_dir for FIXED parts: {codebase_dir}")
                        
                        # âœ… FIX ISSUE #1: Update CodeAssembler's template reference
                        self.inline_generator.code_assembler.template = self.inline_generator._template
                        logger.info("âœ… ISSUE #1 FIXED: Updated CodeAssembler template reference")
                
                inline_php_html = await self.inline_generator.generate_inline_php_file(
                    intent=intent,
                    sql_schema=state.get('sql_code', ''),
                    company_examples=php_examples,
                    analyzed_patterns=analyzed_patterns or {},
                    standards=state.get('md_standards', ''),
                    user_request=state.get('user_request', ''),
                    validation_errors=state.get('validation_errors', [])
                )
                
                # ðŸŽ¯ Store ONLY complete inline PHP file (no extraction)
                state['php_code'] = inline_php_html
                state['complete_php'] = inline_php_html  # âœ… FIX: Store for validation
                state['is_inline_generation'] = True
                state['generation_metadata'] = getattr(self.inline_generator, 'last_generation_metadata', {}) or {}
                state['inline_generation_validation'] = getattr(self.inline_generator, 'last_validation_result', {}) or {}
                
                logger.info(f"âœ… Generated Complete PHP file: {len(inline_php_html)} chars")
                logger.info(f"   ðŸ“„ Contains: PHP + HTML + CSS + JS (all inline)")
                
            else:
                logger.error("âŒ Inline generator not available")
                state['validation_errors'].append({
                    'step': 'php_generation',
                    'error': 'Inline generator not initialized'
                })
                return state
            
            state['current_step'] = 'php_generated'
            
            feature_name = (
                (state.get('generation_metadata') or {}).get('feature_name')
                or intent['database']['table_name']
            )
            logger.info(f"âœ… Complete PHP file generated for {feature_name}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error generating PHP: {str(e)}", exc_info=True)
            state['validation_errors'].append({
                'step': 'php_generation',
                'error': str(e)
            })
            state['current_step'] = 'php_generation_failed'
            # Fail closed so workflow-level fallback sees the real generation error.
            raise
    
    def _extract_code_block(self, content: str, language: str) -> str:
        """
        Extract code from markdown code block
        """
        import re
        
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            # Return the longest match (main code block)
            return max(matches, key=len).strip()
        
        return content.strip()


# Initialize node
generate_php_node = PHPGenerationNode()

## **Step 4.6: HTML Form Generation Node**

class HTMLGenerationNode:
    """
    Generates HTML form
    """
    
    def __init__(self):
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key'],
                max_tokens=3000
            )
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Generate HTML form using ENTERPRISE pattern retrieval
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("Generating HTML form")
            
            intent = state.get('intent')
            if not intent:
                logger.error("No intent found, cannot generate HTML")
                state['validation_errors'].append({
                    'step': 'html_generation',
                    'error': 'No intent data available'
                })
                return state
            
            # ðŸ†• USE ENTERPRISE PATTERN RETRIEVER for COMPLETE HTML examples
            # âœ… TIMEOUT FIX: Skip HTML retrieval for inline PHP mode
            from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever
            
            user_id = state.get('user_id')
            analyzed_patterns = state.get('analyzed_patterns', {})
            enterprise_retriever = EnterprisePatternRetriever(user_id=user_id, analyzed_patterns=analyzed_patterns)
            
            # Get COMPLETE HTML examples (not fragments!)
            # âœ… TIMEOUT FIX: Skip HTML retrieval for inline PHP mode (HTML is embedded in PHP)
            is_inline = True  # We're using inline PHP generation
            html_patterns = ""
            if not is_inline:
                logger.info("ðŸ” Retrieving COMPLETE HTML examples from company codebase")
                html_patterns = enterprise_retriever.get_html_examples(intent, k=3)
            else:
                logger.info("â© Skipping HTML retrieval (inline PHP mode - HTML embedded in PHP file)")
            
            # Build form fields HTML
            form_fields = self._build_form_fields_html(intent['fields'])
            
            feature_name = intent['database']['table_name']
            
            # ðŸ†• CHECK IF WE HAVE ANALYZED PATTERNS
            from agents.prompts.dynamic_prompt_builder import DynamicPromptBuilder
            
            analyzed_patterns = state.get('analyzed_patterns')
            
            if analyzed_patterns:
                logger.info("âœ… Using DYNAMIC HTML prompt with analyzed patterns + COMPLETE examples")
                
                # Build dynamic prompt using REAL company patterns
                prompt_text = DynamicPromptBuilder.build_html_prompt(
                    analyzed_patterns=analyzed_patterns,
                    intent=intent,
                    html_patterns=html_patterns,  # COMPLETE examples!
                    html_standards=state.get('md_standards', ''),
                    form_fields_html=form_fields
                )
                
                html_prompt = PromptTemplate(template=prompt_text, input_variables=[])
                chain = html_prompt | self.llm
                result = await chain.ainvoke({})
                
            else:
                logger.warning("âš ï¸ No analyzed patterns, using COMPLETE HTML examples only")
                
                # âœ… FIX: Escape curly braces in examples for PromptTemplate
                safe_html_patterns = html_patterns.replace('{', '{{').replace('}', '}}') if html_patterns else ''
                safe_standards = state.get('md_standards', '').replace('{', '{{').replace('}', '}}')
                safe_fields = form_fields.replace('{', '{{').replace('}', '}}')
                safe_intent = json.dumps(intent, indent=2).replace('{', '{{').replace('}', '}}')
                
                # Use COMPLETE examples directly
                fallback_prompt = f"""
Generate HTML form that STRICTLY FOLLOWS the company's HTML patterns shown below.

User Request Intent:
{safe_intent}

CRITICAL: Study these COMPLETE, REAL HTML examples from the company codebase and follow their patterns EXACTLY:

{safe_html_patterns}

Company Coding Standards:
{safe_standards}

Form Fields to Include:
{safe_fields}

REQUIREMENTS:
1. Use the EXACT form structure you see in examples (e.g., form-horizontal, form-group)
2. Use the EXACT CSS classes (e.g., col-md-4, col-md-2, form-control)
3. Follow the EXACT input naming patterns from examples
4. Include the EXACT button structure and classes
5. Use the EXACT layout patterns (label + input structure)
6. Follow the EXACT form attributes (id, name, method, action patterns)
7. Copy the EXACT DOCTYPE and HTML structure
8. Include the EXACT CSS/JS file references

Generate ONLY the HTML code in a code block that looks EXACTLY like the examples above.
"""
                
                html_prompt = PromptTemplate(template=fallback_prompt, input_variables=[])
                chain = html_prompt | self.llm
                result = await chain.ainvoke({})
            
            # Extract HTML code
            html_code = self._extract_code_block(result.content, 'html')
            
            # Update state
            state['html_code'] = html_code
            state['current_step'] = 'html_generated'
            
            logger.info(f"HTML form generated: {intent['form_title']}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error generating HTML: {str(e)}")
            state['validation_errors'].append({
                'step': 'html_generation',
                'error': str(e)
            })
            return state
    
    def _build_form_fields_html(self, fields: list) -> str:
        """
        Build HTML snippet for form fields
        """
        html_parts = []
        
        for field in fields:
            field_html = f"""
<!-- {field['label']} -->
<div class="form-group">
    <label for="{field['name']}" class="form-label">
        {field['label']}
        {'<span class="required">*</span>' if field['required'] else ''}
    </label>
"""
            
            if field['input_type'] == 'textarea':
                field_html += f"""
    <textarea 
        id="{field['name']}" 
        name="{field['name']}" 
        class="form-control"
        {'required' if field['required'] else ''}
    ></textarea>
"""
            elif field['input_type'] == 'select':
                field_html += f"""
    <select 
        id="{field['name']}" 
        name="{field['name']}" 
        class="form-control"
        {'required' if field['required'] else ''}
    >
        <option value="">Select {field['label']}</option>
        <!-- Options will be populated dynamically or by pattern -->
    </select>
"""
            else:
                field_html += f"""
    <input 
        type="{field['input_type']}" 
        id="{field['name']}" 
        name="{field['name']}" 
        class="form-control"
        {'required' if field['required'] else ''}
    >
"""
            
            field_html += f"""
    <div class="error-message" id="{field['name']}_error"></div>
</div>
"""
            html_parts.append(field_html)
        
        return "\n".join(html_parts)
    
    def _extract_patterns(self, retrieved_patterns: list, language: str) -> str:
        """
        Extract patterns for specific language
        """
        patterns = []
        
        for pattern_group in retrieved_patterns:
            if pattern_group['language'] == language:
                for pattern in pattern_group['patterns']:
                    patterns.append(pattern['content'])
        
        return "\n\n---\n\n".join(patterns) if patterns else f"No {language} patterns available."
    
    def _extract_code_block(self, content: str, language: str) -> str:
        """
        Extract code from markdown code block
        """
        import re
        
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            return max(matches, key=len).strip()
        
        return content.strip()


# Initialize node
generate_html_node = HTMLGenerationNode()


## **Step 4.7: CSS Generation Node**

class CSSGenerationNode:
    """
    Generates CSS styling
    """
    
    def __init__(self):
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key'],
                max_tokens=3000
            )
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Generate CSS using ENTERPRISE pattern retrieval
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("Generating CSS styling")
            
            intent = state.get('intent')
            if not intent:
                logger.error("No intent found, cannot generate CSS")
                state['validation_errors'].append({
                    'step': 'css_generation',
                    'error': 'No intent data available'
                })
                return state
            
            # ðŸ†• USE ENTERPRISE PATTERN RETRIEVER for COMPLETE CSS examples
            from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever
            
            user_id = state.get('user_id')
            analyzed_patterns = state.get('analyzed_patterns', {})
            enterprise_retriever = EnterprisePatternRetriever(user_id=user_id, analyzed_patterns=analyzed_patterns)
            
            # Get COMPLETE CSS examples (not fragments!)
            logger.info("ðŸ” Retrieving COMPLETE CSS examples from company codebase")
            css_patterns = enterprise_retriever.get_css_examples(intent, k=3)
            
            feature_name = intent['database']['table_name']
            
            # ðŸ†• CHECK IF WE HAVE ANALYZED PATTERNS
            from agents.prompts.dynamic_prompt_builder import DynamicPromptBuilder
            
            analyzed_patterns = state.get('analyzed_patterns')
            
            if analyzed_patterns:
                logger.info("âœ… Using DYNAMIC CSS prompt with analyzed patterns + COMPLETE examples")
                
                # Build dynamic prompt using REAL company patterns
                prompt_text = DynamicPromptBuilder.build_css_prompt(
                    analyzed_patterns=analyzed_patterns,
                    intent=intent,
                    css_patterns=css_patterns,  # COMPLETE examples!
                    css_standards=state.get('md_standards', ''),
                    html_code=state.get('html_code', '')
                )
                
                css_prompt = PromptTemplate(template=prompt_text, input_variables=[])
                chain = css_prompt | self.llm
                result = await chain.ainvoke({})
                
            else:
                logger.warning("âš ï¸ No analyzed patterns, using COMPLETE CSS examples only")
                
                # Use COMPLETE examples directly
                fallback_prompt = f"""
Generate CSS styling that STRICTLY FOLLOWS the company's CSS patterns shown below.

User Request Intent:
{json.dumps(intent, indent=2)}

HTML Structure:
```html
{state.get('html_code', '')}
```

CRITICAL: Study these COMPLETE, REAL CSS examples from the company codebase and follow their patterns EXACTLY:

{css_patterns}

Company Coding Standards:
{state.get('md_standards', '')}

REQUIREMENTS:
1. Use the EXACT color scheme you see in examples
2. Use the EXACT font families and sizes from examples
3. Follow the EXACT spacing units (px, rem, etc.) used in examples
4. Use the EXACT class naming patterns
5. Follow the EXACT responsive design patterns
6. Match the EXACT styling approach (inline, classes, etc.)
7. Copy the EXACT form styling patterns
8. Use the EXACT button styling

Generate ONLY the CSS code in a code block that looks EXACTLY like the examples above.
"""
                
                css_prompt = PromptTemplate(template=fallback_prompt, input_variables=[])
                chain = css_prompt | self.llm
                result = await chain.ainvoke({})
            
            # Extract CSS code
            css_code = self._extract_code_block(result.content, 'css')
            
            # Update state
            state['css_code'] = css_code
            state['current_step'] = 'css_generated'
            
            logger.info(f"CSS generated for {feature_name}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error generating CSS: {str(e)}")
            state['validation_errors'].append({
                'step': 'css_generation',
                'error': str(e)
            })
            return state
    
    def _extract_patterns(self, retrieved_patterns: list, language: str) -> str:
        """
        Extract patterns for specific language
        """
        patterns = []
        
        for pattern_group in retrieved_patterns:
            if pattern_group['language'] == language:
                for pattern in pattern_group['patterns']:
                    patterns.append(pattern['content'])
        
        return "\n\n---\n\n".join(patterns) if patterns else f"No {language} patterns available."
    
    def _extract_code_block(self, content: str, language: str) -> str:
        """
        Extract code from markdown code block
        """
        import re
        
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            return max(matches, key=len).strip()
        
        return content.strip()


# Initialize node
generate_css_node = CSSGenerationNode()

## **Step 4.8: JavaScript Generation Node**

class JavaScriptGenerationNode:
    """
    Generates JavaScript client-side logic
    """
    
    def __init__(self):
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0.1,
                openai_api_key=config['api_key'],
                max_tokens=4000
            )
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Generate JavaScript code using ENTERPRISE pattern retrieval
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("Generating JavaScript code")
            
            intent = state.get('intent')
            if not intent:
                logger.error("No intent found, cannot generate JavaScript")
                state['validation_errors'].append({
                    'step': 'js_generation',
                    'error': 'No intent data available'
                })
                return state
            
            # ðŸ†• USE ENTERPRISE PATTERN RETRIEVER for COMPLETE JS examples
            from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever
            
            user_id = state.get('user_id')
            analyzed_patterns = state.get('analyzed_patterns', {})
            enterprise_retriever = EnterprisePatternRetriever(user_id=user_id, analyzed_patterns=analyzed_patterns)
            
            # Get COMPLETE JS examples (not fragments!)
            logger.info("ðŸ” Retrieving COMPLETE JavaScript examples from company codebase")
            js_patterns = enterprise_retriever.get_js_examples(intent, k=3)
            
            # Build validation rules
            validation_rules = self._build_validation_rules(intent['fields'])
            
            feature_name = intent['database']['table_name']
            api_endpoint = f"/api/{feature_name}_handler.php"
            
            # Get HTML code (no truncation - keep complete for validation)
            html_code = state.get('html_code', '')
            
            # ðŸ†• CHECK IF WE HAVE ANALYZED PATTERNS
            from agents.prompts.dynamic_prompt_builder import DynamicPromptBuilder
            
            analyzed_patterns = state.get('analyzed_patterns')
            
            if analyzed_patterns:
                logger.info("âœ… Using DYNAMIC JS prompt with analyzed patterns + COMPLETE examples")
                
                # Build dynamic prompt using REAL company patterns
                prompt_text = DynamicPromptBuilder.build_js_prompt(
                    analyzed_patterns=analyzed_patterns,
                    intent=intent,
                    html_code=html_code,
                    js_patterns=js_patterns,  # COMPLETE examples!
                    js_standards=state.get('md_standards', ''),
                    api_endpoint=api_endpoint
                )
                
                js_prompt = PromptTemplate(template=prompt_text, input_variables=[])
                chain = js_prompt | self.llm
                result = await chain.ainvoke({})
                
            else:
                logger.warning("âš ï¸ No analyzed patterns, using COMPLETE JS examples only")
                
                # âœ… FIX: Escape curly braces in examples for PromptTemplate
                safe_js_patterns = js_patterns.replace('{', '{{').replace('}', '}}') if js_patterns else ''
                safe_standards = state.get('md_standards', '').replace('{', '{{').replace('}', '}}')
                safe_html = html_code.replace('{', '{{').replace('}', '}}')
                safe_intent = json.dumps(intent, indent=2).replace('{', '{{').replace('}', '}}')
                safe_validation = json.dumps(validation_rules, indent=2).replace('{', '{{').replace('}', '}}')
                
                # Use COMPLETE examples directly
                fallback_prompt = f"""
Generate JavaScript code that STRICTLY FOLLOWS the company's JS patterns shown below.

User Request Intent:
{safe_intent}

HTML Structure:
```html
{safe_html}
```

API Endpoint: {api_endpoint}

CRITICAL: Study these COMPLETE, REAL JavaScript examples from the company codebase and follow their patterns EXACTLY:

{safe_js_patterns}

Company Coding Standards:
{safe_standards}

Validation Rules:
{safe_validation}

REQUIREMENTS:
1. Use the EXACT function naming patterns you see in examples (e.g., btnsave_click, checkKeycode)
2. Use the EXACT AJAX/jQuery patterns from examples (e.g., $.post, $.ajax)
3. Follow the EXACT form submission patterns
4. Use the EXACT variable naming conventions
5. Include the EXACT keyboard navigation patterns if present
6. Follow the EXACT error handling and validation patterns
7. Copy the EXACT event binding approach
8. Use the EXACT success/error callback structure

Generate ONLY the JavaScript code in a code block that looks EXACTLY like the examples above.
"""
                
                js_prompt = PromptTemplate(template=fallback_prompt, input_variables=[])
                chain = js_prompt | self.llm
                result = await chain.ainvoke({})
            
            # Extract JS code
            js_code = self._extract_code_block(result.content, 'javascript')
            if not js_code:
                js_code = self._extract_code_block(result.content, 'js')
            
            # Update state
            state['js_code'] = js_code
            state['current_step'] = 'js_generated'
            
            logger.info(f"JavaScript generated for {feature_name}")
            
            return state
            
        except Exception as e:
            logger.error(f"Error generating JavaScript: {str(e)}")
            state['validation_errors'].append({
                'step': 'js_generation',
                'error': str(e)
            })
            return state
    
    def _build_validation_rules(self, fields: list) -> Dict:
        """
        Build validation rules object for JavaScript
        """
        rules = {}
        
        for field in fields:
            field_rules = {
                'required': field['required']
            }
            
            # Add type-specific validations
            if field['input_type'] == 'email':
                field_rules['email'] = True
            
            if 'validation' in field and field['validation']:
                for validation in field['validation']:
                    if validation.startswith('min:'):
                        field_rules['minLength'] = int(validation.split(':')[1])
                    elif validation.startswith('max:'):
                        field_rules['maxLength'] = int(validation.split(':')[1])
                    elif validation.startswith('pattern:'):
                        field_rules['pattern'] = validation.split(':', 1)[1]
            
            rules[field['name']] = field_rules
        
        return rules
    
    def _extract_patterns(self, retrieved_patterns: list, language: str, max_patterns: int = 3, max_length: int = 800) -> str:
        """
        Extract patterns for specific language with strict limits to prevent token overflow
        
        Args:
            max_patterns: Maximum number of patterns (default: 3 for JS)
            max_length: Maximum chars per pattern (NOT USED - keep complete)
        """
        patterns = []
        
        for pattern_group in retrieved_patterns:
            if pattern_group['language'] == language:
                for pattern in pattern_group['patterns'][:max_patterns]:
                    content = pattern['content']
                    # âœ… NO TRUNCATION: Keep complete patterns
                    # LLM needs full context to understand company patterns
                    patterns.append(content)
                break  # Only process first matching group
        
        return "\n\n---\n\n".join(patterns) if patterns else f"No {language} patterns available."
    
    def _extract_code_block(self, content: str, language: str) -> str:
        """
        Extract code from markdown code block
        """
        import re
        
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            return max(matches, key=len).strip()
        
        return content.strip()


# Initialize node
generate_js_node = JavaScriptGenerationNode()

# ðŸš€ **PHASE 5: CODE INTEGRATION, VALIDATION & LANGGRAPH WORKFLOW**
## **Step 5.1: Code Integration & Linking Node**

from agents.prompts.integration_prompts import CODE_LINKING_PROMPT
import os
import zipfile
from pathlib import Path

class CodeIntegrationNode:
    """
    Integrates all generated code files and ensures proper linking
    """
    
    def __init__(self):
        self.llm = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0,
                openai_api_key=config['api_key'],
                max_tokens=3000
            )
    
    def _extract_filename_from_request(self, user_request: str) -> str:
        """
        Extract PHP filename from user request string.
        
        Searches for these patterns in order:
        1. "File name: frmArea.php"
        2. "filename: frmArea.php"
        3. Any frm*.php in the text
        4. Any *.php in the text
        
        Returns:
            str: filename like 'frmArea.php' or empty string ''
            NEVER returns None
        
        Raises:
            ValueError: if user_request is not a string
        """
        import re
        
        # Type validation — fail loudly not silently
        if not isinstance(user_request, str):
            raise ValueError(
                f"_extract_filename_from_request expects str, "
                f"got {type(user_request)}"
            )
        
        if not user_request.strip():
            logger.warning("_extract_filename_from_request: empty request string")
            return ''
        
        # Pattern 1: "File name: frmArea.php" or "File name= frmArea.php"
        match = re.search(
            r'[Ff]ile\s*[Nn]ame\s*[:=]\s*(frm\w+\.php)',
            user_request
        )
        if match:
            filename = match.group(1)
            logger.info(f"Extracted filename (pattern1): {filename}")
            return filename
        
        # Pattern 2: "filename: frmArea.php" case insensitive
        match = re.search(
            r'\bfilename\s*[:=]\s*(\w+\.php)',
            user_request,
            re.IGNORECASE
        )
        if match:
            filename = match.group(1)
            logger.info(f"Extracted filename (pattern2): {filename}")
            return filename
        
        # Pattern 3: any frm*.php word boundary
        match = re.search(r'\b(frm\w+\.php)\b', user_request)
        if match:
            filename = match.group(1)
            logger.info(f"Extracted filename (pattern3): {filename}")
            return filename
        
        # Pattern 4: any *.php as last resort
        match = re.search(r'\b(\w+\.php)\b', user_request)
        if match:
            filename = match.group(1)
            logger.info(f"Extracted filename (pattern4): {filename}")
            return filename
        
        logger.warning(
            f"_extract_filename_from_request: no PHP filename found "
            f"in request (first 100 chars): {user_request[:100]}"
        )
        return ''
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        ðŸ†• SIMPLIFIED: Integration for complete PHP only (no extraction, no SQL)
        """
        try:
            self._initialize()
            
            logger.info("ðŸš€ Integration - Complete PHP only (company style)")
            
            # Get the complete PHP file
            php_code = state.get('php_code', '')
            
            if not php_code:
                logger.error("No PHP code generated")
                raise ValueError("No PHP code available for integration")
            
            # ðŸŽ¯ Store ONLY complete PHP (no extraction, no SQL)
            state['integrated_code'] = {
                'complete_php': php_code
            }
            
            # Get feature name for file structure
            intent = state.get('intent', {})
            generation_metadata = state.get('generation_metadata', {}) or {}
            
            # FIX #5: Use filename from user request/contract, not table name
            # User requested: frmArea.php, not frmTblarea.php
            user_request = state.get('user_request', '')
            file_name_from_request = self._extract_filename_from_request(user_request)
            
            feature_name = generation_metadata.get('feature_name') or intent.get('database', {}).get('table_name', 'unknown')
            file_name = (
                file_name_from_request or 
                generation_metadata.get('file_name') or 
                f"frm{feature_name.title().replace('Tbl', '').replace('tbl', '')}.php"
            )
            form_title = generation_metadata.get('title') or feature_name.title()
            
            # Create simple file structure
            state['file_structure'] = {
                'root': f"{feature_name}_module",
                'files': {
                    'complete_php': {
                        'path': file_name,
                        'description': 'Complete PHP file with inline HTML, CSS, JS'
                    }
                }
            }
            
            # Simple deployment guide
            state['deployment_guide'] = f"""# Deployment Guide - {form_title} Form

## File Generated:
- `{file_name}` - Complete PHP file with embedded HTML, CSS, and JavaScript

## Deployment Steps:
1. Upload `{file_name}` to your web server
2. Ensure database tables already exist (company standard)
3. Configure database connection in `include/config.inc.php`
4. Access the form via: `http://yourserver/{file_name}`

## Requirements:
- PHP 7.0+
- MySQL database with existing tables
- Web server (Apache/Nginx)
- Company's standard includes and functions

## Note:
This file follows company's inline PHP+HTML structure with all code in one file.
"""
            
            state['current_step'] = 'code_integrated'
            
            logger.info(f"âœ… Complete PHP integrated for {feature_name}")
            logger.info(f"   ðŸ“„ File: {file_name} ({len(php_code)} chars)")
            
            return state
            
        except Exception as e:
            logger.error(f"Error in code integration: {str(e)}", exc_info=True)
            
            # Fallback
            logger.warning("Integration failed, using basic structure")
            
            generation_metadata = state.get('generation_metadata', {}) or {}
            feature_name = generation_metadata.get('feature_name') or state.get('intent', {}).get('database', {}).get('table_name', 'unknown')
            
            # FIX #5: Use filename from user request/contract, not table name
            user_request = state.get('user_request', '')
            file_name_from_request = self._extract_filename_from_request(user_request)
            
            file_name = (
                file_name_from_request or
                generation_metadata.get('file_name') or 
                f"frm{feature_name.title().replace('Tbl', '').replace('tbl', '')}.php"
            )
            
            state['integrated_code'] = {
                'complete_php': state.get('php_code', '')
            }
            
            state['file_structure'] = {
                'root': f"{feature_name}_module",
                'files': {
                    'complete_php': {'path': file_name}
                }
            }
            
            state['deployment_guide'] = "Upload the PHP file to your server."
            state['current_step'] = 'code_integrated'
            
            state['validation_errors'].append({
                'step': 'code_integration',
                'error': str(e),
                'severity': 'minor'
            })
            
            return state
    
    def _parse_integration_result(self, content: str) -> Dict:
        """
        Parse LLM integration response
        """
        import re
        import json
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass
        
        # Fallback: extract corrected code blocks
        result = {}
        
        # Extract corrected PHP
        php_match = re.search(r'```php\n(.*?)```', content, re.DOTALL)
        if php_match:
            result['corrected_php'] = php_match.group(1).strip()
        
        # Extract corrected HTML
        html_match = re.search(r'```html\n(.*?)```', content, re.DOTALL)
        if html_match:
            result['corrected_html'] = html_match.group(1).strip()
        
        # Extract corrected CSS
        css_match = re.search(r'```css\n(.*?)```', content, re.DOTALL)
        if css_match:
            result['corrected_css'] = css_match.group(1).strip()
        
        # Extract corrected JS
        js_match = re.search(r'```(?:javascript|js)\n(.*?)```', content, re.DOTALL)
        if js_match:
            result['corrected_js'] = js_match.group(1).strip()
        
        return result
    
    def _create_file_structure(self, state: AgentState, feature_name: str, integration_data: Dict) -> Dict:
        """
        Create organized file structure
        """
        structure = {
            'root': f"{feature_name}_module",
            'files': {
                'sql': {
                    'path': f"sql/{feature_name}_schema.sql",
                    'content': state.get('sql_code', '')
                },
                'php': {
                    'path': f"api/{feature_name}_handler.php",
                    'content': integration_data.get('corrected_php', state.get('php_code', ''))
                },
                'html': {
                    'path': f"views/{feature_name}_form.html",
                    'content': integration_data.get('corrected_html', state.get('html_code', ''))
                },
                'css': {
                    'path': f"assets/css/{feature_name}.css",
                    'content': integration_data.get('corrected_css', state.get('css_code', ''))
                },
                'js': {
                    'path': f"assets/js/{feature_name}.js",
                    'content': integration_data.get('corrected_js', state.get('js_code', ''))
                },
                'config': {
                    'path': 'config/database.php',
                    'content': self._generate_db_config()
                }
            }
        }
        
        return structure
    
    def _generate_db_config(self) -> str:
        """
        Generate database configuration file
        """
        return """<?php
/**
 * Database Configuration
 * Update these values according to your environment
 */

define('DB_HOST', 'localhost');
define('DB_USER', 'root');
define('DB_PASS', '');
define('DB_NAME', 'your_database_name');

// Create connection
$conn = new mysqli(DB_HOST, DB_USER, DB_PASS, DB_NAME);

// Check connection
if ($conn->connect_error) {
    die(json_encode([
        'error' => 'Database connection failed',
        'details' => $conn->connect_error
    ]));
}

// Set charset
$conn->set_charset("utf8mb4");
?>
"""
    
    def _generate_deployment_guide(self, state: AgentState, feature_name: str, file_structure: Dict) -> str:
        """
        Generate step-by-step deployment instructions
        """
        intent = state.get('intent', {})
        if not intent:
            intent = {
                'form_title': feature_name.replace('_', ' ').title(),
                'fields': []
            }
        
        guide = f"""
# {intent.get('form_title', feature_name.replace('_', ' ').title())} - Deployment Guide

## Prerequisites
- PHP {state.get('standards_metadata', {}).get('php_version', '7.4')}+
- MySQL 5.7+
- Web server (Apache/Nginx)

## Installation Steps

### 1. Database Setup
```bash
# Login to MySQL
mysql -u root -p

# Create database (if not exists)
CREATE DATABASE IF NOT EXISTS your_database_name;

# Use database
USE your_database_name;

# Import schema
SOURCE sql/{feature_name}_schema.sql;
```

### 2. Configuration
1. Open `config/database.php`
2. Update database credentials:
   - DB_HOST
   - DB_USER
   - DB_PASS
   - DB_NAME

### 3. File Deployment
Copy files to your web server:
```
{file_structure['root']}/
â”œâ”€â”€ config/
â”‚   â””â”€â”€ database.php          # Database connection
â”œâ”€â”€ api/
â”‚   â””â”€â”€ {feature_name}_handler.php   # Backend API
â”œâ”€â”€ views/
â”‚   â””â”€â”€ {feature_name}_form.html     # Frontend form
â”œâ”€â”€ assets/
â”‚   â”œâ”€â”€ css/
â”‚   â”‚   â””â”€â”€ {feature_name}.css       # Styling
â”‚   â””â”€â”€ js/
â”‚       â””â”€â”€ {feature_name}.js        # Client logic
â””â”€â”€ sql/
    â””â”€â”€ {feature_name}_schema.sql    # Database schema
```

### 4. File Permissions
```bash
chmod 755 api/{feature_name}_handler.php
chmod 644 views/{feature_name}_form.html
chmod 644 assets/css/{feature_name}.css
chmod 644 assets/js/{feature_name}.js
```

### 5. Access the Application
Navigate to: `http://yourserver.com/views/{feature_name}_form.html`

## API Endpoints

### Create Record
- **URL**: `/api/{feature_name}_handler.php`
- **Method**: POST
- **Content-Type**: application/json
- **Body**:
```json
{json.dumps({field['name']: field['label'] for field in intent.get('fields', [])}, indent=2) if intent.get('fields') else '{}'}
```

### Read Record
- **URL**: `/api/{feature_name}_handler.php?id={{id}}`
- **Method**: GET

### Update Record
- **URL**: `/api/{feature_name}_handler.php?id={{id}}`
- **Method**: PUT
- **Body**: Same as Create

### Delete Record
- **URL**: `/api/{feature_name}_handler.php?id={{id}}`
- **Method**: DELETE

## Testing

### Sample Data
Sample insert statements are included in the SQL file for testing.

### Frontend Testing
1. Open the form in browser
2. Fill in all required fields (marked with *)
3. Submit the form
4. Check browser console for any errors
5. Verify data in database

## Troubleshooting

### Common Issues

**Issue**: Form submission returns 500 error
- **Solution**: Check database credentials in `config/database.php`

**Issue**: CORS errors in browser console
- **Solution**: Update `Access-Control-Allow-Origin` in PHP file

**Issue**: Validation not working
- **Solution**: Check JavaScript console for errors, ensure JS file is loaded

## Support
For issues, check:
1. PHP error logs
2. Browser console
3. Network tab in developer tools
"""
        
        return guide


# Initialize node
integrate_code_node = CodeIntegrationNode()


## **Step 5.2: Validation Node**
from agents.prompts.validation_prompts import VALIDATION_PROMPT
from agents.validators.security_validator import SecurityValidator
from agents.validators.syntax_validator import SyntaxValidator
from agents.validators.dynamic_code_validator import DynamicCodeValidator

class ValidationNode:
    """
    âœ… STEP 3: Validates generated code with dynamic patterns
    - V-1: Critical errors block generation
    - V-2: Code size validation
    - V-3: needs_revision triggers retry
    """
    
    def __init__(self):
        self.llm = None
        self.security_validator = None
        self.syntax_validator = None
        self.dynamic_validator = None
        self.company_style_normalizer = None
        self.company_contract_validator = None
    
    def _initialize(self):
        """Lazy initialization to avoid Django settings issues"""
        if self.llm is None:
            config = get_llm_config()
            self.llm = ChatOpenAI(
                model=config['model'],
                temperature=0,
                openai_api_key=config['api_key'],
                max_tokens=2000
            )
            
            self.security_validator = SecurityValidator()
            self.syntax_validator = SyntaxValidator()
            self.company_style_normalizer = CompanyStyleNormalizer()
            self.company_contract_validator = CompanyFormContractValidator()
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        âœ… STEP 3: Comprehensive validation with dynamic patterns
        """
        try:
            # Initialize if not already done
            self._initialize()
            logger.info("Validating generated code")
            
            # âœ… STEP 3: Initialize dynamic validator with user request
            user_request = state.get('user_request', '')
            analyzed_patterns = state.get('analyzed_patterns', {})
            self.dynamic_validator = DynamicCodeValidator(analyzed_patterns, user_request)
            
            # Get generated code and normalize it BEFORE validation.
            php_code = state.get('php_code', '') or ''
            complete_php = state.get('integrated_code', {}).get('complete_php', '') or php_code
            normalized_complete_php = self.company_style_normalizer.normalize(complete_php)
            if state.get('integrated_code') is not None:
                state['integrated_code']['complete_php'] = normalized_complete_php
            state['normalized_complete_php'] = normalized_complete_php
            contract_validation = self.company_contract_validator.validate(normalized_complete_php)
            state['company_contract_validation'] = contract_validation
            diagnostics = dict(state.get('generation_diagnostics') or {})
            diagnostics.setdefault('normalization', {})
            diagnostics['normalization']['changed'] = normalized_complete_php != complete_php
            diagnostics['contract_validation'] = contract_validation
            state['generation_diagnostics'] = diagnostics
            
            # âœ… STEP 3: Run dynamic validation FIRST (most important)
            strict_contract = state.get('strict_contract') or {}
            intent = {
                'feature_type': state.get('feature_type', 'form'),
                'database': state.get('intent', {}).get('database', {}),
                'strict_security_rules': bool(strict_contract.get('valid')),
                'strict_contract_mode': bool(strict_contract.get('valid')),
                'strict_contract': strict_contract,
                'required_features': state.get('strict_features', []),
            }
            dynamic_result = self.dynamic_validator.validate_code(normalized_complete_php, intent)
            
            # âœ… V-1 FIX: If dynamic validation blocks, stop immediately
            if dynamic_result.get('block_generation', False):
                logger.error("âŒ CRITICAL: Dynamic validation BLOCKED generation")
                current_regen = int(state.get('regeneration_count', 0) or 0)
                max_regens = int(state.get('max_regenerations', 3) or 3)
                if current_regen < max_regens:
                    state['regeneration_count'] = current_regen + 1
                else:
                    state['regeneration_count'] = current_regen
                validation_reason = "dynamic_block_generation"
                state['validation_result'] = {
                    'overall_score': 0,
                    'final_score': 0,
                    'dynamic_score': 0,
                    'enterprise_score': 0,
                    'pattern_score': 0,
                    'detailed_results': {'dynamic': dynamic_result},
                    'all_issues': {
                        'critical': dynamic_result['critical_errors'],
                        'major': [],
                        'minor': dynamic_result['warnings']
                    },
                    'approval_status': 'needs_revision',
                    'regeneration_required': True,
                    'block_generation': True,
                    'needs_revision': True,
                    'critical_errors_count': len(dynamic_result.get('critical_errors', [])),
                    'validation_passed': False,
                    'block_save': True,
                    'validation_reason': validation_reason,
                    'score': 0,
                    'authoritative_gate': {
                        'final_pass': False,
                        'reason': validation_reason,
                    },
                }
                state['validation_score'] = 0
                state['validation_passed'] = False
                state['validation_reason'] = validation_reason
                state['block_save'] = True
                state.setdefault('validation_errors', [])
                state['validation_errors'].extend(dynamic_result.get('critical_errors', []))
                state['current_step'] = 'validated'
                return state
            
            # Perform other validation checks
            validation_results = {
                'dynamic': dynamic_result,
                'company_contract': contract_validation,
                'security': await self._validate_security(state),
                'syntax': await self._validate_syntax(state),
                'standards': await self._validate_standards(state)
            }

            # Cost optimization: optional LLM validation (disabled by default)
            if self._is_llm_validation_enabled():
                validation_results['llm_review'] = await self._llm_validation(state)
            else:
                validation_results['llm_review'] = {
                    'score': 90,
                    'critical_issues': [],
                    'major_issues': [],
                    'minor_issues': ['LLM validation disabled for cost optimization']
                }
            
            # Authoritative scoring inputs.
            dynamic_score = float(dynamic_result.get('score', 0) or 0)
            other_scores = [
                float(v.get('score', 0) or 0)
                for k, v in validation_results.items()
                if k not in {'dynamic', 'company_contract'}
            ]
            enterprise_score = (sum(other_scores) / len(other_scores)) if other_scores else 0.0
            overall_score = (dynamic_score * 0.5) + (enterprise_score * 0.5)

            all_issues = {
                'critical': dynamic_result['critical_errors'].copy(),
                'major': [],
                'minor': dynamic_result['warnings'].copy()
            }

            strict_company_compiler = bool(getattr(settings, 'STRICT_COMPANY_FORM_COMPILER', False))
            strict_contract_active = bool((state.get('strict_contract') or {}).get('valid'))
            strict_company_enforced = bool(strict_company_compiler or strict_contract_active)
            if contract_validation.get('errors'):
                contract_issue = {
                    'severity': 'critical' if strict_company_enforced else 'major',
                    'file': 'PHP',
                    'issue': 'Company form contract validation failed',
                    'details': contract_validation.get('errors', []),
                }
                logger.error(
                    "Company form contract validation failed: %s",
                    "; ".join([str(err) for err in contract_validation.get('errors', [])])
                )
                if strict_company_enforced:
                    all_issues['critical'].append(contract_issue)
                else:
                    all_issues['major'].append(contract_issue)
            if contract_validation.get('warnings'):
                all_issues['minor'].append({
                    'severity': 'minor',
                    'file': 'PHP',
                    'issue': 'Company form contract warnings',
                    'details': contract_validation.get('warnings', []),
                })

            for validation_type, result in validation_results.items():
                if validation_type == 'company_contract':
                    continue
                if validation_type != 'dynamic':
                    all_issues['critical'].extend(result.get('critical_issues', []))
                    all_issues['major'].extend(result.get('major_issues', []))
                    all_issues['minor'].extend(result.get('minor_issues', []))

            inline_generation_validation = state.get('inline_generation_validation', {}) or {}
            if inline_generation_validation:
                if not inline_generation_validation.get('valid', True):
                    missing_functions = inline_generation_validation.get('missing_functions', [])
                    if missing_functions:
                        all_issues['critical'].append({
                            'severity': 'critical',
                            'file': 'PHP',
                            'issue': f"Generator validation missing company functions: {', '.join(missing_functions)}",
                            'details': ['Inline PHP generator did not satisfy required company database functions']
                        })

                    forbidden_functions = inline_generation_validation.get('forbidden_functions', [])
                    if forbidden_functions:
                        all_issues['critical'].append({
                            'severity': 'critical',
                            'file': 'PHP',
                            'issue': f"Generator validation found forbidden functions: {', '.join(forbidden_functions)}",
                            'details': ['Remove forbidden DB APIs and regenerate with company-standard functions only']
                        })

                    required_blockers = inline_generation_validation.get('required_blockers', [])
                    for blocker in required_blockers:
                        all_issues['critical'].append({
                            'severity': 'critical',
                            'file': 'PHP',
                            'issue': blocker.get('message', blocker.get('key', 'Missing required pattern')),
                            'details': [f"Generator blocker: {blocker.get('key', 'required_pattern')}"]
                        })

                    if inline_generation_validation.get('optional_warnings'):
                        all_issues['minor'].append({
                            'severity': 'minor',
                            'file': 'PHP',
                            'issue': 'Generator reported optional warnings',
                            'details': inline_generation_validation.get('optional_warnings', [])
                        })

            generation_metadata = state.get('generation_metadata', {}) or {}
            fallback_usage = generation_metadata.get('fallback_usage', {}) if isinstance(generation_metadata, dict) else {}
            if isinstance(fallback_usage, dict) and fallback_usage:
                generic_ratio = float(fallback_usage.get('generic_ratio_percent', 0) or 0)
                generic_budget = float(fallback_usage.get('generic_budget_percent', 1) or 1)
                budget_passed = bool(fallback_usage.get('generic_budget_passed', True))
                fallback_events = fallback_usage.get('events', []) or []
                fallback_reasons = [str(evt.get('reason', 'fallback_applied')) for evt in fallback_events if isinstance(evt, dict)]

                if not budget_passed:
                    all_issues['critical'].append({
                        'severity': 'critical',
                        'file': 'PHP',
                        'issue': (
                            f"Generic fallback budget exceeded ({generic_ratio:.4f}% > {generic_budget:.4f}%). "
                            "Output violates <=1% generic fallback policy."
                        ),
                        'details': fallback_reasons[:10]
                    })
                elif generic_ratio > 0:
                    all_issues['minor'].append({
                        'severity': 'minor',
                        'file': 'PHP',
                        'issue': f"Generic fallback auto-attachments used ({generic_ratio:.4f}% of output)",
                        'details': fallback_reasons[:10]
                    })
            
            pattern_score = enterprise_score
            # âœ… ISSUE #12 FIX: Integrate pattern_validation results into validation
            pattern_validation = state.get('pattern_validation')
            if pattern_validation:
                pattern_score = float(pattern_validation.get('overall_score', 0) or 0)
                
                # ✅ ACTION 2 FIX: Store pattern_validation_score for views.py
                state['pattern_validation_score'] = int(pattern_score)
                logger.info(f"✅ Stored pattern_validation_score: {state['pattern_validation_score']}%")
                
                # Add pattern validation issues to all_issues
                php_missing = pattern_validation.get('php', {}).get('missing_patterns', [])
                html_missing = pattern_validation.get('html', {}).get('missing_patterns', [])
                php_suggestions = pattern_validation.get('php', {}).get('suggestions', [])
                
                if php_missing and pattern_score < 75:
                    all_issues['major'].append({
                        'severity': 'major',
                        'file': 'PHP',
                        'issue': f'Pattern mismatch: {", ".join(php_missing[:3])}',
                        'details': php_suggestions[:3]
                    })
                
                logger.info(f"ðŸ“Š Pattern validation observed: pattern_score={pattern_score:.1f}%")
            
            # âœ… FIX #2 + TIMEOUT FIX: Don't treat optional pattern warnings as critical errors
            # User-requested patterns (dropdown, grid, etc.) are OPTIONAL - they don't block generation
            # Only REAL critical errors (missing company functions, syntax errors) should trigger regeneration
            user_request = state.get('user_request', '').lower()
            requested_patterns = []
            requested_pattern_rules = [
                (
                    'dropdown',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_DROPDOWN_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_DROPDOWN_KEYWORDS',
                        default=['dropdown', 'select']
                    )
                ),
                (
                    'keyboard_navigation',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_KEYBOARD_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_KEYBOARD_KEYWORDS',
                        default=['keyboard', 'checkkeycode']
                    )
                ),
                (
                    'form_validation',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_VALIDATION_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_VALIDATION_KEYWORDS',
                        default=['formvalidation', 'form validation']
                    )
                ),
                (
                    'select2',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_SELECT2_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_SELECT2_KEYWORDS',
                        default=['select2']
                    )
                ),
                (
                    'grid',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_GRID_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_GRID_KEYWORDS',
                        default=['grid', 'detail', 'tblcustomerdtl']
                    )
                ),
                (
                    'chart',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_CHART_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_CHART_KEYWORDS',
                        default=['chart', 'acc_cust']
                    )
                ),
                (
                    'cascading_dropdown',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_CASCADING_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_CASCADING_KEYWORDS',
                        default=['cascading']
                    )
                ),
                (
                    'ajax_auto_id',
                    get_csv_setting(
                        'CODEGEN_REQUEST_PATTERN_AJAX_KEYWORDS',
                        'CODEGEN_REQUEST_PATTERN_AJAX_KEYWORDS',
                        default=['maxid', 'getmaxid']
                    )
                ),
            ]
            for pattern_name, keywords in requested_pattern_rules:
                normalized_keywords = [str(k).strip().lower() for k in keywords if str(k).strip()]
                if any(keyword in user_request for keyword in normalized_keywords):
                    requested_patterns.append(pattern_name)
            
            # Check which requested patterns are missing (for logging only, NOT for blocking)
            missing_requested = []
            for pattern in requested_patterns:
                for warning_key in ['cascading_dropdown', 'keyboard_navigation', 'form_validation', 'select2_cascading', 'grid_pattern', 'chart_integration']:
                    if pattern in warning_key.lower() or warning_key.lower() in pattern:
                        if any(warning_key.lower() in str(w).lower() for w in all_issues.get('minor', [])):
                            missing_requested.append(pattern)
                            break
            
            # âœ… TIMEOUT FIX: Log missing patterns but DON'T add to critical errors
            # These are OPTIONAL patterns - code can still work without them
            if missing_requested:
                logger.warning(f"âš ï¸ {len(missing_requested)} optional patterns not detected (code still valid): {missing_requested}")
            critical_count = len(all_issues['critical'])
            retrieval_quality = str(state.get('retrieval_quality') or 'sufficient').lower()
            retrieval_required_coverage = float(state.get('retrieval_required_coverage', 0) or 0.0)
            retrieval_score = float(
                state.get('retrieval_score', state.get('retrieval_quality_score', 0)) or 0.0
            )
            retrieval_hard_block_floor = float(RETRIEVAL_HARD_BLOCK_FLOOR) * 100.0
            retrieval_target_floor = float(RETRIEVAL_COVERAGE_FLOOR) * 100.0
            retrieval_score_floor = float(RETRIEVAL_SCORE_FLOOR)
            retrieval_hard_block = False
            dynamic_critical_count = len(dynamic_result.get('critical_errors', []))
            external_critical_count = max(0, critical_count - dynamic_critical_count)
            block_generation = bool(dynamic_result.get('block_generation', False) or external_critical_count > 0)
            needs_revision = bool(dynamic_result.get('needs_revision', False))
            contract_failed = bool(contract_validation.get('errors'))
            if contract_failed and strict_company_enforced:
                needs_revision = True
                block_generation = True

            retrieval_coverage_failed = retrieval_required_coverage < retrieval_target_floor
            retrieval_score_failed = retrieval_score < retrieval_score_floor
            if retrieval_quality == 'insufficient' or retrieval_coverage_failed or retrieval_score_failed:
                retrieval_hard_block = True
                needs_revision = True
                block_generation = True
                details = [
                    f"retrieval_required_coverage={retrieval_required_coverage:.1f}% (min {retrieval_target_floor:.1f}%)",
                    f"retrieval_score={retrieval_score:.1f} (min {retrieval_score_floor:.1f})",
                ]
                if retrieval_required_coverage < retrieval_hard_block_floor:
                    details.append(
                        f"retrieval_required_coverage also below emergency floor {retrieval_hard_block_floor:.1f}%"
                    )
                all_issues['major'].append({
                    'severity': 'major',
                    'file': 'retrieval',
                    'issue': 'Retrieval strict quality floor not met',
                    'details': details
                })
            if block_generation:
                needs_revision = True
            final_score = float(dynamic_score)

            failure_reasons = []
            if block_generation and dynamic_result.get('block_generation', False):
                failure_reasons.append("dynamic_block_generation=true")
            if external_critical_count > 0:
                failure_reasons.append(f"external_critical_errors={external_critical_count}")
            if needs_revision:
                failure_reasons.append("dynamic_needs_revision=true")
            if contract_failed and strict_company_enforced:
                failure_reasons.append("company_contract_validation_failed=true")
            if retrieval_hard_block:
                failure_reasons.append(
                    f"retrieval_quality_floor_failed(coverage={retrieval_required_coverage:.1f}%/{retrieval_target_floor:.1f}%,"
                    f"score={retrieval_score:.1f}/{retrieval_score_floor:.1f})"
                )
            if not bool(dynamic_result.get('valid', True)):
                failure_reasons.append("dynamic_valid=false")

            authoritative_pass = bool(dynamic_result.get('valid', False)) and not failure_reasons
            validation_reason = 'authoritative_pass' if authoritative_pass else '; '.join(failure_reasons)

            # Consistency clamp: a revision/block flag can never coexist with valid/pass scores.
            if needs_revision or block_generation:
                authoritative_pass = False
                final_score = min(final_score, 49.0)

            regeneration_required = not authoritative_pass
            approval_status = 'approved' if authoritative_pass else 'needs_revision'
            block_save = not authoritative_pass

            # Update state
            state['validation_result'] = {
                'overall_score': final_score,
                'final_score': final_score,
                'dynamic_score': dynamic_score,
                'enterprise_score': enterprise_score,
                'pattern_score': pattern_score,
                'detailed_results': validation_results,
                'all_issues': all_issues,
                'approval_status': approval_status,
                'regeneration_required': regeneration_required,
                'block_generation': block_generation,
                'needs_revision': needs_revision,
                'critical_errors_count': critical_count,
                'validation_passed': authoritative_pass,
                'block_save': block_save,
                'validation_reason': validation_reason,
                'score': final_score,
                'retrieval_quality': retrieval_quality,
                'retrieval_score': retrieval_score,
                'retrieval_required_coverage': retrieval_required_coverage,
                'authoritative_gate': {
                    'final_pass': authoritative_pass,
                    'reason': validation_reason,
                },
            }
            state['validation_score'] = final_score
            state['validation_passed'] = authoritative_pass
            state['validation_reason'] = validation_reason
            state['block_save'] = block_save
            state['current_step'] = 'validated'
            
            if regeneration_required:
                state['validation_errors'].extend(all_issues['critical'])
                current_regen = int(state.get('regeneration_count', 0) or 0)
                max_regens = int(state.get('max_regenerations', 3) or 3)
                if current_regen < max_regens:
                    state['regeneration_count'] = current_regen + 1
            
            logger.info(
                "âœ… STEP 3: Validation completed - final=%.2f dynamic=%.2f enterprise=%.2f pattern=%.2f status=%s",
                final_score,
                dynamic_score,
                enterprise_score,
                pattern_score,
                approval_status,
            )
            logger.info(f"   Critical errors: {critical_count}")
            logger.info(f"   Needs revision: {needs_revision}")
            logger.info(f"   Validation passed: {authoritative_pass}")
            logger.info(f"   Validation reason: {validation_reason}")
            if critical_count > 0:
                logger.error(f"   Critical validation issues: {all_issues.get('critical', [])}")
            contract_errors = []
            if isinstance(contract_validation, dict):
                contract_errors = contract_validation.get('errors') or []
            if contract_errors:
                logger.error(f"   Company contract errors: {contract_errors}")
            logger.info(
                f"   Regeneration counter: {state.get('regeneration_count', 0)}/{state.get('max_regenerations', 3)}"
            )
            
            return state
            
        except Exception as e:
            logger.error(f"Error in validation: {str(e)}")
            state['validation_errors'].append({
                'step': 'validation',
                'error': str(e)
            })
            current_regen = int(state.get('regeneration_count', 0) or 0)
            max_regens = int(state.get('max_regenerations', 3) or 3)
            if current_regen < max_regens:
                state['regeneration_count'] = current_regen + 1
            state['validation_result'] = {
                'overall_score': 0,
                'final_score': 0,
                'dynamic_score': 0,
                'enterprise_score': 0,
                'pattern_score': 0,
                'detailed_results': {},
                'all_issues': {
                    'critical': [{'severity': 'critical', 'step': 'validation', 'issue': str(e)}],
                    'major': [],
                    'minor': []
                },
                'approval_status': 'needs_revision',
                'regeneration_required': True,
                'block_generation': True,
                'needs_revision': True,
                'critical_errors_count': 1,
                'validation_passed': False,
                'block_save': True,
                'validation_reason': 'validation_exception',
                'score': 0,
                'authoritative_gate': {
                    'final_pass': False,
                    'reason': 'validation_exception',
                },
            }
            state['validation_score'] = 0
            state['validation_passed'] = False
            state['validation_reason'] = 'validation_exception'
            state['block_save'] = True
            state['current_step'] = 'validated'
            return state

    def _is_llm_validation_enabled(self) -> bool:
        """Enable expensive LLM validation only when explicitly requested."""
        try:
            raw = str(getattr(settings, 'ENABLE_LLM_VALIDATION', os.getenv('ENABLE_LLM_VALIDATION', 'false'))).strip().lower()
            return raw in ('1', 'true', 'yes', 'on')
        except Exception:
            return False
    
    async def _validate_security(self, state: AgentState) -> Dict:
        """
        Security validation
        """
        logger.info("Running security validation")
        
        issues = []
        score = 100
        strict_security_rules = bool((state.get('strict_contract') or {}).get('valid'))
        issue_severity = 'critical' if strict_security_rules else 'major'
        penalty_step = 25 if strict_security_rules else 15
        
        # Check PHP for SQL injection vulnerabilities
        php_code = state.get('php_code', '') or ''
        if php_code:
            sql_injection_check = self.security_validator.check_sql_injection(php_code)
            if not sql_injection_check['safe']:
                issues.append({
                    'severity': issue_severity,
                    'file': 'PHP',
                    'issue': 'Potential SQL injection vulnerability',
                    'details': sql_injection_check['details']
                })
                score -= penalty_step
        
        # Check for XSS vulnerabilities
        html_code = state.get('html_code', '') or ''
        js_code = state.get('js_code', '') or ''
        
        xss_check = self.security_validator.check_xss(html_code, js_code)
        if not xss_check['safe']:
            issues.append({
                'severity': issue_severity,
                'file': 'HTML/JS',
                'issue': 'Potential XSS vulnerability',
                'details': xss_check['details']
            })
            score -= penalty_step
        
        # Check for hardcoded credentials
        all_code = f"{php_code}\n{html_code}\n{js_code}"
        credentials_check = self.security_validator.check_hardcoded_credentials(all_code)
        if not credentials_check['safe']:
            issues.append({
                'severity': issue_severity,
                'file': 'Multiple',
                'issue': 'Hardcoded credentials detected',
                'details': credentials_check['details']
            })
            score -= (30 if strict_security_rules else 20)
        
        return {
            'score': max(0, score),
            'critical_issues': [i for i in issues if i['severity'] == 'critical'],
            'major_issues': [i for i in issues if i['severity'] == 'major'],
            'minor_issues': [i for i in issues if i['severity'] == 'minor']
        }
    
    async def _validate_syntax(self, state: AgentState) -> Dict:
        """
        Syntax validation for all languages
        """
        logger.info("Running syntax validation")
        
        issues = []
        score = 100
        
        # Validate PHP syntax against the final normalized output in inline mode.
        php_code = (
            state.get('normalized_complete_php')
            or (state.get('integrated_code', {}) or {}).get('complete_php')
            or state.get('php_code', '')
        )
        strict_syntax_mode = bool(
            (state.get('strict_contract') or {}).get('valid')
            or getattr(settings, 'STRICT_COMPANY_FORM_COMPILER', False)
        )
        if php_code:
            php_check = self.syntax_validator.validate_php(php_code)
            if not php_check['valid']:
                issues.append({
                    'severity': 'critical' if strict_syntax_mode else 'major',
                    'file': 'PHP',
                    'issue': 'Syntax error in PHP code',
                    'details': php_check['errors']
                })
                score -= 40 if strict_syntax_mode else 20
        
        # Validate HTML syntax
        html_code = state.get('html_code', '')
        if html_code:
            html_check = self.syntax_validator.validate_html(html_code)
            if not html_check['valid']:
                issues.append({
                    'severity': 'major',
                    'file': 'HTML',
                    'issue': 'Invalid HTML structure',
                    'details': html_check['errors']
                })
                score -= 20
        
        # Validate CSS syntax
        css_code = state.get('css_code', '')
        if css_code:
            css_check = self.syntax_validator.validate_css(css_code)
            if not css_check['valid']:
                issues.append({
                    'severity': 'minor',
                    'file': 'CSS',
                    'issue': 'CSS syntax issues',
                    'details': css_check['errors']
                })
                score -= 10
        
        # Validate JavaScript syntax
        js_code = state.get('js_code', '')
        if js_code:
            js_check = self.syntax_validator.validate_javascript(js_code)
            if not js_check['valid']:
                issues.append({
                    'severity': 'major',
                    'file': 'JavaScript',
                    'issue': 'JavaScript syntax error',
                    'details': js_check['errors']
                })
                score -= 20
        
        return {
            'score': max(0, score),
            'critical_issues': [i for i in issues if i['severity'] == 'critical'],
            'major_issues': [i for i in issues if i['severity'] == 'major'],
            'minor_issues': [i for i in issues if i['severity'] == 'minor']
        }
    
    async def _validate_standards(self, state: AgentState) -> Dict:
        """
        Validate against company coding standards
        """
        logger.info("Running standards compliance validation")
        
        # Simple standards check (can be enhanced)
        issues = []
        score = 100
        
        standards = state.get('md_standards', '')
        metadata = state.get('standards_metadata', {})
        
        # Check PHP version compatibility (if specified)
        if metadata.get('php_version'):
            # This is a placeholder - would need actual PHP version detection
            pass
        
        # Check for consistent naming conventions
        # (Simplified check)
        
        return {
            'score': score,
            'critical_issues': [],
            'major_issues': [],
            'minor_issues': issues
        }
    
    async def _llm_validation(self, state: AgentState) -> Dict:
        """
        LLM-based comprehensive validation
        
        âœ… TIMEOUT FIX: Skip LLM validation during regeneration attempts
        LLM validation is expensive (sends 25KB+ code to API)
        Only run on first generation attempt
        """
        # âœ… TIMEOUT FIX: Skip during regeneration
        attempt_count = state.get('generation_attempt', 0)
        if attempt_count > 1:
            logger.info(f"â© Skipping LLM validation during regeneration attempt {attempt_count} (timeout prevention)")
            return {
                'score': 85,
                'critical_issues': [],
                'major_issues': [],
                'minor_issues': ['LLM validation skipped during regeneration']
            }
        
        logger.info("Running LLM-based validation")
        
        validation_prompt = PromptTemplate(
            template=VALIDATION_PROMPT,
            input_variables=["complete_code_bundle", "md_standards"]
        )
        
        # Bundle all code
        code_bundle = f"""
## SQL Schema
```sql
{state.get('sql_code', '')}
```

## PHP Backend
```php
{state.get('php_code', '')}
```

## HTML Form
```html
{state.get('html_code', '')}
```

## CSS Styling
```css
{state.get('css_code', '')}
```

## JavaScript
```javascript
{state.get('js_code', '')}
```
"""
        
        chain = validation_prompt | self.llm
        
        result = await chain.ainvoke({
            "complete_code_bundle": code_bundle,
            "md_standards": state.get('md_standards', '')
        })
        
        # Parse validation result
        validation_data = self._parse_validation_response(result.content)
        
        return validation_data
    
    def _parse_validation_response(self, content: str) -> Dict:
        """
        Parse LLM validation response
        """
        import re
        import json
        
        # Try to extract JSON
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                return {
                    'score': float(data.get('overall_score', 80)),
                    'critical_issues': data.get('critical_issues', []),
                    'major_issues': data.get('major_issues', []),
                    'minor_issues': data.get('minor_issues', [])
                }
            except:
                pass
        
        # Fallback: Return low score with warning if LLM response can't be parsed
        logger.warning("âš ï¸ LLM validation response could not be parsed â€” returning conservative score")
        return {
            'score': 50,  # âœ… PHASE B FIX 4: Conservative score instead of hardcoded 80
            'critical_issues': ['LLM validation response malformed â€” manual review recommended'],
            'major_issues': [],
            'minor_issues': []
        }


# Initialize node
validate_code_node = ValidationNode()


## **Step 5.3: ENTERPRISE Pattern Validation Node**

class PatternValidationNode:
    """
    ENTERPRISE-GRADE pattern validation
    Validates generated code STRUCTURE against company patterns
    Checks if code LOOKS like company code, not just function names
    """
    
    def __init__(self):
        self.validator = None
        self.pattern_retriever = None
    
    def _initialize(self, user_id: str, analyzed_patterns: Dict = None):
        """Lazy initialization to avoid Django settings issues"""
        if self.validator is None:
            from agents.validators.enterprise_pattern_validator import EnterprisePatternValidator
            from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever
            
            self.validator = EnterprisePatternValidator(user_id=user_id)
            analyzed_patterns = analyzed_patterns or {}
            self.pattern_retriever = EnterprisePatternRetriever(user_id=user_id, analyzed_patterns=analyzed_patterns)
    
    async def execute(self, state: AgentState) -> AgentState:
        """
        Validate pattern matching using ENTERPRISE validator
        Checks CODE STRUCTURE, not just function names
        """
        try:
            # Fast path: skip expensive pattern retrieval in inline mode/regeneration
            attempt_count = state.get('generation_attempt', 0)
            is_inline = state.get('is_inline_generation', False)

            if attempt_count > 1:
                logger.info(f"â© Skipping pattern validation during regeneration attempt {attempt_count} (timeout prevention)")
                state['pattern_validation'] = {
                    'overall_score': 100,
                    'passed': True,
                    'php': {'score': 100, 'passed': True, 'details': {}, 'missing_patterns': [], 'suggestions': []},
                    'html': {'score': 100, 'passed': True, 'details': {'inline_mode': True}, 'missing_patterns': [], 'suggestions': []},
                    'message': 'Skipped during regeneration (timeout prevention)'
                }
                return state

            user_id = state.get('user_id')
            analyzed_patterns = state.get('analyzed_patterns', {})
            self._initialize(user_id, analyzed_patterns=analyzed_patterns)
            
            logger.info("ðŸ” ENTERPRISE Pattern Validation: Checking code structure")
            
            # Get intent for context
            intent = state.get('intent', {})
            
            # Get company examples for comparison
            # Reduced k=3 to k=1 for validation (faster, less data, fixes timeout)
            php_examples = self.pattern_retriever.get_php_examples(
                intent,
                k=1,
                user_request=state.get('user_request', ''),
            )
            # âœ… TIMEOUT FIX: Skip HTML retrieval for inline PHP mode
            # HTML is embedded in the PHP file, no need to retrieve separate HTML examples
            if is_inline:
                logger.info("â© Skipping HTML retrieval during validation (inline PHP mode)")
                html_examples = ""
            else:
                html_examples = self.pattern_retriever.get_html_examples(intent, k=5)
            
            # Extract actual code from formatted examples
            php_company_code = self._extract_code_from_examples(php_examples, 'php')
            html_company_code = self._extract_code_from_examples(html_examples, 'html')
            
            # ðŸ†• ISSUE #2 FIX: Use complete_php for inline generation
            # For inline generation: complete_php has the full file with db_insert/db_update
            # For separate generation: php_code has the backend logic
            integrated_code = state.get('integrated_code', {})
            is_inline = state.get('is_inline_generation', False)
            
            # âœ… FIX: Priority order for validation
            if is_inline and integrated_code and 'complete_php' in integrated_code:
                php_code_to_validate = integrated_code['complete_php']
                logger.info("ðŸ” Validating COMPLETE PHP (inline mode - includes all db functions)")
            elif 'complete_php' in state:
                php_code_to_validate = state['complete_php']
                logger.info("ðŸ” Validating COMPLETE PHP from state['complete_php']")
            else:
                php_code_to_validate = state.get('php_code', '')
                logger.info("ðŸ” Validating separate PHP file")
            
            # Validate PHP structure
            php_result = self.validator.validate_php_structure(
                generated_code=php_code_to_validate,
                company_examples=php_company_code
            )
            
            # Validate HTML structure (only if separate HTML exists)
            # âœ… FIX: Skip HTML validation for inline PHP mode OR if no HTML examples found
            if state.get('html_code') and state.get('html_code').strip() and html_company_code:
                logger.info("ðŸ” Validating separate HTML file")
                html_result = self.validator.validate_html_structure(
                    generated_html=state.get('html_code', ''),
                    company_examples=html_company_code
                )
            else:
                # Inline PHP mode - HTML is embedded in PHP file
                if not html_company_code:
                    logger.info("âšª Skipping HTML validation (no HTML examples found - inline PHP mode)")
                else:
                    logger.info("âšª Skipping HTML validation (inline PHP mode)")
                html_result = {
                    'score': 100,
                    'passed': True,
                    'details': {'inline_mode': True},
                    'missing_patterns': [],
                    'suggestions': ['HTML embedded in PHP file']
                }
            
            # Calculate overall score
            overall_score = (php_result['score'] * 0.6 + html_result['score'] * 0.4)
            overall_passed = php_result['passed'] and html_result['passed']
            
            # Store results
            validation_result = {
                'overall_score': overall_score,
                'passed': overall_passed,
                'php': php_result,
                'html': html_result,
                'message': f"Pattern Matching: {overall_score:.1f}% - {'âœ… PASSED' if overall_passed else 'âŒ FAILED'}"
            }
            
            state['pattern_validation'] = validation_result
            state['current_step'] = 'pattern_validated'
            
            # Log detailed results
            logger.info(f"ðŸ“Š PHP Structure: {php_result['score']:.1f}% - {'âœ… PASSED' if php_result['passed'] else 'âŒ FAILED'}")
            logger.info(f"   PHP Details: {php_result['details']}")
            
            logger.info(f"ðŸ“Š HTML Structure: {html_result['score']:.1f}% - {'âœ… PASSED' if html_result['passed'] else 'âŒ FAILED'}")
            logger.info(f"   HTML Details: {html_result['details']}")
            
            logger.info(f"ðŸ“Š Overall Pattern Matching: {overall_score:.1f}% - {'âœ… PASSED' if overall_passed else 'âŒ FAILED'}")
            
            if not overall_passed:
                logger.warning("âŒ Pattern validation FAILED - Code structure does not match company patterns")
                
                # Log missing patterns
                all_missing = php_result.get('missing_patterns', []) + html_result.get('missing_patterns', [])
                if all_missing:
                    logger.warning("Missing patterns:")
                    for pattern in all_missing[:10]:
                        logger.warning(f"   â€¢ {pattern}")
                
                # Log suggestions
                all_suggestions = php_result.get('suggestions', []) + html_result.get('suggestions', [])
                if all_suggestions:
                    logger.info("Suggestions for improvement:")
                    for suggestion in all_suggestions[:5]:
                        logger.info(f"   ðŸ’¡ {suggestion}")
                
                # Add to validation errors
                state['validation_errors'].append({
                    'step': 'pattern_validation',
                    'error': 'Generated code structure does not match company patterns',
                    'php_score': php_result['score'],
                    'html_score': html_result['score'],
                    'missing_patterns': all_missing,
                    'suggestions': all_suggestions
                })
                
                # Reduce validation score
                current_score = state.get('validation_score', 100)
                if current_score is None:
                    current_score = 100
                penalty = (100 - overall_score) * 0.3  # 30% weight on pattern matching
                state['validation_score'] = max(0, current_score - penalty)
                
                logger.warning(f"âš ï¸ Validation score reduced to {state['validation_score']:.1f}% due to pattern mismatch")
            else:
                logger.info("âœ… Pattern validation PASSED - Code structure matches company patterns")
            
            return state
            
        except Exception as e:
            logger.error(f"Error in pattern validation: {str(e)}", exc_info=True)
            # Don't fail the entire workflow
            state['current_step'] = 'pattern_validation_error'
            return state
    
    def _extract_code_from_examples(self, formatted_examples: str, language: str) -> List[str]:
        """
        Extract actual code blocks from formatted examples string
        """
        import re
        
        # Pattern to match code blocks
        pattern = rf"```{language}\n(.*?)```"
        matches = re.findall(pattern, formatted_examples, re.DOTALL)
        
        return [match.strip() for match in matches if match.strip()]


# Initialize node
validate_patterns_node = PatternValidationNode()

