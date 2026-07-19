interface Props {
  percent: number
}

export default function ProgressBar({ percent }: Props) {
  return (
    <div className="w-full bg-surface rounded-full h-2 overflow-hidden">
      <div
        className="bg-primary h-2 rounded-full transition-all duration-300"
        style={{ width: `${Math.min(percent, 100)}%` }}
      />
    </div>
  )
}
