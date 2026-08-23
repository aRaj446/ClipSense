"""
Phase 1 (SenseScrub backend prep) — Focused Tests

Covers:
    1.  CORS — SenseScrub origin (5174) accepted
    2.  CORS — ClipSense origin (5173) still accepted
    3.  CORS — unknown origin not reflected
    4.  Static-file CORS middleware — /trailers/ path with known origin
    5.  Static-file CORS middleware — /uploads/ path with known origin
    6.  SmartTrailerEdit model — table created, row insert/read/delete
    7.  Editor GET — TrailerJob 404 still works
    8.  Editor GET — SmartTrailerJob 404 works
    9.  Editor GET — pending TrailerJob returns 409 (unchanged)
    10. Editor GET — pending SmartTrailerJob returns 409
    11. Editor GET — done TrailerJob returns plan_source=ai, job_type=standard
    12. Editor GET — done SmartTrailerJob returns plan_source=ai, job_type=smart
    13. Editor PUT — TrailerJob saves user plan, plan_source=user (unchanged)
    14. Editor PUT — SmartTrailerJob saves user plan, plan_source=user
    15. Editor PUT — empty clips rejected 400 (both job types)
    16. Editor DELETE — TrailerJob reverts to ai plan (unchanged)
    17. Editor DELETE — SmartTrailerJob reverts to ai plan
    18. Editor DELETE — unknown job returns 404
    19. Editor POST /render — TrailerJob returns 202 + new_job_id, job_type=standard
    20. Editor POST /render — SmartTrailerJob returns 202 + new_job_id, job_type=smart
    21. Editor POST /render — new SmartTrailerJob is pollable via /smart-trailer/job/{id}
    22. Regression — existing TrailerJob editor response shape unchanged
    23. Database migration — smart_trailer_edits table exists in live DB
    24. Editor GET /scenes — TrailerJob and SmartTrailerJob return AI clips

Run from backend/:
    python -m pytest tests/test_phase1_sensescrub_backend.py -v
"""

import json
import uuid
import tempfile
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
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
    import os
    try:
        os.unlink(_db_file.name)
    except OSError:
        pass


@pytest.fixture(scope="module")
def client():
    return TestClient(fastapi_app, raise_server_exceptions=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

_SAMPLE_PLAN = {
    "clips": [
        {
            "start_time": 0.0, "end_time": 5.0,
            "reason": "test", "topic": "Action",
            "sentiment": "Positive", "platform": "youtube",
            "mood_group": "energetic", "transcript_text": "hello",
        }
    ],
    "target_duration": 5.0,
    "audio_fade_out": True,
    "output_format": "mp4",
    "rationale": "AI plan",
}


def _make_trailer_job(status: str = "done") -> str:
    """Insert a TrailerJob row directly and return its id."""
    from app.models.trailer_job import TrailerJob
    db = _TestSession()
    try:
        job = TrailerJob(
            id=str(uuid.uuid4()),
            project_id="test-project",
            dataset_id="test-dataset",
            status=status,
            editing_plan=json.dumps(_SAMPLE_PLAN),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _make_smart_job(status: str = "done") -> str:
    """Insert a SmartTrailerJob row directly and return its id."""
    from app.models.smart_trailer_job import SmartTrailerJob
    db = _TestSession()
    try:
        job = SmartTrailerJob(
            id=str(uuid.uuid4()),
            project_id="test-project",
            dataset_id="test-dataset",
            raw_footage_path="/tmp/fake_raw.mp4",
            sample_trailer_path="/tmp/fake_sample.mp4",
            comments_path="/tmp/fake_comments.txt",
            status=status,
            editing_plan=json.dumps(_SAMPLE_PLAN),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — CORS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCORS:

    def test_sensescrub_origin_accepted(self, client):
        r = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:5174"

    def test_clipsense_origin_still_accepted(self, client):
        r = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:5173"

    def test_unknown_origin_not_reflected(self, client):
        r = client.options(
            "/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao != "http://evil.example.com"

    def test_static_trailers_cors_known_origin(self, client):
        r = client.get(
            "/trailers/nonexistent.mp4",
            headers={"Origin": "http://localhost:5174"},
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:5174"

    def test_static_uploads_cors_known_origin(self, client):
        r = client.get(
            "/uploads/nonexistent.mp4",
            headers={"Origin": "http://localhost:5174"},
        )
        acao = r.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:5174"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — SmartTrailerEdit model
# ═══════════════════════════════════════════════════════════════════════════════

class TestSmartTrailerEditModel:

    def test_table_exists_in_test_db(self):
        tables = inspect(_engine).get_table_names()
        assert "smart_trailer_edits" in tables

    def test_insert_and_read(self):
        from app.models.smart_trailer_edit import SmartTrailerEdit
        db = _TestSession()
        try:
            job_id = str(uuid.uuid4())
            row = SmartTrailerEdit(
                job_id=job_id,
                plan_json=json.dumps({"clips": []}),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
            fetched = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
            assert fetched is not None
            assert fetched.job_id == job_id
        finally:
            db.close()

    def test_delete(self):
        from app.models.smart_trailer_edit import SmartTrailerEdit
        db = _TestSession()
        try:
            job_id = str(uuid.uuid4())
            row = SmartTrailerEdit(
                job_id=job_id,
                plan_json=json.dumps({"clips": []}),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
            db.delete(row)
            db.commit()
            assert db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first() is None
        finally:
            db.close()

    def test_no_fk_constraint_on_job_id(self):
        from app.models.smart_trailer_edit import SmartTrailerEdit
        db = _TestSession()
        try:
            row = SmartTrailerEdit(
                job_id="nonexistent-job-id-fk-test",
                plan_json=json.dumps({"clips": []}),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.commit()
            db.delete(row)
            db.commit()
        finally:
            db.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Editor GET
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorGet:

    def test_unknown_job_returns_404(self, client):
        r = client.get("/editor/nonexistent-job-id")
        assert r.status_code == 404

    def test_unknown_smart_job_returns_404(self, client):
        r = client.get(f"/editor/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_pending_trailer_job_returns_409(self, client):
        job_id = _make_trailer_job(status="pending")
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 409

    def test_pending_smart_job_returns_409(self, client):
        job_id = _make_smart_job(status="pending")
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 409

    def test_done_trailer_job_returns_200(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 200, r.text

    def test_done_trailer_job_plan_source_ai(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_done_trailer_job_job_type_standard(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["job_type"] == "standard"

    def test_done_smart_job_returns_200(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}")
        assert r.status_code == 200, r.text

    def test_done_smart_job_plan_source_ai(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_done_smart_job_job_type_smart(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["job_type"] == "smart"

    def test_done_smart_job_response_shape(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}")
        body = r.json()
        for field in ("job_id", "project_id", "status", "plan", "plan_source",
                      "plan_updated_at", "job_type"):
            assert field in body, f"Missing field: {field}"

    def test_done_smart_job_plan_not_none(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Editor PUT
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorPut:

    def test_trailer_job_put_saves_plan(self, client):
        job_id = _make_trailer_job()
        r = client.put(f"/editor/{job_id}/plan", json={
            "clips": [_SAMPLE_PLAN["clips"][0]],
            "rationale": "User edit",
        })
        assert r.status_code == 200, r.text

    def test_trailer_job_put_changes_source_to_user(self, client):
        job_id = _make_trailer_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "user"

    def test_smart_job_put_saves_plan(self, client):
        job_id = _make_smart_job()
        r = client.put(f"/editor/{job_id}/plan", json={
            "clips": [_SAMPLE_PLAN["clips"][0]],
            "rationale": "Smart user edit",
        })
        assert r.status_code == 200, r.text

    def test_smart_job_put_changes_source_to_user(self, client):
        job_id = _make_smart_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "user"

    def test_smart_job_put_plan_updated_at_set(self, client):
        job_id = _make_smart_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_updated_at"] is not None

    def test_smart_job_put_job_type_still_smart(self, client):
        job_id = _make_smart_job()
        r = client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        assert r.json()["job_type"] == "smart"

    def test_empty_clips_rejected_trailer_job(self, client):
        job_id = _make_trailer_job()
        r = client.put(f"/editor/{job_id}/plan", json={"clips": []})
        assert r.status_code == 400

    def test_empty_clips_rejected_smart_job(self, client):
        job_id = _make_smart_job()
        r = client.put(f"/editor/{job_id}/plan", json={"clips": []})
        assert r.status_code == 400

    def test_put_unknown_job_returns_404(self, client):
        r = client.put(f"/editor/{uuid.uuid4()}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        assert r.status_code == 404

    def test_smart_job_put_idempotent(self, client):
        job_id = _make_smart_job()
        clip = _SAMPLE_PLAN["clips"][0]
        client.put(f"/editor/{job_id}/plan", json={"clips": [clip], "rationale": "first"})
        r = client.put(f"/editor/{job_id}/plan", json={"clips": [clip], "rationale": "second"})
        assert r.status_code == 200
        assert r.json()["plan"]["rationale"] == "second"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Editor DELETE
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorDelete:

    def test_trailer_job_delete_reverts_to_ai(self, client):
        job_id = _make_trailer_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r_del = client.delete(f"/editor/{job_id}/plan")
        assert r_del.status_code == 204
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"
        assert r.json()["plan_updated_at"] is None

    def test_smart_job_delete_reverts_to_ai(self, client):
        job_id = _make_smart_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r_del = client.delete(f"/editor/{job_id}/plan")
        assert r_del.status_code == 204
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"
        assert r.json()["plan_updated_at"] is None

    def test_delete_no_edit_is_idempotent(self, client):
        job_id = _make_smart_job()
        r = client.delete(f"/editor/{job_id}/plan")
        assert r.status_code == 204

    def test_delete_unknown_job_returns_404(self, client):
        r = client.delete(f"/editor/{uuid.uuid4()}/plan")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Editor POST /render
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorRender:

    def test_trailer_job_render_returns_202(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_trailer_job_render_returns_new_job_id(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        body = r.json()
        assert "new_job_id" in body
        assert body["new_job_id"] != job_id

    def test_trailer_job_render_job_type_standard(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.json()["job_type"] == "standard"

    def test_trailer_job_render_new_job_pollable(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/trailer-job/{new_id}")
        assert r2.status_code == 200
        assert r2.json()["status"] in ("pending", "processing", "done", "failed")

    def test_smart_job_render_returns_202(self, client):
        job_id = _make_smart_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202, r.text

    def test_smart_job_render_returns_new_job_id(self, client):
        job_id = _make_smart_job()
        r = client.post(f"/editor/{job_id}/render")
        body = r.json()
        assert "new_job_id" in body
        assert body["new_job_id"] != job_id

    def test_smart_job_render_job_type_smart(self, client):
        job_id = _make_smart_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.json()["job_type"] == "smart"

    def test_smart_job_render_new_job_pollable_via_smart_endpoint(self, client):
        job_id = _make_smart_job()
        r = client.post(f"/editor/{job_id}/render")
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/smart-trailer/job/{new_id}")
        assert r2.status_code == 200
        assert r2.json()["status"] in ("pending", "processing", "done", "failed")

    def test_render_unknown_job_returns_404(self, client):
        r = client.post(f"/editor/{uuid.uuid4()}/render")
        assert r.status_code == 404

    def test_render_pending_job_returns_409(self, client):
        job_id = _make_trailer_job(status="pending")
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 409

    def test_smart_render_pending_job_returns_409(self, client):
        job_id = _make_smart_job(status="pending")
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 409


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7 — Regression: existing TrailerJob editor response shape unchanged
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrailerJobEditorRegression:

    def test_response_has_all_original_fields(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}")
        body = r.json()
        for field in ("job_id", "project_id", "status", "output_url", "platform",
                      "clip_score", "plan", "plan_source", "plan_updated_at",
                      "created_at", "updated_at"):
            assert field in body, f"Missing original field: {field}"

    def test_plan_source_ai_before_edit(self, client):
        job_id = _make_trailer_job()
        client.delete(f"/editor/{job_id}/plan")
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_put_then_get_source_is_user(self, client):
        job_id = _make_trailer_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "user"

    def test_delete_then_get_source_is_ai(self, client):
        job_id = _make_trailer_job()
        client.put(f"/editor/{job_id}/plan", json={"clips": [_SAMPLE_PLAN["clips"][0]]})
        client.delete(f"/editor/{job_id}/plan")
        r = client.get(f"/editor/{job_id}")
        assert r.json()["plan_source"] == "ai"
        assert r.json()["plan_updated_at"] is None

    def test_render_creates_independent_new_job(self, client):
        job_id = _make_trailer_job()
        r = client.post(f"/editor/{job_id}/render")
        assert r.status_code == 202
        new_id = r.json()["new_job_id"]
        assert new_id != job_id
        r_orig = client.get(f"/editor/{job_id}")
        assert r_orig.status_code == 200
        assert r_orig.json()["job_id"] == job_id


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8 — Live DB migration check
# ═══════════════════════════════════════════════════════════════════════════════

class TestLiveDBMigration:

    def test_smart_trailer_edits_table_in_live_db(self):
        from sqlalchemy import create_engine as _ce, inspect as _inspect
        live_engine = _ce("sqlite:///./app/clipsense.db",
                          connect_args={"check_same_thread": False})
        tables = _inspect(live_engine).get_table_names()
        live_engine.dispose()
        assert "smart_trailer_edits" in tables

    def test_trailer_edits_table_still_intact(self):
        from sqlalchemy import create_engine as _ce, inspect as _inspect
        live_engine = _ce("sqlite:///./app/clipsense.db",
                          connect_args={"check_same_thread": False})
        insp = _inspect(live_engine)
        tables = insp.get_table_names()
        assert "trailer_edits" in tables
        cols = {c["name"] for c in insp.get_columns("trailer_edits")}
        assert "job_id" in cols
        assert "plan_json" in cols
        assert "updated_at" in cols
        live_engine.dispose()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 9 — GET /editor/{job_id}/scenes
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditorScenes:

    def test_trailer_job_scenes_returns_200(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}/scenes")
        assert r.status_code == 200, r.text

    def test_trailer_job_scenes_returns_ai_clips(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}/scenes")
        body = r.json()
        assert "scenes" in body
        assert len(body["scenes"]) == 1
        assert body["scenes"][0]["start_time"] == 0.0
        assert body["scenes"][0]["end_time"] == 5.0

    def test_smart_job_scenes_returns_200(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}/scenes")
        assert r.status_code == 200, r.text

    def test_smart_job_scenes_returns_ai_clips(self, client):
        job_id = _make_smart_job()
        r = client.get(f"/editor/{job_id}/scenes")
        body = r.json()
        assert "scenes" in body
        assert len(body["scenes"]) == 1

    def test_scenes_unaffected_by_user_edit(self, client):
        """Scenes always reflect the AI plan even after the user edits the trailer plan."""
        job_id = _make_smart_job()
        client.put(f"/editor/{job_id}/plan", json={
            "clips": [{
                "start_time": 10.0, "end_time": 15.0,
                "reason": "user", "topic": "Custom",
                "sentiment": "Neutral", "platform": None,
                "mood_group": "calm", "transcript_text": "",
            }],
        })
        r = client.get(f"/editor/{job_id}/scenes")
        assert r.json()["scenes"][0]["start_time"] == 0.0

    def test_scenes_unknown_job_returns_404(self, client):
        r = client.get(f"/editor/{uuid.uuid4()}/scenes")
        assert r.status_code == 404

    def test_scenes_response_shape(self, client):
        job_id = _make_trailer_job()
        r = client.get(f"/editor/{job_id}/scenes")
        scene = r.json()["scenes"][0]
        for field in ("start_time", "end_time", "topic", "sentiment",
                      "reason", "transcript_text", "mood_group", "muted"):
            assert field in scene, f"Missing field: {field}"
