# ClipSense — AI Marketing Optimization Platform (Week 1)

A full-stack foundation for an AI-powered marketing video optimization platform.

## Tech Stack

- **Frontend**: React 18, Vite, TypeScript, TailwindCSS, React Router, Axios, React Hook Form
- **Backend**: Python, FastAPI, Uvicorn, FFprobe

## Prerequisites

- Node.js 18+
- Python 3.10+
- FFmpeg installed and available in PATH

### Install FFmpeg

- **Windows**: `winget install ffmpeg` or download from https://ffmpeg.org/download.html
- **macOS**: `brew install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

## Getting Started

### Backend

```bash
# First-time setup only
cd backend
python -m venv venv
venv\Scripts\activate   # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Then from the project root:

```bash
npm run backend
```

Backend runs at: http://localhost:8000
API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| POST | /upload | Upload a video |
| GET | /projects | List all projects |
| GET | /project/{id} | Get project by ID |
| DELETE | /project/{id} | Delete project |

## Project Structure

```
clipsense/
├── backend/
│   └── app/
│       ├── api/          # Route handlers
│       ├── services/     # Business logic
│       ├── schemas/      # Pydantic models
│       ├── utils/        # FFprobe, storage, validators
│       ├── uploads/      # Stored video files
│       ├── metadata/     # JSON metadata per project
│       └── main.py
└── frontend/
    └── src/
        ├── components/   # Reusable UI components
        ├── pages/        # Route-level page components
        ├── layouts/      # Shell layouts
        ├── services/     # API service layer
        ├── context/      # React Context (state)
        ├── hooks/        # Custom hooks
        ├── types/        # TypeScript interfaces
        └── utils/        # Formatters, constants
```

## Week 2+ (Planned)

- Scene detection
- Speech-to-text (Whisper)
- Trailer generation
- Sentiment analysis
- OpenAI integration
