from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session

from app.schemas.project import ProjectResponse, ProjectListItem
from app.services.project_service import ProjectService
from app.utils.validators import validate_video_file
from app.db.database import get_db

router = APIRouter()
service = ProjectService()


@router.post("/upload", response_model=ProjectResponse, status_code=201)
async def upload_video(file: UploadFile = File(...)):
    validate_video_file(file)
    return await service.upload_video(file)


@router.get("/projects", response_model=list[ProjectListItem])
def list_projects():
    return service.list_projects()


@router.get("/project/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str):
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.delete("/project/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    deleted = service.delete_project(project_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Project not found")
