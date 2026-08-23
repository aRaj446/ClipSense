import { TrailerStrategy } from '../types/analysis'
import apiClient from './apiClient'

export const strategyService = {
  async generate(datasetId: string): Promise<TrailerStrategy> {
    const { data } = await apiClient.post<TrailerStrategy>(`/strategy/${datasetId}/generate`)
    return data
  },

  async get(datasetId: string): Promise<TrailerStrategy | null> {
    try {
      const { data } = await apiClient.get<TrailerStrategy>(`/strategy/${datasetId}`)
      return data
    } catch (err: any) {
      if (err?.response?.status === 404) return null
      throw err
    }
  },

  async update(datasetId: string, userStrategy: string): Promise<TrailerStrategy> {
    const { data } = await apiClient.put<TrailerStrategy>(`/strategy/${datasetId}`, {
      user_strategy: userStrategy,
    })
    return data
  },

  async reset(datasetId: string): Promise<TrailerStrategy> {
    const { data } = await apiClient.post<TrailerStrategy>(`/strategy/${datasetId}/reset`)
    return data
  },
}
