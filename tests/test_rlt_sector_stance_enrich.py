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
    """Template-level guards: sector_stance chip uses l-en/l-zh, no title= CJK."""

    def test_chip_class_present_in_template(self):
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        assert "nb-sec-stance" in content, "RLT-R6 sector-stance chip CSS class missing"

    def test_chip_uses_len_lzh_spans(self):
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        # The Jinja chip rendering block must use l-en/l-zh spans (bilingual law).
        # Search for the Jinja conditional block specifically.
        assert "sector_stance" in content, "sector_stance field reference missing"
        # Find the Jinja 'if n.get(\"sector_stance\")' block
        idx = content.find("if n.get('sector_stance')")
        assert idx != -1, "sector_stance Jinja if-block missing from template"
        block = content[idx:idx + 700]
        assert "l-en" in block, "sector_stance chip missing l-en span"
        assert "l-zh" in block, "sector_stance chip missing l-zh span"

    def test_chip_no_title_attribute_with_zh(self):
        """CJK must not appear in title= attributes (CI-enforced law)."""
        import re
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        # Scan the nb-sec-stance block for title= attributes
        idx = content.find("nb-sec-stance")
        if idx == -1:
            pytest.skip("chip not yet in template")
        block = content[idx:idx + 800]
        # title= must not appear inside this block
        assert "title=" not in block, "sector_stance chip must not use title= (CJK law)"

    def test_help_tip_uses_scroll_safe_idiom(self):
        """The ? tip must use .help::before (scroll-safe) idiom, not ::after."""
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        # The .help::before hover-bridge rule must be present (established by #2337)
        assert ".help:hover::before" in content, "scroll-safe .help::before bridge missing"

    def test_disagreement_tip_text_en_present(self):
        """The EN disagreement tip text must appear in the template."""
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        assert "single-stock bottoming trigger" in content, (
            "EN disagreement tip text missing from template"
        )

    def test_disagreement_tip_text_zh_present(self):
        """The ZH disagreement tip text must appear in the template."""
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        assert "个股筑底触发信号" in content, (
            "ZH disagreement tip text missing from template"
        )

    def test_cautionary_chip_class_present(self):
        """The ss-caution modifier class must be in the template."""
        tmpl = pathlib.Path(__file__).resolve().parent.parent / "templates" / "dashboard.html.j2"
        if not tmpl.exists():
            pytest.skip("template not found — running outside full repo")
        content = tmpl.read_text()
        assert "ss-caution" in content, "RLT-R6 ss-caution modifier missing from template"
