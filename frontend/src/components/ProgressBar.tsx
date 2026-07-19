interface Props {
  percent: number
}

export default function ProgressBar({ percent }: Props) {
  const clamped = Math.min(Math.max(percent, 0), 100)
  return (
    <div className="w-full bg-surface-raised rounded-full h-1.5 overflow-hidden">
      <div
        className="h-1.5 rounded-full transition-all duration-300 relative overflow-hidden"
        style={{
          width: `${clamped}%`,
          background: 'linear-gradient(90deg, #D4A843 0%, #E8C56A 60%, #8B7CF6 100%)',
        }}
      >
        <span
          className="absolute inset-0 animate-shimmer"
          style={{
            background: 'linear-gradient(90deg, transparent 0%, #ffffff20 50%, transparent 100%)',
            backgroundSize: '200% 100%',
          }}
        />
      </div>
    </div>
  )
}
