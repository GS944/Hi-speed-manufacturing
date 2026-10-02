"""Application settings, read from environment variables (or backend/.env).

Nothing is required to run locally. In production the only required setting is CORS_ORIGINS (the URL of the
frontend). Storage and database are pluggable:

  * database: SQLite file in DATA_DIR (default) or any PostgreSQL URL in DATABASE_URL (e.g. Neon, free)
  * workbook files: local folder DATA_DIR/files (default) or any S3-compatible bucket (Backblaze B2, Cloudflare R2,
    AWS S3, MinIO) when S3_BUCKET is set - required on hosts without a persistent disk (e.g. Render Free).
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    env = BASE_DIR / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0]            # allow trailing comments
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


# "production" turns on strict checks (API docs off, CORS must be set, HSTS).
ENV = _env("ENV", "development").lower()
IS_PRODUCTION = ENV in ("production", "prod")

DATA_DIR = Path(_env("DATA_DIR") or BASE_DIR / "data").resolve()
FILES_DIR = DATA_DIR / "files"
TMP_DIR = DATA_DIR / "tmp"
MODELS_DIR = Path(_env("MODELS_DIR") or DATA_DIR / "models")
if not MODELS_DIR.is_absolute():
    MODELS_DIR = (BASE_DIR / MODELS_DIR).resolve()
for _d in (DATA_DIR, FILES_DIR, TMP_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _db_url() -> str:
    url = _env("DATABASE_URL")
    if not url:
        return f"sqlite:///{(DATA_DIR / 'ordertrack.db').as_posix()}"
    # providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _db_url()
IS_SQLITE = DATABASE_URL.startswith("sqlite")

# ---- workbook file storage
S3_BUCKET = _env("S3_BUCKET")
S3_ENDPOINT_URL = _env("S3_ENDPOINT_URL") or None      # e.g. https://s3.us-west-004.backblazeb2.com
S3_REGION = _env("S3_REGION") or None
S3_ACCESS_KEY_ID = _env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY = _env("S3_SECRET_ACCESS_KEY")
S3_PREFIX = _env("S3_PREFIX", "ordertrack/").lstrip("/")
STORAGE_BACKEND = "s3" if S3_BUCKET else "local"

# Storage quota for uploaded workbooks (requirement: more than 5 GB). Backblaze B2 free = 10 GB.
STORAGE_QUOTA_GB = float(_env("STORAGE_QUOTA_GB", "10"))
MAX_UPLOAD_MB = int(_env("MAX_UPLOAD_MB", "200"))

# ---- accounts
# Standard sign-up / sign-in. ALLOW_SIGNUP sets the initial state of "Allow new sign-ups"; an administrator can switch
# it on or off later in Settings > Users (the switch is stored in the database).
ALLOW_SIGNUP = _env("ALLOW_SIGNUP", "true").lower() in ("1", "true", "yes", "on")
# Optional: also create an account from the environment on start-up (e.g. to regain access).
ADMIN_USERNAME = _env("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or ""

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = float(_env("JWT_EXPIRE_HOURS", "10"))
JWT_SECRET = _env("JWT_SECRET")      # optional; otherwise generated once and stored in the database

_default_origins = "" if IS_PRODUCTION else "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"
CORS_ORIGINS = [o.strip().rstrip("/") for o in _env("CORS_ORIGINS", _default_origins).split(",") if o.strip()]
# Optional regex, e.g. https://hi-speed-manufacturing(-[a-z0-9-]+)?\.vercel\.app to also allow preview deployments
CORS_ORIGIN_REGEX = _env("CORS_ORIGIN_REGEX") or None

STATIC_DIR = Path(_env("STATIC_DIR") or BASE_DIR.parent / "frontend" / "dist").resolve()
API_DOCS = _env("API_DOCS", "false" if IS_PRODUCTION else "true").lower() == "true"


def validate() -> list[str]:
    """Problems that must be fixed before serving production traffic."""
    problems = []
    if IS_PRODUCTION and not CORS_ORIGINS and not CORS_ORIGIN_REGEX:
        problems.append("CORS_ORIGINS is empty. Set it to your frontend URL, e.g. https://hi-speed-manufacturing.vercel.app")
    if S3_BUCKET and not (S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY):
        problems.append("S3_BUCKET is set but S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY are missing.")
    if bool(ADMIN_USERNAME) != bool(ADMIN_PASSWORD):
        problems.append("Set both ADMIN_USERNAME and ADMIN_PASSWORD, or neither (then sign up in the app).")
    return problems
