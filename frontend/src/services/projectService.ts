import { Project } from '../types/project'
import apiClient from './apiClient'

export interface ProjectAnalyticsStatus {
  project_id: string
  dataset_id: string | null
  has_analytics: boolean
  segment_count: number
  positive: number
  negative: number
  neutral: number
  top_topic: string | null
  analyzed_at: string | null
  sensecap_url: string | null
}

export interface ProjectTrailerListItem {
  job_id: string
  project_id: string
  dataset_id: string | null
  generation_number: number
  user_prompt: string | null
  status: 'pending' | 'processing' | 'done' | 'failed'
  output_url: string | null
  clip_count: number | null
  target_duration: number | null
  clip_score: number | null
  has_creative_direction: boolean
  fast_mode: boolean | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export const projectService = {
  async listProjects(): Promise<Project[]> {
    const { data } = await apiClient.get<Project[]>('/projects')
    return data
  },

  async getProject(id: string): Promise<Project> {
    const { data } = await apiClient.get<Project>(`/project/${id}`)
    return data
  },

  async deleteProject(id: string): Promise<void> {
    await apiClient.delete(`/project/${id}`)
  },

  async getAnalyticsStatus(projectId: string): Promise<ProjectAnalyticsStatus> {
    const { data } = await apiClient.get<ProjectAnalyticsStatus>(`/project/${projectId}/analytics-status`)
    return data
  },

  async runAnalytics(projectId: string, force = false): Promise<ProjectAnalyticsStatus> {
    const { data } = await apiClient.post<ProjectAnalyticsStatus>(
      `/project/${projectId}/run-analytics`,
      null,
      { params: force ? { force: true } : {} },
    )
    return data
  },

  async generateTrailer(
    projectId: string,
    userPrompt?: string,
    fastMode = false,
  ): Promise<import('../types/analysis').SmartTrailerJob> {
    const { data } = await apiClient.post(
      `/project/${projectId}/generate-trailer`,
      { user_prompt: userPrompt || null, fast_mode: fastMode },
    )
    return data
  },

  async listTrailers(projectId: string): Promise<ProjectTrailerListItem[]> {
    const { data } = await apiClient.get<ProjectTrailerListItem[]>(`/project/${projectId}/trailers`)
    return data
  },
}
