import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clapperboard, ChevronDown, Loader2, CheckCircle, XCircle, Play, RefreshCw, Sparkles, Trash2, Square, MessageSquare } from 'lucide-react'
import { StoredDataset, TrailerJob } from '../types/analysis'
import { trailerService } from '../services/trailerService'
import { useToast } from '../context/ToastContext'
import Button from './Button'
import Card from './Card'
import JobProgressPanel, { ProgressStep } from './JobProgressPanel'

const POLL_INTERVAL_MS = 3000

interface Props {
  projectId: string
  datasets: StoredDataset[]
}

const STATUS_LABEL: Record<TrailerJob['status'], string> = {
  pending:    'Queued…',
  processing: 'Generating trailer…',
  done:       'Ready',
  failed:     'Failed',
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
    <div className="mt-3 space-y-2">
      <p className="text-xs font-medium uppercase tracking-wide" style={{ color: '#5C5A72' }}>
        Clip Timeline — {clips.length} clips · {fmt(totalDuration)}
      </p>

      {/* Mood legend */}
      <div className="flex gap-3 flex-wrap mb-1">
        {Object.entries(MOOD_COLOR).map(([mood, { border, label }]) => (
          <span key={mood} className="flex items-center gap-1 text-xs" style={{ color: '#A8A4B8' }}>
            <span className="w-2 h-2 rounded-sm inline-block" style={{ background: border }} />
            {label}
          </span>
        ))}
      </div>

      {/* Visual timeline bar */}
      <div className="flex h-3 rounded-full overflow-hidden gap-px" style={{ background: '#252538' }}>
        {clips.map((clip, i) => {
          const pct = ((clip.end_time - clip.start_time) / totalDuration) * 100
          const mood = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          return (
            <div
              key={i}
              title={`${clip.topic} · ${fmt(clip.start_time)}–${fmt(clip.end_time)}`}
              style={{ width: `${pct}%`, background: mood.border, opacity: 0.85, minWidth: 2 }}
            />
          )
        })}
      </div>

      {/* Clip cards */}
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
        {clips.map((clip, i) => {
          const mood = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          const isOpen = expanded === i
          return (
            <div
              key={i}
              className="rounded-xl border cursor-pointer transition-all duration-150"
              style={{ background: mood.bg, borderColor: mood.border + '40', borderLeft: `3px solid ${mood.border}` }}
              onClick={() => setExpanded(isOpen ? null : i)}
            >
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="text-xs font-mono shrink-0" style={{ color: mood.border }}>
                  {fmt(clip.start_time)}–{fmt(clip.end_time)}
                </span>
                <span className="text-xs truncate flex-1" style={{ color: '#F0EDE8' }}>{clip.topic}</span>
                <span className="text-xs px-1.5 py-0.5 rounded-full shrink-0" style={{ background: mood.border + '22', color: mood.border }}>
                  {mood.label}
                </span>
                <span className="text-xs shrink-0" style={{ color: '#5C5A72' }}>
                  {fmt(clip.end_time - clip.start_time)}
                </span>
              </div>
              {isOpen && (
                <div className="px-3 pb-2.5 space-y-1.5">
                  <p className="text-xs" style={{ color: '#A8A4B8' }}>{clip.reason}</p>
                  {clip.transcript_text && (
                    <div className="flex gap-1.5 items-start">
                      <MessageSquare size={10} className="shrink-0 mt-0.5" style={{ color: '#5C5A72' }} />
                      <p className="text-xs italic" style={{ color: '#5C5A72' }}>"{clip.transcript_text}"</p>
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
  const { toast } = useToast()
  const navigate  = useNavigate()

  const [selectedDs, setSelectedDs]   = useState<string>('')
  const [jobs, setJobs]               = useState<TrailerJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [generating, setGenerating]   = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState<{ stage: string; percent: number; message: string; steps: ProgressStep[] } | null>(null)
  const pollRef                       = useRef<ReturnType<typeof setInterval> | null>(null)
  const sseUnsubRef                   = useRef<(() => void) | null>(null)

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

  const activeJob     = jobs.find(j => j.id === activeJobId)
  const completedJobs = jobs.filter(j => j.status === 'done' && j.output_url)

  const statusColor = (s: TrailerJob['status']) =>
    s === 'done' ? '#4ADE80' : s === 'failed' ? '#F87171' : '#D4A843'

  return (
    <Card className="space-y-5">

      {/* Header */}
      <div className="flex items-center gap-2">
        <Sparkles size={16} style={{ color: '#D4A843' }} />
        <h2 className="font-semibold" style={{ color: '#F0EDE8' }}>Video Generation</h2>
        {loadingJobs && <Loader2 size={13} className="animate-spin ml-1" style={{ color: '#5C5A72' }} />}
        {completedJobs.length > 0 && (
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full border"
            style={{ background: '#D4A84312', color: '#D4A843', borderColor: '#D4A84328' }}>
            {completedJobs.length} variant{completedJobs.length !== 1 ? 's' : ''} ready
          </span>
        )}
      </div>

      <p className="text-sm" style={{ color: '#A8A4B8' }}>
        Select a feedback dataset. The AI reads the sentiment analytics and decides
        which segments to include. FFmpeg assembles the final clip with crossfade transitions.
      </p>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <select
            value={selectedDs}
            onChange={e => setSelectedDs(e.target.value)}
            disabled={generating || datasets.length === 0}
            className="w-full appearance-none border rounded-xl px-3 py-2 text-sm outline-none focus:ring-1 disabled:opacity-50 pr-8"
            style={{ background: '#13131F', borderColor: '#252538', color: '#F0EDE8' }}
          >
            <option value="" disabled>
              {datasets.length === 0 ? 'No datasets — upload feedback first' : 'Select a feedback dataset…'}
            </option>
            {datasets.map(ds => (
              <option key={ds.id} value={ds.id}>
                {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`} ({ds.segment_count} segments)
              </option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" style={{ color: '#5C5A72' }} />
        </div>
        <Button onClick={handleGenerate} loading={generating} disabled={!selectedDs || generating} icon={<Clapperboard size={14} />}>
          {generating ? 'Generating…' : 'Generate Trailer'}
        </Button>
      </div>

      {/* Active job banner */}
      {activeJob && (activeJob.status === 'pending' || activeJob.status === 'processing') && (
        <div className="space-y-3">
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

      {/* Job list */}
      {jobs.length > 0 && (
        <div className="space-y-3">
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: '#5C5A72' }}>Generated Trailers</p>
          {jobs.map(job => (
            <div key={job.id} className="rounded-2xl overflow-hidden"
              style={{ border: `1px solid ${statusColor(job.status)}20`, borderLeft: `3px solid ${statusColor(job.status)}` }}>

              <div className="flex items-center gap-3 px-4 py-3"
                style={{ background: 'linear-gradient(145deg, #13131F, #1A1A2E)' }}>
                {job.status === 'done'   && <CheckCircle size={14} style={{ color: '#4ADE80' }} className="shrink-0" />}
                {job.status === 'failed' && <XCircle     size={14} style={{ color: '#F87171' }} className="shrink-0" />}
                {(job.status === 'pending' || job.status === 'processing') && (
                  <Loader2 size={14} className="animate-spin shrink-0" style={{ color: '#D4A843' }} />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium" style={{ color: '#F0EDE8' }}>
                    {STATUS_LABEL[job.status]}
                    {job.editing_plan && (
                      <span className="ml-2 text-xs font-normal" style={{ color: '#5C5A72' }}>
                        {job.editing_plan.clips.length} clips · {fmt(job.editing_plan.target_duration)}
                      </span>
                    )}
                    {job.platform && (
                      <span className="ml-2 text-xs font-normal capitalize" style={{ color: '#5C5A72' }}>· {job.platform}</span>
                    )}
                  </p>
                  {job.error_message && <p className="text-xs mt-0.5 truncate" style={{ color: '#F87171' }}>{job.error_message}</p>}
                  {job.editing_plan?.rationale && <p className="text-xs mt-0.5 truncate" style={{ color: '#5C5A72' }}>{job.editing_plan.rationale}</p>}
                </div>
                <span className="text-xs shrink-0 hidden sm:inline" style={{ color: '#5C5A72' }}>{new Date(job.updated_at).toLocaleString()}</span>
                {job.status === 'failed' && (
                  <button onClick={() => handleRetry(job.dataset_id)} disabled={generating}
                    className="transition-colors shrink-0 disabled:opacity-40" style={{ color: '#5C5A72' }}>
                    <RefreshCw size={13} />
                  </button>
                )}
                {(job.status === 'done' || job.status === 'failed') && (
                  <button onClick={() => handleDelete(job.id)} className="transition-colors shrink-0"
                    style={{ color: '#5C5A72' }}>
                    <Trash2 size={13} />
                  </button>
                )}
              </div>

              {/* Clip timeline preview */}
              {job.editing_plan && job.editing_plan.clips.length > 0 && (
                <div className="px-4 pb-3" style={{ background: 'linear-gradient(145deg, #13131F, #1A1A2E)' }}>
                  <ClipTimeline clips={job.editing_plan.clips} totalDuration={job.editing_plan.target_duration} />
                </div>
              )}

              {job.status === 'done' && job.output_url && (
                <div style={{ borderTop: '1px solid #252538', background: '#0C0C14' }}>
                  <video controls className="w-full max-h-64 object-contain bg-black"
                    src={trailerService.trailerUrl(job.output_url)} />
                  <div className="px-4 py-2 flex items-center gap-3">
                    <a href={trailerService.trailerUrl(job.output_url)} download
                      className="flex items-center gap-1.5 text-xs transition-opacity hover:opacity-70"
                      style={{ color: '#D4A843' }}>
                      <Play size={12} /> Download trailer
                    </a>
                    {job.clip_score !== null && (
                      <span className="text-xs ml-auto" style={{ color: '#5C5A72' }}>
                        Score: <span className="font-medium" style={{ color: '#FCD34D' }}>{Math.round((job.clip_score ?? 0) * 100)}%</span>
                      </span>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
