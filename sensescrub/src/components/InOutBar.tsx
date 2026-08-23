import { useRef, useState, useCallback } from 'react'
import type { EditorClip } from '../types'

interface Props {
  clips: EditorClip[]
  onTrimFirst: (newStart: number) => void
  onTrimLast:  (newEnd: number)   => void
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

const MIN_DUR = 0.5

export default function InOutBar({ clips, onTrimFirst, onTrimLast }: Props) {
  const barRef  = useRef<HTMLDivElement>(null)
  const [drag,  setDrag]  = useState<'in' | 'out' | null>(null)
  const [inPct, setInPct] = useState(0)
  const [outPct,setOutPct]= useState(100)

  const origRef = useRef<{ clientX: number; pct: number; clip: EditorClip } | null>(null)

  const totalDur = clips.reduce((s, c) => s + Math.max(0, c.end_time - c.start_time), 0)

  const startDragIn = useCallback((e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    if (!clips.length) return
    setDrag('in')
    origRef.current = { clientX: e.clientX, pct: inPct, clip: clips[0] }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [clips, inPct])

  const startDragOut = useCallback((e: React.PointerEvent) => {
    e.preventDefault(); e.stopPropagation()
    if (!clips.length) return
    setDrag('out')
    origRef.current = { clientX: e.clientX, pct: outPct, clip: clips[clips.length - 1] }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }, [clips, outPct])

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!drag || !origRef.current || !barRef.current) return
    const rect     = barRef.current.getBoundingClientRect()
    const deltaPct = ((e.clientX - origRef.current.clientX) / rect.width) * 100

    if (drag === 'in') {
      const first    = origRef.current.clip
      const maxInPct = ((first.end_time - first.start_time - MIN_DUR) / totalDur) * 100
      setInPct(Math.max(0, Math.min(maxInPct, origRef.current.pct + deltaPct)))
    } else {
      const last          = origRef.current.clip
      const maxOutTrimPct = ((last.end_time - last.start_time - MIN_DUR) / totalDur) * 100
      setOutPct(Math.max(100 - maxOutTrimPct, Math.min(100, origRef.current.pct + deltaPct)))
    }
  }, [drag, totalDur])

  const handlePointerUp = useCallback(() => {
    if (!drag || !origRef.current) { setDrag(null); return }

    if (drag === 'in') {
      const first    = clips[0]
      const trimSec  = (inPct / 100) * totalDur
      const newStart = Math.min(first.start_time + trimSec, first.end_time - MIN_DUR)
      onTrimFirst(Math.max(first.start_time, newStart))
      setInPct(0)
    } else {
      const last   = clips[clips.length - 1]
      const trimSec = ((100 - outPct) / 100) * totalDur
      const newEnd  = Math.max(last.end_time - trimSec, last.start_time + MIN_DUR)
      onTrimLast(Math.min(last.end_time, newEnd))
      setOutPct(100)
    }
    setDrag(null)
    origRef.current = null
  }, [drag, clips, inPct, outPct, totalDur, onTrimFirst, onTrimLast])

  if (!clips.length || totalDur <= 0) return null

  const first = clips[0]
  const last  = clips[clips.length - 1]

  const inTimeSec      = (inPct / 100) * totalDur
  const outTimeSec     = ((100 - outPct) / 100) * totalDur
  const previewInTime  = Math.min(first.start_time + inTimeSec,  first.end_time  - MIN_DUR)
  const previewOutTime = Math.max(last.end_time    - outTimeSec, last.start_time + MIN_DUR)

  const inLabel  = drag === 'in'  ? fmtTime(previewInTime)  : fmtTime(first.start_time)
  const outLabel = drag === 'out' ? fmtTime(previewOutTime) : fmtTime(last.end_time)

  return (
    <div className="space-y-1">
      {/* Label row */}
      <div className="flex items-center justify-between px-0.5">
        <span className="text-[9px] text-slate-600 uppercase tracking-wide font-medium">In / Out</span>
        <span className="text-[10px] text-slate-500 font-mono">
          <span className={drag === 'in' ? 'text-primary' : ''}>In {inLabel}</span>
          <span className="text-slate-700 mx-1.5">·</span>
          <span className={drag === 'out' ? 'text-accent-amber' : ''}>Out {outLabel}</span>
        </span>
      </div>

      {/* Bar */}
      <div
        ref={barRef}
        className="relative h-8 rounded-lg overflow-hidden select-none"
        style={{ background: '#0E0E1A', border: '1px solid #252538' }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        {/* Dimmed left region */}
        {inPct > 0 && (
          <div
            className="absolute top-0 bottom-0 bg-black/50"
            style={{ left: 0, width: `${inPct}%` }}
          />
        )}

        {/* Active region */}
        <div
          className="absolute top-0 bottom-0"
          style={{
            left:       `${inPct}%`,
            right:      `${100 - outPct}%`,
            background: 'linear-gradient(90deg, #D4A84312 0%, #D4A84308 100%)',
            borderTop:  '1px solid #D4A84330',
            borderBottom: '1px solid #D4A84330',
          }}
        />

        {/* Dimmed right region */}
        {outPct < 100 && (
          <div
            className="absolute top-0 bottom-0 bg-black/50"
            style={{ right: 0, width: `${100 - outPct}%` }}
          />
        )}

        {/* IN handle */}
        <div
          className="absolute top-0 bottom-0 w-5 z-10 flex items-center justify-center group"
          style={{ left: `${inPct}%`, transform: 'translateX(-50%)', cursor: 'ew-resize' }}
          onPointerDown={startDragIn}
        >
          <div
            className="w-1 h-full rounded-sm transition-colors"
            style={{ background: drag === 'in' ? '#D4A843' : '#D4A84380' }}
          />
          <span
            className="absolute text-[8px] font-bold font-mono whitespace-nowrap pointer-events-none"
            style={{ color: drag === 'in' ? '#D4A843' : '#D4A84399', top: '50%', transform: 'translateY(-50%) translateX(6px)' }}
          >
            IN
          </span>
        </div>

        {/* OUT handle */}
        <div
          className="absolute top-0 bottom-0 w-5 z-10 flex items-center justify-center group"
          style={{ left: `${outPct}%`, transform: 'translateX(-50%)', cursor: 'ew-resize' }}
          onPointerDown={startDragOut}
        >
          <div
            className="w-1 h-full rounded-sm transition-colors"
            style={{ background: drag === 'out' ? '#F59E0B' : '#F59E0B80' }}
          />
          <span
            className="absolute text-[8px] font-bold font-mono whitespace-nowrap pointer-events-none"
            style={{ color: drag === 'out' ? '#F59E0B' : '#F59E0B99', top: '50%', transform: 'translateY(-50%) translateX(-22px)' }}
          >
            OUT
          </span>
        </div>
      </div>
    </div>
  )
}
