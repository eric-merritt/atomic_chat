#!/usr/bin/env python3
"""Unified launcher for Atomic Chat — replaces start.sh.

Drives the llama-server binary (main + summary), the MCP tools server, the Flask
backend, the Vite frontend, and the Neo4j container as managed subprocesses.
config.py is the single source of truth for ports and llama launch specs.

Usage:
  uv run python launch.py [start|stop|restart|status|stop-app|stop-llama|shell]
"""

import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT, "logs")
DOTENVX_BIN = os.environ.get(
  "DOTENVX_BIN", "/home/ermer/node_modules/.bin/dotenvx"
)


# ── .env loading ─────────────────────────────────────────────────────────────
# Mirror start.sh's `source .env`: plaintext keys (ports, model paths) reach
# config.py here; encrypted secret values stay opaque and are decrypted later by
# `dotenvx run` when the backend/tools subprocesses actually launch.
def read_env_file(path):
  """Parse a KEY=VALUE .env file into a dict, ignoring comments and blanks."""
  pairs = {}
  if not os.path.isfile(path):
    return pairs
  for rawLine in open(path, encoding="utf-8"):
    line = rawLine.strip()
    if not line or line.startswith("#") or "=" not in line:
      continue
    key, value = line.split("=", 1)
    pairs[key.strip()] = value.strip().strip('"').strip("'")
  return pairs


def apply_env(envPairs):
  """Set each key in the process environment unless already present."""
  for key, value in envPairs.items():
    os.environ.setdefault(key, value)


apply_env(read_env_file(os.path.join(ROOT, ".env")))

# config is imported only AFTER .env is applied so its os.environ reads resolve.
import config  # noqa: E402


# ── PID tracking ─────────────────────────────────────────────────────────────
def pidfile_for(name):
  return os.path.join(LOG_DIR, f"{name}.pid")


def read_pid(name):
  path = pidfile_for(name)
  if not os.path.isfile(path):
    return None
  try:
    return int(open(path, encoding="utf-8").read().strip())
  except (ValueError, OSError):
    return None


def write_pid(name, pid):
  with open(pidfile_for(name), "w", encoding="utf-8") as handle:
    handle.write(str(pid))


def clear_pid(name):
  try:
    os.remove(pidfile_for(name))
  except FileNotFoundError:
    pass


def process_alive(pid):
  if pid is None:
    return False
  try:
    os.kill(pid, 0)
    return True
  except ProcessLookupError:
    return False
  except PermissionError:
    return True


def is_running(name):
  return process_alive(read_pid(name))


# ── Subprocess lifecycle ─────────────────────────────────────────────────────
def spawn(name, argv, extraEnv=None):
  """Launch argv detached into its own session, logging to logs/<name>.log."""
  logPath = os.path.join(LOG_DIR, f"{name}.log")
  childEnv = {**os.environ, **(extraEnv or {})}
  with open(logPath, "w", encoding="utf-8") as logHandle:
    process = subprocess.Popen(
      argv,
      stdout=logHandle,
      stderr=subprocess.STDOUT,
      cwd=ROOT,
      env=childEnv,
      start_new_session=True,
    )
  write_pid(name, process.pid)
  return process.pid


def stop_process(name, label):
  """Terminate the whole process group for `name`, then drop its pidfile."""
  pid = read_pid(name)
  if not process_alive(pid):
    clear_pid(name)
    return
  try:
    groupId = os.getpgid(pid)
  except ProcessLookupError:
    clear_pid(name)
    return
  os.killpg(groupId, signal.SIGTERM)
  for _ in range(24):
    if not process_alive(pid):
      break
    time.sleep(0.25)
  if process_alive(pid):
    os.killpg(groupId, signal.SIGKILL)
  clear_pid(name)
  print(f"  ⛔ Stopped {label} (PID {pid})")


def wait_healthy(name, port, timeoutSec=180):
  """Block until http://127.0.0.1:<port>/health answers, or the process dies."""
  deadline = time.monotonic() + timeoutSec
  url = f"http://127.0.0.1:{port}/health"
  while time.monotonic() < deadline:
    if not is_running(name):
      print(f"  💥 {name} died during load — see {LOG_DIR}/{name}.log")
      return False
    try:
      with urllib.request.urlopen(url, timeout=1) as response:
        if response.status == 200:
          print(f"  ✅ {name} ready on :{port}")
          return True
    except (urllib.error.URLError, OSError):
      pass
    time.sleep(0.5)
  print(f"  ⏰ {name} did not bind :{port} within {timeoutSec}s — see {LOG_DIR}/{name}.log")
  return False


# ── llama-server ─────────────────────────────────────────────────────────────
def build_llama_argv(spec):
  """Translate a config launch spec into a llama-server argument vector."""
  argv = [
    spec["bin"],
    "--model", spec["model"],
    "--host", spec["host"],
    "--port", str(spec["port"]),
    "--alias", spec["alias"],
    "--jinja",
    "--reasoning", "off",
    "--no-webui",
    "--parallel", "1",
    "-ngl", str(spec["ngl"]),
    "-c", str(spec["ctx"]),
  ]
  if spec.get("flash_attn"):
    argv += ["--flash-attn", "on"]
  if spec.get("cache_type"):
    argv += ["--cache-type-k", spec["cache_type"], "--cache-type-v", spec["cache_type"]]
  if spec.get("mmproj"):
    argv += ["--mmproj", spec["mmproj"]]
  if spec.get("draft_model"):
    argv += ["--model-draft", spec["draft_model"], "-ngld", str(spec["draft_ngl"])]
  return argv


def llama_env(spec):
  """LD_LIBRARY_PATH so the binary resolves its shared libs regardless of the
  ldconfig cache (the libs sit beside the binary and in /usr/local/lib)."""
  libDirs = [os.path.dirname(os.path.realpath(spec["bin"])), "/usr/local/lib"]
  existing = os.environ.get("LD_LIBRARY_PATH", "")
  return {"LD_LIBRARY_PATH": ":".join([*libDirs, existing]).rstrip(":")}


def start_llama(spec):
  """Start one llama-server (skip if already up) and wait for it to bind."""
  name = spec["name"]
  if is_running(name):
    print(f"⚡ {name} already running (PID {read_pid(name)}), skipping")
    return True
  print(f"🚀 Starting {name} on :{spec['port']} | {spec['alias']} ({spec['model']})")
  spawn(name, build_llama_argv(spec), extraEnv=llama_env(spec))
  return wait_healthy(name, spec["port"])


# ── Neo4j (docker) ───────────────────────────────────────────────────────────
NEO4J_RUN_ARGV = [
  "docker", "run", "-d",
  "--name", "neo4j",
  "-p", "7687:7687",
  "-p", "7474:7474",
  "-e", "NEO4J_AUTH=neo4j/atomic_chat_dev",
  "-e", "NEO4J_PLUGINS=[\"apoc\"]",
  "-e", "NEO4J_apoc_export_file_enabled=true",
  "-e", "NEO4J_apoc_import_file_enabled=true",
  "-e", "NEO4J_apoc_import_file_use__neo4j__config=true",
  "-v", f"{ROOT}/neo4j/data:/data",
  "-v", f"{ROOT}/neo4j/logs:/logs",
  "-v", f"{ROOT}/neo4j/plugins:/plugins",
  "-v", f"{ROOT}/neo4j/import:/import",
  "neo4j:5.26",
]


def neo4j_running():
  result = subprocess.run(
    ["docker", "ps", "--filter", "name=neo4j", "--format", "{{.Names}}"],
    capture_output=True, text=True,
  )
  return "neo4j" in result.stdout


def neo4j_accepts_bolt():
  result = subprocess.run(
    ["docker", "exec", "neo4j", "cypher-shell",
     "-u", "neo4j", "-p", "atomic_chat_dev", "RETURN 1"],
    capture_output=True, text=True,
  )
  return result.returncode == 0


def start_neo4j():
  if neo4j_running():
    print("⚡ Neo4j already running, skipping")
    return
  print("🗄️  Starting Neo4j...")
  started = subprocess.run(["docker", "start", "neo4j"], capture_output=True, text=True)
  if started.returncode != 0:
    print("   Neo4j container not found, creating...")
    subprocess.run(NEO4J_RUN_ARGV, check=True)
  deadline = time.monotonic() + 30
  while time.monotonic() < deadline:
    if neo4j_accepts_bolt():
      print("  ✅ Neo4j ready")
      return
    time.sleep(1)
  print("  ⏰ Neo4j did not accept bolt within 30s — continuing")


def stop_neo4j():
  if neo4j_running():
    subprocess.run(["docker", "stop", "neo4j"], capture_output=True)
    print("  ⛔ Stopped Neo4j")


# ── App services ─────────────────────────────────────────────────────────────
def dotenvx_python(scriptName, *scriptArgs):
  """Wrap a python entrypoint in `dotenvx run -- uv run python` for secret decryption."""
  return [DOTENVX_BIN, "run", "--", "uv", "run", "python",
          os.path.join(ROOT, scriptName), *scriptArgs]


def start_tools():
  print(f"🔧 Starting tools-server on :{config.TOOLS_PORT}")
  spawn("tools", dotenvx_python("tools_server.py"))


def start_backend():
  print(f"🐍 Starting backend on :{config.BACKEND_PORT}")
  spawn("backend", dotenvx_python("main.py", "--serve"))


def start_frontend():
  print(f"⚛️  Starting frontend on :{config.FRONTEND_PORT}")
  spawn("frontend", ["npm", "--prefix", os.path.join(ROOT, "frontend"), "run", "dev"])


# ── Service registry ─────────────────────────────────────────────────────────
# Friendly name (CLI-facing) → internal name (pidfile/log) + how to start it.
SERVICES = {
  "main":     { "internal": "llama",         "label": "llama-server",  "kind": "llama", "spec": config.MAIN_LLAMA },
  "summary":  { "internal": "llama_summary", "label": "llama-summary", "kind": "llama", "spec": config.SUMMARY_LLAMA },
  "tools":    { "internal": "tools",         "label": "tools-server",  "kind": "app",   "starter": start_tools },
  "backend":  { "internal": "backend",       "label": "backend",       "kind": "app",   "starter": start_backend },
  "frontend": { "internal": "frontend",      "label": "frontend",      "kind": "app",   "starter": start_frontend },
}

# Dependency-safe order for bulk operations (main before summary for VRAM, etc.).
STARTUP_ORDER = ["main", "summary", "tools", "backend", "frontend"]


def in_startup_order(names):
  return [name for name in STARTUP_ORDER if name in names]


def start_service(name):
  """Start one service by friendly name. Skips if already running."""
  service = SERVICES[name]
  if service["kind"] == "llama":
    return start_llama(service["spec"])
  internal = service["internal"]
  if is_running(internal):
    print(f"⚡ {internal} already running (PID {read_pid(internal)}), skipping")
    return True
  service["starter"]()
  return True


def stop_service(name):
  """Stop one service by friendly name."""
  service = SERVICES[name]
  stop_process(service["internal"], service["label"])


def restart_service(name):
  stop_service(name)
  start_service(name)


# ── Stop groups ──────────────────────────────────────────────────────────────
def stop_app():
  for name in ("tools", "backend", "frontend"):
    stop_service(name)


def stop_llama():
  for name in ("main", "summary"):
    stop_service(name)


def stop_all():
  stop_llama()
  stop_app()
  stop_neo4j()


# ── Orchestration ────────────────────────────────────────────────────────────
def start_all():
  start_neo4j()
  if not start_service("main"):
    print("❌ Main llama-server failed to come up — aborting before summary contends for VRAM")
    sys.exit(1)
  if not start_service("summary"):
    print("  ⚠️  summary did not come up — continuing (chat works, summaries degraded)")
  start_service("tools")
  start_service("backend")
  start_service("frontend")
  print("")
  print("✅ Services running.")
  print(f"   Logs: {LOG_DIR}/")
  print(f"   UI: http://localhost:{config.FRONTEND_PORT}")
  print(f"   Cmds: start|stop|restart [{('|').join(STARTUP_ORDER)}] · status · --watch <svc>")


def restart_all():
  stop_all()
  time.sleep(1)
  start_all()


def status():
  print("=== Service Status ===")
  for name in STARTUP_ORDER:
    internal = SERVICES[name]["internal"]
    if is_running(internal):
      print(f"  ✅ {name}: RUNNING (PID {read_pid(internal)})")
    else:
      print(f"  ❌ {name}: STOPPED")


# ── Watch (kitty grid split) ─────────────────────────────────────────────────
PYFIGLET_BIN = os.path.join(ROOT, ".venv", "bin", "pyfiglet")


def watch_pane_command(name, logPath):
  """Pane command: a fixed green figlet banner up top, log scrolling beneath it.

  The banner is pinned by setting the terminal scroll region (DECSTBM) to start
  below it, so streaming log lines never push the header off-screen.
  """
  follow = f"exec tail -n 200 -F {logPath}"
  if not os.path.exists(PYFIGLET_BIN):
    return follow
  return (
    "clear; "
    "ROWS=$(tput lines 2>/dev/null||echo 40); "
    "COLS=$(tput cols 2>/dev/null||echo 80); "
    "printf '\\033[1;32m'; "
    f"{PYFIGLET_BIN} -j center -w $COLS {name.upper()}; "
    "printf '\\033[0m'; "
    "printf '\\033[8;%dr' $ROWS; "  # lock rows 1-7 as a fixed header
    "printf '\\033[8;1H'; "         # drop cursor below the header
    + follow
  )


def open_kitty_watch(names):
  """Open a new kitty window, tiled in a grid, each pane banner + tailing a log."""
  kittyBin = shutil.which("kitty")
  if not kittyBin:
    print("  ⚠️  kitty not found on PATH — cannot open watch split")
    return
  ordered = in_startup_order(names)
  sessionLines = ["new_tab atomic-watch", "layout grid"]
  for name in ordered:
    logPath = os.path.join(LOG_DIR, f"{SERVICES[name]['internal']}.log")
    paneCommand = watch_pane_command(name, logPath)
    sessionLines.append(f'launch --title {name.upper()} sh -c "{paneCommand}"')
  session = tempfile.NamedTemporaryFile(
    mode="w", suffix=".kitty-session", delete=False, encoding="utf-8"
  )
  session.write("\n".join(sessionLines) + "\n")
  session.close()
  subprocess.Popen(
    [kittyBin,
     "-o", "window_margin_width=4",            # ~8px gutter between panes
     "-o", "window_border_width=1",            # divider line in that gutter
     "-o", "draw_minimal_borders=yes",
     "-o", "active_border_color=#2ea043",
     "-o", "inactive_border_color=#2ea043",
     "--session", session.name],
    start_new_session=True,
  )
  print(f"  🪟 kitty watch: {', '.join(ordered)}")


# ── CLI ──────────────────────────────────────────────────────────────────────
def parse_args(argv):
  parser = argparse.ArgumentParser(
    prog="launch.py",
    description="Atomic Chat launcher — operate on all services or named ones "
                f"({'|'.join(STARTUP_ORDER)}).",
  )
  parser.add_argument(
    "command",
    choices=["start", "stop", "restart", "status", "shell",
             "stop-app", "stop-llama", "watch"],
  )
  parser.add_argument(
    "services", nargs="*",
    help="Optional service names to act on; default is all.",
  )
  parser.add_argument(
    "--watch", action="append", default=[], metavar="SERVICE",
    help="Tail this service in a kitty grid split after the command (repeatable).",
  )
  parsed = parser.parse_args(argv)
  for name in [*parsed.services, *parsed.watch]:
    if name not in SERVICES:
      parser.error(f"unknown service '{name}' (valid: {', '.join(STARTUP_ORDER)})")
  return parsed


def main():
  os.makedirs(LOG_DIR, exist_ok=True)
  args = parse_args(sys.argv[1:] or ["start"])
  command, services = args.command, args.services

  if command == "watch":
    targets = in_startup_order(services or args.watch)
    if not targets:
      print("watch needs at least one service (positional or --watch)")
      sys.exit(1)
    open_kitty_watch(targets)
    return

  if command == "status":
    status()
  elif command == "shell":
    restart_service("tools")
  elif command == "stop-app":
    stop_app()
  elif command == "stop-llama":
    stop_llama()
  elif command == "start":
    if services:
      for name in in_startup_order(services):
        start_service(name)
    else:
      start_all()
  elif command == "stop":
    if services:
      for name in services:
        stop_service(name)
    else:
      stop_all()
  elif command == "restart":
    if services:
      for name in in_startup_order(services):
        restart_service(name)
    else:
      restart_all()

  if args.watch:
    open_kitty_watch(args.watch)


if __name__ == "__main__":
  main()
