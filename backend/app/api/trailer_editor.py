"""
Trailer Editor API — Scrubber Integration Surface

Endpoints:
    GET    /editor/{job_id}         — job metadata + active editing plan
    PUT    /editor/{job_id}/plan    — save a user-modified clip list
    POST   /editor/{job_id}/render  — re-render from the current plan (new job)
    DELETE /editor/{job_id}/plan    — reset to AI-generated plan

Job resolution order (additive — existing TrailerJob behaviour unchanged):
    1. Look up TrailerJob.  If found → use existing TrailerJob path (unchanged).
    2. Look up SmartTrailerJob.  If found → use SmartTrailerJob path (new).
    3. Neither found → 404.

Design contract for the Scrubber app:
    - The AI-generated plan (TrailerJob/SmartTrailerJob.editing_plan) is NEVER mutated.
    - TrailerJob user edits are stored in trailer_edits (unchanged).
    - SmartTrailerJob user edits are stored in smart_trailer_edits (new table, no FK).
    - GET always returns the user plan when it exists, otherwise the AI plan.
    - POST /render spawns a new TrailerJob (standard) or SmartTrailerJob (smart).
    - The Scrubber can poll the new job_id via GET /trailer-job/{id} or
      GET /smart-trailer/job/{id} respectively.
"""

import json
import uuid
import os
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.trailer_job import TrailerJob
from app.models.trailer_edit import TrailerEdit
from app.models.smart_trailer_job import SmartTrailerJob
from app.models.smart_trailer_edit import SmartTrailerEdit
from app.schemas.feedback import TrailerEditingPlan, TrailerClip

router = APIRouter(prefix="/editor")
logger = logging.getLogger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────

class ClipUpdate(BaseModel):
    """A single clip in the user-modified plan. Mirrors TrailerClip."""
    start_time:      float
    end_time:        float
    reason:          str  = ""
    topic:           str  = ""
    sentiment:       str  = ""
    platform:        str | None = None
    mood_group:      str  = "calm"
    transcript_text: str  = ""
    muted:           bool = False
    speed:           float = 1.0  # Playback speed multiplier (0.25–4.0)


class UpdatePlanRequest(BaseModel):
    clips:           list[ClipUpdate]
    target_duration: float | None = None   # recalculated server-side if omitted
    audio_fade_out:  bool  = True
    output_format:   str   = "mp4"
    rationale:       str   = "User-edited plan"
    source_editor:   str   = ""  # "sensescrub" when edited via SenseScrub


class EditorJobResponse(BaseModel):
    """Full editor state returned to the Scrubber."""
    job_id:          str
    project_id:      str
    status:          str
    output_url:      str | None
    raw_footage_url: str | None   # served via GET /editor/{job_id}/raw-video
    platform:        str | None
    clip_score:      float | None
    # Active plan — user override when present, AI plan otherwise
    plan:            dict | None
    plan_source:     str          # "ai" | "user"
    plan_updated_at: str | None   # ISO timestamp of last user save
    created_at:      str
    updated_at:      str
    # Identifies which job table this came from — lets SenseScrub poll the right endpoint
    job_type:        str          # "standard" | "smart"
    # Editor tag — "sensescrub" if edited via SenseScrub
    source_editor:   str | None = None


class RenderResponse(BaseModel):
    """Returned immediately after POST /render — Scrubber polls the new job."""
    new_job_id: str
    message:    str
    job_type:   str   # "standard" | "smart"


# ── Helpers — TrailerJob (unchanged) ─────────────────────────────────────────

def _raw_footage_url_standard(job: TrailerJob) -> str | None:
    """Return a URL to serve the raw footage for a standard TrailerJob."""
    from app.utils.storage import UPLOAD_DIR
    for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
        candidate = os.path.join(UPLOAD_DIR, f"{job.project_id}{ext}")
        if os.path.exists(candidate):
            return f"/editor/{job.id}/raw-video"
    return None


def _raw_footage_url_smart(job: SmartTrailerJob) -> str | None:
    """Return a URL to serve the raw footage for a SmartTrailerJob."""
    if job.raw_footage_path and os.path.exists(job.raw_footage_path):
        return f"/editor/{job.id}/raw-video"
    return None



def _output_url_standard(job: TrailerJob) -> str | None:
    if job.output_path and os.path.exists(job.output_path):
        return f"/trailers/{os.path.basename(job.output_path)}"
    return None


def _active_plan_standard(
    job: TrailerJob, edit: TrailerEdit | None
) -> tuple[dict | None, str, str | None]:
    """Return (plan_dict, source, updated_at_iso)."""
    if edit:
        try:
            return json.loads(edit.plan_json), "user", edit.updated_at.isoformat()
        except Exception:
            pass
    if job.editing_plan:
        try:
            return json.loads(job.editing_plan), "ai", None
        except Exception:
            pass
    return None, "ai", None


def _serialise_standard(job: TrailerJob, edit: TrailerEdit | None) -> EditorJobResponse:
    plan, source, plan_ts = _active_plan_standard(job, edit)
    return EditorJobResponse(
        job_id=job.id,
        project_id=job.project_id,
        status=job.status,
        output_url=_output_url_standard(job),
        raw_footage_url=_raw_footage_url_standard(job),
        platform=job.platform,
        clip_score=job.clip_score,
        plan=plan,
        plan_source=source,
        plan_updated_at=plan_ts,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        job_type="standard",
    )


# ── Helpers — SmartTrailerJob (new) ──────────────────────────────────────────

def _output_url_smart(job: SmartTrailerJob) -> str | None:
    if not job.output_path or not os.path.exists(job.output_path):
        return None
    if job.project_id:
        return f"/project/{job.project_id}/generation/{job.id}/video"
    return f"/trailers/{os.path.basename(job.output_path)}"


def _active_plan_smart(
    job: SmartTrailerJob, edit: SmartTrailerEdit | None
) -> tuple[dict | None, str, str | None]:
    """Return (plan_dict, source, updated_at_iso)."""
    if edit:
        try:
            return json.loads(edit.plan_json), "user", edit.updated_at.isoformat()
        except Exception:
            pass
    if job.editing_plan:
        try:
            return json.loads(job.editing_plan), "ai", None
        except Exception:
            pass
    return None, "ai", None


def _serialise_smart(job: SmartTrailerJob, edit: SmartTrailerEdit | None) -> EditorJobResponse:
    plan, source, plan_ts = _active_plan_smart(job, edit)
    return EditorJobResponse(
        job_id=job.id,
        project_id=job.project_id or "",
        status=job.status,
        output_url=_output_url_smart(job),
        raw_footage_url=_raw_footage_url_smart(job),
        platform=job.platform,
        clip_score=job.clip_score,
        plan=plan,
        plan_source=source,
        plan_updated_at=plan_ts,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        job_type="smart",
    )


# ── GET /editor/{job_id}/scenes ─────────────────────────────────────────────

class SceneEntry(BaseModel):
    """A single scene available for editing — sourced from the AI plan."""
    start_time:      float
    end_time:        float
    topic:           str
    sentiment:       str
    reason:          str
    transcript_text: str
    mood_group:      str
    platform:        str | None
    muted:           bool


class ScenesResponse(BaseModel):
    scenes: list[SceneEntry]


@router.get("/{job_id}/scenes", response_model=ScenesResponse)
def get_scenes(job_id: str, db: Session = Depends(get_db)):
    """
    Return all scenes available for editing — always sourced from the original
    AI-generated plan so the user can add back deleted clips or browse all options.
    """
    def _clips_from_plan(plan_json: str | None) -> list[SceneEntry]:
        if not plan_json:
            return []
        try:
            plan = json.loads(plan_json)
            return [
                SceneEntry(
                    start_time=float(c.get("start_time", 0)),
                    end_time=float(c.get("end_time", 0)),
                    topic=c.get("topic", ""),
                    sentiment=c.get("sentiment", ""),
                    reason=c.get("reason", ""),
                    transcript_text=c.get("transcript_text", ""),
                    mood_group=c.get("mood_group", "calm"),
                    platform=c.get("platform"),
                    muted=bool(c.get("muted", False)),
                )
                for c in plan.get("clips", [])
            ]
        except Exception:
            return []

    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        return ScenesResponse(scenes=_clips_from_plan(job.editing_plan))

    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        return ScenesResponse(scenes=_clips_from_plan(smart_job.editing_plan))

    raise HTTPException(status_code=404, detail="Trailer job not found")


# ── GET /editor/{job_id}/raw-video ────────────────────────────────────────────

@router.get("/{job_id}/raw-video")
def get_raw_footage(job_id: str, db: Session = Depends(get_db)):
    """
    Serve the raw footage file for live preview in SenseScrub.
    Supports HTTP Range requests so the browser can seek without downloading the whole file.
    """
    from fastapi.responses import FileResponse
    from app.utils.storage import UPLOAD_DIR

    # Standard TrailerJob
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            candidate = os.path.join(UPLOAD_DIR, f"{job.project_id}{ext}")
            if os.path.exists(candidate):
                return FileResponse(candidate, media_type="video/mp4")
        raise HTTPException(status_code=404, detail="Raw footage not found")

    # SmartTrailerJob
    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        if smart_job.raw_footage_path and os.path.exists(smart_job.raw_footage_path):
            return FileResponse(smart_job.raw_footage_path, media_type="video/mp4")
        raise HTTPException(status_code=404, detail="Raw footage not found")

    raise HTTPException(status_code=404, detail="Job not found")


# ── GET /editor/{job_id} ──────────────────────────────────────────────────────

@router.get("/{job_id}", response_model=EditorJobResponse)
def get_editor_state(job_id: str, db: Session = Depends(get_db)):
    """
    Return job metadata and the active editing plan.
    Resolves TrailerJob first, then SmartTrailerJob.
    """
    # --- existing TrailerJob path (unchanged) ---
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        if job.status != "done":
            raise HTTPException(status_code=409, detail=f"Job is not done yet (status={job.status})")
        edit = db.query(TrailerEdit).filter(TrailerEdit.job_id == job_id).first()
        return _serialise_standard(job, edit)

    # --- SmartTrailerJob path (new) ---
    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        if smart_job.status != "done":
            raise HTTPException(status_code=409, detail=f"Job is not done yet (status={smart_job.status})")
        edit = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
        return _serialise_smart(smart_job, edit)

    raise HTTPException(status_code=404, detail="Trailer job not found")


# ── PUT /editor/{job_id}/plan ─────────────────────────────────────────────────

@router.put("/{job_id}/plan", response_model=EditorJobResponse)
def save_plan(job_id: str, body: UpdatePlanRequest, db: Session = Depends(get_db)):
    """
    Persist a user-modified clip list.
    Replaces any previous user edit for this job.
    The AI plan on the source job is never touched.
    """
    if not body.clips:
        raise HTTPException(status_code=400, detail="clips must not be empty")

    target = body.target_duration or round(
        sum(c.end_time - c.start_time for c in body.clips), 2
    )
    plan_dict = {
        "clips":           [c.model_dump() for c in body.clips],
        "target_duration": target,
        "audio_fade_out":  body.audio_fade_out,
        "output_format":   body.output_format,
        "rationale":       body.rationale,
        "source_editor":   body.source_editor,
    }

    # --- existing TrailerJob path (unchanged) ---
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        edit = db.query(TrailerEdit).filter(TrailerEdit.job_id == job_id).first()
        if edit:
            edit.plan_json  = json.dumps(plan_dict)
            edit.updated_at = datetime.now(timezone.utc)
        else:
            edit = TrailerEdit(job_id=job_id, plan_json=json.dumps(plan_dict))
            db.add(edit)
        db.commit()
        db.refresh(edit)
        return _serialise_standard(job, edit)

    # --- SmartTrailerJob path (new) ---
    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        edit = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
        if edit:
            edit.plan_json  = json.dumps(plan_dict)
            edit.updated_at = datetime.now(timezone.utc)
        else:
            edit = SmartTrailerEdit(job_id=job_id, plan_json=json.dumps(plan_dict))
            db.add(edit)
        db.commit()
        db.refresh(edit)
        return _serialise_smart(smart_job, edit)

    raise HTTPException(status_code=404, detail="Trailer job not found")


# ── POST /editor/{job_id}/render ──────────────────────────────────────────────

@router.post("/{job_id}/render", response_model=RenderResponse, status_code=202)
def render_from_plan(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Re-render the trailer from the active plan (user edit if present, AI plan otherwise).
    For TrailerJob: creates a new TrailerJob — original is preserved.
    For SmartTrailerJob: creates a new SmartTrailerJob — original is preserved.
    """
    # --- existing TrailerJob path (unchanged) ---
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        if job.status != "done":
            raise HTTPException(status_code=409, detail=f"Source job is not done (status={job.status})")
        edit = db.query(TrailerEdit).filter(TrailerEdit.job_id == job_id).first()
        plan_dict, source, _ = _active_plan_standard(job, edit)
        if not plan_dict or not plan_dict.get("clips"):
            raise HTTPException(status_code=422, detail="No editing plan available to render")

        new_job = TrailerJob(
            id=str(uuid.uuid4()),
            project_id=job.project_id,
            dataset_id=job.dataset_id,
            status="pending",
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        background_tasks.add_task(
            _run_render_job_standard,
            new_job_id=new_job.id,
            project_id=job.project_id,
            plan_dict=plan_dict,
        )
        return RenderResponse(
            new_job_id=new_job.id,
            message=f"Render started from {source} plan. Poll GET /trailer-job/{new_job.id}.",
            job_type="standard",
        )

    # --- SmartTrailerJob path (new) ---
    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        if smart_job.status != "done":
            raise HTTPException(status_code=409, detail=f"Source job is not done (status={smart_job.status})")
        edit = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
        plan_dict, source, _ = _active_plan_smart(smart_job, edit)
        if not plan_dict or not plan_dict.get("clips"):
            raise HTTPException(status_code=422, detail="No editing plan available to render")

        new_job = SmartTrailerJob(
            id=str(uuid.uuid4()),
            project_id=smart_job.project_id,
            dataset_id=smart_job.dataset_id,
            raw_footage_path=smart_job.raw_footage_path,
            sample_trailer_path=smart_job.sample_trailer_path,
            comments_path=smart_job.comments_path,
            raw_footage_original_name=smart_job.raw_footage_original_name,
            sample_trailer_original_name=smart_job.sample_trailer_original_name,
            comments_original_name=smart_job.comments_original_name,
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)

        background_tasks.add_task(
            _run_render_job_smart,
            new_job_id=new_job.id,
            raw_footage_path=smart_job.raw_footage_path,
            project_id=smart_job.project_id,
            plan_dict=plan_dict,
        )
        return RenderResponse(
            new_job_id=new_job.id,
            message=f"Render started from {source} plan. Poll GET /smart-trailer/job/{new_job.id}.",
            job_type="smart",
        )

    raise HTTPException(status_code=404, detail="Trailer job not found")


# ── GET /editor/{job_id}/render/progress (SSE) ──────────────────────────────

@router.get("/{job_id}/render/progress")
def editor_render_progress(job_id: str, new_job_id: str, db: Session = Depends(get_db)):
    """
    SSE stream for a render job spawned by POST /editor/{job_id}/render.
    Accepts ?new_job_id=<uuid> — the job id returned by the render endpoint.
    Resolves the source job type to determine which progress store key to read.
    Emits: data: {stage, percent, message, steps}
    Closes automatically when stage == "done" or "failed".
    """
    import time
    import json as _json
    from fastapi.responses import StreamingResponse
    from app.utils.render_progress import get_progress

    # Validate source job exists (determines job_type for the caller; progress
    # is keyed by new_job_id regardless of type)
    source_standard = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    source_smart    = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if not source_standard and not source_smart:
        raise HTTPException(status_code=404, detail="Source job not found")

    def _stream():
        for _ in range(600):   # max 10 minutes
            entry = get_progress(new_job_id)
            if entry:
                payload = _json.dumps({
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


# ── DELETE /editor/{job_id}/plan ──────────────────────────────────────────────

@router.delete("/{job_id}/plan", status_code=204)
def reset_plan(job_id: str, db: Session = Depends(get_db)):
    """
    Delete the user-modified plan, reverting the editor to the AI-generated plan.
    """
    # --- existing TrailerJob path (unchanged) ---
    job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    if job:
        edit = db.query(TrailerEdit).filter(TrailerEdit.job_id == job_id).first()
        if edit:
            db.delete(edit)
            db.commit()
        return

    # --- SmartTrailerJob path (new) ---
    smart_job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()
    if smart_job:
        edit = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
        if edit:
            db.delete(edit)
            db.commit()
        return

    raise HTTPException(status_code=404, detail="Trailer job not found")


# ── Shared helper: plan_dict clips → PlannedClip list (no re-processing) ─────

def _plan_to_planned_clips(plan_dict: dict) -> list:
    """
    Convert plan_dict["clips"] directly to PlannedClip objects.
    No boundary expansion, no sentence snapping, no mood reordering —
    the user's exact trim points and clip order are preserved verbatim.
    """
    from app.utils.clip_planner import PlannedClip
    return [
        PlannedClip(
            start_time=float(c["start_time"]),
            end_time=float(c["end_time"]),
            reason=c.get("reason", ""),
            topic=c.get("topic", ""),
            sentiment=c.get("sentiment", ""),
            platform=c.get("platform"),
            mood_group=c.get("mood_group", "calm"),
            transcript_text=c.get("transcript_text", ""),
            muted=bool(c.get("muted", False)),
            speed=float(c.get("speed", 1.0)),
        )
        for c in plan_dict["clips"]
    ]


# ── Background render task — standard TrailerJob ──────────────────────────────

def _run_render_job_standard(
    new_job_id: str,
    project_id: str,
    plan_dict: dict,
):
    """
    Re-render using FFmpeg from a pre-built clip plan for a standard TrailerJob.
    Clips are used exactly as stored — no re-processing that would override user edits.
    """
    from app.db.database import SessionLocal
    from app.utils.render_progress import set_progress, set_step
    from app.utils.storage import UPLOAD_DIR, TRAILERS_DIR
    from app.utils.ffmpeg_composer import compose

    _STEPS = [
        {"key": "loading",    "label": "Loading plan",          "status": "pending", "percent": 0},
        {"key": "extracting", "label": "Extracting clips",      "status": "pending", "percent": 0},
        {"key": "composing",  "label": "Composing transitions", "status": "pending", "percent": 0},
        {"key": "normalising","label": "Normalising audio",     "status": "pending", "percent": 0},
    ]

    db = SessionLocal()
    try:
        job = db.query(TrailerJob).filter(TrailerJob.id == new_job_id).first()
        if not job:
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        set_progress(new_job_id, "queued", 0, "Starting render…", steps=_STEPS)

        from app.utils.job_queue import job_slot
        with job_slot():
            input_path = None
            for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
                candidate = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")
                if os.path.exists(candidate):
                    input_path = candidate
                    break
            if not input_path:
                raise FileNotFoundError(f"Source video not found for project {project_id}")

            set_step(new_job_id, "loading", "done", 100, "Plan loaded", overall_percent=10)
            set_step(new_job_id, "extracting", "active", 0, "Preparing clips…", overall_percent=15)

            # Use clips exactly as the user edited them — no re-processing
            planned = _plan_to_planned_clips(plan_dict)
            if not planned:
                raise ValueError("No clips in plan")

            set_step(new_job_id, "extracting", "done", 100,
                     f"{len(planned)} clips ready", overall_percent=40)
            set_step(new_job_id, "composing", "active", 0, "Composing…", overall_percent=45)

            output_filename = f"{project_id}_edit_{uuid.uuid4().hex[:8]}.mp4"
            output_path     = os.path.join(TRAILERS_DIR, output_filename)

            ok, err = compose(
                planned, input_path, output_path, {},
                plan_dict.get("audio_fade_out", True),
                job_id=new_job_id,
                beats=[],
            )
            if not ok:
                raise RuntimeError(err or "FFmpeg composition failed")

        pos_count  = sum(1 for c in planned if c.sentiment in {"Positive", "Praise"})
        clip_score = round(pos_count / len(planned), 3) if planned else 0.0

        final_plan = TrailerEditingPlan(
            clips=[
                TrailerClip(
                    start_time=c.start_time, end_time=c.end_time,
                    reason=c.reason, topic=c.topic, sentiment=c.sentiment,
                    platform=c.platform, mood_group=c.mood_group,
                    transcript_text=c.transcript_text, muted=c.muted,
                )
                for c in planned
            ],
            target_duration=sum(c.end_time - c.start_time for c in planned),
            audio_fade_out=plan_dict.get("audio_fade_out", True),
            output_format=plan_dict.get("output_format", "mp4"),
            rationale=plan_dict.get("rationale", "User-edited render"),
        )

        job.status       = "done"
        job.output_path  = output_path
        job.editing_plan = final_plan.model_dump_json()
        job.platform     = planned[0].platform if planned else None
        job.clip_score   = clip_score
        job.updated_at   = datetime.now(timezone.utc)
        db.commit()

        set_progress(new_job_id, "done", 100, "Render complete")

    except Exception as exc:
        logger.exception("Editor render job %s failed", new_job_id)
        try:
            job = db.query(TrailerJob).filter(TrailerJob.id == new_job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = str(exc)
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
            set_progress(new_job_id, "failed", 100, str(exc))
        except Exception:
            pass
    finally:
        db.close()


# ── Background render task — SmartTrailerJob ──────────────────────────────────

def _run_render_job_smart(
    new_job_id: str,
    raw_footage_path: str,
    project_id: str | None,
    plan_dict: dict,
):
    """
    Re-render using FFmpeg from a pre-built clip plan for a SmartTrailerJob.
    Clips are used exactly as stored — no re-processing that would override user edits.
    """
    from app.db.database import SessionLocal
    from app.utils.render_progress import set_progress, set_step
    from app.utils.storage import TRAILERS_DIR, project_generations_dir
    from app.utils.ffmpeg_composer import compose

    _STEPS = [
        {"key": "loading",    "label": "Loading plan",          "status": "pending", "percent": 0},
        {"key": "extracting", "label": "Extracting clips",      "status": "pending", "percent": 0},
        {"key": "composing",  "label": "Composing transitions", "status": "pending", "percent": 0},
        {"key": "normalising","label": "Normalising audio",     "status": "pending", "percent": 0},
    ]

    db = SessionLocal()
    try:
        job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == new_job_id).first()
        if not job:
            return

        job.status     = "processing"
        job.updated_at = datetime.now(timezone.utc)
        db.commit()

        set_progress(new_job_id, "queued", 0, "Starting render…", steps=_STEPS)

        from app.utils.job_queue import job_slot
        with job_slot():
            input_path = os.path.normpath(os.path.abspath(raw_footage_path))
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Raw footage not found: {input_path}")

            set_step(new_job_id, "loading", "done", 100, "Plan loaded", overall_percent=10)
            set_step(new_job_id, "extracting", "active", 0, "Preparing clips…", overall_percent=15)

            # Use clips exactly as the user edited them — no re-processing
            planned = _plan_to_planned_clips(plan_dict)
            if not planned:
                raise ValueError("No clips in plan")

            set_step(new_job_id, "extracting", "done", 100,
                     f"{len(planned)} clips ready", overall_percent=40)
            set_step(new_job_id, "composing", "active", 0, "Composing…", overall_percent=45)

            if project_id:
                out_dir = project_generations_dir(project_id)
            else:
                out_dir = TRAILERS_DIR
            output_filename = f"smart_{new_job_id[:8]}_edit_{uuid.uuid4().hex[:8]}.mp4"
            output_path     = os.path.join(out_dir, output_filename)

            ok, err = compose(
                planned, input_path, output_path, {},
                plan_dict.get("audio_fade_out", True),
                job_id=new_job_id,
                beats=[],
            )
            if not ok:
                raise RuntimeError(err or "FFmpeg composition failed")

        pos_count  = sum(1 for c in planned if c.sentiment in {"Positive", "Praise"})
        clip_score = round(pos_count / len(planned), 3) if planned else 0.0

        final_plan = TrailerEditingPlan(
            clips=[
                TrailerClip(
                    start_time=c.start_time, end_time=c.end_time,
                    reason=c.reason, topic=c.topic, sentiment=c.sentiment,
                    platform=c.platform, mood_group=c.mood_group,
                    transcript_text=c.transcript_text, muted=c.muted,
                )
                for c in planned
            ],
            target_duration=sum(c.end_time - c.start_time for c in planned),
            audio_fade_out=plan_dict.get("audio_fade_out", True),
            output_format=plan_dict.get("output_format", "mp4"),
            rationale=plan_dict.get("rationale", "User-edited render"),
        )

        job.status       = "done"
        job.output_path  = output_path
        job.editing_plan = final_plan.model_dump_json()
        job.platform     = planned[0].platform if planned else None
        job.clip_score   = clip_score
        job.updated_at   = datetime.now(timezone.utc)
        db.commit()

        set_progress(new_job_id, "done", 100, "Render complete")

    except Exception as exc:
        logger.exception("Smart editor render job %s failed", new_job_id)
        try:
            job = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == new_job_id).first()
            if job:
                job.status        = "failed"
                job.error_message = str(exc)
                job.updated_at    = datetime.now(timezone.utc)
                db.commit()
            set_progress(new_job_id, "failed", 100, str(exc))
        except Exception:
            pass
    finally:
        db.close()


# ── POST /editor/{job_id}/upload-render ───────────────────────────────────────

@router.post("/{job_id}/upload-render", response_model=EditorJobResponse)
async def upload_client_render(
    job_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a client-side rendered video (from SenseScrub's WebCodecs export)
    and register it as a new trailer under the same project.

    - Creates a new SmartTrailerJob/TrailerJob with status='done'
    - Stores the uploaded file in TRAILERS_DIR
    - Tags with source_editor='sensescrub'
    - Returns the full EditorJobResponse so the client can update its state
    """
    from app.utils.storage import TRAILERS_DIR

    # Resolve source job to get project_id
    source_job = db.query(TrailerJob).filter(TrailerJob.id == job_id).first()
    source_smart = db.query(SmartTrailerJob).filter(SmartTrailerJob.id == job_id).first()

    if not source_job and not source_smart:
        raise HTTPException(status_code=404, detail="Source job not found")

    project_id = (source_job.project_id if source_job else source_smart.project_id) or ""

    # Generate unique filename and save
    new_job_id = str(uuid.uuid4())
    output_filename = f"sensescrub_{project_id}_{new_job_id[:8]}.mp4"
    output_path = os.path.join(TRAILERS_DIR, output_filename)

    os.makedirs(TRAILERS_DIR, exist_ok=True)

    # Stream file to disk
    try:
        contents = await file.read()
        with open(output_path, "wb") as f:
            f.write(contents)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"File save failed: {exc}")

    # Get the active plan from the source job
    if source_job:
        edit = db.query(TrailerEdit).filter(TrailerEdit.job_id == job_id).first()
        plan_dict, _, _ = _active_plan_standard(source_job, edit)
    else:
        edit = db.query(SmartTrailerEdit).filter(SmartTrailerEdit.job_id == job_id).first()
        plan_dict, _, _ = _active_plan_smart(source_smart, edit)

    # Tag the plan with source_editor
    if plan_dict:
        plan_dict["source_editor"] = "sensescrub"

    # Create a new job record (SmartTrailerJob for consistency with project trailers)
    new_job = SmartTrailerJob(
        id=new_job_id,
        project_id=project_id,
        raw_footage_path=source_smart.raw_footage_path if source_smart else "",
        sample_trailer_path=source_smart.sample_trailer_path if source_smart else "",
        comments_path=source_smart.comments_path if source_smart else "",
        status="done",
        output_path=output_path,
        editing_plan=json.dumps(plan_dict) if plan_dict else None,
        platform=source_smart.platform if source_smart else (source_job.platform if source_job else None),
        user_prompt="Edited and exported via SenseScrub",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(new_job)
    db.commit()
    db.refresh(new_job)

    # Return the new job as EditorJobResponse
    return EditorJobResponse(
        job_id=new_job.id,
        project_id=project_id,
        status="done",
        output_url=f"/trailers/{output_filename}",
        raw_footage_url=None,
        platform=new_job.platform,
        clip_score=None,
        plan=plan_dict,
        plan_source="user",
        plan_updated_at=new_job.updated_at.isoformat(),
        created_at=new_job.created_at.isoformat(),
        updated_at=new_job.updated_at.isoformat(),
        job_type="smart",
        source_editor="sensescrub",
    )
