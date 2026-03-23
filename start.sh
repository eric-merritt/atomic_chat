#!/usr/bin/env bash
# Start backend, tools server, and frontend in the background, detached from terminal.
# Logs written to logs/ directory. Use ./start.sh stop to kill all.

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$DIR/logs"
PIDFILE_BACK="$LOGDIR/backend.pid"
PIDFILE_TOOLS="$LOGDIR/tools_server.pid"
PIDFILE_FRONT="$LOGDIR/frontend.pid"

mkdir -p "$LOGDIR"

stop_servers() {
    for pf in "$PIDFILE_BACK" "$PIDFILE_TOOLS" "$PIDFILE_FRONT"; do
        if [[ -f "$pf" ]]; then
            pid=$(cat "$pf")
            if kill -0 "$pid" 2>/dev/null; then
                kill "$pid"
                echo "Stopped PID $pid"
            fi
            rm -f "$pf"
        fi
    done
}

case "${1:-start}" in
    stop)
        stop_servers
        exit 0
        ;;
    restart)
        stop_servers
        ;;
    start) ;;
    *)
        echo "Usage: $0 [start|stop|restart]"
        exit 1
        ;;
esac

# Kill existing if running
stop_servers

# Tools server — MCP on port 5100
nohup uv run python "$DIR/tools_server.py" \
    > "$LOGDIR/tools_server.log" 2>&1 &
echo $! > "$PIDFILE_TOOLS"
echo "Tools server started (PID $!, log: logs/tools_server.log)"

# Backend — Flask on port 5000
nohup uv run python "$DIR/main.py" --serve \
    > "$LOGDIR/backend.log" 2>&1 &
echo $! > "$PIDFILE_BACK"
echo "Backend started (PID $!, log: logs/backend.log)"

# Frontend — Vite on port 5173
nohup npm --prefix "$DIR/frontend" run dev \
    > "$LOGDIR/frontend.log" 2>&1 &
echo $! > "$PIDFILE_FRONT"
echo "Frontend started (PID $!, log: logs/frontend.log)"

echo "All servers running. Use './start.sh stop' to shut down."
