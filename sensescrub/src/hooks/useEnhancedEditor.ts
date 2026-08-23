/**
 * useEnhancedEditor — Extended editor state with undo/redo, split, and speed
 *
 * Wraps useEditorState and adds:
 *   - Undo/redo with Ctrl+Z / Ctrl+Y keyboard shortcuts
 *   - Split-at-playhead (S key)
 *   - Per-clip speed control
 *   - History-tracked mutations (all existing ops now push undo snapshots)
 *
 * Drop-in replacement for useEditorState in EditorReady.
 */

import { useCallback } from 'react'
import type { EditorJobResponse, EditorClip, SceneEntry } from '../types'
import { useEditorState, type EditorState, type EditorActions, type DerivedEditorState } from './useEditorState'
import { useUndoRedo } from './useUndoRedo'
import { assembledToRaw } from '../utils/timeline'

// ── Extended actions interface ─────────────────────────────────────────────────

export interface EnhancedEditorActions extends EditorActions {
  /** Split the clip under the playhead at the current position */
  splitAtPlayhead: () => void
  /** Set speed for a clip (0.25–4.0). Stored as `speed` field on clip. */
  setClipSpeed: (clipId: string, speed: number) => void
  /** Undo the last editing action */
  undo: () => void
  /** Redo the last undone action */
  redo: () => void
  /** Whether undo is available */
  canUndo: () => boolean
  /** Whether redo is available */
  canRedo: () => boolean
}

// ── ID generation ─────────────────────────────────────────────────────────────

let _splitSeq = 2000
function nextSplitId(): string {
  return `clip-${Date.now()}-${++_splitSeq}`
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useEnhancedEditor(
  editor: EditorJobResponse,
): [EditorState, EnhancedEditorActions, DerivedEditorState] {
  const [state, baseActions, derived] = useEditorState(editor)
  const undoRedo = useUndoRedo()

  // ── Helper: mutate with undo snapshot ───────────────────────────────────
  // All mutations that change clips go through this pattern:
  //   1. Push current clips as undo snapshot
  //   2. Call the actual mutation

  const addClip = useCallback((scene: SceneEntry) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.addClip(scene)
  }, [state.clips, baseActions, undoRedo])

  const removeClip = useCallback((id: string) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.removeClip(id)
  }, [state.clips, baseActions, undoRedo])

  const reorderClip = useCallback((fromIndex: number, toIndex: number) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.reorderClip(fromIndex, toIndex)
  }, [state.clips, baseActions, undoRedo])

  const trimClip = useCallback((id: string, newStart: number, newEnd: number) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.trimClip(id, newStart, newEnd)
  }, [state.clips, baseActions, undoRedo])

  const trimFirstClip = useCallback((newStart: number) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.trimFirstClip(newStart)
  }, [state.clips, baseActions, undoRedo])

  const trimLastClip = useCallback((newEnd: number) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.trimLastClip(newEnd)
  }, [state.clips, baseActions, undoRedo])

  const toggleMute = useCallback((id: string) => {
    undoRedo.pushSnapshot(state.clips)
    baseActions.toggleMute(id)
  }, [state.clips, baseActions, undoRedo])

  const resetToAiPlan = useCallback((aiClips: EditorClip[]) => {
    undoRedo.clear()
    baseActions.resetToAiPlan(aiClips)
  }, [baseActions, undoRedo])

  // ── Split at playhead ───────────────────────────────────────────────────

  const splitAtPlayhead = useCallback(() => {
    const { clips, playhead } = state
    if (clips.length === 0) return

    // Convert assembled playhead time to raw footage time
    const rawTime = assembledToRaw(playhead, clips)

    // Find the clip containing this raw time (strictly inside, not at boundaries)
    const clipIndex = clips.findIndex(
      c => rawTime > c.start_time + 0.1 && rawTime < c.end_time - 0.1
    )
    if (clipIndex < 0) return

    const clip = clips[clipIndex]

    // Minimum 0.5s per resulting clip
    const leftDuration = rawTime - clip.start_time
    const rightDuration = clip.end_time - rawTime
    if (leftDuration < 0.5 || rightDuration < 0.5) return

    // Push undo snapshot BEFORE mutation
    undoRedo.pushSnapshot(clips)

    // Create the two halves
    const leftClip: EditorClip = {
      ...clip,
      // Keep original ID for left portion
      end_time: rawTime,
    }

    const rightClip: EditorClip = {
      ...clip,
      id: nextSplitId(),
      start_time: rawTime,
    }

    // Build new clips array with the split
    const newClips = [...clips]
    newClips.splice(clipIndex, 1, leftClip, rightClip)

    // Set directly via setClips (preserves dirty state)
    baseActions.setClips(newClips)
  }, [state, baseActions, undoRedo])

  // ── Set clip speed ──────────────────────────────────────────────────────

  const setClipSpeed = useCallback((clipId: string, speed: number) => {
    const clampedSpeed = Math.max(0.25, Math.min(4, speed))

    undoRedo.pushSnapshot(state.clips)

    // Store speed on the clip object. We add it as a custom field.
    // The EditorClip type will need to be extended, but for now we cast.
    const newClips = state.clips.map(c => {
      if (c.id !== clipId) return c
      return { ...c, speed: clampedSpeed } as EditorClip
    })

    baseActions.setClips(newClips)
  }, [state.clips, baseActions, undoRedo])

  // ── Undo / Redo ─────────────────────────────────────────────────────────

  const undo = useCallback(() => {
    const prevClips = undoRedo.undo(state.clips)
    if (prevClips) {
      baseActions.setClips(prevClips)
    }
  }, [state.clips, baseActions, undoRedo])

  const redo = useCallback(() => {
    const nextClips = undoRedo.redo(state.clips)
    if (nextClips) {
      baseActions.setClips(nextClips)
    }
  }, [state.clips, baseActions, undoRedo])

  // ── Assemble enhanced actions ───────────────────────────────────────────

  const enhancedActions: EnhancedEditorActions = {
    ...baseActions,
    // Override mutations with undo-tracked versions
    addClip,
    removeClip,
    reorderClip,
    trimClip,
    trimFirstClip,
    trimLastClip,
    toggleMute,
    resetToAiPlan,
    // New operations
    splitAtPlayhead,
    setClipSpeed,
    undo,
    redo,
    canUndo: undoRedo.canUndo,
    canRedo: undoRedo.canRedo,
  }

  return [state, enhancedActions, derived]
}
