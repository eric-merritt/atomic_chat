"""Job posting search tools: Indeed search and detail fetch.

Primary source is Indeed. Tools share the `_web_session` from tools.web so
cookies set via www_set_cookies carry over (useful if Indeed presents an
interstitial that can be cleared by setting a trust cookie).
"""

import re
import json
import urllib.parse

import bs4 as beautifulsoup
import json5

from qwen_agent.tools.base import BaseTool, register_tool

from tools._output import tool_result, retry
from tools.web import _web_session, _strip_html_noise, _get_or_create_browser


INDEED_BASE = "https://www.indeed.com"


def _indeed_search_url(query: str, location: str, radius: int,
                       days_posted: int, remote: bool, start: int) -> str:
    params = {
        "q": query,
        "l": location,
        "radius": str(radius),
        "fromage": str(days_posted),
        "start": str(start),
    }
    if remote:
        # Indeed's "Remote" attribute filter; attr value is stable across their deploys
        params["sc"] = "0kf:attr(DSQF7);"
    return f"{INDEED_BASE}/jobs?" + urllib.parse.urlencode(params)


def _first_text(el, selectors: list[str]) -> str:
    """Return stripped text of the first matching selector, else ''."""
    for sel in selectors:
        found = el.select_one(sel)
        if found:
            txt = found.get_text(separator=" ", strip=True)
            if txt:
                return txt
    return ""


def _first_attr(el, selectors: list[str], attr: str) -> str:
    for sel in selectors:
        found = el.select_one(sel)
        if found and found.get(attr):
            return found.get(attr)
    return ""


def _parse_cards(html: str) -> list[dict]:
    """Parse Indeed results HTML into a list of job dicts.

    Tries structured selectors first (data-testid has been stable longer than
    class names), then falls back to any element carrying a data-jk attribute.
    """
    soup = beautifulsoup.BeautifulSoup(html, "html.parser")

    # Indeed renders each card inside a <div class="job_seen_beacon"> wrapping
    # an <a data-jk="..."> handle. Either works as the root scan.
    cards = soup.select("div.job_seen_beacon")
    if not cards:
        cards = soup.select("[data-testid='slider_item']")
    if not cards:
        # Last-resort: every element with a data-jk handle is a card root.
        seen = set()
        cards = []
        for a in soup.select("[data-jk]"):
            jk = a.get("data-jk")
            if jk and jk not in seen:
                seen.add(jk)
                # Climb to the nearest card-ish parent so company/location selectors resolve
                parent = a
                for _ in range(6):
                    if parent.parent:
                        parent = parent.parent
                cards.append(parent)

    jobs: list[dict] = []
    for card in cards:
        jk = _first_attr(card, ["a[data-jk]", "[data-jk]"], "data-jk")
        title = _first_text(card, [
            "h2 a span[title]",
            "h2.jobTitle span",
            "h2.jobTitle a",
            "[data-testid='job-title']",
        ])
        if not title:
            # Some variants hide title in aria-label
            lbl = _first_attr(card, ["h2 a", "a[data-jk]"], "aria-label")
            if lbl:
                title = lbl
        company = _first_text(card, [
            "[data-testid='company-name']",
            "span.companyName",
            ".company_location [data-testid='company-name']",
        ])
        location = _first_text(card, [
            "[data-testid='text-location']",
            "div.companyLocation",
            ".company_location [data-testid='text-location']",
        ])
        salary = _first_text(card, [
            "[data-testid='attribute_snippet_testid']",
            ".salary-snippet-container",
            ".metadata.salary-snippet-container",
        ])
        summary = _first_text(card, [
            "[data-testid='job-snippet']",
            "div.job-snippet",
        ])
        posted = _first_text(card, [
            "[data-testid='myJobsStateDate']",
            "span.date",
        ])
        url = f"{INDEED_BASE}/viewjob?jk={jk}" if jk else ""

        if not (title or jk):
            continue

        jobs.append({
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "posted": posted,
            "summary": summary,
            "url": url,
            "job_key": jk,
            "source": "indeed",
        })

    return jobs


@register_tool("jb_search")
class JobSearchTool(BaseTool):
    description = (
        "Search Indeed for job postings. Returns a compact list of {title, "
        "company, location, salary, posted, summary, url, job_key}. Use "
        "jb_fetch with a job_key or url to get the full description."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string",
                      "description": "Job title or keywords (e.g. 'purchaser', 'lighting project manager ITAR')."},
            "location": {"type": "string",
                         "description": "Location string Indeed accepts (e.g. 'Denver, CO', 'Remote'). Default: 'Denver, CO'."},
            "radius": {"type": "integer",
                       "description": "Search radius in miles. Default: 25."},
            "days_posted": {"type": "integer",
                            "description": "Only show jobs posted within N days. Default: 14."},
            "remote": {"type": "boolean",
                       "description": "Filter for Remote postings only. Default: false."},
            "max_results": {"type": "integer",
                            "description": "Max postings to return. Range 1-50. Default: 15."},
            "js": {"type": "boolean",
                   "description": "Use headless Firefox instead of requests. Use if Indeed returns a challenge page. Default: false."},
        },
        "required": ["query"],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = (p.get("query") or "").strip()
        if not query:
            return tool_result(error="query is required")
        location = (p.get("location") or "Denver, CO").strip()
        radius = max(0, min(100, int(p.get("radius", 25))))
        days_posted = max(1, min(60, int(p.get("days_posted", 14))))
        remote = bool(p.get("remote", False))
        max_results = max(1, min(50, int(p.get("max_results", 15))))
        js = bool(p.get("js", False))

        jobs: list[dict] = []
        # Indeed paginates by start=0,10,20,...
        for start in range(0, max_results, 10):
            url = _indeed_search_url(query, location, radius, days_posted, remote, start)
            try:
                if js:
                    driver = _get_or_create_browser()
                    driver.get(url)
                    import time
                    time.sleep(3)
                    html = driver.page_source
                else:
                    r = _web_session.get(url, timeout=20)
                    if r.status_code in (403, 429):
                        return tool_result(error=(
                            f"Indeed blocked the request ({r.status_code}). Retry with js=true, or set a trust "
                            "cookie via www_set_cookies and retry."
                        ))
                    r.raise_for_status()
                    html = r.text
            except Exception as e:
                return tool_result(error=f"Indeed fetch failed at start={start}: {e}")

            # Detect in-body challenge pages (200 response with CAPTCHA)
            low = html.lower()
            if ("captcha" in low or "unusual activity" in low) and not js:
                return tool_result(error=(
                    "Indeed returned a challenge page. Retry with js=true, or set a trust cookie "
                    "via www_set_cookies and retry."
                ))

            page_jobs = _parse_cards(html)
            if not page_jobs:
                break
            jobs.extend(page_jobs)
            if len(jobs) >= max_results:
                break

        # Dedup by job_key (pagination can repeat)
        seen: set[str] = set()
        unique: list[dict] = []
        for j in jobs:
            key = j.get("job_key") or f"{j.get('title')}|{j.get('company')}"
            if key in seen:
                continue
            seen.add(key)
            unique.append(j)
            if len(unique) >= max_results:
                break

        return tool_result(data={
            "query": query,
            "location": location,
            "remote": remote,
            "count": len(unique),
            "jobs": unique,
        })


@register_tool("jb_fetch")
class JobFetchTool(BaseTool):
    description = (
        "Fetch the full description of a single Indeed posting by job_key or full url. "
        "Returns {title, company, location, salary, description, url}."
    )
    parameters = {
        "type": "object",
        "properties": {
            "job_key": {"type": "string",
                        "description": "Indeed job key (the data-jk value from jb_search results)."},
            "url": {"type": "string",
                    "description": "Alternative to job_key — full https://www.indeed.com/viewjob?jk=... URL."},
            "js": {"type": "boolean",
                   "description": "Use headless Firefox instead of requests. Default: false."},
        },
        "required": [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        job_key = (p.get("job_key") or "").strip()
        url = (p.get("url") or "").strip()
        js = bool(p.get("js", False))

        if not url and job_key:
            url = f"{INDEED_BASE}/viewjob?jk={urllib.parse.quote(job_key)}"
        if not url:
            return tool_result(error="Provide job_key or url")
        if not url.startswith(("http://", "https://")):
            return tool_result(error="url must start with http:// or https://")

        try:
            if js:
                driver = _get_or_create_browser()
                driver.get(url)
                import time
                time.sleep(3)
                html = driver.page_source
            else:
                r = _web_session.get(url, timeout=20)
                r.raise_for_status()
                html = r.text
        except Exception as e:
            return tool_result(error=f"Failed to fetch {url}: {e}")

        soup = beautifulsoup.BeautifulSoup(html, "html.parser")

        title = _first_text(soup, [
            "h1.jobsearch-JobInfoHeader-title",
            "[data-testid='jobsearch-JobInfoHeader-title']",
            "h1",
        ])
        company = _first_text(soup, [
            "[data-testid='inlineHeader-companyName']",
            "[data-company-name='true']",
            "div.jobsearch-InlineCompanyRating a",
        ])
        location = _first_text(soup, [
            "[data-testid='inlineHeader-companyLocation']",
            "div.jobsearch-JobInfoHeader-subtitle div",
        ])
        salary = _first_text(soup, [
            "#salaryInfoAndJobType span",
            "[data-testid='job-compensation']",
        ])
        desc_node = soup.select_one("#jobDescriptionText") or soup.select_one("[data-testid='jobsearch-JobComponent-description']")
        description = desc_node.get_text("\n", strip=True) if desc_node else ""

        if not (title or description):
            low = html.lower()
            if "captcha" in low or "unusual activity" in low:
                return tool_result(error="Indeed challenge page — retry with js=true or set trust cookies.")

        return tool_result(data={
            "url": url,
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "description": description,
        })
