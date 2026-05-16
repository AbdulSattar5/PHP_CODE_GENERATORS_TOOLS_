import re
from pathlib import Path

from django.conf import settings

from models.project import CompanyCodebase, CompanyStandards, Project


WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\\/:*?\"<>|\r\n]+(?:\\[^\\/:*?\"<>|\r\n]+)*")
UNIX_PATH_RE = re.compile(r"(?:/home/|/Users/|/var/|/tmp/)[^\s'\"]+")
PRIVATE_SUBPATH_RE = re.compile(
    r"(company_codebases|runtime/company_codebases|runtime/chroma|media/temp_uploads|runtime/generated_code)[^,\n\r]*",
    re.IGNORECASE,
)


def sanitize_public_text(value):
    if value is None:
        return ""

    text = str(value)
    sanitized = WINDOWS_PATH_RE.sub("[private-path]", text)
    sanitized = UNIX_PATH_RE.sub("[private-path]", sanitized)
    sanitized = PRIVATE_SUBPATH_RE.sub("[private-runtime-path]", sanitized)
    return sanitized


def sanitize_public_metadata(value):
    if isinstance(value, dict):
        safe = {}
        for key, item in value.items():
            lowered_key = str(key).lower()
            if lowered_key in {
                "source_file",
                "absolute_file_path",
                "file_path",
                "codebase_root",
                "temp_file_path",
                "upload_path",
            }:
                safe[key] = Path(str(item)).name if item else ""
                continue
            safe[key] = sanitize_public_metadata(item)
        return safe

    if isinstance(value, list):
        return [sanitize_public_metadata(item) for item in value]

    if isinstance(value, tuple):
        return [sanitize_public_metadata(item) for item in value]

    if isinstance(value, str):
        return sanitize_public_text(value)

    return value


def build_setup_status(user, selected_project_id=None):
    project_selected = False
    project_count = 0
    codebase_uploaded = False
    codebase_indexed = False
    codebase_failed = False
    standards_available = False

    if getattr(user, "is_authenticated", False):
        user_projects = Project.objects.filter(user=user)
        project_count = user_projects.count()
        if selected_project_id:
            project_selected = user_projects.filter(id=selected_project_id).exists()

        user_codebases = CompanyCodebase.objects.filter(user=user)
        codebase_uploaded = user_codebases.exists()
        codebase_indexed = user_codebases.filter(is_indexed=True, index_status="ready").exists()
        codebase_failed = user_codebases.filter(index_status="failed").exists()
        standards_available = CompanyStandards.objects.filter(user=user).exists()

    return {
        "openai_api_key_configured": bool(getattr(settings, "OPENAI_API_KEY_CONFIGURED", False)),
        "project_selected": bool(project_selected),
        "project_count": project_count,
        "codebase_uploaded": bool(codebase_uploaded),
        "codebase_indexed": bool(codebase_indexed),
        "codebase_failed": bool(codebase_failed),
        "standards_available": bool(standards_available),
    }


def build_config_status():
    database_name = settings.DATABASES["default"].get("NAME")
    return {
        "openai_api_key": bool(getattr(settings, "OPENAI_API_KEY_CONFIGURED", False)),
        "chroma_directory": Path(settings.CHROMA_PERSIST_DIRECTORY).exists(),
        "codebase_storage": Path(settings.COMPANY_CODEBASE_DIR).exists(),
        "database_connected": bool(database_name),
        "debug_mode": bool(settings.DEBUG),
    }


def safe_index_error_message(raw_error):
    message = sanitize_public_text(raw_error).lower()
    if not message:
        return settings.INDEXING_FAILED_MESSAGE
    if "openai" in message and ("api key" in message or "authentication" in message):
        return "OpenAI API key not configured. Codebase files were stored, but indexing was skipped."
    if "zip" in message or "archive" in message or "supported code files" in message:
        return settings.INDEXING_FAILED_MESSAGE
    return "Codebase indexing failed. Please review the uploaded ZIP file and try again."
