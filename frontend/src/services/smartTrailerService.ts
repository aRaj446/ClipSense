import { SmartTrailerJob } from '../types/analysis'
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

  async generate(jobId: string): Promise<SmartTrailerJob> {
    const { data } = await apiClient.post<SmartTrailerJob>(`/smart-trailer/generate/${jobId}`)
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

  async getAnalytics(jobId: string): Promise<AnalyticsReport> {
    const { data } = await apiClient.get<AnalyticsReport>(`/smart-trailer/job/${jobId}/analytics`)
    return data
  },

  trailerUrl(outputUrl: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}${outputUrl}`
  },
}
