import { useRef, useState, DragEvent, ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Brain, UploadCloud, FileJson, FileText, X, CheckCircle,
  Database, ChevronDown, ChevronRight, Trash2, Pencil, Download, BarChart2, Info,
} from 'lucide-react'
import { AnalysisResult, StoredDataset } from '../types/analysis'
import { feedbackService } from '../services/feedbackService'
import { useToast } from '../context/ToastContext'
import Button from './Button'
import Card from './Card'
import ProgressBar from './ProgressBar'
import FeedbackSummaryCard from './FeedbackSummaryCard'
import TimelineInsights from './TimelineInsights'
import OptimizationRecommendations from './OptimizationRecommendations'
import { formatFileSize } from '../utils/format'

const ACCEPTED_EXTENSIONS = ['.json', '.csv', '.txt']
const ACCEPTED_MIME = 'application/json,text/csv,text/plain'

interface Props {
  projectId: string
  datasets: StoredDataset[]
  onDatasetsChange: (datasets: StoredDataset[]) => void
  /** Read-only datasets shown with a "Sample Trailer" disclaimer (smart trailer use) */
  sampleDatasets?: StoredDataset[]
  /** When true, hides the upload form — used for smart trailer detail view */
  readOnly?: boolean
}
interface SelectedFile { file: File; ext: string }

export default function AudienceFeedbackPanel({ projectId, datasets, onDatasetsChange, sampleDatasets, readOnly }: Props) {
  const { toast }    = useToast()
  const navigate     = useNavigate()
  const inputRef     = useRef<HTMLInputElement>(null)

  const [selected, setSelected]   = useState<SelectedFile | null>(null)
  const [dragOver, setDragOver]   = useState(false)
  const [uploading, setUploading] = useState(false)
  const [progress, setProgress]   = useState(0)
  const [result, setResult]       = useState<AnalysisResult | null>(null)
  const [fileError, setFileError] = useState<string | null>(null)
  const [expanded, setExpanded]   = useState<string | null>(null)
  const [deleting, setDeleting]   = useState<string | null>(null)
  const [renaming, setRenaming]   = useState<string | null>(null)
  const [renameVal, setRenameVal] = useState('')

  async function loadDatasets() {
    try { onDatasetsChange(await feedbackService.listDatasets(projectId)) }
    catch { /* non-critical */ }
  }

  function validateAndSet(file: File) {
    const ext = '.' + (file.name.split('.').pop()?.toLowerCase() ?? '')
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setFileError(`Unsupported format "${ext}". Upload a .json, .csv, or .txt file.`)
      return
    }
    setFileError(null)
    setSelected({ file, ext })
    setResult(null)
  }

  function onInputChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) validateAndSet(file)
    e.target.value = ''
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) validateAndSet(file)
  }

  function clearSelection() {
    setSelected(null); setResult(null); setProgress(0); setFileError(null)
  }

  async function handleUpload() {
    if (!selected) return
    setUploading(true); setProgress(0)
    try {
      const data = await feedbackService.uploadFeedbackFile(projectId, selected.file, setProgress)
      setResult(data)
      toast(`Dataset saved — ${data.timeline_insights.length} segments analysed.`)
      loadDatasets()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        ?? 'Upload failed. Check the file format and try again.'
      toast(msg, 'error')
    } finally { setUploading(false) }
  }

  async function handleDelete(datasetId: string) {
    setDeleting(datasetId)
    try {
      await feedbackService.deleteDataset(datasetId)
      onDatasetsChange(datasets.filter(d => d.id !== datasetId))
      if (result?.dataset_id === datasetId) setResult(null)
      toast('Dataset deleted.')
    } catch { toast('Failed to delete dataset.', 'error') }
    finally { setDeleting(null) }
  }

  function startRename(ds: StoredDataset) { setRenaming(ds.id); setRenameVal(ds.name ?? '') }

  async function commitRename(datasetId: string) {
    try {
      const updated = await feedbackService.renameDataset(datasetId, renameVal)
      onDatasetsChange(datasets.map(d => d.id === datasetId ? { ...d, name: updated.name } : d))
    } catch { toast('Failed to rename dataset.', 'error') }
    finally { setRenaming(null) }
  }

  function fileIcon(ext: string) {
    if (ext === '.json') return <FileJson size={20} className="text-primary" />
    if (ext === '.csv')  return <FileText size={20} className="text-primary" />
    return <FileText size={20} className="text-slate-400" />
  }

  return (
    <div className="space-y-6">

      {/* ── Upload panel — hidden in readOnly mode ────────────────────────── */}
      {!readOnly && (
      <Card className="space-y-5">

        <div className="flex items-center gap-2">
          <Brain size={16} className="text-primary" />
          <h2 className="font-semibold text-slate-100">Audience Feedback Dataset</h2>
        </div>

        <p className="text-sm text-slate-400 leading-relaxed">
          Upload a feedback file for this video.{' '}
          <span className="text-slate-300 font-medium">.json</span> and{' '}
          <span className="text-slate-300 font-medium">.csv</span> use the structured parser.{' '}
          <span className="text-slate-300 font-medium">.txt</span> is parsed automatically.
        </p>

        {/* Drop zone */}
        {!selected && (
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
              dragOver ? 'border-primary bg-primary/10' : 'border-surface-border hover:border-primary/50 hover:bg-surface-card'
            }`}
          >
            <UploadCloud size={36} className={`mx-auto mb-3 ${dragOver ? 'text-primary' : 'text-slate-500'}`} />
            <p className="text-slate-300 font-medium text-sm">Drag & drop or click to select</p>
            <p className="text-slate-500 text-xs mt-1">.json · .csv · .txt</p>
            <input ref={inputRef} type="file" accept={ACCEPTED_MIME} className="hidden" onChange={onInputChange} />
          </div>
        )}

        {fileError && <p className="text-red-400 text-sm">⚠ {fileError}</p>}

        {/* Selected file card */}
        {selected && (
          <div className="bg-surface border border-surface-border rounded-lg p-4 space-y-3">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-primary/10 rounded-lg shrink-0">
                {fileIcon(selected.ext)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 text-sm font-medium truncate">{selected.file.name}</p>
                <p className="text-slate-500 text-xs mt-0.5">
                  {formatFileSize(selected.file.size)} · {selected.ext.toUpperCase()}
                </p>
              </div>
              <button onClick={clearSelection} disabled={uploading} className="text-slate-500 hover:text-slate-300 disabled:opacity-40 shrink-0">
                <X size={16} />
              </button>
            </div>

            {uploading && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-xs text-slate-400">
                  <span>Uploading & analysing…</span>
                  <span>{progress}%</span>
                </div>
                <ProgressBar percent={progress} />
              </div>
            )}

            {result && !uploading && (
              <div className="flex items-center gap-2 text-green-400 text-xs font-medium">
                <CheckCircle size={13} /> Saved · dataset_id: {result.dataset_id.slice(0, 8)}…
              </div>
            )}

            {!result && (
              <div className="flex gap-3 pt-1">
                <Button onClick={handleUpload} loading={uploading} icon={<Database size={14} />} className="flex-1 justify-center">
                  {uploading ? 'Processing…' : 'Upload & Analyse'}
                </Button>
                <Button variant="ghost" onClick={clearSelection} disabled={uploading}>Cancel</Button>
              </div>
            )}

            {result && !uploading && (
              <Button variant="ghost" icon={<UploadCloud size={14} />} onClick={clearSelection} className="w-full justify-center">
                Upload another dataset
              </Button>
            )}
          </div>
        )}

        {/* Format reference */}
        <details>
          <summary className="text-xs text-slate-500 cursor-pointer hover:text-slate-300 select-none">View expected file formats</summary>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-surface rounded-lg p-3 border border-surface-border">
              <p className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5"><FileJson size={12} /> feedback.json</p>
              <pre className="text-xs text-slate-400 leading-relaxed overflow-x-auto">{`[\n  {\n    "timestamp": "00:34",\n    "topic": "Camera",\n    "sentiment": "Positive",\n    "summary": "Great shot",\n    "confidence": 0.92\n  }\n]`}</pre>
            </div>
            <div className="bg-surface rounded-lg p-3 border border-surface-border">
              <p className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5"><FileText size={12} /> feedback.csv</p>
              <pre className="text-xs text-slate-400 leading-relaxed overflow-x-auto">{`timestamp,topic,sentiment,summary,confidence\n00:34,Camera,Positive,Great shot,0.92\n,Music,Negative,Too loud,0.85`}</pre>
            </div>
            <div className="bg-surface rounded-lg p-3 border border-surface-border">
              <p className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
                <FileText size={12} /> feedback.txt
              </p>
              <pre className="text-xs text-slate-400 leading-relaxed overflow-x-auto">{`The intro at 0:30 felt too slow.\nLoved the product demo — very clear!\nBackground music was way too loud.`}</pre>
            </div>
          </div>
        </details>
      </Card>
      )}

      {/* ── Analysis results ─────────────────────────────────────────────── */}
      {result && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <FeedbackSummaryCard summary={result.feedback_summary} />
            <div className="lg:col-span-2">
              <TimelineInsights insights={result.timeline_insights} />
            </div>
          </div>
          <OptimizationRecommendations recommendations={result.optimization_recommendations} />
        </>
      )}

      {/* ── Saved Datasets ───────────────────────────────────────────────── */}
      {(datasets.length > 0 || (sampleDatasets?.length ?? 0) > 0) && (
        <Card className="space-y-3">
          <div className="flex items-center gap-2">
            <Database size={16} className="text-primary" />
            <h2 className="font-semibold text-slate-100">Saved Datasets</h2>
            <span className="ml-auto text-xs text-slate-500">
              {datasets.length + (sampleDatasets?.length ?? 0)} dataset{(datasets.length + (sampleDatasets?.length ?? 0)) !== 1 ? 's' : ''}
            </span>
          </div>

          <div className="space-y-2">
            {/* ── Sample trailer datasets (read-only) ── */}
            {sampleDatasets?.map(ds => (
              <div key={ds.id} className="border border-amber-500/20 rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-3 bg-amber-500/5 hover:bg-amber-500/10 transition-colors">
                  <button onClick={() => setExpanded(expanded === ds.id ? null : ds.id)} className="text-slate-400 shrink-0">
                    {expanded === ds.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>
                  <button onClick={() => setExpanded(expanded === ds.id ? null : ds.id)} className="flex-1 min-w-0 text-left">
                    <span className="text-slate-300 text-sm font-medium truncate block">
                      {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`}
                    </span>
                  </button>
                  <span className="text-xs text-slate-500 shrink-0">{ds.segment_count} seg{ds.segment_count !== 1 ? 's' : ''}</span>
                  <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-400 border border-amber-500/25 shrink-0">
                    <Info size={10} /> Sample Trailer
                  </span>
                </div>
                {expanded === ds.id && (
                  <>
                    <div className="px-4 py-2 bg-amber-500/5 border-t border-amber-500/15">
                      <p className="text-xs text-amber-400/80 flex items-start gap-1.5">
                        <Info size={11} className="shrink-0 mt-0.5" />
                        This dataset was derived from the audience comments uploaded with the sample trailer. It is read-only.
                      </p>
                    </div>
                    <div className="border-t border-amber-500/15 divide-y divide-surface-border">
                      {ds.segments.map(seg => (
                        <div key={seg.id} className="flex items-start gap-3 px-4 py-2.5 text-xs">
                          <span className="text-slate-600 w-10 shrink-0">{seg.timestamp ?? '—'}</span>
                          <span className="text-slate-400 w-24 shrink-0 truncate">{seg.topic}</span>
                          <span className="shrink-0 px-1.5 py-0.5 rounded text-xs font-medium" style={{
                            background: seg.sentiment === 'Positive' || seg.sentiment === 'Praise'
                              ? '#D4A84318' : seg.sentiment === 'Negative' || seg.sentiment === 'Complaint'
                              ? '#F8717118' : '#8B7CF618',
                            color: seg.sentiment === 'Positive' || seg.sentiment === 'Praise'
                              ? '#D4A843' : seg.sentiment === 'Negative' || seg.sentiment === 'Complaint'
                              ? '#F87171' : '#8B7CF6',
                          }}>{seg.sentiment}</span>
                          <span className="text-slate-400 flex-1">{seg.summary}</span>
                          <span className="text-slate-600 shrink-0">{Math.round(seg.confidence * 100)}%</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ))}

            {/* ── Regular editable datasets ── */}
            {datasets.map(ds => (
              <div key={ds.id} className="border border-surface-border rounded-lg overflow-hidden">
                <div className="flex items-center gap-2 px-4 py-3 bg-surface hover:bg-surface-card transition-colors">
                  <button onClick={() => setExpanded(expanded === ds.id ? null : ds.id)} className="text-slate-400 shrink-0">
                    {expanded === ds.id ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  </button>

                  {renaming === ds.id ? (
                    <input
                      autoFocus
                      value={renameVal}
                      onChange={e => setRenameVal(e.target.value)}
                      onBlur={() => commitRename(ds.id)}
                      onKeyDown={e => {
                        if (e.key === 'Enter') commitRename(ds.id)
                        if (e.key === 'Escape') setRenaming(null)
                      }}
                      className="flex-1 min-w-0 bg-surface-border text-slate-100 text-sm px-2 py-0.5 rounded outline-none focus:ring-1 focus:ring-primary"
                      placeholder="Dataset name…"
                    />
                  ) : (
                    <button onClick={() => setExpanded(expanded === ds.id ? null : ds.id)} className="flex-1 min-w-0 text-left">
                      <span className="text-slate-300 text-sm font-medium truncate block">
                        {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`}
                      </span>
                    </button>
                  )}

                  <span className="text-xs text-slate-500 shrink-0">{ds.segment_count} seg{ds.segment_count !== 1 ? 's' : ''}</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-surface-border text-slate-400 shrink-0 capitalize hidden sm:inline">
                    {ds.source.replace(/_/g, ' ')}
                  </span>
                  <span className="text-xs text-slate-600 shrink-0 hidden md:inline">
                    {new Date(ds.created_at).toLocaleString()}
                  </span>
                  <a href={feedbackService.exportDatasetUrl(ds.id)} download title="Export as Excel" className="text-slate-600 hover:text-green-400 transition-colors shrink-0">
                    <Download size={13} />
                  </a>
                  <button onClick={() => navigate(`/analytics?project=${projectId}&dataset=${ds.id}`)} className="text-slate-600 hover:text-primary transition-colors shrink-0" title="View analytics dashboard">
                    <BarChart2 size={13} />
                  </button>
                  <button onClick={() => renaming === ds.id ? setRenaming(null) : startRename(ds)} className="text-slate-600 hover:text-slate-300 transition-colors shrink-0" title="Rename dataset">
                    <Pencil size={13} />
                  </button>
                  <button onClick={() => handleDelete(ds.id)} disabled={deleting === ds.id} className="text-slate-600 hover:text-red-400 transition-colors disabled:opacity-40 shrink-0" title="Delete dataset">
                    <Trash2 size={13} />
                  </button>
                </div>

                {expanded === ds.id && (
                  <div className="border-t border-surface-border divide-y divide-surface-border">
                    {ds.segments.map(seg => (
                      <div key={seg.id} className="flex items-start gap-3 px-4 py-2.5 text-xs">
                        <span className="text-slate-600 w-10 shrink-0">{seg.timestamp ?? '—'}</span>
                        <span className="text-slate-400 w-24 shrink-0 truncate">{seg.topic}</span>
                        <span className="shrink-0 px-1.5 py-0.5 rounded text-xs font-medium" style={{
                          background: seg.sentiment === 'Positive' || seg.sentiment === 'Praise'
                            ? '#D4A84318' : seg.sentiment === 'Negative' || seg.sentiment === 'Complaint'
                            ? '#F8717118' : '#8B7CF618',
                          color: seg.sentiment === 'Positive' || seg.sentiment === 'Praise'
                            ? '#D4A843' : seg.sentiment === 'Negative' || seg.sentiment === 'Complaint'
                            ? '#F87171' : '#8B7CF6',
                        }}>{seg.sentiment}</span>
                        <span className="text-slate-400 flex-1">{seg.summary}</span>
                        <span className="text-slate-600 shrink-0">{Math.round(seg.confidence * 100)}%</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

    </div>
  )
}
