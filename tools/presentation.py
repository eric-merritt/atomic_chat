"""Presentation tools: display images, videos, text, and markdown inline in chat.

These tools have no side effects — they return structured data that the frontend
renders as rich media. Prefix: ap_ (agent presentation).
"""

import json5
from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result
from tools.web import _load_summary, _load_page

_IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
_VID_EXTS = {'.mp4', '.webm', '.avi', '.mkv', '.3gp'}


def _ext(url: str) -> str:
    from urllib.parse import urlparse
    from pathlib import PurePosixPath
    path = urlparse(url).path
    return PurePosixPath(path).suffix.lower()


def _require_str(p: dict, key: str) -> str | None:
    """Return error string if key is missing or blank, else None."""
    val = p.get(key, '')
    if not (isinstance(val, str) and val.strip()):
        return f"'{key}' is required and must be a non-empty string"
    return None


def _require_ext(url, allowed, label):
    ext = _ext(url)
    if ext not in allowed:
        readable = ', '.join(sorted(allowed))
        return f"URL extension '{ext or '(none)'}' is not allowed for {label}. Must be one of: {readable}"
    return None


def _check_ext(url, allowed, label):
    """Like _require_ext but skips validation when the URL has no extension (e.g. CDN URLs)."""
    ext = _ext(url)
    if not ext:
        return None
    if ext not in allowed:
        readable = ', '.join(sorted(allowed))
        return f"URL extension '{ext}' is not allowed for {label}. Must be one of: {readable}"
    return None


@register_tool('ap_img')
class ApImg(BaseTool):
    description = 'Display an image inline in the chat response. Use this to show images found on the web or from local paths.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Direct URL or local path to the image file.'},
            'caption': {'type': 'string', 'description': 'Caption to display below the image.'},
        },
        'required': ['url'],
    }

    def call(self, params: str, **kwargs) -> dict:
        try:
            p = json5.loads(params)
        except Exception as e:
            return tool_result(error=f'Malformed JSON input: {e}')
        if err := _require_str(p, 'url'):
            return tool_result(error=err)
        if err := _require_ext(p['url'], _IMG_EXTS, 'ap_img'):
            return tool_result(error=err)
        return tool_result({'type': 'ap_img', 'url': p['url'], 'caption': p.get('caption', '')})


@register_tool('ap_vid')
class ApVid(BaseTool):
    description = 'Display a video preview inline in the chat response. Ideal for short preview clips (2-10 seconds). Use this after finding video results so the user can preview them before downloading. Example: after a torrent/video search, call ap_vid for each result with its preview URL and title.'
    parameters = {
        'type': 'object',
        'properties': {
            'url': {'type': 'string', 'description': 'Direct URL to the video file (mp4, webm, etc.).'},
            'title': {'type': 'string', 'description': 'Title of the video.'},
            'thumbnail_url': {'type': 'string', 'description': 'Optional thumbnail/poster image URL shown before the video plays.'},
            'page_url': {'type': 'string', 'description': 'Optional URL of the page where this video was found.'},
        },
        'required': ['url', 'title'],
    }

    def call(self, params: str, **kwargs) -> dict:
        try:
            p = json5.loads(params)
        except Exception as e:
            return tool_result(error=f'Malformed JSON input: {e}')
        if err := _require_str(p, 'url'):
            return tool_result(error=err)
        if err := _require_str(p, 'title'):
            return tool_result(error=err)
        if err := _require_ext(p['url'], _VID_EXTS, 'ap_vid'):
            return tool_result(error=err)
        thumb = p.get('thumbnail_url', '')
        if thumb:
            if err := _require_ext(thumb, _IMG_EXTS, 'thumbnail_url'):
                return tool_result(error=err)
        return tool_result({'type': 'ap_vid', 'url': p['url'], 'title': p['title'], 'thumbnail_url': thumb, 'page_url': p.get('page_url', '')})


@register_tool('ap_txt')
class ApTxt(BaseTool):
    description = (
        'Display a block of plain text inline in the chat response. '
        'Pass `page_ref` (returned by www_find_content for non-gallery pages) to render the fetched page text — '
        'do NOT retype the content; let the server load it. '
        'Pass `content` for arbitrary text, file excerpts, or log output.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'page_ref': {'type': 'string', 'description': 'Ref handle from www_find_content (non-gallery pages). Server loads the page text; do not retype it.'},
            'content': {'type': 'string', 'description': 'Plain text content to display directly.'},
            'title': {'type': 'string', 'description': 'Optional title for the text block.'},
        },
        'required': [],
    }

    _MAX_CHARS = 10_000

    def call(self, params: str, **kwargs) -> dict:
        try:
            p = json5.loads(params)
        except Exception as e:
            return tool_result(error=f'Malformed JSON input: {e}')

        page_ref = (p.get('page_ref') or '').strip()
        content = (p.get('content') or '').strip()
        title = (p.get('title') or '').strip()

        if page_ref:
            entry = _load_page(page_ref)
            if not entry:
                return tool_result(error=f"page_ref '{page_ref}' not found or expired — re-run www_find_content and use the fresh ref.")
            import bs4
            soup = bs4.BeautifulSoup(entry['content'], 'html.parser')
            content = soup.get_text(separator='\n', strip=True)
            if not title:
                title = entry.get('url', '')

        if not content:
            return tool_result(error="Provide either 'page_ref' (from www_find_content) or non-empty 'content'")

        truncated = len(content) > self._MAX_CHARS
        display = content[:self._MAX_CHARS] + ('\n…[truncated]' if truncated else '')
        return tool_result({'type': 'ap_txt', 'content': display, 'title': title})


@register_tool('ap_dl_select_gallery')
class ApGallery(BaseTool):
    description = (
        'Display a selectable gallery grid of results inline. Each item gets a checkbox and a video/photo preview. '
        'Preferred: pass `summary_ref` — the short handle returned by www_find_content for gallery pages. The server loads the items for you; do not re-type them. '
        'Alternate: pass `items` yourself for hand-crafted galleries. '
        'Use this when the user asks to browse or download media — show ALL results, not a handful.'
    )
    parameters = {
        'type': 'object',
        'properties': {
            'summary_ref': {
                'type': 'string',
                'description': "Handle returned by www_find_content for gallery pages (field: `summary_ref`). The server resolves the items and title from this ref.",
            },
            'items': {
                'type': 'array',
                'description': 'Gallery items to display (alternative to summary_ref).',
                'items': {
                    'type': 'object',
                    'properties': {
                        'title': {'type': 'string', 'description': 'Display title for this item.'},
                        'url': {'type': 'string', 'description': 'Download or landing URL for this item.'},
                        'preview_photo': {'type': 'string', 'description': 'Thumbnail image URL.'},
                        'preview_video': {'type': 'string', 'description': 'Short preview video URL.'},
                        'page_url': {'type': 'string', 'description': 'Optional source page URL.'},
                    },
                    'required': ['title', 'url'],
                },
            },
            'caption': {'type': 'string', 'description': 'Optional label shown above the grid.'},
        },
        'required': []
    }

    def call(self, params: str, **kwargs) -> dict:
        try:
            p = json5.loads(params)
        except Exception as e:
            return tool_result(error=f'Malformed JSON input: {e}')

        items = p.get('items')
        summary_ref = p.get('summary_ref')
        caption = p.get('caption', '')

        if (not items) and summary_ref:
            entry = _load_summary(summary_ref)
            if not entry:
                return tool_result(error=f"summary_ref '{summary_ref}' not found or expired. Re-run www_find_content and pass the fresh ref.")
            summary = entry.get('summary') or {}
            if isinstance(summary.get('items'), list):
                items = summary['items']
            if not caption:
                caption = summary.get('title', '')

        if not isinstance(items, list) or len(items) == 0:
            return tool_result(error="Provide either `summary_ref` (from www_find_content) or a non-empty `items` array")

        validated = []
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                return tool_result(error=f'Item {i} must be an object')
            title = item.get('title') or ''
            url = item.get('url') or ''
            if not (title and isinstance(title, str)):
                return tool_result(error=f"Item {i}: 'title' is required")
            if not (url and isinstance(url, str)):
                return tool_result(error=f"Item {i}: 'url' is required")
            validated.append({
                'title': title,
                'url': url,
                'preview_photo': item.get('preview_photo', '') or '',
                'preview_video': item.get('preview_video', '') or '',
                'page_url': item.get('page_url', '') or '',
            })
        return tool_result({'type': 'ap_gallery', 'items': validated, 'caption': caption})


@register_tool('ap_md')
class ApMd(BaseTool):
    description = 'Display formatted markdown inline in the chat response. Use for structured summaries, tables, or any content that benefits from formatting.'
    parameters = {
        'type': 'object',
        'properties': {
            'content': {'type': 'string', 'description': 'Markdown content to render.'},
            'title': {'type': 'string', 'description': 'Optional title displayed above the content.'},
        },
        'required': ['content'],
    }

    def call(self, params: str, **kwargs) -> dict:
        try:
            p = json5.loads(params)
        except Exception as e:
            return tool_result(error=f'Malformed JSON input: {e}')
        if err := _require_str(p, 'content'):
            return tool_result(error=err)
        return tool_result({'type': 'ap_md', 'content': p['content'], 'title': p.get('title', '')})
