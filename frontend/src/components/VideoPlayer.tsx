interface Props {
  src: string
  className?: string
}

export default function VideoPlayer({ src, className = '' }: Props) {
  return (
    <video
      src={src}
      controls
      className={`w-full rounded-lg bg-black ${className}`}
      preload="metadata"
    >
      Your browser does not support the video tag.
    </video>
  )
}
