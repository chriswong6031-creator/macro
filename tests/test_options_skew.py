"""Pure-function tests for engine/options_skew.py — single-name IV skew (display-only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from engine import options_skew as S  # noqa: E402


def _chain(underlying="XYZ", spot=100.0, put_iv=0.40, call_iv=0.30, days=30):
    """A minimal two-expiry chain: a near-target ~30d expiry + a far one to exercise
    expiry selection. Puts carry put_iv, calls call_iv → skew = put_iv - call_iv."""
    T = days / 365.0
    rows = []
    for exp, t in [("2026-07-21", T), ("2027-01-21", T * 6)]:
        # OTM put at delta ~-0.25 (K below spot) and ATM call at delta ~0.5 (K≈spot)
        rows += [
            dict(underlying=underlying, expiry=exp, K=spot * 0.95, T=t, is_call=False,
                 iv=put_iv, delta=-0.25, oi=100, gamma=0.01, volume=10, spot=spot, asof="2026-06-21"),
            dict(underlying=underlying, expiry=exp, K=spot * 0.90, T=t, is_call=False,
                 iv=put_iv + 0.05, delta=-0.10, oi=50, gamma=0.01, volume=5, spot=spot, asof="2026-06-21"),
            dict(underlying=underlying, expiry=exp, K=spot, T=t, is_call=True,
                 iv=call_iv, delta=0.50, oi=100, gamma=0.01, volume=10, spot=spot, asof="2026-06-21"),
            dict(underlying=underlying, expiry=exp, K=spot * 1.05, T=t, is_call=True,
                 iv=call_iv - 0.02, delta=0.25, oi=50, gamma=0.01, volume=5, spot=spot, asof="2026-06-21"),
        ]
    return pd.DataFrame(rows)


def test_compute_skew_put_over_call():
    m = S.compute_skew(_chain(put_iv=0.40, call_iv=0.30))
    assert m is not None
    assert abs(m["otm_put_iv"] - 0.40) < 1e-9 and abs(m["atm_call_iv"] - 0.30) < 1e-9
    assert abs(m["skew"] - 0.10) < 1e-9                 # +0.10 put-over-call skew
    assert 25 <= m["tenor_days"] <= 35                  # picked the ~30d expiry, not the far one


def test_compute_skew_negative_when_call_rich():
    m = S.compute_skew(_chain(put_iv=0.28, call_iv=0.34))
    assert m["skew"] < 0                                 # call IV > put IV → negative skew


def test_skew_map_multi_underlying():
    chain = pd.concat([_chain("AAA", put_iv=0.5, call_iv=0.3),
                       _chain("BBB", put_iv=0.3, call_iv=0.35)], ignore_index=True)
    mp = S.skew_map(chain)
    assert set(mp) == {"AAA", "BBB"}
    assert mp["AAA"]["skew"] > 0 and mp["BBB"]["skew"] < 0


def test_compute_skew_degrades_empty():
    assert S.compute_skew(pd.DataFrame()) is None
    assert S.compute_skew(None) is None
    assert S.skew_map(None) == {}


def test_build_snapshot_is_context_only(monkeypatch, tmp_path):
    # no gate file, no store → dormant 'measuring' state, never scored
    monkeypatch.delenv("THETADATA_STORE", raising=False)
    monkeypatch.setattr("engine.thetadata_store.resolve_thetadata_store",
                        lambda **kw: None)
    pay = S.build_snapshot()
    assert pay["is_context_only"] is True
    assert pay["scored"] is False
    assert pay["schema"] == S.SCHEMA


# --------------------------------------------------------------------------- #
# ThetaData chain store migration (A-F03-W2-1)
# --------------------------------------------------------------------------- #

def _write_theta_store(tmp_path, root="XYZ", date="2026-06-21", expiry="2026-07-21",
                        spot=100.0, put_iv=0.40, call_iv=0.30):
    """Synthetic ThetaData store: eod + oi + greeks tiers for one root/year,
    documented columns per engine/thetadata_store.py:8-12."""
    pa = pytest.importorskip("pyarrow")  # noqa: F841
    year = date[:4]
    strikes = [90.0, 95.0, 100.0, 105.0]
    rights = ["P", "P", "C", "C"]
    deltas = [-0.10, -0.25, 0.50, 0.25]
    ivs = [put_iv + 0.05, put_iv, call_iv, call_iv - 0.02]

    eod_rows, oi_rows, greeks_rows = [], [], []
    for k, r, d, iv in zip(strikes, rights, deltas, ivs):
        eod_rows.append(dict(root=root, expiration=expiry, strike=k, right=r, date=date,
                              open=1.0, high=1.0, low=1.0, close=1.0, volume=10, count=1,
                              bid=0.9, ask=1.1))
        oi_rows.append(dict(root=root, expiration=expiry, strike=k, right=r, date=date,
                             open_interest=50))
        greeks_rows.append(dict(root=root, expiration=expiry, strike=k, right=r, date=date,
                                 bid=0.9, ask=1.1, underlying_price=spot, delta=d,
                                 theta=0.0, vega=0.0, rho=0.0, epsilon=0.0, lambda_=0.0,
                                 implied_vol=iv, iv_error=0.0))

    for tier, rows in (("eod", eod_rows), ("oi", oi_rows), ("greeks", greeks_rows)):
        d = tmp_path / tier / root
        d.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(d / f"{year}.parquet")
    return tmp_path


def test_thetadata_chain_positive(tmp_path):
    store = _write_theta_store(tmp_path, root="XYZ", put_iv=0.40, call_iv=0.30)
    frame, state = S.load_chain(asof="2026-06-21", store=store, roots=["XYZ"])
    assert state == "ok"
    assert frame is not None
    for col in ["underlying", "expiry", "K", "T", "iv", "delta", "is_call",
                "spot", "oi", "volume", "asof"]:
        assert col in frame.columns
    m = S.skew_map(frame)
    assert m["XYZ"]["skew"] == pytest.approx(0.10, abs=1e-6)
    assert 25 <= m["XYZ"]["tenor_days"] <= 35


def test_missing_chain_is_typed_null(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("THETADATA_STORE", raising=False)
    # Empty store dir → unresolved (no eod/oi/greeks subdirs at all).
    monkeypatch.setattr("engine.thetadata_store.resolve_thetadata_store",
                        lambda **kw: None)
    pay = S.build_snapshot()
    assert pay["names"] == {} and pay["n"] == 0 and pay["source"] is None
    assert pay["source_state"] == "thetadata_store_unresolved"
    out = capsys.readouterr().out
    assert any(line.startswith("::warning") for line in out.splitlines())

    # store with eod/ but no greeks/ → no_iv_tier
    store = tmp_path / "eodonly"
    (store / "eod" / "XYZ").mkdir(parents=True)
    frame, state = S.load_chain(store=store)
    assert frame is None and state == "no_iv_tier"

    assert all(v is not None for v in [pay["source_state"], pay["names"], pay["ranked"]])
    assert pay["source_state"] != "ok"


def test_stale_chain_is_typed_null(tmp_path, capsys, monkeypatch):
    from datetime import date as _date
    store = _write_theta_store(tmp_path, root="XYZ", date="2026-06-21")
    monkeypatch.setattr("engine.thetadata_store.resolve_thetadata_store",
                        lambda **kw: store)
    pay = S.build_snapshot(today=_date(2026, 7, 21))  # 30 days after the chain's asof
    assert pay["source_state"] == "stale_chain"
    assert pay["source_detail"]["stale_days"] >= 25
    out = capsys.readouterr().out
    assert any(line.startswith("::warning") for line in out.splitlines())


def test_legacy_path_not_globbed_by_default(monkeypatch):
    import glob as glob_mod
    monkeypatch.delenv(S._LEGACY_CHAIN_ENV, raising=False)
    monkeypatch.setattr("engine.thetadata_store.resolve_thetadata_store",
                        lambda **kw: None)

    def _boom(*a, **kw):
        raise AssertionError("legacy path reached")
    monkeypatch.setattr(glob_mod, "glob", _boom)

    # must not raise: the legacy glob is never reached when the flag is unset
    S.build_snapshot()

    monkeypatch.setenv(S._LEGACY_CHAIN_ENV, "1")
    with pytest.raises(AssertionError, match="legacy path reached"):
        S._legacy_chain()


def test_thetadata_and_legacy_overlap(tmp_path, monkeypatch):
    """Cross-source equivalence: the same underlying facts fed through the legacy
    polygon_gex schema and the ThetaData schema must drive the identical formula
    to the same sign and comparable magnitude."""
    spot, put_iv, call_iv = 100.0, 0.40, 0.30

    legacy_rows = [
        dict(underlying="XYZ", strike_ticker="O:XYZ", expiry="2026-07-21", K=95.0,
             T=30 / 365.0, is_call=False, oi=100, iv=put_iv, gamma=0.01, delta=-0.25,
             volume=10, spot=spot, asof="2026-06-21"),
        dict(underlying="XYZ", strike_ticker="O:XYZ", expiry="2026-07-21", K=90.0,
             T=30 / 365.0, is_call=False, oi=50, iv=put_iv + 0.05, gamma=0.01,
             delta=-0.10, volume=5, spot=spot, asof="2026-06-21"),
        dict(underlying="XYZ", strike_ticker="O:XYZ", expiry="2026-07-21", K=100.0,
             T=30 / 365.0, is_call=True, oi=100, iv=call_iv, gamma=0.01, delta=0.50,
             volume=10, spot=spot, asof="2026-06-21"),
        dict(underlying="XYZ", strike_ticker="O:XYZ", expiry="2026-07-21", K=105.0,
             T=30 / 365.0, is_call=True, oi=50, iv=call_iv - 0.02, gamma=0.01,
             delta=0.25, volume=5, spot=spot, asof="2026-06-21"),
    ]
    legacy_chain = pd.DataFrame(legacy_rows)
    skew_legacy = S.compute_skew(legacy_chain)["skew"]

    store = _write_theta_store(tmp_path, root="XYZ", put_iv=put_iv, call_iv=call_iv)
    frame, state = S.load_chain(asof="2026-06-21", store=store, roots=["XYZ"])
    assert state == "ok"
    skew_theta = S.skew_map(frame)["XYZ"]["skew"]

    import math
    assert math.copysign(1, skew_legacy) == math.copysign(1, skew_theta)
    assert abs(skew_legacy - skew_theta) < 0.01


def test_null_is_never_zero(tmp_path, monkeypatch):
    for resolver in (lambda **kw: None,):
        monkeypatch.setattr("engine.thetadata_store.resolve_thetadata_store", resolver)
        pay = S.build_snapshot()
        assert pay["source_state"] != "ok"
        assert "skew" not in json.dumps(pay["names"])
        assert pay["ranked"] == []


# --------------------------------------------------------------------------- #
# Regression: _fwd_ic must emit a finite, non-NaN HAC t-stat                  #
# --------------------------------------------------------------------------- #

def test_fwd_ic_hac_t_is_finite_not_nan():
    """Regression guard for the t_hac key bug.

    Before the fix, _fwd_ic used summ.get("t", summ.get("hac_t", ...)) which
    always produces NaN because ic_summary() returns the key 't_hac', not 't'
    or 'hac_t'.  This test creates a synthetic panel large enough to pass the
    6-IC floor in ic_summary and asserts the returned 'hac_t' is a finite float.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import numpy as np
    import pandas as pd

    # Build a synthetic panel with a strong positive monotone signal so that
    # rank-IC is reliably non-NaN and the HAC t-stat is large.
    dates = [f"2020-01-{i+2:02d}" for i in range(25)]
    underlyings = [f"SYM{j:02d}" for j in range(15)]

    rows = []
    spot_base = 100.0
    for i, d in enumerate(dates):
        for j, u in enumerate(underlyings):
            # Monotone drift so spots increase — gives clean forward returns
            rows.append({"date": d, "underlying": u,
                         "skew": float(j) / 14.0,  # cross-sectional rank matches j
                         "spot": spot_base + i * 0.5 + j * 0.1})
    panel = pd.DataFrame(rows)

    from scripts.validate_options_skew import _fwd_ic
    result = _fwd_ic(panel, h=5)

    assert result["n_dates"] > 0, "Expected non-zero IC dates from synthetic panel"
    hac_t = result.get("hac_t")
    assert hac_t is not None, "_fwd_ic did not return 'hac_t' key"
    assert np.isfinite(float(hac_t)), (
        f"hac_t is {hac_t!r} — expected a finite float. "
        "This indicates the t_hac key is still wrong (ic_summary returns 't_hac', "
        "not 't' or 'hac_t')."
    )
