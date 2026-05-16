from typing import Dict
from asgiref.sync import sync_to_async
from langgraph.graph import StateGraph, END
from .state import AgentState, create_initial_state
from .nodes import (
    analyze_intent_node,
    retrieve_patterns_node,
    load_standards_node,
    generate_database_node,
    generate_php_node,
    integrate_code_node,
    validate_code_node,
    validate_patterns_node
)
from .edges import (
    should_regenerate,
    check_critical_errors,
    resolve_authoritative_validation_gate,
    should_continue_after_retrieval,
)
from agents.prompts.smart_prompt_enhancer import smart_prompt_enhancer
from agents.utils.strict_erp_controller import StrictERPController
import logging
import os

logger = logging.getLogger(__name__)

class CodeGenerationWorkflow:
    """
    🆕 SIMPLIFIED: Complete PHP-only workflow for code generation
    Generates single inline PHP file with embedded HTML, CSS, JS (company style)
    """
    
    def __init__(self):
        self.skip_database_generation = os.getenv('INLINE_SKIP_DATABASE_SCHEMA', '1').lower() in ('1', 'true', 'yes', 'on')
        if self.skip_database_generation:
            logger.info("⏩ Inline mode: database schema generation node is disabled")
        self.workflow = self._build_workflow()
        self.app = self.workflow.compile()
    
    def _build_workflow(self) -> StateGraph:
        """
        Build the simplified workflow for complete PHP generation
        """
        # Create graph
        workflow = StateGraph(AgentState)
        
        # 🆕 SIMPLIFIED: Only essential nodes
        workflow.add_node("analyze_intent", self._analyze_intent_wrapper)
        workflow.add_node("retrieve_patterns", self._retrieve_patterns_wrapper)
        workflow.add_node("load_standards", self._load_standards_wrapper)
        if not self.skip_database_generation:
            workflow.add_node("generate_database", self._generate_database_wrapper)
        workflow.add_node("generate_php", self._generate_php_wrapper)
        workflow.add_node("integrate_code", self._integrate_code_wrapper)
        workflow.add_node("validate_patterns", self._validate_patterns_wrapper)
        workflow.add_node("validate_code", self._validate_code_wrapper)
        workflow.add_node("finalize_output", self._finalize_output)
        workflow.add_node("handle_failure", self._handle_failure)
        
        # Set entry point
        workflow.set_entry_point("analyze_intent")
        
        # Sequential flow: Intent → Patterns → Standards → Database → Complete PHP
        workflow.add_edge("analyze_intent", "retrieve_patterns")
        workflow.add_conditional_edges(
            "retrieve_patterns",
            should_continue_after_retrieval,
            {
                "continue": "load_standards",
                "fail": "handle_failure",
            }
        )
        
        if self.skip_database_generation:
            workflow.add_edge("load_standards", "generate_php")
        else:
            workflow.add_edge("load_standards", "generate_database")
            workflow.add_edge("generate_database", "generate_php")
        
        # 🆕 SIMPLIFIED: Direct to integration (no separate HTML/CSS/JS generation)
        workflow.add_edge("generate_php", "integrate_code")
        
        # Integration and validation
        workflow.add_edge("integrate_code", "validate_patterns")
        workflow.add_edge("validate_patterns", "validate_code")
        
        # Conditional edge: Regenerate or Finalize
        workflow.add_conditional_edges(
            "validate_code",
            should_regenerate,
            {
                "regenerate": "generate_php",  # 🆕 Go back to PHP generation (no database node)
                "finalize": "finalize_output",
                "fail": "handle_failure"
            }
        )
        
        # Conditional edge: Check for critical errors
        workflow.add_conditional_edges(
            "finalize_output",
            check_critical_errors,
            {
                "continue": END,
                "fail": "handle_failure"
            }
        )
        
        workflow.add_edge("handle_failure", END)
        
        return workflow
    
    # Wrapper methods for async execution
    async def _analyze_intent_wrapper(self, state: AgentState) -> AgentState:
        return await analyze_intent_node.execute(state)
    
    async def _retrieve_patterns_wrapper(self, state: AgentState) -> AgentState:
        return await retrieve_patterns_node.execute(state)
    
    async def _load_standards_wrapper(self, state: AgentState) -> AgentState:
        return await load_standards_node.execute(state)
    
    async def _generate_database_wrapper(self, state: AgentState) -> AgentState:
        if self.skip_database_generation:
            logger.info("⏩ Skipping DB schema generation (inline complete-PHP path)")
            if state.get('sql_code') is None:
                state['sql_code'] = ''
            state['current_step'] = 'database_skipped'
            return state
        return await generate_database_node.execute(state)
    
    async def _generate_php_wrapper(self, state: AgentState) -> AgentState:
        return await generate_php_node.execute(state)
    
    async def _integrate_code_wrapper(self, state: AgentState) -> AgentState:
        return await integrate_code_node.execute(state)
    
    async def _validate_patterns_wrapper(self, state: AgentState) -> AgentState:
        return await validate_patterns_node.execute(state)
    
    async def _validate_code_wrapper(self, state: AgentState) -> AgentState:
        # Regeneration count is advanced in edge routing when we actually branch to regenerate.
        return await validate_code_node.execute(state)
    
    async def _finalize_output(self, state: AgentState) -> AgentState:
        """
        🆕 SIMPLIFIED: Return ONLY complete PHP file (company style)
        No SQL, no separate HTML/CSS/JS - just one complete inline PHP file
        """
        logger.info("Finalizing output - Complete PHP only (company style)")
        
        integrated_code = state.get('integrated_code', {})
        validation_result = state.get('validation_result', {}) or {}
        validation_gate = resolve_authoritative_validation_gate(validation_result)
        validation_passed = bool(validation_gate.get('validation_passed'))
        block_save = bool(
            state.get('block_save')
            or validation_gate.get('block_save')
        )
        
        # Check if complete PHP exists
        if not integrated_code or not integrated_code.get('complete_php'):
            logger.error("No complete PHP code was generated")
            state['status'] = 'failed'
            state['error_message'] = 'Complete PHP generation failed - no code produced'
            state['final_output'] = {
                'error': 'Complete PHP generation failed - no code produced',
                'code': {},
                'status': 'failed'
            }
            return state

        if block_save:
            logger.error(
                "Finalization blocked by authoritative validation gate "
                f"(validation_passed={validation_passed}, block_save={block_save})"
            )
            state['status'] = 'failed'
            state['error_message'] = validation_result.get('validation_reason') or 'Validation failed'
            state['block_save'] = True
            state['validation_passed'] = False
            state['final_output'] = {
                'error': 'Code generation failed authoritative validation',
                'details': state['error_message'],
                'validation_score': state.get('validation_score', 0),
                'validation_result': validation_result,
                'code': {},
                'status': 'failed'
            }
            return state

        strict_contract = state.get('strict_contract') or {}
        if strict_contract.get('valid'):
            generation_metadata = state.get('generation_metadata', {}) or {}
            missing_canonical = [
                key for key in ('table_name', 'file_name', 'title')
                if not str(generation_metadata.get(key) or '').strip()
            ]
            if missing_canonical:
                state['status'] = 'failed'
                state['error_message'] = (
                    "Strict canonical naming missing in generation metadata: "
                    + ', '.join(missing_canonical)
                )
                state['block_save'] = True
                state['validation_passed'] = False
                state['final_output'] = {
                    'error': 'Code generation failed authoritative validation',
                    'details': state['error_message'],
                    'validation_score': state.get('validation_score', 0),
                    'validation_result': validation_result,
                    'code': {},
                    'status': 'failed'
                }
                return state

            fallback_mode = str(generation_metadata.get('fallback_mode') or '').strip()
            fallback_usage = generation_metadata.get('fallback_usage')
            if not fallback_mode and isinstance(fallback_usage, dict) and fallback_usage.get('events'):
                fallback_mode = 'fallback_usage_events'
            if fallback_mode:
                state['status'] = 'failed'
                state['error_message'] = (
                    "Strict contract mode disallows fallback output, but fallback metadata was present: "
                    + fallback_mode
                )
                state['block_save'] = True
                state['validation_passed'] = False
                state['final_output'] = {
                    'error': 'Code generation failed authoritative validation',
                    'details': state['error_message'],
                    'validation_score': state.get('validation_score', 0),
                    'validation_result': validation_result,
                    'code': {},
                    'status': 'failed'
                }
                return state
        
        # 🎯 Return ONLY complete PHP (no SQL, no separate files)
        final_code = {
            'complete_php': integrated_code.get('complete_php', '')
        }
        inline_generation_metadata = state.get('generation_metadata', {}) or {}
        
        logger.info(f"✅ Complete PHP Generation Summary:")
        logger.info(f"   📄 Complete PHP file: {len(final_code['complete_php'])} chars")
        logger.info(f"   📄 This file contains: PHP + HTML + CSS + JS (all inline)")
        
        state['final_output'] = {
            'code': final_code,
            'file_structure': state.get('file_structure', {}),
            'deployment_guide': state.get('deployment_guide', ''),
            'validation_score': state.get('validation_score', 0),
            'validation_result': validation_result,
            'intent': state.get('intent', {}),
            'metadata': {
                'regeneration_count': state.get('regeneration_count', 0),
                'patterns_used': len(state.get('retrieved_patterns', [])),
                'generation_type': 'complete_php_only',
                'inline_generation_metadata': inline_generation_metadata,
                'attempts_made': inline_generation_metadata.get('attempts_made', 0),
                'max_attempts': inline_generation_metadata.get('max_attempts', 0),
                'refusal_count': inline_generation_metadata.get('refusal_count', 0),
                'llm_call_failures': inline_generation_metadata.get('llm_call_failures', 0),
                'workflow_status': 'completed',
                'validation_passed': validation_passed,
                'generation_diagnostics': state.get('generation_diagnostics', {}),
            }
        }
        
        state['status'] = 'completed'
        state['block_save'] = False
        state['validation_passed'] = validation_passed
        state['current_step'] = 'finalized'
        
        return state
    
    async def _handle_failure(self, state: AgentState) -> AgentState:
        """
        Handle critical failures
        """
        logger.error("Code generation failed due to critical errors")
        
        state['status'] = 'failed'
        state['block_save'] = True
        state['validation_passed'] = False
        state['final_output'] = {
            'error': 'Code generation failed',
            'details': state.get('error_message', 'Unknown error'),
            'validation_errors': state.get('validation_errors', []),
            'validation_result': state.get('validation_result', {}),
            'status': 'failed',
            'code': {}
        }
        
        return state
    
    async def execute(self, user_request: str, project_id: str, user_id: str, database_connection_id: str = None, codebase_id: str = None) -> Dict:
        """
        Execute the complete workflow
        🆕 ENHANCED: Now auto-enhances user's simple prompt with company patterns
        """
        strict_controller = StrictERPController()
        preflight = None
        initial_state = None
        try:
            logger.info(f"Starting code generation for project {project_id} (codebase_id: {codebase_id})")
            logger.info(f"📝 Original user request: {user_request[:100]}...")
            
            # 🆕 SMART ENHANCEMENT: Auto-add company patterns to user's simple prompt
            # This happens BEFORE intent analysis, so LLM sees enhanced requirements
            # User just says: "Create customer form"
            # System adds: AJAX auto-ID, db_insert(), tblcustomer, comp_code, etc.
            
            # Note: We'll enhance after intent analysis to use detected fields
            # For now, pass original request to intent analysis
            
            # Create initial state with database connection and codebase_id
            initial_state = create_initial_state(user_request, project_id, user_id, database_connection_id, codebase_id)

            analyzed_patterns = None
            if codebase_id:
                try:
                    from agents.utils.cache_helper import get_cached_analyzed_patterns

                    analyzed_patterns = get_cached_analyzed_patterns(user_id, codebase_id)
                    if analyzed_patterns:
                        initial_state['analyzed_patterns'] = analyzed_patterns
                        logger.info("Loaded analyzed patterns into workflow state for strict ERP preflight")
                except Exception as cache_error:
                    logger.warning(f"Could not load analyzed patterns before preflight: {cache_error}")

            preflight = await sync_to_async(
                strict_controller.run_preflight,
                thread_sensitive=True,
            )(
                user_request=user_request,
                user_id=user_id,
                codebase_id=codebase_id,
                analyzed_patterns=analyzed_patterns,
            )

            if not preflight.get('approved'):
                logger.error(
                    "Strict ERP preflight blocked workflow "
                    f"(reason={preflight.get('reason')}, codebase_id={codebase_id})"
                )
                result = strict_controller.attach_metadata(
                    dict(preflight.get('result') or {}),
                    preflight,
                    persistence_allowed=False,
                )
                await sync_to_async(
                    strict_controller.record_workflow_outcome,
                    thread_sensitive=True,
                )(
                    user_id=user_id,
                    project_id=project_id,
                    codebase_id=codebase_id,
                    preflight=preflight,
                    final_output=result,
                )
                return result

            retrieval = preflight.get('retrieval', {}) or {}
            contract = preflight.get('contract', {}) or {}
            initial_state['strict_contract'] = contract
            initial_state['strict_form_type'] = contract.get('form_type')
            initial_state['strict_features'] = contract.get('features', [])
            initial_state['strict_required_patterns'] = retrieval.get('required_pattern_types', [])
            initial_state['strict_selected_patterns'] = retrieval.get('selected_patterns', [])
            initial_state['strict_pattern_memory_context'] = retrieval.get('memory_context', '')
            initial_state['strict_combo_signature'] = retrieval.get('combo_signature')
            initial_state['pattern_coverage'] = retrieval.get('pattern_coverage')
            preflight_retrieval_quality = float(retrieval.get('retrieval_quality', 0.0) or 0.0)
            preflight_retrieval_score = float(
                retrieval.get('retrieval_score', preflight_retrieval_quality * 100.0) or 0.0
            )
            initial_state['retrieval_score'] = preflight_retrieval_score
            initial_state['retrieval_quality_score'] = preflight_retrieval_score
            initial_state['retrieval_required_coverage'] = float(retrieval.get('pattern_coverage', 0.0) or 0.0) * 100.0
            initial_state['retrieval_quality'] = (
                'sufficient'
                if preflight_retrieval_quality >= 0.30
                else 'insufficient'
            )
            initial_state['retrieval_top_candidates'] = retrieval.get('top_candidates', [])
            if contract.get('valid'):
                # Strict contract runs still need limited retries for transient parse/tag failures.
                # Structural failures are handled by edge-level classifier (fail closed).
                initial_state['max_regenerations'] = 3
             
            # Run workflow
            final_state = await self.app.ainvoke(initial_state)
            
            # Debug logging
            logger.info(f"final_state type: {type(final_state)}")
            logger.info(f"final_state keys: {final_state.keys() if isinstance(final_state, dict) else 'NOT A DICT'}")
            logger.info(f"Code generation completed with status: {final_state.get('status') if isinstance(final_state, dict) else 'UNKNOWN'}")
            
            # Ensure final_state is a dict
            if not isinstance(final_state, dict):
                logger.error(f"final_state is not a dict! Type: {type(final_state)}, Value: {final_state}")
                return {
                    'error': 'Workflow returned invalid state',
                    'details': str(final_state),
                    'code': {},
                    'status': 'failed'
                }
            
            # Return final output (ensure it's a dict)
            final_output = final_state.get('final_output', {})
            
            # Ensure final_output is a dict
            if not isinstance(final_output, dict):
                logger.error(f"final_output is not a dict, it's {type(final_output)}: {final_output}")
                final_output = {
                    'error': str(final_output) if final_output else 'Unknown error',
                    'code': {},
                    'status': 'failed'
                }
            
            # If complete_php is missing in final_output, recover from state using inline contract
            code_block = final_output.get('code', {}) if isinstance(final_output.get('code', {}), dict) else {}
            has_complete_php = bool((code_block.get('complete_php') or '').strip())
            workflow_status = str(final_state.get('status') or '').lower()
            if workflow_status == 'completed' and not has_complete_php:
                logger.warning("Missing complete_php in final_output, recovering from state")
                def _safe_strip(value):
                    if value is None:
                        return ''
                    if isinstance(value, str):
                        return value.strip()
                    return str(value).strip()

                recovered_complete_php = (
                    _safe_strip(final_state.get('complete_php')) or
                    _safe_strip((final_state.get('integrated_code', {}) or {}).get('complete_php')) or
                    _safe_strip(final_state.get('php_code'))
                )
                final_output['code'] = {'complete_php': recovered_complete_php}
                logger.info(f"Recovered complete_php length: {len(recovered_complete_php)} chars")
                if not recovered_complete_php:
                    final_output.setdefault('status', 'failed')
                    final_output.setdefault('error', 'Complete PHP generation failed - no code produced')

            final_validation = final_output.get('validation_result', {}) if isinstance(final_output, dict) else {}
            if not final_validation and isinstance(final_state, dict):
                final_validation = final_state.get('validation_result', {}) or {}

            final_validation_gate = resolve_authoritative_validation_gate(final_validation)
            validation_passed = bool(final_validation_gate.get('validation_passed'))
            block_save = bool(final_validation_gate.get('block_save'))
            persistence_allowed = validation_passed and not block_save and workflow_status == 'completed'
            final_output = strict_controller.attach_metadata(
                final_output,
                preflight,
                persistence_allowed=persistence_allowed,
            )
            await sync_to_async(
                strict_controller.record_workflow_outcome,
                thread_sensitive=True,
            )(
                user_id=user_id,
                project_id=project_id,
                codebase_id=codebase_id,
                preflight=preflight,
                final_state=final_state,
                final_output=final_output,
            )
            
            return final_output
            
        except Exception as e:
            logger.error(f"Workflow execution error: {str(e)}", exc_info=True)
            failure_result = {
                'error': 'Workflow execution failed',
                'details': str(e),
                'code': {},
                'status': 'failed'
            }
            failure_result = strict_controller.attach_metadata(
                failure_result,
                preflight,
                persistence_allowed=False,
            )
            if preflight:
                await sync_to_async(
                    strict_controller.record_workflow_outcome,
                    thread_sensitive=True,
                )(
                    user_id=user_id,
                    project_id=project_id,
                    codebase_id=codebase_id,
                    preflight=preflight,
                    final_state=initial_state,
                    final_output=failure_result,
                )
            return failure_result


# Initialize workflow
code_generation_workflow = CodeGenerationWorkflow()
