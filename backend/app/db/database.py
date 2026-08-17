"""
Database configuration.

Local development:  SQLite  — zero setup, file-based, runs anywhere.
Production:         Change DATABASE_URL to PostgreSQL / AWS RDS.
                    Everything else — models, services, queries — stays identical.

Migration path:
    SQLite (now):       sqlite:///./app/clipsense.db
    PostgreSQL (later): postgresql://user:password@host:5432/clipsense
    AWS RDS (later):    postgresql://user:password@<rds-endpoint>:5432/clipsense
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.utils.storage import DB_PATH

# ── Change only this line when moving to an online database ──────────────────
DATABASE_URL = f"sqlite:///./{DB_PATH}"

# check_same_thread=False is required for SQLite with FastAPI's threaded server.
# WAL mode allows concurrent readers alongside a single writer, eliminating
# "database is locked" errors when background job threads commit while the
# request thread is mid-read. busy_timeout gives writers up to 5s to retry
# before raising an error rather than failing immediately.
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 30,          # busy_timeout in seconds for pysqlite
    },
)

# Enable WAL mode and set busy timeout once at engine creation time
from sqlalchemy import event as _sa_event

@_sa_event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")  # 5 000 ms
    cursor.execute("PRAGMA synchronous=NORMAL")  # safe with WAL, faster than FULL
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    FastAPI dependency — yields a DB session per request and guarantees cleanup.
    Usage: db: Session = Depends(get_db)
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """
    Create all tables on application startup.
    Safe to call multiple times — skips tables that already exist.
    When migrating to PostgreSQL, replace this with Alembic migrations.
    """
    from app.db.base import Base
    import app.models.feedback_dataset  # noqa: F401
    import app.models.trailer_job       # noqa: F401
    import app.models.smart_trailer_job # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Additive SQLite migrations — safe to run on every startup
    import re as _re
    from sqlalchemy import text as _text
    with engine.connect() as conn:
        for col in ("raw_footage_original_name", "sample_trailer_original_name", "comments_original_name"):
            try:
                conn.execute(_text(f"ALTER TABLE smart_trailer_jobs ADD COLUMN {col} VARCHAR"))
                conn.commit()
            except Exception:
                pass  # column already exists

        # analytics_cache column on feedback_datasets
        try:
            conn.execute(_text("ALTER TABLE feedback_datasets ADD COLUMN analytics_cache TEXT"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # New columns: gemini_used + fallback_warning on both job tables
        for table, col, coltype in [
            ("trailer_jobs",       "gemini_used",      "VARCHAR"),
            ("trailer_jobs",       "fallback_warning", "TEXT"),
            ("smart_trailer_jobs", "gemini_used",      "VARCHAR"),
            ("smart_trailer_jobs", "fallback_warning", "TEXT"),
        ]:
            try:
                conn.execute(_text(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}"))
                conn.commit()
            except Exception:
                pass  # column already exists

        # raw_footage_duration_secs — stored at generation time for time-saved calculation
        try:
            conn.execute(_text("ALTER TABLE smart_trailer_jobs ADD COLUMN raw_footage_duration_secs FLOAT"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # fast_mode — records whether the job was run in fast demo mode
        try:
            conn.execute(_text("ALTER TABLE smart_trailer_jobs ADD COLUMN fast_mode VARCHAR"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # GPU/device metadata columns
        for _col in ("device_used", "encoder_used", "whisper_model_used"):
            try:
                conn.execute(_text(f"ALTER TABLE smart_trailer_jobs ADD COLUMN {_col} VARCHAR"))
                conn.commit()
            except Exception:
                pass  # column already exists

        # Backfill original names for rows uploaded before this column existed
        def _clean(path: str, marker: str, jid: str) -> str:
            name = _re.split(r'[/\\]', path or '')[-1]
            stripped = _re.sub(r'^[0-9a-f]{32}' + marker, '', name)
            return f'Smart Trailer {jid[:8]}' if stripped.startswith('.') else (stripped or name)

        rows = conn.execute(_text(
            "SELECT id, raw_footage_path, sample_trailer_path, comments_path "
            "FROM smart_trailer_jobs WHERE raw_footage_original_name IS NULL"
        )).fetchall()
        for row in rows:
            job_id, raw, sample, comments = row
            conn.execute(_text(
                "UPDATE smart_trailer_jobs "
                "SET raw_footage_original_name=:r, sample_trailer_original_name=:s, comments_original_name=:c "
                "WHERE id=:id"
            ), {"r": _clean(raw, "_raw", job_id), "s": _clean(sample, "_sample", job_id), "c": _clean(comments, "_comments", job_id), "id": job_id})
        conn.commit()
