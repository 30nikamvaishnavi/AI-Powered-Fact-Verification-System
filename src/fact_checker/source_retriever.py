"""Safe URL validation and publicly accessible webpage text extraction."""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import ManualEvidenceInput, RetrievalStatus, RetrievedSource, SearchResult

DEFAULT_TIMEOUT_SECONDS = 8
MAX_RESPONSE_BYTES = 1_000_000
MAX_STORED_TEXT_CHARS = 15_000
USER_AGENT = "FactVerificationSystem/1.0 (+educational-research; respectful-crawler)"

_RESTRICTED_HTTP_STATUSES = {401, 403, 429, 451}
_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain"}


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sanitize_untrusted_text(text: str) -> str:
    """Normalize whitespace and strip control characters from untrusted webpage text."""
    if not text:
        return ""
    # Strip ASCII control chars except newline/tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()[:MAX_STORED_TEXT_CHARS]


def extract_publisher(url: str) -> str:
    """Extract normalized publisher/domain string from a URL."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if "@" in host:
        host = host.split("@", maxsplit=1)[-1]
    if ":" in host:
        host = host.split(":", maxsplit=1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


def validate_public_url(url: str) -> tuple[bool, str | None]:
    """Validate that a URL uses http/https and does not point to private/loopback targets."""
    candidate = (url or "").strip()
    if not candidate:
        return False, "URL is empty."

    parsed = urlparse(candidate)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, f"Unsupported URL scheme '{parsed.scheme or 'none'}'. Use http or https."
    if not parsed.netloc or not parsed.hostname:
        return False, "URL is missing a valid domain name."

    hostname = parsed.hostname.lower().strip(".")
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".local"):
        return False, "Local/internal hostnames are not permitted."

    try:
        ip_obj = ipaddress.ip_address(hostname)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
        ):
            return False, "Private or reserved IP addresses are not permitted."
    except ValueError:
        # Hostname is a domain name, not an IP literal; verify it contains a dot
        if "." not in hostname:
            return False, "URL hostname must be a valid public domain."

    return True, None


def _extract_publication_date(soup: BeautifulSoup) -> str | None:
    """Extract publication date from standard HTML metadata if explicitly present."""
    meta_selectors = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"property": "og:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "publishdate"}),
        ("meta", {"name": "date"}),
        ("meta", {"itemprop": "datePublished"}),
        ("meta", {"name": "DC.date.issued"}),
    ]
    for tag_name, attrs in meta_selectors:
        tag = soup.find(tag_name, attrs=attrs)
        if tag and tag.get("content"):
            val = sanitize_untrusted_text(str(tag["content"]))
            if val:
                return val[:40]

    time_tag = soup.find("time")
    if time_tag:
        dt = time_tag.get("datetime") or time_tag.get_text(" ", strip=True)
        if dt:
            cleaned = sanitize_untrusted_text(str(dt))
            if cleaned:
                return cleaned[:40]

    return None


def parse_html_content(html: str, fallback_title: str = "Untitled Source") -> tuple[str, str, str | None]:
    """Extract clean article text, page title, and optional publication date from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    page_title = (
        sanitize_untrusted_text(title_tag.get_text(" ", strip=True))
        if title_tag
        else fallback_title
    )
    if not page_title:
        page_title = fallback_title

    pub_date = _extract_publication_date(soup)

    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()

    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in container.find_all(["p", "li"])
        if len(p.get_text(" ", strip=True)) >= 25
    ]

    extracted = "\n".join(paragraphs) if paragraphs else container.get_text("\n", strip=True)

    return page_title, sanitize_untrusted_text(extracted), pub_date


def retrieve_source_from_url(
    url: str,
    *,
    title: str | None = None,
    snippet: str = "",
    publication_date: str | None = None,
    provider: str = "web",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> RetrievedSource:
    """Safely fetch publicly accessible webpage text for a URL without bypassing restrictions."""
    source_id = f"src-{uuid.uuid4().hex[:8]}"
    timestamp = utc_now_iso()
    clean_url = (url or "").strip()
    clean_snippet = sanitize_untrusted_text(snippet)

    is_valid, validation_error = validate_public_url(clean_url)
    if not is_valid:
        return RetrievedSource(
            source_id=source_id,
            title=title or "Invalid Source URL",
            url=clean_url,
            publisher="invalid",
            publication_date=publication_date,
            snippet=clean_snippet,
            retrieved_text="",
            retrieval_status=RetrievalStatus.INVALID_URL,
            retrieval_error=validation_error,
            retrieved_at=timestamp,
            is_manual=False,
            provider=provider,
        )

    publisher = extract_publisher(clean_url)
    effective_title = (title or publisher).strip()
    http_client = session or requests

    try:
        response = http_client.get(
            clean_url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9,*/*;q=0.5"},
            timeout=timeout,
            allow_redirects=True,
        )
    except requests.Timeout:
        return _inaccessible_source(
            source_id=source_id,
            title=effective_title,
            url=clean_url,
            publisher=publisher,
            publication_date=publication_date,
            snippet=clean_snippet,
            error=f"Request timed out after {timeout}s.",
            timestamp=timestamp,
            provider=provider,
        )
    except requests.RequestException as exc:
        return _inaccessible_source(
            source_id=source_id,
            title=effective_title,
            url=clean_url,
            publisher=publisher,
            publication_date=publication_date,
            snippet=clean_snippet,
            error=f"Network retrieval failed: {type(exc).__name__}.",
            timestamp=timestamp,
            provider=provider,
        )

    if response.status_code in _RESTRICTED_HTTP_STATUSES:
        return _inaccessible_source(
            source_id=source_id,
            title=effective_title,
            url=clean_url,
            publisher=publisher,
            publication_date=publication_date,
            snippet=clean_snippet,
            error=f"Access restricted (HTTP {response.status_code}) — website restrictions respected.",
            timestamp=timestamp,
            provider=provider,
        )

    if response.status_code >= 400:
        return _inaccessible_source(
            source_id=source_id,
            title=effective_title,
            url=clean_url,
            publisher=publisher,
            publication_date=publication_date,
            snippet=clean_snippet,
            error=f"HTTP error {response.status_code} when requesting source.",
            timestamp=timestamp,
            provider=provider,
        )

    content_type = str(response.headers.get("Content-Type", "")).lower()
    raw_bytes = response.content[:MAX_RESPONSE_BYTES]
    encoding = response.encoding or "utf-8"
    decoded = raw_bytes.decode(encoding, errors="replace")

    if "html" in content_type or "<html" in decoded[:500].lower():
        parsed_title, extracted_text, extracted_date = parse_html_content(
            decoded, fallback_title=effective_title
        )
        final_title = title or parsed_title
        final_date = publication_date or extracted_date
    elif "text/plain" in content_type or not content_type:
        final_title = effective_title
        extracted_text = sanitize_untrusted_text(decoded)
        final_date = publication_date
    else:
        return _inaccessible_source(
            source_id=source_id,
            title=effective_title,
            url=clean_url,
            publisher=publisher,
            publication_date=publication_date,
            snippet=clean_snippet,
            error=f"Unsupported content type '{content_type}'.",
            timestamp=timestamp,
            provider=provider,
        )

    if not extracted_text:
        return _inaccessible_source(
            source_id=source_id,
            title=final_title,
            url=clean_url,
            publisher=publisher,
            publication_date=final_date,
            snippet=clean_snippet,
            error="No readable article text could be extracted from the page.",
            timestamp=timestamp,
            provider=provider,
        )

    return RetrievedSource(
        source_id=source_id,
        title=final_title,
        url=clean_url,
        publisher=publisher,
        publication_date=final_date,
        snippet=clean_snippet,
        retrieved_text=extracted_text,
        retrieval_status=RetrievalStatus.RETRIEVED,
        retrieval_error=None,
        retrieved_at=timestamp,
        is_manual=False,
        provider=provider,
    )


def _inaccessible_source(
    *,
    source_id: str,
    title: str,
    url: str,
    publisher: str,
    publication_date: str | None,
    snippet: str,
    error: str,
    timestamp: str,
    provider: str,
) -> RetrievedSource:
    status = RetrievalStatus.SNIPPET_ONLY if snippet else RetrievalStatus.INACCESSIBLE
    return RetrievedSource(
        source_id=source_id,
        title=title,
        url=url,
        publisher=publisher,
        publication_date=publication_date,
        snippet=snippet,
        retrieved_text="",
        retrieval_status=status,
        retrieval_error=error,
        retrieved_at=timestamp,
        is_manual=False,
        provider=provider,
    )


def retrieve_sources_from_search_results(
    results: list[SearchResult],
    *,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> list[RetrievedSource]:
    """Retrieve webpage text for each SearchResult while preserving snippets and URLs."""
    retrieved: list[RetrievedSource] = []
    seen_urls: set[str] = set()
    for item in results:
        normalized_url = item.url.strip()
        if normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        retrieved.append(
            retrieve_source_from_url(
                normalized_url,
                title=item.title,
                snippet=item.snippet,
                publication_date=item.publication_date,
                provider=item.provider,
                timeout=timeout,
                session=session,
            )
        )
    return retrieved


def build_manual_source(
    entry: ManualEvidenceInput,
    *,
    fetch_if_text_missing: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> RetrievedSource:
    """Convert a user-supplied ManualEvidenceInput into a RetrievedSource."""
    clean_url = entry.url.strip()
    clean_text = sanitize_untrusted_text(entry.text)
    is_valid, validation_error = validate_public_url(clean_url)

    if not is_valid:
        return RetrievedSource(
            source_id=f"src-{uuid.uuid4().hex[:8]}",
            title=entry.title.strip(),
            url=clean_url,
            publisher="invalid",
            publication_date=entry.publication_date.strip() if entry.publication_date else None,
            snippet="",
            retrieved_text="",
            retrieval_status=RetrievalStatus.INVALID_URL,
            retrieval_error=validation_error,
            retrieved_at=utc_now_iso(),
            is_manual=True,
            provider="manual",
        )

    if not clean_text and fetch_if_text_missing:
        fetched = retrieve_source_from_url(
            clean_url,
            title=entry.title.strip(),
            publication_date=entry.publication_date.strip() if entry.publication_date else None,
            provider="manual-fetch",
            timeout=timeout,
            session=session,
        )
        return fetched.model_copy(update={"is_manual": True})

    if not clean_text:
        return RetrievedSource(
            source_id=f"src-{uuid.uuid4().hex[:8]}",
            title=entry.title.strip(),
            url=clean_url,
            publisher=extract_publisher(clean_url),
            publication_date=entry.publication_date.strip() if entry.publication_date else None,
            snippet="",
            retrieved_text="",
            retrieval_status=RetrievalStatus.INACCESSIBLE,
            retrieval_error="No evidence text was provided for this manual source.",
            retrieved_at=utc_now_iso(),
            is_manual=True,
            provider="manual",
        )

    return RetrievedSource(
        source_id=f"src-{uuid.uuid4().hex[:8]}",
        title=entry.title.strip(),
        url=clean_url,
        publisher=extract_publisher(clean_url),
        publication_date=entry.publication_date.strip() if entry.publication_date else None,
        snippet="",
        retrieved_text=clean_text,
        retrieval_status=RetrievalStatus.MANUAL,
        retrieval_error=None,
        retrieved_at=utc_now_iso(),
        is_manual=True,
        provider="manual",
    )
