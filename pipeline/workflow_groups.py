"""Static registry of workflow groups for tool curation.

Each group maps a human-readable name to a list of tool names and a short
tooltip. The Tool Curator recommends groups — not individual tools.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowGroup:
    tools: list[str]
    tooltip: str
    gate: str | None = None  # 'waiver' | 'age' — requires Dashboard acceptance before use


WORKFLOW_GROUPS: dict[str, WorkflowGroup] = {
    "Filesystem": WorkflowGroup(
        tools=["fs_read", "fs_info", "fs_ls", "fs_ls_dir", "fs_tree", "fs_write", "fs_append",
               "fs_replace", "fs_insert_at_line", "fs_delete", "fs_copy", "fs_move",
               "fs_make_dir", "fs_grep", "fs_find", "fs_find_def"],
        tooltip="File reading, writing, and directory operations, and codesearch functions like fs_find_def to find function definitions",
    ),
    "Web Tools": WorkflowGroup(
        tools=["www_ddg", "www_find_content", "www_set_cookies", "www_set_local_storage",
               "www_find_dl", "www_dl", "www_dl_status", "www_find_routes",
               "www_query", "www_click", "www_find_struct"],
        tooltip="Web search, fetch-and-extract, and browser navigation",
    ),
    "Presentation": WorkflowGroup(
        tools=["ap_img", "ap_vid", "ap_gallery", "ap_txt", "ap_md"],
        tooltip="Display images, videos, galleries, text, and markdown inline in the chat",
    ),
    "Ecommerce": WorkflowGroup(
        tools=["ec_search", "ec_enrich"],
        tooltip="Product search across eBay, Amazon, and Craigslist",
    ),
    "OnlyFans": WorkflowGroup(
        tools=["of_extract", "of_extract_all",
               "of_scroll_convos", "of_scroll_msgs",
               "of_save_media"],
        tooltip="Creator discovery, profiles, and media management",
        gate="age",
    ),
    "Torrent": WorkflowGroup(
        tools=["bt_search", "bt_download", "bt_plugins",
               "bt_toggle_plugin", "bt_add", "bt_active"],
        tooltip="Torrent search, download, and management",
    ),
    "MCP": WorkflowGroup(
        tools=["mcp_init_conn","mcp_call_tool"],
        tooltip="Connect to external MCP tool servers",
    ),
    "Jobs": WorkflowGroup(
        tools=["jb_search", "jb_fetch"],
        tooltip="Job posting search (Indeed) and posting detail fetch",
    ),
    "Accounting": WorkflowGroup(
        tools=["fa_ledger", "fa_new_acct", "fa_ls_accts",
               "fa_acct_bal", "fa_update_acct",
               "fa_tx_new", "fa_tx_search",
               "fa_tx_void", "fa_acct_det",
               "fa_new_item", "fa_receive",
               "fa_ls_items", "fa_rm_item",
               "fa_tx_sale",
               "fa_value", "fa_close",
               "fa_stmt"],
        tooltip="Double-entry bookkeeping and financial reports",
    ),
    "Vision": WorkflowGroup(
        tools=["vis_desc_img"],
        tooltip="Image analysis and description via vision model",
    ),
    "Bug Bounty": WorkflowGroup(
        tools=["bb_h1_programs", "bb_h1_disclosures", "bb_h1_company",
               "bb_bc_programs", "bb_bc_disclosures",
               "bb_inti_programs", "bb_ywh_programs", "bb_synack_programs",
               "bb_search", "bb_vuln_types"],
        tooltip="Bug bounty program discovery and vulnerability research across HackerOne, Bugcrowd, Intigriti, YesWeHack, Synack",
        gate="waiver",
    ),
    "Exploit": WorkflowGroup(
        tools=["xp_sinj", "xp_xss", "xp_ssrf", "xp_cmdi", "xp_trav", "xp_rce", "xp_scan", "xp_gen"],
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

    # Group tools by their workflow group
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
