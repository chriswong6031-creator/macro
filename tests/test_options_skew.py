"""Pure-function tests for engine/options_skew.py — single-name IV skew (display-only)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

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


def test_build_snapshot_is_context_only():
    # no gate file in a clean env → dormant 'measuring' state, never scored
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
