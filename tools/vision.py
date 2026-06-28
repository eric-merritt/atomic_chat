import os
import sys
import base64
import json5

# Project root on sys.path so `from tools.x` / `from config` resolve no matter
# how this file is launched (by path, as a module, or from inside tools/).
ROOT = os.path.expanduser("~") + "/devproj/python/atomic_chat"
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from qwen_agent.tools.base import register_tool, BaseTool
from tools._output import tool_result
from config import LLAMA_SERVER_URL, DEFAULT_MODEL


def _encode_image(file_path):
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


@register_tool("vis_desc_img")
class DescribeImageTool(BaseTool):
    """Sends an image to the vision model for analysis after encoding as Base64"""

    description = "Converts an image to Base64, then sends it to the vision model to be analyzed and converted into a text description."

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "An absolute filepath or a direct URL to an image.",
            },
            "prompt": {
                "type": "string",
                "description": 'A prompt that summarizes what the user wants from the vision model output. e.g. "Describe what is happening in this photo."',
            },
        },
        "required": ["path"],
    }

    def call(self, params: str, **kwargs):
        import requests

        p = json5.loads(params)
        path = p["path"]
        prompt = p["prompt"]

        VISION_URL = f"{LLAMA_SERVER_URL}/v1/chat/completions"
        # The main llama-server carries the Qwen vision projector (--mmproj),
        # so image analysis goes to the mounted model itself.

        def get_mime_type(file_path):
            ext = os.path.splitext(file_path)[1].lower()
            return {
                ".jpg": "jpeg",
                ".jpeg": "jpeg",
                ".png": "png",
                ".webp": "webp",
            }.get(ext, "jpeg")  # fallback

        # Handle URL vs local file
        if path.startswith("http"):
            image_url = path
        else:
            encoded_image = _encode_image(path)
            mime = get_mime_type(path)
            image_url = f"data:image/{mime};base64,{encoded_image}"

        payload = {
            "model": DEFAULT_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {
                            "type": "text",
                            "text": prompt
                            if prompt
                            else "Describe this image in detail.",
                        },
                    ],
                }
            ],
            "max_tokens": 300,
        }

        res = requests.post(VISION_URL, json=payload, timeout=60)

        return res.json()


IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp")
SHARPNESS_CUT = 20  # Stage 2 keeps this many sharpest frames for the model.
SWISS_ROUNDS = 3  # Stage 4 matches each frame plays within its action bucket.


def _is_image(file_path):
    return os.path.splitext(file_path)[1].lower() in IMAGE_EXTS


def _frame_index(file_path):
    # Parse the trailing number from names like frame_00042.jpg -> 42 so frames
    # carry their video order. Falls back to 0 when no digits are present.
    stem = os.path.splitext(os.path.basename(file_path))[0]
    digits = "".join(char for char in stem if char.isdigit())
    return int(digits) if digits else 0


def _collect_image_paths(paths, recursive):
    # One responsibility: expand the path list into a flat list of image files.
    collected = []
    for member in paths:
        if os.path.isfile(member):
            if _is_image(member):
                collected.append(member)
        elif os.path.isdir(member) and recursive:
            for root, _dirs, files in os.walk(member):
                collected += [
                    os.path.join(root, name) for name in files if _is_image(name)
                ]
        elif os.path.isdir(member):
            collected += [
                os.path.join(member, name)
                for name in os.listdir(member)
                if _is_image(name) and os.path.isfile(os.path.join(member, name))
            ]
    return sorted(set(collected), key=_frame_index)


def _sharpness(file_path):
    # Variance of the Laplacian: the standard motion-blur metric. Higher = sharper.
    import cv2

    gray = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return -1.0
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _sharpest(image_paths, keep):
    # One responsibility: rank by sharpness, return the top `keep` paths.
    ranked = sorted(image_paths, key=_sharpness, reverse=True)
    return ranked[:keep]


def _data_url(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    mime = {
        ".jpg": "jpeg",
        ".jpeg": "jpeg",
        ".png": "png",
        ".webp": "webp",
        ".bmp": "bmp",
    }.get(ext, "jpeg")
    return f"data:image/{mime};base64,{_encode_image(file_path)}"


def _ask_vision(content, max_tokens):
    # Single POST to the vision-capable llama-server. Returns the text reply.
    import requests

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": content}],
        "max_tokens": max_tokens,
    }
    res = requests.post(
        f"{LLAMA_SERVER_URL}/v1/chat/completions", json=payload, timeout=120
    )
    return res.json()["choices"][0]["message"]["content"].strip()


def _action_tag(file_path):
    # One responsibility: get a short action label for a single frame.
    content = [
        {"type": "image_url", "image_url": {"url": _data_url(file_path)}},
        {
            "type": "text",
            "text": "Label the primary action in this frame in 1-3 words "
            "(e.g. 'typing', 'talking', 'standing'). Reply with only the label.",
        },
    ]
    return _ask_vision(content, max_tokens=12).lower()


def _bucket_by_action(image_paths):
    # One responsibility: group frames by their model-assigned action label.
    buckets = {}
    for file_path in image_paths:
        label = _action_tag(file_path)
        buckets.setdefault(label, []).append(file_path)
    return buckets


def _compare_quality(left, right):
    # One responsibility: ask the model which of two frames is higher quality.
    # Returns the winning path. Defaults to `left` when the reply is ambiguous.
    content = [
        {"type": "image_url", "image_url": {"url": _data_url(left)}},
        {"type": "image_url", "image_url": {"url": _data_url(right)}},
        {
            "type": "text",
            "text": "Two frames are shown. Which is higher quality (sharper, "
            "less motion blur)? Reply with only '1' for the first or '2' for the second.",
        },
    ]
    return right if "2" in _ask_vision(content, max_tokens=4) else left


def _swiss_best(bucket):
    # One responsibility: rank a bucket by win-count over several matches and
    # return the single best frame. Robust to noisy individual comparisons.
    if len(bucket) < 2:
        return bucket[0]
    scores = {path: 0 for path in bucket}
    for round_number in range(SWISS_ROUNDS):
        ordered = sorted(bucket, key=lambda path: scores[path], reverse=True)
        rotated = ordered[round_number:] + ordered[:round_number]
        for left, right in zip(ordered, rotated):
            if left is right:
                continue
            scores[_compare_quality(left, right)] += 1
    return max(scores, key=lambda path: scores[path])


def _copy_winners(best_per_action, output_dir):
    # One responsibility: copy each winner into output_dir (originals untouched)
    # and return {action: new_path}. Skips copy if src and dst resolve equal.
    import shutil

    os.makedirs(output_dir, exist_ok=True)
    copied = {}
    for action, src in best_per_action.items():
        dst = os.path.join(output_dir, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
        copied[action] = dst
    return copied


@register_tool("viz_quality_sort")
class VisionGradingTool(BaseTool):
    """
    Selects the best, most varied frames from a set of webcam/video photos.

    Pipeline: collect -> sharpness cut (top 20, no model) -> action-tag the
    survivors (vision model) -> Swiss-score within each action bucket -> return
    the single best frame per distinct action. Diversity is driven by action
    labels so the result spans different moments, not one sharp instant.
    """

    description = (
        "Takes directories or photo paths from extracted video frames and returns "
        "the best-quality frame for each distinct action, favoring sharp, varied shots."
    )

    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "array",
                "items": {"type": "string"},
                "description": "One or more paths. Each can be an image file or a directory.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Include subdirectories' photos? Defaults to false.",
            },
            "output_dir": {
                "type": "string",
                "description": "If set, copy the selected winners into this directory "
                "(originals are left untouched) and return the new paths.",
            },
        },
        "required": ["path"],
    }

    def call(self, params: str, **kwargs):
        parsed = json5.loads(params)
        paths = parsed.get("path")
        recursive = bool(parsed.get("recursive", False))
        output_dir = parsed.get("output_dir")

        if isinstance(paths, str):
            paths = [paths]
        if not paths:
            return tool_result(error="No paths provided.")

        image_paths = _collect_image_paths(paths, recursive)
        if len(image_paths) < 2:
            return tool_result(error="Need at least 2 photos to compare.")

        candidates = _sharpest(image_paths, SHARPNESS_CUT)
        buckets = _bucket_by_action(candidates)
        best_per_action = {
            action: _swiss_best(frames) for action, frames in buckets.items()
        }
        if output_dir:
            best_per_action = _copy_winners(best_per_action, output_dir)
        return tool_result(data=best_per_action)
