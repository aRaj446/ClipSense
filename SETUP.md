# ClipSense — Local Setup

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| pnpm | 8+ | `npm install -g pnpm` |
| FFmpeg | Latest | Must be on PATH. [Download](https://ffmpeg.org/download.html) |

## One-time setup

```bash
# 1. Clone the repo
git clone <repo-url> Clipsense
cd Clipsense
git checkout sensecap

# 2. Create the shared Python virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install all Python dependencies (backend + sensecap dashboard)
pip install -r requirements.txt

# 5. Install ClipSense frontend dependencies
cd frontend
npm install
cd ..

# 6. Install SenseScrub (OpenReel video editor) dependencies
cd VideoEditor/openreel-video
pnpm install
cd ../..

# 7. (Optional) Install SenseCap dashboard dependencies
# Streamlit is included in the Python requirements above — no extra step needed.
```

## Environment variables

The backend `.env` is already configured for local development. If starting fresh:

```bash
# backend/.env (already present with defaults)
UPLOAD_DIR=app/uploads
METADATA_DIR=app/metadata
MAX_FILE_SIZE_MB=10240
ALLOWED_EXTENSIONS=mp4,mov,avi
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5176
SENSECAP_URL=http://localhost:8501
CLIPSENSE_BASE_URL=http://localhost:8000
USE_GPU=false
DEVICE=auto
VIDEO_ENCODER=auto
WHISPER_MODEL=base
```

```bash
# frontend/.env (already present with defaults)
VITE_API_BASE_URL=http://localhost:8000
VITE_SENSECAP_URL=http://localhost:8501
VITE_SENSESCRUB_URL=http://localhost:5176
```

## Run everything

```bash
# From the project root — starts all 4 services in separate windows:
npm run dev
```

This launches:

| Service | URL | Description |
|---------|-----|-------------|
| Backend (FastAPI) | http://localhost:8000 | API server + video processing |
| ClipSense Frontend | http://localhost:5173 | Main dashboard UI |
| SenseScrub (OpenReel) | http://localhost:5176 | Video editor (auto-opens from ClipSense) |
| SenseCap Dashboard | http://localhost:8501 | Analytics/Streamlit dashboard |

## Run services individually

```bash
# Backend only
npm run backend

# Frontend only
npm run frontend

# SenseScrub (video editor) only
npm run openreel

# SenseCap dashboard only
npm run sensecap
```

## How it works

1. Upload a video in **ClipSense** (http://localhost:5173)
2. Upload feedback/comments and generate a trailer
3. Once generated, click **"Open in SenseScrub"** — this opens the OpenReel editor with your trailer auto-loaded
4. Edit the trailer using the full NLE (trim, split, effects, transitions, etc.)
5. Export — the video saves locally AND uploads back to ClipSense automatically

## Troubleshooting

**"pnpm: command not found"**
```bash
npm install -g pnpm
```

**FFmpeg not found**
- Windows: Download from https://www.gyan.dev/ffmpeg/builds/ → extract → add `bin/` folder to system PATH
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

**Port already in use**
```bash
# Kill all ClipSense services
npm run kill:backend
npm run kill:frontend
npm run kill:openreel
```

**CORS errors in browser console**
- Make sure `backend/.env` has `CORS_ORIGINS` including all frontend ports (5173, 5176)
- Restart the backend after changing `.env`

**OpenReel SharedArrayBuffer error**
- OpenReel requires `Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy` headers (set automatically by its Vite config)
- Use Chrome or Edge — Firefox/Safari may have issues with some WebCodecs features
