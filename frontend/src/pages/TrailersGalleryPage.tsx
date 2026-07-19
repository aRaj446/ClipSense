import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Clapperboard, Sparkles, Film, ChevronRight } from 'lucide-react'
import { Project } from '../types/project'
import { projectService } from '../services/projectService'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'
import SmartTrailerPanel from '../components/SmartTrailerPanel'
import ProjectDetailsEmbed from '../components/ProjectDetailsEmbed'
import SmartDetailsPage from './SmartDetailsPage'

export default function TrailersGalleryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const mode       = (searchParams.get('mode') as 'standard' | 'smart') ?? 'standard'
  const projectId  = searchParams.get('project') ?? null
  const smartJobId = searchParams.get('smart')   ?? null

  const [projects, setProjects] = useState<Project[]>([])
  const [loading,  setLoading]  = useState(true)

  useEffect(() => {
    projectService.listProjects()
      .then(setProjects)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function setMode(m: 'standard' | 'smart') {
    if (m === 'standard') {
      setSearchParams(projectId ? { project: projectId } : {})
    } else {
      setSearchParams(smartJobId ? { mode: 'smart', smart: smartJobId } : { mode: 'smart' })
    }
  }

  function selectProject(id: string) { setSearchParams({ project: id }) }
  function clearProject()            { setSearchParams({}) }
  function selectSmartJob(id: string){ setSearchParams({ mode: 'smart', smart: id }) }
  function clearSmartJob()           { setSearchParams({ mode: 'smart' }) }

  return (
    <div className="max-w-7xl mx-auto space-y-6">

      <div>
        <h1 className="text-2xl font-bold text-slate-100">Video Generation</h1>
        <p className="text-slate-400 text-sm mt-1">Generate trailers from your uploaded projects.</p>
      </div>

      {/* Standard / Smart toggle */}
      <div className="flex gap-1 p-1 bg-surface-card border border-surface-border rounded-lg w-fit">
        <button
          onClick={() => setMode('standard')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            mode === 'standard' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Clapperboard size={13} /> Standard
        </button>
        <button
          onClick={() => setMode('smart')}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
            mode === 'smart' ? 'bg-surface text-slate-100 shadow-sm' : 'text-slate-500 hover:text-slate-300'
          }`}
        >
          <Sparkles size={13} /> Smart Trailer
        </button>
      </div>

      {/* ── Standard ── */}
      {mode === 'standard' && (
        projectId ? (
          <div className="space-y-4">
            <button
              onClick={clearProject}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-100 transition-colors"
            >
              <ChevronRight size={14} className="rotate-180" /> Back to projects
            </button>
            <ProjectDetailsEmbed key={projectId} projectId={projectId} onBack={clearProject} />
          </div>
        ) : (
          loading ? (
            <div className="flex justify-center py-16"><LoadingSpinner size={32} /></div>
          ) : projects.length === 0 ? (
            <Card className="flex flex-col items-center py-16 text-center">
              <Film size={40} className="text-slate-600 mb-4" />
              <p className="text-slate-300 font-medium">No projects yet</p>
              <p className="text-slate-500 text-sm mt-1">Upload a video first to generate trailers.</p>
            </Card>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {projects.map(p => (
                <button
                  key={p.id}
                  onClick={() => selectProject(p.id)}
                  className="bg-surface-card border border-surface-border rounded-xl p-4 text-left hover:border-primary/40 hover:bg-surface transition-colors group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2.5 bg-primary/10 rounded-lg shrink-0">
                      <Film size={18} className="text-primary" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-slate-100 font-medium text-sm truncate group-hover:text-primary transition-colors">
                        {p.filename}
                      </p>
                      <p className="text-slate-500 text-xs mt-0.5 capitalize">{p.status}</p>
                    </div>
                    <ChevronRight size={16} className="text-slate-600 group-hover:text-primary transition-colors shrink-0" />
                  </div>
                </button>
              ))}
            </div>
          )
        )
      )}

      {/* ── Smart ── */}
      {mode === 'smart' && (
        smartJobId ? (
          <div className="space-y-4">
            <button
              onClick={clearSmartJob}
              className="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-100 transition-colors"
            >
              <ChevronRight size={14} className="rotate-180" /> Back to smart trailers
            </button>
            <SmartDetailsPage key={smartJobId} jobId={smartJobId} onBack={clearSmartJob} />
          </div>
        ) : (
          <SmartTrailerPanel onSelectJob={selectSmartJob} />
        )
      )}

    </div>
  )
}
