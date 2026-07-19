"""
Feedback Dataset Service

All database persistence for FeedbackDataset and FeedbackSegmentRecord.
No business logic lives here — only storage concerns.

Called by the API layer after Agent 1 produces segments and
BEFORE Agent 2 runs optimization / sentiment classification.
"""

import uuid
import json
from sqlalchemy.orm import Session

from app.models.feedback_dataset import FeedbackDataset, FeedbackSegmentRecord
from app.schemas.feedback import FeedbackSegment


class FeedbackDatasetService:

    def save_dataset(
        self,
        db: Session,
        project_id: str,
        raw_text: str,
        segments: list[FeedbackSegment],
        source: str = "manual_paste",
    ) -> FeedbackDataset:
        """
        Persist a full structured dataset.
        Called immediately after Agent 1 produces segments,
        before Agent 2 runs sentiment-based optimization.
        """
        dataset = FeedbackDataset(
            id=str(uuid.uuid4()),
            project_id=project_id,
            raw_text=raw_text,
            source=source,
        )
        db.add(dataset)

        for position, seg in enumerate(segments):
            db.add(FeedbackSegmentRecord(
                id=str(uuid.uuid4()),
                dataset_id=dataset.id,
                position=position,
                timestamp=seg.timestamp,
                topic=seg.topic,
                sentiment=seg.sentiment,
                summary=seg.summary,
                confidence=seg.confidence,
            ))

        db.commit()
        db.refresh(dataset)
        return dataset

    def get_datasets_for_project(
        self,
        db: Session,
        project_id: str,
    ) -> list[FeedbackDataset]:
        """Return all datasets for a project, newest first."""
        return (
            db.query(FeedbackDataset)
            .filter(FeedbackDataset.project_id == project_id)
            .order_by(FeedbackDataset.created_at.desc())
            .all()
        )

    def get_dataset_by_id(
        self,
        db: Session,
        dataset_id: str,
    ) -> FeedbackDataset | None:
        """Return a single dataset with all its segments."""
        return (
            db.query(FeedbackDataset)
            .filter(FeedbackDataset.id == dataset_id)
            .first()
        )

    def rename_dataset(self, db: Session, dataset_id: str, name: str) -> FeedbackDataset | None:
        """Set a user-defined name on a dataset. Returns None if not found."""
        dataset = self.get_dataset_by_id(db, dataset_id)
        if not dataset:
            return None
        dataset.name = name.strip() or None
        db.commit()
        db.refresh(dataset)
        return dataset

    def delete_dataset(self, db: Session, dataset_id: str) -> bool:
        """Delete a dataset and all its segments (cascade)."""
        dataset = self.get_dataset_by_id(db, dataset_id)
        if not dataset:
            return False
        db.delete(dataset)
        db.commit()
        return True

    def get_analytics_cache(self, db: Session, dataset_id: str) -> dict | None:
        """Return cached AnalyticsReport JSON if available, else None."""
        dataset = self.get_dataset_by_id(db, dataset_id)
        if not dataset or not dataset.analytics_cache:
            return None
        try:
            return json.loads(dataset.analytics_cache)
        except Exception:
            return None

    def set_analytics_cache(self, db: Session, dataset_id: str, report_json: str) -> None:
        """Persist a serialised AnalyticsReport against the dataset."""
        dataset = self.get_dataset_by_id(db, dataset_id)
        if not dataset:
            return
        dataset.analytics_cache = report_json
        db.commit()
