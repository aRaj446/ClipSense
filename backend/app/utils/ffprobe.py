import subprocess
import json
from typing import Optional


def extract_video_metadata(file_path: str) -> dict:
    """Extract video metadata using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_streams", "-show_format",
            file_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}

        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        fmt = data.get("format", {})

        if not video_stream:
            return {}

        return {
            "duration": _safe_float(fmt.get("duration")),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": _parse_fps(video_stream.get("r_frame_rate", "0/1")),
            "codec": video_stream.get("codec_name"),
            "bitrate": _safe_int(fmt.get("bit_rate")),
        }
    except Exception:
        return {}


def _parse_fps(fps_str: str) -> Optional[float]:
    try:
        num, den = fps_str.split("/")
        return round(int(num) / int(den), 2) if int(den) != 0 else None
    except Exception:
        return None


def _safe_float(val) -> Optional[float]:
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    try:
        return int(val)
    except (TypeError, ValueError):
        return None
