import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Clapperboard, Film, ChevronRight, Zap } from 'lucide-react'
import { Project } from '../types/project'
import { projectService } from '../services/projectService'
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
    if (m === 'standard') setSearchParams(projectId ? { project: projectId } : {})
    else setSearchParams(smartJobId ? { mode: 'smart', smart: smartJobId } : { mode: 'smart' })
  }

  function selectProject(id: string) { setSearchParams({ project: id }) }
  function clearProject()            { setSearchParams({}) }
  function selectSmartJob(id: string){ setSearchParams({ mode: 'smart', smart: id }) }
  function clearSmartJob()           { setSearchParams({ mode: 'smart' }) }

  return (
    <div className="max-w-7xl mx-auto space-y-0">

      {/* ── Page Hero ── */}
      <div className="relative rounded-3xl overflow-hidden mb-8"
        style={{ border: '1px solid #2A2A40', boxShadow: '0 8px 60px 0 #00000080' }}>

        {/* bg */}
        <div className="absolute inset-0"
          style={{ background: 'linear-gradient(135deg,#0C0C14 0%,#14102A 35%,#1A1230 60%,#0E1420 85%,#0C0C14 100%)' }} />

        {/* blobs */}
        <div className="absolute -top-40 -left-40 w-[40rem] h-[40rem] rounded-full pointer-events-none animate-spin-slow"
          style={{ background: 'radial-gradient(circle,#D4A84345 0%,transparent 65%)', filter: 'blur(70px)' }} />
        <div className="absolute -bottom-40 -right-32 w-[44rem] h-[44rem] rounded-full pointer-events-none animate-float"
          style={{ background: 'radial-gradient(circle,#8B7CF638 0%,transparent 65%)', filter: 'blur(80px)', animationDelay: '2s' }} />
        <div className="absolute top-0 right-1/4 w-56 h-56 rounded-full pointer-events-none animate-spin-slow"
          style={{ background: 'radial-gradient(circle,#2DD4BF18 0%,transparent 70%)', filter: 'blur(50px)', animationDirection: 'reverse' }} />

        {/* grid */}
        <div className="absolute inset-0 pointer-events-none opacity-[0.025]"
          style={{ backgroundImage: 'linear-gradient(#fff 1px,transparent 1px),linear-gradient(90deg,#fff 1px,transparent 1px)', backgroundSize: '48px 48px' }} />

        {/* shimmer bottom */}
        <div className="absolute bottom-0 left-0 right-0 h-px"
          style={{ background: 'linear-gradient(90deg,transparent,#D4A84350,#8B7CF640,transparent)' }} />

        {/* particles */}
        {[...Array(8)].map((_, i) => (
          <div key={i} className="absolute rounded-full pointer-events-none animate-float"
            style={{
              width:  [5,7,4,9,5,6,4,8][i],
              height: [5,7,4,9,5,6,4,8][i],
              top:    ['15%','70%','35%','85%','20%','60%','45%','10%'][i],
              left:   ['8%','80%','90%','15%','50%','35%','65%','75%'][i],
              background: ['#D4A843','#8B7CF6','#2DD4BF','#D4A843','#8B7CF6','#2DD4BF','#D4A843','#8B7CF6'][i],
              opacity: 0.4,
              filter: 'blur(1px)',
              animationDelay: `${i * 0.6}s`,
              animationDuration: `${3 + i * 0.4}s`,
            }} />
        ))}

        <div className="relative z-10 px-10 py-16">
          {/* badge */}
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full mb-7"
            style={{ background: 'rgba(212,168,67,0.10)', border: '1px solid rgba(212,168,67,0.30)', backdropFilter: 'blur(8px)' }}>
            <Zap size={13} style={{ color: '#D4A843' }} />
            <span className="text-xs font-bold tracking-widest uppercase" style={{ color: '#E8C56A' }}>ClipSense Studio</span>
          </div>

          {/* giant heading */}
          <h1 className="font-black leading-none mb-5 bg-clip-text text-transparent"
            style={{
              fontSize: 'clamp(3.5rem,9vw,7rem)',
              backgroundImage: 'linear-gradient(120deg,#F5E6B8 0%,#E8C56A 20%,#D4A843 45%,#A78BFA 75%,#8B7CF6 100%)',
              backgroundSize: '200% 200%',
              animation: 'gradient-shift 5s ease infinite',
              letterSpacing: '-0.03em',
              lineHeight: 0.9,
            }}>
            Video<br />Generation
          </h1>

          <p className="text-lg max-w-2xl mb-8" style={{ color: '#A8A4B8' }}>
            Generate cinematic trailers driven by sentiment analytics and beat-aligned scene selection.
          </p>

          {/* mode toggle — big pill style */}
          <div className="flex gap-3">
            <button onClick={() => setMode('standard')}
              className="flex items-center gap-2.5 px-6 py-3 rounded-2xl font-semibold text-sm transition-all duration-200"
              style={mode === 'standard'
                ? { background: 'linear-gradient(135deg,#D4A843,#E8C56A)', color: '#0C0C14', boxShadow: '0 0 24px 0 #D4A84350' }
                : { background: 'rgba(255,255,255,0.05)', border: '1px solid #2A2A40', color: '#A8A4B8' }}>
              <Clapperboard size={16} /> Standard Trailer
            </button>
            <button onClick={() => setMode('smart')}
              className="flex items-center gap-2.5 px-6 py-3 rounded-2xl font-semibold text-sm transition-all duration-200"
              style={mode === 'smart'
                ? { background: 'linear-gradient(135deg,#8B7CF6,#A78BFA)', color: '#fff', boxShadow: '0 0 24px 0 #8B7CF650' }
                : { background: 'rgba(255,255,255,0.05)', border: '1px solid #2A2A40', color: '#A8A4B8' }}>
              <Clapperboard size={16} /> Smart Trailer
            </button>
          </div>
        </div>
      </div>

      {/* ── Standard ── */}
      {mode === 'standard' && (
        projectId ? (
          <div className="space-y-4">
            <button onClick={clearProject}
              className="flex items-center gap-1.5 text-sm transition-colors"
              style={{ color: '#A8A4B8' }}>
              <ChevronRight size={14} className="rotate-180" /> Back to projects
            </button>
            <ProjectDetailsEmbed key={projectId} projectId={projectId} onBack={clearProject} />
          </div>
        ) : loading ? (
          <div className="flex justify-center py-16"><LoadingSpinner size={32} /></div>
        ) : projects.length === 0 ? (
          <div className="flex flex-col items-center py-20 rounded-3xl"
            style={{ background: 'linear-gradient(145deg,#13131F,#1A1A2E)', border: '1px solid #252538' }}>
            <div className="w-20 h-20 rounded-3xl flex items-center justify-center mb-5 animate-float"
              style={{ background: 'linear-gradient(135deg,#D4A84314,#8B7CF614)', border: '1px solid #D4A84325' }}>
              <Film size={32} style={{ color: '#5C5A72' }} />
            </div>
            <p className="text-lg font-semibold mb-2" style={{ color: '#F0EDE8' }}>No projects yet</p>
            <p className="text-sm" style={{ color: '#5C5A72' }}>Upload a video first to generate trailers.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((p, i) => (
              <button key={p.id} onClick={() => selectProject(p.id)}
                className="group rounded-2xl p-5 text-left transition-all duration-200 animate-fade-in"
                style={{
                  background: 'linear-gradient(145deg,#13131F,#1A1A2E)',
                  border: '1px solid #252538',
                  animationDelay: `${i * 60}ms`,
                }}>
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 transition-all duration-200 group-hover:scale-110"
                    style={{ background: 'linear-gradient(135deg,#D4A84318,#8B7CF614)', border: '1px solid #D4A84325' }}>
                    <Film size={20} style={{ color: '#D4A843' }} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-sm truncate transition-colors duration-200"
                      style={{ color: '#F0EDE8' }}>
                      {p.filename}
                    </p>
                    <p className="text-xs mt-0.5 capitalize" style={{ color: '#5C5A72' }}>{p.status}</p>
                  </div>
                  <ChevronRight size={16} className="shrink-0 transition-all duration-200 group-hover:translate-x-1"
                    style={{ color: '#5C5A72' }} />
                </div>
              </button>
            ))}
          </div>
        )
      )}

      {/* ── Smart ── */}
      {mode === 'smart' && (
        smartJobId ? (
          <div className="space-y-4">
            <button onClick={clearSmartJob}
              className="flex items-center gap-1.5 text-sm transition-colors"
              style={{ color: '#A8A4B8' }}>
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
