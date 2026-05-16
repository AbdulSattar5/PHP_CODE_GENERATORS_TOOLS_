"""
Simplified LangGraph edge functions for complete-PHP workflow.
"""

import logging
from .state import AgentState
from agents.config.pipeline_constants import (
    MAX_RETRIES_TRANSIENT,
    STRUCTURAL_FAILURE_KEYWORDS,
)

logger = logging.getLogger(__name__)


def resolve_authoritative_validation_gate(validation_result: dict) -> dict:
    """
    Normalize validation flags so every workflow edge/finalizer uses one decision model.
    """
    validation_result = validation_result or {}
    authoritative_gate = validation_result.get('authoritative_gate') or {}
    approval_status = str(validation_result.get('approval_status', '')).lower()
    if isinstance(authoritative_gate, dict) and 'final_pass' in authoritative_gate:
        validation_passed = bool(authoritative_gate.get('final_pass'))
    else:
        validation_passed = bool(
            validation_result.get('validation_passed')
            if 'validation_passed' in validation_result
            else approval_status == 'approved'
        )
    if not approval_status:
        approval_status = 'approved' if validation_passed else 'needs_revision'
    block_generation = bool(validation_result.get('block_generation'))
    block_save = bool(
        validation_result.get('block_save')
        or block_generation
        or approval_status == 'needs_revision'
        or not validation_passed
    )
    regeneration_required = bool(
        validation_result.get('regeneration_required')
        or block_generation
        or not validation_passed
    )
    return {
        'approval_status': approval_status,
        'validation_passed': validation_passed,
        'block_generation': block_generation,
        'block_save': block_save,
        'regeneration_required': regeneration_required,
    }


def classify_failure_type(state: dict) -> str:
    """
    Classify validation failures:
    - transient: recoverable parse/tag/format output issues
    - structural: contract/retrieval/master-detail/canonical mismatches
    """
    validation_result = state.get('validation_result', {}) or {}
    validation_errors = state.get('validation_errors', []) or []
    validation_reason = str(state.get('validation_reason') or validation_result.get('validation_reason') or '').lower()
    critical_errors = validation_result.get('critical_errors', []) or []
    all_issues = (validation_result.get('all_issues') or {})
    critical_issues = list(all_issues.get('critical') or [])
    major_issues = list(all_issues.get('major') or [])

    structural_keywords = list(STRUCTURAL_FAILURE_KEYWORDS) + [
        "0/",
        "missing required",
        "forbidden",
        "field contract",
        "detail rows",
        "pre-delete",
        "dependency",
    ]

    combined_parts = [validation_reason]
    combined_parts.extend(str(item).lower() for item in validation_errors)
    combined_parts.extend(str(item).lower() for item in critical_errors)
    combined_parts.extend(str(item).lower() for item in critical_issues)
    combined_parts.extend(str(item).lower() for item in major_issues)
    combined_text = " ".join(part for part in combined_parts if part).strip()

    for keyword in structural_keywords:
        if keyword in combined_text:
            return "structural"

    return "transient"


def should_continue_after_retrieval(state: AgentState) -> str:
    """Fail closed before generation when strict retrieval gate is blocked."""
    if bool(state.get('retrieval_gate_blocked')):
        logger.error(
            "Retrieval gate blocked generation: %s",
            state.get('retrieval_gate_reason') or state.get('validation_reason') or 'unknown_reason'
        )
        return "fail"
    return "continue"


def should_regenerate(state: AgentState) -> str:
    """Decide whether workflow should regenerate code or finalize."""
    # Inline mode can still regenerate when validators mark output unusable.
    if state.get('is_inline_generation', False):
        validation_result = state.get('validation_result', {}) or {}
        gate = resolve_authoritative_validation_gate(validation_result)
        regeneration_required = bool(gate.get('regeneration_required'))

        if not regeneration_required:
            logger.info("Inline mode: Finalizing")
            return "finalize"

        failure_type = classify_failure_type(state)
        if failure_type == 'structural':
            logger.warning("Inline mode: structural validation failure; failing closed")
            state['status'] = 'failed'
            state['block_save'] = True
            state['validation_passed'] = False
            state['validation_reason'] = (
                validation_result.get('validation_reason')
                or "structural_validation_failure"
            )
            return "fail"

        configured_max = int(state.get('max_regenerations', MAX_RETRIES_TRANSIENT) or MAX_RETRIES_TRANSIENT)
        max_regenerations = configured_max if configured_max > 0 else MAX_RETRIES_TRANSIENT
        max_regenerations = min(max_regenerations, MAX_RETRIES_TRANSIENT)
        regeneration_count = int(state.get('regeneration_count', 0) or 0)

        if regeneration_count < max_regenerations:
            logger.info(
                "Inline mode: Validation requested regeneration "
                f"({regeneration_count}/{max_regenerations}, type={failure_type})"
            )
            return "regenerate"

        logger.warning(
            "Inline mode: max regenerations reached "
            f"({regeneration_count}/{max_regenerations}, type={failure_type}); failing closed"
        )
        state['status'] = 'failed'
        state['block_save'] = True
        state['validation_passed'] = False
        state['validation_reason'] = (
            validation_result.get('validation_reason')
            or f"{failure_type}_retry_exhausted_{regeneration_count}_{max_regenerations}"
        )
        return "fail"

    validation_result = state.get('validation_result', {})
    validation_score = validation_result.get('score', 0)

    critical_errors = validation_result.get('critical_issues', [])
    if len(critical_errors) > 0:
        logger.info(f"Critical errors detected ({len(critical_errors)}), regenerating")
        return "regenerate"

    logger.info(f"Validation passed (score: {validation_score}%), finalizing")
    return "finalize"


def check_critical_errors(state: AgentState) -> str:
    """Check for critical errors that should fail finalization."""
    validation_result = state.get('validation_result', {}) or {}
    gate = resolve_authoritative_validation_gate(validation_result)
    if gate.get('block_save'):
        logger.error(
            "Validation unresolved at finalize boundary "
            f"(block_generation={validation_result.get('block_generation')}, "
            f"approval_status={gate.get('approval_status')}, "
            f"validation_passed={validation_result.get('validation_passed')})"
        )
        return "fail"

    validation_errors = state.get('validation_errors', [])

    critical_errors = []
    for error in validation_errors:
        if isinstance(error, dict) and error.get('severity') == 'critical':
            critical_errors.append(error)
        elif isinstance(error, str) and 'critical' in error.lower():
            critical_errors.append(error)

    if len(critical_errors) > 8:
        logger.error(f"Too many critical errors ({len(critical_errors)})")
        return "fail"

    return "continue"
