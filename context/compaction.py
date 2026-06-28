"""Inline context compaction.

Runs at the START of a turn, before the agent is built — a conflict-free point,
since no stream is active yet. When the assembled prompt would exceed a fraction
of the context window, messages older than a recent window are folded into the
conversation's running_summary (incremental: only messages newer than the last
fold are summarized). Messages are NEVER deleted; compaction only changes what
is sent to the model this turn.

The full transcript stays in the DB for the UI, re-summarization, and audit.
"""

from context import build_history
from agents.agent_summary import fold_summary

# Fraction of the context window at which compaction triggers.
COMPACT_AT_PCT = 0.75
# Messages kept verbatim after the summary (the rest are folded).
RECENT_WINDOW = 4


def needs_compaction(estimated_tokens: int, ctx_size: int) -> bool:
    """One responsibility: is the prompt over the compaction threshold?"""
    return ctx_size > 0 and estimated_tokens >= ctx_size * COMPACT_AT_PCT


def _render_exchanges(rows: list) -> str:
    """One responsibility: flatten message rows into summarizable text."""
    lines = []
    for row in rows:
        content = (row.content or "").strip()
        if content:
            lines.append(f"{row.role}: {content}")
    return "\n".join(lines)


def fold_old_messages(conversation, db_rows: list):
    """Fold messages older than RECENT_WINDOW into conversation.running_summary.

    Only rows newer than summary_covers_through are sent to the summarizer, so
    the fold stays small. Mutates the conversation row (caller commits). Returns
    the recent rows kept verbatim.
    """
    older = db_rows[:-RECENT_WINDOW]
    recent = db_rows[-RECENT_WINDOW:]

    covers = conversation.summary_covers_through
    unfolded = [r for r in older if covers is None or r.created_at > covers]

    if unfolded:
        conversation.running_summary = fold_summary(
            conversation.running_summary or "", _render_exchanges(unfolded)
        )
        conversation.summary_covers_through = older[-1].created_at

    return recent


def compacted_history(running_summary: str, recent_rows: list) -> list:
    """One responsibility: build [summary] + recent as replacement history.

    The new user message is appended downstream by the caller, so it is not
    included here.
    """
    head = (
        [{"role": "user", "content": f"[CONVERSATION SO FAR]\n{running_summary}"}]
        if running_summary
        else []
    )
    recent_dicts = [
        {"role": r.role, "content": r.content, "tool_calls": r.tool_calls or []}
        for r in recent_rows
    ]
    return head + build_history(recent_dicts)
