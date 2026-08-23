"""
Projects API

Endpoints:
    POST /upload-project                      — unified 3-file upload
    POST /upload                              — legacy single-file upload
    GET  /projects                            — list all projects
    GET  /project/{id}                        — get single project
    GET  /project/{id}/analytics-status       — analytics readiness + sentiment summary
    POST /project/{id}/run-analytics          — run (or return cached) analytics
    POST /project/{id}/generate-trailer       — generate trailer from project files
    GET  /project/{id}/trailers               — list generated trailers for project
    DELETE /project/{id}                      — delete project + cascade
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional

from app.schemas.project import (
    ProjectResponse, ProjectListItem, UploadProjectResponse,
    ProjectAnalyticsStatus, ProjectGenerationRequest, ProjectTrailerListItem,
)
from app.services.project_service import ProjectService
from app.utils.validators import validate_video_file
from app.utils.storage import project_generations_dir
from app.db.database import get_db

router  = APIRouter()
service = ProjectService()


def _project_gen_dir(project_id: str) -> str:
    """Return (and create) the generations directory for a project."""
    return project_generations_dir(project_id)


# ── POST /upload-project ──────────────────────────────────────────────────────

@router.post("/upload-project", response_model=UploadProjectResponse, status_code=201)
def upload_project(
    raw_footage:    UploadFile = File(..., description="Long-form unedited raw footage (video)"),
    sample_trailer: UploadFile = File(..., description="Reference sample trailer (video)"),
    feedback_file:  UploadFile = File(..., description="Audience feedback dataset (.json / .csv / .txt)"),
    name:           Optional[str] = Form(None, description="Optional project name"),
    db:             Session = Depends(get_db),
):
    validate_video_file(raw_footage)
    validate_video_file(sample_trailer)

    project_dict = service.upload_project(
        raw_footage=raw_footage,
        sample_trailer=sample_trailer,
        feedback_file=feedback_file,
        db=db,
        name=name,
    )

    dataset_id = project_dict.get("dataset_id") or ""

    return UploadProjectResponse(
        project=ProjectResponse(**{
            k: project_dict.get(k)
            for k in ProjectResponse.model_fields
        }),
        dataset_id=dataset_id,
        dataset_created=True,
    )


# ── POST /upload (legacy) ─────────────────────────────────────────────────────

@router.post("/upload", response_model=ProjectResponse, status_code=201)
async def upload_video(file: UploadFile = File(...)):
    """Legacy single-file upload. Kept for backward compatibility."""
    validate_video_file(file)
    return await service.upload_video(file)


# ── GET /projects ─────────────────────────────────────────────────────────────

@router.get("/projects", response_model=list[ProjectListItem])
def list_projects():
    return service.list_projects()


# ── GET /project/{project_id} ─────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ── GET /project/{project_id}/analytics-status ───────────────────────────────

@router.get("/project/{project_id}/analytics-status", response_model=ProjectAnalyticsStatus)
def get_analytics_status(project_id: str, db: Session = Depends(get_db)):
    """
    Return analytics readiness for a project's primary feedback dataset.
    Includes sentiment summary when analytics have already been computed.
    """
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    dataset_id = project.get("dataset_id")
    if not dataset_id:
        return ProjectAnalyticsStatus(project_id=project_id)

    from app.services.feedback_dataset_service import FeedbackDatasetService
    import os
    from urllib.parse import urlencode

    ds_service = FeedbackDatasetService()
    ds = ds_service.get_dataset_by_id(db, dataset_id)
    if not ds:
        return ProjectAnalyticsStatus(project_id=project_id, dataset_id=dataset_id)

    segment_count = len(ds.segments)
    cached = ds_service.get_analytics_cache(db, dataset_id)

    if not cached:
        return ProjectAnalyticsStatus(
            project_id=project_id,
            dataset_id=dataset_id,
            has_analytics=False,
            segment_count=segment_count,
        )

    dist      = cached.get("sentiment_distribution", {})
    breakdown = cached.get("topic_breakdown", [])
    top_topic = breakdown[0].get("topic") if breakdown else None

    base_url     = os.getenv("CLIPSENSE_BASE_URL", "http://localhost:8000").rstrip("/")
    sensecap_url = os.getenv("SENSECAP_URL", "http://localhost:8501").rstrip("/")
    csv_url      = f"{base_url}/export-dataset/{dataset_id}/csv"
    ds_name      = ds.name or project.get("name") or project.get("filename", "")[:40]
    params       = urlencode({"source": "clipsense", "dataset_url": csv_url, "dataset_name": ds_name})

    return ProjectAnalyticsStatus(
        project_id=project_id,
        dataset_id=dataset_id,
        has_analytics=True,
        segment_count=segment_count,
        positive=dist.get("Positive", 0) + dist.get("Praise", 0),
        negative=dist.get("Negative", 0) + dist.get("Complaint", 0),
        neutral=dist.get("Neutral", 0) + dist.get("Question", 0) + dist.get("Suggestion", 0),
        top_topic=top_topic,
        analyzed_at=cached.get("analyzed_at"),
        sensecap_url=f"{sensecap_url}?{params}",
    )


# ── POST /project/{project_id}/run-analytics ─────────────────────────────────

@router.post("/project/{project_id}/run-analytics", response_model=ProjectAnalyticsStatus)
def run_analytics(
    project_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
):
    """
    Run (or return cached) analytics for a project's primary feedback dataset.
    force=False: returns cached result if available.
    force=True: recomputes and overwrites the cache.
    """
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    dataset_id = project.get("dataset_id")
    if not dataset_id:
        raise HTTPException(
            status_code=404,
            detail="Project has no feedback dataset. Upload a project with a feedback file first.",
        )

    from app.services.feedback_dataset_service import FeedbackDatasetService
    from app.services.analytics_agent import AnalyticsAgent
    from app.schemas.feedback import FeedbackSegment

    ds_service = FeedbackDatasetService()
    ds = ds_service.get_dataset_by_id(db, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Feedback dataset not found")

    if not ds.segments:
        raise HTTPException(status_code=422, detail="Dataset has no segments to analyse")

    if not force:
        cached = ds_service.get_analytics_cache(db, dataset_id)
        if cached:
            return get_analytics_status(project_id, db)

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
    report = AnalyticsAgent().analyze(segments)
    ds_service.set_analytics_cache(db, dataset_id, report.model_dump_json())

    return get_analytics_status(project_id, db)


# ── POST /project/{project_id}/generate-trailer ───────────────────────────────

@router.post("/project/{project_id}/generate-trailer", status_code=202)
def generate_trailer_from_project(
    project_id: str,
    background_tasks: BackgroundTasks,
    body: ProjectGenerationRequest = ProjectGenerationRequest(),
    db: Session = Depends(get_db),
):
    """
    Generate a trailer from an existing project without re-uploading files.

    First generation: user_prompt is optional.
    Regeneration (2nd+): user_prompt is MANDATORY — the user must provide new instructions.

    Each generation creates a new SmartTrailerJob. The user_prompt is stored on the
    job row so generation history shows what instructions produced each output.
    Source files (raw footage, sample trailer, feedback) are never duplicated.
    """
    import os, uuid
    from datetime import datetime, timezone
    from app.models.smart_trailer_job import SmartTrailerJob
    from app.api.smart_trailer import _run_smart_job, _serialise

    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    raw_path      = project.get("raw_footage_path") or project.get("file_path", "")
    sample_path   = project.get("sample_trailer_path", "")
    dataset_id    = project.get("dataset_id")
    feedback_path = project.get("feedback_file_path", "")

    if not raw_path or not os.path.exists(raw_path):
        raise HTTPException(status_code=422,
            detail="Raw footage file not found. The project may have been partially deleted.")
    if not sample_path or not os.path.exists(sample_path):
        raise HTTPException(status_code=422,
            detail="Sample trailer file not found. The project may have been partially deleted.")
    if not dataset_id:
        raise HTTPException(status_code=422,
            detail="Project has no feedback dataset. Run analytics first.")
    if not feedback_path or not os.path.exists(feedback_path):
        raise HTTPException(status_code=422,
            detail="Feedback file not found. The project may have been partially deleted.")

    # Enforce mandatory prompt on regeneration (2nd+ generation)
    existing_count = (
        db.query(SmartTrailerJob)
        .filter(SmartTrailerJob.project_id == project_id)
        .count()
    )
    if existing_count > 0 and not (body.user_prompt or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Expectations are required for regeneration. Provide new instructions for this generation.",
        )

    now    = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    job    = SmartTrailerJob(
        id=job_id,
        project_id=project_id,
        dataset_id=dataset_id,
        raw_footage_path=raw_path,
        sample_trailer_path=sample_path,
        comments_path=feedback_path,
        raw_footage_original_name=project.get("raw_footage_name") or os.path.basename(raw_path),
        sample_trailer_original_name=project.get("sample_trailer_name") or os.path.basename(sample_path),
        comments_original_name=project.get("feedback_file_name") or os.path.basename(feedback_path),
        user_prompt=(body.user_prompt or "").strip() or None,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(
        _run_smart_job,
        job_id=job_id,
        user_prompt=body.user_prompt,
        audio=None,
        include_subtitles=False,
        fast_mode=body.fast_mode,
        output_dir=_project_gen_dir(project_id),
    )
    return _serialise(job)


# ── GET /project/{project_id}/trailers ────────────────────────────────────────

@router.get("/project/{project_id}/trailers", response_model=list[ProjectTrailerListItem])
def list_project_trailers(project_id: str, db: Session = Depends(get_db)):
    """List all generated trailers for a project, newest first."""
    import json, os
    from app.models.smart_trailer_job import SmartTrailerJob

    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    jobs = (
        db.query(SmartTrailerJob)
        .filter(SmartTrailerJob.project_id == project_id)
        .order_by(SmartTrailerJob.created_at.desc())
        .all()
    )

    total = len(jobs)
    result = []
    for idx, job in enumerate(jobs):
        output_url = None
        if job.output_path and os.path.exists(job.output_path):
            # Project-scoped URL (Phase 6) — served by the dedicated endpoint
            output_url = f"/project/{project_id}/generation/{job.id}/video"

        clip_count, target_duration, has_creative_dir = None, None, False
        if job.editing_plan:
            try:
                plan = json.loads(job.editing_plan)
                clip_count       = len(plan.get("clips", []))
                target_duration  = plan.get("target_duration")
                has_creative_dir = bool(job.user_prompt) or (
                    "Creative direction applied" in plan.get("rationale", "")
                )
            except Exception:
                pass

        result.append(ProjectTrailerListItem(
            job_id=job.id,
            project_id=project_id,
            dataset_id=job.dataset_id,
            generation_number=total - idx,   # oldest = 1, newest = total
            user_prompt=job.user_prompt,
            status=job.status,
            output_url=output_url,
            clip_count=clip_count,
            target_duration=target_duration,
            clip_score=job.clip_score,
            has_creative_direction=has_creative_dir,
            fast_mode=(job.fast_mode == "true") if job.fast_mode is not None else None,
            error_message=job.error_message,
            created_at=job.created_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        ))
    return result


# ── GET /project/{project_id}/generation/{job_id}/video ────────────────────────────

@router.get("/project/{project_id}/generation/{job_id}/video")
def get_project_generation_video(project_id: str, job_id: str, db: Session = Depends(get_db)):
    """
    Serve the generated trailer video for a specific project generation.
    Handles both project-scoped paths (Phase 6) and legacy flat TRAILERS_DIR paths.
    """
    import os
    from fastapi.responses import FileResponse
    from app.models.smart_trailer_job import SmartTrailerJob

    job = (
        db.query(SmartTrailerJob)
        .filter(SmartTrailerJob.id == job_id, SmartTrailerJob.project_id == project_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Generation not found")
    if not job.output_path:
        raise HTTPException(status_code=404, detail="No output file for this generation")
    if not os.path.exists(job.output_path):
        raise HTTPException(status_code=404, detail="Output file missing from disk")

    return FileResponse(
        job.output_path,
        media_type="video/mp4",
        filename=f"trailer_gen{job_id[:8]}.mp4",
    )


# ── DELETE /project/{project_id} ─────────────────────────────────────────────

@router.delete("/project/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    deleted = service.delete_project(project_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
