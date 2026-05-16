import re
from typing import Optional

from agents.utils.company_form_blueprint import CompanyFormBlueprint


class CompanyStyleNormalizer:
    """
    Deterministically normalize rendered output to the approved company style
    before hard contract validation runs.
    """

    def __init__(self, blueprint: Optional[CompanyFormBlueprint] = None):
        self.blueprint = blueprint or CompanyFormBlueprint.load_default()

    def normalize(self, code: str) -> str:
        normalized = str(code or "")
        if not normalized.strip():
            return normalized

        normalized = self._normalize_session_keys(normalized)
        normalized = self._normalize_config_include(normalized)
        normalized = self._normalize_footer_count(normalized)
        normalized = self._normalize_edit_binding_variable(normalized)
        return normalized

    def _normalize_session_keys(self, code: str) -> str:
        session_contract = self.blueprint.get_session_contract()
        replacements = (
            (r"\$_SESSION\[['\"]User_ID['\"]\]", f"$_SESSION['{session_contract.get('user', 'user_id')}']"),
            (r"\$_SESSION\[['\"]Comp_Code['\"]\]", f"$_SESSION['{session_contract.get('company', 'comp_code')}']"),
            (r"\$_SESSION\[['\"]Login_ID['\"]\]", f"$_SESSION['{session_contract.get('login', 'login_id')}']"),
        )
        normalized = code
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    def _normalize_config_include(self, code: str) -> str:
        includes = self.blueprint.get_required_includes()
        top_includes = includes.get("top", [])
        if not top_includes:
            return code
        canonical_include = top_includes[0]
        normalized = re.sub(
            r"require_once\s*\(\s*['\"]includes/config\.php['\"]\s*\)\s*;",
            f'include("{canonical_include}");',
            code,
            flags=re.IGNORECASE,
        )
        if canonical_include.lower() not in normalized.lower():
            normalized = re.sub(
                r"(<\?php\s*)",
                rf'\1@session_start();' + "\n" + f'include("{canonical_include}");' + "\n",
                normalized,
                count=1,
                flags=re.IGNORECASE,
            )
        return normalized

    def _normalize_footer_count(self, code: str) -> str:
        required_footer_count = self.blueprint.get_footer_count()
        footer_pattern = re.compile(
            r'(?:include|include_once|require|require_once)\s*\(\s*[\'"]include/footer\.php[\'"]\s*\)\s*;?',
            re.IGNORECASE,
        )
        matches = list(footer_pattern.finditer(code))
        if len(matches) <= required_footer_count:
            return code

        kept = 0
        chunks = []
        last_index = 0
        for match in matches:
            chunks.append(code[last_index:match.start()])
            if kept < required_footer_count:
                chunks.append(match.group(0))
                kept += 1
            last_index = match.end()
        chunks.append(code[last_index:])
        return "".join(chunks)

    def _normalize_edit_binding_variable(self, code: str) -> str:
        target_var = self.blueprint.get_edit_binding_variable()
        normalized = re.sub(r"\$record\b", f"${target_var}", code)
        normalized = re.sub(r"\$row_data\b", f"${target_var}", normalized)
        return normalized
