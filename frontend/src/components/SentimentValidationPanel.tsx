/**
 * SentimentValidationPanel
 *
 * Answers leadership's question: "Why did ClipSense choose these clips?"
 *
 * Chain visualised:
 *   SENTIMENT → THEME / TOPIC → CLIP SELECTION → GENERATED TRAILER
 *
 * Data sources (all from existing backend response — no new endpoints):
 *   job.analysis_report.top_scene_categories   → positive theme bars
 *   job.analysis_report.positive_patterns       → positive evidence sentences
 *   job.analysis_report.negative_patterns       → negative evidence sentences
 *   job.analysis_report.influence_explanation   → AI reasoning paragraph
 *   job.analysis_report.scene_selection_rationale[i].confidence → per-clip confidence
 *   job.editing_plan.clips[i].topic             → theme matching
 *   job.editing_plan.clips[i].sentiment         → sentiment tag
 *   job.editing_plan.clips[i].reason            → selection reason
 *   job.editing_plan.clips[i].transcript_text   → dialogue excerpt
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { MessageSquare, TrendingUp, TrendingDown, ChevronDown } from 'lucide-react'
import { SmartTrailerJob, SmartTrailerAnalysis } from '../types/analysis'
import Card from './Card'

// ── Types ─────────────────────────────────────────────────────────────────────

type Clip = NonNullable<SmartTrailerJob['editing_plan']>['clips'][number]

interface Props {
  job: SmartTrailerJob
}

// ── Design-system colour tokens ───────────────────────────────────────────────
// Positive → primary gold (not bright green — per design system)
// Neutral  → ink.muted warm grey
// Negative → accent.red (already used throughout the codebase)

const SENTIMENT_COLORS = {
  positive: '#D4A843',
  neutral:  '#A8A4B8',
  negative: '#F87171',
} as const

const POSITIVE_SENTIMENTS = new Set(['Positive', 'Praise'])
const NEGATIVE_SENTIMENTS = new Set(['Negative', 'Complaint'])

function sentimentColor(s: string): string {
  if (POSITIVE_SENTIMENTS.has(s)) return SENTIMENT_COLORS.positive
  if (NEGATIVE_SENTIMENTS.has(s)) return SENTIMENT_COLORS.negative
  return SENTIMENT_COLORS.neutral
}

function sentimentLabel(s: string): string {
  if (POSITIVE_SENTIMENTS.has(s)) return 'Positive'
  if (NEGATIVE_SENTIMENTS.has(s)) return 'Negative'
  return 'Neutral'
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(secs: number): string {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Case-insensitive, whitespace-normalised topic → category match */
function normalise(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, ' ')
}

function topicMatchesCategory(topic: string, categories: string[]): boolean {
  const t = normalise(topic)
  return categories.some(c => {
    const cn = normalise(c)
    return t === cn || t.includes(cn) || cn.includes(t)
  })
}

/**
 * Build theme bars from top_scene_categories.
 *
 * The backend gives us category strings but no per-category percentages.
 * We derive percentages from how many generated clips match each category —
 * this is the only honest signal available without a new backend endpoint.
 * If no clips match at all, we fall back to equal-weight bars so the UI
 * never shows empty bars.
 */
function buildThemeBars(
  categories: string[],
  clips: Clip[],
): { label: string; pct: number; matchCount: number }[] {
  if (categories.length === 0) return []

  const counts = categories.map(cat => ({
    label: cat,
    matchCount: clips.filter(c => topicMatchesCategory(c.topic, [cat])).length,
  }))

  const maxCount = Math.max(...counts.map(c => c.matchCount), 1)

  return counts.map(c => ({
    label:      c.label,
    matchCount: c.matchCount,
    // Scale so the highest-count category = 100%, others proportional.
    // Minimum bar width 12% so bars are always visible.
    pct: Math.max(12, Math.round((c.matchCount / maxCount) * 100)),
  }))
}

// ── Sub-components ────────────────────────────────────────────────────────────

/** Animated horizontal bar for a theme */
function ThemeBar({
  label,
  pct,
  matchCount,
  isHighlighted,
  onClick,
}: {
  label: string
  pct: number
  matchCount: number
  isHighlighted: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left group"
      style={{ outline: 'none' }}
    >
      <div className="flex items-center justify-between mb-1">
        <span
          className="text-xs font-medium transition-colors duration-150"
          style={{ color: isHighlighted ? '#D4A843' : '#F0EDE8' }}
        >
          {label}
        </span>
        <span
          className="text-[10px] font-mono transition-colors duration-150"
          style={{ color: isHighlighted ? '#D4A843' : '#5C5A72' }}
        >
          {matchCount} clip{matchCount !== 1 ? 's' : ''}
        </span>
      </div>
      <div
        className="h-1.5 rounded-full overflow-hidden"
        style={{ background: '#1E1E30' }}
      >
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${pct}%`,
            background: isHighlighted
              ? 'linear-gradient(90deg, #D4A843, #E8C56A)'
              : 'linear-gradient(90deg, #D4A84360, #D4A84330)',
          }}
        />
      </div>
    </button>
  )
}

/** Sentiment tag chip — uses design-system colours */
function SentimentTag({ sentiment }: { sentiment: string }) {
  const color = sentimentColor(sentiment)
  const label = sentimentLabel(sentiment)
  return (
    <span
      className="inline-flex items-center text-[10px] font-semibold px-2 py-0.5 rounded-full shrink-0"
      style={{
        background: `${color}18`,
        color,
        border: `1px solid ${color}30`,
      }}
    >
      {label}
    </span>
  )
}

/** Single clip card in the right column */
function ClipCard({
  clip,
  index,
  isSelected,
  isThemeMatch,
  rationaleConfidence,
  onClick,
}: {
  clip: Clip
  index: number
  isSelected: boolean
  isThemeMatch: boolean
  rationaleConfidence: number | null
  onClick: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const color = sentimentColor(clip.sentiment)
  const [open, setOpen] = useState(false)

  // Auto-expand when selected from outside
  useEffect(() => {
    if (isSelected) setOpen(true)
  }, [isSelected])

  // Scroll into view when selected
  useEffect(() => {
    if (isSelected && ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }
  }, [isSelected])

  return (
    <div
      ref={ref}
      className="rounded-xl cursor-pointer transition-all duration-200"
      style={{
        background: isSelected ? '#13131F' : 'rgba(255,255,255,0.02)',
        border: `1px solid ${isSelected ? color + '50' : '#1E1E30'}`,
        borderLeft: `3px solid ${color}`,
        boxShadow: isSelected ? `0 0 0 1px ${color}20, 0 4px 16px ${color}10` : 'none',
      }}
      onClick={() => {
        onClick()
        setOpen(o => !o)
      }}
    >
      {/* ── Collapsed row ── */}
      <div className="flex items-center gap-2.5 px-3 py-2.5 flex-wrap">
        {/* Clip number */}
        <span
          className="text-[10px] font-mono font-semibold shrink-0 w-6 h-6 rounded-md flex items-center justify-center"
          style={{
            background: isSelected ? color + '20' : '#1E1E30',
            color: isSelected ? color : '#5C5A72',
          }}
        >
          {String(index + 1).padStart(2, '0')}
        </span>

        {/* Timecode */}
        <span
          className="text-[10px] font-mono shrink-0 tabular-nums"
          style={{ color: '#5C5A72' }}
        >
          {fmt(clip.start_time)} – {fmt(clip.end_time)}
        </span>

        {/* Topic chip */}
        <span
          className="text-[10px] font-medium px-2 py-0.5 rounded-full shrink-0 max-w-[120px] truncate"
          style={{
            background: isThemeMatch ? '#D4A84318' : '#1E1E30',
            color:      isThemeMatch ? '#D4A843'   : '#A8A4B8',
            border:     `1px solid ${isThemeMatch ? '#D4A84330' : '#252538'}`,
          }}
          title={clip.topic}
        >
          {clip.topic}
        </span>

        {/* Sentiment tag */}
        <SentimentTag sentiment={clip.sentiment} />

        {/* Confidence badge — from scene_selection_rationale */}
        {rationaleConfidence !== null && (
          <span
            className="text-[10px] font-mono shrink-0 ml-auto"
            style={{ color: '#5C5A72' }}
          >
            {Math.round(rationaleConfidence * 100)}%
          </span>
        )}

        {/* Expand toggle */}
        <span
          className="shrink-0 transition-transform duration-150"
          style={{
            color: '#5C5A72',
            transform: open ? 'rotate(0deg)' : 'rotate(-90deg)',
          }}
        >
          <ChevronDown size={12} />
        </span>
      </div>

      {/* ── Expanded body ── */}
      {open && (
        <div
          className="px-3 pb-3 space-y-2.5 border-t"
          style={{ borderColor: color + '20' }}
        >
          {/* Reason — the core answer to "why this clip?" */}
          <div className="pt-2.5 space-y-1">
            <p
              className="text-[10px] font-semibold uppercase tracking-wide"
              style={{ color: '#5C5A72' }}
            >
              Why this clip was selected
            </p>
            <p
              className="text-xs leading-relaxed"
              style={{ color: '#A8A4B8' }}
            >
              {clip.reason}
            </p>
          </div>

          {/* Theme match indicator */}
          {isThemeMatch && (
            <div
              className="flex items-center gap-1.5 text-[10px] rounded-lg px-2.5 py-1.5"
              style={{ background: '#D4A84310', border: '1px solid #D4A84320' }}
            >
              <span style={{ color: '#D4A843' }}>◆</span>
              <span style={{ color: '#D4A843' }}>
                Topic "{clip.topic}" matches a top positive theme
              </span>
            </div>
          )}

          {/* Transcript excerpt */}
          {clip.transcript_text?.trim() && (
            <div
              className="flex gap-2 items-start rounded-lg px-2.5 py-2"
              style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}
            >
              <MessageSquare
                size={10}
                className="shrink-0 mt-0.5"
                style={{ color: '#5C5A72' }}
              />
              <p
                className="text-[11px] italic leading-relaxed"
                style={{ color: '#5C5A72' }}
              >
                "{clip.transcript_text}"
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Match score display ───────────────────────────────────────────────────────

function MatchScore({
  aligned,
  total,
  hasCategories,
}: {
  aligned: number
  total: number
  hasCategories: boolean
}) {
  if (!hasCategories) {
    return (
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-xl text-xs"
        style={{ background: '#1E1E30', color: '#5C5A72' }}
      >
        Theme alignment unavailable — no top scene categories in analysis
      </div>
    )
  }

  const pct = total > 0 ? (aligned / total) * 100 : 0
  const color = pct >= 60 ? '#D4A843' : pct >= 30 ? '#A8A4B8' : '#F87171'

  return (
    <div
      className="flex items-center gap-3 px-4 py-3 rounded-xl"
      style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}
    >
      {/* Circular indicator */}
      <div className="relative shrink-0 w-10 h-10">
        <svg viewBox="0 0 36 36" className="w-10 h-10 -rotate-90">
          <circle
            cx="18" cy="18" r="15"
            fill="none"
            stroke="#1E1E30"
            strokeWidth="3"
          />
          <circle
            cx="18" cy="18" r="15"
            fill="none"
            stroke={color}
            strokeWidth="3"
            strokeDasharray={`${pct * 0.942} 94.2`}
            strokeLinecap="round"
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
        </svg>
        <span
          className="absolute inset-0 flex items-center justify-center text-[9px] font-bold"
          style={{ color }}
        >
          {Math.round(pct)}%
        </span>
      </div>

      {/* Text */}
      <div className="min-w-0">
        <p className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>
          {aligned} of {total} clips align with top positive themes
        </p>
        <p className="text-[10px] mt-0.5" style={{ color: '#5C5A72' }}>
          {pct.toFixed(1)}% theme alignment
        </p>
      </div>
    </div>
  )
}

// ── Left column ───────────────────────────────────────────────────────────────

function LeftColumn({
  analysis,
  clips,
  selectedTopic,
  onThemeClick,
}: {
  analysis: SmartTrailerAnalysis
  clips: Clip[]
  selectedTopic: string | null
  onThemeClick: (topic: string | null) => void
}) {
  const positiveBars = buildThemeBars(analysis.top_scene_categories, clips)

  // Negative themes: derived from negative_patterns sentences.
  // The backend gives us sentence strings, not structured topic/count objects.
  // We display them as evidence bullets, not percentage bars, because we have
  // no honest percentage to show for them.
  const negPatterns = analysis.negative_patterns ?? []
  const posPatterns = analysis.positive_patterns ?? []

  return (
    <div className="space-y-5">

      {/* Header */}
      <div>
        <h3
          className="text-sm font-semibold"
          style={{ color: '#F0EDE8' }}
        >
          Why these clips?
        </h3>
        <p
          className="text-xs mt-1 leading-relaxed"
          style={{ color: '#5C5A72' }}
        >
          ClipSense selected these moments based on audience sentiment.
        </p>
      </div>

      {/* Top positive themes — percentage bars */}
      {positiveBars.length > 0 && (
        <div className="space-y-3">
          <p
            className="text-[10px] font-semibold uppercase tracking-widest flex items-center gap-1.5"
            style={{ color: '#D4A843' }}
          >
            <TrendingUp size={10} />
            Top positive themes
          </p>
          <div className="space-y-3">
            {positiveBars.map(bar => (
              <ThemeBar
                key={bar.label}
                label={bar.label}
                pct={bar.pct}
                matchCount={bar.matchCount}
                isHighlighted={selectedTopic !== null && normalise(selectedTopic) === normalise(bar.label)}
                onClick={() =>
                  onThemeClick(
                    selectedTopic !== null && normalise(selectedTopic) === normalise(bar.label)
                      ? null
                      : bar.label,
                  )
                }
              />
            ))}
          </div>
          <p
            className="text-[10px] leading-relaxed"
            style={{ color: '#5C5A72' }}
          >
            Bar width = proportion of generated clips matching each theme.
            Click a theme to highlight its clips.
          </p>
        </div>
      )}

      {/* Positive patterns — sentence evidence */}
      {posPatterns.length > 0 && (
        <div className="space-y-2">
          <p
            className="text-[10px] font-semibold uppercase tracking-widest"
            style={{ color: '#5C5A72' }}
          >
            Positive signals applied
          </p>
          <div className="space-y-1.5">
            {posPatterns.map((p, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-xs"
                style={{ color: '#A8A4B8' }}
              >
                <span
                  className="shrink-0 mt-0.5 text-[10px] font-bold"
                  style={{ color: '#D4A84370' }}
                >
                  +
                </span>
                {p}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Negative themes — sentence evidence */}
      {negPatterns.length > 0 && (
        <div className="space-y-2">
          <p
            className="text-[10px] font-semibold uppercase tracking-widest flex items-center gap-1.5"
            style={{ color: '#F87171' }}
          >
            <TrendingDown size={10} />
            Negative patterns avoided
          </p>
          <div className="space-y-1.5">
            {negPatterns.map((p, i) => (
              <div
                key={i}
                className="flex items-start gap-2 text-xs"
                style={{ color: '#A8A4B8' }}
              >
                <span
                  className="shrink-0 mt-0.5 text-[10px] font-bold"
                  style={{ color: '#F8717170' }}
                >
                  −
                </span>
                {p}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Influence explanation — verbatim from backend */}
      {analysis.influence_explanation && (
        <div
          className="rounded-xl px-3 py-3 space-y-1"
          style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}
        >
          <p
            className="text-[10px] font-semibold uppercase tracking-widest"
            style={{ color: '#5C5A72' }}
          >
            AI reasoning
          </p>
          <p
            className="text-xs leading-relaxed italic"
            style={{ color: '#A8A4B8' }}
          >
            {analysis.influence_explanation}
          </p>
        </div>
      )}
    </div>
  )
}

// ── Right column ──────────────────────────────────────────────────────────────

function RightColumn({
  clips,
  analysis,
  selectedClipIndex,
  selectedTopic,
  onClipSelect,
}: {
  clips: Clip[]
  analysis: SmartTrailerAnalysis
  selectedClipIndex: number | null
  selectedTopic: string | null
  onClipSelect: (index: number, topic: string) => void
}) {
  const categories = analysis.top_scene_categories ?? []
  const rationale  = analysis.scene_selection_rationale ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3
          className="text-sm font-semibold"
          style={{ color: '#F0EDE8' }}
        >
          Generated trailer
        </h3>
        <span
          className="text-[10px] font-mono px-2 py-0.5 rounded-full"
          style={{ background: '#1E1E30', color: '#A8A4B8' }}
        >
          {clips.length} clip{clips.length !== 1 ? 's' : ''} · {fmt(clips.reduce((s, c) => s + (c.end_time - c.start_time), 0))}
        </span>
      </div>

      <div className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
        {clips.map((clip, i) => {
          const isThemeMatch = topicMatchesCategory(clip.topic, categories)

          // Match by clip_index from scene_selection_rationale
          const rationaleEntry = rationale.find(r => r.clip_index === i)
          const confidence = rationaleEntry?.confidence ?? null

          // Highlight if: this clip is selected, OR its topic matches the selected theme
          const isSelected =
            selectedClipIndex === i ||
            (selectedTopic !== null && topicMatchesCategory(clip.topic, [selectedTopic]))

          return (
            <ClipCard
              key={i}
              clip={clip}
              index={i}
              isSelected={isSelected}
              isThemeMatch={isThemeMatch}
              rationaleConfidence={confidence}
              onClick={() => onClipSelect(i, clip.topic)}
            />
          )
        })}
      </div>
    </div>
  )
}

// ── Connection indicator ──────────────────────────────────────────────────────
// Shown between the two columns when a clip is selected.
// Pure CSS transition — no JS animation library.

function ConnectionIndicator({ visible, topic }: { visible: boolean; topic: string | null }) {
  return (
    <div
      className="hidden lg:flex flex-col items-center justify-center gap-1 px-1 transition-opacity duration-300"
      style={{ opacity: visible ? 1 : 0, minWidth: 24 }}
      aria-hidden="true"
    >
      <div
        className="w-px flex-1 rounded-full transition-all duration-300"
        style={{
          background: visible
            ? 'linear-gradient(180deg, transparent, #D4A84360, #D4A843, #D4A84360, transparent)'
            : '#1E1E30',
          minHeight: 40,
        }}
      />
      {topic && visible && (
        <span
          className="text-[9px] font-semibold px-1.5 py-0.5 rounded-full text-center"
          style={{
            background: '#D4A84318',
            color: '#D4A843',
            border: '1px solid #D4A84330',
            writingMode: 'vertical-rl',
            maxHeight: 80,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {topic}
        </span>
      )}
      <div
        className="w-px flex-1 rounded-full transition-all duration-300"
        style={{
          background: visible
            ? 'linear-gradient(180deg, transparent, #D4A84360, #D4A843, #D4A84360, transparent)'
            : '#1E1E30',
          minHeight: 40,
        }}
      />
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function SentimentValidationPanel({ job }: Props) {
  const analysis = job.analysis_report
  const plan     = job.editing_plan

  // Shared interaction state
  const [selectedClipIndex, setSelectedClipIndex] = useState<number | null>(null)
  const [selectedTopic,     setSelectedTopic]     = useState<string | null>(null)

  const handleClipSelect = useCallback((index: number, topic: string) => {
    setSelectedClipIndex(prev => {
      const next = prev === index ? null : index
      // When deselecting, also clear topic
      if (next === null) setSelectedTopic(null)
      else setSelectedTopic(topic)
      return next
    })
  }, [])

  const handleThemeClick = useCallback((topic: string | null) => {
    setSelectedTopic(topic)
    // Clear clip selection when clicking a theme directly
    setSelectedClipIndex(null)
  }, [])

  // Guard: need both analysis and clips
  if (!analysis || !plan || plan.clips.length === 0) return null

  const clips      = plan.clips
  const categories = analysis.top_scene_categories ?? []

  // Match score: clips whose topic matches a top positive category
  const alignedClips = clips.filter(c => topicMatchesCategory(c.topic, categories))
  const alignedCount = alignedClips.length
  const totalCount   = clips.length

  const connectionVisible = selectedClipIndex !== null || selectedTopic !== null
  const connectionTopic   = selectedTopic ?? (selectedClipIndex !== null ? clips[selectedClipIndex]?.topic ?? null : null)

  return (
    <Card className="space-y-5" variant="gradient">

      {/* ── Panel header ── */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2
            className="text-base font-semibold"
            style={{ color: '#F0EDE8' }}
          >
            Sentiment → Output Validation
          </h2>
          <p
            className="text-xs mt-0.5"
            style={{ color: '#5C5A72' }}
          >
            How audience sentiment shaped every clip in the generated trailer
          </p>
        </div>
        {/* Dismiss selection hint */}
        {connectionVisible && (
          <button
            onClick={() => { setSelectedClipIndex(null); setSelectedTopic(null) }}
            className="text-[10px] px-2.5 py-1 rounded-lg border transition-colors"
            style={{ color: '#5C5A72', borderColor: '#252538' }}
          >
            Clear selection
          </button>
        )}
      </div>

      {/* ── Match score ── */}
      <MatchScore
        aligned={alignedCount}
        total={totalCount}
        hasCategories={categories.length > 0}
      />

      {/* ── Two-column body ── */}
      {/*
        Desktop: [left 2fr] [connector 24px] [right 3fr]
        Tablet:  same, reduced widths
        Mobile:  stacked — left then right
      */}
      <div className="flex flex-col lg:flex-row gap-6 lg:gap-0">

        {/* Left column */}
        <div className="lg:w-2/5 lg:pr-4">
          <LeftColumn
            analysis={analysis}
            clips={clips}
            selectedTopic={selectedTopic}
            onThemeClick={handleThemeClick}
          />
        </div>

        {/* Animated connection line — desktop only */}
        <ConnectionIndicator
          visible={connectionVisible}
          topic={connectionTopic}
        />

        {/* Divider — mobile only */}
        <div
          className="lg:hidden h-px w-full"
          style={{ background: '#1E1E30' }}
        />

        {/* Right column */}
        <div className="lg:flex-1 lg:pl-4 lg:border-l" style={{ borderColor: '#1E1E30' }}>
          <RightColumn
            clips={clips}
            analysis={analysis}
            selectedClipIndex={selectedClipIndex}
            selectedTopic={selectedTopic}
            onClipSelect={handleClipSelect}
          />
        </div>

      </div>

    </Card>
  )
}
