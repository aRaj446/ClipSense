/**
 * CanvasPreview — OpenReel-powered video preview on <canvas>
 *
 * Replaces the old <video> element approach with frame-accurate rendering.
 * The PlaybackController drives frame rendering via VideoEngine.renderFrame()
 * and paints each decoded frame to this canvas.
 *
 * Features:
 *   - Real-time preview of the assembled clip sequence
 *   - Frame-accurate seeking (no HTML5 video seeking inaccuracy)
 *   - Instant visual feedback on clip edits (trim, reorder, delete)
 *   - Synchronized audio via RealtimeAudioGraph
 *   - Aspect-ratio-correct display with letterboxing
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { Film, AlertTriangle, Loader2 } from 'lucide-react'
import type { Project } from '@openreel/core'
import type { EditorClip } from '../types'
import { usePlayback } from '../engine/playback-bridge'
import { totalDuration } from '../utils/timeline'
import PlaybackControls from './PlaybackControls'

interface Props {
  /** The OpenReel Project (rebuilt when clips change) */
  project: Project | null
  /** The current clip list (for duration/control display) */
  clips: EditorClip[]
  /** Seek to this assembled time (set by timeline/inspector clicks) */
  seekTarget?: number | null
  /** Reports assembled trailer time upward (for timeline sync) */
  onCurrentTime?: (t: number) => void
  /** Parent can store a ref to the play/pause handler for keyboard shortcuts */
  onPlayPauseRef?: React.MutableRefObject<(() => void) | null>
  /** Whether the engine is still loading media */
  loading?: boolean
  /** Loading progress percent (0-100) */
  loadProgress?: number
  /** Error message if engine initialization failed */
  engineError?: string | null
}

export default function CanvasPreview({
  project,
  clips,
  seekTarget,
  onCurrentTime,
  onPlayPauseRef,
  loading = false,
  loadProgress = 0,
  engineError = null,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ width: 1920, height: 1080 })

  // Connect to the PlaybackController
  const { info, controls } = usePlayback(project, canvasRef)

  const liveAssembledDuration = totalDuration(clips)

  // ── Report time changes upward ──────────────────────────────────────────
  useEffect(() => {
    onCurrentTime?.(info.currentTime)
  }, [info.currentTime, onCurrentTime])

  // ── Handle external seek targets ────────────────────────────────────────
  const prevSeekTarget = useRef<number | null | undefined>(undefined)
  useEffect(() => {
    if (seekTarget == null) return
    if (seekTarget === prevSeekTarget.current) return
    prevSeekTarget.current = seekTarget

    controls.seek(seekTarget)
  }, [seekTarget, controls])

  // ── Expose play/pause to parent for keyboard shortcuts ──────────────────
  const handlePlayPause = useCallback(async () => {
    await controls.togglePlayback()
  }, [controls])

  useEffect(() => {
    if (onPlayPauseRef) onPlayPauseRef.current = handlePlayPause
    return () => { if (onPlayPauseRef) onPlayPauseRef.current = null }
  })

  // ── Responsive canvas sizing ────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        if (width > 0 && height > 0) {
          // Maintain 16:9 aspect ratio within container
          const aspectRatio = 16 / 9
          let canvasW = width
          let canvasH = width / aspectRatio
          if (canvasH > height) {
            canvasH = height
            canvasW = height * aspectRatio
          }
          setCanvasSize({
            width: Math.round(canvasW),
            height: Math.round(canvasH),
          })
        }
      }
    })

    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // ── Scrubber seek ───────────────────────────────────────────────────────
  const handleSeek = useCallback((assembledTime: number) => {
    controls.seek(assembledTime)
  }, [controls])

  // ── Volume control (placeholder — will wire to RealtimeAudioGraph) ──────
  const [volume, setVolume] = useState(1)
  const [muted, setMuted] = useState(false)

  const handleVolume = useCallback((val: number) => {
    setVolume(val)
    setMuted(val === 0)
    // TODO: wire to realtimeAudioGraph.setMasterVolume(val)
  }, [])

  const handleMute = useCallback(() => {
    setMuted(prev => !prev)
    // TODO: wire to realtimeAudioGraph.setPreviewMuted(!muted)
  }, [])

  // ── Render ──────────────────────────────────────────────────────────────

  // Loading state
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-black text-white gap-3">
        <Loader2 size={24} className="animate-spin text-primary" />
        <div className="text-xs text-slate-400">
          Loading footage{loadProgress > 0 ? ` (${loadProgress}%)` : '...'}
        </div>
        {loadProgress > 0 && (
          <div className="w-48 h-1 bg-slate-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${loadProgress}%` }}
            />
          </div>
        )}
      </div>
    )
  }

  // Error state
  if (engineError) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-black text-white gap-2">
        <AlertTriangle size={20} className="text-amber-400" />
        <p className="text-xs text-slate-400 max-w-xs text-center">{engineError}</p>
      </div>
    )
  }

  // No project yet
  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-black text-slate-600 gap-2">
        <Film size={24} />
        <p className="text-xs">Initializing preview engine...</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Canvas container — aspect-ratio-correct display */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0 flex items-center justify-center bg-black overflow-hidden"
      >
        <canvas
          ref={canvasRef}
          width={canvasSize.width}
          height={canvasSize.height}
          className="max-w-full max-h-full object-contain"
          style={{
            width: canvasSize.width,
            height: canvasSize.height,
            imageRendering: 'auto',
          }}
        />
      </div>

      {/* Playback controls */}
      <PlaybackControls
        playing={info.isPlaying}
        currentTime={info.currentTime}
        duration={liveAssembledDuration}
        volume={volume}
        muted={muted}
        mode="live"
        onPlayPause={handlePlayPause}
        onSeek={handleSeek}
        onVolume={handleVolume}
        onMuteToggle={handleMute}
        onFullscreen={() => {}}
      />
    </div>
  )
}
