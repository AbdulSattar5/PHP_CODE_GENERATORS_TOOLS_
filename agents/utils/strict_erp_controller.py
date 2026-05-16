"""
Strict ERP controller utilities.

This module provides the deterministic preflight gate requested for
enterprise PHP ERP form generation:
1. Parse a strict prompt contract.
2. Ensure persistent pattern memory exists for the selected codebase.
3. Retrieve patterns by form type + features, not by unrelated files.
4. Record success/failure/contamination learning signals.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from django.contrib.auth import get_user_model
from django.db import transaction

from agents.utils.request_parser import RequestSchemaParser, normalize_request_text
from models.project import PatternLearningEvent, PatternMemory

logger = logging.getLogger(__name__)
UserModel = get_user_model()


CORE_COMPANY_FUNCTIONS = [
    'db_insert',
    'db_update',
    'db_delete',
    'db_getRecord',
    'getvalue',
    'getrows',
    'getrows2',
    'funStartTran',
    'funEndTran',
    'fun_log',
]

MANDATORY_SESSION_KEYS = [
    'user_id',
    'comp_code',
    'login_id',
]

BASE_REQUIRED_PATTERNS = [
    'CRUD_PATTERN',
    'TEMPLATE_PATTERN',
    'SESSION_PATTERN',
    'SECURITY_PATTERN',
]

MIN_RETRIEVAL_QUALITY = 0.30
MIN_PATTERN_COVERAGE = 0.75


class StrictPromptContractParser:
    """
    Convert a user request into a strict ERP contract.
    The contract is intentionally explicit so generation can be blocked early
    when the request is underspecified.
    """

    def parse(self, user_request: str) -> Dict[str, Any]:
        parser = RequestSchemaParser()
        errors: List[str] = []
        parse_failed = False
        normalized_request = normalize_request_text(user_request)

        try:
            base = parser.parse(normalized_request)
        except Exception as exc:
            parse_failed = True
            base = parser.get_schema() or {}
            errors.extend(parser.get_errors())
            if not parser.get_errors():
                errors.append(f"request schema parser failed: {exc}")

        detail_table = str(base.get('detail_table') or '').strip() or self._extract_detail_table(normalized_request)
        # Single source of truth for master fields: RequestSchemaParser output.
        # Section-specific extraction is only used as a fallback.
        master_fields = list(base.get('fields', []) or [])
        detail_fields = self._extract_detail_fields(normalized_request)
        detail_field_names = {
            str(field.get('name') or '').strip().lower()
            for field in detail_fields
            if str(field.get('name') or '').strip()
        }
        if master_fields and detail_field_names:
            master_fields = [
                field for field in master_fields
                if str(field.get('name') or '').strip().lower() not in detail_field_names
            ]
        if not master_fields:
            master_fields = self._extract_master_fields(normalized_request)
        relationships = list(base.get('relationships', []) or [])
        dependencies = list(base.get('dependencies', []) or [])
        if parse_failed and not base:
            errors.append("parsed schema is empty after parser failure")

        if not self._has_explicit_primary_key(normalized_request):
            inferred_primary_key = self._infer_primary_key_from_fields(master_fields)
            if inferred_primary_key:
                current_pk = str(base.get('primary_key') or '').strip()
                if not current_pk or current_pk.lower() == 'code':
                    base['primary_key'] = inferred_primary_key
            logger.info(
                "Strict contract: no explicit primary key directive; continuing with inferred/default PK '%s'",
                str(base.get('primary_key') or '').strip() or 'Code',
            )

        if detail_table and not detail_fields:
            errors.append("detail table declared but detail fields are missing")

        entity = self._build_entity_name(
            filename=base.get('filename'),
            title=base.get('title'),
            table_name=base.get('table'),
        )
        if not entity:
            errors.append("entity could not be derived from title/filename/table")

        features = self._extract_features(normalized_request, base, detail_table, detail_fields)
        form_type = self._classify_form_type(detail_table, detail_fields, features, relationships)

        contract = {
            'entity': entity,
            'file_name': base.get('filename', ''),
            'title': base.get('title', ''),
            'master_table': base.get('table', ''),
            'detail_table': detail_table,
            'primary_key': base.get('primary_key', ''),
            'form_type': form_type,
            'features': features,
            'master_fields': master_fields,
            'detail_fields': detail_fields,
            'relationships': relationships,
            'dependencies': dependencies,
            'pre_delete_checks': dependencies,
            'required_sections': [
                'VARIABLE_INIT_PHP',
                'AJAX_HANDLERS_PHP',
                'CRUD_LOGIC_PHP',
                'FORM_FIELDS_HTML',
                'FORM_VALIDATION_FIELDS',
                'SELECT2_HANDLERS',
                'ENTITY_JS',
            ],
            'errors': [],
        }

        required_pairs = {
            'file_name': contract['file_name'],
            'title': contract['title'],
            'master_table': contract['master_table'],
            'primary_key': contract['primary_key'],
        }
        for key, value in required_pairs.items():
            if not str(value or '').strip():
                errors.append(f"{key} is required")

        if not contract['master_fields']:
            errors.append("master_fields are required")

        contract['errors'] = list(dict.fromkeys(error for error in errors if error))
        contract['valid'] = not contract['errors']
        return contract

    def _extract_detail_table(self, user_request: str) -> str:
        match = re.search(
            r'(?im)^\s*(?:[-*]\s*)?detail(?:\s+|_)table\s*:\s*([A-Za-z_][A-Za-z0-9_]*)\s*$',
            normalize_request_text(user_request or ''),
        )
        return match.group(1).strip() if match else ''

    def _extract_detail_fields(self, user_request: str) -> List[Dict[str, Any]]:
        return self._extract_fields_from_section(
            user_request=user_request,
            section_pattern=(
                r'(?is)(?:detail(?:\s+|_)grid|detail(?:\s+|_)fields?)\s*(?:\([^)]+\))?\s*:\s*(.*?)'
                r'(?:relationships?\s*(?:\([^)]+\))?\s*:|dependencies?\s*(?:\([^)]+\))?\s*:|business(?:\s+|_)validations?\s*(?:\([^)]+\))?\s*:|operations\s*(?:\([^)]+\))?\s*:|'
                r'required(?:\s+company)?\s+(?:patterns|functions)\s*:|output\s*:|$)'
            ),
        )

    def _extract_master_fields(self, user_request: str) -> List[Dict[str, Any]]:
        return self._extract_fields_from_section(
            user_request=user_request,
            section_pattern=(
                r'(?is)master(?:\s+|_)fields?(?:\s*\([^)]+\))?\s*:\s*(.*?)'
                r'(?:detail(?:\s+|_)grid\s*(?:\([^)]+\))?\s*:|detail(?:\s+|_)fields?\s*(?:\([^)]+\))?\s*:|relationships?\s*(?:\([^)]+\))?\s*:|dependencies?\s*(?:\([^)]+\))?\s*:|'
                r'business(?:\s+|_)validations?\s*(?:\([^)]+\))?\s*:|operations\s*(?:\([^)]+\))?\s*:|required(?:\s+company)?\s+(?:patterns|functions)\s*:|output\s*:|$)'
            ),
        )

    def _extract_fields_from_section(self, user_request: str, section_pattern: str) -> List[Dict[str, Any]]:
        normalized_request = normalize_request_text(user_request or '')
        section_match = re.search(
            section_pattern,
            normalized_request,
        )
        if not section_match:
            return []

        fields: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for match in re.finditer(
            r'(?im)^\s*[-*]\s*([A-Za-z_][A-Za-z0-9_]*)\s*\|([^\n]+)$',
            section_match.group(1),
        ):
            field_name = match.group(1).strip()
            if field_name in seen:
                continue
            seen.add(field_name)
            field_spec = match.group(2).strip()
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

            input_type = self._extract_attribute(field_spec, r'Input\s*:\s*([^|]+)') or inferred_input_type
            required = self._extract_bool(field_spec, r'Required\s*:\s*(Yes|No|True|False|Mandatory)')
            readonly = self._extract_bool(field_spec, r'(?:Readonly|Read\s*only)\s*:\s*(Yes|No|True|False)')
            if required is None and inferred_required is not None:
                required = inferred_required
            if readonly is None and inferred_readonly is not None:
                readonly = inferred_readonly
            fields.append({
                'name': field_name,
                'db_type': self._extract_attribute(field_spec, r'DB\s*:\s*([^|]+)'),
                'input_type': input_type,
                'required': required,
                'readonly': readonly,
            })
        return fields

    def _extract_features(
        self,
        user_request: str,
        parsed_schema: Dict[str, Any],
        detail_table: str,
        detail_fields: Sequence[Dict[str, Any]],
    ) -> List[str]:
        text = (user_request or '').lower()
        features = set(str(feature).lower() for feature in parsed_schema.get('features', []) or [])

        if detail_table or detail_fields or 'txtcountacc' in text:
            features.add('txtcountacc')
        if 'getmaxid' in text or 'maxid(' in text:
            features.add('getmaxid')
            features.add('ajax')
        if 'ajax' in text:
            features.add('ajax')
        if 'select2' in text:
            features.add('select2')
        if 'formvalidation' in text or 'validation' in text:
            features.add('validation')
        if 'checkkeycode' in text or 'keyboard' in text:
            features.add('keyboard')
        if 'dependent dropdown' in text or 'cascading' in text or 'cascade' in text:
            features.add('dependent_dropdown')
            features.add('ajax')
        if parsed_schema.get('relationships'):
            for rel in parsed_schema.get('relationships', []):
                if rel.get('cascade'):
                    features.add('dependent_dropdown')
                    features.add('ajax')
        return sorted(features)

    def _classify_form_type(
        self,
        detail_table: str,
        detail_fields: Sequence[Dict[str, Any]],
        features: Sequence[str],
        relationships: Sequence[Dict[str, Any]],
    ) -> str:
        lowered_features = {str(feature).lower() for feature in features or []}
        if detail_table or detail_fields or 'txtcountacc' in lowered_features:
            return 'MASTER_DETAIL'
        if 'dependent_dropdown' in lowered_features:
            return 'DEPENDENT'
        for rel in relationships or []:
            if rel.get('cascade'):
                return 'DEPENDENT'
        return 'SIMPLE'

    def _has_explicit_primary_key(self, user_request: str) -> bool:
        return bool(
            re.search(r'(?i)\bprimary\s+key\s*:', user_request or '')
            or re.search(r'(?i)\bprimary_key\s*:', user_request or '')
            or re.search(r'(?i)\bPRIMARY\s+KEY\b', user_request or '')
        )

    def _infer_primary_key_from_fields(self, fields: Sequence[Dict[str, Any]]) -> str:
        candidates = [str((field or {}).get('name') or '').strip() for field in fields or []]
        candidates = [name for name in candidates if name]
        if not candidates:
            return ''

        priority_exact = {'id', 'code', 'pk', 'uid'}
        for name in candidates:
            if name.lower() in priority_exact:
                return name

        priority_suffixes = ('_id', '_code', 'code')
        for name in candidates:
            lowered = name.lower()
            if lowered.endswith(priority_suffixes):
                return name

        return ''

    def _build_entity_name(self, filename: str, title: str, table_name: str) -> str:
        candidates = [filename, title, table_name]
        for candidate in candidates:
            value = str(candidate or '').strip()
            if not value:
                continue
            value = os.path.basename(value)
            value = re.sub(r'\.php$', '', value, flags=re.IGNORECASE)
            value = re.sub(r'^(frm|tbl)', '', value, flags=re.IGNORECASE)
            tokens = [token for token in re.split(r'[_\-\s]+', value) if token]
            if tokens:
                return ''.join(token[:1].upper() + token[1:] for token in tokens)
        return ''

    def _extract_attribute(self, text: str, pattern: str) -> str:
        match = re.search(pattern, text or '', re.IGNORECASE)
        return match.group(1).strip() if match else ''

    def _extract_bool(self, text: str, pattern: str) -> bool:
        match = re.search(pattern, text or '', re.IGNORECASE)
        if not match:
            return False
        return str(match.group(1)).strip().lower() in {'yes', 'true', '1', 'mandatory'}


class PatternMemoryService:
    """
    Persistent, weighted pattern memory manager.
    """

    def _resolve_user_filter_kwargs(self, user_id: str) -> Dict[str, Any]:
        normalized_user_id = str(user_id or '').strip()
        if not normalized_user_id:
            return {}
        if normalized_user_id.isdigit():
            return {'user_id': int(normalized_user_id)}
        if UserModel.objects.filter(username=normalized_user_id).exists():
            return {'user__username': normalized_user_id}
        if UserModel.objects.filter(email=normalized_user_id).exists():
            return {'user__email': normalized_user_id}
        return {}

    def _resolve_user_fk_kwargs(self, user_id: str) -> Dict[str, Any]:
        normalized_user_id = str(user_id or '').strip()
        if not normalized_user_id:
            return {}
        if normalized_user_id.isdigit():
            return {'user_id': int(normalized_user_id)}
        user = (
            UserModel.objects.filter(username=normalized_user_id).first()
            or UserModel.objects.filter(email=normalized_user_id).first()
        )
        if user:
            return {'user_id': int(user.id)}
        return {}

    def ensure_memory(
        self,
        user_id: str,
        codebase_id: str,
        analyzed_patterns: Optional[Dict[str, Any]] = None,
    ) -> List[PatternMemory]:
        if not codebase_id:
            return []

        user_filter_kwargs = self._resolve_user_filter_kwargs(user_id)
        if not user_filter_kwargs:
            logger.warning("Pattern memory lookup skipped: unresolved user reference '%s'", user_id)
            return []

        existing = list(
            PatternMemory.objects.filter(codebase_id=codebase_id, **user_filter_kwargs)
            .order_by('pattern_type', 'form_type')
        )
        if existing:
            return existing

        if not analyzed_patterns:
            return []

        return self.bootstrap_from_analyzed_patterns(user_id, codebase_id, analyzed_patterns)

    def bootstrap_from_analyzed_patterns(
        self,
        user_id: str,
        codebase_id: str,
        analyzed_patterns: Dict[str, Any],
    ) -> List[PatternMemory]:
        entries = self._build_memory_entries(analyzed_patterns)
        if not entries:
            return []

        user_fk_kwargs = self._resolve_user_fk_kwargs(user_id)
        if not user_fk_kwargs:
            logger.warning("Pattern memory bootstrap skipped: unresolved user reference '%s'", user_id)
            return []

        created_records: List[PatternMemory] = []
        with transaction.atomic():
            for entry in entries:
                record, _ = PatternMemory.objects.update_or_create(
                    codebase_id=codebase_id,
                    pattern_type=entry['pattern_type'],
                    form_type=entry['form_type'],
                    feature_signature=entry['feature_signature'],
                    **user_fk_kwargs,
                    defaults={
                        'payload': entry['payload'],
                        'required_functions': entry['required_functions'],
                        'structure_skeleton': entry['structure_skeleton'],
                        'constraints': entry['constraints'],
                        'examples': entry['examples'],
                    },
                )
                created_records.append(record)
        logger.info(
            "Bootstrapped %s strict pattern memory records for codebase %s",
            len(created_records),
            codebase_id,
        )
        return created_records

    def retrieve(
        self,
        *,
        user_id: str,
        codebase_id: str,
        contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        required_types = self.required_pattern_types(contract)
        feature_signature = self._feature_signature(contract.get('features', []))
        user_filter_kwargs = self._resolve_user_filter_kwargs(user_id)
        if not user_filter_kwargs:
            return {
                'selected_patterns': [],
                'top_candidates': [],
                'pattern_coverage': 0.0,
                'retrieval_quality': 0.0,
                'required_pattern_types': required_types,
                'feature_signature': feature_signature,
                'memory_context': '',
                'combo_signature': self.combo_signature(codebase_id, contract, required_types),
                'reason': 'unresolved_user_reference',
                'block_generation': True,
            }
        pattern_queryset = PatternMemory.objects.filter(codebase_id=codebase_id, **user_filter_kwargs)

        selected_patterns: List[Dict[str, Any]] = []
        top_candidates: List[Dict[str, Any]] = []
        matched_required = 0

        for required_type in required_types:
            candidates = list(pattern_queryset.filter(pattern_type=required_type))
            if not candidates:
                top_candidates.append({
                    'pattern_type': required_type,
                    'score': 0.0,
                    'reason': 'missing_pattern_type',
                })
                continue

            best_payload: Optional[Dict[str, Any]] = None
            best_score = -1.0
            for candidate in candidates:
                score = self._score_candidate(candidate, contract)
                candidate_summary = {
                    'id': str(candidate.id),
                    'pattern_type': candidate.pattern_type,
                    'form_type': candidate.form_type,
                    'feature_signature': candidate.feature_signature,
                    'weight': candidate.weight,
                    'score': round(score, 4),
                }
                top_candidates.append(candidate_summary)
                if score > best_score:
                    best_score = score
                    best_payload = self._serialize_pattern(candidate, score)

            if best_payload:
                selected_patterns.append(best_payload)
                if best_score >= MIN_RETRIEVAL_QUALITY:
                    matched_required += 1

        pattern_coverage = (
            matched_required / len(required_types)
            if required_types else 0.0
        )
        retrieval_quality = (
            sum(pattern['score'] for pattern in selected_patterns) / len(selected_patterns)
            if selected_patterns else 0.0
        )
        combo_signature = self.combo_signature(codebase_id, contract, required_types)
        combo_blacklist_filter = self._resolve_user_filter_kwargs(user_id)
        combo_blacklisted = bool(combo_blacklist_filter) and PatternLearningEvent.objects.filter(
            codebase_id=codebase_id,
            pattern_combo_signature=combo_signature,
            is_blacklisted_combo=True,
            **combo_blacklist_filter,
        ).exists()

        block_generation = bool(
            combo_blacklisted
            or retrieval_quality < MIN_RETRIEVAL_QUALITY
            or pattern_coverage < MIN_PATTERN_COVERAGE
        )

        if combo_blacklisted:
            reason = 'pattern_combo_blacklisted'
        elif retrieval_quality < MIN_RETRIEVAL_QUALITY:
            reason = 'retrieval_quality_below_floor'
        elif pattern_coverage < MIN_PATTERN_COVERAGE:
            reason = 'pattern_coverage_below_floor'
        else:
            reason = 'approved'

        return {
            'required_pattern_types': required_types,
            'selected_patterns': selected_patterns,
            'top_candidates': top_candidates,
            'feature_signature': feature_signature,
            'pattern_coverage': round(pattern_coverage, 4),
            'retrieval_quality': round(retrieval_quality, 4),
            'combo_signature': combo_signature,
            'combo_blacklisted': combo_blacklisted,
            'block_generation': block_generation,
            'needs_revision': block_generation,
            'reason': reason,
            'memory_context': self.render_generation_context(selected_patterns),
        }

    def required_pattern_types(self, contract: Dict[str, Any]) -> List[str]:
        required = list(BASE_REQUIRED_PATTERNS)
        features = {str(feature).lower() for feature in contract.get('features', []) or []}
        form_type = str(contract.get('form_type') or 'SIMPLE').upper()

        if form_type == 'MASTER_DETAIL':
            required.append('MASTER_DETAIL_PATTERN')
        if form_type == 'DEPENDENT' or {'ajax', 'getmaxid', 'dependent_dropdown', 'dropdown'} & features:
            required.append('AJAX_PATTERN')
        if 'validation' in features:
            required.append('VALIDATION_PATTERN')
        if 'select2' in features:
            required.append('SELECT2_PATTERN')

        seen: Set[str] = set()
        ordered: List[str] = []
        for pattern_type in required:
            if pattern_type not in seen:
                seen.add(pattern_type)
                ordered.append(pattern_type)
        return ordered

    def combo_signature(
        self,
        codebase_id: str,
        contract: Dict[str, Any],
        required_pattern_types: Sequence[str],
    ) -> str:
        form_type = str(contract.get('form_type') or 'SIMPLE').upper()
        feature_signature = self._feature_signature(contract.get('features', []))
        pattern_signature = '+'.join(sorted(required_pattern_types))
        return f"{codebase_id}|{form_type}|{feature_signature}|{pattern_signature}"

    def render_generation_context(self, selected_patterns: Sequence[Dict[str, Any]]) -> str:
        if not selected_patterns:
            return ''

        chunks: List[str] = [
            "STRICT ERP PATTERN MEMORY",
            "Use these company patterns as the authoritative retrieval context.",
        ]
        for pattern in selected_patterns:
            chunks.append(f"[{pattern['pattern_type']}] form_type={pattern['form_type']} score={pattern['score']:.2f}")
            if pattern.get('required_functions'):
                chunks.append(f"required_functions: {', '.join(pattern['required_functions'])}")
            if pattern.get('constraints'):
                chunks.append(f"constraints: {'; '.join(pattern['constraints'][:6])}")
            if pattern.get('structure_skeleton'):
                chunks.append(
                    "structure: " + json.dumps(pattern['structure_skeleton'], ensure_ascii=True, sort_keys=True)
                )
            if pattern.get('examples'):
                example_text = ' | '.join(str(example) for example in pattern['examples'][:5])
                chunks.append(f"examples: {example_text}")
            chunks.append("")
        return '\n'.join(chunks).strip()

    def record_outcome(
        self,
        *,
        user_id: str,
        codebase_id: Optional[str],
        project_id: Optional[str],
        contract: Optional[Dict[str, Any]],
        retrieval: Optional[Dict[str, Any]],
        outcome: str,
        phase: str,
        failure_reason: str = '',
        validator_errors: Optional[Sequence[Any]] = None,
        section_sizes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[PatternLearningEvent]:
        if not codebase_id:
            return None
        user_fk_kwargs = self._resolve_user_fk_kwargs(user_id)
        if not user_fk_kwargs:
            logger.warning("Pattern learning event skipped: unresolved user reference '%s'", user_id)
            return None

        contract = contract or {}
        retrieval = retrieval or {}
        validator_errors = list(validator_errors or [])
        section_sizes = dict(section_sizes or {})
        metadata = dict(metadata or {})

        blacklisted = bool(outcome in {'contamination', 'low_coverage'})

        event = PatternLearningEvent.objects.create(
            project_id=project_id or None,
            codebase_id=codebase_id,
            pattern_combo_signature=retrieval.get('combo_signature', ''),
            selected_patterns=[
                {
                    'id': pattern.get('id'),
                    'pattern_type': pattern.get('pattern_type'),
                    'score': pattern.get('score'),
                }
                for pattern in retrieval.get('selected_patterns', []) or []
            ],
            outcome=outcome,
            phase=phase,
            form_type=str(contract.get('form_type') or ''),
            feature_signature=str(retrieval.get('feature_signature') or ''),
            entity_name=str(contract.get('entity') or ''),
            retrieval_quality=float(retrieval.get('retrieval_quality') or 0.0),
            pattern_coverage=float(retrieval.get('pattern_coverage') or 0.0),
            validator_errors=validator_errors,
            section_sizes=section_sizes,
            top_candidates=list(retrieval.get('top_candidates', []) or [])[:12],
            failure_reason=failure_reason or '',
            is_blacklisted_combo=blacklisted,
            metadata=metadata,
            **user_fk_kwargs,
        )

        self._update_pattern_weights(retrieval.get('selected_patterns', []) or [], outcome)
        return event

    def _update_pattern_weights(self, selected_patterns: Sequence[Dict[str, Any]], outcome: str) -> None:
        if not selected_patterns:
            return

        delta_map = {
            'success': 0.10,
            'failure': -0.05,
            'contamination': -0.30,
            'low_coverage': -0.15,
            'missing_memory': -0.10,
            'contract_reject': -0.05,
        }
        delta = delta_map.get(outcome, -0.05)
        pattern_ids = [pattern.get('id') for pattern in selected_patterns if pattern.get('id')]
        if not pattern_ids:
            return

        with transaction.atomic():
            for record in PatternMemory.objects.select_for_update().filter(id__in=pattern_ids):
                record.weight = max(0.1, min(5.0, float(record.weight or 1.0) + delta))
                if outcome == 'success':
                    record.success_count += 1
                elif outcome == 'contamination':
                    record.failure_count += 1
                    record.contamination_count += 1
                else:
                    record.failure_count += 1
                record.save(update_fields=[
                    'weight',
                    'success_count',
                    'failure_count',
                    'contamination_count',
                    'updated_at',
                ])

    def _build_memory_entries(self, analyzed_patterns: Dict[str, Any]) -> List[Dict[str, Any]]:
        php = analyzed_patterns.get('php', {}) if isinstance(analyzed_patterns, dict) else {}
        html = analyzed_patterns.get('html', {}) if isinstance(analyzed_patterns, dict) else {}
        js = analyzed_patterns.get('js', {}) if isinstance(analyzed_patterns, dict) else {}

        evidence_blob = json.dumps(analyzed_patterns, default=str).lower()
        raw_function_sources: List[Any] = list(php.get('functions', []) or [])
        for extra_key in ('database_functions', 'db_functions'):
            extra_values = php.get(extra_key, []) or analyzed_patterns.get(extra_key, []) or []
            if extra_values:
                raw_function_sources.extend(list(extra_values))
        function_names = self._normalize_names(raw_function_sources)
        table_names = self._normalize_names(php.get('table_names', []))
        field_names = self._normalize_names(php.get('field_names', []))
        ajax_functions = self._normalize_names(php.get('ajax_functions', []))
        include_patterns = self._normalize_names(php.get('include_patterns', []))
        validation_functions = self._normalize_names(php.get('validation_functions', []))
        css_classes = self._normalize_names(html.get('css_classes', []))
        grid_patterns = php.get('grid_patterns', []) if isinstance(php.get('grid_patterns', []), list) else []
        dynamic_dropdowns = php.get('dynamic_dropdowns', []) if isinstance(php.get('dynamic_dropdowns', []), list) else []

        detected_company_functions = [
            func for func in CORE_COMPANY_FUNCTIONS
            if func.lower() in {name.lower() for name in function_names}
        ]
        if not detected_company_functions:
            detected_company_functions = CORE_COMPANY_FUNCTIONS[:]

        has_txtcountacc = 'txtcountacc' in evidence_blob
        has_select2 = 'select2' in evidence_blob
        has_formvalidation = 'formvalidation' in evidence_blob
        has_htmlspecialchars = 'htmlspecialchars' in evidence_blob

        entries: List[Dict[str, Any]] = [
            self._pattern_entry(
                pattern_type='CRUD_PATTERN',
                form_type='ALL',
                feature_signature='crud',
                required_functions=detected_company_functions,
                structure_skeleton={
                    'crud_handlers': ['Save', 'Update', 'Delete', 'Edit'],
                    'auto_primary_key': True,
                    'company_db_api': True,
                },
                constraints=[
                    'Use company db_* functions only',
                    'Primary key must remain readonly/auto',
                    'LLM generates dynamic CRUD sections only',
                ],
                examples=(function_names + table_names + field_names)[:12],
                payload={
                    'tables': table_names[:20],
                    'fields': field_names[:40],
                    'functions': function_names[:20],
                },
            ),
            self._pattern_entry(
                pattern_type='TEMPLATE_PATTERN',
                form_type='ALL',
                feature_signature='template',
                required_functions=[],
                structure_skeleton={
                    'includes': include_patterns[:10],
                    'form_wrapper': html.get('form_structure', [])[:5] if isinstance(html.get('form_structure', []), list) else [],
                    'css_classes': css_classes[:20],
                },
                constraints=[
                    'Keep fixed company template outside LLM-generated sections',
                    'Exactly one form after integration',
                    'No nested form tags',
                ],
                examples=(include_patterns + css_classes)[:12],
                payload={
                    'includes': include_patterns[:20],
                    'css_classes': css_classes[:30],
                },
            ),
            self._pattern_entry(
                pattern_type='SESSION_PATTERN',
                form_type='ALL',
                feature_signature='session',
                required_functions=[],
                structure_skeleton={
                    'session_keys': MANDATORY_SESSION_KEYS,
                    'session_pattern': php.get('session_management'),
                },
                constraints=[
                    "$_SESSION['user_id'] must be available",
                    "$_SESSION['comp_code'] must be available",
                    "$_SESSION['login_id'] must be available",
                ],
                examples=[php.get('session_management')] if php.get('session_management') else MANDATORY_SESSION_KEYS[:],
                payload={
                    'session_keys': MANDATORY_SESSION_KEYS,
                    'session_management': php.get('session_management'),
                },
            ),
            self._pattern_entry(
                pattern_type='SECURITY_PATTERN',
                form_type='ALL',
                feature_signature='security',
                required_functions=detected_company_functions,
                structure_skeleton={
                    'escape_output': has_htmlspecialchars,
                    'forbidden_functions': ['mysql_query'],
                    'transactions': php.get('transaction_management', {}),
                },
                constraints=[
                    'No mysql_query or raw SQL concat',
                    'Escape output with htmlspecialchars',
                    'Use company db_* functions and transaction helpers',
                ],
                examples=[
                    'htmlspecialchars' if has_htmlspecialchars else '',
                    'funStartTran',
                    'funEndTran',
                ],
                payload={
                    'has_htmlspecialchars': has_htmlspecialchars,
                    'transaction_management': php.get('transaction_management', {}),
                },
            ),
        ]

        if ajax_functions or dynamic_dropdowns or 'getmaxid' in evidence_blob:
            entries.append(
                self._pattern_entry(
                    pattern_type='AJAX_PATTERN',
                    form_type='ALL',
                    feature_signature='ajax+dropdown+getmaxid',
                    required_functions=['getvalue', 'getrows'],
                    structure_skeleton={
                        'ajax_handlers': ajax_functions[:20],
                        'dependent_dropdowns': dynamic_dropdowns[:5],
                        'auto_id': 'getmaxid' in evidence_blob,
                    },
                    constraints=[
                        'AJAX handlers must be explicit server actions',
                        'GetMaxID and dropdown loaders should match company naming',
                    ],
                    examples=(ajax_functions + self._normalize_names(dynamic_dropdowns))[:12],
                    payload={
                        'ajax_functions': ajax_functions[:30],
                        'dynamic_dropdowns': dynamic_dropdowns[:8],
                    },
                )
            )

        if has_formvalidation or validation_functions:
            entries.append(
                self._pattern_entry(
                    pattern_type='VALIDATION_PATTERN',
                    form_type='ALL',
                    feature_signature='validation+formvalidation',
                    required_functions=[],
                    structure_skeleton={
                        'validation_framework': php.get('formvalidation', {}),
                        'validation_functions': validation_functions[:20],
                    },
                    constraints=[
                        'formValidation rules must exist when requested',
                        'Requested fields must have explicit validation mapping',
                    ],
                    examples=validation_functions[:12],
                    payload={
                        'formvalidation': php.get('formvalidation', {}),
                        'validation_functions': validation_functions[:20],
                    },
                )
            )

        if has_select2:
            entries.append(
                self._pattern_entry(
                    pattern_type='SELECT2_PATTERN',
                    form_type='ALL',
                    feature_signature='select2',
                    required_functions=[],
                    structure_skeleton={
                        'select2': True,
                        'css_classes': [token for token in css_classes if 'select2' in token.lower()][:10],
                    },
                    constraints=[
                        'Select2 handlers must only be generated when requested',
                    ],
                    examples=[token for token in css_classes if 'select2' in token.lower()][:10] or ['select2'],
                    payload={'select2': True},
                )
            )

        if has_txtcountacc or grid_patterns:
            entries.append(
                self._pattern_entry(
                    pattern_type='MASTER_DETAIL_PATTERN',
                    form_type='MASTER_DETAIL',
                    feature_signature='txtcountacc+detail_loop',
                    required_functions=['db_delete', 'db_insert', 'getrows'],
                    structure_skeleton={
                        'txtcountacc': True,
                        'delete_before_insert': True,
                        'detail_loop': True,
                    },
                    constraints=[
                        'TXTCOUNTACC is mandatory for master-detail forms',
                        'Delete existing detail rows before reinsert',
                        'Use a separate detail loop / CRUD flow',
                    ],
                    examples=self._normalize_names(grid_patterns)[:12] or ['TXTCOUNTACC', 'detail loop'],
                    payload={
                        'grid_patterns': grid_patterns[:8],
                        'txtcountacc': has_txtcountacc,
                    },
                )
            )

        return entries

    def _pattern_entry(
        self,
        *,
        pattern_type: str,
        form_type: str,
        feature_signature: str,
        required_functions: Sequence[str],
        structure_skeleton: Dict[str, Any],
        constraints: Sequence[str],
        examples: Sequence[Any],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            'pattern_type': pattern_type,
            'form_type': form_type,
            'feature_signature': feature_signature,
            'required_functions': [str(item) for item in required_functions if str(item or '').strip()],
            'structure_skeleton': structure_skeleton,
            'constraints': [str(item) for item in constraints if str(item or '').strip()],
            'examples': [str(item) for item in examples if str(item or '').strip()],
            'payload': payload,
        }

    def _normalize_names(self, values: Iterable[Any]) -> List[str]:
        output: List[str] = []
        seen: Set[str] = set()
        for value in values or []:
            if isinstance(value, dict):
                candidate = (
                    value.get('name')
                    or value.get('type')
                    or value.get('function')
                    or value.get('table')
                    or value.get('field')
                    or value.get('code')
                    or ''
                )
            else:
                candidate = value
            token = str(candidate or '').strip()
            if not token:
                continue
            token_key = token.lower()
            if token_key in seen:
                continue
            seen.add(token_key)
            output.append(token)
        return output

    def _score_candidate(self, candidate: PatternMemory, contract: Dict[str, Any]) -> float:
        form_type = str(contract.get('form_type') or 'SIMPLE').upper()
        requested_features = {str(feature).lower() for feature in contract.get('features', []) or []}
        candidate_features = {
            token.lower()
            for token in re.split(r'[+,| ]+', str(candidate.feature_signature or ''))
            if token.strip()
        }
        feature_overlap = (
            len(requested_features & candidate_features) / len(requested_features)
            if requested_features else 1.0
        )
        form_match = 1.0 if candidate.form_type in {form_type, 'ALL'} else 0.0
        company_match = 1.0 if candidate.required_functions or candidate.pattern_type in {'TEMPLATE_PATTERN', 'SESSION_PATTERN'} else 0.4
        weight_score = max(0.02, min(float(candidate.weight or 1.0) / 5.0, 1.0))

        score = (
            0.35 * form_match +
            0.25 * feature_overlap +
            0.20 * company_match +
            0.20 * weight_score
        )
        return round(score, 4)

    def _serialize_pattern(self, candidate: PatternMemory, score: float) -> Dict[str, Any]:
        return {
            'id': str(candidate.id),
            'pattern_type': candidate.pattern_type,
            'form_type': candidate.form_type,
            'feature_signature': candidate.feature_signature,
            'required_functions': list(candidate.required_functions or []),
            'structure_skeleton': dict(candidate.structure_skeleton or {}),
            'constraints': list(candidate.constraints or []),
            'examples': list(candidate.examples or []),
            'payload': dict(candidate.payload or {}),
            'weight': float(candidate.weight or 1.0),
            'score': float(score),
        }

    def _feature_signature(self, features: Sequence[str]) -> str:
        tokens = sorted({str(feature).lower() for feature in features or [] if str(feature or '').strip()})
        return '+'.join(tokens) if tokens else 'base'


class StrictERPController:
    """
    Orchestrates strict ERP preflight and learning.
    """

    def __init__(self):
        self.contract_parser = StrictPromptContractParser()
        self.memory_service = PatternMemoryService()

    def run_preflight(
        self,
        *,
        user_request: str,
        user_id: str,
        codebase_id: Optional[str],
        analyzed_patterns: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        contract = self.contract_parser.parse(user_request)
        if not contract.get('valid'):
            return self._preflight_failure(
                codebase_id=codebase_id,
                contract=contract,
                retrieval={},
                reason='contract_reject',
                message='Prompt contract rejected by strict ERP parser.',
                details=contract.get('errors', []),
            )

        if not codebase_id:
            return self._preflight_failure(
                codebase_id=codebase_id,
                contract=contract,
                retrieval={},
                reason='missing_memory',
                message='Pattern memory is required before generation. Upload and analyze a company codebase first.',
                details=['codebase_id is required for strict ERP generation'],
            )

        memory_records = self.memory_service.ensure_memory(
            user_id=user_id,
            codebase_id=codebase_id,
            analyzed_patterns=analyzed_patterns,
        )
        if not memory_records:
            return self._preflight_failure(
                codebase_id=codebase_id,
                contract=contract,
                retrieval={},
                reason='missing_memory',
                message='Pattern memory is empty for the selected codebase. Run codebase analysis before generation.',
                details=['persistent pattern memory could not be loaded or bootstrapped'],
            )

        retrieval = self.memory_service.retrieve(
            user_id=user_id,
            codebase_id=codebase_id,
            contract=contract,
        )
        if retrieval.get('block_generation'):
            message_map = {
                'pattern_combo_blacklisted': 'Pattern retrieval blocked because this form-type pattern combo is blacklisted.',
                'retrieval_quality_below_floor': 'Pattern retrieval quality is below the strict floor.',
                'pattern_coverage_below_floor': 'Pattern coverage is below the strict floor.',
            }
            detail_map = {
                'pattern_combo_blacklisted': ['pattern combo was previously blacklisted due to failure or contamination'],
                'retrieval_quality_below_floor': [f"retrieval_quality={retrieval.get('retrieval_quality', 0):.2f} (< {MIN_RETRIEVAL_QUALITY:.2f})"],
                'pattern_coverage_below_floor': [f"pattern_coverage={retrieval.get('pattern_coverage', 0):.2f} (< {MIN_PATTERN_COVERAGE:.2f})"],
            }
            return self._preflight_failure(
                codebase_id=codebase_id,
                contract=contract,
                retrieval=retrieval,
                reason=str(retrieval.get('reason') or 'retrieval_blocked'),
                message=message_map.get(str(retrieval.get('reason')), 'Strict ERP retrieval gate blocked generation.'),
                details=detail_map.get(str(retrieval.get('reason')), ['retrieval preflight blocked']),
            )

        return {
            'approved': True,
            'contract': contract,
            'retrieval': retrieval,
            'metadata': self._metadata_payload(contract, retrieval, approved=True, hard_block=False),
        }

    def record_workflow_outcome(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        codebase_id: Optional[str],
        preflight: Optional[Dict[str, Any]],
        final_state: Optional[Dict[str, Any]] = None,
        final_output: Optional[Dict[str, Any]] = None,
    ) -> Optional[PatternLearningEvent]:
        if not preflight:
            return None

        contract = preflight.get('contract') or {}
        retrieval = preflight.get('retrieval') or {}
        metadata = (final_output or {}).get('metadata', {}) if isinstance(final_output, dict) else {}
        validation_result = {}
        if isinstance(final_output, dict):
            validation_result = final_output.get('validation_result', {}) or {}
        if not validation_result and isinstance(final_state, dict):
            validation_result = final_state.get('validation_result', {}) or {}

        if not preflight.get('approved'):
            reason = str(preflight.get('reason') or 'preflight_failed')
            outcome = 'contamination' if 'contamination' in reason else 'missing_memory'
            if reason == 'contract_reject':
                outcome = 'contract_reject'
            if reason in {'pattern_coverage_below_floor', 'retrieval_quality_below_floor', 'pattern_combo_blacklisted'}:
                outcome = 'low_coverage'
            return self.memory_service.record_outcome(
                user_id=user_id,
                codebase_id=codebase_id,
                project_id=project_id,
                contract=contract,
                retrieval=retrieval,
                outcome=outcome,
                phase='preflight',
                failure_reason=str(preflight.get('message') or reason),
                validator_errors=list(preflight.get('details', []) or []),
                section_sizes={},
                metadata={'strict_erp': preflight.get('metadata', {})},
            )

        section_sizes = self._section_sizes(final_state, final_output)
        validation_reason = str(validation_result.get('validation_reason') or '').lower()
        approval_status = str(validation_result.get('approval_status') or '').lower()
        validation_passed = bool(
            validation_result.get('validation_passed')
            if 'validation_passed' in validation_result
            else approval_status == 'approved'
        )

        if 'contamination' in validation_reason:
            outcome = 'contamination'
        elif not validation_passed and (
            retrieval.get('pattern_coverage', 0) < MIN_PATTERN_COVERAGE
            or retrieval.get('retrieval_quality', 0) < MIN_RETRIEVAL_QUALITY
        ):
            outcome = 'low_coverage'
        elif validation_passed:
            outcome = 'success'
        else:
            outcome = 'failure'

        validator_errors = []
        if isinstance(validation_result.get('all_issues'), dict):
            validator_errors = (
                list(validation_result['all_issues'].get('critical', []) or []) +
                list(validation_result['all_issues'].get('major', []) or [])
            )

        return self.memory_service.record_outcome(
            user_id=user_id,
            codebase_id=codebase_id,
            project_id=project_id,
            contract=contract,
            retrieval=retrieval,
            outcome=outcome,
            phase='validation' if not validation_passed else 'persistence',
            failure_reason=validation_reason,
            validator_errors=validator_errors,
            section_sizes=section_sizes,
            metadata={'strict_erp': metadata.get('strict_erp', {}) if isinstance(metadata, dict) else {}},
        )

    def attach_metadata(
        self,
        result: Dict[str, Any],
        preflight: Optional[Dict[str, Any]],
        *,
        persistence_allowed: Optional[bool] = None,
    ) -> Dict[str, Any]:
        if not isinstance(result, dict) or not preflight:
            return result

        metadata = dict(result.get('metadata') or {})
        strict_meta = dict(preflight.get('metadata') or {})
        if persistence_allowed is not None:
            strict_meta['persistence_allowed'] = bool(persistence_allowed)
            strict_meta['block_save'] = not bool(persistence_allowed)
        metadata['strict_erp'] = strict_meta
        result['metadata'] = metadata
        return result

    def _preflight_failure(
        self,
        *,
        codebase_id: Optional[str],
        contract: Dict[str, Any],
        retrieval: Dict[str, Any],
        reason: str,
        message: str,
        details: Sequence[Any],
    ) -> Dict[str, Any]:
        metadata = self._metadata_payload(contract, retrieval, approved=False, hard_block=True)
        metadata['reason'] = reason
        return {
            'approved': False,
            'reason': reason,
            'message': message,
            'details': list(details or []),
            'contract': contract,
            'retrieval': retrieval,
            'metadata': metadata,
            'result': {
                'error': message,
                'details': '\n'.join(str(item) for item in details) if details else message,
                'code': {},
                'status': 'failed',
                'validation_result': {
                    'approval_status': 'needs_revision',
                    'validation_passed': False,
                    'block_save': True,
                    'block_generation': True,
                    'needs_revision': True,
                    'regeneration_required': False,
                    'validation_reason': reason,
                    'retrieval_quality': retrieval.get('retrieval_quality', 0.0),
                    'pattern_coverage': retrieval.get('pattern_coverage', 0.0),
                },
                'metadata': {
                    'strict_erp': metadata,
                },
            },
        }

    def _metadata_payload(
        self,
        contract: Dict[str, Any],
        retrieval: Dict[str, Any],
        *,
        approved: bool,
        hard_block: bool,
    ) -> Dict[str, Any]:
        return {
            'approved': approved,
            'hard_block': hard_block,
            'form_type': contract.get('form_type'),
            'entity': contract.get('entity'),
            'features': list(contract.get('features', []) or []),
            'required_pattern_types': list(retrieval.get('required_pattern_types', []) or []),
            'retrieval_quality': float(retrieval.get('retrieval_quality', 0.0) or 0.0),
            'pattern_coverage': float(retrieval.get('pattern_coverage', 0.0) or 0.0),
            'selected_patterns': [
                {
                    'id': pattern.get('id'),
                    'pattern_type': pattern.get('pattern_type'),
                    'score': pattern.get('score'),
                }
                for pattern in retrieval.get('selected_patterns', []) or []
            ],
            'top_candidates': list(retrieval.get('top_candidates', []) or [])[:8],
        }

    def _section_sizes(
        self,
        final_state: Optional[Dict[str, Any]],
        final_output: Optional[Dict[str, Any]],
    ) -> Dict[str, int]:
        state = final_state or {}
        output = final_output or {}
        code = (output.get('code', {}) or {}) if isinstance(output, dict) else {}
        complete_php = str(code.get('complete_php') or state.get('complete_php') or state.get('php_code') or '')
        return {
            'complete_php': len(complete_php),
            'php_code': len(str(state.get('php_code') or '')),
            'html_code': len(str(state.get('html_code') or '')),
            'js_code': len(str(state.get('js_code') or '')),
            'validation_errors': len(list(state.get('validation_errors', []) or [])),
        }
