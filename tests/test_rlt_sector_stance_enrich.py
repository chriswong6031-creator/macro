"""Unit tests for RLT-R6 sector-stance disclosure enrichment.

Covers the enrich logic that joins sector_central verdicts onto each standout
row in build_site._enrich_standouts_sector_stance (implemented inline in the
build_site main flow). Tests use synthetic standout rows and synthetic
sector_central verdicts; no network calls and no live data reads.

Authority: display-only. The enrichment never touches selection, rank, or gates.
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Helpers — a minimal synthetic sector_central payload
# ---------------------------------------------------------------------------

def _sc_payload(sectors: list[dict]) -> dict:
    """Minimal sector_central.json-shaped dict."""
    return {"as_of": "2026-07-12", "sectors": sectors}


def _sc_sector(ticker: str, label_en: str, label_zh: str, score: int) -> dict:
    return {
        "ticker": ticker,
        "name": "Test",
        "conviction": {"label_en": label_en, "label_zh": label_zh, "score": score},
    }


def _standout_row(ticker: str, sector: str) -> dict:
    return {"ticker": ticker, "name": ticker + " Inc", "sector": sector, "alpha": 0.1}


# ---------------------------------------------------------------------------
# The enrichment logic extracted for unit testing
# (mirrors the inline block in build_site.py exactly — if the block changes,
#  update this helper to match)
# ---------------------------------------------------------------------------

def _apply_enrichment(us_standouts: dict, sc_doc: dict) -> None:
    """Apply the RLT-R6 join in-place (mirrors build_site logic).

    Only the buy lane is enriched — watch rows are never rendered as cards
    so their enrichment would be dead code.
    """
    from engine.spotlight import GICS_TO_ETF as _GICS_ETF

    _sc_by_etf: dict[str, tuple[str, str]] = {}
    for _sec in (sc_doc.get("sectors") or []):
        _etf = _sec.get("ticker")
        _conv = _sec.get("conviction") or {}
        if _etf and _conv.get("label_en"):
            _sc_by_etf[_etf] = (
                _conv["label_en"],
                _conv.get("label_zh") or _conv["label_en"],
            )

    for _card in (us_standouts.get("buy") or []):
        _gics = _card.get("sector") or ""
        _etf = _GICS_ETF.get(_gics)
        if _etf and _etf in _sc_by_etf:
            _lbl_en, _lbl_zh = _sc_by_etf[_etf]
            _card["sector_stance"] = _lbl_en
            _card["sector_stance_zh"] = _lbl_zh


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSectorStanceEnrichBasic:
    def test_buy_row_gets_stance_fields(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows = {"buy": [_standout_row("VTRS", "Health Care")], "watch": []}
        _apply_enrichment(rows, sc)
        card = rows["buy"][0]
        assert card["sector_stance"] == "Reduce"
        assert card["sector_stance_zh"] == "减配"

    def test_watch_row_not_enriched(self):
        """Watch rows are card-less (never rendered) — enrichment is buy-only."""
        sc = _sc_payload([_sc_sector("XLRE", "Reduce", "减配", 15)])
        rows = {"buy": [], "watch": [_standout_row("GNL", "Real Estate")]}
        _apply_enrichment(rows, sc)
        # watch lane must NOT receive stance fields (no card rendering surface)
        assert "sector_stance" not in rows["watch"][0]

    def test_buy_lane_enriched_watch_untouched(self):
        sc = _sc_payload([
            _sc_sector("XLV", "Reduce", "减配", 25),
            _sc_sector("XLRE", "Reduce", "减配", 15),
        ])
        rows = {
            "buy": [_standout_row("VTRS", "Health Care")],
            "watch": [_standout_row("GNL", "Real Estate")],
        }
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Reduce"
        # watch row must remain unmodified
        assert "sector_stance" not in rows["watch"][0]

    def test_accumulate_sector_gets_positive_stance(self):
        sc = _sc_payload([_sc_sector("XLU", "Accumulate", "积极配置", 74)])
        rows = {"buy": [_standout_row("SO", "Utilities")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Accumulate"

    def test_constructive_sector(self):
        sc = _sc_payload([_sc_sector("XLE", "Constructive", "建设性", 65)])
        rows = {"buy": [_standout_row("XOM", "Energy")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Constructive"

    def test_neutral_sector(self):
        sc = _sc_payload([_sc_sector("XLK", "Neutral", "中性", 57)])
        rows = {"buy": [_standout_row("AAPL", "Information Technology")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Neutral"

    def test_cautious_sector(self):
        sc = _sc_payload([_sc_sector("XLB", "Cautious", "谨慎", 38)])
        rows = {"buy": [_standout_row("NEM", "Materials")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Cautious"


class TestSectorStanceEnrichFallback:
    def test_missing_sector_field_no_crash(self):
        """Row with no sector key -> no stance fields added, no crash."""
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        row = {"ticker": "VTRS", "name": "Viatris Inc", "alpha": 0.1}
        rows = {"buy": [row], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]

    def test_empty_sector_string_no_crash(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows = {"buy": [_standout_row("VTRS", "")], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]

    def test_none_sector_no_crash(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        row = {"ticker": "VTRS", "name": "Viatris", "sector": None, "alpha": 0.1}
        rows = {"buy": [row], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]

    def test_unmapped_gics_sector_no_crash(self):
        """A GICS name not in GICS_TO_ETF -> field silently absent."""
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows = {"buy": [_standout_row("ZZZZ", "NotARealSector")], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]

    def test_sector_etf_absent_from_sc_doc_no_crash(self):
        """GICS maps to XLK but sector_central doc has no XLK entry."""
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows = {"buy": [_standout_row("AAPL", "Information Technology")], "watch": []}
        _apply_enrichment(rows, sc)
        # XLK not in sc_doc -> no stance field on AAPL
        assert "sector_stance" not in rows["buy"][0]

    def test_empty_sectors_list_no_crash(self):
        sc = _sc_payload([])
        rows = {"buy": [_standout_row("VTRS", "Health Care")], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]

    def test_empty_buy_and_watch_no_crash(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows: dict = {"buy": [], "watch": []}
        _apply_enrichment(rows, sc)  # should not raise

    def test_missing_lanes_no_crash(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        rows: dict = {}  # no buy/watch keys
        _apply_enrichment(rows, sc)  # should not raise

    def test_sc_sector_missing_conviction_no_crash(self):
        """Sector entry with no conviction block -> silently skipped."""
        sc = _sc_payload([{"ticker": "XLV", "name": "Health Care"}])
        rows = {"buy": [_standout_row("VTRS", "Health Care")], "watch": []}
        _apply_enrichment(rows, sc)
        assert "sector_stance" not in rows["buy"][0]


class TestSectorStanceNoSelectionEffect:
    """Verify enrichment is purely additive — does not touch any existing field."""

    def test_existing_fields_unchanged(self):
        sc = _sc_payload([_sc_sector("XLV", "Reduce", "减配", 25)])
        row = _standout_row("VTRS", "Health Care")
        row.update({"composite": 0.85, "alpha": 1.2, "conviction": {"score": 72}})
        rows = {"buy": [copy.deepcopy(row)], "watch": []}
        _apply_enrichment(rows, sc)
        card = rows["buy"][0]
        # All pre-existing fields unchanged
        assert card["composite"] == 0.85
        assert card["alpha"] == 1.2
        assert card["conviction"]["score"] == 72
        assert card["ticker"] == "VTRS"
        assert card["sector"] == "Health Care"
        # Only new fields added
        assert card["sector_stance"] == "Reduce"

    def test_multiple_rows_independent(self):
        """Enrichment on one row must not affect another row."""
        sc = _sc_payload([
            _sc_sector("XLV", "Reduce", "减配", 25),
            _sc_sector("XLK", "Neutral", "中性", 57),
        ])
        rows = {
            "buy": [
                _standout_row("VTRS", "Health Care"),
                _standout_row("AAPL", "Information Technology"),
            ],
            "watch": [],
        }
        _apply_enrichment(rows, sc)
        assert rows["buy"][0]["sector_stance"] == "Reduce"
        assert rows["buy"][1]["sector_stance"] == "Neutral"


class TestGICSAliases:
    """GICS_TO_ETF covers several alias forms — verify key aliases work."""

    def test_information_technology_alias(self):
        sc = _sc_payload([_sc_sector("XLK", "Neutral", "中性", 57)])
        rows = {"buy": [_standout_row("AAPL", "Information Technology")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0].get("sector_stance") == "Neutral"

    def test_consumer_discretionary(self):
        sc = _sc_payload([_sc_sector("XLY", "Neutral", "中性", 48)])
        rows = {"buy": [_standout_row("AMZN", "Consumer Discretionary")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0].get("sector_stance") == "Neutral"

    def test_consumer_staples(self):
        sc = _sc_payload([_sc_sector("XLP", "Neutral", "中性", 47)])
        rows = {"buy": [_standout_row("KO", "Consumer Staples")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0].get("sector_stance") == "Neutral"

    def test_communication_services(self):
        sc = _sc_payload([_sc_sector("XLC", "Neutral", "中性", 57)])
        rows = {"buy": [_standout_row("GOOG", "Communication Services")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0].get("sector_stance") == "Neutral"

    def test_financials(self):
        sc = _sc_payload([_sc_sector("XLF", "Cautious", "谨慎", 37)])
        rows = {"buy": [_standout_row("JPM", "Financials")], "watch": []}
        _apply_enrichment(rows, sc)
        assert rows["buy"][0].get("sector_stance") == "Cautious"


class TestTemplateChipPresence:
    """Template guards for the sector-stance disclosure (RLT-R6), post prophet card v1.

    fe7a7426c49 (operator-ratified redesign, 2026-07-22) retired the standalone
    .nb-sec-stance chip; the ratified home is now a row in the prophet card's
    ⚠N flags popover. Pinned here: the dashboard still folds sector_stance into
    the flag rows (cautionary stances only), the single-stock-vs-sector
    disagreement copy survives in BOTH languages, and the popover renders rows
    through the bilingual l-en/l-zh idiom with no title= attribute (CJK law).
    """

    def _template(self) -> str:
        """The dashboard's board markup: dashboard.html.j2 + the us-board card
        partial it includes.

        The pv_card call site — and with it the sector_stance fold and its
        bilingual disagreement copy — moved into _us_board_cards.html.j2 when the
        us_stocks board gained its server-side tier split
        (docs/TIER_PREVIEW_PATTERN.md), so the shell and the /premiumdata/ payload
        render cards from ONE source. Reading the pair keeps these checks pointed
        at the markup rather than at the file it used to sit in.
        """
        root = pathlib.Path(__file__).resolve().parent.parent / "templates"
        tmpl = root / "dashboard.html.j2"
        cards = root / "_us_board_cards.html.j2"
        if not tmpl.exists() or not cards.exists():
            pytest.skip("template not found — running outside full repo")
        return tmpl.read_text() + cards.read_text()

    def test_stance_folded_into_flag_rows(self):
        """dashboard.html.j2 must fold sector_stance into the pv_card flag rows."""
        content = self._template()
        idx = content.find("if n.get('sector_stance')")
        assert idx != -1, "sector_stance Jinja if-block missing from template"
        block = content[idx:idx + 700]
        assert "_fl.rows" in block, (
            "sector_stance no longer folds into the prophet-card flag rows — "
            "the demoted RLT-R6 home was dropped"
        )
        assert "'Reduce','Cautious'" in block.replace(", ", ","), (
            "stance flag row must stay scoped to the cautionary stances "
            "(Reduce/Cautious) — a sector in Accumulate/Neutral is not a caution"
        )

    def test_disagreement_tip_text_en_present(self):
        """The EN disagreement copy (single-stock trigger vs sector call) must survive."""
        content = self._template()
        assert "single-stock trigger, not a sector call" in content, (
            "EN disagreement copy missing from template (ratified prophet-card wording)"
        )

    def test_disagreement_tip_text_zh_present(self):
        """The ZH disagreement copy must survive."""
        content = self._template()
        assert "个股信号，非板块判断" in content, (
            "ZH disagreement copy missing from template (ratified prophet-card wording)"
        )

    def test_flags_popover_renders_bilingual_rows_no_title(self):
        """The ⚠N popover renders stance rows via l-en/l-zh spans, never title=."""
        import jinja2
        repo = pathlib.Path(__file__).resolve().parent.parent
        if not (repo / "templates" / "_prophet_card.html.j2").exists():
            pytest.skip("prophet card template not found — running outside full repo")
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(repo / "templates")),
            undefined=jinja2.Undefined, autoescape=False,
        )
        tpl = env.from_string(
            '{% import "_prophet_card.html.j2" as pv %}{{ pv.pv_card(cx) }}'
        )
        out = tpl.render(cx={
            "href": "stock.html#JPM", "tk": "JPM", "mkt": "us", "verb": "near",
            "flags": [(
                "Sector stance: Cautious — single-stock trigger, not a sector call",
                "板块态度：谨慎 — 个股信号，非板块判断",
            )],
        })
        assert "pv-cau-row" in out, "flags popover row markup missing"
        assert 'class="l-en"' in out and 'class="l-zh"' in out, (
            "popover rows must render through the bilingual l-en/l-zh idiom"
        )
        assert "个股信号，非板块判断" in out
        assert "title=" not in out, "prophet card must not use title= (CJK title= law)"

    def test_help_tip_uses_scroll_safe_idiom(self):
        """The ? tip must use .help::before (scroll-safe) idiom, not ::after."""
        content = self._template()
        # The .help::before hover-bridge rule must be present (established by #2337)
        assert ".help:hover::before" in content, "scroll-safe .help::before bridge missing"
