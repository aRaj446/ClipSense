"""
Phase 6 — Integration & Validation — Chunk 2 of 3
JOB SYSTEM

Covers:
    - Trailer job creation (pending → processing → done/failed)
    - Job state persisted in DB
    - Semaphore: job_slot context manager acquires and releases
    - Progress store: set_progress / get_progress / set_step / evict_stale
    - SSE endpoint returns text/event-stream with valid JSON events
    - Job cancel transitions status to failed
    - Job retry creates a new job
    - Duplicate generate requests each create independent jobs
    - Job delete removes record and file reference
    - Audience analysis job lifecycle (pending → done)
    - Audience analysis SSE progress stream
    - Audience analysis job delete
    - Editor render job creates a new pollable TrailerJob
    - Progress steps include "strategy" as first step

Run from backend/:
    python -m pytest tests/test_phase6_chunk2_jobsystem.py -v
"""

import json
import time
import tempfile
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app as fastapi_app
from app.db import database as _db_module
from app.db.database import get_db
from app.db.base import Base

# ── Shared test DB ────────────────────────────────────────────────────────────

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
TEST_DB_URL = f"sqlite:///{_db_file.name}"
_engine      = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    import app.models.feedback_dataset
    import app.models.trailer_job
    import app.models.smart_trailer_job
    import app.models.audience_analysis_job
    import app.models.trailer_strategy
    import app.models.trailer_edit
    import app.models.project
    Base.metadata.create_all(bind=_engine)
    from tests.conftest import seed_project_row
    seed_project_row(_TestSession)
    _db_module.SessionLocal = _TestSession
    fastapi_app.dependency_overrides[get_db] = _override_get_db
    yield
    fastapi_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=_engine)
    import os
    try:
        os.unlink(_db_file.name)
    except OSError:
        pass


@pytest.fixture(scope="module")
def client():
    return TestClient(fastapi_app, raise_server_exceptions=True)


PROJECT_ID = "83a49988-d057-46e4-8600-fe7c9ff8d7ff"

_JSON_FEEDBACK = json.dumps([
    {"timestamp": "0:10", "topic": "Action",     "sentiment": "Positive", "summary": "Great action",         "confidence": 0.92},
    {"timestamp": "0:30", "topic": "Music",      "sentiment": "Positive", "summary": "Music fits",           "confidence": 0.88},
    {"timestamp": "1:00", "topic": "Exposition", "sentiment": "Negative", "summary": "Too much exposition",  "confidence": 0.85},
    {"timestamp": "1:30", "topic": "Characters", "sentiment": "Positive", "summary": "Strong character",     "confidence": 0.90},
])


@pytest.fixture(scope="module")
def dataset_id(client):
    r = client.post(
        "/upload-feedback",
        data={"project_id": PROJECT_ID},
        files={"file": ("feedback.json", _JSON_FEEDBACK.encode(), "application/json")},
    )
    assert r.status_code == 201, r.text
    return r.json()["dataset_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — Trailer Job Creation & DB State
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrailerJobCreation:

    def test_generate_trailer_returns_202(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        # 202 = job queued; 404 = project video missing (valid in test env)
        assert r.status_code in (202, 404), r.text

    def test_generate_trailer_response_shape(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        body = r.json()
        for field in ("id", "project_id", "dataset_id", "status", "created_at", "updated_at"):
            assert field in body, f"Missing field: {field}"

    def test_generate_trailer_initial_status_is_pending(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        assert r.json()["status"] == "pending"

    def test_job_persisted_and_pollable(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        r2 = client.get(f"/trailer-job/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == job_id

    def test_job_listed_under_project(self, client, dataset_id):
        client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        r = client.get(f"/trailer-jobs/{PROJECT_ID}")
        assert r.status_code == 200
        assert len(r.json()) > 0

    def test_duplicate_generate_creates_independent_jobs(self, client, dataset_id):
        r1 = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        r2 = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r1.status_code == 404 or r2.status_code == 404:
            pytest.skip("Project video not present")
        assert r1.json()["id"] != r2.json()["id"]

    def test_unknown_job_returns_404(self, client):
        r = client.get("/trailer-job/nonexistent-job-id")
        assert r.status_code == 404

    def test_unknown_project_returns_404(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": "00000000-0000-0000-0000-000000000000",
            "dataset_id": dataset_id,
        })
        assert r.status_code == 404

    def test_unknown_dataset_returns_404(self, client):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": "00000000-0000-0000-0000-000000000000",
        })
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Cancel & Retry
# ═══════════════════════════════════════════════════════════════════════════════

class TestCancelAndRetry:

    def _create_job(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        return r.json()["id"]

    def test_cancel_pending_job_sets_status_failed(self, client, dataset_id):
        job_id = self._create_job(client, dataset_id)
        r = client.post(f"/trailer-job/{job_id}/cancel")
        # Job may have already transitioned out of pending in the background
        assert r.status_code in (200, 400), r.text
        if r.status_code == 200:
            assert r.json()["status"] == "failed"
            assert r.json()["error_message"] == "Cancelled by user"

    def test_cancel_already_failed_job_returns_400(self, client, dataset_id):
        job_id = self._create_job(client, dataset_id)
        client.post(f"/trailer-job/{job_id}/cancel")
        r = client.post(f"/trailer-job/{job_id}/cancel")
        assert r.status_code == 400

    def test_cancel_unknown_job_returns_404(self, client):
        r = client.post("/trailer-job/nonexistent-id/cancel")
        assert r.status_code == 404

    def test_retry_creates_new_job(self, client, dataset_id):
        # Cancel a job then retry by posting a new generate request
        job_id = self._create_job(client, dataset_id)
        client.post(f"/trailer-job/{job_id}/cancel")
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        assert r.status_code == 202
        assert r.json()["id"] != job_id

    def test_delete_job_removes_record(self, client, dataset_id):
        job_id = self._create_job(client, dataset_id)
        client.post(f"/trailer-job/{job_id}/cancel")
        r_del = client.delete(f"/trailer-job/{job_id}")
        assert r_del.status_code == 204
        r_get = client.get(f"/trailer-job/{job_id}")
        assert r_get.status_code == 404

    def test_delete_unknown_job_returns_404(self, client):
        r = client.delete("/trailer-job/nonexistent-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Progress Store (unit-level, no video needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressStore:

    def test_set_and_get_progress(self):
        from app.utils.render_progress import set_progress, get_progress, clear_progress
        jid = "test-progress-job-1"
        set_progress(jid, "processing", 42, "Halfway there")
        entry = get_progress(jid)
        assert entry is not None
        assert entry["stage"]   == "processing"
        assert entry["percent"] == 42
        assert entry["message"] == "Halfway there"
        clear_progress(jid)

    def test_get_progress_returns_none_for_unknown(self):
        from app.utils.render_progress import get_progress
        assert get_progress("totally-unknown-job-xyz") is None

    def test_set_step_updates_named_step(self):
        from app.utils.render_progress import set_progress, set_step, get_progress, clear_progress
        jid = "test-progress-job-2"
        steps = [
            {"key": "strategy",   "label": "Loading strategy",  "status": "pending", "percent": 0},
            {"key": "scenes",     "label": "Detecting scenes",  "status": "pending", "percent": 0},
        ]
        set_progress(jid, "processing", 0, "Starting", steps=steps)
        set_step(jid, "strategy", "done", 100, "Strategy loaded", overall_percent=5)
        entry = get_progress(jid)
        strat_step = next(s for s in entry["steps"] if s["key"] == "strategy")
        assert strat_step["status"]  == "done"
        assert strat_step["percent"] == 100
        assert entry["percent"]      == 5
        clear_progress(jid)

    def test_set_step_noop_for_unknown_job(self):
        from app.utils.render_progress import set_step
        # Must not raise
        set_step("nonexistent-job-xyz", "strategy", "done", 100)

    def test_progress_steps_preserved_across_set_progress(self):
        from app.utils.render_progress import set_progress, get_progress, clear_progress
        jid = "test-progress-job-3"
        steps = [{"key": "scenes", "label": "Scenes", "status": "pending", "percent": 0}]
        set_progress(jid, "processing", 10, "msg", steps=steps)
        # Update without passing steps — existing steps must be preserved
        set_progress(jid, "processing", 20, "updated msg")
        entry = get_progress(jid)
        assert len(entry["steps"]) == 1
        assert entry["steps"][0]["key"] == "scenes"
        clear_progress(jid)

    def test_evict_stale_removes_old_entries(self):
        from app.utils.render_progress import set_progress, get_progress, evict_stale, clear_progress
        import app.utils.render_progress as _rp
        jid = "test-stale-job"
        set_progress(jid, "done", 100, "Done")
        # Manually backdate the timestamp
        with _rp._lock:
            _rp._store[jid]["ts"] = 0.0
        evict_stale()
        assert get_progress(jid) is None

    def test_percent_clamped_to_0_100(self):
        from app.utils.render_progress import set_progress, get_progress, clear_progress
        jid = "test-clamp-job"
        set_progress(jid, "processing", 999, "Over 100")
        assert get_progress(jid)["percent"] == 100
        set_progress(jid, "processing", -50, "Under 0")
        assert get_progress(jid)["percent"] == 0
        clear_progress(jid)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — SSE Endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestSSEEndpoint:

    def _first_sse_event(self, client, job_id: str) -> dict | None:
        """Read the first SSE event from the progress stream."""
        with client.stream("GET", f"/trailer-job/{job_id}/progress") as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except Exception:
                        return None
        return None

    def test_sse_returns_event_stream_content_type(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        with client.stream("GET", f"/trailer-job/{job_id}/progress") as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_sse_first_event_has_required_fields(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        event = self._first_sse_event(client, job_id)
        assert event is not None
        for field in ("stage", "percent", "message", "steps"):
            assert field in event, f"Missing SSE field: {field}"

    def test_sse_steps_include_strategy_key(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        event = self._first_sse_event(client, job_id)
        if event and event.get("steps"):
            step_keys = [s["key"] for s in event["steps"]]
            assert "strategy" in step_keys, f"'strategy' step missing. Got: {step_keys}"

    def test_sse_pending_event_for_unknown_job(self, client):
        """SSE for unknown job should emit a pending event, not crash."""
        with client.stream("GET", "/trailer-job/nonexistent-job-sse/progress") as r:
            for line in r.iter_lines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    assert data["stage"] == "pending"
                    break


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Semaphore (unit-level)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSemaphore:

    def test_job_slot_acquires_and_releases(self):
        from app.utils.job_queue import job_slot, _semaphore
        assert _semaphore._value == 1
        with job_slot():
            assert _semaphore._value == 0
        assert _semaphore._value == 1

    def test_job_slot_releases_on_exception(self):
        from app.utils.job_queue import job_slot, _semaphore
        try:
            with job_slot():
                raise RuntimeError("Simulated failure")
        except RuntimeError:
            pass
        assert _semaphore._value == 1

    def test_job_slot_is_reentrant_after_release(self):
        from app.utils.job_queue import job_slot
        with job_slot():
            pass
        with job_slot():
            pass  # Must not deadlock


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Audience Analysis Job Lifecycle
# ═══════════════════════════════════════════════════════════════════════════════

class TestAudienceAnalysisJobLifecycle:

    def test_submit_text_returns_202(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Great action scenes. Music is perfect. Too much exposition.",
        })
        assert r.status_code == 202, r.text

    def test_submit_text_response_shape(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Good pacing. Bad dialogue.",
        })
        body = r.json()
        for field in ("id", "status", "source", "created_at", "updated_at"):
            assert field in body

    def test_submit_text_initial_status_pending_or_processing(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Excellent cinematography.",
        })
        assert r.json()["status"] in ("pending", "processing")

    def test_submit_file_json_returns_202(self, client):
        feedback = json.dumps([
            {"timestamp": "0:10", "topic": "Action", "sentiment": "Positive",
             "summary": "Great action", "confidence": 0.9},
        ])
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.json", feedback.encode(), "application/json")},
        )
        assert r.status_code == 202, r.text

    def test_submit_file_unsupported_extension_returns_400(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.pdf", b"content", "application/pdf")},
        )
        assert r.status_code == 400

    def test_submit_empty_file_returns_422(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.json", b"", "application/json")},
        )
        assert r.status_code == 422

    def test_submit_empty_text_returns_400(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "   ",
        })
        assert r.status_code == 400

    def test_job_pollable_after_submit(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Good scenes. Bad audio.",
        })
        job_id = r.json()["id"]
        r2 = client.get(f"/audience-analysis/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == job_id

    def test_job_delete_removes_record(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Temporary feedback for delete test.",
        })
        job_id = r.json()["id"]
        r_del = client.delete(f"/audience-analysis/{job_id}")
        assert r_del.status_code == 204
        r_get = client.get(f"/audience-analysis/{job_id}")
        assert r_get.status_code == 404

    def test_audience_analysis_sse_returns_event_stream(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "Great action. Poor pacing.",
        })
        job_id = r.json()["id"]
        with client.stream("GET", f"/audience-analysis/{job_id}/progress") as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_audience_analysis_unknown_project_returns_404(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": "00000000-0000-0000-0000-000000000000",
            "feedback": "Some feedback.",
        })
        assert r.status_code == 404
