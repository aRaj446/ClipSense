"""
Feedback Structuring Agent — Stage 1

Primary:  HuggingFace zero-shot classification (facebook/bart-large-mnli)
          Runs fully local — no API key, no external calls.
          Model is lazy-loaded on first use and cached for the process lifetime.

Fallback: Regex + keyword heuristics — used if the model fails to load
          or inference raises an exception.

Pipeline contract (unchanged):
    FeedbackStructuringAgent.parse(raw_text: str) -> list[FeedbackSegment]
"""

import re
import logging
from app.schemas.feedback import FeedbackSegment

logger = logging.getLogger(__name__)

# ── Valid label sets ──────────────────────────────────────────────────────────

VALID_TOPICS = [
    "Camera", "Music", "Narration", "Transitions", "Intro", "Ending",
    "Product Demo", "Subtitles", "Pacing", "Engagement", "Animation",
    "Feature Explanation", "Pricing", "General",
]

VALID_SENTIMENTS = [
    "Positive", "Negative", "Neutral", "Suggestion", "Complaint", "Praise", "Question",
]

# ── HuggingFace model (lazy singleton) ───────────────────────────────────────

_classifier = None
_MODEL_NAME = "facebook/bart-large-mnli"


def _get_classifier():
    """Lazy-load the zero-shot classifier. Returns None if unavailable."""
    global _classifier
    if _classifier is not None:
        return _classifier
    try:
        from transformers import pipeline
        logger.info("FeedbackStructuringAgent: loading %s …", _MODEL_NAME)
        _classifier = pipeline(
            "zero-shot-classification",
            model=_MODEL_NAME,
            device=-1,          # CPU — set to 0 for GPU if available
            multi_label=False,
        )
        logger.info("FeedbackStructuringAgent: model loaded successfully")
        return _classifier
    except Exception as exc:
        logger.warning("FeedbackStructuringAgent: could not load HuggingFace model (%s) — regex fallback active", exc)
        return None


def _classify_line(clf, text: str) -> tuple[str, str, float]:
    """
    Run zero-shot classification for both topic and sentiment in two passes.
    Returns (topic, sentiment, confidence).
    Confidence is the geometric mean of both classification scores.
    """
    topic_result     = clf(text, VALID_TOPICS,     hypothesis_template="This feedback is about {}.")
    sentiment_result = clf(text, VALID_SENTIMENTS, hypothesis_template="The sentiment of this feedback is {}.")

    topic     = topic_result["labels"][0]
    sentiment = sentiment_result["labels"][0]

    # Geometric mean of top scores — reflects joint confidence
    topic_score     = float(topic_result["scores"][0])
    sentiment_score = float(sentiment_result["scores"][0])
    confidence      = round((topic_score * sentiment_score) ** 0.5, 3)
    confidence      = max(0.40, min(1.00, confidence))

    return topic, sentiment, confidence


# ── HuggingFace primary path ──────────────────────────────────────────────────

def _hf_parse(raw_feedback: str) -> list[FeedbackSegment] | None:
    """Parse feedback using HuggingFace zero-shot classification."""
    clf = _get_classifier()
    if clf is None:
        return None

    raw_lines = re.split(r"[\n]+", raw_feedback)
    segments: list[FeedbackSegment] = []
    seen: set[str] = set()

    for raw_line in raw_lines:
        line = _clean_line(raw_line)
        if len(line) < 8:
            continue
        key = line.lower()
        if key in seen or key.strip("! ") in _SPAM_EXACT:
            continue
        seen.add(key)

        try:
            topic, sentiment, confidence = _classify_line(clf, line)
        except Exception as exc:
            logger.warning("FeedbackStructuringAgent: HF inference failed on line, skipping: %s", exc)
            continue

        segments.append(FeedbackSegment(
            timestamp=_extract_timestamp(line),
            topic=topic,
            sentiment=sentiment,
            summary=line[:120],
            confidence=confidence,
        ))

    return segments if segments else None


# ── Regex fallback ────────────────────────────────────────────────────────────

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Camera":              ["camera", "shot", "close-up", "closeup", "footage", "visual", "picture", "image"],
    "Music":               ["music", "audio", "sound", "song", "track", "beat", "volume", "loud", "background"],
    "Narration":           ["narration", "narrator", "voice", "voiceover", "voice-over", "speaking"],
    "Transitions":         ["transition", "cut", "jump", "edit", "switch", "awkward"],
    "Intro":               ["intro", "introduction", "beginning", "start", "opening", "first minute", "first 30"],
    "Ending":              ["ending", "outro", "conclusion", "end", "finish", "last"],
    "Product Demo":        ["demo", "demonstration", "product", "feature", "showcase", "show"],
    "Subtitles":           ["subtitle", "subtitles", "caption", "captions", "text", "multilingual", "language"],
    "Pacing":              ["long", "short", "slow", "fast", "pace", "pacing", "skip", "boring", "drag"],
    "Engagement":          ["stopped watching", "dropped off", "lost interest", "engaged", "hooked", "attention"],
    "Animation":           ["animation", "animated", "motion", "graphic", "effect", "vfx"],
    "Feature Explanation": ["feature", "explanation", "explain", "how it works", "tutorial", "walkthrough"],
    "Pricing":             ["price", "pricing", "cost", "expensive", "cheap", "value"],
}

_POSITIVE_WORDS = {
    "amazing", "incredible", "loved", "great", "excellent", "awesome", "fantastic",
    "beautiful", "perfect", "best", "brilliant", "outstanding", "superb", "wonderful",
    "nice", "good", "enjoy", "enjoyed", "impressive", "love", "like", "liked",
    "goosebumps", "iconic", "insane", "gorgeous", "unbelievable",
    "highlight", "favorite", "favourite", "never misses", "never disappoints",
    "deserves", "hype", "fits perfectly", "wow", "fire",
}
_NEGATIVE_WORDS = {
    "too long", "too loud", "skip", "boring", "bad", "terrible", "awful", "poor",
    "stopped watching", "dropped", "lost interest", "awkward", "confusing",
    "unclear", "disappointed", "hate", "hated", "dislike", "disliked",
    "not impressed", "difficult to hear", "too slow", "too many",
    "stayed too long", "pacing", "worse", "worst",
}
_SUGGESTION_WORDS = {
    "wish", "should", "could", "would", "suggest", "recommend", "consider",
    "maybe", "perhaps", "improve", "add", "include", "need more", "move the",
    "add subtitles", "more gameplay", "explain", "can someone",
}

_TIMESTAMP_PATTERNS = [
    re.compile(r'\b(\d{1,2}:\d{2}(?::\d{2})?)\b'),
    re.compile(r'\b(\d+)\s*m(?:in(?:ute)?s?)?\s*(\d+)\s*s(?:ec(?:ond)?s?)?\b'),
    re.compile(r'\b(\d+)\s*(?:min(?:ute)?s?)\b'),
    re.compile(r'\b(\d+)\s*(?:sec(?:ond)?s?)\b'),
]

_SPAM_EXACT = {"first", "first!!", "w", "lol", "lmao", "nice", "fire", "🔥", "😂"}

_CLEAN_PATTERNS = [
    re.compile(r'https?://\S+'),
    re.compile(r'#\w+'),
    re.compile(r'@\w+'),
    re.compile(r'[^\x00-\x7F\u0900-\u097F\u3040-\u30FF\u4E00-\u9FFF\s]+'),
]


def _clean_line(text: str) -> str:
    for pat in _CLEAN_PATTERNS:
        text = pat.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _extract_timestamp(text: str) -> str | None:
    t = text.lower()
    m = _TIMESTAMP_PATTERNS[0].search(t)
    if m: return m.group(1)
    m = _TIMESTAMP_PATTERNS[1].search(t)
    if m: return f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    m = _TIMESTAMP_PATTERNS[2].search(t)
    if m: return f"{int(m.group(1)):02d}:00"
    m = _TIMESTAMP_PATTERNS[3].search(t)
    if m: return f"00:{int(m.group(1)):02d}"
    return None


def _detect_topic(text: str) -> str:
    lower = text.lower()
    scores = {t: sum(1 for kw in kws if kw in lower) for t, kws in _TOPIC_KEYWORDS.items()}
    scores = {t: s for t, s in scores.items() if s}
    return max(scores, key=lambda k: scores[k]) if scores else "General"


def _detect_sentiment(text: str) -> tuple[str, float]:
    lower = text.lower()
    is_suggestion = any(w in lower for w in _SUGGESTION_WORDS)
    pos = sum(1 for w in _POSITIVE_WORDS if w in lower)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in lower)
    if is_suggestion and neg == 0: return "Suggestion", 0.80
    if pos > neg: return "Positive", round(min(0.70 + pos * 0.08, 0.98), 2)
    if neg > pos: return "Negative", round(min(0.70 + neg * 0.08, 0.98), 2)
    if is_suggestion: return "Suggestion", 0.75
    return "Neutral", 0.60


def _regex_parse(raw_feedback: str) -> list[FeedbackSegment]:
    raw_lines = re.split(r'[\n]+', raw_feedback)
    segments: list[FeedbackSegment] = []
    seen: set[str] = set()

    for raw_line in raw_lines:
        line = _clean_line(raw_line)
        if len(line) < 8:
            continue
        key = line.lower()
        if key in seen or key.strip('! ') in _SPAM_EXACT:
            continue
        seen.add(key)

        sentiment, confidence = _detect_sentiment(line)
        segments.append(FeedbackSegment(
            timestamp=_extract_timestamp(line),
            topic=_detect_topic(line),
            sentiment=sentiment,
            summary=line[:120],
            confidence=confidence,
        ))
    return segments


# ── Public interface ──────────────────────────────────────────────────────────

class FeedbackStructuringAgent:
    """
    Stage 1 — Feedback Structuring Agent.

    Parses raw unstructured audience feedback into structured FeedbackSegment list.

    Primary:  HuggingFace zero-shot classification (facebook/bart-large-mnli).
              Runs fully local — no API key required.
    Fallback: Regex + keyword heuristics if the model is unavailable.
    """

    def parse(self, raw_feedback: str) -> list[FeedbackSegment]:
        result = _hf_parse(raw_feedback)
        if result is not None:
            logger.info("FeedbackStructuringAgent: HuggingFace parsed %d segments", len(result))
            return result

        logger.warning("FeedbackStructuringAgent: HuggingFace unavailable — using regex fallback")
        segments = _regex_parse(raw_feedback)
        logger.info("FeedbackStructuringAgent: regex fallback parsed %d segments", len(segments))
        return segments
