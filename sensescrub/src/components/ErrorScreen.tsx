import { AlertTriangle, WifiOff, Clock, SearchX } from 'lucide-react'

export type ErrorKind =
  | 'missing-params'
  | 'invalid-params'
  | 'not-found'
  | 'not-ready'
  | 'unavailable'
  | 'unknown'

interface Props {
  kind: ErrorKind
  detail?: string
}

const CONFIG: Record<ErrorKind, { icon: React.ReactNode; title: string; body: string }> = {
  'missing-params': {
    icon: <AlertTriangle size={36} className="text-accent-amber" />,
    title: 'Missing URL parameters',
    body: 'SenseScrub must be opened from ClipSense via the "Open in SenseScrub" button. Both ?project= and ?job= are required.',
  },
  'invalid-params': {
    icon: <AlertTriangle size={36} className="text-accent-amber" />,
    title: 'Invalid URL parameters',
    body: 'The project or job ID in the URL is not a valid UUID. Please return to ClipSense and reopen the link.',
  },
  'not-found': {
    icon: <SearchX size={36} className="text-accent-red" />,
    title: 'Job not found',
    body: 'The requested project or job could not be found. It may have been deleted, or the URL may be stale.',
  },
  'not-ready': {
    icon: <Clock size={36} className="text-accent-amber" />,
    title: 'Job not ready',
    body: 'This job has not finished processing yet (status 409). Return to ClipSense and wait for the job to complete before opening it in SenseScrub.',
  },
  'unavailable': {
    icon: <WifiOff size={36} className="text-accent-red" />,
    title: 'Backend unavailable',
    body: 'Could not reach the ClipSense backend. Make sure the backend server is running on port 8000 and try again.',
  },
  'unknown': {
    icon: <AlertTriangle size={36} className="text-accent-red" />,
    title: 'Unexpected error',
    body: 'Something went wrong loading the editor.',
  },
}

export default function ErrorScreen({ kind, detail }: Props) {
  const { icon, title, body } = CONFIG[kind]
  return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-5 px-6 text-center">
      {icon}
      <div className="space-y-2">
        <p className="text-slate-100 font-semibold text-base">{title}</p>
        <p className="text-slate-400 text-sm max-w-md">{body}</p>
        {detail && (
          <p className="text-slate-600 text-xs font-mono mt-2 max-w-md break-all">{detail}</p>
        )}
      </div>
    </div>
  )
}
