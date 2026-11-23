"""Configurable search provider interface and real API adapters."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import requests

from .models import SearchResult


class SearchProviderError(RuntimeError):
    """Raised when a configured search provider fails safely."""


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "unknown"


class SearchProvider(ABC):
    """Abstract interface allowing search backends to be swapped cleanly."""

    name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the provider has the required configuration/credentials."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Execute a search query and return normalized SearchResult objects."""


class NullSearchProvider(SearchProvider):
    """Fallback provider used when no search API key is configured."""

    name = "manual"

    def is_configured(self) -> bool:
        return False

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Return no external results when no search API key is configured."""
        return []


class TavilySearchProvider(SearchProvider):
    """Search provider backed by the Tavily Search API (requires TAVILY_API_KEY)."""

    name = "tavily"
    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("TAVILY_API_KEY", "")).strip()
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.is_configured():
            raise SearchProviderError("Tavily search is not configured (missing TAVILY_API_KEY).")
        if not query.strip():
            return []

        payload = {
            "api_key": self._api_key,
            "query": query.strip(),
            "max_results": max(1, min(max_results, 10)),
            "search_depth": "basic",
            "include_answer": False,
        }
        try:
            response = requests.post(self.ENDPOINT, json=payload, timeout=self._timeout)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise SearchProviderError("Tavily search request timed out.") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise SearchProviderError(f"Tavily search returned HTTP {status}.") from exc
        except (requests.RequestException, ValueError) as exc:
            raise SearchProviderError("Failed to query Tavily search API.") from exc

        raw_results = data.get("results", [])
        if not isinstance(raw_results, list):
            raise SearchProviderError("Malformed response format from Tavily search API.")

        results: list[SearchResult] = []
        for item in raw_results[:max_results]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            if not url:
                continue
            title = str(item.get("title") or _domain_from_url(url)).strip()
            snippet = str(item.get("content") or "").strip()
            pub_date = item.get("published_date")
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    publisher=_domain_from_url(url),
                    publication_date=str(pub_date).strip() if pub_date else None,
                    snippet=snippet,
                    provider=self.name,
                )
            )
        return results


class SerperSearchProvider(SearchProvider):
    """Search provider backed by Serper Google Search JSON API (requires SERPER_API_KEY)."""

    name = "serper"
    ENDPOINT = "https://google.serper.dev/search"

    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self._api_key = (api_key if api_key is not None else os.getenv("SERPER_API_KEY", "")).strip()
        self._timeout = timeout

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        if not self.is_configured():
            raise SearchProviderError("Serper search is not configured (missing SERPER_API_KEY).")
        if not query.strip():
            return []

        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {"q": query.strip(), "num": max(1, min(max_results, 10))}
        try:
            response = requests.post(
                self.ENDPOINT, headers=headers, json=payload, timeout=self._timeout
            )
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            raise SearchProviderError("Serper search request timed out.") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise SearchProviderError(f"Serper search returned HTTP {status}.") from exc
        except (requests.RequestException, ValueError) as exc:
            raise SearchProviderError("Failed to query Serper search API.") from exc

        organic = data.get("organic", [])
        if not isinstance(organic, list):
            raise SearchProviderError("Malformed response format from Serper search API.")

        results: list[SearchResult] = []
        for item in organic[:max_results]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("link", "")).strip()
            if not url:
                continue
            title = str(item.get("title") or _domain_from_url(url)).strip()
            snippet = str(item.get("snippet") or "").strip()
            pub_date = item.get("date")
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    publisher=_domain_from_url(url),
                    publication_date=str(pub_date).strip() if pub_date else None,
                    snippet=snippet,
                    provider=self.name,
                )
            )
        return results


def get_search_provider(provider_name: str | None = None) -> SearchProvider:
    """Resolve the active SearchProvider from explicit selection or environment variables.

    Never scrapes search engine HTML pages. Returns NullSearchProvider if no API key
    is configured so the application safely uses Manual Evidence Mode.
    """
    choice = (provider_name or os.getenv("SEARCH_PROVIDER", "auto")).strip().lower()

    if choice == "none":
        return NullSearchProvider()
    if choice == "tavily":
        provider = TavilySearchProvider()
        return provider if provider.is_configured() else NullSearchProvider()
    if choice == "serper":
        provider = SerperSearchProvider()
        return provider if provider.is_configured() else NullSearchProvider()

    # Auto-detect configured API provider
    tavily = TavilySearchProvider()
    if tavily.is_configured():
        return tavily

    serper = SerperSearchProvider()
    if serper.is_configured():
        return serper

    return NullSearchProvider()
