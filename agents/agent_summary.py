"""Context-compression agent.

Wraps the summary-model request that routes/chat.py used to issue inline via the
requests library. The prompt that was built inside summarize_context() now lives
here as this agent's own prompt.
"""

import requests

from config import LLAMA_SERVER_URL, SUMMARIZE_MODEL

SUMMARY_SYSTEM_PROMPT = (
    "You compress conversation history. Each of the last 3 turns should be summarized in 2-3 sentences."
    " The 4th and 5th most recent turns should be summarized in 1 sentence. Older turns are purged. "
    "Preserve open tasks, the most recent completed task, and any directions from the user that give "
    "user intent, and any facts the assistant will need to continue the work. "
    "Include what the user was trying to accomplish and what state things were left in. "
    "Output only the summary."
)


# Incremental fold: takes the PREVIOUS running memory + only the NEW messages
# and returns updated memory. State-extraction, not prose — keeps load-bearing
# facts (goals, paths, ids, open bugs, decisions), drops chatter. Tuned for the
# small summary model.
FOLD_SYSTEM_PROMPT = (
    "You maintain a running memory of a coding session so a fresh agent can continue "
    "without re-reading the whole history. You get the PREVIOUS MEMORY and NEW EXCHANGES. "
    "Return the UPDATED MEMORY.\n\n"
    "KEEP (load-bearing for the next turn):\n"
    "- The user's goal and any stated constraints or preferences.\n"
    "- Decisions made, and reasoning that still binds future work.\n"
    "- Files/paths/functions/IDs touched and what changed in each.\n"
    "- Unresolved bugs, failures, TODOs and their current state.\n"
    "- Anything the user explicitly asked to remember.\n\n"
    "DROP (noise the next turn does not need):\n"
    "- Greetings, acknowledgements, restated questions, thinking-out-loud.\n"
    "- Tool output already acted on (keep the conclusion, not the dump).\n"
    "- Superseded facts — if a value changed, keep only the latest.\n\n"
    "RULES: Be terse, bullet points, no preamble. Never invent state. If unsure whether "
    "something matters, keep the fact and drop the words. Output ONLY the updated memory."
)


def fold_summary(prev_summary: str, new_exchanges: str, timeout: int = 60) -> str:
    """Fold `new_exchanges` into `prev_summary`, returning the updated memory.

    Incremental — only the messages newer than the last compaction are passed,
    so the summary call stays small as the conversation grows.
    """
    user_block = (
        f"PREVIOUS MEMORY:\n{prev_summary or '(none)'}\n\n"
        f"NEW EXCHANGES:\n{new_exchanges}"
    )
    resp = requests.post(
        f"{LLAMA_SERVER_URL}/v1/chat/completions",
        json={
            "model": SUMMARIZE_MODEL,
            "messages": [
                {"role": "system", "content": FOLD_SYSTEM_PROMPT},
                {"role": "user", "content": user_block},
            ],
            "stream": False,
            "cache_prompt": False,
            "id_slot": 1,
        },
        timeout=timeout,
    )
    return resp.json()["choices"][0]["message"]["content"].strip()


def summarize(transcript: str, timeout: int = 60) -> str:
    """Return a compressed summary of `transcript` from the summary model."""
    resp = requests.post(
        f"{LLAMA_SERVER_URL}/v1/chat/completions",
        json={
            "model": SUMMARIZE_MODEL,
            "messages": [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
            "stream": False,
            "cache_prompt": False,
            "id_slot": 1,
        },
        timeout=timeout,
    )
    return resp.json()["choices"][0]["message"]["content"].strip()
