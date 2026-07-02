"""C2 — intl macro de-risk sleeve producer + verdict + wire-safety (masterplan §5 C2, W2).

The C2 channel VALIDATED as CONTEXT against the declared US-SPY-drawdown target (DSR 0.83
< the 0.90 door; residual DD-content vs the 5 US MRS legs marginal/window-fragile), so it is
NOT wired into conditions._macro_risk_legs. These tests guard:

  * the leaf producer (engine.intl_sleeve) — pure, causal (publication-lagged, no look-ahead),
    honest per-market leg availability (EZ runs curve+short only — EZ unemployment is dead);
  * the verdict — the ledger + the intl_claims BACKFILL agree that C2 is CONTEXT, un-sized, kill;
  * leg-zeroing on staleness — engine.intl_feed returns weight 0 for a stale/CONTEXT C2;
  * MRS wire-safety — the MRS composite is UNCHANGED because no intl leg was added, AND the
    general invariant that a zero-weight leg cannot move the composite (the guarantee any
    FUTURE wave relies on when it does clear the door).
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

from engine import intl_claims, intl_feed, intl_sleeve  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. leaf producer — purity + honest availability
# --------------------------------------------------------------------------- #
def test_intl_sleeve_imports_nothing_from_the_scoring_core():
    """engine.intl_sleeve is a LEAF: it must not import conditions/stock_score/playbook."""
    src = (_ROOT / "engine" / "intl_sleeve.py").read_text()
    for forbidden in ("engine.conditions", "engine.stock_score", "engine.playbook",
                      "from engine import conditions", "from engine import stock_score",
                      "from engine import playbook"):
        for line in src.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")):
                assert forbidden not in s, f"leaf purity violated: {s}"


def test_pooled_markets_drop_kr():
    """INTL-50: KR is DROPPED from the pooled gate (the uniform gate HARMS Korea)."""
    assert "KR" not in intl_sleeve.POOLED_MARKETS
    assert set(intl_sleeve.POOLED_MARKETS) == {"JP", "EZ", "GB"}


def test_availability_is_honest_ez_has_no_sahm_leg():
    """EZ unemployment is dead (frozen 2023-01) → EZ runs CURVE + SHORT only, never a faked
    Sahm leg. JP + GB carry all three legs (their unemployment series are live)."""
    avail = intl_sleeve.availability()
    assert set(avail["EZ"]) == {"curve", "short"}, avail["EZ"]
    assert "sahm" not in avail["EZ"]
    assert "sahm" in avail["JP"] and "sahm" in avail["GB"]


def test_pooled_feature_is_a_fraction_in_unit_interval():
    feat = intl_sleeve.pooled_feature().dropna()
    assert len(feat) > 1000
    assert float(feat.min()) >= 0.0 - 1e-9 and float(feat.max()) <= 1.0 + 1e-9
    # the fraction only takes values {0, 1/3, 2/3, 1} (3 pooled markets) up to fp noise
    vals = set(round(float(v), 4) for v in feat.unique())
    allowed = {0.0, round(1 / 3, 4), round(2 / 3, 4), 1.0}
    assert vals <= allowed, f"unexpected fraction levels: {vals - allowed}"


# --------------------------------------------------------------------------- #
# 2. builder causality — no look-ahead (publication lag + monthly ffill)
# --------------------------------------------------------------------------- #
def test_feature_is_publication_lagged_no_lookahead(monkeypatch):
    """A synthetic monthly de-risk print dated month M (all-legs-firing) must NOT move the
    daily feature before M + PUB_LAG_M. This proves the +1m publication lag is applied and
    that a value is never visible before its (lagged) date."""
    # a monthly index; craft series so the de-risk gate flips ON exactly at 2010-06.
    midx = pd.date_range("2005-01-01", "2015-01-01", freq="MS")

    def fake_read(group, name):
        s = pd.Series(0.0, index=midx)
        if name.endswith("yield_10y"):
            # 10y BELOW short from 2010-06 → curve inverted (10y - short < 0)
            s = pd.Series(2.0, index=midx)
            s.loc[s.index >= "2010-06-01"] = -1.0
            return pd.DataFrame({name: s})
        if name.endswith("short_3m"):
            # short rising + above 12m mean from 2010-06 → tightening leg + curve base
            s = pd.Series(0.5, index=midx)
            s.loc[s.index >= "2010-06-01"] = 0.5 + 0.5 * np.arange((s.index >= "2010-06-01").sum())
            return pd.DataFrame({name: s})
        if name.endswith("unemployment"):
            return pd.DataFrame({name: pd.Series(4.0, index=midx)})  # flat → no Sahm
        return None

    monkeypatch.setattr(intl_sleeve.store, "read", fake_read)
    didx = pd.bdate_range("2009-01-01", "2011-06-01")
    feat = intl_sleeve.pooled_feature(didx)
    lag = pd.DateOffset(months=intl_sleeve.PUB_LAG_M)
    flip_date = pd.Timestamp("2010-06-01") + lag       # earliest the print may be visible
    before = feat.loc[feat.index < flip_date]
    # BEFORE the lagged flip date the feature must be 0 (nothing de-risking yet) — no look-ahead
    assert float(before.fillna(0).max()) == 0.0, "feature moved BEFORE the publication-lagged date"
    # AFTER, the markets that hit >=2 legs de-risk → feature rises above 0
    after = feat.loc[feat.index >= flip_date + pd.Timedelta(days=40)]
    assert float(after.fillna(0).max()) > 0.0, "feature never fired after the lagged date"


def test_feature_value_matches_last_pooled_reading():
    feat = intl_sleeve.pooled_feature().dropna()
    assert intl_sleeve.feature_value() == float(feat.iloc[-1])


# --------------------------------------------------------------------------- #
# 3. the verdict — CONTEXT, un-sized, kill (do NOT wire)
# --------------------------------------------------------------------------- #
def test_c2_backfill_verdict_is_context_and_unsized():
    row = next(r for r in intl_claims.BACKFILL if r["id"] == "c2_intl_macro_sleeve")
    assert row["verdict"] == "CONTEXT", "C2 graded CONTEXT vs the US book — do NOT wire"
    assert row["weight_cap"] == 0.0
    assert row["kill"] is True
    # the DSR door is the binding failure; the residual DD-content is recorded
    assert row["metrics"]["dsr"] < 0.90
    assert row["gates"]["deflated_sharpe"] == "fail"


def test_c2_claim_declares_the_builder_and_a_monthly_freshness_sla():
    claim = next(c for c in intl_claims.CLAIMS if c["id"] == "c2_intl_macro_sleeve")
    assert claim["builder"] == "scripts.intl_phase0.build_c2_sleeve"
    # monthly macro + publication lag → the SLA must tolerate a quarterly-lagged print
    # but still catch a DEAD series (years stale). 120d is the chosen middle.
    assert claim["freshness_sla_days"] == 120
    # KR is not in the C2 source series (dropped from the pooled gate)
    assert not any("KR" in s for _g, s in claim["source_series"])


def test_ledger_has_c2_context_after_run():
    """The committed ledger reflects the live C2 grade (CONTEXT) with the measured numbers."""
    p = _ROOT / "data" / "intl_bridge" / "ledger.json"
    d = json.loads(p.read_text())
    c2 = next(f for f in d["features"] if f["id"] == "c2_intl_macro_sleeve")
    assert c2["verdict"] == "CONTEXT"
    assert c2["weight_cap"] == 0.0
    assert c2["kill"] is True


# --------------------------------------------------------------------------- #
# 4. leg-zeroing — intl_feed returns weight 0 for C2 (CONTEXT + on staleness)
# --------------------------------------------------------------------------- #
def _write_ledger(root: Path, feat: dict):
    d = root / "data" / "intl_bridge"
    d.mkdir(parents=True, exist_ok=True)
    (d / "ledger.json").write_text(json.dumps(
        {"asof": "2026-07-02", "family": "intl_bridge", "features": [feat]}))


def _fresh_parquet(root: Path, group: str, name: str, last: date):
    p = root / "data" / group
    p.mkdir(parents=True, exist_ok=True)
    idx = pd.date_range(end=pd.Timestamp(last), periods=10, freq="MS")
    pd.DataFrame({name: range(10)}, index=idx).to_parquet(
        p / f"{name}.parquet")


def test_intl_feed_zeroes_context_c2(tmp_path):
    """A CONTEXT verdict → weight 0 regardless of freshness (the three-state policy)."""
    _write_ledger(tmp_path, {
        "id": "c2_intl_macro_sleeve", "channel": "C2", "direction": "de-risk",
        "verdict": "CONTEXT", "weight_cap": 0.15, "kill": True,
        "source_series": ["intl_macro/JP_yield_10y"], "freshness_sla_days": 120,
        "validation_ref": "x", "notes": "",
    })
    _fresh_parquet(tmp_path, "intl_macro", "JP_yield_10y", date.today())
    st = intl_feed.features(root=tmp_path)
    assert st["c2_intl_macro_sleeve"]["weight"] == 0.0


def test_intl_feed_zeroes_on_stale_source(tmp_path):
    """Even a (hypothetical) CONFIRMED de-risk leg zeroes when its source series is stale —
    the freshness SLA on the yield/short-rate inputs. This is the leg-zeroing guarantee any
    future wave depends on when C2 (or its successors) clears the door."""
    _write_ledger(tmp_path, {
        "id": "c2_intl_macro_sleeve", "channel": "C2", "direction": "de-risk",
        "verdict": "CONFIRMED", "weight_cap": 0.15, "kill": False,
        "source_series": ["intl_macro/JP_yield_10y"], "freshness_sla_days": 120,
        "validation_ref": "x", "notes": "",
    })
    # a print 400 days old vs a 120d SLA → stale → weight 0
    _fresh_parquet(tmp_path, "intl_macro", "JP_yield_10y", date.today() - timedelta(days=400))
    st = intl_feed.features(root=tmp_path)
    assert st["c2_intl_macro_sleeve"]["stale"] is True
    assert st["c2_intl_macro_sleeve"]["weight"] == 0.0


# --------------------------------------------------------------------------- #
# 5. MRS wire-safety — composite UNCHANGED (no intl leg added) + zero-weight invariant
# --------------------------------------------------------------------------- #
def test_no_intl_leg_was_wired_into_macro_risk_legs():
    """C2 is CONTEXT → the MRS composite must be UNCHANGED. Assert _macro_risk_legs still
    exposes exactly the 5 US legs and no intl_sleeve / intl_feed hook was added."""
    src = (_ROOT / "engine" / "conditions.py").read_text()
    region = src[src.index("def _macro_risk_legs"):src.index("def macro_risk_series")]
    for us_leg in ("recession", "drawdown", "nfci", "liquidity", "transition"):
        assert f'legs["{us_leg}"]' in region, f"US leg {us_leg} missing"
    # no intl leg / no leaf import into the scoring seam (the whole point of a CONTEXT verdict)
    assert "intl_sleeve" not in region
    assert 'legs["intl' not in region
    assert "intl_feed" not in region


def test_zero_weight_leg_cannot_move_the_mrs_composite():
    """The invariant a FUTURE wave relies on when C2's successor clears the door: adding a
    leg with weight 0 (or an unavailable leg) leaves the renormalized composite identical.
    Tests engine.conditions._combine_legs directly (the MRS combiner)."""
    from engine.conditions import _combine_legs
    idx = pd.date_range("2020-01-01", periods=200, freq="B")
    base_legs = {
        "recession": (pd.Series(0.4, index=idx), pd.Series(True, index=idx)),
        "drawdown": (pd.Series(0.6, index=idx), pd.Series(True, index=idx)),
    }
    w = {"recession": 1.0, "drawdown": 1.0, "intl_sleeve": 0.0}
    base = _combine_legs(base_legs, w)
    # add an intl leg with weight 0 → composite must be byte-identical
    with_zero = _combine_legs({**base_legs,
                               "intl_sleeve": (pd.Series(1.0, index=idx),
                                               pd.Series(True, index=idx))}, w)
    pd.testing.assert_series_equal(base, with_zero, check_names=False)
    # and an UNAVAILABLE leg (available=False) also cannot move it, at any weight
    with_unavail = _combine_legs({**base_legs,
                                  "intl_sleeve": (pd.Series(1.0, index=idx),
                                                  pd.Series(False, index=idx))},
                                 {"recession": 1.0, "drawdown": 1.0, "intl_sleeve": 0.5})
    pd.testing.assert_series_equal(base, with_unavail, check_names=False)
