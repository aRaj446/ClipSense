import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Clapperboard, ChevronDown, Loader2, CheckCircle, XCircle,
  Play, RefreshCw, Sparkles, Trash2, Square, MessageSquare,
  Film, Download, Clock, ArrowRight,
} from 'lucide-react'
import { StoredDataset, TrailerJob } from '../types/analysis'
import { trailerService } from '../services/trailerService'
import { useToast } from '../context/ToastContext'
import Button from './Button'
import JobProgressPanel, { ProgressStep } from './JobProgressPanel'

const POLL_INTERVAL_MS = 3000

interface Props { projectId: string; datasets: StoredDataset[] }

const STATUS_LABEL: Record<TrailerJob['status'], string> = {
  pending:    'Queued',
  processing: 'Generating…',
  done:       'Ready',
  failed:     'Failed',
}

const STATUS_COLOR: Record<TrailerJob['status'], string> = {
  pending:    '#D4A843',
  processing: '#8B7CF6',
  done:       '#4ADE80',
  failed:     '#F87171',
}

const MOOD_COLOR: Record<string, { bg: string; border: string; label: string }> = {
  action:    { bg: '#F8717118', border: '#F87171', label: 'Action' },
  emotional: { bg: '#8B7CF618', border: '#8B7CF6', label: 'Emotional' },
  dialogue:  { bg: '#D4A84318', border: '#D4A843', label: 'Dialogue' },
  calm:      { bg: '#2DD4BF18', border: '#2DD4BF', label: 'Calm' },
}

function fmt(secs: number) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function ClipTimeline({ clips, totalDuration }: {
  clips: NonNullable<TrailerJob['editing_plan']>['clips']
  totalDuration: number
}) {
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>
          Clip Timeline
        </span>
        <span className="text-xs font-mono px-2 py-0.5 rounded-full"
          style={{ background: '#1E1E30', color: '#A8A4B8' }}>
          {clips.length} clips · {fmt(totalDuration)}
        </span>
      </div>

      {/* Mood legend */}
      <div className="flex gap-3 flex-wrap">
        {Object.entries(MOOD_COLOR).map(([mood, { border, label }]) => (
          <span key={mood} className="flex items-center gap-1.5 text-xs" style={{ color: '#A8A4B8' }}>
            <span className="w-2 h-2 rounded-sm" style={{ background: border }} />{label}
          </span>
        ))}
      </div>

      {/* Segmented bar */}
      <div className="flex h-3 rounded-full overflow-hidden gap-px" style={{ background: '#1E1E30' }}>
        {clips.map((clip, i) => {
          const pct  = ((clip.end_time - clip.start_time) / totalDuration) * 100
          const mood = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          return (
            <div key={i}
              title={`${clip.topic} · ${fmt(clip.start_time)}–${fmt(clip.end_time)}`}
              className="cursor-pointer transition-opacity hover:opacity-100"
              style={{ width: `${pct}%`, background: mood.border, opacity: 0.75, minWidth: 3 }}
              onClick={() => setExpanded(expanded === i ? null : i)}
            />
          )
        })}
      </div>

      {/* Clip rows */}
      <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
        {clips.map((clip, i) => {
          const mood   = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          const isOpen = expanded === i
          return (
            <div key={i}
              className="rounded-xl cursor-pointer transition-all duration-150"
              style={{
                background: isOpen ? mood.bg : 'rgba(255,255,255,0.02)',
                border: `1px solid ${isOpen ? mood.border + '40' : '#1E1E30'}`,
                borderLeft: `3px solid ${mood.border}`,
              }}
              onClick={() => setExpanded(isOpen ? null : i)}>
              <div className="flex items-center gap-2.5 px-3 py-2">
                <span className="text-xs font-mono shrink-0 tabular-nums" style={{ color: mood.border }}>
                  {fmt(clip.start_time)}
                </span>
                <span className="text-xs truncate flex-1 font-medium" style={{ color: '#F0EDE8' }}>
                  {clip.topic}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full shrink-0"
                  style={{ background: mood.border + '18', color: mood.border }}>
                  {mood.label}
                </span>
                <span className="text-xs font-mono shrink-0" style={{ color: '#5C5A72' }}>
                  {fmt(clip.end_time - clip.start_time)}
                </span>
              </div>
              {isOpen && (
                <div className="px-3 pb-3 space-y-2 border-t" style={{ borderColor: mood.border + '20' }}>
                  <p className="text-xs pt-2 leading-relaxed" style={{ color: '#A8A4B8' }}>{clip.reason}</p>
                  {clip.transcript_text && (
                    <div className="flex gap-2 items-start rounded-lg px-2.5 py-2"
                      style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}>
                      <MessageSquare size={10} className="shrink-0 mt-0.5" style={{ color: '#5C5A72' }} />
                      <p className="text-xs italic leading-relaxed" style={{ color: '#5C5A72' }}>
                        "{clip.transcript_text}"
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function TrailerPanel({ projectId, datasets }: Props) {
  const { toast }  = useToast()
  const navigate   = useNavigate()

  const [selectedDs,  setSelectedDs]  = useState<string>('')
  const [jobs,        setJobs]        = useState<TrailerJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [generating,  setGenerating]  = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [progress,    setProgress]    = useState<{ stage: string; percent: number; message: string; steps: ProgressStep[] } | null>(null)
  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null)
  const sseUnsubRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    trailerService.listJobs(projectId)
      .then(existing => {
        setJobs(existing)
        const inFlight = existing.find(j => j.status === 'pending' || j.status === 'processing')
        if (inFlight) { setGenerating(true); setActiveJobId(inFlight.id) }
      })
      .catch(() => {})
      .finally(() => setLoadingJobs(false))
  }, [projectId])

  useEffect(() => {
    if (datasets.length === 0) return
    const stillExists = datasets.some(ds => ds.id === selectedDs)
    if (!stillExists) setSelectedDs(datasets[0].id)
  }, [datasets])

  useEffect(() => {
    if (!activeJobId) return
    setProgress(null)
    sseUnsubRef.current = trailerService.subscribeProgress(
      activeJobId,
      (stage, percent, message, steps) => setProgress({ stage, percent, message, steps }),
    )
    pollRef.current = setInterval(async () => {
      try {
        const job = await trailerService.pollJob(activeJobId)
        setJobs(prev => prev.map(j => j.id === job.id ? job : j))
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollRef.current!)
          sseUnsubRef.current?.()
          setActiveJobId(null)
          setGenerating(false)
          setProgress(null)
          if (job.status === 'done') toast('Trailer generated successfully!')
          else toast(job.error_message ?? 'Trailer generation failed.', 'error')
        }
      } catch { /* retry next tick */ }
    }, POLL_INTERVAL_MS)
    return () => { clearInterval(pollRef.current!); sseUnsubRef.current?.() }
  }, [activeJobId])

  async function handleGenerate() {
    if (!selectedDs) return
    setGenerating(true)
    try {
      const job = await trailerService.generateTrailer(projectId, selectedDs)
      setJobs(prev => [job, ...prev.filter(j => j.id !== job.id)])
      setActiveJobId(job.id)
      toast('Trailer job started — processing in background.')
      navigate('/trailers')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to start trailer generation.'
      toast(msg, 'error')
      setGenerating(false)
    }
  }

  async function handleRetry(datasetId: string) {
    setSelectedDs(datasetId)
    setGenerating(true)
    try {
      const job = await trailerService.generateTrailer(projectId, datasetId)
      setJobs(prev => [job, ...prev.filter(j => j.id !== job.id)])
      setActiveJobId(job.id)
      toast('Retrying trailer generation…')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Failed to retry.'
      toast(msg, 'error')
      setGenerating(false)
    }
  }

  async function handleCancel() {
    if (!activeJobId) return
    try {
      const job = await trailerService.cancelJob(activeJobId)
      setJobs(prev => prev.map(j => j.id === job.id ? job : j))
      clearInterval(pollRef.current!)
      setActiveJobId(null)
      setGenerating(false)
      toast('Trailer generation cancelled.')
    } catch { toast('Failed to cancel job.', 'error') }
  }

  async function handleDelete(jobId: string) {
    try {
      await trailerService.deleteJob(jobId)
      setJobs(prev => prev.filter(j => j.id !== jobId))
      toast('Trailer deleted.')
    } catch { toast('Failed to delete trailer.', 'error') }
  }

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Dataset selector + generate ── */}
      <div className="relative rounded-2xl p-5 overflow-hidden"
        style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #252538' }}>

        {generating && (
          <div className="absolute inset-x-0 h-px pointer-events-none animate-shimmer-slide"
            style={{ background: 'linear-gradient(90deg,transparent,#D4A84360,#8B7CF650,transparent)', top: 0 }} />
        )}

        <div className="flex items-center gap-2 mb-4">
          <Film size={14} style={{ color: '#D4A843' }} />
          <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>Generate Trailer</span>
          {loadingJobs && <Loader2 size={12} className="animate-spin ml-auto" style={{ color: '#5C5A72' }} />}
        </div>

        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <select
              value={selectedDs}
              onChange={e => setSelectedDs(e.target.value)}
              disabled={generating || datasets.length === 0}
              className="w-full appearance-none rounded-xl px-4 py-2.5 text-sm outline-none disabled:opacity-50 pr-9"
              style={{ background: '#0E0E1A', border: '1px solid #2A2A40', color: '#F0EDE8' }}>
              <option value="" disabled>
                {datasets.length === 0 ? 'No datasets — upload feedback first' : 'Select a feedback dataset…'}
              </option>
              {datasets.map(ds => (
                <option key={ds.id} value={ds.id}>
                  {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`} ({ds.segment_count} segments)
                </option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: '#5C5A72' }} />
          </div>
          <Button onClick={handleGenerate} loading={generating} disabled={!selectedDs || generating}
            icon={<Clapperboard size={14} />}>
            {generating ? 'Generating…' : 'Generate Trailer'}
          </Button>
        </div>

        {generating && (
          <div className="mt-4 space-y-3">
            <JobProgressPanel
              stage={progress?.stage ?? 'pending'}
              percent={progress?.percent ?? 0}
              message={progress?.message ?? 'Analysing sentiment, classifying mood groups, composing with crossfades…'}
              steps={progress?.steps ?? []}
            />
            <div className="flex justify-end">
              <button onClick={handleCancel}
                className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors"
                style={{ borderColor: '#F8717130', color: '#F87171', background: '#F8717108' }}>
                <Square size={11} /> Stop generation
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Job list ── */}
      {jobs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>
              Generated Trailers
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: '#1E1E30', color: '#A8A4B8' }}>
              {jobs.length} job{jobs.length !== 1 ? 's' : ''}
            </span>
          </div>

          {jobs.map((job, idx) => {
            const sc = STATUS_COLOR[job.status]
            return (
              <div key={job.id}
                className="rounded-2xl overflow-hidden animate-fade-in"
                style={{
                  border: `1px solid ${sc}20`,
                  boxShadow: job.status === 'done' ? `0 0 24px 0 ${sc}12` : 'none',
                  animationDelay: `${idx * 50}ms`,
                }}>

                {/* ── Card header ── */}
                <div className="flex items-center gap-3 px-5 py-3.5"
                  style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', borderBottom: `1px solid ${sc}18` }}>

                  {/* Status icon */}
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: sc + '15', border: `1px solid ${sc}30` }}>
                    {job.status === 'done'       && <CheckCircle size={15} style={{ color: sc }} />}
                    {job.status === 'failed'     && <XCircle     size={15} style={{ color: sc }} />}
                    {(job.status === 'pending' || job.status === 'processing') && (
                      <Loader2 size={15} className="animate-spin" style={{ color: sc }} />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>
                        {STATUS_LABEL[job.status]}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ background: sc + '15', color: sc, border: `1px solid ${sc}30` }}>
                        {job.status}
                      </span>
                      {job.editing_plan && (
                        <span className="flex items-center gap-1 text-xs" style={{ color: '#5C5A72' }}>
                          <Clock size={10} />
                          {job.editing_plan.clips.length} clips · {fmt(job.editing_plan.target_duration)}
                        </span>
                      )}
                    </div>
                    {job.error_message && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: '#F87171' }}>{job.error_message}</p>
                    )}
                    {job.editing_plan?.rationale && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: '#5C5A72' }}>{job.editing_plan.rationale}</p>
                    )}
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-xs hidden sm:inline mr-2" style={{ color: '#5C5A72' }}>
                      {new Date(job.updated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true })}
                    </span>
                    {job.status === 'failed' && (
                      <button onClick={() => handleRetry(job.dataset_id)} disabled={generating}
                        className="p-1.5 rounded-lg transition-colors disabled:opacity-40"
                        style={{ color: '#D4A843', background: '#D4A84310' }}
                        title="Retry">
                        <RefreshCw size={13} />
                      </button>
                    )}
                    {(job.status === 'done' || job.status === 'failed') && (
                      <button onClick={() => handleDelete(job.id)}
                        className="p-1.5 rounded-lg transition-colors"
                        style={{ color: '#5C5A72', background: 'transparent' }}
                        title="Delete">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>

                {/* ── Card body: two-column on large screens ── */}
                {(job.editing_plan || (job.status === 'done' && job.output_url)) && (
                  <div className="grid grid-cols-1 lg:grid-cols-2"
                    style={{ background: 'linear-gradient(145deg,#0F0F1C,#13131F)' }}>

                    {/* Left — clip timeline */}
                    {job.editing_plan && job.editing_plan.clips.length > 0 && (
                      <div className="p-5" style={{ borderRight: '1px solid #1E1E30' }}>
                        <ClipTimeline
                          clips={job.editing_plan.clips}
                          totalDuration={job.editing_plan.target_duration}
                        />
                      </div>
                    )}

                    {/* Right — video preview */}
                    {job.status === 'done' && job.output_url && (
                      <div className="flex flex-col">
                        <video controls className="w-full object-contain bg-black"
                          style={{ maxHeight: 260 }}
                          src={trailerService.trailerUrl(job.output_url)} />
                        <div className="px-5 py-3 flex items-center gap-3"
                          style={{ borderTop: '1px solid #1E1E30' }}>
                          <a href={trailerService.trailerUrl(job.output_url)} download
                            className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-lg transition-all"
                            style={{ background: '#D4A84318', color: '#D4A843', border: '1px solid #D4A84330' }}>
                            <Download size={12} /> Download
                          </a>
                          <a href={trailerService.trailerUrl(job.output_url)} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1.5 text-xs transition-all"
                            style={{ color: '#5C5A72' }}>
                            <Play size={11} /> Open <ArrowRight size={11} />
                          </a>
                        </div>
                      </div>
                    )}

                    {/* If only timeline (no video yet) fill full width */}
                    {job.editing_plan && job.editing_plan.clips.length > 0 && !(job.status === 'done' && job.output_url) && (
                      <div className="p-5 flex items-center justify-center"
                        style={{ borderLeft: '1px solid #1E1E30' }}>
                        <div className="text-center">
                          <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3"
                            style={{ background: '#1E1E30', border: '1px solid #252538' }}>
                            <Film size={20} style={{ color: '#5C5A72' }} />
                          </div>
                          <p className="text-xs" style={{ color: '#5C5A72' }}>
                            {job.status === 'processing' ? 'Rendering video…' : 'No preview yet'}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* ── Empty state ── */}
      {!loadingJobs && jobs.length === 0 && (
        <div className="flex flex-col items-center py-14 rounded-2xl"
          style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #252538' }}>
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4 animate-float"
            style={{ background: 'linear-gradient(135deg,#D4A84312,#8B7CF610)', border: '1px solid #D4A84320' }}>
            <Sparkles size={22} style={{ color: '#5C5A72' }} />
          </div>
          <p className="text-sm font-semibold mb-1" style={{ color: '#F0EDE8' }}>No trailers yet</p>
          <p className="text-xs" style={{ color: '#5C5A72' }}>Select a dataset above and generate your first trailer.</p>
        </div>
      )}
    </div>
  )
}
