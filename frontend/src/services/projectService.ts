import { Project } from '../types/project'
import apiClient from './apiClient'

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
}
