"""
Web search tools — Serper via managed Zuplo gateway (POST {GATEWAY_BASE_URL}/search), then DuckDuckGo fallback.

Auth matches main LLM: JWT as Bearer, or ``Bearer sk-gateway-managed`` (or saved api_key) plus ``X-Gateway-Sig``.
Zuplo injects the Serper API key upstream. On any Serper/gateway failure, tools fall back to DuckDuckGo (``ddgs``).

Tools: web_search, web_research, web_advanced.

Debug: outbound gateway /search calls append lines to ``backend/gateway_search_debug.log``
(same idea as ``screenops_debug.log``): URL, redacted headers, JSON request body, status,
and response body (truncated). Safe for credentials — Authorization / X-Gateway-Sig redacted.
"""

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import structlog
import httpx
from bs4 import BeautifulSoup

logger = structlog.get_logger()

# Same layout as screenops_debug.log: file lives under main-app/backend/
_GATEWAY_SEARCH_DEBUG_LOG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "gateway_search_debug.log"
)
_MAX_DEBUG_RESPONSE_CHARS = 24_000


def _redact_headers_for_log(headers: dict[str, str]) -> dict[str, str]:
    """Copy headers for debug output; never log bearer tokens or HMAC material."""
    out: dict[str, str] = {}
    for k, v in headers.items():
        lk = k.lower()
        if lk == "authorization":
            out[k] = "<redacted>"
        elif lk == "x-gateway-sig":
            out[k] = "<redacted>"
        else:
            out[k] = v
    return out


def _gateway_search_debug_log(tag: str, **kwargs: Any) -> None:
    """Append one line to gateway_search_debug.log (best-effort, never raises)."""
    try:
        ts = datetime.utcnow().isoformat()
        parts = " ".join(f"{k}={v!r}" for k, v in kwargs.items())
        line = f"[{ts}] [{tag}] {parts}\n"
        with open(_GATEWAY_SEARCH_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass

_serper_gateway_url: str = ""
_serper_gateway_token: str = ""
# When using HMAC (no JWT in gateway_token), same Bearer placeholder as OpenAI client → Zuplo.
_serper_managed_bearer_key: str = ""

# Constants
TIMEOUT = 10  # HTTP request timeout (seconds)
MAX_CONTENT_LENGTH = 5000  # Max chars per scraped page


# ---------------------------------------------------------------------------
# Provider Abstraction
# ---------------------------------------------------------------------------

class SearchResult:
    """Standardized search result format."""
    def __init__(
        self,
        organic: list[dict],
        knowledge_graph: Optional[dict] = None,
        people_also_ask: Optional[list[str]] = None,
        related_searches: Optional[list[str]] = None,
    ):
        self.organic = organic  # [{"title": "...", "link": "...", "snippet": "..."}, ...]
        self.knowledge_graph = knowledge_graph
        self.people_also_ask = people_also_ask
        self.related_searches = related_searches


class SearchProvider(ABC):
    """Abstract base class for search providers."""
    
    @abstractmethod
    def search(
        self,
        query: str,
        num_results: int = 10,
        gl: str = "us",
        hl: str = "en",
        **kwargs
    ) -> SearchResult:
        """Perform a search and return standardized results."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available (API key configured, etc.)."""
        pass
    
    @abstractmethod
    def supports_advanced_operators(self) -> bool:
        """Whether this provider supports advanced search operators."""
        pass


class SerperProvider(SearchProvider):
    """Serper search via managed gateway (JWT Bearer, or managed Bearer + X-Gateway-Sig like chat)."""

    def __init__(
        self,
        gateway_url: str,
        gateway_token: str = "",
        managed_bearer_key: str = "",
    ):
        self.gateway_url = gateway_url.rstrip("/") if gateway_url else ""
        self.gateway_token = gateway_token
        self.managed_bearer_key = (managed_bearer_key or "").strip()

    def is_available(self) -> bool:
        if not self.gateway_url:
            return False
        if (self.gateway_token or "").strip():
            return True
        from app.services.gateway_session import gateway_llm_headers

        return bool(gateway_llm_headers())
    
    def supports_advanced_operators(self) -> bool:
        return True
    
    def _build_advanced_query(self, query: str, **kwargs) -> str:
        """Build query string with advanced operators."""
        import re
        q = re.sub(r'\s+', ' ', query.strip())
        
        if kwargs.get("site"):
            q += f" site:{kwargs['site']}"
        if kwargs.get("filetype"):
            q += f" filetype:{kwargs['filetype']}"
        if kwargs.get("inurl"):
            q += f" inurl:{kwargs['inurl']}"
        if kwargs.get("intitle"):
            q += f" intitle:{kwargs['intitle']}"
        if kwargs.get("related"):
            q += f" related:{kwargs['related']}"
        if kwargs.get("cache"):
            q += f" cache:{kwargs['cache']}"
        if kwargs.get("before"):
            q += f" before:{kwargs['before']}"
        if kwargs.get("after"):
            q += f" after:{kwargs['after']}"
        if kwargs.get("exact"):
            q += f' "{kwargs["exact"]}"'
        if kwargs.get("exclude"):
            exclude_terms = kwargs["exclude"].split(",") if isinstance(kwargs["exclude"], str) else kwargs["exclude"]
            for term in exclude_terms:
                q += f" -{term.strip()}"
        if kwargs.get("or_terms"):
            or_terms = kwargs["or_terms"].split(",") if isinstance(kwargs["or_terms"], str) else kwargs["or_terms"]
            or_str = " OR ".join(t.strip() for t in or_terms)
            q += f" ({or_str})"
        
        return q.strip()
    
    def search(
        self,
        query: str,
        num_results: int = 10,
        gl: str = "us",
        hl: str = "en",
        **kwargs
    ) -> SearchResult:
        """Search using Serper API."""
        try:
            # Ensure num_results is an integer
            try:
                num_results = int(num_results) if isinstance(num_results, str) else int(num_results)
                num_results = max(1, min(num_results, 100))  # Clamp between 1 and 100
            except (ValueError, TypeError):
                num_results = 10
            
            # Build query with advanced operators if provided
            enhanced_query = self._build_advanced_query(query, **kwargs)
            
            payload = {
                "q": enhanced_query,
                "num": num_results,
                "gl": gl,
                "hl": hl,
            }
            
            # Add optional parameters
            if kwargs.get("location"):
                payload["location"] = kwargs["location"]
            if kwargs.get("tbs"):
                payload["tbs"] = kwargs["tbs"]
            if kwargs.get("page"):
                try:
                    page = int(kwargs["page"]) if isinstance(kwargs["page"], str) else int(kwargs["page"])
                    payload["page"] = max(1, page)
                except (ValueError, TypeError):
                    pass  # Skip invalid page
            if "autocorrect" in kwargs:
                try:
                    payload["autocorrect"] = bool(kwargs["autocorrect"]) if isinstance(kwargs["autocorrect"], str) else bool(kwargs["autocorrect"])
                except (ValueError, TypeError):
                    payload["autocorrect"] = True
            
            search_url = f"{self.gateway_url}/search"
            headers: dict[str, str] = {"Content-Type": "application/json"}
            token = (self.gateway_token or "").strip()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            else:
                from app.services.gateway_session import gateway_llm_headers

                gh = gateway_llm_headers()
                if not gh:
                    raise RuntimeError(
                        "Web search requires gateway auth: Supabase session JWT or per-user gateway HMAC secret."
                    )
                # Same pattern as AsyncOpenAI managed gateway: Bearer placeholder + X-Gateway-Sig
                bearer = self.managed_bearer_key or "sk-gateway-managed"
                headers["Authorization"] = f"Bearer {bearer}"
                headers.update(gh)
            try:
                response = httpx.post(
                    search_url,
                    headers=headers,
                    json=payload,
                    timeout=30.0,
                )
            except httpx.RequestError as exc:
                _gateway_search_debug_log(
                    "serper_gateway",
                    event="request_error",
                    url=search_url,
                    method="POST",
                    request_headers=_redact_headers_for_log(dict(headers)),
                    request_body=json.dumps(payload, ensure_ascii=False),
                    error=str(exc),
                )
                raise

            raw_text = response.text or ""
            logged_body = raw_text
            if len(logged_body) > _MAX_DEBUG_RESPONSE_CHARS:
                logged_body = (
                    logged_body[:_MAX_DEBUG_RESPONSE_CHARS]
                    + f"... [truncated, {len(raw_text)} chars total]"
                )
            _gateway_search_debug_log(
                "serper_gateway",
                event="round_trip",
                url=search_url,
                method="POST",
                request_headers=_redact_headers_for_log(dict(headers)),
                request_body=json.dumps(payload, ensure_ascii=False),
                status_code=response.status_code,
                response_body=logged_body,
            )

            response.raise_for_status()
            data = response.json()
            
            # Extract organic results
            organic = []
            for item in data.get("organic", []):
                organic.append({
                    "title": item.get("title", "N/A"),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "position": item.get("position", 0),
                })
            
            # Extract knowledge graph
            kg = data.get("knowledgeGraph")
            
            # Extract "people also ask"
            paa = []
            for item in data.get("peopleAlsoAsk", []):
                question = item.get("question", "")
                if question:
                    paa.append(question)
            
            # Extract related searches
            related = data.get("relatedSearches", [])
            
            return SearchResult(
                organic=organic,
                knowledge_graph=kg,
                people_also_ask=paa if paa else None,
                related_searches=related if related else None,
            )
        except Exception as exc:
            logger.error("serper_search_error", query=query[:80], error=str(exc))
            raise


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo via ``ddgs`` (fallback when Serper/gateway fails)."""

    def is_available(self) -> bool:
        return True

    def supports_advanced_operators(self) -> bool:
        return False

    def search(
        self,
        query: str,
        num_results: int = 10,
        gl: str = "us",
        hl: str = "en",
        **kwargs: Any,
    ) -> SearchResult:
        try:
            from ddgs import DDGS
        except ImportError as exc:
            raise RuntimeError("ddgs package not installed. Run: pip install ddgs") from exc

        try:
            num_results = int(num_results) if isinstance(num_results, str) else int(num_results)
            num_results = max(1, min(num_results, 25))
        except (ValueError, TypeError):
            num_results = 10

        with DDGS() as ddgs:
            raw = list(ddgs.text(query.strip(), max_results=num_results))
        organic: list[dict] = []
        for i, r in enumerate(raw, 1):
            organic.append(
                {
                    "title": r.get("title", "N/A"),
                    "link": r.get("href") or r.get("link", ""),
                    "snippet": (r.get("body") or r.get("snippet", ""))[:500],
                    "position": i,
                }
            )
        return SearchResult(organic=organic)


# ---------------------------------------------------------------------------
# Provider Manager
# ---------------------------------------------------------------------------

def _get_provider() -> SearchProvider:
    """Serper via managed gateway (configured per request)."""
    base = (_serper_gateway_url or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("Web search gateway URL not configured (GATEWAY_BASE_URL).")
    return SerperProvider(
        gateway_url=base,
        gateway_token=_serper_gateway_token or "",
        managed_bearer_key=_serper_managed_bearer_key,
    )


def _search_with_fallback(query: str, **kwargs: Any) -> SearchResult:
    """Try Serper via Zuplo; on any failure use DuckDuckGo."""
    try:
        return _get_provider().search(query, **kwargs)
    except Exception as exc:
        logger.warning(
            "serper_gateway_failed_fallback_ddg",
            query=(query or "")[:80],
            error=str(exc),
        )
        nr = kwargs.get("num_results", 10)
        try:
            nr = int(nr) if isinstance(nr, str) else int(nr)
            nr = max(1, min(nr, 25))
        except (ValueError, TypeError):
            nr = 10
        return DuckDuckGoProvider().search(
            query,
            num_results=nr,
            gl=str(kwargs.get("gl") or "us"),
            hl=str(kwargs.get("hl") or "en"),
        )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def configure_web_search(
    gateway_url: str = "",
    gateway_token: str = "",
    managed_bearer_key: str = "",
):
    """Configure web search (called from agent_service on each request)."""
    global _serper_gateway_url, _serper_gateway_token, _serper_managed_bearer_key
    _serper_gateway_url = gateway_url or ""
    _serper_gateway_token = gateway_token or ""
    _serper_managed_bearer_key = (managed_bearer_key or "").strip()


# ---------------------------------------------------------------------------
# Tool 1: web_search (replaces basic_search)
# ---------------------------------------------------------------------------

def web_search(
    query: str,
    num_results: int = 10,
    gl: str = "us",
    hl: str = "en",
) -> str:
    """Search the web and return results.
    
    Tries Serper via the managed gateway (POST /search); on failure uses DuckDuckGo.
    Returns formatted results with titles, URLs, snippets, knowledge graph,
    "people also ask", and related searches.
    
    Parameters
    ----------
    query : str
        Search query.
    num_results : int
        Number of results to return (default 10).
    gl : str
        Region code (ISO 3166-1 alpha-2, default "us").
    hl : str
        Language code (ISO 639-1, default "en").
    
    Returns
    -------
    str
        Formatted search results.
    """
    if not query or not query.strip():
        return "Error: empty search query"
    
    # Convert parameters to correct types (agent may pass strings)
    try:
        num_results = int(num_results) if isinstance(num_results, str) else int(num_results)
        num_results = max(1, min(num_results, 100))  # Clamp between 1 and 100
    except (ValueError, TypeError):
        num_results = 10
    
    try:
        result = _search_with_fallback(query, num_results=num_results, gl=gl, hl=hl)

        lines: list[str] = [f"Search results for: {query}\n"]
        
        # Knowledge graph
        if result.knowledge_graph:
            kg = result.knowledge_graph
            lines.append("Knowledge Graph:")
            if kg.get("title"):
                lines.append(f"  Title: {kg['title']}")
            if kg.get("description"):
                lines.append(f"  Description: {kg['description']}")
            lines.append("")
        
        # Organic results
        if result.organic:
            lines.append("Organic Results:")
            for i, item in enumerate(result.organic, 1):
                lines.append(f"{i}. {item['title']}")
                lines.append(f"   URL: {item['link']}")
                if item['snippet']:
                    lines.append(f"   {item['snippet'][:300]}")
                lines.append("")
        else:
            lines.append("No results found.\n")
        
        # People also ask
        if result.people_also_ask:
            lines.append("People Also Ask:")
            for q in result.people_also_ask[:5]:  # Limit to 5
                lines.append(f"  - {q}")
            lines.append("")
        
        # Related searches
        if result.related_searches:
            lines.append("Related Searches:")
            for s in result.related_searches[:5]:  # Limit to 5
                lines.append(f"  - {s}")
            lines.append("")
        
        return "\n".join(lines)
    except Exception as exc:
        logger.error("web_search_error", query=query[:80], error=str(exc))
        return f"Search error: {exc}"


# ---------------------------------------------------------------------------
# Tool 2: web_research (replaces deep_websearch)
# ---------------------------------------------------------------------------

def _search_and_extract_with_provider(query: str) -> list[dict]:
    """Search using provider and return structured results."""
    try:
        result = _search_with_fallback(query, num_results=8)
        
        structured = []
        for item in result.organic:
            structured.append({
                "title": item.get("title", "N/A"),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return structured
    except Exception as exc:
        logger.error("web_research_search_error", error=str(exc))
        raise


def _select_top_results(
    query: str,
    results: list[dict],
    llm_client: Any,
    model: str,
) -> list[dict]:
    """Use LLM to pick the top 3 most relevant results (same logic as deep_websearch)."""
    if len(results) <= 3:
        return results
    
    formatted = []
    for i, r in enumerate(results, 1):
        formatted.append(
            f"{i}. Title: {r.get('title', 'N/A')}\n"
            f"   URL: {r.get('link', 'N/A')}\n"
            f"   Snippet: {r.get('snippet', '')[:200]}"
        )
    results_text = "\n\n".join(formatted)
    
    system = (
        "You are a search result ranking expert.\n"
        "Select the top 3 most relevant results for the query.\n"
        "Return ONLY a JSON array of numbers (1-indexed), e.g. [1, 3, 5]."
    )
    user = f"Query: {query}\n\nSearch Results:\n{results_text}\n\nSelect top 3:"
    
    try:
        import asyncio
        
        async def _call():
            resp = await llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=50,
            )
            return resp.choices[0].message.content or "[]"
        
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                raw = pool.submit(asyncio.run, _call()).result()
        else:
            raw = asyncio.run(_call())
        
        m = re.search(r"\[[\d\s,]+\]", raw)
        indices = json.loads(m.group(0)) if m else json.loads(raw)
        
        selected = []
        for idx in indices[:3]:
            if 1 <= idx <= len(results):
                selected.append(results[idx - 1])
        return selected if selected else results[:3]
    except Exception as exc:
        logger.warning("web_research_selection_fallback", error=str(exc))
        return results[:3]


def _scrape_urls(results: list[dict]) -> dict[str, str]:
    """Scrape content from URLs using web_fetch logic (same as deep_websearch)."""
    from app.tools.web_fetch import web_fetch
    
    scraped: dict[str, str] = {}
    for r in results:
        url = r.get("link", "")
        if not url:
            continue
        try:
            # Use web_fetch for scraping (trafilatura/BeautifulSoup)
            content = web_fetch(url)
            # Extract just the content part (remove "Content from URL:\n\n" prefix)
            if content.startswith(f"Content from {url}:\n\n"):
                content = content[len(f"Content from {url}:\n\n"):]
            elif content.startswith("Content from"):
                # Handle any URL format
                parts = content.split("\n\n", 1)
                if len(parts) > 1:
                    content = parts[1]
            
            # Truncate if too long
            if len(content) > MAX_CONTENT_LENGTH:
                content = content[:MAX_CONTENT_LENGTH] + "... [truncated]"
            scraped[url] = content
        except Exception as exc:
            scraped[url] = f"[Error scraping: {exc}]"
    
    return scraped


def _format_research_content(
    query: str,
    scraped: dict[str, str],
    results: list[dict],
) -> str:
    """Format scraped content for the agent (same as deep_websearch)."""
    sections = []
    for url, content in scraped.items():
        info = next((r for r in results if r.get("link") == url), {})
        title = info.get("title", "Unknown")
        sections.append(
            f"Source: {title}\n"
            f"URL: {url}\n"
            f"Content:\n{content}\n"
            f"{'-' * 50}"
        )
    return "\n\n".join(sections) if sections else "No content scraped."


def make_web_research_fn(llm_client: Any, model: str):
    """Return a web_research(query) -> str function bound to the given LLM."""
    
    def web_research(query: str) -> str:
        """Comprehensive web research: search → select top 3 → scrape → format.
        
        Search step uses Serper via the managed gateway, then DuckDuckGo if that fails.
        Same pipeline as deep_websearch: search → LLM selects top 3 → scrape → format.
        
        Parameters
        ----------
        query : str
            Research query.
        
        Returns
        -------
        str
            Formatted research results with full content from top sources.
        """
        if not query or not query.strip():
            return "Error: empty query"
        try:
            # Step 1: Search (Serper via managed gateway)
            results = _search_and_extract_with_provider(query)
            if not results:
                return f"No search results found for: {query}"
            
            # Step 2: LLM selects top 3
            top = _select_top_results(query, results, llm_client, model)
            if not top:
                return "No results selected."
            
            # Step 3: Scrape full content
            scraped = _scrape_urls(top)
            if not scraped:
                return "Failed to scrape any URLs."
            
            # Step 4: Format
            return _format_research_content(query, scraped, top)
        except Exception as exc:
            logger.error("web_research_error", query=query[:80], error=str(exc))
            return f"Web research error: {exc}"
    
    return web_research


# ---------------------------------------------------------------------------
# Tool 3: web_advanced (new tool with full Serper features)
# ---------------------------------------------------------------------------

def web_advanced(
    query: str,
    num_results: int = 10,
    gl: str = "us",
    hl: str = "en",
    location: Optional[str] = None,
    tbs: Optional[str] = None,  # "qdr:h", "qdr:d", "qdr:w", "qdr:m", "qdr:y"
    page: int = 1,
    autocorrect: bool = True,
    # Advanced operators
    site: Optional[str] = None,
    filetype: Optional[str] = None,
    inurl: Optional[str] = None,
    intitle: Optional[str] = None,
    related: Optional[str] = None,
    cache: Optional[str] = None,
    before: Optional[str] = None,  # YYYY-MM-DD
    after: Optional[str] = None,   # YYYY-MM-DD
    exact: Optional[str] = None,
    exclude: Optional[str] = None,  # comma-separated
    or_terms: Optional[str] = None,  # comma-separated
) -> str:
    """Advanced web search with full Serper API features.
    
    Supports advanced search operators, region/language targeting, time filters,
    and pagination (Serper via gateway; operators may be ignored if falling back to DuckDuckGo).
    
    Parameters
    ----------
    query : str
        Search query.
    num_results : int
        Number of results (default 10).
    gl : str
        Region code (default "us").
    hl : str
        Language code (default "en").
    location : str, optional
        Location string (e.g., "SoHo, New York, United States").
    tbs : str, optional
        Time filter: "qdr:h" (hour), "qdr:d" (day), "qdr:w" (week),
        "qdr:m" (month), "qdr:y" (year).
    page : int
        Page number (default 1).
    autocorrect : bool
        Enable autocorrect (default True).
    site : str, optional
        Limit to domain (e.g., "python.org").
    filetype : str, optional
        File type filter (e.g., "pdf", "doc").
    inurl : str, optional
        Word must appear in URL.
    intitle : str, optional
        Word must appear in title.
    related : str, optional
        Find similar sites (e.g., "github.com").
    cache : str, optional
        View cached version of URL.
    before : str, optional
        Date before (YYYY-MM-DD).
    after : str, optional
        Date after (YYYY-MM-DD).
    exact : str, optional
        Exact phrase match.
    exclude : str, optional
        Terms to exclude (comma-separated).
    or_terms : str, optional
        Alternative terms (comma-separated, OR operator).
    
    Returns
    -------
    str
        Formatted search results.
    """
    if not query or not query.strip():
        return "Error: empty search query"
    
    # Convert parameters to correct types (agent may pass strings)
    try:
        num_results = int(num_results) if isinstance(num_results, str) else int(num_results)
        num_results = max(1, min(num_results, 100))  # Clamp between 1 and 100
    except (ValueError, TypeError):
        num_results = 10
    
    try:
        page = int(page) if isinstance(page, str) else int(page)
        page = max(1, page)  # Ensure at least 1
    except (ValueError, TypeError):
        page = 1
    
    try:
        autocorrect = bool(autocorrect) if isinstance(autocorrect, str) else bool(autocorrect)
    except (ValueError, TypeError):
        autocorrect = True
    
    try:
        # Build kwargs for advanced operators
        kwargs = {
            "location": location,
            "tbs": tbs,
            "page": page,
            "autocorrect": autocorrect,
            "site": site,
            "filetype": filetype,
            "inurl": inurl,
            "intitle": intitle,
            "related": related,
            "cache": cache,
            "before": before,
            "after": after,
            "exact": exact,
            "exclude": exclude,
            "or_terms": or_terms,
        }
        
        # Remove None values
        kwargs = {k: v for k, v in kwargs.items() if v is not None}

        result = _search_with_fallback(
            query, num_results=num_results, gl=gl, hl=hl, **kwargs
        )
        
        # Format results (same as web_search)
        lines: list[str] = [f"Advanced search results for: {query}\n"]
        
        if result.knowledge_graph:
            kg = result.knowledge_graph
            lines.append("Knowledge Graph:")
            if kg.get("title"):
                lines.append(f"  Title: {kg['title']}")
            if kg.get("description"):
                lines.append(f"  Description: {kg['description']}")
            lines.append("")
        
        if result.organic:
            lines.append("Organic Results:")
            for i, item in enumerate(result.organic, 1):
                lines.append(f"{i}. {item['title']}")
                lines.append(f"   URL: {item['link']}")
                if item['snippet']:
                    lines.append(f"   {item['snippet'][:300]}")
                lines.append("")
        else:
            lines.append("No results found.\n")
        
        if result.people_also_ask:
            lines.append("People Also Ask:")
            for q in result.people_also_ask[:5]:
                lines.append(f"  - {q}")
            lines.append("")
        
        if result.related_searches:
            lines.append("Related Searches:")
            for s in result.related_searches[:5]:
                lines.append(f"  - {s}")
            lines.append("")
        
        return "\n".join(lines)
    except Exception as exc:
        logger.error("web_advanced_error", query=query[:80], error=str(exc))
        return f"Advanced search error: {exc}"
