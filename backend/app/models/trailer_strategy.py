from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from app.db.base import Base


class TrailerStrategy(Base):
    """
    Persists the AI-generated and user-edited trailer strategy for a dataset.

    generated_strategy  — produced by StrategyAgent from AnalyticsReport, never overwritten
    user_strategy       — the user's current working text; starts as a copy of generated_strategy
    updated_at          — last time user_strategy was saved
    """
    __tablename__ = "trailer_strategies"

    id                 = Column(String, primary_key=True)
    dataset_id         = Column(String, ForeignKey("feedback_datasets.id"), nullable=False, unique=True, index=True)
    generated_strategy = Column(Text, nullable=False)
    user_strategy      = Column(Text, nullable=False)
    updated_at         = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<TrailerStrategy dataset_id={self.dataset_id}>"
