"""
Phase 2.2: GenerationPlanner
Plans code generation and builds prompts based on parsed contracts.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class GenerationPlanner:
    """
    ✅ PHASE 2.2: GENERATION PLANNER
    
    Responsibilities:
    1. Build generation prompts from contracts
    2. Plan generation strategy (controlled vs full-file)
    3. Determine what sections to generate
    4. Build validation contract for validator
    5. Plan retry strategy
    
    This class consolidates all prompt-building logic from InlinePHPGenerator.
    """
    
    def __init__(self):
        self.last_plan = {}
    
    def plan_generation(
        self,
        contract: Dict,
        company_examples: str,
        analyzed_patterns: Dict,
        user_requirements: Dict
    ) -> Dict:
        """
        Plan the generation strategy based on contract and requirements.
        
        Args:
            contract: Merged contract from ContractParser
            company_examples: Company code examples
            analyzed_patterns: Analyzed patterns from codebase
            user_requirements: Detected user requirements (dropdown, validation, etc.)
        
        Returns:
            {
                'strategy': 'controlled' | 'full_file',
                'sections_to_generate': List[str],
                'prompt': str,
                'validation_contract': Dict,
                'max_retries': int
            }
        """
        plan = {
            'strategy': 'controlled',  # Default to controlled assembly
            'sections_to_generate': [],
            'prompt': '',
            'validation_contract': {},
            'max_retries': 4
        }
        
        # Determine sections to generate
        plan['sections_to_generate'] = self._determine_sections(contract, user_requirements)
        
        # Build validation contract
        plan['validation_contract'] = self._build_validation_contract(contract, user_requirements)
        
        # Build generation prompt
        plan['prompt'] = self._build_generation_prompt(
            contract=contract,
            company_examples=company_examples,
            analyzed_patterns=analyzed_patterns,
            user_requirements=user_requirements
        )
        
        self.last_plan = plan
        return plan
    
    def _determine_sections(self, contract: Dict, user_requirements: Dict) -> List[str]:
        """
        Determine which sections need to be generated.
        
        Returns list of section names:
        - 'php_variables'
        - 'crud_handlers'
        - 'ajax_handlers'
        - 'form_fields'
        - 'validation_rules'
        - 'select2_handlers'
        - 'entity_js'
        """
        sections = [
            'php_variables',
            'crud_handlers',
            'ajax_handlers',
            'form_fields',
            'validation_rules',
            'select2_handlers',
            'entity_js',
        ]

        return sections
    
    def _build_validation_contract(self, contract: Dict, user_requirements: Dict) -> Dict:
        """
        Build validation contract that defines what validator should check.
        
        This ensures validator only checks what was actually requested.
        """
        validation_contract = {
            'required_functions': [
                'db_insert',
                'db_update',
                'db_delete',
                'db_getRecord'
            ],
            'required_handlers': ['Save', 'Update', 'Delete', 'Edit'],
            'required_ajax': ['GetMaxID'],
            'required_fields': [],
            'required_validation': user_requirements.get('wants_formvalidation', False),
            'required_keyboard': user_requirements.get('wants_keyboard', False),
            'required_dropdown': user_requirements.get('wants_dropdown', False),
            'required_grid': user_requirements.get('wants_grid', False),
            'required_dependencies': [],
            'strict_production_checks': True
        }
        
        # Add field names from contract
        for field in contract.get('fields', []):
            validation_contract['required_fields'].append(field.get('name'))
        
        # Add dependency checks
        for dep in contract.get('dependencies', []):
            validation_contract['required_dependencies'].append({
                'table': dep.get('table'),
                'field': dep.get('field')
            })
        
        return validation_contract
    
    def _build_generation_prompt(
        self,
        contract: Dict,
        company_examples: str,
        analyzed_patterns: Dict,
        user_requirements: Dict
    ) -> str:
        """
        Build the generation prompt for LLM.
        
        This is a compact, focused prompt that tells LLM exactly what to generate.
        
        ✅ FIX 1: Force inject mandatory functions
        ✅ FIX 2: Strengthen generation requirements (15000+ chars expected)
        """
        prompt_parts = []
        primary_key = contract.get('primary_key', 'Code')
        field_names = [str(field.get('name') or '').strip() for field in contract.get('fields', []) if str(field.get('name') or '').strip()]
        validation_field_one = field_names[0] if field_names else primary_key
        validation_field_two = field_names[1] if len(field_names) > 1 else validation_field_one
        allowed_tables = {str(contract.get('table_name') or '').strip()}
        allowed_tables.update(
            str(dep.get('table') or '').strip()
            for dep in contract.get('dependencies', [])
            if str(dep.get('table') or '').strip()
        )
        
        # Header with size requirement
        prompt_parts.append("Generate COMPLETE PHP CRUD form code with the following specification:")
        prompt_parts.append("")
        prompt_parts.append("⚠️ CRITICAL: Generate COMPLETE business logic (minimum 15000 characters expected)")
        prompt_parts.append("⚠️ This is VARIABLE code only - framework will be added automatically")
        prompt_parts.append("")
        
        # Entity metadata
        prompt_parts.append("=== ENTITY METADATA ===")
        prompt_parts.append(f"Table: {contract.get('table_name', 'tblentity')}")
        prompt_parts.append(f"Filename: {contract.get('file_name', 'frmEntity.php')}")
        prompt_parts.append(f"Title: {contract.get('title', 'Entity')}")
        prompt_parts.append(f"Primary Key: {primary_key}")
        prompt_parts.append("")
        prompt_parts.append("=== DETERMINISTIC CONTRACT RULES (MANDATORY) ===")
        prompt_parts.append("Generate by contract mapping ONLY. Never imitate entities from examples.")
        prompt_parts.append(f"Allowed Tables: {', '.join(sorted(tbl for tbl in allowed_tables if tbl))}")
        prompt_parts.append(f"Allowed Fields: {', '.join(field_names)}")
        prompt_parts.append("Use examples only for coding style/pattern shape, never for field/table/entity names.")
        prompt_parts.append("")
        
        # Fields
        prompt_parts.append("=== FIELDS (MUST GENERATE ALL) ===")
        prompt_parts.append(f"⚠️ CRITICAL: You MUST generate HTML inputs for ALL {len(contract.get('fields', []))} fields below")
        prompt_parts.append("")
        for idx, field in enumerate(contract.get('fields', []), 1):
            field_line = f"{idx}. {field.get('name')}"
            if field.get('db_type'):
                field_line += f" ({field.get('db_type')})"
            if field.get('input_type'):
                field_line += f" → {field.get('input_type')}"
            if field.get('required'):
                field_line += " [REQUIRED]"
            if field.get('readonly'):
                field_line += " [READONLY]"
            prompt_parts.append(field_line)
        prompt_parts.append("")
        prompt_parts.append(f"⚠️ REMINDER: Generate HTML input elements for ALL {len(contract.get('fields', []))} fields listed above")
        prompt_parts.append("")
        
        # Relationships
        if contract.get('relationships'):
            prompt_parts.append("=== RELATIONSHIPS ===")
            for rel in contract.get('relationships', []):
                prompt_parts.append(f"- {rel.get('field')} -> {rel.get('references')}")
            prompt_parts.append("")
        
        # Dependencies
        if contract.get('dependencies'):
            prompt_parts.append("=== PRE-DELETE CHECKS (MANDATORY) ===")
            for dep in contract.get('dependencies', []):
                prompt_parts.append(f"- Check {dep.get('table')}.{dep.get('field')}")
                prompt_parts.append(f"  Message: {dep.get('message')}")
            prompt_parts.append("")
        
        # ✅ FIX 1: Force inject mandatory functions with explicit requirements
        prompt_parts.append("=== MANDATORY COMPANY FUNCTIONS (MUST USE ALL) ===")
        prompt_parts.append("YOU MUST USE ALL OF THESE FUNCTIONS:")
        prompt_parts.append("")
        prompt_parts.append("Database Operations (REQUIRED):")
        prompt_parts.append("- db_insert($table, $columns) - for INSERT operations")
        prompt_parts.append("- db_update($table, $columns, $filter) - for UPDATE operations")
        prompt_parts.append("- db_delete($table, $filter) - for DELETE operations")
        prompt_parts.append("- db_getRecord($table, $filter) - for SELECT single record")
        prompt_parts.append("- getrows($table, $field, $value) - for counting dependencies")
        prompt_parts.append("- getvalue($query) - for fetching single values")
        prompt_parts.append("")
        prompt_parts.append("Transaction Management (REQUIRED):")
        prompt_parts.append("- funStartTran() - start transaction before INSERT/UPDATE/DELETE")
        prompt_parts.append("- funEndTran() - commit transaction after successful operation")
        prompt_parts.append("")
        prompt_parts.append("Build all column maps strictly from the field contract above.")
        prompt_parts.append("")
        
        # ✅ FIX 2: Mandatory AJAX requirements
        prompt_parts.append("=== MANDATORY AJAX HANDLERS (MUST IMPLEMENT) ===")
        prompt_parts.append("YOU MUST IMPLEMENT THESE AJAX HANDLERS:")
        prompt_parts.append("")
        prompt_parts.append("1. GetMaxID Handler (REQUIRED):")
        prompt_parts.append("```php")
        prompt_parts.append("if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {")
        prompt_parts.append(f"    $maxid = getvalue(\"SELECT IFNULL(MAX({primary_key}),0)+1 FROM $table WHERE Comp_Code='\" . add($comp_code) . \"'\");")
        prompt_parts.append("    echo $maxid;")
        prompt_parts.append("    exit;")
        prompt_parts.append("}")
        prompt_parts.append("```")
        prompt_parts.append("")
        prompt_parts.append("2. JavaScript maxid() function (REQUIRED):")
        prompt_parts.append("```javascript")
        prompt_parts.append("function maxid() {")
        prompt_parts.append("    $.ajax({")
        prompt_parts.append("        url: '<?=$form?>',")
        prompt_parts.append("        type: 'POST',")
        prompt_parts.append("        data: {Action: 'GetMaxID'},")
        prompt_parts.append("        dataType: 'json',")
        prompt_parts.append("        success: function(response) {")
        prompt_parts.append(f"            $('#{primary_key}').val(response.maxid);")
        prompt_parts.append("        }")
        prompt_parts.append("    });")
        prompt_parts.append("}")
        prompt_parts.append("```")
        prompt_parts.append("")
        
        # Features
        if contract.get('features'):
            prompt_parts.append("=== REQUIRED FEATURES ===")
            for feature in contract.get('features', []):
                prompt_parts.append(f"- {feature}")
            prompt_parts.append("")
        
        # Company examples for style only
        if company_examples:
            prompt_parts.append("=== COMPANY STYLE HINTS ===")
            prompt_parts.append("Use company examples only for transaction/session/UI coding style.")
            prompt_parts.append("Do not copy field names, table names, or entity-specific logic from examples.")
            prompt_parts.append("")
        
        # ✅ FIX 2: STRICT SECTION OUTPUT - Force exact section structure
        prompt_parts.append("=== 🚨 STRICT GENERATION STRUCTURE (MANDATORY) ===")
        prompt_parts.append("")
        prompt_parts.append("You MUST generate code in EXACT order with ALL sections:")
        prompt_parts.append("")
        prompt_parts.append("=== SECTION 1: PHP VARIABLES ===")
        prompt_parts.append("- $form, $form2, $table, $title, $case_type")
        prompt_parts.append("- Session variables: $user_id, $comp_code, $login_id")
        prompt_parts.append("")
        prompt_parts.append("=== SECTION 2: CRUD HANDLERS (Save, Update, Delete, Edit) ===")
        prompt_parts.append("- Save handler: INSERT with db_insert() wrapped in funStartTran/funEndTran")
        prompt_parts.append("- Update handler: UPDATE with db_update() wrapped in funStartTran/funEndTran")
        prompt_parts.append("- Delete handler: DELETE with pre-delete checks + db_delete()")
        prompt_parts.append("- Edit handler: SELECT with db_getRecord()")
        prompt_parts.append("")
        prompt_parts.append("=== SECTION 3: AJAX HANDLER (GetMaxID + JSON + exit) ===")
        prompt_parts.append("- GetMaxID handler with JSON response and exit")
        prompt_parts.append("- JavaScript maxid() function with $.ajax")
        prompt_parts.append("")
        prompt_parts.append("=== SECTION 4: HTML FORM (ALL fields) ===")
        prompt_parts.append(f"- Generate HTML input for ALL {len(contract.get('fields', []))} fields listed above")
        prompt_parts.append("- Use proper input types (text, select, checkbox, etc.)")
        prompt_parts.append("- Add proper labels and IDs")
        prompt_parts.append("")
        prompt_parts.append("=== SECTION 5: FORMVALIDATION JS (MANDATORY - CRITICAL) ===")
        prompt_parts.append("⚠️ THIS SECTION IS ABSOLUTELY REQUIRED - DO NOT SKIP!")
        prompt_parts.append("")
        prompt_parts.append("You MUST include FormValidation JavaScript like this:")
        prompt_parts.append("")
        prompt_parts.append("```javascript")
        prompt_parts.append("$(document).ready(function() {")
        prompt_parts.append("    $('#frmArea').formValidation({")
        prompt_parts.append("        framework: 'bootstrap',")
        prompt_parts.append("        icon: {")
        prompt_parts.append("            valid: 'glyphicon glyphicon-ok',")
        prompt_parts.append("            invalid: 'glyphicon glyphicon-remove',")
        prompt_parts.append("            validating: 'glyphicon glyphicon-refresh'")
        prompt_parts.append("        },")
        prompt_parts.append("        fields: {")
        prompt_parts.append(f"            {validation_field_one}: {{")
        prompt_parts.append("                validators: {")
        prompt_parts.append(f"                    notEmpty: {{ message: '{validation_field_one} is required' }}")
        prompt_parts.append("                }")
        prompt_parts.append("            },")
        prompt_parts.append(f"            {validation_field_two}: {{")
        prompt_parts.append("                validators: {")
        prompt_parts.append(f"                    notEmpty: {{ message: '{validation_field_two} is required' }}")
        prompt_parts.append("                }")
        prompt_parts.append("            }")
        prompt_parts.append("            // Include all remaining contract fields")
        prompt_parts.append("        }")
        prompt_parts.append("    });")
        prompt_parts.append("});")
        prompt_parts.append("```")
        prompt_parts.append("")
        prompt_parts.append(f"⚠️ CRITICAL: Generate formValidation for ALL {len(contract.get('fields', []))} fields")
        prompt_parts.append("⚠️ Missing FormValidation = INVALID OUTPUT")
        prompt_parts.append("")
        prompt_parts.append("You MUST complete ALL 7 controlled sections.")
        prompt_parts.append("If any section missing → OUTPUT INVALID")
        prompt_parts.append("")
        prompt_parts.append("MINIMUM OUTPUT SIZE: 15000+ characters")
        prompt_parts.append("⚠️ DO NOT return partial code")
        prompt_parts.append("⚠️ DO NOT skip FormValidation section")
        prompt_parts.append("❌ DO NOT skip ANY section")
        prompt_parts.append("❌ If incomplete → OUTPUT INVALID")
        prompt_parts.append("")
        
        return "\n".join(prompt_parts)
    
    def build_retry_prompt(
        self,
        original_prompt: str,
        validation_errors: List[str],
        previous_code: str = "",
        previous_size: int = 0
    ) -> str:
        """
        Build retry prompt with validation errors.
        
        ✅ CHANGE 7: STRICT RETRY - Force tagged structure
        🔴 FIX 3: Add explicit examples for missing tags (especially ENTITY_JS)
        
        Args:
            original_prompt: Original generation prompt
            validation_errors: List of validation errors from validator
            previous_code: Previously generated code (for context)
            previous_size: Size of previous code in chars
        
        Returns:
            Enhanced prompt with error feedback and missing tag examples
        """
        # ✅ CHANGE 7: Add strict retry header at the top
        retry_header = """
🚨 RETRY ATTEMPT - PREVIOUS OUTPUT WAS REJECTED 🚨

REASON: You did not use the required TAGGED STRUCTURE.

YOU MUST USE THIS FORMAT (NO EXCEPTIONS):
<<<VARIABLE_INIT_PHP>>> ... <<<END_VARIABLE_INIT_PHP>>>
<<<CRUD_LOGIC_PHP>>> ... <<<END_CRUD_LOGIC_PHP>>>
<<<AJAX_HANDLERS_PHP>>> ... <<<END_AJAX_HANDLERS_PHP>>>
<<<FORM_FIELDS_HTML>>> ... <<<END_FORM_FIELDS_HTML>>>
<<<ENTITY_JS>>> ... <<<END_ENTITY_JS>>>

⚠️ FLAT PHP CODE = IMMEDIATE REJECTION
⚠️ MISSING TAGS = SYSTEM FAILURE
⚠️ THIS IS YOUR LAST CHANCE

"""
        
        # 🔴 FIX 3: Detect which tags are missing and provide specific examples
        missing_tags_examples = ""
        
        # Check for missing ENTITY_JS tags (most common issue)
        has_entity_js_error = any('ENTITY_JS' in str(err) for err in validation_errors)
        has_missing_tags_error = any('Missing required tags' in str(err) for err in validation_errors)
        
        # 🔴 FIX C: Detect assembly failure (missing company functions)
        has_assembly_failure = any('MERGE FAILED' in str(err) or 'Missing mandatory company functions' in str(err) for err in validation_errors)
        missing_functions_examples = ""
        
        if has_assembly_failure:
            # Extract which functions are missing
            missing_functions_examples = """

═══════════════════════════════════════════════════════════════════════════════
🔴 CRITICAL: ASSEMBLY FAILED - MISSING COMPANY FUNCTIONS 🔴
═══════════════════════════════════════════════════════════════════════════════

Your previous code had correct tags BUT did not USE the mandatory company functions.

YOU MUST CALL THESE FUNCTIONS IN YOUR CRUD_LOGIC_PHP SECTION:

1. SAVE HANDLER (MANDATORY - COPY THIS EXACT PATTERN):

<<<CRUD_LOGIC_PHP>>>
<?php
// Save Handler
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Save') {
    // Start transaction
    funStartTran();
    
    // Prepare data array
    $data = array(
        'Area_Code' => $_POST['Area_Code'],
        'Area_Name' => $_POST['Area_Name'],
        'Region_Code' => $_POST['Region_Code'],
        'Description' => $_POST['Description'],
        'Is_Active' => isset($_POST['Is_Active']) ? 1 : 0,
        'Comp_Code' => $_SESSION['Comp_Code'],
        'User_ID' => $_SESSION['User_ID']
    );
    
    // Insert into database
    db_insert('tblarea', $data);
    
    // Commit transaction
    funEndTran();
    
    echo json_encode(['success' => true, 'message' => 'Record saved successfully']);
    exit;
}

// Update Handler
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Update') {
    funStartTran();
    
    $data = array(
        'Area_Name' => $_POST['Area_Name'],
        'Region_Code' => $_POST['Region_Code'],
        'Description' => $_POST['Description'],
        'Is_Active' => isset($_POST['Is_Active']) ? 1 : 0
    );
    
    $filter = " Area_Code='" . add($_POST['Area_Code']) . "' AND Comp_Code='" . add($_SESSION['comp_code']) . "'";
    db_update('tblarea', $data, $filter);
    
    funEndTran();
    
    echo json_encode(['success' => true, 'message' => 'Record updated successfully']);
    exit;
}

// Delete Handler with Pre-Delete Checks
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Delete') {
    $area_code = $_POST['Area_Code'];
    $comp_code = $_SESSION['comp_code'];
    
    // Check dependencies using getrows()
    $customer_count = getrows('tblcustomer', ' Area_Code', add($area_code));
    if ($customer_count > 0) {
        echo json_encode(['success' => false, 'message' => 'Cannot delete Area. It is used in Customer records.']);
        exit;
    }
    
    $salesman_count = getrows('tblsalesman', ' Area_Code', add($area_code));
    if ($salesman_count > 0) {
        echo json_encode(['success' => false, 'message' => 'Cannot delete Area. It is used in Salesman records.']);
        exit;
    }
    
    // Proceed with delete
    funStartTran();
    
    $filter = " Area_Code='" . add($area_code) . "' AND Comp_Code='" . add($comp_code) . "'";
    db_delete('tblarea', $filter);
    
    funEndTran();
    
    echo json_encode(['success' => true, 'message' => 'Record deleted successfully']);
    exit;
}

// Edit Handler - Load record for editing
if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Edit') {
    $area_code = $_POST['Area_Code'];
    $comp_code = $_SESSION['comp_code'];
    $filter = " Area_Code='" . add($area_code) . "' AND Comp_Code='" . add($comp_code) . "'";
    
    $record = db_getRecord('tblarea', $filter, $params);
    
    echo json_encode($record);
    exit;
}
?>
<<<END_CRUD_LOGIC_PHP>>>

⚠️ CRITICAL REQUIREMENTS:
✓ MUST wrap db_insert/db_update/db_delete with funStartTran() and funEndTran()
✓ MUST use db_insert() for Save - NOT raw SQL
✓ MUST use db_update() for Update - NOT raw SQL
✓ MUST use db_delete() for Delete - NOT raw SQL
✓ MUST use db_getRecord() for Edit - NOT raw SQL
✓ MUST use getrows() for dependency checks - NOT raw SQL
✓ MUST use getvalue() for single value queries

2. AJAX HANDLERS (MANDATORY):

<<<AJAX_HANDLERS_PHP>>>
<?php
// GetMaxID Handler
if (isset($_POST['Action']) && $_POST['Action'] == 'GetMaxID') {
    $comp_code = $_SESSION['Comp_Code'];
    
    // Use getvalue() to fetch max ID
    $maxid = getvalue("SELECT COALESCE(MAX(CAST(Area_Code AS UNSIGNED)), 0) + 1 AS maxid FROM tblarea WHERE Comp_Code = ?", array($comp_code));
    
    echo $maxid;
    exit;
}
?>
<<<END_AJAX_HANDLERS_PHP>>>

⚠️ YOU MUST COPY THE ABOVE PATTERNS EXACTLY
⚠️ DO NOT use mysql_query() or mysqli_query() - USE COMPANY FUNCTIONS ONLY
⚠️ EVERY database operation MUST use: db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
⚠️ EVERY insert/update/delete MUST be wrapped in funStartTran() / funEndTran()

═══════════════════════════════════════════════════════════════════════════════
"""
        
        if has_entity_js_error or has_missing_tags_error:
            missing_tags_examples = """

=== 🔴 CRITICAL: MISSING TAGS DETECTED ===

Your previous attempt was missing required section tags.
Here are EXACT EXAMPLES of what you MUST include:

1. <<<ENTITY_JS>>> SECTION (MANDATORY - COPY THIS FORMAT):

<<<ENTITY_JS>>>
<script>
// Entity Master - JavaScript Functions

// AJAX GetMaxID function
function maxid() {
    $.ajax({
        url: '',
        type: 'POST',
        data: { Action: 'GetMaxID' },
        success: function(response) {
            $('#Area_Code').val(response.trim());
        }
    });
}

// Document Ready - Initialize form
$(document).ready(function() {
    // Call maxid on page load
    maxid();
    
    // Form Validation Setup
    $('#frmMain').formValidation({
        framework: 'bootstrap',
        icon: {
            valid: 'glyphicon glyphicon-ok',
            invalid: 'glyphicon glyphicon-remove',
            validating: 'glyphicon glyphicon-refresh'
        },
        fields: {
            Area_Code: {
                validators: {
                    notEmpty: { message: 'Area Code is required' }
                }
            },
            Area_Name: {
                validators: {
                    notEmpty: { message: 'Area Name is required' }
                }
            }
            // ADD ALL YOUR FIELDS HERE
        }
    }).on('success.form.fv', function(e) {
        e.preventDefault();
        $('#btnSave').click();
    });
});
</script>
<<<END_ENTITY_JS>>>

⚠️ COPY THE ABOVE FORMAT EXACTLY - Replace field names with your actual fields
⚠️ The <<<ENTITY_JS>>> and <<<END_ENTITY_JS>>> tags are MANDATORY
⚠️ Even if your JS is minimal, you MUST include this section with tags

2. ALL OTHER SECTIONS MUST ALSO HAVE TAGS:

<<<VARIABLE_INIT_PHP>>>
<?php
$table = 'tblarea';
$form = 'Area Master';
?>
<<<END_VARIABLE_INIT_PHP>>>

<<<CRUD_LOGIC_PHP>>>
<?php
// Your CRUD code here
?>
<<<END_CRUD_LOGIC_PHP>>>

<<<AJAX_HANDLERS_PHP>>>
<?php
// Your AJAX handlers here
?>
<<<END_AJAX_HANDLERS_PHP>>>

<<<FORM_FIELDS_HTML>>>
<!-- Your form fields HTML here -->
<<<END_FORM_FIELDS_HTML>>>

⚠️ EVERY SECTION MUST BE WRAPPED IN TAGS - NO EXCEPTIONS
"""
        
        # Check if FormValidation is missing
        has_formvalidation_error = any('formValidation' in str(err).lower() for err in validation_errors)
        
        retry_prompt = retry_header + missing_functions_examples + missing_tags_examples + original_prompt + f"""

=== 🚨 PREVIOUS ATTEMPT ERRORS ===

Previous output FAILED with {len(validation_errors)} errors.

Errors found:
{chr(10).join(f"- {err}" for err in validation_errors[:5])}

Previous output was only {previous_size} characters (expected 15000+).

You MUST fix ALL missing parts:

1. Use TAGGED STRUCTURE (see examples above)
2. CALL ALL MANDATORY COMPANY FUNCTIONS (see examples above)
3. Wrap database operations in funStartTran() / funEndTran()
4. Use db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
5. Generate FULL code (15000+ chars)
6. DO NOT return partial code again

⚠️ CRITICAL: All company functions are MANDATORY
⚠️ Missing function calls = ASSEMBLY FAILURE
⚠️ Missing tags = SYSTEM FAILURE
⚠️ NO RAW SQL ALLOWED - USE COMPANY FUNCTIONS ONLY
"""
        
        return retry_prompt
    
    def get_last_plan(self) -> Dict:
        """Get the last generation plan"""
        return self.last_plan
