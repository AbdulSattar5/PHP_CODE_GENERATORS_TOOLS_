import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from agents.graph.code_assembler import CodeAssembler
from agents.validators.dynamic_code_validator import DynamicCodeValidator
from api.views import CodeGenerationViewSet

SAMPLE_CODEBASE_DIR = Path(__file__).resolve().parent / 'fixtures' / 'sample_company_codebase'


SUBAREA_REQUEST = (
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
    "Detail Grid: Not required "
    "Business Validations: - SubArea_Name must be unique within Area_Code "
    "- Cannot delete if used in customer "
    "Required Patterns: - cascading dropdown Area_Code "
    "- pre-delete check tblcustomer "
    "- all company functions"
)

SUBAREA_COMPANY_BASELINE_REQUEST = (
    "Create complete Sub Area master form. "
    "Table: tblsubarea "
    "File name: frmSubArea.php "
    "Title: Sub Area "
    "CaseType: SubArea "
    "Required Patterns: - pre-delete check tblcustomer - all company functions"
)


class ValidatorAndFallbackRegressionTests(SimpleTestCase):
    def test_company_template_fallback_honors_explicit_file_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            codebase_root = Path(tmp) / '1' / 'cb1'
            codebase_root.mkdir(parents=True)
            (codebase_root / 'frmArea.php').write_text(
                '<?php $table = "tblarea"; $title = "Area"; ?>',
                encoding='utf-8'
            )
            (codebase_root / 'frmSubArea.php').write_text(
                '<?php $table = "tblsubarea"; $title = "Sub Area"; ?>',
                encoding='utf-8'
            )

            with override_settings(COMPANY_CODEBASE_DIR=tmp):
                result = CodeGenerationViewSet()._generate_company_template_fallback(
                    SUBAREA_REQUEST,
                    user_id='1',
                    codebase_id='cb1'
                )

        self.assertIsNotNone(result)
        self.assertEqual(
            result['file_structure']['files']['complete_php']['path'],
            'frmSubArea.php'
        )
        self.assertEqual(result['intent']['database']['table_name'], 'tblsubarea')

    def test_public_fixture_subarea_form_is_not_blocked_by_dynamic_validator(self):
        company_form = SAMPLE_CODEBASE_DIR / 'frmSubArea.php'
        self.assertTrue(company_form.exists(), f'Expected fixture form at {company_form}')

        company_code = company_form.read_text(encoding='utf-8', errors='ignore')
        result = DynamicCodeValidator(
            user_request=SUBAREA_COMPANY_BASELINE_REQUEST
        ).validate_code(company_code, {})

        self.assertTrue(result['valid'])
        self.assertFalse(result['block_generation'])
        self.assertEqual(result['critical_errors'], [])

    def test_dynamic_validator_parses_simple_fields_and_primary_key(self):
        validator = DynamicCodeValidator(
            user_request=(
                "Create complete Sub Area form. "
                "Table: tblsubarea "
                "Primary key: SubArea_Code "
                "Fields: SubArea_Code, Area_Code, SubArea_Name, Is_Active"
            )
        )

        self.assertEqual(validator.expected_patterns['table_name'], 'tblsubarea')
        self.assertEqual(validator.expected_patterns['primary_key'], 'SubArea_Code')
        self.assertEqual(
            validator.expected_patterns['field_names'],
            ['SubArea_Code', 'Area_Code', 'SubArea_Name', 'Is_Active']
        )

    def test_dynamic_validator_compact_prompt_excludes_dependency_tables_from_fields(self):
        validator = DynamicCodeValidator(user_request=SUBAREA_REQUEST)

        self.assertEqual(validator.expected_patterns['table_name'], 'tblsubarea')
        self.assertEqual(validator.expected_patterns['primary_key'], 'SubArea_Code')
        self.assertEqual(
            validator.expected_patterns['field_names'],
            ['SubArea_Code', 'Area_Code', 'SubArea_Name', 'Is_Active']
        )

    def test_dynamic_fallback_field_extractor_stops_before_dependency_sections(self):
        fields = CodeGenerationViewSet()._extract_requested_fields_from_prompt(SUBAREA_REQUEST)
        self.assertEqual(fields, ['SubArea_Code', 'Area_Code', 'SubArea_Name', 'Is_Active'])

    def test_dynamic_validator_ignores_company_helper_names_when_extracting_fields(self):
        validator = DynamicCodeValidator(
            user_request=(
                "Create complete Area master form. "
                "Table: tblarea "
                "Primary key: Area_Code "
                "Master Fields (USE EXACT NAMES, NO EXTRA FIELDS): "
                "- Area_Code | DB: varchar | Input: readonly textbox | Required: Yes "
                "- Area_Name | DB: varchar | Input: textbox | Required: Yes "
                "- Is_Active | DB: tinyint | Input: checkbox | Required: Yes "
                "Required Company Patterns (MANDATORY): "
                "- session_start, db_insert, db_update, db_delete, db_getRecord "
                "- funStartTran/funEndTran - fun_log - AJAX GetMaxID + maxid() "
                "- formValidation + checkKeycode"
            )
        )

        self.assertEqual(
            validator.expected_patterns['field_names'],
            ['Area_Code', 'Area_Name', 'Is_Active']
        )

    def test_dynamic_validator_enforces_field_contract_and_output_escaping(self):
        validator = DynamicCodeValidator(
            user_request=(
                "Create complete Area master form. "
                "Table: tblarea "
                "Primary key: Area_Code "
                "Master Fields: "
                "- Area_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes "
                "- Area_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes "
                "- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No "
            )
        )
        code = """
        <form class="form-horizontal">
          <input type="text" name="Area_Code" value="<?=htmlspecialchars($Area_Code, ENT_QUOTES);?>">
          <input type="text" name="Area_Name" value="<?=htmlspecialchars($Area_Name, ENT_QUOTES);?>">
          <input type="checkbox" name="Is_Active" value="1">
        </form>
        """

        result = validator._validate_field_contract(code)

        self.assertTrue(result['valid'])
        self.assertEqual(result['errors'], [])

    def test_dynamic_validator_allows_common_scaffold_hidden_fields(self):
        validator = DynamicCodeValidator(
            user_request=(
                "Create complete Customer master form. "
                "Table: tblcustomer "
                "Primary key: Customer_Code "
                "Master Fields: "
                "- Customer_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes "
                "- Customer_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes "
                "- Contact_Number | DB: VARCHAR(20) | Input: textbox | Required: No "
                "- Email | DB: VARCHAR(100) | Input: textbox | Required: No "
                "- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No "
            )
        )
        code = """
        <form class="form-horizontal">
          <input type="hidden" name="action" value="save">
          <input type="hidden" name="major" value="">
          <input type="hidden" name="txtmode" value="new">
          <input type="hidden" name="CTRL_HID_VALUE" value="<?=htmlspecialchars($CTRL_HID_VALUE, ENT_QUOTES);?>">
          <input type="text" name="Customer_Code" value="<?=htmlspecialchars($Customer_Code, ENT_QUOTES);?>">
          <input type="text" name="Customer_Name" value="<?=htmlspecialchars($Customer_Name, ENT_QUOTES);?>">
          <input type="text" name="Contact_Number" value="<?=htmlspecialchars($Contact_Number, ENT_QUOTES);?>">
          <input type="text" name="Email" value="<?=htmlspecialchars($Email, ENT_QUOTES);?>">
          <input type="checkbox" name="Is_Active" value="1">
        </form>
        """

        result = validator._validate_field_contract(code)

        self.assertTrue(result['valid'])
        self.assertEqual(result['errors'], [])

    def test_code_assembler_sanitizes_raw_php_field_values(self):
        assembler = CodeAssembler()
        raw = """
        <form>
          <input type="text" name="Customer_Name" value="<?=$customer_name;?>">
          <input type="text" name="Email" value="<?php echo $email; ?>">
          <textarea name="Remarks"><?=$remarks;?></textarea>
          <textarea name="Description"><?php echo $description; ?></textarea>
        </form>
        """

        normalized = assembler._sanitize_rendered_dynamic_values(raw)

        self.assertIn('value="<?=htmlspecialchars($customer_name, ENT_QUOTES);?>"', normalized)
        self.assertIn('value="<?php echo htmlspecialchars($email, ENT_QUOTES); ?>"', normalized)
        self.assertIn('><?=htmlspecialchars($remarks, ENT_QUOTES);?></textarea>', normalized)
        self.assertIn('><?php echo htmlspecialchars($description, ENT_QUOTES); ?></textarea>', normalized)

    def test_code_assembler_extracts_nested_maxid_ajax_without_truncation(self):
        assembler = CodeAssembler()
        entity_js = """
        function maxid() {
            $.ajax({
                url: "api.php",
                data: { action: "GetMaxID" },
                success: function(resp) {
                    var payload = { value: resp.next, nested: { ok: true } };
                    document.getElementById("Code").value = payload.value;
                }
            });
        }
        function checkKeycode(e) { return true; }
        """

        head_scripts = assembler._extract_head_scripts_from_entity_js(entity_js)

        self.assertIn("function maxid()", head_scripts)
        self.assertIn("nested: { ok: true }", head_scripts)
        self.assertIn('document.getElementById("Code").value', head_scripts)
        self.assertIn("});", head_scripts)

    def test_code_assembler_rejects_malformed_maxid_ajax_block(self):
        assembler = CodeAssembler()
        malformed = """
        function maxid() {
            $.ajax({
                url: "api.php",
                success: function(resp) {
                    console.log(resp);
                }
            })
        }
        """

        with self.assertRaises(ValueError) as exc:
            assembler._extract_head_scripts_from_entity_js(malformed)

        self.assertIn("Malformed maxid() AJAX block detected", str(exc.exception))

    def test_code_assembler_repairs_malformed_form_action_js_assignment(self):
        assembler = CodeAssembler()
        broken = """
        <script>
        function btnsave_click() {
            var form = document.getElementById('frm');
            form.action = "<?php echo $form2, ENT_QUOTES);?>";
            form.submit();
        }
        </script>
        <form class="form-horizontal" id="frm" action="<?=$form2;?>>
        </form>
        """

        repaired = assembler._repair_known_form_action_patterns(broken)

        self.assertIn('form.action = "<?php echo $form2; ?>";', repaired)
        self.assertIn('action="<?=$form2;?>"', repaired)

    def test_code_assembler_manual_merge_normalizes_embedded_form_tag(self):
        assembler = CodeAssembler()
        sections = {
            "form_fields": """
            <form id="frmCostCenter" method="post" action="<?=$form?>">
                <input type="text" name="CostCenter_Code" value="<?=$CostCenter_Code?>">
            </form>
            """
        }
        contract = {
            "file_name": "frmCostCenter.php",
            "table_name": "tblcostcenter",
            "title": "Cost Center",
            "fields": [{"name": "CostCenter_Code"}],
        }

        merged = assembler._merge_manual(sections, contract, {})

        self.assertEqual(merged.lower().count("<form"), 1)
        self.assertEqual(merged.lower().count("</form>"), 1)
        self.assertIn('id="frm"', merged)
        self.assertIn('action="<?=$form2;?>"', merged)
        self.assertNotIn('multipart/form-data">">', merged)
        self.assertNotIn('multipart/form-data">>', merged)
        self.assertIn("$('#frm').submit();", merged)
        self.assertIn("$('#frm').formValidation({", merged)

    def test_keyboard_navigation_is_warning_when_not_requested(self):
        repo_root = Path(__file__).resolve().parents[2]
        matches = sorted(repo_root.glob('company_codebases/**/frmSubArea.php'))
        self.assertTrue(matches, 'Expected at least one real frmSubArea.php in company_codebases')
        code = matches[0].read_text(encoding='utf-8', errors='ignore')
        code = code.replace('checkKeycode', 'removedKeyboardNav')
        validator = DynamicCodeValidator(
            user_request=SUBAREA_COMPANY_BASELINE_REQUEST
        )

        result = validator.validate_code(code, {})

        self.assertTrue(result['valid'])
        self.assertFalse(result['block_generation'])
        self.assertEqual(result['critical_errors'], [])
        self.assertIn(
            "Keyboard navigation handler checkKeycode(...) was not detected.",
            result['warnings']
        )

    def test_dynamic_validator_blocks_security_and_structure_antipatterns(self):
        repo_root = Path(__file__).resolve().parents[2]
        matches = sorted(repo_root.glob('company_codebases/**/frmSubArea.php'))
        self.assertTrue(matches, 'Expected at least one real frmSubArea.php in company_codebases')

        base_code = matches[0].read_text(encoding='utf-8', errors='ignore')
        bad_tail = """
        <?php
        $filter = "SubArea_Code='" . $_REQUEST['SubArea_Code'] . "'";
        ?>
        <form class="form-horizontal" action="<?=$form2;?>>
            <?= $_REQUEST['SubArea_Name']; ?>
        </form>
        <script>
        function maxid(){ return 1; }
        function maxid(){ return 2; }
        </script>
        <!-- populate options -->
        """
        validator = DynamicCodeValidator(user_request=SUBAREA_REQUEST)

        result = validator.validate_code(base_code + bad_tail, {})

        self.assertFalse(result['valid'])
        self.assertTrue(result['block_generation'])
        error_blob = " | ".join(result['critical_errors'])
        self.assertIn("Unsafe SQL filter concatenation", error_blob)
        self.assertIn("Malformed form action attribute", error_blob)
        self.assertIn("Duplicate maxid() JavaScript function", error_blob)

    def test_master_detail_validator_allows_shared_parent_key_between_master_and_detail(self):
        validator = DynamicCodeValidator(user_request="Master Table: tblinvoice Detail Table: tblinvoicedetail")
        validator.expected_patterns['table_name'] = 'tblinvoice'
        validator.expected_patterns['detail_table'] = 'tblinvoicedetail'
        validator.expected_patterns['primary_key'] = 'Invoice_No'
        validator.expected_patterns['detail_field_names'] = ['Invoice_No', 'Sr_No', 'Product_Code']
        validator.expected_patterns['field_contract'] = [
            {'name': 'Invoice_No', 'section': 'master'},
            {'name': 'Invoice_Date', 'section': 'master'},
            {'name': 'Invoice_No', 'section': 'detail'},
            {'name': 'Sr_No', 'section': 'detail'},
            {'name': 'Product_Code', 'section': 'detail'},
        ]

        code = """
        <input type="hidden" name="TXTCOUNTACC" value="<?=htmlspecialchars($TXTCOUNTACC, ENT_QUOTES);?>">
        <?php
        $columns = [
            'Invoice_No' => $_POST['Invoice_No'],
            'Invoice_Date' => $_POST['Invoice_Date'],
        ];
        db_insert($table, $columns);
        $count = intval($_POST['TXTCOUNTACC'] ?? $_REQUEST['TXTCOUNTACC'] ?? 0);
        for ($i = 1; $i <= $count; $i++) {
            db_insert('tblinvoicedetail', [
                'Invoice_No' => $_POST['Invoice_No'],
                'Sr_No' => $_POST['Sr_No' . $i],
                'Product_Code' => $_POST['Product_Code' . $i],
            ]);
        }
        db_delete('tblinvoicedetail', 'Invoice_No = ?', [$_POST['Invoice_No']]);
        ?>
        """

        result = validator._validate_master_detail_structure(code)

        self.assertTrue(result['valid'])
        self.assertEqual(result['errors'], [])

    def test_master_detail_validator_still_blocks_detail_only_field_leakage(self):
        validator = DynamicCodeValidator(user_request="Master Table: tblinvoice Detail Table: tblinvoicedetail")
        validator.expected_patterns['table_name'] = 'tblinvoice'
        validator.expected_patterns['detail_table'] = 'tblinvoicedetail'
        validator.expected_patterns['primary_key'] = 'Invoice_No'
        validator.expected_patterns['detail_field_names'] = ['Invoice_No', 'Sr_No', 'Product_Code']
        validator.expected_patterns['field_contract'] = [
            {'name': 'Invoice_No', 'section': 'master'},
            {'name': 'Invoice_Date', 'section': 'master'},
            {'name': 'Invoice_No', 'section': 'detail'},
            {'name': 'Sr_No', 'section': 'detail'},
            {'name': 'Product_Code', 'section': 'detail'},
        ]

        bad_code = """
        <input type="hidden" name="TXTCOUNTACC" value="<?=htmlspecialchars($TXTCOUNTACC, ENT_QUOTES);?>">
        <?php
        $columns = [
            'Invoice_No' => $_POST['Invoice_No'],
            'Invoice_Date' => $_POST['Invoice_Date'],
            'Product_Code' => $_POST['Product_Code'], // illegal detail-only leak
        ];
        db_insert($table, $columns);
        $count = intval($_POST['TXTCOUNTACC'] ?? $_REQUEST['TXTCOUNTACC'] ?? 0);
        for ($i = 1; $i <= $count; $i++) {
            db_insert('tblinvoicedetail', [
                'Invoice_No' => $_POST['Invoice_No'],
                'Sr_No' => $_POST['Sr_No' . $i],
                'Product_Code' => $_POST['Product_Code' . $i],
            ]);
        }
        db_delete('tblinvoicedetail', 'Invoice_No = ?', [$_POST['Invoice_No']]);
        ?>
        """

        result = validator._validate_master_detail_structure(bad_code)

        self.assertFalse(result['valid'])
        self.assertIn(
            "Detail fields leaked into master insert context: Product_Code",
            " | ".join(result['errors'])
        )

    def test_master_detail_validator_does_not_flag_amount_substring_in_master_fields(self):
        validator = DynamicCodeValidator(user_request="Master Table: tblinvoice Detail Table: tblinvoicedetail")
        validator.expected_patterns['table_name'] = 'tblinvoice'
        validator.expected_patterns['detail_table'] = 'tblinvoicedetail'
        validator.expected_patterns['primary_key'] = 'Invoice_No'
        validator.expected_patterns['detail_field_names'] = ['Invoice_No', 'Amount', 'Rate']
        validator.expected_patterns['field_contract'] = [
            {'name': 'Invoice_No', 'section': 'master'},
            {'name': 'Total_Amount', 'section': 'master'},
            {'name': 'Net_Amount', 'section': 'master'},
            {'name': 'Invoice_No', 'section': 'detail'},
            {'name': 'Amount', 'section': 'detail'},
            {'name': 'Rate', 'section': 'detail'},
        ]

        code = """
        <input type="hidden" name="TXTCOUNTACC" value="<?=htmlspecialchars($TXTCOUNTACC, ENT_QUOTES);?>">
        <?php
        $columns = [
            'Invoice_No' => $_POST['Invoice_No'],
            'Total_Amount' => $_POST['Total_Amount'],
            'Net_Amount' => $_POST['Net_Amount'],
        ];
        db_insert($table, $columns);
        $count = intval($_POST['TXTCOUNTACC'] ?? $_REQUEST['TXTCOUNTACC'] ?? 0);
        for ($i = 1; $i <= $count; $i++) {
            db_insert('tblinvoicedetail', [
                'Invoice_No' => $_POST['Invoice_No'],
                'Amount' => $_POST['Amount' . $i],
                'Rate' => $_POST['Rate' . $i],
            ]);
        }
        db_delete('tblinvoicedetail', 'Invoice_No = ?', [$_POST['Invoice_No']]);
        ?>
        """

        result = validator._validate_master_detail_structure(code)

        self.assertTrue(result['valid'])
        self.assertEqual(result['errors'], [])
