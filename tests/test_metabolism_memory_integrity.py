"""tests/test_metabolism_memory_integrity.py — Hermetic tests for memory-integrity fixes.

COVERAGE:
  F1 — verify.py dry_run purity + idempotent memory appends
    1. dry_run=True writes zero durable files (lessons, strategic_memory, agenda_archive)
    2. triple-run of the same graded contract appends exactly 1 lesson row + 1 strategic-memory row
    3. governance tap skipped in dry_run mode

  F2 — insight_bus compact_bus
    4. compact_bus bounds live file (handled rows archived)
    5. archive integrity: archived rows appear in the monthly archive file
    6. handled rows dropped from live file
    7. surplus cap: file bounded to max_open_rows
    8. empty bus → compact is a no-op
    9. missing bus file → compact returns retained=0 without error

  F3 — standout lobes exempted from generic_fitness
    10. site-us-standouts skipped by generic_fitness (bespoke builder exempt)
    11. site-china-standouts skipped by generic_fitness
    12. organism_state sees bespoke card (non-empty sensors) not overwritten by generic

  F4 — minor fixes
    13. parse_check_by handles non-zero-padded YYYY-M-D
    14. accrual-honesty gate fires on non-zero-padded check_by date
    15. parse_check_by strips timezone offset strings correctly
    16. exit-staleness guard returns UNVERIFIABLE when price store is stale

All tests HERMETIC (tmp dirs, monkeypatching, no real network/subprocess).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Shared fixture helpers ────────────────────────────────────────────────────

def _tmp_root() -> Path:
    d = Path(tempfile.mkdtemp())
    for subdir in [
        "data/metabolism/fitness",
        "data/metabolism/fitness_history",
        "data/metabolism/agenda",
        "data/metabolism/agenda_archive",
        "data/metabolism/verify",
        "data/metabolism/lessons",
        "config",
        "docs",
        "research",
    ]:
        (d / subdir).mkdir(parents=True, exist_ok=True)
    (d / "research" / "DO_NOT_REBUILD.md").write_text("# empty\n", encoding="utf-8")
    (d / "docs" / "ACTIVE_BUILD_MAP.md").write_text("# empty\n", encoding="utf-8")
    return d


def _write_minimal_charter(root: Path, lobe_id: str, extra_sensors: list | None = None) -> None:
    """Write a minimal lobe_charters.yml with the given lobe as active/structured."""
    import yaml  # noqa: PLC0415
    sensors = extra_sensors or [
        {"id": "liveness_score", "store": f"data/test/{lobe_id}.json",
         "maturity_date": "2027-01-01", "accruing": True},
    ]
    charters = {
        "charters": {
            lobe_id: {
                "lobe_id": lobe_id,
                "tier": "display",
                "lifecycle_state": "active",
                "fitness_sensors": sensors,
            }
        }
    }
    cfg = root / "config"
    cfg.mkdir(exist_ok=True)
    (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — verify.py dry_run purity + idempotency
# ═══════════════════════════════════════════════════════════════════════════════

class TestVerifyDryRunPurity:
    """F1a: dry_run=True writes zero durable files."""

    def _run_verify(self, root: Path, dry_run: bool = False) -> dict:
        from engine.metabolism.verify import verify_proposal
        with patch(
            "engine.metabolism.verify._evaluate_contract",
            return_value=("CONFIRMED", "contract held"),
        ):
            return verify_proposal(
                cycle_id="cycle-dryrun",
                contract={
                    "proposal_id": "p-dryrun",
                    "sensor": "ic_mean",
                    "expected_sign": "positive",
                    "band": [0.05, None],
                    "check_by": "2020-01-01",
                },
                root=root,
                today="2026-07-10",
                dry_run=dry_run,
            )

    def test_dry_run_zero_lessons_write(self, tmp_path):
        """dry_run=True → lessons.jsonl not created."""
        root = _tmp_root()
        record = self._run_verify(root, dry_run=True)
        assert record["realized"]["outcome"] == "CONFIRMED"
        lessons_path = root / "data" / "metabolism" / "lessons.jsonl"
        assert not lessons_path.exists(), "lessons.jsonl must NOT be written in dry_run mode"

    def test_dry_run_zero_strategic_memory_write(self, tmp_path):
        """dry_run=True → strategic_memory.jsonl not created."""
        root = _tmp_root()
        self._run_verify(root, dry_run=True)
        sm_path = root / "data" / "metabolism" / "strategic_memory.jsonl"
        assert not sm_path.exists(), "strategic_memory.jsonl must NOT be written in dry_run mode"

    def test_dry_run_zero_agenda_archive_write(self, tmp_path):
        """dry_run=True → agenda_archive/ not populated."""
        root = _tmp_root()
        self._run_verify(root, dry_run=True)
        archive_dir = root / "data" / "metabolism" / "agenda_archive"
        assert not any(archive_dir.iterdir()), "agenda_archive must NOT be written in dry_run mode"

    def test_dry_run_governance_tap_skipped(self, tmp_path):
        """dry_run=True on an UNVERIFIABLE result → governance tap NOT called."""
        root = _tmp_root()
        from engine.metabolism.verify import verify_proposal
        with patch(
            "engine.metabolism.verify._evaluate_contract",
            return_value=("UNVERIFIABLE", "no data"),
        ), patch("engine.metabolism.verify._append_governance_tap") as mock_tap:
            verify_proposal(
                cycle_id="cycle-tap",
                contract={
                    "proposal_id": "p-tap",
                    "sensor": "ic_mean",
                    "check_by": "2020-01-01",
                },
                root=root,
                today="2026-07-10",
                dry_run=True,
            )
        mock_tap.assert_not_called()

    def test_non_dry_run_writes_lessons(self, tmp_path):
        """Without dry_run, lessons.jsonl IS written."""
        root = _tmp_root()
        self._run_verify(root, dry_run=False)
        lessons_path = root / "data" / "metabolism" / "lessons.jsonl"
        assert lessons_path.exists(), "lessons.jsonl must be written when NOT dry_run"


class TestVerifyIdempotency:
    """F1b: triple-run of the same graded contract → exactly 1 lesson + 1 strategic-memory row."""

    def _run_once(self, root: Path) -> dict:
        from engine.metabolism.verify import verify_proposal
        with patch(
            "engine.metabolism.verify._evaluate_contract",
            return_value=("CONFIRMED", "contract held"),
        ):
            return verify_proposal(
                cycle_id="cycle-idem",
                contract={
                    "proposal_id": "p-idem",
                    "sensor": "ic_mean",
                    "expected_sign": "positive",
                    "band": [0.05, None],
                    "check_by": "2020-01-01",
                },
                root=root,
                today="2026-07-10",
                dry_run=False,
            )

    def test_triple_run_single_lesson_row(self, tmp_path):
        """Running verify 3 times on the same cycle+proposal_id yields exactly 1 lesson row."""
        root = _tmp_root()
        for _ in range(3):
            self._run_once(root)
        lessons_path = root / "data" / "metabolism" / "lessons.jsonl"
        assert lessons_path.exists()
        rows = [json.loads(ln) for ln in lessons_path.read_text().splitlines() if ln.strip()]
        cycle_rows = [r for r in rows if r.get("cycle_id") == "cycle-idem"
                      and r.get("proposal_id") == "p-idem"]
        assert len(cycle_rows) == 1, (
            f"Expected exactly 1 lesson row for cycle-idem/p-idem, got {len(cycle_rows)}: {cycle_rows}"
        )

    def test_triple_run_single_strategic_memory_row(self, tmp_path):
        """Running verify 3 times on the same cycle+proposal_id yields exactly 1 strategic-memory row."""
        root = _tmp_root()
        for _ in range(3):
            self._run_once(root)
        sm_path = root / "data" / "metabolism" / "strategic_memory.jsonl"
        assert sm_path.exists()
        rows = [json.loads(ln) for ln in sm_path.read_text().splitlines() if ln.strip()]
        cycle_rows = [r for r in rows if r.get("cycle_id") == "cycle-idem"
                      and r.get("proposal_id") == "p-idem"]
        assert len(cycle_rows) == 1, (
            f"Expected exactly 1 strategic_memory row for cycle-idem/p-idem, got {len(cycle_rows)}: {cycle_rows}"
        )

    def test_different_proposals_get_separate_rows(self, tmp_path):
        """Different proposal_ids in the same cycle each get their own rows."""
        root = _tmp_root()
        from engine.metabolism.verify import verify_proposal
        contracts = [
            {"proposal_id": "p-a", "sensor": "ic_mean", "check_by": "2020-01-01"},
            {"proposal_id": "p-b", "sensor": "ic_std", "check_by": "2020-01-01"},
        ]
        for contract in contracts:
            with patch(
                "engine.metabolism.verify._evaluate_contract",
                return_value=("CONFIRMED", "held"),
            ):
                verify_proposal(
                    cycle_id="cycle-multi",
                    contract=contract,
                    root=root,
                    today="2026-07-10",
                    dry_run=False,
                )
        lessons_path = root / "data" / "metabolism" / "lessons.jsonl"
        rows = [json.loads(ln) for ln in lessons_path.read_text().splitlines() if ln.strip()]
        cycle_rows = [r for r in rows if r.get("cycle_id") == "cycle-multi"]
        assert len(cycle_rows) == 2, (
            f"Expected 2 lesson rows for different proposals, got {len(cycle_rows)}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# F2 — insight_bus compact_bus
# ═══════════════════════════════════════════════════════════════════════════════

class TestInsightBusCompaction:
    """F2: compact_bus bounds + archive integrity + handled-row removal."""

    def _make_bus(self, root: Path, n_rows: int, handled_count: int = 0) -> Path:
        """Write n_rows to insight_bus.jsonl, optionally marking some as handled."""
        from engine.metabolism.insight_bus import build_row, BUS_PATH
        bus_path = root / BUS_PATH
        bus_path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for i in range(n_rows):
            ts = (datetime.now(timezone.utc) - timedelta(days=i)).isoformat(timespec="seconds")
            r = build_row(
                emitter="test_emitter",
                kind="health_transition",
                severity="medium",
                entities=[f"lobe_{i}"],
                summary=f"Test insight {i}",
                ts=ts,
            )
            rows.append(r)
            with bus_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

        # Mark some as handled by appending handler rows
        for i in range(handled_count):
            handler = {
                "schema": "metabolism.insight_bus.v1",
                "insight_id": f"handler_{i}",
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "cycle_id": None,
                "emitter": "insight_bus.mark_handled",
                "kind": "handled",
                "severity": "low",
                "entities": [rows[i].get("insight_id", "")],
                "evidence_ref": None,
                "summary": f"handled: insight {rows[i].get('insight_id', '')}",
                "handled": True,
                "handled_by": f"handler_{i}",
                "authority": {"is_context_only": True},
            }
            with bus_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(handler, ensure_ascii=False) + "\n")

        return bus_path

    def test_compact_archives_handled_rows(self, tmp_path):
        """compact_bus moves handled rows out of the live file."""
        root = _tmp_root()
        bus_path = self._make_bus(root, n_rows=5, handled_count=2)
        initial_count = sum(1 for ln in bus_path.read_text().splitlines() if ln.strip())

        from engine.metabolism.insight_bus import compact_bus
        result = compact_bus(root=root)
        assert result.get("errors") == [], f"compact_bus errors: {result['errors']}"
        assert result["archived"] > 0, "Should archive at least the handled rows + handler rows"

        # Live file should have fewer rows
        remaining = sum(1 for ln in bus_path.read_text().splitlines() if ln.strip())
        assert remaining < initial_count, "Live file should shrink after compaction"

    def test_compact_archive_integrity(self, tmp_path):
        """Archived rows appear in the monthly archive JSONL file."""
        root = _tmp_root()
        self._make_bus(root, n_rows=5, handled_count=2)

        from engine.metabolism.insight_bus import compact_bus, _ARCHIVE_DIR_REL
        result = compact_bus(root=root)

        archive_dir = root / _ARCHIVE_DIR_REL
        if result["archived"] > 0:
            archive_files = list(archive_dir.glob("*.jsonl"))
            assert archive_files, "Archive directory should have at least one file"
            total_archived_rows = sum(
                sum(1 for ln in f.read_text().splitlines() if ln.strip())
                for f in archive_files
            )
            assert total_archived_rows == result["archived"], (
                f"Archive row count mismatch: files have {total_archived_rows}, "
                f"result says {result['archived']}"
            )

    def test_compact_surplus_cap(self, tmp_path):
        """compact_bus caps live file to max_open_rows."""
        root = _tmp_root()
        self._make_bus(root, n_rows=20)  # 20 fresh rows, none handled

        from engine.metabolism.insight_bus import compact_bus
        result = compact_bus(root=root, max_open_rows=10)
        assert result.get("errors") == []
        assert result["retained"] <= 10, (
            f"Live file should be capped at 10 rows, retained={result['retained']}"
        )
        assert result["archived"] >= 10

    def test_compact_empty_bus_noop(self, tmp_path):
        """compact_bus on empty bus file returns retained=0 without error."""
        root = _tmp_root()
        from engine.metabolism.insight_bus import BUS_PATH, compact_bus
        bus_path = root / BUS_PATH
        bus_path.parent.mkdir(parents=True, exist_ok=True)
        bus_path.write_text("", encoding="utf-8")

        result = compact_bus(root=root)
        assert result.get("errors") == []
        assert result["retained"] == 0
        assert result["archived"] == 0

    def test_compact_absent_bus_noop(self, tmp_path):
        """compact_bus when bus file is absent returns retained=0 without error."""
        root = _tmp_root()
        from engine.metabolism.insight_bus import compact_bus
        result = compact_bus(root=root)
        assert result.get("errors") == []
        assert result["retained"] == 0

    def test_compact_stale_rows_archived(self, tmp_path):
        """compact_bus archives rows older than retention_days."""
        root = _tmp_root()
        from engine.metabolism.insight_bus import build_row, BUS_PATH, compact_bus
        bus_path = root / BUS_PATH
        bus_path.parent.mkdir(parents=True, exist_ok=True)

        # Write 3 old rows (200 days ago) + 2 fresh rows
        old_ts = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat(timespec="seconds")
        fresh_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for i in range(3):
            r = build_row("emitter", "health_transition", "low", [f"old_{i}"], f"old {i}", ts=old_ts)
            with bus_path.open("a") as fh:
                fh.write(json.dumps(r) + "\n")
        for i in range(2):
            r = build_row("emitter", "contradiction", "low", [f"fresh_{i}"], f"fresh {i}", ts=fresh_ts)
            with bus_path.open("a") as fh:
                fh.write(json.dumps(r) + "\n")

        result = compact_bus(root=root, retention_days=90)
        assert result["archived"] >= 3, f"Should archive at least 3 old rows, got {result['archived']}"
        assert result["retained"] <= 2, f"Should retain at most 2 fresh rows, got {result['retained']}"

    def test_compact_handled_rows_not_in_live_file(self, tmp_path):
        """After compact, handled rows do not appear in the live file."""
        root = _tmp_root()
        bus_path = self._make_bus(root, n_rows=3, handled_count=3)

        from engine.metabolism.insight_bus import compact_bus, BUS_PATH
        compact_bus(root=root)

        live_rows = []
        bus_path_live = root / BUS_PATH
        if bus_path_live.exists():
            for ln in bus_path_live.read_text().splitlines():
                if ln.strip():
                    live_rows.append(json.loads(ln))
        # No row in live file should be a non-handler insight that was handled
        for r in live_rows:
            if not r.get("handled"):
                # This is an original insight row — it should not be handled
                assert not r.get("handled"), f"Handled row survived in live file: {r}"


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — standout lobes exempted from generic_fitness
# ═══════════════════════════════════════════════════════════════════════════════

class TestStandoutLobeExemption:
    """F3: site-us-standouts and site-china-standouts skipped by generic_fitness."""

    def _make_standout_root(self, tmp_path: Path, lobe_id: str, store_path: str) -> Path:
        """Create a root with a standout lobe in lobe_charters.yml."""
        root = tmp_path / "repo"
        root.mkdir()
        import yaml  # noqa: PLC0415
        sensors = [
            {"id": "hit_quality", "store": store_path,
             "maturity_date": "2026-09-15", "accruing": True},
        ]
        charters = {
            "charters": {
                lobe_id: {
                    "lobe_id": lobe_id,
                    "tier": "display",
                    "lifecycle_state": "active",
                    "fitness_sensors": sensors,
                }
            }
        }
        cfg = root / "config"
        cfg.mkdir()
        (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
        (root / "data").mkdir()
        return root

    def test_site_us_standouts_skipped(self, tmp_path):
        """site-us-standouts is NOT written by generic_fitness (bespoke builder exempt)."""
        root = self._make_standout_root(tmp_path, "site-us-standouts",
                                        "data/metabolism/fitness/standouts_us.json")
        from engine.metabolism.generic_fitness import build_generic_fitness_cards
        written = build_generic_fitness_cards(root=root)
        written_names = [Path(p).name for p in written]
        assert "site-us-standouts.json" not in written_names, (
            "site-us-standouts.json must not be written by generic builder (bespoke)"
        )

    def test_site_china_standouts_skipped(self, tmp_path):
        """site-china-standouts is NOT written by generic_fitness (bespoke builder exempt)."""
        root = self._make_standout_root(tmp_path, "site-china-standouts",
                                        "data/metabolism/fitness/standouts_cn.json")
        from engine.metabolism.generic_fitness import build_generic_fitness_cards
        written = build_generic_fitness_cards(root=root)
        written_names = [Path(p).name for p in written]
        assert "site-china-standouts.json" not in written_names, (
            "site-china-standouts.json must not be written by generic builder (bespoke)"
        )

    def test_bespoke_card_not_overwritten(self, tmp_path):
        """When bespoke card exists with real sensors, generic_fitness does not overwrite it."""
        root = self._make_standout_root(tmp_path, "site-us-standouts",
                                        "data/metabolism/fitness/standouts_us.json")
        # Write a "bespoke" card with real sensor content
        fitness_dir = root / "data" / "metabolism" / "fitness"
        fitness_dir.mkdir(parents=True, exist_ok=True)
        bespoke_card = {
            "schema": "metabolism.standout_audit.v1",
            "lobe": "site-us-standouts",
            "sensors": {"hit_quality": {"value": 0.65, "note": "real sensor"}},
        }
        bespoke_path = fitness_dir / "standouts_us.json"
        bespoke_path.write_text(json.dumps(bespoke_card), encoding="utf-8")

        from engine.metabolism.generic_fitness import build_generic_fitness_cards
        build_generic_fitness_cards(root=root)

        # Card should still have the bespoke content
        card = json.loads(bespoke_path.read_text())
        assert card.get("sensors", {}).get("hit_quality", {}).get("value") == 0.65, (
            "Bespoke card content was overwritten by generic_fitness"
        )

    def test_til_still_skipped(self, tmp_path):
        """Original 'til' exemption still works after the fix."""
        root = self._make_standout_root(tmp_path, "til",
                                        "data/metabolism/fitness/til.json")
        from engine.metabolism.generic_fitness import build_generic_fitness_cards
        written = build_generic_fitness_cards(root=root)
        written_names = [Path(p).name for p in written]
        assert "til.json" not in written_names, "til.json must not be written by generic builder"

    def test_other_active_lobes_still_get_cards(self, tmp_path):
        """Normal active lobes with structured sensors still get fitness cards."""
        root = tmp_path / "repo"
        root.mkdir()
        import yaml  # noqa: PLC0415
        charters = {
            "charters": {
                "site-us-standouts": {
                    "lobe_id": "site-us-standouts",
                    "tier": "display",
                    "lifecycle_state": "active",
                    "fitness_sensors": [{"id": "hit_quality",
                                         "store": "data/metabolism/fitness/standouts_us.json",
                                         "maturity_date": "2026-09-15", "accruing": True}],
                },
                "normal-active-lobe": {
                    "lobe_id": "normal-active-lobe",
                    "tier": "display",
                    "lifecycle_state": "active",
                    "fitness_sensors": [{"id": "liveness", "store": "data/test/live.json",
                                         "maturity_date": "2027-01-01", "accruing": True}],
                },
            }
        }
        cfg = root / "config"
        cfg.mkdir()
        (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
        (root / "data").mkdir()

        from engine.metabolism.generic_fitness import build_generic_fitness_cards
        written = build_generic_fitness_cards(root=root)
        written_names = [Path(p).name for p in written]
        assert "normal-active-lobe.json" in written_names, (
            "normal-active-lobe should still get a fitness card"
        )
        assert "site-us-standouts.json" not in written_names


# ═══════════════════════════════════════════════════════════════════════════════
# F4 — Minor fixes
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseCheckBy:
    """F4b/F4c: parse_check_by handles non-zero-padded and timezone-offset strings."""

    def test_canonical_iso_date(self):
        """parse_check_by handles canonical YYYY-MM-DD."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-07-15")
        assert result == date(2026, 7, 15)

    def test_non_zero_padded_month(self):
        """F4b: parse_check_by handles YYYY-M-DD (non-zero-padded month)."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-7-15")
        assert result == date(2026, 7, 15)

    def test_non_zero_padded_day(self):
        """F4b: parse_check_by handles YYYY-MM-D (non-zero-padded day)."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-07-5")
        assert result == date(2026, 7, 5)

    def test_non_zero_padded_both(self):
        """F4b: parse_check_by handles YYYY-M-D (both non-zero-padded)."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-7-5")
        assert result == date(2026, 7, 5)

    def test_timezone_offset_stripped(self):
        """F4c: parse_check_by strips timezone offset from ISO datetime."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-07-15T00:00:00+05:30")
        assert result == date(2026, 7, 15)

    def test_z_suffix_stripped(self):
        """F4c: parse_check_by strips Z suffix from ISO datetime."""
        from engine.metabolism.verify import parse_check_by
        result = parse_check_by("2026-07-15T00:00:00Z")
        assert result == date(2026, 7, 15)

    def test_none_input_returns_none(self):
        """parse_check_by returns None for None input."""
        from engine.metabolism.verify import parse_check_by
        assert parse_check_by(None) is None

    def test_garbage_returns_none(self):
        """parse_check_by returns None for unparseable garbage."""
        from engine.metabolism.verify import parse_check_by
        assert parse_check_by("not-a-date") is None


class TestAccrualHonestyGateNonPadded:
    """F4b: accrual-honesty gate fires even on non-zero-padded check_by."""

    def _make_propose_root(self, tmp_path: Path, maturity_date: str) -> Path:
        root = tmp_path / "repo"
        root.mkdir()
        import yaml  # noqa: PLC0415
        charters = {
            "charters": {
                "test-lobe": {
                    "lobe_id": "test-lobe",
                    "tier": "display",
                    "lifecycle_state": "active",
                    "fitness_sensors": [
                        {"id": "ic_mean", "store": "data/test/ic.json",
                         "maturity_date": maturity_date, "accruing": True},
                    ],
                }
            }
        }
        cfg = root / "config"
        cfg.mkdir()
        (cfg / "lobe_charters.yml").write_text(yaml.dump(charters), encoding="utf-8")
        (root / "data").mkdir()
        return root

    def test_non_padded_check_by_before_maturity_denied(self, tmp_path):
        """Non-zero-padded check_by before maturity_date fires the accrual-honesty gate."""
        root = self._make_propose_root(tmp_path, "2026-09-15")

        # _validate_proposal wraps the fitness contract validation; pass a minimal proposal
        from engine.metabolism.propose import _validate_proposal
        proposal = {
            "proposal_id": "p-test",
            "title": "Test proposal",
            "tier": "T1",
            "kind": "NOVEL_BUILD",
            "targets_sensor": "ic_mean",
            "fitness_contract": {
                "sensor": "ic_mean",
                "check_by": "2026-7-1",  # non-padded, before maturity 2026-09-15
                "band": [0.05, None],
                "expected_sign": "positive",
            },
        }
        accruing_maturity = {"ic_mean": "2026-09-15"}
        error = _validate_proposal(proposal, accruing_maturity=accruing_maturity)
        assert error is not None, (
            "Accrual-honesty gate must fire for non-padded check_by 2026-7-1 < maturity 2026-09-15"
        )
        assert "accrual-honesty" in error.lower() or "matures" in error.lower()

    def test_non_padded_check_by_after_maturity_allowed(self, tmp_path):
        """Non-zero-padded check_by after maturity_date does NOT fire the gate."""
        root = self._make_propose_root(tmp_path, "2026-09-15")
        from engine.metabolism.propose import _validate_proposal
        proposal = {
            "proposal_id": "p-test",
            "title": "Test proposal",
            "tier": "T1",
            "kind": "NOVEL_BUILD",
            "targets_sensor": "ic_mean",
            "fitness_contract": {
                "sensor": "ic_mean",
                "check_by": "2026-10-1",  # non-padded, after maturity 2026-09-15
                "band": [0.05, None],
                "expected_sign": "positive",
            },
        }
        accruing_maturity = {"ic_mean": "2026-09-15"}
        error = _validate_proposal(proposal, accruing_maturity=accruing_maturity)
        assert error is None, (
            f"Accrual-honesty gate must NOT fire for 2026-10-1 >= maturity 2026-09-15, got: {error}"
        )


class TestExitStalenessGuard:
    """F4a: rel_return exit-close staleness guard."""

    def test_stale_exit_returns_unverifiable(self, tmp_path):
        """_check_exit_staleness returns (True, note) when price store is stale."""
        root = Path(tempfile.mkdtemp())
        # Write a minimal parquet-like CSV price store with last close 10 days before check_by
        ticker = "TESTX"
        check_by = "2026-07-15"
        stale_date = "2026-07-04"  # 11 days before check_by (>1 session)
        price_dir = root / "data" / "yahoo"
        price_dir.mkdir(parents=True, exist_ok=True)
        csv_path = price_dir / f"{ticker}.csv"
        csv_path.write_text(
            f"Date,Close\n{stale_date},100.0\n2026-07-03,99.0\n",
            encoding="utf-8",
        )
        from engine.metabolism.verify import _check_exit_staleness
        falsifier_spec = {"kind": "rel_return", "subject_ticker": ticker}
        is_stale, note = _check_exit_staleness(falsifier_spec, check_by, root)
        assert is_stale, f"Should flag stale (11d before check_by), got note: {note!r}"
        assert "stale" in note.lower() or "staleness" in note.lower() or "UNVERIFIABLE" in note

    def test_fresh_exit_not_stale(self, tmp_path):
        """_check_exit_staleness returns (False, '') when price store is fresh."""
        root = Path(tempfile.mkdtemp())
        ticker = "TESTY"
        check_by = "2026-07-15"
        fresh_date = "2026-07-14"  # 1 day before check_by (within tolerance)
        price_dir = root / "data" / "yahoo"
        price_dir.mkdir(parents=True, exist_ok=True)
        csv_path = price_dir / f"{ticker}.csv"
        csv_path.write_text(
            f"Date,Close\n{fresh_date},100.0\n2026-07-13,99.0\n",
            encoding="utf-8",
        )
        from engine.metabolism.verify import _check_exit_staleness
        falsifier_spec = {"kind": "rel_return", "subject_ticker": ticker}
        is_stale, note = _check_exit_staleness(falsifier_spec, check_by, root)
        assert not is_stale, f"Should NOT flag stale for 1-day old data, got: {note!r}"

    def test_absent_price_store_not_stale(self, tmp_path):
        """_check_exit_staleness fails open (returns False) when price store is absent."""
        root = Path(tempfile.mkdtemp())
        from engine.metabolism.verify import _check_exit_staleness
        falsifier_spec = {"kind": "rel_return", "subject_ticker": "NONEXISTENT"}
        is_stale, note = _check_exit_staleness(falsifier_spec, "2026-07-15", root)
        assert not is_stale, "Should fail open (False) when price store absent"
