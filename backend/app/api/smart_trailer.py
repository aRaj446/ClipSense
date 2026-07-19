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
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.models.smart_trailer_job import SmartTrailerJob
from app.schemas.feedback import SmartTrailerJobResponse
from app.db.database import get_db
from app.utils.storage import SMART_UPLOAD_DIR, TRAILERS_DIR

router = APIRouter(prefix="/smart-trailer", tags=["Smart Trailer"])

ALLOWED_VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_COMMENTS_EXTS = {".json", ".csv", ".txt"}


def _save_upload(file: UploadFile, dest_dir: str, suffix: str) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    filename = f"{uuid.uuid4().hex}{suffix}{ext}"
    path = os.path.join(dest_dir, filename)
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
        gemini_used=job.gemini_used == "true" if job.gemini_used is not None else None,
        fallback_warning=job.fallback_warning,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


# POST /smart-trailer/upload

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


# POST /smart-trailer/generate/{job_id}

@router.post("/generate/{job_id}", response_model=SmartTrailerJobResponse, status_code=202)
def generate_smart_trailer(
    job_id: str,
    db: Session = Depends(get_db),
):
    import threading
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("pending", "failed"):
        raise HTTPException(400, f"Job is already {job.status}")

    job.status        = "pending"
    job.error_message = None
    job.updated_at    = datetime.now(timezone.utc)
    db.commit()

    t = threading.Thread(target=_run_smart_job, kwargs={"job_id": job_id}, daemon=True)
    t.start()
    import sys
    print(f"[GENERATE] thread started for job {job_id}, alive={t.is_alive()}", flush=True, file=sys.stderr)
    return _serialise(job)


# GET /smart-trailer/job/{job_id}
# NOTE: /job/{job_id}/analytics is registered first so FastAPI doesn't swallow
# the literal path segment "analytics" as a job_id value.

@router.get("/job/{job_id}/analytics")
def get_smart_job_analytics(job_id: str, db: Session = Depends(get_db)):
    """
    Re-parse the uploaded comments file through FeedbackStructuringAgent
    then run AnalyticsAgent on the resulting segments.
    Returns the same AnalyticsReport shape as GET /analytics/{dataset_id}.
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


@router.get("/job/{job_id}", response_model=SmartTrailerJobResponse)
def get_smart_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    return _serialise(job)


# GET /smart-trailer/jobs

@router.get("/jobs", response_model=list[SmartTrailerJobResponse])
def list_smart_jobs(db: Session = Depends(get_db)):
    jobs = (
        db.query(SmartTrailerJob)
        .order_by(SmartTrailerJob.created_at.desc())
        .all()
    )
    return [_serialise(j) for j in jobs]


# DELETE /smart-trailer/job/{job_id}

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


# POST /smart-trailer/job/{job_id}/cancel

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


# Background task

def _run_smart_job(job_id: str) -> None:
    from app.db.database import SessionLocal
    from app.services.smart_trailer_agent import SmartTrailerAgent
    import os, traceback

    _LOG_PATH = r"C:\Users\7000039334\Documents\Gearshift\Clipsense\backend\thread_env.log"

    try:
        with open(_LOG_PATH, "a") as f:
            f.write(f"job_id={job_id}\n")
            f.write(f"FREE={os.getenv('GEMINI_FREE_API_KEY', 'MISSING')[:10]}\n")
            f.write(f"PAID={os.getenv('GEMINI_PAID_API_KEY', 'MISSING')[:10]}\n")
            import google.genai as genai
            f.write(f"genai_file={genai.__file__}\n")
            try:
                client = genai.Client(api_key=os.getenv('GEMINI_FREE_API_KEY'))
                r = client.models.generate_content(model='models/gemini-3.1-flash-lite', contents='hi')
                f.write(f"thread_live_call=OK: {r.text[:20]}\n")
            except Exception:
                f.write(f"thread_live_call=FAILED:\n{traceback.format_exc()}\n")
            f.flush()
    except Exception:
        pass

    db = SessionLocal()
    try:
        job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
        if not job:
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        import traceback, sys
        _LOG = open("smart_job_debug.log", "a", buffering=1)

        agent = SmartTrailerAgent()
        try:
            output_path, plan, analysis, error, platform, clip_score, gemini_used, fallback_warning = agent.generate(
                raw_footage_path=job.raw_footage_path,
                sample_trailer_path=job.sample_trailer_path,
                comments_path=job.comments_path,
                job_id=job_id,
            )
        except Exception:
            tb = traceback.format_exc()
            _LOG.write("[SMART JOB] agent.generate() raised:\n" + tb + "\n")
            _LOG.flush()
            job.status        = "failed"
            job.error_message = tb
            job.updated_at    = datetime.now(timezone.utc)
            db.commit()
            return
        finally:
            _LOG.close()

        if error or not output_path:
            job.status        = "failed"
            job.error_message = error or "Unknown error"
        else:
            job.status           = "done"
            job.output_path      = output_path
            job.platform         = platform
            job.clip_score       = clip_score
            job.gemini_used      = str(gemini_used).lower()
            job.fallback_warning = fallback_warning
            if plan:
                job.editing_plan = plan.model_dump_json()
            if analysis:
                job.analysis_report = analysis.model_dump_json()

        job.updated_at = datetime.now(timezone.utc)
        db.commit()

    except Exception as exc:
        import traceback, sys
        print("[SMART JOB ERROR] Full traceback:", flush=True, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        try:
            job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = traceback.format_exc()
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
