"""
Video Optimization Agent

Consumes structured FeedbackSegment list + video metadata to produce:
    1. Human-readable OptimizationRecommendations
    2. A machine-readable EditingPlan

Now also consumes:
    - scene_boundaries: PySceneDetect output — used to snap recommendation
      timestamps to real scene edges rather than raw comment timestamps
    - transcript: Whisper output — used to identify speech-rich scenes
      worth preserving and flag silent/low-content scenes for trimming
"""

import logging
from collections import defaultdict
from app.schemas.feedback import (
    FeedbackSegment,
    OptimizationRecommendation,
    EditingPlan,
    EditingOperation,
)

logger = logging.getLogger(__name__)

_HIGH_THRESHOLD   = 2
_MEDIUM_THRESHOLD = 1


def _snap_to_scene(ts_secs: float, scene_boundaries: list[dict]) -> str | None:
    """
    Snap a float timestamp (seconds) to the nearest scene boundary start.
    Returns MM:SS string or None if no boundaries available.
    """
    if not scene_boundaries:
        return None
    best = min(scene_boundaries, key=lambda s: abs(s["start_time"] - ts_secs))
    m = int(best["start_time"]) // 60
    s = int(best["start_time"]) % 60
    return f"{m:02d}:{s:02d}"


def _mm_ss_to_seconds(ts: str) -> float | None:
    try:
        parts = [int(p) for p in ts.split(":")]
        if len(parts) == 2:
            return float(parts[0] * 60 + parts[1])
        if len(parts) == 3:
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    except Exception:
        pass
    return None


def _speech_density(start: float, end: float, transcript: dict) -> float:
    """
    Return fraction of the clip window covered by speech segments [0.0–1.0].
    Used to flag speech-rich scenes as high-value for preservation.
    """
    segments = transcript.get("segments", []) if transcript else []
    if not segments or end <= start:
        return 0.0
    window = end - start
    covered = 0.0
    for seg in segments:
        overlap_start = max(seg["start"], start)
        overlap_end   = min(seg["end"],   end)
        if overlap_end > overlap_start:
            covered += overlap_end - overlap_start
    return min(1.0, covered / window)


class VideoOptimizationAgent:
    """
    Video Optimization Agent.

    Accepts structured feedback segments, video metadata, and optionally
    scene boundaries + transcript for richer, scene-anchored recommendations.
    """

    def analyze(
        self,
        segments: list[FeedbackSegment],
        video_metadata: dict,
        scene_boundaries: list | None = None,
        transcript: dict | None = None,
        detected_objects: list | None = None,
        audio_features: dict | None = None,
        ocr_results: list | None = None,
    ) -> tuple[list[OptimizationRecommendation], EditingPlan]:

        topic_sentiments: dict[str, list[FeedbackSegment]] = defaultdict(list)
        for seg in segments:
            topic_sentiments[seg.topic].append(seg)

        recommendations: list[OptimizationRecommendation] = []
        operations:      list[EditingOperation]            = []

        for topic, segs in topic_sentiments.items():
            neg         = [s for s in segs if s.sentiment in ("Negative", "Complaint")]
            pos         = [s for s in segs if s.sentiment in ("Positive", "Praise")]
            suggestions = [s for s in segs if s.sentiment == "Suggestion"]

            # Derive timestamp — snap to nearest scene boundary if available
            raw_ts   = next((s.timestamp for s in segs if s.timestamp), None)
            raw_secs = _mm_ss_to_seconds(raw_ts) if raw_ts else None
            timestamp = (
                _snap_to_scene(raw_secs, scene_boundaries)
                if raw_secs is not None and scene_boundaries
                else raw_ts
            )

            # Speech density at this timestamp — used to adjust recommendations
            speech_density = 0.0
            if transcript and raw_secs is not None:
                speech_density = _speech_density(
                    max(0.0, raw_secs - 3.0),
                    raw_secs + 3.0,
                    transcript,
                )

            # ── Negative pattern ──────────────────────────────────────────
            if neg:
                priority = "High" if len(neg) >= _HIGH_THRESHOLD else "Medium"
                reason   = self._summarise(neg, topic, "negative")
                action   = self._action_for_topic(topic, "negative")

                # If this negative segment has high speech density, add a note
                if speech_density > 0.6:
                    reason += f" (speech-dense segment — preserve dialogue when trimming)"

                recommendations.append(OptimizationRecommendation(
                    priority=priority, timestamp=timestamp,
                    action=action, reason=reason,
                ))
                operations.append(EditingOperation(
                    priority=priority, timestamp=timestamp,
                    operation=self._operation_for_topic(topic, "negative"),
                    reason=reason,
                ))

            # ── Positive pattern ──────────────────────────────────────────
            if pos:
                priority = "High" if len(pos) >= _HIGH_THRESHOLD else "Medium"
                reason   = self._summarise(pos, topic, "positive")
                action   = f"Preserve and expand {topic} segment"

                # High speech density on a positive segment = key dialogue moment
                if speech_density > 0.6:
                    action  = f"Preserve {topic} segment — key dialogue moment"
                    reason += " High speech density indicates important spoken content."

                recommendations.append(OptimizationRecommendation(
                    priority=priority, timestamp=timestamp,
                    action=action, reason=reason,
                ))
                operations.append(EditingOperation(
                    priority=priority, timestamp=timestamp,
                    operation="increase_duration", duration=8,
                    reason=reason,
                ))

            # ── Suggestion pattern ────────────────────────────────────────
            if suggestions and not neg:
                reason = self._summarise(suggestions, topic, "suggestion")
                recommendations.append(OptimizationRecommendation(
                    priority="Low", timestamp=timestamp,
                    action=f"Consider audience suggestion for {topic}",
                    reason=reason,
                ))
                operations.append(EditingOperation(
                    priority="Low", timestamp=timestamp,
                    operation="review", reason=reason,
                ))

        # ── Scene-level recommendations from boundaries ───────────────────
        if scene_boundaries and transcript:
            self._add_scene_recommendations(
                scene_boundaries, transcript, recommendations, operations,
            )

        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 3))
        operations.sort(key=lambda o: priority_order.get(o.priority, 3))

        logger.info(
            "VideoOptimizationAgent: %d recommendations from %d segments (%d scenes, transcript=%s)",
            len(recommendations), len(segments),
            len(scene_boundaries) if scene_boundaries else 0,
            "yes" if transcript else "no",
        )
        return recommendations, EditingPlan(editing_plan=operations)

    def _add_scene_recommendations(
        self,
        scene_boundaries: list[dict],
        transcript: dict,
        recommendations: list[OptimizationRecommendation],
        operations: list[EditingOperation],
    ) -> None:
        """
        Add scene-level recommendations based on speech density per scene.
        Flags very long silent scenes (>15s, <10% speech) as trim candidates.
        Flags speech-rich scenes (>70% speech) as preserve candidates.
        """
        for scene in scene_boundaries:
            dur     = scene["duration"]
            density = _speech_density(scene["start_time"], scene["end_time"], transcript)
            ts      = scene["timestamp"]

            if dur > 15.0 and density < 0.10:
                recommendations.append(OptimizationRecommendation(
                    priority="Low", timestamp=ts,
                    action="Consider trimming silent scene",
                    reason=f"Scene at {ts} is {dur:.0f}s with <10% speech — may reduce pacing.",
                ))
                operations.append(EditingOperation(
                    priority="Low", timestamp=ts,
                    operation="trim",
                    reason=f"Long silent scene ({dur:.0f}s) detected at {ts}.",
                ))

            elif dur >= 6.0 and density > 0.70:
                recommendations.append(OptimizationRecommendation(
                    priority="Low", timestamp=ts,
                    action="Preserve speech-rich scene",
                    reason=f"Scene at {ts} has {density:.0%} speech coverage — high dialogue value.",
                ))
                operations.append(EditingOperation(
                    priority="Low", timestamp=ts,
                    operation="increase_duration", duration=int(dur),
                    reason=f"Speech-rich scene ({density:.0%} coverage) at {ts}.",
                ))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _summarise(self, segs: list[FeedbackSegment], topic: str, polarity: str) -> str:
        count = len(segs)
        noun  = "viewers" if count > 1 else "a viewer"
        if polarity == "positive":
            return f"{count} {noun} praised the {topic} segment."
        if polarity == "negative":
            return f"{count} {noun} raised concerns about {topic}."
        return f"{count} {noun} suggested improvements to {topic}."

    def _action_for_topic(self, topic: str, polarity: str) -> str:
        if polarity != "negative":
            return f"Preserve {topic}"
        return {
            "Music":               "Reduce background music volume",
            "Intro":               "Shorten the introduction",
            "Pacing":              "Improve overall pacing",
            "Transitions":         "Smooth out transitions",
            "Engagement":          "Restructure to hook viewers earlier",
            "Narration":           "Improve narration clarity",
            "Feature Explanation": "Clarify feature explanation segment",
            "Subtitles":           "Add or improve subtitles",
        }.get(topic, f"Review and improve {topic} segment")

    def _operation_for_topic(self, topic: str, polarity: str) -> str:
        if polarity != "negative":
            return "increase_duration"
        return {
            "Music":       "reduce_audio",
            "Intro":       "trim",
            "Pacing":      "trim",
            "Transitions": "smooth_transition",
            "Engagement":  "reorder",
            "Subtitles":   "add_subtitles",
            "Narration":   "re_narrate",
        }.get(topic, "review")
