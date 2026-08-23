"""
Phase 8 (Export) — Backend Tests

Covers:
    1.  Normal edit — POST /editor/{job_id}/render returns 202 + new_job_id
    2.  Trimmed clip — render accepts clips with modified start/end times
    3.  Reordered clips — render accepts clips in any order
    4.  Deleted clip — render accepts a plan with fewer clips than the AI plan
    5.  Invalid edit — render with empty clips returns 422 (no plan) or 400
    6.  Failure path — render of a pending source job returns 409
    7.  Retry path — second POST /render on same job creates a second independent job
    8.  SSE progress endpoint — GET /editor/{job_id}/render/progress returns SSE stream
    9.  SSE progress — unknown source job returns 404
    10. Original trailer untouched — source job output_path unchanged after render
    11. New job pollable via /trailer-job/{id} (standard)
    12. New job pollable via /smart-trailer/job/{id} (smart)
    13. Render response shape — new_job_id, message, job_type present
    14. job_type=standard for TrailerJob source
    15. job_type=smart for SmartTrailerJob source

Run from backend/:
    python -m pytest tests/test_phase8_export.py -v
"""

import json
import uuid
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile

from app.main import app as fastapi_app
from app.db import database as _db_module
from app.db.database import get_db
from app.db.base import Base


# ── In-memory test DB ─────────────────────────────────────────────────────────

_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
TEST_DB_URL  = f"sqlite:///{_db_file.name}"
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
    import app.models.smart_trailer_edit
    import app.models.project
    Base.metadata.create_all(bind=_engine)
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


# ── Helpers ───────────────────────────────────────────────────────────────────

_AI_CLIPS = [
    {
        "start_time": 0.0, "end_time": 5.0,
        "reason": "Opening action", "topic": "Action",
        "sentiment": "Positive", "platform": "youtube",
        "mood_group": "energetic", "transcript_text": "hello world",
    },
    {
        "start_time": 10.0, "end_time": 18.0,
        "reason": "Climax scene", "topic": "Drama",
        "sentiment": "Positive", "platform": "youtube",
        "mood_group": "intense", "transcript_text": "the end",
    },
    {
        "start_time": 25.0, "end_time": 30.0,
        "reason": "Outro", "topic": "General",
        "sentiment": "Neutral", "platform": "youtube",
        "mood_group": "calm", "transcript_text": "",
    },
]

_AI_PLAN = {
    "clips": _AI_CLIPS,
    "target_duration": 18.0,
    "audio_fade_out": True,
    "output_format": "mp4",
    "rationale": "AI plan",
}


def _make_trailer_job(status: str = "done", plan: dict | None = None) -> str:
    from app.models.trailer_job import TrailerJob
    db = _TestSession()
    try:
        job = TrailerJob(
            id=str(uuid.uuid4()),
            project_id="test-project-p8",
            dataset_id="test-dataset-p8",
            status=status,
            editing_plan=json.dumps(plan or _AI_PLAN),
            output_path="/tmp/fake_original_trailer.mp4",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _make_smart_job(status: str = "done", plan: dict | None = None) -> str:
    from app.models.smart_trailer_job import SmartTrailerJob
    db = _TestSession()
    try:
        job = SmartTrailerJob(
            id=str(uuid.uuid4()),
            project_id="test-project-p8",
            dataset_id="test-dataset-p8",
            raw_footage_path="/tmp/fake_raw.mp4",
            sample_trailer_path="/tmp/fake_sample.mp4",
            comments_path="/tmp/fake_comments.txt",
            status=status,
            editing_plan=json.dumps(plan or _AI_PLAN),
            output_path="/tmp/fake_original_smart_trailer.mp4",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _save_user_plan(client, job_id: str, clips: list) -> None:
    r = client.put(f"/editor/{job_id}/plan", json={"clips": clips})
    assert r.status_code == 200, f"PUT plan failed: {r.text}"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Normal edit — render from AI plan
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalEdit:

    def test_render_returns_202(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_response_shape(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        body = r.json()
        assert "new_job_id" in body
        assert "message" in body
        assert "job_type" in body

    def test_render_new_job_id_differs_from_source(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.json()["new_job_id"] != job_id

    def test_render_job_type_standard(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.json()["job_type"] == "standard"

    def test_render_job_type_smart(self, client):
        job_id = _make_smart_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.json()["job_type"] == "smart"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Trimmed clip — user saves trimmed plan, then renders
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrimmedClip:

    def test_render_accepts_trimmed_clips(self, client):
        job_id = _make_trailer_job()
        trimmed = [
            {**_AI_CLIPS[0], "start_time": 1.0, "end_time": 4.0},   # trimmed both ends
            {**_AI_CLIPS[1], "start_time": 10.5, "end_time": 17.5},  # trimmed both ends
        ]
        _save_user_plan(client, job_id, trimmed)
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_trimmed_creates_new_job(self, client):
        job_id = _make_trailer_job()
        trimmed = [{**_AI_CLIPS[0], "start_time": 0.5, "end_time": 4.5}]
        _save_user_plan(client, job_id, trimmed)
        r = client.post(f"/editor/{job_id}/render")
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/trailer-job/{new_id}")
        assert r2.status_code == 200
        assert r2.json()["status"] in ("pending", "processing", "done", "failed")

    def test_render_trimmed_smart_job(self, client):
        job_id = _make_smart_job()
        trimmed = [{**_AI_CLIPS[0], "start_time": 1.0, "end_time": 4.0}]
        _save_user_plan(client, job_id, trimmed)
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/smart-trailer/job/{new_id}")
        assert r2.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Reordered clips
# ═══════════════════════════════════════════════════════════════════════════════

class TestReorderedClips:

    def test_render_accepts_reordered_clips(self, client):
        job_id = _make_trailer_job()
        reordered = [_AI_CLIPS[2], _AI_CLIPS[0], _AI_CLIPS[1]]  # reversed order
        _save_user_plan(client, job_id, reordered)
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_reordered_new_job_pollable(self, client):
        job_id = _make_trailer_job()
        reordered = [_AI_CLIPS[1], _AI_CLIPS[0]]
        _save_user_plan(client, job_id, reordered)
        r = client.post(f"/editor/{job_id}/render")
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/trailer-job/{new_id}")
        assert r2.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Deleted clip — plan with fewer clips than AI plan
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeletedClip:

    def test_render_accepts_single_clip_plan(self, client):
        job_id = _make_trailer_job()
        _save_user_plan(client, job_id, [_AI_CLIPS[0]])
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_deleted_clip_new_job_created(self, client):
        job_id = _make_trailer_job()
        _save_user_plan(client, job_id, [_AI_CLIPS[1]])  # only middle clip
        r = client.post(f"/editor/{job_id}/render")
        new_id = r.json()["new_job_id"]
        assert new_id != job_id

    def test_render_deleted_clip_smart_job(self, client):
        job_id = _make_smart_job()
        _save_user_plan(client, job_id, [_AI_CLIPS[0]])
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Invalid edit — no plan available
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidEdit:

    def test_render_job_with_no_editing_plan_returns_422(self, client):
        """A job with no editing_plan and no user edit must return 422."""
        from app.models.trailer_job import TrailerJob
        db = _TestSession()
        try:
            job = TrailerJob(
                id=str(uuid.uuid4()),
                project_id="test-project-p8",
                dataset_id="test-dataset-p8",
                status="done",
                editing_plan=None,   # no AI plan
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(job)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 422, r.text

    def test_render_unknown_job_returns_404(self, client):
        r = client.post(f"/editor/{uuid.uuid4()}/render")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Failure path — pending source job
# ═══════════════════════════════════════════════════════════════════════════════

class TestFailurePath:

    def test_render_pending_trailer_job_returns_409(self, client):
        job_id = _make_trailer_job(status="pending")
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 409

    def test_render_pending_smart_job_returns_409(self, client):
        job_id = _make_smart_job(status="pending")
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 409

    def test_render_processing_trailer_job_returns_409(self, client):
        job_id = _make_trailer_job(status="processing")
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Retry path — two sequential renders on the same source job
# ═══════════════════════════════════════════════════════════════════════════════

class TestRetryPath:

    def test_second_render_creates_independent_job(self, client):
        job_id = _make_trailer_job()
        r1 = client.post(f"/editor/{job_id}/render")
        r2 = client.post(f"/editor/{job_id}/render")
        assert r1.status_code == 202
        assert r2.status_code == 202
        id1 = r1.json()["new_job_id"]
        id2 = r2.json()["new_job_id"]
        assert id1 != id2

    def test_both_render_jobs_pollable(self, client):
        job_id = _make_trailer_job()
        id1 = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        id2 = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        assert client.get(f"/trailer-job/{id1}").status_code == 200
        assert client.get(f"/trailer-job/{id2}").status_code == 200

    def test_smart_retry_creates_independent_job(self, client):
        job_id = _make_smart_job()
        id1 = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        id2 = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        assert id1 != id2
        assert client.get(f"/smart-trailer/job/{id1}").status_code == 200
        assert client.get(f"/smart-trailer/job/{id2}").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SSE progress endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestSSEProgressEndpoint:

    def test_sse_endpoint_exists_and_streams(self, client):
        """GET /editor/{job_id}/render/progress must return 200 text/event-stream."""
        job_id  = _make_trailer_job()
        new_id  = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        r = client.get(
            f"/editor/{job_id}/render/progress",
            params={"new_job_id": new_id},
            headers={"Accept": "text/event-stream"},
        )
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")

    def test_sse_endpoint_unknown_source_returns_404(self, client):
        r = client.get(
            f"/editor/{uuid.uuid4()}/render/progress",
            params={"new_job_id": str(uuid.uuid4())},
        )
        assert r.status_code == 404

    def test_sse_payload_contains_required_fields(self, client):
        """First SSE event must contain stage, percent, message, steps."""
        job_id = _make_trailer_job()
        new_id = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        r = client.get(
            f"/editor/{job_id}/render/progress",
            params={"new_job_id": new_id},
        )
        # Read first event line
        first_data = None
        for line in r.text.splitlines():
            if line.startswith("data: "):
                first_data = json.loads(line[6:])
                break
        assert first_data is not None
        for field in ("stage", "percent", "message", "steps"):
            assert field in first_data, f"Missing SSE field: {field}"

    def test_sse_smart_job_source(self, client):
        """SSE endpoint must also work for SmartTrailerJob sources."""
        job_id = _make_smart_job()
        new_id = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        r = client.get(
            f"/editor/{job_id}/render/progress",
            params={"new_job_id": new_id},
        )
        assert r.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Original trailer untouched
# ═══════════════════════════════════════════════════════════════════════════════

class TestOriginalTrailerUntouched:

    def test_source_job_output_path_unchanged_after_render(self, client):
        from app.models.trailer_job import TrailerJob
        job_id = _make_trailer_job()
        db = _TestSession()
        try:
            original_path = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        client.post(f"/editor/{job_id}/render")

        db = _TestSession()
        try:
            after_path = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        assert original_path == after_path, (
            f"Source job output_path was mutated: {original_path!r} → {after_path!r}"
        )

    def test_source_smart_job_output_path_unchanged(self, client):
        from app.models.smart_trailer_job import SmartTrailerJob
        job_id = _make_smart_job()
        db = _TestSession()
        try:
            original_path = db.query(SmartTrailerJob).filter(
                SmartTrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        client.post(f"/editor/{job_id}/render")

        db = _TestSession()
        try:
            after_path = db.query(SmartTrailerJob).filter(
                SmartTrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        assert original_path == after_path

    def test_source_job_editing_plan_unchanged_after_render(self, client):
        """The AI editing_plan on the source job must never be mutated."""
        from app.models.trailer_job import TrailerJob
        job_id = _make_trailer_job()
        db = _TestSession()
        try:
            original_plan = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().editing_plan
        finally:
            db.close()

        # Save a user plan and render
        _save_user_plan(client, job_id, [_AI_CLIPS[0]])
        client.post(f"/editor/{job_id}/render")

        db = _TestSession()
        try:
            after_plan = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().editing_plan
        finally:
            db.close()

        assert original_plan == after_plan, "Source job editing_plan was mutated"

    def test_new_render_job_has_different_id(self, client):
        """Sanity: new job id must be a fresh UUID, not the source id."""
        job_id = _make_trailer_job()
        new_id = client.post(f"/editor/{job_id}/render").json()["new_job_id"]
        # Validate it's a valid UUID
        parsed = uuid.UUID(new_id)
        assert str(parsed) == new_id
        assert new_id != job_id
