"""
Scene Detector Utility

Uses PySceneDetect (ContentDetector) to find shot boundaries in a video file.
Returns a list of scene dicts with start_time, end_time, duration (all in seconds)
and a formatted MM:SS timestamp for Gemini prompt injection.

Falls back to an empty list if scenedetect or opencv is unavailable, so the
rest of the pipeline degrades gracefully rather than crashing.
"""

import logging

logger = logging.getLogger(__name__)


def _seconds_to_mmss(seconds: float) -> str:
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"


def detect_scenes(video_path: str, threshold: float = 27.0, min_scene_len: float = 1.0) -> list[dict]:
    """
    Detect shot boundaries in a video file.

    Primary:  AdaptiveDetector — uses a rolling average of frame differences,
              adapts to the video's own motion baseline. Significantly fewer
              false positives on footage with camera movement, gradual lighting
              changes, or slow fades compared to a fixed threshold.
    Fallback: ContentDetector — used if AdaptiveDetector is unavailable
              (scenedetect < 0.6.1) or raises an exception.

    Args:
        video_path:    Absolute path to the video file.
        threshold:     ContentDetector fallback sensitivity (lower = more cuts).
        min_scene_len: Minimum scene length in seconds.

    Returns:
        List of dicts, each with:
          - scene_index:  int (0-based)
          - start_time:   float (seconds)
          - end_time:     float (seconds)
          - duration:     float (seconds)
          - timestamp:    str  (MM:SS of scene start)
    """
    try:
        import os
        video_path = os.path.normpath(video_path)
        from scenedetect import open_video, SceneManager

        video   = open_video(video_path)
        manager = SceneManager()

        # Try AdaptiveDetector first — better on real-world footage
        try:
            from scenedetect.detectors import AdaptiveDetector
            manager.add_detector(AdaptiveDetector(
                adaptive_threshold=3.0,   # 3× local baseline to trigger a cut
                window_width=3,           # 7-frame rolling window — more stable against flashes
                min_content_val=15.0,     # ignore near-static frames
                min_scene_len=min_scene_len,
                weights=AdaptiveDetector.Components(
                    delta_hue=1.0,
                    delta_sat=1.0,
                    delta_lum=1.0,
                    delta_edges=0.5,      # partial edge sensitivity catches structural cuts
                ),
            ))
            logger.debug("scene_detector: using AdaptiveDetector")
        except ImportError:
            from scenedetect.detectors import ContentDetector
            manager.add_detector(ContentDetector(threshold=threshold, min_scene_len=min_scene_len))
            logger.debug("scene_detector: AdaptiveDetector unavailable, using ContentDetector")

        manager.detect_scenes(video, show_progress=False, frame_skip=4)
        scene_list = manager.get_scene_list()

        scenes = []
        for i, (start, end) in enumerate(scene_list):
            start_s = start.get_seconds()
            end_s   = end.get_seconds()
            scenes.append({
                "scene_index": i,
                "start_time":  round(start_s, 2),
                "end_time":    round(end_s, 2),
                "duration":    round(end_s - start_s, 2),
                "timestamp":   _seconds_to_mmss(start_s),
            })

        logger.info("scene_detector: detected %d scenes in %s", len(scenes), video_path)
        return scenes

    except Exception as exc:
        logger.warning("scene_detector: failed for %s — %s", video_path, exc)
        return []
