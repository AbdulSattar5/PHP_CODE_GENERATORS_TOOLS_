"""
Phase 2.2: ContractParser
Extracts and parses contracts from user requests and company examples.
Replaces heuristic extraction with deterministic parsing.
"""

import re
import os
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ContractParser:
    """
    ✅ PHASE 2.2: CONTRACT PARSER
    
    Responsibilities:
    1. Parse user request into structured contract using RequestSchemaParser
    2. Extract canonical metadata from company examples
    3. Extract field definitions, relationships, dependencies
    4. Detect patterns (hierarchical, cascading, grid)
    5. Build validation contract
    
    This class consolidates all parsing logic from InlinePHPGenerator.
    """
    
    def __init__(self):
        self.last_parsed_contract = {}
    
    def parse_user_request(self, user_request: str) -> Dict:
        """
        Parse user request into structured contract.
        Uses RequestSchemaParser for deterministic parsing.
        
        Returns:
            {
                'table': str,
                'filename': str,
                'title': str,
                'case_type': str,
                'primary_key': str,
                'fields': List[Dict],
                'relationships': List[Dict],
                'dependencies': List[Dict],
                'features': List[str],
                'parsing_method': 'schema_parser' | 'heuristic'
            }
        """
        from agents.utils.request_parser import RequestSchemaParser
        
        try:
            parser = RequestSchemaParser()
            schema = parser.parse(user_request)
            schema['parsing_method'] = 'schema_parser'
            
            logger.info("✅ ContractParser: Used RequestSchemaParser")
            logger.info(f"   Fields: {len(schema.get('fields', []))}")
            logger.info(f"   Relationships: {len(schema.get('relationships', []))}")
            logger.info(f"   Dependencies: {len(schema.get('dependencies', []))}")
            
            self.last_parsed_contract = schema
            return schema
            
        except Exception as e:
            logger.warning(f"⚠️ ContractParser: RequestSchemaParser failed: {e}")
            logger.warning("   Falling back to heuristic extraction")
            
            # Fallback to heuristic
            heuristic_contract = self._heuristic_parse(user_request)
            heuristic_contract['parsing_method'] = 'heuristic'
            
            self.last_parsed_contract = heuristic_contract
            return heuristic_contract
    
    def _heuristic_parse(self, user_request: str) -> Dict:
        """
        Fallback heuristic parsing when structured parsing fails.
        Extracts basic metadata from unstructured text.
        """
        contract = {
            'table': '',
            'filename': '',
            'title': '',
            'case_type': '',
            'primary_key': 'Code',
            'fields': [],
            'relationships': [],
            'dependencies': [],
            'features': []
        }
        
        # Extract table name
        table_match = re.search(r'(?i)\btable\s*:\s*([a-z][a-z0-9_]+)', user_request)
        if table_match:
            contract['table'] = table_match.group(1).strip()
        
        # Extract filename
        file_match = re.search(r'(?i)(?:file\s*name|filename)\s*:\s*([a-z0-9_]+\.php)', user_request)
        if file_match:
            contract['filename'] = file_match.group(1).strip()
        
        # Extract title
        title_match = re.search(r'(?i)\btitle\s*:\s*([A-Za-z][A-Za-z0-9_ \-]+)', user_request)
        if title_match:
            contract['title'] = title_match.group(1).strip()
        
        # Detect features from keywords
        lowered = user_request.lower()
        if 'dropdown' in lowered or 'cascading' in lowered:
            contract['features'].append('dropdown')
        if 'validation' in lowered:
            contract['features'].append('validation')
        if 'keyboard' in lowered:
            contract['features'].append('keyboard')
        if 'grid' in lowered or 'detail' in lowered:
            contract['features'].append('grid')
        
        return contract
    
    def extract_canonical_metadata(
        self, 
        company_example: str, 
        example_file_path: str = ""
    ) -> Dict:
        """
        Extract canonical form metadata from company example.
        Looks for $form2, $table, $title, CaseType in PHP code.
        
        Returns:
            {
                'file_name': str,
                'file_path': str,
                'feature_name': str,
                'table_name': str,
                'title': str,
                'case_type': str
            }
        """
        source_text = company_example or ''
        
        # Read from file if path provided
        if example_file_path and os.path.exists(example_file_path):
            try:
                with open(example_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    source_text = f.read()
            except Exception as e:
                logger.warning(f"Could not read example file: {e}")
        
        metadata = {
            'file_name': '',
            'file_path': example_file_path or '',
            'feature_name': '',
            'table_name': '',
            'title': '',
            'case_type': '',
        }
        
        # Extract $form2
        form2_match = re.search(r'\$form2\s*=\s*["\']([^"\']+\.php)["\']', source_text, re.IGNORECASE)
        if form2_match:
            metadata['file_name'] = os.path.basename(form2_match.group(1).strip())
        
        # Extract $table
        table_match = re.search(r'\$table\s*=\s*["\']([^"\']+)["\']', source_text, re.IGNORECASE)
        if table_match:
            metadata['table_name'] = table_match.group(1).strip()
        
        # Extract $title
        title_match = re.search(r'\$title\s*=\s*["\']([^"\']+)["\']', source_text, re.IGNORECASE)
        if title_match:
            metadata['title'] = title_match.group(1).strip()
        
        # Extract CaseType
        case_type_match = re.search(r'CaseType=([^"\']+)', source_text, re.IGNORECASE)
        if case_type_match:
            metadata['case_type'] = case_type_match.group(1).strip()
        
        # Fallback: use file path
        if not metadata['file_name'] and example_file_path:
            metadata['file_name'] = os.path.basename(example_file_path)
        
        # Extract feature name from filename
        if metadata['file_name'].lower().startswith('frm') and metadata['file_name'].lower().endswith('.php'):
            metadata['feature_name'] = metadata['file_name'][3:-4]
        
        # Fill in missing values
        if not metadata['feature_name'] and metadata['title']:
            metadata['feature_name'] = metadata['title'].replace(' ', '_')
        
        if not metadata['title'] and metadata['feature_name']:
            metadata['title'] = metadata['feature_name'].replace('_', ' ')
        
        if not metadata['case_type'] and metadata['title']:
            metadata['case_type'] = metadata['title']
        
        if not metadata['table_name'] and metadata['feature_name']:
            metadata['table_name'] = f"tbl{metadata['feature_name'].replace('_', '').lower()}"
        
        return metadata
    
    def merge_contracts(
        self, 
        user_contract: Dict, 
        company_metadata: Dict
    ) -> Dict:
        """
        Merge user request contract with company example metadata.
        User contract takes precedence for explicit values.
        
        ✅ FIX PRIORITY 2: Ensure ALL parsed fields are preserved through merge
        
        Returns merged contract with all metadata.
        """
        merged = company_metadata.copy()
        
        # User contract overrides company metadata
        if user_contract.get('table'):
            merged['table_name'] = user_contract['table']
        if user_contract.get('filename'):
            merged['file_name'] = user_contract['filename']
        if user_contract.get('title'):
            merged['title'] = user_contract['title']
        if user_contract.get('case_type'):
            merged['case_type'] = user_contract['case_type']
        
        # Add user contract fields
        merged['primary_key'] = user_contract.get('primary_key', 'Code')
        merged['fields'] = user_contract.get('fields', [])
        merged['detail_table'] = user_contract.get('detail_table', '')
        merged['relationships'] = user_contract.get('relationships', [])
        merged['dependencies'] = user_contract.get('dependencies', [])
        merged['features'] = user_contract.get('features', [])
        merged['parsing_method'] = user_contract.get('parsing_method', 'heuristic')

        master_fields = []
        detail_fields = []
        for field in merged.get('fields', []) or []:
            if not isinstance(field, dict):
                continue
            section = str(field.get('section') or 'master').strip().lower()
            if section in {'detail', 'grid', 'child', 'line'}:
                detail_fields.append(field)
            else:
                master_fields.append(field)
        merged['master_fields'] = master_fields
        merged['detail_fields'] = detail_fields
        
        # ✅ FIX PRIORITY 2: Log field preservation
        field_count = len(merged.get('fields', []))
        logger.info(f"✅ Contract merge complete:")
        logger.info(f"   - Table: {merged.get('table_name')}")
        logger.info(f"   - File: {merged.get('file_name')}")
        logger.info(f"   - Fields: {field_count} preserved")
        if field_count > 0:
            field_names = [f.get('name') for f in merged.get('fields', [])]
            logger.info(f"   - Field names: {', '.join(field_names[:10])}")  # Show first 10
        
        return merged
    
    def detect_hierarchical_pattern(
        self, 
        company_example: str, 
        user_request: str
    ) -> Dict:
        """
        Detect hierarchical code pattern (e.g., Area -> SubArea).
        
        Returns:
            {
                'is_hierarchical': bool,
                'parent_field': str,
                'parent_request_param': str,
                'code_length': int,
                'separator': str
            }
        """
        pattern = {
            'is_hierarchical': False,
            'parent_field': '',
            'parent_request_param': '',
            'code_length': 4,
            'separator': '-'
        }
        
        # Check for hierarchical keywords
        combined_text = (company_example + '\n' + user_request).lower()
        
        if 'hierarchical' in combined_text or 'parent' in combined_text:
            pattern['is_hierarchical'] = True
            
            # Try to extract parent field
            parent_match = re.search(r'parent[_\s]*field\s*:\s*([A-Za-z_][A-Za-z0-9_]*)', user_request, re.IGNORECASE)
            if parent_match:
                pattern['parent_field'] = parent_match.group(1).strip()
            
            # Try to extract separator
            sep_match = re.search(r'separator\s*:\s*([^\s\n]+)', user_request, re.IGNORECASE)
            if sep_match:
                pattern['separator'] = sep_match.group(1).strip()
        
        return pattern
    
    def detect_cascading_dropdown(
        self, 
        company_example: str, 
        user_request: str
    ) -> Dict:
        """
        Detect cascading dropdown logic.
        
        Returns:
            {
                'has_cascading': bool,
                'parent_dropdown': str,
                'child_dropdown': str
            }
        """
        pattern = {
            'has_cascading': False,
            'parent_dropdown': '',
            'child_dropdown': ''
        }
        
        combined_text = (company_example + '\n' + user_request).lower()
        
        if 'cascading' in combined_text or 'cascade' in combined_text:
            pattern['has_cascading'] = True
            
            # Try to extract dropdown names from relationships
            # This would be enhanced with actual relationship parsing
        
        return pattern
    
    def detect_grid_pattern(
        self, 
        company_example: str, 
        user_request: str
    ) -> Dict:
        """
        Detect detail grid pattern.
        
        Returns:
            {
                'has_grid': bool,
                'sub_table': str,
                'grid_fields': List[str],
                'txtcount_var': str
            }
        """
        pattern = {
            'has_grid': False,
            'sub_table': '',
            'grid_fields': [],
            'txtcount_var': 'TXTCOUNT'
        }
        
        combined_text = (company_example + '\n' + user_request).lower()
        
        if 'grid' in combined_text or 'detail' in combined_text:
            pattern['has_grid'] = True
            
            # Try to extract sub-table name
            sub_table_match = re.search(r'(?:sub[_\s]*table|detail[_\s]*table)\s*:\s*([a-z][a-z0-9_]+)', user_request, re.IGNORECASE)
            if sub_table_match:
                pattern['sub_table'] = sub_table_match.group(1).strip()
        
        return pattern
    
    def get_last_contract(self) -> Dict:
        """Get the last parsed contract"""
        return self.last_parsed_contract
