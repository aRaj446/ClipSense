import { useEffect, useRef, useCallback, useState } from 'react'
import type { EditorClip } from '../types'
import { savePlan } from '../api/editor'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'retrying' | 'failed'

const DEBOUNCE_MS = 1000
const RETRY_MS    = 2000

interface UseAutoSaveResult {
  saveStatus: SaveStatus
  savedAt: string | null   // ISO timestamp from server response
  forceSave: () => void
}

export function useAutoSave(
  jobId: string,
  clips: EditorClip[],
  dirty: boolean,
): UseAutoSaveResult {
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle')
  const [savedAt,    setSavedAt]    = useState<string | null>(null)

  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retryTimer    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestClips   = useRef<EditorClip[]>(clips)
  const saving        = useRef(false)

  // Keep latestClips in sync without triggering the effect
  useEffect(() => { latestClips.current = clips }, [clips])

  const doSave = useCallback(async (attempt = 1) => {
    if (saving.current) return
    saving.current = true
    setSaveStatus(attempt === 1 ? 'saving' : 'retrying')

    try {
      const result = await savePlan(jobId, latestClips.current)
      setSavedAt(result.plan_updated_at)
      setSaveStatus('saved')
    } catch {
      if (attempt === 1) {
        setSaveStatus('retrying')
        retryTimer.current = setTimeout(() => {
          saving.current = false
          doSave(2)
        }, RETRY_MS)
        return
      }
      setSaveStatus('failed')
    } finally {
      if (attempt !== 1 || saveStatus !== 'retrying') {
        saving.current = false
      }
    }
  }, [jobId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Debounced auto-save whenever dirty clips change
  useEffect(() => {
    if (!dirty) return

    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    if (retryTimer.current)    clearTimeout(retryTimer.current)
    saving.current = false

    debounceTimer.current = setTimeout(() => doSave(1), DEBOUNCE_MS)

    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [clips, dirty, doSave])

  // Cleanup on unmount
  useEffect(() => () => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    if (retryTimer.current)    clearTimeout(retryTimer.current)
  }, [])

  const forceSave = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    saving.current = false
    doSave(1)
  }, [doSave])

  return { saveStatus, savedAt, forceSave }
}
