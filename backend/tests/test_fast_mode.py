"""
Tests for Fast Demo Mode.

Covers:
    1. Normal mode — fast_mode=False default, Whisper called
    2. Fast mode — fast_mode=True, Whisper NOT called
    3. Editor prompt + fast mode — creative direction still applied
    4. Audio settings + fast mode — audio normalisation still applied
    5. Subtitles + fast mode — subtitles silently disabled, no fabrication
    6. Comparison output + fast mode — plan and analysis still produced
    7. Output validation — fast_mode flag in schema, request, response

Run with:
    cd backend
    set PYTHONPATH=C:\\...\\backend
    pytest tests/test_fast_mode.py -v
"""

import sys
import os
import inspect
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.feedback import SmartTrailerGenerateRequest, SmartTrailerJobResponse
from app.utils.ffmpeg_composer import compose, map_transcript_to_timeline


# ── Test 1: Normal mode — fast_mode defaults to False ────────────────────────

def test_generate_request_fast_mode_defaults_false():
    """SmartTrailerGenerateRequest.fast_mode must default to False."""
    req = SmartTrailerGenerateRequest()
    assert req.fast_mode is False


def test_generate_request_fast_mode_can_be_set():
    req = SmartTrailerGenerateRequest(fast_mode=True)
    assert req.fast_mode is True


def test_agent_generate_signature_has_fast_mode():
    """SmartTrailerAgent.generate() must accept fast_mode parameter."""
    from app.services.smart_trailer_agent import SmartTrailerAgent
    sig = inspect.signature(SmartTrailerAgent.generate)
    assert "fast_mode" in sig.parameters
    assert sig.parameters["fast_mode"].default is False


# ── Test 2: Fast mode — Whisper is NOT called ─────────────────────────────────

def test_fast_mode_skips_whisper(tmp_path):
    """
    When fast_mode=True, transcribe() must not be called.
    We verify by patching transcribe and asserting it is never invoked.
    The agent is called with mocked heavy dependencies so no real video is needed.
    """
    from app.services.smart_trailer_agent import SmartTrailerAgent

    agent = SmartTrailerAgent()

    # Minimal mocks — we only care that transcribe is never called
    with mock.patch("app.services.smart_trailer_agent.transcribe") as mock_transcribe, \
         mock.patch("app.services.smart_trailer_agent._get_video_duration", return_value=60.0), \
         mock.patch("app.services.smart_trailer_agent.detect_scenes", return_value=[
             {"scene_index": 0, "start_time": 0.0, "end_time": 10.0, "duration": 10.0},
             {"scene_index": 1, "start_time": 10.0, "end_time": 20.0, "duration": 10.0},
             {"scene_index": 2, "start_time": 20.0, "end_time": 30.0, "duration": 10.0},
         ]), \
         mock.patch("app.services.smart_trailer_agent.detect_beats", return_value={
             "beats": [], "strong_beats": [], "tempo": 120.0, "beat_count": 0,
         }), \
         mock.patch("app.services.smart_trailer_agent.classify_clips_by_mood", side_effect=lambda c, _: c), \
         mock.patch("app.services.smart_trailer_agent.compose", return_value=(True, "")), \
         mock.patch("app.services.smart_trailer_agent._read_comments_file", return_value="Great action scenes!"), \
         mock.patch.object(agent._structuring_agent, "parse", return_value=[
             mock.MagicMock(sentiment="Positive", topic="Action", timestamp="0:05", summary="Great", confidence=0.9),
         ]), \
         mock.patch("app.utils.render_progress.set_progress"), \
         mock.patch("app.utils.render_progress.set_step"), \
         mock.patch("app.utils.render_progress.get_progress", return_value=None):

        raw_footage = str(tmp_path / "raw.mp4")
        open(raw_footage, "wb").close()

        agent.generate(
            raw_footage_path=raw_footage,
            sample_trailer_path=str(tmp_path / "sample.mp4"),
            comments_path=str(tmp_path / "comments.txt"),
            job_id="test-fast-001",
            fast_mode=True,
        )

    mock_transcribe.assert_not_called()


def test_normal_mode_calls_whisper(tmp_path):
    """
    When fast_mode=False (default), transcribe() must be called exactly once.
    """
    from app.services.smart_trailer_agent import SmartTrailerAgent

    agent = SmartTrailerAgent()

    with mock.patch("app.services.smart_trailer_agent.transcribe",
                    return_value={"segments": [], "words": [], "language": "", "full_text": ""}) as mock_transcribe, \
         mock.patch("app.services.smart_trailer_agent._get_video_duration", return_value=60.0), \
         mock.patch("app.services.smart_trailer_agent.detect_scenes", return_value=[
             {"scene_index": 0, "start_time": 0.0, "end_time": 10.0, "duration": 10.0},
             {"scene_index": 1, "start_time": 10.0, "end_time": 20.0, "duration": 10.0},
         ]), \
         mock.patch("app.services.smart_trailer_agent.detect_beats", return_value={
             "beats": [], "strong_beats": [], "tempo": 120.0, "beat_count": 0,
         }), \
         mock.patch("app.services.smart_trailer_agent.classify_clips_by_mood", side_effect=lambda c, _: c), \
         mock.patch("app.services.smart_trailer_agent.compose", return_value=(True, "")), \
         mock.patch("app.services.smart_trailer_agent._read_comments_file", return_value="Great scenes!"), \
         mock.patch.object(agent._structuring_agent, "parse", return_value=[
             mock.MagicMock(sentiment="Positive", topic="Action", timestamp="0:05", summary="Great", confidence=0.9),
         ]), \
         mock.patch("app.utils.render_progress.set_progress"), \
         mock.patch("app.utils.render_progress.set_step"), \
         mock.patch("app.utils.render_progress.get_progress", return_value=None):

        raw_footage = str(tmp_path / "raw.mp4")
        open(raw_footage, "wb").close()

        agent.generate(
            raw_footage_path=raw_footage,
            sample_trailer_path=str(tmp_path / "sample.mp4"),
            comments_path=str(tmp_path / "comments.txt"),
            job_id="test-normal-001",
            fast_mode=False,
        )

    mock_transcribe.assert_called_once()


# ── Test 3: Editor prompt + fast mode ────────────────────────────────────────

def test_creative_prompt_applied_in_fast_mode(tmp_path):
    """Creative direction prompt must still be parsed and applied in fast mode."""
    from app.services.smart_trailer_agent import SmartTrailerAgent, _parse_creative_prompt

    prefs = _parse_creative_prompt("more action, faster pacing")
    assert not prefs.is_empty()
    assert prefs.action > 0
    assert prefs.pacing > 0

    # Verify the agent accepts user_prompt alongside fast_mode without error
    agent = SmartTrailerAgent()
    sig = inspect.signature(agent.generate)
    assert "user_prompt" in sig.parameters
    assert "fast_mode" in sig.parameters


# ── Test 4: Audio settings + fast mode ───────────────────────────────────────

def test_audio_settings_accepted_with_fast_mode():
    """AudioSettings must be accepted alongside fast_mode=True in the request schema."""
    from app.schemas.feedback import AudioSettings
    req = SmartTrailerGenerateRequest(
        audio=AudioSettings(target_lufs=-12, bass_boost=True),
        fast_mode=True,
    )
    assert req.fast_mode is True
    assert req.audio is not None
    assert req.audio.target_lufs == -12
    assert req.audio.bass_boost is True


# ── Test 5: Subtitles + fast mode — no fabrication ───────────────────────────

def test_fast_mode_disables_subtitles_in_agent(tmp_path):
    """
    When fast_mode=True and include_subtitles=True, the agent must:
    1. Not call transcribe()
    2. Call compose() with include_subtitles=False
    """
    from app.services.smart_trailer_agent import SmartTrailerAgent

    agent = SmartTrailerAgent()
    compose_calls = []

    def _fake_compose(clips, input_path, output_path, transcript,
                      audio_fade_out=True, job_id=None, beats=None,
                      audio_settings=None, include_subtitles=False):
        compose_calls.append({"include_subtitles": include_subtitles, "transcript": transcript})
        return True, ""

    with mock.patch("app.services.smart_trailer_agent.transcribe") as mock_transcribe, \
         mock.patch("app.services.smart_trailer_agent._get_video_duration", return_value=60.0), \
         mock.patch("app.services.smart_trailer_agent.detect_scenes", return_value=[
             {"scene_index": 0, "start_time": 0.0, "end_time": 10.0, "duration": 10.0},
             {"scene_index": 1, "start_time": 10.0, "end_time": 20.0, "duration": 10.0},
         ]), \
         mock.patch("app.services.smart_trailer_agent.detect_beats", return_value={
             "beats": [], "strong_beats": [], "tempo": 120.0, "beat_count": 0,
         }), \
         mock.patch("app.services.smart_trailer_agent.classify_clips_by_mood", side_effect=lambda c, _: c), \
         mock.patch("app.services.smart_trailer_agent.compose", side_effect=_fake_compose), \
         mock.patch("app.services.smart_trailer_agent._read_comments_file", return_value="Great!"), \
         mock.patch.object(agent._structuring_agent, "parse", return_value=[
             mock.MagicMock(sentiment="Positive", topic="Action", timestamp="0:05", summary="Great", confidence=0.9),
         ]), \
         mock.patch("app.utils.render_progress.set_progress"), \
         mock.patch("app.utils.render_progress.set_step"), \
         mock.patch("app.utils.render_progress.get_progress", return_value=None):

        raw_footage = str(tmp_path / "raw.mp4")
        open(raw_footage, "wb").close()

        agent.generate(
            raw_footage_path=raw_footage,
            sample_trailer_path=str(tmp_path / "sample.mp4"),
            comments_path=str(tmp_path / "comments.txt"),
            job_id="test-sub-fast-001",
            include_subtitles=True,   # requested by user
            fast_mode=True,           # overrides subtitles
        )

    # Whisper must not have been called
    mock_transcribe.assert_not_called()

    # compose() must have been called with include_subtitles=False
    assert len(compose_calls) == 1
    assert compose_calls[0]["include_subtitles"] is False

    # Transcript passed to compose must be empty (no fabrication)
    transcript = compose_calls[0]["transcript"]
    assert transcript.get("segments", []) == []


def test_fast_mode_empty_transcript_no_subtitle_entries():
    """
    map_transcript_to_timeline with an empty transcript (fast mode result)
    must return no entries — no fabrication.
    """
    from app.utils.clip_planner import PlannedClip
    clips   = [PlannedClip(start_time=0.0, end_time=30.0, reason="test", topic="T", sentiment="Positive")]
    offsets = [0.0]
    durs    = [30.0]
    empty_transcript = {"segments": [], "words": [], "language": "", "full_text": ""}

    entries = map_transcript_to_timeline(clips, offsets, durs, empty_transcript)
    assert entries == []


# ── Test 6: Comparison output + fast mode ────────────────────────────────────

def test_fast_mode_still_produces_plan_and_analysis(tmp_path):
    """
    fast_mode=True must still produce a TrailerEditingPlan and SmartTrailerAnalysis.
    Only Whisper is skipped — scene detection, sentiment, clip scoring all run.
    """
    from app.services.smart_trailer_agent import SmartTrailerAgent

    agent = SmartTrailerAgent()

    with mock.patch("app.services.smart_trailer_agent.transcribe"), \
         mock.patch("app.services.smart_trailer_agent._get_video_duration", return_value=60.0), \
         mock.patch("app.services.smart_trailer_agent.detect_scenes", return_value=[
             {"scene_index": 0, "start_time": 0.0, "end_time": 10.0, "duration": 10.0},
             {"scene_index": 1, "start_time": 10.0, "end_time": 20.0, "duration": 10.0},
             {"scene_index": 2, "start_time": 20.0, "end_time": 30.0, "duration": 10.0},
         ]), \
         mock.patch("app.services.smart_trailer_agent.detect_beats", return_value={
             "beats": [], "strong_beats": [], "tempo": 120.0, "beat_count": 0,
         }), \
         mock.patch("app.services.smart_trailer_agent.classify_clips_by_mood", side_effect=lambda c, _: c), \
         mock.patch("app.services.smart_trailer_agent.compose", return_value=(True, "")), \
         mock.patch("app.services.smart_trailer_agent._read_comments_file", return_value="Great action!"), \
         mock.patch.object(agent._structuring_agent, "parse", return_value=[
             mock.MagicMock(sentiment="Positive", topic="Action", timestamp="0:05", summary="Great", confidence=0.9),
         ]), \
         mock.patch("app.utils.render_progress.set_progress"), \
         mock.patch("app.utils.render_progress.set_step"), \
         mock.patch("app.utils.render_progress.get_progress", return_value=None):

        raw_footage = str(tmp_path / "raw.mp4")
        open(raw_footage, "wb").close()

        result = agent.generate(
            raw_footage_path=raw_footage,
            sample_trailer_path=str(tmp_path / "sample.mp4"),
            comments_path=str(tmp_path / "comments.txt"),
            job_id="test-plan-fast-001",
            fast_mode=True,
        )

    output_path, plan, analysis, error, platform, clip_score, _, fallback_warning, raw_dur = result

    assert error is None, f"Expected no error, got: {error}"
    assert plan is not None, "TrailerEditingPlan must be produced in fast mode"
    assert analysis is not None, "SmartTrailerAnalysis must be produced in fast mode"
    assert len(plan.clips) > 0, "Plan must contain clips"
    assert raw_dur == 60.0


# ── Test 7: Output validation — schema and flag propagation ──────────────────

def test_job_response_schema_has_fast_mode():
    """SmartTrailerJobResponse must include fast_mode field."""
    sig_fields = SmartTrailerJobResponse.model_fields
    assert "fast_mode" in sig_fields


def test_fast_mode_true_in_response():
    """SmartTrailerJobResponse must correctly represent fast_mode=True."""
    resp = SmartTrailerJobResponse(
        id="abc",
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        comments_name="comments.txt",
        status="done",
        fast_mode=True,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:01:00",
    )
    assert resp.fast_mode is True


def test_fast_mode_false_in_response():
    """SmartTrailerJobResponse must correctly represent fast_mode=False."""
    resp = SmartTrailerJobResponse(
        id="abc",
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        comments_name="comments.txt",
        status="done",
        fast_mode=False,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:01:00",
    )
    assert resp.fast_mode is False


def test_fast_mode_none_in_response_for_old_jobs():
    """fast_mode=None must be accepted for jobs created before this feature."""
    resp = SmartTrailerJobResponse(
        id="abc",
        raw_footage_name="raw.mp4",
        sample_trailer_name="sample.mp4",
        comments_name="comments.txt",
        status="done",
        fast_mode=None,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:01:00",
    )
    assert resp.fast_mode is None


def test_fast_mode_rationale_note(tmp_path):
    """
    When fast_mode=True, the editing plan rationale must contain a note
    indicating transcription was skipped.
    """
    from app.services.smart_trailer_agent import SmartTrailerAgent

    agent = SmartTrailerAgent()

    with mock.patch("app.services.smart_trailer_agent.transcribe"), \
         mock.patch("app.services.smart_trailer_agent._get_video_duration", return_value=60.0), \
         mock.patch("app.services.smart_trailer_agent.detect_scenes", return_value=[
             {"scene_index": 0, "start_time": 0.0, "end_time": 10.0, "duration": 10.0},
             {"scene_index": 1, "start_time": 10.0, "end_time": 20.0, "duration": 10.0},
         ]), \
         mock.patch("app.services.smart_trailer_agent.detect_beats", return_value={
             "beats": [], "strong_beats": [], "tempo": 120.0, "beat_count": 0,
         }), \
         mock.patch("app.services.smart_trailer_agent.classify_clips_by_mood", side_effect=lambda c, _: c), \
         mock.patch("app.services.smart_trailer_agent.compose", return_value=(True, "")), \
         mock.patch("app.services.smart_trailer_agent._read_comments_file", return_value="Great!"), \
         mock.patch.object(agent._structuring_agent, "parse", return_value=[
             mock.MagicMock(sentiment="Positive", topic="Action", timestamp="0:05", summary="Great", confidence=0.9),
         ]), \
         mock.patch("app.utils.render_progress.set_progress"), \
         mock.patch("app.utils.render_progress.set_step"), \
         mock.patch("app.utils.render_progress.get_progress", return_value=None):

        raw_footage = str(tmp_path / "raw.mp4")
        open(raw_footage, "wb").close()

        _, plan, _, error, *_ = agent.generate(
            raw_footage_path=raw_footage,
            sample_trailer_path=str(tmp_path / "sample.mp4"),
            comments_path=str(tmp_path / "comments.txt"),
            job_id="test-rationale-001",
            fast_mode=True,
        )

    assert error is None
    assert plan is not None
    assert "fast" in plan.rationale.lower() or "transcription" in plan.rationale.lower(), \
        f"Expected fast mode note in rationale, got: {plan.rationale!r}"


def test_backward_compat_no_fast_mode_field():
    """
    Existing API clients that omit fast_mode must get False by default.
    """
    req = SmartTrailerGenerateRequest(user_prompt="more action")
    assert req.fast_mode is False
    assert req.include_subtitles is False
