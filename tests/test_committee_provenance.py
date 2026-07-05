"""Tests for W8b PR1: provenance sidecar (engine/provenance_sidecar.py) and
committee.html render smoke.

All tests are hermetic: synthetic fixtures only, no real market data loaded.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.provenance_sidecar import (
    ProvenanceContext,
    build_provenance,
    load_context,
    _staleness_days,
    _qual_state,
    _kernel_cell,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx_with_kernel() -> ProvenanceContext:
    """Minimal context with one kernel cell (altdata / horizon 5)."""
    ctx = ProvenanceContext()
    ctx.kernel[("altdata", 5)] = {
        "shrunken_ic": 0.002903,
        "wilson_ci_low": 0.463027,
        "n_eff": 94,
        "armed": False,
        "reliability": 0.9216,
    }
    ctx.kernel[("us_board", 5)] = {
        "shrunken_ic": 0.009527,
        "wilson_ci_low": 0.560977,
        "n_eff": 758,
        "armed": True,
        "reliability": 0.990,
    }
    ctx.kernel[("radar", 5)] = {
        "shrunken_ic": 0.003660,
        "wilson_ci_low": 0.521,
        "n_eff": 987,
        "armed": False,
        "reliability": 0.992,
    }
    return ctx


def _ctx_with_altdata(ticker: str = "NVDA") -> ProvenanceContext:
    ctx = _ctx_with_kernel()
    ctx.altdata_by_ticker[ticker] = {
        "convergence_score": 8,
        "channels": ["13f_add", "darkpool_accum"],
        "weighted_score": 2.75,
        "as_of": "2026-06-19",
    }
    return ctx


def _ctx_with_spine(ticker: str = "NVDA") -> ProvenanceContext:
    ctx = _ctx_with_altdata(ticker)
    ctx.spine_latest[ticker] = {
        "altdata": {
            "signal_id": "qledger:e1f59f0a110a022f:63",
            "engine": "altdata",
            "family": "altdata",
            "ledger": "qledger",
            "as_of": "2026-06-19",
            "horizon": 63,
            "direction": 1,
            "score": 2.0,
            "outcome_excess": -0.0566,
            "outcome_graded": True,
            "graded_at": "2026-07-02",
        },
        "us_board": {
            "signal_id": "us_board:2026-06-17:NVDA:buy:5",
            "engine": "us_board",
            "family": "us_board:buy",
            "ledger": "board",
            "as_of": "2026-06-17",
            "horizon": 5,
            "direction": 1,
            "score": 0.667,
            "outcome_excess": -0.0624,
            "outcome_graded": True,
            "graded_at": "2026-06-22",
        },
        "radar": {
            "signal_id": "qledger:c8291bcf2f25eb87:5",
            "engine": "radar",
            "family": "radar",
            "ledger": "qledger",
            "as_of": "2026-06-22",
            "horizon": 5,
            "direction": 1,
            "score": 27.0,
            "outcome_excess": -0.0566,
            "outcome_graded": True,
            "graded_at": "2026-07-02",
        },
    }
    return ctx


# ---------------------------------------------------------------------------
# 1. Staleness helper
# ---------------------------------------------------------------------------

class TestStaleness:
    def test_none_on_missing(self):
        assert _staleness_days(None) is None

    def test_none_on_bad_format(self):
        assert _staleness_days("not-a-date") is None

    def test_non_negative(self):
        days = _staleness_days("2020-01-01")
        assert days is not None and days > 0

    def test_recent_date_low_stale(self):
        import datetime
        today = datetime.date.today()
        yesterday = str(today - datetime.timedelta(days=1))
        days = _staleness_days(yesterday)
        assert days == 1


# ---------------------------------------------------------------------------
# 2. Qual state
# ---------------------------------------------------------------------------

class TestQualState:
    def test_altdata_is_display(self):
        qs = _qual_state("altdata")
        assert qs["ladder_state"] == "DISPLAY"

    def test_altdata_grandfathered(self):
        assert _qual_state("altdata")["grandfathered"] is True

    def test_radar_not_grandfathered(self):
        assert _qual_state("radar.edge_score")["grandfathered"] is False

    def test_shadow_family(self):
        assert _qual_state("us_importance_v0_pit")["ladder_state"] == "SHADOW"

    def test_unknown_family_returns_unknown(self):
        qs = _qual_state("some_nonexistent_family")
        assert qs["ladder_state"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# 3. Kernel cell helper
# ---------------------------------------------------------------------------

class TestKernelCell:
    def test_existing_cell_returns_data(self):
        ctx = _ctx_with_kernel()
        cell = _kernel_cell(ctx, "altdata", horizon=5)
        assert cell["shrunken_ic"] == pytest.approx(0.002903)
        assert cell["armed"] is False

    def test_missing_engine_returns_nulls(self):
        ctx = _ctx_with_kernel()
        cell = _kernel_cell(ctx, "nonexistent_engine", horizon=5)
        assert cell["shrunken_ic"] is None
        assert cell["armed"] is None

    def test_armed_engine_returns_true(self):
        ctx = _ctx_with_kernel()
        cell = _kernel_cell(ctx, "us_board", horizon=5)
        assert cell["armed"] is True


# ---------------------------------------------------------------------------
# 4. build_provenance: shape guarantees
# ---------------------------------------------------------------------------

class TestProvenance:
    """Each row MUST have the required fields, regardless of data availability."""

    REQUIRED_FIELDS = [
        "claim_source", "family", "qual_ladder", "synapse_tier",
        "kernel", "spine_ref", "graded_at", "staleness_days",
        "as_of", "direction", "is_display_only",
    ]
    REQUIRED_KERNEL_FIELDS = ["shrunken_ic", "wilson_ci_low", "n_eff", "armed"]
    REQUIRED_QUAL_FIELDS = ["ladder_state", "grandfathered", "note"]

    def _check_row(self, row: dict):
        for f in self.REQUIRED_FIELDS:
            assert f in row, f"provenance row missing field {f!r}: {row}"
        for f in self.REQUIRED_KERNEL_FIELDS:
            assert f in row["kernel"], f"kernel missing {f!r}"
        for f in self.REQUIRED_QUAL_FIELDS:
            assert f in row["qual_ladder"], f"qual_ladder missing {f!r}"
        assert row["is_display_only"] is True, "is_display_only must always be True"

    def test_altdata_row_shape(self):
        ctx = _ctx_with_altdata("AAPL")
        ctx.spine_latest["AAPL"] = {
            "altdata": {
                "signal_id": "test:001", "engine": "altdata", "family": "altdata",
                "ledger": "qledger", "as_of": "2026-06-19", "horizon": 63,
                "direction": 1, "score": 2.0, "outcome_excess": None,
                "outcome_graded": False, "graded_at": None,
            }
        }
        rows = build_provenance("AAPL", {}, ctx)
        assert len(rows) >= 1
        altdata_row = next(r for r in rows if r["claim_source"] == "altdata")
        self._check_row(altdata_row)

    def test_kernel_ic_value_correct(self):
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        altdata_row = next((r for r in rows if r["claim_source"] == "altdata"), None)
        assert altdata_row is not None
        assert altdata_row["kernel"]["shrunken_ic"] == pytest.approx(0.002903)

    def test_is_display_only_always_true(self):
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        for row in rows:
            assert row["is_display_only"] is True

    def test_no_row_has_money_path_flag(self):
        """No row should have a field that could be misread as a buy recommendation."""
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        for row in rows:
            # These fields must not appear on provenance rows (Article 1/2 guard)
            assert "buy" not in row, "provenance must not contain 'buy' key"
            assert "recommendation" not in row
            assert "action" not in row

    def test_spine_ref_set_when_available(self):
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        altdata_row = next((r for r in rows if r["claim_source"] == "altdata"), None)
        assert altdata_row is not None
        assert altdata_row["spine_ref"] == "qledger:e1f59f0a110a022f:63"

    def test_us_board_row_armed_true(self):
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        board_row = next((r for r in rows if r["claim_source"] == "us_board"), None)
        assert board_row is not None
        assert board_row["kernel"]["armed"] is True

    def test_empty_returns_list_not_raises(self):
        """Empty context must return [] not raise."""
        ctx = ProvenanceContext()
        rows = build_provenance("NVDA", {}, ctx)
        assert isinstance(rows, list)

    def test_missing_ticker_returns_empty(self):
        """Ticker not in spine or altdata → empty list."""
        ctx = _ctx_with_kernel()
        rows = build_provenance("ZZZZZ", {}, ctx)
        assert isinstance(rows, list)
        # no altdata, no spine → 0 rows (or only rows that don't need lookup)
        non_fund = [r for r in rows if r["claim_source"] != "fundamentals"]
        assert len(non_fund) == 0

    def test_all_rows_shape(self):
        ctx = _ctx_with_spine("NVDA")
        rows = build_provenance("NVDA", {}, ctx)
        for row in rows:
            self._check_row(row)


# ---------------------------------------------------------------------------
# 5. Fail-open: load_context with missing files
# ---------------------------------------------------------------------------

class TestLoadContextFailOpen:
    def test_missing_root_returns_empty_context(self, tmp_path):
        """load_context on an empty directory must not raise; returns empty context."""
        ctx = load_context(tmp_path)
        assert isinstance(ctx.kernel, dict)
        assert len(ctx.kernel) == 0
        assert isinstance(ctx.spine_latest, dict)
        assert isinstance(ctx.altdata_by_ticker, dict)

    def test_missing_kernel_estimates(self, tmp_path):
        ctx = load_context(tmp_path)
        assert ctx.kernel == {}

    def test_partial_directory_structure(self, tmp_path):
        """Only neuralweb dir present (no spine / altdata) — no exception."""
        (tmp_path / "data" / "neuralweb").mkdir(parents=True)
        ctx = load_context(tmp_path)
        assert isinstance(ctx, ProvenanceContext)


# ---------------------------------------------------------------------------
# 6. Committee page render smoke
# ---------------------------------------------------------------------------

def _jinja_env():
    """Load the real Jinja2 environment from templates/."""
    from jinja2 import Environment, FileSystemLoader
    root = Path(__file__).resolve().parent.parent
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,
    )
    return env, root


class TestCommitteePageRenderSmoke:
    """Smoke tests: template renders without errors and contains required elements."""

    def test_renders_without_error(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert html, "render produced empty output"
        assert "<!DOCTYPE html>" in html

    def test_contains_committee_view_heading(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "Committee View" in html

    def test_contains_disclaimer(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        # Compliance disclaimer must be present
        assert "not investment advice" in html.lower() or "Research" in html

    def test_contains_is_context_only(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "CONTEXT ONLY" in html or "is_context_only" in html.lower()

    def test_no_title_attribute_i18n_violation(self):
        """title= attributes must not contain translated text (CI guard law)."""
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        import re
        # Find all title="..." attrs; check for l-en/l-zh span markers inside
        titles = re.findall(r'title="([^"]*)"', html)
        for title_val in titles:
            assert "<span" not in title_val, (
                f"title attribute must not contain translated spans; found: {title_val!r}"
            )

    def test_contains_auth_gate(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        # Auth gate element must be present
        assert "cm_gate" in html
        assert "cm_signin_btn" in html

    def test_contains_navlinks_include(self):
        """_navlinks partial must be wired (via _site_nav)."""
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        # The nav logo is always present via _navlinks
        assert "MASTERMIND" in html

    def test_plain_english_box_present(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "In plain English" in html

    def test_living_graph_canvas_present(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "graph_canvas" in html

    def test_cortex_memo_section_present(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "Cortex Committee Memo" in html or "cm_memo_section" in html

    def test_kernel_family_cards_section_present(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "Kernel Family" in html or "cm_kf_grid" in html

    def test_supabase_cfg_injected(self):
        env, _ = _jinja_env()
        fake_cfg = '{"url":"https://test.supabase.co","anonKey":"test-key"}'
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json=fake_cfg,
        )
        assert "test.supabase.co" in html

    def test_committee_nav_link_in_navlinks(self):
        """committee.html must be linked from _navlinks via _site_nav."""
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "committee.html" in html

    def test_generated_utc_injected(self):
        env, _ = _jinja_env()
        html = env.get_template("committee.html.j2").render(
            generated_utc="2026-07-04T12:00:00Z",
            supabase_cfg_json="null",
        )
        assert "2026-07-04T12:00:00Z" in html
