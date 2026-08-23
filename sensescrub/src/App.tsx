import { useEffect, useState } from 'react'
import { isAxiosError } from 'axios'
import { getProject, getEditorState } from './api/editor'
import type { Project, EditorJobResponse } from './types'
import ErrorScreen, { ErrorKind } from './components/ErrorScreen'
import EditorReady from './components/EditorReady'
import { Scissors } from 'lucide-react'

// ── UUID validation ───────────────────────────────────────────────────────────

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function isUUID(s: string) {
  return UUID_RE.test(s)
}

// ── URL param extraction ──────────────────────────────────────────────────────

function readParams(): { projectId: string | null; jobId: string | null; genNumber: number | null } {
  const p = new URLSearchParams(window.location.search)
  const gen = p.get('gen')
  return {
    projectId: p.get('project'),
    jobId:     p.get('job'),
    genNumber: gen ? parseInt(gen, 10) || null : null,
  }
}

// ── State machine ─────────────────────────────────────────────────────────────

type AppState =
  | { phase: 'loading' }
  | { phase: 'error'; kind: ErrorKind; detail?: string }
  | { phase: 'ready'; project: Project; editor: EditorJobResponse; generationLabel: string }

// ── Loading spinner ───────────────────────────────────────────────────────────

function LoadingScreen({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4">
      <div className="flex items-center gap-2">
        <Scissors size={18} className="text-primary animate-pulse" />
        <span className="gradient-text text-sm font-bold tracking-wide">SenseScrub</span>
      </div>
      <div className="w-6 h-6 rounded-full border-2 border-surface-border border-t-primary animate-spin" />
      <p className="text-slate-500 text-xs">{message}</p>
    </div>
  )
}

// ── Error classifier ──────────────────────────────────────────────────────────

function classifyError(err: unknown): { kind: ErrorKind; detail?: string } {
  if (isAxiosError(err)) {
    const status = err.response?.status
    if (status === 404) return { kind: 'not-found' }
    if (status === 409) return { kind: 'not-ready' }
    if (!err.response)  return { kind: 'unavailable', detail: err.message }
  }
  const msg = err instanceof Error ? err.message : String(err)
  return { kind: 'unknown', detail: msg }
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const [state, setState] = useState<AppState>({ phase: 'loading' })

  useEffect(() => {
    async function load() {
      const { projectId, jobId, genNumber } = readParams()

      // 1. Presence check
      if (!projectId || !jobId) {
        setState({ phase: 'error', kind: 'missing-params' })
        return
      }

      // 2. Format validation
      if (!isUUID(projectId) || !isUUID(jobId)) {
        setState({ phase: 'error', kind: 'invalid-params',
          detail: `project="${projectId}" job="${jobId}"` })
        return
      }

      // 3. Load project
      let project: Project
      try {
        project = await getProject(projectId)
      } catch (err) {
        const { kind, detail } = classifyError(err)
        setState({ phase: 'error', kind, detail })
        return
      }

      // 4. Load editor state
      let editor: EditorJobResponse
      try {
        editor = await getEditorState(jobId)
      } catch (err) {
        const { kind, detail } = classifyError(err)
        setState({ phase: 'error', kind, detail })
        return
      }

      // 5. Derive generation label
      const genLabel = genNumber != null
        ? `Gen ${genNumber}`
        : `Job ${editor.job_id.slice(0, 8)}`
      const generationLabel = `${genLabel} · ${
        new Date(editor.created_at).toLocaleDateString(undefined, {
          month: 'short', day: 'numeric', year: 'numeric',
        })
      }`

      setState({ phase: 'ready', project, editor, generationLabel })
    }

    load()
  }, [])

  if (state.phase === 'loading') {
    return <LoadingScreen message="Loading editor…" />
  }

  if (state.phase === 'error') {
    return <ErrorScreen kind={state.kind} detail={state.detail} />
  }

  return (
    <EditorReady
      project={state.project}
      editor={state.editor}
      generationLabel={state.generationLabel}
    />
  )
}
