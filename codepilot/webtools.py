"""Built-in web tools: a small, trusted set, called directly (no MCP servers).

- library_docs: up-to-date docs and code examples for libraries and SDKs, from Context7 (the docs service
  Cursor, Claude Code and Copilot users wire in). Only the library name and the question are sent.
- web_fetch: read a web page (as text) or an image. It asks per domain, because a fetched URL can carry
  data out of the session. Nothing is pre-approved (CVE-2026-54316 showed why), redirects to another domain
  are refused, and cloud metadata addresses are always blocked.
- web_search: web results from Brave Search. Only offered when BRAVE_API_KEY is set.

All three are off with CODEPILOT_WEB=0.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

MAX_DOWNLOAD = 5_000_000
MAX_TEXT = 40_000
TIMEOUT = 20
UA = "codepilot (+https://github.com/bbrennan/codepilot)"
CONTEXT7 = "https://context7.com/api/v2"


class WebError(RuntimeError):
    pass


# -- HTML to readable text --------------------------------------------------------------------------

class _Text(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "head"}
    BLOCK = {"p", "div", "section", "article", "main", "br", "li", "tr", "table", "ul", "ol", "pre", "blockquote",
             "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "header", "footer", "nav", "aside"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0
        self.title = ""
        self._in_title = False
        self.href: str | None = None
        self.pre = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True
        if tag in self.SKIP:
            self.skip += 1
        if self.skip:
            return
        if tag in self.BLOCK:
            self.out.append("\n")
        if tag in ("h1", "h2", "h3", "h4"):
            self.out.append("#" * int(tag[1]) + " ")
        elif tag == "li":
            self.out.append("- ")
        elif tag == "pre":
            self.pre += 1
            self.out.append("```\n")
        elif tag == "a":
            self.href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "pre":
            self.pre = max(0, self.pre - 1)
            self.out.append("\n```\n")
        elif tag == "a" and self.href and self.href.startswith("http"):
            self.out.append(f" ({self.href})")
            self.href = None
        if tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.out.append(data if self.pre else re.sub(r"\s+", " ", data))


def html_to_text(html: str) -> tuple[str, str]:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.out)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return parser.title.strip(), text


# -- fetching ---------------------------------------------------------------------------------------

def host_of(url: str) -> str:
    return (urllib.parse.urlsplit(url).hostname or "").lower()


METADATA_ADDRESSES = ("169.254.169.254", "fd00:ec2::254")


def vet_address(text: str) -> None:
    """Refuse cloud-metadata and link-local addresses, including an IPv4 one wrapped in IPv6 (::ffff:a.b.c.d)."""
    ip = ipaddress.ip_address(text.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if ip.is_link_local or str(ip) in METADATA_ADDRESSES:
        raise WebError("cloud metadata and link-local addresses are never fetched")


def check_target(url: str) -> None:
    """Early, friendly refusal. The real guard is GuardedConnection, which vets the address actually connected to."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise WebError("only http and https URLs can be fetched")
    try:
        addrs = {ai[4][0] for ai in socket.getaddrinfo(parts.hostname, None)}
    except socket.gaierror:
        raise WebError(f"can't resolve {parts.hostname}") from None
    for a in addrs:
        vet_address(a)


def _connect_vetted(conn) -> socket.socket:
    """Resolve at connection time and connect to an address that passed vet_address: a hostile DNS server can answer
    differently for the pre-check and the connection (DNS rebinding), and redirects connect afresh too."""
    last: OSError | None = None
    for family, _type, _proto, _canon, addr in socket.getaddrinfo(conn.host, conn.port, type=socket.SOCK_STREAM):
        vet_address(addr[0])
        try:
            return socket.create_connection((addr[0], addr[1]), conn.timeout, conn.source_address)
        except OSError as exc:
            last = exc
    raise last or OSError(f"can't connect to {conn.host}")


class GuardedHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = _connect_vetted(self)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


class GuardedHTTPSConnection(http.client.HTTPSConnection):
    def connect(self):
        sock = _connect_vetted(self)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class GuardedHTTPHandler(urllib.request.HTTPHandler):
    def http_open(self, req):
        return self.do_open(GuardedHTTPConnection, req)


class GuardedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(GuardedHTTPSConnection, req, context=self._context)


class SameHostRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if host_of(newurl) != host_of(req.full_url):
            raise WebError(f"the page redirects to another site ({newurl}); fetch that URL if you trust it")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def safe_opener() -> urllib.request.OpenerDirector:
    """An opener for fetching user- or model-supplied URLs: same-site redirects only, vetted connections only."""
    return urllib.request.build_opener(SameHostRedirects, GuardedHTTPHandler, GuardedHTTPSHandler)


def _get(url: str, headers: dict | None = None, timeout: float = TIMEOUT) -> tuple[bytes, str, str]:
    check_target(url)
    opener = safe_opener()
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with opener.open(req, timeout=timeout) as resp:
            data = resp.read(MAX_DOWNLOAD + 1)
            ctype = resp.headers.get("Content-Type", "")
            final = resp.geturl()
    except urllib.error.HTTPError as exc:
        raise WebError(f"HTTP {exc.code} from {host_of(url)}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise WebError(f"couldn't fetch {url}: {getattr(exc, 'reason', exc)}") from None
    if len(data) > MAX_DOWNLOAD:
        raise WebError(f"the response is larger than {MAX_DOWNLOAD // 1_000_000} MB")
    return data, ctype.lower(), final


def fetch_page(url: str) -> dict:
    """{"kind": "text", "title", "text", "url"} or {"kind": "image", "bytes"}."""
    from . import images

    data, ctype, final = _get(url)
    if ctype.startswith("image/") or images.sniff(data):
        return {"kind": "image", "bytes": data, "url": final}
    if "pdf" in ctype or data[:5] == b"%PDF-":
        raise WebError("PDFs aren't supported; look for an HTML version of the page")
    charset = (re.search(r"charset=([\w-]+)", ctype) or [None, "utf-8"])[1]
    body = data.decode(charset, errors="replace")
    if "html" in ctype or body.lstrip()[:200].lower().startswith(("<!doctype html", "<html")):
        title, text = html_to_text(body)
    else:
        title, text = "", body
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT] + f"\n[... truncated at {MAX_TEXT:,} characters ...]"
    return {"kind": "text", "title": title, "text": text, "url": final}


# -- Context7 ---------------------------------------------------------------------------------------

def _context7(path: str, params: dict, key: str, raw: bool = False):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data, _, _ = _get(f"{CONTEXT7}/{path}?{urllib.parse.urlencode(params)}", headers)
    text = data.decode(errors="replace")
    return text if raw else json.loads(text)


def library_docs(library: str, question: str, key: str = "", tokens: int = 6000) -> str:
    try:
        found = _context7("libs/search", {"libraryName": library, "query": question}, key).get("results", [])
    except (WebError, ValueError) as exc:
        raise WebError(f"Context7 search failed: {exc}") from None
    if not found:
        return f"No documentation found for {library!r} on Context7. Try another name, or web_fetch its docs site."
    best = found[0]
    try:
        docs = _context7("context", {"libraryId": best["id"], "query": question, "type": "txt",
                                     "tokens": tokens}, key, raw=True)
    except WebError as exc:
        raise WebError(f"Context7 docs failed: {exc}") from None
    others = ", ".join(f"{r['title']} ({r['id']})" for r in found[1:5])
    head = f"Documentation for {best.get('title', library)} ({best['id']}) from Context7"
    return f"{head}{'; other matches: ' + others if others else ''}\n\n{docs.strip()[:MAX_TEXT]}"


# -- Brave Search ------------------------------------------------------------------------------------

def web_search(query: str, key: str, count: int = 8) -> str:
    url = "https://api.search.brave.com/res/v1/web/search?" + urllib.parse.urlencode({"q": query, "count": count})
    data, _, _ = _get(url, {"X-Subscription-Token": key, "Accept": "application/json"})
    results = json.loads(data).get("web", {}).get("results", [])
    if not results:
        return "No results."
    return "\n\n".join(f"{i}. {r.get('title', '')}\n   {r.get('url', '')}\n   "
                       f"{re.sub('<[^>]+>', '', r.get('description', ''))}" for i, r in enumerate(results, 1))
