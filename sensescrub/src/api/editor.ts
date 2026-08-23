import client from './client'
import type { Project, EditorJobResponse, ProjectTrailerListItem, EditorClip, SceneEntry } from '../types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

/** Resolve an output_url from EditorJobResponse to a full absolute URL. */
export function videoUrl(outputUrl: string): string {
  return `${API_BASE}${outputUrl}`
}

export async function getProject(projectId: string): Promise<Project> {
  const { data } = await client.get<Project>(`/project/${projectId}`)
  return data
}

export async function getEditorState(jobId: string): Promise<EditorJobResponse> {
  const { data } = await client.get<EditorJobResponse>(`/editor/${jobId}`)
  return data
}

export async function getTrailers(projectId: string): Promise<ProjectTrailerListItem[]> {
  const { data } = await client.get<ProjectTrailerListItem[]>(`/project/${projectId}/trailers`)
  return data
}

export async function getScenes(jobId: string): Promise<SceneEntry[]> {
  const { data } = await client.get<{ scenes: SceneEntry[] }>(`/editor/${jobId}/scenes`)
  return data.scenes
}

export async function savePlan(jobId: string, clips: EditorClip[]): Promise<EditorJobResponse> {
  const target = clips.reduce((s, c) => s + Math.max(0, c.end_time - c.start_time), 0)
  // Strip frontend-only `id` field before sending to backend
  const wireClips = clips.map(({ id: _id, ...rest }) => rest)
  const { data } = await client.put<EditorJobResponse>(`/editor/${jobId}/plan`, {
    clips: wireClips,
    target_duration: Math.round(target * 100) / 100,
    audio_fade_out:  true,
    output_format:   'mp4',
    rationale:       'User-edited plan',
    source_editor:   'sensescrub',
  })
  return data
}

export async function resetPlan(jobId: string): Promise<void> {
  await client.delete(`/editor/${jobId}/plan`)
}

export interface RenderResponse {
  new_job_id: string
  message: string
  job_type: 'standard' | 'smart'
}

export async function startRender(jobId: string): Promise<RenderResponse> {
  const { data } = await client.post<RenderResponse>(`/editor/${jobId}/render`)
  return data
}

/** Returns an EventSource for SSE render progress. Caller must close() it. */
export function subscribeRenderProgress(
  jobId: string,
  newJobId: string,
  onMessage: (data: { stage: string; percent: number; message: string; steps: unknown[] }) => void,
  onError: () => void,
): EventSource {
  const url = `${API_BASE}/editor/${jobId}/render/progress?new_job_id=${newJobId}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch { /* ignore malformed */ }
  }
  es.onerror = () => { es.close(); onError() }
  return es
}

/**
 * Upload a client-side rendered video to the backend.
 * Creates a new trailer record tagged with source_editor='sensescrub'.
 */
export async function uploadClientRender(jobId: string, videoBlob: Blob): Promise<EditorJobResponse> {
  const formData = new FormData()
  formData.append('file', videoBlob, `sensescrub-export-${Date.now()}.mp4`)

  const { data } = await client.post<EditorJobResponse>(
    `/editor/${jobId}/upload-render`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000, // 2 min for large uploads
    },
  )
  return data
}
