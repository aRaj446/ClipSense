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


# ── Deterministic clip planner ────────────────────────────────────────────────

def _build_plans(
    analytics: AnalyticsReport,
    video_duration: float,
    shot_boundaries: list[dict],
) -> list[dict]:
    """
    Build one clip plan per platform using engagement-weighted scoring.

    Uses engagement_score from TopicBreakdown (Stage 2 output) to weight
    candidate clips. Higher engagement_score topics get priority.
    Clips are snapped to real scene boundaries from PySceneDetect.
    """
    # Build engagement weight per topic from Stage 2 engagement_score
    # engagement_score is already (positive - negative) / total in [-1.0, 1.0]
    # Multiply by avg_confidence to further weight high-certainty topics
    topic_weight: dict[str, float] = {
        tb.topic: round((tb.engagement_score + 1.0) * tb.avg_confidence, 4)
        for tb in analytics.topic_breakdown
    }

    # Collect timestamped candidates, weighted by topic engagement
    candidates = sorted(
        [p for p in analytics.timeline if p.timestamp],
        key=lambda x: topic_weight.get(x.topic, 0.0) * x.confidence,
        reverse=True,
    )

    # Prefer positive candidates; fall back to all if none exist
    positive_candidates = [c for c in candidates if c.sentiment in _POSITIVE_SENTIMENTS]
    if positive_candidates:
        candidates = positive_candidates + [c for c in candidates if c not in positive_candidates]

    # Deduplicate by timestamp
    seen_ts: set[str] = set()
    deduped = []
    for p in candidates:
        if p.timestamp not in seen_ts:
            seen_ts.add(p.timestamp)
            deduped.append(p)
    candidates = deduped

    plans = []
    for platform, spec in PLATFORM_SPECS.items():
        clips = []
        total = 0.0

        for point in candidates:
            secs = _mm_ss_to_seconds(point.timestamp)
            if secs is None:
                continue
            start, end = _snap_to_scene(secs, shot_boundaries, video_duration)
            clip_len = end - start
            # Enforce 6s minimum at planning stage too
            if clip_len < 6.0 or total + clip_len > spec["max_duration"]:
                continue
            clips.append({
                "start_time": round(start, 2),
                "end_time":   round(end, 2),
                "reason":     f"Audience responded positively to {point.topic} "
                              f"(engagement={topic_weight.get(point.topic, 0):.2f})",
                "topic":      point.topic,
                "sentiment":  point.sentiment,
                "platform":   platform,
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
    ) -> tuple[str | None, TrailerEditingPlan | None, str | None, str | None, float | None, bool, str | None]:

        input_path = self._find_video(project_id)
        if not input_path:
            return None, None, f"Source video not found for project {project_id}", None, None, False, None

        if not video_duration or video_duration <= 0:
            video_duration = _infer_duration(analytics)
            logger.info("VideoRegenerationAgent: inferred duration %.1fs from timeline", video_duration)

        # Stage 1 — parallel pre-processing
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                fut_scenes     = pool.submit(detect_scenes, input_path)
                fut_transcript = pool.submit(transcribe, input_path)
                fut_beats      = pool.submit(detect_beats, input_path)
                shot_boundaries = fut_scenes.result()
                transcript      = fut_transcript.result()
                beat_data       = fut_beats.result()
        except Exception as exc:
            return None, None, f"Pre-processing failed: {exc}", None, None, False, None

        logger.info(
            "VideoRegenerationAgent: pre-processing done — %d shots, %d transcript segs, %.1f BPM",
            len(shot_boundaries), len(transcript["segments"]), beat_data["tempo"],
        )

        # Stage 2 — deterministic clip planning
        plans    = _build_plans(analytics, video_duration, shot_boundaries)
        best_raw = _select_best_plan(plans)

        if not best_raw or not best_raw.get("clips"):
            return None, None, "No suitable clips found in analytics timeline.", None, None, False, None

        platform   = best_raw["platform"]
        clip_score = best_raw["clip_score"]

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

        ok, err = compose(planned, input_path, output_path, transcript, plan.audio_fade_out)
        if not ok:
            return None, plan, err, platform, clip_score, False, None

        return output_path, plan, None, platform, clip_score, False, None

    def _find_video(self, project_id: str) -> str | None:
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")
            if os.path.exists(path):
                return path
        return None
