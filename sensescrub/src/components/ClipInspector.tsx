import { X, Trash2, VolumeX, Volume2, RotateCcw, Play } from 'lucide-react'
import type { EditorClip } from '../types'

interface Props {
  clip:          EditorClip
  index:         number
  /** Raw start_time of the original scene — used for reset trim */
  origStart:     number
  /** Raw end_time of the original scene — used for reset trim */
  origEnd:       number
  onClose:       () => void
  onSeek:        (t: number) => void
  onDelete:      (index: number) => void
  onMute:        (index: number) => void
  onResetTrim:   (index: number, origStart: number, origEnd: number) => void
  onSpeedChange?: (clipId: string, speed: number) => void
}

function fmtPrecise(s: number): string {
  const m   = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return m > 0 ? `${m}:${sec.padStart(4, '0')}` : `${sec}s`
}

function fmtDur(s: number): string {
  if (s < 60) return `${s.toFixed(2)}s`
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function sentimentColor(sentiment: string): { color: string; bg: string } {
  const s = sentiment || 'Neutral'
  if (s === 'Positive' || s === 'Praise')    return { color: '#D4A843', bg: '#D4A84320' }
  if (s === 'Negative' || s === 'Complaint') return { color: '#F87171', bg: '#F8717120' }
  return { color: '#8B7CF6', bg: '#8B7CF620' }
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  if (!value) return null
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[8px] text-slate-600 uppercase tracking-wide font-medium">{label}</span>
      <span className={`text-[11px] text-slate-300 leading-snug break-words ${mono ? 'font-mono' : ''}`}>
        {value}
      </span>
    </div>
  )
}

export default function ClipInspector({
  clip, index, origStart, origEnd,
  onClose, onSeek, onDelete, onMute, onResetTrim, onSpeedChange,
}: Props) {
  const dur         = clip.end_time - clip.start_time
  const isTrimmed   = clip.start_time !== origStart || clip.end_time !== origEnd
  const { color, bg } = sentimentColor(clip.sentiment)

  return (
    <div className="animate-fade-in">

      {/* ── Title row ── */}
      <div className="flex items-center gap-2 px-3 pt-3 pb-2">
        {/* Clip number badge */}
        <div
          className="w-6 h-6 rounded flex items-center justify-center shrink-0 text-[10px] font-bold"
          style={{ background: bg, color }}
        >
          {index + 1}
        </div>

        {/* Sentiment pill */}
        <span
          className="px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase tracking-wide"
          style={{ color, background: bg }}
        >
          {clip.sentiment || 'Neutral'}
        </span>

        {/* Muted badge */}
        {clip.muted && (
          <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-surface-raised text-slate-500">
            muted
          </span>
        )}

        {/* Trimmed badge */}
        {isTrimmed && (
          <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-accent-violet/15 text-accent-violet">
            trimmed
          </span>
        )}

        <div className="flex-1" />

        {/* Close */}
        <button
          onClick={onClose}
          className="w-6 h-6 flex items-center justify-center rounded text-slate-600 hover:text-slate-300 hover:bg-surface-raised/50 transition-colors"
          aria-label="Close inspector"
        >
          <X size={12} />
        </button>
      </div>

      {/* ── Topic ── */}
      {clip.topic && (
        <div className="px-3 pb-2">
          <p className="text-[12px] font-medium text-slate-200 leading-snug">{clip.topic}</p>
        </div>
      )}

      {/* ── Time strip ── */}
      <div
        className="mx-3 mb-2 rounded-lg px-3 py-2 flex items-center gap-3"
        style={{ background: '#0E0E1A', border: '1px solid #252538' }}
      >
        {/* In point */}
        <div className="flex flex-col items-center gap-0.5 flex-1">
          <span className="text-[8px] text-slate-600 uppercase tracking-wide">In</span>
          <span className="text-[11px] font-mono text-slate-200">{fmtPrecise(clip.start_time)}</span>
        </div>

        {/* Arrow + duration */}
        <div className="flex flex-col items-center gap-0.5">
          <span className="text-[8px] text-slate-700">──────</span>
          <span className="text-[10px] font-mono font-semibold" style={{ color }}>{fmtDur(dur)}</span>
        </div>

        {/* Out point */}
        <div className="flex flex-col items-center gap-0.5 flex-1">
          <span className="text-[8px] text-slate-600 uppercase tracking-wide">Out</span>
          <span className="text-[11px] font-mono text-slate-200">{fmtPrecise(clip.end_time)}</span>
        </div>
      </div>

      {/* ── Action buttons ── */}
      <div className="flex items-center gap-1 px-3 pb-3">
        {/* Seek to start */}
        <button
          onClick={() => onSeek(clip.start_time)}
          title={`Seek to ${fmtPrecise(clip.start_time)}`}
          className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-medium text-primary border border-primary/30 hover:bg-primary/10 hover:border-primary/60 transition-colors"
        >
          <Play size={9} />
          Seek
        </button>

        {/* Mute toggle */}
        <button
          onClick={() => onMute(index)}
          title={clip.muted ? 'Unmute clip' : 'Mute clip audio'}
          className={`flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-medium border transition-colors ${
            clip.muted
              ? 'text-accent-amber border-accent-amber/30 bg-accent-amber/10 hover:bg-accent-amber/20'
              : 'text-slate-500 border-slate-700 hover:text-slate-200 hover:border-slate-500'
          }`}
        >
          {clip.muted ? <Volume2 size={9} /> : <VolumeX size={9} />}
          {clip.muted ? 'Unmute' : 'Mute'}
        </button>

        {/* Reset trim — only shown when trimmed */}
        {isTrimmed && (
          <button
            onClick={() => onResetTrim(index, origStart, origEnd)}
            title="Restore original clip boundaries"
            className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-medium text-accent-violet border border-accent-violet/30 hover:bg-accent-violet/10 transition-colors"
          >
            <RotateCcw size={9} />
            Reset
          </button>
        )}

        <div className="flex-1" />

        {/* Delete */}
        <button
          onClick={() => onDelete(index)}
          title="Remove clip from trailer"
          className="flex items-center gap-1 px-2 py-1.5 rounded text-[10px] font-medium text-red-400 border border-red-400/25 hover:bg-red-400/10 hover:border-red-400/50 transition-colors"
          aria-label="Delete clip"
        >
          <Trash2 size={9} />
          Delete
        </button>
      </div>

      {/* ── Speed control ── */}
      {onSpeedChange && (
        <div className="mx-3 mb-2 rounded-lg px-3 py-2" style={{ background: '#0E0E1A', border: '1px solid #252538' }}>
          <span className="text-[8px] text-slate-600 uppercase tracking-wide font-medium">Speed</span>
          <div className="flex items-center gap-1.5 mt-1.5">
            {[0.5, 0.75, 1, 1.5, 2].map(speed => (
              <button
                key={speed}
                onClick={() => onSpeedChange(clip.id, speed)}
                className={`px-2 py-1 rounded text-[10px] font-mono font-medium transition-colors ${
                  (clip.speed ?? 1) === speed
                    ? 'bg-primary/20 text-primary border border-primary/40'
                    : 'text-slate-500 border border-slate-700 hover:text-slate-200 hover:border-slate-500'
                }`}
              >
                {speed}x
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Metadata fields ── */}
      <div
        className="mx-3 mb-3 rounded-lg p-2.5 grid grid-cols-2 gap-x-3 gap-y-2.5"
        style={{ background: '#0E0E1A', border: '1px solid #252538' }}
      >
        <Field label="Mood"     value={clip.mood_group} />
        <Field label="Platform" value={clip.platform ?? ''} />
        <Field label="Audio"    value={clip.muted ? 'Muted' : 'Active'} />
        {clip.reason && (
          <div className="col-span-2 flex flex-col gap-0.5">
            <span className="text-[8px] text-slate-600 uppercase tracking-wide font-medium">Reason</span>
            <span className="text-[11px] text-slate-400 leading-snug">{clip.reason}</span>
          </div>
        )}
        {clip.transcript_text && (
          <div className="col-span-2 flex flex-col gap-0.5">
            <span className="text-[8px] text-slate-600 uppercase tracking-wide font-medium">Transcript</span>
            <p className="text-[10px] text-slate-500 italic leading-snug line-clamp-3">
              {clip.transcript_text}
            </p>
          </div>
        )}
      </div>

    </div>
  )
}
