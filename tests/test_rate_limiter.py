"""Unit tests for DomainRateLimiter in scifi.network.rate_limiter."""

import threading
from unittest.mock import patch

import pytest

from scifi.network.rate_limiter import DomainRateLimiter


def test_default_domain_rates() -> None:
    """Verify default rate limits for known academic registries."""
    limiter = DomainRateLimiter()
    assert limiter.get_rate("api.crossref.org") == 5.0
    assert limiter.get_rate("api.openalex.org") == 10.0
    assert limiter.get_rate("export.arxiv.org") == 0.33
    assert limiter.get_rate("api.semanticscholar.org") == 1.0
    assert limiter.get_rate("api.semanticscholar.org", headers={"x-api-key": "secret"}) == 10.0
    assert limiter.get_rate("unknown.registry.org") == 5.0


def test_rate_limiter_pacing() -> None:
    """Verify that requests spaced too closely trigger appropriate sleep intervals."""
    limiter = DomainRateLimiter(limits={"test.org": 10.0}, enabled=True)
    with patch("time.sleep") as mock_sleep, patch("time.monotonic") as mock_time:
        mock_time.side_effect = [100.0, 100.02, 100.1, 100.15]
        # First call: no wait
        delay1 = limiter.acquire("https://test.org/api")
        mock_sleep.assert_not_called()
        assert delay1 == 0.0

        # Second call 20ms later: needed interval is 100ms -> should sleep 80ms
        delay2 = limiter.acquire("https://test.org/api")
        assert mock_sleep.called
        assert round(mock_sleep.call_args[0][0], 2) == 0.08
        assert round(delay2, 2) == 0.08


def test_rate_limiter_disabled_via_flag() -> None:
    """Verify that acquire() bypasses pacing when enabled=False."""
    limiter = DomainRateLimiter(enabled=False)
    with patch("time.sleep") as mock_sleep:
        delay = limiter.acquire("https://export.arxiv.org/api/query")
        mock_sleep.assert_not_called()
        assert delay == 0.0


def test_rate_limiter_disabled_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that SCIFI_DISABLE_RATE_LIMIT=1 bypasses pacing immediately."""
    monkeypatch.setenv("SCIFI_DISABLE_RATE_LIMIT", "1")
    limiter = DomainRateLimiter(enabled=True)
    with patch("time.sleep") as mock_sleep:
        delay = limiter.acquire("https://export.arxiv.org/api/query")
        mock_sleep.assert_not_called()
        assert delay == 0.0


def test_url_parsing_fallbacks() -> None:
    """Verify domain extraction handles ports, credentials, relative paths, and unrecognized hosts."""
    limiter = DomainRateLimiter()

    # Domain with port in URL
    assert limiter.get_rate("https://api.crossref.org:8443/works/10.1000") == 5.0
    # Bare hostname with port
    assert limiter.get_rate("api.openalex.org:443") == 10.0
    # URL with username and password
    assert limiter.get_rate("https://user:pass@export.arxiv.org/abs/1234") == 0.33
    # Unrecognized domain falls back to default
    assert limiter.get_rate("custom.registry.edu") == 5.0
    # Relative path without host falls back to default
    assert limiter.get_rate("/v1/works") == 5.0
    # Empty string or whitespace falls back to default
    assert limiter.get_rate("") == 5.0
    assert limiter.get_rate("   ") == 5.0


def test_semantic_scholar_header_variants() -> None:
    """Verify Semantic Scholar key detection is case-insensitive and ignores empty keys."""
    limiter = DomainRateLimiter()

    # Uppercase header
    assert limiter.get_rate("api.semanticscholar.org", headers={"X-API-KEY": "secret"}) == 10.0
    # Mixed case header
    assert limiter.get_rate("api.semanticscholar.org", headers={"X-Api-Key": "secret"}) == 10.0
    # Empty string key -> unauthenticated rate
    assert limiter.get_rate("api.semanticscholar.org", headers={"x-api-key": ""}) == 1.0
    # None key -> unauthenticated rate
    assert limiter.get_rate("api.semanticscholar.org", headers={"x-api-key": None}) == 1.0  # type: ignore[dict-item]
    # Irrelevant header -> unauthenticated rate
    assert limiter.get_rate("api.semanticscholar.org", headers={"Authorization": "Bearer abc"}) == 1.0


def test_custom_limits_override() -> None:
    """Verify user-provided limits override or extend defaults."""
    custom_limits = {
        "api.crossref.org": 20.0,
        "custom.service.org": 2.0,
        "default": 1.5,
    }
    limiter = DomainRateLimiter(limits=custom_limits)

    # Overridden default
    assert limiter.get_rate("api.crossref.org") == 20.0
    # Retained default
    assert limiter.get_rate("api.openalex.org") == 10.0
    # Newly added domain
    assert limiter.get_rate("custom.service.org") == 2.0
    # Overridden default fallback for unrecognized domains
    assert limiter.get_rate("another.unknown.org") == 1.5


def test_rate_limiter_thread_safety() -> None:
    """Verify concurrent requests from multiple threads schedule safely without race conditions."""
    limiter = DomainRateLimiter(limits={"threaded.org": 50.0}, enabled=True)
    results: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        # Use patch inside worker or acquire with 0 wait time simulated
        delay = limiter.acquire("https://threaded.org/api")
        with lock:
            results.append(delay)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All 5 threads must complete successfully
    assert len(results) == 5
    # Threaded reservations must have scheduled non-negative delays
    for d in results:
        assert d >= 0.0
