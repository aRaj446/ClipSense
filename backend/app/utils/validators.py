import os
from fastapi import UploadFile, HTTPException

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi"}
ALLOWED_MIME_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo"}


def validate_video_file(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid MIME type '{file.content_type}'.",
        )
