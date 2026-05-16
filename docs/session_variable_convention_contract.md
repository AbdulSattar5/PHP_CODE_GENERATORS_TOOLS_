# Session And Variable Convention Contract

Source forms reviewed:

- `frmArea.php`
- `frmSubArea.php`
- `frmCustomer.php`

## Session Contract

Canonical session keys are lower-case:

- `$_SESSION['user_id']`
- `$_SESSION['comp_code']`
- `$_SESSION['login_id']`

Upper-case variants such as `User_ID`, `Comp_Code`, and `Login_ID` are not the approved runtime contract for generated output.

## Core PHP Variables

- `$form`
- `$form2`
- `$table`
- `$title`

Optional:

- `$sub_table` for master-detail forms
- `$Code`, `$MAXID`, `$CUST_Id`, etc. for entity-specific identifiers

## Canonical Audit Columns

For insert and update maps, the commonly required audit and company columns are:

- `CreationDateTime`
- `Comp_Code`
- `UserId`
- `Login_ID`

Entity-specific forms may add more columns, but these are the common baseline.

## Canonical Edit Binding Variable

- The preferred bound record variable inside form fields is `$obj`.
- Generated forms should not mix `$obj`, `$record`, and `$row_data` in the same final file.

## Canonical Hidden Workflow Fields

- `txtmode`
- `CTRL_HID_VALUE`
- `TXTCOUNTACC` for master-detail forms

## Canonical Form IDs And Button IDs

- Form id and name: `frm`
- Primary save button id: `btnSave`

## Canonical GetMaxID Contract

- PHP returns a plain scalar string
- JavaScript consumes that scalar directly
- Do not mix scalar PHP output with `response.maxid` JSON-style JavaScript
