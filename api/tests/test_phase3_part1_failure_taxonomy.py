"""
PHASE 3 PART 3.1: FAILURE TAXONOMY TESTS

Tests for structured failure classification system.
"""

import pytest
from agents.utils.failure_taxonomy import (
    FailureTaxonomy,
    FailureCategory,
    FailureSeverity
)


class TestFailureTaxonomy:
    """Test failure taxonomy initialization and basic operations."""
    
    def test_initialization(self):
        """Test taxonomy initializes with all signatures."""
        taxonomy = FailureTaxonomy()
        
        assert taxonomy is not None
        assert len(taxonomy.signatures) > 0
        assert len(taxonomy.signatures) >= 20  # Should have at least 20 signatures
    
    def test_get_all_categories(self):
        """Test getting all failure categories."""
        taxonomy = FailureTaxonomy()
        categories = taxonomy.get_all_categories()
        
        assert len(categories) > 0
        assert FailureCategory.CONTRACT_MISMATCH in categories
        assert FailureCategory.MISSING_REQUIRED_SECTION in categories
        assert FailureCategory.LLM_REFUSAL in categories
    
    def test_get_signatures_by_severity(self):
        """Test filtering signatures by severity."""
        taxonomy = FailureTaxonomy()
        
        critical = taxonomy.get_signatures_by_severity(FailureSeverity.CRITICAL)
        high = taxonomy.get_signatures_by_severity(FailureSeverity.HIGH)
        
        assert len(critical) > 0
        assert len(high) > 0
        assert all(sig.severity == FailureSeverity.CRITICAL for sig in critical)


class TestContractFailures:
    """Test classification of contract-related failures."""
    
    def test_contract_mismatch(self):
        """Test detection of contract mismatch failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Validation contract mismatch: generator promised CRUD but validator expected only Read"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.CONTRACT_MISMATCH
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
        assert 'contract' in result['matched_keywords']
    
    def test_missing_required_section(self):
        """Test detection of missing required sections."""
        taxonomy = FailureTaxonomy()
        
        error = "PHP logic section is empty - cannot proceed"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.MISSING_REQUIRED_SECTION
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
    
    def test_incomplete_section(self):
        """Test detection of incomplete sections."""
        taxonomy = FailureTaxonomy()
        
        error = "Section completeness score 35% is below threshold of 40%"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.INCOMPLETE_SECTION
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] >= 0.5


class TestNamingFailures:
    """Test classification of naming-related failures."""
    
    def test_canonical_naming_failure(self):
        """Test detection of canonical naming extraction failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Table name is blank - canonical extraction failed"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.CANONICAL_NAMING_FAILURE
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
    
    def test_naming_mismatch(self):
        """Test detection of naming mismatches."""
        taxonomy = FailureTaxonomy()
        
        error = "Generated table name 'tblStudent' != requested name 'tblstudent' - naming mismatch detected"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.NAMING_MISMATCH
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] >= 0.5


class TestTemplateFailures:
    """Test classification of template-related failures."""
    
    def test_template_merge_failure(self):
        """Test detection of template merge failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Anchor merge failed: {{PHP_LOGIC}} anchor not found in template"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.TEMPLATE_MERGE_FAILURE
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
    
    def test_template_validation_failure(self):
        """Test detection of template validation failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Template missing required anchor: {{FORM_FIELDS}}"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.TEMPLATE_VALIDATION_FAILURE
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] >= 0.5


class TestEnterprisePatternFailures:
    """Test classification of enterprise pattern failures."""
    
    def test_missing_company_functions(self):
        """Test detection of missing company functions."""
        taxonomy = FailureTaxonomy()
        
        error = "Missing company function: db_insert not found in generated code"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.MISSING_COMPANY_FUNCTIONS
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5
    
    def test_missing_crud_handlers(self):
        """Test detection of missing CRUD handlers."""
        taxonomy = FailureTaxonomy()
        
        error = "CRUD handler missing: insert handler not found"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.MISSING_CRUD_HANDLERS
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5
    
    def test_missing_ajax_handlers(self):
        """Test detection of missing AJAX handlers."""
        taxonomy = FailureTaxonomy()
        
        error = "AJAX handler missing: GetMaxID not found"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.MISSING_AJAX_HANDLERS
        assert result['severity'] == FailureSeverity.MEDIUM
        assert result['confidence'] > 0.5


class TestFieldFailures:
    """Test classification of field-related failures."""
    
    def test_field_mismatch(self):
        """Test detection of field mismatches."""
        taxonomy = FailureTaxonomy()
        
        error = "Field mismatch: generated fields != requested fields"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.FIELD_MISMATCH
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5
    
    def test_missing_required_fields(self):
        """Test detection of missing required fields."""
        taxonomy = FailureTaxonomy()
        
        error = "Required field missing: Student_Name is mandatory but not found"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.MISSING_REQUIRED_FIELDS
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5
    
    def test_extra_fields(self):
        """Test detection of extra fields."""
        taxonomy = FailureTaxonomy()
        
        error = "Extra field generated: Address was not requested"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.EXTRA_FIELDS
        assert result['severity'] == FailureSeverity.MEDIUM
        assert result['confidence'] > 0.5


class TestValidationFailures:
    """Test classification of validation-related failures."""
    
    def test_validation_contract_mismatch(self):
        """Test detection of validation contract mismatches."""
        taxonomy = FailureTaxonomy()
        
        error = "Validator checking wrong contract: validation contract != generation contract"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.VALIDATION_CONTRACT_MISMATCH
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
    
    def test_dependency_check_failure(self):
        """Test detection of dependency check failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Pre-delete dependency check not found for tblcustomer"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.DEPENDENCY_CHECK_FAILURE
        assert result['severity'] == FailureSeverity.MEDIUM
        assert result['confidence'] > 0.5


class TestLLMFailures:
    """Test classification of LLM-related failures."""
    
    def test_llm_refusal(self):
        """Test detection of LLM refusals."""
        taxonomy = FailureTaxonomy()
        
        error = "LLM refused to generate: content policy violation"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.LLM_REFUSAL
        assert result['severity'] == FailureSeverity.CRITICAL
        assert result['confidence'] > 0.5
    
    def test_llm_incomplete_output(self):
        """Test detection of incomplete LLM output."""
        taxonomy = FailureTaxonomy()
        
        error = "LLM output truncated - generation incomplete"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.LLM_INCOMPLETE_OUTPUT
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5
    
    def test_llm_malformed_output(self):
        """Test detection of malformed LLM output."""
        taxonomy = FailureTaxonomy()
        
        error = "Cannot parse LLM output: invalid section format"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.LLM_MALFORMED_OUTPUT
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5


class TestSystemFailures:
    """Test classification of system-level failures."""
    
    def test_timeout(self):
        """Test detection of timeout failures."""
        taxonomy = FailureTaxonomy()
        
        error = "Generation timed out after 120 seconds - timeout exceeded"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.TIMEOUT
        assert result['severity'] == FailureSeverity.MEDIUM
        assert result['confidence'] >= 0.5
    
    def test_api_error(self):
        """Test detection of API errors."""
        taxonomy = FailureTaxonomy()
        
        error = "API error: HTTP error 500 - connection failed"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.API_ERROR
        assert result['severity'] == FailureSeverity.HIGH
        assert result['confidence'] > 0.5


class TestMultipleInputs:
    """Test classification with multiple input sources."""
    
    def test_classify_with_validation_errors(self):
        """Test classification using validation errors list."""
        taxonomy = FailureTaxonomy()
        
        validation_errors = [
            "Missing company function: db_insert",
            "Missing company function: db_update",
            "CRUD handler not found"
        ]
        
        result = taxonomy.classify_failure(validation_errors=validation_errors)
        
        assert result['category'] == FailureCategory.MISSING_COMPANY_FUNCTIONS
        assert result['confidence'] > 0.5
    
    def test_classify_with_log_context(self):
        """Test classification using log context."""
        taxonomy = FailureTaxonomy()
        
        log_context = """
        INFO: Starting generation
        ERROR: Template merge failed
        ERROR: Anchor {{PHP_LOGIC}} not found in template
        ERROR: Cannot proceed with merge
        """
        
        result = taxonomy.classify_failure(log_context=log_context)
        
        assert result['category'] == FailureCategory.TEMPLATE_MERGE_FAILURE
        assert result['confidence'] > 0.5
    
    def test_classify_with_generated_code(self):
        """Test classification by analyzing generated code."""
        taxonomy = FailureTaxonomy()
        
        generated_code = """
        <?php
        // Some code but missing db_insert, db_update, db_delete
        function getData() {
            return [];
        }
        ?>
        """
        
        error = "Missing company functions in generated code: db_insert not found"
        result = taxonomy.classify_failure(
            error_message=error,
            generated_code=generated_code
        )
        
        assert result['category'] == FailureCategory.MISSING_COMPANY_FUNCTIONS
        assert result['confidence'] >= 0.5


class TestUnknownFailures:
    """Test handling of unknown/unclassified failures."""
    
    def test_unknown_failure_with_no_input(self):
        """Test classification with no input returns unknown."""
        taxonomy = FailureTaxonomy()
        
        result = taxonomy.classify_failure()
        
        assert result['category'] == FailureCategory.UNKNOWN
        assert result['confidence'] == 0.0
    
    def test_unknown_failure_with_unmatched_text(self):
        """Test classification with unmatched text returns unknown."""
        taxonomy = FailureTaxonomy()
        
        error = "Something completely random and unrelated xyz123"
        result = taxonomy.classify_failure(error_message=error)
        
        assert result['category'] == FailureCategory.UNKNOWN
        assert result['confidence'] == 0.0


class TestRecoveryStrategies:
    """Test recovery strategy retrieval."""
    
    def test_get_recovery_strategy(self):
        """Test getting recovery strategy for a category."""
        taxonomy = FailureTaxonomy()
        
        strategy = taxonomy.get_recovery_strategy(FailureCategory.CONTRACT_MISMATCH)
        
        assert strategy is not None
        assert len(strategy) > 0
        assert "contract" in strategy.lower()
    
    def test_recovery_strategy_in_classification(self):
        """Test recovery strategy is included in classification result."""
        taxonomy = FailureTaxonomy()
        
        error = "Contract mismatch detected"
        result = taxonomy.classify_failure(error_message=error)
        
        assert 'recovery_strategy' in result
        assert result['recovery_strategy'] is not None
        assert len(result['recovery_strategy']) > 0
