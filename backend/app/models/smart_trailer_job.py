"""
ORM Model — Smart Trailer Job

Tracks every Smart Trailer generation request.
Inputs: raw footage path, sample trailer path, comments file path.
Separate table — does not touch trailer_jobs.

Statuses:
    pending    — job created, not yet started
    processing — analysis + FFmpeg pipeline running
    done       — trailer file written to disk
    failed     — pipeline error, see error_message
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime
from app.db.base import Base


class SmartTrailerJob(Base):
    __tablename__ = "smart_trailer_jobs"

    id                  = Column(String,   primary_key=True)
    # input file paths (stored on disk under uploads/smart/)
    raw_footage_path    = Column(String,   nullable=False)
    sample_trailer_path = Column(String,   nullable=False)
    comments_path       = Column(String,   nullable=False)
    # original uploaded filenames (user-visible names)
    raw_footage_original_name    = Column(String, nullable=True)
    sample_trailer_original_name = Column(String, nullable=True)
    comments_original_name       = Column(String, nullable=True)
    # job lifecycle
    status              = Column(String,   default="pending")   # pending|processing|done|failed
    output_path         = Column(String,   nullable=True)
    # Gemini outputs
    editing_plan        = Column(Text,     nullable=True)       # JSON — TrailerEditingPlan
    analysis_report     = Column(Text,     nullable=True)       # JSON — SmartTrailerAnalysis
    platform            = Column(String,   nullable=True)
    clip_score          = Column(Float,    nullable=True)       # 0.0–1.0
    gemini_used         = Column(String,   nullable=True)       # 'true'|'false'
    fallback_warning    = Column(Text,     nullable=True)       # disclaimer when fallback was used
    error_message       = Column(Text,     nullable=True)
    # Duration of the raw footage in seconds — stored at generation time so the
    # time-saved calculation can use the actual input length, not the output length.
    raw_footage_duration_secs = Column(Float, nullable=True)
    fast_mode           = Column(String,   nullable=True)   # 'true'|'false' — set at generation time
    # GPU/device metadata — recorded at generation time for analytics/debug
    device_used         = Column(String,   nullable=True)   # 'cuda'|'cpu'
    encoder_used        = Column(String,   nullable=True)   # 'h264_nvenc'|'libx264'
    whisper_model_used  = Column(String,   nullable=True)   # e.g. 'base', 'small'
    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                 onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<SmartTrailerJob id={self.id} status={self.status}>"
