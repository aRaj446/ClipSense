export default function Navbar() {
  return (
    <header className="h-16 border-b border-surface-border bg-surface-card/50 backdrop-blur-sm
      flex items-center px-6 gap-3 sticky top-0 z-30">
      <div className="flex items-center gap-2">
        <span className="font-bold text-slate-100 text-lg tracking-tight">ClipSense</span>
      </div>
      <span className="ml-2 text-xs text-slate-500 bg-surface-border px-2 py-0.5 rounded-full">
        Week 1 — Foundation
      </span>
    </header>
  )
}
