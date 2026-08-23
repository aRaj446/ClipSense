"""
Trailer Strategy API — Phase 3

Endpoints:
    POST /strategy/{dataset_id}/generate  — derive strategy from cached analytics, persist, return
    GET  /strategy/{dataset_id}           — return persisted strategy (404 if not yet generated)
    PUT  /strategy/{dataset_id}           — save user-edited strategy text
    POST /strategy/{dataset_id}/reset     — reset user_strategy back to generated_strategy
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.services.trailer_strategy_service import TrailerStrategyService
from app.services.strategy_agent import generate_strategy
from app.schemas.feedback import AnalyticsReport, FeedbackSegment
from app.services.analytics_agent import AnalyticsAgent

router = APIRouter(prefix="/strategy")

_dataset_svc  = FeedbackDatasetService()
_strategy_svc = TrailerStrategyService()
_analytics    = AnalyticsAgent()


class TrailerStrategyResponse(BaseModel):
    dataset_id:         str
    generated_strategy: str
    user_strategy:      str
    updated_at:         str


class UpdateStrategyRequest(BaseModel):
    user_strategy: str


def _to_response(row) -> TrailerStrategyResponse:
    return TrailerStrategyResponse(
        dataset_id=row.dataset_id,
        generated_strategy=row.generated_strategy,
        user_strategy=row.user_strategy,
        updated_at=row.updated_at.isoformat(),
    )


@router.post("/{dataset_id}/generate", response_model=TrailerStrategyResponse, status_code=201)
def generate_trailer_strategy(dataset_id: str, db: Session = Depends(get_db)):
    """
    Derive a trailer strategy from the dataset's analytics report.
    Uses the cached report if available; computes and caches it otherwise.
    Always overwrites any previously generated strategy for this dataset.
    """
    ds = _dataset_svc.get_dataset_by_id(db, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Resolve analytics report — use cache or compute fresh
    cached = _dataset_svc.get_analytics_cache(db, dataset_id)
    if cached:
        report = AnalyticsReport(**cached)
    else:
        if not ds.segments:
            raise HTTPException(status_code=422, detail="Dataset has no segments to analyse")
        segments = [
            FeedbackSegment(
                timestamp=seg.timestamp,
                topic=seg.topic,
                sentiment=seg.sentiment,
                summary=seg.summary,
                confidence=seg.confidence,
            )
            for seg in ds.segments
        ]
        report = _analytics.analyze(segments)
        _dataset_svc.set_analytics_cache(db, dataset_id, report.model_dump_json())

    strategy_text = generate_strategy(report)

    # Upsert: delete existing row then create fresh so generated_strategy is always current
    existing = _strategy_svc.get(db, dataset_id)
    if existing:
        from app.models.trailer_strategy import TrailerStrategy as _TS
        db.query(_TS).filter(_TS.dataset_id == dataset_id).delete()
        db.commit()

    row = _strategy_svc.create(db, dataset_id, strategy_text)
    return _to_response(row)


@router.get("/{dataset_id}", response_model=TrailerStrategyResponse)
def get_trailer_strategy(dataset_id: str, db: Session = Depends(get_db)):
    """Return the persisted strategy for a dataset. 404 if not yet generated."""
    row = _strategy_svc.get(db, dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not yet generated for this dataset")
    return _to_response(row)


@router.put("/{dataset_id}", response_model=TrailerStrategyResponse)
def update_trailer_strategy(
    dataset_id: str,
    body: UpdateStrategyRequest,
    db: Session = Depends(get_db),
):
    """Save the user-edited strategy. generated_strategy is never modified."""
    if not body.user_strategy.strip():
        raise HTTPException(status_code=400, detail="user_strategy must not be empty")
    row = _strategy_svc.update_user_strategy(db, dataset_id, body.user_strategy)
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found — generate it first")
    return _to_response(row)


@router.post("/{dataset_id}/reset", response_model=TrailerStrategyResponse)
def reset_trailer_strategy(dataset_id: str, db: Session = Depends(get_db)):
    """Reset user_strategy back to the original generated_strategy."""
    row = _strategy_svc.reset_to_generated(db, dataset_id)
    if not row:
        raise HTTPException(status_code=404, detail="Strategy not found — generate it first")
    return _to_response(row)
