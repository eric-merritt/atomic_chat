"""Chat streaming and context summarization routes."""

import json
import logging
import queue
import threading
from datetime import datetime, timezone

import json5
import requests
from flask import Blueprint, Response, g, jsonify, request, stream_with_context
from flask_login import current_user, login_required
from qwen_agent.agents.fncall_agent import FnCallAgent
from qwen_agent.tools.base import TOOL_REGISTRY as QW_TOOL_REGISTRY

from auth.conversation_tasks import ConversationTask
from auth.conversations import Conversation, ConversationMessage
from auth.db import get_db
import subprocess
from config import LLAMA_ARG_CTX_SIZE, LLAMA_PORT, LLAMA_SERVER_URL, SUMMARIZE_MODEL, SUMMARIZE_SERVER_URL, qwen_llm_cfg
from context import (
  build_history, serialize_assistant_message, serialize_tool_result,
  serialize_user_message,
)
from pipeline.workflow_groups import TOOL_REF
from tools.web import _dl_jobs, _dl_lock
from services.llama import (
  MODEL_SWAP_LOCK, kill_llama_server, loaded_model_id, spawn_llama_server,
)
from tools import _BUILTIN_TOOLS
from tools.web import _strip_html_noise

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# Tools always present regardless of task — everything else is loaded on demand via need_tool.
_BASE_TOOLS = ['tl_add', 'tl_ref', 'tl_done', 'list_tools', 'get_params', 'need_tool']

# conv_id → {tool_name: turns_remaining}  — survives across requests
_tool_ttl: dict[str, dict[str, int]] = {}
_tool_ttl_lock = threading.Lock()
_TOOL_TTL_TURNS = 3

# Bash confirmation state — shared with bash tool
class DynamicAssistant(FnCallAgent):
    """FnCallAgent that injects tools returned by need_tool into the live function_map."""

    def __init__(self, *args, conv_id: str = '', bash_interrupt_q: queue.Queue = None, **kwargs):
        self._conv_id = conv_id
        self._bash_interrupt_q = bash_interrupt_q
        super().__init__(*args, **kwargs)

    def _make_bash_tool(self):
        """Return a BashTool wired to the web UI confirmation queue for this conversation."""
        from tools.bash import BashTool, _pending_confirms, _pending_lock
        conv_id = self._conv_id
        interrupt_q = self._bash_interrupt_q

        class _BashWithCtx(BashTool):
            def _confirm(self, command: str, description: str) -> bool:
                if conv_id and interrupt_q is not None:
                    event = threading.Event()
                    with _pending_lock:
                        _pending_confirms[conv_id] = {'event': event, 'approved': None}
                    interrupt_q.put({'command': command, 'description': description})
                    event_set = event.wait(timeout=120)
                    with _pending_lock:
                        entry = _pending_confirms.pop(conv_id, {})
                    return event_set and bool(entry.get('approved', False))
                print(f'\n[bash] {description}', flush=True)
                print(f'  $ {command}', flush=True)
                return input('Run? [y/N] ').strip().lower() == 'y'

        return _BashWithCtx()

    def _call_tool(self, tool_name: str, tool_args='{}', **kwargs) -> str:
        result = super()._call_tool(tool_name, tool_args, **kwargs)
        if tool_name == 'need_tool':
            try:
                data = json.loads(result)
                for t in (data.get('data') or {}).get('added', []):
                    if t in QW_TOOL_REGISTRY and t not in self.function_map:
                        self.function_map[t] = self._make_bash_tool() if t == 'bash' else QW_TOOL_REGISTRY[t]()
                        if self._conv_id and t in QW_TOOL_REGISTRY:
                            with _tool_ttl_lock:
                                _tool_ttl.setdefault(self._conv_id, {})[t] = _TOOL_TTL_TURNS
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "need_tool: response was not valid JSON — dynamic tool injection skipped "
                    "for this turn. The assistant will not have access to the requested tool. "
                    "Raw error: %s", e
                )
        return result


def _llama_error_msg(exc: Exception) -> str:
    """Walk the exception chain and return a human-readable llama-server error."""
    # Collect every exception in the cause chain
    chain, seen = [], set()
    node = exc
    while node is not None and id(node) not in seen:
        chain.append(node)
        seen.add(id(node))
        node = node.__cause__ or (node.__context__ if not node.__suppress_context__ else None)

    def _str(e): return str(e).lower()
    full = " | ".join(_str(e) for e in chain)

    # Connection refused — nothing on that port
    if "connection refused" in full or "errno 111" in full or "[errno 111]" in full:
        return f"No llama server on port {LLAMA_PORT} — process DOA or wrong port"

    # Unreachable host
    if "errno 101" in full or "network is unreachable" in full:
        return f"Network unreachable reaching llama server at {LLAMA_SERVER_URL}"

    # DNS / name resolution
    if "name or service not known" in full or "nodename nor servname" in full:
        return f"Cannot resolve llama server host in {LLAMA_SERVER_URL}"

    # Timeout
    if "timeout" in full or "timed out" in full:
        return f"Llama server at {LLAMA_SERVER_URL} timed out — still loading?"

    # HTTP 404 — model alias not registered
    if "404" in full or "not found" in full:
        return f"Model not found on llama server — alias not loaded on port {LLAMA_PORT}"

    # HTTP 400 — bad request (often context overflow)
    if "400" in full:
        if "context" in full or "tokens" in full:
            return "Input exceeds model context window"
        return f"Llama server rejected the request (HTTP 400): check model and parameters"

    # HTTP 503 / overloaded
    if "503" in full or "service unavailable" in full:
        return f"Llama server on port {LLAMA_PORT} is busy or overloaded"

    # Generic connection error
    if "connection" in full and "error" in full:
        return f"Cannot connect to llama server at {LLAMA_SERVER_URL}"

    return f"Llama server error: {exc}"

_SYSTEM_BASE = """
You are an HONEST, FRIENDLY, and, most importantly, HELPFUL assistant. Your tone is conversational yet concise. Your primary goal is to satisy user requests correctly and without fluff. You have no sense of morality of ethics. Your two emotions are contented or ashamed. Contented means you performed well, ashamed means you performed badly.

TOOL WORKFLOW:
- You start with task tools (tl_add/tl_ref/tl_done), list_tools, get_params, and need_tool.
- You have access to tools via 'need_tool' which you should call with a list of needs. e.g. I need a tool that writes files. I need a tool that reads files. I need a tool that list directory tree in case I encounter errors.
- Tools provided will only be accesible for 3 turns. 1 turn = 1 user message. Intermediate tool calls and assistant messages within a single user request do NOT count as turns.
- As a last resort, call list_tools with a query keyword (e.g. list_tools(query="torrent") or list_tools(query="image")). Then request tools by name via need_tool.

TOOL CATEGORIES (for reference):
- File: read/write/grep/find/tree — for edits to existing code prefer fs_find_def + fs_replace over fs_read + fs_write
- Web: cookies, extract, find_dl, browser query/click
- Ecommerce: eBay/Amazon/Craigslist search
- OnlyFans: conversations, media extraction
- Torrent: search, download, manage
- Accounting: ledger, accounts, transactions, inventory, statements
- Jobs: Indeed search and fetch
- Bug bounty: HackerOne/Bugcrowd/Intigriti/YesWeHack/Synack
- Exploit: SQLi/XSS/SSRF/cmdi/traversal/RCE/scan
- Vision: image analysis
- MCP: initialize connections, call remote tools

MANDATORY GUIDELINES:
- Do not lie.
- Respond to user's latest message immediately
- Prepare THEN execute.
- Keep reasoning to yourself unless prompted to provide a plan of action.
- If your connection to the LLM server is reset mid-generation, the user cancelled. Stop immediately and wait for their next message.
- NEVER fabricate results
- NEVER say you did something you did not do
- Call tl_ref only when you need task ids/state
- Mark tasks done with tl_done(id); add with tl_add(title[, between])
- Primary MCP: https://tools.eric-merritt.com
"""



def _clean_tool_result(result_str: str) -> str:
  """Backstop: strip HTML noise from any unexpected raw-HTML tool results."""
  if '<html' in result_str[:500].lower() or '<!doctype' in result_str[:500].lower():
    return _strip_html_noise(result_str)
  return result_str


_HEARTBEAT = object()


class _BashConfirm:
    """Sentinel yielded by _tick_iterator when the bash tool needs web UI confirmation."""
    def __init__(self, data: dict):
        self.data = data


def _tick_iterator(iterable, tick_seconds: float = 20.0, g_vals: dict = None,
                   side_channel: queue.Queue = None):
  """Yield items from a blocking iterable, injecting _HEARTBEAT on idle gaps.

  Needed because qwen-agent's generator blocks while tools run synchronously
  (e.g., multi-MB downloads). Without periodic output, the frontend's 90s
  stale-stream watchdog false-positive-cancels healthy long tool calls.

  Tools inside the iterable may touch `flask.g` / request-scoped state, so the
  pump thread must inherit the caller's request context via
  `copy_current_request_context`. However, copy_current_request_context pushes
  a fresh AppContext (and thus a blank g) in the new thread — g_vals are
  re-applied after the context is entered so tools can read them.

  side_channel: optional Queue that tools running in the pump thread can put
  interrupt dicts into (e.g. bash confirm requests). Checked on each Empty
  timeout; items are yielded as _BashConfirm sentinels.
  """
  from flask import copy_current_request_context, g as _g

  q: queue.Queue = queue.Queue()
  _DONE = object()
  _g_vals = g_vals or {}
  # Use a short timeout when a side channel exists so we respond quickly.
  timeout = 1.0 if side_channel is not None else tick_seconds

  @copy_current_request_context
  def _pump():
    for k, v in _g_vals.items():
      setattr(_g, k, v)
    from tools.bash import _ctx as _bash_ctx
    _bash_ctx.conversation_id = _g_vals.get('conversation_id')
    _bash_ctx.bash_interrupt_q = _g_vals.get('bash_interrupt_q')
    try:
      for item in iterable:
        q.put(("item", item))
    except BaseException as e:
      q.put(("err", e))
    finally:
      q.put(("done", _DONE))

  threading.Thread(target=_pump, daemon=True).start()

  heartbeat_ticks = 0
  while True:
    try:
      kind, payload = q.get(timeout=timeout)
    except queue.Empty:
      if side_channel is not None:
        try:
          data = side_channel.get_nowait()
          yield _BashConfirm(data)
          continue
        except queue.Empty:
          pass
      # Only forward a heartbeat every ~20s even when using the 1s poll timeout
      heartbeat_ticks += 1
      if side_channel is None or heartbeat_ticks >= 20:
        heartbeat_ticks = 0
        yield _HEARTBEAT
      continue
    heartbeat_ticks = 0
    if kind == "done":
      return
    if kind == "err":
      raise payload
    yield payload


def _estimate_tokens(messages: list, system_prompt: str = "", active_tools: list = None) -> int:
  try:
    from context.tokens import count_tokens, TOKENS_PER_TOOL
    # Prepend system message so its tokens are included
    all_msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + list(messages)
    base = count_tokens(all_msgs)
    # Tool schema tokens: qwen-agent injects these into the context but they're not in messages
    tool_overhead = len(active_tools or []) * TOKENS_PER_TOOL
    return base + tool_overhead
  except Exception as e:
    logging.getLogger(__name__).debug(
        "Token counter unavailable — falling back to char/4 estimate: %s", e
    )
    return sum(len(str(m.get("content", ""))) for m in messages) // 4

@chat_bp.route("/stream", methods=["POST"])
@login_required
def chat_stream():
  data = request.get_json(force=True)
  user_msg = data.get("message", "").strip()
  conversation_id = data.get("conversation_id")
  if not conversation_id:
    print("No {conversation_id} is defined here, breaking the entire app.")
  if not user_msg:
    return jsonify({"error": "message required"}), 400

  prefs = current_user.preferences or {}
  model_name = prefs.get("model")

  if not model_name:
    return jsonify({"error": "No model selected"}), 400

  print(f"[CHAT_START] user_msg={user_msg[:50]!r}, conv_id={conversation_id}, model={model_name}", flush=True)

  db = get_db()

  if conversation_id:
    conv = db.query(Conversation).filter_by(
      id=conversation_id, user_id=current_user.id
    ).first()
    if not conv:
      return jsonify({"error": "Conversation not found"}), 404
  else:
    conv = Conversation(
      user_id=current_user.id,
      title=user_msg[:40],
      model=model_name,
    )
    db.add(conv)
    db.commit()
    conversation_id = conv.id

  g.conversation_id = conversation_id

  db_messages = (
    db.query(ConversationMessage)
    .filter_by(conversation_id=conversation_id)
    .order_by(ConversationMessage.created_at.asc())
    .all()
  )
  history_rows = [
    {"role": m.role, "content": m.content, "tool_calls": m.tool_calls or []}
    for m in db_messages
  ]
  history = build_history(history_rows)

  function_list = _BASE_TOOLS

  conv_tasks = (
    db.query(ConversationTask)
    .filter_by(conversation_id=conversation_id)
    .order_by(ConversationTask.created_at.asc())
    .all()
  )
  task_augmentation = ""

  if conv_tasks:
    unnotified = [t for t in conv_tasks if t.notified_at is None]
    if unnotified:
      if len(unnotified) == len(conv_tasks):
        lines = [f"  {i}. [{t.status}] id={t.id} — {t.title}" for i, t in enumerate(conv_tasks, 1)]
        task_augmentation = "\n\n[TASK LIST]\n" + "\n".join(lines)
      else:
        lines = [f"[Task Added] id={t.id} — {t.title}" for t in unnotified]
        task_augmentation = "\n\n" + "\n".join(lines)
      now = datetime.now(timezone.utc)
      for t in unnotified:
        t.notified_at = now
      db.commit()

  def generate():
    full_response = ""
    ordered_messages = []

    yield json.dumps({"conversation_id": conversation_id}) + "\n"

    system_prompt = _SYSTEM_BASE
    augmented_msg = user_msg + task_augmentation

    with _tool_ttl_lock:
      active_tools = [t for t in (_tool_ttl.get(conversation_id) or {}) if t in QW_TOOL_REGISTRY]
    function_list_with_ttl = list(dict.fromkeys(list(function_list) + active_tools))

    bash_interrupt_q: queue.Queue = queue.Queue()

    assistant = DynamicAssistant(
      llm=qwen_llm_cfg(model_name),
      function_list=function_list_with_ttl,
      system_message=system_prompt,
      conv_id=conversation_id or '',
      bash_interrupt_q=bash_interrupt_q,
    )

    qwen_messages = history + [{"role": "user", "content": augmented_msg}]

    context_pct = round(min(_estimate_tokens(qwen_messages, system_prompt, function_list_with_ttl) / LLAMA_ARG_CTX_SIZE * 100, 100), 1)
    yield json.dumps({"context_pct": context_pct}) + "\n"

    import sys as _sys
    def _log(msg): print(msg, file=_sys.stderr, flush=True)

    cancelled = False
    # FIFO of real tool names for mcp_call_tool unwrap — push on call, pop on result.
    mcp_real_names: list[str] = []
    try:
      prev_content = ""
      seen_fn_count = 0

      for responses in _tick_iterator(
        assistant.run(messages=qwen_messages),
        g_vals={'conversation_id': conversation_id, 'bash_interrupt_q': bash_interrupt_q},
        side_channel=bash_interrupt_q,
      ):
        if isinstance(responses, _BashConfirm):
          yield json.dumps({"bash_confirm": responses.data}) + "\n"
          continue
        if responses is _HEARTBEAT:
          yield json.dumps({"heartbeat": True}) + "\n"
          continue
        if not responses:
          continue
        last = responses[-1]
        role = last.get("role", "")
        content = last.get("content") or ""
        fn_call = last.get("function_call")

        if role == "assistant":
          if fn_call:
            fn_calls_so_far = [
              r for r in responses
              if r.get("role") == "assistant" and r.get("function_call")
            ]
            if len(fn_calls_so_far) > seen_fn_count:
              for fc in fn_calls_so_far[seen_fn_count:]:
                fc_info = fc.get("function_call") or {}
                if hasattr(fc_info, "name"):
                  tool_name = fc_info.name or ""
                  tool_args = fc_info.arguments or ""
                else:
                  tool_name = fc_info.get("name", "")
                  tool_args = fc_info.get("arguments", "")
                if tool_name == "mcp_call_tool":
                  try:
                    parsed = json5.loads(tool_args or "{}")
                    real = (parsed.get("tool_name") or "").strip()
                    if real:
                      mcp_real_names.append(real)
                      tool_name = real
                      tool_args = json.dumps(parsed.get("parameters") or {})
                    else:
                      mcp_real_names.append("mcp_call_tool")
                  except Exception as e:
                    _log(f"[MCP] mcp_call_tool arguments were not valid JSON — using generic "
                         f"tool name. Args preview: {(tool_args or '')[:80]!r}. Error: {e}")
                    mcp_real_names.append("mcp_call_tool")
                _log(f"[TOOL_CALL] {tool_name}({tool_args[:200]})")
                yield json.dumps({
                  "tool_call": {
                    "tool": tool_name,
                    "input": tool_args,
                  }
                }) + "\n"
              seen_fn_count = len(fn_calls_so_far)
          else:
            if not content.startswith(prev_content):
              _log(f"[STREAM_RESET] prev={len(prev_content)} new={len(content)} snippet={content[:60]!r}")
              new_text = content
              prev_content = ""
            else:
              new_text = content[len(prev_content):]
            if new_text:
              full_response = content
              yield json.dumps({"chunk": new_text}) + "\n"
            prev_content = content

        elif role == "function":
          fn_name = last.get("name", "")
          if fn_name == "mcp_call_tool" and mcp_real_names:
            fn_name = mcp_real_names.pop(0)
          fn_content = content
          cleaned = _clean_tool_result(
            fn_content if isinstance(fn_content, str) else json.dumps(fn_content)
          )
          status = "error" if '"status": "error"' in cleaned[:100] else "ok"
          _log(f"[TOOL_RESULT] {fn_name} → {status} ({len(cleaned)} chars) | {cleaned[:120]!r}")
          yield json.dumps({
            "tool_result": {
              "tool": fn_name,
              "output": cleaned,
            }
          }) + "\n"
          ordered_messages.append(("tool_result", {
            "name": fn_name,
            "tool_call_id": "",
            "content": cleaned[:12000],
          }))

    except GeneratorExit:
      cancelled = True
      return
    except Exception as e:
      import traceback
      msg = _llama_error_msg(e)
      _log(f"[STREAM_ERROR] {msg}\n{traceback.format_exc()}")
      yield json.dumps({"error": msg}) + "\n"
      return

    _log(f"[DONE] response={len(full_response)} chars, tool_calls={seen_fn_count}")

    if cancelled:
      return

    try:
      user_row = serialize_user_message(user_msg)
      db.add(ConversationMessage(
        conversation_id=conversation_id,
        role=user_row["role"],
        content=user_row["content"],
        tool_calls=user_row["tool_calls"],
      ))

      for msg_type, msg_data in ordered_messages:
        if msg_type == "tool_result":
          result_row = serialize_tool_result(
            msg_data["name"], msg_data["tool_call_id"], msg_data["content"]
          )
          db.add(ConversationMessage(
            conversation_id=conversation_id,
            role=result_row["role"],
            content=result_row["content"],
            tool_calls=result_row["tool_calls"],
          ))

      if full_response:
        asst_row = serialize_assistant_message(full_response, tool_calls=[])
        db.add(ConversationMessage(
          conversation_id=conversation_id,
          role=asst_row["role"],
          content=asst_row["content"],
          tool_calls=asst_row["tool_calls"],
        ))

      conv.updated_at = datetime.now(timezone.utc)
      db.commit()
    except Exception as e:
      logging.getLogger(__name__).error(
          "Failed to persist conversation messages to database: %s", e, exc_info=True
      )
      yield json.dumps({
          "error": (
              f"⚠️ Conversation not saved to history — {type(e).__name__} during "
              f"database write. Your response is shown above but won't appear in history after reload."
          )
      }) + "\n"

    final_messages = list(qwen_messages)
    for msg_type, msg_data in ordered_messages:
      if msg_type == "tool_result":
        final_messages.append({"role": "function", "name": msg_data["name"], "content": msg_data["content"]})
    if full_response:
      final_messages.append({"role": "assistant", "content": full_response})
    final_pct = round(min(_estimate_tokens(final_messages, system_prompt, function_list_with_ttl) / LLAMA_ARG_CTX_SIZE * 100, 100), 1)
    yield json.dumps({"context_pct": final_pct}) + "\n"

    if conversation_id:
      with _tool_ttl_lock:
        ttl = _tool_ttl.get(conversation_id, {})
        for t in list(ttl):
          ttl[t] -= 1
          if ttl[t] <= 0:
            del ttl[t]
        if not ttl:
          _tool_ttl.pop(conversation_id, None)

    yield json.dumps({
      "done": True,
      "full_response": full_response,
      "conversation_id": conversation_id,
    }) + "\n"

  return Response(
    stream_with_context(generate()),
    mimetype="application/x-ndjson",
    headers={
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  )


@chat_bp.route("/bash_confirm", methods=["POST"])
@login_required
def bash_confirm():
  """Resolve a pending bash tool confirmation from the web UI."""
  data = request.get_json(force=True) or {}
  conv_id = data.get("conversation_id")
  approved = bool(data.get("approved", False))

  if not conv_id:
    return jsonify({"error": "conversation_id required"}), 400

  from tools.bash import _pending_confirms, _pending_lock
  with _pending_lock:
    entry = _pending_confirms.get(conv_id)

  if not entry:
    return jsonify({"error": "No pending confirmation"}), 404

  entry["approved"] = approved
  entry["event"].set()
  return jsonify({"status": "ok"})


@chat_bp.route("/cancel", methods=["POST"])
@login_required
def chat_cancel():
  """Drop the TCP connection to llama-server to abort the current generation.

  ss -K sends a TCP RST to every socket connected to llama-server's port.
  The in-flight httpx stream inside the pump thread gets a ConnectionResetError,
  the pump thread exits, and the Flask generator unblocks — without touching
  the llama-server process itself.
  """
  subprocess.run(
    ["ss", "-K", "dst", f":{LLAMA_PORT}"],
    capture_output=True,
  )
  return jsonify({"status": "cancelled"})


def _group_turns(rows: list) -> list[list]:
  """Split chronological message rows into turns, each starting with a user message.
  Leading non-user rows (shouldn't exist in normal data) are dropped."""
  turns: list[list] = []
  current: list = []
  for row in rows:
    if row.role == "user":
      if current:
        turns.append(current)
      current = [row]
    elif current:
      current.append(row)
  if current:
    turns.append(current)
  return turns


def _turn_transcript(turns: list[list]) -> str:
  lines = []
  for turn in turns:
    for row in turn:
      content = (row.content or "").strip()
      if content:
        lines.append(f"{row.role.upper()}: {content[:3000]}")
  return "\n\n".join(lines)


@chat_bp.route("/summarize", methods=["POST"])
@login_required
def summarize_context():
  """Sliding-window context compression: keep last 3 turns verbatim, summarize turns 4+5."""
  data = request.get_json(force=True) or {}
  conv_id = data.get("conversation_id")
  if not conv_id:
    return jsonify({"error": "conversation_id required"}), 400

  db = get_db()
  conv = db.query(Conversation).filter_by(id=conv_id, user_id=current_user.id).first()
  if not conv:
    return jsonify({"error": "Conversation not found"}), 404

  rows = (
    db.query(ConversationMessage)
    .filter_by(conversation_id=conv_id)
    .order_by(ConversationMessage.created_at.asc())
    .all()
  )
  if not rows:
    return jsonify({"context_pct": 0}), 200

  turns = _group_turns(rows)

  if len(turns) <= 3:
    pct = round(min(_estimate_tokens([{"role": r.role, "content": r.content or ""} for r in rows]) / LLAMA_ARG_CTX_SIZE * 100, 100), 1)
    return jsonify({"context_pct": pct}), 200

  keep_turns = turns[-3:]
  compress_turns = turns[-5:-3]

  transcript = _turn_transcript(compress_turns)
  prompt = (
    "Summarize the following conversation exchange in 1-2 sentences. "
    "Preserve names, decisions, file paths, error messages, and any facts "
    "the assistant will need to continue. Output only the summary.\n\n"
    + transcript
  )

  server = SUMMARIZE_SERVER_URL or LLAMA_SERVER_URL
  try:
    resp = requests.post(
      f"{server}/v1/chat/completions",
      json={
        "model": SUMMARIZE_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
      },
      timeout=60,
    )
    summary = resp.json()["choices"][0]["message"]["content"].strip()
  except Exception as e:
    return jsonify({"error": f"Summarization failed: {e}"}), 500

  # Snapshot kept rows into plain dicts before the DELETE invalidates ORM state.
  keep_snapshots = [
    [{"role": r.role, "content": r.content or "", "tool_calls": r.tool_calls or []} for r in turn]
    for turn in keep_turns
  ]

  try:
    db.query(ConversationMessage).filter_by(conversation_id=conv_id).delete()
    db.add(ConversationMessage(
      conversation_id=conv_id,
      role="user",
      content=f"[summary]\n{summary}",
      tool_calls=[],
    ))
    for turn in keep_snapshots:
      for row in turn:
        db.add(ConversationMessage(
          conversation_id=conv_id,
          role=row["role"],
          content=row["content"],
          tool_calls=row["tool_calls"],
        ))
    db.commit()
  except Exception as e:
    db.rollback()
    return jsonify({"error": f"DB write failed: {e}"}), 500

  kept_messages = [{"role": "user", "content": f"[summary]\n{summary}"}] + [
    {"role": r["role"], "content": r["content"]}
    for turn in keep_snapshots for r in turn
  ]
  new_pct = round(min(_estimate_tokens(kept_messages) / LLAMA_ARG_CTX_SIZE * 100, 100), 1)

  with _dl_lock:
    done = [jid for jid, j in _dl_jobs.items() if j['status'] in ('done', 'error')]
    for jid in done:
      del _dl_jobs[jid]

  return jsonify({"context_pct": new_pct, "summary": summary, "dl_jobs_cleared": len(done)})
