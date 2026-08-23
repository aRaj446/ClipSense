/**
 * SenseScrub Engine Module
 *
 * Wraps OpenReel's core engine (@openreel/core) and exposes a simplified API
 * for SenseScrub's video editing workflow. This module handles:
 *
 * - Engine initialization (VideoEngine, AudioEngine, PlaybackController)
 * - Media loading (raw footage → blob → media library)
 * - Playback control (play/pause/seek driven by MasterTimelineClock)
 * - Project bridge (EditorClip[] → OpenReel Project)
 *
 * Usage:
 *   import { useEditorEngine } from './engine'
 *   const { project, ready, loading } = useEditorEngine(jobId, clips, rawUrl)
 */

export { type EngineConfig, type EngineStatus, type PlaybackState, type EngineError, type MediaLoadProgress, DEFAULT_ENGINE_CONFIG } from './types'
export { SenseScrubEngine, getEngine, initializeEngine, disposeEngine } from './engine-core'
export { useEngine, type UseEngineResult } from './useEngine'
export { useEditorEngine, type EditorEngineState } from './useEditorEngine'
export { usePlayback, type PlaybackControls, type PlaybackInfo } from './playback-bridge'
export { buildProject, rebuildProject, getClipAssembledStart, getClipAtAssembledTime, type ProjectBridgeOptions, type ProjectBridgeResult } from './project-bridge'
export { loadRawFootage, releaseMediaUrl, type MediaLoadResult, type ProgressCallback } from './media-loader'
