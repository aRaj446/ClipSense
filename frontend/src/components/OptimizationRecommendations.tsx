import { Clock, Lightbulb, AlertTriangle, ArrowRight } from 'lucide-react'
import { OptimizationRecommendation } from '../types/analysis'
import Card from './Card'

interface Props { recommendations: OptimizationRecommendation[] }

const PRIORITY_CONFIG: Record<string, {
  color: string; bg: string; border: string; label: string; icon: React.ReactNode
}> = {
  High:   { color: '#F87171', bg: '#F8717112', border: '#F8717135', label: 'High',   icon: <AlertTriangle size={11} /> },
  Medium: { color: '#D4A843', bg: '#D4A84312', border: '#D4A84335', label: 'Medium', icon: <Lightbulb     size={11} /> },
  Low:    { color: '#8B7CF6', bg: '#8B7CF612', border: '#8B7CF635', label: 'Low',    icon: <ArrowRight    size={11} /> },
}

export default function OptimizationRecommendations({ recommendations }: Props) {
  // Group by priority order
  const ordered = [
    ...recommendations.filter(r => r.priority === 'High'),
    ...recommendations.filter(r => r.priority === 'Medium'),
    ...recommendations.filter(r => r.priority === 'Low'),
    ...recommendations.filter(r => !['High', 'Medium', 'Low'].includes(r.priority)),
  ]

  return (
    <Card>
      <h3 className="font-semibold mb-5 flex items-center gap-2" style={{ color: '#F0EDE8' }}>
        <Lightbulb size={15} style={{ color: '#D4A843' }} />
        Optimisation Recommendations
        {ordered.length > 0 && (
          <span className="ml-auto text-xs font-normal" style={{ color: '#5C5A72' }}>
            {ordered.length} action{ordered.length !== 1 ? 's' : ''}
          </span>
        )}
      </h3>

      {ordered.length === 0 ? (
        <p className="text-sm text-center py-8" style={{ color: '#5C5A72' }}>No recommendations generated.</p>
      ) : (
        <ul className="space-y-3">
          {ordered.map((rec, i) => {
            const cfg = PRIORITY_CONFIG[rec.priority] ?? PRIORITY_CONFIG.Low
            return (
              <li key={i} className="rounded-xl p-4 space-y-2.5 transition-all duration-150"
                style={{ background: cfg.bg, border: `1px solid ${cfg.border}`, borderLeft: `3px solid ${cfg.color}` }}>

                <div className="flex items-center gap-2 flex-wrap">
                  {/* Rank number */}
                  <span className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold shrink-0"
                    style={{ background: cfg.color + '22', color: cfg.color }}>
                    {i + 1}
                  </span>
                  {/* Priority badge */}
                  <span className="flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full"
                    style={{ background: cfg.color + '18', color: cfg.color, border: `1px solid ${cfg.border}` }}>
                    {cfg.icon} {cfg.label} Priority
                  </span>
                  {/* Timestamp */}
                  {rec.timestamp && (
                    <span className="flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded"
                      style={{ background: '#1E1E30', color: '#A8A4B8' }}>
                      <Clock size={9} /> {rec.timestamp}
                    </span>
                  )}
                </div>

                <p className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>{rec.action}</p>
                <p className="text-sm leading-relaxed" style={{ color: '#A8A4B8' }}>{rec.reason}</p>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
