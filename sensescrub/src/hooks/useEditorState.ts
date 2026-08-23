import { useState, useCallback, useMemo } from 'react'
import type { EditorClip, EditorJobResponse, SceneEntry } from '../types'
import { videoUrl } from '../api/editor'
import { totalDuration, computeTimelineOffsets, assembledToRaw } from '../utils/timeline'

// ── ID generation ─────────────────────────────────────────────────────────────

let _seq = 0
function nextId(): string {
  return `clip-${Date.now()}-${++_seq}`
}

function withId(c: Omit<EditorClip, 'id'>): EditorClip {
  return { ...c, id: nextId() }
}

// ── State shape ───────────────────────────────────────────────────────────────

export interface EditorState {
  // Identity
  jobId:       string
  projectId:   string
  jobType:     'standard' | 'smart'

  // Media
  rawSrc:      string | null   // raw footage URL (live preview)
  videoSrc:    string | null   // rendered output URL

  // Clips — the single authoritative list
  clips:       EditorClip[]

  // Selection
  selectedClipId: string | null

  // Playhead — assembled trailer time (0 → totalDuration)
  playhead:    number
  // seekTarget — raw footage timestamp; consumed by VideoPreview
  seekTarget:  number | null

  // Persistence
  dirty:       boolean
  planSource:  'ai' | 'user'
}

// ── Derived state (pure, no useState) ─────────────────────────────────────────

export interface DerivedEditorState {
  totalDuration:   number
  clipOffsets:     ReturnType<typeof computeTimelineOffsets>
  selectedClip:    EditorClip | null
  selectedIndex:   number
  activeClipIndex: number          // clip index under the current playhead
  activeClipId:    string | null   // clip id under the current playhead
  /** Maps source start_time → clip id for the first matching trailer clip */
  sceneToClipId:   Map<number, string>
}

export function deriveEditorState(state: EditorState): DerivedEditorState {
  const dur     = totalDuration(state.clips)
  const offsets = computeTimelineOffsets(state.clips)

  const selectedIndex = state.selectedClipId
    ? state.clips.findIndex(c => c.id === state.selectedClipId)
    : -1
  const selectedClip = selectedIndex >= 0 ? state.clips[selectedIndex] : null

  // Active clip = clip whose raw range contains the current playhead position
  const rawPos = assembledToRaw(state.playhead, state.clips)
  const activeClipIndex = state.clips.findIndex(
    c => rawPos >= c.start_time && rawPos < c.end_time
  )
  const activeClipId = activeClipIndex >= 0 ? state.clips[activeClipIndex].id : null

  // Map source start_time → clip id (first match wins — handles duplicates)
  const sceneToClipId = new Map<number, string>()
  for (const c of state.clips) {
    if (!sceneToClipId.has(c.start_time)) sceneToClipId.set(c.start_time, c.id)
  }

  return { totalDuration: dur, clipOffsets: offsets, selectedClip, selectedIndex, activeClipIndex, activeClipId, sceneToClipId }
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface EditorActions {
  // LOAD_EDITOR_STATE — called once on mount with server response
  loadEditorState: (editor: EditorJobResponse) => void

  // SELECT_CLIP
  selectClip: (id: string | null) => void

  // ADD_CLIP — from scene browser
  addClip: (scene: SceneEntry) => void

  // REMOVE_CLIP
  removeClip: (id: string) => void

  // REORDER_CLIP
  reorderClip: (fromIndex: number, toIndex: number) => void

  // TRIM_CLIP
  trimClip: (id: string, newStart: number, newEnd: number) => void

  // Convenience trims for InOutBar
  trimFirstClip: (newStart: number) => void
  trimLastClip:  (newEnd: number)   => void

  // SET_PLAYHEAD — assembled trailer time reported by VideoPreview
  setPlayhead: (assembledTime: number) => void

  // Seek — sets seekTarget (raw footage coords) for VideoPreview
  seekToClip: (id: string) => void
  seekToRaw:  (rawTime: number) => void
  seekToAssembled: (assembledTime: number) => void

  // SET_VOLUME / mute per clip
  toggleMute: (id: string) => void

  // RESET_TO_AI_PLAN
  resetToAiPlan: (aiClips: EditorClip[]) => void

  // SAVE_EDITOR_STATE — called by useAutoSave after successful PUT
  markSaved: () => void

  // After export: update rendered video URL
  setVideoSrc: (url: string) => void

  // Direct clip replacement — used by undo/redo and split
  setClips: (clips: EditorClip[]) => void
}

export function useEditorState(editor: EditorJobResponse): [EditorState, EditorActions, DerivedEditorState] {
  const rawSrc = editor.raw_footage_url ? videoUrl(editor.raw_footage_url) : null

  const [state, setState] = useState<EditorState>(() => ({
    jobId:          editor.job_id,
    projectId:      editor.project_id,
    jobType:        editor.job_type,
    rawSrc,
    videoSrc:       editor.output_url ? videoUrl(editor.output_url) : null,
    clips:          (editor.plan?.clips ?? []).map(c => withId({ ...c, muted: c.muted ?? false })),
    selectedClipId: null,
    playhead:       0,
    seekTarget:     null,
    dirty:          false,
    planSource:     editor.plan_source,
  }))

  // ── Internal mutate helper ────────────────────────────────────────────────
  const mutate = useCallback((updater: (prev: EditorState) => Partial<EditorState>) => {
    setState(prev => ({ ...prev, ...updater(prev), dirty: true, planSource: 'user' }))
  }, [])

  // ── Actions ───────────────────────────────────────────────────────────────

  const loadEditorState = useCallback((ed: EditorJobResponse) => {
    const rs = ed.raw_footage_url ? videoUrl(ed.raw_footage_url) : null
    setState({
      jobId:          ed.job_id,
      projectId:      ed.project_id,
      jobType:        ed.job_type,
      rawSrc:         rs,
      videoSrc:       ed.output_url ? videoUrl(ed.output_url) : null,
      clips:          (ed.plan?.clips ?? []).map(c => withId({ ...c, muted: c.muted ?? false })),
      selectedClipId: null,
      playhead:       0,
      seekTarget:     null,
      dirty:          false,
      planSource:     ed.plan_source,
    })
  }, [])

  const selectClip = useCallback((id: string | null) => {
    setState(prev => {
      if (id === null) return { ...prev, selectedClipId: null }
      const clip = prev.clips.find(c => c.id === id)
      if (!clip) return { ...prev, selectedClipId: null }
      // Seek to clip start on selection
      return { ...prev, selectedClipId: id, seekTarget: clip.start_time }
    })
  }, [])

  const addClip = useCallback((scene: SceneEntry) => {
    mutate(prev => ({
      clips: [
        ...prev.clips,
        withId({
          start_time:      scene.start_time,
          end_time:        scene.end_time,
          topic:           scene.topic,
          sentiment:       scene.sentiment,
          reason:          scene.reason,
          transcript_text: scene.transcript_text,
          mood_group:      scene.mood_group,
          platform:        scene.platform,
          muted:           false,
        }),
      ],
    }))
  }, [mutate])

  const removeClip = useCallback((id: string) => {
    mutate(prev => ({
      clips:          prev.clips.filter(c => c.id !== id),
      selectedClipId: prev.selectedClipId === id ? null : prev.selectedClipId,
    }))
  }, [mutate])

  const reorderClip = useCallback((fromIndex: number, toIndex: number) => {
    mutate(prev => {
      const next = [...prev.clips]
      const [moved] = next.splice(fromIndex, 1)
      next.splice(toIndex, 0, moved)
      return { clips: next }
    })
  }, [mutate])

  const trimClip = useCallback((id: string, newStart: number, newEnd: number) => {
    mutate(prev => ({
      clips: prev.clips.map(c =>
        c.id === id ? { ...c, start_time: newStart, end_time: newEnd } : c
      ),
    }))
  }, [mutate])

  const trimFirstClip = useCallback((newStart: number) => {
    mutate(prev => {
      if (!prev.clips.length) return {}
      const next = [...prev.clips]
      next[0] = { ...next[0], start_time: newStart }
      return { clips: next }
    })
  }, [mutate])

  const trimLastClip = useCallback((newEnd: number) => {
    mutate(prev => {
      if (!prev.clips.length) return {}
      const next = [...prev.clips]
      next[next.length - 1] = { ...next[next.length - 1], end_time: newEnd }
      return { clips: next }
    })
  }, [mutate])

  const setPlayhead = useCallback((assembledTime: number) => {
    setState(prev => ({ ...prev, playhead: assembledTime }))
  }, [])

  const seekToClip = useCallback((id: string) => {
    setState(prev => {
      const clip = prev.clips.find(c => c.id === id)
      if (!clip) return prev
      return { ...prev, selectedClipId: id, seekTarget: clip.start_time }
    })
  }, [])

  const seekToRaw = useCallback((rawTime: number) => {
    setState(prev => ({ ...prev, seekTarget: rawTime }))
  }, [])

  const seekToAssembled = useCallback((assembledTime: number) => {
    setState(prev => {
      const rawTime = assembledToRaw(assembledTime, prev.clips)
      return { ...prev, seekTarget: rawTime }
    })
  }, [])

  const toggleMute = useCallback((id: string) => {
    mutate(prev => ({
      clips: prev.clips.map(c => c.id === id ? { ...c, muted: !c.muted } : c),
    }))
  }, [mutate])

  const resetToAiPlan = useCallback((aiClips: EditorClip[]) => {
    setState(prev => ({
      ...prev,
      clips:          aiClips.map(c => withId({ ...c, muted: c.muted ?? false })),
      selectedClipId: null,
      dirty:          false,
      planSource:     'ai',
      seekTarget:     null,
      playhead:       0,
    }))
  }, [])

  const markSaved = useCallback(() => {
    setState(prev => ({ ...prev, dirty: false }))
  }, [])

  const setVideoSrc = useCallback((url: string) => {
    setState(prev => ({ ...prev, videoSrc: url }))
  }, [])

  // Direct clip replacement — used by undo/redo and split operations.
  // Marks state as dirty and planSource as 'user'.
  const setClips = useCallback((clips: EditorClip[]) => {
    setState(prev => ({
      ...prev,
      clips,
      dirty: true,
      planSource: 'user' as const,
      selectedClipId: prev.selectedClipId && clips.find(c => c.id === prev.selectedClipId)
        ? prev.selectedClipId
        : null,
    }))
  }, [])

  const actions: EditorActions = {
    loadEditorState,
    selectClip,
    addClip,
    removeClip,
    reorderClip,
    trimClip,
    trimFirstClip,
    trimLastClip,
    setPlayhead,
    seekToClip,
    seekToRaw,
    seekToAssembled,
    toggleMute,
    resetToAiPlan,
    markSaved,
    setVideoSrc,
    setClips,
  }

  // Clip-stable derived values — only recompute when clips array changes
  const clipsDerived = useMemo(() => {
    const offsets = computeTimelineOffsets(state.clips)
    const sceneToClipId = new Map<number, string>()
    for (const c of state.clips) {
      if (!sceneToClipId.has(c.start_time)) sceneToClipId.set(c.start_time, c.id)
    }
    return { clipOffsets: offsets, sceneToClipId }
  }, [state.clips])

  // Playhead-dependent derived values — recompute on every tick
  const selectedIndex = state.selectedClipId
    ? state.clips.findIndex(c => c.id === state.selectedClipId)
    : -1
  const selectedClip = selectedIndex >= 0 ? state.clips[selectedIndex] : null
  const rawPos = assembledToRaw(state.playhead, state.clips)
  const activeClipIndex = state.clips.findIndex(
    c => rawPos >= c.start_time && rawPos < c.end_time
  )
  const activeClipId = activeClipIndex >= 0 ? state.clips[activeClipIndex].id : null

  const derived: DerivedEditorState = {
    totalDuration:   totalDuration(state.clips),
    clipOffsets:     clipsDerived.clipOffsets,
    sceneToClipId:   clipsDerived.sceneToClipId,
    selectedClip,
    selectedIndex,
    activeClipIndex,
    activeClipId,
  }

  return [state, actions, derived]
}
