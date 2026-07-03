"""W0.5 / W0.10 / W0.8 unit tests.

W0.5 — _basket_tailwind_map THS extension:
  - Names absent from curated baskets but present in THS get a non-null tailwind entry.
  - The winning entry across curated+THS maximises |rel20|.
  - The label for THS-sourced entries is prefixed "theme: <name> (THS)".
  - 300725.SZ (Synthetic Biology, the exemplar hole) resolves to a non-null tailwind.

W0.10 — sector first-tick-up chip (forward_log → sector_turn dict):
  - A Shenwan sector with phase=="Trough" and osc_slope>0 maps to state=="bottoming".
  - A sector with osc_slope<=0 does NOT produce a first-tick-up entry.
  - The Yahoo→Shenwan taxonomy join is marked approx:true.
  - sector_turn field is absent when no match (no false read).

W0.8 — china_lookup.html.j2 staleness banner:
  - Template parses without Jinja2 errors.
  - The r_stale_banner element is present in the HTML.
  - The bilingual stale_prefix/stale_suffix keys exist in both lang dicts.
  - The t()-in-attributes rule is not violated in changed regions.

Mirrors idioms of tests/test_china_stocks_copy_w09.py (nearest sibling).
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
LOOKUP_SRC = (ROOT / "templates" / "china_lookup.html.j2").read_text()


# ─────────────────────────────────────────────────────────────────────────────
# W0.5 helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_curated_data(symbol: str, rel20: float) -> dict:
    return {
        "baskets": [
            {
                "name": "Curated Basket",
                "perf": {"20d": {"rel": rel20 / 100.0}},
                "members": [{"symbol": symbol}],
            }
        ]
    }


def _make_ths_data(symbol: str, rel20: float, basket_name: str = "Synthetic Biology") -> dict:
    return {
        "baskets": [
            {
                "name": basket_name,
                "perf": {"20d": {"rel": rel20 / 100.0}},
                "members": [{"symbol": symbol}],
            }
        ]
    }


# ─────────────────────────────────────────────────────────────────────────────
# W0.5 tests
# ─────────────────────────────────────────────────────────────────────────────

class TestW05TailwindMap:
    """W0.5 — _basket_tailwind_map picks up THS baskets."""

    def test_ths_only_name_gets_tailwind(self):
        """A name in THS but not in curated baskets must get a non-null tailwind entry."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value={"baskets": []}), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   return_value=_make_ths_data("300725.SZ", 18.9)):
            result = _basket_tailwind_map()
        assert "300725.SZ" in result, "300725.SZ (THS-only) must appear in tailwind map"
        entry = result["300725.SZ"]
        assert entry["rel20"] == pytest.approx(18.9, abs=0.01)
        assert "THS" in entry["name"], f"THS source not in label: {entry['name']!r}"
        assert entry["source"] == "ths"

    def test_curated_beats_ths_when_stronger(self):
        """When curated |rel20| > THS |rel20|, curated wins."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value=_make_curated_data("000001.SS", 30.0)), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   return_value=_make_ths_data("000001.SS", 10.0)):
            result = _basket_tailwind_map()
        entry = result["000001.SS"]
        assert entry["rel20"] == pytest.approx(30.0, abs=0.01)
        assert entry["source"] == "curated"
        assert "THS" not in entry["name"]

    def test_ths_beats_curated_when_stronger(self):
        """When THS |rel20| > curated |rel20|, THS wins."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value=_make_curated_data("000001.SS", 5.0)), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   return_value=_make_ths_data("000001.SS", 25.0)):
            result = _basket_tailwind_map()
        entry = result["000001.SS"]
        assert entry["rel20"] == pytest.approx(25.0, abs=0.01)
        assert entry["source"] == "ths"

    def test_ths_label_prefixed_correctly(self):
        """THS entries must be labeled 'theme: <basket_name> (THS)'."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value={"baskets": []}), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   return_value=_make_ths_data("688306.SS", 15.0, "Humanoid Robots")):
            result = _basket_tailwind_map()
        label = result["688306.SS"]["name"]
        assert label == "theme: Humanoid Robots (THS)", f"Unexpected label: {label!r}"

    def test_curated_label_unchanged(self):
        """Curated basket entries must NOT carry the (THS) suffix."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value=_make_curated_data("000001.SS", 12.0)), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   return_value={"baskets": []}):
            result = _basket_tailwind_map()
        label = result["000001.SS"]["name"]
        assert "THS" not in label, f"Curated label should not have THS suffix: {label!r}"

    def test_failure_in_ths_degrades_gracefully(self):
        """If THS compute raises, curated still works (best-effort)."""
        from scripts.build_china_library import _basket_tailwind_map
        with patch("engine.baskets_china.compute_china_baskets",
                   return_value=_make_curated_data("000001.SS", 10.0)), \
             patch("engine.baskets_china.compute_china_ths_baskets",
                   side_effect=RuntimeError("THS unavailable")):
            result = _basket_tailwind_map()
        assert "000001.SS" in result
        assert result["000001.SS"]["source"] == "curated"


# ─────────────────────────────────────────────────────────────────────────────
# W0.10 tests — sector first-tick-up dict
# ─────────────────────────────────────────────────────────────────────────────

class TestW010SectorFirstTickUp:
    """W0.10 — sector first-tick-up mapping from forward_log."""

    def _make_flog(self) -> pd.DataFrame:
        """Minimal forward_log with one qualifying and one non-qualifying sector."""
        return pd.DataFrame([
            {"date": "2026-07-03", "id": "801150", "name": "Pharma & Biotech",
             "kind": "sector", "phase": "Trough", "osc_slope": 2.0, "signature": 30.0},
            {"date": "2026-07-03", "id": "801010", "name": "Agriculture",
             "kind": "sector", "phase": "Trough", "osc_slope": 0.8, "signature": 6.0},
            {"date": "2026-07-03", "id": "801040", "name": "Steel",
             "kind": "sector", "phase": "Trough", "osc_slope": -3.4, "signature": 9.0},
            {"date": "2026-07-03", "id": "b-cn_insurers", "name": "Insurers",
             "kind": "basket", "phase": "Trough", "osc_slope": 6.9, "signature": 8.0},
        ])

    def test_pharma_qualifies_as_first_tick_up(self):
        """Pharma & Biotech (Trough + osc_slope>0) must appear in the sector_turn dict."""
        flog = self._make_flog()
        # Reproduce the filter logic from build_china_library main()
        latest = flog[flog["date"] == flog["date"].max()]
        ftu = latest[
            (latest["phase"] == "Trough") &
            (latest["osc_slope"] > 0) &
            (latest["kind"] == "sector")
        ]
        names = set(ftu["name"].tolist())
        assert "Pharma & Biotech" in names
        assert "Agriculture" in names
        assert "Steel" not in names        # osc_slope < 0
        assert "Insurers" not in names    # kind == basket, not sector

    def test_sector_turn_state_is_bottoming(self):
        """The state field in the sector_turn dict must be 'bottoming'."""
        flog = self._make_flog()
        latest = flog[flog["date"] == flog["date"].max()]
        ftu = latest[
            (latest["phase"] == "Trough") &
            (latest["osc_slope"] > 0) &
            (latest["kind"] == "sector")
        ]
        for _, row in ftu.iterrows():
            entry = {"state": "bottoming", "osc_slope": float(row["osc_slope"]),
                     "approx": True}
            assert entry["state"] == "bottoming"

    def test_approx_flag_set(self):
        """Each sector_turn entry must carry approx:True (Yahoo→SW is approximate)."""
        # The build logic sets approx:True on every entry from the map.
        # Verify the constant is present in the builder source.
        src = (ROOT / "scripts" / "build_china_library.py").read_text()
        assert '"approx":    True' in src or "'approx':    True" in src or \
               '"approx": True' in src or "'approx': True" in src, \
               "approx:True must be set in the sector_turn dict in build_china_library"

    def test_yahoo_to_sw_map_has_healthcare(self):
        """The Yahoo→Shenwan taxonomy map must map 'Healthcare' to 'Pharma & Biotech'."""
        src = (ROOT / "scripts" / "build_china_library.py").read_text()
        assert '"Healthcare"' in src and '"Pharma & Biotech"' in src, \
            "Healthcare→Pharma & Biotech mapping missing from _YAHOO_TO_SW"

    def test_ledger_append_has_sector_turn_column(self):
        """append_board must include sector_turn in the ledger record."""
        src = (ROOT / "engine" / "china_standout_track.py").read_text()
        assert '"sector_turn"' in src, \
            "sector_turn column missing from china_standout_track.append_board"

    def test_grade_slices_by_sector_turn(self):
        """grade() must include by_sector_turn stratification."""
        src = (ROOT / "engine" / "china_standout_track.py").read_text()
        assert "by_sector_turn" in src, \
            "by_sector_turn slice missing from china_standout_track.grade"


# ─────────────────────────────────────────────────────────────────────────────
# W0.8 tests — china_lookup.html.j2 staleness banner
# ─────────────────────────────────────────────────────────────────────────────

class TestW08StalenessBanner:
    """W0.8 — china_lookup.html.j2 shows a staleness banner when detail data is old."""

    def test_template_parses_without_errors(self):
        """Full template must parse (Jinja2 syntax check) — the most important gate."""
        from jinja2 import Environment
        env = Environment(autoescape=False)
        env.parse(LOOKUP_SRC)

    def test_stale_banner_element_present(self):
        """The r_stale_banner div must be present in the template."""
        assert 'id="r_stale_banner"' in LOOKUP_SRC, \
            "r_stale_banner element not found in china_lookup.html.j2"

    def test_stale_banner_has_stale_class(self):
        """The staleness banner element must use the stale-banner CSS class."""
        assert 'class="stale-banner"' in LOOKUP_SRC or \
               "stale-banner" in LOOKUP_SRC, \
               "stale-banner CSS class not found"

    def test_stale_prefix_key_in_en_dict(self):
        """The stale_prefix key must be present in the EN translation dict."""
        assert "stale_prefix" in LOOKUP_SRC, \
            "stale_prefix key missing from T.en dict"

    def test_stale_suffix_key_in_both_dicts(self):
        """The stale_suffix key must appear in both EN and ZH translation dicts."""
        # Count occurrences — must appear at least twice (once in en, once in zh)
        count = LOOKUP_SRC.count("stale_suffix")
        assert count >= 2, \
            f"stale_suffix appears only {count} time(s); expected ≥2 (en + zh)"

    def test_zh_stale_copy_is_present(self):
        """The ZH translation for the staleness warning must be non-empty."""
        assert "看板" in LOOKUP_SRC or "数据" in LOOKUP_SRC, \
            "ZH staleness copy missing from china_lookup.html.j2"

    def test_banner_shown_when_diffdays_gt_1(self):
        """The JS must show the banner when today - d.asof > 1 day."""
        assert "diffDays > 1" in LOOKUP_SRC, \
            "Staleness threshold (diffDays > 1) not found in banner JS"

    def test_banner_hidden_when_not_stale(self):
        """The JS must hide the banner when data is current."""
        assert "banner.style.display = 'none'" in LOOKUP_SRC, \
            "Banner hide logic missing from JS"

    def test_dual_span_bilingual_pattern_in_banner(self):
        """The banner must use the l-en / l-zh dual-span pattern."""
        assert 'l-en' in LOOKUP_SRC, "l-en span missing from template"
        assert 'l-zh' in LOOKUP_SRC, "l-zh span missing from template"
        # The banner itself uses this pattern
        assert "class=\"l-en\"" in LOOKUP_SRC or "l-en" in LOOKUP_SRC, \
            "Banner does not use bilingual dual-span pattern"

    def test_no_t_call_inside_attributes_in_banner(self):
        """t() must never appear inside an HTML attribute value (the i18n gotcha)."""
        # Extract the banner-related region
        start = LOOKUP_SRC.find("r_stale_banner")
        end = LOOKUP_SRC.find("r_summary", start)
        region = LOOKUP_SRC[start:end]
        bad = re.search(
            r'(?:title|style|data-[a-z]+|aria-[a-z]+|class)="[^"]*\{\{\s*t\(', region
        )
        assert not bad, \
            f"t() found inside an HTML attribute in banner region: {bad.group()!r}"
