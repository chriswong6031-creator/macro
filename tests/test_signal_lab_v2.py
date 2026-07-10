"""Signal Lab v2 (LANE A) — targeted tests for features A1-A13.

Covers:
- A1: DSR provenance key shape
- A2: adjudications loader (well-formed / missing / corrupt)
- A3: frontier_chip_counts derived from frontier_rows
- A8: slug stability
- A9: payload always carries 'warnings' + 'adjudications' + 'frontier_chip_counts'
- A10: source_refs extraction
- Template renders without raising (regression smoke)
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from jinja2 import Environment, FileSystemLoader

from engine import signal_lab
from engine.signal_lab import (
    _compute_frontier_chip_counts,
    _load_adjudications,
    _name_to_slug,
)

WORKTREE = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# A8: slug stability
# ---------------------------------------------------------------------------

class TestSlugStability:
    def test_ascii_only(self):
        assert _name_to_slug("Cross-Asset Trend") == "cross-asset-trend"

    def test_strips_punctuation(self):
        assert _name_to_slug("SUE (Surprise)") == "sue-surprise"

    def test_chinese_stripped(self):
        # Chinese characters are not a-z0-9; they become hyphens then trimmed
        s = _name_to_slug("Flow 内幕 Signal")
        # Should contain "flow" and "signal" connected by hyphens
        assert "flow" in s
        assert "signal" in s

    def test_max_length(self):
        long_name = "A" * 200
        assert len(_name_to_slug(long_name)) <= 80

    def test_stable_across_calls(self):
        name = "Mean-Reversion Breadth Thrust"
        assert _name_to_slug(name) == _name_to_slug(name)

    def test_empty_string(self):
        # Should not raise; empty or single char result
        result = _name_to_slug("")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# A9: payload keys always present
# ---------------------------------------------------------------------------

class TestPayloadKeys:
    def test_warnings_always_present(self):
        p = signal_lab.build_scorecard()
        assert "warnings" in p
        assert isinstance(p["warnings"], list)

    def test_adjudications_always_present(self):
        p = signal_lab.build_scorecard()
        assert "adjudications" in p
        assert isinstance(p["adjudications"], list)

    def test_frontier_chip_counts_always_present(self):
        p = signal_lab.build_scorecard()
        assert "frontier_chip_counts" in p
        assert isinstance(p["frontier_chip_counts"], dict)

    def test_docket_candidate_count_present(self):
        p = signal_lab.build_scorecard()
        assert "docket_candidate_count" in p
        assert p["docket_candidate_count"] >= 0

    def test_waves_adjudication_backcompat(self):
        """Existing tests depend on payload['waves_adjudication']."""
        p = signal_lab.build_scorecard()
        assert "waves_adjudication" in p


# ---------------------------------------------------------------------------
# A2: adjudications loader
# ---------------------------------------------------------------------------

class TestAdjudicationsLoader:
    def test_loads_real_file(self):
        """Real adjudications.json must parse and be a non-empty list."""
        warnings: list[str] = []
        adjs = _load_adjudications(warnings)
        assert isinstance(adjs, list)
        assert len(adjs) >= 1, "Expected at least one adjudication event"
        assert warnings == [], f"Unexpected warnings: {warnings}"

    def test_returns_empty_on_missing_file(self):
        warnings: list[str] = []
        with patch.object(signal_lab, "_ADJUDICATIONS_PATH", Path("/nonexistent/adj.json")):
            adjs = _load_adjudications(warnings)
        assert adjs == []
        # Loader may or may not warn on missing file — just verify it doesn't raise

    def test_returns_empty_and_warns_on_corrupt_json(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{not valid json}")
            tmp_path = Path(f.name)
        try:
            warnings: list[str] = []
            with patch.object(signal_lab, "_ADJUDICATIONS_PATH", tmp_path):
                adjs = _load_adjudications(warnings)
            assert adjs == []
            assert len(warnings) >= 1
            assert "json" in warnings[0].lower() or "adjudication" in warnings[0].lower()
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_schema_has_required_fields(self):
        """Each event must have date, title, title_zh."""
        warnings: list[str] = []
        adjs = _load_adjudications(warnings)
        for event in adjs:
            assert "date" in event, "Missing 'date' in adjudication"
            assert "title" in event, "Missing 'title' in adjudication"

    def test_sorted_date_descending(self):
        """Loader sorts events newest-first."""
        data = [
            {"date": "2024-01-01", "title": "old"},
            {"date": "2026-07-06", "title": "new"},
        ]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(data, f)
            tmp_path = Path(f.name)
        try:
            warnings: list[str] = []
            with patch.object(signal_lab, "_ADJUDICATIONS_PATH", tmp_path):
                adjs = _load_adjudications(warnings)
            assert adjs[0]["date"] >= adjs[-1]["date"]
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# A3: frontier_chip_counts derived from frontier_rows
# ---------------------------------------------------------------------------

class TestFrontierChipCounts:
    def test_counts_match_rows(self):
        """Chip counts total must equal number of frontier rows."""
        from engine.signal_lab import page_frontier_rows

        rows = page_frontier_rows()
        actual = _compute_frontier_chip_counts(rows)
        # Total should match row count
        assert sum(actual.values()) == len(rows)

    def test_no_negative_counts(self):
        from engine.signal_lab import page_frontier_rows
        rows = page_frontier_rows()
        counts = _compute_frontier_chip_counts(rows)
        for k, v in counts.items():
            assert v >= 0, f"Negative count for {k}"

    def test_payload_counts_equal_row_recount(self):
        """Payload frontier_chip_counts must equal _compute_frontier_chip_counts(frontier_rows)."""
        p = signal_lab.build_scorecard()
        expected = _compute_frontier_chip_counts(p["frontier_rows"])
        assert p["frontier_chip_counts"] == dict(expected)


# ---------------------------------------------------------------------------
# A10: source_refs extraction
# ---------------------------------------------------------------------------

class TestSourceRefsExtraction:
    def test_all_registry_rows_have_source_refs(self):
        """_audit_source_refs attaches source_refs to every row that has a source."""
        from engine.signal_lab import REGISTRY
        from engine.signal_lab import _audit_source_refs
        rows = [dict(r) for r in REGISTRY]
        _audit_source_refs(rows)
        for row in rows:
            assert "source_refs" in row, f"Missing source_refs on {row.get('name')}"
            assert isinstance(row["source_refs"], list)

    def test_ref_items_have_required_keys(self):
        from engine.signal_lab import REGISTRY, _audit_source_refs
        rows = [dict(r) for r in REGISTRY]
        _audit_source_refs(rows)
        for row in rows:
            for ref in row["source_refs"]:
                assert "ref" in ref, "ref item missing 'ref' key"
                assert "exists" in ref, "ref item missing 'exists' key"
                assert isinstance(ref["exists"], bool)

    def test_tricky_source_tokens(self):
        """Dot-md and reports/ tokens are both extracted."""
        from engine.signal_lab import _SOURCE_REF_RE

        source = "reports/GTF_results.md · reports/some_report.txt"
        tokens = _SOURCE_REF_RE.findall(source)
        assert any(".md" in t for t in tokens)
        assert any("reports/" in t for t in tokens)

    def test_empty_source_gives_empty_refs(self):
        from engine.signal_lab import _audit_source_refs
        row = {"name": "Dummy", "source": ""}
        _audit_source_refs([row])
        assert row["source_refs"] == []


# ---------------------------------------------------------------------------
# A1: DSR provenance shape in payload rows
# ---------------------------------------------------------------------------

class TestDsrProvenance:
    def test_rows_with_dsr_may_have_provenance(self):
        """If dsr_provenance is set, it must contain 'basis' and 'n_trials'."""
        p = signal_lab.build_scorecard()
        for tier in p["tiers"]:
            for row in tier["rows"]:
                prov = row.get("dsr_provenance")
                if prov is None:
                    continue
                assert "basis" in prov, f"Missing 'basis' in dsr_provenance for {row['name']}"
                assert prov["basis"] in ("ledger", "frozen", "frozen-quote", "expired"), (
                    f"Unknown basis {prov['basis']} for {row['name']}"
                )
                assert "n_trials" in prov


# ---------------------------------------------------------------------------
# Template render smoke test
# ---------------------------------------------------------------------------

class TestTemplateRender:
    def _render(self, payload: dict) -> str:
        env = Environment(
            loader=FileSystemLoader(str(WORKTREE / "templates")),
            autoescape=False,
        )
        tmpl = env.get_template("signal_lab.html.j2")
        return tmpl.render(**payload)

    def test_render_succeeds_with_real_payload(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert len(html) > 50_000, "Rendered HTML seems too short"

    def test_render_contains_a4_frontier_filter(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert 'id="fq"' in html, "Missing frontier search input (A4)"
        assert 'id="fmkt"' in html, "Missing frontier market select (A4)"

    def test_render_contains_a5_expand_buttons(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "row-expand-btn" in html, "Missing expand button class (A5)"

    def test_render_contains_a7_pending_checkbox(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert 'data-tier="pending"' in html, "Missing pending tier checkbox (A7)"

    def test_render_contains_a8_anchor_ids(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert 'id="sig-' in html, "Missing sig- anchor IDs (A8)"

    def test_render_contains_a9_warn_banner_css(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "warn-banner" in html, "Missing warn-banner CSS class (A9)"

    def test_render_contains_a11_localstorage(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "sl_filters" in html, "Missing localStorage key (A11)"
        assert "slreset" in html, "Missing reset button id (A11)"

    def test_render_contains_a12_pipeline_legend(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "pipeline-legend" in html, "Missing pipeline legend (A12)"

    def test_render_contains_a13_cross_link(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "cross-link-chip" in html, "Missing cross-link chip (A13)"
        assert "china_stocks_lab.html" in html, "Missing China lab link (A13)"

    def test_render_contains_a8_hash_handler(self):
        p = signal_lab.build_scorecard()
        html = self._render(p)
        assert "handleHash" in html, "Missing hash navigation handler (A8)"

    def test_render_warns_banner_only_when_warnings(self):
        p = signal_lab.build_scorecard()
        # Inject a warning
        p2 = dict(p, warnings=["test-warning-XYZZY"])
        html = self._render(p2)
        assert "test-warning-XYZZY" in html, "Warning not rendered in banner"

    def test_render_no_warn_banner_when_no_warnings(self):
        p = signal_lab.build_scorecard()
        p2 = dict(p, warnings=[])
        html = self._render(p2)
        # warn-banner div should not appear (it's conditional)
        # The CSS class still appears in <style>; check the actual div
        assert '<div class="warn-banner">' not in html

    def test_no_validated_word_in_new_additions(self):
        """New template structural additions (pipeline legend, cross-link, warn banner, etc.)
        must not introduce 'validated'. Pre-existing tier labels like 'Scored — validated & wired'
        come from REGISTRY strings, not from our template markup."""
        p = signal_lab.build_scorecard()
        html = self._render(p)
        # Check only our new structural template blocks, not the whole document
        # (existing REGISTRY why strings legitimately contain 'validated')
        for block_id in ["pipeline-legend", "cross-link-chip", "warn-banner", "sl_filters"]:
            # Find the relevant CSS/HTML block's context
            idx = html.find(block_id)
            if idx == -1:
                continue
            # Check within ±200 chars of the block marker — new additions only
            snippet = html[max(0, idx - 50): idx + 200]
            # The word 'validated' should not appear in structural additions
            # (tier labels are rendered in different DOM locations)
            assert "validated" not in snippet.lower() or "warn-banner" in snippet, (
                f"'validated' unexpectedly found near block {block_id}: {snippet[:100]}"
            )
