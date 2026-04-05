"""Task Extractor — 1.7B worker #1.

Reads the user's message and recent conversation history, extracts new
tasks, and writes them to conversation_tasks. Signals whether new tasks
were found so the Tool Curator can short-circuit.
"""

import json
import logging
import os
import re

from qwen_agent.llm import get_chat_model

from config import TASK_EXTRACTOR_MODEL

_LOG_DIR = os.path.join(os.path.dirname(__file__), "training_data", "logs")
_EXTRACTOR_LOG = os.path.join(_LOG_DIR, "task_extractor.jsonl")

logger = logging.getLogger(__name__)

_SYSTEM_MSG = (
    "You are a task extraction agent. Read the user's message and conversation "
    "context, then extract new tasks. A task is a concrete action the agent must "
    "perform. Follow-ups that modify existing tasks are NOT new tasks. Return ONLY "
    "a JSON array of short task titles, or [] if none."
)


def _log_exchange(prompt: str, response: str):
    """Append a training-format JSONL line for this exchange."""
    try:
        os.makedirs(_LOG_DIR, exist_ok=True)
        entry = {
            "messages": [
                {"role": "system", "content": _SYSTEM_MSG},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": response},
            ]
        }
        with open(_EXTRACTOR_LOG, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug("Failed to log extractor exchange: %s", e)


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

    return f"""You are a task extraction agent. Read the user's message and decide if it contains NEW tasks not already in the list.

EXISTING TASKS (DO NOT repeat, rephrase, or re-extract these):
{task_lines}

Recent conversation:
{history_lines}

User message: "{user_message}"

Rules:
- ONLY extract tasks that are genuinely NEW and not already covered by existing tasks above.
- If the user says "do the tasks", "perform the task list", "execute", "go ahead", etc. — these are NOT new tasks. Return [].
- Follow-ups like "try again", "fix that", "now do X with that" are NOT new tasks. Return [].
- References to existing tasks are NOT new tasks. Return [].
- If the message contains truly new tasks not in the list above, return a JSON array of task titles.
- PRESERVE ALL DETAILS in task titles: URLs, product names, prices, filters, selectors, file paths, quantities — everything the agent needs to act. Do NOT summarize or shorten.

Return ONLY a JSON array. Examples:
- New tasks: ["Search eBay for Sony WH-1000XM5 under $200 used condition", "Import prices from https://supplier.com/catalog into inventory ledger"]
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
        from config import qwen_curation_llm_cfg
        llm = get_chat_model(qwen_curation_llm_cfg(TASK_EXTRACTOR_MODEL))
        messages = [
            {"role": "system", "content": _SYSTEM_MSG},
            {"role": "user", "content": prompt},
        ]
        *_, final = llm.chat(messages=messages)
        raw = final[-1].get("content", "")
        new_titles = _parse_extractor_response(raw)
        _log_exchange(prompt, raw)
    except Exception as e:
        logger.warning("Task Extractor failed (%s), assuming no new tasks", e)
        return False

    if not new_titles:
        logger.info("Task Extractor: no new tasks")
        return False

    # Deduplicate against existing tasks (exact + overlap)
    _STOPWORDS = {"the", "a", "an", "to", "from", "for", "of", "in", "on", "and", "or", "with"}
    existing_lower = [t["title"].lower().strip() for t in existing_tasks]

    def _normalize_words(s: str) -> set[str]:
        return {w for w in re.sub(r"[^\w\s]", "", s.lower()).split() if w not in _STOPWORDS}

    def _extract_urls(s: str) -> set[str]:
        return set(re.findall(r'[\w.-]+\.(?:com|org|net|io|dev|co)\b[/\w.-]*', s.lower()))

    def _is_duplicate(candidate: str) -> bool:
        c = candidate.lower().strip()
        c_words = _normalize_words(c)
        c_urls = _extract_urls(c)
        for ex in existing_lower:
            if c == ex:
                return True
            # Catch rephrased duplicates: if one contains the other
            if len(c) > 8 and len(ex) > 8 and (c in ex or ex in c):
                return True
            # URL overlap: same domain/URL referenced means same task
            if c_urls and c_urls & _extract_urls(ex):
                return True
            # Word overlap: >50% shared meaningful words means duplicate
            ex_words = _normalize_words(ex)
            if c_words and ex_words:
                overlap = len(c_words & ex_words) / min(len(c_words), len(ex_words))
                if overlap >= 0.5:
                    return True
        return False

    new_titles = [t for t in new_titles if not _is_duplicate(t)]

    if not new_titles:
        logger.info("Task Extractor: all extracted tasks already exist, skipping")
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
