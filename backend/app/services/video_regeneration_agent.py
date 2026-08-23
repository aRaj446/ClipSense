"""
Video Regeneration Agent — Stage 3

Pipeline:
    Stage 1 — Pre-processing (parallel)
        Scene detection, Whisper transcription, librosa beat detection.

    Stage 2 — Deterministic clip planning
        Engagement-weighted scoring using AnalyticsReport.topic_breakdown
        engagement_score (from Stage 2 AnalyticsAgent). Selects clips from
        timeline sentiment points, snapped to real scene boundaries.
        Produces one plan per platform; best clip_score wins.

    Stage 3 — Clip processing + FFmpeg composition
        process_clips(): sentence-safe boundaries, 6s minimum, mood grouping.
        compose(): colour grading, xfade transitions, audio ducking, loudnorm.

No external API calls. No Gemini. Fully deterministic and offline.
"""

import os
import uuid
import logging
from concurrent.futures import ThreadPoolExecutor

from app.schemas.feedback import AnalyticsReport, TrailerEditingPlan, TrailerClip
from app.utils.storage import UPLOAD_DIR, TRAILERS_DIR
from app.utils.scene_detector import detect_scenes
from app.utils.transcript import transcribe
from app.utils.beat_detector import detect_beats
from app.utils.clip_planner import process_clips
from app.utils.ffmpeg_composer import compose

logger = logging.getLogger(__name__)

PLATFORM_SPECS = {
    "youtube":   {"max_duration": 120},
    "instagram": {"max_duration": 60},
    "tiktok":    {"max_duration": 60},
    "twitter":   {"max_duration": 30},
}

_POSITIVE_SENTIMENTS = {"Positive", "Praise"}


# ── Duration inference ────────────────────────────────────────────────────────

def _mm_ss_to_seconds(ts: str) -> float | None:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def _infer_duration(analytics: AnalyticsReport, fallback: float = 120.0) -> float:
    max_secs = 0.0
    for point in analytics.timeline:
        if point.timestamp:
            secs = _mm_ss_to_seconds(point.timestamp)
            if secs and secs > max_secs:
                max_secs = secs
    return (max_secs + 30.0) if max_secs > 0 else fallback


# ── Scene snapping ────────────────────────────────────────────────────────────

def _snap_to_scene(
    timestamp_s: float,
    shot_boundaries: list[dict],
    video_duration: float,
) -> tuple[float, float]:
    """Snap a timestamp to the nearest scene boundary. Falls back to ±2/+3s window."""
    if not shot_boundaries:
        start = max(0.0, timestamp_s - 2.0)
        end   = min(video_duration, timestamp_s + 3.0)
        return start, end
    best = min(shot_boundaries, key=lambda s: abs(s["start_time"] - timestamp_s))
    return best["start_time"], best["end_time"]


# ── Strategy interpreter ──────────────────────────────────────────────────────

# Keyword groups mapped to topic/mood signals already present in the analytics.
# Each entry: (signal_keywords, topic_boost, sentiment_boost, pacing_short)
#   topic_boost:     added to topic_weight for matching topics
#   sentiment_boost: added when candidate sentiment matches
#   pacing_short:    True = prefer shorter clips (fast pacing intent)
_STRATEGY_RULES: list[tuple[tuple[str, ...], float, float, bool]] = [
    # High energy / action
    (("high-energy", "high energy", "action", "fast", "intense", "explosive", "dynamic"),
     0.6, 0.3, True),
    # Emotional / character
    (("emotional", "emotion", "character", "heartfelt", "touching", "intimate", "personal"),
     0.5, 0.2, False),
    # Reduce slow / exposition
    (("reduce slow", "less slow", "cut slow", "avoid slow", "reduce exposition",
      "less exposition", "cut exposition", "avoid exposition"),
     -0.5, -0.3, True),
    # Suspense / tension
    (("suspense", "tension", "thriller", "mystery", "tense", "gripping"),
     0.4, 0.2, False),
    # Pacing — fast
    (("fast pacing", "fast-paced", "snappy", "quick cuts", "rapid"),
     0.0, 0.0, True),
    # Pacing — slow
    (("slow pacing", "slower", "relaxed", "gentle", "calm"),
     0.0, 0.0, False),
]


def _parse_strategy(strategy_text: str | None) -> dict:
    """
    Parse a free-form strategy string into scoring modifiers.

    Returns a dict:
        topic_boosts:    dict[str, float]  — per-topic additive weight
        sentiment_boost: float             — added when candidate is Positive/Praise
        prefer_short:    bool              — prefer clips < 10s
        raw_labels:      list[str]         — human-readable summary
    """
    result = {
        "topic_boosts":    {},
        "sentiment_boost": 0.0,
        "prefer_short":    False,
        "raw_labels":      [],
    }
    if not strategy_text or not strategy_text.strip():
        return result

    text = strategy_text.lower()
    for keywords, topic_boost, sentiment_boost, pacing_short in _STRATEGY_RULES:
        for kw in keywords:
            if kw in text:
                result["sentiment_boost"] += sentiment_boost
                if pacing_short:
                    result["prefer_short"] = True
                label = kw.replace("-", " ").title()
                if label not in result["raw_labels"]:
                    result["raw_labels"].append(label)
                break  # one match per rule group is enough

    result["sentiment_boost"] = max(-1.0, min(1.0, result["sentiment_boost"]))
    return result


# ── Deterministic clip planner ────────────────────────────────────────────────

def _build_plans(
    analytics: AnalyticsReport,
    video_duration: float,
    shot_boundaries: list[dict],
    beats: list[float],
    strategy_text: str | None = None,
) -> list[dict]:
    """
    Build one clip plan per platform using engagement-weighted scoring.

    When strategy_text is provided, a strategy_score layer is added on top of
    the base engagement weight. The strategy never replaces audience signal —
    it only adjusts the ordering within the existing candidate pool.

    Scoring layers (additive):
        base_weight      = (engagement_score + 1.0) * avg_confidence  [0.0 – 2.0]
        strategy_score   = sentiment_boost when candidate matches strategy intent
                         + prefer_short bonus for clips < 10s
                         (bounded to ±0.5 total so audience signal always dominates)
    """
    from app.utils.beat_detector import find_nearest_beat

    # Parse strategy modifiers (no-op when strategy_text is None)
    strat = _parse_strategy(strategy_text)

    # Build engagement weight per topic from Stage 2 engagement_score
    topic_weight: dict[str, float] = {
        tb.topic: round((tb.engagement_score + 1.0) * tb.avg_confidence, 4)
        for tb in analytics.topic_breakdown
    }

    def _candidate_score(point, clip_len: float) -> float:
        base = topic_weight.get(point.topic, 0.0) * point.confidence
        if not strategy_text:
            return base
        # Strategy layer — bounded to ±0.5 so audience signal always dominates
        s_score = 0.0
        if point.sentiment in _POSITIVE_SENTIMENTS:
            s_score += strat["sentiment_boost"]
        if strat["prefer_short"] and clip_len < 10.0:
            s_score += 0.2
        return base + max(-0.5, min(0.5, s_score))

    # Collect timestamped candidates
    raw_candidates = [p for p in analytics.timeline if p.timestamp]

    # Pre-compute scene windows so we can use clip_len in scoring
    candidate_scenes: list[tuple] = []
    for point in raw_candidates:
        secs = _mm_ss_to_seconds(point.timestamp)
        if secs is None:
            continue
        secs_snapped = find_nearest_beat(secs, beats, tolerance=0.5)
        start, end   = _snap_to_scene(secs_snapped, shot_boundaries, video_duration)
        candidate_scenes.append((point, start, end))

    # Sort by composite score descending
    candidate_scenes.sort(
        key=lambda x: _candidate_score(x[0], x[2] - x[1]),
        reverse=True,
    )

    # Prefer positive candidates first (audience signal > strategy)
    positive_cs = [x for x in candidate_scenes if x[0].sentiment in _POSITIVE_SENTIMENTS]
    other_cs    = [x for x in candidate_scenes if x[0].sentiment not in _POSITIVE_SENTIMENTS]
    candidate_scenes = positive_cs + other_cs

    # Deduplicate by timestamp
    seen_ts: set[str] = set()
    deduped = []
    for item in candidate_scenes:
        ts = item[0].timestamp
        if ts not in seen_ts:
            seen_ts.add(ts)
            deduped.append(item)
    candidate_scenes = deduped

    # Build strategy rationale suffix
    strategy_note = ""
    if strategy_text and strat["raw_labels"]:
        strategy_note = " Strategy applied: " + " · ".join(strat["raw_labels"]) + "."

    plans = []
    for platform, spec in PLATFORM_SPECS.items():
        clips = []
        total = 0.0

        for point, start, end in candidate_scenes:
            clip_len = end - start
            if clip_len < 6.0 or total + clip_len > spec["max_duration"]:
                continue
            score = _candidate_score(point, clip_len)
            clips.append({
                "start_time":       round(start, 2),
                "end_time":         round(end, 2),
                "reason":           (
                    f"Audience responded positively to {point.topic} "
                    f"(score={score:.2f})"
                    + (f"; {strategy_note.strip()}" if strategy_note else "")
                ),
                "topic":            point.topic,
                "sentiment":        point.sentiment,
                "platform":         platform,
                "strategy_score":   round(max(-0.5, min(0.5, score - topic_weight.get(point.topic, 0.0) * point.confidence)), 3),
            })
            total += clip_len

        pos_count  = sum(1 for c in clips if c["sentiment"] in _POSITIVE_SENTIMENTS)
        clip_score = round(pos_count / len(clips), 3) if clips else 0.0

        plans.append({
            "platform":        platform,
            "clip_score":      clip_score,
            "clips":           clips,
            "target_duration": round(total, 2),
            "audio_fade_out":  True,
            "output_format":   "mp4",
            "rationale":       (
                f"Engagement-weighted plan for {platform}: "
                f"{len(clips)} clips selected from highest-scoring topics."
                + strategy_note
            ),
        })

    return plans


def _select_best_plan(plans: list[dict]) -> dict | None:
    """Pick the plan with the highest clip_score. Ties broken by target_duration."""
    valid = [p for p in plans if p.get("clips")]
    if not valid:
        return None
    return max(valid, key=lambda p: (p.get("clip_score", 0), p.get("target_duration", 0)))


# ── Public interface ──────────────────────────────────────────────────────────

class VideoRegenerationAgent:
    """
    Stage 3 — Video Regeneration Agent.

    Fully deterministic — no external API calls.
    Uses engagement_score from Stage 2 AnalyticsAgent to weight clip selection.

    Returns: (output_path, editing_plan, error_message, platform, clip_score,
              gemini_used=False, fallback_warning=None)
    """

    def generate(
        self,
        project_id: str,
        analytics: AnalyticsReport,
        video_duration: float,
        target_duration: float = 60.0,
        job_id: str | None = None,
        strategy_text: str | None = None,
    ) -> tuple[str | None, TrailerEditingPlan | None, str | None, str | None, float | None, bool, str | None]:

        _key = job_id or project_id  # use job_id for progress so SSE reads the right key

        input_path = self._find_video(project_id)
        if not input_path:
            return None, None, f"Source video not found for project {project_id}", None, None, False, None

        if not video_duration or video_duration <= 0:
            video_duration = _infer_duration(analytics)
            logger.info("VideoRegenerationAgent: inferred duration %.1fs from timeline", video_duration)

        # Initialise progress steps (only if not already set by the API layer)
        from app.utils.render_progress import set_progress, init_steps, set_step, get_progress
        _STEPS = [
            {"key": "strategy",   "label": "Loading strategy",        "status": "pending", "percent": 0},
            {"key": "scenes",     "label": "Detecting scenes",         "status": "pending", "percent": 0},
            {"key": "transcript", "label": "Transcribing audio",       "status": "pending", "percent": 0},
            {"key": "beats",      "label": "Analysing beat rhythm",    "status": "pending", "percent": 0},
            {"key": "planning",   "label": "Planning clip selection",  "status": "pending", "percent": 0},
            {"key": "extracting", "label": "Extracting clips",         "status": "pending", "percent": 0},
            {"key": "composing",  "label": "Composing transitions",    "status": "pending", "percent": 0},
            {"key": "normalising","label": "Normalising audio",        "status": "pending", "percent": 0},
        ]
        if not (get_progress(_key) or {}).get("steps"):
            set_progress(_key, "preprocessing", 0, "Starting pipeline", steps=_STEPS)

        # Strategy step — resolve and log before heavy pre-processing
        set_step(_key, "strategy", "active", 0, "Loading trailer strategy…", overall_percent=1)
        if strategy_text and strategy_text.strip():
            strat_parsed = _parse_strategy(strategy_text)
            strat_labels = " · ".join(strat_parsed["raw_labels"]) if strat_parsed["raw_labels"] else "custom strategy"
            set_step(_key, "strategy", "done", 100, f"Strategy loaded: {strat_labels}", overall_percent=2)
            logger.info("VideoRegenerationAgent: strategy loaded — %s", strat_labels)
        else:
            set_step(_key, "strategy", "done", 100, "No strategy — using default scoring", overall_percent=2)
            logger.info("VideoRegenerationAgent: no strategy provided — default scoring")

        # Stage 1 — parallel pre-processing
        set_step(_key, "scenes",     "active", 0, "Detecting shot boundaries…", overall_percent=2)
        set_step(_key, "transcript", "active", 0, "Transcribing audio…")
        set_step(_key, "beats",      "active", 0, "Analysing beat rhythm…")
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                fut_scenes     = pool.submit(detect_scenes, input_path)
                fut_transcript = pool.submit(transcribe, input_path)
                fut_beats      = pool.submit(detect_beats, input_path)
                shot_boundaries = fut_scenes.result()
                set_step(_key, "scenes", "done", 100, f"{len(shot_boundaries)} scenes detected", overall_percent=10)
                transcript      = fut_transcript.result()
                set_step(_key, "transcript", "done", 100, f"{len(transcript['segments'])} segments transcribed", overall_percent=20)
                beat_data       = fut_beats.result()
                set_step(_key, "beats", "done", 100, f"{beat_data['beat_count']} beats at {beat_data['tempo']:.0f} BPM", overall_percent=28)
        except Exception as exc:
            return None, None, f"Pre-processing failed: {exc}", None, None, False, None

        logger.info(
            "VideoRegenerationAgent: pre-processing done — %d shots, %d transcript segs, %.1f BPM",
            len(shot_boundaries), len(transcript["segments"]), beat_data["tempo"],
        )

        # Stage 2 — deterministic clip planning
        set_step(_key, "planning", "active", 0, "Scoring and selecting clips…", overall_percent=30)
        plans    = _build_plans(analytics, video_duration, shot_boundaries, beat_data.get("beats", []), strategy_text=strategy_text)
        best_raw = _select_best_plan(plans)

        if not best_raw or not best_raw.get("clips"):
            return None, None, "No suitable clips found in analytics timeline.", None, None, False, None

        platform   = best_raw["platform"]
        clip_score = best_raw["clip_score"]
        set_step(_key, "planning", "done", 100, f"{len(best_raw['clips'])} clips selected for {platform}", overall_percent=35)

        logger.info(
            "VideoRegenerationAgent: best plan — platform=%s score=%.3f clips=%d",
            platform, clip_score, len(best_raw["clips"]),
        )

        # Stage 3 — clip processing (6s min, sentence-safe, mood grouping)
        planned = process_clips(
            raw_clips=best_raw["clips"],
            transcript=transcript,
            video_duration=video_duration,
            video_path=input_path,
            target_duration=best_raw["target_duration"],
        )
        if not planned:
            return None, None, "No clips remained after processing.", None, None, False, None

        clips = [
            TrailerClip(
                start_time=c.start_time,
                end_time=c.end_time,
                reason=c.reason,
                topic=c.topic,
                sentiment=c.sentiment,
                platform=platform,
                mood_group=c.mood_group,
                transcript_text=c.transcript_text,
            )
            for c in planned
        ]
        plan = TrailerEditingPlan(
            clips=clips,
            target_duration=sum(c.end_time - c.start_time for c in planned),
            audio_fade_out=best_raw["audio_fade_out"],
            output_format=best_raw["output_format"],
            rationale=best_raw["rationale"],
        )

        # Stage 3 — FFmpeg composition
        output_filename = f"{project_id}_{platform}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "VideoRegenerationAgent: composing — platform=%s score=%.3f clips=%d → %s",
            platform, clip_score, len(plan.clips), output_path,
        )

        ok, err = compose(
            planned, input_path, output_path, transcript,
            plan.audio_fade_out,
            job_id=_key,
            beats=beat_data.get("beats", []),
        )
        if not ok:
            return None, plan, err, platform, clip_score, False, None

        return output_path, plan, None, platform, clip_score, False, None

    def _find_video(self, project_id: str) -> str | None:
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")
            if os.path.exists(path):
                return path
        return None
