import { Project } from '../types/project'
import apiClient from './apiClient'

export const uploadService = {
  async uploadVideo(
    file: File,
    onProgress?: (percent: number) => void
  ): Promise<Project> {
    const form = new FormData()
    form.append('file', file)

    const { data } = await apiClient.post<Project>('/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress(e) {
        if (e.total && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100))
        }
      },
    })
    return data
  },
}
