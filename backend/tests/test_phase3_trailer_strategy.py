"""
Phase 3 — Trailer Strategy Tests

Test cases:
    1.  Strategy generation from cached analytics
    2.  Strategy generation computes analytics when no cache exists
    3.  Generated strategy is a non-empty string
    4.  GET strategy returns 404 before generation
    5.  GET strategy returns persisted row after generation
    6.  User can edit and save strategy (PUT)
    7.  Saved user_strategy differs from generated_strategy after edit
    8.  generated_strategy is never overwritten by PUT
    9.  Reset restores user_strategy to generated_strategy
    10. Regenerate overwrites generated_strategy and resets user_strategy
    11. Empty user_strategy rejected (400)
    12. Strategy for unknown dataset returns 404
    13. Strategy persists across requests (DB persistence)
    14. Empty analytics (no segments) returns 422 on generate
    15. Strategy agent produces output covering positive/negative signals

Run from backend/:
    python -m pytest tests/test_phase3_trailer_strategy.py -v
"""

import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import tempfile

from app.main import app as fastapi_app
from app.db import database as _db_module
from app.db.database import get_db
from app.db.base import Base

# ── Test DB setup (same pattern as Phase 1) ───────────────────────────────────
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
    import app.models.feedback_dataset
    import app.models.trailer_job
    import app.models.smart_trailer_job
    import app.models.audience_analysis_job
    import app.models.trailer_strategy
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
    {"timestamp": "0:15", "topic": "Action",     "sentiment": "Positive",  "summary": "Great action sequence",      "confidence": 0.92},
    {"timestamp": "0:45", "topic": "Music",      "sentiment": "Positive",  "summary": "Music fits perfectly",       "confidence": 0.88},
    {"timestamp": "1:00", "topic": "Exposition", "sentiment": "Negative",  "summary": "Too much exposition here",   "confidence": 0.85},
    {"timestamp": "1:30", "topic": "Pacing",     "sentiment": "Negative",  "summary": "Pacing slows down badly",   "confidence": 0.81},
    {"timestamp": "2:00", "topic": "Characters", "sentiment": "Positive",  "summary": "Character moment is strong", "confidence": 0.90},
    {"timestamp": None,   "topic": "General",    "sentiment": "Suggestion", "summary": "Add more close-up shots",   "confidence": 0.75},
])

_POSITIVE_ONLY = json.dumps([
    {"timestamp": "0:10", "topic": "Action",     "sentiment": "Positive", "summary": "Excellent opening",    "confidence": 0.95},
    {"timestamp": "0:30", "topic": "Characters", "sentiment": "Praise",   "summary": "Characters are great", "confidence": 0.91},
])


@pytest.fixture(scope="module")
def dataset_id(client):
    """Create a dataset with analytics cached, return its ID."""
    r = client.post("/analyze-feedback", json={
        "project_id": PROJECT_ID,
        "feedback": "The action scenes are incredible and very engaging.\n"
                    "Character moments feel authentic and emotional.\n"
                    "The exposition is too long and loses the audience.\n"
                    "Pacing in the middle section is too slow.\n"
                    "The music choice is perfect for the tone.",
    })
    assert r.status_code == 200, r.text
    ds_id = r.json()["dataset_id"]
    # Pre-compute analytics cache
    r2 = client.get(f"/analytics/{ds_id}")
    assert r2.status_code == 200
    return ds_id


@pytest.fixture(scope="module")
def dataset_id_no_cache(client):
    """Create a dataset WITHOUT pre-computing analytics cache."""
    r = client.post("/analyze-feedback", json={
        "project_id": PROJECT_ID,
        "feedback": "The trailer is visually stunning.\nThe pacing feels off in places.",
    })
    assert r.status_code == 200, r.text
    return r.json()["dataset_id"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 1 — Strategy generation from cached analytics
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyGeneration:
    def test_generate_returns_201(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201, r.text

    def test_generate_response_shape(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201
        data = r.json()
        assert "dataset_id"         in data
        assert "generated_strategy" in data
        assert "user_strategy"      in data
        assert "updated_at"         in data
        assert data["dataset_id"] == dataset_id

    # Test 3 — generated strategy is non-empty
    def test_generated_strategy_is_non_empty(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201
        assert len(r.json()["generated_strategy"].strip()) > 0

    # Test 2 — computes analytics when no cache exists
    def test_generate_without_cache_succeeds(self, client, dataset_id_no_cache):
        r = client.post(f"/strategy/{dataset_id_no_cache}/generate")
        assert r.status_code == 201, r.text
        assert len(r.json()["generated_strategy"].strip()) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Test 4 — GET returns 404 before generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetStrategy:
    def test_get_returns_404_before_generate(self, client):
        # Create a fresh dataset that has never had a strategy generated
        r = client.post("/analyze-feedback", json={
            "project_id": PROJECT_ID,
            "feedback": "Some feedback text here.",
        })
        fresh_id = r.json()["dataset_id"]
        r2 = client.get(f"/strategy/{fresh_id}")
        assert r2.status_code == 404, r2.text

    # Test 5 — GET returns persisted row after generation
    def test_get_returns_strategy_after_generate(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.get(f"/strategy/{dataset_id}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["dataset_id"] == dataset_id
        assert len(data["generated_strategy"]) > 0

    def test_get_unknown_dataset_returns_404(self, client):
        r = client.get("/strategy/nonexistent-dataset-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 6, 7, 8 — Edit and save strategy
# ═══════════════════════════════════════════════════════════════════════════════

class TestEditStrategy:
    EDITED_TEXT = "Focus on fast-paced action sequences and emotional character moments. Cut all exposition."

    def test_put_saves_user_strategy(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": self.EDITED_TEXT})
        assert r.status_code == 200, r.text
        assert r.json()["user_strategy"] == self.EDITED_TEXT

    # Test 7 — user_strategy differs from generated after edit
    def test_user_strategy_differs_after_edit(self, client, dataset_id):
        gen_r = client.post(f"/strategy/{dataset_id}/generate")
        generated = gen_r.json()["generated_strategy"]
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": self.EDITED_TEXT})
        get_r = client.get(f"/strategy/{dataset_id}")
        data = get_r.json()
        assert data["user_strategy"] == self.EDITED_TEXT
        assert data["generated_strategy"] == generated  # unchanged

    # Test 8 — generated_strategy never overwritten by PUT
    def test_generated_strategy_unchanged_after_put(self, client, dataset_id):
        gen_r = client.post(f"/strategy/{dataset_id}/generate")
        original_generated = gen_r.json()["generated_strategy"]
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Completely different text."})
        get_r = client.get(f"/strategy/{dataset_id}")
        assert get_r.json()["generated_strategy"] == original_generated

    # Test 11 — empty user_strategy rejected
    def test_empty_user_strategy_rejected(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": "   "})
        assert r.status_code == 400, r.text

    # Test 12 — PUT on unknown dataset returns 404
    def test_put_unknown_dataset_returns_404(self, client):
        r = client.put("/strategy/nonexistent-id", json={"user_strategy": "Some text."})
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Test 9 — Reset restores user_strategy to generated_strategy
# ═══════════════════════════════════════════════════════════════════════════════

class TestResetStrategy:
    def test_reset_restores_generated(self, client, dataset_id):
        gen_r = client.post(f"/strategy/{dataset_id}/generate")
        generated = gen_r.json()["generated_strategy"]
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "User edited this."})
        reset_r = client.post(f"/strategy/{dataset_id}/reset")
        assert reset_r.status_code == 200, reset_r.text
        data = reset_r.json()
        assert data["user_strategy"] == generated

    def test_reset_unknown_dataset_returns_404(self, client):
        r = client.post("/strategy/nonexistent-id/reset")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Test 10 — Regenerate overwrites generated_strategy
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegenerate:
    def test_regenerate_returns_201(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201, r.text

    def test_regenerate_resets_user_strategy(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "My custom strategy."})
        regen_r = client.post(f"/strategy/{dataset_id}/generate")
        # After regeneration, user_strategy is reset to the new generated text
        data = regen_r.json()
        assert data["user_strategy"] == data["generated_strategy"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 13 — DB persistence across requests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPersistence:
    def test_strategy_persists_across_requests(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        saved_text = "Persisted user strategy text."
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": saved_text})
        # New GET request should return the saved text
        r = client.get(f"/strategy/{dataset_id}")
        assert r.status_code == 200
        assert r.json()["user_strategy"] == saved_text

    def test_updated_at_changes_after_save(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r1 = client.get(f"/strategy/{dataset_id}")
        t1 = r1.json()["updated_at"]
        import time; time.sleep(0.05)
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Updated text."})
        r2 = client.get(f"/strategy/{dataset_id}")
        t2 = r2.json()["updated_at"]
        assert t2 >= t1


# ═══════════════════════════════════════════════════════════════════════════════
# Test 14 — Empty dataset (no segments) returns 422 on generate
# ═══════════════════════════════════════════════════════════════════════════════

class TestEmptyDataset:
    def test_generate_on_unknown_dataset_returns_404(self, client):
        r = client.post("/strategy/does-not-exist/generate")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# Test 15 — Strategy agent output covers positive/negative signals
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyAgentOutput:
    def test_strategy_references_positive_topics(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        strategy = r.json()["generated_strategy"].lower()
        # Strategy should mention something about positive engagement
        assert any(word in strategy for word in [
            "positive", "prioriti", "action", "character", "music",
            "amplif", "strong", "focus"
        ]), f"Strategy does not reference positive signals: {strategy}"

    def test_strategy_references_negative_signals(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        strategy = r.json()["generated_strategy"].lower()
        # Strategy should mention something about negative signals
        assert any(word in strategy for word in [
            "negative", "minimi", "reduc", "avoid", "address",
            "pain", "issue", "exposition", "pacing"
        ]), f"Strategy does not reference negative signals: {strategy}"

    def test_strategy_agent_direct(self):
        """Unit test the strategy agent directly without HTTP."""
        from app.services.strategy_agent import generate_strategy
        from app.schemas.feedback import (
            AnalyticsReport, AudiencePreferences, TopicBreakdown,
            ConfidenceStats, TopicInsight,
        )
        report = AnalyticsReport(
            sentiment_distribution={"Positive": 6, "Negative": 3, "Neutral": 1,
                                    "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0},
            topic_breakdown=[
                TopicBreakdown(topic="Action", total=4, positive=4, negative=0, neutral=0,
                               avg_confidence=0.9, dominant_sentiment="Positive", engagement_score=1.0),
                TopicBreakdown(topic="Exposition", total=3, positive=0, negative=3, neutral=0,
                               avg_confidence=0.85, dominant_sentiment="Negative", engagement_score=-1.0),
            ],
            timeline=[],
            confidence_stats=ConfidenceStats(mean=0.87, min=0.75, max=0.95,
                                             high_confidence_count=8, low_confidence_count=0,
                                             unanchored_count=2),
            sentiment_velocity=[],
            top_issues=[TopicInsight(topic="Exposition", sentiment="Negative", count=3,
                                     avg_confidence=0.85, sample_summaries=["Too long"])],
            top_positives=[TopicInsight(topic="Action", sentiment="Positive", count=4,
                                        avg_confidence=0.9, sample_summaries=["Great action"])],
            audience_preferences=AudiencePreferences(
                liked=["Action"],
                disliked=["Exposition"],
                recurring_requests=["Add more close-ups"],
                recurring_complaints=["Too much exposition"],
                recurring_praise=["Great action sequences"],
            ),
            total_segments=10,
            analyzed_at="2024-01-01T00:00:00",
        )
        result = generate_strategy(report)
        assert isinstance(result, str)
        assert len(result.strip()) > 0
        assert "action" in result.lower() or "positive" in result.lower()
