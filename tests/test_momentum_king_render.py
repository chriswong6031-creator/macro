"""tests/test_momentum_king_render.py — Hermetic render smoke tests for
templates/momentum_king.html.j2.

Coverage:
  - No Jinja exception on any of: LEADER_CANDIDATE, CONTESTED, NO_CLEAR_LEADER sectors
  - A member with null alpha and null species renders without error
  - Empty top_candidates board renders the explicit abstain message
  - Output contains schema identifier token and the page title string
  - Output contains NO literal "None" or "NaN" or "nan" substring
  - FileSystemLoader is pointed at the real templates/ dir so
    {% include '_navlinks.html.j2' %} resolves without error
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"


# ── Fixture builders ──────────────────────────────────────────────────────────

def _member(
    ticker: str,
    alpha=1.5,
    sector_rank=1,
    sector_n=40,
    species="FRESH_INITIATION",
    trend_legs=3,
    fresh_cross=True,
    ticks_since_cross=2,
    residual_entry="intact",
    rev_pctile=55,
    eligible=True,
    based=True,
    extended=False,
    reasons=None,
) -> dict:
    return {
        "ticker": ticker,
        "name": f"{ticker} Corp",
        "sector": "Information Technology",
        "alpha": alpha,
        "sector_rank": sector_rank,
        "sector_n": sector_n,
        "residual_entry": residual_entry,
        "rev_pctile": rev_pctile,
        "species": species,
        "trend_legs": trend_legs,
        "fresh_cross": fresh_cross,
        "ticks_since_cross": ticks_since_cross,
        "extended": extended,
        "based": based,
        "eligible": eligible,
        "gates": {"alpha_leader": True, "confluence_bull": True, "not_extended": True},
        "reasons": reasons or [],
    }


def _sector(name: str, state: str, leader=None, dominance_margin=0.5, n=40, members=None) -> dict:
    return {
        "sector": name,
        "state": state,
        "leader": leader,
        "dominance_margin": dominance_margin,
        "n": n,
        "members": members or [],
    }


def _mk_board(
    top_candidates=None,
    sectors=None,
    as_of="2026-07-14",
    stale=False,
    n_leader_candidates=1,
    n_contested=2,
    n_no_clear_leader=8,
    n_sectors=11,
) -> dict:
    return {
        "schema": "momentum_king.v1",
        "as_of": as_of,
        "stale": stale,
        "note": "test fixture",
        "built_utc": "2026-07-14T00:00:00+00:00",
        "params": {
            "alpha_leader_min": 0.5,
            "min_trend_legs": 2,
            "dominance_tau": 0.5,
            "fresh_within": 3,
            "extended_atr": 2.0,
        },
        "coverage": {
            "n_sectors": n_sectors,
            "n_leader_candidates": n_leader_candidates,
            "n_contested": n_contested,
            "n_no_clear_leader": n_no_clear_leader,
        },
        "top_candidates": top_candidates if top_candidates is not None else [],
        "sectors": sectors if sectors is not None else [],
    }


def _render(mk: dict) -> str:
    """Render the template and return the HTML string.  Raises on any Jinja error."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False)
    tpl = env.get_template("momentum_king.html.j2")
    return tpl.render(mk=mk)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestThreeStateRender:
    """One test per sector state to confirm no Jinja exception."""

    def test_leader_candidate_renders(self):
        m = _member("NVDA", alpha=1.8)
        sec = _sector("Information Technology", "LEADER_CANDIDATE", leader="NVDA", members=[m])
        tc = [
            {"ticker": "NVDA", "name": "NVIDIA", "sector": "Information Technology",
             "alpha": 1.8, "species": "FRESH_INITIATION", "trend_legs": 3,
             "fresh_cross": True, "ticks_since_cross": 2}
        ]
        html = _render(_mk_board(top_candidates=tc, sectors=[sec]))
        assert "momentum_king.v1" in html or "Momentum King" in html

    def test_contested_renders(self):
        m1 = _member("AAPL", alpha=0.9)
        m2 = _member("MSFT", alpha=0.85, sector_rank=2)
        sec = _sector("Information Technology", "CONTESTED", leader=None,
                      dominance_margin=0.05, members=[m1, m2])
        html = _render(_mk_board(sectors=[sec]))
        assert "Contested" in html or "争议" in html

    def test_no_clear_leader_renders(self):
        m = _member("TSLA", alpha=0.2, eligible=False, reasons=["alpha below threshold"])
        sec = _sector("Consumer Discretionary", "NO_CLEAR_LEADER", leader=None,
                      dominance_margin=0.0, members=[m])
        html = _render(_mk_board(sectors=[sec]))
        assert "No Clear Leader" in html or "无明显领袖" in html


class TestNullFieldSafety:
    """Members with null alpha and null species must not emit literal None/NaN."""

    def test_null_alpha_no_literal_none(self):
        m = _member("ZZZZ", alpha=None, species=None, trend_legs=None,
                    ticks_since_cross=None, rev_pctile=None)
        sec = _sector("Utilities", "NO_CLEAR_LEADER", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        assert "None" not in html, "Literal 'None' found in rendered output"
        assert "NaN" not in html, "Literal 'NaN' found in rendered output"
        assert "nan" not in html, "Literal 'nan' found in rendered output"

    def test_null_top_candidate_fields(self):
        tc = [{"ticker": "ZZZZ", "name": None, "sector": None,
               "alpha": None, "species": None, "trend_legs": None,
               "fresh_cross": None, "ticks_since_cross": None}]
        html = _render(_mk_board(top_candidates=tc))
        assert "None" not in html
        assert "NaN" not in html

    def test_null_coverage_fields(self):
        """Coverage fields all null — should not crash or emit None."""
        board = _mk_board()
        board["coverage"] = {
            "n_sectors": None,
            "n_leader_candidates": None,
            "n_contested": None,
            "n_no_clear_leader": None,
        }
        html = _render(board)
        assert "None" not in html
        assert "NaN" not in html


class TestEmptyBoard:
    """Empty top_candidates should render the explicit abstain wording."""

    def test_abstain_message_present(self):
        html = _render(_mk_board(top_candidates=[], n_no_clear_leader=9))
        assert "honest abstain" in html or "诚实弃权" in html, (
            "Abstain wording missing for empty top_candidates board"
        )

    def test_abstain_message_no_none_literal(self):
        html = _render(_mk_board(top_candidates=[], sectors=[]))
        assert "None" not in html
        assert "NaN" not in html

    def test_empty_sectors_no_crash(self):
        html = _render(_mk_board(top_candidates=[], sectors=[]))
        assert html  # non-empty string


class TestStaleBanner:
    """Stale banner appears only when stale=True."""

    def test_stale_banner_shown(self):
        html = _render(_mk_board(stale=True))
        assert "stale" in html.lower() or "陈旧" in html

    def test_no_stale_banner_when_fresh(self):
        html = _render(_mk_board(stale=False))
        assert "banner-stale" not in html


class TestHtmlStructure:
    """Basic structural checks."""

    def test_schema_or_title_present(self):
        html = _render(_mk_board())
        assert "Momentum King" in html or "动量之王" in html

    def test_no_none_in_full_fixture(self):
        """Full fixture with all three states and mixed nulls."""
        m_null = _member("ABCD", alpha=None, species=None, trend_legs=None)
        m_ok = _member("NVDA", alpha=1.8)
        sectors = [
            _sector("IT", "LEADER_CANDIDATE", leader="NVDA", members=[m_ok]),
            _sector("Consumer", "CONTESTED", members=[m_null]),
            _sector("Utilities", "NO_CLEAR_LEADER", members=[]),
        ]
        tc = [{"ticker": "NVDA", "name": "NVIDIA", "sector": "IT",
               "alpha": 1.8, "species": "FRESH_INITIATION", "trend_legs": 3,
               "fresh_cross": True, "ticks_since_cross": 2}]
        html = _render(_mk_board(top_candidates=tc, sectors=sectors, stale=False))
        assert "None" not in html, "Literal 'None' in full-fixture render"
        assert "NaN" not in html, "Literal 'NaN' in full-fixture render"
        assert "nan" not in html, "Literal 'nan' in full-fixture render"

    def test_display_only_footer_present(self):
        html = _render(_mk_board())
        assert "Display-only" in html or "仅供展示" in html

    def test_species_fresh_chip(self):
        m = _member("NVDA", species="FRESH_INITIATION")
        sec = _sector("IT", "LEADER_CANDIDATE", leader="NVDA", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        # FRESH_INITIATION renders as Fresh / 新起
        assert "Fresh" in html or "新起" in html

    def test_species_established_chip(self):
        m = _member("AAPL", species="ESTABLISHED_CONTINUATION")
        sec = _sector("IT", "LEADER_CANDIDATE", leader="AAPL", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        assert "Cont." in html or "延续" in html

    def test_ineligible_member_dimmed(self):
        m = _member("LAGG", eligible=False, alpha=0.1, reasons=["alpha below threshold"])
        sec = _sector("Energy", "NO_CLEAR_LEADER", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        # ineligible rows carry class="ineligible"
        assert "ineligible" in html

    def test_witness_chips_absent_when_not_present(self):
        """net_inflow_witness and options_context absent from member → no witness chips."""
        m = _member("NVDA")
        # Remove optional witness fields entirely
        m.pop("net_inflow_witness", None)
        m.pop("options_context", None)
        sec = _sector("IT", "LEADER_CANDIDATE", leader="NVDA", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        # Should NOT render inflow/options badges when field absent
        assert "Inflow" not in html and "净流入" not in html

    def test_witness_chip_renders_when_present(self):
        """net_inflow_witness=True renders the inflow badge."""
        m = _member("NVDA")
        m["net_inflow_witness"] = True
        sec = _sector("IT", "LEADER_CANDIDATE", leader="NVDA", members=[m])
        html = _render(_mk_board(sectors=[sec]))
        assert "Inflow" in html or "净流入" in html
