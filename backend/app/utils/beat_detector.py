"""
Beat Detector Utility

Extracts the audio track from a video file using FFmpeg, then runs librosa's
beat tracker to detect beat timestamps and estimate tempo (BPM).

The beat timestamps are passed to Gemini so it can align clip boundaries and
transitions with musical accents rather than placing cuts at arbitrary times.

Falls back to an empty result gracefully if librosa or FFmpeg is unavailable.
"""

import os
import logging
import tempfile
import subprocess

logger = logging.getLogger(__name__)


def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG = _get_ffmpeg()


def _extract_audio(video_path: str, audio_path: str) -> bool:
    """Extract mono 22050 Hz WAV from video for librosa."""
    cmd = [
        FFMPEG, "-y", "-i", video_path,
        "-ac", "1", "-ar", "11025",
        "-vn", audio_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        return result.returncode == 0
    except Exception as exc:
        logger.warning("beat_detector: audio extraction failed — %s", exc)
        return False


def detect_beats(video_path: str) -> dict:
    """
    Detect beat timestamps and tempo from a video's audio track.

    Returns a dict with:
      - beats:        list of float (beat timestamps in seconds)
      - tempo:        float (estimated BPM)
      - beat_count:   int
      - strong_beats: list of float (every 4th beat — downbeats, best for major cuts)

    Returns an empty result dict on any failure.
    """
    empty = {"beats": [], "tempo": 0.0, "beat_count": 0, "strong_beats": []}
    video_path = os.path.normpath(video_path)
    tmp_dir = tempfile.mkdtemp(prefix="clipsense_beats_")
    audio_path = os.path.join(tmp_dir, "audio.wav")

    try:
        if not _extract_audio(video_path, audio_path):
            return empty

        import librosa
        import numpy as np

        y, sr = librosa.load(audio_path, sr=11025, mono=True, res_type='kaiser_fast')
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, hop_length=256)
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()

        # Scalar tempo (librosa may return array)
        bpm = float(np.atleast_1d(tempo)[0])

        # Strong beats = every 4th beat (downbeats) — best anchor points for major cuts
        strong_beats = [round(t, 3) for i, t in enumerate(beat_times) if i % 4 == 0]
        beats = [round(t, 3) for t in beat_times]

        logger.info(
            "beat_detector: %.1f BPM, %d beats, %d strong beats in %s",
            bpm, len(beats), len(strong_beats), video_path,
        )
        return {
            "beats":        beats,
            "tempo":        round(bpm, 1),
            "beat_count":   len(beats),
            "strong_beats": strong_beats,
        }

    except Exception as exc:
        logger.warning("beat_detector: failed for %s — %s", video_path, exc)
        return empty

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def find_nearest_beat(desired_time: float, beats: list[float], tolerance: float = 0.5) -> float:
    """
    Snap a desired cut time to the nearest beat within ±tolerance seconds.
    Returns the original time if no beat is within tolerance.
    """
    if not beats:
        return desired_time
    nearest = min(beats, key=lambda b: abs(b - desired_time))
    if abs(nearest - desired_time) <= tolerance:
        return round(nearest, 3)
    return desired_time
