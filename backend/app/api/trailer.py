"""
Trailer Generation API

Endpoints:
    POST /generate-trailer              — trigger trailer generation job
    GET  /trailer-job/{job_id}          — poll job status
    GET  /trailer-jobs/{project_id}     — list all jobs for a project
    GET  /all-trailers                  — all done jobs across all projects
"""

import uuid
import json
import os
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.schemas.feedback import (
    GenerateTrailerRequest,
    TrailerJobResponse,
    AnalyticsReport,
    FeedbackSegment,
)
from app.services.video_regeneration_agent import VideoRegenerationAgent
from app.services.analytics_agent import AnalyticsAgent
from app.services.video_optimization_agent import VideoOptimizationAgent
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.services.project_service import ProjectService
from app.models.trailer_job import TrailerJob
from app.db.database import get_db

router = APIRouter()

logger = logging.getLogger(__name__)

_regen_agent     = VideoRegenerationAgent()
_analytics_agent = AnalyticsAgent()
_optim_agent     = VideoOptimizationAgent()
_dataset_service = FeedbackDatasetService()
_project_service = ProjectService()


# ── POST /generate-trailer ────────────────────────────────────────────────────

@router.post("/generate-trailer", response_model=TrailerJobResponse, status_code=202)
def generate_trailer(
    body: GenerateTrailerRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    project = _project_service.get_project(body.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    ds = _dataset_service.get_dataset_by_id(db, body.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail=f"Dataset '{body.dataset_id[:8]}…' not found. It may have been deleted — please re-upload your feedback file.")

    job = TrailerJob(
        id=str(uuid.uuid4()),
        project_id=body.project_id,
        dataset_id=body.dataset_id,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    video_duration  = float(project.get("duration") or 0)
    target_duration = max(30.0, min(120.0, round(video_duration * 0.15)))

    background_tasks.add_task(
        _run_job,
        job_id=job.id,
        project=project,
        dataset_segments=ds.segments,
        target_duration=target_duration,
    )

    return _serialise(job)


# ── GET /trailer-job/{job_id} ─────────────────────────────────────────────────

@router.get("/trailer-job/{job_id}", response_model=TrailerJobResponse)
def get_trailer_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _serialise(job)


# ── GET /trailer-jobs/{project_id} ───────────────────────────────────────────

@router.get("/trailer-jobs/{project_id}", response_model=list[TrailerJobResponse])
def list_trailer_jobs(project_id: str, db: Session = Depends(get_db)):
    jobs = (
        db.query(TrailerJob)
        .filter(TrailerJob.project_id == project_id)
        .order_by(TrailerJob.created_at.desc())
        .all()
    )
    return [_serialise(j) for j in jobs]


# ── DELETE /trailer-job/{job_id} ────────────────────────────────────────────

@router.delete("/trailer-job/{job_id}", status_code=204)
def delete_trailer_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.output_path and os.path.exists(job.output_path):
        try:
            os.remove(job.output_path)
        except OSError:
            pass
    db.delete(job)
    db.commit()


# ── POST /trailer-job/{job_id}/cancel ────────────────────────────────────────

@router.post("/trailer-job/{job_id}/cancel", response_model=TrailerJobResponse)
def cancel_trailer_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("pending", "processing"):
        raise HTTPException(status_code=400, detail="Job is not in a cancellable state")
    job.status        = "failed"
    job.error_message = "Cancelled by user"
    job.updated_at    = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return _serialise(job)


# ── GET /trailer-job/{job_id}/progress (SSE) ─────────────────────────────────

@router.get("/trailer-job/{job_id}/progress")
def trailer_job_progress(job_id: str):
    """
    Server-Sent Events stream for render progress.
    Emits: data: {"stage": str, "percent": int, "message": str}
    Closes automatically when stage == "done" or "failed".
    """
    import asyncio
    import time
    from fastapi.responses import StreamingResponse
    from app.utils.render_progress import get_progress

    def _stream():
        for _ in range(300):   # max 5 minutes at 1s intervals
            entry = get_progress(job_id)
            if entry:
                payload = json.dumps({
                    "stage":   entry["stage"],
                    "percent": entry["percent"],
                    "message": entry["message"],
                    "steps":   entry.get("steps", []),
                })
                yield f"data: {payload}\n\n"
                if entry["stage"] in ("done", "failed"):
                    break
            else:
                yield f"data: {{\"stage\": \"pending\", \"percent\": 0, \"message\": \"Waiting to start\", \"steps\": []}}\n\n"
            time.sleep(1)

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── GET /all-trailers ─────────────────────────────────────────────────────────

@router.get("/all-trailers", response_model=list[TrailerJobResponse])
def all_trailers(db: Session = Depends(get_db)):
    """Return all completed trailer jobs across all projects, newest first."""
    jobs = (
        db.query(TrailerJob)
        .filter(TrailerJob.status == "done")
        .order_by(TrailerJob.created_at.desc())
        .all()
    )
    return [_serialise(j) for j in jobs]


# ── Background task ───────────────────────────────────────────────────────────

def _run_job(
    job_id: str,
    project: dict,
    dataset_segments,
    target_duration: float,
):
    from app.db.database import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
        if not job:
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        from app.utils.job_queue import job_slot
        from app.utils.render_progress import set_progress, init_steps
        _STEPS = [
            {"key": "scenes",     "label": "Detecting scenes",       "status": "pending", "percent": 0},
            {"key": "transcript", "label": "Transcribing audio",      "status": "pending", "percent": 0},
            {"key": "beats",      "label": "Analysing beat rhythm",   "status": "pending", "percent": 0},
            {"key": "planning",   "label": "Planning clip selection", "status": "pending", "percent": 0},
            {"key": "extracting", "label": "Extracting clips",        "status": "pending", "percent": 0},
            {"key": "composing",  "label": "Composing transitions",   "status": "pending", "percent": 0},
            {"key": "normalising","label": "Normalising audio",       "status": "pending", "percent": 0},
        ]
        set_progress(job_id, "queued", 0, "Waiting for previous job to finish…", steps=_STEPS)
        with job_slot():
            segments = [
                FeedbackSegment(
                    timestamp=seg.timestamp,
                    topic=seg.topic,
                    sentiment=seg.sentiment,
                    summary=seg.summary,
                    confidence=seg.confidence,
                )
                for seg in dataset_segments
            ]

            analytics: AnalyticsReport = _analytics_agent.analyze(segments)

            # Run VideoOptimizationAgent — its recommendations inform clip scoring
            # by injecting high-priority positive timestamps back into the analytics
            # timeline so VideoRegenerationAgent weights them higher.
            recommendations, _ = _optim_agent.analyze(
                segments=segments,
                video_metadata=project,
            )

            # Promote high-priority positive timestamps into the analytics timeline
            # so the clip planner treats them as anchor points
            from app.schemas.feedback import TimelinePoint
            boosted = set()
            for rec in recommendations:
                if rec.priority == "High" and rec.timestamp:
                    boosted.add(rec.timestamp)
            if boosted:
                existing_ts = {p.timestamp for p in analytics.timeline}
                for rec in recommendations:
                    if rec.timestamp and rec.timestamp not in existing_ts:
                        analytics.timeline.append(TimelinePoint(
                            timestamp=rec.timestamp,
                            topic=rec.action.split()[0] if rec.action else "General",
                            sentiment="Positive",
                            summary=rec.reason,
                            confidence=0.85,
                        ))
                logger.info("trailer: injected %d optimization timestamps into analytics", len(boosted))

            video_duration = float(project.get("duration") or 0.0)
            output_path, plan, error, platform, clip_score, gemini_used, fallback_warning = _regen_agent.generate(
                project_id=project["id"],
                analytics=analytics,
                video_duration=video_duration,
                target_duration=target_duration,
                job_id=job_id,
            )

        if error or not output_path:
            job.status        = "failed"
            job.error_message = error or "Unknown error"
            from app.utils.render_progress import set_progress
            set_progress(job_id, "failed", 100, job.error_message)
        else:
            job.status           = "done"
            job.output_path      = output_path
            job.editing_plan     = plan.model_dump_json() if plan else None
            job.platform         = platform
            job.clip_score       = clip_score
            job.gemini_used      = str(gemini_used).lower()
            job.fallback_warning = fallback_warning

        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        try:
            job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = str(exc)
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialise(job: TrailerJob) -> TrailerJobResponse:
    from app.utils.storage import TRAILERS_DIR
    import os

    output_url = None
    if job.output_path and os.path.exists(job.output_path):
        filename   = os.path.basename(job.output_path)
        output_url = f"/trailers/{filename}"

    editing_plan = None
    if job.editing_plan:
        try:
            editing_plan = json.loads(job.editing_plan)
        except Exception:
            pass

    return TrailerJobResponse(
        id=job.id,
        project_id=job.project_id,
        dataset_id=job.dataset_id,
        status=job.status,
        output_url=output_url,
        editing_plan=editing_plan,
        platform=job.platform,
        clip_score=job.clip_score,
        gemini_used=job.gemini_used == "true" if job.gemini_used is not None else None,
        fallback_warning=job.fallback_warning,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )
