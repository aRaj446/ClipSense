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
        className="bg-surface-card border-r border-surface-border flex flex-col py-3 shrink-0
          transition-[width] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
          will-change-[width] overflow-hidden"
      >
        <nav className="flex flex-col gap-0.5 px-2 mt-2">
          {navItems.map(({ to, label, icon: Icon, disabled }) => (
            <Tooltip.Root key={to}>

              {/* Trigger wraps a plain div so Radix never touches NavLink cursor */}
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
                        'transition-colors duration-150',
                        collapsed ? 'justify-center' : '',
                        disabled
                          ? 'pointer-events-none opacity-40 text-slate-500'
                          : isActive
                            ? 'bg-primary/15 text-primary'
                            : 'text-slate-400 hover:bg-surface hover:text-slate-100',
                      ].join(' ')
                    }
                  >
                    {/* Active left indicator */}
                    {({ isActive }: { isActive: boolean }) => (
                      <>
                        {!disabled && (
                          <span
                            className={`absolute left-0 top-1/2 -translate-y-1/2 w-0.5 rounded-r-full bg-primary
                              transition-all duration-200 ease-in-out
                              ${isActive ? 'h-5 opacity-100' : 'h-0 opacity-0'}`}
                          />
                        )}

                        <Icon size={18} className="shrink-0" />

                        {/* Label — width + opacity animate together */}
                        <span
                          aria-hidden={collapsed}
                          className={`whitespace-nowrap overflow-hidden leading-none
                            transition-[width,opacity] duration-300 ease-[cubic-bezier(0.4,0,0.2,1)]
                            ${collapsed
                              ? 'w-0 opacity-0 pointer-events-none'
                              : 'w-auto opacity-100'
                            }`}
                        >
                          {label}
                        </span>

                        {/* Soon badge */}
                        {disabled && !collapsed && (
                          <span className="ml-auto text-[10px] bg-surface-border text-slate-500 px-1.5 py-0.5 rounded shrink-0">
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
                  className="z-50 px-2.5 py-1.5 rounded-md text-xs font-medium
                    bg-slate-800 text-slate-100 border border-slate-700 shadow-lg select-none
                    data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0
                    data-[state=delayed-open]:zoom-in-95
                    data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
                >
                  {label}
                  {disabled && <span className="ml-1.5 text-slate-500">(Soon)</span>}
                  <Tooltip.Arrow className="fill-slate-800" />
                </Tooltip.Content>
              </Tooltip.Portal>

            </Tooltip.Root>
          ))}
        </nav>
      </aside>
    </Tooltip.Provider>
  )
}
