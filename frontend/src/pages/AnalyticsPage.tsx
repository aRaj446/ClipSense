import { useEffect, useState, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BarChart2, ChevronRight, ChevronDown, Film, Database,
  Loader2, Clapperboard, ExternalLink,
} from 'lucide-react'
import { Project } from '../types/project'
import { StoredDataset, SmartTrailerJob } from '../types/analysis'
import { projectService } from '../services/projectService'
import { feedbackService } from '../services/feedbackService'
import { smartTrailerService } from '../services/smartTrailerService'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'
import AnalyticsDashboard from '../components/AnalyticsDashboard'
import SmartAnalyticsDashboard from '../components/SmartAnalyticsDashboard'

interface ProjectWithDatasets extends Project {
  datasets: StoredDataset[]
  loadingDatasets: boolean
}

export default function AnalyticsPage() {
  const [searchParams]                        = useSearchParams()
  const [projects, setProjects]               = useState<ProjectWithDatasets[]>([])
  const [loading, setLoading]                 = useState(true)
  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [selectedDataset, setSelectedDataset] = useState<{ projectId: string; datasetId: string; datasetName: string | null } | null>(null)

  const [sidebarMode, setSidebarMode]           = useState<'standard' | 'smart'>('standard')
  const [smartJobs, setSmartJobs]               = useState<SmartTrailerJob[]>([])
  const [selectedSmartJob, setSelectedSmartJob] = useState<SmartTrailerJob | null>(null)

  const qProject = searchParams.get('project')
  const qDataset  = searchParams.get('dataset')

  useEffect(() => {
    smartTrailerService.listJobs()
      .then(jobs => setSmartJobs(jobs.filter(j => j.status === 'done')))
      .catch(() => {})
  }, [])

  useEffect(() => {
    projectService.listProjects()
      .then(projs => {
        setProjects(projs.map(p => ({ ...p, datasets: [], loadingDatasets: false })))
        if (qProject) setExpandedProject(qProject)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

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
      <div className="w-72 shrink-0 flex flex-col gap-2 overflow-y-auto pr-1">
        <div className="flex items-center gap-2 mb-1 px-1">
          <BarChart2 size={16} className="text-primary" />
          <h1 className="text-sm font-semibold text-slate-100">Analytics</h1>
          <span className="ml-auto text-xs text-slate-500">{projects.length} project{projects.length !== 1 ? 's' : ''}</span>
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
            </Card>
          ) : (
            projects.map(project => {
              const isExpanded = expandedProject === project.id
              return (
                <div key={project.id} className="rounded-lg border border-surface-border overflow-hidden">
                  <button
                    onClick={() => setExpandedProject(isExpanded ? null : project.id)}
                    className="w-full flex items-center gap-2 px-3 py-2.5 bg-surface hover:bg-surface-card transition-colors text-left"
                  >
                    {isExpanded
                      ? <ChevronDown size={13} className="text-slate-400 shrink-0" />
                      : <ChevronRight size={13} className="text-slate-400 shrink-0" />
                    }
                    <Film size={13} className="text-primary shrink-0" />
                    <span className="text-slate-200 text-xs font-medium truncate flex-1">{project.filename}</span>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-surface-border bg-surface/50">
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
                              onClick={() => setSelectedDataset({ projectId: project.id, datasetId: ds.id, datasetName: ds.name })}
                              className={`w-full flex items-center gap-2 px-4 py-2 text-left transition-colors border-b border-surface-border/50 last:border-0 ${
                                isSelected ? 'bg-primary/10 text-primary' : 'text-slate-400 hover:bg-surface-card hover:text-slate-200'
                              }`}
                            >
                              <Database size={11} className="shrink-0" />
                              <span className="text-xs truncate flex-1">{ds.name ?? `Dataset ${ds.id.slice(0, 8)}…`}</span>
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

        {/* Smart: flat list — one click selects the job's comments dataset */}
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
                    <span className="text-[10px] text-yellow-400 font-mono shrink-0">{Math.round(job.clip_score * 100)}%</span>
                  )}
                </button>
              )
            })
          )
        )}
      </div>

      {/* ── Right panel ──────────────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto">
        {sidebarMode === 'smart' ? (
          selectedSmartJob ? (
            <SmartAnalyticsDashboard job={selectedSmartJob} />
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4">
              <Clapperboard size={48} className="text-slate-700" />
              <p className="text-slate-400 font-medium">Select a smart trailer's dataset to view analytics</p>
              <p className="text-slate-600 text-sm">Expand a smart trailer on the left and click the comments dataset.</p>
            </div>
          )
        ) : (
          !selectedDataset ? (
            <div className="flex flex-col items-center justify-center h-full text-center gap-4">
              <BarChart2 size={48} className="text-slate-700" />
              <p className="text-slate-400 font-medium">Select a dataset to view analytics</p>
              <p className="text-slate-600 text-sm">Expand a project on the left and click any dataset.</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Film size={12} className="text-primary" />
                <span className="text-slate-300 font-medium truncate">
                  {selectedProject?.filename ?? selectedDataset.projectId.slice(0, 8)}
                </span>
                <ChevronRight size={11} />
                <Database size={11} className="text-primary" />
                <span className="text-slate-300 font-medium truncate">
                  {selectedDataset.datasetName ?? `Dataset ${selectedDataset.datasetId.slice(0, 8)}…`}
                </span>
                <button
                  onClick={() => window.open(
                    feedbackService.sensecapDeepLink(selectedDataset.datasetId, selectedDataset.datasetName ?? undefined),
                    '_blank',
                    'noopener,noreferrer',
                  )}
                  className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-80"
                  style={{ background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)', border: '1px solid #D4A84335', color: '#D4A843' }}
                >
                  <ExternalLink size={11} /> Open in Sensecap
                </button>
              </div>
              <AnalyticsDashboard
                datasetId={selectedDataset.datasetId}
                datasetName={selectedDataset.datasetName}
              />
            </div>
          )
        )}
      </div>

    </div>
  )
}
