"""Tool registry — auto-discovered from tools/ package.

All tool modules use qwen-agent's @register_tool decorator.
Importing each module triggers registration in TOOL_REGISTRY.
ALL_TOOLS is built from the registry after all modules are loaded.
"""

import importlib
import os
import pkgutil
import sys

from qwen_agent.tools.base import TOOL_REGISTRY

import tools as _pkg

_BUILTIN_TOOLS = set(TOOL_REGISTRY.keys())

# When a tool module is launched directly (python tools/filesystem.py), it runs
# as __main__ and registers its tools. Skip re-importing that same module under
# its package name here, or its @register_tool would fire twice and raise.
_main_file = getattr(sys.modules.get('__main__'), '__file__', '') or ''
_running_module = os.path.splitext(os.path.basename(_main_file))[0]

for _mod in pkgutil.iter_modules(_pkg.__path__):
  if not _mod.name.startswith('_') and _mod.name != _running_module:
    try:
      importlib.import_module(f"tools.{_mod.name}")
    except Exception as _exc:
      print(f"WARN: failed to load tools.{_mod.name}: {_exc}", file=sys.stderr)

ALL_TOOLS = [cls for name, cls in TOOL_REGISTRY.items() if name not in _BUILTIN_TOOLS]
