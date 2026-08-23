"""
Tests for the Sensecap CSV export — GET /export-dataset/{dataset_id}/csv

Pure helper functions are imported directly from app.utils.sensecap_export
(no FastAPI dependency). The endpoint itself is tested via build_sensecap_csv
which contains all the serialisation logic.

Covers:
    1.  SENSECAP_CS_COLUMNS — stable order (regression guard)
    2.  _normalise_sentiment_label — all 7 ClipSense values
    3.  _sentiment_score — Positive gives positive score
    4.  _sentiment_score — Negative gives negative score
    5.  _sentiment_score — Neutral gives 0.0
    6.  _sentiment_score — NaN confidence handled
    7.  _sentiment_score — confidence > 1 clamped
    8.  _sentiment_score — confidence < 0 clamped
    9.  _sentiment_score — non-numeric confidence handled
    10. _sentiment_score — zero confidence
    11. _sentiment_score — result always within [-1, 1]
    12. _safe_filename — strips dangerous characters
    13. _safe_filename — collapses whitespace to underscores
    14. _safe_filename — falls back when nothing usable remains
    15. _safe_filename — Unicode word characters preserved
    16. _safe_filename — max length enforced
    17. build_sensecap_csv — correct row count
    18. build_sensecap_csv — correct column order
    19. build_sensecap_csv — source always "clipsense"
    20. build_sensecap_csv — text maps from summary
    21. build_sensecap_csv — theme maps from topic
    22. build_sensecap_csv — video_timestamp preserved (MM:SS)
    23. build_sensecap_csv — video_timestamp empty when null
    24. build_sensecap_csv — timestamp is ISO datetime string
    25. build_sensecap_csv — sentiment_label normalised for all 7 values
    26. build_sensecap_csv — sentiment_score sign correct
    27. build_sensecap_csv — confidence preserved
    28. build_sensecap_csv — dataset_name in every row
    29. build_sensecap_csv — Unicode text preserved
    30. build_sensecap_csv — commas in text do not break CSV structure
    31. build_sensecap_csv — newlines in text do not break CSV structure
    32. build_sensecap_csv — quotes in text do not break CSV structure
    33. build_sensecap_csv — no geography columns present
    34. build_sensecap_csv — no engagement columns present
    35. build_sensecap_csv — no ROI columns present

Run with:
    cd backend
    set PYTHONPATH=C:\\Users\\7000039334\\Documents\\Gearshift\\Clipsense\\backend
    pytest tests/test_sensecap_csv_export.py -v
"""

import csv
import io
import sys
import os
from datetime import datetime, timezone
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.utils.sensecap_export import (
    SENSECAP_CS_COLUMNS,
    normalise_sentiment_label,
    sentiment_score,
    safe_filename,
    build_sensecap_csv,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_segment(
    position=0,
    timestamp="00:34",
    topic="Action",
    sentiment="Positive",
    summary="Great shot",
    confidence=0.92,
    created_at=None,
):
    seg = MagicMock()
    seg.position       = position
    seg.timestamp      = timestamp
    seg.topic          = topic
    seg.sentiment      = sentiment
    seg.summary        = summary
    seg.confidence     = confidence
    seg.created_at     = created_at or datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    return seg


def _parse_csv(csv_bytes: bytes) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))


# ── SENSECAP_CS_COLUMNS stability ─────────────────────────────────────────────

def test_sensecap_cs_columns_stable_order():
    """Regression guard — column order must not change silently."""
    assert SENSECAP_CS_COLUMNS == [
        "source",
        "dataset_name",
        "text",
        "timestamp",
        "video_timestamp",
        "sentiment_label",
        "sentiment_score",
        "theme",
        "confidence",
        "ap_liked",
        "ap_disliked",
        "ap_recurring_requests",
        "ap_recurring_complaints",
        "ap_recurring_praise",
    ]


# ── normalise_sentiment_label ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("Positive",   "Positive"),
    ("Praise",     "Positive"),
    ("Negative",   "Negative"),
    ("Complaint",  "Negative"),
    ("Neutral",    "Neutral"),
    ("Question",   "Neutral"),
    ("Suggestion", "Neutral"),
    ("unknown",    "Neutral"),
    ("",           "Neutral"),
])
def test_normalise_sentiment_label(raw, expected):
    assert normalise_sentiment_label(raw) == expected


# ── sentiment_score ───────────────────────────────────────────────────────────

def test_sentiment_score_positive():
    assert sentiment_score("Positive", 0.9) == pytest.approx(0.9)


def test_sentiment_score_negative():
    assert sentiment_score("Negative", 0.8) == pytest.approx(-0.8)


def test_sentiment_score_neutral():
    assert sentiment_score("Neutral", 0.75) == 0.0


def test_sentiment_score_nan_confidence():
    assert sentiment_score("Positive", float("nan")) == 0.0


def test_sentiment_score_confidence_above_one_clamped():
    assert sentiment_score("Positive", 1.5) == pytest.approx(1.0)


def test_sentiment_score_confidence_below_zero_clamped():
    # Negative confidence is nonsensical; clamp to 0 before applying sign
    assert sentiment_score("Negative", -0.3) == 0.0


def test_sentiment_score_non_numeric_confidence():
    assert sentiment_score("Positive", "not-a-number") == 0.0


def test_sentiment_score_zero_confidence():
    assert sentiment_score("Positive", 0.0) == 0.0
    assert sentiment_score("Negative", 0.0) == 0.0


def test_sentiment_score_within_bounds():
    for label in ("Positive", "Negative", "Neutral"):
        score = sentiment_score(label, 0.5)
        assert -1.0 <= score <= 1.0


# ── safe_filename ─────────────────────────────────────────────────────────────

def test_safe_filename_strips_dangerous_chars():
    result = safe_filename("my dataset; rm -rf /", "fallback")
    assert ";" not in result
    assert "/" not in result
    assert result


def test_safe_filename_collapses_whitespace():
    result = safe_filename("my   dataset  name", "fallback")
    assert "  " not in result
    assert "_" in result


def test_safe_filename_fallback_when_empty():
    assert safe_filename(";;;###", "fallback") == "fallback"


def test_safe_filename_unicode_preserved():
    result = safe_filename("Café Feedback", "fallback")
    assert result and result != "fallback"


def test_safe_filename_max_length():
    assert len(safe_filename("a" * 200, "fallback")) <= 64


# ── build_sensecap_csv — structure ────────────────────────────────────────────

def test_build_csv_correct_row_count():
    segs  = [_make_segment(position=i) for i in range(5)]
    rows  = _parse_csv(build_sensecap_csv(segs, "Test"))
    assert len(rows) == 5


def test_build_csv_correct_column_order():
    segs   = [_make_segment()]
    raw    = build_sensecap_csv(segs, "Test").decode("utf-8")
    header = next(csv.reader(io.StringIO(raw)))
    assert header == SENSECAP_CS_COLUMNS


def test_build_csv_source_always_clipsense():
    segs = [_make_segment(sentiment="Positive"), _make_segment(sentiment="Negative")]
    for row in _parse_csv(build_sensecap_csv(segs, "Test")):
        assert row["source"] == "clipsense"


# ── build_sensecap_csv — field mapping ───────────────────────────────────────

def test_build_csv_text_maps_from_summary():
    seg  = _make_segment(summary="Loved the opening scene")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert rows[0]["text"] == "Loved the opening scene"


def test_build_csv_theme_maps_from_topic():
    seg  = _make_segment(topic="Character Development")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert rows[0]["theme"] == "Character Development"


def test_build_csv_video_timestamp_preserved():
    seg  = _make_segment(timestamp="01:23")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert rows[0]["video_timestamp"] == "01:23"


def test_build_csv_video_timestamp_empty_when_null():
    seg  = _make_segment(timestamp=None)
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert rows[0]["video_timestamp"] == ""


def test_build_csv_timestamp_is_iso_datetime():
    dt   = datetime(2024, 3, 15, 9, 30, 0, tzinfo=timezone.utc)
    seg  = _make_segment(created_at=dt)
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert "2024-03-15" in rows[0]["timestamp"]


def test_build_csv_sentiment_label_normalised_all_values():
    cases = [
        ("Positive",   "Positive"),
        ("Praise",     "Positive"),
        ("Negative",   "Negative"),
        ("Complaint",  "Negative"),
        ("Neutral",    "Neutral"),
        ("Question",   "Neutral"),
        ("Suggestion", "Neutral"),
    ]
    for raw, expected in cases:
        seg  = _make_segment(sentiment=raw)
        rows = _parse_csv(build_sensecap_csv([seg], "Test"))
        assert rows[0]["sentiment_label"] == expected, f"Failed for {raw}"


def test_build_csv_sentiment_score_positive():
    seg  = _make_segment(sentiment="Positive", confidence=0.9)
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert float(rows[0]["sentiment_score"]) == pytest.approx(0.9)


def test_build_csv_sentiment_score_negative():
    seg  = _make_segment(sentiment="Negative", confidence=0.8)
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert float(rows[0]["sentiment_score"]) == pytest.approx(-0.8)


def test_build_csv_confidence_preserved():
    seg  = _make_segment(confidence=0.77)
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert float(rows[0]["confidence"]) == pytest.approx(0.77)


def test_build_csv_dataset_name_in_every_row():
    segs = [_make_segment(position=i) for i in range(3)]
    for row in _parse_csv(build_sensecap_csv(segs, "Trailer Feedback Q1")):
        assert row["dataset_name"] == "Trailer Feedback Q1"


# ── build_sensecap_csv — text edge cases ─────────────────────────────────────

def test_build_csv_unicode_text_preserved():
    seg  = _make_segment(summary="Loved the café scene — très bien! 日本語テスト")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert "café" in rows[0]["text"]
    assert "日本語" in rows[0]["text"]


def test_build_csv_commas_in_text_do_not_break_structure():
    seg  = _make_segment(summary="Great, but the ending, however, was weak")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert len(rows) == 1
    assert "Great, but" in rows[0]["text"]


def test_build_csv_newlines_in_text_do_not_break_structure():
    seg  = _make_segment(summary="Line one\nLine two\nLine three")
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert len(rows) == 1
    assert "Line one" in rows[0]["text"]


def test_build_csv_quotes_in_text_do_not_break_structure():
    seg  = _make_segment(summary='He said "amazing" and I agree')
    rows = _parse_csv(build_sensecap_csv([seg], "Test"))
    assert len(rows) == 1
    assert "amazing" in rows[0]["text"]


# ── build_sensecap_csv — absent columns ──────────────────────────────────────

def test_build_csv_no_geography_columns():
    rows = _parse_csv(build_sensecap_csv([_make_segment()], "Test"))
    for col in ("lat", "lon", "country", "country_code", "region"):
        assert col not in rows[0], f"Column '{col}' must not be present"


def test_build_csv_no_engagement_columns():
    rows = _parse_csv(build_sensecap_csv([_make_segment()], "Test"))
    for col in ("likes", "shares", "replies", "engagement"):
        assert col not in rows[0], f"Column '{col}' must not be present"


def test_build_csv_no_roi_columns():
    rows = _parse_csv(build_sensecap_csv([_make_segment()], "Test"))
    for col in ("roi_driver", "roi_value_usd"):
        assert col not in rows[0], f"Column '{col}' must not be present"
