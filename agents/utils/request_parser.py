"""
Request Schema Parser - Phase 2.1
Deterministic parser that converts user requests into structured JSON schema.
No heuristics - only explicit parsing with clear fallbacks.
"""

import re
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def _line_looks_like_field_definition(line: str) -> bool:
    """Return True when a line looks like a structured field contract."""
    stripped = str(line or '').strip()
    if not stripped:
        return False
    return bool(
        re.match(r'^\s*[-*]\s*[A-Za-z_][A-Za-z0-9_]*\s*\|', stripped)
        or re.match(r'^\s*[-*]\s*[A-Za-z_][A-Za-z0-9_]*\s*->', stripped)
        or ('field=' in stripped.lower() and 'message=' in stripped.lower())
    )


def normalize_request_text(user_request: str) -> str:
    """
    Normalize compact prompts into deterministic section/bullet text.

    This keeps pipe-delimited field contracts intact while splitting metadata
    headings and inline bullet lists onto their own lines.
    """
    text = (user_request or "").replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return ''

    normalized_lines = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if _line_looks_like_field_definition(stripped):
            normalized_lines.append(raw_line.rstrip())
        else:
            normalized_lines.append(re.sub(r'\s*\|\s*', '\n', raw_line.rstrip()))
    text = '\n'.join(normalized_lines)

    # Use horizontal whitespace only so heading matching stays on one line.
    section_pattern = (
        r'(?:master[ \t]*table|master_table|detail[ \t]*table|detail_table|table|'
        r'file[ \t]*name|file_name|filename|file|title|case[ \t]*type|casetype|'
        r'primary[ \t]*key|primary_key|master[ \t]*fields|form[ \t]*fields|fields|'
        r'detail[ \t]*grid|detail[ \t]*fields|relationships?|dependencies?|'
        r'business[ \t]*validations?|validation[ \t]*rules|required[ \t]*company[ \t]*patterns|'
        r'required[ \t]*patterns|features?|operations|crud[ \t]*operations|output)'
    )
    # Split inline section headings on the same physical line only.
    # Using [ \t]+ avoids crossing line breaks and truncating values like:
    # "Title: Test Form" -> "Title: Test\nForm".
    text = re.sub(
        rf'[ \t]+(?={section_pattern}[ \t]*:)',
        '\n',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(
        r'[ \t]+(?=-\s*[A-Za-z_][A-Za-z0-9_]*)',
        '\n',
        text
    )
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class RequestSchemaParser:
    """
    ✅ PHASE 2.1: REQUEST SCHEMA PARSER
    
    Converts natural language user requests into deterministic JSON schema.
    This eliminates guessing and provides a clear contract for generation.
    
    Output Schema:
    {
        "table": "tblsubarea",
        "filename": "frmSubArea.php",
        "title": "Sub Area",
        "case_type": "SubArea",
        "primary_key": "SubArea_Code",
        "fields": [
            {
                "name": "SubArea_Code",
                "db_type": "VARCHAR(20)",
                "input_type": "textbox",
                "required": true,
                "readonly": true
            }
        ],
        "relationships": [
            {
                "field": "Area_Code",
                "references": "tblarea.Area_Code",
                "cascade": true,
                "input_type": "select"
            }
        ],
        "dependencies": [
            {
                "table": "tblcustomer",
                "field": "SubArea_Code",
                "message": "Cannot delete if used in customer"
            }
        ],
        "features": ["dropdown", "validation", "keyboard", "predelete"]
    }
    """
    
    def __init__(self):
        self.schema = {}
        self.errors = []
        self.warnings = []
    
    def parse(self, user_request: str) -> Dict[str, Any]:
        """
        Parse user request into structured schema.
        
        Args:
            user_request: Raw user request text
        
        Returns:
            Structured schema dict
        
        Raises:
            ValueError: If required fields are missing
        """
        logger.info("📋 PHASE 2.1: Parsing user request into schema...")
        
        self.schema = {}
        self.errors = []
        self.warnings = []
        
        normalized_request = self._normalize_request(user_request)
        
        # 1. Extract canonical naming (REQUIRED)
        self._parse_canonical_naming(normalized_request)
        
        # 2. Extract primary key (REQUIRED)
        self._parse_primary_key(normalized_request)
        
        # 3. Extract fields (REQUIRED)
        self._parse_fields(normalized_request)
        
        # 4. Extract relationships (OPTIONAL)
        self._parse_relationships(normalized_request)
        
        # 5. Extract dependencies (OPTIONAL)
        self._parse_dependencies(normalized_request)
        
        # 6. Extract features (OPTIONAL)
        self._parse_features(normalized_request)
        
        # 7. Validate schema completeness
        self._validate_schema()
        
        # 8. Log results
        self._log_parsing_results()
        
        return self.schema

    def _normalize_request(self, user_request: str) -> str:
        """
        Normalize prompt formatting so repeated parsing across stages is deterministic.
        """
        return normalize_request_text(user_request)
    
    def _parse_canonical_naming(self, user_request: str):
        """Extract table, filename, title, case_type"""
        logger.info("   Parsing canonical naming...")
        
        # Table name (REQUIRED)
        table_patterns = [
            r'(?i)^\s*(?:[-*]\s*)?master\s*table\s*:\s*([a-z][a-z0-9_]*)\s*$',
            r'(?i)^\s*(?:[-*]\s*)?master_table\s*:\s*([a-z][a-z0-9_]*)\s*$',
            r'(?i)^\s*(?:[-*]\s*)?table\s*:\s*([a-z][a-z0-9_]*)\s*$',  # Multiline
            r'(?i)\bmaster\s*table\s*:\s*([a-z][a-z0-9_]+)',
            r'(?i)\bmaster_table\s*:\s*([a-z][a-z0-9_]+)',
            r'(?i)\btable\s*:\s*([a-z][a-z0-9_]+)',  # Inline
            r'(?i)table\s+name\s*:\s*([a-z][a-z0-9_]+)',  # "Table name:"
        ]
        
        table_name = None
        for pattern in table_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                table_name = match.group(1).strip()
                break
        
        if not table_name:
            self.errors.append("table name is required but not found")
        else:
            self.schema['table'] = table_name
            self.schema['master_table'] = table_name

        detail_table_patterns = [
            r'(?i)^\s*(?:[-*]\s*)?detail\s*table\s*:\s*([a-z][a-z0-9_]*)\s*$',
            r'(?i)^\s*(?:[-*]\s*)?detail_table\s*:\s*([a-z][a-z0-9_]*)\s*$',
            r'(?i)\bdetail\s*table\s*:\s*([a-z][a-z0-9_]+)',
            r'(?i)\bdetail_table\s*:\s*([a-z][a-z0-9_]+)',
        ]
        for pattern in detail_table_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                self.schema['detail_table'] = match.group(1).strip()
                break
        
        # File name (REQUIRED)
        file_patterns = [
            r'(?i)^\s*(?:[-*]\s*)?file_name\s*:\s*([a-z0-9_().\-]+\.php)\s*$',
            r'(?i)^\s*(?:[-*]\s*)?(?:file\s*name|filename|file)\s*:\s*([a-z0-9_().\-]+\.php)\s*$',
            r'(?i)file_name\s*:\s*([a-z0-9_().\-]+\.php)',
            r'(?i)(?:file\s*name|filename|file)\s*:\s*([a-z0-9_().\-]+\.php)',
        ]
        
        file_name = None
        for pattern in file_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                file_name = match.group(1).strip()
                break
        
        if not file_name:
            self.errors.append("file name is required but not found")
        else:
            self.schema['filename'] = file_name
            self.schema['file_name'] = file_name
        
        # Title (REQUIRED)
        title_patterns = [
            r'(?i)^\s*(?:[-*]\s*)?title\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$',
            r'(?i)\btitle\s*:\s*([A-Za-z][A-Za-z0-9_ \-]+)',
        ]
        
        title = None
        for pattern in title_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                title = match.group(1).strip()
                break
        
        if not title:
            title = self._infer_title(user_request, file_name=file_name, table_name=table_name)

        if not title:
            self.errors.append("title is required but not found")
        else:
            self.schema['title'] = title
        
        # Case Type (OPTIONAL - defaults to title)
        case_type_patterns = [
            r'(?i)^\s*(?:[-*]\s*)?(?:case\s*type|casetype)\s*:\s*([A-Za-z][A-Za-z0-9_ \-]*)\s*$',
            r'(?i)(?:case\s*type|casetype)\s*:\s*([A-Za-z][A-Za-z0-9_ \-]+)',
        ]
        
        case_type = None
        for pattern in case_type_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                case_type = match.group(1).strip()
                break
        
        resolved_case_type = case_type or title or 'Entity'
        self.schema['case_type'] = resolved_case_type

        entity_source = file_name or title or table_name or ''
        entity_name = entity_source
        if entity_name.lower().startswith('frm') and entity_name.lower().endswith('.php'):
            entity_name = entity_name[3:-4]
        elif entity_name.lower().startswith('tbl'):
            entity_name = entity_name[3:]
        entity_name = re.sub(r'[^A-Za-z0-9_\-\s]', '', entity_name).strip()
        if entity_name:
            self.schema['entity'] = entity_name
    
    def _parse_primary_key(self, user_request: str):
        """Extract primary key field"""
        logger.info("   Parsing primary key...")
        
        # Look for explicit primary key declaration
        pk_patterns = [
            r'(?i)primary[_\s]+key\s*:\s*[-*]?\s*([A-Za-z_][A-Za-z0-9_]*)',
            r'(?i)primary\s+key\s*:\s*[-*]?\s*([A-Za-z_][A-Za-z0-9_]*)',
            r'(?i)pk\s*:\s*([A-Za-z_][A-Za-z0-9_]*)',
        ]
        
        primary_key = None
        for pattern in pk_patterns:
            match = re.search(pattern, user_request, re.MULTILINE)
            if match:
                primary_key = match.group(1).strip()
                break
        
        if not primary_key:
            # Try to infer from first field if it's marked as PRIMARY KEY
            field_match = re.search(
                r'(?i)[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|[^|]*PRIMARY\s+KEY',
                user_request
            )
            if field_match:
                primary_key = field_match.group(1).strip()
        
        if not primary_key:
            self.warnings.append("primary key not specified, will default to 'Code'")
            primary_key = 'Code'
        
        self.schema['primary_key'] = primary_key
    
    def _parse_fields(self, user_request: str):
        """Extract field definitions"""
        logger.info("   Parsing fields...")
        
        fields = []
        seen_fields = set()
        section_headers = []
        section_patterns = [
            (r'(?i)\b(master\s*fields?|master\s*table|header\s*fields|main\s*fields)\b\s*(?:\([^)]*\))?\s*:', 'master'),
            (r'(?i)\b(detail\s*grid|child\s*fields|line\s*items|detail\s*fields|grid\s*fields|subgrid)\b\s*(?:\([^)]*\))?\s*:', 'detail'),
            (r'(?i)\b(dependencies|pre-?delete|relationships|features|business\s*validations?|business\s*rules?)\b\s*(?:\([^)]*\))?\s*:', 'meta'),
        ]
        for pattern, section_name in section_patterns:
            for match in re.finditer(pattern, user_request or '', re.IGNORECASE):
                section_headers.append((match.start(), section_name))
        section_headers.sort(key=lambda item: item[0])
        
        # Pattern: - Field_Name | DB: VARCHAR(20) | Input: textbox | Required: Yes
        # Note: This should NOT match relationship lines (those have ->)
        field_pattern = re.compile(r'(?im)^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|([^\n]+)$')
        
        for match in field_pattern.finditer(user_request or ''):
            field_name = match.group(1).strip()
            field_spec = match.group(2).strip()
            current_section = "master"
            for header_pos, header_section in section_headers:
                if header_pos <= match.start():
                    current_section = header_section
                else:
                    break

            # Ignore bullets from meta sections (dependencies/relationships/features/etc).
            if current_section not in {'master', 'detail'}:
                continue

            field_spec = re.split(
                r'(?i)\b(?:master\s*fields?|detail\s*grid|detail\s*table|detail\s*fields?|'
                r'dependencies|relationships|features|business\s*validations?|business\s*rules?)\b\s*(?:\([^)]*\))?\s*:',
                field_spec,
                maxsplit=1
            )[0].strip()
            if not field_spec:
                continue
            
            # Skip if this looks like a relationship (has ->)
            if '->' in field_spec or '->' in field_name:
                continue
            
            # Skip if this looks like a dependency (has field= or message=)
            if 'field=' in field_spec or 'message=' in field_spec:
                continue
            
            # Skip duplicate fields
            if field_name in seen_fields:
                continue
            seen_fields.add(field_name)
            
            # Parse field attributes
            tokens = [token.strip() for token in field_spec.split('|') if token.strip()]
            inferred_input_type = None
            token_input_types = {
                'text': 'textbox',
                'textbox': 'textbox',
                'input': 'textbox',
                'select': 'select',
                'dropdown': 'select',
                'checkbox': 'checkbox',
                'textarea': 'textarea',
                'date': 'date',
                'number': 'number',
                'numeric': 'number',
            }
            token_lookup = {token.lower() for token in tokens}
            for token in tokens:
                normalized_token = token.lower()
                if normalized_token in token_input_types:
                    inferred_input_type = token_input_types[normalized_token]
                    break

            inferred_required = None
            if 'required' in token_lookup:
                inferred_required = True
            elif 'optional' in token_lookup:
                inferred_required = False

            inferred_readonly = None
            readonly_tokens = {'readonly', 'read only', 'auto', 'auto-generated', 'auto generated'}
            if token_lookup.intersection(readonly_tokens):
                inferred_readonly = True

            field = {
                'name': field_name,
                'db_type': self._extract_attribute(field_spec, r'DB\s*:\s*([^|]+)'),
                'input_type': self._extract_attribute(field_spec, r'Input\s*:\s*([^|]+)') or inferred_input_type,
                'required': self._extract_boolean(field_spec, r'Required\s*:\s*(Yes|No|True|False)'),
                'readonly': self._extract_boolean(field_spec, r'(?:Readonly|Read\s*only)\s*:\s*(Yes|No|True|False)'),
                'section': current_section,
            }

            if field.get('required') is None and inferred_required is not None:
                field['required'] = inferred_required
            if field.get('readonly') is None and inferred_readonly is not None:
                field['readonly'] = inferred_readonly
            
            # Clean up None values
            field = {k: v for k, v in field.items() if v is not None}
            
            fields.append(field)
            logger.info(f"      Parsed field: {field_name} ({field.get('db_type', 'no type')})")
        
        if not fields:
            fallback_fields = self._parse_simple_fields(user_request, seen_fields)
            if fallback_fields:
                fields.extend(fallback_fields)
                logger.info(f"      Fallback extracted {len(fallback_fields)} simple field lines")

        if not fields:
            self.errors.append("no fields found - at least one field is required")
        else:
            self.schema['fields'] = fields
            logger.info(f"      ✅ Found {len(fields)} fields total")
    
    def _parse_relationships(self, user_request: str):
        """Extract relationship definitions"""
        logger.info("   Parsing relationships...")
        
        relationships = []
        
        # Pattern: - Field_Name -> tbltarget.Target_Field | Input: select | Cascade: Yes
        # OR: - Field_Name -> tbltarget.Target_Field (without additional attributes)
        rel_pattern = r'(?i)^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*->\s*([a-z][a-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)(?:\s*\|([^\n]+))?'
        
        for match in re.finditer(rel_pattern, user_request, re.MULTILINE):
            field_name = match.group(1).strip()
            reference = match.group(2).strip()
            rel_spec = match.group(3).strip() if match.group(3) else ''
            
            relationship = {
                'field': field_name,
                'references': reference,
                'cascade': self._extract_boolean(rel_spec, r'Cascade\s*:\s*(Yes|No|True|False)'),
                'input_type': self._extract_attribute(rel_spec, r'Input\s*:\s*([^|]+)'),
            }
            
            # Clean up None values
            relationship = {k: v for k, v in relationship.items() if v is not None}
            
            relationships.append(relationship)
        
        if relationships:
            self.schema['relationships'] = relationships
            logger.info(f"      Found {len(relationships)} relationships")
    
    def _parse_dependencies(self, user_request: str):
        """Extract dependency definitions for pre-delete checks"""
        logger.info("   Parsing dependencies...")
        
        dependencies = []
        
        # Pattern: - tbltarget | field=Field_Name | message=Cannot delete...
        dep_pattern = r'(?i)^\s*[-*]\s*([a-z][a-z0-9_]*)\s*\|\s*field\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*message\s*=\s*([^|\n]+)'
        
        for match in re.finditer(dep_pattern, user_request, re.MULTILINE):
            table = match.group(1).strip()
            field = match.group(2).strip()
            message = match.group(3).strip()
            
            dependency = {
                'table': table,
                'field': field,
                'message': message
            }
            
            dependencies.append(dependency)
        
        if dependencies:
            self.schema['dependencies'] = dependencies
            logger.info(f"      Found {len(dependencies)} dependencies")
    
    def _parse_features(self, user_request: str):
        """Extract requested features"""
        logger.info("   Parsing features...")
        
        features = []
        
        # Feature keywords
        feature_keywords = {
            'dropdown': r'(?i)\b(dropdown|select|cascading)\b',
            'validation': r'(?i)\b(validation|validate|formvalidation)\b',
            'keyboard': r'(?i)\b(keyboard|navigation|keycode)\b',
            'predelete': r'(?i)\b(pre-?delete|dependency\s+check)\b',
            'grid': r'(?i)\b(grid|detail|master-detail)\b',
            'chart': r'(?i)\b(chart|graph)\b',
            'select2': r'(?i)\bselect2\b',
            'ajax': r'(?i)\bajax\b',
        }
        
        for feature, pattern in feature_keywords.items():
            if re.search(pattern, user_request):
                features.append(feature)
        
        if features:
            self.schema['features'] = features
            logger.info(f"      Found features: {', '.join(features)}")

    def _infer_title(self, user_request: str, file_name: str = None, table_name: str = None) -> str:
        """
        Infer title when explicit "Title:" line is missing.
        """
        prompt = str(user_request or '').strip()

        phrase_patterns = [
            r'(?i)\bcreate\b[^.\n]{0,180}?\b([A-Za-z][A-Za-z0-9_ ]{1,80})\s+form\b',
            r'(?i)\b([A-Za-z][A-Za-z0-9_ ]{1,80})\s+form\b',
        ]
        for pattern in phrase_patterns:
            match = re.search(pattern, prompt)
            if not match:
                continue

            candidate = re.sub(r'\s+', ' ', match.group(1)).strip()
            candidate = re.sub(
                r'(?i)^(?:a|an|the)?\s*(?:complete|simple|new|full|production-?ready)?\s*',
                '',
                candidate
            ).strip()
            candidate = re.sub(r'(?i)\b(?:as|with|using|in)\b.*$', '', candidate).strip()
            if candidate:
                return self._title_from_token(candidate)

        if file_name:
            stem = re.sub(r'(?i)\.php$', '', str(file_name).strip())
            if stem.lower().startswith('frm'):
                stem = stem[3:]
            if stem:
                return self._title_from_token(stem)

        if table_name:
            stem = str(table_name).strip()
            if stem.lower().startswith('tbl'):
                stem = stem[3:]
            if stem:
                return self._title_from_token(stem)

        return ''

    def _title_from_token(self, token: str) -> str:
        cleaned = re.sub(r'[^A-Za-z0-9_\-\s]', ' ', str(token or ''))
        cleaned = re.sub(r'[_\-]+', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            return ''
        return ' '.join(word[:1].upper() + word[1:] for word in cleaned.split())

    def _parse_simple_fields(self, user_request: str, seen_fields: set) -> List[Dict[str, Any]]:
        """
        Fallback field parser for compact/plain field lines like:
        txtRollNo (required)
        Id (auto max+1, readonly)
        """
        parsed_fields: List[Dict[str, Any]] = []
        in_fields_section = False
        current_section = 'master'

        section_start_pattern = re.compile(
            r'(?i)^\s*(?:[-*]\s*)?'
            r'(master\s*fields?|fields?|header\s*fields|main\s*fields|'
            r'detail\s*grid|detail\s*fields?|child\s*fields|line\s*items)\s*:'
        )
        detail_section_pattern = re.compile(
            r'(?i)^\s*(?:[-*]\s*)?(detail\s*grid|detail\s*fields?|child\s*fields|line\s*items)\s*:'
        )
        section_stop_pattern = re.compile(
            r'(?i)^\s*(?:[-*]\s*)?'
            r'(dependencies?|relationships?|features?|business\s*rules?|business\s*validations?|'
            r'company\s*rules?|output|crud|module\s*details|primary\s*key)\s*:'
        )

        for raw_line in str(user_request or '').splitlines():
            line = raw_line.strip()
            if not line:
                continue

            if section_start_pattern.match(line):
                in_fields_section = True
                current_section = 'detail' if detail_section_pattern.match(line) else 'master'
                continue

            if in_fields_section and section_stop_pattern.match(line):
                in_fields_section = False
                continue

            if not in_fields_section:
                continue

            candidate = re.sub(r'^\s*[-*]\s*', '', line).strip()
            if not candidate:
                continue

            lowered = candidate.lower()
            if '->' in candidate or 'field=' in lowered or 'message=' in lowered:
                continue
            if ':' in candidate and '(' not in candidate and ')' not in candidate:
                continue

            name_match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)', candidate)
            if not name_match:
                continue

            field_name = name_match.group(1).strip()
            if field_name in seen_fields:
                continue
            seen_fields.add(field_name)

            field: Dict[str, Any] = {
                'name': field_name,
                'section': current_section,
            }

            if re.search(r'(?i)\brequired\b', candidate):
                field['required'] = True
            if re.search(r'(?i)\b(read\s*only|readonly|auto|max\+?1|auto-generated|auto generated)\b', candidate):
                field['readonly'] = True

            if re.search(r'(?i)\bhidden\b', candidate):
                field['input_type'] = 'hidden'
            elif re.search(r'(?i)\b(select|dropdown)\b', candidate):
                field['input_type'] = 'select'
            elif re.search(r'(?i)\bcheckbox\b', candidate):
                field['input_type'] = 'checkbox'
            elif re.search(r'(?i)\b(date|dob)\b', candidate):
                field['input_type'] = 'date'
            else:
                field['input_type'] = 'textbox'

            parsed_fields.append(field)

        return parsed_fields
    
    def _extract_attribute(self, text: str, pattern: str) -> Optional[str]:
        """Extract attribute value from text"""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_boolean(self, text: str, pattern: str) -> Optional[bool]:
        """Extract boolean value from text"""
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1).strip().lower()
            return value in ['yes', 'true', '1']
        return None
    
    def _validate_schema(self):
        """Validate schema completeness"""
        logger.info("   Validating schema completeness...")
        
        # Check required fields
        required_fields = ['table', 'filename', 'title', 'primary_key', 'fields']
        
        for field in required_fields:
            if field not in self.schema:
                self.errors.append(f"required field '{field}' is missing from schema")
                continue
            value = self.schema.get(field)
            if isinstance(value, str) and not value.strip():
                self.errors.append(f"required field '{field}' is blank in schema")
            if isinstance(value, list) and len(value) == 0:
                self.errors.append(f"required field '{field}' is empty in schema")
        
        # Validate fields have minimum required attributes
        if 'fields' in self.schema:
            for idx, field in enumerate(self.schema['fields']):
                if 'name' not in field:
                    self.errors.append(f"field at index {idx} is missing 'name' attribute")
        
        # Raise error if critical issues found
        if self.errors:
            error_msg = "❌ SCHEMA PARSING FAILED:\n" + "\n".join(f"  - {err}" for err in self.errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
    
    def _log_parsing_results(self):
        """Log parsing results"""
        logger.info("✅ Schema parsing complete:")
        logger.info(f"   Table: {self.schema.get('table', 'N/A')}")
        logger.info(f"   Filename: {self.schema.get('filename', 'N/A')}")
        logger.info(f"   Title: {self.schema.get('title', 'N/A')}")
        logger.info(f"   Primary Key: {self.schema.get('primary_key', 'N/A')}")
        logger.info(f"   Fields: {len(self.schema.get('fields', []))} defined")
        logger.info(f"   Relationships: {len(self.schema.get('relationships', []))} defined")
        logger.info(f"   Dependencies: {len(self.schema.get('dependencies', []))} defined")
        logger.info(f"   Features: {', '.join(self.schema.get('features', [])) or 'None'}")
        
        if self.warnings:
            logger.warning(f"   Warnings: {len(self.warnings)}")
            for warning in self.warnings:
                logger.warning(f"      - {warning}")
    
    def get_schema(self) -> Dict[str, Any]:
        """Get parsed schema"""
        return self.schema
    
    def get_errors(self) -> List[str]:
        """Get parsing errors"""
        return self.errors
    
    def get_warnings(self) -> List[str]:
        """Get parsing warnings"""
        return self.warnings
