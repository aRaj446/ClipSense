import { useNavigate } from 'react-router-dom'
import { Film, Clock, HardDrive } from 'lucide-react'
import { Project } from '../types/project'
import { formatDuration, formatFileSize, formatDate } from '../utils/format'

interface Props {
  project: Project
}

const statusColors: Record<string, string> = {
  uploaded: 'bg-blue-500/20 text-blue-400',
  processing: 'bg-yellow-500/20 text-yellow-400',
  done: 'bg-green-500/20 text-green-400',
}

export default function VideoCard({ project }: Props) {
  const navigate = useNavigate()

  return (
    <div
      onClick={() => navigate(`/project/${project.id}`)}
      className="bg-surface-card border border-surface-border rounded-xl p-6 cursor-pointer
        hover:border-primary/50 hover:shadow-lg hover:shadow-primary/5 transition-all duration-200 group"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="p-2 bg-primary/10 rounded-lg group-hover:bg-primary/20 transition-colors">
          <Film size={20} className="text-primary" />
        </div>
        <span
          className={`text-xs px-2 py-1 rounded-full font-medium capitalize ${
            statusColors[project.status] ?? statusColors.uploaded
          }`}
        >
          {project.status}
        </span>
      </div>

      <h3 className="font-medium text-slate-100 truncate mb-1" title={project.filename}>
        {project.filename}
      </h3>
      <p className="text-xs text-slate-500 mb-4">{formatDate(project.upload_time)}</p>

      <div className="flex items-center gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <Clock size={12} />
          {formatDuration(project.duration)}
        </span>
        <span className="flex items-center gap-1">
          <HardDrive size={12} />
          {formatFileSize(project.size)}
        </span>
      </div>
    </div>
  )
}
