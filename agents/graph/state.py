# agents/graph/state.py

from typing import TypedDict, Annotated, List, Dict, Optional
from langchain_core.messages import BaseMessage
import operator
from agents.utils.runtime_config import get_int_setting

class AgentState(TypedDict):
    """
    🆕 SIMPLIFIED: State structure for complete PHP-only generation
    """
    
    # Input
    user_request: str
    project_id: str
    user_id: str
    
    # Intent Analysis
    intent: Optional[Dict]  # Parsed user intent
    feature_type: Optional[str]
    required_fields: Optional[List[Dict]]
    
    # Context Retrieval
    retrieved_patterns: Annotated[List[str], operator.add]  # Company code patterns
    analyzed_patterns: Optional[Dict]  # Pre-analyzed patterns from codebase
    codebase_id: Optional[str]  # ID of the codebase being used
    template_info: Optional[Dict]  # Template metadata for generation node (Task 3.4)
    md_standards: Optional[str]  # Coding standards content
    standards_metadata: Optional[Dict]  # Parsed standards (PHP version, etc.)
    strict_contract: Optional[Dict]  # Strict ERP prompt contract
    strict_form_type: Optional[str]
    strict_features: Optional[List[str]]
    strict_required_patterns: Optional[List[str]]
    strict_selected_patterns: Optional[List[Dict]]
    strict_pattern_memory_context: Optional[str]
    strict_combo_signature: Optional[str]
    pattern_coverage: Optional[float]
    retrieval_quality_score: Optional[float]
    retrieval_score: Optional[float]
    retrieval_metrics: Optional[Dict]
    retrieval_real_db_function_count: Optional[int]
    retrieval_synthetic_db_function_count: Optional[int]
    
    # Database Connection (kept for future use, but not generating SQL)
    database_connection_id: Optional[str]
    database_type: Optional[str]
    database_connection_details: Optional[Dict]
    
    # 🆕 SIMPLIFIED: Generated Code - Only complete PHP
    php_code: Optional[str]  # Complete inline PHP+HTML+CSS+JS file
    complete_php: Optional[str]  # Complete PHP for validation (alias for php_code)
    
    # 🆕 DEPRECATED: These fields no longer used (kept for backward compatibility)
    sql_code: Optional[str]  # Not generated anymore
    html_code: Optional[str]  # Not extracted anymore
    css_code: Optional[str]  # Not extracted anymore
    js_code: Optional[str]  # Not extracted anymore
    php_logic: Optional[str]  # Not extracted anymore
    
    # Inline Generation Flag (always True now)
    is_inline_generation: bool
    generation_metadata: Optional[Dict]  # Canonical naming/table metadata from inline generator
    inline_generation_validation: Optional[Dict]  # Inline validation summary for downstream nodes
    
    # Integration
    integrated_code: Optional[Dict]  # Contains only 'complete_php' key
    normalized_complete_php: Optional[str]
    file_structure: Optional[Dict]
    deployment_guide: Optional[str]
    
    # Validation
    validation_result: Optional[Dict]
    validation_errors: Annotated[List[Dict], operator.add]
    validation_score: Optional[float]
    validation_passed: Optional[bool]
    validation_reason: Optional[str]
    block_save: Optional[bool]
    company_contract_validation: Optional[Dict]
    generation_diagnostics: Optional[Dict]
    retrieval_quality: Optional[str]
    retrieval_required_coverage: Optional[float]
    retrieval_top_candidates: Optional[List[Dict]]
    retrieval_gate_blocked: Optional[bool]
    retrieval_gate_reason: Optional[str]
    
    # Control Flow
    regeneration_count: int
    max_regenerations: int
    current_step: Optional[str]
    
    # Conversation
    messages: Annotated[List[BaseMessage], operator.add]
    
    # Output
    final_output: Optional[Dict]
    status: Optional[str]  # 'processing', 'completed', 'failed'
    error_message: Optional[str]


def create_initial_state(user_request: str, project_id: str, user_id: str, database_connection_id: str = None, codebase_id: str = None) -> AgentState:
    """
    🆕 SIMPLIFIED: Initialize agent state for complete PHP-only generation
    """
    max_regenerations = get_int_setting(
        'CODEGEN_WORKFLOW_MAX_REGENERATIONS',
        'CODEGEN_WORKFLOW_MAX_REGENERATIONS',
        3,
        min_value=0,
        max_value=5
    )

    return AgentState(
        user_request=user_request,
        project_id=project_id,
        user_id=user_id,
        intent=None,
        feature_type=None,
        required_fields=None,
        retrieved_patterns=[],
        analyzed_patterns=None,
        codebase_id=codebase_id,
        template_info=None,  # Task 3.4: Template metadata for generation node
        md_standards=None,
        standards_metadata=None,
        strict_contract=None,
        strict_form_type=None,
        strict_features=None,
        strict_required_patterns=None,
        strict_selected_patterns=None,
        strict_pattern_memory_context=None,
        strict_combo_signature=None,
        pattern_coverage=None,
        retrieval_quality_score=None,
        retrieval_score=None,
        retrieval_metrics=None,
        retrieval_real_db_function_count=None,
        retrieval_synthetic_db_function_count=None,
        database_connection_id=database_connection_id,
        database_type=None,
        database_connection_details=None,
        
        # 🆕 SIMPLIFIED: Only php_code is actively used
        php_code=None,  # Will contain complete inline PHP+HTML+CSS+JS
        
        # 🆕 DEPRECATED: Set to None, not used anymore
        sql_code=None,
        html_code=None,
        css_code=None,
        js_code=None,
        php_logic=None,
        
        is_inline_generation=True,  # 🆕 Always True now
        generation_metadata=None,
        inline_generation_validation=None,
        integrated_code=None,
        normalized_complete_php=None,
        file_structure=None,
        deployment_guide=None,
        validation_result=None,
        validation_errors=[],
        validation_score=None,
        validation_passed=None,
        validation_reason=None,
        block_save=None,
        company_contract_validation=None,
        generation_diagnostics=None,
        retrieval_quality=None,
        retrieval_required_coverage=None,
        retrieval_top_candidates=None,
        retrieval_gate_blocked=False,
        retrieval_gate_reason=None,
        regeneration_count=0,
        max_regenerations=max_regenerations,
        current_step=None,
        messages=[],
        final_output=None,
        status='processing',
        error_message=None
    )
