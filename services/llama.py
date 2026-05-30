"""llama-server subprocess lifecycle manager.

Owns PID tracking, SIGTERM→SIGKILL shutdown, and spawn-with-health-wait
for the single llama.cpp process. One model loads at a time; model swap
is kill+spawn. Callers should serialize swaps with MODEL_SWAP_LOCK.
"""

import os
import signal
import subprocess
import threading
import time

import requests

from config import (
  LLAMA_ARG_CTX_SIZE, LLAMA_BIN, LLAMA_HOST, LLAMA_PORT, LLAMA_SERVER_URL, MODELS,
)

LLAMA_PID_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "llama.pid")
LLAMA_LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "llama.log")
MODEL_SWAP_LOCK = threading.Lock()

# loaded_model_id is hot — every chat request hits it via /health/ready and
# every model-swap polls it in a tight loop. Cache the answer for a short
# window so we don't pay /v1/models latency per call. Cache is invalidated
# explicitly by spawn_llama_server / kill_llama_server.
_LOADED_MODEL_CACHE_TTL_S = 5.0
_loaded_model_cache: dict = {"value": None, "expires_at": 0.0}
_loaded_model_cache_lock = threading.Lock()


def _invalidate_loaded_model_cache() -> None:
  with _loaded_model_cache_lock:
    _loaded_model_cache["value"] = None
    _loaded_model_cache["expires_at"] = 0.0


def loaded_model_id() -> str | None:
  now = time.monotonic()
  with _loaded_model_cache_lock:
    if now < _loaded_model_cache["expires_at"]:
      return _loaded_model_cache["value"]
  try:
    response = requests.get(f"{LLAMA_SERVER_URL}/v1/models", timeout=2)
    response.raise_for_status()
    data = response.json().get("data") or []
    value = data[0]["id"] if data else None
  except Exception:
    value = None
  with _loaded_model_cache_lock:
    _loaded_model_cache["value"] = value
    _loaded_model_cache["expires_at"] = now + _LOADED_MODEL_CACHE_TTL_S
  return value


def llama_is_healthy() -> bool:
  try:
    r = requests.get(f"{LLAMA_SERVER_URL}/health", timeout=1)
    return r.status_code == 200
  except requests.RequestException:
    return False


def _read_pid() -> int | None:
  try:
    with open(LLAMA_PID_FILE) as f:
      pid = int(f.read().strip())
    os.kill(pid, 0)
    return pid
  except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
    return None


def kill_llama_server() -> None:
  _invalidate_loaded_model_cache()
  pid = _read_pid()
  if pid is None:
    return
  try:
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
      try:
        os.kill(pid, 0)
        time.sleep(0.3)
      except ProcessLookupError:
        break
    else:
      os.kill(pid, signal.SIGKILL)
  except ProcessLookupError:
    pass
  try:
    os.remove(LLAMA_PID_FILE)
  except FileNotFoundError:
    pass


def spawn_llama_server(model_id: str, timeout_s: int = 120) -> bool:
  _invalidate_loaded_model_cache()
  cfg = MODELS[model_id]
  os.makedirs(os.path.dirname(LLAMA_LOG_FILE), exist_ok=True)
  log_f = open(LLAMA_LOG_FILE, "ab")
  cmd = [
    LLAMA_BIN,
    "--model", cfg["path"],
    "--host", LLAMA_HOST,
    "--port", str(LLAMA_PORT),
    "--jinja",
    "--reasoning", "off",
    "--flash-attn", "on",
    "--cache-type-k", "q8_0",
    "--cache-type-v", "q8_0",
    "-c", str(cfg.get("ctx", LLAMA_ARG_CTX_SIZE)),
    "-ngl", str(cfg.get("ngl", 99)),
    "--parallel", "1",
    "--alias", model_id,
  ]
  proc = subprocess.Popen(
    cmd, stdout=log_f, stderr=subprocess.STDOUT, start_new_session=True
  )
  with open(LLAMA_PID_FILE, "w") as f:
    f.write(str(proc.pid))

  deadline = time.time() + timeout_s
  while time.time() < deadline:
    if proc.poll() is not None:
      return False
    if llama_is_healthy() and loaded_model_id() == model_id:
      return True
    time.sleep(0.5)
  return False
