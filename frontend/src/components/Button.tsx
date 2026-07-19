import { ReactNode, ButtonHTMLAttributes } from 'react'
import LoadingSpinner from './LoadingSpinner'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost'
  loading?: boolean
  icon?: ReactNode
}

const variants = {
  primary: 'bg-gradient-primary hover:opacity-90 text-white shadow-glow-sm hover:shadow-glow-md active:scale-[0.97]',
  danger:  'bg-red-600 hover:bg-red-500 text-white active:scale-[0.97]',
  ghost:   'bg-transparent border border-surface-border hover:border-primary/40 hover:bg-surface-raised hover:shadow-glow-sm text-slate-300 active:scale-[0.97]',
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
      className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
        transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${className}`}
    >
      {loading ? <LoadingSpinner size={16} /> : icon}
      {children}
    </button>
  )
}
