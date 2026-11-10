# SciFi Centralized Rate-Limiting & Network Resilience Engine Design Document

**Date:** 2026-11-09  
**Status:** In Review  
**Topic:** Centralized proactive pacing, reactive 429/5xx exponential backoff, retry-after handling, and polite headers across all academic registries.

---

## 1. Intent & The Why

SciFi integrates with multiple academic registries and literature APIs:
- **Crossref Works API** (DOI metadata and Crossmark retractions/errata)
- **OpenAlex API** (works, author profiles, and title resolution)
- **Semantic Scholar Graph API** (citation contexts, influence, and intents)
- **arXiv Export API** (preprints, withdrawal notices, and categories)
- **DataCite API** (dataset and non-traditional publication DOIs)
- **Unpaywall API** (open access PDF locations)

Prior to this work, only `SemanticScholarClient` had rate-limiting defense. All other modules (`CrossRefFetcher`, `OpenAlexFetcher`, `DataCiteFetcher`, `ArxivFetcher`, `bib_auditor`, `resolver`, `argus/searcher`, and `literature/fetcher`) fired unthrottled `requests.get()` calls.

When auditing a bibliography with dozens of citations or resolving references in bulk:
1. Unthrottled request bursts trigger HTTP `429 Too Many Requests` or connection bans from registry endpoints.
2. The calling modules catch 429 responses as generic HTTP errors and return `None`.
3. Valid papers are silently misclassified as `UNRESOLVED` or unverified, causing false alarms in literature audits and peer review checks.
4. External APIs with strict rate limits (e.g., arXiv's 1 req / 3s policy or OpenAlex's polite pool) are not respected.

This project delivers a centralized, reusable network module (`scifi/network/`) providing **proactive domain-based pacing**, **reactive 429/5xx exponential backoff**, **Retry-After header parsing**, and **polite user-agent and contact injection** across all external HTTP operations in SciFi.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- **Proactive Request Pacing (Token Bucket / Rate Limiter):** Enforce per-host request rate limits before requests hit the network to prevent throttling proactively:
  - OpenAlex: 10 req/s default.
  - Crossref: 5 req/s default (polite pool).
  - Semantic Scholar: 1 req/s without API key, 10 req/s with key.
  - arXiv: 0.33 req/s (max 1 req every 3 seconds per arXiv API TOS).
  - DataCite & Unpaywall: 5 req/s default.
  - Default/fallback for other hosts: 5 req/s.
- **Reactive Retry & Exponential Backoff:**
  - Catch HTTP `429 Too Many Requests`, `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout`, as well as transient network connection timeouts.
  - Parse and honor `Retry-After` headers (both integer seconds and HTTP-date strings).
  - When `Retry-After` is absent, apply exponential backoff with jitter: `min(max_delay, backoff_factor * (2 ** attempt)) + random.uniform(0, 0.1)`.
  - Configurable `max_retries` (default: 3).
- **Polite Identity Headers & Configuration Integration:**
  - Automatically inject a standardized `User-Agent`: `SciFi-Toolkit/1.0 (academic-researcher; +https://github.com/scifi-toolkit; mailto:contact@scifi-toolkit.org)`.
  - Integrate directly with `scifi.config.resolve_config()` to pull configured `email` and API keys (e.g. `s2_api_key`).
- **Seamless Consumer Integration:**
  - Refactor all existing fetchers and network consumers to use the centralized `ResilientSession` / `get_session()`.
  - Deprecate and remove redundant bespoke retry code in `scifi/literature/semantic_scholar.py`.
- **Test Ergonomics & Offline Isolation:**
  - Support instant bypassing or mock-time acceleration via environment variable (`SCIFI_DISABLE_RATE_LIMIT=1`) or session parameter so existing and new tests execute with zero artificial latency.

### Non-Goals
- Adding asynchronous networking (e.g., `aiohttp` or `httpx` async event loops). SciFi's architecture and CLI/FastMCP interfaces are synchronous; keeping the client synchronous avoids thread/event-loop mismatch.
- Implementing a persistent disk cache in this network client (SciFi already has dedicated SQLite / file caching in `scifi/literature/store.py` and `scifi/cache.py`).

### Anti-Goals
- **No Silent 429 Swallowing:** 429 errors must not be quietly converted into `None` before retries are exhausted. If retries are exhausted, log a clear warning with response details and return the terminal `Response` object.
- **No Heavy Third-Party Dependencies:** Implement the token bucket and backoff using Python standard library (`time`, `threading`, `math`, `urllib.parse`, `email.utils`) on top of existing `requests`. Do not add heavy dependencies like `tenacity` or `ratelimit`.

---

## 3. Constraints

- **Python Compatibility:** Python >= 3.12, strict type hints, dataclasses.
- **Zero New Mandatory External Dependencies:** Relies purely on standard library + `requests`.
- **Thread Safety:** Pacing state (token bucket / timestamps) must be protected by thread locks (`threading.Lock`) so multi-threaded calls (e.g., in MCP servers or future concurrent workers) do not corrupt rate-limit tracking.
- **100% Backward Compatibility:** All existing function signatures in `fetchers.py`, `bib_auditor.py`, `resolver.py`, `semantic_scholar.py`, and `argus/searcher.py` must retain their input parameters (`timeout`, etc.) and return types.
- **Test Regression Safety:** All 429 existing unit tests must pass without failure.

---

## 4. Approaches Considered

| Approach | Description | Trade-offs & Evaluation | Decision |
|---|---|---|---|
| **1. Centralized Resilient Client with Proactive Pacing & Reactive Backoff** | A dedicated `scifi/network/` package exposing `ResilientSession` and `get_session()`. Proactive domain token buckets pace outgoing calls; reactive handlers catch 429/5xx and respect `Retry-After` with exponential backoff. All existing fetchers route through this client. | **Pros:** Prevents 429 bans before they happen; uniform retry behavior across all registries; eliminates code duplication; thread-safe; easily bypassed in test suites.<br>**Cons:** Requires refactoring multiple fetcher files. | **SELECTED (User approved)** |
| **2. Reactive-Only Transport Adapters via `urllib3.util.Retry`** | Mount `HTTPAdapter(max_retries=Retry(...))` on `requests.Session`. | **Pros:** Minimal boilerplate.<br>**Cons:** Zero proactive pacing. Burst requests (such as 50 `.bib` entries in `sf bib audit`) hammer registries and rely entirely on getting throttled before backing off. Fails arXiv TOS. | Rejected |
| **3. Individual Per-Module Retry Logic** | Copy bespoke retry loops into each fetcher file. | **Pros:** Isolated edits.<br>**Cons:** High code duplication, inconsistent behaviors, no global domain rate limit coordination. | Rejected |

---

## 5. System Architecture & Detailed Design

### 5.1 Architecture Diagram

```
+-----------------------------------------------------------------------------------+
|                            SciFi Calling Modules                                  |
|   citation_verifier/fetchers.py    bib_auditor.py     literature/resolver.py      |
|   argus/searcher.py                literature/fetcher.py   semantic_scholar.py    |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
+-----------------------------------------------------------------------------------+
|                        scifi.network.client.ResilientSession                      |
|                                                                                   |
|  1. Proactive Domain Pacer (scifi.network.rate_limiter.DomainRateLimiter)         |
|     - Token bucket / minimum inter-request interval per domain                    |
|     - Dynamic rate calculation (e.g. 10 req/s with API key vs 1 req/s without)    |
|     - Thread-safe via threading.Lock()                                            |
|     - Configurable rates: OpenAlex (10/s), Crossref (5/s), arXiv (0.33/s), etc.   |
|                                                                                   |
|  2. Default Polite Header Injector                                                |
|     - Session-level default: User-Agent: SciFi-Toolkit/1.0 (+https://...)         |
|     - Request-level headers override defaults (preserves Mozilla/5.0 in redirects)|
|     - Auto-configures email / API keys via scifi.config.resolve_config()          |
|                                                                                   |
|  3. Reactive Retry & Backoff Engine                                               |
|     - Catches 429, 502, 503, 504, ConnectionError, Timeout                        |
|     - Reads Retry-After header (seconds or HTTP date)                             |
|     - Exponential backoff with jitter fallback                                    |
|     - Standard requests contract: returns terminal Response on HTTP 429/5xx,      |
|       raises RequestException if network connection fails permanently             |
+-----------------------------------------------------------------------------------+
                                         │
                                         ▼
                           requests.Session.get / post
                                         │
                                         ▼
                External Registries (Crossref, OpenAlex, arXiv, etc.)
```

### 5.2 Module Layout

```text
scifi/network/
├── __init__.py           # Exports get_session, ResilientSession, DomainRateLimiter, Config
├── rate_limiter.py       # DomainRateLimiter, TokenBucket, rate limit registry configurations
└── client.py             # ResilientSession, request execution, Retry-After parsing, backoff
```

### 5.3 Technical Decisions Settled

1. **Terminal Failure Behavior (Raise vs. Return Contract):**
   - `ResilientSession.request()` conforms strictly to `requests.Session` conventions.
   - For HTTP responses (including persistent 429 or 5xx after retries are exhausted), `request()` logs a clear warning and returns the terminal `requests.Response` object. Callers can inspect `resp.status_code`.
   - For network connection or timeout errors (`requests.exceptions.ConnectionError`, `requests.exceptions.Timeout`), `request()` raises the underlying `requests.exceptions.RequestException` after retries are exhausted.
2. **Semantic Scholar Dynamic Rate Limiting:**
   - `DomainRateLimiter.acquire(url, headers=...)` dynamically inspects whether an API key (`x-api-key` header or configured `s2_api_key`) is present.
   - If present, `api.semanticscholar.org` is permitted up to 10.0 req/s. If unauthenticated, it is capped at 1.0 req/s.
3. **Configuration Source of Truth:**
   - `scifi.network` imports `resolve_config()` from `scifi.config`.
   - Default contact email in `User-Agent` and default `s2_api_key` are loaded automatically from `~/.scifi/config.json` / `scifi.toml`.
4. **Header Precedence & Anti-Bot Compatibility:**
   - `ResilientSession` sets polite defaults on the session level (`session.headers`).
   - If a caller specifies explicit headers (such as `scifi/citation_verifier/identifiers.py` using `Mozilla/5.0...`), the caller's request headers take precedence, preserving anti-bot compatibility.
5. **Test Compatibility & Mocking:**
   - In modules like `scifi/literature/resolver.py` and `scifi/literature/semantic_scholar.py` where unit tests mock `requests.get`, expose a module-level alias `requests = get_session()` or delegate `requests.get` so existing `@patch("...requests.get")` decorators continue intercepting calls seamlessly with 0 test breakage.

---

## 6. What's Left to the Builder

- Exact jitter calculation formula (`random.uniform(0.01, 0.1)`).
- Log message formatting (`logger.info` vs `logger.warning`) during backoff.
- Unit tests in `tests/test_network.py` verifying rate limiter timing, 429 backoff, and header merging.
- Ensuring `pytest` runs at full speed with mock time or rate limiting disabled during standard test runs.

---
