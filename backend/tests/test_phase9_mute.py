"""
Phase 9 (Per-clip mute) — Backend Tests

Covers:
    1.  TrailerClip schema — muted defaults to False
    2.  TrailerClip schema — muted=True round-trips through model_dump_json
    3.  ClipUpdate schema — muted defaults to False
    4.  ClipUpdate schema — muted=True accepted
    5.  PlannedClip dataclass — muted defaults to False
    6.  PlannedClip dataclass — muted=True preserved
    7.  process_clips — muted=False forwarded to PlannedClip
    8.  process_clips — muted=True forwarded to PlannedClip
    9.  PUT /editor/{job_id}/plan — muted=True persisted in plan_json
    10. PUT /editor/{job_id}/plan — muted=False persisted in plan_json
    11. GET /editor/{job_id} — muted field present in returned plan clips
    12. GET /editor/{job_id} — muted defaults to False for AI plan clips
    13. POST /editor/{job_id}/render — muted clip accepted, 202 returned
    14. POST /editor/{job_id}/render — all-muted plan accepted, 202 returned
    15. FFmpeg audio filter — muted clip uses anullsrc (silence)
    16. FFmpeg audio filter — unmuted clip uses loudnorm
    17. Original trailer untouched after muted render
    18. Muted field survives PUT → GET round-trip (standard job)
    19. Muted field survives PUT → GET round-trip (smart job)
    20. Mixed muted/unmuted plan — render returns 202

Run from backend/:
    python -m pytest tests/test_phase9_mute.py -v
"""

import json
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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

_BASE_CLIP = {
    "start_time": 0.0, "end_time": 5.0,
    "reason": "test", "topic": "Action",
    "sentiment": "Positive", "platform": "youtube",
    "mood_group": "energetic", "transcript_text": "hello",
}

_AI_PLAN = {
    "clips": [_BASE_CLIP],
    "target_duration": 5.0,
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
            project_id="test-p9",
            dataset_id="test-ds-p9",
            status=status,
            editing_plan=json.dumps(plan or _AI_PLAN),
            output_path="/tmp/fake_original.mp4",
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
            project_id="test-p9",
            dataset_id="test-ds-p9",
            raw_footage_path="/tmp/fake_raw.mp4",
            sample_trailer_path="/tmp/fake_sample.mp4",
            comments_path="/tmp/fake_comments.txt",
            status=status,
            editing_plan=json.dumps(plan or _AI_PLAN),
            output_path="/tmp/fake_original_smart.mp4",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# 1–2. TrailerClip schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrailerClipSchema:

    def test_muted_defaults_false(self):
        from app.schemas.feedback import TrailerClip
        clip = TrailerClip(
            start_time=0.0, end_time=5.0,
            reason="r", topic="t", sentiment="Positive",
        )
        assert clip.muted is False

    def test_muted_true_round_trips(self):
        from app.schemas.feedback import TrailerClip
        clip = TrailerClip(
            start_time=0.0, end_time=5.0,
            reason="r", topic="t", sentiment="Positive",
            muted=True,
        )
        data = json.loads(clip.model_dump_json())
        assert data["muted"] is True

    def test_muted_false_round_trips(self):
        from app.schemas.feedback import TrailerClip
        clip = TrailerClip(
            start_time=0.0, end_time=5.0,
            reason="r", topic="t", sentiment="Positive",
            muted=False,
        )
        data = json.loads(clip.model_dump_json())
        assert data["muted"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3–4. ClipUpdate schema
# ═══════════════════════════════════════════════════════════════════════════════

class TestClipUpdateSchema:

    def test_muted_defaults_false(self):
        from app.api.trailer_editor import ClipUpdate
        cu = ClipUpdate(start_time=0.0, end_time=5.0)
        assert cu.muted is False

    def test_muted_true_accepted(self):
        from app.api.trailer_editor import ClipUpdate
        cu = ClipUpdate(start_time=0.0, end_time=5.0, muted=True)
        assert cu.muted is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5–6. PlannedClip dataclass
# ═══════════════════════════════════════════════════════════════════════════════

class TestPlannedClipDataclass:

    def test_muted_defaults_false(self):
        from app.utils.clip_planner import PlannedClip
        pc = PlannedClip(start_time=0.0, end_time=5.0, reason="r", topic="t", sentiment="P")
        assert pc.muted is False

    def test_muted_true_preserved(self):
        from app.utils.clip_planner import PlannedClip
        pc = PlannedClip(start_time=0.0, end_time=5.0, reason="r", topic="t", sentiment="P", muted=True)
        assert pc.muted is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7–8. process_clips forwards muted
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessClipsMuted:

    def _run(self, muted: bool):
        from app.utils.clip_planner import process_clips
        raw = [{
            "start_time": 0.0, "end_time": 10.0,
            "reason": "r", "topic": "t", "sentiment": "Positive",
            "platform": None, "mood_group": "calm",
            "transcript_text": "", "muted": muted,
        }]
        # Patch classify_clips_by_mood to avoid librosa dependency in tests
        with patch("app.utils.clip_planner.classify_clips_by_mood", side_effect=lambda clips, _: clips):
            result = process_clips(
                raw_clips=raw,
                transcript={"segments": []},
                video_duration=60.0,
                video_path="/tmp/fake.mp4",
                target_duration=float("inf"),
            )
        return result

    def test_muted_false_forwarded(self):
        result = self._run(False)
        assert len(result) == 1
        assert result[0].muted is False

    def test_muted_true_forwarded(self):
        result = self._run(True)
        assert len(result) == 1
        assert result[0].muted is True


# ═══════════════════════════════════════════════════════════════════════════════
# 9–12. Editor API — muted in plan persistence and retrieval
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorMutedPersistence:

    def test_put_muted_true_persisted(self, client):
        job_id = _make_trailer_job()
        clip = {**_BASE_CLIP, "muted": True}
        r = client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        assert r.status_code == 200
        returned_clip = r.json()["plan"]["clips"][0]
        assert returned_clip["muted"] is True

    def test_put_muted_false_persisted(self, client):
        job_id = _make_trailer_job()
        clip = {**_BASE_CLIP, "muted": False}
        r = client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        assert r.status_code == 200
        returned_clip = r.json()["plan"]["clips"][0]
        assert returned_clip["muted"] is False

    def test_get_muted_field_present_in_plan(self, client):
        """GET /editor/{job_id} must include muted in each clip."""
        job_id = _make_trailer_job()
        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 200
        plan_clip = r.json()["plan"]["clips"][0]
        assert "muted" in plan_clip
        assert plan_clip["muted"] is True

    def test_get_ai_plan_muted_defaults_false(self, client):
        """AI plan clips without muted field should be treated as muted=False."""
        # AI plan stored without muted field (legacy format)
        ai_plan = {
            "clips": [_BASE_CLIP],   # no muted key
            "target_duration": 5.0,
            "audio_fade_out": True,
            "output_format": "mp4",
            "rationale": "AI plan",
        }
        job_id = _make_trailer_job(plan=ai_plan)
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 200
        # The AI plan clip may or may not have muted — if present it must be False
        plan_clip = r.json()["plan"]["clips"][0]
        assert plan_clip.get("muted", False) is False

    def test_muted_round_trip_standard_job(self, client):
        job_id = _make_trailer_job()
        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["muted"] is True

    def test_muted_round_trip_smart_job(self, client):
        job_id = _make_smart_job()
        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"]["clips"][0]["muted"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 13–14. Render accepts muted plans
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderWithMutedClips:

    def test_render_muted_clip_returns_202(self, client):
        job_id = _make_trailer_job()
        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_all_muted_plan_returns_202(self, client):
        """A plan where every clip is muted must still be accepted."""
        job_id = _make_trailer_job()
        clips = [
            {**_BASE_CLIP, "muted": True},
            {**_BASE_CLIP, "start_time": 10.0, "end_time": 15.0, "muted": True},
        ]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_mixed_muted_plan_returns_202(self, client):
        job_id = _make_trailer_job()
        clips = [
            {**_BASE_CLIP, "muted": True},
            {**_BASE_CLIP, "start_time": 10.0, "end_time": 15.0, "muted": False},
        ]
        client.put(f"/editor/{job_id}/plan", json={"clips": clips})
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_render_muted_smart_job_returns_202(self, client):
        job_id = _make_smart_job()
        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text


# ═══════════════════════════════════════════════════════════════════════════════
# 15–16. FFmpeg audio filter selection
# ═══════════════════════════════════════════════════════════════════════════════

class TestFFmpegAudioFilter:
    """
    Verify that compose() builds the correct FFmpeg command for muted vs unmuted clips.
    We patch subprocess.run to capture the command without executing FFmpeg.
    """

    def _run_compose_capture_cmds(self, muted: bool) -> list[list[str]]:
        """Run compose() with a single clip and return all captured FFmpeg commands."""
        from app.utils.clip_planner import PlannedClip
        from app.utils.ffmpeg_composer import compose

        clip = PlannedClip(
            start_time=0.0, end_time=5.0,
            reason="r", topic="t", sentiment="Positive",
            muted=muted,
        )

        captured: list[list[str]] = []

        def fake_run(cmd, **kwargs):
            captured.append(list(cmd))
            m = MagicMock()
            m.returncode = 0
            m.stderr = ""
            m.stdout = ""
            return m

        with patch("app.utils.ffmpeg_composer.subprocess.run", side_effect=fake_run), \
             patch("app.utils.ffmpeg_composer._resolve_encoder", return_value="libx264"), \
             patch("app.utils.device.encoder_options", return_value=["-preset", "fast"]), \
             patch("app.utils.ffmpeg_composer._probe_duration", return_value=5.0), \
             patch("app.utils.ffmpeg_composer._stitch_clips",
                   return_value=(True, "", [0.0], [5.0])), \
             patch("app.utils.ffmpeg_composer._loudnorm_pass1", return_value=""), \
             patch("app.utils.ffmpeg_composer._build_loudnorm_filter",
                   return_value="loudnorm=I=-14:LRA=11:TP=-1:linear=true"):
            compose(
                clips=[clip],
                input_path="/tmp/fake.mp4",
                output_path="/tmp/out.mp4",
                transcript={"segments": []},
                audio_fade_out=False,
                job_id=None,
            )

        return captured

    def test_muted_clip_uses_anullsrc(self):
        """The per-clip extraction command for a muted clip must include anullsrc."""
        cmds = self._run_compose_capture_cmds(muted=True)
        # First command is the per-clip extraction
        extraction_cmd = " ".join(cmds[0]) if cmds else ""
        assert "anullsrc" in extraction_cmd, (
            f"Expected anullsrc in muted clip command, got: {extraction_cmd}"
        )

    def test_muted_clip_does_not_use_loudnorm_on_audio(self):
        """Muted clip extraction must NOT apply loudnorm to the audio."""
        cmds = self._run_compose_capture_cmds(muted=True)
        extraction_cmd = " ".join(cmds[0]) if cmds else ""
        # loudnorm should not appear in the per-clip -af filter for muted clips
        # (it may appear in the final pass command, not the extraction)
        af_idx = cmds[0].index("-af") if "-af" in cmds[0] else -1
        if af_idx >= 0:
            af_value = cmds[0][af_idx + 1]
            assert "loudnorm" not in af_value, (
                f"Muted clip should not use loudnorm in -af, got: {af_value}"
            )

    def test_unmuted_clip_uses_loudnorm(self):
        """The per-clip extraction command for an unmuted clip must use loudnorm."""
        cmds = self._run_compose_capture_cmds(muted=False)
        extraction_cmd = " ".join(cmds[0]) if cmds else ""
        assert "loudnorm" in extraction_cmd, (
            f"Expected loudnorm in unmuted clip command, got: {extraction_cmd}"
        )

    def test_unmuted_clip_does_not_use_anullsrc(self):
        """Unmuted clip must not use anullsrc."""
        cmds = self._run_compose_capture_cmds(muted=False)
        extraction_cmd = " ".join(cmds[0]) if cmds else ""
        assert "anullsrc" not in extraction_cmd, (
            f"Unmuted clip must not use anullsrc, got: {extraction_cmd}"
        )

    def test_muted_clip_maps_lavfi_input(self):
        """Muted clip FFmpeg command must include -f lavfi to inject the silent source."""
        cmds = self._run_compose_capture_cmds(muted=True)
        extraction_cmd = " ".join(cmds[0]) if cmds else ""
        assert "lavfi" in extraction_cmd, (
            f"Expected -f lavfi in muted clip command, got: {extraction_cmd}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 17. Original trailer untouched
# ═══════════════════════════════════════════════════════════════════════════════

class TestOriginalUntouched:

    def test_source_output_path_unchanged_after_muted_render(self, client):
        from app.models.trailer_job import TrailerJob
        job_id = _make_trailer_job()

        db = _TestSession()
        try:
            original_path = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        client.post(f"/editor/{job_id}/render")

        db = _TestSession()
        try:
            after_path = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().output_path
        finally:
            db.close()

        assert original_path == after_path

    def test_source_editing_plan_unchanged_after_muted_render(self, client):
        from app.models.trailer_job import TrailerJob
        job_id = _make_trailer_job()

        db = _TestSession()
        try:
            original_plan = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().editing_plan
        finally:
            db.close()

        clip = {**_BASE_CLIP, "muted": True}
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip]})
        client.post(f"/editor/{job_id}/render")

        db = _TestSession()
        try:
            after_plan = db.query(TrailerJob).filter(
                TrailerJob.id == job_id
            ).first().editing_plan
        finally:
            db.close()

        assert original_plan == after_plan
