"""
ORM Model — Audience Analysis Job

Tracks a standalone audience intelligence analysis run.
Decoupled from project video uploads — accepts raw text or file input.

Statuses:
    pending    — job queued, not yet started
    processing — pipeline running (parsing → sentiment → topics → analytics)
    done       — analytics_report populated
    failed     — error_message populated
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class AudienceAnalysisJob(Base):
    __tablename__ = "audience_analysis_jobs"

    id           = Column(String,   primary_key=True)
    project_id   = Column(String,   nullable=False, index=True)
    source       = Column(String,   nullable=False)   # manual_paste | file_upload | file_upload_txt
    raw_text     = Column(Text,     nullable=False)
    status       = Column(String,   default="pending")  # pending|processing|done|failed
    dataset_id   = Column(String,   nullable=True)      # FK to feedback_datasets.id (set after persist)
    analytics_report = Column(Text, nullable=True)      # JSON-serialised AnalyticsReport
    error_message    = Column(Text, nullable=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<AudienceAnalysisJob id={self.id} status={self.status}>"
