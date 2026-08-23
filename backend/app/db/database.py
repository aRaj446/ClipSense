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
    import app.models.feedback_dataset       # noqa: F401
    import app.models.trailer_job            # noqa: F401
    import app.models.smart_trailer_job      # noqa: F401
    import app.models.audience_analysis_job  # noqa: F401
    import app.models.trailer_strategy       # noqa: F401
    import app.models.trailer_edit           # noqa: F401
    import app.models.smart_trailer_edit     # noqa: F401
    import app.models.project                # noqa: F401
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

        # trailer_strategies table is created by Base.metadata.create_all above;
        # no additive migration needed for new installs.

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

        # ── Phase 2 additive migrations ───────────────────────────────────────

        # content_hash on feedback_datasets — enables duplicate-dataset detection
        try:
            conn.execute(_text("ALTER TABLE feedback_datasets ADD COLUMN content_hash VARCHAR"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # sample_trailer_path on feedback_datasets — records which sample was used
        try:
            conn.execute(_text("ALTER TABLE feedback_datasets ADD COLUMN sample_trailer_path VARCHAR"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # Unique index on (project_id, content_hash) — prevents duplicate datasets
        # CREATE INDEX IF NOT EXISTS is safe to run on every startup
        try:
            conn.execute(_text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_feedback_datasets_project_hash "
                "ON feedback_datasets (project_id, content_hash) "
                "WHERE content_hash IS NOT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # index already exists or SQLite version doesn't support partial index

        # Backfill content_hash for existing datasets that pre-date Phase 2
        import hashlib as _hashlib
        existing_rows = conn.execute(_text(
            "SELECT id, raw_text FROM feedback_datasets WHERE content_hash IS NULL AND raw_text IS NOT NULL"
        )).fetchall()
        for ds_id, raw_text in existing_rows:
            if raw_text:
                h = _hashlib.sha256(raw_text.encode("utf-8", errors="replace")).hexdigest()[:16]
                try:
                    conn.execute(_text(
                        "UPDATE feedback_datasets SET content_hash=:h WHERE id=:id"
                    ), {"h": h, "id": ds_id})
                except Exception:
                    pass  # duplicate hash for this project — leave null
        conn.commit()

        # ── Phase 4 additive migrations ───────────────────────────────────────
        # project_id + dataset_id on smart_trailer_jobs — project-based generation
        for _col in ("project_id", "dataset_id"):
            try:
                conn.execute(_text(f"ALTER TABLE smart_trailer_jobs ADD COLUMN {_col} VARCHAR"))
                conn.commit()
            except Exception:
                pass  # column already exists
        try:
            conn.execute(_text(
                "CREATE INDEX IF NOT EXISTS ix_smart_trailer_jobs_project_id "
                "ON smart_trailer_jobs (project_id) WHERE project_id IS NOT NULL"
            ))
            conn.commit()
        except Exception:
            pass  # index already exists

        # ── Phase 5 additive migrations ───────────────────────────────────────
        # user_prompt — stores the user's expectations / creative direction per generation
        try:
            conn.execute(_text("ALTER TABLE smart_trailer_jobs ADD COLUMN user_prompt TEXT"))
            conn.commit()
        except Exception:
            pass  # column already exists

        # ── Phase 1 (SenseScrub) additive migrations ──────────────────────────
        # smart_trailer_edits — created by Base.metadata.create_all for new installs.
        # CREATE TABLE IF NOT EXISTS is a safe no-op on new installs and ensures
        # the table exists on databases that pre-date this model registration.
        try:
            conn.execute(_text(
                "CREATE TABLE IF NOT EXISTS smart_trailer_edits ("
                "  job_id     TEXT PRIMARY KEY, "
                "  plan_json  TEXT NOT NULL, "
                "  updated_at DATETIME NOT NULL"
                ")"
            ))
            conn.commit()
        except Exception:
            pass  # table already exists
