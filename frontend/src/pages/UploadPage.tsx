import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Film, Clapperboard, MessageSquare,
  Upload, CheckCircle, X, HardDrive, BarChart2, Zap,
} from 'lucide-react'
import { uploadService } from '../services/uploadService'
import { useToast } from '../context/ToastContext'
import Button from '../components/Button'
import Card from '../components/Card'
import ProgressBar from '../components/ProgressBar'
import { formatFileSize } from '../utils/format'

// ── Reusable file picker ──────────────────────────────────────────────────────

interface FileInputProps {
  label: string
  hint: string
  accept: string
  file: File | null
  onChange: (f: File | null) => void
  icon: React.ReactNode
  required?: boolean
}

function FileInput({ label, hint, accept, file, onChange, icon, required }: FileInputProps) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <span className="text-sm font-medium text-slate-200">{label}</span>
        {required && <span className="text-xs text-red-400">*</span>}
      </div>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        className={`flex items-center gap-3 px-4 py-3 rounded-xl border text-sm transition-all text-left
          ${file
            ? 'border-primary/50 bg-primary/8 text-primary'
            : 'border-surface-border text-slate-400 hover:border-slate-500 hover:text-slate-200 hover:bg-surface-card'
          }`}
      >
        <span className="shrink-0 opacity-70">{icon}</span>
        <span className="flex-1 min-w-0">
          {file ? (
            <span className="flex flex-col gap-0.5">
              <span className="truncate font-medium text-slate-100">{file.name}</span>
              <span className="text-xs text-slate-500">{formatFileSize(file.size)}</span>
            </span>
          ) : (
            <span className="flex flex-col gap-0.5">
              <span>Choose {label}…</span>
              <span className="text-xs text-slate-600">{hint}</span>
            </span>
          )}
        </span>
        {file && (
          <span
            role="button"
            aria-label={`Remove ${label}`}
            onClick={e => { e.stopPropagation(); onChange(null) }}
            className="shrink-0 text-slate-500 hover:text-red-400 transition-colors p-1"
          >
            <X size={14} />
          </span>
        )}
      </button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={e => onChange(e.target.files?.[0] ?? null)}
      />
    </div>
  )
}

// ── Success modal ─────────────────────────────────────────────────────────────

interface SuccessModalProps {
  projectId: string
  datasetId: string
  onClose: () => void
}

function SuccessModal({ projectId, datasetId, onClose }: SuccessModalProps) {
  const navigate = useNavigate()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)' }}>
      <div className="relative w-full max-w-md rounded-2xl p-8 animate-fade-in"
        style={{
          background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
          border: '1px solid #2A2A40',
          boxShadow: '0 24px 80px 0 #00000090',
        }}>

        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-slate-500 hover:text-slate-300 transition-colors"
        >
          <X size={18} />
        </button>

        {/* Icon */}
        <div className="flex justify-center mb-5">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg,#22c55e20,#16a34a18)', border: '1px solid #22c55e30' }}>
            <CheckCircle size={32} className="text-green-400" />
          </div>
        </div>

        {/* Message */}
        <h2 className="text-xl font-bold text-center text-slate-100 mb-2">
          Upload Successful
        </h2>
        <p className="text-sm text-center text-slate-400 mb-8 leading-relaxed">
          Your project has been created. To perform Sentiment Analysis, go to the{' '}
          <span className="text-primary font-medium">Analytics</span> tab.
        </p>

        {/* Navigation buttons */}
        <div className="flex flex-col gap-3">
          <Button
            onClick={() => navigate(`/analytics?project=${projectId}&dataset=${datasetId}`)}
            icon={<BarChart2 size={15} />}
            className="w-full justify-center"
          >
            Go to Analytics
          </Button>
          <Button
            variant="ghost"
            onClick={() => navigate(`/trailers?project=${projectId}`)}
            icon={<Zap size={15} />}
            className="w-full justify-center"
          >
            Go to Video Generation
          </Button>
          <Button
            variant="ghost"
            onClick={onClose}
            className="w-full justify-center text-slate-500"
          >
            Upload Another Project
          </Button>
        </div>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const { toast } = useToast()

  const [rawFootage,    setRawFootage]    = useState<File | null>(null)
  const [sampleTrailer, setSampleTrailer] = useState<File | null>(null)
  const [feedbackFile,  setFeedbackFile]  = useState<File | null>(null)
  const [projectName,   setProjectName]   = useState('')

  const [uploading,  setUploading]  = useState(false)
  const [progress,   setProgress]   = useState(0)
  const [successInfo, setSuccessInfo] = useState<{ projectId: string; datasetId: string } | null>(null)

  const canUpload = rawFootage && sampleTrailer && feedbackFile && !uploading

  async function handleUpload() {
    if (!rawFootage || !sampleTrailer || !feedbackFile) return
    setUploading(true)
    setProgress(0)
    try {
      const result = await uploadService.uploadProject(
        rawFootage,
        sampleTrailer,
        feedbackFile,
        projectName.trim() || undefined,
        pct => setProgress(pct),
      )
      setSuccessInfo({
        projectId: result.project.id,
        datasetId: result.dataset_id,
      })
      // Reset form
      setRawFootage(null)
      setSampleTrailer(null)
      setFeedbackFile(null)
      setProjectName('')
      setProgress(0)
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail
      toast(detail ?? 'Upload failed. Please try again.', 'error')
    } finally {
      setUploading(false)
    }
  }

  return (
    <>
      <div className="max-w-xl mx-auto space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Upload Project</h1>
          <p className="text-slate-400 mt-1 text-sm">
            Provide your raw footage, a sample trailer, and audience feedback to create a project.
          </p>
        </div>

        <Card className="space-y-5">

          {/* Project name */}
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-200">Project Name</span>
            <input
              type="text"
              value={projectName}
              onChange={e => setProjectName(e.target.value)}
              placeholder="e.g. Summer Campaign 2025"
              maxLength={255}
              className="w-full rounded-xl border border-surface-border bg-surface px-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 outline-none focus:ring-1 focus:ring-primary transition-colors"
            />
            <span className="text-xs text-slate-600">Optional — used as a display label for this project.</span>
          </div>

          <div className="h-px bg-surface-border" />

          {/* File inputs */}
          <div className="space-y-4">
            <FileInput
              label="Raw Footage"
              hint="MP4, MOV, AVI, MKV, WEBM · Max 10 GB"
              accept="video/*"
              file={rawFootage}
              onChange={setRawFootage}
              icon={<Film size={16} />}
              required
            />
            <FileInput
              label="Sample Trailer"
              hint="Reference trailer for style analysis · Max 10 GB"
              accept="video/*"
              file={sampleTrailer}
              onChange={setSampleTrailer}
              icon={<Clapperboard size={16} />}
              required
            />
            <FileInput
              label="Audience Feedback"
              hint=".json, .csv, or .txt · Structured or unstructured"
              accept=".json,.csv,.txt"
              file={feedbackFile}
              onChange={setFeedbackFile}
              icon={<MessageSquare size={16} />}
              required
            />
          </div>

          {/* Progress */}
          {uploading && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-slate-400">
                <span>Uploading…</span>
                <span>{progress}%</span>
              </div>
              <ProgressBar percent={progress} />
            </div>
          )}

          {/* File summary when all selected */}
          {rawFootage && sampleTrailer && feedbackFile && !uploading && (
            <div className="rounded-xl p-3 space-y-1.5"
              style={{ background: 'rgba(212,168,67,0.05)', border: '1px solid rgba(212,168,67,0.15)' }}>
              <p className="text-xs font-medium text-slate-400 mb-2">Ready to upload</p>
              {[
                { label: 'Raw Footage',    file: rawFootage,    icon: <Film size={11} /> },
                { label: 'Sample Trailer', file: sampleTrailer, icon: <Clapperboard size={11} /> },
                { label: 'Feedback',       file: feedbackFile,  icon: <MessageSquare size={11} /> },
              ].map(({ label, file, icon }) => (
                <div key={label} className="flex items-center gap-2 text-xs text-slate-400">
                  <span className="text-primary">{icon}</span>
                  <span className="font-medium text-slate-300 w-28 shrink-0">{label}</span>
                  <span className="truncate flex-1 text-slate-500">{file.name}</span>
                  <span className="shrink-0 flex items-center gap-1 text-slate-600">
                    <HardDrive size={10} /> {formatFileSize(file.size)}
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Submit */}
          <Button
            onClick={handleUpload}
            loading={uploading}
            disabled={!canUpload}
            icon={<Upload size={15} />}
            className="w-full justify-center"
          >
            {uploading ? 'Uploading…' : 'Upload Project'}
          </Button>

          <p className="text-xs text-slate-600 text-center">
            All three files are required. Feedback is parsed automatically.
          </p>
        </Card>
      </div>

      {/* Success modal */}
      {successInfo && (
        <SuccessModal
          projectId={successInfo.projectId}
          datasetId={successInfo.datasetId}
          onClose={() => setSuccessInfo(null)}
        />
      )}
    </>
  )
}
