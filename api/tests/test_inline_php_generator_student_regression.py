from django.test import SimpleTestCase

from agents.graph.inline_php_generator import InlinePHPGenerator


class InlinePHPGeneratorStudentRegressionTests(SimpleTestCase):
    def setUp(self):
        self.generator = InlinePHPGenerator(
            {
                'api_key': 'test-key',
                'model': 'gpt-4o-mini',
            }
        )

    def test_student_prompt_auto_attach_closes_known_blockers(self):
        student_prompt = """Create complete Student master form.

Table: tblstudent
File name: frmStudent.php
Title: Student
CaseType: Student

Primary Key:
- STU_CODE | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields (USE EXACT NAMES, NO EXTRA FIELDS):
- STU_CODE | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes
- Campus_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Class_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Section_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- First_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Last_Name | DB: VARCHAR(120) | Input: textbox | Required: No
- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- DOB | DB: DATE | Input: date | Required: Yes
- Admission_Date | DB: DATE | Input: date | Required: Yes
- STATUS | DB: TINYINT(1) | Input: checkbox | Required: No
- ACC_CODE | DB: VARCHAR(20) | Input: textbox | Required: No

Detail Grid (tblstudentsubjectdt):
- SR_NO | DB: INT | Input: readonly textbox | Required: Yes
- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Subject_Name | DB: VARCHAR(120) | Input: readonly textbox | Required: No
- Is_Optional | DB: TINYINT(1) | Input: checkbox | Required: No

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- AJAX GetMaxID handler + maxid() JS (endpoint must be <?=$form2;?>, no ajax.php file endpoint)
- AJAX GetCOSTCENTER handler
- pre-delete dependency checks for: tblattendance, tblstudentfee, tblexamenrollment
- detail-grid insert/update/delete flow using TXTCOUNTACC and row loop
- Canonical names must match exactly: table=tblstudent, file=frmStudent.php, title=Student
"""

        known_bad_generated_code = """<?php
@session_start();
include("include/config.inc.php");
$form2 = "frmStudent.php";
$table = "tblstudent";
$title = "Student";
$primaryField = "ACC_CODE";

if (!function_exists('add_Slashes_new')) {
    function add_Slashes_new($value) { return addslashes($value); }
}

if (($_REQUEST['Action'] ?? '') == 'Save') {
    if (function_exists('funStartTran')) { funStartTran(); }
    $primaryValue = $_REQUEST[$primaryField] ?? '';
    $columns = array();
    $columns['STU_CODE'] = add_Slashes_new($_REQUEST['STU_CODE'] ?? '');
    $columns['AdmissionNo'] = add_Slashes_new($_REQUEST['AdmissionNo'] ?? '');
    $columns['Campus_Code'] = add_Slashes_new($_REQUEST['Campus_Code'] ?? '');
    $columns['Class_Code'] = add_Slashes_new($_REQUEST['Class_Code'] ?? '');
    $columns['Section_Code'] = add_Slashes_new($_REQUEST['Section_Code'] ?? '');
    $columns['First_Name'] = add_Slashes_new($_REQUEST['First_Name'] ?? '');
    $columns['Last_Name'] = add_Slashes_new($_REQUEST['Last_Name'] ?? '');
    $columns['Father_Name'] = add_Slashes_new($_REQUEST['Father_Name'] ?? '');
    $columns['DOB'] = add_Slashes_new($_REQUEST['DOB'] ?? '');
    $columns['Admission_Date'] = add_Slashes_new($_REQUEST['Admission_Date'] ?? '');
    $columns['STATUS'] = add_Slashes_new($_REQUEST['STATUS'] ?? '');
    $columns['SR_NO'] = add_Slashes_new($_REQUEST['SR_NO'] ?? '');
    $columns['Subject_Code'] = add_Slashes_new($_REQUEST['Subject_Code'] ?? '');
    $columns['Subject_Name'] = add_Slashes_new($_REQUEST['Subject_Name'] ?? '');
    $columns['Is_Optional'] = add_Slashes_new($_REQUEST['Is_Optional'] ?? '');
    $columns['Comp_Code'] = $_SESSION['comp_code'] ?? '';
    $columns['Updated_By'] = $_SESSION['user_id'] ?? '';
    $columns['Updated_Date'] = date('Y-m-d H:i:s');

    if (function_exists('getrows') && getrows($table, $primaryField, $primaryValue) == '1') {
        if (function_exists('db_update')) {
            db_update($table, $columns, "$primaryField='".add_Slashes_new($primaryValue)."' AND Comp_Code='".$_SESSION['comp_code']."'");
        }
        if (function_exists('fun_log')) { fun_log($table, $primaryValue, 'Update', $_SESSION['user_id'] ?? ''); }
    } else {
        $columns[$primaryField] = add_Slashes_new($primaryValue);
        $columns['Created_By'] = $_SESSION['user_id'] ?? '';
        $columns['Created_Date'] = date('Y-m-d H:i:s');
        if (function_exists('db_insert')) {
            db_insert($table, $columns);
        }
        if (function_exists('fun_log')) { fun_log($table, $primaryValue, 'Save', $_SESSION['user_id'] ?? ''); }
    }

    if (function_exists('funEndTran')) { funEndTran(); }
    header("Location: ".$form2."?msg=saved");
    exit;
}
?>
<!DOCTYPE html>
<html>
<body>
<form id="frmDynamic" method="post">
    <div class="form-group">
      <label for="ACC_CODE">ACC CODE</label>
      <input type="text" id="ACC_CODE" name="ACC_CODE" />
    </div>
</form>
</body>
</html>
"""

        request_metadata = self.generator._extract_explicit_request_metadata(student_prompt)
        naming_metadata = {
            'table_name': request_metadata.get('table_name') or 'tblstudent',
            'file_name': request_metadata.get('file_name') or 'frmStudent.php',
            'title': request_metadata.get('title') or 'Student',
            'case_type': request_metadata.get('case_type') or 'Student',
            'strict_company_validation': True,
            'strict_validation_reason': 'retrieval_context_strong',
        }
        company_fields = self.generator._extract_field_names_from_example('', student_prompt)
        grid_pattern = self.generator._detect_grid_pattern('', 'Student', company_fields.get('detail_grid', {}))

        patched = self.generator._auto_attach_shared_components(
            known_bad_generated_code,
            fixed_parts={},
            user_request=student_prompt,
        )
        validation = self.generator._validate_company_functions(
            patched,
            user_request=student_prompt,
            hierarchy_pattern={},
            company_fields=company_fields,
            grid_pattern=grid_pattern,
            naming_metadata=naming_metadata,
        )

        self.assertTrue(validation.get('valid'))
        self.assertEqual(validation.get('required_blockers'), [])

    def test_school_prompt_detail_grid_not_required_turns_off_grid(self):
        school_prompt = """Create complete School master form.

Table: tbl_school
File name: frmSchool.php
Title: School
CaseType: School

Detail Grid: Not required

Required Company Patterns (MANDATORY):
- AJAX GetCOSTCENTER handler (if customer reference uses it)
"""

        requirements = self.generator._detect_user_requirements(school_prompt)
        requested_grid = self.generator._extract_requested_grid(school_prompt)

        self.assertFalse(requirements.get('wants_grid'))
        self.assertTrue(requirements.get('grid_opt_out'))
        self.assertFalse(requirements.get('wants_getcostcenter'))
        self.assertFalse(requested_grid.get('has_grid'))
        self.assertTrue(requested_grid.get('explicit_opt_out'))

    def test_compact_prompt_parses_metadata_fields_and_grid_opt_out(self):
        compact_prompt = (
            "Create complete Sub Area master form. "
            "Table: tblsubarea "
            "File name: frmSubArea.php "
            "Title: Sub Area "
            "CaseType: SubArea "
            "Primary Key: - SubArea_Code | DB: varchar | Input: readonly textbox "
            "Master Fields: - SubArea_Code | DB: varchar | Input: readonly textbox | Required: Yes "
            "- Area_Code | DB: varchar | Input: select | Required: Yes "
            "- SubArea_Name | DB: varchar | Input: textbox | Required: Yes "
            "- Is_Active | DB: tinyint | Input: checkbox | Required: Yes "
            "Relationships: - Area_Code -> tblarea.Area_Code | Input: select | Cascade: Yes "
            "Dependencies: - tblcustomer | field=SubArea_Code | message=Cannot delete if used in customer "
            "- tblsaleman | field=SubArea_Code | message=Cannot delete if used in salesman "
            "Business Validations: - SubArea_Name must be unique within Area_Code "
            "Detail Grid: - Not required"
        )

        request_metadata = self.generator._extract_explicit_request_metadata(compact_prompt)
        requirements = self.generator._detect_user_requirements(compact_prompt)
        requested_grid = self.generator._extract_requested_grid(compact_prompt)
        company_fields = self.generator._extract_field_names_from_example('', compact_prompt)

        self.assertEqual(request_metadata.get('table_name'), 'tblsubarea')
        self.assertEqual(request_metadata.get('file_name'), 'frmSubArea.php')
        self.assertEqual(request_metadata.get('title'), 'Sub Area')
        self.assertEqual(request_metadata.get('case_type'), 'SubArea')
        self.assertEqual(request_metadata.get('effective_entity_compact'), 'subarea')
        self.assertEqual(requirements.get('requested_entity'), 'SubArea')
        self.assertFalse(requirements.get('wants_grid'))
        self.assertTrue(requested_grid.get('explicit_opt_out'))
        self.assertFalse(requested_grid.get('has_grid'))
        self.assertEqual(
            company_fields.get('user_requested_fields'),
            ['SubArea_Code', 'Area_Code', 'SubArea_Name', 'Is_Active']
        )
        self.assertEqual(company_fields.get('primary_key'), 'SubArea_Code')
        self.assertTrue(company_fields.get('detail_grid', {}).get('explicit_opt_out'))

    def test_controlled_section_parser_extracts_tagged_blocks(self):
        tagged_output = """
<<<VARIABLE_INIT_PHP>>>
$Code = "";
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
if (isset($_POST['btnSave'])) {
    funStartTran();
}
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
if ($_REQUEST['Action'] == 'GetMaxID') {
    echo '0001';
    exit;
}
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<div class="form-group"><input type="text" name="Code" id="Code"></div>
<<<END_FORM_FIELDS_HTML>>>

<<<ENTITY_JS>>>
window.companyFieldOrder = ['Code', 'btnSave'];
<<<END_ENTITY_JS>>>
"""

        sections = self.generator._parse_controlled_generation_sections(tagged_output)

        self.assertEqual(sections['VARIABLE_INIT_PHP'], '$Code = "";')
        self.assertIn("funStartTran()", sections['CRUD_LOGIC_PHP'])
        self.assertIn("GetMaxID", sections['AJAX_HANDLERS_PHP'])
        self.assertIn('form-group', sections['FORM_FIELDS_HTML'])
        self.assertIn('window.companyFieldOrder', sections['ENTITY_JS'])

    def test_controlled_assembler_locks_company_framework_order(self):
        company_prompt = """Create complete Area master form.

Table: tblarea
File name: frmArea.php
Title: Area
CaseType: Area

Fields:
- Code
- Description
"""
        request_metadata = self.generator._extract_explicit_request_metadata(company_prompt)
        company_fields = self.generator._extract_field_names_from_example('', company_prompt)
        naming_metadata = {
            'table_name': request_metadata.get('table_name') or 'tblarea',
            'file_name': request_metadata.get('file_name') or 'frmArea.php',
            'title': request_metadata.get('title') or 'Area',
            'case_type': request_metadata.get('case_type') or 'Area',
            'strict_company_validation': True,
            'strict_validation_reason': 'retrieval_context_strong',
        }
        fixed_parts = {
            'html_head': '<head><title>Old</title><script src="global/vendor/breakpoints/breakpoints.js"></script></head>',
            'body_start': '<body class="animsition"><div class="page"><div class="page-content"><form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">',
            'body_end': '</form></div></div><?php include("include/footer.php");?></body></html>',
            'footer_scripts': '<script src="global/vendor/jquery/jquery.js"></script>\n<script src="global/vendor/formvalidation/formValidation.min.js"></script>',
        }
        sections = {
            'VARIABLE_INIT_PHP': '$Code = "";\n$Description = "";',
            'CRUD_LOGIC_PHP': (
                "if ((isset($_REQUEST['action']) ? $_REQUEST['action'] : '') == 'Update') {\n"
                "    $obj = db_getRecord($table, \"Code='\".add($_REQUEST['major']).\"'\");\n"
                "}\n"
                "if (isset($_POST['btnSave'])) {\n"
                "    funStartTran();\n"
                "    $columns['Code'] = add_Slashes_new($_REQUEST['Code']);\n"
                "    $columns['Description'] = add_Slashes_new($_REQUEST['Description']);\n"
                "    $columns['Comp_Code'] = $_SESSION['comp_code'];\n"
                "    if (getrows($table, 'Code', $_REQUEST['Code']) == '1') {\n"
                "        db_update($table, $columns, \"Code='\".add($_REQUEST['Code']).\"'\");\n"
                "        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['Code'], 'Update', db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);\n"
                "    } else {\n"
                "        db_insert($table, $columns);\n"
                "        fun_log($_SESSION['user_id'], $_SESSION['comp_code'], $title, $_REQUEST['Code'], 'Save', db_dateFormat(date('Y-m-d')), $_SESSION['login_id']);\n"
                "    }\n"
                "    funEndTran();\n"
                "    exit;\n"
                "}"
            ),
            'AJAX_HANDLERS_PHP': (
                "if ((isset($_REQUEST['Action']) ? $_REQUEST['Action'] : '') == 'GetMaxID') {\n"
                "    echo getvalue(\"SELECT LPAD(MAX(Code)+1,2,'0') FROM $table WHERE Comp_Code='\".$_SESSION['comp_code'].\"'\");\n"
                "    exit;\n"
                "}"
            ),
            'FORM_FIELDS_HTML': (
                '<div class="form-group">\n'
                '  <label class="col-md-4 control-label text-danger">Code :</label>\n'
                '  <div class="col-md-2"><input type="text" class="form-control" name="Code" id="Code" value="<?=$Code;?>" onKeyDown="checkKeycode(event,this.id);" /></div>\n'
                '</div>\n'
                '<div class="form-group">\n'
                '  <label class="col-md-4 control-label text-danger">Description :</label>\n'
                '  <div class="col-md-4"><input type="text" class="form-control" name="Description" id="Description" value="<?=$Description;?>" onKeyDown="checkKeycode(event,this.id);" /></div>\n'
                '</div>'
            ),
            'ENTITY_JS': (
                "window.companyFieldOrder = ['Code', 'Description', 'btnSave'];\n"
                "window.companyValidationFields = {\n"
                "  'Code': { validators: { notEmpty: { message: 'Code is required' } } },\n"
                "  'Description': { validators: { notEmpty: { message: 'Description is required' } } }\n"
                "};\n"
                "window.companyFormOnLoad = function () { document.getElementById('Code').focus(); };"
            ),
        }

        assembled = self.generator._assemble_controlled_php_file(
            fixed_parts=fixed_parts,
            naming_metadata=naming_metadata,
            sections=sections,
            company_fields=company_fields,
            user_request=company_prompt,
        )

        self.assertIn('@session_start();', assembled)
        self.assertIn('include("include/config.inc.php");', assembled)
        self.assertIn('$form = "frmSettingEditDeleteCase.php?CaseType=Area";', assembled)
        self.assertIn('<?php include("include/footer.php");?>', assembled)
        self.assertIn('window.companySharedInit', assembled)
        self.assertIn('window.companyFieldOrder', assembled)
        self.assertLess(assembled.index('@session_start();'), assembled.index('<!DOCTYPE html>'))
        self.assertLess(assembled.index('<!DOCTYPE html>'), assembled.index('window.companySharedInit'))

    def test_controlled_assembler_normalizes_keyboard_and_label_hooks(self):
        company_prompt = """Create complete Area master form.

Table: tblarea
File name: frmArea.php
Title: Area
CaseType: Area
Required Company Patterns:
- formValidation + checkKeycode

Fields:
- Code
- Description
"""
        request_metadata = self.generator._extract_explicit_request_metadata(company_prompt)
        company_fields = self.generator._extract_field_names_from_example('', company_prompt)
        naming_metadata = {
            'table_name': request_metadata.get('table_name') or 'tblarea',
            'file_name': request_metadata.get('file_name') or 'frmArea.php',
            'title': request_metadata.get('title') or 'Area',
            'case_type': request_metadata.get('case_type') or 'Area',
            'strict_company_validation': True,
            'strict_validation_reason': 'retrieval_context_strong',
        }
        fixed_parts = {
            'html_head': '<head><title>Old</title></head>',
            'body_start': '<body><div class="page"><div class="page-content"><form id="frm" method="POST" action="<?=$form2;?>">',
            'body_end': '</form><?php include("include/footer.php");?></body></html>',
            'footer_scripts': '<script src="global/vendor/jquery/jquery.js"></script>',
        }
        sections = {
            'VARIABLE_INIT_PHP': '$Code = "";\n$Description = "";',
            'CRUD_LOGIC_PHP': "if (isset($_POST['btnSave'])) { funStartTran(); funEndTran(); }",
            'AJAX_HANDLERS_PHP': '',
            'FORM_FIELDS_HTML': (
                '<div class="form-group">\n'
                '  <label for="Code">Code</label>\n'
                '  <div><input type="text" name="Code" id="Code" value="<?=$Code;?>"></div>\n'
                '</div>\n'
                '<div class="form-group">\n'
                '  <label for="Description">Description</label>\n'
                '  <div><textarea name="Description" id="Description"><?=$Description;?></textarea></div>\n'
                '</div>'
            ),
            'ENTITY_JS': '',
        }

        assembled = self.generator._assemble_controlled_php_file(
            fixed_parts=fixed_parts,
            naming_metadata=naming_metadata,
            sections=sections,
            company_fields=company_fields,
            user_request=company_prompt,
        )

        self.assertIn('control-label', assembled)
        self.assertIn('col-md-4', assembled)
        self.assertIn('<div class="col-md-8">', assembled)
        self.assertIn('onKeyDown="checkKeycode(event,this.id);"', assembled)
        self.assertIn('value="<?=htmlspecialchars($Code, ENT_QUOTES);?>" onKeyDown="checkKeycode(event,this.id);"', assembled)
        self.assertIn('<textarea class="form-control" name="Description" id="Description" onKeyDown="checkKeycode(event,this.id);">', assembled)
        self.assertIn('<body class="animsition" onLoad="companyPageLoad();">', assembled)
        self.assertIn('action="<?=$form2;?>" enctype="multipart/form-data">', assembled)
        self.assertIn('function checkKeycode(e, field)', assembled)
        self.assertIn('document.onkeydown = checkKeycode;', assembled)

    def test_controlled_field_normalizer_repairs_unclosed_controls_before_wrapper_close(self):
        company_prompt = """Create complete Sub Area master form.

Required Company Patterns:
- formValidation + checkKeycode
"""
        malformed_fields = (
            '<div class="form-group">\n'
            '  <label for="SubArea_Code">Sub Area Code</label>\n'
            '  <div><input type="text" name="SubArea_Code" id="SubArea_Code" value="<?=$SubArea_Code;?>" required\n'
            '  </div>\n'
            '</div>\n'
            '<div class="form-group">\n'
            '  <label for="Area_Code">Area</label>\n'
            '  <div><select name="Area_Code" id="Area_Code" required\n'
            '  <option value="">Select</option></select></div>\n'
            '</div>\n'
            '<div class="form-group">\n'
            '  <label for="Is_Active">Is Active</label>\n'
            '  <div><input type="checkbox" name="Is_Active" id="Is_Active" <?= $Is_Active ? \'checked\' : \'\'; ?>\n'
            '  </div>\n'
            '</div>'
        )

        normalized = self.generator._normalize_controlled_form_fields(
            malformed_fields,
            user_request=company_prompt,
        )

        self.assertIn('value="<?=htmlspecialchars($SubArea_Code, ENT_QUOTES);?>" required onKeyDown="checkKeycode(event,this.id);">', normalized)
        self.assertIn('<select class="form-control" name="Area_Code" id="Area_Code" required onKeyDown="checkKeycode(event,this.id);">', normalized)
        self.assertIn('<input type="checkbox" name="Is_Active" id="Is_Active" <?= $Is_Active ? \'checked\' : \'\'; ?> onKeyDown="checkKeycode(event,this.id);">', normalized)
        self.assertNotIn('</div onKeyDown="checkKeycode(event,this.id);">>', normalized)
        self.assertNotIn('</div>>', normalized)
        self.assertNotIn('</div>\n  <option value="">Select</option>', normalized)
