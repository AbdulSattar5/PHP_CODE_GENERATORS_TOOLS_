"""
PHASE 3 PART 3.1: FAILURE TAXONOMY INTEGRATION TESTS

Tests that FailureTaxonomy is properly integrated into EnterpriseValidator.
"""

import pytest
from agents.graph.enterprise_validator import EnterpriseValidator
from agents.utils.failure_taxonomy import FailureCategory, FailureSeverity


class TestTaxonomyIntegration:
    """Test that taxonomy is integrated into validator."""
    
    def test_validator_has_taxonomy(self):
        """Test validator initializes with taxonomy."""
        validator = EnterpriseValidator()
        
        assert hasattr(validator, 'taxonomy')
        assert validator.taxonomy is not None
    
    def test_validation_failure_classified(self):
        """Test that validation failures are classified."""
        validator = EnterpriseValidator()
        
        # Generate code with missing company functions
        code = """
        <?php
        // Missing db_insert, db_update, db_delete
        function getData() {
            return [];
        }
        ?>
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': ['Save', 'Update', 'Delete'],
            'required_fields': ['Code', 'Name']
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        # Should fail
        assert not is_valid
        assert len(errors) > 0
        
        # Should have failure classification
        result = validator.get_last_validation_result()
        assert 'failure_classification' in result
        assert result['failure_classification'] is not None
        
        classification = result['failure_classification']
        assert 'category' in classification
        assert 'severity' in classification
        assert 'recovery_strategy' in classification
    
    def test_missing_company_functions_classified(self):
        """Test missing company functions are classified correctly."""
        validator = EnterpriseValidator()
        
        code = "<?php echo 'test'; ?>"
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': [],
            'required_fields': []
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        result = validator.get_last_validation_result()
        classification = result['failure_classification']
        
        # Should classify as missing company functions
        assert classification['category'] == FailureCategory.MISSING_COMPANY_FUNCTIONS
        assert classification['severity'] == FailureSeverity.HIGH
    
    def test_missing_crud_handlers_classified(self):
        """Test missing CRUD handlers are classified correctly."""
        validator = EnterpriseValidator()
        
        code = """
        <?php
        // Has functions but no handlers
        db_insert($table, $data);
        db_update($table, $data, $where);
        db_delete($table, $where);
        ?>
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': ['Save', 'Update', 'Delete'],
            'required_fields': []
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        result = validator.get_last_validation_result()
        classification = result['failure_classification']
        
        # Should classify as missing CRUD handlers
        assert classification['category'] == FailureCategory.MISSING_CRUD_HANDLERS
        assert classification['severity'] == FailureSeverity.HIGH
    
    def test_incomplete_section_classified(self):
        """Test incomplete sections are classified correctly."""
        validator = EnterpriseValidator()
        
        # Code with some CRUD but incomplete
        code = """
        <?php
        db_insert($table, $data);
        // Missing update, delete, handlers
        ?>
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': ['Save', 'Update', 'Delete'],
            'required_fields': []
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        result = validator.get_last_validation_result()
        classification = result['failure_classification']
        
        # Should have low completeness score
        assert scores['overall'] < 50  # Adjusted threshold
        assert classification['category'] in [
            FailureCategory.INCOMPLETE_SECTION,
            FailureCategory.MISSING_COMPANY_FUNCTIONS,
            FailureCategory.MISSING_CRUD_HANDLERS
        ]
    
    def test_field_mismatch_classified(self):
        """Test field mismatches are classified correctly."""
        validator = EnterpriseValidator()
        
        code = """
        <?php
        db_insert($table, $data);
        db_update($table, $data, $where);
        db_delete($table, $where);
        ?>
        <form>
            <input name="WrongField1" />
            <input name="WrongField2" />
        </form>
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': [],
            'required_fields': ['Code', 'Name', 'Description']
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        result = validator.get_last_validation_result()
        classification = result['failure_classification']
        
        # Should classify as field or handler mismatch
        assert classification['category'] in [
            FailureCategory.FIELD_MISMATCH,
            FailureCategory.MISSING_REQUIRED_FIELDS,
            FailureCategory.MISSING_CRUD_HANDLERS  # Can also be classified as this
        ]
    
    def test_recovery_strategy_provided(self):
        """Test that recovery strategy is provided for failures."""
        validator = EnterpriseValidator()
        
        code = "<?php echo 'minimal'; ?>"
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': ['Save', 'Update', 'Delete'],
            'required_fields': ['Code', 'Name']
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        result = validator.get_last_validation_result()
        classification = result['failure_classification']
        
        # Should have recovery strategy
        assert 'recovery_strategy' in classification
        assert len(classification['recovery_strategy']) > 0
        assert isinstance(classification['recovery_strategy'], str)
    
    def test_successful_validation_no_classification(self):
        """Test that successful validation has no failure classification."""
        validator = EnterpriseValidator()
        
        # Complete valid code
        code = """
        <?php
        db_insert($table, $data);
        db_update($table, $data, $where);
        db_delete($table, $where);
        db_getRecord($table, $where);
        
        switch($Action) {
            case 'Save':
                db_insert($table, $data);
                break;
            case 'Update':
                db_update($table, $data, $where);
                break;
            case 'Delete':
                db_delete($table, $where);
                break;
            case 'Edit':
                $data = db_getRecord($table, $where);
                break;
        }
        ?>
        <form>
            <input name="Code" />
            <input name="Name" />
        </form>
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete'],
            'required_handlers': ['Save', 'Update', 'Delete', 'Edit'],
            'required_fields': ['Code', 'Name']
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        # Should pass
        assert is_valid
        assert len(errors) == 0
        
        # Should have no failure classification
        result = validator.get_last_validation_result()
        assert result['failure_classification'] is None
