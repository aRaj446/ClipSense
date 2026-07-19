import { useState, useMemo, useCallback, useRef, useEffect } from 'react'
import { Link2, Link2Off, TrendingUp, TrendingDown, Minus, Activity, Tag, BarChart2, ChevronRight, ChevronDown, Film, Database, Loader2, Play, Pause, Sparkles, Clapperboard, MessageSquare } from 'lucide-react'
import { Project } from '../types/project'
import { StoredDataset, StoredSegment, TrailerJob, SmartTrailerJob } from '../types/analysis'
import { projectService } from '../services/projectService'
import { feedbackService } from '../services/feedbackService'
import { trailerService } from '../services/trailerService'
import { smartTrailerService } from '../services/smartTrailerService'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Range { start: number; end: number }

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

interface ProjectWithDatasets extends Project {
  datasets: StoredDataset[]
  loadingDatasets: boolean
  trailers: TrailerJob[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const SENTIMENT_POS = new Set(['Positive', 'Praise'])
const SENTIMENT_NEG = new Set(['Negative', 'Complaint'])

function parseTimestamp(ts: string | null): number | null {
  if (!ts) return null
  const parts = ts.split(':').map(Number)
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  return null
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
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

// ── RangeSlider ───────────────────────────────────────────────────────────────

interface SliderProps { min: number; max: number; range: Range; color: string; onChange: (r: Range) => void }

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
      if (dragging.current === 'start') onChange({ start: Math.min(val, range.end - 1), end: range.end })
      else onChange({ start: range.start, end: Math.max(val, range.start + 1) })
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
      <div className="absolute w-4 h-4 rounded-full border-2 border-white shadow-md cursor-grab active:cursor-grabbing z-10 -translate-x-1/2" style={{ left: `${startPct}%`, background: color }} onMouseDown={onMouseDown('start')} />
      <div className="absolute w-4 h-4 rounded-full border-2 border-white shadow-md cursor-grab active:cursor-grabbing z-10 -translate-x-1/2" style={{ left: `${endPct}%`, background: color }} onMouseDown={onMouseDown('end')} />
    </div>
  )
}

// ── MetricsPanel ──────────────────────────────────────────────────────────────

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
              <div className="bg-green-500 transition-all duration-150" style={{ width: `${(metrics.positive / metrics.total) * 100}%` }} />
              <div className="bg-slate-500 transition-all duration-150" style={{ width: `${(metrics.neutral  / metrics.total) * 100}%` }} />
              <div className="bg-red-500   transition-all duration-150" style={{ width: `${(metrics.negative / metrics.total) * 100}%` }} />
            </div>
            <div className="flex gap-3 mt-1.5">
              {[
                { label: 'Pos', count: metrics.positive, cls: 'text-green-400', icon: <TrendingUp size={10} /> },
                { label: 'Neu', count: metrics.neutral,  cls: 'text-slate-400', icon: <Minus size={10} /> },
                { label: 'Neg', count: metrics.negative, cls: 'text-red-400',   icon: <TrendingDown size={10} /> },
              ].map(s => (
                <span key={s.label} className={`flex items-center gap-0.5 text-xs ${s.cls}`}>
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

// ── ScrubberPage ──────────────────────────────────────────────────────────────

export default function ScrubberPage() {
  const [projects, setProjects]               = useState<ProjectWithDatasets[]>([])
  const [loading, setLoading]                 = useState(true)
  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [selectedDs, setSelectedDs]           = useState<StoredDataset | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [sidebarMode, setSidebarMode]           = useState<'standard' | 'smart'>('standard')
  const [smartJobs, setSmartJobs]               = useState<SmartTrailerJob[]>([])
  const [expandedSmartJob, setExpandedSmartJob] = useState<string | null>(null)
  const [selectedSmartJob, setSelectedSmartJob] = useState<SmartTrailerJob | null>(null)
  const [smartSegments, setSmartSegments]       = useState<StoredSegment[] | null>(null)
  const [smartSegmentsLoading, setSmartSegmentsLoading] = useState(false)

  const [synced, setSynced]               = useState(false)
  const [rangeA, setRangeA]               = useState<Range>({ start: 0, end: 60 })
  const [rangeB, setRangeB]               = useState<Range>({ start: 0, end: 60 })
  const [activeSection, setActiveSection] = useState<string | null>(null)

  // variant video playback
  const [playing, setPlaying]   = useState(false)
  const [sharedTime, setSharedTime] = useState(0)
  const variantRefs = useRef<(HTMLVideoElement | null)[]>([])
  const timelineRef = useRef<HTMLDivElement | null>(null)

  // load all projects + smart jobs on mount
  useEffect(() => {
    projectService.listProjects()
      .then(projs => setProjects(projs.map(p => ({ ...p, datasets: [], loadingDatasets: false, trailers: [] }))))
      .catch(() => {})
      .finally(() => setLoading(false))
    smartTrailerService.listJobs()
      .then(jobs => setSmartJobs(jobs.filter(j => j.status === 'done')))
      .catch(() => {})
  }, [])

  // lazy-load datasets + trailers when a project is expanded
  useEffect(() => {
    if (!expandedProject) return
    setProjects(prev => prev.map(p => {
      if (p.id !== expandedProject || p.datasets.length > 0 || p.loadingDatasets) return p
      Promise.all([
        feedbackService.listDatasets(p.id),
        trailerService.listJobs(p.id),
      ]).then(([datasets, trailers]) => {
        setProjects(curr => curr.map(cp =>
          cp.id === p.id ? { ...cp, datasets, trailers: trailers.filter(j => j.status === 'done' && j.output_url), loadingDatasets: false } : cp
        ))
      }).catch(() => {
        setProjects(curr => curr.map(cp => cp.id === p.id ? { ...cp, loadingDatasets: false } : cp))
      })
      return { ...p, loadingDatasets: true }
    }))
  }, [expandedProject])

  // fetch segments for selected smart job and build a synthetic dataset
  useEffect(() => {
    if (!selectedSmartJob) { setSmartSegments(null); return }
    setSmartSegmentsLoading(true)
    smartTrailerService.getAnalytics(selectedSmartJob.id)
      .then(report => {
        const segs: StoredSegment[] = report.timeline.map((pt, i) => ({
          id: String(i),
          position: i,
          timestamp: pt.timestamp,
          topic: pt.topic,
          sentiment: pt.sentiment,
          summary: pt.summary,
          confidence: pt.confidence,
          created_at: report.analyzed_at,
        }))
        setSmartSegments(segs)
      })
      .catch(() => setSmartSegments([]))
      .finally(() => setSmartSegmentsLoading(false))
  }, [selectedSmartJob?.id])

  // synthetic dataset built from smart segments — drives the scrubber
  const smartDataset = useMemo<StoredDataset | null>(() => {
    if (!selectedSmartJob || !smartSegments) return null
    return {
      id: selectedSmartJob.id,
      project_id: '',
      name: selectedSmartJob.comments_name,
      source: 'smart',
      created_at: selectedSmartJob.created_at,
      segment_count: smartSegments.length,
      segments: smartSegments,
    }
  }, [selectedSmartJob, smartSegments])


  const activeDataset = sidebarMode === 'smart' ? smartDataset : selectedDs

  const maxTime = useMemo(() => {
    if (!activeDataset) return 300
    const times = activeDataset.segments
      .map(s => parseTimestamp(s.timestamp))
      .filter((t): t is number => t !== null)
    return times.length > 0 ? Math.ceil(Math.max(...times)) + 30 : 300
  }, [activeDataset])

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

  const metricsA = useMemo(() => activeDataset ? computeMetrics(activeDataset.segments, clamp(rangeA)) : null, [activeDataset, rangeA, maxTime])
  const metricsB = useMemo(() => activeDataset ? computeMetrics(activeDataset.segments, clamp(rangeB)) : null, [activeDataset, rangeB, maxTime])

  // reset ranges when dataset changes
  useEffect(() => {
    setRangeA({ start: 0, end: Math.min(60, maxTime) })
    setRangeB({ start: 0, end: Math.min(60, maxTime) })
    setSynced(false)
    setActiveSection(null)
    setPlaying(false)
    setSharedTime(0)
  }, [activeDataset?.id])

  const selectedProject = useMemo(
    () => projects.find(p => p.id === selectedProjectId),
    [projects, selectedProjectId]
  )
  const variants = useMemo(() => {
    if (sidebarMode === 'smart' || !selectedDs) return []
    return (selectedProject?.trailers ?? []).filter(v => v.dataset_id === selectedDs.id)
  }, [sidebarMode, selectedProject, selectedDs])
  const maxVariantDuration = useMemo(() =>
    variants.reduce((max, v) => {
      const dur = (v.editing_plan?.clips ?? []).reduce((s, c) => s + (c.end_time - c.start_time), 0)
      return Math.max(max, dur)
    }, 60)
  , [variants])

  const seekAllTo = useCallback((t: number) => {
    setSharedTime(t)
    variantRefs.current.forEach(v => { if (v) v.currentTime = t })
  }, [])

  const togglePlay = useCallback(() => {
    setPlaying(p => {
      const next = !p
      variantRefs.current.forEach(v => { if (!v) return; next ? v.play() : v.pause() })
      return next
    })
  }, [])

  useEffect(() => {
    variantRefs.current = variantRefs.current.slice(0, variants.length)
  }, [variants.length])

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
  }, [variants.length])

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <LoadingSpinner size={36} />
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto flex gap-6 h-[calc(100vh-80px)]">

      {/* ── Left panel — project + dataset tree ──────────────────────────── */}
      <div className="w-64 shrink-0 flex flex-col gap-2 overflow-y-auto pr-1">
        <div className="flex items-center gap-2 mb-1 px-1">
          <Film size={15} className="text-primary" />
          <h1 className="text-sm font-semibold text-slate-100">Select Dataset</h1>
        </div>

        {/* Standard / Smart toggle */}
        <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-lg mb-1">
          <button
            onClick={() => setSidebarMode('standard')}
            className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
              sidebarMode === 'standard' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Clapperboard size={11} /> Standard
          </button>
          <button
            onClick={() => setSidebarMode('smart')}
            className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
              sidebarMode === 'smart' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Sparkles size={11} /> Smart
          </button>
        </div>

        {/* Standard: project → dataset tree */}
        {sidebarMode === 'standard' && (
          projects.length === 0 ? (
            <Card className="py-10 text-center">
              <Film size={32} className="text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">No projects yet.</p>
            </Card>
          ) : (
            projects.map(project => {
              const isExpanded = expandedProject === project.id
              return (
                <div key={project.id} className="rounded-lg border border-surface-border overflow-hidden">
                  <button
                    onClick={() => setExpandedProject(isExpanded ? null : project.id)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 bg-surface hover:bg-surface-card transition-colors text-left"
                    onClickCapture={() => { if (!isExpanded) setSelectedProjectId(project.id) }}
                  >
                    {isExpanded
                      ? <ChevronDown size={13} className="text-slate-400 shrink-0" />
                      : <ChevronRight size={13} className="text-slate-400 shrink-0" />
                    }
                    <Film size={13} className="text-primary shrink-0" />
                    <span className="text-slate-200 text-xs font-medium truncate flex-1">{project.filename}</span>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-surface-border bg-surface/50">
                      {project.loadingDatasets ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 size={14} className="text-slate-500 animate-spin" />
                        </div>
                      ) : project.datasets.length === 0 ? (
                        <p className="text-xs text-slate-600 px-4 py-3 italic">No datasets uploaded.</p>
                      ) : (
                        project.datasets.map(ds => {
                          const isSelected = selectedDs?.id === ds.id
                          return (
                            <button
                              key={ds.id}
                              onClick={() => { setSelectedDs(ds); setSelectedProjectId(project.id) }}
                              className={`w-full flex items-center gap-2 px-4 py-2 text-left transition-colors border-b border-surface-border/50 last:border-0 ${
                                isSelected
                                  ? 'bg-primary/10 text-primary'
                                  : 'text-slate-400 hover:bg-surface-card hover:text-slate-200'
                              }`}
                            >
                              <Database size={11} className="shrink-0" />
                              <span className="text-xs truncate flex-1">{ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`}</span>
                              <span className="text-xs opacity-60 shrink-0">{ds.segment_count}s</span>
                            </button>
                          )
                        })
                      )}
                    </div>
                  )}
                </div>
              )
            })
          )
        )}

        {/* Smart: generated trailer → comments dataset tree */}
        {sidebarMode === 'smart' && (
          smartJobs.length === 0 ? (
            <Card className="py-10 text-center">
              <Sparkles size={32} className="text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">No smart trailers yet.</p>
            </Card>
          ) : (
            smartJobs.map(job => {
              const isExpanded = expandedSmartJob === job.id
              const isDatasetSelected = selectedSmartJob?.id === job.id
              return (
                <div key={job.id} className="rounded-lg border border-surface-border overflow-hidden">
                  <button
                    onClick={() => setExpandedSmartJob(isExpanded ? null : job.id)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 bg-surface hover:bg-surface-card transition-colors text-left"
                  >
                    {isExpanded
                      ? <ChevronDown size={13} className="text-slate-400 shrink-0" />
                      : <ChevronRight size={13} className="text-slate-400 shrink-0" />
                    }
                    <Sparkles size={13} className="text-primary shrink-0" />
                    <span className="text-slate-200 text-xs font-medium truncate flex-1">{job.raw_footage_name}</span>
                    {job.clip_score != null && (
                      <span className="text-[10px] text-yellow-400 font-mono shrink-0">{Math.round(job.clip_score * 100)}%</span>
                    )}
                  </button>
                  {isExpanded && (
                    <div className="border-t border-surface-border bg-surface/50">
                      <button
                        onClick={() => setSelectedSmartJob(job)}
                        className={`w-full flex items-center gap-2 px-4 py-2 text-left transition-colors ${
                          isDatasetSelected ? 'bg-primary/10 text-primary' : 'text-slate-400 hover:bg-surface-card hover:text-slate-200'
                        }`}
                      >
                        <MessageSquare size={11} className="shrink-0" />
                        <span className="text-xs truncate flex-1">{job.comments_name}</span>
                        <span className="text-xs opacity-60 shrink-0">{job.editing_plan?.clips.length ?? 0} clips</span>
                      </button>
                    </div>
                  )}
                </div>
              )
            })
          )
        )}
      </div>

      {/* ── Right panel — scrubber ────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {!activeDataset ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            {sidebarMode === 'smart' ? (
              <>
                {smartSegmentsLoading
                  ? <LoadingSpinner size={36} />
                  : <>
                      <Sparkles size={48} className="text-slate-700" />
                      <p className="text-slate-400 font-medium">Select a smart trailer's dataset to start scrubbing</p>
                      <p className="text-slate-600 text-sm">Expand a smart trailer on the left and click the comments dataset.</p>
                    </>
                }
              </>
            ) : (
              <>
                <Film size={48} className="text-slate-700" />
                <p className="text-slate-400 font-medium">Select a dataset to start scrubbing</p>
                <p className="text-slate-600 text-sm">Expand a project on the left and click any dataset.</p>
              </>
            )}
          </div>
        ) : variants.length < 2 ? (
          <div className="flex flex-col items-center justify-center h-full text-center gap-4">
            <Film size={48} className="text-slate-700" />
            <p className="text-slate-400 font-medium">No variants to compare yet</p>
            <p className="text-slate-600 text-sm">Generate at least 2 trailers from this dataset to use the scrubber.</p>
          </div>
        ) : (
          <div className="space-y-4">

            {/* Dataset label */}
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Database size={12} className="text-primary" />
              <span className="text-slate-300 font-medium">{activeDataset.name ?? `Dataset ${activeDataset.id.slice(0, 8)}…`}</span>
              <span className="text-slate-600">· {activeDataset.segment_count} segments · {formatTime(maxTime)} total</span>
            </div>

            {/* Section quick-jump */}
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-slate-500 shrink-0">Jump to:</span>
              {SECTIONS.map(sec => (
                <button
                  key={sec.label}
                  onClick={() => applySection(sec)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium border transition-colors ${
                    activeSection === sec.label
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
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                  synced
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
                <RangeSlider min={0} max={maxTime} range={clamp(rangeB)} color="#10b981" onChange={handleRangeB} />
                {metricsB && <MetricsPanel metrics={metricsB} label="Range B Metrics" color="#10b981" />}
              </Card>
            </div>

            {/* Range Comparison table */}
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

            {/* Segment lists */}
            {(metricsA?.total ?? 0) > 0 || (metricsB?.total ?? 0) > 0 ? (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {metricsA && metricsA.total > 0 && (
                  <Card>
                    <p className="text-xs font-semibold text-indigo-400 uppercase tracking-wide mb-3">Range A — Segments</p>
                    <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                      {metricsA.segments.map(seg => (
                        <div key={seg.id} className="flex items-start gap-2 text-xs py-1 border-b border-surface-border/40 last:border-0">
                          <span className="text-slate-600 font-mono shrink-0 w-10">{seg.timestamp ?? '—'}</span>
                          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            SENTIMENT_POS.has(seg.sentiment) ? 'bg-green-500/15 text-green-400' :
                            SENTIMENT_NEG.has(seg.sentiment) ? 'bg-red-500/15 text-red-400' :
                            'bg-slate-500/15 text-slate-400'
                          }`}>{seg.sentiment}</span>
                          <span className="text-slate-400 truncate flex-1">{seg.summary}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
                {metricsB && metricsB.total > 0 && (
                  <Card>
                    <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wide mb-3">Range B — Segments</p>
                    <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
                      {metricsB.segments.map(seg => (
                        <div key={seg.id} className="flex items-start gap-2 text-xs py-1 border-b border-surface-border/40 last:border-0">
                          <span className="text-slate-600 font-mono shrink-0 w-10">{seg.timestamp ?? '—'}</span>
                          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            SENTIMENT_POS.has(seg.sentiment) ? 'bg-green-500/15 text-green-400' :
                            SENTIMENT_NEG.has(seg.sentiment) ? 'bg-red-500/15 text-red-400' :
                            'bg-slate-500/15 text-slate-400'
                          }`}>{seg.sentiment}</span>
                          <span className="text-slate-400 truncate flex-1">{seg.summary}</span>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}
              </div>
            ) : null}

            {/* ── Variant Video Previews ──────────────────────────────────── */}
            {variants.length > 0 && (
              <Card className="space-y-4">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Generated Variants — Video Preview</p>
                <div className={`grid gap-4 ${
                  variants.length <= 2 ? 'grid-cols-1 lg:grid-cols-2' : 'grid-cols-2 xl:grid-cols-3'
                }`}>
                  {variants.map((v, i) => (
                    <div key={v.id} className="flex flex-col gap-1">
                      <span className="text-xs text-slate-400 font-medium">
                        {v.platform ? v.platform.charAt(0).toUpperCase() + v.platform.slice(1) : `Variant ${i + 1}`}
                        {v.clip_score != null && (
                          <span className="ml-2 text-primary font-mono">{Math.round(v.clip_score * 100)}%</span>
                        )}
                      </span>
                      <video
                        ref={el => { variantRefs.current[i] = el }}
                        src={trailerService.trailerUrl(v.output_url!)}
                        className="w-full rounded-lg aspect-video object-contain bg-black"
                        preload="metadata"
                        muted
                        playsInline
                      />
                      {/* clip sentiment strip */}
                      {v.editing_plan && v.editing_plan.clips.length > 0 && (() => {
                        const total = v.editing_plan.clips.reduce((s, c) => s + (c.end_time - c.start_time), 0)
                        return (
                          <div className="flex h-1.5 rounded-full overflow-hidden gap-px">
                            {v.editing_plan.clips.map((c, ci) => {
                              const w = total > 0 ? ((c.end_time - c.start_time) / total) * 100 : 0
                              const bg = c.sentiment === 'Positive' || c.sentiment === 'Praise' ? 'bg-green-500'
                                : c.sentiment === 'Negative' || c.sentiment === 'Complaint' ? 'bg-red-500'
                                : 'bg-slate-500'
                              return <div key={ci} className={`${bg} h-full`} style={{ width: `${w}%` }} title={`${c.topic} · ${c.sentiment}`} />
                            })}
                          </div>
                        )
                      })()}
                    </div>
                  ))}
                </div>

                {/* Shared playback timeline */}
                <div className="flex items-center gap-3 pt-1">
                  <button
                    onClick={togglePlay}
                    className="flex items-center justify-center w-8 h-8 rounded-full bg-primary hover:bg-primary/80 transition-colors shrink-0"
                  >
                    {playing ? <Pause size={14} className="text-white" /> : <Play size={14} className="text-white" />}
                  </button>
                  <span className="text-xs font-mono text-slate-400 shrink-0 w-10 text-right">{formatTime(Math.round(sharedTime))}</span>
                  <div
                    className="relative flex-1 h-5 flex items-center cursor-pointer select-none"
                    ref={el => { timelineRef.current = el }}
                    onMouseDown={e => {
                      const el = timelineRef.current
                      if (!el) return
                      const seek = (ev: MouseEvent) => {
                        const rect = el.getBoundingClientRect()
                        const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
                        seekAllTo(ratio * maxVariantDuration)
                      }
                      seek(e.nativeEvent)
                      const onUp = () => { window.removeEventListener('mousemove', seek); window.removeEventListener('mouseup', onUp) }
                      window.addEventListener('mousemove', seek)
                      window.addEventListener('mouseup', onUp)
                    }}
                  >
                    <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-700" />
                    <div className="absolute h-1.5 rounded-full bg-primary" style={{ width: `${maxVariantDuration > 0 ? (sharedTime / maxVariantDuration) * 100 : 0}%` }} />
                    <div className="absolute w-3.5 h-3.5 rounded-full bg-white border-2 border-primary shadow -translate-x-1/2" style={{ left: `${maxVariantDuration > 0 ? (sharedTime / maxVariantDuration) * 100 : 0}%` }} />
                  </div>
                  <span className="text-xs font-mono text-slate-600 shrink-0 w-10">{formatTime(Math.round(maxVariantDuration))}</span>
                </div>
              </Card>
            )}

          </div>
        )}
      </div>
    </div>
  )
}
