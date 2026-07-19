import { ReactNode, CSSProperties } from 'react'

interface Props {
  children: ReactNode
  className?: string
  variant?: 'default' | 'glow' | 'gradient'
  animate?: boolean
  style?: CSSProperties
}

export default function Card({ children, className = '', variant = 'default', animate = false, style }: Props) {
  const base = 'border rounded-2xl p-6 transition-all duration-200'

  const variants = {
    default:  'bg-surface-card border-surface-border hover:border-surface-muted/70 shadow-card',
    glow:     'bg-surface-card border-surface-border hover:border-primary/35 hover:shadow-glow-sm shadow-card',
    gradient: 'bg-gradient-card border-surface-border hover:border-primary/25 shadow-card',
  }

  return (
    <div className={`${base} ${variants[variant]} ${animate ? 'animate-fade-in' : ''} ${className}`} style={style}>
      {children}
    </div>
  )
}
