"""Hermetic tests for oracle_nightly Step 20 — active-episode analogues (O3).

WHY THIS SUITE EXISTS
---------------------
engine/oracle/memory.py::find_analogues and its producer
scripts/build_oracle_memory.py were both fully built, but the producer was
scheduled NOWHERE (no config/dag.yml node, no nightly step).  So
data/oracle/memory_active_analogues.json was never written and
oracle_state.json active_episodes[].analogues was permanently null in
production — a built organ with no heartbeat.  Step 20 gives it one.

What these tests pin (each can SEE its failure):
  1. absent inputs        → no crash, no file, step returns False
  2. synthetic inputs     → file written, keyed the way the REAL reader indexes
                            it (engine/oracle/live.py::_load_active_analogues,
                            imported here rather than restated), every block
                            carrying the exact descriptive note
  3. re-run               → idempotent payload + CLEAN overwrite (a block for an
                            episode that has since exhausted must disappear, not
                            linger forever)
  4. base rates untouched → Step 4a hand-rolls memory_base_rates.json from the
                            gauntlet p3_results; Step 20 must never overwrite it
  5. leakage law applied  → an analogue whose 63-session outcome window has not
                            closed before the query onset is excluded

All fixtures are synthetic and tiny (6 episodes, 2 nodes, 120 sessions) — no
committed-data pins, no repo data/ writes (everything under tmp_path).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

# The exact string every analogue aggregate must carry (R4: descriptive layer).
NOTE = "descriptive — analogue history, not a forecast"

ARTIFACT = "memory_active_analogues.json"


# ---------------------------------------------------------------------------
# Fixture builders — minimal schema find_analogues() actually reads
# ---------------------------------------------------------------------------

def _dates(n: int = 120) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-02", periods=n)


def _episode(
    episode_id: str,
    node: str,
    direction: str,
    onset: pd.Timestamp,
    exhausted: pd.Timestamp | None,
    *,
    accel: float = 2.0,
    outcome: float = 0.05,
) -> dict:
    """One catalog row.  Only the columns find_analogues reads are populated."""
    row = {
        "episode_id": episode_id,
        "node": node,
        "direction": direction,
        "onset_date": onset,
        "exhausted_date": exhausted if exhausted is not None else pd.NaT,
        # scalar feature legs
        "peak_accel_z": accel,
        "cohesion_at_onset": 0.4,
        "breadth_at_onset": 0.6,
        "regime_vix_pctile": 0.5,
        "regime_spy_above_200d": 1.0,
    }
    for h in (5, 21, 63):
        row[f"outcome_rs_{h}d"] = outcome * (h / 21.0)
        row[f"outcome_mature_{h}d"] = True
    return row


def _write_fixture(data_dir: Path, *, exhaust_q2: bool = False, with_panel: bool = True) -> dict:
    """Write episodes_s.parquet (+ panel_s.parquet) into <data_dir>/oracle.

    Layout (d = business sessions from 2024-01-02):

      A1     AAA out d[20]  closed   → eligible analogue for Q1
      A2     BBB out d[25]  closed   → eligible analogue for Q1
      A3     AAA in  d[22]  closed   → eligible analogue for Q2 only (direction)
      ALEAK  AAA out d[100] closed   → LEAKAGE-EXCLUDED for Q1 (window still open)
      Q1     AAA out d[110] ACTIVE
      Q2     BBB in  d[112] ACTIVE   (or closed when exhaust_q2)

    Returns the episode-id map so tests can assert by name.
    """
    d = _dates()
    oracle = data_dir / "oracle"
    oracle.mkdir(parents=True, exist_ok=True)

    ids = {
        "A1": "AAA::out::analogue1::1",
        "A2": "BBB::out::analogue2::1",
        "A3": "AAA::in::analogue3::1",
        "ALEAK": "AAA::out::tooRecent::1",
        "Q1": "AAA::out::query1::1",
        "Q2": "BBB::in::query2::1",
    }
    rows = [
        _episode(ids["A1"], "AAA", "out", d[20], d[40], outcome=0.02),
        _episode(ids["A2"], "BBB", "out", d[25], d[45], outcome=0.06),
        _episode(ids["A3"], "AAA", "in", d[22], d[42], outcome=0.04),
        _episode(ids["ALEAK"], "AAA", "out", d[100], d[105], outcome=0.09),
        _episode(ids["Q1"], "AAA", "out", d[110], None),
        _episode(ids["Q2"], "BBB", "in", d[112], d[115] if exhaust_q2 else None),
    ]
    pd.DataFrame(rows).to_parquet(oracle / "episodes_s.parquet")

    if with_panel:
        # MultiIndex (node, date) with an 'rs' column — the trajectory leg and
        # the session-index leg of the leakage law both read this.
        frames = []
        for i, node in enumerate(("AAA", "BBB")):
            frames.append(pd.DataFrame({
                "node": node,
                "date": d,
                "rs": [1.0 + i * 0.5 + j * 0.01 for j in range(len(d))],
            }))
        panel = pd.concat(frames, ignore_index=True).set_index(["node", "date"])
        panel.to_parquet(oracle / "panel_s.parquet")

    return ids


def _run_step(data_dir: Path, *, dry_run: bool = False) -> bool:
    from scripts.oracle_nightly import _step_memory_analogues
    return _step_memory_analogues(data_dir, dry_run)


def _read_artifact(data_dir: Path) -> dict:
    return json.loads((data_dir / "oracle" / ARTIFACT).read_text())


def _blocks(payload: dict) -> dict:
    return {k: v for k, v in payload.items() if k != "meta"}


# ---------------------------------------------------------------------------
# (a) Absent inputs — degrade, never crash
# ---------------------------------------------------------------------------

class TestAbsentInputs:
    def test_empty_data_dir_no_crash_no_file(self, tmp_path):
        """No episode parquets at all: step reports the failure and writes nothing."""
        ok = _run_step(tmp_path)
        assert ok is False
        assert not (tmp_path / "oracle" / ARTIFACT).exists()

    def test_missing_panel_still_produces_analogues(self, tmp_path):
        """panel_s absent → calendar-day leakage fallback, still a real artifact."""
        ids = _write_fixture(tmp_path, with_panel=False)
        assert _run_step(tmp_path) is True
        payload = _read_artifact(tmp_path)
        assert set(_blocks(payload)) == {ids["Q1"], ids["Q2"]}

    def test_dry_run_writes_nothing(self, tmp_path):
        _write_fixture(tmp_path)
        assert _run_step(tmp_path, dry_run=True) is True
        assert not (tmp_path / "oracle" / ARTIFACT).exists()

    def test_no_active_episodes_writes_empty_artifact(self, tmp_path):
        """Catalog present but nothing live: a fresh EMPTY artifact beats a stale one."""
        d = _dates()
        oracle = tmp_path / "oracle"
        oracle.mkdir(parents=True)
        pd.DataFrame([
            _episode("AAA::out::closed::1", "AAA", "out", d[20], d[40]),
        ]).to_parquet(oracle / "episodes_s.parquet")

        assert _run_step(tmp_path) is True
        payload = _read_artifact(tmp_path)
        assert _blocks(payload) == {}
        assert payload["meta"]["n_active_total"] == 0


# ---------------------------------------------------------------------------
# (b) Synthetic inputs — shape, keys, and the descriptive note
# ---------------------------------------------------------------------------

class TestArtifactShape:
    def test_top_level_keys_and_meta(self, tmp_path):
        ids = _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True

        payload = _read_artifact(tmp_path)
        meta = payload["meta"]
        for key in ("schema", "generated_at", "n_active_total", "n_blocks",
                    "tier_filter", "k", "episode_ids", "description"):
            assert key in meta, f"meta missing {key}"
        assert meta["n_active_total"] == 2
        assert meta["n_blocks"] == 2
        assert sorted(meta["episode_ids"]) == sorted([ids["Q1"], ids["Q2"]])

        # ACTIVE episodes only — a closed episode never gets its own block.
        assert set(_blocks(payload)) == {ids["Q1"], ids["Q2"]}
        assert ids["A1"] not in payload

    def test_every_block_carries_the_descriptive_note(self, tmp_path):
        _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True

        blocks = _blocks(_read_artifact(tmp_path))
        assert blocks, "no analogue blocks written"
        for ep_id, block in blocks.items():
            assert block["aggregate"]["description"] == NOTE, ep_id

    def test_keyed_the_way_the_real_reader_indexes_it(self, tmp_path):
        """The seam, pinned against the REAL reader rather than a restatement.

        engine/oracle/live.py fills active_episodes[].analogues with
        analogues_meta.get(episode_id); a payload it cannot index leaves the
        field null — exactly the production state this step exists to end.
        """
        from engine.oracle.live import _load_active_analogues

        ids = _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True

        analogues_meta = _load_active_analogues(tmp_path)
        assert analogues_meta is not None
        for key in ("Q1", "Q2"):
            block = analogues_meta.get(ids[key])
            assert isinstance(block, dict), f"reader cannot index {ids[key]}"
            assert block["analogues"], f"{ids[key]} has an empty analogue list"

    def test_analogue_membership_and_leakage_exclusion(self, tmp_path):
        ids = _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True
        blocks = _blocks(_read_artifact(tmp_path))

        q1 = blocks[ids["Q1"]]
        got = {a["episode_id"] for a in q1["analogues"]}
        # Same-direction, fully-closed outcome windows only.
        assert got == {ids["A1"], ids["A2"]}
        # ALEAK's 63-session window has not closed before Q1's onset.
        assert ids["ALEAK"] not in got
        assert q1["leakage_excluded"] >= 1
        assert q1["query_direction"] == "out"
        assert q1["tier"] == "s"

        q2 = blocks[ids["Q2"]]
        assert {a["episode_id"] for a in q2["analogues"]} == {ids["A3"]}
        assert q2["aggregate"]["k"] == 1
        assert q2["aggregate"]["n_mature_21d"] == 1

    def test_same_node_flagged_not_dropped(self, tmp_path):
        ids = _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True
        blocks = _blocks(_read_artifact(tmp_path))

        flags = {a["episode_id"]: a["same_node"] for a in blocks[ids["Q1"]]["analogues"]}
        assert flags[ids["A1"]] is True    # AAA vs AAA
        assert flags[ids["A2"]] is False   # BBB vs AAA


# ---------------------------------------------------------------------------
# (c) Re-run — idempotent payload, clean overwrite
# ---------------------------------------------------------------------------

class TestRerun:
    def test_rerun_payload_identical_apart_from_generated_at(self, tmp_path):
        _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True
        first = _read_artifact(tmp_path)
        assert _run_step(tmp_path) is True
        second = _read_artifact(tmp_path)

        assert _blocks(first) == _blocks(second)
        first_meta = dict(first["meta"])
        second_meta = dict(second["meta"])
        assert first_meta.pop("generated_at") is not None
        assert second_meta.pop("generated_at") is not None
        assert first_meta == second_meta

    def test_exhausted_episode_block_disappears(self, tmp_path):
        """Clean overwrite: a block must not outlive the episode it describes."""
        ids = _write_fixture(tmp_path)
        assert _run_step(tmp_path) is True
        assert ids["Q2"] in _read_artifact(tmp_path)

        _write_fixture(tmp_path, exhaust_q2=True)   # Q2 has since exhausted
        assert _run_step(tmp_path) is True

        payload = _read_artifact(tmp_path)
        assert ids["Q2"] not in payload, "stale block survived the overwrite"
        assert set(_blocks(payload)) == {ids["Q1"]}
        assert payload["meta"]["n_blocks"] == 1


# ---------------------------------------------------------------------------
# Step 4a boundary — ANALOGUES ONLY
# ---------------------------------------------------------------------------

class TestBaseRatesUntouched:
    def test_step_never_writes_memory_base_rates(self, tmp_path):
        """Step 4a hand-rolls base rates from the gauntlet p3_results.

        A Step 20 that ran build_oracle_memory's base-rate half would silently
        replace that artifact with a differently-derived one.
        """
        _write_fixture(tmp_path)
        br = tmp_path / "oracle" / "memory_base_rates.json"
        sentinel = {"out_onset": {"source": "gauntlet/p3_results.json s3_error_rates"}}
        br.write_text(json.dumps(sentinel))

        assert _run_step(tmp_path) is True
        assert json.loads(br.read_text()) == sentinel

    def test_analogues_only_flag_leaves_base_rates_absent(self, tmp_path):
        """The CLI half the step delegates to: --analogues-only writes ONE file."""
        from scripts.build_oracle_memory import main as memory_main

        _write_fixture(tmp_path)
        rc = memory_main(["--data-dir", str(tmp_path), "--analogues-only"])
        assert rc == 0
        assert (tmp_path / "oracle" / ARTIFACT).exists()
        assert not (tmp_path / "oracle" / "memory_base_rates.json").exists()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
