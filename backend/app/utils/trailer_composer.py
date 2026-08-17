"""
TrailerComposer — MoviePy Composition Layer

Architecture position:

    AI/CV
      ↓
    TrailerEditingPlan          (serialisable Pydantic schema — no MoviePy objects)
      ↓
    TrailerComposer             ← THIS FILE
      ↓
    MoviePy high-level composition
      ↓
    FFmpeg final processing     (encoding, muxing, loudnorm, EQ, subtitles)
      ↓
    output.mp4

Responsibilities (MoviePy owns):
    - Open source video handles (reused per unique source path)
    - Extract subclips (trimming / time-range selection)
    - Apply per-clip effects: FadeIn, FadeOut
    - Timeline placement with with_start()
    - Transitions: cut, fade, crossfade (declarative config)
    - Concatenate / composite the timeline
    - Audio timeline: dialogue + music + SFX layers via CompositeAudioClip
    - Write a single intermediate file for FFmpeg to encode

Responsibilities (FFmpeg retains):
    - Final codec selection and encoding (libx264 / h264_nvenc)
    - Muxing
    - Two-pass loudnorm
    - EQ (bass boost / treble cut)
    - Hardware encoding
    - Subtitle burn-in (FFmpeg subtitles filter)
    - Audio fade-out on final output

NOT in TrailerComposer (AI/CV layer):
    - Sentiment analysis
    - Topic analysis
    - Scene detection
    - Whisper transcription
    - Beat detection
    - Clip scoring
    - Creative prompt interpretation

Memory contract:
    - Source VideoFileClip handles are opened once per unique source path
      and reused for all subclips from that source.
    - All handles are closed in the finally block on success AND failure.
    - No entire raw footage is loaded into memory — subclipped() is lazy.
    - No intermediate rendered video per clip — one composition, one write.

MoviePy version: 2.x only.
    Uses: subclipped(), with_start(), with_effects(), with_duration(),
          CompositeVideoClip, concatenate_videoclips, CompositeAudioClip,
          CrossFadeIn, FadeIn, FadeOut, AudioFadeIn, AudioFadeOut.
    Does NOT use: moviepy.editor, set_start(), set_duration(), set_audio().
"""

from __future__ import annotations

import logging
import os
import time
import tracemalloc
from dataclasses import dataclass, field
from typing import Optional

from app.schemas.feedback import TrailerEditingPlan, TrailerClip

logger = logging.getLogger(__name__)

# Default crossfade duration — matches the existing CROSSFADE_DURATION constant
# in ffmpeg_composer so behaviour is identical after migration.
DEFAULT_CROSSFADE_DURATION = 1.0   # seconds

# Supported transition types
TRANSITION_CUT       = "cut"
TRANSITION_FADE      = "fade"
TRANSITION_CROSSFADE = "crossfade"
_VALID_TRANSITIONS   = {TRANSITION_CUT, TRANSITION_FADE, TRANSITION_CROSSFADE}


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class ComposeResult:
    """
    Returned by TrailerComposer.compose().

    success:
        True when the intermediate file was written successfully.

    output_path:
        Absolute path to the intermediate .mp4 written by MoviePy.
        Only valid when success=True.
        This file is the input to the FFmpeg final-encoding pass.

    clip_timeline_offsets:
        Per-clip start positions (seconds) on the composed timeline.
        Used by map_transcript_to_timeline() for subtitle timestamp mapping.

    clip_durations:
        Actual duration (seconds) of each composed clip after trimming.
        Parallel to clip_timeline_offsets.

    surviving_clips:
        TrailerClip objects that were successfully composed.
        Clips that failed to open/extract are excluded.

    error:
        Non-empty string when success=False.

    composition_duration_secs:
        Wall-clock time spent in MoviePy composition (excludes FFmpeg).

    peak_memory_mb:
        Peak RSS memory increase during composition (MB).
        0.0 when tracemalloc is unavailable.
    """
    success:                  bool
    output_path:              str                  = ""
    clip_timeline_offsets:    list[float]          = field(default_factory=list)
    clip_durations:           list[float]          = field(default_factory=list)
    surviving_clips:          list[TrailerClip]    = field(default_factory=list)
    error:                    str                  = ""
    composition_duration_secs: float              = 0.0
    peak_memory_mb:           float               = 0.0


# ── Transition config ─────────────────────────────────────────────────────────

@dataclass
class TransitionConfig:
    """
    Declarative transition specification.

    type:     "cut" | "fade" | "crossfade"
    duration: overlap/fade duration in seconds (ignored for "cut")

    Example:
        TransitionConfig(type="crossfade", duration=0.4)
        TransitionConfig(type="fade",      duration=0.5)
        TransitionConfig(type="cut")
    """
    type:     str   = TRANSITION_CROSSFADE
    duration: float = DEFAULT_CROSSFADE_DURATION

    def __post_init__(self) -> None:
        if self.type not in _VALID_TRANSITIONS:
            raise ValueError(
                f"TransitionConfig.type must be one of {sorted(_VALID_TRANSITIONS)}, "
                f"got {self.type!r}"
            )
        if self.duration < 0:
            raise ValueError(f"TransitionConfig.duration must be >= 0, got {self.duration}")


# ── TrailerComposer ───────────────────────────────────────────────────────────

class TrailerComposer:
    """
    Consumes a TrailerEditingPlan and produces a single intermediate video
    file via MoviePy composition.

    TrailerEditingPlan is a serialisable Pydantic schema — it contains no
    MoviePy objects. TrailerComposer is the only layer that touches MoviePy.

    Usage:
        composer = TrailerComposer(source_path="/path/to/raw.mp4")
        result   = composer.compose(plan, output_path="/tmp/intermediate.mp4")
        if result.success:
            # hand result.output_path to FFmpeg for final encoding
            ...

    The source_path is the local file path to the raw footage.
    MoviePy never accesses S3 — the storage layer handles S3 ↔ local copies.
    """

    def __init__(
        self,
        source_path: str,
        transition: Optional[TransitionConfig] = None,
    ) -> None:
        """
        source_path:
            Absolute local path to the source video file.

        transition:
            Declarative transition config applied between all clips.
            Defaults to crossfade with DEFAULT_CROSSFADE_DURATION.
        """
        self._source_path = os.path.normpath(os.path.abspath(source_path))
        self._transition  = transition or TransitionConfig()

    # ── Public API ────────────────────────────────────────────────────────────

    def compose(
        self,
        plan: TrailerEditingPlan,
        output_path: str,
        music_path:  Optional[str] = None,
        sfx_paths:   Optional[list[str]] = None,
    ) -> ComposeResult:
        """
        Compose the trailer from plan and write an intermediate file.

        plan:
            TrailerEditingPlan — serialisable, no MoviePy objects.

        output_path:
            Where to write the intermediate .mp4.
            This is the input to the FFmpeg final-encoding pass.

        music_path:
            Optional local path to a background music file.
            Mixed into the audio timeline at reduced volume (-12 dB relative).

        sfx_paths:
            Optional list of (path, start_time) tuples for SFX placement.
            Not yet implemented — reserved for future extension.

        Returns ComposeResult.
        """
        if not plan.clips:
            return ComposeResult(success=False, error="TrailerEditingPlan has no clips.")

        tracemalloc.start()
        t_start = time.perf_counter()

        # All MoviePy handles collected here for guaranteed cleanup
        _open_sources: dict[str, object] = {}   # source_path → VideoFileClip
        _mv_clips:     list[object]       = []   # subclipped VideoFileClip objects
        _audio_clips:  list[object]       = []   # AudioFileClip objects
        _composite:    object | None      = None

        try:
            result = self._compose_inner(
                plan, output_path, music_path,
                _open_sources, _mv_clips, _audio_clips,
            )
            _composite = None   # write_videofile already closed it internally
        except Exception as exc:
            logger.error("TrailerComposer.compose: unhandled exception — %s", exc)
            result = ComposeResult(success=False, error=str(exc))
        finally:
            self._close_all(_mv_clips, _audio_clips, _open_sources)

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result.composition_duration_secs = round(time.perf_counter() - t_start, 3)
        result.peak_memory_mb            = round(peak / 1_048_576, 2)
        return result

    # ── Internal composition ──────────────────────────────────────────────────

    def _compose_inner(
        self,
        plan:          TrailerEditingPlan,
        output_path:   str,
        music_path:    Optional[str],
        _open_sources: dict,
        _mv_clips:     list,
        _audio_clips:  list,
    ) -> ComposeResult:
        from moviepy import (
            VideoFileClip, CompositeVideoClip, CompositeAudioClip,
            concatenate_videoclips,
        )
        from moviepy.video.fx import CrossFadeIn, FadeIn, FadeOut
        from moviepy.audio.fx import AudioFadeIn, AudioFadeOut

        surviving_clips:       list[TrailerClip] = []
        clip_timeline_offsets: list[float]       = []
        clip_durations:        list[float]       = []
        positioned:            list              = []

        # ── Step 1: Open source, extract subclips, apply per-clip effects ────
        src = self._get_source(self._source_path, _open_sources)
        if src is None:
            return ComposeResult(
                success=False,
                error=f"Cannot open source video: {self._source_path}",
            )

        timeline_pos = 0.0
        t = self._transition

        for i, clip in enumerate(plan.clips):
            start = float(clip.start_time)
            end   = float(clip.end_time)

            if end <= start:
                logger.warning(
                    "TrailerComposer: clip %d has end <= start (%.3f <= %.3f) — skipped",
                    i, end, start,
                )
                continue

            # Clamp to source duration
            src_dur = src.duration or 0.0
            if src_dur > 0:
                start = max(0.0, min(start, src_dur))
                end   = max(start, min(end, src_dur))
                if end - start < 0.1:
                    logger.warning(
                        "TrailerComposer: clip %d too short after clamping (%.3fs) — skipped",
                        i, end - start,
                    )
                    continue

            try:
                sub = src.subclipped(start, end)
                _mv_clips.append(sub)
            except Exception as exc:
                logger.warning(
                    "TrailerComposer: clip %d (%.1f–%.1f) subclip failed — %s — skipped",
                    i, start, end, exc,
                )
                continue

            clip_dur = sub.duration

            # ── Step 2: Apply transition effects and place on timeline ────────
            if t.type == TRANSITION_CUT:
                placed = sub.with_start(timeline_pos)
                clip_timeline_offsets.append(timeline_pos)
                clip_durations.append(clip_dur)
                timeline_pos += clip_dur

            elif t.type == TRANSITION_FADE:
                fade_d = min(t.duration, clip_dur / 2)
                effects = []
                if i > 0:
                    effects.append(FadeIn(fade_d))
                if i == len(plan.clips) - 1:
                    effects.append(FadeOut(fade_d))
                sub_fx = sub.with_effects(effects) if effects else sub
                placed = sub_fx.with_start(timeline_pos)
                clip_timeline_offsets.append(timeline_pos)
                clip_durations.append(clip_dur)
                timeline_pos += clip_dur

            else:  # crossfade (default)
                xfade_d = min(t.duration, clip_dur / 2)
                if i == 0:
                    placed = sub.with_start(0.0)
                    clip_timeline_offsets.append(0.0)
                    clip_durations.append(clip_dur)
                    timeline_pos = clip_dur
                else:
                    tl_start = timeline_pos - xfade_d
                    placed = (
                        sub
                        .with_effects([CrossFadeIn(xfade_d)])
                        .with_start(tl_start)
                    )
                    clip_timeline_offsets.append(tl_start)
                    clip_durations.append(clip_dur)
                    timeline_pos = tl_start + clip_dur

            positioned.append(placed)
            surviving_clips.append(clip)

        if not positioned:
            return ComposeResult(
                success=False,
                error="All clips failed to extract — nothing to compose.",
            )

        # ── Step 3: Build video composite ────────────────────────────────────
        if len(positioned) == 1:
            final_video = positioned[0]
        else:
            final_video = CompositeVideoClip(positioned)

        # ── Step 4: Audio timeline composition ───────────────────────────────
        # Dialogue audio is already embedded in the video subclips.
        # If music_path is provided, mix it in at reduced volume.
        if music_path and os.path.isfile(music_path):
            try:
                from moviepy import AudioFileClip
                music = AudioFileClip(music_path)
                _audio_clips.append(music)

                # Trim or loop music to match video duration
                vid_dur = final_video.duration
                if music.duration < vid_dur:
                    # Loop by repeating — simple approach without concatenate overhead
                    import math
                    repeats = math.ceil(vid_dur / music.duration)
                    from moviepy import concatenate_audioclips
                    music = concatenate_audioclips([music] * repeats)
                    _audio_clips.append(music)

                music = music.subclipped(0, vid_dur).with_volume_scaled(0.25)
                _audio_clips.append(music)

                # Composite: dialogue (from video) + music
                dialogue_audio = final_video.audio
                if dialogue_audio is not None:
                    mixed = CompositeAudioClip([
                        dialogue_audio,
                        music.with_start(0),
                    ])
                    final_video = final_video.with_audio(mixed)
                else:
                    final_video = final_video.with_audio(music.with_start(0))

                logger.info("TrailerComposer: music mixed in from %s", music_path)
            except Exception as exc:
                logger.warning("TrailerComposer: music mixing failed (%s) — continuing without music", exc)

        # ── Step 5: Write intermediate file ──────────────────────────────────
        # Use libx264 fast preset — FFmpeg will re-encode in the final pass.
        # logger=None suppresses MoviePy's progress bar (we have our own SSE).
        try:
            final_video.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                fps=30,
                preset="fast",
                logger=None,
            )
        except Exception as exc:
            return ComposeResult(
                success=False,
                error=f"MoviePy write_videofile failed: {exc}",
            )

        logger.info(
            "TrailerComposer: composed %d clips → %s (%.1fs timeline)",
            len(surviving_clips), output_path, timeline_pos,
        )

        return ComposeResult(
            success=True,
            output_path=output_path,
            clip_timeline_offsets=clip_timeline_offsets,
            clip_durations=clip_durations,
            surviving_clips=surviving_clips,
        )

    # ── Source handle management ──────────────────────────────────────────────

    def _get_source(self, path: str, cache: dict) -> object | None:
        """
        Return a cached VideoFileClip for path, opening it on first access.
        Reuses the same handle for all subclips from the same source file,
        avoiding redundant file opens and reducing memory overhead.
        """
        if path in cache:
            return cache[path]
        try:
            from moviepy import VideoFileClip
            clip = VideoFileClip(path)
            cache[path] = clip
            logger.debug("TrailerComposer: opened source %s (%.1fs)", path, clip.duration or 0)
            return clip
        except Exception as exc:
            logger.error("TrailerComposer: cannot open %s — %s", path, exc)
            return None

    # ── Resource cleanup ──────────────────────────────────────────────────────

    @staticmethod
    def _close_all(
        mv_clips:     list,
        audio_clips:  list,
        open_sources: dict,
    ) -> None:
        """
        Close all MoviePy handles unconditionally.
        Called in the finally block — runs on success AND failure.
        """
        for obj in mv_clips:
            try:
                obj.close()
            except Exception:
                pass
        for obj in audio_clips:
            try:
                obj.close()
            except Exception:
                pass
        for obj in open_sources.values():
            try:
                obj.close()
            except Exception:
                pass
        mv_clips.clear()
        audio_clips.clear()
        open_sources.clear()
