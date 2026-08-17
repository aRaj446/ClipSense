"""
Transcript Utility

Runs OpenAI Whisper on a video file to produce:
  - segments: list of sentence-level dicts with start, end, text
  - words:    list of word-level dicts with start, end, word (when available)

The segments are used by the trailer agents to:
  1. Detect speech boundaries so FFmpeg clip edges never cut mid-sentence.
  2. Identify content-rich moments for clip selection scoring.

Device selection is controlled by the DEVICE and USE_GPU environment variables
(see app/utils/device.py). The model name is controlled by WHISPER_MODEL.

Model caching:
    The loaded Whisper model is cached per (model_name, device) pair within
    the worker process. This avoids reloading the model for every job while
    remaining safe if the device or model name changes between calls (e.g.
    during testing). The cache is process-scoped — each worker process has
    its own cache, which is correct for both local and EC2 deployments.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

# Thread-safe model cache: (model_name, device) → whisper model instance
# Keyed by both model name and device so a test that patches DEVICE does not
# accidentally reuse a model loaded on a different device.
_model_cache: dict = {}
_model_cache_lock = threading.Lock()


def _get_model():
    """
    Load and cache the Whisper model for the currently configured device.

    Thread-safe: uses a lock so concurrent jobs in the same process do not
    trigger duplicate model loads. The first caller loads the model; all
    subsequent callers receive the cached instance.

    Device and model name are resolved fresh on each call so that changes to
    environment variables (e.g. in tests) are respected without restarting.
    """
    from app.utils.device import resolve_device, whisper_model_name
    model_name = whisper_model_name()
    device = resolve_device()
    cache_key = (model_name, device)

    with _model_cache_lock:
        if cache_key not in _model_cache:
            import whisper
            logger.info(
                "transcript: loading Whisper model '%s' on device '%s'",
                model_name, device,
            )
            _model_cache[cache_key] = whisper.load_model(model_name, device=device)
            logger.info(
                "transcript: model '%s' loaded on '%s'",
                model_name, device,
            )
        return _model_cache[cache_key]


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
