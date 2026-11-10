# Centralized Rate-Limiting & Network Resilience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a centralized, thread-safe rate-limiting and network resilience layer (`scifi/network/`) with proactive domain pacing, reactive 429/5xx exponential backoff, `Retry-After` parsing, and polite identity headers, and refactor all external registry consumers across SciFi to use it.

**Architecture:** A dedicated `scifi/network/` module provides `DomainRateLimiter` (token bucket / inter-request interval with dynamic API key awareness) and `ResilientSession` (subclassing `requests.Session` with reactive backoff, jitter, and polite headers). All fetchers (`fetchers.py`, `bib_auditor.py`, `resolver.py`, `argus/searcher.py`, `semantic_scholar.py`, `fetcher.py`) are refactored to route requests through `get_session()`.

**Tech Stack:** Python 3.12+, `requests`, `urllib.parse`, `email.utils`, `threading`, `time`, `math`, `pytest`.

**Spec:** `docs/superpowers/specs/2026-11-09-rate-limiting-and-network-resilience-design.md`

## Global Constraints

- Python >= 3.12 compatibility with strict type hints and dataclasses.
- Zero new mandatory external dependencies; pure standard library + `requests`.
- Thread-safe domain rate-limiting via `threading.Lock()`.
- Standard `requests.Session` contract: return terminal `Response` on persistent HTTP 429/5xx, re-raise `RequestException` on network transport failures.
- Zero regressions: all 429 existing unit tests must continue passing.
- Fast offline testing: bypass rate limiting in tests when `SCIFI_DISABLE_RATE_LIMIT=1` or `enabled=False`.

## Review Focus

1. **HTTP-Date `Retry-After` Header:** Headers formatted as RFC 2822 dates (e.g. `Wed, 21 Oct 2026 07:28:00 GMT`) must parse cleanly into positive delay offsets without failing `float()` conversion.
2. **Clamping & Bounding Backoff Delays:** Negative delays or absurdly large `Retry-After` values must be bounded between `0.0` and `max_backoff` (default: 60.0s).
3. **Transient Network Errors (`Timeout` and `ConnectionError`):** Must trigger backoff and retries before re-raising the terminal `RequestException`.
4. **URL Hostname Parsing Fallbacks:** Irregular URLs (ports, missing schemes, relative paths) must resolve cleanly to the `"default"` domain limit without raising `KeyError` or `ValueError`.
5. **Thread Concurrency Under Lock:** Multiple threads hitting the same domain in rapid succession must be serialized so that the configured requests-per-second limit is strictly enforced.

---

### Task 1: Core Domain Rate Limiter (`scifi/network/rate_limiter.py`)

**Files:**
- Create: `scifi/network/__init__.py`
- Create: `scifi/network/rate_limiter.py`
- Test: `tests/test_rate_limiter.py`

**Interfaces:**
- Consumes: `os.getenv("SCIFI_DISABLE_RATE_LIMIT")`, `urllib.parse.urlparse`, `time.monotonic`, `threading.Lock`.
- Produces:
  - `DEFAULT_DOMAIN_LIMITS: dict[str, float]`
  - `class DomainRateLimiter(limits: Optional[dict[str, float]] = None, enabled: bool = True)`
  - `DomainRateLimiter.acquire(url: str, headers: Optional[dict[str, str]] = None) -> float` (returns waited delay)
  - `DomainRateLimiter.get_rate(domain: str, headers: Optional[dict[str, str]] = None) -> float`

- [ ] **Step 1: Write the failing tests in `tests/test_rate_limiter.py`**

```python
import os
import time
from unittest.mock import patch
from scifi.network.rate_limiter import DomainRateLimiter, DEFAULT_DOMAIN_LIMITS

def test_default_domain_rates():
    limiter = DomainRateLimiter()
    assert limiter.get_rate("api.crossref.org") == 5.0
    assert limiter.get_rate("api.openalex.org") == 10.0
    assert limiter.get_rate("export.arxiv.org") == 0.33
    assert limiter.get_rate("api.semanticscholar.org") == 1.0
    assert limiter.get_rate("api.semanticscholar.org", headers={"x-api-key": "secret"}) == 10.0
    assert limiter.get_rate("unknown.registry.org") == 5.0

def test_rate_limiter_pacing():
    limiter = DomainRateLimiter(limits={"test.org": 10.0}, enabled=True)
    with patch("time.sleep") as mock_sleep, patch("time.monotonic") as mock_time:
        mock_time.side_effect = [100.0, 100.02, 100.1, 100.15]
        # First call: no wait
        limiter.acquire("https://test.org/api")
        mock_sleep.assert_not_called()

        # Second call 20ms later: needed interval is 100ms -> should sleep 80ms
        limiter.acquire("https://test.org/api")
        assert mock_sleep.called
        assert round(mock_sleep.call_args[0][0], 2) == 0.08

def test_rate_limiter_disabled_via_flag():
    limiter = DomainRateLimiter(enabled=False)
    with patch("time.sleep") as mock_sleep:
        limiter.acquire("https://export.arxiv.org/api/query")
        mock_sleep.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_rate_limiter.py -v`  
Expected: FAIL with ModuleNotFoundError: No module named 'scifi.network'

- [ ] **Step 3: Implement `scifi/network/__init__.py` and `scifi/network/rate_limiter.py`**

Implement `DomainRateLimiter`:
- Extract domain via `urllib.parse.urlsplit(url).netloc.split(":")[0].lower()`.
- Thread-safe tracking of `last_request_time[domain]` protected by `threading.Lock()`.
- Dynamic key check for `api.semanticscholar.org` looking for `x-api-key` in `headers`.
- `acquire()` computes wait time `interval - (now - last_time)`, sleeps if > 0, updates timestamp.
- Respects `enabled` parameter and `os.getenv("SCIFI_DISABLE_RATE_LIMIT") == "1"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_rate_limiter.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/network/__init__.py scifi/network/rate_limiter.py tests/test_rate_limiter.py
git commit -m "feat(network): implement domain rate limiter with dynamic key pacing"
```

---

### Task 2: Centralized Resilient Session with Backoff (`scifi/network/client.py`)

**Files:**
- Create: `scifi/network/client.py`
- Modify: `scifi/network/__init__.py`
- Test: `tests/test_resilient_session.py`

**Interfaces:**
- Consumes: `DomainRateLimiter`, `requests.Session`, `scifi.config.resolve_config`.
- Produces:
  - `parse_retry_after(header_val: Optional[str]) -> Optional[float]`
  - `compute_backoff_delay(attempt: int, backoff_factor: float = 0.5, max_backoff: float = 60.0) -> float`
  - `class ResilientSession(requests.Session)`
  - `get_session() -> ResilientSession`

- [ ] **Step 1: Write the failing tests in `tests/test_resilient_session.py`**

```python
from unittest.mock import MagicMock, patch
import requests
import pytest
from scifi.network.client import (
    ResilientSession,
    parse_retry_after,
    compute_backoff_delay,
    get_session,
)

def test_parse_retry_after_seconds():
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid") is None

def test_parse_retry_after_http_date():
    from datetime import datetime, timezone, timedelta
    future = datetime.now(timezone.utc) + timedelta(seconds=30)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    delay = parse_retry_after(http_date)
    assert delay is not None
    assert 25.0 <= delay <= 35.0

def test_compute_backoff_delay_bounds():
    delay_0 = compute_backoff_delay(0, backoff_factor=1.0)
    assert 1.0 <= delay_0 <= 1.2  # Includes jitter
    delay_high = compute_backoff_delay(10, backoff_factor=1.0, max_backoff=30.0)
    assert delay_high <= 30.1

def test_resilient_session_retries_on_429():
    session = ResilientSession(max_retries=2, backoff_factor=0.01)
    session.rate_limiter.enabled = False

    resp_429 = requests.Response()
    resp_429.status_code = 429
    resp_429.headers["Retry-After"] = "0.01"

    resp_200 = requests.Response()
    resp_200.status_code = 200

    with patch.object(requests.Session, "request", side_effect=[resp_429, resp_200]) as mock_req, \
         patch("time.sleep") as mock_sleep:
        final_resp = session.request("GET", "https://api.crossref.org/works/10.1234")
        assert final_resp.status_code == 200
        assert mock_req.call_count == 2
        assert mock_sleep.called

def test_resilient_session_returns_terminal_response_on_exhaustion():
    session = ResilientSession(max_retries=2, backoff_factor=0.01)
    session.rate_limiter.enabled = False

    resp_429 = requests.Response()
    resp_429.status_code = 429

    with patch.object(requests.Session, "request", return_value=resp_429) as mock_req, \
         patch("time.sleep"):
        final_resp = session.request("GET", "https://api.crossref.org/works/10.1234")
        assert final_resp.status_code == 429
        assert mock_req.call_count == 3  # initial + 2 retries
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_resilient_session.py -v`  
Expected: FAIL with ImportError / ModuleNotFoundError

- [ ] **Step 3: Implement `scifi/network/client.py` and export in `scifi/network/__init__.py`**

Implement:
- `parse_retry_after(header_val)`: tries `float(header_val)`, fallback to `email.utils.parsedate_to_datetime()`. Clamps negative values to `0.0`.
- `compute_backoff_delay(attempt, backoff_factor, max_backoff)`: `min(max_backoff, backoff_factor * (2 ** attempt)) + random.uniform(0.01, 0.1)`.
- `ResilientSession(requests.Session)`:
  - Initializes `self.rate_limiter = DomainRateLimiter()`.
  - Sets default `User-Agent`: `SciFi-Toolkit/1.0 (academic-researcher; +https://github.com/scifi-toolkit; mailto:{email})` resolving `email` from `resolve_config().email`.
  - In `request(method, url, **kwargs)`:
    - Calls `self.rate_limiter.acquire(url, headers=kwargs.get("headers"))`.
    - Handles status codes `429, 502, 503, 504` and `RequestException` retries.
    - Respects `Retry-After` if present, falls back to `compute_backoff_delay`.
    - Returns terminal `Response` on HTTP status codes; raises `RequestException` on persistent connection errors.
- `get_session()` singleton function.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_resilient_session.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/network/client.py scifi/network/__init__.py tests/test_resilient_session.py
git commit -m "feat(network): implement ResilientSession with 429 backoff and polite headers"
```

---

### Task 3: Refactor Citation Verifiers & Bib Auditor to use Centralized Network Client

**Files:**
- Modify: `scifi/citation_verifier/fetchers.py`
- Modify: `scifi/citation_verifier/bib_auditor.py`
- Modify: `scifi/citation_verifier/identifiers.py`
- Test: `tests/test_citation_verifier.py`, `tests/test_bib_auditor.py`

**Interfaces:**
- Consumes: `scifi.network.get_session`.
- Preserves: All existing signatures and models (`CrossRefFetcher.fetch`, `OpenAlexFetcher.fetch`, `ArXivFetcher.fetch`, `DataCiteFetcher.fetch`, `audit_bib_content`, `search_identifier_by_title`).

- [ ] **Step 1: Write test verifying fetchers route through resilient session**

Add test to `tests/test_citation_verifier.py`:
```python
from unittest.mock import patch
import requests
from scifi.citation_verifier.fetchers import CrossRefFetcher

def test_crossref_fetcher_uses_resilient_session():
    with patch("scifi.citation_verifier.fetchers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"message": {"title": ["Test Paper"]}}'
        mock_session.get.return_value = resp

        meta = CrossRefFetcher.fetch("10.1000/182")
        assert meta is not None
        assert mock_session.get.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_citation_verifier.py -k test_crossref_fetcher_uses_resilient_session -v`  
Expected: FAIL (mock_session.get not called)

- [ ] **Step 3: Refactor `fetchers.py`, `bib_auditor.py`, and `identifiers.py`**

- In `scifi/citation_verifier/fetchers.py`:
  - Import `get_session` from `scifi.network`.
  - Replace `requests.get(...)` in `CrossRefFetcher.fetch`, `OpenAlexFetcher.fetch`, `ArXivFetcher.fetch`, `DataCiteFetcher.fetch`, and `resolve_citation` with `get_session().get(...)`.
- In `scifi/citation_verifier/bib_auditor.py`:
  - Import `get_session` from `scifi.network`.
  - Replace `requests.get(...)` in `search_identifier_by_title` with `get_session().get(...)`.
- In `scifi/citation_verifier/identifiers.py`:
  - Replace `requests.get(clean_q, headers=headers...)` with `get_session().get(clean_q, headers=headers...)`. Caller's `Mozilla/5.0` header is retained.

- [ ] **Step 4: Run citation verifier and bib auditor test suites**

Run: `uv run pytest tests/test_citation_verifier.py tests/test_bib_auditor.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/citation_verifier/fetchers.py scifi/citation_verifier/bib_auditor.py scifi/citation_verifier/identifiers.py tests/test_citation_verifier.py
git commit -m "refactor(citation_verifier): route registry queries through ResilientSession"
```

---

### Task 4: Refactor Literature Discovery & Semantic Scholar to use Centralized Network Client

**Files:**
- Modify: `scifi/literature/semantic_scholar.py`
- Modify: `scifi/literature/resolver.py`
- Modify: `scifi/literature/fetcher.py`
- Modify: `scifi/argus/searcher.py`
- Test: `tests/test_literature_semantic_scholar.py`, `tests/test_literature_resolver.py`, `tests/test_argus.py`

**Interfaces:**
- Consumes: `scifi.network.get_session`.
- Preserves: Full backward compatibility for tests patching `requests.get` via module aliases or session delegation.

- [ ] **Step 1: Inspect and run existing literature tests to establish baseline**

Run: `uv run pytest tests/test_literature_semantic_scholar.py tests/test_literature_resolver.py tests/test_argus.py -v`  
Expected: All pass.

- [ ] **Step 2: Refactor `semantic_scholar.py`**

- Update `SemanticScholarClient`:
  - Route HTTP calls in `_execute_request` through `get_session()`.
  - Keep `format_paper_id`, `_map_intents`, and existing method signatures intact.
  - Simplify 429 retry code by delegating to `ResilientSession`'s native 429 backoff engine.
  - Ensure compatibility with tests mocking `requests.get`.

- [ ] **Step 3: Refactor `resolver.py`, `fetcher.py`, and `argus/searcher.py`**

- In `scifi/literature/resolver.py`:
  - Route all OpenAlex, Crossref, and preprint queries through `get_session().get()`.
  - Retain module-level `requests` delegation so tests with `@patch("scifi.literature.resolver.requests.get")` seamlessly intercept calls.
- In `scifi/literature/fetcher.py`:
  - Route PDF and Unpaywall lookups through `get_session().get()`.
- In `scifi/argus/searcher.py`:
  - Route OpenAlex and Crossref lookups through `get_session().get()`.

- [ ] **Step 4: Run literature, resolver, and argus test suites**

Run: `uv run pytest tests/test_literature_semantic_scholar.py tests/test_literature_resolver.py tests/test_argus.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scifi/literature/semantic_scholar.py scifi/literature/resolver.py scifi/literature/fetcher.py scifi/argus/searcher.py
git commit -m "refactor(literature,argus): standardize on centralized ResilientSession"
```

---

### Task 5: End-to-End Regression & Integration Verification

**Files:**
- Create: `tests/test_network_e2e.py`
- Test: All repository tests (`uv run pytest`)

**Interfaces:**
- Validates: Rapid sequential `.bib` audit simulation with rate limiter active, verifying zero 429 dropped records and correct pacing.

- [ ] **Step 1: Write integration test in `tests/test_network_e2e.py`**

```python
from unittest.mock import patch
import requests
from scifi.citation_verifier.bib_auditor import audit_bib_content
from scifi.network import get_session

SAMPLE_BIB = """
@article{paper1,
  title = {Attention Is All You Need},
  author = {Vaswani, Ashish},
  year = {2017},
  doi = {10.5555/3295222.3295349}
}
@article{paper2,
  title = {Deep Residual Learning for Image Recognition},
  author = {He, Kaiming},
  year = {2016},
  doi = {10.1109/CVPR.2016.90}
}
"""

def test_bib_audit_e2e_with_resilient_session():
    # Verify that bib audit runs cleanly through ResilientSession
    # and recovers gracefully from simulated transient 429
    session = get_session()
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = requests.Response()
        if call_count == 1:
            resp.status_code = 429
            resp.headers["Retry-After"] = "0.01"
            return resp
        resp.status_code = 200
        resp._content = b'{"message": {"title": ["Verified Title"], "author": [{"family": "Vaswani", "given": "Ashish"}]}}'
        return resp

    with patch.object(requests.Session, "request", side_effect=mock_request), \
         patch("time.sleep"):
        report = audit_bib_content(SAMPLE_BIB, search_missing=False)
        assert report.total_entries == 2
        # First call backed off and retried, successfully resolving
        assert report.verified_count >= 1
```

- [ ] **Step 2: Run new end-to-end integration test**

Run: `uv run pytest tests/test_network_e2e.py -v`  
Expected: PASS

- [ ] **Step 3: Run entire repository test suite to verify 0 regressions**

Run: `uv run pytest -q`  
Expected: 429+ passed in ~15s with 0 errors.

- [ ] **Step 4: Commit**

```bash
git add tests/test_network_e2e.py
git commit -m "test(network): add end-to-end resilient session and bib auditor integration test"
```
