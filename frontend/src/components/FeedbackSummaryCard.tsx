import { ThumbsUp, ThumbsDown, Minus } from 'lucide-react'
import { FeedbackSummary } from '../types/analysis'
import Card from './Card'

interface Props {
  summary: FeedbackSummary
}

export default function FeedbackSummaryCard({ summary }: Props) {
  const total = summary.positive + summary.negative + summary.neutral || 1

  const rows = [
    {
      label: 'Positive',
      count: summary.positive,
      icon: <ThumbsUp size={14} />,
      bar: 'bg-green-500',
      text: 'text-green-400',
      bg: 'bg-green-500/10',
    },
    {
      label: 'Negative',
      count: summary.negative,
      icon: <ThumbsDown size={14} />,
      bar: 'bg-red-500',
      text: 'text-red-400',
      bg: 'bg-red-500/10',
    },
    {
      label: 'Neutral / Suggestions',
      count: summary.neutral,
      icon: <Minus size={14} />,
      bar: 'bg-slate-400',
      text: 'text-slate-400',
      bg: 'bg-slate-500/10',
    },
  ]

  return (
    <Card>
      <h3 className="font-semibold text-slate-100 mb-4">Feedback Summary</h3>
      <div className="space-y-3">
        {rows.map(({ label, count, icon, bar, text, bg }) => (
          <div key={label}>
            <div className="flex items-center justify-between mb-1">
              <span className={`flex items-center gap-1.5 text-sm ${text}`}>
                {icon}
                {label}
              </span>
              <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${bg} ${text}`}>
                {count}
              </span>
            </div>
            <div className="w-full bg-surface rounded-full h-1.5">
              <div
                className={`${bar} h-1.5 rounded-full transition-all duration-500`}
                style={{ width: `${(count / total) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-slate-500 mt-4">
        {total} feedback segment{total !== 1 ? 's' : ''} analysed
      </p>
    </Card>
  )
}
