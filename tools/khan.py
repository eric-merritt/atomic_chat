"""Khan Academy scraping tools.

Three tools following the course → unit → lesson hierarchy:
  khan_ls_courses     → lists enrolled courses
  khan_unit_fetch     → unit description + lesson cards
  khan_lesson_scrape  → video transcript or article paragraphs
"""

import json
import os
import re
import time
import urllib.parse
from pathlib import Path

import bs4 as beautifulsoup
import json5

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry

# ── Shared browser fetch ────────────────────────────────────────────────────

_browser_driver = None


def _get_driver():
    global _browser_driver
    if _browser_driver is not None:
        return _browser_driver
    from selenium import webdriver
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service

    gd = os.environ.get("GECKODRIVER_PATH", "/home/ermer/.local/bin/geckodriver")
    opts = Options()
    opts.add_argument("--headless")
    _browser_driver = webdriver.Firefox(
        service=Service(gd), options=opts,
    )
    _browser_driver.set_page_load_timeout(30)
    return _browser_driver


def _fetch(url: str, wait: float = 5) -> tuple[str, str | None]:
    """Fetch a page via headless browser. Returns (raw_html, error)."""
    try:
        driver = _get_driver()
    except Exception as e:
        return "", f"No browser: {e}"
    try:
        driver.get(url)
        time.sleep(wait)
        return driver.page_source, None
    except Exception as e:
        return "", f"Fetch failed: {e}"


def _soup(raw_html: str) -> beautifulsoup.BeautifulSoup:
    return beautifulsoup.BeautifulSoup(raw_html, "html.parser")


# ── khan_ls_courses ─────────────────────────────────────────────────────────

@register_tool("khan_ls_courses")
class KhanListCourses(BaseTool):
    description = "List the courses on the user's Khan Academy dashboard. Returns a dict of course name → URL."
    parameters = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Dashboard URL. Default: https://www.khanacademy.org/profile/me/courses",
            },
        },
        "required": [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params) if params else {}
        url = p.get("url", "https://www.khanacademy.org/profile/me/courses")

        raw, err = _fetch(url, wait=5)
        if err:
            return tool_result(error=err)

        s = _soup(raw)
        dashboard = s.find("div", attrs={"data-testid": "courses-dashboard"})
        if not dashboard:
            return tool_result(error="No courses dashboard found — are cookies set?")

        courses: dict = {}
        idx = 0
        for li in dashboard.find_all("li"):
            h3 = li.find("h3")
            if not h3:
                continue
            name = h3.get_text(strip=True)
            see_all = li.find("a", href=True)
            course_url = see_all["href"] if see_all else ""

            # Extract topics
            topics: list[dict] = []
            for a in li.find_all("a", attrs={"aria-label": True, "href": True}):
                label = a["aria-label"].strip()
                href = a["href"]
                if label and href and not label.startswith(("See all", "Resume")):
                    full = href if href.startswith("http") else f"https://www.khanacademy.org{href}"
                    topics.append({"name": label, "url": full})

            key = f"course_{idx}"
            courses[key] = {"name": name, "url": course_url, "topics": topics}
            idx += 1

        return tool_result(data={"courses": courses})


# ── khan_unit_fetch ─────────────────────────────────────────────────────────

@register_tool("khan_unit_fetch")
class KhanUnitFetch(BaseTool):
    description = (
        "Fetch a Khan Academy unit page (e.g. /science/ap-biology/chemistry-of-life). "
        "Returns unit description and list of lesson cards with name, URL, and type (video/article)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Unit URL (from khan_ls_courses output)."},
        },
        "required": ["url"],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p["url"]

        raw, err = _fetch(url, wait=4)
        if err:
            return tool_result(error=err)

        s = _soup(raw)

        # Unit description: h2 "About this unit" → sibling span → p
        about = s.find("h2", string=lambda t: t and "About this unit" in t)
        description = ""
        if about:
            sib = about.find_next_sibling("span")
            if sib:
                p_el = sib.find("p")
                if p_el:
                    description = p_el.get_text(strip=True)

        # Lesson cards
        lessons: list[dict] = []
        for card in s.find_all(attrs={"data-testid": "lesson-card"}):
            h2_el = card.find("h2")
            if not h2_el:
                continue
            a_el = h2_el.find("a", href=True)
            if not a_el:
                continue
            name = a_el.get_text(strip=True) or a_el.get("aria-label", "")
            href = a_el["href"]
            full = href if href.startswith("http") else f"https://www.khanacademy.org{href}"
            lessons.append({"name": name, "url": full})

        return tool_result(data={
            "unit_url": url,
            "description": description,
            "lessons": lessons,
        })


# ── khan_lesson_scrape ──────────────────────────────────────────────────────

def _detect_page_type(s) -> str:
    if s.find("button", attrs={"data-testid": "video-play-button"}):
        return "video"
    if s.find(attrs={"data-testid": "content-library-content-title"}):
        return "article"
    return "unknown"


def _extract_video_transcript(s) -> str:
    """Extract transcript from the video tab.

    Structure: button#videoTabTranscript-tab → div#videoTabTranscript-content
    → ul[itemprop="transcript"] → li → button > span (text spans).
    """
    # The tab content is typically already rendered in the DOM
    transcript_ul = s.find("ul", attrs={"itemprop": "transcript"})
    if not transcript_ul:
        return ""

    segments: list[str] = []
    for li in transcript_ul.find_all("li"):
        btn = li.find("button")
        if not btn:
            continue
        # Skip the timestamp span, get the text spans
        spans = btn.find_all("span")
        for sp in spans:
            if sp.get("class") and "_tnp8yqs" in sp.get("class", []):
                continue  # skip timestamp
            txt = sp.get_text(strip=True)
            if txt:
                segments.append(txt)

    return " ".join(segments)


def _extract_article_content(s) -> tuple[str, list[str]]:
    """Extract title and paragraphs from an article page.

    Title from h1[data-testid="content-library-content-title"].
    Paragraphs from div.paragraph with h2 children or loose plaintext.
    """
    title_el = s.find(attrs={"data-testid": "content-library-content-title"})
    title = title_el.get_text(strip=True) if title_el else ""

    paragraphs: list[str] = []
    for div in s.find_all("div", class_="paragraph"):
        # Check for h2 children (sub-headings)
        for h2 in div.find_all("h2"):
            txt = h2.get_text(strip=True)
            if txt:
                paragraphs.append(txt)

        # Check for loose text nodes (not wrapped in p or other element)
        # Walk child nodes, collect text that isn't inside an h2/p/etc.
        parts: list[str] = []
        for child in div.children:
            if isinstance(child, beautifulsoup.NavigableString):
                txt = str(child).strip()
                if txt and len(txt) > 20:
                    parts.append(txt)
            elif getattr(child, "name", None) in ("h2", "p", "ul", "ol"):
                pass  # handled above or skip
            elif getattr(child, "name", None):
                txt = child.get_text(strip=True)
                if txt and len(txt) > 20:
                    parts.append(txt)
        if parts:
            paragraphs.append(" ".join(parts))

    return title, paragraphs


def _find_next_lesson_link(s, current_url: str) -> str | None:
    """Find the 'next' link from the content library footer.

    Structure: div[data-testid="content-library-footer"]
    → div → div (3rd child) → div (1st child) → a
    """
    footer = s.find(attrs={"data-testid": "content-library-footer"})
    if not footer:
        return None

    divs = footer.find_all("div", recursive=True)
    if len(divs) >= 4:
        # Try the described structure: 3rd div → 1st div → a
        target = divs[2]  # 3rd child (0-indexed)
        inner = target.find("div")
        if inner:
            a = inner.find("a", href=True)
            if a:
                href = a["href"]
                return href if href.startswith("http") else f"https://www.khanacademy.org{href}"

    # Fallback: look for any "next" navigation link
    for a in footer.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(strip=True).lower()
        if "next" in label or "continue" in label:
            return href if href.startswith("http") else f"https://www.khanacademy.org{href}"

    return None


@register_tool("khan_lesson_scrape")
class KhanLessonScrape(BaseTool):
    description = (
        "Scrape a Khan Academy lesson page. Detects video vs article type. "
        "Video pages: extracts transcript. Article pages: extracts title and paragraphs. "
        "Also returns the URL of the next lesson piece if available."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Lesson URL."},
        },
        "required": ["url"],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        url = p["url"]

        raw, err = _fetch(url, wait=4)
        if err:
            return tool_result(error=err)

        s = _soup(raw)
        page_type = _detect_page_type(s)
        next_url = _find_next_lesson_link(s, url)

        if page_type == "video":
            transcript = _extract_video_transcript(s)
            if not transcript:
                return tool_result(data={
                    "url": url,
                    "type": "video",
                    "transcript": "",
                    "message": "No transcript found. Try waiting longer or clicking the transcript tab first.",
                    "next_url": next_url,
                })
            return tool_result(data={
                "url": url,
                "type": "video",
                "transcript": transcript,
                "next_url": next_url,
            })

        elif page_type == "article":
            title, paragraphs = _extract_article_content(s)
            return tool_result(data={
                "url": url,
                "type": "article",
                "title": title,
                "paragraphs": paragraphs,
                "next_url": next_url,
            })

        else:
            return tool_result(data={
                "url": url,
                "type": "unknown",
                "message": "Could not determine page type. No video-play-button or content-library-content-title found.",
                "next_url": next_url,
            })
