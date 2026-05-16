"""
Phase 2 Part 2.3 & 2.4: Anchor-Based Merger and Section Assertions Tests
"""

import pytest
from agents.utils.anchor_based_merger import AnchorBasedMerger


class TestAnchorBasedMerger:
    """Test Phase 2.3: Anchor-Based Merger"""
    
    def test_merge_with_anchors(self):
        """Test merging sections using anchors"""
        template = """<?php
{{PHP_LOGIC}}
?>
<html>
<body>
{{FORM_FIELDS}}
</body>
</html>"""
        
        merger = AnchorBasedMerger(template)
        
        sections = {
            'php_logic': '$table = "tbltest";\ndb_insert($table, $data);\ndb_update($table, $data);\ndb_delete($table, "Code = ?", [$code]);',
            'form_fields': '<input type="text" name="Code" />'
        }
        
        result = merger.merge(sections)
        
        assert '$table = "tbltest"' in result
        assert '<input type="text" name="Code" />' in result
        assert '{{PHP_LOGIC}}' not in result
        assert '{{FORM_FIELDS}}' not in result
    
    def test_merge_without_template(self):
        """Test merging when no template provided"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': '$table = "tbltest";\ndb_insert($table, $data);\ndb_update($table, $data);\ndb_delete($table, "Code = ?", [$code]);',
            'form_fields': '<input type="text" name="Code" />'
        }
        
        result = merger.merge(sections)
        
        # Should build default template
        assert '$table = "tbltest"' in result
        assert '<input type="text" name="Code" />' in result
        assert '<!DOCTYPE html>' in result
    
    def test_validate_template(self):
        """Test template validation"""
        merger = AnchorBasedMerger()
        
        # Valid template
        valid_template = "<?php {{PHP_LOGIC}} ?> {{FORM_FIELDS}}"
        assert merger.validate_template(valid_template) == True
        
        # Invalid template (missing anchors)
        invalid_template = "<?php ?> <form></form>"
        assert merger.validate_template(invalid_template) == False
    
    def test_get_anchor_positions(self):
        """Test getting anchor positions"""
        template = """<?php
{{PHP_LOGIC}}
?>
<html>
{{FORM_FIELDS}}
</html>"""
        
        merger = AnchorBasedMerger(template)
        positions = merger.get_anchor_positions(template)
        
        assert 'PHP_LOGIC' in positions
        assert 'FORM_FIELDS' in positions
        assert positions['PHP_LOGIC'] < positions['FORM_FIELDS']


class TestSectionAssertions:
    """Test Phase 2.4: Section Assertions"""
    
    def test_assert_required_sections_pass(self):
        """Test that valid sections pass assertion"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': '$table = "tbltest";\ndb_insert($table, $data);\ndb_update($table, $data);\ndb_delete($table, "Code = ?", [$code]);',
            'form_fields': '<input type="text" name="Code" /><input type="text" name="Name" />'
        }
        
        # Should not raise
        merger._assert_required_sections(sections)
    
    def test_assert_empty_php_logic_fails(self):
        """Test that empty PHP logic fails assertion"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': '',
            'form_fields': '<input type="text" name="Code" />'
        }
        
        with pytest.raises(ValueError) as exc_info:
            merger._assert_required_sections(sections)
        
        assert 'php_logic is empty' in str(exc_info.value).lower()
    
    def test_assert_empty_form_fields_fails(self):
        """Test that empty form fields fails assertion"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': '$table = "tbltest";\ndb_insert($table, $data);\ndb_update($table, $data);\ndb_delete($table, "Code = ?", [$code]);',
            'form_fields': ''
        }
        
        with pytest.raises(ValueError) as exc_info:
            merger._assert_required_sections(sections)
        
        assert 'form_fields is empty' in str(exc_info.value).lower()
    
    def test_assert_missing_required_functions_fails(self):
        """Test that missing required functions fails assertion"""
        merger = AnchorBasedMerger()
        
        # PHP logic without required functions but long enough
        sections = {
            'php_logic': '$table = "tbltest"; $code = "test"; // No db functions here at all in this code',
            'form_fields': '<input type="text" name="Code" /><input type="text" name="Name" />'
        }
        
        with pytest.raises(ValueError) as exc_info:
            merger._assert_required_sections(sections)
        
        error_msg = str(exc_info.value).lower()
        assert 'missing required functions' in error_msg or 'db_insert' in error_msg
    
    def test_assert_no_input_elements_fails(self):
        """Test that form fields without input elements fails assertion"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': '$table = "tbltest";\ndb_insert($table, $data);\ndb_update($table, $data);\ndb_delete($table, "Code = ?", [$code]);',
            'form_fields': '<div>No inputs here</div>'
        }
        
        with pytest.raises(ValueError) as exc_info:
            merger._assert_required_sections(sections)
        
        assert 'no input elements' in str(exc_info.value).lower()
    
    def test_assert_too_short_section_fails(self):
        """Test that too short sections fail assertion"""
        merger = AnchorBasedMerger()
        
        sections = {
            'php_logic': 'short',  # Too short
            'form_fields': '<input type="text" name="Code" />'
        }
        
        with pytest.raises(ValueError) as exc_info:
            merger._assert_required_sections(sections)
        
        assert 'too short' in str(exc_info.value).lower()


class TestCodeAssemblerIntegration:
    """Test integration of anchor-based merger with CodeAssembler"""
    
    def test_code_assembler_uses_anchor_merger(self):
        """Test that CodeAssembler uses anchor-based merger"""
        from agents.graph.code_assembler import CodeAssembler
        
        assembler = CodeAssembler(template=None)
        
        generated_code = """
        <?php
        $form = "frmTest.php";
        $table = "tbltest";
        
        if ($_REQUEST['Action'] == 'Save') {
            db_insert($table, $data);
        }
        if ($_REQUEST['Action'] == 'Update') {
            db_update($table, $data);
        }
        if ($_REQUEST['Action'] == 'Delete') {
            db_delete($table, "Code = ?", [$code]);
        }
        ?>
        <input type="text" name="Test_Code" />
        """
        
        contract = {
            'table_name': 'tbltest',
            'file_name': 'frmTest.php',
            'title': 'Test',
            'dependencies': []
        }
        
        # Should use anchor-based merger
        result = assembler.assemble(generated_code, contract)
        
        assert result is not None
        assert len(result) > 0
