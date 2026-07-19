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
}

export type ProjectListItem = Pick<
  Project,
  'id' | 'filename' | 'duration' | 'size' | 'upload_time' | 'status'
>
