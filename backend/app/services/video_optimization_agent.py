"""
Video Optimization Agent — Module 2

Responsibility:
    Consume structured feedback segments (from the Feedback Structuring Agent)
    and video metadata to produce:
      1. Human-readable OptimizationRecommendations
      2. A machine-readable EditingPlan for the future Video Regeneration Agent

This module NEVER parses raw feedback text.
It only consumes structured FeedbackSegment objects.

Future upgrade path:
    Replace the `analyze()` method body with an LLM call that receives the
    structured segments as a JSON prompt. The EditingPlan contract remains stable
    so the Video Regeneration Agent can consume it without changes.

Future inputs (designed for, not yet implemented):
    - scene_boundaries: list of detected scene timestamps
    - transcript: speech-to-text output with word-level timestamps
    - detected_objects: object detection results per frame
    - audio_features: volume, music presence, speech segments
    - ocr_results: on-screen text detected per frame
"""

from collections import defaultdict
from app.schemas.feedback import (
    FeedbackSegment,
    OptimizationRecommendation,
    EditingPlan,
    EditingOperation,
)


# Priority thresholds — how many mentions before escalating priority
_HIGH_THRESHOLD = 2
_MEDIUM_THRESHOLD = 1


class VideoOptimizationAgent:
    """
    Module 2 — Video Optimization Agent.

    Accepts structured feedback segments and video metadata.
    Returns recommendations and a structured editing plan.

    To integrate an LLM in a future phase, replace the body of `analyze()`
    with a prompt-based API call. The input/output contracts remain unchanged.
    """

    def analyze(
        self,
        segments: list[FeedbackSegment],
        video_metadata: dict,
        # Future parameters — accepted but not yet used:
        scene_boundaries: list | None = None,
        transcript: list | None = None,
        detected_objects: list | None = None,
        audio_features: dict | None = None,
        ocr_results: list | None = None,
    ) -> tuple[list[OptimizationRecommendation], EditingPlan]:
        """
        Analyze structured feedback and produce recommendations + editing plan.

        Args:
            segments:          Structured output from FeedbackStructuringAgent.
            video_metadata:    Dict with duration, width, height, fps, codec, etc.
            scene_boundaries:  (Future) Scene detection results.
            transcript:        (Future) Speech-to-text with timestamps.
            detected_objects:  (Future) Per-frame object detection.
            audio_features:    (Future) Audio analysis results.
            ocr_results:       (Future) On-screen text per frame.

        Returns:
            Tuple of (recommendations list, editing plan).
        """
        # Group segments by topic and sentiment for pattern detection
        topic_sentiments: dict[str, list[FeedbackSegment]] = defaultdict(list)
        for seg in segments:
            topic_sentiments[seg.topic].append(seg)

        recommendations: list[OptimizationRecommendation] = []
        operations: list[EditingOperation] = []

        for topic, segs in topic_sentiments.items():
            neg = [s for s in segs if s.sentiment in ("Negative", "Complaint")]
            pos = [s for s in segs if s.sentiment in ("Positive", "Praise")]
            suggestions = [s for s in segs if s.sentiment == "Suggestion"]

            # Derive a representative timestamp (first one found in the group)
            timestamp = next((s.timestamp for s in segs if s.timestamp), None)

            # ── Negative pattern → recommend fix ──────────────────────────
            if neg:
                priority = "High" if len(neg) >= _HIGH_THRESHOLD else "Medium"
                reason = self._summarise(neg, topic, "negative")
                action = self._action_for_topic(topic, "negative")

                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    timestamp=timestamp,
                    action=action,
                    reason=reason,
                ))
                operations.append(EditingOperation(
                    priority=priority,
                    timestamp=timestamp,
                    operation=self._operation_for_topic(topic, "negative"),
                    reason=reason,
                ))

            # ── Positive pattern → recommend preserving / expanding ────────
            if pos:
                priority = "High" if len(pos) >= _HIGH_THRESHOLD else "Medium"
                reason = self._summarise(pos, topic, "positive")
                action = f"Preserve and expand {topic} segment"

                recommendations.append(OptimizationRecommendation(
                    priority=priority,
                    timestamp=timestamp,
                    action=action,
                    reason=reason,
                ))
                operations.append(EditingOperation(
                    priority=priority,
                    timestamp=timestamp,
                    operation="increase_duration",
                    duration=8,
                    reason=reason,
                ))

            # ── Suggestion pattern → recommend consideration ───────────────
            if suggestions and not neg:
                reason = self._summarise(suggestions, topic, "suggestion")
                recommendations.append(OptimizationRecommendation(
                    priority="Low",
                    timestamp=timestamp,
                    action=f"Consider audience suggestion for {topic}",
                    reason=reason,
                ))
                operations.append(EditingOperation(
                    priority="Low",
                    timestamp=timestamp,
                    operation="review",
                    reason=reason,
                ))

        # Sort by priority
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 3))
        operations.sort(key=lambda o: priority_order.get(o.priority, 3))

        return recommendations, EditingPlan(editing_plan=operations)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _summarise(self, segs: list[FeedbackSegment], topic: str, polarity: str) -> str:
        count = len(segs)
        noun = "viewers" if count > 1 else "a viewer"
        if polarity == "positive":
            return f"{count} {noun} praised the {topic} segment."
        if polarity == "negative":
            return f"{count} {noun} raised concerns about {topic}."
        return f"{count} {noun} suggested improvements to {topic}."

    def _action_for_topic(self, topic: str, polarity: str) -> str:
        if polarity != "negative":
            return f"Preserve {topic}"
        actions = {
            "Music":               "Reduce background music volume",
            "Intro":               "Shorten the introduction",
            "Pacing":              "Improve overall pacing",
            "Transitions":         "Smooth out transitions",
            "Engagement":          "Restructure to hook viewers earlier",
            "Narration":           "Improve narration clarity",
            "Feature Explanation": "Clarify feature explanation segment",
            "Subtitles":           "Add or improve subtitles",
        }
        return actions.get(topic, f"Review and improve {topic} segment")

    def _operation_for_topic(self, topic: str, polarity: str) -> str:
        if polarity != "negative":
            return "increase_duration"
        ops = {
            "Music":               "reduce_audio",
            "Intro":               "trim",
            "Pacing":              "trim",
            "Transitions":         "smooth_transition",
            "Engagement":          "reorder",
            "Subtitles":           "add_subtitles",
            "Narration":           "re_narrate",
        }
        return ops.get(topic, "review")
