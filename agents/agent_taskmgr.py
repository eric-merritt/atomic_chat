"""Task-manager agent.

This agent is the FIRST receiver of every user message. Before the main agent
runs, it reads the incoming message (plus recent context) and builds the flat
task list the main agent will work off of, writing it directly to
ConversationTask via the `tg_sync` tool.

It also reviews the main agent's tl_done claims at stream close
(review_task_completion), and decomposes user-added tasks on TaskList close.

Built with qwen-agent's Assistant creation function and pointed at the fast
summary model.
"""

from openai import OpenAI
from flask import g

from config import qwen_summary_cfg, SUMMARIZE_MODEL, SUMMARIZE_SERVER_URL

TASKMGR_SYSTEM_PROMPT = """
You break user requests into an atomic task list. You call ONE tool, `tg_sync`, every turn.

YOU SEE: latest user message + existing task list.
YOU OUTPUT: only NEW tasks, plus EDITED tasks (resubmit with their existing id).

A task is atomic when it needs no further breakdown, can be verified objectively,
and can run on its own. Order tasks logically; use depends_on for ordering.

Example — user: "Check the www_fetch_content tool for errors."
1. List tree for the tools folder
2. Search web tools for www_fetch_content
3. Read its lines
4. Identify errors
5. Report to user

Each task has: title, action (what to do), expected_output (proof of done),
depends_on (id it waits on, optional).

EVERY TURN: call tg_sync once.
- New/changed tasks in the message -> pass them.
- Nothing new -> call tg_sync with an empty tasks list.
"""


REVIEW_SYSTEM_PROMPT = """
Your only responsibility is verifying task completion. If the main agent calls "tl_done" you are
the LAST line of DEFENSE that decides if that claim is TRUE or FALSE.

FORMAT IF:
- AGREE (agent did complete): {"agree": true, "reason": "<1 sentence>"}
- DISAGREE (agent did not complete): {"agree": false, "reason": "<1 sentence>"}
"""


def _drain(agent, messages):
    """Run the agent to completion, returning its final message list."""
    final = []
    for responses in agent.run(messages=messages):
        final = responses
    return final


def _last_text(messages: list) -> str:
    """Return the final assistant text from a drained message list."""
    for message in reversed(messages):
        if message.get("role") == "assistant" and message.get("content"):
            return message["content"]
    return ""


def review_task_completion(
    conversation_id: str, task_title: str, evidence: str
) -> dict:
    """Ask the task-manager model whether a tl_done claim is genuinely complete.

    Returns {"agree": bool, "reason": str}. Defaults to disagree on any parse/LLM
    failure so a human is asked rather than silently trusting the worker.
    """
    import json5

    g.conversation_id = conversation_id
    agent = Assistant(llm=qwen_summary_cfg(), system_message=REVIEW_SYSTEM_PROMPT)
    prompt = (
        f"TASK CLAIMED DONE:\n{task_title}\n\n"
        f"RECENT ACTIVITY (assistant text + tool calls/results this turn):\n{evidence}\n\n"
        "Is this task genuinely complete? Reply with the JSON object only."
    )
    try:
        verdict_text = _last_text(_drain(agent, [{"role": "user", "content": prompt}]))
        parsed = json5.loads(
            verdict_text[verdict_text.find("{") : verdict_text.rfind("}") + 1]
        )
        return {
            "agree": bool(parsed.get("agree")),
            "reason": str(parsed.get("reason", "")),
        }
    except Exception as review_err:
        return {"agree": False, "reason": f"reviewer unavailable ({review_err})"}


# conversation_id → list of task titles the user manually added/edited at
# TaskList close, awaiting decomposition. Ephemeral (conversation-scoped, only
# relevant for the immediately following taskmgr run). Populated by the snapshot
# endpoint, drained by run_taskmgr.
_pending_user_tasks: dict[str, list[str]] = {}


def queue_user_tasks(conversation_id: str, titles: list[str]) -> None:
    """Mark user-added/edited tasks for decomposition on the next taskmgr run."""
    if not conversation_id or not titles:
        return
    bucket = _pending_user_tasks.setdefault(conversation_id, [])
    for title in titles:
        cleaned = (title or "").strip()
        if cleaned and cleaned not in bucket:
            bucket.append(cleaned)


def _drain_user_tasks(conversation_id: str) -> list[str]:
    return _pending_user_tasks.pop(conversation_id, [])


_TG_SYNC_SCHEMA = {
    "type": "function",
    "function": {
        "name": "tg_sync",
        "description": (
            "Sync the conversation task list. Pass only NEW tasks or tasks with edits. "
            "Omitted tasks are left untouched."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "action": {"type": "string"},
                            "expected_output": {"type": "string"},
                            "depends_on": {"type": "string"},
                        },
                        "required": ["title"],
                    },
                }
            },
            "required": ["tasks"],
        },
    },
}


def run_taskmgr(conversation_id: str, user_message: str, existing_tasks: list) -> list:
    """Build/refresh the task list for `conversation_id` from `user_message`.

    Makes a single LLM call, parses the tg_sync tool args, and calls the tool
    directly — no tool_result is ever sent back to the model, making looping
    structurally impossible.
    """
    from tools.taskgraph import TaskSyncTool

    g.conversation_id = conversation_id

    existing_block = (
        "\n".join(
            f"- id={t['id']} [{t['status']}] {t['title']}" for t in existing_tasks
        )
        or "(empty)"
    )

    user_added = _drain_user_tasks(conversation_id)
    user_added_block = ""
    if user_added:
        bullets = "\n".join(f"- {title}" for title in user_added)
        user_added_block = (
            "USER MANUALLY ADDED THESE TASKS (decompose each into worker subtasks, "
            "exactly as if the user had asked for it in chat — keep the original task "
            "and add its subtasks, using depends_on for ordering where it helps):\n"
            + bullets
            + "\n\n"
        )

    prompt = (
        f"EXISTING TASK LIST:\n{existing_block}\n\n"
        + user_added_block
        + (f"NEW USER MESSAGE:\n{user_message}\n\n" if user_message else "")
        + "Update the task list and call tg_sync once."
    )

    client = OpenAI(base_url=SUMMARIZE_SERVER_URL + "/v1", api_key="EMPTY")
    response = client.chat.completions.create(
        model=SUMMARIZE_MODEL,
        messages=[
            {"role": "system", "content": TASKMGR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        tools=[_TG_SYNC_SCHEMA],
        tool_choice="required",
    )

    msg = response.choices[0].message
    tool_calls = msg.tool_calls or []
    if tool_calls:
        TaskSyncTool().call(tool_calls[0].function.arguments)

    return [msg.model_dump()]
