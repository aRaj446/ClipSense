import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clapperboard, ChevronDown, Loader2, CheckCircle, XCircle, Play, RefreshCw, Sparkles, Trash2, Square } from 'lucide-react'
import { StoredDataset, TrailerJob } from '../types/analysis'
import { trailerService } from '../services/trailerService'
import { useToast } from '../context/ToastContext'
import Button from './Button'
import Card from './Card'

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

export default function TrailerPanel({ projectId, datasets }: Props) {
  const { toast } = useToast()
  const navigate = useNavigate()

  const [selectedDs, setSelectedDs]   = useState<string>('')
  const [jobs, setJobs]               = useState<TrailerJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [generating, setGenerating]   = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const pollRef                       = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Load existing jobs on mount + resume polling for in-progress jobs ──────
  useEffect(() => {
    trailerService.listJobs(projectId)
      .then(existing => {
        setJobs(existing)
        // resume polling for any job still in flight
        const inFlight = existing.find(
          j => j.status === 'pending' || j.status === 'processing'
        )
        if (inFlight) {
          setGenerating(true)
          setActiveJobId(inFlight.id)
        }
      })
      .catch(() => {})
      .finally(() => setLoadingJobs(false))
  }, [projectId])

  // Auto-select first dataset; re-select if current selection no longer exists
  useEffect(() => {
    if (datasets.length === 0) return
    const stillExists = datasets.some(ds => ds.id === selectedDs)
    if (!stillExists) setSelectedDs(datasets[0].id)
  }, [datasets])

  // ── Polling ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!activeJobId) return
    pollRef.current = setInterval(async () => {
      try {
        const job = await trailerService.pollJob(activeJobId)
        setJobs(prev => prev.map(j => j.id === job.id ? job : j))
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollRef.current!)
          setActiveJobId(null)
          setGenerating(false)
          if (job.status === 'done') toast('Trailer generated successfully!')
          else toast(job.error_message ?? 'Trailer generation failed.', 'error')
        }
      } catch { /* retry next tick */ }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(pollRef.current!)
  }, [activeJobId])

  // ── Generate ──────────────────────────────────────────────────────────────

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
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to start trailer generation.'
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
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to retry trailer generation.'
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
    } catch {
      toast('Failed to cancel job.', 'error')
    }
  }

  async function handleDelete(jobId: string) {
    try {
      await trailerService.deleteJob(jobId)
      setJobs(prev => prev.filter(j => j.id !== jobId))
      toast('Trailer deleted.')
    } catch {
      toast('Failed to delete trailer.', 'error')
    }
  }

  const activeJob     = jobs.find(j => j.id === activeJobId)
  const completedJobs = jobs.filter(j => j.status === 'done' && j.output_url)

  return (
    <Card className="space-y-5">

      {/* ── Header ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">
        <Sparkles size={16} className="text-primary" />
        <h2 className="font-semibold text-slate-100">Video Generation</h2>
        {loadingJobs && (
          <Loader2 size={13} className="text-slate-500 animate-spin ml-1" />
        )}
        {completedJobs.length > 0 && (
          <span className="ml-auto text-xs px-2 py-0.5 rounded-full bg-primary/15 text-primary border border-primary/20">
            {completedJobs.length} variant{completedJobs.length !== 1 ? 's' : ''} ready
          </span>
        )}
      </div>

      {/* ── Generate controls ─────────────────────────────────────────────── */}
      <p className="text-sm text-slate-400 leading-relaxed">
        Select a feedback dataset. Gemini reads the sentiment analytics and decides
        which segments to include. FFmpeg assembles the final clip.
      </p>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <select
            value={selectedDs}
            onChange={e => setSelectedDs(e.target.value)}
            disabled={generating || datasets.length === 0}
            className="w-full appearance-none bg-surface border border-surface-border rounded-lg px-3 py-2 text-sm text-slate-200 outline-none focus:ring-1 focus:ring-primary disabled:opacity-50 pr-8"
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
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 pointer-events-none" />
        </div>

        <Button
          onClick={handleGenerate}
          loading={generating}
          disabled={!selectedDs || generating}
          icon={<Clapperboard size={14} />}
        >
          {generating ? 'Generating…' : 'Generate Trailer'}
        </Button>
      </div>

      {/* ── Active job progress ───────────────────────────────────────────── */}
      {activeJob && (activeJob.status === 'pending' || activeJob.status === 'processing') && (
        <div className="flex items-center gap-3 bg-surface border border-surface-border rounded-lg px-4 py-3">
          <Loader2 size={16} className="text-primary animate-spin shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-slate-200 text-sm font-medium">{STATUS_LABEL[activeJob.status]}</p>
            <p className="text-slate-500 text-xs mt-0.5">
              Gemini is analysing sentiment data and planning the edit…
            </p>
          </div>
          <span className="text-xs text-slate-600">{activeJob.id.slice(0, 8)}…</span>
          <button
            onClick={handleCancel}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
            title="Stop generation"
          >
            <Square size={11} /> Stop
          </button>
        </div>
      )}

      {/* ── Job list ──────────────────────────────────────────────────────── */}
      {jobs.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-slate-500 font-medium uppercase tracking-wide">Generated Trailers</p>
          {jobs.map(job => (
            <div key={job.id} className="border border-surface-border rounded-lg overflow-hidden">

              <div className="flex items-center gap-3 px-4 py-3 bg-surface">
                {job.status === 'done'   && <CheckCircle size={14} className="text-green-400 shrink-0" />}
                {job.status === 'failed' && <XCircle size={14} className="text-red-400 shrink-0" />}
                {(job.status === 'pending' || job.status === 'processing') && (
                  <Loader2 size={14} className="text-primary animate-spin shrink-0" />
                )}

                <div className="flex-1 min-w-0">
                  <p className="text-slate-300 text-sm font-medium">
                    {STATUS_LABEL[job.status]}
                    {job.editing_plan && (
                      <span className="ml-2 text-xs text-slate-500 font-normal">
                        {job.editing_plan.clips.length} clips · {Math.round(job.editing_plan.target_duration)}s
                      </span>
                    )}
                    {job.platform && (
                      <span className="ml-2 text-xs text-slate-500 font-normal capitalize">· {job.platform}</span>
                    )}
                  </p>
                  {job.error_message && (
                    <p className="text-red-400 text-xs mt-0.5 truncate">{job.error_message}</p>
                  )}
                  {job.editing_plan?.rationale && (
                    <p className="text-slate-500 text-xs mt-0.5 truncate">{job.editing_plan.rationale}</p>
                  )}
                </div>

                <span className="text-xs text-slate-600 shrink-0 hidden sm:inline">
                  {new Date(job.updated_at).toLocaleString()}
                </span>

                {job.status === 'failed' && (
                  <button
                    onClick={() => handleRetry(job.dataset_id)}
                    disabled={generating}
                    className="text-slate-600 hover:text-slate-300 disabled:opacity-40 transition-colors shrink-0"
                    title="Retry generation"
                  >
                    <RefreshCw size={13} />
                  </button>
                )}
                {(job.status === 'done' || job.status === 'failed') && (
                  <button
                    onClick={() => handleDelete(job.id)}
                    className="text-slate-600 hover:text-red-400 transition-colors shrink-0"
                    title="Delete trailer"
                  >
                    <Trash2 size={13} />
                  </button>
                )}
              </div>

              {job.status === 'done' && job.output_url && (
                <div className="border-t border-surface-border bg-black">
                  <video
                    controls
                    className="w-full max-h-64 object-contain"
                    src={trailerService.trailerUrl(job.output_url)}
                  >
                    Your browser does not support video playback.
                  </video>
                  <div className="px-4 py-2 flex items-center gap-3">
                    <a
                      href={trailerService.trailerUrl(job.output_url)}
                      download
                      className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors"
                    >
                      <Play size={12} /> Download trailer
                    </a>
                    {job.clip_score !== null && (
                      <span className="text-xs text-slate-500 ml-auto">
                        Score: <span className="text-yellow-400 font-medium">{Math.round((job.clip_score ?? 0) * 100)}%</span>
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
