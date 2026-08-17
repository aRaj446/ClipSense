import { useState } from 'react'
import {
  Upload, Film, Users, BarChart2, Eye, Send,
  type LucideIcon,
} from 'lucide-react'
import type { SmartTrailerJob } from '../types/analysis'
import type { PipelineStep, PipelineStepStatus } from '../types/analysis'

// ── Colour tokens (never Tailwind bg-* for these) ────────────────────────────

const STATUS_COLOURS: Record<PipelineStepStatus, {
  node: string       // fill / border colour
  label: string      // text colour
  ring: string       // outer ring for active
  connector: string  // line segment colour
}> = {
  completed: { node: '#D4A843', label: '#E8C56A', ring: 'transparent',  connector: '#D4A843' },
  active:    { node: 'transparent', label: '#F0EDE8', ring: '#D4A843',  connector: '#D4A84360' },
  pending:   { node: '#252538', label: '#5C5A72',  ring: 'transparent', connector: '#252538' },
  skipped:   { node: '#1A1A2E', label: '#363654',  ring: 'transparent', connector: '#1E1E30' },
}

// ── Derive pipeline steps from a SmartTrailerJob (or null for empty state) ───

export function deriveSteps(
  job: SmartTrailerJob | null,
  navigate?: {
    toUpload: () => void
    toTrailers: () => void
    toDetails: () => void
  },
): PipelineStep[] {
  // No job at all — first step active, rest pending
  if (!job) {
    return STEP_DEFINITIONS.map((def, i) => ({
      ...def,
      status: i === 0 ? 'active' : 'pending',
      action: i === 0 ? navigate?.toUpload : undefined,
    }))
  }

  const jobStatus = job.status  // 'pending' | 'processing' | 'done' | 'failed'
  const hasSentiment = !!(job.analysis_report)
  const hasV2 = !!(job.output_url)

  // Map job lifecycle onto the 7 stages
  // Stage indices:
  //  0 Upload Raw Clips
  //  1 Generate Sample Trailer
  //  2 Internal Team Review
  //  3 Capture Sentiment
  //  4 Generate V2 Trailer
  //  5 Editor Review
  //  6 Publish

  function stageStatus(idx: number): PipelineStepStatus {
    if (jobStatus === 'failed') {
      // Everything up to the point of failure is completed; failed step is skipped
      if (idx <= 1) return 'completed'
      return 'skipped'
    }
    if (jobStatus === 'pending') {
      if (idx === 0) return 'completed'   // files uploaded
      if (idx === 1) return 'active'      // generation queued
      return 'pending'
    }
    if (jobStatus === 'processing') {
      if (idx <= 0) return 'completed'
      if (idx === 1) return 'active'      // actively generating
      return 'pending'
    }
    // done
    if (idx === 0) return 'completed'                                    // upload done
    if (idx === 1) return 'completed'                                    // generation done
    if (idx === 2) return 'completed'                                    // team review — done once job is done
    if (idx === 3) return hasSentiment ? 'completed' : 'active'         // sentiment capture — active until analytics run
    if (idx === 4) return hasV2 ? 'completed' : hasSentiment ? 'active' : 'pending'
    if (idx === 5) return hasV2 ? 'active' : 'pending'                  // editor review — active when V2 ready
    if (idx === 6) return 'pending'                                      // publish — never auto-completed
    return 'pending'
  }

  return STEP_DEFINITIONS.map((def, i) => {
    const status = stageStatus(i)
    let action: (() => void) | undefined
    if (i === 0 && navigate) action = navigate.toUpload
    if (i === 1 && navigate && (jobStatus === 'done' || jobStatus === 'processing')) action = navigate.toDetails
    if (i === 4 && navigate && hasV2) action = navigate.toDetails
    if (i === 5 && navigate && hasV2) action = navigate.toDetails

    // Only attach real timestamps — never fabricate
    let timestamp: string | undefined
    if (i === 0) timestamp = job.created_at
    if (i === 4 && hasV2) timestamp = job.updated_at

    return { ...def, status, action, timestamp }
  })
}

// ── Static step definitions (no status — derived at runtime) ─────────────────

const STEP_DEFINITIONS: Omit<PipelineStep, 'status'>[] = [
  {
    id: 'upload',
    title: 'Upload Raw Clips',
    description: 'Editor uploads long-form raw footage, a sample trailer, and audience comments.',
    icon: 'Upload',
  },
  {
    id: 'sample-trailer',
    title: 'Generate Sample Trailer',
    description: 'ClipSense analyses the sample trailer\'s editing style and audience sentiment to plan clips.',
    icon: 'Film',
  },
  {
    id: 'team-review',
    title: 'Internal Team Review',
    description: 'Internal stakeholders review the analysis report and sentiment breakdown.',
    icon: 'Users',
  },
  {
    id: 'sentiment',
    title: 'Capture Sentiment',
    description: 'Audience comments are structured into sentiment segments with topic and timestamp.',
    icon: 'BarChart2',
  },
  {
    id: 'v2-trailer',
    title: 'Generate V2 Trailer',
    description: 'Sentiment-informed clip planning selects and composes the optimised V2 trailer.',
    icon: 'Film',
  },
  {
    id: 'editor-review',
    title: 'Editor Review',
    description: 'Editor inspects clip-by-clip sentiment alignment and optionally regenerates with a prompt.',
    icon: 'Eye',
  },
  {
    id: 'publish',
    title: 'Publish',
    description: 'Approved trailer is published. Audience sentiment from V2 feeds the next iteration.',
    icon: 'Send',
  },
]

// ── Icon resolver ─────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, LucideIcon> = {
  Upload, Film, Users, BarChart2, Eye, Send,
}

function StepIcon({ name, size, color }: { name: string; size: number; color: string }) {
  const Icon = ICON_MAP[name] ?? Film
  return <Icon size={size} color={color} />
}

// ── Node ──────────────────────────────────────────────────────────────────────

function StepNode({
  step,
  index,
  isLast,
  layout,
}: {
  step: PipelineStep
  index: number
  isLast: boolean
  layout: 'horizontal' | 'vertical'
}) {
  const [hovered, setHovered] = useState(false)
  const c = STATUS_COLOURS[step.status]
  const isActive    = step.status === 'active'
  const isCompleted = step.status === 'completed'
  const isClickable = !!step.action

  const nodeSize = 36

  // ── Node circle ──
  const nodeEl = (
    <div
      className="relative flex items-center justify-center shrink-0"
      style={{ width: nodeSize, height: nodeSize }}
    >
      {/* Pulse ring — active only */}
      {isActive && (
        <div
          className="absolute inset-0 rounded-full"
          style={{
            border: `2px solid ${c.ring}`,
            animation: 'pipeline-pulse 2s ease-in-out infinite',
            transform: 'scale(1.35)',
          }}
        />
      )}
      {/* Main circle */}
      <div
        className="relative z-10 rounded-full flex items-center justify-center transition-all duration-200"
        style={{
          width: nodeSize,
          height: nodeSize,
          background: isActive
            ? 'linear-gradient(135deg, #1A1A2E, #13131F)'
            : isCompleted
              ? `linear-gradient(135deg, ${c.node}, #C49535)`
              : c.node,
          border: isActive
            ? `2px solid ${c.ring}`
            : isCompleted
              ? 'none'
              : `2px solid #363654`,
          boxShadow: isActive
            ? `0 0 16px 0 #D4A84340`
            : isCompleted
              ? `0 0 12px 0 #D4A84328`
              : 'none',
          transform: hovered && isClickable ? 'scale(1.1)' : 'scale(1)',
        }}
      >
        <StepIcon
          name={step.icon}
          size={15}
          color={
            isCompleted ? '#0C0C14'
            : isActive   ? '#D4A843'
            : '#363654'
          }
        />
      </div>

      {/* Step number badge */}
      <div
        className="absolute -top-1 -right-1 z-20 rounded-full flex items-center justify-center"
        style={{
          width: 14,
          height: 14,
          background: isCompleted ? '#D4A843' : isActive ? '#1A1A2E' : '#1A1A2E',
          border: `1px solid ${isCompleted ? '#D4A843' : isActive ? '#D4A84360' : '#363654'}`,
          fontSize: 8,
          fontWeight: 700,
          color: isCompleted ? '#0C0C14' : isActive ? '#D4A843' : '#5C5A72',
        }}
      >
        {index + 1}
      </div>
    </div>
  )

  // ── Tooltip ──
  const tooltip = hovered && (
    <div
      className="absolute z-50 pointer-events-none"
      style={
        layout === 'horizontal'
          ? { bottom: 'calc(100% + 10px)', left: '50%', transform: 'translateX(-50%)', minWidth: 180, maxWidth: 220 }
          : { left: 'calc(100% + 12px)', top: '50%', transform: 'translateY(-50%)', minWidth: 200, maxWidth: 260 }
      }
    >
      <div
        className="rounded-xl px-3 py-2.5 text-left"
        style={{
          background: '#13131F',
          border: '1px solid #252538',
          boxShadow: '0 8px 32px 0 #00000080',
        }}
      >
        <p className="text-xs font-semibold mb-1" style={{ color: c.label }}>{step.title}</p>
        <p className="text-xs leading-relaxed" style={{ color: '#A8A4B8' }}>{step.description}</p>
        {step.timestamp && (
          <p className="text-[10px] mt-1.5" style={{ color: '#5C5A72' }}>
            {new Date(step.timestamp).toLocaleString()}
          </p>
        )}
        <p className="text-[10px] mt-1 font-medium uppercase tracking-wide" style={{ color: c.label }}>
          {step.status}
          {isClickable && ' · click to open'}
        </p>
      </div>
      {/* Arrow */}
      {layout === 'horizontal' && (
        <div
          className="absolute left-1/2 -translate-x-1/2"
          style={{
            bottom: -5,
            width: 0,
            height: 0,
            borderLeft: '5px solid transparent',
            borderRight: '5px solid transparent',
            borderTop: '5px solid #252538',
          }}
        />
      )}
    </div>
  )

  // ── Label (below node on horizontal, right of node on vertical) ──
  const label = (
    <p
      className="text-center font-medium transition-colors duration-150"
      style={{
        fontSize: 11,
        color: hovered ? c.label : isCompleted ? '#A8A4B8' : isActive ? '#F0EDE8' : '#5C5A72',
        maxWidth: layout === 'horizontal' ? 80 : undefined,
        lineHeight: 1.3,
      }}
    >
      {step.title}
    </p>
  )

  if (layout === 'horizontal') {
    return (
      <div className="flex flex-col items-center gap-2 relative">
        <div
          className="relative flex flex-col items-center gap-2"
          style={{ cursor: isClickable ? 'pointer' : 'default' }}
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          onClick={() => step.action?.()}
        >
          {tooltip}
          {nodeEl}
          {label}
        </div>
      </div>
    )
  }

  // Vertical layout
  return (
    <div className="flex items-start gap-4 relative">
      <div
        className="relative flex flex-col items-center"
        style={{ cursor: isClickable ? 'pointer' : 'default' }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={() => step.action?.()}
      >
        {tooltip}
        {nodeEl}
        {/* Vertical connector below node */}
        {!isLast && (
          <div
            style={{
              width: 2,
              height: 40,
              marginTop: 4,
              background: c.connector,
              borderRadius: 1,
              flexShrink: 0,
            }}
          />
        )}
      </div>
      <div
        className="pt-1.5 pb-2"
        style={{ cursor: isClickable ? 'pointer' : 'default' }}
        onClick={() => step.action?.()}
      >
        <p className="text-sm font-medium" style={{ color: isActive ? '#F0EDE8' : isCompleted ? '#A8A4B8' : '#5C5A72' }}>
          {step.title}
        </p>
        <p className="text-xs mt-0.5 leading-relaxed" style={{ color: '#5C5A72' }}>
          {step.description}
        </p>
        {step.timestamp && (
          <p className="text-[10px] mt-1" style={{ color: '#363654' }}>
            {new Date(step.timestamp).toLocaleString()}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Horizontal connector between two nodes ────────────────────────────────────

function HorizontalConnector({
  fromStatus,
  toStatus,
}: {
  fromStatus: PipelineStepStatus
  toStatus: PipelineStepStatus
}) {
  const isLit = fromStatus === 'completed'
  const toActive = toStatus === 'active'

  return (
    <div
      className="flex-1 relative"
      style={{ height: 36, display: 'flex', alignItems: 'center', minWidth: 16 }}
    >
      <div
        className="w-full"
        style={{
          height: 2,
          borderRadius: 1,
          background: isLit && toActive
            ? 'linear-gradient(90deg, #D4A843, #D4A84340)'
            : isLit
              ? '#D4A843'
              : '#252538',
          // Animated gradient only on the connector leading into the active node
          ...(isLit && toActive ? {
            backgroundSize: '200% 100%',
            animation: 'pipeline-connector-flow 2s linear infinite',
          } : {}),
        }}
      />
    </div>
  )
}

// ── PipelineDiagram ───────────────────────────────────────────────────────────

interface Props {
  steps?: PipelineStep[]   // pre-derived steps; if omitted, renders empty-state
}

export default function PipelineDiagram({ steps }: Props) {
  const resolvedSteps = steps ?? deriveSteps(null)

  return (
    <>
      {/* Keyframes injected once via a style tag */}
      <style>{`
        @keyframes pipeline-pulse {
          0%, 100% { opacity: 0.6; transform: scale(1.35); }
          50%       { opacity: 1;   transform: scale(1.55); }
        }
        @keyframes pipeline-connector-flow {
          0%   { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>

      <div
        className="rounded-2xl p-5 border"
        style={{
          background: 'linear-gradient(145deg, #13131F, #1A1A2E)',
          borderColor: '#252538',
          boxShadow: '0 2px 20px 0 #00000055',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="font-semibold text-sm" style={{ color: '#F0EDE8' }}>
              ClipSense Workflow
            </h3>
            <p className="text-xs mt-0.5" style={{ color: '#5C5A72' }}>
              End-to-end feedback loop
            </p>
          </div>
          {/* Legend */}
          <div className="hidden sm:flex items-center gap-3">
            {(['completed', 'active', 'pending'] as PipelineStepStatus[]).map(s => (
              <div key={s} className="flex items-center gap-1.5">
                <div
                  className="rounded-full"
                  style={{
                    width: 8,
                    height: 8,
                    background: s === 'completed' ? '#D4A843' : s === 'active' ? 'transparent' : '#252538',
                    border: s === 'active' ? '2px solid #D4A843' : 'none',
                  }}
                />
                <span className="text-[10px] capitalize" style={{ color: '#5C5A72' }}>{s}</span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Desktop / Tablet: horizontal ── */}
        {/* Hidden on mobile (< md), shown md+ */}
        <div className="hidden md:flex items-start">
          {resolvedSteps.map((step, i) => (
            <div key={step.id} className="flex items-center flex-1 min-w-0">
              <StepNode
                step={step}
                index={i}
                isLast={i === resolvedSteps.length - 1}
                layout="horizontal"
              />
              {i < resolvedSteps.length - 1 && (
                <HorizontalConnector
                  fromStatus={step.status}
                  toStatus={resolvedSteps[i + 1].status}
                />
              )}
            </div>
          ))}
        </div>

        {/* ── Mobile: vertical timeline ── */}
        <div className="flex flex-col md:hidden">
          {resolvedSteps.map((step, i) => (
            <StepNode
              key={step.id}
              step={step}
              index={i}
              isLast={i === resolvedSteps.length - 1}
              layout="vertical"
            />
          ))}
        </div>
      </div>
    </>
  )
}
