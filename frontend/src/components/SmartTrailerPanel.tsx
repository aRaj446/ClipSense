import { useState, useEffect, useRef } from 'react'
import { Loader2, CheckCircle, XCircle, RefreshCw, Square, Trash2, Sparkles, MessageSquare, Play } from 'lucide-react'
import { SmartTrailerJob } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import Card from './Card'
import JobProgressPanel, { ProgressStep } from './JobProgressPanel'

const POLL_INTERVAL_MS = 3000

const STATUS_LABEL: Record<SmartTrailerJob['status'], string> = {
  pending:    'Queued…',
  processing: 'Analysing footage & generating trailer…',
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
  clips: NonNullable<SmartTrailerJob['editing_plan']>['clips']
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
          const pct  = ((clip.end_time - clip.start_time) / totalDuration) * 100
          const mood = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          return (
            <div key={i}
              title={`${clip.topic} · ${fmt(clip.start_time)}–${fmt(clip.end_time)}`}
              style={{ width: `${pct}%`, background: mood.border, opacity: 0.85, minWidth: 2 }}
            />
          )
        })}
      </div>

      {/* Clip cards */}
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-1">
        {clips.map((clip, i) => {
          const mood   = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          const isOpen = expanded === i
          return (
            <div key={i}
              className="rounded-xl border cursor-pointer transition-all duration-150"
              style={{ background: mood.bg, borderColor: mood.border + '40', borderLeft: `3px solid ${mood.border}` }}
              onClick={() => setExpanded(isOpen ? null : i)}
            >
              <div className="flex items-center gap-2 px-3 py-2">
                <span className="text-xs font-mono shrink-0" style={{ color: mood.border }}>
                  {fmt(clip.start_time)}–{fmt(clip.end_time)}
                </span>
                <span className="text-xs truncate flex-1" style={{ color: '#F0EDE8' }}>{clip.topic}</span>
                <span className="text-xs px-1.5 py-0.5 rounded-full shrink-0"
                  style={{ background: mood.border + '22', color: mood.border }}>
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

export default function SmartTrailerPanel({ onSelectJob }: { onSelectJob?: (id: string) => void } = {}) {
  const { toast } = useToast()
  const [jobs,        setJobs]        = useState<SmartTrailerJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [progress,    setProgress]    = useState<{ stage: string; percent: number; message: string; steps: ProgressStep[] } | null>(null)
  const pollRef    = useRef<ReturnType<typeof setInterval> | null>(null)
  const sseUnsubRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    smartTrailerService.listJobs()
      .then(existing => {
        setJobs(existing)
        const inFlight = existing.find(j => j.status === 'pending' || j.status === 'processing')
        if (inFlight) setActiveJobId(inFlight.id)
      })
      .catch(() => {})
      .finally(() => setLoadingJobs(false))
  }, [])

  const PENDING_STEPS: ProgressStep[] = [
    { key: 'comments',   label: 'Parsing audience comments', status: 'pending', percent: 0 },
    { key: 'sample',     label: 'Analysing sample trailer',  status: 'pending', percent: 0 },
    { key: 'scenes',     label: 'Detecting scenes',          status: 'pending', percent: 0 },
    { key: 'transcript', label: 'Transcribing audio',        status: 'pending', percent: 0 },
    { key: 'beats',      label: 'Analysing beat rhythm',     status: 'pending', percent: 0 },
    { key: 'planning',   label: 'Planning clip selection',   status: 'pending', percent: 0 },
    { key: 'extracting', label: 'Extracting clips',          status: 'pending', percent: 0 },
    { key: 'composing',  label: 'Composing transitions',     status: 'pending', percent: 0 },
    { key: 'normalising',label: 'Normalising audio',         status: 'pending', percent: 0 },
  ]

  useEffect(() => {
    if (!activeJobId) return
    // Seed with pending steps immediately so UI doesn't appear frozen before first SSE tick
    setProgress({ stage: 'queued', percent: 0, message: 'Starting…', steps: PENDING_STEPS })
    sseUnsubRef.current = smartTrailerService.subscribeProgress(
      activeJobId,
      (stage, percent, message, steps) => setProgress({ stage, percent, message, steps: steps.length ? steps : PENDING_STEPS }),
    )
    pollRef.current = setInterval(async () => {
      try {
        const job = await smartTrailerService.pollJob(activeJobId)
        setJobs(prev => prev.map(j => j.id === job.id ? job : j))
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollRef.current!)
          sseUnsubRef.current?.()
          setActiveJobId(null)
          setProgress(null)
          if (job.status === 'done') toast('Smart trailer generated successfully!')
          else toast(job.error_message ?? 'Smart trailer generation failed.', 'error')
        }
      } catch { /* retry next tick */ }
    }, POLL_INTERVAL_MS)
    return () => { clearInterval(pollRef.current!); sseUnsubRef.current?.() }
  }, [activeJobId])

  async function handleCancel() {
    if (!activeJobId) return
    try {
      const job = await smartTrailerService.cancelJob(activeJobId)
      setJobs(prev => prev.map(j => j.id === job.id ? job : j))
      clearInterval(pollRef.current!)
      setActiveJobId(null)
      toast('Generation cancelled.')
    } catch { toast('Failed to cancel.', 'error') }
  }

  async function handleDelete(jobId: string) {
    try {
      await smartTrailerService.deleteJob(jobId)
      setJobs(prev => prev.filter(j => j.id !== jobId))
      toast('Job deleted.')
    } catch { toast('Failed to delete.', 'error') }
  }

  async function handleRetry(job: SmartTrailerJob) {
    try {
      const started = await smartTrailerService.generate(job.id)
      setJobs(prev => prev.map(j => j.id === started.id ? started : j))
      setActiveJobId(started.id)
      toast('Retrying generation…')
    } catch { toast('Failed to retry.', 'error') }
  }

  const activeJob = jobs.find(j => j.id === activeJobId)

  const statusColor = (s: SmartTrailerJob['status']) =>
    s === 'done' ? '#4ADE80' : s === 'failed' ? '#F87171' : '#D4A843'

  if (loadingJobs) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 size={24} className="animate-spin" style={{ color: '#5C5A72' }} />
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <Card variant="gradient" className="flex flex-col items-center py-16 text-center">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
          style={{ background: 'linear-gradient(135deg,#D4A84314,#8B7CF614)', border: '1px solid #D4A84320' }}>
          <Sparkles size={28} style={{ color: '#5C5A72' }} />
        </div>
        <p className="font-medium" style={{ color: '#F0EDE8' }}>No smart trailers yet</p>
        <p className="text-sm mt-1" style={{ color: '#5C5A72' }}>Go to Upload → Smart Trailer to generate one.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-4">

      {/* Active job banner */}
      {activeJob && (activeJob.status === 'pending' || activeJob.status === 'processing') && (
        <div className="space-y-3">
          <JobProgressPanel
            stage={progress?.stage ?? 'pending'}
            percent={progress?.percent ?? 0}
            message={progress?.message ?? 'Analysing sample trailer, classifying mood groups, composing with crossfades…'}
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
      <div className="space-y-3">
        {jobs.map(job => (
          <div key={job.id} className="rounded-2xl overflow-hidden"
            style={{ border: `1px solid ${statusColor(job.status)}20`, borderLeft: `3px solid ${statusColor(job.status)}` }}>

            <div
              className={`flex items-center gap-3 px-4 py-3 ${job.status === 'done' && onSelectJob ? 'cursor-pointer' : ''}`}
              style={{ background: 'linear-gradient(145deg, #13131F, #1A1A2E)' }}
              onClick={() => job.status === 'done' && onSelectJob?.(job.id)}
            >
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
                <p className="text-xs truncate mt-0.5" style={{ color: '#5C5A72' }}>
                  {job.raw_footage_name} + {job.sample_trailer_name}
                </p>
                {job.error_message && <p className="text-xs mt-0.5 truncate" style={{ color: '#F87171' }}>{job.error_message}</p>}
              </div>
              {job.clip_score != null && (
                <span className="text-xs font-mono shrink-0" style={{ color: '#FCD34D' }}>
                  {Math.round(job.clip_score * 100)}%
                </span>
              )}
              <span className="text-xs shrink-0 hidden sm:inline" style={{ color: '#5C5A72' }}>
                {new Date(job.updated_at).toLocaleString()}
              </span>
              {job.status === 'failed' && (
                <button onClick={e => { e.stopPropagation(); handleRetry(job) }}
                  className="transition-colors shrink-0" style={{ color: '#5C5A72' }}>
                  <RefreshCw size={13} />
                </button>
              )}
              {(job.status === 'done' || job.status === 'failed') && (
                <button onClick={e => { e.stopPropagation(); handleDelete(job.id) }}
                  className="transition-colors shrink-0" style={{ color: '#5C5A72' }}>
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
                  src={smartTrailerService.trailerUrl(job.output_url)} />
                <div className="px-4 py-2 flex items-center gap-3">
                  <a href={smartTrailerService.trailerUrl(job.output_url)} download
                    className="flex items-center gap-1.5 text-xs transition-opacity hover:opacity-70"
                    style={{ color: '#D4A843' }}>
                    <Play size={12} /> Download trailer
                  </a>
                  {job.clip_score != null && (
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
    </div>
  )
}
