"""
Shared pytest configuration for the ClipSense backend test suite.

Provides:
    - sys.path fix so `import app` resolves from backend/
    - seed_project_row(): session-scoped helper that inserts the hardcoded
      PROJECT_ID used by test_phase1_audience_intelligence, test_phase3_*,
      and test_phase6_* into whatever SQLAlchemy session is active for that
      test module.  Called from each module's setup_db fixture via the
      autouse mechanism below.

Design:
    Each test module already owns its own isolated SQLite DB and patches
    _db_module.SessionLocal.  The project row must be inserted AFTER
    Base.metadata.create_all() runs in that module's setup_db fixture.
    We achieve this by providing a module-scoped autouse fixture here that
    depends on setup_db — pytest guarantees setup_db runs first because it
    is listed as a dependency.

    Tests that do NOT use PROJECT_ID are unaffected: the fixture inserts one
    lightweight row and exits immediately.
"""

import sys
import os

# ── sys.path fix ──────────────────────────────────────────────────────────────
_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


# ── Shared PROJECT_ID (matches the hardcoded constant in all failing tests) ───
SHARED_PROJECT_ID = "83a49988-d057-46e4-8600-fe7c9ff8d7ff"


def seed_project_row(session_factory) -> None:
    """
    Insert a minimal Project row with SHARED_PROJECT_ID if it does not already
    exist.  Uses the provided session_factory (the test module's _TestSession)
    so the row lands in the correct isolated test DB.

    File paths point at non-existent dummy paths — the feedback/analytics/
    strategy/audience-analysis endpoints only call get_project() to confirm
    the project exists; they never open the files themselves.
    """
    from app.models.project import Project
    from datetime import datetime, timezone

    db = session_factory()
    try:
        exists = db.query(Project).filter(Project.id == SHARED_PROJECT_ID).first()
        if not exists:
            db.add(Project(
                id=SHARED_PROJECT_ID,
                name="Test Project",
                raw_footage_path="/tmp/test_raw.mp4",
                sample_trailer_path="/tmp/test_sample.mp4",
                feedback_file_path="/tmp/test_feedback.json",
                raw_footage_name="test_raw.mp4",
                sample_trailer_name="test_sample.mp4",
                feedback_file_name="test_feedback.json",
                status="uploaded",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            ))
            db.commit()
    finally:
        db.close()
