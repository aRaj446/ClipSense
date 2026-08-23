"""
Audience Intelligence API

Endpoints:
    POST /audience-analysis                        — submit text feedback, queue background job
    POST /audience-analysis/upload                 — submit file feedback (.json/.csv/.txt), queue background job
    GET  /audience-analysis/{job_id}               — poll job status + result
    GET  /audience-analysis/{job_id}/progress      — SSE progress stream
    GET  /audience-analysis/{job_id}/report        — retrieve completed AnalyticsReport
    DELETE /audience-analysis/{job_id}             — delete job record

Pipeline stages (mapped to render_progress):
    parsing       →  0–20%
    sentiment     → 20–50%
    topics        → 50–70%
    analytics     → 70–95%
    done          → 100%
"""

import json
import uuid
import logging
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session

from app.models.audience_analysis_job import AudienceAnalysisJob
from app.schemas.feedback import (
    SubmitAudienceFeedbackRequest,
    AudienceAnalysisJobResponse,
    AnalyticsReport,
    FeedbackSegment,
)
from app.services.feedback_structuring_agent import FeedbackStructuringAgent
from app.services.analytics_agent import AnalyticsAgent
from app.services.feedback_dataset_service import FeedbackDatasetService
from app.services.project_service import ProjectService
from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audience-analysis", tags=["Audience Intelligence"])

_ALLOWED_EXTENSIONS = {".json", ".csv", ".txt"}

_structuring_agent = FeedbackStructuringAgent()
_analytics_agent   = AnalyticsAgent()
_dataset_service   = FeedbackDatasetService()
_project_service   = ProjectService()

_PIPELINE_STEPS = [
    {"key": "parsing",   "label": "Parsing feedback",       "status": "pending", "percent": 0},
    {"key": "sentiment", "label": "Sentiment analysis",     "status": "pending", "percent": 0},
    {"key": "topics",    "label": "Topic analysis",         "status": "pending", "percent": 0},
    {"key": "analytics", "label": "Generating analytics",   "status": "pending", "percent": 0},
]


# ── Serialiser ────────────────────────────────────────────────────────────────

def _serialise(job: AudienceAnalysisJob) -> AudienceAnalysisJobResponse:
    report = None
    if job.analytics_report:
        try:
            report = json.loads(job.analytics_report)
        except Exception:
            pass
    return AudienceAnalysisJobResponse(
        id=job.id,
        status=job.status,
        source=job.source,
        dataset_id=job.dataset_id,
        analytics_report=report,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


# ── POST /audience-analysis (text) ───────────────────────────────────────────

@router.post("", response_model=AudienceAnalysisJobResponse, status_code=202)
def submit_text_feedback(
    body: SubmitAudienceFeedbackRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Submit raw unstructured feedback text for background audience analysis.
    Returns a job ID immediately — poll /audience-analysis/{job_id} for results.
    """
    if not _project_service.get_project(body.project_id):
        raise HTTPException(404, "Project not found")
    if not body.feedback.strip():
        raise HTTPException(400, "Feedback text must not be empty")

    job = _create_job(db, body.project_id, body.feedback.strip(), "manual_paste")
    background_tasks.add_task(_run_analysis_job, job.id, body.project_id)
    logger.info("AudienceAnalysis: queued job %s (manual_paste)", job.id)
    return _serialise(job)


# ── POST /audience-analysis/upload (file) ────────────────────────────────────

@router.post("/upload", response_model=AudienceAnalysisJobResponse, status_code=202)
async def upload_feedback_file(
    project_id: str = Form(...),
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """
    Upload a feedback file (.json, .csv, or .txt) for background audience analysis.
    Returns a job ID immediately — poll /audience-analysis/{job_id} for results.
    """
    if not _project_service.get_project(project_id):
        raise HTTPException(404, "Project not found")

    filename = file.filename or ""
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'. Allowed: .json, .csv, .txt")

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(422, "Uploaded file is empty")

    raw_text = raw_bytes.decode("utf-8", errors="replace")
    source   = "file_upload_txt" if ext == ".txt" else "file_upload"

    job = _create_job(db, project_id, raw_text, source, file_ext=ext)
    background_tasks.add_task(_run_analysis_job, job.id, project_id, ext)
    logger.info("AudienceAnalysis: queued job %s (%s, ext=%s)", job.id, source, ext)
    return _serialise(job)


# ── GET /audience-analysis/{job_id} ──────────────────────────────────────────

@router.get("/{job_id}", response_model=AudienceAnalysisJobResponse)
def get_analysis_job(job_id: str, db: Session = Depends(get_db)):
    """Poll job status. analytics_report is populated when status == 'done'."""
    job = _get_job_or_404(db, job_id)
    return _serialise(job)


# ── GET /audience-analysis/{job_id}/progress (SSE) ───────────────────────────

@router.get("/{job_id}/progress")
def analysis_job_progress(job_id: str):
    """
    Server-Sent Events stream for audience analysis pipeline progress.
    Emits: data: {"stage": str, "percent": int, "message": str, "steps": [...]}
    """
    import time
    from fastapi.responses import StreamingResponse
    from app.utils.render_progress import get_progress

    def _stream():
        for _ in range(300):   # max 5 minutes
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
                yield 'data: {"stage": "pending", "percent": 0, "message": "Waiting to start", "steps": []}\n\n'
            time.sleep(1)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── GET /audience-analysis/{job_id}/report ───────────────────────────────────

@router.get("/{job_id}/report", response_model=AnalyticsReport)
def get_analysis_report(job_id: str, db: Session = Depends(get_db)):
    """Return the completed AnalyticsReport. 404 if not done yet."""
    job = _get_job_or_404(db, job_id)
    if job.status != "done":
        raise HTTPException(400, f"Report not ready — job status is '{job.status}'")
    if not job.analytics_report:
        raise HTTPException(500, "Job completed but report is missing")
    return AnalyticsReport(**json.loads(job.analytics_report))


# ── DELETE /audience-analysis/{job_id} ───────────────────────────────────────

@router.delete("/{job_id}", status_code=204)
def delete_analysis_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job record. Does not delete the linked feedback dataset."""
    job = _get_job_or_404(db, job_id)
    db.delete(job)
    db.commit()


# ── Private helpers ───────────────────────────────────────────────────────────

def _create_job(
    db: Session,
    project_id: str,
    raw_text: str,
    source: str,
    file_ext: str = "",
) -> AudienceAnalysisJob:
    job = AudienceAnalysisJob(
        id=str(uuid.uuid4()),
        project_id=project_id,
        source=source,
        raw_text=raw_text,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _get_job_or_404(db: Session, job_id: str) -> AudienceAnalysisJob:
    job = db.query(AudienceAnalysisJob).filter(AudienceAnalysisJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Analysis job not found")
    return job


def _parse_structured_file(raw_text: str, ext: str) -> list[FeedbackSegment] | None:
    """
    Parse .json or .csv into FeedbackSegment list.
    Returns None on failure so the caller can fall back to the structuring agent.
    """
    import csv
    import io

    if ext == ".json":
        try:
            data = json.loads(raw_text)
            if not isinstance(data, list):
                return None
            segments = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                segments.append(FeedbackSegment(
                    timestamp=item.get("timestamp"),
                    topic=item.get("topic", "General"),
                    sentiment=item.get("sentiment", "Neutral"),
                    summary=str(item.get("summary", item.get("comment", ""))),
                    confidence=float(item.get("confidence", 0.75)),
                ))
            return segments if segments else None
        except Exception as exc:
            logger.warning("AudienceAnalysis: JSON parse failed: %s", exc)
            return None

    if ext == ".csv":
        try:
            reader = csv.DictReader(io.StringIO(raw_text))
            segments = []
            for row in reader:
                row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
                segments.append(FeedbackSegment(
                    timestamp=row.get("timestamp") or None,
                    topic=row.get("topic", "General") or "General",
                    sentiment=row.get("sentiment", "Neutral") or "Neutral",
                    summary=row.get("summary", row.get("comment", "")),
                    confidence=float(row.get("confidence", 0.75) or 0.75),
                ))
            return segments if segments else None
        except Exception as exc:
            logger.warning("AudienceAnalysis: CSV parse failed: %s", exc)
            return None

    return None


# ── Background task ───────────────────────────────────────────────────────────

def _run_analysis_job(job_id: str, project_id: str, file_ext: str = "") -> None:
    """
    Background pipeline:
        1. Parsing      — extract FeedbackSegment list from raw text
        2. Sentiment    — already embedded in FeedbackStructuringAgent output
        3. Topics       — already embedded in FeedbackStructuringAgent output
        4. Analytics    — AnalyticsAgent produces full AnalyticsReport
        5. Persist      — save dataset + cache report on job record
    """
    from app.db.database import SessionLocal
    from app.utils.job_queue import job_slot
    from app.utils.render_progress import set_progress, init_steps, set_step

    db = SessionLocal()
    try:
        job = db.query(AudienceAnalysisJob).filter(AudienceAnalysisJob.id == job_id).first()
        if not job:
            logger.error("AudienceAnalysis: job %s not found", job_id)
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        set_progress(job_id, "parsing", 0, "Starting analysis pipeline…", steps=list(_PIPELINE_STEPS))
        init_steps(job_id, list(_PIPELINE_STEPS))

        with job_slot():
            # ── Stage 1: Parsing ─────────────────────────────────────────────
            set_step(job_id, "parsing", "active", 0, "Parsing feedback…", overall_percent=2)

            raw_text = job.raw_text
            if not raw_text or not raw_text.strip():
                raise ValueError("Feedback text is empty")

            # Structured file path: try direct parse first, fall back to agent
            segments: list[FeedbackSegment] | None = None
            if file_ext in (".json", ".csv"):
                segments = _parse_structured_file(raw_text, file_ext)
                if segments is None:
                    logger.warning(
                        "AudienceAnalysis: structured parse failed for %s — falling back to agent",
                        file_ext,
                    )

            if segments is None:
                segments = _structuring_agent.parse(raw_text)

            if not segments:
                raise ValueError("No feedback segments could be extracted from the input")

            set_step(job_id, "parsing", "done", 100,
                     f"{len(segments)} segments extracted", overall_percent=20)
            logger.info("AudienceAnalysis: job %s — %d segments parsed", job_id, len(segments))

            # ── Stage 2: Sentiment (already in segments — mark done) ─────────
            set_step(job_id, "sentiment", "active", 50,
                     "Classifying sentiment…", overall_percent=30)

            pos = sum(1 for s in segments if s.sentiment in ("Positive", "Praise"))
            neg = sum(1 for s in segments if s.sentiment in ("Negative", "Complaint"))
            neu = len(segments) - pos - neg

            set_step(job_id, "sentiment", "done", 100,
                     f"{pos} positive · {neg} negative · {neu} neutral",
                     overall_percent=50)

            # ── Stage 3: Topics (already in segments — mark done) ────────────
            set_step(job_id, "topics", "active", 50,
                     "Aggregating topics…", overall_percent=55)

            from collections import Counter
            topic_counts = Counter(s.topic for s in segments)
            top_topics   = ", ".join(t for t, _ in topic_counts.most_common(3))

            set_step(job_id, "topics", "done", 100,
                     f"Top topics: {top_topics}", overall_percent=70)

            # ── Stage 4: Analytics ───────────────────────────────────────────
            set_step(job_id, "analytics", "active", 0,
                     "Generating analytics report…", overall_percent=72)

            report = _analytics_agent.analyze(segments)

            set_step(job_id, "analytics", "done", 100,
                     "Analytics complete", overall_percent=90)

            # ── Persist dataset + cache report ───────────────────────────────
            dataset = _dataset_service.save_dataset(
                db=db,
                project_id=project_id,
                raw_text=raw_text,
                segments=segments,
                source=job.source,
            )
            report_json = report.model_dump_json()
            _dataset_service.set_analytics_cache(db, dataset.id, report_json)

            job.status           = "done"
            job.dataset_id       = dataset.id
            job.analytics_report = report_json
            job.updated_at       = datetime.now(timezone.utc)
            db.commit()

            set_progress(job_id, "done", 100, "Analysis complete")
            logger.info(
                "AudienceAnalysis: job %s done — dataset=%s segments=%d topics=%d",
                job_id, dataset.id, len(segments), len(report.topic_breakdown),
            )

    except Exception:
        tb = traceback.format_exc()
        logger.error("AudienceAnalysis: job %s failed:\n%s", job_id, tb)
        try:
            job = db.query(AudienceAnalysisJob).filter(AudienceAnalysisJob.id == job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = tb[:2000]
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
                from app.utils.render_progress import set_progress
                set_progress(job_id, "failed", 100, tb[:200])
        except Exception:
            pass
    finally:
        db.close()
