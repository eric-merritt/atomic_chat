"""Tool registry — auto-discovered from tools/ package.

All tool modules use qwen-agent's @register_tool decorator.
Importing each module triggers registration in TOOL_REGISTRY.
ALL_TOOLS is built from the registry after all modules are loaded.
"""

import importlib
import pkgutil
import sys

from qwen_agent.tools.base import TOOL_REGISTRY

import tools as _pkg

_BUILTIN_TOOLS = set(TOOL_REGISTRY.keys())

for _mod in pkgutil.iter_modules(_pkg.__path__):
  if not _mod.name.startswith('_'):
    try:
      importlib.import_module(f"tools.{_mod.name}")
    except Exception as _exc:
      print(f"WARN: failed to load tools.{_mod.name}: {_exc}", file=sys.stderr)

ALL_TOOLS = [cls for name, cls in TOOL_REGISTRY.items() if name not in _BUILTIN_TOOLS]
