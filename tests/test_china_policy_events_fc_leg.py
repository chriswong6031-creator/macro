"""Tests for scripts/china_policy_events_fc_leg.py — F-C MPC phrase-diff leg.

Coverage:
  1. Phrase-diff event extraction from 3 synthetic communiqué fixtures
     (appeared / dropped / no-change).
  2. Publish-date anchor + fallback to meeting_date.
  3. PIT anchor — first close strictly AFTER anchor date.
  4. Unsigned invariance — results contain no verdict field beyond 'exploratory'
     for F-C; no 'GO'/'KILL'/'ACCRUE' verdict permitted.
  5. Conditioning cell n<5 prints n only.
  6. Results JSON schema: FC_communiques has exploratory:true, unsigned:true,
     no 'verdict' key with an FDR value.

NO live network in tests. Synthetic fixtures only. Tracked parquets are
never written; tests restore any state they modify.
"""
from __future__ import annotations

import copy
import json
import pathlib
import tempfile

import numpy as np
import pandas as pd
import pytest

# ── Imports under test ────────────────────────────────────────────────────────

from scripts.china_policy_events_fc_leg import (
    _body_text,
    _conditioning_cell_fc,
    compute_fc_conditioning,
    compute_slice_tables,
    extract_phrase_diff_events,
    run_fc_leg,
    update_results_json,
    append_fc_report,
)
from engine.communique_diff import load_phrase_book, phrases_in_text


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load_book() -> list[dict]:
    """Load the real phrase book from the repo."""
    book = load_phrase_book(REPO_ROOT)
    assert book, "phrase_book.yml must be loadable for F-C tests"
    return book


def _make_df(rows: list[dict]) -> pd.DataFrame:
    """Build a minimal communiques DataFrame from a list of row dicts."""
    cols = [
        "doc_id", "family", "meeting_year", "meeting_quarter",
        "meeting_date", "publish_date", "title", "body", "body_sha256",
        "url", "source", "_fetched_at",
    ]
    import hashlib
    full_rows = []
    for i, r in enumerate(rows):
        row = {c: r.get(c, None) for c in cols}
        row["doc_id"] = r.get("doc_id") or hashlib.sha256(f"test_{i}".encode()).hexdigest()
        row["body_sha256"] = hashlib.sha256(str(row.get("body", "")).encode()).hexdigest()
        row["source"] = r.get("source", "test")
        row["_fetched_at"] = "2026-07-06T00:00:00Z"
        full_rows.append(row)
    return pd.DataFrame(full_rows, columns=cols)


def _synthetic_price_series(n: int = 200, start: str = "2009-01-05") -> pd.Series:
    """Deterministic price series spanning 2009–2026."""
    rng = np.random.default_rng(99)
    idx = pd.bdate_range(start, periods=n)
    prices = 3000.0 * np.cumprod(1 + rng.normal(0, 0.008, n))
    return pd.Series(prices, index=idx)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: Phrase-diff event extraction — appeared fixture
# ─────────────────────────────────────────────────────────────────────────────

class TestPhraseDiffExtraction:
    """Scenario 1: first readout has 稳健的货币政策; second ADDS 降准降息."""

    def test_appeared_event_detected(self):
        book = _load_book()
        # First readout: 稳健的货币政策 only
        prior_body = "会议认为，要坚持稳健的货币政策，保持流动性合理充裕。"
        # Second readout: ADDS 降准降息
        current_body = "会议认为，要坚持稳健的货币政策，适时降准降息，保持流动性合理充裕。"

        df = _make_df([
            {"meeting_year": 2019, "meeting_quarter": 1,
             "meeting_date": "2019-03-26", "publish_date": "2019-03-28",
             "title": "MPC Q1 2019", "body": prior_body},
            {"meeting_year": 2019, "meeting_quarter": 2,
             "meeting_date": "2019-06-25", "publish_date": "2019-06-27",
             "title": "MPC Q2 2019", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 1, f"Expected 1 event, got {len(events)}"
        ev = events[0]
        assert "降准降息" in ev["appeared"], \
            f"Expected 降准降息 in appeared, got {ev['appeared']}"
        assert len(ev["dropped"]) == 0, \
            f"Expected no drops, got {ev['dropped']}"

    def test_dropped_event_detected(self):
        """Scenario 2: 房住不炒 present in prior, absent in current."""
        book = _load_book()
        prior_body = "会议认为，要坚持房住不炒，稳健的货币政策，稳增长。"
        current_body = "会议认为，稳健的货币政策，稳增长，扩大内需。"

        df = _make_df([
            {"meeting_year": 2023, "meeting_quarter": 4,
             "meeting_date": "2023-12-26", "publish_date": "2023-12-28",
             "title": "MPC Q4 2023", "body": prior_body},
            {"meeting_year": 2024, "meeting_quarter": 1,
             "meeting_date": "2024-03-26", "publish_date": "2024-03-28",
             "title": "MPC Q1 2024", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 1
        ev = events[0]
        assert "房住不炒" in ev["dropped"], \
            f"Expected 房住不炒 in dropped, got {ev['dropped']}"
        # 扩大内需 appeared
        assert "扩大内需" in ev["appeared"], \
            f"Expected 扩大内需 in appeared, got {ev['appeared']}"

    def test_no_change_not_an_event(self):
        """Scenario 3: identical phrase sets → NOT an event."""
        book = _load_book()
        body = "会议认为，稳健的货币政策，保持流动性合理充裕，稳增长。"

        df = _make_df([
            {"meeting_year": 2021, "meeting_quarter": 1,
             "meeting_date": "2021-03-30", "publish_date": "2021-04-01",
             "title": "MPC Q1 2021", "body": body},
            {"meeting_year": 2021, "meeting_quarter": 2,
             "meeting_date": "2021-06-29", "publish_date": "2021-07-01",
             "title": "MPC Q2 2021", "body": body},  # identical
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 0, \
            f"Expected 0 events (no change), got {len(events)}: {events}"

    def test_cold_start_skips_first_row(self):
        """First row in sequence must never produce an event (cold-start rule)."""
        book = _load_book()
        body = "会议认为，适度宽松，降准降息，稳增长。"
        df = _make_df([
            {"meeting_year": 2009, "meeting_quarter": 1,
             "meeting_date": "2009-03-24", "publish_date": "2009-03-26",
             "title": "MPC Q1 2009", "body": body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 0, \
            "First row (cold start) must not produce an event"

    def test_variant_form_matches_canonical(self):
        """A variant form (适度宽松的货币政策) should register as canonical 适度宽松."""
        book = _load_book()
        prior_body = "稳健的货币政策继续保持稳定。"
        # Use the VARIANT form (适度宽松的货币政策), should register as canonical 适度宽松
        current_body = "实施适度宽松的货币政策，加大逆周期调节力度。"

        df = _make_df([
            {"meeting_year": 2024, "meeting_quarter": 3,
             "meeting_date": "2024-09-24", "publish_date": "2024-09-26",
             "title": "MPC Q3 2024", "body": prior_body},
            {"meeting_year": 2024, "meeting_quarter": 4,
             "meeting_date": "2024-12-24", "publish_date": "2024-12-26",
             "title": "MPC Q4 2024", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 1
        ev = events[0]
        # Canonical form must be in appeared, not the variant
        assert "适度宽松" in ev["appeared"], \
            f"Variant form must map to canonical 适度宽松; appeared={ev['appeared']}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: Publish-date anchor + fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestAnchor:
    def test_publish_date_used_when_available(self):
        """publish_date should be the primary anchor."""
        book = _load_book()
        prior_body = "稳健的货币政策。"
        current_body = "适度宽松，稳健的货币政策。"

        df = _make_df([
            {"meeting_year": 2024, "meeting_quarter": 3,
             "meeting_date": "2024-09-24", "publish_date": "2024-09-26",
             "title": "MPC Q3 2024", "body": prior_body},
            {"meeting_year": 2024, "meeting_quarter": 4,
             "meeting_date": "2024-12-24", "publish_date": "2024-12-26",
             "title": "MPC Q4 2024", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 1
        assert events[0]["anchor_date"] == "2024-12-26"
        assert events[0]["anchor_source"] == "publish_date"

    def test_fallback_to_meeting_date(self):
        """When publish_date is null, fall back to meeting_date."""
        book = _load_book()
        prior_body = "稳健的货币政策。"
        current_body = "适度宽松，扩大内需。"

        df = _make_df([
            {"meeting_year": 2024, "meeting_quarter": 3,
             "meeting_date": "2024-09-24", "publish_date": None,
             "title": "MPC Q3 2024", "body": prior_body},
            {"meeting_year": 2024, "meeting_quarter": 4,
             "meeting_date": "2024-12-24", "publish_date": None,
             "title": "MPC Q4 2024", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 1
        assert events[0]["anchor_date"] == "2024-12-24"
        assert events[0]["anchor_source"] == "meeting_date_fallback"

    def test_no_anchor_skips_event(self):
        """Event with neither publish_date nor meeting_date must be skipped."""
        book = _load_book()
        prior_body = "稳健的货币政策。"
        current_body = "适度宽松，扩大内需。"

        df = _make_df([
            {"meeting_year": 2024, "meeting_quarter": 3,
             "meeting_date": None, "publish_date": None,
             "title": "MPC Q3 2024", "body": prior_body},
            {"meeting_year": 2024, "meeting_quarter": 4,
             "meeting_date": None, "publish_date": None,
             "title": "MPC Q4 2024", "body": current_body},
        ])

        events = extract_phrase_diff_events(df, book)
        assert len(events) == 0, "Event with no anchor date must be skipped"


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: PIT anchor
# ─────────────────────────────────────────────────────────────────────────────

class TestPITAnchor:
    def test_entry_strictly_after_anchor(self):
        """car_for_event's entry is strictly after anchor — not on it."""
        from scripts.china_policy_events_phase0 import car_for_event, next_trading_day

        prices = _synthetic_price_series(200)
        cal = prices.index

        # Event on a trading day
        event_date = cal[10]
        entry = next_trading_day(event_date, cal)

        assert entry is not None
        assert entry > event_date, \
            f"PIT violation: entry={entry} not > event={event_date}"

        # Check CAR starts from entry, not event close
        car = car_for_event(event_date, prices, 20, cal)
        assert car is not None

        # Manually verify entry position
        entry_pos = cal.searchsorted(event_date, side="right")
        assert cal[entry_pos] == entry


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: Unsigned invariance
# ─────────────────────────────────────────────────────────────────────────────

class TestUnsignedInvariance:
    """F-C results must not contain any gated verdict (GO/KILL/ACCRUE/NO-GO)."""

    FORBIDDEN_VERDICTS = {"GO", "KILL", "NO-GO", "ACCRUE", "BLOCKED-POWER"}

    def test_run_fc_leg_verdict_is_exploratory(self, tmp_path):
        """run_fc_leg must return verdict='EXPLORATORY', no forbidden verdicts."""
        from scripts._create_synthetic_communiques import create_synthetic_communiques
        comm_path = tmp_path / "communiques.parquet"
        create_synthetic_communiques(out_path=comm_path)

        fc_result = run_fc_leg(communiques_path=comm_path)
        assert fc_result["verdict"] == "EXPLORATORY", \
            f"F-C verdict must be EXPLORATORY, got {fc_result['verdict']}"
        assert fc_result.get("exploratory") is True
        assert fc_result.get("unsigned") is True

        # No forbidden verdict keys
        v = fc_result.get("verdict", "")
        assert v not in self.FORBIDDEN_VERDICTS, \
            f"F-C must not carry a gated verdict: {v}"

    def test_fc_result_has_no_verdict_field_with_fdr_value(self, tmp_path):
        """The F-C result dict must not carry any verdict key from the FDR gate set."""
        from scripts._create_synthetic_communiques import create_synthetic_communiques
        comm_path = tmp_path / "communiques.parquet"
        create_synthetic_communiques(out_path=comm_path)

        fc_result = run_fc_leg(communiques_path=comm_path)

        # Deep-check: no value in the entire result dict is a forbidden verdict string
        def _check_no_forbidden(obj, path=""):
            if isinstance(obj, str) and obj in self.FORBIDDEN_VERDICTS:
                pytest.fail(
                    f"F-C result contains forbidden verdict '{obj}' at path '{path}'"
                )
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check_no_forbidden(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _check_no_forbidden(item, f"{path}[{i}]")

        _check_no_forbidden(fc_result)

    def test_results_json_fc_stanza_unsigned(self, tmp_path):
        """After update_results_json, the FC_communiques stanza has exploratory+unsigned."""
        # Create a minimal results JSON
        minimal_results = {
            "event_counts": {"FC_mpc_communiques": "BLOCKED-DATA"},
            "fc_status": "BLOCKED-DATA",
            "exploratory_trials": {
                "FC_communiques": {
                    "verdict": "BLOCKED-DATA",
                    "reason": "absent",
                }
            },
            "gated_trials": {},
            "verdicts": {},
            "bh_fdr": {},
        }
        results_path = tmp_path / "results.json"
        results_path.write_text(json.dumps(minimal_results))

        fc_result = {
            "verdict": "EXPLORATORY",
            "exploratory": True,
            "unsigned": True,
            "no_verdict_note": "UNSIGNED",
            "n_events_after_dedup": 10,
            "n_mpc_readouts": 20,
            "n_fallback_anchor": 0,
        }

        update_results_json(fc_result, results_path=results_path)

        updated = json.loads(results_path.read_text())
        fc = updated["exploratory_trials"]["FC_communiques"]
        assert fc.get("exploratory") is True, "FC stanza must have exploratory=True"
        assert fc.get("unsigned") is True, "FC stanza must have unsigned=True"
        assert fc.get("verdict") not in self.FORBIDDEN_VERDICTS, \
            f"FC verdict must not be a gated verdict: {fc.get('verdict')}"


# ─────────────────────────────────────────────────────────────────────────────
# Test 5: Conditioning cell n<5 prints n only
# ─────────────────────────────────────────────────────────────────────────────

class TestConditioningCells:
    def test_cell_n_lt_5_prints_n_only(self):
        """Cell with n<5 must return only {'n': n}."""
        cell = _conditioning_cell_fc(pd.Series([0.01, 0.02, 0.03]))  # n=3
        assert cell == {"n": 3}, f"Expected {{'n': 3}}, got {cell}"

    def test_cell_n_ge_5_includes_mean_median(self):
        """Cell with n≥5 must include mean_car_h20 and median_car_h20."""
        vals = pd.Series([0.01, 0.02, 0.03, 0.04, 0.05])
        cell = _conditioning_cell_fc(vals)
        assert "n" in cell
        assert "mean_car_h20" in cell
        assert "median_car_h20" in cell
        assert cell["n"] == 5
        assert abs(cell["mean_car_h20"] - 0.03) < 1e-9

    def test_conditioning_no_t_stats(self, tmp_path):
        """compute_fc_conditioning must not include any t-stat keys."""
        from scripts._create_synthetic_communiques import create_synthetic_communiques
        comm_path = tmp_path / "communiques.parquet"
        create_synthetic_communiques(out_path=comm_path)

        fc_result = run_fc_leg(communiques_path=comm_path)
        cond = fc_result.get("conditioning_tables", {})

        forbidden_keys = {"hac_t", "t_stat", "t", "p_value", "hac_p"}
        for regime_col, tbl in cond.items():
            for label_val, cell in tbl.items():
                for k in cell.keys():
                    assert k not in forbidden_keys, \
                        f"Conditioning cell {regime_col}/{label_val} has forbidden key '{k}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 6: Results JSON schema
# ─────────────────────────────────────────────────────────────────────────────

class TestResultsJSONSchema:
    def test_fc_in_exploratory_trials(self):
        """After a full run, results JSON has FC_communiques in exploratory_trials."""
        results_path = REPO_ROOT / "data" / "experiments" / "china_policy_events_results.json"
        if not results_path.exists():
            pytest.skip("results JSON not present — run the phase-0 script first")
        with open(results_path) as f:
            r = json.load(f)
        assert "FC_communiques" in r.get("exploratory_trials", {}), \
            "FC_communiques must be in exploratory_trials after F-C run"

    def test_fc_stanza_has_required_keys(self):
        """FC_communiques stanza must have the required schema keys."""
        results_path = REPO_ROOT / "data" / "experiments" / "china_policy_events_results.json"
        if not results_path.exists():
            pytest.skip("results JSON not present")
        with open(results_path) as f:
            r = json.load(f)
        fc = r.get("exploratory_trials", {}).get("FC_communiques", {})
        if fc.get("verdict") == "BLOCKED-DATA":
            pytest.skip("F-C still BLOCKED-DATA — run fc_leg script first")
        required = {"verdict", "exploratory", "unsigned", "n_events_after_dedup",
                    "horizons", "primary_stats", "slice_tables"}
        missing = required - set(fc.keys())
        assert not missing, f"FC stanza missing keys: {missing}"

    def test_fc_verdict_is_exploratory_in_json(self):
        """After a real run, FC verdict must be EXPLORATORY."""
        results_path = REPO_ROOT / "data" / "experiments" / "china_policy_events_results.json"
        if not results_path.exists():
            pytest.skip("results JSON not present")
        with open(results_path) as f:
            r = json.load(f)
        fc = r.get("exploratory_trials", {}).get("FC_communiques", {})
        if fc.get("verdict") == "BLOCKED-DATA":
            pytest.skip("F-C still BLOCKED-DATA")
        assert fc.get("verdict") == "EXPLORATORY", \
            f"Expected EXPLORATORY, got {fc.get('verdict')}"
        assert fc.get("exploratory") is True
        assert fc.get("unsigned") is True


# ─────────────────────────────────────────────────────────────────────────────
# Test 7: Slice tables (APPEARED-only / DROPPED-only / BOTH)
# ─────────────────────────────────────────────────────────────────────────────

class TestSliceTables:
    def test_slice_tables_cover_all_keys(self, tmp_path):
        """slice_tables must have appeared_only, dropped_only, and both keys."""
        from scripts._create_synthetic_communiques import create_synthetic_communiques
        comm_path = tmp_path / "communiques.parquet"
        create_synthetic_communiques(out_path=comm_path)

        fc_result = run_fc_leg(communiques_path=comm_path)
        slices = fc_result.get("slice_tables", {})
        assert "appeared_only" in slices, "slice_tables must have appeared_only"
        assert "dropped_only" in slices, "slice_tables must have dropped_only"
        assert "both" in slices, "slice_tables must have both"

    def test_slice_cells_have_no_t_stats(self, tmp_path):
        """Slice table cells must not contain t-stats (n/mean/median only)."""
        from scripts._create_synthetic_communiques import create_synthetic_communiques
        comm_path = tmp_path / "communiques.parquet"
        create_synthetic_communiques(out_path=comm_path)

        fc_result = run_fc_leg(communiques_path=comm_path)
        slices = fc_result.get("slice_tables", {})
        forbidden = {"hac_t", "t_stat", "t", "p_value", "hac_p", "hac_t_exploratory"}
        for key, cell in slices.items():
            for k in cell.keys():
                assert k not in forbidden, \
                    f"Slice cell '{key}' has forbidden key '{k}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 8: Report file has F-C section
# ─────────────────────────────────────────────────────────────────────────────

class TestReport:
    def test_report_contains_fc_section(self):
        """After a run, the report must contain the F-C section marker."""
        report_path = REPO_ROOT / "reports" / "china-policy-events-phase0.md"
        if not report_path.exists():
            pytest.skip("report file not present")
        text = report_path.read_text()
        if "BLOCKED-DATA" in text and "F-C MPC Communiqué Phrase-Diff Leg" not in text:
            pytest.skip("F-C section not yet written")
        assert "F-C MPC Communiqué Phrase-Diff Leg" in text, \
            "Report must contain F-C section header after the run"
        assert "EXPLORATORY / UNSIGNED" in text, \
            "F-C section must state EXPLORATORY / UNSIGNED"
        assert "no verdict" in text.lower() or "no_verdict" in text.lower(), \
            "F-C section must explicitly note no verdict"

    def test_report_has_plain_english_box(self):
        """F-C section must have an 'In plain English' box."""
        report_path = REPO_ROOT / "reports" / "china-policy-events-phase0.md"
        if not report_path.exists():
            pytest.skip("report file not present")
        text = report_path.read_text()
        if "F-C MPC Communiqué Phrase-Diff Leg" not in text:
            pytest.skip("F-C section not yet written")
        # The section between the F-C header and the end should have an In plain English box
        fc_start = text.index("F-C MPC Communiqué Phrase-Diff Leg")
        fc_text = text[fc_start:]
        assert "In plain English" in fc_text, \
            "F-C section must contain an 'In plain English' box"
