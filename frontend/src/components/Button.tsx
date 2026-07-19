import { ReactNode, ButtonHTMLAttributes } from 'react'
import LoadingSpinner from './LoadingSpinner'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'danger' | 'ghost'
  loading?: boolean
  icon?: ReactNode
}

const variants = {
  primary: 'bg-primary hover:bg-primary-hover text-white',
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  ghost: 'bg-transparent border border-surface-border hover:bg-surface-card text-slate-300',
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
        transition-colors disabled:opacity-50 disabled:cursor-not-allowed
        ${variants[variant]} ${className}`}
    >
      {loading ? <LoadingSpinner size={16} /> : icon}
      {children}
    </button>
  )
}
