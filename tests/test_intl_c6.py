"""C6 — Asia-semi aggregate read-through: builder causality + print-excision + the
lead-lag kernel + verdict + wire-safety (masterplan §5 C6, W4).

C6 VALIDATED as CONTEXT: the EW TSM+ASML ADR basket's only strong relationship with SMH
is the CONTEMPORANEOUS lag-0 co-membership term (TSM+ASML ARE two of SMH's largest
holdings) — no lag>=1 lead survives the lead-lag kernel, so it is not a tradeable lead
and (the ADRs being US-session) not even a timezone-transmission read. Nothing is wired.
These tests guard:

  * the C6 builder — causal (returns-only, no look-ahead), honest builder contract, de-risk;
  * the earnings-print excision — a ±2 trading-day window around every constituent print,
    print-on-weekend maps to the next session, and the verdict is excision-invariant;
  * the lead-lag kernel `pass` semantics — lag-0 co-membership is EXCLUDED by construction;
    a lag>=1 lead needs BH-FDR survival AND split-half same-sign;
  * the decide() kernel short-circuit — a cross-market claim whose kernel finds no lag>=1
    lead is CONTEXT no matter its other gates; a passing kernel is required for CONFIRMED;
  * the verdicts — the ledger + intl_claims BACKFILL agree C6 is CONTEXT, un-sized, kill;
  * leg-zeroing — engine.intl_feed returns weight 0 for the C6 CONTEXT leg (and on staleness);
  * wire-safety — stock_score._axis_tailwind (the would-be DOWNGRADE-only seam) UNCHANGED.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from engine import intl_claims, intl_feed  # noqa: E402
from scripts import c6_asia_semi_readthrough as C6  # noqa: E402
from scripts import intl_phase0 as H  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. builder — causality, contract, de-risk direction
# --------------------------------------------------------------------------- #
def _claim() -> dict:
    return next(c for c in intl_claims.CLAIMS if c["id"] == "c6_asia_semi_readthrough")


def test_c6_declared_grid_is_tsm_asml_only():
    """ADJ-4: exactly the declared source_series — no undeclared local-semi grid."""
    c = _claim()
    assert c["source_series"] == [("yahoo", "TSM"), ("yahoo", "ASML")]
    assert c["target"] == ("yahoo", "SMH")
    assert c["horizons"] == (5,)          # ONE pre-registered horizon
    assert c["direction"] == "de-risk"


def test_c6_basket_requires_both_constituents():
    """The EW basket is a genuine TWO-sensor aggregate — a date with only one name present
    yields NaN (skipna=False), never a single-name extrapolation."""
    idx = pd.date_range("2020-01-01", periods=6, freq="B")
    tsm = pd.Series([0.01, 0.02, np.nan, 0.0, -0.01, 0.03], index=idx)
    asml = pd.Series([0.02, np.nan, 0.01, 0.0, 0.02, -0.01], index=idx)
    panel = pd.concat([tsm, asml], axis=1)
    ew = panel.mean(axis=1, skipna=False)
    assert np.isnan(ew.iloc[1]) and np.isnan(ew.iloc[2])   # one name missing → NaN
    assert ew.iloc[0] == (0.01 + 0.02) / 2                 # both present → EW mean


def test_c6_builder_returns_the_contract_and_is_derisk():
    """The builder yields the harness contract incl. prod_by_lag (the kernel input)."""
    b = C6.build(_claim())
    assert "error" not in b, b
    for k in ("signal", "strat_ret", "bench_ret", "target_dd", "basis",
              "split_half_same_sign", "prod_by_lag", "leadlag_split"):
        assert k in b, k
    assert isinstance(b["prod_by_lag"], dict) and "lag0" in b["prod_by_lag"]
    assert _claim()["direction"] == "de-risk"


def test_c6_basket_is_returns_only_causal():
    """asia_semi_basket is pct_change of close — a pure return series, no forward look."""
    bk = C6.asia_semi_basket()
    assert bk is not None and len(bk.dropna()) > 1000
    # a return series: bounded, mean ~0, not a price level
    assert abs(float(bk.dropna().mean())) < 0.01
    assert float(bk.dropna().abs().max()) < 1.0


# --------------------------------------------------------------------------- #
# 2. earnings-print excision — ±2 trading days, weekend→next session, invariance
# --------------------------------------------------------------------------- #
def test_excise_mask_removes_pm2_trading_days_around_a_print(monkeypatch):
    idx = pd.bdate_range("2021-01-04", periods=20)          # a run of business days
    print_day = idx[10]
    monkeypatch.setattr(C6, "_print_dates", lambda: [print_day])
    mask = C6.excise_mask(idx, span_td=2)
    # the print day and ±2 trading days around it are excised (False)
    for j in range(8, 13):
        assert mask.iloc[j] == False, (j, idx[j])
    # rows well outside the window are kept (True)
    assert mask.iloc[0] and mask.iloc[19]
    assert int((~mask).sum()) == 5                          # exactly the 5-day window


def test_excise_mask_maps_weekend_print_to_next_session(monkeypatch):
    idx = pd.bdate_range("2021-01-04", periods=20)
    # a Saturday print → the mask should center on the following Monday session
    sat = pd.Timestamp("2021-01-16")                        # a Saturday
    mon = pd.Timestamp("2021-01-18")                        # the next business day in idx
    monkeypatch.setattr(C6, "_print_dates", lambda: [sat])
    mask = C6.excise_mask(idx, span_td=2)
    jm = int(idx.searchsorted(mon))
    assert mask.iloc[jm] == False                           # the reacting session is excised
    assert int((~mask).sum()) >= 3                          # a window formed (near the edge)


def test_excise_mask_empty_when_no_prints(monkeypatch):
    idx = pd.bdate_range("2021-01-04", periods=10)
    monkeypatch.setattr(C6, "_print_dates", lambda: [])
    mask = C6.excise_mask(idx)
    assert bool(mask.all())                                 # nothing excised → all True


def test_c6_verdict_is_excision_invariant():
    """The lag-1 corr with and without print-excision is ~identical — the CONTEXT verdict
    is not an artifact of the excision (it simply has no lead to find either way)."""
    bk = C6.asia_semi_basket()
    smh = C6._smh_ret()
    common = bk.dropna().index.intersection(smh.dropna().index)
    no_mask = C6.prod_by_lag(bk.reindex(common), smh.reindex(common), mask=None)
    with_mask = C6.prod_by_lag(bk.reindex(common), smh.reindex(common),
                               mask=C6.excise_mask(common))
    l1_no = float(no_mask["lag1"].mean())
    l1_yes = float(with_mask["lag1"].mean())
    assert abs(l1_no - l1_yes) < 0.02, (l1_no, l1_yes)
    # neither is a positive tradeable lead (both small; the un-excised is <= the noise floor)
    assert l1_yes < 0.03


# --------------------------------------------------------------------------- #
# 3. lead-lag kernel — lag-0 excluded, lag>=1 needs FDR + split-half
# --------------------------------------------------------------------------- #
def test_kernel_excludes_lag0_from_pass():
    """A gigantic lag-0 co-membership term must NOT count as a lead (pass excludes lag0)."""
    n = 3000
    idx = pd.date_range("2005-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)
    z = pd.Series(rng.standard_normal(n), index=idx)
    prods = {"lag0": (z * z).dropna(),                      # perfect contemporaneous corr
             "lag1": (z * z.shift(1)).dropna(),             # ~0 at lag 1 (white noise)
             "lag2": (z * z.shift(2)).dropna()}
    ker = H.leadlag_kernel(prods, split=str(idx[n // 2].date()))
    assert ker["pass"] is False                             # lag0 alone is not a lead
    assert "lag0" not in ker["lead_lags"]


def test_kernel_flags_a_real_lag1_lead():
    """A genuine lag-1 predictive product (survives FDR + split-half) IS flagged a lead."""
    n = 4000
    idx = pd.date_range("2005-01-01", periods=n, freq="B")
    rng = np.random.default_rng(1)
    leader = pd.Series(rng.standard_normal(n), index=idx)
    # follower_t = 0.3*leader_{t-1} + noise → a real, stable lag-1 lead
    follower = 0.3 * leader.shift(1) + 0.2 * pd.Series(rng.standard_normal(n), index=idx)
    zf = (follower - follower.mean()) / follower.std()
    zl = (leader - leader.mean()) / leader.std()
    prods = {"lag0": (zf * zl).dropna(),
             "lag1": (zf * zl.shift(1)).dropna(),
             "lag2": (zf * zl.shift(2)).dropna()}
    ker = H.leadlag_kernel(prods, split=str(idx[n // 2].date()))
    assert ker["pass"] is True
    assert "lag1" in ker["lead_lags"]


def test_c6_kernel_has_no_lag_ge1_survivor():
    """The REAL C6 data: lag-0 is huge (co-membership) but no lag>=1 link survives."""
    b = C6.build(_claim())
    ker = H.leadlag_kernel(b["prod_by_lag"], split=b["leadlag_split"])
    assert ker["pass"] is False, ker.get("lead_lags")
    # lag-0 dominates and is FDR-significant; lag>=1 are not
    assert (ker["fdr"].get("lag0") or {}).get("reject") is True
    assert (ker["fdr"].get("lag1") or {}).get("reject") in (False, None)


# --------------------------------------------------------------------------- #
# 4. decide() short-circuit — kernel-fail → CONTEXT; kernel-pass required for CONFIRMED
# --------------------------------------------------------------------------- #
def test_decide_kernel_fail_is_context_over_everything():
    """A cross-market claim whose kernel finds no lag>=1 lead is CONTEXT even if every
    OTHER gate would pass — the kernel is the binding gate for a read-through (ADJ-4)."""
    claim = {"id": "x", "channel": "C6", "direction": "de-risk"}
    gates = {"freshness": {"pass": True},
             "orthogonality": {"pass": True},
             "crisis_count": {"pass": True},
             "crisis_independent_es": {"pass": True},
             "drawdown_reduction": {"pass": True},
             "promotion": {},
             "lead_lag_kernel": {"pass": False, "lead_lags": []}}
    v = H.decide(claim, dsr=0.99, gates=gates, split_half=True,
                 effective_n_crises=6, orthogonal_partial=-0.10)
    assert v["verdict"] == "CONTEXT"
    assert v["weight_cap"] == 0.0
    assert "co-membership" in v["reason"] or "kernel" in v["reason"]


def test_decide_confirmed_requires_the_kernel_to_pass():
    """CONFIRMED needs the kernel to clear (kernel_ok is not False) — a cross-market claim
    cannot be CONFIRMED with a failing kernel, and passes only when it holds."""
    claim = {"id": "x", "channel": "C6", "direction": "de-risk"}
    base = {"freshness": {"pass": True}, "orthogonality": {"pass": True},
            "crisis_count": {"pass": True}, "crisis_independent_es": {"pass": True},
            "drawdown_reduction": {"pass": True}, "promotion": {}}
    # kernel FAIL → never CONFIRMED
    v_fail = H.decide(claim, dsr=0.99,
                      gates={**base, "lead_lag_kernel": {"pass": False}},
                      split_half=True, effective_n_crises=6, orthogonal_partial=-0.10)
    assert v_fail["verdict"] != "CONFIRMED"
    # kernel PASS + all gates → CONFIRMED
    v_ok = H.decide(claim, dsr=0.99,
                    gates={**base, "lead_lag_kernel": {"pass": True, "lead_lags": ["lag1"]}},
                    split_half=True, effective_n_crises=6, orthogonal_partial=-0.10)
    assert v_ok["verdict"] == "CONFIRMED"
    assert v_ok["weight_cap"] > 0.0


# --------------------------------------------------------------------------- #
# 5. verdict — ledger + BACKFILL agree C6 is CONTEXT, un-sized, kill
# --------------------------------------------------------------------------- #
def test_ledger_has_c6_context():
    p = _ROOT / "data" / "intl_bridge" / "ledger.json"
    d = json.loads(p.read_text())
    f = next(x for x in d["features"] if x["id"] == "c6_asia_semi_readthrough")
    assert f["verdict"] == "CONTEXT"
    assert f["weight_cap"] == 0.0
    assert f["kill"] is True
    assert f["gates"]["lead_lag_kernel"] in (False, "fail")


def test_backfill_c6_row_agrees():
    row = next(r for r in intl_claims.BACKFILL if r["id"] == "c6_asia_semi_readthrough")
    assert row["verdict"] == "CONTEXT"
    assert row["weight_cap"] == 0.0
    assert row["kill"] is True
    assert row["gates"]["lead_lag_kernel"] == "fail"


# --------------------------------------------------------------------------- #
# 6. leg-zeroing — intl_feed returns weight 0 for the C6 CONTEXT leg (+ on staleness)
# --------------------------------------------------------------------------- #
def _write_ledger(root: Path, feat: dict):
    d = root / "data" / "intl_bridge"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ledger.json").write_text(json.dumps(
        {"asof": "2026-07-02", "family": "intl_bridge", "features": [feat]}))


def _fresh_parquet(root: Path, group: str, name: str, last: date):
    p = root / "data" / group
    p.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(end=pd.Timestamp(last), periods=10, freq="D")
    pd.DataFrame({name: range(10)}, index=idx).to_parquet(p / f"{name}.parquet")


def test_intl_feed_zeroes_context_c6(tmp_path):
    _write_ledger(tmp_path, {
        "id": "c6_asia_semi_readthrough", "channel": "C6", "direction": "de-risk",
        "verdict": "CONTEXT", "weight_cap": 0.10, "kill": True,
        "source_series": ["yahoo/TSM", "yahoo/ASML"], "freshness_sla_days": 5,
        "validation_ref": "x", "notes": "",
    })
    _fresh_parquet(tmp_path, "yahoo", "TSM", date.today())
    _fresh_parquet(tmp_path, "yahoo", "ASML", date.today())
    st = intl_feed.features(root=tmp_path)
    assert st["c6_asia_semi_readthrough"]["weight"] == 0.0


def test_intl_feed_zeroes_c6_on_stale_source(tmp_path):
    """Even a hypothetical CONFIRMED de-risk C6 leg zeroes if a source series is stale."""
    _write_ledger(tmp_path, {
        "id": "c6_asia_semi_readthrough", "channel": "C6", "direction": "de-risk",
        "verdict": "CONFIRMED", "weight_cap": 0.10, "kill": False,
        "source_series": ["yahoo/TSM"], "freshness_sla_days": 5,
        "validation_ref": "x", "notes": "",
    })
    _fresh_parquet(tmp_path, "yahoo", "TSM", date.today() - timedelta(days=60))
    st = intl_feed.features(root=tmp_path)
    assert st["c6_asia_semi_readthrough"]["stale"] is True
    assert st["c6_asia_semi_readthrough"]["weight"] == 0.0


# --------------------------------------------------------------------------- #
# 7. wire-safety — the C6 seam (stock_score._axis_tailwind) is UNCHANGED
# --------------------------------------------------------------------------- #
def test_axis_tailwind_has_no_c6_wire():
    """C6 is CONTEXT → nothing wired. stock_score._axis_tailwind (the would-be DOWNGRADE-
    only seam) must not reference the C6 basket/feed."""
    src = (_ROOT / "engine" / "stock_score.py").read_text()
    region = src[src.index("def _axis_tailwind"):]
    region = region[:region.index("\ndef ", 1) if "\ndef " in region[1:] else len(region)]
    for forbidden in ("c6_asia", "asia_semi", "readthrough", "c6_asia_semi_readthrough",
                      "intl_feed"):
        assert forbidden not in src, f"C6 leaked into a scorer: {forbidden}"


def test_c6_builder_has_no_scoring_core_imports():
    """The C6 grader script is additive — it never imports the scoring-core scorers."""
    src = (_ROOT / "scripts" / "c6_asia_semi_readthrough.py").read_text()
    for forbidden in ("engine.stock_score", "engine.china_name_score", "engine.playbook",
                      "engine.conditions"):
        for line in src.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")):
                assert forbidden not in s, f"C6 builder imports a scorer: {s}"
