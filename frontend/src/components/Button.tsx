import { ReactNode, ButtonHTMLAttributes } from 'react'
import LoadingSpinner from './LoadingSpinner'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost'
  loading?: boolean
  icon?: ReactNode
}

export default function Button({
  variant = 'primary',
  loading,
  icon,
  children,
  className = '',
  disabled,
  style,
  ...rest
}: Props) {
  const base = `inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium
    transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.97]`

  if (variant === 'primary') {
    return (
      <button
        {...rest}
        disabled={disabled || loading}
        className={`${base} ${className}`}
        style={{
          background: 'linear-gradient(135deg, #D4A843 0%, #E8C56A 100%)',
          color: '#0C0C14',
          fontWeight: 600,
          boxShadow: '0 0 14px 0 #D4A84322',
          ...style,
        }}
      >
        {loading ? <LoadingSpinner size={16} /> : icon}
        {children}
      </button>
    )
  }

  if (variant === 'danger') {
    return (
      <button
        {...rest}
        disabled={disabled || loading}
        className={`${base} bg-red-500/90 hover:bg-red-500 text-white ${className}`}
        style={style}
      >
        {loading ? <LoadingSpinner size={16} /> : icon}
        {children}
      </button>
    )
  }

  // ghost
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={`${base} bg-transparent border border-surface-border hover:border-primary/40
        hover:bg-surface-raised ${className}`}
      style={{ color: '#A8A4B8', ...style }}
    >
      {loading ? <LoadingSpinner size={16} /> : icon}
      {children}
    </button>
  )
}
