"""Domain-based proactive request pacing and rate limiting.

Provides thread-safe token/interval pacing for academic registries and APIs,
supporting dynamic API-key rate tier switching and fast offline bypass.
"""

from __future__ import annotations

import os
import threading
import time
import urllib.parse
from collections.abc import Mapping

# Default proactive rate limits in requests per second.
DEFAULT_DOMAIN_LIMITS: dict[str, float] = {
    "api.crossref.org": 5.0,
    "api.openalex.org": 10.0,
    "export.arxiv.org": 0.33,
    "arxiv.org": 0.33,
    "api.semanticscholar.org": 1.0,
    "api.datacite.org": 5.0,
    "api.unpaywall.org": 5.0,
    "default": 5.0,
}


class DomainRateLimiter:
    """Thread-safe proactive domain rate limiter for outbound HTTP requests."""

    def __init__(
        self,
        limits: Mapping[str, float] | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            limits: Optional mapping of domain names to rate limits in requests/sec.
                Overrides or supplements the entries in DEFAULT_DOMAIN_LIMITS.
            enabled: If False, acquire() returns immediately without delay.
        """
        self.enabled = enabled
        self.limits: dict[str, float] = dict(DEFAULT_DOMAIN_LIMITS)
        if limits:
            self.limits.update(limits)

        self._last_request_time: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def extract_domain(url_or_domain: str) -> str:
        """Extract a normalized lowercase domain name from a URL or hostname.

        Handles URLs with schemes, ports, credentials, scheme-less hostnames,
        relative paths, and malformed strings safely.

        Args:
            url_or_domain: A URL or hostname string.

        Returns:
            The normalized domain string (e.g. 'api.crossref.org') or 'default'.
        """
        if not url_or_domain:
            return "default"
        cleaned = str(url_or_domain).strip()
        if not cleaned:
            return "default"

        try:
            if "://" not in cleaned and not cleaned.startswith("//"):
                parsed = urllib.parse.urlsplit(f"//{cleaned}")
            else:
                parsed = urllib.parse.urlsplit(cleaned)
            hostname = parsed.hostname
            if hostname:
                return hostname.strip().lower()
        except Exception:
            pass

        return "default"

    def get_rate(
        self,
        domain: str,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """Get the configured rate limit (requests per second) for a domain or URL.

        Dynamically checks for authentication headers (e.g. Semantic Scholar API keys)
        to assign authenticated tier rate limits.

        Args:
            domain: Domain name or URL string.
            headers: Optional request headers to inspect for credentials.

        Returns:
            Configured rate limit in requests per second (float).
        """
        normalized_domain = self.extract_domain(domain)

        # Dynamic check for Semantic Scholar authenticated pool
        if normalized_domain == "api.semanticscholar.org":
            has_api_key = False
            if headers:
                for k, v in headers.items():
                    if k.lower() in ("x-api-key", "api-key") and v:
                        has_api_key = True
                        break
            if has_api_key:
                return self.limits.get("api.semanticscholar.org:authenticated", 10.0)

        if normalized_domain in self.limits:
            return self.limits[normalized_domain]

        return self.limits.get("default", 5.0)

    def acquire(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
    ) -> float:
        """Acquire rate limit clearance to dispatch a request to the target URL.

        Paces requests according to the configured requests-per-second limit for the
        target domain. If rate limiting is disabled via constructor or the
        SCIFI_DISABLE_RATE_LIMIT environment variable, returns 0.0 immediately.

        Args:
            url: Target request URL or domain string.
            headers: Optional request headers to inspect for credentials.

        Returns:
            Delay in seconds waited (0.0 if request was dispatched without waiting).
        """
        if not self.enabled or os.getenv("SCIFI_DISABLE_RATE_LIMIT") == "1":
            return 0.0

        domain = self.extract_domain(url)
        rate = self.get_rate(domain, headers=headers)
        if rate <= 0:
            return 0.0

        interval = 1.0 / rate

        with self._lock:
            now = time.monotonic()
            last_time = self._last_request_time.get(domain, 0.0)
            scheduled_time = max(now, last_time + interval)
            wait_time = scheduled_time - now
            self._last_request_time[domain] = scheduled_time

        if wait_time > 0:
            time.sleep(wait_time)
            return wait_time

        return 0.0
