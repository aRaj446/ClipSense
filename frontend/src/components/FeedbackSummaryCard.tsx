import { ThumbsUp, ThumbsDown, Minus } from 'lucide-react'
import { FeedbackSummary } from '../types/analysis'
import Card from './Card'

interface Props { summary: FeedbackSummary }

const ROWS = [
  {
    key:    'positive' as const,
    label:  'Positive',
    icon:   <ThumbsUp size={13} />,
    color:  '#D4A843',
    bg:     '#D4A84318',
    border: '#D4A84340',
  },
  {
    key:    'negative' as const,
    label:  'Negative',
    icon:   <ThumbsDown size={13} />,
    color:  '#F87171',
    bg:     '#F8717118',
    border: '#F8717140',
  },
  {
    key:    'neutral' as const,
    label:  'Neutral / Suggestions',
    icon:   <Minus size={13} />,
    color:  '#8B7CF6',
    bg:     '#8B7CF618',
    border: '#8B7CF640',
  },
]

export default function FeedbackSummaryCard({ summary }: Props) {
  const total = summary.positive + summary.negative + summary.neutral || 1
  const positivePct = Math.round((summary.positive / total) * 100)

  return (
    <Card>
      <h3 className="font-semibold mb-5" style={{ color: '#F0EDE8' }}>Sentiment Overview</h3>

      {/* Ring summary */}
      <div className="flex items-center justify-center mb-6">
        <div className="relative w-28 h-28">
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1E1E30" strokeWidth="3.2" />
            {/* Positive arc */}
            <circle cx="18" cy="18" r="15.9" fill="none"
              stroke="#D4A843" strokeWidth="3.2"
              strokeDasharray={`${(summary.positive / total) * 100} 100`}
              strokeLinecap="round" />
            {/* Negative arc */}
            <circle cx="18" cy="18" r="15.9" fill="none"
              stroke="#F87171" strokeWidth="3.2"
              strokeDasharray={`${(summary.negative / total) * 100} 100`}
              strokeDashoffset={`${-((summary.positive / total) * 100)}`}
              strokeLinecap="round" />
            {/* Neutral arc */}
            <circle cx="18" cy="18" r="15.9" fill="none"
              stroke="#8B7CF6" strokeWidth="3.2"
              strokeDasharray={`${(summary.neutral / total) * 100} 100`}
              strokeDashoffset={`${-(((summary.positive + summary.negative) / total) * 100)}`}
              strokeLinecap="round" />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-2xl font-bold" style={{ color: '#D4A843' }}>{positivePct}%</span>
            <span className="text-xs" style={{ color: '#5C5A72' }}>positive</span>
          </div>
        </div>
      </div>

      {/* Bars */}
      <div className="space-y-3">
        {ROWS.map(({ key, label, icon, color, bg, border }) => {
          const count = summary[key]
          const pct   = (count / total) * 100
          return (
            <div key={key} className="rounded-xl p-3" style={{ background: bg, border: `1px solid ${border}` }}>
              <div className="flex items-center justify-between mb-2">
                <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color }}>
                  {icon} {label}
                </span>
                <span className="text-xs font-bold font-mono" style={{ color }}>{count}</span>
              </div>
              <div className="w-full rounded-full h-1.5" style={{ background: '#1E1E30' }}>
                <div
                  className="h-1.5 rounded-full transition-all duration-700"
                  style={{ width: `${pct}%`, background: color }}
                />
              </div>
            </div>
          )
        })}
      </div>

      <p className="text-xs mt-4 text-center" style={{ color: '#5C5A72' }}>
        {total} segment{total !== 1 ? 's' : ''} analysed
      </p>
    </Card>
  )
}
