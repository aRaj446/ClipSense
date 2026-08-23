/**
 * useEngine — React hook for SenseScrub engine lifecycle
 *
 * Initializes the OpenReel-powered engine on mount and disposes on unmount.
 * Provides engine status, error state, and access to the engine instance.
 */

import { useEffect, useState, useRef } from 'react'
import type { EngineStatus, EngineError } from './types'
import { SenseScrubEngine, initializeEngine, disposeEngine, getEngine } from './engine-core'

export interface UseEngineResult {
  /** Current engine lifecycle status */
  status: EngineStatus
  /** Error details if initialization failed */
  error: EngineError | null
  /** Whether the engine is fully ready for rendering */
  ready: boolean
  /** Whether WebCodecs is supported (determines canvas vs video fallback) */
  webCodecsSupported: boolean
  /** The engine instance (null until ready) */
  engine: SenseScrubEngine | null
}

/**
 * Hook to manage engine lifecycle. Call once at the top of the editor component tree.
 *
 * @example
 * ```tsx
 * function EditorReady() {
 *   const { ready, error, engine } = useEngine()
 *   if (!ready) return <LoadingScreen />
 *   if (error && !error.recoverable) return <ErrorScreen />
 *   // Use engine for preview...
 * }
 * ```
 */
export function useEngine(): UseEngineResult {
  const [status, setStatus] = useState<EngineStatus>('idle')
  const [error, setError] = useState<EngineError | null>(null)
  const [engine, setEngine] = useState<SenseScrubEngine | null>(null)
  const initRef = useRef(false)

  useEffect(() => {
    // Prevent double-init in React strict mode
    if (initRef.current) return
    initRef.current = true

    let disposed = false

    async function boot() {
      setStatus('initializing')

      try {
        const instance = await initializeEngine()

        if (disposed) {
          // Component unmounted during init
          disposeEngine()
          return
        }

        setEngine(instance)
        setStatus(instance.status)
        setError(instance.error)
      } catch (err) {
        if (disposed) return
        const message = err instanceof Error ? err.message : String(err)
        setError({
          code: 'INIT_FAILED',
          message,
          recoverable: false,
        })
        setStatus('error')
      }
    }

    boot()

    return () => {
      disposed = true
      disposeEngine()
    }
  }, [])

  return {
    status,
    error,
    ready: status === 'ready',
    webCodecsSupported: engine?.webCodecsSupported ?? false,
    engine,
  }
}
