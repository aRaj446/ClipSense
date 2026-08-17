"""
Tests — GPU / Device Configuration (Feature 9)

Covers:
    1.  USE_GPU=false  → always CPU, regardless of DEVICE
    2.  DEVICE=auto    → CPU when CUDA unavailable
    3.  DEVICE=auto    → CUDA when CUDA available
    4.  DEVICE=cpu     → CPU even when CUDA available
    5.  DEVICE=cuda    → CUDA when available
    6.  DEVICE=cuda    → RuntimeError when CUDA unavailable
    7.  VIDEO_ENCODER=auto  → libx264 when NVENC unavailable
    8.  VIDEO_ENCODER=auto  → h264_nvenc when NVENC available
    9.  VIDEO_ENCODER=cpu   → libx264 always
    10. VIDEO_ENCODER=gpu   → h264_nvenc when available
    11. VIDEO_ENCODER=gpu   → RuntimeError when NVENC unavailable
    12. USE_GPU=false  → libx264 regardless of VIDEO_ENCODER
    13. encoder_options returns correct flags for each encoder
    14. collect_gpu_metadata — CPU path
    15. collect_gpu_metadata — GPU path
    16. whisper_model_name reads WHISPER_MODEL env var
    17. Whisper model cache keyed by (model, device) — different devices load separately
    18. Whisper model cache — same key reuses cached instance
    19. MediaStorage workspace_for creates isolated directories
    20. WorkspaceContext cleanup removes workspace tree
    21. MediaStorage context manager cleans up on exit
    22. WorkspaceContext resolve_input returns absolute path
    23. WorkspaceContext tmp_path and output_path are inside workspace
    24. WORKSPACE_ROOT env var is respected by storage

Run with:
    cd backend
    set PYTHONPATH=C:\\...\\backend
    pytest tests/test_gpu_config.py -v
"""

import os
import sys
import unittest.mock as mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reload_device():
    """
    Re-import device module with a cleared lru_cache so env-var patches take effect.
    lru_cache is process-scoped; tests must clear it between cases.
    """
    import importlib
    import app.utils.device as dev
    importlib.reload(dev)
    # Also clear the caches on the freshly reloaded module
    dev._cuda_available.cache_clear()
    dev._nvenc_available.cache_clear()
    return dev


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK A — Device resolution
# ═══════════════════════════════════════════════════════════════════════════════

def test_use_gpu_false_forces_cpu():
    """USE_GPU=false must return cpu regardless of DEVICE setting."""
    with mock.patch.dict(os.environ, {"USE_GPU": "false", "DEVICE": "cuda"}):
        dev = _reload_device()
        assert dev.resolve_device() == "cpu"


def test_device_auto_cpu_when_cuda_unavailable():
    """DEVICE=auto with CUDA unavailable must return cpu."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "auto"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=False):
            assert dev.resolve_device() == "cpu"


def test_device_auto_cuda_when_available():
    """DEVICE=auto with CUDA available must return cuda."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "auto"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=True):
            assert dev.resolve_device() == "cuda"


def test_device_cpu_explicit():
    """DEVICE=cpu must return cpu even when CUDA is available."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "cpu"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=True):
            assert dev.resolve_device() == "cpu"


def test_device_cuda_explicit_when_available():
    """DEVICE=cuda with CUDA available must return cuda."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "cuda"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=True):
            assert dev.resolve_device() == "cuda"


def test_device_cuda_explicit_raises_when_unavailable():
    """DEVICE=cuda with CUDA unavailable must raise RuntimeError with a clear message."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "cuda"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=False):
            try:
                dev.resolve_device()
                assert False, "Expected RuntimeError"
            except RuntimeError as exc:
                assert "DEVICE=cuda" in str(exc)
                assert "CUDA" in str(exc)


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK B — Encoder resolution
# ═══════════════════════════════════════════════════════════════════════════════

def test_encoder_auto_libx264_when_nvenc_unavailable():
    """VIDEO_ENCODER=auto with NVENC unavailable must return libx264."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "VIDEO_ENCODER": "auto"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_nvenc_available", return_value=False):
            assert dev.resolve_video_encoder() == "libx264"


def test_encoder_auto_nvenc_when_available():
    """VIDEO_ENCODER=auto with NVENC available must return h264_nvenc."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "VIDEO_ENCODER": "auto"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_nvenc_available", return_value=True):
            assert dev.resolve_video_encoder() == "h264_nvenc"


def test_encoder_cpu_explicit():
    """VIDEO_ENCODER=cpu must return libx264 always."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "VIDEO_ENCODER": "cpu"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_nvenc_available", return_value=True):
            assert dev.resolve_video_encoder() == "libx264"


def test_encoder_gpu_explicit_when_available():
    """VIDEO_ENCODER=gpu with NVENC available must return h264_nvenc."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "VIDEO_ENCODER": "gpu"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_nvenc_available", return_value=True):
            assert dev.resolve_video_encoder() == "h264_nvenc"


def test_encoder_gpu_explicit_raises_when_unavailable():
    """VIDEO_ENCODER=gpu with NVENC unavailable must raise RuntimeError."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "VIDEO_ENCODER": "gpu"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_nvenc_available", return_value=False):
            try:
                dev.resolve_video_encoder()
                assert False, "Expected RuntimeError"
            except RuntimeError as exc:
                assert "VIDEO_ENCODER=gpu" in str(exc)
                assert "h264_nvenc" in str(exc)


def test_use_gpu_false_forces_libx264():
    """USE_GPU=false must return libx264 regardless of VIDEO_ENCODER setting."""
    with mock.patch.dict(os.environ, {"USE_GPU": "false", "VIDEO_ENCODER": "gpu"}):
        dev = _reload_device()
        assert dev.resolve_video_encoder() == "libx264"


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK C — Encoder options
# ═══════════════════════════════════════════════════════════════════════════════

def test_encoder_options_libx264():
    """libx264 options must include -crf and -preset."""
    from app.utils.device import encoder_options
    opts = encoder_options("libx264")
    assert "-crf" in opts
    assert "-preset" in opts


def test_encoder_options_nvenc():
    """h264_nvenc options must include -rc, -cq, -preset."""
    from app.utils.device import encoder_options
    opts = encoder_options("h264_nvenc")
    assert "-rc" in opts
    assert "-cq" in opts
    assert "-preset" in opts


def test_encoder_options_unknown_falls_back_to_libx264():
    """Unknown encoder name must fall back to libx264 options."""
    from app.utils.device import encoder_options
    opts = encoder_options("some_unknown_encoder")
    assert "-crf" in opts


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK D — GPU metadata collection
# ═══════════════════════════════════════════════════════════════════════════════

def test_collect_gpu_metadata_cpu_path():
    """collect_gpu_metadata on CPU must return correct structure."""
    with mock.patch.dict(os.environ, {"USE_GPU": "false"}):
        dev = _reload_device()
        meta = dev.collect_gpu_metadata()
        assert meta["device"] == "cpu"
        assert meta["gpu_enabled"] is False
        assert meta["encoder"] == "libx264"
        assert "whisper_model" in meta
        assert "cuda_available" in meta
        assert meta["gpu_name"] is None


def test_collect_gpu_metadata_gpu_path():
    """collect_gpu_metadata with GPU enabled and CUDA available must reflect GPU."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "auto", "VIDEO_ENCODER": "auto"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=True), \
             mock.patch.object(dev, "_nvenc_available", return_value=True):
            # Stub torch so no real GPU or torch install is needed
            fake_torch = mock.MagicMock()
            fake_torch.cuda.get_device_name.return_value = "Tesla T4"
            with mock.patch.dict(sys.modules, {"torch": fake_torch}):
                meta = dev.collect_gpu_metadata()
        assert meta["device"] == "cuda"
        assert meta["gpu_enabled"] is True
        assert meta["encoder"] == "h264_nvenc"


def test_collect_gpu_metadata_never_raises():
    """collect_gpu_metadata must never raise even if resolve_device raises."""
    with mock.patch.dict(os.environ, {"USE_GPU": "true", "DEVICE": "cuda"}):
        dev = _reload_device()
        with mock.patch.object(dev, "_cuda_available", return_value=False):
            # DEVICE=cuda + no CUDA would normally raise — metadata must absorb it
            meta = dev.collect_gpu_metadata()
            assert meta["device"] == "cpu"  # fell back gracefully


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK E — Whisper model name
# ═══════════════════════════════════════════════════════════════════════════════

def test_whisper_model_name_default():
    """WHISPER_MODEL not set must default to 'base'."""
    env = {k: v for k, v in os.environ.items() if k != "WHISPER_MODEL"}
    with mock.patch.dict(os.environ, env, clear=True):
        from app.utils import device as dev
        assert dev.whisper_model_name() == "base"


def test_whisper_model_name_from_env():
    """WHISPER_MODEL env var must be respected."""
    with mock.patch.dict(os.environ, {"WHISPER_MODEL": "small"}):
        from app.utils import device as dev
        assert dev.whisper_model_name() == "small"


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK F — Whisper model cache
# ═══════════════════════════════════════════════════════════════════════════════

def test_whisper_model_cache_reuses_same_key(tmp_path):
    """
    Calling _get_model() twice with the same (model, device) must load
    the model only once — the second call returns the cached instance.
    """
    import app.utils.transcript as tr

    tr._model_cache.clear()

    fake_model = object()
    load_calls = []

    def _fake_load(name, device=None):
        load_calls.append((name, device))
        return fake_model

    fake_whisper = mock.MagicMock()
    fake_whisper.load_model.side_effect = _fake_load

    with mock.patch.dict(os.environ, {"WHISPER_MODEL": "base", "USE_GPU": "false", "DEVICE": "auto"}), \
         mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
        m1 = tr._get_model()
        m2 = tr._get_model()

    assert m1 is m2
    assert len(load_calls) == 1, f"Expected 1 load, got {len(load_calls)}"

    tr._model_cache.clear()


def test_whisper_model_cache_different_keys_load_separately(tmp_path):
    """
    Calling _get_model() with different (model, device) combinations must
    load the model separately for each unique key.
    """
    import app.utils.transcript as tr

    tr._model_cache.clear()

    load_calls = []

    def _fake_load(name, device=None):
        load_calls.append((name, device))
        return object()  # distinct object each time

    fake_whisper = mock.MagicMock()
    fake_whisper.load_model.side_effect = _fake_load

    # First call: base/cpu
    with mock.patch.dict(os.environ, {"WHISPER_MODEL": "base", "USE_GPU": "false"}), \
         mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
        tr._get_model()

    # Second call: small/cpu — different model name → different cache key
    with mock.patch.dict(os.environ, {"WHISPER_MODEL": "small", "USE_GPU": "false"}), \
         mock.patch.dict(sys.modules, {"whisper": fake_whisper}):
        tr._get_model()

    assert len(load_calls) == 2
    assert load_calls[0][0] == "base"
    assert load_calls[1][0] == "small"

    tr._model_cache.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# CHUNK G — MediaStorage / WorkspaceContext
# ═══════════════════════════════════════════════════════════════════════════════

def test_workspace_for_creates_isolated_dirs(tmp_path):
    """workspace_for must create input/, tmp/, output/ under {root}/{job_id}/."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        # Re-import storage so _WORKSPACE_ROOT picks up the patched env
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-abc")
        assert os.path.isdir(ws.input_dir)
        assert os.path.isdir(ws.tmp_dir)
        assert os.path.isdir(ws.output_dir)
        assert ws.workspace_dir == os.path.join(str(tmp_path), "job-abc")
        ws.cleanup()


def test_workspace_cleanup_removes_tree(tmp_path):
    """cleanup() must remove the entire workspace directory."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-cleanup")
        assert os.path.isdir(ws.workspace_dir)
        ws.cleanup()
        assert not os.path.exists(ws.workspace_dir)


def test_workspace_cleanup_idempotent(tmp_path):
    """cleanup() called twice must not raise."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-idem")
        ws.cleanup()
        ws.cleanup()  # must not raise


def test_workspace_context_manager_cleans_up(tmp_path):
    """MediaStorage.workspace() context manager must clean up on exit."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        storage = st.MediaStorage()
        with storage.workspace("job-ctx") as ws:
            workspace_dir = ws.workspace_dir
            assert os.path.isdir(workspace_dir)
        assert not os.path.exists(workspace_dir)


def test_workspace_context_manager_cleans_up_on_exception(tmp_path):
    """MediaStorage.workspace() must clean up even when the body raises."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        storage = st.MediaStorage()
        workspace_dir = None
        try:
            with storage.workspace("job-exc") as ws:
                workspace_dir = ws.workspace_dir
                raise ValueError("simulated failure")
        except ValueError:
            pass
        assert workspace_dir is not None
        assert not os.path.exists(workspace_dir)


def test_resolve_input_returns_absolute_path(tmp_path):
    """resolve_input must return an absolute, normalised path."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-resolve")
        source = str(tmp_path / "video.mp4")
        result = ws.resolve_input(source)
        assert os.path.isabs(result)
        ws.cleanup()


def test_tmp_path_and_output_path_inside_workspace(tmp_path):
    """tmp_path() and output_path() must return paths inside the workspace."""
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": str(tmp_path)}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-paths")
        assert ws.tmp_path("subtitles.srt").startswith(ws.tmp_dir)
        assert ws.output_path("trailer.mp4").startswith(ws.output_dir)
        ws.cleanup()


def test_workspace_root_env_var_respected(tmp_path):
    """WORKSPACE_ROOT env var must be used as the workspace root."""
    custom_root = str(tmp_path / "custom_ws")
    os.makedirs(custom_root, exist_ok=True)
    with mock.patch.dict(os.environ, {"WORKSPACE_ROOT": custom_root}):
        import importlib
        import app.utils.storage as st
        importlib.reload(st)

        ws = st.MediaStorage().workspace_for("job-root")
        assert ws.workspace_dir.startswith(custom_root)
        ws.cleanup()
