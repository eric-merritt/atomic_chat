#!/usr/bin/env python3
"""Build a Microsoft Store-compliant MSIX bundle for the Atomic Chat agent.

This script is meant to run on Windows with the Windows 10/11 SDK installed
(it shells out to `makeappx.exe`). On non-Windows hosts it stages the package
directory and writes a .pkg.json manifest, leaving the final pack step for
a Windows runner (e.g. GitHub Actions windows-latest).

Layout produced under dist/windows/AtomicChatAgent/:
  AppxManifest.xml
  atomic-chat-agent.exe
  Assets/
    StoreLogo.png         (300x300)
    Square44x44Logo.png   (44x44)
    Square71x71Logo.png   (71x71)
    Square150x150Logo.png (150x150)
    SplashScreen.png      (1440x2160)

Output: dist/windows/AtomicChatAgent-<version>.msix

Run:
  python installer/build_msix.py            # uses default version 0.2.0
  python installer/build_msix.py 0.3.1      # override version
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INSTALLER_DIR = ROOT_DIR / "installer"
ASSETS_SRC_DIR = INSTALLER_DIR / "assets"
DIST_DIR = ROOT_DIR / "dist" / "windows"
PKG_STAGE_DIR = DIST_DIR / "AtomicChatAgent"
MANIFEST_SRC = INSTALLER_DIR / "AppxManifest.xml"

# (filename, source_logo, expected_size). The installer ships pre-rendered
# 150/300/71 logos; the rest are generated via Pillow at build time.
ASSET_TARGETS: list[tuple[str, str, tuple[int, int]]] = [
  ("StoreLogo.png",         "logo_300x300.png", (300, 300)),
  ("Square44x44Logo.png",   "logo_71x71.png",   (44, 44)),
  ("Square71x71Logo.png",   "logo_71x71.png",   (71, 71)),
  ("Square150x150Logo.png", "logo_150x150.png", (150, 150)),
  ("SplashScreen.png",      "poster_1440x2160.png", (1440, 2160)),
]


def _info(msg: str) -> None:
  print(f"[build_msix] {msg}", flush=True)


def _fail(msg: str) -> None:
  print(f"[build_msix] ERROR: {msg}", file=sys.stderr, flush=True)
  sys.exit(1)


def _resolve_version(arg_value: str | None) -> str:
  """Pull version from CLI arg, pyproject.toml, or fall back to 0.0.0."""
  if arg_value:
    return arg_value
  pyproject = ROOT_DIR / "pyproject.toml"
  if pyproject.exists():
    for line in pyproject.read_text(encoding="utf-8").splitlines():
      stripped = line.strip()
      if stripped.startswith("version"):
        return stripped.split("=", 1)[1].strip().strip('"').strip("'")
  return "0.0.0"


def _stamp_manifest_version(target: Path, version: str) -> None:
  """Rewrite the Identity Version attribute. MSIX requires four-part versions.

  Uses regex on the raw text rather than ElementTree so the original
  namespace prefixes (uap, uap10, rescap) survive — ET would rename them
  to ns1/ns2/etc. and break IgnorableNamespaces, failing Store certification.
  """
  parts = version.split(".")
  while len(parts) < 4:
    parts.append("0")
  four_part = ".".join(parts[:4])
  manifest_text = target.read_text(encoding="utf-8")
  updated_text, replacement_count = re.subn(
    r'(<Identity[^>]*\bVersion=")[^"]*(")',
    rf'\g<1>{four_part}\g<2>',
    manifest_text,
    count=1,
  )
  if replacement_count == 0:
    _fail(f"manifest at {target} is missing an Identity/Version attribute")
  target.write_text(updated_text, encoding="utf-8")
  _info(f"manifest version set to {four_part}")


def _resize_or_copy(source: Path, target: Path, size: tuple[int, int]) -> None:
  """Resize source PNG to target size if Pillow is available; else copy as-is."""
  try:
    from PIL import Image  # type: ignore
  except ImportError:
    _info("Pillow not installed — copying source asset without resize. "
          "Install pillow for proper Store-compliant scaling.")
    shutil.copy2(source, target)
    return
  with Image.open(source) as img:
    resized = img.convert("RGBA").resize(size, Image.LANCZOS)
    resized.save(target, format="PNG")


def _stage_assets(stage_assets_dir: Path) -> None:
  """Populate the stage Assets/ folder with all manifest-referenced PNGs."""
  stage_assets_dir.mkdir(parents=True, exist_ok=True)
  for filename, source_name, size in ASSET_TARGETS:
    source_path = ASSETS_SRC_DIR / source_name
    if not source_path.exists():
      _fail(f"missing source asset {source_path}; cannot build Store-compliant package")
    _resize_or_copy(source_path, stage_assets_dir / filename, size)
  _info(f"staged {len(ASSET_TARGETS)} visual assets")


def _build_agent_exe() -> Path:
  """Run PyInstaller to produce atomic-chat-agent.exe.

  On non-Windows hosts the .exe cannot be built — return the expected path
  and let the caller decide whether to abort.
  """
  expected = DIST_DIR / "atomic-chat-agent.exe"
  if platform.system() != "Windows":
    _info(f"non-Windows host — skipping PyInstaller; expected exe at {expected} "
          "(will need to run pack step on Windows)")
    return expected
  agent_entry = ROOT_DIR / "atomic_client" / "agent.py"
  cmd = [
    sys.executable, "-m", "PyInstaller", "--onefile", "--name", "atomic-chat-agent",
    "--distpath", str(DIST_DIR), "--workpath", str(DIST_DIR / "_build"),
    "--specpath", str(DIST_DIR / "_spec"), str(agent_entry),
  ]
  _info("running PyInstaller…")
  result = subprocess.run(cmd, cwd=ROOT_DIR)
  if result.returncode != 0:
    _fail("PyInstaller failed; see output above")
  return expected


def _stage_package(version: str) -> Path:
  """Lay out the staging directory exactly as makeappx expects."""
  if PKG_STAGE_DIR.exists():
    shutil.rmtree(PKG_STAGE_DIR)
  PKG_STAGE_DIR.mkdir(parents=True)
  staged_manifest = PKG_STAGE_DIR / "AppxManifest.xml"
  shutil.copy2(MANIFEST_SRC, staged_manifest)
  _stamp_manifest_version(staged_manifest, version)
  _stage_assets(PKG_STAGE_DIR / "Assets")
  built_exe = _build_agent_exe()
  if built_exe.exists():
    shutil.copy2(built_exe, PKG_STAGE_DIR / "atomic-chat-agent.exe")
    _info("copied agent exe into stage")
  else:
    _info("agent exe not present — packaging will fail until exe is built")
  return PKG_STAGE_DIR


def _find_makeappx() -> str | None:
  for candidate in (
    "makeappx.exe", "makeappx",
    r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.22621.0\x64\makeappx.exe",
    r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\makeappx.exe",
  ):
    found = shutil.which(candidate)
    if found:
      return found
    if Path(candidate).exists():
      return candidate
  return None


def _pack(stage_dir: Path, output_msix: Path) -> bool:
  makeappx_path = _find_makeappx()
  if not makeappx_path:
    _info("makeappx not found — wrote stage directory only. "
          "Run on a Windows host with Win 10/11 SDK to produce the .msix.")
    return False
  cmd = [makeappx_path, "pack", "/d", str(stage_dir), "/p", str(output_msix), "/o"]
  _info(f"packing → {output_msix}")
  result = subprocess.run(cmd)
  if result.returncode != 0:
    _fail("makeappx failed")
  return True


def main() -> int:
  version = _resolve_version(sys.argv[1] if len(sys.argv) > 1 else None)
  DIST_DIR.mkdir(parents=True, exist_ok=True)
  stage_dir = _stage_package(version)
  output_msix = DIST_DIR / f"AtomicChatAgent-{version}.msix"
  packed = _pack(stage_dir, output_msix)
  manifest_summary = {
    "version": version,
    "stage_dir": str(stage_dir),
    "output_msix": str(output_msix) if packed else None,
    "host_can_pack": packed,
    "next_steps": (
      "Sign with signtool.exe / Partner Center cert, then upload via Partner Center"
      if packed else
      "Re-run on a Windows host with the Win 10/11 SDK to produce the .msix"
    ),
  }
  (DIST_DIR / "AtomicChatAgent.pkg.json").write_text(
    json.dumps(manifest_summary, indent=2), encoding="utf-8"
  )
  _info("done")
  return 0


if __name__ == "__main__":
  sys.exit(main())
