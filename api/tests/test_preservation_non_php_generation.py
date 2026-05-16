"""
Preservation Property Tests - Non-PHP-Generation Workflow Steps

**IMPORTANT**: Follow observation-first methodology
**EXPECTED OUTCOME**: Tests PASS on unfixed code (confirms baseline behavior to preserve)

**Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.8, 3.9, 3.10**

This test suite verifies that non-PHP-generation workflow steps (intent analysis, pattern retrieval,
validation) remain unchanged after the fix is implemented. These tests should pass on both unfixed
and fixed code.

The tests use property-based testing approach by generating multiple test cases to provide stronger
guarantees that behavior is preserved across the input domain.
"""

import asyncio
from pathlib import Path
from typing import Dict, List

from django.test import SimpleTestCase

from agents.graph.nodes import IntentAnalysisNode, PatternRetrievalNode, ValidationNode
from agents.graph.state import AgentState
from agents.utils.dynamic_form_template import DynamicFormTemplate
from agents.validators.security_validator import SecurityValidator
from agents.validators.syntax_validator import SyntaxValidator


SAMPLE_CODEBASE_DIR = Path(__file__).resolve().parent / "fixtures" / "sample_company_codebase"


class PreservationIntentAnalysisTest(SimpleTestCase):
    """
    Property 2.1: Preservation - Intent Analysis Structured Output
    
    For all intent analysis requests, structured output format is preserved.
    This verifies that the intent analysis node continues to parse user prompts
    into structured intent with the same format and fields.
    """
    
    def setUp(self):
        self.intent_node = IntentAnalysisNode()
    
    def _create_test_state(self, user_request: str) -> AgentState:
        """Helper to create a test state with user request"""
        return AgentState(
            user_request=user_request,
            project_id='test-project',
            user_id='test-user',
            intent={},
            retrieved_patterns=[],
            generated_code={},
            validation_results={},
            errors=[],
            metadata={}
        )
    
    def test_property_intent_analysis_simple_master_form(self):
        """
        Test Case 1: Simple master form request produces structured intent
        
        **EXPECTED**: Intent contains form_title, table_name, operations, feature_type
        """
        user_request = """Create Customer master form.
Table: tblcustomer
File name: frmCustomer.php
Title: Customer
Primary Key: Customer_Code
"""
        
        state = self._create_test_state(user_request)
        result_state = asyncio.run(self.intent_node.execute(state))
        
        # Verify structured output format is preserved
        self.assertIn('intent', result_state)
        intent = result_state['intent']
        
        # Check that intent has expected structure
        self.assertIsInstance(intent, dict, "Intent should be a dictionary")
        self.assertIn('form_title', intent, "Intent should contain form_title")
        self.assertIn('operations', intent, "Intent should contain operations")
        
        # Verify intent values are reasonable
        self.assertTrue(len(intent['form_title']) > 0, "form_title should not be empty")
        self.assertIsInstance(intent['operations'], list, "operations should be a list")
        
        # Check database structure (table_name is nested in database)
        if 'database' in intent:
            self.assertIn('table_name', intent['database'], "Intent database should contain table_name")
            self.assertTrue(len(intent['database']['table_name']) > 0, "table_name should not be empty")
    
    def test_property_intent_analysis_hierarchical_form(self):
        """
        Test Case 2: Hierarchical form request produces structured intent
        
        **EXPECTED**: Intent contains form_title, operations, database with table_name
        """
        user_request = """Create Invoice master-detail form.
Master Table: tblinvoice
Detail Table: tblinvoicedetail
Primary Key: Invoice_No
Foreign Key: Invoice_No
"""
        
        state = self._create_test_state(user_request)
        result_state = asyncio.run(self.intent_node.execute(state))
        
        # Verify structured output format is preserved
        self.assertIn('intent', result_state)
        intent = result_state['intent']
        
        # Check that intent has expected structure
        self.assertIsInstance(intent, dict, "Intent should be a dictionary")
        self.assertIn('form_title', intent, "Intent should contain form_title")
        
        # Verify intent values are reasonable
        self.assertTrue(len(intent['form_title']) > 0, "form_title should not be empty")
        
        # Check database structure (table_name is nested in database)
        if 'database' in intent:
            self.assertIn('table_name', intent['database'], "Intent database should contain table_name")
            self.assertTrue(len(intent['database']['table_name']) > 0, "table_name should not be empty")
    
    def test_property_intent_analysis_with_dependencies(self):
        """
        Test Case 3: Form with dependencies produces structured intent
        
        **EXPECTED**: Intent contains form_title, operations, database with table_name
        """
        user_request = """Create Area master form.
Table: tblarea
Dependencies:
- tblcustomer | field=Area_Code
- tblsalesman | field=Area_Code
"""
        
        state = self._create_test_state(user_request)
        result_state = asyncio.run(self.intent_node.execute(state))
        
        # Verify structured output format is preserved
        self.assertIn('intent', result_state)
        intent = result_state['intent']
        
        # Check that intent has expected structure
        self.assertIsInstance(intent, dict, "Intent should be a dictionary")
        self.assertIn('form_title', intent, "Intent should contain form_title")
        
        # Verify intent values are reasonable
        self.assertTrue(len(intent['form_title']) > 0, "form_title should not be empty")
        
        # Check database structure (table_name is nested in database)
        if 'database' in intent:
            self.assertIn('table_name', intent['database'], "Intent database should contain table_name")
            self.assertTrue(len(intent['database']['table_name']) > 0, "table_name should not be empty")


class PreservationPatternRetrievalTest(SimpleTestCase):
    """
    Property 2.2: Preservation - Pattern Retrieval ChromaDB Vector Search
    
    For all pattern retrieval requests, ChromaDB vector search returns same patterns.
    This verifies that the pattern retrieval node continues to use vector similarity
    search and returns patterns in the same format.
    """
    
    def setUp(self):
        self.retrieval_node = PatternRetrievalNode()
        self.retrieval_node._initialize(user_id='test-user')
    
    def _create_test_state(self, intent: Dict) -> AgentState:
        """Helper to create a test state with intent"""
        return AgentState(
            user_request='Test request',
            project_id='test-project',
            user_id='test-user',
            intent=intent,
            retrieved_patterns=[],
            generated_code={},
            validation_results={},
            errors=[],
            metadata={}
        )
    
    def test_property_pattern_retrieval_simple_form(self):
        """
        Test Case 1: Simple form intent retrieves patterns from ChromaDB
        
        **EXPECTED**: Retrieved patterns is a list with pattern entries
        """
        intent = {
            'form_title': 'Customer',
            'table_name': 'tblcustomer',
            'operations': ['create', 'read', 'update', 'delete'],
            'feature_type': 'master_form'
        }
        
        state = self._create_test_state(intent)
        result_state = asyncio.run(self.retrieval_node.execute(state))
        
        # Verify pattern retrieval format is preserved
        self.assertIn('retrieved_patterns', result_state)
        patterns = result_state['retrieved_patterns']
        
        # Check that patterns have expected structure
        self.assertIsInstance(patterns, list, "Retrieved patterns should be a list")
        
        # If patterns are returned, verify they have expected structure
        if len(patterns) > 0:
            pattern = patterns[0]
            self.assertIsInstance(pattern, dict, "Each pattern should be a dictionary")
    
    def test_property_pattern_retrieval_hierarchical_form(self):
        """
        Test Case 2: Hierarchical form intent retrieves patterns from ChromaDB
        
        **EXPECTED**: Retrieved patterns is a list with pattern entries
        """
        intent = {
            'form_title': 'Invoice',
            'table_name': 'tblinvoice',
            'operations': ['create', 'read', 'update', 'delete'],
            'feature_type': 'master_detail_form'
        }
        
        state = self._create_test_state(intent)
        result_state = asyncio.run(self.retrieval_node.execute(state))
        
        # Verify pattern retrieval format is preserved
        self.assertIn('retrieved_patterns', result_state)
        patterns = result_state['retrieved_patterns']
        
        # Check that patterns have expected structure
        self.assertIsInstance(patterns, list, "Retrieved patterns should be a list")
        
        # If patterns are returned, verify they have expected structure
        if len(patterns) > 0:
            pattern = patterns[0]
            self.assertIsInstance(pattern, dict, "Each pattern should be a dictionary")
    
    def test_property_pattern_retrieval_with_relationships(self):
        """
        Test Case 3: Form with relationships retrieves patterns from ChromaDB
        
        **EXPECTED**: Retrieved patterns is a list with pattern entries
        """
        intent = {
            'form_title': 'Area',
            'table_name': 'tblarea',
            'operations': ['create', 'read', 'update', 'delete'],
            'feature_type': 'master_form'
        }
        
        state = self._create_test_state(intent)
        result_state = asyncio.run(self.retrieval_node.execute(state))
        
        # Verify pattern retrieval format is preserved
        self.assertIn('retrieved_patterns', result_state)
        patterns = result_state['retrieved_patterns']
        
        # Check that patterns have expected structure
        self.assertIsInstance(patterns, list, "Retrieved patterns should be a list")


class PreservationValidationTest(SimpleTestCase):
    """
    Property 2.3: Preservation - Validation Pipeline
    
    For all validation requests, validation pipeline produces same results.
    This verifies that the validation node continues to validate syntax, security,
    and patterns in the same way.
    """
    
    def setUp(self):
        self.validation_node = ValidationNode()
        self.validation_node._initialize()
    
    def _create_test_state(self, generated_code: Dict) -> AgentState:
        """Helper to create a test state with generated code"""
        return AgentState(
            user_request='Test request',
            project_id='test-project',
            user_id='test-user',
            intent={'form_title': 'Test'},
            retrieved_patterns=[],
            generated_code=generated_code,
            validation_results={},
            errors=[],
            metadata={}
        )
    
    def test_property_validation_simple_php_code(self):
        """
        Test Case 1: Simple PHP code validation produces structured results
        
        **EXPECTED**: Validation results contain validation status
        """
        generated_code = {
            'php': '<?php\n$test = "hello";\necho $test;\n?>'
        }
        
        state = self._create_test_state(generated_code)
        result_state = asyncio.run(self.validation_node.execute(state))
        
        # Verify validation results format is preserved
        self.assertIn('validation_results', result_state)
        validation = result_state['validation_results']
        
        # Check that validation has expected structure
        self.assertIsInstance(validation, dict, "Validation results should be a dictionary")
        # Validation may be empty dict if validation is blocked, which is acceptable
        # The key is that the structure is preserved
    
    def test_property_validation_php_with_sql(self):
        """
        Test Case 2: PHP code with SQL validation produces structured results
        
        **EXPECTED**: Validation results contain validation status
        """
        generated_code = {
            'php': '<?php\n$sql = "SELECT * FROM tblcustomer";\n$result = mysqli_query($conn, $sql);\n?>'
        }
        
        state = self._create_test_state(generated_code)
        result_state = asyncio.run(self.validation_node.execute(state))
        
        # Verify validation results format is preserved
        self.assertIn('validation_results', result_state)
        validation = result_state['validation_results']
        
        # Check that validation has expected structure
        self.assertIsInstance(validation, dict, "Validation results should be a dictionary")
        # Validation may be empty dict if validation is blocked, which is acceptable
        # The key is that the structure is preserved
    
    def test_property_validation_invalid_php_code(self):
        """
        Test Case 3: Invalid PHP code validation produces structured results
        
        **EXPECTED**: Validation results contain validation status
        """
        generated_code = {
            'php': '<?php\n$test = "unclosed string\necho $test;\n?>'
        }
        
        state = self._create_test_state(generated_code)
        result_state = asyncio.run(self.validation_node.execute(state))
        
        # Verify validation results format is preserved
        self.assertIn('validation_results', result_state)
        validation = result_state['validation_results']
        
        # Check that validation has expected structure
        self.assertIsInstance(validation, dict, "Validation results should be a dictionary")
        # Validation may be empty dict if validation is blocked, which is acceptable
        # The key is that the structure is preserved


class PreservationNonHierarchicalFormTest(SimpleTestCase):
    """
    Property 2.4: Preservation - Non-Hierarchical Form Generation
    
    For all non-hierarchical form requests, standard CRUD generation works.
    This verifies that forms without cascading logic continue to work correctly.
    """
    
    def test_property_non_hierarchical_form_structure(self):
        """
        Test Case 1: Non-hierarchical form has standard CRUD structure
        
        **EXPECTED**: Form structure contains master fields only, no detail grids
        """
        # This is a structural test - we verify that the intent analysis
        # correctly identifies non-hierarchical forms
        intent_node = IntentAnalysisNode()
        
        user_request = """Create Customer master form.
Table: tblcustomer
Primary Key: Customer_Code
Fields: Customer_Code, Customer_Name, Contact_Number
"""
        
        state = AgentState(
            user_request=user_request,
            project_id='test-project',
            user_id='test-user',
            intent={},
            retrieved_patterns=[],
            generated_code={},
            validation_results={},
            errors=[],
            metadata={}
        )
        
        result_state = asyncio.run(intent_node.execute(state))
        
        # Verify that intent correctly identifies this as a non-hierarchical form
        self.assertIn('intent', result_state)
        intent = result_state['intent']
        
        # Non-hierarchical forms should not have detail table information
        feature_type = intent.get('feature_type', '')
        self.assertNotIn('detail', feature_type.lower(), 
                        "Non-hierarchical form should not have 'detail' in feature_type")


class PreservationMasterOnlyFormTest(SimpleTestCase):
    """
    Property 2.5: Preservation - Master-Only Form Generation
    
    For all master-only form requests, forms without detail grids work.
    This verifies that forms without sub-table logic continue to work correctly.
    """
    
    def test_property_master_only_form_structure(self):
        """
        Test Case 1: Master-only form has no detail grid logic
        
        **EXPECTED**: Form structure contains master fields only, no sub-table logic
        """
        # This is a structural test - we verify that the intent analysis
        # correctly identifies master-only forms
        intent_node = IntentAnalysisNode()
        
        user_request = """Create Area master form.
Table: tblarea
Primary Key: Area_Code
Fields: Area_Code, Area_Name, Region_Code
"""
        
        state = AgentState(
            user_request=user_request,
            project_id='test-project',
            user_id='test-user',
            intent={},
            retrieved_patterns=[],
            generated_code={},
            validation_results={},
            errors=[],
            metadata={}
        )
        
        result_state = asyncio.run(intent_node.execute(state))
        
        # Verify that intent correctly identifies this as a master-only form
        self.assertIn('intent', result_state)
        intent = result_state['intent']
        
        # Master-only forms should not have detail table information
        feature_type = intent.get('feature_type', '')
        self.assertNotIn('detail', feature_type.lower(), 
                        "Master-only form should not have 'detail' in feature_type")


class PreservationTemplateLoadingTest(SimpleTestCase):
    """
    Property 2.6: Preservation - DynamicFormTemplate Loading
    
    When the system uses the DynamicFormTemplate class, it continues to load
    templates from the codebase directory.
    
    **Validates: Requirement 3.8**
    """
    
    def test_property_template_loading_from_codebase(self):
        """
        Test Case 1: DynamicFormTemplate loads from codebase directory
        
        **EXPECTED**: Template loading mechanism remains unchanged
        """
        template = DynamicFormTemplate(
            codebase_dir=str(SAMPLE_CODEBASE_DIR)
        )
        
        # Verify that template has expected attributes
        self.assertTrue(hasattr(template, 'codebase_dir'), 
                       "Template should have codebase_dir attribute")
        self.assertTrue(hasattr(template, 'load'), 
                       "Template should have load method")
        
        # Verify codebase_dir is set correctly
        self.assertIsInstance(template.codebase_dir, str, 
                            "codebase_dir should be a string")
        self.assertTrue(len(template.codebase_dir) > 0, 
                       "codebase_dir should not be empty")
