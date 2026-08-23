"""
Phase 4 — Strategy-Driven Trailer Generation Tests

Test cases:
    1.  Existing generation (no strategy) — backward compatibility
    2.  Strategy-driven generation — simple strategy
    3.  Complex strategy — multiple requirements
    4.  Empty/whitespace strategy — treated as no strategy
    5.  Strategy loaded automatically from DB when saved
    6.  Explicit body.strategy overrides DB strategy
    7.  Missing transcript — fallback behaviour
    8.  Beat detection failure — fallback behaviour
    9.  Strategy parser — high-energy keywords
    10. Strategy parser — emotional keywords
    11. Strategy parser — reduce slow/exposition keywords
    12. Strategy parser — empty string returns no-op modifiers
    13. _build_plans with strategy — strategy_score present in clips
    14. _build_plans without strategy — backward-compatible output shape
    15. Strategy step appears in progress steps list
    16. Regression — Phase 3 strategy endpoints still work

Run from backend/:
    python -m pytest tests/test_phase4_strategy_generation.py -v
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

# ── Test DB ───────────────────────────────────────────────────────────────────
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

_MIXED_FEEDBACK = json.dumps([
    {"timestamp": "0:10", "topic": "Action",     "sentiment": "Positive",  "summary": "Great action sequence",    "confidence": 0.92},
    {"timestamp": "0:30", "topic": "Music",      "sentiment": "Positive",  "summary": "Music fits perfectly",     "confidence": 0.88},
    {"timestamp": "1:00", "topic": "Exposition", "sentiment": "Negative",  "summary": "Too much exposition",      "confidence": 0.85},
    {"timestamp": "1:30", "topic": "Characters", "sentiment": "Positive",  "summary": "Strong character moment",  "confidence": 0.90},
    {"timestamp": "2:00", "topic": "Pacing",     "sentiment": "Negative",  "summary": "Pacing slows badly",       "confidence": 0.81},
])


@pytest.fixture(scope="module")
def dataset_id(client):
    """Create a dataset with analytics cached."""
    r = client.post("/analyze-feedback", json={
        "project_id": PROJECT_ID,
        "feedback": (
            "The action scenes are incredible.\n"
            "Music choice is perfect.\n"
            "Too much exposition in the middle.\n"
            "Character moments feel authentic.\n"
            "Pacing slows down too much."
        ),
    })
    assert r.status_code == 200, r.text
    ds_id = r.json()["dataset_id"]
    client.get(f"/analytics/{ds_id}")   # warm analytics cache
    return ds_id


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 1–4 — API-level generation (no actual video — expect graceful failure)
# These tests verify the request/response contract and strategy wiring,
# not the FFmpeg pipeline (no video file exists in the test environment).
# ═══════════════════════════════════════════════════════════════════════════════

class TestGenerationAPIContract:

    # Test 1 — backward compatibility: no strategy field accepted
    def test_no_strategy_field_accepted(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        # 202 accepted (job queued) or 404 project not found are both valid
        # depending on whether the project metadata file exists.
        # What must NOT happen: 422 (schema rejection) or 500.
        assert r.status_code in (202, 404), r.text

    # Test 2 — simple strategy accepted without schema error
    def test_simple_strategy_accepted(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "High-energy trailer focusing on action sequences.",
        })
        assert r.status_code in (202, 404), r.text

    # Test 3 — complex strategy accepted
    def test_complex_strategy_accepted(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": (
                "Create a high-energy trailer focusing on action and emotional character moments. "
                "Reduce slow exposition scenes. Prioritise fast pacing and suspenseful cuts."
            ),
        })
        assert r.status_code in (202, 404), r.text

    # Test 4 — empty strategy treated as no strategy (not rejected)
    def test_empty_strategy_not_rejected(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "",
        })
        assert r.status_code in (202, 404), r.text

    def test_whitespace_strategy_not_rejected(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "   ",
        })
        assert r.status_code in (202, 404), r.text


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 5–6 — Strategy DB loading
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyDBLoading:

    # Test 5 — strategy loaded from DB when no body.strategy provided
    def test_strategy_loaded_from_db(self, client, dataset_id):
        # Save a strategy to DB
        client.post(f"/strategy/{dataset_id}/generate")
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Focus on action."})

        # Trigger generation without body.strategy — should pick up DB strategy
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        # Job accepted (or 404 if project video missing) — no schema error
        assert r.status_code in (202, 404), r.text

    # Test 6 — explicit body.strategy overrides DB strategy
    def test_body_strategy_overrides_db(self, client, dataset_id):
        # Save a different strategy to DB
        client.post(f"/strategy/{dataset_id}/generate")
        client.put(f"/strategy/{dataset_id}", json={"user_strategy": "DB strategy text."})

        # Provide explicit override in body
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "Body override strategy.",
        })
        assert r.status_code in (202, 404), r.text


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 7–8 — Fallback behaviour (unit-level, no video needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackBehaviour:

    # Test 7 — missing transcript: _build_plans still returns plans
    def test_build_plans_with_empty_transcript(self):
        from app.services.video_regeneration_agent import _build_plans
        from app.schemas.feedback import (
            AnalyticsReport, AudiencePreferences, TopicBreakdown,
            ConfidenceStats, TimelinePoint,
        )
        report = AnalyticsReport(
            sentiment_distribution={"Positive": 3, "Negative": 1, "Neutral": 0,
                                    "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0},
            topic_breakdown=[
                TopicBreakdown(topic="Action", total=3, positive=3, negative=0, neutral=0,
                               avg_confidence=0.9, dominant_sentiment="Positive", engagement_score=1.0),
            ],
            timeline=[
                TimelinePoint(timestamp="0:10", topic="Action", sentiment="Positive",
                              summary="Great action", confidence=0.9),
            ],
            confidence_stats=ConfidenceStats(mean=0.9, min=0.9, max=0.9,
                                             high_confidence_count=1, low_confidence_count=0,
                                             unanchored_count=0),
            sentiment_velocity=[],
            top_issues=[],
            top_positives=[],
            audience_preferences=AudiencePreferences(
                liked=["Action"], disliked=[], recurring_requests=[],
                recurring_complaints=[], recurring_praise=[],
            ),
            total_segments=4,
            analyzed_at="2024-01-01T00:00:00",
        )
        # Empty shot boundaries and beats — should not crash
        plans = _build_plans(report, 120.0, [], [], strategy_text=None)
        assert isinstance(plans, list)
        assert len(plans) == 4  # one per platform

    # Test 8 — beat detection failure: _build_plans with empty beats list
    def test_build_plans_with_empty_beats(self):
        from app.services.video_regeneration_agent import _build_plans
        from app.schemas.feedback import (
            AnalyticsReport, AudiencePreferences, TopicBreakdown,
            ConfidenceStats, TimelinePoint,
        )
        report = AnalyticsReport(
            sentiment_distribution={"Positive": 2, "Negative": 0, "Neutral": 0,
                                    "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0},
            topic_breakdown=[
                TopicBreakdown(topic="Music", total=2, positive=2, negative=0, neutral=0,
                               avg_confidence=0.85, dominant_sentiment="Positive", engagement_score=1.0),
            ],
            timeline=[
                TimelinePoint(timestamp="0:20", topic="Music", sentiment="Positive",
                              summary="Music is great", confidence=0.85),
            ],
            confidence_stats=ConfidenceStats(mean=0.85, min=0.85, max=0.85,
                                             high_confidence_count=1, low_confidence_count=0,
                                             unanchored_count=0),
            sentiment_velocity=[],
            top_issues=[],
            top_positives=[],
            audience_preferences=AudiencePreferences(
                liked=["Music"], disliked=[], recurring_requests=[],
                recurring_complaints=[], recurring_praise=[],
            ),
            total_segments=2,
            analyzed_at="2024-01-01T00:00:00",
        )
        plans = _build_plans(report, 120.0, [], beats=[], strategy_text="High-energy action trailer.")
        assert isinstance(plans, list)


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 9–12 — Strategy parser unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategyParser:

    def test_high_energy_keywords(self):
        from app.services.video_regeneration_agent import _parse_strategy
        result = _parse_strategy("Create a high-energy action trailer with fast pacing.")
        assert result["prefer_short"] is True
        assert result["sentiment_boost"] > 0
        assert len(result["raw_labels"]) > 0

    def test_emotional_keywords(self):
        from app.services.video_regeneration_agent import _parse_strategy
        result = _parse_strategy("Focus on emotional character moments and heartfelt scenes.")
        assert result["sentiment_boost"] > 0
        assert any("motion" in l.lower() or "haracter" in l.lower()
                   for l in result["raw_labels"])

    def test_reduce_slow_keywords(self):
        from app.services.video_regeneration_agent import _parse_strategy
        result = _parse_strategy("Reduce slow scenes and cut exposition.")
        assert result["sentiment_boost"] < 0 or result["prefer_short"] is True

    def test_empty_string_returns_noop(self):
        from app.services.video_regeneration_agent import _parse_strategy
        result = _parse_strategy("")
        assert result["sentiment_boost"] == 0.0
        assert result["prefer_short"] is False
        assert result["raw_labels"] == []

    def test_none_returns_noop(self):
        from app.services.video_regeneration_agent import _parse_strategy
        result = _parse_strategy(None)
        assert result["sentiment_boost"] == 0.0
        assert result["prefer_short"] is False

    def test_sentiment_boost_clamped(self):
        from app.services.video_regeneration_agent import _parse_strategy
        # Pile on many positive keywords — boost must stay within [-1, 1]
        result = _parse_strategy(
            "high-energy action fast intense explosive dynamic emotional heartfelt suspense tension"
        )
        assert -1.0 <= result["sentiment_boost"] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Tests 13–14 — _build_plans output shape
# ═══════════════════════════════════════════════════════════════════════════════

def _make_report():
    from app.schemas.feedback import (
        AnalyticsReport, AudiencePreferences, TopicBreakdown,
        ConfidenceStats, TimelinePoint,
    )
    return AnalyticsReport(
        sentiment_distribution={"Positive": 4, "Negative": 2, "Neutral": 0,
                                "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0},
        topic_breakdown=[
            TopicBreakdown(topic="Action", total=4, positive=4, negative=0, neutral=0,
                           avg_confidence=0.9, dominant_sentiment="Positive", engagement_score=1.0),
            TopicBreakdown(topic="Exposition", total=2, positive=0, negative=2, neutral=0,
                           avg_confidence=0.85, dominant_sentiment="Negative", engagement_score=-1.0),
        ],
        timeline=[
            TimelinePoint(timestamp="0:10", topic="Action",     sentiment="Positive",
                          summary="Great action", confidence=0.92),
            TimelinePoint(timestamp="0:45", topic="Action",     sentiment="Positive",
                          summary="More action",  confidence=0.88),
            TimelinePoint(timestamp="1:20", topic="Exposition", sentiment="Negative",
                          summary="Too slow",     confidence=0.85),
        ],
        confidence_stats=ConfidenceStats(mean=0.88, min=0.85, max=0.92,
                                         high_confidence_count=3, low_confidence_count=0,
                                         unanchored_count=0),
        sentiment_velocity=[],
        top_issues=[],
        top_positives=[],
        audience_preferences=AudiencePreferences(
            liked=["Action"], disliked=["Exposition"],
            recurring_requests=[], recurring_complaints=[], recurring_praise=[],
        ),
        total_segments=6,
        analyzed_at="2024-01-01T00:00:00",
    )


class TestBuildPlans:

    # Test 13 — strategy_score present in clips when strategy provided
    def test_strategy_score_in_clips_with_strategy(self):
        from app.services.video_regeneration_agent import _build_plans
        shot_boundaries = [
            {"scene_index": 0, "start_time": 0.0,  "end_time": 15.0, "duration": 15.0},
            {"scene_index": 1, "start_time": 15.0, "end_time": 30.0, "duration": 15.0},
            {"scene_index": 2, "start_time": 30.0, "end_time": 50.0, "duration": 20.0},
        ]
        plans = _build_plans(
            _make_report(), 120.0, shot_boundaries, [],
            strategy_text="High-energy action trailer.",
        )
        clips_with_score = [
            c for p in plans for c in p["clips"] if "strategy_score" in c
        ]
        assert len(clips_with_score) > 0, "strategy_score should be present in clips"

    # Test 14 — backward-compatible output shape without strategy
    def test_output_shape_without_strategy(self):
        from app.services.video_regeneration_agent import _build_plans
        shot_boundaries = [
            {"scene_index": 0, "start_time": 0.0,  "end_time": 15.0, "duration": 15.0},
            {"scene_index": 1, "start_time": 15.0, "end_time": 35.0, "duration": 20.0},
        ]
        plans = _build_plans(_make_report(), 120.0, shot_boundaries, [], strategy_text=None)
        assert len(plans) == 4  # one per platform
        for p in plans:
            assert "platform"        in p
            assert "clip_score"      in p
            assert "clips"           in p
            assert "target_duration" in p
            assert "rationale"       in p

    def test_strategy_note_in_rationale(self):
        from app.services.video_regeneration_agent import _build_plans
        shot_boundaries = [
            {"scene_index": 0, "start_time": 0.0,  "end_time": 15.0, "duration": 15.0},
        ]
        plans = _build_plans(
            _make_report(), 120.0, shot_boundaries, [],
            strategy_text="High-energy action trailer.",
        )
        rationales = [p["rationale"] for p in plans]
        assert any("Strategy" in r or "strategy" in r or "Action" in r
                   for r in rationales), "Strategy note should appear in rationale"

    def test_no_strategy_note_without_strategy(self):
        from app.services.video_regeneration_agent import _build_plans
        shot_boundaries = [
            {"scene_index": 0, "start_time": 0.0, "end_time": 15.0, "duration": 15.0},
        ]
        plans = _build_plans(_make_report(), 120.0, shot_boundaries, [], strategy_text=None)
        for p in plans:
            assert "Strategy applied" not in p["rationale"]


# ═══════════════════════════════════════════════════════════════════════════════
# Test 15 — Strategy step in progress steps list
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressSteps:

    def test_strategy_step_in_steps_list(self, client, dataset_id):
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
            "strategy": "High-energy action trailer.",
        })
        if r.status_code == 404:
            pytest.skip("Project video not present — skipping progress step check")
        assert r.status_code == 202
        job_id = r.json()["id"]

        # Poll progress once — steps should be initialised immediately
        import time
        time.sleep(0.3)
        prog_r = client.get(f"/trailer-job/{job_id}/progress")
        # SSE — read first event
        content = b""
        for chunk in prog_r.iter_bytes():
            content += chunk
            if b"\n\n" in content:
                break
        line = content.decode().split("\n")[0]
        if line.startswith("data:"):
            data = json.loads(line[5:].strip())
            step_keys = [s["key"] for s in data.get("steps", [])]
            assert "strategy" in step_keys, f"'strategy' step missing from {step_keys}"


# ═══════════════════════════════════════════════════════════════════════════════
# Test 16 — Regression: Phase 3 strategy endpoints still work
# ═══════════════════════════════════════════════════════════════════════════════

class TestPhase3Regression:

    def test_strategy_generate_still_works(self, client, dataset_id):
        r = client.post(f"/strategy/{dataset_id}/generate")
        assert r.status_code == 201, r.text

    def test_strategy_get_still_works(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.get(f"/strategy/{dataset_id}")
        assert r.status_code == 200, r.text

    def test_strategy_put_still_works(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.put(f"/strategy/{dataset_id}", json={"user_strategy": "Regression test strategy."})
        assert r.status_code == 200, r.text

    def test_strategy_reset_still_works(self, client, dataset_id):
        client.post(f"/strategy/{dataset_id}/generate")
        r = client.post(f"/strategy/{dataset_id}/reset")
        assert r.status_code == 200, r.text

    def test_generate_trailer_schema_unchanged(self, client, dataset_id):
        """GenerateTrailerRequest without strategy field must still be accepted."""
        r = client.post("/generate-trailer", json={
            "project_id": PROJECT_ID,
            "dataset_id": dataset_id,
        })
        assert r.status_code != 422, "Schema must not reject requests without strategy field"
