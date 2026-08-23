import { Scissors, Save, Download, RotateCcw, Loader2, CheckCircle, AlertCircle, Undo2, Redo2, SplitSquareHorizontal } from 'lucide-react'
import type { SaveStatus } from '../hooks/useAutoSave'
import type { ExportStatus } from '../hooks/useExport'

interface Props {
  projectName: string
  generationLabel: string
  jobType: 'standard' | 'smart'
  planSource: 'ai' | 'user'
  saveStatus: SaveStatus
  savedAt: string | null
  exportStatus: ExportStatus
  onResetToAI: () => void
  onExport: () => void
  // Enhanced editor controls
  onUndo?: () => void
  onRedo?: () => void
  canUndo?: boolean
  canRedo?: boolean
  onQuickDownload?: () => void
  onSplit?: () => void
}

function SaveIndicator({ status, savedAt }: { status: SaveStatus; savedAt: string | null }) {
  switch (status) {
    case 'saving':
      return (
        <span className="flex items-center gap-1.5 text-xs text-slate-400">
          <Loader2 size={12} className="animate-spin" />
          Saving…
        </span>
      )
    case 'retrying':
      return (
        <span className="flex items-center gap-1.5 text-xs text-accent-amber">
          <Loader2 size={12} className="animate-spin" />
          Save failed — retrying
        </span>
      )
    case 'failed':
      return (
        <span className="flex items-center gap-1.5 text-xs text-accent-red">
          <AlertCircle size={12} />
          Save failed
        </span>
      )
    case 'saved':
      return (
        <span className="flex items-center gap-1.5 text-xs text-accent-green">
          <CheckCircle size={12} />
          Saved{savedAt ? ` ${new Date(savedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
        </span>
      )
    default:
      return (
        <span className="flex items-center gap-1.5 text-xs text-slate-500">
          <Save size={12} />
          <span className="italic">AI plan</span>
        </span>
      )
  }
}

function ExportButton({ status, onClick }: { status: ExportStatus; onClick: () => void }) {
  const busy = status === 'starting' || status === 'rendering'

  if (busy) {
    return (
      <button
        disabled
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary/40 text-primary/60 text-xs cursor-not-allowed"
      >
        <Loader2 size={12} className="animate-spin" />
        Exporting…
      </button>
    )
  }

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-primary text-primary hover:bg-primary/10 text-xs transition-colors font-medium"
      title="Render and export the current edit as MP4"
    >
      <Download size={12} />
      {status === 'done' ? 'Export again' : 'Export'}
    </button>
  )
}

export default function EditorHeader({
  projectName, generationLabel, jobType,
  planSource, saveStatus, savedAt,
  exportStatus, onResetToAI, onExport,
  onUndo, onRedo, canUndo, canRedo,
  onQuickDownload, onSplit,
}: Props) {
  return (
    <header className="flex items-center gap-4 px-5 py-3 border-b border-surface-border bg-surface-card shrink-0">
      {/* Brand */}
      <div className="flex items-center gap-2 shrink-0">
        <Scissors size={16} className="text-primary" />
        <span className="gradient-text text-sm font-bold tracking-wide">SenseScrub</span>
      </div>

      <div className="w-px h-5 bg-surface-border shrink-0" />

      {/* Project + generation */}
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-slate-200 text-sm font-medium truncate">{projectName}</span>
        <span className="text-slate-600 text-xs shrink-0">·</span>
        <span className="text-slate-400 text-xs shrink-0">{generationLabel}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 ${
          jobType === 'smart'
            ? 'bg-accent-violet/15 text-accent-violet'
            : 'bg-primary/15 text-primary'
        }`}>
          {jobType}
        </span>
      </div>

      <div className="flex-1" />

      {/* Editing tools: Undo / Redo / Split */}
      {(onUndo || onRedo || onSplit) && (
        <div className="flex items-center gap-1">
          {onUndo && (
            <button
              onClick={onUndo}
              disabled={canUndo !== undefined && !canUndo}
              className="p-1.5 rounded hover:bg-surface-raised disabled:opacity-30 disabled:cursor-not-allowed text-slate-400 hover:text-slate-200 transition-colors"
              title="Undo (Ctrl+Z)"
            >
              <Undo2 size={14} />
            </button>
          )}
          {onRedo && (
            <button
              onClick={onRedo}
              disabled={canRedo !== undefined && !canRedo}
              className="p-1.5 rounded hover:bg-surface-raised disabled:opacity-30 disabled:cursor-not-allowed text-slate-400 hover:text-slate-200 transition-colors"
              title="Redo (Ctrl+Y)"
            >
              <Redo2 size={14} />
            </button>
          )}
          {onSplit && (
            <button
              onClick={onSplit}
              className="p-1.5 rounded hover:bg-surface-raised text-slate-400 hover:text-slate-200 transition-colors"
              title="Split at playhead (S)"
            >
              <SplitSquareHorizontal size={14} />
            </button>
          )}
        </div>
      )}

      {/* Save status */}
      <SaveIndicator status={saveStatus} savedAt={savedAt} />

      {/* Reset to AI — only shown when a user plan exists */}
      {planSource === 'user' && (
        <button
          onClick={onResetToAI}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-500 text-xs transition-colors"
          title="Discard edits and restore the AI-generated plan"
        >
          <RotateCcw size={11} />
          Reset to AI
        </button>
      )}

      {/* Export */}
      <ExportButton status={exportStatus} onClick={onExport} />
      {onQuickDownload && (
        <button
          onClick={onQuickDownload}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-500 text-xs transition-colors"
          title="Quick download (client-side render)"
        >
          <Download size={12} />
          Quick Save
        </button>
      )}
    </header>
  )
}
