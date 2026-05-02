"""Per-conversation task list tools (tl_ref, tl_add, tl_done)."""

import json5
from flask import g
from qwen_agent.tools.base import BaseTool, register_tool

from auth.conversation_tasks import ConversationTask
from auth.db import SessionLocal
from tools._output import tool_result


def _ordered_tasks_for_current_conv():
  """Return (db, tasks) for the current conversation, ordered by created_at."""
  conversation_id = g.get('conversation_id', '')
  db = SessionLocal()
  return db, (
    db.query(ConversationTask)
    .filter_by(conversation_id=conversation_id)
    .order_by(ConversationTask.created_at.asc())
    .all()
  )


def _task_dto(idx: int, task) -> dict:
  return {
    "number": idx,
    "id": task.id,
    "title": task.title,
    "status": task.status,
  }


@register_tool('tl_ref')
class TaskListRefTool(BaseTool):
  description = "Reference the current task list. Returns each task's id, 1-based number, title, and status. Call only when you need to look up task ids or inspect current state."
  parameters = {'type': 'object', 'properties': {}, 'required': []}

  def call(self, params: str, **kwargs) -> dict:
    db, ordered = _ordered_tasks_for_current_conv()
    try:
      return tool_result(data={
        "tasks": [_task_dto(i, t) for i, t in enumerate(ordered, 1)],
      })
    finally:
      db.close()


@register_tool('tl_add')
class TaskListAddTool(BaseTool):
  description = "Add a task to the current conversation's task list. Pass `between: [id_a, id_b]` to insert between two existing tasks; otherwise the task is appended."
  parameters = {
    'type': 'object',
    'properties': {
      'title': {'type': 'string', 'description': 'Task title.'},
      'between': {
        'type': 'array',
        'items': {'type': 'string'},
        'description': 'Optional 2-element list of task ids [before_id, after_id]. New task is inserted between them.',
      },
      'depends_on': {'type': 'string', 'description': 'Optional id of another task this one depends on.'},
    },
    'required': ['title'],
  }

  def call(self, params: str, **kwargs) -> dict:
    try:
      p = json5.loads(params)
    except Exception as e:
      return tool_result(error=f"Malformed JSON input: {e}")
    title = (p.get('title') or '').strip()
    if not title:
      return tool_result(error="'title' is required")
    conversation_id = g.get('conversation_id', '')
    if not conversation_id:
      return tool_result(error="No active conversation")

    between = p.get('between')
    depends_on = p.get('depends_on')

    db, ordered = _ordered_tasks_for_current_conv()
    try:
      by_id = {t.id: t for t in ordered}
      created_at = None
      if between is not None:
        if not (isinstance(between, list) and len(between) == 2):
          return tool_result(error="'between' must be a 2-element list of task ids")
        before_id, after_id = between
        before = by_id.get(before_id)
        after = by_id.get(after_id)
        if not before or not after:
          return tool_result(error="One or both ids in 'between' were not found in this conversation")
        if before.created_at >= after.created_at:
          return tool_result(error="'between' ids must be in current list order: [before_id, after_id]")
        delta = (after.created_at - before.created_at) / 2
        created_at = before.created_at + delta

      kwargs_ = {
        'conversation_id': conversation_id,
        'title': title,
        'depends_on': depends_on,
      }
      if created_at is not None:
        kwargs_['created_at'] = created_at
      task = ConversationTask(**kwargs_)
      db.add(task)
      db.commit()
      return tool_result(data={
        "id": task.id,
        "title": task.title,
        "status": task.status,
      })
    finally:
      db.close()


@register_tool('tl_done')
class TaskListDoneTool(BaseTool):
  description = "Mark a task as done by its id (as returned from tl_add or tl_ref)."
  parameters = {
    'type': 'object',
    'properties': {
      'id': {'type': 'string', 'description': 'Task id.'},
    },
    'required': ['id'],
  }

  def call(self, params: str, **kwargs) -> dict:
    try:
      p = json5.loads(params)
    except Exception as e:
      return tool_result(error=f"Malformed JSON input: {e}")
    task_id = (p.get('id') or '').strip()
    if not task_id:
      return tool_result(error="'id' is required")
    conversation_id = g.get('conversation_id', '')
    db = SessionLocal()
    try:
      task = (
        db.query(ConversationTask)
        .filter_by(id=task_id, conversation_id=conversation_id)
        .first()
      )
      if not task:
        return tool_result(error=f"Task {task_id!r} not found in this conversation")
      task.status = 'done'
      db.commit()
      return tool_result(data={"id": task.id, "title": task.title, "status": task.status})
    finally:
      db.close()
