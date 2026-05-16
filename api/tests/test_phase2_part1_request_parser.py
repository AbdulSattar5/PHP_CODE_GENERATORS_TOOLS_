"""
Phase 2 Part 2.1: Request Schema Parser Tests
Tests the RequestSchemaParser integration into generation flow
"""

import pytest
from agents.utils.request_parser import RequestSchemaParser


class TestRequestSchemaParser:
    """Test RequestSchemaParser functionality"""
    
    def test_parse_complete_request(self):
        """Test parsing a complete structured request"""
        user_request = """
        Table: tblstudent
        File name: frmStudent.php
        Title: Student Master
        
        Primary Key:
        - STU_CODE
        
        Fields:
        - STU_CODE | DB: VARCHAR(20) | Input: textbox | Required: Yes
        - STU_NAME | DB: VARCHAR(100) | Input: textbox | Required: Yes
        - School_Code -> tblschool.School_Code | Input: select
        
        Dependencies:
        - tblattendance | field=STU_CODE | message=Cannot delete
        """
        
        parser = RequestSchemaParser()
        schema = parser.parse(user_request)
        
        assert schema['table'] == 'tblstudent'
        assert schema['filename'] == 'frmStudent.php'
        assert schema['title'] == 'Student Master'
        assert schema['primary_key'] == 'STU_CODE'
        assert len(schema['fields']) == 2  # STU_CODE, STU_NAME (not School_Code - that's a relationship)
        assert len(schema['relationships']) == 1
        assert len(schema['dependencies']) == 1
    
    def test_parse_minimal_request(self):
        """Test parsing with minimal required fields"""
        user_request = """
        Table: tblarea
        File name: frmArea.php
        Title: Area
        
        Fields:
        - Area_Code | DB: VARCHAR(20) | Input: textbox
        """
        
        parser = RequestSchemaParser()
        schema = parser.parse(user_request)
        
        assert schema['table'] == 'tblarea'
        assert schema['filename'] == 'frmArea.php'
        assert schema['title'] == 'Area'
        assert len(schema['fields']) == 1
    
    def test_parse_missing_required_fields(self):
        """Test that parser raises error when required fields missing"""
        user_request = """
        Some random text without proper structure
        """
        
        parser = RequestSchemaParser()
        
        with pytest.raises(ValueError) as exc_info:
            parser.parse(user_request)
        
        assert "table name is required" in str(exc_info.value).lower()
    
    def test_parse_features(self):
        """Test feature detection from request"""
        user_request = """
        Table: tbltest
        File name: frmTest.php
        Title: Test
        
        Fields:
        - Code | DB: VARCHAR(20) | Input: textbox
        
        Features: dropdown, validation, keyboard, predelete
        """
        
        parser = RequestSchemaParser()
        schema = parser.parse(user_request)
        
        assert 'dropdown' in schema['features']
        assert 'validation' in schema['features']
        assert 'keyboard' in schema['features']
        assert 'predelete' in schema['features']
    
    def test_parse_relationships(self):
        """Test relationship parsing"""
        user_request = """
        Table: tblsubarea
        File name: frmSubArea.php
        Title: Sub Area
        
        Fields:
        - SubArea_Code | DB: VARCHAR(20) | Input: textbox
        - Area_Code -> tblarea.Area_Code | Input: select | Cascade: Yes
        """
        
        parser = RequestSchemaParser()
        schema = parser.parse(user_request)
        
        assert len(schema['relationships']) == 1
        rel = schema['relationships'][0]
        assert rel['field'] == 'Area_Code'
        assert rel['references'] == 'tblarea.Area_Code'
        assert rel.get('cascade') == True
        assert rel.get('input_type') == 'select'
    
    def test_parse_dependencies(self):
        """Test dependency parsing for pre-delete checks"""
        user_request = """
        Table: tblemployee
        File name: frmEmployee.php
        Title: Employee
        
        Fields:
        - Employee_Code | DB: VARCHAR(20) | Input: textbox
        
        Dependencies:
        - tblpayroll | field=Employee_Code | message=Cannot delete employee with payroll records
        - tblattendance | field=Employee_Code | message=Cannot delete employee with attendance
        """
        
        parser = RequestSchemaParser()
        schema = parser.parse(user_request)
        
        assert len(schema['dependencies']) == 2
        assert schema['dependencies'][0]['table'] == 'tblpayroll'
        assert schema['dependencies'][0]['field'] == 'Employee_Code'
        assert 'payroll' in schema['dependencies'][0]['message'].lower()

    def test_parse_compact_master_detail_request_deterministically(self):
        """Compact one-line prompts should still preserve full canonical contract."""
        user_request = (
            "Create complete Student master-detail form. "
            "Master Table: tblstudent "
            "Detail Table: tblstudentsubjectdt "
            "File name: frmStudent.php "
            "Title: Student "
            "Primary Key: - STU_CODE | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox "
            "Master Fields: "
            "- STU_CODE | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes "
            "- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes "
            "- Campus_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
            "- Class_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
            "- Section_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
            "- First_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes "
            "- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes "
            "- DOB | DB: DATE | Input: date | Required: Yes "
            "- Admission_Date | DB: DATE | Input: date | Required: Yes "
            "- STATUS | DB: TINYINT(1) | Input: checkbox | Required: No "
            "Detail Grid (tblstudentsubjectdt): "
            "- SR_NO | DB: INT | Input: readonly textbox | Required: Yes "
            "- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
            "- Subject_Name | DB: VARCHAR(120) | Input: readonly textbox | Required: No "
            "- Is_Optional | DB: TINYINT(1) | Input: checkbox | Required: No "
            "Dependencies: "
            "- tblattendance | field=STU_CODE | message=Cannot delete. Attendance records exist. "
            "- tblstudentfee | field=STU_CODE | message=Cannot delete. Fee records exist."
        )

        parser = RequestSchemaParser()
        schema = parser.parse(user_request)

        assert schema['table'] == 'tblstudent'
        assert schema['master_table'] == 'tblstudent'
        assert schema['detail_table'] == 'tblstudentsubjectdt'
        assert schema['filename'] == 'frmStudent.php'
        assert schema['file_name'] == 'frmStudent.php'
        assert schema['title'] == 'Student'
        assert schema['entity'] == 'Student'
        assert schema['primary_key'] == 'STU_CODE'
        parsed_field_names = [field['name'] for field in schema['fields']]
        for field_name in [
            'STU_CODE', 'AdmissionNo', 'Campus_Code', 'Class_Code', 'Section_Code',
            'First_Name', 'Father_Name', 'DOB', 'Admission_Date', 'STATUS',
            'SR_NO', 'Subject_Code', 'Subject_Name', 'Is_Optional',
        ]:
            assert field_name in parsed_field_names
        assert len(schema['dependencies']) == 2

    def test_parse_plain_master_fields_without_explicit_title(self):
        """Plain field lines and missing explicit title should be inferred and parsed."""
        user_request = """
        Create a complete Student Master form as ONE complete PHP file (inline PHP+HTML+CSS+JS) in company style.

        Module details:
        Table: tblstudent
        File name: frmStudent.php
        CRUD: create, read, update, delete

        Master fields:
        Id (auto max+1, readonly)
        txtRollNo (required)
        txtStudentName (required)
        txtClass (required)
        txtmode (status: Active/Deactive)
        CTRL_HID_VALUE (hidden)
        """

        parser = RequestSchemaParser()
        schema = parser.parse(user_request)

        assert schema['table'] == 'tblstudent'
        assert schema['filename'] == 'frmStudent.php'
        assert schema['title'] == 'Student Master'

        parsed_field_names = [field['name'] for field in schema['fields']]
        for field_name in ['Id', 'txtRollNo', 'txtStudentName', 'txtClass', 'txtmode', 'CTRL_HID_VALUE']:
            assert field_name in parsed_field_names

        hidden_field = next(field for field in schema['fields'] if field['name'] == 'CTRL_HID_VALUE')
        assert hidden_field.get('input_type') == 'hidden'


class TestRequestParserIntegration:
    """Test RequestSchemaParser integration with InlinePHPGenerator"""
    
    def test_parser_used_when_structured_request(self):
        """Test that parser is used when request is structured"""
        from agents.graph.inline_php_generator import InlinePHPGenerator
        
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGenerator(llm_config)
        
        user_request = """
        Table: tbltest
        File name: frmTest.php
        Title: Test Form
        
        Fields:
        - Test_Code | DB: VARCHAR(20) | Input: textbox
        """
        
        # Test the parser wrapper method
        metadata = generator._extract_canonical_form_metadata_with_parser(
            user_request=user_request,
            company_example="",
            example_file_path=""
        )
        
        assert metadata['parsing_method'] == 'schema_parser'
        assert metadata['table_name'] == 'tbltest'
        assert metadata['file_name'] == 'frmTest.php'
        assert metadata['title'] == 'Test Form'
        assert len(metadata['parsed_fields']) == 1
    
    def test_fallback_to_heuristic_when_parser_fails(self):
        """Test fallback to heuristic extraction when parser fails"""
        from agents.graph.inline_php_generator import InlinePHPGenerator
        
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGenerator(llm_config)
        
        # Unstructured request that will fail parsing
        user_request = "Create a simple form"
        
        # Company example with heuristic-extractable metadata
        company_example = """
        <?php
        $form2 = "frmArea.php";
        $table = "tblarea";
        $title = "Area Master";
        ?>
        """
        
        metadata = generator._extract_canonical_form_metadata_with_parser(
            user_request=user_request,
            company_example=company_example,
            example_file_path=""
        )
        
        assert metadata['parsing_method'] == 'heuristic'
        assert metadata['table_name'] == 'tblarea'
        assert metadata['file_name'] == 'frmArea.php'
        assert metadata['title'] == 'Area Master'
