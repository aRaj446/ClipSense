import { Clock } from 'lucide-react'
import { TimelineInsight } from '../types/analysis'
import Card from './Card'

interface Props {
  insights: TimelineInsight[]
}

const sentimentStyles: Record<string, string> = {
  Positive:   'bg-green-500/15 text-green-400 border-green-500/30',
  Praise:     'bg-green-500/15 text-green-400 border-green-500/30',
  Negative:   'bg-red-500/15 text-red-400 border-red-500/30',
  Complaint:  'bg-red-500/15 text-red-400 border-red-500/30',
  Suggestion: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  Question:   'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  Neutral:    'bg-slate-500/15 text-slate-400 border-slate-500/30',
}

function confidenceColor(score: number): string {
  if (score >= 0.85) return 'bg-green-500'
  if (score >= 0.70) return 'bg-yellow-500'
  return 'bg-slate-400'
}

export default function TimelineInsights({ insights }: Props) {
  return (
    <Card>
      <h3 className="font-semibold text-slate-100 mb-4">Timeline Insights</h3>

      {insights.length === 0 ? (
        <p className="text-slate-500 text-sm text-center py-6">No timeline data extracted.</p>
      ) : (
        <ul className="space-y-3 max-h-96 overflow-y-auto pr-1">
          {insights.map((item, i) => {
            const style = sentimentStyles[item.sentiment] ?? sentimentStyles.Neutral
            return (
              <li
                key={i}
                className={`rounded-lg border p-3 space-y-2 ${style.split(' ').slice(2).join(' ')} bg-surface`}
              >
                <div className="flex items-start justify-between gap-2 flex-wrap">
                  <div className="flex items-center gap-2 flex-wrap">
                    {item.timestamp && (
                      <span className="flex items-center gap-1 text-xs text-slate-400 bg-surface-border px-2 py-0.5 rounded font-mono">
                        <Clock size={10} />
                        {item.timestamp}
                      </span>
                    )}
                    <span className="text-xs font-medium text-slate-300 bg-surface-border px-2 py-0.5 rounded">
                      {item.topic}
                    </span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${style}`}>
                      {item.sentiment}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500 shrink-0">
                    {Math.round(item.confidence * 100)}% confidence
                  </span>
                </div>

                <p className="text-slate-300 text-sm leading-relaxed">{item.summary}</p>

                {/* Confidence bar */}
                <div className="w-full bg-surface rounded-full h-1">
                  <div
                    className={`${confidenceColor(item.confidence)} h-1 rounded-full transition-all duration-500`}
                    style={{ width: `${item.confidence * 100}%` }}
                  />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
