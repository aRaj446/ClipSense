import { useEffect, useState, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  FolderOpen, Video, Clapperboard,
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
  tiktok:    { label: 'TikTok',    icon: <Music2 size={12} />,    color: 'text-accent-teal bg-teal-500/10 border-teal-500/20' },
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
  accentColor: string
  delay?: number
}

function StatCard({ label, value, icon, iconBg, accentColor, delay = 0 }: StatCardProps) {
  return (
    <div
      className="rounded-2xl p-5 flex items-center gap-4 border transition-all duration-200
        hover:-translate-y-0.5 animate-fade-in"
      style={{
        background: 'linear-gradient(145deg, #13131F 0%, #1A1A2E 100%)',
        borderColor: '#252538',
        boxShadow: '0 2px 20px 0 #00000050',
        animationDelay: `${delay}ms`,
      }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = accentColor + '40')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = '#252538')}
    >
      <div className="p-3 rounded-xl shrink-0" style={{ background: iconBg }}>
        {icon}
      </div>
      <div>
        <p className="text-2xl font-bold" style={{ color: '#F0EDE8' }}>
          {typeof value === 'number' ? <AnimatedNumber target={value} /> : value}
        </p>
        <p className="text-sm" style={{ color: '#A8A4B8' }}>{label}</p>
      </div>
    </div>
  )
}

// ── Trailer card ──────────────────────────────────────────────────────────────

function TrailerCard({ job, winnerMap }: {
  job: TrailerJob | SmartTrailerJob
  winnerMap: Record<string, string>
}) {
  const isSmart = !('project_id' in job)
  const score = job.clip_score ?? 0
  const scoreColor = score >= 0.75 ? '#4ADE80' : score >= 0.5 ? '#F59E0B' : '#F87171'
  const meta = job.platform ? PLATFORM_META[job.platform] : null
  const isWinner = !isSmart && winnerMap[(job as TrailerJob).project_id] === job.id
  const videoUrl = isSmart
    ? smartTrailerService.trailerUrl(job.output_url!)
    : trailerService.trailerUrl((job as TrailerJob).output_url!)

  return (
    <div
      className="rounded-2xl overflow-hidden transition-all duration-200 hover:-translate-y-0.5"
      style={{
        background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
        border: `1px solid ${isWinner ? '#D4A84350' : '#252538'}`,
        boxShadow: isWinner ? '0 0 24px 0 #D4A84318' : '0 2px 20px 0 #00000045',
      }}
    >
      {job.output_url ? (
        <video controls className="w-full aspect-video object-contain bg-black" src={videoUrl} />
      ) : (
        <div className="w-full aspect-video bg-black flex items-center justify-center">
          <Clapperboard size={28} className="text-ink-faint/40" />
        </div>
      )}
      <div className="p-3 flex items-center gap-2 flex-wrap">
        {isSmart ? (
          <span className="flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border"
            style={{ color: '#D4A843', background: '#D4A84312', borderColor: '#D4A84328' }}>
            <Sparkles size={11} /> Smart
          </span>
        ) : meta ? (
          <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full border ${meta.color}`}>
            {meta.icon}{meta.label}
          </span>
        ) : null}
        {isWinner && (
          <span className="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full font-medium"
            style={{ background: '#D4A84318', color: '#E8C56A', border: '1px solid #D4A84330' }}>
            <Trophy size={10} /> Winner
          </span>
        )}
        {job.clip_score !== null && (
          <span className="flex items-center gap-1 text-xs font-medium" style={{ color: scoreColor }}>
            <Star size={11} fill="currentColor" />
            {Math.round(score * 100)}%
          </span>
        )}
        {job.output_url && (
          <a href={videoUrl} download
            className="flex items-center gap-1 text-xs ml-auto transition-opacity hover:opacity-70"
            style={{ color: '#D4A843' }}>
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
    { label: 'Total Projects',     value: projects.length, icon: <FolderOpen   size={20} style={{ color: '#D4A843' }} />, iconBg: 'linear-gradient(135deg,#D4A84320,#D4A84308)', accentColor: '#D4A843' },
    { label: 'Videos Uploaded',    value: projects.length, icon: <Video        size={20} style={{ color: '#8B7CF6' }} />, iconBg: 'linear-gradient(135deg,#8B7CF620,#8B7CF608)', accentColor: '#8B7CF6' },
    { label: 'Trailers Generated', value: totalTrailers,   icon: <Clapperboard size={20} style={{ color: '#2DD4BF' }} />, iconBg: 'linear-gradient(135deg,#2DD4BF20,#2DD4BF08)', accentColor: '#2DD4BF' },
  ]

  const tabs = ['all', ...PLATFORMS]

  return (
    <div className="max-w-7xl mx-auto space-y-8">

      {/* ── Hero header ──────────────────────────────────────────────────── */}
      <div
        className="rounded-2xl p-6 flex items-center justify-between gap-4 animate-fade-in"
        style={{
          background: 'linear-gradient(135deg, #13131F 0%, #1A1A2E 60%, #13131F 100%)',
          border: '1px solid #252538',
          boxShadow: '0 0 60px 0 #D4A84308',
        }}
      >
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles size={13} style={{ color: '#D4A843' }} />
            <span className="text-xs font-medium tracking-widest uppercase" style={{ color: '#5C5A72' }}>
              AI Marketing Platform
            </span>
          </div>
          <h1
            className="text-3xl font-bold bg-clip-text text-transparent"
            style={{ backgroundImage: 'linear-gradient(135deg, #F0EDE8 0%, #A8A4B8 100%)' }}
          >
            Dashboard
          </h1>
          <p className="text-sm mt-1" style={{ color: '#A8A4B8' }}>
            Analyse audience feedback and generate optimised trailers.
          </p>
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
            <h2 className="text-lg font-semibold" style={{ color: '#F0EDE8' }}>Trailers</h2>
            <button onClick={() => navigate('/trailers')}
              className="text-xs transition-opacity hover:opacity-70"
              style={{ color: '#D4A843' }}>
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
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-medium border transition-all duration-150"
                  style={active ? {
                    background: 'linear-gradient(135deg,#D4A84318,#8B7CF610)',
                    borderColor: '#D4A84330',
                    color: '#E8C56A',
                  } : {
                    background: 'transparent',
                    borderColor: '#252538',
                    color: '#5C5A72',
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
        <h2 className="text-lg font-semibold mb-4" style={{ color: '#F0EDE8' }}>Recent Projects</h2>
        {loading ? (
          <div className="flex justify-center py-16">
            <LoadingSpinner size={32} />
          </div>
        ) : projects.length === 0 && allSmartTrailers.length === 0 ? (
          <Card variant="gradient" className="flex flex-col items-center justify-center py-16 text-center">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
              style={{ background: 'linear-gradient(135deg,#D4A84312,#8B7CF610)', border: '1px solid #D4A84320' }}
            >
              <AlertCircle size={28} style={{ color: '#5C5A72' }} />
            </div>
            <p className="font-medium" style={{ color: '#F0EDE8' }}>No projects yet</p>
            <p className="text-sm mt-1 mb-6" style={{ color: '#5C5A72' }}>Upload your first video to get started</p>
            <Button icon={<Upload size={16} />} onClick={() => navigate('/upload')}>Upload Video</Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {projects.map((p: Project) => <VideoCard key={p.id} project={p} />)}
            {allSmartTrailers.map(job => (
              <div
                key={job.id}
                onClick={() => navigate(`/smart-trailer/${job.id}`)}
                className="rounded-2xl p-6 cursor-pointer transition-all duration-200 hover:-translate-y-0.5"
                style={{
                  background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
                  border: '1px solid #252538',
                  boxShadow: '0 2px 20px 0 #00000045',
                }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = '#D4A84335')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = '#252538')}
              >
                <div className="flex items-start justify-between mb-3">
                  <div
                    className="p-2 rounded-xl"
                    style={{ background: 'linear-gradient(135deg,#D4A84318,#8B7CF610)' }}
                  >
                    <Sparkles size={20} style={{ color: '#D4A843' }} />
                  </div>
                  <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full font-medium"
                    style={{ background: '#D4A84312', color: '#D4A843', border: '1px solid #D4A84328' }}>
                    <Sparkles size={10} /> Smart
                  </span>
                </div>
                <h3 className="font-medium truncate mb-1" style={{ color: '#F0EDE8' }} title={job.raw_footage_name}>
                  {job.raw_footage_name}
                </h3>
                <p className="text-xs mb-4" style={{ color: '#5C5A72' }}>{new Date(job.created_at).toLocaleDateString()}</p>
                <div className="flex items-center gap-4 text-xs" style={{ color: '#A8A4B8' }}>
                  {job.editing_plan && (
                    <span className="flex items-center gap-1">
                      <Clapperboard size={12} />
                      {job.editing_plan.clips.length} clips · {Math.round(job.editing_plan.target_duration)}s
                    </span>
                  )}
                  {job.clip_score != null && (
                    <span className="flex items-center gap-1 ml-auto"
                      style={{ color: job.clip_score >= 0.75 ? '#4ADE80' : job.clip_score >= 0.5 ? '#F59E0B' : '#F87171' }}>
                      <Star size={12} fill="currentColor" />
                      {Math.round(job.clip_score * 100)}%
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
