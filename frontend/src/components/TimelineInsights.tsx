import { useState } from 'react'
import { Clock, ChevronDown, ChevronRight, ThumbsUp, ThumbsDown, Lightbulb, HelpCircle, Minus } from 'lucide-react'
import { TimelineInsight } from '../types/analysis'
import Card from './Card'

interface Props { insights: TimelineInsight[] }

const SENTIMENT_CONFIG: Record<string, {
  color: string; bg: string; border: string; icon: React.ReactNode
}> = {
  Positive:   { color: '#D4A843', bg: '#D4A84312', border: '#D4A84340', icon: <ThumbsUp  size={11} /> },
  Praise:     { color: '#D4A843', bg: '#D4A84312', border: '#D4A84340', icon: <ThumbsUp  size={11} /> },
  Negative:   { color: '#F87171', bg: '#F8717112', border: '#F8717140', icon: <ThumbsDown size={11} /> },
  Complaint:  { color: '#F87171', bg: '#F8717112', border: '#F8717140', icon: <ThumbsDown size={11} /> },
  Suggestion: { color: '#8B7CF6', bg: '#8B7CF612', border: '#8B7CF640', icon: <Lightbulb  size={11} /> },
  Question:   { color: '#60A5FA', bg: '#60A5FA12', border: '#60A5FA40', icon: <HelpCircle size={11} /> },
  Neutral:    { color: '#5C5A72', bg: '#5C5A7212', border: '#5C5A7240', icon: <Minus      size={11} /> },
}

function confidencePalette(score: number) {
  if (score >= 0.85) return '#D4A843'
  if (score >= 0.70) return '#8B7CF6'
  return '#5C5A72'
}

export default function TimelineInsights({ insights }: Props) {
  const [expanded, setExpanded] = useState<number | null>(null)

  return (
    <Card>
      <h3 className="font-semibold mb-5" style={{ color: '#F0EDE8' }}>
        Timeline Insights
        <span className="ml-2 text-xs font-normal" style={{ color: '#5C5A72' }}>
          {insights.length} segment{insights.length !== 1 ? 's' : ''}
        </span>
      </h3>

      {insights.length === 0 ? (
        <p className="text-sm text-center py-8" style={{ color: '#5C5A72' }}>No timeline data extracted.</p>
      ) : (
        <ul className="space-y-0 max-h-[420px] overflow-y-auto pr-1">
          {insights.map((item, i) => {
            const cfg     = SENTIMENT_CONFIG[item.sentiment] ?? SENTIMENT_CONFIG.Neutral
            const isOpen  = expanded === i
            const isLast  = i === insights.length - 1

            return (
              <li key={i} className="flex gap-3">
                {/* Vertical timeline spine */}
                <div className="flex flex-col items-center shrink-0 pt-1">
                  <div className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 z-10"
                    style={{ background: cfg.bg, border: `1.5px solid ${cfg.border}`, color: cfg.color }}>
                    {cfg.icon}
                  </div>
                  {!isLast && <div className="w-px flex-1 mt-1" style={{ background: '#252538' }} />}
                </div>

                {/* Card */}
                <div className="flex-1 pb-3">
                  <div
                    className="rounded-xl cursor-pointer transition-all duration-150"
                    style={{ background: isOpen ? cfg.bg : '#13131F', border: `1px solid ${isOpen ? cfg.border : '#252538'}` }}
                    onClick={() => setExpanded(isOpen ? null : i)}
                  >
                    <div className="flex items-center gap-2 px-3 py-2.5 flex-wrap">
                      {/* Timestamp */}
                      {item.timestamp && (
                        <span className="flex items-center gap-1 text-xs font-mono px-1.5 py-0.5 rounded"
                          style={{ background: '#1E1E30', color: '#A8A4B8' }}>
                          <Clock size={9} /> {item.timestamp}
                        </span>
                      )}
                      {/* Topic */}
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full"
                        style={{ background: '#1E1E30', color: '#F0EDE8' }}>
                        {item.topic}
                      </span>
                      {/* Sentiment badge */}
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full flex items-center gap-1"
                        style={{ background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}` }}>
                        {cfg.icon} {item.sentiment}
                      </span>
                      {/* Expand toggle */}
                      <span className="ml-auto shrink-0" style={{ color: '#5C5A72' }}>
                        {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                      </span>
                    </div>

                    {isOpen && (
                      <div className="px-3 pb-3 space-y-2 border-t" style={{ borderColor: cfg.border + '40' }}>
                        <p className="text-sm leading-relaxed pt-2" style={{ color: '#D4D0E8' }}>
                          {item.summary}
                        </p>
                        {/* Confidence */}
                        <div className="flex items-center gap-2">
                          <div className="flex-1 rounded-full h-1" style={{ background: '#1E1E30' }}>
                            <div className="h-1 rounded-full transition-all duration-500"
                              style={{ width: `${item.confidence * 100}%`, background: confidencePalette(item.confidence) }} />
                          </div>
                          <span className="text-xs font-mono shrink-0"
                            style={{ color: confidencePalette(item.confidence) }}>
                            {Math.round(item.confidence * 100)}%
                          </span>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </Card>
  )
}
