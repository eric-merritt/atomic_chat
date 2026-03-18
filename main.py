"""
Agentic chat app with Flask API, Ollama model selection,
and a 2-column tool browser with > / < selection controls.
All tools are always bound to the agent — the browser just
lets you inspect what params each tool needs.
"""

import json
import re
from uuid import uuid4
import ollama as ollama_client
import os as _os
from flask import Flask, request, jsonify, Response, stream_with_context, send_file

from langchain_ollama import ChatOllama
from langchain.agents import create_agent, AgentState
from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.structured_output import ResponseFormat
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolCall
from langchain_core.caches import BaseCache
from langgraph.types import Checkpointer
from langgraph.store.base import BaseStore

import httpx

from config import AGENT_PORTS, agent_url
from tools import ALL_TOOLS


# ── Tool-call fixer ──────────────────────────────────────────────────────────
# Many Ollama models (qwen, llama, etc.) emit tool calls as JSON text in
# message.content instead of populating message.tool_calls.  This wrapper
# detects that pattern and promotes the text to real ToolCall objects so
# LangGraph's agent loop can route to the tools node.

_TOOL_NAMES = {t.name for t in ALL_TOOLS}


def _try_parse_tool_calls(content: str) -> list[ToolCall] | None:
    """Try to extract tool call(s) from raw JSON text content.

    Handles several patterns Ollama models use:
    1. Pure JSON text (entire content is a valid tool call)
    2. Content entirely wrapped in markdown fences
    3. Markdown fences embedded in prose/explanation text
    4. Bare JSON objects embedded in prose text
    """
    text = content.strip()
    if not text:
        return None

    def _parse_obj(parsed) -> list[ToolCall] | None:
        """Convert parsed JSON to ToolCall(s) if it looks like one."""
        if isinstance(parsed, dict) and "name" in parsed and parsed["name"] in _TOOL_NAMES:
            return [ToolCall(
                name=parsed["name"],
                args=parsed.get("arguments") or parsed.get("args") or {},
                id=str(uuid4()),
            )]
        if isinstance(parsed, list):
            calls = []
            for item in parsed:
                if isinstance(item, dict) and item.get("name") in _TOOL_NAMES:
                    calls.append(ToolCall(
                        name=item["name"],
                        args=item.get("arguments") or item.get("args") or {},
                        id=str(uuid4()),
                    ))
            return calls or None
        return None

    # 1. Try the entire content as JSON (maybe after stripping outer fences)
    attempt = text
    fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", attempt, re.DOTALL)
    if fence_match:
        attempt = fence_match.group(1).strip()
    try:
        result = _parse_obj(json.loads(attempt))
        if result:
            return result
    except json.JSONDecodeError:
        pass

    # 2. Search for fenced JSON blocks anywhere in the text
    for m in re.finditer(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL):
        try:
            result = _parse_obj(json.loads(m.group(1).strip()))
            if result:
                return result
        except json.JSONDecodeError:
            continue

    # 3. Search for bare JSON objects containing a tool name anywhere in text
    for m in re.finditer(r"\{[^{}]*\"name\"\s*:\s*\"[^\"]+\"[^{}]*\{.*?\}[^{}]*\}", text, re.DOTALL):
        try:
            result = _parse_obj(json.loads(m.group(0)))
            if result:
                return result
        except json.JSONDecodeError:
            continue

    # 4. Greedy brace matching: find outermost { ... } containing a tool name
    for m in re.finditer(r"\{", text):
        start = m.start()
        depth = 0
        end = start
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if depth == 0 and end > start:
            candidate = text[start:end]
            try:
                result = _parse_obj(json.loads(candidate))
                if result:
                    return result
            except json.JSONDecodeError:
                continue

    return None


class ToolCallFixerChatModel(ChatOllama):
    """ChatOllama subclass that promotes text-based tool calls to real ones.

    Also prevents infinite tool-call loops: if the last message in the
    conversation is already a ToolMessage (i.e. the model just got a tool
    result back), we strip tools from the request so the model is forced
    to respond with natural language.
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        # If the model just received a tool result, don't offer tools again
        # so it responds with text instead of re-calling the same tool
        from langchain_core.messages import ToolMessage
        last_is_tool_result = messages and isinstance(messages[-1], ToolMessage)
        if last_is_tool_result:
            kwargs.pop("tools", None)

        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        if not last_is_tool_result:
            for gen in result.generations:
                msg = gen.message
                if not msg.tool_calls and msg.content:
                    parsed = _try_parse_tool_calls(msg.content)
                    if parsed:
                        msg.tool_calls = parsed
                        msg.content = ""
        return result

app = Flask(__name__)
app.secret_key = _os.environ.get("SECRET_KEY", "dev-secret-change-in-production")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False  # Set True in production behind HTTPS

# ── Auth setup ────────────────────────────────────────────────────────────────
from auth.middleware import login_manager, auth_guard
from auth.routes import auth_bp, init_oauth
from auth.db import init_db, SessionLocal

login_manager.init_app(app)
init_oauth(app)
app.register_blueprint(auth_bp)
app.before_request(auth_guard)

@app.teardown_appcontext
def shutdown_session(exception=None):
    SessionLocal.remove()

# Create tables on first run (use Alembic migrations in production)
with app.app_context():
    init_db()

_FRONTEND_DIST = _os.path.join(_os.path.dirname(__file__), "frontend", "dist")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """Serve React SPA from frontend/dist/."""
    full = _os.path.join(_FRONTEND_DIST, path)
    if path and _os.path.isfile(full):
        return send_file(full)
    index = _os.path.join(_FRONTEND_DIST, "index.html")
    if _os.path.isfile(index):
        return send_file(index)
    return "Frontend not built. Run: cd frontend && npm run build", 404


# ── State ────────────────────────────────────────────────────────────────────
_state = {
    "model": None,
    "system_prompt": """You are a helpful assistant with access to filesystem, search, and web tools.

## Tool families

**Filesystem tools** — read, info, ls, tree, write, append, replace, insert, delete, copy, move, mkdir, grep, find, definition
These are short-named for efficiency. They operate on the local filesystem. Use them for any file or directory operation.

## Response discipline

After receiving tool results, your ONLY job is to answer the user's specific question using those results.

NEVER describe the format or structure of tool results. NEVER say things like "The tool returned a JSON object containing..." or "Each object includes details such as..." — the user does not care about the data format. They care about the CONTENT.

WRONG response to eBay results:
"The tool response is a JSON object containing an array of objects, each representing a GPU product listing. Each object includes details such as the title, URL, price text, and shipping information."

CORRECT response to eBay results:
"1. EVGA RTX 3060 12GB - $189.00 (free shipping) — ebay.com/itm/123456
2. MSI RTX 3060 Ventus — $195.00 (+$10 shipping) — ebay.com/itm/789012"

Rules:
- Extract the actual data from tool results and present it as human-readable text.
- Do NOT describe the JSON structure, field names, or data types.
- Do NOT explain what the tool does or how you called it.
- Do NOT add background context or unsolicited advice.
- Do NOT restate the user's question back to them.
- If results are empty, say so in one sentence and stop.

## Marketplace tool selection

You have tools for eBay, Amazon, Craigslist, and cross-platform flows. Choose the right one:

### Single-platform tools
- **ebay_search** — Quick single-page eBay lookup. Use for browsing or checking availability.
- **ebay_sold_search** — eBay completed/sold listings. Use to check actual market prices.
- **ebay_deep_scan** — Multi-page paginated eBay scan with GPU model extraction. Use for volume analysis.
- **amazon_search** — Search Amazon product listings. Returns price, rating, Prime status.
- **craigslist_search** — Search one Craigslist city. Denver-area cities (denver, boulder, colorado springs, fort collins, pueblo) are within 100mi and can be pickup. All other cities require shipping.
- **craigslist_multi_search** — LOOPING tool that searches multiple Craigslist cities. Use scope='local' for Denver area only, 'shipping' for distant cities (shipping required), or 'all' for everywhere.

### Flow tools (LOOPING — these run multi-step pipelines internally)
- **cross_platform_search** — Searches eBay + Amazon + Craigslist in one call. Use when the user wants to compare across platforms or see what's available everywhere.
- **deal_finder** — The most powerful flow. Runs a full pipeline: deep-scans eBay (3 pages), searches Amazon, searches Craigslist across all cities, groups results by product model, computes median prices per group, and flags listings >=20% below median as deals. Use this whenever the user asks for deals, bargains, underpriced listings, or best value across platforms.
- **enrichment_pipeline** — LOOPING tool that iteratively enriches data using a small eval model. Each iteration adds a new dimension/consideration. The eval model decides when to stop. Use when the user wants data enriched with multiple considerations, ratings, categorizations, or analysis layers. Pass in data from any prior tool call + a goal describing what to add.

### When to use which
- User wants to browse one platform → use the single-platform tool
- User wants to compare prices across platforms → use `cross_platform_search`
- User asks "find me deals" or "what's underpriced" → use `deal_finder`
- User asks about sold/market prices → use `ebay_sold_search`

### Craigslist fulfillment rules
- Cities within ~100mi of Denver (pickup OK): denver, boulder, colorado springs, fort collins, pueblo
- All other cities: shipping required. The tools automatically filter for shipping-available listings in non-local cities and tag each result with fulfillment type (pickup vs shipping_required).

## eBay price analysis rules

When the user asks you to find deals, underpriced listings, high-margin opportunities, or compare prices from eBay search results, follow these rules strictly:

1. **Group by exact model.** Only compare listings that are the same specific product model. For example, "RTX 3060" is a different group from "RTX 3060 Ti", which is different from "RTX 3070". A lower-tier model costing less than a higher-tier model is expected — that is NOT a deal.

2. **Compute per-group statistics.** For each model group:
   - Count the number of listings.
   - Calculate the median price (not the mean — outliers skew means).
   - Identify the lowest price in the group.

3. **Flag a listing as underpriced only if** its price is ≥20% below the median price of its own model group AND the group has at least 3 listings (too few listings means unreliable comparison).

4. **Include total cost.** Always add the shipping cost to the listing price before comparing. A "$200 + $50 shipping" listing is $250 total, not $200.

5. **Present results clearly.** When reporting deals, show:
   - The model name and the listing's total price (price + shipping).
   - The group median for that model.
   - The percentage below median.
   - The listing URL.

6. **If no listings meet the criteria**, say so explicitly — do not stretch the definition to force results.

## NVIDIA GPU generations reference

When searching for or analyzing GPU listings, only consider cards with current AI/ML relevance. Ignore anything older than Turing.

| Generation | Architecture | Year | Consumer (GeForce) | Workstation / Data Center | AI/ML notes |
|---|---|---|---|---|---|
| Turing | Turing (SM 7.5) | 2018 | RTX 2060/2070/2080, GTX 1650/1660 | Quadro RTX 4000/5000/6000/8000, T4 | First-gen tensor cores. T4 still widely deployed for inference. 2060+ usable for light training. |
| Ampere | Ampere (SM 8.0/8.6) | 2020 | RTX 3060/3070/3080/3090 | A100, A40, A30, A10, A6000, A5000, A4000 | 3rd-gen tensor cores, TF32. A100 is the workhorse of modern AI training. RTX 3090 (24GB) popular for local training. |
| Ada Lovelace | Ada (SM 8.9) | 2022 | RTX 4060/4070/4080/4090 | L40, L40S, RTX 6000 Ada | 4th-gen tensor cores, FP8. RTX 4090 (24GB) is top consumer AI card. L40S for data center inference. |
| Hopper | Hopper (SM 9.0) | 2022 | — | H100, H200 | Transformer Engine, HBM3. H100 is the flagship training GPU. No consumer version. |
| Blackwell | Blackwell (SM 10.0) | 2024 | RTX 5070/5080/5090 | B100, B200, GB200 | 5th-gen tensor cores, FP4. Latest generation. RTX 5090 (32GB) for consumer. |

**Skip these — no AI/ML relevance:**
- Kepler (2012): GTX 600/700, Quadro K-series (K2200, K4200, K5200, K6000)
- Maxwell (2014): GTX 900, Quadro M-series
- Pascal (2016): GTX 1060/1070/1080, Quadro P-series, Tesla P100/P40 (P100 is marginal — old but has FP16)
- Volta (2017): Titan V, Tesla V100 (V100 still has some relevance for legacy HPC but is end-of-life)

When the user asks about GPU deals for AI/ML, only search for and analyze Turing or newer cards. If results contain older generation cards, filter them out and note that they were excluded.""",
    "history": [],          # list of {"role": ..., "content": ...}
    "selected_tools": [],   # indices into ALL_TOOLS (for display only)
}


def _tool_meta(t) -> dict:
    """Extract name, description, and parameter info from a LangChain tool."""
    schema = t.args_schema.schema() if t.args_schema else {}
    props = schema.get("properties", {})
    required = schema.get("required", [])
    params = {}
    for pname, pinfo in props.items():
        params[pname] = {
            "type": pinfo.get("type", "string"),
            "description": pinfo.get("description", ""),
            "required": pname in required,
        }
        if "default" in pinfo:
            params[pname]["default"] = pinfo["default"]
    return {
        "name": t.name,
        "description": t.description.split("\n")[0] if t.description else "",
        "params": params,
    }


TOOL_REGISTRY = [_tool_meta(t) for t in ALL_TOOLS]


# ── Models ───────────────────────────────────────────────────────────────────

@app.route("/api/models", methods=["GET"])
def list_models():
    """List locally available Ollama models."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models]
        return jsonify({"models": names, "current": _state["model"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/models", methods=["POST"])
def select_model():
    """Select an Ollama model.  Body: {"model": "name"}"""
    data = request.get_json(force=True)
    model = data.get("model")
    if not model:
        return jsonify({"error": "model required"}), 400
    _state["model"] = model
    _state["history"] = []
    return jsonify({"model": model})


# ── Tools browser ────────────────────────────────────────────────────────────

@app.route("/api/tools", methods=["GET"])
def get_tools():
    """Return the 2-column tool state: available (left) and selected (right)."""
    selected_idx = set(_state["selected_tools"])
    available = []
    selected = []
    for i, meta in enumerate(TOOL_REGISTRY):
        entry = {"index": i, **meta}
        if i in selected_idx:
            selected.append(entry)
        else:
            available.append(entry)
    return jsonify({"available": available, "selected": selected})


@app.route("/api/tools/select", methods=["POST"])
def select_tool():
    """Move a tool from available -> selected.  Body: {"index": N}
    This is the > button."""
    data = request.get_json(force=True)
    idx = data.get("index")
    if idx is None or idx < 0 or idx >= len(TOOL_REGISTRY):
        return jsonify({"error": "invalid index"}), 400
    if idx not in _state["selected_tools"]:
        _state["selected_tools"].append(idx)
    return get_tools()


@app.route("/api/tools/deselect", methods=["POST"])
def deselect_tool():
    """Move a tool from selected -> available.  Body: {"index": N}
    This is the < button."""
    data = request.get_json(force=True)
    idx = data.get("index")
    if idx in _state["selected_tools"]:
        _state["selected_tools"].remove(idx)
    return get_tools()


@app.route("/api/tools/<int:index>", methods=["GET"])
def tool_detail(index: int):
    """Get full detail (params) for a tool by index."""
    if index < 0 or index >= len(TOOL_REGISTRY):
        return jsonify({"error": "invalid index"}), 404
    return jsonify(TOOL_REGISTRY[index])


# ── System prompt ────────────────────────────────────────────────────────────

@app.route("/api/system", methods=["GET"])
def get_system():
    return jsonify({"system_prompt": _state["system_prompt"]})


@app.route("/api/system", methods=["POST"])
def set_system():
    data = request.get_json(force=True)
    _state["system_prompt"] = data.get("system_prompt", _state["system_prompt"])
    return jsonify({"system_prompt": _state["system_prompt"]})


# ── Chat ─────────────────────────────────────────────────────────────────────

def _build_agent():
    """Build a LangGraph agent using create_agent (langchain >= 1.2)."""
    if not _state["model"]:
        raise ValueError("No model selected. POST /api/models first.")

    llm = ToolCallFixerChatModel(
        model=_state["model"],
        temperature=0,
        base_url="http://localhost:11434",
    )

    # Only bind selected tools (or none if nothing selected)
    selected_idx = set(_state["selected_tools"])
    tools = [t for i, t in enumerate(ALL_TOOLS) if i in selected_idx] if selected_idx else []
    agent = create_agent(
        llm,
        tools,
        system_prompt=_state["system_prompt"],
    )
    return agent


def _history_to_messages() -> list:
    """Convert internal history to LangChain messages."""
    msgs = []
    for m in _state["history"]:
        if m["role"] == "user":
            msgs.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            msgs.append(AIMessage(content=m["content"]))
    return msgs


@app.route("/api/chat", methods=["POST"])
def chat():
    """Send a message.  Body: {"message": "..."}
    Returns: {"response": "..."}
    """
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "message required"}), 400

    try:
        agent = _build_agent()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    messages = _history_to_messages()
    messages.append(HumanMessage(content=user_msg))
    _state["history"].append({"role": "user", "content": user_msg})

    try:
        result = agent.invoke({"messages": messages})
        # Extract the last AI message from the result
        output_msgs = result.get("messages", [])
        response = ""
        for msg in reversed(output_msgs):
            if isinstance(msg, AIMessage) and msg.content:
                response = msg.content
                break
        _state["history"].append({"role": "assistant", "content": response})
        return jsonify({"response": response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """Streaming version of chat. Returns newline-delimited JSON."""
    data = request.get_json(force=True)
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"error": "message required"}), 400

    try:
        agent = _build_agent()
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    messages = _history_to_messages()
    messages.append(HumanMessage(content=user_msg))
    _state["history"].append({"role": "user", "content": user_msg})

    def generate():
        from langchain_core.messages import ToolMessage
        full_response = ""
        try:
            for event in agent.stream({"messages": messages}, stream_mode="updates"):
                for node_name, node_output in event.items():
                    if "messages" not in node_output:
                        continue
                    for msg in node_output["messages"]:
                        # Tool calls (AI decided to call a tool)
                        tc = getattr(msg, "tool_calls", None)
                        if tc:
                            for call in tc:
                                yield json.dumps({"tool_call": {
                                    "tool": call.get("name", ""),
                                    "input": str(call.get("args", "")),
                                }}) + "\n"
                        # Tool results
                        elif isinstance(msg, ToolMessage):
                            yield json.dumps({"tool_result": {
                                "tool": getattr(msg, "name", ""),
                                "output": str(msg.content)[:500],
                            }}) + "\n"
                        # AI text response (final answer)
                        elif msg.content:
                            full_response = msg.content
                            yield json.dumps({"chunk": msg.content}) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
            return

        _state["history"].append({"role": "assistant", "content": full_response})
        yield json.dumps({"done": True, "full_response": full_response}) + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Agent proxy endpoints ────────────────────────────────────────────────────

@app.route("/api/agent/<agent_name>/call", methods=["POST"])
def call_agent(agent_name: str):
    """Proxy a tool call to a specific agent.

    Body: {"tool": "tool_name", "params": {...}}
    """
    if agent_name not in AGENT_PORTS:
        return jsonify({"error": f"Unknown agent: {agent_name}"}), 404

    data = request.get_json(force=True)
    tool_name = data.get("tool", "")
    params = data.get("params", {})

    try:
        url = agent_url(agent_name)
        resp = httpx.post(
            f"{url}/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": params},
                "id": 1,
            },
            timeout=60.0,
        )
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents", methods=["GET"])
def list_agents():
    """List all available agents and their status."""
    agents = {}
    for name, port in AGENT_PORTS.items():
        try:
            resp = httpx.post(
                f"http://127.0.0.1:{port}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                timeout=2.0,
            )
            resp.raise_for_status()
            agents[name] = {"port": port, "status": "up"}
        except Exception:
            agents[name] = {"port": port, "status": "down"}
    return jsonify(agents)


@app.route("/api/history", methods=["GET"])
def get_history():
    return jsonify({"history": _state["history"]})


@app.route("/api/history", methods=["DELETE"])
def clear_history():
    _state["history"] = []
    return jsonify({"cleared": True})


# ── CLI tool browser (for terminal use) ─────────────────────────────────────

def cli_tool_browser():
    """Interactive 2-column tool browser for the terminal."""
    selected_idx = set()

    while True:
        available = [(i, TOOL_REGISTRY[i]) for i in range(len(TOOL_REGISTRY)) if i not in selected_idx]
        selected = [(i, TOOL_REGISTRY[i]) for i in sorted(selected_idx)]

        # Render 2 columns
        col_w = 38
        print("\n" + "=" * (col_w * 2 + 7))
        print(f"{'AVAILABLE':<{col_w}}  | >  | {'SELECTED':<{col_w}}")
        print("-" * (col_w * 2 + 7))

        max_rows = max(len(available), len(selected), 1)
        for row in range(max_rows):
            left = f"  {available[row][0]:>2}. {available[row][1]['name']}" if row < len(available) else ""
            right = f"  {selected[row][0]:>2}. {selected[row][1]['name']}" if row < len(selected) else ""
            print(f"{left:<{col_w}}  |    | {right:<{col_w}}")

        print("-" * (col_w * 2 + 7))
        print("Commands:  > N  (select)   < N  (deselect)   ? N  (inspect)   q  (done)")
        cmd = input("> ").strip()

        if cmd.lower() == "q":
            break
        elif cmd.startswith(">"):
            try:
                idx = int(cmd[1:].strip())
                if 0 <= idx < len(TOOL_REGISTRY):
                    selected_idx.add(idx)
                    meta = TOOL_REGISTRY[idx]
                    print(f"\n  + {meta['name']}: {meta['description']}")
                    if meta["params"]:
                        print("    Params required from user:")
                        for pn, pi in meta["params"].items():
                            req = "*" if pi["required"] else ""
                            default = f" (default: {pi.get('default', '')})" if "default" in pi else ""
                            print(f"      {req}{pn} ({pi['type']}){default}: {pi['description']}")
            except ValueError:
                print("  Usage: > N")
        elif cmd.startswith("<"):
            try:
                idx = int(cmd[1:].strip())
                selected_idx.discard(idx)
            except ValueError:
                print("  Usage: < N")
        elif cmd.startswith("?"):
            try:
                idx = int(cmd[1:].strip())
                if 0 <= idx < len(TOOL_REGISTRY):
                    meta = TOOL_REGISTRY[idx]
                    print(f"\n  {meta['name']}: {meta['description']}")
                    for pn, pi in meta["params"].items():
                        req = "*" if pi["required"] else ""
                        default = f" (default: {pi.get('default', '')})" if "default" in pi else ""
                        print(f"    {req}{pn} ({pi['type']}){default}: {pi['description']}")
            except ValueError:
                print("  Usage: ? N")

    _state["selected_tools"] = sorted(selected_idx)
    print(f"\nSelected {len(selected_idx)} tools (all {len(ALL_TOOLS)} are still bound to agent).")


def cli_model_picker():
    """Interactive model picker for the terminal."""
    try:
        models = ollama_client.list()
        names = [m.model for m in models.models]
    except Exception as e:
        print(f"Error listing models: {e}")
        return

    print("\nAvailable Ollama models:")
    for i, name in enumerate(names):
        marker = " *" if name == _state["model"] else ""
        print(f"  {i:>2}. {name}{marker}")

    choice = input("\nSelect model number (or Enter to keep current): ").strip()
    if choice.isdigit() and 0 <= int(choice) < len(names):
        _state["model"] = names[int(choice)]
        print(f"Model set to: {_state['model']}")


def cli_chat():
    """Interactive chat loop for the terminal."""
    if not _state["model"]:
        print("No model selected. Pick one first.")
        cli_model_picker()
        if not _state["model"]:
            return

    print(f"\nChat with {_state['model']} ({len(ALL_TOOLS)} tools bound)")
    print("Type 'quit' to exit, 'clear' to reset history.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() == "quit":
            break
        if user_input.lower() == "clear":
            _state["history"] = []
            print("  (history cleared)")
            continue

        agent = _build_agent()
        messages = _history_to_messages()
        messages.append(HumanMessage(content=user_input))
        _state["history"].append({"role": "user", "content": user_input})

        print("Agent: ", end="", flush=True)
        try:
            result = agent.invoke({"messages": messages})
            output_msgs = result.get("messages", [])
            response = ""
            for msg in reversed(output_msgs):
                if isinstance(msg, AIMessage) and msg.content:
                    response = msg.content
                    break
            _state["history"].append({"role": "assistant", "content": response})
            print(response)
        except Exception as e:
            print(f"\n  [Error: {e}]")


def main():
    import sys

    if "--seed-admin" in sys.argv:
        from auth.seed import seed_admin
        with app.app_context():
            seed_admin()
        return

    if "--promote-admin" in sys.argv:
        from auth.seed import promote_admin
        idx = sys.argv.index("--promote-admin")
        username = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else None
        if not username:
            print("Usage: python main.py --promote-admin <username>")
            return
        with app.app_context():
            promote_admin(username)
        return

    if "--serve" in sys.argv:
        port = 5000
        for arg in sys.argv:
            if arg.startswith("--port="):
                port = int(arg.split("=")[1])
        print(f"Starting Flask API on http://localhost:{port}")
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        # Interactive CLI mode
        print("=== Agentic Chat (LangChain + Ollama) ===")
        while True:
            print("\n  1. Pick model")
            print("  2. Browse tools")
            print("  3. Chat")
            print("  4. Set system prompt")
            print("  5. Start API server")
            print("  q. Quit")
            choice = input("\n> ").strip()

            if choice == "1":
                cli_model_picker()
            elif choice == "2":
                cli_tool_browser()
            elif choice == "3":
                cli_chat()
            elif choice == "4":
                prompt = input("System prompt: ").strip()
                if prompt:
                    _state["system_prompt"] = prompt
                    print("  Updated.")
            elif choice == "5":
                app.run(host="0.0.0.0", port=5000, debug=True)
            elif choice.lower() == "q":
                break


if __name__ == "__main__":
    main()
