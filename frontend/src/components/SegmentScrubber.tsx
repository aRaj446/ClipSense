import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { Link2, Link2Off, TrendingUp, TrendingDown, Minus, Activity, Tag, BarChart2, GitCompare, X, Play, Pause, Trophy, Download } from 'lucide-react'
import { StoredDataset, StoredSegment, TrailerJob } from '../types/analysis'
import { trailerService } from '../services/trailerService'
import Card from './Card'

interface Props {
  datasets: StoredDataset[]
  videoUrl?: string
  variants?: TrailerJob[]
  autoCompare?: boolean
  originalUrl?: string      // browser-accessible URL for the original/baseline trailer
  originalLabel?: string    // display name for the original (defaults to "Original")
}

interface Range {
  start: number
  end: number
}

interface RangeMetrics {
  total: number
  positive: number
  negative: number
  neutral: number
  avgConfidence: number
  topTopic: string
  engagementScore: number
  segments: StoredSegment[]
}

const SENTIMENT_POS = new Set(['Positive', 'Praise'])
const SENTIMENT_NEG = new Set(['Negative', 'Complaint'])

function parseTimestamp(ts: string | null): number | null {
  if (!ts) return null
  const parts = ts.split(':').map(Number)
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return null
}

function computeMetrics(segments: StoredSegment[], range: Range): RangeMetrics {
  const filtered = segments.filter(s => {
    const t = parseTimestamp(s.timestamp)
    return t !== null && t >= range.start && t <= range.end
  })

  if (filtered.length === 0) {
    return { total: 0, positive: 0, negative: 0, neutral: 0, avgConfidence: 0, topTopic: '—', engagementScore: 0, segments: [] }
  }

  const positive = filtered.filter(s => SENTIMENT_POS.has(s.sentiment)).length
  const negative = filtered.filter(s => SENTIMENT_NEG.has(s.sentiment)).length
  const neutral  = filtered.length - positive - negative
  const avgConf  = filtered.reduce((a, s) => a + s.confidence, 0) / filtered.length

  const topicCount: Record<string, number> = {}
  filtered.forEach(s => { topicCount[s.topic] = (topicCount[s.topic] ?? 0) + 1 })
  const topTopic = Object.entries(topicCount).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—'

  const sentimentScore  = (positive - negative * 0.8) / filtered.length
  const engagementScore = Math.max(0, Math.min(1, (sentimentScore + 1) / 2 * avgConf))

  return { total: filtered.length, positive, negative, neutral, avgConfidence: avgConf, topTopic, engagementScore, segments: filtered }
}

function formatTime(s: number): string {
  const m   = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

// ── Video preview — seeks in real-time ───────────────────────────────────────

function VideoPreview({ src, seekTo }: { src: string; seekTo: number }) {
  const ref = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const v = ref.current
    if (!v) return
    const doSeek = () => { v.currentTime = seekTo }
    if (v.readyState >= 1) {
      doSeek()
    } else {
      v.addEventListener('loadedmetadata', doSeek, { once: true })
    }
  }, [seekTo])

  return (
    <video
      ref={ref}
      src={src}
      className="w-full rounded-lg aspect-video object-contain bg-black"
      preload="metadata"
      muted
      playsInline
      controls
    />
  )
}

// ── Dual-handle range slider ──────────────────────────────────────────────────

interface SliderProps {
  min: number
  max: number
  range: Range
  color: string
  onChange: (r: Range) => void
}

function RangeSlider({ min, max, range, color, onChange }: SliderProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const dragging = useRef<'start' | 'end' | null>(null)

  const toPercent   = (v: number) => max === min ? 0 : ((v - min) / (max - min)) * 100
  const fromClientX = useCallback((clientX: number): number => {
    const rect = trackRef.current?.getBoundingClientRect()
    if (!rect) return min
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return Math.round(min + ratio * (max - min))
  }, [min, max])

  const onMouseDown = (handle: 'start' | 'end') => (e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = handle
    const onMove = (ev: MouseEvent) => {
      const val = fromClientX(ev.clientX)
      if (dragging.current === 'start') {
        onChange({ start: Math.min(val, range.end - 1), end: range.end })
      } else {
        onChange({ start: range.start, end: Math.max(val, range.start + 1) })
      }
    }
    const onUp = () => {
      dragging.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const startPct = toPercent(range.start)
  const endPct   = toPercent(range.end)

  return (
    <div ref={trackRef} className="relative h-5 flex items-center select-none cursor-pointer">
      <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-700" />
      <div className="absolute h-1.5 rounded-full" style={{ left: `${startPct}%`, width: `${endPct - startPct}%`, background: color }} />
      <div
        className="absolute w-4 h-4 rounded-full border-2 border-white shadow-md cursor-grab active:cursor-grabbing z-10 -translate-x-1/2"
        style={{ left: `${startPct}%`, background: color }}
        onMouseDown={onMouseDown('start')}
      />
      <div
        className="absolute w-4 h-4 rounded-full border-2 border-white shadow-md cursor-grab active:cursor-grabbing z-10 -translate-x-1/2"
        style={{ left: `${endPct}%`, background: color }}
        onMouseDown={onMouseDown('end')}
      />
    </div>
  )
}

// ── Metrics panel ─────────────────────────────────────────────────────────────

function MetricsPanel({ metrics, label, color }: { metrics: RangeMetrics; label: string; color: string }) {
  const engPct  = Math.round(metrics.engagementScore * 100)
  const confPct = Math.round(metrics.avgConfidence * 100)

  return (
    <div className="space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wide" style={{ color }}>{label}</p>
      {metrics.total === 0 ? (
        <p className="text-xs text-slate-500 italic">No timestamped segments in this range.</p>
      ) : (
        <>
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span className="flex items-center gap-1"><Activity size={11} />Engagement Score</span>
              <span className="font-semibold" style={{ color }}>{engPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
              <div className="h-full rounded-full transition-all duration-150" style={{ width: `${engPct}%`, background: color }} />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-xs text-slate-400 mb-1">
              <span className="flex items-center gap-1"><BarChart2 size={11} />Avg Confidence</span>
              <span className="font-semibold text-yellow-400">{confPct}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-700 overflow-hidden">
              <div className="h-full rounded-full bg-yellow-400 transition-all duration-150" style={{ width: `${confPct}%` }} />
            </div>
          </div>
          <div>
            <p className="text-xs text-slate-500 mb-1.5">Sentiment Breakdown</p>
            <div className="flex gap-1 h-2 rounded-full overflow-hidden">
              <div className="transition-all duration-150" style={{ width: `${(metrics.positive / metrics.total) * 100}%`, background: '#D4A843' }} />
              <div className="transition-all duration-150" style={{ width: `${(metrics.neutral  / metrics.total) * 100}%`, background: '#A8A4B8' }} />
              <div className="transition-all duration-150" style={{ width: `${(metrics.negative / metrics.total) * 100}%`, background: '#F87171' }} />
            </div>
            <div className="flex gap-3 mt-1.5">
              {[
                { label: 'Pos', count: metrics.positive, color: '#D4A843', icon: <TrendingUp size={10} /> },
                { label: 'Neu', count: metrics.neutral,  color: '#A8A4B8', icon: <Minus size={10} /> },
                { label: 'Neg', count: metrics.negative, color: '#F87171', icon: <TrendingDown size={10} /> },
              ].map(s => (
                <span key={s.label} className="flex items-center gap-0.5 text-xs" style={{ color: s.color }}>
                  {s.icon}{s.count}
                </span>
              ))}
              <span className="ml-auto text-xs text-slate-500">{metrics.total} segs</span>
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Tag size={11} className="text-primary shrink-0" />
            <span>Top topic:</span>
            <span className="text-slate-200 font-medium truncate">{metrics.topTopic}</span>
          </div>
        </>
      )}
    </div>
  )
}

// ── Section quick-jumps ───────────────────────────────────────────────────────

const SECTIONS = [
  { label: 'Beginning', startFrac: 0,    endFrac: 0.33 },
  { label: 'Middle',    startFrac: 0.33, endFrac: 0.66 },
  { label: 'End',       startFrac: 0.66, endFrac: 1    },
]

// ── Main ──────────────────────────────────────────────────────────────────────

export default function SegmentScrubber({ datasets, videoUrl, variants, autoCompare, originalUrl, originalLabel }: Props) {
  const [selectedDs, setSelectedDs]       = useState<string>(datasets[0]?.id ?? '')
  const [synced, setSynced]               = useState(false)
  const [rangeA, setRangeA]               = useState<Range>({ start: 0, end: 60 })
  const [rangeB, setRangeB]               = useState<Range>({ start: 0, end: 60 })
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [compareOpen, setCompareOpen]     = useState(autoCompare ?? false)
  const [playing, setPlaying]             = useState(false)
  const [sharedTime, setSharedTime]       = useState(0)
  const [winnerId, setWinnerId]           = useState<string | null>(null)
  const [selectedVariantIdx, setSelectedVariantIdx] = useState(0)
  const variantRefs                       = useRef<(HTMLVideoElement | null)[]>([])
  const originalRef                       = useRef<HTMLVideoElement | null>(null)
  const timelineTrackRef                  = useRef<HTMLDivElement | null>(null)

  // persist winner per project across sessions
  const projectId = variants?.[0]?.project_id ?? null
  useEffect(() => {
    if (!projectId) return
    const stored = localStorage.getItem(`winner:${projectId}`)
    if (stored) setWinnerId(stored)
  }, [projectId])

  const setWinner = useCallback((jobId: string) => {
    setWinnerId(prev => {
      const next = prev === jobId ? null : jobId
      if (projectId) {
        if (next) localStorage.setItem(`winner:${projectId}`, next)
        else localStorage.removeItem(`winner:${projectId}`)
      }
      return next
    })
  }, [projectId])

  const dataset = useMemo(() => datasets.find(d => d.id === selectedDs), [datasets, selectedDs])

  const maxTime = useMemo(() => {
    if (!dataset) return 300
    const times = dataset.segments
      .map(s => parseTimestamp(s.timestamp))
      .filter((t): t is number => t !== null)
    return times.length > 0 ? Math.ceil(Math.max(...times)) + 30 : 300
  }, [dataset])

  const clamp = (r: Range): Range => ({
    start: Math.min(r.start, maxTime - 1),
    end:   Math.min(r.end,   maxTime),
  })

  const handleRangeA = useCallback((r: Range) => {
    setRangeA(r)
    if (synced) setRangeB(r)
    setActiveSection(null)
  }, [synced])

  const handleRangeB = useCallback((r: Range) => {
    setRangeB(r)
    if (synced) setRangeA(r)
    setActiveSection(null)
  }, [synced])

  const toggleSync = () => {
    setSynced(s => {
      if (!s) setRangeB(rangeA)
      return !s
    })
  }

  const applySection = (sec: typeof SECTIONS[0]) => {
    const r: Range = {
      start: Math.round(sec.startFrac * maxTime),
      end:   Math.round(sec.endFrac   * maxTime),
    }
    setRangeA(r)
    setRangeB(r)
    setSynced(true)
    setActiveSection(sec.label)
  }

  const metricsA = useMemo(() => dataset ? computeMetrics(dataset.segments, clamp(rangeA)) : null, [dataset, rangeA, maxTime])
  const metricsB = useMemo(() => dataset ? computeMetrics(dataset.segments, clamp(rangeB)) : null, [dataset, rangeB, maxTime])

  // sort variants by clip_score descending (nulls last), stable
  const sortedVariants = useMemo(() => {
    if (!variants) return []
    return [...variants].sort((a, b) => {
      if (a.clip_score === null && b.clip_score === null) return 0
      if (a.clip_score === null) return 1
      if (b.clip_score === null) return -1
      return b.clip_score - a.clip_score
    })
  }, [variants])

  // build disambiguated labels: "YouTube #1", "YouTube #2" only when platform repeats
  const variantLabels = useMemo(() => {
    const vlist = sortedVariants
    const platformCount: Record<string, number> = {}
    vlist.forEach(v => {
      const key = v.platform ?? '__none__'
      platformCount[key] = (platformCount[key] ?? 0) + 1
    })
    const platformIdx: Record<string, number> = {}
    return vlist.map((v, i) => {
      const key = v.platform ?? '__none__'
      if (platformCount[key] > 1) {
        platformIdx[key] = (platformIdx[key] ?? 0) + 1
        const base = v.platform
          ? v.platform.charAt(0).toUpperCase() + v.platform.slice(1)
          : `Variant ${i + 1}`
        return `${base} #${platformIdx[key]}`
      }
      return v.platform
        ? v.platform.charAt(0).toUpperCase() + v.platform.slice(1)
        : `Variant ${i + 1}`
    })
  }, [sortedVariants])

  const variantDurations = useMemo(() =>
    sortedVariants.map(v =>
      (v.editing_plan?.clips ?? []).reduce((sum, c) => sum + (c.end_time - c.start_time), 0)
    )
  , [sortedVariants])

  const maxVariantDuration = useMemo(() =>
    variantDurations.length > 0 ? Math.max(...variantDurations) : 60
  , [variantDurations])

  const exportReport = useCallback(() => {
    const headers = ['Variant', 'Platform', 'Clip Score', 'Duration (s)', 'Clip Count', 'Top Topic', 'Winner']
    const rows = sortedVariants.map((v, i) => {
      const duration = (v.editing_plan?.clips ?? []).reduce((s, c) => s + (c.end_time - c.start_time), 0)
      const topicCounts: Record<string, number> = {}
      ;(v.editing_plan?.clips ?? []).forEach(c => {
        if (c.topic) topicCounts[c.topic] = (topicCounts[c.topic] ?? 0) + 1
      })
      const topTopic = Object.entries(topicCounts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? ''
      return [
        variantLabels[i],
        v.platform ?? '',
        v.clip_score != null ? `${Math.round(v.clip_score * 100)}%` : '',
        duration > 0 ? Math.round(duration) : '',
        v.editing_plan?.clips?.length ?? 0,
        topTopic,
        winnerId === v.id ? 'Yes' : 'No',
      ]
    })
    const csv = [headers, ...rows]
      .map(r => r.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `variant-report-${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }, [sortedVariants, variantLabels, winnerId])

  const seekAllTo = useCallback((t: number) => {
    setSharedTime(t)
    variantRefs.current.forEach(v => { if (v) v.currentTime = t })
    if (originalRef.current) originalRef.current.currentTime = t
  }, [])

  const togglePlay = useCallback(() => {
    setPlaying(p => {
      const next = !p
      variantRefs.current.forEach(v => { if (!v) return; next ? v.play() : v.pause() })
      if (originalRef.current) next ? originalRef.current.play() : originalRef.current.pause()
      return next
    })
  }, [])

  // Reset selected variant index when variant list changes to avoid out-of-bounds
  useEffect(() => {
    setSelectedVariantIdx(0)
  }, [sortedVariants.length])

  // trim stale refs when variant count changes
  useEffect(() => {
    variantRefs.current = variantRefs.current.slice(0, variants?.length ?? 0)
  }, [variants?.length])

  // sync sharedTime from first video's timeupdate + reset playing on ended
  useEffect(() => {
    const first = variantRefs.current[0]
    if (!first) return
    const onTime  = () => setSharedTime(first.currentTime)
    const onEnded = () => setPlaying(false)
    first.addEventListener('timeupdate', onTime)
    variantRefs.current.forEach(v => v?.addEventListener('ended', onEnded))
    return () => {
      first.removeEventListener('timeupdate', onTime)
      variantRefs.current.forEach(v => v?.removeEventListener('ended', onEnded))
    }
  }, [variants?.length])

  if (datasets.length === 0) {
    return (
      <Card className="flex items-center justify-center py-12">
        <p className="text-slate-500 text-sm">Upload a feedback dataset to use the scrubber.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-4">

      {/* Dataset selector */}
      <select
        value={selectedDs}
        onChange={e => setSelectedDs(e.target.value)}
        className="w-full appearance-none bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-primary"
      >
        {datasets.map(ds => (
          <option key={ds.id} value={ds.id}>
            {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`} ({ds.segment_count} segments)
          </option>
        ))}
      </select>

      {/* Section quick-jump */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-500 shrink-0">Jump to:</span>
        {SECTIONS.map(sec => (
          <button
            key={sec.label}
            onClick={() => applySection(sec)}
            className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors
              ${activeSection === sec.label
                ? 'bg-primary/15 text-primary border-primary/30'
                : 'text-slate-400 border-surface-border hover:text-slate-100 hover:border-slate-500'
              }`}
          >
            {sec.label}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-600">Total: {formatTime(maxTime)}</span>
      </div>

      {/* Sync toggle */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {synced ? 'Ranges are synced — drag either slider to move both.' : 'Ranges are independent — drag each slider separately.'}
        </p>
        <button
          onClick={toggleSync}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors
            ${synced
              ? 'bg-primary/15 text-primary border-primary/30'
              : 'text-slate-400 border-surface-border hover:text-slate-100'
            }`}
        >
          {synced ? <Link2 size={12} /> : <Link2Off size={12} />}
          {synced ? 'Synced' : 'Sync Ranges'}
        </button>
      </div>

      {/* Range cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* Range A */}
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-indigo-400 uppercase tracking-wide">Range A</span>
            <span className="text-xs text-slate-500 font-mono">
              {formatTime(clamp(rangeA).start)} → {formatTime(clamp(rangeA).end)}
              <span className="ml-1 text-slate-600">({formatTime(clamp(rangeA).end - clamp(rangeA).start)})</span>
            </span>
          </div>
          {videoUrl && <VideoPreview src={videoUrl} seekTo={clamp(rangeA).start} />}
          <RangeSlider min={0} max={maxTime} range={clamp(rangeA)} color="#6366f1" onChange={handleRangeA} />
          {metricsA && <MetricsPanel metrics={metricsA} label="Range A Metrics" color="#6366f1" />}
        </Card>

        {/* Range B */}
        <Card className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wide">Range B</span>
            <span className="text-xs text-slate-500 font-mono">
              {formatTime(clamp(rangeB).start)} → {formatTime(clamp(rangeB).end)}
              <span className="ml-1 text-slate-600">({formatTime(clamp(rangeB).end - clamp(rangeB).start)})</span>
            </span>
          </div>
          {videoUrl && <VideoPreview src={videoUrl} seekTo={clamp(rangeB).start} />}
          <RangeSlider min={0} max={maxTime} range={clamp(rangeB)} color="#10b981" onChange={handleRangeB} />
          {metricsB && <MetricsPanel metrics={metricsB} label="Range B Metrics" color="#10b981" />}
        </Card>
      </div>

      {/* Variants ready indicator + Compare button */}
      {variants && variants.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-primary/10 border border-primary/20 flex-wrap">
          <span className="text-xs text-primary font-medium">
            {variants.length} generated variant{variants.length !== 1 ? 's' : ''} available
          </span>
          <span className="text-xs text-slate-500">— scrub the ranges above to explore engagement</span>
          {winnerId && (() => {
            const wi = sortedVariants.findIndex(v => v.id === winnerId)
            return wi !== -1 ? (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-yellow-400/15 text-yellow-400 border border-yellow-400/30 font-medium">
                <Trophy size={10} /> {variantLabels[wi]}
              </span>
            ) : null
          })()}
          {variants.length >= 1 && (
            <button
              onClick={() => setCompareOpen(true)}
              className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-white hover:bg-primary/80 transition-colors"
            >
              <GitCompare size={12} />
              {variants.length === 1 ? 'Inspect Variant' : 'Compare Variants'}
            </button>
          )}
        </div>
      )}

      {/* Comparison table */}
      {metricsA && metricsB && metricsA.total > 0 && metricsB.total > 0 && (
        <Card>
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-3">Range Comparison</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-slate-300">
              <thead>
                <tr className="text-slate-500 border-b border-surface-border">
                  <th className="text-left pb-2 font-medium">Metric</th>
                  <th className="text-center pb-2 font-medium text-indigo-400">Range A</th>
                  <th className="text-center pb-2 font-medium text-emerald-400">Range B</th>
                  <th className="text-center pb-2 font-medium">Winner</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border/50">
                {[
                  { label: 'Engagement',        a: `${Math.round(metricsA.engagementScore * 100)}%`, b: `${Math.round(metricsB.engagementScore * 100)}%`, aVal: metricsA.engagementScore, bVal: metricsB.engagementScore },
                  { label: 'Avg Confidence',    a: `${Math.round(metricsA.avgConfidence * 100)}%`,   b: `${Math.round(metricsB.avgConfidence * 100)}%`,   aVal: metricsA.avgConfidence,   bVal: metricsB.avgConfidence },
                  { label: 'Positive Segments', a: metricsA.positive,                                b: metricsB.positive,                                aVal: metricsA.positive,        bVal: metricsB.positive },
                  { label: 'Segment Count',     a: metricsA.total,                                   b: metricsB.total,                                   aVal: metricsA.total,           bVal: metricsB.total },
                ].map(row => {
                  const winner = row.aVal > row.bVal ? 'A' : row.bVal > row.aVal ? 'B' : '='
                  return (
                    <tr key={row.label}>
                      <td className="py-2 text-slate-500">{row.label}</td>
                      <td className={`py-2 text-center font-mono ${winner === 'A' ? 'text-indigo-300 font-semibold' : ''}`}>{row.a}</td>
                      <td className={`py-2 text-center font-mono ${winner === 'B' ? 'text-emerald-300 font-semibold' : ''}`}>{row.b}</td>
                      <td className="py-2 text-center">
                        {winner === '='
                          ? <span className="text-slate-600">—</span>
                          : <span className={`px-1.5 py-0.5 rounded text-xs font-bold ${winner === 'A' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-emerald-500/20 text-emerald-300'}`}>{winner}</span>
                        }
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── Compare Variants fullscreen overlay ──────────────────────────── */}
      <div className={`fixed inset-0 z-50 bg-[#0a0f1a] flex flex-col ${
        compareOpen ? '' : 'hidden'
      }`}>
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800 shrink-0">
            <div className="flex items-center gap-2">
              <GitCompare size={15} className="text-primary" />
              <div>
                <span className="text-sm font-semibold text-slate-100">
                  {originalUrl ? 'Original vs ClipSense' : 'Variant Comparison Editor'}
                </span>
                {originalUrl && (
                  <p className="text-xs text-slate-500 leading-none mt-0.5">
                    Compare the baseline trailer with AI-selected versions.
                  </p>
                )}
              </div>
              {!originalUrl && (
                <span className="text-xs text-slate-500 ml-1">— {sortedVariants.length} variants</span>
              )}
              {winnerId && (() => {
                const w = (variants ?? []).find(v => v.id === winnerId)
                return w ? (
                  <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-yellow-400/15 text-yellow-400 border border-yellow-400/30 ml-2">
                    <Trophy size={11} /> Winner: {variantLabels[sortedVariants.indexOf(w)]}
                  </span>
                ) : null
              })()}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={exportReport}
                className="flex items-center gap-1.5 text-slate-400 hover:text-green-400 text-xs px-3 py-1.5 rounded-lg border border-slate-700 hover:border-green-500/40 transition-colors"
              >
                <Download size={12} /> Export CSV
              </button>
              <button
                onClick={() => setCompareOpen(false)}
                className="flex items-center gap-1.5 text-slate-400 hover:text-white text-xs px-3 py-1.5 rounded-lg border border-slate-700 hover:border-slate-500 transition-colors"
              >
                <X size={12} /> Close
              </button>
            </div>
          </div>

          {/* Video area — original baseline + AI variants */}
          <div className="flex-1 overflow-y-auto p-4">
            {originalUrl ? (
              // ── Original vs AI layout: large left + right panel ──────────
              <div className="flex flex-col lg:flex-row gap-4 h-full">

                {/* Left — Original baseline */}
                <div className="flex flex-col gap-2 lg:w-1/2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">
                      {originalLabel ?? 'Original'}
                    </span>
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-400 border border-slate-600">
                      Baseline
                    </span>
                    <span className="text-xs text-slate-600 ml-auto">No AI score</span>
                  </div>
                  <video
                    ref={el => { originalRef.current = el }}
                    src={originalUrl}
                    className="w-full rounded-xl aspect-video object-contain bg-black"
                    preload="metadata"
                    muted
                    playsInline
                  />
                </div>

                {/* Right — AI Generated (selected variant + selector) */}
                <div className="flex flex-col gap-2 lg:w-1/2">
                  {/* Variant selector tabs */}
                  {sortedVariants.length > 1 && (
                    <div className="flex gap-1 flex-wrap">
                      {sortedVariants.map((v, i) => (
                        <button
                          key={v.id}
                          onClick={() => setSelectedVariantIdx(i)}
                          className={`text-xs px-2.5 py-1 rounded-lg border transition-colors ${
                            selectedVariantIdx === i
                              ? 'bg-primary/15 text-primary border-primary/30'
                              : 'text-slate-500 border-slate-700 hover:text-slate-300 hover:border-slate-500'
                          }`}
                        >
                          {variantLabels[i]}
                          {v.clip_score != null && (
                            <span className="ml-1.5 font-mono opacity-70">{Math.round(v.clip_score * 100)}%</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}

                  {/* Selected AI variant */}
                  {sortedVariants[selectedVariantIdx] && (() => {
                    const v = sortedVariants[selectedVariantIdx]
                    const isWinner = winnerId === v.id
                    return (
                      <>
                        <div className="flex items-center gap-2">
                          {isWinner && <Trophy size={12} className="text-yellow-400 shrink-0" />}
                          <span className={`text-xs font-semibold uppercase tracking-wide ${
                            isWinner ? 'text-yellow-300' : 'text-slate-300'
                          }`}>
                            {variantLabels[selectedVariantIdx]}
                          </span>
                          <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/30">
                            AI Generated
                          </span>
                          {v.clip_score != null && (
                            <span className="text-xs text-primary font-mono ml-auto">{Math.round(v.clip_score * 100)}%</span>
                          )}
                          <button
                            onClick={() => setWinner(v.id)}
                            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${
                              isWinner
                                ? 'bg-yellow-400/15 text-yellow-400 border-yellow-400/40'
                                : 'text-slate-500 border-slate-700 hover:text-yellow-400 hover:border-yellow-400/40'
                            }`}
                          >
                            <Trophy size={11} />{isWinner ? 'Unset' : 'Set as Winner'}
                          </button>
                        </div>
                        <video
                          ref={el => { variantRefs.current[selectedVariantIdx] = el }}
                          src={trailerService.trailerUrl(v.output_url!)}
                          className="w-full rounded-xl aspect-video object-contain bg-black"
                          preload="metadata"
                          muted
                          playsInline
                        />
                        {/* Clip sentiment strip */}
                        {v.editing_plan && v.editing_plan.clips.length > 0 && (() => {
                          const total = v.editing_plan.clips.reduce((s, c) => s + (c.end_time - c.start_time), 0)
                          return (
                            <div className="flex h-2 rounded-full overflow-hidden gap-px" title="AI clip sentiment timeline">
                              {v.editing_plan.clips.map((c, ci) => {
                                const w = total > 0 ? ((c.end_time - c.start_time) / total) * 100 : 0
                                const bg = SENTIMENT_POS.has(c.sentiment) ? '#D4A843'
                                  : SENTIMENT_NEG.has(c.sentiment) ? '#F87171' : '#A8A4B8'
                                return (
                                  <div key={ci} className="h-full" style={{ width: `${w}%`, background: bg }}
                                    title={`${c.topic} · ${c.sentiment} · ${Math.round(c.end_time - c.start_time)}s`} />
                                )
                              })}
                            </div>
                          )
                        })()}
                      </>
                    )
                  })()}
                </div>
              </div>
            ) : (
              // Standard multi-variant grid (no original)
              <div className={`grid gap-4 ${
                sortedVariants.length <= 2 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-2 xl:grid-cols-3'
              }`}>
                {sortedVariants.map((v, i) => {
                  const isWinner = winnerId === v.id
                  return (
                    <div
                      key={v.id}
                      className={`flex flex-col gap-2 rounded-xl p-2 border-2 transition-colors ${
                        isWinner ? 'border-yellow-400/70 bg-yellow-400/5' : 'border-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-1.5">
                          {isWinner && <Trophy size={13} className="text-yellow-400 shrink-0" />}
                          <span className={`text-xs font-semibold uppercase tracking-wide ${
                            isWinner ? 'text-yellow-300' : 'text-slate-300'
                          }`}>
                            {variantLabels[i]}
                          </span>
                          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/30">
                            AI Generated
                          </span>
                          {isWinner && (
                            <span className="text-xs px-1.5 py-0.5 rounded-full bg-yellow-400/15 text-yellow-400 border border-yellow-400/30 font-medium">Winner</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          {v.clip_score != null && (
                            <span className="text-xs text-primary font-mono">{Math.round(v.clip_score * 100)}%</span>
                          )}
                          <button
                            onClick={() => setWinner(v.id)}
                            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${
                              isWinner
                                ? 'bg-yellow-400/15 text-yellow-400 border-yellow-400/40 hover:bg-yellow-400/25'
                                : 'text-slate-500 border-slate-700 hover:text-yellow-400 hover:border-yellow-400/40'
                            }`}
                          >
                            <Trophy size={11} />
                            {isWinner ? 'Unset' : 'Set as Winner'}
                          </button>
                        </div>
                      </div>
                      <video
                        ref={el => { variantRefs.current[i] = el }}
                        src={trailerService.trailerUrl(v.output_url!)}
                        className="w-full rounded-lg aspect-video object-contain bg-black"
                        preload="metadata"
                        muted
                        playsInline
                      />
                      {v.editing_plan && v.editing_plan.clips.length > 0 && (() => {
                        const total = v.editing_plan.clips.reduce((s, c) => s + (c.end_time - c.start_time), 0)
                        return (
                          <div className="flex h-2 rounded-full overflow-hidden gap-px" title="Clip sentiment timeline">
                            {v.editing_plan.clips.map((c, ci) => {
                              const w = total > 0 ? ((c.end_time - c.start_time) / total) * 100 : 0
                              const bg = SENTIMENT_POS.has(c.sentiment) ? '#D4A843'
                                : SENTIMENT_NEG.has(c.sentiment) ? '#F87171' : '#A8A4B8'
                              return (
                                <div key={ci} className="h-full" style={{ width: `${w}%`, background: bg }}
                                  title={`${c.topic} · ${c.sentiment} · ${Math.round(c.end_time - c.start_time)}s`} />
                              )
                            })}
                          </div>
                        )
                      })()}
                    </div>
                  )
                })}
              </div>
            )}
          </div>


          {/* Per-variant metrics table */}
          <div className="shrink-0 border-t border-slate-800 overflow-x-auto">
            <table className="w-full text-xs text-slate-300 min-w-max">
              <thead>
                <tr className="text-slate-500 border-b border-slate-800">
                  <th className="text-left px-4 py-2 font-medium">Metric</th>
                  {sortedVariants.map((v, i) => (
                    <th key={v.id} className="text-center px-4 py-2 font-medium text-slate-300">
                      {variantLabels[i]}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {(() => {
                  const vlist = sortedVariants
                  const durations = vlist.map(v =>
                    (v.editing_plan?.clips ?? []).reduce((s, c) => s + (c.end_time - c.start_time), 0)
                  )
                  const clipCounts = vlist.map(v => v.editing_plan?.clips?.length ?? 0)
                  const scores     = vlist.map(v => v.clip_score ?? 0)
                  const topTopics  = vlist.map(v => {
                    const counts: Record<string, number> = {}
                    ;(v.editing_plan?.clips ?? []).forEach(c => {
                      if (c.topic) counts[c.topic] = (counts[c.topic] ?? 0) + 1
                    })
                    return Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? '—'
                  })

                  const bestIdx = (arr: number[]) => {
                    const max = Math.max(...arr)
                    return arr.map(v => v === max && max > 0)
                  }

                  const rows: { label: string; values: (string | number)[]; best: boolean[] }[] = [
                    { label: 'Clip Score',  values: scores.map(s => s > 0 ? `${Math.round(s * 100)}%` : '—'),        best: bestIdx(scores) },
                    { label: 'Duration',    values: durations.map(d => d > 0 ? formatTime(Math.round(d)) : '—'), best: bestIdx(durations) },
                    { label: 'Clip Count',  values: clipCounts,                                                  best: bestIdx(clipCounts) },
                    { label: 'Top Topic',   values: topTopics,                                                   best: topTopics.map(() => false) },
                    { label: 'Selected',    values: vlist.map(v => winnerId === v.id ? '🏆' : '—'),              best: vlist.map(() => false) },
                  ]

                  return rows.map(row => (
                    <tr key={row.label} className={row.label === 'Selected' ? 'border-t-2 border-slate-700' : ''}>
                      <td className={`px-4 py-2 ${ row.label === 'Selected' ? 'text-yellow-400 font-medium' : 'text-slate-500'}`}>{row.label}</td>
                      {row.values.map((val, i) => (
                        <td key={i} className={`px-4 py-2 text-center font-mono ${
                          row.best[i] ? 'text-primary font-semibold' : ''
                        }`}>
                          {row.best[i] && <span className="mr-1 text-primary">★</span>}
                          {val}
                        </td>
                      ))}
                    </tr>
                  ))
                })()}
              </tbody>
            </table>
          </div>

          {/* Shared timeline controls */}
          <div className="shrink-0 px-6 py-3 border-t border-slate-800 flex flex-col gap-2">
            {/* Engagement heatmap band */}
            {dataset && (() => {
              const BUCKETS = 50
              const buckets = Array.from({ length: BUCKETS }, (_, bi) => {
                const bStart = (bi / BUCKETS) * maxVariantDuration
                const bEnd   = ((bi + 1) / BUCKETS) * maxVariantDuration
                const segs = dataset.segments.filter(s => {
                  const t = parseTimestamp(s.timestamp)
                  return t !== null && t >= bStart && t < bEnd
                })
                if (segs.length === 0) return 0
                const pos = segs.filter(s => SENTIMENT_POS.has(s.sentiment)).length
                const neg = segs.filter(s => SENTIMENT_NEG.has(s.sentiment)).length
                return (pos - neg) / segs.length
              })
              // Check if AI variants have any positive clips to decide annotation
              const aiHasPositive = sortedVariants.some(v =>
                (v.editing_plan?.clips ?? []).some(c => SENTIMENT_POS.has(c.sentiment))
              )
              return (
                <div className="space-y-1">
                  <p className="text-[10px] text-slate-600">
                    {originalUrl && aiHasPositive
                      ? 'AI version prioritizes audience-positive segments'
                      : 'Audience sentiment by timeline'
                    }
                  </p>
                  <div className="flex h-1.5 rounded-full overflow-hidden gap-px" title="Engagement heatmap from dataset segments">
                    {buckets.map((score, bi) => {
                      const bg = score > 0.2 ? '#D4A843' : score < -0.2 ? '#F87171' : '#A8A4B8'
                      return <div key={bi} className="flex-1 h-full opacity-80" style={{ background: bg }} />
                    })}
                  </div>
                </div>
              )
            })()}
            <div className="flex items-center gap-4">
            <button
              onClick={togglePlay}
              className="flex items-center justify-center w-8 h-8 rounded-full bg-primary hover:bg-primary/80 transition-colors shrink-0"
            >
              {playing ? <Pause size={14} className="text-white" /> : <Play size={14} className="text-white" />}
            </button>
            <span className="text-xs font-mono text-slate-400 shrink-0 w-10 text-right">{formatTime(Math.round(sharedTime))}</span>
            <div
              className="relative flex-1 h-5 flex items-center cursor-pointer select-none"
              ref={el => { timelineTrackRef.current = el }}
              onMouseDown={e => {
                const el = timelineTrackRef.current
                if (!el) return
                const seek = (ev: MouseEvent) => {
                  const rect = el.getBoundingClientRect()
                  const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
                  seekAllTo(ratio * maxVariantDuration)
                }
                seek(e.nativeEvent)
                const onUp = () => {
                  window.removeEventListener('mousemove', seek)
                  window.removeEventListener('mouseup', onUp)
                }
                window.addEventListener('mousemove', seek)
                window.addEventListener('mouseup', onUp)
              }}
            >
              <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-700" />
              <div
                className="absolute h-1.5 rounded-full bg-primary"
                style={{ width: `${maxVariantDuration > 0 ? (sharedTime / maxVariantDuration) * 100 : 0}%` }}
              />
              <div
                className="absolute w-3.5 h-3.5 rounded-full bg-white border-2 border-primary shadow -translate-x-1/2"
                style={{ left: `${maxVariantDuration > 0 ? (sharedTime / maxVariantDuration) * 100 : 0}%` }}
              />
            </div>
            <span className="text-xs font-mono text-slate-600 shrink-0 w-10">{formatTime(Math.round(maxVariantDuration))}</span>
            </div>
          </div>
        </div>

    </div>
  )
}
