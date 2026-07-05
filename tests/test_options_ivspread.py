"""Pure-function tests for engine/options_ivspread.py — Cremers-Weinbaum call−put IV spread
(directional options confirmer, display-only until the forward-IC gate validates)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from engine import options_ivspread as S  # noqa: E402


def _chain(underlying="XYZ", spot=100.0, call_iv=0.32, put_iv=0.30, days=30, strikes=(0.95, 1.0, 1.05)):
    """A minimal matched-strike chain: at each strike a CALL (call_iv) and a PUT (put_iv), so
    every matched pair's spread = call_iv − put_iv. Two expiries exercise expiry selection."""
    T = days / 365.0
    rows = []
    for exp, t in [("2026-07-21", T), ("2027-01-21", T * 6)]:
        for k_mult in strikes:
            K = spot * k_mult
            rows.append(dict(underlying=underlying, expiry=exp, K=K, T=t, is_call=True,
                             iv=call_iv, delta=0.5, oi=100, gamma=0.01, volume=10,
                             spot=spot, asof="2026-06-21"))
            rows.append(dict(underlying=underlying, expiry=exp, K=K, T=t, is_call=False,
                             iv=put_iv, delta=-0.5, oi=100, gamma=0.01, volume=10,
                             spot=spot, asof="2026-06-21"))
    return pd.DataFrame(rows)


def test_compute_ivspread_calls_richer():
    m = S.compute_ivspread(_chain(call_iv=0.34, put_iv=0.30))
    assert m is not None
    assert abs(m["ivspread"] - 0.04) < 1e-6            # +4 vol pts call-over-put
    assert m["n_pairs"] == 3 and m["weight_kind"] == "oi"
    assert 25 <= m["tenor_days"] <= 35                 # picked the ~30d expiry, not the far one


def test_compute_ivspread_puts_richer():
    m = S.compute_ivspread(_chain(call_iv=0.30, put_iv=0.34))
    assert m["ivspread"] < 0                            # puts richer → negative spread


def test_ivspread_map_multi_underlying():
    chain = pd.concat([_chain("AAA", call_iv=0.36, put_iv=0.30),
                       _chain("BBB", call_iv=0.30, put_iv=0.35)], ignore_index=True)
    mp = S.ivspread_map(chain)
    assert set(mp) == {"AAA", "BBB"}
    assert mp["AAA"]["ivspread"] > 0 and mp["BBB"]["ivspread"] < 0


def test_compute_degrades_empty():
    assert S.compute_ivspread(pd.DataFrame()) is None
    assert S.compute_ivspread(None) is None
    assert S.ivspread_map(None) == {}


# ---- the confirmer -------------------------------------------------------- #
def test_assess_confirm_when_calls_strongly_richer():
    m = S.compute_ivspread(_chain(call_iv=0.35, put_iv=0.30))     # +5 vol pts
    a = S.assess(m)
    assert a["verdict"] == "confirm" and a["score"] >= 1.0
    assert any(r["tone"] == "confirm" for r in a["reasons"])


def test_assess_caution_when_puts_strongly_richer():
    m = S.compute_ivspread(_chain(call_iv=0.30, put_iv=0.35))     # −5 vol pts
    a = S.assess(m)
    assert a["verdict"] == "caution" and a["score"] <= -1.0


def test_assess_neutral_near_parity():
    m = S.compute_ivspread(_chain(call_iv=0.302, put_iv=0.30))    # +0.2 vol pts, inside band
    a = S.assess(m)
    assert a["verdict"] == "neutral" and a["score"] == 0.0


def test_assess_direction_guard_caps_long_on_falling_name():
    m = S.compute_ivspread(_chain(call_iv=0.35, put_iv=0.30))     # would confirm a long
    a = S.assess(m, direction="down")
    assert a["score"] == 0.0 and a["verdict"] == "neutral"


def test_assess_change_reinforces_modest_level():
    m = S.compute_ivspread(_chain(call_iv=0.31, put_iv=0.30))     # +1 vol pt = modest (+0.5)
    assert S.assess(m)["verdict"] == "neutral"                     # modest level alone → neutral
    a = S.assess(m, chg=0.006)                                     # demand building (+0.5) → 1.0
    assert a["verdict"] == "confirm"


def test_assess_thin_pairs_returns_none():
    assert S.assess({"ivspread": 0.04, "n_pairs": 2}) is None      # below min_pairs
    assert S.assess(None) is None


# ---- ledger / disk -------------------------------------------------------- #
def test_snapshot_idempotent_and_prior_map(monkeypatch, tmp_path):
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    chain = _chain("AAA", call_iv=0.34, put_iv=0.30)
    assert S.snapshot(chain=chain) == 1                            # one underlying added
    assert S.snapshot(chain=chain) == 0                            # same (date,underlying) → idempotent
    led = S.load_history()
    assert led is not None and len(led) == 1
    pm = S.prior_spread_map()
    assert abs(pm["AAA"] - 0.04) < 1e-6


def test_build_snapshot_is_context_only():
    pay = S.build_snapshot()
    assert pay["is_context_only"] is True
    assert pay["scored"] is False
    assert pay["schema"] == S.SCHEMA


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

    # Build a synthetic panel with a monotone signal.  Strong positive IC so the
    # HAC t-stat is robustly non-NaN across all reasonable random seeds.
    dates = [f"2020-01-{i+2:02d}" for i in range(25)]
    underlyings = [f"SYM{j:02d}" for j in range(15)]

    rows = []
    spot_base = 100.0
    for i, d in enumerate(dates):
        for j, u in enumerate(underlyings):
            rows.append({"date": d, "underlying": u,
                         "ivspread": float(j) / 14.0,  # cross-sectional rank matches j
                         "spot": spot_base + i * 0.5 + j * 0.1})
    panel = pd.DataFrame(rows)

    from scripts.validate_options_ivspread import _fwd_ic
    result = _fwd_ic(panel, h=5)

    assert result["n_dates"] > 0, "Expected non-zero IC dates from synthetic panel"
    hac_t = result.get("hac_t")
    assert hac_t is not None, "_fwd_ic did not return 'hac_t' key"
    assert np.isfinite(float(hac_t)), (
        f"hac_t is {hac_t!r} — expected a finite float. "
        "This indicates the t_hac key is still wrong (ic_summary returns 't_hac', "
        "not 't' or 'hac_t')."
    )
