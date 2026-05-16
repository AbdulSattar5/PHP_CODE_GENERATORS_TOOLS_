"""
Pipeline-wide constants (single source of truth).
"""

# Validation thresholds
DYNAMIC_VALIDATOR_PASS_THRESHOLD = 100
ENTERPRISE_QUALITY_GOOD_THRESHOLD = 75
ENTERPRISE_QUALITY_WARN_THRESHOLD = 60
RETRIEVAL_COVERAGE_FLOOR = 0.75
RETRIEVAL_HARD_BLOCK_FLOOR = 0.40
RETRIEVAL_SCORE_FLOOR = 60.0
PATTERN_EXTRACTION_SUFFICIENT_PCT = 0.75

# Retry policy
MAX_RETRIES_TRANSIENT = 2
MAX_RETRIES_STRUCTURAL = 0

# Token budgets
MAX_CHARS_PER_FALLBACK_FILE = 2500
MAX_FALLBACK_FILES = 3
MAX_TOTAL_PATTERN_CONTEXT_CHARS = 7000

# ChromaDB
CHROMADB_OVERFETCH_MULTIPLIER = 3
CHROMADB_MIN_FORM_TYPE_KW_HITS = 2

# Form type keywords
MASTER_DETAIL_INDICATOR_KEYWORDS = [
    "TXTCOUNTACC",
    "txtcountacc",
    "$count",
    "detail_table",
    "for.*\\$i.*=.*1",
    "\\$i.*<=.*\\$count",
    "funStartTran",
    "funEndTran",
    "db_delete.*detail",
]
SIMPLE_FORM_INDICATOR_KEYWORDS = [
    "db_insert",
    "db_update",
    "db_delete",
    "db_getRecord",
    "funStartTran",
    "funEndTran",
]

# Mandatory DB functions
MANDATORY_DB_FUNCTIONS = [
    "db_insert",
    "db_update",
    "db_delete",
    "db_getRecord",
    "getrows",
    "getvalue",
    "funStartTran",
    "funEndTran",
    "fun_log",
]

# Forbidden legacy functions
FORBIDDEN_LEGACY_FUNCTIONS = [
    "mysql_query",
    "mysql_fetch_array",
    "mysql_connect",
    "mysql_num_rows",
    "mysql_error",
]

# PHP variable rules
REQUIRED_PHP_VARIABLES = ["$Code", "$columns", "$filter", "$table", "$table2"]
FORBIDDEN_PHP_VARIABLES = ["$record", "$result", "$res"]

# Session variables (case-sensitive keys)
SESSION_USER_ID = "User_ID"
SESSION_COMP_CODE = "Comp_Code"
SESSION_LOGIN_ID = "Login_ID"

# Utility files always allowed in retrieval
UTILITY_FILENAMES = frozenset(
    [
        "functions.php",
        "db_functions.php",
        "common.php",
        "helpers.php",
        "utils.php",
        "config.php",
    ]
)

# Excluded files from entity examples
EXCLUDED_FILENAMES = frozenset(
    [
        "salebookingsimple.php",
        "quotation.php",
        "frmquotation.php",
    ]
)

# Structural failures (never retry)
STRUCTURAL_FAILURE_KEYWORDS = [
    "master-detail",
    "txtcountacc",
    "detail table",
    "contract mismatch",
    "wrong fields",
    "retrieval insufficient",
    "entity file missing",
    "canonical naming",
    "wrong table",
    "detail field in master",
    "missing detail insert",
    "filtered 0",
    "block_generation",
    "structural",
    "no examples",
]

