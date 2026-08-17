"""
Smart Trailer Agent — Stage 4

Pipeline:
    Stage 1 — Comments Structuring
        Parse raw audience comments into FeedbackSegment list via FeedbackStructuringAgent.

    Stage 2 — Sample Trailer Pattern Analysis (deterministic)
        Correlates audience sentiment with sample trailer shot boundaries to extract
        positive/negative editing patterns. Pure Python — no external API calls.

    Stage 3 — Raw Footage Clip Planning (deterministic)
        Selects clips from raw footage using scene boundaries, beat alignment,
        and sentiment-informed scoring. Enforces 6s minimum per clip.

    Stage 4 — Clip Processing + FFmpeg Composition
        Converts plan dicts directly to PlannedClip, classifies mood, composes
        with moviepy CrossFadeIn transitions, loudnorm, and video/audio fade-out.

No external API calls. No Gemini. Fully deterministic and offline.
"""

import os
import csv
import json
import uuid
import logging
import subprocess
import re
from collections import Counter

from app.schemas.feedback import (
    FeedbackSegment,
    SmartTrailerAnalysis,
    TrailerEditingPlan,
    TrailerClip,
)
from app.services.feedback_structuring_agent import FeedbackStructuringAgent
from app.utils.storage import TRAILERS_DIR
from app.utils.scene_detector import detect_scenes
from app.utils.transcript import transcribe
from app.utils.beat_detector import detect_beats
from app.utils.clip_planner import classify_clips_by_mood
from app.utils.ffmpeg_composer import compose, AudioSettings as ComposerAudioSettings

logger = logging.getLogger(__name__)

MIN_NO_SPEECH = 3.0  # seconds — minimum duration for non-dialogue clips

_POSITIVE_SENTIMENTS = {"Positive", "Praise"}
_NEGATIVE_SENTIMENTS = {"Negative", "Complaint"}


# ── Creative direction preferences ───────────────────────────────────────────
# Lightweight deterministic parser — no LLM required.
#
# Weighting contract:
#   - Each dimension is in [-1.0, +1.0]
#   - +1.0 = strong preference FOR that quality
#   - -1.0 = strong preference AGAINST that quality
#   - 0.0  = no preference expressed
#
# Scoring contract (applied in scene_score):
#   creative_bias = sum(pref * CREATIVE_BIAS_WEIGHT for matching dims)
#   CREATIVE_BIAS_WEIGHT = 0.4  (max ±0.4 per dimension)
#   This keeps creative bias bounded well below the base sentiment score (2.0)
#   so strong audience sentiment always dominates unless the editor explicitly
#   overrides a dimension.

CREATIVE_BIAS_WEIGHT = 0.4  # max contribution per matched dimension

class CreativePreferences:
    """Normalised creative direction parsed from a free-form editor prompt."""
    __slots__ = ("action", "emotion", "humour", "suspense", "pacing", "character", "raw_labels")

    def __init__(self):
        self.action:    float = 0.0
        self.emotion:   float = 0.0
        self.humour:    float = 0.0
        self.suspense:  float = 0.0
        self.pacing:    float = 0.0   # +1 = faster, -1 = slower
        self.character: float = 0.0
        self.raw_labels: list[str] = []  # human-readable summary tokens

    def is_empty(self) -> bool:
        return all(
            getattr(self, d) == 0.0
            for d in ("action", "emotion", "humour", "suspense", "pacing", "character")
        )

    def summary_labels(self) -> list[str]:
        """Return display-ready labels derived from parsed preferences."""
        return list(self.raw_labels)


# Synonym map: (dimension, direction, synonyms...)
# direction: +1 = more, -1 = less
_SYNONYM_RULES: list[tuple[str, float, tuple[str, ...]]] = [
    # action
    ("action",    +1.0, ("action", "fight", "chase", "intense", "explosive", "dynamic", "energetic")),
    ("action",    -1.0, ("less action", "no action", "remove action", "reduce action")),
    # emotion
    ("emotion",   +1.0, ("emotional", "emotion", "heartfelt", "touching", "moving", "sentimental", "dramatic")),
    ("emotion",   -1.0, ("less emotional", "remove emotional", "reduce emotional", "no emotion", "less drama")),
    # humour
    ("humour",    +1.0, ("humour", "humor", "funny", "comic", "comedy", "laugh", "lighthearted", "fun", "witty", "humorous")),
    ("humour",    -1.0, ("less funny", "no comedy", "remove humour", "less humour", "serious")),
    # suspense
    ("suspense",  +1.0, ("suspense", "suspenseful", "tension", "thriller", "mystery", "mysterious", "tense", "gripping")),
    ("suspense",  -1.0, ("less suspense", "no tension", "remove suspense", "less tension")),
    # pacing
    ("pacing",    +1.0, ("fast", "faster", "quick", "rapid", "snappy", "fast-paced", "fast paced", "speed up")),
    ("pacing",    -1.0, ("slow", "slower", "slower paced", "slow down", "relaxed", "calm", "gentle")),
    # character
    ("character", +1.0, ("character", "characters", "character moment", "character moments", "personal", "intimate", "people")),
    ("character", -1.0, ("less character", "no character moments", "remove character")),
]

# Negation prefixes that flip direction
_NEGATION_PREFIXES = ("no ", "not ", "remove ", "without ", "less ", "reduce ", "avoid ", "cut ")
_POSITIVE_PREFIXES = ("more ", "add ", "keep ", "include ", "increase ", "make it ", "make more ")


def _parse_creative_prompt(prompt: str | None) -> CreativePreferences:
    """
    Parse a free-form creative direction string into a CreativePreferences object.

    Strategy:
    1. Normalise to lowercase.
    2. Check multi-word negation phrases first (e.g. "less emotional").
    3. Check positive prefix phrases (e.g. "more action").
    4. Fall back to bare keyword matching with context-window negation check.
    """
    prefs = CreativePreferences()
    if not prompt or not prompt.strip():
        return prefs

    text = prompt.lower().strip()
    # Clamp helper — accumulate but never exceed ±1.0
    def _apply(dim: str, delta: float, label: str) -> None:
        current = getattr(prefs, dim)
        setattr(prefs, dim, max(-1.0, min(1.0, current + delta)))
        if label not in prefs.raw_labels:
            prefs.raw_labels.append(label)

    for dim, direction, synonyms in _SYNONYM_RULES:
        for syn in synonyms:
            if syn not in text:
                continue
            # Multi-word synonyms already encode direction — apply directly
            if " " in syn:
                _apply(dim, direction * 0.8, ("More " if direction > 0 else "Less ") + dim)
                continue
            # Single-word: check surrounding context for negation / positive prefix
            idx = text.find(syn)
            window = text[max(0, idx - 20): idx]  # 20-char look-behind
            negated  = any(window.endswith(p.rstrip()) or (p.rstrip() + " ") in window for p in _NEGATION_PREFIXES)
            boosted  = any(window.endswith(p.rstrip()) or (p.rstrip() + " ") in window for p in _POSITIVE_PREFIXES)
            effective = direction * (-1.0 if negated else 1.0)
            strength  = 0.9 if boosted or negated else 0.6
            label_dir = "More" if effective > 0 else "Less"
            _apply(dim, effective * strength, f"{label_dir} {dim}")

    return prefs


# ── FFmpeg duration probe ─────────────────────────────────────────────────────

def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"

FFMPEG = _get_ffmpeg()


def _get_video_duration(video_path: str) -> float:
    try:
        result = subprocess.run(
            [FFMPEG, "-i", video_path],
            capture_output=True, text=True, timeout=15,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", result.stderr)
        if match:
            h, m, s = match.groups()
            return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 0.0


# ── Comments file parser ──────────────────────────────────────────────────────

def _read_comments_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                lines = []
                for item in data:
                    if isinstance(item, str):
                        lines.append(item)
                    elif isinstance(item, dict):
                        for key in ("text", "comment", "body", "content", "message"):
                            if key in item:
                                lines.append(str(item[key]))
                                break
                return "\n".join(lines)
            return str(data)
        elif ext == ".csv":
            lines = []
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    for key in ("text", "comment", "body", "content", "message"):
                        if key in row:
                            lines.append(row[key])
                            break
                    else:
                        lines.append(" ".join(row.values()))
            return "\n".join(lines)
        else:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
    except Exception as exc:
        logger.warning("SmartTrailerAgent: failed to read comments file: %s", exc)
        return ""


# ── Stage 2: Deterministic sample trailer analysis ───────────────────────────

def _ts_to_seconds(ts: str) -> float | None:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def _analyse_sample_trailer(
    segments: list[FeedbackSegment],
    sample_duration: float,
    shot_boundaries: list[dict],
) -> dict:
    """
    Correlate audience sentiment with sample trailer shot boundaries to extract
    positive and negative editing patterns. Pure Python — no external calls.
    """
    pos = [s for s in segments if s.sentiment in _POSITIVE_SENTIMENTS]
    neg = [s for s in segments if s.sentiment in _NEGATIVE_SENTIMENTS]

    # Map each timestamped segment to its nearest shot boundary
    def nearest_shot(ts_secs: float) -> dict | None:
        if not shot_boundaries:
            return None
        return min(shot_boundaries, key=lambda sc: abs(sc["start_time"] - ts_secs))

    # Identify which shot indices drove positive vs negative reactions
    pos_shot_indices: list[int] = []
    neg_shot_indices: list[int] = []
    for seg in segments:
        if not seg.timestamp:
            continue
        secs = _ts_to_seconds(seg.timestamp)
        if secs is None:
            continue
        shot = nearest_shot(secs)
        if shot is None:
            continue
        if seg.sentiment in _POSITIVE_SENTIMENTS:
            pos_shot_indices.append(shot["scene_index"])
        elif seg.sentiment in _NEGATIVE_SENTIMENTS:
            neg_shot_indices.append(shot["scene_index"])

    # Derive positive patterns from most-praised topics and shot durations
    pos_topic_counts = Counter(s.topic for s in pos)
    neg_topic_counts = Counter(s.topic for s in neg)
    top_pos_topics   = [t for t, _ in pos_topic_counts.most_common(4)]
    top_neg_topics   = [t for t, _ in neg_topic_counts.most_common(3)]

    # Characterise shot durations at positive moments
    pos_durations = []
    for idx in set(pos_shot_indices):
        shots = [sc for sc in shot_boundaries if sc["scene_index"] == idx]
        if shots:
            pos_durations.append(shots[0]["duration"])

    avg_pos_dur = round(sum(pos_durations) / len(pos_durations), 1) if pos_durations else 0.0
    pacing_desc = "fast-paced cuts" if avg_pos_dur < 4.0 else "sustained longer shots"

    positive_patterns = [f"Positive audience response to {t} segments" for t in top_pos_topics]
    if avg_pos_dur > 0:
        positive_patterns.append(f"Editing rhythm of ~{avg_pos_dur}s per shot ({pacing_desc}) drove engagement")
    if not positive_patterns:
        positive_patterns = ["Strong opening moments", "High-energy scene transitions"]

    negative_patterns = [f"Negative audience response to {t} segments" for t in top_neg_topics]
    if not negative_patterns:
        negative_patterns = ["Slow pacing sections", "Abrupt scene changes"]

    return {
        "sentiment_summary": (
            f"Audience showed {len(pos)} positive and {len(neg)} negative reactions "
            f"across {len(segments)} total comments on the sample trailer."
        ),
        "positive_patterns":    positive_patterns,
        "negative_patterns":    negative_patterns,
        "top_scene_categories": top_pos_topics or ["Action", "Dialogue"],
        "influence_explanation": (
            f"New trailer will prioritise {', '.join(top_pos_topics[:2] or ['high-engagement'])} scenes "
            f"and avoid {', '.join(top_neg_topics[:2] or ['low-engagement'])} segments."
        ),
    }


# ── Stage 3: Deterministic raw footage clip planner ──────────────────────────

def _plan_clips_from_raw(
    analysis: dict,
    raw_duration: float,
    target_duration: float,
    raw_shots: list[dict],
    raw_beats: dict,
    transcript: dict,
    prefs: CreativePreferences | None = None,
) -> dict:
    """
    Select clips from raw footage using:
    - Scene boundaries from PySceneDetect (prefer whole scenes)
    - Beat alignment from librosa (snap start/end to nearest strong beat)
    - Sentiment-informed topic scoring (prefer scenes matching positive patterns)
    - Creative direction bias (bounded at CREATIVE_BIAS_WEIGHT per dimension)
    - 6s minimum clip duration enforced at selection stage

    Scoring layers (additive):
        base_score        — dialogue presence, beat alignment, duration fit
        sentiment_score   — negative pattern penalty
        creative_bias     — editor preference per mood dimension (max ±1.2 total)
    """
    from app.utils.beat_detector import find_nearest_beat
    strong_beats = raw_beats.get("strong_beats", [])
    all_beats    = raw_beats.get("beats", [])
    pos_topics   = set(analysis.get("top_scene_categories", []))
    neg_patterns = analysis.get("negative_patterns", [])
    _prefs       = prefs or CreativePreferences()

    # Map mood_group → preference dimension
    _MOOD_TO_DIM: dict[str, str] = {
        "action":    "action",
        "emotional": "emotion",
        "dialogue":  "character",
        "calm":      "emotion",   # calm scenes carry emotional weight
    }

    def _creative_bias(scene: dict, mood: str) -> tuple[float, str]:
        """
        Return (bias_score, explanation_fragment).
        bias_score is bounded to [-1.2, +1.2] across all dimensions.
        explanation_fragment is empty string when bias had no effect.
        """
        if _prefs.is_empty():
            return 0.0, ""

        bias  = 0.0
        parts: list[str] = []

        # Mood-dimension match
        dim = _MOOD_TO_DIM.get(mood)
        if dim:
            pref_val = getattr(_prefs, dim)
            if pref_val != 0.0:
                contribution = pref_val * CREATIVE_BIAS_WEIGHT
                bias += contribution
                direction = "requested" if pref_val > 0 else "de-prioritised"
                parts.append(f"editor {direction} {dim}")

        # Pacing preference: faster pacing boosts short scenes, penalises long ones
        if _prefs.pacing != 0.0:
            dur = scene["duration"]
            if _prefs.pacing > 0 and dur < 8.0:
                contribution = _prefs.pacing * CREATIVE_BIAS_WEIGHT * 0.5
                bias += contribution
                parts.append("editor requested faster pacing")
            elif _prefs.pacing < 0 and dur > 12.0:
                contribution = abs(_prefs.pacing) * CREATIVE_BIAS_WEIGHT * 0.5
                bias += contribution
                parts.append("editor requested slower pacing")

        # Suspense: boosts any scene near a strong beat (tension = rhythm)
        if _prefs.suspense > 0 and any(abs(scene["start_time"] - b) <= 1.0 for b in strong_beats):
            contribution = _prefs.suspense * CREATIVE_BIAS_WEIGHT * 0.5
            bias += contribution
            parts.append("editor requested more suspense")

        # Humour: no structural signal available — log but don't fabricate a score
        # (humour is a tonal quality that cannot be detected from scene boundaries alone)

        bias = max(-1.2, min(1.2, bias))
        return bias, " + ".join(parts)

    def scene_score(scene: dict, mood: str = "calm") -> tuple[float, str]:
        """
        Returns (total_score, reason_string).
        Reason string explains which factors contributed.
        """
        score = 0.0
        reason_parts: list[str] = []

        from app.utils.clip_planner import get_transcript_text
        clip_text  = get_transcript_text(scene["start_time"], scene["end_time"], transcript)
        has_speech = bool(clip_text.strip())

        # Base: dialogue presence
        if has_speech:
            score += 2.0
            reason_parts.append("dialogue scene")

        # Base: beat alignment
        if any(abs(scene["start_time"] - b) <= 0.5 for b in strong_beats):
            score += 0.5
            reason_parts.append("beat-aligned")

        # Base: duration fit
        if 6.0 <= scene["duration"] <= 20.0:
            score += 0.5
            reason_parts.append("good duration")

        # Sentiment: negative pattern penalty
        for pat in neg_patterns:
            if "slow" in pat.lower() and scene["duration"] > 20.0:
                score -= 0.5
                reason_parts.append("penalised: slow pacing pattern")

        # Creative bias layer
        bias, bias_explanation = _creative_bias(scene, mood)
        if bias != 0.0:
            score += bias
            if bias_explanation:
                reason_parts.append(bias_explanation)

        reason = "; ".join(reason_parts) if reason_parts else "scene boundary selection"
        return score, reason

    # Pre-classify mood for each scene so score() is consistent
    def _infer_mood(scene: dict) -> str:
        from app.utils.clip_planner import get_transcript_text
        clip_text = get_transcript_text(scene["start_time"], scene["end_time"], transcript)
        if clip_text.strip():
            return "dialogue"
        dur = scene["duration"]
        if dur < 6.0:
            return "action"
        if dur > 20.0:
            return "calm"
        return "action"

    scene_moods = {id(sc): _infer_mood(sc) for sc in raw_shots}

    # Sort scenes by score descending, filter to >= 6s
    scored = sorted(
        [sc for sc in raw_shots if sc["duration"] >= 6.0],
        key=lambda sc: scene_score(sc, scene_moods.get(id(sc), "calm"))[0],
        reverse=True,
    )

    MAX_CLIPS = 7
    clips = []
    total = 0.0
    pos_topics_list = sorted(pos_topics)  # deterministic order

    for scene in scored:
        if total >= target_duration or len(clips) >= MAX_CLIPS:
            break

        mood      = scene_moods.get(id(scene), "calm")
        sc_score, sc_reason = scene_score(scene, mood)

        from app.utils.clip_planner import get_transcript_text, get_dialogue_window
        clip_text  = get_transcript_text(scene["start_time"], scene["end_time"], transcript)
        has_speech = bool(clip_text.strip())

        if has_speech:
            d_start, d_end = get_dialogue_window(
                scene["start_time"], scene["end_time"], transcript
            )
            snapped_start = min(scene["start_time"], d_start) if d_start is not None else scene["start_time"]
            snapped_end   = max(scene["end_time"],   d_end)   if d_end   is not None else scene["end_time"]
        else:
            snapped_start = find_nearest_beat(scene["start_time"], all_beats, tolerance=0.4)
            snapped_end   = scene["end_time"]
            if snapped_end - snapped_start < MIN_NO_SPEECH:
                snapped_start = scene["start_time"]

        snapped_start = max(0.0, snapped_start)
        snapped_end   = min(raw_duration, snapped_end)

        remaining = target_duration - total
        clip_dur  = snapped_end - snapped_start
        min_dur   = MIN_NO_SPEECH if not has_speech else clip_dur
        if clip_dur > remaining and remaining >= min_dur:
            snapped_end = snapped_start + remaining

        top_topic = (pos_topics_list[0] if pos_topics_list else "General") if has_speech else "General"
        sentiment = "Positive" if sc_score >= 1.0 else ("Neutral" if sc_score >= 0.5 else "Negative")

        clips.append({
            "start_time": round(snapped_start, 3),
            "end_time":   round(snapped_end, 3),
            "reason":     sc_reason,
            "topic":      top_topic,
            "sentiment":  sentiment,
            "platform":   "youtube",
        })
        total += snapped_end - snapped_start

    # Fallback: all valid scenes in order
    if not clips:
        for scene in raw_shots:
            if scene["duration"] < 6.0:
                continue
            if total + scene["duration"] > target_duration:
                break
            clips.append({
                "start_time": scene["start_time"],
                "end_time":   scene["end_time"],
                "reason":     "Scene boundary fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += scene["duration"]

    # Last resort: evenly sampled 8s windows
    if not clips:
        step = max(10.0, raw_duration / 10)
        t = 0.0
        while t + 6.0 <= raw_duration and total + 6.0 <= target_duration:
            end = min(t + 8.0, raw_duration)
            clips.append({
                "start_time": round(t, 2),
                "end_time":   round(end, 2),
                "reason":     "Evenly sampled fallback clip",
                "topic":      "General",
                "sentiment":  "Positive",
                "platform":   "youtube",
            })
            total += end - t
            t += step

    clip_score = round(min(1.0, len(clips) / max(1, len(raw_shots))) * 0.8, 3)

    # Build rationale — include creative direction summary if prefs were applied
    base_rationale = (
        f"Deterministic plan: {len(clips)} clips selected from raw footage "
        f"using beat alignment and sentiment-informed scene scoring."
    )
    if not _prefs.is_empty() and _prefs.summary_labels():
        creative_summary = " · ".join(_prefs.summary_labels())
        rationale = f"{base_rationale} Creative direction applied: {creative_summary}."
    else:
        rationale = base_rationale

    return {
        "platform":        "youtube",
        "clip_score":      clip_score,
        "clips":           clips,
        "target_duration": round(total, 2),
        "audio_fade_out":  True,
        "output_format":   "mp4",
        "rationale":       rationale,
        "scene_selection_rationale": [
            {"clip_index": i, "confidence": clip_score, "reason": c["reason"]}
            for i, c in enumerate(clips)
        ],
    }


# ── Public interface ──────────────────────────────────────────────────────────

class SmartTrailerAgent:
    """
    Smart Trailer Agent — generates a new trailer from raw footage guided by
    sample trailer analysis and audience sentiment from comments.

    Fully deterministic — no external API calls.

    Returns: (output_path, editing_plan, analysis_report, error_message,
              platform, clip_score, gemini_used=False, fallback_warning=None)
    """

    def __init__(self):
        self._structuring_agent = FeedbackStructuringAgent()

    def generate(
        self,
        raw_footage_path: str,
        sample_trailer_path: str,
        comments_path: str,
        job_id: str,
        user_prompt: str | None = None,
        audio=None,
        include_subtitles: bool = False,
        fast_mode: bool = False,
    ) -> tuple[str | None, TrailerEditingPlan | None, SmartTrailerAnalysis | None,
               str | None, str | None, float | None, bool, str | None, float | None]:
        # Returns: (output_path, plan, analysis, error, platform, clip_score,
        #           gemini_used=False, fallback_warning, raw_footage_duration_secs)

        # Fast mode: subtitles require transcript — silently disable if fast_mode is on
        if fast_mode and include_subtitles:
            logger.info("SmartTrailerAgent: fast_mode=True overrides include_subtitles=True — subtitles disabled")
            include_subtitles = False

        # Convert schema AudioSettings → composer AudioSettings
        composer_audio = None
        if audio is not None:
            composer_audio = ComposerAudioSettings(
                target_lufs=audio.target_lufs,
                bass_boost=audio.bass_boost,
                treble_cut=audio.treble_cut,
            )

        # Parse creative direction prompt before any heavy work
        prefs = _parse_creative_prompt(user_prompt)
        if not prefs.is_empty():
            logger.info(
                "SmartTrailerAgent: creative direction parsed — %s",
                ", ".join(prefs.summary_labels()),
            )

        # ── Stage 1: Parse comments ───────────────────────────────────────────
        from app.utils.render_progress import set_progress, init_steps, set_step
        _STEPS = [
            {"key": "comments",   "label": "Parsing audience comments",  "status": "pending", "percent": 0},
            {"key": "sample",     "label": "Analysing sample trailer",    "status": "pending", "percent": 0},
            {"key": "scenes",     "label": "Detecting scenes",            "status": "pending", "percent": 0},
            {"key": "transcript", "label": "Transcribing audio",          "status": "pending", "percent": 0},
            {"key": "beats",      "label": "Analysing beat rhythm",       "status": "pending", "percent": 0},
            {"key": "planning",   "label": "Planning clip selection",     "status": "pending", "percent": 0},
            {"key": "extracting", "label": "Extracting clips",            "status": "pending", "percent": 0},
            {"key": "composing",  "label": "Composing transitions",       "status": "pending", "percent": 0},
            {"key": "normalising","label": "Normalising audio",           "status": "pending", "percent": 0},
        ]
        # Only initialise if steps not already set by the API layer
        from app.utils.render_progress import get_progress as _gp
        if not (_gp(job_id) or {}).get("steps"):
            set_progress(job_id, "parsing", 0, "Starting pipeline", steps=_STEPS)
            init_steps(job_id, _STEPS)

        set_step(job_id, "comments", "active", 0, "Parsing audience comments…", overall_percent=2)
        raw_text = _read_comments_file(comments_path)
        if not raw_text.strip():
            return None, None, None, "Comments file is empty or unreadable.", None, None, False, None, None

        segments = self._structuring_agent.parse(raw_text)
        if not segments:
            return None, None, None, "No feedback segments could be extracted from comments.", None, None, False, None, None

        set_step(job_id, "comments", "done", 100, f"{len(segments)} segments parsed", overall_percent=8)
        logger.info("SmartTrailerAgent: parsed %d comment segments", len(segments))

        # ── Stage 2: Analyse sample trailer ──────────────────────────────────
        set_step(job_id, "sample", "active", 0, "Analysing sample trailer…", overall_percent=10)
        try:
            sample_duration = _get_video_duration(sample_trailer_path)
            sample_shots    = detect_scenes(sample_trailer_path)
        except Exception as exc:
            logger.warning("SmartTrailerAgent: sample trailer pre-processing failed: %s", exc)
            sample_duration = 120.0
            sample_shots    = []

        if sample_duration <= 0:
            sample_duration = 120.0

        analysis_raw = _analyse_sample_trailer(segments, sample_duration, sample_shots)
        set_step(job_id, "sample", "done", 100, f"{len(sample_shots)} shots analysed", overall_percent=18)
        logger.info("SmartTrailerAgent: Stage 2 analysis complete — %d positive patterns", len(analysis_raw["positive_patterns"]))

        # ── Stage 3: Pre-process raw footage (sequential — CPU-bound tasks) ──
        set_step(job_id, "scenes",     "active", 0, "Detecting shot boundaries…", overall_percent=20)
        try:
            raw_duration = _get_video_duration(raw_footage_path)
            if raw_duration <= 0:
                return None, None, None, "Could not determine raw footage duration.", None, None, False, None, None

            raw_shots = detect_scenes(raw_footage_path)
            set_step(job_id, "scenes", "done", 100, f"{len(raw_shots)} scenes detected", overall_percent=30)

            if fast_mode:
                # Skip Whisper — return empty transcript so all downstream code
                # that checks transcript.get("segments", []) gets an empty list.
                # Beat detection still runs (librosa, not Whisper — fast).
                raw_transcript = {"segments": [], "words": [], "language": "", "full_text": ""}
                set_step(job_id, "transcript", "done", 100, "Skipped (fast demo mode)", overall_percent=40)
                logger.info("SmartTrailerAgent: fast_mode=True — Whisper transcription skipped")
            else:
                set_step(job_id, "transcript", "active", 0, "Transcribing audio…", overall_percent=31)
                raw_transcript = transcribe(raw_footage_path)
                set_step(job_id, "transcript", "done", 100, f"{len(raw_transcript['segments'])} segments transcribed", overall_percent=40)

            set_step(job_id, "beats", "active", 0, "Analysing beat rhythm…", overall_percent=41)
            raw_beats = detect_beats(raw_footage_path)
            set_step(job_id, "beats", "done", 100, f"{raw_beats['beat_count']} beats at {raw_beats['tempo']:.0f} BPM", overall_percent=48)

        except Exception as exc:
            return None, None, None, f"Raw footage pre-processing failed: {exc}", None, None, False, None, None

        logger.info(
            "SmartTrailerAgent: raw footage — %.1fs, %d shots, %d transcript segs, %.1f BPM",
            raw_duration, len(raw_shots), len(raw_transcript["segments"]), raw_beats["tempo"],
        )

        # Append fast mode note to rationale so it surfaces in the editing plan
        _fast_mode_note = " [Fast demo mode: transcription skipped]" if fast_mode else ""

        target_duration = max(60.0, min(120.0, round(raw_duration * 0.25)))

        # ── Stage 3: Plan clips ───────────────────────────────────────────────
        set_step(job_id, "planning", "active", 0, "Scoring and selecting clips…", overall_percent=50)
        plan_raw = _plan_clips_from_raw(
            analysis_raw, raw_duration, target_duration,
            raw_shots, raw_beats, raw_transcript,
            prefs=prefs,
        )

        if not plan_raw.get("clips"):
            return None, None, None, "No clips could be planned from raw footage.", None, None, False, None, None

        set_step(job_id, "planning", "done", 100, f"{len(plan_raw['clips'])} clips planned", overall_percent=55)
        platform   = plan_raw["platform"]
        clip_score = plan_raw["clip_score"]

        logger.info("SmartTrailerAgent: Stage 3 plan — %d clips, score=%.3f", len(plan_raw["clips"]), clip_score)

        # Build SmartTrailerAnalysis — extend influence_explanation with creative direction
        creative_note = ""
        if not prefs.is_empty() and prefs.summary_labels():
            creative_note = " Editor creative direction: " + " · ".join(prefs.summary_labels()) + "."

        analysis = SmartTrailerAnalysis(
            sentiment_summary=analysis_raw["sentiment_summary"],
            positive_patterns=analysis_raw["positive_patterns"],
            negative_patterns=analysis_raw["negative_patterns"],
            top_scene_categories=analysis_raw["top_scene_categories"],
            influence_explanation=analysis_raw["influence_explanation"] + creative_note,
            scene_selection_rationale=plan_raw["scene_selection_rationale"],
        )

        # ── Stage 4: Convert plan → PlannedClip + mood classification only ──
        # Do NOT run process_clips — the planner already selected, bounded, and
        # budgeted every clip. Re-running boundary expansion + overlap removal
        # on score-sorted (non-chronological) clips destroys most of them.
        from app.utils.clip_planner import PlannedClip, get_transcript_text
        planned: list[PlannedClip] = [
            PlannedClip(
                start_time=float(c["start_time"]),
                end_time=float(c["end_time"]),
                reason=c.get("reason", ""),
                topic=c.get("topic", "General"),
                sentiment=c.get("sentiment", "Positive"),
                platform=c.get("platform", "youtube"),
                transcript_text=get_transcript_text(
                    float(c["start_time"]), float(c["end_time"]), raw_transcript
                ),
            )
            for c in plan_raw["clips"]
        ]
        # Sort chronologically so FFmpeg extracts in timeline order
        planned.sort(key=lambda c: c.start_time)
        # Mood classification only — for transition selection
        planned = classify_clips_by_mood(planned, raw_footage_path)
        # Force last clip to action mood for energetic ending
        if planned:
            planned[-1].mood_group = "action"

        if not planned:
            return None, None, analysis, "No clips remained after processing.", platform, clip_score, False, None, raw_duration

        logger.info("SmartTrailerAgent: %d clips ready (%.1fs total)",
                    len(planned), sum(c.end_time - c.start_time for c in planned))

        clips = [
            TrailerClip(
                start_time=c.start_time,
                end_time=c.end_time,
                reason=c.reason,
                topic=c.topic,
                sentiment=c.sentiment,
                platform=platform,
                mood_group=c.mood_group,
                transcript_text=c.transcript_text,
            )
            for c in planned
        ]
        plan = TrailerEditingPlan(
            clips=clips,
            target_duration=sum(c.end_time - c.start_time for c in planned),
            audio_fade_out=plan_raw["audio_fade_out"],
            output_format=plan_raw["output_format"],
            rationale=plan_raw["rationale"] + _fast_mode_note,
        )

        output_filename = f"smart_{job_id}_{uuid.uuid4().hex[:8]}.mp4"
        output_path     = os.path.join(TRAILERS_DIR, output_filename)

        logger.info(
            "SmartTrailerAgent: composing — platform=%s score=%.3f clips=%d → %s",
            platform, clip_score, len(plan.clips), output_path,
        )

        ok, err = compose(
            planned, raw_footage_path, output_path, raw_transcript,
            plan.audio_fade_out,
            job_id=job_id,
            beats=raw_beats.get("beats", []),
            audio_settings=composer_audio,
            include_subtitles=include_subtitles,
        )
        if not ok:
            return None, plan, analysis, err, platform, clip_score, False, None, raw_duration

        return output_path, plan, analysis, None, platform, clip_score, False, None, raw_duration
