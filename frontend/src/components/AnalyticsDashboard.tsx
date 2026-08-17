import { useEffect, useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
  ScatterChart, Scatter, ZAxis,
  LineChart, Line, ReferenceLine,
} from 'recharts'
import { BarChart2, Loader2, AlertCircle, TrendingUp, TrendingDown, Activity, Clock } from 'lucide-react'
import { AnalyticsReport } from '../types/analysis'
import { feedbackService } from '../services/feedbackService'
import Card from './Card'

interface Props {
  datasetId: string
  datasetName: string | null
  prefetchedReport?: AnalyticsReport
}

const SENTIMENT_COLORS: Record<string, string> = {
  Positive:   '#4ADE80',
  Praise:     '#86EFAC',
  Negative:   '#F87171',
  Complaint:  '#FCA5A5',
  Neutral:    '#A8A4B8',
  Suggestion: '#FCD34D',
  Question:   '#93C5FD',
}

const CHART_COLORS = ['#D4A843', '#8B7CF6', '#2DD4BF', '#F472B6', '#60A5FA', '#A78BFA', '#34D399']

const TOOLTIP_STYLE = {
  backgroundColor: '#13131F',
  border: '1px solid #252538',
  borderRadius: '10px',
  color: '#F0EDE8',
  fontSize: '12px',
  boxShadow: '0 8px 32px 0 #00000060',
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span
        className="w-0.5 h-4 rounded-full shrink-0"
        style={{ background: 'linear-gradient(180deg, #D4A843, #8B7CF6)' }}
      />
      <span style={{ color: '#D4A843' }}>{icon}</span>
      <h3 className="font-semibold text-sm" style={{ color: '#F0EDE8' }}>{title}</h3>
    </div>
  )
}

function truncate(str: string, max = 14) {
  return str.length > max ? str.slice(0, max) + '…' : str
}

// Engagement score bar: -1.0 (all negative) → +1.0 (all positive)
function EngagementBar({ score }: { score: number }) {
  const pct = Math.round(((score + 1) / 2) * 100)
  const color = score >= 0.2 ? '#4ADE80' : score >= -0.2 ? '#FCD34D' : '#F87171'
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1 rounded-full" style={{ background: '#252538' }}>
        <div className="h-1 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-xs shrink-0 font-medium" style={{ color }}>
        {score >= 0 ? '+' : ''}{score.toFixed(2)}
      </span>
    </div>
  )
}

export default function AnalyticsDashboard({ datasetId, datasetName, prefetchedReport }: Props) {
  const [report, setReport]   = useState<AnalyticsReport | null>(prefetchedReport ?? null)
  const [loading, setLoading] = useState(!prefetchedReport)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    if (prefetchedReport) { setReport(prefetchedReport); setLoading(false); return }
    setLoading(true)
    setError(null)
    feedbackService.getAnalytics(datasetId)
      .then(setReport)
      .catch(() => setError('Failed to load analytics.'))
      .finally(() => setLoading(false))
  }, [datasetId, prefetchedReport])

  if (loading) {
    return (
      <Card className="flex items-center justify-center py-16 gap-3">
        <Loader2 size={20} className="animate-spin" style={{ color: '#D4A843' }} />
        <span className="text-sm" style={{ color: '#A8A4B8' }}>Generating analytics…</span>
      </Card>
    )
  }

  if (error || !report) {
    return (
      <Card className="flex items-center justify-center py-12 gap-3">
        <AlertCircle size={18} style={{ color: '#F87171' }} />
        <span className="text-sm" style={{ color: '#A8A4B8' }}>{error ?? 'No data'}</span>
      </Card>
    )
  }

  // ── Prepare chart data ────────────────────────────────────────────────────
  const safeReport = {
    ...report,
    total_segments:     report.total_segments      ?? 0,
    analyzed_at:        report.analyzed_at         ?? new Date().toISOString(),
    sentiment_distribution: report.sentiment_distribution ?? {},
    timeline:           report.timeline            ?? [],
    sentiment_velocity: report.sentiment_velocity  ?? [],
    top_issues:         report.top_issues          ?? [],
    top_positives:      report.top_positives       ?? [],
    topic_breakdown:    report.topic_breakdown     ?? [],
    confidence_stats: {
      mean:                   report.confidence_stats?.mean                   ?? 0,
      min:                    report.confidence_stats?.min                    ?? 0,
      max:                    report.confidence_stats?.max                    ?? 0,
      high_confidence_count:  report.confidence_stats?.high_confidence_count  ?? 0,
      low_confidence_count:   report.confidence_stats?.low_confidence_count   ?? 0,
      unanchored_count:       report.confidence_stats?.unanchored_count       ?? 0,
    },
  }

  const sentimentPieData = Object.entries(safeReport.sentiment_distribution ?? {})
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))

  // Topic bar sorted by engagement_score (already sorted from backend)
  const topicBarData = safeReport.topic_breakdown.slice(0, 8).map(t => ({
    topic:    truncate(t.topic),
    Positive: t.positive,
    Negative: t.negative,
    Neutral:  t.neutral,
    score:    t.engagement_score,
  }))

  const issueVsPositiveData = [
    ...safeReport.top_positives.map(t => ({ topic: truncate(t.topic, 18), count: t.count, type: 'Positive', conf: Math.round(t.avg_confidence * 100) })),
    ...safeReport.top_issues.map(t =>    ({ topic: truncate(t.topic, 18), count: t.count, type: 'Negative', conf: Math.round(t.avg_confidence * 100) })),
  ]

  const confidenceBarData = [
    { label: 'High ≥80%', count: safeReport.confidence_stats.high_confidence_count, fill: '#4ADE80' },
    { label: 'Medium',    count: safeReport.total_segments - safeReport.confidence_stats.high_confidence_count - safeReport.confidence_stats.low_confidence_count, fill: '#FCD34D' },
    { label: 'Low <60%',  count: safeReport.confidence_stats.low_confidence_count, fill: '#F87171' },
  ]

  const timelineScatterData = safeReport.timeline
    .filter(t => t.timestamp)
    .map(t => {
      const parts = (t.timestamp ?? '0:0').split(':').map(Number)
      const x = parts.length === 3
        ? parts[0] * 3600 + parts[1] * 60 + parts[2]
        : parts[0] * 60 + (parts[1] ?? 0)
      return { x, y: Math.round(t.confidence * 100), sentiment: t.sentiment, topic: t.topic, summary: t.summary }
    })

  const velocityData = safeReport.sentiment_velocity.map(b => ({
    minute: `${b.minute}:00`,
    Positive: b.positive,
    Negative: b.negative,
    Net: b.net,
  }))

  return (
    <div className="space-y-5">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 flex-wrap">
        <BarChart2 size={16} style={{ color: '#D4A843' }} />
        <h2 className="font-semibold" style={{ color: '#F0EDE8' }}>
          Analytics Dashboard
          {datasetName && <span className="ml-2 font-normal text-sm" style={{ color: '#5C5A72' }}>— {datasetName}</span>}
        </h2>
        <div className="ml-auto flex items-center gap-3 flex-wrap">
          {safeReport.confidence_stats.unanchored_count > 0 && (
            <span
              className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border"
              style={{ color: '#FCD34D', background: '#FCD34D12', borderColor: '#FCD34D28' }}
            >
              <Clock size={10} />
              {safeReport.confidence_stats.unanchored_count} without timestamp
            </span>
          )}
          <span className="text-xs" style={{ color: '#5C5A72' }}>
            {safeReport.total_segments} segments · {new Date(safeReport.analyzed_at).toLocaleString()}
          </span>
        </div>
      </div>

      {/* ── Stat pills ─────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Segments',  value: safeReport.total_segments,                                color: '#D4A843', bg: 'linear-gradient(135deg,#D4A84320,#D4A84308)' },
          { label: 'Avg Confidence',  value: `${Math.round(safeReport.confidence_stats.mean * 100)}%`, color: '#8B7CF6', bg: 'linear-gradient(135deg,#8B7CF620,#8B7CF608)' },
          { label: 'High Confidence', value: safeReport.confidence_stats.high_confidence_count,        color: '#4ADE80', bg: 'linear-gradient(135deg,#4ADE8020,#4ADE8008)' },
          { label: 'Topics Covered',  value: safeReport.topic_breakdown.length,                        color: '#2DD4BF', bg: 'linear-gradient(135deg,#2DD4BF20,#2DD4BF08)' },
        ].map(s => (
          <div
            key={s.label}
            className="rounded-2xl p-4 text-center border"
            style={{ background: s.bg, borderColor: `${s.color}22` }}
          >
            <p className="text-2xl font-bold" style={{ color: s.color }}>{s.value}</p>
            <p className="text-xs mt-0.5" style={{ color: '#5C5A72' }}>{s.label}</p>
          </div>
        ))}
      </div>

      {/* ── Row 1: Sentiment Pie + Topic Bar ───────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        <Card>
          <SectionTitle icon={<Activity size={14} />} title="Sentiment Distribution" />
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={sentimentPieData}
                cx="50%" cy="50%"
                innerRadius={50} outerRadius={80}
                paddingAngle={3}
                dataKey="value"
                label={false}
              >
                {sentimentPieData.map((entry, i) => (
                  <Cell key={i} fill={SENTIMENT_COLORS[entry.name] ?? CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v) => [v, 'Count']} />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-3 justify-center">
            {sentimentPieData.map((entry, i) => (
              <span key={entry.name} className="flex items-center gap-1 text-xs" style={{ color: '#A8A4B8' }}>
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ background: SENTIMENT_COLORS[entry.name] ?? CHART_COLORS[i % CHART_COLORS.length] }} />
                {entry.name} ({entry.value})
              </span>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle icon={<BarChart2 size={14} />} title="Sentiment by Topic (sorted by engagement)" />
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={topicBarData} margin={{ top: 4, right: 8, left: -18, bottom: 56 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252538" />
              <XAxis
                dataKey="topic"
                tick={{ fill: '#A8A4B8', fontSize: 10 }}
                angle={-40}
                textAnchor="end"
                interval={0}
                tickFormatter={(v) => truncate(v, 12)}
              />
              <YAxis tick={{ fill: '#A8A4B8', fontSize: 10 }} width={28} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend verticalAlign="top" wrapperStyle={{ fontSize: '11px', color: '#A8A4B8', paddingBottom: '4px' }} />
              <Bar dataKey="Positive" stackId="a" fill="#4ADE80" />
              <Bar dataKey="Neutral"  stackId="a" fill="#A8A4B8" />
              <Bar dataKey="Negative" stackId="a" fill="#F87171" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ── Row 2: Sentiment Velocity ───────────────────────────────────────── */}
      {velocityData.length > 0 && (
        <Card>
          <SectionTitle icon={<Activity size={14} />} title="Sentiment Velocity — reactions per minute" />
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={velocityData} margin={{ top: 8, right: 16, left: -18, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252538" />
              <XAxis dataKey="minute" tick={{ fill: '#A8A4B8', fontSize: 10 }} />
              <YAxis tick={{ fill: '#A8A4B8', fontSize: 10 }} width={28} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend verticalAlign="top" wrapperStyle={{ fontSize: '11px', color: '#A8A4B8', paddingBottom: '4px' }} />
              <ReferenceLine y={0} stroke="#363654" />
              <Line type="monotone" dataKey="Positive" stroke="#4ADE80" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Negative" stroke="#F87171" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey="Net"      stroke="#D4A843" strokeWidth={2} dot={false} strokeDasharray="4 2" />
            </LineChart>
          </ResponsiveContainer>
          <p className="text-xs mt-1 text-center" style={{ color: '#5C5A72' }}>
            Net (gold dashed) = positive − negative per minute. Peaks show where audience engagement was highest.
          </p>
        </Card>
      )}

      {/* ── Row 3: Top Issues vs Positives + Confidence ────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        <Card>
          <SectionTitle icon={<TrendingUp size={14} />} title="Top Positives vs Issues" />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={issueVsPositiveData}
              layout="vertical"
              margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#252538" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#A8A4B8', fontSize: 10 }} width={30} />
              <YAxis
                type="category"
                dataKey="topic"
                tick={{ fill: '#A8A4B8', fontSize: 10 }}
                width={100}
                tickFormatter={(v) => truncate(v, 16)}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {issueVsPositiveData.map((entry, i) => (
                  <Cell key={i} fill={entry.type === 'Positive' ? '#4ADE80' : '#F87171'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2 justify-center">
            <span className="flex items-center gap-1 text-xs" style={{ color: '#A8A4B8' }}><span className="w-2 h-2 rounded-full inline-block" style={{ background: '#4ADE80' }} />Positives</span>
            <span className="flex items-center gap-1 text-xs" style={{ color: '#A8A4B8' }}><span className="w-2 h-2 rounded-full inline-block" style={{ background: '#F87171' }} />Issues</span>
          </div>
        </Card>

        <Card>
          <SectionTitle icon={<TrendingDown size={14} />} title="Confidence Distribution" />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={confidenceBarData} margin={{ top: 4, right: 8, left: -18, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252538" />
              <XAxis dataKey="label" tick={{ fill: '#A8A4B8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#A8A4B8', fontSize: 10 }} width={28} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {confidenceBarData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div><p className="text-xs" style={{ color: '#5C5A72' }}>Min</p><p className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>{Math.round(safeReport.confidence_stats.min * 100)}%</p></div>
            <div><p className="text-xs" style={{ color: '#5C5A72' }}>Mean</p><p className="text-sm font-semibold" style={{ color: '#FCD34D' }}>{Math.round(safeReport.confidence_stats.mean * 100)}%</p></div>
            <div><p className="text-xs" style={{ color: '#5C5A72' }}>Max</p><p className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>{Math.round(safeReport.confidence_stats.max * 100)}%</p></div>
          </div>
        </Card>
      </div>

      {/* ── Row 4: Timeline Scatter ─────────────────────────────────────────── */}
      {timelineScatterData.length > 0 && (
        <Card>
          <SectionTitle icon={<Activity size={14} />} title="Confidence Over Time (Timestamped Segments)" />
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart margin={{ top: 10, right: 20, left: -8, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#252538" />
              <XAxis
                type="number" dataKey="x" name="Time (s)"
                tick={{ fill: '#A8A4B8', fontSize: 10 }}
                label={{ value: 'Time (s)', position: 'insideBottom', offset: -12, fill: '#5C5A72', fontSize: 11 }}
              />
              <YAxis
                type="number" dataKey="y" name="Confidence"
                domain={[0, 100]}
                tick={{ fill: '#A8A4B8', fontSize: 10 }}
                width={36}
                label={{ value: 'Conf %', angle: -90, position: 'insideLeft', offset: 10, fill: '#5C5A72', fontSize: 11 }}
              />
              <ZAxis range={[40, 40]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div style={TOOLTIP_STYLE} className="px-3 py-2 max-w-[220px]">
                      <p className="font-medium" style={{ color: '#F0EDE8' }}>{d.topic}</p>
                      <p style={{ color: '#A8A4B8' }}>Time: {d.x}s · Conf: {d.y}%</p>
                      <p style={{ color: SENTIMENT_COLORS[d.sentiment] ?? '#A8A4B8' }}>{d.sentiment}</p>
                      <p className="text-xs mt-1 line-clamp-2" style={{ color: '#5C5A72' }}>{d.summary}</p>
                    </div>
                  )
                }}
              />
              <Scatter
                data={timelineScatterData}
                fill="#D4A843"
                shape={(props: any) => {
                  const { cx, cy, payload } = props
                  return <circle cx={cx} cy={cy} r={5} fill={SENTIMENT_COLORS[payload.sentiment] ?? '#D4A843'} fillOpacity={0.85} />
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-xs mt-1 text-center" style={{ color: '#5C5A72' }}>
            Each dot = one timestamped segment. Color = sentiment. Hover for detail.
          </p>
        </Card>
      )}

      {/* ── Row 5: Topic engagement scores ─────────────────────────────────── */}
      <Card>
        <SectionTitle icon={<TrendingUp size={14} />} title="Topic Engagement Scores" />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
          {safeReport.topic_breakdown.map(t => (
            <div key={t.topic}>
              <div className="flex items-center justify-between">
                <span className="text-sm" style={{ color: '#F0EDE8' }}>{t.topic}</span>
                <span className="text-xs" style={{ color: '#5C5A72' }}>{t.total} mentions</span>
              </div>
              <EngagementBar score={t.engagement_score} />
            </div>
          ))}
        </div>
      </Card>

      {/* ── Row 6: Top Issues & Positives detail ───────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {[
          { title: 'Top Positives', items: safeReport.top_positives, color: '#4ADE80', bg: 'linear-gradient(135deg,#4ADE8010,#4ADE8006)', border: '#4ADE8020' },
          { title: 'Top Issues',    items: safeReport.top_issues,    color: '#F87171', bg: 'linear-gradient(135deg,#F8717110,#F8717106)', border: '#F8717120' },
        ].map(({ title, items, color, bg, border }) => (
          <Card key={title}>
            <SectionTitle icon={<BarChart2 size={14} />} title={title} />
            <div className="space-y-3">
              {items.length === 0 && <p className="text-xs" style={{ color: '#5C5A72' }}>None detected.</p>}
              {items.map((item, i) => (
                <div
                  key={i}
                  className="rounded-xl px-3 py-2.5 border"
                  style={{ background: bg, borderColor: border, borderLeft: `3px solid ${color}` }}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-sm font-medium truncate" style={{ color }}>{item.topic}</span>
                    <span className="text-xs shrink-0" style={{ color: '#5C5A72' }}>
                      {item.count} mentions · {Math.round(item.avg_confidence * 100)}% conf
                    </span>
                  </div>
                  <div className="space-y-1">
                    {item.sample_summaries.map((s, j) => (
                      <p key={j} className="text-xs flex gap-1.5" style={{ color: '#A8A4B8' }}>
                        <span style={{ color: `${color}80` }}>›</span>
                        <span className="line-clamp-1">{s}</span>
                      </p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

    </div>
  )
}
