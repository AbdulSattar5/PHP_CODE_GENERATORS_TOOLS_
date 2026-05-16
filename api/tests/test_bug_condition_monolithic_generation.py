"""
Bug Condition Exploration Test - Monolithic Generation Without Template Injection

**CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
**DO NOT attempt to fix the test or the code when it fails**
**NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation

**Validates: Requirements 1.1, 1.2, 1.3, 1.5, 1.6, 1.8**

This test demonstrates that the current InlinePHPGenerator generates complete monolithic PHP files
including framework components (session_start, includes, CSS links, footer scripts) instead of only
generating dynamic content that gets injected into a company framework template.

The test uses concrete failing cases to ensure reproducibility.
"""

from django.test import SimpleTestCase
from agents.graph.inline_php_generator import InlinePHPGenerator
from agents.utils.dynamic_form_template import DynamicFormTemplate
import re


class BugConditionMonolithicGenerationTest(SimpleTestCase):
    """
    Property 1: Bug Condition - Monolithic Generation Without Template Injection
    
    This test verifies that the UNFIXED code exhibits the bug condition:
    - LLM generates complete monolithic PHP files including framework components
    - Generated code does NOT use DynamicFormTemplate.merge_with_generated()
    - Structure order is inconsistent with company pattern
    - Missing mandatory company functions
    - Field types do NOT map correctly to UI components
    - Delete operations missing pre-delete dependency checks
    """
    
    def setUp(self):
        self.generator = InlinePHPGenerator(
            {
                'api_key': 'test-key',
                'model': 'gpt-4o-mini',
            }
        )
    
    def test_concrete_case_1_simple_customer_form_exhibits_bug(self):
        """
        Example 1: Generated code includes session_start and includes (should be in template)
        
        **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
        """
        prompt = """Create complete Customer master form.

Table: tblcustomer
File name: frmCustomer.php
Title: Customer
CaseType: Customer

Primary Key:
- Customer_Code | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields:
- Customer_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Customer_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Contact_Number | DB: VARCHAR(20) | Input: textbox | Required: No
- Email | DB: VARCHAR(100) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- AJAX GetMaxID handler + maxid() JS
- formValidation per field
"""
        
        # Extract metadata from prompt
        request_metadata = self.generator._extract_explicit_request_metadata(prompt)
        company_fields = self.generator._extract_field_names_from_example('', prompt)
        
        # Build the generation prompt
        generation_prompt = self.generator._build_compact_generation_prompt(
            intent={'form_title': 'tblcustomer'},
            user_request=prompt,
            company_fields=company_fields,
            naming_metadata=request_metadata,
            hierarchy_pattern={},
            grid_pattern={},
        )
        
        # Analyze the prompt to see if it asks for framework components
        analysis = {
            'prompt_asks_for_session_start': 'session_start' in generation_prompt.lower(),
            'prompt_asks_for_includes': 'include' in generation_prompt.lower(),
            'prompt_asks_for_html_wrapper': 'html' in generation_prompt.lower() or 'doctype' in generation_prompt.lower(),
            'prompt_mentions_template_injection': 'template' in generation_prompt.lower() and 'inject' in generation_prompt.lower(),
            'prompt_mentions_fixed_parts': 'fixed' in generation_prompt.lower() and 'variable' in generation_prompt.lower(),
        }
        
        # **BUG CONDITION**: The prompt should NOT ask for framework components
        # **BUG CONDITION**: The prompt SHOULD mention template injection and fixed/variable parts
        
        # This assertion will FAIL on unfixed code (proving the bug exists)
        self.assertFalse(
            analysis['prompt_asks_for_session_start'],
            "BUG DETECTED: Prompt asks LLM to generate session_start (should be in template)"
        )
        self.assertFalse(
            analysis['prompt_asks_for_includes'],
            "BUG DETECTED: Prompt asks LLM to generate includes (should be in template)"
        )
        self.assertTrue(
            analysis['prompt_mentions_template_injection'],
            "BUG DETECTED: Prompt does not mention template injection (should use DynamicFormTemplate.merge_with_generated())"
        )
    
    def test_concrete_case_2_area_form_missing_company_functions(self):
        """
        Example 2: Generated code missing db_insert/db_update functions (should be enforced)
        
        **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
        """
        prompt = """Create complete Area master form.

Table: tblarea
File name: frmArea.php
Title: Area
CaseType: Area

Primary Key:
- Area_Code | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields:
- Area_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Area_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Region_Code | DB: VARCHAR(20) | Input: select | Required: Yes

Dependencies:
- tblcustomer | field=Area_Code | message=Cannot delete if used in customer
- tblsalesman | field=Area_Code | message=Cannot delete if used in salesman

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- pre-delete dependency checks for: tblcustomer, tblsalesman
"""
        
        # Extract metadata from prompt
        request_metadata = self.generator._extract_explicit_request_metadata(prompt)
        company_fields = self.generator._extract_field_names_from_example('', prompt)
        
        # Build the generation prompt
        generation_prompt = self.generator._build_compact_generation_prompt(
            intent={'form_title': 'tblarea'},
            user_request=prompt,
            company_fields=company_fields,
            naming_metadata=request_metadata,
            hierarchy_pattern={},
            grid_pattern={},
        )
        
        # Check if prompt enforces mandatory company functions
        mandatory_functions = ['db_insert', 'db_update', 'db_delete', 'db_getRecord', 'getrows', 'getvalue', 'funStartTran', 'funEndTran']
        
        functions_mentioned = {
            func: func in generation_prompt
            for func in mandatory_functions
        }
        
        # **BUG CONDITION**: The prompt should explicitly enforce all mandatory company functions
        # This assertion will FAIL on unfixed code (proving the bug exists)
        missing_functions = [func for func, mentioned in functions_mentioned.items() if not mentioned]
        
        self.assertEqual(
            len(missing_functions), 0,
            f"BUG DETECTED: Prompt does not enforce mandatory company functions: {missing_functions}"
        )
    
    def test_concrete_case_3_field_type_mapping_not_enforced(self):
        """
        Example 3: varchar field becomes generic input instead of text input with validation
        
        **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
        """
        prompt = """Create complete Customer master form.

Table: tblcustomer
File name: frmCustomer.php
Title: Customer
CaseType: Customer

Primary Key:
- Customer_Code | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields:
- Customer_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Customer_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Contact_Number | DB: VARCHAR(20) | Input: textbox | Required: No
- Email | DB: VARCHAR(100) | Input: textbox | Required: No
- Is_Active | DB: TINYINT(1) | Input: checkbox | Required: No

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- AJAX GetMaxID handler + maxid() JS
- formValidation per field
"""
        
        # Extract metadata from prompt
        request_metadata = self.generator._extract_explicit_request_metadata(prompt)
        company_fields = self.generator._extract_field_names_from_example('', prompt)
        
        # Build the generation prompt
        generation_prompt = self.generator._build_compact_generation_prompt(
            intent={'form_title': 'tblcustomer'},
            user_request=prompt,
            company_fields=company_fields,
            naming_metadata=request_metadata,
            hierarchy_pattern={},
            grid_pattern={},
        )
        
        # Check if prompt includes explicit field type mapping instructions
        field_type_mappings = {
            'varchar': 'text input' in generation_prompt.lower(),
            'int': 'numeric input' in generation_prompt.lower() or 'number input' in generation_prompt.lower(),
            'tinyint': 'checkbox' in generation_prompt.lower(),
            'select': 'dropdown' in generation_prompt.lower() or 'select' in generation_prompt.lower(),
        }
        
        # **BUG CONDITION**: The prompt should include explicit field type mapping instructions
        # This assertion will FAIL on unfixed code (proving the bug exists)
        missing_mappings = [field_type for field_type, mentioned in field_type_mappings.items() if not mentioned]
        
        self.assertLessEqual(
            len(missing_mappings), 1,
            f"BUG DETECTED: Prompt does not include explicit field type mapping instructions for: {missing_mappings}"
        )
    
    def test_concrete_case_4_predelete_checks_not_enforced(self):
        """
        Example 4: Delete operation missing getrows() pre-delete check
        
        **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists)
        """
        prompt = """Create complete Area master form.

Table: tblarea
File name: frmArea.php
Title: Area
CaseType: Area

Primary Key:
- Area_Code | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields:
- Area_Code | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- Area_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Region_Code | DB: VARCHAR(20) | Input: select | Required: Yes

Dependencies:
- tblcustomer | field=Area_Code | message=Cannot delete if used in customer
- tblsalesman | field=Area_Code | message=Cannot delete if used in salesman

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- pre-delete dependency checks for: tblcustomer, tblsalesman
"""
        
        # Extract metadata from prompt
        request_metadata = self.generator._extract_explicit_request_metadata(prompt)
        company_fields = self.generator._extract_field_names_from_example('', prompt)
        
        # Build the generation prompt
        generation_prompt = self.generator._build_compact_generation_prompt(
            intent={'form_title': 'tblarea'},
            user_request=prompt,
            company_fields=company_fields,
            naming_metadata=request_metadata,
            hierarchy_pattern={},
            grid_pattern={},
        )
        
        # Check if prompt enforces pre-delete dependency checks
        predelete_enforcement = {
            'mentions_predelete': 'pre-delete' in generation_prompt.lower() or 'predelete' in generation_prompt.lower(),
            'mentions_getrows_check': 'getrows' in generation_prompt.lower() and ('check' in generation_prompt.lower() or 'dependency' in generation_prompt.lower()),
            'mentions_alert_exit': ('alert' in generation_prompt.lower() or 'message' in generation_prompt.lower()) and 'exit' in generation_prompt.lower(),
        }
        
        # **BUG CONDITION**: The prompt should enforce pre-delete dependency checks with getrows() and alert/exit
        # This assertion will FAIL on unfixed code (proving the bug exists)
        missing_enforcement = [check for check, present in predelete_enforcement.items() if not present]
        
        self.assertEqual(
            len(missing_enforcement), 0,
            f"BUG DETECTED: Prompt does not enforce pre-delete dependency checks: {missing_enforcement}"
        )
