"""Per-role agent definitions.

Each agent owns its own system prompt and is constructed with qwen-agent's
creation functions:

- agent_main    → the user-facing chat agent (routes/chat.py)
- agent_summary → context compression against the summary model
- agent_taskmgr → maintains the conversation task list as a flat
                  root → edge → node graph, writing directly to ConversationTask
"""
