"""Task Extractor — 1.7B worker #1.

Reads the user's message and recent conversation history, extracts new
tasks, and writes them to conversation_tasks. Signals whether new tasks
were found so the Tool Curator can short-circuit.
"""

import json
import logging
import re

from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage

from config import TASK_EXTRACTOR_MODEL

logger = logging.getLogger(__name__)


def _build_extractor_prompt(
    user_message: str,
    existing_tasks: list[dict],
    recent_messages: list[dict],
) -> str:
    """Build the prompt for the Task Extractor model."""
    if existing_tasks:
        task_lines = "\n".join(
            f"- [{t['status']}] {t['title']}" for t in existing_tasks
        )
    else:
        task_lines = "(none)"

    if recent_messages:
        history_lines = "\n".join(
            f"{m['role']}: {m['content'][:200]}" for m in recent_messages[-5:]
        )
    else:
        history_lines = "(none)"

    return f"""You are a task extraction agent. Read the user's message and conversation
context, then decide if there are new tasks.

Current tasks:
{task_lines}

Recent conversation:
{history_lines}

User message: "{user_message}"

Rules:
- A "task" is a concrete action the user wants the agent to perform.
- Follow-ups like "try again", "format that differently", "now do X with that"
  are NOT new tasks — they modify existing tasks.
- If the message contains new tasks, return a JSON array of short task titles.
- If there are no new tasks, return an empty array.

Return ONLY a JSON array. Examples:
- New tasks: ["Scrape supplier pricing from URL", "Import prices into ledger"]
- No new tasks: []"""


def _parse_extractor_response(raw: str) -> list[str]:
    """Parse the extractor's response into a list of task title strings.

    Returns an empty list if the response is malformed.
    """
    # Strip <think>...</think> tags (qwen3 models)
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

    # Extract JSON array
    match = re.search(r"\[.*\]", cleaned, flags=re.DOTALL)
    if not match:
        return []

    try:
        parsed = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, list):
        return []

    return [item for item in parsed if isinstance(item, str) and item.strip()]


def extract_tasks(
    user_message: str,
    conversation_id: str,
    db,
) -> bool:
    """Run the Task Extractor and write new tasks to DB.

    Args:
        user_message: The user's current message.
        conversation_id: Active conversation ID.
        db: SQLAlchemy session.

    Returns:
        True if new tasks were extracted, False otherwise.
    """
    from auth.conversation_tasks import ConversationTask
    from auth.conversations import ConversationMessage

    # Load existing tasks for this conversation
    existing = db.query(ConversationTask).filter_by(
        conversation_id=conversation_id
    ).all()
    existing_tasks = [{"title": t.title, "status": t.status} for t in existing]

    # Load recent messages for context
    recent = (
        db.query(ConversationMessage)
        .filter_by(conversation_id=conversation_id)
        .order_by(ConversationMessage.created_at.desc())
        .limit(5)
        .all()
    )
    recent_messages = [
        {"role": m.role, "content": m.content}
        for m in reversed(recent)
    ]

    prompt = _build_extractor_prompt(user_message, existing_tasks, recent_messages)

    try:
        llm = ChatOllama(
            model=TASK_EXTRACTOR_MODEL,
            temperature=0,
            base_url="http://localhost:11434",
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        new_titles = _parse_extractor_response(response.content)
    except Exception as e:
        logger.warning("Task Extractor failed (%s), assuming no new tasks", e)
        return False

    if not new_titles:
        logger.info("Task Extractor: no new tasks")
        return False

    # Write new tasks to DB
    for title in new_titles:
        db.add(ConversationTask(
            conversation_id=conversation_id,
            title=title,
        ))
    db.commit()

    logger.info("Task Extractor: %d new tasks: %s", len(new_titles), new_titles)
    return True
