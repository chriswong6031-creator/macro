"""Tests for engine/gdelt_client.py — shared GDELT fetch client.

No live network: all HTTP calls are mocked.  Covers:
  - Cross-process throttle: spacing >= min_interval across two calls.
  - 429 -> backoff -> success path: sleeps the right intervals, returns articles.
  - Final-failure path (429 on every attempt): returns (None, 'rate_limited').
  - Failure never cached: a rate_limited result is NOT written to cache_path.
  - Success cached: a successful result IS written to cache_path, and a second
    call with a fresh cache returns the cached articles without hitting the network.
  - no_articles reason: empty artlist -> ([], 'no_articles').
  - Non-200 -> (None, 'fetch_error').
  - Non-JSON content-type -> (None, 'rate_limited') (GDELT rate-limit text pattern).

Run:  python3 -m pytest tests/test_gdelt_client.py -x -q
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import gdelt_client as _gc


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_response(status: int, json_body: dict | None = None, content_type: str = "application/json"):
    """Build a minimal mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.headers = {"Content-Type": content_type}
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _gdelt_body(titles: list[str]) -> dict:
    """Minimal GDELT artlist JSON with the given titles."""
    return {
        "articles": [
            {"title": t, "url": f"https://example.com/{i}", "domain": "example.com",
             "seendate": "20260710T120000Z"}
            for i, t in enumerate(titles)
        ]
    }


_SAMPLE_PARAMS = {"query": "tariff", "mode": "artlist", "format": "json", "maxrecords": "10"}


# ── throttle tests ────────────────────────────────────────────────────────────

def test_throttle_spacing_between_two_calls(tmp_path):
    """Two sequential calls must be spaced >= min_interval seconds apart."""
    timestamps: list[float] = []

    def _fake_requests_get(*args, **kwargs):
        timestamps.append(time.monotonic())
        return _make_response(200, _gdelt_body(["headline one"]))

    min_interval = 0.05  # short for speed
    stamp_file = tmp_path / "gdelt" / "last_request"

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=_fake_requests_get):
        # Ensure parent dir exists
        stamp_file.parent.mkdir(parents=True, exist_ok=True)

        _gc.get_articles(_SAMPLE_PARAMS, min_interval=min_interval)
        _gc.get_articles(_SAMPLE_PARAMS, min_interval=min_interval)

    assert len(timestamps) == 2, "expected exactly two network requests"
    gap = timestamps[1] - timestamps[0]
    assert gap >= min_interval * 0.9, (
        f"requests were only {gap:.4f}s apart; expected >= {min_interval}s"
    )


# ── retry / backoff tests ─────────────────────────────────────────────────────

def test_429_then_success(tmp_path):
    """429 on attempt-0 -> sleep 30s -> success on attempt-1 -> returns articles."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    responses = [
        _make_response(429),
        _make_response(200, _gdelt_body(["Tariff news headline"])),
    ]

    sleep_calls: list[float] = []

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=responses), \
         patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):

        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is not None and len(articles) == 1
    assert articles[0]["title"] == "Tariff news headline"
    assert reason is None
    # Must have slept the first-retry interval
    assert any(s >= 29 for s in sleep_calls), (
        f"expected a sleep >= 29s after first 429; got sleep_calls={sleep_calls}"
    )


def test_429_all_attempts_returns_none(tmp_path):
    """Three consecutive 429s -> (None, 'rate_limited')."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    responses = [_make_response(429)] * 3

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=responses), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is None
    assert reason == "rate_limited"


def test_non_200_returns_fetch_error(tmp_path):
    """HTTP 500 -> (None, 'fetch_error')."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", return_value=_make_response(500)), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is None
    assert reason == "fetch_error"


def test_non_json_content_type_rate_limited(tmp_path):
    """200 + text/plain content-type (GDELT rate-limit text body) -> rate_limited."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    # Three non-JSON responses (all retry attempts)
    responses = [_make_response(200, content_type="text/plain")] * 3

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=responses), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is None
    assert reason == "rate_limited"


# ── cache tests ───────────────────────────────────────────────────────────────

def test_failure_not_cached(tmp_path):
    """A rate_limited result must NOT be written to cache_path."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file = tmp_path / "cache.json"
    responses = [_make_response(429)] * 3

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=responses), \
         patch("time.sleep"):
        _gc.get_articles(_SAMPLE_PARAMS, cache_path=cache_file,
                         cache_ttl_s=3600, min_interval=0.0)

    assert not cache_file.exists(), "failure result must not be written to cache"


def test_success_is_cached(tmp_path):
    """A successful fetch must write to cache_path; a second call returns cached data
    without any network request."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file = tmp_path / "cache.json"
    resp = _make_response(200, _gdelt_body(["Tariff headline for cache test"]))

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", return_value=resp) as mock_get, \
         patch("time.sleep"):
        # First call: hits network
        arts1, r1 = _gc.get_articles(_SAMPLE_PARAMS, cache_path=cache_file,
                                     cache_ttl_s=3600, min_interval=0.0)
        # Second call: should use cache, NOT the network
        arts2, r2 = _gc.get_articles(_SAMPLE_PARAMS, cache_path=cache_file,
                                     cache_ttl_s=3600, min_interval=0.0)

    assert cache_file.exists(), "cache file must be written after success"
    assert mock_get.call_count == 1, (
        f"network was called {mock_get.call_count} times; expected 1 (cache hit on 2nd)"
    )
    assert arts1 is not None and len(arts1) == 1
    assert arts2 is not None and len(arts2) == 1
    assert arts1[0]["title"] == arts2[0]["title"] == "Tariff headline for cache test"


# ── article normalisation ─────────────────────────────────────────────────────

def test_parse_articles_seendate_normalisation():
    """_parse_articles converts GDELT compact seendate to ISO 8601."""
    raw = {
        "articles": [
            {"title": "T", "url": "http://x.com", "domain": "x.com",
             "seendate": "20260710T120000Z"},
        ]
    }
    out = _gc._parse_articles(raw)
    assert len(out) == 1
    assert out[0]["seendate"].startswith("2026-07-10"), out[0]["seendate"]


def test_parse_articles_language_sourcecountry_passthrough():
    """_parse_articles must preserve language and sourcecountry from the raw article.
    These fields are needed by commodity_news; hardcoding '' would silently drop
    real per-article metadata."""
    raw = {
        "articles": [
            {"title": "T", "url": "http://x.com", "domain": "x.com",
             "seendate": "20260710T120000Z",
             "language": "English", "sourcecountry": "United States"},
            # Article without these fields — should default to empty string, not KeyError
            {"title": "T2", "url": "http://y.com", "domain": "y.com",
             "seendate": "20260710T120000Z"},
        ]
    }
    out = _gc._parse_articles(raw)
    assert len(out) == 2
    assert out[0]["language"] == "English"
    assert out[0]["sourcecountry"] == "United States"
    assert out[1]["language"] == ""
    assert out[1]["sourcecountry"] == ""


def test_empty_artlist_returns_no_articles_reason(tmp_path):
    """An empty articles list -> ([], 'no_articles')."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    resp = _make_response(200, {"articles": []})

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", return_value=resp), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles == []
    assert reason == "no_articles"


# ── cross-process stamp correctness tests ────────────────────────────────────

def test_stamp_is_wall_clock_unix_time(tmp_path):
    """The on-disk stamp written by _throttle must be a wall-clock unix timestamp
    (time.time()) so it is meaningful when read by a different process.  Before this
    fix the code wrote time.monotonic() instead — not comparable across processes or
    after a reboot."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)

    before = time.time()

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", return_value=_make_response(200, _gdelt_body(["t"]))), \
         patch("time.sleep"):
        _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    after = time.time()
    assert stamp_file.exists(), "stamp file must be written after a request"

    raw = stamp_file.read_text().strip()
    stamp_val = float(raw)
    # A wall-clock unix timestamp for now is ~1.75e9; time.monotonic() on this
    # box is in the tens-of-thousands-of-seconds range (boot-relative).
    # Assert the stamp is within the wall-clock window.
    assert before <= stamp_val <= after + 1.0, (
        f"stamp {stamp_val!r} is not a wall-clock unix time (expected {before:.1f}..{after:.1f}); "
        "was time.monotonic() written instead of time.time()?"
    )


def test_cross_process_stamp_honoured(tmp_path):
    """Simulate a prior process writing a wall-clock stamp. A second call in THIS
    process must read it and enforce the spacing — proving cross-process pacing works.
    If the code were writing time.monotonic() this test would still pass by accident
    (same-process), but combined with test_stamp_is_wall_clock_unix_time it catches
    the regression."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    min_interval = 0.05

    # Simulate a prior process having fetched 0.5 * min_interval ago
    prior_ts = time.time() - (min_interval * 0.5)
    stamp_file.write_text(str(prior_ts))

    request_times: list[float] = []

    def _fake_get(*args, **kwargs):
        request_times.append(time.time())
        return _make_response(200, _gdelt_body(["x"]))

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=_fake_get):
        _gc.get_articles(_SAMPLE_PARAMS, min_interval=min_interval)

    assert len(request_times) == 1
    elapsed_since_prior = request_times[0] - prior_ts
    assert elapsed_since_prior >= min_interval * 0.9, (
        f"request fired only {elapsed_since_prior:.4f}s after prior-process stamp "
        f"(expected >= {min_interval}s); cross-process pacing not honoured"
    )


# ── query-rejection tests (the 2026-06-20..07-10 news_vector stall shape) ────

def test_query_rejected_is_structural_not_retried(tmp_path):
    """GDELT 200 + text/html 'Your query was too short or too long.' must return
    (None, 'query_rejected') after ONE request — retrying a rejected query can
    never heal it and only burns the shared per-IP budget. Binning it as
    rate_limited/fetch_error is how the news_vector stall hid for three weeks."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    rejected = _make_response(200, content_type="text/html; charset=utf-8")
    rejected.text = "Your query was too short or too long.\n"
    calls: list[int] = []

    def _fake_get(*args, **kwargs):
        calls.append(1)
        return rejected

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", side_effect=_fake_get), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is None
    assert reason == "query_rejected"
    assert len(calls) == 1, "a rejected query must NOT be retried"


def test_non_json_unknown_text_still_retried_as_rate_limit(tmp_path):
    """200 + non-JSON WITHOUT a rejection marker keeps the conservative
    retry-as-rate-limit behavior (GDELT's throttle text is 200 + plain text)."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    throttled = _make_response(200, content_type="text/plain")
    throttled.text = "Please limit requests to one every 5 seconds or contact ..."

    with patch.object(_gc, "_stamp_path", return_value=stamp_file), \
         patch("requests.get", return_value=throttled), \
         patch("time.sleep"):
        articles, reason = _gc.get_articles(_SAMPLE_PARAMS, min_interval=0.0)

    assert articles is None
    assert reason == "rate_limited"


# ── public wait_turn gate (timeline-endpoint callers) ─────────────────────────

def test_wait_turn_public_gate_spaces_calls(tmp_path):
    """wait_turn() — used by hk_gdelt / missing_tape_gdelt / macro_news which keep
    their own transport — must honour the same cross-process stamp as get_articles."""
    stamp_file = tmp_path / "gdelt" / "last_request"
    stamp_file.parent.mkdir(parents=True, exist_ok=True)
    min_interval = 0.05

    with patch.object(_gc, "_stamp_path", return_value=stamp_file):
        _gc.wait_turn(min_interval)          # claims the slot
        t0 = time.monotonic()
        _gc.wait_turn(min_interval)          # must wait out the interval
        gap = time.monotonic() - t0

    assert gap >= min_interval * 0.9, (
        f"second wait_turn returned after only {gap:.4f}s; expected >= {min_interval}s"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-x", "-q"])
