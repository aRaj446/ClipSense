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
    clips: { start_time: number; end_time: number; reason: string; topic: string; sentiment: string; platform?: string }[]
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
  }
  top_issues: {
    topic: string
    sentiment: string
    count: number
    avg_confidence: number
    sample_summary: string
  }[]
  top_positives: {
    topic: string
    sentiment: string
    count: number
    avg_confidence: number
    sample_summary: string
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

export interface SmartTrailerJob {
  id: string
  raw_footage_name: string
  sample_trailer_name: string
  comments_name: string
  status: 'pending' | 'processing' | 'done' | 'failed'
  output_url: string | null
  editing_plan: {
    clips: { start_time: number; end_time: number; reason: string; topic: string; sentiment: string; platform?: string }[]
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
