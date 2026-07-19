import { Clock, Lightbulb } from 'lucide-react'
import { OptimizationRecommendation } from '../types/analysis'
import Card from './Card'

interface Props {
  recommendations: OptimizationRecommendation[]
}

const priorityStyles: Record<string, string> = {
  High:   'bg-red-500/15 text-red-400 border border-red-500/30',
  Medium: 'bg-yellow-500/15 text-yellow-400 border border-yellow-500/30',
  Low:    'bg-slate-500/15 text-slate-400 border border-slate-500/30',
}

const priorityDot: Record<string, string> = {
  High:   'bg-red-500',
  Medium: 'bg-yellow-500',
  Low:    'bg-slate-400',
}

export default function OptimizationRecommendations({ recommendations }: Props) {
  return (
    <Card>
      <h3 className="font-semibold text-slate-100 mb-4 flex items-center gap-2">
        <Lightbulb size={16} className="text-primary" />
        Optimization Recommendations
      </h3>

      {recommendations.length === 0 ? (
        <p className="text-slate-500 text-sm text-center py-6">
          No recommendations generated.
        </p>
      ) : (
        <ul className="space-y-3">
          {recommendations.map((rec, i) => (
            <li
              key={i}
              className="bg-surface border border-surface-border rounded-lg p-4 space-y-2"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${priorityStyles[rec.priority] ?? priorityStyles.Low}`}>
                  <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${priorityDot[rec.priority] ?? 'bg-slate-400'}`} />
                  {rec.priority} Priority
                </span>
                {rec.timestamp && (
                  <span className="flex items-center gap-1 text-xs text-slate-400 bg-surface-border px-2 py-0.5 rounded font-mono">
                    <Clock size={10} />
                    {rec.timestamp}
                  </span>
                )}
              </div>

              <p className="text-slate-100 text-sm font-medium">{rec.action}</p>
              <p className="text-slate-400 text-sm leading-relaxed">{rec.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
