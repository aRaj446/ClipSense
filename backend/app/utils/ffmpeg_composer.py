"""
FFmpeg Composer Utility

Shared video assembly layer used by both VideoRegenerationAgent and SmartTrailerAgent.

Features:
    - Resolution/fps normalisation (1920x1080 @ 30fps, settb=1/30) before compositing
    - Colour grading across all clips (exposure/saturation normalisation)
    - Per-clip loudnorm (-16 LUFS) so every clip enters compositing at matched loudness
    - moviepy CrossFadeIn transitions between clips
    - Beat-snapped clip boundaries when beats list provided
    - Scene-boundary music fade (volume dip before each cut for smooth transitions)
    - Two-pass loudnorm (-14 LUFS) on final output
    - Video + audio fade-out on final clip
    - Real-time SSE progress reporting
    - Failed clip extractions are skipped rather than aborting the whole job
"""

import os
import re
import json
import logging
import subprocess
import tempfile

from app.utils.clip_planner import PlannedClip, MIN_CLIP_DURATION
from app.utils.render_progress import set_progress
from app.utils.beat_detector import find_nearest_beat

logger = logging.getLogger(__name__)

CROSSFADE_DURATION = 1.0   # seconds — xfade overlap between clips

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


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stderr
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg timed out after {timeout}s"
    except FileNotFoundError:
        return False, f"FFmpeg not found at '{cmd[0]}'"
    except Exception as exc:
        return False, str(exc)


def _probe_duration(path: str) -> float:
    from app.utils.ffprobe import extract_video_metadata
    meta = extract_video_metadata(path)
    return float(meta.get("duration") or 0.0)


def _loudnorm_pass1(input_path: str) -> str:
    cmd = [
        FFMPEG, "-y", "-i", input_path,
        "-af", "loudnorm=I=-14:LRA=11:TP=-1:print_format=json",
        "-f", "null", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        m = re.search(r"(\{[^{}]+\})", r.stderr, re.DOTALL)
        return m.group(1) if m else ""
    except Exception:
        return ""


def _build_loudnorm_filter(measured_json: str) -> str:
    base = "loudnorm=I=-14:LRA=11:TP=-1:linear=true"
    if not measured_json:
        return base
    try:
        d = json.loads(measured_json)
        keys = ("input_i", "input_lra", "input_tp", "input_thresh", "target_offset")
        vals = {k: d[k] for k in keys}
        if any(v in ("-inf", "inf", "nan", "-nan") for v in vals.values()):
            return base
        return (
            f"loudnorm=I=-14:LRA=11:TP=-1"
            f":measured_I={vals['input_i']}"
            f":measured_LRA={vals['input_lra']}"
            f":measured_TP={vals['input_tp']}"
            f":measured_thresh={vals['input_thresh']}"
            f":offset={vals['target_offset']}"
            f":linear=true:print_format=none"
        )
    except Exception:
        return base



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


def compose(
    clips: list[PlannedClip],
    input_path: str,
    output_path: str,
    transcript: dict,
    audio_fade_out: bool = True,
    job_id: str | None = None,
    beats: list[float] | None = None,
) -> tuple[bool, str]:
    """
    Assemble clips into a final video. Returns (success, error_message).
    Failed individual clip extractions are skipped; the job only fails if
    every clip fails or the final compose step fails.
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
    # Skip if the snap would move start forward past a safe margin from end.
    if beats:
        for clip in clips:
            snapped = find_nearest_beat(clip.start_time, beats, tolerance=0.4)
            # Only accept snap if it doesn't shrink the clip AND moves start earlier/same
            if snapped <= clip.start_time and clip.end_time - snapped >= MIN_CLIP_DURATION:
                clip.start_time = snapped

    tmp_dir = tempfile.mkdtemp(prefix="clipsense_compose_")

    try:
        # ── Step 1: Extract, normalise, grade, and loudnorm each clip ────────
        clip_paths: list[str] = []
        n_clips = len(clips)

        for i, clip in enumerate(clips):
            pct_overall = 55 + int((i / n_clips) * 20)
            _progress("extracting", int((i / n_clips) * 40), f"Extracting clip {i + 1}/{n_clips}")
            _step("extracting", "active", int((i / n_clips) * 100), f"Clip {i + 1} of {n_clips}", overall=pct_overall)
            out = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")

            audio_filter = f"{_CLIP_LOUDNORM},aresample=async=1000"

            cmd = [
                FFMPEG, "-y",
                "-ss", str(clip.start_time),
                "-to", str(clip.end_time),
                "-i", input_path,
                "-map", "0:v:0", "-map", "0:a:0",
                "-vf", _CLIP_VF,
                "-af", audio_filter,
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-c:a", "aac", "-b:a", "192k",
                "-avoid_negative_ts", "make_zero",
                "-vsync", "cfr",
                "-max_muxing_queue_size", "1024",
                out,
            ]
            ok, err = _run(cmd)
            if not ok:
                logger.warning(
                    "compose: clip %d (%.1f-%.1f) extraction failed, skipping - %s",
                    i, clip.start_time, clip.end_time, err[:3000],
                )
                continue
            clip_paths.append(out)

        if not clip_paths:
            return False, "All clip extractions failed - no clips to compose."

        _step("extracting", "done", 100, f"{len(clip_paths)} clips extracted", overall=75)

        # ── Step 2: Stitch clips with moviepy crossfade transitions ──────────
        if len(clip_paths) == 1:
            _progress("composing", 50, "Single clip — skipping transitions")
            _step("composing", "done", 100, "Single clip — no transitions needed", overall=80)
            concat_out = clip_paths[0]
        else:
            _progress("composing", 50, f"Stitching {len(clip_paths)} clips with transitions")
            _step("composing", "active", 0, f"Stitching {len(clip_paths)} clips", overall=76)

            concat_out = os.path.join(tmp_dir, "concat_out.mp4")

            mv_clips: list = []
            composite = None
            try:
                from moviepy import VideoFileClip, CompositeVideoClip
                from moviepy.video.fx import CrossFadeIn

                mv_clips = [VideoFileClip(p) for p in clip_paths]

                # Place each clip on the timeline overlapping by CROSSFADE_DURATION.
                # CrossFadeIn dissolves the incoming clip over the overlap window.
                timeline_pos = 0.0
                positioned = []
                for idx, mvc in enumerate(mv_clips):
                    if idx == 0:
                        positioned.append(mvc.with_start(0))
                        timeline_pos = mvc.duration
                    else:
                        start = timeline_pos - CROSSFADE_DURATION
                        positioned.append(
                            mvc.with_effects([CrossFadeIn(CROSSFADE_DURATION)])
                               .with_start(start)
                        )
                        timeline_pos = start + mvc.duration

                composite = CompositeVideoClip(positioned)
                composite.write_videofile(
                    concat_out,
                    codec="libx264",
                    audio_codec="aac",
                    fps=30,
                    preset="fast",
                    logger=None,
                )
            except Exception as exc:
                return False, f"Transition stitching failed: {exc}"
            finally:
                for mvc in mv_clips:
                    try:
                        mvc.close()
                    except Exception:
                        pass
                if composite is not None:
                    try:
                        composite.close()
                    except Exception:
                        pass

        _step("composing", "done", 100, "Transitions applied", overall=82)

        # ── Step 3: Audio fade-out + two-pass loudnorm ────────────────────────
        _progress("normalising", 80, "Normalising audio levels")
        _step("normalising", "active", 0, "Running two-pass loudnorm…", overall=83)
        duration = _probe_duration(concat_out)
        fade_filter = ""
        vfade_filter = ""
        if audio_fade_out and duration > 0:
            fade_start    = max(0.0, duration - 2.0)
            fade_filter   = f"afade=t=out:st={fade_start:.2f}:d=2,"
            vfade_filter  = f"fade=t=out:st={fade_start:.2f}:d=2,"

        # Build scene-boundary music fade envelope from actual clip durations
        clip_durations_for_fade = [_probe_duration(p) for p in clip_paths]
        boundary_fade = _build_scene_boundary_fade(clip_durations_for_fade)
        boundary_filter = f"{boundary_fade}," if boundary_fade else ""

        measured   = _loudnorm_pass1(concat_out)
        loudnorm   = _build_loudnorm_filter(measured)
        audio_filt = f"{boundary_filter}{fade_filter}{loudnorm}"

        ok, err = _run([
            FFMPEG, "-y", "-i", concat_out,
            "-vf", f"{vfade_filter}format=yuv420p",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-profile:v", "high", "-level", "4.1",
            "-af", audio_filt,
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ])
        if not ok:
            return False, f"Final output failed: {err}"

        _progress("done", 100, "Render complete")
        _step("normalising", "done", 100, "Audio normalised", overall=100)
        return True, ""

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
