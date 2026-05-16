"""
Test for Template Layout Fix - Missing topmenu/sidemenu/footer includes

This test verifies the fix for the issue where validator expected topmenu.php,
sidemenu.php, and footer.php includes but the template wasn't injecting them.

Issue from logs/gencode.log line 1023:
- Missing shared header include (topmenu.php)
- Missing shared sidebar include (sidemenu.php/rightmenu.php)
- Missing shared footer include (footer.php)
- Missing company page container structure (page/page-content)
- Form must use company layout class `form-horizontal`
"""

import os
from pathlib import Path

import pytest

from agents.utils.dynamic_form_template import DynamicFormTemplate


SAMPLE_CODEBASE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_company_codebase"


class TestTemplateLayoutFix:
    """Test that template properly injects layout includes"""
    
    @pytest.fixture
    def template(self):
        """Load template from the public fixture codebase."""
        codebase_dir = str(SAMPLE_CODEBASE_DIR)
        if not os.path.exists(codebase_dir):
            pytest.skip("Sample codebase fixture not found")

        template = DynamicFormTemplate(codebase_dir)
        template.load()
        return template
    
    def test_template_extracts_includes(self, template):
        """Test that template extracts topmenu/sidemenu/footer from company files"""
        assert template._topmenu_include == 'include/topmenu.php'
        assert template._sidemenu_include == 'include/sidemenu.php'
        assert template._footer_include == 'include/footer.php'
    
    def test_merge_injects_topmenu(self, template):
        """Test that merge injects topmenu.php include"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        assert 'topmenu.php' in result
        assert '<?php include("include/topmenu.php"); ?>' in result
    
    def test_merge_injects_sidemenu(self, template):
        """Test that merge injects sidemenu.php include"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        assert 'sidemenu.php' in result
        assert '<?php include("include/sidemenu.php"); ?>' in result
    
    def test_merge_injects_footer(self, template):
        """Test that merge injects footer.php include"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        assert 'footer.php' in result
        assert '<?php include("include/footer.php"); ?>' in result
    
    def test_merge_injects_page_container(self, template):
        """Test that merge injects page container structure"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        assert '<div class="page">' in result
        assert '<div class="page-content">' in result
    
    def test_merge_injects_form_horizontal(self, template):
        """Test that merge wraps form fields in form-horizontal class"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        assert 'form-horizontal' in result
    
    def test_merge_output_size_increased(self, template):
        """Test that output size includes the extracted shared company layout."""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )

        # Public fixtures are intentionally compact, but the merged output should
        # still be substantially larger than a minimal generated form fragment.
        assert len(result) > 4000, f"Output too small: {len(result)} chars"
    
    def test_all_validator_requirements_met(self, template):
        """Test that all validator requirements from logs are met"""
        result = template.merge_with_generated(
            php_logic='<?php session_start(); ?>',
            form_fields='<input type="text" name="test" />',
            ajax_handlers='function GetMaxID() { }',
            crud_operations='db_insert(); db_update(); db_delete(); db_getRecord(); getrows(); getvalue(); funStartTran(); funEndTran();'
        )
        
        # All requirements from logs/gencode.log line 1023
        assert 'topmenu.php' in result, "Missing topmenu.php"
        assert 'sidemenu.php' in result, "Missing sidemenu.php"
        assert 'footer.php' in result, "Missing footer.php"
        assert '<div class="page">' in result, "Missing page container"
        assert '<div class="page-content">' in result, "Missing page-content"
        assert 'form-horizontal' in result, "Missing form-horizontal class"
