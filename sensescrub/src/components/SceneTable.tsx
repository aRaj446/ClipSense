import { useRef, useEffect, useState } from 'react'
import { Plus, X, Check, Film } from 'lucide-react'
import type { SceneEntry } from '../types'

interface Props {
  scenes:         SceneEntry[]
  sceneToClipId:  Map<number, string>
  selectedClipId: string | null
  activeClipId:   string | null
  onSelectClip:   (id: string | null) => void
  onAdd:          (scene: SceneEntry) => void
  onRemove:       (clipId: string) => void
}

type Filter = 'all' | 'trailer' | 'available'

function fmtTime(s: number): string {
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function fmtDur(s: number): string {
  if (s < 60) return `${s.toFixed(1)}s`
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function SentimentPip({ sentiment }: { sentiment: string }) {
  const s = sentiment || 'Neutral'
  const isPos = s === 'Positive' || s === 'Praise'
  const isNeg = s === 'Negative' || s === 'Complaint'
  const color = isPos ? '#D4A843' : isNeg ? '#F87171' : '#5A5880'
  const bg    = isPos ? '#D4A84322' : isNeg ? '#F8717122' : '#5A588022'
  return (
    <span
      className="inline-flex items-center px-1.5 py-0.5 rounded text-[8px] font-semibold uppercase tracking-wide shrink-0"
      style={{ color, background: bg }}
    >
      {s}
    </span>
  )
}

export default function SceneTable({
  scenes, sceneToClipId, selectedClipId, activeClipId,
  onSelectClip, onAdd, onRemove,
}: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const activeRowRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (activeClipId && activeRowRef.current) {
      activeRowRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [activeClipId])

  if (!scenes.length) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 py-12">
        <Film size={28} className="text-slate-700" />
        <p className="text-slate-600 text-xs">No scenes detected</p>
      </div>
    )
  }

  const inTrailerCount  = sceneToClipId.size
  const availableCount  = scenes.length - inTrailerCount

  const filtered = scenes.filter(scene => {
    const inTrailer = sceneToClipId.has(scene.start_time)
    if (filter === 'trailer')   return inTrailer
    if (filter === 'available') return !inTrailer
    return true
  })

  return (
    <div className="flex flex-col h-full">

      {/* ── Header ── */}
      <div className="shrink-0 px-3 pt-2.5 pb-0 border-b border-surface-border">
        <div className="flex items-center justify-between mb-2">
          <span className="text-[9px] text-slate-500 uppercase tracking-wide font-medium">
            Scene Browser
          </span>
          <span className="text-[10px] font-mono text-slate-600">
            <span className="text-primary">{inTrailerCount}</span>
            <span className="text-slate-700"> / </span>
            {scenes.length}
          </span>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-0.5 -mb-px">
          {([
            { key: 'all',       label: 'All',       count: scenes.length },
            { key: 'trailer',   label: 'In trailer', count: inTrailerCount },
            { key: 'available', label: 'Available',  count: availableCount },
          ] as { key: Filter; label: string; count: number }[]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setFilter(tab.key)}
              className={`px-2.5 py-1.5 text-[9px] font-medium rounded-t transition-colors border-b-2 ${
                filter === tab.key
                  ? 'text-slate-200 border-primary bg-surface-raised/30'
                  : 'text-slate-600 border-transparent hover:text-slate-400 hover:bg-surface-raised/10'
              }`}
            >
              {tab.label}
              <span className={`ml-1 font-mono ${filter === tab.key ? 'text-primary' : 'text-slate-700'}`}>
                {tab.count}
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* ── Scene list ── */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex items-center justify-center py-10">
            <p className="text-slate-600 text-xs">No scenes in this view</p>
          </div>
        ) : (
          <div className="divide-y divide-surface-border/30">
            {filtered.map((scene, i) => {
              // Use original index for display number
              const origIndex = scenes.indexOf(scene)
              const clipId    = sceneToClipId.get(scene.start_time) ?? null
              const inTrailer = clipId !== null
              const isSelected = inTrailer && clipId === selectedClipId
              const isActive   = inTrailer && clipId === activeClipId
              const dur        = scene.end_time - scene.start_time

              return (
                <div
                  key={i}
                  ref={isActive ? activeRowRef : undefined}
                  className={`relative px-3 py-2.5 transition-colors border-l-2 ${
                    isActive
                      ? 'border-primary bg-primary/[0.07]'
                      : isSelected
                        ? 'border-accent-amber bg-accent-amber/[0.04]'
                        : inTrailer
                          ? 'border-transparent hover:bg-surface-raised/20'
                          : 'border-transparent hover:bg-surface-raised/10'
                  } ${!inTrailer ? 'opacity-60 hover:opacity-90' : ''}`}
                >
                  {/* ── Row top: number + time + dur + sentiment ── */}
                  <div className="flex items-center gap-2 mb-1 min-w-0">
                    <span className="text-[9px] font-mono text-slate-700 shrink-0 w-5 text-right select-none">
                      {origIndex + 1}
                    </span>
                    <span className="text-[9px] font-mono text-slate-500 shrink-0">
                      {fmtTime(scene.start_time)}
                    </span>
                    <span className="text-[9px] font-mono text-slate-600 shrink-0">
                      {fmtDur(dur)}
                    </span>
                    <div className="flex-1" />
                    <SentimentPip sentiment={scene.sentiment} />
                  </div>

                  {/* ── Row middle: topic + actions ── */}
                  <div className="flex items-center gap-1.5 min-w-0 pl-7">
                    <span className={`text-[11px] flex-1 truncate leading-snug ${
                      inTrailer ? 'text-slate-200' : 'text-slate-500'
                    }`}>
                      {scene.topic || `Scene ${origIndex + 1}`}
                    </span>

                    {/* Actions */}
                    {inTrailer ? (
                      <div className="flex items-center gap-1 shrink-0">
                        {/* Select / deselect */}
                        <button
                          onClick={() => onSelectClip(isSelected ? null : clipId!)}
                          title={isSelected ? 'Deselect clip' : 'Select in timeline'}
                          className={`w-6 h-6 flex items-center justify-center rounded transition-colors ${
                            isSelected
                              ? 'bg-accent-amber/20 text-accent-amber hover:bg-accent-amber/30'
                              : 'text-slate-600 hover:text-slate-300 hover:bg-surface-raised/40'
                          }`}
                        >
                          <Check size={11} />
                        </button>
                        {/* Remove */}
                        <button
                          onClick={() => onRemove(clipId!)}
                          title="Remove from trailer"
                          className="w-6 h-6 flex items-center justify-center rounded text-slate-600 hover:text-red-400 hover:bg-red-400/10 transition-colors"
                        >
                          <X size={11} />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => onAdd(scene)}
                        title="Add to trailer"
                        className="flex items-center gap-0.5 px-2 py-0.5 rounded text-[9px] font-medium shrink-0 text-primary border border-primary/30 hover:bg-primary/10 hover:border-primary/60 transition-colors"
                      >
                        <Plus size={9} />
                        Add
                      </button>
                    )}
                  </div>

                  {/* ── Row bottom: transcript ── */}
                  {scene.transcript_text && (
                    <p className="text-[9px] text-slate-600 italic leading-snug mt-1 pl-7 line-clamp-2">
                      {scene.transcript_text}
                    </p>
                  )}

                  {/* Active playback indicator dot */}
                  {isActive && (
                    <div
                      className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-4 rounded-r"
                      style={{ background: '#D4A843', boxShadow: '0 0 6px #D4A84388' }}
                    />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
