import { useRef, useState, useCallback, useEffect } from 'react'
import { Play, Pause, GitCompare, TrendingUp, Clock, Layers } from 'lucide-react'
import { SmartTrailerJob } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import Card from './Card'

interface Props {
  job: SmartTrailerJob
}

const SENTIMENT_POS = new Set(['Positive', 'Praise'])
const SENTIMENT_NEG = new Set(['Negative', 'Complaint'])

function fmt(secs: number) {
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function VideoPane({
  src,
  label,
  badge,
  badgeColor,
  videoRef,
  onTimeUpdate,
  controls,
}: {
  src: string
  label: string
  badge: string
  badgeColor: string
  videoRef: React.RefObject<HTMLVideoElement | null>
  onTimeUpdate?: () => void
  controls?: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold" style={{ color: '#F0EDE8' }}>
          {label}
        </span>
        <span
          className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
          style={{
            background: `${badgeColor}18`,
            color: badgeColor,
            border: `1px solid ${badgeColor}30`,
          }}
        >
          {badge}
        </span>
      </div>
      <video
        ref={videoRef as React.RefObject<HTMLVideoElement>}
        src={src}
        className="w-full rounded-xl object-contain bg-black"
        style={{ maxHeight: 280, border: '1px solid #1E1E30' }}
        preload="metadata"
        controls={controls}
        muted={!controls}
        playsInline
        onTimeUpdate={onTimeUpdate}
      />
    </div>
  )
}

export default function TrailerComparisonPanel({ job }: Props) {
  const v1Ref = useRef<HTMLVideoElement | null>(null)
  const v2Ref = useRef<HTMLVideoElement | null>(null)
  const timelineRef = useRef<HTMLDivElement | null>(null)

  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [synced, setSynced] = useState(true)

  const v2Url = job.output_url ? smartTrailerService.resolveUrl(job.output_url) : null
  const v1Url = job.sample_trailer_url
    ? smartTrailerService.resolveUrl(job.sample_trailer_url)
    : null

  // Duration comes from the editing plan (V2 is the generated one)
  const v2Duration = job.editing_plan
    ? job.editing_plan.clips.reduce((s, c) => s + (c.end_time - c.start_time), 0)
    : 0

  const togglePlay = useCallback(() => {
    setPlaying(p => {
      const next = !p
      if (synced) {
        ;[v1Ref.current, v2Ref.current].forEach(v => {
          if (!v) return
          next ? v.play().catch(() => {}) : v.pause()
        })
      } else {
        const v = v2Ref.current
        if (v) next ? v.play().catch(() => {}) : v.pause()
      }
      return next
    })
  }, [synced])

  const seekTo = useCallback(
    (t: number) => {
      setCurrentTime(t)
      if (synced) {
        ;[v1Ref.current, v2Ref.current].forEach(v => {
          if (v) v.currentTime = t
        })
      } else {
        if (v2Ref.current) v2Ref.current.currentTime = t
      }
    },
    [synced],
  )

  // Sync currentTime display from V2 (the generated trailer drives the scrubber)
  const handleV2TimeUpdate = useCallback(() => {
    if (v2Ref.current) setCurrentTime(v2Ref.current.currentTime)
  }, [])

  // Stop playing state when video ends
  useEffect(() => {
    const v = v2Ref.current
    if (!v) return
    const onEnded = () => setPlaying(false)
    v.addEventListener('ended', onEnded)
    return () => v.removeEventListener('ended', onEnded)
  }, [v2Url])

  if (!v2Url) return null

  // Clip sentiment strip for V2
  const clips = job.editing_plan?.clips ?? []
  const totalDur = clips.reduce((s, c) => s + (c.end_time - c.start_time), 0)

  // Key differences derived from analysis_report
  const analysis = job.analysis_report
  const posPatterns = analysis?.positive_patterns?.slice(0, 2) ?? []
  const negAvoided = analysis?.negative_patterns?.slice(0, 2) ?? []
  const topCategories = analysis?.top_scene_categories?.slice(0, 3) ?? []

  return (
    <Card className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2">
        <GitCompare size={15} style={{ color: '#D4A843' }} />
        <div>
          <h3 className="font-semibold" style={{ color: '#F0EDE8' }}>
            Original vs ClipSense
          </h3>
          <p className="text-xs" style={{ color: '#5C5A72' }}>
            Compare the baseline trailer with AI-selected versions.
          </p>
        </div>
        {/* Sync toggle */}
        <button
          onClick={() => setSynced(s => !s)}
          className="ml-auto text-[10px] font-medium px-2.5 py-1 rounded-lg border transition-colors"
          style={{
            background: synced ? '#D4A84315' : 'transparent',
            color: synced ? '#D4A843' : '#5C5A72',
            borderColor: synced ? '#D4A84330' : '#252538',
          }}
        >
          {synced ? 'Synced playback' : 'Independent'}
        </button>
      </div>

      {/* Video grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {v1Url ? (
          <VideoPane
            src={v1Url}
            label={job.sample_trailer_name}
            badge="V1 · Original"
            badgeColor="#A8A4B8"
            videoRef={v1Ref}
            controls={!synced}
          />
        ) : (
          <div
            className="flex flex-col items-center justify-center rounded-xl aspect-video"
            style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}
          >
            <Layers size={24} style={{ color: '#252538' }} />
            <p className="text-xs mt-2" style={{ color: '#5C5A72' }}>
              Original sample not available
            </p>
          </div>
        )}
        <VideoPane
          src={v2Url}
          label={job.raw_footage_name}
          badge="V2 · AI Generated"
          badgeColor="#D4A843"
          videoRef={v2Ref}
          onTimeUpdate={synced ? handleV2TimeUpdate : undefined}
          controls={!synced}
        />
      </div>

      {/* Shared playback controls — synced mode only */}
      {synced && <div className="flex items-center gap-3">
        <button
          onClick={togglePlay}
          className="flex items-center justify-center w-8 h-8 rounded-full shrink-0 transition-colors"
          style={{ background: '#D4A843', color: '#0C0C14' }}
        >
          {playing ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <span
          className="text-xs font-mono shrink-0 w-10 text-right"
          style={{ color: '#A8A4B8' }}
        >
          {fmt(Math.round(currentTime))}
        </span>
        {/* Scrubber */}
        <div
          ref={timelineRef}
          className="relative flex-1 h-5 flex items-center cursor-pointer select-none"
          onMouseDown={e => {
            const el = timelineRef.current
            if (!el || v2Duration <= 0) return
            const seek = (ev: MouseEvent) => {
              const rect = el.getBoundingClientRect()
              const ratio = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width))
              seekTo(ratio * v2Duration)
            }
            seek(e.nativeEvent)
            const onUp = () => {
              window.removeEventListener('mousemove', seek)
              window.removeEventListener('mouseup', onUp)
            }
            window.addEventListener('mousemove', seek)
            window.addEventListener('mouseup', onUp)
          }}
        >
          <div className="absolute inset-x-0 h-1.5 rounded-full" style={{ background: '#1E1E30' }} />
          <div
            className="absolute h-1.5 rounded-full"
            style={{
              width: `${v2Duration > 0 ? (currentTime / v2Duration) * 100 : 0}%`,
              background: '#D4A843',
            }}
          />
          <div
            className="absolute w-3.5 h-3.5 rounded-full border-2 shadow -translate-x-1/2"
            style={{
              left: `${v2Duration > 0 ? (currentTime / v2Duration) * 100 : 0}%`,
              background: '#fff',
              borderColor: '#D4A843',
            }}
          />
        </div>
        <span className="text-xs font-mono shrink-0 w-10" style={{ color: '#5C5A72' }}>
          {fmt(Math.round(v2Duration))}
        </span>
      </div>}

      {/* V2 clip sentiment strip */}
      {clips.length > 0 && totalDur > 0 && (
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-wide mb-1.5" style={{ color: '#5C5A72' }}>
            {clips.some(c => SENTIMENT_POS.has(c.sentiment))
              ? 'AI version prioritizes audience-positive segments'
              : 'Audience sentiment by timeline'}
          </p>
          <div className="flex h-2 rounded-full overflow-hidden gap-px">
            {clips.map((c, i) => {
              const w = ((c.end_time - c.start_time) / totalDur) * 100
              const bg = SENTIMENT_POS.has(c.sentiment)
                ? '#D4A843'
                : SENTIMENT_NEG.has(c.sentiment)
                ? '#F87171'
                : '#A8A4B8'
              return (
                <div
                  key={i}
                  className="h-full"
                  style={{ width: `${w}%`, background: bg, minWidth: 2 }}
                  title={`${c.topic} · ${c.sentiment} · ${fmt(c.end_time - c.start_time)}`}
                />
              )
            })}
          </div>
          <div className="flex gap-4 mt-1.5">
            {[
              { label: 'Positive', color: '#D4A843' },
              { label: 'Neutral', color: '#A8A4B8' },
              { label: 'Negative', color: '#F87171' },
            ].map(s => (
              <span key={s.label} className="flex items-center gap-1 text-[10px]" style={{ color: '#5C5A72' }}>
                <span className="w-2 h-2 rounded-full inline-block" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* What changed — derived from analysis */}
      {(posPatterns.length > 0 || negAvoided.length > 0 || topCategories.length > 0) && (
        <div
          className="rounded-xl px-4 py-3 grid grid-cols-1 sm:grid-cols-3 gap-4"
          style={{ background: '#0E0E1A', border: '1px solid #1E1E30' }}
        >
          {posPatterns.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide flex items-center gap-1" style={{ color: '#4ADE80' }}>
                <TrendingUp size={9} /> Emphasised in V2
              </p>
              {posPatterns.map((p, i) => (
                <p key={i} className="text-xs" style={{ color: '#A8A4B8' }}>
                  + {p}
                </p>
              ))}
            </div>
          )}
          {negAvoided.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide" style={{ color: '#F87171' }}>
                Reduced in V2
              </p>
              {negAvoided.map((p, i) => (
                <p key={i} className="text-xs" style={{ color: '#A8A4B8' }}>
                  − {p}
                </p>
              ))}
            </div>
          )}
          {topCategories.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] font-semibold uppercase tracking-wide flex items-center gap-1" style={{ color: '#D4A843' }}>
                <Clock size={9} /> Top scene types
              </p>
              <div className="flex flex-wrap gap-1">
                {topCategories.map((cat, i) => (
                  <span
                    key={i}
                    className="text-[10px] px-2 py-0.5 rounded-full"
                    style={{ background: '#D4A84318', color: '#D4A843', border: '1px solid #D4A84330' }}
                  >
                    {cat}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Card>
  )
}
