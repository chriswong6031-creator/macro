"""Stock Identity W1 — the fingerprint's two structural laws.

1. **Block purity.** The metric block — the only block a future distance or map may
   read — carries no gap-family member and no label-like feature. If a sector, cap
   bucket, or plane id ever leaked into it, a "behavioral neighborhood" could
   partition by label before it partitions by behavior and nobody would see it in
   the output.
2. **Causality.** Every value at a date is a function of that date's trailing data
   only. Truncation invariance is the executable form of that claim: dropping every
   row after ``asof`` must not move a single number.

Synthetic frames only — no network, no committed-artifact dependency, no plotting.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.stock_identity import fingerprint as fp

ROOT = Path(__file__).resolve().parents[1]
SPEC_JSON = ROOT / "data" / "stock_identity" / "fingerprints" / "fingerprint_spec.json"

#: Substrings that would make a metric-block feature a LABEL rather than a measurement.
LABEL_LIKE = (
    "sector", "industry", "cap_bucket", "plane", "basket", "venue", "market_cap",
)


def _frame(n: int = 1500, seed: int = 7, with_open: bool = True) -> pd.DataFrame:
    """A synthetic OHLCV frame with enough history to light up every window."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2016-01-04", periods=n, name="Date")
    steps = rng.normal(0.0004, 0.018, size=n)
    # a couple of deliberate regime shifts so drawdown/cyclicality features are not flat
    steps[400:520] -= 0.006
    steps[900:1000] += 0.005
    close = 40.0 * np.exp(np.cumsum(steps))
    spread = np.abs(rng.normal(0.012, 0.006, size=n)) * close
    df = pd.DataFrame(
        {
            "close": close,
            "high": close + spread,
            "low": np.maximum(close - spread, 0.01),
            "volume": rng.integers(200_000, 4_000_000, size=n).astype(float),
        },
        index=idx,
    )
    if with_open:
        df.insert(0, "open", close * (1.0 + rng.normal(0, 0.004, size=n)))
    return df


class TestBlockPurity:
    def test_metric_block_holds_no_gap_family_member(self):
        # The gap family is structurally unavailable on the open-less curated plane, so
        # the plane-availability law excludes it from the metric block universe-wide
        # rather than masking it per name.
        for f in fp.METRIC_FEATURES:
            assert f["family"] not in fp.PLANE_GATED_FAMILIES, f["name"]
            assert "gap" not in f["name"], f["name"]

    def test_metric_block_holds_no_label_like_feature(self):
        for f in fp.METRIC_FEATURES:
            for token in LABEL_LIKE:
                assert token not in f["name"], f"{f['name']} carries label token {token!r}"

    def test_label_like_features_live_in_the_diagnostic_block(self):
        diag = {f["name"] for f in fp.DIAGNOSTIC_FEATURES}
        for expected in ("d_sector", "d_industry", "d_cap_bucket", "d_price_plane_id"):
            assert expected in diag
        for f in fp.DIAGNOSTIC_FEATURES:
            assert f["block"] == "diagnostic"

    def test_every_feature_declares_exactly_one_block(self):
        names = [f["name"] for f in fp.ALL_FEATURES]
        assert len(names) == len(set(names)), "duplicate feature name"
        assert set(fp.METRIC_NAMES).isdisjoint(set(fp.DIAGNOSTIC_NAMES))
        for f in fp.ALL_FEATURES:
            assert f["block"] in ("metric", "diagnostic")

    def test_metric_membership_is_not_plane_conditional(self):
        # A plane-conditional metric block is exactly what would let neighborhoods
        # discover data planes and report them as behavior.
        for plane in ("stocks_tr_v1", "baskets_ohlcv_v1", "stock_identity_ohlcv_v1"):
            assert fp.metric_names_for_plane(plane) == fp.METRIC_NAMES

    def test_every_family_carries_at_least_two_windows(self):
        # The masterplan's ">=2 window lengths" applied at family level, which is the
        # reading recorded in the spec as `window_law_reading`.
        by_family: dict[str, set[int]] = {}
        for f in fp.METRIC_FEATURES:
            by_family.setdefault(f["family"], set()).update(f["windows"])
        for family, windows in by_family.items():
            if family == "F3":
                continue  # catalog-derived; windowless by construction
            assert len(windows) >= 2, f"{family} has windows {windows}"


class TestSpecHash:
    def test_spec_hash_is_deterministic(self):
        assert fp.spec_hash() == fp.spec_hash()
        assert fp.spec_hash() == fp.spec_hash(fp.spec())

    def test_spec_hash_moves_when_the_enumeration_moves(self):
        s = fp.spec()
        s["features"] = s["features"][:-1]
        assert fp.spec_hash(s) != fp.spec_hash()

    def test_committed_spec_json_matches_the_code(self):
        if not SPEC_JSON.exists():
            pytest.skip("fingerprint_spec.json not present in this checkout")
        payload = json.loads(SPEC_JSON.read_text(encoding="utf-8"))
        recorded = payload.pop("fingerprint_spec_hash")
        payload.pop("authority", None)
        assert fp.spec_hash(payload) == recorded
        assert recorded == fp.spec_hash()


class TestTruncationInvariance:
    """Value at t is unchanged when future rows are dropped — on every feature."""

    @pytest.mark.parametrize("with_open", [True, False])
    @pytest.mark.parametrize("cut", [200, 60])
    def test_raw_values_are_identical_when_the_future_is_removed(self, with_open, cut):
        df = _frame(with_open=with_open)
        plane = "baskets_ohlcv_v1" if with_open else "stocks_tr_v1"
        asof = df.index[-cut]
        full = fp.compute_raw(df, plane_id=plane, asof=asof, factor_returns=None)
        truncated = fp.compute_raw(
            df.loc[df.index <= asof], plane_id=plane, asof=asof, factor_returns=None
        )
        assert set(full) == set(truncated)
        for key, a in full.items():
            b = truncated[key]
            if isinstance(a, float) and isinstance(b, float):
                assert a == pytest.approx(b, rel=1e-12, abs=1e-12), key
            else:
                assert a == b, key

    def test_factor_conditioned_features_are_also_truncation_invariant(self):
        df = _frame()
        rng = np.random.default_rng(11)
        factor = pd.Series(rng.normal(0.0003, 0.01, len(df)), index=df.index, name="UNIV_EW")
        asof = df.index[-150]
        a = fp.compute_raw(df, plane_id="baskets_ohlcv_v1", asof=asof, factor_returns=factor)
        b = fp.compute_raw(
            df.loc[df.index <= asof], plane_id="baskets_ohlcv_v1", asof=asof,
            factor_returns=factor.loc[factor.index <= asof],
        )
        for key in ("f9_beta_univ_ew_252", "f9_idio_share_252", "f9_beta_univ_ew_756"):
            assert a[key] == pytest.approx(b[key], rel=1e-12), key

    def test_short_history_is_coverage_masked_not_an_error(self):
        # The IPO stressor in the pilot exists to exercise exactly this path.
        df = _frame(n=120)
        raw = fp.compute_raw(df, plane_id="baskets_ohlcv_v1", asof=df.index[-1])
        assert raw["_n_sessions"] == 120
        assert all(raw[name] is None for name in fp.METRIC_NAMES)
        mask = fp.coverage_mask(raw)
        assert not any(mask[name] for name in fp.METRIC_NAMES)


class TestCrossSectionAndInstability:
    def test_percentiles_keep_nulls_null(self):
        vals = pd.DataFrame(
            {"f1_kaufman_er_63": [0.1, 0.5, None, 0.9]},
            index=["A", "B", "C", "D"],
        )
        pct = fp.cross_sectional_percentiles(vals, ["f1_kaufman_er_63"])
        assert pd.isna(pct.loc["C", "f1_kaufman_er_63"])
        assert pct.loc["D", "f1_kaufman_er_63"] > pct.loc["A", "f1_kaufman_er_63"]

    def test_adjacent_window_quartile_jump_flags_both_members(self):
        pct = pd.DataFrame(
            {"f1_kaufman_er_63": [5.0, 50.0], "f1_kaufman_er_126": [95.0, 55.0]},
            index=["jumper", "stable"],
        )
        flags = fp.unstable_flags(pct)
        assert bool(flags.loc["jumper", "f1_kaufman_er_63"]) is True
        assert bool(flags.loc["jumper", "f1_kaufman_er_126"]) is True
        assert bool(flags.loc["stable", "f1_kaufman_er_63"]) is False

    def test_univ_ew_is_the_cross_name_equal_weight_mean(self):
        idx = pd.bdate_range("2024-01-01", periods=5)
        rets = {
            "A": pd.Series([0.01, 0.02, np.nan, 0.0, -0.01], index=idx),
            "B": pd.Series([0.03, 0.00, 0.05, 0.02, -0.03], index=idx),
        }
        fac = fp.universe_equal_weight_factor(rets)
        assert fac.iloc[0] == pytest.approx(0.02)
        assert fac.iloc[2] == pytest.approx(0.05)  # skipna: the present name carries it
        assert fac.name == "UNIV_EW"
