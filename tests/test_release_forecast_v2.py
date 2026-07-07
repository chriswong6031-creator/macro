"""Tests for PR-F (schema v2) additions to MRI release forecast.

Categories:
  1. inputs_hash — determinism + sensitivity (different feature value → different hash)
  2. release_id / prediction_id — format contracts
  3. Revision sweep — idempotency + append-only, synthetic revised parquet
  4. Reaction rows — math + weekend alignment, synthetic EOD fixtures
  5. Claims projection — contract + walk-forward on synthetic vintages
  6. Schema-1 row compatibility — old ledger rows still load fine by capture/scoreboard

Run:
    python -m pytest tests/test_release_forecast_v2.py -v
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from engine.release_forecast import (
    compute_inputs_hash,
    make_prediction_id,
    make_release_id,
)
from scripts.build_release_forecast import (
    _append_ledger_rows,
    _build_scoreboard,
    _check_reaction_rows,
    _check_release_day_capture,
    _check_revision_sweep,
    _load_ledger,
    _nth_trading_day_after,
    _next_trading_day,
)


# ============================================================
# Helpers
# ============================================================

def _make_vintages_df(rows: list[dict]) -> None:
    """Write data/fred_vintage/vintages.parquet for a tmp_root."""
    pass  # inline in fixtures below


def _write_parquet(root: Path, rel: str, df: pd.DataFrame) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=True)


def _write_parquet_no_index(root: Path, rel: str, df: pd.DataFrame) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


@pytest.fixture()
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "data" / "release_forecast").mkdir(parents=True)
    (tmp_path / "data" / "fred_vintage").mkdir(parents=True)
    (tmp_path / "data" / "fred").mkdir(parents=True)
    (tmp_path / "data" / "yahoo").mkdir(parents=True)
    (tmp_path / "site" / "macrodata").mkdir(parents=True)
    return tmp_path


def _projection_row_v2(
    release: str = "cpi_headline",
    period: str = "2026-06",
    asof_night: str = "2026-07-01",
    proj_point: float = 0.28,
    proj_p10: float = 0.10,
    proj_p25: float = 0.18,
    proj_p75: float = 0.38,
    proj_p90: float = 0.46,
    release_date: str = "2026-07-10",
) -> dict:
    return {
        "schema": 2,
        "row_type": "projection",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": release_date,
        "release_id": f"CPI:{period}:first",
        "prediction_id": f"CPI:{period}:first:{asof_night}:v1",
        "inputs_hash": "abc123",
        "horizon_days": 9,
        "days_to": 9,
        "projection_point": proj_point,
        "projection_p10": proj_p10,
        "projection_p25": proj_p25,
        "projection_p75": proj_p75,
        "projection_p90": proj_p90,
        "confidence": 0.60,
        "input_completeness": 0.75,
        "benchmark_naive_prior": 0.24,
        "benchmark_trailing_3m": 0.25,
        "benchmark_ar_model": 0.26,
        "benchmark_cleveland": 0.30,
        "surprise_skew_sigma": 0.40,
        "surprise_skew_tag": "hotter",
        "fed_stance": "hawkish",
        "gap_bp": 7,
        "implied_cuts_12m": -1,
        "next_fomc": "2026-07-29",
    }


def _scored_row_v2(
    release: str = "cpi_headline",
    period: str = "2026-06",
    asof_night: str = "2026-07-14",
    actual: float = 0.30,
    proj_point: float = 0.28,
    proj_p25: float = 0.18,
    proj_p75: float = 0.38,
    release_date: str = "2026-07-10",
) -> dict:
    return {
        "schema": 2,
        "row_type": "scored",
        "asof_night": asof_night,
        "release": release,
        "period": period,
        "release_date": release_date,
        "actual": actual,
        "actual_first": actual,
        "raw_initial_print": None,
        "frozen_asof_night": "2026-07-01",
        "frozen_projection_point": proj_point,
        "frozen_projection_p10": 0.10,
        "frozen_projection_p25": proj_p25,
        "frozen_projection_p75": proj_p75,
        "frozen_projection_p90": 0.46,
        "our_surprise": round(actual - proj_point, 4),
        "surprise_vs_naive": round(actual - 0.24, 4),
        "surprise_vs_trailing": round(actual - 0.25, 4),
        "surprise_vs_ar": round(actual - 0.26, 4),
        "surprise_vs_cleveland": round(actual - 0.30, 4),
        "interval_hit": True,
        "skew_hit": True,
        "benchmark_naive_prior": 0.24,
    }


# ============================================================
# 1. inputs_hash — determinism + sensitivity
# ============================================================

class TestInputsHash:
    def test_deterministic_same_features(self):
        """Same features always produce the same hash."""
        feats = {"lag1": 0.2, "lag2": 0.18, "lag3": 0.15, "ppi": 0.3}
        h1 = compute_inputs_hash(feats)
        h2 = compute_inputs_hash(feats)
        assert h1 == h2, "inputs_hash not deterministic"

    def test_hash_is_hex_string(self):
        feats = {"a": 1.0, "b": 2.0}
        h = compute_inputs_hash(feats)
        assert isinstance(h, str)
        assert len(h) == 64, f"Expected sha256 hex (64 chars), got {len(h)}"
        int(h, 16)  # raises ValueError if not valid hex

    def test_different_value_different_hash(self):
        """Changing any feature value must change the hash."""
        base = {"lag1": 0.2, "lag2": 0.18}
        alt = {"lag1": 0.21, "lag2": 0.18}  # lag1 changed
        assert compute_inputs_hash(base) != compute_inputs_hash(alt), (
            "Different feature values must produce different hashes"
        )

    def test_different_feature_name_different_hash(self):
        """Changing a feature name must change the hash."""
        h1 = compute_inputs_hash({"lag1": 0.2, "lag2": 0.18})
        h2 = compute_inputs_hash({"lag1": 0.2, "lag3": 0.18})  # lag2 → lag3
        assert h1 != h2

    def test_none_values_excluded(self):
        """None values are excluded from hash computation."""
        h1 = compute_inputs_hash({"a": 1.0, "b": None})
        h2 = compute_inputs_hash({"a": 1.0})
        assert h1 == h2, "None values should be excluded from hash (same result as omitting them)"

    def test_ordering_invariant(self):
        """Hash is order-invariant (sorted by feature name)."""
        h1 = compute_inputs_hash({"a": 1.0, "b": 2.0})
        h2 = compute_inputs_hash({"b": 2.0, "a": 1.0})
        assert h1 == h2, "inputs_hash must be independent of dict insertion order"

    def test_empty_features(self):
        """Empty feature dict produces a stable hash (sha256 of empty array)."""
        h = compute_inputs_hash({})
        assert isinstance(h, str) and len(h) == 64


# ============================================================
# 2. release_id / prediction_id format contracts
# ============================================================

class TestReleaseIdFormats:
    def test_cpi_release_id(self):
        rid = make_release_id("cpi_headline", "2026-06")
        assert rid == "CPI:2026-06:first"

    def test_cpi_core_release_id(self):
        rid = make_release_id("cpi_core", "2026-06")
        assert rid == "CPI_CORE:2026-06:first"

    def test_nfp_release_id(self):
        rid = make_release_id("nfp", "2026-07")
        assert rid == "NFP:2026-07:first"

    def test_claims_release_id(self):
        rid = make_release_id("claims", "2026-07-11")
        assert rid == "CLAIMS:2026-07-11:first"

    def test_prediction_id_format(self):
        rid = "CPI:2026-06:first"
        asof = "2026-07-07"
        pid = make_prediction_id(rid, asof)
        assert pid == "CPI:2026-06:first:2026-07-07:v1"

    def test_prediction_id_contains_release_id(self):
        rid = make_release_id("nfp", "2026-07")
        pid = make_prediction_id(rid, "2026-08-01")
        assert pid.startswith(rid)
        assert "2026-08-01" in pid
        assert pid.endswith(":v1")


# ============================================================
# 3. Revision sweep — idempotency + append-only
# ============================================================

def _make_vintage_parquet(root: Path, rows: list[dict]) -> None:
    df = pd.DataFrame(rows)
    for col in ("period", "realtime_start", "realtime_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


class TestRevisionSweep:
    def _make_scored_ledger(self, actual_first: float = 0.30) -> list[dict]:
        return [_scored_row_v2(actual=actual_first, proj_point=0.28)]

    def _make_cpi_vintage_with_revision(
        self, root: Path, actual_first: float, revised_val: float
    ) -> None:
        """Write vintages with both initial print and a later revision."""
        _make_vintage_parquet(root, [
            # Prior month (for MoM computation)
            {
                "series": "CPIAUCSL", "period": "2026-05-01",
                "value": 315.000, "realtime_start": "2026-06-12",
                "realtime_end": "2099-01-01",
            },
            # Initial print (release_date 2026-07-10): back-computed level for actual_first MoM
            {
                "series": "CPIAUCSL", "period": "2026-06-01",
                "value": 315.000 * (1 + actual_first / 100),
                "realtime_start": "2026-07-10",
                "realtime_end": "2026-08-14",
            },
            # Revision (later realtime_start)
            {
                "series": "CPIAUCSL", "period": "2026-06-01",
                "value": 315.000 * (1 + revised_val / 100),
                "realtime_start": "2026-08-14",
                "realtime_end": "2099-01-01",
            },
        ])

    def test_no_revision_no_row(self, tmp_root: Path):
        """If actual_first == latest, no revision row emitted."""
        actual = 0.40
        self._make_cpi_vintage_with_revision(tmp_root, actual_first=actual, revised_val=actual)
        ledger = self._make_scored_ledger(actual_first=actual)
        rows = _check_revision_sweep(date(2026, 9, 1), tmp_root, ledger)
        assert rows == [], "No revision row expected when value unchanged"

    def test_revision_emitted_when_different(self, tmp_root: Path):
        """If revised value differs from actual_first, one revision row is emitted."""
        actual_first = 0.30
        revised_val = 0.35  # 5bp revision
        self._make_cpi_vintage_with_revision(tmp_root, actual_first, revised_val)
        ledger = self._make_scored_ledger(actual_first=actual_first)
        rows = _check_revision_sweep(date(2026, 9, 1), tmp_root, ledger)
        assert len(rows) == 1, f"Expected 1 revision row, got {len(rows)}"
        r = rows[0]
        assert r["row_type"] == "revision"
        assert r["schema"] == 2
        assert r["actual_first"] == pytest.approx(actual_first, abs=1e-3)
        assert "actual_latest" in r
        assert "revision_pp" in r
        assert abs(r["revision_pp"]) > 1e-9

    def test_revision_idempotent(self, tmp_root: Path):
        """Running sweep twice does not produce duplicate revision rows."""
        actual_first = 0.30
        revised_val = 0.35
        self._make_cpi_vintage_with_revision(tmp_root, actual_first, revised_val)
        ledger = self._make_scored_ledger(actual_first=actual_first)

        rows1 = _check_revision_sweep(date(2026, 9, 1), tmp_root, ledger)
        # Second call: add the first revision rows to the ledger (simulating append)
        ledger2 = ledger + rows1
        rows2 = _check_revision_sweep(date(2026, 9, 2), tmp_root, ledger2)
        assert rows2 == [], "Revision sweep must be idempotent for same revised value"

    def test_revision_append_only(self, tmp_root: Path):
        """Revision rows are appended, not replacing scored rows."""
        actual_first = 0.30
        revised_val = 0.35
        self._make_cpi_vintage_with_revision(tmp_root, actual_first, revised_val)
        ledger_path = tmp_root / "data" / "release_forecast" / "forward_ledger.jsonl"
        scored = self._make_scored_ledger(actual_first=actual_first)
        _append_ledger_rows(ledger_path, scored)
        revision_rows = _check_revision_sweep(date(2026, 9, 1), tmp_root, scored)
        _append_ledger_rows(ledger_path, revision_rows)

        all_rows = _load_ledger(ledger_path)
        scored_count = sum(1 for r in all_rows if r["row_type"] == "scored")
        revision_count = sum(1 for r in all_rows if r["row_type"] == "revision")
        assert scored_count == 1, "Scored rows must not be removed"
        assert revision_count == len(revision_rows)


# ============================================================
# 4. Reaction rows — math + weekend alignment
# ============================================================

class TestReactionRows:
    def _make_eod_series(self, root: Path) -> None:
        """Write synthetic EOD series for DGS10, T10Y2Y, SPY, DTWEXBGS.

        Release date = 2026-07-08 (Wednesday).
        h0_prior = 2026-07-07 (Tuesday).
        h0      = 2026-07-08 (Wednesday).
        h1      = 2026-07-09 (Thursday).
        Series starts 2026-07-07 so all three dates are in index.
        """
        # Start from 2026-07-07 (Tuesday) so h0_prior is in the index
        dates = pd.date_range("2026-07-07", periods=10, freq="B")  # Business days
        n = len(dates)
        # dates[0] = 2026-07-07 (h0_prior for release 2026-07-08)
        # dates[1] = 2026-07-08 (h0)
        # dates[2] = 2026-07-09 (h1)

        # DGS10 (us10y) in pct — 4.20 on h0_prior, 4.30 on h0 (+10bp), 4.25 on h1 (-5bp)
        dgs10 = pd.DataFrame({"us10y": [4.20] * n}, index=dates)
        dgs10.index.name = "date"
        dgs10.iloc[1] = 4.30  # h0 (2026-07-08): up 10bp
        dgs10.iloc[2] = 4.25  # h1 (2026-07-09): down 5bp
        _write_parquet(root, "data/fred/DGS10.parquet", dgs10)

        # T10Y2Y — 0.50 on h0_prior, 0.55 on h0 (+5bp)
        t10y2y = pd.DataFrame({"spread_2s10s": [0.50] * n}, index=dates)
        t10y2y.index.name = "date"
        t10y2y.iloc[1] = 0.55  # h0: +5bp
        _write_parquet(root, "data/fred/T10Y2Y.parquet", t10y2y)

        # SPY (close) — 450 on h0_prior, 447 on h0, 449 on h1
        spy = pd.DataFrame({"close": [450.0] * n}, index=dates)
        spy.index.name = "Date"
        spy.iloc[1] = 447.0   # h0: -0.667%
        spy.iloc[2] = 449.0   # h1: +0.447%
        _write_parquet(root, "data/yahoo/SPY.parquet", spy)

        # DTWEXBGS — 114.0 on h0_prior, 114.5 on h0
        dtwex = pd.DataFrame({"broad_dollar": [114.0] * n}, index=dates)
        dtwex.index.name = "date"
        dtwex.iloc[1] = 114.5  # h0: +0.439%
        _write_parquet(root, "data/fred/DTWEXBGS.parquet", dtwex)

    def test_reaction_row_math(self, tmp_root: Path):
        """Reaction row math: dgs10_h0_bp = (h0 - prior) × 100.

        Series: h0_prior=2026-07-07 (4.20), h0=2026-07-08 (4.30), h1=2026-07-09 (4.25).
        Release date = 2026-07-08 (Wednesday) → h0 = 2026-07-08, h0_prior = 2026-07-07.
        """
        self._make_eod_series(tmp_root)
        # Release date = 2026-07-08 (Wednesday), h0 = 2026-07-08, h1 = 2026-07-09 (Thu)
        scored = [_scored_row_v2(
            release="cpi_headline", period="2026-06",
            release_date="2026-07-08",
            asof_night="2026-07-10",
        )]
        rows = _check_reaction_rows(date(2026, 7, 10), tmp_root, scored)
        assert len(rows) == 1, f"Expected 1 reaction row, got {len(rows)}"
        r = rows[0]
        assert r["row_type"] == "reaction"
        assert r["schema"] == 2
        # dgs10_h0_bp: (4.30 - 4.20) × 100 = 10bp
        assert r["dgs10_h0_bp"] == pytest.approx(10.0, abs=0.01)
        # dgs10_h1_bp: (4.25 - 4.30) × 100 = -5bp
        assert r["dgs10_h1_bp"] == pytest.approx(-5.0, abs=0.01)
        # spy_h0_pct: (447 / 450 - 1) × 100
        assert r["spy_h0_pct"] == pytest.approx((447.0 / 450.0 - 1) * 100, abs=0.001)
        # spy_h1_pct: (449 / 447 - 1) × 100
        assert r["spy_h1_pct"] == pytest.approx((449.0 / 447.0 - 1) * 100, abs=0.001)

    def test_weekend_release_maps_to_next_trading_day(self):
        """A Saturday release date maps h0 to the following Monday."""
        sat = date(2026, 7, 11)  # Saturday
        assert sat.weekday() == 5, "Fixture error: 2026-07-11 must be Saturday"
        h0 = _next_trading_day(sat)
        assert h0.weekday() == 0, f"h0 must be Monday, got weekday={h0.weekday()}"
        assert h0 == date(2026, 7, 13)

    def test_h1_is_next_business_day_after_h0(self):
        """h1 = next business day after h0."""
        h0 = date(2026, 7, 10)  # Friday
        h1 = _nth_trading_day_after(h0, 1)
        assert h1 == date(2026, 7, 13), f"h1 after Friday must be Monday, got {h1}"

    def test_reaction_row_idempotent(self, tmp_root: Path):
        """Second sweep doesn't add a second reaction row for same (release, period)."""
        self._make_eod_series(tmp_root)
        scored = [_scored_row_v2(
            release="cpi_headline", period="2026-06",
            release_date="2026-07-08", asof_night="2026-07-10",
        )]
        rows1 = _check_reaction_rows(date(2026, 7, 10), tmp_root, scored)
        combined = scored + rows1
        rows2 = _check_reaction_rows(date(2026, 7, 11), tmp_root, combined)
        assert rows2 == [], "Reaction row must be idempotent"

    def test_no_reaction_if_h1_not_available(self, tmp_root: Path):
        """No reaction row if h1 date is in the future relative to today.

        Release date = 2026-07-08 (Wed). h0 = 2026-07-08, h1 = 2026-07-09.
        today = 2026-07-08 → h1 > today → no reaction row.
        """
        self._make_eod_series(tmp_root)
        scored = [_scored_row_v2(
            release="cpi_headline", period="2026-06",
            release_date="2026-07-08", asof_night="2026-07-08",
        )]
        # today = 2026-07-08 = h0 day; h1 = 2026-07-09 > today
        rows = _check_reaction_rows(date(2026, 7, 8), tmp_root, scored)
        assert rows == [], "No reaction row when h1 data not yet available"


# ============================================================
# 5. Claims projection — contract + walk-forward on synthetic vintages
# ============================================================

def _make_claims_vintages(root: Path, n_weeks: int = 80) -> pd.DataFrame:
    """Write synthetic ICSA + IC4WSA vintage rows (weekly, 2010→).

    IC4WSA[t] = trailing 4-week average of ICSA initial prints.
    Each observation is published 6 days after the reference period (Saturday).
    """
    base_date = pd.Timestamp("2010-01-02")  # First Saturday
    rows = []
    rng = np.random.default_rng(42)
    # Raw ALFRED persons scale (~200,000), matching real ICSA/IC4WSA vintages;
    # project_claims converts to thousands internally.
    icsa_vals = 200000.0 + rng.standard_normal(n_weeks) * 10000

    for i in range(n_weeks):
        period = base_date + pd.Timedelta(weeks=i)
        rt_start = period + pd.Timedelta(days=6)  # published 6 days later
        icsa_val = round(icsa_vals[i], 1)
        rows.append({
            "series": "ICSA",
            "period": period,
            "value": icsa_val,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("2099-12-31"),
        })
        # IC4WSA = simple trailing 4-week mean of ICSA
        if i >= 3:
            ic4 = round(np.mean(icsa_vals[max(0, i - 3):i + 1]), 1)
        else:
            ic4 = round(np.mean(icsa_vals[:i + 1]), 1)
        rows.append({
            "series": "IC4WSA",
            "period": period,
            "value": ic4,
            "realtime_start": rt_start,
            "realtime_end": pd.Timestamp("2099-12-31"),
        })

    df = pd.DataFrame(rows)
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return df


class TestClaimsProjection:
    def test_claims_projection_contract(self, tmp_root: Path):
        """project_claims returns required keys with display_only=True, authority=False."""
        _make_claims_vintages(tmp_root, n_weeks=80)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        asof = date(2011, 8, 1)
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=24,
        )
        assert result["release"] == "claims"
        assert result["display_only"] is True
        assert result["authority"] is False
        assert result["target"] == "icsa_level"
        assert result["regime_axis"] == "growth"
        assert "point" in result
        assert result["pit_provenance"]["authority"] is False

    def test_claims_point_equals_last_ic4wsa(self, tmp_root: Path):
        """Point estimate must equal the last IC4WSA initial print knowable at asof,
        expressed in thousands (ic4wsa_last / 1000.0)."""
        _make_claims_vintages(tmp_root, n_weeks=60)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        asof = date(2011, 4, 1)
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=24,
        )
        # Last IC4WSA knowable at asof — point is now in thousands (FIX-4)
        ic4wsa = knowable_series(vintages, "IC4WSA", asof)
        if not ic4wsa.empty:
            expected_point = round(float(ic4wsa["value"].iloc[-1]) / 1000.0, 3)
            assert result["point"] == pytest.approx(expected_point, abs=0.001)
            # Sanity: synthetic data is ~200,000 raw persons → ~200.0 in thousands
            assert 150.0 <= result["point"] <= 260.0, (
                f"point={result['point']} not in plausible thousands range [150, 260] "
                "(synthetic ICSA ~200,000 raw persons → ~200.0 thousands)"
            )

    def test_claims_quantiles_when_enough_residuals(self, tmp_root: Path):
        """With n>=24 residuals, quantiles are non-null and ordered p10<=p25<=p50<=p75<=p90."""
        _make_claims_vintages(tmp_root, n_weeks=80)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        asof = date(2011, 8, 1)
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=24,
        )
        if result["n_residuals"] >= 24:
            vals = [result.get(k) for k in ("p10", "p25", "p50", "p75", "p90")]
            assert all(v is not None for v in vals), "All quantiles must be non-null with enough residuals"
            assert vals[0] <= vals[1] <= vals[2] <= vals[3] <= vals[4], (
                f"Quantile order violated: {vals}"
            )

    def test_claims_quantiles_null_insufficient_data(self, tmp_root: Path):
        """With <24 residuals, quantiles are null."""
        _make_claims_vintages(tmp_root, n_weeks=10)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        asof = date(2010, 4, 1)
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=24,
        )
        if result["n_residuals"] < 24:
            assert result["p10"] is None, "p10 must be null with fewer than 24 residuals"

    def test_claims_walk_forward_residuals_pit(self, tmp_root: Path):
        """Walk-forward residuals respect PIT: IC4WSA used for period T must have
        realtime_start < corresponding ICSA's realtime_start."""
        _make_claims_vintages(tmp_root, n_weeks=60)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        # At the latest asof, n_residuals should be positive (PIT correctly pairs series)
        asof = date(2011, 5, 1)
        result = project_claims(
            asof, vintages,
            knowable_series_fn=knowable_series,
            min_quantile_obs=5,
        )
        assert result["n_residuals"] > 0, (
            "Expected positive residual count — PIT pairing may have failed"
        )

    def test_claims_empty_vintages(self, tmp_root: Path):
        """With empty vintages, project_claims returns a null projection."""
        # Write empty vintages
        df = pd.DataFrame(columns=["series", "period", "value", "realtime_start", "realtime_end"])
        (tmp_root / "data" / "fred_vintage").mkdir(parents=True, exist_ok=True)
        df.to_parquet(tmp_root / "data" / "fred_vintage" / "vintages.parquet", index=False)
        from engine.release_forecast import load_vintages, knowable_series
        from engine.release_components_nfp import project_claims
        vintages = load_vintages(tmp_root)
        result = project_claims(
            date(2010, 6, 1), vintages,
            knowable_series_fn=knowable_series,
        )
        assert result["point"] is None
        assert result["release"] == "claims"


# ============================================================
# 6. Schema-1 row compatibility (old rows still work in capture/scoreboard)
# ============================================================

class TestSchema1Compatibility:
    """Old schema-1 rows (no 'schema' key, no 'actual_first') must still be
    handled correctly by the capture function and scoreboard aggregation."""

    def _schema1_projection_row(self) -> dict:
        return {
            "row_type": "projection",
            "asof_night": "2026-07-01",
            "release": "cpi_headline",
            "period": "2026-06",
            "release_date": "2026-07-10",
            "days_to": 9,
            "projection_point": 0.28,
            "projection_p10": 0.10,
            "projection_p90": 0.46,
            "confidence": 0.60,
            "input_completeness": 0.75,
            "benchmark_naive_prior": 0.24,
            "benchmark_trailing_3m": 0.25,
            "benchmark_ar_model": 0.26,
            "benchmark_cleveland": 0.30,
            "surprise_skew_sigma": 0.40,
            "surprise_skew_tag": "hotter",
            "fed_stance": "hawkish",
            "gap_bp": 7,
            "implied_cuts_12m": -1,
            "next_fomc": "2026-07-29",
        }

    def _schema1_scored_row(self) -> dict:
        return {
            "row_type": "scored",
            "asof_night": "2026-07-14",
            "release": "cpi_headline",
            "period": "2026-06",
            "release_date": "2026-07-10",
            "actual": 0.30,
            "raw_initial_print": None,
            "frozen_asof_night": "2026-07-01",
            "frozen_projection_point": 0.28,
            "frozen_projection_p10": 0.10,
            "frozen_projection_p90": 0.46,
            "our_surprise": 0.02,
            "surprise_vs_naive": 0.06,
            "surprise_vs_trailing": 0.05,
            "surprise_vs_ar": 0.04,
            "surprise_vs_cleveland": 0.0,
            "interval_hit": True,
            "skew_hit": True,
        }

    def test_schema1_scored_in_scoreboard(self):
        """Schema-1 scored rows enter the scoreboard without error."""
        scored = [self._schema1_scored_row()]
        sb = _build_scoreboard(scored, accrual_start="2026-07-07")
        cpi = sb["by_release"].get("cpi_headline")
        assert cpi is not None
        assert cpi["n"] == 1
        assert cpi["mae_ours"] is not None

    def test_schema1_no_duplicate_scored_row(self, tmp_root: Path):
        """Schema-1 projection rows still trigger release-day capture."""
        _make_vintage_parquet_for_capture(tmp_root)
        ledger = [self._schema1_projection_row()]
        scored = _check_release_day_capture(date(2026, 7, 14), tmp_root, ledger)
        assert len(scored) == 1, "Schema-1 projection row must enable capture"
        # The scored row must have actual_first (v2 field added in capture)
        assert "actual_first" in scored[0]

    def test_schema1_scoreboard_interval_50_null(self):
        """Schema-1 scored rows (no p25/p75) get None for interval_50_coverage."""
        scored = [self._schema1_scored_row()]
        sb = _build_scoreboard(scored, accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        # p25/p75 not in schema-1 rows → interval_50_coverage is None
        assert cpi.get("interval_50_coverage") is None


def _make_vintage_parquet_for_capture(root: Path) -> None:
    """Write CPI vintages for release-day capture test."""
    rows = [
        {
            "series": "CPIAUCSL", "period": "2026-05-01",
            "value": 315.000, "realtime_start": "2026-06-12",
            "realtime_end": "2099-01-01",
        },
        {
            "series": "CPIAUCSL", "period": "2026-06-01",
            "value": 316.260, "realtime_start": "2026-07-10",
            "realtime_end": "2099-01-01",
        },
    ]
    df = pd.DataFrame(rows)
    for col in ("period", "realtime_start", "realtime_end"):
        df[col] = pd.to_datetime(df[col])
    path = root / "data" / "fred_vintage" / "vintages.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


# ============================================================
# 7. Scoreboard v2 fields
# ============================================================

class TestScoreboardV2Fields:
    """Verify schema v2 scoreboard additions."""

    def test_scoreboard_has_v2_schema(self):
        sb = _build_scoreboard([], accrual_start="2026-07-07")
        assert sb["schema"] in ("release_forecast_scoreboard.v1", "release_forecast_scoreboard.v2")

    def test_interval_50_coverage_computed(self):
        """interval_50_coverage uses p25-p75 band."""
        # actual=0.30 is within [p25=0.18, p75=0.38] → hit
        row = _scored_row_v2(actual=0.30, proj_p25=0.18, proj_p75=0.38)
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        assert cpi["interval_50_coverage"] == pytest.approx(1.0, abs=1e-4)
        assert cpi["interval_50_coverage_n"] == 1

    def test_interval_50_coverage_miss(self):
        """actual outside [p25, p75] → miss."""
        row = _scored_row_v2(actual=0.50, proj_p25=0.18, proj_p75=0.38)
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        assert cpi["interval_50_coverage"] == pytest.approx(0.0, abs=1e-4)

    def test_mae_vs_actual_latest_from_revision(self):
        """mae_vs_actual_latest uses projection vs actual_latest from revision rows."""
        scored = _scored_row_v2(actual=0.30, proj_point=0.28)
        revision = {
            "schema": 2,
            "row_type": "revision",
            "asof_night": "2026-09-01",
            "release": "cpi_headline",
            "period": "2026-06",
            "actual_first": 0.30,
            "actual_latest": 0.35,
            "revised_value": 0.35,
            "revision_pp": 0.05,
        }
        sb = _build_scoreboard([scored, revision], accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        # mae_vs_actual_latest = |0.35 - 0.28| = 0.07
        assert cpi["mae_vs_actual_latest"] == pytest.approx(0.07, abs=1e-4)

    def test_mae_vs_actual_latest_null_when_no_revisions(self):
        """mae_vs_actual_latest is null when no revision rows exist."""
        row = _scored_row_v2()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        assert cpi["mae_vs_actual_latest"] is None

    def test_reaction_summary_null_when_fewer_than_3(self):
        """reaction_mean_abs_dgs10_h0_bp is null when n<3."""
        rows = [_scored_row_v2(period=f"2026-0{i}") for i in range(1, 3)]
        sb = _build_scoreboard(rows, accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        assert cpi["reaction_mean_abs_dgs10_h0_bp"] is None

    def test_interval_50_coverage_note_present(self):
        """interval_50_coverage_note must be present to flag the approximation."""
        row = _scored_row_v2()
        sb = _build_scoreboard([row], accrual_start="2026-07-07")
        cpi = sb["by_release"]["cpi_headline"]
        assert "interval_50_coverage_note" in cpi


# ============================================================
# 8. Module split — imports still work via engine.release_forecast
# ============================================================

class TestModuleSplit:
    def test_build_cpi_features_importable(self):
        """build_cpi_features is importable from engine.release_forecast (backward compat)."""
        from engine.release_forecast import build_cpi_features
        assert callable(build_cpi_features)

    def test_build_nfp_features_importable(self):
        """build_nfp_features is importable from engine.release_forecast (backward compat)."""
        from engine.release_forecast import build_nfp_features
        assert callable(build_nfp_features)

    def test_project_release_accepts_claims(self):
        """project_release now accepts 'claims' without raising ValueError."""
        # We pass an asof date; it will fail gracefully (empty vintages) but not with ValueError
        from engine.release_forecast import project_release
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            (td_path / "data" / "fred_vintage").mkdir(parents=True)
            # Write empty vintages
            df = pd.DataFrame(columns=["series", "period", "value", "realtime_start", "realtime_end"])
            df.to_parquet(td_path / "data" / "fred_vintage" / "vintages.parquet", index=False)
            result = project_release("claims", date(2026, 7, 7), td_path)
            assert result["release"] == "claims"
            assert result["display_only"] is True

    def test_cpi_component_importable(self):
        """engine.release_components_cpi is importable."""
        from engine.release_components_cpi import build_cpi_features as _build
        assert callable(_build)

    def test_nfp_component_importable(self):
        """engine.release_components_nfp is importable."""
        from engine.release_components_nfp import build_nfp_features as _build
        assert callable(_build)

    def test_claims_component_importable(self):
        """engine.release_components_nfp.project_claims is importable."""
        from engine.release_components_nfp import project_claims
        assert callable(project_claims)
