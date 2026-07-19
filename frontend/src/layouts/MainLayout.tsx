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
      <header className="h-16 border-b border-surface-border bg-surface-card/50 backdrop-blur-sm
        flex items-center px-4 gap-3 sticky top-0 z-30 shrink-0">

        {/* Hamburger */}
        <button
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className="flex items-center justify-center w-9 h-9 rounded-lg
            text-slate-400 hover:text-slate-100 hover:bg-surface
            transition-colors duration-150 shrink-0 focus-visible:outline-none
            focus-visible:ring-2 focus-visible:ring-primary/60"
        >
          <Menu size={18} />
        </button>

        {/* Logo */}
        <div className="flex items-center gap-2">
          <div className="p-1.5 bg-primary rounded-lg">
            <Zap size={16} className="text-white" />
          </div>
          <span className="font-bold text-slate-100 text-lg tracking-tight">ClipSense</span>
        </div>

        <span className="ml-2 text-xs text-slate-500 bg-surface-border px-2 py-0.5 rounded-full">
          Week 1 — Foundation
        </span>
      </header>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        <Sidebar collapsed={collapsed} />
        <main className="flex-1 overflow-y-auto p-8 transition-all duration-300">
          <Outlet />
        </main>
      </div>

    </div>
  )
}
