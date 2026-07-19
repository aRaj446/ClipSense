import { useNavigate } from 'react-router-dom'
import { Film, Clock, HardDrive } from 'lucide-react'
import { Project } from '../types/project'
import { formatDuration, formatFileSize, formatDate } from '../utils/format'

interface Props {
  project: Project
}

const statusColors: Record<string, { text: string; bg: string; border: string }> = {
  uploaded:   { text: '#8B7CF6', bg: 'rgba(139,124,246,0.10)', border: 'rgba(139,124,246,0.22)' },
  processing: { text: '#F59E0B', bg: 'rgba(245,158,11,0.10)',  border: 'rgba(245,158,11,0.22)' },
  done:       { text: '#4ADE80', bg: 'rgba(74,222,128,0.10)',  border: 'rgba(74,222,128,0.22)' },
}

export default function VideoCard({ project }: Props) {
  const navigate = useNavigate()
  const sc = statusColors[project.status] ?? statusColors.uploaded

  return (
    <div
      onClick={() => navigate(`/project/${project.id}`)}
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
          <Film size={20} style={{ color: '#D4A843' }} />
        </div>
        <span
          className="text-xs px-2 py-1 rounded-full font-medium capitalize"
          style={{ color: sc.text, background: sc.bg, border: `1px solid ${sc.border}` }}
        >
          {project.status}
        </span>
      </div>

      <h3 className="font-medium truncate mb-1" style={{ color: '#F0EDE8' }} title={project.filename}>
        {project.filename}
      </h3>
      <p className="text-xs mb-4" style={{ color: '#5C5A72' }}>{formatDate(project.upload_time)}</p>

      <div className="flex items-center gap-4 text-xs" style={{ color: '#A8A4B8' }}>
        <span className="flex items-center gap-1">
          <Clock size={12} style={{ color: '#5C5A72' }} />
          {formatDuration(project.duration)}
        </span>
        <span className="flex items-center gap-1">
          <HardDrive size={12} style={{ color: '#5C5A72' }} />
          {formatFileSize(project.size)}
        </span>
      </div>
    </div>
  )
}
