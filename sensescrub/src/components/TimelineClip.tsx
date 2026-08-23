import { VolumeX } from 'lucide-react'
import type { ClipOffset } from '../utils/timeline'

interface Props {
  offset: ClipOffset
  selected: boolean
  isActive: boolean
  isDragOver: boolean
  onClick: (index: number) => void
  onDragStart: (index: number) => void
  onDragOver: (index: number) => void
  onDrop: (index: number) => void
  onDragEnd: () => void
  onTrimStart: (index: number, handle: 'left' | 'right', clientX: number) => void
}

function sentimentBg(sentiment: string, muted: boolean): string {
  if (muted) return '#4A4870'
  if (sentiment === 'Positive' || sentiment === 'Praise')    return '#D4A843'
  if (sentiment === 'Negative' || sentiment === 'Complaint') return '#F87171'
  return '#5A5880'
}

function sentimentFill(sentiment: string, muted: boolean): string {
  if (muted) return '#2A2848'
  if (sentiment === 'Positive' || sentiment === 'Praise')    return '#D4A84318'
  if (sentiment === 'Negative' || sentiment === 'Complaint') return '#F8717118'
  return '#36365418'
}

function fmt(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

export default function TimelineClip({
  offset, selected, isActive, isDragOver,
  onClick, onDragStart, onDragOver, onDrop, onDragEnd, onTrimStart,
}: Props) {
  const { clip, index, leftPct, widthPct } = offset
  const dur   = clip.end_time - clip.start_time
  const muted = clip.muted ?? false
  const accentColor = sentimentBg(clip.sentiment, muted)
  const fillColor   = sentimentFill(clip.sentiment, muted)

  // Border color priority: selected > active > sentiment
  const borderColor = selected ? '#D4A843' : isActive ? '#8B7CF6' : accentColor
  const boxShadow   = selected
    ? `0 0 0 2px #D4A84366, inset 0 0 12px #D4A84310`
    : isActive
      ? `0 0 0 2px #8B7CF655`
      : undefined

  return (
    <div
      role="button"
      tabIndex={0}
      draggable={!selected}
      aria-label={`Clip ${index + 1}: ${clip.topic || 'clip'} ${fmt(clip.start_time)}–${fmt(clip.end_time)}${muted ? ' (muted)' : ''}`}
      aria-pressed={selected}
      onClick={() => onClick(index)}
      onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') onClick(index) }}
      onDragStart={e => { e.stopPropagation(); onDragStart(index) }}
      onDragOver={e => { e.preventDefault(); e.stopPropagation(); onDragOver(index) }}
      onDrop={e => { e.preventDefault(); e.stopPropagation(); onDrop(index) }}
      onDragEnd={e => { e.stopPropagation(); onDragEnd() }}
      className="absolute top-1 bottom-1"
      style={{
        left:   `${leftPct}%`,
        width:  `${widthPct}%`,
        padding: '0 2px',
        cursor: selected ? 'default' : 'grab',
      }}
    >
      {/* ── Left trim handle ── */}
      {selected && (
        <div
          className="absolute left-0 top-0 bottom-0 w-3 z-30 flex items-center justify-center group"
          style={{ cursor: 'ew-resize' }}
          onPointerDown={e => { e.stopPropagation(); e.preventDefault(); onTrimStart(index, 'left', e.clientX) }}
          onClick={e => e.stopPropagation()}
        >
          {/* Bracket shape */}
          <div className="relative w-2 h-5 flex items-center justify-center">
            <div className="absolute left-0 top-0 bottom-0 w-0.5 rounded-full bg-primary" />
            <div className="absolute left-0 top-0 w-1.5 h-0.5 rounded-full bg-primary" />
            <div className="absolute left-0 bottom-0 w-1.5 h-0.5 rounded-full bg-primary" />
          </div>
        </div>
      )}

      {/* ── Clip body ── */}
      <div
        className="h-full rounded flex flex-col overflow-hidden transition-all duration-75 select-none"
        style={{
          background: fillColor,
          border:     `1.5px solid ${borderColor}`,
          boxShadow,
          opacity: muted ? 0.6 : 1,
        }}
      >
        {/* Top accent bar */}
        <div
          className="h-1 w-full shrink-0"
          style={{
            background: muted
              ? `repeating-linear-gradient(45deg, ${accentColor} 0px, ${accentColor} 3px, transparent 3px, transparent 6px)`
              : accentColor,
            opacity: selected ? 1 : 0.85,
          }}
        />

        {/* Content */}
        {widthPct > 3 && (
          <div className="flex-1 px-1 pt-0.5 pb-1 min-w-0 flex flex-col justify-between">
            {/* Clip number + mute icon */}
            <div className="flex items-center gap-0.5 min-w-0">
              <span
                className="text-[8px] font-bold shrink-0 leading-none"
                style={{ color: accentColor, opacity: 0.9 }}
              >
                {index + 1}
              </span>
              {muted && widthPct > 5 && (
                <VolumeX size={7} className="shrink-0" style={{ color: accentColor, opacity: 0.7 }} />
              )}
            </div>

            {/* Topic label */}
            {widthPct > 6 && (
              <p
                className="text-[9px] font-medium leading-tight truncate"
                style={{ color: selected || isActive ? '#E8E4F0' : '#A8A4B8' }}
              >
                {clip.topic || `Clip ${index + 1}`}
              </p>
            )}

            {/* Duration */}
            {widthPct > 8 && (
              <p className="text-[8px] font-mono leading-none" style={{ color: accentColor, opacity: 0.75 }}>
                {fmt(dur)}
              </p>
            )}
          </div>
        )}
      </div>

      {/* ── Drag-over indicator ── */}
      {isDragOver && (
        <div
          className="absolute left-0 top-0 bottom-0 w-0.5 rounded-full z-40"
          style={{ background: '#D4A843', boxShadow: '0 0 6px #D4A843' }}
        />
      )}

      {/* ── Right trim handle ── */}
      {selected && (
        <div
          className="absolute right-0 top-0 bottom-0 w-3 z-30 flex items-center justify-center group"
          style={{ cursor: 'ew-resize' }}
          onPointerDown={e => { e.stopPropagation(); e.preventDefault(); onTrimStart(index, 'right', e.clientX) }}
          onClick={e => e.stopPropagation()}
        >
          <div className="relative w-2 h-5 flex items-center justify-center">
            <div className="absolute right-0 top-0 bottom-0 w-0.5 rounded-full bg-primary" />
            <div className="absolute right-0 top-0 w-1.5 h-0.5 rounded-full bg-primary" />
            <div className="absolute right-0 bottom-0 w-1.5 h-0.5 rounded-full bg-primary" />
          </div>
        </div>
      )}
    </div>
  )
}
