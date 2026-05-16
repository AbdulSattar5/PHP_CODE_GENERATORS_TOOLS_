# Validator Hard-Fail Checklist

Source forms reviewed:

- `frmArea.php`
- `frmSubArea.php`
- `frmCustomer.php`

## Category A — Hard Fail

The following conditions must block save and trigger regeneration or user-facing diagnostics:

- Missing `include("include/config.inc.php");`
- Missing `include("include/topmenu.php");`
- Missing `include("include/sidemenu.php");`
- Missing `include("include/formheader.php");`
- Missing `include("include/footer.php");`
- Footer include appears more than once
- Form is missing `class="form-horizontal"`
- Form is missing `id="frm"` or `name="frm"`
- Session keys do not follow the canonical lower-case contract:
  `user_id`, `comp_code`, `login_id`
- `GetMaxID` PHP/JS contract mismatch:
  scalar PHP output paired with JSON JS consumer, or vice versa
- `btnsave_click()` missing when form submit lifecycle requires it
- `formValidation` submit chain missing:
  `.on('success.form.fv', ...) -> btnsave_click()`
- Edit binding variable mismatch:
  record fetch assigns one variable while form fields read another
- Placeholder count and parameter count mismatch in company helper calls
- Missing common audit/company columns in generated insert or update maps:
  `Comp_Code`, `UserId`, `Login_ID`
- Master-detail form declares detail behavior but lacks `TXTCOUNTACC` and detail save loop

## Category B — Warn Only

The following conditions should be logged but do not automatically block save:

- Missing optional plugin hooks such as `select2`
- Missing advanced grid arrays in a master-only form
- Missing optional AJAX helpers not requested by the user
- Cosmetic differences in field layout that do not break company flow
- Extra non-breaking comments or whitespace differences
