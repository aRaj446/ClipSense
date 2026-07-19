"""
Smart Trailer Agent

Pipeline:
    Stage 1 — Comments Structuring
        Parse raw audience comments into FeedbackSegment list via FeedbackStructuringAgent.

    Stage 2 — Sample Trailer Analysis (Gemini)
        Correlates audience sentiment with sample trailer editing patterns.

    Stage 3 — Raw Footage Clip Plan (Gemini)
        Proposes clip plan from raw footage guided by Stage 2 analysis.

    Stage 4 — Clip Processing + FFmpeg Composition
        - Sentence-safe boundaries (never cut mid-speech)
        - 6-second minimum clip duration
        - Mood/energy grouping via librosa
        - xfade crossfade transitions
        - Colour grading + audio ducking + loudnorm

Gemini NEVER touches video files.
FFmpeg NEVER makes creative decisions.
"""

import os
import re
import csv
import json
import uuid
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor

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
from app.utils.clip_planner import process_clips
from app.utils.ffmpeg_composer import compose

logger = logging.getLogger(__name__)

_GEMINI_MODEL_FREE = "models/gemini-3.1-flash-lite"
_GEMINI_MODEL_PAID = "models/gemini-3.1-flash-lite"


def _get_free_key() -> str:
    return os.getenv("GEMINI_FREE_API_KEY") or os.getenv("GEMINI_API_KEY", "")


def _get_paid_key() -> str:
    return os.getenv("GEMINI_PAID_API_KEY") or os.getenv("GEMINI_API_KEY", "")


def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _get_ffmpeg()


def _get_video_duration(video_path: str) -> float:
    cmd = [FFMPEG, "-i", video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except subprocess.TimeoutExpired:
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


# ── Stage 2 prompt ────────────────────────────────────────────────────────────

_SAMPLE_ANALYSIS_PROMPT = """
You are the Smart Trailer Agent of an AI-powered Video Marketing Optimization Platform.

You have been given:
1. Structured audience feedback segments from a sample trailer (with sentiment, topics, timestamps).
2. The sample trailer duration in seconds.

Your job is to analyse the editing patterns of the sample trailer by correlating audience
sentiment with the timeline of comments. Extract what editing decisions drove positive reactions
and what drove negative reactions.

========================================
OUTPUT CONTRACT
========================================

Return ONLY a valid JSON object. No markdown. No code fences.

{{
  "sentiment_summary": "2-3 sentence overall audience sentiment summary",
  "positive_patterns": [
    "editing pattern or scene type that drove positive reactions — be specific"
  ],
  "negative_patterns": [
    "editing pattern or scene type that drove negative reactions — be specific"
  ],
  "top_scene_categories": [
    "scene category with highest engagement"
  ],
  "influence_explanation": "2-3 sentences explaining how these patterns will guide the new trailer"
}}

Rules:
- positive_patterns: list 3-6 specific patterns
- negative_patterns: list 2-4 specific patterns
- top_scene_categories: list 3-5 categories

========================================
SAMPLE TRAILER DURATION (seconds): {sample_duration}

SAMPLE TRAILER SHOT BOUNDARIES (detected by PySceneDetect):
{shot_boundaries}

AUDIENCE FEEDBACK SEGMENTS:
{segments}
========================================
"""

# ── Stage 3 prompt ────────────────────────────────────────────────────────────

_CLIP_PLAN_PROMPT = """
You are the Smart Trailer Agent of an AI-powered Video Marketing Optimization Platform.
Generate a clip plan from RAW FOOTAGE ONLY.

OUTPUT CONTRACT — Return ONLY a valid JSON object. No markdown. No code fences.

{{
  "platform": "youtube",
  "clip_score": 0.0,
  "clips": [
    {{
      "start_time": 0.0,
      "end_time": 0.0,
      "reason": "one sentence",
      "topic": "scene category label",
      "sentiment": "Positive",
      "platform": "youtube"
    }}
  ],
  "target_duration": 0.0,
  "audio_fade_out": true,
  "output_format": "mp4",
  "rationale": "2-3 sentence explanation",
  "scene_selection_rationale": [
    {{
      "clip_index": 0,
      "confidence": 0.0,
      "reason": "why this moment was chosen"
    }}
  ]
}}

Rules:
- start_time and end_time in SECONDS within raw footage duration ({raw_duration}s)
- Each clip at least 6 seconds long
- Total duration must not exceed {target_duration}s
- clip_score: 0.0-1.0

========================================
RAW FOOTAGE DURATION (seconds): {raw_duration}
TARGET TRAILER DURATION (seconds): {target_duration}

RAW FOOTAGE SHOT BOUNDARIES:
{raw_shot_boundaries}

SPEECH TRANSCRIPT:
{transcript_segments}

AUDIO BEAT TIMESTAMPS:
{beat_data}

SAMPLE TRAILER ANALYSIS:
{analysis}
========================================
"""


def _trim_for_prompt(shot_boundaries: list[dict], transcript: dict, beat_data: dict) -> tuple[list, list, dict]:
    shots    = shot_boundaries[:60]
    segments = transcript.get("segments", [])[:80]
    strong   = beat_data.get("strong_beats", [])[:60]
    return shots, segments, {"tempo": beat_data.get("tempo", 0.0), "strong_beats": strong}


def _call_gemini_analysis(segments: list[FeedbackSegment], sample_duration: float, shot_boundaries: list[dict]) -> dict:
    import google.genai as genai
    client = genai.Client(api_key=_get_free_key())
    prompt = _SAMPLE_ANALYSIS_PROMPT.format(
        sample_duration=round(sample_duration, 1),
        shot_boundaries=json.dumps(shot_boundaries[:60], indent=2),
        segments=json.dumps([s.model_dump() for s in segments[:100]], indent=2),
    )
    response = client.models.generate_content(model=_GEMINI_MODEL_FREE, contents=prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _call_gemini_clip_plan(
    analysis: dict, raw_duration: float, target_duration: float,
    raw_shot_boundaries: list[dict], transcript: dict, beat_data: dict,
) -> dict:
    import google.genai as genai
    client = genai.Client(api_key=_get_paid_key())
    shots, segments, trimmed_beats = _trim_for_prompt(raw_shot_boundaries, transcript, beat_data)
    prompt = _CLIP_PLAN_PROMPT.format(
        raw_duration=round(raw_duration, 1),
        target_duration=round(target_duration, 1),
        raw_shot_boundaries=json.dumps(shots, indent=2),
        transcript_segments=json.dumps(segments, indent=2),
        beat_data=json.dumps(trimmed_beats, indent=2),
        analysis=json.dumps(analysis, indent=2),
    )
    response = client.models.generate_content(model=_GEMINI_MODEL_PAID, contents=prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


# ── Fallbacks ─────────────────────────────────────────────────────────────────

def _fallback_analysis(segments: list[FeedbackSegment]) -> dict:
    pos    = [s for s in segments if s.sentiment in ("Positive", "Praise")]
    neg    = [s for s in segments if s.sentiment in ("Negative", "Complaint")]
    topics = list({s.topic for s in pos[:5]})
    return {
        "sentiment_summary":    f"Audience showed {len(pos)} positive and {len(neg)} negative reactions.",
        "positive_patterns":    [f"Positive audience response to {t}" for t in topics[:4]] or ["Strong opening moments"],
        "negative_patterns":    [f"Negative response to {s.topic}" for s in neg[:2]] or ["Slow pacing sections"],
        "top_scene_categories": topics[:4] or ["Action", "Dialogue"],
        "influence_explanation": "New trailer will prioritise scenes matching positive audience reactions.",
    }


def _fallback_clip_plan(raw_duration: float, target_duration: float, raw_shots: list[dict], raw_beats: dict) -> dict:
    clips        = []
    total        = 0.0
    strong_beats = set(raw_beats.get("strong_beats", []))

    if raw_shots:
        for scene in raw_shots:
            if total + scene["duration"] > target_duration:
                break
            if scene["duration"] < 6.0:
                continue
            on_beat = any(abs(scene["start_time"] - b) <= 0.5 for b in strong_beats) if strong_beats else True
            if not on_beat and clips:
                continue
            clips.append({"start_time": scene["start_time"], "end_time": scene["end_time"],
                          "reason": "Scene boundary fallback clip", "topic": "General",
                          "sentiment": "Positive", "platform": "youtube"})
            total += scene["duration"]
        if not clips:
            for scene in raw_shots:
                if total + scene["duration"] > target_duration:
                    break
                if scene["duration"] < 6.0:
                    continue
                clips.append({"start_time": scene["start_time"], "end_time": scene["end_time"],
                              "reason": "Scene boundary fallback clip", "topic": "General",
                              "sentiment": "Positive", "platform": "youtube"})
                total += scene["duration"]
    else:
        step = max(10.0, raw_duration / 10)
        t    = 0.0
        while t + 6.0 <= raw_duration and total + 6.0 <= target_duration:
            start   = t
            end     = min(start + 8.0, raw_duration)
            clips.append({"start_time": round(start, 2), "end_time": round(end, 2),
                          "reason": "Evenly sampled fallback clip", "topic": "General",
                          "sentiment": "Positive", "platform": "youtube"})
            total += end - start
            t     += step

    return {
        "platform": "youtube", "clip_score": 0.5, "clips": clips,
        "target_duration": round(total, 2), "audio_fade_out": True,
        "output_format": "mp4", "rationale": "Fallback: scene-boundary clips from raw footage.",
        "scene_selection_rationale": [
            {"clip_index": i, "confidence": 0.5, "reason": "Scene boundary fallback"}
            for i in range(len(clips))
        ],
    }


# ── Public interface ──────────────────────────────────────────────────────────

class SmartTrailerAgent:
    """
    Smart Trailer Agent — generates a new trailer from raw footage guided by
    sample trailer analysis and audience sentiment from comments.

    Returns: (output_path, editing_plan, analysis_report, error_message,
              platform, clip_score, gemini_used, fallback_warning)
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
        raw_text = _read_comments_file(comments_path)
        if not raw_text.strip():
            return None, None, None, "Comments file is empty or unreadable.", None, None, False, None

        segments = self._structuring_agent.parse(raw_text)
        if not segments:
            return None, None, None, "No feedback segments could be extracted from comments.", None, None, False, None

        logger.info("SmartTrailerAgent: parsed %d comment segments", len(segments))

        # ── Stage 2: Analyse sample trailer ──────────────────────────────────
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_dur   = pool.submit(_get_video_duration, sample_trailer_path)
            fut_shots = pool.submit(detect_scenes, sample_trailer_path)
            sample_duration = fut_dur.result()
            sample_shots    = fut_shots.result()

        if sample_duration <= 0:
            sample_duration = 120.0
            logger.warning("SmartTrailerAgent: could not read sample trailer duration, using 120s")

        gemini_used      = False
        fallback_warning: str | None = None

        try:
            analysis_raw = _call_gemini_analysis(segments, sample_duration, sample_shots)
            gemini_used  = True
            logger.info("SmartTrailerAgent: Stage 2 Gemini analysis complete")
        except Exception as exc:
            logger.warning("SmartTrailerAgent: Stage 2 Gemini failed (%s) — using fallback analysis", exc)
            analysis_raw     = _fallback_analysis(segments)
            fallback_warning = "Stage 2 used fallback analysis (Gemini unavailable)"

        # ── Stage 3: Generate clip plan from raw footage ──────────────────────
        with ThreadPoolExecutor(max_workers=4) as pool:
            fut_dur        = pool.submit(_get_video_duration, raw_footage_path)
            fut_shots      = pool.submit(detect_scenes, raw_footage_path)
            fut_transcript = pool.submit(transcribe, raw_footage_path)
            fut_beats      = pool.submit(detect_beats, raw_footage_path)
            raw_duration   = fut_dur.result()
            raw_shots      = fut_shots.result()
            raw_transcript = fut_transcript.result()
            raw_beats      = fut_beats.result()

        if raw_duration <= 0:
            return None, None, None, "Could not determine raw footage duration.", None, None, gemini_used, fallback_warning

        logger.info(
            "SmartTrailerAgent: raw footage — %.1fs, %d shots, %d transcript segs, %.1f BPM",
            raw_duration, len(raw_shots), len(raw_transcript["segments"]), raw_beats["tempo"],
        )

        target_duration = max(30.0, min(120.0, round(raw_duration * 0.15)))

        try:
            plan_raw    = _call_gemini_clip_plan(analysis_raw, raw_duration, target_duration, raw_shots, raw_transcript, raw_beats)
            gemini_used = True
            logger.info("SmartTrailerAgent: Stage 3 Gemini clip plan complete — %d clips", len(plan_raw.get("clips", [])))
        except Exception as exc:
            logger.warning("SmartTrailerAgent: Stage 3 Gemini failed (%s) — using fallback clip plan", exc)
            plan_raw         = _fallback_clip_plan(raw_duration, target_duration, raw_shots, raw_beats)
            fallback_warning = (fallback_warning or "") + " | Stage 3 used fallback clip plan"

        if not plan_raw.get("clips"):
            return None, None, None, "No clips could be planned from raw footage.", None, None, gemini_used, fallback_warning

        platform   = plan_raw.get("platform", "youtube")
        clip_score = plan_raw.get("clip_score")

        # Build SmartTrailerAnalysis
        analysis = SmartTrailerAnalysis(
            sentiment_summary=analysis_raw.get("sentiment_summary", ""),
            positive_patterns=analysis_raw.get("positive_patterns", []),
            negative_patterns=analysis_raw.get("negative_patterns", []),
            top_scene_categories=analysis_raw.get("top_scene_categories", []),
            influence_explanation=analysis_raw.get("influence_explanation", ""),
            scene_selection_rationale=plan_raw.get("scene_selection_rationale", []),
        )

        # ── Stage 4: Clip processing + FFmpeg composition ─────────────────────
        planned = process_clips(
            raw_clips=plan_raw["clips"],
            transcript=raw_transcript,
            video_duration=raw_duration,
            video_path=raw_footage_path,
            target_duration=target_duration,
        )
        if not planned:
            return None, None, analysis, "No clips remained after processing.", platform, clip_score, gemini_used, fallback_warning

        logger.info("SmartTrailerAgent: %d clips after processing", len(planned))

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
            audio_fade_out=plan_raw.get("audio_fade_out", True),
            output_format=plan_raw.get("output_format", "mp4"),
            rationale=plan_raw.get("rationale", ""),
        )

        output_filename = f"smart_{job_id}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "SmartTrailerAgent: composing — platform=%s score=%.2f clips=%d → %s",
            platform, clip_score or 0, len(plan.clips), output_path,
        )

        ok, err = compose(planned, raw_footage_path, output_path, raw_transcript, plan.audio_fade_out)
        if not ok:
            return None, plan, analysis, err, platform, clip_score, gemini_used, fallback_warning

        return output_path, plan, analysis, None, platform, clip_score, gemini_used, fallback_warning
