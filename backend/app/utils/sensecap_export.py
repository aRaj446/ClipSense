"""
Sensecap CSV export helpers — no FastAPI dependency.

Extracted here so tests can import these pure functions directly without
triggering the APIRouter() initialisation in feedback.py (which fails on
some FastAPI versions in the test environment).

Imported by feedback.py and by the test suite.
"""

import csv
import io
import re

# ── Canonical column schema ───────────────────────────────────────────────────
# Only fields that ClipSense genuinely possesses are included.
# Geography (lat/lon/country/region), engagement (likes/shares/replies),
# and ROI (roi_driver/roi_value_usd) are intentionally omitted — Sensecap
# detects their absence and renders honest "unavailable" states instead of
# fabricating zeros or "Global" placeholders.
#
# source="clipsense" is the mode flag Sensecap reads to activate ClipSense mode.
# video_timestamp is the MM:SS timecode from the original feedback file;
# timestamp is the UTC wall-clock datetime the segment was stored.
SENSECAP_CS_COLUMNS = [
    "source",           # always "clipsense" — Sensecap mode flag
    "dataset_name",     # human-readable dataset label
    "text",             # seg.summary — the actual comment/feedback text
    "timestamp",        # seg.created_at as ISO datetime — used for time-series
    "video_timestamp",  # seg.timestamp (MM:SS timecode) — used for video-position chart
    "sentiment_label",  # Positive | Negative | Neutral (normalised from 7-value ClipSense vocab)
    "sentiment_score",  # direction × confidence, clamped to [-1, 1]
    "theme",            # seg.topic
    "confidence",       # seg.confidence as float [0, 1]
]

_POSITIVE_SENTIMENTS = frozenset({"Positive", "Praise"})
_NEGATIVE_SENTIMENTS = frozenset({"Negative", "Complaint"})


def normalise_sentiment_label(raw: str) -> str:
    """Map ClipSense 7-value sentiment vocabulary to Positive / Negative / Neutral."""
    if raw in _POSITIVE_SENTIMENTS:
        return "Positive"
    if raw in _NEGATIVE_SENTIMENTS:
        return "Negative"
    return "Neutral"


def sentiment_score(label: str, confidence: float) -> float:
    """
    Derive a numeric sentiment score in [-1, 1] from a normalised label and
    ClipSense confidence value.

    Positive → +confidence
    Negative → -confidence
    Neutral  → 0.0

    Handles NaN, missing, and out-of-range confidence safely.
    """
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        conf = 0.0
    if conf != conf:  # NaN check
        conf = 0.0
    conf = max(0.0, min(1.0, conf))  # clamp to [0, 1]
    if label == "Positive":
        return round(conf, 6)
    if label == "Negative":
        return round(-conf, 6)
    return 0.0


def safe_filename(raw: str, fallback: str) -> str:
    """
    Sanitize a user-controlled string for use in a Content-Disposition filename.
    Strips characters that could cause header injection or filesystem issues.
    Falls back to `fallback` if nothing usable remains.
    """
    # Keep only alphanumerics, spaces, hyphens, underscores, dots
    cleaned = re.sub(r"[^\w\s.\-]", "", raw, flags=re.UNICODE).strip()
    # Collapse whitespace to underscores
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned[:64] or fallback


def build_sensecap_csv(segments, dataset_name: str) -> bytes:
    """
    Serialise a list of FeedbackSegmentRecord ORM objects to a UTF-8 CSV
    using SENSECAP_CS_COLUMNS as the canonical schema.

    Returns raw bytes ready for a StreamingResponse.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=SENSECAP_CS_COLUMNS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()

    for seg in segments:
        norm_label = normalise_sentiment_label(seg.sentiment)
        score      = sentiment_score(norm_label, seg.confidence)
        writer.writerow({
            "source":          "clipsense",
            "dataset_name":    dataset_name,
            "text":            seg.summary,
            "timestamp":       seg.created_at.isoformat(),
            "video_timestamp": seg.timestamp or "",
            "sentiment_label": norm_label,
            "sentiment_score": score,
            "theme":           seg.topic,
            "confidence":      round(seg.confidence, 6),
        })

    return buf.getvalue().encode("utf-8")
