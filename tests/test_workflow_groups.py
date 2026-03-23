from workflow_groups import WORKFLOW_GROUPS, WorkflowGroup


def test_registry_is_not_empty():
    assert len(WORKFLOW_GROUPS) > 0


def test_all_entries_are_workflow_groups():
    for name, group in WORKFLOW_GROUPS.items():
        assert isinstance(group, WorkflowGroup), f"{name} is not a WorkflowGroup"
        assert isinstance(group.tools, list)
        assert len(group.tools) > 0, f"{name} has no tools"
        assert isinstance(group.tooltip, str)
        assert len(group.tooltip) > 0, f"{name} has no tooltip"


def test_no_duplicate_tools_across_groups():
    seen = {}
    for name, group in WORKFLOW_GROUPS.items():
        for tool in group.tools:
            assert tool not in seen, f"Tool '{tool}' in both '{seen[tool]}' and '{name}'"
            seen[tool] = name


def test_all_tools_exist_in_registry():
    from tools import ALL_TOOLS
    all_names = {t.name for t in ALL_TOOLS}
    for name, group in WORKFLOW_GROUPS.items():
        for tool in group.tools:
            assert tool in all_names, f"Tool '{tool}' in group '{name}' not found in ALL_TOOLS"


def test_tooltip_is_concise():
    for name, group in WORKFLOW_GROUPS.items():
        word_count = len(group.tooltip.split())
        assert word_count <= 15, f"{name} tooltip is {word_count} words (max 15)"
