import { useEffect, useState, useRef, useCallback } from 'react'
import {
  Film, Database, BarChart2, Play, Loader2, CheckCircle, XCircle,
  RefreshCw, Download, Clock, Wand2, AlertCircle, ChevronDown,
  ChevronUp, Zap, Square, RotateCcw,
} from 'lucide-react'
import { Project } from '../types/project'
import { ProjectAnalyticsStatus, ProjectTrailerListItem, projectService } from '../services/projectService'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import Card from './Card'
import JobProgressPanel, { ProgressStep } from './JobProgressPanel'

const POLL_MS = 3000

const CREATIVE_CHIPS = [
  'Focus on action',
  'Emphasize emotional moments',
  'Fast-paced trailer',
  'Focus on product features',
  'More suspense',
  'More character moments',
]

function fmt(secs: number) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function MetricPill({
  value, label, color, bg, border,
}: { value: string | number; label: string; color: string; bg: string; border: string }) {
  return (
    <div className="rounded-xl px-4 py-3 text-center" style={{ background: bg, border: `1px solid ${border}` }}>
      <p className="text-xl font-bold" style={{ color }}>{value}</p>
      <p className="text-xs mt-0.5" style={{ color: '#5C5A72' }}>{label}</p>
    </div>
  )
}

function TopicRow({ label, topics, color }: { label: string; topics: string[]; color: string }) {
  if (!topics.length) return null
  return (
    <div className="flex items-start gap-2">
      <span className="text-xs shrink-0 mt-0.5" style={{ color: '#5C5A72' }}>{label}:</span>
      <div className="flex flex-wrap gap-1">
        {topics.slice(0, 4).map(t => (
          <span key={t} className="text-xs px-2 py-0.5 rounded-full"
            style={{ background: color + '18', color, border: `1px solid ${color}30` }}>
            {t}
          </span>
        ))}
      </div>
    </div>
  )
}

function TrailerRow({
  trailer, onPlay, onRegenerate,
}: {
  trailer: ProjectTrailerListItem
  onPlay: (url: string) => void
  onRegenerate: (prompt: string) => void
}) {
  const statusColor = {
    pending: '#D4A843', processing: '#8B7CF6', done: '#4ADE80', failed: '#F87171',
  }[trailer.status] ?? '#A8A4B8'

  return (
    <div className="rounded-xl overflow-hidden" style={{ border: `1px solid ${statusColor}20` }}>
      <div className="flex items-start gap-3 px-4 py-3"
        style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)' }}>
        {/* Generation badge */}
        <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
          style={{ background: statusColor + '15', border: `1px solid ${statusColor}30` }}>
          {trailer.status === 'done'       && <CheckCircle size={13} style={{ color: statusColor }} />}
          {trailer.status === 'failed'     && <XCircle     size={13} style={{ color: statusColor }} />}
          {(trailer.status === 'pending' || trailer.status === 'processing') && (
            <Loader2 size={13} className="animate-spin" style={{ color: statusColor }} />
          )}
        </div>

        <div className="flex-1 min-w-0">
          {/* Header row */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold" style={{ color: '#D4A843' }}>
              Gen {trailer.generation_number}
            </span>
            <span className="text-xs font-semibold capitalize" style={{ color: '#F0EDE8' }}>
              {trailer.status}
            </span>
            {trailer.clip_count != null && trailer.target_duration != null && (
              <span className="flex items-center gap-1 text-xs" style={{ color: '#5C5A72' }}>
                <Clock size={9} /> {trailer.clip_count} clips · {fmt(trailer.target_duration)}
              </span>
            )}
            {trailer.clip_score != null && (
              <span className="text-xs font-mono" style={{ color: '#D4A843' }}>
                {Math.round(trailer.clip_score * 100)}%
              </span>
            )}
          </div>

          {/* User expectation */}
          {trailer.user_prompt && (
            <p className="text-xs mt-1 italic" style={{ color: '#A8A4B8' }}>
              &ldquo;{trailer.user_prompt}&rdquo;
            </p>
          )}

          <p className="text-xs mt-0.5" style={{ color: '#5C5A72' }}>
            {new Date(trailer.created_at).toLocaleString()}
          </p>
          {trailer.error_message && (
            <p className="text-xs mt-0.5 truncate" style={{ color: '#F87171' }}>{trailer.error_message}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
          {trailer.status === 'done' && trailer.output_url && (
            <>
              <button
                onClick={() => onPlay(trailer.output_url!)}
                className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-all"
                style={{ background: '#4ADE8018', color: '#4ADE80', border: '1px solid #4ADE8030' }}>
                <Play size={10} /> Play
              </button>
              <a
                href={smartTrailerService.trailerUrl(trailer.output_url)}
                download
                className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-all"
                style={{ background: '#8B7CF618', color: '#8B7CF6', border: '1px solid #8B7CF630' }}>
                <Download size={10} /> Save
              </a>
            </>
          )}
          <button
            onClick={() => onRegenerate(trailer.user_prompt || '')}
            className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg transition-all"
            style={{ background: '#D4A84318', color: '#D4A843', border: '1px solid #D4A84330' }}
            title="Regenerate with new instructions">
            <RotateCcw size={10} /> Retry
          </button>
        </div>
      </div>
    </div>
  )
}

interface Props {
  project: Project
}

const PENDING_STEPS: ProgressStep[] = [
  { key: 'comments',    label: 'Parsing audience feedback',  status: 'pending', percent: 0 },
  { key: 'sample',      label: 'Analysing sample trailer',   status: 'pending', percent: 0 },
  { key: 'scenes',      label: 'Detecting scenes',           status: 'pending', percent: 0 },
  { key: 'transcript',  label: 'Transcribing audio',         status: 'pending', percent: 0 },
  { key: 'beats',       label: 'Analysing beat rhythm',      status: 'pending', percent: 0 },
  { key: 'planning',    label: 'Planning clip selection',    status: 'pending', percent: 0 },
  { key: 'extracting',  label: 'Extracting clips',           status: 'pending', percent: 0 },
  { key: 'composing',   label: 'Composing transitions',      status: 'pending', percent: 0 },
  { key: 'normalising', label: 'Normalising audio',          status: 'pending', percent: 0 },
]

export default function ProjectGenerationPanel({ project }: Props) {
  const { toast } = useToast()

  const [status,   setStatus]   = useState<ProjectAnalyticsStatus | null>(null)
  const [trailers, setTrailers] = useState<ProjectTrailerListItem[]>([])
  const [loadingMeta, setLoadingMeta] = useState(true)

  const [prompt,   setPrompt]   = useState('')
  const [fastMode, setFastMode] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [genError,   setGenError]   = useState<string | null>(null)

  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [progress, setProgress] = useState<{
    stage: string; percent: number; message: string; steps: ProgressStep[]
  } | null>(null)

  const [playUrl,       setPlayUrl]       = useState<string | null>(null)
  const [showMetrics,   setShowMetrics]   = useState(true)
  const [runningAnalytics, setRunningAnalytics] = useState(false)

  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null)
  const sseUnsubRef = useRef<(() => void) | null>(null)

  // Load analytics status + existing trailers
  useEffect(() => {
    setLoadingMeta(true)
    Promise.all([
      projectService.getAnalyticsStatus(project.id).catch(() => null),
      projectService.listTrailers(project.id).catch(() => []),
    ]).then(([s, t]) => {
      setStatus(s)
      setTrailers(t as ProjectTrailerListItem[])
      const inFlight = (t as ProjectTrailerListItem[]).find(
        j => j.status === 'pending' || j.status === 'processing'
      )
      if (inFlight) setActiveJobId(inFlight.job_id)
    }).finally(() => setLoadingMeta(false))
  }, [project.id])

  // SSE + poll for active job
  useEffect(() => {
    if (!activeJobId) return
    setProgress({ stage: 'queued', percent: 0, message: 'Starting…', steps: PENDING_STEPS })

    sseUnsubRef.current = smartTrailerService.subscribeProgress(
      activeJobId,
      (stage, percent, message, steps) =>
        setProgress({ stage, percent, message, steps: steps.length ? steps : PENDING_STEPS }),
    )

    pollRef.current = setInterval(async () => {
      try {
        const job = await smartTrailerService.pollJob(activeJobId)
        if (job.status === 'done' || job.status === 'failed') {
          clearInterval(pollRef.current!)
          sseUnsubRef.current?.()
          setActiveJobId(null)
          setProgress(null)
          setGenerating(false)
          projectService.listTrailers(project.id).then(setTrailers).catch(() => {})
          if (job.status === 'done') toast('Trailer generated successfully!')
          else toast(job.error_message ?? 'Generation failed.', 'error')
        }
      } catch { /* retry next tick */ }
    }, POLL_MS)

    return () => { clearInterval(pollRef.current!); sseUnsubRef.current?.() }
  }, [activeJobId])

  const handleRunAnalytics = useCallback(async () => {
    setRunningAnalytics(true)
    try {
      const s = await projectService.runAnalytics(project.id)
      setStatus(s)
      toast('Analytics ready.')
    } catch {
      toast('Failed to run analytics.', 'error')
    } finally {
      setRunningAnalytics(false)
    }
  }, [project.id])

  // isRegeneration = there is already at least one generation for this project
  const isRegeneration = trailers.length > 0

  const handleGenerate = useCallback(async () => {
    if (activeJobId) { toast('A generation is already in progress.', 'error'); return }
    if (isRegeneration && !prompt.trim()) {
      setGenError('Expectations are required for regeneration. Describe what this generation should focus on.')
      return
    }
    setGenError(null)
    setGenerating(true)
    try {
      const job = await projectService.generateTrailer(
        project.id,
        prompt.trim() || undefined,
        fastMode,
      )
      setTrailers(prev => [
        {
          job_id: job.id,
          project_id: project.id,
          dataset_id: project.dataset_id,
          generation_number: prev.length + 1,
          user_prompt: prompt.trim() || null,
          status: job.status as 'pending',
          output_url: null,
          clip_count: null,
          target_duration: null,
          clip_score: null,
          has_creative_direction: !!prompt.trim(),
          fast_mode: fastMode,
          error_message: null,
          created_at: job.created_at,
          updated_at: job.updated_at,
        },
        ...prev,
      ])
      setActiveJobId(job.id)
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Generation failed. Please try again.'
      setGenError(msg)
      setGenerating(false)
    }
  }, [project.id, prompt, fastMode, activeJobId, isRegeneration])

  const handleCancel = useCallback(async () => {
    if (!activeJobId) return
    try {
      await smartTrailerService.cancelJob(activeJobId)
      clearInterval(pollRef.current!)
      sseUnsubRef.current?.()
      setActiveJobId(null)
      setProgress(null)
      setGenerating(false)
      toast('Generation cancelled.')
      projectService.listTrailers(project.id).then(setTrailers).catch(() => {})
    } catch { toast('Failed to cancel.', 'error') }
  }, [activeJobId, project.id])

  // Called from TrailerRow Retry button — pre-fills prompt field and scrolls to form
  const handleRegenerate = useCallback((prevPrompt: string) => {
    setPrompt(prevPrompt)
    setGenError(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }, [])

  const displayName = project.name || project.filename
  const total = (status?.positive ?? 0) + (status?.negative ?? 0) + (status?.neutral ?? 0)
  const posPct = total ? Math.round(((status?.positive ?? 0) / total) * 100) : 0
  const negPct = total ? Math.round(((status?.negative ?? 0) / total) * 100) : 0
  const neuPct = total ? 100 - posPct - negPct : 0

  if (loadingMeta) {
    return (
      <div className="flex items-center justify-center py-16 gap-3">
        <Loader2 size={20} className="animate-spin" style={{ color: '#D4A843' }} />
        <span className="text-sm" style={{ color: '#A8A4B8' }}>Loading project…</span>
      </div>
    )
  }

  return (
    <div className="space-y-5">

      {/* Project header */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
          style={{ background: 'linear-gradient(135deg,#D4A84318,#8B7CF614)', border: '1px solid #D4A84325' }}>
          <Film size={18} style={{ color: '#D4A843' }} />
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-semibold text-sm truncate" style={{ color: '#F0EDE8' }}>{displayName}</h2>
          <div className="flex items-center gap-3 mt-0.5 flex-wrap">
            {project.raw_footage_name && (
              <span className="flex items-center gap-1 text-xs" style={{ color: '#5C5A72' }}>
                <Film size={9} /> {project.raw_footage_name}
              </span>
            )}
            {project.feedback_file_name && (
              <span className="flex items-center gap-1 text-xs" style={{ color: '#5C5A72' }}>
                <Database size={9} /> {project.feedback_file_name}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Metrics panel */}
      <Card>
        <button
          className="w-full flex items-center justify-between mb-3"
          onClick={() => setShowMetrics(v => !v)}>
          <div className="flex items-center gap-2">
            <BarChart2 size={14} style={{ color: '#D4A843' }} />
            <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>Audience Metrics</span>
            {status?.has_analytics && (
              <span className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: '#4ADE8018', color: '#4ADE80', border: '1px solid #4ADE8030' }}>
                {status.segment_count} segments
              </span>
            )}
          </div>
          {showMetrics ? <ChevronUp size={14} style={{ color: '#5C5A72' }} /> : <ChevronDown size={14} style={{ color: '#5C5A72' }} />}
        </button>

        {showMetrics && (
          <>
            {!status?.has_analytics ? (
              <div className="flex flex-col items-center py-6 gap-3 text-center">
                <BarChart2 size={28} style={{ color: '#5C5A72' }} />
                <p className="text-sm" style={{ color: '#A8A4B8' }}>
                  {!status?.dataset_id
                    ? 'No feedback dataset found for this project.'
                    : 'Analytics not yet computed for this project.'}
                </p>
                {status?.dataset_id && (
                  <button
                    onClick={handleRunAnalytics}
                    disabled={runningAnalytics}
                    className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all disabled:opacity-50"
                    style={{ background: '#D4A84320', color: '#D4A843', border: '1px solid #D4A84335' }}>
                    {runningAnalytics
                      ? <><Loader2 size={11} className="animate-spin" /> Running…</>
                      : <><Play size={11} /> Run Analytics</>}
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-3">
                  <MetricPill value={`${posPct}%`} label="Positive" color="#4ADE80" bg="#4ADE8010" border="#4ADE8025" />
                  <MetricPill value={`${negPct}%`} label="Negative" color="#F87171" bg="#F8717110" border="#F8717125" />
                  <MetricPill value={`${neuPct}%`} label="Neutral"  color="#A8A4B8" bg="#A8A4B810" border="#A8A4B825" />
                </div>
                <div className="h-2 rounded-full overflow-hidden flex gap-px" style={{ background: '#1E1E30' }}>
                  {posPct > 0 && <div style={{ width: `${posPct}%`, background: '#4ADE80' }} />}
                  {negPct > 0 && <div style={{ width: `${negPct}%`, background: '#F87171' }} />}
                  {neuPct > 0 && <div style={{ width: `${neuPct}%`, background: '#A8A4B840' }} />}
                </div>
                {status.top_topic && (
                  <div className="space-y-1.5">
                    <TopicRow label="Top topic" topics={[status.top_topic]} color="#D4A843" />
                  </div>
                )}
                {status.analyzed_at && (
                  <p className="text-xs" style={{ color: '#5C5A72' }}>
                    Analysed {new Date(status.analyzed_at).toLocaleString()}
                    <button
                      onClick={handleRunAnalytics}
                      disabled={runningAnalytics}
                      className="ml-2 inline-flex items-center gap-1 transition-opacity hover:opacity-80 disabled:opacity-40"
                      style={{ color: '#5C5A72' }}
                      title="Refresh analytics">
                      <RefreshCw size={10} className={runningAnalytics ? 'animate-spin' : ''} />
                    </button>
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </Card>

      {/* Generation form */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Wand2 size={14} style={{ color: '#8B7CF6' }} />
          <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>
            {isRegeneration ? 'New Generation' : 'Generate Trailer'}
          </span>
          {isRegeneration && (
            <span className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: '#F8717112', color: '#F87171', border: '1px solid #F8717130' }}>
              Expectations required
            </span>
          )}
        </div>

        <div className="space-y-2 mb-4">
          <label className="text-xs font-medium" style={{ color: '#A8A4B8' }}>
            Expectations{' '}
            {isRegeneration
              ? <span style={{ color: '#F87171' }}>*</span>
              : <span style={{ color: '#5C5A72' }}>(optional)</span>}
          </label>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            disabled={!!activeJobId}
            placeholder={
              isRegeneration
                ? 'Required — describe what this generation should focus on differently…'
                : 'e.g. Focus on action. Create a fast-paced trailer. Emphasize emotional moments.'
            }
            rows={3}
            className="w-full resize-none rounded-xl px-3 py-2.5 text-xs outline-none transition-colors disabled:opacity-50"
            style={{ background: '#0E0E1A', border: `1px solid ${isRegeneration && !prompt.trim() ? '#F8717140' : '#252538'}`, color: '#F0EDE8' }}
            onFocus={e => (e.target.style.borderColor = '#8B7CF660')}
            onBlur={e => (e.target.style.borderColor = isRegeneration && !prompt.trim() ? '#F8717140' : '#252538')}
          />
          <div className="flex flex-wrap gap-1.5">
            {CREATIVE_CHIPS.map(chip => (
              <button
                key={chip}
                type="button"
                disabled={!!activeJobId}
                onClick={() => setPrompt(p => p.trim() ? p.trimEnd() + '. ' + chip : chip)}
                className="text-xs px-2 py-0.5 rounded-full border transition-colors disabled:opacity-40"
                style={{ borderColor: '#252538', color: '#5C5A72' }}
                onMouseEnter={e => { (e.target as HTMLElement).style.color = '#D4A843'; (e.target as HTMLElement).style.borderColor = '#D4A84340' }}
                onMouseLeave={e => { (e.target as HTMLElement).style.color = '#5C5A72'; (e.target as HTMLElement).style.borderColor = '#252538' }}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>

        <label className="flex items-center gap-2.5 cursor-pointer mb-4 group">
          <div
            className="relative w-4 h-4 rounded shrink-0 flex items-center justify-center transition-colors"
            style={{
              background: fastMode ? '#8B7CF620' : 'transparent',
              border: `1px solid ${fastMode ? '#8B7CF6' : '#252538'}`,
            }}
            onClick={() => setFastMode(v => !v)}>
            {fastMode && (
              <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
                <path d="M1 3.5L3.5 6L8 1" stroke="#8B7CF6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            )}
          </div>
          <div onClick={() => setFastMode(v => !v)}>
            <p className="text-xs font-medium" style={{ color: '#F0EDE8' }}>Fast demo mode</p>
            <p className="text-xs" style={{ color: '#5C5A72' }}>Skip transcription to reduce generation time.</p>
          </div>
        </label>

        {genError && (
          <div className="flex items-start gap-2 mb-3 px-3 py-2.5 rounded-xl text-xs"
            style={{ background: '#F8717112', color: '#F87171', border: '1px solid #F8717130' }}>
            <AlertCircle size={13} className="shrink-0 mt-0.5" />
            <span>{genError}</span>
          </div>
        )}

        {activeJobId ? (
          <button
            onClick={handleCancel}
            className="flex items-center gap-2 w-full justify-center px-4 py-2.5 rounded-xl text-sm font-semibold transition-all"
            style={{ background: '#F8717112', color: '#F87171', border: '1px solid #F8717130' }}>
            <Square size={13} /> Stop Generation
          </button>
        ) : (
          <button
            onClick={handleGenerate}
            disabled={generating || !status?.dataset_id || (isRegeneration && !prompt.trim())}
            className="flex items-center gap-2 w-full justify-center px-4 py-2.5 rounded-xl text-sm font-semibold transition-all disabled:opacity-50"
            style={{
              background: 'linear-gradient(135deg,#D4A843,#E8C56A)',
              color: '#0C0C14',
              boxShadow: generating ? 'none' : '0 0 20px 0 #D4A84340',
            }}>
            {generating
              ? <><Loader2 size={14} className="animate-spin" /> Queuing…</>
              : isRegeneration
                ? <><RotateCcw size={14} /> Regenerate Trailer</>
                : <><Zap size={14} /> Generate Trailer</>}
          </button>
        )}

        {!status?.dataset_id && (
          <p className="text-xs text-center mt-2" style={{ color: '#5C5A72' }}>
            Upload a project with a feedback file to enable generation.
          </p>
        )}
      </Card>

      {/* Active job progress */}
      {activeJobId && progress && (
        <Card>
          <div className="flex items-center gap-2 mb-3">
            <Loader2 size={13} className="animate-spin" style={{ color: '#8B7CF6' }} />
            <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>Generating…</span>
            <span className="flex items-center gap-1 ml-1">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#4ADE80' }} />
              <span className="text-xs" style={{ color: '#4ADE80' }}>Live</span>
            </span>
          </div>
          <JobProgressPanel
            stage={progress.stage}
            percent={progress.percent}
            message={progress.message}
            steps={progress.steps}
          />
        </Card>
      )}

      {/* Video player */}
      {playUrl && (
        <Card>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>Preview</span>
            <button onClick={() => setPlayUrl(null)} className="text-xs" style={{ color: '#5C5A72' }}>✕ Close</button>
          </div>
          <video
            controls
            autoPlay
            className="w-full rounded-xl bg-black"
            style={{ maxHeight: 320 }}
            src={smartTrailerService.trailerUrl(playUrl)}
          />
        </Card>
      )}

      {/* Generation history */}
      {trailers.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>
              Generation History
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: '#1E1E30', color: '#A8A4B8' }}>
              {trailers.length}
            </span>
          </div>
          {trailers.map(t => (
            <TrailerRow
              key={t.job_id}
              trailer={t}
              onPlay={url => setPlayUrl(url)}
              onRegenerate={handleRegenerate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
