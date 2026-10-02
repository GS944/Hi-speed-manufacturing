"""Database models (SQLAlchemy 2.0). SQLite by default; PostgreSQL (e.g. Neon) via DATABASE_URL."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
                        create_engine, event, inspect, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import DATABASE_URL, IS_SQLITE


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if IS_SQLITE else {"connect_timeout": 15},
    pool_pre_ping=True,                       # serverless Postgres (Neon) drops idle connections
    **({} if IS_SQLITE else {"pool_size": 5, "max_overflow": 5, "pool_recycle": 280}),
)

if IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="admin")
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DataFile(Base):
    __tablename__ = "data_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str] = mapped_column(String(300))
    stored_name: Mapped[str] = mapped_column(String(300))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    sheet_sig: Mapped[str | None] = mapped_column(Text, nullable=True)   # sorted sheet names, for version detection
    status: Mapped[str] = mapped_column(String(20), default="processing")  # processing|ready|error|archived
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(80), default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataTable(Base):
    """One logical table found inside a sheet (a sheet may hold several side-by-side tables)."""
    __tablename__ = "data_tables"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("data_files.id", ondelete="CASCADE"), index=True)
    sheet_name: Mapped[str] = mapped_column(String(200))
    block_index: Mapped[int] = mapped_column(Integer, default=0)
    range_ref: Mapped[str] = mapped_column(String(40), default="")
    header_row: Mapped[int] = mapped_column(Integer, default=1)
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(20), default="table")  # table|form
    role: Mapped[str] = mapped_column(String(40), default="unknown")
    role_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    columns: Mapped[list] = mapped_column(JSON, default=list)   # [{name, letter, dtype, stats}]
    profile: Mapped[dict] = mapped_column(JSON, default=dict)   # engine output (JSON config) - editable
    form: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # extracted form layout for templates
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Record(Base):
    __tablename__ = "records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("data_tables.id", ondelete="CASCADE"), index=True)
    row_no: Mapped[int] = mapped_column(Integer)          # source row number in the sheet (0 = added in app)
    data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class RecordKey(Base):
    """Inverted index: normalised key -> record (primary keys and foreign references)."""
    __tablename__ = "record_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("data_tables.id", ondelete="CASCADE"))
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), default="pk")  # pk|ref


Index("ix_record_keys_key", RecordKey.key, RecordKey.kind)
Index("ix_record_keys_record", RecordKey.record_id)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60), default="")
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class PrintJob(Base):
    __tablename__ = "print_jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_no: Mapped[str] = mapped_column(String(40), unique=True)
    kind: Mapped[str] = mapped_column(String(30))        # annexure|route_card
    order_key: Mapped[str] = mapped_column(String(120), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    copies: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    created_by: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


# Columns added after the first release: (table, column, SQL type). Applied idempotently on start-up so existing
# databases upgrade in place without a migration tool.
_ADDED_COLUMNS = [
    ("users", "failed_logins", "INTEGER DEFAULT 0"),
    ("users", "locked_until", "TIMESTAMP"),
    ("data_files", "sheet_sig", "TEXT"),
]


def init_db() -> None:
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if column not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_setting(db, key: str, default=None):
    s = db.get(Setting, key)
    return s.value if s else default


def set_setting(db, key: str, value) -> None:
    s = db.get(Setting, key)
    if s:
        s.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()
