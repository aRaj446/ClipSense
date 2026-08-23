"""
ORM Model — Smart Trailer Edit

Stores a user-modified editing plan for a completed SmartTrailerJob.
Mirrors TrailerEdit but uses a plain string job_id (no FK) so it can
reference SmartTrailerJob IDs without touching the trailer_edits table
or its existing FK to trailer_jobs.

Design contract (identical to TrailerEdit):
    - The AI-generated plan on SmartTrailerJob.editing_plan is NEVER mutated.
    - User edits are stored here (one row per job_id).
    - GET returns the user plan when present, otherwise the AI plan.
    - DELETE removes this row, reverting the editor to the AI plan.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime
from app.db.base import Base


class SmartTrailerEdit(Base):
    __tablename__ = "smart_trailer_edits"

    job_id     = Column(String, primary_key=True)   # SmartTrailerJob.id — no FK by design
    plan_json  = Column(Text, nullable=False)        # JSON — same shape as TrailerEditingPlan
    updated_at = Column(DateTime,
                        default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc),
                        nullable=False)

    def __repr__(self) -> str:
        return f"<SmartTrailerEdit job_id={self.job_id}>"
