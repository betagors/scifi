"""End-to-end integration tests for network resilience, rate limiting, and bib auditing.

Validates that real-world workflows such as bibliography auditing, multi-registry
lookups, domain rate pacing, and transient 429/5xx recovery function seamlessly
through the centralized ResilientSession and DomainRateLimiter architecture.
"""

from __future__ import annotations

import json
import threading
from unittest.mock import patch

import pytest
import requests

from scifi.citation_verifier.bib_auditor import audit_bib_content
from scifi.network import DomainRateLimiter, ResilientSession

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
    """Verify that bib audit runs cleanly through ResilientSession and recovers from transient 429.

    Simulates a .bib audit encountering a transient 429 with Retry-After header,
    verifying automatic backoff, retry, and successful resolution without dropping
    citations into UNRESOLVED.
    """
    call_count = 0

    def mock_request(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        resp = requests.Response()

        # First request encounters a transient 429 rate limit
        if call_count == 1:
            resp.status_code = 429
            resp.headers["Retry-After"] = "0.01"
            return resp

        # Retry of paper1 or resolution of paper2 succeeds with 200
        resp.status_code = 200
        if "api.openalex.org" in url:
            payload = {
                "id": "https://openalex.org/W12345",
                "is_retracted": False,
                "cited_by_count": 1000,
            }
        elif "3295222.3295349" in url or "Vaswani" in url:
            payload = {
                "message": {
                    "title": ["Attention Is All You Need"],
                    "author": [{"family": "Vaswani", "given": "Ashish"}],
                    "published-print": {"date-parts": [[2017]]},
                }
            }
        else:
            payload = {
                "message": {
                    "title": ["Deep Residual Learning for Image Recognition"],
                    "author": [{"family": "He", "given": "Kaiming"}],
                    "published-print": {"date-parts": [[2016]]},
                }
            }
        resp._content = json.dumps(payload).encode("utf-8")
        return resp

    with patch.object(requests.Session, "request", side_effect=mock_request), patch("time.sleep") as mock_sleep:
        report = audit_bib_content(SAMPLE_BIB, search_missing=False)

        assert report.total_entries == 2
        # First call backed off and retried, successfully resolving without being dropped
        assert report.verified_count >= 1
        assert report.unresolved_count == 0
        # Call 1 was 429 on CrossRef, call 2 was retry 200 on CrossRef,
        # call 3 was OpenAlex cross-check, followed by paper 2 lookups.
        assert call_count >= 3
        # Verified that time.sleep was invoked for the Retry-After delay
        assert mock_sleep.called
        assert mock_sleep.call_args_list[0][0][0] == 0.01


def test_domain_rate_limiter_pacing_across_sequential_registry_lookups():
    """Verify that ResilientSession paces rapid sequential registry requests to respect domain limits.

    Ensures that inter-request delays are enforced per domain and that distinct
    domains maintain isolated rate pacing buckets.
    """
    limiter = DomainRateLimiter(
        limits={"api.crossref.org": 5.0, "api.openalex.org": 10.0},
        enabled=True,
    )
    session = ResilientSession(rate_limiter=limiter, max_retries=1)

    resp_200 = requests.Response()
    resp_200.status_code = 200
    resp_200._content = b"{}"

    sleep_calls: list[float] = []
    current_time = 1000.0

    def fake_monotonic():
        return current_time

    def fake_sleep(duration):
        nonlocal current_time
        sleep_calls.append(duration)
        current_time += duration

    with (
        patch.object(requests.Session, "request", return_value=resp_200),
        patch("time.monotonic", side_effect=fake_monotonic),
        patch("time.sleep", side_effect=fake_sleep),
    ):
        # 1. First request to crossref (limit = 5.0 req/s -> 0.20s interval)
        session.get("https://api.crossref.org/works/10.1000/1")
        assert len(sleep_calls) == 0  # First request fires without delay

        # 2. Advance time by only 0.05s (too soon; minimum interval is 0.20s -> sleep 0.15s)
        current_time += 0.05
        session.get("https://api.crossref.org/works/10.1000/2")
        assert len(sleep_calls) == 1
        assert pytest.approx(sleep_calls[-1], abs=1e-3) == 0.15

        # 3. Sequential request to OpenAlex (independent domain bucket)
        # Even though Crossref was recently accessed, OpenAlex has no prior request timestamp.
        session.get("https://api.openalex.org/works/W12345")
        assert len(sleep_calls) == 1  # No sleep for independent domain

        # 4. Rapid second request to OpenAlex (limit = 10.0 req/s -> 0.10s interval)
        # Advance time by only 0.02s -> should sleep 0.08s
        current_time += 0.02
        session.get("https://api.openalex.org/works/W67890")
        assert len(sleep_calls) == 2
        assert pytest.approx(sleep_calls[-1], abs=1e-3) == 0.08


def test_bib_audit_e2e_recovers_from_transient_503_and_429():
    """Verify that bib audit seamlessly recovers from mixed transient 503 and 429 responses.

    Validates that a multi-paper bibliography audit survives server unavailability
    (503) and rate limits (429) across different entries, leaving 0 entries unresolved.
    """
    three_papers_bib = """
    @article{p1,
      title = {Attention Is All You Need},
      author = {Vaswani, Ashish},
      year = {2017},
      doi = {10.5555/3295222.3295349}
    }
    @article{p2,
      title = {Deep Residual Learning for Image Recognition},
      author = {He, Kaiming},
      year = {2016},
      doi = {10.1109/CVPR.2016.90}
    }
    @article{p3,
      title = {Language Models are Few-Shot Learners},
      author = {Brown, Tom B.},
      year = {2020},
      doi = {10.5555/3495724.3495883}
    }
    """

    cr_calls: dict[str, int] = {}

    def mock_request(method, url, **kwargs):
        resp = requests.Response()

        # Handle OpenAlex cross-checks cleanly
        if "api.openalex.org" in url:
            resp.status_code = 200
            resp._content = b'{"is_retracted": false, "cited_by_count": 500}'
            return resp

        # Track CrossRef lookups per DOI
        cr_calls[url] = cr_calls.get(url, 0) + 1
        call_num = cr_calls[url]

        # Paper 1 encounters a 503 on its first try to CrossRef
        if "3295222.3295349" in url and call_num == 1:
            resp.status_code = 503
            return resp

        # Paper 2 encounters a 429 with Retry-After on its first try to CrossRef
        if "CVPR.2016.90" in url and call_num == 1:
            resp.status_code = 429
            resp.headers["Retry-After"] = "0.02"
            return resp

        # All retries and other calls succeed
        resp.status_code = 200
        if "3295222.3295349" in url:
            payload = {
                "message": {
                    "title": ["Attention Is All You Need"],
                    "author": [{"family": "Vaswani", "given": "Ashish"}],
                    "published-print": {"date-parts": [[2017]]},
                }
            }
        elif "CVPR.2016.90" in url:
            payload = {
                "message": {
                    "title": ["Deep Residual Learning for Image Recognition"],
                    "author": [{"family": "He", "given": "Kaiming"}],
                    "published-print": {"date-parts": [[2016]]},
                }
            }
        else:
            payload = {
                "message": {
                    "title": ["Language Models are Few-Shot Learners"],
                    "author": [{"family": "Brown", "given": "Tom B."}],
                    "published-print": {"date-parts": [[2020]]},
                }
            }
        resp._content = json.dumps(payload).encode("utf-8")
        return resp

    with patch.object(requests.Session, "request", side_effect=mock_request), patch("time.sleep"):
        report = audit_bib_content(three_papers_bib, search_missing=False)

        assert report.total_entries == 3
        assert report.verified_count == 3
        assert report.unresolved_count == 0
        # Paper 1 CrossRef was attempted twice (503 then 200)
        assert any("3295222.3295349" in u and c == 2 for u, c in cr_calls.items())
        # Paper 2 CrossRef was attempted twice (429 then 200)
        assert any("CVPR.2016.90" in u and c == 2 for u, c in cr_calls.items())


def test_resilient_session_e2e_thread_safe_concurrent_pacing():
    """Verify that ResilientSession handles multi-threaded registry queries safely without errors."""
    limiter = DomainRateLimiter(
        limits={"api.crossref.org": 50.0},
        enabled=True,
    )
    session = ResilientSession(rate_limiter=limiter, max_retries=1)

    resp_200 = requests.Response()
    resp_200.status_code = 200
    resp_200._content = b'{"status": "ok"}'

    results: list[int] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker(i: int):
        try:
            r = session.get(f"https://api.crossref.org/works/10.1000/{i}")
            with lock:
                results.append(r.status_code)
        except Exception as e:
            with lock:
                errors.append(e)

    with patch.object(requests.Session, "request", return_value=resp_200):
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert len(errors) == 0
    assert len(results) == 10
    assert all(code == 200 for code in results)
