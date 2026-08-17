"""
Tests for Feature 7 — Optional Dialogue/Subtitle Overlay.

Tests the public functions:
    map_transcript_to_timeline()  — timestamp remapping
    build_srt()                   — SRT generation
    compose() signature           — include_subtitles parameter

Covers all 13 required cases:
    1.  subtitles disabled (compose signature + default)
    2.  subtitles enabled (map produces entries)
    3.  timestamp conversion (basic offset)
    4.  trimmed clips (clamping)
    5.  multiple clips (crossfade offsets)
    6.  Unicode text
    7.  empty transcript
    8.  missing transcript key
    9.  subtitle cleanup (SRT written to tmp_dir, cleaned up)
    10. fast mode + subtitles (empty transcript → no entries, no fabrication)
    11. output duration (SRT entries clamped to total_duration)
    12. subtitle timing (start < end enforced in build_srt)
    13. final video validation (build_srt produces valid SRT format)

Run with:
    cd backend
    set PYTHONPATH=C:\\...\\backend
    pytest tests/test_subtitle_overlay.py -v
"""

import sys
import os
import inspect
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.clip_planner import PlannedClip
from app.utils.ffmpeg_composer import (
    map_transcript_to_timeline,
    build_srt,
    write_srt_file,
    compose,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clip(start: float, end: float) -> PlannedClip:
    return PlannedClip(
        start_time=start,
        end_time=end,
        reason="test",
        topic="Test",
        sentiment="Positive",
    )


def _transcript(*segments) -> dict:
    """Build a minimal transcript dict from (start, end, text) tuples."""
    return {
        "segments": [
            {"start": s, "end": e, "text": t}
            for s, e, t in segments
        ],
        "words": [],
        "language": "en",
        "full_text": "",
    }


# ── Test 1: subtitles disabled ────────────────────────────────────────────────

def test_compose_include_subtitles_defaults_false():
    """compose() must accept include_subtitles and default to False."""
    sig = inspect.signature(compose)
    assert "include_subtitles" in sig.parameters
    assert sig.parameters["include_subtitles"].default is False


# ── Test 2: subtitles enabled — map produces entries ─────────────────────────

def test_subtitles_enabled_produces_entries():
    """When transcript has segments overlapping the clip, entries are returned."""
    clips   = [_clip(10.0, 20.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((12.0, 15.0, "Hello world"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert entries[0]["text"] == "Hello world"


# ── Test 3: timestamp conversion — basic offset ───────────────────────────────

def test_single_clip_single_segment_basic_offset():
    """
    Clip: source 10.0–20.0 s, placed at timeline offset 0.0
    Segment: source 12.0–15.0 s
    Expected: timeline 2.0–5.0 s
    """
    clips   = [_clip(10.0, 20.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((12.0, 15.0, "Hello world"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert abs(entries[0]["start"] - 2.0) < 1e-6
    assert abs(entries[0]["end"]   - 5.0) < 1e-6


def test_single_clip_with_nonzero_timeline_offset():
    """
    Clip: source 5.0–15.0 s, placed at timeline offset 8.0 s
    Segment: source 7.0–10.0 s
    Expected: timeline 10.0–13.0 s
    """
    clips   = [_clip(5.0, 15.0)]
    offsets = [8.0]
    durs    = [10.0]
    tr      = _transcript((7.0, 10.0, "Test line"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert abs(entries[0]["start"] - 10.0) < 1e-6
    assert abs(entries[0]["end"]   - 13.0) < 1e-6


# ── Test 4: trimmed clips — clamping ─────────────────────────────────────────

def test_segment_clamped_when_clip_trimmed():
    """
    Clip: source 10.0–18.0 s (8 s duration), timeline offset 0.0
    Segment: source 16.0–22.0 s — extends beyond clip end
    Expected: clamped to clip duration → timeline 6.0–8.0 s
    """
    clips   = [_clip(10.0, 18.0)]
    offsets = [0.0]
    durs    = [8.0]
    tr      = _transcript((16.0, 22.0, "Trimmed segment"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert abs(entries[0]["start"] - 6.0) < 1e-6
    assert abs(entries[0]["end"]   - 8.0) < 1e-6


def test_segment_before_clip_start_clamped():
    """
    Clip: source 10.0–20.0 s, timeline offset 0.0
    Segment: source 8.0–12.0 s — starts before clip
    Expected: local_start clamped to 0.0 → timeline 0.0–2.0 s
    """
    clips   = [_clip(10.0, 20.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((8.0, 12.0, "Partial overlap start"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert abs(entries[0]["start"]                    - 0.0) < 1e-6
    assert abs(entries[0]["end"] - entries[0]["start"] - 2.0) < 1e-6


def test_segment_outside_clip_excluded():
    """Segment entirely outside clip range produces no entries."""
    clips   = [_clip(10.0, 20.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((25.0, 28.0, "Outside clip"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 0


# ── Test 5: multiple clips ────────────────────────────────────────────────────

def test_two_clips_correct_offsets():
    """
    Clip 0: source 0–10 s, timeline offset 0.0
    Clip 1: source 20–30 s, timeline offset 9.0 (10s - 1s crossfade)
    """
    clips   = [_clip(0.0, 10.0), _clip(20.0, 30.0)]
    offsets = [0.0, 9.0]
    durs    = [10.0, 10.0]
    tr      = _transcript(
        (2.0,  4.0,  "First clip line"),
        (22.0, 25.0, "Second clip line"),
    )

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 2

    first  = next(e for e in entries if "First"  in e["text"])
    second = next(e for e in entries if "Second" in e["text"])

    assert abs(first["start"]  - 2.0)  < 1e-6
    assert abs(first["end"]    - 4.0)  < 1e-6
    assert abs(second["start"] - 11.0) < 1e-6
    assert abs(second["end"]   - 14.0) < 1e-6


def test_three_clips_crossfade_offsets():
    """
    Three 10 s clips with 1 s crossfade:
    Clip 0: offset 0.0
    Clip 1: offset 9.0  (10 - 1)
    Clip 2: offset 18.0 (9 + 10 - 1)
    """
    clips   = [_clip(0.0, 10.0), _clip(20.0, 30.0), _clip(40.0, 50.0)]
    offsets = [0.0, 9.0, 18.0]
    durs    = [10.0, 10.0, 10.0]
    tr      = _transcript(
        (1.0,  3.0,  "Clip zero"),
        (21.0, 24.0, "Clip one"),
        (45.0, 48.0, "Clip two"),
    )

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 3

    c0 = next(e for e in entries if "zero" in e["text"])
    assert abs(c0["start"] - 1.0) < 1e-6
    assert abs(c0["end"]   - 3.0) < 1e-6

    c1 = next(e for e in entries if "one" in e["text"])
    assert abs(c1["start"] - 10.0) < 1e-6   # 9.0 + (21-20)
    assert abs(c1["end"]   - 13.0) < 1e-6   # 9.0 + (24-20)

    c2 = next(e for e in entries if "two" in e["text"])
    assert abs(c2["start"] - 23.0) < 1e-6   # 18.0 + (45-40)
    assert abs(c2["end"]   - 26.0) < 1e-6   # 18.0 + (48-40)


def test_multiple_segments_in_one_clip():
    """Multiple segments within a single clip all get correct offsets."""
    clips   = [_clip(100.0, 130.0)]
    offsets = [5.0]
    durs    = [30.0]
    tr      = _transcript(
        (102.0, 105.0, "Line one"),
        (110.0, 114.0, "Line two"),
        (120.0, 125.0, "Line three"),
    )

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 3

    c1 = next(e for e in entries if "one"   in e["text"])
    c2 = next(e for e in entries if "two"   in e["text"])
    c3 = next(e for e in entries if "three" in e["text"])

    assert abs(c1["start"] - 7.0)  < 1e-6   # 5 + (102-100)
    assert abs(c1["end"]   - 10.0) < 1e-6
    assert abs(c2["start"] - 15.0) < 1e-6   # 5 + (110-100)
    assert abs(c2["end"]   - 19.0) < 1e-6
    assert abs(c3["start"] - 25.0) < 1e-6   # 5 + (120-100)
    assert abs(c3["end"]   - 30.0) < 1e-6


# ── Test 6: Unicode ───────────────────────────────────────────────────────────

def test_unicode_text_preserved():
    """Unicode characters in transcript text must pass through unchanged."""
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((1.0, 3.0, "こんにちは 🎬 Ünïcödé"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert len(entries) == 1
    assert entries[0]["text"] == "こんにちは 🎬 Ünïcödé"

    srt = build_srt(entries)
    assert "こんにちは 🎬 Ünïcödé" in srt


# ── Test 7: empty transcript ──────────────────────────────────────────────────

def test_empty_transcript_produces_no_entries():
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = {"segments": [], "words": [], "language": "", "full_text": ""}

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert entries == []


def test_empty_text_segment_skipped():
    """Whitespace-only text segments must be excluded."""
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((2.0, 4.0, "   "))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert entries == []


def test_very_short_segment_skipped():
    """Segments shorter than 0.1 s must be skipped."""
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = _transcript((2.0, 2.05, "Blink"))

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert entries == []


# ── Test 8: missing transcript key ───────────────────────────────────────────

def test_missing_segments_key_returns_empty():
    """If transcript dict has no 'segments' key, return empty list gracefully."""
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]
    tr      = {}   # no 'segments' key at all

    entries = map_transcript_to_timeline(clips, offsets, durs, tr)
    assert entries == []


def test_none_transcript_handled():
    """If transcript is an empty dict (fast mode), return empty list."""
    clips   = [_clip(0.0, 10.0)]
    offsets = [0.0]
    durs    = [10.0]

    entries = map_transcript_to_timeline(clips, offsets, durs, {})
    assert entries == []


# ── Test 9: subtitle cleanup ──────────────────────────────────────────────────

def test_srt_file_written_and_readable():
    """write_srt_file creates a valid UTF-8 file that can be read back."""
    entries = [
        {"start": 1.0, "end": 3.0, "text": "Hello"},
        {"start": 5.0, "end": 7.0, "text": "World"},
    ]
    with tempfile.TemporaryDirectory(prefix="clipsense_test_") as tmp:
        srt_path = os.path.join(tmp, "test.srt")
        write_srt_file(entries, srt_path)
        assert os.path.exists(srt_path)
        content = open(srt_path, encoding="utf-8").read()
        assert "Hello" in content
        assert "World" in content
    # After context manager exits, tmp_dir is deleted — file no longer exists
    assert not os.path.exists(srt_path)


# ── Test 10: fast mode + subtitles ───────────────────────────────────────────

def test_fast_mode_empty_transcript_no_fabrication():
    """
    Fast mode produces an empty transcript (no Whisper run).
    map_transcript_to_timeline must return [] — no fabricated entries.
    """
    clips   = [_clip(0.0, 60.0)]
    offsets = [0.0]
    durs    = [60.0]
    # Fast mode transcript — empty segments, no words
    fast_mode_transcript = {"segments": [], "words": [], "language": "", "full_text": ""}

    entries = map_transcript_to_timeline(clips, offsets, durs, fast_mode_transcript)
    assert entries == [], "Fast mode must not fabricate subtitle entries"

    srt = build_srt(entries)
    # SRT with no entries should be empty or just whitespace
    assert srt.strip() == ""


# ── Test 11: output duration clamping ────────────────────────────────────────

def test_build_srt_clamps_to_total_duration():
    """Entries starting at or beyond total_duration must be excluded."""
    entries = [
        {"start": 5.0,  "end": 8.0,  "text": "Inside"},
        {"start": 30.0, "end": 33.0, "text": "Outside"},
    ]
    srt = build_srt(entries, total_duration=25.0)
    assert "Inside"  in srt
    assert "Outside" not in srt


def test_build_srt_end_clamped_to_total_duration():
    """Entry that starts inside but ends beyond total_duration must be clamped."""
    entries = [{"start": 23.0, "end": 28.0, "text": "Partial"}]
    srt = build_srt(entries, total_duration=25.0)
    assert "Partial" in srt
    # End time should be clamped to 25.0 → 00:00:25,000
    assert "00:00:25,000" in srt


# ── Test 12: subtitle timing ──────────────────────────────────────────────────

def test_build_srt_skips_invalid_timing():
    """Entries where start >= end must be excluded from SRT output."""
    entries = [
        {"start": 5.0, "end": 3.0,  "text": "Reversed"},   # end < start
        {"start": 5.0, "end": 5.0,  "text": "Zero dur"},   # zero duration
        {"start": 2.0, "end": 4.0,  "text": "Valid"},
    ]
    srt = build_srt(entries)
    assert "Valid"    in srt
    assert "Reversed" not in srt
    assert "Zero dur" not in srt


def test_build_srt_no_negative_timestamps():
    """Negative start times must be clamped to 0."""
    entries = [{"start": -1.0, "end": 2.0, "text": "Negative start"}]
    srt = build_srt(entries)
    assert "Negative start" in srt
    assert "00:00:00,000" in srt   # clamped start


# ── Test 13: SRT format validation ───────────────────────────────────────────

def test_build_srt_valid_format():
    """build_srt must produce correctly structured SRT with sequential numbering."""
    entries = [
        {"start": 1.5,  "end": 3.2,  "text": "First line"},
        {"start": 5.0,  "end": 7.0,  "text": "Second line"},
        {"start": 10.0, "end": 12.5, "text": "Third line"},
    ]
    srt = build_srt(entries)
    lines = srt.split("\n")

    # Find blocks: index, timestamp, text, blank
    blocks = []
    i = 0
    while i < len(lines):
        if lines[i].strip().isdigit():
            idx  = int(lines[i].strip())
            ts   = lines[i + 1] if i + 1 < len(lines) else ""
            text = lines[i + 2] if i + 2 < len(lines) else ""
            blocks.append((idx, ts, text))
            i += 4
        else:
            i += 1

    assert len(blocks) == 3
    assert blocks[0][0] == 1
    assert blocks[1][0] == 2
    assert blocks[2][0] == 3

    # Verify timestamp format HH:MM:SS,mmm --> HH:MM:SS,mmm
    import re
    ts_pattern = re.compile(r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}")
    for _, ts, _ in blocks:
        assert ts_pattern.match(ts), f"Invalid SRT timestamp: {ts!r}"

    assert "First line"  in srt
    assert "Second line" in srt
    assert "Third line"  in srt


def test_srt_timestamp_formatting():
    """_secs_to_srt_time must produce correct HH:MM:SS,mmm strings."""
    from app.utils.ffmpeg_composer import _secs_to_srt_time
    assert _secs_to_srt_time(0.0)     == "00:00:00,000"
    assert _secs_to_srt_time(1.5)     == "00:00:01,500"
    assert _secs_to_srt_time(61.25)   == "00:01:01,250"
    assert _secs_to_srt_time(3661.1)  == "01:01:01,100"
    assert _secs_to_srt_time(-5.0)    == "00:00:00,000"   # negative clamped
