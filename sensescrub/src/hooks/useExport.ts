import { useState, useRef, useCallback } from 'react'
import { startRender, subscribeRenderProgress, videoUrl } from '../api/editor'

export type ExportStatus = 'idle' | 'starting' | 'rendering' | 'done' | 'failed'

export interface StepEntry {
  key: string
  label: string
  status: 'pending' | 'active' | 'done' | 'failed'
  percent: number
}

export interface ExportState {
  status: ExportStatus
  percent: number
  message: string
  steps: StepEntry[]
  outputUrl: string | null
  error: string | null
}

const IDLE: ExportState = {
  status: 'idle', percent: 0, message: '', steps: [], outputUrl: null, error: null,
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export function useExport(jobId: string, onNewVideoUrl?: (url: string) => void) {
  const [state, setState] = useState<ExportState>(IDLE)
  const esRef    = useRef<EventSource | null>(null)
  const newJobId = useRef<string | null>(null)

  const _cleanup = () => {
    if (esRef.current) { esRef.current.close(); esRef.current = null }
  }

  const startExport = useCallback(async () => {
    _cleanup()
    setState({ ...IDLE, status: 'starting', message: 'Submitting render job…' })

    let renderResp: Awaited<ReturnType<typeof startRender>>
    try {
      renderResp = await startRender(jobId)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to start render'
      setState(s => ({ ...s, status: 'failed', error: msg }))
      return
    }

    newJobId.current = renderResp.new_job_id
    setState(s => ({ ...s, status: 'rendering', message: 'Render queued…' }))

    esRef.current = subscribeRenderProgress(
      jobId,
      renderResp.new_job_id,
      (data) => {
        const steps = (data.steps ?? []) as StepEntry[]
        if (data.stage === 'done') {
          _cleanup()
          const pollPath =
            renderResp.job_type === 'smart'
              ? `/smart-trailer/job/${renderResp.new_job_id}`
              : `/trailer-job/${renderResp.new_job_id}`
          // Fetch the new job to get its output_url and update the player
          if (onNewVideoUrl) {
            fetch(`${API_BASE}${pollPath}`)
              .then(r => r.json())
              .then(data => {
                const url: string | null = data.output_url ?? null
                if (url) onNewVideoUrl(videoUrl(url))
              })
              .catch(() => { /* silent */ })
          }
          setState(s => ({
            ...s,
            status: 'done',
            percent: 100,
            message: 'Export complete',
            steps,
            outputUrl: pollPath,
            error: null,
          }))
        } else if (data.stage === 'failed') {
          _cleanup()
          setState(s => ({
            ...s,
            status: 'failed',
            percent: data.percent,
            message: data.message,
            steps,
            error: data.message || 'Render failed',
          }))
        } else {
          setState(s => ({
            ...s,
            status: 'rendering',
            percent: data.percent,
            message: data.message,
            steps,
          }))
        }
      },
      () => {
        // SSE connection error — only fail if not already done
        setState(s => {
          if (s.status === 'done') return s
          return { ...s, status: 'failed', error: 'Lost connection to render server' }
        })
      },
    )
  }, [jobId])

  const retry = useCallback(() => {
    _cleanup()
    setState(IDLE)
    startExport()
  }, [startExport])

  const dismiss = useCallback(() => {
    _cleanup()
    setState(IDLE)
  }, [])

  return { exportState: state, startExport, retry, dismiss }
}
