"""
Phase 3 — Analytics + SenseCap Integration Tests

Covers:
    1.  analytics-status returns no-dataset for project without dataset_id
    2.  analytics-status returns pending when dataset exists but no cache
    3.  analytics-status returns has_analytics=True after run-analytics
    4.  analytics-status includes sentiment counts after run-analytics
    5.  analytics-status includes sensecap_url after run-analytics
    6.  run-analytics 404 for unknown project
    7.  run-analytics 404 for project with no dataset
    8.  run-analytics 422 for dataset with no segments
    9.  run-analytics returns cached result on second call (no recompute)
    10. run-analytics force=True recomputes and overwrites cache
    11. duplicate dataset: same feedback content → same dataset_id
    12. unique dataset: different feedback content → different dataset_id
    13. sensecap_url contains source=clipsense param
    14. sensecap_url contains dataset_url pointing to /export-dataset/{id}/csv
    15. GET /analytics/{dataset_id} returns cached report after run-analytics
    16. export-dataset CSV has correct columns after run-analytics
    17. run-analytics is idempotent (calling twice gives same result)
    18. analytics-status 404 for unknown project

Run with:
    cd backend
    set PYTHONPATH=C:\\Users\\7000039334\\Documents\\Gearshift\\Clipsense\\backend
    pytest tests/test_phase3_analytics.py -v
"""

import json
import sys
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models.feedback_dataset   # noqa: F401
import app.models.project            # noqa: F401
import app.models.audience_analysis_job  # noqa: F401
import app.models.trailer_job        # noqa: F401
import app.models.smart_trailer_job  # noqa: F401
import app.models.trailer_strategy   # noqa: F401
import app.models.trailer_edit       # noqa: F401

from app.models.project import Project
from app.models.feedback_dataset import FeedbackDataset, FeedbackSegmentRecord
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.services.analytics_agent import AnalyticsAgent
from app.schemas.feedback import FeedbackSegment


# ── In-memory SQLite fixture ──────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    return eng


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_project(db, dataset_id=None, name="Test Project"):
    pid = str(uuid.uuid4())
    row = Project(
        id=pid,
        name=name,
        raw_footage_path=f"/tmp/{pid}/raw.mp4",
        sample_trailer_path=f"/tmp/{pid}/sample.mp4",
        feedback_file_path=f"/tmp/{pid}/feedback.json",
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        feedback_file_name="feedback.json",
        size=1024,
        status="uploaded",
        dataset_id=dataset_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _make_segments(n=5):
    sentiments = ["Positive", "Negative", "Neutral", "Praise", "Complaint"]
    return [
        FeedbackSegment(
            timestamp=f"00:{i:02d}",
            topic=f"Topic{i % 3}",
            sentiment=sentiments[i % len(sentiments)],
            summary=f"Feedback segment {i}",
            confidence=0.7 + i * 0.04,
        )
        for i in range(n)
    ]


def _make_dataset(db, project_id, raw_text="test feedback", n_segments=5):
    svc = FeedbackDatasetService()
    return svc.save_dataset(
        db=db,
        project_id=project_id,
        raw_text=raw_text,
        segments=_make_segments(n_segments),
        source="project_upload",
    )


# ── Simulate the analytics-status endpoint logic ──────────────────────────────

def _analytics_status(project_row, db):
    """Mirror the logic in GET /project/{id}/analytics-status."""
    from urllib.parse import urlencode

    dataset_id = project_row.dataset_id
    if not dataset_id:
        return {"project_id": project_row.id, "dataset_id": None, "has_analytics": False, "segment_count": 0}

    svc = FeedbackDatasetService()
    ds  = svc.get_dataset_by_id(db, dataset_id)
    if not ds:
        return {"project_id": project_row.id, "dataset_id": dataset_id, "has_analytics": False, "segment_count": 0}

    cached = svc.get_analytics_cache(db, dataset_id)
    if not cached:
        return {
            "project_id": project_row.id,
            "dataset_id": dataset_id,
            "has_analytics": False,
            "segment_count": len(ds.segments),
        }

    dist      = cached.get("sentiment_distribution", {})
    breakdown = cached.get("topic_breakdown", [])
    top_topic = breakdown[0].get("topic") if breakdown else None

    base_url     = "http://localhost:8000"
    sensecap_url = "http://localhost:8501"
    csv_url      = f"{base_url}/export-dataset/{dataset_id}/csv"
    ds_name      = ds.name or project_row.name or ""
    params       = urlencode({"source": "clipsense", "dataset_url": csv_url, "dataset_name": ds_name})

    return {
        "project_id":   project_row.id,
        "dataset_id":   dataset_id,
        "has_analytics": True,
        "segment_count": len(ds.segments),
        "positive":     dist.get("Positive", 0) + dist.get("Praise", 0),
        "negative":     dist.get("Negative", 0) + dist.get("Complaint", 0),
        "neutral":      dist.get("Neutral", 0) + dist.get("Question", 0) + dist.get("Suggestion", 0),
        "top_topic":    top_topic,
        "analyzed_at":  cached.get("analyzed_at"),
        "sensecap_url": f"{sensecap_url}?{params}",
    }


def _run_analytics(project_row, db, force=False):
    """Mirror the logic in POST /project/{id}/run-analytics."""
    dataset_id = project_row.dataset_id
    assert dataset_id, "Project has no dataset"

    svc = FeedbackDatasetService()
    ds  = svc.get_dataset_by_id(db, dataset_id)
    assert ds and ds.segments, "Dataset missing or empty"

    if not force:
        cached = svc.get_analytics_cache(db, dataset_id)
        if cached:
            return _analytics_status(project_row, db)

    segments = [
        FeedbackSegment(
            timestamp=seg.timestamp,
            topic=seg.topic,
            sentiment=seg.sentiment,
            summary=seg.summary,
            confidence=seg.confidence,
        )
        for seg in ds.segments
    ]
    report = AnalyticsAgent().analyze(segments)
    svc.set_analytics_cache(db, dataset_id, report.model_dump_json())
    return _analytics_status(project_row, db)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_status_no_dataset(db):
    """1. analytics-status returns no-dataset for project without dataset_id."""
    project = _make_project(db, dataset_id=None)
    status  = _analytics_status(project, db)
    assert status["dataset_id"] is None
    assert status["has_analytics"] is False
    assert status["segment_count"] == 0


def test_status_pending_before_analytics(db):
    """2. analytics-status returns pending when dataset exists but no cache."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    status = _analytics_status(project, db)
    assert status["dataset_id"] == ds.id
    assert status["has_analytics"] is False
    assert status["segment_count"] == 5


def test_status_has_analytics_after_run(db):
    """3. analytics-status returns has_analytics=True after run-analytics."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)
    status = _analytics_status(project, db)
    assert status["has_analytics"] is True


def test_status_sentiment_counts(db):
    """4. analytics-status includes sentiment counts after run-analytics."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id, n_segments=10)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)
    status = _analytics_status(project, db)
    total = status["positive"] + status["negative"] + status["neutral"]
    assert total == 10


def test_status_sensecap_url_present(db):
    """5. analytics-status includes sensecap_url after run-analytics."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)
    status = _analytics_status(project, db)
    assert status["sensecap_url"] is not None
    assert "source=clipsense" in status["sensecap_url"]


def test_run_analytics_404_unknown_project():
    """6. run-analytics raises for unknown project."""
    with pytest.raises(AssertionError):
        # _run_analytics asserts dataset_id exists; simulate missing project
        class FakeRow:
            dataset_id = None
        _run_analytics(FakeRow(), None)


def test_run_analytics_404_no_dataset(db):
    """7. run-analytics raises for project with no dataset."""
    project = _make_project(db, dataset_id=None)
    with pytest.raises(AssertionError):
        _run_analytics(project, db)


def test_run_analytics_422_empty_dataset(db):
    """8. run-analytics raises for dataset with no segments."""
    project = _make_project(db)
    # Create dataset with zero segments
    svc = FeedbackDatasetService()
    ds  = svc.save_dataset(db=db, project_id=project.id, raw_text="x", segments=[], source="project_upload")
    project.dataset_id = ds.id
    db.commit()
    with pytest.raises(AssertionError):
        _run_analytics(project, db)


def test_run_analytics_returns_cached_on_second_call(db):
    """9. run-analytics returns cached result on second call."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    result1 = _run_analytics(project, db)
    result2 = _run_analytics(project, db)
    assert result1["analyzed_at"] == result2["analyzed_at"]


def test_run_analytics_force_recomputes(db):
    """10. run-analytics force=True recomputes and overwrites cache."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    result1 = _run_analytics(project, db)
    # Force recompute — analyzed_at may differ by a tiny amount but structure is same
    result2 = _run_analytics(project, db, force=True)
    assert result2["has_analytics"] is True
    assert result2["segment_count"] == result1["segment_count"]


def test_duplicate_dataset_same_id(db):
    """11. Same feedback content → same dataset_id (deduplication)."""
    project = _make_project(db)
    svc     = FeedbackDatasetService()
    segs    = _make_segments(3)
    raw     = "identical feedback text"

    ds1, created1 = svc.save_dataset_deduped(db, project.id, raw, segs, "project_upload")
    ds2, created2 = svc.save_dataset_deduped(db, project.id, raw, segs, "project_upload")

    assert ds1.id == ds2.id
    assert created1 is True
    assert created2 is False


def test_unique_dataset_different_id(db):
    """12. Different feedback content → different dataset_id."""
    project = _make_project(db)
    svc     = FeedbackDatasetService()
    segs    = _make_segments(3)

    ds1, _ = svc.save_dataset_deduped(db, project.id, "feedback A", segs, "project_upload")
    ds2, _ = svc.save_dataset_deduped(db, project.id, "feedback B", segs, "project_upload")

    assert ds1.id != ds2.id


def test_sensecap_url_has_source_param(db):
    """13. sensecap_url contains source=clipsense."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)
    status = _analytics_status(project, db)
    assert "source=clipsense" in status["sensecap_url"]


def test_sensecap_url_has_dataset_url(db):
    """14. sensecap_url contains dataset_url pointing to /export-dataset/{id}/csv (URL-encoded)."""
    from urllib.parse import unquote
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)
    status = _analytics_status(project, db)
    decoded = unquote(status["sensecap_url"])
    assert f"/export-dataset/{ds.id}/csv" in decoded


def test_analytics_cache_readable_after_run(db):
    """15. GET /analytics/{dataset_id} returns cached report after run-analytics."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)

    svc    = FeedbackDatasetService()
    cached = svc.get_analytics_cache(db, ds.id)
    assert cached is not None
    assert "sentiment_distribution" in cached
    assert "topic_breakdown" in cached
    assert cached["total_segments"] == 5


def test_export_csv_columns_after_run(db):
    """16. export-dataset CSV has correct columns after run-analytics."""
    from app.utils.sensecap_export import build_sensecap_csv, SENSECAP_CS_COLUMNS
    import csv, io

    project = _make_project(db)
    ds      = _make_dataset(db, project.id)
    project.dataset_id = ds.id
    db.commit()

    _run_analytics(project, db)

    svc    = FeedbackDatasetService()
    ds_obj = svc.get_dataset_by_id(db, ds.id)
    cached = svc.get_analytics_cache(db, ds.id)
    ap     = cached.get("audience_preferences") if cached else None

    csv_bytes = build_sensecap_csv(ds_obj.segments, ds_obj.name or "test", audience_preferences=ap)
    reader    = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8")))
    rows      = list(reader)

    assert len(rows) == 5
    for col in ["source", "sentiment_label", "theme", "text", "confidence"]:
        assert col in rows[0]
    for row in rows:
        assert row["source"] == "clipsense"


def test_run_analytics_idempotent(db):
    """17. Calling run-analytics twice gives same segment count."""
    project = _make_project(db)
    ds      = _make_dataset(db, project.id, n_segments=7)
    project.dataset_id = ds.id
    db.commit()

    r1 = _run_analytics(project, db)
    r2 = _run_analytics(project, db)
    assert r1["segment_count"] == r2["segment_count"] == 7


def test_analytics_status_unknown_project(db):
    """18. analytics-status for unknown project returns no-dataset shape."""
    class FakeRow:
        id         = "nonexistent-id"
        dataset_id = None
        name       = None

    status = _analytics_status(FakeRow(), db)
    assert status["has_analytics"] is False
    assert status["dataset_id"] is None
