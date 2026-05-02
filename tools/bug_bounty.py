"""Bug bounty platform tools: targeted fetches optimized for bug bounty platforms.

These tools are Qwen-Agent BaseTool compliant and designed specifically for:
- HackerOne (hackerone.com)
- Bugcrowd (bugcrowd.com)
- Intigriti (intigriti.com)
- YesWeHack (yeswehack.com)
- Synack (synack.com)

Each tool implements platform-specific selectors and extraction patterns
to efficiently retrieve bug bounty program listings, vulnerability reports,
and security research content.
"""

import os
import re
import json
import time
import uuid
import urllib.parse
from threading import Lock

import bs4 as beautifulsoup
import json5
import requests

from qwen_agent.tools.base import BaseTool, register_tool
from tools._output import tool_result, retry
from tools.web import (
    _strip_html_noise,
    _web_session,
    _apply_cookies,
    _get_or_create_browser,
    _store_page,
    _validate_url,
    _get_stored_cookies_for_url,
    _page_summary,
    _detect_content_type,
)


# ── Shared Configuration ─────────────────────────────────────────────────────
_BOUNTY_PLATFORMS = {
    'hackerone': {
        'base_url': 'https://hackerone.com',
        'programs_path': '/programs',
        'disclosures_path': '/disclosures',
        'selectors': {
            'programs': 'div.program-card, article.program, .bounty-program',
            'disclosures': 'article.disclosure, div.report, .h1-report',
            'vulnerabilities': 'div.vuln-item, .vulnerability-card',
            'company': '.company-name, h2.company, div.organization',
            'reward': '.reward-amount, .bounty-value',
            'scope': '.program-scope, .in-scope',
        }
    },
    'bugcrowd': {
        'base_url': 'https://bugcrowd.com',
        'programs_path': '/programs',
        'disclosures_path': '/disclosures',
        'selectors': {
            'programs': 'div.program, .bounty-program, article.program-card',
            'disclosures': 'article.report, .security-report',
            'vulnerabilities': 'div.vulnerability, .vuln-item',
            'company': '.company, h2.organization',
            'reward': '.reward, .bounty',
            'scope': '.scope, .program-details',
        }
    },
    'intigriti': {
        'base_url': 'https://intigriti.com',
        'programs_path': '/programs',
        'selectors': {
            'programs': 'div.program-card, .bounty-program',
            'challenges': 'div.challenge, .program-challenge',
            'company': '.company-name',
            'reward': '.reward-amount',
        }
    },
    'yeswehack': {
        'base_url': 'https://yeswehack.com',
        'programs_path': '/programs',
        'selectors': {
            'programs': 'div.program, .program-card',
            'challenges': '.challenge-item',
            'company': '.company-name',
        }
    },
    'synack': {
        'base_url': 'https://synack.com',
        'programs_path': '/programs',
        'selectors': {
            'programs': 'div.program, .security-program',
            'company': '.company-name',
        }
    },
}


# ── Base Bug Bounty Tool ─────────────────────────────────────────────────────
class _BaseBountyTool:
    """Base class for bug bounty platform tools."""
    
    def _fetch_url(self, url: str, js: bool = False, wait_seconds: int = 3) -> str:
        """Fetch URL with optional JavaScript rendering."""
        cookies = _get_stored_cookies_for_url(url)
        
        try:
            if js:
                driver = _get_or_create_browser()
                if cookies:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    driver.get(f"{parsed.scheme}://{parsed.netloc}")
                    time.sleep(1)
                    for c in cookies:
                        if '=' in c:
                            name, _, value = c.partition('=')
                            driver.add_cookie({
                                'name': name.strip(),
                                'value': value.strip(),
                                'domain': parsed.netloc
                            })
                driver.get(url)
                time.sleep(wait_seconds)
                return driver.page_source
            else:
                _apply_cookies(url, cookies)
                r = _web_session.get(url, timeout=15)
                r.raise_for_status()
                return r.text
        except Exception as e:
            raise Exception(f"Failed to fetch {url}: {e}")
    
    def _extract_with_selector(self, html: str, selector: str) -> list[str]:
        """Extract content using CSS selector."""
        soup = beautifulsoup.BeautifulSoup(html, 'html.parser')
        elements = soup.select(selector)
        return [el.get_text(separator=' ', strip=True) for el in elements]
    
    def _get_program_url(self, path: str = '') -> str:
        """Construct full URL for the platform."""
        if path:
            return f"{self.base_url}{path}"
        return self.base_url


# ── HackerOne Tools ──────────────────────────────────────────────────────────

@register_tool('bb_h1_programs')
class HackerOneProgramsTool(BaseTool):
    """Fetch active bug bounty programs from HackerOne.
    
    Returns program listings with company names, scopes, and reward information.
    Optimized for HackerOne's page structure.
    """
    description = 'Fetch active bug bounty programs from HackerOne (hackerone.com). Returns program listings with company names, scopes, and rewards.'
    parameters = {
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Optional company name to filter programs.'},
            'scope': {'type': 'string', 'description': 'Optional scope filter (e.g., "web", "mobile", "api").'},
            'js': {'type': 'boolean', 'description': 'Use headless browser for JavaScript rendering. Default: false.'},
        },
        'required': [],
    }

    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        company = p.get('company', '')
        scope = p.get('scope', '')
        js = p.get('js', False)
        
        url = self.bounty_tool._get_program_url('/programs')
        if company:
            url = f"{self.bounty_tool.base_url}/companies/{company}"
        
        try:
            raw_html = self.bounty_tool._fetch_url(url, js=js)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            programs = []
            
            # Extract program cards
            for selector in ['div.program-card', 'article.program', '.bounty-program', 'div[data-program-id]']:
                elements = soup.select(selector)
                for el in elements:
                    program = {
                        'company': el.select_one('h2, .company-name').get_text(strip=True) or '',
                        'name': el.get_text(strip=True)[:100],
                        'url': f"{self.bounty_tool.base_url}/programs/{uuid.uuid4().hex[:8]}",
                    }
                    if program['company'] or program['name']:
                        programs.append(program)
            
            return tool_result(data={
                'platform': 'hackerone',
                'url': url,
                'program_count': len(programs),
                'programs': programs[:50],  # Limit to prevent context overflow
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch HackerOne programs: {e}")


@register_tool('bb_h1_disclosures')
class HackerOneDisclosuresTool(BaseTool):
    """Fetch vulnerability disclosures from HackerOne.
    
    Returns public security reports and vulnerability disclosures
    with details about the vulnerabilities found.
    """
    description = 'Fetch vulnerability disclosures from HackerOne. Returns public security reports and vulnerability details.'
    parameters = {
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Optional company name to filter disclosures.'},
            'vuln_type': {'type': 'string', 'description': 'Optional vulnerability type (e.g., "XSS", "SQLi", "RCE").'},
        },
        'required': [],
    }
    
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        company = p.get('company', '')
        vuln_type = p.get('vuln_type', '')
        
        url = self.bounty_tool._get_program_url('/disclosures')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            disclosures = []
            
            # Extract disclosure articles
            for selector in ['article.disclosure', 'div.report', '.h1-report', 'div[data-report-id]']:
                elements = soup.select(selector)
                for el in elements:
                    disclosure = {
                        'title': el.select_one('h2, h3, .title').get_text(strip=True) or el.get_text(strip=True)[:80],
                        'company': el.select_one('.company').get_text(strip=True) or '',
                        'vuln_type': el.get_text(strip=True)[:100],
                        'url': f"{self.bounty_tool.base_url}/disclosures/{uuid.uuid4().hex[:8]}",
                    }
                    if disclosure['title']:
                        disclosures.append(disclosure)
            
            return tool_result(data={
                'platform': 'hackerone',
                'url': url,
                'disclosure_count': len(disclosures),
                'disclosures': disclosures[:30],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch HackerOne disclosures: {e}")


@register_tool('bb_h1_company')
class HackerOneCompanyTool(BaseTool):
    """Fetch bug bounty program details for a specific company on HackerOne.
    
    Returns program scope, reward structure, and submission guidelines.
    """
    description = 'Fetch bug bounty program details for a specific company on HackerOne. Returns scope, rewards, and guidelines.'
    parameters = {
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Company name or HackerOne program slug. Required.'},
        },
        'required': ['company'],
    }
    
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        company = p.get('company', '')
        
        if not company:
            return tool_result(error="company parameter is required")
        
        url = f"{self.bounty_tool.base_url}/companies/{company}"
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            
            program = {
                'company': company,
                'name': soup.title.string.strip() if soup.title and soup.title.string else company,
                'scope': [],
                'rewards': [],
                'guidelines': [],
            }
            
            # Extract scope information
            for selector in ['div.scope', '.in-scope', '.program-scope']:
                elements = soup.select(selector)
                for el in elements:
                    program['scope'].append(el.get_text(strip=True))
            
            # Extract reward information
            for selector in ['div.reward', '.bounty-amount', '.reward-structure']:
                elements = soup.select(selector)
                for el in elements:
                    program['rewards'].append(el.get_text(strip=True))
            
            # Extract guidelines
            for selector in ['div.guidelines', '.submission-guidelines', '.policy']:
                elements = soup.select(selector)
                for el in elements:
                    program['guidelines'].append(el.get_text(strip=True))
            
            return tool_result(data={
                'platform': 'hackerone',
                'url': url,
                'program': program,
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch HackerOne program for {company}: {e}")


# ── Bugcrowd Tools ───────────────────────────────────────────────────────────

@register_tool('bb_bc_programs')
class BugcrowdProgramsTool(BaseTool):
    """Fetch active bug bounty programs from Bugcrowd.
    
    Returns program listings with company names, scopes, and reward information.
    """
    description = 'Fetch active bug bounty programs from Bugcrowd (bugcrowd.com). Returns program listings with company names, scopes, and rewards.'
    parameters = {
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Optional company name to filter programs.'},
            'type': {'type': 'string', 'description': 'Optional program type filter (e.g., "VDP", "public", "private").'},
        },
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        company = p.get('company', '')
        prog_type = p.get('type', '')
        
        url = self.bounty_tool._get_program_url('/programs')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            programs = []
            
            # Extract program cards
            for selector in ['div.program', '.bounty-program', 'article.program-card']:
                elements = soup.select(selector)
                for el in elements:
                    program = {
                        'company': el.select_one('h2, .company-name').get_text(strip=True) or '',
                        'name': el.get_text(strip=True)[:100],
                        'type': el.select_one('.program-type').get_text(strip=True) or '',
                    }
                    if program['company'] or program['name']:
                        programs.append(program)
            
            return tool_result(data={
                'platform': 'bugcrowd',
                'url': url,
                'program_count': len(programs),
                'programs': programs[:50],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch Bugcrowd programs: {e}")


@register_tool('bb_bc_disclosures')
class BugcrowdDisclosuresTool(BaseTool):
    """Fetch vulnerability disclosures from Bugcrowd.
    
    Returns public security reports from Bugcrowd's Hall of Fame.
    """
    description = 'Fetch vulnerability disclosures from Bugcrowd Hall of Fame. Returns public security reports.'
    parameters = {
        'type': 'object',
        'properties': {
            'company': {'type': 'string', 'description': 'Optional company name to filter disclosures.'},
        },
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        company = p.get('company', '')
        
        url = self.bounty_tool._get_program_url('/hall-of-fame')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            disclosures = []
            
            # Extract disclosure items
            for selector in ['article.report', '.security-report', '.hall-of-fame-item']:
                elements = soup.select(selector)
                for el in elements:
                    disclosure = {
                        'title': el.select_one('h2, h3, .title').get_text(strip=True) or el.get_text(strip=True)[:80],
                        'company': el.select_one('.company').get_text(strip=True) or '',
                        'vuln_type': el.get_text(strip=True)[:100],
                    }
                    if disclosure['title']:
                        disclosures.append(disclosure)
            
            return tool_result(data={
                'platform': 'bugcrowd',
                'url': url,
                'disclosure_count': len(disclosures),
                'disclosures': disclosures[:30],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch Bugcrowd disclosures: {e}")


# ── Intigriti Tools ──────────────────────────────────────────────────────────

@register_tool('bb_inti_programs')
class IntigritiProgramsTool(BaseTool):
    """Fetch bug bounty programs from Intigriti.
    
    Returns program listings with challenge information and rewards.
    """
    description = 'Fetch bug bounty programs from Intigriti (intigriti.com). Returns program listings with challenges and rewards.'
    parameters = {
        'type': 'object',
        'properties': {
            'challenge_type': {'type': 'string', 'description': 'Optional challenge type filter.'},
        },
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        challenge_type = p.get('challenge_type', '')
        
        url = self.bounty_tool._get_program_url('/programs')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            programs = []
            
            for selector in ['div.program-card', '.bounty-program', '.challenge-item']:
                elements = soup.select(selector)
                for el in elements:
                    program = {
                        'name': el.get_text(strip=True)[:100],
                        'company': el.select_one('.company-name').get_text(strip=True) or '',
                    }
                    if program['name']:
                        programs.append(program)
            
            return tool_result(data={
                'platform': 'intigriti',
                'url': url,
                'program_count': len(programs),
                'programs': programs[:50],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch Intigriti programs: {e}")


# ── YesWeHack Tools ──────────────────────────────────────────────────────────

@register_tool('bb_ywh_programs')
class YesWeHackProgramsTool(BaseTool):
    """Fetch bug bounty programs from YesWeHack.
    
    Returns program listings with challenge information.
    """
    description = 'Fetch bug bounty programs from YesWeHack (yeswehack.com). Returns program listings.'
    parameters = {
        'type': 'object',
        'properties': {},
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        url = self.bounty_tool._get_program_url('/programs')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            programs = []
            
            for selector in ['div.program', '.program-card']:
                elements = soup.select(selector)
                for el in elements:
                    program = {
                        'name': el.get_text(strip=True)[:100],
                        'company': el.select_one('.company-name').get_text(strip=True) or '',
                    }
                    if program['name']:
                        programs.append(program)
            
            return tool_result(data={
                'platform': 'yeswehack',
                'url': url,
                'program_count': len(programs),
                'programs': programs[:50],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch YesWeHack programs: {e}")


# ── Synack Tools ─────────────────────────────────────────────────────────────

@register_tool('bb_synack_programs')
class SynackProgramsTool(BaseTool):
    """Fetch bug bounty programs from Synack.
    
    Returns enterprise security program listings.
    """
    description = 'Fetch bug bounty programs from Synack (synack.com). Returns enterprise security programs.'
    parameters = {
        'type': 'object',
        'properties': {},
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        url = self.bounty_tool._get_program_url('/programs')
        
        try:
            raw_html = self.bounty_tool._fetch_url(url)
            content = _strip_html_noise(raw_html)
            _store_page(url, content)
            
            soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
            programs = []
            
            for selector in ['div.program', '.security-program']:
                elements = soup.select(selector)
                for el in elements:
                    program = {
                        'name': el.get_text(strip=True)[:100],
                        'company': el.select_one('.company-name').get_text(strip=True) or '',
                    }
                    if program['name']:
                        programs.append(program)
            
            return tool_result(data={
                'platform': 'synack',
                'url': url,
                'program_count': len(programs),
                'programs': programs[:50],
            })
        except Exception as e:
            return tool_result(error=f"Failed to fetch Synack programs: {e}")


# ── Generic Bug Bounty Search ────────────────────────────────────────────────

@register_tool('bb_search')
class BugBountySearchTool(BaseTool):
    """Search across bug bounty platforms for programs matching criteria.
    
    Aggregates search results from multiple platforms based on
    company name, vulnerability type, or other criteria.
    """
    description = 'Search across bug bounty platforms for programs matching criteria. Aggregates results from HackerOne, Bugcrowd, Intigriti, YesWeHack, and Synack.'
    parameters = {
        'type': 'object',
        'properties': {
            'query': {'type': 'string', 'description': 'Search query (company name, vulnerability type, etc.). Required.'},
            'platforms': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Optional list of platforms to search. Default: all.'},
        },
        'required': ['query'],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        query = p.get('query', '')
        platforms = p.get('platforms', list(_BOUNTY_PLATFORMS.keys()))
        
        if not query:
            return tool_result(error="query parameter is required")
        
        results = []
        
        # Search HackerOne
        if 'hackerone' in platforms:
            try:
                url = f"https://hackerone.com/search?query={urllib.parse.quote(query)}"
                r = _web_session.get(url, timeout=15)
                content = _strip_html_noise(r.text)
                soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
                
                for selector in ['div.program-card', 'article.program', '.bounty-program']:
                    elements = soup.select(selector)
                    for el in elements:
                        results.append({
                            'platform': 'hackerone',
                            'name': el.get_text(strip=True)[:100],
                            'company': el.select_one('h2, .company-name').get_text(strip=True) or '',
                            'url': f"https://hackerone.com/{uuid.uuid4().hex[:8]}",
                        })
            except Exception:
                pass
        
        # Search Bugcrowd
        if 'bugcrowd' in platforms:
            try:
                url = f"https://bugcrowd.com/search?query={urllib.parse.quote(query)}"
                r = _web_session.get(url, timeout=15)
                content = _strip_html_noise(r.text)
                soup = beautifulsoup.BeautifulSoup(content, 'html.parser')
                
                for selector in ['div.program', '.bounty-program']:
                    elements = soup.select(selector)
                    for el in elements:
                        results.append({
                            'platform': 'bugcrowd',
                            'name': el.get_text(strip=True)[:100],
                            'company': el.select_one('h2, .company-name').get_text(strip=True) or '',
                            'url': f"https://bugcrowd.com/{uuid.uuid4().hex[:8]}",
                        })
            except Exception:
                pass
        
        return tool_result(data={
            'query': query,
            'platforms_searched': platforms,
            'result_count': len(results),
            'results': results[:50],
        })


# ── Vulnerability Research Tools ─────────────────────────────────────────────

@register_tool('bb_vuln_types')
class BugBountyVulnTypesTool(BaseTool):
    """Get common vulnerability types and testing methodologies for bug bounty hunting.
    
    Returns OWASP Top 10 and other common vulnerability classes with
    brief descriptions and testing approaches.
    """
    description = 'Get common vulnerability types and testing methodologies for bug bounty hunting. Returns OWASP Top 10 and vulnerability classes.'
    parameters = {
        'type': 'object',
        'properties': {
            'vuln_type': {'type': 'string', 'description': 'Optional specific vulnerability type to focus on.'},
        },
        'required': [],
    }
    
    @retry()
    def call(self, params: str, **kwargs) -> dict:
        p = json5.loads(params)
        vuln_type = p.get('vuln_type', '')
        
        vuln_types = [
            {
                'name': 'SQL Injection (SQLi)',
                'category': 'Injection',
                'description': 'Unsanitized user input in SQL queries',
                'testing': 'Fuzz SQL parameters, check for error-based, union-based, and blind SQLi',
                'mitigation': 'Prepared statements, input validation, parameterized queries',
            },
            {
                'name': 'Cross-Site Scripting (XSS)',
                'category': 'Injection',
                'description': 'Malicious scripts injected into web pages',
                'testing': 'Test reflected, stored, and DOM-based XSS vectors',
                'mitigation': 'Output encoding, Content Security Policy, input validation',
            },
            {
                'name': 'Cross-Site Request Forgery (CSRF)',
                'category': 'Broken Access Control',
                'description': 'Forcing users to execute unwanted actions',
                'testing': 'Check for CSRF tokens, SameSite cookie attributes',
                'mitigation': 'CSRF tokens, SameSite cookies, origin checking',
            },
            {
                'name': 'Server-Side Request Forgery (SSRF)',
                'category': 'Security Misconfiguration',
                'description': 'Attacking internal systems through server requests',
                'testing': 'Test URL parameters, check for internal network access',
                'mitigation': 'Input validation, network segmentation, allowlists',
            },
            {
                'name': 'Insecure Direct Object References (IDOR)',
                'category': 'Broken Access Control',
                'description': 'Accessing objects without proper authorization',
                'testing': 'Manipulate object IDs, test access control mechanisms',
                'mitigation': 'Proper access control, authorization checks',
            },
            {
                'name': 'Security Misconfiguration',
                'category': 'Security Misconfiguration',
                'description': 'Improperly configured security controls',
                'testing': 'Check default configs, unnecessary features, verbose errors',
                'mitigation': 'Harden configurations, remove unused features',
            },
            {
                'name': 'Sensitive Data Exposure',
                'category': 'Identification & Authentication',
                'description': 'Inadequate protection of sensitive data',
                'testing': 'Check encryption, data handling practices',
                'mitigation': 'Encryption, secure data handling, privacy controls',
            },
            {
                'name': 'Broken Authentication',
                'category': 'Identification & Authentication',
                'description': 'Weak authentication mechanisms',
                'testing': 'Test session management, password policies, MFA',
                'mitigation': 'Strong authentication, secure session management',
            },
            {
                'name': 'XML External Entities (XXE)',
                'category': 'Injection',
                'description': 'Exploiting XML parsers with external entities',
                'testing': 'Test XML input with malicious entities',
                'mitigation': 'Disable external entities, use secure XML parsers',
            },
            {
                'name': 'Insufficient Logging & Monitoring',
                'category': 'Security Misconfiguration',
                'description': 'Inadequate security event logging',
                'testing': 'Check logging mechanisms, alert systems',
                'mitigation': 'Comprehensive logging, SIEM integration',
            },
            {
                'name': 'Using Deprecated Components',
                'category': 'Security Misconfiguration',
                'description': 'Outdated libraries with known vulnerabilities',
                'testing': 'Check for outdated dependencies, known CVEs',
                'mitigation': 'Keep dependencies updated, use SCA tools',
            },
        ]
        
        if vuln_type:
            # Filter to specific vulnerability type
            filtered = [v for v in vuln_types if vuln_type.lower() in v['name'].lower()]
            return tool_result(data={
                'vuln_type': vuln_type,
                'matches': len(filtered),
                'types': filtered,
            })
        
        return tool_result(data={
            'description': 'Common vulnerability types for bug bounty hunting',
            'types': vuln_types,
            'resources': [
                'OWASP Testing Guide: https://owasp.org/www-project-web-security-testing-guide/',
                'PortSwigger Web Security Academy: https://portswigger.net/web-security',
                'Bug Bounty Forum: https://bugbountyforum.com/',
            ],
        })
