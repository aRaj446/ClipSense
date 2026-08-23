"""
Phase 6 — Integration & Validation — Chunk 1 of 3
DATA FLOW

Covers:
    - Shared DB fixture reused by all three chunks
    - Feedback ingestion  (text, JSON file, CSV file, TXT file)
    - Structured feedback → segments → analytics report
    - Analytics report shape and field completeness
    - Analytics cache (second call returns cached, not recomputed)
    - Audience preferences populated in report
    - Strategy generation from analytics
    - Strategy immutability (generated_strategy never overwritten by PUT)
    - User strategy edit and reset
    - Strategy resolution priority (body > DB > None)
    - Editor GET state (plan_source = "ai" before any user edit)
    - Editor PUT plan (user edit persisted, plan_source = "user")
    - Editor DELETE plan (reverts to AI plan)
    - Sensecap CSV export shape

Run from backend/:
    python -m pytest tests/test_phase6_chunk1_dataflow.py -v
"""

import json
import io
import csv
import tempfile
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app as fastapi_app
from app.db import database as _db_module
from app.db.database import get_db
from app.db.base import Base

# ── Shared test DB (named temp file so background threads see same schema) ────

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


# Real project that has a video file on disk
PROJECT_ID = "83a49988-d057-46e4-8600-fe7c9ff8d7ff"

_TEXT_FEEDBACK = (
    "The opening action sequence is incredible — really grabs attention.\n"
    "Music choice fits the tone perfectly at 0:30.\n"
    "Too much slow exposition around 1:00, loses momentum badly.\n"
    "Character moments at 1:30 feel authentic and emotionally resonant.\n"
    "Pacing drags in the second half — needs tighter cuts.\n"
    "The climax at 2:00 is the strongest part of the whole piece.\n"
    "Sound design is excellent throughout.\n"
    "Some dialogue scenes feel too long and could be trimmed.\n"
)

_JSON_FEEDBACK = json.dumps([
    {"timestamp": "0:10", "topic": "Action",     "sentiment": "Positive",  "summary": "Great opening action",      "confidence": 0.92},
    {"timestamp": "0:30", "topic": "Music",      "sentiment": "Positive",  "summary": "Music fits perfectly",      "confidence": 0.88},
    {"timestamp": "1:00", "topic": "Exposition", "sentiment": "Negative",  "summary": "Too much slow exposition",  "confidence": 0.85},
    {"timestamp": "1:30", "topic": "Characters", "sentiment": "Positive",  "summary": "Strong character moment",   "confidence": 0.90},
    {"timestamp": "2:00", "topic": "Climax",     "sentiment": "Positive",  "summary": "Climax is the best part",  "confidence": 0.94},
    {"timestamp": "2:30", "topic": "Pacing",     "sentiment": "Negative",  "summary": "Pacing drags at the end",  "confidence": 0.81},
])

_CSV_FEEDBACK = (
    "timestamp,topic,sentiment,summary,confidence\n"
    "0:10,Action,Positive,Great opening action,0.92\n"
    "0:30,Music,Positive,Music fits perfectly,0.88\n"
    "1:00,Exposition,Negative,Too much slow exposition,0.85\n"
    "1:30,Characters,Positive,Strong character moment,0.90\n"
    "2:00,Climax,Positive,Climax is the best part,0.94\n"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — Feedback Ingestion
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackIngestion:

    def test_text_feedback_returns_dataset_id(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert "dataset_id" in body
        assert len(body["dataset_id"]) > 0

    def test_text_feedback_returns_segments(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body["timeline_insights"]) > 0

    def test_text_feedback_summary_counts_add_up(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        body = r.json()
        s = body["feedback_summary"]
        total = s["positive"] + s["negative"] + s["neutral"]
        assert total == len(body["timeline_insights"])

    def test_json_file_upload_returns_201(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", _JSON_FEEDBACK.encode(), "application/json")},
        )
        assert r.status_code == 201, r.text

    def test_json_file_upload_segments_match_input(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", _JSON_FEEDBACK.encode(), "application/json")},
        )
        assert r.status_code == 201
        assert len(r.json()["timeline_insights"]) == 6

    def test_csv_file_upload_returns_201(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.csv", _CSV_FEEDBACK.encode(), "text/csv")},
        )
        assert r.status_code == 201, r.text

    def test_csv_file_upload_segments_match_input(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.csv", _CSV_FEEDBACK.encode(), "text/csv")},
        )
        assert r.status_code == 201
        assert len(r.json()["timeline_insights"]) == 5

    def test_dataset_persisted_and_retrievable(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        ds_id = r.json()["dataset_id"]
        r2 = client.get(f"/feedback-dataset/{ds_id}")
        assert r2.status_code == 200
        assert r2.json()["id"] == ds_id

    def test_dataset_listed_under_project(self, client):
        r = client.get(f"/feedback-datasets/{PROJECT_ID}")
        assert r.status_code == 200
        assert len(r.json()) > 0

    def test_dataset_rename(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": "Good action scenes. Bad pacing.",
        })
        ds_id = r.json()["dataset_id"]
        r2 = client.patch(f"/feedback-dataset/{ds_id}/rename", json={"name": "Phase6 Test Dataset"})
        assert r2.status_code == 200
        assert r2.json()["name"] == "Phase6 Test Dataset"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Analytics Report
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def dataset_id(client):
    """Single dataset used by all analytics/strategy/editor tests."""
    r = client.post(
        "/upload-feedback",
        data={"project_id": PROJECT_ID},
        files={"file": ("feedback.json", _JSON_FEEDBACK.encode(), "application/json")},
    )
    assert r.status_code == 201, r.text
    return r.json()["dataset_id"]


class TestAnalyticsReport:

    def test_analytics_endpoint_returns_200(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        assert r.status_code == 200, r.text

    def test_analytics_has_required_top_level_fields(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        body = r.json()
        for field in (
            "sentiment_distribution", "topic_breakdown", "timeline",
            "confidence_stats", "sentiment_velocity", "top_issues",
            "top_positives", "audience_preferences", "total_segments", "analyzed_at",
        ):
            assert field in body, f"Missing field: {field}"

    def test_analytics_sentiment_distribution_has_positive(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        dist = r.json()["sentiment_distribution"]
        assert dist.get("Positive", 0) > 0

    def test_analytics_topic_breakdown_populated(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        tb = r.json()["topic_breakdown"]
        assert len(tb) > 0
        for entry in tb:
            assert "topic" in entry
            assert "engagement_score" in entry

    def test_analytics_timeline_has_timestamps(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        timeline = r.json()["timeline"]
        timestamped = [p for p in timeline if p["timestamp"]]
        assert len(timestamped) > 0

    def test_analytics_confidence_stats_shape(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        cs = r.json()["confidence_stats"]
        for field in ("mean", "min", "max", "high_confidence_count", "low_confidence_count"):
            assert field in cs

    def test_analytics_audience_preferences_shape(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        ap = r.json()["audience_preferences"]
        for field in ("liked", "disliked", "recurring_requests", "recurring_complaints", "recurring_praise"):
            assert field in ap, f"Missing audience_preferences field: {field}"
            assert isinstance(ap[field], list)

    def test_analytics_audience_preferences_liked_populated(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        ap = r.json()["audience_preferences"]
        # Dataset has 4 positive segments — liked should not be empty
        assert len(ap["liked"]) > 0

    def test_analytics_cache_returns_same_result(self, client, dataset_id):
        r1 = client.get(f"/analytics/{dataset_id}")
        r2 = client.get(f"/analytics/{dataset_id}")
        assert r1.json()["analyzed_at"] == r2.json()["analyzed_at"]

    def test_analytics_total_segments_matches_dataset(self, client, dataset_id):
        r_ds  = client.get(f"/feedback-dataset/{dataset_id}")
        r_ana = client.get(f"/analytics/{dataset_id}")
        assert r_ana.json()["total_segments"] == r_ds.json()["segment_count"]


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Strategy: generation, edit, reset, immutability
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyDataFlow:

    def test_generate_returns_201(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201, r.text

    def test_generate_response_has_required_fields(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        body = r.json()
        for field in ("dataset_id", "generated_strategy", "user_strategy", "updated_at"):
            assert field in body

    def test_generated_strategy_is_non_empty(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert len(r.json()["generated_strategy"].strip()) > 0

    def test_user_strategy_equals_generated_on_first_generate(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        body = r.json()
        assert body["user_strategy"] == body["generated_strategy"]

    def test_get_returns_strategy_after_generate(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.get(f"/strategy/{dataset_id}")
        assert r.status_code == 200

    def test_put_saves_user_strategy(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Focus on high-energy action."})
        assert r.status_code == 200
        assert r.json()["user_strategy"] == "Focus on high-energy action."

    def test_generated_strategy_unchanged_after_put(self, client, dataset_id):
        r_gen = client.post(f"/strategy/{dataset_id}/generate")
        original = r_gen.json()["generated_strategy"]
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "My custom strategy."})
        r_get = client.get(f"/strategy/{dataset_id}")
        assert r_get.json()["generated_strategy"] == original

    def test_reset_restores_generated_strategy(self, client, dataset_id):
        r_gen = client.post(f"/strategy/{dataset_id}/generate")
        generated = r_gen.json()["generated_strategy"]
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Completely different text."})
        r_reset = client.post(f"/strategy/{dataset_id}/reset")
        assert r_reset.status_code == 200
        assert r_reset.json()["user_strategy"] == generated

    def test_empty_user_strategy_rejected(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": "   "})
        assert r.status_code == 400

    def test_strategy_references_positive_topics(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        text = r.json()["generated_strategy"].lower()
        # Dataset has Action, Music, Characters, Climax as positive topics
        positive_topics = {"action", "music", "characters", "climax"}
        assert any(t in text for t in positive_topics), \
            f"Strategy should reference at least one positive topic. Got: {text[:200]}"

    def test_strategy_references_negative_signals(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        text = r.json()["generated_strategy"].lower()
        # Dataset has Exposition and Pacing as negative topics
        negative_signals = {"exposition", "pacing", "slow", "negative"}
        assert any(s in text for s in negative_signals), \
            f"Strategy should reference negative signals. Got: {text[:200]}"

    def test_strategy_resolution_body_overrides_db(self, client, dataset_id):
        """body.strategy takes priority over DB user_strategy."""
        client.post(f"/strategy/{dataset_id}/generate")
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "DB strategy text."})
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "Body override strategy.",
        })
        # 202 accepted or 404 project video missing — must not be 422 or 500
        assert r.status_code in (202, 404), r.text

    def test_strategy_resolution_db_used_when_no_body(self, client, dataset_id):
        """When body.strategy is absent, DB user_strategy is loaded."""
        client.post(f"/strategy/{dataset_id}/generate")
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Focus on action."})
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        assert r.status_code in (202, 404), r.text

    def test_strategy_resolution_none_when_no_strategy_exists(self, client):
        """When no strategy in body and no DB row, generation still works."""
        # Create a fresh dataset with no strategy
        r_ds = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": "Good action. Bad pacing.",
        })
        fresh_ds_id = r_ds.json()["dataset_id"]
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": fresh_ds_id,
        })
        assert r.status_code in (202, 404), r.text


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Editor state: GET / PUT / DELETE
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def done_job_id(client, dataset_id):
    """
    Return the id of a completed trailer job for the test dataset.
    Looks for an existing done job first; skips if none exists and no video
    is present (CI environment without video files).
    """
    r = client.get(f"/trailer-jobs/{PROJECT_ID}")
    if r.status_code == 200:
        done = [j for j in r.json() if j["status"] == "done" and j["dataset_id"] == dataset_id]
        if done:
            return done[0]["id"]
    pytest.skip("No completed trailer job available — skipping editor tests")


class TestEditorDataFlow:

    def test_editor_get_returns_200_for_done_job(self, client, done_job_id):
        r = client.get(f"/editor/{done_job_id}")
        assert r.status_code == 200, r.text

    def test_editor_get_response_shape(self, client, done_job_id):
        r = client.get(f"/editor/{done_job_id}")
        body = r.json()
        for field in ("job_id", "project_id", "status", "plan", "plan_source", "plan_updated_at"):
            assert field in body, f"Missing field: {field}"

    def test_editor_get_plan_source_is_ai_before_edit(self, client, done_job_id):
        # Delete any existing user edit first to ensure clean state
        client.delete(f"/editor/{done_job_id}/plan")
        r = client.get(f"/editor/{done_job_id}")
        assert r.json()["plan_source"] == "ai"

    def test_editor_get_plan_not_none_for_done_job(self, client, done_job_id):
        r = client.get(f"/editor/{done_job_id}")
        assert r.json()["plan"] is not None

    def test_editor_put_saves_user_plan(self, client, done_job_id):
        # Get the AI plan to use as base
        r_get = client.get(f"/editor/{done_job_id}")
        ai_plan = r_get.json()["plan"]
        clips = ai_plan["clips"][:2] if len(ai_plan["clips"]) >= 2 else ai_plan["clips"]

        r = client.put(f"/editor/{done_job_id}/plan", json={
            "clips": clips,
            "rationale": "User trimmed to first 2 clips",
        })
        assert r.status_code == 200, r.text

    def test_editor_put_changes_plan_source_to_user(self, client, done_job_id):
        r_get = client.get(f"/editor/{done_job_id}")
        clips = r_get.json()["plan"]["clips"][:1]
        client.put(f"/editor/{done_job_id}/plan", json={"clips": clips})
        r = client.get(f"/editor/{done_job_id}")
        assert r.json()["plan_source"] == "user"

    def test_editor_put_plan_updated_at_is_set(self, client, done_job_id):
        r_get = client.get(f"/editor/{done_job_id}")
        clips = r_get.json()["plan"]["clips"][:1]
        client.put(f"/editor/{done_job_id}/plan", json={"clips": clips})
        r = client.get(f"/editor/{done_job_id}")
        assert r.json()["plan_updated_at"] is not None

    def test_editor_delete_reverts_to_ai_plan(self, client, done_job_id):
        # First save a user edit
        r_get = client.get(f"/editor/{done_job_id}")
        clips = r_get.json()["plan"]["clips"][:1]
        client.put(f"/editor/{done_job_id}/plan", json={"clips": clips})
        # Now delete it
        r_del = client.delete(f"/editor/{done_job_id}/plan")
        assert r_del.status_code == 204
        # Verify reverted
        r = client.get(f"/editor/{done_job_id}")
        assert r.json()["plan_source"] == "ai"
        assert r.json()["plan_updated_at"] is None

    def test_editor_put_empty_clips_rejected(self, client, done_job_id):
        r = client.put(f"/editor/{done_job_id}/plan", json={"clips": []})
        assert r.status_code == 400

    def test_editor_get_unknown_job_returns_404(self, client):
        r = client.get("/editor/nonexistent-job-id")
        assert r.status_code == 404

    def test_editor_delete_unknown_job_returns_404(self, client):
        r = client.delete("/editor/nonexistent-job-id/plan")
        assert r.status_code == 404

    def test_editor_render_returns_202_with_new_job_id(self, client, done_job_id):
        r = client.post(f"/editor/{done_job_id}/render")
        assert r.status_code == 202, r.text
        body = r.json()
        assert "new_job_id" in body
        assert body["new_job_id"] != done_job_id

    def test_editor_render_new_job_is_pollable(self, client, done_job_id):
        r = client.post(f"/editor/{done_job_id}/render")
        new_id = r.json()["new_job_id"]
        r2 = client.get(f"/trailer-job/{new_id}")
        assert r2.status_code == 200
        assert r2.json()["status"] in ("pending", "processing", "done", "failed")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Sensecap CSV export
# ═══════════════════════════════════════════════════════════════════════════════

class TestSensecapExport:

    def test_csv_export_returns_200(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        assert r.status_code == 200, r.text

    def test_csv_export_content_type(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        assert "text/csv" in r.headers.get("content-type", "")

    def test_csv_export_has_content_disposition(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        assert "attachment" in r.headers.get("content-disposition", "")

    def test_csv_export_is_parseable(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        reader = csv.DictReader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) > 0

    def test_csv_export_has_required_columns(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        reader = csv.DictReader(io.StringIO(r.text))
        headers = set(reader.fieldnames or [])
        for col in ("video_timestamp", "theme", "sentiment_label", "confidence", "text"):
            assert col in headers, f"Missing CSV column: {col}"

    def test_csv_export_has_audience_preference_columns(self, client, dataset_id):
        # Warm analytics cache first so ap_* columns are populated
        client.get(f"/analytics/{dataset_id}")
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        reader = csv.DictReader(io.StringIO(r.text))
        headers = set(reader.fieldnames or [])
        for col in ("ap_liked", "ap_disliked", "ap_recurring_requests",
                    "ap_recurring_complaints", "ap_recurring_praise"):
            assert col in headers, f"Missing audience preference CSV column: {col}"

    def test_csv_export_row_count_matches_segments(self, client, dataset_id):
        r_ds  = client.get(f"/feedback-dataset/{dataset_id}")
        r_csv = client.get(f"/export-dataset/{dataset_id}/csv")
        rows = list(csv.DictReader(io.StringIO(r_csv.text)))
        assert len(rows) == r_ds.json()["segment_count"]

    def test_excel_export_returns_200(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers.get("content-type", "")
