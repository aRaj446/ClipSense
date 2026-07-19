import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

interface Props {
  open: boolean
  title: string
  onClose: () => void
  children: ReactNode
}

export default function Modal({ open, title, onClose, children }: Props) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-md"
        style={{ background: 'radial-gradient(ellipse at center, #2563EB0A 0%, #00000070 100%)' }}
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative bg-surface-card border border-surface-border rounded-2xl p-6 w-full max-w-md shadow-glow-sm animate-scale-in">
        {/* Glow accent line at top */}
        <div
          className="absolute top-0 left-8 right-8 h-px rounded-full"
          style={{ background: 'linear-gradient(90deg, transparent, #2563EB60, #7C3AED60, transparent)' }}
        />

        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-semibold text-slate-100">{title}</h2>
          <button
            onClick={onClose}
            className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400
              hover:text-slate-100 hover:bg-surface-raised transition-all duration-150"
          >
            <X size={16} />
          </button>
        </div>

        {children}
      </div>
    </div>
  )
}
