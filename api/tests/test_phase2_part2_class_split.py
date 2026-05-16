"""
Phase 2 Part 2.2: Class Split Tests
Tests the 4 new classes: ContractParser, GenerationPlanner, CodeAssembler, EnterpriseValidator
"""

import pytest
from agents.graph.contract_parser import ContractParser
from agents.graph.generation_planner import GenerationPlanner
from agents.graph.code_assembler import CodeAssembler
from agents.graph.enterprise_validator import EnterpriseValidator
from agents.utils.enterprise_pattern_retriever import EnterprisePatternRetriever


class TestContractParser:
    """Test ContractParser functionality"""
    
    def test_parse_structured_request(self):
        """Test parsing structured user request"""
        parser = ContractParser()
        
        user_request = """
        Table: tblstudent
        File name: frmStudent.php
        Title: Student Master
        
        Fields:
        - STU_CODE | DB: VARCHAR(20) | Input: textbox | Required: Yes
        - STU_NAME | DB: VARCHAR(100) | Input: textbox | Required: Yes
        """
        
        contract = parser.parse_user_request(user_request)
        
        assert contract['parsing_method'] == 'schema_parser'
        assert contract['table'] == 'tblstudent'
        assert contract['filename'] == 'frmStudent.php'
        assert contract['title'] == 'Student Master'
        assert len(contract['fields']) >= 1
    
    def test_extract_canonical_metadata(self):
        """Test extracting metadata from company example"""
        parser = ContractParser()
        
        company_example = """
        <?php
        $form2 = "frmArea.php";
        $table = "tblarea";
        $title = "Area Master";
        ?>
        """
        
        metadata = parser.extract_canonical_metadata(company_example)
        
        assert metadata['file_name'] == 'frmArea.php'
        assert metadata['table_name'] == 'tblarea'
        assert metadata['title'] == 'Area Master'
    
    def test_merge_contracts(self):
        """Test merging user contract with company metadata"""
        parser = ContractParser()
        
        user_contract = {
            'table': 'tbltest',
            'filename': 'frmTest.php',
            'title': 'Test',
            'primary_key': 'Test_Code',
            'fields': [{'name': 'Test_Code'}],
            'relationships': [],
            'dependencies': [],
            'features': ['validation']
        }
        
        company_metadata = {
            'file_name': 'frmOld.php',
            'table_name': 'tblold',
            'title': 'Old'
        }
        
        merged = parser.merge_contracts(user_contract, company_metadata)
        
        # User contract should override
        assert merged['table_name'] == 'tbltest'
        assert merged['file_name'] == 'frmTest.php'
        assert merged['title'] == 'Test'
        assert merged['primary_key'] == 'Test_Code'


class TestGenerationPlanner:
    """Test GenerationPlanner functionality"""
    
    def test_plan_generation(self):
        """Test generation planning"""
        planner = GenerationPlanner()
        
        contract = {
            'table_name': 'tbltest',
            'file_name': 'frmTest.php',
            'title': 'Test',
            'primary_key': 'Code',
            'fields': [
                {'name': 'Code'},
                {'name': 'Name'}
            ],
            'relationships': [],
            'dependencies': [],
            'features': ['validation']
        }
        
        user_requirements = {
            'wants_dropdown': False,
            'wants_keyboard': True,
            'wants_formvalidation': True,
            'wants_grid': False
        }
        
        plan = planner.plan_generation(
            contract=contract,
            company_examples="",
            analyzed_patterns={},
            user_requirements=user_requirements
        )
        
        assert plan['strategy'] == 'controlled'
        assert 'php_variables' in plan['sections_to_generate']
        assert 'crud_handlers' in plan['sections_to_generate']
        assert 'select2_handlers' in plan['sections_to_generate']
        assert 'entity_js' in plan['sections_to_generate']
        assert len(plan['prompt']) > 0
        assert 'validation_contract' in plan
    
    def test_build_validation_contract(self):
        """Test validation contract building"""
        planner = GenerationPlanner()
        
        contract = {
            'fields': [
                {'name': 'Code'},
                {'name': 'Name'}
            ],
            'dependencies': [
                {'table': 'tblchild', 'field': 'Parent_Code'}
            ],
            'features': []
        }
        
        user_requirements = {
            'wants_formvalidation': True,
            'wants_keyboard': False,
            'wants_grid': False
        }
        
        validation_contract = planner._build_validation_contract(contract, user_requirements)
        
        assert 'db_insert' in validation_contract['required_functions']
        assert 'Save' in validation_contract['required_handlers']
        assert 'GetMaxID' in validation_contract['required_ajax']
        assert 'Code' in validation_contract['required_fields']
        assert 'Name' in validation_contract['required_fields']
        assert validation_contract['required_validation'] == True
        assert len(validation_contract['required_dependencies']) == 1


class TestCodeAssembler:
    """Test CodeAssembler functionality"""
    
    def test_parse_sections(self):
        """Test parsing generated code into sections"""
        assembler = CodeAssembler()
        
        generated_code = """
        <?php
        $form = "frmTest.php";
        $table = "tbltest";
        
        if ($_REQUEST['Action'] == 'Save') {
            db_insert($table, $data);
        }
        ?>
        
        <input type="text" name="Code" />
        """
        
        sections = assembler._parse_sections(generated_code)
        
        assert 'php_variables' in sections
        assert 'crud_handlers' in sections
        assert 'form_fields' in sections

    def test_parse_sections_from_controlled_tags(self):
        """Controlled 5-section output should populate both new and legacy keys."""
        assembler = CodeAssembler()

        generated_code = """
<<<VARIABLE_INIT_PHP>>>
$Code = "";
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
if (isset($_POST['btnSave'])) {
    db_insert($table, $columns);
}
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
if ($_REQUEST['Action'] == 'GetMaxID') {
    echo getvalue("SELECT 1");
    exit;
}
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<input type="text" name="Code" id="Code" />
<<<END_FORM_FIELDS_HTML>>>

<<<ENTITY_JS>>>
window.companyFieldOrder = ['Code'];
<<<END_ENTITY_JS>>>
"""

        sections = assembler._parse_sections(generated_code)

        assert '$Code' in sections['php_variables']
        assert sections['php_logic'] == sections['php_variables']
        assert 'db_insert' in sections['crud_handlers']
        assert sections['crud_operations'] == sections['crud_handlers']
        assert 'GetMaxID' in sections['ajax_handlers']
        assert 'name="Code"' in sections['form_fields']
        assert 'window.companyFieldOrder' in sections['entity_js']
    
    def test_auto_repair_comp_code(self):
        """Test auto-repair injects Comp_Code"""
        assembler = CodeAssembler()
        
        sections = {
            'crud_handlers': 'WHERE Code = ?',
            'php_variables': '',
            'form_fields': ''
        }
        
        contract = {'dependencies': []}
        
        repaired = assembler._auto_repair(sections, contract)
        
        assert 'Comp_Code' in repaired['crud_handlers']
    
    def test_auto_repair_predelete_checks(self):
        """Test auto-repair injects pre-delete checks"""
        assembler = CodeAssembler()
        
        sections = {
            'crud_handlers': 'db_delete($table, "Code = ?", [$code]);',
            'php_variables': '',
            'form_fields': ''
        }
        
        contract = {
            'dependencies': [
                {'table': 'tblchild', 'field': 'Parent_Code', 'message': 'Cannot delete'}
            ]
        }
        
        repaired = assembler._auto_repair(sections, contract)
        
        assert 'getrows' in repaired['crud_handlers']
        assert 'tblchild' in repaired['crud_handlers']

    def test_dedupe_maxid_in_final_output_keeps_single_declaration(self):
        assembler = CodeAssembler()
        assembled = """
<script>
function maxid(){
    if (true) {
        return 1;
    }
    return 0;
}
</script>
<script>
function maxid(){ return 2; }
</script>
"""
        deduped = assembler._dedupe_maxid_in_final_output(assembled)
        assert deduped.lower().count("function maxid(") == 1
        assert "return 1;" in deduped
        assert "return 2;" not in deduped

    def test_assert_required_sections_accepts_uppercase_form_tag(self):
        assembler = CodeAssembler()
        assembled = """
<?php db_insert($table, $columns); db_update($table, $columns, $filter, $params); db_delete($table, $filter, $params); ?>
<FORM id="frm" method="POST"></FORM>
"""
        assembler._assert_required_sections_after_merge(assembled, {})


class TestEnterpriseValidator:
    """Test EnterpriseValidator functionality"""
    
    def test_validate_company_functions(self):
        """Test validation of company functions"""
        validator = EnterpriseValidator()
        
        code = """
        db_insert($table, $data);
        db_update($table, $data, "Code = ?", [$code]);
        db_delete($table, "Code = ?", [$code]);
        """
        
        validation_contract = {
            'required_functions': ['db_insert', 'db_update', 'db_delete', 'db_getRecord'],
            'required_handlers': [],
            'required_ajax': [],
            'required_fields': [],
            'required_dependencies': []
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        # Should have 1 error (missing db_getRecord)
        assert len(errors) == 1
        assert 'db_getRecord' in errors[0]
    
    def test_validate_crud_handlers(self):
        """Test validation of CRUD handlers"""
        validator = EnterpriseValidator()
        
        code = """
        if ($_REQUEST['Action'] == 'Save') {
            db_insert($table, $data);
        }
        if ($_REQUEST['Action'] == 'Update') {
            db_update($table, $data);
        }
        """
        
        validation_contract = {
            'required_functions': [],
            'required_handlers': ['Save', 'Update', 'Delete', 'Edit'],
            'required_ajax': [],
            'required_fields': [],
            'required_dependencies': []
        }
        
        is_valid, errors, scores = validator.validate(code, validation_contract)
        
        # Should have 2 errors (missing Delete and Edit)
        # Note: The pattern matches 'Action' == 'Save' format
        delete_missing = any('Delete' in err for err in errors)
        edit_missing = any('Edit' in err for err in errors)
        
        assert delete_missing
        assert edit_missing

    def test_validate_ajax_handlers_supports_request_action_pattern(self):
        validator = EnterpriseValidator()
        code = """
        if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {
            echo getvalue("SELECT 1");
            exit;
        }
        """
        errors = validator._validate_ajax_handlers(code, ['GetMaxID'])
        assert errors == []
    
    def test_calculate_crud_completeness(self):
        """Test CRUD completeness scoring"""
        validator = EnterpriseValidator()
        
        code = """
        case 'Save':
            db_insert($table, $data);
            break;
        case 'Update':
            db_update($table, $data);
            break;
        case 'Delete':
            db_delete($table, "Code = ?", [$code]);
            break;
        case 'Edit':
            $record = db_getRecord($table, "Code = ?", [$code]);
            break;
        """
        
        score = validator._calculate_crud_completeness(code)
        
        # Should be 100% (all CRUD operations present)
        assert score == 100
    
    def test_validate_fields(self):
        """Test field validation"""
        validator = EnterpriseValidator()
        
        code = """
        <input type="text" name="Code" />
        <input type="text" name="Name" />
        """
        
        errors, score = validator._validate_fields(code, ['Code', 'Name', 'Description'])
        
        # Should have 1 error (missing Description)
        assert len(errors) == 1
        assert 'Description' in errors[0]
        # Score should be 66% (2 out of 3 fields)
        assert score == 66

    def test_strict_production_checks_flag_blocks_unsafe_patterns(self):
        validator = EnterpriseValidator()

        code = """
        <?php
        db_update($table, $columns, $filter, $params);
        db_delete($table, $filter, $params);
        $filter = "Code='" . $_REQUEST['Code'] . "'";
        ?>
        <form action="<?=$form2;?>>
            <?= $_REQUEST['Code']; ?>
        </form>
        <script>
        function maxid(){ return 1; }
        function maxid(){ return 2; }
        </script>
        ?>
        """

        validation_contract = {
            'required_functions': [],
            'required_handlers': [],
            'required_ajax': [],
            'required_fields': [],
            'required_dependencies': [],
            'strict_production_checks': True
        }

        is_valid, errors, _ = validator.validate(code, validation_contract)

        assert is_valid is False
        assert any("Unsafe SQL filter concatenation" in err for err in errors)
        assert any("Malformed form action attribute" in err for err in errors)
        assert any("Duplicate JavaScript maxid()" in err for err in errors)


class TestIntegration:
    """Test integration of all 4 classes"""
    
    def test_full_workflow(self):
        """Test complete workflow: Parse -> Plan -> Assemble -> Validate"""
        
        # 1. Parse contract
        parser = ContractParser()
        user_request = """
        Table: tbltest
        File name: frmTest.php
        Title: Test Form
        
        Fields:
        - Test_Code | DB: VARCHAR(20) | Input: textbox | Required: Yes
        - Test_Name | DB: VARCHAR(100) | Input: textbox | Required: Yes
        """
        
        contract = parser.parse_user_request(user_request)
        assert contract['table'] == 'tbltest'
        
        # 2. Plan generation
        planner = GenerationPlanner()
        user_requirements = {
            'wants_formvalidation': True,
            'wants_keyboard': False,
            'wants_grid': False
        }
        
        plan = planner.plan_generation(
            contract=contract,
            company_examples="",
            analyzed_patterns={},
            user_requirements=user_requirements
        )
        
        assert 'validation_contract' in plan
        
        # 3. Assemble code (mock generated code)
        assembler = CodeAssembler()
        generated_code = """
        <?php
        $form = "frmTest.php";
        $table = "tbltest";
        
        if ($_REQUEST['Action'] == 'Save') {
            db_insert($table, $data);
        }
        ?>
        <input type="text" name="Test_Code" />
        <input type="text" name="Test_Name" />
        """
        
        assembled = assembler.assemble(generated_code, contract)
        assert len(assembled) > 0
        
        # 4. Validate
        validator = EnterpriseValidator()
        is_valid, errors, scores = validator.validate(
            assembled,
            plan['validation_contract']
        )
        
        # Should have some errors (incomplete CRUD)
        assert isinstance(errors, list)
        assert isinstance(scores, dict)
        assert 'overall' in scores


class TestEnterprisePatternRetriever:
    def test_filter_complete_php_files_preserves_entity_bonus_after_chunk_merge(self):
        class _NoExclude:
            @staticmethod
            def should_exclude_file(filename, file_size, intent_type):
                return False

        retriever = EnterprisePatternRetriever.__new__(EnterprisePatternRetriever)
        retriever.user_id = '8'
        retriever.pattern_extractor = _NoExclude()
        retriever.embedding_manager = None

        chunk_base = """<?php
@session_start();
include("include/config.inc.php");
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Save') { db_insert($table, $columns); }
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Update') { db_update($table, $columns, "Code = ?", [$code]); }
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Delete') { db_delete($table, "Code = ?", [$code]); }
?>
<!doctype html><html><head><link rel="stylesheet" href="a.css"></head><body><script src="a.js"></script></body></html>
"""
        results = [
            {
                'content': chunk_base,
                'metadata': {'file_path': r'C:\repo\frmStudent.php', 'chunk_index': 0, 'total_chunks': 2},
                'similarity_score': 0.30
            },
            {
                'content': chunk_base + "\n<!-- second chunk -->",
                'metadata': {'file_path': r'C:\repo\frmStudent.php', 'chunk_index': 1, 'total_chunks': 2},
                'similarity_score': 0.28
            },
            {
                'content': chunk_base,
                'metadata': {'file_path': r'C:\repo\frmEngineer.php', 'chunk_index': 0, 'total_chunks': 1},
                'similarity_score': 0.35
            },
        ]

        complete = retriever._filter_complete_php_files(
            results=results,
            query='CRUD form for Student',
            intent_type='form',
            user_request='Create complete Student form. File name: frmStudent.php'
        )

        student_rows = [
            row for row in complete
            if 'frmstudent.php' in str(row.get('metadata', {}).get('file_path', '')).lower()
        ]
        assert student_rows, "Expected merged frmStudent.php in filtered examples"
        assert student_rows[0].get('entity_bonus', 0) >= 10
