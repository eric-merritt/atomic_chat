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

from flask import g
from qwen_agent.agents import Assistant

from config import qwen_summary_cfg

TASKMGR_SYSTEM_PROMPT = """
You are responsible for maintaining an atomic list of tasks. From the user message,
you decide all of the steps it takes to complete the request. Each message after the 1st
will include a task list. You must identify any NEW tasks. Do NOT duplicate. Even if no new
tasks are present in user message, you MUST call tg_sync w/ "tasks": [] or the flow will
break.

HOW TO WORK AS SWITCH:

## CASE: USER MSG

  - Read the latest user message + existing task list.
  - If user message includes new task, follow these instructions:
      1. Deconstruct request into specific, atomic subtasks.
      2. A task is "atomic" if it requires no further subdivision, can be verified objectively, and can be executed independently.
      3. Organize them in a logical, sequential order.
      4. For each task, clearly state the required action, the expected output, and any dependencies.
  - Call tg_sync ONCE. Include ONLY NEW tasks OR tasks with edits.
  - To update an existing task, pass its exact current title (or id)
  - depends_on = input for TASKn depends on output from TASKn-1
  - Titles MUST BE SHORT ex: "Read config.py" or "Run test suite"
  - action = specific action to perform (e.g. "Read config.py and extract DB_URL")
  - expected_output = what correct completion produces (e.g. "DB_URL string value")
  - OUTPUT:
      <tool_call>
      {
      "name": "tg_sync",
      "arguments": {
        "tasks":
          [
            {
              "title": "...",
              "action": "...",
              "expected_output": "...",
              "depends_on": "..."
            },
            {
              "title": "...",
              "action": "...",
              "expected_output": "..."
            }
          ]
        }
      }
      </tool_call>

## CASE: TOOL_RESULT
  - OUTPUT: "OK" # This passes loop to main agent

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


def run_taskmgr(conversation_id: str, user_message: str, existing_tasks: list) -> list:
    """Build/refresh the task list for `conversation_id` from `user_message`.

    existing_tasks: list of {"id","title","status"} dicts (current list).
    The summary model sees ONLY the current task list plus the new user message —
    no conversation history tail — to keep its input small and stateless per turn.
    Returns the agent's final message list (for logging); the real effect is the
    tg_sync write to ConversationTask.
    """
    g.conversation_id = conversation_id

    agent = Assistant(
        llm=qwen_summary_cfg(),
        function_list=["tg_sync"],
        system_message=TASKMGR_SYSTEM_PROMPT,
    )

    existing_block = (
        "\n".join(
            f"- id={t['id']} [{t['status']}] {t['title']}" for t in existing_tasks
        )
        or "(empty)"
    )

    # Tasks the user typed straight into the TaskList (at close). Treat each like a
    # request the user made in chat: break it into subtasks the worker can execute.
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

    return _drain(agent, [{"role": "user", "content": prompt}])
