import { AnalysisResult, StoredDataset, AnalyticsReport } from '../types/analysis'
import apiClient from './apiClient'

export const feedbackService = {
  /**
   * Upload a structured feedback file (.json or .csv).
   * The backend parses it directly into FeedbackSegment objects,
   * saves to DB, and runs the Video Optimization Agent.
   */
  async uploadFeedbackFile(
    projectId: string,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<AnalysisResult> {
    const form = new FormData()
    form.append('project_id', projectId)
    form.append('file', file)

    const { data } = await apiClient.post<AnalysisResult>('/upload-feedback', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress(e) {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100))
        }
      },
    })
    return data
  },

  async listDatasets(projectId: string): Promise<StoredDataset[]> {
    const { data } = await apiClient.get<StoredDataset[]>(`/feedback-datasets/${projectId}`)
    return data
  },

  async renameDataset(datasetId: string, name: string): Promise<StoredDataset> {
    const { data } = await apiClient.patch<StoredDataset>(`/feedback-dataset/${datasetId}/rename`, { name })
    return data
  },

  async deleteDataset(datasetId: string): Promise<void> {
    await apiClient.delete(`/feedback-dataset/${datasetId}`)
  },

  async getAnalytics(datasetId: string): Promise<AnalyticsReport> {
    const { data } = await apiClient.get<AnalyticsReport>(`/analytics/${datasetId}`)
    return data
  },

  exportDatasetUrl(datasetId: string): string {
    const base = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
    return `${base}/export-dataset/${datasetId}`
  },

  /**
   * Submit raw unstructured feedback text.
   * Kept for future Gemini 2.5 Pro LLM integration.
   */
  async analyzeFeedback(projectId: string, feedback: string): Promise<AnalysisResult> {
    const { data } = await apiClient.post<AnalysisResult>('/analyze-feedback', {
      project_id: projectId,
      feedback,
    })
    return data
  },
}
