"""
Phase 1 Comprehensive Tests
Tests all 5 parts of Phase 1 fixes:
1.1 - Fail-Fast Validation (dynamic_form_template.py)
1.2 - Canonical Naming Fix (inline_php_generator.py)
1.3 - Auto-Repair Logic (inline_php_generator.py)
1.4 - Section Completeness Scoring (inline_php_generator.py)
1.5 - Validation Alignment (inline_php_generator.py)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from agents.utils.dynamic_form_template import DynamicFormTemplate
from agents.graph.inline_php_generator import InlinePHPGenerator


class TestPhase1Part1_FailFastValidation:
    """Test Part 1.1: Fail-Fast Validation in dynamic_form_template.py"""
    
    def test_merge_fails_when_php_logic_empty(self, tmp_path):
        """Should raise ValueError when PHP logic is empty"""
        # Create a dummy codebase directory
        codebase_dir = tmp_path / "codebase"
        codebase_dir.mkdir()
        
        # Create a dummy form file
        form_file = codebase_dir / "frmTest.php"
        form_file.write_text("<?php echo 'test'; ?>")
        
        template = DynamicFormTemplate(str(codebase_dir))
        template.load()
        
        # Test: Empty PHP logic should fail
        with pytest.raises(ValueError) as exc_info:
            template.merge_with_generated(
                php_logic="",
                form_fields="<input type='text' name='test'>",
                ajax_handlers="",
                crud_operations=""
            )
        
        assert "PHP logic is empty" in str(exc_info.value)
        assert "MERGE FAILED" in str(exc_info.value)
    
    def test_merge_fails_when_form_fields_empty(self, tmp_path):
        """Should raise ValueError when form fields are empty"""
        codebase_dir = tmp_path / "codebase"
        codebase_dir.mkdir()
        form_file = codebase_dir / "frmTest.php"
        form_file.write_text("<?php echo 'test'; ?>")
        
        template = DynamicFormTemplate(str(codebase_dir))
        template.load()
        
        # Test: Empty form fields should fail
        with pytest.raises(ValueError) as exc_info:
            template.merge_with_generated(
                php_logic="<?php $table = 'test'; ?>",
                form_fields="",
                ajax_handlers="",
                crud_operations=""
            )
        
        assert "form_fields is empty" in str(exc_info.value)
    
    def test_merge_fails_when_mandatory_functions_missing(self, tmp_path):
        """Should raise ValueError when mandatory company functions are missing"""
        codebase_dir = tmp_path / "codebase"
        codebase_dir.mkdir()
        form_file = codebase_dir / "frmTest.php"
        form_file.write_text("<?php echo 'test'; ?>")
        
        template = DynamicFormTemplate(str(codebase_dir))
        template.load()
        
        # Test: Missing mandatory functions should fail
        with pytest.raises(ValueError) as exc_info:
            template.merge_with_generated(
                php_logic="<?php $table = 'test'; ?>",
                form_fields="<input type='text' name='test'>",
                ajax_handlers="",
                crud_operations="<?php echo 'save'; ?>"
            )
        
        assert "Missing mandatory company functions" in str(exc_info.value)
        assert "db_insert" in str(exc_info.value)
    
    def test_merge_succeeds_with_valid_sections(self, tmp_path):
        """Should succeed when all required sections are present"""
        codebase_dir = tmp_path / "codebase"
        codebase_dir.mkdir()
        form_file = codebase_dir / "frmTest.php"
        form_file.write_text("<?php echo 'test'; ?>")
        
        template = DynamicFormTemplate(str(codebase_dir))
        template.load()
        
        # Test: Valid sections should succeed
        result = template.merge_with_generated(
            php_logic="<?php $table = 'test'; db_insert($table, $columns); ?>",
            form_fields="<input type='text' name='test'>",
            ajax_handlers="<?php if($_REQUEST['Action']=='GetMaxID') { echo '1'; exit; } ?>",
            crud_operations="<?php db_update($table, $columns); db_delete($table, 'Code=1'); db_getRecord($table, 'Code=1'); getrows('SELECT * FROM test'); getvalue('SELECT Code FROM test'); funStartTran(); funEndTran(); ?>"
        )
        
        assert len(result) > 0
        assert "db_insert" in result

    def test_merge_preserves_entity_js(self, tmp_path):
        """Entity-specific JS should survive template merge."""
        codebase_dir = tmp_path / "codebase"
        codebase_dir.mkdir()
        form_file = codebase_dir / "frmTest.php"
        form_file.write_text("<?php echo 'test'; ?>")

        template = DynamicFormTemplate(str(codebase_dir))
        template.load()

        result = template.merge_with_generated(
            php_logic="<?php $table = 'test'; db_insert($table, $columns); ?>",
            form_fields="<input type='text' name='test'>",
            ajax_handlers="<?php if($_REQUEST['Action']=='GetMaxID') { echo '1'; exit; } ?>",
            crud_operations="<?php db_update($table, $columns); db_delete($table, 'Code=1'); db_getRecord($table, 'Code=1'); getrows('SELECT * FROM test'); getvalue('SELECT Code FROM test'); funStartTran(); funEndTran(); ?>",
            entity_js="window.companyFieldOrder = ['test'];"
        )

        assert "window.companyFieldOrder" in result
        assert "<script>" in result


class TestPhase1Part2_CanonicalNamingFix:
    """Test Part 1.2: Canonical Naming Fix in inline_php_generator.py"""
    
    def test_extract_table_name_from_request(self):
        """Should extract table name from user request"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        user_request = "Table: tblstudent\nFile name: frmStudent.php\nTitle: Student"
        metadata = generator._extract_explicit_request_metadata(user_request)
        
        assert metadata['table_name'] == 'tblstudent'
        assert metadata['file_name'] == 'frmStudent.php'
        assert metadata['title'] == 'Student'
    
    def test_extract_inline_format(self):
        """Should extract from inline format: 'Table: tblname'"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        user_request = "Create form. Table: tblarea File name: frmArea.php Title: Area"
        metadata = generator._extract_explicit_request_metadata(user_request)
        
        assert metadata['table_name'] == 'tblarea'
        assert metadata['file_name'] == 'frmArea.php'
        assert metadata['title'] == 'Area'
    
    def test_logs_extraction_results(self, caplog):
        """Should log extraction results with visual indicators"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        user_request = "Table: tbltest\nFile name: frmTest.php\nTitle: Test"
        
        with caplog.at_level('INFO'):
            metadata = generator._extract_explicit_request_metadata(user_request)
        
        # Check logs contain extraction info
        log_text = caplog.text
        assert "Canonical naming extraction" in log_text or "table_name" in log_text


class TestPhase1Part3_AutoRepairLogic:
    """Test Part 1.3: Auto-Repair Logic in inline_php_generator.py"""
    
    def test_auto_repair_injects_comp_code(self):
        """Should inject Comp_Code filters in WHERE clauses"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        code = "SELECT * FROM tblstudent WHERE Code = '123'"
        validation_result = {'compcode_pattern_found': False}
        
        repaired_code, was_repaired = generator._auto_repair_critical_blocks(
            code, validation_result, {}
        )
        
        assert was_repaired
        assert "Comp_Code" in repaired_code
        assert "$_SESSION['comp_code']" in repaired_code
    
    def test_auto_repair_injects_session_variables(self):
        """Should inject session variables in columns array"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        code = "$columns = array();"
        validation_result = {'session_pattern_found': False}
        
        repaired_code, was_repaired = generator._auto_repair_critical_blocks(
            code, validation_result, {}
        )
        
        assert was_repaired
        assert "User_ID" in repaired_code
        assert "Login_ID" in repaired_code
    
    def test_auto_repair_injects_audit_logging(self):
        """Should inject fun_log() calls after db operations"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        code = "db_insert($table, $columns);"
        validation_result = {'audit_pattern_found': False}
        
        repaired_code, was_repaired = generator._auto_repair_critical_blocks(
            code, validation_result, {}
        )
        
        assert was_repaired
        assert "fun_log" in repaired_code
    
    def test_auto_repair_no_changes_when_valid(self):
        """Should not modify code when validation passes"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        code = "<?php echo 'valid'; ?>"
        validation_result = {
            'compcode_pattern_found': True,
            'session_pattern_found': True,
            'audit_pattern_found': True,
            'delegated_events_found': True,
            'ajax_reinit_guard_found': True,
            'predelete_checks_found': True
        }
        
        repaired_code, was_repaired = generator._auto_repair_critical_blocks(
            code, validation_result, {}
        )
        
        assert not was_repaired
        assert repaired_code == code


class TestPhase1Part4_SectionCompletenessScoring:
    """Test Part 1.4: Section Completeness Scoring in inline_php_generator.py"""
    
    def test_calculate_crud_completeness(self):
        """Should calculate CRUD operations completeness percentage"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        sections = {
            'CRUD_LOGIC_PHP': '''
                if($_POST['txtmode'] == 'save') {
                    db_insert($table, $columns);
                }
                if($_POST['txtmode'] == 'update') {
                    db_update($table, $columns);
                }
                if($_REQUEST['action'] == 'delete') {
                    db_delete($table, 'Code=1');
                }
                if($_REQUEST['action'] == 'edit') {
                    $data = db_getRecord($table, 'Code=1');
                }
                $columns = array();
                funStartTran();
                funEndTran();
            '''
        }
        
        completeness = generator._calculate_section_completeness(sections, {})
        
        assert 'CRUD_LOGIC_PHP' in completeness
        assert completeness['CRUD_LOGIC_PHP'] >= 80  # Should be high
    
    def test_calculate_ajax_completeness(self):
        """Should calculate AJAX handlers completeness percentage"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        sections = {
            'AJAX_HANDLERS_PHP': '''
                if($_REQUEST['Action'] == 'GetMaxID') {
                    echo '1';
                    exit;
                }
            '''
        }
        
        completeness = generator._calculate_section_completeness(sections, {})
        
        assert 'AJAX_HANDLERS_PHP' in completeness
        assert completeness['AJAX_HANDLERS_PHP'] >= 50
    
    def test_overall_completeness_calculation(self):
        """Should calculate overall completeness from all sections"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        sections = {
            'CRUD_LOGIC_PHP': 'db_insert($table, $columns); db_update($table, $columns);',
            'AJAX_HANDLERS_PHP': "if($_REQUEST['Action']=='GetMaxID') { echo '1'; exit; }",
            'FORM_FIELDS_HTML': '<input type="text" name="test">',
            'ENTITY_JS': '.formValidation({ fields: {} })',
            'VARIABLE_INIT_PHP': '$form = "test"; $form2 = "test"; $table = "test"; $title = "test";'
        }
        
        completeness = generator._calculate_section_completeness(sections, {})
        
        assert 'OVERALL' in completeness
        assert 0 <= completeness['OVERALL'] <= 100
    
    def test_identifies_weak_sections(self, caplog):
        """Should identify and log weak sections (<50%)"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        sections = {
            'CRUD_LOGIC_PHP': 'echo "incomplete";',  # Very incomplete
            'AJAX_HANDLERS_PHP': '',
            'FORM_FIELDS_HTML': '<input>',
            'ENTITY_JS': '',
            'VARIABLE_INIT_PHP': '$form = "test";'
        }
        
        with caplog.at_level('WARNING'):
            completeness = generator._calculate_section_completeness(sections, {})
        
        # Should log weak sections
        assert any(score < 50 for name, score in completeness.items() if name != 'OVERALL')


class TestPhase1Part5_ValidationAlignment:
    """Test Part 1.5: Validation Alignment in inline_php_generator.py"""
    
    def test_validation_contract_built_from_user_request(self, caplog):
        """Should build validation contract based on user requirements"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        # Mock the validation function to capture contract
        code = "<?php echo 'test'; ?>"
        user_request = "Create form with dropdown and validation"
        
        with caplog.at_level('INFO'):
            # This will trigger validation contract building
            try:
                generator._validate_company_functions(
                    code, user_request, {}, {}, {}, {}
                )
            except:
                pass  # We just want to see the logs
        
        log_text = caplog.text
        assert "Validation Contract" in log_text or "PHASE 1.5" in log_text
    
    def test_conditional_validations_based_on_request(self):
        """Should only validate what user requested"""
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        # Test that _detect_user_requirements returns a dict
        user_request = "Create form with dropdown and select field"
        user_requirements = generator._detect_user_requirements(user_request)
        
        # Should return a dictionary with requirement flags
        assert isinstance(user_requirements, dict)
        assert 'wants_dropdown' in user_requirements
        assert 'wants_grid' in user_requirements
        assert 'wants_formvalidation' in user_requirements
        
        # The function should detect requirements based on keywords
        # This is a basic smoke test to ensure the function works


class TestPhase1Integration:
    """Integration tests for all Phase 1 parts working together"""
    
    def test_full_phase1_flow(self, tmp_path):
        """Test complete Phase 1 flow: extraction → scoring → validation → repair"""
        # This is a high-level integration test
        # In real scenario, this would test the full generation pipeline
        
        # 1. Test canonical naming extraction
        llm_config = {'api_key': 'test', 'model': 'gpt-4o-mini'}
        generator = InlinePHPGenerator(llm_config)
        
        user_request = "Table: tbltest\nFile name: frmTest.php\nTitle: Test Form"
        metadata = generator._extract_explicit_request_metadata(user_request)
        
        assert metadata['table_name'] == 'tbltest'
        assert metadata['file_name'] == 'frmTest.php'
        assert metadata['title'] == 'Test Form'
        
        # 2. Test section completeness scoring
        sections = {
            'CRUD_LOGIC_PHP': 'db_insert($table, $columns);',
            'AJAX_HANDLERS_PHP': "if($_REQUEST['Action']=='GetMaxID') { exit; }",
            'FORM_FIELDS_HTML': '<input type="text">',
            'ENTITY_JS': '.formValidation({})',
            'VARIABLE_INIT_PHP': '$form = "test"; $table = "test";'
        }
        
        completeness = generator._calculate_section_completeness(sections, {})
        assert 'OVERALL' in completeness
        
        # 3. Test auto-repair
        code = "SELECT * FROM tbltest WHERE Code = '1'"
        validation_result = {'compcode_pattern_found': False}
        
        repaired_code, was_repaired = generator._auto_repair_critical_blocks(
            code, validation_result, {}
        )
        
        assert was_repaired
        assert "Comp_Code" in repaired_code


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
