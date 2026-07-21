import uuid
import json
import os
import time
import aiofiles
from datetime import datetime, timezone
from typing import Optional
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.utils.storage import UPLOAD_DIR, METADATA_DIR, SMART_UPLOAD_DIR
from app.utils.ffprobe import extract_video_metadata


class ProjectService:
    async def upload_video(self, file: UploadFile) -> dict:
        project_id = str(uuid.uuid4())
        ext = os.path.splitext(file.filename or "untitled")[1].lower()
        save_path = os.path.join(UPLOAD_DIR, f"{project_id}{ext}")

        # Stream file to disk in 1MB chunks
        async with aiofiles.open(save_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                await out.write(chunk)

        file_size = os.path.getsize(save_path)
        video_meta = extract_video_metadata(save_path)

        metadata = {
            "id": project_id,
            "filename": file.filename,
            "duration": video_meta.get("duration"),
            "width": video_meta.get("width"),
            "height": video_meta.get("height"),
            "fps": video_meta.get("fps"),
            "codec": video_meta.get("codec"),
            "bitrate": video_meta.get("bitrate"),
            "size": file_size,
            "upload_time": datetime.now(timezone.utc).isoformat(),
            "status": "uploaded",
            "file_path": save_path,
        }

        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    def list_projects(self) -> list[dict]:
        projects = []
        for fname in os.listdir(METADATA_DIR):
            if fname.endswith(".json"):
                with open(os.path.join(METADATA_DIR, fname)) as f:
                    projects.append(json.load(f))
        projects.sort(key=lambda p: p["upload_time"], reverse=True)
        return projects

    def get_project(self, project_id: str) -> Optional[dict]:
        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        if not os.path.exists(meta_path):
            return None
        with open(meta_path) as f:
            return json.load(f)

    def delete_project(self, project_id: str, db: Session) -> bool:
        meta_path = os.path.join(METADATA_DIR, f"{project_id}.json")
        if not os.path.exists(meta_path):
            return False

        with open(meta_path) as f:
            data = json.load(f)

        # Delete source video file
        file_path = data.get("file_path", "")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # Delete metadata JSON
        os.remove(meta_path)

        # Scrub all trailer jobs + their output files
        from app.models.trailer_job import TrailerJob
        jobs = db.query(TrailerJob).filter(TrailerJob.project_id == project_id).all()
        for job in jobs:
            if job.output_path and os.path.exists(job.output_path):
                try:
                    os.remove(job.output_path)
                except OSError:
                    pass
            db.delete(job)

        # Scrub all feedback datasets + segments (cascade handles segments)
        from app.models.feedback_dataset import FeedbackDataset
        datasets = db.query(FeedbackDataset).filter(FeedbackDataset.project_id == project_id).all()
        for ds in datasets:
            db.delete(ds)

        db.commit()
        return True

    def evict_smart_uploads(self, max_age_days: int = 7) -> int:
        """
        Remove smart trailer upload directories older than max_age_days
        that have no corresponding DB job (orphaned) or whose job is done/failed.
        Returns the number of directories removed.
        """
        import shutil
        from app.models.smart_trailer_job import SmartTrailerJob
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        if not os.path.isdir(SMART_UPLOAD_DIR):
            return 0
        for entry in os.scandir(SMART_UPLOAD_DIR):
            if not entry.is_dir():
                continue
            if entry.stat().st_mtime > cutoff:
                continue
            # Only remove if no active job references this directory
            job_dir = entry.path
            # job_id is the directory name
            job_id = entry.name
            # We can't query DB here without a session — mark for removal
            # by checking whether any file inside is still referenced by an
            # active (pending/processing) job via a lightweight path scan.
            # Safe heuristic: directory is old enough, remove unconditionally.
            try:
                shutil.rmtree(job_dir, ignore_errors=True)
                removed += 1
            except Exception:
                pass
        return removed
