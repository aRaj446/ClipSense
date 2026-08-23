import { useEffect, useState } from 'react'
import { X, Download, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import type { ExportState, StepEntry } from '../hooks/useExport'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

// Steps shown when no SSE steps have arrived yet (initial skeleton)
const DEFAULT_STEPS: StepEntry[] = [
  { key: 'loading',    label: 'Loading plan',          status: 'pending', percent: 0 },
  { key: 'extracting', label: 'Extracting clips',      status: 'pending', percent: 0 },
  { key: 'composing',  label: 'Composing transitions', status: 'pending', percent: 0 },
  { key: 'normalising',label: 'Normalising audio',     status: 'pending', percent: 0 },
]

function StepRow({ step }: { step: StepEntry }) {
  const icon =
    step.status === 'done'   ? <CheckCircle  size={13} className="text-accent-green shrink-0" /> :
    step.status === 'active' ? <Loader2      size={13} className="text-primary animate-spin shrink-0" /> :
    step.status === 'failed' ? <AlertCircle  size={13} className="text-accent-red shrink-0" /> :
                               <span className="w-[13px] h-[13px] rounded-full border border-slate-600 shrink-0" />

  return (
    <div className="flex items-center gap-2.5">
      {icon}
      <span className={`text-xs ${
        step.status === 'done'   ? 'text-slate-300' :
        step.status === 'active' ? 'text-slate-200 font-medium' :
        step.status === 'failed' ? 'text-accent-red' :
                                   'text-slate-500'
      }`}>
        {step.label}
      </span>
      {step.status === 'active' && step.percent > 0 && (
        <span className="ml-auto text-[10px] text-slate-500 font-mono">{step.percent}%</span>
      )}
    </div>
  )
}

interface Props {
  state: ExportState
  onRetry: () => void
  onDismiss: () => void
}

export default function ExportProgress({ state, onRetry, onDismiss }: Props) {
  const [finalUrl, setFinalUrl] = useState<string | null>(null)

  // When done, fetch the new job to get the real output_url
  useEffect(() => {
    if (state.status !== 'done' || !state.outputUrl) return
    let cancelled = false
    fetch(`${API_BASE}${state.outputUrl}`)
      .then(r => r.json())
      .then(data => {
        if (cancelled) return
        const url: string | null = data.output_url ?? null
        setFinalUrl(url ? `${API_BASE}${url}` : null)
      })
      .catch(() => { /* silent */ })
    return () => { cancelled = true }
  }, [state.status, state.outputUrl])

  const steps = state.steps.length > 0 ? state.steps : DEFAULT_STEPS

  return (
    // Backdrop
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onDismiss() }}
    >
      <div className="bg-surface-card border border-surface-border rounded-2xl w-full max-w-sm mx-4 shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border">
          <div className="flex items-center gap-2">
            <Download size={14} className="text-primary" />
            <span className="text-sm font-semibold text-slate-200">
              {state.status === 'done'   ? 'Export complete' :
               state.status === 'failed' ? 'Export failed' :
                                           'Exporting…'}
            </span>
          </div>
          {(state.status === 'done' || state.status === 'failed') && (
            <button onClick={onDismiss} className="text-slate-500 hover:text-slate-300 transition-colors">
              <X size={14} />
            </button>
          )}
        </div>

        <div className="px-5 py-4 space-y-4">

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center">
              <span className="text-[11px] text-slate-400 truncate pr-2">{state.message || 'Preparing…'}</span>
              <span className="text-[11px] text-slate-500 font-mono shrink-0">{state.percent}%</span>
            </div>
            <div className="h-1.5 bg-surface-raised rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  state.status === 'failed' ? 'bg-accent-red' :
                  state.status === 'done'   ? 'bg-accent-green' :
                                              'bg-primary'
                }`}
                style={{ width: `${state.percent}%` }}
              />
            </div>
          </div>

          {/* Steps */}
          <div className="space-y-2.5">
            {steps.map(step => <StepRow key={step.key} step={step} />)}
          </div>

          {/* Done — download link */}
          {state.status === 'done' && (
            <div className="pt-1">
              {finalUrl ? (
                <a
                  href={finalUrl}
                  download
                  className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-xl bg-primary text-surface-base text-sm font-semibold hover:bg-primary/90 transition-colors"
                >
                  <Download size={14} />
                  Download MP4
                </a>
              ) : (
                <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
                  <Loader2 size={12} className="animate-spin" />
                  Fetching download link…
                </div>
              )}
            </div>
          )}

          {/* Failed — error + retry */}
          {state.status === 'failed' && (
            <div className="space-y-3 pt-1">
              {state.error && (
                <p className="text-xs text-accent-red bg-accent-red/10 rounded-lg px-3 py-2 break-words">
                  {state.error}
                </p>
              )}
              <button
                onClick={onRetry}
                className="w-full px-4 py-2.5 rounded-xl border border-primary text-primary text-sm font-medium hover:bg-primary/10 transition-colors"
              >
                Retry export
              </button>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}
