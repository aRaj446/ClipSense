export interface Project {
  id: string
  filename: string
  duration: number | null
  width: number | null
  height: number | null
  fps: number | null
  codec: string | null
  bitrate: number | null
  size: number
  upload_time: string
  status: 'uploaded' | 'processing' | 'done'
  // Phase 2 additions — present for new projects, null for legacy
  name: string | null
  dataset_id: string | null
  raw_footage_name: string | null
  sample_trailer_name: string | null
  feedback_file_name: string | null
}

export type ProjectListItem = Pick<
  Project,
  'id' | 'filename' | 'duration' | 'size' | 'upload_time' | 'status' | 'name' | 'dataset_id'
>
