/**
 * useEditorEngine — Full integration hook for the OpenReel engine in SenseScrub
 *
 * Orchestrates the complete lifecycle:
 *   1. Engine initialization (WebCodecs, VideoEngine, PlaybackController)
 *   2. Raw footage download (blob with progress tracking)
 *   3. Project construction (EditorClip[] → OpenReel Project)
 *   4. Auto-rebuild when clips change
 *
 * Usage in EditorReady:
 * ```tsx
 * const { project, loading, loadProgress, engineError, webCodecsSupported } =
 *   useEditorEngine(editor.job_id, clips, editor.raw_footage_url)
 * ```
 */

import { useState, useEffect, useRef, useMemo } from 'react'
import type { Project } from '@openreel/core'
import type { EditorClip } from '../types'
import type { EngineStatus, MediaLoadProgress } from './types'
import { useEngine } from './useEngine'
import { loadRawFootage, releaseMediaUrl } from './media-loader'
import { buildProject, rebuildProject } from './project-bridge'
import type { MediaMetadata } from '@openreel/core'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface EditorEngineState {
  /** The OpenReel Project (null until media loaded and project built) */
  project: Project | null
  /** Whether we're still loading (engine init or media download) */
  loading: boolean
  /** Current loading phase description */
  loadingPhase: string
  /** Media download progress (0-100) */
  loadProgress: number
  /** Error message if anything failed */
  engineError: string | null
  /** Whether the browser supports WebCodecs (determines canvas vs fallback) */
  webCodecsSupported: boolean
  /** Whether the engine is fully ready and project is built */
  ready: boolean
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useEditorEngine(
  jobId: string,
  clips: EditorClip[],
  rawFootageUrl: string | null,
): EditorEngineState {
  // Phase 1: Engine initialization
  const { ready: engineReady, error: engineError, engine, webCodecsSupported } = useEngine()

  // Phase 2: Media loading state
  const [mediaBlob, setMediaBlob] = useState<Blob | null>(null)
  const [mediaMetadata, setMediaMetadata] = useState<MediaMetadata | null>(null)
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const [mediaLoading, setMediaLoading] = useState(false)
  const [loadProgress, setLoadProgress] = useState(0)
  const [loadingPhase, setLoadingPhase] = useState('Initializing engine...')
  const [mediaError, setMediaError] = useState<string | null>(null)

  // Phase 3: Project state
  const [project, setProject] = useState<Project | null>(null)

  // Refs for abort control
  const abortRef = useRef<AbortController | null>(null)
  const prevClipsRef = useRef<EditorClip[]>(clips)

  // ── Phase 2: Load raw footage after engine is ready ───────────────────────
  useEffect(() => {
    if (!engineReady || !webCodecsSupported || !rawFootageUrl || mediaBlob) return

    const abortController = new AbortController()
    abortRef.current = abortController

    async function loadMedia() {
      setMediaLoading(true)
      setLoadingPhase('Downloading footage...')
      setLoadProgress(0)

      try {
        const result = await loadRawFootage(
          jobId,
          (progress: MediaLoadProgress) => {
            setLoadProgress(progress.percent)
          },
          abortController.signal,
        )

        if (abortController.signal.aborted) return

        setMediaBlob(result.blob)
        setMediaMetadata(result.metadata)
        setMediaUrl(result.url)
        setLoadingPhase('Building project...')
        setMediaLoading(false)
      } catch (err) {
        if (abortController.signal.aborted) return
        const msg = err instanceof Error ? err.message : String(err)
        setMediaError(`Failed to load footage: ${msg}`)
        setMediaLoading(false)
      }
    }

    loadMedia()

    return () => {
      abortController.abort()
      if (mediaUrl) releaseMediaUrl(mediaUrl)
    }
  }, [engineReady, webCodecsSupported, rawFootageUrl, jobId]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Phase 3: Build project once media is loaded ───────────────────────────
  useEffect(() => {
    if (!mediaBlob || !mediaMetadata) return

    try {
      const result = buildProject(clips, mediaBlob, mediaMetadata)
      setProject(result.project)
      setLoadingPhase('')
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setMediaError(`Failed to build project: ${msg}`)
    }
  }, [mediaBlob, mediaMetadata]) // Only on initial build — not on clip changes

  // ── Rebuild project when clips change (after initial build) ───────────────
  useEffect(() => {
    if (!project || !mediaBlob || !mediaMetadata) return

    // Skip if clips reference is the same (no change)
    if (prevClipsRef.current === clips) return
    prevClipsRef.current = clips

    try {
      const result = rebuildProject(project, clips)
      setProject(result.project)
    } catch (err) {
      console.warn('[useEditorEngine] Rebuild failed:', err)
      // Don't set error — keep the old project and let user keep editing
    }
  }, [clips]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Compute derived state ─────────────────────────────────────────────────

  const loading = !engineReady || mediaLoading || (engineReady && webCodecsSupported && !project && !mediaError)

  const errorMsg = useMemo(() => {
    if (engineError && !engineError.recoverable) return engineError.message
    if (mediaError) return mediaError
    return null
  }, [engineError, mediaError])

  return {
    project,
    loading,
    loadingPhase,
    loadProgress,
    engineError: errorMsg,
    webCodecsSupported,
    ready: !!project && engineReady,
  }
}
