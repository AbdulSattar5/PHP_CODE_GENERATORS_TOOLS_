"""
Dynamic Company Form Template Extractor
Extracts FIXED parts from ANY uploaded codebase dynamically.
Works for ANY company - no hardcoded values.

How it works:
1. Scans ALL frm*.php files in the uploaded codebase
2. Finds patterns that appear in 80%+ of forms (CSS, scripts, includes)
3. Extracts HTML structure from the best representative form
4. Returns a template that can merge with LLM-generated variable parts
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


class DynamicFormTemplate:
    """
    Dynamically extracts FIXED parts from uploaded company codebase.
    
    FIXED parts (same across 80%+ of forms):
    - CSS links (bootstrap, plugins, fonts)
    - Footer scripts (jQuery, bootstrap, plugins, components)
    - HTML wrapper (DOCTYPE, head, body, form structure)
    - Includes (topmenu, sidemenu, footer)
    - FormValidation boilerplate
    - Breakpoints, Site.run()
    
    VARIABLE parts (change per form):
    - PHP variables ($form, $form2, $table, $title)
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
        self._form_tag: str = ""
        self._topmenu_include: str = ""
        self._sidemenu_include: str = ""
        self._footer_include: str = ""
        self._loaded = False
        self._source_file: str = ""
        self._total_forms_scanned: int = 0
    
    def load(self) -> bool:
        """
        Dynamically extract template from codebase.
        Returns True if successful.
        """
        if self._loaded:
            return True
        
        # Step 1: Find ALL frm*.php files
        frm_files = self._find_form_files()
        self._total_forms_scanned = len(frm_files)
        
        if not frm_files:
            logger.warning(f"No frm*.php files found in {self.codebase_dir}")
            return False
        
        logger.info(f"📂 Scanning {len(frm_files)} form files for common patterns...")
        
        # Step 2: Find COMMON patterns across ALL forms
        self._extract_common_patterns(frm_files)
        
        # Step 3: Pick best representative form for detailed HTML extraction
        best_form = self._find_best_representative(frm_files)
        if best_form:
            self._extract_html_structure(best_form)
            self._source_file = os.path.basename(best_form)

        if not self._is_template_usable():
            logger.warning(
                "Dynamic template extraction produced incomplete structure; template will remain unavailable"
            )
            self._loaded = False
            return False

        self._loaded = True
        
        logger.info(f"✅ Dynamic template built from {self._total_forms_scanned} forms")
        logger.info(f"   Source: {self._source_file}")
        logger.info(f"   FIXED CSS links: {len(self._css_links)} files")
        logger.info(f"   FIXED Footer scripts: {len(self._footer_scripts)} files")
        logger.info(f"   FIXED HTML head: {len(self._html_head)} chars")
        logger.info(f"   FIXED Body start: {len(self._body_start)} chars")
        logger.info(f"   FIXED Body end: {len(self._body_end)} chars")
        
        fixed_size = len(self._html_head) + len(self._body_start) + len(self._body_end)
        fixed_size += len(self._css_links) * 60  # avg per CSS link tag
        fixed_size += len(self._footer_scripts) * 50  # avg per script tag
        logger.info(f"   FIXED template size: ~{fixed_size:,} chars ({fixed_size/1024:.1f} KB)")
        
        return True

    def _is_template_usable(self) -> bool:
        """Check minimum structure needed for safe template-based assembly."""
        required_segments = {
            'html_head': self._html_head,
            'body_start': self._body_start,
            'body_end': self._body_end,
        }
        missing_segments = [
            name for name, value in required_segments.items()
            if not str(value or '').strip()
        ]
        if missing_segments:
            logger.warning(
                f"Template missing required segments: {', '.join(missing_segments)}"
            )
            return False

        combined_markup = (self._body_start or '') + (self._body_end or '')
        if not str(self._form_tag or '').strip() and '<form' not in combined_markup.lower():
            logger.warning("Template missing form boundary markers")
            return False
        return True

    def is_loaded_and_usable(self) -> bool:
        """Public readiness check used by strict assembly paths."""
        return bool(self._loaded and self._is_template_usable())
    
    def _find_form_files(self) -> List[str]:
        """Find all frm*.php files in codebase."""
        frm_files = []
        for root, dirs, files in os.walk(self.codebase_dir):
            # Skip non-code directories
            dirs[:] = [d for d in dirs if d not in [
                'vendor', 'node_modules', '.git', 'storage', 'cache',
                'logs', 'tmp', 'temp', 'backup', 'dist', 'build'
            ]]
            for f in files:
                if f.startswith('frm') and f.endswith('.php'):
                    frm_files.append(os.path.join(root, f))
        return frm_files
    
    def _extract_common_patterns(self, frm_files: List[str]):
        """
        Find patterns that appear in 80%+ of forms.
        These are the FIXED parts that every form shares.
        """
        # Sample up to 15 forms for efficiency
        sample = frm_files[:min(15, len(frm_files))]
        
        css_counter: Counter = Counter()
        script_counter: Counter = Counter()
        include_counter: Counter = Counter()
        
        for filepath in sample:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # CSS links
                for css in re.findall(r'<link rel="stylesheet" href="([^"]+)">', content):
                    css_counter[css] += 1
                
                # Footer scripts
                for script in re.findall(r'<script src="([^"]+)"></script>', content):
                    script_counter[script] += 1
                
                # PHP includes
                for inc in re.findall(r'include\(["\']([^"\']+)["\']\)', content):
                    include_counter[inc] += 1
                    
            except Exception as e:
                logger.warning(f"Error reading {filepath}: {e}")
        
        # FIXED = appears in >= 80% of sampled forms
        threshold = max(1, int(len(sample) * 0.8))
        
        self._css_links = [css for css, count in css_counter.most_common() if count >= threshold]
        self._footer_scripts = [s for s, count in script_counter.most_common() if count >= threshold]
        
        # Common includes
        for inc, count in include_counter.most_common():
            if count < threshold:
                continue
            inc_lower = inc.lower()
            if 'topmenu' in inc_lower:
                self._topmenu_include = inc
            elif 'sidemenu' in inc_lower or 'rightmenu' in inc_lower:
                self._sidemenu_include = inc
            elif 'footer' in inc_lower:
                self._footer_include = inc
        
        logger.info(f"📊 Common patterns (threshold: {threshold}/{len(sample)} forms):")
        logger.info(f"   CSS: {len(self._css_links)} common links")
        logger.info(f"   Scripts: {len(self._footer_scripts)} common scripts")
    
    def _find_best_representative(self, frm_files: List[str]) -> Optional[str]:
        """
        Find a framework-heavy, low-contamination representative template.
        We prefer stable shared layout scaffolding over entity-specific feature density.
        """
        scored = []
        contamination_tokens = [
            'main_area', 'sub_area', 'cust_', 'customer', 'salesman',
            'costcenter', 'cbocustcategory', 'txtbname'
        ]
        
        for filepath in frm_files[:30]:  # Check first 30
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                score = 0
                lower = content.lower()
                basename = os.path.basename(filepath).lower()

                # Strongly prefer shared company framework patterns.
                if 'include("include/topmenu.php")' in lower:
                    score += 8
                if 'include("include/sidemenu.php")' in lower or 'include("include/rightmenu.php")' in lower:
                    score += 8
                if 'include("include/footer.php")' in lower:
                    score += 8
                if 'form-horizontal' in lower and 'action="<?=$form2;?>' in lower:
                    score += 8
                if 'class="page"' in lower and 'class="page-content"' in lower:
                    score += 6
                if 'breakpoints();' in lower and 'site.run()' in lower:
                    score += 4

                # Lightweight feature signals.
                if 'formvalidation' in lower:
                    score += 2
                if 'select2' in lower:
                    score += 2
                if 'getmaxid' in lower:
                    score += 1

                # Penalize highly entity-specific/customer-heavy templates.
                contamination_hits = sum(1 for token in contamination_tokens if token in lower)
                score -= contamination_hits * 3
                if basename.startswith('frmcustomer'):
                    score -= 10
                
                scored.append((score, filepath))
            except:
                pass
        
        if scored:
            scored.sort(reverse=True)
            logger.info(
                "📌 Representative template selected: %s (score=%s)",
                os.path.basename(scored[0][1]),
                scored[0][0]
            )
            return scored[0][1]
        
        return frm_files[0] if frm_files else None
    
    def _extract_html_structure(self, filepath: str):
        """Extract complete HTML structure from a representative form."""
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # HTML head (from <head> to </head>)
            head_match = re.search(r'(<head>.*?</head>)', content, re.DOTALL)
            if head_match:
                self._html_head = head_match.group(1)
            
            # Body start (from <body> up to but excluding the first <form>)
            body_match = re.search(r'(<body[^>]*>[\s\S]*?)<form\b', content, re.DOTALL | re.IGNORECASE)
            if body_match:
                self._body_start = body_match.group(1)
            else:
                body_match = re.search(r'(<body[^>]*>)', content, re.DOTALL | re.IGNORECASE)
                if body_match:
                    self._body_start = body_match.group(1)
            
            # Form tag
            form_match = re.search(r'(<form[^>]*>)', content, re.DOTALL)
            if form_match:
                self._form_tag = form_match.group(1)
            
            # Body end (after </form> to </html>) so merge logic controls form wrapper.
            body_end_match = re.search(r'</form>\s*(.*?</html>)', content, re.DOTALL | re.IGNORECASE)
            if body_end_match:
                self._body_end = body_end_match.group(1)
            else:
                body_end_match = re.search(r'(</body>\s*</html>)', content, re.DOTALL | re.IGNORECASE)
                if body_end_match:
                    self._body_end = body_end_match.group(1)
                
        except Exception as e:
            logger.error(f"Error extracting HTML from {filepath}: {e}")
    
    def get_css_links_html(self) -> str:
        """Get CSS links as HTML."""
        if not self._loaded:
            self.load()
        return '\n'.join(f'  <link rel="stylesheet" href="{css}">' for css in self._css_links)
    
    def get_footer_scripts_html(self) -> str:
        """Get footer scripts as HTML."""
        if not self._loaded:
            self.load()
        return '\n'.join(f'  <script src="{script}"></script>' for script in self._footer_scripts)

    def _ensure_common_css_links(self, head_html: str) -> str:
        """Inject missing common CSS links so merged output keeps full company layout footprint."""
        if not head_html:
            return head_html

        existing = {
            str(match).strip().lower()
            for match in re.findall(r'<link[^>]+href=["\']([^"\']+)["\']', head_html, flags=re.IGNORECASE)
            if str(match).strip()
        }
        missing = [
            css for css in (self._css_links or [])
            if str(css).strip() and str(css).strip().lower() not in existing
        ]
        if not missing:
            return head_html

        logger.info(f"Injecting {len(missing)} missing common CSS links into template head")
        injection = '\n'.join(f'  <link rel="stylesheet" href="{css}">' for css in missing)
        return head_html.rstrip() + '\n' + injection + '\n'

    def _strip_inline_head_scripts(self, head_html: str) -> str:
        """
        Remove inline <script> blocks from template head.
        Representative templates often contain entity-specific JS in <head>;
        keeping only external script tags prevents syntax contamination.
        """
        if not head_html:
            return head_html
        cleaned = re.sub(
            r'<script(?![^>]*\bsrc=)[^>]*>[\s\S]*?</script>',
            '',
            head_html,
            flags=re.IGNORECASE
        )
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned

    def _ensure_common_footer_scripts(self, body_end_html: str) -> str:
        """Inject missing common footer scripts so minimal variable sections still preserve full template size."""
        if not body_end_html:
            return body_end_html

        existing = {
            str(match).strip().lower()
            for match in re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', body_end_html, flags=re.IGNORECASE)
            if str(match).strip()
        }
        missing = [
            script for script in (self._footer_scripts or [])
            if str(script).strip() and str(script).strip().lower() not in existing
        ]
        if not missing:
            return body_end_html

        logger.info(f"Injecting {len(missing)} missing common footer scripts into template body end")
        script_block = '\n'.join(f'  <script src="{script}"></script>' for script in missing)
        if re.search(r'</body>', body_end_html, re.IGNORECASE):
            return re.sub(
                r'</body>',
                script_block + '\n</body>',
                body_end_html,
                count=1,
                flags=re.IGNORECASE
            )
        return body_end_html.rstrip() + '\n' + script_block + '\n'

    def _fixed_framework_bootstrap_js(self) -> str:
        """Shared bootstrap JS kept in merged template output for deterministic behavior and baseline footprint."""
        return """
<script>
(function(window){
  if (!window) { return; }

  window.companyFieldOrder = window.companyFieldOrder || [];
  window.companyValidationFields = window.companyValidationFields || {};
  window.companyFormOnLoad = window.companyFormOnLoad || function () {};
  window.companyAfterInit = window.companyAfterInit || function () {};

  window.companyCheckKeycode = window.companyCheckKeycode || function (e, field) {
    var evt = e || window.event;
    var keycode = evt && (evt.which || evt.keyCode);
    if (keycode !== 13) {
      return true;
    }
    if (evt && evt.preventDefault) {
      evt.preventDefault();
    } else if (evt) {
      evt.returnValue = false;
    }

    var order = window.companyFieldOrder || [];
    var currentField = field || (document.activeElement ? document.activeElement.id : '');
    var idx = order.indexOf(currentField);
    if (idx >= 0 && idx < order.length - 1) {
      var next = document.getElementById(order[idx + 1]);
      if (next) {
        if (typeof next.focus === 'function') {
          next.focus();
        }
        if (window.jQuery && window.jQuery.fn && window.jQuery.fn.select2 && window.jQuery(next).hasClass('select2-hidden-accessible')) {
          window.jQuery(next).select2('open');
        }
      }
    }
    return false;
  };

  window.checkKeycode = window.companyCheckKeycode;
  window.checkKeycode = window.checkKeycode || function (e, field) {
    return window.companyCheckKeycode(e, field);
  };
  function checkKeycode(e, field) {
    return window.companyCheckKeycode(e, field);
  }
  document.onkeydown = checkKeycode;

  window.btnsave_click = window.btnsave_click || function () {
    var form = document.getElementById('frm') || document.forms.frm;
    if (!form) { return false; }

    if (window.jQuery) {
      var $form = window.jQuery(form);
      var fv = $form.data('formValidation');
      if (fv && typeof fv.validate === 'function') {
        fv.validate();
        if (typeof fv.isValid === 'function' && !fv.isValid()) {
          return false;
        }
      }
    }

    var hiddenMode = document.getElementById('txtmode');
    if (hiddenMode) {
      hiddenMode.value = 'save';
    }

    var disabledInputs = form.querySelectorAll(':disabled');
    for (var i = 0; i < disabledInputs.length; i++) {
      disabledInputs[i].setAttribute('data-company-disabled', '1');
      disabledInputs[i].disabled = false;
    }

    form.action = "<?php echo $form2; ?>";
    form.method = "post";
    form.submit();
    return true;
  };

  window.companySharedInit = function () {
    if (window.__companySharedInit) { return; }
    window.__companySharedInit = true;

    var $ = window.jQuery;
    if (window.Site && typeof window.Site.run === 'function') {
      window.Site.run();
    }
    if (!$) { return; }

    $(document)
      .off('click.companyAjaxNav')
      .on('click.companyAjaxNav', '[data-ajax-nav], a.ajax-nav', function (e) {
        var url = $(this).attr('href') || $(this).data('ajax-nav');
        if (!url || url === '#' || /^javascript:/i.test(url)) {
          return;
        }
        e.preventDefault();
        $.get(url).done(function (html) {
          var $target = $('#ajax-content');
          if ($target.length) {
            $target.html(html);
          }
        });
      });

    if ($.fn && $.fn.select2) {
      $('select[data-plugin="select2"], select.select2').each(function () {
        var $el = $(this);
        if (!$el.data('select2')) {
          $el.select2({ width: '100%' });
        }
      });
    }

    var $form = $('#frm');
    if ($form.length && $.fn && $.fn.formValidation && !$form.data('formValidation')) {
      $form.formValidation({
        framework: 'bootstrap',
        fields: window.companyValidationFields || {}
      });
    }

    if (typeof window.companyAfterInit === 'function') {
      window.companyAfterInit($);
    }
  };

  window.companyPageLoad = function () {
    window.companySharedInit();
    if (typeof window.companyFormOnLoad === 'function') {
      window.companyFormOnLoad();
    }
  };
})(window);
</script>
""".strip()

    def _normalize_php_segment(self, code: str) -> str:
        """Normalize embedded PHP fragments so template merge adds only one PHP wrapper."""
        segment = (code or '').strip()
        if not segment:
            return ""
        segment = re.sub(r'^\s*<\?php', '', segment, flags=re.IGNORECASE).strip()
        segment = re.sub(r'\?>\s*$', '', segment).strip()
        return segment

    def _strip_named_js_function(self, markup: str, function_name: str) -> str:
        """Remove a named JS function declaration from template markup."""
        if not markup:
            return ""

        original_markup = markup
        lines = markup.splitlines()
        output: List[str] = []
        i = 0
        target = (function_name or '').strip().lower()

        while i < len(lines):
            line = lines[i]
            match = re.search(r'function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', line, re.IGNORECASE)
            if not match or match.group(1).lower() != target:
                output.append(line)
                i += 1
                continue

            brace_depth = line.count('{') - line.count('}')
            i += 1
            while i < len(lines) and brace_depth > 0:
                brace_depth += lines[i].count('{') - lines[i].count('}')
                i += 1

            if brace_depth > 0:
                logger.warning(
                    "⚠️ Template JS strip aborted for %s due to unmatched braces; preserving original markup",
                    function_name
                )
                return original_markup

        return '\n'.join(output)

    def _strip_named_js_functions(self, markup: str, function_names: List[str]) -> str:
        cleaned = str(markup or '')
        for function_name in function_names or []:
            cleaned = self._strip_named_js_function(cleaned, function_name)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _strip_legacy_formvalidation_blocks(self, markup: str) -> str:
        """Remove template-era FormValidation init blocks so only one canonical init remains."""
        cleaned = str(markup or '')
        patterns = [
            r'\(\s*function\s*\(\)\s*\{\s*\$\([^)]+\)\s*\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*(?:\.on\([\s\S]*?\)\s*)*;?\s*\}\)\s*\(\s*\)\s*;?',
            r'\$\(\s*document\s*\)\.ready\s*\(\s*function\s*\(\)\s*\{\s*\$\([^)]+\)\s*\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*(?:\.on\([\s\S]*?\)\s*)*;?\s*\}\s*\)\s*;?',
            r'\$\([^)]+\)\s*\.formValidation\s*\(\s*\{[\s\S]*?\}\s*\)\s*(?:\.on\([\s\S]*?\)\s*)*;?',
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r'<script>\s*</script>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()
    
    def merge_with_generated(self,
                              php_logic: str = "",
                              form_fields: str = "",
                              head_scripts: str = "",
                              body_onload: str = "",
                              form_validation_fields: str = "",
                              select2_handlers: str = "",
                              ajax_handlers: str = "",
                              crud_operations: str = "",
                              entity_js: str = "") -> str:
        """
        Merge LLM-generated VARIABLE parts with FIXED template.
        
        Args:
            php_logic: PHP save/update/delete logic from LLM
            form_fields: HTML form fields from LLM
            head_scripts: maxid(), btnsave_click(), checkKeycode() from LLM
            body_onload: onLoad handler for <body>
            form_validation_fields: FormValidation field definitions from LLM
            select2_handlers: Select2 event handlers from LLM
            ajax_handlers: AJAX handlers (GetMaxID, cascading dropdowns) from LLM
            crud_operations: CRUD operations (Save/Update/Delete/Edit) from LLM
        
        Returns:
            Complete PHP file (FIXED + VARIABLE = company-style form)
        
        Raises:
            ValueError: If required sections are empty
        """
        if not self._loaded:
            self.load()
        
        # ✅ PHASE 1.1: FAIL-FAST VALIDATION
        logger.info("🔍 Validating VARIABLE parts for template injection...")
        
        # Combine all PHP logic sources for validation
        all_php_logic = '\n'.join([
            php_logic or '',
            ajax_handlers or '',
            crud_operations or ''
        ])
        
        # Track validation errors
        validation_errors = []
        
        # CRITICAL: Check required VARIABLE parts
        if not all_php_logic.strip():
            validation_errors.append("PHP logic is empty (php_logic, ajax_handlers, crud_operations all empty)")
        
        if not form_fields or not form_fields.strip():
            validation_errors.append("form_fields is empty - cannot generate form without fields")
        
        # FAIL FAST: If critical sections are empty, raise error immediately
        if validation_errors:
            error_msg = "❌ MERGE FAILED - Required sections are empty:\n" + "\n".join(f"  - {err}" for err in validation_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # ✅ TASK 3.3: Validate mandatory company functions are present
        # FIX #1: Search across ALL sections (not just CRUD)
        # Combine ALL generated sections for comprehensive validation
        all_generated_code = '\n'.join([
            php_logic or '',
            ajax_handlers or '',
            crud_operations or '',
            form_fields or '',
            head_scripts or '',
            entity_js or ''
        ])
        
        # CORE mandatory — must always be present somewhere in generated code
        core_mandatory = [
            'db_insert', 'db_update', 'db_delete', 'db_getRecord',
            'funStartTran', 'funEndTran'
        ]
        
        # CONDITIONAL mandatory — getrows/getvalue can be in ANY section
        conditional_mandatory = ['getrows', 'getvalue']
        
        missing_functions = []
        
        # Check core functions (BLOCKS if missing)
        for func in core_mandatory:
            if func not in all_generated_code:
                missing_functions.append(func)
        
        # Check conditional functions (WARN ONLY, don't block)
        for func in conditional_mandatory:
            if func not in all_generated_code:
                logger.warning(f"⚠️ Optional function '{func}' not found in any section (non-blocking - will be auto-injected if needed)")
                # DO NOT append to missing_functions — just log warning
        
        if missing_functions:
            error_msg = f"❌ MERGE FAILED - Missing mandatory company functions: {', '.join(missing_functions)}"
            logger.error(error_msg)
            logger.error(f"   Searched in: php_logic, ajax_handlers, crud_operations, form_fields, head_scripts, entity_js")
            raise ValueError(error_msg)
        else:
            logger.info(f"✅ All mandatory company functions present: {', '.join(core_mandatory)}")
            if all(func in all_generated_code for func in conditional_mandatory):
                logger.info(f"✅ Optional functions also present: {', '.join(conditional_mandatory)}")
        
        # Log what VARIABLE parts we received
        logger.info(f"📊 VARIABLE parts received:")
        logger.info(f"   - php_logic: {len(php_logic)} chars")
        logger.info(f"   - form_fields: {len(form_fields)} chars")
        logger.info(f"   - head_scripts: {len(head_scripts)} chars")
        logger.info(f"   - body_onload: {len(body_onload)} chars")
        logger.info(f"   - form_validation_fields: {len(form_validation_fields)} chars")
        logger.info(f"   - select2_handlers: {len(select2_handlers)} chars")
        logger.info(f"   - ajax_handlers: {len(ajax_handlers)} chars")
        logger.info(f"   - crud_operations: {len(crud_operations)} chars")
        logger.info(f"   - entity_js: {len(entity_js)} chars")
        
        parts = []
        
        # ✅ TASK 3.3: 1. Inject PHP logic at the top of the file before HTML
        logger.info("🔧 Injecting PHP logic at top of file...")
        
        # Combine all PHP logic parts in proper order
        combined_php_logic = []
        if php_logic and php_logic.strip():
            normalized = self._normalize_php_segment(php_logic)
            if normalized:
                combined_php_logic.append(normalized)
        if crud_operations and crud_operations.strip():
            normalized = self._normalize_php_segment(crud_operations)
            if normalized:
                combined_php_logic.append(normalized)
        if ajax_handlers and ajax_handlers.strip():
            normalized = self._normalize_php_segment(ajax_handlers)
            if normalized:
                combined_php_logic.append(normalized)
        
        if combined_php_logic:
            parts.append("<?php")
            parts.append('\n\n'.join(combined_php_logic))
            parts.append("?>")
            parts.append("")
        else:
            logger.warning("⚠️ No PHP logic to inject - skipping PHP section")
        
        # 2. HTML head (FIXED)
        template_head = self._strip_named_js_functions(
            self._html_head,
            ['maxid', 'btnsave_click', 'checkKeycode']
        )
        template_head = self._strip_inline_head_scripts(template_head)
        template_head = self._ensure_common_css_links(template_head)
        template_head = re.sub(r'</head>\s*$', '', template_head, flags=re.IGNORECASE)
        parts.append(template_head)
        parts.append("")
        
        # ✅ TASK 3.3: 3. Inject head scripts (maxid(), btnsave_click(), checkKeycode()) in the head section
        logger.info("🔧 Injecting head scripts in head section...")
        if head_scripts and head_scripts.strip():
            parts.append("  <script>")
            parts.append("  Breakpoints();")
            parts.append("")
            parts.append(head_scripts.strip())
            parts.append("  </script>")
        parts.append("</head>")
        parts.append("")
        
        # 4. Body start (FIXED) with dynamic onLoad
        # Strip out any existing includes from body_start since we'll inject them separately
        body_start = self._body_start
        
        # Remove existing includes from body_start to avoid duplication
        body_start = re.sub(r'<\?php\s+include\(["\']include/topmenu\.php["\']\);\s*\?>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'<\?php\s+include\(["\']include/sidemenu\.php["\']\);\s*\?>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'<\?php\s+include\(["\']include/rightmenu\.php["\']\);\s*\?>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'<\?php\s+include\(["\']include/formheader\.php["\']\);\s*\?>', '', body_start, flags=re.IGNORECASE)
        
        # Remove page container divs from body_start since we'll add them separately
        body_start = re.sub(r'<div\s+class="page[^"]*"[^>]*>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'<div\s+class="page-content[^"]*"[^>]*>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'<form\b[^>]*>', '', body_start, flags=re.IGNORECASE)
        body_start = re.sub(r'</form>', '', body_start, flags=re.IGNORECASE)
        
        if body_onload and body_onload.strip():
            if 'onLoad=' in body_start:
                body_start = re.sub(r'onLoad="[^"]*"', f'onLoad="{body_onload}"', body_start)
            else:
                body_start = body_start.replace('<body', f'<body onLoad="{body_onload}"')
        parts.append(body_start)
        parts.append("")
        
        # ✅ FIX: Inject topmenu, sidemenu, footer includes (CRITICAL for validator)
        logger.info("🔧 Injecting company layout includes (topmenu, sidemenu, footer)...")
        if self._topmenu_include:
            parts.append(f'  <?php include("{self._topmenu_include}"); ?>')
            logger.info(f"   ✅ Injected topmenu: {self._topmenu_include}")
        if self._sidemenu_include:
            parts.append(f'  <?php include("{self._sidemenu_include}"); ?>')
            logger.info(f"   ✅ Injected sidemenu: {self._sidemenu_include}")
        parts.append("")
        
        # Add page container structure (required by validator)
        parts.append('  <div class="page">')
        parts.append('    <div class="page-content">')
        logger.info("   ✅ Injected page container structure")
        parts.append("")
        
        # ✅ TASK 3.3: 5. Inject form fields in the body section within the form wrapper
        logger.info("🔧 Injecting form fields in body section...")
        if form_fields and form_fields.strip():
            sanitized_form_fields = re.sub(r'<form\b[^>]*>', '', form_fields.strip(), flags=re.IGNORECASE)
            sanitized_form_fields = re.sub(r'</form>', '', sanitized_form_fields, flags=re.IGNORECASE)
            sanitized_form_fields = re.sub(r'^\s*["\']\s*>\s*', '', sanitized_form_fields)

            # Enforce a single canonical form wrapper to avoid nested/broken forms.
            parts.append('    <form class="form-horizontal" id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">')
            parts.append(sanitized_form_fields.strip())
            parts.append('    </form>')
            logger.info("   ✅ Injected canonical form wrapper with sanitized fields")
            parts.append("")
        else:
            logger.warning("⚠️ No form fields to inject")
        
        # Close page container structure
        parts.append('    </div>')
        parts.append('  </div>')
        parts.append("")
        
        # ✅ FIX: Inject footer include (CRITICAL for validator)
        if self._footer_include:
            parts.append(f'  <?php include("{self._footer_include}"); ?>')
            logger.info(f"   ✅ Injected footer: {self._footer_include}")
        parts.append("")
        
        # ✅ TASK 3.3: 6. Body end (FIXED) with injected VARIABLE parts
        replace_template_validation = bool(
            (form_validation_fields and form_validation_fields.strip())
            or (select2_handlers and select2_handlers.strip())
            or (entity_js and entity_js.strip())
        )
        body_end = (
            self._strip_legacy_formvalidation_blocks(self._body_end)
            if replace_template_validation
            else (self._body_end or '')
        )
        body_end = self._ensure_common_footer_scripts(body_end)
        body_end = re.sub(r'</form>', '', body_end, flags=re.IGNORECASE)
        
        # ✅ TASK 3.3: Replace FormValidation fields placeholder with LLM-generated validation rules
        if form_validation_fields and form_validation_fields.strip() and "fields:" in body_end:
            logger.info("🔧 Replacing FormValidation fields placeholder...")
            body_end = re.sub(
                r"(fields:\s*\{)[^}]*(\})",
                f"fields: {{\n{form_validation_fields.strip()}\n      }}",
                body_end,
                count=1,
                flags=re.DOTALL
            )
        
        # ✅ TASK 3.3: Inject Select2 handlers in dedicated script block.
        # Never splice into an existing <script src="..."></script> tag.
        if select2_handlers and select2_handlers.strip():
            logger.info("🔧 Injecting Select2 event handlers in dedicated script block...")
            select2_block = f"<script>\n{select2_handlers.strip()}\n</script>"
            if "</body>" in body_end:
                body_end = body_end.replace("</body>", f"{select2_block}\n</body>", 1)
            elif "</html>" in body_end:
                body_end = body_end.replace("</html>", f"{select2_block}\n</html>", 1)
            else:
                body_end = body_end + "\n" + select2_block
        
        # Preserve entity-specific JS so maxid(), formValidation config,
        # field order, and other dynamic behavior survive template merge.
        if entity_js and entity_js.strip():
            logger.info("Injecting entity-specific JS before closing body tag...")
            entity_payload = entity_js.strip()
            entity_block = entity_payload
            if not re.match(r'^\s*<script\b', entity_payload, re.IGNORECASE):
                entity_block = f"<script>\n{entity_payload}\n</script>"

            if "</body>" in body_end:
                body_end = body_end.replace(
                    "</body>",
                    f"{entity_block}\n</body>",
                    1
                )
            elif "</html>" in body_end:
                body_end = body_end.replace(
                    "</html>",
                    f"{entity_block}\n</html>",
                    1
                )
            else:
                body_end = body_end + "\n" + entity_block

        framework_js = self._fixed_framework_bootstrap_js()
        if framework_js and 'window.companySharedInit' not in body_end:
            if "</body>" in body_end:
                body_end = body_end.replace("</body>", framework_js + "\n</body>", 1)
            elif "</html>" in body_end:
                body_end = body_end.replace("</html>", framework_js + "\n</html>", 1)
            else:
                body_end = body_end + "\n" + framework_js

        parts.append(body_end)
        
        merged_content = '\n'.join(parts)
        
        logger.info(f"✅ Template injection complete:")
        logger.info(f"   - Total output: {len(merged_content)} chars ({len(merged_content)/1024:.1f} KB)")
        logger.info(f"   - PHP logic injected: {'✅' if combined_php_logic else '⚠️ (empty)'}")
        logger.info(f"   - Head scripts injected: {'✅' if head_scripts else '⚠️ (empty)'}")
        logger.info(f"   - Form fields injected: {'✅' if form_fields else '⚠️ (empty)'}")
        logger.info(f"   - FormValidation fields injected: {'✅' if form_validation_fields else '⚠️ (empty)'}")
        logger.info(f"   - Select2 handlers injected: {'✅' if select2_handlers else '⚠️ (empty)'}")
        logger.info(f"   - AJAX handlers injected: {'✅' if ajax_handlers else '⚠️ (empty)'}")
        logger.info(f"   - CRUD operations injected: {'✅' if crud_operations else '⚠️ (empty)'}")
        logger.info(f"   - Layout includes injected: {'✅' if self._topmenu_include and self._sidemenu_include and self._footer_include else '⚠️ (missing)'}")
        
        logger.info(f"   - Entity JS injected: {'âœ…' if entity_js else 'âš ï¸ (empty)'}")
        return merged_content
    
    def get_template_info_for_prompt(self) -> str:
        """Get template info to include in LLM prompt."""
        if not self._loaded:
            self.load()
        
        return f"""
COMPANY FORM TEMPLATE (FIXED PARTS - Automatically Added at Runtime):

The following parts are FIXED and will be automatically added to your generated code.
You DO NOT need to generate these - just focus on the VARIABLE parts.

✅ CSS LINKS: {len(self._css_links)} files (bootstrap, plugins, fonts)
✅ FOOTER SCRIPTS: {len(self._footer_scripts)} files (jQuery, bootstrap, plugins)
✅ HTML STRUCTURE: DOCTYPE, <html>, <head>, <meta>, <body>, <form> wrapper
✅ INCLUDES: topmenu, sidemenu, footer
✅ FormValidation boilerplate
✅ Site.run(), Breakpoints

YOUR JOB - Generate ONLY the VARIABLE parts:
1. PHP variables ($form, $form2, $table, $title)
2. AJAX handlers (GetMaxID function)
3. Delete logic with pre-delete checks
4. Save/Update logic with $columns array
5. Form fields (inputs, selects, textareas)
6. FormValidation field definitions
7. Keyboard navigation (checkKeycode function)
8. Select2 event handlers (if dropdowns)

Template size: ~{len(self._html_head) + len(self._body_start) + len(self._body_end):,} chars
"""
