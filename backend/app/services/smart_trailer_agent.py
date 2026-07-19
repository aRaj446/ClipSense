"""
Smart Trailer Agent

Pipeline:
    Stage 1 — Comments Structuring
        Parse raw audience comments (JSON/CSV/TXT) into FeedbackSegment list
        using the existing FeedbackStructuringAgent.

    Stage 2 — Sample Trailer Analysis (Gemini)
        Gemini analyses the sample trailer's editing metadata (duration, scene
        count inferred from comments timestamps) and correlates audience
        sentiment with editing patterns to extract:
          - positive editing patterns (what drove good reactions)
          - negative editing patterns (what drove bad reactions)
          - top scene categories by engagement
          - overall sentiment summary

    Stage 3 — Raw Footage Scene Detection (Gemini)
        Gemini analyses the raw footage duration and the sentiment-informed
        editing style to propose a clip plan using ONLY the raw footage as
        source material.

    Stage 4 — FFmpeg Execution
        FFmpeg extracts and concatenates the selected clips from raw footage.
        Gemini never touches the video file directly.

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
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from app.schemas.feedback import (
    FeedbackSegment,
    SmartTrailerAnalysis,
    TrailerEditingPlan,
    TrailerClip,
)
from app.services.feedback_structuring_agent import FeedbackStructuringAgent
from app.utils.storage import TRAILERS_DIR
from app.utils.scene_detector import detect_scenes
from app.utils.transcript import transcribe, find_safe_cut_point
from app.utils.beat_detector import detect_beats, find_nearest_beat

logger = logging.getLogger(__name__)

_GEMINI_MODEL_FREE = "models/gemini-3.1-flash-lite"
_GEMINI_MODEL_PAID = "models/gemini-3.1-flash-lite"


def _get_free_key() -> str:
    return os.getenv("GEMINI_FREE_API_KEY") or os.getenv("GEMINI_API_KEY", "")


def _get_paid_key() -> str:
    return os.getenv("GEMINI_PAID_API_KEY") or os.getenv("GEMINI_API_KEY", "")


# ── FFmpeg helpers (reuse same pattern as VideoRegenerationAgent) ─────────────

def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

FFMPEG = _get_ffmpeg()


def _run_ffmpeg(cmd: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0, result.stderr
    except subprocess.TimeoutExpired:
        return False, "FFmpeg timed out after 300 seconds"
    except FileNotFoundError:
        return False, f"FFmpeg not found at '{cmd[0]}'. Run: pip install imageio[ffmpeg]"
    except Exception as exc:
        return False, str(exc)


def _get_video_duration(video_path: str) -> float:
    """Extract video duration in seconds using FFmpeg."""
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
    """Read comments file (.json, .csv, .txt) and return as a single text block."""
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
                        # accept common keys: text, comment, body, content
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
                        # fallback: join all values
                        lines.append(" ".join(row.values()))
            return "\n".join(lines)

        else:  # .txt
            with open(path, "r", encoding="utf-8") as f:
                return f.read()

    except Exception as exc:
        logger.warning("SmartTrailerAgent: failed to read comments file: %s", exc)
        return ""


# ── Stage 2 prompt — Sample Trailer Analysis ─────────────────────────────────

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
- positive_patterns: list 3-6 specific patterns (e.g. "Fast cuts during action sequences at 0:30-0:45")
- negative_patterns: list 2-4 specific patterns
- top_scene_categories: list 3-5 categories
- Be specific — reference timestamps and topics from the segments where possible

========================================
SAMPLE TRAILER DURATION (seconds): {sample_duration}

SAMPLE TRAILER SHOT BOUNDARIES (detected by PySceneDetect):
{shot_boundaries}

AUDIENCE FEEDBACK SEGMENTS:
{segments}
========================================

Instructions for using shot boundaries:
- Each entry gives the exact start_time, end_time, duration, and MM:SS timestamp of a detected cut in the sample trailer.
- Correlate audience feedback timestamps with these shot boundaries to identify which specific cuts, scene lengths, and edit rhythms drove positive or negative reactions.
- Use scene duration patterns (e.g. rapid short cuts vs long sustained shots) to characterise the editing style at each moment.
- Reference specific scene_index values in your positive_patterns and negative_patterns so Stage 3 can replicate or avoid those structural choices.
"""


# ── Stage 3 prompt — Raw Footage Clip Plan ────────────────────────────────────

_CLIP_PLAN_PROMPT = """
You are an expert cinematic video editor. Your objective is to create a seamless, emotionally engaging, professional-quality video from multiple video clips and an accompanying music track. The final edit should feel like a single, cohesive film rather than a collection of separate clips.
Editing Guidelines
Analyze every video clip for content, quality, dialogue, facial expressions, emotions, camera movement, lighting, and scene context before making any edits.
Select the best takes and remove blurry, shaky, repetitive, or low-quality footage unless it is intentionally required for storytelling.
Group clips with similar emotions, mood, and narrative context together. For example, joyful moments should transition into other joyful moments, emotional scenes into emotional scenes, and high-energy scenes into high-energy scenes. Avoid abrupt emotional shifts unless they are clearly motivated by the story.
Arrange the clips to create a logical and engaging narrative with smooth progression between scenes.
Stitch clips together seamlessly using natural cuts, match cuts, motion matching, speed ramps, whip transitions, or subtle cross dissolves only when appropriate. Avoid transitions that feel distracting or overused.
Maintain visual continuity by matching subject movement, camera direction, framing, lighting, and color between consecutive clips whenever possible.
Never cut off dialogue abruptly. Ensure every spoken sentence begins and ends naturally. Preserve complete words, phrases, and emotional delivery. If a cut occurs during speech, move the edit point or use an alternate angle or B-roll so the dialogue remains continuous and natural.
Preserve conversational flow by ensuring speakers are not interrupted mid-sentence or mid-expression. Leave natural pauses where needed.
Synchronize cuts, transitions, speed ramps, and key visual moments with the beat, rhythm, and structure of the background music. Major visual changes should align with musical accents, drops, or transitions.
Let the music guide the pacing. Increase editing tempo during energetic sections and slow the pace during softer or emotional moments.
Adjust clip speed only when it improves storytelling or synchronization with the music. Slow motion and speed ramps should feel smooth and intentional.
Apply consistent color correction and grading so all clips share a unified cinematic look.
Stabilize footage when necessary while preserving natural camera movement.
Balance exposure, white balance, contrast, and saturation across all clips to avoid noticeable visual inconsistencies.
Remove unnecessary pauses, repeated shots, and dead space while preserving the natural rhythm of conversations and emotional moments.
Blend ambient audio with the background music where appropriate. Use smooth audio fades and avoid sudden changes in volume.
Ensure every scene transition feels motivated by either the story, the emotion, the dialogue, or the music.
If multiple aspect ratios are needed (16:9, 9:16, or 1:1), intelligently reframe each shot to keep the main subject in focus.
Maintain consistent pacing and emotional continuity from beginning to end so the viewer remains engaged throughout.
Quality Checks Before Finalizing
Verify that clips with similar emotions are grouped together unless a deliberate emotional contrast is intended.
Confirm that no dialogue is cut off abruptly and every spoken line sounds complete and natural.
Ensure there are no awkward jump cuts, missing reactions, or incomplete actions.
Check that every cut and transition feels smooth and intentional.
Confirm that edits are synchronized with the music's beat and emotional progression.
Verify consistent color, exposure, and audio levels across the entire video.
Ensure the final video feels like one continuous, professionally edited production rather than multiple stitched-together clips.
Goal: Deliver a polished, cinematic edit with seamless visual transitions, coherent emotional flow, uninterrupted dialogue, and precise music synchronization that feels natural, immersive, and professionally crafted.

You are also the Smart Trailer Agent of an AI-powered Video Marketing Optimization Platform. You must generate a new trailer clip plan using ONLY the raw footage as source material.
You have been given:
1. The raw footage duration in seconds.
2. An analysis of what editing patterns drove positive/negative audience reactions in a sample trailer, derived from structured audience sentiment feedback.
3. The target trailer duration.

Apply the cinematic editing guidelines above when proposing the clip plan, and additionally use the sentiment analysis data below to inform every creative decision:
- Use positive_patterns from the sample trailer analysis to identify editing styles and scene types that drove good audience reactions — replicate these in the new trailer.
- Use negative_patterns to identify what drove poor reactions — avoid these editing choices entirely.
- Use top_scene_categories to prioritise scene types with the highest audience engagement as anchor moments in the edit.
- Use sentiment_summary to understand the overall emotional tone the audience responded to and calibrate the trailer's emotional arc to match or improve upon it.
- Use scene_selection_rationale confidence scores to weight clip selection: prefer moments with higher confidence scores when choosing between candidate clips from the raw footage.

Your job is to propose a clip plan from the raw footage that:
- Adopts the positive editing patterns from the sample trailer analysis
- Avoids the negative patterns
- Maintains narrative continuity
- Optimises for audience engagement and retention

========================================
OUTPUT CONTRACT
========================================

Return ONLY a valid JSON object. No markdown. No code fences.

{{
  "platform": "youtube",
  "clip_score": 0.0,
  "clips": [
    {{
      "start_time": 0.0,
      "end_time": 0.0,
      "reason": "one sentence explaining why this clip was selected",
      "topic": "scene category label",
      "sentiment": "Positive",
      "platform": "youtube"
    }}
  ],
  "target_duration": 0.0,
  "audio_fade_out": true,
  "output_format": "mp4",
  "rationale": "2-3 sentence explanation of the overall editing strategy",
  "scene_selection_rationale": [
    {{
      "clip_index": 0,
      "confidence": 0.0,
      "reason": "why this specific moment from raw footage was chosen"
    }}
  ]
}}

Rules:
- start_time and end_time are in SECONDS (float), within raw footage duration ({raw_duration}s)
- Each clip must be at least 3 seconds long
- Total duration must not exceed {target_duration}s
- Order clips for maximum engagement: strong opening, strong close
- clip_score: 0.0-1.0 reflecting how well the plan adopts positive patterns
- scene_selection_rationale must have one entry per clip

========================================
RAW FOOTAGE DURATION (seconds): {raw_duration}
TARGET TRAILER DURATION (seconds): {target_duration}

RAW FOOTAGE SHOT BOUNDARIES (detected by PySceneDetect):
{raw_shot_boundaries}

RAW FOOTAGE SPEECH TRANSCRIPT (Whisper word-level timestamps):
{transcript_segments}

RAW FOOTAGE AUDIO BEAT TIMESTAMPS (librosa beat tracker):
{beat_data}

SAMPLE TRAILER ANALYSIS:
{analysis}
========================================

Instructions for using raw footage shot boundaries:
- Each entry is a real detected scene in the raw footage with its exact start_time, end_time, and duration.
- You MUST select start_time and end_time values from within these detected scene boundaries — do not invent timestamps that fall mid-scene unless you are intentionally trimming a scene.
- Prefer selecting whole scenes or contiguous groups of scenes rather than arbitrary sub-clips.
- Use the scene durations to replicate the pacing patterns identified as positive in the sample trailer analysis.
- Avoid scenes whose duration or position matches patterns identified as negative in the sample trailer analysis.

Instructions for using the speech transcript:
- Each segment entry has start, end, and text — a complete spoken sentence or phrase.
- NEVER set a clip end_time that falls mid-sentence. Always extend or trim the end_time to the nearest segment end boundary.
- NEVER set a clip start_time that cuts into an ongoing sentence. Always start at or before the segment start boundary.
- Prefer clips that contain complete, meaningful spoken phrases — these are more engaging than silent or mid-sentence clips.
- Use the transcript text to identify content-rich moments and prioritise them in the edit.

Instructions for using beat timestamps:
- tempo gives the overall BPM of the raw footage audio track.
- strong_beats lists every 4th beat (downbeats) — use these as anchor points for major scene transitions and clip boundaries.
- Align clip start_time and end_time values to the nearest strong_beat where possible without violating speech boundaries.
"""


def _trim_for_prompt(shot_boundaries: list[dict], transcript: dict, beat_data: dict) -> tuple[list, list, dict]:
    shots = shot_boundaries[:60]
    segments = transcript.get("segments", [])[:80]
    strong = beat_data.get("strong_beats", [])[:60]
    trimmed_beats = {"tempo": beat_data.get("tempo", 0.0), "strong_beats": strong}
    return shots, segments, trimmed_beats


def _call_gemini_analysis(
    segments: list[FeedbackSegment],
    sample_duration: float,
    shot_boundaries: list[dict],
) -> dict | None:
    import sys
    print("Entering Smart Trailer Agent", flush=True, file=sys.stderr)
    import google.genai as genai
    client = genai.Client(api_key=_get_free_key())
    prompt = _SAMPLE_ANALYSIS_PROMPT.format(
        sample_duration=round(sample_duration, 1),
        shot_boundaries=json.dumps(shot_boundaries[:60], indent=2),
        segments=json.dumps([s.model_dump() for s in segments[:100]], indent=2),
    )
    print("About to call Gemini", flush=True, file=sys.stderr)
    print("Model:", _GEMINI_MODEL_FREE, flush=True, file=sys.stderr)
    print("Key prefix:", _get_free_key()[:8], flush=True, file=sys.stderr)
    response = client.models.generate_content(model=_GEMINI_MODEL_FREE, contents=prompt)
    text = response.text.strip()
    logger.info("SmartTrailerAgent Stage2: Gemini raw response (first 500 chars): %s", text[:500])
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


def _call_gemini_clip_plan(
    analysis: dict,
    raw_duration: float,
    target_duration: float,
    raw_shot_boundaries: list[dict],
    transcript: dict,
    beat_data: dict,
) -> dict | None:
    import sys
    print("Entering Smart Trailer Agent — Stage 3 clip plan", flush=True, file=sys.stderr)
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
    print("About to call Gemini", flush=True, file=sys.stderr)
    print("Model:", _GEMINI_MODEL_PAID, flush=True, file=sys.stderr)
    print("Key prefix:", _get_paid_key()[:8], flush=True, file=sys.stderr)
    response = client.models.generate_content(model=_GEMINI_MODEL_PAID, contents=prompt)
    text = response.text.strip()
    logger.info("SmartTrailerAgent Stage3: Gemini raw response (first 500 chars): %s", text[:500])
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return json.loads(text)


# ── Fallback clip plan ────────────────────────────────────────────────────────

def _fallback_analysis(segments: list[FeedbackSegment]) -> dict:
    """Pure-Python fallback when Gemini is unavailable for Stage 2."""
    pos = [s for s in segments if s.sentiment in ("Positive", "Praise")]
    neg = [s for s in segments if s.sentiment in ("Negative", "Complaint")]
    topics = list({s.topic for s in pos[:5]})
    return {
        "sentiment_summary": f"Audience showed {len(pos)} positive and {len(neg)} negative reactions.",
        "positive_patterns": [f"Positive audience response to {t}" for t in topics[:4]] or ["Strong opening moments"],
        "negative_patterns": [f"Negative response to {s.topic}" for s in neg[:2]] or ["Slow pacing sections"],
        "top_scene_categories": topics[:4] or ["Action", "Dialogue"],
        "influence_explanation": "New trailer will prioritise scenes matching positive audience reactions.",
    }


def _fallback_clip_plan(
    raw_duration: float,
    target_duration: float,
    raw_shots: list[dict],
    raw_beats: dict,
) -> dict:
    """Pure-Python fallback clip plan when Gemini is unavailable for Stage 3.
    Selects clips aligned to detected scene boundaries and beat timestamps."""
    clips = []
    total = 0.0
    strong_beats = set(raw_beats.get("strong_beats", []))

    if raw_shots:
        # Walk detected scenes; include scenes that start on or near a strong beat
        for scene in raw_shots:
            if total + scene["duration"] > target_duration:
                break
            if scene["duration"] < 3.0:
                continue
            # Prefer scenes whose start aligns with a strong beat (within 0.5s)
            on_beat = any(abs(scene["start_time"] - b) <= 0.5 for b in strong_beats) if strong_beats else True
            if not on_beat and len(clips) > 0:
                continue  # skip off-beat scenes unless we have nothing yet
            clips.append({
                "start_time": scene["start_time"],
                "end_time":   scene["end_time"],
                "reason":     "Scene boundary aligned fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += scene["duration"]
        # If beat-filtering left us with nothing, fall back to all valid scenes
        if not clips:
            for scene in raw_shots:
                if total + scene["duration"] > target_duration:
                    break
                if scene["duration"] < 3.0:
                    continue
                clips.append({
                    "start_time": scene["start_time"],
                    "end_time":   scene["end_time"],
                    "reason":     "Scene boundary fallback clip",
                    "topic":      "General",
                    "sentiment":  "Positive",
                    "platform":   "youtube",
                })
                total += scene["duration"]
    else:
        # No scene data — evenly sample with beat-aligned windows
        step = max(10.0, raw_duration / 10)
        t = 0.0
        while t + 5.0 <= raw_duration and total + 5.0 <= target_duration:
            # Snap start to nearest strong beat if available
            start = t
            if strong_beats:
                nearest = min(strong_beats, key=lambda b: abs(b - t))
                if abs(nearest - t) <= 1.0:
                    start = nearest
            end = min(start + 5.0, raw_duration)
            clips.append({
                "start_time": round(start, 2),
                "end_time":   round(end, 2),
                "reason":     "Evenly sampled beat-aligned fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += end - start
            t += step

    return {
        "platform": "youtube",
        "clip_score": 0.5,
        "clips": clips,
        "target_duration": round(total, 2),
        "audio_fade_out": True,
        "output_format": "mp4",
        "rationale": "Fallback: scene-boundary and beat-aligned clips from raw footage.",
        "scene_selection_rationale": [
            {"clip_index": i, "confidence": 0.5, "reason": "Scene boundary fallback"}
            for i in range(len(clips))
        ],
    }


# ── FFmpeg execution (same as VideoRegenerationAgent) ─────────────────────────

def _loudnorm_pass1(ffmpeg: str, input_path: str) -> str:
    """Run loudnorm analysis pass and return the measured JSON string."""
    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        match = re.search(r"(\{[^{}]+\})", result.stderr, re.DOTALL)
        return match.group(1) if match else ""
    except Exception:
        return ""


def _execute_plan(plan: TrailerEditingPlan, input_path: str, output_path: str) -> tuple[bool, str]:
    if not plan.clips:
        return False, "Editing plan contains no clips."

    tmp_dir = tempfile.mkdtemp(prefix="clipsense_smart_")
    clip_paths: list[str] = []

    try:
        for i, clip in enumerate(plan.clips):
            clip_path = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")
            cmd = [
                FFMPEG, "-y",
                "-ss", str(clip.start_time),
                "-to", str(clip.end_time),
                "-i", input_path,
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-c:a", "aac", "-b:a", "192k",
                "-vf", "eq=brightness=0:contrast=1:saturation=1.1",
                "-avoid_negative_ts", "make_zero",
                clip_path,
            ]
            ok, err = _run_ffmpeg(cmd)
            if not ok:
                return False, f"Failed to extract clip {i}: {err}"
            clip_paths.append(clip_path)

        concat_file = os.path.join(tmp_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for cp in clip_paths:
                f.write(f"file '{cp}'\n")

        # Re-encode concat to avoid A/V sync drift from differing keyframe intervals
        concat_output = os.path.join(tmp_dir, "concat_output.mp4")
        ok, err = _run_ffmpeg([
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-c:a", "aac", "-b:a", "192k",
            concat_output,
        ])
        if not ok:
            return False, f"Concatenation failed: {err}"

        # Probe duration
        probe = subprocess.run(
            [FFMPEG, "-i", concat_output, "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        duration = 0.0
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe.stderr)
        if dur_match:
            h, m, s = dur_match.groups()
            duration = int(h) * 3600 + int(m) * 60 + float(s)

        # Build audio filter: optional fade-out + two-pass loudnorm
        fade_filter = ""
        if plan.audio_fade_out and duration > 0:
            fade_start = max(0.0, duration - 2.0)
            fade_filter = f"afade=t=out:st={fade_start:.2f}:d=2,"

        measured_json = _loudnorm_pass1(FFMPEG, concat_output)
        loudnorm_filter = "loudnorm=I=-14:LRA=11:TP=-1:linear=true"
        if measured_json:
            try:
                m_data = json.loads(measured_json)
                _safe = {k: m_data[k] for k in ('input_i','input_lra','input_tp','input_thresh','target_offset')}
                # FFmpeg rejects -inf/-nan values — fall back to single-pass if any are non-finite
                if all(v not in ('-inf', 'inf', 'nan', '-nan') for v in _safe.values()):
                    loudnorm_filter = (
                        f"loudnorm=I=-14:LRA=11:TP=-1"
                        f":measured_I={_safe['input_i']}"
                        f":measured_LRA={_safe['input_lra']}"
                        f":measured_TP={_safe['input_tp']}"
                        f":measured_thresh={_safe['input_thresh']}"
                        f":offset={_safe['target_offset']}"
                        f":linear=true:print_format=none"
                    )
            except (KeyError, json.JSONDecodeError):
                pass

        ok, err = _run_ffmpeg([
            FFMPEG, "-y", "-i", concat_output,
            "-af", f"{fade_filter}{loudnorm_filter}",
            "-c:v", "copy",
            output_path,
        ])
        if not ok:
            return False, f"Final output failed: {err}"
        return True, ""

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Public interface ──────────────────────────────────────────────────────────

class SmartTrailerAgent:
    """
    Smart Trailer Agent — generates a new trailer from raw footage guided by
    sample trailer analysis and audience sentiment from comments.

    Returns: (output_path, editing_plan, analysis_report, error_message, platform, clip_score)
    """

    def __init__(self):
        self._structuring_agent = FeedbackStructuringAgent()

    def generate(
        self,
        raw_footage_path: str,
        sample_trailer_path: str,
        comments_path: str,
        job_id: str,
    ) -> tuple[str | None, TrailerEditingPlan | None, SmartTrailerAnalysis | None, str | None, str | None, float | None, bool, str | None]:

        # ── Stage 1: Parse comments ───────────────────────────────────────────
        raw_text = _read_comments_file(comments_path)
        if not raw_text.strip():
            return None, None, None, "Comments file is empty or unreadable.", None, None, False, None

        segments = self._structuring_agent.parse(raw_text)
        if not segments:
            return None, None, None, "No feedback segments could be extracted from comments.", None, None, False, None

        logger.info("SmartTrailerAgent: parsed %d comment segments", len(segments))

        # ── Stage 2: Analyse sample trailer ──────────────────────────────────
        # sample duration + scene detection run in parallel (both read the same file independently)
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_dur    = pool.submit(_get_video_duration, sample_trailer_path)
            fut_shots  = pool.submit(detect_scenes, sample_trailer_path)
            sample_duration = fut_dur.result()
            sample_shots    = fut_shots.result()

        if sample_duration <= 0:
            sample_duration = 120.0
            logger.warning("SmartTrailerAgent: could not read sample trailer duration, using 120s")
        logger.info("SmartTrailerAgent: sample trailer — %d shots detected", len(sample_shots))

        key = _get_free_key()
        logger.info("SmartTrailerAgent: GEMINI_FREE_API_KEY present=%s value_prefix=%s", bool(key), key[:8] if key else "(empty)")
        gemini_used = True
        fallback_warning: str | None = None
        try:
            analysis_raw = _call_gemini_analysis(segments, sample_duration, sample_shots)
        except Exception:
            import traceback
            tb = traceback.format_exc()
            with open("smart_job_debug.log", "a") as f:
                f.write("[Stage2 FAILED]\n" + tb + "\n")
            raise

        logger.info("SmartTrailerAgent: sample trailer analysis complete")

        # ── Stage 3: Generate clip plan from raw footage ──────────────────────
        # duration, scene detection, transcription and beat detection all run in parallel
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
            return None, None, None, "Could not determine raw footage duration.", None, None, False, None
        logger.info(
            "SmartTrailerAgent: raw footage pre-processing done — %.1fs, %d shots, %d transcript segments, %.1f BPM",
            raw_duration, len(raw_shots), len(raw_transcript["segments"]), raw_beats["tempo"],
        )

        target_duration = max(30.0, min(120.0, round(raw_duration * 0.15)))

        paid_key = _get_paid_key()
        logger.info("SmartTrailerAgent: GEMINI_PAID_API_KEY present=%s value_prefix=%s", bool(paid_key), paid_key[:8] if paid_key else "(empty)")
        try:
            plan_raw = _call_gemini_clip_plan(analysis_raw, raw_duration, target_duration, raw_shots, raw_transcript, raw_beats)
        except Exception:
            import traceback
            tb = traceback.format_exc()
            with open("smart_job_debug.log", "a") as f:
                f.write("[Stage3 FAILED]\n" + tb + "\n")
            raise

        if not plan_raw.get("clips"):
            return None, None, None, "No clips could be planned from raw footage.", None, None, gemini_used, fallback_warning

        logger.info("SmartTrailerAgent: clip plan ready — %d clips", len(plan_raw["clips"]))

        # Build SmartTrailerAnalysis
        scene_rationale = plan_raw.get("scene_selection_rationale", [])
        analysis = SmartTrailerAnalysis(
            sentiment_summary=analysis_raw.get("sentiment_summary", ""),
            positive_patterns=analysis_raw.get("positive_patterns", []),
            negative_patterns=analysis_raw.get("negative_patterns", []),
            top_scene_categories=analysis_raw.get("top_scene_categories", []),
            influence_explanation=analysis_raw.get("influence_explanation", ""),
            scene_selection_rationale=scene_rationale,
        )

        # Clamp Gemini clip boundaries to valid range, then snap to speech/beat
        beats = raw_beats.get("strong_beats", [])
        for c in plan_raw["clips"]:
            c["start_time"] = max(0.0, float(c.get("start_time", 0.0)))
            c["end_time"]   = min(raw_duration, float(c.get("end_time", raw_duration)))
            if c["end_time"] - c["start_time"] < 2.0:
                continue
            safe_start = find_safe_cut_point(c["start_time"], raw_transcript)
            safe_end   = find_safe_cut_point(c["end_time"],   raw_transcript)
            safe_start = find_nearest_beat(safe_start, beats)
            safe_end   = find_nearest_beat(safe_end,   beats)
            if safe_end - safe_start >= 2.0:
                c["start_time"] = safe_start
                c["end_time"]   = safe_end

        # Build TrailerEditingPlan
        clips = [TrailerClip(**c) for c in plan_raw["clips"]]
        plan = TrailerEditingPlan(
            clips=clips,
            target_duration=plan_raw.get("target_duration", target_duration),
            audio_fade_out=plan_raw.get("audio_fade_out", True),
            output_format=plan_raw.get("output_format", "mp4"),
            rationale=plan_raw.get("rationale", ""),
        )

        platform   = plan_raw.get("platform", "youtube")
        clip_score = plan_raw.get("clip_score")

        # ── Stage 4: FFmpeg execution ─────────────────────────────────────────
        output_filename = f"smart_{job_id}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "SmartTrailerAgent: executing FFmpeg — platform=%s score=%.2f clips=%d → %s",
            platform, clip_score or 0, len(plan.clips), output_path,
        )

        ok, err = _execute_plan(plan, raw_footage_path, output_path)
        if not ok:
            return None, plan, analysis, err, platform, clip_score, gemini_used, fallback_warning

        return output_path, plan, analysis, None, platform, clip_score, gemini_used, fallback_warning
