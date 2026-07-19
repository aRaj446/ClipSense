from pydantic import BaseModel
from typing import Optional


class AnalyzeFeedbackRequest(BaseModel):
    project_id: str
    feedback: str  # Raw unstructured audience feedback text


class FeedbackSegment(BaseModel):
    """A single structured insight extracted by the Feedback Structuring Agent."""
    timestamp: Optional[str] = None
    topic: str
    sentiment: str  # Positive | Negative | Neutral | Suggestion | Complaint | Praise | Question
    summary: str
    confidence: float


class FeedbackSummary(BaseModel):
    positive: int
    negative: int
    neutral: int


class OptimizationRecommendation(BaseModel):
    """A single editing recommendation produced by the Video Optimization Agent."""
    priority: str  # High | Medium | Low
    timestamp: Optional[str] = None
    action: str
    reason: str


class EditingOperation(BaseModel):
    """
    Structured editing operation for the future Video Regeneration Agent.
    Defines the contract between the Video Optimization Agent and the regeneration pipeline.
    """
    priority: str
    timestamp: Optional[str] = None
    operation: str   # trim | increase_duration | reduce_audio | add_subtitles | etc.
    duration: Optional[int] = None
    reason: str


class EditingPlan(BaseModel):
    """
    Machine-readable editing plan produced by the Video Optimization Agent.
    Designed to be consumed directly by the future Video Regeneration Agent.
    """
    editing_plan: list[EditingOperation]


class AnalysisResponse(BaseModel):
    """Full response returned by POST /analyze-feedback."""
    dataset_id: str                                   # ID of the persisted dataset
    feedback_summary: FeedbackSummary
    timeline_insights: list[FeedbackSegment]
    optimization_recommendations: list[OptimizationRecommendation]
    editing_plan: EditingPlan


# ── DB read schemas ───────────────────────────────────────────────────────────

class StoredSegment(BaseModel):
    """Serialised FeedbackSegmentRecord for API responses."""
    id: str
    position: int
    timestamp: Optional[str] = None
    topic: str
    sentiment: str
    summary: str
    confidence: float
    created_at: str

    model_config = {"from_attributes": True}


class FeedbackDatasetResponse(BaseModel):
    """Serialised FeedbackDataset for API responses."""
    id: str
    project_id: str
    name: Optional[str] = None
    source: str
    created_at: str
    segment_count: int
    segments: list[StoredSegment] = []

    model_config = {"from_attributes": True}


class RenameDatasetRequest(BaseModel):
    name: str


# ── Analytics schemas ─────────────────────────────────────────────────────────

class TopicBreakdown(BaseModel):
    topic: str
    total: int
    positive: int
    negative: int
    neutral: int
    avg_confidence: float
    dominant_sentiment: str


class TimelinePoint(BaseModel):
    timestamp: Optional[str]
    topic: str
    sentiment: str
    summary: str
    confidence: float


class ConfidenceStats(BaseModel):
    mean: float
    min: float
    max: float
    high_confidence_count: int
    low_confidence_count: int


class TopicInsight(BaseModel):
    topic: str
    sentiment: str
    count: int
    avg_confidence: float
    sample_summary: str


class AnalyticsReport(BaseModel):
    """Power BI / Tableau-ready analytics payload produced by the Analytics Agent."""
    sentiment_distribution: dict[str, int]
    topic_breakdown: list[TopicBreakdown]
    timeline: list[TimelinePoint]
    confidence_stats: ConfidenceStats
    top_issues: list[TopicInsight]
    top_positives: list[TopicInsight]
    total_segments: int
    analyzed_at: str


# ── Trailer schemas ───────────────────────────────────────────────────────────

class TrailerClip(BaseModel):
    start_time: float
    end_time: float
    reason: str
    topic: str
    sentiment: str
    platform: Optional[str] = None   # youtube | instagram | tiktok | twitter


class TrailerEditingPlan(BaseModel):
    """
    Full editing plan produced by Gemini for the Video Regeneration Agent.
    FFmpeg executes this plan — Gemini never touches the video file.
    """
    clips: list[TrailerClip]
    target_duration: float             # desired total trailer length in seconds
    audio_fade_out: bool = True
    output_format: str = "mp4"
    rationale: str                     # Gemini's explanation of the plan


class TrailerJobResponse(BaseModel):
    """API response for trailer job status."""
    id: str
    project_id: str
    dataset_id: str
    status: str
    output_url: Optional[str] = None
    editing_plan: Optional[dict] = None
    platform: Optional[str] = None
    clip_score: Optional[float] = None
    gemini_used: Optional[bool] = None
    fallback_warning: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class GenerateTrailerRequest(BaseModel):
    project_id: str
    dataset_id: str


# ── Smart Trailer schemas ───────────────────────────────────────────────────────────────

class SmartTrailerAnalysis(BaseModel):
    """Analysis output produced by the Smart Trailer Agent."""
    sentiment_summary: str                  # overall audience sentiment on the sample trailer
    positive_patterns: list[str]            # editing patterns correlated with positive reactions
    negative_patterns: list[str]            # editing patterns correlated with negative reactions
    top_scene_categories: list[str]         # scene types with highest engagement
    influence_explanation: str              # how sample trailer analysis shaped the new trailer
    scene_selection_rationale: list[dict]   # per-clip confidence + reason from raw footage


class SmartTrailerJobResponse(BaseModel):
    """API response for smart trailer job status."""
    id: str
    raw_footage_name: str
    sample_trailer_name: str
    comments_name: str
    status: str
    output_url: Optional[str] = None
    editing_plan: Optional[dict] = None
    analysis_report: Optional[dict] = None
    platform: Optional[str] = None
    clip_score: Optional[float] = None
    gemini_used: Optional[bool] = None
    fallback_warning: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
