interface Props {
  percent: number
}

export default function ProgressBar({ percent }: Props) {
  const clamped = Math.min(Math.max(percent, 0), 100)
  return (
    <div className="w-full bg-surface-raised rounded-full h-2 overflow-hidden">
      <div
        className="h-2 rounded-full transition-all duration-300 relative overflow-hidden"
        style={{
          width: `${clamped}%`,
          background: 'linear-gradient(90deg, #2563EB 0%, #7C3AED 100%)',
        }}
      >
        {/* shimmer sweep */}
        <span
          className="absolute inset-0 animate-shimmer"
          style={{
            background: 'linear-gradient(90deg, transparent 0%, #ffffff18 50%, transparent 100%)',
            backgroundSize: '200% 100%',
          }}
        />
      </div>
    </div>
  )
}
