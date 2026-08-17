"""
Device Configuration Utility

Single source of truth for hardware device selection across the ClipSense
backend. Reads from environment variables so the same code runs on:
  - Local CPU development machines
  - AWS EC2 GPU instances (any NVIDIA GPU with CUDA)
  - CI/CD pipelines (CPU-only)

Environment variables (set in .env or EC2 environment):
    USE_GPU=false           Master GPU switch. When false, forces CPU regardless
                            of DEVICE setting. Default: false.

    DEVICE=auto             Device selection strategy.
                            auto  → CUDA if available, otherwise CPU (default)
                            cuda  → Require CUDA; raise RuntimeError if unavailable
                            cpu   → CPU only

    VIDEO_ENCODER=auto      FFmpeg video encoder selection.
                            auto  → h264_nvenc if available, otherwise libx264
                            gpu   → Require h264_nvenc; raise RuntimeError if unavailable
                            cpu   → libx264 always

    WHISPER_MODEL=base      Whisper model size. Configurable so EC2 instances with
                            more VRAM can use larger models without code changes.
                            Supported: tiny, base, small, medium, large, large-v2, large-v3

All resolution functions are pure (no side effects) and safe to call from
multiple threads. CUDA availability is checked once and cached.
"""

import os
import logging
import subprocess
import functools

logger = logging.getLogger(__name__)

# ── Environment reads ─────────────────────────────────────────────────────────

def _env(key: str, default: str) -> str:
    return os.getenv(key, default).strip().lower()


def use_gpu() -> bool:
    """Return True if the USE_GPU master switch is enabled."""
    return _env("USE_GPU", "false") in ("1", "true", "yes")


def device_setting() -> str:
    """Return the raw DEVICE env value (auto/cuda/cpu)."""
    return _env("DEVICE", "auto")


def video_encoder_setting() -> str:
    """Return the raw VIDEO_ENCODER env value (auto/gpu/cpu)."""
    return _env("VIDEO_ENCODER", "auto")


def whisper_model_name() -> str:
    """Return the configured Whisper model name."""
    return os.getenv("WHISPER_MODEL", "base").strip()


# ── CUDA availability (cached) ────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _cuda_available() -> bool:
    """
    Check whether CUDA is available via PyTorch.
    Result is cached for the process lifetime — CUDA availability does not
    change at runtime and torch.cuda.is_available() has non-trivial overhead.
    Returns False if torch is not installed.
    """
    try:
        import torch
        available = torch.cuda.is_available()
        if available:
            device_name = torch.cuda.get_device_name(0)
            logger.info("device: CUDA available — %s", device_name)
        else:
            logger.info("device: CUDA not available — will use CPU")
        return available
    except ImportError:
        logger.info("device: torch not installed — CUDA unavailable")
        return False
    except Exception as exc:
        logger.warning("device: CUDA check failed (%s) — falling back to CPU", exc)
        return False


# ── Public device resolution ──────────────────────────────────────────────────

def resolve_device() -> str:
    """
    Resolve the effective compute device string for PyTorch/Whisper.

    Returns "cuda" or "cpu".

    Raises RuntimeError if DEVICE=cuda but CUDA is unavailable.
    """
    if not use_gpu():
        logger.debug("device: USE_GPU=false — using CPU")
        return "cpu"

    setting = device_setting()

    if setting == "cpu":
        return "cpu"

    if setting == "cuda":
        if not _cuda_available():
            raise RuntimeError(
                "DEVICE=cuda but CUDA is not available on this machine. "
                "Install CUDA drivers, or set DEVICE=auto to fall back to CPU."
            )
        return "cuda"

    # auto (default)
    return "cuda" if _cuda_available() else "cpu"


# ── FFmpeg encoder detection ──────────────────────────────────────────────────

@functools.lru_cache(maxsize=1)
def _nvenc_available() -> bool:
    """
    Probe FFmpeg for h264_nvenc encoder support.
    Cached for the process lifetime.
    Returns False if FFmpeg is not found or NVENC is not compiled in.
    """
    # Resolve FFmpeg path the same way ffmpeg_composer does, without importing it
    # (avoids a circular import: device ←→ ffmpeg_composer).
    try:
        import imageio_ffmpeg
        _ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        _ffmpeg_exe = "ffmpeg"

    try:
        result = subprocess.run(
            [_ffmpeg_exe, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
        available = "h264_nvenc" in result.stdout
        if available:
            logger.info("device: h264_nvenc encoder available")
        else:
            logger.info("device: h264_nvenc not available — will use libx264")
        return available
    except FileNotFoundError:
        logger.warning("device: FFmpeg not found — cannot probe encoders")
        return False
    except Exception as exc:
        logger.warning("device: encoder probe failed (%s) — falling back to libx264", exc)
        return False


def resolve_video_encoder() -> str:
    """
    Resolve the effective FFmpeg video encoder.

    Returns "h264_nvenc" or "libx264".

    Raises RuntimeError if VIDEO_ENCODER=gpu but NVENC is unavailable.
    """
    if not use_gpu():
        logger.debug("device: USE_GPU=false — using libx264")
        return "libx264"

    setting = video_encoder_setting()

    if setting == "cpu":
        return "libx264"

    if setting == "gpu":
        if not _nvenc_available():
            raise RuntimeError(
                "VIDEO_ENCODER=gpu but h264_nvenc is not available. "
                "Ensure NVIDIA drivers and FFmpeg with NVENC support are installed, "
                "or set VIDEO_ENCODER=auto to fall back to libx264."
            )
        return "h264_nvenc"

    # auto (default)
    return "h264_nvenc" if _nvenc_available() else "libx264"


# ── Encoder-specific FFmpeg options ──────────────────────────────────────────

def encoder_options(encoder: str) -> list[str]:
    """
    Return encoder-specific FFmpeg flags for the given encoder name.

    libx264:    -crf 18 -preset fast  (quality-based, CPU)
    h264_nvenc: -rc vbr -cq 19 -preset p4 -profile:v high
                (NVENC quality mode; p4 = balanced quality/speed)

    These options are intentionally conservative — they produce output
    compatible with standard H.264 decoders on all platforms.
    """
    if encoder == "h264_nvenc":
        return ["-rc", "vbr", "-cq", "19", "-preset", "p4", "-profile:v", "high"]
    # libx264 default
    return ["-crf", "18", "-preset", "fast"]


# ── GPU job metadata ──────────────────────────────────────────────────────────

def collect_gpu_metadata() -> dict:
    """
    Collect GPU/device metadata for job recording.

    Returns a dict with:
        device          — resolved device string ("cuda" or "cpu")
        gpu_enabled     — bool
        encoder         — resolved encoder string
        whisper_model   — configured model name
        cuda_available  — bool (raw CUDA probe result)
        gpu_name        — NVIDIA GPU name if available, else None

    Safe to call even when torch/CUDA are not installed.
    Never raises.
    """
    try:
        device = resolve_device()
    except RuntimeError:
        device = "cpu"

    try:
        encoder = resolve_video_encoder()
    except RuntimeError:
        encoder = "libx264"

    gpu_name = None
    if _cuda_available():
        try:
            import torch
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            pass

    return {
        "device":        device,
        "gpu_enabled":   device == "cuda",
        "encoder":       encoder,
        "whisper_model": whisper_model_name(),
        "cuda_available": _cuda_available(),
        "gpu_name":      gpu_name,
    }
