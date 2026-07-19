"""
ORM Model — Trailer Job

Tracks every trailer generation request, its status, and output path.
One job per POST /generate-trailer call.

Statuses:
    pending    — job created, not yet started
    processing — FFmpeg pipeline running
    done       — trailer file written to disk
    failed     — pipeline error, see error_message
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime
from app.db.base import Base


class TrailerJob(Base):
    __tablename__ = "trailer_jobs"

    id             = Column(String, primary_key=True)
    project_id     = Column(String, nullable=False, index=True)
    dataset_id     = Column(String, nullable=False)
    status         = Column(String, default="pending")       # pending|processing|done|failed
    output_path    = Column(String, nullable=True)
    editing_plan   = Column(Text,   nullable=True)           # JSON string of TrailerEditingPlan
    platform       = Column(String, nullable=True)           # youtube|instagram|tiktok|twitter
    clip_score     = Column(Float,  nullable=True)           # 0.0–1.0 sentiment satisfaction score
    gemini_used    = Column(String, nullable=True)           # 'true'|'false' — whether Gemini produced the plan
    fallback_warning = Column(Text, nullable=True)           # disclaimer shown when fallback was used
    error_message  = Column(Text,   nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<TrailerJob id={self.id} project_id={self.project_id} status={self.status}>"
