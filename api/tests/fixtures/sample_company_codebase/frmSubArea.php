<?php
@session_start();
include("include/config.inc.php");

$form = "frmSubArea.php";
$form2 = "frmSubArea.php";
$table = "tblsubarea";
$title = "Sub Area";
$user_id = $_SESSION['user_id'] ?? '';
$comp_code = $_SESSION['comp_code'] ?? '';
$login_id = $_SESSION['login_id'] ?? '';
$obj = [];

if ($_REQUEST['Action'] == 'GetMaxID') {
    echo "SUBAREA-001";
    exit;
}

if ($_POST) {
    $columns = [
        'SubArea_Code' => $_POST['SubArea_Code'] ?? '',
        'Area_Code' => $_POST['Area_Code'] ?? '',
        'SubArea_Name' => $_POST['SubArea_Name'] ?? '',
        'Is_Active' => $_POST['Is_Active'] ?? 0,
        'CreationDateTime' => date('Y-m-d H:i:s'),
        'Comp_Code' => $comp_code,
        'UserId' => $user_id,
        'Login_ID' => $login_id,
    ];
    funStartTran();
    db_insert($table, $columns);
    funEndTran();
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title><?php echo htmlspecialchars($title, ENT_QUOTES, 'UTF-8'); ?></title>
    <script>
    Breakpoints();
    function maxid() {
        document.getElementById('SubArea_Code').value = 'SUBAREA-001';
    }
    function btnsave_click() {
        $('#frm').submit();
    }
    function checkKeycode(event) {
        return true;
    }
    document.onkeydown = checkKeycode;
    </script>
</head>
<body onload="maxid()">
<?php include("include/topmenu.php"); ?>
<?php include("include/sidemenu.php"); ?>
<div class="page">
<?php include("include/formheader.php"); ?>
<div class="page-content">
<form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">
    <input type="hidden" name="action" value="save">
    <input type="hidden" name="major" value="">
    <input type="hidden" name="txtmode" value="new">
    <input type="hidden" name="CTRL_HID_VALUE" value="<?=htmlspecialchars($CTRL_HID_VALUE ?? '', ENT_QUOTES, 'UTF-8');?>">

    <select name="Area_Code">
        <option value="">Select Area</option>
    </select>
    <input type="text" id="SubArea_Code" name="SubArea_Code" value="<?=htmlspecialchars($obj['SubArea_Code'] ?? '', ENT_QUOTES, 'UTF-8');?>">
    <input type="text" name="SubArea_Name" value="<?=htmlspecialchars($obj['SubArea_Name'] ?? '', ENT_QUOTES, 'UTF-8');?>">
    <input type="checkbox" name="Is_Active" value="1">

    <button type="button" id="btnSave" onclick="btnsave_click()">Save</button>
</form>
</div>
</div>
<?php include("include/footer.php"); ?>
<script>
$('#frm').formValidation({}).on('success.form.fv', function(e) {
    e.preventDefault();
    btnsave_click();
});
</script>
</body>
</html>
