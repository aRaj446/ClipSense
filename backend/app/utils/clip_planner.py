"""
Clip Planner Utility

Shared post-processing layer applied to every clip plan before FFmpeg execution.
Used by both VideoRegenerationAgent (Stage 3) and SmartTrailerAgent (Stage 4).

Responsibilities:
    1. Enforce 6-second minimum clip duration — extend or drop clips below threshold
    2. Strict transcript-safe boundaries — extend clip end to complete the current
       sentence; never cut mid-word or mid-sentence
    3. Mood/energy classification — label each clip as 'action', 'emotional',
       'dialogue', or 'calm' using librosa RMS energy analysis
    4. Mood-group reordering — keep similar mood clips together to avoid
       continuous pace changes; order: action → emotional → dialogue → calm
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MIN_CLIP_DURATION = 6.0   # seconds — hard minimum for any clip in the final output

# Mood group order for final assembly
_MOOD_ORDER = {"action": 0, "emotional": 1, "dialogue": 2, "calm": 3}


@dataclass
class PlannedClip:
    start_time:      float
    end_time:        float
    reason:          str
    topic:           str
    sentiment:       str
    platform:        str | None = None
    mood_group:      str = "calm"          # action | emotional | dialogue | calm
    transcript_text: str = ""              # full transcript text for this clip segment
    energy:          float = 0.0           # normalised RMS energy [0.0–1.0]


# ── Transcript helpers ────────────────────────────────────────────────────────

def extend_to_sentence_end(
    start: float,
    end: float,
    transcript: dict,
    video_duration: float,
    tolerance: float = 4.0,
) -> tuple[float, float]:
    """
    Strictly extend clip boundaries so no sentence is cut mid-way.

    - start is snapped BACK to the start of any sentence that begins within
      tolerance seconds after the desired start (never cut into ongoing speech)
    - end is extended FORWARD to the end of any sentence that overlaps the
      desired end boundary (never cut off a sentence in progress)

    Returns (adjusted_start, adjusted_end).
    """
    segments = transcript.get("segments", [])
    if not segments:
        return start, end

    adj_start = start
    adj_end   = end

    # Find any sentence that starts within [start, start+tolerance]
    # and snap start back to its beginning so we don't enter mid-sentence
    for seg in segments:
        if start <= seg["start"] <= start + tolerance:
            adj_start = min(adj_start, seg["start"])
            break

    # Find any sentence whose end falls within [end-tolerance, end+tolerance]
    # and extend our clip end to cover it completely
    for seg in segments:
        seg_start = seg["start"]
        seg_end   = seg["end"]
        # Sentence overlaps our clip end — extend to cover it
        if seg_start < adj_end < seg_end:
            adj_end = seg_end
        # Sentence starts just after our clip end — include it if within tolerance
        elif adj_end <= seg_start <= adj_end + tolerance:
            adj_end = seg_end

    adj_start = max(0.0, adj_start)
    adj_end   = min(video_duration, adj_end)
    return round(adj_start, 3), round(adj_end, 3)


def get_transcript_text(start: float, end: float, transcript: dict) -> str:
    """Extract all transcript text that falls within [start, end]."""
    segments = transcript.get("segments", [])
    parts = [
        seg["text"].strip()
        for seg in segments
        if seg["start"] >= start - 0.5 and seg["end"] <= end + 0.5
    ]
    return " ".join(parts).strip()


# ── Energy / mood classification ──────────────────────────────────────────────

def _extract_clip_energy(
    audio_y,
    sr: int,
    start: float,
    end: float,
) -> float:
    """Compute normalised mean RMS energy for a clip window."""
    import numpy as np
    import librosa
    start_sample = int(start * sr)
    end_sample   = int(end   * sr)
    clip_audio   = audio_y[start_sample:end_sample]
    if len(clip_audio) == 0:
        return 0.0
    rms = librosa.feature.rms(y=clip_audio)[0]
    return float(np.mean(rms))


def classify_mood(energy: float, energy_max: float, transcript_text: str) -> str:
    """
    Classify a clip's mood group based on energy level and transcript content.

    Thresholds (relative to max energy in the video):
        > 70% of max  → action
        > 40% of max  → emotional  (if speech present) or action (if no speech)
        > 15% of max  → dialogue   (if speech present) or calm
        ≤ 15% of max  → calm
    """
    if energy_max <= 0:
        return "calm"

    ratio = energy / energy_max
    has_speech = bool(transcript_text.strip())

    if ratio > 0.70:
        return "action"
    if ratio > 0.40:
        return "emotional" if has_speech else "action"
    if ratio > 0.15:
        return "dialogue" if has_speech else "calm"
    return "calm"


def classify_clips_by_mood(
    clips: list[PlannedClip],
    video_path: str,
) -> list[PlannedClip]:
    """
    Run librosa energy analysis on the video audio and assign mood_group
    to each clip. Falls back gracefully if librosa is unavailable.
    """
    try:
        import librosa
        import numpy as np
        import subprocess
        import tempfile
        import os

        # Extract mono audio via FFmpeg
        from app.utils.beat_detector import _get_ffmpeg
        ffmpeg = _get_ffmpeg()
        tmp_dir   = tempfile.mkdtemp(prefix="clipsense_mood_")
        audio_path = os.path.join(tmp_dir, "audio.wav")

        cmd = [ffmpeg, "-y", "-i", video_path, "-ac", "1", "-ar", "22050", "-vn", audio_path]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            logger.warning("clip_planner: audio extraction failed for mood classification")
            return clips

        y, sr = librosa.load(audio_path, sr=22050, mono=True)

        # Compute per-clip energy
        energies = [_extract_clip_energy(y, sr, c.start_time, c.end_time) for c in clips]
        energy_max = max(energies) if energies else 1.0

        for clip, energy in zip(clips, energies):
            clip.energy     = round(energy / energy_max if energy_max > 0 else 0.0, 3)
            clip.mood_group = classify_mood(energy, energy_max, clip.transcript_text)

        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

        logger.info(
            "clip_planner: mood classified %d clips — %s",
            len(clips),
            {g: sum(1 for c in clips if c.mood_group == g) for g in _MOOD_ORDER},
        )

    except Exception as exc:
        logger.warning("clip_planner: mood classification failed (%s) — defaulting to 'calm'", exc)

    return clips


# ── Overlap / duplicate removal ──────────────────────────────────────────────

def _remove_overlaps(clips: list[PlannedClip]) -> list[PlannedClip]:
    """
    Remove clips whose time ranges overlap with an already-accepted clip.
    When two clips overlap, keep the longer one.
    Clips are processed in original order; the first accepted clip wins
    unless a later clip is strictly longer and covers the same window.
    """
    if len(clips) <= 1:
        return clips

    # Sort by start_time for sweep
    sorted_clips = sorted(clips, key=lambda c: c.start_time)
    accepted: list[PlannedClip] = []

    for clip in sorted_clips:
        overlapping = [
            i for i, a in enumerate(accepted)
            if clip.start_time < a.end_time and clip.end_time > a.start_time
        ]
        if not overlapping:
            accepted.append(clip)
        else:
            # Replace the overlapping accepted clip if the new one is longer
            idx = overlapping[0]
            existing_dur = accepted[idx].end_time - accepted[idx].start_time
            new_dur      = clip.end_time - clip.start_time
            if new_dur > existing_dur:
                logger.debug(
                    "clip_planner: replacing overlap %.1f–%.1f with longer %.1f–%.1f",
                    accepted[idx].start_time, accepted[idx].end_time,
                    clip.start_time, clip.end_time,
                )
                accepted[idx] = clip

    removed = len(clips) - len(accepted)
    if removed:
        logger.info("clip_planner: removed %d overlapping clip(s)", removed)

    # Restore original mood-order after overlap removal
    return accepted


# ── Mood-group reordering ──────────────────────────────────────────────────────

def reorder_by_mood(clips: list[PlannedClip]) -> list[PlannedClip]:
    """
    Reorder clips so similar moods are grouped together.
    Order: action → emotional → dialogue → calm
    Within each group, preserve original relative order.
    Always keep the highest-energy clip first (strong opening).
    """
    if len(clips) <= 1:
        return clips

    groups: dict[str, list[PlannedClip]] = {g: [] for g in _MOOD_ORDER}
    for clip in clips:
        groups.setdefault(clip.mood_group, []).append(clip)

    reordered: list[PlannedClip] = []
    for mood in sorted(_MOOD_ORDER, key=lambda m: _MOOD_ORDER[m]):
        reordered.extend(groups[mood])

    # Ensure the highest-energy clip opens the trailer
    if reordered:
        best_idx = max(range(len(reordered)), key=lambda i: reordered[i].energy)
        if best_idx != 0:
            reordered.insert(0, reordered.pop(best_idx))

    return reordered


# ── Main entry point ──────────────────────────────────────────────────────────

def process_clips(
    raw_clips: list[dict],
    transcript: dict,
    video_duration: float,
    video_path: str,
    target_duration: float,
) -> list[PlannedClip]:
    """
    Full clip processing pipeline:
        1. Convert raw dicts to PlannedClip objects
        2. Extend boundaries to complete sentences (strict)
        3. Enforce 6-second minimum — extend if possible, drop if not
        4. Classify mood via librosa energy
        5. Reorder by mood group
        6. Re-enforce target_duration after reorder

    Returns final list of PlannedClip objects ready for FFmpeg.
    """
    planned: list[PlannedClip] = []

    for raw in raw_clips:
        start = max(0.0, float(raw.get("start_time", 0.0)))
        end   = min(video_duration, float(raw.get("end_time", video_duration)))

        # Step 1: extend to sentence boundaries
        start, end = extend_to_sentence_end(start, end, transcript, video_duration)

        # Step 2: enforce 6-second minimum
        if end - start < MIN_CLIP_DURATION:
            # Try extending end first
            extended_end = min(video_duration, start + MIN_CLIP_DURATION)
            extended_end_safe, _ = extend_to_sentence_end(start, extended_end, transcript, video_duration)
            extended_end = max(extended_end, extended_end_safe)
            if extended_end - start >= MIN_CLIP_DURATION:
                end = extended_end
            else:
                # Try pulling start back
                extended_start = max(0.0, end - MIN_CLIP_DURATION)
                if end - extended_start >= MIN_CLIP_DURATION:
                    start = extended_start
                else:
                    logger.debug("clip_planner: dropping clip %.1f–%.1f (too short after extension)", start, end)
                    continue

        # Step 3: get transcript text for this clip
        text = get_transcript_text(start, end, transcript)

        planned.append(PlannedClip(
            start_time=start,
            end_time=end,
            reason=raw.get("reason", ""),
            topic=raw.get("topic", "General"),
            sentiment=raw.get("sentiment", "Neutral"),
            platform=raw.get("platform"),
            transcript_text=text,
        ))

    if not planned:
        return planned

    # Step 4: remove overlapping clips — keep the longer one when two clips overlap
    planned = _remove_overlaps(planned)

    if not planned:
        return planned

    # Step 5: classify mood
    planned = classify_clips_by_mood(planned, video_path)

    # Step 6: reorder by mood group
    planned = reorder_by_mood(planned)

    # Step 7: trim to target_duration
    final: list[PlannedClip] = []
    total = 0.0
    for clip in planned:
        dur = clip.end_time - clip.start_time
        if total + dur > target_duration + 5.0:   # allow 5s overshoot for sentence completion
            break
        final.append(clip)
        total += dur

    logger.info(
        "clip_planner: %d clips → %d after processing (%.1fs total)",
        len(raw_clips), len(final), total,
    )
    return final
