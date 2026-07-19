import { ReactNode, ButtonHTMLAttributes } from 'react'
import LoadingSpinner from './LoadingSpinner'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost'
  loading?: boolean
  icon?: ReactNode
}

const variants = {
  primary: 'bg-gradient-gold text-[#0C0C14] font-semibold shadow-glow-sm hover:shadow-glow-md hover:opacity-92 active:scale-[0.97]',
  danger:  'bg-red-500/90 hover:bg-red-500 text-white active:scale-[0.97]',
  ghost:   'bg-transparent border border-surface-border hover:border-primary/40 hover:bg-surface-raised text-ink-muted hover:text-ink active:scale-[0.97]',
}

export default function Button({
  variant = 'primary',
  loading,
  icon,
  children,
  className = '',
  disabled,
  ...rest
}: Props) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm
        transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${className}`}
    >
      {loading ? <LoadingSpinner size={16} /> : icon}
      {children}
    </button>
  )
}
