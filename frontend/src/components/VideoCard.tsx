import { useNavigate } from 'react-router-dom'
import { Film, Clock, HardDrive } from 'lucide-react'
import { Project } from '../types/project'
import { formatDuration, formatFileSize, formatDate } from '../utils/format'

interface Props {
  project: Project
}

const statusColors: Record<string, { text: string; bg: string; border: string }> = {
  uploaded:   { text: 'text-blue-400',   bg: 'bg-blue-500/10',   border: 'border-blue-500/20' },
  processing: { text: 'text-amber-400',  bg: 'bg-amber-500/10',  border: 'border-amber-500/20' },
  done:       { text: 'text-green-400',  bg: 'bg-green-500/10',  border: 'border-green-500/20' },
}

export default function VideoCard({ project }: Props) {
  const navigate = useNavigate()
  const sc = statusColors[project.status] ?? statusColors.uploaded

  return (
    <div
      onClick={() => navigate(`/project/${project.id}`)}
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
          <Film size={20} className="text-primary" />
        </div>
        <span className={`text-xs px-2 py-1 rounded-full font-medium capitalize border ${sc.text} ${sc.bg} ${sc.border}`}>
          {project.status}
        </span>
      </div>

      <h3 className="font-medium text-slate-100 truncate mb-1" title={project.filename}>
        {project.filename}
      </h3>
      <p className="text-xs text-slate-500 mb-4">{formatDate(project.upload_time)}</p>

      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <Clock size={12} className="text-slate-500" />
          {formatDuration(project.duration)}
        </span>
        <span className="flex items-center gap-1">
          <HardDrive size={12} className="text-slate-500" />
          {formatFileSize(project.size)}
        </span>
      </div>
    </div>
  )
}
