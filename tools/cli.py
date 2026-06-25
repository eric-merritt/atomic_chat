"""Bash tool: launch a shell command detached (backgrounded + disowned), return
immediately with a PID and output-file path. The command keeps running after the
tool returns; the model reads its output from the file on a later call."""

import os
import sys

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
  sys.path.insert(0, ROOT)


import shlex
import tempfile
import subprocess

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result
from tools._access import check_fs_access

_OUTPUT_DIR = os.path.join(tempfile.gettempdir(), 'atomic_chat_bash')


def _ensure_output_dir() -> None:
  os.makedirs(_OUTPUT_DIR, exist_ok=True)


def _output_path(pid: int) -> str:
  return os.path.join(_OUTPUT_DIR, f'bash_{ pid }.log')


def _launch_detached(command: str) -> dict:
  """Start the command fully detached, stdout+stderr → a log file. Returns the
  PID and output path. The process outlives this call (own session, disowned)."""
  _ensure_output_dir()
  # A placeholder path is needed before the PID exists, so write to a temp file
  # first, then rename to the PID-named path once the child is running.
  handle, staging_path = tempfile.mkstemp(dir=_OUTPUT_DIR, suffix='.log')
  log_file = os.fdopen(handle, 'wb')
  child = subprocess.Popen(
    command,
    shell=True,
    stdout=log_file,
    stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,
    start_new_session=True,  # detach from our process group — disown
  )
  log_file.close()
  final_path = _output_path(child.pid)
  os.replace(staging_path, final_path)
  return { 'pid': child.pid, 'output_file': final_path }


def _read_output(output_file: str) -> dict:
  """Return the current contents of a backgrounded command's output file plus
  whether the process is still running."""
  if not os.path.isfile(output_file):
    return tool_result(error=f'No such output file: { output_file }')
  with open(output_file, 'r', errors='replace') as handle:
    contents = handle.read()
  pid = _pid_from_path(output_file)
  return tool_result(data={
    'output_file': output_file,
    'running': _is_running(pid),
    'output': contents or None,
  })


def _pid_from_path(output_file: str) -> int | None:
  base = os.path.basename(output_file)
  if base.startswith('bash_') and base.endswith('.log'):
    return int(base[len('bash_'):-len('.log')])
  return None


def _is_running(pid: int | None) -> bool:
  """True only if the PID is a live, non-zombie process. A disowned child we
  never wait() on becomes a zombie when it finishes, so os.kill(pid, 0) alone
  would falsely report it as running — read its state from /proc instead."""
  if pid is None:
    return False
  try:
    with open(f'/proc/{ pid }/stat', 'r') as handle:
      state = handle.read().rsplit(')', 1)[1].split()[0]
    return state != 'Z'
  except (FileNotFoundError, ProcessLookupError):
    return False


@register_tool('cli_bash')
class BashTool(BaseTool):
  description = (
    'Launch a shell command in the background (detached). Returns immediately '
    'with a pid and output_file; the command keeps running after this call. '
    'To read what it has produced so far, call again with output_file set.'
  )
  parameters = {
    'type': 'object',
    'properties': {
      'command': {
        'type': 'string',
        'description': 'The shell command to launch in the background.',
      },
      'description': {
        'type': 'string',
        'description': 'Plain-English explanation of what this command does and why.',
      },
      'output_file': {
        'type': 'string',
        'description': 'Read mode: path returned by a prior launch. When set, '
                       'returns that command\'s current output instead of launching.',
      },
    },
    'required': [],
  }

  def call(self, params: str, **kwargs) -> dict:
    access = check_fs_access(self.name, params)
    if access is not None:
      return access
    parsed = json5.loads(params)
    output_file = (parsed.get('output_file') or '').strip()
    if output_file:
      return _read_output(output_file)

    command = (parsed.get('command') or '').strip()
    if not command:
      return tool_result(error='command is required (or output_file to read)')
    launched = _launch_detached(command)
    return tool_result(data=launched)
