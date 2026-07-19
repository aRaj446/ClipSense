"""
FFmpeg Composer Utility

Shared video assembly layer used by both VideoRegenerationAgent and SmartTrailerAgent.

Features:
    - Crossfade (xfade) transitions between clips — no hard cuts
    - Consistent colour grading across all clips (exposure/saturation normalisation)
    - Audio ducking under speech segments (sidechaincompress-style via volume envelope)
    - Two-pass loudnorm for broadcast-standard audio levels
    - Audio fade-out on final clip
"""

import os
import re
import json
import logging
import subprocess
import tempfile

from app.utils.clip_planner import PlannedClip

logger = logging.getLogger(__name__)

CROSSFADE_DURATION = 0.5   # seconds — xfade overlap between clips

# Colour grading filter applied to every clip for visual consistency
_GRADE_FILTER = (
    "eq=brightness=0.02:contrast=1.05:saturation=1.15:gamma=1.02,"
    "curves=r='0/0 0.5/0.52 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.48 1/1'"
)


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
    r = subprocess.run([FFMPEG, "-i", path, "-f", "null", "-"], capture_output=True, text=True, timeout=30)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        h, mn, s = m.groups()
        return int(h) * 3600 + int(mn) * 60 + float(s)
    return 0.0


def _loudnorm_pass1(input_path: str) -> str:
    cmd = [FFMPEG, "-y", "-i", input_path,
           "-af", "loudnorm=I=-14:LRA=11:TP=-1:print_format=json",
           "-f", "null", "-"]
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


def _build_audio_duck_filter(transcript: dict, clip_start: float, clip_end: float) -> str:
    """
    Build a volume envelope that ducks background audio to 0.3 during speech
    and restores to 1.0 during non-speech. Uses volume= with enable= expressions.
    Falls back to no ducking if no transcript segments overlap this clip.
    """
    segments = transcript.get("segments", [])
    speech_windows = [
        (max(0.0, s["start"] - clip_start), min(clip_end - clip_start, s["end"] - clip_start))
        for s in segments
        if s["start"] < clip_end and s["end"] > clip_start
    ]
    if not speech_windows:
        return ""

    # Build enable expression: between(t, start, end) for each speech window
    conditions = "+".join(
        f"between(t,{round(ws, 3)},{round(we, 3)})"
        for ws, we in speech_windows
        if we > ws
    )
    if not conditions:
        return ""

    # volume=1 normally, 0.35 during speech (subtle duck — keeps ambience audible)
    return f"volume=enable='{conditions}':volume=0.35:eval=frame"


def compose(
    clips: list[PlannedClip],
    input_path: str,
    output_path: str,
    transcript: dict,
    audio_fade_out: bool = True,
) -> tuple[bool, str]:
    """
    Assemble clips into a final video with:
        - Colour-graded clip extraction
        - xfade crossfade transitions between clips
        - Audio ducking under speech
        - Two-pass loudnorm
        - Optional audio fade-out

    Returns (success, error_message).
    """
    if not clips:
        return False, "No clips to compose."

    tmp_dir = tempfile.mkdtemp(prefix="clipsense_compose_")

    try:
        # ── Step 1: Extract and grade each clip ───────────────────────────
        clip_paths: list[str] = []
        for i, clip in enumerate(clips):
            out = os.path.join(tmp_dir, f"clip_{i:03d}.mp4")

            # Build audio duck filter for this clip's speech windows
            duck = _build_audio_duck_filter(transcript, clip.start_time, clip.end_time)
            audio_filter = duck if duck else "anull"

            cmd = [
                FFMPEG, "-y",
                "-ss", str(clip.start_time),
                "-to", str(clip.end_time),
                "-i", input_path,
                "-vf", _GRADE_FILTER,
                "-af", audio_filter,
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-c:a", "aac", "-b:a", "192k",
                "-avoid_negative_ts", "make_zero",
                out,
            ]
            ok, err = _run(cmd)
            if not ok:
                return False, f"Clip {i} extraction failed: {err}"
            clip_paths.append(out)

        if len(clip_paths) == 1:
            # Single clip — skip xfade, go straight to loudnorm
            concat_out = clip_paths[0]
        else:
            # ── Step 2: xfade crossfade between consecutive clips ─────────
            # Build a filtergraph that chains xfade for all N clips
            # xfade requires re-encoding so we use a filter_complex approach
            inputs = []
            for p in clip_paths:
                inputs += ["-i", p]

            # Build filter_complex: chain xfade across all clips
            # [0][1]xfade=...[v01]; [v01][2]xfade=...[v012]; ...
            # Audio: [0][1]acrossfade=...[a01]; [a01][2]acrossfade=...[a012]; ...
            n = len(clip_paths)
            v_chain = "[0:v]"
            a_chain = "[0:a]"
            filter_parts = []

            for i in range(1, n):
                v_in  = v_chain if i == 1 else f"[vx{i-1}]"
                v_out = f"[vx{i}]" if i < n - 1 else "[vout]"
                a_in  = a_chain if i == 1 else f"[ax{i-1}]"
                a_out = f"[ax{i}]" if i < n - 1 else "[aout]"

                # Get duration of the previous clip for offset calculation
                prev_dur = _probe_duration(clip_paths[i - 1])
                offset   = max(0.1, prev_dur - CROSSFADE_DURATION)

                filter_parts.append(
                    f"{v_in}[{i}:v]xfade=transition=fade:duration={CROSSFADE_DURATION}:offset={offset:.3f}{v_out}"
                )
                filter_parts.append(
                    f"{a_in}[{i}:a]acrossfade=d={CROSSFADE_DURATION}{a_out}"
                )

            filter_complex = ";".join(filter_parts)
            concat_out = os.path.join(tmp_dir, "xfade_out.mp4")

            cmd = (
                [FFMPEG, "-y"]
                + inputs
                + [
                    "-filter_complex", filter_complex,
                    "-map", "[vout]", "-map", "[aout]",
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "192k",
                    concat_out,
                ]
            )
            ok, err = _run(cmd, timeout=600)
            if not ok:
                # xfade failed (e.g. mismatched resolutions) — fall back to concat
                logger.warning("compose: xfade failed (%s) — falling back to concat", err[:200])
                concat_out = os.path.join(tmp_dir, "concat_fallback.mp4")
                concat_file = os.path.join(tmp_dir, "concat.txt")
                with open(concat_file, "w") as f:
                    for p in clip_paths:
                        f.write(f"file '{p}'\n")
                ok, err = _run([
                    FFMPEG, "-y", "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "192k",
                    concat_out,
                ])
                if not ok:
                    return False, f"Concatenation failed: {err}"

        # ── Step 3: Audio fade-out + two-pass loudnorm ────────────────────
        duration = _probe_duration(concat_out)
        fade_filter = ""
        if audio_fade_out and duration > 0:
            fade_start  = max(0.0, duration - 2.0)
            fade_filter = f"afade=t=out:st={fade_start:.2f}:d=2,"

        measured   = _loudnorm_pass1(concat_out)
        loudnorm   = _build_loudnorm_filter(measured)
        audio_filt = f"{fade_filter}{loudnorm}"

        ok, err = _run([
            FFMPEG, "-y", "-i", concat_out,
            "-af", audio_filt,
            "-c:v", "copy",
            output_path,
        ])
        if not ok:
            return False, f"Final output failed: {err}"

        return True, ""

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
