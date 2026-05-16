"""
ENTERPRISE-GRADE Dynamic Prompt Builder
Uses ACTUAL company codebase examples - NO dummy patterns, NO metadata-only
Shows complete code examples to LLM for accurate pattern matching
"""

from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class DynamicPromptBuilder:
    """
    Builds code generation prompts using ACTUAL company code examples
    CRITICAL: Shows real code structure, not just function names
    """
    
    @staticmethod
    def build_php_prompt(analyzed_patterns: Dict, intent: Dict, sql_schema: str, 
                        php_patterns: str, php_standards: str) -> str:
        """
        🆕 ENHANCED: Build PHP generation prompt with CRITICAL PATTERNS FIRST
        
        ENTERPRISE APPROACH:
        1. Extract 12 ESSENTIAL patterns from analyzed_patterns
        2. Show COMPLETE examples with actual code
        3. Make patterns MANDATORY with clear instructions
        4. Reduce prompt size by focusing on essentials
        """
        
        import json
        
        # Format intent for display
        intent_str = json.dumps(intent, indent=2)
        
        # 🆕 EXTRACT 12 ESSENTIAL PATTERNS from analyzed_patterns
        php_analyzed = analyzed_patterns.get('php', {})
        
        ajax_auto_id = php_analyzed.get('ajax_auto_id', [])
        delete_checks = php_analyzed.get('delete_checks', [])
        chart_integration = php_analyzed.get('chart_integration', [])
        conditional_logic = php_analyzed.get('conditional_logic', {})
        dynamic_dropdowns = php_analyzed.get('dynamic_dropdowns', [])
        formvalidation = php_analyzed.get('formvalidation', {})
        keyboard_nav = php_analyzed.get('keyboard_navigation', {})
        grid_patterns = php_analyzed.get('grid_patterns', [])
        disabled_fields = php_analyzed.get('disabled_fields', [])
        asset_loading = php_analyzed.get('asset_loading', {})
        php_includes = php_analyzed.get('php_includes', [])
        
        # ESCAPE CURLY BRACES for PromptTemplate
        safe_php_patterns = php_patterns.replace('{', '{{').replace('}', '}}')
        safe_intent_str = intent_str.replace('{', '{{').replace('}', '}}')
        safe_sql_schema = sql_schema.replace('{', '{{').replace('}', '}}')
        safe_php_standards = php_standards.replace('{', '{{').replace('}', '}}')
        
        # 🆕 BUILD FOCUSED PROMPT with CRITICAL PATTERNS FIRST
        prompt = f"""=== ENTERPRISE CODE GENERATION: CRITICAL PATTERNS MANDATORY ===

You are generating PHP code for a company with SPECIFIC patterns.
Below are the MANDATORY patterns you MUST include.

=== 🔥 PATTERN #1: AJAX AUTO-ID GENERATION (MANDATORY) ===

**Company's Actual Code:**
```php
{ajax_auto_id[0]['code'] if ajax_auto_id else '''if($_REQUEST['Action']=='GetMaxID') {{
    $MAXID = getvalue("SELECT IFNULL(MAX(id),0)+1 as Code FROM table WHERE comp_code='".$_SESSION['comp_code']."'");
    echo $MAXID;
    exit;
}}'''}
```

**JavaScript Function:**
```javascript
function maxid() {{
    var area = $('#Main_Area').val();
    $.post(form, {{Action:'GetMaxID', SelectArea: area}}, function(data) {{
        $('#CUST_Id').val(data);
    }});
}}
```

**HTML onChange:**
```html
<select id="Main_Area" onChange="maxid();">
```

⚠️ THIS IS MANDATORY - YOU MUST INCLUDE THIS EXACT PATTERN!

=== 🔥 PATTERN #2: DYNAMIC DROPDOWN POPULATION (MANDATORY IF DROPDOWN MENTIONED) ===

**Company's Actual Code:**
```php
{dynamic_dropdowns[0]['code'] if dynamic_dropdowns else '''if($_REQUEST['areaId']) {{
    $sql = mysql_query("SELECT Code, Description FROM tblsubarea WHERE Country_Code='".$_REQUEST['areaId']."'");
    while($row = mysql_fetch_array($sql)) {{
        $array_[] = array('Code' => $row['Code'], 'Description' => $row['Description']);
    }}
    echo json_encode($array_);
    exit;
}}'''}
```

**JavaScript Function:**
```javascript
function SubArea() {{
    $.ajax({{
        url: form,
        data: {{ areaId: $('#Main_Area').val() }},
        success: function(msg) {{
            var data = JSON.parse(msg);
            $('#Sub_Area').empty();
            $.each(data, function(i, item) {{
                $('#Sub_Area').append($('<option>', {{ value: item.Code, text: item.Description }}));
            }});
        }}
    }});
}}
```

⚠️ MANDATORY IF USER MENTIONED DROPDOWN/CASCADE!

=== 🔥 PATTERN #3: PRE-DELETE DEPENDENCY CHECK (MANDATORY) ===

**Company's Actual Code:**
```php
{delete_checks[0]['check_code'] if delete_checks else '''if(getrows2("invoice", $filter) >= 1) {{
    print "<script>alert('This Customer Exists in Invoice. Cannot Delete!');</script>";
    exit;
}}'''}
```

⚠️ ALWAYS CHECK DEPENDENCIES BEFORE DELETE!

=== 🔥 PATTERN #4: CHART OF ACCOUNTS INTEGRATION (MANDATORY) ===

**Company's Actual Code:**
```php
{chart_integration[0]['code'] if chart_integration and len(chart_integration) > 0 else '''// Generate ACC_CODE
$don = ACC_CUST . $_REQUEST['CUST_Id'];

// INSERT into chart
$sql = "INSERT INTO chart (ACC_CODE, ACC_NAME, GRP_DET, LEVEL, comp_code) 
        VALUES ('$don', '".$_REQUEST['CUST_Name']."', 'D', '4', '".$_SESSION['comp_code']."')";
mysql_query($sql);

// UPDATE chart
$sql = "UPDATE chart SET ACC_NAME='".$_REQUEST['CUST_Name']."' WHERE ACC_CODE='$don'";

// DELETE from chart
$sql = "DELETE FROM chart WHERE ACC_CODE='$don'";'''}
```

⚠️ MANDATORY FOR CUSTOMER/SUPPLIER FORMS!

=== 🔥 PATTERN #5: CONDITIONAL CODE (UPDATE VS INSERT) ===

**Company's Actual Code:**
```php
{conditional_logic.get('update_logic', ['''if(getrows($table, " Code", $Code) == '1') {{
    // UPDATE
    db_update($table, $columns, $filter);
    fun_log($table, $Code, "Update", $_SESSION['login_id']);
    print "<script>alert(MSG_REC_UPDATED);</script>";
}} else {{
    // INSERT
    db_insert($table, $columns);
    fun_log($table, $Code, "Save", $_SESSION['login_id']);
    print "<script>alert(MSG_REC_SAVED);</script>";
}}'''])[0]}
```

⚠️ ALWAYS CHECK IF RECORD EXISTS BEFORE INSERT/UPDATE!

=== COMPANY'S COMPLETE PHP CODE EXAMPLES ===

{safe_php_patterns}

=== END OF COMPANY EXAMPLES ===

=== YOUR TASK ===

User Request:
{safe_intent_str}

Database Schema:
```sql
{safe_sql_schema}
```

Company Coding Standards:
{safe_php_standards}

=== ✅ CRITICAL INSTRUCTIONS (FOLLOW EXACTLY) ===

1. **INCLUDE ALL 5 MANDATORY PATTERNS ABOVE**
   - Pattern #1: AJAX Auto-ID (ALWAYS)
   - Pattern #2: Dynamic Dropdowns (IF user mentioned dropdown)
   - Pattern #3: Pre-Delete Checks (ALWAYS)
   - Pattern #4: Chart Integration (IF customer/supplier form)
   - Pattern #5: Conditional Logic (ALWAYS)

2. **USE COMPANY'S EXACT FUNCTIONS**:
   - funStartTran() / funEndTran() for transactions
   - db_insert($table, $columns) for inserts
   - db_update($table, $columns, $filter) for updates
   - db_delete($table, $filter) for deletes
   - getrows($table, $field, $value) for checking existence
   - getrows2($table, $filter) for dependency checks
   - getvalue($sql) for single value queries
   - fun_log($table, $code, $action, $user) for logging

3. **USE COMPANY'S VARIABLE PATTERNS**:
   - $columns array for database fields
   - $filter for WHERE clauses
   - $table for table name
   - $Code for primary key
   - $_SESSION['comp_code'], $_SESSION['user_id'], $_SESSION['login_id']

4. **FOLLOW FORM PROCESSING PATTERN**:
   ```php
   @session_start();
   include("include/config.inc.php");
   
   // AJAX Handlers FIRST
   if($_REQUEST['Action']=='GetMaxID') {{ ... }}
   if($_REQUEST['areaId']) {{ ... }}
   
   // Form Processing
   if(isset($_POST["txtmode"]) and $_POST["txtmode"]=="save") {{
       funStartTran();
       
       $columns['Field1'] = add_Slashes_new($_REQUEST['Field1']);
       $columns['comp_code'] = $_SESSION['comp_code'];
       
       if(getrows($table," Code",$Code) == '1') {{
           db_update($table,$columns,$filter);
           fun_log($table,$Code,"Update",$_SESSION['login_id']);
       }} else {{
           db_insert($table,$columns);
           fun_log($table,$Code,"Save",$_SESSION['login_id']);
       }}
       
       funEndTran();
   }}
   
   // Delete with dependency check
   if(isset($_POST["txtmode"]) and $_POST["txtmode"]=="delete") {{
       if(getrows2("related_table",$filter)>=1) {{
           print "<script>alert('Cannot delete - record exists in related table');</script>";
           exit;
       }}
       db_delete($table,$filter);
   }}
   ```

5. **CRITICAL RULES**:
   - Start with @session_start()
   - Include config.inc.php at top
   - AJAX handlers BEFORE form processing
   - Use company's database functions (NOT raw mysqli/PDO)
   - Add logging with fun_log()
   - Use company's message constants (MSG_REC_SAVED, MSG_REC_UPDATED)
   - Check dependencies before delete
   - Use transactions for multi-table operations

=== ⚠️ VALIDATION CHECKLIST ===

Before returning code, verify:
- [ ] AJAX Auto-ID handler present (if($_REQUEST['Action']=='GetMaxID'))
- [ ] Dynamic dropdown handler present (if user mentioned dropdown)
- [ ] Pre-delete dependency check present
- [ ] Chart of accounts integration (if customer/supplier)
- [ ] Conditional update vs insert logic
- [ ] Uses funStartTran() and funEndTran()
- [ ] Uses db_insert(), db_update(), db_delete()
- [ ] Uses getrows() for existence check
- [ ] Uses $_SESSION['comp_code']
- [ ] Includes fun_log() calls

=== 📋 ADDITIONAL PATTERNS (INCLUDE IF APPLICABLE) ===

6. **FORMVALIDATION.JS FRAMEWORK** (if validation needed)
   - Initialize: $('#frm').formValidation({{ framework: "bootstrap", fields: {{ ... }} }});

7. **KEYBOARD NAVIGATION** (if mentioned)
   - document.onkeydown = checkKeycode;
   - if(keycode == 13 && field == 'field1') {{ document.getElementById('field2').focus(); }}

8. **GRID/TABLE PATTERNS** (if detail records needed)
   - for($i=0;$i<=$_REQUEST['TXTCOUNT'];$i++) {{ ... }}
   - <input name="field<?php echo $i;?>">

9. **DISABLED FIELD HANDLING** (if update mode)
   - document.getElementById('field').disabled=false; before submit
   - <select disabled <?php if($_REQUEST['action']=='Update') echo "disabled"; ?>>

10. **COMPLETE ASSET LOADING**
    - CSS: bootstrap.min.css, site.min.css, formValidation.css
    - JS: jquery.js, bootstrap.js, formValidation.min.js

11. **PHP INCLUDE FILES**
    - include("include/config.inc.php");
    - <?php include("include/formheader.php"); ?>
    - <?php include("include/topmenu.php"); ?>
    - <?php include("include/sidemenu.php"); ?>
    - <?php include("include/footer.php"); ?>

12. **TRANSACTION MANAGEMENT**
    - funStartTran(); at start
    - All db operations
    - funEndTran(); at end$' }} }} }}
   - Custom callbacks: callback: {{ callback: function(value, validator, $field) {{ return validation logic; }} }}
   - Success handler: .on('success.form.fv', function(e) {{ e.preventDefault(); btnsave_click(); }});

7. **KEYBOARD NAVIGATION (Enter Key)** - REQUIRED
   - Function: document.onkeydown = checkKeycode; function checkKeycode(e,field) {{ var keycode; if(window.event) keycode=window.event.keyCode; else if(e) keycode=e.which; }}
   - Field mapping: if(keycode == 13 && field == 'Main_Area') {{ document.getElementById('Sub_Area').focus(); }}
   - HTML attribute: onKeyDown="checkKeycode(event,this.id);"
   - Map ALL fields in sequence for data entry speed

8. **GRID/TABLE FOR DETAIL RECORDS** - REQUIRED
   - PHP Loop: for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++) {{ if($_REQUEST['SR_NO'.$i]!='') {{ $columns['SR_NO']=$_REQUEST['SR_NO'.$i]; db_insert($sub_table,$columns); }} }}
   - HTML Grid: <input name="txtField<?php echo $sr;?>" id="txtField<?php echo $sr;?>">
   - Checkbox: <input type="checkbox" name="Edit<?php echo $sr;?>" value="1">
   - Hidden counter: <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="<?php echo $sr;?>">

9. **TRANSACTION MANAGEMENT** - REQUIRED
   - Start: funStartTran(); at beginning of save/update block
   - Operations: db_insert(), db_update(), db_delete() within transaction
   - End: funEndTran(); after all operations complete
   - Ensures atomicity across multiple table operations

10. **DISABLED FIELD HANDLING** - REQUIRED
    - Enable before submit: document.getElementById('Main_Area').disabled=false; in btnsave_click()
    - HTML disabled: <Select disabled <? if($_REQUEST['action']=='Update') {{ echo "disabled='disabled'"; }} ?>>
    - Re-enable ALL disabled fields before form submission

11. **COMPLETE ASSET LOADING** - REQUIRED
    - CSS: bootstrap.min.css, bootstrap-extend.min.css, site.min.css, select2.css, formValidation.css, icheck.css
    - JS: jquery.js, bootstrap.js, select2.min.js, formValidation.min.js, icheck.min.js, funJs.js
    - Plugins: data-plugin="select2", data-plugin="datepicker"
    - IE Compatibility: <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->

12. **PHP INCLUDE FILES** - REQUIRED
    - Config: include("include/config.inc.php"); at top
    - Header: <?php include("include/formheader.php"); ?> after page div
    - Menu: <?php include("include/topmenu.php");?> at body start
    - Sidebar: <?php include("include/sidemenu.php");?> after topmenu
    - Footer: <?php include("include/footer.php");?> before scripts

=== CRITICAL INSTRUCTIONS ===

1. **COPY THE STRUCTURE** - Look at the company examples above and copy:
   - Session management pattern (e.g., @session_start())
   - Include statements (e.g., include("include/config.inc.php"))
   - Variable naming (e.g., $columns['FieldName'])
   - Database functions (e.g., funStartTran(), db_insert(), funEndTran())
   - Error handling patterns
   - Form processing structure

2. **USE COMPANY'S FUNCTIONS** - From the examples above, use:
   - funStartTran() / funEndTran() for transactions
   - db_insert($table, $columns) for inserts
   - db_update($table, $columns, $filter) for updates
   - db_delete($table, $filter) for deletes
   - getrows($table, $field, $value) for checking existence
   - add_Slashes_new() for escaping strings
   - db_dateFormat() for date formatting
   - fun_log() for logging operations

3. **MATCH VARIABLE PATTERNS** - Use the same variable structure:
   - $columns array for database fields
   - $filter for WHERE clauses
   - $table for table name
   - $Code for primary key
   - $_SESSION['comp_code'], $_SESSION['user_id'], $_SESSION['login_id']

4. **FOLLOW FORM PROCESSING PATTERN**:
   ```php
   if ( isset($_POST["txtmode"]) and $_POST["txtmode"]=="save")
   {{{{
       funStartTran();
       
       // Build $columns array
       $columns['Field1'] = value1;
       $columns['Field2'] = value2;
       
       // Check if update or insert
       if ( getrows($table," Code",$value) == '1')
       {{{{
           db_update($table,$columns,$filter);
       }}}}
       else
       {{{{
           db_insert($table,$columns);
       }}}}
       
       funEndTran();
   }}}}
   ```

5. **CRITICAL RULES**:
   - Start with @session_start()
   - Include config.inc.php
   - Use company's database functions
   - Use company's variable naming conventions
   - Add logging with fun_log()
   - Use company's message constants (MSG_REC_SAVED, MSG_REC_UPDATED)
   - INCLUDE ALL 12 ESSENTIAL COMPONENTS

=== OUTPUT REQUIREMENTS ===

Generate ONLY the PHP code in a code block.
The code MUST include ALL 5 MANDATORY PATTERNS listed above.
The code MUST look like it was written by the same developer who wrote the company examples.
DO NOT use generic PHP patterns - COPY the company's style exactly.

```php
// Your generated code here - MUST INCLUDE ALL MANDATORY PATTERNS
```
"""
        
        return prompt
    
    @staticmethod
    def _extract_php_examples(php_patterns: str) -> List[str]:
        """
        Extract individual PHP code examples from patterns string
        Returns list of complete code examples
        """
        examples = []
        
        # Split by code block markers
        if "```php" in php_patterns:
            blocks = php_patterns.split("```php")
            for block in blocks[1:]:  # Skip first (before first ```)
                if "```" in block:
                    code = block.split("```")[0].strip()
                    if code and len(code) > 100:  # Only substantial examples
                        examples.append(code)
        
        return examples[:5]  # Return top 5 examples
    
    @staticmethod
    def build_html_prompt(analyzed_patterns: Dict, intent: Dict, html_patterns: str, 
                         html_standards: str, form_fields_html: str) -> str:
        """
        Build HTML generation prompt using ACTUAL company code examples
        NO escaping - shows real HTML structure to LLM
        """
        
        import json
        intent_str = json.dumps(intent, indent=2)
        
        # Handle None values
        html_patterns = html_patterns or "<!-- No HTML patterns available -->"
        html_standards = html_standards or "<!-- No HTML standards available -->"
        form_fields_html = form_fields_html or "<!-- No form fields available -->"
        
        # ESCAPE for template safety
        safe_html_patterns = html_patterns.replace('{', '{{').replace('}', '}}')
        safe_intent_str = intent_str.replace('{', '{{').replace('}', '}}')
        safe_form_fields_html = form_fields_html.replace('{', '{{').replace('}', '}}')
        safe_html_standards = html_standards.replace('{', '{{').replace('}', '}}')
        
        prompt = f"""=== ENTERPRISE CODE GENERATION: USE COMPANY'S ACTUAL HTML STRUCTURE ===

You are generating HTML for a company with a SPECIFIC form structure.
Below are REAL examples from their codebase. You MUST copy this structure EXACTLY.

=== COMPANY'S ACTUAL HTML CODE EXAMPLES ===

{safe_html_patterns}

=== END OF COMPANY EXAMPLES ===

=== YOUR TASK ===

User Request:
{safe_intent_str}

Form Fields Required:
{safe_form_fields_html}

Company Standards:
{safe_html_standards}

=== 12 ESSENTIAL FORM COMPONENTS (MUST INCLUDE ALL) ===

1. **AJAX AUTO-ID GENERATION** - REQUIRED
   - PHP Handler: if($_REQUEST['Action']=='GetMaxID') {{ $MAXID=getvalue("SELECT MAX..."); echo $MAXID; exit; }}
   - JavaScript: function maxid() {{ $.post(form, {{Action:'GetMaxID', SelectArea: area}}, function(data) {{ $('#CUST_Id').val(data); }}); }}
   - Call on Area change: onChange="maxid();"
   - Pattern from company: GetMaxID, GetCOSTCENTER handlers

2. **PRE-DELETE DEPENDENCY CHECK** - REQUIRED
   - Before deleting, check if record exists in related tables
   - Example: if ( getrows2("invoice",$filter)>=1) {{ alert and exit }}
   - Prevents orphaned records and data integrity issues

3. **CHART OF ACCOUNTS INTEGRATION** - REQUIRED
   - Generate ACC_CODE: $don = ACC_CUST.CustomerCode($_REQUEST['CUST_Id']);
   - INSERT: INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL) VALUES (...)
   - UPDATE: UPDATE chart SET ACC_NAME='...' WHERE ACC_CODE='...'
   - DELETE: delete from chart where ACC_CODE='...'
   - Pattern from company: ACC_CUST prefix, GRP_DET='D', LEVEL='4'

4. **CONDITIONAL CODE GENERATION (Update vs Insert)** - REQUIRED
   - Check if record exists: if ( getrows($table," Code",$value) == '1')
   - If exists: db_update() | If not: db_insert()
   - Different SQL logic for INSERT vs UPDATE

5. **DYNAMIC DROPDOWN POPULATION** - REQUIRED
   - PHP Handler: if($_REQUEST['bnkId']) {{ $sql=mysql_query("SELECT Code,Description FROM tblsubarea WHERE Country_Code='".$_REQUEST['bnkId']."'"); echo json_encode($array_); exit; }}
   - JavaScript: function SubArea() {{ $.ajax({{ url:form, data:{{ bnkId: $('#Main_Area').val() }}, success: function(msg) {{ populate dropdown }} }}); }}
   - onChange binding: <Select onChange="SubArea();">
   - Cascade pattern: Area → SubArea → Salesman

6. **FORMVALIDATION.JS FRAMEWORK** - REQUIRED
   - Initialize: $('#frm').formValidation({{ framework: "bootstrap", button: {{ selector: '#btnSave', disabled: 'disabled' }}, fields: {{ ... }} }});
   - Field validators: fieldName: {{ validators: {{ notEmpty: {{ message: '...' }}, regexp: {{ regexp: '^pattern$' }} }} }}
   - Custom callbacks: callback: {{ callback: function(value, validator, $field) {{ return validation logic; }} }}
   - Success handler: .on('success.form.fv', function(e) {{ e.preventDefault(); btnsave_click(); }});

7. **KEYBOARD NAVIGATION (Enter Key)** - REQUIRED
   - Function: document.onkeydown = checkKeycode; function checkKeycode(e,field) {{ var keycode; if(window.event) keycode=window.event.keyCode; else if(e) keycode=e.which; }}
   - Field mapping: if(keycode == 13 && field == 'Main_Area') {{ document.getElementById('Sub_Area').focus(); }}
   - HTML attribute: onKeyDown="checkKeycode(event,this.id);"
   - Map ALL fields in sequence for data entry speed

8. **GRID/TABLE FOR DETAIL RECORDS** - REQUIRED
   - PHP Loop: for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++) {{ if($_REQUEST['SR_NO'.$i]!='') {{ $columns['SR_NO']=$_REQUEST['SR_NO'.$i]; db_insert($sub_table,$columns); }} }}
   - HTML Grid: <input name="txtField<?php echo $sr;?>" id="txtField<?php echo $sr;?>">
   - Checkbox: <input type="checkbox" name="Edit<?php echo $sr;?>" value="1">
   - Hidden counter: <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="<?php echo $sr;?>">

9. **TRANSACTION MANAGEMENT** - REQUIRED
   - Start: funStartTran(); at beginning of save/update block
   - Operations: db_insert(), db_update(), db_delete() within transaction
   - End: funEndTran(); after all operations complete
   - Ensures atomicity across multiple table operations

10. **DISABLED FIELD HANDLING** - REQUIRED
    - Enable before submit: document.getElementById('Main_Area').disabled=false; in btnsave_click()
    - HTML disabled: <Select disabled <? if($_REQUEST['action']=='Update') {{ echo "disabled='disabled'"; }} ?>>
    - Re-enable ALL disabled fields before form submission

11. **COMPLETE ASSET LOADING** - REQUIRED
    - CSS: bootstrap.min.css, bootstrap-extend.min.css, site.min.css, select2.css, formValidation.css, icheck.css
    - JS: jquery.js, bootstrap.js, select2.min.js, formValidation.min.js, icheck.min.js, funJs.js
    - Plugins: data-plugin="select2", data-plugin="datepicker"
    - IE Compatibility: <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->

12. **PHP INCLUDE FILES** - REQUIRED
    - Config: include("include/config.inc.php"); at top
    - Header: <?php include("include/formheader.php"); ?> after page div
    - Menu: <?php include("include/topmenu.php");?> at body start
    - Sidebar: <?php include("include/sidemenu.php");?> after topmenu
    - Footer: <?php include("include/footer.php");?> before scripts

=== CRITICAL INSTRUCTIONS ===

1. **COPY THE FORM STRUCTURE** - From examples above, use:
   - Same DOCTYPE and HTML structure
   - Same CSS/JS includes
   - Same form attributes (method, id, class)
   - Same input field structure
   - Same button structure

2. **USE COMPANY'S CSS CLASSES** - From examples, use classes like:
   - form-control
   - form-group
   - btn, btn-primary
   - panel, panel-body
   - row, col-md-*

3. **MATCH INPUT NAMING** - Use company's naming convention:
   - Check if company uses UPPERCASE (name="TXTFIELD") or camelCase
   - Use same prefix patterns (TXT, CMB, CHK, etc.)
   - Follow exact naming from examples

4. **INCLUDE REQUIRED ELEMENTS**:
   - Hidden fields for mode/action
   - Proper labels with for attributes
   - Required field indicators
   - Form validation attributes
   - Form enctype="multipart/form-data"
   - Bootstrap layout classes

5. **FOLLOW COMPANY'S LAYOUT**:
   - Use same grid system (Bootstrap columns)
   - Same spacing and structure
   - Same button placement
   - Same field grouping

6. **INCLUDE ALL ASSETS**:
   - Bootstrap CSS/JS
   - jQuery
   - Select2
   - FormValidation
   - iCheck
   - Browser compatibility scripts

=== OUTPUT REQUIREMENTS ===

Generate ONLY the HTML code in a code block.
The HTML MUST look like it was written by the same developer who wrote the examples above.
DO NOT use generic Bootstrap templates - COPY the company's exact structure.
ENSURE ALL 12 ESSENTIAL COMPONENTS ARE INCLUDED.

```html
<!-- Your generated HTML here -->
```
"""
        
        return prompt
    
    @staticmethod
    def build_css_prompt(analyzed_patterns: Dict, intent: Dict, css_patterns: str,
                        css_standards: str, html_code: str) -> str:
        """
        Build CSS generation prompt using ACTUAL company code examples
        NO escaping - shows real CSS to LLM
        """
        
        import json
        intent_str = json.dumps(intent, indent=2)
        
        # Handle None values
        css_patterns = css_patterns or "/* No CSS patterns available */"
        css_standards = css_standards or "/* No CSS standards available */"
        html_code = html_code or "<!-- No HTML code available -->"
        
        # ESCAPE for template safety
        safe_css_patterns = css_patterns.replace('{', '{{').replace('}', '}}')
        safe_intent_str = intent_str.replace('{', '{{').replace('}', '}}')
        safe_html_code = html_code.replace('{', '{{').replace('}', '}}')
        safe_css_standards = css_standards.replace('{', '{{').replace('}', '}}')
        
        prompt = f"""=== ENTERPRISE CODE GENERATION: USE COMPANY'S ACTUAL CSS STYLES ===

You are generating CSS for a company with a SPECIFIC design system.
Below are REAL examples from their codebase. You MUST copy this styling EXACTLY.

=== COMPANY'S ACTUAL CSS CODE EXAMPLES ===

{safe_css_patterns}

=== END OF COMPANY EXAMPLES ===

=== YOUR TASK ===

User Request:
{safe_intent_str}

HTML Structure to Style:
```html
{safe_html_code}
```

Company Standards:
{safe_css_standards}

=== CRITICAL INSTRUCTIONS ===

1. **COPY THE COLOR SCHEME** - From examples above, use:
   - Same primary colors
   - Same background colors
   - Same border colors
   - Same hover/focus states

2. **USE COMPANY'S TYPOGRAPHY**:
   - Same font families
   - Same font sizes
   - Same font weights
   - Same line heights

3. **MATCH SPACING PATTERNS**:
   - Same margin/padding values
   - Same spacing units (px, rem, em)
   - Same layout spacing

4. **FOLLOW COMPANY'S COMPONENT STYLES**:
   - Form input styles
   - Button styles
   - Panel/card styles
   - Table styles

5. **USE COMPANY'S CLASS NAMING**:
   - Follow same naming conventions
   - Use same prefixes/suffixes
   - Match class structure

=== OUTPUT REQUIREMENTS ===

Generate ONLY the CSS code in a code block.
The CSS MUST match the company's design system shown in examples above.
DO NOT use generic styles - COPY the company's exact styling patterns.

```css
/* Your generated CSS here */
```
"""
        
        return prompt
    
    @staticmethod
    def build_js_prompt(analyzed_patterns: Dict, intent: Dict, html_code: str,
                       js_patterns: str, js_standards: str, api_endpoint: str) -> str:
        """
        Build JavaScript generation prompt using ACTUAL company code examples
        NO escaping - shows real JavaScript to LLM
        """
        
        import json
        intent_str = json.dumps(intent, indent=2)
        
        # Handle None values
        js_patterns = js_patterns or "/* No JavaScript patterns available */"
        js_standards = js_standards or "/* No JavaScript standards available */"
        html_code = html_code or "<!-- No HTML code available -->"
        api_endpoint = api_endpoint or "/api/default"
        
        # ESCAPE for template safety
        safe_js_patterns = js_patterns.replace('{', '{{').replace('}', '}}')
        safe_intent_str = intent_str.replace('{', '{{').replace('}', '}}')
        safe_html_code = html_code.replace('{', '{{').replace('}', '}}')
        safe_js_standards = js_standards.replace('{', '{{').replace('}', '}}')
        
        prompt = f"""=== ENTERPRISE CODE GENERATION: USE COMPANY'S ACTUAL JAVASCRIPT PATTERNS ===

You are generating JavaScript for a company with SPECIFIC coding patterns.
Below are REAL examples from their codebase. You MUST copy this structure EXACTLY.

=== COMPANY'S ACTUAL JAVASCRIPT CODE EXAMPLES ===

{safe_js_patterns}

=== END OF COMPANY EXAMPLES ===

=== YOUR TASK ===

User Request:
{safe_intent_str}

HTML Structure:
```html
{safe_html_code}
```

API Endpoint: {api_endpoint}

Company Standards:
{safe_js_standards}

=== 12 ESSENTIAL FORM COMPONENTS (MUST INCLUDE ALL) ===

1. **AJAX AUTO-ID GENERATION** - REQUIRED
   - PHP Handler: if($_REQUEST['Action']=='GetMaxID') {{ $MAXID=getvalue("SELECT MAX..."); echo $MAXID; exit; }}
   - JavaScript: function maxid() {{ $.post(form, {{Action:'GetMaxID', SelectArea: area}}, function(data) {{ $('#CUST_Id').val(data); }}); }}
   - Call on Area change: onChange="maxid();"
   - Pattern from company: GetMaxID, GetCOSTCENTER handlers

2. **PRE-DELETE DEPENDENCY CHECK** - REQUIRED
   - Before deleting, check if record exists in related tables
   - Example: if ( getrows2("invoice",$filter)>=1) {{ alert and exit }}
   - Prevents orphaned records and data integrity issues

3. **CHART OF ACCOUNTS INTEGRATION** - REQUIRED
   - Generate ACC_CODE: $don = ACC_CUST.CustomerCode($_REQUEST['CUST_Id']);
   - INSERT: INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL) VALUES (...)
   - UPDATE: UPDATE chart SET ACC_NAME='...' WHERE ACC_CODE='...'
   - DELETE: delete from chart where ACC_CODE='...'
   - Pattern from company: ACC_CUST prefix, GRP_DET='D', LEVEL='4'

4. **CONDITIONAL CODE GENERATION (Update vs Insert)** - REQUIRED
   - Check if record exists: if ( getrows($table," Code",$value) == '1')
   - If exists: db_update() | If not: db_insert()
   - Different SQL logic for INSERT vs UPDATE

5. **DYNAMIC DROPDOWN POPULATION** - REQUIRED
   - PHP Handler: if($_REQUEST['bnkId']) {{ $sql=mysql_query("SELECT Code,Description FROM tblsubarea WHERE Country_Code='".$_REQUEST['bnkId']."'"); echo json_encode($array_); exit; }}
   - JavaScript: function SubArea() {{ $.ajax({{ url:form, data:{{ bnkId: $('#Main_Area').val() }}, success: function(msg) {{ populate dropdown }} }}); }}
   - onChange binding: <Select onChange="SubArea();">
   - Cascade pattern: Area → SubArea → Salesman

6. **FORMVALIDATION.JS FRAMEWORK** - REQUIRED
   - Initialize: $('#frm').formValidation({{ framework: "bootstrap", button: {{ selector: '#btnSave', disabled: 'disabled' }}, fields: {{ ... }} }});
   - Field validators: fieldName: {{ validators: {{ notEmpty: {{ message: '...' }}, regexp: {{ regexp: '^pattern$' }} }} }}
   - Custom callbacks: callback: {{ callback: function(value, validator, $field) {{ return validation logic; }} }}
   - Success handler: .on('success.form.fv', function(e) {{ e.preventDefault(); btnsave_click(); }});

7. **KEYBOARD NAVIGATION (Enter Key)** - REQUIRED
   - Function: document.onkeydown = checkKeycode; function checkKeycode(e,field) {{ var keycode; if(window.event) keycode=window.event.keyCode; else if(e) keycode=e.which; }}
   - Field mapping: if(keycode == 13 && field == 'Main_Area') {{ document.getElementById('Sub_Area').focus(); }}
   - HTML attribute: onKeyDown="checkKeycode(event,this.id);"
   - Map ALL fields in sequence for data entry speed

8. **GRID/TABLE FOR DETAIL RECORDS** - REQUIRED
   - PHP Loop: for($i=0;$i<=$_REQUEST['TXTCOUNTACC'];$i++) {{ if($_REQUEST['SR_NO'.$i]!='') {{ $columns['SR_NO']=$_REQUEST['SR_NO'.$i]; db_insert($sub_table,$columns); }} }}
   - HTML Grid: <input name="txtField<?php echo $sr;?>" id="txtField<?php echo $sr;?>">
   - Checkbox: <input type="checkbox" name="Edit<?php echo $sr;?>" value="1">
   - Hidden counter: <input type="hidden" id="TXTCOUNTACC" name="TXTCOUNTACC" value="<?php echo $sr;?>">

9. **TRANSACTION MANAGEMENT** - REQUIRED
   - Start: funStartTran(); at beginning of save/update block
   - Operations: db_insert(), db_update(), db_delete() within transaction
   - End: funEndTran(); after all operations complete
   - Ensures atomicity across multiple table operations

10. **DISABLED FIELD HANDLING** - REQUIRED
    - Enable before submit: document.getElementById('Main_Area').disabled=false; in btnsave_click()
    - HTML disabled: <Select disabled <? if($_REQUEST['action']=='Update') {{ echo "disabled='disabled'"; }} ?>>
    - Re-enable ALL disabled fields before form submission

11. **COMPLETE ASSET LOADING** - REQUIRED
    - CSS: bootstrap.min.css, bootstrap-extend.min.css, site.min.css, select2.css, formValidation.css, icheck.css
    - JS: jquery.js, bootstrap.js, select2.min.js, formValidation.min.js, icheck.min.js, funJs.js
    - Plugins: data-plugin="select2", data-plugin="datepicker"
    - IE Compatibility: <!--[if lt IE 9]><script src="html5shiv.min.js"></script><![endif]-->

12. **PHP INCLUDE FILES** - REQUIRED
    - Config: include("include/config.inc.php"); at top
    - Header: <?php include("include/formheader.php"); ?> after page div
    - Menu: <?php include("include/topmenu.php");?> at body start
    - Sidebar: <?php include("include/sidemenu.php");?> after topmenu
    - Footer: <?php include("include/footer.php");?> before scripts

=== CRITICAL INSTRUCTIONS ===

1. **COPY THE AJAX PATTERN** - From examples above, use:
   - Same AJAX library (jQuery $.ajax, $.post, or fetch)
   - Same request structure
   - Same success/error handling
   - Same data formatting

2. **USE COMPANY'S FUNCTION PATTERNS**:
   - Same function naming conventions
   - Same parameter patterns
   - Same return value handling
   - Same error handling

3. **MATCH EVENT HANDLING**:
   - Same event binding approach
   - Same event handler structure
   - Same validation patterns
   - Same user feedback methods

4. **IMPLEMENT KEYBOARD NAVIGATION**:
   - document.onkeydown = checkKeycode function
   - if(keycode == 13 && field == 'fieldName') {{ document.getElementById('nextField').focus(); }}
   - Enter key moves to next field for data entry speed

5. **FOLLOW COMPANY'S VALIDATION**:
   - Same validation function structure
   - Same error message display
   - Same field highlighting
   - Same validation rules

6. **USE COMPANY'S UTILITIES**:
   - Same helper functions
   - Same data formatting functions
   - Same DOM manipulation patterns
   - Same keyboard navigation

=== OUTPUT REQUIREMENTS ===

Generate ONLY the JavaScript code in a code block.
The JavaScript MUST look like it was written by the same developer who wrote the examples above.
DO NOT use modern ES6+ if company uses jQuery/ES5 - MATCH their style exactly.
ENSURE ALL 12 ESSENTIAL COMPONENTS ARE INCLUDED (especially keyboard navigation).

```javascript
// Your generated JavaScript here
```
"""
        
        return prompt
    
    @staticmethod
    def has_analyzed_patterns(state: Dict) -> bool:
        """
        Check if state has analyzed patterns
        """
        return 'analyzed_patterns' in state and state['analyzed_patterns'] is not None