import re
from typing import Dict, List, Optional, Tuple

from agents.utils.company_form_blueprint import CompanyFormBlueprint


class CompanyFormContractValidator:
    """
    Hard company-style contract validator for normalized inline PHP output.
    """

    def __init__(self, blueprint: Optional[CompanyFormBlueprint] = None):
        self.blueprint = blueprint or CompanyFormBlueprint.load_default()

    def validate(self, code: str) -> Dict:
        text = str(code or "")
        errors: List[str] = []
        warnings: List[str] = []

        if not text.strip():
            return {
                "passed": False,
                "errors": ["No code generated after normalization."],
                "warnings": [],
                "details": {},
            }

        self._validate_required_includes(text, errors)
        self._validate_include_order(text, errors)
        self._validate_footer_count(text, errors)
        self._validate_session_contract(text, errors)
        self._validate_form_contract(text, errors)
        self._validate_submit_chain(text, errors)
        self._validate_getmaxid_contract(text, errors)
        self._validate_edit_binding_contract(text, errors)
        self._validate_audit_columns(text, errors)
        self._validate_placeholder_count(text, errors)

        return {
            "passed": not errors,
            "errors": errors,
            "warnings": warnings,
            "details": {
                "required_includes": self.blueprint.get_required_includes(),
                "session_contract": self.blueprint.get_session_contract(),
                "getmaxid_contract": self.blueprint.get_getmaxid_contract(),
            },
        }

    def _validate_required_includes(self, code: str, errors: List[str]) -> None:
        includes = self.blueprint.get_required_includes()
        for position, files in includes.items():
            for include_file in files:
                if include_file.lower() not in code.lower():
                    errors.append(f"Missing required {position} include: {include_file}")

    def _validate_footer_count(self, code: str, errors: List[str]) -> None:
        required_count = self.blueprint.get_footer_count()
        footer_count = len(
            re.findall(
                r'(?:include|include_once|require|require_once)\s*\(\s*[\'"]include/footer\.php[\'"]\s*\)',
                code,
                re.IGNORECASE,
            )
        )
        if footer_count != required_count:
            errors.append(f"Footer include count mismatch: expected {required_count}, found {footer_count}")

    def _validate_include_order(self, code: str, errors: List[str]) -> None:
        includes = self.blueprint.get_required_includes()
        ordered_groups = [
            ('top', includes.get('top', [])),
            ('body', includes.get('body', [])),
            ('footer', includes.get('footer', [])),
        ]

        first_index_by_group: Dict[str, int] = {}
        for group, paths in ordered_groups:
            indexes = []
            for include_path in paths:
                idx = code.lower().find(str(include_path).lower())
                if idx >= 0:
                    indexes.append(idx)
            if indexes:
                first_index_by_group[group] = min(indexes)

        if (
            'top' in first_index_by_group
            and 'body' in first_index_by_group
            and first_index_by_group['top'] > first_index_by_group['body']
        ):
            errors.append('Include order mismatch: top includes must appear before body includes.')

        if (
            'body' in first_index_by_group
            and 'footer' in first_index_by_group
            and first_index_by_group['body'] > first_index_by_group['footer']
        ):
            errors.append('Include order mismatch: body includes must appear before footer include.')

    def _validate_session_contract(self, code: str, errors: List[str]) -> None:
        session_contract = self.blueprint.get_session_contract()
        approved = set(session_contract.values())
        session_keys = re.findall(r'\$_SESSION\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]', code, re.IGNORECASE)
        for key in session_keys:
            if key not in approved:
                errors.append(f"Session key casing mismatch: expected company lower-case contract, found `{key}`")

    def _validate_form_contract(self, code: str, errors: List[str]) -> None:
        form_contract = self.blueprint.get_form_contract()
        form_match = re.search(r'<form\b([^>]*)>', code, re.IGNORECASE)
        if not form_match:
            errors.append("Missing <form> tag.")
            return
        form_tag = form_match.group(0)
        required_pairs = (
            ("id", str(form_contract.get("id", "frm"))),
            ("name", str(form_contract.get("name", "frm"))),
            ("method", str(form_contract.get("method", "POST"))),
        )
        for attr, value in required_pairs:
            if not re.search(rf'\b{attr}\s*=\s*["\']{re.escape(value)}["\']', form_tag, re.IGNORECASE):
                errors.append(f"Form missing canonical {attr}=\"{value}\"")
        required_class = str(form_contract.get("class", "form-horizontal"))
        if not re.search(rf'\bclass\s*=\s*["\'][^"\']*\b{re.escape(required_class)}\b', form_tag, re.IGNORECASE):
            errors.append(f"Form missing canonical class `{required_class}`")

    def _validate_submit_chain(self, code: str, errors: List[str]) -> None:
        submit_chain = self.blueprint.get_js_submit_chain()
        submit_function = str(submit_chain.get("submit_function", "btnsave_click"))
        validation_event = str(submit_chain.get("validation_event", "success.form.fv"))
        if submit_function not in code:
            errors.append(f"Missing submit function `{submit_function}`")
        if ".formValidation(" not in code:
            errors.append("Missing formValidation initialization.")
        if validation_event not in code:
            errors.append(f"Missing validation lifecycle event `{validation_event}`")
        if validation_event in code and submit_function not in code:
            errors.append(f"Validation lifecycle does not trigger `{submit_function}`")

    def _validate_getmaxid_contract(self, code: str, errors: List[str]) -> None:
        contract = self.blueprint.get_getmaxid_contract()
        if contract.get("php_return") == "scalar":
            if re.search(r'json_encode\s*\(\s*\[\s*[\'"]maxid[\'"]', code, re.IGNORECASE):
                errors.append("GetMaxID contract mismatch: company blueprint expects scalar PHP output, not JSON.")
            if re.search(r'response\s*\.\s*maxid', code, re.IGNORECASE):
                errors.append("GetMaxID contract mismatch: JavaScript expects response.maxid but company blueprint expects scalar response.")

    def _validate_edit_binding_contract(self, code: str, errors: List[str]) -> None:
        target_var = self.blueprint.get_edit_binding_variable()
        if re.search(r'\$record\b', code) or re.search(r'\$row_data\b', code):
            errors.append(f"Edit binding mismatch: final output must normalize to `${target_var}` only.")

    def _validate_audit_columns(self, code: str, errors: List[str]) -> None:
        audit_columns = self.blueprint.get_audit_columns()
        code_lower = code.lower()
        missing = [column for column in audit_columns if column.lower() not in code_lower]
        if missing:
            errors.append("Missing canonical audit columns: " + ", ".join(missing))

    def _validate_placeholder_count(self, code: str, errors: List[str]) -> None:
        calls = re.findall(
            r'(getvalue|getrows|db_getRecord|db_update|db_delete)\s*\(([\s\S]*?)\)\s*;',
            code,
            re.IGNORECASE,
        )
        for function_name, raw_args in calls:
            if function_name.lower() in {'getvalue', 'getrows'}:
                continue
            mismatch = self._count_placeholder_mismatch(raw_args)
            if mismatch:
                expected, actual = mismatch
                errors.append(
                    f"Placeholder mismatch in {function_name}: SQL expects {expected} params but array provides {actual}"
                )

    def _count_placeholder_mismatch(self, raw_args: str) -> Optional[Tuple[int, int]]:
        sql_match = re.search(
            r'["\']((?:SELECT|UPDATE|DELETE|INSERT|REPLACE|WITH|CALL)\b[\s\S]*?\?[^"\']*)["\']',
            raw_args,
            re.IGNORECASE | re.DOTALL,
        )
        if not sql_match:
            return None
        sql_text = sql_match.group(1)
        expected = sql_text.count("?")
        array_match = re.search(r'\[([^\]]*)\]', raw_args, re.DOTALL)
        if not array_match:
            return None
        array_body = array_match.group(1).strip()
        if not array_body:
            actual = 0
        else:
            actual = len([part for part in array_body.split(",") if part.strip()])
        if expected != actual:
            return expected, actual
        return None
