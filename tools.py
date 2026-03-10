"""
Agent tools derived from ~/agent_tooling.py.
Each function is wrapped with LangChain's @tool decorator so it can be
bound to a ChatOllama agent.  All tools are *always* passed to the agent;
the CLI tool-browser just lets the user inspect required params.
"""

import os
import re
import glob as glob_mod
import json
import shutil
import difflib
import time
import random
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional

from langchain.tools import tool
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage


# ── Read Operations ──────────────────────────────────────────────────────────

@tool
def read_file(path: str, start_line: int = 0, end_line: int = -1) -> str:
    """Read a file and return its contents with line numbers.

    Args:
        path: Absolute or relative file path.
        start_line: First line to include (0-indexed).
        end_line: Last line to include (exclusive). -1 = read to end.
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    end = None if end_line == -1 else end_line
    subset = lines[start_line:end]
    numbered = [f"{i:>6}  {line.rstrip()}" for i, line in enumerate(subset, start=start_line + 1)]
    return "\n".join(numbered)


@tool
def file_info(path: str) -> str:
    """Return metadata about a file: size, modified time, type, line count.

    Args:
        path: Absolute or relative file path.
    """
    path = os.path.expanduser(path)
    stat = os.stat(path)
    info = {
        "path": os.path.abspath(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified": stat.st_mtime,
        "is_file": os.path.isfile(path),
        "is_dir": os.path.isdir(path),
    }
    if info["is_file"]:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                info["line_count"] = sum(1 for _ in f)
        except Exception:
            info["line_count"] = None
    return json.dumps(info, indent=2)


@tool
def list_dir(path: str = ".", recursive: bool = False, pattern: str = "*") -> str:
    """List directory contents, optionally recursive with glob pattern.

    Args:
        path: Directory to list.
        recursive: If True, walk subdirectories.
        pattern: Glob pattern to filter results (e.g. '*.py').
    """
    path = os.path.expanduser(path)
    if recursive:
        entries = sorted(glob_mod.glob(os.path.join(path, "**", pattern), recursive=True))
    else:
        entries = sorted(glob_mod.glob(os.path.join(path, pattern)))
    return "\n".join(entries)


@tool
def tree(path: str = ".", max_depth: int = 3, show_hidden: bool = False) -> str:
    """Generate a directory tree string.

    Args:
        path: Root directory.
        max_depth: Maximum depth to traverse.
        show_hidden: Include dotfiles/dotdirs.
    """
    path = os.path.expanduser(path)
    lines = []

    def _walk(dir_path: str, prefix: str, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return
        if not show_hidden:
            entries = [e for e in entries if not e.startswith(".")]
        dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e))]
        files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e))]
        for f in files:
            lines.append(f"{prefix}{f}")
        for d in dirs:
            lines.append(f"{prefix}{d}/")
            _walk(os.path.join(dir_path, d), prefix + "  ", depth + 1)

    lines.append(f"{os.path.basename(os.path.abspath(path))}/")
    _walk(path, "  ", 1)
    return "\n".join(lines)


# ── Write Operations ─────────────────────────────────────────────────────────

@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file, creating parent directories if needed.

    Args:
        path: File path to write.
        content: Full file content.
    """
    path = os.path.expanduser(path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        written = f.write(content)
    return f"Wrote {written} bytes to {os.path.abspath(path)}"


@tool
def append_file(path: str, content: str) -> str:
    """Append content to the end of a file.

    Args:
        path: File path to append to.
        content: Content to append.
    """
    path = os.path.expanduser(path)
    with open(path, "a", encoding="utf-8") as f:
        written = f.write(content)
    return f"Appended {written} bytes to {os.path.abspath(path)}"


@tool
def replace_in_file(path: str, old: str, new: str, count: int = 1) -> str:
    """Replace exact string occurrences in a file.

    Args:
        path: File to edit.
        old: Exact string to find.
        new: Replacement string.
        count: Max replacements. 0 = replace all.
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        return f"ERROR: String not found in {path}"
    occurrences = content.count(old)
    if count == 0:
        new_content = content.replace(old, new)
        replaced = occurrences
    else:
        new_content = content.replace(old, new, count)
        replaced = min(count, occurrences)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)
    return f"Replaced {replaced} occurrence(s) in {os.path.abspath(path)}"


@tool
def insert_at_line(path: str, line_number: int, content: str) -> str:
    """Insert content at a specific line number (1-indexed).

    Args:
        path: File to edit.
        line_number: Line number to insert before (1-indexed).
        content: Text to insert.
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    if not content.endswith("\n"):
        content += "\n"
    lines.insert(line_number - 1, content)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Inserted at line {line_number} in {os.path.abspath(path)}"


@tool
def delete_lines(path: str, start: int, end: int) -> str:
    """Delete a range of lines from a file (1-indexed, inclusive).

    Args:
        path: File to edit.
        start: First line to delete (1-indexed).
        end: Last line to delete (1-indexed, inclusive).
    """
    path = os.path.expanduser(path)
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    removed = lines[start - 1 : end]
    del lines[start - 1 : end]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return f"Deleted lines {start}-{end} ({len(removed)} lines) from {os.path.abspath(path)}"


# ── File Management ──────────────────────────────────────────────────────────

@tool
def copy_file(src: str, dst: str) -> str:
    """Copy a file or directory.

    Args:
        src: Source path.
        dst: Destination path.
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
    else:
        os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
        shutil.copy2(src, dst)
    return f"Copied {src} -> {dst}"


@tool
def move_file(src: str, dst: str) -> str:
    """Move/rename a file or directory.

    Args:
        src: Source path.
        dst: Destination path.
    """
    src, dst = os.path.expanduser(src), os.path.expanduser(dst)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    shutil.move(src, dst)
    return f"Moved {src} -> {dst}"


@tool
def delete_file(path: str) -> str:
    """Delete a file or empty directory.

    Args:
        path: Path to delete.
    """
    path = os.path.expanduser(path)
    if os.path.isdir(path):
        os.rmdir(path)
    else:
        os.remove(path)
    return f"Deleted {os.path.abspath(path)}"


@tool
def make_dir(path: str) -> str:
    """Create a directory and any missing parents.

    Args:
        path: Directory path to create.
    """
    path = os.path.expanduser(path)
    os.makedirs(path, exist_ok=True)
    return f"Created directory {os.path.abspath(path)}"


# ── Search Operations ────────────────────────────────────────────────────────

@tool
def grep(
    pattern: str,
    path: str = ".",
    file_pattern: str = "*",
    ignore_case: bool = False,
    context: int = 0,
    max_results: int = 50,
) -> str:
    """Search file contents with regex, returning matches with context.

    Args:
        pattern: Regex pattern to search for.
        path: File or directory to search in.
        file_pattern: Glob to filter which files to search (e.g. '*.py').
        ignore_case: Case-insensitive matching.
        context: Number of lines before/after each match to include.
        max_results: Maximum number of matches to return.
    """
    path = os.path.expanduser(path)
    flags = re.IGNORECASE if ignore_case else 0
    regex = re.compile(pattern, flags)
    results = []

    if os.path.isfile(path):
        files = [path]
    else:
        files = sorted(glob_mod.glob(os.path.join(path, "**", file_pattern), recursive=True))

    for filepath in files:
        if not os.path.isfile(filepath):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except (PermissionError, OSError):
            continue
        for i, line in enumerate(lines):
            if regex.search(line):
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                snippet = []
                for j in range(start, end):
                    marker = ">" if j == i else " "
                    snippet.append(f"  {marker} {j + 1:>5}  {lines[j].rstrip()}")
                results.append(f"{filepath}:{i + 1}\n" + "\n".join(snippet))
                if len(results) >= max_results:
                    return "\n\n".join(results) + f"\n... (truncated at {max_results} results)"

    if not results:
        return f"No matches for /{pattern}/ in {path}"
    return "\n\n".join(results)


@tool
def find_files(
    path: str = ".",
    name: str = "",
    extension: str = "",
    contains: str = "",
    max_results: int = 50,
) -> str:
    """Find files by name pattern, extension, or content.

    Args:
        path: Directory to search.
        name: Glob pattern for filename (e.g. 'test_*').
        extension: File extension filter (e.g. '.py').
        contains: Only return files containing this string.
        max_results: Maximum files to return.
    """
    path = os.path.expanduser(path)
    pat = name if name else "*"
    if extension:
        if not extension.startswith("."):
            extension = "." + extension
        pat = f"*{extension}" if not name else pat

    matches = sorted(glob_mod.glob(os.path.join(path, "**", pat), recursive=True))
    matches = [m for m in matches if os.path.isfile(m)]

    if extension and name:
        matches = [m for m in matches if m.endswith(extension)]

    if contains:
        filtered = []
        for m in matches:
            try:
                with open(m, "r", encoding="utf-8", errors="replace") as f:
                    if contains in f.read():
                        filtered.append(m)
            except (PermissionError, OSError):
                continue
        matches = filtered

    return "\n".join(matches[:max_results])


@tool
def find_definition(symbol: str, path: str = ".", file_pattern: str = "*.py") -> str:
    """Find where a function, class, or variable is defined.

    Args:
        symbol: Name of the symbol to find.
        path: Directory to search.
        file_pattern: Glob pattern for files to search.
    """
    patterns = [
        rf"^\s*(def|class)\s+{re.escape(symbol)}\b",
        rf"^\s*(export\s+)?(function|const|let|var|class)\s+{re.escape(symbol)}\b",
        rf"^{re.escape(symbol)}\s*=",
    ]
    combined = "|".join(f"({p})" for p in patterns)
    return grep.invoke({"pattern": combined, "path": path, "file_pattern": file_pattern, "context": 3})


# ── Web Operations ───────────────────────────────────────────────────────────

@tool
def web_search(query: str, num_results: int = 5) -> str:
    """Search the web using DuckDuckGo and return results.

    Args:
        query: Search query string.
        num_results: Max results to return.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return f"ERROR: DuckDuckGo search failed: {e}"

    results = []
    if data.get("AbstractText"):
        results.append(f"[Answer] {data['AbstractText']}\n  Source: {data.get('AbstractURL', 'N/A')}")
    for topic in data.get("RelatedTopics", [])[:num_results]:
        if isinstance(topic, dict) and "Text" in topic:
            results.append(f"[Result] {topic['Text']}\n  URL: {topic.get('FirstURL', 'N/A')}")
    if not results:
        return f"No instant answer found for: {query}\nTry: https://duckduckgo.com/?q={encoded}"
    return "\n\n".join(results)


@tool
def fetch_url(url: str, max_chars: int = 5000) -> str:
    """Fetch a URL and return its text content (HTML tags stripped).

    Args:
        url: URL to fetch.
        max_chars: Maximum characters to return.
    """
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentTooling/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: Failed to fetch {url}: {e}"

    if "html" in content_type.lower() or raw.strip().startswith("<"):
        raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
        raw = re.sub(r"\s+", " ", raw).strip()

    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n... (truncated at {max_chars} chars)"
    return raw


# ── eBay Operations ──────────────────────────────────────────────────────────

EBAY_SORT_OPTIONS = {
    "best_match": "",
    "ending_soonest": "&_sop=1",
    "newly_listed": "&_sop=10",
    "price_low": "&_sop=15",
    "price_high": "&_sop=16",
}


def _parse_ebay_listings(html: str) -> list[dict]:
    """Extract listing data from eBay search results HTML (internal helper).

    Supports both the legacy s-item__* layout and the current s-card layout
    (eBay migrated to su-card-container / s-card classes circa late 2025).
    """
    # Restrict to main results river if present
    river_marker = re.search(r'id=["\']?srp-river-results["\']?', html)
    if river_marker:
        html = html[river_marker.start():]

    listings = []

    # ── New layout (s-card) ──────────────────────────────────────────────
    # Each listing card starts with class="s-card s-card--horizontal"
    card_starts = [m.start() for m in re.finditer(r'class="s-card\s+s-card--', html)]
    if card_starts:
        for idx, start in enumerate(card_starts):
            end = card_starts[idx + 1] if idx + 1 < len(card_starts) else len(html)
            block = html[start:end]
            listing = {}

            # Title: inside <div ... class=s-card__title><span class="su-styled-text primary default">TEXT</span>
            title_match = re.search(
                r'class=s-card__title[^>]*>(.*?)</div>',
                block, re.DOTALL,
            )
            if title_match:
                title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
                # Remove eBay boilerplate suffixes/prefixes
                title = re.sub(r"Opens in a new window or tab$", "", title).strip()
                title = re.sub(r"^New Listing", "", title).strip()
                if title.lower() in ("shop on ebay", "results matching fewer words", ""):
                    continue
                listing["title"] = title

            # URL: href=https://www.ebay.com/itm/NNN (may or may not be quoted)
            url_match = re.search(r'href=["\']?(https://www\.ebay\.com/itm/\d+)', block)
            if url_match:
                listing["url"] = url_match.group(1)

            # Price: class="... s-card__price">$XX.XX</span>
            # Collect all price spans and join them (handles "X to Y" ranges)
            price_spans = re.findall(r's-card__price">(.*?)</span>', block, re.DOTALL)
            if price_spans:
                price_text = " ".join(re.sub(r"<[^>]+>", "", p).strip() for p in price_spans)
                listing["price_text"] = price_text
                nums = re.findall(r"\$?([\d,]+\.?\d*)", price_text)
                if nums:
                    listing["price"] = float(nums[0].replace(",", ""))

            # Shipping: look for "delivery" or "shipping" text
            ship_match = re.search(
                r'su-styled-text[^>]*>([^<]*(?:delivery|shipping)[^<]*)</span>',
                block, re.IGNORECASE,
            )
            if ship_match:
                listing["shipping"] = ship_match.group(1).strip()

            if listing.get("title") and listing.get("url"):
                listings.append(listing)

        if listings:
            return listings

    # ── Legacy layout (s-item) ───────────────────────────────────────────
    item_blocks = re.findall(
        r'<div class="s-item__wrapper[^"]*">(.*?)</div>\s*</div>\s*</li>',
        html, re.DOTALL,
    )
    if not item_blocks:
        item_blocks = re.findall(r'class="s-item\s[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL)

    for block in item_blocks:
        listing = {}
        title_match = re.search(
            r'class="s-item__title[^"]*"[^>]*>(?:<span[^>]*>)?(.*?)(?:</span>)?</(?:h3|div|span)>',
            block, re.DOTALL,
        )
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
            if title.lower() in ("shop on ebay", "results matching fewer words"):
                continue
            listing["title"] = title

        url_match = re.search(r'href="(https://www\.ebay\.com/itm/[^"]+)"', block)
        if url_match:
            listing["url"] = url_match.group(1).split("?")[0]

        price_match = re.search(r'class="s-item__price[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if price_match:
            price_text = re.sub(r"<[^>]+>", "", price_match.group(1)).strip()
            listing["price_text"] = price_text
            nums = re.findall(r"\$?([\d,]+\.?\d*)", price_text)
            if nums:
                listing["price"] = float(nums[0].replace(",", ""))

        ship_match = re.search(r'class="s-item__shipping[^"]*"[^>]*>(.*?)</span>', block, re.DOTALL)
        if ship_match:
            listing["shipping"] = re.sub(r"<[^>]+>", "", ship_match.group(1)).strip()

        if listing.get("title") and listing.get("url"):
            listings.append(listing)
    return listings


@tool
def ebay_search(
    query: str,
    sort: str = "best_match",
    min_price: float = -1,
    max_price: float = -1,
    condition: str = "",
    max_results: int = 20,
) -> str:
    """Search eBay and return parsed listings.

    Args:
        query: Search terms.
        sort: Sort order (best_match, ending_soonest, newly_listed, price_low, price_high).
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        condition: Filter (new, used, refurbished, parts). Empty to skip.
        max_results: Max listings to return.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}"
    url += EBAY_SORT_OPTIONS.get(sort, "")
    if min_price >= 0:
        url += f"&_udlo={min_price}"
    if max_price >= 0:
        url += f"&_udhi={max_price}"
    condition_map = {
        "new": "&LH_ItemCondition=1000",
        "used": "&LH_ItemCondition=3000",
        "refurbished": "&LH_ItemCondition=2500",
        "parts": "&LH_ItemCondition=7000",
    }
    if condition.lower() in condition_map:
        url += condition_map[condition.lower()]
    url += "&rt=nc&LH_BIN=1"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return json.dumps([{"error": str(e)}])

    listings = _parse_ebay_listings(html)[:max_results]
    return json.dumps(listings, indent=2)


@tool
def ebay_sold_search(query: str, max_results: int = 20) -> str:
    """Search eBay completed/sold listings to find market prices.

    Args:
        query: Search terms.
        max_results: Max listings to return.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}&LH_Complete=1&LH_Sold=1&rt=nc"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return json.dumps([{"error": str(e)}])

    listings = _parse_ebay_listings(html)[:max_results]
    for listing in listings:
        listing["sold"] = True
    return json.dumps(listings, indent=2)


# ── GPU model extraction & shipping parsing ──────────────────────────────────

_GPU_MODEL_PATTERNS = [
    # GeForce RTX consumer (Turing → Blackwell)
    re.compile(r"(RTX)\s*(\d0[5-9]0)(\s*Ti|\s*Super)?", re.IGNORECASE),
    # GTX 16-series (Turing)
    re.compile(r"(GTX)\s*(16[56]0)(\s*Ti|\s*Super)?", re.IGNORECASE),
    # Data center / workstation (match longer names first)
    re.compile(r"(Quadro\s*RTX\s*[4-8]000)", re.IGNORECASE),
    re.compile(r"\b(A100|A6000|A5000|A4000|A40|A30|A10)\b", re.IGNORECASE),
    re.compile(r"\b(L40S|L40)\b", re.IGNORECASE),
    re.compile(r"\b(H200|H100)\b", re.IGNORECASE),
    re.compile(r"\b(B200|B100|GB200)\b", re.IGNORECASE),
    re.compile(r"\b(T4)\b"),
]


def _extract_gpu_model(title: str) -> str:
    """Extract a normalized GPU model name from a listing title.

    Returns a canonical string like 'RTX 3060 Ti' or 'A100', or '' if no
    known model is found.
    """
    for pat in _GPU_MODEL_PATTERNS:
        m = pat.search(title)
        if m:
            groups = [g.strip() for g in m.groups() if g]
            model = " ".join(groups)
            # Normalize spacing: "RTX3060" → "RTX 3060"
            model = re.sub(r"(RTX|GTX)\s*(\d)", r"\1 \2", model, flags=re.IGNORECASE)
            # Collapse any double spaces
            model = re.sub(r"\s+", " ", model).strip()
            return model.upper()
    return ""


def _parse_shipping_cost(shipping: str) -> float:
    """Parse a shipping string into a numeric cost.

    Examples:
        '+$10.00 delivery'  → 10.0
        'Free delivery'     → 0.0
        'delivery in 2-4 days' → 0.0  (assumed free when no price stated)
        ''                  → 0.0
    """
    if not shipping:
        return 0.0
    shipping_lower = shipping.lower()
    if "free" in shipping_lower:
        return 0.0
    m = re.search(r"\$?([\d,]+\.?\d*)", shipping)
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


@tool
def ebay_deep_scan(
    query: str,
    condition: str = "used",
    min_price: float = -1,
    max_price: float = -1,
    sort: str = "best_match",
    pages: int = 5,
    max_results: int = 200,
) -> str:
    """Paginated eBay search that compresses results to model + price for bulk analysis.

    Scrapes multiple pages with rate-limiting delays, extracts GPU model names,
    parses shipping costs, deduplicates by URL, and returns compact listings
    sorted by model then total cost.

    Args:
        query: Search terms (e.g. 'RTX 3060', 'used GPU').
        condition: Filter (new, used, refurbished, parts). Empty to skip.
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        sort: Sort order (best_match, ending_soonest, newly_listed, price_low, price_high).
        pages: Number of result pages to scrape (1-10).
        max_results: Maximum total listings to return.
    """
    pages = max(1, min(pages, 10))

    encoded = urllib.parse.quote_plus(query)
    base_url = f"https://www.ebay.com/sch/i.html?_nkw={encoded}"
    base_url += EBAY_SORT_OPTIONS.get(sort, "")
    if min_price >= 0:
        base_url += f"&_udlo={min_price}"
    if max_price >= 0:
        base_url += f"&_udhi={max_price}"
    condition_map = {
        "new": "&LH_ItemCondition=1000",
        "used": "&LH_ItemCondition=3000",
        "refurbished": "&LH_ItemCondition=2500",
        "parts": "&LH_ItemCondition=7000",
    }
    if condition.lower() in condition_map:
        base_url += condition_map[condition.lower()]
    base_url += "&rt=nc&LH_BIN=1"

    seen_urls = set()
    all_listings = []

    for page_num in range(1, pages + 1):
        url = base_url if page_num == 1 else f"{base_url}&_pgn={page_num}"

        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:
            # Skip failed pages and keep going
            if page_num < pages:
                time.sleep(random.uniform(3.0, 6.0))
            continue

        raw_listings = _parse_ebay_listings(html)

        for listing in raw_listings:
            item_url = listing.get("url", "")
            if not item_url or item_url in seen_urls:
                continue
            seen_urls.add(item_url)

            price = listing.get("price", 0.0)
            shipping_cost = _parse_shipping_cost(listing.get("shipping", ""))
            model = _extract_gpu_model(listing.get("title", ""))

            all_listings.append({
                "model": model,
                "title": listing.get("title", ""),
                "price": price,
                "shipping_cost": shipping_cost,
                "total_cost": round(price + shipping_cost, 2),
                "url": item_url,
            })

        # Rate-limit delay between pages (skip after last page)
        if page_num < pages:
            time.sleep(random.uniform(3.0, 6.0))

    # Sort by model name, then total cost
    all_listings.sort(key=lambda x: (x["model"], x["total_cost"]))

    return json.dumps(all_listings[:max_results], indent=2)


# ── Amazon Operations ─────────────────────────────────────────────────────────

def _parse_amazon_listings(html: str) -> list[dict]:
    """Extract listing data from Amazon search results HTML (internal helper).

    Parses the search result cards from Amazon's HTML, extracting title, URL,
    price, rating, and Prime eligibility.
    """
    listings = []

    # Find search result items by data-component-type="s-search-result"
    blocks = re.findall(
        r'data-component-type="s-search-result"[^>]*data-asin="([^"]+)"(.*?)(?=data-component-type="s-search-result"|<div class="s-main-slot s-result-list-col-0-footer">|$)',
        html, re.DOTALL,
    )
    if not blocks:
        # Fallback: split by data-asin
        blocks = re.findall(
            r'data-asin="([A-Z0-9]{10})"(.*?)(?=data-asin="[A-Z0-9]{10}"|$)',
            html, re.DOTALL,
        )

    for asin, block in blocks:
        if not asin or asin == "":
            continue
        listing: dict = {"asin": asin}

        # Title: usually in <span class="a-text-normal"> or <h2>
        title_match = re.search(
            r'<span class="a-(?:size-medium a-color-base a-text-normal|text-normal)"[^>]*>(.*?)</span>',
            block, re.DOTALL,
        )
        if not title_match:
            title_match = re.search(r'<h2[^>]*>.*?<span[^>]*>(.*?)</span>', block, re.DOTALL)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()
            if not title or title.lower() in ("", "sponsored"):
                continue
            listing["title"] = title
        else:
            continue

        # URL
        url_match = re.search(r'href="(/[^"]*?/dp/[A-Z0-9]{10}[^"]*)"', block)
        if url_match:
            listing["url"] = "https://www.amazon.com" + url_match.group(1).split("/ref=")[0]
        else:
            listing["url"] = f"https://www.amazon.com/dp/{asin}"

        # Price: look for <span class="a-price"> containing whole and fraction
        price_whole = re.search(r'<span class="a-price-whole">(\d[\d,]*)', block)
        price_frac = re.search(r'<span class="a-price-fraction">(\d+)', block)
        if price_whole:
            price_str = price_whole.group(1).replace(",", "")
            frac = price_frac.group(1) if price_frac else "00"
            listing["price"] = float(f"{price_str}.{frac}")
            listing["price_text"] = f"${listing['price']:.2f}"

        # Rating
        rating_match = re.search(r'(\d\.?\d?) out of 5 stars', block)
        if rating_match:
            listing["rating"] = float(rating_match.group(1))

        # Prime
        if "a-icon-prime" in block or "Prime" in block:
            listing["prime"] = True

        # Shipping - free shipping detection
        if "FREE delivery" in block or "free shipping" in block.lower() or listing.get("prime"):
            listing["shipping"] = "Free"
            listing["shipping_cost"] = 0.0
        else:
            ship_match = re.search(r'\$(\d+\.?\d*)\s*(?:delivery|shipping)', block, re.IGNORECASE)
            if ship_match:
                listing["shipping_cost"] = float(ship_match.group(1))
                listing["shipping"] = f"+${ship_match.group(1)} shipping"
            else:
                listing["shipping_cost"] = 0.0
                listing["shipping"] = "Unknown"

        if listing.get("title"):
            listings.append(listing)

    return listings


@tool
def amazon_search(
    query: str,
    min_price: float = -1,
    max_price: float = -1,
    sort: str = "relevance",
    max_results: int = 20,
) -> str:
    """Search Amazon and return parsed product listings.

    Args:
        query: Search terms (e.g. 'RTX 3060', 'mechanical keyboard').
        min_price: Minimum price filter in dollars. -1 to skip.
        max_price: Maximum price filter in dollars. -1 to skip.
        sort: Sort order (relevance, price_low, price_high, avg_review, newest).
        max_results: Max listings to return.
    """
    encoded = urllib.parse.quote_plus(query)
    url = f"https://www.amazon.com/s?k={encoded}"

    sort_map = {
        "relevance": "",
        "price_low": "&s=price-asc-rank",
        "price_high": "&s=price-desc-rank",
        "avg_review": "&s=review-rank",
        "newest": "&s=date-desc-rank",
    }
    url += sort_map.get(sort, "")

    # Price filters (Amazon uses cents in low/high params on some pages,
    # but the rh= filter works more reliably)
    if min_price >= 0 or max_price >= 0:
        lo = int(min_price * 100) if min_price >= 0 else ""
        hi = int(max_price * 100) if max_price >= 0 else ""
        url += f"&rh=p_36%3A{lo}-{hi}"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return json.dumps([{"error": str(e)}])

    listings = _parse_amazon_listings(html)[:max_results]

    # Enrich with GPU model if applicable
    for listing in listings:
        model = _extract_gpu_model(listing.get("title", ""))
        if model:
            listing["gpu_model"] = model

    return json.dumps(listings, indent=2)


# ── Craigslist Operations ─────────────────────────────────────────────────────

# Cities within ~100mi of Denver (pickup OK)
CRAIGSLIST_DENVER_AREA = {
    "denver":           "https://denver.craigslist.org",
    "boulder":          "https://boulder.craigslist.org",
    "colorado springs": "https://cosprings.craigslist.org",
    "fort collins":     "https://fortcollins.craigslist.org",
    "pueblo":           "https://pueblo.craigslist.org",
}

# Major cities outside 100mi (shipping required)
CRAIGSLIST_SHIPPING_CITIES = {
    "los angeles":  "https://losangeles.craigslist.org",
    "san francisco":"https://sfbay.craigslist.org",
    "san diego":    "https://sandiego.craigslist.org",
    "seattle":      "https://seattle.craigslist.org",
    "portland":     "https://portland.craigslist.org",
    "phoenix":      "https://phoenix.craigslist.org",
    "dallas":       "https://dallas.craigslist.org",
    "houston":      "https://houston.craigslist.org",
    "austin":       "https://austin.craigslist.org",
    "chicago":      "https://chicago.craigslist.org",
    "new york":     "https://newyork.craigslist.org",
    "atlanta":      "https://atlanta.craigslist.org",
    "miami":        "https://miami.craigslist.org",
    "minneapolis":  "https://minneapolis.craigslist.org",
    "detroit":      "https://detroit.craigslist.org",
    "boston":        "https://boston.craigslist.org",
    "philadelphia": "https://philadelphia.craigslist.org",
    "washington dc":"https://washingtondc.craigslist.org",
    "las vegas":    "https://lasvegas.craigslist.org",
    "salt lake city":"https://saltlakecity.craigslist.org",
}


def _parse_craigslist_listings(html: str, city: str, is_local: bool) -> list[dict]:
    """Extract listing data from Craigslist search results HTML.

    Args:
        html: Raw HTML from Craigslist search.
        city: City name for labeling.
        is_local: True if within 100mi of Denver (pickup available).
    """
    listings = []

    # Craigslist uses <li class="cl-static-search-result"> or <li class="result-row">
    # New layout (2024+): <li class="cl-static-search-result">
    new_items = re.findall(
        r'<li class="cl-static-search-result"[^>]*>(.*?)</li>',
        html, re.DOTALL,
    )

    if new_items:
        for block in new_items:
            listing: dict = {"city": city}
            listing["fulfillment"] = "pickup" if is_local else "shipping_required"

            # Title and URL
            link = re.search(r'href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            if link:
                url = link.group(1)
                if not url.startswith("http"):
                    # relative URL — shouldn't happen but handle it
                    pass
                listing["url"] = url
                listing["title"] = re.sub(r"<[^>]+>", "", link.group(2)).strip()

            # Price
            price_match = re.search(r'<div class="price">\s*\$?([\d,]+)', block)
            if price_match:
                listing["price"] = float(price_match.group(1).replace(",", ""))
                listing["price_text"] = f"${listing['price']:.0f}"

            if listing.get("title") and listing.get("url"):
                listings.append(listing)
    else:
        # Legacy layout: <li class="result-row">
        legacy_items = re.findall(
            r'<li class="result-row"[^>]*>(.*?)</li>',
            html, re.DOTALL,
        )
        for block in legacy_items:
            listing = {"city": city}
            listing["fulfillment"] = "pickup" if is_local else "shipping_required"

            link = re.search(r'href="([^"]+)"[^>]*class="result-title[^"]*">(.*?)</a>', block, re.DOTALL)
            if link:
                listing["url"] = link.group(1)
                listing["title"] = re.sub(r"<[^>]+>", "", link.group(2)).strip()

            price_match = re.search(r'<span class="result-price">\$?([\d,]+)', block)
            if price_match:
                listing["price"] = float(price_match.group(1).replace(",", ""))
                listing["price_text"] = f"${listing['price']:.0f}"

            if listing.get("title") and listing.get("url"):
                listings.append(listing)

    return listings


def _craigslist_search_city(
    base_url: str,
    query: str,
    city: str,
    is_local: bool,
    category: str = "sss",
    min_price: int = -1,
    max_price: int = -1,
    max_results: int = 25,
) -> list[dict]:
    """Search a single Craigslist city and return parsed listings."""
    encoded = urllib.parse.quote_plus(query)
    url = f"{base_url}/search/{category}?query={encoded}"
    if min_price >= 0:
        url += f"&min_price={min_price}"
    if max_price >= 0:
        url += f"&max_price={max_price}"
    # For non-local cities, filter to shipping available
    if not is_local:
        url += "&shipping=1"

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
            "Accept-Language": "en-US,en;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return []

    return _parse_craigslist_listings(html, city, is_local)[:max_results]


@tool
def craigslist_search(
    query: str,
    city: str = "denver",
    category: str = "sss",
    min_price: int = -1,
    max_price: int = -1,
    max_results: int = 25,
) -> str:
    """Search Craigslist in a specific city.

    Cities within ~100mi of Denver (pickup available): denver, boulder,
    colorado springs, fort collins, pueblo.

    Cities outside that radius require shipping. Available: los angeles,
    san francisco, san diego, seattle, portland, phoenix, dallas, houston,
    austin, chicago, new york, atlanta, miami, minneapolis, detroit, boston,
    philadelphia, washington dc, las vegas, salt lake city.

    Args:
        query: Search terms.
        city: City name (see above). Defaults to denver.
        category: Craigslist category code. 'sss' = for sale, 'cta' = cars+trucks,
                  'sys' = computers, 'ele' = electronics.
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        max_results: Max listings to return.
    """
    city_lower = city.lower().strip()

    if city_lower in CRAIGSLIST_DENVER_AREA:
        base_url = CRAIGSLIST_DENVER_AREA[city_lower]
        is_local = True
    elif city_lower in CRAIGSLIST_SHIPPING_CITIES:
        base_url = CRAIGSLIST_SHIPPING_CITIES[city_lower]
        is_local = False
    else:
        return json.dumps({"error": f"Unknown city '{city}'. Use one of: {', '.join(sorted(list(CRAIGSLIST_DENVER_AREA.keys()) + list(CRAIGSLIST_SHIPPING_CITIES.keys())))}"})

    listings = _craigslist_search_city(
        base_url, query, city_lower, is_local,
        category=category, min_price=min_price, max_price=max_price,
        max_results=max_results,
    )

    # Enrich with GPU model if applicable
    for listing in listings:
        model = _extract_gpu_model(listing.get("title", ""))
        if model:
            listing["gpu_model"] = model

    return json.dumps(listings, indent=2)


@tool
def craigslist_multi_search(
    query: str,
    scope: str = "local",
    category: str = "sss",
    min_price: int = -1,
    max_price: int = -1,
    max_results_per_city: int = 10,
) -> str:
    """Search Craigslist across multiple cities simultaneously.

    This is a LOOPING tool — it iterates through cities one by one with
    rate-limiting delays between requests. Results accumulate across all cities.

    Scope controls which cities to search:
    - 'local': Denver-area cities only (within 100mi — pickup available)
    - 'shipping': Major US cities outside Denver area (shipping required)
    - 'all': Both local and shipping cities

    Args:
        query: Search terms.
        scope: Which cities to search: 'local', 'shipping', or 'all'.
        category: Craigslist category code. 'sss' = for sale, 'sys' = computers,
                  'ele' = electronics, 'cta' = cars+trucks.
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        max_results_per_city: Max listings per city.
    """
    cities_to_search: list[tuple[str, str, bool]] = []  # (city, url, is_local)

    if scope in ("local", "all"):
        for city_name, base_url in CRAIGSLIST_DENVER_AREA.items():
            cities_to_search.append((city_name, base_url, True))
    if scope in ("shipping", "all"):
        for city_name, base_url in CRAIGSLIST_SHIPPING_CITIES.items():
            cities_to_search.append((city_name, base_url, False))

    if not cities_to_search:
        return json.dumps({"error": f"Invalid scope '{scope}'. Use 'local', 'shipping', or 'all'."})

    all_listings = []
    cities_searched = []
    cities_failed = []

    for i, (city_name, base_url, is_local) in enumerate(cities_to_search):
        results = _craigslist_search_city(
            base_url, query, city_name, is_local,
            category=category, min_price=min_price, max_price=max_price,
            max_results=max_results_per_city,
        )

        if results:
            # Enrich with GPU model
            for listing in results:
                model = _extract_gpu_model(listing.get("title", ""))
                if model:
                    listing["gpu_model"] = model
            all_listings.extend(results)
            cities_searched.append(f"{city_name} ({len(results)} results)")
        else:
            cities_failed.append(city_name)

        # Rate limit between cities (skip after last)
        if i < len(cities_to_search) - 1:
            time.sleep(random.uniform(1.5, 3.0))

    # Sort by price (cheapest first), listings without price at end
    all_listings.sort(key=lambda x: (x.get("price") is None, x.get("price", 999999)))

    summary = {
        "total_listings": len(all_listings),
        "cities_searched": cities_searched,
        "cities_with_no_results": cities_failed,
        "listings": all_listings,
    }
    return json.dumps(summary, indent=2)


# ── Cross-Platform Flow Tools ─────────────────────────────────────────────────
# These tools implement LOOPING agent call patterns — they iterate across
# multiple data sources (platforms, cities) to aggregate and compare results.
# When the LLM calls these tools, it should understand that the tool is
# performing an internal loop and will return aggregated results from all
# sources in a single response.

@tool
def cross_platform_search(
    query: str,
    platforms: str = "all",
    min_price: float = -1,
    max_price: float = -1,
    condition: str = "",
    max_results_per_platform: int = 15,
) -> str:
    """Search across eBay, Amazon, and Craigslist in a single call.

    THIS IS A LOOPING FLOW TOOL. It internally loops through each requested
    platform, collects results, and returns them aggregated. The loop includes
    rate-limiting delays between platforms. You are calling ONE tool but getting
    results from MULTIPLE sources.

    Args:
        query: Search terms (e.g. 'RTX 3060', 'mechanical keyboard').
        platforms: Comma-separated list or 'all'. Options: ebay, amazon, craigslist.
                   Example: 'ebay,amazon' or 'all'.
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        condition: Condition filter for eBay (new, used, refurbished). Ignored by others.
        max_results_per_platform: Max listings per platform.
    """
    platform_list = [p.strip().lower() for p in platforms.split(",")]
    if "all" in platform_list:
        platform_list = ["ebay", "amazon", "craigslist"]

    aggregated: dict = {
        "query": query,
        "platforms_searched": [],
        "total_listings": 0,
        "results": {},
    }

    for i, platform in enumerate(platform_list):
        if platform == "ebay":
            try:
                raw = ebay_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "condition": condition,
                    "max_results": max_results_per_platform,
                })
                listings = json.loads(raw)
                for listing in listings:
                    listing["platform"] = "ebay"
                    listing["fulfillment"] = "shipping"
                    model = _extract_gpu_model(listing.get("title", ""))
                    if model:
                        listing["gpu_model"] = model
                aggregated["results"]["ebay"] = listings
                aggregated["platforms_searched"].append(f"ebay ({len(listings)} results)")
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["ebay"] = [{"error": str(e)}]

        elif platform == "amazon":
            try:
                raw = amazon_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "max_results": max_results_per_platform,
                })
                listings = json.loads(raw)
                for listing in listings:
                    listing["platform"] = "amazon"
                    listing["fulfillment"] = "shipping"
                aggregated["results"]["amazon"] = listings
                aggregated["platforms_searched"].append(f"amazon ({len(listings)} results)")
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["amazon"] = [{"error": str(e)}]

        elif platform == "craigslist":
            try:
                raw = craigslist_multi_search.invoke({
                    "query": query,
                    "scope": "all",
                    "min_price": int(min_price) if min_price >= 0 else -1,
                    "max_price": int(max_price) if max_price >= 0 else -1,
                    "max_results_per_city": max(3, max_results_per_platform // 5),
                })
                cl_data = json.loads(raw)
                listings = cl_data.get("listings", [])
                for listing in listings:
                    listing["platform"] = "craigslist"
                aggregated["results"]["craigslist"] = listings
                aggregated["platforms_searched"].append(
                    f"craigslist ({len(listings)} results across {len(cl_data.get('cities_searched', []))} cities)"
                )
                aggregated["total_listings"] += len(listings)
            except Exception as e:
                aggregated["results"]["craigslist"] = [{"error": str(e)}]

        # Rate limit between platforms
        if i < len(platform_list) - 1:
            time.sleep(random.uniform(2.0, 4.0))

    return json.dumps(aggregated, indent=2)


@tool
def deal_finder(
    query: str,
    platforms: str = "all",
    min_price: float = -1,
    max_price: float = -1,
    condition: str = "used",
    threshold_pct: float = 20.0,
) -> str:
    """Find deals by searching multiple platforms, grouping by product model,
    computing median prices, and flagging listings priced significantly below median.

    THIS IS A LOOPING FLOW TOOL. It performs a multi-step pipeline:
      1. LOOP through platforms (eBay deep scan, Amazon, Craigslist multi-city)
      2. Aggregate all listings
      3. Group by extracted product model
      4. Compute per-group median price
      5. Flag listings priced >= threshold_pct below their group median
      6. Return deals sorted by savings percentage

    The entire pipeline runs in a single tool call. Results come back as a
    structured deal report ready to present to the user.

    Args:
        query: Search terms (e.g. 'RTX 3060 GPU', 'used ThinkPad').
        platforms: Comma-separated list or 'all'. Options: ebay, amazon, craigslist.
        min_price: Minimum price filter. -1 to skip.
        max_price: Maximum price filter. -1 to skip.
        condition: Condition filter for eBay (new, used, refurbished).
        threshold_pct: Minimum percentage below median to flag as a deal.
                       Default 20 means listing must be >=20% below median.
    """
    import statistics

    platform_list = [p.strip().lower() for p in platforms.split(",")]
    if "all" in platform_list:
        platform_list = ["ebay", "amazon", "craigslist"]

    all_listings: list[dict] = []
    platforms_searched = []

    # ── Step 1: Loop through platforms and collect listings ──
    for i, platform in enumerate(platform_list):
        if platform == "ebay":
            try:
                raw = ebay_deep_scan.invoke({
                    "query": query,
                    "condition": condition,
                    "min_price": min_price,
                    "max_price": max_price,
                    "pages": 3,
                    "max_results": 100,
                })
                listings = json.loads(raw)
                for lst in listings:
                    lst["platform"] = "ebay"
                    lst["fulfillment"] = "shipping"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0) + lst.get("shipping_cost", 0)
                all_listings.extend(listings)
                platforms_searched.append(f"ebay ({len(listings)} listings, 3-page deep scan)")
            except Exception as e:
                platforms_searched.append(f"ebay (error: {e})")

        elif platform == "amazon":
            try:
                raw = amazon_search.invoke({
                    "query": query,
                    "min_price": min_price,
                    "max_price": max_price,
                    "max_results": 30,
                })
                listings = json.loads(raw)
                for lst in listings:
                    lst["platform"] = "amazon"
                    lst["fulfillment"] = "shipping"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0) + lst.get("shipping_cost", 0)
                    if "model" not in lst and "gpu_model" in lst:
                        lst["model"] = lst["gpu_model"]
                    elif "model" not in lst:
                        lst["model"] = _extract_gpu_model(lst.get("title", ""))
                all_listings.extend(listings)
                platforms_searched.append(f"amazon ({len(listings)} listings)")
            except Exception as e:
                platforms_searched.append(f"amazon (error: {e})")

        elif platform == "craigslist":
            try:
                raw = craigslist_multi_search.invoke({
                    "query": query,
                    "scope": "all",
                    "min_price": int(min_price) if min_price >= 0 else -1,
                    "max_price": int(max_price) if max_price >= 0 else -1,
                    "max_results_per_city": 5,
                })
                cl_data = json.loads(raw)
                listings = cl_data.get("listings", [])
                for lst in listings:
                    lst["platform"] = "craigslist"
                    if "total_cost" not in lst:
                        lst["total_cost"] = lst.get("price", 0)
                    if "model" not in lst and "gpu_model" in lst:
                        lst["model"] = lst["gpu_model"]
                    elif "model" not in lst:
                        lst["model"] = _extract_gpu_model(lst.get("title", ""))
                all_listings.extend(listings)
                n_cities = len(cl_data.get("cities_searched", []))
                platforms_searched.append(f"craigslist ({len(listings)} listings across {n_cities} cities)")
            except Exception as e:
                platforms_searched.append(f"craigslist (error: {e})")

        # Rate limit between platforms
        if i < len(platform_list) - 1:
            time.sleep(random.uniform(2.0, 4.0))

    # ── Step 2: Group by model ──
    groups: dict[str, list[dict]] = {}
    ungrouped = []
    for lst in all_listings:
        model = lst.get("model", "")
        if model:
            groups.setdefault(model, []).append(lst)
        else:
            ungrouped.append(lst)

    # ── Step 3: Compute medians and find deals ──
    deals = []
    group_stats = {}

    for model, items in groups.items():
        prices = [x["total_cost"] for x in items if x.get("total_cost", 0) > 0]
        if len(prices) < 3:
            group_stats[model] = {
                "count": len(items),
                "note": "Too few listings for reliable comparison (need >=3)",
            }
            continue

        median_price = statistics.median(prices)
        group_stats[model] = {
            "count": len(items),
            "median_price": round(median_price, 2),
            "min_price": round(min(prices), 2),
            "max_price": round(max(prices), 2),
        }

        threshold = median_price * (1 - threshold_pct / 100)
        for item in items:
            total = item.get("total_cost", 0)
            if total > 0 and total <= threshold:
                pct_below = round((1 - total / median_price) * 100, 1)
                savings = round(median_price - total, 2)
                deals.append({
                    "model": model,
                    "title": item.get("title", ""),
                    "total_cost": total,
                    "median_price": round(median_price, 2),
                    "pct_below_median": pct_below,
                    "savings": savings,
                    "platform": item.get("platform", ""),
                    "fulfillment": item.get("fulfillment", ""),
                    "url": item.get("url", ""),
                })

    # Sort deals by savings percentage (best deals first)
    deals.sort(key=lambda x: x["pct_below_median"], reverse=True)

    report = {
        "query": query,
        "platforms_searched": platforms_searched,
        "total_listings_analyzed": len(all_listings),
        "models_found": len(groups),
        "ungrouped_listings": len(ungrouped),
        "group_statistics": group_stats,
        "deals_found": len(deals),
        "threshold": f">={threshold_pct}% below median",
        "deals": deals,
    }

    return json.dumps(report, indent=2)


# ── Enrichment Pipeline ──────────────────────────────────────────────────────

@tool
def enrichment_pipeline(
    data: str,
    goal: str,
    max_iterations: int = 5,
    eval_model: str = "qwen3:4b",
) -> str:
    """Iteratively enrich data by adding new dimensions/considerations using an LLM eval loop.

    THIS IS A LOOPING FLOW TOOL. It runs an internal LLM-evaluated loop:
      1. Send current data + goal to a small eval model
      2. Eval model adds a new enrichment dimension OR signals done
      3. Repeat until done or max_iterations reached

    Use this for multi-step enrichment pipelines where each pass adds a new
    consideration (pricing context, quality scores, comparisons, categories, etc.)

    Args:
        data: Input data to enrich. JSON string from a prior tool call, or raw text.
        goal: Natural language description of what enrichment dimensions to add.
              Example: 'Add price-to-performance ratings, flag vague descriptions,
              categorize by seller type'
        max_iterations: Maximum loop iterations (hard cap). Default 5.
        eval_model: Ollama model for loop evaluation. Default 'qwen3:4b'.
    """
    if not data or not data.strip():
        return json.dumps({"status": "error", "message": "Empty data input. Provide data to enrich."})

    # Check eval model availability
    try:
        eval_llm = ChatOllama(
            model=eval_model,
            temperature=0,
            base_url="http://localhost:11434",
        )
    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to initialize eval model '{eval_model}': {e}. Run: ollama pull {eval_model}",
        })

    system_prompt = """You are a data enrichment engine. Your job is to iteratively add new dimensions/considerations to data until the goal is fully satisfied.

Respond ONLY with valid JSON (no markdown fences, no explanation outside JSON).

If there are more dimensions to add, respond with:
{"action": "enrich", "dimension": "short_name", "description": "what you added and why", "enriched_data": <the full data with the new dimension merged in>}

If the goal is fully satisfied, respond with:
{"action": "done", "reasoning": "why all requested dimensions are complete"}"""

    current_data = data
    iteration_log = []
    consecutive_failures = 0

    for iteration in range(1, max_iterations + 1):
        # Truncate if too large for small model context
        display_data = current_data
        if len(current_data) > 4000:
            display_data = current_data[:4000]
            iteration_log.append({
                "iteration": iteration,
                "warning": f"Data truncated from {len(current_data)} to 4000 chars for eval model",
            })

        log_summary = "None yet" if not iteration_log else json.dumps(
            [e for e in iteration_log if "dimension" in e], indent=2
        )

        user_prompt = f"""GOAL: {goal}

CURRENT DATA:
{display_data}

PREVIOUS ITERATIONS:
{log_summary}

Iteration {iteration} of {max_iterations}. Add the next enrichment dimension, or signal done."""

        try:
            result = eval_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ])
            response_text = result.content.strip()

            # Strip markdown fences if present
            fence_match = re.match(r"^```(?:json)?\s*\n?(.*?)\n?\s*```$", response_text, re.DOTALL)
            if fence_match:
                response_text = fence_match.group(1).strip()

            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": "Malformed JSON from eval model",
                "raw_response": response_text[:200] if 'response_text' in dir() else "no response",
            })
            if consecutive_failures >= 2:
                break
            continue
        except Exception as e:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": f"Eval model call failed: {e}",
            })
            if consecutive_failures >= 2:
                break
            continue

        # Reset failure counter on success
        consecutive_failures = 0

        action = parsed.get("action", "")

        if action == "done":
            iteration_log.append({
                "iteration": iteration,
                "action": "done",
                "reasoning": parsed.get("reasoning", ""),
            })
            break

        elif action == "enrich":
            enriched = parsed.get("enriched_data")
            if enriched is not None:
                current_data = json.dumps(enriched, indent=2) if not isinstance(enriched, str) else enriched
            iteration_log.append({
                "iteration": iteration,
                "action": "enrich",
                "dimension": parsed.get("dimension", "unknown"),
                "description": parsed.get("description", ""),
            })

        else:
            consecutive_failures += 1
            iteration_log.append({
                "iteration": iteration,
                "error": f"Unknown action '{action}' from eval model",
            })
            if consecutive_failures >= 2:
                break

    # Determine exit reason
    if consecutive_failures >= 2:
        exit_reason = "consecutive_failures"
    elif iteration_log and iteration_log[-1].get("action") == "done":
        exit_reason = "llm_done"
    else:
        exit_reason = "max_iterations"

    # Parse final data for clean output
    try:
        final_data = json.loads(current_data)
    except (json.JSONDecodeError, TypeError):
        final_data = current_data

    report = {
        "status": "completed",
        "iterations_used": len([e for e in iteration_log if e.get("action") in ("enrich", "done") or "error" in e]),
        "max_iterations": max_iterations,
        "exit_reason": exit_reason,
        "iteration_log": iteration_log,
        "enriched_data": final_data,
    }

    return json.dumps(report, indent=2)


# ── Registry ─────────────────────────────────────────────────────────────────

ALL_TOOLS = [
    read_file,
    file_info,
    list_dir,
    tree,
    write_file,
    append_file,
    replace_in_file,
    insert_at_line,
    delete_lines,
    copy_file,
    move_file,
    delete_file,
    make_dir,
    grep,
    find_files,
    find_definition,
    web_search,
    fetch_url,
    ebay_search,
    ebay_sold_search,
    ebay_deep_scan,
    amazon_search,
    craigslist_search,
    craigslist_multi_search,
    cross_platform_search,
    deal_finder,
    enrichment_pipeline,
]
