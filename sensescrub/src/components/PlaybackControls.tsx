import { useRef, useCallback, useState } from 'react'
import { Play, Pause, Volume2, VolumeX, Maximize, Clapperboard, Video } from 'lucide-react'

export type PreviewMode = 'live' | 'rendered'

interface Props {
  playing:      boolean
  currentTime:  number
  duration:     number
  volume:       number        // 0–1
  muted:        boolean
  // Mode toggle — only shown when both rawSrc and src exist
  mode?:        PreviewMode
  canSwitchMode?: boolean
  onPlayPause:  () => void
  onSeek:       (t: number) => void
  onVolume:     (v: number) => void
  onMuteToggle: () => void
  onFullscreen: () => void
  onSwitchMode?: (m: PreviewMode) => void
}

function fmtTime(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00'
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function PlaybackControls({
  playing, currentTime, duration, volume, muted,
  mode, canSwitchMode,
  onPlayPause, onSeek, onVolume, onMuteToggle, onFullscreen, onSwitchMode,
}: Props) {
  const scrubberRef  = useRef<HTMLDivElement>(null)
  const volumeRef    = useRef<HTMLDivElement>(null)
  const [scrubbing,  setScrubbing]  = useState(false)
  const [hoverPct,   setHoverPct]   = useState<number | null>(null)
  const [volDragging, setVolDragging] = useState(false)

  const progress = duration > 0 ? Math.min(1, currentTime / duration) : 0

  // ── Scrubber helpers ──────────────────────────────────────────────────────
  function pctFromEvent(e: React.MouseEvent | React.PointerEvent, el: HTMLElement): number {
    const rect = el.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  }

  const handleScrubberPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setScrubbing(true)
    const pct = pctFromEvent(e, e.currentTarget)
    onSeek(pct * duration)
  }, [duration, onSeek])

  const handleScrubberPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    const pct = pctFromEvent(e, e.currentTarget)
    setHoverPct(pct)
    if (scrubbing) onSeek(pct * duration)
  }, [scrubbing, duration, onSeek])

  const handleScrubberPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (scrubbing) {
      const pct = pctFromEvent(e, e.currentTarget)
      onSeek(pct * duration)
    }
    setScrubbing(false)
  }, [scrubbing, duration, onSeek])

  const handleScrubberLeave = useCallback(() => {
    if (!scrubbing) setHoverPct(null)
  }, [scrubbing])

  // Arrow key seek is handled globally in EditorReady — scrubber just
  // prevents default to avoid page scroll when focused
  const handleScrubberKey = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') e.preventDefault()
  }, [])

  // ── Volume helpers ────────────────────────────────────────────────────────
  function volPctFromEvent(e: React.PointerEvent, el: HTMLElement): number {
    const rect = el.getBoundingClientRect()
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  }

  const handleVolPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId)
    setVolDragging(true)
    onVolume(volPctFromEvent(e, e.currentTarget))
  }, [onVolume])

  const handleVolPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (volDragging) onVolume(volPctFromEvent(e, e.currentTarget))
  }, [volDragging, onVolume])

  const handleVolPointerUp = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (volDragging) onVolume(volPctFromEvent(e, e.currentTarget))
    setVolDragging(false)
  }, [volDragging, onVolume])

  const displayVolume = muted ? 0 : volume
  const hoverTime     = hoverPct !== null ? hoverPct * duration : null

  return (
    <div
      className="flex flex-col select-none shrink-0"
      style={{ background: '#0D0D1A', borderTop: '1px solid #252538' }}
    >
      {/* ── Scrubber ── */}
      <div
        ref={scrubberRef}
        role="slider"
        aria-label="Seek"
        aria-valuemin={0}
        aria-valuemax={duration}
        aria-valuenow={currentTime}
        tabIndex={0}
        className="relative h-7 flex items-center px-0 cursor-pointer"
        onPointerDown={handleScrubberPointerDown}
        onPointerMove={handleScrubberPointerMove}
        onPointerUp={handleScrubberPointerUp}
        onPointerLeave={handleScrubberLeave}
        onKeyDown={handleScrubberKey}
      >
        {/* Track background */}
        <div
          className="absolute inset-x-0 rounded-none"
          style={{ top: '50%', transform: 'translateY(-50%)', height: scrubbing ? 5 : 3, background: '#252538', transition: 'height 0.1s' }}
        />

        {/* Filled portion */}
        <div
          className="absolute left-0 rounded-none"
          style={{
            top: '50%',
            transform: 'translateY(-50%)',
            height: scrubbing ? 5 : 3,
            width: `${progress * 100}%`,
            background: '#D4A843',
            transition: 'height 0.1s',
          }}
        />

        {/* Hover ghost */}
        {hoverPct !== null && !scrubbing && (
          <div
            className="absolute left-0 rounded-none pointer-events-none"
            style={{
              top: '50%',
              transform: 'translateY(-50%)',
              height: 3,
              width: `${hoverPct * 100}%`,
              background: '#D4A84355',
            }}
          />
        )}

        {/* Thumb */}
        <div
          className="absolute rounded-full pointer-events-none transition-transform"
          style={{
            left:      `${progress * 100}%`,
            top:       '50%',
            transform: `translate(-50%, -50%) scale(${scrubbing ? 1.4 : 1})`,
            width:     10,
            height:    10,
            background: '#D4A843',
            boxShadow:  scrubbing ? '0 0 0 3px #D4A84340' : '0 0 0 2px #0D0D1A',
            transition: 'transform 0.1s',
          }}
        />

        {/* Hover time tooltip */}
        {hoverTime !== null && (
          <div
            className="absolute bottom-full mb-1 pointer-events-none"
            style={{ left: `${(hoverPct ?? 0) * 100}%`, transform: 'translateX(-50%)' }}
          >
            <div
              className="px-1.5 py-0.5 rounded text-[9px] font-mono text-slate-200 whitespace-nowrap"
              style={{ background: '#1A1A2E', border: '1px solid #363654' }}
            >
              {fmtTime(hoverTime)}
            </div>
          </div>
        )}
      </div>

      {/* ── Controls row ── */}
      <div className="flex items-center gap-2 px-3 pb-2 pt-0.5">

        {/* Play / Pause */}
        <button
          onClick={onPlayPause}
          className="flex items-center justify-center w-7 h-7 rounded-full shrink-0 transition-colors"
          style={{ background: '#D4A843' }}
          aria-label={playing ? 'Pause' : 'Play'}
        >
          {playing
            ? <Pause size={12} style={{ color: '#0C0C14' }} />
            : <Play  size={12} style={{ color: '#0C0C14', marginLeft: 1 }} />
          }
        </button>

        {/* Time display */}
        <span className="text-[11px] font-mono tabular-nums shrink-0" style={{ color: '#6B6890' }}>
          <span style={{ color: '#C8C4D8' }}>{fmtTime(currentTime)}</span>
          <span className="mx-0.5">/</span>
          {fmtTime(duration)}
        </span>

        <div className="flex-1" />

        {/* Mode toggle — only when both sources available */}
        {canSwitchMode && mode && onSwitchMode && (
          <div
            className="flex items-center rounded-lg overflow-hidden shrink-0"
            style={{ border: '1px solid #252538', background: '#0E0E1A' }}
          >
            <button
              onClick={() => onSwitchMode('live')}
              title="Live preview — reflects current edits instantly"
              className={`flex items-center gap-1 px-2 py-1 text-[9px] font-medium transition-colors ${
                mode === 'live'
                  ? 'text-primary bg-primary/15'
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              <Clapperboard size={9} />
              Live
            </button>
            <div style={{ width: 1, background: '#252538', alignSelf: 'stretch' }} />
            <button
              onClick={() => onSwitchMode('rendered')}
              title="Rendered output — last exported MP4"
              className={`flex items-center gap-1 px-2 py-1 text-[9px] font-medium transition-colors ${
                mode === 'rendered'
                  ? 'text-accent-violet bg-accent-violet/15'
                  : 'text-slate-600 hover:text-slate-400'
              }`}
            >
              <Video size={9} />
              Rendered
            </button>
          </div>
        )}

        {/* Volume */}
        <button
          onClick={onMuteToggle}
          className="shrink-0 transition-colors"
          style={{ color: displayVolume === 0 ? '#5C5A72' : '#8B8AA0' }}
          aria-label={muted ? 'Unmute' : 'Mute'}
        >
          {displayVolume === 0
            ? <VolumeX size={13} />
            : <Volume2 size={13} />
          }
        </button>

        {/* Custom volume track */}
        <div
          ref={volumeRef}
          className="relative h-6 flex items-center cursor-pointer shrink-0"
          style={{ width: 64 }}
          onPointerDown={handleVolPointerDown}
          onPointerMove={handleVolPointerMove}
          onPointerUp={handleVolPointerUp}
          aria-label="Volume"
        >
          {/* Track */}
          <div
            className="absolute inset-x-0 rounded-full"
            style={{ height: 3, background: '#252538', top: '50%', transform: 'translateY(-50%)' }}
          />
          {/* Fill */}
          <div
            className="absolute left-0 rounded-full"
            style={{
              height: 3,
              width: `${displayVolume * 100}%`,
              background: '#8B8AA0',
              top: '50%',
              transform: 'translateY(-50%)',
            }}
          />
          {/* Thumb */}
          <div
            className="absolute rounded-full pointer-events-none"
            style={{
              left:      `${displayVolume * 100}%`,
              top:       '50%',
              transform: 'translate(-50%, -50%)',
              width:     8,
              height:    8,
              background: '#C8C4D8',
              boxShadow:  '0 0 0 2px #0D0D1A',
            }}
          />
        </div>

        {/* Fullscreen */}
        <button
          onClick={onFullscreen}
          className="shrink-0 transition-colors"
          style={{ color: '#5C5A72' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#8B8AA0')}
          onMouseLeave={e => (e.currentTarget.style.color = '#5C5A72')}
          aria-label="Fullscreen"
        >
          <Maximize size={13} />
        </button>

      </div>
    </div>
  )
}
