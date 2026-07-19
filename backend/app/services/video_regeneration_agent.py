"""
Video Regeneration Agent — Module 3

Pipeline:
    Stage 1 — Clip Analysis (Gemini)
        Gemini independently analyzes the video duration and analytics report
        to propose multiple platform-specific promotional clips. Each proposed
        clip is assigned a platform (youtube/instagram/tiktok/twitter), a
        sentiment satisfaction score (0.0–1.0), and a rationale.

    Stage 2 — Clip Selection
        Clips are ranked by clip_score (sentiment satisfaction). Only the
        highest-scoring clip per platform is kept. The best overall clip
        (highest score) is selected for FFmpeg execution.

    Stage 3 — FFmpeg Execution
        FFmpeg extracts, concatenates, and fades the selected clip plan.
        FFmpeg never makes creative decisions.

Gemini NEVER touches the video file.
FFmpeg NEVER makes creative decisions.
"""

import os
import re
import json
import uuid
import logging
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.schemas.feedback import AnalyticsReport, TrailerEditingPlan, TrailerClip
from app.utils.storage import UPLOAD_DIR, TRAILERS_DIR
from app.utils.scene_detector import detect_scenes
from app.utils.transcript import transcribe, find_safe_cut_point
from app.utils.beat_detector import detect_beats, find_nearest_beat

logger = logging.getLogger(__name__)

# Use imageio-ffmpeg bundled binary if ffmpeg is not on PATH
def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

def _get_ffprobe() -> str:
    """Use ffprobe if available, otherwise fall back to the ffmpeg binary for probing."""
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
        if os.path.exists(ffprobe_path):
            return ffprobe_path
    except Exception:
        pass
    return "ffprobe"

FFMPEG  = _get_ffmpeg()
FFPROBE = _get_ffprobe()

_GEMINI_MODEL = "models/gemini-3.1-flash-lite"


def _get_gemini_key() -> str:
    return os.getenv("GEMINI_PAID_API_KEY") or os.getenv("GEMINI_API_KEY", "")

# Platform specs: max duration in seconds
PLATFORM_SPECS = {
    "youtube":   {"max_duration": 120, "label": "YouTube Trailer"},
    "instagram": {"max_duration": 60,  "label": "Instagram Reel"},
    "tiktok":    {"max_duration": 60,  "label": "TikTok"},
    "twitter":   {"max_duration": 30,  "label": "Twitter/X"},
}

# ── Gemini prompt ─────────────────────────────────────────────────────────────

_CLIP_ANALYSIS_PROMPT = """
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

You are also the Video Regeneration Agent of an AI-powered Video Marketing Optimization Platform. You receive a structured analytics report derived from audience sentiment analysis of a video. Apply the cinematic editing guidelines above when proposing clip plans, and additionally use the analytics metrics below to inform every creative decision:
- Use sentiment_distribution to understand the overall emotional tone of the audience and calibrate the trailer's emotional arc accordingly.
- Use top_positives (topics and timestamps with the highest positive/praise sentiment and confidence) to identify which scenes resonated most — prioritise these segments in the edit.
- Use top_issues (topics with the highest negative/complaint sentiment) to identify scenes that drove poor reactions — exclude or minimise these segments.
- Use topic_breakdown (per-topic positive, negative, neutral counts and avg_confidence) to weight scene selection: topics with high positive counts and high avg_confidence should appear earlier and longer in the edit.
- Use timeline (timestamped sentiment points) to pinpoint exact moments of peak positive engagement and use them as anchor points for cuts, transitions, and music sync.
- Use confidence_stats (mean, min, max, high_confidence_count, low_confidence_count) to filter out low-confidence segments (confidence < 0.60) from the edit unless no higher-confidence alternatives exist.

========================================
PLATFORMS TO GENERATE FOR
========================================

For EACH of the following platforms, propose one editing plan:
  - youtube   (max {youtube_max}s)  — full trailer, broad audience
  - instagram (max {instagram_max}s) — punchy reel, visual highlights
  - tiktok    (max {tiktok_max}s)   — fast-paced, hook-first
  - twitter   (max {twitter_max}s)  — short teaser, strong opening

========================================
DECISION RULES
========================================

1. PRIORITIZE segments from top_positives — these are what audiences loved.
2. AVOID segments from top_issues — these are what audiences disliked.
3. USE timeline entries with timestamps to identify exact clip boundaries.
4. Each clip must be at least 3 seconds long.
5. Total clip duration must not exceed the platform max duration.
6. Order clips to maximize engagement: start strong, end strong.
7. Prefer high-confidence segments (confidence >= 0.80).
8. After building each plan, assign a clip_score (0.0–1.0):
   - 1.0 = all clips are from top_positives, zero overlap with top_issues
   - 0.0 = clips are entirely from top_issues
   - Score proportionally based on positive vs negative sentiment coverage.

========================================
OUTPUT CONTRACT
========================================

Return ONLY a valid JSON array of 4 objects (one per platform). No markdown. No code fences.

[
  {{
    "platform": "youtube",
    "clip_score": 0.0,
    "clips": [
      {{
        "start_time": 0.0,
        "end_time": 0.0,
        "reason": "one sentence",
        "topic": "topic label",
        "sentiment": "sentiment label",
        "platform": "youtube"
      }}
    ],
    "target_duration": 0.0,
    "audio_fade_out": true,
    "output_format": "mp4",
    "rationale": "2-3 sentence editing strategy for this platform"
  }}
]

Rules:
- start_time and end_time are in SECONDS (float)
- If a timestamp is "01:30", start_time = 90.0
- Snap clip boundaries to the nearest detected shot boundary from SHOT BOUNDARIES when available.
  Do NOT use an arbitrary fixed window — use the actual scene start_time and end_time.
- If no shot boundary is near a timeline timestamp, use a 5-second window (start = timestamp - 2, end = timestamp + 3)
- clip_score must be between 0.0 and 1.0

========================================
ANALYTICS REPORT:
{analytics}

VIDEO DURATION (seconds): {video_duration}

SHOT BOUNDARIES (detected by PySceneDetect):
{shot_boundaries}

SPEECH TRANSCRIPT (Whisper word-level timestamps):
{transcript_segments}

AUDIO BEAT TIMESTAMPS (librosa beat tracker):
{beat_data}
========================================

Instructions for using shot boundaries:
- Each entry gives the exact start_time, end_time, duration, and MM:SS timestamp of a detected cut.
- Correlate timeline sentiment timestamps with these shot boundaries to snap clip selections to real scene edges.
- Use scene duration patterns to inform pacing: replicate short rapid cuts for high-energy platforms (tiktok, twitter), use longer sustained scenes for youtube.
- Prefer selecting whole scenes or contiguous groups of scenes rather than arbitrary sub-clips.

Instructions for using the speech transcript:
- Each segment entry has start, end, and text — a complete spoken sentence or phrase.
- NEVER set a clip end_time that falls mid-sentence. Always extend or trim the end_time to the nearest segment end boundary.
- NEVER set a clip start_time that cuts into an ongoing sentence. Always start at or before the segment start boundary.
- Prefer clips that contain complete, meaningful spoken phrases — these are more engaging than silent or mid-sentence clips.
- Use the transcript text to identify content-rich moments (product mentions, emotional statements, key phrases) and prioritise them.

Instructions for using beat timestamps:
- tempo gives the overall BPM of the audio track.
- beats lists every detected beat in seconds — ideal for cut points on fast-paced platforms (tiktok, instagram).
- strong_beats lists every 4th beat (downbeats) — use these as anchor points for major scene transitions and clip boundaries on all platforms.
- Align clip start_time and end_time values to the nearest strong_beat where possible without violating speech boundaries.
- For high-energy platforms (tiktok, twitter), prefer shorter clips whose duration is a multiple of the beat interval (60/tempo seconds).
"""


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
    """Infer video duration from the highest timestamp in the timeline when metadata is unavailable."""
    max_secs = 0.0
    for point in analytics.timeline:
        if point.timestamp:
            secs = _mm_ss_to_seconds(point.timestamp)
            if secs and secs > max_secs:
                max_secs = secs
    # Add 30s buffer beyond the last known timestamp, or use fallback
    return (max_secs + 30.0) if max_secs > 0 else fallback


def _trim_for_prompt(shot_boundaries: list[dict], transcript: dict, beat_data: dict) -> tuple[list, list, dict]:
    """Reduce data size before injecting into Gemini prompt to stay within token limits."""
    # Cap shot boundaries at 60 scenes
    shots = shot_boundaries[:60]
    # Cap transcript segments at 80 entries
    segments = transcript.get("segments", [])[:80]
    # Only pass strong_beats (every 4th beat) and cap at 60, drop raw beats entirely
    strong = beat_data.get("strong_beats", [])[:60]
    trimmed_beats = {"tempo": beat_data.get("tempo", 0.0), "strong_beats": strong}
    return shots, segments, trimmed_beats


def _call_gemini(
    analytics: AnalyticsReport,
    video_duration: float,
    shot_boundaries: list[dict],
    transcript: dict,
    beat_data: dict,
) -> list[dict] | None:
    import sys
    print("Entering Video Regeneration Agent", flush=True, file=sys.stderr)
    import google.genai as genai
    client = genai.Client(api_key=_get_gemini_key())

    shots, segments, trimmed_beats = _trim_for_prompt(shot_boundaries, transcript, beat_data)

    prompt = _CLIP_ANALYSIS_PROMPT.format(
        analytics=analytics.model_dump_json(indent=2),
        video_duration=round(video_duration, 1),
        shot_boundaries=json.dumps(shots, indent=2),
        transcript_segments=json.dumps(segments, indent=2),
        beat_data=json.dumps(trimmed_beats, indent=2),
        youtube_max=PLATFORM_SPECS["youtube"]["max_duration"],
        instagram_max=PLATFORM_SPECS["instagram"]["max_duration"],
        tiktok_max=PLATFORM_SPECS["tiktok"]["max_duration"],
        twitter_max=PLATFORM_SPECS["twitter"]["max_duration"],
    )
    print("About to call Gemini", flush=True, file=sys.stderr)
    print("Model:", _GEMINI_MODEL, flush=True, file=sys.stderr)
    print("Key prefix:", _get_gemini_key()[:8], flush=True, file=sys.stderr)
    response = client.models.generate_content(model=_GEMINI_MODEL, contents=prompt)
    text = response.text.strip()
    logger.info("VideoRegenerationAgent: Gemini raw response (first 500 chars): %s", text[:500])

    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    return json.loads(text)


def _snap_to_scene(
    timestamp_s: float,
    shot_boundaries: list[dict],
    video_duration: float,
) -> tuple[float, float]:
    """Snap a timestamp to the nearest scene boundary start/end. Falls back to ±2/+3s window."""
    if not shot_boundaries:
        start = max(0.0, timestamp_s - 2.0)
        end = min(video_duration, timestamp_s + 3.0) if video_duration > 0 else timestamp_s + 3.0
        return start, end
    # Find the scene whose start_time is closest to the timestamp
    best = min(shot_boundaries, key=lambda s: abs(s["start_time"] - timestamp_s))
    return best["start_time"], best["end_time"]


def _fallback_plans(
    analytics: AnalyticsReport,
    video_duration: float,
    shot_boundaries: list[dict],
) -> list[dict]:
    """Pure-Python fallback: build one plan per platform using engagement-weighted scoring."""
    positive_sentiments = {"Positive", "Praise"}

    # Build engagement weight per topic: avg_confidence * positive_count
    topic_weight: dict[str, float] = {}
    for tb in analytics.topic_breakdown:
        topic_weight[tb.topic] = round(tb.avg_confidence * tb.positive, 3)

    candidates = sorted(
        [p for p in analytics.timeline if p.timestamp and p.sentiment in positive_sentiments],
        key=lambda x: topic_weight.get(x.topic, 0) * x.confidence,
        reverse=True,
    )
    if not candidates:
        # Fall back to all timestamped segments sorted by confidence
        candidates = sorted(
            [p for p in analytics.timeline if p.timestamp],
            key=lambda x: x.confidence,
            reverse=True,
        )

    # Deduplicate by timestamp to avoid redundant clips
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
            if clip_len < 3.0 or total + clip_len > spec["max_duration"]:
                continue
            clips.append({
                "start_time": round(start, 2),
                "end_time":   round(end, 2),
                "reason":     f"Audience responded positively to {point.topic}",
                "topic":      point.topic,
                "sentiment":  point.sentiment,
                "platform":   platform,
            })
            total += clip_len

        pos_count = sum(1 for c in clips if c["sentiment"] in positive_sentiments)
        clip_score = round(pos_count / len(clips), 2) if clips else 0.0

        plans.append({
            "platform":        platform,
            "clip_score":      clip_score,
            "clips":           clips,
            "target_duration": round(total, 2),
            "audio_fade_out":  True,
            "output_format":   "mp4",
            "rationale":       f"Fallback plan for {platform}: highest-confidence positive segments.",
        })

    return plans


def _select_best_plan(plans: list[dict]) -> dict | None:
    """Pick the plan with the highest clip_score. Ties broken by target_duration (longer wins)."""
    valid = [p for p in plans if p.get("clips")]
    if not valid:
        return None
    return max(valid, key=lambda p: (p.get("clip_score", 0), p.get("target_duration", 0)))


# ── FFmpeg execution ──────────────────────────────────────────────────────────

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


def _loudnorm_pass1(ffmpeg: str, input_path: str) -> str:
    """Run loudnorm analysis pass and return the measured_I/LRA/TP/thresh JSON string."""
    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1:print_format=json",
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # loudnorm prints its JSON to stderr
        match = re.search(r"(\{[^{}]+\})", result.stderr, re.DOTALL)
        return match.group(1) if match else ""
    except Exception:
        return ""


def _execute_plan(
    plan: TrailerEditingPlan,
    input_path: str,
    output_path: str,
) -> tuple[bool, str]:
    if not plan.clips:
        return False, "Editing plan contains no clips."

    tmp_dir = tempfile.mkdtemp(prefix="clipsense_trailer_")
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
        cmd = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow",
            "-c:a", "aac", "-b:a", "192k",
            concat_output,
        ]
        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return False, f"Concatenation failed: {err}"

        # Probe duration for fade calculation
        probe_result = subprocess.run(
            [FFMPEG, "-i", concat_output, "-f", "null", "-"],
            capture_output=True, text=True, timeout=30,
        )
        duration = 0.0
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", probe_result.stderr)
        if dur_match:
            h, m, s = dur_match.groups()
            duration = int(h) * 3600 + int(m) * 60 + float(s)

        # Build audio filter chain: optional fade-out + two-pass loudnorm
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

        audio_filter = f"{fade_filter}{loudnorm_filter}"

        cmd = [
            FFMPEG, "-y", "-i", concat_output,
            "-af", audio_filter,
            "-c:v", "copy",
            output_path,
        ]
        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return False, f"Final output failed: {err}"

        return True, ""

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Public interface ──────────────────────────────────────────────────────────

class VideoRegenerationAgent:
    """
    Module 3 — Video Regeneration Agent.

    Stage 1: Gemini proposes platform-specific clip plans and scores each by
             sentiment satisfaction (clip_score 0.0–1.0).
    Stage 2: Best-scoring plan is selected for FFmpeg execution.
    Stage 3: FFmpeg extracts clips, concatenates, applies audio fade.

    Returns the winning plan's platform and clip_score alongside the output path.
    """

    def generate(
        self,
        project_id: str,
        analytics: AnalyticsReport,
        video_duration: float,
        target_duration: float = 60.0,
    ) -> tuple[str | None, TrailerEditingPlan | None, str | None, str | None, float | None, bool, str | None]:
        """
        Returns: (output_path, editing_plan, error_message, platform, clip_score, gemini_used, fallback_warning)
        """
        input_path = self._find_video(project_id)
        if not input_path:
            return None, None, f"Source video not found for project {project_id}", None, None, False, None

        # If ffprobe didn't extract duration, infer from timeline timestamps
        if not video_duration or video_duration <= 0:
            video_duration = _infer_duration(analytics)
            logger.info("VideoRegenerationAgent: duration unknown, inferred %.1fs from timeline", video_duration)

        # Run scene detection, transcription and beat detection in parallel
        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_scenes = pool.submit(detect_scenes, input_path)
            fut_transcript = pool.submit(transcribe, input_path)
            fut_beats = pool.submit(detect_beats, input_path)
            shot_boundaries = fut_scenes.result()
            transcript      = fut_transcript.result()
            beat_data       = fut_beats.result()

        logger.info(
            "VideoRegenerationAgent: pre-processing done — %d shots, %d transcript segments, %.1f BPM",
            len(shot_boundaries), len(transcript["segments"]), beat_data["tempo"],
        )

        # Stage 1 — Gemini or fallback
        key = _get_gemini_key()
        logger.info("VideoRegenerationAgent: GEMINI_API_KEY present=%s value_prefix=%s", bool(key), key[:8] if key else "(empty)")
        gemini_used = True
        fallback_warning: str | None = None
        raw_plans = _call_gemini(analytics, video_duration, shot_boundaries, transcript, beat_data)

        # Stage 2 — select best plan by clip_score
        best_raw = _select_best_plan(raw_plans)
        if not best_raw or not best_raw.get("clips"):
            return None, None, "No suitable clips found in analytics timeline.", None, None, gemini_used, fallback_warning

        platform   = best_raw.get("platform")
        clip_score = best_raw.get("clip_score")

        # Clamp Gemini clip boundaries to valid range, then snap to speech/beat
        beats = beat_data.get("strong_beats", [])
        safe_clips = []
        for c in best_raw["clips"]:
            c["start_time"] = max(0.0, float(c.get("start_time", 0.0)))
            c["end_time"]   = min(video_duration, float(c.get("end_time", video_duration))) if video_duration > 0 else float(c.get("end_time", 0.0))
            if c["end_time"] - c["start_time"] < 2.0:
                safe_clips.append(c)
                continue
            safe_start = find_safe_cut_point(c["start_time"], transcript)
            safe_end   = find_safe_cut_point(c["end_time"],   transcript)
            safe_start = find_nearest_beat(safe_start, beats)
            safe_end   = find_nearest_beat(safe_end,   beats)
            if safe_end - safe_start >= 2.0:
                c["start_time"] = safe_start
                c["end_time"]   = safe_end
            safe_clips.append(c)

        # Build TrailerEditingPlan from best raw plan
        clips = [TrailerClip(**c) for c in safe_clips]
        plan = TrailerEditingPlan(
            clips=clips,
            target_duration=best_raw.get("target_duration", target_duration),
            audio_fade_out=best_raw.get("audio_fade_out", True),
            output_format=best_raw.get("output_format", "mp4"),
            rationale=best_raw.get("rationale", ""),
        )

        # Stage 3 — FFmpeg
        output_filename = f"{project_id}_{platform}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "VideoRegenerationAgent: platform=%s score=%.2f clips=%d → %s",
            platform, clip_score or 0, len(plan.clips), output_path,
        )
        ok, err = _execute_plan(plan, input_path, output_path)

        if not ok:
            return None, plan, err, platform, clip_score, gemini_used, fallback_warning

        return output_path, plan, None, platform, clip_score, gemini_used, fallback_warning

    def _find_video(self, project_id: str) -> str | None:
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")
            if os.path.exists(path):
                return path
        return None
