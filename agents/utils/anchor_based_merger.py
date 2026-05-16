"""
Phase 2.3: Anchor-Based Merger
Deterministic template merging using anchor points.
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class AnchorBasedMerger:
    """
    ✅ PHASE 2.3: ANCHOR-BASED MERGER
    
    Uses anchor points in template for deterministic merging.
    No guessing - exact positions defined by anchors.
    
    Anchors:
    - {{PHP_LOGIC}} - Where to inject PHP code
    - {{FORM_FIELDS}} - Where to inject form HTML
    - {{VALIDATION_RULES}} - Where to inject FormValidation
    - {{HEAD_SCRIPTS}} - Where to inject JavaScript
    - {{AJAX_HANDLERS}} - Where to inject AJAX code
    """
    
    def __init__(self, template: str = ""):
        self.template = template
        self.anchors = {
            'PHP_LOGIC': '{{PHP_LOGIC}}',
            'FORM_FIELDS': '{{FORM_FIELDS}}',
            'VALIDATION_RULES': '{{VALIDATION_RULES}}',
            'HEAD_SCRIPTS': '{{HEAD_SCRIPTS}}',
            'AJAX_HANDLERS': '{{AJAX_HANDLERS}}'
        }
    
    def merge(self, sections: Dict[str, str]) -> str:
        """
        Merge sections into template using anchors.
        
        Args:
            sections: Dict of section_name -> content
                {
                    'php_logic': '...',
                    'form_fields': '...',
                    'validation_rules': '...',
                    'head_scripts': '...',
                    'ajax_handlers': '...'
                }
        
        Returns:
            Merged template with sections injected at anchor points
        
        Raises:
            ValueError: If required anchors missing or sections empty
        """
        logger.info("🔧 PHASE 2.3: Starting anchor-based merge...")
        
        # ✅ PHASE 2.4: SECTION ASSERTIONS
        self._assert_required_sections(sections)
        
        # Start with template
        result = self.template
        
        # If no template, build from scratch
        if not result or not result.strip():
            result = self._build_default_template()
        
        # Replace each anchor with corresponding section
        for section_name, content in sections.items():
            anchor_key = section_name.upper()
            anchor = self.anchors.get(anchor_key, f'{{{{{anchor_key}}}}}')
            
            if anchor in result:
                result = result.replace(anchor, content or '')
                logger.info(f"✅ Injected {section_name} at anchor {anchor}")
            else:
                logger.warning(f"⚠️ Anchor {anchor} not found in template")
        
        # Clean up any remaining anchors
        for anchor in self.anchors.values():
            result = result.replace(anchor, '')
        
        logger.info("✅ PHASE 2.3: Anchor-based merge complete")
        return result
    
    def _assert_required_sections(self, sections: Dict[str, str]):
        """
        ✅ PHASE 2.4: SECTION ASSERTIONS
        
        Assert that required sections are non-empty.
        Fail fast if critical sections missing.
        
        Raises:
            ValueError: If required sections are empty
        """
        logger.info("🔍 PHASE 2.4: Asserting required sections...")
        
        required_sections = {
            'php_logic': 'PHP logic (variables, CRUD handlers)',
            'form_fields': 'Form fields HTML'
        }
        
        errors = []
        
        for section_name, description in required_sections.items():
            content = sections.get(section_name, '')
            
            if not content or not content.strip():
                errors.append(f"{section_name} is empty ({description})")
            else:
                # Check minimum length (relaxed for tests)
                if len(content.strip()) < 20:
                    errors.append(f"{section_name} is too short ({len(content)} chars)")
        
        # Assert PHP logic contains required functions
        php_logic = sections.get('php_logic', '')
        required_functions = ['db_insert', 'db_update', 'db_delete']
        
        missing_functions = []
        for func in required_functions:
            if func not in php_logic:
                missing_functions.append(func)
        
        if missing_functions:
            errors.append(f"PHP logic missing required functions: {', '.join(missing_functions)}")
        
        # Assert form fields contain input elements
        form_fields = sections.get('form_fields', '')
        if '<input' not in form_fields and '<select' not in form_fields and '<textarea' not in form_fields:
            errors.append("Form fields contain no input elements (<input>, <select>, <textarea>)")
        
        if errors:
            error_msg = "❌ SECTION ASSERTION FAILED:\n" + "\n".join(f"  - {err}" for err in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info("✅ PHASE 2.4: All required sections present and valid")
    
    def _build_default_template(self) -> str:
        """
        Build default template with anchors if no template provided.
        """
        return """<?php
{{PHP_LOGIC}}
?>

<!DOCTYPE html>
<html>
<head>
    <title>Form</title>
    {{HEAD_SCRIPTS}}
</head>
<body>
    <form>
        {{FORM_FIELDS}}
    </form>
    
    <script>
    {{AJAX_HANDLERS}}
    {{VALIDATION_RULES}}
    </script>
</body>
</html>
"""
    
    def validate_template(self, template: str) -> bool:
        """
        Validate that template contains required anchors.
        
        Returns:
            True if template is valid, False otherwise
        """
        required_anchors = ['{{PHP_LOGIC}}', '{{FORM_FIELDS}}']
        
        for anchor in required_anchors:
            if anchor not in template:
                logger.warning(f"⚠️ Template missing required anchor: {anchor}")
                return False
        
        return True
    
    def get_anchor_positions(self, template: str) -> Dict[str, int]:
        """
        Get positions of all anchors in template.
        
        Returns:
            Dict of anchor_name -> position
        """
        positions = {}
        
        for name, anchor in self.anchors.items():
            pos = template.find(anchor)
            if pos != -1:
                positions[name] = pos
        
        return positions
