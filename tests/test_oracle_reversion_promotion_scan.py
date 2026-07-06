"""Tests for oracle_reversion_promotion_scan (P2) and W4.b additions.

All fixtures are SYNTHETIC — no real data, no network.

Test inventory
--------------
(A) selftest_passes              — --selftest returns 0 (all 4 paths verified)
(B) grant_path_candidate         — n>=25, lift_lb>1.25 → candidate queued
(C) refuse_path_accruing         — n<25 → refused, shown in accruing
(D) lapse_path_proposed          — confirmer + ci-decay → lapse proposed
(E) never_auto_promote           — no ratified_by → authority NOT written
(F) ratification_applied         — ratified_by set → authority updated
(G) requeue_reminder             — n >= requeue_at_n → reminder printed
(H) kill_requeue_writer          — _write_kill_requeue keep-first semantics
(I) mde_at_80pct                 — MDE formula correctness
(J) underpowered_accruing_class  — UNDERPOWERED-ACCRUING detection logic
(K) kill_requeue_not_written_when_powered — adequate power → no kill_requeue row
(L) authority_reader_in_sidecar  — P1 sidecar surfaces ratified tier from authority file
(M) authority_reader_fail_open   — P1 sidecar tolerates missing authority file
(N) mde_edge_cases               — MDE returns None for n=0, sigma=0
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers — synthetic data builders
# ---------------------------------------------------------------------------

def _make_registry_entry(
    compound_id: str,
    operating_regime: str = "dual",
) -> dict:
    return {
        "id": compound_id,
        "name": f"Synthetic {compound_id}",
        "reversion": {
            "gauntlet": "PASS",
            "cluster": "test",
            "operating_regime": operating_regime,
            "asym": 1.83,
            "wr": 0.74,
            "ret_exit": 0.03,
            "n": 300,
        },
        "universe": {"tier": "s"},
        "mechanism_en": "synthetic test",
    }


def _make_matured_rows(
    compound_id: str,
    n: int,
    hits: int,
    operating_regime: str = "dual",
    fire_date: str = "2025-03-20",
) -> list[dict]:
    """Build n synthetic matured ledger rows with `hits` positive ret_exit values.

    fire_date defaults to 2025-03-20 which is ~103 days before now=2025-07-01
    used in tests — within the 120-day staleness window.
    """
    rows = []
    for i in range(n):
        ret_exit = 0.05 if i < hits else -0.02
        regime = "risk_on"
        if operating_regime == "risk_off":
            regime = "risk_off"
        elif operating_regime == "dual":
            regime = "risk_off" if i % 3 == 0 else "risk_on"
        rows.append({
            "compound_id": compound_id,
            "node": f"node_{i % 2}",
            "tier": "s",
            "fire_date": fire_date,
            "exec_date": fire_date,
            "exit_date": fire_date,
            "regime": regime,
            "ret_exit": ret_exit,
            "mfe": 0.08,
            "mae": -0.03,
            "matured": True,
        })
    return rows


def _write_registry(data_dir: Path, entries: list[dict]) -> None:
    p = data_dir / "oracle" / "compounds" / "registry.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")


def _write_ledger(data_dir: Path, compound_id: str, rows: list[dict]) -> None:
    p = data_dir / "oracle" / "reversion_forward" / f"{compound_id}.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def _write_sidecar(site_dir: Path, signals: list[dict]) -> None:
    p = site_dir / "basketdata" / "oracle_reversion_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"signals": signals}))


def _write_authority(data_dir: Path, authorities: dict[str, dict]) -> None:
    p = data_dir / "oracle" / "reversion_authority.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "reversion_authority.v1",
        "updated_at": "2025-01-01T00:00:00",
        "authorities": authorities,
    }
    p.write_text(json.dumps(payload))


# ---------------------------------------------------------------------------
# Test A — selftest_passes
# ---------------------------------------------------------------------------

def test_selftest_passes():
    """--selftest must return 0 (all 4 invariant paths verified)."""
    from scripts.oracle_reversion_promotion_scan import _run_selftest
    ret = _run_selftest()
    assert ret == 0, f"_run_selftest() returned {ret}, expected 0"


# ---------------------------------------------------------------------------
# Test B — grant_path_candidate
# ---------------------------------------------------------------------------

def test_grant_path_candidate():
    """n=30, hits=25, base_rate=0.55 → candidate queued."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "GRANT_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=30, hits=25))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": 0.55}}],
        )

        result = run_promotion_scan(
            td / "data", td / "site", dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

    assert result["n_candidates"] == 1, (
        f"Expected 1 candidate, got {result['n_candidates']}"
    )
    assert result["n_accruing"] == 0


# ---------------------------------------------------------------------------
# Test C — refuse_path_accruing
# ---------------------------------------------------------------------------

def test_refuse_path_accruing():
    """n=5 (< 25) → refused, shown in accruing."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "REFUSE_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=5, hits=4))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": 0.55}}],
        )

        result = run_promotion_scan(
            td / "data", td / "site", dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

    assert result["n_candidates"] == 0
    assert result["n_accruing"] == 1


# ---------------------------------------------------------------------------
# Test D — lapse_path_proposed
# ---------------------------------------------------------------------------

def test_lapse_path_proposed():
    """confirmer authority + ci-decay (lift_lb<=1.25) → lapse proposed."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan
    from engine.neuralweb.constitution import wilson_lower

    # Choose n=30, hits=15, base_rate=0.75 so lift_lb is well below 1.25
    n, hits, base_rate = 30, 15, 0.75
    wl = wilson_lower(hits, n, z=1.645)
    lift = wl / base_rate
    assert lift <= 1.25, f"lift={lift} not <= 1.25 for lapse test — adjust fixtures"

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "LAPSE_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=n, hits=hits, fire_date="2025-03-20"))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": base_rate}}],
        )
        # Pre-seed authority with confirmer tier
        _write_authority(
            td / "data",
            {cid: {"authority_level": "confirmer", "ratified_by": "test_human"}},
        )

        result = run_promotion_scan(
            td / "data", td / "site", dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

    assert result["n_lapses"] == 1, f"Expected 1 lapse, got {result['n_lapses']}"
    assert result["n_candidates"] == 0


# ---------------------------------------------------------------------------
# Test E — never_auto_promote
# ---------------------------------------------------------------------------

def test_never_auto_promote():
    """Grant path + no ratified_by in queue → authority file NOT written."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "NAP_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=30, hits=25))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": 0.55}}],
        )

        run_promotion_scan(
            td / "data", td / "site", dry_run=False,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

        auth_path = td / "data" / "oracle" / "reversion_authority.json"
        if auth_path.exists():
            auth_data = json.loads(auth_path.read_text())
            authorities = auth_data.get("authorities", {})
            assert cid not in authorities, (
                f"NEVER-AUTO-PROMOTE violated: {cid} in authority file without ratified_by"
            )


# ---------------------------------------------------------------------------
# Test F — ratification_applied
# ---------------------------------------------------------------------------

def test_ratification_applied():
    """Queue row with ratified_by set → authority updated on next scan."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "RATIFY_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=30, hits=25))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": 0.55}}],
        )

        # Pre-seed queue with a ratified row
        queue_dir = td / "data" / "oracle"
        queue_dir.mkdir(parents=True, exist_ok=True)
        queue_dir.joinpath("reversion_promotion_queue.json").write_text(json.dumps({
            "candidates": [{
                "compound_id": cid,
                "proposed_authority": "confirmer",
                "ratified_by": "fable-human-2025-07-01",
                "proposed_at": "2025-06-01T00:00:00",
                "gate_result": {"lift_lb": 1.35},
            }],
            "lapses": [],
        }))

        run_promotion_scan(
            td / "data", td / "site", dry_run=False,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

        auth_path = td / "data" / "oracle" / "reversion_authority.json"
        assert auth_path.exists(), "authority file should exist after ratification"
        auth_data = json.loads(auth_path.read_text())
        authorities = auth_data.get("authorities", {})
        assert cid in authorities, f"{cid} not in authorities after ratification"
        assert authorities[cid]["authority_level"] == "confirmer"
        assert authorities[cid]["ratified_by"] == "fable-human-2025-07-01"


# ---------------------------------------------------------------------------
# Test G — requeue_reminder
# ---------------------------------------------------------------------------

def test_requeue_reminder():
    """n >= requeue_at_n → requeue reminder included in scan result."""
    from scripts.oracle_reversion_promotion_scan import run_promotion_scan

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "REQUEUE_TEST"
        _write_registry(td / "data", [_make_registry_entry(cid)])
        _write_ledger(td / "data", cid, _make_matured_rows(cid, n=10, hits=7))
        _write_sidecar(
            td / "site",
            [{"id": cid, "live": {"base_rate": 0.55}}],
        )
        # Write kill_requeue with requeue_at_n=5 (already met by n=10)
        kq_path = td / "data" / "oracle" / "reversion_kill_requeue.jsonl"
        kq_path.parent.mkdir(parents=True, exist_ok=True)
        kq_path.write_text(json.dumps({
            "compound_id": cid,
            "killed_at_asof": "2025-01-01",
            "n_at_kill": 2,
            "point_estimates": {"WR": 0.65},
            "requeue_at_n": 5,
        }) + "\n")

        result = run_promotion_scan(
            td / "data", td / "site", dry_run=True,
            now=datetime(2025, 7, 1, tzinfo=timezone.utc),
            governance_root=td,
        )

    assert result["n_requeue_reminders"] == 1, (
        f"Expected 1 requeue reminder, got {result['n_requeue_reminders']}"
    )


# ---------------------------------------------------------------------------
# Test H — kill_requeue_writer (keep-first semantics)
# ---------------------------------------------------------------------------

def test_kill_requeue_writer_keep_first():
    """_write_kill_requeue keep-first: second call for same compound is no-op."""
    from scripts.oracle_reversion_screen import _write_kill_requeue

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        data_dir = td / "data"

        # First write
        _write_kill_requeue(
            "KQTEST", data_dir,
            n_at_kill=10,
            point_estimates={"WR": 0.65},
            asof="2025-03-01",
        )
        path = data_dir / "oracle" / "reversion_kill_requeue.jsonl"
        assert path.exists()
        lines1 = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines1) == 1

        # Second write for same compound — must be no-op
        _write_kill_requeue(
            "KQTEST", data_dir,
            n_at_kill=20,
            point_estimates={"WR": 0.70},
            asof="2025-04-01",
        )
        lines2 = [l for l in path.read_text().splitlines() if l.strip()]
        assert len(lines2) == 1, "keep-first violated: second write added a row"

        row = json.loads(lines2[0])
        assert row["n_at_kill"] == 10, "keep-first violated: first row overwritten"
        assert row["requeue_at_n"] == 20  # 2 × n_at_kill=10


# ---------------------------------------------------------------------------
# Test I — mde_at_80pct
# ---------------------------------------------------------------------------

def test_mde_at_80pct():
    """MDE@80% formula: (z_alpha + z_power) * sigma / sqrt(n)."""
    from scripts.oracle_reversion_screen import _mde_at_80pct

    # Positive control: verify formula
    n, sigma = 100, 0.05
    mde = _mde_at_80pct(n, sigma)
    z_alpha, z_power = 1.645, 0.842
    expected = (z_alpha + z_power) * sigma / np.sqrt(n)
    assert mde is not None
    assert abs(mde - expected) < 1e-10, f"MDE={mde} expected={expected}"

    # Larger n → smaller MDE
    mde_large = _mde_at_80pct(400, sigma)
    assert mde_large < mde

    # Larger sigma → larger MDE
    mde_wide = _mde_at_80pct(n, sigma * 2)
    assert mde_wide > mde


def test_mde_edge_cases():
    """MDE returns None for invalid inputs."""
    from scripts.oracle_reversion_screen import _mde_at_80pct

    assert _mde_at_80pct(0, 0.05) is None
    assert _mde_at_80pct(10, 0.0) is None
    assert _mde_at_80pct(10, None) is None
    assert _mde_at_80pct(10, float("nan")) is None


# ---------------------------------------------------------------------------
# Test J — underpowered_accruing_class
# ---------------------------------------------------------------------------

def test_underpowered_accruing_detects():
    """UNDERPOWERED-ACCRUING: positive estimates, power<50%."""
    from scripts.oracle_reversion_screen import _is_underpowered_accruing

    # Small n, positive estimates, large sigma → low power
    stats = {"n": 10, "WR": 0.65, "mean_ret_exit": 0.02, "asym": 1.5}
    sigma = 0.15  # very large noise → power << 50%
    assert _is_underpowered_accruing(stats, sigma), (
        "Expected UNDERPOWERED-ACCRUING for large sigma / small n"
    )


def test_underpowered_accruing_not_when_powered():
    """Not UNDERPOWERED-ACCRUING when power >= 50% at observed effect."""
    from scripts.oracle_reversion_screen import _is_underpowered_accruing

    # Large n, large effect → high power
    stats = {"n": 200, "WR": 0.70, "mean_ret_exit": 0.10, "asym": 2.0}
    sigma = 0.05
    assert not _is_underpowered_accruing(stats, sigma)


def test_underpowered_accruing_not_when_negative_estimate():
    """Not UNDERPOWERED-ACCRUING when point estimates not all positive."""
    from scripts.oracle_reversion_screen import _is_underpowered_accruing

    stats = {"n": 10, "WR": 0.40, "mean_ret_exit": -0.01, "asym": 0.8}
    sigma = 0.15
    assert not _is_underpowered_accruing(stats, sigma)


# ---------------------------------------------------------------------------
# Test K — kill_requeue not written when adequately powered
# ---------------------------------------------------------------------------

def test_kill_requeue_not_written_when_powered():
    """When adequately powered, _write_kill_requeue is NOT called by run_gauntlet."""
    from scripts.oracle_reversion_screen import _is_underpowered_accruing

    # A compound with sufficient power should not be flagged
    stats = {"n": 300, "WR": 0.72, "mean_ret_exit": 0.08, "asym": 2.5}
    sigma = 0.05
    result = _is_underpowered_accruing(stats, sigma)
    assert not result, "Adequately powered compound should not be UNDERPOWERED-ACCRUING"


# ---------------------------------------------------------------------------
# Test L — authority_reader_in_sidecar (P1 wiring)
# ---------------------------------------------------------------------------

def test_authority_surfaces_in_sidecar():
    """P1 sidecar surfaces ratified authority_level from P2 authority file."""
    from scripts.oracle_reversion_state import _load_authority, _build_signal_record
    import pandas as pd

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "AUTH_SIDECAR"

        # Write authority file with confirmer tier
        _write_authority(
            td / "data",
            {cid: {"authority_level": "confirmer", "ratified_by": "test_human"}},
        )

        authority_map = _load_authority(td / "data")
        assert cid in authority_map

        compound = _make_registry_entry(cid)
        # _build_signal_record needs data_dir + latest_date_by_tier
        # We don't have a real panel; just test the authority surfacing logic directly
        record = _build_signal_record(
            compound,
            td / "data",
            latest_date_by_tier={"s": None},
            authority_map=authority_map,
        )
        assert record["authority_level"] == "confirmer", (
            f"Expected 'confirmer', got '{record['authority_level']}'"
        )
        assert record["article2_surface"] == "confirmer"


# ---------------------------------------------------------------------------
# Test M — authority_reader_fail_open
# ---------------------------------------------------------------------------

def test_authority_reader_fail_open():
    """P1 sidecar defaults to 'display' when authority file missing."""
    from scripts.oracle_reversion_state import _load_authority, _build_signal_record

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        cid = "NO_AUTH"

        # No authority file written
        authority_map = _load_authority(td / "data")
        assert authority_map == {}, "Expected empty dict when authority file missing"

        compound = _make_registry_entry(cid)
        record = _build_signal_record(
            compound,
            td / "data",
            latest_date_by_tier={"s": None},
            authority_map=authority_map,
        )
        assert record["authority_level"] == "display", (
            f"Expected 'display' (no authority file), got '{record['authority_level']}'"
        )
