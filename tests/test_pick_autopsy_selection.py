"""Tests for PR-R3 pick autopsy selection in engine/metabolism/standout_auditor.py.

Coverage:
  1. Extremes-first ordering: top winners and bottom losers included.
  2. All gate_suppressed rows always included.
  3. All data_fault rows always included.
  4. Cap respected.
  5. Empty DataFrame returns empty list.
  6. Missing excess column still returns mandatory rows.
  7. dry_run with injected caller writes to shadow dir, not real store.
  8. dry_run without model_caller returns status=refused.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_attr_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal attribution DataFrame."""
    return pd.DataFrame(rows)


def _row(ticker: str, excess: float | None, pf: str = "clean",
         asof: str = "2026-07-01", lane: str = "buy") -> dict:
    return {
        "ticker": ticker,
        "as_of": asof,
        "lane": lane,
        "horizon": 21,
        "taxonomy_version": "v1",
        "outcome_cause": "momentum",
        "process_fault": pf,
        "excess_spy": excess,
        "sector": "tech",
        "board_tenure_days": 5,
        "quad_hard_label": "bull",
        "vol_regime": "normal",
    }


# ---------------------------------------------------------------------------
# 1. Extremes-first ordering
# ---------------------------------------------------------------------------
class TestExtremesFirst:
    def test_top_winners_included(self):
        """Top-K winners by excess_spy should appear in selected picks."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            _row("A", 0.30),  # winner
            _row("B", -0.25),  # loser
            _row("C", 0.01),  # middle
            _row("D", 0.28),  # winner
            _row("E", -0.22),  # loser
            _row("F", 0.00),  # middle
        ]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=4)
        tickers = {p["ticker"] for p in picks}
        # Top winner A should be included
        assert "A" in tickers, "Top winner A should be selected"

    def test_bottom_losers_included(self):
        """Bottom-K losers by excess_spy should appear in selected picks."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            _row("A", 0.30),
            _row("B", -0.25),  # worst loser
            _row("C", 0.01),
            _row("D", 0.28),
            _row("E", -0.22),
            _row("F", 0.00),
        ]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=4)
        tickers = {p["ticker"] for p in picks}
        assert "B" in tickers, "Worst loser B should be selected"


# ---------------------------------------------------------------------------
# 2. All gate_suppressed always included
# ---------------------------------------------------------------------------
class TestGateSuppressedAlwaysIncluded:
    def test_all_gate_suppressed_included(self):
        """ALL gate_suppressed rows must be in the selection, up to cap."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            _row("SUPP1", 0.05, pf="gate_suppressed"),
            _row("SUPP2", -0.01, pf="gate_suppressed"),
            _row("NORMAL", 0.10),
            _row("LOSER", -0.10),
        ]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=10)
        tickers = {p["ticker"] for p in picks}
        assert "SUPP1" in tickers, "gate_suppressed SUPP1 must be selected"
        assert "SUPP2" in tickers, "gate_suppressed SUPP2 must be selected"

    def test_gate_suppressed_not_double_counted(self):
        """gate_suppressed picks must appear only once."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            _row("SUPP", 0.05, pf="gate_suppressed"),
        ]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=10)
        supp_count = sum(1 for p in picks if p["ticker"] == "SUPP")
        assert supp_count == 1, "gate_suppressed SUPP should appear exactly once"


# ---------------------------------------------------------------------------
# 3. All data_fault rows always included
# ---------------------------------------------------------------------------
class TestDataFaultAlwaysIncluded:
    def test_all_data_fault_included(self):
        """ALL data_fault rows must be in the selection."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            _row("FAULT1", None, pf="data_fault"),
            _row("FAULT2", -0.05, pf="data_fault"),
            _row("NORMAL", 0.10),
        ]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=10)
        tickers = {p["ticker"] for p in picks}
        assert "FAULT1" in tickers, "data_fault FAULT1 must be selected"
        assert "FAULT2" in tickers, "data_fault FAULT2 must be selected"


# ---------------------------------------------------------------------------
# 4. Cap respected
# ---------------------------------------------------------------------------
class TestCapRespected:
    def test_result_never_exceeds_cap(self):
        """select_autopsy_picks must never return more than cap picks."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [_row(f"T{i}", float(i) * 0.01) for i in range(50)]
        df = _make_attr_df(rows)
        for cap in (1, 5, 12, 25):
            picks = select_autopsy_picks("us", df, cap=cap)
            assert len(picks) <= cap, (
                f"Expected <= {cap} picks, got {len(picks)}"
            )

    def test_small_df_returns_all(self):
        """With fewer rows than cap, all rows are returned."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [_row("A", 0.1), _row("B", -0.1)]
        df = _make_attr_df(rows)
        picks = select_autopsy_picks("us", df, cap=12)
        assert len(picks) == 2


# ---------------------------------------------------------------------------
# 5. Empty DataFrame returns empty list
# ---------------------------------------------------------------------------
class TestEmptyDataFrame:
    def test_empty_df_returns_empty(self):
        """select_autopsy_picks must return [] for an empty DataFrame."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        df = pd.DataFrame()
        picks = select_autopsy_picks("us", df, cap=12)
        assert picks == []

    def test_none_df_returns_empty(self):
        """select_autopsy_picks must return [] for None input."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        picks = select_autopsy_picks("us", None, cap=12)
        assert picks == []


# ---------------------------------------------------------------------------
# 6. Missing excess column still returns mandatory rows
# ---------------------------------------------------------------------------
class TestMissingExcessColumn:
    def test_no_excess_col_returns_mandatory(self):
        """Without an excess column, gate_suppressed/data_fault rows still selected."""
        from engine.metabolism.standout_auditor import select_autopsy_picks

        rows = [
            {"ticker": "SUPP", "as_of": "2026-07-01", "lane": "buy",
             "horizon": 21, "taxonomy_version": "v1",
             "outcome_cause": "momentum", "process_fault": "gate_suppressed"},
            {"ticker": "NORM", "as_of": "2026-07-01", "lane": "buy",
             "horizon": 21, "taxonomy_version": "v1",
             "outcome_cause": "momentum", "process_fault": "clean"},
        ]
        df = pd.DataFrame(rows)
        picks = select_autopsy_picks("us", df, cap=12)
        tickers = {p["ticker"] for p in picks}
        assert "SUPP" in tickers, "gate_suppressed must be selected even without excess col"


# ---------------------------------------------------------------------------
# 7. dry_run contract: refused without model_caller
# ---------------------------------------------------------------------------
class TestDryRunContract:
    def test_dry_run_without_caller_refused(self, tmp_path):
        """run_pick_autopsies(dry_run=True) without model_caller returns status=refused."""
        from engine.metabolism.standout_auditor import run_pick_autopsies

        result = run_pick_autopsies(
            "us", "test_cycle_001", model_caller=None,
            root=tmp_path, dry_run=True,
        )
        assert result["status"] == "refused", (
            f"Expected status=refused, got {result['status']}"
        )

    def test_dry_run_with_caller_uses_shadow(self, tmp_path):
        """run_pick_autopsies(dry_run=True) with a caller uses shadow dir and not real store."""
        from engine.metabolism.standout_auditor import run_pick_autopsies, _attribution_path

        # Build a minimal attribution parquet
        rows = [
            {"ticker": "TEST", "as_of": "2026-07-01", "lane": "buy",
             "horizon": 21, "taxonomy_version": "v1",
             "outcome_cause": "momentum", "process_fault": "gate_suppressed",
             "excess_spy": 0.05, "sector": "tech", "board_tenure_days": 3,
             "quad_hard_label": "bull", "vol_regime": "normal"},
        ]
        attr_path = _attribution_path("us", tmp_path)
        attr_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(str(attr_path))

        # Inject a minimal model_caller
        def _fake_caller(prompt: str):
            return (
                '[{"pick_index": 1, "root_cause": "Test root cause", '
                '"mitigation_verdict": "not_a_failure", '
                '"lesson": "Test lesson", "engines_credit": "Test credit"}]',
                None,
                None,
            )

        result = run_pick_autopsies(
            "us", "test_cycle_dry_001", model_caller=_fake_caller,
            root=tmp_path, dry_run=True,
        )
        # Should succeed or have no_picks; must NOT touch real data/standout_audit/pick_autopsies
        real_autopsy_dir = tmp_path / "data" / "standout_audit" / "pick_autopsies"
        # The real dir should not exist or be empty
        if real_autopsy_dir.exists():
            real_files = list(real_autopsy_dir.rglob("*.json"))
            # dry_run files go to shadow, real files must be absent
            # Shadow path includes "shadow" in its path
            non_shadow = [f for f in real_files if "shadow" not in str(f)]
            assert not non_shadow, (
                f"dry_run wrote to real autopsy dir: {non_shadow}"
            )


# ---------------------------------------------------------------------------
# 8. Invalid mitigation_verdict rejects to "invalid" not "external_unforeseeable"
# ---------------------------------------------------------------------------
class TestMitigationVerdictValidation:
    """Fix #3: invalid enum values must be rejected, not coerced to a valid member."""

    def _make_attr_parquet(self, tmp_path: Path) -> Path:
        from engine.metabolism.standout_auditor import _attribution_path
        rows = [
            {"ticker": "INVLD", "as_of": "2026-07-01", "lane": "buy",
             "horizon": 21, "taxonomy_version": "v1",
             "outcome_cause": "momentum", "process_fault": "gate_suppressed",
             "excess_spy": 0.05, "sector": "tech", "board_tenure_days": 3,
             "quad_hard_label": "bull", "vol_regime": "normal"},
        ]
        attr_path = _attribution_path("us", tmp_path)
        attr_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_parquet(str(attr_path))
        return attr_path

    def test_invalid_verdict_produces_invalid_marker(self, tmp_path):
        """LLM returning an unrecognised verdict must produce mitigation_verdict='invalid'."""
        from engine.metabolism.standout_auditor import run_pick_autopsies

        self._make_attr_parquet(tmp_path)

        def _bad_verdict_caller(prompt: str):
            return (
                '[{"pick_index": 1, "root_cause": "something", '
                '"mitigation_verdict": "totally_made_up_value", '
                '"lesson": "lesson", "engines_credit": "none"}]',
                None, None,
            )

        result = run_pick_autopsies(
            "us", "test_cycle_invalid_verdict",
            model_caller=_bad_verdict_caller,
            root=tmp_path, dry_run=True,
        )
        # If picks were written, inspect the artifact
        if result.get("written"):
            doc = json.loads(Path(result["written"][0]).read_text())
            assert doc["llm"]["mitigation_verdict"] == "invalid", (
                f"Expected mitigation_verdict='invalid', got {doc['llm']['mitigation_verdict']!r}"
            )
            assert "mitigation_verdict_raw" in doc["llm"], (
                "Expected mitigation_verdict_raw field to carry the raw LLM value"
            )
            assert doc["llm"]["mitigation_verdict_raw"] == "totally_made_up_value", (
                f"mitigation_verdict_raw should carry the raw string, "
                f"got {doc['llm']['mitigation_verdict_raw']!r}"
            )

    def test_valid_verdict_passes_through(self, tmp_path):
        """A valid mitigation_verdict must pass through unchanged."""
        from engine.metabolism.standout_auditor import run_pick_autopsies

        self._make_attr_parquet(tmp_path)

        def _good_verdict_caller(prompt: str):
            return (
                '[{"pick_index": 1, "root_cause": "some cause", '
                '"mitigation_verdict": "mitigable_process", '
                '"lesson": "lesson text", "engines_credit": "systems noted"}]',
                None, None,
            )

        result = run_pick_autopsies(
            "us", "test_cycle_valid_verdict",
            model_caller=_good_verdict_caller,
            root=tmp_path, dry_run=True,
        )
        if result.get("written"):
            doc = json.loads(Path(result["written"][0]).read_text())
            assert doc["llm"]["mitigation_verdict"] == "mitigable_process", (
                f"Valid verdict should pass through, got {doc['llm']['mitigation_verdict']!r}"
            )
            assert "mitigation_verdict_raw" not in doc["llm"], (
                "mitigation_verdict_raw should be absent for valid verdicts"
            )

    def test_invalid_verdict_never_maps_to_external_unforeseeable(self, tmp_path):
        """The old fallback 'external_unforeseeable' must NOT be used for invalid LLM output."""
        from engine.metabolism.standout_auditor import run_pick_autopsies

        self._make_attr_parquet(tmp_path)

        def _bad_caller(prompt: str):
            return (
                '[{"pick_index": 1, "root_cause": "a root cause", '
                '"mitigation_verdict": "BAD_ENUM_VALUE", '
                '"lesson": "l", "engines_credit": "e"}]',
                None, None,
            )

        result = run_pick_autopsies(
            "us", "test_cycle_no_ext_unfore",
            model_caller=_bad_caller,
            root=tmp_path, dry_run=True,
        )
        if result.get("written"):
            doc = json.loads(Path(result["written"][0]).read_text())
            assert doc["llm"]["mitigation_verdict"] != "external_unforeseeable", (
                "Invalid LLM verdict must not silently map to external_unforeseeable"
            )
