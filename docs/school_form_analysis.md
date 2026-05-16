# School Form Analysis and Fix Report

## Scope
- Prompt added for School master form in the prompt guide.
- Generated School form output stored as the public fixture `api/tests/fixtures/generated/frmSchool.php`.
- Compared School output against company baseline form patterns from frmArea.php, frmSubArea.php, and frmCustomer.php.

## Company-Baseline Comparison Checklist

1. Include chain and order
- Required: include/config.inc.php, include/topmenu.php, include/sidemenu.php, include/formheader.php, include/footer.php.
- School output status: PASS.

2. Single canonical form contract
- Required: one <form> with id="frm", name="frm", method="POST", class contains form-horizontal.
- School output status: PASS.

3. Session and audit contract
- Required session keys: user_id, comp_code, login_id.
- Required audit/write columns: CreationDateTime, Comp_Code, UserId, Login_ID.
- School output status: PASS.

4. CRUD function contract
- Required use of company functions: db_insert, db_update, db_delete, db_getRecord, getrows/getvalue.
- School output status: PASS.

5. GetMaxID contract
- Required: scalar PHP return, JS handles scalar response, maxid() present.
- School output status: PASS.

6. Submit lifecycle contract
- Required: formValidation initialization, success.form.fv event, btnsave_click() path.
- School output status: PASS.

7. Pre-delete dependency check
- Required: tblstudent dependency guard before delete.
- School output status: PASS.

8. Escaping and safe output
- Required: rendered dynamic values use htmlspecialchars(..., ENT_QUOTES, 'UTF-8').
- School output status: PASS.

## Missing Items Found and Fixed in Pipeline

1. Missing jQuery submit normalization in manual assembler path
- Symptom: Regression expected $('#frm').submit(); but output only used document.frm.submit().
- Fix: CodeAssembler manual merge now emits jQuery submit path with plain JS fallback.
- File updated: agents/graph/code_assembler.py.

2. Missing School prompt in guide
- Symptom: No parser-safe School example available.
- Fix: Added Example 4 - School Master prompt.
- File updated: PROMPT_EXAMPLES_GUIDE.md.

## Notes
- This report is based on the strict company contract blueprint and current hard-validator behavior.
- School output is generated in company style and can be used as a reference fixture for future regressions.
