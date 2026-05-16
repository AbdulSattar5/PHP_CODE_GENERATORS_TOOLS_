"""
Pattern Matching Validator
Checks if generated code matches company's actual patterns
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class PatternMatchingValidator:
    """
    Validates that generated code follows company's actual patterns
    """
    
    def validate_php_patterns(self, php_code: str, analyzed_patterns: Dict) -> Dict:
        """
        Check if PHP code uses company's patterns - IMPROVED VERSION
        Now checks CODE STRUCTURE, not just function names
        Returns: {score: 0-100, issues: [...]}
        """
        score = 0
        issues = []
        max_score = 100
        
        php_patterns = analyzed_patterns.get('php', {})
        
        # Check 1: Session Management STRUCTURE (20 points)
        session_mgmt = php_patterns.get('session_management', 'session_start()')
        if '@session_start()' in php_code or 'session_start()' in php_code:
            # Check if it's at the beginning of the file (proper structure)
            lines = php_code.split('\n')
            found_early = False
            for i, line in enumerate(lines[:10]):  # Check first 10 lines
                if 'session_start' in line:
                    found_early = True
                    break
            
            if found_early:
                score += 20
                logger.info(f"✅ PHP: Using company's session pattern at file start")
            else:
                score += 10  # Partial credit
                issues.append("Session management not at file start")
        else:
            issues.append(f"Missing company's session pattern: {session_mgmt}")
            logger.warning(f"❌ PHP: Not using company's session pattern")
        
        # Check 2: Include Structure (20 points)
        if 'include(' in php_code or 'require(' in php_code:
            # Check if includes are near the top
            lines = php_code.split('\n')
            found_early = False
            for i, line in enumerate(lines[:15]):  # Check first 15 lines
                if 'include(' in line or 'require(' in line:
                    found_early = True
                    break
            
            if found_early:
                score += 20
                logger.info(f"✅ PHP: Using include statements at file start")
            else:
                score += 10
                issues.append("Include statements not at file start")
        else:
            issues.append(f"Missing include statements")
            logger.warning(f"❌ PHP: Not using include statements")
        
        # Check 3: Transaction STRUCTURE (20 points)
        trans_start = php_patterns.get('transaction_management', {}).get('start', 'funStartTran')
        trans_end = php_patterns.get('transaction_management', {}).get('end', 'funEndTran')
        
        has_start = trans_start in php_code
        has_end = trans_end in php_code
        
        if has_start and has_end:
            # Check if they're properly paired (start before end)
            start_pos = php_code.find(trans_start)
            end_pos = php_code.find(trans_end)
            
            if start_pos < end_pos:
                score += 20
                logger.info(f"✅ PHP: Using proper transaction structure")
            else:
                score += 10
                issues.append("Transaction functions not properly ordered")
        elif has_start or has_end:
            score += 5
            issues.append("Incomplete transaction management (missing start or end)")
        else:
            issues.append(f"Missing company's transaction pattern: {trans_start}, {trans_end}")
        
        # Check 4: Database Operations STRUCTURE (20 points)
        company_functions = php_patterns.get('functions', [])
        db_functions = [f for f in company_functions if any(db in f for db in ['db_', 'getrows', 'mysql_'])]
        
        if db_functions:
            matches = sum(1 for func in db_functions[:10] if func in php_code)
            if matches >= 3:
                score += 20
                logger.info(f"✅ PHP: Using {matches} company database functions")
            elif matches >= 1:
                score += 10
                logger.info(f"✅ PHP: Using {matches} company database functions (partial)")
            else:
                # Handle both List[str] and List[Dict] formats for safety
                if db_functions and isinstance(db_functions[0], dict):
                    db_funcs_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in db_functions[:5]])
                else:
                    db_funcs_str = ', '.join([str(f) for f in db_functions[:5]])
                issues.append(f"Not using company's database functions: {db_funcs_str}")
                logger.warning(f"❌ PHP: Not using company's database functions")
        
        # Check 5: Variable Structure (20 points)
        common_vars = php_patterns.get('common_variables', [])
        if common_vars:
            # Check for proper variable structure patterns
            has_columns = '$columns[' in php_code  # Array structure
            has_filter = '$filter' in php_code
            has_table = '$table' in php_code
            
            structure_score = 0
            if has_columns:
                structure_score += 8
            if has_filter:
                structure_score += 6
            if has_table:
                structure_score += 6
            
            score += structure_score
            
            if structure_score >= 15:
                logger.info(f"✅ PHP: Using company variable structure patterns")
            elif structure_score >= 8:
                logger.info(f"✅ PHP: Using some company variable patterns")
            else:
                issues.append(f"Not using company's variable structure: $columns[], $filter, $table")
                logger.warning(f"❌ PHP: Not using company's variable structure")
        
        return {
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score * 100) if max_score > 0 else 0,
            'issues': issues,
            'passed': score >= 60  # Need at least 60% pattern match
        }
    
    def validate_html_patterns(self, html_code: str, analyzed_patterns: Dict) -> Dict:
        """
        Check if HTML code uses company's patterns - IMPROVED VERSION
        Now checks HTML STRUCTURE, not just CSS classes
        """
        score = 0
        issues = []
        max_score = 100
        
        html_patterns = analyzed_patterns.get('html', {})
        
        # Check 1: Form Structure (30 points)
        if '<form' in html_code:
            # Check for proper form attributes
            has_method = 'method=' in html_code
            has_action = 'action=' in html_code
            has_id_or_name = 'id=' in html_code or 'name=' in html_code
            
            form_score = 0
            if has_method:
                form_score += 10
            if has_action:
                form_score += 10
            if has_id_or_name:
                form_score += 10
            
            score += form_score
            if form_score >= 20:
                logger.info(f"✅ HTML: Using proper form structure")
            else:
                issues.append("Form missing proper attributes (method, action, id/name)")
        else:
            issues.append("Missing form tag")
            logger.warning(f"❌ HTML: Missing form tag")
        
        # Check 2: Input Structure (30 points)
        input_count = html_code.count('<input')
        if input_count >= 2:
            # Check for proper input attributes
            has_names = 'name=' in html_code
            has_ids = 'id=' in html_code
            has_classes = 'class=' in html_code
            
            input_score = 0
            if has_names:
                input_score += 10
            if has_ids:
                input_score += 10
            if has_classes:
                input_score += 10
            
            score += input_score
            if input_score >= 20:
                logger.info(f"✅ HTML: Using proper input structure")
            else:
                issues.append("Inputs missing proper attributes (name, id, class)")
        else:
            issues.append("Not enough input fields")
        
        # Check 3: CSS Classes (20 points)
        css_classes = html_patterns.get('css_classes', [])
        
        # Check for CRITICAL company CSS classes
        critical_classes = ['form-group', 'col-md-', 'form-control', 'btn', 'btn-primary']
        critical_matches = sum(1 for cls in critical_classes if cls in html_code)
        
        if css_classes:
            matches = sum(1 for cls in css_classes[:10] if cls in html_code)
            if matches >= 5 and critical_matches >= 4:
                score += 20
                logger.info(f"✅ HTML: Using {matches} company CSS classes with critical patterns")
            elif matches >= 3 and critical_matches >= 3:
                score += 15
                logger.info(f"✅ HTML: Using {matches} company CSS classes")
            elif critical_matches >= 3:
                score += 10
                logger.info(f"✅ HTML: Using critical CSS classes (partial)")
            else:
                # Handle both List[str] and List[Dict] formats for safety
                if css_classes and isinstance(css_classes[0], dict):
                    css_str = ', '.join([str(c.get('name', c.get('class', ''))) for c in css_classes[:5]])
                else:
                    css_str = ', '.join([str(c) for c in css_classes[:5]])
                issues.append(f"Not using company's CSS classes: {css_str}")
                logger.warning(f"❌ HTML: Not using company's CSS classes")
        else:
            # Check for critical classes even if no patterns available
            if critical_matches >= 4:
                score += 15
            elif critical_matches >= 2:
                score += 8
            else:
                issues.append("Missing critical CSS classes: form-group, col-md-*, form-control, btn")
        
        # Check 4: Layout Structure (20 points)
        # Check for Bootstrap/grid structure with company's specific pattern
        has_form_horizontal = 'form-horizontal' in html_code
        has_form_groups = html_code.count('form-group') >= 2  # At least 2 form groups
        has_col_md = 'col-md-' in html_code
        has_control_label = 'control-label' in html_code
        
        layout_score = 0
        if has_form_horizontal:
            layout_score += 5
        if has_form_groups:
            layout_score += 5
        if has_col_md:
            layout_score += 5
        if has_control_label:
            layout_score += 5
        
        score += layout_score
        if layout_score >= 15:
            logger.info(f"✅ HTML: Using proper company layout structure (form-horizontal, form-groups, col-md, control-label)")
        elif layout_score >= 10:
            logger.info(f"✅ HTML: Using company layout structure")
        elif layout_score >= 5:
            logger.info(f"✅ HTML: Using some layout structure")
        else:
            issues.append("Missing proper company layout structure (form-horizontal, form-groups, col-md, control-label)")
        
        return {
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score * 100) if max_score > 0 else 0,
            'issues': issues,
            'passed': score >= 40  # Lowered threshold from 40 to make it more achievable
        }
    
    def validate_js_patterns(self, js_code: str, analyzed_patterns: Dict) -> Dict:
        """
        Check if JavaScript code uses company's patterns
        """
        score = 0
        issues = []
        max_score = 100
        
        js_patterns = analyzed_patterns.get('js', {})
        
        # Check 1: AJAX Pattern (40 points)
        ajax_pattern = js_patterns.get('ajax_pattern', '')
        uses_jquery = js_patterns.get('uses_jquery', True)
        
        if uses_jquery and ('$.post' in js_code or '$.ajax' in js_code or 'jQuery' in js_code):
            score += 40
            logger.info(f"✅ JS: Using jQuery AJAX pattern")
        elif not uses_jquery and ('fetch(' in js_code or 'XMLHttpRequest' in js_code):
            score += 40
            logger.info(f"✅ JS: Using vanilla JS AJAX pattern")
        else:
            expected = "jQuery ($.post, $.ajax)" if uses_jquery else "fetch() or XMLHttpRequest"
            issues.append(f"Not using company's AJAX pattern: {expected}")
            logger.warning(f"❌ JS: Not using company's AJAX pattern")
        
        # Check 2: Function Names (30 points)
        functions = js_patterns.get('functions', [])
        if functions:
            matches = sum(1 for func in functions[:10] if func in js_code)
            if matches > 0:
                score += min(30, matches * 6)
                logger.info(f"✅ JS: Using {matches} company function names")
            else:
                # Handle both List[str] and List[Dict] formats for safety
                if functions and isinstance(functions[0], dict):
                    funcs_str = ', '.join([str(f.get('name', f.get('function', ''))) for f in functions[:5]])
                else:
                    funcs_str = ', '.join([str(f) for f in functions[:5]])
                issues.append(f"Not using company's function names: {funcs_str}")
                logger.warning(f"❌ JS: Not using company's function names")
        
        # Check 3: Variable Names (30 points)
        common_vars = js_patterns.get('common_variables', [])
        if common_vars:
            matches = sum(1 for var in common_vars[:10] if var in js_code)
            if matches > 0:
                score += min(30, matches * 6)
                logger.info(f"✅ JS: Using {matches} company variable names")
            else:
                # Handle both List[str] and List[Dict] formats for safety
                if common_vars and isinstance(common_vars[0], dict):
                    vars_str = ', '.join([str(v.get('name', v.get('variable', ''))) for v in common_vars[:5]])
                else:
                    vars_str = ', '.join([str(v) for v in common_vars[:5]])
                issues.append(f"Not using company's variable names: {vars_str}")
                logger.warning(f"❌ JS: Not using company's variable names")
        
        return {
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score * 100) if max_score > 0 else 0,
            'issues': issues,
            'passed': score >= 40
        }
    
    def validate_all_patterns(self, state: Dict) -> Dict:
        """
        Validate all generated code against company patterns
        """
        analyzed_patterns = state.get('analyzed_patterns', {})
        
        if not analyzed_patterns:
            logger.warning("⚠️ No analyzed patterns available for validation")
            return {
                'overall_score': 0,
                'passed': False,
                'message': 'No company patterns available for validation'
            }
        
        logger.info("🔍 Starting pattern matching validation...")
        
        results = {
            'php': self.validate_php_patterns(state.get('php_code', ''), analyzed_patterns),
            'html': self.validate_html_patterns(state.get('html_code', ''), analyzed_patterns),
            'js': self.validate_js_patterns(state.get('js_code', ''), analyzed_patterns)
        }
        
        # Calculate overall score
        total_score = sum(r['score'] for r in results.values())
        total_max = sum(r['max_score'] for r in results.values())
        overall_percentage = (total_score / total_max * 100) if total_max > 0 else 0
        
        # Collect all issues
        all_issues = []
        for lang, result in results.items():
            for issue in result['issues']:
                all_issues.append(f"{lang.upper()}: {issue}")
        
        # Log summary
        logger.info(f"📊 Pattern Matching Results:")
        logger.info(f"   PHP: {results['php']['percentage']:.1f}% ({results['php']['score']}/{results['php']['max_score']})")
        logger.info(f"   HTML: {results['html']['percentage']:.1f}% ({results['html']['score']}/{results['html']['max_score']})")
        logger.info(f"   JS: {results['js']['percentage']:.1f}% ({results['js']['score']}/{results['js']['max_score']})")
        logger.info(f"   OVERALL: {overall_percentage:.1f}% - {'✅ PASSED' if overall_percentage >= 50 else '❌ FAILED'}")
        
        return {
            'overall_score': overall_percentage,
            'passed': overall_percentage >= 50,  # Need 50% overall match
            'results': results,
            'issues': all_issues,
            'message': f"Pattern matching: {overall_percentage:.1f}% - {'PASSED' if overall_percentage >= 50 else 'FAILED'}"
        }
