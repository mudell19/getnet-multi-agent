"""Polite sequential crawler: one level deep, same host, with a raw HTML cache."""
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from getnet_multi_agent.logging_setup import log_event

PAUSE_SECONDS = 2.0
USER_AGENT = "getnet-multi-agent-crawler/0.1"
SKIPPED_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".svg", ".webp", ".zip", ".mp4", ".doc", ".docx", ".xls", ".xlsx")


@dataclass(frozen=True)
class SourceSite:
    start_url: str
    host: str
    path_prefix: str
    origin: str
    required: tuple[str, ...] = ()

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.hostname != self.host:
            return False
        if not self.path_prefix:
            return True
        path = parts.path.rstrip("/")
        return path == self.path_prefix or path.startswith(self.path_prefix + "/")


SOURCES = (
    SourceSite(
        "https://site.getnet.com.br/",
        "site.getnet.com.br",
        "",
        "brazil_site",
        tuple(
            f"https://site.getnet.com.br{p}"
            for p in ("/duvidas/", "/crediario/", "/link-de-pagamento/", "/pix/", "/todas-as-maquininhas/")
        ),
    ),
    SourceSite(
        "https://www.getnet.net/en",
        "www.getnet.net",
        "/en",
        "global_site",
        ("https://www.getnet.net/en/our-solutions/in-person-payments",),
    ),
)


@dataclass
class Page:
    url: str
    final_url: str
    html: str
    origin: str
    title: str = ""


@dataclass
class CrawlResult:
    pages: list[Page] = field(default_factory=list)
    stopped_hosts: list[str] = field(default_factory=list)


def normalize(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))


def visible_text_hash(html: str) -> str:
    """Hashes visible text, because raw HTML differs per request in nonces and tokens."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return hashlib.sha256(" ".join(soup.get_text(" ").split()).encode()).hexdigest()


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    return [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]


class HtmlCache:
    def __init__(self, directory: Path):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def _stem(self, url: str) -> Path:
        return self.directory / hashlib.sha256(normalize(url).encode()).hexdigest()

    def get(self, url: str) -> dict | None:
        meta = self._stem(url).with_suffix(".json")
        if not meta.exists():
            return None
        entry = json.loads(meta.read_text())
        html = self._stem(url).with_suffix(".html")
        entry["html"] = html.read_text() if html.exists() else ""
        return entry

    def put(self, url: str, final_url: str, status: int, content_type: str, html: str) -> dict:
        entry = {"url": url, "final_url": final_url, "status": status, "content_type": content_type}
        self._stem(url).with_suffix(".json").write_text(json.dumps(entry))
        if html:
            self._stem(url).with_suffix(".html").write_text(html)
        return {**entry, "html": html}


class Crawler:
    def __init__(self, cache_dir: Path, max_pages: int, refresh: bool = False, client=None, sleep=time.sleep):
        self.cache = HtmlCache(cache_dir)
        self.max_pages = max_pages
        self.refresh = refresh
        self.client = client or httpx.Client(
            follow_redirects=True, timeout=20.0, headers={"User-Agent": USER_AGENT}
        )
        self.sleep = sleep
        self.stopped: set[str] = set()
        self._fetched_any = False

    def _fetch(self, url: str, site: SourceSite) -> dict | None:
        """Returns a cache entry. A cached URL is refetched only by the refresh command."""
        cached = self.cache.get(url)
        if cached and (not self.refresh or site.host in self.stopped):
            return cached
        if site.host in self.stopped:
            return None
        if self._fetched_any:
            self.sleep(PAUSE_SECONDS)
        self._fetched_any = True
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            log_event("crawl_error", url=url, error=type(exc).__name__)
            return cached
        if response.status_code in (403, 429):
            log_event("crawl_host_stopped", host=site.host, url=url, status=response.status_code)
            self.stopped.add(site.host)
            return cached
        content_type = response.headers.get("content-type", "")
        is_html = response.status_code == 200 and content_type.startswith("text/html")
        return self.cache.put(
            url, str(response.url), response.status_code, content_type, response.text if is_html else ""
        )

    def crawl(self, sources=SOURCES) -> CrawlResult:
        pages: list[Page] = []
        seen_final: set[str] = set()
        seen_hash: set[str] = set()

        def consider(url: str, site: SourceSite) -> str | None:
            entry = self._fetch(url, site)
            if not entry or entry["status"] != 200 or not entry["content_type"].startswith("text/html"):
                return None
            final = entry["final_url"]
            if not site.allows(final) or normalize(final) in seen_final:
                return None
            seen_final.add(normalize(final))
            digest = visible_text_hash(entry["html"])
            if digest in seen_hash:
                return None
            seen_hash.add(digest)
            soup = BeautifulSoup(entry["html"], "lxml")
            title = soup.title.get_text(" ", strip=True) if soup.title else final
            pages.append(Page(url, final, entry["html"], site.origin, title))
            return entry["html"]

        # Start pages and required pages go first, so the page cap cannot exclude them.
        queues: list[list[tuple[str, SourceSite]]] = []
        visited: set[str] = set()
        for site in sources:
            visited.add(normalize(site.start_url))
            html = consider(site.start_url, site)
            links = extract_links(html, site.start_url) if html else []
            queue: list[tuple[str, SourceSite]] = []
            for link in [*site.required, *links]:
                key = normalize(link)
                if key in visited or not site.allows(link):
                    continue
                if urlsplit(key).path.lower().endswith(SKIPPED_EXTENSIONS):
                    continue
                visited.add(key)
                queue.append((key if link not in site.required else link, site))
            queues.append(queue)

        for site, queue in zip(sources, queues):
            for url, _ in queue[: len(site.required)]:
                if len(pages) < self.max_pages:
                    consider(url, site)
        remaining = [q[len(s.required) :] for s, q in zip(sources, queues)]
        while any(remaining) and len(pages) < self.max_pages:
            for queue in remaining:
                if queue and len(pages) < self.max_pages:
                    url, site = queue.pop(0)
                    consider(url, site)
        log_event("crawl_complete", pages=len(pages), stopped_hosts=sorted(self.stopped))
        return CrawlResult(pages, sorted(self.stopped))
