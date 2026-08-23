interface Props {
  /** currentTime as a percentage of total duration (0–100). */
  pct: number
}

export default function Playhead({ pct }: Props) {
  return (
    <div
      className="absolute top-0 bottom-0 z-20 pointer-events-none"
      style={{ left: `${pct}%` }}
    >
      {/* Needle */}
      <div
        className="absolute top-0 bottom-0 w-px"
        style={{ background: '#D4A843', boxShadow: '0 0 3px #D4A84388' }}
      />
      {/* Triangle head */}
      <div
        className="absolute -top-px -translate-x-1/2"
        style={{
          width: 0,
          height: 0,
          borderLeft: '5px solid transparent',
          borderRight: '5px solid transparent',
          borderTop: '7px solid #D4A843',
          filter: 'drop-shadow(0 0 3px #D4A84388)',
        }}
      />
    </div>
  )
}
