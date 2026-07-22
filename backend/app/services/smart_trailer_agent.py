"""
Smart Trailer Agent — Stage 4

Pipeline:
    Stage 1 — Comments Structuring
        Parse raw audience comments into FeedbackSegment list via FeedbackStructuringAgent.

    Stage 2 — Sample Trailer Pattern Analysis (deterministic)
        Correlates audience sentiment with sample trailer shot boundaries to extract
        positive/negative editing patterns. Pure Python — no external API calls.

    Stage 3 — Raw Footage Clip Planning (deterministic)
        Selects clips from raw footage using scene boundaries, beat alignment,
        and sentiment-informed scoring. Enforces 6s minimum per clip.

    Stage 4 — Clip Processing + FFmpeg Composition
        Converts plan dicts directly to PlannedClip, classifies mood, composes
        with moviepy CrossFadeIn transitions, loudnorm, and video/audio fade-out.

No external API calls. No Gemini. Fully deterministic and offline.
"""

import os
import csv
import json
import uuid
import logging
import subprocess
import re
from collections import Counter

from app.schemas.feedback import (
    FeedbackSegment,
    SmartTrailerAnalysis,
    TrailerEditingPlan,
    TrailerClip,
)
from app.services.feedback_structuring_agent import FeedbackStructuringAgent
from app.utils.storage import TRAILERS_DIR
from app.utils.scene_detector import detect_scenes
from app.utils.transcript import transcribe
from app.utils.beat_detector import detect_beats
from app.utils.clip_planner import classify_clips_by_mood
from app.utils.ffmpeg_composer import compose

logger = logging.getLogger(__name__)

MIN_NO_SPEECH = 3.0  # seconds — minimum duration for non-dialogue clips

_POSITIVE_SENTIMENTS = {"Positive", "Praise"}
_NEGATIVE_SENTIMENTS = {"Negative", "Complaint"}


# ── FFmpeg duration probe ─────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

FFMPEG = _get_ffmpeg()


def _get_video_duration(video_path: str) -> float:
    try:
        result = subprocess.run(
            [FFMPEG, "-i", video_path],
            capture_output=True, text=True, timeout=15,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


# ── Comments file parser ──────────────────────────────────────────────────────

def _read_comments_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                lines = []
                for item in data:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, dict):
                        for key in ("text", "comment", "body", "content", "message"):
                            if key in item:
                                lines.append(str(item[key]))
                                break
                return "\n".join(lines)
            return str(data)
        elif ext == ".csv":
            lines = []
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for key in ("text", "comment", "body", "content", "message"):
                        if key in row:
                            lines.append(row[key])
                            break
                    else:
                        lines.append(" ".join(row.values()))
            return "\n".join(lines)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as exc:
        logger.warning("SmartTrailerAgent: failed to read comments file: %s", exc)
        return ""


# ── Stage 2: Deterministic sample trailer analysis ───────────────────────────

def _ts_to_seconds(ts: str) -> float | None:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def _analyse_sample_trailer(
    segments: list[FeedbackSegment],
    sample_duration: float,
    shot_boundaries: list[dict],
) -> dict:
    """
    Correlate audience sentiment with sample trailer shot boundaries to extract
    positive and negative editing patterns. Pure Python — no external calls.
    """
    pos = [s for s in segments if s.sentiment in _POSITIVE_SENTIMENTS]
    neg = [s for s in segments if s.sentiment in _NEGATIVE_SENTIMENTS]

    # Map each timestamped segment to its nearest shot boundary
    def nearest_shot(ts_secs: float) -> dict | None:
        if not shot_boundaries:
            return None
        return min(shot_boundaries, key=lambda sc: abs(sc["start_time"] - ts_secs))

    # Identify which shot indices drove positive vs negative reactions
    pos_shot_indices: list[int] = []
    neg_shot_indices: list[int] = []
    for seg in segments:
        if not seg.timestamp:
            continue
        secs = _ts_to_seconds(seg.timestamp)
        if secs is None:
            continue
        shot = nearest_shot(secs)
        if shot is None:
            continue
        if seg.sentiment in _POSITIVE_SENTIMENTS:
            pos_shot_indices.append(shot["scene_index"])
        elif seg.sentiment in _NEGATIVE_SENTIMENTS:
            neg_shot_indices.append(shot["scene_index"])

    # Derive positive patterns from most-praised topics and shot durations
    pos_topic_counts = Counter(s.topic for s in pos)
    neg_topic_counts = Counter(s.topic for s in neg)
    top_pos_topics   = [t for t, _ in pos_topic_counts.most_common(4)]
    top_neg_topics   = [t for t, _ in neg_topic_counts.most_common(3)]

    # Characterise shot durations at positive moments
    pos_durations = []
    for idx in set(pos_shot_indices):
        shots = [sc for sc in shot_boundaries if sc["scene_index"] == idx]
        if shots:
            pos_durations.append(shots[0]["duration"])

    avg_pos_dur = round(sum(pos_durations) / len(pos_durations), 1) if pos_durations else 0.0
    pacing_desc = "fast-paced cuts" if avg_pos_dur < 4.0 else "sustained longer shots"

    positive_patterns = [f"Positive audience response to {t} segments" for t in top_pos_topics]
    if avg_pos_dur > 0:
        positive_patterns.append(f"Editing rhythm of ~{avg_pos_dur}s per shot ({pacing_desc}) drove engagement")
    if not positive_patterns:
        positive_patterns = ["Strong opening moments", "High-energy scene transitions"]

    negative_patterns = [f"Negative audience response to {t} segments" for t in top_neg_topics]
    if not negative_patterns:
        negative_patterns = ["Slow pacing sections", "Abrupt scene changes"]

    return {
        "sentiment_summary": (
            f"Audience showed {len(pos)} positive and {len(neg)} negative reactions "
            f"across {len(segments)} total comments on the sample trailer."
        ),
        "positive_patterns":    positive_patterns,
        "negative_patterns":    negative_patterns,
        "top_scene_categories": top_pos_topics or ["Action", "Dialogue"],
        "influence_explanation": (
            f"New trailer will prioritise {', '.join(top_pos_topics[:2] or ['high-engagement'])} scenes "
            f"and avoid {', '.join(top_neg_topics[:2] or ['low-engagement'])} segments."
        ),
    }


# ── Stage 3: Deterministic raw footage clip planner ──────────────────────────

def _plan_clips_from_raw(
    analysis: dict,
    raw_duration: float,
    target_duration: float,
    raw_shots: list[dict],
    raw_beats: dict,
    transcript: dict,
) -> dict:
    """
    Select clips from raw footage using:
    - Scene boundaries from PySceneDetect (prefer whole scenes)
    - Beat alignment from librosa (snap start/end to nearest strong beat)
    - Sentiment-informed topic scoring (prefer scenes matching positive patterns)
    - 6s minimum clip duration enforced at selection stage
    """
    from app.utils.beat_detector import find_nearest_beat
    strong_beats = raw_beats.get("strong_beats", [])
    all_beats    = raw_beats.get("beats", [])
    pos_topics   = set(analysis.get("top_scene_categories", []))
    neg_patterns = analysis.get("negative_patterns", [])

    # Score each scene
    def scene_score(scene: dict) -> float:
        score = 0.0
        # Check if this scene has dialogue
        from app.utils.clip_planner import get_transcript_text
        clip_text = get_transcript_text(scene["start_time"], scene["end_time"], transcript)
        has_speech = bool(clip_text.strip())
        # Dialogue scenes are prioritised — they carry the story
        if has_speech:
            score += 2.0
        # Prefer scenes on or near a strong beat (secondary to dialogue)
        if any(abs(scene["start_time"] - b) <= 0.5 for b in strong_beats):
            score += 0.5
        # Prefer scenes whose duration matches positive pacing
        if 6.0 <= scene["duration"] <= 20.0:
            score += 0.5
        # Penalise scenes matching negative patterns
        for pat in neg_patterns:
            if "slow" in pat.lower() and scene["duration"] > 20.0:
                score -= 0.5
        return score

    # Sort scenes by score descending, filter to >= 6s
    scored = sorted(
        [sc for sc in raw_shots if sc["duration"] >= 6.0],
        key=scene_score,
        reverse=True,
    )

    MAX_CLIPS = 7
    clips = []
    total = 0.0
    pos_topics_list = sorted(pos_topics)  # deterministic order
    for scene in scored:
        if total >= target_duration or len(clips) >= MAX_CLIPS:
            break

        # Check for dialogue in this scene
        from app.utils.clip_planner import get_transcript_text, get_dialogue_window
        clip_text = get_transcript_text(scene["start_time"], scene["end_time"], transcript)
        has_speech = bool(clip_text.strip())

        if has_speech:
            # Dialogue takes priority — expand to cover the full dialogue window,
            # never snap to beat (beat snapping would cut mid-sentence)
            d_start, d_end = get_dialogue_window(
                scene["start_time"], scene["end_time"], transcript
            )
            snapped_start = min(scene["start_time"], d_start) if d_start is not None else scene["start_time"]
            snapped_end   = max(scene["end_time"],   d_end)   if d_end   is not None else scene["end_time"]
        else:
            # No dialogue — snap start to nearest beat for musical alignment
            snapped_start = find_nearest_beat(scene["start_time"], all_beats, tolerance=0.4)
            snapped_end   = scene["end_time"]
            if snapped_end - snapped_start < MIN_NO_SPEECH:
                snapped_start = scene["start_time"]

        snapped_start = max(0.0, snapped_start)
        snapped_end   = min(raw_duration, snapped_end)

        # Trim last clip to fit target exactly (respect dialogue minimum)
        remaining = target_duration - total
        clip_dur  = snapped_end - snapped_start
        min_dur   = MIN_NO_SPEECH if not has_speech else clip_dur  # never trim dialogue
        if clip_dur > remaining and remaining >= min_dur:
            snapped_end = snapped_start + remaining
        top_topic = (pos_topics_list[0] if pos_topics_list else "General") if has_speech else "General"
        sentiment = "Positive" if scene_score(scene) >= 1.0 else ("Neutral" if scene_score(scene) >= 0.5 else "Negative")

        clips.append({
            "start_time": round(snapped_start, 3),
            "end_time":   round(snapped_end, 3),
            "reason":     f"Scene selected by beat-alignment and sentiment scoring (score={scene_score(scene):.1f})",
            "topic":      top_topic,
            "sentiment":  sentiment,
            "platform":   "youtube",
        })
        total += snapped_end - snapped_start

    # If no scored scenes qualify, fall back to all valid scenes in order
    if not clips:
        for scene in raw_shots:
            if scene["duration"] < 6.0:
                continue
            if total + scene["duration"] > target_duration:
                break
            clips.append({
                "start_time": scene["start_time"],
                "end_time":   scene["end_time"],
                "reason":     "Scene boundary fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += scene["duration"]

    # Last resort: evenly sampled 8s windows if no scene data
    if not clips:
        step = max(10.0, raw_duration / 10)
        t = 0.0
        while t + 6.0 <= raw_duration and total + 6.0 <= target_duration:
            end = min(t + 8.0, raw_duration)
            clips.append({
                "start_time": round(t, 2),
                "end_time":   round(end, 2),
                "reason":     "Evenly sampled fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += end - t
            t += step

    clip_score = round(min(1.0, len(clips) / max(1, len(raw_shots))) * 0.8, 3)

    return {
        "platform":        "youtube",
        "clip_score":      clip_score,
        "clips":           clips,
        "target_duration": round(total, 2),
        "audio_fade_out":  True,
        "output_format":   "mp4",
        "rationale":       (
            f"Deterministic plan: {len(clips)} clips selected from raw footage "
            f"using beat alignment and sentiment-informed scene scoring."
        ),
        "scene_selection_rationale": [
            {"clip_index": i, "confidence": clip_score, "reason": c["reason"]}
            for i, c in enumerate(clips)
        ],
    }


# ── Public interface ──────────────────────────────────────────────────────────

class SmartTrailerAgent:
    """
    Smart Trailer Agent — generates a new trailer from raw footage guided by
    sample trailer analysis and audience sentiment from comments.

    Fully deterministic — no external API calls.

    Returns: (output_path, editing_plan, analysis_report, error_message,
              platform, clip_score, gemini_used=False, fallback_warning=None)
    """

    def __init__(self):
        self._structuring_agent = FeedbackStructuringAgent()

    def generate(
        self,
        raw_footage_path: str,
        sample_trailer_path: str,
        comments_path: str,
        job_id: str,
    ) -> tuple[str | None, TrailerEditingPlan | None, SmartTrailerAnalysis | None,
               str | None, str | None, float | None, bool, str | None]:

        # ── Stage 1: Parse comments ───────────────────────────────────────────
        from app.utils.render_progress import set_progress, init_steps, set_step
        _STEPS = [
            {"key": "comments",   "label": "Parsing audience comments",  "status": "pending", "percent": 0},
            {"key": "sample",     "label": "Analysing sample trailer",    "status": "pending", "percent": 0},
            {"key": "scenes",     "label": "Detecting scenes",            "status": "pending", "percent": 0},
            {"key": "transcript", "label": "Transcribing audio",          "status": "pending", "percent": 0},
            {"key": "beats",      "label": "Analysing beat rhythm",       "status": "pending", "percent": 0},
            {"key": "planning",   "label": "Planning clip selection",     "status": "pending", "percent": 0},
            {"key": "extracting", "label": "Extracting clips",            "status": "pending", "percent": 0},
            {"key": "composing",  "label": "Composing transitions",       "status": "pending", "percent": 0},
            {"key": "normalising","label": "Normalising audio",           "status": "pending", "percent": 0},
        ]
        # Only initialise if steps not already set by the API layer
        from app.utils.render_progress import get_progress as _gp
        if not (_gp(job_id) or {}).get("steps"):
            set_progress(job_id, "parsing", 0, "Starting pipeline", steps=_STEPS)
            init_steps(job_id, _STEPS)

        set_step(job_id, "comments", "active", 0, "Parsing audience comments…", overall_percent=2)
        raw_text = _read_comments_file(comments_path)
        if not raw_text.strip():
            return None, None, None, "Comments file is empty or unreadable.", None, None, False, None

        segments = self._structuring_agent.parse(raw_text)
        if not segments:
            return None, None, None, "No feedback segments could be extracted from comments.", None, None, False, None

        set_step(job_id, "comments", "done", 100, f"{len(segments)} segments parsed", overall_percent=8)
        logger.info("SmartTrailerAgent: parsed %d comment segments", len(segments))

        # ── Stage 2: Analyse sample trailer ──────────────────────────────────
        set_step(job_id, "sample", "active", 0, "Analysing sample trailer…", overall_percent=10)
        try:
            sample_duration = _get_video_duration(sample_trailer_path)
            sample_shots    = detect_scenes(sample_trailer_path)
        except Exception as exc:
            logger.warning("SmartTrailerAgent: sample trailer pre-processing failed: %s", exc)
            sample_duration = 120.0
            sample_shots    = []

        if sample_duration <= 0:
            sample_duration = 120.0

        analysis_raw = _analyse_sample_trailer(segments, sample_duration, sample_shots)
        set_step(job_id, "sample", "done", 100, f"{len(sample_shots)} shots analysed", overall_percent=18)
        logger.info("SmartTrailerAgent: Stage 2 analysis complete — %d positive patterns", len(analysis_raw["positive_patterns"]))

        # ── Stage 3: Pre-process raw footage (sequential — CPU-bound tasks) ──
        set_step(job_id, "scenes",     "active", 0, "Detecting shot boundaries…", overall_percent=20)
        try:
            raw_duration = _get_video_duration(raw_footage_path)
            if raw_duration <= 0:
                return None, None, None, "Could not determine raw footage duration.", None, None, False, None

            raw_shots = detect_scenes(raw_footage_path)
            set_step(job_id, "scenes", "done", 100, f"{len(raw_shots)} scenes detected", overall_percent=30)

            set_step(job_id, "transcript", "active", 0, "Transcribing audio…", overall_percent=31)
            raw_transcript = transcribe(raw_footage_path)
            set_step(job_id, "transcript", "done", 100, f"{len(raw_transcript['segments'])} segments transcribed", overall_percent=40)

            set_step(job_id, "beats", "active", 0, "Analysing beat rhythm…", overall_percent=41)
            raw_beats = detect_beats(raw_footage_path)
            set_step(job_id, "beats", "done", 100, f"{raw_beats['beat_count']} beats at {raw_beats['tempo']:.0f} BPM", overall_percent=48)

        except Exception as exc:
            return None, None, None, f"Raw footage pre-processing failed: {exc}", None, None, False, None

        logger.info(
            "SmartTrailerAgent: raw footage — %.1fs, %d shots, %d transcript segs, %.1f BPM",
            raw_duration, len(raw_shots), len(raw_transcript["segments"]), raw_beats["tempo"],
        )

        target_duration = max(60.0, min(120.0, round(raw_duration * 0.25)))

        # ── Stage 3: Plan clips ───────────────────────────────────────────────
        set_step(job_id, "planning", "active", 0, "Scoring and selecting clips…", overall_percent=50)
        plan_raw = _plan_clips_from_raw(
            analysis_raw, raw_duration, target_duration,
            raw_shots, raw_beats, raw_transcript,
        )

        if not plan_raw.get("clips"):
            return None, None, None, "No clips could be planned from raw footage.", None, None, False, None

        set_step(job_id, "planning", "done", 100, f"{len(plan_raw['clips'])} clips planned", overall_percent=55)
        platform   = plan_raw["platform"]
        clip_score = plan_raw["clip_score"]

        logger.info("SmartTrailerAgent: Stage 3 plan — %d clips, score=%.3f", len(plan_raw["clips"]), clip_score)

        # Build SmartTrailerAnalysis
        analysis = SmartTrailerAnalysis(
            sentiment_summary=analysis_raw["sentiment_summary"],
            positive_patterns=analysis_raw["positive_patterns"],
            negative_patterns=analysis_raw["negative_patterns"],
            top_scene_categories=analysis_raw["top_scene_categories"],
            influence_explanation=analysis_raw["influence_explanation"],
            scene_selection_rationale=plan_raw["scene_selection_rationale"],
        )

        # ── Stage 4: Convert plan → PlannedClip + mood classification only ──
        # Do NOT run process_clips — the planner already selected, bounded, and
        # budgeted every clip. Re-running boundary expansion + overlap removal
        # on score-sorted (non-chronological) clips destroys most of them.
        from app.utils.clip_planner import PlannedClip, get_transcript_text
        planned: list[PlannedClip] = [
            PlannedClip(
                start_time=float(c["start_time"]),
                end_time=float(c["end_time"]),
                reason=c.get("reason", ""),
                topic=c.get("topic", "General"),
                sentiment=c.get("sentiment", "Positive"),
                platform=c.get("platform", "youtube"),
                transcript_text=get_transcript_text(
                    float(c["start_time"]), float(c["end_time"]), raw_transcript
                ),
            )
            for c in plan_raw["clips"]
        ]
        # Sort chronologically so FFmpeg extracts in timeline order
        planned.sort(key=lambda c: c.start_time)
        # Mood classification only — for transition selection
        planned = classify_clips_by_mood(planned, raw_footage_path)
        # Force last clip to action mood for energetic ending
        if planned:
            planned[-1].mood_group = "action"

        if not planned:
            return None, None, analysis, "No clips remained after processing.", platform, clip_score, False, None

        logger.info("SmartTrailerAgent: %d clips ready (%.1fs total)",
                    len(planned), sum(c.end_time - c.start_time for c in planned))

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
            audio_fade_out=plan_raw["audio_fade_out"],
            output_format=plan_raw["output_format"],
            rationale=plan_raw["rationale"],
        )

        output_filename = f"smart_{job_id}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "SmartTrailerAgent: composing — platform=%s score=%.3f clips=%d → %s",
            platform, clip_score, len(plan.clips), output_path,
        )

        ok, err = compose(
            planned, raw_footage_path, output_path, raw_transcript,
            plan.audio_fade_out,
            job_id=job_id,
            beats=raw_beats.get("beats", []),
        )
        if not ok:
            return None, plan, analysis, err, platform, clip_score, False, None

        return output_path, plan, analysis, None, platform, clip_score, False, None
