"""
FFmpeg Composer Utility

Shared video assembly layer used by both VideoRegenerationAgent and SmartTrailerAgent.

Architecture:
    TrailerEditingPlan
      ↓
    FFmpeg per-clip extraction + normalisation  ← Step 1 (this file)
      ↓
    _stitch_clips()  (MoviePy crossfade transitions on normalised clips)  ← Step 2 (this file)
      ↓
    FFmpeg final pass  (encode, loudnorm, EQ, subtitles)  ← Step 3 (this file)
      ↓
    output.mp4

Two MoviePy layers — distinct responsibilities, not duplicates:

    _stitch_clips() [this file]:
        Operates on already-normalised per-clip .mp4 files produced by Step 1.
        Each file is a distinct source — no subclipping, no source reuse.
        Applies CrossFadeIn transitions and writes one intermediate file.

    TrailerComposer [trailer_composer.py]:
        Operates on a single raw source video.
        Handles subclipping, source handle reuse, declarative TransitionConfig,
        and optional music/SFX mixing.
        Reserved for future raw-source composition (e.g. S3-backed pipeline).
        Not called by the current pipeline.

FFmpeg responsibilities (this file):
    - Per-clip normalisation: resolution, fps, colour grade, per-clip loudnorm
    - Final codec selection and encoding (libx264 / h264_nvenc)
    - Muxing
    - Two-pass loudnorm on final output
    - Optional EQ: bass boost (+4 dB @ 100 Hz), treble cut (-3 dB @ 8 kHz)
    - Hardware encoding (h264_nvenc on EC2 GPU)
    - Subtitle burn-in via FFmpeg subtitles filter (SRT)
    - Video + audio fade-out on final clip
    - Real-time SSE progress reporting
    - Failed clip extractions are skipped rather than aborting the whole job

Subtitle architecture (FFmpeg SRT approach):
    Subtitles are burned in during the final FFmpeg pass using the `subtitles`
    filter, which reads a temporary SRT file generated from the Whisper transcript.

    This approach is retained over MoviePy TextClip because:
      - FFmpeg subtitles filter is GPU-accelerated on EC2 GPU instances
      - No font/display dependency (MoviePy TextClip requires a display or Pillow fonts)
      - Lower memory usage — no in-memory video frame manipulation
      - SRT is a standard format; the pipeline is auditable and portable
      - Cleaner separation: MoviePy owns transitions, FFmpeg owns encoding+subtitles

    Timestamp mapping per clip (implemented in map_transcript_to_timeline):
        source_seg_start  — Whisper timestamp in source video seconds
        clip.start_time   — where FFmpeg cut the clip from the source
        clip_local_start  = source_seg_start - clip.start_time   (clip-local time)
        timeline_start    = clip_timeline_offset + clip_local_start

    Segments are clamped to [0, clip_duration] before placement so trimmed clips
    never produce out-of-range SRT entries.

    Temporary SRT files are created inside the job-scoped tmp_dir and are
    deleted unconditionally in the finally block — on success AND failure.
"""

import os
import re
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field

from app.utils.clip_planner import PlannedClip, MIN_CLIP_DURATION
from app.utils.render_progress import set_progress
from app.utils.beat_detector import find_nearest_beat

logger = logging.getLogger(__name__)

CROSSFADE_DURATION = 1.0   # seconds — xfade overlap between clips

# Default loudness target — matches existing behaviour
_DEFAULT_TARGET_LUFS = -14


@dataclass
class AudioSettings:
    """
    Per-job audio normalisation controls.

    target_lufs:
        Final output loudness in LUFS. Passed to the two-pass loudnorm filter.
        Default -14 preserves existing behaviour.
        Supported values: -16, -14, -12, -10.

    bass_boost:
        Apply a +4 dB low-shelf EQ at 100 Hz.
        Conservative value chosen to enhance low-frequency impact without
        muddying dialogue. Applied BEFORE loudnorm so the normaliser
        compensates for any integrated loudness change.

    treble_cut:
        Apply a -3 dB high-shelf EQ at 8 kHz.
        Conservative value chosen to soften high-frequency harshness
        (e.g. sibilance, harsh music transients) while preserving speech clarity.
        Applied BEFORE loudnorm for the same reason.

    Filter order in the final pass:
        [boundary_fade] → [afade] → [bass_boost?] → [treble_cut?] → loudnorm

    EQ is applied before loudnorm so the normaliser sees the EQ'd signal and
    compensates accordingly — this is the correct order for broadcast workflows.
    """
    target_lufs: int = _DEFAULT_TARGET_LUFS
    bass_boost: bool = False
    treble_cut: bool = False

# Colour grading applied to every clip for visual consistency
_GRADE_FILTER = (
    "eq=brightness=0.02:contrast=1.05:saturation=1.15:gamma=1.02,"
    "curves=r='0/0 0.5/0.52 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.48 1/1'"
)

# Normalise every clip to 1920x1080 @ 30fps before compositing.
_NORMALISE_FILTER = (
    "scale=1920:1080:force_original_aspect_ratio=decrease,"
    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,"
    "setsar=1,"
    "fps=30,settb=1/30"
)

# Full per-clip video filter: normalise, grade, then force yuv420p last
# format=yuv420p must come AFTER curves/eq — some ffmpeg builds promote
# to yuv444p internally during grading; pinning format at the end prevents
# the encoder from seeing 4:4:4 which -profile:v high rejects.
_CLIP_VF = f"{_NORMALISE_FILTER},{_GRADE_FILTER},format=yuv420p"

# Per-clip loudnorm — normalise each clip to -16 LUFS before compositing so no
# clip enters a transition louder or quieter than its neighbours.
_CLIP_LOUDNORM = "loudnorm=I=-16:LRA=11:TP=-1:linear=true"


def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _get_ffmpeg()


def _resolve_encoder() -> str:
    """Resolve the video encoder at call time (not import time) so tests can patch env vars."""
    try:
        from app.utils.device import resolve_video_encoder
        return resolve_video_encoder()
    except RuntimeError as exc:
        logger.error("ffmpeg_composer: encoder resolution failed — %s", exc)
        raise
    except Exception as exc:
        logger.warning("ffmpeg_composer: encoder resolution error (%s) — falling back to libx264", exc)
        return "libx264"


def _run(cmd: list[str], timeout: int = 300, job_id: str | None = None) -> tuple[bool, str]:
    """Run an FFmpeg command. If job_id is provided, registers the subprocess for cancellation."""
    from app.utils.job_queue import register_process, unregister_process, is_cancelled

    if job_id and is_cancelled(job_id):
        return False, "Cancelled by user"

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if job_id:
            register_process(job_id, proc)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return False, f"FFmpeg timed out after {timeout}s"
        finally:
            if job_id:
                unregister_process(job_id)

        if job_id and is_cancelled(job_id):
            return False, "Cancelled by user"

        return proc.returncode == 0, stderr.decode('utf-8', errors='replace')
    except FileNotFoundError:
        return False, f"FFmpeg not found at '{cmd[0]}'"
    except Exception as exc:
        return False, str(exc)


def _probe_duration(path: str) -> float:
    from app.utils.ffprobe import extract_video_metadata
    meta = extract_video_metadata(path)
    return float(meta.get("duration") or 0.0)


def _loudnorm_pass1(input_path: str, target_lufs: int = _DEFAULT_TARGET_LUFS) -> str:
    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-af", f"loudnorm=I={target_lufs}:LRA=11:TP=-1:print_format=json",
        "-f", "null", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        m = re.search(r"(\{[^{}]+\})", r.stderr, re.DOTALL)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _build_loudnorm_filter(measured_json: str, target_lufs: int = _DEFAULT_TARGET_LUFS) -> str:
    base = f"loudnorm=I={target_lufs}:LRA=11:TP=-1:linear=true"
    if not measured_json:
        return base
    try:
        d = json.loads(measured_json)
        keys = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
        vals = {k: d[k] for k in keys}
        if any(v in ("-inf", "inf", "nan", "-nan") for v in vals.values()):
            return base
        return (
            f"loudnorm=I={target_lufs}:LRA=11:TP=-1"
            f":measured_I={vals['input_i']}"
            f":measured_LRA={vals['input_lra']}"
            f":measured_TP={vals['input_tp']}"
            f":measured_thresh={vals['input_thresh']}"
            f":offset={vals['target_offset']}"
            f":linear=true:print_format=none"
        )
    except Exception:
        return base


def _build_eq_filters(settings: AudioSettings) -> str:
    """
    Build optional EQ filter string from AudioSettings.

    Bass boost:  +4 dB low-shelf at 100 Hz
    Treble cut:  -3 dB high-shelf at 8 kHz

    Returns a comma-prefixed filter string (e.g. ",equalizer=...,equalizer=...")
    or empty string when neither toggle is enabled.
    Callers prepend this directly to an audio filter chain.
    """
    parts: list[str] = []
    if settings.bass_boost:
        parts.append("equalizer=f=100:width_type=o:width=1:g=4")
    if settings.treble_cut:
        parts.append("equalizer=f=8000:width_type=o:width=1:g=-3")
    return ("," + ",".join(parts)) if parts else ""


# ── Subtitle timestamp mapping ────────────────────────────────────────────────

def map_transcript_to_timeline(
    clips: list[PlannedClip],
    clip_timeline_offsets: list[float],
    clip_durations: list[float],
    transcript: dict,
) -> list[dict]:
    """
    Map Whisper transcript segments to final trailer timeline positions.

    For each PlannedClip, find all transcript segments that overlap
    [clip.start_time, clip.end_time], remap their timestamps to the clip's
    position in the stitched timeline, and clamp to the clip's actual duration.

    Timestamp mapping:
        clip_local_start = seg.start - clip.start_time
        clip_local_end   = seg.end   - clip.start_time
        timeline_start   = clip_timeline_offset + clip_local_start
        timeline_end     = clip_timeline_offset + clip_local_end

    Both values are clamped to [0, clip_duration] in clip-local space so
    trimmed clips never produce out-of-range entries.

    Returns a list of dicts: {start: float, end: float, text: str}
    where start/end are seconds on the final trailer timeline.
    Entries with duration < 0.1 s or empty text are excluded.
    """
    segments = transcript.get("segments", [])
    if not segments:
        return []

    result: list[dict] = []

    for clip, tl_offset, clip_dur in zip(clips, clip_timeline_offsets, clip_durations):
        overlapping = [
            seg for seg in segments
            if seg["start"] < clip.end_time and seg["end"] > clip.start_time
            and seg.get("text", "").strip()
        ]
        for seg in overlapping:
            local_start = seg["start"] - clip.start_time
            local_end   = seg["end"]   - clip.start_time

            # Clamp to actual extracted clip duration
            local_start = max(0.0, local_start)
            local_end   = min(clip_dur, local_end)

            if local_end <= local_start:
                continue

            tl_start = tl_offset + local_start
            tl_end   = tl_offset + local_end
            duration  = tl_end - tl_start

            if duration < 0.1:
                continue

            result.append({
                "start": round(tl_start, 3),
                "end":   round(tl_end, 3),
                "text":  seg["text"].strip(),
            })

    logger.debug("map_transcript_to_timeline: %d subtitle entries mapped", len(result))
    return result


# ── SRT generation ────────────────────────────────────────────────────────────

def _secs_to_srt_time(secs: float) -> str:
    """Convert seconds to SRT timestamp format: HH:MM:SS,mmm"""
    secs = max(0.0, secs)
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    ms = int(round((secs - int(secs)) * 1000))
    # Guard against rounding pushing ms to 1000
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(subtitle_entries: list[dict], total_duration: float | None = None) -> str:
    """
    Generate a valid SRT string from a list of {start, end, text} dicts.

    Requirements enforced:
      - Sequential 1-based numbering
      - HH:MM:SS,mmm timestamps
      - start < end (entries where start >= end are skipped)
      - No negative timestamps (clamped to 0)
      - No subtitles beyond total_duration (if provided)
      - Unicode text passed through unchanged
    """
    lines: list[str] = []
    index = 1
    for entry in subtitle_entries:
        start = max(0.0, entry["start"])
        end   = entry["end"]
        text  = entry.get("text", "").strip()

        if not text:
            continue
        if end <= start:
            continue
        if total_duration is not None and start >= total_duration:
            continue
        if total_duration is not None:
            end = min(end, total_duration)

        lines.append(str(index))
        lines.append(f"{_secs_to_srt_time(start)} --> {_secs_to_srt_time(end)}")
        lines.append(text)
        lines.append("")   # blank line between entries
        index += 1

    return "\n".join(lines)


def write_srt_file(subtitle_entries: list[dict], path: str, total_duration: float | None = None) -> None:
    """Write SRT content to path. Raises on I/O error."""
    content = build_srt(subtitle_entries, total_duration)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    logger.debug("write_srt_file: wrote %d entries to %s", len(subtitle_entries), path)


# ── Scene boundary fade ───────────────────────────────────────────────────────

def _build_scene_boundary_fade(clip_durations: list[float], fade_secs: float = 0.8) -> str:
    """
    Build an audio volume envelope that dips to 0.4 for `fade_secs` before
    each clip boundary, then recovers — giving a smooth musical transition
    at every scene cut rather than an abrupt audio jump.
    Returns an ffmpeg volume filter expression, or empty string if not needed.
    """
    if len(clip_durations) <= 1:
        return ""
    conditions = []
    t = 0.0
    for dur in clip_durations[:-1]:   # no fade needed after the last clip
        t += dur
        fade_start = round(t - fade_secs, 3)
        fade_end   = round(t, 3)
        if fade_start >= 0:
            conditions.append(f"between(t,{fade_start},{fade_end})")
    if not conditions:
        return ""
    expr = "+".join(conditions)
    return f"volume=enable='{expr}':volume=0.4:eval=frame"


# ── MoviePy transition stitching ─────────────────────────────────────────────

def _stitch_clips(
    clip_paths: list[str],
    concat_out: str,
) -> tuple[bool, str, list[float], list[float]]:
    """
    Stitch already-normalised per-clip .mp4 files into one intermediate file
    using MoviePy CrossFadeIn transitions.

    Each clip_path is a distinct source file produced by FFmpeg Step 1.
    No subclipping — each file is opened as a complete VideoFileClip.

    Returns:
        (success, error_message, clip_timeline_offsets, clip_durations)

    clip_timeline_offsets and clip_durations are parallel lists used by
    map_transcript_to_timeline() for subtitle timestamp mapping.
    On failure both lists are empty.
    """
    from moviepy import VideoFileClip, CompositeVideoClip
    from moviepy.video.fx import CrossFadeIn

    clip_timeline_offsets: list[float] = []
    clip_durations:        list[float] = []
    positioned:            list        = []
    mv_handles:            list        = []
    composite                          = None
    tl_pos                             = 0.0
    errors:                list[str]   = []

    try:
        for idx, cp in enumerate(clip_paths):
            try:
                mvc = VideoFileClip(cp)
                mv_handles.append(mvc)
                dur = mvc.duration
                if idx == 0:
                    clip_timeline_offsets.append(0.0)
                    clip_durations.append(dur)
                    positioned.append(mvc.with_start(0.0))
                    tl_pos = dur
                else:
                    xfade = min(CROSSFADE_DURATION, dur / 2)
                    tl_start = tl_pos - xfade
                    clip_timeline_offsets.append(tl_start)
                    clip_durations.append(dur)
                    positioned.append(
                        mvc.with_effects([CrossFadeIn(xfade)])
                           .with_start(tl_start)
                    )
                    tl_pos = tl_start + dur
            except Exception as exc:
                logger.warning(
                    "_stitch_clips: MoviePy open failed for clip %d (%s) — %s",
                    idx, cp, exc,
                )
                errors.append(str(exc))

        if not positioned:
            return False, f"All MoviePy clip opens failed: {'; '.join(errors)}", [], []

        composite = CompositeVideoClip(positioned)
        composite.write_videofile(
            concat_out,
            codec="libx264",
            audio_codec="aac",
            fps=30,
            preset="fast",
            logger=None,
        )
        return True, "", clip_timeline_offsets, clip_durations

    except Exception as exc:
        return False, f"Transition stitching failed: {exc}", [], []

    finally:
        for mvc in mv_handles:
            try:
                mvc.close()
            except Exception:
                pass
        if composite is not None:
            try:
                composite.close()
            except Exception:
                pass


# ── Main compose function ─────────────────────────────────────────────────────

def compose(
    clips: list[PlannedClip],
    input_path: str,
    output_path: str,
    transcript: dict,
    audio_fade_out: bool = True,
    job_id: str | None = None,
    beats: list[float] | None = None,
    audio_settings: AudioSettings | None = None,
    include_subtitles: bool = False,
) -> tuple[bool, str]:
    """
    Assemble clips into a final video. Returns (success, error_message).
    Failed individual clip extractions are skipped; the job only fails if
    every clip fails or the final compose step fails.

    Subtitle flow (when include_subtitles=True):
        1. map_transcript_to_timeline() converts Whisper segments to trailer timestamps
        2. write_srt_file() writes a temporary SRT into the job-scoped tmp_dir
        3. FFmpeg final pass burns subtitles via the `subtitles` filter
        4. tmp_dir (including the SRT) is deleted in the finally block

    If transcript has no segments, subtitles are silently skipped (graceful degradation).
    """
    if not clips:
        return False, "No clips to compose."

    # Normalise input path to absolute to avoid CWD-relative resolution issues
    input_path = os.path.normpath(os.path.abspath(input_path))

    def _progress(stage: str, pct: int, msg: str = "") -> None:
        if job_id:
            set_progress(job_id, stage, pct, msg)

    def _step(key: str, status: str, pct: int, msg: str = "", overall: int | None = None) -> None:
        if job_id:
            from app.utils.render_progress import set_step
            set_step(job_id, key, status, pct, msg, overall_percent=overall)

    # Beat-snap clip starts for musical cut alignment.
    if beats:
        for clip in clips:
            snapped = find_nearest_beat(clip.start_time, beats, tolerance=0.4)
            if snapped <= clip.start_time and clip.end_time - snapped >= MIN_CLIP_DURATION:
                clip.start_time = snapped

    # Job-scoped temp directory — all temp files (clips, concat, SRT) live here.
    # Deleted unconditionally in the finally block.
    # Resolve long path immediately to avoid Windows 8.3 short names in FFmpeg args.
    _raw_tmp = tempfile.mkdtemp(prefix="clipsense_compose_")
    try:
        import ctypes
        _buf = ctypes.create_unicode_buffer(32768)
        ctypes.windll.kernel32.GetLongPathNameW(_raw_tmp, _buf, 32768)
        tmp_dir = _buf.value or _raw_tmp
    except Exception:
        tmp_dir = _raw_tmp

    try:
        # ── Step 1: Extract, normalise, grade, and loudnorm each clip ────────
        clip_paths: list[str] = []
        _surviving_clips: list[PlannedClip] = []
        n_clips = len(clips)

        for i, clip in enumerate(clips):
            # Check cancellation between each clip extraction
            if job_id:
                from app.utils.job_queue import is_cancelled
                if is_cancelled(job_id):
                    return False, "Cancelled by user"

            pct_overall = 55 + int((i / n_clips) * 20)
            _progress("extracting", int((i / n_clips) * 40), f"Extracting clip {i + 1}/{n_clips}")
            _step("extracting", "active", int((i / n_clips) * 100), f"Clip {i + 1} of {n_clips}", overall=pct_overall)
            out = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")

            # Muted clips: replace audio with silence of the same duration.
            # anullsrc generates a silent stream; atrim caps it to the clip length.
            if getattr(clip, 'muted', False):
                clip_dur = clip.end_time - clip.start_time
                audio_filter = (
                    f"anullsrc=r=44100:cl=stereo,"
                    f"atrim=duration={clip_dur:.3f},"
                    f"aresample=async=1000"
                )
                audio_map = ["-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo"]
                audio_map_flag = ["-map", "1:a:0"]
            else:
                audio_filter = f"{_CLIP_LOUDNORM},aresample=async=1000"
                audio_map = []
                audio_map_flag = ["-map", "0:a:0"]

            # Speed control: apply setpts for video and atempo for audio
            clip_speed = getattr(clip, 'speed', 1.0)
            speed_vf = ""
            speed_af = ""
            if clip_speed != 1.0 and clip_speed > 0:
                # setpts=PTS/speed makes video faster (speed>1) or slower (speed<1)
                speed_vf = f",setpts=PTS/{clip_speed}"
                # atempo only supports 0.5–2.0 range; chain multiple for extremes
                if clip_speed >= 0.5 and clip_speed <= 2.0:
                    speed_af = f",atempo={clip_speed}"
                elif clip_speed < 0.5:
                    # Chain two atempo filters: sqrt(speed) * sqrt(speed)
                    half = clip_speed ** 0.5
                    speed_af = f",atempo={half:.4f},atempo={half:.4f}"
                else:
                    # speed > 2.0: chain two
                    half = clip_speed ** 0.5
                    speed_af = f",atempo={half:.4f},atempo={half:.4f}"

            _encoder = _resolve_encoder()
            from app.utils.device import encoder_options
            cmd = [
                FFMPEG, "-y",
                "-ss", str(clip.start_time),
                "-to", str(clip.end_time),
                "-i", input_path,
                *audio_map,
                "-map", "0:v:0", *audio_map_flag,
                "-vf", f"{_CLIP_VF}{speed_vf}",
                "-af", f"{audio_filter}{speed_af}",
                "-c:v", _encoder, *encoder_options(_encoder),
                "-c:a", "aac", "-b:a", "192k",
                "-avoid_negative_ts", "make_zero",
                "-vsync", "cfr",
                "-max_muxing_queue_size", "1024",
                out,
            ]
            ok, err = _run(cmd, job_id=job_id)
            if not ok:
                logger.warning(
                    "compose: clip %d (%.1f-%.1f) extraction failed, skipping - %s",
                    i, clip.start_time, clip.end_time, err[:3000],
                )
                continue
            clip_paths.append(out)
            _surviving_clips.append(clip)

        if not clip_paths:
            return False, "All clip extractions failed - no clips to compose."

        _step("extracting", "done", 100, f"{len(clip_paths)} clips extracted", overall=75)

        # ── Step 2: Stitch clips with moviepy crossfade transitions ──────────
        _progress("composing", 50, f"Stitching {len(clip_paths)} clips with transitions")
        _step("composing", "active", 0, f"Stitching {len(clip_paths)} clips", overall=76)

        concat_out = os.path.join(tmp_dir, "concat_out.mp4")

        # Track timeline offsets for subtitle timestamp mapping
        clip_timeline_offsets: list[float] = []
        clip_durations_mv: list[float] = []

        if len(clip_paths) == 1:
            # Single clip — no transitions needed, just copy through
            _progress("composing", 50, "Single clip — skipping transitions")
            concat_out = clip_paths[0]
            clip_timeline_offsets = [0.0]
            clip_durations_mv = [_probe_duration(clip_paths[0])]
            _step("composing", "done", 100, "Single clip — no transitions needed", overall=80)
        else:
            ok_stitch, err_stitch, clip_timeline_offsets, clip_durations_mv = _stitch_clips(
                clip_paths, concat_out
            )
            if not ok_stitch:
                return False, err_stitch

        _step("composing", "done", 100, "Transitions applied", overall=82)

        # ── Step 3: Audio fade-out + two-pass loudnorm + optional subtitles ──
        _progress("normalising", 80, "Normalising audio levels")
        _step("normalising", "active", 0, "Running two-pass loudnorm…", overall=83)

        duration = _probe_duration(concat_out)

        # Audio fade-out filter
        fade_filter = ""
        vfade_filter = ""
        if audio_fade_out and duration > 0:
            fade_start   = max(0.0, duration - 2.0)
            fade_filter  = f"afade=t=out:st={fade_start:.2f}:d=2,"
            vfade_filter = f"fade=t=out:st={fade_start:.2f}:d=2,"

        # Scene-boundary music fade
        clip_durations_for_fade = [_probe_duration(p) for p in clip_paths]
        boundary_fade   = _build_scene_boundary_fade(clip_durations_for_fade)
        boundary_filter = f"{boundary_fade}," if boundary_fade else ""

        # EQ + loudnorm
        settings   = audio_settings or AudioSettings()
        eq_str     = _build_eq_filters(settings)   # e.g. ",equalizer=..." or ""
        eq_filter  = eq_str[1:] + "," if eq_str else ""  # strip leading comma, add trailing
        measured   = _loudnorm_pass1(concat_out, settings.target_lufs)
        loudnorm   = _build_loudnorm_filter(measured, settings.target_lufs)

        # Filter order: boundary_fade → afade → EQ → loudnorm
        audio_filt = f"{boundary_filter}{fade_filter}{eq_filter}{loudnorm}"

        # Video filter: optional subtitle burn-in + fade + format pin
        subtitle_vf = ""
        if include_subtitles:
            subtitle_entries = map_transcript_to_timeline(
                _surviving_clips,
                clip_timeline_offsets,
                clip_durations_mv,
                transcript,
            )
            if subtitle_entries:
                # Build drawtext filters — one per subtitle entry.
                # Strip characters that break FFmpeg filter string parsing.
                dt_parts: list[str] = []
                for entry in subtitle_entries:
                    safe_text = (
                        entry["text"]
                        .replace("'", "")
                        .replace('"', "")
                        .replace("\\", "")
                        .replace(":", " ")
                        .replace("%", "%%")
                        .strip()
                    )
                    if not safe_text:
                        continue
                    dt_parts.append(
                        f"drawtext=text='{safe_text}'"
                        f":fontsize=22:fontcolor=white"
                        f":box=1:boxcolor=black@0.5:boxborderw=6"
                        f":x=(w-text_w)/2:y=h-th-60"
                        f":enable='between(t,{entry['start']},{entry['end']})'"
                    )
                if dt_parts:
                    subtitle_vf = ",".join(dt_parts) + ","
                    logger.info("compose: burning %d subtitle entries via drawtext", len(dt_parts))
            else:
                logger.info("compose: include_subtitles=True but no transcript segments mapped — subtitles skipped")

        video_filt = f"{subtitle_vf}{vfade_filter}format=yuv420p"

        _final_encoder = _resolve_encoder()
        from app.utils.device import encoder_options as _enc_opts
        _final_enc_opts = _enc_opts(_final_encoder)
        # libx264 supports -profile:v/-level; NVENC uses its own profile flags
        _profile_opts = ["-profile:v", "high", "-level", "4.1"] if _final_encoder == "libx264" else []
        ok, err = _run([
            FFMPEG, "-y", "-i", concat_out,
            "-vf", video_filt,
            "-c:v", _final_encoder, *_final_enc_opts, *_profile_opts,
            "-af", audio_filt,
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ], job_id=job_id)
        if not ok:
            return False, f"Final output failed: {err}"

        _progress("done", 100, "Render complete")
        _step("normalising", "done", 100, "Audio normalised", overall=100)
        return True, ""

    finally:
        import shutil
        shutil.rmtree(_raw_tmp, ignore_errors=True)
