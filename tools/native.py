
import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)

import json
import re

import json5
import requests
from qwen_agent.tools.base import register_tool, BaseTool, TOOL_REGISTRY as QW_TOOL_REGISTRY

from pipeline.workflow_groups import TOOL_REF, WORKFLOW_GROUPS
from tools._output import tool_result
# ─────────────────────────────────────────────────────────────
# INTERNAL TOOLS
# Registered as qwen-agent tools so Assistant handles them natively.
# ─────────────────────────────────────────────────────────────

@register_tool('get_params')
class GetParamsTool(BaseTool):
  description = 'Look up a tool\'s parameters before calling it. Returns param names, types, descriptions, and which are required.'
  parameters = {
  'type': 'object',
  'properties': {
    'tool_name': {'type': 'string', 'description': 'Name of the tool to look up.'},
  },
  'required': ['tool_name'],
  }

  def call(self, params: str, **kwargs) -> dict:
    from tools._output import tool_result
    p = json5.loads(params)
    name = p.get('tool_name', '')
    cls = QW_TOOL_REGISTRY.get(name)
    if not cls:
      return tool_result(error=f"Unknown tool '{name}'")
    schema = getattr(cls, 'parameters', {})
    props = schema.get('properties', {})
    required = set(schema.get('required', []))
    param_list = []
    for pname, pdef in props.items():
      param_list.append({
        "name": pname,
        "type": pdef.get("type", "string"),
        "required": pname in required,
        "description": pdef.get("description", ""),
    })
    return tool_result(data={
      "tool": name,
      "description": getattr(cls, 'description', ''),
      "params": param_list,
    })


@register_tool('list_tools')
class ListToolsTool(BaseTool):
  description = 'List available tools grouped by category. Pass a query to filter by name or description (e.g. "web", "file", "accounting"). Omit query to list all.'
  parameters = {
  'type': 'object',
  'properties': {
    'query': {'type': 'string', 'description': 'Optional keyword to filter tools by name or description.'},
  },
  'required': [],
  }
  def call(self, params: str, **kwargs) -> dict:
    from tools._output import tool_result
    from pipeline.workflow_groups import TOOL_REF
    p = json5.loads(params) if params and params.strip() not in ('{}', '') else {}
    query = (p.get('query') or '').strip().lower()

    all_groups = dict(WORKFLOW_GROUPS)
    native = {'tooltip': 'Task management', 'tools': ['tl_add', 'tl_ref', 'tl_done', 'list_tools', 'get_params']}

    def _with_descs(names):
      return {t: TOOL_REF.get(t, '') for t in names}

    groups = {}
    for name, group in all_groups.items():
      tools = group.tools
      if query:
        tools = [t for t in tools if query in t.lower() or query in TOOL_REF.get(t, '').lower()]
      if tools:
        groups[name] = {'tooltip': group.tooltip, 'tools': _with_descs(tools)}

    if not query or any(query in t.lower() or query in TOOL_REF.get(t, '').lower() for t in native['tools']):
      groups['Native'] = {**native, 'tools': _with_descs(native['tools'])}

    if not groups:
      return tool_result(data={'message': f'No tools match "{query}". Try a broader term.'})
    return tool_result(data=groups)


_STOP_WORDS = frozenset({
    'i', 'a', 'an', 'the', 'to', 'for', 'and', 'or', 'of', 'in', 'on',
    'with', 'need', 'want', 'use', 'using', 'my', 'me', 'some', 'get',
    'it', 'its', 'that', 'this', 'from', 'by', 'be', 'is', 'are', 'do',
})


def _filter_catalog(description: str) -> dict[str, str]:
    """Return the ~15 most keyword-relevant tools from TOOL_REF for this description."""
    words = {w for w in re.findall(r'[a-z]+', description.lower()) if w not in _STOP_WORDS}
    if not words:
        return TOOL_REF

    scores: list[tuple[int, str]] = []
    for name, desc in TOOL_REF.items():
        haystack = re.findall(r'[a-z]+', f'{name} {desc}'.lower())
        score = sum(1 for w in words if w in haystack)
        scores.append((score, name))

    scores.sort(reverse=True)
    top = [name for score, name in scores if score > 0][:15]
    if not top:
        return TOOL_REF
    return {name: TOOL_REF[name] for name in top}


_ROUTER_SYSTEM = (
    "You are a tool router. Your job is to select tools from a catalog that satisfy a task description.\n"
    "Rules:\n"
    "- If the agent names a specific tool, always include it exactly as named.\n"
    "- Any filesystem task must always include fs_find_def, fs_replace, and fs_tree alongside any other fs tools.\n"
    "- If you are uncertain between candidates, return your top 2.\n"
    "- Return ONLY a JSON array of tool names. No explanation, no markdown."
)

def _route_tools(description: str) -> list[str]:
    """Route tools using Neo4j graph summaries. Falls back to LLM-based routing."""
    from config import SUMMARIZE_MODEL, SUMMARIZE_SERVER_URL, LLAMA_SERVER_URL

    # class.__name__ → registered name: the graph keys tools by CLASS name
    # (e.g. 'BrowserClickTool') but the registry is keyed by the tool's `name`
    # attribute (e.g. 'www_click').
    class_to_name = {cls.__name__: reg for reg, cls in QW_TOOL_REGISTRY.items()}

    def _to_registered(graph_name: str) -> str:
        if graph_name in QW_TOOL_REGISTRY:
            return graph_name
        return class_to_name.get(graph_name, graph_name)

    # Primary: Neo4j-based scoring against tool summaries
    try:
        from services.neo4j_context import score_tools_for_task
        scored = score_tools_for_task(description, limit=15)
        if scored:
            # Top-scoring tools that exist in registry (after name translation)
            names = [_to_registered(t["name"]) for t in scored]
            names = [n for n in names if n in QW_TOOL_REGISTRY]
            if names:
                return names[:10]
    except Exception as e:
        print(f'[tool_router] Neo4j routing error: {e}', flush=True)

    # Fallback: original LLM-based routing
    catalog_dict = _filter_catalog(description)
    catalog = '\n'.join(f'  {name}: {desc}' for name, desc in catalog_dict.items())
    prompt = (
        f"Catalog:\n{catalog}\n\n"
        f"Task: {description}\n\n"
        'Return format: ["tool_name"] or ["tool_a", "tool_b"]'
    )
    server = SUMMARIZE_SERVER_URL or LLAMA_SERVER_URL
    try:
        resp = requests.post(
            f"{server}/v1/chat/completions",
            json={
                "model": SUMMARIZE_MODEL,
                "messages": [
                    {"role": "system", "content": _ROUTER_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "max_tokens": 80,
                "chat_template_kwargs": {"thinking": False},
            },
            timeout=30,
        )
        content = resp.json()["choices"][0]["message"]["content"].strip()
        match = re.search(r'\[.*?\]', content, re.DOTALL)
        if match:
            names = json.loads(match.group())
            return [n for n in names if isinstance(n, str) and n in QW_TOOL_REGISTRY]
    except Exception as e:
        print(f'[tool_router] LLM routing error: {e}', flush=True)
    return []
