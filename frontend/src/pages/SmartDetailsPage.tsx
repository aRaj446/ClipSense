import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, Trash2, Sparkles, Film, Clapperboard,
  HardDrive, Calendar, Zap, Clock,
  TrendingUp, TrendingDown, MessageSquare,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { SmartTrailerJob, StoredDataset } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import VideoPlayer from '../components/VideoPlayer'
import Button from '../components/Button'
import Card from '../components/Card'
import Modal from '../components/Modal'
import LoadingSpinner from '../components/LoadingSpinner'
import AudienceFeedbackPanel from '../components/AudienceFeedbackPanel'
import { formatDate } from '../utils/format'

// ── MetaRow — identical to ProjectDetailsEmbed ────────────────────────────────

function MetaRow({ icon, label, value, truncate = false }: {
  icon: ReactNode; label: string; value: string; truncate?: boolean
}) {
  return (
    <div className={`py-3 border-b border-surface-border last:border-0 ${
      truncate ? 'flex flex-col gap-1' : 'flex items-center justify-between'
    }`}>
      <span className="flex items-center gap-2 text-slate-400 text-sm shrink-0">{icon}{label}</span>
      <span className="text-slate-100 text-sm font-medium truncate" title={value}>{value}</span>
    </div>
  )
}

// ── AnalysisReport ────────────────────────────────────────────────────────────

function AnalysisReport({ report }: { report: SmartTrailerJob['analysis_report'] }) {
  if (!report) return null
  return (
    <Card className="space-y-4">
      <h3 className="font-semibold text-slate-100 flex items-center gap-2">
        <Sparkles size={15} className="text-primary" /> Analysis Report
      </h3>
      <div className="flex items-start gap-2 text-sm text-slate-300 bg-surface rounded-lg px-3 py-2.5">
        <MessageSquare size={14} className="text-primary shrink-0 mt-0.5" />
        <span>{report.sentiment_summary}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="space-y-2">
          <p className="text-xs font-semibold text-green-400 flex items-center gap-1">
            <TrendingUp size={12} /> Positive Patterns
          </p>
          <ul className="space-y-1.5">
            {report.positive_patterns.map((p, i) => (
              <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                <span className="text-green-500 shrink-0 mt-0.5">+</span>{p}
              </li>
            ))}
          </ul>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-semibold text-red-400 flex items-center gap-1">
            <TrendingDown size={12} /> Negative Patterns
          </p>
          <ul className="space-y-1.5">
            {report.negative_patterns.map((p, i) => (
              <li key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                <span className="text-red-500 shrink-0 mt-0.5">−</span>{p}
              </li>
            ))}
          </ul>
        </div>
      </div>
      {report.top_scene_categories.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {report.top_scene_categories.map((cat, i) => (
            <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              {cat}
            </span>
          ))}
        </div>
      )}
      <p className="text-xs text-slate-500 italic leading-relaxed">{report.influence_explanation}</p>
    </Card>
  )
}

// ── SmartDetailsPage ──────────────────────────────────────────────────────────

interface Props {
  jobId: string
  onBack: () => void
}

export default function SmartDetailsPage({ jobId, onBack }: Props) {
  const { toast } = useToast()

  const [job,         setJob]         = useState<SmartTrailerJob | null>(null)
  const [sampleDs,    setSampleDs]    = useState<StoredDataset | null>(null)
  const [loading,     setLoading]     = useState(true)
  const [error,       setError]       = useState<string | null>(null)
  const [deleteModal, setDeleteModal] = useState(false)
  const [deleting,    setDeleting]    = useState(false)
  const prevId = useRef<string | null>(null)

  useEffect(() => {
    if (prevId.current === jobId) return
    prevId.current = jobId
    setLoading(true)
    setError(null)
    setJob(null)
    setSampleDs(null)

    smartTrailerService.pollJob(jobId)
      .then(j => {
        setJob(j)
        // Build synthetic StoredDataset from analytics timeline for AudienceFeedbackPanel
        smartTrailerService.getAnalytics(jobId)
          .then(report => {
            const segs = report.timeline.map((pt, i) => ({
              id: String(i),
              position: i,
              timestamp: pt.timestamp,
              topic: pt.topic,
              sentiment: pt.sentiment,
              summary: pt.summary,
              confidence: pt.confidence,
              created_at: report.analyzed_at,
            }))
            setSampleDs({
              id: j.id,
              project_id: '',
              name: j.comments_name,
              source: 'smart',
              created_at: j.created_at,
              segment_count: segs.length,
              segments: segs,
            })
          })
          .catch(() => {/* analytics optional — panel still renders without it */})
      })
      .catch(() => setError('Smart trailer not found'))
      .finally(() => setLoading(false))
  }, [jobId])

  async function handleDelete() {
    if (!job) return
    setDeleting(true)
    try {
      await smartTrailerService.deleteJob(job.id)
      toast('Smart trailer deleted.')
      onBack()
    } catch {
      toast('Failed to delete.', 'error')
      setDeleting(false)
    }
  }

  if (loading) return <div className="flex justify-center py-16"><LoadingSpinner size={32} /></div>

  if (error || !job) {
    return (
      <div className="flex flex-col items-center py-16 gap-4 text-center">
        <Sparkles size={48} className="text-slate-600" />
        <p className="text-slate-300 font-medium">{error ?? 'Smart trailer not found'}</p>
        <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={onBack}>Back</Button>
      </div>
    )
  }

  const videoUrl = job.output_url ? smartTrailerService.trailerUrl(job.output_url) : null

  return (
    <>
      <div className="space-y-6">

        {/* ── Header — mirrors ProjectDetailsEmbed ── */}
        <div className="flex items-center gap-4">
          <div className="flex-1 min-w-0">
            <h2 className="text-xl font-bold text-slate-100 truncate">{job.raw_footage_name}</h2>
            <p className="text-slate-400 text-sm mt-0.5">{formatDate(job.created_at)}</p>
          </div>
          <span className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full bg-primary/15 text-primary border border-primary/20 font-medium">
            <Sparkles size={11} /> Smart Trailer
          </span>
        </div>

        {/* ── Video + Metadata card — mirrors ProjectDetailsEmbed grid ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* 2/3 — video player + delete */}
          <div className="lg:col-span-2 space-y-4">
            {videoUrl ? (
              <VideoPlayer src={videoUrl} />
            ) : (
              <div className="w-full rounded-xl bg-surface border border-surface-border aspect-video flex items-center justify-center">
                <Sparkles size={32} className="text-slate-700" />
              </div>
            )}
            <Button variant="danger" icon={<Trash2 size={16} />} onClick={() => setDeleteModal(true)}>
              Delete
            </Button>
          </div>

          {/* 1/3 — metadata card */}
          <Card className="self-start">
            <h3 className="font-semibold text-slate-100 mb-2 flex items-center gap-2">
              <Sparkles size={15} className="text-primary" /> Job Details
            </h3>
            <MetaRow icon={<Film size={14} />}         label="Raw Footage"    value={job.raw_footage_name}    truncate />
            <MetaRow icon={<Clapperboard size={14} />} label="Sample Trailer" value={job.sample_trailer_name} truncate />
            <MetaRow icon={<HardDrive size={14} />}    label="Comments File"  value={job.comments_name}       truncate />
            <MetaRow icon={<Calendar size={14} />}     label="Created"        value={formatDate(job.created_at)} />
            {job.clip_score != null && (
              <MetaRow icon={<Zap size={14} />} label="Clip Score" value={`${Math.round(job.clip_score * 100)}%`} />
            )}
            {job.editing_plan && (
              <MetaRow
                icon={<Clock size={14} />}
                label="Duration"
                value={`${Math.round(job.editing_plan.target_duration)}s · ${job.editing_plan.clips.length} clips`}
              />
            )}
          </Card>
        </div>

        {/* ── Audience Feedback — same AudienceFeedbackPanel as standard,
             sampleDatasets shows the comments dataset read-only with amber disclaimer,
             readOnly hides the upload form since smart trailers have no project_id ── */}
        <AudienceFeedbackPanel
          projectId={job.id}
          datasets={[]}
          onDatasetsChange={() => {}}
          sampleDatasets={sampleDs ? [sampleDs] : []}
          readOnly
        />

        {/* ── Analysis Report — smart-only section below datasets ── */}
        <AnalysisReport report={job.analysis_report} />

      </div>

      <Modal open={deleteModal} title="Delete Smart Trailer" onClose={() => setDeleteModal(false)}>
        <p className="text-slate-300 text-sm mb-6">
          Are you sure you want to delete{' '}
          <span className="font-medium text-slate-100">"{job.raw_footage_name}"</span>?
          This action cannot be undone.
        </p>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={() => setDeleteModal(false)}>Cancel</Button>
          <Button variant="danger" loading={deleting} onClick={handleDelete}>Delete</Button>
        </div>
      </Modal>
    </>
  )
}
