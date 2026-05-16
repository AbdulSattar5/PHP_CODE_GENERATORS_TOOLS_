# Company Form Section Blueprint

Source forms reviewed from the sample fixture set:

- `api/tests/fixtures/sample_company_codebase/frmArea.php`
- `api/tests/fixtures/sample_company_codebase/frmSubArea.php`
- `api/tests/fixtures/sample_company_codebase/frmCustomer.php`

This document captures the canonical section order that the generator should target, even when a specific company form does not exist.

## Canonical Generation Tag Order

1. `BOOTSTRAP_PHP`
2. `AJAX_HANDLERS_PHP`
3. `CRUD_LOGIC_PHP`
4. `HEAD_HTML`
5. `ENTITY_JS`
6. `BODY_OPEN_HTML`
7. `FORM_HTML`
8. `BODY_END_HTML`

## Canonical Rendered File Order

1. PHP bootstrap:
   `@session_start();`
   `include("include/config.inc.php");`
   canonical variables such as `$form`, `$form2`, `$table`, `$title`
2. Optional scalar AJAX handlers:
   `GetMaxID`, `GetCOSTCENTER`, or other request-driven handlers
3. CRUD and edit-display logic:
   delete
   update display / record fetch
   save or update transaction block
4. PHP close tag
5. `<!DOCTYPE html>` and `<head>`
6. Head helper JavaScript:
   `Breakpoints();`
   `maxid()` when required
   `btnsave_click()`
   `checkKeycode()`
7. `<body ...>`
8. Body includes and layout wrapper:
   `include("include/topmenu.php");`
   `include("include/sidemenu.php");`
   `<div class="page ...">`
   `include("include/formheader.php");`
   `<div class="page-content ...">`
9. `<form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">`
10. Field rows in company grid layout
11. Buttons and hidden workflow fields:
   `btnSave`
   `btnReset`
   `txtmode`
   `CTRL_HID_VALUE`
   `TXTCOUNTACC` for master-detail forms
12. Single footer include:
   `include("include/footer.php");`
13. Bottom script bundle
14. Page init and `formValidation` chain

## Required Includes And Order

- Top include block:
  `include("include/config.inc.php");`
- Body include block:
  `include("include/topmenu.php");`
  `include("include/sidemenu.php");`
  `include("include/formheader.php");`
- Footer block:
  `include("include/footer.php");`

## Form Structure Rules

- Form must use `class="form-horizontal"`.
- Form must use `id="frm"` and `name="frm"`.
- Form method is `POST`.
- Form action points to `<?=$form2;?>`.
- Hidden workflow fields appear inside the form, not outside it.
- Footer must appear exactly once.

## JavaScript Lifecycle Rules

- `btnsave_click()` is the canonical save submit function.
- `document.onkeydown = checkKeycode` is the canonical keyboard entry path.
- If `formValidation` is used, the canonical chain is:
  `$('#frm').formValidation(...).on('success.form.fv', function(e) { e.preventDefault(); btnsave_click(); });`
- `maxid()` is optional, but when present it is defined before the body and is typically called from `onLoad`.

## GetMaxID Contract

Observed company forms return plain scalar output for `GetMaxID`, not JSON objects.

- PHP:
  `echo $MAXID;`
- JS:
  assigns the raw `data` or response string directly to the input field

## Master-Detail Scaffold

Observed canonical detail workflow from `frmCustomer.php`:

- hidden counter field: `TXTCOUNTACC`
- detail delete before reinsert on save/update
- detail loop:
  `for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++)`
- row arrays such as `gridData` may exist in complex forms

## Canonical Edit Binding

- Company forms primarily use `$obj` as the record binding variable in form fields.
- Generator should normalize edit-display state to `$obj[...]` in rendered output.
