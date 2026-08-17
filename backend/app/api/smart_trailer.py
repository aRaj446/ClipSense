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
import shutil
import traceback
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session

from app.models.smart_trailer_job import SmartTrailerJob
from app.schemas.feedback import SmartTrailerJobResponse, SmartTrailerGenerateRequest, TimeSavedBreakdown, AudioSettings
from app.db.database import get_db
from app.utils.storage import SMART_UPLOAD_DIR, TRAILERS_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/smart-trailer", tags=["Smart Trailer"])

ALLOWED_VIDEO_EXTS    = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
ALLOWED_COMMENTS_EXTS = {".json", ".csv", ".txt"}


_MAX_UPLOAD_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "10240")) * 1024 * 1024


def _save_upload(file: UploadFile, dest_dir: str, suffix: str) -> str:
    """
    Stream an uploaded file to disk without buffering the entire content in RAM.
    Enforces MAX_FILE_SIZE_MB (default 10 240 MB) — raises HTTP 413 if exceeded.
    """
    ext      = os.path.splitext(file.filename or "")[1].lower()
    filename = f"{uuid.uuid4().hex}{suffix}{ext}"
    path     = os.path.join(dest_dir, filename)
    written  = 0
    chunk    = 1024 * 1024  # 1 MB chunks
    with open(path, "wb") as out:
        while True:
            buf = file.file.read(chunk)
            if not buf:
                break
            written += len(buf)
            if written > _MAX_UPLOAD_BYTES:
                out.close()
                os.remove(path)
                raise HTTPException(
                    413,
                    f"File exceeds maximum allowed size of "
                    f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            out.write(buf)
    return path


def _serialise(job: SmartTrailerJob) -> SmartTrailerJobResponse:
    output_url = None
    if job.output_path and os.path.exists(job.output_path):
        output_url = f"/trailers/{os.path.basename(job.output_path)}"

    # Expose the sample trailer so the frontend can show V1 vs V2 comparison.
    # The sample trailer is stored under uploads/smart/<job_id>/ — serve it
    # via the existing /trailers static mount by symlinking is not available on
    # Windows, so we serve it through a dedicated endpoint instead.
    sample_trailer_url = None
    if job.sample_trailer_path and os.path.exists(job.sample_trailer_path):
        sample_trailer_url = f"/smart-trailer/job/{job.id}/sample"

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
        sample_trailer_url=sample_trailer_url,
        editing_plan=editing_plan,
        analysis_report=analysis_report,
        platform=job.platform,
        clip_score=job.clip_score,
        fallback_warning=job.fallback_warning,
        error_message=job.error_message,
        raw_footage_duration_secs=job.raw_footage_duration_secs,
        fast_mode=(job.fast_mode == "true") if job.fast_mode is not None else None,
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
    body: SmartTrailerGenerateRequest = SmartTrailerGenerateRequest(),
    db: Session = Depends(get_db),
):
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in ("pending", "failed", "done"):
        raise HTTPException(400, f"Job is already {job.status}")

    job.status        = "pending"
    job.error_message = None
    job.output_path   = None
    job.editing_plan  = None
    job.analysis_report = None
    job.updated_at    = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(
        _run_smart_job,
        job_id=job_id,
        user_prompt=body.user_prompt,
        audio=body.audio,
        include_subtitles=body.include_subtitles,
        fast_mode=body.fast_mode,
    )
    logger.info("SmartTrailer: background task queued for job %s (prompt=%r, fast_mode=%s)", job_id, body.user_prompt, body.fast_mode)
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


# ── GET /smart-trailer/job/{job_id}/sample ───────────────────────────────────
# Serve the original sample trailer so the frontend can show V1 vs V2.
# Registered before /job/{job_id} to avoid route shadowing.

@router.get("/job/{job_id}/sample")
def get_sample_trailer_file(job_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import FileResponse
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.sample_trailer_path or not os.path.exists(job.sample_trailer_path):
        raise HTTPException(404, "Sample trailer file not found")
    return FileResponse(
        job.sample_trailer_path,
        media_type="video/mp4",
        filename=job.sample_trailer_original_name or os.path.basename(job.sample_trailer_path),
    )


# ── GET /smart-trailer/job/{job_id}/time-saved ───────────────────────────────
# Registered before /job/{job_id} to avoid route shadowing.

def _parse_smart_comments(job: SmartTrailerJob) -> list:
    """
    Return segment-like objects compatible with build_sensecap_csv from a smart trailer job.
    Each object exposes: .timestamp, .topic, .sentiment, .summary, .confidence, .created_at
    Priority: structured .json/.csv → .txt via LLM agent → cached timeline fallback.
    """
    from app.services.feedback_structuring_agent import FeedbackStructuringAgent
    from app.services.smart_trailer_agent import _read_comments_file
    from datetime import datetime, timezone
    import csv as _csv
    import io as _io

    _now = datetime.now(timezone.utc)

    class _Seg:
        """Minimal segment compatible with build_sensecap_csv."""
        __slots__ = ("timestamp", "topic", "sentiment", "summary", "confidence", "created_at")
        def __init__(self, timestamp, topic, sentiment, summary, confidence, created_at=None):
            self.timestamp  = timestamp
            self.topic      = topic
            self.sentiment  = sentiment
            self.summary    = summary
            self.confidence = confidence
            self.created_at = created_at or _now

    def _from_pydantic(segs):
        """Wrap FeedbackSegment pydantic objects into _Seg."""
        return [_Seg(s.timestamp, s.topic, s.sentiment, s.summary, s.confidence) for s in segs]

    if job.comments_path and os.path.exists(job.comments_path):
        raw_text = _read_comments_file(job.comments_path)
        if raw_text.strip():
            ext = os.path.splitext(job.comments_path)[1].lower()

            if ext == ".json":
                try:
                    data = json.loads(raw_text)
                    if isinstance(data, list):
                        return [
                            _Seg(
                                timestamp=item.get("timestamp"),
                                topic=item.get("topic", "General"),
                                sentiment=item.get("sentiment", "Neutral"),
                                summary=str(item.get("summary", item.get("comment", ""))),
                                confidence=float(item.get("confidence", 0.75)),
                            )
                            for item in data if isinstance(item, dict)
                        ]
                except Exception:
                    pass

            elif ext == ".csv":
                try:
                    reader = _csv.DictReader(_io.StringIO(raw_text))
                    segs = []
                    for row in reader:
                        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
                        segs.append(_Seg(
                            timestamp=row.get("timestamp") or None,
                            topic=row.get("topic", "General") or "General",
                            sentiment=row.get("sentiment", "Neutral") or "Neutral",
                            summary=row.get("summary", row.get("comment", "")),
                            confidence=float(row.get("confidence", 0.75) or 0.75),
                        ))
                    if segs:
                        return segs
                except Exception:
                    pass

            # .txt or structured parse failure → LLM/regex agent
            pydantic_segs = FeedbackStructuringAgent().parse(raw_text)
            if pydantic_segs:
                return _from_pydantic(pydantic_segs)

    # Fallback: reconstruct from cached analysis_report timeline
    if job.analysis_report:
        try:
            cached = json.loads(job.analysis_report)
            timeline = cached.get("timeline", [])
            if timeline:
                return [
                    _Seg(
                        timestamp=pt.get("timestamp"),
                        topic=pt.get("topic", "General"),
                        sentiment=pt.get("sentiment", "Neutral"),
                        summary=pt.get("summary", ""),
                        confidence=float(pt.get("confidence", 0.75)),
                    )
                    for pt in timeline
                ]
        except Exception:
            pass

    return []


@router.get("/job/{job_id}/time-saved", response_model=TimeSavedBreakdown)
def get_time_saved(job_id: str, db: Session = Depends(get_db)):
    """
    Return the auditable time-saved breakdown for a completed smart trailer job.

    Calculation (units documented in TimeSavedBreakdown docstring):

        raw_footage_duration_secs is in SECONDS (probed by FFmpeg).

        manual_editing_hours:
            raw_footage_duration_secs / 60   -> raw footage minutes
            * 0.5                            -> estimated editing hours
            / 60                             -> convert to hours
            = raw_footage_duration_secs / 60 * 0.5 / 60
            = raw_footage_duration_secs / 7200

        processing_hours:
            (job.updated_at - job.created_at).total_seconds() / 3600
            job.created_at = row inserted when files were uploaded
            job.updated_at = last DB write = job completion timestamp

        estimated_time_saved_hours:
            max(manual_editing_hours - processing_hours, 0)
    """
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "done":
        raise HTTPException(400, "Time-saved data only available for completed jobs")
    if not job.raw_footage_duration_secs or job.raw_footage_duration_secs <= 0:
        raise HTTPException(422, "Raw footage duration not recorded for this job")

    # raw_footage_duration_secs is in SECONDS — confirmed from _get_video_duration()
    raw_secs = job.raw_footage_duration_secs
    manual_editing_hours = raw_secs / 60.0 * 0.5 / 60.0   # secs -> mins -> editing-hrs -> hrs

    processing_secs = max(0.0, (job.updated_at - job.created_at).total_seconds())
    processing_hours = processing_secs / 3600.0

    estimated_time_saved_hours = max(manual_editing_hours - processing_hours, 0.0)

    return TimeSavedBreakdown(
        manual_editing_hours=round(manual_editing_hours, 4),
        processing_hours=round(processing_hours, 4),
        estimated_time_saved_hours=round(estimated_time_saved_hours, 4),
        raw_footage_duration_secs=round(raw_secs, 2),
    )


# ── GET /smart-trailer/job/{job_id}/export-csv ───────────────────────────────
# Registered before /job/{job_id} to avoid route shadowing.

@router.get("/job/{job_id}/export-csv")
def export_smart_job_csv(job_id: str, db: Session = Depends(get_db)):
    """
    Export the smart trailer's comments dataset as a Sensecap-compatible CSV.
    """
    import io
    from fastapi.responses import StreamingResponse
    from app.utils.sensecap_export import build_sensecap_csv, safe_filename

    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")

    dataset_label = job.comments_original_name or job_id[:8]
    segments = _parse_smart_comments(job)

    if not segments:
        raise HTTPException(422, "No segments available to export.")

    csv_bytes = build_sensecap_csv(segments, dataset_label)
    fname = f"sensecap_{safe_filename(dataset_label, job_id[:8])}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── GET /smart-trailer/job/{job_id}/analytics ─────────────────────────────────
# Registered before /job/{job_id} so FastAPI doesn't treat "analytics" as a job_id

@router.get("/job/{job_id}/analytics")
def get_smart_job_analytics(job_id: str, db: Session = Depends(get_db)):
    from app.services.analytics_agent import AnalyticsAgent
    from app.services.feedback_structuring_agent import FeedbackStructuringAgent
    from app.services.smart_trailer_agent import _read_comments_file
    from app.schemas.feedback import FeedbackSegment
    import csv as _csv, io as _io

    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "done":
        raise HTTPException(400, f"Analytics only available for completed jobs (current status: {job.status})")

    segs = []

    if job.comments_path and os.path.exists(job.comments_path):
        raw_text = _read_comments_file(job.comments_path)
        if raw_text.strip():
            ext = os.path.splitext(job.comments_path)[1].lower()
            if ext == ".json":
                try:
                    data = json.loads(raw_text)
                    if isinstance(data, list):
                        segs = [FeedbackSegment(
                            timestamp=item.get("timestamp"),
                            topic=item.get("topic", "General"),
                            sentiment=item.get("sentiment", "Neutral"),
                            summary=str(item.get("summary", item.get("comment", ""))),
                            confidence=float(item.get("confidence", 0.75)),
                        ) for item in data if isinstance(item, dict)]
                except Exception:
                    pass
            elif ext == ".csv":
                try:
                    reader = _csv.DictReader(_io.StringIO(raw_text))
                    for row in reader:
                        row = {k.strip().lower(): (v.strip() if v else "") for k, v in row.items()}
                        segs.append(FeedbackSegment(
                            timestamp=row.get("timestamp") or None,
                            topic=row.get("topic", "General") or "General",
                            sentiment=row.get("sentiment", "Neutral") or "Neutral",
                            summary=row.get("summary", row.get("comment", "")),
                            confidence=float(row.get("confidence", 0.75) or 0.75),
                        ))
                except Exception:
                    pass
            if not segs:
                segs = FeedbackStructuringAgent().parse(raw_text)

    if not segs and job.analysis_report:
        try:
            timeline = json.loads(job.analysis_report).get("timeline", [])
            segs = [FeedbackSegment(
                timestamp=pt.get("timestamp"),
                topic=pt.get("topic", "General"),
                sentiment=pt.get("sentiment", "Neutral"),
                summary=pt.get("summary", ""),
                confidence=float(pt.get("confidence", 0.75)),
            ) for pt in timeline]
        except Exception:
            pass

    if not segs:
        raise HTTPException(404, "No segments could be extracted. Re-generate the trailer to restore analytics.")

    return AnalyticsAgent().analyze(segs)


# ── GET /smart-trailer/job/{job_id}/gpu-info ──────────────────────────────────
# Debug/analytics endpoint — exposes device metadata recorded at generation time.
# Not surfaced in the user-facing UI; intended for ops/debugging on EC2.

@router.get("/job/{job_id}/gpu-info")
def get_gpu_info(job_id: str, db: Session = Depends(get_db)):
    """
    Return the GPU/device metadata recorded when this job was processed.
    Only available for completed jobs.
    """
    job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "done":
        raise HTTPException(400, "GPU info only available for completed jobs")
    return {
        "job_id":            job.id,
        "device_used":       job.device_used,
        "encoder_used":      job.encoder_used,
        "whisper_model_used": job.whisper_model_used,
        "fast_mode":         job.fast_mode == "true" if job.fast_mode is not None else None,
    }


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

def _run_smart_job(
    job_id: str,
    user_prompt: str | None = None,
    audio: AudioSettings | None = None,
    include_subtitles: bool = False,
    fast_mode: bool = False,
) -> None:
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
            output_path, plan, analysis, error, platform, clip_score, _, fallback_warning, raw_footage_duration = agent.generate(
                raw_footage_path=job.raw_footage_path,
                sample_trailer_path=job.sample_trailer_path,
                comments_path=job.comments_path,
                job_id=job_id,
                user_prompt=user_prompt,
                audio=audio,
                include_subtitles=include_subtitles,
                fast_mode=fast_mode,
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
            job.fallback_warning = fallback_warning
            job.fast_mode        = "true" if fast_mode else "false"
            if plan:
                job.editing_plan = plan.model_dump_json()
            if analysis:
                job.analysis_report = analysis.model_dump_json()
            # Store raw footage duration so the time-saved endpoint can use the
            # actual input length rather than the generated output length.
            if raw_footage_duration is not None:
                job.raw_footage_duration_secs = raw_footage_duration
            # Record GPU/device metadata for analytics
            from app.utils.device import collect_gpu_metadata
            _gpu_meta = collect_gpu_metadata()
            job.device_used        = _gpu_meta["device"]
            job.encoder_used       = _gpu_meta["encoder"]
            job.whisper_model_used = _gpu_meta["whisper_model"]
            logger.info(
                "SmartTrailer: job %s done — %s (device=%s encoder=%s model=%s)",
                job_id, output_path,
                _gpu_meta["device"], _gpu_meta["encoder"], _gpu_meta["whisper_model"],
            )

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
