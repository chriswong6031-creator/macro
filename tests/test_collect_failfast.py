"""Guard the FRED-frontend fail-fast circuit breaker on the macro collectors.

A FRED-frontend outage once turned the intl_macro plane into a ~56-minute no-op
(34 series x 3 retries x 30s, every one timing out and producing nothing). These
collectors now abort a source after a short run of CONSECUTIVE connection failures,
while still trying every series when the failures are merely dead series ids.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.base import is_connection_error  # noqa: E402
from collectors.canada_macro import (  # noqa: E402
    _ABORT_AFTER_CONSECUTIVE_CONN_ERRORS as CA_ABORT,
    CanadaMacroAdapter,
)
from collectors.intl_macro import (  # noqa: E402
    _ABORT_AFTER_CONSECUTIVE_CONN_ERRORS as INTL_ABORT,
    IntlMacroAdapter,
)
from lib import config  # noqa: E402


@pytest.fixture(autouse=True)
def _hermetic_no_network_no_data_writes(monkeypatch, tmp_path):
    """Pin these breaker tests to their STUBS, never to the runner's uplink.

    2026-08-04: ``test_intl_aborts_fast_when_host_unreachable`` was RED on a
    pristine main on any NETWORKED machine, and clobbered a tracked file on
    every run.  The tests stub only ``a._fetch_fred``, but
    ``IntlMacroAdapter.fetch()`` grew a SECOND live leg in #4109 — the
    ``official_series`` loop (``_fetch_official`` -> ``http_get`` -> live
    ECB/Eurostat, 2 series in config.yml).  With connectivity those officials
    RESOLVED, so ``frames`` was non-empty, the expected RuntimeError never
    raised, and ``fetch()`` ran on into ``_write_provenance()`` against the REAL
    ``data/intl_macro/provenance.json`` — rewriting 358 lines of committed
    provenance down to the ~28 lines of whichever 2 series happened to resolve.
    Offline, the identical test passed.  A verdict that depends on the runner's
    network is not a test.

    Two belts, because the per-test ``_fetch_official`` stubs below only close
    the leg we know about today:
      * socket-level block — any FUTURE unstubbed live leg fails LOUDLY right
        here instead of silently inheriting the machine's connectivity;
      * ``config.data_dir`` -> tmp_path — the conftest MM_DATA_GUARD idiom, so a
        provenance write that ever does get reached physically lands outside the
        repo.  Both collectors.intl_macro and collectors.base call
        ``config.data_dir()`` through the module reference, so patching the
        module attribute covers them at call time.
    """
    def _boom(*_a, **_k):
        raise AssertionError("test attempted real network access")

    monkeypatch.setattr(socket, "getaddrinfo", _boom)
    monkeypatch.setattr(socket, "create_connection", _boom)
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)


def _intl_plan_len(a: IntlMacroAdapter) -> int:
    n = sum(len(c.get("fred") or {}) for c in a.countries.values())
    return n + len(a.cfg.get("extra_series") or {})


def test_is_connection_error_classification():
    assert is_connection_error(requests.exceptions.ConnectTimeout("x"))
    assert is_connection_error(requests.exceptions.ReadTimeout("x"))
    assert is_connection_error(requests.exceptions.ConnectionError("Max retries exceeded"))
    assert is_connection_error(Exception("HTTPSConnectionPool: Read timed out"))
    # data-level problems are NOT connection errors
    assert not is_connection_error(ValueError("fred FOO: no numeric rows"))
    assert not is_connection_error(Exception("HTTP 404"))


def test_intl_aborts_fast_when_host_unreachable():
    a = IntlMacroAdapter()
    plan_len = _intl_plan_len(a)
    assert plan_len > INTL_ABORT  # otherwise the test proves nothing
    calls = {"n": 0}

    def conn_down(_fid):
        calls["n"] += 1
        raise requests.exceptions.ConnectTimeout("Read timed out")

    def official_down(_col, _spec):
        raise requests.exceptions.ConnectTimeout("Read timed out")

    a._fetch_fred = conn_down
    a._fetch_official = official_down
    try:
        a.fetch()
        raise AssertionError("expected RuntimeError when nothing resolved")
    except RuntimeError:
        pass
    assert calls["n"] == INTL_ABORT, f"attempted {calls['n']}, expected fail-fast at {INTL_ABORT}"


def test_intl_tries_all_when_failures_are_dead_series():
    a = IntlMacroAdapter()
    plan_len = _intl_plan_len(a)
    calls = {"n": 0}

    def data_dead(fid):
        calls["n"] += 1
        raise ValueError(f"fred {fid}: no numeric rows")

    def official_down(_col, _spec):
        raise requests.exceptions.ConnectTimeout("Read timed out")

    a._fetch_fred = data_dead
    a._fetch_official = official_down
    try:
        a.fetch()
    except RuntimeError:
        pass
    assert calls["n"] == plan_len, "dead-series data errors must not trip the host breaker"


def test_canada_dead_fred_does_not_starve_boc_statcan():
    c = CanadaMacroAdapter()
    n_boc = len(c.cfg.get("boc_series", {}))
    n_sc = len(c.cfg.get("statcan_vectors", {}))
    n_fred = len(c.cfg.get("fred_series", {}))
    assert n_fred > CA_ABORT and (n_boc + n_sc) > 0

    def ok(_ref):
        return pd.DataFrame({"_": [1.0]}, index=[pd.Timestamp("2020-01-01")])

    fred_calls = {"n": 0}

    def fred_down(_fid):
        fred_calls["n"] += 1
        raise requests.exceptions.ConnectionError("Max retries exceeded")

    c._fetch_boc = ok
    c._fetch_statcan = ok
    c._fetch_fred = fred_down

    frames = c.fetch()
    assert fred_calls["n"] == CA_ABORT, "FRED source should abort fast"
    assert len(frames) == n_boc + n_sc, "healthy BoC/StatsCan series must all resolve"


# ---------------------------------------------------------------------------
# run_adapter duck-typing degradation (daily 2026-08-02/08-03 collect outage).
#
# #4311 made run_adapter call adapter.fetch_result_status(frames) UNCONDITIONALLY
# after a successful fetch, but only 2 of ~228 collector modules define that
# protocol.  Worse, the except handler read adapter.expected_failure — also
# optional — so the first adapter lacking BOTH attributes (gaming_ny) raised
# inside the handler and killed the whole collect pass: every source after it
# went uncollected for two nights and every source before it took a false
# "failed" breaker strike.  These tests pin the contract in the step's own
# name: graceful degradation NEVER fails the build on one source.
# ---------------------------------------------------------------------------
from collectors.base import run_adapter  # noqa: E402


class _BareAdapter:
    """The pre-#4311 adapter surface: name/group/stale_after_days/fetch only."""

    name = "bare_test_source"
    group = "test_group"
    stale_after_days = 9

    def __init__(self, exc: Exception | None = None):
        self._exc = exc

    def fetch(self, full_history: bool = False) -> dict:
        if self._exc is not None:
            raise self._exc
        return {}

    def validate(self, series_name, df):
        return df


def test_bare_adapter_success_survives_missing_status_protocol():
    res = run_adapter(_BareAdapter())
    assert res.status == "ok"


def test_bare_adapter_failure_survives_missing_expected_failure():
    res = run_adapter(_BareAdapter(exc=RuntimeError("boom")))
    assert res.status == "failed"
    assert "RuntimeError" in (res.error or "")


def test_declared_status_protocol_still_honored():
    class _Declaring(_BareAdapter):
        name = "declaring_test_source"

        def fetch_result_status(self, frames) -> str:
            return "blocked"

    res = run_adapter(_Declaring())
    assert res.status == "blocked"
