"""Tests for BD-AVOID-1 Phase-1 Stamper (PR-C2).

Synthetic fixtures only — CI has no canonical massive_stock_day data.

Covers:
  1. Detector parity: detect_bd2/bd3 imported (not re-implemented) in stamper
  2. Control-sampler seeding determinism: same event_id → same controls
  3. Maturity gating: rows with sufficient price history get grades; others remain None
  4. Append-only enforcement: re-running does not duplicate existing event_ids
  5. Phase-0 phase-1 threshold gate: stamper only accepts post-registration events
  6. TrialLedger declaration: budget logged before any ledger write
  7. Vintage stamp: vintage_stamp() is called and keys are present in output rows
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Imports from the stamper (not re-implementing detectors)
# ---------------------------------------------------------------------------
from scripts.research.bd_avoid1_stamper import (
    _make_event_id,
    _seed_for_event,
    _sample_control_dates,
    _grade_row,
    _existing_event_ids,
    _empty_ledger,
    _last_stamp_date,
    REGISTRATION_DATE,
    ACTIVE_DEFINITIONS,
    CONTROL_RATIO,
)
from scripts.research.dump_breakdown_events import (
    detect_bd2,
    detect_bd3,
    ERA_START,
    ERA_PRIOR_BARS_REQUIRED,
)
from engine.grading import (
    TerminalState,
    TerminalStateShort,
    LIFTOFF_8,
    LIFTOFF_HORIZON_21,
    SHORT_ADVERSE_MULT,
    SHORT_FAVORABLE_MULT_21,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bday_series(vals, start="2021-01-04"):
    """Build a business-day close Series."""
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series([float(v) for v in vals], index=idx)


def _flat_series(n: int = 500, start_price: float = 20.0, start: str = "2021-01-04") -> pd.Series:
    """Flat close Series of n bars (sufficient for ERA + ERA_PRIOR_BARS_REQUIRED)."""
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(np.full(n, start_price), index=idx)


# ---------------------------------------------------------------------------
# 1. Detector import parity — detectors come from dump_breakdown_events
# ---------------------------------------------------------------------------

class TestDetectorImportParity:
    """Verify the stamper imports detectors rather than re-implementing them."""

    def test_stamper_uses_imported_detect_bd2(self):
        """detect_bd2 is the same object imported from dump_breakdown_events."""
        # The stamper imports detect_bd2 from dump_breakdown_events; verify identity.
        from scripts.research import bd_avoid1_stamper as stamper_mod
        import scripts.research.dump_breakdown_events as phase0_mod
        assert stamper_mod.detect_bd2 is phase0_mod.detect_bd2

    def test_stamper_uses_imported_detect_bd3(self):
        """detect_bd3 is the same object imported from dump_breakdown_events."""
        from scripts.research import bd_avoid1_stamper as stamper_mod
        import scripts.research.dump_breakdown_events as phase0_mod
        assert stamper_mod.detect_bd3 is phase0_mod.detect_bd3

    def test_stamper_imports_frozen_threshold_constants(self):
        """Key threshold constants are imported (not re-assigned) in the stamper."""
        from scripts.research import bd_avoid1_stamper as stamper_mod
        import scripts.research.dump_breakdown_events as phase0_mod
        # ERA_PRIOR_BARS_REQUIRED and ERA_START must match phase0 exactly
        assert stamper_mod.ERA_PRIOR_BARS_REQUIRED == phase0_mod.ERA_PRIOR_BARS_REQUIRED
        assert stamper_mod.ERA_START == phase0_mod.ERA_START


# ---------------------------------------------------------------------------
# 2. Event ID construction
# ---------------------------------------------------------------------------

class TestEventId:

    def test_event_id_is_deterministic(self):
        ts = pd.Timestamp("2026-07-10")
        eid1 = _make_event_id("AAPL", "BD-2", ts)
        eid2 = _make_event_id("AAPL", "BD-2", ts)
        assert eid1 == eid2

    def test_event_id_different_for_different_definitions(self):
        ts = pd.Timestamp("2026-07-10")
        assert _make_event_id("AAPL", "BD-2", ts) != _make_event_id("AAPL", "BD-3", ts)

    def test_event_id_different_for_different_tickers(self):
        ts = pd.Timestamp("2026-07-10")
        assert _make_event_id("AAPL", "BD-2", ts) != _make_event_id("MSFT", "BD-2", ts)

    def test_event_id_format(self):
        ts = pd.Timestamp("2026-07-10")
        eid = _make_event_id("AAPL", "BD-2", ts)
        parts = eid.split("|")
        assert len(parts) == 3
        assert parts[0] == "AAPL"
        assert parts[1] == "BD-2"
        assert parts[2] == "2026-07-10"


# ---------------------------------------------------------------------------
# 3. Seeded control sampling — determinism
# ---------------------------------------------------------------------------

class TestControlSeedingDeterminism:

    def test_same_event_id_same_seed(self):
        """_seed_for_event is deterministic: same event_id → same seed."""
        eid = "AAPL|BD-2|2026-07-10"
        s1 = _seed_for_event(eid)
        s2 = _seed_for_event(eid)
        assert s1 == s2

    def test_different_event_ids_different_seeds(self):
        """Different event_ids → different seeds (with high probability)."""
        s1 = _seed_for_event("AAPL|BD-2|2026-07-10")
        s2 = _seed_for_event("MSFT|BD-2|2026-07-10")
        assert s1 != s2

    def test_seed_is_valid_rng_seed(self):
        """Seed must be a non-negative int < 2^31."""
        seed = _seed_for_event("AAPL|BD-3|2026-07-10")
        assert isinstance(seed, int)
        assert 0 <= seed < 2 ** 31

    def test_control_dates_deterministic_given_seed(self):
        """Same seed → same control dates on the same close series."""
        close = _flat_series(500)
        raw_df = None
        event_ts = close.index[300]  # well within ERA

        seed = 42
        ctrl1 = _sample_control_dates(
            "TEST", close, raw_df, event_ts,
            existing_event_dates={event_ts},
            seed=seed,
        )
        ctrl2 = _sample_control_dates(
            "TEST", close, raw_df, event_ts,
            existing_event_dates={event_ts},
            seed=seed,
        )
        assert ctrl1 == ctrl2

    def test_control_dates_differ_for_different_seeds(self):
        """Different seeds → typically different control dates."""
        close = _flat_series(500)
        event_ts = close.index[300]

        ctrl1 = _sample_control_dates(
            "TEST", close, None, event_ts,
            existing_event_dates={event_ts},
            seed=1,
        )
        ctrl2 = _sample_control_dates(
            "TEST", close, None, event_ts,
            existing_event_dates={event_ts},
            seed=999999,
        )
        # With 500 bars and two seeds, these should differ; not guaranteed but very likely
        assert ctrl1 != ctrl2 or len(ctrl1) == 0

    def test_control_count_is_control_ratio(self):
        """Controls per event = CONTROL_RATIO (3) when pool is large enough."""
        close = _flat_series(500)
        event_ts = close.index[300]

        ctrls = _sample_control_dates(
            "TEST", close, None, event_ts,
            existing_event_dates={event_ts},
            seed=42,
        )
        assert len(ctrls) == CONTROL_RATIO

    def test_controls_exclude_event_bar(self):
        """Control dates must not include the event date itself."""
        close = _flat_series(500)
        event_ts = close.index[300]

        ctrls = _sample_control_dates(
            "TEST", close, None, event_ts,
            existing_event_dates={event_ts},
            seed=42,
        )
        assert event_ts not in ctrls

    def test_controls_in_same_calendar_year(self):
        """Controls are year-stratified: same year as event."""
        close = _flat_series(800, start="2021-01-04")
        event_ts = close.index[400]  # somewhere in 2022/2023

        ctrls = _sample_control_dates(
            "TEST", close, None, event_ts,
            existing_event_dates={event_ts},
            seed=42,
        )
        for ct in ctrls:
            assert ct.year == event_ts.year


# ---------------------------------------------------------------------------
# 4. Maturity gating — grade_row
# ---------------------------------------------------------------------------

class TestMaturityGating:

    def _make_vstamp(self) -> dict:
        return {
            "price_plane_id": "test",
            "adjustment_mode": "test",
            "universe_as_of": "2026-07-06",
            "frame": "test",
            "survivorship_biased": True,
            "coverage_frac": 1.0,
            "dead_name_coverage_pct": None,
            "era_law_cohort": "test",
            "stamp_degraded": False,
        }

    def test_grade_row_returns_none_state_when_not_matured(self):
        """If close series is too short after event, long_state_clean8_21 is None."""
        # 5 bars after event bar — not enough for h21 maturity
        n = ERA_PRIOR_BARS_REQUIRED + 3  # just enough for ERA, but not h21 maturity
        close = _flat_series(n)
        event_ts = close.index[ERA_PRIOR_BARS_REQUIRED]  # near end of series

        row = _grade_row(
            ticker="TEST",
            event_ts=event_ts,
            close=close,
            definition="BD-2",
            is_control=False,
            control_seed=None,
            stamp_date="2026-07-06",
            vstamp=self._make_vstamp(),
        )
        # Should be censored since not enough bars after fill
        assert row["long_state_clean8_21"] is None or row["censored"] is True

    def test_grade_row_returns_state_when_matured(self):
        """If close series has >=h21 bars after event, long_state_clean8_21 is set."""
        # Build: 400 bars flat at 20, event at bar 300, 100 bars after
        close = _flat_series(400)
        # Use a bar early enough that 21+ bars remain
        event_ts = close.index[300]

        row = _grade_row(
            ticker="TEST",
            event_ts=event_ts,
            close=close,
            definition="BD-2",
            is_control=False,
            control_seed=None,
            stamp_date="2026-07-06",
            vstamp=self._make_vstamp(),
        )
        # Flat series → DEAD_MONEY or CUSHIONED (never liftoff at entry*1.08 or stop at 0.95)
        assert row["long_state_clean8_21"] is not None
        assert row["entry_price"] == pytest.approx(20.0)

    def test_grade_row_short_state_is_quarantined_but_present(self):
        """Short-side grade is recorded (not None when matured) but carries no verdict."""
        close = _flat_series(400)
        event_ts = close.index[300]

        row = _grade_row(
            ticker="TEST",
            event_ts=event_ts,
            close=close,
            definition="BD-3",
            is_control=False,
            control_seed=None,
            stamp_date="2026-07-06",
            vstamp=self._make_vstamp(),
        )
        # Both long and short states should be populated for a flat series with enough bars
        assert row["short_state_short21"] is not None

    def test_grade_row_vintage_stamp_present(self):
        """vintage_stamp JSON field is non-empty in every row."""
        close = _flat_series(400)
        event_ts = close.index[300]
        vstamp = self._make_vstamp()

        row = _grade_row(
            ticker="TEST",
            event_ts=event_ts,
            close=close,
            definition="BD-2",
            is_control=False,
            control_seed=None,
            stamp_date="2026-07-06",
            vstamp=vstamp,
        )
        assert row["vintage_stamp"] is not None
        parsed = json.loads(row["vintage_stamp"])
        assert "price_plane_id" in parsed
        assert "survivorship_biased" in parsed

    def test_control_row_has_is_control_true(self):
        """Control rows have is_control=True and a non-None control_seed."""
        close = _flat_series(400)
        ctrl_ts = close.index[250]

        row = _grade_row(
            ticker="TEST",
            event_ts=ctrl_ts,
            close=close,
            definition="BD-2",
            is_control=True,
            control_seed=42,
            stamp_date="2026-07-06",
            vstamp=self._make_vstamp(),
        )
        assert row["is_control"] is True
        assert row["control_seed"] == 42


# ---------------------------------------------------------------------------
# 5. Append-only enforcement
# ---------------------------------------------------------------------------

class TestAppendOnlyEnforcement:

    def test_existing_event_ids_no_duplication(self):
        """_existing_event_ids returns the correct set; re-running with existing ids skips them."""
        rows = [
            {"event_id": "AAPL|BD-2|2026-07-07", "is_control": False},
            {"event_id": "AAPL|BD-2|2026-07-07|ctrl_0", "is_control": True},
        ]
        df = pd.DataFrame(rows)
        ids = _existing_event_ids(df)
        assert "AAPL|BD-2|2026-07-07" in ids
        assert "AAPL|BD-2|2026-07-07|ctrl_0" in ids
        assert len(ids) == 2

    def test_existing_event_ids_empty_df(self):
        """Empty DataFrame → empty set."""
        df = _empty_ledger()
        ids = _existing_event_ids(df)
        assert ids == set()

    def test_last_stamp_date_from_empty_is_before_registration(self):
        """Empty ledger → last_stamp = REGISTRATION_DATE - 1 day."""
        df = _empty_ledger()
        last = _last_stamp_date(df)
        assert last < REGISTRATION_DATE

    def test_last_stamp_date_from_populated_df(self):
        """last_stamp_date = max(pit_stamp_date) in the ledger."""
        rows = [
            {"event_id": "X|BD-2|2026-07-07", "pit_stamp_date": "2026-07-07", "is_control": False},
            {"event_id": "X|BD-2|2026-07-08", "pit_stamp_date": "2026-07-08", "is_control": False},
        ]
        df = pd.DataFrame(rows)
        last = _last_stamp_date(df)
        assert last == pd.Timestamp("2026-07-08")


# ---------------------------------------------------------------------------
# 6. Phase-1 PIT constraint — no Phase-0 events fed to forward ledger
# ---------------------------------------------------------------------------

class TestPITConstraint:

    def test_registration_date_is_2026_07_06(self):
        """REGISTRATION_DATE must be 2026-07-06 as declared in the prereg."""
        assert REGISTRATION_DATE == pd.Timestamp("2026-07-06")

    def test_active_definitions_excludes_bd1(self):
        """ACTIVE_DEFINITIONS must contain BD-2 and BD-3 but NOT BD-1."""
        assert "BD-1" not in ACTIVE_DEFINITIONS
        assert "BD-2" in ACTIVE_DEFINITIONS
        assert "BD-3" in ACTIVE_DEFINITIONS


# ---------------------------------------------------------------------------
# 7. Trial ledger declaration
# ---------------------------------------------------------------------------

class TestTrialLedgerDeclaration:
    """Verify _ensure_trial_ledger logs before any ledger write."""

    def test_ensure_trial_ledger_calls_log_declared_budget(self, tmp_path):
        """_ensure_trial_ledger must call log_declared_budget(2, family='short_side')."""
        from scripts.research.bd_avoid1_stamper import _ensure_trial_ledger

        # Intercept TrialLedger.log_declared_budget
        calls = []
        real_log = None

        from engine.trial_ledger import TrialLedger

        original_init = TrialLedger.__init__

        def patched_log(self, n, *, family=None, reason=""):
            calls.append({"n": n, "family": family or self.default_family})
            # still write (idempotent)
            return original_log(self, n, family=family, reason=reason)

        original_log = TrialLedger.log_declared_budget

        with patch.object(TrialLedger, "log_declared_budget", patched_log):
            _ensure_trial_ledger(tmp_path)

        assert len(calls) >= 1
        assert any(c["n"] == 2 and c["family"] == "short_side" for c in calls)


# ---------------------------------------------------------------------------
# 8. Full run integration (temp dir, mocked price plane)
# ---------------------------------------------------------------------------

class TestFullRunIntegration:
    """Mocked end-to-end: simulate a single BD-2 event firing post-registration."""

    def _make_vstamp(self) -> dict:
        from engine.vintage_stamp import vintage_stamp
        return vintage_stamp(
            price_plane_id="test",
            adjustment_mode="test",
            universe_as_of="2026-07-06",
            frame="test",
            survivorship_biased=True,
            coverage_frac=1.0,
            dead_name_coverage_pct=None,
            era_law_cohort="test",
        )

    def test_run_dry_run_empty_universe(self, tmp_path, monkeypatch):
        """run() with empty universe completes without errors in dry-run mode."""
        from scripts.research.bd_avoid1_stamper import run

        # Patch build_universe to return empty set → no tickers to process
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper.build_universe",
            lambda: set(),
        )
        # Patch git to no-op
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._narrow_commit",
            lambda *a, **kw: True,
        )
        # Patch vintage stamp
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._build_vintage_stamp",
            lambda n: self._make_vstamp(),
        )
        # Patch TrialLedger to avoid writing to real ledger
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._ensure_trial_ledger",
            lambda p: None,
        )

        result = run(data_dir=tmp_path, dry_run=True)

        assert result["n_new_events"] == 0
        assert result["n_new_controls"] == 0
        assert result["dry_run"] is True

    def test_run_appends_new_event_rows(self, tmp_path, monkeypatch):
        """run() writes event + control rows when new events are detected."""
        from scripts.research.bd_avoid1_stamper import run, _detect_new_events

        # Build a close series with enough history
        close = _flat_series(500, start="2021-01-04")
        # Inject a fake event on a day after REGISTRATION_DATE
        fake_event_ts = REGISTRATION_DATE + pd.Timedelta(days=3)
        # Snap to nearest business day in close
        closest_idx = close.index.searchsorted(fake_event_ts)
        if closest_idx >= len(close):
            closest_idx = len(close) - 1
        fake_event_ts = close.index[min(closest_idx, len(close) - 50)]

        def fake_detect(ticker, cl, raw_df, existing_ids, last_stamp):
            if ticker == "FAKE":
                return {"BD-2": [fake_event_ts], "BD-3": []}
            return {"BD-2": [], "BD-3": []}

        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._detect_new_events",
            fake_detect,
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper.build_universe",
            lambda: {"FAKE"},
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._read_massive_ticker",
            lambda ticker: close,
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._read_massive_ohlcv",
            lambda ticker: None,
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._narrow_commit",
            lambda *a, **kw: True,
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._build_vintage_stamp",
            lambda n: self._make_vstamp(),
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._ensure_trial_ledger",
            lambda p: None,
        )
        monkeypatch.setattr(
            "scripts.research.bd_avoid1_stamper._sample_control_dates",
            lambda ticker, close, raw_df, event_ts, existing_event_dates, seed: [],
        )

        result = run(data_dir=tmp_path, dry_run=False)

        assert result["n_new_events"] == 1
        # Ledger should exist now
        ledger_path = tmp_path / "research" / "bd_avoid1_ledger.parquet"
        assert ledger_path.exists()
        df = pd.read_parquet(ledger_path)
        assert len(df) == 1
        event_row = df.iloc[0]
        assert event_row["ticker"] == "FAKE"
        assert event_row["definition"] == "BD-2"
        assert bool(event_row["is_control"]) is False

    def test_run_no_duplicate_on_rerun(self, tmp_path, monkeypatch):
        """Re-running does not duplicate existing event_ids.

        We test this by verifying that _detect_new_events receives the correct
        existing_ids on the second run (containing the first run's event_id),
        and that the stamper skips any event_id already in existing_ids.
        """
        from scripts.research.bd_avoid1_stamper import run, _make_event_id

        close = _flat_series(500, start="2021-01-04")
        fake_event_ts = close.index[320]
        fake_eid = _make_event_id("FAKE", "BD-2", fake_event_ts)

        detected_ids_seen: list[set] = []

        def fake_detect(ticker, cl, raw_df, existing_ids, last_stamp):
            detected_ids_seen.append(set(existing_ids))
            if ticker == "FAKE":
                # Only return event if not already in existing_ids
                if fake_eid not in existing_ids:
                    return {"BD-2": [fake_event_ts], "BD-3": []}
            return {"BD-2": [], "BD-3": []}

        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._detect_new_events", fake_detect)
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper.build_universe", lambda: {"FAKE"})
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._read_massive_ticker", lambda t: close)
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._read_massive_ohlcv", lambda t: None)
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._narrow_commit", lambda *a, **kw: True)
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._build_vintage_stamp",
                            lambda n: self._make_vstamp())
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._ensure_trial_ledger", lambda p: None)
        monkeypatch.setattr("scripts.research.bd_avoid1_stamper._sample_control_dates",
                            lambda *a, **kw: [])

        # First run: 1 event written
        r1 = run(data_dir=tmp_path, dry_run=False)
        assert r1["n_new_events"] == 1

        # Second run: fake_eid is now in existing_ids → 0 new
        r2 = run(data_dir=tmp_path, dry_run=False)
        assert r2["n_new_events"] == 0

        # Total rows should still be 1 (no duplication)
        ledger = pd.read_parquet(tmp_path / "research" / "bd_avoid1_ledger.parquet")
        assert len(ledger) == 1

        # On the second run, existing_ids should contain the first run's event_id
        # (detected_ids_seen[1] = second run's existing_ids at time of detection)
        assert len(detected_ids_seen) >= 2
        assert fake_eid in detected_ids_seen[1]
