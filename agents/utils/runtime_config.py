"""
Runtime configuration helpers.
Reads values from Django settings first, then environment variables.
"""

import os
import re
from typing import List, Optional


def _read_setting(name: str):
    try:
        from django.conf import settings  # Imported lazily
        if settings.configured and hasattr(settings, name):
            return getattr(settings, name)
    except Exception:
        pass
    return None


def get_int_setting(
    setting_name: str,
    env_name: str,
    default: int,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
) -> int:
    raw = _read_setting(setting_name)
    if raw is None:
        raw = os.getenv(env_name, default)

    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = int(default)

    if min_value is not None and value < min_value:
        value = min_value
    if max_value is not None and value > max_value:
        value = max_value
    return value


def get_csv_setting(
    setting_name: str,
    env_name: str,
    default: Optional[List[str]] = None
) -> List[str]:
    raw = _read_setting(setting_name)
    if raw is None:
        raw = os.getenv(env_name, "")

    if isinstance(raw, (list, tuple, set)):
        parts = [str(item).strip() for item in raw if str(item).strip()]
    else:
        text = str(raw or "")
        parts = [part.strip() for part in re.split(r'[,;\n]+', text) if part.strip()]

    if not parts and default:
        parts = [str(item).strip() for item in default if str(item).strip()]

    unique = []
    seen = set()
    for item in parts:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(item)

    return unique
