import { useEffect, useState, useMemo, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BarChart2, ChevronRight, ChevronDown, Film, Database,
  Loader2, Clapperboard, ExternalLink, Play, RefreshCw,
  CheckCircle2, AlertCircle, Clock, Zap,
} from 'lucide-react'
import { Project } from '../types/project'
import { StoredDataset, SmartTrailerJob } from '../types/analysis'
import { projectService, ProjectAnalyticsStatus } from '../services/projectService'
import { feedbackService } from '../services/feedbackService'
import { smartTrailerService } from '../services/smartTrailerService'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'
import AnalyticsDashboard from '../components/AnalyticsDashboard'
import SmartAnalyticsDashboard from '../components/SmartAnalyticsDashboard'
import TrailerStrategyPanel from '../components/TrailerStrategyPanel'

interface ProjectWithDatasets extends Project {
  datasets: StoredDataset[]
  loadingDatasets: boolean
  analyticsStatus: ProjectAnalyticsStatus | null
  loadingStatus: boolean
}

type RunState = 'idle' | 'running' | 'done' | 'error'

// ── Sentiment summary pill ────────────────────────────────────────────────────
function SentimentPills({ status }: { status: ProjectAnalyticsStatus }) {
  const total = status.positive + status.negative + status.neutral
  if (!total) return null
  return (
    <div className="flex gap-1 mt-1.5 flex-wrap">
      {status.positive > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: '#4ADE8018', color: '#4ADE80', border: '1px solid #4ADE8030' }}>
          +{status.positive}
        </span>
      )}
      {status.negative > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: '#F8717118', color: '#F87171', border: '1px solid #F8717130' }}>
          -{status.negative}
        </span>
      )}
      {status.neutral > 0 && (
        <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
          style={{ background: '#A8A4B818', color: '#A8A4B8', border: '1px solid #A8A4B830' }}>
          ~{status.neutral}
        </span>
      )}
    </div>
  )
}

// ── Analytics status badge ────────────────────────────────────────────────────
function StatusBadge({ status }: { status: ProjectAnalyticsStatus | null }) {
  if (!status) return null
  if (!status.dataset_id) {
    return (
      <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full"
        style={{ background: '#5C5A7218', color: '#5C5A72', border: '1px solid #5C5A7230' }}>
        <Database size={8} /> No dataset
      </span>
    )
  }
  if (status.has_analytics) {
    return (
      <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full"
        style={{ background: '#4ADE8018', color: '#4ADE80', border: '1px solid #4ADE8030' }}>
        <CheckCircle2 size={8} /> Analysed
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-full"
      style={{ background: '#FCD34D18', color: '#FCD34D', border: '1px solid #FCD34D30' }}>
      <Clock size={8} /> Pending
    </span>
  )
}

export default function AnalyticsPage() {
  const [searchParams]                        = useSearchParams()
  const [projects, setProjects]               = useState<ProjectWithDatasets[]>([])
  const [loading, setLoading]                 = useState(true)
  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [selectedDataset, setSelectedDataset] = useState<{
    projectId: string; datasetId: string; datasetName: string | null
  } | null>(null)

  const [sidebarMode, setSidebarMode]           = useState<'standard' | 'smart'>('standard')
  const [smartJobs, setSmartJobs]               = useState<SmartTrailerJob[]>([])
  const [selectedSmartJob, setSelectedSmartJob] = useState<SmartTrailerJob | null>(null)

  // Per-project run state
  const [runStates, setRunStates] = useState<Record<string, RunState>>({})
  const [runErrors, setRunErrors] = useState<Record<string, string>>({})

  // SenseCap redirect error
  const [sensecapError, setSensecapError] = useState<string | null>(null)

  const qProject = searchParams.get('project')
  const qDataset  = searchParams.get('dataset')

  useEffect(() => {
    smartTrailerService.listJobs()
      .then(jobs => setSmartJobs(jobs.filter(j => j.status === 'done' && !j.project_id)))
      .catch(() => {})
  }, [])

  useEffect(() => {
    projectService.listProjects()
      .then(projs => {
        const withMeta = projs.map(p => ({
          ...p,
          datasets: [],
          loadingDatasets: false,
          analyticsStatus: null,
          loadingStatus: false,
        }))
        setProjects(withMeta)
        if (qProject) setExpandedProject(qProject)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Load analytics status for Phase 2 projects (those with dataset_id)
  useEffect(() => {
    projects.forEach(p => {
      if (!p.dataset_id || p.analyticsStatus || p.loadingStatus) return
      setProjects(prev => prev.map(pp =>
        pp.id === p.id ? { ...pp, loadingStatus: true } : pp
      ))
      projectService.getAnalyticsStatus(p.id)
        .then(status => {
          setProjects(prev => prev.map(pp =>
            pp.id === p.id ? { ...pp, analyticsStatus: status, loadingStatus: false } : pp
          ))
        })
        .catch(() => {
          setProjects(prev => prev.map(pp =>
            pp.id === p.id ? { ...pp, loadingStatus: false } : pp
          ))
        })
    })
  }, [projects.length])

  // Expand project and load datasets
  useEffect(() => {
    if (!expandedProject) return
    setProjects(prev => prev.map(p => {
      if (p.id !== expandedProject || p.datasets.length > 0 || p.loadingDatasets) return p
      feedbackService.listDatasets(p.id).then(datasets => {
        setProjects(curr => curr.map(cp =>
          cp.id === p.id ? { ...cp, datasets, loadingDatasets: false } : cp
        ))
        if (qDataset && p.id === qProject) {
          const ds = datasets.find(d => d.id === qDataset)
          if (ds) setSelectedDataset({ projectId: p.id, datasetId: ds.id, datasetName: ds.name })
        }
      }).catch(() => {
        setProjects(curr => curr.map(cp =>
          cp.id === p.id ? { ...cp, loadingDatasets: false } : cp
        ))
      })
      return { ...p, loadingDatasets: true }
    }))
  }, [expandedProject])

  const handleRunAnalytics = useCallback(async (projectId: string, force = false) => {
    setRunStates(s => ({ ...s, [projectId]: 'running' }))
    setRunErrors(e => { const n = { ...e }; delete n[projectId]; return n })
    setSensecapError(null)
    try {
      const status = await projectService.runAnalytics(projectId, force)
      setProjects(prev => prev.map(p =>
        p.id === projectId ? { ...p, analyticsStatus: status } : p
      ))
      setRunStates(s => ({ ...s, [projectId]: 'done' }))
    } catch (err: any) {
      const msg = err?.response?.data?.detail ?? 'Analytics failed. Please try again.'
      setRunErrors(e => ({ ...e, [projectId]: msg }))
      setRunStates(s => ({ ...s, [projectId]: 'error' }))
    }
  }, [])

  const handleOpenSensecap = useCallback((url: string | null) => {
    setSensecapError(null)
    if (!url) {
      setSensecapError('SenseCap URL is not configured. Run analytics first.')
      return
    }
    try {
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch {
      setSensecapError('Could not open SenseCap. Check that it is running at the configured URL.')
    }
  }, [])

  const selectedProject = useMemo(
    () => projects.find(p => p.id === selectedDataset?.projectId),
    [projects, selectedDataset]
  )

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <LoadingSpinner size={36} />
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto flex gap-6 h-[calc(100vh-80px)]">

      {/* ── Left panel ───────────────────────────────────────────────────── */}
      <div className="w-80 shrink-0 flex flex-col gap-2 overflow-y-auto pr-1">
        <div className="flex items-center gap-2 mb-1 px-1">
          <BarChart2 size={16} className="text-primary" />
          <h1 className="text-sm font-semibold text-slate-100">Analytics</h1>
          <span className="ml-auto text-xs text-slate-500">
            {projects.length} project{projects.length !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Standard / Smart toggle */}
        <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-lg mb-1">
          <button
            onClick={() => setSidebarMode('standard')}
            className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
              sidebarMode === 'standard' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Clapperboard size={11} /> Standard
          </button>
          <button
            onClick={() => setSidebarMode('smart')}
            className={`flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-colors ${
              sidebarMode === 'smart' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <Clapperboard size={11} /> Smart
          </button>
        </div>

        {/* Standard: project → dataset tree */}
        {sidebarMode === 'standard' && (
          projects.length === 0 ? (
            <Card className="py-10 text-center">
              <Film size={32} className="text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">No projects yet.</p>
              <p className="text-slate-600 text-xs mt-1">Upload a project to get started.</p>
            </Card>
          ) : (
            projects.map(project => {
              const isExpanded  = expandedProject === project.id
              const runState    = runStates[project.id] ?? 'idle'
              const runError    = runErrors[project.id]
              const status      = project.analyticsStatus
              const displayName = project.name || project.filename

              return (
                <div key={project.id} className="rounded-lg border border-surface-border overflow-hidden">
                  {/* Project header row */}
                  <button
                    onClick={() => setExpandedProject(isExpanded ? null : project.id)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 bg-surface hover:bg-surface-card transition-colors text-left"
                  >
                    {isExpanded
                      ? <ChevronDown size={13} className="text-slate-400 shrink-0" />
                      : <ChevronRight size={13} className="text-slate-400 shrink-0" />
                    }
                    <Film size={13} className="text-primary shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-200 text-xs font-medium truncate">{displayName}</p>
                      {project.name && project.filename !== project.name && (
                        <p className="text-slate-600 text-[10px] truncate">{project.filename}</p>
                      )}
                    </div>
                    {project.loadingStatus
                      ? <Loader2 size={11} className="text-slate-500 animate-spin shrink-0" />
                      : <StatusBadge status={status} />
                    }
                  </button>

                  {/* Expanded: analytics actions + dataset list */}
                  {isExpanded && (
                    <div className="border-t border-surface-border bg-surface/50">

                      {/* Phase 2 project: analytics controls */}
                      {project.dataset_id && (
                        <div className="px-3 py-2.5 border-b border-surface-border/50 space-y-2">

                          {/* Sentiment summary */}
                          {status?.has_analytics && <SentimentPills status={status} />}
                          {status?.top_topic && (
                            <p className="text-[10px] text-slate-500 truncate">
                              Top topic: <span className="text-slate-400">{status.top_topic}</span>
                            </p>
                          )}

                          {/* Run error */}
                          {runError && (
                            <div className="flex items-start gap-1.5 text-[10px] rounded-md px-2 py-1.5"
                              style={{ background: '#F8717112', color: '#F87171', border: '1px solid #F8717130' }}>
                              <AlertCircle size={10} className="shrink-0 mt-0.5" />
                              <span>{runError}</span>
                            </div>
                          )}

                          {/* Action buttons */}
                          <div className="flex gap-1.5">
                            {!status?.has_analytics ? (
                              <button
                                onClick={() => handleRunAnalytics(project.id)}
                                disabled={runState === 'running'}
                                className="flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-all disabled:opacity-50"
                                style={{
                                  background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)',
                                  border: '1px solid #D4A84335',
                                  color: '#D4A843',
                                }}
                              >
                                {runState === 'running'
                                  ? <><Loader2 size={11} className="animate-spin" /> Running…</>
                                  : <><Play size={11} /> Run Analysis</>
                                }
                              </button>
                            ) : (
                              <>
                                <button
                                  onClick={() => handleRunAnalytics(project.id, true)}
                                  disabled={runState === 'running'}
                                  className="flex items-center gap-1 px-2 py-1.5 rounded-md text-[10px] font-medium transition-all disabled:opacity-50 text-slate-400 hover:text-slate-200 border border-surface-border hover:border-slate-500"
                                  title="Recompute analytics"
                                >
                                  {runState === 'running'
                                    ? <Loader2 size={10} className="animate-spin" />
                                    : <RefreshCw size={10} />
                                  }
                                </button>
                                <button
                                  onClick={() => handleOpenSensecap(status.sensecap_url)}
                                  className="flex items-center gap-1.5 flex-1 justify-center px-2 py-1.5 rounded-md text-xs font-medium transition-all hover:opacity-80"
                                  style={{
                                    background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)',
                                    border: '1px solid #D4A84335',
                                    color: '#D4A843',
                                  }}
                                >
                                  <Zap size={11} /> Open in Sensecap
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Dataset list */}
                      {project.loadingDatasets ? (
                        <div className="flex items-center justify-center py-4">
                          <Loader2 size={14} className="text-slate-500 animate-spin" />
                        </div>
                      ) : project.datasets.length === 0 ? (
                        <p className="text-xs text-slate-600 px-4 py-3 italic">No datasets uploaded.</p>
                      ) : (
                        project.datasets.map(ds => {
                          const isSelected = selectedDataset?.datasetId === ds.id
                          return (
                            <button
                              key={ds.id}
                              onClick={() => setSelectedDataset({
                                projectId: project.id,
                                datasetId: ds.id,
                                datasetName: ds.name,
                              })}
                              className={`w-full flex items-center gap-2 px-4 py-2 text-left transition-colors border-b border-surface-border/50 last:border-0 ${
                                isSelected
                                  ? 'bg-primary/10 text-primary'
                                  : 'text-slate-400 hover:bg-surface-card hover:text-slate-200'
                              }`}
                            >
                              <Database size={11} className="shrink-0" />
                              <span className="text-xs truncate flex-1">
                                {ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`}
                              </span>
                              <span className="text-xs opacity-60 shrink-0">{ds.segment_count}s</span>
                            </button>
                          )
                        })
                      )}
                    </div>
                  )}
                </div>
              )
            })
          )
        )}

        {/* Smart: flat list */}
        {sidebarMode === 'smart' && (
          smartJobs.length === 0 ? (
            <Card className="py-10 text-center">
              <Clapperboard size={32} className="text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 text-sm">No smart trailers yet.</p>
            </Card>
          ) : (
            smartJobs.map(job => {
              const isSelected = selectedSmartJob?.id === job.id
              return (
                <button
                  key={job.id}
                  onClick={() => setSelectedSmartJob(job)}
                  className={`w-full flex items-center gap-2 px-3 py-2.5 rounded-lg border transition-colors text-left ${
                    isSelected
                      ? 'bg-primary/10 border-primary/30 text-primary'
                      : 'bg-surface border-surface-border text-slate-400 hover:bg-surface-card hover:text-slate-200'
                  }`}
                >
                  <Clapperboard size={13} className={isSelected ? 'text-primary shrink-0' : 'text-slate-500 shrink-0'} />
                  <div className="flex-1 min-w-0">
                    <p className={`text-xs font-medium truncate ${isSelected ? 'text-primary' : 'text-slate-200'}`}>
                      {job.raw_footage_name}
                    </p>
                    <p className="text-[10px] truncate mt-0.5" style={{ color: isSelected ? '#D4A84399' : '#5C5A72' }}>
                      {job.comments_name}
                    </p>
                  </div>
                  {job.clip_score != null && (
                    <span className="text-[10px] text-yellow-400 font-mono shrink-0">
                      {Math.round(job.clip_score * 100)}%
                    </span>
                  )}
                </button>
              )
            })
          )
        )}
      </div>

      {/* ── Right panel ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">

        {/* SenseCap global error banner */}
        {sensecapError && (
          <div className="flex items-center gap-2 mb-4 px-4 py-3 rounded-xl text-sm"
            style={{ background: '#F8717112', color: '#F87171', border: '1px solid #F8717130' }}>
            <AlertCircle size={15} className="shrink-0" />
            <span className="flex-1">{sensecapError}</span>
            <button onClick={() => setSensecapError(null)} className="text-xs opacity-60 hover:opacity-100">✕</button>
          </div>
        )}

        {sidebarMode === 'smart' ? (
          selectedSmartJob ? (
            <SmartAnalyticsDashboard job={selectedSmartJob} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4">
              <Clapperboard size={48} className="text-slate-700" />
              <p className="text-slate-400 font-medium">Select a smart trailer to view analytics</p>
              <p className="text-slate-600 text-sm">Click any smart trailer on the left.</p>
            </div>
          )
        ) : (
          !selectedDataset ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4">
              <BarChart2 size={48} className="text-slate-700" />
              <p className="text-slate-400 font-medium">Select a dataset to view analytics</p>
              <p className="text-slate-600 text-sm">
                Expand a project on the left, run analysis, then click a dataset.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Breadcrumb + Sensecap button */}
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Film size={12} className="text-primary" />
                <span className="text-slate-300 font-medium truncate">
                  {selectedProject?.name || selectedProject?.filename || selectedDataset.projectId.slice(0, 8)}
                </span>
                <ChevronRight size={11} />
                <Database size={11} className="text-primary" />
                <span className="text-slate-300 font-medium truncate">
                  {selectedDataset.datasetName ?? `Dataset ${selectedDataset.datasetId.slice(0, 8)}…`}
                </span>
                <button
                  onClick={() => {
                    setSensecapError(null)
                    const url = feedbackService.sensecapDeepLink(
                      selectedDataset.datasetId,
                      selectedDataset.datasetName ?? undefined,
                    )
                    try {
                      window.open(url, '_blank', 'noopener,noreferrer')
                    } catch {
                      setSensecapError(
                        'Could not open SenseCap. Ensure it is running at ' +
                        (import.meta.env.VITE_SENSECAP_URL ?? 'http://localhost:8501')
                      )
                    }
                  }}
                  className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-80"
                  style={{
                    background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)',
                    border: '1px solid #D4A84335',
                    color: '#D4A843',
                  }}
                >
                  <ExternalLink size={11} /> Open in Sensecap
                </button>
              </div>

              <AnalyticsDashboard
                datasetId={selectedDataset.datasetId}
                datasetName={selectedDataset.datasetName}
              />
              <TrailerStrategyPanel datasetId={selectedDataset.datasetId} />
            </div>
          )
        )}
      </div>

    </div>
  )
}
