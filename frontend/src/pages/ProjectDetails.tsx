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
import Modal from '../components/Modal'
import LoadingSpinner from '../components/LoadingSpinner'
import AudienceFeedbackPanel from '../components/AudienceFeedbackPanel'
import TrailerPanel from '../components/TrailerPanel'
import { formatDuration, formatFileSize, formatDate } from '../utils/format'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// ── MetaRow ───────────────────────────────────────────────────────────────────

interface MetaRowProps { icon: ReactNode; label: string; value: string; truncate?: boolean }

function MetaRow({ icon, label, value, truncate = false }: MetaRowProps) {
  return (
    <div className={`py-3 last:border-0 ${truncate ? 'flex flex-col gap-1' : 'flex items-center justify-between'}`}
      style={{ borderBottom: '1px solid #1E1E30' }}>
      <span className="flex items-center gap-2 text-sm shrink-0" style={{ color: '#5C5A72' }}>
        {icon} {label}
      </span>
      <span className="text-sm font-medium truncate" style={{ color: '#F0EDE8' }} title={value}>
        {value}
      </span>
    </div>
  )
}

// ── ProjectDetails ────────────────────────────────────────────────────────────

export default function ProjectDetails() {
  const { id }   = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { removeProject } = useProjects()
  const { toast }         = useToast()

  const [project,     setProject]     = useState<Project | null>(null)
  const [datasets,    setDatasets]    = useState<StoredDataset[]>([])
  const [loading,     setLoading]     = useState(true)
  const [deleteModal, setDeleteModal] = useState(false)
  const [deleting,    setDeleting]    = useState(false)
  const [error,       setError]       = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    projectService.getProject(id)
      .then(setProject)
      .catch(() => setError('Project not found'))
      .finally(() => setLoading(false))
  }, [id])

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
        <Film size={48} style={{ color: '#363654' }} />
        <p className="font-medium" style={{ color: '#A8A4B8' }}>{error ?? 'Project not found'}</p>
        <Button variant="ghost" icon={<ArrowLeft size={16} />} onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>
    )
  }

  const ext        = project.filename.split('.').pop()?.toLowerCase() ?? 'mp4'
  const videoUrl   = `${API_BASE}/uploads/${project.id}.${ext}`
  const resolution = project.width && project.height ? `${project.width}×${project.height}` : '—'

  return (
    <>
      <div className="max-w-6xl mx-auto space-y-6">

        {/* ── Page hero header ───────────────────────────────────────────── */}
        <div className="relative rounded-3xl overflow-hidden animate-fade-in"
          style={{ border: '1px solid #2A2A40', boxShadow: '0 8px 40px 0 #00000070' }}>

          {/* Gradient bg */}
          <div className="absolute inset-0"
            style={{ background: 'linear-gradient(135deg, #0C0C14 0%, #14102A 35%, #1A1230 60%, #0E1420 85%, #0C0C14 100%)' }} />

          {/* Blobs */}
          <div className="absolute -top-16 -left-16 w-72 h-72 rounded-full pointer-events-none animate-spin-slow"
            style={{ background: 'radial-gradient(circle, #D4A84320 0%, transparent 65%)', filter: 'blur(36px)' }} />
          <div className="absolute -bottom-16 -right-12 w-80 h-80 rounded-full pointer-events-none animate-float"
            style={{ background: 'radial-gradient(circle, #8B7CF616 0%, transparent 65%)', filter: 'blur(40px)', animationDelay: '2s' }} />

          {/* Grid */}
          <div className="absolute inset-0 pointer-events-none opacity-[0.025]"
            style={{ backgroundImage: 'linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px)', backgroundSize: '48px 48px' }} />

          {/* Bottom line */}
          <div className="absolute bottom-0 left-0 right-0 h-px"
            style={{ background: 'linear-gradient(90deg, transparent, #D4A84340, #8B7CF630, transparent)' }} />

          <div className="relative z-10 flex items-center gap-4 px-8 py-7">
            <button onClick={() => navigate('/')}
              className="p-2 rounded-xl transition-all hover:scale-105 shrink-0"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid #2A2A40', color: '#A8A4B8' }}>
              <ArrowLeft size={18} />
            </button>
            <div className="flex-1 min-w-0">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full mb-2"
                style={{ background: 'rgba(139,124,246,0.10)', border: '1px solid rgba(139,124,246,0.25)' }}>
                <Film size={11} style={{ color: '#8B7CF6' }} />
                <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#A78BFA' }}>
                  Project
                </span>
              </div>
              <h1 className="font-extrabold truncate bg-clip-text text-transparent"
                style={{
                  fontSize: 'clamp(1.25rem, 2.5vw, 2rem)',
                  backgroundImage: 'linear-gradient(120deg, #F5E6B8 0%, #E8C56A 30%, #D4A843 55%, #A78BFA 85%, #8B7CF6 100%)',
                  backgroundSize: '200% 200%',
                  animation: 'gradient-shift 6s ease infinite',
                }}>
                {project.filename}
              </h1>
              <p className="text-xs mt-1" style={{ color: '#5C5A72' }}>{formatDate(project.upload_time)}</p>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              <span className="text-xs px-3 py-1.5 rounded-full font-semibold capitalize"
                style={{ background: '#8B7CF618', color: '#A78BFA', border: '1px solid #8B7CF628' }}>
                {project.status}
              </span>
              <Button variant="danger" icon={<Trash2 size={14} />} onClick={() => setDeleteModal(true)}>
                Delete
              </Button>
            </div>
          </div>
        </div>

        {/* ── Video + Metadata ────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 animate-fade-in" style={{ animationDelay: '80ms' }}>

          {/* Video player */}
          <div className="lg:col-span-2">
            <div className="rounded-2xl overflow-hidden"
              style={{ border: '1px solid #252538', boxShadow: '0 4px 30px 0 #00000060' }}>
              <VideoPlayer src={videoUrl} />
            </div>
          </div>

          {/* Metadata card */}
          <div className="rounded-2xl p-5 self-start"
            style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #252538' }}>
            <h2 className="font-semibold mb-3 flex items-center gap-2" style={{ color: '#F0EDE8' }}>
              <Film size={14} style={{ color: '#D4A843' }} /> Video Metadata
            </h2>
            <MetaRow icon={<Film     size={13} />} label="File Name"   value={project.filename} truncate />
            <MetaRow icon={<Monitor  size={13} />} label="Resolution"  value={resolution} />
            <MetaRow icon={<Clock    size={13} />} label="Duration"    value={formatDuration(project.duration)} />
            <MetaRow icon={<Calendar size={13} />} label="Upload Date" value={formatDate(project.upload_time)} />
            <MetaRow icon={<HardDrive size={13} />} label="Size"       value={formatFileSize(project.size)} />
            <MetaRow icon={<Zap      size={13} />} label="FPS"         value={project.fps ? `${project.fps}` : '—'} />
            <MetaRow icon={<Film     size={13} />} label="Codec"       value={project.codec ?? '—'} />
          </div>
        </div>

        {/* ── Audience Feedback ───────────────────────────────────────────── */}
        <div className="animate-fade-in" style={{ animationDelay: '140ms' }}>
          <AudienceFeedbackPanel
            projectId={project.id}
            datasets={datasets}
            onDatasetsChange={setDatasets}
          />
        </div>

        {/* ── Trailer Generation ───────────────────────────────────────────── */}
        <div className="animate-fade-in" style={{ animationDelay: '200ms' }}>
          <TrailerPanel projectId={project.id} datasets={datasets} />
        </div>

      </div>

      {/* ── Delete modal ───────────────────────────────────────────────────── */}
      <Modal open={deleteModal} title="Delete Project" onClose={() => setDeleteModal(false)}>
        <p className="text-sm mb-6" style={{ color: '#A8A4B8' }}>
          Are you sure you want to delete{' '}
          <span className="font-medium" style={{ color: '#F0EDE8' }}>"{project.filename}"</span>?
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
