"""
ORM Model — Project

One row per uploaded project. A project groups:
    - raw footage file
    - sample trailer file
    - feedback dataset file
    - all generated trailers (via trailer_jobs.project_id)

The project_id is the stable identifier used across all other tables.

Legacy projects (uploaded before this table existed) are stored only as
JSON files in app/metadata/. ProjectService reads both sources and merges
them transparently — the DB row is the authoritative source when present.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, Integer, Text, DateTime
from app.db.base import Base


class Project(Base):
    __tablename__ = "projects"

    id                   = Column(String, primary_key=True)
    name                 = Column(String, nullable=True)          # user-defined label
    # file paths (absolute, stored at upload time)
    raw_footage_path     = Column(String, nullable=False)
    sample_trailer_path  = Column(String, nullable=False)
    feedback_file_path   = Column(String, nullable=False)
    # original uploaded filenames (user-visible)
    raw_footage_name     = Column(String, nullable=True)
    sample_trailer_name  = Column(String, nullable=True)
    feedback_file_name   = Column(String, nullable=True)
    # video metadata from ffprobe on raw_footage
    duration             = Column(Float,   nullable=True)
    width                = Column(Integer, nullable=True)
    height               = Column(Integer, nullable=True)
    fps                  = Column(Float,   nullable=True)
    codec                = Column(String,  nullable=True)
    bitrate              = Column(Integer, nullable=True)
    size                 = Column(Integer, nullable=True)         # raw footage bytes
    # dataset created during upload
    dataset_id           = Column(String, nullable=True)          # FK to feedback_datasets.id
    # lifecycle
    status               = Column(String, default="uploaded")     # uploaded | processing | done
    created_at           = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at           = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                                  onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r} status={self.status}>"
