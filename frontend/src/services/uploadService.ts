import { Project } from '../types/project'
import apiClient from './apiClient'

export interface UploadProjectResult {
  project: Project
  dataset_id: string
  dataset_created: boolean
}

export const uploadService = {
  /** Legacy single-file upload — kept for backward compatibility. */
  async uploadVideo(
    file: File,
    onProgress?: (percent: number) => void,
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

  /** New unified 3-file upload for Phase 2. */
  async uploadProject(
    rawFootage: File,
    sampleTrailer: File,
    feedbackFile: File,
    name?: string,
    onProgress?: (percent: number) => void,
  ): Promise<UploadProjectResult> {
    const form = new FormData()
    form.append('raw_footage', rawFootage)
    form.append('sample_trailer', sampleTrailer)
    form.append('feedback_file', feedbackFile)
    if (name?.trim()) form.append('name', name.trim())

    const { data } = await apiClient.post<UploadProjectResult>('/upload-project', form, {
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
