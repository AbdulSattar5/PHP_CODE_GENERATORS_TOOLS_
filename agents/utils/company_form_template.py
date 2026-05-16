"""
Company Form Template System
Extracts FIXED parts from company forms and provides template for generation.
LLM only generates VARIABLE parts (fields, save/update logic, delete checks).
Fixed parts (scripts, CSS, HTML wrapper, FormValidation boilerplate) are injected from template.
"""

import os
import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CompanyFormTemplate:
    """
    Extracts and manages FIXED parts from company forms.
    
    FIXED parts (same across ALL forms):
    - HTML head structure (DOCTYPE, meta tags)
    - CSS links (bootstrap, plugins, fonts)
    - JavaScript library includes
    - Footer scripts (30+ script tags)
    - HTML wrapper structure
    - FormValidation boilerplate
    - Keyboard navigation boilerplate
    
    VARIABLE parts (change per form):
    - PHP variables (form, form2, table, title)
    - AJAX handlers
    - Delete logic
    - Save/Update logic
    - Form fields
    - FormValidation field definitions
    """
    
    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
        self._css_links: List[str] = []
        self._footer_scripts: List[str] = []
        self._html_head: str = ""
        self._body_start: str = ""
        self._body_end: str = ""
        self._loaded = False
    
    def load(self):
        """Load template from company codebase forms."""
        if self._loaded:
            return
        
        frm_files = []
        for root, dirs, files in os.walk(self.codebase_dir):
            for f in files:
                if f.startswith('frm') and f.endswith('.php'):
                    frm_files.append(os.path.join(root, f))
        
        if not frm_files:
            logger.warning(f"No frm*.php files found in {self.codebase_dir}")
            return
        
        self._extract_from_form(frm_files[0])
        self._loaded = True
        logger.info(f"✅ CompanyFormTemplate loaded from {os.path.basename(frm_files[0])}")
    
    def _extract_from_form(self, filepath: str):
        """Extract fixed parts from a company form."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # CSS links
            self._css_links = re.findall(r'<link rel="stylesheet" href="([^"]+)">', content)
            
            # Footer scripts
            self._footer_scripts = re.findall(r'<script src="([^"]+)"></script>', content)
            
            # HTML head
            head_match = re.search(r'(<head>.*?</head>)', content, re.DOTALL)
            if head_match:
                self._html_head = head_match.group(1)
            
            # Body start (from <body> to <form>)
            body_match = re.search(r'(<body[^>]*>.*?<form[^>]*>)', content, re.DOTALL)
            if body_match:
                self._body_start = body_match.group(1)
            
            # Body end (from </form> to </html>)
            body_end_match = re.search(r'(</form>.*?</html>)', content, re.DOTALL)
            if body_end_match:
                self._body_end = body_end_match.group(1)
            
            logger.info(f"✅ Extracted template from {os.path.basename(filepath)}")
            logger.info(f"   CSS links: {len(self._css_links)}")
            logger.info(f"   Footer scripts: {len(self._footer_scripts)}")
            logger.info(f"   HTML head: {len(self._html_head)} chars")
            logger.info(f"   Body start: {len(self._body_start)} chars")
            logger.info(f"   Body end: {len(self._body_end)} chars")
            
        except Exception as e:
            logger.error(f"Error extracting from {filepath}: {e}")
    
    def get_css_links(self) -> str:
        """Get all CSS links as HTML string."""
        if not self._css_links:
            self.load()
        return '\n'.join(f'  <link rel="stylesheet" href="{css}">' for css in self._css_links)
    
    def get_footer_scripts(self) -> str:
        """Get all footer script tags as HTML string."""
        if not self._footer_scripts:
            self.load()
        return '\n'.join(f'  <script src="{script}"></script>' for script in self._footer_scripts)
    
    def get_complete_template(self) -> Dict[str, str]:
        """Get complete template with all fixed parts."""
        self.load()
        return {
            'html_head': self._html_head,
            'body_start': self._body_start,
            'body_end': self._body_end,
            'css_links': self.get_css_links(),
            'footer_scripts': self.get_footer_scripts(),
        }
    
    def merge_with_generated(self, php_logic: str, form_fields: str, form_validation: str, 
                             keyboard_nav: str, select2_handlers: str = "", 
                             ajax_handlers: str = "", maxid_function: str = "",
                             btnsave_function: str = "", body_onload: str = "") -> str:
        """
        Merge LLM-generated VARIABLE parts with FIXED template.
        
        Args:
            php_logic: PHP save/update/delete logic from LLM
            form_fields: HTML form fields from LLM
            form_validation: FormValidation field definitions from LLM
            keyboard_nav: Keyboard navigation from LLM
            select2_handlers: Select2 event handlers from LLM
            ajax_handlers: Custom AJAX handlers from LLM
            maxid_function: maxid() function for hierarchical codes
            btnsave_function: btnsave_click() function
            body_onload: onLoad handler for <body>
        
        Returns:
            Complete PHP file with all fixed + variable parts
        """
        self.load()
        
        # Build the complete file
        parts = []
        
        # 1. PHP logic at top
        parts.append(php_logic)
        parts.append("?>")
        parts.append("")
        
        # 2. HTML head (FIXED)
        parts.append(self._html_head)
        parts.append("")
        
        # 3. Head scripts (FIXED + VARIABLE)
        head_scripts = []
        
        # FIXED: Breakpoints
        head_scripts.append("  <script>")
        head_scripts.append("  Breakpoints();")
        
        # VARIABLE: maxid() function
        if maxid_function:
            head_scripts.append(maxid_function)
        
        # VARIABLE: btnsave_click() function
        if btnsave_function:
            head_scripts.append(btnsave_function)
        
        # VARIABLE: Keyboard navigation
        if keyboard_nav:
            head_scripts.append(keyboard_nav)
        
        head_scripts.append("  </script>")
        parts.append('\n'.join(head_scripts))
        parts.append("</head>")
        parts.append("")
        
        # 4. Body start (FIXED)
        if body_onload:
            body_start = self._body_start.replace('onLoad=""', f'onLoad="{body_onload}"')
            if 'onLoad=' not in body_start:
                body_start = body_start.replace('<body', f'<body onLoad="{body_onload}"')
            parts.append(body_start)
        else:
            parts.append(self._body_start)
        parts.append("")
        
        # 5. Form fields (VARIABLE)
        parts.append(form_fields)
        parts.append("")
        
        # 6. Body end (FIXED) - includes footer scripts + FormValidation + Select2
        body_end = self._body_end
        
        # Inject FormValidation fields before the closing </script>
        if form_validation:
            # Find the formValidation fields section and replace
            fv_pattern = r"(fields:\s*\{)[^}]*\}"
            if re.search(fv_pattern, body_end, re.DOTALL):
                body_end = re.sub(fv_pattern, f"fields: {{\n{form_validation}\n      }}", body_end, count=1, flags=re.DOTALL)
        
        # Inject Select2 handlers
        if select2_handlers:
            # Add before the final </script>
            body_end = body_end.replace("</script>", f"{select2_handlers}\n  </script>")
        
        parts.append(body_end)
        
        return '\n'.join(parts)
    
    def get_template_for_prompt(self) -> str:
        """Get template formatted for LLM prompt."""
        self.load()
        
        return f"""
COMPANY FORM TEMPLATE (FIXED PARTS - Automatically Added):

The following parts are FIXED and will be automatically added to your generated code.
You DO NOT need to generate these - just focus on the VARIABLE parts.

1. CSS LINKS ({len(self._css_links)} files):
{self.get_css_links()[:500]}...

2. FOOTER SCRIPTS ({len(self._footer_scripts)} files):
{self.get_footer_scripts()[:500]}...

3. HTML STRUCTURE:
- DOCTYPE, <html>, <head>, <meta> tags → AUTOMATIC
- <body> with onLoad, topmenu, sidemenu → AUTOMATIC
- <form class="form-horizontal"> wrapper → AUTOMATIC
- Footer includes, page wrapper → AUTOMATIC

YOUR JOB: Generate ONLY the VARIABLE parts:
1. PHP variables ($form, $form2, $table, $title)
2. AJAX handlers (GetMaxID function)
3. Delete logic with pre-delete checks
4. Save/Update logic with $columns array
5. Form fields (inputs, selects, textareas)
6. FormValidation field definitions
7. Keyboard navigation mappings
8. Select2 event handlers (if dropdowns)

The template has {len(self._css_links)} CSS files and {len(self._footer_scripts)} JS files.
"""
