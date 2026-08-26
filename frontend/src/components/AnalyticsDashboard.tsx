import { useEffect, useRef, useState } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line, ReferenceLine,
} from 'recharts'
import { BarChart2, Loader2, AlertCircle, Clock, Download } from 'lucide-react'
import { AnalyticsReport } from '../types/analysis'
import { feedbackService } from '../services/feedbackService'
import Card from './Card'
import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'

interface Props {
  datasetId: string
  datasetName: string | null
  prefetchedReport?: AnalyticsReport
}

const SENTIMENT_COLORS: Record<string, string> = {
  Positive: '#4ADE80', Praise: '#86EFAC',
  Negative: '#F87171', Complaint: '#FCA5A5',
  Neutral: '#A8A4B8', Suggestion: '#FCD34D', Question: '#93C5FD',
}
const CHART_COLORS = ['#D4A843', '#8B7CF6', '#2DD4BF', '#F472B6', '#60A5FA', '#A78BFA', '#34D399']

export default function AnalyticsDashboard({ datasetId, datasetName, prefetchedReport }: Props) {
  const [report, setReport] = useState<AnalyticsReport | null>(prefetchedReport ?? null)
  const [loading, setLoading] = useState(!prefetchedReport)
  const [error, setError] = useState<string | null>(null)
  const [generating, setGenerating] = useState(false)
  const chartsRef = useRef<HTMLDivElement>(null)

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

  const r = {
    ...report,
    total_segments: report.total_segments ?? 0,
    analyzed_at: report.analyzed_at ?? new Date().toISOString(),
    sentiment_distribution: report.sentiment_distribution ?? {},
    timeline: report.timeline ?? [],
    sentiment_velocity: report.sentiment_velocity ?? [],
    top_issues: report.top_issues ?? [],
    top_positives: report.top_positives ?? [],
    topic_breakdown: report.topic_breakdown ?? [],
    confidence_stats: {
      mean: report.confidence_stats?.mean ?? 0,
      min: report.confidence_stats?.min ?? 0,
      max: report.confidence_stats?.max ?? 0,
      high_confidence_count: report.confidence_stats?.high_confidence_count ?? 0,
      low_confidence_count: report.confidence_stats?.low_confidence_count ?? 0,
      unanchored_count: report.confidence_stats?.unanchored_count ?? 0,
    },
  }

  // Chart data for PDF
  const sentimentPieData = Object.entries(r.sentiment_distribution)
    .filter(([, v]) => v > 0)
    .map(([name, value]) => ({ name, value }))

  const velocityData = r.sentiment_velocity.map(b => ({
    minute: `${b.minute}:00`, Positive: b.positive, Negative: b.negative, Net: b.net,
  }))

  const confidenceBarData = [
    { label: 'High ≥80%', count: r.confidence_stats.high_confidence_count, fill: '#4ADE80' },
    { label: 'Medium', count: r.total_segments - r.confidence_stats.high_confidence_count - r.confidence_stats.low_confidence_count, fill: '#FCD34D' },
    { label: 'Low <60%', count: r.confidence_stats.low_confidence_count, fill: '#F87171' },
  ]

  // PDF generation — slices the canvas into page-height chunks to avoid cutoff
  async function handleDownloadPDF() {
    if (!chartsRef.current) return
    setGenerating(true)
    try {
      chartsRef.current.style.display = 'block'
      await new Promise(resolve => setTimeout(resolve, 1500))

      const canvas = await html2canvas(chartsRef.current, {
        backgroundColor: '#090909',
        scale: 2,
        useCORS: true,
        logging: false,
      })

      const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })
      const pageWidth = pdf.internal.pageSize.getWidth()
      const pageHeight = pdf.internal.pageSize.getHeight()
      const margin = 8
      const contentWidth = pageWidth - margin * 2
      const contentHeight = pageHeight - margin * 2

      // Calculate how many pixels of the canvas fit per page
      const scale = contentWidth / canvas.width
      const pxPerPage = Math.floor(contentHeight / scale)

      let y = 0
      let pageNum = 0

      while (y < canvas.height) {
        if (pageNum > 0) pdf.addPage()

        // Slice the canvas for this page
        const sliceHeight = Math.min(pxPerPage, canvas.height - y)
        const sliceCanvas = document.createElement('canvas')
        sliceCanvas.width = canvas.width
        sliceCanvas.height = sliceHeight
        const ctx = sliceCanvas.getContext('2d')!
        // Fill dark background first
        ctx.fillStyle = '#090909'
        ctx.fillRect(0, 0, sliceCanvas.width, sliceCanvas.height)
        // Draw the slice from the source canvas
        ctx.drawImage(
          canvas,
          0, y, canvas.width, sliceHeight,
          0, 0, canvas.width, sliceHeight
        )

        const sliceData = sliceCanvas.toDataURL('image/png')
        const sliceImgHeight = sliceHeight * scale

        // Dark background for the full page
        pdf.setFillColor(9, 9, 9)
        pdf.rect(0, 0, pageWidth, pageHeight, 'F')

        // Add the slice image
        pdf.addImage(sliceData, 'PNG', margin, margin, contentWidth, sliceImgHeight)

        y += pxPerPage
        pageNum++
      }

      pdf.save(`sensecap-report-${datasetId.slice(0, 8)}.pdf`)
    } catch (err) {
      console.error('PDF generation failed:', err)
    } finally {
      if (chartsRef.current) chartsRef.current.style.display = 'none'
      setGenerating(false)
    }
  }

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
          {r.confidence_stats.unanchored_count > 0 && (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border"
              style={{ color: '#FCD34D', background: '#FCD34D12', borderColor: '#FCD34D28' }}>
              <Clock size={10} />
              {r.confidence_stats.unanchored_count} without timestamp
            </span>
          )}
          <span className="text-xs" style={{ color: '#5C5A72' }}>
            {r.total_segments} segments · {new Date(r.analyzed_at).toLocaleString()}
          </span>
        </div>
      </div>

      {/* ── Summary + Actions ──────────────────────────────────────────────── */}
      <Card className="py-8">
        <div className="flex flex-col items-center text-center gap-5">
          <div className="flex items-center gap-6 flex-wrap justify-center">
            {[
              { label: 'Segments', value: r.total_segments, color: '#D4A843' },
              { label: 'Confidence', value: `${Math.round(r.confidence_stats.mean * 100)}%`, color: '#8B7CF6' },
              { label: 'Topics', value: r.topic_breakdown.length, color: '#2DD4BF' },
              { label: 'Positive', value: sentimentPieData.find(s => s.name === 'Positive')?.value ?? 0, color: '#4ADE80' },
              { label: 'Negative', value: sentimentPieData.find(s => s.name === 'Negative')?.value ?? 0, color: '#F87171' },
            ].map(s => (
              <div key={s.label} className="text-center">
                <p className="text-xl font-bold" style={{ color: s.color }}>{s.value}</p>
                <p className="text-[10px] mt-0.5" style={{ color: '#5C5A72' }}>{s.label}</p>
              </div>
            ))}
          </div>

          <p className="text-sm max-w-md" style={{ color: '#A8A4B8' }}>
            Download the full report as PDF or view interactive charts in Sensecap.
          </p>

          <div className="flex items-center gap-3 flex-wrap justify-center">
            <button
              onClick={handleDownloadPDF}
              disabled={generating}
              className="flex items-center gap-2 px-5 py-3 rounded-xl text-sm font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-60"
              style={{ background: 'linear-gradient(135deg, #D4A843, #8B7CF6)', color: '#0C0A09', boxShadow: '0 4px 20px rgba(212,168,67,0.3)' }}
            >
              {generating ? <><Loader2 size={16} className="animate-spin" /> Generating Report…</> : <><Download size={16} /> Download Report (PDF)</>}
            </button>
          </div>
        </div>
      </Card>

      {/* ═══════════════════════════════════════════════════════════════════════
          HIDDEN — off-screen, rendered only during PDF generation
          Styled to match the premium dark dashboard layout
         ═══════════════════════════════════════════════════════════════════════ */}
      <div
        ref={chartsRef}
        style={{ display: 'none', position: 'absolute', left: '-9999px', top: 0, width: '900px', background: '#090909', padding: '36px', fontFamily: 'Inter, system-ui, sans-serif' }}
      >
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px', paddingBottom: '14px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{ width: '26px', height: '26px', borderRadius: '7px', background: 'linear-gradient(135deg, #FF7417, #FF8A3D)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <span style={{ fontSize: '12px', color: '#090909', fontWeight: 800 }}>⚡</span>
            </div>
            <span style={{ fontSize: '15px', fontWeight: 700, color: '#F5F5F3', letterSpacing: '-0.02em' }}>Sensecap</span>
            <span style={{ fontSize: '9px', fontWeight: 600, color: '#68645F', background: 'rgba(255,116,23,0.08)', padding: '2px 7px', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>by ClipSense</span>
          </div>
          <span style={{ fontSize: '10px', color: '#4A4744' }}>
            {datasetName ?? 'Dataset'} · Generated {new Date().toLocaleDateString()} at {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        {/* ── Hero: Stance + AI Summary side by side ──────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '5fr 7fr', gap: '16px', marginBottom: '20px' }}>
          {/* Left: Customer Sentiment */}
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.07)', borderRadius: '12px', padding: '22px' }}>
            <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.09em', textTransform: 'uppercase', color: '#68645F' }}>Customer sentiment</span>
            <h2 style={{ fontSize: '22px', fontWeight: 700, color: '#F5F5F3', letterSpacing: '-0.03em', margin: '8px 0 0', lineHeight: 1.2 }}>
              {(() => {
                const posPct = Math.round(((sentimentPieData.find(s => s.name === 'Positive')?.value ?? 0) / Math.max(r.total_segments, 1)) * 100)
                const negPct = Math.round(((sentimentPieData.find(s => s.name === 'Negative')?.value ?? 0) / Math.max(r.total_segments, 1)) * 100)
                if (posPct >= 55) return 'Positive, trending up'
                if (negPct >= 30) return 'Concerning, needs attention'
                return 'Mixed, leaning positive'
              })()}
            </h2>
            <div style={{ display: 'flex', alignItems: 'flex-end', gap: '12px', marginTop: '16px' }}>
              <span style={{ fontSize: '38px', fontWeight: 700, color: '#42D980', lineHeight: 1, letterSpacing: '-0.04em' }}>
                {Math.round(((sentimentPieData.find(s => s.name === 'Positive')?.value ?? 0) / Math.max(r.total_segments, 1)) * 100)}%
              </span>
              <span style={{ fontSize: '11px', color: '#4A4744', paddingBottom: '4px' }}>positive overall</span>
            </div>
            {/* Distribution bar */}
            <div style={{ display: 'flex', gap: '2px', height: '8px', borderRadius: '99px', overflow: 'hidden', marginTop: '16px' }}>
              {sentimentPieData.map((s, i) => {
                const pct = (s.value / Math.max(r.total_segments, 1)) * 100
                const color = s.name === 'Positive' || s.name === 'Praise' ? '#42D980' : s.name === 'Negative' || s.name === 'Complaint' ? '#FF6B6B' : '#FFBE2E'
                return <div key={i} style={{ width: `${pct}%`, background: color, borderRadius: i === 0 ? '99px 0 0 99px' : i === sentimentPieData.length - 1 ? '0 99px 99px 0' : '0' }} />
              })}
            </div>
            <div style={{ display: 'flex', gap: '14px', marginTop: '10px' }}>
              {sentimentPieData.map((s, i) => {
                const pct = Math.round((s.value / Math.max(r.total_segments, 1)) * 100)
                const color = s.name === 'Positive' || s.name === 'Praise' ? '#42D980' : s.name === 'Negative' || s.name === 'Complaint' ? '#FF6B6B' : '#FFBE2E'
                return (
                  <span key={i} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '10px' }}>
                    <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: color }} />
                    <span style={{ color: '#A09C96' }}>{pct}% {s.name.toLowerCase()}</span>
                  </span>
                )
              })}
            </div>
            {/* Mini stats */}
            <div style={{ display: 'flex', gap: '16px', marginTop: '16px', paddingTop: '14px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
              <div><p style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', margin: 0 }}>{r.total_segments}</p><p style={{ fontSize: '10px', color: '#68645F', margin: 0 }}>mentions</p></div>
              <div><p style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', margin: 0 }}>{Math.round(r.confidence_stats.mean * 100)}%</p><p style={{ fontSize: '10px', color: '#68645F', margin: 0 }}>confidence</p></div>
              <div><p style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', margin: 0 }}>{r.topic_breakdown.length}</p><p style={{ fontSize: '10px', color: '#68645F', margin: 0 }}>topics</p></div>
            </div>
          </div>

          {/* Right: AI Executive Summary */}
          <div style={{ background: 'linear-gradient(135deg, rgba(255,116,23,0.07), rgba(167,139,250,0.06), rgba(21,20,18,0))', borderRadius: '12px', border: '1px solid rgba(167,139,250,0.14)', overflow: 'hidden' }}>
            {/* Top gradient edge — rendered as a normal flow element, not absolute */}
            <div style={{ height: '2px', background: 'linear-gradient(90deg, rgba(255,116,23,0.6), rgba(167,139,250,0.5), transparent)', borderRadius: '12px 12px 0 0' }} />
            <div style={{ padding: '20px 22px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
              <span style={{ color: '#A78BFA', fontSize: '11px' }}>✦</span>
              <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase' as const, color: '#A78BFA' }}>AI Executive Summary</span>
              <span style={{ marginLeft: 'auto', fontSize: '10px', color: '#68645F' }}>{Math.round(r.confidence_stats.mean * 100)}% confidence</span>
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#F5F5F3', margin: '14px 0 0', letterSpacing: '-0.015em', lineHeight: 1.35 }}>
              {r.top_positives.length > 0 && r.top_issues.length > 0
                ? `Positive reactions around ${r.top_positives[0].topic}, while ${r.top_issues[0].topic} needs attention.`
                : r.top_positives.length > 0
                  ? `Strong positive signal around ${r.top_positives[0].topic}.`
                  : 'Baseline sentiment established.'}
            </h3>
            <p style={{ fontSize: '12px', color: '#A09C96', margin: '8px 0 0', lineHeight: 1.6 }}>
              {r.total_segments} feedback segments analysed across {r.topic_breakdown.length} topics with {Math.round(r.confidence_stats.mean * 100)}% model confidence.
            </p>
            {/* What to watch / What's working */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginTop: '16px' }}>
              <div style={{ background: 'rgba(255,107,107,0.05)', border: '1px solid rgba(255,107,107,0.12)', borderRadius: '9px', padding: '11px' }}>
                <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#FF6B6B' }}>⚠ What to watch</span>
                <p style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', margin: '5px 0 0' }}>{r.top_issues[0]?.topic ?? 'Nothing flagged'}</p>
                <p style={{ fontSize: '10px', color: '#68645F', margin: '2px 0 0' }}>{r.top_issues[0] ? `${r.top_issues[0].count} negative mentions` : 'No issues detected'}</p>
              </div>
              <div style={{ background: 'rgba(66,217,128,0.05)', border: '1px solid rgba(66,217,128,0.12)', borderRadius: '9px', padding: '11px' }}>
                <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.07em', textTransform: 'uppercase', color: '#42D980' }}>✓ What's working</span>
                <p style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', margin: '5px 0 0' }}>{r.top_positives[0]?.topic ?? 'Awaiting data'}</p>
                <p style={{ fontSize: '10px', color: '#68645F', margin: '2px 0 0' }}>{r.top_positives[0] ? `${r.top_positives[0].count} positive mentions` : 'No signal yet'}</p>
              </div>
            </div>
            <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
              <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#68645F' }}>Recommended action</span>
              <p style={{ fontSize: '12px', fontWeight: 500, color: '#F5F5F3', margin: '4px 0 0' }}>
                {r.top_issues[0] ? `Review negative feedback around ${r.top_issues[0].topic}.` : r.top_positives[0] ? `Keep reinforcing ${r.top_positives[0].topic}.` : 'Collect more feedback.'}
              </p>
            </div>
          </div>{/* close padding wrapper */}
          </div>{/* close AI panel */}
        </div>

        {/* ── KPI Strip ───────────────────────────────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1px', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', overflow: 'hidden', marginBottom: '20px', border: '1px solid rgba(255,255,255,0.06)' }}>
          {[
            { label: 'Overall sentiment', value: `${Math.round(((sentimentPieData.find(s => s.name === 'Positive')?.value ?? 0) / Math.max(r.total_segments, 1)) * 100)}%`, color: '#42D980' },
            { label: 'Mentions', value: String(r.total_segments), color: '#F5F5F3' },
            { label: 'Positive', value: String(sentimentPieData.find(s => s.name === 'Positive')?.value ?? 0), color: '#42D980' },
            { label: 'Negative', value: String(sentimentPieData.find(s => s.name === 'Negative')?.value ?? 0), color: '#FF6B6B' },
            { label: 'Confidence', value: `${Math.round(r.confidence_stats.mean * 100)}%`, color: '#FFBE2E' },
          ].map(m => (
            <div key={m.label} style={{ background: '#111110', padding: '14px 16px' }}>
              <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#68645F' }}>{m.label}</span>
              <p style={{ fontSize: '22px', fontWeight: 700, color: m.color, margin: '6px 0 0', letterSpacing: '-0.04em', lineHeight: 1 }}>{m.value}</p>
            </div>
          ))}
        </div>

        {/* ── Topic Intelligence Table ────────────────────────────────────── */}
        <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '20px', marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3', marginBottom: '14px' }}>Topic Intelligence</h3>
          {/* Column headers */}
          <div style={{ display: 'grid', gridTemplateColumns: '30px 140px 1fr 90px 50px', gap: '12px', padding: '0 2px 8px', fontSize: '9px', fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: '#4A4744' }}>
            <span></span><span>Topic</span><span>Sentiment mix</span><span style={{ textAlign: 'right' }}>Dominant</span><span style={{ textAlign: 'right' }}>Score</span>
          </div>
          {r.topic_breakdown.slice(0, 8).map((t, i) => {
            const total = t.positive + t.neutral + t.negative || 1
            const maxTotal = Math.max(...r.topic_breakdown.map(x => x.total), 1)
            const barW = (t.total / maxTotal) * 100
            const posPct = Math.round((t.positive / total) * 100)
            const neuPct = Math.round((t.neutral / total) * 100)
            const negPct = Math.round((t.negative / total) * 100)
            const dominant = t.positive >= t.negative ? (t.positive >= t.neutral ? 'positive' : 'neutral') : 'negative'
            const domColor = dominant === 'positive' ? '#42D980' : dominant === 'negative' ? '#FF6B6B' : '#FFBE2E'
            const domLabel = dominant === 'positive' ? `${posPct}% positive` : dominant === 'negative' ? `${negPct}% negative` : `${neuPct}% neutral`
            const scoreColor = t.engagement_score >= 0.2 ? '#42D980' : t.engagement_score <= -0.2 ? '#FF6B6B' : '#FFBE2E'
            return (
              <div key={t.topic} style={{ display: 'grid', gridTemplateColumns: '30px 140px 1fr 90px 50px', gap: '12px', alignItems: 'center', padding: '9px 2px', borderTop: i === 0 ? 'none' : '1px solid rgba(255,255,255,0.035)' }}>
                <span style={{ fontSize: '10px', fontWeight: 600, color: i === 0 ? '#FF7417' : '#4A4744', textAlign: 'right' }}>{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <span style={{ fontSize: '12px', fontWeight: 500, color: '#F5F5F3' }}>{t.topic}</span>
                  <span style={{ display: 'block', fontSize: '10px', color: '#68645F' }}>{t.total} mentions</span>
                </div>
                <div style={{ height: '7px', borderRadius: '99px', background: 'rgba(255,255,255,0.04)', overflow: 'hidden' }}>
                  <div style={{ display: 'flex', height: '100%', width: `${barW}%`, borderRadius: '99px', overflow: 'hidden', gap: '1px' }}>
                    {posPct > 0 && <div style={{ width: `${posPct}%`, background: '#42D980' }} />}
                    {neuPct > 0 && <div style={{ width: `${neuPct}%`, background: '#FFBE2E' }} />}
                    {negPct > 0 && <div style={{ width: `${negPct}%`, background: '#FF6B6B' }} />}
                  </div>
                </div>
                <span style={{ fontSize: '10px', fontWeight: 500, color: domColor, textAlign: 'right' }}>{domLabel}</span>
                <span style={{ fontSize: '11px', fontWeight: 600, color: scoreColor, textAlign: 'right' }}>{t.engagement_score >= 0 ? '+' : ''}{t.engagement_score.toFixed(2)}</span>
              </div>
            )
          })}
          <div style={{ display: 'flex', gap: '14px', marginTop: '12px', paddingTop: '10px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
            {[['Positive', '#42D980'], ['Neutral', '#FFBE2E'], ['Negative', '#FF6B6B']].map(([n, c]) => (
              <span key={n} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '10px', color: '#68645F' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: c }} />{n}
              </span>
            ))}
          </div>
        </div>

        {/* ── Sentiment Drivers (side by side) ────────────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
          {/* Positive drivers */}
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '12px' }}>
              <span style={{ color: '#42D980', fontSize: '10px' }}>✦</span>
              <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#42D980' }}>Positive drivers</span>
            </div>
            {r.top_positives.length === 0 ? (
              <p style={{ fontSize: '11px', color: '#4A4744' }}>No positive drivers detected.</p>
            ) : (
              r.top_positives.slice(0, 4).map((item, i) => (
                <div key={i} style={{ marginBottom: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 500, color: '#F5F5F3' }}>{item.topic}</span>
                    <span style={{ fontSize: '10px', color: '#42D980' }}>{Math.round(item.avg_confidence * 100)}%</span>
                  </div>
                  <div style={{ height: '5px', borderRadius: '99px', background: 'rgba(255,255,255,0.04)' }}>
                    <div style={{ height: '100%', borderRadius: '99px', background: '#42D980', opacity: 0.7, width: `${Math.min((item.count / Math.max(r.top_positives[0]?.count ?? 1, 1)) * 100, 100)}%` }} />
                  </div>
                  <span style={{ fontSize: '10px', color: '#68645F' }}>{item.count} mentions</span>
                </div>
              ))
            )}
          </div>
          {/* Negative drivers */}
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '18px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '12px' }}>
              <span style={{ color: '#FF6B6B', fontSize: '10px' }}>⚠</span>
              <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#FF6B6B' }}>Negative drivers</span>
            </div>
            {r.top_issues.length === 0 ? (
              <p style={{ fontSize: '11px', color: '#4A4744' }}>No negative drivers detected.</p>
            ) : (
              r.top_issues.slice(0, 4).map((item, i) => (
                <div key={i} style={{ marginBottom: '10px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 500, color: '#F5F5F3' }}>{item.topic}</span>
                    <span style={{ fontSize: '10px', color: '#FF6B6B' }}>{Math.round(item.avg_confidence * 100)}%</span>
                  </div>
                  <div style={{ height: '5px', borderRadius: '99px', background: 'rgba(255,255,255,0.04)' }}>
                    <div style={{ height: '100%', borderRadius: '99px', background: '#FF6B6B', opacity: 0.7, width: `${Math.min((item.count / Math.max(r.top_issues[0]?.count ?? 1, 1)) * 100, 100)}%` }} />
                  </div>
                  <span style={{ fontSize: '10px', color: '#68645F' }}>{item.count} mentions</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* ── Recommended Actions ─────────────────────────────────────────── */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '7px', marginBottom: '12px' }}>
            <span style={{ color: '#A78BFA', fontSize: '11px' }}>✦</span>
            <span style={{ fontSize: '14px', fontWeight: 600, color: '#F5F5F3' }}>Recommended Actions</span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
            {(() => {
              const actions: Array<{ title: string; body: string; impact: string; tone: string }> = []
              if (r.top_issues[0]) {
                actions.push({ title: `Investigate ${r.top_issues[0].topic}`, body: `${r.top_issues[0].count} negative mentions with ${Math.round(r.top_issues[0].avg_confidence * 100)}% confidence.`, impact: 'HIGH', tone: 'negative' })
              }
              if (r.top_positives[0]) {
                actions.push({ title: `Double down on ${r.top_positives[0].topic}`, body: `Strongest performer at ${Math.round((r.top_positives[0].count / Math.max(r.total_segments, 1)) * 100)}% of total positive feedback.`, impact: 'HIGH', tone: 'positive' })
              }
              if (r.topic_breakdown.length > 2) {
                actions.push({ title: 'Preserve what resonates', body: `"${r.topic_breakdown[0]?.topic}", "${r.topic_breakdown[1]?.topic}" recur throughout positive feedback.`, impact: 'MEDIUM', tone: 'neutral' })
              }
              return actions.map((a, i) => {
                const accent = a.tone === 'negative' ? '#FF6B6B' : a.tone === 'positive' ? '#42D980' : '#FFBE2E'
                const impactColor = a.impact === 'HIGH' ? '#FF6B6B' : '#FFBE2E'
                return (
                  <div key={i} style={{ background: '#1D1B19', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '16px', borderLeft: `2px solid ${accent}`, position: 'relative' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
                      <span style={{ fontSize: '10px', fontWeight: 600, color: '#4A4744' }}>{String(i + 1).padStart(2, '0')}</span>
                      <span style={{ fontSize: '9px', fontWeight: 600, letterSpacing: '0.06em', color: impactColor, background: `${impactColor}14`, border: `1px solid ${impactColor}26`, padding: '2px 6px', borderRadius: '4px' }}>{a.impact} IMPACT</span>
                    </div>
                    <h4 style={{ fontSize: '13px', fontWeight: 600, color: '#F5F5F3', margin: '0 0 6px', letterSpacing: '-0.01em' }}>{a.title}</h4>
                    <p style={{ fontSize: '11px', color: '#A09C96', margin: 0, lineHeight: 1.5 }}>{a.body}</p>
                  </div>
                )
              })
            })()}
          </div>
        </div>

        {/* ── Sentiment Charts (smaller, side by side) ────────────────────── */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '16px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 600, color: '#F5F5F3', marginBottom: '10px' }}>Sentiment Distribution</h4>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={sentimentPieData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={3} dataKey="value" isAnimationActive={false} label={({ name, value }) => `${name}: ${value}`}>
                  {sentimentPieData.map((entry, i) => <Cell key={i} fill={SENTIMENT_COLORS[entry.name] ?? CHART_COLORS[i % CHART_COLORS.length]} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '16px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 600, color: '#F5F5F3', marginBottom: '10px' }}>Confidence Distribution</h4>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={confidenceBarData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#68645F', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#68645F', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]} isAnimationActive={false}>
                  {confidenceBarData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ── Velocity chart ──────────────────────────────────────────────── */}
        {velocityData.length > 0 && (
          <div style={{ background: '#151412', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '12px', padding: '16px', marginBottom: '20px' }}>
            <h4 style={{ fontSize: '12px', fontWeight: 600, color: '#F5F5F3', marginBottom: '10px' }}>Sentiment Velocity</h4>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={velocityData} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
                <XAxis dataKey="minute" tick={{ fill: '#68645F', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#68645F', fontSize: 10 }} axisLine={false} tickLine={false} />
                <ReferenceLine y={0} stroke="rgba(255,255,255,0.08)" />
                <Line type="monotone" dataKey="Positive" stroke="#42D980" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="Negative" stroke="#FF6B6B" strokeWidth={2} dot={false} isAnimationActive={false} />
                <Line type="monotone" dataKey="Net" stroke="#FF7417" strokeWidth={2} dot={false} strokeDasharray="4 2" isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* ── Footer ──────────────────────────────────────────────────────── */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '12px', display: 'flex', justifyContent: 'space-between' }}>
          <p style={{ fontSize: '10px', color: '#4A4744', margin: 0 }}>
            Generated by Sensecap · Powered by ClipSense
          </p>
          <p style={{ fontSize: '10px', color: '#4A4744', margin: 0 }}>
            {r.total_segments} segments · {r.topic_breakdown.length} topics · {Math.round(r.confidence_stats.mean * 100)}% confidence
          </p>
        </div>
      </div>
    </div>
  )
}
