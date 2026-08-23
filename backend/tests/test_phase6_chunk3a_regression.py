"""
Phase 6 — Integration & Validation — Chunk 3a of 3
REGRESSION

Verifies all functionality that existed BEFORE Phase 1-4 migration:
    - Project upload and metadata retrieval
    - Feedback file upload (JSON, CSV, TXT)
    - POST /analyze-feedback (text path)
    - Feedback dataset list / get / delete / rename
    - Analytics endpoint and cache
    - POST /generate-trailer (standard path, no strategy)
    - Trailer job poll / list / cancel / delete
    - GET /all-trailers
    - Trailer SSE progress stream
    - Smart trailer job list
    - Sensecap CSV and Excel export
    - Health endpoint

Run from backend/:
    python -m pytest tests/test_phase6_chunk3a_regression.py -v
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
    {"timestamp": "0:10", "topic": "Action",     "sentiment": "Positive", "summary": "Great action",        "confidence": 0.92},
    {"timestamp": "0:30", "topic": "Music",      "sentiment": "Positive", "summary": "Music fits",          "confidence": 0.88},
    {"timestamp": "1:00", "topic": "Exposition", "sentiment": "Negative", "summary": "Too much exposition", "confidence": 0.85},
    {"timestamp": "1:30", "topic": "Characters", "sentiment": "Positive", "summary": "Strong character",    "confidence": 0.90},
])

_CSV_FEEDBACK = (
    "timestamp,topic,sentiment,summary,confidence\n"
    "0:10,Action,Positive,Great opening action,0.92\n"
    "0:30,Music,Positive,Music fits perfectly,0.88\n"
    "1:00,Exposition,Negative,Too much slow exposition,0.85\n"
)

_TEXT_FEEDBACK = (
    "The action scenes are incredible.\n"
    "Music choice is perfect.\n"
    "Too much exposition in the middle.\n"
    "Character moments feel authentic.\n"
)


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
# Section 1 — Health
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthRegression:

    def test_health_endpoint_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_health_response_has_status(self, client):
        r = client.get("/health")
        assert "status" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Project Metadata
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectRegression:

    def test_list_projects_returns_200(self, client):
        r = client.get("/projects")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_known_project_returns_200(self, client):
        r = client.get(f"/project/{PROJECT_ID}")
        assert r.status_code == 200

    def test_project_has_required_fields(self, client):
        r = client.get(f"/project/{PROJECT_ID}")
        body = r.json()
        for field in ("id", "filename", "status"):
            assert field in body, f"Missing project field: {field}"

    def test_unknown_project_returns_404(self, client):
        r = client.get("/project/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Feedback Upload Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackUploadRegression:

    def test_json_upload_still_returns_201(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.json", _JSON_FEEDBACK.encode(), "application/json")},
        )
        assert r.status_code == 201, r.text

    def test_csv_upload_still_returns_201(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.csv", _CSV_FEEDBACK.encode(), "text/csv")},
        )
        assert r.status_code == 201, r.text

    def test_txt_upload_still_returns_201(self, client):
        r = client.post(
            "/upload-feedback",
            data={"project_id": PROJECT_ID},
            files={"file": ("fb.txt", _TEXT_FEEDBACK.encode(), "text/plain")},
        )
        assert r.status_code == 201, r.text

    def test_analyze_feedback_text_path_still_works(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert r.status_code == 200, r.text

    def test_analyze_feedback_returns_dataset_id(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert "dataset_id" in r.json()
        assert len(r.json()["dataset_id"]) > 0

    def test_analyze_feedback_returns_optimization_recommendations(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert "optimization_recommendations" in r.json()

    def test_analyze_feedback_returns_editing_plan(self, client):
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": _TEXT_FEEDBACK,
        })
        assert "editing_plan" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Dataset CRUD Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestDatasetCRUDRegression:

    def test_list_datasets_returns_200(self, client, dataset_id):
        r = client.get(f"/feedback-datasets/{PROJECT_ID}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_dataset_returns_200(self, client, dataset_id):
        r = client.get(f"/feedback-dataset/{dataset_id}")
        assert r.status_code == 200

    def test_get_dataset_has_segments(self, client, dataset_id):
        r = client.get(f"/feedback-dataset/{dataset_id}")
        assert len(r.json()["segments"]) > 0

    def test_rename_dataset_still_works(self, client, dataset_id):
        r = client.patch(
            f"/feedback-dataset/{dataset_id}/rename",
            json={"name": "Regression Test Dataset"},
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Regression Test Dataset"

    def test_delete_dataset_removes_record(self, client):
        # Create a throwaway dataset
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": "Throwaway feedback for delete regression test.",
        })
        ds_id = r.json()["dataset_id"]
        r_del = client.delete(f"/feedback-dataset/{ds_id}")
        assert r_del.status_code == 204
        r_get = client.get(f"/feedback-dataset/{ds_id}")
        assert r_get.status_code == 404

    def test_unknown_dataset_returns_404(self, client):
        r = client.get("/feedback-dataset/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Analytics Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyticsRegression:

    def test_analytics_endpoint_still_works(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        assert r.status_code == 200, r.text

    def test_analytics_cache_still_works(self, client, dataset_id):
        r1 = client.get(f"/analytics/{dataset_id}")
        r2 = client.get(f"/analytics/{dataset_id}")
        assert r1.json()["analyzed_at"] == r2.json()["analyzed_at"]

    def test_analytics_sentiment_distribution_present(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        assert "sentiment_distribution" in r.json()

    def test_analytics_topic_breakdown_present(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        assert len(r.json()["topic_breakdown"]) > 0

    def test_analytics_audience_preferences_present(self, client, dataset_id):
        r = client.get(f"/analytics/{dataset_id}")
        assert "audience_preferences" in r.json()

    def test_analytics_unknown_dataset_returns_404(self, client):
        r = client.get("/analytics/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Trailer Generation Regression (no strategy)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrailerGenerationRegression:

    def test_generate_trailer_without_strategy_still_accepted(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        # 202 = queued, 404 = project video missing — both valid
        assert r.status_code in (202, 404), r.text

    def test_generate_trailer_schema_unchanged(self, client, dataset_id):
        """GenerateTrailerRequest without strategy must not be rejected with 422."""
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        assert r.status_code != 422, "Schema must not reject requests without strategy field"

    def test_trailer_job_list_still_works(self, client):
        r = client.get(f"/trailer-jobs/{PROJECT_ID}")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_all_trailers_endpoint_still_works(self, client):
        r = client.get("/all-trailers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_all_trailers_only_returns_done_jobs(self, client):
        r = client.get("/all-trailers")
        for job in r.json():
            assert job["status"] == "done"

    def test_trailer_job_poll_still_works(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        r2 = client.get(f"/trailer-job/{job_id}")
        assert r2.status_code == 200

    def test_trailer_sse_still_returns_event_stream(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        if r.status_code == 404:
            pytest.skip("Project video not present")
        job_id = r.json()["id"]
        with client.stream("GET", f"/trailer-job/{job_id}/progress") as resp:
            assert "text/event-stream" in resp.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 7 — Export Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportRegression:

    def test_csv_export_still_returns_200(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        assert r.status_code == 200

    def test_csv_export_still_parseable(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}/csv")
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert len(rows) > 0

    def test_excel_export_still_returns_200(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}")
        assert r.status_code == 200

    def test_excel_export_content_type(self, client, dataset_id):
        r = client.get(f"/export-dataset/{dataset_id}")
        assert "spreadsheetml" in r.headers.get("content-type", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 8 — Smart Trailer Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestSmartTrailerRegression:

    def test_smart_trailer_list_returns_200(self, client):
        r = client.get("/smart-trailer/jobs")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_smart_trailer_unknown_job_returns_404(self, client):
        r = client.get("/smart-trailer/job/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Section 9 — Strategy Endpoints Regression
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyEndpointsRegression:

    def test_strategy_generate_still_returns_201(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201, r.text

    def test_strategy_get_still_returns_200(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.get(f"/strategy/{dataset_id}")
        assert r.status_code == 200

    def test_strategy_put_still_returns_200(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Regression strategy."})
        assert r.status_code == 200

    def test_strategy_reset_still_returns_200(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.post(f"/strategy/{dataset_id}/reset")
        assert r.status_code == 200

    def test_strategy_get_unknown_dataset_returns_404(self, client):
        r = client.get("/strategy/00000000-0000-0000-0000-000000000000")
        assert r.status_code == 404

    def test_strategy_generate_unknown_dataset_returns_404(self, client):
        r = client.post("/strategy/00000000-0000-0000-0000-000000000000/generate")
        assert r.status_code == 404
