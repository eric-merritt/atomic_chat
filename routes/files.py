"""File read and serve endpoints for the frontend file preview modal."""

import os
import uuid
from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required

_UPLOAD_DIR = os.path.join(os.path.expanduser("~"), "workspace", "uploads")
_ALLOWED_UPLOAD_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

files_bp = Blueprint("files", __name__, url_prefix="/api/files")

_ALLOWED_ROOTS = (
    os.path.realpath(os.path.expanduser("~")),
)

LANGUAGE_MAP = {
    '.py': 'python', '.ts': 'typescript', '.tsx': 'typescript',
    '.js': 'javascript', '.jsx': 'javascript', '.json': 'json',
    '.md': 'markdown', '.html': 'html', '.css': 'css',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash',
    '.yml': 'yaml', '.yaml': 'yaml', '.toml': 'toml',
    '.rs': 'rust', '.go': 'go', '.java': 'java',
    '.c': 'c', '.cpp': 'cpp', '.h': 'c',
    '.sql': 'sql', '.ini': 'ini', '.env': 'bash',
    '.txt': 'text', '.log': 'text', '.xml': 'xml',
}

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico'}

MAX_LINES = 500


def _safe_path(path: str) -> str | None:
    """Resolve path, reject traversal attempts, and enforce allowed roots."""
    if not path or not path.strip():
        return None
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        return None
    resolved = os.path.realpath(os.path.expanduser(path))
    if not any(resolved == root or resolved.startswith(root + os.sep) for root in _ALLOWED_ROOTS):
        return None
    return resolved


@files_bp.route("/read")
@login_required
def read_file():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    resolved = _safe_path(path)
    if not resolved:
        return jsonify({"error": "invalid path"}), 403
    if not os.path.isfile(resolved):
        return jsonify({"error": "not found"}), 404

    ext = os.path.splitext(resolved)[1].lower()
    if ext in IMAGE_EXTS:
        return jsonify({"error": "use /api/files/serve for images"}), 400

    language = LANGUAGE_MAP.get(ext, "text")

    try:
        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except PermissionError:
        return jsonify({"error": "permission denied"}), 403

    truncated = len(lines) > MAX_LINES
    content = "".join(lines[:MAX_LINES])

    return jsonify({
        "content": content,
        "language": language,
        "size_bytes": os.path.getsize(resolved),
        "lines_returned": min(len(lines), MAX_LINES),
        "truncated": truncated,
    })


@files_bp.route("/upload", methods=["POST"])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "no file provided"}), 400
    f = request.files['file']
    ext = os.path.splitext(f.filename or '')[1].lower()
    if ext not in _ALLOWED_UPLOAD_EXTS:
        allowed = ', '.join(sorted(_ALLOWED_UPLOAD_EXTS))
        return jsonify({"error": f"unsupported type '{ext}', allowed: {allowed}"}), 400
    os.makedirs(_UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    dest = os.path.join(_UPLOAD_DIR, filename)
    f.save(dest)
    return jsonify({"path": dest, "filename": f.filename})


@files_bp.route("/serve")
@login_required
def serve_file():
    path = request.args.get("path", "")
    if not path:
        return jsonify({"error": "path required"}), 400
    resolved = _safe_path(path)
    if not resolved:
        return jsonify({"error": "invalid path"}), 403
    if not os.path.isfile(resolved):
        return jsonify({"error": "not found"}), 404
    return send_file(resolved)
