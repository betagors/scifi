"""Centralized resilient HTTP session with domain pacing, 429/5xx backoff, and polite headers.

Provides thread-safe proactive pacing via DomainRateLimiter, reactive exponential
backoff with Retry-After header parsing (seconds and HTTP-date), and automatic
injection of polite User-Agent and registry API keys.
"""

from __future__ import annotations

from datetime import datetime, timezone
import email.utils
import logging
import random
import threading
import time
from typing import Any, Mapping, Optional

import requests
from requests.exceptions import ChunkedEncodingError
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import RequestException, Timeout

from scifi.config import DEFAULT_FALLBACK_EMAIL, ScifiConfig, resolve_config
from scifi.network.rate_limiter import DomainRateLimiter

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES: int = 3
DEFAULT_BACKOFF_FACTOR: float = 0.5
DEFAULT_MAX_BACKOFF: float = 60.0

# Transient HTTP status codes subject to automatic retry and exponential backoff
RETRY_STATUS_CODES: set[int] = {429, 502, 503, 504}


def parse_retry_after(
    header_val: Optional[str],
    max_backoff: Optional[float] = None,
) -> Optional[float]:
    """Parse a Retry-After header value into delay in seconds.

    Handles integer/float second durations (e.g. '12', '0.5') as well as
    RFC 2822 HTTP-date strings (e.g. 'Wed, 21 Oct 2026 07:28:00 GMT').
    Delays are bounded to >= 0.0. If max_backoff is provided, delay is
    clamped to [0.0, max_backoff].

    Args:
        header_val: Raw value of the 'Retry-After' header, or None.
        max_backoff: Optional maximum backoff ceiling in seconds.

    Returns:
        Parsed delay in seconds as float, or None if missing or unparseable.
    """
    if not header_val:
        return None

    cleaned = str(header_val).strip()
    if not cleaned:
        return None

    # 1. Attempt parsing as numerical seconds (integer or float)
    try:
        seconds = float(cleaned)
        delay = max(0.0, seconds)
        if max_backoff is not None:
            delay = min(max_backoff, delay)
        return delay
    except ValueError:
        pass

    # 2. Attempt parsing as RFC 2822 HTTP-date
    try:
        target_dt = email.utils.parsedate_to_datetime(cleaned)
        if target_dt is None:
            return None
        if target_dt.tzinfo is None:
            target_dt = target_dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delay = (target_dt - now).total_seconds()
        delay = max(0.0, delay)
        if max_backoff is not None:
            delay = min(max_backoff, delay)
        return delay
    except Exception:
        return None


def compute_backoff_delay(
    attempt: int,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    max_backoff: float = DEFAULT_MAX_BACKOFF,
) -> float:
    """Calculate exponential backoff delay with uniform jitter.

    Formula: min(max_backoff, backoff_factor * (2 ** attempt)) + random.uniform(0.01, 0.1)

    Args:
        attempt: Retry attempt index (0-based for the first retry).
        backoff_factor: Base multiplier for exponential delay in seconds.
        max_backoff: Maximum delay cap before jitter in seconds.

    Returns:
        Backoff delay in seconds as float.
    """
    base_delay = backoff_factor * (2 ** max(0, attempt))
    clamped = min(max_backoff, max(0.0, base_delay))
    jitter = random.uniform(0.01, 0.1)
    return clamped + jitter


class ResilientSession(requests.Session):
    """Centralized resilient HTTP session for academic registries and APIs.

    Features:
    - Proactive domain rate limiting via DomainRateLimiter.
    - Reactive retry for HTTP 429, 502, 503, 504 and transient network errors.
    - Retry-After header parsing (seconds and HTTP-date) with bounded backoff.
    - Polite default User-Agent identifying SciFi toolkit and contact email.
    - Automatic injection of Semantic Scholar API keys if configured.
    - Conforms to standard requests.Session contract: returns terminal Response
      on persistent HTTP status codes, re-raises RequestException on network errors.
    """

    def __init__(
        self,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        max_backoff: float = DEFAULT_MAX_BACKOFF,
        rate_limiter: Optional[DomainRateLimiter] = None,
        config: Optional[ScifiConfig] = None,
    ) -> None:
        """Initialize the resilient session.

        Args:
            max_retries: Maximum number of retries after initial failure.
            backoff_factor: Multiplier for exponential backoff calculation.
            max_backoff: Maximum backoff ceiling in seconds.
            rate_limiter: Optional custom DomainRateLimiter instance.
            config: Optional resolved ScifiConfig. If None, loaded via resolve_config().
        """
        super().__init__()
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff
        self.rate_limiter = rate_limiter if rate_limiter is not None else DomainRateLimiter()
        self.config = config if config is not None else resolve_config()

        email = self.config.email or DEFAULT_FALLBACK_EMAIL
        self.headers["User-Agent"] = (
            f"SciFi-Toolkit/1.0 (academic-researcher; +https://github.com/scifi-toolkit; mailto:{email})"
        )

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Send an HTTP request with proactive pacing and reactive backoff retry.

        Args:
            method: HTTP method (e.g. 'GET', 'POST').
            url: Target URL string.
            **kwargs: Additional arguments passed to requests.Session.request.

        Returns:
            requests.Response: Terminal response from the server.

        Raises:
            requests.exceptions.RequestException: Re-raised if retries are exhausted
                on network transport errors (ConnectionError, Timeout).
        """
        # Inject Semantic Scholar API key if targeting api.semanticscholar.org
        # and not already provided by caller headers
        domain = DomainRateLimiter.extract_domain(url)
        if domain == "api.semanticscholar.org" and self.config.s2_api_key:
            req_headers = dict(kwargs.get("headers") or {})
            has_key = any(k.lower() in ("x-api-key", "api-key") for k in req_headers)
            if not has_key:
                req_headers["x-api-key"] = self.config.s2_api_key
                kwargs["headers"] = req_headers

        # Merge headers for rate limiter inspection (e.g. checking x-api-key)
        merged_headers = dict(self.headers)
        if "headers" in kwargs and kwargs["headers"]:
            merged_headers.update(kwargs["headers"])

        last_response: Optional[requests.Response] = None

        for attempt in range(self.max_retries + 1):
            # Proactive pacing
            self.rate_limiter.acquire(url, headers=merged_headers)

            try:
                response = super().request(method, url, **kwargs)
                last_response = response

                if response.status_code in RETRY_STATUS_CODES:
                    if attempt == self.max_retries:
                        logger.warning(
                            "Max retries (%d) exhausted for %s %s with terminal status %d",
                            self.max_retries,
                            method,
                            url,
                            response.status_code,
                        )
                        return response

                    # Release intermediate socket back to pool before sleeping
                    try:
                        response.close()
                    except Exception:
                        pass

                    # Determine retry delay
                    retry_after = parse_retry_after(
                        response.headers.get("Retry-After"),
                        max_backoff=self.max_backoff,
                    )
                    if retry_after is not None:
                        delay = retry_after
                    else:
                        delay = compute_backoff_delay(
                            attempt,
                            backoff_factor=self.backoff_factor,
                            max_backoff=self.max_backoff,
                        )

                    logger.info(
                        "Received HTTP %d for %s %s; retrying in %.2fs (attempt %d/%d)",
                        response.status_code,
                        method,
                        url,
                        delay,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(delay)
                    continue

                return response

            except (RequestsConnectionError, Timeout, ChunkedEncodingError) as exc:
                if attempt == self.max_retries:
                    logger.warning(
                        "Max retries (%d) exhausted for %s %s due to network error: %s",
                        self.max_retries,
                        method,
                        url,
                        exc,
                    )
                    raise

                delay = compute_backoff_delay(
                    attempt,
                    backoff_factor=self.backoff_factor,
                    max_backoff=self.max_backoff,
                )
                logger.info(
                    "Network error (%s) on %s %s; retrying in %.2fs (attempt %d/%d)",
                    type(exc).__name__,
                    method,
                    url,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(delay)
                continue

        if last_response is not None:
            return last_response
        raise RequestException(f"Failed to execute request {method} {url}")


_session: Optional[ResilientSession] = None
_session_lock = threading.Lock()


def get_session() -> ResilientSession:
    """Return a shared thread-safe ResilientSession singleton instance."""
    global _session
    if _session is None:
        with _session_lock:
            if _session is None:
                _session = ResilientSession()
    return _session
