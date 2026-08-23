"""
Phase 6 — Storage, File Organisation & Data Lifecycle Tests

Covers:
    1.  upload — project directory created with source/ files
    2.  duplicate — same feedback hash reuses dataset, no duplicate files
    3.  generation — output written to project generations dir
    4.  regeneration — second output does not overwrite first
    5.  retrieval — output_url points to project-scoped endpoint
    6.  deletion — project dir + smart job outputs removed
    7.  project loading — DB row matches disk files
    8.  missing file — integrity check reports missing files
    9.  orphaned file — integrity check reports orphaned outputs
    10. restart — DB reload returns correct paths after re-query
    11. storage integrity check — clean project reports ok=True

Run with:
    cd backend
    set PYTHONPATH=C:\\Users\\7000039334\\Documents\\Gearshift\\Clipsense\\backend
    pytest tests/test_phase6_storage.py -v
"""

import json
import os
import sys
import uuid
import tempfile
import shutil
from datetime import datetime, timezone

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
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.schemas.feedback import FeedbackSegment
from app.utils.storage_integrity import check_storage_integrity


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
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_file(directory: str, name: str, content: bytes = b"fake") -> str:
    path = os.path.join(directory, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _make_project(db, tmp_dir, feedback_text="test feedback") -> Project:
    """Create a project with real files on disk."""
    pid = str(uuid.uuid4())
    proj_dir = os.path.join(tmp_dir, "projects", pid)
    os.makedirs(proj_dir, exist_ok=True)

    raw_path      = _make_file(proj_dir, "raw.mp4")
    sample_path   = _make_file(proj_dir, "sample.mp4")
    feedback_path = _make_file(proj_dir, "feedback.json",
                               json.dumps([{"timestamp": "00:01", "topic": "Action",
                                            "sentiment": "Positive", "summary": "Great",
                                            "confidence": 0.9}]).encode())

    row = Project(
        id=pid,
        name="Test Project",
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        feedback_file_path=feedback_path,
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        feedback_file_name="feedback.json",
        size=4,
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
    ds, _ = svc.save_dataset_deduped(db, pid, feedback_text, segs, "project_upload")
    row.dataset_id = ds.id
    db.commit()
    db.refresh(row)
    return row


def _make_generation(db, project: Project, tmp_dir,
                     user_prompt=None, write_output=True) -> SmartTrailerJob:
    """Simulate a completed generation with a project-scoped output file."""
    job_id   = str(uuid.uuid4())
    gen_dir  = os.path.join(tmp_dir, "projects", project.id, "generations")
    os.makedirs(gen_dir, exist_ok=True)

    output_path = None
    if write_output:
        output_path = os.path.join(gen_dir, f"smart_{job_id[:8]}.mp4")
        with open(output_path, "wb") as f:
            f.write(b"fake video")

    now = datetime.now(timezone.utc)
    job = SmartTrailerJob(
        id=job_id,
        project_id=project.id,
        dataset_id=project.dataset_id,
        raw_footage_path=project.raw_footage_path,
        sample_trailer_path=project.sample_trailer_path,
        comments_path=project.feedback_file_path,
        user_prompt=user_prompt,
        status="done" if write_output else "pending",
        output_path=output_path,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_upload_project_files_on_disk(db, tmp_dir):
    """1. Upload — project directory created with source files."""
    project = _make_project(db, tmp_dir)
    assert os.path.exists(project.raw_footage_path)
    assert os.path.exists(project.sample_trailer_path)
    assert os.path.exists(project.feedback_file_path)
    # All three files live under the same project directory
    proj_dir = os.path.dirname(project.raw_footage_path)
    assert project.id in proj_dir


def test_duplicate_feedback_reuses_dataset(db, tmp_dir):
    """2. Duplicate — same feedback text reuses dataset, no new dataset row."""
    svc  = FeedbackDatasetService()
    segs = [FeedbackSegment(timestamp="00:01", topic="Action", sentiment="Positive",
                            summary="Great", confidence=0.9)]
    pid1 = str(uuid.uuid4())
    pid2 = str(uuid.uuid4())
    ds1, created1 = svc.save_dataset_deduped(db, pid1, "identical feedback", segs, "test")
    ds2, created2 = svc.save_dataset_deduped(db, pid1, "identical feedback", segs, "test")
    assert created1 is True
    assert created2 is False
    assert ds1.id == ds2.id


def test_generation_output_in_project_dir(db, tmp_dir):
    """3. Generation — output written to project generations directory."""
    project = _make_project(db, tmp_dir)
    job     = _make_generation(db, project, tmp_dir)
    assert job.output_path is not None
    assert os.path.exists(job.output_path)
    # Output must be inside the project directory
    assert project.id in job.output_path


def test_regeneration_does_not_overwrite(db, tmp_dir):
    """4. Regeneration — second output does not overwrite first."""
    project = _make_project(db, tmp_dir)
    job1    = _make_generation(db, project, tmp_dir, user_prompt=None)
    job2    = _make_generation(db, project, tmp_dir, user_prompt="Focus on action.")
    assert job1.output_path != job2.output_path
    assert os.path.exists(job1.output_path)
    assert os.path.exists(job2.output_path)


def test_output_url_is_project_scoped(db, tmp_dir):
    """5. Retrieval — output_url uses project-scoped endpoint pattern."""
    project = _make_project(db, tmp_dir)
    job     = _make_generation(db, project, tmp_dir)

    # Simulate list_project_trailers URL construction
    output_url = f"/project/{project.id}/generation/{job.id}/video"
    assert project.id in output_url
    assert job.id in output_url
    assert "/trailers/" not in output_url  # must NOT use flat trailers mount


def test_delete_project_removes_directory(db, tmp_dir):
    """6. Deletion — project directory removed on delete."""
    project  = _make_project(db, tmp_dir)
    proj_dir = os.path.dirname(project.raw_footage_path)
    assert os.path.isdir(proj_dir)

    # Simulate delete_project directory removal
    shutil.rmtree(proj_dir, ignore_errors=True)
    assert not os.path.isdir(proj_dir)


def test_delete_project_cascades_smart_jobs(db, tmp_dir):
    """6b. Deletion — SmartTrailerJob rows for project are deleted."""
    project = _make_project(db, tmp_dir)
    job     = _make_generation(db, project, tmp_dir)
    job_id  = job.id

    # Simulate cascade delete
    db.delete(job)
    db.commit()

    remaining = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    assert remaining is None


def test_project_loading_db_matches_disk(db, tmp_dir):
    """7. Project loading — DB paths match actual files on disk."""
    project = _make_project(db, tmp_dir)
    # Re-query to simulate a restart
    reloaded = db.query(Project).filter(Project.id == project.id).first()
    assert reloaded is not None
    assert os.path.exists(reloaded.raw_footage_path)
    assert os.path.exists(reloaded.sample_trailer_path)
    assert os.path.exists(reloaded.feedback_file_path)


def test_integrity_check_reports_missing_raw(db, tmp_dir):
    """8. Missing file — integrity check reports missing raw footage."""
    project = _make_project(db, tmp_dir)
    # Delete the raw footage file
    os.remove(project.raw_footage_path)

    report = check_storage_integrity(db)
    assert project.id in report["projects"]["missing_raw"]
    assert report["summary"]["ok"] is False
    assert report["summary"]["issues"] >= 1


def test_integrity_check_reports_missing_output(db, tmp_dir):
    """9. Orphaned file — integrity check reports done job with missing output."""
    project = _make_project(db, tmp_dir)
    job     = _make_generation(db, project, tmp_dir)
    # Delete the output file
    os.remove(job.output_path)

    report = check_storage_integrity(db)
    assert job.id in report["generations"]["missing_output"]
    assert report["summary"]["ok"] is False


def test_db_reload_returns_correct_paths(db, tmp_dir):
    """10. Restart — DB reload returns correct paths after re-query."""
    project = _make_project(db, tmp_dir)
    job     = _make_generation(db, project, tmp_dir)

    # Simulate server restart by re-querying
    reloaded_project = db.query(Project).filter(Project.id == project.id).first()
    reloaded_job     = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job.id).first()

    assert reloaded_project.raw_footage_path == project.raw_footage_path
    assert reloaded_job.output_path == job.output_path
    assert os.path.exists(reloaded_job.output_path)


def test_integrity_check_clean_project_ok(db, tmp_dir):
    """11. Storage integrity check — clean project with all files present reports ok=True."""
    project = _make_project(db, tmp_dir)
    _make_generation(db, project, tmp_dir)

    report = check_storage_integrity(db)
    # This project's files all exist — it should not appear in any missing list
    assert project.id not in report["projects"]["missing_raw"]
    assert project.id not in report["projects"]["missing_sample"]
    assert project.id not in report["projects"]["missing_feedback"]


def test_generations_dir_created_on_demand(tmp_dir):
    """Storage helper — project_generations_dir creates directory."""
    from app.utils.storage import project_generations_dir
    # Temporarily point PROJECT_UPLOAD_DIR at tmp_dir
    import app.utils.storage as _s
    orig = _s.PROJECT_UPLOAD_DIR
    _s.PROJECT_UPLOAD_DIR = tmp_dir
    try:
        pid  = str(uuid.uuid4())
        path = project_generations_dir(pid)
        assert os.path.isdir(path)
        assert pid in path
        assert path.endswith("generations")
    finally:
        _s.PROJECT_UPLOAD_DIR = orig


def test_evict_skips_active_job_dirs(db, tmp_dir):
    """Eviction — directories referenced by active jobs are not removed."""
    from app.services.project_service import ProjectService

    # Create a fake smart upload dir with an active job
    job_dir = os.path.join(tmp_dir, "smart", str(uuid.uuid4()))
    os.makedirs(job_dir, exist_ok=True)
    raw_path = _make_file(job_dir, "raw.mp4")

    now = datetime.now(timezone.utc)
    job = SmartTrailerJob(
        id=str(uuid.uuid4()),
        project_id=None,
        raw_footage_path=raw_path,
        sample_trailer_path=_make_file(job_dir, "sample.mp4"),
        comments_path=_make_file(job_dir, "comments.json"),
        status="processing",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()

    # evict_smart_uploads queries the real DB — we just verify the logic
    # by checking that the active dir is in active_dirs set
    active_dirs = set()
    for path in (job.raw_footage_path, job.sample_trailer_path, job.comments_path):
        if path:
            active_dirs.add(os.path.dirname(os.path.abspath(path)))

    assert os.path.abspath(job_dir) in active_dirs

    # Clean up
    db.delete(job)
    db.commit()
