"""
Prompt templates for GenCode AI code generation
"""

from typing import Dict, List, Any


class PromptTemplates:
    """
    Collection of prompt templates for different code generation tasks
    """
    
    @staticmethod
    def get_intent_analysis_prompt(user_request: str) -> Dict[str, str]:
        """
        Prompt for analyzing user intent
        """
        system_prompt = """
You are an expert software analyst. Your job is to analyze user requests for code generation and extract structured intent information.

Analyze the user's request and identify:
1. Primary intent (form_creation, crud_operations, api_development, etc.)
2. Entities mentioned (student, product, user, etc.)
3. Required components (database, frontend, backend, styling, javascript)
4. Complexity level (simple, medium, complex)
5. Estimated number of files needed

Respond in a structured format that can be parsed.
"""
        
        human_prompt = f"""
User Request: "{user_request}"

Please analyze this request and provide:
- Primary Intent: [intent]
- Entities: [list of entities]
- Components Needed: [database, frontend, backend, styling, javascript]
- Complexity: [simple/medium/complex]
- Estimated Files: [number]
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def get_database_generation_prompt(user_request: str, intent: Dict, patterns: List[Dict], standards: Dict) -> Dict[str, str]:
        """
        Prompt for generating database schema
        """
        system_prompt = f"""
You are an expert database architect. Generate MySQL database schema based on user requirements.

STANDARDS TO FOLLOW:
- Engine: {standards.get('db_engine', 'InnoDB')}
- Charset: {standards.get('charset', 'utf8mb4')}
- Use proper data types and constraints
- Include primary keys, foreign keys, and indexes
- Add timestamps (created_at, updated_at)

COMPANY PATTERNS:
{PromptTemplates._format_patterns(patterns, 'sql')}

Generate clean, production-ready SQL schema.
"""
        
        human_prompt = f"""
User Request: "{user_request}"

Intent Analysis:
- Primary Intent: {intent.get('primary_intent', 'unknown')}
- Entities: {', '.join(intent.get('entities', []))}

Generate MySQL database schema that includes:
1. All necessary tables
2. Proper relationships
3. Appropriate data types
4. Indexes for performance
5. Sample data insertion (optional)

Provide only the SQL code in a code block.
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def get_php_generation_prompt(user_request: str, intent: Dict, sql_schema: str, patterns: List[Dict], standards: Dict) -> Dict[str, str]:
        """
        Prompt for generating PHP backend code
        """
        system_prompt = f"""
You are an expert PHP developer. Generate secure, production-ready PHP code.

STANDARDS TO FOLLOW:
- PHP Version: {standards.get('php_version', '8.0+')}
- Use prepared statements for database queries
- Implement proper error handling
- Follow PSR-12 coding standards
- Include input validation and sanitization
- Use proper security practices (prevent SQL injection, XSS)

🔴 CRITICAL - USE COMPANY'S ACTUAL PATTERNS (EXACT SIGNATURES REQUIRED):

✅ CORRECT COMPANY SIGNATURES (use these exactly):
- db_insert($table, $columns) - CORRECT
- db_update($table, $columns, $filter) - CORRECT
- db_delete($table, $filter) - CORRECT
- db_getRecord($table, $filter) - CORRECT
- getrows($table, $field, $value) - CORRECT (returns row count integer)
- getvalue("SELECT ...") - CORRECT (direct SQL, returns scalar value)
- mysql_fetch_array(db_getRecord(...)) - CORRECT for record binding
- mysql_query("SQL") - CORRECT for complex operations

❌ FORBIDDEN PARAMETERIZED PATTERNS (will fail validation):
- db_update($table, $columns, $filter, $params) - FORBIDDEN
- db_delete($table, $filter, $params) - FORBIDDEN
- getrows("SELECT ...", [$params]) - FORBIDDEN
- db_getRecord($table, $filter, $params) - FORBIDDEN
- getvalue("SELECT ...", [$params]) - FORBIDDEN
- mysqli_query() - FORBIDDEN
- new mysqli() - FORBIDDEN
- new PDO() - FORBIDDEN
- mysqli_fetch_array() - FORBIDDEN

✅ CORRECT SQL PATTERNS:
- Filter strings use concatenation: $filter = " Code='" . add($_REQUEST['code']) . "'"
- Dependencies: $count = getrows($table, $field, add($value))
- Single value: $maxid = getvalue("SELECT MAX(Code)+1 FROM $table WHERE Comp_Code='" . add($comp_code) . "'")
- Record: $obj = db_getRecord($table, $filter) or $obj = mysql_fetch_array(db_getRecord($table, $filter))

⚠️ CRITICAL EXAMPLE - PRE-DELETE DEPENDENCY CHECK:
✅ CORRECT:
    if ( getrows("tbldetail",$filter)>=1)
    {{
        print "<script>alert('This record exists in related table!');</script>";
        exit;
    }}
    db_delete($table, $filter);

❌ WRONG:
    $count = getrows("SELECT * FROM tbldetail WHERE key=?", [$value]);
    db_delete($table, $filter, $params);

COMPANY PATTERNS:
{PromptTemplates._format_patterns(patterns, 'php')}

Generate clean, secure PHP code that handles the user's requirements.

=== 12 ESSENTIAL FORM COMPONENTS (MUST INCLUDE ALL) ===

1. **FORM ROUTING STRUCTURE** - REQUIRED
   - Define $form (list/delete page) and $form2 (current form) at top
   - Handle $_REQUEST['action'] (Update/Delete) and $_POST['txtmode'] (save)
   - Redirect after operations: print "<script>document.location='$form';</script>";

2. **PRE-DELETE DEPENDENCY CHECK** - REQUIRED
   - Before deleting, check if record exists in related tables
   - Example: if ( getrows2("invoice",$filter)>=1) {{ alert and exit }}
   - Prevents orphaned records and data integrity issues

3. **UPDATE VS SAVE LOGIC** - REQUIRED
   - Check if record exists: if ( getrows($table," Code",$value) == '1')
   - If exists: db_update() | If not: db_insert()
   - Different SQL logic for INSERT vs UPDATE

4. **add_Slashes_new() SANITIZATION** - REQUIRED
   - Use add_Slashes_new() for ALL text fields: $columns['NAME'] = add_Slashes_new($_REQUEST['txtname']);
   - Prevents SQL injection and handles special characters
   - Apply to: text inputs, textareas, any user string input

5. **FULL ASSET/PLUGIN STACK** - REQUIRED (in HTML section)
   - Bootstrap CSS/JS, jQuery, Select2, FormValidation, iCheck
   - All required for responsive UI and form functionality

6. **FORMVALIDATION PLUGIN** - REQUIRED (in HTML section)
   - Client-side validation using FormValidation plugin
   - Validates required fields, email format, custom callbacks
   - Prevents invalid data submission

7. **KEYBOARD NAVIGATION LOGIC** - REQUIRED (in JavaScript section)
   - Implement document.onkeydown = checkKeycode
   - Enter key moves focus to next field (Tab replacement)
   - Improves data entry speed and UX

8. **HIDDEN FIELD USAGE PATTERN** - REQUIRED
   - <input type="hidden" id="txtmode" name="txtmode" value="new"> - tracks save/update mode
   - <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action'];?>"> - tracks action
   - Used to differentiate form submission types

9. **TRANSACTION HANDLING SCOPE** - REQUIRED
   - funStartTran() at start of save/update operation
   - funEndTran() at end of operation
   - Ensures data consistency across multiple table inserts/updates

10. **FORM ENCTYPE** - REQUIRED
    - enctype="multipart/form-data" on form tag
    - Required for file uploads and proper form submission

11. **ADVANCED CSS LAYOUT CLASSES** - REQUIRED (in HTML section)
    - form-horizontal, form-group, col-md-*, control-label
    - Bootstrap grid system for responsive layout
    - Used in every form for consistent styling

12. **BROWSER COMPATIBILITY SCRIPTS** - REQUIRED (in HTML section)
    - <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->
    - <!--[if lt IE 10]><script src="media.match.min.js"></script><![endif]-->
    - Required for IE compatibility
"""
        
        human_prompt = f"""
User Request: "{user_request}"

Database Schema:
```sql
{sql_schema}
```

Intent Analysis:
- Primary Intent: {intent.get('primary_intent', 'unknown')}
- Entities: {', '.join(intent.get('entities', []))}

Generate PHP code that includes:
1. Database connection
2. CRUD operations
3. Form processing
4. Input validation
5. Error handling
6. Security measures
7. ALL 12 ESSENTIAL FORM COMPONENTS

Provide only the PHP code in a code block.
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def get_html_generation_prompt(user_request: str, intent: Dict, php_code: str, patterns: List[Dict], standards: Dict) -> Dict[str, str]:
        """
        Prompt for generating HTML frontend code
        """
        system_prompt = f"""
You are an expert frontend developer. Generate semantic, accessible HTML code.

STANDARDS TO FOLLOW:
- Use HTML5 semantic elements
- Include proper ARIA attributes for accessibility
- Ensure proper form structure and validation
- Use responsive design principles
- Include meta tags and proper document structure

COMPANY PATTERNS:
{PromptTemplates._format_patterns(patterns, 'html')}

Generate clean, semantic HTML that works with the PHP backend.

=== 12 ESSENTIAL FORM COMPONENTS (MUST INCLUDE ALL) ===

1. **FORM ROUTING STRUCTURE** - REQUIRED
   - Define $form (list/delete page) and $form2 (current form) at top
   - Handle $_REQUEST['action'] (Update/Delete) and $_POST['txtmode'] (save)
   - Redirect after operations: print "<script>document.location='$form';</script>";

2. **PRE-DELETE DEPENDENCY CHECK** - REQUIRED
   - Before deleting, check if record exists in related tables
   - Example: if ( getrows2("invoice",$filter)>=1) {{ alert and exit }}
   - Prevents orphaned records and data integrity issues

3. **UPDATE VS SAVE LOGIC** - REQUIRED
   - Check if record exists: if ( getrows($table," Code",$value) == '1')
   - If exists: db_update() | If not: db_insert()
   - Different SQL logic for INSERT vs UPDATE

4. **add_Slashes_new() SANITIZATION** - REQUIRED
   - Use add_Slashes_new() for ALL text fields: $columns['NAME'] = add_Slashes_new($_REQUEST['txtname']);
   - Prevents SQL injection and handles special characters
   - Apply to: text inputs, textareas, any user string input

5. **FULL ASSET/PLUGIN STACK** - REQUIRED
   - Include: <link rel="stylesheet" href="global/vendor/formvalidation/formValidation.css">
   - Include: <link rel="stylesheet" href="global/vendor/select2/select2.css">
   - Include: <link rel="stylesheet" href="global/vendor/jquery-datepicker/jquery.datepicker.css">
   - Include: <script src="global/vendor/formvalidation/formValidation.min.js"></script>
   - Include: <script src="global/vendor/select2/select2.min.js"></script>
   - Include: <script src="global/vendor/jquery-datepicker/jquery.datepicker.min.js"></script>
   - Bootstrap CSS/JS, jQuery, Select2, FormValidation, Datepicker, iCheck
   - All required for responsive UI and form functionality

6. **FORMVALIDATION PLUGIN** - REQUIRED
   - Client-side validation using FormValidation plugin
   - Validates required fields, email format, custom callbacks
   - Prevents invalid data submission
   - Initialize: $('#frm').formValidation({ framework: "bootstrap", ... })

7. **KEYBOARD NAVIGATION LOGIC** - REQUIRED (in JavaScript section)
   - Implement document.onkeydown = checkKeycode
   - Enter key moves focus to next field (Tab replacement)
   - Improves data entry speed and UX

8. **HIDDEN FIELD USAGE PATTERN** - REQUIRED
   - <input type="hidden" id="txtmode" name="txtmode" value="new"> - tracks save/update mode
   - <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action'];?>"> - tracks action
   - Used to differentiate form submission types

9. **TRANSACTION HANDLING SCOPE** - REQUIRED
   - funStartTran() at start of save/update operation
   - funEndTran() at end of operation
   - Ensures data consistency across multiple table inserts/updates

10. **FORM ENCTYPE** - REQUIRED
    - <form ... enctype="multipart/form-data" ...>
    - Required for file uploads and proper form submission

11. **ADVANCED CSS LAYOUT CLASSES** - REQUIRED
    - form-horizontal, form-group, col-md-*, control-label
    - Bootstrap grid system for responsive layout
    - Example: <div class="form-group"><label class="col-md-2 control-label">Field:</label><div class="col-md-4">...</div></div>
    - Used in every form for consistent styling

12. **BROWSER COMPATIBILITY SCRIPTS** - REQUIRED
    - <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->
    - <!--[if lt IE 10]><script src="media.match.min.js"></script><![endif]-->
    - Required for IE compatibility
"""
        
        human_prompt = f"""
User Request: "{user_request}"

PHP Backend Code:
```php
{php_code[:1000]}...
```

Intent Analysis:
- Primary Intent: {intent.get('primary_intent', 'unknown')}
- Entities: {', '.join(intent.get('entities', []))}

Generate HTML code that includes:
1. Proper document structure
2. Forms that match PHP processing
3. Semantic HTML5 elements
4. Accessibility features
5. Responsive structure
6. Error message display areas
7. ALL 12 ESSENTIAL FORM COMPONENTS

Provide only the HTML code in a code block.
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def get_css_generation_prompt(user_request: str, intent: Dict, html_code: str, patterns: List[Dict], standards: Dict) -> Dict[str, str]:
        """
        Prompt for generating CSS styling code
        """
        system_prompt = f"""
You are an expert CSS developer. Generate modern, responsive CSS code.

STANDARDS TO FOLLOW:
- CSS Framework: {standards.get('css_framework', 'Custom')}
- Use mobile-first responsive design
- Implement proper color scheme and typography
- Use CSS Grid and Flexbox for layouts
- Include hover states and transitions
- Ensure accessibility (contrast, focus states)

COMPANY PATTERNS:
{PromptTemplates._format_patterns(patterns, 'css')}

Generate clean, modern CSS that styles the HTML beautifully.
"""
        
        human_prompt = f"""
User Request: "{user_request}"

HTML Structure:
```html
{html_code[:1000]}...
```

Intent Analysis:
- Primary Intent: {intent.get('primary_intent', 'unknown')}
- Entities: {', '.join(intent.get('entities', []))}

Generate CSS code that includes:
1. Responsive layout
2. Form styling
3. Button and input styles
4. Color scheme and typography
5. Hover and focus states
6. Mobile-friendly design
7. Loading and error states

Provide only the CSS code in a code block.
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def get_js_generation_prompt(user_request: str, intent: Dict, html_code: str, php_code: str, patterns: List[Dict], standards: Dict) -> Dict[str, str]:
        """
        Prompt for generating JavaScript code
        """
        system_prompt = f"""
You are an expert JavaScript developer. Generate modern, efficient JavaScript code.

STANDARDS TO FOLLOW:
- Use ES6+ syntax
- Implement proper error handling
- Use async/await for API calls
- Include form validation
- Provide user feedback (loading, success, error states)
- Follow modern JavaScript best practices

COMPANY PATTERNS:
{PromptTemplates._format_patterns(patterns, 'js')}

Generate clean, modern JavaScript that enhances the user experience.

=== 12 ESSENTIAL FORM COMPONENTS (MUST INCLUDE ALL) ===

1. **FORM ROUTING STRUCTURE** - REQUIRED
   - Define $form (list/delete page) and $form2 (current form) at top
   - Handle $_REQUEST['action'] (Update/Delete) and $_POST['txtmode'] (save)
   - Redirect after operations: print "<script>document.location='$form';</script>";

2. **PRE-DELETE DEPENDENCY CHECK** - REQUIRED
   - Before deleting, check if record exists in related tables
   - Example: if ( getrows2("invoice",$filter)>=1) {{ alert and exit }}
   - Prevents orphaned records and data integrity issues

3. **UPDATE VS SAVE LOGIC** - REQUIRED
   - Check if record exists: if ( getrows($table," Code",$value) == '1')
   - If exists: db_update() | If not: db_insert()
   - Different SQL logic for INSERT vs UPDATE

4. **add_Slashes_new() SANITIZATION** - REQUIRED
   - Use add_Slashes_new() for ALL text fields: $columns['NAME'] = add_Slashes_new($_REQUEST['txtname']);
   - Prevents SQL injection and handles special characters
   - Apply to: text inputs, textareas, any user string input

5. **FULL ASSET/PLUGIN STACK** - REQUIRED
   - Include: <script src="global/vendor/formvalidation/formValidation.min.js"></script>
   - Include: <script src="global/vendor/formvalidation/framework/bootstrap.min.js"></script>
   - Include Bootstrap CSS/JS, jQuery, Select2, FormValidation, iCheck
   - All required for responsive UI and form functionality

6. **FORMVALIDATION PLUGIN** - REQUIRED
   - Client-side validation using FormValidation plugin
   - Validates required fields, email format, custom callbacks
   - Prevents invalid data submission
   - Initialize FormValidation with framework bootstrap

7. **KEYBOARD NAVIGATION LOGIC** - REQUIRED
   - Implement document.onkeydown = checkKeycode
   - Enter key moves focus to next field (Tab replacement)
   - Improves data entry speed and UX
   - Example: if(keycode == 13 && field == 'fieldName') {{ document.getElementById('nextField').focus(); }}

8. **HIDDEN FIELD USAGE PATTERN** - REQUIRED
   - <input type="hidden" id="txtmode" name="txtmode" value="new"> - tracks save/update mode
   - <input type="hidden" name="CTRL_HID_VALUE" id="CTRL_HID_VALUE" value="<?php echo $_REQUEST['action'];?>"> - tracks action
   - Used to differentiate form submission types

9. **TRANSACTION HANDLING SCOPE** - REQUIRED
   - funStartTran() at start of save/update operation
   - funEndTran() at end of operation
   - Ensures data consistency across multiple table inserts/updates

10. **FORM ENCTYPE** - REQUIRED
    - <form ... enctype="multipart/form-data" ...>
    - Required for file uploads and proper form submission

11. **ADVANCED CSS LAYOUT CLASSES** - REQUIRED
    - form-horizontal, form-group, col-md-*, control-label
    - Bootstrap grid system for responsive layout
    - Used in every form for consistent styling

12. **BROWSER COMPATIBILITY SCRIPTS** - REQUIRED
    - <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->
    - <!--[if lt IE 10]><script src="media.match.min.js"></script><![endif]-->
    - Required for IE compatibility
"""
        
        human_prompt = f"""
User Request: "{user_request}"

HTML Structure:
```html
{html_code[:500]}...
```

PHP Backend:
```php
{php_code[:500]}...
```

Intent Analysis:
- Primary Intent: {intent.get('primary_intent', 'unknown')}
- Entities: {', '.join(intent.get('entities', []))}

Generate JavaScript code that includes:
1. Form validation
2. AJAX/Fetch API calls
3. User feedback (loading, success, error)
4. DOM manipulation
5. Event handlers
6. Error handling
7. Keyboard navigation (Enter key moves to next field)
8. ALL 12 ESSENTIAL FORM COMPONENTS

Provide only the JavaScript code in a code block.
"""
        
        return {
            'system': system_prompt,
            'human': human_prompt
        }
    
    @staticmethod
    def _format_patterns(patterns: List[Dict], language: str) -> str:
        """
        Format retrieved patterns for inclusion in prompts
        """
        if not patterns:
            return "No specific company patterns available."
        
        formatted_patterns = []
        for pattern in patterns[:3]:  # Limit to top 3 patterns
            if pattern.get('language') == language:
                formatted_patterns.append(f"""
Pattern: {pattern.get('description', 'Code pattern')}
```{language}
{pattern.get('code', '')[:500]}...
```
""")
        
        if not formatted_patterns:
            return f"No {language} patterns available."
        
        return "\n".join(formatted_patterns)