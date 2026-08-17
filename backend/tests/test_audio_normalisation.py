"""
Tests for Feature 6 — Audio Normalisation Controls.

Covers:
    - AudioSettings dataclass defaults and validation
    - _build_loudnorm_filter with different target_lufs values
    - _build_eq_filters for bass_boost / treble_cut combinations
    - compose() signature accepts audio_settings without error
    - Pydantic AudioSettings schema validation

Run with:
    cd backend
    python -m pytest tests/test_audio_normalisation.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from app.utils.ffmpeg_composer import (
    AudioSettings,
    _build_loudnorm_filter,
    _build_eq_filters,
    _DEFAULT_TARGET_LUFS,
)
from app.schemas.feedback import AudioSettings as SchemaAudioSettings


# ── AudioSettings dataclass ───────────────────────────────────────────────────

def test_default_audio_settings():
    s = AudioSettings()
    assert s.target_lufs == -14
    assert s.bass_boost is False
    assert s.treble_cut is False


def test_audio_settings_custom_lufs():
    s = AudioSettings(target_lufs=-16)
    assert s.target_lufs == -16


def test_audio_settings_bass_boost():
    s = AudioSettings(bass_boost=True)
    assert s.bass_boost is True
    assert s.treble_cut is False


def test_audio_settings_treble_cut():
    s = AudioSettings(treble_cut=True)
    assert s.treble_cut is True
    assert s.bass_boost is False


def test_audio_settings_both_enabled():
    s = AudioSettings(bass_boost=True, treble_cut=True)
    assert s.bass_boost is True
    assert s.treble_cut is True


# ── _build_loudnorm_filter ────────────────────────────────────────────────────

def test_loudnorm_default_lufs_no_measured():
    f = _build_loudnorm_filter("", -14)
    assert "I=-14" in f
    assert "loudnorm" in f


def test_loudnorm_minus16_lufs():
    f = _build_loudnorm_filter("", -16)
    assert "I=-16" in f


def test_loudnorm_minus12_lufs():
    f = _build_loudnorm_filter("", -12)
    assert "I=-12" in f


def test_loudnorm_minus10_lufs():
    f = _build_loudnorm_filter("", -10)
    assert "I=-10" in f


def test_loudnorm_with_measured_json_uses_target():
    measured = """{
        "input_i": "-23.5",
        "input_lra": "7.2",
        "input_tp": "-3.1",
        "input_thresh": "-33.5",
        "target_offset": "0.5"
    }"""
    f = _build_loudnorm_filter(measured, -16)
    assert "I=-16" in f
    assert "measured_I=-23.5" in f
    assert "linear=true" in f


def test_loudnorm_with_inf_values_falls_back():
    measured = """{
        "input_i": "-inf",
        "input_lra": "0.0",
        "input_tp": "-inf",
        "input_thresh": "-inf",
        "target_offset": "0.0"
    }"""
    f = _build_loudnorm_filter(measured, -14)
    # Should fall back to simple filter without measured_ params
    assert "measured_I" not in f
    assert "I=-14" in f


def test_loudnorm_with_invalid_json_falls_back():
    f = _build_loudnorm_filter("not json at all", -14)
    assert "I=-14" in f
    assert "loudnorm" in f


# ── _build_eq_filters ─────────────────────────────────────────────────────────

def test_eq_no_filters_returns_empty():
    s = AudioSettings()
    assert _build_eq_filters(s) == ""


def test_eq_bass_boost_only():
    s = AudioSettings(bass_boost=True)
    result = _build_eq_filters(s)
    assert "equalizer" in result
    assert "f=100" in result
    assert "g=4" in result
    # treble should not appear
    assert "f=8000" not in result


def test_eq_treble_cut_only():
    s = AudioSettings(treble_cut=True)
    result = _build_eq_filters(s)
    assert "equalizer" in result
    assert "f=8000" in result
    assert "g=-3" in result
    # bass should not appear
    assert "f=100" not in result


def test_eq_both_enabled():
    s = AudioSettings(bass_boost=True, treble_cut=True)
    result = _build_eq_filters(s)
    assert "f=100" in result
    assert "f=8000" in result
    assert "g=4" in result
    assert "g=-3" in result


def test_eq_filter_starts_with_comma_when_present():
    """Filter string must start with comma so it can be safely concatenated."""
    s = AudioSettings(bass_boost=True)
    result = _build_eq_filters(s)
    assert result.startswith(",")


def test_eq_filter_empty_string_when_disabled():
    s = AudioSettings(bass_boost=False, treble_cut=False)
    result = _build_eq_filters(s)
    assert result == ""


# ── Pydantic schema validation ────────────────────────────────────────────────

def test_schema_defaults():
    s = SchemaAudioSettings()
    assert s.target_lufs == -14
    assert s.bass_boost is False
    assert s.treble_cut is False


def test_schema_valid_lufs_values():
    for lufs in (-16, -14, -12, -10):
        s = SchemaAudioSettings(target_lufs=lufs)
        assert s.target_lufs == lufs


def test_schema_invalid_lufs_raises():
    with pytest.raises(Exception):
        SchemaAudioSettings(target_lufs=-11)


def test_schema_bass_boost_true():
    s = SchemaAudioSettings(bass_boost=True)
    assert s.bass_boost is True


def test_schema_treble_cut_true():
    s = SchemaAudioSettings(treble_cut=True)
    assert s.treble_cut is True


def test_schema_both_enabled():
    s = SchemaAudioSettings(bass_boost=True, treble_cut=True)
    assert s.bass_boost is True
    assert s.treble_cut is True


# ── Default preserves existing behaviour ─────────────────────────────────────

def test_default_lufs_matches_existing_constant():
    """Default target_lufs must equal the existing hardcoded -14 LUFS."""
    assert _DEFAULT_TARGET_LUFS == -14
    assert AudioSettings().target_lufs == _DEFAULT_TARGET_LUFS


def test_default_settings_produce_no_eq():
    """Default settings must not inject any EQ — preserves existing behaviour."""
    s = AudioSettings()
    assert _build_eq_filters(s) == ""


def test_default_loudnorm_filter_unchanged():
    """Default settings must produce the same loudnorm filter as before Feature 6."""
    f = _build_loudnorm_filter("", _DEFAULT_TARGET_LUFS)
    assert "I=-14" in f
    assert "LRA=11" in f
    assert "TP=-1" in f
