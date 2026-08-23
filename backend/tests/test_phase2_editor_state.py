"""
Phase 2 — Canonical Editor State (backend contract tests)

These tests verify that the backend correctly handles the editor state
contract that useEditorState depends on:

1.  PUT /plan strips unknown fields (id) without error
2.  PUT /plan round-trips clip data correctly
3.  GET /editor returns clips with all fields useEditorState expects
4.  RESET (DELETE /plan) returns to AI plan
5.  Clip order is preserved through PUT → GET round-trip
6.  Multiple clips are preserved through PUT → GET round-trip
7.  Muted flag is persisted
8.  Trim values (start_time / end_time) are persisted exactly
9.  planSource transitions: ai → user → ai
10. plan_updated_at is set on PUT and cleared on DELETE

Run from backend/:
    python -m pytest tests/test_phase2_editor_state.py -v
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


# ── Shared in-memory test DB ──────────────────────────────────────────────────

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

_AI_PLAN = {
    "clips": [
        {
            "start_time": 10.0, "end_time": 20.0,
            "reason": "AI selected", "topic": "Intro",
            "sentiment": "Positive", "platform": "youtube",
            "mood_group": "energetic", "transcript_text": "Welcome",
        },
        {
            "start_time": 30.0, "end_time": 45.0,
            "reason": "AI selected", "topic": "Action",
            "sentiment": "Positive", "platform": "youtube",
            "mood_group": "energetic", "transcript_text": "Let's go",
        },
    ],
    "target_duration": 25.0,
    "audio_fade_out": True,
    "output_format": "mp4",
    "rationale": "AI plan",
}


def _make_job() -> str:
    from app.models.smart_trailer_job import SmartTrailerJob
    db = _TestSession()
    try:
        job = SmartTrailerJob(
            id=str(uuid.uuid4()),
            project_id="p2-test",
            dataset_id="d2-test",
            raw_footage_path="/tmp/fake.mp4",
            sample_trailer_path="/tmp/fake_sample.mp4",
            comments_path="/tmp/fake_comments.txt",
            status="done",
            editing_plan=json.dumps(_AI_PLAN),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


# Clip as useEditorState would send it — includes frontend-only `id` field
def _clip_with_id(start: float, end: float, **kwargs) -> dict:
    return {
        "id": f"clip-frontend-{uuid.uuid4().hex[:8]}",   # frontend-only
        "start_time": start,
        "end_time": end,
        "reason": kwargs.get("reason", "user"),
        "topic": kwargs.get("topic", "Test"),
        "sentiment": kwargs.get("sentiment", "Neutral"),
        "platform": kwargs.get("platform", None),
        "mood_group": kwargs.get("mood_group", "calm"),
        "transcript_text": kwargs.get("transcript_text", ""),
        "muted": kwargs.get("muted", False),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — PUT /plan strips unknown fields without error
# ═══════════════════════════════════════════════════════════════════════════════

class TestPutStripsUnknownFields:

    def test_put_with_id_field_returns_200(self, client):
        """Backend must accept clips that include a frontend id field."""
        job_id = _make_job()
        clip = _clip_with_id(5.0, 10.0)
        r = client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        assert r.status_code == 200, r.text

    def test_put_with_id_field_plan_source_becomes_user(self, client):
        job_id = _make_job()
        clip = _clip_with_id(5.0, 10.0)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "user"

    def test_put_id_field_not_stored_in_plan(self, client):
        """The id field must not appear in the stored plan clips."""
        job_id = _make_job()
        clip = _clip_with_id(5.0, 10.0)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        stored_clip = r.json()["plan"]["clips"][0]
        assert "id" not in stored_clip


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Round-trip clip data
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipRoundTrip:

    def test_start_end_times_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(12.5, 27.3)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        stored = r.json()["plan"]["clips"][0]
        assert stored["start_time"] == 12.5
        assert stored["end_time"] == 27.3

    def test_topic_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0, topic="My Topic")
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["topic"] == "My Topic"

    def test_sentiment_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0, sentiment="Negative")
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["sentiment"] == "Negative"

    def test_muted_true_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0, muted=True)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["muted"] is True

    def test_muted_false_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0, muted=False)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["muted"] is False

    def test_transcript_text_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0, transcript_text="Hello world")
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["transcript_text"] == "Hello world"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Clip order preserved
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipOrder:

    def test_two_clips_order_preserved(self, client):
        job_id = _make_job()
        clips = [
            _clip_with_id(50.0, 60.0, topic="Second"),
            _clip_with_id(10.0, 20.0, topic="First"),
        ]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        r = client.get(f"/editor/{job_id}")
        stored = r.json()["plan"]["clips"]
        assert stored[0]["topic"] == "Second"
        assert stored[1]["topic"] == "First"

    def test_three_clips_order_preserved(self, client):
        job_id = _make_job()
        clips = [
            _clip_with_id(30.0, 40.0, topic="C"),
            _clip_with_id(10.0, 20.0, topic="A"),
            _clip_with_id(50.0, 60.0, topic="B"),
        ]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        r = client.get(f"/editor/{job_id}")
        stored = r.json()["plan"]["clips"]
        assert [c["topic"] for c in stored] == ["C", "A", "B"]

    def test_clip_count_preserved(self, client):
        job_id = _make_job()
        clips = [_clip_with_id(float(i * 10), float(i * 10 + 5)) for i in range(5)]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        r = client.get(f"/editor/{job_id}")
        assert len(r.json()["plan"]["clips"]) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — planSource transitions
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlanSourceTransitions:

    def test_initial_source_is_ai(self, client):
        job_id = _make_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_after_put_source_is_user(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip_with_id(0.0, 5.0)]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "user"

    def test_after_delete_source_is_ai(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip_with_id(0.0, 5.0)]})
        client.delete(f"/editor/{job_id}/plan")
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_plan_updated_at_set_on_put(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip_with_id(0.0, 5.0)]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_updated_at"] is not None

    def test_plan_updated_at_cleared_on_delete(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip_with_id(0.0, 5.0)]})
        client.delete(f"/editor/{job_id}/plan")
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_updated_at"] is None

    def test_reset_restores_ai_clips(self, client):
        """After DELETE, GET returns the original AI plan clips."""
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip_with_id(99.0, 100.0, topic="User clip")]})
        client.delete(f"/editor/{job_id}/plan")
        r = client.get(f"/editor/{job_id}")
        clips = r.json()["plan"]["clips"]
        # AI plan has 2 clips starting at 10.0 and 30.0
        assert len(clips) == 2
        assert clips[0]["start_time"] == 10.0
        assert clips[1]["start_time"] == 30.0


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Trim precision
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrimPrecision:

    def test_fractional_trim_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(12.345, 27.891)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        stored = r.json()["plan"]["clips"][0]
        assert abs(stored["start_time"] - 12.345) < 0.001
        assert abs(stored["end_time"] - 27.891) < 0.001

    def test_zero_start_preserved(self, client):
        job_id = _make_job()
        clip = _clip_with_id(0.0, 5.0)
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["start_time"] == 0.0
