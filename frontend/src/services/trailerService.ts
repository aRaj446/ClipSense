import { TrailerJob } from '../types/analysis'
import apiClient from './apiClient'

export const trailerService = {
  async generateTrailer(
    projectId: string,
    datasetId: string,
  ): Promise<TrailerJob> {
    const { data } = await apiClient.post<TrailerJob>('/generate-trailer', {
      project_id: projectId,
      dataset_id: datasetId,
    })
    return data
  },

  async pollJob(jobId: string): Promise<TrailerJob> {
    const { data } = await apiClient.get<TrailerJob>(`/trailer-job/${jobId}`)
    return data
  },

  async listJobs(projectId: string): Promise<TrailerJob[]> {
    const { data } = await apiClient.get<TrailerJob[]>(`/trailer-jobs/${projectId}`)
    return data
  },

  async listAllTrailers(): Promise<TrailerJob[]> {
    const { data } = await apiClient.get<TrailerJob[]>('/all-trailers')
    return data
  },

  async deleteJob(jobId: string): Promise<void> {
    await apiClient.delete(`/trailer-job/${jobId}`)
  },

  async cancelJob(jobId: string): Promise<TrailerJob> {
    const { data } = await apiClient.post<TrailerJob>(`/trailer-job/${jobId}/cancel`)
    return data
  },

  trailerUrl(outputUrl: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}${outputUrl}`
  },
}
