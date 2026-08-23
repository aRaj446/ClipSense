"""
ORM Model — Trailer Edit

Stores a user-modified editing plan for a completed trailer job.
The original AI-generated plan on TrailerJob is never touched.

One row per job_id — PUT replaces the whole plan, DELETE removes the row
(reverting the Scrubber back to the AI plan).
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.db.base import Base


class TrailerEdit(Base):
    __tablename__ = "trailer_edits"

    job_id     = Column(String, ForeignKey("trailer_jobs.id", ondelete="CASCADE"),
                        primary_key=True)
    plan_json  = Column(Text, nullable=False)   # JSON — same shape as TrailerEditingPlan
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<TrailerEdit job_id={self.job_id}>"
