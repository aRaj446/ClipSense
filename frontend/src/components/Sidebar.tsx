import { NavLink } from 'react-router-dom'
import * as Tooltip from '@radix-ui/react-tooltip'
import {
  LayoutDashboard, Upload, Clapperboard, Settings,
  BarChart2, Scissors,
} from 'lucide-react'

const navItems = [
  { to: '/',          label: 'Dashboard',       icon: LayoutDashboard },
  { to: '/upload',    label: 'Upload',           icon: Upload },
  { to: '/trailers',  label: 'Video Generation', icon: Clapperboard },
  { to: '/analytics', label: 'Analytics',        icon: BarChart2 },
  { to: '/scrubber',  label: 'Scrubber',         icon: Scissors },
  { to: '/settings',  label: 'Settings',         icon: Settings, disabled: true },
]

interface Props {
  collapsed: boolean
}

export default function Sidebar({ collapsed }: Props) {
  return (
    <Tooltip.Provider delayDuration={150} skipDelayDuration={0}>
      <aside
        style={{ width: collapsed ? 60 : 240 }}
        className="flex flex-col py-3 shrink-0
          transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
          will-change-[width] overflow-hidden relative"
      >
        {/* Sidebar background with subtle gradient */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(180deg, #0E1525 0%, #080D18 100%)',
            borderRight: '1px solid #1C2A3F',
          }}
        />
        {/* Subtle top glow */}
        <div
          className="absolute top-0 left-0 right-0 h-32 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at 50% 0%, #2563EB0A 0%, transparent 70%)' }}
        />

        <nav className="flex flex-col gap-0.5 px-2 mt-2 relative">
          {navItems.map(({ to, label, icon: Icon, disabled }) => (
            <Tooltip.Root key={to}>

              <Tooltip.Trigger asChild>
                <div className={disabled ? 'cursor-not-allowed' : 'cursor-pointer'}>
                  <NavLink
                    to={to}
                    end={to === '/'}
                    tabIndex={disabled ? -1 : undefined}
                    onClick={(e) => disabled && e.preventDefault()}
                    className={({ isActive }) =>
                      [
                        'relative flex items-center gap-3 rounded-lg',
                        'px-2.5 py-2.5 text-sm font-medium select-none',
                        'outline-none focus-visible:ring-2 focus-visible:ring-primary/60',
                        'transition-all duration-150',
                        collapsed ? 'justify-center' : '',
                        disabled
                          ? 'pointer-events-none opacity-40 text-slate-500'
                          : isActive
                            ? 'text-white'
                            : 'text-slate-400 hover:text-slate-100',
                      ].join(' ')
                    }
                  >
                    {({ isActive }: { isActive: boolean }) => (
                      <>
                        {/* Active background gradient */}
                        {!disabled && isActive && (
                          <span
                            className="absolute inset-0 rounded-lg"
                            style={{
                              background: 'linear-gradient(135deg, #2563EB18 0%, #7C3AED12 100%)',
                              border: '1px solid #2563EB22',
                            }}
                          />
                        )}

                        {/* Hover background */}
                        {!disabled && !isActive && (
                          <span className="absolute inset-0 rounded-lg opacity-0 hover:opacity-100
                            bg-surface-raised transition-opacity duration-150" />
                        )}

                        {/* Active left indicator — gradient bar */}
                        {!disabled && (
                          <span
                            className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full
                              transition-all duration-200 ease-in-out"
                            style={{
                              height: isActive ? '20px' : '0px',
                              opacity: isActive ? 1 : 0,
                              background: 'linear-gradient(180deg, #2563EB 0%, #7C3AED 100%)',
                              boxShadow: isActive ? '0 0 8px #2563EB80' : 'none',
                            }}
                          />
                        )}

                        {/* Icon — gradient tint when active */}
                        <span
                          className="relative shrink-0"
                          style={isActive ? {
                            filter: 'drop-shadow(0 0 6px #2563EB80)',
                          } : {}}
                        >
                          <Icon
                            size={18}
                            style={isActive ? {
                              stroke: 'url(#nav-gradient)',
                            } : {}}
                          />
                          {/* Inline SVG gradient def — rendered once per icon */}
                          {isActive && (
                            <svg width="0" height="0" className="absolute">
                              <defs>
                                <linearGradient id="nav-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                  <stop offset="0%" stopColor="#3B82F6" />
                                  <stop offset="100%" stopColor="#7C3AED" />
                                </linearGradient>
                              </defs>
                            </svg>
                          )}
                        </span>

                        {/* Label */}
                        <span
                          aria-hidden={collapsed}
                          className={`whitespace-nowrap overflow-hidden leading-none relative
                            transition-[width,opacity] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
                            ${collapsed ? 'w-0 opacity-0 pointer-events-none' : 'w-auto opacity-100'}`}
                        >
                          {label}
                        </span>

                        {/* Soon badge */}
                        {disabled && !collapsed && (
                          <span className="ml-auto text-[10px] bg-surface-raised text-slate-500
                            px-1.5 py-0.5 rounded shrink-0 relative">
                            Soon
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                </div>
              </Tooltip.Trigger>

              {/* Tooltip — only active when collapsed */}
              <Tooltip.Portal>
                <Tooltip.Content
                  side="right"
                  sideOffset={10}
                  hidden={!collapsed}
                  className="z-50 px-2.5 py-1.5 rounded-lg text-xs font-medium select-none
                    border shadow-glow-sm
                    data-[state=delayed-open]:animate-fade-in
                    data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
                  style={{
                    background: 'linear-gradient(135deg, #0E1525 0%, #141E30 100%)',
                    borderColor: '#2563EB30',
                    color: '#e2e8f0',
                  }}
                >
                  {label}
                  {disabled && <span className="ml-1.5 text-slate-500">(Soon)</span>}
                  <Tooltip.Arrow style={{ fill: '#0E1525' }} />
                </Tooltip.Content>
              </Tooltip.Portal>

            </Tooltip.Root>
          ))}
        </nav>

        {/* Bottom gradient fade */}
        <div
          className="absolute bottom-0 left-0 right-0 h-16 pointer-events-none"
          style={{ background: 'linear-gradient(0deg, #080D18 0%, transparent 100%)' }}
        />
      </aside>
    </Tooltip.Provider>
  )
}
