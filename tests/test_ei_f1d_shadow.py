"""Regression tests for the EI-F1D-RW shadow review forward-outcome machinery
(scripts/ei_shadow_review.py).

The load-bearing invariant: evaluate_f1d_shadow's D_f / Wilson / falsification /
flip-eligibility block is live ONLY on a ledger that has been through
join_forward_outcomes (which creates stopped_{H}d / matured_{H}d). PR #1505
originally shipped with the F1D branch evaluating the RAW ledger, leaving the
whole block permanently None/False — these tests pin both sides of that seam so
a future refactor can't silently disconnect the join again.

Wilson convention (P2_5_INTERACTION_PREREG.md §8): one-sided 95% upper bound
(z=1.645) → alpha=0.10 through the two-sided _wilson_cluster_bootstrap idiom.
"""
import numpy as np
import pandas as pd
import pytest

import scripts.ei_shadow_review as esr

# Synthetic price paths: GOODCO never draws down 5%; BADCO loses >5% within
# ~13 bars of any entry — so stop-out at 21d/63d is deterministic per ticker.
_IDX = pd.bdate_range("2025-01-02", "2025-12-31")
_GOOD = pd.Series(100.0 * (1.001 ** np.arange(len(_IDX))), index=_IDX)
_BAD = pd.Series(100.0 * (0.996 ** np.arange(len(_IDX))), index=_IDX)


def _ledger(qual_is_good: bool) -> pd.DataFrame:
    """30 weekly clusters (~2.3 quarters) of paired GOODCO/BADCO rows, with all
    c*_qual flags set on one ticker family per `qual_is_good`."""
    rows = []
    for asof in pd.date_range("2025-01-06", periods=30, freq="7D"):
        for ticker in ("GOODCO", "BADCO"):
            qual = (ticker == "GOODCO") if qual_is_good else (ticker == "BADCO")
            rows.append({
                "asof": asof, "ticker": ticker, "board_name": "us_stocks",
                "washout_active": True, "dd_pct": 30.0, "ext_z": -1.0,
                "rs_sector_quartile": 1, "above_200": False, "blend_sorted": 0.5,
                "f1d_shadow_bonus": 0.1 if qual else 0.0,
                "f1d_shadow_rank": 1, "gate_state": "armed",
                "logged_at": "2025-01-01T00:00:00",
                **{c: qual for c in esr.F1D_CONFIGS.values()},
            })
    return pd.DataFrame(rows)


@pytest.fixture(autouse=True)
def _synthetic_prices(monkeypatch):
    monkeypatch.setattr(
        esr, "_load_close_for_ticker",
        lambda t: _GOOD if t == "GOODCO" else _BAD,
    )


def test_raw_ledger_leaves_flip_block_dark():
    """Without the forward join the D_f block must stay None/False (counts-only) —
    the graceful absent-data path, and the shape of the original #1505 defect."""
    c6 = esr.evaluate_f1d_shadow(_ledger(qual_is_good=True))["configs"]["C6"]
    assert c6["D_f_63d_pp"] is None
    assert c6["wilson_upper_63d"] is None
    assert c6["flip_eligible"] is False


def test_joined_ledger_lights_flip_machinery():
    """After join_forward_outcomes, D_f/Wilson populate and the flip criterion
    (D_f<0, Wilson_upper<0, >=25 clusters, >=2 quarters) is reachable."""
    joined = esr.join_forward_outcomes(_ledger(qual_is_good=True), horizons=esr.HORIZONS)
    assert joined["matured_63d"].any() and joined["matured_21d"].any()

    res = esr.evaluate_f1d_shadow(joined)
    assert res["accrual"]["clusters_pass"] and res["accrual"]["quarters_pass"]
    c6 = res["configs"]["C6"]
    # qualified = GOODCO (never stops), unqualified = BADCO (always stops) → −100pp
    assert c6["D_f_63d_pp"] == pytest.approx(-100.0)
    assert c6["D_f_21d_pp"] == pytest.approx(-100.0)
    assert c6["wilson_upper_63d"] is not None and c6["wilson_upper_63d"] < 0
    assert c6["falsification_tripped"] is False
    assert c6["flip_eligible"] is True


def test_adverse_direction_trips_falsification():
    """Qualified rows stopping out MORE (D_f >= +3.34pp) must trip the tripwire
    and block flip eligibility."""
    joined = esr.join_forward_outcomes(_ledger(qual_is_good=False), horizons=esr.HORIZONS)
    c6 = esr.evaluate_f1d_shadow(joined)["configs"]["C6"]
    assert c6["D_f_63d_pp"] >= esr.F1D_FALSIFICATION_DF
    assert c6["falsification_tripped"] is True
    assert c6["flip_eligible"] is False
