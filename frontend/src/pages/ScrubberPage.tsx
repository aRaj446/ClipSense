import { useState, useEffect } from 'react'
import { ChevronRight, ChevronDown, Film, Loader2, ExternalLink, Scissors } from 'lucide-react'
import { Project } from '../types/project'
import { projectService, ProjectTrailerListItem } from '../services/projectService'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'

const SENSESCRUB_URL = import.meta.env.VITE_SENSESCRUB_URL ?? 'http://localhost:5176'

interface ProjectRow extends Project {
  trailers: ProjectTrailerListItem[]
  loading: boolean
  loaded: boolean
}

function statusBadge(status: ProjectTrailerListItem['status']) {
  const styles: Record<typeof status, string> = {
    done:       'bg-green-500/15 text-green-400',
    processing: 'bg-yellow-500/15 text-yellow-400',
    pending:    'bg-slate-500/15 text-slate-400',
    failed:     'bg-red-500/15 text-red-400',
  }
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${styles[status]}`}>
      {status}
    </span>
  )
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'text-green-400'
  if (score >= 0.4) return 'text-yellow-400'
  return 'text-red-400'
}

export default function ScrubberPage() {
  const [projects, setProjects] = useState<ProjectRow[]>([])
  const [loading, setLoading]   = useState(true)
  const [expanded, setExpanded] = useState<string | null>(null)

  useEffect(() => {
    projectService.listProjects()
      .then(ps => setProjects(ps.map(p => ({ ...p, trailers: [], loading: false, loaded: false }))))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function toggle(projectId: string) {
    setExpanded(prev => {
      const next = prev === projectId ? null : projectId
      if (next) loadTrailers(next)
      return next
    })
  }

  function loadTrailers(projectId: string) {
    setProjects(prev => prev.map(p => {
      if (p.id !== projectId || p.loaded || p.loading) return p
      projectService.listTrailers(projectId)
        .then(trailers => setProjects(curr => curr.map(cp =>
          cp.id === projectId ? { ...cp, trailers, loading: false, loaded: true } : cp
        )))
        .catch(() => setProjects(curr => curr.map(cp =>
          cp.id === projectId ? { ...cp, loading: false, loaded: true } : cp
        )))
      return { ...p, loading: true }
    }))
  }

  function openInSenseScrub(projectId: string, jobId: string, _genNumber: number) {
    const apiBase = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    window.open(
      `${SENSESCRUB_URL}/#/clipsense?projectId=${projectId}&jobId=${jobId}&apiBase=${encodeURIComponent(apiBase)}`,
      '_blank', 'noopener,noreferrer',
    )
  }

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <LoadingSpinner size={36} />
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6 py-6">
      <div className="flex items-center gap-2">
        <Scissors size={18} className="text-primary" />
        <h1 className="text-base font-semibold text-slate-100">SenseScrub Launcher</h1>
        <span className="text-xs text-slate-500 ml-1">Open a generated trailer in SenseScrub for fine-grained editing</span>
      </div>

      {projects.length === 0 ? (
        <Card className="py-16 text-center">
          <Film size={36} className="text-slate-600 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">No projects yet.</p>
        </Card>
      ) : (
        projects.map(project => {
          const isOpen = expanded === project.id
          return (
            <Card key={project.id} className="p-0 overflow-hidden">
              <button
                onClick={() => toggle(project.id)}
                className="w-full flex items-center gap-3 px-4 py-3 hover:bg-surface-card transition-colors text-left"
              >
                {isOpen
                  ? <ChevronDown size={14} className="text-slate-400 shrink-0" />
                  : <ChevronRight size={14} className="text-slate-400 shrink-0" />
                }
                <Film size={14} className="text-primary shrink-0" />
                <span className="text-slate-200 text-sm font-medium flex-1 truncate">
                  {project.name ?? project.filename}
                </span>
                <span className="text-xs text-slate-600 shrink-0">{project.filename}</span>
              </button>

              {isOpen && (
                <div className="border-t border-surface-border">
                  {project.loading ? (
                    <div className="flex items-center justify-center py-6">
                      <Loader2 size={16} className="text-slate-500 animate-spin" />
                    </div>
                  ) : project.trailers.length === 0 ? (
                    <p className="text-xs text-slate-600 italic px-5 py-4">No trailers generated for this project.</p>
                  ) : (
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-500 border-b border-surface-border/60">
                          <th className="text-left px-5 py-2 font-medium">#</th>
                          <th className="text-left px-3 py-2 font-medium">Status</th>
                          <th className="text-left px-3 py-2 font-medium">Date</th>
                          <th className="text-center px-3 py-2 font-medium">Clips</th>
                          <th className="text-center px-3 py-2 font-medium">Score</th>
                          <th className="px-4 py-2" />
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-surface-border/40">
                        {project.trailers.map(t => (
                          <tr key={t.job_id} className="hover:bg-surface-card/50 transition-colors">
                            {/* Generation number + type badges */}
                            <td className="px-5 py-2.5">
                              <div className="flex items-center gap-1.5">
                                <span className="text-slate-400 font-mono text-xs">Gen {t.generation_number}</span>
                                {t.has_creative_direction && (
                                  <span className="px-1 py-0.5 rounded text-[9px] font-medium bg-accent-violet/15 text-accent-violet" title={t.user_prompt ?? undefined}>✦ directed</span>
                                )}
                                {t.fast_mode && (
                                  <span className="px-1 py-0.5 rounded text-[9px] font-medium bg-slate-700 text-slate-400">fast</span>
                                )}
                              </div>
                            </td>
                            <td className="px-3 py-2.5">{statusBadge(t.status)}</td>
                            <td className="px-3 py-2.5 text-slate-500 text-xs">{formatDate(t.created_at)}</td>
                            <td className="px-3 py-2.5 text-center text-slate-400 text-xs">
                              {t.clip_count ?? '—'}
                            </td>
                            <td className="px-3 py-2.5 text-center font-mono text-xs">
                              {t.clip_score != null
                                ? <span className={scoreColor(t.clip_score)}>{Math.round(t.clip_score * 100)}%</span>
                                : <span className="text-slate-600">—</span>
                              }
                            </td>
                            <td className="px-4 py-2.5 text-right">
                              {t.status === 'done' ? (
                                <button
                                  onClick={() => openInSenseScrub(project.id, t.job_id, t.generation_number)}
                                  className="flex items-center gap-1.5 ml-auto px-3 py-1.5 rounded-lg bg-primary/15 text-primary hover:bg-primary/25 transition-colors text-xs font-medium"
                                >
                                  <ExternalLink size={11} />
                                  Open in SenseScrub
                                </button>
                              ) : (
                                <span className="text-slate-700 text-xs">—</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              )}
            </Card>
          )
        })
      )}
    </div>
  )
}
