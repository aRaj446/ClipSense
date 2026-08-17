"""
Tests for TrailerComposer — MoviePy composition layer (Chunk 3a).

All tests that require actual video I/O create a real synthetic .mp4 via
FFmpeg (a 3-second colour-bar clip) so MoviePy can open a genuine file.
Tests that only exercise the public API surface (empty plan, missing source,
TransitionConfig validation, ComposeResult shape) need no video at all.

Covers:
    1.  TransitionConfig — default values
    2.  TransitionConfig — cut
    3.  TransitionConfig — fade
    4.  TransitionConfig — crossfade custom duration
    5.  TransitionConfig — invalid type raises ValueError
    6.  TransitionConfig — negative duration raises ValueError
    7.  TransitionConfig — zero duration allowed
    8.  ComposeResult — failure defaults
    9.  ComposeResult — success fields
    10. TrailerComposer — default transition is crossfade
    11. TrailerComposer — custom transition stored
    12. TrailerComposer — source path normalised to absolute
    13. compose() — empty plan returns failure, no file created
    14. compose() — missing source file returns failure
    15. compose() — single clip, cut transition
    16. compose() — single clip, fade transition
    17. compose() — single clip, crossfade transition
    18. compose() — multiple clips, cut transition
    19. compose() — multiple clips, crossfade transition
    20. compose() — trimming: start/end respected
    21. compose() — invalid timestamps (end <= start) skipped, rest composed
    22. compose() — all clips invalid returns failure
    23. compose() — clip clamped to source duration
    24. compose() — clip_timeline_offsets length matches surviving clips
    25. compose() — clip_durations length matches surviving clips
    26. compose() — surviving_clips excludes skipped clips
    27. compose() — output file exists on success
    28. compose() — output file is a valid .mp4 (FFmpeg can probe it)
    29. compose() — composition_duration_secs > 0 on success
    30. compose() — peak_memory_mb >= 0 on success
    31. compose() — audio composition: music_path mixed in
    32. compose() — audio composition: missing music_path ignored gracefully
    33. compose() — cleanup: no handles leak after success
    34. compose() — cleanup: no handles leak after failure
    35. _close_all — safe with empty inputs
    36. _get_source — caches handle on second call
    37. _get_source — returns None for non-existent file

Run with:
    cd backend
    python -m pytest tests/test_trailer_composer.py -v
"""

import os
import re
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.trailer_composer import (
    ComposeResult,
    TrailerComposer,
    TransitionConfig,
    DEFAULT_CROSSFADE_DURATION,
    TRANSITION_CUT,
    TRANSITION_FADE,
    TRANSITION_CROSSFADE,
)
from app.schemas.feedback import TrailerClip, TrailerEditingPlan


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _make_synthetic_video(path: str, duration: float = 3.0, width: int = 320, height: int = 240) -> None:
    """
    Create a minimal real .mp4 using FFmpeg colour-bar source.
    No external media required — purely synthetic.
    Raises pytest.skip if FFmpeg is unavailable.
    """
    ffmpeg = _get_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", f"color=c=blue:size={width}x{height}:rate=30:duration={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
        "-c:a", "aac", "-b:a", "64k",
        "-t", str(duration),
        path,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=30)
    if r.returncode != 0:
        pytest.skip(f"FFmpeg could not create synthetic video: {r.stderr.decode()[:200]}")


def _probe_duration(path: str) -> float:
    """Return video duration in seconds via FFprobe."""
    ffmpeg = _get_ffmpeg()
    r = subprocess.run([ffmpeg, "-i", path], capture_output=True, text=True, timeout=15)
    m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", r.stderr)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _make_clip(start: float, end: float, sentiment: str = "Positive") -> TrailerClip:
    return TrailerClip(
        start_time=start,
        end_time=end,
        reason="test",
        topic="Test",
        sentiment=sentiment,
    )


def _make_plan(*clips: TrailerClip) -> TrailerEditingPlan:
    total = sum(c.end_time - c.start_time for c in clips)
    return TrailerEditingPlan(
        clips=list(clips),
        target_duration=total,
        rationale="test plan",
    )


# ── 1–7: TransitionConfig ─────────────────────────────────────────────────────

def test_transition_config_defaults():
    tc = TransitionConfig()
    assert tc.type == TRANSITION_CROSSFADE
    assert tc.duration == DEFAULT_CROSSFADE_DURATION


def test_transition_config_cut():
    tc = TransitionConfig(type=TRANSITION_CUT)
    assert tc.type == TRANSITION_CUT


def test_transition_config_fade():
    tc = TransitionConfig(type=TRANSITION_FADE, duration=0.5)
    assert tc.type == TRANSITION_FADE
    assert tc.duration == 0.5


def test_transition_config_crossfade_custom_duration():
    tc = TransitionConfig(type=TRANSITION_CROSSFADE, duration=0.4)
    assert tc.duration == 0.4


def test_transition_config_invalid_type_raises():
    with pytest.raises(ValueError, match="must be one of"):
        TransitionConfig(type="wipe")


def test_transition_config_negative_duration_raises():
    with pytest.raises(ValueError, match="must be >= 0"):
        TransitionConfig(type=TRANSITION_FADE, duration=-0.1)


def test_transition_config_zero_duration_allowed():
    tc = TransitionConfig(type=TRANSITION_FADE, duration=0.0)
    assert tc.duration == 0.0


# ── 8–9: ComposeResult ────────────────────────────────────────────────────────

def test_compose_result_failure_defaults():
    r = ComposeResult(success=False, error="something went wrong")
    assert r.success is False
    assert r.output_path == ""
    assert r.clip_timeline_offsets == []
    assert r.clip_durations == []
    assert r.surviving_clips == []
    assert r.error == "something went wrong"
    assert r.composition_duration_secs == 0.0
    assert r.peak_memory_mb == 0.0


def test_compose_result_success_fields():
    r = ComposeResult(
        success=True,
        output_path="/tmp/out.mp4",
        clip_timeline_offsets=[0.0, 8.0],
        clip_durations=[9.0, 9.0],
    )
    assert r.success is True
    assert r.output_path == "/tmp/out.mp4"
    assert len(r.clip_timeline_offsets) == 2
    assert len(r.clip_durations) == 2


# ── 10–12: TrailerComposer instantiation ──────────────────────────────────────

def test_composer_default_transition_is_crossfade():
    c = TrailerComposer(source_path="/fake/path.mp4")
    assert c._transition.type == TRANSITION_CROSSFADE


def test_composer_custom_transition_stored():
    tc = TransitionConfig(type=TRANSITION_CUT)
    c = TrailerComposer(source_path="/fake/path.mp4", transition=tc)
    assert c._transition.type == TRANSITION_CUT


def test_composer_source_path_normalised():
    raw = "/fake/../fake/path.mp4"
    c = TrailerComposer(source_path=raw)
    assert c._source_path == os.path.normpath(os.path.abspath(raw))


# ── 13–14: compose() without real video ──────────────────────────────────────

def test_compose_empty_plan_returns_failure():
    c = TrailerComposer(source_path="/fake/path.mp4")
    plan = _make_plan()
    result = c.compose(plan, output_path="/tmp/should_not_exist.mp4")
    assert result.success is False
    assert result.output_path == ""
    assert not os.path.exists("/tmp/should_not_exist.mp4")


def test_compose_missing_source_returns_failure(tmp_path):
    c = TrailerComposer(source_path=str(tmp_path / "nonexistent.mp4"))
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is False
    assert result.output_path == ""
    assert len(result.error) > 0
    assert not os.path.exists(out)


# ── 15–20: compose() with real synthetic video ────────────────────────────────

@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory):
    """3-second 320x240 synthetic .mp4 shared across all real-video tests."""
    d = tmp_path_factory.mktemp("synth")
    path = str(d / "source.mp4")
    _make_synthetic_video(path, duration=3.0)
    return path


def test_compose_single_clip_cut(synthetic_video, tmp_path):
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_cut.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert os.path.exists(out)
    assert len(result.surviving_clips) == 1
    assert len(result.clip_timeline_offsets) == 1
    assert result.clip_timeline_offsets[0] == pytest.approx(0.0)


def test_compose_single_clip_fade(synthetic_video, tmp_path):
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_FADE, duration=0.3),
    )
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_fade.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert os.path.exists(out)


def test_compose_single_clip_crossfade(synthetic_video, tmp_path):
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=0.5),
    )
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_xfade_single.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert os.path.exists(out)


def test_compose_multiple_clips_cut(synthetic_video, tmp_path):
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(_make_clip(0.0, 1.0), _make_clip(1.0, 2.5))
    out = str(tmp_path / "out_multi_cut.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 2
    # cut: second clip starts exactly where first ends
    assert result.clip_timeline_offsets[1] == pytest.approx(
        result.clip_timeline_offsets[0] + result.clip_durations[0], abs=0.1
    )


def test_compose_multiple_clips_crossfade(synthetic_video, tmp_path):
    xfade_d = 0.3
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CROSSFADE, duration=xfade_d),
    )
    plan = _make_plan(_make_clip(0.0, 1.5), _make_clip(1.5, 3.0))
    out = str(tmp_path / "out_multi_xfade.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 2
    # crossfade: second clip starts (first_dur - xfade_d) into timeline
    expected_offset = result.clip_durations[0] - xfade_d
    assert result.clip_timeline_offsets[1] == pytest.approx(expected_offset, abs=0.1)


# ── 20: Trimming ──────────────────────────────────────────────────────────────

def test_compose_trimming_respected(synthetic_video, tmp_path):
    """Subclip start/end must be honoured — output duration ≈ requested range."""
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(_make_clip(0.5, 2.0))   # 1.5 s window
    out = str(tmp_path / "out_trim.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert result.clip_durations[0] == pytest.approx(1.5, abs=0.15)


# ── 21–22: Invalid timestamps ─────────────────────────────────────────────────

def test_compose_invalid_clip_skipped_rest_composed(synthetic_video, tmp_path):
    """A clip with end <= start is skipped; valid clips still compose."""
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(
        _make_clip(5.0, 2.0),   # invalid: end < start
        _make_clip(0.0, 2.0),   # valid
    )
    out = str(tmp_path / "out_skip_invalid.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 1


def test_compose_all_clips_invalid_returns_failure(synthetic_video, tmp_path):
    """If every clip is invalid, compose() must return failure."""
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(
        _make_clip(5.0, 2.0),   # end < start
        _make_clip(3.0, 3.0),   # zero duration
    )
    out = str(tmp_path / "out_all_invalid.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is False
    assert not os.path.exists(out)


# ── 23: Clamping to source duration ──────────────────────────────────────────

def test_compose_clip_clamped_to_source_duration(synthetic_video, tmp_path):
    """A clip that extends beyond source duration is clamped, not errored."""
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    # Source is 3 s; request 1.0–99.0 — should clamp to 1.0–3.0
    plan = _make_plan(_make_clip(1.0, 99.0))
    out = str(tmp_path / "out_clamped.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert result.clip_durations[0] == pytest.approx(2.0, abs=0.2)


# ── 24–26: Offset / duration / surviving_clips parallel arrays ────────────────

def test_compose_offsets_length_matches_surviving(synthetic_video, tmp_path):
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 1.0), _make_clip(1.0, 2.5))
    out = str(tmp_path / "out_parallel.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.clip_timeline_offsets) == len(result.surviving_clips)


def test_compose_durations_length_matches_surviving(synthetic_video, tmp_path):
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 1.0), _make_clip(1.0, 2.5))
    out = str(tmp_path / "out_dur_parallel.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.clip_durations) == len(result.surviving_clips)


def test_compose_surviving_clips_excludes_skipped(synthetic_video, tmp_path):
    c = TrailerComposer(
        source_path=synthetic_video,
        transition=TransitionConfig(type=TRANSITION_CUT),
    )
    plan = _make_plan(
        _make_clip(10.0, 5.0),  # invalid — skipped
        _make_clip(0.0, 1.5),   # valid
        _make_clip(1.5, 3.0),   # valid
    )
    out = str(tmp_path / "out_surviving.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert len(result.surviving_clips) == 2


# ── 27–28: Output file validation ────────────────────────────────────────────

def test_compose_output_file_exists(synthetic_video, tmp_path):
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_exists.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 0


def test_compose_output_is_valid_mp4(synthetic_video, tmp_path):
    """FFmpeg must be able to probe the output file without error."""
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_valid.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    dur = _probe_duration(out)
    assert dur > 0.0, "FFmpeg could not probe output duration"


# ── 29–30: Timing and memory fields ──────────────────────────────────────────

def test_compose_duration_recorded(synthetic_video, tmp_path):
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_timing.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert result.composition_duration_secs > 0.0


def test_compose_peak_memory_non_negative(synthetic_video, tmp_path):
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_mem.mp4")
    result = c.compose(plan, output_path=out)
    assert result.success is True, result.error
    assert result.peak_memory_mb >= 0.0


# ── 31–32: Audio composition ──────────────────────────────────────────────────

def test_compose_music_path_mixed_in(synthetic_video, tmp_path):
    """When a valid music file is provided, compose() must still succeed."""
    # Create a synthetic audio-only file as music
    ffmpeg = _get_ffmpeg()
    music_path = str(tmp_path / "music.aac")
    r = subprocess.run([
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=5",
        "-c:a", "aac", "-b:a", "64k",
        music_path,
    ], capture_output=True, timeout=15)
    if r.returncode != 0:
        pytest.skip("Could not create synthetic music file")

    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_music.mp4")
    result = c.compose(plan, output_path=out, music_path=music_path)
    assert result.success is True, result.error
    assert os.path.isfile(out)


def test_compose_missing_music_path_ignored(synthetic_video, tmp_path):
    """A music_path that does not exist must be silently ignored."""
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_no_music.mp4")
    result = c.compose(
        plan,
        output_path=out,
        music_path=str(tmp_path / "nonexistent_music.aac"),
    )
    assert result.success is True, result.error


# ── 33–34: Resource cleanup ───────────────────────────────────────────────────

def test_compose_no_handle_leak_after_success(synthetic_video, tmp_path):
    """
    After a successful compose(), _open_sources must be empty.
    We verify by patching _close_all and checking it was called.
    """
    import unittest.mock as mock
    c = TrailerComposer(source_path=synthetic_video)
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_leak_ok.mp4")

    original_close = TrailerComposer._close_all
    close_calls = []

    def _patched_close(mv, audio, sources):
        close_calls.append((len(mv), len(audio), len(sources)))
        original_close(mv, audio, sources)

    with mock.patch.object(TrailerComposer, "_close_all", staticmethod(_patched_close)):
        result = c.compose(plan, output_path=out)

    assert result.success is True, result.error
    assert len(close_calls) == 1, "_close_all must be called exactly once"


def test_compose_no_handle_leak_after_failure(tmp_path):
    """After a failed compose() (missing source), _close_all must still run."""
    import unittest.mock as mock
    c = TrailerComposer(source_path=str(tmp_path / "missing.mp4"))
    plan = _make_plan(_make_clip(0.0, 2.0))
    out = str(tmp_path / "out_leak_fail.mp4")

    close_calls = []
    original_close = TrailerComposer._close_all

    def _patched_close(mv, audio, sources):
        close_calls.append(True)
        original_close(mv, audio, sources)

    with mock.patch.object(TrailerComposer, "_close_all", staticmethod(_patched_close)):
        result = c.compose(plan, output_path=out)

    assert result.success is False
    assert len(close_calls) == 1, "_close_all must be called even on failure"


# ── 35: _close_all edge cases ─────────────────────────────────────────────────

def test_close_all_safe_with_empty_inputs():
    TrailerComposer._close_all([], [], {})  # must not raise


def test_close_all_safe_with_already_closed_handle():
    """_close_all must not raise even if a handle's close() raises."""
    class _BadHandle:
        def close(self):
            raise RuntimeError("already closed")

    TrailerComposer._close_all([_BadHandle()], [_BadHandle()], {"k": _BadHandle()})


# ── 36–37: _get_source caching ────────────────────────────────────────────────

def test_get_source_caches_handle(synthetic_video):
    """Second call with the same path must return the identical object."""
    c = TrailerComposer(source_path=synthetic_video)
    cache: dict = {}
    h1 = c._get_source(synthetic_video, cache)
    h2 = c._get_source(synthetic_video, cache)
    assert h1 is h2, "Handle must be reused from cache"
    assert len(cache) == 1
    # cleanup
    try:
        h1.close()
    except Exception:
        pass


def test_get_source_returns_none_for_missing_file(tmp_path):
    c = TrailerComposer(source_path=str(tmp_path / "missing.mp4"))
    cache: dict = {}
    result = c._get_source(str(tmp_path / "missing.mp4"), cache)
    assert result is None
    assert len(cache) == 0
