"""Bash tool: execute shell commands with user confirmation (web UI preferred, terminal fallback)."""

import subprocess
import threading

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result
from tools._access import check_fs_access

# conv_id → {"event": threading.Event, "approved": bool | None}
_pending_confirms: dict[str, dict] = {}
_pending_lock = threading.Lock()

# Thread-local set by the pump thread before assistant.run() so tools can
# reach the web-UI confirmation queue without depending on flask.g.
_ctx = threading.local()


@register_tool('bash')
class BashTool(BaseTool):
    description = (
        'Execute a shell command. You must provide a plain-English description '
        'of what the command does. The user will be prompted to confirm before it runs.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'command': {
                'type': 'string',
                'description': 'The shell command to execute.',
            },
            'description': {
                'type': 'string',
                'description': 'Plain-English explanation of what this command does and why.',
            },
        },
        'required': ['command', 'description'],
    }

    def call(self, params: str, **kwargs) -> dict:
        r = check_fs_access(self.name, params)
        if r is not None:
            return r
        p = json5.loads(params)
        command = (p.get('command') or '').strip()
        description = (p.get('description') or '').strip()

        if not command:
            return tool_result(error='command is required')
        if not description:
            return tool_result(error='description is required')

        approved = self._confirm(command, description)
        if not approved:
            return tool_result(error='User declined.')

        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
        )
        return tool_result(data={
            'stdout': result.stdout or None,
            'stderr': result.stderr or None,
            'returncode': result.returncode,
        })

    def _confirm(self, command: str, description: str) -> bool:
        conv_id: str | None = getattr(_ctx, 'conversation_id', None)
        interrupt_q = getattr(_ctx, 'bash_interrupt_q', None)

        if conv_id and interrupt_q is not None:
            event = threading.Event()
            with _pending_lock:
                _pending_confirms[conv_id] = {'event': event, 'approved': None}

            interrupt_q.put({'command': command, 'description': description})
            event_set = event.wait(timeout=120)

            with _pending_lock:
                entry = _pending_confirms.pop(conv_id, {})

            return event_set and bool(entry.get('approved', False))

        # Terminal fallback when no web context is available
        print(f'\n[bash] {description}', flush=True)
        print(f'  $ {command}', flush=True)
        return input('Run? [y/N] ').strip().lower() == 'y'
