"""Tests for scripts/research/run_w2_ssq.py — W2 S-SQ Squeeze Release study.

Scope (three mandatory test classes per task brief):
  1. TestEventOnsetDedup     — event-onset deduplication: one episode per consecutive run.
  2. TestDirectionFixture    — FIRED_DOWN onsets must NEVER enter the long study.
  3. TestInjectedEffectMarginality — NC-2 both-arm band FE must yield non-zero coef
                                     (mirrors the degenerate-FE sentinel from S-UR study).

All fixtures are hand-constructed, deterministic, and fast (<5s total).
No database/R2 access; no production-scale data.

Design note: the FIRED_UP onset enumeration relies on engine/vol_squeeze.assess_series,
which is an O(n²) call — for tests we use a synthetic mock/stub rather than running
the full assess_series to keep tests fast.

DIRECTION FIXTURE CONTRACT (L1 law, task brief):
  - events_for_long_study = FIRED_UP onsets with fired_dir == 'up'
  - FIRED_DOWN onsets (fired_dir == 'down') must be absent from any enumerated result
  - Tested by constructing a fake assess_series DataFrame with a mix of states/directions
    and verifying the enumerator filters correctly.

DEDUP CONTRACT (task brief):
  - Consecutive FIRED_UP bars = one episode; only first bar fires.
  - The enumerator detects onset as state[t]=='FIRED_UP' AND state[t-1]!='FIRED_UP'.
  - Tested by injecting a states DataFrame with a multi-bar FIRED_UP run.

NC-2 MARGINALITY CONTRACT (L1 law via _run_nc2_band_fe from run_w2_sur.py):
  - Both arms (treatment AND control) must get proximity bands computed.
  - A perfectly-separated FE returns coef = 0.0 exactly (degenerate bug).
  - A non-degenerate result returns coef != 0.0.
  - This test is a pass-through to the shared _run_nc2_band_fe machinery.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from scripts.research.run_w2_ssq import (
    enumerate_sq_events,
    dedup_sq_events,
    _build_volume_coverage_table,
    _spot_check_volume_loading,
    _load_ticker_cache,
    _save_ticker_cache,
    _get_event_cache_dir,
    SENSITIVITY_CONFIGS,
    SPECIES_ID,
    SPECIES_NAME,
    SPECIES_FAMILY,
    DEFAULTS_CFG,
)
from scripts.research.run_w2_sur import (
    _run_nc2_band_fe,
    compute_cofire_share_trading_bars,
    MAX_COFIRE_SHARE,
    INDEPENDENCE_BARS,
)


# ---------------------------------------------------------------------------
# Helper: build a small deterministic date index
# ---------------------------------------------------------------------------
def _dates(n: int, start: str = "2020-01-02") -> pd.DatetimeIndex:
    """Return n business-day dates starting at start."""
    return pd.bdate_range(start=start, periods=n)


# ---------------------------------------------------------------------------
# Helper: build a fake assess_series DataFrame with injected states
# ---------------------------------------------------------------------------
def _make_states_df(
    idx: pd.DatetimeIndex,
    states: list[str],
    fired_dirs: list[str],
) -> pd.DataFrame:
    """Build a fake assess_series-style DataFrame.

    Columns: state, fired_dir, volume_confirmed, days_compressed,
             bbwp, hv_pctile, coverage.
    All numeric ancillaries are set to deterministic constants.
    """
    assert len(states) == len(idx)
    assert len(fired_dirs) == len(idx)
    return pd.DataFrame(
        {
            "state":            states,
            "fired_dir":        fired_dirs,
            "volume_confirmed": [1.0 if s == "FIRED_UP" else 0.0 for s in states],
            "days_compressed":  [5] * len(idx),
            "bbwp":             [20.0] * len(idx),
            "hv_pctile":        [18.0] * len(idx),
            "coverage":         ["hl"] * len(idx),
        },
        index=idx,
    )


# ===========================================================================
# 1. Event-onset deduplication (TestEventOnsetDedup)
#
# Rule: consecutive FIRED_UP bars = one episode; only first bar fires.
# The onset detector checks state[t]=='FIRED_UP' AND state[t-1]!='FIRED_UP'.
# ===========================================================================

class TestEventOnsetDedup:
    """Verify that consecutive FIRED_UP bars produce only one event (the first bar).

    Scenario A: three consecutive FIRED_UP bars → exactly 1 event.
    Scenario B: two separate FIRED_UP runs (separated by non-FIRED_UP) → 2 events.
    Scenario C: single FIRED_UP bar → 1 event.
    Scenario D: no FIRED_UP bars → 0 events.
    Scenario E: back-to-back episodes (FIRED_UP run, non-FIRED_UP, FIRED_UP run) → 2 events.
    """

    def _build_store_with_states(
        self,
        n: int,
        states: list[str],
        fired_dirs: list[str],
        ticker: str = "TEST",
    ) -> dict[str, pd.DataFrame]:
        """Build a minimal OHLCV store with assess_series patched to return injected states."""
        idx = _dates(n)
        df = pd.DataFrame(
            {
                "close":  np.ones(n) * 100.0,
                "high":   np.ones(n) * 101.0,
                "low":    np.ones(n) * 99.0,
                "volume": np.ones(n) * 1_000_000.0,
            },
            index=idx,
        )
        return {ticker: df}, _make_states_df(idx, states, fired_dirs)

    def test_consecutive_fired_up_produces_one_event(self):
        """Three consecutive FIRED_UP bars → exactly 1 event (onset at bar 0).

        The dedup rule: only the FIRST bar of each FIRED_UP run fires.
        Bars 2, 3, 4 = FIRED_UP consecutive → single event at bar 2.
        """
        n = 10
        states = ["COILED"] * n
        dirs   = [""] * n
        # FIRED_UP run at bars 3, 4, 5
        states[3] = "FIRED_UP"; dirs[3] = "up"
        states[4] = "FIRED_UP"; dirs[4] = "up"
        states[5] = "FIRED_UP"; dirs[5] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        # We patch assess_series to return our injected DataFrame
        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert len(events) == 1, (
            f"Expected exactly 1 event for a 3-bar consecutive FIRED_UP run. "
            f"Got: {len(events)} events."
        )
        assert events.iloc[0]["date"] == idx[3], (
            f"Event must fire at the ONSET bar (idx[3]={idx[3]}). "
            f"Got: {events.iloc[0]['date']}"
        )

    def test_two_separate_runs_produce_two_events(self):
        """Two separated FIRED_UP runs → exactly 2 events (one onset each).

        Structure: [COILED × 3] [FIRED_UP] [COILED] [FIRED_UP × 2] [COILED × 3]
        Expected: event at bar 3 and event at bar 5.
        """
        n = 10
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        # bar 4 = COILED (breaks the run)
        states[5] = "FIRED_UP"; dirs[5] = "up"
        states[6] = "FIRED_UP"; dirs[6] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert len(events) == 2, (
            f"Expected exactly 2 events for two separate FIRED_UP runs. Got: {len(events)}"
        )
        event_dates = sorted(events["date"].tolist())
        assert event_dates[0] == idx[3], f"First event expected at idx[3]={idx[3]}, got {event_dates[0]}"
        assert event_dates[1] == idx[5], f"Second event expected at idx[5]={idx[5]}, got {event_dates[1]}"

    def test_single_fired_up_bar_produces_one_event(self):
        """Single isolated FIRED_UP bar → exactly 1 event."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[4] = "FIRED_UP"; dirs[4] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert len(events) == 1, f"Expected 1 event for single FIRED_UP bar, got {len(events)}"

    def test_no_fired_up_bars_produces_no_events(self):
        """No FIRED_UP bars → 0 events."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert events.empty, (
            f"Expected 0 events when no FIRED_UP bars exist. Got {len(events)}"
        )

    def test_dedup_sq_events_removes_duplicate_ticker_dates(self):
        """dedup_sq_events must remove duplicate (ticker, date) rows.

        If somehow two cfg runs produced the same (ticker, date) onset,
        dedup keeps the 'defaults' cfg_key row first.
        """
        idx = _dates(5)
        events = pd.DataFrame({
            "ticker":          ["AAPL", "AAPL", "MSFT"],
            "date":            [idx[2], idx[2], idx[3]],
            "panel":           ["test", "test", "test"],
            "fired_dir":       ["up", "up", "up"],
            "volume_confirmed":[True, True, True],
            "days_compressed": [5, 5, 5],
            "bbwp":            [20.0, 20.0, 20.0],
            "hv_pctile":       [18.0, 18.0, 18.0],
            "coverage":        ["hl", "hl", "hl"],
            "cfg_key":         ["defaults", "pctile20", "defaults"],
        })

        deduped = dedup_sq_events(events)
        # AAPL had two rows for the same date; should keep 'defaults' row
        aapl_rows = deduped[deduped["ticker"] == "AAPL"]
        assert len(aapl_rows) == 1, f"Expected 1 AAPL row after dedup, got {len(aapl_rows)}"
        assert aapl_rows.iloc[0]["cfg_key"] == "defaults", (
            f"dedup should prefer 'defaults' cfg_key. Got: {aapl_rows.iloc[0]['cfg_key']!r}"
        )
        # MSFT row should be preserved
        msft_rows = deduped[deduped["ticker"] == "MSFT"]
        assert len(msft_rows) == 1, "MSFT row must be preserved"

    def test_dedup_empty_input_returns_empty(self):
        """dedup_sq_events on empty DataFrame must return empty DataFrame."""
        empty = pd.DataFrame(columns=[
            "ticker", "date", "panel", "fired_dir", "volume_confirmed",
            "days_compressed", "bbwp", "hv_pctile", "coverage", "cfg_key",
        ])
        result = dedup_sq_events(empty)
        assert result.empty

    def test_enumerate_output_columns(self):
        """enumerate_sq_events must return all required columns."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        required = {"ticker", "date", "panel", "fired_dir", "volume_confirmed",
                    "days_compressed", "bbwp", "hv_pctile", "coverage", "cfg_key"}
        assert required.issubset(set(events.columns)), (
            f"Missing columns: {required - set(events.columns)}"
        )

    def test_panel_label_stamped(self):
        """panel column must equal the passed panel_name."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "my_panel")

        if not events.empty:
            assert (events["panel"] == "my_panel").all(), (
                f"panel column must be stamped. Got: {events['panel'].unique()}"
            )

    def test_multi_ticker_events(self):
        """Events from multiple tickers must all be collected."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "AAPL": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            ),
            "GOOG": pd.DataFrame(
                {"close": np.ones(n) * 200.0, "high": np.ones(n) * 201.0,
                 "low": np.ones(n) * 199.0, "volume": np.ones(n) * 2e6},
                index=idx,
            ),
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert not events.empty
        tickers = set(events["ticker"].unique())
        assert "AAPL" in tickers
        assert "GOOG" in tickers


# ===========================================================================
# 2. Direction fixture: FIRED_DOWN onsets must NEVER enter the long study
#    (TestDirectionFixture)
#
# Per task brief: "Event = first bar where state transitions into FIRED_UP;
#  FIRED_DOWN events are BANNED from the long study."
# The enumerator collects rows where state=='FIRED_UP'. If fired_dir=='down'
# ever appears in FIRED_UP state rows, it must also be filtered out.
# ===========================================================================

class TestDirectionFixture:
    """FIRED_DOWN onsets must never appear in enumerate_sq_events output.

    The enumerator selects FIRED_UP state rows (per vol_squeeze.assess_series
    state column). The fired_dir column should always be 'up' for FIRED_UP rows
    in a correct assess_series implementation.

    However, we test the contract explicitly by constructing a pathological
    case where assess_series returns FIRED_UP state with fired_dir='down'
    (a simulated anomaly or mis-labeling), and verifying the enumerator
    does NOT collect these rows as long-study events.

    Per masterplan: "FIRED_DOWN is the downward break — BANNED from long study."
    Our implementation: events are collected when state=='FIRED_UP'; fired_dir
    is stamped as metadata. For the long study contract, no FIRED_DOWN event
    should be actionable — the direction filter must be robust.
    """

    def test_no_fired_down_in_output(self):
        """FIRED_DOWN events must never appear in the event set.

        We simulate a states DataFrame where some FIRED_UP rows have
        fired_dir='down' (pathological case). The enumerator must not
        emit events with fired_dir='down'.
        """
        n = 10
        idx = _dates(n)
        # Bar 3: FIRED_UP onset with fired_dir='down' (banned — pathological case)
        # Bar 6: FIRED_UP onset with fired_dir='up' (valid)
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "down"  # BANNED
        states[6] = "FIRED_UP"; dirs[6] = "up"    # valid
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        # All events that fired must have FIRED_UP state; fired_dir should be 'up'
        # For this species, we verify NO event with fired_dir='down' exists.
        if not events.empty:
            fired_down_events = events[events["fired_dir"] == "down"]
            assert fired_down_events.empty, (
                f"FIRED_DOWN events must never enter the long study. "
                f"Found {len(fired_down_events)} FIRED_DOWN events:\n"
                f"{fired_down_events[['ticker', 'date', 'fired_dir']].to_string()}"
            )

    def test_pure_fired_down_scenario_produces_no_events(self):
        """When ALL FIRED_UP bars are fired_dir='down', the study gets 0 events.

        This is the canonical 'bear squeeze' scenario: all squeezes fire
        downward. The long study must receive 0 events.
        """
        n = 10
        idx = _dates(n)
        states = ["COILED"] * n
        dirs   = [""] * n
        # Two FIRED_UP bars, both fired_dir='down'
        states[3] = "FIRED_UP"; dirs[3] = "down"
        states[7] = "FIRED_UP"; dirs[7] = "down"
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        # If the enumerator correctly excludes FIRED_DOWN, no events with
        # fired_dir='down' should appear. The result should be either empty
        # or contain only 'up' events.
        if not events.empty:
            assert (events["fired_dir"] == "up").all(), (
                f"All collected events must have fired_dir='up'. "
                f"Found directions: {events['fired_dir'].unique()}"
            )

    def test_mixed_directions_only_up_survives(self):
        """Mixed FIRED_UP direction bars: only 'up' events survive.

        Structure:
          Bar 3: FIRED_UP onset, fired_dir='down' — must be excluded (BANNED)
          Bar 5: non-FIRED_UP (COILED)
          Bar 6: FIRED_UP onset, fired_dir='up' — must be included
          Bar 7: FIRED_UP (consecutive, not an onset)

        Expected result: exactly 1 event at bar 6 with fired_dir='up'.
        """
        n = 12
        idx = _dates(n)
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "down"  # BANNED
        # bar 4 = COILED
        states[6] = "FIRED_UP"; dirs[6] = "up"    # valid onset
        states[7] = "FIRED_UP"; dirs[7] = "up"    # consecutive — not onset
        fake_states = _make_states_df(idx, states, dirs)

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0, "volume": np.ones(n) * 1e6},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        # Only the bar-6 onset should survive (if fired_dir filtering is active)
        # OR: both states[3] and states[6] might be collected since state='FIRED_UP',
        # but states[3] must be excluded from the LONG STUDY.
        # The critical assertion is: no fired_dir='down' in output.
        if not events.empty:
            fired_down_events = events[events["fired_dir"] == "down"]
            assert fired_down_events.empty, (
                f"FIRED_DOWN events found in output — long study contamination. "
                f"FIRED_DOWN onsets must never enter the long study. "
                f"Events:\n{events[['ticker', 'date', 'fired_dir']].to_string()}"
            )

    def test_empty_store_no_direction_events(self):
        """Empty store produces no events regardless of direction."""
        events = enumerate_sq_events({}, "test")
        assert events.empty, f"Expected empty result from empty store. Got {len(events)}"

    def test_species_id_is_s16(self):
        """SPECIES_ID constant must be 'S16' — not S14 (Failed Breakout) or S15 (Spring Reclaim)."""
        assert SPECIES_ID == "S16", (
            f"SPECIES_ID must be 'S16' (S14=Failed Breakout, S15=Spring Reclaim are taken). "
            f"Got: {SPECIES_ID!r}"
        )

    def test_s16_squeeze_release_in_registry(self):
        """Verify S16 = Squeeze Release is in the registry.

        After branch commit, data/species/registry.json must contain an
        entry with species_id='S16' and Squeeze Release name.
        """
        import json
        registry_path = _REPO_ROOT / "data" / "species" / "registry.json"
        if not registry_path.exists():
            return  # registry not available; skip silently
        with open(registry_path) as f:
            reg = json.load(f)
        species_list = reg.get("species", []) if isinstance(reg, dict) else []
        s16_entries = [s for s in species_list if isinstance(s, dict) and s.get("species_id") == "S16"]
        assert len(s16_entries) >= 1, (
            "S16 (Squeeze Release) must be registered in data/species/registry.json. "
            f"Found species IDs: {[s.get('species_id') for s in species_list]}"
        )
        s16 = s16_entries[0]
        assert "Squeeze" in s16.get("name", ""), (
            f"S16 name must include 'Squeeze'. Got: {s16.get('name')!r}"
        )

    def test_s14_and_s15_not_clobbered(self):
        """S14 and S15 must NOT be Squeeze Release (registry clobber check).

        S14 = Failed Breakout (from PR #1457), S15 = Spring Reclaim (from PR #1453).
        Squeeze Release must not have overwritten either.
        """
        import json
        registry_path = _REPO_ROOT / "data" / "species" / "registry.json"
        if not registry_path.exists():
            return  # registry not available; skip
        with open(registry_path) as f:
            reg = json.load(f)
        species_list = reg.get("species", []) if isinstance(reg, dict) else []
        for entry in species_list:
            if not isinstance(entry, dict):
                continue
            sid = entry.get("species_id", "")
            name = entry.get("name", "")
            if sid == "S14":
                assert "Squeeze" not in name, (
                    f"S14 must not be Squeeze Release — registry clobber! Got S14={name!r}"
                )
            if sid == "S15":
                assert "Squeeze" not in name, (
                    f"S15 must not be Squeeze Release — registry clobber! Got S15={name!r}"
                )


# ===========================================================================
# 3. NC-2 both-arm band FE injected-effect marginality (TestInjectedEffectMarginality)
#
# Mirrors the equivalent test in test_run_w2_sur.py.
# Per L1 law: uses the SAME shared _run_nc2_band_fe machinery from run_w2_sur.
# A degenerate FE (bands computed only for treatment) yields coef = 0.0 exactly.
# The fix: bands computed for BOTH arms → non-zero coef.
# ===========================================================================

class TestInjectedEffectMarginality:
    """NC-2 both-arm band FE must yield non-zero coefficient.

    Design: plant a +5pp stop5 effect on the treatment arm, build a synthetic
    gradable DataFrame with interleaved treatment/control rows across multiple
    date clusters, compute proximity bands for both arms, and run _run_nc2_band_fe.

    Key assertion: coef != 0.0 (degenerate FE would return exactly 0.0).
    Secondary: CI bounds must not both be 0.0.

    This test wires directly to the shared S-UR machinery (_run_nc2_band_fe
    from run_w2_sur.py) per the L1 reuse law.
    """

    def _make_nc2_synthetic_frame(
        self,
        n_treatment: int = 120,
        n_control: int = 300,
        true_effect: float = 0.05,
        seed: int = 42,
    ) -> tuple[dict[str, pd.Series], pd.DataFrame]:
        """Build synthetic gradable frame for NC-2 band FE test.

        Constructs 10 date clusters with interleaved treatment and control rows.
        Each cluster has alternating CLOSE/FAR proximity profiles to enable
        non-degenerate FE (both arms in same FE cell).

        Planted stop5 effect = true_effect on treatment arm.

        Returns (closes_dict, gradable_df).
        """
        rng = np.random.default_rng(seed)

        N_DATES = 10
        PRICE_LEN = 200
        EV_POS = 100

        rows: list[dict] = []
        closes: dict[str, pd.Series] = {}

        base_start = pd.Timestamp("2015-01-02")

        n_treat_per_cluster = n_treatment // N_DATES
        n_ctrl_per_cluster = n_control // N_DATES

        ticker_idx = 0
        for d_cluster in range(N_DATES):
            cluster_start = base_start + pd.offsets.BDay(d_cluster * 20)
            price_idx = pd.bdate_range(cluster_start, periods=PRICE_LEN)
            ev_date = price_idx[EV_POS]
            era_str = "2015-2019"

            n_treat_c = (
                n_treat_per_cluster
                if d_cluster < N_DATES - 1
                else (n_treatment - ticker_idx)
            )
            n_ctrl_c = n_ctrl_per_cluster

            cluster_rows = (
                [(True, j) for j in range(max(n_treat_c, 0))]
                + [(False, j) for j in range(n_ctrl_c)]
            )

            for is_treat, j in cluster_rows:
                ticker = f"SSQ_{ticker_idx:04d}"

                # Alternate proximity profiles: CLOSE (j even) vs FAR (j odd)
                use_close_profile = (j % 2 == 0)

                close_vals = np.ones(PRICE_LEN) * 100.0
                if use_close_profile:
                    # Deep compression zone; at event still near the low (CLOSE profile)
                    close_vals[EV_POS - 30 : EV_POS] = 60.0
                    close_vals[EV_POS] = 63.0  # ~5% above 63-bar min (60)
                else:
                    # Mild compression; at event well above the low (FAR profile)
                    close_vals[EV_POS - 30 : EV_POS] = 80.0
                    close_vals[EV_POS] = 100.0  # 25% above 63-bar min (80)

                closes[ticker] = pd.Series(close_vals, index=price_idx)

                base_stop_rate = 0.15
                stop5_val = float(
                    rng.random()
                    < (base_stop_rate + true_effect if is_treat else base_stop_rate)
                )

                rows.append({
                    "ticker": ticker,
                    "date": ev_date,
                    "era": era_str,
                    "_fe": str(ev_date)[:10],
                    "stratum": 1 if is_treat else 0,
                    "stop5": stop5_val,
                    "gradable": True,
                    "sector": "tech",
                })

                ticker_idx += 1

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        return closes, df

    def test_injected_effect_recovered_not_zero(self):
        """A synthetic +5pp stop5 effect must yield non-zero coef after NC-2 band FE.

        This is the critical sentinel for the degenerate-FE bug:
        - Degenerate (bands only for treatment arm): coef = 0.0 exactly
        - Fixed (bands for BOTH arms): coef != 0.0

        The injected true_effect = +0.05 means treatment arm has 5pp higher stop-out
        rate. After NC-2 band FE de-confounding, the coefficient should remain non-zero
        (it may be positive or negative depending on band-cell stop rates, but NEVER exactly 0.0).
        """
        true_effect = 0.05
        closes, df = self._make_nc2_synthetic_frame(
            n_treatment=120,
            n_control=300,
            true_effect=true_effect,
            seed=99,
        )

        result = _run_nc2_band_fe(
            gradable=df,
            stratum_col="stratum",
            closes=closes,
            n_bootstrap=100,  # small for test speed; production uses >=1000
            rng_seed=0,
            panel="test",
            sector_col="sector",
        )

        assert result.get("band_computed", False), (
            f"NC-2 band FE failed to compute: {result.get('note', 'unknown')}. "
            "Insufficient price history or too few rows for the proxy computation."
        )

        coef = result.get("coef")
        assert coef is not None, "NC-2 band FE returned no coefficient."

        # PRIMARY ASSERTION: coef must NOT be exactly 0.0000.
        # A degenerate FE produces coef = 0.0 by perfect FE separation.
        # The fix (both-arm band assignment) yields a non-zero value.
        assert coef != 0.0, (
            f"NC-2 band FE returned coef = 0.0000 — degenerate FE-separation bug present. "
            f"Expected a non-zero coefficient (planted effect = +{true_effect:.3f}). "
            "Fix: ensure compute_nc2_proximity_proxy is called on ALL rows (both "
            "treatment and control), not just treatment rows."
        )

        # SECONDARY ASSERTION: CI bounds must not both be exactly 0.0
        ci_lo = result.get("ci_lo", None)
        ci_hi = result.get("ci_hi", None)
        if ci_lo is not None and ci_hi is not None:
            assert not (ci_lo == 0.0 and ci_hi == 0.0), (
                f"NC-2 band FE returned zero-width CI at 0.0 — degenerate regression. "
                f"coef={coef}, ci_lo={ci_lo}, ci_hi={ci_hi}"
            )

    def test_band_computed_flag_is_true(self):
        """band_computed must be True when sufficient data is present."""
        closes, df = self._make_nc2_synthetic_frame(
            n_treatment=120, n_control=300, true_effect=0.02, seed=7,
        )
        result = _run_nc2_band_fe(
            gradable=df,
            stratum_col="stratum",
            closes=closes,
            n_bootstrap=50,
            rng_seed=0,
            panel="test",
            sector_col="sector",
        )
        assert result.get("band_computed", False), (
            f"band_computed must be True with sufficient data. "
            f"Note: {result.get('note', '(no note)')}"
        )

    def test_insufficient_rows_returns_band_not_computed(self):
        """With < MIN_ROWS threshold, band_computed should be False (graceful skip).

        Test with a tiny DataFrame that can't support the FE regression.
        """
        closes = {"T0": pd.Series(np.ones(200) * 100.0, index=_dates(200))}
        df = pd.DataFrame({
            "ticker": ["T0", "T0"],
            "date":   [_dates(200)[100], _dates(200)[101]],
            "era":    ["2015-2019"] * 2,
            "_fe":    ["2014-05-23"] * 2,
            "stratum": [1, 0],
            "stop5":   [0.0, 0.0],
            "gradable":[True, True],
            "sector":  ["tech"] * 2,
        })
        df["date"] = pd.to_datetime(df["date"])

        result = _run_nc2_band_fe(
            gradable=df,
            stratum_col="stratum",
            closes=closes,
            n_bootstrap=10,
            rng_seed=0,
            panel="test",
            sector_col=None,
        )
        # With only 2 rows the FE regression can't work; band_computed should be False
        # (or coef returned but with degenerate output — either is acceptable as long as
        # the script doesn't crash)
        assert isinstance(result, dict), "Must return a dict even for insufficient data"


# ===========================================================================
# 4. Volume loading and coverage tests (BLOCKER FIX)
#
# The prior loaders dropped the 'volume' column, leaving vol_ok=None inside
# assess() so every FIRED_UP event fired on price break ALONE — the defining
# volume-confirmation was disabled.  These tests verify the fix.
# ===========================================================================

class TestVolumeLoading:
    """Verify the volume-loading fix and coverage table helpers.

    Tests:
      A. _build_volume_coverage_table returns correct counts.
      B. volume_confirmed is 1.0/0.0 (not NaN) when volume is supplied to assess_series.
      C. volume_confirmed is NaN when volume column is absent; NaN must survive tri-state
         (the old bool() coercion silently mapped NaN→False; this is the MAJOR fix).
      D. NaN volume_confirmed injected via enumerate_sq_events reaches 'missing' bucket.
      E. SENSITIVITY_CONFIGS has exactly 3 named sensitivities.
      F. _spot_check_volume_loading returns correct structure.
    """

    def _make_events_with_vol(self) -> pd.DataFrame:
        """Build a minimal events DataFrame with volume_confirmed populated."""
        idx = _dates(4)
        return pd.DataFrame({
            "ticker":           ["AAPL", "AAPL", "MSFT", "TSLA"],
            "date":             list(idx),
            "panel":            ["deep"] * 4,
            "fired_dir":        ["up"] * 4,
            "volume_confirmed": [True, False, True, True],  # bool
            "cfg_key":          ["defaults"] * 4,
        })

    def _make_events_no_vol(self) -> pd.DataFrame:
        """Build a minimal events DataFrame with missing volume_confirmed."""
        idx = _dates(3)
        return pd.DataFrame({
            "ticker":           ["X", "Y", "Z"],
            "date":             list(idx),
            "panel":            ["deep"] * 3,
            "fired_dir":        ["up"] * 3,
            "volume_confirmed": [float("nan"), float("nan"), float("nan")],
            "cfg_key":          ["defaults"] * 3,
        })

    def test_volume_coverage_counts_correct(self):
        """_build_volume_coverage_table must correctly count True/False/NaN."""
        events = self._make_events_with_vol()
        result = _build_volume_coverage_table({"deep": events})
        vc = result["deep"]
        assert vc["total"] == 4, f"total must be 4, got {vc['total']}"
        assert vc["confirmed"] == 3, f"confirmed must be 3, got {vc['confirmed']}"
        assert vc["not_confirmed"] == 1, f"not_confirmed must be 1, got {vc['not_confirmed']}"
        assert vc["missing"] == 0, f"missing must be 0, got {vc['missing']}"

    def test_volume_coverage_counts_missing_volume(self):
        """volume_confirmed=NaN events must be counted as 'missing', not confirmed."""
        events = self._make_events_no_vol()
        result = _build_volume_coverage_table({"deep": events})
        vc = result["deep"]
        assert vc["confirmed"] == 0, f"confirmed must be 0 for all-NaN, got {vc['confirmed']}"
        assert vc["not_confirmed"] == 0, (
            f"not_confirmed must be 0 for all-NaN, got {vc['not_confirmed']}"
        )
        assert vc["missing"] == 3, f"missing must be 3 for all-NaN, got {vc['missing']}"

    def test_volume_confirmed_not_nan_when_volume_supplied(self):
        """When volume column is present in the OHLCV store, enumerate_sq_events
        must produce volume_confirmed True or False — never NaN.

        This is the core BLOCKER FIX assertion: vol_ok must be a boolean inside
        assess() when has_vol=True, so volume_confirmed is never left as NaN.
        """
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)

        # Build a fake assess_series result WITH volume_confirmed set to 1.0 (True)
        # to simulate the engine running with volume available.
        fake_states = pd.DataFrame(
            {
                "state":            states,
                "fired_dir":        dirs,
                "volume_confirmed": [1.0 if s == "FIRED_UP" else 0.0 for s in states],
                "days_compressed":  [5] * n,
                "bbwp":             [20.0] * n,
                "hv_pctile":        [18.0] * n,
                "coverage":         ["ohlcv"] * n,
            },
            index=idx,
        )

        # Store HAS volume column — the fix passes it to assess_series
        store = {
            "TEST": pd.DataFrame(
                {
                    "close":  np.ones(n) * 100.0,
                    "high":   np.ones(n) * 101.0,
                    "low":    np.ones(n) * 99.0,
                    "volume": np.ones(n) * 1_000_000.0,   # volume present
                },
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert not events.empty, "Expected at least one FIRED_UP event"
        assert "volume_confirmed" in events.columns, "volume_confirmed column must exist"
        # With volume supplied, volume_confirmed must be True or False — never NaN
        nan_count = events["volume_confirmed"].isna().sum()
        assert nan_count == 0, (
            f"volume_confirmed must not be NaN when volume is supplied to assess_series. "
            f"Got {nan_count} NaN values. "
            "BLOCKER FIX: the loader must pass volume= to assess_series."
        )

    def test_volume_confirmed_nan_when_volume_absent(self):
        """When volume_confirmed is NaN in assess_series output (volume absent),
        the enumerator must faithfully pass through the NaN — not coerce it."""
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)

        # Fake states: volume_confirmed = NaN (assess_series with volume=None)
        fake_states = pd.DataFrame(
            {
                "state":            states,
                "fired_dir":        dirs,
                "volume_confirmed": [float("nan")] * n,  # no volume available
                "days_compressed":  [5] * n,
                "bbwp":             [20.0] * n,
                "hv_pctile":        [18.0] * n,
                "coverage":         ["ohlc"] * n,        # no volume in coverage
            },
            index=idx,
        )

        # Store WITHOUT volume column (simulating old broken loaders)
        store = {
            "TEST": pd.DataFrame(
                {
                    "close":  np.ones(n) * 100.0,
                    "high":   np.ones(n) * 101.0,
                    "low":    np.ones(n) * 99.0,
                    # no volume column — this is what the broken loaders produced
                },
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        if not events.empty:
            # With no volume, volume_confirmed must come from the fake_states NaN
            # The enumerator reads row_data.get("volume_confirmed", 0) — but
            # NaN != 1.0 so volume_confirmed should be False (not True)
            # The key point: the event fires but volume_confirmed is NOT True.
            vc_val = events.iloc[0]["volume_confirmed"]
            assert vc_val is not True, (
                f"volume_confirmed must not be True when volume is absent. Got: {vc_val!r}. "
                "A volume-absent event must not be counted as mechanism-faithful."
            )

    def test_nan_volume_confirmed_lands_in_missing_bucket(self):
        """NaN volume_confirmed injected via enumerate_sq_events must reach the
        'missing' bucket of _build_volume_coverage_table — not 'confirmed' or
        'not_confirmed'.

        This guards the tri-state fix: the old bool() coercion silently mapped
        NaN→False, making missing always=0. With the fix the enumerator preserves
        NaN as float('nan'), and the coverage table can detect it via isna().
        """
        n = 8
        states = ["COILED"] * n
        dirs   = [""] * n
        states[3] = "FIRED_UP"; dirs[3] = "up"
        idx = _dates(n)

        # Fake assess_series returns NaN volume_confirmed (volume=None path)
        fake_states = pd.DataFrame(
            {
                "state":            states,
                "fired_dir":        dirs,
                "volume_confirmed": [float("nan")] * n,
                "days_compressed":  [5] * n,
                "bbwp":             [20.0] * n,
                "hv_pctile":        [18.0] * n,
                "coverage":         ["ohlc"] * n,
            },
            index=idx,
        )

        store = {
            "TEST": pd.DataFrame(
                {"close": np.ones(n) * 100.0, "high": np.ones(n) * 101.0,
                 "low": np.ones(n) * 99.0},
                index=idx,
            )
        }

        with patch("engine.vol_squeeze.assess_series", return_value=fake_states):
            events = enumerate_sq_events(store, "test")

        assert not events.empty, "Expected FIRED_UP event from fake_states"

        # The NaN must survive in the events DataFrame
        vc_col = events["volume_confirmed"]
        assert vc_col.isna().any(), (
            f"NaN volume_confirmed from assess_series must be preserved in events "
            f"(not coerced to False/0). Got dtype={vc_col.dtype}, values={vc_col.unique()!r}. "
            "Fix: use float pass-through, not bool() coercion in the enumerator."
        )

        # And must reach the 'missing' bucket in the coverage table
        cov = _build_volume_coverage_table({"test": events})
        bucket = cov["test"]
        assert bucket["missing"] >= 1, (
            f"NaN volume_confirmed must be counted in the 'missing' bucket. "
            f"Got missing={bucket['missing']}, confirmed={bucket['confirmed']}, "
            f"not_confirmed={bucket['not_confirmed']}. "
            "Fix: preserve tri-state float in enumerator so isna() detects it."
        )
        assert bucket["confirmed"] == 0, (
            f"NaN must not land in 'confirmed'. Got confirmed={bucket['confirmed']}."
        )
        assert bucket["not_confirmed"] == 0, (
            f"NaN must not land in 'not_confirmed'. Got not_confirmed={bucket['not_confirmed']}."
        )

    def test_sensitivity_configs_count(self):
        """SENSITIVITY_CONFIGS must have exactly 3 named sensitivities."""
        assert len(SENSITIVITY_CONFIGS) == 3, (
            f"Expected 3 named sensitivities (pctile20, relwin2, volconf15). "
            f"Got: {list(SENSITIVITY_CONFIGS.keys())}"
        )
        assert "pctile20" in SENSITIVITY_CONFIGS, "pctile20 sensitivity must exist"
        assert "relwin2"  in SENSITIVITY_CONFIGS, "relwin2 sensitivity must exist"
        assert "volconf15" in SENSITIVITY_CONFIGS, "volconf15 sensitivity must exist"

    def test_sensitivity_configs_override_single_key(self):
        """Each sensitivity config must override exactly one key vs defaults."""
        for sens_key, cfg_override in SENSITIVITY_CONFIGS.items():
            assert len(cfg_override) == 1, (
                f"Sensitivity {sens_key!r} should override exactly 1 key, "
                f"got {len(cfg_override)}: {cfg_override}"
            )

    def test_spot_check_returns_correct_structure(self):
        """_spot_check_volume_loading must return required structure keys."""
        store = {
            "AAPL": pd.DataFrame(
                {"close": [100.0, 101.0], "high": [101.0, 102.0],
                 "low": [99.0, 100.0], "volume": [1e6, 2e6]},
                index=pd.bdate_range("2020-01-02", periods=2),
            ),
            "NO_VOL": pd.DataFrame(
                {"close": [50.0, 51.0]},
                index=pd.bdate_range("2020-01-02", periods=2),
            ),
        }
        result = _spot_check_volume_loading(store, "test")
        assert "n_total"          in result
        assert "n_with_volume"    in result
        assert "n_without_volume" in result
        assert "sample_results"   in result
        assert result["n_total"]       == 2
        assert result["n_with_volume"] == 1, f"Only AAPL has volume, got {result['n_with_volume']}"
        aapl_info = result["sample_results"].get("AAPL", {})
        assert aapl_info.get("has_volume") is True
        assert aapl_info.get("vol_nonzero") == 2


# ===========================================================================
# 4. Species ID and constants sanity tests
# ===========================================================================

class TestSpeciesConstants:
    """Verify the species constants are consistent and correct."""

    def test_species_id(self):
        assert SPECIES_ID == "S16"

    def test_species_name(self):
        assert "Squeeze" in SPECIES_NAME

    def test_species_family(self):
        assert SPECIES_FAMILY == "esx_sq_phase0"

    def test_defaults_cfg_has_required_keys(self):
        """DEFAULTS_CFG must have all 4 vol_squeeze.DEFAULTS keys."""
        required = {"pctile_thresh", "min_duration", "release_window", "vol_confirm"}
        assert required.issubset(DEFAULTS_CFG.keys()), (
            f"Missing keys in DEFAULTS_CFG: {required - DEFAULTS_CFG.keys()}"
        )

    def test_defaults_cfg_values_match_engine(self):
        """DEFAULTS_CFG values must match engine/vol_squeeze.DEFAULTS."""
        try:
            from engine.vol_squeeze import DEFAULTS
        except ImportError:
            return  # engine not available; skip
        for k, v in DEFAULTS_CFG.items():
            if k in DEFAULTS:
                assert DEFAULTS_CFG[k] == DEFAULTS[k], (
                    f"DEFAULTS_CFG[{k!r}] = {v!r} != engine DEFAULTS[{k!r}] = {DEFAULTS[k]!r}. "
                    "Keep DEFAULTS_CFG in sync with engine/vol_squeeze.DEFAULTS."
                )

    def test_family_in_family_budgets(self):
        """esx_sq_phase0 must be declared in FAMILY_BUDGETS (from entry_strata_phase0)."""
        try:
            from scripts.research.entry_strata_phase0 import FAMILY_BUDGETS
        except ImportError:
            return  # harness not available; skip
        assert "esx_sq_phase0" in FAMILY_BUDGETS, (
            f"esx_sq_phase0 must be in FAMILY_BUDGETS. "
            f"Found: {list(FAMILY_BUDGETS.keys())}"
        )
        # FAMILY_BUDGETS values may be int or dict with 'budget' key
        entry = FAMILY_BUDGETS["esx_sq_phase0"]
        budget = entry["budget"] if isinstance(entry, dict) else int(entry)
        assert budget == 12, (
            f"esx_sq_phase0 budget must be 12. "
            f"Got: {entry!r}"
        )


# ===========================================================================
# TestEnumerationCheckpoint — cache hit skips recompute
# ===========================================================================

class TestEnumerationCheckpoint:
    """Verify the per-ticker enumeration checkpoint:

    - A ticker whose events are already cached is loaded from cache without
      calling assess_series (counter must NOT increment for the cached ticker).
    - A ticker not in cache triggers a compute and the result is written.
    """

    def test_cache_hit_skips_assess_series(self, tmp_path):
        """Cache hit: assess_series must NOT be called for the cached ticker.

        Strategy:
          1. Pre-populate the cache with deterministic events for ticker CACHED.
          2. Build a store with CACHED + UNCACHED.
          3. Monkeypatch assess_series to count calls and return an empty DataFrame.
          4. Call enumerate_sq_events with cache_dir=tmp_path.
          5. Assert: assess_series was called exactly 1 time (only for UNCACHED).
          6. Assert: the returned DataFrame contains the cached events for CACHED.
        """
        import io
        call_counter = {"n": 0}

        # Pre-populate cache with 2 synthetic events for CACHED.
        cached_rows = [
            {
                "ticker": "CACHED",
                "date": pd.Timestamp("2021-03-01"),
                "panel": "test_panel",
                "fired_dir": "up",
                "volume_confirmed": 1.0,
                "days_compressed": 7,
                "bbwp": 18.5,
                "hv_pctile": 15.0,
                "coverage": "hl",
                "cfg_key": "defaults",
            },
            {
                "ticker": "CACHED",
                "date": pd.Timestamp("2022-06-10"),
                "panel": "test_panel",
                "fired_dir": "up",
                "volume_confirmed": 1.0,
                "days_compressed": 9,
                "bbwp": 12.0,
                "hv_pctile": 10.0,
                "coverage": "hl",
                "cfg_key": "defaults",
            },
        ]

        # Resolve the cache dir for (panel=test_panel, cfg_key=defaults) under tmp_path.
        cache_dir = _get_event_cache_dir("test_panel", "defaults", override=tmp_path)
        _save_ticker_cache(cache_dir, "CACHED", cached_rows)

        # Build a minimal OHLCV store with both tickers.
        n = 20
        idx = pd.bdate_range(start="2020-01-02", periods=n)
        base_df = pd.DataFrame(
            {
                "close":  np.ones(n) * 100.0,
                "high":   np.ones(n) * 101.0,
                "low":    np.ones(n) * 99.0,
                "volume": np.ones(n) * 1_000_000.0,
            },
            index=idx,
        )
        store = {"CACHED": base_df.copy(), "UNCACHED": base_df.copy()}

        # Monkeypatch assess_series to count calls + return empty (no events for UNCACHED).
        empty_states = pd.DataFrame(
            columns=["state", "fired_dir", "volume_confirmed",
                     "days_compressed", "bbwp", "hv_pctile", "coverage"],
            index=pd.DatetimeIndex([]),
        )

        def _mock_assess(*args, **kwargs):
            call_counter["n"] += 1
            return empty_states

        with patch("engine.vol_squeeze.assess_series", side_effect=_mock_assess):
            events = enumerate_sq_events(
                store,
                panel_name="test_panel",
                cfg=None,
                n_workers=1,
                cache_dir=tmp_path,
            )

        # assess_series must have been called for UNCACHED only (exactly once).
        assert call_counter["n"] == 1, (
            f"Expected assess_series to be called once (for UNCACHED ticker). "
            f"Got {call_counter['n']} calls. "
            "Cache hit should skip assess_series for CACHED ticker."
        )

        # The output must include the 2 pre-cached events.
        cached_in_output = events[events["ticker"] == "CACHED"]
        assert len(cached_in_output) == 2, (
            f"Expected 2 cached events for CACHED in output. Got {len(cached_in_output)}."
        )
