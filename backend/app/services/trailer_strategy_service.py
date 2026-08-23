import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.trailer_strategy import TrailerStrategy


class TrailerStrategyService:

    def get(self, db: Session, dataset_id: str) -> TrailerStrategy | None:
        return (
            db.query(TrailerStrategy)
            .filter(TrailerStrategy.dataset_id == dataset_id)
            .first()
        )

    def create(self, db: Session, dataset_id: str, generated: str) -> TrailerStrategy:
        """Create a new strategy row. user_strategy starts as a copy of generated."""
        row = TrailerStrategy(
            id=str(uuid.uuid4()),
            dataset_id=dataset_id,
            generated_strategy=generated,
            user_strategy=generated,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def update_user_strategy(self, db: Session, dataset_id: str, text: str) -> TrailerStrategy | None:
        """Overwrite user_strategy only. generated_strategy is never touched."""
        row = self.get(db, dataset_id)
        if not row:
            return None
        row.user_strategy = text
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return row

    def reset_to_generated(self, db: Session, dataset_id: str) -> TrailerStrategy | None:
        """Reset user_strategy back to generated_strategy."""
        row = self.get(db, dataset_id)
        if not row:
            return None
        row.user_strategy = row.generated_strategy
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return row
