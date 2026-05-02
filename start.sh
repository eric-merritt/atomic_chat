#!/usr/bin/env bash
# Unified Launcher: llama-server + tools + backend + frontend
# Usage: ./start.sh [start|stop|restart|status]
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$DIR/logs"
mkdir -p "$LOGDIR"

# PID tracking
PIDFILE_LLAMA="$LOGDIR/llama.pid"
PIDFILE_LLAMA_SUMMARY="$LOGDIR/llama_summary.pid"
PIDFILE_LLAMA_VISION="$LOGDIR/llama_vision.pid"
PIDFILE_TOOLS="$LOGDIR/tools.pid"
PIDFILE_BACKEND="$LOGDIR/backend.pid"
PIDFILE_FRONTEND="$LOGDIR/frontend.pid"

# Defaults (override via env or .env)
# Must match an entry in config.py MODELS so backend-triggered swaps line up.
MODEL_ALIAS="${MODEL_ALIAS:-qwen3.5:27b-iq4_xs}"
SUMMARY_MODEL_ALIAS="${SUMMARY_MODEL_ALIAS:-qwen3.5:4b-q5_k_m}"
MODEL="${MODEL:-/home/ermer/models/Qwen/Qwen3.5-27B/Qwen3.5-27B-IQ4_XS.gguf}"
SUMMARY_MODEL="${SUMMARY_MODEL:-/home/ermer/models/Qwen/Qwen3.5-4B/Qwen3.5-4B-Q5_K_M.gguf}"
SUMMARY_NGL="${SUMMARY_NGL:-0}"
MODEL_NGL="${MODEL_NGL:-36}"
MODEL_CTX="${MODEL_CTX:-32000}"
LLAMA_PORT="${LLAMA_PORT:-5173}"
LLAMA_SUMMARY_PORT="${LLAMA_SUMMARY_PORT:-5175}"
LLAMA_VISION_PORT="${LLAMA_VISION_PORT:-14530}"
VISION_MODEL="${VISION_MODEL:-/home/ermer/models/llava/llava-v1.5-7b-Q4_K_M-complete.gguf}"
VISION_MMPROJ="${VISION_MMPROJ:-/home/ermer/models/llava/Llava-v1.5-7b-mmproj-model-f16.gguf}"
TOOLS_PORT="${TOOLS_PORT:-5100}"
BACKEND_PORT="${BACKEND_PORT:-5000}"
FRONTEND_PORT="${FRONTEND_PORT:-5174}"

# ─── Helpers ───────────────────────────────────────────────────────────────
stop_pid() {
    local pf=$1 name=$2
    [[ -f "$pf" ]] || return 0
    local pid=$(cat "$pf")
    if kill -0 "$pid" 2>/dev/null; then
        pkill -P "$pid" 2>/dev/null || true
        kill "$pid"
        for i in {1..8}; do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
        kill -9 "$pid" 2>/dev/null || true
        echo "  ⛔ Stopped $name (PID $pid)"
    fi
    rm -f "$pf"
}

stop_app() {
    stop_pid "$PIDFILE_TOOLS"    "tools-server"
    stop_pid "$PIDFILE_BACKEND"  "backend"
    stop_pid "$PIDFILE_FRONTEND" "frontend"
}

stop_llama() {
    stop_pid "$PIDFILE_LLAMA"         "llama-server"
    stop_pid "$PIDFILE_LLAMA_SUMMARY" "llama-summary"
    stop_pid "$PIDFILE_LLAMA_VISION"  "llama-vision"
}

is_running() {
    [[ -f "$1" ]] && kill -0 "$(cat "$1")" 2>/dev/null
}

# ─── Commands ──────────────────────────────────────────────────────────────
CMD="${1:-start}"
case "$CMD" in
    stop)       stop_llama; stop_app; exit 0 ;;
    stop-app)   stop_app;   exit 0 ;;
    stop-llama) stop_llama; exit 0 ;;
    restart)    stop_llama; stop_app; sleep 1 ;;
    shell)      ;;
    status)
        echo "=== Service Status ==="
        for pf in "$PIDFILE_LLAMA" "$PIDFILE_LLAMA_SUMMARY" "$PIDFILE_LLAMA_VISION" "$PIDFILE_TOOLS" "$PIDFILE_BACKEND" "$PIDFILE_FRONTEND"; do
            n=$(basename "$pf" .pid)
            if is_running "$pf"; then echo "  ✅ $n: RUNNING (PID $(cat "$pf"))";
            else echo "  ❌ $n: STOPPED"; fi
        done
        exit 0 ;;
    start)   ;;
    *) echo "Usage: $0 [start|stop|stop-app|stop-llama|restart|shell|status]"; exit 1 ;;
esac

# shell mode only restarts tools-server; other modes restart all app services
if [[ "$CMD" == "shell" ]]; then
    stop_pid "$PIDFILE_TOOLS" "tools-server"
else
    stop_app
fi

# ─── 1. llama.cpp Server ──────────────────────────────────────────────────
if is_running "$PIDFILE_LLAMA"; then
    echo "⚡ llama-server already running (PID $(cat "$PIDFILE_LLAMA")), skipping"
else
    echo "🚀 Starting llama-server on :$LLAMA_PORT | Model: $MODEL_ALIAS ($MODEL)"
    nohup llama-server \
        --model "$MODEL" \
        --host 0.0.0.0 \
        --port "$LLAMA_PORT" \
        --jinja \
        --reasoning off \
        --flash-attn on \
        --cache-type-k q8_0 \
        --cache-type-v q8_0 \
        -c "$MODEL_CTX" \
        -ngl "$MODEL_NGL" \
        --parallel 1 \
        --alias "$MODEL_ALIAS" \
        > "$LOGDIR/llama.log" 2>&1 &
    echo $! > "$PIDFILE_LLAMA"
fi

if is_running "$PIDFILE_LLAMA_SUMMARY"; then
    echo "⚡ llama-summary already running (PID $(cat "$PIDFILE_LLAMA_SUMMARY")), skipping"
else
    echo "🚀 Starting llama-summary on :$LLAMA_SUMMARY_PORT | Model: $SUMMARY_MODEL_ALIAS ($SUMMARY_MODEL)"
    nohup llama-server \
        --model "$SUMMARY_MODEL" \
        --host 127.0.0.1 \
        --port "$LLAMA_SUMMARY_PORT" \
        --jinja \
        --reasoning off \
        -c 4096 \
        -ngl "$SUMMARY_NGL" \
        --parallel 1 \
        --alias "$SUMMARY_MODEL_ALIAS" \
        > "$LOGDIR/llama_summary.log" 2>&1 &
    echo $! > "$PIDFILE_LLAMA_SUMMARY"
fi

if is_running "$PIDFILE_LLAMA_VISION"; then
    echo "⚡ llama-vision already running (PID $(cat "$PIDFILE_LLAMA_VISION")), skipping"
else
    echo "🚀 Starting llama-vision on :$LLAMA_VISION_PORT | Model: llava-v1.5-7b"
    nohup llama-server \
        --model "$VISION_MODEL" \
        --mmproj "$VISION_MMPROJ" \
        --host 127.0.0.1 \
        --port "$LLAMA_VISION_PORT" \
        -ngl 0 \
        --parallel 1 \
        --alias llava-v1.5-7b \
        > "$LOGDIR/llama_vision.log" 2>&1 &
    echo $! > "$PIDFILE_LLAMA_VISION"
fi

# ─── 2. MCP Tools Server ──────────────────────────────────────────────────
echo "🔧 Starting tools-server on :$TOOLS_PORT"
nohup uv run python "$DIR/tools_server.py" \
    > "$LOGDIR/tools.log" 2>&1 &
echo $! > "$PIDFILE_TOOLS"

# ─── 3. Flask Backend ─────────────────────────────────────────────────────
if [[ "$CMD" != "shell" ]]; then
    echo "🐍 Starting backend on :$BACKEND_PORT"
    nohup uv run python "$DIR/main.py" --serve \
        > "$LOGDIR/backend.log" 2>&1 &
    echo $! > "$PIDFILE_BACKEND"

    # ─── 4. React Frontend ────────────────────────────────────────────────────
    echo "⚛️  Starting frontend on :$FRONTEND_PORT"
    nohup npm --prefix "$DIR/frontend" run dev \
        > "$LOGDIR/frontend.log" 2>&1 &
    echo $! > "$PIDFILE_FRONTEND"
fi

echo ""
echo "✅ Services running."
echo "   Logs: $LOGDIR/"
if [[ "$CMD" != "shell" ]]; then
    echo "   UI: http://localhost:$FRONTEND_PORT"
fi
echo "   Use: ./$0 stop | stop-app | stop-llama | restart | shell | start"
