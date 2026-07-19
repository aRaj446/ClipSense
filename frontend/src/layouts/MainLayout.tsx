import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { Menu, Zap } from 'lucide-react'
import Sidebar from '../components/Sidebar'

const STORAGE_KEY = 'sidebar:collapsed'

function readInitial(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState<boolean>(readInitial)

  function toggle() {
    setCollapsed(prev => {
      const next = !prev
      try { localStorage.setItem(STORAGE_KEY, String(next)) } catch { /* ignore */ }
      return next
    })
  }

  return (
    <div className="min-h-screen flex flex-col bg-surface">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="h-16 flex items-center px-4 gap-3 sticky top-0 z-30 shrink-0
        bg-surface/80 backdrop-blur-xl"
        style={{
          borderBottom: '1px solid transparent',
          backgroundImage:
            'linear-gradient(#080D18CC, #080D18CC), linear-gradient(90deg, #2563EB30, #7C3AED20, transparent)',
          backgroundOrigin: 'border-box',
          backgroundClip: 'padding-box, border-box',
        }}
      >
        {/* Hamburger */}
        <button
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0
            text-slate-400 hover:text-slate-100 hover:bg-surface-raised
            transition-all duration-150 focus-visible:outline-none
            focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          <Menu size={18} />
        </button>

        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div
            className="p-1.5 rounded-lg shadow-glow-sm"
            style={{ background: 'linear-gradient(135deg, #2563EB 0%, #7C3AED 100%)' }}
          >
            <Zap size={16} className="text-white" />
          </div>
          <span
            className="font-bold text-lg tracking-tight bg-clip-text text-transparent"
            style={{ backgroundImage: 'linear-gradient(135deg, #e2e8f0 0%, #94a3b8 100%)' }}
          >
            ClipSense
          </span>
          <span
            className="text-[10px] font-medium px-1.5 py-0.5 rounded-full"
            style={{
              background: 'linear-gradient(135deg, #2563EB18, #7C3AED18)',
              border: '1px solid #2563EB30',
              color: '#7C3AED',
            }}
          >
            AI
          </span>
        </div>

        {/* Right side — subtle divider + version */}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-slate-600 hidden sm:inline">v1.0</span>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-green shadow-[0_0_6px_#10B981]" />
            <span className="text-xs text-slate-500 hidden sm:inline">Live</span>
          </div>
        </div>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar collapsed={collapsed} />
        <main className="flex-1 overflow-y-auto p-8 transition-all duration-300 animate-fade-in">
          <Outlet />
        </main>
      </div>

    </div>
  )
}
