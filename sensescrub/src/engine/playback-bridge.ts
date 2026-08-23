/**
 * Playback Bridge — Connect OpenReel's PlaybackController to React state
 *
 * This module bridges the imperative PlaybackController (event-driven, runs on
 * requestAnimationFrame) with React's declarative state model.
 *
 * It provides:
 *   - A React hook (usePlayback) that exposes playback state + controls
 *   - Automatic project sync — when clips change, the controller's project is updated
 *   - Event forwarding — timeupdate/statechange/framerendered → React state
 *   - Canvas binding — connects the display canvas to the controller
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import type { Project } from '@openreel/core'
import { getPlaybackController, getMasterClock } from '@openreel/core'
import type { PlaybackState } from './types'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface PlaybackControls {
  play: () => Promise<void>
  pause: () => void
  stop: () => void
  togglePlayback: () => Promise<void>
  seek: (time: number) => Promise<void>
  setPlaybackRate: (rate: number) => void
}

export interface PlaybackInfo {
  /** Current assembled timeline position in seconds */
  currentTime: number
  /** Total timeline duration in seconds */
  duration: number
  /** Current playback state */
  state: PlaybackState
  /** Whether the engine is currently playing */
  isPlaying: boolean
  /** Current playback rate (1.0 = normal) */
  playbackRate: number
  /** Average frame render time in ms (perf indicator) */
  avgFrameRenderTime: number
  /** Number of dropped frames */
  droppedFrames: number
}

// ── Hook ──────────────────────────────────────────────────────────────────────

/**
 * React hook that provides playback state and controls.
 *
 * @param project - The current OpenReel Project (rebuilt when clips change)
 * @param canvasRef - Ref to the <canvas> element for frame rendering
 *
 * @example
 * ```tsx
 * const { info, controls } = usePlayback(project, canvasRef)
 * <button onClick={controls.togglePlayback}>
 *   {info.isPlaying ? 'Pause' : 'Play'}
 * </button>
 * ```
 */
export function usePlayback(
  project: Project | null,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
) {
  const [info, setInfo] = useState<PlaybackInfo>({
    currentTime: 0,
    duration: 0,
    state: 'stopped',
    isPlaying: false,
    playbackRate: 1,
    avgFrameRenderTime: 0,
    droppedFrames: 0,
  })

  // Track event listener cleanup
  const listenersRef = useRef<Array<() => void>>([])
  const projectRef = useRef<Project | null>(null)

  // ── Bind canvas to controller ───────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !project) return

    try {
      const controller = getPlaybackController()
      controller.setDisplayCanvas(canvas)
    } catch {
      // Controller not initialized yet — will retry when project changes
    }
  }, [canvasRef, project])

  // ── Sync project to controller ──────────────────────────────────────────
  useEffect(() => {
    if (!project) return
    projectRef.current = project

    try {
      const controller = getPlaybackController()
      controller.setProject(project)

      setInfo(prev => ({
        ...prev,
        duration: project.timeline.duration,
      }))
    } catch {
      // Controller not initialized yet
    }
  }, [project])

  // ── Subscribe to controller events ──────────────────────────────────────
  useEffect(() => {
    if (!project) return

    let controller: ReturnType<typeof getPlaybackController>
    try {
      controller = getPlaybackController()
    } catch {
      return
    }

    // Time update — fires on every frame during playback and on seek
    const onTimeUpdate = (event: { time: number }) => {
      setInfo(prev => ({
        ...prev,
        currentTime: event.time,
      }))
    }

    // State change — play/pause/stop
    const onStateChange = (event: { state: string }) => {
      const state = event.state as PlaybackState
      setInfo(prev => ({
        ...prev,
        state,
        isPlaying: state === 'playing',
      }))
    }

    // Frame rendered — perf tracking
    const onFrameRendered = () => {
      // Update perf stats periodically (not every frame — too expensive)
      // We'll update every 30 frames
    }

    controller.addEventListener('timeupdate', onTimeUpdate)
    controller.addEventListener('statechange', onStateChange)
    controller.addEventListener('framerendered', onFrameRendered)

    listenersRef.current = [
      () => controller.removeEventListener('timeupdate', onTimeUpdate),
      () => controller.removeEventListener('statechange', onStateChange),
      () => controller.removeEventListener('framerendered', onFrameRendered),
    ]

    return () => {
      listenersRef.current.forEach(unsub => unsub())
      listenersRef.current = []
    }
  }, [project])

  // ── Controls ────────────────────────────────────────────────────────────

  const play = useCallback(async () => {
    try {
      const controller = getPlaybackController()
      await controller.play()
    } catch (err) {
      console.error('[PlaybackBridge] Play failed:', err)
    }
  }, [])

  const pause = useCallback(() => {
    try {
      const controller = getPlaybackController()
      controller.pause()
    } catch (err) {
      console.error('[PlaybackBridge] Pause failed:', err)
    }
  }, [])

  const stop = useCallback(() => {
    try {
      const controller = getPlaybackController()
      controller.stop()
    } catch (err) {
      console.error('[PlaybackBridge] Stop failed:', err)
    }
  }, [])

  const togglePlayback = useCallback(async () => {
    try {
      const controller = getPlaybackController()
      await controller.togglePlayback()
    } catch (err) {
      console.error('[PlaybackBridge] Toggle failed:', err)
    }
  }, [])

  const seek = useCallback(async (time: number) => {
    try {
      const controller = getPlaybackController()
      await controller.seek(time)
    } catch (err) {
      console.error('[PlaybackBridge] Seek failed:', err)
    }
  }, [])

  const setPlaybackRate = useCallback((rate: number) => {
    try {
      const clock = getMasterClock()
      clock.setPlaybackRate(rate)
      setInfo(prev => ({ ...prev, playbackRate: rate }))
    } catch (err) {
      console.error('[PlaybackBridge] Set rate failed:', err)
    }
  }, [])

  const controls: PlaybackControls = {
    play,
    pause,
    stop,
    togglePlayback,
    seek,
    setPlaybackRate,
  }

  return { info, controls }
}
