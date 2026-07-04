"""Hermetic tests for Oracle W-B4 Sentinels.

engine/oracle/sentinels.py  +  GRAMMAR_VERSION in oracle_screen._params_hash

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory
--------------
A. grammar_version_in_params_hash:
     same spec + different GRAMMAR_VERSION → two distinct params_hash values;
     same spec + same version → one hash.

B. panel_drift_null_rate_trips:
     Planted null-rate jump > 0.15 absolute trips the check and writes a
     sentinel_log row.

C. panel_drift_backward_date_trips:
     Max date moving BACKWARD trips the check.

D. panel_drift_schema_change_trips:
     Column-set change (added/removed column) trips the check.

E. panel_drift_first_run_silent:
     First run (no prior sentinel_state.json) seeds the file silently —
     no sentinel_log rows written.

F. decay_watch_sign_flip_fires_at_n30:
     Planted sign-flip with n_live >= 30 fires decay_watch.

G. decay_watch_sign_flip_silent_below_n10:
     Planted sign-flip with n_live < 10 stays silent.

H. ledger_integrity_torn_line_counted:
     A planted torn/corrupt JSON line in the ledger is counted and trips
     the sentinel, not crashed.

I. ledger_integrity_clean_no_trip:
     A clean ledger produces no trip.

J. node_count_drop_trips:
     Node count drop > 10% trips the check.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import os
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_data_dir(tmp_path: Path) -> Path:
    """Create a minimal synthetic oracle data layout under tmp_path."""
    oracle_dir = tmp_path / "oracle"
    oracle_dir.mkdir(parents=True)
    (oracle_dir / "compounds").mkdir(parents=True)
    return tmp_path


def _write_manifest(data_dir: Path, *, tier_s_node_count: int = 11,
                    date_range_end: str = "2026-07-01",
                    columns: list[str] | None = None,
                    null_rates: dict | None = None) -> None:
    """Write a synthetic manifest.json under data_dir/oracle/."""
    cols = columns or ["ret", "rs", "vel_1w"]
    nr = null_rates or {c: 0.001 for c in cols}
    manifest = {
        "schema_version": 1,
        "built_at": "2026-07-04T00:00:00Z",
        "column_schema": cols,
        "tier_s": {
            "tier": "s",
            "node_count": tier_s_node_count,
            "date_range": ["1998-12-22", date_range_end],
            "rows": tier_s_node_count * 6000,
            "null_rates": nr,
        },
    }
    (data_dir / "oracle" / "manifest.json").write_text(json.dumps(manifest))


def _write_sentinel_state(data_dir: Path, snapshot: dict) -> None:
    state = {"panel_snapshot": snapshot,
             "panel_snapshot_updated_at": "2026-07-03T00:00:00Z"}
    (data_dir / "oracle" / "sentinel_state.json").write_text(json.dumps(state))


# ---------------------------------------------------------------------------
# A. GRAMMAR_VERSION in params_hash
# ---------------------------------------------------------------------------

def _make_hash(compound_id: str, screener: str, tier: str,
               horizons: list[int], grammar_version: str) -> str:
    """Mirror the oracle_screen._params_hash logic for testing."""
    payload = (
        f"{compound_id}|{screener}|{tier}|{sorted(horizons)}"
        f"|grammar={grammar_version}"
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def test_grammar_version_different_versions_produce_different_hashes():
    """Same spec + different GRAMMAR_VERSION → two distinct hashes (forces new ledger row)."""
    h1 = _make_hash("A2", "tier1_screen_v1", "s", [21, 63], "1.0.0")
    h2 = _make_hash("A2", "tier1_screen_v1", "s", [21, 63], "1.1.0")
    assert h1 != h2, (
        "GRAMMAR_VERSION must be part of params_hash so evaluator semantics "
        "changes force a new ledger row"
    )


def test_grammar_version_same_version_stable_hash():
    """Same spec + same GRAMMAR_VERSION → same hash every time (keep-first is deterministic)."""
    h1 = _make_hash("A2", "tier1_screen_v1", "s", [21, 63], "1.1.0")
    h2 = _make_hash("A2", "tier1_screen_v1", "s", [21, 63], "1.1.0")
    assert h1 == h2


def test_grammar_version_imported_constant():
    """GRAMMAR_VERSION is importable from engine.oracle.compounds and is a string."""
    from engine.oracle.compounds import GRAMMAR_VERSION
    assert isinstance(GRAMMAR_VERSION, str)
    assert GRAMMAR_VERSION  # non-empty


def test_params_hash_includes_grammar_version():
    """The actual _params_hash in oracle_screen includes GRAMMAR_VERSION."""
    # Verify by computing what the hash WOULD be without grammar and confirm
    # it differs from what oracle_screen actually produces.
    from scripts.oracle_screen import _params_hash
    from engine.oracle.compounds import GRAMMAR_VERSION

    h_actual = _params_hash("TEST", "tier1_screen_v1", "s", [21, 63])
    h_without_grammar = hashlib.sha256(
        f"TEST|tier1_screen_v1|s|{sorted([21, 63])}".encode()
    ).hexdigest()[:12]
    assert h_actual != h_without_grammar, (
        "_params_hash must incorporate GRAMMAR_VERSION; "
        "without it the hash matches the pre-W-B4 formula"
    )

    # Also confirm it matches the expected formula with grammar
    h_expected = hashlib.sha256(
        f"TEST|tier1_screen_v1|s|{sorted([21, 63])}|grammar={GRAMMAR_VERSION}".encode()
    ).hexdigest()[:12]
    assert h_actual == h_expected


# ---------------------------------------------------------------------------
# B. Panel drift — null-rate jump trips
# ---------------------------------------------------------------------------

def test_panel_drift_null_rate_jump_trips(tmp_path):
    from engine.oracle.sentinels import check_panel_drift

    data_dir = _make_data_dir(tmp_path)
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    cols = ["ret", "rs", "vel_1w"]
    # Write a prior snapshot with low null-rates
    prior_snapshot = {
        "tier_s.node_count": 11,
        "tier_s.date_range": ["1998-12-22", "2026-07-01"],
        "tier_s.columns": sorted(cols),
        "tier_s.null_rate.ret": 0.001,
        "tier_s.null_rate.rs": 0.001,
    }
    _write_sentinel_state(data_dir, prior_snapshot)

    # Write tonight's manifest with a big null-rate jump on "ret"
    _write_manifest(data_dir, null_rates={"ret": 0.20, "rs": 0.001, "vel_1w": 0.001})

    trips = check_panel_drift(data_dir, state_path, log_path)
    assert any("null-rate" in t and "ret" in t for t in trips), (
        f"Expected null-rate trip for 'ret'; got: {trips}"
    )
    # Sentinel log should have a row
    assert log_path.exists()
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(r.get("check") == "panel_drift" for r in rows)


# ---------------------------------------------------------------------------
# C. Panel drift — backward date trips
# ---------------------------------------------------------------------------

def test_panel_drift_backward_date_trips(tmp_path):
    from engine.oracle.sentinels import check_panel_drift

    data_dir = _make_data_dir(tmp_path)
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    cols = ["ret", "rs"]
    prior_snapshot = {
        "tier_s.node_count": 11,
        "tier_s.date_range": ["1998-12-22", "2026-07-03"],
        "tier_s.columns": sorted(cols),
        "tier_s.null_rate.ret": 0.001,
    }
    _write_sentinel_state(data_dir, prior_snapshot)

    # Tonight's date_range max goes BACKWARD (regression)
    _write_manifest(data_dir, date_range_end="2026-07-01")

    trips = check_panel_drift(data_dir, state_path, log_path)
    assert any("regressed" in t or "BACKWARD" in t.upper() or "max date" in t.lower()
               for t in trips), (
        f"Expected date-range regression trip; got: {trips}"
    )


# ---------------------------------------------------------------------------
# D. Panel drift — schema change trips
# ---------------------------------------------------------------------------

def test_panel_drift_schema_change_trips(tmp_path):
    from engine.oracle.sentinels import check_panel_drift

    data_dir = _make_data_dir(tmp_path)
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    prior_cols = ["ret", "rs", "vel_1w"]
    prior_snapshot = {
        "tier_s.node_count": 11,
        "tier_s.date_range": ["1998-12-22", "2026-07-01"],
        "tier_s.columns": sorted(prior_cols),
        "tier_s.null_rate.ret": 0.001,
    }
    _write_sentinel_state(data_dir, prior_snapshot)

    # Tonight drops "vel_1w" and adds a new column "new_col"
    tonight_cols = ["ret", "rs", "new_col"]
    _write_manifest(data_dir, columns=tonight_cols)

    trips = check_panel_drift(data_dir, state_path, log_path)
    assert any("schema" in t.lower() for t in trips), (
        f"Expected schema-change trip; got: {trips}"
    )


# ---------------------------------------------------------------------------
# E. Panel drift — first run seeds silently (no sentinel_log rows)
# ---------------------------------------------------------------------------

def test_panel_drift_first_run_silent(tmp_path):
    from engine.oracle.sentinels import check_panel_drift

    data_dir = _make_data_dir(tmp_path)
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    # No prior sentinel_state.json
    _write_manifest(data_dir)

    trips = check_panel_drift(data_dir, state_path, log_path)
    assert trips == [], f"First run should be silent; got trips: {trips}"

    # State should have been seeded
    assert state_path.exists(), "sentinel_state.json should be seeded on first run"

    # No sentinel_log rows from a first-run seed
    if log_path.exists():
        rows = [l for l in log_path.read_text().splitlines() if l.strip()]
        assert rows == [], f"No log rows expected on first run; got {rows}"


# ---------------------------------------------------------------------------
# F. Edge decay — sign flip fires at n >= 30
# ---------------------------------------------------------------------------

def test_decay_watch_sign_flip_fires_at_n30(tmp_path):
    from engine.oracle.sentinels import check_edge_decay, _append_sentinel_log
    from engine.oracle.contract import _DISPLAY_WITH_EDGE_COMPOUNDS

    data_dir = _make_data_dir(tmp_path)
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    # We need to plant:
    # 1. A p3_results.json with a POSITIVE published stat for ep_in_onset_21d
    # 2. A forward_ledger.jsonl with n>=30 NEGATIVE matured rows (sign flip)
    gauntlet_dir = data_dir / "oracle" / "gauntlet"
    gauntlet_dir.mkdir(parents=True)

    p3 = {
        "timing": {
            "ep_in_onset_21d": {"mean_excess": 0.012},
            "ep_out_onset_5d": {"mean_excess": 0.008},
        }
    }
    (gauntlet_dir / "p3_results.json").write_text(json.dumps(p3))

    # Plant 35 matured forward_ledger rows for ep_in_onset_21d with NEGATIVE excess
    fwd_path = data_dir / "oracle" / "forward_ledger.jsonl"
    with open(fwd_path, "w") as fh:
        for i in range(35):
            row = {
                "episode_id": f"XLK::in::2025-0{1 + i % 9:02d}-01",
                "node": "XLK",
                "direction": "in",
                "tier": "onset",
                "onset_date": f"2025-0{1 + i % 9:02d}-01",
                "pit_stamp": f"2025-0{1 + i % 9:02d}-01",
                "cell_tags": {"entry_onset_21d": True},
                "excess_21d": -0.025,  # NEGATIVE — sign flip vs published +0.012
            }
            fh.write(json.dumps(row) + "\n")

    trips = check_edge_decay(data_dir, log_path)
    assert any("ep_in_onset_21d" in t for t in trips), (
        f"Expected decay_watch trip for ep_in_onset_21d sign-flip; got: {trips}"
    )
    # Sentinel log should exist and have a row
    assert log_path.exists()
    rows = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(r.get("check") == "edge_decay" for r in rows)


# ---------------------------------------------------------------------------
# G. Edge decay — sign flip SILENT at n < 10
# ---------------------------------------------------------------------------

def test_decay_watch_sign_flip_silent_below_n10(tmp_path):
    from engine.oracle.sentinels import check_edge_decay

    data_dir = _make_data_dir(tmp_path)
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    gauntlet_dir = data_dir / "oracle" / "gauntlet"
    gauntlet_dir.mkdir(parents=True)

    p3 = {"timing": {"ep_in_onset_21d": {"mean_excess": 0.012}}}
    (gauntlet_dir / "p3_results.json").write_text(json.dumps(p3))

    # Only 5 rows — below the n < 10 threshold
    fwd_path = data_dir / "oracle" / "forward_ledger.jsonl"
    with open(fwd_path, "w") as fh:
        for i in range(5):
            row = {
                "episode_id": f"XLK::in::2025-0{i+1:02d}-01",
                "node": "XLK",
                "direction": "in",
                "tier": "onset",
                "onset_date": f"2025-0{i+1:02d}-01",
                "pit_stamp": f"2025-0{i+1:02d}-01",
                "cell_tags": {"entry_onset_21d": True},
                "excess_21d": -0.025,
            }
            fh.write(json.dumps(row) + "\n")

    trips = check_edge_decay(data_dir, log_path)
    assert trips == [], (
        f"n_live < 10 should be silent; got trips: {trips}"
    )


# ---------------------------------------------------------------------------
# H. Ledger integrity — torn line counted, not crashed
# ---------------------------------------------------------------------------

def test_ledger_integrity_torn_line_counted(tmp_path):
    from engine.oracle.sentinels import check_ledger_integrity

    data_dir = _make_data_dir(tmp_path)
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    # Write a trial_ledger with one good row and one corrupt/torn line
    tl_path = data_dir / "oracle" / "compounds" / "trial_ledger.jsonl"
    with open(tl_path, "w") as fh:
        fh.write(json.dumps({"compound_id": "A2", "n": 100}) + "\n")
        fh.write('{"compound_id": "A2", "n": CORRUPT_LINE\n')  # not valid JSON

    trips = check_ledger_integrity(data_dir, log_path)
    assert any("trial_ledger" in t and "unparseable" in t for t in trips), (
        f"Expected unparseable line trip for trial_ledger; got: {trips}"
    )
    # Sentinel log should exist
    assert log_path.exists()


# ---------------------------------------------------------------------------
# I. Ledger integrity — clean ledger no trip
# ---------------------------------------------------------------------------

def test_ledger_integrity_clean_no_trip(tmp_path):
    from engine.oracle.sentinels import check_ledger_integrity

    data_dir = _make_data_dir(tmp_path)
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    tl_path = data_dir / "oracle" / "compounds" / "trial_ledger.jsonl"
    with open(tl_path, "w") as fh:
        fh.write(json.dumps({"compound_id": "A2", "n": 100}) + "\n")
        fh.write(json.dumps({"compound_id": "A3", "n": 50}) + "\n")

    trips = check_ledger_integrity(data_dir, log_path)
    assert trips == [], f"Clean ledger should produce no trips; got: {trips}"


# ---------------------------------------------------------------------------
# J. Panel drift — node count drop > 10% trips
# ---------------------------------------------------------------------------

def test_panel_drift_node_count_drop_trips(tmp_path):
    from engine.oracle.sentinels import check_panel_drift

    data_dir = _make_data_dir(tmp_path)
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    # Prior: 11 nodes; tonight: 9 (drop = 2/11 = 18.2% > 10%)
    prior_snapshot = {
        "tier_s.node_count": 11,
        "tier_s.date_range": ["1998-12-22", "2026-07-01"],
        "tier_s.columns": sorted(["ret", "rs"]),
        "tier_s.null_rate.ret": 0.001,
    }
    _write_sentinel_state(data_dir, prior_snapshot)
    _write_manifest(data_dir, tier_s_node_count=9)

    trips = check_panel_drift(data_dir, state_path, log_path)
    assert any("node count" in t.lower() for t in trips), (
        f"Expected node-count drop trip; got: {trips}"
    )
