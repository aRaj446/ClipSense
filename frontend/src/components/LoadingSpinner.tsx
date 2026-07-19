interface Props {
  size?: number
  className?: string
}

export default function LoadingSpinner({ size = 24, className = '' }: Props) {
  const r = (size / 2) * 0.75
  const cx = size / 2
  const circumference = 2 * Math.PI * r

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      fill="none"
      className={`animate-spin ${className}`}
      style={{ filter: 'drop-shadow(0 0 4px #2563EB60)' }}
    >
      <defs>
        <linearGradient id="spinner-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%"   stopColor="#2563EB" stopOpacity="1" />
          <stop offset="100%" stopColor="#7C3AED" stopOpacity="0.2" />
        </linearGradient>
      </defs>
      {/* Track */}
      <circle
        cx={cx} cy={cx} r={r}
        stroke="#1C2A3F"
        strokeWidth={size * 0.12}
      />
      {/* Arc */}
      <circle
        cx={cx} cy={cx} r={r}
        stroke="url(#spinner-gradient)"
        strokeWidth={size * 0.12}
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * 0.75}
        transform={`rotate(-90 ${cx} ${cx})`}
      />
    </svg>
  )
}
