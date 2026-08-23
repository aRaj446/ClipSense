import uuid
import json
import os
import shutil
import time
import aiofiles
from datetime import datetime, timezone
from typing import Optional
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.utils.storage import UPLOAD_DIR, METADATA_DIR, SMART_UPLOAD_DIR, PROJECT_UPLOAD_DIR
from app.utils.ffprobe import extract_video_metadata

_MAX_UPLOAD_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "10240")) * 1024 * 1024
_ALLOWED_FEEDBACK_EXTS = {".json", ".csv", ".txt"}


def _save_upload_sync(file: UploadFile, dest_path: str) -> None:
    """
    Stream an UploadFile to dest_path synchronously (1 MB chunks).
    Enforces MAX_FILE_SIZE_MB. Raises HTTP 413 if exceeded.
    Caller is responsible for cleanup on error.
    """
    written = 0
    chunk_size = 1024 * 1024
    with open(dest_path, "wb") as out:
        while True:
            buf = file.file.read(chunk_size)
            if not buf:
                break
            written += len(buf)
            if written > _MAX_UPLOAD_BYTES:
                out.close()
                os.remove(dest_path)
                raise HTTPException(
                    413,
                    f"File exceeds maximum allowed size of "
                    f"{_MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            out.write(buf)


class ProjectService:

    # ── New unified upload (Phase 2) ──────────────────────────────────────────

    def upload_project(
        self,
        raw_footage: UploadFile,
        sample_trailer: UploadFile,
        feedback_file: UploadFile,
        db: Session,
        name: str | None = None,
    ) -> dict:
        """
        Create a new project from three uploaded files.

        Steps:
            1. Validate file extensions
            2. Create project directory
            3. Save all three files (streaming, enforces MAX_FILE_SIZE_MB)
            4. ffprobe raw footage for metadata
            5. INSERT projects row
            6. Parse feedback file → FeedbackSegment list (deduped)
            7. INSERT feedback_datasets + feedback_segments rows
            8. Return project dict (same shape as get_project())

        On any failure after files are saved, the project directory is cleaned up.
        """
        from app.models.project import Project
        from app.services.feedback_dataset_service import FeedbackDatasetService
        from app.services.feedback_structuring_agent import FeedbackStructuringAgent
        from app.api.feedback import _parse_file  # reuse existing structured parser

        # ── Validate extensions ───────────────────────────────────────────────
        raw_ext      = os.path.splitext(raw_footage.filename    or "")[1].lower()
        sample_ext   = os.path.splitext(sample_trailer.filename or "")[1].lower()
        feedback_ext = os.path.splitext(feedback_file.filename  or "")[1].lower()

        from app.utils.validators import ALLOWED_EXTENSIONS as _VIDEO_EXTS
        if raw_ext not in _VIDEO_EXTS:
            raise HTTPException(400, f"Raw footage must be a video file ({', '.join(_VIDEO_EXTS)})")
        if sample_ext not in _VIDEO_EXTS:
            raise HTTPException(400, f"Sample trailer must be a video file ({', '.join(_VIDEO_EXTS)})")
        if feedback_ext not in _ALLOWED_FEEDBACK_EXTS:
            raise HTTPException(400, f"Feedback file must be .json, .csv, or .txt")

        project_id  = str(uuid.uuid4())
        project_dir = os.path.join(PROJECT_UPLOAD_DIR, project_id)
        os.makedirs(project_dir, exist_ok=True)

        raw_path      = os.path.join(project_dir, f"raw{raw_ext}")
        sample_path   = os.path.join(project_dir, f"sample{sample_ext}")
        feedback_path = os.path.join(project_dir, f"feedback{feedback_ext}")

        saved: list[str] = []
        try:
            _save_upload_sync(raw_footage,    raw_path);      saved.append(raw_path)
            _save_upload_sync(sample_trailer, sample_path);   saved.append(sample_path)
            _save_upload_sync(feedback_file,  feedback_path); saved.append(feedback_path)
        except HTTPException:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise
        except Exception as exc:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(500, f"File save failed: {exc}") from exc

        # ── ffprobe raw footage ───────────────────────────────────────────────
        try:
            video_meta = extract_video_metadata(raw_path)
        except Exception:
            video_meta = {}

        raw_size = os.path.getsize(raw_path)
        now      = datetime.now(timezone.utc)

        # ── Persist project row ───────────────────────────────────────────────
        try:
            project_row = Project(
                id=project_id,
                name=(name.strip()[:255] if name and name.strip() else None),
                raw_footage_path=raw_path,
                sample_trailer_path=sample_path,
                feedback_file_path=feedback_path,
                raw_footage_name=raw_footage.filename,
                sample_trailer_name=sample_trailer.filename,
                feedback_file_name=feedback_file.filename,
                duration=video_meta.get("duration"),
                width=video_meta.get("width"),
                height=video_meta.get("height"),
                fps=video_meta.get("fps"),
                codec=video_meta.get("codec"),
                bitrate=video_meta.get("bitrate"),
                size=raw_size,
                status="uploaded",
                created_at=now,
                updated_at=now,
            )
            db.add(project_row)
            db.flush()  # get the id into the session without committing yet
        except Exception as exc:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(500, f"Failed to create project record: {exc}") from exc

        # ── Parse feedback file ───────────────────────────────────────────────
        try:
            with open(feedback_path, "rb") as fh:
                raw_bytes = fh.read()
            raw_text = raw_bytes.decode("utf-8", errors="replace")

            if feedback_ext == ".txt":
                agent    = FeedbackStructuringAgent()
                segments = agent.parse(raw_text)
                source   = "project_upload_txt"
            else:
                segments = _parse_file(raw_text, feedback_ext)
                source   = "project_upload"

            if not segments:
                raise ValueError("Feedback file contained no valid segments.")

        except HTTPException:
            db.rollback()
            shutil.rmtree(project_dir, ignore_errors=True)
            raise
        except Exception as exc:
            db.rollback()
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(422, f"Feedback file could not be parsed: {exc}") from exc

        # ── Persist feedback dataset (deduped) ────────────────────────────────
        try:
            ds_service = FeedbackDatasetService()
            dataset, created = ds_service.save_dataset_deduped(
                db=db,
                project_id=project_id,
                raw_text=raw_text,
                segments=segments,
                source=source,
                sample_trailer_path=sample_path,
            )
            project_row.dataset_id = dataset.id
            db.commit()
            db.refresh(project_row)
        except Exception as exc:
            db.rollback()
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(500, f"Failed to persist feedback dataset: {exc}") from exc

        # ── Also write legacy JSON metadata for backward compat ───────────────
        metadata = self._project_row_to_dict(project_row)
        try:
            meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass  # non-fatal — DB row is authoritative

        return metadata

    # ── Legacy single-file upload (kept for backward compat) ─────────────────

    async def upload_video(self, file: UploadFile) -> dict:
        project_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename or "untitled")[1].lower()
        save_path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")

        async with aiofiles.open(save_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                await out.write(chunk)

        file_size  = os.path.getsize(save_path)
        video_meta = extract_video_metadata(save_path)

        metadata = {
            "id":          project_id,
            "filename":    file.filename,
            "duration":    video_meta.get("duration"),
            "width":       video_meta.get("width"),
            "height":      video_meta.get("height"),
            "fps":         video_meta.get("fps"),
            "codec":       video_meta.get("codec"),
            "bitrate":     video_meta.get("bitrate"),
            "size":        file_size,
            "upload_time": datetime.now(timezone.utc).isoformat(),
            "status":      "uploaded",
            "file_path":   save_path,
        }

        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    # ── Read / list / delete ──────────────────────────────────────────────────

    def list_projects(self) -> list[dict]:
        """
        Return all projects, newest first.
        Merges DB rows (Phase 2) with legacy JSON files (Phase 1).
        DB rows take precedence when both exist for the same project_id.
        """
        from app.db.database import SessionLocal
        from app.models.project import Project as ProjectModel

        db = SessionLocal()
        try:
            db_rows = db.query(ProjectModel).order_by(ProjectModel.created_at.desc()).all()
            db_ids  = {row.id for row in db_rows}
            projects = [self._project_row_to_dict(row) for row in db_rows]
        finally:
            db.close()

        # Append legacy JSON projects not yet in DB
        if os.path.isdir(METADATA_DIR):
            for fname in os.listdir(METADATA_DIR):
                if not fname.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(METADATA_DIR, fname)) as f:
                        data = json.load(f)
                    if data.get("id") not in db_ids:
                        projects.append(data)
                except Exception:
                    pass

        projects.sort(key=lambda p: p.get("upload_time") or p.get("created_at") or "", reverse=True)
        return projects

    def get_project(self, project_id: str) -> Optional[dict]:
        """
        Return a single project dict.
        Checks DB first (Phase 2 projects), falls back to JSON file (legacy).
        """
        from app.db.database import SessionLocal
        from app.models.project import Project as ProjectModel

        db = SessionLocal()
        try:
            row = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
            if row:
                return self._project_row_to_dict(row)
        finally:
            db.close()

        # Legacy fallback
        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                return json.load(f)
        return None

    def delete_project(self, project_id: str, db: Session) -> bool:
        """
        Delete a project and all associated data.

        Cascade order:
            1. SmartTrailerJob rows for this project — output files outside the
               project directory (legacy flat TRAILERS_DIR paths) are removed
               individually. Project-scoped outputs are removed with the dir.
            2. TrailerJob rows (legacy generation table).
            3. FeedbackDataset + FeedbackSegmentRecord rows.
            4. Project directory tree (source files + generations/).
            5. Legacy JSON metadata file.
        """
        from app.models.project import Project as ProjectModel
        from app.models.trailer_job import TrailerJob
        from app.models.smart_trailer_job import SmartTrailerJob
        from app.models.feedback_dataset import FeedbackDataset

        deleted_something = False

        project_row = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
        project_dir_abs = os.path.abspath(os.path.join(PROJECT_UPLOAD_DIR, project_id))

        # ── Cascade: smart trailer jobs (project-based generations) ──────────
        # Must happen before rmtree so we can check which outputs are inside
        # the project dir (will be removed by rmtree) vs outside (flat path).
        smart_jobs = db.query(SmartTrailerJob).filter(
            SmartTrailerJob.project_id == project_id
        ).all()
        for job in smart_jobs:
            if job.output_path and os.path.exists(job.output_path):
                # Only remove individually if it lives outside the project dir
                if not os.path.abspath(job.output_path).startswith(project_dir_abs):
                    try:
                        os.remove(job.output_path)
                    except OSError:
                        pass
            db.delete(job)

        # ── Phase 2: DB row + project directory ──────────────────────────────
        if project_row:
            if os.path.isdir(project_dir_abs):
                shutil.rmtree(project_dir_abs, ignore_errors=True)
            db.delete(project_row)
            deleted_something = True

        # ── Legacy: JSON metadata file + flat upload file ─────────────────────
        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f:
                    data = json.load(f)
                file_path = data.get("file_path", "")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass
            os.remove(meta_path)
            deleted_something = True

        # Also remove any orphaned flat upload file (legacy single-file upload)
        # even if the metadata JSON is already gone
        for ext in (".mp4", ".mov", ".avi", ".mkv", ".webm"):
            flat_path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")
            if os.path.exists(flat_path):
                try:
                    os.remove(flat_path)
                except OSError:
                    pass

        if not deleted_something:
            return False

        # ── Cascade: legacy trailer jobs ──────────────────────────────────────
        jobs = db.query(TrailerJob).filter(TrailerJob.project_id == project_id).all()
        for job in jobs:
            if job.output_path and os.path.exists(job.output_path):
                try:
                    os.remove(job.output_path)
                except OSError:
                    pass
            db.delete(job)

        # ── Cascade: feedback datasets + segments ─────────────────────────────
        datasets = db.query(FeedbackDataset).filter(
            FeedbackDataset.project_id == project_id
        ).all()
        for ds in datasets:
            db.delete(ds)

        db.commit()
        return True

    # ── Smart upload eviction ─────────────────────────────────────────────────

    def evict_smart_uploads(self, max_age_days: int = 7) -> int:
        """
        Remove stale smart upload directories older than max_age_days.
        Skips any directory that is still referenced by an active SmartTrailerJob
        (status = pending or processing) to avoid deleting in-flight source files.
        """
        from app.db.database import SessionLocal
        from app.models.smart_trailer_job import SmartTrailerJob

        cutoff  = time.time() - max_age_days * 86400
        removed = 0

        if not os.path.isdir(SMART_UPLOAD_DIR):
            return 0

        # Collect job dirs that are still active — do not evict these
        db = SessionLocal()
        try:
            active_jobs = db.query(SmartTrailerJob).filter(
                SmartTrailerJob.status.in_(("pending", "processing"))
            ).all()
            active_dirs = set()
            for job in active_jobs:
                for path in (job.raw_footage_path, job.sample_trailer_path, job.comments_path):
                    if path:
                        parent = os.path.dirname(os.path.abspath(path))
                        active_dirs.add(parent)
        finally:
            db.close()

        for entry in os.scandir(SMART_UPLOAD_DIR):
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime > cutoff:
                continue
            if os.path.abspath(entry.path) in active_dirs:
                continue
            try:
                shutil.rmtree(entry.path, ignore_errors=True)
                removed += 1
            except Exception:
                pass
        return removed

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _project_row_to_dict(row) -> dict:
        """Convert a Project ORM row to the canonical project dict shape."""
        return {
            "id":                  row.id,
            "name":                row.name,
            "filename":            row.raw_footage_name or row.raw_footage_path.split(os.sep)[-1],
            "raw_footage_path":    row.raw_footage_path,
            "sample_trailer_path": row.sample_trailer_path,
            "feedback_file_path":  row.feedback_file_path,
            "raw_footage_name":    row.raw_footage_name,
            "sample_trailer_name": row.sample_trailer_name,
            "feedback_file_name":  row.feedback_file_name,
            "dataset_id":          row.dataset_id,
            "duration":            row.duration,
            "width":               row.width,
            "height":              row.height,
            "fps":                 row.fps,
            "codec":               row.codec,
            "bitrate":             row.bitrate,
            "size":                row.size or 0,
            "upload_time":         row.created_at.isoformat(),
            "status":              row.status,
            "file_path":           row.raw_footage_path,  # backward compat alias
        }
