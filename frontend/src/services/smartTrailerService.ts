import { SmartTrailerJob, TimeSavedBreakdown, GenerateRequest } from '../types/analysis'
import { AnalyticsReport } from '../types/analysis'
import apiClient from './apiClient'

export const smartTrailerService = {
  async upload(
    rawFootage: File,
    sampleTrailer: File,
    commentsFile: File,
    onProgress?: (pct: number) => void,
  ): Promise<SmartTrailerJob> {
    const form = new FormData()
    form.append('raw_footage',    rawFootage)
    form.append('sample_trailer', sampleTrailer)
    form.append('comments_file',  commentsFile)
    const { data } = await apiClient.post<SmartTrailerJob>('/smart-trailer/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress(e) {
        if (e.total && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
      },
    })
    return data
  },

  async generate(jobId: string, req: GenerateRequest = {}): Promise<SmartTrailerJob> {
    const { data } = await apiClient.post<SmartTrailerJob>(
      `/smart-trailer/generate/${jobId}`,
      req,
    )
    return data
  },

  async pollJob(jobId: string): Promise<SmartTrailerJob> {
    const { data } = await apiClient.get<SmartTrailerJob>(`/smart-trailer/job/${jobId}`)
    return data
  },

  async listJobs(): Promise<SmartTrailerJob[]> {
    const { data } = await apiClient.get<SmartTrailerJob[]>('/smart-trailer/jobs')
    return data
  },

  async deleteJob(jobId: string): Promise<void> {
    await apiClient.delete(`/smart-trailer/job/${jobId}`)
  },

  async cancelJob(jobId: string): Promise<SmartTrailerJob> {
    const { data } = await apiClient.post<SmartTrailerJob>(`/smart-trailer/job/${jobId}/cancel`)
    return data
  },

  async getTimeSaved(jobId: string): Promise<TimeSavedBreakdown> {
    const { data } = await apiClient.get<TimeSavedBreakdown>(`/smart-trailer/job/${jobId}/time-saved`)
    return data
  },

  async getAnalytics(jobId: string): Promise<AnalyticsReport> {
    const { data } = await apiClient.get<AnalyticsReport>(`/smart-trailer/job/${jobId}/analytics`)
    return data
  },

  exportCsvUrl(jobId: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}/smart-trailer/job/${jobId}/export-csv`
  },

  trailerUrl(outputUrl: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}${outputUrl}`
  },

  // Resolve any backend-relative URL (output_url, sample_trailer_url, etc.)
  resolveUrl(relativeUrl: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}${relativeUrl}`
  },

  subscribeProgress(
    jobId: string,
    onUpdate: (stage: string, percent: number, message: string, steps: any[]) => void,
    onDone?: () => void,
  ): () => void {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    const es = new EventSource(`${base}/smart-trailer/job/${jobId}/progress`)
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data)
        onUpdate(d.stage, d.percent, d.message, d.steps ?? [])
        if (d.stage === 'done' || d.stage === 'failed') { es.close(); onDone?.() }
      } catch { /* ignore malformed */ }
    }
    es.onerror = () => es.close()
    return () => es.close()
  },
}
