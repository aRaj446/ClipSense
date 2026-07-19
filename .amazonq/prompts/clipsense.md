# ClipSense — Project Context Prompt

## Project
Full-stack AI Marketing Optimization Platform. Path: `C:\Users\7000039334\Documents\Gearshift\Clipsense\`

## Stack
- Frontend: React 18 + Vite + TypeScript + TailwindCSS
- Backend: FastAPI + Python + SQLAlchemy + SQLite (→ PostgreSQL/RDS later)
- Video processing: FFmpeg + PySceneDetect + Whisper (libraries, not LLMs)
- LLM target: Gemini 2.5 Pro (multimodal) for Agent 1 sentiment parsing

## AI Pipeline
Agent 1 (FeedbackStructuringAgent) → DB SAVE → Agent 2 (VideoOptimizationAgent) → Agent 3 (VideoRegenerationAgent, placeholder)
- Agent 1: regex/keyword parsing → produces `list[FeedbackSegment]`. Replace `parse()` body with Gemini API call when ready.
- Agent 2: groups segments by topic, counts pos/neg, produces `OptimizationRecommendation[]` + `EditingPlan`
- Agent 3: executes `EditingPlan` via FFmpeg commands (not yet implemented)

## DB
SQLite at `app/clipsense.db`. Tables: `feedback_datasets` (id, project_id, raw_text, source, created_at), `feedback_segments` (id, dataset_id, position, timestamp, topic, sentiment, summary, confidence, created_at). Change `DATABASE_URL` in `database.py` to migrate.

## Key Rules
- `source` field: `"manual_paste"` for text, `"file_upload"` for file upload
- Valid sentiments: Positive / Negative / Neutral / Suggestion / Complaint / Praise / Question
- `POST /analyze-feedback` (text) kept for future Gemini integration — do not remove
- `POST /upload-feedback` (multipart) accepts `.json` (top-level array) or `.csv` (header: timestamp, topic, sentiment, summary, confidence)
- LLMs decide what to edit; FFmpeg/libraries execute the edits
- Migrate DB: change one line (`DATABASE_URL`) in `backend/app/db/database.py`

## File Map
```
backend/app/
  main.py                          # FastAPI app, lifespan startup
  db/base.py                       # DeclarativeBase
  db/database.py                   # engine, SessionLocal, get_db, create_tables — DATABASE_URL here
  models/feedback_dataset.py       # FeedbackDataset + FeedbackSegmentRecord ORM
  schemas/feedback.py              # FeedbackSegment, AnalysisResponse (has dataset_id), EditingPlan, etc.
  schemas/project.py               # ProjectResponse, ProjectListItem
  services/feedback_structuring_agent.py   # Agent 1 — replace parse() for Gemini
  services/video_optimization_agent.py     # Agent 2 — recommendations + editing plan
  services/video_regeneration_agent.py     # Agent 3 — placeholder
  services/feedback_dataset_service.py     # DB CRUD for datasets/segments
  services/project_service.py              # video upload/list/get/delete, JSON metadata
  api/feedback.py                  # /upload-feedback, /analyze-feedback, /feedback-datasets, /feedback-dataset
  api/projects.py                  # upload, list, get, delete
  utils/storage.py                 # UPLOAD_DIR, METADATA_DIR, DB_PATH, ensure_directories
  utils/ffprobe.py                 # extract_video_metadata via ffprobe subprocess
  utils/validators.py              # validate_video_file (ext + MIME)

frontend/src/
  types/project.ts                 # Project, ProjectListItem
  types/analysis.ts                # FeedbackSummary, AnalysisResult (has dataset_id), EditingPlan, etc.
  services/feedbackService.ts      # uploadFeedbackFile (multipart), analyzeFeedback (text/LLM)
  services/projectService.ts       # listProjects, getProject, deleteProject
  services/uploadService.ts        # uploadVideo with progress
  components/AudienceFeedbackPanel.tsx     # drag-drop file zone, progress, success state, format reference
  components/FeedbackSummaryCard.tsx       # pos/neg/neutral counts + proportion bars
  components/TimelineInsights.tsx          # per-segment list with sentiment badge + confidence bar
  components/OptimizationRecommendations.tsx  # priority-sorted recommendations
  components/PipelineDiagram.tsx           # read-only pipeline (active vs future stages)
  pages/ProjectDetails.tsx         # video player + metadata + AudienceFeedbackPanel + delete modal
  pages/Dashboard.tsx              # stats cards + project grid
  pages/UploadPage.tsx             # drag-drop upload with preview + progress
  context/ProjectContext.tsx       # projects, fetchProjects, removeProject
  context/ToastContext.tsx         # toast notifications
  layouts/MainLayout.tsx           # Navbar + Sidebar + Outlet
```
