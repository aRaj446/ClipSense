import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { EditorJobResponse, Project, SceneEntry } from '../types'
import { resetPlan, getScenes } from '../api/editor'
import { useEnhancedEditor } from '../hooks/useEnhancedEditor'
import { useAutoSave } from '../hooks/useAutoSave'
import { useExport } from '../hooks/useExport'
import { useExportDual } from '../hooks/useExportDual'
import { useEditorEngine } from '../engine'
import EditorHeader from './EditorHeader'
import VideoPreview from './VideoPreview'
import CanvasPreview from './CanvasPreview'
import Timeline from './Timeline'
import ExportProgress from './ExportProgress'
import SceneTable from './SceneTable'
import ClipInspector from './ClipInspector'

interface Props {
  project: Project
  editor: EditorJobResponse
  generationLabel: string
}

function fmt(secs: number) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function EditorReady({ project, editor, generationLabel }: Props) {
  const [jsonOpen, setJsonOpen] = useState(false)
  const [scenes,   setScenes]   = useState<SceneEntry[]>([])

  const [state, actions, derived] = useEnhancedEditor(editor)
  const { clips, selectedClipId, playhead, seekTarget, dirty, planSource, videoSrc, rawSrc } = state
  const { totalDuration, activeClipIndex, activeClipId, sceneToClipId, selectedClip, selectedIndex } = derived

  const debugMode = new URLSearchParams(window.location.search).has('debug')

  // OpenReel engine integration — provides frame-accurate canvas preview
  const useCanvasPreview = !new URLSearchParams(window.location.search).has('legacy-preview')
  const engineState = useEditorEngine(editor.job_id, clips, editor.raw_footage_url)

  const { saveStatus, savedAt } = useAutoSave(editor.job_id, clips, dirty)
  const { exportState, startExport, retry, dismiss } = useExport(editor.job_id, actions.setVideoSrc)
  const { controls: dualExportControls } = useExportDual(editor.job_id, actions.setVideoSrc)

  // Load scenes once on mount
  useEffect(() => {
    getScenes(editor.job_id).then(setScenes).catch(() => {})
  }, [editor.job_id])

  // Unsaved-changes guard
  useEffect(() => {
    function handleBeforeUnload(e: BeforeUnloadEvent) {
      if (!dirty) return
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [dirty])

  // Ref for imperative play/pause from VideoPreview
  const videoPlayPauseRef = useRef<(() => void) | null>(null)

  // Refs that mirror fast-changing state so the keyboard handler never
  // needs to be re-registered during playback (~30fps timeupdate ticks).
  const clipsRef          = useRef(clips)
  const playheadRef       = useRef(playhead)
  const totalDurationRef  = useRef(totalDuration)
  const activeClipIdxRef  = useRef(activeClipIndex)
  const selectedIdxRef    = useRef(selectedIndex)
  const selectedClipIdRef = useRef(selectedClipId)
  useEffect(() => {
    clipsRef.current         = clips
    playheadRef.current      = playhead
    totalDurationRef.current = totalDuration
    activeClipIdxRef.current = activeClipIndex
    selectedIdxRef.current   = selectedIndex
    selectedClipIdRef.current = selectedClipId
  })

  // Global keyboard shortcuts — registered once, reads state via refs.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return

      // Ctrl/Cmd shortcuts (undo, redo) — handle before the ctrlKey guard
      if (e.ctrlKey || e.metaKey) {
        switch (e.key.toLowerCase()) {
          case 'z':
            e.preventDefault()
            if (e.shiftKey) {
              actions.redo()
            } else {
              actions.undo()
            }
            return
          case 'y':
            e.preventDefault()
            actions.redo()
            return
        }
        return // All other Ctrl/Cmd combos — ignore
      }

      const c   = clipsRef.current
      const ph  = playheadRef.current
      const dur = totalDurationRef.current
      const ai  = activeClipIdxRef.current
      const si  = selectedIdxRef.current
      const sc  = selectedClipIdRef.current

      switch (e.key) {

        // Space: play / pause
        case ' ':
          e.preventDefault()
          videoPlayPauseRef.current?.()
          break

        // ArrowLeft: seek -5s  |  Shift+ArrowLeft: jump to previous clip
        case 'ArrowLeft':
          e.preventDefault()
          if (e.shiftKey) {
            const prevClip = c[Math.max(0, ai - 1)]
            if (prevClip) actions.seekToRaw(prevClip.start_time)
          } else {
            actions.seekToAssembled(Math.max(0, ph - 5))
          }
          break

        // ArrowRight: seek +5s  |  Shift+ArrowRight: jump to next clip
        case 'ArrowRight':
          e.preventDefault()
          if (e.shiftKey) {
            const nextClip = c[Math.min(c.length - 1, ai + 1)]
            if (nextClip) actions.seekToRaw(nextClip.start_time)
          } else {
            actions.seekToAssembled(Math.min(dur, ph + 5))
          }
          break

        // [: select previous clip in timeline
        case '[': {
          e.preventDefault()
          const base = si >= 0 ? si : ai
          const prev = c[Math.max(0, base - 1)]
          if (prev) actions.selectClip(prev.id)
          break
        }

        // ]: select next clip in timeline
        case ']': {
          e.preventDefault()
          const base = si >= 0 ? si : ai
          const next = c[Math.min(c.length - 1, base + 1)]
          if (next) actions.selectClip(next.id)
          break
        }

        // Escape: deselect current clip
        case 'Escape':
          if (sc !== null) {
            e.preventDefault()
            actions.selectClip(null)
          }
          break

        // S: split clip at playhead
        case 's':
        case 'S':
          e.preventDefault()
          actions.splitAtPlayhead()
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [actions])

  // Timeline bridge: index-based callbacks to ID-based actions
  const handleTimelineSeek = useCallback((rawTime: number) => {
    actions.seekToRaw(rawTime)
  }, [actions])

  const handleTimelineSelectClip = useCallback((id: string | null) => {
    actions.selectClip(id)
  }, [actions])

  const handleDelete = useCallback((index: number) => {
    const clip = clips[index]
    if (clip) actions.removeClip(clip.id)
  }, [clips, actions])

  const handleReorder = useCallback((from: number, to: number) => {
    actions.reorderClip(from, to)
  }, [actions])

  const handleTrim = useCallback((index: number, newStart: number, newEnd: number) => {
    const clip = clips[index]
    if (clip) actions.trimClip(clip.id, newStart, newEnd)
  }, [clips, actions])

  const handleMute = useCallback((index: number) => {
    const clip = clips[index]
    if (clip) actions.toggleMute(clip.id)
  }, [clips, actions])

  const handleResetToAI = useCallback(async () => {
    try {
      await resetPlan(editor.job_id)
      const aiClips = (editor.plan?.clips ?? []).map(c => ({ ...c, muted: c.muted ?? false }))
      actions.resetToAiPlan(aiClips)
    } catch {
      // Silent
    }
  }, [editor.job_id, editor.plan, actions])

  const handleInspectorSeek = useCallback((rawTime: number) => {
    actions.seekToRaw(rawTime)
  }, [actions])

  const handleInspectorClose = useCallback(() => {
    actions.selectClip(null)
  }, [actions])

  const handleResetTrim = useCallback((index: number, origStart: number, origEnd: number) => {
    const clip = clips[index]
    if (clip) actions.trimClip(clip.id, origStart, origEnd)
  }, [clips, actions])

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface">

      <EditorHeader
        projectName={project.name ?? project.filename}
        generationLabel={generationLabel}
        jobType={editor.job_type}
        planSource={planSource}
        saveStatus={saveStatus}
        savedAt={savedAt}
        exportStatus={exportState.status}
        onResetToAI={handleResetToAI}
        onExport={startExport}
        onUndo={actions.undo}
        onRedo={actions.redo}
        canUndo={actions.canUndo()}
        canRedo={actions.canRedo()}
        onSplit={actions.splitAtPlayhead}
        onQuickDownload={() => dualExportControls.quickDownload(engineState.project)}
      />

      {exportState.status !== 'idle' && (
        <ExportProgress
          state={exportState}
          onRetry={retry}
          onDismiss={dismiss}
        />
      )}

      <div className="flex flex-1 overflow-hidden">

        {/* Left column: video + timeline */}
        <div className="flex flex-col flex-1 min-w-0 overflow-hidden">

          <div className="flex-1 min-h-0 overflow-hidden bg-black">
            {useCanvasPreview && engineState.webCodecsSupported ? (
              <CanvasPreview
                project={engineState.project}
                clips={clips}
                seekTarget={seekTarget}
                onCurrentTime={actions.setPlayhead}
                onPlayPauseRef={videoPlayPauseRef}
                loading={engineState.loading}
                loadProgress={engineState.loadProgress}
                engineError={engineState.engineError}
              />
            ) : (
              <VideoPreview
                src={videoSrc}
                rawSrc={rawSrc}
                clips={clips}
                seekTarget={seekTarget}
                onCurrentTime={actions.setPlayhead}
                onPlayPauseRef={videoPlayPauseRef}
              />
            )}
          </div>

          <div className="shrink-0 border-t border-surface-border bg-surface-card overflow-y-auto max-h-[40vh]">
            <div className="flex items-center justify-between px-4 py-2 border-b border-surface-border/60">
              <span className="text-[9px] text-slate-500 uppercase tracking-wide font-medium">Timeline</span>
              {/* Global shortcut hints */}
              <div className="flex items-center gap-1.5 text-[9px] text-slate-700">
                {[
                  { key: 'Space',   hint: 'play' },
                  { key: '←→',      hint: '±5s' },
                  { key: 'Shift+←→', hint: 'clip' },
                  { key: '[ ]',     hint: 'select' },
                  { key: 'S',       hint: 'split' },
                  { key: 'Ctrl+Z',  hint: 'undo' },
                  { key: 'Esc',     hint: 'deselect' },
                ].map(({ key, hint }) => (
                  <span key={key} className="flex items-center gap-0.5">
                    <kbd className="px-1 py-0.5 rounded bg-surface-raised border border-surface-border/80 font-mono text-slate-600">
                      {key}
                    </kbd>
                    <span className="text-slate-700">{hint}</span>
                  </span>
                ))}
              </div>
            </div>
            <Timeline
              clips={clips}
              currentTime={playhead}
              selectedClipId={selectedClipId}
              activeClipIndex={activeClipIndex}
              onSelectClip={handleTimelineSelectClip}
              onSeek={handleTimelineSeek}
              onDelete={handleDelete}
              onReorder={handleReorder}
              onTrim={handleTrim}
              onMute={handleMute}
              onTrimFirst={actions.trimFirstClip}
              onTrimLast={actions.trimLastClip}
            />
          </div>
        </div>

        {/* Right sidebar */}
        <aside className="w-72 xl:w-80 shrink-0 flex flex-col border-l border-surface-border bg-surface-card overflow-y-auto">

          {selectedClip !== null && selectedIndex >= 0 && (() => {
            const matchScene = scenes.find(s => s.start_time === selectedClip.start_time)
              ?? scenes.reduce<typeof scenes[0] | null>((best, s) =>
                  best === null || Math.abs(s.start_time - selectedClip.start_time) < Math.abs(best.start_time - selectedClip.start_time)
                    ? s : best
                , null)
            const origStart = matchScene?.start_time ?? selectedClip.start_time
            const origEnd   = matchScene?.end_time   ?? selectedClip.end_time
            return (
              <div className="shrink-0 border-b border-surface-border">
                <ClipInspector
                  clip={selectedClip}
                  index={selectedIndex}
                  origStart={origStart}
                  origEnd={origEnd}
                  onClose={handleInspectorClose}
                  onSeek={handleInspectorSeek}
                  onDelete={handleDelete}
                  onMute={handleMute}
                  onResetTrim={handleResetTrim}
                  onSpeedChange={actions.setClipSpeed}
                />
              </div>
            )
          })()}

          <div className="flex-1 min-h-0">
            <SceneTable
              scenes={scenes}
              sceneToClipId={sceneToClipId}
              selectedClipId={selectedClipId}
              activeClipId={activeClipId}
              onSelectClip={actions.selectClip}
              onAdd={actions.addClip}
              onRemove={actions.removeClip}
            />
          </div>

          {/* Job metadata */}
          <div className="shrink-0 border-t border-surface-border p-3 space-y-1">
            <p className="text-[9px] text-slate-600 uppercase tracking-wide font-medium px-1 mb-2">Job info</p>
            <div className="grid grid-cols-2 gap-1.5">
              {[
                { label: 'Job ID',   value: editor.job_id.slice(0, 8) + '…' },
                { label: 'Type',     value: editor.job_type },
                { label: 'Clips',    value: String(clips.length) },
                { label: 'Duration', value: fmt(totalDuration) },
                { label: 'Score',    value: editor.clip_score != null ? `${Math.round(editor.clip_score * 100)}%` : '—' },
                { label: 'Platform', value: editor.platform ?? '—' },
                { label: 'Plan',     value: planSource },
                { label: 'Status',   value: editor.status },
              ].map(({ label, value }) => (
                <div key={label} className="bg-surface-raised/50 rounded-lg px-2.5 py-2">
                  <p className="text-[9px] text-slate-600 uppercase tracking-wide mb-0.5">{label}</p>
                  <p className="text-slate-300 text-[11px] font-mono truncate">{value}</p>
                </div>
              ))}
            </div>
            {editor.plan?.rationale && (
              <p className="text-[10px] text-slate-500 italic px-1 pt-1 leading-relaxed">
                {editor.plan.rationale}
              </p>
            )}
          </div>

          {/* Debug panel */}
          {debugMode && (
            <div className="shrink-0 border-t border-surface-border">
              <button
                onClick={() => setJsonOpen(o => !o)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-surface-raised/30 transition-colors"
              >
                {jsonOpen
                  ? <ChevronDown  size={11} className="text-slate-500 shrink-0" />
                  : <ChevronRight size={11} className="text-slate-500 shrink-0" />
                }
                <span className="text-[10px] text-slate-500 font-medium">Debug state</span>
              </button>
              {jsonOpen && (
                <pre className="px-3 pb-3 text-[10px] text-slate-400 overflow-x-auto leading-relaxed border-t border-surface-border max-h-64">
                  {JSON.stringify({ state, derived }, null, 2)}
                </pre>
              )}
            </div>
          )}

        </aside>
      </div>
    </div>
  )
}
