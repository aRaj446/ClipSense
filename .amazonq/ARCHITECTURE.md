# ClipSense — Architecture

## Request Flow

```
Browser
  │
  ├─ POST /upload-feedback (multipart .json/.csv)
  │     └─ _parse_json / _parse_csv
  │           └─ Agent 1: FeedbackStructuringAgent.parse()   ← replace body for Gemini
  │                 └─ DB SAVE (feedback_datasets + feedback_segments)
  │                       └─ Agent 2: VideoOptimizationAgent.analyze()
  │                             └─ AnalysisResponse { dataset_id, summary, recommendations, editing_plan }
  │
  ├─ POST /analyze-feedback (text body)                       ← reserved for Gemini LLM path
  │
  ├─ GET  /feedback-datasets/{project_id}
  ├─ GET  /feedback-dataset/{dataset_id}
  └─ DELETE /feedback-dataset/{dataset_id}
```

## Data Model

```
feedback_datasets
  id (UUID PK)
  project_id
  raw_text
  source          "file_upload" | "manual_paste"
  created_at

feedback_segments                    ← cascade delete on dataset
  id (UUID PK)
  dataset_id (FK)
  position
  timestamp       nullable
  topic
  sentiment       Positive|Negative|Neutral|Suggestion|Complaint|Praise|Question
  summary
  confidence      float
  created_at
```

## Agent Contracts

```python
# Agent 1 — swap parse() body for Gemini
FeedbackStructuringAgent.parse(raw_text: str) -> list[FeedbackSegment]

# Agent 2 — accepts future multimodal inputs
VideoOptimizationAgent.analyze(
    segments: list[FeedbackSegment],
    scene_boundaries=None,   # PySceneDetect
    transcript=None,         # Whisper
    detected_objects=None,
    audio_features=None,
    ocr_results=None,
) -> tuple[list[OptimizationRecommendation], EditingPlan]

# Agent 3 — placeholder
VideoRegenerationAgent.generate_optimized_video(
    project_id: str,
    editing_plan: EditingPlan,
) -> str   # output path
```

## DB Migration (SQLite → PostgreSQL/RDS)

Change one line in `backend/app/db/database.py`:
```python
# SQLite (local)
DATABASE_URL = "sqlite:///./app/clipsense.db"

# PostgreSQL / AWS RDS
DATABASE_URL = "postgresql://user:password@host:5432/clipsense"
```
Then run: `alembic upgrade head`

## Tech Decisions

| Concern | Choice | Reason |
|---|---|---|
| Sentiment parsing | Gemini 2.5 Pro | Multimodal — reads video + text in one API call |
| Video editing execution | FFmpeg + PySceneDetect + Whisper | Libraries, not LLMs. LLMs produce EditingPlan JSON; FFmpeg executes it |
| Local DB | SQLite | Zero config, single file, trivial to swap |
| Prod DB | PostgreSQL / AWS RDS | One-line change in database.py |
| Migrations | Alembic | Already installed, run when schema changes |
