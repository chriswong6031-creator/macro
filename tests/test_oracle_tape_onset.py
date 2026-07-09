"""Tests for FTR W7 — TAPE-ONSET (unconfirmed) display tier.

Registration: research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md
Constitution: research/ORACLE_CONSTITUTION.md

Test inventory
--------------
A. predicate_threshold        — raw accel_z threshold gate (>= 1.0)
B. predicate_direction        — vel_1w > vel_3m direction check
C. predicate_episode_suppress — active same-direction episode blocks the flag
D. predicate_nan_safety       — NaN inputs → False (never raises)
E. rates_math                 — p_onset_5d + false_positive_5d = 1.0 (registration §3)
F. rates_window_bounds        — window_start/end match panel date range
G. additive_payload_tolerance — old readers (no tape_onset keys) unaffected
H. banned_key_check           — check_banned_keys catches 'forecast', 'predicted', etc.
I. ledger_append              — new flags appended; keep-first (same key not duplicated)
J. ledger_lane_gate           — nightly-only; dry_run=True writes nothing
K. ledger_no_append_when_not_flagged — unflagged nodes do not create ledger rows
L. compute_payload_structure  — returns dict with correct top-level keys per node
M. false_positive_explicit    — false_positive_5d = 1 - p_onset_5d printed explicitly
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine.oracle.tape_onset import (
    TAPE_ONSET_RAW_ACCEL_Z_THRESHOLD,
    is_tape_onset,
    compute_tape_onset_stats,
    compute_tape_onset_payload,
    append_tape_onset_ledger,
    check_banned_keys,
)


# ---------------------------------------------------------------------------
# Synthetic helpers
# ---------------------------------------------------------------------------

def _make_panel(
    nodes: list[str],
    n_days: int = 80,
    start: str = "2023-01-03",
    seed: int = 42,
) -> pd.DataFrame:
    """Minimal MultiIndex (node, date) panel with required columns."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days, name="date")
    rows = []
    for node in nodes:
        az = rng.normal(0.0, 0.8, n_days)  # mostly below 1.0
        vel_1w = rng.normal(0.005, 0.015, n_days)
        vel_3m = rng.normal(0.002, 0.008, n_days)
        for i, d in enumerate(dates):
            rows.append({
                "node": node,
                "date": d,
                "accel_z": az[i],
                "vel_1w": vel_1w[i],
                "vel_3m": vel_3m[i],
                "ret": rng.normal(0.001, 0.01),
                "rs": rng.normal(0, 0.005),
            })
    df = pd.DataFrame(rows).set_index(["node", "date"])
    return df


def _make_flagged_panel(
    node: str = "XLK",
    n_days: int = 80,
    start: str = "2023-01-03",
    flag_last: bool = True,
) -> pd.DataFrame:
    """Panel where the last row is guaranteed to have tape_onset = True."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range(start, periods=n_days, name="date")
    az = rng.normal(0.0, 0.5, n_days)
    vel_1w = rng.normal(0.005, 0.01, n_days)
    vel_3m = rng.normal(0.002, 0.005, n_days)
    if flag_last:
        az[-1] = 1.5          # >= 1.0
        vel_1w[-1] = 0.03     # > vel_3m
        vel_3m[-1] = 0.01
    rows = [{"node": node, "date": d, "accel_z": az[i], "vel_1w": vel_1w[i],
             "vel_3m": vel_3m[i], "ret": 0.001, "rs": 0.001}
            for i, d in enumerate(dates)]
    df = pd.DataFrame(rows).set_index(["node", "date"])
    return df


def _make_episodes(
    node: str,
    direction: str = "in",
    onset_date: str = "2023-01-03",
    exhausted_date: str | None = "2023-02-15",
    confirmed_date: str | None = "2023-01-10",
) -> pd.DataFrame:
    """Minimal episodes DataFrame with one episode."""
    row: dict = {
        "node": node,
        "direction": direction,
        "onset_date": pd.Timestamp(onset_date),
        "exhausted_date": pd.Timestamp(exhausted_date) if exhausted_date else None,
        "confirmed_date": pd.Timestamp(confirmed_date) if confirmed_date else None,
        "episode_id": f"{node}::{direction}::{onset_date}::1",
        "two_sided": False,
        "survivorship_flagged": False,
    }
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# A. predicate_threshold
# ---------------------------------------------------------------------------

class TestPredicateThreshold:
    def test_at_threshold_fires(self):
        assert is_tape_onset(
            accel_z_raw=TAPE_ONSET_RAW_ACCEL_Z_THRESHOLD,
            vel_1w=0.02, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is True

    def test_above_threshold_fires(self):
        assert is_tape_onset(
            accel_z_raw=2.5,
            vel_1w=0.02, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is True

    def test_below_threshold_no_fire(self):
        assert is_tape_onset(
            accel_z_raw=0.99,
            vel_1w=0.02, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is False

    def test_zero_no_fire(self):
        assert is_tape_onset(
            accel_z_raw=0.0,
            vel_1w=0.02, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is False


# ---------------------------------------------------------------------------
# B. predicate_direction
# ---------------------------------------------------------------------------

class TestPredicateDirection:
    def test_vel_1w_equals_vel_3m_no_fire(self):
        # vel_1w == vel_3m: NOT strictly greater → no fire
        assert is_tape_onset(
            accel_z_raw=1.5,
            vel_1w=0.02, vel_3m=0.02,
            has_active_same_direction_episode=False,
        ) is False

    def test_vel_1w_less_than_vel_3m_no_fire(self):
        assert is_tape_onset(
            accel_z_raw=1.5,
            vel_1w=0.01, vel_3m=0.02,
            has_active_same_direction_episode=False,
        ) is False

    def test_vel_1w_greater_than_vel_3m_fires(self):
        assert is_tape_onset(
            accel_z_raw=1.5,
            vel_1w=0.03, vel_3m=0.02,
            has_active_same_direction_episode=False,
        ) is True


# ---------------------------------------------------------------------------
# C. predicate_episode_suppress
# ---------------------------------------------------------------------------

class TestPredicateEpisodeSuppress:
    def test_active_episode_blocks(self):
        assert is_tape_onset(
            accel_z_raw=2.0,
            vel_1w=0.05, vel_3m=0.01,
            has_active_same_direction_episode=True,
        ) is False

    def test_no_active_episode_fires(self):
        assert is_tape_onset(
            accel_z_raw=2.0,
            vel_1w=0.05, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is True


# ---------------------------------------------------------------------------
# D. predicate_nan_safety
# ---------------------------------------------------------------------------

class TestPredicateNanSafety:
    def test_nan_accel_z(self):
        assert is_tape_onset(
            accel_z_raw=float("nan"),
            vel_1w=0.05, vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is False

    def test_nan_vel_1w(self):
        assert is_tape_onset(
            accel_z_raw=2.0,
            vel_1w=float("nan"), vel_3m=0.01,
            has_active_same_direction_episode=False,
        ) is False

    def test_nan_vel_3m(self):
        assert is_tape_onset(
            accel_z_raw=2.0,
            vel_1w=0.05, vel_3m=float("nan"),
            has_active_same_direction_episode=False,
        ) is False

    def test_all_nan(self):
        assert is_tape_onset(
            accel_z_raw=float("nan"),
            vel_1w=float("nan"), vel_3m=float("nan"),
            has_active_same_direction_episode=False,
        ) is False


# ---------------------------------------------------------------------------
# E. rates_math — p_onset_5d + false_positive_5d = 1.0
# ---------------------------------------------------------------------------

class TestRatesMath:
    def test_false_positive_complement(self):
        """false_positive_5d = 1 - p_onset_5d (registration §3, printed explicitly)."""
        panel = _make_flagged_panel(node="XLK", n_days=200, flag_last=False)
        # Inject several flags in the history
        idx = panel.index
        node_idx = [i for i, (n, _) in enumerate(idx) if n == "XLK"]
        az_vals = panel["accel_z"].values.copy()
        vel_1w_vals = panel["vel_1w"].values.copy()
        vel_3m_vals = panel["vel_3m"].values.copy()
        # Force 10 flags at non-tail positions
        for pos in node_idx[10:21]:
            az_vals[pos] = 1.5
            vel_1w_vals[pos] = 0.04
            vel_3m_vals[pos] = 0.01
        panel = panel.copy()
        panel["accel_z"] = az_vals
        panel["vel_1w"] = vel_1w_vals
        panel["vel_3m"] = vel_3m_vals
        node_panel = panel.xs("XLK", level="node").sort_index()
        stats = compute_tape_onset_stats(node_panel, None, "XLK")

        if stats["p_onset_5d"] is not None and stats["false_positive_5d"] is not None:
            total = round(stats["p_onset_5d"] + stats["false_positive_5d"], 6)
            assert abs(total - 1.0) < 1e-5, (
                f"p_onset_5d + false_positive_5d = {total}, expected 1.0"
            )
            assert 0.0 <= stats["p_onset_5d"] <= 1.0, (
                f"p_onset_5d={stats['p_onset_5d']} must be in [0, 1]"
            )
            assert 0.0 <= stats["false_positive_5d"] <= 1.0, (
                f"false_positive_5d={stats['false_positive_5d']} must be in [0, 1]"
            )

    def test_no_flags_returns_zero(self):
        """A panel where the flag never fires returns n_flags=0 and None rates."""
        panel = _make_panel(nodes=["XLF"], n_days=60)
        node_panel = panel.xs("XLF", level="node").sort_index()
        # Force all accel_z below threshold
        node_panel = node_panel.copy()
        node_panel["accel_z"] = 0.1
        stats = compute_tape_onset_stats(node_panel, None, "XLF")
        assert stats["n_flags"] == 0
        assert stats["p_onset_5d"] is None
        assert stats["false_positive_5d"] is None

    def test_tail_flags_do_not_inflate_rates(self):
        """Regression: tail flags (partial forward window) must NOT inflate p_onset_5d > 1.0.

        The bug: numerator loop only skipped flags with zero forward sessions while the
        denominator required a full 5-session window — yielding p_onset_5d > 1.0 and
        false_positive_5d < 0 when tail flags happened to also have a smoothed-onset hit
        in their partial window.  Fix: both numerator and denominator restrict to
        full-window flags.
        """
        panel = _make_panel(nodes=["XLV"], n_days=40)
        node_panel = panel.xs("XLV", level="node").sort_index()
        node_panel = node_panel.copy()
        # Place flags in the last 3 rows (tail — fewer than 5 forward sessions each)
        node_panel["accel_z"] = 0.0
        node_panel["vel_1w"] = 0.0
        node_panel["vel_3m"] = -0.01
        for pos in [-3, -2, -1]:
            node_panel.iloc[pos, node_panel.columns.get_loc("accel_z")] = 1.5
            node_panel.iloc[pos, node_panel.columns.get_loc("vel_1w")] = 0.04
            node_panel.iloc[pos, node_panel.columns.get_loc("vel_3m")] = 0.01
        # Also set accel_z_5d high in tail so partial-window numerator would have fired
        if "accel_z_5d" in node_panel.columns:
            node_panel.iloc[-2, node_panel.columns.get_loc("accel_z_5d")] = 2.0
            node_panel.iloc[-1, node_panel.columns.get_loc("accel_z_5d")] = 2.0
        stats = compute_tape_onset_stats(node_panel, None, "XLV")
        # Tail-only flags: no full-window flags exist → rates should be None
        if stats["p_onset_5d"] is not None:
            assert 0.0 <= stats["p_onset_5d"] <= 1.0, (
                f"p_onset_5d={stats['p_onset_5d']} exceeded 1.0 — tail-flag inflation bug"
            )
        if stats["false_positive_5d"] is not None:
            assert 0.0 <= stats["false_positive_5d"] <= 1.0, (
                f"false_positive_5d={stats['false_positive_5d']} went negative — tail-flag inflation bug"
            )


# ---------------------------------------------------------------------------
# F. rates_window_bounds
# ---------------------------------------------------------------------------

class TestRatesWindowBounds:
    def test_window_matches_panel_dates(self):
        panel = _make_panel(nodes=["XLE"], n_days=80, start="2022-06-01")
        node_panel = panel.xs("XLE", level="node").sort_index()
        stats = compute_tape_onset_stats(node_panel, None, "XLE")
        expected_start = node_panel.index[0].strftime("%Y-%m-%d")
        expected_end = node_panel.index[-1].strftime("%Y-%m-%d")
        assert stats["window_start"] == expected_start
        assert stats["window_end"] == expected_end


# ---------------------------------------------------------------------------
# G. additive_payload_tolerance — old readers unaffected
# ---------------------------------------------------------------------------

class TestAdditivePayloadTolerance:
    def test_old_reader_ignores_new_keys(self):
        """A dict consumer that only reads 'asof' is unaffected by tape_onset_nodes."""
        payload = {
            "schema": "oracle_tape_onset.v1",
            "asof": "2026-07-09",
            "nodes": {
                "XLK": {
                    "tape_onset_unconfirmed": True,
                    "tape_onset_stats": {"n_flags": 5, "p_onset_5d": 0.4,
                                         "false_positive_5d": 0.6, "p_confirmed_10d": 0.2,
                                         "window_start": "2022-01-01", "window_end": "2026-07-09"},
                }
            },
        }
        # Old reader only accesses known keys — should not raise on new keys
        old_reader_result = payload.get("asof")
        assert old_reader_result == "2026-07-09"
        # New keys are just ignored by old reader
        unknown = payload.get("nodes", {}).get("XLK", {}).get("tape_onset_unconfirmed")
        assert unknown is True  # new reader can access it

    def test_tape_onset_nodes_additive_on_turn_desk(self):
        """Adding tape_onset_nodes field to a turn_desk dict does not break existing keys."""
        turn_desk = {
            "schema": "oracle_turn_desk.v1",
            "asof": "2026-07-09",
            "armed": [],
            "base_rates": {"in_window_wr21": 0.652},
        }
        # Additive: merge tape_onset_nodes
        augmented = {**turn_desk, "tape_onset_nodes": {"XLK": {"tape_onset_unconfirmed": False}}}
        # Existing keys preserved
        assert augmented["schema"] == "oracle_turn_desk.v1"
        assert augmented["armed"] == []
        assert augmented["base_rates"]["in_window_wr21"] == 0.652
        # New key present
        assert "tape_onset_nodes" in augmented


# ---------------------------------------------------------------------------
# H. banned_key_check
# ---------------------------------------------------------------------------

class TestBannedKeyCheck:
    def test_clean_payload_no_errors(self):
        payload = {"asof": "2026-07-09", "nodes": {"XLK": {"tape_onset_unconfirmed": True}}}
        assert check_banned_keys(payload) == []

    def test_forecast_key_caught(self):
        payload = {"forecast_probability": 0.7}
        errs = check_banned_keys(payload)
        assert any("forecast" in e for e in errs)

    def test_predicted_key_caught(self):
        payload = {"nodes": {"XLK": {"predicted_onset": True}}}
        errs = check_banned_keys(payload)
        assert any("predicted" in e for e in errs)

    def test_target_key_caught(self):
        payload = {"target_return": 0.05}
        errs = check_banned_keys(payload)
        assert any("target" in e for e in errs)

    def test_expected_return_key_caught(self):
        payload = {"expected_return_5d": 0.02}
        errs = check_banned_keys(payload)
        assert any("expected_return" in e for e in errs)

    def test_nested_banned_key_caught(self):
        payload = {"stats": {"sub": {"expected_return_10d": 0.01}}}
        errs = check_banned_keys(payload)
        assert any("expected_return" in e for e in errs)

    def test_list_items_checked(self):
        payload = {"items": [{"forecast_value": 0.5}]}
        errs = check_banned_keys(payload)
        assert any("forecast" in e for e in errs)


# ---------------------------------------------------------------------------
# I. ledger_append — new flags appended, keep-first
# ---------------------------------------------------------------------------

class TestLedgerAppend:
    def test_flagged_node_appended(self, tmp_path):
        ledger_path = tmp_path / "tape_onset_ledger.jsonl"
        payload = {"XLK": {"tape_onset_unconfirmed": True, "tape_onset_stats": {}}}
        n = append_tape_onset_ledger(payload, "2026-07-09", ledger_path)
        assert n == 1
        assert ledger_path.exists()
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1
        assert rows[0]["node"] == "XLK"
        assert rows[0]["asof"] == "2026-07-09"
        assert rows[0]["tape_onset_unconfirmed"] is True

    def test_keep_first_no_duplicate(self, tmp_path):
        ledger_path = tmp_path / "tape_onset_ledger.jsonl"
        payload = {"XLK": {"tape_onset_unconfirmed": True, "tape_onset_stats": {}}}
        n1 = append_tape_onset_ledger(payload, "2026-07-09", ledger_path)
        n2 = append_tape_onset_ledger(payload, "2026-07-09", ledger_path)
        assert n1 == 1
        assert n2 == 0  # keep-first: same key not duplicated
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 1

    def test_different_date_appended(self, tmp_path):
        ledger_path = tmp_path / "tape_onset_ledger.jsonl"
        payload = {"XLK": {"tape_onset_unconfirmed": True, "tape_onset_stats": {}}}
        n1 = append_tape_onset_ledger(payload, "2026-07-09", ledger_path)
        n2 = append_tape_onset_ledger(payload, "2026-07-10", ledger_path)
        assert n1 == 1
        assert n2 == 1  # different asof = new key
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# J. ledger_lane_gate — dry_run writes nothing
# ---------------------------------------------------------------------------

class TestLedgerDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        ledger_path = tmp_path / "tape_onset_ledger.jsonl"
        payload = {"XLK": {"tape_onset_unconfirmed": True, "tape_onset_stats": {}}}
        n = append_tape_onset_ledger(payload, "2026-07-09", ledger_path, dry_run=True)
        assert n == 1  # counts rows but doesn't write
        assert not ledger_path.exists()  # file not created


# ---------------------------------------------------------------------------
# K. ledger_no_append_when_not_flagged
# ---------------------------------------------------------------------------

class TestLedgerNoAppendWhenNotFlagged:
    def test_unflagged_node_not_written(self, tmp_path):
        ledger_path = tmp_path / "tape_onset_ledger.jsonl"
        payload = {
            "XLK": {"tape_onset_unconfirmed": False, "tape_onset_stats": {}},
            "XLV": {"tape_onset_unconfirmed": False, "tape_onset_stats": {}},
        }
        n = append_tape_onset_ledger(payload, "2026-07-09", ledger_path)
        assert n == 0
        assert not ledger_path.exists()


# ---------------------------------------------------------------------------
# L. compute_payload_structure
# ---------------------------------------------------------------------------

class TestComputePayloadStructure:
    def test_returns_dict_with_required_keys(self):
        panel = _make_flagged_panel(node="XLK", n_days=80)
        payload = compute_tape_onset_payload(panel, None)
        assert "XLK" in payload
        node_payload = payload["XLK"]
        assert "tape_onset_unconfirmed" in node_payload
        assert "tape_onset_stats" in node_payload
        assert isinstance(node_payload["tape_onset_unconfirmed"], bool)
        stats = node_payload["tape_onset_stats"]
        for key in ("n_flags", "p_onset_5d", "p_confirmed_10d", "false_positive_5d",
                    "window_start", "window_end"):
            assert key in stats, f"Missing key '{key}' in tape_onset_stats"

    def test_flagged_on_last_row(self):
        panel = _make_flagged_panel(node="XLK", n_days=80, flag_last=True)
        payload = compute_tape_onset_payload(panel, None)
        assert payload["XLK"]["tape_onset_unconfirmed"] is True

    def test_not_flagged_when_episode_active(self):
        panel = _make_flagged_panel(node="XLK", n_days=80, flag_last=True)
        latest_date = panel.xs("XLK", level="node").index[-1]
        # Episode active at latest date (onset before, not yet exhausted)
        episodes = _make_episodes(
            node="XLK",
            direction="in",
            onset_date=(latest_date - pd.Timedelta(days=5)).strftime("%Y-%m-%d"),
            exhausted_date=None,  # open episode
        )
        payload = compute_tape_onset_payload(panel, episodes)
        # Episode is active on latest date → flag suppressed
        assert payload["XLK"]["tape_onset_unconfirmed"] is False

    def test_empty_panel_returns_empty(self):
        panel = pd.DataFrame()
        payload = compute_tape_onset_payload(panel, None)
        assert payload == {}


# ---------------------------------------------------------------------------
# M. false_positive_explicit
# ---------------------------------------------------------------------------

class TestFalsePositiveExplicit:
    def test_false_positive_is_explicitly_printed(self):
        """Registration §3: false_positive_5d = 1 - p_onset_5d, printed explicitly."""
        panel = _make_panel(nodes=["XLU"], n_days=200, seed=7)
        node_panel = panel.xs("XLU", level="node").sort_index()
        # Force several flags in the middle of the panel
        node_panel = node_panel.copy()
        for i in range(20, 35):
            node_panel.iloc[i, node_panel.columns.get_loc("accel_z")] = 1.8
            node_panel.iloc[i, node_panel.columns.get_loc("vel_1w")] = 0.05
            node_panel.iloc[i, node_panel.columns.get_loc("vel_3m")] = 0.01
        stats = compute_tape_onset_stats(node_panel, None, "XLU")

        # The key must be present (explicit, not implied)
        assert "false_positive_5d" in stats

        if stats["p_onset_5d"] is not None:
            # Arithmetic identity
            expected_fp = round(1.0 - stats["p_onset_5d"], 4)
            assert abs((stats["false_positive_5d"] or 0) - expected_fp) < 1e-5
