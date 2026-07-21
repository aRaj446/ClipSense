import { useEffect, useRef, useState } from 'react'
import { CheckCircle, XCircle, Loader2, Clock } from 'lucide-react'

export interface ProgressStep {
  key: string
  label: string
  status: 'pending' | 'active' | 'done' | 'failed'
  percent: number
}

interface Props {
  stage: string
  percent: number
  message: string
  steps: ProgressStep[]
}

// Smoothly animate a number from its previous value to the new target
function useAnimatedValue(target: number, duration = 600) {
  const [display, setDisplay] = useState(target)
  const raf = useRef<number>(0)
  const from = useRef(target)
  const startTs = useRef<number | null>(null)

  useEffect(() => {
    if (target === display) return
    from.current = display
    startTs.current = null
    cancelAnimationFrame(raf.current)

    function step(ts: number) {
      if (!startTs.current) startTs.current = ts
      const t = Math.min((ts - startTs.current) / duration, 1)
      const ease = 1 - Math.pow(1 - t, 3)
      setDisplay(Math.round(from.current + (target - from.current) * ease))
      if (t < 1) raf.current = requestAnimationFrame(step)
    }
    raf.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf.current)
  }, [target])

  return display
}

function StepRow({ step, index }: { step: ProgressStep; index: number }) {
  const animPct = useAnimatedValue(step.percent)
  const isActive = step.status === 'active'
  const isDone   = step.status === 'done'
  const isFailed = step.status === 'failed'
  const isPending = step.status === 'pending'

  const barColor = isFailed
    ? 'linear-gradient(90deg, #F87171, #FCA5A5)'
    : isDone
    ? 'linear-gradient(90deg, #4ADE80, #86EFAC)'
    : 'linear-gradient(90deg, #D4A843, #E8C56A, #D4A843)'

  const barStyle = isActive
    ? { width: `${animPct || 100}%`, background: barColor, backgroundSize: '200% 100%' }
    : isDone
    ? { width: '100%', background: barColor }
    : isFailed
    ? { width: '100%', background: barColor }
    : { width: '0%', background: barColor }

  return (
    <div
      className="flex items-center gap-3"
      style={{
        opacity: isPending ? 0.35 : 1,
        transform: isPending ? 'translateX(-4px)' : 'translateX(0)',
        transition: `opacity 0.4s ease ${index * 60}ms, transform 0.4s ease ${index * 60}ms`,
      }}
    >
      {/* Icon */}
      <div className="shrink-0 w-5 h-5 flex items-center justify-center">
        {isDone   && <CheckCircle size={14} style={{ color: '#4ADE80' }} />}
        {isFailed && <XCircle     size={14} style={{ color: '#F87171' }} />}
        {isActive && <Loader2     size={14} className="animate-spin" style={{ color: '#D4A843' }} />}
        {isPending && <Clock      size={12} style={{ color: '#5C5A72' }} />}
      </div>

      {/* Label + bar */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span
            className="text-xs font-medium truncate"
            style={{ color: isDone ? '#4ADE80' : isFailed ? '#F87171' : isActive ? '#F0EDE8' : '#5C5A72' }}
          >
            {step.label}
          </span>
          {(isActive || isDone) && (
            <span className="text-xs font-mono ml-2 shrink-0" style={{ color: isDone ? '#4ADE80' : '#D4A843' }}>
              {isDone ? '100' : animPct}%
            </span>
          )}
        </div>
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ background: '#1E1E30' }}
        >
          <div
            className="h-full rounded-full"
            style={{
              ...barStyle,
              transition: isActive ? 'width 0.5s ease' : isDone ? 'width 0.3s ease' : 'none',
              animation: isActive && !animPct ? 'shimmer-bar 1.8s ease-in-out infinite' : undefined,
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default function JobProgressPanel({ stage, percent, message, steps }: Props) {
  const animOverall = useAnimatedValue(percent)
  const hasSteps = steps.length > 0
  const activeStep = steps.find(s => s.status === 'active')
  const doneCount  = steps.filter(s => s.status === 'done').length

  return (
    <div
      className="rounded-2xl overflow-hidden"
      style={{
        background: 'linear-gradient(145deg, #0F0F1C, #13131F)',
        border: '1px solid #D4A84322',
        boxShadow: '0 0 32px 0 #D4A84308, inset 0 1px 0 #D4A84312',
      }}
    >
      {/* Header bar */}
      <div
        className="px-4 pt-4 pb-3"
        style={{ borderBottom: '1px solid #1E1E30' }}
      >
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Loader2 size={14} className="animate-spin shrink-0" style={{ color: '#D4A843' }} />
            <span className="text-sm font-semibold" style={{ color: '#F0EDE8' }}>
              {stage === 'done' ? 'Complete' : stage === 'failed' ? 'Failed' : 'Generating…'}
            </span>
            {hasSteps && (
              <span
                className="text-xs px-2 py-0.5 rounded-full"
                style={{ background: '#D4A84318', color: '#D4A843', border: '1px solid #D4A84328' }}
              >
                {doneCount}/{steps.length}
              </span>
            )}
          </div>
          <span className="text-xs font-mono font-semibold" style={{ color: '#D4A843' }}>
            {animOverall}%
          </span>
        </div>

        {/* Overall bar */}
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: '#1E1E30' }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${animOverall}%`,
              background: 'linear-gradient(90deg, #D4A843 0%, #E8C56A 50%, #8B7CF6 100%)',
              transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
              boxShadow: '0 0 8px 0 #D4A84360',
            }}
          />
        </div>

        {/* Active message */}
        {(message || activeStep) && (
          <p className="text-xs mt-2 truncate" style={{ color: '#5C5A72' }}>
            {message || activeStep?.label}
          </p>
        )}
      </div>

      {/* Step rows */}
      {hasSteps && (
        <div className="px-4 py-3 space-y-3">
          {steps.map((step, i) => (
            <StepRow key={step.key} step={step} index={i} />
          ))}
        </div>
      )}
    </div>
  )
}
