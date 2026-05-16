"""
PHASE 2.2: Refactored InlinePHPGenerator
Uses the 4 new modular classes for cleaner architecture.
"""

import logging
from typing import Dict, List
from agents.graph.inline_php_generator import InlinePHPGenerator
from agents.graph.contract_parser import ContractParser
from agents.graph.generation_planner import GenerationPlanner
from agents.graph.code_assembler import CodeAssembler
from agents.graph.enterprise_validator import EnterpriseValidator

logger = logging.getLogger(__name__)


class InlinePHPGeneratorRefactored(InlinePHPGenerator):
    """
    ✅ PHASE 2.2: REFACTORED GENERATOR
    
    Extends InlinePHPGenerator to use 4 modular classes:
    1. ContractParser - Parse user request into contract
    2. GenerationPlanner - Plan generation strategy
    3. CodeAssembler - Assemble final code
    4. EnterpriseValidator - Validate generated code
    
    This provides cleaner separation of concerns while maintaining
    backward compatibility with existing code.
    """
    
    def __init__(self, llm_config: Dict, codebase_dir: str = None):
        # Initialize parent class
        super().__init__(llm_config, codebase_dir)
        
        # ✅ PHASE 2.2: Initialize new modular classes
        self.contract_parser = ContractParser()
        self.generation_planner = GenerationPlanner()
        self.code_assembler = CodeAssembler(self._template)
        self.enterprise_validator = EnterpriseValidator()
        
        logger.info("✅ InlinePHPGeneratorRefactored initialized with 4 modular classes")
    
    async def generate_with_modular_architecture(
        self,
        intent: Dict,
        sql_schema: str,
        company_examples: str,
        analyzed_patterns: Dict,
        standards: str,
        user_request: str = "",
        validation_errors: List = None,
        max_retries: int = 2
    ) -> str:
        """
        ✅ PHASE 2.2: MODULAR GENERATION FLOW
        
        Uses 4 classes for clean separation:
        1. ContractParser → Parse user request
        2. GenerationPlanner → Plan generation
        3. LLM → Generate code
        4. CodeAssembler → Assemble final file
        5. EnterpriseValidator → Validate output
        
        Args:
            intent: Intent analysis from IntentAnalysisNode
            sql_schema: Database schema
            company_examples: Company code examples
            analyzed_patterns: Analyzed patterns from codebase
            standards: Company coding standards
            user_request: Raw user request text
            validation_errors: Previous validation errors (for retry)
            max_retries: Maximum retry attempts
        
        Returns:
            Complete assembled PHP file
        """
        logger.info("=" * 80)
        logger.info("🚀 PHASE 2.2: Starting modular generation flow")
        logger.info("=" * 80)
        
        # ============================================================
        # STEP 1: PARSE CONTRACT
        # ============================================================
        logger.info("📋 STEP 1: Parsing user request into contract...")
        
        try:
            user_contract = self.contract_parser.parse_user_request(user_request)
            
            # Extract company metadata
            company_metadata = self.contract_parser.extract_canonical_metadata(
                company_examples,
                example_file_path=""
            )
            
            # Merge contracts
            contract = self.contract_parser.merge_contracts(user_contract, company_metadata)
            
            logger.info(f"✅ Contract parsed:")
            logger.info(f"   Table: {contract.get('table_name')}")
            logger.info(f"   File: {contract.get('file_name')}")
            logger.info(f"   Fields: {len(contract.get('fields', []))}")
            logger.info(f"   Method: {contract.get('parsing_method')}")
            
        except Exception as e:
            logger.error(f"❌ Contract parsing failed: {e}")
            # Fallback to old method
            return await self.generate_inline_php_file(
                intent=intent,
                sql_schema=sql_schema,
                company_examples=company_examples,
                analyzed_patterns=analyzed_patterns,
                standards=standards,
                user_request=user_request,
                validation_errors=validation_errors,
                max_retries=max_retries
            )
        
        # ============================================================
        # STEP 2: PLAN GENERATION
        # ============================================================
        logger.info("📝 STEP 2: Planning generation strategy...")
        
        # Detect user requirements
        user_requirements = self._detect_user_requirements(user_request)
        
        try:
            plan = self.generation_planner.plan_generation(
                contract=contract,
                company_examples=company_examples,
                analyzed_patterns=analyzed_patterns,
                user_requirements=user_requirements
            )
            
            logger.info(f"✅ Generation plan created:")
            logger.info(f"   Strategy: {plan['strategy']}")
            logger.info(f"   Sections: {len(plan['sections_to_generate'])}")
            logger.info(f"   Prompt length: {len(plan['prompt'])} chars")
            
        except Exception as e:
            logger.error(f"❌ Generation planning failed: {e}")
            # Fallback to old method
            return await self.generate_inline_php_file(
                intent=intent,
                sql_schema=sql_schema,
                company_examples=company_examples,
                analyzed_patterns=analyzed_patterns,
                standards=standards,
                user_request=user_request,
                validation_errors=validation_errors,
                max_retries=max_retries
            )
        
        # ============================================================
        # STEP 3: GENERATE CODE WITH LLM
        # ============================================================
        logger.info("🤖 STEP 3: Generating code with LLM...")
        
        retry_count = 0
        generated_code = None
        
        while retry_count <= max_retries:
            try:
                # Build prompt (use retry prompt if errors exist)
                if validation_errors and retry_count > 0:
                    prompt = self.generation_planner.build_retry_prompt(
                        original_prompt=plan['prompt'],
                        validation_errors=validation_errors,
                        previous_code=generated_code or ""
                    )
                else:
                    prompt = plan['prompt']
                
                # Call LLM
                messages = self._build_generation_messages(prompt, user_request)
                model_name = self._model_for_attempt(retry_count)
                llm_client = self._get_llm_client(model_name)
                
                logger.info(f"   Calling LLM (attempt {retry_count + 1}/{max_retries + 1}, model: {model_name})...")
                
                response = await llm_client.ainvoke(messages)
                generated_code = response.content
                
                logger.info(f"✅ LLM generated {len(generated_code)} chars")
                break
                
            except Exception as e:
                logger.error(f"❌ LLM generation failed (attempt {retry_count + 1}): {e}")
                retry_count += 1
                
                if retry_count > max_retries:
                    logger.error("❌ Max retries reached, falling back to old method")
                    return await self.generate_inline_php_file(
                        intent=intent,
                        sql_schema=sql_schema,
                        company_examples=company_examples,
                        analyzed_patterns=analyzed_patterns,
                        standards=standards,
                        user_request=user_request,
                        validation_errors=validation_errors,
                        max_retries=max_retries
                    )
        
        # ============================================================
        # STEP 4: ASSEMBLE CODE
        # ============================================================
        logger.info("🔧 STEP 4: Assembling final PHP file...")
        
        try:
            assembled_code = self.code_assembler.assemble(
                generated_code=generated_code,
                contract=contract,
                fixed_parts={}
            )
            
            logger.info(f"✅ Code assembled: {len(assembled_code)} chars")
            
        except Exception as e:
            logger.error(f"❌ Code assembly failed: {e}")
            # Return raw generated code as fallback
            assembled_code = generated_code
        
        # ============================================================
        # STEP 5: VALIDATE
        # ============================================================
        logger.info("🔍 STEP 5: Validating generated code...")
        
        try:
            is_valid, errors, scores = self.enterprise_validator.validate(
                generated_code=assembled_code,
                validation_contract=plan['validation_contract']
            )
            
            logger.info(f"{'✅' if is_valid else '❌'} Validation result:")
            logger.info(f"   Valid: {is_valid}")
            logger.info(f"   Errors: {len(errors)}")
            logger.info(f"   Overall score: {scores.get('overall', 0)}%")
            
            # Store validation result
            self.last_validation_result = {
                'is_valid': is_valid,
                'errors': errors,
                'scores': scores
            }
            
            # If validation failed and retries available, retry
            if not is_valid and retry_count < max_retries:
                logger.warning(f"⚠️ Validation failed, retrying with error feedback...")
                return await self.generate_with_modular_architecture(
                    intent=intent,
                    sql_schema=sql_schema,
                    company_examples=company_examples,
                    analyzed_patterns=analyzed_patterns,
                    standards=standards,
                    user_request=user_request,
                    validation_errors=errors,
                    max_retries=max_retries
                )
            
        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            # Continue with assembled code even if validation fails
        
        # ============================================================
        # DONE
        # ============================================================
        logger.info("=" * 80)
        logger.info("✅ PHASE 2.2: Modular generation complete")
        logger.info("=" * 80)
        
        return assembled_code
