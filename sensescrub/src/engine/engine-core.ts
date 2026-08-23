/**
 * SenseScrub Engine Core
 *
 * Singleton wrapper around OpenReel's VideoEngine, AudioEngine, and PlaybackController.
 * Provides a simplified initialization and status API for SenseScrub.
 *
 * The engine is lazily initialized — call initializeEngine() once when the editor
 * mounts, then use getEngine() to access the instance.
 */

import type { EngineConfig, EngineStatus, EngineError } from './types'
import { DEFAULT_ENGINE_CONFIG } from './types'

// ── OpenReel Core Imports ─────────────────────────────────────────────────────
// These come from the local @openreel/core package source.
// VideoEngine handles WebCodecs frame decoding + canvas compositing.
// AudioEngine handles offline audio rendering.
// PlaybackController orchestrates the real-time playback loop.
// MasterTimelineClock provides AudioContext-based frame-accurate timing.

import {
  VideoEngine,
  AudioEngine,
  PlaybackController,
  getVideoEngine,
  getAudioEngine,
  getPlaybackController,
  initializeMasterClock,
  initializeRealtimeAudioGraph,
  getMasterClock,
  getRealtimeAudioGraph,
} from '@openreel/core'

// ── Engine Singleton ──────────────────────────────────────────────────────────

export class SenseScrubEngine {
  private _status: EngineStatus = 'idle'
  private _error: EngineError | null = null
  private _config: EngineConfig

  // OpenReel engine instances
  private _videoEngine: VideoEngine | null = null
  private _audioEngine: AudioEngine | null = null
  private _playbackController: PlaybackController | null = null

  // Feature detection
  private _webCodecsSupported: boolean = false
  private _webGPUSupported: boolean = false

  constructor(config: Partial<EngineConfig> = {}) {
    this._config = { ...DEFAULT_ENGINE_CONFIG, ...config }
    this._detectCapabilities()
  }

  // ── Public API ────────────────────────────────────────────────────────────

  get status(): EngineStatus { return this._status }
  get error(): EngineError | null { return this._error }
  get config(): EngineConfig { return this._config }
  get webCodecsSupported(): boolean { return this._webCodecsSupported }
  get webGPUSupported(): boolean { return this._webGPUSupported }

  get videoEngine(): VideoEngine | null { return this._videoEngine }
  get audioEngine(): AudioEngine | null { return this._audioEngine }
  get playbackController(): PlaybackController | null { return this._playbackController }

  /**
   * Initialize all engine subsystems.
   * Call once when the editor component mounts.
   */
  async initialize(): Promise<void> {
    if (this._status === 'ready' || this._status === 'initializing') return

    this._status = 'initializing'
    this._error = null

    try {
      // 1. Check for WebCodecs support (required for frame decoding)
      if (!this._webCodecsSupported) {
        console.warn('[SenseScrubEngine] WebCodecs not supported — falling back to video element preview')
        this._error = {
          code: 'WEBCODECS_UNSUPPORTED',
          message: 'Your browser does not support WebCodecs. Using fallback preview mode.',
          recoverable: true,
        }
        // We still mark as "ready" because the fallback (old <video> preview) will be used
        this._status = 'ready'
        return
      }

      // 2. Initialize MasterTimelineClock with configured frame rate
      initializeMasterClock({ frameRate: this._config.frameRate })

      // 3. Get/create singleton engine instances
      this._videoEngine = getVideoEngine()
      this._audioEngine = getAudioEngine()
      this._playbackController = getPlaybackController()

      // 4. Initialize VideoEngine (loads mediabunny wasm, sets up decoders)
      await this._videoEngine.initialize()
      console.log('[SenseScrubEngine] VideoEngine initialized')

      // 5. Initialize AudioEngine
      await this._audioEngine.initialize()
      console.log('[SenseScrubEngine] AudioEngine initialized')

      // 6. Initialize PlaybackController (wires clock → video + audio)
      await this._playbackController.initialize(this._videoEngine, this._audioEngine)
      console.log('[SenseScrubEngine] PlaybackController initialized')

      // 7. Initialize RealtimeAudioGraph for preview audio
      initializeRealtimeAudioGraph(getMasterClock())
      console.log('[SenseScrubEngine] RealtimeAudioGraph initialized')

      this._status = 'ready'
      console.log('[SenseScrubEngine] All subsystems ready ✓')

    } catch (err) {
      const message = err instanceof Error ? err.message : String(err)
      console.error('[SenseScrubEngine] Initialization failed:', message)
      this._error = {
        code: 'INIT_FAILED',
        message: `Engine initialization failed: ${message}`,
        recoverable: false,
      }
      this._status = 'error'
    }
  }

  /**
   * Dispose all engine resources. Call on unmount.
   */
  dispose(): void {
    try {
      this._playbackController?.dispose()
      this._videoEngine?.dispose()
      this._audioEngine?.dispose()
    } catch (err) {
      console.warn('[SenseScrubEngine] Dispose error:', err)
    }

    this._videoEngine = null
    this._audioEngine = null
    this._playbackController = null
    this._status = 'idle'
    this._error = null
  }

  // ── Private ───────────────────────────────────────────────────────────────

  private _detectCapabilities(): void {
    // WebCodecs: required for frame-by-frame decoding
    this._webCodecsSupported = (
      typeof VideoDecoder !== 'undefined' &&
      typeof VideoEncoder !== 'undefined' &&
      typeof AudioDecoder !== 'undefined'
    )

    // WebGPU: optional, enables GPU-accelerated compositing
    this._webGPUSupported = 'gpu' in navigator

    console.log('[SenseScrubEngine] Capabilities:', {
      webCodecs: this._webCodecsSupported,
      webGPU: this._webGPUSupported,
    })
  }
}

// ── Module-level singleton ──────────────────────────────────────────────────

let _instance: SenseScrubEngine | null = null

/**
 * Get the engine singleton. Throws if not initialized.
 */
export function getEngine(): SenseScrubEngine {
  if (!_instance) {
    throw new Error('[SenseScrubEngine] Engine not initialized. Call initializeEngine() first.')
  }
  return _instance
}

/**
 * Initialize the engine singleton with optional config overrides.
 */
export async function initializeEngine(config: Partial<EngineConfig> = {}): Promise<SenseScrubEngine> {
  if (_instance && _instance.status === 'ready') {
    return _instance
  }

  _instance = new SenseScrubEngine(config)
  await _instance.initialize()
  return _instance
}

/**
 * Dispose the engine singleton and release all resources.
 */
export function disposeEngine(): void {
  if (_instance) {
    _instance.dispose()
    _instance = null
  }
}
