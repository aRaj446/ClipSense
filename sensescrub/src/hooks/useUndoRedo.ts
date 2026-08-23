/**
 * useUndoRedo — Lightweight undo/redo history for SenseScrub clip editing
 *
 * Maintains a snapshot stack of EditorClip[] arrays. Each mutating action
 * (trim, reorder, delete, add, mute, split, speed change) pushes the previous
 * state onto the undo stack. Undo pops from that stack and pushes to redo.
 *
 * This is simpler than OpenReel's full ActionExecutor (which handles multi-track
 * NLE operations) but perfectly fits SenseScrub's single-track flat clip model.
 *
 * Max history depth: 50 steps (prevents memory bloat on long editing sessions).
 */

import { useCallback, useRef } from 'react'
import type { EditorClip } from '../types'

const MAX_HISTORY = 50

export interface UndoRedoControls {
  /** Push current clip state before a mutation. Call BEFORE changing clips. */
  pushSnapshot: (clips: EditorClip[]) => void
  /** Undo — returns the previous clip state, or null if nothing to undo */
  undo: (currentClips: EditorClip[]) => EditorClip[] | null
  /** Redo — returns the next clip state, or null if nothing to redo */
  redo: (currentClips: EditorClip[]) => EditorClip[] | null
  /** Whether undo is available */
  canUndo: () => boolean
  /** Whether redo is available */
  canRedo: () => boolean
  /** Clear all history (e.g., on reset to AI plan) */
  clear: () => void
}

export function useUndoRedo(): UndoRedoControls {
  const undoStack = useRef<EditorClip[][]>([])
  const redoStack = useRef<EditorClip[][]>([])

  const pushSnapshot = useCallback((clips: EditorClip[]) => {
    // Deep clone the clips array (shallow clone of each clip object is sufficient
    // since clip fields are primitives/strings)
    undoStack.current.push(clips.map(c => ({ ...c })))
    // Trim to max history
    if (undoStack.current.length > MAX_HISTORY) {
      undoStack.current.shift()
    }
    // Any new action invalidates the redo stack
    redoStack.current = []
  }, [])

  const undo = useCallback((currentClips: EditorClip[]): EditorClip[] | null => {
    if (undoStack.current.length === 0) return null
    // Push current state onto redo stack
    redoStack.current.push(currentClips.map(c => ({ ...c })))
    // Pop previous state from undo stack
    return undoStack.current.pop()!
  }, [])

  const redo = useCallback((currentClips: EditorClip[]): EditorClip[] | null => {
    if (redoStack.current.length === 0) return null
    // Push current state onto undo stack
    undoStack.current.push(currentClips.map(c => ({ ...c })))
    // Pop next state from redo stack
    return redoStack.current.pop()!
  }, [])

  const canUndo = useCallback(() => undoStack.current.length > 0, [])
  const canRedo = useCallback(() => redoStack.current.length > 0, [])

  const clear = useCallback(() => {
    undoStack.current = []
    redoStack.current = []
  }, [])

  return { pushSnapshot, undo, redo, canUndo, canRedo, clear }
}
