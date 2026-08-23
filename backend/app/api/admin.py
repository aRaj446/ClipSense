"""
Admin API

Endpoints:
    GET /admin/storage-integrity  — verify DB paths match disk, return report
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db

router = APIRouter(prefix="/admin")


@router.get("/storage-integrity")
def storage_integrity(db: Session = Depends(get_db)):
    """
    Run a storage integrity check and return a report of any missing or
    orphaned files. Does not modify anything — read-only diagnostic.
    """
    from app.utils.storage_integrity import check_storage_integrity
    return check_storage_integrity(db)
