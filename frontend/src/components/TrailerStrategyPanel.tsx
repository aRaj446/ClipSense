import { useEffect, useState, useRef } from 'react'
import { Sparkles, Save, RotateCcw, Pencil, Loader2, AlertCircle } from 'lucide-react'
import { TrailerStrategy } from '../types/analysis'
import { strategyService } from '../services/strategyService'
import Button from './Button'

interface Props {
  datasetId: string
}

type PanelState = 'idle' | 'loading' | 'ready' | 'editing' | 'saving' | 'error'

export default function TrailerStrategyPanel({ datasetId }: Props) {
  const [strategy, setStrategy]   = useState<TrailerStrategy | null>(null)
  const [state, setState]         = useState<PanelState>('idle')
  const [draft, setDraft]         = useState('')
  const [errorMsg, setErrorMsg]   = useState('')
  const [savedFlash, setSavedFlash] = useState(false)
  const textareaRef               = useRef<HTMLTextAreaElement>(null)

  // Load existing strategy on mount / dataset change
  useEffect(() => {
    setState('loading')
    setStrategy(null)
    setErrorMsg('')
    strategyService.get(datasetId)
      .then(s => {
        setStrategy(s)
        setState(s ? 'ready' : 'idle')
      })
      .catch(() => setState('idle'))
  }, [datasetId])

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px'
    }
  }, [draft, state])

  async function handleGenerate() {
    setState('loading')
    setErrorMsg('')
    try {
      const s = await strategyService.generate(datasetId)
      setStrategy(s)
      setState('ready')
    } catch {
      setErrorMsg('Failed to generate strategy. Ensure analytics have been computed for this dataset.')
      setState('error')
    }
  }

  function handleEdit() {
    if (!strategy) return
    setDraft(strategy.user_strategy)
    setState('editing')
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  async function handleSave() {
    if (!strategy) return
    setState('saving')
    try {
      const s = await strategyService.update(datasetId, draft)
      setStrategy(s)
      setState('ready')
      setSavedFlash(true)
      setTimeout(() => setSavedFlash(false), 2000)
    } catch {
      setErrorMsg('Failed to save strategy.')
      setState('editing')
    }
  }

  function handleCancelEdit() {
    setState('ready')
    setDraft('')
  }

  async function handleReset() {
    if (!strategy) return
    setState('loading')
    try {
      const s = await strategyService.reset(datasetId)
      setStrategy(s)
      setState('ready')
    } catch {
      setErrorMsg('Failed to reset strategy.')
      setState('ready')
    }
  }

  const isEdited = strategy && strategy.user_strategy !== strategy.generated_strategy

  return (
    <div
      className="rounded-xl border p-5 space-y-4"
      style={{ background: 'linear-gradient(135deg,#13131F 0%,#0C0C14 100%)', borderColor: '#252538' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <Sparkles size={15} style={{ color: '#D4A843' }} />
        <h2 className="text-sm font-semibold text-slate-100">Trailer Strategy</h2>
        {isEdited && (
          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: '#D4A84320', color: '#D4A843', border: '1px solid #D4A84335' }}>
            Edited
          </span>
        )}
        {savedFlash && (
          <span className="ml-auto text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ background: '#55A88B20', color: '#55A88B', border: '1px solid #55A88B35' }}>
            Saved
          </span>
        )}
      </div>

      {/* Body */}
      {state === 'loading' && (
        <div className="flex items-center gap-2 py-4 text-slate-500 text-sm">
          <Loader2 size={14} className="animate-spin" /> Generating strategy…
        </div>
      )}

      {state === 'saving' && (
        <div className="flex items-center gap-2 py-4 text-slate-500 text-sm">
          <Loader2 size={14} className="animate-spin" /> Saving…
        </div>
      )}

      {state === 'error' && (
        <div className="flex items-start gap-2 text-sm rounded-lg p-3"
          style={{ background: '#991B1B18', border: '1px solid #991B1B40', color: '#FCA5A5' }}>
          <AlertCircle size={14} className="shrink-0 mt-0.5" />
          <span>{errorMsg}</span>
        </div>
      )}

      {state === 'idle' && (
        <p className="text-slate-500 text-sm">
          Generate an AI trailer strategy based on this dataset's audience analytics.
        </p>
      )}

      {(state === 'ready' || state === 'editing') && strategy && (
        <div className="space-y-3">
          {state === 'editing' ? (
            <textarea
              ref={textareaRef}
              value={draft}
              onChange={e => setDraft(e.target.value)}
              className="w-full rounded-lg px-3 py-2.5 text-sm text-slate-100 resize-none leading-relaxed outline-none focus:ring-1"
              style={{
                background: '#1A1A2E',
                border: '1px solid #D4A84340',
                minHeight: 100,
                boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.3)',
              }}
              placeholder="Write your trailer strategy…"
            />
          ) : (
            <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
              {strategy.user_strategy}
            </p>
          )}

          <p className="text-[10px] text-slate-600">
            Last updated {new Date(strategy.updated_at).toLocaleString()}
          </p>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2 pt-1">
        {(state === 'idle' || state === 'error') && (
          <Button onClick={handleGenerate} className="text-xs px-3 py-1.5">
            <Sparkles size={12} /> Generate Strategy
          </Button>
        )}

        {state === 'ready' && (
          <>
            <Button onClick={handleGenerate} className="text-xs px-3 py-1.5">
              <Sparkles size={12} /> Regenerate
            </Button>
            <Button variant="ghost" onClick={handleEdit} className="text-xs px-3 py-1.5">
              <Pencil size={12} /> Edit
            </Button>
            {isEdited && (
              <Button variant="ghost" onClick={handleReset} className="text-xs px-3 py-1.5">
                <RotateCcw size={12} /> Reset to AI
              </Button>
            )}
          </>
        )}

        {state === 'editing' && (
          <>
            <Button onClick={handleSave} className="text-xs px-3 py-1.5">
              <Save size={12} /> Save
            </Button>
            <Button variant="ghost" onClick={handleCancelEdit} className="text-xs px-3 py-1.5">
              Cancel
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
