from dotenv import load_dotenv
load_dotenv(override=True)  # Must be first — override ensures .env values always win

import os

# Add imageio_ffmpeg binary to PATH so Whisper can find ffmpeg
try:
    import imageio_ffmpeg
    _ffmpeg_dir = os.path.dirname(imageio_ffmpeg.get_ffmpeg_exe())
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.api import health, projects, feedback
from app.api import trailer
from app.api import smart_trailer
from app.api import audience_analysis
from app.api import trailer_strategy
from app.api import trailer_editor
from app.api import admin
from app.utils.storage import ensure_directories, TRAILERS_DIR
from app.db.database import create_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_directories()
    create_tables()
    # Pre-warm HuggingFace model in a background thread so the first
    # feedback request doesn't block for 30-60s on a cold model load.
    import threading
    def _prewarm():
        try:
            from app.services.feedback_structuring_agent import _get_sentiment_classifier
            _get_sentiment_classifier()
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Model pre-warm failed: %s", exc)
        try:
            from app.services.project_service import ProjectService
            removed = ProjectService().evict_smart_uploads(max_age_days=7)
            if removed:
                import logging
                logging.getLogger(__name__).info("lifespan: evicted %d stale smart upload dir(s)", removed)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Smart upload eviction failed: %s", exc)
    threading.Thread(target=_prewarm, daemon=True, name="hf-prewarm").start()
    yield


app = FastAPI(
    title="ClipSense — AI Marketing Optimization Platform",
    version="1.0.0",
    lifespan=lifespan,
)

_CORS_ORIGINS = set(os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","))

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Range"],
)


@app.middleware("http")
async def _cross_origin_resource_policy(request, call_next):
    """
    Add Cross-Origin-Resource-Policy header to all responses so OpenReel
    (which uses Cross-Origin-Embedder-Policy: require-corp) can fetch
    resources from this backend.
    """
    response = await call_next(request)
    origin = request.headers.get("origin", "")
    if origin in _CORS_ORIGINS:
        response.headers.setdefault("Cross-Origin-Resource-Policy", "cross-origin")
    return response


@app.middleware("http")
async def _static_cors(request, call_next):
    """
    CORSMiddleware does not cover StaticFiles sub-applications because they
    are mounted directly on the ASGI stack and bypass the middleware chain.
    This middleware adds the necessary Access-Control-Allow-Origin header to
    every /trailers/* and /uploads/* response so the browser can play videos
    and load assets served from a different port (e.g. :8000 vs :5173).
    """
    response = await call_next(request)
    if request.url.path.startswith(("/trailers/", "/uploads/")):
        origin = request.headers.get("origin", "")
        if origin in _CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        elif "*" in _CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = "*"
    return response


os.makedirs("app/uploads",  exist_ok=True)
os.makedirs(TRAILERS_DIR,   exist_ok=True)
app.mount("/uploads",  StaticFiles(directory="app/uploads"),  name="uploads")
app.mount("/trailers", StaticFiles(directory=TRAILERS_DIR),   name="trailers")

app.include_router(health.router,             tags=["Health"])
app.include_router(projects.router,           tags=["Projects"])
app.include_router(feedback.router,           tags=["Feedback Analysis"])
app.include_router(trailer.router,            tags=["Trailer Generation"])
app.include_router(smart_trailer.router,      tags=["Smart Trailer"])
app.include_router(audience_analysis.router,  tags=["Audience Intelligence"])
app.include_router(trailer_strategy.router,   tags=["Trailer Strategy"])
app.include_router(trailer_editor.router,     tags=["Trailer Editor"])
app.include_router(admin.router,              tags=["Admin"])
