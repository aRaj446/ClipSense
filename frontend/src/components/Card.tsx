import { ReactNode } from 'react'

interface Props {
  children: ReactNode
  className?: string
}

export default function Card({ children, className = '' }: Props) {
  return (
    <div
      className={`bg-surface-card border border-surface-border rounded-xl p-6 ${className}`}
    >
      {children}
    </div>
  )
}
