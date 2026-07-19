import { useEffect, useState } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
  ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { BarChart2, Loader2, AlertCircle, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import { AnalyticsReport } from '../types/analysis'
import { feedbackService } from '../services/feedbackService'
import Card from './Card'

interface Props {
  datasetId: string
  datasetName: string | null
  prefetchedReport?: AnalyticsReport
}

const SENTIMENT_COLORS: Record<string, string> = {
  Positive:   '#22c55e',
  Praise:     '#4ade80',
  Negative:   '#ef4444',
  Complaint:  '#f87171',
  Neutral:    '#94a3b8',
  Suggestion: '#f59e0b',
  Question:   '#60a5fa',
}

const CHART_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#60a5fa', '#a78bfa', '#34d399']

const TOOLTIP_STYLE = {
  backgroundColor: '#1e293b',
  border: '1px solid #334155',
  borderRadius: '8px',
  color: '#e2e8f0',
  fontSize: '12px',
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="text-primary">{icon}</span>
      <h3 className="font-semibold text-slate-100 text-sm">{title}</h3>
    </div>
  )
}

// Truncate long labels to fit axis ticks
function truncate(str: string, max = 14) {
  return str.length > max ? str.slice(0, max) + '…' : str
}

export default function AnalyticsDashboard({ datasetId, datasetName, prefetchedReport }: Props) {
  const [report, setReport]   = useState<AnalyticsReport | null>(prefetchedReport ?? null)
  const [loading, setLoading] = useState(!prefetchedReport)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    // If a prefetched report was passed in, use it directly — no fetch needed
    if (prefetchedReport) {
      setReport(prefetchedReport)
      setLoading(false)
      return
    }
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
        <Loader2 size={20} className="text-primary animate-spin" />
        <span className="text-slate-400 text-sm">Generating analytics…</span>
      </Card>
    )
  }

  if (error || !report) {
    return (
      <Card className="flex items-center justify-center py-12 gap-3">
        <AlertCircle size={18} className="text-red-400" />
        <span className="text-slate-400 text-sm">{error ?? 'No data'}</span>
      </Card>
    )
  }

  // ── Prepare chart data ──────────────────────────────────────────────────

  const sentimentPieData = Object.entries(report.sentiment_distribution)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))

  const topicBarData = report.topic_breakdown.slice(0, 8).map(t => ({
    topic: truncate(t.topic),
    Positive: t.positive,
    Negative: t.negative,
    Neutral:  t.neutral,
    total:    t.total,
  }))

  const issueVsPositiveData = [
    ...report.top_positives.map(t => ({ topic: truncate(t.topic, 18), count: t.count, type: 'Positive', conf: Math.round(t.avg_confidence * 100) })),
    ...report.top_issues.map(t =>    ({ topic: truncate(t.topic, 18), count: t.count, type: 'Negative', conf: Math.round(t.avg_confidence * 100) })),
  ]

  const confidenceBarData = [
    { label: 'High ≥80%', count: report.confidence_stats.high_confidence_count, fill: '#22c55e' },
    { label: 'Medium',    count: report.total_segments - report.confidence_stats.high_confidence_count - report.confidence_stats.low_confidence_count, fill: '#f59e0b' },
    { label: 'Low <60%',  count: report.confidence_stats.low_confidence_count, fill: '#ef4444' },
  ]

  const timelineScatterData = report.timeline
    .filter(t => t.timestamp)
    .map(t => {
      const parts = (t.timestamp ?? '0:0').split(':').map(Number)
      const x = parts.length === 3
        ? parts[0] * 3600 + parts[1] * 60 + parts[2]
        : parts[0] * 60 + (parts[1] ?? 0)
      return { x, y: Math.round(t.confidence * 100), sentiment: t.sentiment, topic: t.topic }
    })

  return (
    <div className="space-y-5">

      <div className="flex items-center gap-2">
        <BarChart2 size={16} className="text-primary" />
        <h2 className="font-semibold text-slate-100">
          Analytics Dashboard
          {datasetName && <span className="ml-2 text-slate-500 font-normal text-sm">— {datasetName}</span>}
        </h2>
        <span className="ml-auto text-xs text-slate-500">{report.total_segments} segments · {new Date(report.analyzed_at).toLocaleString()}</span>
      </div>

      {/* ── Stat pills ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Segments',  value: report.total_segments,                               color: 'text-primary' },
          { label: 'Avg Confidence',  value: `${Math.round(report.confidence_stats.mean * 100)}%`, color: 'text-yellow-400' },
          { label: 'High Confidence', value: report.confidence_stats.high_confidence_count,        color: 'text-green-400' },
          { label: 'Topics Covered',  value: report.topic_breakdown.length,                        color: 'text-blue-400' },
        ].map(s => (
          <Card key={s.label} className="text-center py-3">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-slate-500 mt-0.5">{s.label}</p>
          </Card>
        ))}
      </div>

      {/* ── Row 1: Sentiment Pie + Topic Bar ───────────────────────────── */}
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
          {/* Legend below chart — never overlaps */}
          <div className="flex flex-wrap gap-x-3 gap-y-1.5 mt-3 justify-center">
            {sentimentPieData.map((entry, i) => (
              <span key={entry.name} className="flex items-center gap-1 text-xs text-slate-400">
                <span className="w-2 h-2 rounded-full inline-block shrink-0" style={{ background: SENTIMENT_COLORS[entry.name] ?? CHART_COLORS[i % CHART_COLORS.length] }} />
                {entry.name} ({entry.value})
              </span>
            ))}
          </div>
        </Card>

        <Card>
          <SectionTitle icon={<BarChart2 size={14} />} title="Sentiment by Topic" />
          {/* Extra bottom margin so rotated labels don't clip */}
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={topicBarData} margin={{ top: 4, right: 8, left: -18, bottom: 56 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                dataKey="topic"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                angle={-40}
                textAnchor="end"
                interval={0}
                tickFormatter={(v) => truncate(v, 12)}
              />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} width={28} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Legend
                verticalAlign="top"
                wrapperStyle={{ fontSize: '11px', color: '#94a3b8', paddingBottom: '4px' }}
              />
              <Bar dataKey="Positive" stackId="a" fill="#22c55e" />
              <Bar dataKey="Neutral"  stackId="a" fill="#94a3b8" />
              <Bar dataKey="Negative" stackId="a" fill="#ef4444" radius={[3, 3, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ── Row 2: Top Issues vs Positives + Confidence ────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        <Card>
          <SectionTitle icon={<TrendingUp size={14} />} title="Top Positives vs Issues" />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart
              data={issueVsPositiveData}
              layout="vertical"
              margin={{ top: 4, right: 16, left: 0, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 10 }} width={30} />
              <YAxis
                type="category"
                dataKey="topic"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                width={100}
                tickFormatter={(v) => truncate(v, 16)}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                {issueVsPositiveData.map((entry, i) => (
                  <Cell key={i} fill={entry.type === 'Positive' ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2 justify-center">
            <span className="flex items-center gap-1 text-xs text-slate-400"><span className="w-2 h-2 rounded-full bg-green-500 inline-block" />Positives</span>
            <span className="flex items-center gap-1 text-xs text-slate-400"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" />Issues</span>
          </div>
        </Card>

        <Card>
          <SectionTitle icon={<TrendingDown size={14} />} title="Confidence Distribution" />
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={confidenceBarData} margin={{ top: 4, right: 8, left: -18, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="label" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} width={28} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {confidenceBarData.map((entry, i) => (
                  <Cell key={i} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-3 grid grid-cols-3 gap-2 text-center">
            <div><p className="text-xs text-slate-500">Min</p><p className="text-sm font-semibold text-slate-200">{Math.round(report.confidence_stats.min * 100)}%</p></div>
            <div><p className="text-xs text-slate-500">Mean</p><p className="text-sm font-semibold text-yellow-400">{Math.round(report.confidence_stats.mean * 100)}%</p></div>
            <div><p className="text-xs text-slate-500">Max</p><p className="text-sm font-semibold text-slate-200">{Math.round(report.confidence_stats.max * 100)}%</p></div>
          </div>
        </Card>
      </div>

      {/* ── Row 3: Timeline Scatter ─────────────────────────────────────── */}
      {timelineScatterData.length > 0 && (
        <Card>
          <SectionTitle icon={<Activity size={14} />} title="Confidence Over Time (Timestamped Segments)" />
          <ResponsiveContainer width="100%" height={240}>
            <ScatterChart margin={{ top: 10, right: 20, left: -8, bottom: 24 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis
                type="number" dataKey="x" name="Time (s)"
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                label={{ value: 'Time (s)', position: 'insideBottom', offset: -12, fill: '#64748b', fontSize: 11 }}
              />
              <YAxis
                type="number" dataKey="y" name="Confidence"
                domain={[0, 100]}
                tick={{ fill: '#94a3b8', fontSize: 10 }}
                width={36}
                label={{ value: 'Conf %', angle: -90, position: 'insideLeft', offset: 10, fill: '#64748b', fontSize: 11 }}
              />
              <ZAxis range={[40, 40]} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div style={TOOLTIP_STYLE} className="px-3 py-2">
                      <p className="font-medium text-slate-200">{d.topic}</p>
                      <p className="text-slate-400">Time: {d.x}s · Confidence: {d.y}%</p>
                      <p style={{ color: SENTIMENT_COLORS[d.sentiment] ?? '#94a3b8' }}>{d.sentiment}</p>
                    </div>
                  )
                }}
              />
              <Scatter
                data={timelineScatterData}
                fill="#6366f1"
                shape={(props: any) => {
                  const { cx, cy, payload } = props
                  return <circle cx={cx} cy={cy} r={5} fill={SENTIMENT_COLORS[payload.sentiment] ?? '#6366f1'} fillOpacity={0.85} />
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-xs text-slate-600 mt-1 text-center">Each dot = one timestamped feedback segment. Color = sentiment.</p>
        </Card>
      )}

      {/* ── Row 4: Top Issues & Positives detail ───────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {[
          { title: 'Top Positives', items: report.top_positives, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/20' },
          { title: 'Top Issues',    items: report.top_issues,    color: 'text-red-400',   bg: 'bg-red-500/10',   border: 'border-red-500/20' },
        ].map(({ title, items, color, bg, border }) => (
          <Card key={title}>
            <SectionTitle icon={<BarChart2 size={14} />} title={title} />
            <div className="space-y-2">
              {items.length === 0 && <p className="text-slate-500 text-xs">None detected.</p>}
              {items.map((item, i) => (
                <div key={i} className={`rounded-lg px-3 py-2 border ${bg} ${border}`}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={`text-sm font-medium ${color} truncate`}>{item.topic}</span>
                    <span className="text-xs text-slate-500 shrink-0">{item.count} mentions · {Math.round(item.avg_confidence * 100)}% conf</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{item.sample_summary}</p>
                </div>
              ))}
            </div>
          </Card>
        ))}
      </div>

    </div>
  )
}
