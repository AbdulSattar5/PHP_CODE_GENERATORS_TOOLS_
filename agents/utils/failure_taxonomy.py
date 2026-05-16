"""
PHASE 3 PART 3.1: FAILURE TAXONOMY

Structured failure classification system for code generation failures.
Categorizes failures into actionable types with specific recovery strategies.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


class FailureCategory(Enum):
    """
    Primary failure categories based on log analysis.
    Each category has specific detection patterns and recovery strategies.
    """
    # Contract Issues (Root Cause: Mismatch between generator and validator)
    CONTRACT_MISMATCH = "contract_mismatch"  # Generator promised X, validator expected Y
    MISSING_REQUIRED_SECTION = "missing_required_section"  # Empty PHP logic, form fields, etc.
    INCOMPLETE_SECTION = "incomplete_section"  # Section exists but < 40% complete
    
    # Naming Issues (Root Cause: Non-deterministic extraction)
    CANONICAL_NAMING_FAILURE = "canonical_naming_failure"  # Blank table/file/title
    NAMING_MISMATCH = "naming_mismatch"  # Generator used wrong names
    
    # Template Issues (Root Cause: Merge failures)
    TEMPLATE_MERGE_FAILURE = "template_merge_failure"  # Anchor-based merge failed
    TEMPLATE_VALIDATION_FAILURE = "template_validation_failure"  # Template missing anchors
    
    # Enterprise Pattern Issues (Root Cause: Missing company-specific code)
    MISSING_COMPANY_FUNCTIONS = "missing_company_functions"  # db_insert, getvalue, etc.
    MISSING_CRUD_HANDLERS = "missing_crud_handlers"  # Insert/Update/Delete handlers
    MISSING_AJAX_HANDLERS = "missing_ajax_handlers"  # GetMaxID, dropdown loaders
    
    # Field Issues (Root Cause: Field mismatch)
    FIELD_MISMATCH = "field_mismatch"  # Generated fields != requested fields
    MISSING_REQUIRED_FIELDS = "missing_required_fields"  # Required fields not generated
    EXTRA_FIELDS = "extra_fields"  # Generated fields not requested
    
    # Validation Issues (Root Cause: Validation contract mismatch)
    VALIDATION_CONTRACT_MISMATCH = "validation_contract_mismatch"  # Validator checking wrong things
    DEPENDENCY_CHECK_FAILURE = "dependency_check_failure"  # Pre-delete checks missing
    
    # LLM Issues (Root Cause: LLM output problems)
    LLM_REFUSAL = "llm_refusal"  # LLM refused to generate
    LLM_INCOMPLETE_OUTPUT = "llm_incomplete_output"  # LLM stopped mid-generation
    LLM_MALFORMED_OUTPUT = "llm_malformed_output"  # LLM output not parseable
    
    # System Issues (Root Cause: System-level problems)
    TIMEOUT = "timeout"  # Generation timed out
    API_ERROR = "api_error"  # API call failed
    UNKNOWN = "unknown"  # Unclassified failure


class FailureSeverity(Enum):
    """Failure severity levels for prioritization."""
    CRITICAL = "critical"  # Blocks generation completely
    HIGH = "high"  # Major functionality missing
    MEDIUM = "medium"  # Partial functionality missing
    LOW = "low"  # Minor issues


@dataclass
class FailureSignature:
    """
    Signature for detecting specific failure patterns.
    Each signature has detection patterns and metadata.
    """
    category: FailureCategory
    severity: FailureSeverity
    patterns: List[str]  # Regex patterns to match in logs/errors
    keywords: List[str]  # Keywords to look for
    description: str
    recovery_strategy: str


class FailureTaxonomy:
    """
    Failure taxonomy system for classifying and analyzing generation failures.
    
    Features:
    - Structured failure classification
    - Pattern-based detection
    - Severity assessment
    - Recovery strategy mapping
    """
    
    def __init__(self):
        """Initialize failure taxonomy with all known failure signatures."""
        self.signatures = self._build_failure_signatures()
        logger.info(f"✅ Initialized FailureTaxonomy with {len(self.signatures)} signatures")
    
    def _build_failure_signatures(self) -> List[FailureSignature]:
        """
        Build comprehensive failure signature database.
        Based on analysis of logs/gencode.log.
        """
        return [
            # CONTRACT ISSUES
            FailureSignature(
                category=FailureCategory.CONTRACT_MISMATCH,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"validation.*contract.*mismatch",
                    r"generator.*promised.*validator.*expected",
                    r"contract.*alignment.*failed"
                ],
                keywords=["contract", "mismatch", "alignment", "promised", "expected"],
                description="Generator and validator using different contracts",
                recovery_strategy="Rebuild validation contract from generation plan"
            ),
            
            FailureSignature(
                category=FailureCategory.MISSING_REQUIRED_SECTION,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"PHP.*logic.*(empty|blank)",
                    r"form.*fields.*(empty|blank)",
                    r"required.*section.*(missing|empty|blank)",
                    r"section.*(blank|empty)"
                ],
                keywords=["empty", "blank", "missing", "required section", "php logic", "form fields"],
                description="Critical section (PHP logic, form fields) is empty",
                recovery_strategy="Fail fast and retry with explicit section requirements"
            ),
            
            FailureSignature(
                category=FailureCategory.INCOMPLETE_SECTION,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"completeness.*score.*(below|less|under).*threshold",
                    r"section.*incomplete",
                    r"completeness.*\d+%",
                    r"score.*below"
                ],
                keywords=["incomplete", "completeness", "score", "threshold", "below"],
                description="Section exists but completeness < 40%",
                recovery_strategy="Auto-repair missing blocks or retry with enhanced prompt"
            ),
            
            # NAMING ISSUES
            FailureSignature(
                category=FailureCategory.CANONICAL_NAMING_FAILURE,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"table.*name.*blank",
                    r"file.*name.*blank",
                    r"title.*blank",
                    r"canonical.*extraction.*failed"
                ],
                keywords=["blank", "canonical", "extraction failed", "table name", "file name"],
                description="Failed to extract canonical naming (table/file/title)",
                recovery_strategy="Use RequestSchemaParser for deterministic extraction"
            ),
            
            FailureSignature(
                category=FailureCategory.NAMING_MISMATCH,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"generated.*name.*!=.*requested.*name",
                    r"table.*name.*mismatch",
                    r"file.*name.*mismatch",
                    r"name.*mismatch"
                ],
                keywords=["mismatch", "name", "generated", "requested", "table", "file"],
                description="Generated code uses wrong table/file names",
                recovery_strategy="Enforce canonical names in generation prompt"
            ),
            
            # TEMPLATE ISSUES
            FailureSignature(
                category=FailureCategory.TEMPLATE_MERGE_FAILURE,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"anchor.*merge.*failed",
                    r"template.*merge.*error",
                    r"anchor.*not.*found"
                ],
                keywords=["anchor", "merge", "failed", "template"],
                description="Anchor-based template merge failed",
                recovery_strategy="Validate template has all required anchors"
            ),
            
            FailureSignature(
                category=FailureCategory.TEMPLATE_VALIDATION_FAILURE,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"template.*missing.*anchor",
                    r"anchor.*validation.*failed",
                    r"required.*anchor.*not.*found",
                    r"missing.*required.*anchor"
                ],
                keywords=["template", "anchor", "missing", "validation", "required"],
                description="Template missing required anchors",
                recovery_strategy="Use validated template with all anchors"
            ),
            
            # ENTERPRISE PATTERN ISSUES
            FailureSignature(
                category=FailureCategory.MISSING_COMPANY_FUNCTIONS,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"missing.*company.*function",
                    r"db_insert.*not.*found",
                    r"db_update.*not.*found",
                    r"db_delete.*not.*found",
                    r"getvalue.*not.*found",
                    r"getrows.*not.*found",
                    r"company.*function.*not.*found"
                ],
                keywords=["missing", "company function", "db_insert", "db_update", "db_delete", "getvalue", "function", "not found"],
                description="Missing company-specific database functions",
                recovery_strategy="Auto-inject company function calls or retry with examples"
            ),
            
            FailureSignature(
                category=FailureCategory.MISSING_CRUD_HANDLERS,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"CRUD.*handler.*missing",
                    r"insert.*handler.*not.*found",
                    r"update.*handler.*not.*found",
                    r"delete.*handler.*not.*found"
                ],
                keywords=["CRUD", "handler", "missing", "insert", "update", "delete"],
                description="Missing CRUD operation handlers",
                recovery_strategy="Auto-repair with CRUD handler templates"
            ),
            
            FailureSignature(
                category=FailureCategory.MISSING_AJAX_HANDLERS,
                severity=FailureSeverity.MEDIUM,
                patterns=[
                    r"AJAX.*handler.*missing",
                    r"GetMaxID.*not.*found",
                    r"dropdown.*loader.*missing"
                ],
                keywords=["AJAX", "handler", "missing", "GetMaxID", "dropdown"],
                description="Missing AJAX handlers (GetMaxID, dropdowns)",
                recovery_strategy="Auto-inject AJAX handler templates"
            ),
            
            # FIELD ISSUES
            FailureSignature(
                category=FailureCategory.FIELD_MISMATCH,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"field.*mismatch",
                    r"generated.*fields.*!=.*requested.*fields",
                    r"field.*count.*mismatch"
                ],
                keywords=["field", "mismatch", "generated", "requested"],
                description="Generated fields don't match requested fields",
                recovery_strategy="Enforce exact field list in generation contract"
            ),
            
            FailureSignature(
                category=FailureCategory.MISSING_REQUIRED_FIELDS,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"required.*field.*missing",
                    r"mandatory.*field.*not.*found"
                ],
                keywords=["required", "mandatory", "field", "missing"],
                description="Required fields not generated",
                recovery_strategy="Fail fast and retry with explicit field requirements"
            ),
            
            FailureSignature(
                category=FailureCategory.EXTRA_FIELDS,
                severity=FailureSeverity.MEDIUM,
                patterns=[
                    r"extra.*field.*generated",
                    r"unexpected.*field.*found"
                ],
                keywords=["extra", "unexpected", "field"],
                description="Generated fields not requested by user",
                recovery_strategy="Filter generated fields to match request"
            ),
            
            # VALIDATION ISSUES
            FailureSignature(
                category=FailureCategory.VALIDATION_CONTRACT_MISMATCH,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"validator.*checking.*wrong.*contract",
                    r"validation.*contract.*!=.*generation.*contract"
                ],
                keywords=["validation", "contract", "mismatch", "checking"],
                description="Validator using different contract than generator",
                recovery_strategy="Align validation contract with generation contract"
            ),
            
            FailureSignature(
                category=FailureCategory.DEPENDENCY_CHECK_FAILURE,
                severity=FailureSeverity.MEDIUM,
                patterns=[
                    r"dependency.*check.*missing",
                    r"pre-delete.*check.*not.*found"
                ],
                keywords=["dependency", "pre-delete", "check", "missing"],
                description="Pre-delete dependency checks missing",
                recovery_strategy="Auto-inject dependency check templates"
            ),
            
            # LLM ISSUES
            FailureSignature(
                category=FailureCategory.LLM_REFUSAL,
                severity=FailureSeverity.CRITICAL,
                patterns=[
                    r"LLM.*refused",
                    r"content.*policy.*violation",
                    r"I.*cannot.*generate"
                ],
                keywords=["refused", "policy", "cannot generate"],
                description="LLM refused to generate code",
                recovery_strategy="Use refusal recovery prompt with benign framing"
            ),

            FailureSignature(
                category=FailureCategory.LLM_INCOMPLETE_OUTPUT,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"placeholder/truncated.*detected",
                    r"placeholder.*content.*detected",
                    r"rest\s+of\s+code\s+here",
                    r"populate\s+options",
                    r"\bTODO\b"
                ],
                keywords=["placeholder", "truncated", "todo", "rest of code"],
                description="Generated output contains placeholder/truncation markers",
                recovery_strategy="Retry with strict no-placeholder constraints and section completion checks"
            ),
             
            FailureSignature(
                category=FailureCategory.LLM_INCOMPLETE_OUTPUT,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"LLM.*output.*truncated",
                    r"generation.*incomplete",
                    r"output.*stopped.*mid"
                ],
                keywords=["truncated", "incomplete", "stopped"],
                description="LLM stopped generating mid-output",
                recovery_strategy="Retry with continuation prompt"
            ),
            
            FailureSignature(
                category=FailureCategory.LLM_MALFORMED_OUTPUT,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"LLM.*output.*malformed",
                    r"cannot.*parse.*LLM.*output",
                    r"invalid.*section.*format"
                ],
                keywords=["malformed", "parse", "invalid format"],
                description="LLM output not parseable",
                recovery_strategy="Retry with explicit format instructions"
            ),
            
            # SYSTEM ISSUES
            FailureSignature(
                category=FailureCategory.TIMEOUT,
                severity=FailureSeverity.MEDIUM,
                patterns=[
                    r"timeout",
                    r"timed.*out",
                    r"generation.*timed.*out",
                    r"exceeded.*time.*limit",
                    r"time.*limit"
                ],
                keywords=["timeout", "timed out", "time limit", "exceeded", "generation"],
                description="Generation exceeded time limit",
                recovery_strategy="Retry with shorter context or simpler prompt"
            ),
            
            FailureSignature(
                category=FailureCategory.API_ERROR,
                severity=FailureSeverity.HIGH,
                patterns=[
                    r"API.*error",
                    r"HTTP.*error.*\d+",
                    r"connection.*failed"
                ],
                keywords=["API error", "HTTP error", "connection failed"],
                description="API call failed",
                recovery_strategy="Retry with exponential backoff"
            ),
        ]
    
    def classify_failure(
        self,
        error_message: str = "",
        validation_errors: List[str] = None,
        log_context: str = "",
        generated_code: str = ""
    ) -> Dict[str, Any]:
        """
        Classify a failure based on error messages, validation errors, and context.
        
        Returns:
            {
                'category': FailureCategory,
                'severity': FailureSeverity,
                'description': str,
                'recovery_strategy': str,
                'confidence': float,  # 0.0 to 1.0
                'matched_patterns': List[str],
                'matched_keywords': List[str]
            }
        """
        # Combine all input text for analysis
        full_text = " ".join([
            error_message or "",
            " ".join(validation_errors or []),
            log_context or "",
            generated_code[:1000] if generated_code else ""  # First 1000 chars only
        ]).lower()
        
        if not full_text.strip():
            return self._unknown_failure()
        
        # Score each signature
        scored_signatures = []
        for signature in self.signatures:
            score = self._score_signature(signature, full_text)
            if score > 0:
                scored_signatures.append((signature, score))
        
        if not scored_signatures:
            return self._unknown_failure()
        
        # Get best match
        best_signature, best_score = max(scored_signatures, key=lambda x: x[1])
        
        # Extract matched patterns and keywords
        matched_patterns = [
            pattern for pattern in best_signature.patterns
            if re.search(pattern, full_text, re.IGNORECASE)
        ]
        matched_keywords = [
            keyword for keyword in best_signature.keywords
            if keyword.lower() in full_text
        ]
        
        result = {
            'category': best_signature.category,
            'severity': best_signature.severity,
            'description': best_signature.description,
            'recovery_strategy': best_signature.recovery_strategy,
            'confidence': min(best_score, 1.0),
            'matched_patterns': matched_patterns,
            'matched_keywords': matched_keywords
        }
        
        logger.info(f"🔍 Classified failure: {best_signature.category.value} "
                   f"(severity={best_signature.severity.value}, confidence={result['confidence']:.2f})")
        
        return result
    
    def _score_signature(self, signature: FailureSignature, text: str) -> float:
        """
        Score how well a signature matches the given text.
        Returns score between 0.0 and 1.0.
        """
        score = 0.0
        
        # Pattern matches (higher weight)
        pattern_matches = sum(
            1 for pattern in signature.patterns
            if re.search(pattern, text, re.IGNORECASE)
        )
        if signature.patterns:
            pattern_score = pattern_matches / len(signature.patterns)
            score += pattern_score * 0.7  # 70% weight (increased from 60%)
        
        # Keyword matches (lower weight)
        keyword_matches = sum(
            1 for keyword in signature.keywords
            if keyword.lower() in text
        )
        if signature.keywords:
            keyword_score = keyword_matches / len(signature.keywords)
            score += keyword_score * 0.3  # 30% weight (decreased from 40%)
        
        # Boost score if we have strong matches
        if pattern_matches > 0 and keyword_matches >= 2:
            score = min(score * 1.2, 1.0)  # 20% boost, capped at 1.0
        
        return score
    
    def _unknown_failure(self) -> Dict[str, Any]:
        """Return classification for unknown failure."""
        return {
            'category': FailureCategory.UNKNOWN,
            'severity': FailureSeverity.MEDIUM,
            'description': 'Unclassified failure - no matching signature found',
            'recovery_strategy': 'Generic retry with enhanced logging',
            'confidence': 0.0,
            'matched_patterns': [],
            'matched_keywords': []
        }
    
    def get_recovery_strategy(self, category: FailureCategory) -> str:
        """Get recovery strategy for a specific failure category."""
        for signature in self.signatures:
            if signature.category == category:
                return signature.recovery_strategy
        return "Generic retry"
    
    def get_all_categories(self) -> List[FailureCategory]:
        """Get all failure categories."""
        return list(FailureCategory)
    
    def get_signatures_by_severity(self, severity: FailureSeverity) -> List[FailureSignature]:
        """Get all signatures for a specific severity level."""
        return [sig for sig in self.signatures if sig.severity == severity]
