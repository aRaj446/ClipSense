/**
 * SenseScrub Engine Types
 *
 * Bridge types that map SenseScrub's domain model (EditorClip[], flat timeline)
 * to OpenReel's engine model (Project, Timeline, Track, Clip).
 */

export interface EngineConfig {
  /** Target canvas width for rendering */
  width: number
  /** Target canvas height for rendering */
  height: number
  /** Target frame rate for playback */
  frameRate: number
  /** Whether to enable audio playback during preview */
  enableAudio: boolean
}

export const DEFAULT_ENGINE_CONFIG: EngineConfig = {
  width: 1920,
  height: 1080,
  frameRate: 30,
  enableAudio: true,
}

export type EngineStatus =
  | 'idle'
  | 'initializing'
  | 'loading-media'
  | 'ready'
  | 'error'

export type PlaybackState = 'stopped' | 'playing' | 'paused'

export interface EngineError {
  code: 'INIT_FAILED' | 'MEDIA_LOAD_FAILED' | 'WEBCODECS_UNSUPPORTED' | 'DECODE_ERROR' | 'UNKNOWN'
  message: string
  recoverable: boolean
}

/** Progress info for media loading */
export interface MediaLoadProgress {
  loaded: number
  total: number
  percent: number
}
