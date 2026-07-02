"""W2.2 — per-engine atomic price-basis flip tests (D4 §7 structure/momentum split).

Covers the wave's acceptance gates:

  A. cycles.analyze(price=None) is BYTE-IDENTICAL to the default (no-arg) path.
  B. cycles.analyze(price=...) splits: structure (cycle_state / DCL / failed-cycle) moves
     to the price basis while momentum (mtf / MACD) stays on the passed `close` (TR).
  C. _record_core basis stamping: price → "price"; a tr_fallback-tagged series → "tr_fallback";
     no price → "tr" (legacy). And the structure math actually differs on price.
  D. engine flip fallback labeling: a ticker ABSENT from the price panel is stamped
     tr_fallback (never silent), while a present ticker is "price".
  E. audit_price_basis PASSES on the flipped tree and FAILS on a synthetic regression
     (a structure series that is really TR / a forward log with stale sector 'tr' rows).

Uses the committed data files (read-only) + synthetic fixtures; no network.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cycles  # noqa: E402
from engine import sector_cycles as sc  # noqa: E402
from engine.inputs import _yahoo_close  # noqa: E402


def _clean(d) -> str:
    return json.dumps(d, sort_keys=True, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# A. analyze(price=None) byte-identity
# ─────────────────────────────────────────────────────────────────────────────
def _synthetic_div_series(n=1400, seed=1):
    """A dividend-inflated pair: `tr` grows faster than `price` (a constant yield drag)."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2018-01-01", periods=n)
    steps = rng.normal(0.0004, 0.012, n)
    price = pd.Series(100 * np.exp(np.cumsum(steps)), index=idx)
    # tr = price compounded with a steady ~2%/yr dividend reinvestment
    tr = price * np.exp(np.linspace(0, 0.02 * n / 252, n))
    return price, tr


def test_analyze_price_none_byte_identical():
    _, tr = _synthetic_div_series()
    a0 = cycles.analyze(tr, kind="equity")
    a1 = cycles.analyze(tr, kind="equity", price=None)
    assert _clean(a0) == _clean(a1)


def test_analyze_price_none_byte_identical_real_etf():
    tr = _yahoo_close("XLU", basis="tr")
    if tr is None:
        pytest.skip("XLU not in store")
    tr = tr.dropna()
    assert _clean(cycles.analyze(tr, kind="equity")) == \
           _clean(cycles.analyze(tr, kind="equity", price=None))


# ─────────────────────────────────────────────────────────────────────────────
# B. analyze(price=...) structure/momentum split
# ─────────────────────────────────────────────────────────────────────────────
def test_analyze_price_splits_structure_vs_momentum():
    price, tr = _synthetic_div_series()
    a_tr = cycles.analyze(tr, kind="equity")                    # all on TR
    a_split = cycles.analyze(tr, kind="equity", price=price)    # structure on price

    # momentum is UNCHANGED (mtf runs on `close`=tr in both)
    assert _clean(a_tr["mtf"]) == _clean(a_split["mtf"])

    # structure (cycle_state) reads the price basis → the DCL invalidation *price level*
    # differs (price and tr diverge by the dividend factor).
    dcl_tr = (a_tr["cycle"] or {}).get("dcl_price")
    dcl_split = (a_split["cycle"] or {}).get("dcl_price")
    assert dcl_tr is not None and dcl_split is not None
    assert dcl_tr != dcl_split, "structure DCL price did not move to the price basis"


def test_analyze_real_etf_structure_differs():
    tr = _yahoo_close("XLU", basis="tr")
    px = _yahoo_close("XLU", basis="price")
    if tr is None or px is None:
        pytest.skip("XLU not in store")
    tr, px = tr.dropna(), px.dropna()
    a = cycles.analyze(tr, kind="equity", price=px)
    a0 = cycles.analyze(tr, kind="equity")
    # momentum identical, structure (dcl_price) on the price basis
    assert _clean(a["mtf"]) == _clean(a0["mtf"])
    assert (a["cycle"] or {}).get("dcl_price") != (a0["cycle"] or {}).get("dcl_price")


# ─────────────────────────────────────────────────────────────────────────────
# C. _record_core basis stamping
# ─────────────────────────────────────────────────────────────────────────────
def test_record_core_stamps_price_basis():
    price, tr = _synthetic_div_series()
    price = price.copy()
    price.attrs["price_basis"] = "price"
    win_start = tr.index[-1] - pd.DateOffset(years=7)
    rec_tr = sc._record_core(tr, win_start, tr.index[-1])                    # legacy
    rec_px = sc._record_core(tr, win_start, tr.index[-1], price=price)       # flipped
    assert rec_tr["basis"] == "tr"
    assert rec_px["basis"] == "price"
    assert rec_tr["now"]["basis"] == "tr"
    assert rec_px["now"]["basis"] == "price"


def test_record_core_tr_fallback_labeled():
    """A price series tagged tr_fallback stamps basis='tr_fallback' — never silent."""
    price, tr = _synthetic_div_series()
    fb = tr.copy()
    fb.attrs["price_basis"] = "tr_fallback"
    win_start = tr.index[-1] - pd.DateOffset(years=7)
    rec = sc._record_core(tr, win_start, tr.index[-1], price=fb)
    assert rec["basis"] == "tr_fallback"
    assert rec["now"]["basis"] == "tr_fallback"


def test_record_core_price_moves_turns():
    """On a dividend-inflated pair the price-basis turns differ from TR (the flip is real)."""
    price, tr = _synthetic_div_series(seed=7)
    price = price.copy()
    price.attrs["price_basis"] = "price"
    win_start = tr.index[0]
    rec_tr = sc._record_core(tr, win_start, tr.index[-1])
    rec_px = sc._record_core(tr, win_start, tr.index[-1], price=price)
    t_tr = {(t["date"], t["k"]) for t in rec_tr["turns"] if not t.get("provisional")}
    t_px = {(t["date"], t["k"]) for t in rec_px["turns"] if not t.get("provisional")}
    # at minimum the projection / osc differ; turns usually differ too. Assert the
    # detrended-osc last value moved (a structure read on a different basis).
    assert rec_tr["now"]["pos"] != rec_px["now"]["pos"] or t_tr != t_px


# ─────────────────────────────────────────────────────────────────────────────
# D. engine flip fallback labeling (_price_series)
# ─────────────────────────────────────────────────────────────────────────────
def test_price_series_present_tagged_price():
    idx = pd.bdate_range("2019-01-01", periods=500)
    tr = pd.Series(np.linspace(100, 200, 500), index=idx)
    px = pd.DataFrame({"XLK": np.linspace(90, 180, 500)}, index=idx)
    s = sc._price_series(px, "XLK", tr)
    assert s.attrs.get("price_basis") == "price"


def test_price_series_absent_tagged_tr_fallback():
    idx = pd.bdate_range("2019-01-01", periods=500)
    tr = pd.Series(np.linspace(100, 200, 500), index=idx)
    px = pd.DataFrame({"XLK": np.linspace(90, 180, 500)}, index=idx)
    s = sc._price_series(px, "XLQ_MISSING", tr)   # not in the price panel
    assert s.attrs.get("price_basis") == "tr_fallback"
    # fallback carries the TR values (structure runs on TR, but labeled)
    pd.testing.assert_series_equal(s.reset_index(drop=True), tr.reset_index(drop=True),
                                   check_names=False)


def test_price_series_none_panel_legacy():
    idx = pd.bdate_range("2019-01-01", periods=500)
    tr = pd.Series(np.linspace(100, 200, 500), index=idx)
    assert sc._price_series(None, "XLK", tr) is None   # legacy TR-only path


# ─────────────────────────────────────────────────────────────────────────────
# E. audit passes on the flipped tree; FAILS on a synthetic regression
# ─────────────────────────────────────────────────────────────────────────────
def test_audit_passes_on_flipped_tree(tmp_path):
    from scripts import audit_price_basis as apb
    doc = apb.run(out_dir=tmp_path)
    # the store + engine tree is flipped; every HARD universe must be clean.
    hard = {"golden_fixture", "no_tr_in_structure", "basis_homogeneous",
            "narratives_versioned", "basis_preserving"}
    for u in doc["universes"]:
        if u["name"] in hard:
            assert u["n_failed"] == 0, f"{u['name']} failed: {u.get('failed')}"
    # golden fixture must have PROVEN a real flip (a note, not a failure)
    gf = next(u for u in doc["universes"] if u["name"] == "golden_fixture")
    assert gf["n_failed"] == 0 and gf["n"] == 1


def test_audit_golden_fixture_fails_on_no_op_flip(monkeypatch):
    """If close_price ever equals close (structure on TR), the golden fixture FAILS —
    a synthetic regression: force _detect_swings to return identical turns for both bases."""
    from scripts import audit_price_basis as apb
    from engine import sector_cycles as sc_mod

    # make price and tr detections identical (as if close_price silently reverted to TR)
    fixed = sc_mod._detect_swings(_yahoo_close("XLU", basis="tr").dropna())
    monkeypatch.setattr(sc_mod, "_detect_swings", lambda *a, **k: fixed)
    u = apb._check_golden_fixture()
    assert u.n_failed == 1, "golden fixture should FAIL when price turns == tr turns"


def test_audit_basis_homogeneous_fails_on_stale_tr_sector(tmp_path, monkeypatch):
    """A live forward log with a sector row stamped basis='tr' (a pre-flip leftover) FAILS."""
    from scripts import audit_price_basis as apb
    from lib import config

    eng_dir = tmp_path / "sector_cycles"
    eng_dir.mkdir(parents=True)
    bad = pd.DataFrame([
        {"date": "2026-07-02", "id": "xlk", "kind": "sector", "basis": "tr"},   # STALE
        {"date": "2026-07-02", "id": "b-mag7", "kind": "basket", "basis": "tr"},  # OK
    ])
    bad.to_parquet(eng_dir / "forward_log.parquet", index=False)
    (tmp_path / "country_cycles").mkdir(parents=True)  # absent log → flagged skip, not fail

    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    u = apb._check_basis_homogeneous()
    assert u.n_failed == 1, "a sector row stamped basis='tr' must FAIL basis_homogeneous"
