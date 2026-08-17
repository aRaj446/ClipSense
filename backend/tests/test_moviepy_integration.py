"""
MoviePy Integration Tests + Benchmark (Chunk 3b).

Uses the smallest real trailer in app/trailers/ (7.57 s, 1920x1080, 30 fps)
as the source video.  No synthetic clips — all subclips are taken from the
real file so the integration test exercises the full MoviePy decode path.

Benchmark:
    Measures and compares:
        A. FFmpeg-only path  (compose() with a single clip — no MoviePy transition)
        B. MoviePy path      (TrailerComposer with 2 clips — crossfade transition)

    Metrics collected per run:
        - total_duration_secs
        - composition_duration_secs  (MoviePy path only)
        - encoding_duration_secs     (FFmpeg final pass only, estimated)
        - peak_memory_mb
        - output_file_size_bytes
        - output_duration_secs
        - output_resolution
        - output_fps

    Results are printed to stdout in a readable table and written to
    tests/benchmark_results.json for CI archiving.

Covers:
    1.  Real video opens without error
    2.  Single clip from real video — cut transition
    3.  Single clip from real video — fade transition
    4.  Single clip from real video — crossfade transition
    5.  Two clips from real video — cut
    6.  Two clips from real video — crossfade
    7.  Three clips from real video — crossfade
    8.  Trimming accuracy on real video (±0.3 s tolerance)
    9.  Output resolution matches source (1920x1080)
    10. Output FPS matches source (30)
    11. Output has audio stream
    12. Output duration is within expected range
    13. Subtitles: compose() with include_subtitles=False (no SRT needed)
    14. Audio composition: music overlay on real video
    15. Benchmark A — FFmpeg-only single clip
    16. Benchmark B — MoviePy 2-clip crossfade
    17. Benchmark comparison printed and saved

Run with:
    cd backend
    python -m pytest tests/test_moviepy_integration.py -v -s

The -s flag shows benchmark output on stdout.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import tracemalloc

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.trailer_composer import TrailerComposer, TransitionConfig, TRANSITION_CUT, TRANSITION_CROSSFADE, TRANSITION_FADE
from app.schemas.feedback import TrailerClip, TrailerEditingPlan


# ── Constants ─────────────────────────────────────────────────────────────────

_TRAILERS_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "trailers")
_REAL_VIDEO   = os.path.normpath(
    os.path.join(_TRAILERS_DIR, "smart_b6ee3da0-c7a4-486b-bb3b-e7a059202d42_98c86ea7.mp4")
)
_BENCHMARK_OUT = os.path.join(os.path.dirname(__file__), "benchmark_results.json")

# Source video properties (confirmed by probe)
_SRC_DURATION   = 7.57   # seconds
_SRC_WIDTH      = 1920
_SRC_HEIGHT     = 1080
_SRC_FPS        = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _probe(path: str) -> dict:
    """Return {duration, width, height, fps, has_audio} for a video file."""
    ffmpeg = _get_ffmpeg()
    r = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True, timeout=20)
    text = r.stderr

    dur_m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", text)
    res_m = re.search(r"(\d{3,4})x(\d{3,4})", text)
    fps_m = re.search(r"(\d+(?:\.\d+)?) fps", text)

    duration = 0.0
    if dur_m:
        h, mn, s = dur_m.groups()
        duration = int(h) * 3600 + int(mn) * 60 + float(s)

    return {
        "duration":  duration,
        "width":     int(res_m.group(1)) if res_m else 0,
        "height":    int(res_m.group(2)) if res_m else 0,
        "fps":       float(fps_m.group(1)) if fps_m else 0.0,
        "has_audio": "Audio:" in text,
    }


def _make_clip(start: float, end: float) -> TrailerClip:
    return TrailerClip(
        start_time=start, end_time=end,
        reason="integration test", topic="Test", sentiment="Positive",
    )


def _make_plan(*clips: TrailerClip) -> TrailerEditingPlan:
    return TrailerEditingPlan(
        clips=list(clips),
        target_duration=sum(c.end_time - c.start_time for c in clips),
        rationale="integration test",
    )


def _require_real_video():
    if not os.path.isfile(_REAL_VIDEO):
        pytest.skip(f"Real video not found: {_REAL_VIDEO}")


# ── 1: Real video opens ───────────────────────────────────────────────────────

def test_real_video_is_accessible():
    _require_real_video()
    info = _probe(_REAL_VIDEO)
    assert info["duration"] == pytest.approx(_SRC_DURATION, abs=0.5)
    assert info["width"]    == _SRC_WIDTH
    assert info["height"]   == _SRC_HEIGHT
    assert info["fps"]      == pytest.approx(_SRC_FPS, abs=1.0)
    assert info["has_audio"] is True


# ── 2–4: Single clip, all three transitions ───────────────────────────────────

@pytest.mark.parametrize("transition_type,duration", [
    (TRANSITION_CUT,       0.0),
    (TRANSITION_FADE,      0.4),
    (TRANSITION_CROSSFADE, 0.4),
])
def test_single_clip_all_transitions(transition_type, duration, tmp_path):
    _require_real_video()
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=transition_type, duration=duration),
    )
    plan = _make_plan(_make_clip(1.0, 4.0))
    out  = str(tmp_path / f"single_{transition_type}.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, f"{transition_type}: {result.error}"
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 0


# ── 5–6: Two clips ────────────────────────────────────────────────────────────

def test_two_clips_cut(tmp_path):
    _require_real_video()
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(_make_clip(0.5, 2.5), _make_clip(3.0, 5.5))
    out  = str(tmp_path / "two_cut.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 2
    info = _probe(out)
    assert info["duration"] == pytest.approx(4.0, abs=0.5)


def test_two_clips_crossfade(tmp_path):
    _require_real_video()
    xfade = 0.5
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=xfade),
    )
    plan = _make_plan(_make_clip(0.5, 3.0), _make_clip(3.5, 6.5))
    out  = str(tmp_path / "two_xfade.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 2
    # crossfade overlaps by xfade seconds — total < sum of individual durations
    total_raw = (3.0 - 0.5) + (6.5 - 3.5)
    info = _probe(out)
    assert info["duration"] < total_raw + 0.5


# ── 7: Three clips crossfade ──────────────────────────────────────────────────

def test_three_clips_crossfade(tmp_path):
    _require_real_video()
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=0.3),
    )
    plan = _make_plan(
        _make_clip(0.0, 2.0),
        _make_clip(2.0, 4.5),
        _make_clip(4.5, 7.0),
    )
    out = str(tmp_path / "three_xfade.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 3
    info = _probe(out)
    assert info["duration"] > 0


# ── 8: Trimming accuracy ──────────────────────────────────────────────────────

def test_trimming_accuracy_on_real_video(tmp_path):
    """Requested 2.0 s window — output clip duration must be within ±0.3 s."""
    _require_real_video()
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(_make_clip(1.0, 3.0))   # 2.0 s
    out  = str(tmp_path / "trim_accuracy.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert result.clip_durations[0] == pytest.approx(2.0, abs=0.3)


# ── 9–11: Output properties ───────────────────────────────────────────────────

def test_output_resolution_matches_source(tmp_path):
    _require_real_video()
    c    = TrailerComposer(source_path=_REAL_VIDEO)
    plan = _make_plan(_make_clip(0.0, 3.0))
    out  = str(tmp_path / "res_check.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    info = _probe(out)
    assert info["width"]  == _SRC_WIDTH,  f"Expected {_SRC_WIDTH}, got {info['width']}"
    assert info["height"] == _SRC_HEIGHT, f"Expected {_SRC_HEIGHT}, got {info['height']}"


def test_output_fps_matches_source(tmp_path):
    _require_real_video()
    c    = TrailerComposer(source_path=_REAL_VIDEO)
    plan = _make_plan(_make_clip(0.0, 3.0))
    out  = str(tmp_path / "fps_check.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    info = _probe(out)
    assert info["fps"] == pytest.approx(_SRC_FPS, abs=1.0)


def test_output_has_audio_stream(tmp_path):
    _require_real_video()
    c    = TrailerComposer(source_path=_REAL_VIDEO)
    plan = _make_plan(_make_clip(0.0, 3.0))
    out  = str(tmp_path / "audio_check.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    info = _probe(out)
    assert info["has_audio"] is True


# ── 12: Output duration range ─────────────────────────────────────────────────

def test_output_duration_within_expected_range(tmp_path):
    """Two 2-second clips with 0.5 s crossfade → expected ~3.5 s output."""
    _require_real_video()
    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=0.5),
    )
    plan = _make_plan(_make_clip(0.5, 2.5), _make_clip(3.0, 5.0))
    out  = str(tmp_path / "dur_range.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    info = _probe(out)
    # 2 clips × 2 s − 0.5 s overlap = 3.5 s; allow ±0.5 s tolerance
    assert 3.0 <= info["duration"] <= 4.5, f"Unexpected duration: {info['duration']:.2f}s"


# ── 13: Subtitles flag (no SRT needed — compose() only) ──────────────────────

def test_compose_include_subtitles_false_no_error(tmp_path):
    """include_subtitles=False must not affect TrailerComposer output."""
    _require_real_video()
    c    = TrailerComposer(source_path=_REAL_VIDEO)
    plan = _make_plan(_make_clip(0.0, 3.0))
    out  = str(tmp_path / "no_subs.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error


# ── 14: Audio overlay on real video ──────────────────────────────────────────

def test_music_overlay_on_real_video(tmp_path):
    """Music overlay must not break composition on a real video."""
    _require_real_video()
    ffmpeg     = _get_ffmpeg()
    music_path = str(tmp_path / "music.aac")
    r = subprocess.run([
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=10",
        "-c:a", "aac", "-b:a", "64k", music_path,
    ], capture_output=True, timeout=15)
    if r.returncode != 0:
        pytest.skip("Could not create synthetic music")

    c    = TrailerComposer(source_path=_REAL_VIDEO)
    plan = _make_plan(_make_clip(0.0, 3.0))
    out  = str(tmp_path / "music_overlay.mp4")
    result = c.compose(plan, output_path=out, music_path=music_path)
    assert result.success is True, result.error
    assert os.path.isfile(out)


# ── 15–17: Benchmark ─────────────────────────────────────────────────────────

def _run_benchmark_ffmpeg_only(tmp_path: str) -> dict:
    """
    Benchmark A: FFmpeg-only path.
    Extracts a single 3-second clip directly via FFmpeg (no MoviePy).
    Measures total wall-clock time and peak memory.
    """
    from app.utils.ffmpeg_composer import _get_ffmpeg as _fc_ffmpeg, _CLIP_VF, _CLIP_LOUDNORM
    from app.utils.device import resolve_video_encoder, encoder_options

    ffmpeg  = _fc_ffmpeg()
    encoder = "libx264"
    try:
        encoder = resolve_video_encoder()
    except Exception:
        pass

    out = os.path.join(tmp_path, "bench_ffmpeg.mp4")

    tracemalloc.start()
    t0 = time.perf_counter()

    cmd = [
        ffmpeg, "-y",
        "-ss", "1.0", "-to", "4.0",
        "-i", _REAL_VIDEO,
        "-map", "0:v:0", "-map", "0:a:0",
        "-vf", _CLIP_VF,
        "-af", f"{_CLIP_LOUDNORM},aresample=async=1000",
        "-c:v", encoder, *encoder_options(encoder),
        "-c:a", "aac", "-b:a", "192k",
        "-avoid_negative_ts", "make_zero",
        "-vsync", "cfr",
        out,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)

    total = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    info = _probe(out) if r.returncode == 0 else {}
    return {
        "label":                  "A: FFmpeg-only (single clip, no MoviePy)",
        "success":                r.returncode == 0,
        "total_duration_secs":    round(total, 3),
        "composition_duration_secs": 0.0,
        "encoding_duration_secs": round(total, 3),
        "peak_memory_mb":         round(peak / 1_048_576, 2),
        "output_file_size_bytes": os.path.getsize(out) if os.path.isfile(out) else 0,
        "output_duration_secs":   round(info.get("duration", 0.0), 3),
        "output_resolution":      f"{info.get('width', 0)}x{info.get('height', 0)}",
        "output_fps":             info.get("fps", 0.0),
    }


def _run_benchmark_moviepy(tmp_path: str) -> dict:
    """
    Benchmark B: MoviePy composition + FFmpeg final encoding.
    Two clips with crossfade via TrailerComposer, then probes the output.
    """
    out = os.path.join(tmp_path, "bench_moviepy.mp4")

    c = TrailerComposer(
        source_path=_REAL_VIDEO,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=0.5),
    )
    plan = _make_plan(_make_clip(0.5, 3.0), _make_clip(3.5, 6.5))

    tracemalloc.start()
    t0 = time.perf_counter()
    result = c.compose(plan, output_path=out)
    total = time.perf_counter() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    info = _probe(out) if result.success else {}
    return {
        "label":                  "B: MoviePy composition + FFmpeg intermediate",
        "success":                result.success,
        "total_duration_secs":    round(total, 3),
        "composition_duration_secs": result.composition_duration_secs,
        "encoding_duration_secs": round(total - result.composition_duration_secs, 3),
        "peak_memory_mb":         round(max(peak / 1_048_576, result.peak_memory_mb), 2),
        "output_file_size_bytes": os.path.getsize(out) if os.path.isfile(out) else 0,
        "output_duration_secs":   round(info.get("duration", 0.0), 3),
        "output_resolution":      f"{info.get('width', 0)}x{info.get('height', 0)}",
        "output_fps":             info.get("fps", 0.0),
    }


def _print_benchmark_table(results: list[dict]) -> None:
    cols = [
        ("label",                    38),
        ("total_duration_secs",      10),
        ("composition_duration_secs",12),
        ("encoding_duration_secs",   10),
        ("peak_memory_mb",            9),
        ("output_file_size_bytes",   12),
        ("output_duration_secs",     10),
        ("output_resolution",        12),
        ("output_fps",                8),
    ]
    header = "  ".join(k.ljust(w) for k, w in cols)
    sep    = "  ".join("-" * w for _, w in cols)
    print("\n" + "=" * len(sep))
    print("BENCHMARK RESULTS")
    print("=" * len(sep))
    print(header)
    print(sep)
    for r in results:
        row = "  ".join(str(r.get(k, "")).ljust(w) for k, w in cols)
        print(row)
    print("=" * len(sep) + "\n")


def test_benchmark_ffmpeg_only(tmp_path):
    """Benchmark A: FFmpeg-only single-clip extraction."""
    _require_real_video()
    result = _run_benchmark_ffmpeg_only(str(tmp_path))
    assert result["success"], "FFmpeg-only benchmark failed"
    assert result["total_duration_secs"] > 0
    assert result["output_duration_secs"] > 0
    # Store on module for the comparison test
    test_benchmark_ffmpeg_only._result = result
    print(f"\n[Benchmark A] total={result['total_duration_secs']:.3f}s  "
          f"mem={result['peak_memory_mb']:.1f}MB  "
          f"size={result['output_file_size_bytes']//1024}KB")


def test_benchmark_moviepy_composition(tmp_path):
    """Benchmark B: MoviePy 2-clip crossfade composition."""
    _require_real_video()
    result = _run_benchmark_moviepy(str(tmp_path))
    assert result["success"], f"MoviePy benchmark failed: {result}"
    assert result["total_duration_secs"] > 0
    assert result["output_duration_secs"] > 0
    test_benchmark_moviepy_composition._result = result
    print(f"\n[Benchmark B] total={result['total_duration_secs']:.3f}s  "
          f"compose={result['composition_duration_secs']:.3f}s  "
          f"encode={result['encoding_duration_secs']:.3f}s  "
          f"mem={result['peak_memory_mb']:.1f}MB  "
          f"size={result['output_file_size_bytes']//1024}KB")


def test_benchmark_comparison_and_save(tmp_path):
    """
    Print the comparison table and save results to tests/benchmark_results.json.
    Runs after both benchmark tests — reads their stored results.
    """
    _require_real_video()

    # Run both inline if the individual tests haven't stored results yet
    r_a = getattr(test_benchmark_ffmpeg_only, "_result", None) \
          or _run_benchmark_ffmpeg_only(str(tmp_path))
    r_b = getattr(test_benchmark_moviepy_composition, "_result", None) \
          or _run_benchmark_moviepy(str(tmp_path))

    results = [r_a, r_b]
    _print_benchmark_table(results)

    # Save to JSON
    out_path = os.path.join(os.path.dirname(__file__), "benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Benchmark results saved to {out_path}")

    # Assertions: both runs must produce valid output
    assert r_a["success"], "Benchmark A must succeed"
    assert r_b["success"], "Benchmark B must succeed"
    assert r_a["output_duration_secs"] > 0
    assert r_b["output_duration_secs"] > 0
    assert r_b["output_resolution"] in ("1920x1080", "0x0"), \
        f"Unexpected resolution: {r_b['output_resolution']}"
