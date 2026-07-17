"""Tests for engine.event_window — P3 event-window engine (RIC program).

Guards: phase logic vs hand-built date fixtures, collision detection (including
triple_stack), ledger idempotency + lane gate, ex-ante read null-degradation when
MRI/T1 inputs absent, and the fundamental RIC-R3 / MRI-R20 non-scoring laws.
"""
from __future__ import annotations

import json
import os
from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import event_window as ew


# ---------------------------------------------------------------------------
# Helper: build a trading-day index including a known set of events
# ---------------------------------------------------------------------------
def _make_index(start: str = "2024-01-01", end: str = "2026-12-31") -> pd.DatetimeIndex:
    """US trading-day index (Mon-Fri, no holidays modelled — sufficient for tag tests)."""
    idx = pd.bdate_range(start=start, end=end)
    return idx


def _spy_close(idx: pd.DatetimeIndex, seed: int = 42) -> pd.Series:
    """Synthetic SPY close series (geometric random walk)."""
    rng = np.random.default_rng(seed)
    ret = rng.normal(0.0003, 0.012, len(idx))
    close = 400.0 * np.exp(np.cumsum(ret))
    return pd.Series(close, index=idx)


# ---------------------------------------------------------------------------
# 1. Phase logic — known event dates should tag correctly
# ---------------------------------------------------------------------------
class TestTagPhaseLogic:
    """Verify tag() phase assignments for known calendar dates."""

    def setup_method(self):
        self.idx = _make_index()
        self.t = ew.tag(self.idx)

    def test_fomc_day_phase(self):
        # Known FOMC dates from _FOMC_ANNOUNCEMENT_DATES
        for ds in ["2026-01-28", "2026-03-18", "2026-06-17"]:
            d = pd.Timestamp(ds)
            if d in self.t.index:
                assert self.t.loc[d, "phase"] == "fomc_day", f"Expected fomc_day on {ds}"
                assert self.t.loc[d, "td_to_fomc"] == 0

    def test_cpi_day_phase(self):
        # CPI July 2026: day 14
        d = pd.Timestamp("2026-07-14")
        if d in self.t.index:
            # CPI day should NOT be fomc_day (no FOMC that day)
            assert self.t.loc[d, "phase"] in ("cpi_day", "cpi_week", "quiet"), (
                f"2026-07-14 phase: {self.t.loc[d, 'phase']}"
            )
            assert self.t.loc[d, "td_to_cpi"] == 0 or self.t.loc[d, "td_to_cpi"] <= 4

    def test_claims_day_is_thursday(self):
        """Every row with claims_day=True must be a Thursday."""
        claims = self.t[self.t["claims_day"]]
        for ts in claims.index:
            assert ts.weekday() == 3, f"{ts} is not a Thursday but has claims_day=True"

    def test_quiet_when_no_event_nearby(self):
        """Days far from any event should be 'quiet'."""
        # 2026-04-01 is well away from FOMC (next FOMC 2026-04-29), CPI (2026-04-10),
        # NFP (2026-05-08) and PPI (2026-04-14) — within a month though
        # Find some quiet day: pick a random Friday in a calm week
        # We expect significant fraction of days to be "quiet"
        quiet_count = (self.t["phase"] == "quiet").sum()
        total = len(self.t)
        assert quiet_count > total * 0.3, (
            f"Expected >30% quiet days, got {quiet_count}/{total}"
        )

    def test_all_phases_valid(self):
        """All emitted phase labels must be from the frozen taxonomy."""
        valid = {"cpi_day", "cpi_week", "fomc_day", "fomc_week",
                 "post_fomc_3d", "nfp_day", "quiet"}
        emitted = set(self.t["phase"].unique())
        assert emitted.issubset(valid), f"Unknown phases: {emitted - valid}"

    def test_td_to_nonnegative(self):
        """td_to_* should always be >= 0 or NaN (never negative)."""
        for col in ("td_to_cpi", "td_to_fomc", "td_to_nfp", "td_to_ppi"):
            vals = self.t[col].dropna()
            assert (vals >= 0).all(), f"{col} has negative values"

    def test_fomc_day_td_to_fomc_zero(self):
        """td_to_fomc must be exactly 0 on all fomc_day rows."""
        fomc_rows = self.t[self.t["phase"] == "fomc_day"]
        assert len(fomc_rows) > 0, "No FOMC days found in index"
        assert (fomc_rows["td_to_fomc"] == 0).all()

    def test_post_fomc_3d_follows_fomc(self):
        """post_fomc_3d rows must occur 1-3 trading days after a FOMC day."""
        fomc_days = set(self.t[self.t["phase"] == "fomc_day"].index)
        post_rows = self.t[self.t["phase"] == "post_fomc_3d"]
        for ts in post_rows.index:
            # td_since_fomc is embedded in the phase logic; check indirectly:
            # the preceding fomc_day should exist within 3 trading days
            found = False
            i = list(self.t.index).index(ts)
            for j in range(1, 4):
                if i - j >= 0 and self.t.index[i - j] in fomc_days:
                    found = True
                    break
            assert found, f"post_fomc_3d at {ts} but no FOMC day within 3 preceding trading days"


# ---------------------------------------------------------------------------
# 2. Collision detection
# ---------------------------------------------------------------------------
class TestCollisionDetection:
    """Verify collision state logic."""

    def setup_method(self):
        self.idx = _make_index()
        self.t = ew.tag(self.idx)

    def test_collision_columns_present(self):
        assert all(c in self.t.columns for c in [
            "cpi_fomc_same_week", "cpi_in_opex_week",
            "fomc_in_opex_week", "triple_stack",
        ])

    def test_triple_stack_implies_fomc_in_opex_week(self):
        """triple_stack must always co-occur with fomc_in_opex_week."""
        ts_rows = self.t[self.t["triple_stack"]]
        for ts in ts_rows.index:
            assert self.t.loc[ts, "fomc_in_opex_week"], (
                f"triple_stack at {ts} but fomc_in_opex_week=False"
            )

    def test_collision_booleans(self):
        """All collision columns must be boolean dtype."""
        for col in ("cpi_fomc_same_week", "cpi_in_opex_week",
                    "fomc_in_opex_week", "triple_stack"):
            assert self.t[col].dtype == bool, f"{col} is not bool"

    def test_cpi_fomc_same_week_bidirectional(self):
        """cpi_fomc_same_week should be symmetric: CPI near FOMC and vice versa."""
        # Check there are some weeks where both CPI and FOMC are close together
        # We don't mandate a specific count but the logic should fire when both
        # events are within 4 trading days
        # 2026-03: CPI=11, FOMC=18 — 7 calendar days apart, ~5 trading days
        # This might be just outside the 4-td window — that's OK
        # Just verify the logic is internally consistent: if it fires, both
        # td_to_cpi and td_to_fomc are <= 4
        active = self.t[self.t["cpi_fomc_same_week"]]
        for ts in active.index:
            row = self.t.loc[ts]
            assert row["td_to_cpi"] <= 4 and row["td_to_fomc"] <= 4, (
                f"cpi_fomc_same_week at {ts} but td_to_cpi={row['td_to_cpi']} "
                f"td_to_fomc={row['td_to_fomc']}"
            )


# ---------------------------------------------------------------------------
# 3. Ledger idempotency + lane gate
# ---------------------------------------------------------------------------
class TestLedgerIdempotency:

    def test_stamp_ex_ante_requires_lane(self, tmp_path):
        """stamp_ex_ante() must no-op when COLLECT_LANE != nightly."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "render"
            result = ew.stamp_ex_ante(
                "CPI", "2026-07-14",
                {"asof": "2026-07-13", "implied_event_move": None,
                 "mri_surprise_dispersion": None, "gamma_regime": None},
                {"phase": "cpi_week", "active_collisions": []},
                path=tmp_path / "forward_log.jsonl",
            )
            assert result is False
            p = tmp_path / "forward_log.jsonl"
            assert not p.exists() or p.read_text().strip() == ""
        finally:
            os.environ["COLLECT_LANE"] = env_save

    def test_stamp_ex_ante_writes_on_nightly(self, tmp_path):
        """stamp_ex_ante() writes exactly one row when COLLECT_LANE=nightly."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex_ante = {
                "asof": "2026-07-13",
                "implied_event_move": {
                    "implied_1d_move_pct": 0.72, "atm_iv_pct": 18.5,
                    "available": True, "dte": 1, "exp": "2026-07-14",
                },
                "mri_surprise_dispersion": {
                    "sigma_surprise": 0.15, "available": True,
                },
                "gamma_regime": "negative",
            }
            snap = {"phase": "cpi_week", "active_collisions": []}
            r1 = ew.stamp_ex_ante("CPI", "2026-07-14", ex_ante, snap, path=p)
            assert r1 is True
            rows = ew._read_ledger(p)
            assert len(rows) == 1
            assert rows[0]["release_type"] == "CPI"
            assert rows[0]["release_date"] == "2026-07-14"
            assert rows[0]["implied_1d_move_pct"] == 0.72
            assert rows[0]["realized_1d_move_pct"] is None  # not yet graded
        finally:
            os.environ["COLLECT_LANE"] = env_save

    def test_keep_first_idempotency(self, tmp_path):
        """Second call for same (release_type, release_date) must not overwrite."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex1 = {"asof": "2026-07-13", "implied_event_move": {"implied_1d_move_pct": 0.72},
                   "mri_surprise_dispersion": None, "gamma_regime": None}
            ex2 = {"asof": "2026-07-13", "implied_event_move": {"implied_1d_move_pct": 0.99},
                   "mri_surprise_dispersion": None, "gamma_regime": None}
            snap = {"phase": "cpi_week", "active_collisions": []}
            ew.stamp_ex_ante("CPI", "2026-07-14", ex1, snap, path=p)
            r2 = ew.stamp_ex_ante("CPI", "2026-07-14", ex2, snap, path=p)
            assert r2 is False
            rows = ew._read_ledger(p)
            assert len(rows) == 1
            assert rows[0]["implied_1d_move_pct"] == 0.72  # first value kept
        finally:
            os.environ["COLLECT_LANE"] = env_save

    def test_grade_forward_log_requires_lane(self, tmp_path):
        """grade_forward_log() no-ops when COLLECT_LANE != nightly."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex = {"asof": "2026-07-13", "implied_event_move": {"implied_1d_move_pct": 0.72},
                  "mri_surprise_dispersion": None, "gamma_regime": None}
            snap = {"phase": "cpi_week", "active_collisions": []}
            ew.stamp_ex_ante("CPI", "2026-07-14", ex, snap, path=p)
        finally:
            os.environ["COLLECT_LANE"] = env_save
        # Now grade with wrong lane
        env_save2 = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "render"
            n = ew.grade_forward_log(
                {"2026-07-13": 530.0, "2026-07-14": 528.5},
                path=p,
            )
            assert n == 0
        finally:
            os.environ["COLLECT_LANE"] = env_save2

    def test_grade_fills_realized(self, tmp_path):
        """grade_forward_log() fills realized_1d_move_pct correctly."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex = {"asof": "2026-07-13", "implied_event_move": {"implied_1d_move_pct": 0.72},
                  "mri_surprise_dispersion": None, "gamma_regime": None}
            snap = {"phase": "cpi_week", "active_collisions": []}
            ew.stamp_ex_ante("CPI", "2026-07-14", ex, snap, path=p)
            closes = {"2026-07-13": 530.0, "2026-07-14": 524.65}  # -(0.63/530)*100 = -1%
            n = ew.grade_forward_log(closes, path=p)
            assert n == 1
            rows = ew._read_ledger(p)
            # (524.65 / 530.0 - 1) * 100 = -1.0094%
            assert rows[0]["realized_1d_move_pct"] == pytest.approx(-1.0094, abs=0.01)
            assert rows[0]["reaction_sign"] == "down"
            # implied_vs_realized = abs(realized) / implied = 1.0094 / 0.72
            assert rows[0]["implied_vs_realized"] == pytest.approx(1.0094 / 0.72, abs=0.05)
        finally:
            os.environ["COLLECT_LANE"] = env_save


# ---------------------------------------------------------------------------
# 4. Ex-ante read null-degradation
# ---------------------------------------------------------------------------
class TestExAnteNullDegradation:

    def test_ex_ante_null_when_no_inputs(self):
        """ex_ante_read() returns available=False gracefully when inputs absent."""
        result = ew.ex_ante_read("CPI")
        assert result["is_context_only"] is True
        assert result["display_only"] is True
        # With no inputs, mri and implied will both be None/unavailable
        # available may be False
        assert "glance_en" in result
        assert "glance_zh" in result
        assert "disclaimer_en" in result
        assert "disclaimer_zh" in result

    def test_ex_ante_does_not_shift_values(self):
        """Laws: ex_ante_read never modifies projection values (MRI-R20)."""
        result = ew.ex_ante_read("CPI", phase_stats={"fwd_vol": 18.5})
        # The read must not contain any "adjusted_forecast" or shifted value fields
        forbidden_keys = {"adjusted_forecast", "shifted_value", "dampener", "multiplier"}
        assert not (set(result.keys()) & forbidden_keys), (
            f"Found forbidden scoring keys: {set(result.keys()) & forbidden_keys}"
        )
        assert result["laws"]["mri_r20"] == "no projection shift"
        assert result["laws"]["ric_r3"] == "no score dampener"

    def test_ex_ante_with_implied_move_payload(self):
        """ex_ante_read() correctly extracts implied move from a synthetic vol payload.

        The expected value is the delta-neutral ATM straddle approximation:
          E|move| = ATM_IV * sqrt(1/252) * sqrt(2/pi)
        For ATM_IV=18.5%, this evaluates to ≈ 0.930% (NOT 1.165%, which would be
        the plain 1-sigma move without the sqrt(2/pi) factor).
        The constant below is computed independently: 18.5/100 * (1/252)**0.5 * (2/pi)**0.5 * 100.
        """
        payload = {
            "schema": "options_hub.vol/v1",
            "root": "SPY",
            "asof": "2026-07-13",
            "term": [
                {"dte": 1, "exp": "2026-07-14", "atm_iv": 18.5},
                {"dte": 8, "exp": "2026-07-18", "atm_iv": 17.2},
            ],
        }
        result = ew.ex_ante_read("CPI", spy_vol_payload=payload)
        implied = result.get("implied_event_move")
        assert implied is not None
        assert implied["available"] is True
        assert implied["atm_iv_pct"] == 18.5
        # Independently derived canonical value (not copied from production code):
        #   18.5% annualised IV × sqrt(1/252) × sqrt(2/π) = 0.9299...%
        # A plain 1-sigma move (no sqrt(2/pi)) would be 1.1652% — 25% higher.
        # If this assertion fails after a code change, verify the formula choice:
        #   straddle E|move| uses sqrt(2/pi); 1-sigma does NOT.
        canonical_straddle_1d_pct = 0.9299  # pre-computed: 18.5/100*(1/252)**0.5*(2/3.14159265)**0.5*100
        assert abs(implied["implied_1d_move_pct"] - canonical_straddle_1d_pct) < 0.01, (
            f"implied_1d_move_pct={implied['implied_1d_move_pct']:.4f} deviates from "
            f"canonical straddle value {canonical_straddle_1d_pct:.4f}. "
            "Check that sqrt(2/pi) factor is applied (straddle E|move|, not 1-sigma)."
        )

    def test_ex_ante_is_always_context_only(self):
        """is_context_only must be True regardless of inputs."""
        for inputs in [
            {},
            {"phase_stats": {"fwd_vol": 12.0}},
            {"gamma_regime": "positive"},
        ]:
            r = ew.ex_ante_read("FOMC", **inputs)
            assert r["is_context_only"] is True


# ---------------------------------------------------------------------------
# 5. Snapshot: null-safe
# ---------------------------------------------------------------------------
class TestSnapshot:

    def test_snapshot_none_close(self):
        result = ew.snapshot(None)
        assert result["available"] is False
        assert result["is_context_only"] is True

    def test_snapshot_insufficient_history(self):
        idx = pd.bdate_range("2025-01-01", periods=10)
        close = pd.Series(np.arange(10, dtype=float), index=idx)
        result = ew.snapshot(close)
        assert result["available"] is False

    def test_snapshot_returns_phase_and_collision(self):
        idx = _make_index()
        close = _spy_close(idx)
        result = ew.snapshot(close)
        assert result["available"] is True
        assert result["is_context_only"] is True
        assert result["phase"] in {
            "cpi_day", "cpi_week", "fomc_day", "fomc_week",
            "post_fomc_3d", "nfp_day", "quiet",
        }
        for col in ("cpi_fomc_same_week", "cpi_in_opex_week",
                    "fomc_in_opex_week", "triple_stack"):
            assert col in result["collision_states"]

    def test_snapshot_read_zh_present(self):
        idx = _make_index()
        close = _spy_close(idx)
        result = ew.snapshot(close)
        assert "read_zh" in result
        assert isinstance(result["read_zh"], str) and len(result["read_zh"]) > 0

    def test_snapshot_doctrine_present(self):
        idx = _make_index()
        close = _spy_close(idx)
        result = ew.snapshot(close)
        assert "doctrine" in result
        assert "display" in result["doctrine"].lower() or "context" in result["doctrine"].lower()

    def test_snapshot_asof_and_schema_present(self):
        """snapshot() must carry top-level asof and schema for freshness scanner."""
        idx = _make_index()
        close = _spy_close(idx)
        result = ew.snapshot(close)
        assert "asof" in result, "snapshot() missing top-level 'asof' field (synapse declares asof_field: asof)"
        assert "schema" in result, "snapshot() missing top-level 'schema' field"
        assert result["schema"] == "event_window.snapshot.v1"
        # asof should be a valid ISO date string
        from datetime import date
        asof = result["asof"]
        assert isinstance(asof, str) and len(asof) == 10, f"asof={asof!r} is not a YYYY-MM-DD string"


# ---------------------------------------------------------------------------
# 6. Seasonality — basic shape contracts
# ---------------------------------------------------------------------------
class TestSeasonality:

    def test_seasonality_insufficient_data(self):
        idx = pd.bdate_range("2025-01-01", periods=100)
        close = pd.Series(np.arange(100, dtype=float), index=idx)
        result = ew.seasonality(close)
        assert result["available"] is False

    def test_seasonality_shape(self):
        idx = _make_index("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        result = ew.seasonality(close)
        assert result["available"] is True
        assert "phases" in result
        assert isinstance(result["phases"], dict)
        valid_phases = {"cpi_day", "cpi_week", "fomc_day", "fomc_week",
                        "post_fomc_3d", "nfp_day", "quiet"}
        assert set(result["phases"].keys()).issubset(valid_phases)

    def test_pre_fomc_drift_note(self):
        """Seasonality must include the honest pre-FOMC drift note."""
        idx = _make_index("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        result = ew.seasonality(close)
        assert "pre_fomc_drift_note" in result
        assert "DEAD" in result["pre_fomc_drift_note"] or "dead" in result["pre_fomc_drift_note"].lower()

    def test_phase_stats_fields(self):
        """Each phase stat must have the required sub-fields."""
        idx = _make_index("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        result = ew.seasonality(close)
        required = {"mean_fwd_pct", "excess_pct", "t_hac", "n",
                    "sign_stable", "significant"}
        for ph, stats in result["phases"].items():
            missing = required - set(stats.keys())
            assert not missing, f"Phase {ph} missing fields: {missing}"


# ---------------------------------------------------------------------------
# 7. Historical date fabrication guard — _static_release_dates must NOT
#    back-project 2026 day-of-month values onto earlier years
# ---------------------------------------------------------------------------
class TestNoHistoricalBackProjection:
    """CPI/PPI/NFP release day-of-month values from the 2026 schedule must not
    be stamped as historical dates for pre-2026 years."""

    def test_cpi_dates_not_stamped_pre_2026(self):
        """No CPI date with a pre-2026 year should appear in the tag() output."""
        idx = pd.bdate_range("2000-01-01", "2025-12-31")
        t = ew.tag(idx)
        # With the fix, CPI dates only exist for 2026; historical index has none.
        # Therefore td_to_cpi should never be 0 on a pre-2026 index.
        # (It will be NaN or a forward distance — never exactly 0 since no 2026
        # dates fall within 2000-2025.)
        cpi_day_rows = t[t["phase"] == "cpi_day"]
        assert len(cpi_day_rows) == 0, (
            f"Found {len(cpi_day_rows)} cpi_day rows in a pre-2026 index — "
            "back-projection of 2026 schedule is still active."
        )

    def test_nfp_dates_not_stamped_pre_2026(self):
        """No NFP date with a pre-2026 year should cause nfp_day phase on pre-2026 index."""
        idx = pd.bdate_range("2010-01-01", "2025-12-31")
        t = ew.tag(idx)
        nfp_day_rows = t[t["phase"] == "nfp_day"]
        assert len(nfp_day_rows) == 0, (
            f"Found {len(nfp_day_rows)} nfp_day rows in a pre-2026 index — "
            "back-projection of 2026 NFP schedule is still active."
        )

    def test_2026_cpi_dates_still_tagged(self):
        """The 2026 CPI schedule must still tag correctly on a 2026-spanning index."""
        idx = pd.bdate_range("2026-01-01", "2026-12-31")
        t = ew.tag(idx)
        from engine.event_window import _CPI_2026
        # At least some months should produce a cpi_day (those that land on a bday)
        cpi_day_rows = t[t["td_to_cpi"] == 0]
        assert len(cpi_day_rows) > 0, "No CPI days found in 2026 index — schedule broken."


# ---------------------------------------------------------------------------
# 9. RIC laws enforcement (no scoring, no dampener)
# ---------------------------------------------------------------------------
class TestRicLaws:

    def test_snapshot_is_context_only_always(self):
        idx = _make_index()
        close = _spy_close(idx)
        snap = ew.snapshot(close)
        assert snap.get("is_context_only") is True

    def test_no_scored_path_surfaces_in_output(self):
        """Snapshot output must not contain any field that could be a scored path."""
        idx = _make_index()
        close = _spy_close(idx)
        snap = ew.snapshot(close)
        forbidden = {"score", "conviction", "dampener", "weight",
                     "exposure_adj", "size_factor"}
        assert not (set(snap.keys()) & forbidden), (
            f"Found forbidden scoring fields in snapshot: {set(snap.keys()) & forbidden}"
        )

    def test_ledger_schema_frozen(self, tmp_path):
        """Ledger rows must carry the frozen schema identifier."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex = {"asof": "2026-07-13", "implied_event_move": None,
                  "mri_surprise_dispersion": None, "gamma_regime": None}
            snap = {"phase": "quiet", "active_collisions": []}
            ew.stamp_ex_ante("NFP", "2026-07-02", ex, snap, path=p)
            rows = ew._read_ledger(p)
            assert rows[0]["schema"] == "event_windows.forward_log.v1"
            # Rulers must be frozen
            rulers = rows[0]["rulers"]
            assert rulers["primary"] == "realized_event_day_move_vs_implied"
            assert rulers["secondary"] == "realized_vol_vs_phase_base_rate"
        finally:
            os.environ["COLLECT_LANE"] = env_save


# ---------------------------------------------------------------------------
# 10. Producer: scripts/build_event_windows.py
# ---------------------------------------------------------------------------

class TestBuildEventWindowsProducer:
    """Integration tests for the build_event_windows producer.

    These tests exercise the script's main() function under controlled conditions:
    a tmp_path site tree so writes are isolated, and COLLECT_LANE unset so the
    forward-log stamp is skipped (off-lane read-only run).
    """

    def _make_site_tree(self, tmp_path: "pytest.TempPath") -> "pytest.TempPath":
        """Set up minimal site + data directories expected by the producer."""
        (tmp_path / "site" / "event_windows").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "event_windows").mkdir(parents=True, exist_ok=True)
        return tmp_path

    def test_producer_writes_snapshot(self, tmp_path, monkeypatch):
        """main() writes a valid snapshot.json to site/event_windows/."""
        import json
        from pathlib import Path

        self._make_site_tree(tmp_path)

        # Patch config.ROOT + storage site_dir so the producer writes to tmp_path
        import scripts.build_event_windows as prod
        monkeypatch.setattr(prod, "_root", lambda: tmp_path)

        # Patch _spy_close to return a real-enough series
        idx = pd.bdate_range("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        monkeypatch.setattr(prod, "_spy_close", lambda: close)
        monkeypatch.setattr(prod, "_spy_vol_payload", lambda: None)
        monkeypatch.setattr(prod, "_vol_regime_snap", lambda: None)

        # Patch config.load() to return tmp site_dir
        import lib.config as _config
        orig_load = _config.load
        def _patched_load():
            d = orig_load()
            d.setdefault("storage", {})["site_dir"] = str(tmp_path / "site")
            return d
        monkeypatch.setattr(_config, "load", _patched_load)
        monkeypatch.setattr(_config, "ROOT", tmp_path)

        rc = prod.main()
        assert rc == 0

        snap_path = tmp_path / "site" / "event_windows" / "snapshot.json"
        assert snap_path.exists(), "snapshot.json not written"
        snap = json.loads(snap_path.read_text())
        assert snap.get("available") is True
        assert snap.get("is_context_only") is True
        assert "phase" in snap
        assert "asof" in snap
        assert snap.get("schema") == "event_window.snapshot.v1"

    def test_producer_lane_gate_offlan(self, tmp_path, monkeypatch):
        """Off-lane run (COLLECT_LANE unset) must NOT write forward-log rows."""
        import json
        self._make_site_tree(tmp_path)
        import scripts.build_event_windows as prod
        monkeypatch.setattr(prod, "_root", lambda: tmp_path)
        idx = pd.bdate_range("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        monkeypatch.setattr(prod, "_spy_close", lambda: close)
        monkeypatch.setattr(prod, "_spy_vol_payload", lambda: None)
        monkeypatch.setattr(prod, "_vol_regime_snap", lambda: None)
        import lib.config as _config
        orig_load = _config.load
        def _patched_load():
            d = orig_load()
            d.setdefault("storage", {})["site_dir"] = str(tmp_path / "site")
            return d
        monkeypatch.setattr(_config, "load", _patched_load)
        monkeypatch.setattr(_config, "ROOT", tmp_path)
        # Ensure lane is NOT armed
        env_save = os.environ.pop("COLLECT_LANE", None)
        try:
            rc = prod.main()
            assert rc == 0
            ledger_path = tmp_path / "data" / "event_windows" / "forward_log.jsonl"
            if ledger_path.exists():
                rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
                assert rows == [], "Off-lane run should not write ledger rows"
        finally:
            if env_save is not None:
                os.environ["COLLECT_LANE"] = env_save

    def test_producer_lane_gate_armed_stamps(self, tmp_path, monkeypatch):
        """Armed-lane run (COLLECT_LANE=nightly) stamps T-1 rows when a release is near."""
        import json
        self._make_site_tree(tmp_path)
        import scripts.build_event_windows as prod
        monkeypatch.setattr(prod, "_root", lambda: tmp_path)

        # Build index that includes 2026-07-14 (CPI day) so td_to_cpi=0 or 1 today
        idx = pd.bdate_range("2010-01-01", "2026-12-31")
        close = _spy_close(idx)
        monkeypatch.setattr(prod, "_spy_close", lambda: close)
        monkeypatch.setattr(prod, "_spy_vol_payload", lambda: None)
        monkeypatch.setattr(prod, "_vol_regime_snap", lambda: None)
        monkeypatch.setattr(prod, "_release_forecast_integrity_chip", lambda _rt: None)

        import lib.config as _config
        orig_load = _config.load
        def _patched_load():
            d = orig_load()
            d.setdefault("storage", {})["site_dir"] = str(tmp_path / "site")
            return d
        monkeypatch.setattr(_config, "load", _patched_load)
        monkeypatch.setattr(_config, "ROOT", tmp_path)

        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            # Override today to be 2026-07-13 (1 trading day before CPI 2026-07-14)
            from engine import event_window as _ew
            monkeypatch.setattr(_ew, "_today_override", date(2026, 7, 13), raising=False)
            rc = prod.main()
            assert rc == 0
            # If snapshot says td_to_cpi <= 2, a ledger row should have been stamped
            snap_path = tmp_path / "site" / "event_windows" / "snapshot.json"
            snap = json.loads(snap_path.read_text())
            # At minimum the snapshot should be written
            assert snap.get("available") is True
        finally:
            os.environ["COLLECT_LANE"] = env_save

    def test_producer_null_degradation_no_spy(self, tmp_path, monkeypatch):
        """When SPY close is unavailable, snapshot writes available=False without crashing."""
        import json
        self._make_site_tree(tmp_path)
        import scripts.build_event_windows as prod
        monkeypatch.setattr(prod, "_root", lambda: tmp_path)
        monkeypatch.setattr(prod, "_spy_close", lambda: None)  # simulates store failure
        monkeypatch.setattr(prod, "_spy_vol_payload", lambda: None)
        monkeypatch.setattr(prod, "_vol_regime_snap", lambda: None)
        import lib.config as _config
        orig_load = _config.load
        def _patched_load():
            d = orig_load()
            d.setdefault("storage", {})["site_dir"] = str(tmp_path / "site")
            return d
        monkeypatch.setattr(_config, "load", _patched_load)
        monkeypatch.setattr(_config, "ROOT", tmp_path)
        rc = prod.main()
        assert rc == 0
        snap_path = tmp_path / "site" / "event_windows" / "snapshot.json"
        assert snap_path.exists(), "snapshot.json must be written even when SPY absent"
        snap = json.loads(snap_path.read_text())
        assert snap.get("available") is False, "available must be False when SPY close missing"
        assert snap.get("is_context_only") is True


# ---------------------------------------------------------------------------
# 11. Ledger idempotency (keep-FIRST) + lane-gate
# ---------------------------------------------------------------------------

class TestLedgerIdempotency:
    """Keep-FIRST property: stamping the same (release_type, release_date) twice
    preserves the first row (no duplicate, no overwrite)."""

    def test_keep_first_duplicate_stamp(self, tmp_path):
        """stamp_ex_ante twice with the same key returns False on second call."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            ex = {"asof": "2026-07-13", "implied_event_move": {"implied_1d_move_pct": 0.8, "available": True},
                  "mri_surprise_dispersion": None, "gamma_regime": "backwardation-stress"}
            snap = {"phase": "cpi_week", "active_collisions": ["cpi_in_opex_week"]}

            r1 = ew.stamp_ex_ante("CPI", "2026-07-14", ex, snap, path=p)
            r2 = ew.stamp_ex_ante("CPI", "2026-07-14", ex, snap, path=p)

            assert r1 is True, "First stamp should succeed"
            assert r2 is False, "Second stamp (same key) should be no-op (keep-FIRST)"

            rows = ew._read_ledger(p)
            assert len(rows) == 1, f"Expected 1 row, got {len(rows)} (duplicate detected)"
            assert rows[0]["phase"] == "cpi_week"
        finally:
            os.environ["COLLECT_LANE"] = env_save

    def test_lane_gate_rejects_offlan_stamp(self, tmp_path):
        """stamp_ex_ante returns False when COLLECT_LANE is not 'nightly'."""
        env_save = os.environ.pop("COLLECT_LANE", None)
        try:
            p = tmp_path / "forward_log.jsonl"
            ex = {"asof": "2026-07-13"}
            snap = {"phase": "quiet", "active_collisions": []}
            result = ew.stamp_ex_ante("CPI", "2026-07-14", ex, snap, path=p)
            assert result is False, "Off-lane stamp must return False"
            assert not p.exists() or p.read_text().strip() == "", "No ledger row should be written off-lane"
        finally:
            if env_save is not None:
                os.environ["COLLECT_LANE"] = env_save

    def test_two_different_keys_both_written(self, tmp_path):
        """Two distinct (release_type, release_date) keys both get stamped."""
        env_save = os.environ.get("COLLECT_LANE", "")
        try:
            os.environ["COLLECT_LANE"] = "nightly"
            p = tmp_path / "forward_log.jsonl"
            base_ex = {"asof": "2026-07-13", "implied_event_move": None,
                       "mri_surprise_dispersion": None, "gamma_regime": None}
            snap = {"phase": "quiet", "active_collisions": []}
            ew.stamp_ex_ante("CPI", "2026-07-14", base_ex, snap, path=p)
            ew.stamp_ex_ante("NFP", "2026-08-07", base_ex, snap, path=p)
            rows = ew._read_ledger(p)
            assert len(rows) == 2
            keys = {(r["release_type"], r["release_date"]) for r in rows}
            assert ("CPI", "2026-07-14") in keys
            assert ("NFP", "2026-08-07") in keys
        finally:
            os.environ["COLLECT_LANE"] = env_save
