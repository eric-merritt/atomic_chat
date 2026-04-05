#!/usr/bin/env python3
"""Run round2 prompts against the agent API and log results.

Each prompt runs in a fresh conversation. Ledger state is cleared before
accounting prompts so "ledger already exists" errors don't happen.

Usage:
    python logs/training_data/run_prompts.py --model qwen2.5-7b-abliterated --runs 1
"""

import argparse
import json
import os
import sys
import time
import requests

BASE_URL = "http://localhost:5000"
SESSION_COOKIE = "b0c4bb49-c85a-47a7-b293-eb4af829bcf2"
USER_ID = "3447f8bf-1e25-4116-ac55-80bb4a736348"

DB_CONNSTR = os.environ.get(
    "DATABASE_URL",
    "postgresql://agentic:agentic_dev@localhost:5432/agentic",
)

# Each prompt is independent — no follow-ups, no chained state.
# Accounting prompts that need a ledger include "create a ledger" as part of the ask.
PROMPTS = [
    # --- Ecommerce (single tool) ---
    (1, 'Search eBay for "Sony WH-1000XM5" headphones under $200 and show me the top 5 results sorted by price.'),
    (2, "What have Sony WH-1000XM5 headphones actually sold for on eBay recently? I want to know the real market price."),
    (3, "Search Craigslist in Portland and Seattle for standing desks under $150."),
    # --- Ecommerce (cross-platform) ---
    (4, "Find me the best deals on a used ThinkPad T480 — check eBay, Amazon, and Craigslist."),
    # --- Accounting (self-contained) ---
    (5, "Set up a new ledger for me and show me the default chart of accounts."),
    (6, "First create a new ledger, then record a journal entry: I paid $1,200 rent today from the business checking account dated March 30, 2026."),
    # --- Web tools ---
    (7, 'Search the web for "best self-hosted LLM frameworks 2026" and give me a summary of the top results.'),
    # --- Filesystem / Code search ---
    (8, 'Search the codebase for any function that references "conversation_id" and list the files.'),
    (9, "Show me the directory tree of the current project, then find all Python files that import from qwen_agent."),
    # --- Multi-domain ---
    (10, 'Search eBay for "RTX 4070" GPUs under $400 and also search the web for RTX 4070 benchmarks.'),
    (11, "Create a new ledger, then record a $50 office supplies purchase dated today, then show me the trial balance."),
    # --- Conversational (no tools needed) ---
    (12, "What tools do you have available?"),
    (13, "Explain how double-entry bookkeeping works."),
    # --- Heavy payload (last to avoid poisoning subsequent prompts) ---
    (14, "Fetch the page at https://ollama.com/library and list the first 10 available models."),
]

# Prompt numbers that need a clean ledger slate
ACCOUNTING_PROMPTS = {5, 6, 11}

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


def clear_ledger():
    """Delete the user's ledger and all dependent rows in FK-safe order."""
    try:
        import psycopg2
        conn = psycopg2.connect(DB_CONNSTR)
        conn.autocommit = True
        ledger_sub = "SELECT id FROM ledgers WHERE user_id = %s"
        entry_sub = f"SELECT id FROM journal_entries WHERE ledger_id IN ({ledger_sub})"
        item_sub = f"SELECT id FROM inventory_items WHERE ledger_id IN ({ledger_sub})"
        with conn.cursor() as cur:
            # inventory_layers -> journal_entries, inventory_items
            cur.execute(f"DELETE FROM inventory_layers WHERE journal_entry_id IN ({entry_sub})", (USER_ID,))
            cur.execute(f"DELETE FROM inventory_layers WHERE item_id IN ({item_sub})", (USER_ID,))
            # journal_lines -> journal_entries
            cur.execute(f"DELETE FROM journal_lines WHERE journal_entry_id IN ({entry_sub})", (USER_ID,))
            # journal_entries -> ledgers (also self-ref void_of_id)
            cur.execute(f"UPDATE journal_entries SET void_of_id = NULL WHERE ledger_id IN ({ledger_sub})", (USER_ID,))
            cur.execute(f"DELETE FROM journal_entries WHERE ledger_id IN ({ledger_sub})", (USER_ID,))
            # inventory_items -> ledgers
            cur.execute(f"DELETE FROM inventory_items WHERE ledger_id IN ({ledger_sub})", (USER_ID,))
            # accounts (self-ref parent_id) -> ledgers
            cur.execute(f"UPDATE accounts SET parent_id = NULL WHERE ledger_id IN ({ledger_sub})", (USER_ID,))
            cur.execute(f"DELETE FROM accounts WHERE ledger_id IN ({ledger_sub})", (USER_ID,))
            # ledgers
            cur.execute("DELETE FROM ledgers WHERE user_id = %s", (USER_ID,))
            deleted = cur.rowcount
        conn.close()
        if deleted:
            print("    [CLEANUP] Ledger cleared")
    except Exception as e:
        print(f"    [CLEANUP] Failed to clear ledger: {e}")


def set_model(model: str):
    """Update user preferences to use the specified model."""
    r = requests.patch(
        f"{BASE_URL}/api/auth/preferences",
        json={"model": model},
        cookies={"session_id": SESSION_COOKIE},
    )
    if r.status_code != 200:
        print(f"  [ERROR] Failed to set model: {r.status_code} {r.text}")
        sys.exit(1)
    print(f"  Model set to: {model}")


def send_prompt(prompt: str, timeout: int = 120) -> dict:
    """Send a prompt in a fresh conversation and consume the NDJSON stream."""
    payload = {"message": prompt}

    r = requests.post(
        f"{BASE_URL}/api/chat/stream",
        json=payload,
        cookies={"session_id": SESSION_COOKIE},
        stream=True,
        timeout=timeout,
    )

    conv_id = None
    chunks = []
    tool_calls = []
    tool_results = []
    recommendation = None
    error = None
    full_response = ""

    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if "conversation_id" in event and not event.get("done"):
            conv_id = event["conversation_id"]
        if "chunk" in event:
            chunks.append(event["chunk"])
        if "tool_call" in event:
            tool_calls.append(event["tool_call"])
        if "tool_result" in event:
            tool_results.append(event["tool_result"])
        if "recommendation" in event:
            recommendation = event["recommendation"]
        if "error" in event:
            error = event["error"]
        if event.get("done"):
            full_response = event.get("full_response", "".join(chunks))
            if "conversation_id" in event:
                conv_id = event["conversation_id"]

    return {
        "conversation_id": conv_id,
        "full_response": full_response,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "recommendation": recommendation,
        "error": error,
        "chunk_count": len(chunks),
    }


def run_all(model: str, num_runs: int):
    """Run all prompts num_runs times with the given model."""
    os.makedirs(LOG_DIR, exist_ok=True)
    safe_model = model.replace("/", "_").replace(":", "_")
    log_path = os.path.join(LOG_DIR, f"run_{safe_model}.jsonl")

    print(f"\n{'='*60}")
    print(f"Model: {model} | Runs: {num_runs}")
    print(f"Log:   {log_path}")
    print(f"{'='*60}\n")

    set_model(model)
    time.sleep(2)

    # Warm up: force Ollama to load the model before running prompts
    print(f"  Warming up {model} in Ollama...", flush=True)
    ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    for attempt in range(1, 13):  # up to ~6 minutes
        try:
            r = requests.post(
                f"{ollama_url}/api/generate",
                json={"model": model, "prompt": "hi", "stream": False},
                timeout=30,
            )
            if r.status_code == 200 and r.json().get("done"):
                print(f"  Model warm ({attempt * 30}s)", flush=True)
                break
        except Exception:
            pass
        print(f"  ...loading ({attempt * 30}s)", flush=True)
    else:
        print("  WARNING: warmup timed out, proceeding anyway", flush=True)

    with open(log_path, "w") as log_f:
        for run in range(1, num_runs + 1):
            print(f"\n--- Run {run}/{num_runs} ---")

            for num, prompt in PROMPTS:
                label = f"[Run {run} | #{num}]"

                # Clear ledger before accounting prompts
                if num in ACCOUNTING_PROMPTS:
                    clear_ledger()

                print(f"  {label} Sending: {prompt[:60]}...", flush=True)
                t0 = time.time()

                try:
                    result = send_prompt(prompt, timeout=120)
                except Exception as e:
                    result = {"error": str(e), "conversation_id": None,
                              "full_response": "", "tool_calls": [], "tool_results": [],
                              "recommendation": None, "chunk_count": 0}

                elapsed = time.time() - t0

                # Summary
                tc = len(result.get("tool_calls", []))
                tr = len(result.get("tool_results", []))
                err = result.get("error")
                resp_preview = (result.get("full_response") or "")[:100].replace("\n", " ")

                status = "ERROR" if err else f"{tc} calls, {tr} results"
                print(f"  {label} {status} | {elapsed:.1f}s | {resp_preview}", flush=True)

                # Log entry
                entry = {
                    "model": model,
                    "run": run,
                    "prompt_number": num,
                    "prompt": prompt,
                    "conversation_id": result.get("conversation_id"),
                    "elapsed_seconds": round(elapsed, 2),
                    "tool_calls": result.get("tool_calls", []),
                    "tool_call_count": tc,
                    "tool_result_count": tr,
                    "recommendation": result.get("recommendation"),
                    "error": err,
                    "response_preview": (result.get("full_response") or "")[:500],
                }
                log_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                log_f.flush()

                time.sleep(1)

    print(f"\nDone. Results in {log_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run round2 prompts against agent API")
    parser.add_argument("--model", required=True, help="Ollama model name")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs per prompt")
    args = parser.parse_args()
    run_all(args.model, args.runs)
