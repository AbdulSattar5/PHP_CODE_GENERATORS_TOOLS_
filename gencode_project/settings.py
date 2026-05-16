"""
Django settings for GenCode AI.
"""

import os
import sys
import warnings
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv


os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY"] = "False"
os.environ["CHROMA_DISABLE_TELEMETRY"] = "True"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"


class DummyPostHog:
    def capture(self, *args, **kwargs):
        return None

    def __getattr__(self, name):
        return lambda *args, **kwargs: None


dummy_posthog = type(sys)("posthog")
dummy_posthog.capture = lambda *args, **kwargs: None
dummy_posthog.Posthog = DummyPostHog
sys.modules["posthog"] = dummy_posthog


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local")


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_csv(value, default=None):
    items = [item.strip() for item in str(value or "").split(",") if item.strip()]
    if items:
        return items
    return list(default or [])


def _resolve_path(value, default):
    raw_value = str(value or default).strip()
    candidate = Path(raw_value)
    if not candidate.is_absolute():
        candidate = BASE_DIR / candidate
    return candidate.resolve()


def _normalize_proxy_endpoint(proxy_value):
    value = (proxy_value or "").strip()
    if not value:
        return ""
    candidate = value if "://" in value else f"http://{value}"
    parsed = urlparse(candidate)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return ""
    try:
        port = parsed.port
    except ValueError:
        return host
    if port is not None:
        return f"{host}:{port}"
    return host


def _sanitize_proxy_environment():
    proxy_vars = [
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ]

    if _as_bool(os.getenv("OPENAI_DISABLE_ENV_PROXY"), default=False):
        for key in proxy_vars:
            os.environ.pop(key, None)
        return

    if not _as_bool(os.getenv("OPENAI_STRIP_LOOPBACK_PROXIES"), default=True):
        return

    blocked_raw = os.getenv(
        "OPENAI_BLOCKED_PROXY_ENDPOINTS",
        "127.0.0.1:9,localhost:9,[::1]:9",
    )
    blocked_endpoints = {
        endpoint
        for endpoint in (_normalize_proxy_endpoint(item) for item in blocked_raw.split(","))
        if endpoint
    }

    for key in proxy_vars:
        endpoint = _normalize_proxy_endpoint(os.getenv(key))
        if endpoint and endpoint in blocked_endpoints:
            os.environ.pop(key, None)


def _build_database_config():
    database_url = os.getenv("DATABASE_URL", "sqlite:///db.sqlite3").strip()
    parsed = urlparse(database_url)
    scheme = (parsed.scheme or "sqlite").lower()

    if scheme in {"sqlite", "sqlite3"}:
        db_path = unquote(parsed.path or parsed.netloc or "db.sqlite3")
        if db_path.startswith("/") and not parsed.netloc and not database_url.startswith("sqlite:////"):
            db_path = db_path[1:]
        db_name = Path(db_path or "db.sqlite3")
        if not db_name.is_absolute():
            db_name = BASE_DIR / db_name
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(db_name),
        }

    engine_map = {
        "postgres": "django.db.backends.postgresql",
        "postgresql": "django.db.backends.postgresql",
        "mysql": "django.db.backends.mysql",
    }
    engine = engine_map.get(scheme)
    if not engine:
        raise ValueError(f"Unsupported DATABASE_URL scheme: {scheme}")

    return {
        "ENGINE": engine,
        "NAME": unquote((parsed.path or "").lstrip("/")),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
    }


_sanitize_proxy_environment()


RUNTIME_DIR = _resolve_path(os.getenv("RUNTIME_DIR"), "./runtime")
MEDIA_ROOT = _resolve_path(os.getenv("MEDIA_ROOT"), "./media")
STATIC_ROOT = _resolve_path(os.getenv("STATIC_ROOT"), "./staticfiles")
CACHE_DIR = _resolve_path(os.getenv("CACHE_DIR"), str(RUNTIME_DIR / "cache"))
LOG_DIR = _resolve_path(os.getenv("LOG_DIR"), str(RUNTIME_DIR / "logs"))
GENERATED_CODE_DIR = _resolve_path(
    os.getenv("GENERATED_CODE_DIR"),
    str(RUNTIME_DIR / "generated_code"),
)
COMPANY_CODEBASE_DIR = _resolve_path(
    os.getenv("CODEBASE_STORAGE_DIR") or os.getenv("COMPANY_CODEBASE_DIR"),
    str(RUNTIME_DIR / "company_codebases"),
)
CODEBASE_STORAGE_DIR = COMPANY_CODEBASE_DIR
STANDARDS_DIR = _resolve_path(
    os.getenv("STANDARDS_DIR"),
    str(RUNTIME_DIR / "standards"),
)
CHROMA_PERSIST_DIRECTORY = _resolve_path(
    os.getenv("CHROMA_PERSIST_DIRECTORY"),
    str(RUNTIME_DIR / "chroma"),
)
TEMP_UPLOADS_DIR = MEDIA_ROOT / "temp_uploads"

for directory in [
    RUNTIME_DIR,
    MEDIA_ROOT,
    STATIC_ROOT,
    CACHE_DIR,
    LOG_DIR,
    GENERATED_CODE_DIR,
    COMPANY_CODEBASE_DIR,
    STANDARDS_DIR,
    CHROMA_PERSIST_DIRECTORY,
    TEMP_UPLOADS_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


STRICT_COMPANY_FORM_COMPILER = _as_bool(
    os.getenv("STRICT_COMPANY_FORM_COMPILER"),
    default=False,
)
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
DEBUG = _as_bool(os.getenv("DEBUG"), default=True)
ALLOWED_HOSTS = _split_csv(os.getenv("ALLOWED_HOSTS"), ["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = _split_csv(os.getenv("CSRF_TRUSTED_ORIGINS"), [])

OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip() or None
OPENAI_API_KEY_CONFIGURED = bool(OPENAI_API_KEY)
OPENAI_REQUIRED_MESSAGE = "Please configure your own OpenAI API key before generating code."
CODEBASE_REQUIRED_MESSAGE = "Please upload and index your own codebase before using company-pattern generation."
STANDARDS_REQUIRED_MESSAGE = "Please add your own coding standards or continue without standards."
INDEXING_FAILED_MESSAGE = "Codebase indexing failed. Please check your ZIP file and upload again."


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "models",
    "api",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "gencode_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "api.context_processors.sidebar_context",
            ],
        },
    },
]

WSGI_APPLICATION = "gencode_project.wsgi.application"

DATABASES = {"default": _build_database_config()}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}


CORS_ALLOWED_ORIGINS = _split_csv(
    os.getenv("CORS_ALLOWED_ORIGINS"),
    [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
)
CORS_ALLOW_CREDENTIALS = True


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": str(CACHE_DIR),
        "OPTIONS": {
            "MAX_ENTRIES": 10000,
            "CULL_FREQUENCY": 4,
        },
    }
}


LANGCHAIN_CONFIG = {
    "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "fallback_model": os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini"),
    "openai_api_key": OPENAI_API_KEY,
    "temperature": 0.1,
    "max_tokens": 4000,
}

ENABLE_LLM_VALIDATION = _as_bool(os.getenv("ENABLE_LLM_VALIDATION"), default=False)
DEMO_MODE = _as_bool(os.getenv("DEMO_MODE"), default=False)
CODEGEN_ENFORCE_GPT4O_MINI = _as_bool(
    os.getenv("CODEGEN_ENFORCE_GPT4O_MINI"),
    default=True,
)

MODEL_CONFIGS = {
    "simple": {
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": 2000,
    },
    "medium": {
        "model": "gpt-4o-mini",
        "temperature": 0.1,
        "max_tokens": 4000,
    },
    "complex": {
        "model": "gpt-4o-mini",
        "temperature": 0,
        "max_tokens": 3000,
    },
}


CHROMA_CONFIG = {
    "persist_directory": str(CHROMA_PERSIST_DIRECTORY),
    "collection_name": os.getenv("CHROMA_COLLECTION_NAME", "company_codebase"),
    "embedding_function": "openai",
}


CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("REDIS_URL", "redis://localhost:6379/0")


EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = _as_int(os.getenv("EMAIL_PORT"), 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _as_bool(os.getenv("EMAIL_USE_TLS"), default=True)
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "webmaster@localhost",
)


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "ascii_only": {
            "()": "gencode_project.logging_filters.AsciiOnlyLogFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "gencode.log"),
            "formatter": "verbose",
            "filters": ["ascii_only"],
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["ascii_only"],
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": os.getenv("LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "agents": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"


if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_REDIRECT_EXEMPT = []
    SECURE_SSL_REDIRECT = _as_bool(os.getenv("SECURE_SSL_REDIRECT"), default=True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True


warnings.filterwarnings("ignore", message="Unsupported Windows version")
