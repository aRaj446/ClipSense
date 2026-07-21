"""
Smart Trailer API

Endpoints:
    POST /smart-trailer/upload              - upload raw footage, sample trailer, comments file
    POST /smart-trailer/generate/{job_id}   - trigger generation on an uploaded job
    GET  /smart-trailer/job/{job_id}        - poll job status
    GET  /smart-trailer/jobs                - list all smart trailer jobs
    DELETE /smart-trailer/job/{job_id}      - delete job + files
    POST /smart-trailer/job/{job_id}/cancel - cancel in-flight job
"""

import os
import uuid
import json
import logging
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.models.smart_trailer_job import SmartTrailerJob
from app.schemas.feedback import SmartTrailerJobResponse
from app.db.database import get_db
from app.utils.storage import SMART_UPLOAD_DIR, TRAILERS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-trailer", tags=["Smart Trailer"])

ALLOWED_VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_COMMENTS_EXTS = {".json", ".csv", ".txt"}


def _save_upload(file: UploadFile, dest_dir: str, suffix: str) -> str:
    ext      = os.path.splitext(file.filename or "")[1].lower()
    filename = f"{uuid.uuid4().hex}{suffix}{ext}"
    path     = os.path.join(dest_dir, filename)
    with open(path, "wb") as f:
        f.write(file.file.read())
    return path


def _serialise(job: SmartTrailerJob) -> SmartTrailerJobResponse:
    output_url = None
    if job.output_path and os.path.exists(job.output_path):
        output_url = f"/trailers/{os.path.basename(job.output_path)}"

    editing_plan = None
    if job.editing_plan:
        try:
            editing_plan = json.loads(job.editing_plan)
        except Exception:
            pass

    analysis_report = None
    if job.analysis_report:
        try:
            analysis_report = json.loads(job.analysis_report)
        except Exception:
            pass

    return SmartTrailerJobResponse(
        id=job.id,
        raw_footage_name=job.raw_footage_original_name or os.path.basename(job.raw_footage_path),
        sample_trailer_name=job.sample_trailer_original_name or os.path.basename(job.sample_trailer_path),
        comments_name=job.comments_original_name or os.path.basename(job.comments_path),
        status=job.status,
        output_url=output_url,
        editing_plan=editing_plan,
        analysis_report=analysis_report,
        platform=job.platform,
        clip_score=job.clip_score,
        gemini_used=False,
        fallback_warning=job.fallback_warning,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


# ── POST /smart-trailer/upload ────────────────────────────────────────────────

@router.post("/upload", response_model=SmartTrailerJobResponse, status_code=201)
async def upload_smart_trailer_files(
    raw_footage:    UploadFile = File(..., description="Long-form unedited raw footage"),
    sample_trailer: UploadFile = File(..., description="Reference sample trailer"),
    comments_file:  UploadFile = File(..., description="Audience comments dataset (.json/.csv/.txt)"),
    db: Session = Depends(get_db),
):
    raw_ext      = os.path.splitext(raw_footage.filename    or "")[1].lower()
    sample_ext   = os.path.splitext(sample_trailer.filename or "")[1].lower()
    comments_ext = os.path.splitext(comments_file.filename  or "")[1].lower()

    if raw_ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(400, f"Raw footage must be a video file ({', '.join(ALLOWED_VIDEO_EXTS)})")
    if sample_ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(400, f"Sample trailer must be a video file ({', '.join(ALLOWED_VIDEO_EXTS)})")
    if comments_ext not in ALLOWED_COMMENTS_EXTS:
        raise HTTPException(400, f"Comments file must be {', '.join(ALLOWED_COMMENTS_EXTS)}")

    job_id  = str(uuid.uuid4())
    job_dir = os.path.join(SMART_UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    raw_path      = _save_upload(raw_footage,    job_dir, "_raw")
    sample_path   = _save_upload(sample_trailer, job_dir, "_sample")
    comments_path = _save_upload(comments_file,  job_dir, "_comments")

    job = SmartTrailerJob(
        id=job_id,
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        comments_path=comments_path,
        raw_footage_original_name=raw_footage.filename,
        sample_trailer_original_name=sample_trailer.filename,
        comments_original_name=comments_file.filename,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return _serialise(job)


# ── POST /smart-trailer/generate/{job_id} ────────────────────────────────────

@router.post("/generate/{job_id}", response_model=SmartTrailerJobResponse, status_code=202)
def generate_smart_trailer(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("pending", "failed"):
        raise HTTPException(400, f"Job is already {job.status}")

    job.status        = "pending"
    job.error_message = None
    job.updated_at    = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(_run_smart_job, job_id=job_id)
    logger.info("SmartTrailer: background task queued for job %s", job_id)
    return _serialise(job)


# ── GET /smart-trailer/job/{job_id}/progress (SSE) ───────────────────────────

@router.get("/job/{job_id}/progress")
def smart_trailer_job_progress(job_id: str):
    """
    Server-Sent Events stream for smart trailer render progress.
    Emits: data: {"stage": str, "percent": int, "message": str}
    """
    import time
    import json
    from fastapi.responses import StreamingResponse
    from app.utils.render_progress import get_progress

    def _stream():
        for i in range(600):   # max 10 minutes
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
            time.sleep(0.5 if i < 10 else 1)

    return StreamingResponse(_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── GET /smart-trailer/job/{job_id}/analytics ─────────────────────────────────
# Registered before /job/{job_id} so FastAPI doesn't treat "analytics" as a job_id

@router.get("/job/{job_id}/analytics")
def get_smart_job_analytics(job_id: str, db: Session = Depends(get_db)):
    """
    Re-parse the uploaded comments file through FeedbackStructuringAgent
    then run AnalyticsAgent on the resulting segments.
    """
    from app.services.feedback_structuring_agent import FeedbackStructuringAgent
    from app.services.analytics_agent import AnalyticsAgent
    from app.services.smart_trailer_agent import _read_comments_file

    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "done":
        raise HTTPException(400, "Analytics only available for completed jobs")

    raw_text = _read_comments_file(job.comments_path)
    if not raw_text.strip():
        raise HTTPException(422, "Comments file is empty or unreadable")

    segments = FeedbackStructuringAgent().parse(raw_text)
    if not segments:
        raise HTTPException(422, "No segments could be extracted from comments file")

    return AnalyticsAgent().analyze(segments)


# ── GET /smart-trailer/job/{job_id} ──────────────────────────────────────────

@router.get("/job/{job_id}", response_model=SmartTrailerJobResponse)
def get_smart_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return _serialise(job)


# ── GET /smart-trailer/jobs ───────────────────────────────────────────────────

@router.get("/jobs", response_model=list[SmartTrailerJobResponse])
def list_smart_jobs(db: Session = Depends(get_db)):
    jobs = (
        db.query(SmartTrailerJob)
        .order_by(SmartTrailerJob.created_at.desc())
        .all()
    )
    return [_serialise(j) for j in jobs]


# ── DELETE /smart-trailer/job/{job_id} ───────────────────────────────────────

@router.delete("/job/{job_id}", status_code=204)
def delete_smart_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    job_dir = os.path.join(SMART_UPLOAD_DIR, job_id)
    if os.path.isdir(job_dir):
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)

    if job.output_path and os.path.exists(job.output_path):
        try:
            os.remove(job.output_path)
        except OSError:
            pass

    db.delete(job)
    db.commit()


# ── POST /smart-trailer/job/{job_id}/cancel ───────────────────────────────────

@router.post("/job/{job_id}/cancel", response_model=SmartTrailerJobResponse)
def cancel_smart_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("pending", "processing"):
        raise HTTPException(400, "Job is not in a cancellable state")

    job.status        = "failed"
    job.error_message = "Cancelled by user"
    job.updated_at    = datetime.now(timezone.utc)
    db.commit()
    db.refresh(job)
    return _serialise(job)


# ── Background task ───────────────────────────────────────────────────────────

def _run_smart_job(job_id: str) -> None:
    from app.db.database import SessionLocal
    from app.services.smart_trailer_agent import SmartTrailerAgent

    db = SessionLocal()
    try:
        job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
        if not job:
            logger.error("SmartTrailer: job %s not found in DB", job_id)
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("SmartTrailer: job %s started", job_id)

        from app.utils.job_queue import job_slot
        from app.utils.render_progress import set_progress, init_steps
        _STEPS = [
            {"key": "comments",    "label": "Parsing audience comments",  "status": "pending", "percent": 0},
            {"key": "sample",      "label": "Analysing sample trailer",    "status": "pending", "percent": 0},
            {"key": "scenes",      "label": "Detecting scenes",            "status": "pending", "percent": 0},
            {"key": "transcript",  "label": "Transcribing audio",          "status": "pending", "percent": 0},
            {"key": "beats",       "label": "Analysing beat rhythm",       "status": "pending", "percent": 0},
            {"key": "planning",    "label": "Planning clip selection",     "status": "pending", "percent": 0},
            {"key": "extracting",  "label": "Extracting clips",            "status": "pending", "percent": 0},
            {"key": "composing",   "label": "Composing transitions",       "status": "pending", "percent": 0},
            {"key": "normalising", "label": "Normalising audio",           "status": "pending", "percent": 0},
        ]
        set_progress(job_id, "queued", 0, "Waiting for previous job to finish…", steps=_STEPS)
        with job_slot():
            agent = SmartTrailerAgent()
            output_path, plan, analysis, error, platform, clip_score, _, fallback_warning = agent.generate(
                raw_footage_path=job.raw_footage_path,
                sample_trailer_path=job.sample_trailer_path,
                comments_path=job.comments_path,
                job_id=job_id,
            )

        if error or not output_path:
            job.status        = "failed"
            job.error_message = error or "Unknown error"
            logger.error("SmartTrailer: job %s failed — %s", job_id, job.error_message)
            from app.utils.render_progress import set_progress
            set_progress(job_id, "failed", 100, job.error_message)
        else:
            job.status           = "done"
            job.output_path      = output_path
            job.platform         = platform
            job.clip_score       = clip_score
            job.gemini_used      = "false"
            job.fallback_warning = fallback_warning
            if plan:
                job.editing_plan = plan.model_dump_json()
            if analysis:
                job.analysis_report = analysis.model_dump_json()
            logger.info("SmartTrailer: job %s done — %s", job_id, output_path)

        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    except Exception:
        tb = traceback.format_exc()
        logger.error("SmartTrailer: job %s raised exception:\n%s", job_id, tb)
        try:
            job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = tb[:2000]   # cap to avoid DB overflow
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
                from app.utils.render_progress import set_progress
                set_progress(job_id, "failed", 100, job.error_message[:200])
        except Exception:
            pass
    finally:
        db.close()
