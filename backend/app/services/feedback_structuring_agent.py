"""
Feedback Structuring Agent — Module 1

Primary:  Gemini 2.5 Pro (multimodal LLM) — reads raw unstructured text and
          returns structured FeedbackSegment JSON in a single API call.
Fallback: Regex + keyword heuristics — used when GEMINI_API_KEY is not set
          or the Gemini call fails.

To activate Gemini: set GEMINI_API_KEY in backend/.env
"""

import os
import re
import json
import logging
from app.schemas.feedback import FeedbackSegment

logger = logging.getLogger(__name__)

# ── Gemini setup ──────────────────────────────────────────────────────────────

_GEMINI_MODEL = "models/gemini-3.1-flash-lite"


def _get_gemini_key() -> str:
    return os.getenv("GEMINI_FREE_API_KEY") or os.getenv("GEMINI_API_KEY", "")

_GEMINI_PROMPT = """You are the Feedback Structuring Agent of an AI-powered Video Marketing Optimization Platform.
Your ONLY job is to convert raw unstructured audience feedback into a normalized structured JSON dataset.
Do NOT perform analytics, aggregation, recommendations, or optimization.

DATA CLEANING:
- Remove duplicate comments, URLs, emojis, usernames (@), hashtags (#), spam.
- Ignore meaningless comments ("First", "W", "LOL", standalone emoji) unless they express a clear opinion.
- Normalize punctuation and trim whitespace.
- Feedback may be multilingual — always output English summaries.

TIMESTAMP EXTRACTION:
- Detect formats: 0:34 / 00:34 / 1m20s / 45sec. Normalize to MM:SS. Return null if absent. Never invent timestamps.

TOPIC — choose EXACTLY ONE from: Camera, Music, Narration, Transitions, Intro, Ending, Product Demo, Subtitles, Pacing, Engagement, Animation, Feature Explanation, Pricing, General

SENTIMENT — choose EXACTLY ONE from: Positive, Negative, Neutral, Suggestion, Complaint, Praise, Question

SUMMARY — one clean English sentence, max 120 characters, no slang, no emojis, no copied text.

CONFIDENCE — float 0.40–1.00

OUTPUT: Return ONLY a valid JSON array. No markdown. No explanation. No code fences.
Each object must have exactly: {{"timestamp": "MM:SS or null", "topic": "...", "sentiment": "...", "summary": "...", "confidence": 0.00}}

RAW FEEDBACK:
{feedback}
"""


def _extract_json(text: str) -> str:
    """Extract the first complete JSON array or object from a string."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
        text = text.strip()
    # Find outermost [ ] or { }
    for start_char, end_char in (('[', ']'), ('{', '}')):
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            return text[start:end + 1]
    return text


def _call_gemini(raw_feedback: str) -> list[FeedbackSegment] | None:
    """Call Gemini 2.5 Pro and parse the response into FeedbackSegment list."""
    import sys
    print("Entering Feedback Structuring Agent", flush=True, file=sys.stderr)
    try:
        import google.genai as genai
        client = genai.Client(api_key=_get_gemini_key())
        prompt = _GEMINI_PROMPT.replace("{feedback}", raw_feedback)
        print("About to call Gemini", flush=True, file=sys.stderr)
        print("Model:", _GEMINI_MODEL, flush=True, file=sys.stderr)
        print("Key prefix:", _get_gemini_key()[:8], flush=True, file=sys.stderr)
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
        )
        text = response.text.strip()
        text = _extract_json(text)

        # Repair truncated JSON array — drop the last incomplete object
        if not text.endswith("]"):
            last_complete = text.rfind("},")
            if last_complete != -1:
                text = text[: last_complete + 1] + "]"
            else:
                text = text + "]"  # best-effort

        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Gemini response is not a JSON array")

        segments = []
        for item in data:
            if not isinstance(item, dict):
                continue
            segments.append(FeedbackSegment(
                timestamp=item.get("timestamp") or None,
                topic=item.get("topic") or "General",
                sentiment=item.get("sentiment") or "Neutral",
                summary=str(item.get("summary", ""))[:120],
                confidence=float(item.get("confidence") or 0.75),
            ))
        return segments if segments else None

    except Exception as exc:
        logger.warning("Gemini call failed, falling back to regex parser: %s", exc)
        return None


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
    "amazing","incredible","loved","great","excellent","awesome","fantastic",
    "beautiful","perfect","best","brilliant","outstanding","superb","wonderful",
    "nice","good","enjoy","enjoyed","impressive","love","like","liked",
    "goosebumps","iconic","cooked","insane","gorgeous","unbelievable",
    "highlight","favorite","favourite","never misses","never disappoints",
    "deserves","hype","fits perfectly","steals every scene","stole","wow",
    "day one","take my money","can't wait","goty","replayed","magnifique",
    "increíble","unglaublich","already iconic","crazy","fire",
}
_NEGATIVE_WORDS = {
    "too long","too loud","skip","boring","bad","terrible","awful","poor",
    "stopped watching","dropped","lost interest","awkward","confusing",
    "unclear","disappointed","hate","hated","dislike","disliked",
    "not impressed","difficult to hear","too slow","too many",
    "stayed too long","show gameplay","pacing","worse","worst",
}
_SUGGESTION_WORDS = {
    "wish","should","could","would","suggest","recommend","consider",
    "maybe","perhaps","improve","add","include","need more","move the",
    "add subtitles","more gameplay","explain","can someone",
}

_TIMESTAMP_PATTERNS = [
    re.compile(r'\b(\d{1,2}:\d{2}(?::\d{2})?)\b'),
    re.compile(r'\b(\d+)\s*m(?:in(?:ute)?s?)?\s*(\d+)\s*s(?:ec(?:ond)?s?)?\b'),
    re.compile(r'\b(\d+)\s*(?:min(?:ute)?s?)\b'),
    re.compile(r'\b(\d+)\s*(?:sec(?:ond)?s?)\b'),
]


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


_CLEAN_PATTERNS = [
    re.compile(r'https?://\S+'),           # URLs
    re.compile(r'#\w+'),                   # hashtags
    re.compile(r'@\w+'),                   # usernames
    re.compile(r'[^\x00-\x7F\u0900-\u097F\u3040-\u30FF\u4E00-\u9FFF\s]+'),  # emojis / symbols
]

_SPAM_EXACT = {"first", "first!!", "w", "lol", "lmao", "nice", "fire", "🔥", "😂"}


def _clean_line(text: str) -> str:
    for pat in _CLEAN_PATTERNS:
        text = pat.sub(' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _regex_parse(raw_feedback: str) -> list[FeedbackSegment]:
    # Split only on newlines — never on sentence-ending punctuation
    # (timestamps and their comments live on the same line)
    raw_lines = re.split(r'[\n]+', raw_feedback)

    segments = []
    seen: set[str] = set()

    for raw_line in raw_lines:
        line = _clean_line(raw_line)
        if len(line) < 8:
            continue
        # Deduplicate
        key = line.lower()
        if key in seen:
            continue
        # Skip pure spam
        if key.strip('! ') in _SPAM_EXACT:
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
    Module 1 — Feedback Structuring Agent.

    Uses Gemini 2.5 Pro when GEMINI_API_KEY is set.
    Falls back to regex heuristics otherwise.
    """

    def parse(self, raw_feedback: str) -> list[FeedbackSegment]:
        if _get_gemini_key() and _get_gemini_key() != "your_gemini_api_key_here":
            result = _call_gemini(raw_feedback)
            if result is not None:
                logger.info("Gemini parsed %d segments", len(result))
                return result
            logger.warning("Gemini failed — using regex fallback")

        return _regex_parse(raw_feedback)
