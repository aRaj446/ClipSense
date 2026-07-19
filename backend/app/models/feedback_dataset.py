"""
ORM Models — Structured Feedback Dataset

Two tables:
    feedback_datasets       — one record per analysis run, linked to a project
    feedback_segments       — one record per structured segment within a dataset

The Feedback Structuring Agent (Agent 1) produces segments.
These are persisted here BEFORE the Video Optimization Agent (Agent 2)
performs sentiment-based classification and generates recommendations.

This means the raw structured data is always preserved independently
of any downstream processing decisions.

Migration to online DB:
    Change DATABASE_URL in app/db/database.py.
    Run: alembic revision --autogenerate -m "init"
         alembic upgrade head
    No changes needed in this file.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Integer,
    Text, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from app.db.base import Base


class FeedbackDataset(Base):
    """
    One dataset per analysis run.
    Stores the original raw input and links to all extracted segments.
    """
    __tablename__ = "feedback_datasets"

    id         = Column(String, primary_key=True)
    project_id = Column(String, nullable=False, index=True)
    name       = Column(String, nullable=True)            # user-defined label, null until renamed
    raw_text   = Column(Text, nullable=False)
    source     = Column(String, default="manual_paste")  # manual_paste | file_upload | api
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    segments = relationship(
        "FeedbackSegmentRecord",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="FeedbackSegmentRecord.position",
    )

    def __repr__(self) -> str:
        return f"<FeedbackDataset id={self.id} project_id={self.project_id}>"


class FeedbackSegmentRecord(Base):
    """
    One row per structured segment extracted by the Feedback Structuring Agent.

    Stored with sentiment as extracted by Agent 1.
    Agent 2 reads from this table — it never re-parses raw text.
    """
    __tablename__ = "feedback_segments"

    id         = Column(String, primary_key=True)
    dataset_id = Column(
        String,
        ForeignKey("feedback_datasets.id"),
        nullable=False,
    )
    position   = Column(Integer, nullable=False)   # order within the dataset
    timestamp  = Column(String, nullable=True)     # normalised MM:SS or null
    topic      = Column(String, nullable=False)
    sentiment  = Column(String, nullable=False)    # Positive|Negative|Neutral|etc.
    summary    = Column(Text, nullable=False)      # cleaned comment text
    confidence = Column(Float, nullable=False)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    dataset = relationship("FeedbackDataset", back_populates="segments")

    __table_args__ = (
        Index("ix_segments_dataset_id", "dataset_id"),
        Index("ix_segments_sentiment",  "sentiment"),
        Index("ix_segments_topic",      "topic"),
    )

    def __repr__(self) -> str:
        return (
            f"<FeedbackSegmentRecord id={self.id} "
            f"topic={self.topic} sentiment={self.sentiment}>"
        )
