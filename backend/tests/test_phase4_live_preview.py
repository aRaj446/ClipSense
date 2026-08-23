"""
Phase 4 — Live Preview Backend Contract

The live preview in VideoPreview.tsx depends on:
  1. GET /editor/{job_id}/raw-video  — serves the source file
  2. GET /editor/{job_id}            — returns raw_footage_url when available
  3. PUT /editor/{job_id}/plan       — edits are persisted and immediately readable
  4. Clip data integrity through rapid successive edits

These tests verify the backend side of the live preview contract.
The frontend segment-playback logic is tested manually (browser).

Run from backend/:
    python -m pytest tests/test_phase4_live_preview.py -v
"""

import json
import uuid
import os
import tempfile
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
    try:
        os.unlink(_db_file.name)
    except OSError:
        pass


@pytest.fixture(scope="module")
def client():
    return TestClient(fastapi_app, raise_server_exceptions=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

_PLAN_3_CLIPS = {
    "clips": [
        {"start_time": 10.0, "end_time": 20.0, "reason": "r", "topic": "A",
         "sentiment": "Positive", "platform": None, "mood_group": "calm",
         "transcript_text": "clip A"},
        {"start_time": 35.0, "end_time": 42.0, "reason": "r", "topic": "B",
         "sentiment": "Neutral",  "platform": None, "mood_group": "calm",
         "transcript_text": "clip B"},
        {"start_time": 71.0, "end_time": 80.0, "reason": "r", "topic": "C",
         "sentiment": "Negative", "platform": None, "mood_group": "calm",
         "transcript_text": "clip C"},
    ],
    "target_duration": 26.0,
    "audio_fade_out": True,
    "output_format": "mp4",
    "rationale": "test plan",
}


def _make_job(footage_path: str = "/nonexistent/video.mp4") -> str:
    """Insert a SmartTrailerJob and return its id. Captures id before session close."""
    from app.models.smart_trailer_job import SmartTrailerJob
    job_id = str(uuid.uuid4())
    db = _TestSession()
    try:
        db.add(SmartTrailerJob(
            id=job_id,
            project_id="p4-test",
            dataset_id="d4-test",
            raw_footage_path=footage_path,
            sample_trailer_path="/tmp/fake_sample.mp4",
            comments_path="/tmp/fake_comments.txt",
            status="done",
            editing_plan=json.dumps(_PLAN_3_CLIPS),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ))
        db.commit()
    finally:
        db.close()
    return job_id


def _clip(start: float, end: float, topic: str = "T") -> dict:
    return {
        "start_time": start, "end_time": end,
        "reason": "r", "topic": topic,
        "sentiment": "Neutral", "platform": None,
        "mood_group": "calm", "transcript_text": "",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — raw_footage_url in editor response
# ═══════════════════════════════════════════════════════════════════════════════

class TestRawFootageUrl:

    def test_raw_footage_url_present_when_file_exists(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake video data")
            path = f.name
        try:
            job_id = _make_job(path)
            r = client.get(f"/editor/{job_id}")
            assert r.status_code == 200
            assert r.json()["raw_footage_url"] == f"/editor/{job_id}/raw-video"
        finally:
            os.unlink(path)

    def test_raw_footage_url_null_when_file_missing(self, client):
        job_id = _make_job("/nonexistent/path/video.mp4")
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 200
        assert r.json()["raw_footage_url"] is None

    def test_raw_footage_url_format(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"x")
            path = f.name
        try:
            job_id = _make_job(path)
            r = client.get(f"/editor/{job_id}")
            url = r.json()["raw_footage_url"]
            assert url.startswith("/editor/")
            assert url.endswith("/raw-video")
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — GET /editor/{job_id}/raw-video
# ═══════════════════════════════════════════════════════════════════════════════

class TestRawVideoEndpoint:

    def test_raw_video_returns_200_when_file_exists(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake mp4 content for testing")
            path = f.name
        try:
            job_id = _make_job(path)
            r = client.get(f"/editor/{job_id}/raw-video")
            assert r.status_code == 200
        finally:
            os.unlink(path)

    def test_raw_video_returns_404_when_file_missing(self, client):
        job_id = _make_job("/nonexistent/path/video.mp4")
        r = client.get(f"/editor/{job_id}/raw-video")
        assert r.status_code == 404

    def test_raw_video_unknown_job_returns_404(self, client):
        r = client.get(f"/editor/{uuid.uuid4()}/raw-video")
        assert r.status_code == 404

    def test_raw_video_content_type_video(self, client):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"fake mp4")
            path = f.name
        try:
            job_id = _make_job(path)
            r = client.get(f"/editor/{job_id}/raw-video")
            assert "video" in r.headers.get("content-type", "")
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Clip data integrity for live preview
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipDataIntegrity:

    def test_three_clip_plan_round_trips(self, client):
        job_id = _make_job()
        clips = [_clip(10.0, 20.0, "A"), _clip(35.0, 42.0, "B"), _clip(71.0, 80.0, "C")]
        r = client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        assert r.status_code == 200
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        assert len(stored) == 3
        assert stored[0]["start_time"] == 10.0 and stored[0]["end_time"] == 20.0
        assert stored[1]["start_time"] == 35.0 and stored[1]["end_time"] == 42.0
        assert stored[2]["start_time"] == 71.0 and stored[2]["end_time"] == 80.0

    def test_reorder_persisted_correctly(self, client):
        job_id = _make_job()
        clips = [_clip(71.0, 80.0, "C"), _clip(10.0, 20.0, "A"), _clip(35.0, 42.0, "B")]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        assert stored[0]["topic"] == "C"
        assert stored[1]["topic"] == "A"
        assert stored[2]["topic"] == "B"

    def test_delete_clip_persisted(self, client):
        job_id = _make_job()
        clips = [_clip(10.0, 20.0, "A"), _clip(71.0, 80.0, "C")]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        assert len(stored) == 2
        assert stored[0]["topic"] == "A"
        assert stored[1]["topic"] == "C"

    def test_trim_persisted_exactly(self, client):
        job_id = _make_job()
        clips = [_clip(12.5, 18.3, "A"), _clip(35.0, 42.0, "B")]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"][0]
        assert abs(stored["start_time"] - 12.5) < 0.001
        assert abs(stored["end_time"]   - 18.3) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Rapid successive edits
# ═══════════════════════════════════════════════════════════════════════════════

class TestRapidEdits:

    def test_five_rapid_puts_last_wins(self, client):
        job_id = _make_job()
        for i in range(5):
            r = client.put(f"/editor/{job_id}/plan",
                           json={"clips": [_clip(float(i * 10), float(i * 10 + 5), f"clip-{i}")]})
            assert r.status_code == 200
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        assert len(stored) == 1
        assert stored[0]["topic"] == "clip-4"
        assert stored[0]["start_time"] == 40.0

    def test_add_then_delete_then_add(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [
            _clip(10.0, 20.0, "A"), _clip(35.0, 42.0, "B"), _clip(71.0, 80.0, "C"),
        ]})
        client.put(f"/editor/{job_id}/plan", json={"clips": [
            _clip(10.0, 20.0, "A"), _clip(71.0, 80.0, "C"),
        ]})
        client.put(f"/editor/{job_id}/plan", json={"clips": [
            _clip(10.0, 20.0, "A"), _clip(71.0, 80.0, "C"), _clip(50.0, 55.0, "D"),
        ]})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        assert len(stored) == 3
        assert stored[2]["topic"] == "D"

    def test_trim_then_retrim(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip(10.0, 20.0, "A")]})
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip(12.0, 18.0, "A")]})
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip(13.5, 17.2, "A")]})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"][0]
        assert abs(stored["start_time"] - 13.5) < 0.001
        assert abs(stored["end_time"]   - 17.2) < 0.001


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Assembled duration calculation
# ═══════════════════════════════════════════════════════════════════════════════

class TestAssembledDuration:

    def test_assembled_duration_from_three_clips(self, client):
        """A:10s + B:7s + C:9s = 26s"""
        job_id = _make_job()
        clips = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        total = sum(c["end_time"] - c["start_time"] for c in clips)
        assert abs(total - 26.0) < 0.001

    def test_assembled_duration_after_trim(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan",
                   json={"clips": [_clip(10.0, 15.0, "A"), _clip(35.0, 42.0, "B")]})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        total = sum(c["end_time"] - c["start_time"] for c in stored)
        assert abs(total - 12.0) < 0.001

    def test_assembled_duration_single_clip(self, client):
        job_id = _make_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_clip(20.0, 35.0, "X")]})
        stored = client.get(f"/editor/{job_id}").json()["plan"]["clips"]
        total = sum(c["end_time"] - c["start_time"] for c in stored)
        assert abs(total - 15.0) < 0.001
