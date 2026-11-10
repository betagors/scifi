"""Unit tests for ResilientSession, backoff computation, and Retry-After parsing."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from scifi.config import ScifiConfig
from scifi.network.client import (
    ResilientSession,
    compute_backoff_delay,
    get_session,
    parse_retry_after,
)


def test_parse_retry_after_seconds():
    """Verify integer and float second strings parse correctly with negative clamping."""
    assert parse_retry_after("12") == 12.0
    assert parse_retry_after("0.5") == 0.5
    assert parse_retry_after("0") == 0.0
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after(None) is None
    assert parse_retry_after("invalid") is None
    assert parse_retry_after("") is None
    assert parse_retry_after("   ") is None


def test_parse_retry_after_http_date():
    """Verify RFC 2822 HTTP-date parsing for future and past dates."""
    # Future date (30 seconds ahead)
    future = datetime.now(timezone.utc) + timedelta(seconds=30)
    http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
    delay = parse_retry_after(http_date)
    assert delay is not None
    assert 25.0 <= delay <= 35.0

    # Past date should clamp to 0.0
    past = datetime.now(timezone.utc) - timedelta(seconds=30)
    http_date_past = past.strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(http_date_past) == 0.0


def test_parse_retry_after_clamping():
    """Verify negative and excessive delays are clamped to [0.0, max_backoff]."""
    assert parse_retry_after("-100", max_backoff=30.0) == 0.0
    assert parse_retry_after("120", max_backoff=30.0) == 30.0
    assert parse_retry_after("25", max_backoff=30.0) == 25.0


def test_compute_backoff_delay_bounds():
    """Verify exponential backoff calculation with jitter and max bounds."""
    delay_0 = compute_backoff_delay(0, backoff_factor=1.0)
    assert 1.0 <= delay_0 <= 1.2  # 1.0 * 2^0 + jitter (0.01 to 0.1)

    delay_high = compute_backoff_delay(10, backoff_factor=1.0, max_backoff=30.0)
    assert delay_high <= 30.1

    # Attempt with backoff_factor 0.5
    delay_att1 = compute_backoff_delay(1, backoff_factor=0.5, max_backoff=60.0)
    assert 1.0 <= delay_att1 <= 1.2  # 0.5 * 2^1 + jitter = 1.0 + jitter


def test_resilient_session_retries_on_429():
    """Verify 429 responses trigger backoff and succeed on subsequent 200."""
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
    """Verify terminal 429 response is returned when max retries are exhausted."""
    session = ResilientSession(max_retries=2, backoff_factor=0.01)
    session.rate_limiter.enabled = False

    resp_429 = requests.Response()
    resp_429.status_code = 429

    with patch.object(requests.Session, "request", return_value=resp_429) as mock_req, \
         patch("time.sleep"):
        final_resp = session.request("GET", "https://api.crossref.org/works/10.1234")
        assert final_resp.status_code == 429
        assert mock_req.call_count == 3  # initial + 2 retries


def test_resilient_session_transient_5xx_retries():
    """Verify 502, 503, 504 errors trigger retries and return terminal 503 on exhaustion."""
    session = ResilientSession(max_retries=3, backoff_factor=0.01)
    session.rate_limiter.enabled = False

    resp_502 = requests.Response()
    resp_502.status_code = 502

    resp_503 = requests.Response()
    resp_503.status_code = 503

    resp_504 = requests.Response()
    resp_504.status_code = 504

    resp_200 = requests.Response()
    resp_200.status_code = 200

    # 1. Successful retry across 502 -> 504 -> 200
    with patch.object(requests.Session, "request", side_effect=[resp_502, resp_504, resp_200]) as mock_req, \
         patch("time.sleep"):
        final_resp = session.request("GET", "https://api.openalex.org/works")
        assert final_resp.status_code == 200
        assert mock_req.call_count == 3

    # 2. Exhaustion on persistent 503
    with patch.object(requests.Session, "request", return_value=resp_503) as mock_req, \
         patch("time.sleep"):
        final_resp = session.request("GET", "https://api.openalex.org/works")
        assert final_resp.status_code == 503
        assert mock_req.call_count == 4  # 1 initial + 3 retries


def test_resilient_session_connection_error_and_timeout():
    """Verify network connection and timeout errors retry and eventual re-raise."""
    session = ResilientSession(max_retries=2, backoff_factor=0.01)
    session.rate_limiter.enabled = False

    # 1. Connection error recovered on retry
    resp_200 = requests.Response()
    resp_200.status_code = 200

    with patch.object(
        requests.Session,
        "request",
        side_effect=[requests.exceptions.ConnectionError("Connection reset"), resp_200],
    ) as mock_req, patch("time.sleep") as mock_sleep:
        resp = session.request("GET", "https://export.arxiv.org/api/query")
        assert resp.status_code == 200
        assert mock_req.call_count == 2
        assert mock_sleep.called

    # 2. Persistent timeout re-raises RequestException after exhaustion
    with patch.object(
        requests.Session,
        "request",
        side_effect=requests.exceptions.Timeout("Read timed out"),
    ) as mock_req, patch("time.sleep"):
        with pytest.raises(requests.exceptions.Timeout) as exc_info:
            session.request("GET", "https://export.arxiv.org/api/query")
        assert "Read timed out" in str(exc_info.value)
        assert mock_req.call_count == 3  # 1 initial + 2 retries


def test_resilient_session_caller_header_override():
    """Verify caller-provided headers override session-level default headers."""
    session = ResilientSession()
    session.rate_limiter.enabled = False

    # Check default User-Agent is present on session
    assert "User-Agent" in session.headers
    assert "SciFi-Toolkit/1.0" in session.headers["User-Agent"]

    # When caller specifies custom User-Agent, it must be passed through to super().request
    custom_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CustomScraper/1.0"
    resp_200 = requests.Response()
    resp_200.status_code = 200

    with patch.object(requests.Session, "request", return_value=resp_200) as mock_req:
        session.get("https://doi.org/10.1234/test", headers={"User-Agent": custom_ua, "Accept": "text/html"})
        assert mock_req.called
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["User-Agent"] == custom_ua
        assert call_kwargs["headers"]["Accept"] == "text/html"


def test_resilient_session_s2_api_key_injection():
    """Verify s2_api_key from config is injected for Semantic Scholar calls if not provided."""
    cfg = ScifiConfig(s2_api_key="test-s2-key-12345", email="researcher@test.org")
    session = ResilientSession(config=cfg)
    session.rate_limiter.enabled = False

    resp_200 = requests.Response()
    resp_200.status_code = 200

    # 1. Hitting semantic scholar without x-api-key -> should inject s2_api_key
    with patch.object(requests.Session, "request", return_value=resp_200) as mock_req:
        session.get("https://api.semanticscholar.org/graph/v1/paper/10.1234")
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "test-s2-key-12345"

    # 2. Hitting semantic scholar with custom x-api-key -> caller takes precedence
    with patch.object(requests.Session, "request", return_value=resp_200) as mock_req:
        session.get(
            "https://api.semanticscholar.org/graph/v1/paper/10.1234",
            headers={"x-api-key": "caller-key-override"},
        )
        call_kwargs = mock_req.call_args[1]
        assert call_kwargs["headers"]["x-api-key"] == "caller-key-override"

    # 3. Hitting Crossref -> s2_api_key must NOT be injected
    with patch.object(requests.Session, "request", return_value=resp_200) as mock_req:
        session.get("https://api.crossref.org/works/10.1234")
        call_kwargs = mock_req.call_args[1]
        if "headers" in call_kwargs and call_kwargs["headers"]:
            assert "x-api-key" not in call_kwargs["headers"]


def test_get_session_singleton():
    """Verify get_session returns a singleton ResilientSession instance."""
    s1 = get_session()
    s2 = get_session()
    assert isinstance(s1, ResilientSession)
    assert s1 is s2
