"""
Reverse-engineer ablation recipe from weight deltas.

For each decoder layer, loads output projection + down_proj from both models,
computes delta = W_ablated - W_original, and recovers:
  - which layers were modified (onset / last_layer)
  - the factor (from rank-1 SVD of delta)

Math: orthogonalize_weight applies W -= factor * outer(d, d@W)
so delta is rank-1. SVD recovers d and factor.
"""

import json
import sys
from pathlib import Path

import torch
from safetensors import safe_open

ORIG_PATH  = Path("~/models/Qwen/Qwen3.6-27B").expanduser()
ABLIT_PATH = Path("~/models/Qwen/Qwen3.6-27B-Abliterated/v0.1.0").expanduser()
INDEX_FILE = Path("~/layers.json").expanduser()

DELTA_THRESHOLD = 1e-2

# Output projections to check per layer (first match wins per layer type)
ATTN_PROJ_CANDIDATES = ["self_attn.o_proj", "linear_attn.out_proj"]
MLP_PROJ             = "mlp.down_proj"
KEY_PREFIX           = "model.language_model.layers"

def build_shard_map(model_path: Path) -> dict[str, str]:
  """key -> absolute shard path, from the model's own index or the global layers.json."""
  index = model_path / "model.safetensors.index.json"
  if index.exists():
    data = json.loads(index.read_text())
  else:
    data = json.loads(INDEX_FILE.read_text())
  return { k: str(model_path / v) for k, v in data["weight_map"].items() }

def load_tensor(shard_map: dict, key: str) -> torch.Tensor | None:
  shard = shard_map.get(key)
  if shard is None:
    return None
  with safe_open(shard, framework="pt") as f:
    return f.get_tensor(key).to(torch.float32)

def recover_factor(delta: torch.Tensor, W_orig: torch.Tensor) -> float:
  U, S, _ = torch.svd_lowrank(delta, q=1)
  direction = U[:, 0]
  denom = float((direction @ W_orig).norm())
  return float(S[0]) / denom if denom > 1e-8 else 0.0

def count_layers(shard_map: dict) -> int:
  indices = set()
  for key in shard_map:
    if key.startswith(KEY_PREFIX + ".") and key.endswith(".mlp.down_proj.weight"):
      part = key[len(KEY_PREFIX) + 1:].split(".")[0]
      if part.isdigit():
        indices.add(int(part))
  return max(indices) + 1 if indices else 0

print(f"Loading shard maps...")
orig_map  = build_shard_map(ORIG_PATH)
ablit_map = build_shard_map(ABLIT_PATH)

n_layers = count_layers(orig_map)
print(f"Detected {n_layers} decoder layers\n")

modified_layers = []

for layer_idx in range(n_layers):
  prefix = f"{KEY_PREFIX}.{layer_idx}"

  # Find which attention proj key exists for this layer
  attn_key = next(
    (f"{prefix}.{c}.weight" for c in ATTN_PROJ_CANDIDATES if f"{prefix}.{c}.weight" in orig_map),
    None
  )
  mlp_key = f"{prefix}.{MLP_PROJ}.weight"

  for key in filter(None, [attn_key, mlp_key]):
    proj_label = key.split(f"{layer_idx}.")[1].replace(".weight", "")
    W_orig  = load_tensor(orig_map,  key)
    W_ablit = load_tensor(ablit_map, key)

    if W_orig is None or W_ablit is None:
      print(f"  layer {layer_idx:3d} {proj_label:25s}  NOT FOUND", flush=True)
      continue

    delta = W_ablit - W_orig
    l2 = float(delta.norm())

    if l2 < DELTA_THRESHOLD:
      print(f"  layer {layer_idx:3d} {proj_label:25s}  unchanged  l2={l2:.2e}", flush=True)
    else:
      factor = recover_factor(delta, W_orig)
      modified_layers.append({ "layer": layer_idx, "proj": proj_label, "l2": l2, "factor": factor })
      print(f"  layer {layer_idx:3d} {proj_label:25s}  MODIFIED   l2={l2}  factor={factor}", flush=True)

if not modified_layers:
  print("\nNo modifications detected.")
  sys.exit(0)

mod_idxs    = sorted(set(r["layer"] for r in modified_layers))
factors     = [r["factor"] for r in modified_layers]

print(f"\n=== RECOVERED RECIPE ===")
print(f"  onset      = {mod_idxs[0]}")
print(f"  last_layer = {mod_idxs[-1]}")
print(f"  factor     = {sum(factors)/len(factors)}  (min={min(factors)} max={max(factors)})")
print(f"  modified layers: {mod_idxs}")
