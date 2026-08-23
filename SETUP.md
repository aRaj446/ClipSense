# ClipSense — Local Setup

## Prerequisites
- Python 3.11+
- Node.js 18+
- ffmpeg on PATH ([download](https://ffmpeg.org/download.html))

## One-time setup

```bash
# 1. Clone the repo and enter the project folder
cd Clipsense

# 2. Create the shared Python virtual environment
python -m venv venv

# 3. Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install all Python dependencies (backend + sensecap)
pip install -r requirements.txt

# 5. Install frontend dependencies
cd frontend && npm install && cd ..
```

## Environment variables

Copy the example env files and fill in your keys:
```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

## Run everything

```bash
# From the project root (starts backend on :8000, sensecap on :8501, frontend on :5173)
npm run dev
```

Each service opens in its own terminal window automatically.

| Service  | URL                    |
|----------|------------------------|
| Frontend | http://localhost:5173  |
| Backend  | http://localhost:8000  |
| Sensecap | http://localhost:8501  |
