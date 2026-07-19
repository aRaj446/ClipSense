import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  ArrowLeft, Trash2, Film, Clock, HardDrive, Monitor, Calendar, Zap,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { Project } from '../types/project'
import { StoredDataset } from '../types/analysis'
import { projectService } from '../services/projectService'
import { feedbackService } from '../services/feedbackService'
import { useProjects } from '../context/ProjectContext'
import { useToast } from '../context/ToastContext'
import VideoPlayer from '../components/VideoPlayer'
import Button from '../components/Button'
import Card from '../components/Card'
import Modal from '../components/Modal'
import LoadingSpinner from '../components/LoadingSpinner'
import AudienceFeedbackPanel from '../components/AudienceFeedbackPanel'
import TrailerPanel from '../components/TrailerPanel'
import { formatDuration, formatFileSize, formatDate } from '../utils/format'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// ─── MetaRow ─────────────────────────────────────────────────────────────────

interface MetaRowProps { icon: ReactNode; label: string; value: string; truncate?: boolean }

function MetaRow({ icon, label, value, truncate = false }: MetaRowProps) {
  return (
    <div className={`py-3 border-b border-surface-border last:border-0 ${
      truncate ? 'flex flex-col gap-1' : 'flex items-center justify-between'
    }`}>
      <span className="flex items-center gap-2 text-slate-400 text-sm shrink-0">
        {icon}
        {label}
      </span>
      <span
        className="text-slate-100 text-sm font-medium truncate"
        title={value}
      >
        {value}
      </span>
    </div>
  )
}

// ─── ProjectDetails ───────────────────────────────────────────────────────────

export default function ProjectDetails() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { removeProject } = useProjects()
  const { toast } = useToast()

  const [project, setProject]   = useState<Project | null>(null)
  const [datasets, setDatasets] = useState<StoredDataset[]>([])
  const [loading, setLoading]   = useState(true)
  const [deleteModal, setDeleteModal] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [error, setError]       = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    projectService
      .getProject(id)
      .then(setProject)
      .catch(() => setError('Project not found'))
      .finally(() => setLoading(false))
  }, [id])

  // Load datasets once project id is known; refreshed by AudienceFeedbackPanel via onDatasetsChange
  useEffect(() => {
    if (!id) return
    feedbackService.listDatasets(id).then(setDatasets).catch(() => {})
  }, [id])

  async function handleDelete() {
    if (!project) return
    setDeleting(true)
    try {
      await removeProject(project.id)
      toast('Project deleted.')
      navigate('/')
    } catch {
      toast('Failed to delete project.', 'error')
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <LoadingSpinner size={36} />
      </div>
    )
  }

  if (error || !project) {
    return (
      <div className="flex flex-col items-center py-24 gap-4 text-center">
        <Film size={48} className="text-slate-600" />
        <p className="text-slate-300 font-medium">{error ?? 'Project not found'}</p>
        <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>
    )
  }

  const ext = project.filename.split('.').pop()?.toLowerCase() ?? 'mp4'
  const videoUrl = `${API_BASE}/uploads/${project.id}.${ext}`
  const resolution =
    project.width && project.height ? `${project.width}×${project.height}` : '—'

  return (
    <>
      <div className="max-w-6xl mx-auto space-y-6">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-slate-400 hover:text-slate-100 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-slate-100 truncate">{project.filename}</h1>
            <p className="text-slate-400 text-sm mt-0.5">{formatDate(project.upload_time)}</p>
          </div>
          <span className="text-xs px-3 py-1.5 rounded-full bg-blue-500/20 text-blue-400 font-medium capitalize">
            {project.status}
          </span>
        </div>

        {/* ── Video + Metadata ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Video player — 2 cols */}
          <div className="lg:col-span-2 space-y-4">
            <VideoPlayer src={videoUrl} />

            <div className="flex gap-3">
              <Button
                variant="danger"
                icon={<Trash2 size={16} />}
                onClick={() => setDeleteModal(true)}
              >
                Delete
              </Button>
            </div>
          </div>

          {/* Metadata — 1 col */}
          <Card className="self-start">
            <h2 className="font-semibold text-slate-100 mb-2 flex items-center gap-2">
              <Film size={16} className="text-primary" />
              Video Metadata
            </h2>
            <MetaRow icon={<Film size={14} />}      label="File Name"   value={project.filename} truncate />
            <MetaRow icon={<Monitor size={14} />}   label="Resolution"  value={resolution} />
            <MetaRow icon={<Clock size={14} />}     label="Duration"    value={formatDuration(project.duration)} />
            <MetaRow icon={<Calendar size={14} />}  label="Upload Date" value={formatDate(project.upload_time)} />
            <MetaRow icon={<HardDrive size={14} />} label="Size"        value={formatFileSize(project.size)} />
            <MetaRow icon={<Zap size={14} />}       label="FPS"         value={project.fps ? `${project.fps}` : '—'} />
            <MetaRow icon={<Film size={14} />}      label="Codec"       value={project.codec ?? '—'} />
          </Card>
        </div>

        {/* ── AI Audience Feedback Analysis ──────────────────────────────── */}
        <AudienceFeedbackPanel
          projectId={project.id}
          datasets={datasets}
          onDatasetsChange={setDatasets}
        />

        {/* ── Trailer Generation ───────────────────────────────────────────── */}
        <TrailerPanel
          projectId={project.id}
          datasets={datasets}
        />

      </div>

      {/* ── Delete confirmation modal ───────────────────────────────────── */}
      <Modal
        open={deleteModal}
        title="Delete Project"
        onClose={() => setDeleteModal(false)}
      >
        <p className="text-slate-300 text-sm mb-6">
          Are you sure you want to delete{' '}
          <span className="font-medium text-slate-100">"{project.filename}"</span>?
          This action cannot be undone.
        </p>
        <div className="flex gap-3 justify-end">
          <Button variant="ghost" onClick={() => setDeleteModal(false)}>
            Cancel
          </Button>
          <Button variant="danger" loading={deleting} onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </Modal>
    </>
  )
}
