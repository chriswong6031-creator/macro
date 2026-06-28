"""Guard the circuit-breaker HALF-OPEN recovery on collectors/base.

An open breaker used to be a permanent SILENT death: run_adapter returned "dead"
without retrying, and the daily/weekly collect never pass --full-history (the only
flag that bypassed it), so a single transient trip wedged a HEALTHY source dead for
weeks. It is now half-open: after a cooldown it lets ONE probe through — a success
(or a known-limitation "blocked") closes it; a failed probe re-opens it for another
window. "blocked" closes the breaker too, so an expected_failure source never sticks.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import collectors.base as b  # noqa: E402
from collectors.base import (  # noqa: E402
    CIRCUIT_BREAKER_FAILS,
    Adapter,
    FetchResult,
    _probe_due,
    run_adapter,
    update_breaker,
)


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class _Fake(Adapter):
    name = "fake_src"
    group = "misc"
    stale_after_days = 5

    def __init__(self, impl):
        self._impl = impl
        self.calls = 0

    def fetch(self, full_history: bool = False):
        self.calls += 1
        return self._impl()


def _set_state(monkeypatch, breaker=None, probe=None):
    monkeypatch.setattr(b, "_breaker_state", lambda: dict(breaker or {}))
    monkeypatch.setattr(b, "_probe_state", lambda: dict(probe or {}))


# -- _probe_due --------------------------------------------------------------

def test_probe_due_logic():
    assert _probe_due(None) is True                      # never probed -> due
    assert _probe_due(_iso(2)) is False                  # 2h < 20h cooldown
    assert _probe_due(_iso(25)) is True                  # 25h >= cooldown
    assert _probe_due("not-a-timestamp") is True         # unparseable -> fail open


# -- run_adapter half-open gating -------------------------------------------

def test_open_breaker_probes_when_cooldown_elapsed(monkeypatch):
    """An open breaker with no recent probe RUNS the adapter (half-open)."""
    _set_state(monkeypatch, breaker={"fake_src": CIRCUIT_BREAKER_FAILS}, probe={})

    def boom():
        raise RuntimeError("still down")

    a = _Fake(boom)
    res = run_adapter(a)
    assert a.calls == 1, "half-open must actually attempt the fetch"
    assert res.status == "failed"
    assert res.probed_at, "a half-open probe stamps the time so it waits a cooldown"


def test_open_breaker_skips_within_cooldown(monkeypatch):
    """An open breaker probed recently stays dead and does NOT hit the network."""
    _set_state(monkeypatch,
               breaker={"fake_src": CIRCUIT_BREAKER_FAILS},
               probe={"fake_src": _iso(1)})

    a = _Fake(lambda: {"x": pd.DataFrame({"v": [1.0]}, index=[pd.Timestamp.utcnow()])})
    res = run_adapter(a)
    assert a.calls == 0, "within cooldown the adapter must be skipped"
    assert res.status == "dead"
    assert res.probed_at is None


def test_half_open_success_closes_breaker(monkeypatch):
    """A successful half-open probe resets the count to 0 (breaker closed)."""
    _set_state(monkeypatch, breaker={"fake_src": CIRCUIT_BREAKER_FAILS}, probe={})
    monkeypatch.setattr(b.store, "upsert", lambda *a, **k: a[2])  # return the df

    today = pd.Timestamp(datetime.now(timezone.utc).date())
    a = _Fake(lambda: {"x": pd.DataFrame({"v": [1.0]}, index=[today])})
    res = run_adapter(a)
    assert a.calls == 1 and res.status == "ok"
    breaker, probe = update_breaker([res])
    assert breaker["fake_src"] == 0, "recovered source closes the breaker"
    assert "fake_src" not in probe, "recovered source forgets its probe clock"


# -- update_breaker semantics -----------------------------------------------

def test_blocked_clears_breaker(monkeypatch):
    """'blocked' is an expected_failure (known limitation), not an outage: it must
    close the breaker so the source is never wedged 'dead'."""
    _set_state(monkeypatch, breaker={"src": CIRCUIT_BREAKER_FAILS}, probe={"src": _iso(30)})
    breaker, probe = update_breaker([FetchResult("src", "blocked", probed_at=_iso(0))])
    assert breaker["src"] == 0
    assert "src" not in probe


def test_failed_probe_increments_and_restamps(monkeypatch):
    """A failed half-open probe increments the count and records the probe time so
    the next attempt waits a full cooldown again (not every run)."""
    _set_state(monkeypatch, breaker={"src": CIRCUIT_BREAKER_FAILS}, probe={})
    stamp = _iso(0)
    breaker, probe = update_breaker([FetchResult("src", "failed", probed_at=stamp)])
    assert breaker["src"] == CIRCUIT_BREAKER_FAILS + 1
    assert probe["src"] == stamp


def test_untouched_sources_keep_their_state(monkeypatch):
    """A partial run must not wipe the breaker/probe of sources it didn't run."""
    _set_state(monkeypatch, breaker={"a": 5, "b": 0}, probe={"a": _iso(3)})
    breaker, probe = update_breaker([FetchResult("b", "ok")], {"a": _iso(3)})
    assert breaker["a"] == 5, "skipped source keeps its breaker count"
    assert probe["a"], "skipped source keeps its probe timestamp"
