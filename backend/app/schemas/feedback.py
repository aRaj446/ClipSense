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
    engagement_score: float   # (positive - negative) / total, range [-1.0, 1.0]


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
    unanchored_count: int     # segments with no timestamp


class SentimentVelocityBucket(BaseModel):
    minute: int               # video minute (0 = 0:00–0:59, 1 = 1:00–1:59, …)
    positive: int
    negative: int
    neutral: int
    net: int                  # positive - negative


class TopicInsight(BaseModel):
    topic: str
    sentiment: str
    count: int
    avg_confidence: float
    sample_summaries: list[str]   # up to 3 representative summaries


class AudiencePreferences(BaseModel):
    """
    Derived audience preference signals extracted from structured feedback.
    Produced by the Analytics Agent alongside the main report.
    """
    liked: list[str]               # topics / patterns audiences responded positively to
    disliked: list[str]            # topics / patterns audiences responded negatively to
    recurring_requests: list[str]  # Suggestion-sentiment summaries (up to 5)
    recurring_complaints: list[str]  # Complaint/Negative summaries (up to 5)
    recurring_praise: list[str]    # Praise/Positive summaries (up to 5)


class AnalyticsReport(BaseModel):
    """Power BI / Tableau-ready analytics payload produced by the Analytics Agent."""
    sentiment_distribution: dict[str, int]
    topic_breakdown: list[TopicBreakdown]
    timeline: list[TimelinePoint]
    confidence_stats: ConfidenceStats
    sentiment_velocity: list[SentimentVelocityBucket]
    top_issues: list[TopicInsight]
    top_positives: list[TopicInsight]
    audience_preferences: AudiencePreferences
    total_segments: int
    analyzed_at: str


# ── Audience Analysis Job schemas ────────────────────────────────────────────

class AudienceAnalysisJobResponse(BaseModel):
    """API response for audience analysis job status."""
    id: str
    status: str                          # pending | processing | done | failed
    source: str                          # manual_paste | file_upload | file_upload_txt
    dataset_id: Optional[str] = None     # set once segments are persisted
    analytics_report: Optional[dict] = None  # set once analysis is complete
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class SubmitAudienceFeedbackRequest(BaseModel):
    """Body for POST /audience-analysis (text path)."""
    project_id: str
    feedback: str


# ── Trailer schemas ───────────────────────────────────────────────────────────

class TrailerClip(BaseModel):
    start_time: float
    end_time: float
    reason: str
    topic: str
    sentiment: str
    platform: Optional[str] = None
    mood_group: str = "calm"        # action | emotional | dialogue | calm
    transcript_text: str = ""       # full transcript text for this clip
    muted: bool = False             # when True, audio is silenced during render


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
    fallback_warning: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class GenerateTrailerRequest(BaseModel):
    project_id: str
    dataset_id: str
    strategy: Optional[str] = None   # user trailer strategy text; None = existing behaviour


# ── Smart Trailer schemas ───────────────────────────────────────────────────────────────

_ALLOWED_LUFS = {-16, -14, -12, -10}


class AudioSettings(BaseModel):
    """
    Per-job audio normalisation controls.

    target_lufs: Final output loudness in LUFS. Default -14 preserves existing behaviour.
    bass_boost:  Apply +4 dB low-shelf EQ at 100 Hz. Default False.
    treble_cut:  Apply -3 dB high-shelf EQ at 8 kHz. Default False.
    """
    target_lufs: int = -14
    bass_boost: bool = False
    treble_cut: bool = False

    def model_post_init(self, __context) -> None:
        if self.target_lufs not in _ALLOWED_LUFS:
            raise ValueError(f"target_lufs must be one of {sorted(_ALLOWED_LUFS)}, got {self.target_lufs}")


class SmartTrailerGenerateRequest(BaseModel):
    """Optional body for POST /smart-trailer/generate/{job_id}."""
    user_prompt: Optional[str] = None        # free-form creative direction from the editor
    audio: Optional[AudioSettings] = None   # audio normalisation controls
    include_subtitles: bool = False          # burn transcript subtitles into the output
    fast_mode: bool = False                  # skip Whisper transcription for faster demo generation


class TimeSavedBreakdown(BaseModel):
    """
    Auditable time-saved breakdown for a completed smart trailer job.

    Calculation (all values in hours):

        raw_footage_duration_secs  — actual raw footage length probed by FFmpeg (seconds)
        raw_footage_duration_mins  = raw_footage_duration_secs / 60

        MANUAL_EDIT_RATIO = 0.5
        manual_editing_hours = raw_footage_duration_mins * MANUAL_EDIT_RATIO / 60
            i.e. raw_footage_duration_secs / 60 * 0.5 / 60

        processing_hours = (completed_at - started_at).total_seconds() / 3600
            where started_at  = job.created_at  (row inserted when files uploaded)
                  completed_at = job.updated_at  (last DB write = job completion)

        estimated_time_saved_hours = max(manual_editing_hours - processing_hours, 0)
    """
    manual_editing_hours: float          # estimated hours a human editor would spend
    processing_hours: float              # actual ClipSense wall-clock time in hours
    estimated_time_saved_hours: float    # max(manual - processing, 0)
    raw_footage_duration_secs: float     # source value used for manual estimate


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
    project_id: Optional[str] = None
    raw_footage_name: str
    sample_trailer_name: str
    comments_name: str
    status: str
    output_url: Optional[str] = None
    sample_trailer_url: Optional[str] = None
    editing_plan: Optional[dict] = None
    analysis_report: Optional[dict] = None
    platform: Optional[str] = None
    clip_score: Optional[float] = None
    fallback_warning: Optional[str] = None
    error_message: Optional[str] = None
    raw_footage_duration_secs: Optional[float] = None
    fast_mode: Optional[bool] = None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}
