# AWS GPU-Ready Deployment — ClipSense Backend

This document describes the requirements and configuration steps to run the
ClipSense backend as a GPU worker on an AWS EC2 instance. No infrastructure
is created automatically — this is a reference for manual or IaC-assisted
provisioning.

---

## Architecture

```
Frontend (browser)
    ↓  HTTPS
Backend API  (FastAPI / uvicorn)
    ↓  background task / future: SQS
GPU Worker process
    ├── Whisper  (CUDA if available)
    ├── Scene detection  (CPU — PySceneDetect/OpenCV)
    ├── Beat detection   (CPU — librosa)
    ├── MoviePy          (CPU composition layer)
    └── FFmpeg           (h264_nvenc if available, libx264 fallback)
    ↓
app/trailers/  (local EBS today → S3 later via MediaStorage)
    ↓
Frontend playback
```

---

## EC2 Instance Requirements

### GPU

- Any NVIDIA GPU with CUDA support (e.g. T4, A10G, L4, V100).
- Minimum recommended VRAM:
  - `WHISPER_MODEL=base`  → 1 GB VRAM
  - `WHISPER_MODEL=small` → 2 GB VRAM
  - `WHISPER_MODEL=medium`→ 5 GB VRAM
  - `WHISPER_MODEL=large` → 10 GB VRAM
- No specific instance type is hardcoded. Choose based on workload and cost.

### Software prerequisites

| Component | Minimum version | Notes |
|-----------|----------------|-------|
| NVIDIA driver | 525+ | Required for CUDA 12.x |
| CUDA toolkit | 11.8+ | Must match PyTorch build |
| cuDNN | 8.x+ | Required by PyTorch |
| FFmpeg | 5.x+ | Must be compiled with `--enable-nvenc` |
| Python | 3.11+ | Match the local dev version |

### Storage

- Root EBS: 30 GB minimum (OS + Python packages + models).
- Data EBS: size depends on raw footage volume.
  - Mount at `/mnt/workspace` and set `WORKSPACE_ROOT=/mnt/workspace`.
  - gp3 recommended (3000 IOPS baseline, burstable).

### RAM

- Minimum 16 GB. 32 GB recommended for `WHISPER_MODEL=medium` or larger.

### Network

- Outbound internet access required for:
  - Whisper model download on first run (cached to `~/.cache/whisper`).
  - HuggingFace model download on first run (cached to `~/.cache/huggingface`).
- Inbound: port 8000 (or behind ALB on 443).

---

## Environment Variables

Set these in `/etc/environment`, a systemd unit file, or an EC2 launch template
user-data script. Do **not** commit secrets to source control.

```bash
# Master GPU switch — must be true on GPU instances
USE_GPU=true

# Device strategy
# auto  → CUDA if available, otherwise CPU
# cuda  → require CUDA (fails clearly if unavailable)
# cpu   → CPU only
DEVICE=auto

# FFmpeg encoder
# auto  → h264_nvenc if available, otherwise libx264
# gpu   → require h264_nvenc
# cpu   → libx264 always
VIDEO_ENCODER=auto

# Whisper model — larger = more accurate, more VRAM
# tiny | base | small | medium | large | large-v2 | large-v3
WHISPER_MODEL=base

# Per-job workspace root — point at fast EBS volume
WORKSPACE_ROOT=/mnt/workspace

# Application directories (match your deployment layout)
UPLOAD_DIR=/opt/clipsense/app/uploads
METADATA_DIR=/opt/clipsense/app/metadata

# CORS — set to your frontend domain
CORS_ORIGINS=https://your-frontend-domain.com
```

---

## Verifying GPU Availability

After launching the instance and installing dependencies:

```bash
# Check CUDA
nvidia-smi

# Check PyTorch sees CUDA
python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# Check FFmpeg NVENC
ffmpeg -hide_banner -encoders | grep nvenc

# Check ClipSense device resolution
cd /opt/clipsense/backend
python3 -c "
from app.utils.device import collect_gpu_metadata
import json, os
os.environ['USE_GPU'] = 'true'
print(json.dumps(collect_gpu_metadata(), indent=2))
"
```

Expected output on a GPU instance:
```json
{
  "device": "cuda",
  "gpu_enabled": true,
  "encoder": "h264_nvenc",
  "whisper_model": "base",
  "cuda_available": true,
  "gpu_name": "Tesla T4"
}
```

---

## FFmpeg with NVENC

The `imageio-ffmpeg` package bundles a CPU-only FFmpeg binary. On EC2 GPU
instances you need a system FFmpeg compiled with NVENC support.

```bash
# Ubuntu/Debian — install from jonathonf PPA (includes NVENC)
sudo add-apt-repository ppa:jonathonf/ffmpeg-4
sudo apt update
sudo apt install ffmpeg

# Verify NVENC is present
ffmpeg -hide_banner -encoders | grep nvenc
# Expected: V..... h264_nvenc           NVIDIA NVENC H.264 encoder
```

If the system FFmpeg is found on `PATH` before the `imageio-ffmpeg` binary,
ClipSense will use it automatically (the `_get_ffmpeg()` function in
`ffmpeg_composer.py` prefers `imageio_ffmpeg` but falls back to `ffmpeg` on
`PATH`).

To force the system FFmpeg, prepend its directory to `PATH` in the environment:
```bash
export PATH=/usr/bin:$PATH
```

---

## Containerisation (Optional)

If the project adopts Docker in the future, the recommended base image is:

```
nvcr.io/nvidia/cuda:12.x.x-cudnn8-runtime-ubuntu22.04
```

This provides CUDA, cuDNN, and Ubuntu in a single image. Add:
- Python 3.11+
- FFmpeg with NVENC (compiled or from PPA)
- `pip install -r requirements.txt`

The `WORKSPACE_ROOT` should be a Docker volume mount backed by EBS.

---

## Job Queue — Future SQS Integration

The current worker boundary is `app/utils/job_queue.py` — a process-wide
semaphore that serialises jobs within a single process. The `_run_smart_job`
background task in `app/api/smart_trailer.py` is the entry point.

To connect to SQS or Celery later:

1. Replace `background_tasks.add_task(_run_smart_job, ...)` with an SQS
   `send_message` call in the API layer.
2. Run `_run_smart_job` as a Celery task or a standalone SQS consumer process
   on the GPU EC2 instance.
3. No changes to `SmartTrailerAgent`, `ffmpeg_composer`, or `transcript` are
   needed — the worker boundary is already clean.

---

## GPU Job Metadata

After each completed job, the following fields are recorded in the database
and accessible via `GET /smart-trailer/job/{job_id}/gpu-info`:

| Field | Description |
|-------|-------------|
| `device_used` | `cuda` or `cpu` |
| `encoder_used` | `h264_nvenc` or `libx264` |
| `whisper_model_used` | e.g. `base`, `small` |

This endpoint is intended for ops/debugging and is not surfaced in the
user-facing UI.

---

## Acceptance Checklist

- [ ] Local CPU still works (`USE_GPU=false`, default)
- [ ] Local GPU works if available (`USE_GPU=true`, `DEVICE=auto`)
- [ ] AWS GPU EC2 runs the same worker code without modification
- [ ] Whisper device is configurable via `DEVICE` env var
- [ ] FFmpeg encoder is configurable via `VIDEO_ENCODER` env var
- [ ] No hardcoded GPU model or instance type anywhere in the codebase
- [ ] No hardcoded EC2 instance type
- [ ] Job remains asynchronous (HTTP returns 202 immediately)
- [ ] Temporary files are job-isolated under `WORKSPACE_ROOT/{job_id}/`
- [ ] MoviePy remains hardware-agnostic (CPU composition layer only)
- [ ] No regression in Features 1–8 (122/122 pytest passing)
