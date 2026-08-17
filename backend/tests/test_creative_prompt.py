"""
Tests for _parse_creative_prompt() and the CreativePreferences scoring contract.

Run with:
    cd backend
    python -m pytest tests/test_creative_prompt.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.smart_trailer_agent import (
    _parse_creative_prompt,
    CreativePreferences,
    CREATIVE_BIAS_WEIGHT,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prefs(prompt: str) -> CreativePreferences:
    return _parse_creative_prompt(prompt)


# ── None / empty ──────────────────────────────────────────────────────────────

def test_none_prompt_returns_empty():
    p = _parse_creative_prompt(None)
    assert p.is_empty()


def test_empty_string_returns_empty():
    p = _parse_creative_prompt("   ")
    assert p.is_empty()


# ── Action ────────────────────────────────────────────────────────────────────

def test_more_action_positive():
    p = _prefs("more action")
    assert p.action > 0.0


def test_keep_action_positive():
    p = _prefs("keep the action")
    assert p.action > 0.0


def test_less_action_negative():
    p = _prefs("less action")
    assert p.action < 0.0


def test_remove_action_negative():
    p = _prefs("remove action scenes")
    assert p.action < 0.0


# ── Emotion ───────────────────────────────────────────────────────────────────

def test_more_emotional_positive():
    p = _prefs("more emotional")
    assert p.emotion > 0.0


def test_remove_emotional_negative():
    p = _prefs("remove emotional scenes")
    assert p.emotion < 0.0


def test_less_drama_negative():
    p = _prefs("less drama")
    assert p.emotion < 0.0


# ── Humour ────────────────────────────────────────────────────────────────────

def test_more_humour_positive():
    p = _prefs("more humour")
    assert p.humour > 0.0


def test_make_it_funnier_positive():
    p = _prefs("make it funnier")
    assert p.humour > 0.0


def test_funny_positive():
    p = _prefs("add funny moments")
    assert p.humour > 0.0


def test_serious_reduces_humour():
    p = _prefs("keep it serious")
    assert p.humour < 0.0


# ── Suspense ──────────────────────────────────────────────────────────────────

def test_more_suspense_positive():
    p = _prefs("more suspense")
    assert p.suspense > 0.0


def test_tension_positive():
    p = _prefs("add tension")
    assert p.suspense > 0.0


# ── Pacing ────────────────────────────────────────────────────────────────────

def test_faster_pacing_positive():
    p = _prefs("faster pacing")
    assert p.pacing > 0.0


def test_slow_down_negative():
    p = _prefs("slow down")
    assert p.pacing < 0.0


# ── Character ─────────────────────────────────────────────────────────────────

def test_more_character_moments_positive():
    p = _prefs("more character moments")
    assert p.character > 0.0


# ── Combined prompt ───────────────────────────────────────────────────────────

def test_combined_prompt():
    p = _prefs("Keep the action, remove emotional scenes, and make the trailer more humorous.")
    assert p.action > 0.0,  "action should be positive"
    assert p.emotion < 0.0, "emotion should be negative"
    assert p.humour > 0.0,  "humour should be positive"


def test_combined_not_empty():
    p = _prefs("more action, less emotion")
    assert not p.is_empty()


# ── Bounds ────────────────────────────────────────────────────────────────────

def test_values_bounded_to_one():
    # Repeat the same keyword many times — should never exceed ±1.0
    p = _prefs("action action action action action action action action")
    assert -1.0 <= p.action <= 1.0


def test_creative_bias_weight_constant():
    # Contract: CREATIVE_BIAS_WEIGHT must stay <= 0.5 so sentiment (2.0) dominates
    assert CREATIVE_BIAS_WEIGHT <= 0.5


# ── Summary labels ────────────────────────────────────────────────────────────

def test_summary_labels_non_empty_when_prefs_set():
    p = _prefs("more action")
    assert len(p.summary_labels()) > 0


def test_summary_labels_empty_when_no_prefs():
    p = _parse_creative_prompt(None)
    assert p.summary_labels() == []


# ── Backward compatibility ────────────────────────────────────────────────────

def test_no_prompt_is_backward_compatible():
    """Calling with None must return an empty prefs that has no effect on scoring."""
    p = _parse_creative_prompt(None)
    assert p.is_empty()
    assert p.action == 0.0
    assert p.emotion == 0.0
    assert p.humour == 0.0
    assert p.suspense == 0.0
    assert p.pacing == 0.0
    assert p.character == 0.0
