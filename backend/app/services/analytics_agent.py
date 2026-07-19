"""
Analytics Agent — Stage 2

Responsibility:
    Consume structured FeedbackSegment list (from Stage 1) and produce a
    rich AnalyticsReport ready for frontend dashboard and BI tool ingestion.

    This agent performs NO cleaning, NO NLP, NO structuring.
    It only aggregates already-structured FeedbackSegment objects.

Improvements over baseline:
    - engagement_score per topic: (positive - negative) / total → [-1.0, 1.0]
    - unanchored_count in confidence_stats: segments with no timestamp
    - sentiment_velocity: per-minute bucketed pos/neg/net counts
    - sample_summaries: top 3 representative summaries per topic insight
"""

import logging
from collections import defaultdict, Counter
from datetime import datetime, timezone

from app.schemas.feedback import (
    FeedbackSegment,
    AnalyticsReport,
    TopicBreakdown,
    TimelinePoint,
    ConfidenceStats,
    SentimentVelocityBucket,
    TopicInsight,
)

logger = logging.getLogger(__name__)

_POSITIVE_SENTIMENTS = {"Positive", "Praise"}
_NEGATIVE_SENTIMENTS = {"Negative", "Complaint"}


def _ts_to_seconds(ts: str) -> float | None:
    """Convert MM:SS or HH:MM:SS timestamp string to total seconds."""
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def _compute_analytics(segments: list[FeedbackSegment]) -> AnalyticsReport:

    # ── Sentiment distribution ────────────────────────────────────────────────
    sentiment_dist: dict[str, int] = {
        "Positive": 0, "Negative": 0, "Neutral": 0,
        "Suggestion": 0, "Complaint": 0, "Praise": 0, "Question": 0,
    }
    for seg in segments:
        if seg.sentiment in sentiment_dist:
            sentiment_dist[seg.sentiment] += 1

    # ── Topic breakdown ───────────────────────────────────────────────────────
    topic_map: dict[str, list[FeedbackSegment]] = defaultdict(list)
    for seg in segments:
        topic_map[seg.topic].append(seg)

    topic_breakdown: list[TopicBreakdown] = []
    for topic, segs in topic_map.items():
        pos = sum(1 for s in segs if s.sentiment in _POSITIVE_SENTIMENTS)
        neg = sum(1 for s in segs if s.sentiment in _NEGATIVE_SENTIMENTS)
        neu = sum(1 for s in segs if s.sentiment not in _POSITIVE_SENTIMENTS | _NEGATIVE_SENTIMENTS)
        total = len(segs)
        avg_conf = round(sum(s.confidence for s in segs) / total, 3)
        dominant = Counter(s.sentiment for s in segs).most_common(1)[0][0]
        engagement = round((pos - neg) / total, 3)   # [-1.0, 1.0]

        topic_breakdown.append(TopicBreakdown(
            topic=topic,
            total=total,
            positive=pos,
            negative=neg,
            neutral=neu,
            avg_confidence=avg_conf,
            dominant_sentiment=dominant,
            engagement_score=engagement,
        ))

    # Sort by engagement_score descending so best-performing topics appear first
    topic_breakdown.sort(key=lambda t: t.engagement_score, reverse=True)

    # ── Timeline (timestamped segments only, sorted chronologically) ──────────
    timeline = sorted(
        [
            TimelinePoint(
                timestamp=s.timestamp,
                topic=s.topic,
                sentiment=s.sentiment,
                summary=s.summary,
                confidence=s.confidence,
            )
            for s in segments if s.timestamp
        ],
        key=lambda x: x.timestamp or "",
    )

    # ── Confidence stats ──────────────────────────────────────────────────────
    confs = [s.confidence for s in segments]
    unanchored = sum(1 for s in segments if not s.timestamp)
    confidence_stats = ConfidenceStats(
        mean=round(sum(confs) / len(confs), 3) if confs else 0.0,
        min=round(min(confs), 3) if confs else 0.0,
        max=round(max(confs), 3) if confs else 0.0,
        high_confidence_count=sum(1 for c in confs if c >= 0.80),
        low_confidence_count=sum(1 for c in confs if c < 0.60),
        unanchored_count=unanchored,
    )

    # ── Sentiment velocity (per-minute buckets) ───────────────────────────────
    # Bucket each timestamped segment into its video minute
    velocity_map: dict[int, dict[str, int]] = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0})
    for seg in segments:
        if not seg.timestamp:
            continue
        secs = _ts_to_seconds(seg.timestamp)
        if secs is None:
            continue
        minute = int(secs // 60)
        if seg.sentiment in _POSITIVE_SENTIMENTS:
            velocity_map[minute]["positive"] += 1
        elif seg.sentiment in _NEGATIVE_SENTIMENTS:
            velocity_map[minute]["negative"] += 1
        else:
            velocity_map[minute]["neutral"] += 1

    sentiment_velocity = [
        SentimentVelocityBucket(
            minute=minute,
            positive=counts["positive"],
            negative=counts["negative"],
            neutral=counts["neutral"],
            net=counts["positive"] - counts["negative"],
        )
        for minute, counts in sorted(velocity_map.items())
    ]

    # ── Top issues / top positives (top 5 by count, up to 3 summaries each) ──
    neg_topics: dict[str, list[FeedbackSegment]] = defaultdict(list)
    pos_topics: dict[str, list[FeedbackSegment]] = defaultdict(list)
    for seg in segments:
        if seg.sentiment in _NEGATIVE_SENTIMENTS:
            neg_topics[seg.topic].append(seg)
        elif seg.sentiment in _POSITIVE_SENTIMENTS:
            pos_topics[seg.topic].append(seg)

    def _top5(topic_segs: dict[str, list[FeedbackSegment]]) -> list[TopicInsight]:
        rows: list[TopicInsight] = []
        for topic, segs in sorted(topic_segs.items(), key=lambda x: -len(x[1]))[:5]:
            dominant = Counter(s.sentiment for s in segs).most_common(1)[0][0]
            avg_conf = round(sum(s.confidence for s in segs) / len(segs), 3)
            # Pick up to 3 highest-confidence summaries as representative quotes
            top_segs = sorted(segs, key=lambda s: s.confidence, reverse=True)[:3]
            summaries = [s.summary for s in top_segs]
            rows.append(TopicInsight(
                topic=topic,
                sentiment=dominant,
                count=len(segs),
                avg_confidence=avg_conf,
                sample_summaries=summaries,
            ))
        return rows

    return AnalyticsReport(
        sentiment_distribution=sentiment_dist,
        topic_breakdown=topic_breakdown,
        timeline=timeline,
        confidence_stats=confidence_stats,
        sentiment_velocity=sentiment_velocity,
        top_issues=_top5(neg_topics),
        top_positives=_top5(pos_topics),
        total_segments=len(segments),
        analyzed_at=datetime.now(timezone.utc).isoformat(),
    )


# ── Public interface ──────────────────────────────────────────────────────────

class AnalyticsAgent:
    """
    Stage 2 — Analytics Agent.

    Consumes structured FeedbackSegment list from Stage 1.
    Returns an AnalyticsReport ready for frontend and BI tool ingestion.

    Pure Python — no external API calls, no model inference.
    Deterministic and fast regardless of segment count.
    """

    def analyze(self, segments: list[FeedbackSegment]) -> AnalyticsReport:
        report = _compute_analytics(segments)
        logger.info(
            "AnalyticsAgent: %d segments → %d topics, %d velocity buckets, %d timeline points",
            len(segments), len(report.topic_breakdown),
            len(report.sentiment_velocity), len(report.timeline),
        )
        return report
