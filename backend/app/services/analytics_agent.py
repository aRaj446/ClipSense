"""
Analytics Agent — Module 2

Responsibility:
    Consume the structured JSON produced by the Feedback Structuring Agent
    and generate analytics that Power BI or Tableau can directly ingest.

    This agent performs NO cleaning, NO normalization, NO structuring.
    It only reads already-structured FeedbackSegment objects and produces
    aggregated, insight-rich analytics output.

Primary:  Gemini 2.5 Pro — interprets the structured segments and returns
          a rich analytics JSON payload.
Fallback: Pure-Python aggregation — used when GEMINI_API_KEY is not set
          or the Gemini call fails.
"""

import os
import re
import json
import logging
from collections import defaultdict, Counter
from app.schemas.feedback import FeedbackSegment, AnalyticsReport

logger = logging.getLogger(__name__)

_GEMINI_MODEL = "models/gemini-3.1-flash-lite"


def _get_gemini_key() -> str:
    return os.getenv("GEMINI_FREE_API_KEY") or os.getenv("GEMINI_API_KEY", "")

_ANALYTICS_PROMPT = """
You are the Analytics Agent of an AI-powered Video Marketing Optimization Platform.

You receive a structured JSON array of audience feedback segments that have already
been cleaned, normalized, and classified by the Feedback Structuring Agent.

Your ONLY responsibility is to generate analytics from this structured data.

You MUST NOT re-classify, re-clean, or re-structure the input.
You MUST NOT invent data that is not present in the input.
You MUST NOT return recommendations or editing instructions.

========================================
INPUT CONTRACT
========================================

Each segment has:
  - timestamp: "MM:SS" or null
  - topic: one of the allowed topic labels
  - sentiment: one of Positive | Negative | Neutral | Suggestion | Complaint | Praise | Question
  - summary: cleaned one-sentence description
  - confidence: float 0.0–1.0

========================================
OUTPUT CONTRACT
========================================

Return ONLY a valid JSON object with EXACTLY this structure.
No markdown. No explanation. No code fences.

{
  "sentiment_distribution": {
    "Positive": 0,
    "Negative": 0,
    "Neutral": 0,
    "Suggestion": 0,
    "Complaint": 0,
    "Praise": 0,
    "Question": 0
  },
  "topic_breakdown": [
    {
      "topic": "string",
      "total": 0,
      "positive": 0,
      "negative": 0,
      "neutral": 0,
      "avg_confidence": 0.00,
      "dominant_sentiment": "string"
    }
  ],
  "timeline": [
    {
      "timestamp": "MM:SS or null",
      "topic": "string",
      "sentiment": "string",
      "summary": "string",
      "confidence": 0.00
    }
  ],
  "confidence_stats": {
    "mean": 0.00,
    "min": 0.00,
    "max": 0.00,
    "high_confidence_count": 0,
    "low_confidence_count": 0
  },
  "top_issues": [
    {
      "topic": "string",
      "sentiment": "string",
      "count": 0,
      "avg_confidence": 0.00,
      "sample_summary": "string"
    }
  ],
  "top_positives": [
    {
      "topic": "string",
      "sentiment": "string",
      "count": 0,
      "avg_confidence": 0.00,
      "sample_summary": "string"
    }
  ],
  "total_segments": 0,
  "analyzed_at": "ISO8601 datetime string"
}

Rules:
- top_issues: top 5 negative/complaint topics by count
- top_positives: top 5 positive/praise topics by count
- timeline: include ALL segments that have a non-null timestamp, sorted by timestamp ascending
- high_confidence_count: segments with confidence >= 0.80
- low_confidence_count: segments with confidence < 0.60
- analyzed_at: current UTC datetime in ISO 8601

STRUCTURED SEGMENTS:
{segments}
"""


def _extract_json(text: str) -> str:
    """Extract the first complete JSON array or object from a string."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        text = text.strip()
    for start_char, end_char in (('{', '}'), ('[', ']')):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
    return text


def _call_gemini(segments: list[FeedbackSegment]) -> dict | None:
    import sys
    print("Entering Analytics Agent", flush=True, file=sys.stderr)
    try:
        import google.genai as genai
        client = genai.Client(api_key=_get_gemini_key())
        segments_json = json.dumps([s.model_dump() for s in segments], indent=2)
        prompt = _ANALYTICS_PROMPT.replace("{segments}", segments_json)
        print("About to call Gemini", flush=True, file=sys.stderr)
        print("Model:", _GEMINI_MODEL, flush=True, file=sys.stderr)
        print("Key prefix:", _get_gemini_key()[:8], flush=True, file=sys.stderr)
        response = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
        text = response.text.strip()
        text = _extract_json(text)
        return json.loads(text)

    except Exception as exc:
        logger.warning("Analytics Agent Gemini call failed, using fallback: %s", exc)
        return None


# ── Pure-Python fallback ──────────────────────────────────────────────────────

def _python_analytics(segments: list[FeedbackSegment]) -> dict:
    from datetime import datetime, timezone

    sentiment_dist: dict[str, int] = {
        "Positive": 0, "Negative": 0, "Neutral": 0,
        "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0,
    }
    for seg in segments:
        if seg.sentiment in sentiment_dist:
            sentiment_dist[seg.sentiment] += 1

    # Topic breakdown
    topic_map: dict[str, list[FeedbackSegment]] = defaultdict(list)
    for seg in segments:
        topic_map[seg.topic].append(seg)

    topic_breakdown = []
    for topic, segs in topic_map.items():
        pos = sum(1 for s in segs if s.sentiment in ("Positive", "Praise"))
        neg = sum(1 for s in segs if s.sentiment in ("Negative", "Complaint"))
        neu = len(segs) - pos - neg
        avg_conf = round(sum(s.confidence for s in segs) / len(segs), 2)
        dominant = Counter(s.sentiment for s in segs).most_common(1)[0][0]
        topic_breakdown.append({
            "topic": topic, "total": len(segs),
            "positive": pos, "negative": neg, "neutral": neu,
            "avg_confidence": avg_conf, "dominant_sentiment": dominant,
        })
    topic_breakdown.sort(key=lambda x: x["total"], reverse=True)

    # Timeline — only timestamped segments
    timeline = sorted(
        [
            {"timestamp": s.timestamp, "topic": s.topic, "sentiment": s.sentiment,
             "summary": s.summary, "confidence": s.confidence}
            for s in segments if s.timestamp
        ],
        key=lambda x: x["timestamp"] or "",
    )

    # Confidence stats
    confs = [s.confidence for s in segments]
    confidence_stats = {
        "mean": round(sum(confs) / len(confs), 2) if confs else 0.0,
        "min": round(min(confs), 2) if confs else 0.0,
        "max": round(max(confs), 2) if confs else 0.0,
        "high_confidence_count": sum(1 for c in confs if c >= 0.80),
        "low_confidence_count":  sum(1 for c in confs if c < 0.60),
    }

    # Top issues / positives
    neg_topics: dict[str, list[FeedbackSegment]] = defaultdict(list)
    pos_topics: dict[str, list[FeedbackSegment]] = defaultdict(list)
    for seg in segments:
        if seg.sentiment in ("Negative", "Complaint"):
            neg_topics[seg.topic].append(seg)
        elif seg.sentiment in ("Positive", "Praise"):
            pos_topics[seg.topic].append(seg)

    def _top5(topic_segs: dict[str, list[FeedbackSegment]]) -> list[dict]:
        rows = []
        for topic, segs in sorted(topic_segs.items(), key=lambda x: -len(x[1]))[:5]:
            rows.append({
                "topic": topic,
                "sentiment": Counter(s.sentiment for s in segs).most_common(1)[0][0],
                "count": len(segs),
                "avg_confidence": round(sum(s.confidence for s in segs) / len(segs), 2),
                "sample_summary": segs[0].summary,
            })
        return rows

    return {
        "sentiment_distribution": sentiment_dist,
        "topic_breakdown": topic_breakdown,
        "timeline": timeline,
        "confidence_stats": confidence_stats,
        "top_issues": _top5(neg_topics),
        "top_positives": _top5(pos_topics),
        "total_segments": len(segments),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Public interface ──────────────────────────────────────────────────────────

class AnalyticsAgent:
    """
    Module 2 — Analytics Agent.

    Consumes structured FeedbackSegment list produced by the Feedback Structuring Agent.
    Returns an AnalyticsReport ready for Power BI / Tableau ingestion.

    Uses Gemini 2.5 Pro when GEMINI_API_KEY is set.
    Falls back to pure-Python aggregation otherwise.
    """

    def analyze(self, segments: list[FeedbackSegment]) -> AnalyticsReport:
        if _get_gemini_key() and _get_gemini_key() != "your_gemini_api_key_here":
            result = _call_gemini(segments)
            if result is not None:
                logger.info("Analytics Agent: Gemini produced analytics for %d segments", len(segments))
                return AnalyticsReport(**result)
            logger.warning("Analytics Agent: Gemini failed — using Python fallback")

        return AnalyticsReport(**_python_analytics(segments))
