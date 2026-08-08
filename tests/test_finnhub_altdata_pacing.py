"""finnhub_altdata: the rate limiter must run on the FAILURE path too.

Postmortem 2026-08-06 (17 consecutive nightly failures). `time.sleep(PACE_S)` sat at
the very end of the per-endpoint loop body, and both the error branch and the gate
branch `continue` past it. So the pacing existed only for calls that SUCCEEDED: the
first burst of failures removed the only rate limiting the sweep had, and the run
then hammered the API into a self-sustaining 429 wall. The 2026-08-05 nightly burned
116s to arrive at "no rows from 120 tickers (errors=120)" — a sentence that cannot
distinguish a rejected key from a rate limit from an outage, which is why nobody
could act on it.
"""
from __future__ import annotations

import pytest

import collectors.finnhub_altdata as fa


class _Resp:
    def __init__(self, code):
        self.status_code = code


class _HTTPish(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.response = _Resp(code)


@pytest.fixture()
def _adapter(monkeypatch, tmp_path):
    monkeypatch.setattr(fa, "basket_members", lambda cap: [f"T{i}" for i in range(cap)])
    monkeypatch.setattr(fa.config, "data_dir", lambda: tmp_path)
    a = fa.FinnhubAltdataAdapter()
    a.api_key = "k"
    # __init__ pre-sets expected_failure when no FINNHUB key is in the test env;
    # clear it so these assertions read what fetch() itself decided, not the fixture.
    a.expected_failure = None
    return a


def test_every_attempted_call_is_paced_even_when_it_fails(_adapter, monkeypatch):
    """THE REGRESSION. Without the finally, a failing sweep sleeps zero times."""
    slept: list[float] = []
    monkeypatch.setattr(fa.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(_adapter, "_get",
                        lambda path, params: (_ for _ in ()).throw(_HTTPish(500)))
    with pytest.raises(RuntimeError):
        _adapter.fetch()
    assert slept, "a sweep that only ever fails must still pace itself; it slept 0 times"
    assert all(s == fa.PACE_S for s in slept)


def test_a_wall_of_429s_stops_the_endpoint_by_name_instead_of_grinding(_adapter, monkeypatch):
    """Same 'classify and stop' rule the auth gate already follows: once an endpoint
    answers 429 repeatedly there is nothing left to learn from 300 more requests."""
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    calls: list[str] = []

    def _get(path, params):
        calls.append(path)
        raise _HTTPish(429)

    monkeypatch.setattr(_adapter, "_get", _get)
    with pytest.raises(RuntimeError) as ei:
        _adapter.fetch()
    msg = str(ei.value)
    assert "RATE-LIMITED" in msg, f"the throttle must be named, not counted; got {msg!r}"
    assert "recommendation-trends" in msg
    # 3 endpoints x GIVEUP attempts each, not 120 tickers x 3 endpoints.
    assert len(calls) <= 3 * fa.RATE_LIMIT_GIVEUP + 3, (
        f"gave up far too late: {len(calls)} calls into a 429 wall")


def test_a_throttle_is_never_laundered_into_a_plan_gate(_adapter, monkeypatch):
    """`blocked` means 'known limitation' and CLEARS the circuit breaker
    (collectors/base.py update_breaker). A 429 is transient and must stay a real
    failure, or a rate-limited night reports itself as an expected one."""
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    monkeypatch.setattr(_adapter, "_get",
                        lambda path, params: (_ for _ in ()).throw(_HTTPish(429)))
    with pytest.raises(RuntimeError):
        _adapter.fetch()
    assert not _adapter.expected_failure, (
        "a rate limit set expected_failure => status 'blocked' => breaker cleared")


def test_auth_gate_still_wins_over_the_throttle_path(_adapter, monkeypatch):
    """403 on every endpoint is a plan gate and must keep reporting as one."""
    monkeypatch.setattr(fa.time, "sleep", lambda s: None)
    monkeypatch.setattr(_adapter, "_get",
                        lambda path, params: (_ for _ in ()).throw(_HTTPish(403)))
    with pytest.raises(RuntimeError):
        _adapter.fetch()
    assert _adapter.expected_failure and "403" in _adapter.expected_failure


def test_rate_limit_classifier_is_anchored():
    assert fa._is_rate_limited(_HTTPish(429)) is True
    assert fa._is_rate_limited(Exception("HTTP 429")) is True
    assert fa._is_rate_limited(Exception("ticker 4290 blew up")) is False
    assert fa._is_rate_limited(_HTTPish(403)) is False
