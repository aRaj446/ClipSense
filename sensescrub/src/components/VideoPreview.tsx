import { useRef, useState, useCallback, useEffect } from 'react'
import { Film, AlertTriangle } from 'lucide-react'
import type { EditorClip } from '../types'
import { totalDuration, rawToAssembled, assembledToRaw } from '../utils/timeline'
import PlaybackControls from './PlaybackControls'

interface Props {
  src:              string | null       // rendered output URL
  rawSrc:           string | null       // raw footage URL for live preview
  clips:            EditorClip[]        // canonical clip list — reflects all edits immediately
  seekTarget?:      number | null       // raw footage timestamp to seek to
  onCurrentTime?:   (t: number) => void // reports assembled trailer time upward
  /** Parent can store a ref to the play/pause handler for keyboard shortcuts */
  onPlayPauseRef?:  React.MutableRefObject<(() => void) | null>
}

type PreviewMode = 'live' | 'rendered'

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Index of the clip whose raw range contains rawTime. -1 if none. */
function clipIndexAtRaw(rawTime: number, clips: EditorClip[]): number {
  return clips.findIndex(c => rawTime >= c.start_time && rawTime < c.end_time)
}

/** Index of the clip with the given id. -1 if not found. */
function clipIndexById(id: string, clips: EditorClip[]): number {
  return clips.findIndex(c => c.id === id)
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function VideoPreview({ src, rawSrc, clips, seekTarget, onCurrentTime, onPlayPauseRef }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const wrapRef  = useRef<HTMLDivElement>(null)

  const [mode,             setMode]             = useState<PreviewMode>(rawSrc ? 'live' : 'rendered')
  const [playing,          setPlaying]          = useState(false)
  const [assembledTime,    setAssembledTime]    = useState(0)
  const [renderedDuration, setRenderedDuration] = useState(0)
  const [volume,           setVolume]           = useState(1)
  const [muted,            setMuted]            = useState(false)
  const [error,            setError]            = useState(false)

  // ── Refs that must be current inside video event handlers ─────────────────
  // Always-fresh clips — avoids stale closures in timeupdate
  const clipsRef = useRef<EditorClip[]>(clips)

  // Track active clip by ID (not index) so reorder/delete don't corrupt position
  const activeClipIdRef = useRef<string | null>(clips[0]?.id ?? null)

  // Prevent re-entrant jumps during a seek
  const jumpingRef = useRef(false)

  // ── Sync clipsRef and recover position on every clips change ─────────────
  useEffect(() => {
    const prev  = clipsRef.current
    const next  = clips
    clipsRef.current = next

    const v = videoRef.current
    if (mode !== 'live' || !v) return

    const activeId = activeClipIdRef.current

    // Case 1: no clips — stop and reset
    if (next.length === 0) {
      v.pause()
      setPlaying(false)
      setAssembledTime(0)
      onCurrentTime?.(0)
      activeClipIdRef.current = null
      return
    }

    // Case 2: active clip still exists — re-validate bounds and order position
    if (activeId !== null) {
      const prevIdx = clipIndexById(activeId, prev)
      const nextIdx = clipIndexById(activeId, next)
      if (nextIdx >= 0) {
        const clip = next[nextIdx]
        const rawT = v.currentTime
        // Reorder: clip moved to a different position in the sequence.
        // The raw position may still be valid for this clip's source range,
        // but the assembled position is now wrong — seek to the clip's start
        // so playback resumes from the correct point in the new order.
        const wasReordered = prevIdx !== nextIdx
        // Trim: raw position now outside the (possibly trimmed) clip bounds.
        const isOutOfBounds = rawT < clip.start_time || rawT >= clip.end_time
        if (wasReordered || isOutOfBounds) {
          jumpingRef.current = true
          v.currentTime = clip.start_time
          const at = rawToAssembled(clip.start_time, next)
          setAssembledTime(at)
          onCurrentTime?.(at)
          setTimeout(() => { jumpingRef.current = false }, 200)
        }
        return
      }
    }

    // Case 3: active clip was deleted — find the nearest valid position
    // Use the last known assembled time to find the closest remaining clip
    const rawT = v.currentTime
    const assembled = rawToAssembled(rawT, prev.length ? prev : next)
    // Walk the new clip list to find which assembled position we're closest to
    let cursor = 0
    let bestIdx = 0
    let bestDist = Infinity
    for (let i = 0; i < next.length; i++) {
      const dur = next[i].end_time - next[i].start_time
      const clipMid = cursor + dur / 2
      const dist = Math.abs(assembled - clipMid)
      if (dist < bestDist) { bestDist = dist; bestIdx = i }
      cursor += dur
    }
    const target = next[bestIdx]
    activeClipIdRef.current = target.id
    jumpingRef.current = true
    v.currentTime = target.start_time
    const at = rawToAssembled(target.start_time, next)
    setAssembledTime(at)
    onCurrentTime?.(at)
    setTimeout(() => { jumpingRef.current = false }, 200)
  }, [clips]) // eslint-disable-line react-hooks/exhaustive-deps

  const activeSrc = mode === 'live' ? rawSrc : src

  const liveAssembledDuration = totalDuration(clips)
  const displayDuration = mode === 'live' ? liveAssembledDuration : renderedDuration

  // ── seekTarget: consume raw footage timestamp ─────────────────────────────
  const prevSeekTarget = useRef<number | null | undefined>(undefined)

  useEffect(() => {
    if (seekTarget == null) return
    if (seekTarget === prevSeekTarget.current) return
    prevSeekTarget.current = seekTarget

    const v = videoRef.current
    if (!v) return

    const liveClips = clipsRef.current

    if (mode === 'live') {
      // Find which clip this raw time belongs to
      let idx = clipIndexAtRaw(seekTarget, liveClips)
      // If not inside any clip, find the closest clip start
      if (idx < 0) {
        idx = liveClips.reduce((best, c, i) => {
          return Math.abs(c.start_time - seekTarget) < Math.abs(liveClips[best].start_time - seekTarget) ? i : best
        }, 0)
      }
      if (idx >= 0 && liveClips[idx]) {
        activeClipIdRef.current = liveClips[idx].id
        jumpingRef.current = true
        v.currentTime = seekTarget
        const at = rawToAssembled(seekTarget, liveClips)
        setAssembledTime(at)
        onCurrentTime?.(at)
        setTimeout(() => { jumpingRef.current = false }, 200)
      }
    } else {
      v.currentTime = seekTarget
      setAssembledTime(seekTarget)
      onCurrentTime?.(seekTarget)
    }
  }, [seekTarget, mode]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Reset on source/mode change ───────────────────────────────────────────
  useEffect(() => {
    setError(false)
    setPlaying(false)
    setAssembledTime(0)
    jumpingRef.current = false
    const firstClip = clipsRef.current[0]
    activeClipIdRef.current = firstClip?.id ?? null
    if (videoRef.current && mode === 'live' && firstClip) {
      videoRef.current.currentTime = firstClip.start_time
    }
  }, [activeSrc]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── timeupdate: advance playhead; jump to next clip at end_time ───────────
  const handleTimeUpdate = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    const rawT = v.currentTime

    if (mode === 'live') {
      const liveClips = clipsRef.current
      const at = rawToAssembled(rawT, liveClips)
      setAssembledTime(at)
      onCurrentTime?.(at)

      if (v.paused || jumpingRef.current) return

      // Find current clip by ID
      const activeId = activeClipIdRef.current
      const idx = activeId !== null ? clipIndexById(activeId, liveClips) : -1
      if (idx < 0) return

      const clip = liveClips[idx]
      if (rawT >= clip.end_time - 0.05) {
        const nextIdx = idx + 1
        if (nextIdx < liveClips.length) {
          // Advance to next clip
          jumpingRef.current = true
          activeClipIdRef.current = liveClips[nextIdx].id
          v.currentTime = liveClips[nextIdx].start_time
          setTimeout(() => { jumpingRef.current = false }, 200)
        } else {
          // End of trailer
          v.pause()
          setPlaying(false)
          const first = liveClips[0]
          activeClipIdRef.current = first?.id ?? null
          if (first) {
            v.currentTime = first.start_time
            setAssembledTime(0)
            onCurrentTime?.(0)
          }
        }
      }
    } else {
      setAssembledTime(rawT)
      onCurrentTime?.(rawT)
    }
  }, [mode, onCurrentTime])

  // ── Play/pause ────────────────────────────────────────────────────────────
  const handlePlayPause = useCallback(() => {
    const v = videoRef.current
    if (!v) return

    if (!v.paused) {
      v.pause()
      return
    }

    if (mode === 'live') {
      const liveClips = clipsRef.current
      if (!liveClips.length) return

      // Ensure we're positioned inside a valid clip
      const activeId = activeClipIdRef.current
      const idx = activeId !== null ? clipIndexById(activeId, liveClips) : -1
      const clip = idx >= 0 ? liveClips[idx] : liveClips[0]

      if (idx < 0 || v.currentTime < clip.start_time || v.currentTime >= clip.end_time) {
        activeClipIdRef.current = clip.id
        v.currentTime = clip.start_time
      }
    }
    v.play()
  }, [mode])

  // ── Expose play/pause to parent via ref (for keyboard shortcuts) ──────────
  useEffect(() => {
    if (onPlayPauseRef) onPlayPauseRef.current = handlePlayPause
    return () => { if (onPlayPauseRef) onPlayPauseRef.current = null }
  }) // runs every render so ref always points to latest handlePlayPause

  // ── Scrubber seek (assembled → raw) ──────────────────────────────────────
  const handleSeek = useCallback((assembledT: number) => {
    const v = videoRef.current
    if (!v) return

    if (mode === 'live') {
      const liveClips = clipsRef.current
      const rawT = assembledToRaw(assembledT, liveClips)
      const idx = clipIndexAtRaw(rawT, liveClips)
      if (idx >= 0) activeClipIdRef.current = liveClips[idx].id
      jumpingRef.current = true
      v.currentTime = rawT
      setAssembledTime(assembledT)
      onCurrentTime?.(assembledT)
      setTimeout(() => { jumpingRef.current = false }, 200)
    } else {
      v.currentTime = assembledT
      setAssembledTime(assembledT)
      onCurrentTime?.(assembledT)
    }
  }, [mode, onCurrentTime])

  const handleDurationChange = useCallback(() => {
    setRenderedDuration(videoRef.current?.duration ?? 0)
  }, [])

  const handleEnded  = useCallback(() => setPlaying(false), [])
  const handleError  = useCallback(() => { setError(true); setPlaying(false) }, [])
  const handlePlay   = useCallback(() => setPlaying(true),  [])
  const handlePause  = useCallback(() => setPlaying(false), [])

  const handleVolume = useCallback((val: number) => {
    const v = videoRef.current
    if (!v) return
    v.volume = val; v.muted = false
    setVolume(val); setMuted(false)
  }, [])

  const handleMuteToggle = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    v.muted = !v.muted
    setMuted(v.muted)
  }, [])

  const handleFullscreen = useCallback(() => {
    const el = wrapRef.current
    if (!el) return
    document.fullscreenElement ? document.exitFullscreen() : el.requestFullscreen?.()
  }, [])

  const switchMode = useCallback((m: PreviewMode) => {
    const v = videoRef.current
    if (v) v.pause()
    setPlaying(false)
    setAssembledTime(0)
    setMode(m)
    jumpingRef.current = false
    const firstClip = clipsRef.current[0]
    activeClipIdRef.current = firstClip?.id ?? null
  }, [])

  // ── Render ────────────────────────────────────────────────────────────────

  if (!activeSrc) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-surface-card gap-3">
        <Film size={36} className="text-slate-700" />
        <p className="text-slate-500 text-sm">No video available for this job</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-surface-card gap-3">
        <AlertTriangle size={36} className="text-accent-amber" />
        <p className="text-slate-400 text-sm">Video failed to load</p>
        <p className="text-slate-600 text-xs font-mono break-all max-w-xs text-center">{activeSrc}</p>
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="flex flex-col h-full bg-black overflow-hidden">

      <video
        ref={videoRef}
        src={activeSrc}
        className="w-full flex-1 min-h-0 object-contain bg-black"
        style={{ height: 0 }}
        preload="metadata"
        playsInline
        onTimeUpdate={handleTimeUpdate}
        onDurationChange={handleDurationChange}
        onEnded={handleEnded}
        onError={handleError}
        onPlay={handlePlay}
        onPause={handlePause}
        onDoubleClick={handleFullscreen}
      />

      <PlaybackControls
        playing={playing}
        currentTime={assembledTime}
        duration={displayDuration}
        volume={volume}
        muted={muted}
        mode={mode}
        canSwitchMode={!!(rawSrc && src)}
        onPlayPause={handlePlayPause}
        onSeek={handleSeek}
        onVolume={handleVolume}
        onMuteToggle={handleMuteToggle}
        onFullscreen={handleFullscreen}
        onSwitchMode={switchMode}
      />
    </div>
  )
}
