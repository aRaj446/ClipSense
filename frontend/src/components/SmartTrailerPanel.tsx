import { useState, useEffect, useRef } from 'react'
import { Loader2, CheckCircle, XCircle, RefreshCw, Square, Trash2, Sparkles } from 'lucide-react'
import { SmartTrailerJob } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import Card from './Card'

const POLL_INTERVAL_MS = 3000

const STATUS_LABEL: Record<SmartTrailerJob['status'], string> = {
  pending:    'Queued…',
  processing: 'Analysing footage & generating trailer…',
  done:       'Ready',
  failed:     'Failed',
}

const STATUS_COLOR: Record<SmartTrailerJob['status'], string> = {
  done:       '#10B981',
  failed:     '#EF4444',
  processing: '#2563EB',
  pending:    '#2563EB',
}

export default function SmartTrailerPanel({ onSelectJob }: { onSelectJob?: (id: string) => void } = {}) {
  const { toast } = useToast()
  const [jobs,        setJobs]        = useState<SmartTrailerJob[]>([])
  const [loadingJobs, setLoadingJobs] = useState(true)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

  useEffect(() => {
    if (!activeJobId) return
    pollRef.current = setInterval(async () => {
      try {
        const job = await smartTrailerService.pollJob(activeJobId)
        setJobs(prev => prev.map(j => j.id === job.id ? job : j))
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollRef.current!)
          setActiveJobId(null)
          if (job.status === 'done') toast('Smart trailer generated successfully!')
          else toast(job.error_message ?? 'Smart trailer generation failed.', 'error')
        }
      } catch { /* retry next tick */ }
    }, POLL_INTERVAL_MS)
    return () => clearInterval(pollRef.current!)
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

  if (loadingJobs) {
    return (
      <div className="flex justify-center py-12">
        <Loader2 size={24} className="text-slate-500 animate-spin" />
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <Card variant="gradient" className="flex flex-col items-center py-16 text-center">
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
          style={{ background: 'linear-gradient(135deg,#2563EB14,#7C3AED14)', border: '1px solid #2563EB20' }}
        >
          <Sparkles size={28} className="text-slate-500" />
        </div>
        <p className="text-slate-300 font-medium">No smart trailers yet</p>
        <p className="text-slate-500 text-sm mt-1">Go to Upload → Smart Trailer to generate one.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-4">

      {/* Active job banner */}
      {activeJob && (activeJob.status === 'pending' || activeJob.status === 'processing') && (
        <div
          className="flex items-center gap-3 rounded-lg px-4 py-3"
          style={{
            background: 'linear-gradient(135deg,#2563EB0A,#7C3AED08)',
            border: '1px solid #2563EB20',
            borderLeft: '3px solid #2563EB',
          }}
        >
          <Loader2 size={16} className="text-primary animate-spin shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-slate-200 text-sm font-medium">{STATUS_LABEL[activeJob.status]}</p>
            <p className="text-slate-500 text-xs mt-0.5">
              ClipSense is analysing the sample trailer and planning clips from raw footage…
            </p>
          </div>
          <button
            onClick={handleCancel}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors shrink-0"
          >
            <Square size={11} /> Stop
          </button>
        </div>
      )}

      {/* Job list */}
      <div className="space-y-2">
        {jobs.map(job => (
          <div
            key={job.id}
            className="rounded-lg overflow-hidden"
            style={{
              border: `1px solid ${STATUS_COLOR[job.status]}20`,
              borderLeft: `3px solid ${STATUS_COLOR[job.status]}`,
            }}
          >
            <div
              className={`flex items-center gap-3 px-4 py-3 ${job.status === 'done' && onSelectJob ? 'cursor-pointer' : ''}`}
              style={{ background: 'linear-gradient(145deg,#0E1525,#141E30)' }}
              onClick={() => job.status === 'done' && onSelectJob?.(job.id)}
            >
              {job.status === 'done'   && <CheckCircle size={14} className="text-green-400 shrink-0" />}
              {job.status === 'failed' && <XCircle     size={14} className="text-red-400 shrink-0" />}
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
                <p className="text-xs text-slate-600 truncate mt-0.5">
                  {job.raw_footage_name} + {job.sample_trailer_name}
                </p>
                {job.error_message && <p className="text-red-400 text-xs mt-0.5 truncate">{job.error_message}</p>}
              </div>
              {job.clip_score != null && (
                <span className="text-xs text-yellow-400 font-mono shrink-0">
                  {Math.round(job.clip_score * 100)}%
                </span>
              )}
              <span className="text-xs text-slate-600 shrink-0 hidden sm:inline">
                {new Date(job.updated_at).toLocaleString()}
              </span>
              {job.status === 'failed' && (
                <button onClick={e => { e.stopPropagation(); handleRetry(job) }} className="text-slate-600 hover:text-slate-300 transition-colors shrink-0">
                  <RefreshCw size={13} />
                </button>
              )}
              {(job.status === 'done' || job.status === 'failed') && (
                <button onClick={e => { e.stopPropagation(); handleDelete(job.id) }} className="text-slate-600 hover:text-red-400 transition-colors shrink-0">
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
