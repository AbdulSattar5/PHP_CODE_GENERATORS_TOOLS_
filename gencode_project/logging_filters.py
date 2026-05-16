"""
Global logging filters for clean ASCII-only operational logs.
"""

import logging
import re


class AsciiOnlyLogFilter(logging.Filter):
    """
    Sanitize log records so terminal/file logs remain plain English.

    This removes mojibake and emoji-like glyphs (for example:
    'âš ï¸', 'âŒ', 'ðŸŽ¯', '✅') and collapses extra whitespace.
    """

    _non_ascii_re = re.compile(r"[^\x00-\x7F]+")
    _multi_space_re = re.compile(r"\s{2,}")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True

        sanitized = self._non_ascii_re.sub(" ", message)
        sanitized = sanitized.replace("\r", " ").replace("\n", " ")
        sanitized = self._multi_space_re.sub(" ", sanitized).strip()

        if sanitized != message:
            record.msg = sanitized
            record.args = ()

        return True
