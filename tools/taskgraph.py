"""Task-sync tool for the task-manager agent.

The task-manager calls tg_sync once per run with the WHOLE task list. tg_sync
reconciles it against ConversationTask rows for the current conversation:

  - new title            → INSERT a pending task
  - existing task (matched by id or exact title) → kept; title updated if changed
  - omitted task         → left untouched (never deleted; status is the worker's
                           job via tl_done, so done/pending is preserved)

Each task may name a `depends_on` (an id or the exact title of another task in
the same list) to record ordering — the only relationship the flat task list UI
shows. No graph, no edges array.
"""

import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


import json5
from flask import g
from qwen_agent.tools.base import BaseTool, register_tool

from auth.conversation_tasks import ConversationTask
from auth.db import SessionLocal
from tools._output import tool_result


def _ordered_rows(db, conversation_id):
  return (
    db.query(ConversationTask)
    .filter_by(conversation_id=conversation_id)
    .order_by(ConversationTask.created_at.asc())
    .all()
  )


def _match(ref, by_id, by_title):
  """Resolve a task reference (id or exact title) to an existing row."""
  ref = (ref or "").strip()
  return by_id.get(ref) or by_title.get(ref)


@register_tool('tg_sync')
class TaskSyncTool(BaseTool):
  description = (
    "Sync the conversation task list. Pass the WHOLE list each call: new titles "
    "are added, existing tasks (matched by id or exact title) are kept and "
    "retitled if changed, omitted tasks are left untouched. Existing tasks are "
    "never deleted and their done/pending status is preserved."
  )
  parameters = {
    'type': 'object',
    'properties': {
      'tasks': {
        'type': 'array',
        'description': 'The full task list.',
        'items': {
          'type': 'object',
          'properties': {
            'title': {'type': 'string', 'description': 'Short task title.'},
            'action': {
              'type': 'string',
              'description': 'The specific action to perform for this task.',
            },
            'expected_output': {
              'type': 'string',
              'description': 'What a correct completion of this task produces.',
            },
            'depends_on': {
              'type': 'string',
              'description': 'Optional id or exact title of a task this one follows.',
            },
          },
          'required': ['title'],
        },
      },
    },
    'required': ['tasks'],
  }

  def call(self, params: str, **kwargs) -> dict:
    try:
      parsed = json5.loads(params)
    except Exception as parse_err:
      return tool_result(error=f"Malformed JSON input: {parse_err}")

    tasks = parsed.get('tasks') or []
    conversation_id = g.get('conversation_id', '')
    if not conversation_id:
      return tool_result(error="No active conversation")
    if not isinstance(tasks, list):
      return tool_result(error="'tasks' must be a list")

    db = SessionLocal()
    try:
      title_to_row = _upsert_tasks(db, conversation_id, tasks)
      _apply_dependencies(db, conversation_id, tasks, title_to_row)
      db.commit()
      return tool_result(data={
        "tasks": [
          {
            "id": row.id,
            "title": row.title,
            "action": row.action,
            "expected_output": row.expected_output,
            "status": row.status,
            "depends_on": row.depends_on,
          }
          for row in _ordered_rows(db, conversation_id)
        ],
      })
    finally:
      db.close()


def _upsert_tasks(db, conversation_id, tasks):
  """Insert/update a row per task. Returns {title: row} for dependency wiring."""
  existing = _ordered_rows(db, conversation_id)
  by_id = {row.id: row for row in existing}
  by_title = {(row.title or "").strip(): row for row in existing}
  title_to_row = {}
  for task in tasks:
    title = (task.get('title') or "").strip()
    if not title:
      continue
    row = _match(title, by_id, by_title)
    if row is None:
      row = ConversationTask(conversation_id=conversation_id, title=title)
      db.add(row)
      db.flush()  # populate row.id
      by_id[row.id] = row
      by_title[title] = row
    if task.get('action') is not None:
      row.action = task['action']
    if task.get('expected_output') is not None:
      row.expected_output = task['expected_output']
    title_to_row[title] = row
  return title_to_row


def _apply_dependencies(db, conversation_id, tasks, title_to_row):
  """Set each task's depends_on from its id/title reference."""
  by_id = {row.id: row for row in _ordered_rows(db, conversation_id)}
  for task in tasks:
    dep_ref = (task.get('depends_on') or "").strip()
    title = (task.get('title') or "").strip()
    if not dep_ref or not title:
      continue
    row = title_to_row.get(title)
    dep_row = _match(dep_ref, by_id, title_to_row)
    if row and dep_row and dep_row is not row:
      row.depends_on = dep_row.id
