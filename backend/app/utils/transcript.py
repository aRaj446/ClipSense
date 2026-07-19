"""
Transcript Utility

Runs OpenAI Whisper on a video file to produce:
  - segments: list of sentence-level dicts with start, end, text
  - words:    list of word-level dicts with start, end, word (when available)

The segments are used by the trailer agents to:
  1. Detect speech boundaries so FFmpeg clip edges never cut mid-sentence.
  2. Pass spoken content context to Gemini so it can make content-aware
     clip selections (e.g. prefer clips containing key product phrases).

Uses the "base" model by default — fast enough for server use and accurate
enough for boundary detection. Falls back to an empty result gracefully if
Whisper or torch is unavailable.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Model size: "tiny" | "base" | "small" | "medium" | "large"
# "base" is the best tradeoff between speed and accuracy for boundary detection.
_WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# Cache the loaded model across calls within the same process lifetime
_model_cache: dict = {}


def _get_model():
    if _WHISPER_MODEL not in _model_cache:
        import whisper
        logger.info("transcript: loading Whisper model '%s'", _WHISPER_MODEL)
        _model_cache[_WHISPER_MODEL] = whisper.load_model(_WHISPER_MODEL)
    return _model_cache[_WHISPER_MODEL]


def transcribe(video_path: str) -> dict:
    """
    Transcribe a video file using Whisper.

    Returns a dict with:
      - segments: list of { start, end, text } — sentence/phrase level
      - words:    list of { start, end, word } — word level (empty if unavailable)
      - language: detected language code
      - full_text: complete transcript as a single string

    Returns an empty result dict on any failure.
    """
    empty = {"segments": [], "words": [], "language": "", "full_text": ""}
    try:
        video_path = os.path.abspath(video_path)
        # Patch whisper to use imageio_ffmpeg binary directly
        try:
            import imageio_ffmpeg
            import whisper.audio as _wa
            import functools
            _ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            _orig_load_audio = _wa.load_audio
            @functools.wraps(_orig_load_audio)
            def _patched_load_audio(file, sr=_wa.SAMPLE_RATE):
                from subprocess import run, CalledProcessError
                import numpy as np
                cmd = [_ffmpeg_exe, "-nostdin", "-threads", "0", "-i", file,
                       "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(sr), "-"]
                try:
                    out = run(cmd, capture_output=True, check=True).stdout
                except CalledProcessError as e:
                    raise RuntimeError(f"Failed to load audio: {e.stderr.decode()}") from e
                return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0
            _wa.load_audio = _patched_load_audio
        except Exception:
            pass
        model = _get_model()
        logger.info("transcript: transcribing %s", video_path)

        result = model.transcribe(
            video_path,
            word_timestamps=True,
            verbose=False,
        )

        segments = []
        words = []

        for seg in result.get("segments", []):
            segments.append({
                "start": round(seg["start"], 3),
                "end":   round(seg["end"], 3),
                "text":  seg["text"].strip(),
            })
            for w in seg.get("words", []):
                words.append({
                    "start": round(w["start"], 3),
                    "end":   round(w["end"], 3),
                    "word":  w["word"].strip(),
                })

        logger.info(
            "transcript: %d segments, %d words detected in %s",
            len(segments), len(words), video_path,
        )
        return {
            "segments": segments,
            "words":    words,
            "language": result.get("language", ""),
            "full_text": result.get("text", "").strip(),
        }

    except Exception as exc:
        logger.warning("transcript: failed for %s — %s", video_path, exc)
        return empty


def find_safe_cut_point(
    desired_time: float,
    transcript: dict,
    tolerance: float = 3.0,
) -> float:
    """
    Given a desired cut time, find the nearest sentence boundary within
    ±tolerance seconds that does not fall mid-word or mid-sentence.

    Returns the adjusted cut time (or the original if no speech is nearby).
    """
    segments = transcript.get("segments", [])
    if not segments:
        return desired_time

    best_time = desired_time
    best_dist = float("inf")

    for seg in segments:
        # Prefer cutting at the END of a sentence (natural pause)
        for boundary in (seg["end"], seg["start"]):
            dist = abs(boundary - desired_time)
            if dist <= tolerance and dist < best_dist:
                best_dist = dist
                best_time = boundary

    return round(best_time, 3)
