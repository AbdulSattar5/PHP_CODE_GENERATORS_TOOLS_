"""
Smart Prompt Enhancer
Automatically enhances user's simple prompt with company-specific requirements
User just says: "Create entity form with name, email, phone"
System adds: AJAX auto-ID, company functions, table names, etc.
"""

import re
import logging
import os
from typing import Dict, List

from agents.utils.runtime_config import get_csv_setting

logger = logging.getLogger(__name__)


class SmartPromptEnhancer:
    """
    Enhances user's simple prompt with company-specific patterns
    
    USER SAYS: "Create <entity> form"
    SYSTEM ADDS: AJAX auto-ID, db_insert(), table binding, comp_code, etc.
    """
    
    def __init__(self, analyzed_patterns: Dict = None):
        self.analyzed_patterns = analyzed_patterns or {}

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        text = (text or "").lower()
        return any(keyword.lower() in text for keyword in keywords if keyword)

    def _normalize_identifier(self, value: str, fallback: str = "") -> str:
        cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(value or '')).strip('_')
        if not cleaned:
            return fallback
        return cleaned

    def _extract_explicit_metadata(self, user_prompt: str) -> Dict[str, str]:
        text = user_prompt or ""
        metadata = {}
        patterns = {
            'table_name': r'(?im)^\s*(?:[-*]\s*)?table\s*:\s*([A-Za-z0-9_]+)\s*$',
            'file_name': r'(?im)^\s*(?:[-*]\s*)?(?:file\s*name|filename|file)\s*:\s*([A-Za-z0-9_.-]+)\s*$',
            'title': r'(?im)^\s*(?:[-*]\s*)?title\s*:\s*([A-Za-z0-9_ \-]+)\s*$',
            'case_type': r'(?im)^\s*(?:[-*]\s*)?(?:case\s*type|casetype)\s*:\s*([A-Za-z0-9_ \-]+)\s*$',
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()
        return metadata

    def _extract_entity_name(self, user_prompt: str, intent: Dict, metadata: Dict[str, str]) -> str:
        candidates = [
            metadata.get('case_type', ''),
            metadata.get('title', ''),
            metadata.get('table_name', ''),
            metadata.get('file_name', ''),
        ]

        for candidate in candidates:
            value = str(candidate or '').strip()
            if not value:
                continue
            value = re.sub(r'\.php$', '', value, flags=re.IGNORECASE)
            if value.lower().startswith('frm'):
                value = value[3:]
            if value.lower().startswith('tbl_'):
                value = value[4:]
            elif value.lower().startswith('tbl'):
                value = value[3:]
            normalized = self._normalize_identifier(value)
            if normalized:
                return normalized

        request_lower = (user_prompt or '').lower()
        for pattern in [
            r'create\s+(?:a|an)?\s*(?:complete\s+)?([a-z][a-z0-9_]*)\s+master\s+form',
            r'([a-z][a-z0-9_]*)\s+master\s+form',
            r'form\s+for\s+([a-z][a-z0-9_]*)',
        ]:
            match = re.search(pattern, request_lower, re.IGNORECASE)
            if match:
                normalized = self._normalize_identifier(match.group(1))
                if normalized:
                    return normalized

        if intent and intent.get('form_title'):
            normalized = self._normalize_identifier(intent.get('form_title'))
            if normalized:
                return normalized

        return 'entity'

    def _parse_map_setting(self, setting_name: str, env_name: str) -> Dict[str, str]:
        """
        Parse mapping entries in either format:
        - key:value
        - key=value
        """
        mapping = {}
        raw_items = get_csv_setting(setting_name, env_name, default=[])
        for item in raw_items:
            if ':' in item:
                key, value = item.split(':', 1)
            elif '=' in item:
                key, value = item.split('=', 1)
            else:
                continue
            key_norm = self._normalize_identifier(key).lower()
            value_norm = value.strip()
            if key_norm and value_norm:
                mapping[key_norm] = value_norm
        return mapping

    def _parse_list_map_setting(self, setting_name: str, env_name: str) -> Dict[str, List[str]]:
        """
        Parse map entries in format:
        entity:tbl_a|tbl_b|tbl_c
        """
        result = {}
        raw_items = get_csv_setting(setting_name, env_name, default=[])
        for item in raw_items:
            if ':' in item:
                key, value = item.split(':', 1)
            elif '=' in item:
                key, value = item.split('=', 1)
            else:
                continue
            key_norm = self._normalize_identifier(key).lower()
            if not key_norm:
                continue
            entries = [part.strip() for part in re.split(r'[|]+', value) if part.strip()]
            if entries:
                result[key_norm] = entries
        return result

    def _resolve_table_name(self, entity_name: str, metadata: Dict[str, str]) -> str:
        explicit = self._normalize_identifier(metadata.get('table_name', ''))
        if explicit:
            return explicit

        table_map = self._parse_map_setting('CODEGEN_ENTITY_TABLE_MAP', 'CODEGEN_ENTITY_TABLE_MAP')
        entity_key = self._normalize_identifier(entity_name).lower()
        mapped = table_map.get(entity_key)
        if mapped:
            return mapped

        table_prefix = os.getenv('CODEGEN_TABLE_PREFIX', 'tbl_')
        entity_snake = self._normalize_identifier(entity_name, fallback='entity').lower()
        if table_prefix.endswith('_'):
            return f"{table_prefix}{entity_snake}"
        return f"{table_prefix}{entity_snake}"

    def _resolve_chart_prefix(self, entity_name: str) -> str:
        prefix_map = self._parse_map_setting('CODEGEN_CHART_PREFIX_MAP', 'CODEGEN_CHART_PREFIX_MAP')
        entity_key = self._normalize_identifier(entity_name).lower()
        mapped = prefix_map.get(entity_key)
        if mapped:
            return mapped

        base_prefix = os.getenv('CODEGEN_CHART_PREFIX_BASE', 'ACC').strip() or 'ACC'
        slug_len_raw = os.getenv('CODEGEN_CHART_ENTITY_SLUG_LEN', '4')
        try:
            slug_len = max(2, min(10, int(slug_len_raw)))
        except ValueError:
            slug_len = 4

        entity_slug = re.sub(r'[^A-Za-z0-9]+', '', entity_name or '').upper()[:slug_len] or 'GEN'
        return f"{base_prefix}_{entity_slug}"

    def _extract_dependency_tables(self, user_prompt: str, entity_name: str) -> List[str]:
        text = user_prompt or ""
        match = re.search(
            r'(?im)pre-?delete\s+dependency\s+checks?\s+for\s*:\s*(.+)$',
            text
        )
        if match:
            line = match.group(1).strip()
            raw_parts = [p.strip() for p in re.split(r'[,;]+', line) if p.strip()]
            cleaned = []
            for part in raw_parts:
                part = part.strip('{}[]() ')
                part = self._normalize_identifier(part)
                if part:
                    cleaned.append(part)
            if cleaned:
                return cleaned

        table_map = self._parse_list_map_setting(
            'CODEGEN_PREDELETE_TABLES_MAP',
            'CODEGEN_PREDELETE_TABLES_MAP'
        )
        entity_key = self._normalize_identifier(entity_name).lower()
        return table_map.get(entity_key, [])
    
    def enhance_prompt(self, user_prompt: str, intent: Dict = None) -> str:
        """
        Enhance user's simple prompt with company requirements
        
        Args:
            user_prompt: User's original simple prompt
            intent: Parsed intent with fields, operations, etc.
        
        Returns:
            Enhanced prompt with all company-specific requirements
        """
        logger.info("🔍 Enhancing user prompt with company patterns...")
        logger.info(f"   Original prompt: {user_prompt[:100]}...")
        
        # Detect what user wants
        detection = self._detect_user_requirements(user_prompt, intent)
        
        # Build enhanced prompt
        enhanced = self._build_enhanced_prompt(user_prompt, intent, detection)
        
        logger.info(f"✅ Enhanced prompt: {len(enhanced)} characters")
        logger.info(f"   Added: {', '.join(detection['features_to_add'])}")
        
        return enhanced
    
    def _detect_user_requirements(self, user_prompt: str, intent: Dict) -> Dict:
        """
        Detect what features user wants based on keywords
        """
        prompt_lower = (user_prompt or '').lower()
        metadata = self._extract_explicit_metadata(user_prompt)
        entity_name = self._extract_entity_name(user_prompt, intent, metadata)
        table_name = self._resolve_table_name(entity_name, metadata)

        detection = {
            'form_type': entity_name.lower(),
            'entity_name': entity_name,
            'has_dropdown': False,
            'has_cascade': False,
            'has_validation': False,
            'has_business_validations': False,
            'has_keyboard': False,
            'has_grid': False,
            'has_select2': False,
            'has_chart': False,
            'table_name': table_name,
            'chart_prefix': self._resolve_chart_prefix(entity_name),
            'dependency_tables': self._extract_dependency_tables(user_prompt, entity_name),
            'features_to_add': []
        }

        chart_entity_defaults = get_csv_setting(
            'CODEGEN_CHART_ENTITIES',
            'CODEGEN_CHART_ENTITIES',
            default=['customer', 'supplier']
        )
        chart_keywords = get_csv_setting(
            'CODEGEN_CHART_KEYWORDS',
            'CODEGEN_CHART_KEYWORDS',
            default=['chart', 'account', 'acc_code', 'acc code', 'account chart']
        )
        if (
            detection['form_type'] in {item.lower() for item in chart_entity_defaults}
            or self._matches_keywords(prompt_lower, chart_keywords)
        ):
            detection['has_chart'] = True
        
        # Detect features explicitly mentioned
        if any(word in prompt_lower for word in ['dropdown', 'select', 'area', 'city', 'category']):
            detection['has_dropdown'] = True
            detection['features_to_add'].append('Dynamic Dropdowns')
        
        if any(word in prompt_lower for word in ['cascade', 'cascading', 'dependent']):
            detection['has_cascade'] = True
            detection['features_to_add'].append('Cascading Dropdowns')
        
        if any(word in prompt_lower for word in ['validation', 'validate', 'required']):
            detection['has_validation'] = True
            detection['features_to_add'].append('FormValidation.js')
        if any(word in prompt_lower for word in ['business validation', 'business rule', 'unique', 'pre-delete', 'dependency']):
            detection['has_business_validations'] = True
            detection['features_to_add'].append('Business Validations')
        
        if any(word in prompt_lower for word in ['keyboard', 'enter', 'fast entry']):
            detection['has_keyboard'] = True
            detection['features_to_add'].append('Keyboard Navigation')
        
        if any(word in prompt_lower for word in ['grid', 'detail', 'line item', 'multiple']):
            detection['has_grid'] = True
            detection['features_to_add'].append('Grid Pattern')
        
        if any(word in prompt_lower for word in ['select2', 'searchable']):
            detection['has_select2'] = True
            detection['features_to_add'].append('Select2')
        
        # Check intent for fields that need CASCADING dropdowns
        # Only flag if there's a clear parent-child relationship (city->area)
        if intent and intent.get('fields'):
            field_names = [f.get('name', '').lower() for f in intent['fields']]
            if (
                ('city' in field_names and 'area' in field_names) or
                ('country_code' in field_names and 'state_code' in field_names and 'city_code' in field_names)
            ):
                detection['has_dropdown'] = True
                detection['has_cascade'] = True
                if 'Cascading Dropdowns' not in detection['features_to_add']:
                    detection['features_to_add'].append('Cascading Dropdowns')
        if intent and isinstance(intent, dict):
            strict_contract = intent.get('strict_contract') or {}
            if isinstance(strict_contract, dict):
                for dep in strict_contract.get('dependencies') or []:
                    dep_table = str(dep.get('table') or '').strip()
                    if dep_table and dep_table not in detection['dependency_tables']:
                        detection['dependency_tables'].append(dep_table)
                if strict_contract.get('dependencies'):
                    detection['has_business_validations'] = True
                if strict_contract.get('validation_rules') or strict_contract.get('business_validations'):
                    detection['has_business_validations'] = True
            if intent.get('strict_features'):
                strict_features = {str(feature).strip().lower() for feature in intent.get('strict_features') or []}
                if {'validation', 'predelete', 'dependency'} & strict_features:
                    detection['has_business_validations'] = True

        if detection['dependency_tables']:
            detection['features_to_add'].append('Pre-delete Rules')
            detection['has_business_validations'] = True
        
        # ALWAYS add core features (even if not mentioned)
        detection['features_to_add'].insert(0, 'AJAX Auto-ID')
        detection['features_to_add'].append('Company Functions')
        detection['features_to_add'].append('Multi-Company Filter')
        detection['features_to_add'].append('Logging')
        detection['features_to_add'] = list(dict.fromkeys(detection['features_to_add']))
        
        return detection
    
    def _build_enhanced_prompt(self, user_prompt: str, intent: Dict, detection: Dict) -> str:
        """
        Build enhanced prompt with all company requirements
        """
        
        # Extract fields from intent
        fields = []
        if intent and intent.get('fields'):
            for field in intent['fields']:
                field_name = field.get('label', field.get('name', ''))
                field_type = field.get('input_type', 'text')
                required = field.get('required', False)
                
                field_str = f"- {field_name}"
                if required:
                    field_str += " (required)"
                if field_type == 'select':
                    field_str += " (dropdown)"
                
                fields.append(field_str)
        
        # Get table name
        table_name = detection['table_name'] or 'tbl_entity'
        
        # Build enhanced prompt
        enhanced = f"""
{user_prompt}

=== AUTOMATIC ENHANCEMENTS (Company Standards) ===

**Core Requirements (Always Applied):**

1. **AJAX Auto-ID Generation:**
   - Primary code auto-generated using GetMaxID AJAX handler
   - Load on page load and on relevant parent field changes

2. **Database Operations:**
   - Save to {table_name} table
   - Use funStartTran() for transaction management
   - Use db_insert() for new records
   - Use db_update() for existing records
   - Use db_delete() for deletions
   - Use getrows() to check if record exists

3. **Multi-Company Support:**
   - Filter all queries with $_SESSION['comp_code']
   - Add Comp_Code to all INSERT/UPDATE operations

4. **Session Variables:**
   - Use $_SESSION['user_id'] for created_by/updated_by
   - Use $_SESSION['login_id'] for logging
   - Use $_SESSION['comp_code'] for multi-company filter

5. **Logging:**
   - Call fun_log() on Save, Update, Delete operations
   - Log user_id, action, and timestamp

6. **Error Handling:**
   - Alert messages for success/error
   - Proper error messages for validation failures
"""

        # Add dropdown requirements if detected
        if detection['has_dropdown'] or detection['has_cascade']:
            enhanced += """
7. **Dynamic Dropdowns:**
   - Parent-child dropdowns loaded dynamically from database
   - Child dropdown values should refresh when parent changes
   - Use AJAX handlers with json_encode() for data
   - onChange events to trigger cascade updates
"""

        # Add chart integration for entities that require account linkage
        if detection['has_chart']:
            acc_prefix = detection.get('chart_prefix') or self._resolve_chart_prefix(detection.get('entity_name', 'entity'))
            enhanced += f"""
8. **Chart of Accounts Integration:**
   - Generate ACC_CODE with {acc_prefix} prefix
   - INSERT into chart table on new record
   - UPDATE chart table on record update
   - DELETE from chart table on record delete
   - Set GRP_DET='D' and LEVEL='4'
"""

        # Add validation if detected
        if detection['has_validation']:
            enhanced += """
9. **FormValidation.js Framework:**
   - Initialize with $('#frm').formValidation()
   - Validate required fields
   - Email format validation
   - Phone number validation (numeric only)
   - Minimum length validation
"""

        # Add keyboard navigation if detected
        if detection['has_keyboard']:
            enhanced += """
10. **Keyboard Navigation:**
    - document.onkeydown = checkKeycode
    - Enter key moves to next field
    - Map all fields in sequence
    - Fast data entry support
"""

        # Add Select2 if detected
        if detection['has_select2']:
            enhanced += """
11. **Select2 Integration:**
    - Searchable dropdowns with Select2
    - data-plugin="select2" attribute
    - Placeholder text
    - Clear button
"""

        # Add grid if detected
        if detection['has_grid']:
            enhanced += """
12. **Grid/Detail Records:**
    - Master-detail form structure
    - Dynamic row addition/deletion
    - Loop through detail records on save
    - Hidden counter field (TXTCOUNTACC)
"""

        # Add pre-delete checks
        related_tables = detection.get('dependency_tables') or []
        
        if related_tables:
            tables_str = ', '.join(related_tables)
            enhanced += f"""
13. **Pre-Delete Dependency Checks:**
    - Check if record exists in: {tables_str}
    - Use getrows2() to check dependencies
    - Show alert if dependencies exist
    - Prevent deletion if record is in use
"""

        if detection.get('has_business_validations'):
            enhanced += """
14. **Business Validations (Mandatory):**
    - Enforce unique constraints using getrows() before Save/Update
    - Validate critical business fields server-side before db_insert/db_update
    - Keep dependency checks only inside Delete action block
    - Return explicit error alerts/messages (no silent failures)
"""

        # Add company function list
        enhanced += """
=== MANDATORY COMPANY FUNCTIONS ===

You MUST use these exact functions:
- funStartTran() - Start transaction
- funEndTran() - End transaction
- db_insert($table, $columns) - Insert record
- db_update($table, $columns, $filter) - Update record
- db_delete($table, $filter) - Delete record
- getrows($table, $field, $value) - Check if record exists
- getrows2($table, $filter) - Check dependencies
- getvalue($sql) - Get single value
- fun_log($table, $code, $action, $user) - Log operation
- add_Slashes_new($value) - Escape strings

=== MANDATORY PATTERNS ===

1. Session start: @session_start();
2. Include config: include("include/config.inc.php");
3. AJAX handlers BEFORE form processing
4. Transaction wrapper for all DB operations
5. Conditional logic: if(getrows(...) == '1') { update } else { insert }
6. Multi-company filter in ALL queries
7. Logging on ALL operations

=== OUTPUT FORMAT ===

Generate a SINGLE PHP file with:
- PHP logic at top (session, includes, AJAX handlers, form processing)
- HTML form in middle
- JavaScript at bottom (validation, AJAX, keyboard navigation)
"""

        return enhanced
    
    def get_simple_prompt_template(self, form_type: str = 'customer') -> str:
        """
        Get a simple prompt template that users can use
        System will auto-enhance it
        """
        
        templates = {
            'customer': """Create a customer form with:
- Customer ID (auto-generated)
- Customer Name
- Email
- Phone
- Address
- City (dropdown)
- Area (dropdown, depends on City)
- Category (dropdown)
- Status

Include save, update, delete, and search functionality.""",
            
            'supplier': """Create a supplier form with:
- Supplier ID (auto-generated)
- Supplier Name
- Contact Person
- Email
- Phone
- Address
- City (dropdown)
- Type (dropdown)
- Status

Include save, update, delete, and search functionality.""",
            
            'product': """Create a product form with:
- Product ID (auto-generated)
- Product Name
- Category (dropdown)
- Unit (dropdown)
- Price
- Stock Quantity
- Description
- Status

Include save, update, delete, and search functionality.""",
            
            'employee': """Create an employee form with:
- Employee ID (auto-generated)
- Employee Name
- Email
- Phone
- Department (dropdown)
- Designation (dropdown)
- Salary
- Join Date
- Status

Include save, update, delete, and search functionality."""
        }
        
        normalized = self._normalize_identifier(form_type).lower()
        if normalized in templates:
            return templates[normalized]

        entity_label = self._normalize_identifier(form_type, fallback='Entity').replace('_', ' ')
        return f"""Create a {entity_label.lower()} form with:
- Code (auto-generated)
- Name
- Description
- Status

Include save, update, delete, and search functionality."""


# Singleton instance
smart_prompt_enhancer = SmartPromptEnhancer()
