from pydantic import BaseModel
from typing import Optional


class ProjectResponse(BaseModel):
    id: str
    filename: str
    duration: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    codec: Optional[str] = None
    bitrate: Optional[int] = None
    size: int
    upload_time: str
    status: str


class ProjectListItem(BaseModel):
    id: str
    filename: str
    duration: Optional[float] = None
    size: int
    upload_time: str
    status: str
