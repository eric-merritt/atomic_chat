"""Static registry of workflow groups for tool curation.

Each group maps a human-readable name to a set of tools and a short tooltip.
The Tool Curator recommends groups — not individual tools.

Tools are auto-discovered from TOOL_REGISTRY by prefix. Any tool registered
with @register_tool whose name starts with the group's prefix is included
automatically — no manual list maintenance required.
"""


class WorkflowGroup:
  """Workflow group with lazy prefix-based tool discovery.

  If `prefix` is set, `tools` returns all TOOL_REGISTRY entries whose name
  starts with that prefix, merged after any explicit `tools` entries.
  If only `tools` is provided (no prefix), behaves like the old frozen dataclass.
  """
  def __init__(
    self,
    tooltip: str,
    prefix: str | None = None,
    tools: list[str] | None = None,
    gate: str | None = None,
  ):
    self.tooltip = tooltip
    self.prefix = prefix
    self._tools = tools or []
    self.gate = gate

  @property
  def tools(self) -> list[str]:
    if not self.prefix:
      return self._tools
    from qwen_agent.tools.base import TOOL_REGISTRY
    seen = set(self._tools)
    discovered = [ name for name in TOOL_REGISTRY if name.startswith(self.prefix) and name not in seen ]
    return self._tools + sorted(discovered)


WORKFLOW_GROUPS: dict[str, WorkflowGroup] = {
  "Shell": WorkflowGroup(
    tools=["cli_bash"],
    tooltip="Execute shell commands with user confirmation",
  ),
  "CLI": WorkflowGroup(
    prefix="cli_",
    tooltip="CLI utilities — git, package managers, and other command-line workflows",
  ),
  "Filesystem": WorkflowGroup(
    prefix="fs_",
    tooltip="File reading, writing, and directory operations, and codesearch functions like fs_find_def to find function definitions",
  ),
  "Web Tools": WorkflowGroup(
    prefix="www_",
    tooltip="Web search, fetch-and-extract, browser navigation, and media downloads",
  ),
  "Presentation": WorkflowGroup(
    prefix="ap_",
    tooltip="Display images, videos, galleries, text, and markdown inline in the chat",
  ),
  "Ecommerce": WorkflowGroup(
    prefix="ec_",
    tooltip="Product search across eBay, Amazon, and Craigslist",
  ),
  "OnlyFans": WorkflowGroup(
    prefix="of_",
    tooltip="Creator discovery, profiles, and media management",
    gate="age",
  ),
  "Torrent": WorkflowGroup(
    prefix="bt_",
    tooltip="Torrent search, download, and management",
  ),
  "MCP": WorkflowGroup(
    prefix="mcp_",
    tooltip="Connect to external MCP tool servers",
  ),
  "Jobs": WorkflowGroup(
    prefix="jb_",
    tooltip="Job posting search (Indeed) and posting detail fetch",
  ),
  "Accounting": WorkflowGroup(
    prefix="fa_",
    tooltip="Double-entry bookkeeping and financial reports",
  ),
  "Vision": WorkflowGroup(
    prefix="vis_",
    tooltip="Image analysis and description via vision model",
  ),
  "Bug Bounty": WorkflowGroup(
    prefix="bb_",
    tooltip="Bug bounty program discovery and vulnerability research across HackerOne, Bugcrowd, Intigriti, YesWeHack, Synack",
    gate="waiver",
  ),
  "Exploit": WorkflowGroup(
    prefix="xp_",
    tooltip="Payload generation and vulnerability testing for SQLi, XSS, SSRF, command injection, path traversal, RCE",
    gate="waiver",
  ),
}


class _LazyToolRef:
  """Dict-like view of tool descriptions built from QW_TOOL_REGISTRY on first access.

  Single source of truth: edit the tool class description — TOOL_REF stays in sync.
  """
  _cache: 'dict[str, str] | None' = None

  def _build(self) -> 'dict[str, str]':
    if self._cache is None:
      from qwen_agent.tools.base import TOOL_REGISTRY
      self._cache = {
        name: (getattr(cls, 'description', '') or '').split('\n')[0].strip()
        for name, cls in TOOL_REGISTRY.items()
        if getattr(cls, 'description', None)
      }
    return self._cache

  def get(self, key: str, default: str = '') -> str:
    return self._build().get(key, default)

  def items(self):
    return self._build().items()

  def keys(self):
    return self._build().keys()

  def values(self):
    return self._build().values()

  def __getitem__(self, key: str) -> str:
    return self._build()[key]

  def __contains__(self, key: object) -> bool:
    return key in self._build()

  def __iter__(self):
    return iter(self._build())

  def __len__(self) -> int:
    return len(self._build())


TOOL_REF = _LazyToolRef()


def tool_ref_for_group(group_name: str) -> str:
  """Return a compact reference string for a group's tools."""
  group = WORKFLOW_GROUPS.get(group_name)
  if not group:
    return ""
  return ", ".join(f"{t}: {TOOL_REF.get(t, '?')}" for t in group.tools)


def build_tool_reference(tool_names: list[str]) -> str:
  """Build a system-prompt-ready tool reference with params.

  Format per tool:
    tool_name(param1, param2, ...) — short description
  Grouped by category.
  """
  from qwen_agent.tools.base import TOOL_REGISTRY as QW

  grouped: dict[str, list[str]] = {}
  for name in tool_names:
    g = group_for_tool(name)
    label = g or "Other"
    grouped.setdefault(label, []).append(name)

  lines = []
  for group_label, names in grouped.items():
    lines.append(f"[{group_label}]")
    for name in names:
      desc = TOOL_REF.get(name, "")
      cls = QW.get(name)
      if cls:
        props = getattr(cls, 'parameters', {}).get('properties', {})
        required = set(getattr(cls, 'parameters', {}).get('required', []))
        param_parts = []
        for p in props:
          param_parts.append(f"{p}*" if p in required else p)
        params_str = ", ".join(param_parts)
      else:
        params_str = ""
      lines.append(f"  {name}({params_str}) — {desc}")
    lines.append("")
  return "\n".join(lines).rstrip()


def tools_for_groups(group_names: list[str]) -> list[str]:
  """Return flat list of tool names for the given group names."""
  tools = []
  for name in group_names:
    group = WORKFLOW_GROUPS.get(name)
    if group:
      tools.extend(group.tools)
  return tools


def group_for_tool(tool_name: str) -> str | None:
  """Return the group name a tool belongs to, or None."""
  for name, group in WORKFLOW_GROUPS.items():
    if tool_name in group.tools:
      return name
  return None
