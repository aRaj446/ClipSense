import { useRef, useState, useCallback, useEffect } from 'react'
import type { EditorClip } from '../types'
import { computeTimelineOffsets, totalDuration, pixelToTime, assembledToRaw } from '../utils/timeline'
import TimelineClip from './TimelineClip'
import Playhead from './Playhead'
import InOutBar from './InOutBar'

const MIN_CLIP_DURATION = 0.5  // seconds

interface Props {
  clips: EditorClip[]
  currentTime: number
  selectedClipId: string | null
  activeClipIndex: number
  onSelectClip: (id: string | null) => void
  onSeek: (t: number) => void
  onDelete: (index: number) => void
  onReorder: (from: number, to: number) => void
  onTrim: (index: number, newStart: number, newEnd: number) => void
  onMute: (index: number) => void
  onTrimFirst: (newStart: number) => void
  onTrimLast:  (newEnd: number)   => void
}

interface TrimState {
  index: number
  handle: 'left' | 'right'
  startX: number
  origStart: number
  origEnd: number
  maxEnd: number
  previewStart: number
  previewEnd: number
  /** Pixel position of the active handle for tooltip placement */
  handlePct: number
}

function fmtTime(s: number): string {
  if (s < 60) {
    const sec = Math.floor(s)
    const ms  = Math.round((s - sec) * 10)
    return `${sec}.${ms}s`
  }
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function fmtRuler(s: number): string {
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return m > 0 ? `${m}:${sec.toString().padStart(2, '0')}` : `${sec}s`
}

function rulerTicks(total: number, maxTicks = 12): number[] {
  if (total <= 0) return []
  // Pick a step that gives ≤ maxTicks ticks and lands on clean values
  const candidates = [1, 2, 5, 10, 15, 20, 30, 60, 120, 300]
  const step = candidates.find(s => total / s <= maxTicks) ?? 300
  const ticks: number[] = []
  for (let t = 0; t <= total; t += step) ticks.push(t)
  return ticks
}

export default function Timeline({
  clips, currentTime, selectedClipId, activeClipIndex,
  onSelectClip, onSeek, onDelete, onReorder, onTrim, onMute,
  onTrimFirst, onTrimLast,
}: Props) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [dropIndex, setDropIndex] = useState<number | null>(null)
  const [trim,      setTrim]      = useState<TrimState | null>(null)

  const selectedIndex = selectedClipId
    ? clips.findIndex(c => c.id === selectedClipId)
    : -1
  const safeSelected = selectedIndex >= 0 ? selectedIndex : null

  // Apply live trim preview to display clips
  const displayClips: EditorClip[] = trim
    ? clips.map((c, i) =>
        i === trim.index
          ? { ...c, start_time: trim.previewStart, end_time: trim.previewEnd }
          : c
      )
    : clips

  const total   = totalDuration(displayClips)
  const offsets = computeTimelineOffsets(displayClips)
  const headPct = total > 0 ? Math.min(100, (currentTime / total) * 100) : 0
  const ticks   = rulerTicks(total)

  // ── Track click → seek ────────────────────────────────────────────────────
  const handleTrackClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (dragIndex !== null || trim !== null) return
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) return
    const assembledT = pixelToTime(e.clientX - rect.left, total, rect.width)
    onSeek(assembledToRaw(assembledT, clips))
  }, [total, onSeek, dragIndex, trim, clips])

  // ── Selection ─────────────────────────────────────────────────────────────
  const handleClipClick = useCallback((index: number) => {
    const clip = clips[index]
    if (!clip) return
    onSelectClip(clip.id === selectedClipId ? null : clip.id)
  }, [clips, selectedClipId, onSelectClip])

  // ── Delete ────────────────────────────────────────────────────────────────
  const handleDelete = useCallback((index: number) => {
    onSelectClip(null)
    onDelete(index)
  }, [onDelete, onSelectClip])

  useEffect(() => {
    if (safeSelected === null) return
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault()
        if (safeSelected !== null) handleDelete(safeSelected)
      } else if (e.key === 'm' || e.key === 'M') {
        e.preventDefault()
        if (safeSelected !== null) onMute(safeSelected)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [safeSelected, handleDelete, onMute])

  // ── Drag/drop reorder ─────────────────────────────────────────────────────
  const handleDragStart = useCallback((index: number) => {
    setDragIndex(index); setDropIndex(null)
  }, [])
  const handleDragOver = useCallback((index: number) => { setDropIndex(index) }, [])
  const handleDrop = useCallback((toIndex: number) => {
    if (dragIndex !== null && dragIndex !== toIndex) onReorder(dragIndex, toIndex)
    setDragIndex(null); setDropIndex(null)
  }, [dragIndex, onReorder])
  const handleDragEnd = useCallback(() => {
    setDragIndex(null); setDropIndex(null)
  }, [])

  // ── Trim ──────────────────────────────────────────────────────────────────
  const handleTrimStart = useCallback((index: number, handle: 'left' | 'right', clientX: number) => {
    const clip    = clips[index]
    const clipDur = clip.end_time - clip.start_time
    const rect    = trackRef.current?.getBoundingClientRect()
    const handlePct = rect ? ((clientX - rect.left) / rect.width) * 100 : 0
    setTrim({
      index, handle,
      startX:       clientX,
      origStart:    clip.start_time,
      origEnd:      clip.end_time,
      maxEnd:       clip.end_time + clipDur * 2,
      previewStart: clip.start_time,
      previewEnd:   clip.end_time,
      handlePct,
    })
  }, [clips])

  const handlePointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (!trim) return
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) return
    const pxPerSec  = rect.width / totalDuration(clips)
    const deltaSec  = (e.clientX - trim.startX) / pxPerSec
    const handlePct = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100))

    if (trim.handle === 'left') {
      const newStart = Math.max(0, Math.min(trim.origEnd - MIN_CLIP_DURATION, trim.origStart + deltaSec))
      setTrim(t => t ? { ...t, previewStart: newStart, handlePct } : null)
    } else {
      const newEnd = Math.max(trim.origStart + MIN_CLIP_DURATION, Math.min(trim.maxEnd, trim.origEnd + deltaSec))
      setTrim(t => t ? { ...t, previewEnd: newEnd, handlePct } : null)
    }
  }, [trim, clips])

  const handlePointerUp = useCallback(() => {
    if (!trim) return
    onTrim(trim.index, trim.previewStart, trim.previewEnd)
    setTrim(null)
  }, [trim, onTrim])

  // ── Empty state ───────────────────────────────────────────────────────────
  if (clips.length === 0) {
    return (
      <div className="flex items-center justify-center py-8">
        <p className="text-slate-600 text-sm">No clips — add scenes from the browser →</p>
      </div>
    )
  }

  // Trim tooltip content
  const trimTooltip = trim ? {
    pct:  trim.handlePct,
    time: trim.handle === 'left' ? trim.previewStart : trim.previewEnd,
    dur:  trim.previewEnd - trim.previewStart,
  } : null

  return (
    <div className="px-4 pt-2 pb-3 space-y-2">

      {/* ── Header row ── */}
      <div className="flex items-center justify-between">
        {/* Legend */}
        <div className="flex items-center gap-3 text-[10px] text-slate-600">
          {[
            { label: 'Positive', color: '#D4A843' },
            { label: 'Negative', color: '#F87171' },
            { label: 'Neutral',  color: '#5A5880' },
          ].map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-sm inline-block" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>

        {/* Stats */}
        <div className="flex items-center gap-2 text-[10px] text-slate-600">
          <span className="font-mono">{clips.length} clips · {fmtRuler(total)}</span>
          {safeSelected !== null && (
            <>
              <span className="text-slate-700">·</span>
              <span className="flex items-center gap-1">
                <kbd className="px-1 py-0.5 rounded bg-surface-raised border border-surface-border text-[9px] font-mono text-slate-500">Del</kbd>
                <kbd className="px-1 py-0.5 rounded bg-surface-raised border border-surface-border text-[9px] font-mono text-slate-500">M</kbd>
              </span>
            </>
          )}
        </div>
      </div>

      {/* ── Ruler ── */}
      <div className="relative h-4 select-none">
        {ticks.map(t => (
          <div
            key={t}
            className="absolute top-0 flex flex-col items-center"
            style={{ left: `${total > 0 ? (t / total) * 100 : 0}%` }}
          >
            <div className="w-px h-2 bg-surface-muted" />
            <span className="text-[8px] text-slate-600 font-mono -translate-x-1/2 mt-0.5">
              {fmtRuler(t)}
            </span>
          </div>
        ))}
      </div>

      {/* ── Track ── */}
      <div
        ref={trackRef}
        className="relative h-16"
        style={{ cursor: trim ? 'ew-resize' : 'crosshair' }}
        onClick={handleTrackClick}
        onDragOver={e => e.preventDefault()}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        {/* Track background */}
        <div
          className="absolute inset-0 rounded-md"
          style={{ background: '#0E0E1A', border: '1px solid #252538' }}
        />

        {/* Subtle grid lines aligned to ruler ticks */}
        {ticks.slice(1).map(t => (
          <div
            key={t}
            className="absolute top-0 bottom-0 w-px pointer-events-none"
            style={{ left: `${(t / total) * 100}%`, background: '#252538' }}
          />
        ))}

        {offsets.map((offset, i) => (
          <TimelineClip
            key={i}
            offset={offset}
            selected={safeSelected === offset.index}
            isActive={activeClipIndex === offset.index}
            isDragOver={dropIndex === offset.index && dragIndex !== offset.index}
            onClick={handleClipClick}
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onDragEnd={handleDragEnd}
            onTrimStart={handleTrimStart}
          />
        ))}

        <Playhead pct={headPct} />

        {/* ── Floating trim tooltip ── */}
        {trimTooltip && (
          <div
            className="absolute bottom-full mb-1.5 z-50 pointer-events-none"
            style={{
              left: `${trimTooltip.pct}%`,
              transform: 'translateX(-50%)',
            }}
          >
            <div className="bg-surface-card border border-primary/50 rounded-md px-2 py-1 shadow-lg whitespace-nowrap">
              <span className="text-[10px] font-mono text-primary">
                {trim!.handle === 'left' ? 'In' : 'Out'}: {fmtTime(trimTooltip.time)}
              </span>
              <span className="text-[10px] font-mono text-slate-500 ml-2">
                {fmtTime(trimTooltip.dur)}
              </span>
            </div>
            {/* Arrow */}
            <div
              className="mx-auto w-0 h-0"
              style={{
                borderLeft: '4px solid transparent',
                borderRight: '4px solid transparent',
                borderTop: '4px solid #D4A84380',
              }}
            />
          </div>
        )}
      </div>

      {/* ── Playhead time label ── */}
      <div className="relative h-3 pointer-events-none select-none">
        <span
          className="absolute text-[9px] font-mono text-primary -translate-x-1/2"
          style={{ left: `${headPct}%` }}
        >
          {fmtRuler(currentTime)}
        </span>
      </div>

      {/* ── In/Out global trim bar ── */}
      <InOutBar
        clips={clips}
        onTrimFirst={onTrimFirst}
        onTrimLast={onTrimLast}
      />

    </div>
  )
}
