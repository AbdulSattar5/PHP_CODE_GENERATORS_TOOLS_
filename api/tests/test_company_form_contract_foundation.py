import os
from pathlib import Path

from agents.utils.company_form_blueprint import CompanyFormBlueprint
from agents.utils.company_style_normalizer import CompanyStyleNormalizer
from agents.validators.company_form_contract_validator import CompanyFormContractValidator


COMPANY_FORM_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_company_codebase"


def _read_company_form(file_name: str) -> str:
    path = os.path.join(str(COMPANY_FORM_DIR), file_name)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        return handle.read()


class TestCompanyFormBlueprint:
    def test_blueprint_exposes_runtime_contract_methods(self):
        blueprint = CompanyFormBlueprint.load_default()

        assert blueprint.get_section_order() == [
            "BOOTSTRAP_PHP",
            "AJAX_HANDLERS_PHP",
            "CRUD_LOGIC_PHP",
            "HEAD_HTML",
            "ENTITY_JS",
            "BODY_OPEN_HTML",
            "FORM_HTML",
            "BODY_END_HTML",
        ]
        assert blueprint.get_required_includes()["top"] == ["include/config.inc.php"]
        assert blueprint.get_required_includes()["body"] == [
            "include/topmenu.php",
            "include/sidemenu.php",
            "include/formheader.php",
        ]
        assert blueprint.get_audit_columns() == [
            "CreationDateTime",
            "Comp_Code",
            "UserId",
            "Login_ID",
        ]
        assert blueprint.get_session_contract() == {
            "user": "user_id",
            "company": "comp_code",
            "login": "login_id",
        }
        assert blueprint.get_getmaxid_contract()["php_return"] == "scalar"


class TestCompanyStyleNormalizer:
    def test_normalizer_repairs_session_casing_and_footer_count(self):
        normalizer = CompanyStyleNormalizer()
        broken = """<?php
session_start();
require_once('includes/config.php');
$user = $_SESSION['User_ID'];
$company = $_SESSION['Comp_Code'];
?>
<?php include("include/footer.php");?>
<?php include("include/footer.php");?>
"""
        normalized = normalizer.normalize(broken)

        assert 'include("include/config.inc.php");' in normalized
        assert "$_SESSION['user_id']" in normalized
        assert "$_SESSION['comp_code']" in normalized
        assert normalized.count('include("include/footer.php")') == 1

    def test_normalizer_repairs_edit_binding_variable(self):
        normalizer = CompanyStyleNormalizer()
        broken = """<?php
if($_REQUEST['action'] == 'Update') {
    $record = db_getRecord($table,$filter);
}
?>
<input value="<?php echo $record['Description'];?>" />
"""
        normalized = normalizer.normalize(broken)

        assert "$record" not in normalized
        assert "$obj" in normalized


class TestCompanyFormContractValidator:
    def test_validator_passes_real_company_area_form(self):
        validator = CompanyFormContractValidator()
        company_code = _read_company_form("frmArea.php")
        if not company_code:
            return

        result = validator.validate(company_code)
        assert result["passed"], result["errors"]

    def test_validator_passes_real_company_subarea_form(self):
        validator = CompanyFormContractValidator()
        company_code = _read_company_form("frmSubArea.php")
        if not company_code:
            return

        result = validator.validate(company_code)
        assert result["passed"], result["errors"]

    def test_validator_blocks_known_contract_mismatches(self):
        validator = CompanyFormContractValidator()
        broken = """<?php
@session_start();
include("include/topmenu.php");
if($_REQUEST['Action']=='GetMaxID'){
    echo json_encode(['maxid' => 1]);
    exit;
}
$user = $_SESSION['User_ID'];
$company = $_SESSION['Comp_Code'];
$login = $_SESSION['Login_ID'];
$record = db_getRecord($table, "Code=?", [$Code]);
$columns['Description'] = $_POST['Description'];
?>
<form id="frm" name="frm" method="POST" class="form-horizontal"></form>
<script>
function btnsave_click() {}
$('#frm').formValidation({});
function maxid(){ console.log(response.maxid); }
</script>
<?php include("include/footer.php");?>
<?php include("include/footer.php");?>
"""
        result = validator.validate(broken)

        assert not result["passed"]
        assert any("config.inc.php" in error for error in result["errors"])
        assert any("formheader.php" in error for error in result["errors"])
        assert any("Session key casing mismatch" in error for error in result["errors"])
        assert any("GetMaxID contract mismatch" in error for error in result["errors"])
        assert any("Footer include count mismatch" in error for error in result["errors"])
