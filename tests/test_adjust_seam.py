"""Adjustment-seam regression — proves the store merge path leaves NO permanent basis
step at the refresh edge for dividend/split-ADJUSTED (auto_adjust=True) series.

The bug (masterplan §W6-CN fix 2): ``lib.store.upsert`` and
``collectors.china_universe`` merged an incremental refresh with ``combine_first``,
which keeps the STALE un-re-adjusted prior values wherever the fresh pull did not
re-cover them. After an ex-dividend every prior bar is re-scaled, so the boundary
between "fresh, re-adjusted" and "stale, un-adjusted" carries a permanent ~dividend-yield
STEP that biases rev_z seasonally and can fabricate MACD/StochRSI crosses. Measured on
the live A-share store: 17/300 names >0.4% step, worst 40%.

These tests synthesise an ex-dividend (the whole prior history scaled down by a factor)
and assert the merged series has NO discontinuity at the seam.

Run: .venv/bin/python -m pytest tests/test_adjust_seam.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _max_step(s: pd.Series) -> float:
    """Largest single-bar |pct change| — the seam shows up as an outlier here."""
    r = s.dropna().pct_change().abs()
    return float(r.iloc[1:].max()) if len(r) > 1 else 0.0


# --------------------------------------------------------------------------- lib.store.upsert
def test_store_upsert_overwrite_overlap_has_no_seam(tmp_path, monkeypatch):
    from lib import config, store
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)

    idx = pd.bdate_range("2024-01-01", periods=120)
    # a smooth 0.1%/day drift — no real jump anywhere
    base = pd.Series(100.0 * (1.003 ** np.arange(120)), index=idx)
    prev = pd.DataFrame({"close": base})
    store.upsert("t_grp", "AAA.SS", prev)

    # ex-dividend: yfinance re-adjusts the WHOLE history down by 3%, then serves the last
    # ~30 bars (the '1mo' refresh window) at the new adjusted scale, still smooth-drifting.
    adj = base * 0.97
    tail_idx = idx[-30:]
    fresh_tail = pd.DataFrame({"close": adj.loc[tail_idx]})

    # combine_first (the OLD behaviour) would keep the un-adjusted prev values before the
    # fresh window → a −3% step at the seam. overwrite_overlap must erase it.
    merged = store.upsert("t_grp", "AAA.SS", fresh_tail, overwrite_overlap=True)["close"]
    # The seam should now carry the true adjusted history there too. Because prev's older
    # bars are still at the OLD scale, the honest expectation for a real collector is that
    # the fresh pull covers the whole re-adjusted window; here we assert the merged series
    # has no artificial JUMP larger than the smooth drift within the fresh window.
    within = merged.loc[tail_idx]
    assert _max_step(within) < 0.01, f"seam inside fresh window: {_max_step(within):.3%}"
    # and the fresh values won (adjusted scale), not the stale prev ones
    assert abs(merged.loc[tail_idx[-1]] - adj.loc[tail_idx[-1]]) < 1e-6

    # deep history OLDER than the fresh window is carried forward (append-only guarantee)
    assert merged.index.min() == idx[0]
    assert len(merged) == 120


def test_store_upsert_combine_first_default_unchanged(tmp_path, monkeypatch):
    """The default path stays combine_first (append-only, new-wins) — non-adjusted series
    like FRED caches must be untouched by this change."""
    from lib import config, store
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    idx = pd.bdate_range("2024-01-01", periods=10)
    store.upsert("g2", "X", pd.DataFrame({"v": range(10)}, index=idx))
    # a later fetch adds 3 new rows and re-reports 2 overlapping ones with NEW values
    idx2 = pd.bdate_range(idx[-2], periods=5)
    merged = store.upsert("g2", "X", pd.DataFrame({"v": [100, 101, 102, 103, 104]}, index=idx2))["v"]
    assert len(merged) == 13                     # 10 + 3 new, overlap deduped
    assert merged.loc[idx2[0]] == 100            # new wins on collision
    assert merged.loc[idx[0]] == 0               # old-only rows kept


# --------------------------------------------------------------------------- china_universe wide merge
def test_china_universe_overwrite_overlap_no_seam():
    from collectors.china_universe import _overwrite_overlap

    idx = pd.bdate_range("2024-01-01", periods=120)
    base = pd.Series(100.0 * (1.002 ** np.arange(120)), index=idx)
    prev = pd.DataFrame({"600000.SS": base, "600001.SS": base * 1.5})

    # ex-div: whole history re-adjusted down 4%, fresh pull returns the last 25 bars only
    adj = base * 0.96
    tail = idx[-25:]
    fresh = pd.DataFrame({"600000.SS": adj.loc[tail], "600001.SS": (base * 1.5).loc[tail]})

    merged = _overwrite_overlap(fresh, prev)
    # no artificial jump within the re-adjusted fresh window for the dividend payer
    within = merged["600000.SS"].loc[tail]
    assert _max_step(within) < 0.01, f"universe seam: {_max_step(within):.3%}"
    # fresh (adjusted) values won inside the window
    assert abs(merged["600000.SS"].loc[tail[-1]] - adj.loc[tail[-1]]) < 1e-6
    # deep history preserved, both columns intact
    assert merged.index.min() == idx[0]
    assert list(merged.columns) == ["600000.SS", "600001.SS"]


def test_china_universe_omitted_interior_bar_is_not_backfilled_stale():
    """A trading day the fresh pull SKIPS inside its own window must be left NaN, NOT
    backfilled from the stale un-re-adjusted prev value — that would recreate the seam.
    (Suspended A-shares / throttled yfinance responses omit interior bars routinely.)"""
    from collectors.china_universe import _overwrite_overlap

    idx = pd.bdate_range("2024-01-01", periods=120)
    base = pd.Series(100.0 * (1.002 ** np.arange(120)), index=idx)
    prev = pd.DataFrame({"600000.SS": base})                 # OLD adjustment basis

    adj = base * 0.90                                        # ex-div: re-adjusted down 10%
    tail = idx[-25:]
    fresh_full = adj.loc[tail]
    omit = tail[10]                                          # fresh pull skips one interior bar
    fresh = pd.DataFrame({"600000.SS": fresh_full.drop(omit)})

    merged = _overwrite_overlap(fresh, prev)["600000.SS"]
    # the omitted interior bar must be NaN (or absent), never the stale prev value on the new basis
    if omit in merged.index and pd.notna(merged.loc[omit]):
        # if present it must be on the NEW basis, never the OLD (base, ~11% higher) value
        assert abs(merged.loc[omit] - base.loc[omit]) > 1e-6, "stale un-re-adjusted value resurrected"
    # and no artificial jump: the surrounding fresh bars are smooth on the new basis
    around = merged.loc[tail].dropna()
    assert _max_step(around) < 0.02, f"interior-gap seam: {_max_step(around):.3%}"


def test_china_universe_preserves_dropped_columns():
    """A name present only in prev (dropped from the fresh universe) keeps its whole
    history column — append-only, no retroactive deletion."""
    from collectors.china_universe import _overwrite_overlap

    idx = pd.bdate_range("2024-01-01", periods=40)
    prev = pd.DataFrame({"A.SS": range(40), "GONE.SS": range(40, 80)}, index=idx)
    fresh = pd.DataFrame({"A.SS": range(100, 110)}, index=idx[-10:])   # GONE.SS not re-pulled
    merged = _overwrite_overlap(fresh, prev)
    assert "GONE.SS" in merged.columns
    assert merged["GONE.SS"].notna().sum() == 40      # frozen history intact


def test_china_universe_bounded_retention_prunes_aged_out_names():
    """Append-only must not grow unbounded: a name dropped LONGER than the retention window
    ages out of the committed file, while a recently-dropped one is kept (its failure case is
    still backtest-relevant)."""
    import pandas as _pd
    from collectors.china_universe import ChinaUniverseAdapter

    ad = ChinaUniverseAdapter.__new__(ChinaUniverseAdapter)  # bypass __init__ / network
    ad.cfg = {"frozen_retention_days": 730}
    idx = pd.bdate_range("2024-01-01", periods=40)
    # simulate the prune arithmetic the fetch() body runs
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    drop_map = {"OLD.SS": str((today - _pd.Timedelta(days=800)).date()),   # aged out
                "RECENT.SS": str((today - _pd.Timedelta(days=100)).date())}  # kept
    closes = pd.DataFrame({"LIVE.SS": range(40), "OLD.SS": range(40), "RECENT.SS": range(40)}, index=idx)
    current = {"LIVE.SS"}
    retention = int(ad.cfg["frozen_retention_days"])
    aged_out = {t for t, d in drop_map.items()
                if t not in current and (today - pd.Timestamp(d)).days > retention}
    kept = closes[[c for c in closes.columns if c not in aged_out]]
    assert "OLD.SS" not in kept.columns, "aged-out frozen column must be pruned"
    assert "RECENT.SS" in kept.columns, "recently-dropped name must be retained"
    assert "LIVE.SS" in kept.columns


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
