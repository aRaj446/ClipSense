import { useEffect, useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Video, Clapperboard, TrendingUp,
  Upload, AlertCircle, Play, Youtube, Instagram, Music2, Twitter, Star, Sparkles, Trophy,
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

const PLATFORM_META: Record<string, { label: string; icon: ReactNode; color: string }> = {
  youtube:   { label: 'YouTube',   icon: <Youtube size={12} />,   color: 'text-red-400 bg-red-500/10 border-red-500/20' },
  instagram: { label: 'Instagram', icon: <Instagram size={12} />, color: 'text-pink-400 bg-pink-500/10 border-pink-500/20' },
  tiktok:    { label: 'TikTok',    icon: <Music2 size={12} />,    color: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20' },
  twitter:   { label: 'Twitter/X', icon: <Twitter size={12} />,   color: 'text-sky-400 bg-sky-500/10 border-sky-500/20' },
}

const PLATFORMS = ['youtube', 'instagram', 'tiktok', 'twitter']

// ── Animated counter ──────────────────────────────────────────────────────────

function AnimatedNumber({ target }: { target: number }) {
  const [display, setDisplay] = useState(0)
  const raf = useRef<number>(0)
  useEffect(() => {
    const start = performance.now()
    const duration = 700
    function step(now: number) {
      const t = Math.min((now - start) / duration, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(ease * target))
      if (t < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target])
  return <>{display}</>
}

// ── Stat card ─────────────────────────────────────────────────────────────────

interface StatCardProps {
  label: string
  value: string | number
  icon: ReactNode
  iconBg: string
  placeholder?: boolean
  delay?: number
}

function StatCard({ label, value, icon, iconBg, placeholder, delay = 0 }: StatCardProps) {
  return (
    <Card
      variant="glow"
      animate
      className="flex items-center gap-4"
      style={{ animationDelay: `${delay}ms` } as React.CSSProperties}
    >
      <div className="p-3 rounded-xl shrink-0" style={{ background: iconBg }}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold text-slate-100">
          {placeholder ? (
            <span className="text-slate-500 text-sm font-normal">Coming soon</span>
          ) : typeof value === 'number' ? (
            <AnimatedNumber target={value} />
          ) : value}
        </p>
        <p className="text-sm text-slate-400">{label}</p>
      </div>
    </Card>
  )
}

// ── Trailer card ──────────────────────────────────────────────────────────────

function TrailerCard({ job, winnerMap }: {
  job: TrailerJob | SmartTrailerJob
  winnerMap: Record<string, string>
}) {
  const isSmart = !('project_id' in job)
  const score = job.clip_score ?? 0
  const scoreColor = score >= 0.75 ? 'text-green-400' : score >= 0.5 ? 'text-yellow-400' : 'text-red-400'
  const meta = job.platform ? PLATFORM_META[job.platform] : null
  const isWinner = !isSmart && winnerMap[(job as TrailerJob).project_id] === job.id
  const videoUrl = isSmart
    ? smartTrailerService.trailerUrl(job.output_url!)
    : trailerService.trailerUrl((job as TrailerJob).output_url!)

  return (
    <div
      className="rounded-xl overflow-hidden transition-all duration-200 hover:-translate-y-0.5"
      style={{
        background: 'linear-gradient(145deg, #0E1525, #141E30)',
        border: `2px solid ${isWinner ? '#FACC1560' : '#1C2A3F'}`,
        boxShadow: isWinner ? '0 0 20px 0 #FACC1520' : '0 4px 24px 0 #00000040',
      }}
    >
      {job.output_url ? (
        <video controls className="w-full aspect-video object-contain bg-black" src={videoUrl} />
      ) : (
        <div className="w-full aspect-video bg-black flex items-center justify-center">
          <Clapperboard size={28} className="text-slate-700" />
        </div>
      )}
      <div className="p-3 flex items-center gap-2 flex-wrap">
        {isSmart ? (
          <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border text-primary bg-primary/10 border-primary/20">
            <Sparkles size={11} /> Smart
          </span>
        ) : meta ? (
          <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${meta.color}`}>
            {meta.icon}{meta.label}
          </span>
        ) : null}
        {isWinner && (
          <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full bg-yellow-400/15 text-yellow-400 border border-yellow-400/30 font-medium">
            <Trophy size={10} /> Winner
          </span>
        )}
        {job.clip_score !== null && (
          <span className={`flex items-center gap-1 text-xs font-medium ${scoreColor}`}>
            <Star size={11} fill="currentColor" />
            {Math.round(score * 100)}%
          </span>
        )}
        {job.output_url && (
          <a href={videoUrl} download className="flex items-center gap-1 text-xs text-primary hover:text-primary/80 transition-colors ml-auto">
            <Play size={11} /> Download
          </a>
        )}
      </div>
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
    { label: 'Total Projects',     value: projects.length, icon: <FolderOpen   size={20} className="text-blue-400" />,   iconBg: 'linear-gradient(135deg,#2563EB22,#2563EB0A)' },
    { label: 'Videos Uploaded',    value: projects.length, icon: <Video        size={20} className="text-purple-400" />, iconBg: 'linear-gradient(135deg,#7C3AED22,#7C3AED0A)' },
    { label: 'Trailers Generated', value: totalTrailers,   icon: <Clapperboard size={20} className="text-cyan-400" />,   iconBg: 'linear-gradient(135deg,#06B6D422,#06B6D40A)' },
    { label: 'Optimization Score', value: '—',             icon: <TrendingUp   size={20} className="text-amber-400" />,  iconBg: 'linear-gradient(135deg,#F59E0B22,#F59E0B0A)', placeholder: true },
  ]

  const tabs = ['all', ...PLATFORMS]

  return (
    <div className="max-w-7xl mx-auto space-y-8">

      {/* ── Hero header ──────────────────────────────────────────────────── */}
      <div
        className="rounded-2xl p-6 flex items-center justify-between gap-4 animate-fade-in"
        style={{
          background: 'linear-gradient(135deg, #0E1525 0%, #141E30 60%, #0E1525 100%)',
          border: '1px solid #1C2A3F',
          boxShadow: '0 0 48px 0 #2563EB0A',
        }}
      >
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={13} className="text-primary" />
            <span className="text-xs text-slate-500 font-medium tracking-widest uppercase">AI Marketing Platform</span>
          </div>
          <h1
            className="text-3xl font-bold bg-clip-text text-transparent"
            style={{ backgroundImage: 'linear-gradient(135deg, #e2e8f0 0%, #94a3b8 100%)' }}
          >
            Dashboard
          </h1>
          <p className="text-slate-400 mt-1 text-sm">Analyse audience feedback and generate optimised trailers.</p>
        </div>
        <Button icon={<Upload size={16} />} onClick={() => navigate('/upload')} className="shrink-0">
          Upload Video
        </Button>
      </div>

      {/* ── Stats ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats.map((s, i) => <StatCard key={s.label} {...s} delay={i * 60} />)}
      </div>

      {/* ── Trailers ─────────────────────────────────────────────────────── */}
      {totalTrailers > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-100">Trailers</h2>
            <button onClick={() => navigate('/trailers')} className="text-xs text-primary hover:text-primary/80 transition-colors">
              View all →
            </button>
          </div>

          {/* Platform tabs */}
          <div className="flex gap-2 flex-wrap mb-4">
            {tabs.map(tab => {
              const meta  = tab === 'all' ? null : PLATFORM_META[tab]
              const count = tab === 'all' ? totalTrailers : allTrailers.filter(j => j.platform === tab).length
              const active = activeTab === tab
              return (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all duration-150"
                  style={active ? {
                    background: 'linear-gradient(135deg,#2563EB18,#7C3AED12)',
                    borderColor: '#2563EB30',
                    color: '#3B82F6',
                  } : {
                    background: 'transparent',
                    borderColor: '#1C2A3F',
                    color: '#64748b',
                  }}
                >
                  {meta?.icon}
                  {meta?.label ?? 'All'}
                  <span className="ml-1 text-xs opacity-60">({count})</span>
                </button>
              )
            })}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredStandard.slice(0, 6).map(job => (
              <TrailerCard key={job.id} job={job} winnerMap={winnerMap} />
            ))}
            {filteredSmart.slice(0, Math.max(0, 6 - filteredStandard.length)).map(job => (
              <TrailerCard key={job.id} job={job} winnerMap={winnerMap} />
            ))}
          </div>
        </div>
      )}

      {/* ── Recent Projects ───────────────────────────────────────────────── */}
      <div>
        <h2 className="text-lg font-semibold text-slate-100 mb-4">Recent Projects</h2>
        {loading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size={32} />
          </div>
        ) : projects.length === 0 && allSmartTrailers.length === 0 ? (
          <Card variant="gradient" className="flex flex-col items-center justify-center py-16 text-center">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: 'linear-gradient(135deg,#2563EB14,#7C3AED14)', border: '1px solid #2563EB20' }}
            >
              <AlertCircle size={28} className="text-slate-500" />
            </div>
            <p className="text-slate-300 font-medium">No projects yet</p>
            <p className="text-slate-500 text-sm mt-1 mb-6">Upload your first video to get started</p>
            <Button icon={<Upload size={16} />} onClick={() => navigate('/upload')}>Upload Video</Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((p: Project) => <VideoCard key={p.id} project={p} />)}
            {allSmartTrailers.map(job => (
              <div
                key={job.id}
                onClick={() => navigate(`/smart-trailer/${job.id}`)}
                className="rounded-xl p-6 cursor-pointer transition-all duration-200 group hover:-translate-y-0.5"
                style={{
                  background: 'linear-gradient(145deg, #0E1525, #141E30)',
                  border: '1px solid #1C2A3F',
                  boxShadow: '0 4px 24px 0 #00000040',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#2563EB30')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#1C2A3F')}
              >
                <div className="flex items-start justify-between mb-3">
                  <div
                    className="p-2 rounded-lg transition-all duration-150"
                    style={{ background: 'linear-gradient(135deg,#2563EB18,#7C3AED12)' }}
                  >
                    <Sparkles size={20} className="text-primary" />
                  </div>
                  <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium bg-primary/10 text-primary border border-primary/20">
                    <Sparkles size={10} /> Smart
                  </span>
                </div>
                <h3 className="font-medium text-slate-100 truncate mb-1" title={job.raw_footage_name}>
                  {job.raw_footage_name}
                </h3>
                <p className="text-xs text-slate-500 mb-4">{new Date(job.created_at).toLocaleDateString()}</p>
                <div className="flex items-center gap-4 text-xs text-slate-400">
                  {job.editing_plan && (
                    <span className="flex items-center gap-1">
                      <Clapperboard size={12} />
                      {job.editing_plan.clips.length} clips · {Math.round(job.editing_plan.target_duration)}s
                    </span>
                  )}
                  {job.clip_score != null && (
                    <span className="flex items-center gap-1 ml-auto">
                      <Star size={12} fill="currentColor" className={job.clip_score >= 0.75 ? 'text-green-400' : job.clip_score >= 0.5 ? 'text-yellow-400' : 'text-red-400'} />
                      <span className={job.clip_score >= 0.75 ? 'text-green-400' : job.clip_score >= 0.5 ? 'text-yellow-400' : 'text-red-400'}>
                        {Math.round(job.clip_score * 100)}%
                      </span>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
