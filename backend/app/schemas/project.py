from pydantic import BaseModel
from typing import Optional


class ProjectAnalyticsStatus(BaseModel):
    """Analytics readiness for a project's primary feedback dataset."""
    project_id: str
    dataset_id: Optional[str] = None       # None → no dataset yet
    has_analytics: bool = False             # True → cached report available
    segment_count: int = 0
    # Sentiment summary (populated when has_analytics=True)
    positive: int = 0
    negative: int = 0
    neutral: int = 0
    top_topic: Optional[str] = None
    analyzed_at: Optional[str] = None
    sensecap_url: Optional[str] = None     # pre-built deep-link (backend constructs it)


class ProjectResponse(BaseModel):
    id: str
    filename: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    size: int
    upload_time: str
    status: str
    # Phase 2 additions — present for new projects, null for legacy
    name: Optional[str] = None
    dataset_id: Optional[str] = None
    raw_footage_name: Optional[str] = None
    sample_trailer_name: Optional[str] = None
    feedback_file_name: Optional[str] = None


class ProjectListItem(BaseModel):
    id: str
    filename: str
    duration: Optional[float] = None
    size: int
    upload_time: str
    status: str
    name: Optional[str] = None
    dataset_id: Optional[str] = None


class UploadProjectResponse(BaseModel):
    """Response for POST /upload-project."""
    project: ProjectResponse
    dataset_id: str
    dataset_created: bool   # False = existing dataset was reused (duplicate feedback file)


class ProjectGenerationRequest(BaseModel):
    """Body for POST /project/{id}/generate-trailer."""
    user_prompt: Optional[str] = None   # free-form creative direction / expectations
    fast_mode: bool = False


class ProjectTrailerListItem(BaseModel):
    """One generated trailer for a project."""
    job_id: str
    project_id: str
    dataset_id: Optional[str] = None
    generation_number: int = 1          # 1-based index, newest = highest
    user_prompt: Optional[str] = None   # expectations used for this generation
    status: str
    output_url: Optional[str] = None
    clip_count: Optional[int] = None
    target_duration: Optional[float] = None
    clip_score: Optional[float] = None
    has_creative_direction: bool = False
    fast_mode: Optional[bool] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: str
