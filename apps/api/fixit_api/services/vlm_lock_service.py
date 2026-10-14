import os
import time
import threading
import urllib.request
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class LocalVLMLockManager:
    """
    Concurrency and health controller for on-premise local Strata VLM.
    Prevents concurrent VRAM exhaustion and manages multi-user execution queues.
    """
    _instance: Optional['LocalVLMLockManager'] = None
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, strata_url: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return
        
        # Resolve Strata Base URL from parameter, env, or config
        resolved_url = strata_url or os.environ.get("STRATA_VLM_URL")
        if not resolved_url:
            try:
                from fixit_api.config import settings
                resolved_url = getattr(settings, "STRATA_VLM_URL", None)
            except Exception:
                pass
        if not resolved_url:
            resolved_url = "http://192.168.202.24:8080/v1"

        cleaned = resolved_url.rstrip("/")
        if cleaned.endswith("/chat/completions"):
            base = cleaned.rsplit("/chat/completions", 1)[0]
        elif cleaned.endswith("/v1"):
            base = cleaned.rsplit("/v1", 1)[0]
        else:
            base = cleaned

        self.base_url = base
        self.health_url = f"{base}/health"
        self.models_url = f"{base}/v1/models" if not cleaned.endswith("/v1") else f"{cleaned}/models"
        self._execution_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._is_busy = False
        self._waiting_count = 0
        self._current_task_info: Optional[Dict[str, Any]] = None
        self._task_start_time: Optional[float] = None
        self._initialized = True

    def check_health(self) -> Dict[str, Any]:
        """Queries local Strata VLM server /health endpoint directly, with /v1/models fallback."""
        # 1. Primary: /health endpoint
        try:
            req = urllib.request.Request(self.health_url, headers={"User-Agent": "Fixit-API"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return {
                        "online": True,
                        "status": data.get("status", "ok"),
                        "model": data.get("model", "qwen3.8-flash-next-iq3_s"),
                        "max_context": data.get("max_context", 131072),
                        "loaded": data.get("loaded", True)
                    }
        except Exception as e:
            logger.debug(f"[VLM Health] Primary /health ping failed ({self.health_url}): {e}")

        # 2. Secondary fallback: /v1/models endpoint
        try:
            req = urllib.request.Request(self.models_url, headers={"User-Agent": "Fixit-API"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = data.get("data", [])
                    model_id = models[0].get("id", "qwen3.8-flash-next-iq3_s") if models else "qwen3.8-flash-next-iq3_s"
                    meta = models[0].get("meta", {}) if models else {}
                    return {
                        "online": True,
                        "status": "ok",
                        "model": model_id,
                        "max_context": meta.get("n_ctx", 131072),
                        "loaded": True
                    }
        except Exception as e:
            logger.debug(f"[VLM Health] Secondary /models ping failed ({self.models_url}): {e}")

        return {
            "online": False,
            "status": "offline",
            "model": None,
            "max_context": 0,
            "loaded": False
        }

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive lock state, queue length, and server health."""
        health = self.check_health()
        with self._state_lock:
            elapsed = round(time.time() - self._task_start_time, 1) if (self._is_busy and self._task_start_time) else 0.0
            busy = self._is_busy
            waiting = self._waiting_count
            task_info = dict(self._current_task_info) if self._current_task_info else None
        
        return {
            "online": health["online"],
            "busy": busy,
            "waiting_count": waiting,
            "model": health["model"],
            "max_context": health["max_context"],
            "current_task": task_info,
            "current_task_elapsed_sec": elapsed
        }

    class _LockContext:
        def __init__(self, manager: 'LocalVLMLockManager', task_name: str, model_type: str):
            self.manager = manager
            self.task_name = task_name
            self.model_type = model_type
            self._has_entered_queue = False

        def __enter__(self):
            with self.manager._state_lock:
                if self.manager._is_busy:
                    self.manager._waiting_count += 1
                    self._has_entered_queue = True
                    logger.info(f"[Local VLM Lock] Server is busy. Task '{self.task_name}' queued (Total waiting: {self.manager._waiting_count}).")

            # Acquire global inference execution lock (blocks safely until prior job finishes)
            self.manager._execution_lock.acquire()

            with self.manager._state_lock:
                if self._has_entered_queue and self.manager._waiting_count > 0:
                    self.manager._waiting_count = max(0, self.manager._waiting_count - 1)
                self.manager._is_busy = True
                self.manager._task_start_time = time.time()
                self.manager._current_task_info = {
                    "task_name": self.task_name,
                    "model_type": self.model_type,
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S")
                }
            logger.info(f"[Local VLM Lock] Lock acquired by task '{self.task_name}' ({self.model_type}).")
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            with self.manager._state_lock:
                self.manager._is_busy = False
                self.manager._task_start_time = None
                self.manager._current_task_info = None
            try:
                self.manager._execution_lock.release()
            except RuntimeError:
                pass
            logger.info(f"[Local VLM Lock] Lock released after task '{self.task_name}'.")

    def acquire(self, task_name: str = "ocr_inference", model_type: str = "strata_non_thinking"):
        """Returns a context manager ensuring mutual exclusion for local VLM inference."""
        return self._LockContext(self, task_name, model_type)

# Global singleton instance
vlm_lock_manager = LocalVLMLockManager()
