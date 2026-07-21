import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle, FileVideo, Clock, HardDrive, X,
  Clapperboard, Film, MessageSquare, Sparkles, Loader2,
} from 'lucide-react'
import { uploadService } from '../services/uploadService'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import FileUploader from '../components/FileUploader'
import ProgressBar from '../components/ProgressBar'
import Button from '../components/Button'
import Card from '../components/Card'
import { formatFileSize, formatDuration } from '../utils/format'

interface PendingFile {
  file: File
  previewUrl: string
  duration: number | null
}

// ── Smart file input ──────────────────────────────────────────────────────────

function FileInput({
  label, accept, file, onChange, icon,
}: {
  label: string
  accept: string
  file: File | null
  onChange: (f: File | null) => void
  icon: React.ReactNode
}) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-slate-400 font-medium">{label}</span>
      <button
        type="button"
        onClick={() => ref.current?.click()}
        className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-colors text-left
          ${file
            ? 'border-primary/40 bg-primary/5 text-primary'
            : 'border-surface-border text-slate-400 hover:border-slate-500 hover:text-slate-200'
          }`}
      >
        {icon}
        <span className="truncate flex-1">{file ? file.name : `Choose ${label}…`}</span>
        {file && (
          <span
            role="button"
            onClick={e => { e.stopPropagation(); onChange(null) }}
            className="text-slate-500 hover:text-red-400 transition-colors shrink-0 text-xs"
          >
            ✕
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const navigate = useNavigate()
  const { toast } = useToast()
  const [mode, setMode] = useState<'standard' | 'smart'>('standard')

  // Standard state
  const [pending, setPending]     = useState<PendingFile | null>(null)
  const [progress, setProgress]   = useState(0)
  const [uploading, setUploading] = useState(false)

  // Smart state
  const [rawFootage,    setRawFootage]    = useState<File | null>(null)
  const [sampleTrailer, setSampleTrailer] = useState<File | null>(null)
  const [commentsFile,  setCommentsFile]  = useState<File | null>(null)
  const [smartUploading, setSmartUploading] = useState(false)
  const [smartPct,       setSmartPct]       = useState(0)

  // ── Standard handlers ──────────────────────────────────────────────────────

  function handleFile(file: File) {
    const previewUrl = URL.createObjectURL(file)
    const video = document.createElement('video')
    video.preload = 'metadata'
    video.src = previewUrl
    video.onloadedmetadata = () => setPending({ file, previewUrl, duration: video.duration || null })
    video.onerror = () => setPending({ file, previewUrl, duration: null })
  }

  function clearPending() {
    if (pending?.previewUrl) URL.revokeObjectURL(pending.previewUrl)
    setPending(null)
    setProgress(0)
  }

  async function handleUpload() {
    if (!pending) return
    setUploading(true)
    setProgress(0)
    try {
      const project = await uploadService.uploadVideo(pending.file, setProgress)
      toast('Video uploaded successfully!')
      clearPending()
      navigate(`/project/${project.id}`)
    } catch {
      toast('Upload failed. Please try again.', 'error')
      setUploading(false)
      setProgress(0)
    }
  }

  // ── Smart handlers ─────────────────────────────────────────────────────────

  const canGenerate = rawFootage && sampleTrailer && commentsFile && !smartUploading

  async function handleSmartGenerate() {
    if (!rawFootage || !sampleTrailer || !commentsFile) return
    setSmartUploading(true)
    setSmartPct(0)
    try {
      const job = await smartTrailerService.upload(
        rawFootage, sampleTrailer, commentsFile,
        pct => setSmartPct(pct),
      )
      await smartTrailerService.generate(job.id)
      toast('Files uploaded — generation started!')
      setRawFootage(null)
      setSampleTrailer(null)
      setCommentsFile(null)
      navigate('/trailers')
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Failed to start smart trailer generation.'
      toast(msg, 'error')
    } finally {
      setSmartUploading(false)
      setSmartPct(0)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-2xl mx-auto space-y-6">

      <div>
        <h1 className="text-2xl font-bold text-slate-100">Upload</h1>
        <p className="text-slate-400 mt-1">Upload a video project or generate a smart trailer</p>
      </div>

      {/* Toggle */}
      <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-lg w-fit">
        <button
          onClick={() => setMode('standard')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            mode === 'standard' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Clapperboard size={13} /> Standard
        </button>
        <button
          onClick={() => setMode('smart')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            mode === 'smart' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Sparkles size={13} /> Smart Trailer
        </button>
      </div>

      {/* ── Standard ── */}
      {mode === 'standard' && (
        <>
          <p className="text-slate-400 text-sm">MP4, MOV, AVI, MKV, WEBM · Max 10 GB</p>
          {!pending ? (
            <FileUploader onFile={handleFile} />
          ) : (
            <Card className="space-y-4">
              <video
                src={pending.previewUrl}
                controls
                className="w-full rounded-lg bg-black max-h-64"
                preload="metadata"
              />
              <div className="flex items-start gap-3">
                <div className="p-2 bg-primary/10 rounded-lg shrink-0">
                  <FileVideo size={20} className="text-primary" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-100 truncate">{pending.file.name}</p>
                  <div className="flex gap-4 mt-1 text-sm text-slate-400">
                    <span className="flex items-center gap-1">
                      <HardDrive size={12} />
                      {formatFileSize(pending.file.size)}
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock size={12} />
                      {formatDuration(pending.duration)}
                    </span>
                  </div>
                </div>
                <button
                  onClick={clearPending}
                  disabled={uploading}
                  className="text-slate-500 hover:text-slate-300 transition-colors disabled:opacity-50"
                >
                  <X size={18} />
                </button>
              </div>
              {uploading && (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-xs text-slate-400">
                    <span>Uploading...</span>
                    <span>{progress}%</span>
                  </div>
                  <ProgressBar percent={progress} />
                </div>
              )}
              <div className="flex gap-3 pt-2">
                <Button
                  onClick={handleUpload}
                  loading={uploading}
                  icon={<CheckCircle size={16} />}
                  className="flex-1 justify-center"
                >
                  {uploading ? 'Uploading...' : 'Upload Video'}
                </Button>
                <Button variant="ghost" onClick={clearPending} disabled={uploading}>
                  Cancel
                </Button>
              </div>
            </Card>
          )}
        </>
      )}

      {/* ── Smart ── */}
      {mode === 'smart' && (
        <Card className="space-y-5">
          <div className="flex items-center gap-2">
            <Sparkles size={15} className="text-primary" />
            <h2 className="font-semibold text-slate-100">Smart Trailer</h2>
            <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
              AI-Powered
            </span>
          </div>

          <p className="text-sm text-slate-400 leading-relaxed">
            Upload raw footage, a sample trailer, and audience comments. ClipSense analyses the
            sample trailer's editing style and audience sentiment to generate a new trailer
            from your raw footage.
          </p>

          <div className="space-y-3">
            <FileInput
              label="Raw Footage"
              accept="video/*"
              file={rawFootage}
              onChange={setRawFootage}
              icon={<Film size={14} className="shrink-0" />}
            />
            <FileInput
              label="Sample Trailer"
              accept="video/*"
              file={sampleTrailer}
              onChange={setSampleTrailer}
              icon={<Clapperboard size={14} className="shrink-0" />}
            />
            <FileInput
              label="Audience Comments (.json / .csv / .txt)"
              accept=".json,.csv,.txt"
              file={commentsFile}
              onChange={setCommentsFile}
              icon={<MessageSquare size={14} className="shrink-0" />}
            />
          </div>

          {smartUploading && smartPct > 0 && smartPct < 100 && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-slate-500">
                <span>Uploading files…</span>
                <span>{smartPct}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-slate-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary transition-all duration-150"
                  style={{ width: `${smartPct}%` }}
                />
              </div>
            </div>
          )}

          {smartUploading && smartPct >= 100 && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <Loader2 size={14} className="animate-spin text-primary" />
              Starting generation…
            </div>
          )}

          <Button
            onClick={handleSmartGenerate}
            loading={smartUploading}
            disabled={!canGenerate}
            icon={<Clapperboard size={14} />}
          >
            {smartUploading ? 'Uploading…' : 'Generate Smart Trailer'}
          </Button>
        </Card>
      )}
    </div>
  )
}
