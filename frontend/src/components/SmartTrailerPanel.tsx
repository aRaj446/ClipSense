import { useState, useEffect, useRef } from 'react'
import {
  Brain, Loader2, CheckCircle, XCircle, Film,
  Play, RefreshCw, Sparkles, Trash2, Square, MessageSquare,
  ArrowRight, Download, Clock, Wand2, X, Volume2,
} from 'lucide-react'
import { SmartTrailerJob, AudioSettings, DEFAULT_AUDIO_SETTINGS, TargetLufs, GenerateRequest } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import { useToast } from '../context/ToastContext'
import Modal from './Modal'
import Button from './Button'
import JobProgressPanel, { ProgressStep } from './JobProgressPanel'
import DataSourceDisclaimer from './DataSourceDisclaimer'

const POLL_INTERVAL_MS = 3000

const STATUS_LABEL: Record<SmartTrailerJob['status'], string> = {
  pending:    'Queued',
  processing: 'Generating…',
  done:       'Ready',
  failed:     'Failed',
}

const STATUS_COLOR: Record<SmartTrailerJob['status'], string> = {
  pending:    '#D4A843',
  processing: '#8B7CF6',
  done:       '#4ADE80',
  failed:     '#F87171',
}

const MOOD_COLOR: Record<string, { bg: string; border: string; label: string }> = {
  action:    { bg: '#F8717118', border: '#F87171', label: 'Action' },
  emotional: { bg: '#8B7CF618', border: '#8B7CF6', label: 'Emotional' },
  dialogue:  { bg: '#D4A84318', border: '#D4A843', label: 'Dialogue' },
  calm:      { bg: '#2DD4BF18', border: '#2DD4BF', label: 'Calm' },
}

const CREATIVE_CHIPS = [
  { label: 'More action',            append: 'more action' },
  { label: 'More emotional',         append: 'more emotional' },
  { label: 'More humour',            append: 'more humour' },
  { label: 'More suspense',          append: 'more suspense' },
  { label: 'Faster pacing',          append: 'faster pacing' },
  { label: 'More character moments', append: 'more character moments' },
]

const LUFS_OPTIONS: { value: TargetLufs; label: string }[] = [
  { value: -16, label: '-16 LUFS' },
  { value: -14, label: '-14 LUFS' },
  { value: -12, label: '-12 LUFS' },
  { value: -10, label: '-10 LUFS' },
]

function AudioToggle({
  checked, onChange, label, description,
}: { checked: boolean; onChange: (v: boolean) => void; label: string; description: string }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer group">
      <div
        className="relative mt-0.5 w-4 h-4 rounded shrink-0 flex items-center justify-center transition-colors"
        style={{
          background: checked ? '#8B7CF620' : 'transparent',
          border: `1px solid ${checked ? '#8B7CF6' : '#252538'}`,
        }}
        onClick={() => onChange(!checked)}
      >
        {checked && (
          <svg width="9" height="7" viewBox="0 0 9 7" fill="none">
            <path d="M1 3.5L3.5 6L8 1" stroke="#8B7CF6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        )}
      </div>
      <div onClick={() => onChange(!checked)}>
        <p className="text-xs font-medium leading-none mb-0.5" style={{ color: '#F0EDE8' }}>{label}</p>
        <p className="text-xs" style={{ color: '#5C5A72' }}>{description}</p>
      </div>
    </label>
  )
}

function CreativeChip({ label, onAppend }: { label: string; onAppend: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <button
      type="button"
      onClick={onAppend}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className="text-xs px-2 py-0.5 rounded-full border transition-colors"
      style={{
        borderColor: hovered ? '#D4A84340' : '#252538',
        color: hovered ? '#D4A843' : '#5C5A72',
      }}
    >
      {label}
    </button>
  )
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
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>
          Clip Timeline
        </span>
        <span className="text-xs font-mono px-2 py-0.5 rounded-full"
          style={{ background: '#1E1E30', color: '#A8A4B8' }}>
          {clips.length} clips · {fmt(totalDuration)}
        </span>
      </div>

      {/* Mood legend */}
      <div className="flex gap-3 flex-wrap">
        {Object.entries(MOOD_COLOR).map(([mood, { border, label }]) => (
          <span key={mood} className="flex items-center gap-1.5 text-xs" style={{ color: '#A8A4B8' }}>
            <span className="w-2 h-2 rounded-sm" style={{ background: border }} />{label}
          </span>
        ))}
      </div>

      {/* Segmented bar */}
      <div className="flex h-3 rounded-full overflow-hidden gap-px" style={{ background: '#1E1E30' }}>
        {clips.map((clip, i) => {
          const pct  = ((clip.end_time - clip.start_time) / totalDuration) * 100
          const mood = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          return (
            <div key={i}
              title={`${clip.topic} · ${fmt(clip.start_time)}–${fmt(clip.end_time)}`}
              className="cursor-pointer transition-opacity hover:opacity-100"
              style={{ width: `${pct}%`, background: mood.border, opacity: 0.75, minWidth: 3 }}
              onClick={() => setExpanded(expanded === i ? null : i)}
            />
          )
        })}
      </div>

      {/* Clip rows */}
      <div className="space-y-1.5 max-h-52 overflow-y-auto pr-1">
        {clips.map((clip, i) => {
          const mood   = MOOD_COLOR[clip.mood_group] ?? MOOD_COLOR.calm
          const isOpen = expanded === i
          return (
            <div key={i}
              className="rounded-xl cursor-pointer transition-all duration-150"
              style={{
                background: isOpen ? mood.bg : 'rgba(255,255,255,0.02)',
                border: `1px solid ${isOpen ? mood.border + '40' : '#1E1E30'}`,
                borderLeft: `3px solid ${mood.border}`,
              }}
              onClick={() => setExpanded(isOpen ? null : i)}>
              <div className="flex items-center gap-2.5 px-3 py-2">
                <span className="text-xs font-mono shrink-0 tabular-nums" style={{ color: mood.border }}>
                  {fmt(clip.start_time)}
                </span>
                <span className="text-xs truncate flex-1 font-medium" style={{ color: '#F0EDE8' }}>
                  {clip.topic}
                </span>
                <span className="text-xs px-2 py-0.5 rounded-full shrink-0"
                  style={{ background: mood.border + '18', color: mood.border }}>
                  {mood.label}
                </span>
                <span className="text-xs font-mono shrink-0" style={{ color: '#5C5A72' }}>
                  {fmt(clip.end_time - clip.start_time)}
                </span>
              </div>
              {isOpen && (
                <div className="px-3 pb-3 space-y-2 border-t" style={{ borderColor: mood.border + '20' }}>
                  <p className="text-xs pt-2 leading-relaxed" style={{ color: '#A8A4B8' }}>{clip.reason}</p>
                  {clip.transcript_text && (
                    <div className="flex gap-2 items-start rounded-lg px-2.5 py-2"
                      style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}>
                      <MessageSquare size={10} className="shrink-0 mt-0.5" style={{ color: '#5C5A72' }} />
                      <p className="text-xs italic leading-relaxed" style={{ color: '#5C5A72' }}>
                        "{clip.transcript_text}"
                      </p>
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
  const [retryJobId,     setRetryJobId]     = useState<string | null>(null)
  const [retryPrompt,    setRetryPrompt]    = useState('')
  const [confirmDelete,  setConfirmDelete]  = useState<string | null>(null)
  const [deleting,       setDeleting]       = useState(false)
  const [audioSettings,  setAudioSettings]  = useState<AudioSettings>({ ...DEFAULT_AUDIO_SETTINGS })
  const [includeSubtitles, setIncludeSubtitles] = useState(false)
  const [fastMode,       setFastMode]       = useState(false)
  const pollRef     = useRef<ReturnType<typeof setInterval> | null>(null)
  const sseUnsubRef = useRef<(() => void) | null>(null)

  const PENDING_STEPS: ProgressStep[] = [
    { key: 'comments',    label: 'Parsing audience comments', status: 'pending', percent: 0 },
    { key: 'sample',      label: 'Analysing sample trailer',  status: 'pending', percent: 0 },
    { key: 'scenes',      label: 'Detecting scenes',          status: 'pending', percent: 0 },
    { key: 'transcript',  label: 'Transcribing audio',        status: 'pending', percent: 0 },
    { key: 'beats',       label: 'Analysing beat rhythm',     status: 'pending', percent: 0 },
    { key: 'planning',    label: 'Planning clip selection',   status: 'pending', percent: 0 },
    { key: 'extracting',  label: 'Extracting clips',          status: 'pending', percent: 0 },
    { key: 'composing',   label: 'Composing transitions',     status: 'pending', percent: 0 },
    { key: 'normalising', label: 'Normalising audio',         status: 'pending', percent: 0 },
  ]

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
    setProgress({ stage: 'queued', percent: 0, message: 'Starting…', steps: PENDING_STEPS })
    sseUnsubRef.current = smartTrailerService.subscribeProgress(
      activeJobId,
      (stage, percent, message, steps) =>
        setProgress({ stage, percent, message, steps: steps.length ? steps : PENDING_STEPS }),
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
      setProgress(null)
      toast('Generation cancelled.')
    } catch { toast('Failed to cancel.', 'error') }
  }

  async function handleDelete(jobId: string) {
    setDeleting(true)
    try {
      await smartTrailerService.deleteJob(jobId)
      setJobs(prev => prev.filter(j => j.id !== jobId))
      if (retryJobId === jobId) { setRetryJobId(null); setRetryPrompt('') }
      setConfirmDelete(null)
      toast('Job deleted.')
    } catch { toast('Failed to delete.', 'error') }
    finally { setDeleting(false) }
  }

  async function handleRetry(job: SmartTrailerJob, prompt?: string) {
    if (activeJobId) { toast('A generation is already in progress.', 'error'); return }
    setRetryJobId(null)
    setRetryPrompt('')
    const req: GenerateRequest = {}
    if (prompt?.trim()) req.user_prompt = prompt.trim()
    if (audioSettings.target_lufs !== DEFAULT_AUDIO_SETTINGS.target_lufs ||
      audioSettings.bass_boost ||
      audioSettings.treble_cut
    ) req.audio = audioSettings
    if (includeSubtitles && !fastMode) req.include_subtitles = true
    if (fastMode) req.fast_mode = true
    try {
      const started = await smartTrailerService.generate(job.id, req)
      setJobs(prev => [started, ...prev])
      setActiveJobId(started.id)
      toast(job.status === 'done' ? 'Regenerating trailer…' : 'Retrying generation…')
    } catch { toast('Failed to retry.', 'error') }
  }

  function openRetry(job: SmartTrailerJob) {
    // Pre-populate from previous creative direction if present in rationale
    const match = job.editing_plan?.rationale?.match(/Creative direction applied:\s*(.+?)\./)
    const prefill = match ? match[1].split(' · ').join(', ') : ''
    setRetryJobId(job.id)
    setRetryPrompt(prefill)
    setAudioSettings({ ...DEFAULT_AUDIO_SETTINGS })
    setIncludeSubtitles(false)
    setFastMode(false)
  }

  if (loadingJobs) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 size={28} className="animate-spin" style={{ color: '#8B7CF6' }} />
      </div>
    )
  }

  if (jobs.length === 0 && !activeJobId) {
    return (
      <div className="flex flex-col items-center py-20 rounded-2xl animate-fade-in"
        style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #252538' }}>
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5 animate-float"
          style={{ background: 'linear-gradient(135deg,#8B7CF614,#D4A84310)', border: '1px solid #8B7CF625' }}>
          <Sparkles size={26} style={{ color: '#5C5A72' }} />
        </div>
        <p className="text-base font-semibold mb-1" style={{ color: '#F0EDE8' }}>No smart trailers yet</p>
        <p className="text-sm" style={{ color: '#5C5A72' }}>Go to Upload → Smart Trailer to generate one.</p>
      </div>
    )
  }

  return (
    <div className="space-y-5 animate-fade-in">

      {/* ── Active job progress ── */}
      {activeJobId && (
        <div className="relative rounded-2xl p-6 space-y-4 overflow-hidden"
          style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #8B7CF630' }}>
          <div className="absolute inset-x-0 h-px pointer-events-none animate-shimmer-slide"
            style={{ background: 'linear-gradient(90deg,transparent,#8B7CF660,#D4A84340,transparent)', top: 0 }} />
          <div className="flex items-center gap-2">
            <Brain size={14} style={{ color: '#8B7CF6' }} />
            <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>Generating Smart Trailer</span>
            <span className="flex items-center gap-1 ml-1">
              <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#4ADE80' }} />
              <span className="text-xs" style={{ color: '#4ADE80' }}>Live</span>
            </span>
          </div>
          <JobProgressPanel
            stage={progress?.stage ?? 'pending'}
            percent={progress?.percent ?? 0}
            message={progress?.message ?? 'Analysing footage, classifying mood groups, composing with crossfades…'}
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

      {/* ── Job list ── */}
      {jobs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between px-1">
            <p className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>
              Generated Trailers
            </p>
            <span className="text-xs px-2 py-0.5 rounded-full"
              style={{ background: '#1E1E30', color: '#A8A4B8' }}>
              {jobs.length} job{jobs.length !== 1 ? 's' : ''}
            </span>
          </div>

          {jobs.map((job, idx) => {
            const color = STATUS_COLOR[job.status]
            return (
              <div key={job.id}
                className="rounded-2xl overflow-hidden animate-fade-in"
                style={{
                  border: `1px solid ${color}20`,
                  boxShadow: job.status === 'done' ? `0 0 24px 0 ${color}12` : 'none',
                  animationDelay: `${idx * 50}ms`,
                }}>

                {/* ── Header ── */}
                <div
                  className={`flex items-center gap-3 px-5 py-3.5 ${job.status === 'done' && onSelectJob ? 'cursor-pointer' : ''}`}
                  style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', borderBottom: `1px solid ${color}18` }}
                  onClick={() => job.status === 'done' && onSelectJob?.(job.id)}>

                  {/* Status icon */}
                  <div className="w-8 h-8 rounded-xl flex items-center justify-center shrink-0"
                    style={{ background: color + '15', border: `1px solid ${color}30` }}>
                    {job.status === 'done'   && <CheckCircle size={15} style={{ color }} />}
                    {job.status === 'failed' && <XCircle     size={15} style={{ color }} />}
                    {(job.status === 'pending' || job.status === 'processing') && (
                      <Loader2 size={15} className="animate-spin" style={{ color }} />
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>
                        {STATUS_LABEL[job.status]}
                      </span>
                      <span className="text-xs px-2 py-0.5 rounded-full font-medium"
                        style={{ background: color + '15', color, border: `1px solid ${color}30` }}>
                        {job.status}
                      </span>
                      {job.editing_plan && (
                        <span className="flex items-center gap-1 text-xs" style={{ color: '#5C5A72' }}>
                          <Clock size={10} />
                          {job.editing_plan.clips.length} clips · {fmt(job.editing_plan.target_duration)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs mt-0.5 truncate" style={{ color: '#5C5A72' }}>
                      {job.raw_footage_name} + {job.sample_trailer_name}
                    </p>
                    {job.error_message && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: '#F87171' }}>{job.error_message}</p>
                    )}
                    {/* Rationale — hide when creative direction badge will show */}
                    {job.editing_plan?.rationale && !job.editing_plan.rationale.match(/Creative direction applied:/) && (
                      <p className="text-xs mt-0.5 truncate" style={{ color: '#5C5A72' }}>{job.editing_plan.rationale}</p>
                    )}
                    {/* Creative direction applied banner */}
                    {job.status === 'done' && (() => {
                      const match = job.editing_plan?.rationale?.match(/Creative direction applied:\s*(.+?)\./)
                      if (!match) return null
                      return (
                        <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full mt-1"
                          style={{ background: '#D4A84315', color: '#D4A843', border: '1px solid #D4A84330' }}>
                          <Wand2 size={10} />
                          Creative direction applied
                          <span style={{ color: '#A8A4B8' }}>· {match[1]}</span>
                        </span>
                      )
                    })()}
                    {/* Fast Demo Mode badge */}
                    {job.fast_mode === true && (
                      <span className="inline-flex items-center gap-1.5 text-xs px-2 py-0.5 rounded-full mt-1"
                        style={{ background: '#2DD4BF12', color: '#2DD4BF', border: '1px solid #2DD4BF30' }}>
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none" style={{ flexShrink: 0 }}>
                          <circle cx="4" cy="4" r="3" fill="#2DD4BF" />
                        </svg>
                        FAST DEMO MODE
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-xs hidden sm:inline mr-2" style={{ color: '#5C5A72' }}>
                      {new Date(job.updated_at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: true })}
                    </span>
                    {(job.status === 'failed' || job.status === 'done') && (
                      <button
                        onClick={e => { e.stopPropagation(); openRetry(job) }}
                        className="p-1.5 rounded-lg transition-colors"
                        style={{ color: '#8B7CF6', background: retryJobId === job.id ? '#8B7CF620' : '#8B7CF610' }}
                        title="Regenerate with creative direction"
                      >
                        <RefreshCw size={13} />
                      </button>
                    )}
                    {(job.status === 'done' || job.status === 'failed') && (
                      <button
                        onClick={e => { e.stopPropagation(); setConfirmDelete(job.id) }}
                        className="p-1.5 rounded-lg transition-colors"
                        style={{ color: '#5C5A72' }}
                        title="Delete trailer">
                        <Trash2 size={13} />
                      </button>
                    )}
                  </div>
                </div>

                {/* ── Retry prompt panel ── */}
                {retryJobId === job.id && (
                  <div
                    className="px-5 py-4 space-y-3"
                    style={{ background: '#0E0E1A', borderBottom: '1px solid #1E1E30' }}
                    onClick={e => e.stopPropagation()}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <Wand2 size={12} style={{ color: '#D4A843' }} />
                        <span className="text-xs font-semibold" style={{ color: '#D4A843' }}>Creative direction</span>
                        <span className="text-xs" style={{ color: '#5C5A72' }}>(optional)</span>
                      </div>
                      <button
                        onClick={() => { setRetryJobId(null); setRetryPrompt('') }}
                        style={{ color: '#5C5A72' }}
                      >
                        <X size={13} />
                      </button>
                    </div>
                    <textarea
                      value={retryPrompt}
                      onChange={e => setRetryPrompt(e.target.value)}
                      placeholder="e.g. Keep the action, reduce emotional scenes, make it more humorous."
                      rows={2}
                      className="w-full resize-none rounded-lg px-3 py-2 text-xs outline-none transition-colors"
                      style={{
                        background: '#13131F',
                        border: '1px solid #252538',
                        color: '#F0EDE8',
                      }}
                      onFocus={e => (e.target.style.borderColor = '#D4A84360')}
                      onBlur={e => (e.target.style.borderColor = '#252538')}
                    />
                    <div className="flex flex-wrap gap-1.5">
                      {CREATIVE_CHIPS.map(chip => (
                        <CreativeChip
                          key={chip.label}
                          label={chip.label}
                          onAppend={() =>
                            setRetryPrompt(prev =>
                              prev.trim() ? prev.trimEnd() + ', ' + chip.append : chip.append
                            )
                          }
                        />
                      ))}
                    </div>
                    {/* ── AUDIO section ── */}
                    <DataSourceDisclaimer />
                    <div className="pt-1 space-y-2.5">
                      <div className="flex items-center gap-1.5">
                        <Volume2 size={12} style={{ color: '#8B7CF6' }} />
                        <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#5C5A72' }}>Audio</span>
                      </div>

                      {/* Target Loudness */}
                      <div className="flex items-center justify-between">
                        <span className="text-xs" style={{ color: '#A8A4B8' }}>Target Loudness</span>
                        <select
                          value={audioSettings.target_lufs}
                          onChange={e => setAudioSettings(prev => ({ ...prev, target_lufs: Number(e.target.value) as TargetLufs }))}
                          className="text-xs rounded-lg px-2 py-1 outline-none"
                          style={{
                            background: '#13131F',
                            border: '1px solid #252538',
                            color: '#F0EDE8',
                            minWidth: 100,
                          }}
                        >
                          {LUFS_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                      </div>

                      {/* Audio tone toggles */}
                      <div className="space-y-2">
                        <span className="text-xs" style={{ color: '#A8A4B8' }}>Audio tone</span>
                        <AudioToggle
                          checked={audioSettings.bass_boost}
                          onChange={v => setAudioSettings(prev => ({ ...prev, bass_boost: v }))}
                          label="Bass boost"
                          description="Enhance low-frequency impact."
                        />
                        <AudioToggle
                          checked={audioSettings.treble_cut}
                          onChange={v => setAudioSettings(prev => ({ ...prev, treble_cut: v }))}
                          label="Treble reduction"
                          description="Soften high-frequency intensity."
                        />
                      </div>

                      {/* Subtitle toggle — visual output, separated from audio controls */}
                      <div className="pt-1" style={{ borderTop: '1px solid #1E1E30' }}>
                        <AudioToggle
                          checked={includeSubtitles && !fastMode}
                          onChange={v => setIncludeSubtitles(v)}
                          label="Include subtitles"
                          description={fastMode ? 'Unavailable in fast demo mode.' : 'Burn dialogue subtitles into the generated trailer.'}
                        />
                        {includeSubtitles && !fastMode && (
                          <div className="flex items-center gap-1.5 mt-2 text-xs px-2 py-1 rounded-lg"
                            style={{ background: '#8B7CF610', border: '1px solid #8B7CF625', color: '#8B7CF6' }}>
                            <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                              <circle cx="4" cy="4" r="3" fill="#8B7CF6" />
                            </svg>
                            Subtitles enabled
                          </div>
                        )}
                      </div>

                      {/* Fast Demo Mode — visually secondary, below subtitle toggle */}
                      <div className="pt-2" style={{ borderTop: '1px solid #1E1E30' }}>
                        <AudioToggle
                          checked={fastMode}
                          onChange={v => { setFastMode(v); if (v) setIncludeSubtitles(false) }}
                          label="Fast demo mode"
                          description="Skip transcription to reduce generation time."
                        />
                        {fastMode && (
                          <p className="text-xs mt-1.5 ml-7" style={{ color: '#5C5A72' }}>
                            Dialogue-based features may be unavailable.
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleRetry(job, retryPrompt)}
                        className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg transition-colors"
                        style={{ background: '#8B7CF620', color: '#8B7CF6', border: '1px solid #8B7CF630' }}
                      >
                        <RefreshCw size={11} />
                        {job.status === 'done' ? 'Regenerate' : 'Retry'}
                      </button>
                      <button
                        onClick={() => { setRetryJobId(null); setRetryPrompt('') }}
                        className="text-xs"
                        style={{ color: '#5C5A72' }}
                      >
                        Cancel
                      </button>
                      {retryPrompt.trim() && (
                        <button
                          onClick={() => setRetryPrompt('')}
                          className="text-xs ml-auto"
                          style={{ color: '#5C5A72' }}
                        >
                          Clear prompt
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* ── Body: two-column ── */}
                {(job.editing_plan || (job.status === 'done' && job.output_url)) && (
                  <div className="grid grid-cols-1 lg:grid-cols-2"
                    style={{ background: 'linear-gradient(145deg,#0F0F1C,#13131F)' }}>

                    {/* Left — clip timeline */}
                    {job.editing_plan && job.editing_plan.clips.length > 0 && (
                      <div className="p-5" style={{ borderRight: '1px solid #1E1E30' }}>
                        <ClipTimeline
                          clips={job.editing_plan.clips}
                          totalDuration={job.editing_plan.target_duration}
                        />
                      </div>
                    )}

                    {/* Right — video or placeholder */}
                    {job.status === 'done' && job.output_url ? (
                      <div className="flex flex-col">
                        <video controls className="w-full object-contain bg-black"
                          style={{ maxHeight: 260 }}
                          src={smartTrailerService.trailerUrl(job.output_url)} />
                        <div className="px-5 py-3 flex items-center gap-3"
                          style={{ borderTop: '1px solid #1E1E30' }}>
                          <a href={smartTrailerService.trailerUrl(job.output_url)} download
                            className="flex items-center gap-2 text-xs font-semibold px-3 py-1.5 rounded-lg transition-all"
                            style={{ background: '#8B7CF618', color: '#8B7CF6', border: '1px solid #8B7CF630' }}>
                            <Download size={12} /> Download
                          </a>
                          <a href={smartTrailerService.trailerUrl(job.output_url)} target="_blank" rel="noreferrer"
                            className="flex items-center gap-1.5 text-xs transition-all"
                            style={{ color: '#5C5A72' }}>
                            <Play size={11} /> Open <ArrowRight size={11} />
                          </a>
                        </div>
                      </div>
                    ) : job.editing_plan && job.editing_plan.clips.length > 0 ? (
                      <div className="p-5 flex items-center justify-center">
                        <div className="text-center">
                          <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-3"
                            style={{ background: '#1E1E30', border: '1px solid #252538' }}>
                            <Film size={20} style={{ color: '#5C5A72' }} />
                          </div>
                          <p className="text-xs" style={{ color: '#5C5A72' }}>
                            {job.status === 'processing' ? 'Rendering video…' : 'No preview yet'}
                          </p>
                        </div>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {confirmDelete && (
        <Modal open title="Delete Trailer" onClose={() => setConfirmDelete(null)}>
          <p className="text-sm mb-6" style={{ color: '#A8A4B8' }}>
            This will permanently remove the video file. This action cannot be undone.
          </p>
          <div className="flex gap-3 justify-end">
            <Button variant="ghost" onClick={() => setConfirmDelete(null)}>Cancel</Button>
            <Button variant="danger" loading={deleting} onClick={() => handleDelete(confirmDelete)}>Delete</Button>
          </div>
        </Modal>
      )}
    </div>
  )
}
