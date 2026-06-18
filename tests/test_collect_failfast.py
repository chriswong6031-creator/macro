"""Guard the FRED-frontend fail-fast circuit breaker on the macro collectors.

A FRED-frontend outage once turned the intl_macro plane into a ~56-minute no-op
(34 series x 3 retries x 30s, every one timing out and producing nothing). These
collectors now abort a source after a short run of CONSECUTIVE connection failures,
while still trying every series when the failures are merely dead series ids.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
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

    a._fetch_fred = conn_down
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

    a._fetch_fred = data_dead
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
