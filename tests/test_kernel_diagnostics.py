"""Hermetic unit tests for engine.neuralweb.decay and engine.neuralweb.lagging.

All tests use synthetic fixtures.  No real market data is loaded.

COVERAGE:
  - decay: horizon-curve extraction from kernel_estimates fixture
  - decay: recency_trend window math (hand-computed fixture)
  - decay: staleness days_since_last_fire
  - decay: armed propagation from estimates
  - decay: fail-open on missing estimates/index
  - decay: envelope stamp keys present
  - decay: determinism (same input → same output)
  - lagging: hostile-regime join (Q3/Q4, recession, inflation_shock flags)
  - lagging: missing-date behavior (fail-open → False)
  - lagging: breadth-unconfirmed median logic
  - lagging: repeat_fire counting (>=3 prior fires in 21d)
  - lagging: fail-open on missing regime/breadth stores
  - lagging: envelope stamp keys present
  - lagging: determinism
"""
from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.neuralweb.decay import (
    RECENCY_WINDOWS,
    _window_stats,
    build_families,
)
from engine.neuralweb.lagging import (
    HOSTILE_QUAD_SET,
    REPEAT_FIRE_MIN_COUNT,
    REPEAT_FIRE_WINDOW_DAYS,
    _breadth_lookup,
    _hostile_lookup,
    build_lagging,
)
from engine.neuralweb.envelope import ENVELOPE_KEYS

# ---------------------------------------------------------------------------
# Minimal synthetic registry for envelope stamps
# ---------------------------------------------------------------------------
_REG = {
    "meta": {
        "schema_version": 1,
        "tier_vocabulary": [
            "display", "shadow", "confirmer", "scored", "infrastructure",
        ],
    },
    "artifacts": {
        "kernel-families": {
            "producer": "engine/neuralweb/decay.py",
            "tier": "infrastructure",
        },
        "lagging-signals": {
            "producer": "engine/neuralweb/lagging.py",
            "tier": "infrastructure",
        },
    },
}

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Test root fixture builder
# ---------------------------------------------------------------------------

def _make_root(
    tmp_path: Path,
    estimates_rows: list[dict] | None = None,
    spine_rows: list[dict] | None = None,
    regime_rows: list[dict] | None = None,
    breadth_rows: list[dict] | None = None,
) -> Path:
    """Write minimal parquet/JSON fixtures into tmp_path, return root path."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True, exist_ok=True)

    # kernel_estimates.parquet
    if estimates_rows is not None:
        est_df = pd.DataFrame(estimates_rows)
        est_df.to_parquet(nw_dir / "kernel_estimates.parquet", index=False)

    # spine_index.parquet
    if spine_rows is not None:
        spine_df = pd.DataFrame(spine_rows)
        spine_df.to_parquet(nw_dir / "spine_index.parquet", index=False)

    # regime_history.parquet (DatetimeIndex, columns include quad/recession/inflation_shock)
    if regime_rows is not None:
        regime_df = pd.DataFrame(regime_rows)
        if "date" in regime_df.columns:
            regime_df.index = pd.to_datetime(regime_df["date"])
            regime_df = regime_df.drop(columns=["date"])
        regime_dir = tmp_path / "data" / "regime"
        regime_dir.mkdir(parents=True, exist_ok=True)
        regime_df.to_parquet(regime_dir / "regime_history.parquet")

    # breadth.parquet (DatetimeIndex)
    if breadth_rows is not None:
        br_df = pd.DataFrame(breadth_rows)
        if "date" in br_df.columns:
            br_df.index = pd.to_datetime(br_df["date"])
            br_df = br_df.drop(columns=["date"])
        breadth_dir = tmp_path / "data" / "breadth"
        breadth_dir.mkdir(parents=True, exist_ok=True)
        br_df.to_parquet(breadth_dir / "breadth.parquet")

    return tmp_path


# ---------------------------------------------------------------------------
# decay: horizon_curve extraction
# ---------------------------------------------------------------------------

def _minimal_estimates(engine: str = "test_engine") -> list[dict]:
    """Minimal kernel_estimates rows for a single engine (post-fix schema:
    includes shrunken_ic_sd, armed_reason, regime_coverage)."""
    rows = []
    for h in (5, 10, 21):
        rows.append({
            "engine": engine, "regime": "__all__", "horizon": h,
            "n_raw": 10, "n_eff": 10, "mean_raw": 0.01 * h, "shrunken_ic": 0.005 * h,
            "shrunken_ic_sd": 0.001 * h,
            "reliability": 0.5, "wilson_ci_low": None, "armed": True,
            "armed_reason": "armed: pooled beat equal on held-out tail",
            "regime_coverage": 0.0,
            "fill_basis_mode": "next_bar", "date_first": "2026-01-01", "date_last": "2026-06-30",
        })
        rows.append({
            "engine": engine, "regime": "__unstamped__", "horizon": h,
            "n_raw": 10, "n_eff": 10, "mean_raw": 0.01 * h, "shrunken_ic": 0.005 * h,
            "shrunken_ic_sd": 0.001 * h,
            "reliability": 0.5, "wilson_ci_low": None, "armed": True,
            "armed_reason": "armed: pooled beat equal on held-out tail",
            "regime_coverage": 0.0,
            "fill_basis_mode": "next_bar", "date_first": "2026-01-01", "date_last": "2026-06-30",
        })
    return rows


def _legacy_estimates(engine: str = "legacy_engine") -> list[dict]:
    """Pre-fix kernel_estimates rows (NO shrunken_ic_sd / armed_reason /
    regime_coverage columns) — decay must fail-open to None on these."""
    rows = []
    for h in (5, 10):
        rows.append({
            "engine": engine, "regime": "__all__", "horizon": h,
            "n_raw": 10, "n_eff": 10, "mean_raw": 0.01 * h, "shrunken_ic": 0.005 * h,
            "reliability": 0.5, "wilson_ci_low": None, "armed": False,
            "fill_basis_mode": "next_bar", "date_first": "2026-01-01", "date_last": "2026-06-30",
        })
    return rows


def _minimal_spine(
    engine: str = "test_engine",
    as_of: str = "2026-06-30",
    n: int = 5,
    outcome_excess: float = 0.02,
) -> list[dict]:
    """Minimal spine rows for recency_trend testing."""
    cols = {c: None for c in [
        "signal_id", "engine", "family", "ledger", "as_of", "symbol",
        "scope_type", "universe", "horizon", "direction", "size_binding",
        "fill_basis", "score", "outcome_excess", "outcome_graded", "graded_at",
        "terminal_state_clean15_126", "terminal_state_clean8_21",
        "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63", "fwd_mfe_126",
        "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
        "risk_radar_state", "vector_asof", "species_id", "archetype",
    ]}
    rows = []
    for i in range(n):
        r = dict(cols)
        r.update({
            "signal_id": f"{engine}:{as_of}:SYM{i}:5",
            "engine": engine,
            "ledger": "test",
            "as_of": as_of,
            "symbol": f"SYM{i}",
            "scope_type": "entity",
            "horizon": 5,
            "direction": 1,
            "outcome_excess": outcome_excess,
            "outcome_graded": True,
        })
        rows.append(r)
    return rows


class TestDecayHorizonCurve:
    def test_horizon_curve_all_horizons_present(self, tmp_path):
        """horizon_curve contains __all__ shrunken_ic for each horizon present."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        result = build_families(root)
        fam = result["families"]["test_engine"]
        hc = fam["horizon_curve"]
        assert "5" in hc and "10" in hc and "21" in hc

    def test_horizon_curve_values_from_estimates(self, tmp_path):
        """horizon_curve values match the __all__ shrunken_ic in estimates."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        result = build_families(root)
        hc = result["families"]["test_engine"]["horizon_curve"]
        # shrunken_ic = 0.005 * h for each horizon
        assert abs(hc["5"] - 0.025) < 1e-9
        assert abs(hc["10"] - 0.05) < 1e-9
        assert abs(hc["21"] - 0.105) < 1e-9

    def test_unstamped_cells_not_in_horizon_curve(self, tmp_path):
        """__unstamped__ cells do not appear in horizon_curve (only __all__)."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        result = build_families(root)
        hc = result["families"]["test_engine"]["horizon_curve"]
        # horizon_curve should have exactly the __all__ horizons, not doubled
        # The keys are string horizon numbers; no regime labels should appear
        for key in hc:
            assert key.isdigit(), f"unexpected non-numeric key in horizon_curve: {key!r}"

    def test_missing_estimates_returns_empty_families(self, tmp_path):
        """With no kernel_estimates.parquet, families is empty (fail-open)."""
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        result = build_families(tmp_path)
        assert result["families"] == {}

    def test_generated_from_key_present(self, tmp_path):
        """generated_from is set (sha256 hash or 'sha256:absent')."""
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        result = build_families(tmp_path)
        assert result["generated_from"].startswith("sha256:")


class TestDecayStaleness:
    def test_staleness_date_last_from_estimates(self, tmp_path):
        """staleness.date_last is the max date_last across all cells for the engine."""
        rows = _minimal_estimates()
        # Set different date_last values
        rows[0]["date_last"] = "2026-06-30"
        rows[2]["date_last"] = "2026-06-15"
        root = _make_root(tmp_path, estimates_rows=rows)
        result = build_families(root)
        stal = result["families"]["test_engine"]["staleness"]
        assert stal["date_last"] == "2026-06-30"

    def test_staleness_days_since_is_int(self, tmp_path):
        """days_since_last_fire is a non-negative integer."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        result = build_families(root)
        days = result["families"]["test_engine"]["staleness"]["days_since_last_fire"]
        assert isinstance(days, int)
        assert days >= 0


class TestDecayArmed:
    def test_armed_propagated_from_estimates(self, tmp_path):
        """armed value from estimates is propagated to the family output."""
        rows = _minimal_estimates()
        for r in rows:
            r["armed"] = False
        root = _make_root(tmp_path, estimates_rows=rows)
        result = build_families(root)
        assert result["families"]["test_engine"]["armed"] is False

    def test_armed_true_propagated(self, tmp_path):
        rows = _minimal_estimates()
        for r in rows:
            r["armed"] = True
        root = _make_root(tmp_path, estimates_rows=rows)
        result = build_families(root)
        assert result["families"]["test_engine"]["armed"] is True


class TestDecayRecencyTrend:
    def test_all_windows_present(self, tmp_path):
        """recency_trend contains '252d', '756d', 'all' keys."""
        root = _make_root(
            tmp_path,
            estimates_rows=_minimal_estimates(),
            spine_rows=_minimal_spine(as_of="2026-06-30", n=5),
        )
        result = build_families(root)
        rt = result["families"]["test_engine"]["recency_trend"]
        for key in ("252d", "756d", "all"):
            assert key in rt, f"missing window key: {key}"

    def test_all_window_stats_keys(self, tmp_path):
        """Each window dict has n_eff, mean, wilson_ci_low keys."""
        root = _make_root(
            tmp_path,
            estimates_rows=_minimal_estimates(),
            spine_rows=_minimal_spine(as_of="2026-06-30", n=5),
        )
        result = build_families(root)
        rt = result["families"]["test_engine"]["recency_trend"]
        for key in ("252d", "756d", "all"):
            w = rt[key]
            assert "n_eff" in w
            assert "mean" in w
            assert "wilson_ci_low" in w

    def test_window_stats_n_eff_matches_row_count(self):
        """_window_stats n_eff counts distinct (symbol, as_of) pairs."""
        # 3 rows: 2 unique (symbol, as_of) after dedup
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-30", "outcome_excess": 0.05, "direction": 1},
            {"symbol": "A", "as_of": "2026-06-30", "outcome_excess": 0.05, "direction": 1},  # dup
            {"symbol": "B", "as_of": "2026-06-30", "outcome_excess": 0.10, "direction": 1},
        ])
        stats = _window_stats("eng", rows, None, "2026-07-04")
        assert stats["n_eff"] == 2  # deduped

    def test_window_stats_mean_hand_computed(self):
        """_window_stats mean equals hand-computed mean of signed excess."""
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-01", "outcome_excess": 0.04, "direction": 1},
            {"symbol": "B", "as_of": "2026-06-02", "outcome_excess": 0.06, "direction": 1},
        ])
        # Expected: mean = (0.04 + 0.06) / 2 = 0.05
        stats = _window_stats("eng", rows, None, "2026-07-04")
        assert stats["n_eff"] == 2
        assert abs(stats["mean"] - 0.05) < 1e-9

    def test_window_stats_direction_aware(self):
        """Direction -1 inverts outcome sign (short that avoids loss = positive credit)."""
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-01", "outcome_excess": -0.04, "direction": -1},
        ])
        # direction=-1: signed = (-0.04) * sign(-1) = (-0.04)*(-1) = +0.04
        stats = _window_stats("eng", rows, None, "2026-07-04")
        assert stats["n_eff"] == 1
        assert abs(stats["mean"] - 0.04) < 1e-9

    def test_window_filters_old_rows(self):
        """252d window excludes rows outside the trailing 252 calendar days."""
        today = "2026-07-04"
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-30", "outcome_excess": 0.10, "direction": 1},  # recent
            {"symbol": "B", "as_of": "2025-01-01", "outcome_excess": 0.05, "direction": 1},  # old
        ])
        stats_252 = _window_stats("eng", rows, 252, today)
        # Only the recent row should be in the 252d window
        assert stats_252["n_eff"] == 1

    def test_window_all_includes_old_rows(self):
        """'all' window includes all rows regardless of date."""
        today = "2026-07-04"
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-30", "outcome_excess": 0.10, "direction": 1},
            {"symbol": "B", "as_of": "2020-01-01", "outcome_excess": 0.05, "direction": 1},
        ])
        stats_all = _window_stats("eng", rows, None, today)
        assert stats_all["n_eff"] == 2

    def test_window_stats_empty_returns_nulls(self):
        """Empty input returns n_eff=0, mean=None, wilson_ci_low=None."""
        stats = _window_stats("eng", pd.DataFrame(), None, "2026-07-04")
        assert stats["n_eff"] == 0
        assert stats["mean"] is None
        assert stats["wilson_ci_low"] is None


class TestDecayEnvelope:
    def test_envelope_keys_present_after_write(self, tmp_path, monkeypatch):
        """write_families stamps all five envelope keys as siblings."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        # Inject synthetic registry so tests do not depend on synapse.yml state
        import engine.neuralweb.envelope as _env_mod
        monkeypatch.setattr(_env_mod, "load_registry", lambda: _REG)
        from engine.neuralweb.decay import write_families
        write_families(root)
        out = json.loads(
            (tmp_path / "data" / "neuralweb" / "kernel_families.json").read_text()
        )
        for k in ENVELOPE_KEYS:
            assert k in out, f"envelope key {k!r} missing"
        # families should still be a sibling key (not wrapped)
        assert "families" in out

    def test_determinism(self, tmp_path):
        """Same input produces same generated_from hash."""
        root = _make_root(
            tmp_path,
            estimates_rows=_minimal_estimates(),
            spine_rows=_minimal_spine(),
        )
        r1 = build_families(root)
        r2 = build_families(root)
        assert r1["generated_from"] == r2["generated_from"]
        assert r1["families"] == r2["families"]


class TestDecayHorizonDetail:
    """horizon_detail — additive per-horizon {ic, n_eff, sd} sibling of horizon_curve."""

    def test_horizon_detail_shape(self, tmp_path):
        """horizon_detail carries {ic, n_eff, sd} per horizon; ic matches horizon_curve."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        result = build_families(root)
        fam = result["families"]["test_engine"]
        hc = fam["horizon_curve"]
        hd = fam["horizon_detail"]
        assert set(hd.keys()) == set(hc.keys()), "detail horizons must mirror curve horizons"
        for h_key, point in hd.items():
            assert set(point.keys()) == {"ic", "n_eff", "sd"}
            assert point["ic"] == hc[h_key], f"h={h_key}: detail ic != curve ic"
            assert point["n_eff"] == 10
            assert abs(point["sd"] - 0.001 * int(h_key)) < 1e-9

    def test_horizon_curve_shape_unchanged(self, tmp_path):
        """Back-compat: horizon_curve stays flat {h: ic_float} (template reads it)."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        hc = build_families(root)["families"]["test_engine"]["horizon_curve"]
        for v in hc.values():
            assert v is None or isinstance(v, float), (
                f"horizon_curve value must stay a bare float|None, got {type(v)}"
            )

    def test_horizon_detail_sd_none_on_legacy_parquet(self, tmp_path):
        """Pre-fix parquet (no shrunken_ic_sd column) → sd=None, no crash."""
        root = _make_root(tmp_path, estimates_rows=_legacy_estimates())
        fam = build_families(root)["families"]["legacy_engine"]
        for point in fam["horizon_detail"].values():
            assert point["sd"] is None
            assert point["n_eff"] == 10


class TestDecayFamilyMetadata:
    """outcome_unit + regime_coverage + armed_reason on the family record."""

    def test_outcome_unit_track_record_magnitude(self, tmp_path):
        """track_record outcome_excess is a favorable-excursion magnitude."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates("track_record"))
        fam = build_families(root)["families"]["track_record"]
        assert fam["outcome_unit"] == "magnitude_nonneg"

    def test_outcome_unit_default_signed_excess(self, tmp_path):
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates("radar"))
        fam = build_families(root)["families"]["radar"]
        assert fam["outcome_unit"] == "signed_excess"

    def test_regime_coverage_propagated(self, tmp_path):
        rows = _minimal_estimates()
        for r in rows:
            r["regime_coverage"] = 0.25
        root = _make_root(tmp_path, estimates_rows=rows)
        fam = build_families(root)["families"]["test_engine"]
        assert abs(fam["regime_coverage"] - 0.25) < 1e-9

    def test_regime_coverage_none_on_legacy_parquet(self, tmp_path):
        root = _make_root(tmp_path, estimates_rows=_legacy_estimates())
        fam = build_families(root)["families"]["legacy_engine"]
        assert fam["regime_coverage"] is None

    def test_armed_reason_propagated(self, tmp_path):
        """The arming reason must reach kernel_families.json (reason-drop fix)."""
        root = _make_root(tmp_path, estimates_rows=_minimal_estimates())
        fam = build_families(root)["families"]["test_engine"]
        assert fam["armed_reason"] == "armed: pooled beat equal on held-out tail"
        assert fam["armed_reason"].strip() != "", "armed_reason must never be empty"

    def test_armed_reason_none_on_legacy_parquet(self, tmp_path):
        root = _make_root(tmp_path, estimates_rows=_legacy_estimates())
        fam = build_families(root)["families"]["legacy_engine"]
        assert fam["armed_reason"] is None


class TestDecayShortRecencyWindows:
    """21d/63d trailing windows added to recency_trend."""

    def test_short_windows_present(self, tmp_path):
        root = _make_root(
            tmp_path,
            estimates_rows=_minimal_estimates(),
            spine_rows=_minimal_spine(as_of="2026-06-30", n=5),
        )
        rt = build_families(root)["families"]["test_engine"]["recency_trend"]
        for key in ("21d", "63d", "252d", "756d", "all"):
            assert key in rt, f"missing window key: {key}"
            assert set(rt[key].keys()) == {"n_eff", "mean", "wilson_ci_low"}

    def test_21d_window_filters(self):
        """21d window keeps only fires within the trailing 21 calendar days."""
        today = "2026-07-04"
        rows = pd.DataFrame([
            {"symbol": "A", "as_of": "2026-06-30", "outcome_excess": 0.10, "direction": 1},
            # 55 calendar days back: outside 21d, inside 63d
            {"symbol": "B", "as_of": "2026-05-10", "outcome_excess": 0.05, "direction": 1},
        ])
        stats_21 = _window_stats("eng", rows, 21, today)
        assert stats_21["n_eff"] == 1
        stats_63 = _window_stats("eng", rows, 63, today)
        assert stats_63["n_eff"] == 2


# ---------------------------------------------------------------------------
# lagging: hostile-regime join
# ---------------------------------------------------------------------------

def _make_regime_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df.index = pd.to_datetime(df["date"])
        df = df.drop(columns=["date"])
    return df


class TestLaggingHostileRegime:
    def test_q3_is_hostile(self):
        """Q3 (Stagflation) marks the date as hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q3", "recession": False, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is True

    def test_q4_is_hostile(self):
        """Q4 (Growth-scare) marks the date as hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q4", "recession": False, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is True

    def test_q1_is_not_hostile(self):
        """Q1 (Goldilocks) does not mark the date as hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q1", "recession": False, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is False

    def test_q2_is_not_hostile(self):
        """Q2 (Reflation) does not mark the date as hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q2", "recession": False, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is False

    def test_recession_flag_overrides(self):
        """Q1 with recession=True is still hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q1", "recession": True, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is True

    def test_inflation_shock_flag_overrides(self):
        """Q2 with inflation_shock=True is still hostile."""
        df = _make_regime_df([
            {"date": "2026-06-30", "quad": "Q2", "recession": False, "inflation_shock": True},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is True

    def test_missing_date_returns_false(self):
        """A fire date not in the regime store returns False (fail-open)."""
        df = _make_regime_df([
            {"date": "2026-06-28", "quad": "Q4", "recession": False, "inflation_shock": False},
        ])
        lookup = _hostile_lookup(df)
        assert lookup.get("2026-06-30") is None  # key absent → caller uses .get(d, False)

    def test_empty_regime_df_returns_empty(self):
        """Empty regime store returns empty lookup."""
        lookup = _hostile_lookup(pd.DataFrame())
        assert lookup == {}

    def test_hostile_quad_set_correct(self):
        """HOSTILE_QUAD_SET contains exactly Q3 and Q4."""
        assert HOSTILE_QUAD_SET == frozenset({"Q3", "Q4"})


class TestLaggingBreadthUnconfirmed:
    def test_below_median_is_unconfirmed(self):
        """pct_above_50 below trailing-63d median → unconfirmed."""
        # 63 days of high breadth, then a low reading on fire date
        dates = pd.date_range("2026-04-01", periods=64)
        high_vals = [60.0] * 63 + [40.0]  # last one is the fire date value
        br_df = pd.DataFrame({"pct_above_50": high_vals}, index=dates)
        fire_date = str(dates[-1])[:10]
        lookup = _breadth_lookup(br_df, [fire_date])
        # Median of 63 values = 60.0; fire-date value = 40.0 < 60.0 → unconfirmed
        assert lookup[fire_date] is True

    def test_above_median_is_confirmed(self):
        """pct_above_50 above trailing-63d median → confirmed (not unconfirmed)."""
        dates = pd.date_range("2026-04-01", periods=64)
        low_vals = [40.0] * 63 + [60.0]
        br_df = pd.DataFrame({"pct_above_50": low_vals}, index=dates)
        fire_date = str(dates[-1])[:10]
        lookup = _breadth_lookup(br_df, [fire_date])
        assert lookup[fire_date] is False

    def test_equal_median_is_confirmed(self):
        """pct_above_50 equal to median is NOT below → confirmed."""
        dates = pd.date_range("2026-04-01", periods=64)
        vals = [50.0] * 64
        br_df = pd.DataFrame({"pct_above_50": vals}, index=dates)
        fire_date = str(dates[-1])[:10]
        lookup = _breadth_lookup(br_df, [fire_date])
        assert lookup[fire_date] is False  # not strictly below

    def test_missing_fire_date_returns_false(self):
        """Fire date absent from breadth store returns False (fail-open)."""
        br_df = pd.DataFrame(
            {"pct_above_50": [55.0, 60.0]},
            index=pd.to_datetime(["2026-06-01", "2026-06-02"])
        )
        lookup = _breadth_lookup(br_df, ["2026-06-30"])
        assert lookup["2026-06-30"] is False

    def test_no_window_history_returns_false(self):
        """Only the fire-date row (no prior history) → fail-open False."""
        br_df = pd.DataFrame(
            {"pct_above_50": [40.0]},
            index=pd.to_datetime(["2026-06-30"])
        )
        lookup = _breadth_lookup(br_df, ["2026-06-30"])
        assert lookup["2026-06-30"] is False

    def test_empty_breadth_returns_false(self):
        """Empty breadth store returns False for all dates."""
        lookup = _breadth_lookup(pd.DataFrame(), ["2026-06-30"])
        assert lookup["2026-06-30"] is False


class TestLaggingRepeatFire:
    def test_repeat_fire_flag_set_when_enough_prior_fires(self, tmp_path):
        """repeat_fire flag appears when (engine, symbol) fired >=3 times in 21d."""
        today_str = "2026-07-04"
        # 3 prior fires for (test_eng, AAPL) in 21d + the current fire
        prior_dates = ["2026-06-14", "2026-06-18", "2026-06-22"]
        current_date = "2026-07-01"
        spine_rows = []
        cols_default = {c: None for c in [
            "signal_id", "engine", "family", "ledger", "as_of", "symbol",
            "scope_type", "universe", "horizon", "direction", "size_binding",
            "fill_basis", "score", "outcome_excess", "outcome_graded", "graded_at",
            "terminal_state_clean15_126", "terminal_state_clean8_21",
            "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63", "fwd_mfe_126",
            "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
            "risk_radar_state", "vector_asof", "species_id", "archetype",
        ]}
        for d in prior_dates + [current_date]:
            r = dict(cols_default)
            r.update({
                "signal_id": f"test_eng:{d}:AAPL:5",
                "engine": "test_eng", "ledger": "test",
                "as_of": d, "symbol": "AAPL",
                "scope_type": "entity", "horizon": 5, "direction": 1,
                "outcome_excess": 0.02, "outcome_graded": True,
            })
            spine_rows.append(r)
        root = _make_root(tmp_path, spine_rows=spine_rows)
        result = build_lagging(root)
        fam = result.get("by_family", {}).get("test_eng", {})
        # The current_date fire should have repeat_fire flag
        flagged = fam.get("flagged", [])
        current_fire_flagged = any(
            f["as_of"] == current_date and "repeat_fire" in f["flags"]
            for f in flagged
        )
        assert current_fire_flagged, (
            f"Expected repeat_fire flag for {current_date}; "
            f"flagged fires: {flagged}"
        )

    def test_repeat_fire_not_set_with_insufficient_priors(self, tmp_path):
        """repeat_fire flag NOT set when only 2 prior fires in 21d (< 3 threshold)."""
        prior_dates = ["2026-06-18", "2026-06-22"]  # only 2
        current_date = "2026-07-01"
        cols_default = {c: None for c in [
            "signal_id", "engine", "family", "ledger", "as_of", "symbol",
            "scope_type", "universe", "horizon", "direction", "size_binding",
            "fill_basis", "score", "outcome_excess", "outcome_graded", "graded_at",
            "terminal_state_clean15_126", "terminal_state_clean8_21",
            "fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63", "fwd_mfe_126",
            "rate_pressure", "quad_hard_label", "fused_risk_label", "vol_regime",
            "risk_radar_state", "vector_asof", "species_id", "archetype",
        ]}
        spine_rows = []
        for d in prior_dates + [current_date]:
            r = dict(cols_default)
            r.update({
                "signal_id": f"test_eng:{d}:AAPL:5",
                "engine": "test_eng", "ledger": "test",
                "as_of": d, "symbol": "AAPL",
                "scope_type": "entity", "horizon": 5, "direction": 1,
                "outcome_excess": 0.02, "outcome_graded": True,
            })
            spine_rows.append(r)
        root = _make_root(tmp_path, spine_rows=spine_rows)
        result = build_lagging(root)
        fam = result.get("by_family", {}).get("test_eng", {})
        flagged = fam.get("flagged", [])
        # Verify no repeat_fire on current_date
        has_repeat = any(
            f["as_of"] == current_date and "repeat_fire" in f["flags"]
            for f in flagged
        )
        assert not has_repeat


class TestLaggingFailOpen:
    def test_missing_regime_store_no_error(self, tmp_path):
        """Missing regime_history.parquet: no exception, gaps logged, hostile False."""
        spine_rows = _minimal_spine(as_of="2026-07-01")
        root = _make_root(tmp_path, spine_rows=spine_rows)
        # No regime file written
        result = build_lagging(root)
        # Should succeed (no exception)
        assert "by_family" in result
        # Gap should be reported
        assert any("regime_history" in g for g in result.get("gaps", []))

    def test_missing_breadth_store_no_error(self, tmp_path):
        """Missing breadth.parquet: no exception, gaps logged, unconfirmed False."""
        spine_rows = _minimal_spine(as_of="2026-07-01")
        root = _make_root(tmp_path, spine_rows=spine_rows)
        # No breadth file written
        result = build_lagging(root)
        assert "by_family" in result
        assert any("breadth" in g for g in result.get("gaps", []))

    def test_missing_spine_index_no_error(self, tmp_path):
        """Missing spine_index.parquet: no exception, by_family is empty."""
        (tmp_path / "data" / "neuralweb").mkdir(parents=True, exist_ok=True)
        result = build_lagging(tmp_path)
        assert "by_family" in result


class TestLaggingEnvelope:
    def test_envelope_keys_present_after_write(self, tmp_path, monkeypatch):
        """write_lagging stamps all five envelope keys as siblings."""
        spine_rows = _minimal_spine(as_of="2026-07-01")
        root = _make_root(tmp_path, spine_rows=spine_rows)
        # Inject synthetic registry so tests do not depend on synapse.yml state
        import engine.neuralweb.envelope as _env_mod
        monkeypatch.setattr(_env_mod, "load_registry", lambda: _REG)
        from engine.neuralweb.lagging import write_lagging
        write_lagging(root)
        out = json.loads(
            (tmp_path / "data" / "neuralweb" / "lagging_signals.json").read_text()
        )
        for k in ENVELOPE_KEYS:
            assert k in out, f"envelope key {k!r} missing"
        # by_family is a sibling (not wrapped)
        assert "by_family" in out

    def test_determinism(self, tmp_path):
        """Same spine/regime/breadth input produces same by_family output."""
        spine_rows = _minimal_spine(as_of="2026-07-01")
        root = _make_root(
            tmp_path, spine_rows=spine_rows,
            regime_rows=[
                {"date": "2026-07-01", "quad": "Q1",
                 "recession": False, "inflation_shock": False}
            ],
        )
        r1 = build_lagging(root)
        r2 = build_lagging(root)
        assert r1["by_family"] == r2["by_family"]
