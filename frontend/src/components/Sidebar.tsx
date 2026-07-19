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
        {/* Background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background: 'linear-gradient(180deg, #13131F 0%, #0C0C14 100%)',
            borderRight: '1px solid #252538',
          }}
        />
        {/* Subtle gold glow at top */}
        <div
          className="absolute top-0 left-0 right-0 h-28 pointer-events-none"
          style={{ background: 'radial-gradient(ellipse at 50% 0%, #D4A84308 0%, transparent 70%)' }}
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
                        'relative flex items-center gap-3 rounded-xl',
                        'px-2.5 py-2.5 text-sm font-medium select-none',
                        'outline-none focus-visible:ring-2 focus-visible:ring-primary/50',
                        'transition-all duration-150',
                        collapsed ? 'justify-center' : '',
                        disabled
                          ? 'pointer-events-none opacity-35 text-ink-faint'
                          : isActive
                            ? 'text-ink'
                            : 'text-ink-muted hover:text-ink',
                      ].join(' ')
                    }
                  >
                    {({ isActive }: { isActive: boolean }) => (
                      <>
                        {/* Active background */}
                        {!disabled && isActive && (
                          <span
                            className="absolute inset-0 rounded-xl"
                            style={{
                              background: 'linear-gradient(135deg, #D4A84318 0%, #8B7CF610 100%)',
                              border: '1px solid #D4A84325',
                            }}
                          />
                        )}

                        {/* Hover background */}
                        {!disabled && !isActive && (
                          <span className="absolute inset-0 rounded-xl opacity-0 hover:opacity-100
                            bg-surface-raised transition-opacity duration-150" />
                        )}

                        {/* Active left indicator — gold bar */}
                        {!disabled && (
                          <span
                            className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full
                              transition-all duration-200 ease-in-out"
                            style={{
                              height: isActive ? '20px' : '0px',
                              opacity: isActive ? 1 : 0,
                              background: 'linear-gradient(180deg, #E8C56A 0%, #D4A843 100%)',
                              boxShadow: isActive ? '0 0 8px #D4A84370' : 'none',
                            }}
                          />
                        )}

                        {/* Icon */}
                        <span
                          className="relative shrink-0"
                          style={isActive ? { filter: 'drop-shadow(0 0 5px #D4A84360)' } : {}}
                        >
                          <Icon
                            size={18}
                            style={isActive ? { stroke: 'url(#nav-gradient)' } : {}}
                          />
                          {isActive && (
                            <svg width="0" height="0" className="absolute">
                              <defs>
                                <linearGradient id="nav-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                  <stop offset="0%"   stopColor="#E8C56A" />
                                  <stop offset="100%" stopColor="#D4A843" />
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
                          <span className="ml-auto text-[10px] bg-surface-raised text-ink-faint
                            px-1.5 py-0.5 rounded shrink-0 relative">
                            Soon
                          </span>
                        )}
                      </>
                    )}
                  </NavLink>
                </div>
              </Tooltip.Trigger>

              <Tooltip.Portal>
                <Tooltip.Content
                  side="right"
                  sideOffset={10}
                  hidden={!collapsed}
                  className="z-50 px-2.5 py-1.5 rounded-xl text-xs font-medium select-none
                    border shadow-glow-sm
                    data-[state=delayed-open]:animate-fade-in
                    data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
                  style={{
                    background: 'linear-gradient(135deg, #13131F 0%, #1A1A2E 100%)',
                    borderColor: '#D4A84328',
                    color: '#F0EDE8',
                  }}
                >
                  {label}
                  {disabled && <span className="ml-1.5 text-ink-faint">(Soon)</span>}
                  <Tooltip.Arrow style={{ fill: '#13131F' }} />
                </Tooltip.Content>
              </Tooltip.Portal>

            </Tooltip.Root>
          ))}
        </nav>

        {/* Bottom fade */}
        <div
          className="absolute bottom-0 left-0 right-0 h-16 pointer-events-none"
          style={{ background: 'linear-gradient(0deg, #0C0C14 0%, transparent 100%)' }}
        />
      </aside>
    </Tooltip.Provider>
  )
}
