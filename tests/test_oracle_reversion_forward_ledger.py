"""Tests for oracle_reversion_forward_ledger (P0) and oracle_reversion_state (P1).

All fixtures are SYNTHETIC — no real data files, no network.

Test inventory
--------------
(A) idempotency        — running the ledger writer twice produces the same rows
(B) pit_unmatured      — a manually seeded fire whose exit_date > latest_date is NOT graded
(C) pit_matured        — a manually seeded fire whose exit_date <= latest_date IS graded
(D) schema_conformance — every ledger row has exactly the frozen schema fields
(E) fire_matches_get_entry_dates — fires on latest_date match get_entry_dates output
(F) dedup_on_rerun     — rerunning does not duplicate ledger rows
(G) honest_n0_sidecar  — P1 sidecar has authority_level='display' and live.n_matured=0 at start
(H) fired_today_matches_ledger — fired_today in sidecar matches latest-date ledger rows
(I) fail_open_missing_ledger   — P1 sidecar fails open when ledger dir does not exist
(J) authority_always_display   — authority_level is always "display" regardless of hypothetical stats
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Synthetic data builders
# ---------------------------------------------------------------------------

def _make_panel(
    nodes: list[str],
    n_days: int = 120,
    start: str = "2023-01-02",
    seed: int = 99,
    washout_last_day: bool = True,
) -> pd.DataFrame:
    """Synthetic panel with all required columns.

    When washout_last_day=True, plants washout_w=1 on the final day so the
    nightly writer (which evaluates the latest date only) can detect a fire.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days, name="date")
    rows = []
    for node in nodes:
        ret = rng.normal(0.001, 0.01, n_days)
        rs = rng.normal(0, 0.008, n_days)
        vel_1w = np.cumsum(ret) * 0.02
        vel_1m = np.cumsum(ret) * 0.015
        vel_3m = np.cumsum(ret) * 0.01
        accel = vel_1w - vel_3m
        accel_z = (accel - accel.mean()) / (accel.std() + 1e-9)
        washout_w = np.zeros(n_days)
        if washout_last_day:
            washout_w[-1] = 1.0     # fire on the last date = today
        stochrsi_w_k = rng.uniform(0, 0.25, n_days)
        vix_pctile = rng.uniform(0.2, 0.6, n_days)
        spy_above_200d = np.ones(n_days, dtype=float)   # risk_on
        tlt_ret_10d = rng.normal(0, 0.005, n_days)
        cohesion = rng.uniform(0.3, 0.7, n_days)
        cohesion_chg = np.diff(cohesion, prepend=cohesion[0])
        breadth_50 = rng.uniform(0.3, 0.7, n_days)
        persistence = rng.uniform(0.4, 0.6, n_days)
        turnover_z = rng.normal(0, 1, n_days)
        stochrsi_w_d = rng.uniform(0, 0.3, n_days)
        cohesion_rebuild = np.zeros(n_days)
        oil_ret_10d = rng.normal(0, 0.01, n_days)

        df = pd.DataFrame({
            "ret": ret, "rs": rs, "vel_1w": vel_1w, "vel_1m": vel_1m,
            "vel_3m": vel_3m, "accel": accel, "accel_z": accel_z,
            "washout_w": washout_w, "stochrsi_w_k": stochrsi_w_k,
            "stochrsi_w_d": stochrsi_w_d, "vix_pctile": vix_pctile,
            "spy_above_200d": spy_above_200d, "tlt_ret_10d": tlt_ret_10d,
            "cohesion": cohesion, "cohesion_chg": cohesion_chg,
            "breadth_50": breadth_50, "persistence": persistence,
            "turnover_z": turnover_z, "cohesion_rebuild": cohesion_rebuild,
            "oil_ret_10d": oil_ret_10d,
        }, index=dates)
        df["node"] = node
        rows.append(df.reset_index().set_index(["node", "date"]))

    return pd.concat(rows)


def _make_episodes_empty() -> pd.DataFrame:
    return pd.DataFrame(columns=[
        "episode_id", "node", "direction", "onset_date",
        "confirmed_date", "undeniable_date",
    ])


def _make_registry_compound(compound_id: str = "TEST_WASHOUT") -> dict:
    """Minimal registry compound with reversion block and washout entry_rule."""
    return {
        "id": compound_id,
        "name": "Test washout compound",
        "family": "T",
        "status": "screened",
        "universe": {"tier": "s"},
        "entry_rule": {"col": "washout_w", "op": "gt", "value": 0},
        "condition_rule": None,
        "horizons": [21, 63],
        "live_n": 0,
        "live_effect": None,
        "mechanism_en": "Washout test",
        "mechanism_zh": "洗盘测试",
        "lineage": "test",
        "created": "2026-07-05",
        "reversion": {
            "gauntlet": "PASS",
            "prereg": "research/ORACLE_REVERSION_PROMOTION_PREREG.md",
            "exit_mode": "time",
            "window": 25,
            "exit": 21,
            "metric": "absolute",
            "n": 100,
            "wr": 0.70,
            "asym": 1.8,
            "ret_exit": 0.03,
            "mfe": 0.06,
            "mae": -0.03,
            "risk_on": {"n": 70, "ret_exit": 0.028, "wr": 0.68},
            "risk_off": {"n": 30, "ret_exit": 0.034, "wr": 0.73},
            "oos_holdout": {"n": 30, "ret_exit": 0.04, "wr": 0.72, "split": "2022-12-31"},
            "placebo": {"p95": 0.015, "pass": True, "real": 0.03},
            "asof": "2026-07-05",
            "note": "Test compound",
        },
    }


def _write_registry(tmp: Path, compounds: list[dict]) -> None:
    p = tmp / "oracle" / "compounds"
    p.mkdir(parents=True, exist_ok=True)
    (p / "registry.jsonl").write_text(
        "\n".join(json.dumps(c) for c in compounds) + "\n"
    )


def _write_panel(tmp: Path, panel: pd.DataFrame, tier: str = "s") -> None:
    p = tmp / "oracle"
    p.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(p / f"panel_{tier}.parquet")


def _write_episodes(tmp: Path, eps: pd.DataFrame, tier: str = "s") -> None:
    p = tmp / "oracle"
    p.mkdir(parents=True, exist_ok=True)
    eps.to_parquet(p / f"episodes_{tier}.parquet")


def _write_rotation_groups(tmp: Path) -> None:
    p = tmp / "oracle"
    p.mkdir(parents=True, exist_ok=True)
    (p / "rotation_groups.json").write_text(json.dumps({"complexes": []}))


def _setup_data_dir(
    tmp: Path,
    n_days: int = 120,
    washout_last_day: bool = True,
) -> pd.DataFrame:
    """Set up minimal data dir with panel, episodes, registry, rotation_groups."""
    nodes = ["node_A", "node_B"]
    panel = _make_panel(nodes, n_days=n_days, washout_last_day=washout_last_day)
    eps = _make_episodes_empty()
    registry = [_make_registry_compound()]
    _write_panel(tmp, panel)
    _write_episodes(tmp, eps)
    _write_registry(tmp, registry)
    _write_rotation_groups(tmp)
    return panel


def _seed_ledger(data_dir: Path, compound_id: str, rows: list[dict]) -> None:
    """Pre-seed a ledger with the given rows (for PIT tests)."""
    ledger_dir = data_dir / "oracle" / "reversion_forward"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    (ledger_dir / f"{compound_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )


# ---------------------------------------------------------------------------
# Frozen schema fields (per ORACLE_REVERSION_PROMOTION_PREREG.md)
# ---------------------------------------------------------------------------

FROZEN_SCHEMA_FIELDS = {
    "compound_id", "node", "tier", "fire_date", "exec_date", "exit_date",
    "regime", "ret_exit", "mfe", "mae", "matured",
}


# ---------------------------------------------------------------------------
# Test A — idempotency: two runs produce the same rows
# ---------------------------------------------------------------------------

def test_idempotency():
    """Running the ledger writer twice yields the same JSONL rows (dedup)."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _setup_data_dir(tmp, washout_last_day=True)

        # First run
        run_reversion_forward_ledger(tmp, dry_run=False)
        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        assert ledger_path.exists(), "Ledger not created on first run — washout must fire on latest date"
        rows_run1 = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert len(rows_run1) > 0, "Expected at least one fire on first run"

        # Second run — must NOT grow the ledger
        run_reversion_forward_ledger(tmp, dry_run=False)
        rows_run2 = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]

        assert len(rows_run1) == len(rows_run2), \
            f"Row count changed on second run: {len(rows_run1)} → {len(rows_run2)}"

        # Same fire_date keys
        keys1 = {(r["node"], r["fire_date"]) for r in rows_run1}
        keys2 = {(r["node"], r["fire_date"]) for r in rows_run2}
        assert keys1 == keys2, "Different fire keys on second run"


# ---------------------------------------------------------------------------
# Test B — PIT: a pre-seeded unmatured fire is NOT graded
# ---------------------------------------------------------------------------

def test_pit_unmatured_fire_not_graded():
    """A pre-seeded fire whose exit_date > latest panel date stays matured=False."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        panel = _setup_data_dir(tmp, n_days=50, washout_last_day=False)

        all_dates = panel.index.get_level_values("date").unique().sort_values()
        latest_date = all_dates[-1]
        latest_str = latest_date.isoformat()[:10]

        # Seed a fire with exit_date = latest_date + 30 calendar days (well in the future)
        future_exit = (latest_date + pd.Timedelta(days=30)).isoformat()[:10]
        seed_row = {
            "compound_id": "TEST_WASHOUT",
            "node": "node_A",
            "tier": "s",
            "fire_date": (latest_date - pd.Timedelta(days=5)).isoformat()[:10],
            "exec_date": (latest_date - pd.Timedelta(days=4)).isoformat()[:10],
            "exit_date": future_exit,
            "regime": "risk_on",
            "ret_exit": None,
            "mfe": None,
            "mae": None,
            "matured": False,
        }
        _seed_ledger(tmp, "TEST_WASHOUT", [seed_row])

        run_reversion_forward_ledger(tmp, dry_run=False)

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        seeded = [r for r in rows if r["node"] == "node_A"
                  and r["exit_date"] == future_exit]
        assert seeded, "Seeded row should still be in ledger"
        for r in seeded:
            assert r.get("matured") is False, \
                f"PIT violation: exit_date={future_exit} > latest={latest_str} but row was graded"
            assert r.get("ret_exit") is None, \
                "ret_exit must stay None for unmatured row"


# ---------------------------------------------------------------------------
# Test C — PIT: a pre-seeded matured fire IS graded
# ---------------------------------------------------------------------------

def test_pit_matured_fire_is_graded():
    """A pre-seeded fire whose exit_date <= latest panel date gets graded."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # Need enough data for grading: 120 days so exec+25 window fits
        panel = _setup_data_dir(tmp, n_days=120, washout_last_day=False)

        all_dates = panel.index.get_level_values("date").unique().sort_values()
        # Use dates well inside the panel so exec+25 window is not truncated
        fire_ts = all_dates[10]
        exec_ts = all_dates[11]
        exit_ts = all_dates[33]   # 11 + 21 + 1 = 33; inside 120

        seed_row = {
            "compound_id": "TEST_WASHOUT",
            "node": "node_A",
            "tier": "s",
            "fire_date": fire_ts.isoformat()[:10],
            "exec_date": exec_ts.isoformat()[:10],
            "exit_date": exit_ts.isoformat()[:10],
            "regime": "risk_on",
            "ret_exit": None,
            "mfe": None,
            "mae": None,
            "matured": False,
        }
        _seed_ledger(tmp, "TEST_WASHOUT", [seed_row])

        run_reversion_forward_ledger(tmp, dry_run=False)

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        seeded = [r for r in rows if r["node"] == "node_A"
                  and r["fire_date"] == fire_ts.isoformat()[:10]]
        assert seeded, "Seeded row should be in ledger"
        for r in seeded:
            assert r.get("matured") is True, \
                f"Row with exit_date={exit_ts.isoformat()[:10]} <= latest should be graded"
            assert r.get("ret_exit") is not None, "Matured row must have ret_exit filled"
            assert isinstance(r["ret_exit"], float), "ret_exit must be float"


# ---------------------------------------------------------------------------
# Test D — schema conformance
# ---------------------------------------------------------------------------

def test_schema_conformance():
    """Every row in the ledger has exactly the frozen schema fields (no extras, no missing)."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _setup_data_dir(tmp, washout_last_day=True)

        run_reversion_forward_ledger(tmp, dry_run=False)
        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        assert ledger_path.exists(), "Ledger not created — washout must fire on latest date"

        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert rows, "Expected at least one row"

        for r in rows:
            missing = FROZEN_SCHEMA_FIELDS - set(r.keys())
            extra = set(r.keys()) - FROZEN_SCHEMA_FIELDS
            assert not missing, f"Row missing fields: {missing}\nRow: {r}"
            assert not extra, f"Row has unexpected extra fields: {extra}\nRow: {r}"


# ---------------------------------------------------------------------------
# Test E — fire detection matches get_entry_dates
# ---------------------------------------------------------------------------

def test_fire_detection_matches_get_entry_dates():
    """Fires on latest panel date match what get_entry_dates directly reports."""
    from scripts.oracle_reversion_forward_ledger import (
        _load_reversion_compounds, _load_rotation_groups,
    )
    from scripts.oracle_reversion_screen import _load_panel, _load_episodes
    from engine.oracle.compounds import get_entry_dates, augment_panel_with_derived

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _setup_data_dir(tmp, washout_last_day=True)

        compounds = _load_reversion_compounds(tmp)
        assert len(compounds) == 1
        compound = compounds[0]

        rotation_groups = _load_rotation_groups(tmp)
        p = _load_panel(tmp, "s")
        eps = _load_episodes(tmp, "s")
        panel_aug = augment_panel_with_derived(p.copy())

        all_dates = panel_aug.index.get_level_values("date").unique().sort_values()
        latest_date = all_dates[-1]

        entry_dates = get_entry_dates(compound, panel_aug, eps, rotation_groups)
        # Nodes that fired on latest_date according to get_entry_dates
        expected_nodes = {
            node for node, dates in entry_dates.items()
            if isinstance(dates, pd.DatetimeIndex) and latest_date in dates
        }

        # Run the ledger and check what was recorded on latest_date
        from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger
        run_reversion_forward_ledger(tmp, dry_run=False)

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        recorded_nodes: set[str] = set()
        if ledger_path.exists():
            for line in ledger_path.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("fire_date", "").startswith(latest_date.isoformat()[:10]):
                    recorded_nodes.add(r["node"])

        assert recorded_nodes == expected_nodes, \
            f"Fire detection mismatch: recorded={recorded_nodes} expected={expected_nodes}"


# ---------------------------------------------------------------------------
# Test F — dedup on re-run (3 runs, same row count)
# ---------------------------------------------------------------------------

def test_dedup_on_rerun():
    """Running the ledger 3 times does not grow the row count."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        _setup_data_dir(tmp, washout_last_day=True)

        for _ in range(3):
            run_reversion_forward_ledger(tmp, dry_run=False)

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        assert ledger_path.exists(), "Ledger not created"

        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        assert rows, "Expected at least one row"

        keys = [(r["node"], r["fire_date"]) for r in rows]
        assert len(keys) == len(set(keys)), \
            f"Duplicate (node, fire_date) keys found after 3 runs: {keys}"


# ---------------------------------------------------------------------------
# Test G — honest n=0 sidecar at start of accrual
# ---------------------------------------------------------------------------

def test_honest_n0_sidecar():
    """P1 sidecar has authority_level='display' and live.n_matured=0 when ledger is empty."""
    from scripts.oracle_reversion_state import build_reversion_state

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        site_dir = tmp / "site"
        _setup_data_dir(tmp)
        # Do NOT run the forward ledger — no ledger files yet

        payload = build_reversion_state(tmp, site_dir, dry_run=True)

        assert payload.get("schema") == "oracle_reversion_state.v1", \
            f"Wrong schema: {payload.get('schema')}"
        assert "signals" in payload
        assert len(payload["signals"]) > 0, "Expected at least one signal"

        for sig in payload["signals"]:
            assert sig["authority_level"] == "display", \
                f"authority_level must be 'display', got: {sig['authority_level']}"
            assert sig["article2_surface"] == "display", \
                f"article2_surface must be 'display', got: {sig['article2_surface']}"
            live = sig.get("live", {})
            assert live.get("n_matured") == 0, \
                f"Expected n_matured=0 at start, got: {live.get('n_matured')}"
            # WR should be None at n=0 (not fabricated)
            assert live.get("wr") is None, \
                f"Expected wr=None at n=0 (honest), got: {live.get('wr')}"
            assert live.get("wilson_lower") is None, \
                f"Expected wilson_lower=None at n=0, got: {live.get('wilson_lower')}"


# ---------------------------------------------------------------------------
# Test H — fired_today matches ledger latest-date rows
# ---------------------------------------------------------------------------

def test_fired_today_matches_ledger():
    """fired_today in the sidecar matches nodes with fire_date == latest panel date."""
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger
    from scripts.oracle_reversion_state import build_reversion_state

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        site_dir = tmp / "site"
        # Washout fires on last day
        _setup_data_dir(tmp, washout_last_day=True)

        run_reversion_forward_ledger(tmp, dry_run=False)

        # Read what was recorded on latest date from the ledger
        from scripts.oracle_reversion_screen import _load_panel
        panel = _load_panel(tmp, "s")
        all_dates = panel.index.get_level_values("date").unique().sort_values()
        latest_str = all_dates[-1].isoformat()[:10]

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        expected_nodes: set[str] = set()
        if ledger_path.exists():
            for line in ledger_path.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r.get("fire_date", "").startswith(latest_str):
                    expected_nodes.add(r["node"])

        payload = build_reversion_state(tmp, site_dir, dry_run=True)
        found_sig = None
        for sig in payload["signals"]:
            if sig["id"] == "TEST_WASHOUT":
                found_sig = sig
                break

        assert found_sig is not None, "TEST_WASHOUT signal not in sidecar"
        got_nodes = set(found_sig.get("fired_today", []))
        assert got_nodes == expected_nodes, \
            f"fired_today mismatch: got={got_nodes} expected={expected_nodes}"


# ---------------------------------------------------------------------------
# Test I — fail-open when ledger directory does not exist
# ---------------------------------------------------------------------------

def test_fail_open_missing_ledger():
    """P1 sidecar builds successfully even if no ledger files exist (fail-open)."""
    from scripts.oracle_reversion_state import build_reversion_state

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        site_dir = tmp / "site"
        _setup_data_dir(tmp)
        # Ledger directory NOT created (no _seed_ledger, no run_reversion_forward_ledger)

        # Should not raise, should return a valid payload
        payload = build_reversion_state(tmp, site_dir, dry_run=True)
        assert isinstance(payload, dict)
        assert "signals" in payload
        for sig in payload["signals"]:
            assert sig["live"]["n_matured"] == 0, \
                "Expected n_matured=0 when ledger is missing (fail-open)"


# ---------------------------------------------------------------------------
# Test J — authority_level is always "display" regardless of live stats
# ---------------------------------------------------------------------------

def test_authority_always_display():
    """authority_level is 'display' unconditionally, even with many high-WR matured rows."""
    from scripts.oracle_reversion_state import build_reversion_state

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        site_dir = tmp / "site"
        _setup_data_dir(tmp)

        # Seed fake ledger with 30 high-WR matured rows (hypothetically above any authority gate)
        ledger_dir = tmp / "oracle" / "reversion_forward"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        fake_rows = []
        for i in range(30):
            fake_rows.append({
                "compound_id": "TEST_WASHOUT",
                "node": "node_A",
                "tier": "s",
                "fire_date": f"2024-01-{i+1:02d}",
                "exec_date": f"2024-01-{i+2:02d}",
                "exit_date": f"2024-02-{i+2:02d}",
                "regime": "risk_on",
                "ret_exit": 0.05,   # all wins
                "mfe": 0.08,
                "mae": -0.02,
                "matured": True,
            })
        (ledger_dir / "TEST_WASHOUT.jsonl").write_text(
            "\n".join(json.dumps(r) for r in fake_rows) + "\n"
        )

        payload = build_reversion_state(tmp, site_dir, dry_run=True)

        for sig in payload["signals"]:
            assert sig["authority_level"] == "display", \
                f"authority_level must ALWAYS be 'display', got: {sig['authority_level']}"
            assert sig["article2_surface"] == "display", \
                f"article2_surface must ALWAYS be 'display', got: {sig['article2_surface']}"


# ---------------------------------------------------------------------------
# Test K — PIT guard isolation: ONLY the ledger's exit_ts > latest_date guard
#          prevents grading (not _per_entry_rows' window/exit guard).
#
# This test fails if the guard at oracle_reversion_forward_ledger.py:317
# (`if exit_ts > latest_date: continue`) is removed. It does NOT rely on
# _per_entry_rows' own guards (exec_pos+window >= n or exit_pos >= n).
# ---------------------------------------------------------------------------

def test_pit_guard_is_independently_load_bearing():
    """The ledger PIT guard at line 317 is independently necessary.

    We seed a row where:
      - fire_date/exec_date are early in the panel (exec_pos=6, well inside n=60)
      - the 25-session window and 21-session exit would both fit inside the panel
        (exec_pos=6, exec_pos+21=27<60, exec_pos+25=31<60)
      - BUT exit_date stored in the ledger is set to a far-future calendar date
        (2099-01-01) that is > latest_date

    Without the PIT guard: _grade_rows would call _per_entry_rows with this fire.
    Since exec_pos is early and both exec_pos+21 and exec_pos+25 are < n,
    _per_entry_rows grades the entry successfully → ret_exit is filled → matured=True.

    With the PIT guard: exit_ts = 2099-01-01 > latest_date → skip to_grade → matured=False.
    """
    from scripts.oracle_reversion_forward_ledger import _grade_rows

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # 60-session panel; exec at position 6 → exec+21=27 < 60, exec+25=31 < 60
        panel = _setup_data_dir(tmp, n_days=60, washout_last_day=False)
        from engine.oracle.compounds import augment_panel_with_derived
        all_dates = panel.index.get_level_values("date").unique().sort_values()
        latest_date = all_dates[-1]  # day 59

        fire_ts = all_dates[5]
        exec_ts = all_dates[6]
        # Deliberately store a far-future exit_date (not in the panel at all)
        # so exit_ts > latest_date fires the PIT guard, NOT _per_entry_rows' guard.
        far_future_exit = "2099-01-01"

        compound = _make_registry_compound()

        seed_row = {
            "compound_id": "TEST_WASHOUT",
            "node": "node_A",
            "tier": "s",
            "fire_date": fire_ts.isoformat()[:10],
            "exec_date": exec_ts.isoformat()[:10],
            "exit_date": far_future_exit,
            "regime": "risk_on",
            "ret_exit": None,
            "mfe": None,
            "mae": None,
            "matured": False,
        }

        import pandas as pd
        panel_full = pd.read_parquet(tmp / "oracle" / "panel_s.parquet")
        panel_aug = augment_panel_with_derived(panel_full.copy())

        graded = _grade_rows([seed_row], compound, panel_aug, latest_date)

        assert len(graded) == 1
        assert graded[0]["matured"] is False, (
            "PIT guard failure: exit_date=2099-01-01 > latest_date but row was graded. "
            "The guard `if exit_ts > latest_date: continue` at line 317 is not operating."
        )
        assert graded[0]["ret_exit"] is None, (
            "ret_exit must remain None when PIT guard blocks grading"
        )


# ---------------------------------------------------------------------------
# Test L — Grading numeric contract: ret_exit value must equal _per_entry_rows output.
#
# Mutation-proof: if exit_sessions is changed or the return is sign-flipped,
# this test fails. It does NOT just assert ret_exit is not None (which would
# pass even with a corrupted grading horizon).
# ---------------------------------------------------------------------------

def test_pit_matured_grading_value_matches_per_entry_rows():
    """Graded ret_exit must equal the value produced by _per_entry_rows directly.

    Verifies the NUMERIC correctness of the grading contract, not just that
    ret_exit is non-None. A wrong exit horizon (+5 sessions), a sign flip, or
    a window mismatch would all produce a different value and fail this test.
    """
    from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger
    from scripts.oracle_reversion_screen import _per_entry_rows
    from engine.oracle.compounds import augment_panel_with_derived

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        # 120-day panel; fire at position 10, exec at 11, exit at 32 (11+21=32)
        panel = _setup_data_dir(tmp, n_days=120, washout_last_day=False)
        import pandas as pd
        all_dates = panel.index.get_level_values("date").unique().sort_values()

        fire_ts = all_dates[10]
        exec_ts = all_dates[11]
        exit_ts = all_dates[32]   # exec_pos(11) + exit_sessions(21) = 32

        seed_row = {
            "compound_id": "TEST_WASHOUT",
            "node": "node_A",
            "tier": "s",
            "fire_date": fire_ts.isoformat()[:10],
            "exec_date": exec_ts.isoformat()[:10],
            "exit_date": exit_ts.isoformat()[:10],
            "regime": "risk_on",
            "ret_exit": None,
            "mfe": None,
            "mae": None,
            "matured": False,
        }
        _seed_ledger(tmp, "TEST_WASHOUT", [seed_row])

        run_reversion_forward_ledger(tmp, dry_run=False)

        ledger_path = tmp / "oracle" / "reversion_forward" / "TEST_WASHOUT.jsonl"
        rows = [json.loads(l) for l in ledger_path.read_text().splitlines() if l.strip()]
        seeded = [r for r in rows if r["node"] == "node_A"
                  and r["fire_date"] == fire_ts.isoformat()[:10]]
        assert seeded, "Seeded row not in ledger"
        ledger_ret = seeded[0]["ret_exit"]
        assert ledger_ret is not None, "Matured row must have ret_exit"
        assert isinstance(ledger_ret, float), "ret_exit must be float"

        # Independently compute expected ret_exit via _per_entry_rows
        panel_full = pd.read_parquet(tmp / "oracle" / "panel_s.parquet")
        panel_aug = augment_panel_with_derived(panel_full.copy())

        per_entry = _per_entry_rows(
            {"node_A": pd.DatetimeIndex([fire_ts])},
            panel_aug,
            window=25,
            exit_sessions=21,
            exit_mode="time",
        )
        assert per_entry, "_per_entry_rows returned no rows for the seeded fire"
        expected_ret = per_entry[0]["ret_exit"]
        assert expected_ret is not None, "_per_entry_rows produced None ret_exit for a valid entry"

        assert abs(ledger_ret - expected_ret) < 1e-9, (
            f"ret_exit value mismatch: ledger={ledger_ret:.8f} vs _per_entry_rows={expected_ret:.8f}. "
            "This indicates a wrong exit horizon, window, or return computation in _grade_rows."
        )


# ---------------------------------------------------------------------------
# Test M — PIT base_rate: differs from full-panel base_rate when panel has a
#          regime break after the grading date.
#
# Verifies that _compute_base_rate_pit returns a value that is NOT equal to the
# full-panel base rate when future panel data would materially shift the result.
# ---------------------------------------------------------------------------

def test_pit_base_rate_differs_from_full_panel():
    """base_rate computed PIT (as_of) must differ from the full-panel base_rate
    when a regime break after as_of would change the result.

    Seeds two fires graded at different dates and verifies that restricting the
    denominator to panel dates <= as_of produces a different result from using
    the full panel.
    """
    from scripts.oracle_reversion_state import _compute_base_rate_pit
    import numpy as np

    # Build a panel with 120 sessions where returns are deliberately negative
    # in the LAST 30 sessions (simulating a bear-market break).
    # A full-panel base_rate would be dragged down by the bear tail;
    # a PIT base_rate at as_of = session[89] would not see it.
    rng = np.random.default_rng(42)
    n_days = 120
    dates = pd.bdate_range("2023-01-02", periods=n_days, name="date")

    node = "node_A"
    # Sessions 0-89: mild positive drift (ret ~ +0.3%)
    ret_bull = rng.normal(0.003, 0.008, 90)
    # Sessions 90-119: strong negative drift (ret ~ -0.8%) — regime break
    ret_bear = rng.normal(-0.008, 0.008, 30)
    ret = np.concatenate([ret_bull, ret_bear])

    df = pd.DataFrame({"ret": ret, "node": node}, index=dates)
    panel = df.reset_index().set_index(["node", "date"])

    # as_of = end of bull period (session 89)
    as_of_bull = dates[89]
    # as_of = end of full panel (session 119)
    as_of_full = dates[-1]

    pit_bull = _compute_base_rate_pit(panel, "s", "dual", as_of_bull)
    pit_full = _compute_base_rate_pit(panel, "s", "dual", as_of_full)

    assert pit_bull is not None, "_compute_base_rate_pit returned None for bull-end as_of"
    assert pit_full is not None, "_compute_base_rate_pit returned None for full-panel as_of"

    # The bear-regime tail should push pit_full lower than pit_bull
    assert pit_bull > pit_full, (
        f"PIT base_rate at bull-end ({pit_bull:.4f}) should exceed full-panel rate ({pit_full:.4f}). "
        "This suggests the as_of truncation is not applied correctly."
    )
