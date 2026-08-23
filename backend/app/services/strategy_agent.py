"""
Strategy Agent — Phase 3

Derives a natural-language trailer strategy from a structured AnalyticsReport.
Pure Python — no external API calls, no model inference.
Deterministic given the same report.
"""

from app.schemas.feedback import AnalyticsReport


def generate_strategy(report: AnalyticsReport) -> str:
    """
    Produce a concise, actionable trailer strategy from an AnalyticsReport.

    Considers:
    - positive / negative sentiment distribution
    - top positively and negatively engaged topics
    - sentiment velocity (pacing patterns)
    - audience preferences (liked, disliked, requests, complaints, praise)
    - top issues and top positives
    """
    ap = report.audience_preferences

    # ── Sentiment balance ─────────────────────────────────────────────────────
    dist        = report.sentiment_distribution
    total       = report.total_segments or 1
    pos_count   = dist.get("Positive", 0) + dist.get("Praise", 0)
    neg_count   = dist.get("Negative", 0) + dist.get("Complaint", 0)
    pos_pct     = round(pos_count / total * 100)
    neg_pct     = round(neg_count / total * 100)

    if pos_pct >= 60:
        tone = "The audience responds strongly positively overall."
    elif neg_pct >= 40:
        tone = "The audience has significant negative reactions that must be addressed."
    else:
        tone = "Audience sentiment is mixed, requiring a balanced approach."

    # ── Top performing topics ─────────────────────────────────────────────────
    liked_topics    = ap.liked[:3]
    disliked_topics = ap.disliked[:3]

    focus_line = ""
    if liked_topics:
        focus_line = f"Prioritise content around: {', '.join(liked_topics)}."
    avoid_line = ""
    if disliked_topics:
        avoid_line = f"Minimise or reframe: {', '.join(disliked_topics)}."

    # ── Pacing from sentiment velocity ───────────────────────────────────────
    pacing_line = ""
    if report.sentiment_velocity:
        buckets     = report.sentiment_velocity
        peak_bucket = max(buckets, key=lambda b: b.positive)
        low_bucket  = max(buckets, key=lambda b: b.negative)
        pacing_line = (
            f"Positive engagement peaks around minute {peak_bucket.minute}; "
            f"negative reactions concentrate around minute {low_bucket.minute}. "
            f"Open with high-engagement content and reduce exposure of low-performing segments."
        )

    # ── Audience requests ─────────────────────────────────────────────────────
    request_line = ""
    if ap.recurring_requests:
        top_req = ap.recurring_requests[0]
        request_line = f"The audience has explicitly requested: \"{top_req}\"."

    # ── Top issues ────────────────────────────────────────────────────────────
    issue_line = ""
    if report.top_issues:
        issue_topics = [i.topic for i in report.top_issues[:2]]
        issue_line = f"Address recurring pain points in: {', '.join(issue_topics)}."

    # ── Top positives ─────────────────────────────────────────────────────────
    positive_line = ""
    if report.top_positives:
        pos_topics = [p.topic for p in report.top_positives[:2]]
        positive_line = f"Amplify the strongest positive moments in: {', '.join(pos_topics)}."

    # ── Assemble ──────────────────────────────────────────────────────────────
    parts = [p for p in [
        tone,
        focus_line,
        avoid_line,
        pacing_line,
        positive_line,
        issue_line,
        request_line,
    ] if p]

    return " ".join(parts)
