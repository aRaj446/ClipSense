import { useEffect, useState } from 'react'
import { Sparkles, Loader2, AlertCircle } from 'lucide-react'
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
      .catch(() => setError('Failed to load analytics for this smart trailer.'))
      .finally(() => setLoading(false))
  }, [job.id])

  if (loading) {
    return (
      <Card className="flex items-center justify-center py-16 gap-3">
        <Loader2 size={20} className="text-primary animate-spin" />
        <span className="text-slate-400 text-sm">Analysing comments dataset…</span>
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
        <Sparkles size={12} className="text-primary" />
        <span className="text-slate-300 font-medium truncate">{job.raw_footage_name}</span>
        <span className="text-slate-600">›</span>
        <span className="text-slate-300 font-medium truncate">{job.comments_name}</span>
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
