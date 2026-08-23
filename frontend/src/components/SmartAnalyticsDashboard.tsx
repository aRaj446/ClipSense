import { useEffect, useState } from 'react'
import { Clapperboard, Loader2, AlertCircle, ExternalLink } from 'lucide-react'
import { SmartTrailerJob, AnalyticsReport } from '../types/analysis'
import { smartTrailerService } from '../services/smartTrailerService'
import AnalyticsDashboard from './AnalyticsDashboard'
import Card from './Card'

interface Props {
  job: SmartTrailerJob
}

export default function SmartAnalyticsDashboard({ job }: Props) {
  const [report, setReport]   = useState<AnalyticsReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    setReport(null)
    smartTrailerService.getAnalytics(job.id)
      .then(setReport)
      .catch((err) => {
        const msg = err?.response?.data?.detail ?? err?.message ?? 'Failed to load analytics for this smart trailer.'
        setError(msg)
      })
      .finally(() => setLoading(false))
  }, [job.id])

  if (loading) {
    return (
      <Card className="flex items-center justify-center py-16 gap-3">
        <Loader2 size={20} className="text-primary animate-spin" />
        <span className="text-sm" style={{ color: '#A8A4B8' }}>Analysing comments dataset…</span>
      </Card>
    )
  }

  if (error || !report) {
    return (
      <Card className="flex items-center justify-center py-12 gap-3">
        <AlertCircle size={18} className="text-red-400" />
        <span className="text-slate-400 text-sm">{error ?? 'No data'}</span>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Clapperboard size={12} className="text-primary" />
        <span className="text-slate-300 font-medium truncate">{job.raw_footage_name}</span>
        <span className="text-slate-600">›</span>
        <span className="text-slate-300 font-medium truncate">{job.comments_name}</span>
        <button
          onClick={() => {
            const sensecap = import.meta.env.VITE_SENSECAP_URL ?? 'http://localhost:8501'
            const csvUrl = smartTrailerService.exportCsvUrl(job.id)
            const params = new URLSearchParams({ dataset_url: csvUrl, source: 'clipsense', dataset_name: job.comments_name })
            window.open(`${sensecap}?${params.toString()}`, '_blank', 'noopener,noreferrer')
          }}
          className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all hover:opacity-80"
          style={{ background: 'linear-gradient(135deg,#D4A84320,#8B7CF612)', border: '1px solid #D4A84335', color: '#D4A843' }}
        >
          <ExternalLink size={11} /> Open in Sensecap
        </button>
      </div>

      {/* Full analytics — same component as standard, driven by the real parsed segments */}
      <AnalyticsDashboard
        datasetId={job.id}
        datasetName={job.comments_name}
        prefetchedReport={report}
      />
    </div>
  )
}
