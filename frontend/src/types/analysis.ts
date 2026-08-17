export interface StoredSegment {
  id: string
  position: number
  timestamp: string | null
  topic: string
  sentiment: string
  summary: string
  confidence: number
  created_at: string
}

export interface StoredDataset {
  id: string
  project_id: string
  name: string | null
  source: string
  created_at: string
  segment_count: number
  segments: StoredSegment[]
}

export interface TrailerJob {
  id: string
  project_id: string
  dataset_id: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  output_url: string | null
  editing_plan: {
    clips: {
      start_time: number
      end_time: number
      reason: string
      topic: string
      sentiment: string
      platform?: string
      mood_group: string
      transcript_text: string
    }[]
    target_duration: number
    rationale: string
  } | null
  platform: string | null
  clip_score: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface AnalyticsReport {
  sentiment_distribution: Record<string, number>
  topic_breakdown: {
    topic: string
    total: number
    positive: number
    negative: number
    neutral: number
    avg_confidence: number
    dominant_sentiment: string
    engagement_score: number        // (positive - negative) / total, [-1.0, 1.0]
  }[]
  timeline: {
    timestamp: string | null
    topic: string
    sentiment: string
    summary: string
    confidence: number
  }[]
  confidence_stats: {
    mean: number
    min: number
    max: number
    high_confidence_count: number
    low_confidence_count: number
    unanchored_count: number        // segments with no timestamp
  }
  sentiment_velocity: {
    minute: number
    positive: number
    negative: number
    neutral: number
    net: number
  }[]
  top_issues: {
    topic: string
    sentiment: string
    count: number
    avg_confidence: number
    sample_summaries: string[]      // up to 3 representative quotes
  }[]
  top_positives: {
    topic: string
    sentiment: string
    count: number
    avg_confidence: number
    sample_summaries: string[]
  }[]
  total_segments: number
  analyzed_at: string
}

export interface FeedbackSummary {
  positive: number
  negative: number
  neutral: number
}

export interface TimelineInsight {
  timestamp: string | null
  topic: string
  sentiment: string
  summary: string
  confidence: number
}

export interface OptimizationRecommendation {
  priority: 'High' | 'Medium' | 'Low'
  timestamp: string | null
  action: string
  reason: string
}

export interface EditingOperation {
  priority: string
  timestamp: string | null
  operation: string
  duration?: number
  reason: string
}

export interface EditingPlan {
  editing_plan: EditingOperation[]
}

export interface AnalysisResult {
  dataset_id: string
  feedback_summary: FeedbackSummary
  timeline_insights: TimelineInsight[]
  optimization_recommendations: OptimizationRecommendation[]
  editing_plan: EditingPlan
}

export interface SmartTrailerAnalysis {
  sentiment_summary: string
  positive_patterns: string[]
  negative_patterns: string[]
  top_scene_categories: string[]
  influence_explanation: string
  scene_selection_rationale: { clip_index: number; confidence: number; reason: string }[]
}

// ── Audio settings ───────────────────────────────────────────────────────────────

export type TargetLufs = -16 | -14 | -12 | -10

export interface AudioSettings {
  target_lufs: TargetLufs
  bass_boost: boolean
  treble_cut: boolean
}

export const DEFAULT_AUDIO_SETTINGS: AudioSettings = {
  target_lufs: -14,
  bass_boost: false,
  treble_cut: false,
}

export interface GenerateRequest {
  user_prompt?: string
  audio?: AudioSettings
  include_subtitles?: boolean
  fast_mode?: boolean
}

// ── Time saved ───────────────────────────────────────────────────────────────

export interface TimeSavedBreakdown {
  manual_editing_hours: number        // estimated hours a human editor would spend
  processing_hours: number            // actual ClipSense wall-clock time in hours
  estimated_time_saved_hours: number  // max(manual - processing, 0)
  raw_footage_duration_secs: number   // source value used for manual estimate
}

// ── Pipeline ─────────────────────────────────────────────────────────────────

export type PipelineStepStatus = 'completed' | 'active' | 'pending' | 'skipped'

export interface PipelineStep {
  id: string
  title: string
  description: string
  status: PipelineStepStatus
  icon: string          // lucide icon name — resolved in component
  timestamp?: string    // ISO string, only set when genuinely available
  action?: () => void   // navigation callback, only set when a real route exists
}

export interface SmartTrailerJob {
  id: string
  raw_footage_name: string
  sample_trailer_name: string
  comments_name: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  output_url: string | null
  sample_trailer_url: string | null   // URL to the original sample trailer for V1 vs V2
  raw_footage_duration_secs: number | null  // actual raw footage length in seconds
  fast_mode: boolean | null           // true when job was run in fast demo mode
  editing_plan: {
    clips: {
      start_time: number
      end_time: number
      reason: string
      topic: string
      sentiment: string
      platform?: string
      mood_group: string
      transcript_text: string
    }[]
    target_duration: number
    rationale: string
  } | null
  analysis_report: SmartTrailerAnalysis | null
  platform: string | null
  clip_score: number | null
  error_message: string | null
  created_at: string
  updated_at: string
}
