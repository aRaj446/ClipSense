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
      <header
        className="h-16 flex items-center px-4 gap-3 sticky top-0 z-30 shrink-0"
        style={{
          background: 'rgba(12, 12, 20, 0.85)',
          backdropFilter: 'blur(20px)',
          borderBottom: '1px solid #252538',
          boxShadow: '0 1px 0 0 #D4A84310',
        }}
      >
        {/* Hamburger */}
        <button
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex items-center justify-center w-9 h-9 rounded-xl shrink-0
            text-ink-faint hover:text-ink hover:bg-surface-raised
            transition-all duration-150 focus-visible:outline-none
            focus-visible:ring-2 focus-visible:ring-primary/50"
        >
          <Menu size={18} />
        </button>

        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div
            className="p-1.5 rounded-lg shadow-glow-sm"
            style={{ background: 'linear-gradient(135deg, #D4A843 0%, #E8C56A 100%)' }}
          >
            <Zap size={16} className="text-[#0C0C14]" />
          </div>
          <span
            className="font-bold text-lg tracking-tight bg-clip-text text-transparent"
            style={{ backgroundImage: 'linear-gradient(135deg, #F0EDE8 0%, #A8A4B8 100%)' }}
          >
            ClipSense
          </span>
          <span
            className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full tracking-wide"
            style={{
              background: 'linear-gradient(135deg, #D4A84320, #8B7CF618)',
              border: '1px solid #D4A84328',
              color: '#D4A843',
            }}
          >
            Studio
          </span>
        </div>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-3">
          <span className="text-xs text-ink-faint hidden sm:inline">v1.0</span>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-green" style={{ boxShadow: '0 0 6px #4ADE80' }} />
            <span className="text-xs text-ink-faint hidden sm:inline">Live</span>
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
