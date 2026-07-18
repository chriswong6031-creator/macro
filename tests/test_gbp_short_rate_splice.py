"""GBP short-rate splice (IR3TIB01GBM156N → IUDSOIA/SONIA) — unit tests.

The OECD MEI UK 3m interbank series froze upstream at 2026-01-01 (AU/CA/CH
siblings still update), silently staling the GBPUSD carry input and — via the
40d ffill limit — freezing the dollar-desk smile OLS at 2026-02-26. The fix
splices BoE SONIA (IUDSOIA, daily) onto the interbank history:

  - engine/forex_inputs.load_rate honors ``<meta_key>_hist`` + ``<meta_key>_splice``
    (hist ≤ splice date, live strictly after; fail-open when either leg is absent);
  - engine/forex_dollar masks the one Δ(diff) that straddles the seam
    (flow_regime.py DXY/DTWEXBGS splice-masking precedent).

All tests run on synthetic frames via a monkeypatched lib.store.read — no
repo data / network.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import forex_dollar, forex_inputs

SPLICE = "2026-01-01"

META = {
    "short_rate": "gb_sonia",
    "short_rate_hist": "gb_short",
    "short_rate_splice": SPLICE,
}
SID_MAPS = {"fx_rates_short": {"gb_sonia": "IUDSOIA", "gb_short": "IR3TIB01GBM156N"}}


def _hist_frame() -> pd.DataFrame:
    idx = pd.date_range("2025-09-01", "2026-01-01", freq="MS")
    return pd.DataFrame({"gb_short": [4.0, 3.9, 3.8, 3.75, 3.71]}, index=idx)


def _live_frame() -> pd.DataFrame:
    idx = pd.bdate_range("2025-12-01", "2026-02-10")
    return pd.DataFrame({"gb_sonia": np.linspace(3.74, 3.72, len(idx))}, index=idx)


def _patch_store(monkeypatch, frames: dict[str, pd.DataFrame | None]):
    def fake_read(group, name):
        assert group == "fred"
        return frames.get(name)
    monkeypatch.setattr("lib.store.read", fake_read)


# ---------------------------------------------------------------------------
# forex_inputs.load_rate splice
# ---------------------------------------------------------------------------

def test_load_rate_splices_hist_then_live(monkeypatch):
    _patch_store(monkeypatch, {"IUDSOIA": _live_frame(), "IR3TIB01GBM156N": _hist_frame()})
    s = forex_inputs.load_rate(META, "short_rate", "fx_rates_short", SID_MAPS)
    assert s is not None
    seam = pd.Timestamp(SPLICE)
    # ≤ splice: hist values only (live's overlapping Dec dates must NOT leak in)
    pre = s[s.index <= seam]
    assert float(pre.loc["2026-01-01"]) == 3.71
    assert float(pre.loc["2025-12-01"]) == 3.75
    # > splice: live values only, extending past the frozen hist
    post = s[s.index > seam]
    assert not post.empty
    assert post.index.max() == pd.Timestamp("2026-02-10")
    # named after the LIVE column (downstream naming contract)
    assert s.name == "gb_sonia"
    assert s.index.is_monotonic_increasing


def test_load_rate_fail_open_when_live_absent(monkeypatch):
    """Pre-first-collection: stale history beats nothing (board keeps its factor)."""
    _patch_store(monkeypatch, {"IUDSOIA": None, "IR3TIB01GBM156N": _hist_frame()})
    s = forex_inputs.load_rate(META, "short_rate", "fx_rates_short", SID_MAPS)
    assert s is not None
    assert float(s.iloc[-1]) == 3.71


def test_load_rate_fail_open_when_hist_absent(monkeypatch):
    _patch_store(monkeypatch, {"IUDSOIA": _live_frame(), "IR3TIB01GBM156N": None})
    s = forex_inputs.load_rate(META, "short_rate", "fx_rates_short", SID_MAPS)
    assert s is not None
    assert s.index.max() == pd.Timestamp("2026-02-10")


def test_load_rate_no_hist_key_unchanged(monkeypatch):
    """Assets without a _hist mapping keep the plain single-series path."""
    _patch_store(monkeypatch, {"IUDSOIA": _live_frame()})
    meta = {"short_rate": "gb_sonia"}
    s = forex_inputs.load_rate(meta, "short_rate", "fx_rates_short", SID_MAPS)
    assert s is not None
    assert len(s) == len(_live_frame())


# ---------------------------------------------------------------------------
# forex_dollar: smile GBP leg splice + seam Δ mask
# ---------------------------------------------------------------------------

def test_smile_loader_splices_gbp_leg(monkeypatch):
    frames = {
        "IUDSOIA": _live_frame(),
        "IR3TIB01GBM156N": _hist_frame(),
        "DGS2": pd.DataFrame({"v": [4.0]}, index=[pd.Timestamp("2026-01-05")]),
    }
    def fake_read(group, name):
        return frames.get(name)
    monkeypatch.setattr("lib.store.read", fake_read)
    series = forex_dollar._load_series_for_smile(None)
    gbp = series["gbp2y"]
    assert gbp is not None
    seam = pd.Timestamp(forex_dollar._SMILE_GBP_SPLICE)
    assert float(gbp.loc["2026-01-01"]) == 3.71          # hist side
    assert gbp.index.max() == pd.Timestamp("2026-02-10")  # live side


def test_smile_loader_fail_open_missing_live(monkeypatch):
    frames = {"IR3TIB01GBM156N": _hist_frame()}
    monkeypatch.setattr("lib.store.read", lambda g, n: frames.get(n))
    series = forex_dollar._load_series_for_smile(None)
    assert series["gbp2y"] is not None
    assert float(series["gbp2y"].iloc[-1]) == 3.71


def test_mask_seam_diff_nulls_straddling_delta():
    seam = pd.Timestamp(SPLICE)
    idx = pd.to_datetime(["2025-12-30", "2025-12-31", "2026-01-02", "2026-01-05"])
    diff = pd.Series([0.01, -0.02, 0.50, 0.01], index=idx)  # 0.50 = phantom seam step
    out = forex_dollar._mask_seam_diff(diff, seam)
    assert np.isnan(out.loc["2026-01-02"])                # straddling Δ masked
    assert float(out.loc["2026-01-05"]) == 0.01           # later Δs untouched
    assert float(out.loc["2025-12-31"]) == -0.02          # pre-seam untouched


def test_mask_seam_diff_noop_outside_range():
    seam = pd.Timestamp(SPLICE)
    idx = pd.bdate_range("2026-03-01", periods=5)         # entirely post-seam
    diff = pd.Series(0.01, index=idx)
    out = forex_dollar._mask_seam_diff(diff, seam)
    assert not out.isna().any()


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
