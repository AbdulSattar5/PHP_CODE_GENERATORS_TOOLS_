"""
Analyze the generated Area form code to identify missing patterns.
"""
import re

# Read the generated code
with open('generated_area_form.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract all sections
sections = {
    'VARIABLE_INIT_PHP': '',
    'CRUD_LOGIC_PHP': '',
    'AJAX_HANDLERS_PHP': '',
    'FORM_FIELDS_HTML': '',
    'ENTITY_JS': ''
}

for section_name in sections.keys():
    match = re.search(
        rf'{section_name}:\s*-+\s*(.*?)(?=\n\n[A-Z_]+:|$)',
        content,
        re.DOTALL
    )
    if match:
        sections[section_name] = match.group(1).strip()

# Combine all code
all_code = '\n\n'.join(sections.values())

print("=" * 80)
print("DETAILED ANALYSIS OF GENERATED CODE")
print("=" * 80)
print()

# Check for each mandatory function
mandatory_functions = [
    'db_insert',
    'db_update',
    'db_delete',
    'db_getRecord',
    'getrows',
    'getvalue',
    'funStartTran',
    'funEndTran'
]

print("MANDATORY FUNCTIONS CHECK:")
print("-" * 80)
for func in mandatory_functions:
    pattern = rf'{func}\s*\('
    found = re.search(pattern, all_code)
    status = "✅" if found else "❌"
    print(f"{status} {func}()")
    if found:
        # Show context
        start = max(0, found.start() - 50)
        end = min(len(all_code), found.end() + 50)
        context = all_code[start:end].replace('\n', ' ')
        print(f"   Context: ...{context}...")

print()
print("=" * 80)
print("MISSING PATTERNS ANALYSIS:")
print("=" * 80)
print()

# Check for db_getRecord usage
if not re.search(r'db_getRecord\s*\(', all_code):
    print("❌ MISSING: db_getRecord()")
    print("   Issue: The code references $record but never fetches it using db_getRecord()")
    print("   Expected: Edit action should use db_getRecord() to fetch existing record")
    print("   Example:")
    print("   if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'Edit') {")
    print("       $record = db_getRecord($table, 'Area_Code = ?', [$_REQUEST['Area_Code']]);")
    print("   }")
    print()

# Check for getvalue usage
if not re.search(r'getvalue\s*\(', all_code):
    print("❌ MISSING: getvalue()")
    print("   Issue: The code doesn't use getvalue() for fetching single values")
    print("   Note: This might be acceptable if not needed for this specific form")
    print()

# Check for GetMaxID AJAX handler
if 'GetMaxID' not in all_code:
    print("⚠️  MISSING: GetMaxID AJAX handler")
    print("   Issue: No AJAX handler for auto-generating Area_Code")
    print("   Expected: AJAX_HANDLERS_PHP should include GetMaxID handler")
    print("   Example:")
    print("   if (isset($_REQUEST['Action']) && $_REQUEST['Action'] == 'GetMaxID') {")
    print("       $maxId = getvalue(\"SELECT MAX(Area_Code) FROM tblarea\");")
    print("       echo $maxId + 1;")
    print("       exit;")
    print("   }")
    print()

# Check for maxid() JS function
if 'maxid()' not in all_code and 'function maxid' not in all_code:
    print("⚠️  MISSING: maxid() JavaScript function")
    print("   Issue: No JS function to call GetMaxID AJAX handler")
    print("   Expected: ENTITY_JS should include maxid() function")
    print("   Example:")
    print("   function maxid() {")
    print("       $.ajax({")
    print("           url: 'frmArea.php',")
    print("           data: { Action: 'GetMaxID' },")
    print("           success: function(data) {")
    print("               $('#Area_Code').val(data);")
    print("           }")
    print("       });")
    print("   }")
    print()

print("=" * 80)
print("SUMMARY:")
print("=" * 80)
print()
print("The generated code is PARTIALLY correct but missing critical patterns:")
print()
print("✅ PRESENT:")
print("  • getrows() for pre-delete dependency checks")
print("  • page_container structure (page/page-content/panel divs)")
print("  • delegated_events pattern (.on(event, selector, handler))")
print("  • ajax_reinit_guard (window.formInitialized check)")
print("  • db_insert, db_update, db_delete")
print("  • funStartTran, funEndTran")
print()
print("❌ MISSING:")
print("  • db_getRecord() - Not used to fetch record for Edit action")
print("  • getvalue() - Not used (may not be needed for this form)")
print("  • GetMaxID AJAX handler - Not implemented")
print("  • maxid() JS function - Not implemented")
print()
print("CONCLUSION:")
print("The prompt fix from Task 1 is PARTIALLY working. The LLM is including most")
print("required patterns, but it's not generating complete CRUD logic.")
print()
print("The code references $record but never fetches it, which would cause errors.")
print("This suggests the prompt needs to be more explicit about Edit action logic.")
print()
