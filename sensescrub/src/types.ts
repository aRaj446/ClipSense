// ── Project ───────────────────────────────────────────────────────────────────

export interface Project {
  id: string
  filename: string
  name: string | null
  duration: number | null
  status: 'uploaded' | 'processing' | 'done'
}

// ── Trailer list item (GET /project/{id}/trailers) ────────────────────────────

export interface ProjectTrailerListItem {
  job_id: string
  project_id: string
  generation_number: number
  status: 'pending' | 'processing' | 'done' | 'failed'
  output_url: string | null
  clip_count: number | null
  clip_score: number | null
  created_at: string
  updated_at: string
}

// ── Clip (inside EditorJobResponse.plan) ─────────────────────────────────────

export interface EditorClip {
  /** Stable frontend-only identity. Stripped before PUT /plan. */
  id: string
  start_time: number
  end_time: number
  reason: string
  topic: string
  sentiment: string
  platform: string | null
  mood_group: string
  transcript_text: string
  muted: boolean
  /** Playback speed multiplier (0.25–4.0). Default 1.0. */
  speed?: number
}

export interface EditorPlan {
  clips: EditorClip[]
  target_duration: number
  audio_fade_out: boolean
  output_format: string
  rationale: string
}

// ── Scene (GET /editor/{job_id}/scenes) ─────────────────────────────────────

export interface SceneEntry {
  start_time: number
  end_time: number
  topic: string
  sentiment: string
  reason: string
  transcript_text: string
  mood_group: string
  platform: string | null
  muted: boolean
}

// ── Editor state (GET /editor/{job_id}) ───────────────────────────────────────

export interface EditorJobResponse {
  job_id: string
  project_id: string
  status: string
  output_url: string | null
  raw_footage_url: string | null
  platform: string | null
  clip_score: number | null
  plan: EditorPlan | null
  plan_source: 'ai' | 'user'
  plan_updated_at: string | null
  created_at: string
  updated_at: string
  job_type: 'standard' | 'smart'
}
