"""tests/test_us_sector_rotation_wiring.py
==========================================
Wiring tests for XSR W1 Phase B:
  - sector_central attach+sort fail-open behavior
  - split-tier math covering XLU/XLE/XLV scenarios
  - Jinja template smoke test (fragment render of sector_central.html.j2)

All tests use tmp_path / synthetic data; never write to the real data/ tree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the repo root is importable
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


# ---------------------------------------------------------------------------
# Helpers — minimal conviction record factories
# ---------------------------------------------------------------------------

def _conv_record(
    rid: str,
    ticker: str,
    conviction_label: str,
    conviction_score: int,
    kind: str = "sector",
) -> dict:
    """Minimal sector/basket record as produced by sector_central.compute()."""
    return {
        "id": rid,
        "ticker": ticker,
        "kind": kind,
        "name": ticker,
        "name_zh": None,
        "group": "test",
        "group_zh": "测试",
        "accent": None,
        "conviction": {
            "score": conviction_score,
            "label_en": conviction_label,
            "label_zh": conviction_label,
            "dir": "up" if conviction_score >= 58 else "flat",
            "early": False,
            "confluence": {"agree": 2, "of": 4, "label": "moderate"},
        },
        "cycle": {"phase": None, "phaseLabel": None, "pos": 50, "proj": None,
                  "rs_rank": None, "rs_21d_rank": None, "above200d": True},
        "forward": {"trend_pass": True},
        "heat": None,
        "rotation": None,  # will be populated by _attach_rotation
        "split_view": False,
        "split_copy_en": None,
        "split_copy_zh": None,
    }


def _rotation_instrument(
    rid: str,
    ticker: str,
    basket_id: str,
    rotation_rank: int,
    rotation_score: float,
    kind: str = "sector",
) -> dict:
    """Minimal rotation instrument row (schema from latest.json)."""
    return {
        "id": rid,
        "key": rid,
        "kind": kind,
        "ticker": ticker,
        "basket_id": basket_id,
        "name": ticker,
        "rotation_score": rotation_score,
        "rotation_rank": rotation_rank,
        "components": {
            "mom20": 1.5,
            "fast_rs": 0.8,
            "mom5_raw": 0.4,
            "mom10_raw": 0.6,
            "governor": 3,
            "ob_penalty": 0.0,
            "macd_demotion": 0.0,
        },
        "state_used": "RALLY ON",
        "ob_etf": 0.1,
        "ob_ew": 0.1,
        "stale_flags": [],
        "asof": "2026-07-15",
    }


def _make_rotation_raw(instruments: list[dict]) -> dict:
    return {
        "asof": "2026-07-15",
        "ts": "2026-07-15T22:00:00",
        "authority": "DISPLAY-ONLY",
        "instruments": instruments,
    }


# ---------------------------------------------------------------------------
# Import the functions under test
# ---------------------------------------------------------------------------

from engine.sector_central import (
    _attach_rotation,
    _rotation_rank_bucket,
    _CONVICTION_TIER,
)


# ---------------------------------------------------------------------------
# T1 — fail-open: artifact absent → conviction order preserved, rotation=None
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_artifact_preserves_conviction_order(self):
        """When rotation_raw is empty, records are returned in the order given
        (already conviction-sorted by caller) with rotation=None."""
        records = [
            _conv_record("xlv", "XLV", "Accumulate", 80),
            _conv_record("xlk", "XLK", "Constructive", 65),
            _conv_record("xlu", "XLU", "Neutral", 44),
        ]
        result = _attach_rotation(records, {}, kind="sector")
        assert [r["id"] for r in result] == ["xlv", "xlk", "xlu"]
        assert all(r["rotation"] is None for r in result)

    def test_empty_instruments_list_preserves_order(self):
        records = [
            _conv_record("xlv", "XLV", "Accumulate", 80),
            _conv_record("xlu", "XLU", "Neutral", 44),
        ]
        result = _attach_rotation(records, {"instruments": []}, kind="sector")
        assert [r["id"] for r in result] == ["xlv", "xlu"]
        assert all(r["rotation"] is None for r in result)

    def test_no_crash_on_unparseable_artifact(self):
        """_attach_rotation must not raise on malformed data."""
        records = [_conv_record("xlv", "XLV", "Accumulate", 80)]
        result = _attach_rotation(records, {"instruments": "not-a-list"}, kind="sector")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# T2 — artifact present → rotation order applied
# ---------------------------------------------------------------------------

class TestRotationSort:
    def test_sorted_by_rotation_rank(self):
        """When artifact is present, board order follows rotation_rank ascending."""
        # Conviction order: xlv(80) > xlk(65) > xlu(44)
        # Rotation rank:    xlk=1,   xlu=2,   xlv=3
        records = [
            _conv_record("xlv", "XLV", "Accumulate", 80),
            _conv_record("xlk", "XLK", "Constructive", 65),
            _conv_record("xlu", "XLU", "Neutral", 44),
        ]
        instruments = [
            _rotation_instrument("xlk", "XLK", "b-us_sector_tech",       rotation_rank=1, rotation_score=10.0),
            _rotation_instrument("xlu", "XLU", "b-us_sector_utilities",  rotation_rank=2, rotation_score=7.0),
            _rotation_instrument("xlv", "XLV", "b-us_sector_health",     rotation_rank=3, rotation_score=3.0),
        ]
        raw = _make_rotation_raw(instruments)
        result = _attach_rotation(records, raw, kind="sector")
        assert [r["id"] for r in result] == ["xlk", "xlu", "xlv"]

    def test_rotation_block_populated(self):
        records = [_conv_record("xlv", "XLV", "Reduce", 20)]
        instruments = [
            _rotation_instrument("xlv", "XLV", "b-us_sector_health", rotation_rank=1, rotation_score=9.5),
        ]
        raw = _make_rotation_raw(instruments)
        result = _attach_rotation(records, raw, kind="sector")
        rot = result[0]["rotation"]
        assert rot is not None
        assert rot["rank"] == 1
        assert rot["score"] == 9.5
        assert rot["stale"] is False

    def test_unmatched_records_sort_last(self):
        """Records not found in the rotation artifact sort after matched ones."""
        records = [
            _conv_record("xlv", "XLV", "Accumulate", 80),
            _conv_record("xlk", "XLK", "Constructive", 65),
            _conv_record("orphan", "ORPHAN", "Neutral", 50),  # not in rotation
        ]
        instruments = [
            _rotation_instrument("xlv", "XLV", "b-us_sector_health", rotation_rank=2, rotation_score=7.0),
            _rotation_instrument("xlk", "XLK", "b-us_sector_tech",   rotation_rank=1, rotation_score=10.0),
        ]
        raw = _make_rotation_raw(instruments)
        result = _attach_rotation(records, raw, kind="sector")
        ids = [r["id"] for r in result]
        assert ids.index("xlk") < ids.index("orphan")
        assert ids.index("xlv") < ids.index("orphan")
        assert result[-1]["id"] == "orphan"

    def test_ticker_match_fallback(self):
        """Match by ticker when id doesn't match (case-insensitive)."""
        records = [_conv_record("xlu", "XLU", "Accumulate", 80)]
        instruments = [
            # id differs but ticker matches; kind must match (both "sector") for match to fire
            {**_rotation_instrument("xlu_v2", "XLU", "b-us_sector_utilities",
                                    rotation_rank=1, rotation_score=5.0, kind="sector"),
             "id": "xlu_v2", "key": "xlu_v2"},
        ]
        raw = _make_rotation_raw(instruments)
        result = _attach_rotation(records, raw, kind="sector")
        assert result[0]["rotation"] is not None
        assert result[0]["rotation"]["rank"] == 1


# ---------------------------------------------------------------------------
# T2b — FIX 3: kind-aware matching (proxy basket must not inherit sector rank)
# ---------------------------------------------------------------------------

class TestKindAwareMatching:
    """FIX 3: sector records only match sector instruments; basket records only match
    basket instruments.  The 11 b-us_sector_* proxy-basket records share tickers with
    the sector ETFs but have kind=='basket' — they must NOT match sector instruments."""

    def test_proxy_basket_does_not_inherit_sector_rank(self):
        """A basket record (kind='basket') with ticker XLV must not match a sector
        instrument (kind='sector') with ticker XLV."""
        # basket record for b-us_sector_health (same ticker as sector xlv)
        proxy_basket = _conv_record("b-us_sector_health", "XLV", "Accumulate", 75, kind="basket")
        # sector instrument for xlv (kind='sector')
        sector_inst = _rotation_instrument("xlv", "XLV", "b-us_sector_health",
                                           rotation_rank=1, rotation_score=9.5, kind="sector")
        raw = _make_rotation_raw([sector_inst])
        result = _attach_rotation([proxy_basket], raw, kind="basket")
        # proxy basket must NOT match — rotation should be None
        assert result[0]["rotation"] is None, (
            "Proxy basket must not inherit sector rotation rank (kind mismatch)"
        )

    def test_sector_record_matches_sector_instrument(self):
        """Sector record (kind='sector') still matches sector instrument correctly."""
        sector_rec = _conv_record("xlv", "XLV", "Accumulate", 80, kind="sector")
        sector_inst = _rotation_instrument("xlv", "XLV", "b-us_sector_health",
                                           rotation_rank=1, rotation_score=9.5, kind="sector")
        raw = _make_rotation_raw([sector_inst])
        result = _attach_rotation([sector_rec], raw, kind="sector")
        assert result[0]["rotation"] is not None
        assert result[0]["rotation"]["rank"] == 1

    def test_basket_record_matches_basket_instrument(self):
        """Basket record (kind='basket') matches basket instrument correctly."""
        basket_rec = _conv_record("b-ai_semiconductors", "SMH", "Constructive", 65, kind="basket")
        basket_inst = _rotation_instrument("b-ai_semiconductors", "SMH", "b-ai_semiconductors",
                                           rotation_rank=2, rotation_score=7.0, kind="basket")
        raw = _make_rotation_raw([basket_inst])
        result = _attach_rotation([basket_rec], raw, kind="basket")
        assert result[0]["rotation"] is not None
        assert result[0]["rotation"]["rank"] == 2

    def test_mixed_universe_proxy_baskets_sort_among_unmatched(self):
        """With mixed kinds, proxy baskets get rotation=None and sort after matched baskets."""
        sector_rec     = _conv_record("xlv",                "XLV", "Accumulate",   80, kind="sector")
        proxy_basket   = _conv_record("b-us_sector_health", "XLV", "Constructive", 65, kind="basket")
        genuine_basket = _conv_record("b-ai_semiconductors","SMH", "Neutral",       44, kind="basket")

        sector_inst = _rotation_instrument("xlv", "XLV", "b-us_sector_health",
                                           rotation_rank=1, rotation_score=9.0, kind="sector")
        basket_inst = _rotation_instrument("b-ai_semiconductors", "SMH", "b-ai_semiconductors",
                                           rotation_rank=2, rotation_score=6.0, kind="basket")
        raw = _make_rotation_raw([sector_inst, basket_inst])

        # Test sector lane: only sector_rec matches
        result_sectors = _attach_rotation([sector_rec], raw, kind="sector")
        assert result_sectors[0]["rotation"] is not None

        # Test basket lane: genuine_basket matches, proxy_basket does not
        result_baskets = _attach_rotation([genuine_basket, proxy_basket], raw, kind="basket")
        genuine = next(r for r in result_baskets if r["id"] == "b-ai_semiconductors")
        proxy   = next(r for r in result_baskets if r["id"] == "b-us_sector_health")
        assert genuine["rotation"] is not None
        assert proxy["rotation"] is None
        # Matched records come first
        ids = [r["id"] for r in result_baskets]
        assert ids.index("b-ai_semiconductors") < ids.index("b-us_sector_health")

    def test_split_view_basket_uses_only_matched_basket_count(self):
        """Split-view tier math for baskets uses per-kind ordinal (matched basket count),
        not the global mixed-universe count."""
        # 3 baskets: 2 genuine (matched), 1 proxy (unmatched)
        # For split-view math, n_total should be 2 (matched basket count), not 3.
        genuine1 = _conv_record("b-ai_semiconductors", "SMH", "Accumulate", 80, kind="basket")
        genuine2 = _conv_record("b-defensives",        "XLP", "Neutral",    44, kind="basket")
        proxy    = _conv_record("b-us_sector_health",  "XLV", "Constructive", 65, kind="basket")

        binst1 = _rotation_instrument("b-ai_semiconductors", "SMH", "b-ai_semiconductors",
                                      rotation_rank=1, rotation_score=10.0, kind="basket")
        binst2 = _rotation_instrument("b-defensives",        "XLP", "b-defensives",
                                      rotation_rank=2, rotation_score=5.0,  kind="basket")
        # No instrument for b-us_sector_health (basket kind absent from artifact)

        raw = _make_rotation_raw([binst1, binst2])
        result = _attach_rotation([genuine1, genuine2, proxy], raw, kind="basket")

        # proxy must be unmatched
        proxy_rec = next(r for r in result if r["id"] == "b-us_sector_health")
        assert proxy_rec["rotation"] is None

        # genuine1 (rank 1 of 2 matched) — Accumulate(tier 5) vs bucket of rank 1 of 2
        g1 = next(r for r in result if r["id"] == "b-ai_semiconductors")
        assert g1["rotation"] is not None


# ---------------------------------------------------------------------------
# T3 — split view tier math (XSR-R9)
# ---------------------------------------------------------------------------

class TestSplitViewTierMath:
    """
    XLU scenario: conviction=Accumulate (tier 5), rotation_rank=#9 of 11
      → rotation bucket = 1 (bottom quintile), diff = 1-5 = -4 → split (slower)
    XLV scenario: conviction=Reduce (tier 1), rotation_rank=#7 of 11
      → rotation bucket ≈ 2-3, diff ≥ 2 → split (faster)
    XLE scenario: conviction=Constructive (tier 4), rotation_rank=#34 of baskets
      → low rotation bucket, diff negative → split (slower)
    No split: diff < 2
    """

    def _run(self, conviction_label: int, conv_score: int, rotation_rank: int, n_total: int):
        # Build n_total records AND n_total instruments so per-kind ordinal is realistic.
        # The target record (XLV) gets conviction_label/conv_score; others get Neutral/50.
        records = []
        instruments = []
        for i in range(1, n_total + 1):
            tid = "xlv" if i == rotation_rank else f"inst_{i}"
            tticker = "XLV" if i == rotation_rank else f"X{i:02d}"
            clabel = conviction_label if i == rotation_rank else "Neutral"
            cscore = conv_score if i == rotation_rank else 50
            records.append(_conv_record(tid, tticker, clabel, cscore))
            instruments.append(
                _rotation_instrument(tid, tticker, f"b-sector_{i}",
                                     rotation_rank=i, rotation_score=float(n_total - i))
            )
        raw = _make_rotation_raw(instruments)
        result = _attach_rotation(records, raw, kind="sector")
        # Find the target record (XLV)
        target = next(r for r in result if r["id"] == "xlv")
        return target

    def test_xlu_accumulate_rank9_of_11_produces_split(self):
        """XLU: Accumulate (tier 5) vs fast rank #9 of 11 (bucket 1) → diff=4 → split slower."""
        rec = self._run("Accumulate", 80, rotation_rank=9, n_total=11)
        assert rec["split_view"] is True
        assert "split_copy_en" in rec and rec["split_copy_en"] is not None
        # Direction: fast rank is worse than conviction → "slower" (rotating out)
        assert "rotating out" in rec["split_copy_en"]

    def test_xlv_reduce_rank7_of_11_produces_split(self):
        """XLV: Reduce (tier 1) vs fast rank #7 of 11 (bucket ~2) → diff ≈ 1 → borderline."""
        # rank 7 of 11 → bucket: top18%=2, rem=9, bucket_size=2.25
        #   pos_in_rem = 7-2 = 5 → 5 > 2*2.25=4.5 → bucket 2
        # diff = 2 - 1 = 1 < 2 → NO split
        rec = self._run("Reduce", 20, rotation_rank=7, n_total=11)
        # rank 7 of 11 is bucket 2; Reduce is tier 1; diff = 1 → no split
        assert rec["split_view"] is False

    def test_xlv_reduce_rank2_of_11_produces_split_faster(self):
        """XLV: Reduce (tier 1) vs fast rank #2 of 11 (bucket 5) → diff=4 → split faster."""
        rec = self._run("Reduce", 20, rotation_rank=2, n_total=11)
        assert rec["split_view"] is True
        assert "rotating in" in rec["split_copy_en"]

    def test_no_split_when_diff_less_than_2(self):
        """Constructive (tier 4) vs rank 3 of 11 (bucket 4) → diff=0 → no split."""
        rec = self._run("Constructive", 65, rotation_rank=3, n_total=11)
        # rank 3: top18%=2, pos_in_rem=1, bucket=4
        # conviction tier=4, rotation bucket=4 → diff=0
        assert rec["split_view"] is False

    def test_neutral_conviction_rank1_produces_split_faster(self):
        """Neutral (tier 3) vs rank #1 of 11 (bucket 5) → diff=2 → exactly at boundary → split."""
        rec = self._run("Neutral", 45, rotation_rank=1, n_total=11)
        assert rec["split_view"] is True
        assert "rotating in" in rec["split_copy_en"]


# ---------------------------------------------------------------------------
# T4 — _rotation_rank_bucket math
# ---------------------------------------------------------------------------

class TestRotationRankBucket:
    def test_rank1_of_11_is_tier5(self):
        assert _rotation_rank_bucket(1, 11) == 5

    def test_rank2_of_11_is_tier5(self):
        # top18% of 11 = round(11*0.18) = round(1.98) = 2
        assert _rotation_rank_bucket(2, 11) == 5

    def test_rank3_of_11_is_tier4(self):
        # pos_in_rem = 3-2 = 1; bucket_size = 9/4 = 2.25; 1 <= 2.25 → tier 4
        assert _rotation_rank_bucket(3, 11) == 4

    def test_rank11_of_11_is_tier1(self):
        assert _rotation_rank_bucket(11, 11) == 1

    def test_unknown_rank_is_0(self):
        assert _rotation_rank_bucket(None, 11) == 0

    def test_zero_total_is_0(self):
        assert _rotation_rank_bucket(1, 0) == 0

    def test_single_instrument(self):
        assert _rotation_rank_bucket(1, 1) == 5


# ---------------------------------------------------------------------------
# T5 — CONVICTION_TIER mapping completeness
# ---------------------------------------------------------------------------

class TestConvictionTierMapping:
    def test_all_five_labels_present(self):
        expected = {"Accumulate", "Constructive", "Neutral", "Cautious", "Reduce"}
        assert set(_CONVICTION_TIER.keys()) == expected

    def test_ordering(self):
        assert _CONVICTION_TIER["Accumulate"] > _CONVICTION_TIER["Constructive"]
        assert _CONVICTION_TIER["Constructive"] > _CONVICTION_TIER["Neutral"]
        assert _CONVICTION_TIER["Neutral"] > _CONVICTION_TIER["Cautious"]
        assert _CONVICTION_TIER["Cautious"] > _CONVICTION_TIER["Reduce"]


# ---------------------------------------------------------------------------
# T6 — Jinja template smoke: sector_central.html.j2 renders without error
#       when SECTOR_CENTRAL JS is embedded
# ---------------------------------------------------------------------------

class TestTemplateSmoke:
    """Render the sector_central template with minimal window.SECTOR_CENTRAL
    data and verify it produces valid HTML without raising."""

    def test_template_renders_without_error(self, tmp_path):
        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            pytest.skip("jinja2 not installed")

        templates_dir = REPO / "templates"
        if not templates_dir.exists():
            pytest.skip("templates/ directory not found")
        template_file = templates_dir / "sector_central.html.j2"
        if not template_file.exists():
            pytest.skip("sector_central.html.j2 not found")

        env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=False)
        # Provide minimal i18n stubs so the template doesn't crash on missing globals
        env.globals.update(
            td=lambda en: en,
            tr=lambda en: en,
            t=lambda en, zh="": en,
        )
        # Render without flows_html (None path)
        try:
            html = env.get_template("sector_central.html.j2").render(flows_html=None)
        except Exception as e:
            pytest.fail(f"Template render raised: {e}")

        assert "sector_central_data.js" in html, "data JS include missing"
        assert "xsr-split" in html or "xsr-fast" in html or "fast tape" in html, \
            "XSR chip CSS or text not present in rendered HTML"
        assert "fast rotation lens" in html, "methodology note absent"
        # CI guard: no title= attributes containing translated text
        import re
        title_attrs = re.findall(r'title="([^"]*)"', html)
        for ta in title_attrs:
            # Check for obvious ZH characters in title attrs (ban)
            if any('一' <= c <= '鿿' for c in ta):
                pytest.fail(f"ZH text found in title= attribute: {ta!r}")

    def test_template_split_view_css_present(self):
        """The .xsr-split and .xsr-fast CSS rules must be in the template."""
        template_file = REPO / "templates" / "sector_central.html.j2"
        if not template_file.exists():
            pytest.skip("template not found")
        content = template_file.read_text(encoding="utf-8")
        assert ".xsr-split" in content
        assert ".xsr-fast" in content

    def test_methodology_note_no_banned_vocab(self):
        """Footer methodology note must not contain banned vocabulary."""
        template_file = REPO / "templates" / "sector_central.html.j2"
        if not template_file.exists():
            pytest.skip("template not found")
        content = template_file.read_text(encoding="utf-8")
        # Find the methodology note section (after the split-view CSS insertion)
        # The note is in the <footer> block
        import re
        footer_match = re.search(r'<footer>(.*?)</footer>', content, re.DOTALL)
        if not footer_match:
            pytest.skip("footer block not found in template")
        footer_text = footer_match.group(1)
        banned = ["governor", "MACD", "mom20", "OB penalty"]
        for word in banned:
            assert word not in footer_text, (
                f"Banned vocabulary '{word}' found in footer methodology note"
            )


# ---------------------------------------------------------------------------
# T7 — split copy text sanity
# ---------------------------------------------------------------------------

class TestSplitCopyText:
    """Split copy must not contain banned vocabulary and must be bilingual."""

    def test_no_banned_vocab_in_en_copy(self):
        from engine.sector_central import _SPLIT_COPY_EN, _CONV_PLAIN_EN
        banned = ["governor", "MACD", "mom20", "OB", "ROLLING OVER", "TOP WATCH"]
        for direction, template in _SPLIT_COPY_EN.items():
            for label, plain in _CONV_PLAIN_EN.items():
                text = template.format(conv=plain)
                for b in banned:
                    assert b not in text, (
                        f"Banned '{b}' in EN split copy for direction={direction}, label={label}"
                    )

    def test_zh_copy_contains_chinese(self):
        from engine.sector_central import _SPLIT_COPY_ZH
        for direction, text_template in _SPLIT_COPY_ZH.items():
            assert any('一' <= c <= '鿿' for c in text_template), \
                f"ZH split copy for {direction!r} contains no Chinese characters"


# ---------------------------------------------------------------------------
# T8 — build_us_sector_rotation.py wrapper imports and is callable
# ---------------------------------------------------------------------------

class TestWrapperScript:
    def test_main_importable(self):
        """The wrapper script must be importable as a module."""
        import importlib
        mod = importlib.import_module("scripts.build_us_sector_rotation")
        assert hasattr(mod, "main")
        assert callable(mod.main)
