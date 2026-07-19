from dotenv import load_dotenv
load_dotenv(override=True)  # Must be first — override ensures .env values always win

import os, sys

# Add imageio_ffmpeg binary to PATH so Whisper can find ffmpeg
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

print("[STARTUP] CWD:", os.getcwd(), flush=True, file=sys.stderr)
print("[STARTUP] FREE KEY:", os.getenv("GEMINI_FREE_API_KEY", "MISSING")[:10], flush=True, file=sys.stderr)
print("[STARTUP] PAID KEY:", os.getenv("GEMINI_PAID_API_KEY", "MISSING")[:10], flush=True, file=sys.stderr)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.api import health, projects, feedback
from app.api import trailer
from app.api import smart_trailer
from app.utils.storage import ensure_directories, TRAILERS_DIR
from app.db.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    create_tables()   # Creates SQLite tables on first run — no-op on subsequent runs
    yield


app = FastAPI(
    title="ClipSense — AI Marketing Optimization Platform",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("app/uploads",  exist_ok=True)
os.makedirs(TRAILERS_DIR,   exist_ok=True)
app.mount("/uploads",  StaticFiles(directory="app/uploads"),  name="uploads")
app.mount("/trailers", StaticFiles(directory=TRAILERS_DIR),   name="trailers")

app.include_router(health.router,         tags=["Health"])
app.include_router(projects.router,       tags=["Projects"])
app.include_router(feedback.router,       tags=["Feedback Analysis"])
app.include_router(trailer.router,        tags=["Trailer Generation"])
app.include_router(smart_trailer.router,  tags=["Smart Trailer"])
