"""tests/test_w2044_warn_intensity_phase0.py — W2-044 WARN Intensity Phase-0 unit tests.

Tests the pure-logic components of scripts/w2044_warn_intensity_phase0.py.
No network calls; no real data required.

Covered:
  * TRIAL_GRID structure — 4 cells, all pre-registered as NEGATIVE direction
  * DATA_SOURCE_ASSESSMENT — all 7 sources present, no adequate source
  * WARN_PIT_FENCE_DAYS constant (conservative 7-day fence)
  * _write_report — generates report without error, contains required sections
  * main() run flow — runs to completion with DATA-BLOCKED verdict
  * Report file content — all required sections and gate documentation present
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.w2044_warn_intensity_phase0 as w2044  # noqa: E402


# ---------------------------------------------------------------------------
# Section 1 — TRIAL_GRID structure
# ---------------------------------------------------------------------------

class TestTrialGrid:
    """The trial grid must have exactly 4 cells, all pre-registered NEGATIVE."""

    def test_grid_has_four_cells(self):
        assert len(w2044.TRIAL_GRID) == 4

    def test_all_cells_negative_direction(self):
        for cell in w2044.TRIAL_GRID:
            assert cell["direction"] == "negative", (
                f"Cell '{cell['variant']}' has direction '{cell['direction']}'; "
                "all cells must be pre-registered NEGATIVE"
            )

    def test_two_notice_event_cells(self):
        notice = [c for c in w2044.TRIAL_GRID if c["signal"] == "warn_notice_event"]
        assert len(notice) == 2, "Expected exactly 2 notice_event cells"

    def test_two_intensity_z_cells(self):
        intensity = [c for c in w2044.TRIAL_GRID if c["signal"] == "warn_intensity_z_90d"]
        assert len(intensity) == 2, "Expected exactly 2 intensity_z cells"

    def test_horizons_are_21d_and_63d(self):
        horizons = {c["fwd_days"] for c in w2044.TRIAL_GRID}
        assert horizons == {21, 63}, f"Expected horizons {{21, 63}}, got {horizons}"

    def test_each_signal_has_21d_and_63d(self):
        """Each signal type must have one 21d and one 63d cell (the pre-registered grid)."""
        for sig in ("warn_notice_event", "warn_intensity_z_90d"):
            cells = [c for c in w2044.TRIAL_GRID if c["signal"] == sig]
            fwds = {c["fwd_days"] for c in cells}
            assert fwds == {21, 63}, (
                f"Signal '{sig}' does not have both 21d and 63d cells; got {fwds}"
            )

    def test_each_variant_unique(self):
        variants = [c["variant"] for c in w2044.TRIAL_GRID]
        assert len(variants) == len(set(variants)), "Duplicate variant names in TRIAL_GRID"

    def test_all_cells_have_required_keys(self):
        required = {"variant", "signal", "fwd_days", "direction", "note"}
        for cell in w2044.TRIAL_GRID:
            missing = required - set(cell.keys())
            assert not missing, f"Cell '{cell.get('variant')}' missing keys: {missing}"

    def test_gate_direction_constant_is_negative(self):
        assert w2044.GATE_DIRECTION == "negative"


# ---------------------------------------------------------------------------
# Section 2 — Data source assessment
# ---------------------------------------------------------------------------

class TestDataSourceAssessment:
    """DATA_SOURCE_ASSESSMENT must enumerate all assessed sources with correct verdicts."""

    def test_has_seven_sources(self):
        assert len(w2044.DATA_SOURCE_ASSESSMENT) == 7

    def test_no_source_is_adequate(self):
        """No source should be both machine_accessible_free=True AND not REJECTED/INADEQUATE."""
        for src in w2044.DATA_SOURCE_ASSESSMENT:
            if src["machine_accessible_free"]:
                verdict = src["verdict"]
                assert "REJECTED" in verdict or "INADEQUATE" in verdict, (
                    f"Source '{src['source']}' is free but not REJECTED or INADEQUATE: {verdict}"
                )

    def test_layoffdata_is_blocked(self):
        src = next(s for s in w2044.DATA_SOURCE_ASSESSMENT if "layoffdata" in s["source"].lower())
        assert "BLOCKED" in src["verdict"]

    def test_warn_firehose_is_blocked(self):
        src = next(s for s in w2044.DATA_SOURCE_ASSESSMENT if "Firehose" in s["source"])
        assert "BLOCKED" in src["verdict"]
        assert src["states"] == 50  # full coverage but paywalled

    def test_openicpsr_is_blocked(self):
        src = next(s for s in w2044.DATA_SOURCE_ASSESSMENT if "ICPSR" in s["source"])
        assert "BLOCKED" in src["verdict"]

    def test_biglocalnews_scraper_is_rejected(self):
        src = next(s for s in w2044.DATA_SOURCE_ASSESSMENT if "biglocalnews" in s["source"])
        assert "REJECTED" in src["verdict"]
        # It is free but rejected because it IS a scraper
        assert src["machine_accessible_free"] is True

    def test_datagov_is_inadequate(self):
        src = next(s for s in w2044.DATA_SOURCE_ASSESSMENT if "data.gov" in s["source"])
        assert "INADEQUATE" in src["verdict"]
        assert src["states"] == 1  # single city

    def test_all_sources_have_required_fields(self):
        required = {
            "source", "description", "states", "years", "fields",
            "lag", "machine_accessible_free", "reason_blocked", "verdict"
        }
        for src in w2044.DATA_SOURCE_ASSESSMENT:
            missing = required - set(src.keys())
            assert not missing, f"Source '{src.get('source')}' missing keys: {missing}"

    def test_verdicts_all_blocking(self):
        """Every verdict must indicate blockage (no source is ADEQUATE)."""
        blocking_keywords = {"BLOCKED", "REJECTED", "INADEQUATE"}
        for src in w2044.DATA_SOURCE_ASSESSMENT:
            verdict = src["verdict"]
            assert any(kw in verdict for kw in blocking_keywords), (
                f"Source '{src['source']}' verdict is neither BLOCKED/REJECTED/INADEQUATE: {verdict}"
            )


# ---------------------------------------------------------------------------
# Section 3 — Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_pit_fence_days_is_7(self):
        """Pre-registered PIT fence: notice date + 7 calendar days if posting date absent."""
        assert w2044.WARN_PIT_FENCE_DAYS == 7

    def test_intensity_window_days_is_90(self):
        assert w2044.INTENSITY_WINDOW_DAYS == 90

    def test_fwd_21(self):
        assert w2044.FWD_21 == 21

    def test_fwd_63(self):
        assert w2044.FWD_63 == 63

    def test_gate_abs_t(self):
        assert w2044.GATE_ABS_T == 2.0

    def test_gate_bh_q(self):
        assert w2044.GATE_BH_Q == 0.10

    def test_beta_win(self):
        assert w2044.BETA_WIN == 252

    def test_family_name(self):
        assert w2044.FAMILY == "w2044_warn_intensity"

    def test_price_start_is_2021(self):
        from datetime import date
        assert w2044.PRICE_START == date(2021, 7, 6)


# ---------------------------------------------------------------------------
# Section 4 — Report generation
# ---------------------------------------------------------------------------

class TestReportGeneration:
    """_write_report must produce a valid report with all required sections."""

    def test_write_report_creates_file(self, tmp_path, monkeypatch):
        """_write_report must write a file to REPORT_PATH."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        assert (tmp_path / "test_report.md").exists()

    def test_report_has_required_sections(self, tmp_path, monkeypatch):
        """Report must include all required section headers."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")

        required_patterns = [
            "W2-044",
            "DATA-BLOCKED",
            "In plain English",
            "Pre-registered design",
            "Gates",
            "PIT assumptions",
            "Consolidated WARN feed",
            "Unlock path",
            "Nightly wiring",
            "NEGATIVE",
            "w2044_warn_intensity",
        ]
        for pat in required_patterns:
            assert pat in text, f"Report missing required pattern: '{pat}'"

    def test_report_contains_all_four_trial_variants(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        for cell in w2044.TRIAL_GRID:
            assert cell["variant"] in text, f"Report missing variant: {cell['variant']}"

    def test_report_contains_all_source_names(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        for src in w2044.DATA_SOURCE_ASSESSMENT:
            # Check at least the core source identifier appears
            core_name = src["source"].split(" ")[0]
            assert core_name in text, f"Report missing source: {src['source']}"

    def test_report_mentions_park(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "PARK" in text, "Report must say PARK for data-blocked verdict"

    def test_report_not_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert len(text) > 2000, f"Report too short: {len(text)} chars"

    def test_report_has_no_word_validated(self, tmp_path, monkeypatch):
        """House rule: the word 'validated' must not appear in user-facing reports."""
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044._write_report(status="DATA-BLOCKED")
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "validated" not in text.lower(), (
            "Report must not contain the word 'validated' (CI-enforced)"
        )


# ---------------------------------------------------------------------------
# Section 5 — main() run integration
# ---------------------------------------------------------------------------

class TestMainRun:
    """main() must run to completion and produce the report with DATA-BLOCKED verdict."""

    def test_main_runs_without_error(self, tmp_path, monkeypatch, capsys):
        import engine.trial_ledger as tl
        monkeypatch.setattr(tl, "DEFAULT_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044.main()
        captured = capsys.readouterr()
        assert "DATA-BLOCKED" in captured.out
        assert "PARK" in captured.out

    def test_main_produces_report_file(self, tmp_path, monkeypatch):
        import engine.trial_ledger as tl
        monkeypatch.setattr(tl, "DEFAULT_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044.main()
        assert (tmp_path / "test_report.md").exists()
        text = (tmp_path / "test_report.md").read_text(encoding="utf-8")
        assert "DATA-BLOCKED" in text

    def test_main_zero_adequate_sources(self, capsys, tmp_path, monkeypatch):
        """main() must conclude with 0 adequate sources and trigger DATA-BLOCKED path."""
        import engine.trial_ledger as tl
        monkeypatch.setattr(tl, "DEFAULT_PATH", tmp_path / "ledger.jsonl")
        monkeypatch.setattr(w2044, "REPORT_PATH", tmp_path / "test_report.md")
        w2044.main()
        out = capsys.readouterr().out
        assert "0 adequate" in out or "DATA-BLOCKED" in out
