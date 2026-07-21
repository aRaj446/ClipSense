"""
Clip Planner Utility

Shared post-processing layer applied to every clip plan before FFmpeg execution.
Used by both VideoRegenerationAgent (Stage 3) and SmartTrailerAgent (Stage 4).

Responsibilities:
    1. Expand clip boundaries to cover the full dialogue window in the segment
    2. Snap end to nearest sentence boundary (±1.5s)
    3. Enforce minimum duration — dialogue clips: length of speech (floor 3s),
       non-dialogue clips: 3s hard floor
    4. Mood/energy classification — label each clip as 'action', 'emotional',
       'dialogue', or 'calm' using librosa RMS energy analysis
    5. Mood-group reordering — narrative arc: hook → build → resolve → wind-down
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MIN_CLIP_DURATION         = 3.0   # seconds — fallback minimum for non-dialogue clips
MIN_CLIP_DURATION_SPEECH  = 3.0   # seconds — absolute floor even for dialogue clips

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

def get_dialogue_window(
    start: float,
    end: float,
    transcript: dict,
) -> tuple[float | None, float | None]:
    """
    Return (dialogue_start, dialogue_end) for all transcript segments that
    overlap [start, end]. Returns (None, None) if no speech in this window.
    """
    segments = transcript.get("segments", [])
    overlapping = [
        seg for seg in segments
        if seg["start"] < end and seg["end"] > start
    ]
    if not overlapping:
        return None, None
    return overlapping[0]["start"], overlapping[-1]["end"]


def extend_to_full_dialogue(
    start: float,
    end: float,
    transcript: dict,
    video_duration: float,
) -> tuple[float, float]:
    """
    Expand start/end to cover only the transcript segments that overlap
    [start, end]. Does NOT chain into adjacent segments outside the window.
    """
    segments = transcript.get("segments", [])
    overlapping = [s for s in segments if s["start"] < end and s["end"] > start]
    if not overlapping:
        return start, end
    new_start = min(start, overlapping[0]["start"])
    new_end   = max(end,   overlapping[-1]["end"])
    return round(new_start, 3), round(min(new_end, video_duration), 3)


def extend_to_sentence_end(
    start: float,
    end: float,
    transcript: dict,
    video_duration: float,
    tolerance: float = 1.5,
) -> tuple[float, float]:
    """
    Extend clip end to the nearest sentence boundary within ±tolerance seconds.
    Never chains through multiple segments — only extends by at most tolerance seconds.
    """
    segments = transcript.get("segments", [])
    if not segments:
        return start, end

    adj_end   = end
    best_dist = float("inf")

    for seg in segments:
        if abs(seg["end"] - end) <= tolerance and abs(seg["end"] - end) < best_dist:
            best_dist = abs(seg["end"] - end)
            adj_end   = seg["end"]

    adj_end = min(video_duration, adj_end)
    return round(start, 3), round(adj_end, 3)


def get_transcript_text(start: float, end: float, transcript: dict) -> str:
    """Extract all transcript text that overlaps [start, end]."""
    segments = transcript.get("segments", [])
    parts = [
        seg["text"].strip()
        for seg in segments
        if seg["start"] < end + 0.5 and seg["end"] > start - 0.5
    ]
    return " ".join(parts).strip()


def dialogue_duration(start: float, end: float, transcript: dict) -> float:
    """Return total seconds of speech within [start, end]."""
    segments = transcript.get("segments", [])
    total = 0.0
    for seg in segments:
        seg_s = max(seg["start"], start)
        seg_e = min(seg["end"],   end)
        if seg_e > seg_s:
            total += seg_e - seg_s
    return round(total, 3)


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
    Classify a clip's mood group based on normalised energy [0,1] and transcript.
    Thresholds are adaptive (set by KMeans caller); this function uses pre-computed
    centroid boundaries passed as energy_max=boundary tuple when called from
    classify_clips_by_mood, or falls back to fixed ratios for standalone use.
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


def _kmeans_thresholds(energies: list[float]) -> tuple[float, float, float]:
    """
    Fit KMeans (k=4) on clip energies and return the three boundary values
    that separate the four mood groups (action / emotional / dialogue / calm).
    Falls back to fixed ratios if sklearn is unavailable or too few clips.
    Returns (high_thresh, mid_thresh, low_thresh) as fractions of energy_max.
    """
    if len(energies) < 4:
        return 0.70, 0.40, 0.15
    try:
        import numpy as np
        from sklearn.cluster import KMeans

        X = np.array(energies).reshape(-1, 1)
        km = KMeans(n_clusters=4, n_init=10, random_state=42)
        km.fit(X)
        centres = sorted(float(c[0]) for c in km.cluster_centers_)
        energy_max = max(energies)
        if energy_max <= 0:
            return 0.70, 0.40, 0.15
        # Boundaries are midpoints between adjacent sorted centroids
        b1 = (centres[2] + centres[3]) / 2 / energy_max   # action threshold
        b2 = (centres[1] + centres[2]) / 2 / energy_max   # emotional threshold
        b3 = (centres[0] + centres[1]) / 2 / energy_max   # dialogue threshold
        logger.debug("clip_planner: KMeans thresholds action=%.3f emotional=%.3f dialogue=%.3f", b1, b2, b3)
        return b1, b2, b3
    except Exception as exc:
        logger.warning("clip_planner: KMeans failed (%s) — using fixed thresholds", exc)
        return 0.70, 0.40, 0.15


def _classify_mood_adaptive(
    energy: float,
    energy_max: float,
    transcript_text: str,
    thresholds: tuple[float, float, float],
) -> str:
    """Classify mood using KMeans-derived adaptive thresholds."""
    if energy_max <= 0:
        return "calm"
    ratio = energy / energy_max
    has_speech = bool(transcript_text.strip())
    high, mid, low = thresholds
    if ratio > high:
        return "action"
    if ratio > mid:
        return "emotional" if has_speech else "action"
    if ratio > low:
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

        # Derive adaptive thresholds via KMeans on this video's energy distribution
        thresholds = _kmeans_thresholds(energies)

        for clip, energy in zip(clips, energies):
            clip.energy     = round(energy / energy_max if energy_max > 0 else 0.0, 3)
            clip.mood_group = _classify_mood_adaptive(energy, energy_max, clip.transcript_text, thresholds)

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
    Chronological sweep — used internally before mood classification.
    Sorts by start_time, keeps the longer clip when two overlap.
    """
    if len(clips) <= 1:
        return clips
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
            idx = overlapping[0]
            if (clip.end_time - clip.start_time) > (accepted[idx].end_time - accepted[idx].start_time):
                accepted[idx] = clip
    removed = len(clips) - len(accepted)
    if removed:
        logger.info("clip_planner: removed %d overlapping clip(s) (chronological pass)", removed)
    return accepted


def _remove_overlaps_preserve_order(clips: list[PlannedClip]) -> list[PlannedClip]:
    """
    Order-preserving sweep — used AFTER mood reordering.
    Iterates in narrative order; skips any clip whose time range overlaps
    an already-accepted clip. Keeps the first-seen (higher narrative priority).
    """
    if len(clips) <= 1:
        return clips
    accepted: list[PlannedClip] = []
    for clip in clips:
        overlaps = any(
            clip.start_time < a.end_time and clip.end_time > a.start_time
            for a in accepted
        )
        if not overlaps:
            accepted.append(clip)
        else:
            logger.debug(
                "clip_planner: dropping duplicate %.1f–%.1f (overlaps accepted clip)",
                clip.start_time, clip.end_time,
            )
    removed = len(clips) - len(accepted)
    if removed:
        logger.info("clip_planner: removed %d overlapping clip(s) (order-preserving pass)", removed)
    return accepted


# ── Mood-group reordering ──────────────────────────────────────────────────────

def reorder_by_mood(clips: list[PlannedClip]) -> list[PlannedClip]:
    """
    Arrange clips into a narrative arc: hook → build → peak → resolve → calm.
    Avoids back-to-back sentiment flips by grouping similar moods together
    while following a cinematic energy curve rather than a flat mood dump.

    Arc shape (by mood):
        1. Hook:    1 high-energy action clip (strong opener)
        2. Build:   remaining action clips interleaved with emotional
        3. Peak:    emotional clips
        4. Resolve: dialogue clips
        5. Wind-down: calm clips
    """
    if len(clips) <= 1:
        return clips

    groups: dict[str, list[PlannedClip]] = {g: [] for g in _MOOD_ORDER}
    for clip in clips:
        groups.setdefault(clip.mood_group, []).append(clip)

    # Sort each group by energy descending so highest-energy leads each section
    for g in groups:
        groups[g].sort(key=lambda c: c.energy, reverse=True)

    action    = groups["action"]
    emotional = groups["emotional"]
    dialogue  = groups["dialogue"]
    calm      = groups["calm"]

    reordered: list[PlannedClip] = []

    # 1. Hook — single strongest action clip
    if action:
        reordered.append(action[0])
        action = action[1:]

    # 2. Build — interleave remaining action with emotional for gradual escalation
    build = []
    a_iter = iter(action)
    e_iter = iter(emotional)
    a_done = e_done = False
    while not (a_done and e_done):
        if not a_done:
            c = next(a_iter, None)
            if c is None:
                a_done = True
            else:
                build.append(c)
        if not e_done:
            c = next(e_iter, None)
            if c is None:
                e_done = True
            else:
                build.append(c)
    reordered.extend(build)

    # 3. Resolve — dialogue
    reordered.extend(dialogue)

    # 4. Wind-down — calm
    reordered.extend(calm)

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
        1. Expand boundaries to cover overlapping dialogue segments only
        2. Snap end to nearest sentence boundary (±1.5s)
        3. Enforce minimum duration:
               dialogue clips  → length of the dialogue itself (min 3s)
               non-dialogue    → 3s hard floor
        4. Remove overlapping clips (chronological, keep longer)
        5. Classify mood via librosa energy (for transition selection only)
        6. Trim to target_duration

    Clips are kept in chronological order — reordering destroys A/V sync.
    Returns final list of PlannedClip objects ready for FFmpeg.
    """
    planned: list[PlannedClip] = []

    for raw in raw_clips:
        start = max(0.0, float(raw.get("start_time", 0.0)))
        end   = min(video_duration, float(raw.get("end_time", video_duration)))

        # Step 1: expand to cover the full dialogue in this window
        start, end = extend_to_full_dialogue(start, end, transcript, video_duration)

        # Step 2: also snap end to nearest sentence boundary
        start, end = extend_to_sentence_end(start, end, transcript, video_duration)

        # Step 3: determine minimum duration for this clip
        speech_dur = dialogue_duration(start, end, transcript)
        if speech_dur > 0:
            # Dialogue clip — minimum is the dialogue length itself, floor at 3s
            min_dur = max(MIN_CLIP_DURATION_SPEECH, speech_dur)
        else:
            # No dialogue — 3s minimum
            min_dur = MIN_CLIP_DURATION

        if end - start < min_dur:
            extended_end = min(video_duration, start + min_dur)
            # Try to snap the extended end to a sentence boundary too
            _, extended_end = extend_to_sentence_end(start, extended_end, transcript, video_duration)
            extended_end = max(start + min_dur, extended_end)
            if extended_end - start >= min_dur:
                end = min(video_duration, extended_end)
            else:
                extended_start = max(0.0, end - min_dur)
                if end - extended_start >= min_dur:
                    start = extended_start
                else:
                    logger.debug(
                        "clip_planner: dropping clip %.1f–%.1f (too short after extension, min=%.1fs)",
                        start, end, min_dur,
                    )
                    continue

        # Step 4: get transcript text for this clip
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

    # Step 5: remove overlapping clips — sort chronologically, keep longer
    planned = _remove_overlaps(planned)

    if not planned:
        return planned

    # Step 6: classify mood for transition selection (does NOT reorder)
    planned = classify_clips_by_mood(planned, video_path)

    # Step 7: trim to target_duration (skipped when inf passed)
    if target_duration == float("inf"):
        final = planned
        total = sum(c.end_time - c.start_time for c in final)
    else:
        final: list[PlannedClip] = []
        total = 0.0
        for clip in planned:
            dur = clip.end_time - clip.start_time
            if total + dur > target_duration + 5.0:
                break
            final.append(clip)
            total += dur
        # Trim last clip back only if it has no dialogue
        if final and total > target_duration:
            last = final[-1]
            last_speech = dialogue_duration(last.start_time, last.end_time, transcript)
            if last_speech == 0:
                trimmed_end = last.end_time - (total - target_duration)
                if trimmed_end - last.start_time >= MIN_CLIP_DURATION:
                    last.end_time = round(trimmed_end, 3)

    logger.info(
        "clip_planner: %d clips → %d after processing (%.1fs total)",
        len(raw_clips), len(final), total,
    )
    return final
