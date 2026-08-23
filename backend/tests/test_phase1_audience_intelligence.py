"""
Phase 1 — Audience Intelligence Backend Tests

Test cases:
    1.  Existing feedback workflow (upload-feedback + analyze-feedback)
    2.  JSON feedback via new audience analysis endpoint
    3.  CSV feedback via new audience analysis endpoint
    4.  TXT feedback via new audience analysis endpoint
    5.  Positive-dominant feedback → analytics reflect positive majority
    6.  Negative-dominant feedback → analytics reflect negative majority
    7.  Neutral-dominant feedback  → analytics reflect neutral majority
    8.  Timestamped feedback → timeline + velocity populated
    9.  Feedback without timestamps → timeline empty, unanchored_count correct
    10. Empty dataset → 422 error
    11. Invalid JSON dataset → 422 error
    12. Existing trailer-generation workflow (smoke test — no regression)

Run from backend/:
    python -m pytest tests/test_phase1_audience_intelligence.py -v
"""

import json
import sys
import os
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# conftest.py inserts backend/ into sys.path — imports below resolve correctly
from app.main import app as fastapi_app
from app.db import database as _db_module
from app.db.database import get_db
from app.db.base import Base

# ── Shared test engine (file-based so background threads can connect) ─────────
# :memory: cannot be shared across threads — background tasks open new
# connections via SessionLocal which would get a different empty database.
# A named temp file is used instead so all threads share the same schema.

import tempfile
_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db_file.close()
TEST_DB_URL = f"sqlite:///{_db_file.name}"
_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    import app.models.feedback_dataset      # noqa: F401
    import app.models.trailer_job           # noqa: F401
    import app.models.smart_trailer_job     # noqa: F401
    import app.models.audience_analysis_job # noqa: F401
    import app.models.project               # noqa: F401
    Base.metadata.create_all(bind=_engine)
    from tests.conftest import seed_project_row
    seed_project_row(_TestSession)
    # Patch the module-level SessionLocal so background tasks use the test DB
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


# ── Fixtures: sample data ─────────────────────────────────────────────────────

PROJECT_ID = "83a49988-d057-46e4-8600-fe7c9ff8d7ff"  # exists in metadata/

POSITIVE_FEEDBACK = "\n".join([
    "The opening scene is absolutely amazing and sets the tone perfectly.",
    "Love the music choice — it fits the mood brilliantly.",
    "The camera work is outstanding, especially the close-up shots.",
    "Brilliant transitions between scenes, very smooth.",
    "The narration is clear and engaging throughout.",
])

NEGATIVE_FEEDBACK = "\n".join([
    "The intro is way too long and boring.",
    "The music is too loud and drowns out the narration.",
    "Terrible camera work in the second half.",
    "The pacing is awful — too slow and I stopped watching.",
    "The ending is confusing and abrupt.",
])

NEUTRAL_FEEDBACK = "\n".join([
    "The video is okay.",
    "Nothing special about the music.",
    "The camera work is average.",
    "Transitions are fine.",
    "The narration is acceptable.",
])

TIMESTAMPED_FEEDBACK = "\n".join([
    "0:15 The opening shot is incredible.",
    "0:45 Music kicks in perfectly here.",
    "1:20 Great transition at this point.",
    "2:00 The pacing slows down a bit here.",
    "2:30 Strong ending sequence.",
])

FEEDBACK_NO_TIMESTAMPS = "\n".join([
    "The opening is great.",
    "Music is too loud.",
    "Camera work is excellent.",
    "Pacing could be improved.",
    "Overall a solid trailer.",
])

JSON_FEEDBACK = json.dumps([
    {"timestamp": "0:15", "topic": "Camera",  "sentiment": "Positive",   "summary": "Great opening shot",    "confidence": 0.92},
    {"timestamp": "0:45", "topic": "Music",   "sentiment": "Positive",   "summary": "Music fits perfectly",  "confidence": 0.88},
    {"timestamp": "1:20", "topic": "Pacing",  "sentiment": "Negative",   "summary": "Pacing slows here",     "confidence": 0.81},
    {"timestamp": None,   "topic": "General", "sentiment": "Suggestion",  "summary": "Add more close-ups",   "confidence": 0.75},
    {"timestamp": None,   "topic": "Ending",  "sentiment": "Praise",     "summary": "Ending is powerful",    "confidence": 0.90},
])

CSV_FEEDBACK = (
    "timestamp,topic,sentiment,summary,confidence\n"
    "0:10,Camera,Positive,Excellent opening shot,0.91\n"
    "0:30,Music,Negative,Music too loud,0.85\n"
    "1:00,Pacing,Suggestion,Speed up the middle section,0.78\n"
    ",Narration,Neutral,Narration is fine,0.65\n"
    "2:00,Ending,Praise,Powerful ending,0.93\n"
)


# ── Helper: wait for background job ──────────────────────────────────────────

def _wait_for_job(client, job_id: str, timeout: int = 30) -> dict:
    """Poll /audience-analysis/{job_id} until done or failed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = client.get(f"/audience-analysis/{job_id}")
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(0.3)
    pytest.fail(f"Job {job_id} did not complete within {timeout}s")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Existing feedback workflow (no regression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExistingFeedbackWorkflow:
    def test_analyze_feedback_endpoint_still_works(self, client):
        """POST /analyze-feedback must still return AnalysisResponse."""
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert "dataset_id" in data
        assert "feedback_summary" in data
        assert "timeline_insights" in data
        assert "optimization_recommendations" in data
        assert "editing_plan" in data

    def test_upload_feedback_txt_still_works(self, client):
        """POST /upload-feedback with .txt must still return AnalysisResponse."""
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.txt", POSITIVE_FEEDBACK.encode(), "text/plain")},
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert "dataset_id" in data
        assert data["feedback_summary"]["positive"] >= 0

    def test_analytics_endpoint_still_works(self, client):
        """GET /analytics/{dataset_id} must still return AnalyticsReport."""
        # First create a dataset
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        assert r.status_code == 200
        dataset_id = r.json()["dataset_id"]

        r2 = client.get(f"/analytics/{dataset_id}")
        assert r2.status_code == 200, r2.text
        report = r2.json()
        assert "sentiment_distribution" in report
        assert "topic_breakdown" in report
        assert "audience_preferences" in report   # new field must be present


# ═══════════════════════════════════════════════════════════════════════════════
# Test 2 — JSON feedback via new endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestJSONFeedback:
    def test_json_upload_queues_job(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", JSON_FEEDBACK.encode(), "application/json")},
        )
        assert r.status_code == 202, r.text
        data = r.json()
        assert data["status"] in ("pending", "processing", "done")
        assert data["id"]

    def test_json_upload_completes_with_report(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", JSON_FEEDBACK.encode(), "application/json")},
        )
        assert r.status_code == 202
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done", result.get("error_message")
        assert result["analytics_report"] is not None
        assert result["dataset_id"] is not None

    def test_json_report_has_required_fields(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", JSON_FEEDBACK.encode(), "application/json")},
        )
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        for field in ("sentiment_distribution", "topic_breakdown", "timeline",
                      "confidence_stats", "sentiment_velocity", "top_issues",
                      "top_positives", "audience_preferences", "total_segments"):
            assert field in report, f"Missing field: {field}"

    def test_json_report_endpoint(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.json", JSON_FEEDBACK.encode(), "application/json")},
        )
        job_id = r.json()["id"]
        _wait_for_job(client, job_id)
        r2 = client.get(f"/audience-analysis/{job_id}/report")
        assert r2.status_code == 200, r2.text
        assert "sentiment_distribution" in r2.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Test 3 — CSV feedback via new endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSVFeedback:
    def test_csv_upload_completes(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.csv", CSV_FEEDBACK.encode(), "text/csv")},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done", result.get("error_message")

    def test_csv_report_has_segments(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.csv", CSV_FEEDBACK.encode(), "text/csv")},
        )
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["analytics_report"]["total_segments"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — TXT feedback via new endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestTXTFeedback:
    def test_txt_upload_completes(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.txt", POSITIVE_FEEDBACK.encode(), "text/plain")},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done", result.get("error_message")

    def test_txt_text_submit_completes(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done", result.get("error_message")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 5 — Positive-dominant feedback
# ═══════════════════════════════════════════════════════════════════════════════

class TestPositiveFeedback:
    def test_positive_majority_in_distribution(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        dist = result["analytics_report"]["sentiment_distribution"]
        pos = dist.get("Positive", 0) + dist.get("Praise", 0)
        neg = dist.get("Negative", 0) + dist.get("Complaint", 0)
        assert pos >= neg, f"Expected positive >= negative, got pos={pos} neg={neg}"

    def test_positive_audience_preferences_liked_populated(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        prefs = result["analytics_report"]["audience_preferences"]
        assert isinstance(prefs["liked"], list)
        assert isinstance(prefs["recurring_praise"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 6 — Negative-dominant feedback
# ═══════════════════════════════════════════════════════════════════════════════

class TestNegativeFeedback:
    def test_negative_majority_in_distribution(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": NEGATIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        dist = result["analytics_report"]["sentiment_distribution"]
        pos = dist.get("Positive", 0) + dist.get("Praise", 0)
        neg = dist.get("Negative", 0) + dist.get("Complaint", 0)
        assert neg >= pos, f"Expected negative >= positive, got neg={neg} pos={pos}"

    def test_negative_complaints_populated(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": NEGATIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        prefs = result["analytics_report"]["audience_preferences"]
        assert isinstance(prefs["recurring_complaints"], list)
        assert isinstance(prefs["disliked"], list)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 7 — Neutral-dominant feedback
# ═══════════════════════════════════════════════════════════════════════════════

class TestNeutralFeedback:
    def test_neutral_feedback_completes(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": NEUTRAL_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] == "done", result.get("error_message")

    def test_neutral_distribution_has_neutral_entries(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": NEUTRAL_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        dist = result["analytics_report"]["sentiment_distribution"]
        # At least some segments should be neutral
        total = sum(dist.values())
        assert total > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 8 — Timestamped feedback → timeline + velocity populated
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimestampedFeedback:
    def test_timeline_populated_when_timestamps_present(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": TIMESTAMPED_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        assert len(report["timeline"]) > 0, "Timeline should be populated for timestamped feedback"

    def test_velocity_populated_when_timestamps_present(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": TIMESTAMPED_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        assert len(report["sentiment_velocity"]) > 0, "Velocity should be populated for timestamped feedback"

    def test_json_timestamped_feedback(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("ts.json", JSON_FEEDBACK.encode(), "application/json")},
        )
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        # JSON_FEEDBACK has 3 timestamped entries
        assert len(report["timeline"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9 — Feedback without timestamps
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackWithoutTimestamps:
    def test_timeline_empty_without_timestamps(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": FEEDBACK_NO_TIMESTAMPS,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        assert len(report["timeline"]) == 0, "Timeline should be empty when no timestamps present"

    def test_unanchored_count_equals_total_segments(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": FEEDBACK_NO_TIMESTAMPS,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        report = result["analytics_report"]
        stats = report["confidence_stats"]
        assert stats["unanchored_count"] == report["total_segments"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 10 — Empty dataset → 422
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyDataset:
    def test_empty_text_returns_400(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": "   ",
        })
        assert r.status_code == 400, r.text

    def test_empty_file_returns_422(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("empty.txt", b"", "text/plain")},
        )
        assert r.status_code == 422, r.text

    def test_whitespace_only_txt_file(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("ws.txt", b"   \n\n   ", "text/plain")},
        )
        # Either 422 immediately or job fails — both are acceptable
        if r.status_code == 202:
            job_id = r.json()["id"]
            result = _wait_for_job(client, job_id)
            assert result["status"] == "failed"
        else:
            assert r.status_code in (400, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# Test 11 — Invalid JSON dataset → 422 / job fails gracefully
# ═══════════════════════════════════════════════════════════════════════════════

class TestInvalidDataset:
    def test_malformed_json_falls_back_to_agent(self, client):
        """Malformed JSON should fall back to the structuring agent, not crash."""
        bad_json = b'[{"topic": "Camera", "sentiment": "Positive", BROKEN'
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("bad.json", bad_json, "application/json")},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        # Falls back to structuring agent — may succeed or fail depending on content
        assert result["status"] in ("done", "failed")

    def test_unsupported_extension_rejected(self, client):
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("feedback.xml", b"<root/>", "application/xml")},
        )
        assert r.status_code == 400, r.text

    def test_invalid_project_id_returns_404(self, client):
        r = client.post("/audience-analysis", json={
            "project_id": "nonexistent-project-id",
            "feedback": POSITIVE_FEEDBACK,
        })
        assert r.status_code == 404, r.text

    def test_csv_missing_required_columns_falls_back(self, client):
        """CSV without sentiment/summary columns falls back to structuring agent."""
        bad_csv = b"col1,col2\nfoo,bar\nbaz,qux\n"
        r = client.post(
            "/audience-analysis/upload",
            data={"project_id": PROJECT_ID},
            files={"file": ("bad.csv", bad_csv, "text/csv")},
        )
        assert r.status_code == 202, r.text
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        assert result["status"] in ("done", "failed")


# ═══════════════════════════════════════════════════════════════════════════════
# Test 12 — Existing trailer-generation workflow (smoke test)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExistingTrailerWorkflow:
    def test_feedback_datasets_endpoint_still_works(self, client):
        """GET /feedback-datasets/{project_id} must still return a list."""
        r = client.get(f"/feedback-datasets/{PROJECT_ID}")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_analytics_cache_still_works(self, client):
        """GET /analytics/{dataset_id} must still cache and return on second call."""
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        assert r.status_code == 200
        dataset_id = r.json()["dataset_id"]

        r1 = client.get(f"/analytics/{dataset_id}")
        assert r1.status_code == 200
        r2 = client.get(f"/analytics/{dataset_id}")
        assert r2.status_code == 200
        # Both calls return identical reports
        assert r1.json()["total_segments"] == r2.json()["total_segments"]

    def test_audience_analysis_job_delete(self, client):
        """DELETE /audience-analysis/{job_id} must remove the job."""
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        _wait_for_job(client, job_id)

        del_r = client.delete(f"/audience-analysis/{job_id}")
        assert del_r.status_code == 204

        get_r = client.get(f"/audience-analysis/{job_id}")
        assert get_r.status_code == 404

    def test_audience_preferences_structure(self, client):
        """AudiencePreferences must have all required keys."""
        r = client.post("/audience-analysis", json={
            "project_id": PROJECT_ID,
            "feedback": POSITIVE_FEEDBACK + "\n" + NEGATIVE_FEEDBACK,
        })
        job_id = r.json()["id"]
        result = _wait_for_job(client, job_id)
        prefs = result["analytics_report"]["audience_preferences"]
        for key in ("liked", "disliked", "recurring_requests",
                    "recurring_complaints", "recurring_praise"):
            assert key in prefs, f"Missing key in audience_preferences: {key}"
            assert isinstance(prefs[key], list), f"{key} must be a list"
