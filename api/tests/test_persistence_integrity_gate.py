from django.test import SimpleTestCase

from api.views import CodeGenerationViewSet


class PersistenceIntegrityGateTests(SimpleTestCase):
    def setUp(self):
        self.viewset = CodeGenerationViewSet()

    def test_detects_known_broken_ui_output_patterns(self):
        broken_code = """<?php $form='frmStudent.php'; ?>
<head>
  <script>
  document.onkeydown = checkKeycode
    {
      var keycode = 13;
    }
  function maxid() {
    $.ajax({
      url: '<?=$form?>',
      type: 'POST',
      data: {Action: 'GetMaxID'}
  </script>
</head>
<body>
  <form id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">
">
    <input name="STU_CODE" />
  </form>
  <script src="global/vendor/dropify/dropify.min.js">
$(function () { console.log('broken'); });
  </script>
</body>
</html>"""

        errors = self.viewset._collect_persistence_integrity_errors(broken_code)

        self.assertTrue(errors)
        self.assertTrue(any("Malformed form opening tag" in e for e in errors))
        self.assertTrue(any("document.onkeydown" in e for e in errors))
        self.assertTrue(any("maxid() AJAX block" in e for e in errors))
        self.assertTrue(any("external script tag" in e for e in errors))

    def test_accepts_minimal_clean_output(self):
        clean_code = """<?php $form='frmStudent.php'; $form2='frmStudent.php'; ?>
<head>
  <script>
    function maxid() {
      $.ajax({
        url: '<?=$form?>',
        type: 'POST',
        data: {Action: 'GetMaxID'},
        success: function(data) { console.log(data); }
      });
    }
  </script>
</head>
<body>
  <form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">
    <input name="STU_CODE" />
  </form>
  <script src="global/vendor/dropify/dropify.min.js"></script>
</body>
</html>"""

        errors = self.viewset._collect_persistence_integrity_errors(clean_code)
        self.assertEqual(errors, [])
