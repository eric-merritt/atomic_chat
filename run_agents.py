"""Launch all agent MCP servers.

Usage:
    python run_agents.py              # Start all agents
    python run_agents.py filesystem   # Start only filesystem agent
    python run_agents.py marketplace dispatcher  # Start specific agents
"""

import os
import subprocess
import sys
import signal
import time

from config import AGENT_PORTS

AGENT_SCRIPTS = {
    "filesystem": os.path.join("agents", "filesystem.py"),
    "codesearch": os.path.join("agents", "codesearch.py"),
    "web": os.path.join("agents", "web.py"),
    "marketplace": os.path.join("agents", "marketplace.py"),
    "dispatcher": os.path.join("agents", "dispatcher.py"),
}


def main():
    agents_to_start = sys.argv[1:] if len(sys.argv) > 1 else list(AGENT_SCRIPTS.keys())
    processes = []

    for name in agents_to_start:
        if name not in AGENT_SCRIPTS:
            print(f"Unknown agent: {name}")
            print(f"Available: {', '.join(AGENT_SCRIPTS.keys())}")
            sys.exit(1)

    print(f"Starting {len(agents_to_start)} agent(s)...")

    for name in agents_to_start:
        script = AGENT_SCRIPTS[name]
        port = AGENT_PORTS[name]
        print(f"  {name:15s} -> http://127.0.0.1:{port}")
        proc = subprocess.Popen(
            [sys.executable, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append((name, proc))
        time.sleep(0.5)  # Stagger startup

    print(f"\nAll agents started. Press Ctrl+C to stop.")

    def shutdown(sig, frame):
        print("\nShutting down agents...")
        for name, proc in processes:
            proc.terminate()
            print(f"  Stopped {name}")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Wait for any process to exit
    while True:
        for name, proc in processes:
            ret = proc.poll()
            if ret is not None:
                print(f"\n  Agent {name} exited with code {ret}")
                stderr = proc.stderr.read().decode() if proc.stderr else ""
                if stderr:
                    print(f"  stderr: {stderr[:500]}")
        time.sleep(1)


if __name__ == "__main__":
    main()
