import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional


class CompanyFormBlueprint:
    """
    Runtime access layer for the approved company form contract.

    The human-reviewed markdown documents are for review only. Runtime code
    consumes the structured blueprint JSON artifact instead of parsing docs.
    """

    def __init__(self, blueprint_path: Optional[Path] = None):
        base_dir = Path(__file__).resolve().parent.parent.parent
        self._blueprint_path = blueprint_path or (base_dir / "config" / "company_form_blueprint.json")
        with self._blueprint_path.open("r", encoding="utf-8") as handle:
            self._data = json.load(handle)

    @classmethod
    @lru_cache(maxsize=1)
    def load_default(cls) -> "CompanyFormBlueprint":
        return cls()

    def get_section_order(self) -> List[str]:
        return list(self._data.get("section_order", []))

    def get_required_includes(self) -> Dict[str, List[str]]:
        includes = self._data.get("required_includes", {})
        return {position: list(paths) for position, paths in includes.items()}

    def get_audit_columns(self) -> List[str]:
        return list(self._data.get("audit_columns", []))

    def get_js_submit_chain(self) -> Dict[str, str]:
        return dict(self._data.get("js_submit_chain", {}))

    def get_master_detail_scaffold(self) -> Dict[str, object]:
        return dict(self._data.get("master_detail_scaffold", {}))

    def get_session_contract(self) -> Dict[str, str]:
        return dict(self._data.get("session_contract", {}))

    def get_getmaxid_contract(self) -> Dict[str, object]:
        return dict(self._data.get("getmaxid_contract", {}))

    def get_form_contract(self) -> Dict[str, object]:
        return dict(self._data.get("form_contract", {}))

    def get_footer_count(self) -> int:
        form_contract = self.get_form_contract()
        return int(form_contract.get("footer_count", 1) or 1)

    def get_edit_binding_variable(self) -> str:
        form_contract = self.get_form_contract()
        return str(form_contract.get("edit_binding_variable", "obj") or "obj")

    def get_source_files(self) -> List[str]:
        return list(self._data.get("source_files", []))
