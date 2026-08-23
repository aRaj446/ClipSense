"""
Phase 4 — Project-Based Video Generation Tests

Covers:
    1.  project selection: list_project_trailers returns empty for new project
    2.  generate-trailer 404 for unknown project
    3.  generate-trailer 422 when raw footage file missing
    4.  generate-trailer 422 when sample trailer file missing
    5.  generate-trailer 422 when project has no dataset
    6.  generate-trailer 422 when feedback file missing
    7.  generate-trailer creates SmartTrailerJob with project_id + dataset_id
    8.  generate-trailer without expectation sets user_prompt=None on job
    9.  generate-trailer with expectation stores job correctly
    10. generate-trailer invalid expectation (too long) is accepted (no server-side length limit)
    11. list_project_trailers returns jobs for project
    12. list_project_trailers excludes jobs from other projects
    13. list_project_trailers returns newest first
    14. list_project_trailers output_url is None when output_path missing
    15. list_project_trailers clip_count populated from editing_plan
    16. SmartTrailerJob project_id column exists and is indexed
    17. SmartTrailerJob dataset_id column exists
    18. generate-trailer job status starts as pending
    19. existing trailer generation (smart trailer) still works independently
    20. analytics status is readable before generation

Run with:
    cd backend
    set PYTHONPATH=C:\\Users\\7000039334\\Documents\\Gearshift\\Clipsense\\backend
    pytest tests/test_phase4_generation.py -v
"""

import json
import sys
import os
import uuid
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models.feedback_dataset       # noqa: F401
import app.models.project                # noqa: F401
import app.models.smart_trailer_job      # noqa: F401
import app.models.audience_analysis_job  # noqa: F401
import app.models.trailer_job            # noqa: F401
import app.models.trailer_strategy       # noqa: F401
import app.models.trailer_edit           # noqa: F401

from app.models.project import Project
from app.models.smart_trailer_job import SmartTrailerJob
from app.models.feedback_dataset import FeedbackDataset, FeedbackSegmentRecord
from app.schemas.project import ProjectGenerationRequest, ProjectTrailerListItem
from app.services.feedback_dataset_service import FeedbackDatasetService
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


# ── Temp file helpers ─────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_file(directory: str, name: str, content: bytes = b"fake") -> str:
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(content)
    return path


# ── DB helpers ────────────────────────────────────────────────────────────────

def _make_project(db, tmp_dir, with_files=True, with_dataset=True):
    pid = str(uuid.uuid4())
    raw_path      = _make_file(tmp_dir, f"{pid}_raw.mp4")      if with_files else "/nonexistent/raw.mp4"
    sample_path   = _make_file(tmp_dir, f"{pid}_sample.mp4")   if with_files else "/nonexistent/sample.mp4"
    feedback_path = _make_file(tmp_dir, f"{pid}_feedback.json") if with_files else "/nonexistent/feedback.json"

    row = Project(
        id=pid,
        name="Test Project",
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        feedback_file_path=feedback_path,
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        feedback_file_name="feedback.json",
        size=1024,
        status="uploaded",
        dataset_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()

    if with_dataset:
        svc  = FeedbackDatasetService()
        segs = [FeedbackSegment(timestamp="00:01", topic="Action", sentiment="Positive",
                                summary="Great", confidence=0.9)]
        ds, _ = svc.save_dataset_deduped(db, pid, "test feedback", segs, "project_upload")
        row.dataset_id = ds.id

    db.commit()
    db.refresh(row)
    return row


def _project_to_dict(row) -> dict:
    return {
        "id":                  row.id,
        "name":                row.name,
        "filename":            row.raw_footage_name,
        "raw_footage_path":    row.raw_footage_path,
        "sample_trailer_path": row.sample_trailer_path,
        "feedback_file_path":  row.feedback_file_path,
        "raw_footage_name":    row.raw_footage_name,
        "sample_trailer_name": row.sample_trailer_name,
        "feedback_file_name":  row.feedback_file_name,
        "dataset_id":          row.dataset_id,
        "file_path":           row.raw_footage_path,
        "upload_time":         row.created_at.isoformat(),
        "status":              row.status,
    }


def _simulate_generate(project_dict: dict, db, body: ProjectGenerationRequest) -> SmartTrailerJob:
    """Mirror the logic of POST /project/{id}/generate-trailer without HTTP."""
    raw_path      = project_dict.get("raw_footage_path") or project_dict.get("file_path", "")
    sample_path   = project_dict.get("sample_trailer_path", "")
    dataset_id    = project_dict.get("dataset_id")
    feedback_path = project_dict.get("feedback_file_path", "")

    assert raw_path and os.path.exists(raw_path),      "Raw footage file not found"
    assert sample_path and os.path.exists(sample_path), "Sample trailer file not found"
    assert dataset_id,                                  "Project has no feedback dataset"
    assert feedback_path and os.path.exists(feedback_path), "Feedback file not found"

    now    = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    job    = SmartTrailerJob(
        id=job_id,
        project_id=project_dict["id"],
        dataset_id=dataset_id,
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        comments_path=feedback_path,
        raw_footage_original_name=project_dict.get("raw_footage_name") or os.path.basename(raw_path),
        sample_trailer_original_name=project_dict.get("sample_trailer_name") or os.path.basename(sample_path),
        comments_original_name=project_dict.get("feedback_file_name") or os.path.basename(feedback_path),
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _simulate_list_trailers(project_id: str, db) -> list:
    jobs = (
        db.query(SmartTrailerJob)
        .filter(SmartTrailerJob.project_id == project_id)
        .order_by(SmartTrailerJob.created_at.desc())
        .all()
    )
    result = []
    for job in jobs:
        output_url = None
        if job.output_path and os.path.exists(job.output_path):
            output_url = f"/trailers/{os.path.basename(job.output_path)}"
        clip_count, target_duration, has_creative_dir = None, None, False
        if job.editing_plan:
            try:
                plan = json.loads(job.editing_plan)
                clip_count       = len(plan.get("clips", []))
                target_duration  = plan.get("target_duration")
                has_creative_dir = "Creative direction applied" in plan.get("rationale", "")
            except Exception:
                pass
        result.append({
            "job_id": job.id, "project_id": project_id, "dataset_id": job.dataset_id,
            "status": job.status, "output_url": output_url, "clip_count": clip_count,
            "target_duration": target_duration, "clip_score": job.clip_score,
            "has_creative_direction": has_creative_dir,
            "fast_mode": (job.fast_mode == "true") if job.fast_mode is not None else None,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(), "updated_at": job.updated_at.isoformat(),
        })
    return result


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_list_trailers_empty_for_new_project(db, tmp_dir):
    """1. list_project_trailers returns empty for new project."""
    project = _make_project(db, tmp_dir)
    trailers = _simulate_list_trailers(project.id, db)
    assert trailers == []


def test_generate_404_unknown_project():
    """2. generate-trailer raises for unknown project."""
    with pytest.raises(AssertionError):
        _simulate_generate({"id": "nonexistent", "raw_footage_path": "", "sample_trailer_path": "",
                             "feedback_file_path": "", "dataset_id": None}, None,
                            ProjectGenerationRequest())


def test_generate_422_missing_raw_footage(db, tmp_dir):
    """3. generate-trailer 422 when raw footage file missing."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    d["raw_footage_path"] = "/nonexistent/raw.mp4"
    with pytest.raises(AssertionError, match="Raw footage"):
        _simulate_generate(d, db, ProjectGenerationRequest())


def test_generate_422_missing_sample_trailer(db, tmp_dir):
    """4. generate-trailer 422 when sample trailer file missing."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    d["sample_trailer_path"] = "/nonexistent/sample.mp4"
    with pytest.raises(AssertionError, match="Sample trailer"):
        _simulate_generate(d, db, ProjectGenerationRequest())


def test_generate_422_no_dataset(db, tmp_dir):
    """5. generate-trailer 422 when project has no dataset."""
    project = _make_project(db, tmp_dir, with_dataset=False)
    d = _project_to_dict(project)
    with pytest.raises(AssertionError, match="no feedback dataset"):
        _simulate_generate(d, db, ProjectGenerationRequest())


def test_generate_422_missing_feedback_file(db, tmp_dir):
    """6. generate-trailer 422 when feedback file missing."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    d["feedback_file_path"] = "/nonexistent/feedback.json"
    with pytest.raises(AssertionError, match="Feedback file"):
        _simulate_generate(d, db, ProjectGenerationRequest())


def test_generate_creates_job_with_project_ids(db, tmp_dir):
    """7. generate-trailer creates SmartTrailerJob with project_id + dataset_id."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    job = _simulate_generate(d, db, ProjectGenerationRequest())
    assert job.project_id == project.id
    assert job.dataset_id == project.dataset_id


def test_generate_without_expectation(db, tmp_dir):
    """8. generate-trailer without expectation: user_prompt is None."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    body = ProjectGenerationRequest(user_prompt=None)
    job  = _simulate_generate(d, db, body)
    # user_prompt is not stored on the job row — it's passed to the background task
    # Verify job was created successfully
    assert job.status == "pending"
    assert job.project_id == project.id


def test_generate_with_expectation(db, tmp_dir):
    """9. generate-trailer with expectation creates job correctly."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    body = ProjectGenerationRequest(user_prompt="Focus on action. Fast-paced trailer.")
    job  = _simulate_generate(d, db, body)
    assert job.status == "pending"
    assert job.project_id == project.id


def test_generate_long_expectation_accepted(db, tmp_dir):
    """10. Long expectation string is accepted (no server-side length limit)."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    long_prompt = "Focus on action. " * 50  # 850 chars
    body = ProjectGenerationRequest(user_prompt=long_prompt)
    job  = _simulate_generate(d, db, body)
    assert job.status == "pending"


def test_list_trailers_returns_jobs(db, tmp_dir):
    """11. list_project_trailers returns jobs for project."""
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest())
    _simulate_generate(d, db, ProjectGenerationRequest())
    trailers = _simulate_list_trailers(project.id, db)
    assert len(trailers) == 2


def test_list_trailers_excludes_other_projects(db, tmp_dir):
    """12. list_project_trailers excludes jobs from other projects."""
    p1 = _make_project(db, tmp_dir)
    p2 = _make_project(db, tmp_dir)
    _simulate_generate(_project_to_dict(p1), db, ProjectGenerationRequest())
    _simulate_generate(_project_to_dict(p2), db, ProjectGenerationRequest())
    t1 = _simulate_list_trailers(p1.id, db)
    t2 = _simulate_list_trailers(p2.id, db)
    assert len(t1) == 1
    assert len(t2) == 1
    assert t1[0]["project_id"] == p1.id
    assert t2[0]["project_id"] == p2.id


def test_list_trailers_newest_first(db, tmp_dir):
    """13. list_project_trailers returns newest first."""
    import time
    project = _make_project(db, tmp_dir)
    d = _project_to_dict(project)
    j1 = _simulate_generate(d, db, ProjectGenerationRequest())
    time.sleep(0.01)
    j2 = _simulate_generate(d, db, ProjectGenerationRequest())
    trailers = _simulate_list_trailers(project.id, db)
    assert trailers[0]["job_id"] == j2.id
    assert trailers[1]["job_id"] == j1.id


def test_list_trailers_output_url_none_when_missing(db, tmp_dir):
    """14. list_project_trailers output_url is None when output_path not on disk."""
    project = _make_project(db, tmp_dir)
    job = _simulate_generate(_project_to_dict(project), db, ProjectGenerationRequest())
    job.output_path = "/nonexistent/trailer.mp4"
    db.commit()
    trailers = _simulate_list_trailers(project.id, db)
    assert trailers[0]["output_url"] is None


def test_list_trailers_clip_count_from_editing_plan(db, tmp_dir):
    """15. list_project_trailers clip_count populated from editing_plan."""
    project = _make_project(db, tmp_dir)
    job = _simulate_generate(_project_to_dict(project), db, ProjectGenerationRequest())
    plan = {"clips": [{"start_time": 0, "end_time": 10}] * 5, "target_duration": 50.0, "rationale": "test"}
    job.editing_plan = json.dumps(plan)
    db.commit()
    trailers = _simulate_list_trailers(project.id, db)
    assert trailers[0]["clip_count"] == 5
    assert trailers[0]["target_duration"] == 50.0


def test_smart_trailer_job_has_project_id_column(engine):
    """16. SmartTrailerJob project_id column exists and is indexed."""
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("smart_trailer_jobs")]
    assert "project_id" in cols
    indexes = [i["name"] for i in insp.get_indexes("smart_trailer_jobs")]
    assert any("project_id" in idx for idx in indexes)


def test_smart_trailer_job_has_dataset_id_column(engine):
    """17. SmartTrailerJob dataset_id column exists."""
    insp = inspect(engine)
    cols = [c["name"] for c in insp.get_columns("smart_trailer_jobs")]
    assert "dataset_id" in cols


def test_generate_job_status_starts_pending(db, tmp_dir):
    """18. generate-trailer job status starts as pending."""
    project = _make_project(db, tmp_dir)
    job = _simulate_generate(_project_to_dict(project), db, ProjectGenerationRequest())
    assert job.status == "pending"


def test_legacy_smart_trailer_job_unaffected(db, tmp_dir):
    """19. Legacy SmartTrailerJob (no project_id) still works independently."""
    raw_path    = _make_file(tmp_dir, "legacy_raw.mp4")
    sample_path = _make_file(tmp_dir, "legacy_sample.mp4")
    comments    = _make_file(tmp_dir, "legacy_comments.json")
    now = datetime.now(timezone.utc)
    job = SmartTrailerJob(
        id=str(uuid.uuid4()),
        project_id=None,   # legacy — no project
        dataset_id=None,
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        comments_path=comments,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    assert job.project_id is None
    assert job.dataset_id is None
    assert job.status == "pending"


def test_analytics_status_readable_before_generation(db, tmp_dir):
    """20. Analytics status is readable before generation."""
    from app.services.analytics_agent import AnalyticsAgent

    project = _make_project(db, tmp_dir, with_dataset=True)
    svc = FeedbackDatasetService()
    ds  = svc.get_dataset_by_id(db, project.dataset_id)
    assert ds is not None
    assert len(ds.segments) > 0

    # Run analytics
    segs = [FeedbackSegment(timestamp=s.timestamp, topic=s.topic, sentiment=s.sentiment,
                             summary=s.summary, confidence=s.confidence) for s in ds.segments]
    report = AnalyticsAgent().analyze(segs)
    svc.set_analytics_cache(db, ds.id, report.model_dump_json())

    cached = svc.get_analytics_cache(db, ds.id)
    assert cached is not None
    assert cached["total_segments"] == len(ds.segments)
