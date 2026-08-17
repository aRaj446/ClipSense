/**
 * TimeSavedCard
 *
 * Displays the "Estimated time saved" business-impact metric for a completed
 * smart trailer job.
 *
 * Data source: GET /smart-trailer/job/{id}/time-saved
 *   Returns TimeSavedBreakdown with three auditable components:
 *     manual_editing_hours        — raw_footage_duration_secs / 60 * 0.5 / 60
 *     processing_hours            — (updated_at - created_at) / 3600
 *     estimated_time_saved_hours  — max(manual - processing, 0)
 *
 * Unit note: raw_footage_duration_secs is in SECONDS (confirmed from
 * _get_video_duration() which parses HH:MM:SS.ms → h*3600 + m*60 + s).
 * The backend converts to hours before returning — the frontend never
 * performs the unit conversion itself.
 */

import { useEffect, useState } from 'react'
import { Clock, Zap } from 'lucide-react'
import { SmartTrailerJob, TimeSavedBreakdown } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import Card from './Card'

interface Props {
  job: SmartTrailerJob
}

function fmtHours(hours: number): string {
  if (hours < 1 / 60) return '< 1 min'
  if (hours < 1) {
    const mins = Math.round(hours * 60)
    return `${mins} min`
  }
  const h = Math.floor(hours)
  const m = Math.round((hours - h) * 60)
  return m > 0 ? `${h}h ${m}m` : `${h}h`
}

export default function TimeSavedCard({ job }: Props) {
  const [breakdown, setBreakdown] = useState<TimeSavedBreakdown | null>(null)
  const [error, setError]         = useState(false)

  useEffect(() => {
    if (job.status !== 'done') return
    setBreakdown(null)
    setError(false)
    smartTrailerService.getTimeSaved(job.id)
      .then(setBreakdown)
      .catch(() => setError(true))
  }, [job.id, job.status])

  if (job.status !== 'done') return null
  // Silently hide if the backend can't provide the breakdown (e.g. old job
  // without raw_footage_duration_secs stored) rather than showing an error.
  if (error || !breakdown) return null

  const { manual_editing_hours, processing_hours, estimated_time_saved_hours } = breakdown

  // Bar widths: processing is the small orange slice, saved is the large gold slice.
  // Guard against manual_editing_hours = 0 (shouldn't happen but be safe).
  const totalHours = manual_editing_hours
  const savedPct      = totalHours > 0 ? Math.round((estimated_time_saved_hours / totalHours) * 100) : 0
  const processingPct = totalHours > 0 ? Math.round((processing_hours / totalHours) * 100) : 0
  // Clamp so the two segments always sum to ≤ 100 (rounding can push over by 1)
  const barSavedPct      = Math.min(savedPct, 100)
  const barProcessingPct = Math.min(processingPct, 100 - barSavedPct)

  return (
    <Card className="space-y-5">

      {/* ── Header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <Clock size={15} style={{ color: '#D4A843' }} />
            <h3 className="font-semibold" style={{ color: '#F0EDE8' }}>
              Estimated time saved
            </h3>
          </div>
          <p className="text-xs" style={{ color: '#5C5A72' }}>
            Based on estimated manual trailer-editing effort.
          </p>
        </div>
        {/* Prominent headline number */}
        <div className="text-right shrink-0">
          <p
            className="font-extrabold leading-none"
            style={{
              fontSize: 'clamp(1.75rem, 4vw, 2.5rem)',
              background: 'linear-gradient(135deg, #E8C56A, #D4A843)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}
          >
            {fmtHours(estimated_time_saved_hours)}
          </p>
          <p className="text-[10px] mt-0.5 font-medium uppercase tracking-widest" style={{ color: '#5C5A72' }}>
            estimated time saved
          </p>
        </div>
      </div>

      {/* ── Stat row ── */}
      <div className="grid grid-cols-2 gap-3">
        {[
          {
            label: 'Manual estimate',
            value: fmtHours(manual_editing_hours),
            sub: `${(breakdown.raw_footage_duration_secs / 60).toFixed(1)} min footage × 0.5`,
            color: '#A8A4B8',
            bg: 'linear-gradient(135deg,#A8A4B818,#A8A4B808)',
            border: '#A8A4B822',
          },
          {
            label: 'ClipSense',
            value: fmtHours(processing_hours),
            sub: 'actual processing time',
            color: '#8B7CF6',
            bg: 'linear-gradient(135deg,#8B7CF618,#8B7CF608)',
            border: '#8B7CF622',
          },
        ].map(s => (
          <div
            key={s.label}
            className="rounded-xl p-3 text-center border"
            style={{ background: s.bg, borderColor: s.border }}
          >
            <p className="text-xl font-bold" style={{ color: s.color }}>
              {s.value}
            </p>
            <p className="text-[10px] font-semibold mt-0.5" style={{ color: s.color }}>
              {s.label}
            </p>
            <p className="text-[10px] mt-0.5" style={{ color: '#5C5A72' }}>
              {s.sub}
            </p>
          </div>
        ))}
      </div>

      {/* ── Comparison bar ── */}
      <div>
        <div className="flex justify-between text-[10px] mb-1.5" style={{ color: '#5C5A72' }}>
          <span className="flex items-center gap-1">
            <Zap size={9} /> ClipSense processing
          </span>
          <span style={{ color: '#D4A843' }}>
            {savedPct}% faster than manual
          </span>
        </div>
        {/* Bar: gray track, orange processing slice, gold saved slice */}
        <div className="h-2.5 rounded-full overflow-hidden" style={{ background: '#1E1E30' }}>
          <div className="h-full flex">
            <div
              className="h-full"
              style={{
                width: `${barProcessingPct}%`,
                background: '#8B7CF6',
                minWidth: barProcessingPct > 0 ? 4 : 0,
                borderRadius: barSavedPct === 0 ? '9999px' : '9999px 0 0 9999px',
              }}
            />
            <div
              className="h-full"
              style={{
                width: `${barSavedPct}%`,
                background: 'linear-gradient(90deg, #D4A843, #E8C56A)',
                minWidth: barSavedPct > 0 ? 4 : 0,
                borderRadius: barProcessingPct === 0 ? '9999px' : '0 9999px 9999px 0',
              }}
            />
          </div>
        </div>
        <div className="flex gap-4 mt-1.5">
          {[
            { label: 'Processing', color: '#8B7CF6' },
            { label: 'Estimated time saved', color: '#D4A843' },
          ].map(s => (
            <span key={s.label} className="flex items-center gap-1 text-[10px]" style={{ color: '#5C5A72' }}>
              <span className="w-2 h-2 rounded-full inline-block" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      </div>

      {/* ── Disclaimer ── */}
      <p className="text-[10px] leading-relaxed" style={{ color: '#5C5A72' }}>
        Manual estimate: raw footage duration ({(breakdown.raw_footage_duration_secs / 60).toFixed(1)} min)
        × 0.5 hrs/min = {manual_editing_hours.toFixed(2)} hrs.
        ClipSense processing: {processing_hours.toFixed(2)} hrs actual.
        Actual savings vary by project complexity.
      </p>
    </Card>
  )
}
