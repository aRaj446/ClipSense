import { useEffect, useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Video, Clapperboard,
  Upload, AlertCircle, Play, Youtube, Instagram, Music2, Twitter,
  Sparkles, Trophy, Film, ArrowRight,
} from 'lucide-react'
import { useProjectFetch } from '../hooks/useProjectFetch'
import VideoCard from '../components/VideoCard'
import Button from '../components/Button'
import Card from '../components/Card'
import LoadingSpinner from '../components/LoadingSpinner'
import { Project } from '../types/project'
import { TrailerJob, SmartTrailerJob } from '../types/analysis'
import { trailerService } from '../services/trailerService'
import { smartTrailerService } from '../services/smartTrailerService'
import type { ReactNode } from 'react'

const PLATFORM_META: Record<string, { label: string; icon: ReactNode; color: string; accent: string }> = {
  youtube:   { label: 'YouTube',   icon: <Youtube   size={12} />, color: 'text-red-400 bg-red-500/10 border-red-500/20',   accent: '#F87171' },
  instagram: { label: 'Instagram', icon: <Instagram size={12} />, color: 'text-pink-400 bg-pink-500/10 border-pink-500/20', accent: '#F472B6' },
  tiktok:    { label: 'TikTok',    icon: <Music2    size={12} />, color: 'text-teal-400 bg-teal-500/10 border-teal-500/20', accent: '#2DD4BF' },
  twitter:   { label: 'Twitter/X', icon: <Twitter   size={12} />, color: 'text-sky-400 bg-sky-500/10 border-sky-500/20',   accent: '#60A5FA' },
}

const PLATFORMS = ['youtube', 'instagram', 'tiktok', 'twitter']

// ── Animated counter ──────────────────────────────────────────────────────────

function AnimatedNumber({ target }: { target: number }) {
  const [display, setDisplay] = useState(0)
  const raf = useRef<number>(0)
  useEffect(() => {
    const start = performance.now()
    const duration = 900
    function step(now: number) {
      const t    = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - t, 4)
      setDisplay(Math.round(ease * target))
      if (t < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target])
  return <>{display}</>
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, icon, accentColor, delay = 0 }: {
  label: string; value: number; icon: ReactNode; accentColor: string; delay?: number
}) {
  const [hovered, setHovered] = useState(false)
  return (
    <div
      className="relative rounded-2xl p-5 flex items-center gap-4 border overflow-hidden cursor-default animate-fade-in"
      style={{
        background: 'linear-gradient(145deg, #13131F 0%, #1A1A2E 100%)',
        borderColor: hovered ? accentColor + '50' : '#252538',
        boxShadow: hovered ? `0 8px 32px 0 ${accentColor}18, 0 0 0 1px ${accentColor}20` : '0 2px 20px 0 #00000050',
        transition: 'border-color 0.25s, box-shadow 0.25s, transform 0.2s',
        transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
        animationDelay: `${delay}ms`,
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Shimmer sweep on hover */}
      {hovered && (
        <div className="absolute inset-0 pointer-events-none overflow-hidden rounded-2xl">
          <div className="absolute inset-y-0 w-1/3 animate-shimmer-slide"
            style={{ background: `linear-gradient(90deg, transparent, ${accentColor}08, transparent)` }} />
        </div>
      )}
      {/* Accent bottom line */}
      <div className="absolute bottom-0 left-0 h-0.5 rounded-full transition-all duration-500"
        style={{ width: hovered ? '100%' : '0%', background: `linear-gradient(90deg, ${accentColor}, transparent)` }} />

      <div className="p-3 rounded-xl shrink-0"
        style={{ background: `${accentColor}18`, border: `1px solid ${accentColor}25` }}>
        {icon}
      </div>
      <div>
        <p className="text-3xl font-bold tracking-tight" style={{ color: '#F0EDE8' }}>
          <AnimatedNumber target={value} />
        </p>
        <p className="text-sm mt-0.5" style={{ color: '#A8A4B8' }}>{label}</p>
      </div>
    </div>
  )
}

// ── Trailer card ──────────────────────────────────────────────────────────────

function TrailerCard({ job, winnerMap }: {
  job: TrailerJob | SmartTrailerJob
  winnerMap: Record<string, string>
}) {
  const [hovered, setHovered] = useState(false)
  const isSmart  = !('project_id' in job)
  const meta     = job.platform ? PLATFORM_META[job.platform] : null
  const isWinner = !isSmart && winnerMap[(job as TrailerJob).project_id] === job.id
  const videoUrl = isSmart
    ? smartTrailerService.trailerUrl(job.output_url!)
    : trailerService.trailerUrl((job as TrailerJob).output_url!)

  return (
    <div
      className="rounded-2xl overflow-hidden animate-fade-in"
      style={{
        background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
        border: `1px solid ${isWinner ? '#D4A84350' : hovered ? '#D4A84328' : '#252538'}`,
        boxShadow: isWinner ? '0 0 28px 0 #D4A84320' : hovered ? '0 8px 36px 0 #00000065' : '0 2px 20px 0 #00000045',
        transition: 'border-color 0.25s, box-shadow 0.25s, transform 0.2s',
        transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Video / placeholder */}
      <div className="relative w-full aspect-video bg-black">
        {job.output_url ? (
          <video className="w-full h-full object-contain" src={videoUrl}
            controls={hovered} preload="metadata" />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Clapperboard size={28} style={{ color: '#363654' }} />
          </div>
        )}
        {/* Hover overlay */}
        {job.output_url && !hovered && (
          <div className="absolute inset-0 flex items-center justify-center"
            style={{ background: 'linear-gradient(to top, #0C0C14cc, transparent 60%)' }}>
            <div className="w-12 h-12 rounded-full flex items-center justify-center"
              style={{ background: '#D4A84322', border: '1.5px solid #D4A84350', backdropFilter: 'blur(4px)' }}>
              <Play size={18} fill="#D4A843" style={{ color: '#D4A843', marginLeft: 2 }} />
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-2.5 flex items-center gap-2 flex-wrap"
        style={{ borderTop: '1px solid #1E1E30' }}>
        {isSmart ? (
          <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border"
            style={{ color: '#D4A843', background: '#D4A84312', borderColor: '#D4A84328' }}>
            <Sparkles size={10} /> Smart
          </span>
        ) : meta ? (
          <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${meta.color}`}>
            {meta.icon} {meta.label}
          </span>
        ) : null}
        {isWinner && (
          <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full font-medium"
            style={{ background: '#D4A84318', color: '#E8C56A', border: '1px solid #D4A84330' }}>
            <Trophy size={10} /> Winner
          </span>
        )}
        {job.output_url && (
          <a href={videoUrl} download onClick={e => e.stopPropagation()}
            className="flex items-center gap-1 text-xs ml-auto transition-opacity hover:opacity-70"
            style={{ color: '#D4A843' }}>
            <Play size={10} /> Download
          </a>
        )}
      </div>
    </div>
  )
}

// ── Hero section ──────────────────────────────────────────────────────────────

function Hero({ totalTrailers, totalProjects }: { totalTrailers: number; totalProjects: number }) {
  return (
    <div className="relative rounded-3xl overflow-hidden animate-fade-in"
      style={{ minHeight: 280, border: '1px solid #2A2A40', boxShadow: '0 8px 60px 0 #00000080' }}>

      {/* ── Full gradient background ── */}
      <div className="absolute inset-0"
        style={{
          background: 'linear-gradient(135deg, #0C0C14 0%, #14102A 30%, #1A1230 55%, #0E1420 80%, #0C0C14 100%)',
        }} />

      {/* Mesh colour blobs */}
      <div className="absolute inset-0 pointer-events-none">
        {/* Gold top-left */}
        <div className="absolute -top-20 -left-20 w-96 h-96 rounded-full animate-spin-slow"
          style={{ background: 'radial-gradient(circle, #D4A84328 0%, transparent 65%)', filter: 'blur(40px)' }} />
        {/* Violet bottom-right */}
        <div className="absolute -bottom-24 -right-16 w-[28rem] h-[28rem] rounded-full animate-float"
          style={{ background: 'radial-gradient(circle, #8B7CF622 0%, transparent 65%)', filter: 'blur(48px)', animationDelay: '2s' }} />
        {/* Teal mid */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-80 h-40 rounded-full"
          style={{ background: 'radial-gradient(ellipse, #2DD4BF0A 0%, transparent 70%)', filter: 'blur(32px)' }} />
      </div>

      {/* Subtle grid overlay */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }} />

      {/* ── Content ── */}
      <div className="relative z-10 flex flex-col sm:flex-row sm:items-center gap-8 px-10 py-12">
        <div className="flex-1">

          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full mb-5"
            style={{ background: 'rgba(212,168,67,0.10)', border: '1px solid rgba(212,168,67,0.25)', backdropFilter: 'blur(8px)' }}>
            <Film size={13} style={{ color: '#D4A843' }} />
            <span className="text-xs font-semibold tracking-widest uppercase" style={{ color: '#E8C56A' }}>
              ClipSense Studio
            </span>
          </div>

          {/* Main heading */}
          <h1
            className="font-extrabold leading-tight mb-3 bg-clip-text text-transparent"
            style={{
              fontSize: 'clamp(2rem, 4vw, 3.25rem)',
              backgroundImage: 'linear-gradient(120deg, #F5E6B8 0%, #E8C56A 25%, #D4A843 50%, #A78BFA 80%, #8B7CF6 100%)',
              backgroundSize: '200% 200%',
              animation: 'gradient-shift 6s ease infinite',
            }}
          >
            Welcome back
          </h1>

          {/* Sub-tagline */}
          <p className="text-base leading-relaxed max-w-lg" style={{ color: '#A8A4B8' }}>
            {totalProjects > 0
              ? <>
                  <span style={{ color: '#E8C56A', fontWeight: 600 }}>{totalProjects}</span> project{totalProjects !== 1 ? 's' : ''} &nbsp;·&nbsp;
                  <span style={{ color: '#8B7CF6', fontWeight: 600 }}>{totalTrailers}</span> trailer{totalTrailers !== 1 ? 's' : ''} generated
                </>
              : 'Upload your first video and let AI craft your perfect trailer.'}
          </p>
        </div>

        {/* CTA */}
        <div className="flex flex-col gap-3 shrink-0">
          <Button icon={<Upload size={15} />} onClick={() => window.location.href = '/upload'}
            className="px-6 py-2.5">
            Upload Video
          </Button>
          <p className="text-xs text-center" style={{ color: '#5C5A72' }}>AI-powered trailer generation</p>
        </div>
      </div>

      {/* Bottom shimmer line */}
      <div className="absolute bottom-0 left-0 right-0 h-px"
        style={{ background: 'linear-gradient(90deg, transparent, #D4A84340, #8B7CF630, transparent)' }} />
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const navigate = useNavigate()
  const { projects, loading } = useProjectFetch()
  const [allTrailers,      setAllTrailers]      = useState<TrailerJob[]>([])
  const [allSmartTrailers, setAllSmartTrailers] = useState<SmartTrailerJob[]>([])
  const [activeTab,        setActiveTab]        = useState<string>('all')

  useEffect(() => {
    trailerService.listAllTrailers().then(t => setAllTrailers(t)).catch(() => {})
    smartTrailerService.listJobs().then(j => setAllSmartTrailers(j.filter(j => j.status === 'done'))).catch(() => {})
  }, [])

  const winnerMap = useMemo(() => {
    const map: Record<string, string> = {}
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith('winner:')) {
        const jobId = localStorage.getItem(key)
        if (jobId) map[key.slice(7)] = jobId
      }
    }
    return map
  }, [allTrailers])

  const filteredStandard = activeTab === 'all' ? allTrailers : allTrailers.filter(j => j.platform === activeTab)
  const filteredSmart    = activeTab === 'all' ? allSmartTrailers : []
  const totalTrailers    = allTrailers.length + allSmartTrailers.length

  const stats = [
    { label: 'Total Projects',     value: projects.length, icon: <FolderOpen    size={20} style={{ color: '#D4A843' }} />, accentColor: '#D4A843' },
    { label: 'Videos Uploaded',    value: projects.length, icon: <Video         size={20} style={{ color: '#8B7CF6' }} />, accentColor: '#8B7CF6' },
    { label: 'Trailers Generated', value: totalTrailers,   icon: <Clapperboard  size={20} style={{ color: '#2DD4BF' }} />, accentColor: '#2DD4BF' },
  ]

  const tabs = ['all', ...PLATFORMS]

  return (
    <div className="max-w-7xl mx-auto space-y-8">

      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <Hero totalTrailers={totalTrailers} totalProjects={projects.length} />

      {/* ── Stats ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map((s, i) => <StatCard key={s.label} {...s} delay={i * 80} />)}
      </div>

      {/* ── Trailers ─────────────────────────────────────────────────────── */}
      {totalTrailers > 0 && (
        <div className="animate-fade-in" style={{ animationDelay: '200ms' }}>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: '#F0EDE8' }}>
              <Clapperboard size={16} style={{ color: '#D4A843' }} /> Trailers
            </h2>
            <button onClick={() => navigate('/trailers')}
              className="flex items-center gap-1 text-xs transition-all hover:gap-2"
              style={{ color: '#D4A843' }}>
              View all <ArrowRight size={12} />
            </button>
          </div>

          {/* Platform tabs */}
          <div className="flex gap-2 flex-wrap mb-5">
            {tabs.map(tab => {
              const meta   = tab === 'all' ? null : PLATFORM_META[tab]
              const count  = tab === 'all' ? totalTrailers : allTrailers.filter(j => j.platform === tab).length
              const active = activeTab === tab
              return (
                <button key={tab} onClick={() => setActiveTab(tab)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-medium border transition-all duration-200"
                  style={active ? {
                    background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)',
                    borderColor: '#D4A84338',
                    color: '#E8C56A',
                    boxShadow: '0 0 12px 0 #D4A84318',
                  } : {
                    background: 'transparent',
                    borderColor: '#252538',
                    color: '#5C5A72',
                  }}>
                  {meta?.icon}
                  {meta?.label ?? 'All'}
                  <span className="ml-1 text-xs opacity-50">({count})</span>
                </button>
              )
            })}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredStandard.slice(0, 6).map((job, i) => (
              <div key={job.id} style={{ animationDelay: `${i * 60}ms` }}>
                <TrailerCard job={job} winnerMap={winnerMap} />
              </div>
            ))}
            {filteredSmart.slice(0, Math.max(0, 6 - filteredStandard.length)).map((job, i) => (
              <div key={job.id} style={{ animationDelay: `${(filteredStandard.length + i) * 60}ms` }}>
                <TrailerCard job={job} winnerMap={winnerMap} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Recent Projects ───────────────────────────────────────────────── */}
      <div className="animate-fade-in" style={{ animationDelay: '280ms' }}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2" style={{ color: '#F0EDE8' }}>
            <FolderOpen size={16} style={{ color: '#8B7CF6' }} /> Recent Projects
          </h2>
        </div>

        {loading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size={32} />
          </div>
        ) : projects.length === 0 && allSmartTrailers.length === 0 ? (
          <Card variant="gradient" className="flex flex-col items-center justify-center py-16 text-center">
            <div className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4 animate-float"
              style={{ background: 'linear-gradient(135deg,#D4A84312,#8B7CF610)', border: '1px solid #D4A84320' }}>
              <AlertCircle size={28} style={{ color: '#5C5A72' }} />
            </div>
            <p className="font-medium" style={{ color: '#F0EDE8' }}>No projects yet</p>
            <p className="text-sm mt-1 mb-6" style={{ color: '#5C5A72' }}>Upload your first video to get started</p>
            <Button icon={<Upload size={16} />} onClick={() => navigate('/upload')}>Upload Video</Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((p: Project, i: number) => (
              <div key={p.id} className="animate-fade-in" style={{ animationDelay: `${i * 60}ms` }}>
                <VideoCard project={p} />
              </div>
            ))}
            {allSmartTrailers.map((job, i) => (
              <div key={job.id} className="animate-fade-in" style={{ animationDelay: `${(projects.length + i) * 60}ms` }}>
                <SmartProjectCard job={job} onClick={() => navigate(`/smart-trailer/${job.id}`)} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Smart project card ────────────────────────────────────────────────────────

function SmartProjectCard({ job, onClick }: { job: SmartTrailerJob; onClick: () => void }) {
  const [hovered, setHovered] = useState(false)
  return (
    <div onClick={onClick} className="rounded-2xl p-5 cursor-pointer relative overflow-hidden"
      style={{
        background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
        border: `1px solid ${hovered ? '#D4A84338' : '#252538'}`,
        boxShadow: hovered ? '0 8px 36px 0 #00000065, 0 0 0 1px #D4A84318' : '0 2px 20px 0 #00000045',
        transition: 'border-color 0.25s, box-shadow 0.25s, transform 0.2s',
        transform: hovered ? 'translateY(-3px)' : 'translateY(0)',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Glow orb */}
      {hovered && (
        <div className="absolute -top-8 -right-8 w-32 h-32 rounded-full pointer-events-none"
          style={{ background: 'radial-gradient(circle, #D4A84314 0%, transparent 70%)', filter: 'blur(16px)' }} />
      )}
      <div className="relative z-10">
        <div className="flex items-start justify-between mb-4">
          <div className="p-2.5 rounded-xl"
            style={{ background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)', border: '1px solid #D4A84325' }}>
            <Sparkles size={18} style={{ color: '#D4A843' }} />
          </div>
          <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium"
            style={{ background: '#D4A84312', color: '#D4A843', border: '1px solid #D4A84328' }}>
            <Sparkles size={9} /> Smart
          </span>
        </div>
        <h3 className="font-medium truncate mb-1" style={{ color: '#F0EDE8' }} title={job.raw_footage_name}>
          {job.raw_footage_name}
        </h3>
        <p className="text-xs mb-4" style={{ color: '#5C5A72' }}>
          {new Date(job.created_at).toLocaleDateString()}
        </p>
        <div className="flex items-center gap-3 text-xs" style={{ color: '#A8A4B8' }}>
          {job.editing_plan && (
            <span className="flex items-center gap-1">
              <Clapperboard size={11} />
              {job.editing_plan.clips.length} clips · {Math.round(job.editing_plan.target_duration)}s
            </span>
          )}
          <span className="flex items-center gap-1 ml-auto" style={{ color: '#D4A843' }}>
            View <ArrowRight size={11} />
          </span>
        </div>
      </div>
    </div>
  )
}
