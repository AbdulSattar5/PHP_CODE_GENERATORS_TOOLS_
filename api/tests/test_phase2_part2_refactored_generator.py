"""
Phase 2 Part 2.2: Refactored Generator Integration Test
Tests the InlinePHPGeneratorRefactored with 4 modular classes
"""

import pytest
from agents.graph.inline_php_generator_refactored import InlinePHPGeneratorRefactored


class TestRefactoredGenerator:
    """Test InlinePHPGeneratorRefactored functionality"""
    
    def test_initialization(self):
        """Test that refactored generator initializes with 4 classes"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        # Check that all 4 classes are initialized
        assert hasattr(generator, 'contract_parser')
        assert hasattr(generator, 'generation_planner')
        assert hasattr(generator, 'code_assembler')
        assert hasattr(generator, 'enterprise_validator')
        
        assert generator.contract_parser is not None
        assert generator.generation_planner is not None
        assert generator.code_assembler is not None
        assert generator.enterprise_validator is not None
    
    def test_has_modular_generation_method(self):
        """Test that refactored generator has new modular method"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        # Check that new method exists
        assert hasattr(generator, 'generate_with_modular_architecture')
        assert callable(generator.generate_with_modular_architecture)
    
    def test_backward_compatibility(self):
        """Test that refactored generator maintains backward compatibility"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        # Check that old methods still exist
        assert hasattr(generator, 'generate_inline_php_file')
        assert hasattr(generator, '_detect_user_requirements')
        assert hasattr(generator, '_get_llm_client')
    
    def test_modular_generation_method_exists(self):
        """Test that modular generation method exists (async test skipped)"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        # Just verify the method exists and is callable
        assert hasattr(generator, 'generate_with_modular_architecture')
        assert callable(generator.generate_with_modular_architecture)
        
        # Verify it's an async method
        import inspect
        assert inspect.iscoroutinefunction(generator.generate_with_modular_architecture)


class TestRefactoredGeneratorIntegration:
    """Test integration between refactored generator and 4 classes"""
    
    def test_contract_parser_integration(self):
        """Test that contract parser is properly integrated"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        user_request = """
        Table: tbltest
        File name: frmTest.php
        Title: Test
        
        Fields:
        - Code | DB: VARCHAR(20) | Input: textbox
        """
        
        # Test contract parsing
        contract = generator.contract_parser.parse_user_request(user_request)
        
        assert contract['table'] == 'tbltest'
        assert contract['filename'] == 'frmTest.php'
        assert contract['title'] == 'Test'
    
    def test_generation_planner_integration(self):
        """Test that generation planner is properly integrated"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        contract = {
            'table_name': 'tbltest',
            'file_name': 'frmTest.php',
            'title': 'Test',
            'primary_key': 'Code',
            'fields': [{'name': 'Code'}],
            'relationships': [],
            'dependencies': [],
            'features': []
        }
        
        user_requirements = {
            'wants_formvalidation': True,
            'wants_keyboard': False,
            'wants_grid': False
        }
        
        # Test generation planning
        plan = generator.generation_planner.plan_generation(
            contract=contract,
            company_examples="",
            analyzed_patterns={},
            user_requirements=user_requirements
        )
        
        assert 'strategy' in plan
        assert 'sections_to_generate' in plan
        assert 'prompt' in plan
        assert 'validation_contract' in plan
    
    def test_code_assembler_integration(self):
        """Test that code assembler is properly integrated"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        generated_code = """
        <?php
        $form = "frmTest.php";
        $table = "tbltest";
        ?>
        <input type="text" name="Code" />
        """
        
        contract = {
            'table_name': 'tbltest',
            'file_name': 'frmTest.php',
            'title': 'Test',
            'dependencies': []
        }
        
        # Test code assembly
        assembled = generator.code_assembler.assemble(
            generated_code=generated_code,
            contract=contract,
            fixed_parts={}
        )
        
        assert assembled is not None
        assert len(assembled) > 0
    
    def test_enterprise_validator_integration(self):
        """Test that enterprise validator is properly integrated"""
        llm_config = {
            'model': 'gpt-4o-mini',
            'api_key': 'test-key'
        }
        
        generator = InlinePHPGeneratorRefactored(llm_config)
        
        code = """
        <?php
        if ($_REQUEST['Action'] == 'Save') {
            db_insert($table, $data);
        }
        ?>
        """
        
        validation_contract = {
            'required_functions': ['db_insert'],
            'required_handlers': ['Save'],
            'required_ajax': [],
            'required_fields': [],
            'required_dependencies': []
        }
        
        # Test validation
        is_valid, errors, scores = generator.enterprise_validator.validate(
            generated_code=code,
            validation_contract=validation_contract
        )
        
        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)
        assert isinstance(scores, dict)
