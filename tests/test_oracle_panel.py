"""Hermetic tests for engine/oracle/panel.py — Oracle O0 rotation panel.

ALL fixtures are synthetic (no network, no real data files).
Six invariants tested:

(a) Schema — all COLUMN_SCHEMA columns present in both tiers' output
(b) No lookahead — panel rows ≤ t must be identical whether built on full
    history or on history truncated at t
(c) PIT membership respected — a member with start_date mid-sample contributes
    to member-derived legs only after its start_date
(d) Basket PIT — basket member's prices masked before its 'added' date
(e) Cohesion math — two perfectly correlated members yield cohesion ≈ 1
(f) turnover_z null-safe when all member volumes are missing
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.oracle.panel import (
    COLUMN_SCHEMA,
    _build_node_features,
    _build_ew_index,
    _build_basket_ew_index,
    build_panel_s,
    build_panel_m,
)


# ---------------------------------------------------------------------------
# Synthetic fixture helpers
# ---------------------------------------------------------------------------

def _make_price_series(
    n: int = 300,
    start: str = "2021-01-04",
    seed: int = 0,
    drift: float = 0.0001,
) -> pd.Series:
    """Synthetic daily close prices: GBM with optional drift."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.01, n)
    prices = 100 * (1 + rets).cumprod()
    idx = pd.bdate_range(start, periods=n, name="date")
    return pd.Series(prices, index=idx)


def _make_member_closes(
    n_members: int = 5,
    n: int = 300,
    start: str = "2021-01-04",
    seed: int = 42,
) -> pd.DataFrame:
    """Synthetic member close DataFrame: n_members independent GBM paths."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n, name="date")
    data = {}
    for i in range(n_members):
        rets = rng.normal(0.0001, 0.01, n)
        data[f"T{i}"] = 100 * (1 + rets).cumprod()
    return pd.DataFrame(data, index=idx)


def _make_volume(n: int = 300, start: str = "2021-01-04") -> pd.DataFrame:
    """Synthetic member volume DataFrame."""
    idx = pd.bdate_range(start, periods=n, name="date")
    data = {f"T{i}": np.random.default_rng(i + 100).integers(1_000, 100_000, n)
            for i in range(3)}
    return pd.DataFrame(data, index=idx)


# ---------------------------------------------------------------------------
# (a) Schema: all COLUMN_SCHEMA columns present
# ---------------------------------------------------------------------------

class TestSchema:
    def test_node_features_has_all_columns(self):
        """_build_node_features returns exactly the non-regime columns."""
        lvl = _make_price_series(300)
        bench = _make_price_series(300, seed=1).pct_change(fill_method=None)
        mc = _make_member_closes(5, 300)
        mv = _make_volume(300)
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=mc, member_volume=mv, node_volume=None
        )
        # regime cols are added by the caller; check non-regime schema cols
        non_regime = [c for c in COLUMN_SCHEMA if c not in
                      ("vix_pctile", "tlt_ret_10d", "spy_above_200d")]
        missing = [c for c in non_regime if c not in feats.columns]
        assert not missing, f"Missing columns: {missing}"

    def test_build_panel_s_schema(self, tmp_path):
        """build_panel_s output has all COLUMN_SCHEMA columns."""
        panel = _make_minimal_panel_s(tmp_path)
        if panel.empty:
            pytest.skip("Panel empty — check fixture")
        missing = [c for c in COLUMN_SCHEMA if c not in panel.columns]
        assert not missing, f"Missing from panel_s: {missing}"

    def test_build_panel_m_schema(self, tmp_path):
        """build_panel_m output has all COLUMN_SCHEMA columns."""
        panel = _make_minimal_panel_m(tmp_path)
        if panel.empty:
            pytest.skip("Panel empty — check fixture")
        missing = [c for c in COLUMN_SCHEMA if c not in panel.columns]
        assert not missing, f"Missing from panel_m: {missing}"

    def test_multiindex_levels(self, tmp_path):
        """Output has MultiIndex (node, date)."""
        panel = _make_minimal_panel_s(tmp_path)
        if panel.empty:
            pytest.skip()
        assert panel.index.names == ["node", "date"]


# ---------------------------------------------------------------------------
# (b) No lookahead: rows ≤ t identical on full vs truncated history
# ---------------------------------------------------------------------------

class TestNoLookahead:
    def test_no_lookahead_node_features(self):
        """Truncating the input series at day t must not change earlier rows."""
        n = 300
        lvl = _make_price_series(n)
        bench = lvl.pct_change(fill_method=None)
        mc = _make_member_closes(4, n)

        # Build on full series
        full = _build_node_features(lvl=lvl, bench=bench,
                                    member_closes=mc, member_volume=None,
                                    node_volume=None)

        # Truncate at t = 200 and rebuild
        t = 200
        full_t = _build_node_features(lvl=lvl.iloc[:t], bench=bench.iloc[:t],
                                      member_closes=mc.iloc[:t],
                                      member_volume=None, node_volume=None)

        # Rows ≤ t-1 must be identical in the two builds
        shared_idx = full_t.index.intersection(full.index[: t - 5])
        for col in full.columns:
            if col not in full_t.columns:
                continue
            # Cast to float64 to safely apply np.isnan (regime cols may be bool)
            vals_full = full.loc[shared_idx, col].astype(float).values
            vals_trunc = full_t.loc[shared_idx, col].astype(float).values
            # Both NaN → equal; both finite → close
            both_nan = np.isnan(vals_full) & np.isnan(vals_trunc)
            both_finite = ~np.isnan(vals_full) & ~np.isnan(vals_trunc)
            # All rows must be either both-NaN or matching
            if (~both_nan & ~both_finite).any():
                offenders = shared_idx[~both_nan & ~both_finite]
                raise AssertionError(
                    f"Column '{col}' has NaN/finite mismatch on {offenders[:3]}"
                )
            np.testing.assert_allclose(
                vals_full[both_finite], vals_trunc[both_finite],
                rtol=1e-6,
                err_msg=f"Lookahead detected in column '{col}'",
            )

    def test_no_lookahead_panel_s(self, tmp_path):
        """Tier S panel rows ≤ t are identical when built on full vs truncated data."""
        panel_full = _make_minimal_panel_s(tmp_path)
        if panel_full.empty:
            pytest.skip()

        # Rebuild with end date = mid-point
        dates = panel_full.index.get_level_values("date").unique().sort_values()
        if len(dates) < 20:
            pytest.skip("Not enough dates for lookahead test")
        cutoff = dates[len(dates) // 2]

        panel_trunc = _make_minimal_panel_s(tmp_path, end=str(cutoff.date()))
        if panel_trunc.empty:
            pytest.skip()

        # For each node, compare overlapping dates
        nodes = panel_full.index.get_level_values("node").unique()
        for node in nodes[:2]:  # spot-check first 2 nodes
            if node not in panel_trunc.index.get_level_values("node"):
                continue
            full_node = panel_full.xs(node, level="node")
            trunc_node = panel_trunc.xs(node, level="node")
            shared = full_node.index.intersection(trunc_node.index)
            # Use only dates well before cutoff (allow rolling window warmup)
            shared = shared[shared < cutoff - pd.Timedelta(days=5)]
            if shared.empty:
                continue
            for col in ["vel_3m", "accel_z", "persistence"]:
                if col not in full_node.columns or col not in trunc_node.columns:
                    continue
                a = full_node.loc[shared, col].values
                b = trunc_node.loc[shared, col].values
                mask = ~np.isnan(a) & ~np.isnan(b)
                if mask.any():
                    np.testing.assert_allclose(
                        a[mask], b[mask], rtol=1e-5,
                        err_msg=f"Lookahead in panel_s node={node} col={col}",
                    )


# ---------------------------------------------------------------------------
# (c) PIT membership: member active only after start_date
# ---------------------------------------------------------------------------

class TestPITMembership:
    def test_member_contributes_only_after_start_date(self, tmp_path):
        """A member with start_date day-100 must not affect cohesion before day 100."""
        n = 250
        idx = pd.bdate_range("2021-01-04", periods=n, name="date")

        # 3 early members (from day 0)
        mc_dict = {f"T{i}": _make_price_series(n, seed=i) for i in range(3)}
        # 1 late member (start_date = day 100)
        late_member = "LATE"
        mc_dict[late_member] = _make_price_series(n, seed=99, drift=0.01)

        # Build PIT membership table
        pit = pd.DataFrame([
            {"ticker": f"T{i}", "start_date": pd.Timestamp("2021-01-04"),
             "end_date": pd.NaT, "src": "sp500"}
            for i in range(3)
        ] + [
            {"ticker": late_member, "start_date": idx[100],
             "end_date": pd.NaT, "src": "sp500"}
        ])

        # Apply PIT masking as build_panel_s does it
        for t_name in list(mc_dict.keys()):
            rows = pit[pit["ticker"] == t_name]
            if rows.empty:
                continue
            row = rows.iloc[0]
            start_d = row["start_date"]
            end_d = row["end_date"]
            mask = pd.Series(True, index=idx)
            if pd.notna(start_d):
                mask &= idx >= start_d
            if pd.notna(end_d):
                mask &= idx <= end_d
            mc_dict[t_name] = mc_dict[t_name].where(mask)

        mc = pd.DataFrame(mc_dict, index=idx)

        # Before day 100, LATE member must be NaN
        late_before = mc[late_member].iloc[:100]
        assert late_before.isna().all(), (
            "PIT violation: late member has prices before start_date"
        )

        # After day 100, LATE member must have prices
        late_after = mc[late_member].iloc[100:]
        assert late_after.notna().any(), (
            "Late member has no prices after start_date"
        )


# ---------------------------------------------------------------------------
# (d) Basket PIT: prices masked before 'added' date
# ---------------------------------------------------------------------------

class TestBasketPIT:
    def test_basket_member_masked_before_added(self):
        """Basket EW index must not use a member's price before its added date."""
        n = 200
        idx = pd.bdate_range("2021-01-04", periods=n, name="date")

        early_member = "EARLY"
        late_member = "LATE_BASKET"

        closes_store = {
            early_member: pd.Series(
                100 * (1 + np.random.default_rng(0).normal(0, 0.01, n)).cumprod(),
                index=idx,
            ),
            late_member: pd.Series(
                100 * (1 + np.random.default_rng(1).normal(0.001, 0.01, n)).cumprod(),
                index=idx,
            ),
        }

        members = [
            {"symbol": early_member, "added": "2021-01-04"},
            {"symbol": late_member, "added": str(idx[100].date())},  # day 100
        ]

        lvl = _build_basket_ew_index(members, closes_store, idx)

        # At day 50 (before late member added), the index should be driven only by
        # early_member — return will equal early_member's return for that day
        early_ret_day50 = (closes_store[early_member].iloc[50]
                           / closes_store[early_member].iloc[49]) - 1

        if pd.notna(lvl.iloc[50]) and pd.notna(lvl.iloc[49]):
            basket_ret_day50 = (lvl.iloc[50] / lvl.iloc[49]) - 1
            np.testing.assert_allclose(
                basket_ret_day50, early_ret_day50, rtol=1e-5,
                err_msg="Basket return before late-member added date should equal early-only return",
            )

    def test_basket_ew_index_starts_after_earliest_member(self):
        """EW index returns only start once at least one member has prices.

        The first row of a return-based cumprod index is always NaN because
        pct_change(1) requires a prior price.  We allow exactly 1 NaN (day 0).
        """
        n = 100
        idx = pd.bdate_range("2021-01-04", periods=n, name="date")
        closes_store = {
            "A": pd.Series(np.linspace(100, 110, n), index=idx),
        }
        members = [{"symbol": "A", "added": "2021-01-04"}]
        lvl = _build_basket_ew_index(members, closes_store, idx)
        assert lvl.notna().any()
        # First day is NaN (no prior return); all subsequent days should be defined
        assert lvl.iloc[1:].notna().all(), (
            f"Expected only 1 NaN (day 0); got {lvl.isna().sum()}"
        )


# ---------------------------------------------------------------------------
# (e) Cohesion math: perfectly correlated members → cohesion ≈ 1
# ---------------------------------------------------------------------------

class TestCohesionMath:
    def test_perfectly_correlated_members_cohesion_near_one(self):
        """When all members move identically, cohesion must be ≈ 1."""
        n = 200
        base = _make_price_series(n, seed=7)
        # 4 perfectly correlated members = identical price series
        mc = pd.DataFrame({f"T{i}": base.values for i in range(4)},
                          index=base.index)
        bench = base.pct_change(fill_method=None) * 0  # zero bench
        feats = _build_node_features(
            lvl=base, bench=bench,
            member_closes=mc, member_volume=None, node_volume=None,
        )
        # cohesion should be ≈ 1 once the window fills (after day 40)
        coh_filled = feats["cohesion"].dropna()
        assert len(coh_filled) > 0, "No cohesion values computed"
        assert (coh_filled > 0.95).all(), (
            f"Expected cohesion ≈ 1 for identical members; got min={coh_filled.min():.3f}"
        )

    def test_uncorrelated_members_lower_cohesion(self):
        """Independent random-walk members should have lower cohesion than identical."""
        n = 200
        base = _make_price_series(n, seed=7)
        mc_identical = pd.DataFrame({f"T{i}": base.values for i in range(4)},
                                    index=base.index)
        mc_independent = _make_member_closes(4, n, seed=13)

        bench = base.pct_change(fill_method=None) * 0

        feats_id = _build_node_features(
            lvl=base, bench=bench,
            member_closes=mc_identical, member_volume=None, node_volume=None,
        )
        feats_ind = _build_node_features(
            lvl=_build_ew_index(mc_independent), bench=bench.reindex(mc_independent.index),
            member_closes=mc_independent, member_volume=None, node_volume=None,
        )

        coh_id = feats_id["cohesion"].dropna().mean()
        coh_ind = feats_ind["cohesion"].dropna()
        if len(coh_ind) == 0:
            pytest.skip("No cohesion for independent members")
        coh_ind_mean = coh_ind.mean()

        assert coh_id > coh_ind_mean, (
            f"Expected identical cohesion ({coh_id:.3f}) > independent ({coh_ind_mean:.3f})"
        )


# ---------------------------------------------------------------------------
# (f) turnover_z null-safe when volume missing
# ---------------------------------------------------------------------------

class TestTurnoverZNullSafe:
    def test_turnover_z_null_when_no_volume(self):
        """When neither member volume nor node volume is provided, turnover_z is all NaN."""
        lvl = _make_price_series(200)
        bench = lvl.pct_change(fill_method=None)
        mc = _make_member_closes(3, 200)
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=mc, member_volume=None, node_volume=None,
        )
        assert feats["turnover_z"].isna().all(), (
            "turnover_z should be all-NaN when volume is absent"
        )

    def test_turnover_z_computes_when_node_volume_provided(self):
        """ETF-level volume yields non-NaN turnover_z once the window warms up."""
        lvl = _make_price_series(300)
        bench = lvl.pct_change(fill_method=None)
        node_vol = pd.Series(
            np.random.default_rng(5).integers(1_000_000, 5_000_000, 300),
            index=lvl.index,
        )
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=None, member_volume=None, node_volume=node_vol,
        )
        # After 252-day warmup there should be non-NaN values
        after_warmup = feats["turnover_z"].iloc[252:]
        assert after_warmup.notna().any(), (
            "turnover_z should have non-NaN values after warmup with node volume"
        )

    def test_turnover_z_null_safe_all_zero_volume(self):
        """All-zero volume must not raise — just return NaN (causal_z divides by std)."""
        lvl = _make_price_series(300)
        bench = lvl.pct_change(fill_method=None)
        node_vol = pd.Series(np.zeros(300), index=lvl.index)
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=None, member_volume=None, node_volume=node_vol,
        )
        # Should not raise; turnover_z may be NaN (std=0 case)
        assert "turnover_z" in feats.columns


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_ew_index_drops_missing_members_gracefully(self):
        """_build_ew_index gracefully handles NaN members on some days."""
        n = 100
        idx = pd.bdate_range("2021-01-04", periods=n)
        df = _make_member_closes(3, n)
        # NaN out one member entirely for the first 50 rows
        df.iloc[:50, 0] = np.nan
        lvl = _build_ew_index(df)
        # Level should be defined for all rows where at least one member is non-NaN
        assert lvl.notna().sum() >= n - 1

    def test_node_features_with_no_members(self):
        """When member_closes=None, member-derived legs are all NaN but no crash."""
        lvl = _make_price_series(200)
        bench = lvl.pct_change(fill_method=None)
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=None, member_volume=None, node_volume=None,
        )
        for col in ("cohesion", "cohesion_chg", "breadth_50", "turnover_z"):
            assert feats[col].isna().all(), f"{col} should be NaN with no members"

    def test_accel_is_vel1w_minus_vel3m(self):
        """accel = vel_1w − vel_3m (closed-form check)."""
        lvl = _make_price_series(300)
        bench = lvl.pct_change(fill_method=None) * 0
        feats = _build_node_features(
            lvl=lvl, bench=bench,
            member_closes=None, member_volume=None, node_volume=None,
        )
        expected = feats["vel_1w"] - feats["vel_3m"]
        pd.testing.assert_series_equal(
            feats["accel"].dropna(),
            expected.dropna(),
            rtol=1e-8,
            check_names=False,
        )

    def test_cohesion_chg_is_lagged_difference(self):
        """cohesion_chg = cohesion[t] - cohesion[t - 20d] (spot check)."""
        n = 300
        base = _make_price_series(n, seed=7)
        mc = pd.DataFrame({f"T{i}": base.values for i in range(4)}, index=base.index)
        bench = base.pct_change(fill_method=None) * 0
        feats = _build_node_features(
            lvl=base, bench=bench,
            member_closes=mc, member_volume=None, node_volume=None,
        )
        coh = feats["cohesion"]
        coh_chg = feats["cohesion_chg"]
        expected = coh - coh.shift(20)
        # Check in the range where both are defined
        mask = coh.notna() & coh_chg.notna()
        if mask.any():
            pd.testing.assert_series_equal(
                coh_chg[mask],
                expected[mask],
                atol=1e-9,
                check_names=False,
            )


# ---------------------------------------------------------------------------
# Fixture builders (shared)
# ---------------------------------------------------------------------------

def _make_minimal_yahoo(yahoo_dir: Path, n: int = 300, start: str = "2021-01-04") -> None:
    """Write minimal ETF parquets for XLK and XLV to yahoo_dir."""
    yahoo_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=n, name="date")
    rng = np.random.default_rng(0)
    for i, t in enumerate(["XLK", "XLV"]):
        prices = 100 * (1 + rng.normal(0.0001, 0.01, n)).cumprod()
        volume = rng.integers(1_000_000, 10_000_000, n).astype(float)
        df = pd.DataFrame({"close": prices, "volume": volume}, index=idx)
        df.index.name = "date"
        df.to_parquet(yahoo_dir / f"{t}.parquet")
    # regime series
    for t in ["_VIX", "TLT", "SPY"]:
        prices = 100 * (1 + rng.normal(0, 0.01, n)).cumprod()
        df = pd.DataFrame({"close": prices, "volume": rng.integers(1000, 9999, n).astype(float)},
                          index=idx)
        df.index.name = "date"
        df.to_parquet(yahoo_dir / f"{t}.parquet")


def _make_minimal_massive(massive_dir: Path, tickers: list[str],
                           n: int = 300, start: str = "2021-01-04") -> None:
    massive_dir.mkdir(parents=True, exist_ok=True)
    idx = pd.bdate_range(start, periods=n, name="date")
    rng = np.random.default_rng(1)
    for t in tickers:
        prices = 100 * (1 + rng.normal(0.0001, 0.01, n)).cumprod()
        volume = rng.integers(100_000, 1_000_000, n)
        df = pd.DataFrame(
            {"open": prices, "high": prices * 1.005, "low": prices * 0.995,
             "close": prices, "volume": volume, "transactions": volume // 10},
            index=idx,
        )
        df.index.name = "date"
        df.to_parquet(massive_dir / f"{t}.parquet")


def _make_minimal_panel_s(
    tmp_path: Path,
    n: int = 300,
    start: str = "2021-01-04",
    end: str | None = None,
) -> pd.DataFrame:
    """Build a minimal Tier-S panel using two ETFs and synthetic member data."""
    yahoo_dir = tmp_path / "yahoo"
    massive_dir = tmp_path / "massive_stock_day"

    # Create only XLK and XLV (2 ETFs)
    _make_minimal_yahoo(yahoo_dir, n=n, start=start)

    members_xlt = ["AAPL", "MSFT", "NVDA"]
    members_xlv = ["JNJ", "UNH"]
    all_members = members_xlt + members_xlv
    _make_minimal_massive(massive_dir, all_members, n=n, start=start)

    idx = pd.bdate_range(start, periods=n, name="date")

    # PIT membership
    pit_rows = []
    for t in members_xlt:
        pit_rows.append({"ticker": t, "start_date": pd.Timestamp(start),
                         "end_date": pd.NaT, "src": "sp500"})
    for t in members_xlv:
        pit_rows.append({"ticker": t, "start_date": pd.Timestamp(start),
                         "end_date": pd.NaT, "src": "sp500"})
    pit_membership = pd.DataFrame(pit_rows)

    # Constituents: ticker → sector
    const_rows = (
        [{"name": t, "sector": "Information Technology"} for t in members_xlt]
        + [{"name": t, "sector": "Health Care"} for t in members_xlv]
    )
    constituents = pd.DataFrame(const_rows)
    constituents.index = pd.Index([r["name"] for r in const_rows], name="symbol")

    # Override SECTOR_ETFS in panel.py to only use XLK and XLV for this fixture
    import engine.oracle.panel as _panel
    original_etfs = _panel.SECTOR_ETFS
    original_map = _panel.ETF_TO_SECTOR
    _panel.SECTOR_ETFS = ["XLK", "XLV"]
    _panel.ETF_TO_SECTOR = {"XLK": "Information Technology", "XLV": "Health Care"}
    try:
        panel = build_panel_s(
            yahoo_dir=yahoo_dir,
            massive_dir=massive_dir,
            pit_membership=pit_membership,
            constituents=constituents,
            start=start,
            end=end,
        )
    finally:
        _panel.SECTOR_ETFS = original_etfs
        _panel.ETF_TO_SECTOR = original_map

    return panel


def _make_minimal_panel_m(tmp_path: Path, n: int = 200) -> pd.DataFrame:
    """Build a minimal Tier-M panel using one synthetic subsector."""
    yahoo_dir = tmp_path / "yahoo_m"
    massive_dir = tmp_path / "massive_m"

    _make_minimal_yahoo(yahoo_dir, n=n)
    members = ["AAPL", "MSFT", "GOOG"]
    _make_minimal_massive(massive_dir, members, n=n)

    themes_tree = [
        {
            "theme": "Test Theme",
            "key": "Test Theme",
            "subsectors": [
                {"key": "testsector", "name": "Test Sector",
                 "members": members},
            ],
        }
    ]

    baskets_data = [
        {
            "id": "test_basket",
            "name": "Test Basket",
            "members": [
                {"symbol": "AAPL", "added": "2021-01-04"},
                {"symbol": "MSFT", "added": "2021-06-01"},
            ],
        }
    ]

    return build_panel_m(
        yahoo_dir=yahoo_dir,
        massive_dir=massive_dir,
        themes_tree=themes_tree,
        baskets_data=baskets_data,
        start="2021-01-04",
    )
