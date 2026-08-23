"""
Phase 5 — Multiple Trailer Generation / Regeneration Tests

Covers:
    1.  first generation — no prompt required
    2.  second generation — prompt is mandatory
    3.  multiple generations — each stored as separate job
    4.  mandatory expectation enforced on regeneration
    5.  duplicate expectation — allowed (different job, same text)
    6.  failed regeneration — job created, status=failed, retry allowed
    7.  retry after failure — new job created with new prompt
    8.  output history — generation_number assigned correctly
    9.  project reload — trailers persist across sessions
    10. existing generation workflow — legacy smart trailer unaffected

Run with:
    cd backend
    set PYTHONPATH=C:\\Users\\7000039334\\Documents\\Gearshift\\Clipsense\\backend
    pytest tests/test_phase5_regeneration.py -v
"""

import json
import sys
import os
import uuid
import time
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
import app.models.feedback_dataset
import app.models.project
import app.models.smart_trailer_job
import app.models.audience_analysis_job
import app.models.trailer_job
import app.models.trailer_strategy
import app.models.trailer_edit

from app.models.project import Project
from app.models.smart_trailer_job import SmartTrailerJob
from app.models.feedback_dataset import FeedbackDataset
from app.schemas.project import ProjectGenerationRequest
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.schemas.feedback import FeedbackSegment


# ── Fixtures ──────────────────────────────────────────────────────────────────

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


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_file(directory: str, name: str) -> str:
    path = os.path.join(directory, name)
    with open(path, "wb") as f:
        f.write(b"fake")
    return path


def _make_project(db, tmp_dir) -> Project:
    pid = str(uuid.uuid4())
    raw_path      = _make_file(tmp_dir, f"{pid}_raw.mp4")
    sample_path   = _make_file(tmp_dir, f"{pid}_sample.mp4")
    feedback_path = _make_file(tmp_dir, f"{pid}_feedback.json")

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

    svc  = FeedbackDatasetService()
    segs = [FeedbackSegment(timestamp="00:01", topic="Action", sentiment="Positive",
                            summary="Great", confidence=0.9)]
    ds, _ = svc.save_dataset_deduped(db, pid, "test feedback", segs, "project_upload")
    row.dataset_id = ds.id
    db.commit()
    db.refresh(row)
    return row


def _project_dict(row: Project) -> dict:
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
    """Mirror POST /project/{id}/generate-trailer logic including Phase 5 enforcement."""
    raw_path      = project_dict.get("raw_footage_path") or project_dict.get("file_path", "")
    sample_path   = project_dict.get("sample_trailer_path", "")
    dataset_id    = project_dict.get("dataset_id")
    feedback_path = project_dict.get("feedback_file_path", "")

    assert raw_path and os.path.exists(raw_path),       "Raw footage file not found"
    assert sample_path and os.path.exists(sample_path), "Sample trailer file not found"
    assert dataset_id,                                   "Project has no feedback dataset"
    assert feedback_path and os.path.exists(feedback_path), "Feedback file not found"

    # Phase 5: mandatory prompt on regeneration
    existing_count = (
        db.query(SmartTrailerJob)
        .filter(SmartTrailerJob.project_id == project_dict["id"])
        .count()
    )
    if existing_count > 0 and not (body.user_prompt or "").strip():
        raise ValueError("Expectations are required for regeneration.")

    now    = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    job    = SmartTrailerJob(
        id=job_id,
        project_id=project_dict["id"],
        dataset_id=dataset_id,
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        comments_path=feedback_path,
        raw_footage_original_name=project_dict.get("raw_footage_name"),
        sample_trailer_original_name=project_dict.get("sample_trailer_name"),
        comments_original_name=project_dict.get("feedback_file_name"),
        user_prompt=(body.user_prompt or "").strip() or None,
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
    total = len(jobs)
    result = []
    for idx, job in enumerate(jobs):
        output_url = None
        if job.output_path and os.path.exists(job.output_path):
            output_url = f"/trailers/{os.path.basename(job.output_path)}"
        result.append({
            "job_id":            job.id,
            "project_id":        project_id,
            "generation_number": total - idx,
            "user_prompt":       job.user_prompt,
            "status":            job.status,
            "output_url":        output_url,
            "error_message":     job.error_message,
            "created_at":        job.created_at.isoformat(),
        })
    return result


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_first_generation_no_prompt_required(db, tmp_dir):
    """1. First generation — user_prompt is optional."""
    project = _make_project(db, tmp_dir)
    job = _simulate_generate(_project_dict(project), db, ProjectGenerationRequest(user_prompt=None))
    assert job.status == "pending"
    assert job.user_prompt is None


def test_second_generation_prompt_mandatory(db, tmp_dir):
    """2. Second generation — prompt is mandatory."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="First generation."))
    with pytest.raises(ValueError, match="Expectations are required"):
        _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))


def test_multiple_generations_separate_jobs(db, tmp_dir):
    """3. Multiple generations — each stored as a separate job."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    j1 = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))
    j2 = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Focus on action."))
    j3 = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Emotional moments."))
    assert j1.id != j2.id != j3.id
    trailers = _simulate_list_trailers(project.id, db)
    assert len(trailers) == 3


def test_mandatory_expectation_empty_string_rejected(db, tmp_dir):
    """4. Empty string expectation is rejected on regeneration."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="First."))
    with pytest.raises(ValueError, match="Expectations are required"):
        _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="   "))


def test_duplicate_expectation_allowed(db, tmp_dir):
    """5. Duplicate expectation text is allowed — creates a new job."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    j1 = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Focus on action."))
    j2 = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Focus on action."))
    assert j1.id != j2.id
    assert j1.user_prompt == j2.user_prompt == "Focus on action."


def test_failed_regeneration_job_created(db, tmp_dir):
    """6. Failed regeneration — job is created with status=pending, can be set to failed."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))
    job = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Try again."))
    # Simulate pipeline failure
    job.status = "failed"
    job.error_message = "FFmpeg error"
    db.commit()
    trailers = _simulate_list_trailers(project.id, db)
    failed = next(t for t in trailers if t["job_id"] == job.id)
    assert failed["status"] == "failed"
    assert failed["error_message"] == "FFmpeg error"


def test_retry_after_failure_creates_new_job(db, tmp_dir):
    """7. Retry after failure — new job created with new prompt."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))
    failed_job = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="First attempt."))
    failed_job.status = "failed"
    db.commit()

    retry_job = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Retry with new focus."))
    assert retry_job.id != failed_job.id
    assert retry_job.user_prompt == "Retry with new focus."
    assert retry_job.status == "pending"


def test_generation_number_assigned_correctly(db, tmp_dir):
    """8. Output history — generation_number is 1-based, oldest=1, newest=N."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))
    time.sleep(0.01)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Second."))
    time.sleep(0.01)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Third."))

    trailers = _simulate_list_trailers(project.id, db)
    # Newest first in list, so trailers[0] = gen 3, trailers[2] = gen 1
    assert trailers[0]["generation_number"] == 3
    assert trailers[1]["generation_number"] == 2
    assert trailers[2]["generation_number"] == 1


def test_project_reload_trailers_persist(db, tmp_dir):
    """9. Project reload — trailers persist across DB sessions."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt=None))
    _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Second generation."))

    # Simulate reload by querying fresh
    trailers = _simulate_list_trailers(project.id, db)
    assert len(trailers) == 2
    assert trailers[0]["user_prompt"] == "Second generation."
    assert trailers[1]["user_prompt"] is None


def test_user_prompt_stored_on_job(db, tmp_dir):
    """8b. user_prompt is stored on the job row and returned in history."""
    project = _make_project(db, tmp_dir)
    d = _project_dict(project)
    job = _simulate_generate(d, db, ProjectGenerationRequest(user_prompt="Focus on suspense."))
    assert job.user_prompt == "Focus on suspense."
    trailers = _simulate_list_trailers(project.id, db)
    assert trailers[0]["user_prompt"] == "Focus on suspense."


def test_legacy_smart_trailer_unaffected(db, tmp_dir):
    """10. Existing generation workflow — legacy SmartTrailerJob (no project_id) unaffected."""
    raw_path    = _make_file(tmp_dir, f"legacy_{uuid.uuid4().hex}_raw.mp4")
    sample_path = _make_file(tmp_dir, f"legacy_{uuid.uuid4().hex}_sample.mp4")
    comments    = _make_file(tmp_dir, f"legacy_{uuid.uuid4().hex}_comments.json")
    now = datetime.now(timezone.utc)
    job = SmartTrailerJob(
        id=str(uuid.uuid4()),
        project_id=None,
        dataset_id=None,
        user_prompt=None,
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
    assert job.user_prompt is None
    assert job.status == "pending"
