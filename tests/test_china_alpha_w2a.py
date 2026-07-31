"""tests/test_china_alpha_w2a.py — W2-A: narrative heat + name tag unit tests.

Tests are synthetic-fixture-only except for the live-verify block at the bottom,
which runs the real pipeline over the committed artifacts and checks that the
exemplar tickers stay covered and that live records are well-formed.

Nearest sibling: tests/test_china_alpha_w1b.py (same fixture idiom).

Live-block repair, 2026-07-26: this file was never wired into CI, so three
live-exemplar tests sat red unnoticed.  They asserted market outcomes
(`ths_synbio rel20 > 0` — "was +17.8pp at design time") against
data/china_search/closes.parquet, which is committed and advanced nightly.
Those assertions were deleted, not fixed: they encode market weather, not a code
contract.  See TestLiveExemplars' docstring for what the block may assert now.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Synthetic-fixture helpers ────────────────────────────────────────────────

def _bdate(n: int, start: str = "2022-01-03") -> pd.DatetimeIndex:
    return pd.bdate_range(start=start, periods=n)


def _flat_closes(tickers: list[str], n: int = 120,
                 start: str = "2022-01-03",
                 multiplier: dict[str, float] | None = None) -> pd.DataFrame:
    """Build a synthetic wide closes panel.

    multiplier: per-ticker daily-return multiplier over the last 20 bars
    (allows us to control rel20 precisely).
    """
    mult = multiplier or {}
    idx = _bdate(n, start)
    data: dict[str, list[float]] = {}
    for t in tickers:
        base = 100.0
        prices = []
        for i in range(n):
            prices.append(base)
            if i >= n - 20 and t in mult:
                base *= mult[t]
        data[t] = prices
    return pd.DataFrame(data, index=idx)


def _bench_series(closes: pd.DataFrame, gain_20d: float = 0.0) -> pd.Series:
    """Flat benchmark with optional 20d gain (fraction)."""
    n = len(closes)
    vals = [100.0] * n
    for i in range(n - 20, n):
        vals[i] = 100.0 * (1.0 + gain_20d * (i - (n - 21)) / 20.0)
    vals[-1] = 100.0 * (1.0 + gain_20d)
    return pd.Series(vals, index=closes.index, dtype=float)


def _membership(basket_id: str, tickers: list[str], name: str = "TestBasket",
                name_zh: str = "测试") -> dict:
    """Build a minimal membership dict for one basket."""
    members = [{"ticker": t, "added": "2022-01-01", "removed": None, "name_zh": t}
               for t in tickers]
    return {basket_id: {"name": name, "name_zh": name_zh,
                        "category": "Test", "category_zh": "测试",
                        "members": members}}


def _minimal_radar(basket_id: str, tickers: list[str],
                   rank: int = 1,
                   honesty: str = "validated") -> dict:
    """Build a minimal radar return dict with one basket containing given tickers."""
    top_members = [{"ticker": t, "name_zh": t, "ret_63d": 10.0} for t in tickers]
    return {
        "as_of": "2026-07-03",
        "baskets": [{
            "id":          basket_id,
            "name":        "TestRadarBasket",
            "name_zh":     "测试雷达",
            "category":    "Test",
            "category_zh": "测试",
            "ret_63d":     10.0,
            "rank_63d":    rank,
            "above_200d":  True,
            "state":       {"score": 30, "label": "Recovering"},
            "global_ai":   {"mom_4w_pct": 5.0, "direction": "up",
                            "validated_tag": honesty, "as_of": "2026-07-03"},
            "top_members": top_members,
        }],
        "provenance": {"momentum": "descriptive", "global_ai": "validated"},
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — narrative_heat(): threshold boundary tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNarrativeHeatThresholds:
    """Spec: HOT = rel20 >= +5pp AND breadth >= 60%; WARMING = rel20 >= 0 AND breadth >= 50%."""

    def test_thresholds_are_the_preregistered_values(self):
        """Pin the gate values themselves, as literals.

        Every other threshold test — synthetic boundary cases here, and the
        live census in TestLiveExemplars — imports these constants and grades
        against them, so loosening a constant moves both sides of the
        comparison and nothing goes red.  Verified 2026-07-26: dropping
        HOT_REL20_THRESHOLD 5.0 -> 4.0 left all 1774 china tests green.  These
        are pre-registered gates (CLAUDE.md §Epistemics), so a change here is a
        re-registration and must be a deliberate, reviewed diff — not a silent
        one.
        """
        from engine import china_narrative_tags as cnt
        assert cnt.HOT_REL20_THRESHOLD == 5.0
        assert cnt.HOT_BREADTH_THRESHOLD == 0.60
        assert cnt.WARM_REL20_THRESHOLD == 0.0
        assert cnt.WARM_BREADTH_THRESHOLD == 0.50

    def _run_heat(self, basket_id: str, tickers: list[str],
                  multiplier: dict[str, float],
                  bench_gain: float = 0.0,
                  curated: bool = True) -> dict | None:
        from engine.china_narrative_tags import narrative_heat
        closes = _flat_closes(tickers, multiplier=multiplier)
        bench  = _bench_series(closes, gain_20d=bench_gain)
        mem    = _membership(basket_id, tickers)
        if curated:
            h = narrative_heat(closes, mem, None, bench)
        else:
            h = narrative_heat(closes, None, mem, bench)
        return h.get(basket_id)

    def test_hot_exact_boundary_rel20_5pp_breadth_60pct(self):
        """rel20 == 5pp exactly AND breadth == 60% -> HOT."""
        # 5 tickers; 3 of 5 must be above their 20d MA -> 60% breadth
        # basket raw 20d = bench 20d + 5pp
        # bench gain = 0; basket raw must be ≈ 5%
        # multiplier for winning tickers: compound 1.003 over 20 bars ≈ +6.2% (above MA)
        # losing tickers: flat (below their MA since MA is avg of 100 across 20 bars =100, last=100; barely above; make losers go DOWN)
        tickers = ["A", "B", "C", "D", "E"]
        # 3 winners go up by factor ≈ 1.003/day (6.2% over 20 days)
        # 2 losers go down by factor 0.997/day (-5.9% over 20 days)
        mult = {"A": 1.003, "B": 1.003, "C": 1.003, "D": 0.997, "E": 0.997}
        rec = self._run_heat("b1", tickers, mult, bench_gain=0.00)
        assert rec is not None
        # breadth: exactly 3/5 above 20d MA? The "flat then ramp" construction means
        # the MA < last for the up-movers (last > average) and > last for down-movers.
        # rel20 is EW basket; up 3, down 2: EW raw20 = (3*6.2 + 2*(-5.9))/5 ≈ 1.5pp
        # That would be WARMING, not HOT, because we only have 3/5 up and 2/5 down.
        # Let's instead test a cleaner HOT: all 5 tickers up 6%, bench flat -> rel20=6%, breadth=100%
        mult_hot = {t: 1.003 for t in tickers}
        rec = self._run_heat("b_hot", tickers, mult_hot, bench_gain=0.00)
        assert rec is not None
        assert rec["level"] == "HOT", (
            f"All-up basket with bench flat should be HOT; got level={rec['level']!r}, "
            f"rel20={rec['rel20']}, breadth={rec['breadth']}")

    def test_rel20_exactly_5pp_with_full_breadth_is_hot(self):
        """rel20 >= +5pp AND breadth = 1.0 -> HOT (boundary rel20 inclusive)."""
        from engine.china_narrative_tags import (
            narrative_heat, HOT_REL20_THRESHOLD, HOT_BREADTH_THRESHOLD,
        )
        tickers = ["X", "Y", "Z"]
        # Control: all up ~6.2% (1.003^20), bench flat -> rel20 ≈ +6.2pp, breadth=100%
        mult = {t: 1.003 for t in tickers}
        closes = _flat_closes(tickers, multiplier=mult)
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bx", tickers)
        h = narrative_heat(closes, mem, None, bench)
        rec = h.get("bx")
        assert rec is not None
        assert rec["rel20"] >= HOT_REL20_THRESHOLD
        assert rec["breadth"] >= HOT_BREADTH_THRESHOLD
        assert rec["level"] == "HOT"

    def test_warming_boundary_rel20_zero_breadth_exactly_50pct(self):
        """rel20 == 0pp AND breadth == 50% -> WARMING (not HOT, not None)."""
        from engine.china_narrative_tags import narrative_heat
        # 4 tickers: 2 up exactly to match bench, 2 flat (MA = last, so AT ma20, not above -> not breadth)
        # Easier construction: 4 tickers all perfectly flat, bench flat -> rel20=0, breadth=0 -> None
        # Instead: 2 tickers up slightly (above 20d MA), 2 tickers flat (AT 20d MA, not above).
        # To get exactly breadth=0.5 and rel20>=0:
        # Up ticker: price goes to 101 on last day from base 100; MA for last 20 = (100*19+101)/20=100.05 < 101 ✓
        # Down ticker: price goes to 99; MA = (100*19+99)/20 = 99.95 > 99 -> not above MA ✓
        # EW basket: (101 + 99) / 2 / 100 - 1 = 0 -> rel20=0%; bench flat -> rel20=0pp ✓
        # breadth = 2/4 = 50% ✓ -> WARMING boundary
        from engine.china_narrative_tags import WARM_REL20_THRESHOLD, WARM_BREADTH_THRESHOLD
        tickers = ["U", "V", "W", "X"]
        n = 60
        idx = _bdate(n)
        data = {
            "U": [100.0] * (n - 1) + [101.0],  # slightly above 20d MA
            "V": [100.0] * (n - 1) + [101.0],  # slightly above 20d MA
            "W": [100.0] * (n - 1) + [99.0],   # below 20d MA
            "X": [100.0] * (n - 1) + [99.0],   # below 20d MA
        }
        closes = pd.DataFrame(data, index=idx, dtype=float)
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bwarm", tickers)
        h = narrative_heat(closes, mem, None, bench)
        rec = h.get("bwarm")
        assert rec is not None
        assert abs(rec["rel20"]) < 0.5, f"Expected rel20 ~0, got {rec['rel20']}"
        assert abs(rec["breadth"] - 0.5) < 0.02, f"Expected breadth ~0.5, got {rec['breadth']}"
        assert rec["level"] == "WARMING", (
            f"rel20~0, breadth~50% should be WARMING; got {rec['level']!r}")

    def test_below_threshold_gives_none_level(self):
        """rel20 < 0 and breadth < 50% -> level=None (unqualified)."""
        from engine.china_narrative_tags import narrative_heat
        tickers = ["A", "B", "C"]
        # All down -> rel20 negative, breadth < 60%
        mult = {t: 0.995 for t in tickers}
        rec = self._run_heat("b_none", tickers, mult, bench_gain=0.00)
        assert rec is not None
        assert rec["level"] is None, f"Down basket should give level=None; got {rec['level']!r}"

    def test_level_uses_the_same_precision_as_published_rel20(self):
        """A value displayed as zero must not contradict the inclusive zero gate."""
        tickers = ["A", "B", "C"]
        # Two gentle winners and one offsetting loser produce ~-0.004pp over
        # 20 days with 2/3 breadth: published rel20 rounds to -0.0.
        mult = {"A": 1.001, "B": 1.001, "C": 0.997994}
        rec = self._run_heat("b_rounding", tickers, mult, bench_gain=0.00)
        assert rec is not None
        assert rec["rel20"] == 0.0
        assert rec["breadth"] >= 0.50
        assert rec["level"] == "WARMING"

    def test_hot_rel20_but_low_breadth_gives_warming_or_none(self):
        """rel20 >= 5pp but breadth < 60% -> not HOT."""
        from engine.china_narrative_tags import narrative_heat
        # 5 tickers: only 2 up a lot, 3 flat — EW rel20 could be >= 5pp but breadth=40%
        tickers = ["A", "B", "C", "D", "E"]
        n = 60
        idx = _bdate(n)
        data = {
            "A": [100.0] * (n - 1) + [115.0],   # +15%
            "B": [100.0] * (n - 1) + [115.0],   # +15%
            "C": [100.0] * n,
            "D": [100.0] * n,
            "E": [100.0] * n,
        }
        closes = pd.DataFrame(data, index=idx, dtype=float)
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("b_highrel_lowbreadth", tickers)
        h = narrative_heat(closes, mem, None, bench)
        rec = h.get("b_highrel_lowbreadth")
        assert rec is not None
        # rel20 = (15+15+0+0+0)/5 = 6% -> >= 5pp
        # breadth: A and B are above MA (flat then spike), C/D/E flat (== MA) -> 2/5 = 40%
        # 40% < 60% -> NOT HOT; 40% < 50% -> NOT WARMING either -> None
        assert rec["level"] != "HOT", (
            f"High rel20 but low breadth must not be HOT; got {rec['level']!r}, "
            f"rel20={rec['rel20']}, breadth={rec['breadth']}")

    def test_source_label_curated(self):
        from engine.china_narrative_tags import narrative_heat
        tickers = ["P", "Q", "R"]
        mult = {t: 1.003 for t in tickers}
        closes = _flat_closes(tickers, multiplier=mult)
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bcur", tickers)
        h = narrative_heat(closes, mem, None, bench)
        rec = h.get("bcur")
        assert rec is not None
        assert rec["source"] == "curated"

    def test_source_label_ths(self):
        from engine.china_narrative_tags import narrative_heat
        tickers = ["P", "Q", "R"]
        mult = {t: 1.003 for t in tickers}
        closes = _flat_closes(tickers, multiplier=mult)
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bths", tickers)
        h = narrative_heat(closes, None, mem, bench)
        rec = h.get("bths")
        assert rec is not None
        assert rec["source"] == "THS"

    def test_n_members_n_covered_fields_present(self):
        from engine.china_narrative_tags import narrative_heat
        tickers = ["A", "B", "C", "D"]  # D won't appear in closes
        mult = {"A": 1.002, "B": 1.002, "C": 1.002}
        closes = _flat_closes(["A", "B", "C"], multiplier=mult)  # D absent
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bcover", ["A", "B", "C", "D"])  # D listed in membership
        h = narrative_heat(closes, mem, None, bench)
        rec = h.get("bcover")
        assert rec is not None
        assert rec["n_members"] == 4  # 4 in membership
        assert rec["n_covered"] == 3  # 3 with closes data

    def test_basket_below_min_members_skipped(self):
        """A basket with fewer than 3 covered members must be skipped."""
        from engine.china_narrative_tags import narrative_heat
        closes = _flat_closes(["A", "B"])   # only 2 tickers
        bench  = _bench_series(closes, gain_20d=0.00)
        mem    = _membership("bsmall", ["A", "B"])
        h = narrative_heat(closes, mem, None, bench)
        assert "bsmall" not in h, "Basket with <3 covered members must be skipped"

    def test_degradation_empty_closes_returns_empty_dict(self):
        from engine.china_narrative_tags import narrative_heat
        h = narrative_heat(None, {}, {}, None)
        assert h == {}

    def test_degradation_no_memberships_returns_empty_dict(self):
        from engine.china_narrative_tags import narrative_heat
        closes = _flat_closes(["A", "B", "C"])
        bench  = _bench_series(closes)
        h = narrative_heat(closes, None, None, bench)
        assert h == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — name_tags(): membership join + strongest-theme selection
# ═══════════════════════════════════════════════════════════════════════════════

class TestNameTags:
    """Tests for name_tags() — ticker -> strongest qualifying theme + radar join."""

    def _heat_record(self, basket_id: str, name: str, level: str | None,
                     rel20: float, breadth: float, source: str = "THS") -> dict:
        return {
            "basket_id": basket_id, "name": name, "name_zh": name,
            "level": level, "rel20": rel20, "breadth": breadth,
            "source": source, "n_members": 5, "n_covered": 5,
        }

    def test_single_hot_basket_gives_tag(self):
        from engine.china_narrative_tags import name_tags
        heat = {"b1": self._heat_record("b1", "HotBasket", "HOT", 10.0, 0.75)}
        mem  = _membership("b1", ["T1", "T2"])
        tags = name_tags(heat, None, mem, None)
        assert "T1" in tags
        assert tags["T1"]["level"] == "HOT"
        assert tags["T1"]["basket_id"] == "b1"
        assert tags["T1"]["theme"] == "HotBasket"

    def test_strongest_by_rel20_chosen(self):
        """When a ticker is in two qualifying baskets, the higher rel20 wins."""
        from engine.china_narrative_tags import name_tags
        heat = {
            "b1": self._heat_record("b1", "Basket1", "HOT",     8.0, 0.80),
            "b2": self._heat_record("b2", "Basket2", "WARMING", 3.0, 0.55),
        }
        mem1 = _membership("b1", ["TICK"])
        mem2 = _membership("b2", ["TICK"])
        merged_ths = {**mem1, **mem2}
        tags = name_tags(heat, None, merged_ths, None)
        assert "TICK" in tags
        assert tags["TICK"]["basket_id"] == "b1", (
            "Basket with higher rel20 (b1=8.0 > b2=3.0) must win")

    def test_non_qualifying_basket_not_selected(self):
        """A basket with level=None must not appear as the primary theme tag."""
        from engine.china_narrative_tags import name_tags
        heat = {"b1": self._heat_record("b1", "ColdBasket", None, -2.0, 0.30)}
        mem  = _membership("b1", ["TICK"])
        tags = name_tags(heat, None, mem, None)
        # TICK may still get a tag if in radar, but theme should be None
        if "TICK" in tags:
            assert tags["TICK"]["level"] is None or tags["TICK"]["basket_id"] is None, (
                "Non-qualifying basket must not set theme")

    def test_ticker_in_both_curated_and_ths_correct_source(self):
        """Source label on the winning basket is preserved through the join."""
        from engine.china_narrative_tags import name_tags
        heat = {
            "b_cur": self._heat_record("b_cur", "Curated", "HOT",     12.0, 0.90, source="curated"),
            "b_ths": self._heat_record("b_ths", "THS",     "WARMING",  2.0, 0.60, source="THS"),
        }
        mem_cur = _membership("b_cur", ["TICK"])
        mem_ths = _membership("b_ths", ["TICK"])
        tags = name_tags(heat, mem_cur, mem_ths, None)
        assert "TICK" in tags
        assert tags["TICK"]["source"] == "curated", (
            "Curated basket wins (higher rel20); source must be 'curated'")

    def test_radar_join_attached(self):
        """If ticker appears in radar top_members, radar join is attached."""
        from engine.china_narrative_tags import name_tags
        heat = {}
        mem  = {}
        radar = _minimal_radar("r1", ["TICK_R"], rank=3, honesty="validated")
        tags = name_tags(heat, None, mem, radar)
        assert "TICK_R" in tags
        assert tags["TICK_R"]["radar"] is not None
        assert tags["TICK_R"]["radar"]["basket_id"] == "r1"
        assert tags["TICK_R"]["radar"]["narr_rank"] == 3
        assert tags["TICK_R"]["radar"]["global_ai"]["validated_tag"] == "validated"

    def test_radar_honesty_preserved_verbatim(self):
        """Honesty tags from radar must be passed through unchanged."""
        from engine.china_narrative_tags import name_tags
        for honesty in ("validated", "partial", "2024+-only", "weak"):
            radar = _minimal_radar("r1", ["T"], rank=1, honesty=honesty)
            tags  = name_tags({}, None, {}, radar)
            assert "T" in tags
            assert tags["T"]["radar"]["global_ai"]["validated_tag"] == honesty, (
                f"Honesty tag {honesty!r} must be preserved verbatim")

    def test_ticker_not_in_any_basket_absent(self):
        """A ticker with no basket membership and not in radar must not appear."""
        from engine.china_narrative_tags import name_tags
        heat = {"b1": self._heat_record("b1", "B1", "HOT", 8.0, 0.8)}
        mem  = _membership("b1", ["A", "B"])
        tags = name_tags(heat, None, mem, None)
        assert "C" not in tags, "C is not in any basket; must not appear in tags"

    def test_missing_radar_keys_tolerated(self):
        """Radar dict with missing keys must not crash name_tags (shape tolerance)."""
        from engine.china_narrative_tags import name_tags
        # Radar with missing global_ai and missing rank_63d on one basket
        radar = {
            "as_of": "2026-07-03",
            "baskets": [{
                "id": "b_partial",
                # name, rank_63d, global_ai all missing
                "top_members": [{"ticker": "T1", "name_zh": "T1"}],
            }],
            "provenance": {},
        }
        tags = name_tags({}, None, {}, radar)
        assert "T1" in tags, "Ticker in radar must be tagged even with missing radar fields"
        r = tags["T1"]["radar"]
        assert r is not None
        assert r.get("narr_rank") is None or isinstance(r.get("narr_rank"), (int, float, type(None)))

    def test_empty_radar_does_not_crash(self):
        from engine.china_narrative_tags import name_tags
        tags = name_tags({}, None, {}, {"as_of": "2026-07-03", "baskets": []})
        assert isinstance(tags, dict)

    def test_none_radar_does_not_crash(self):
        from engine.china_narrative_tags import name_tags
        heat = {"b1": self._heat_record("b1", "B", "HOT", 8.0, 0.80)}
        mem  = _membership("b1", ["T"])
        tags = name_tags(heat, None, mem, None)
        assert "T" in tags
        assert tags["T"]["radar"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — ab_tier(): A/B tier assignment
# ═══════════════════════════════════════════════════════════════════════════════

class TestAbTier:
    """Tests for ab_tier() — stage + tag -> A/B/None."""

    def _tag(self, level: str | None = "HOT",
             honesty: str | None = None) -> dict:
        radar: dict | None = None
        if honesty is not None:
            radar = {"basket_id": "r1", "narr_rank": 1,
                     "global_ai": {"validated_tag": honesty}}
        return {"level": level, "radar": radar}

    def test_entry_hot_is_A(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier("ENTRY", self._tag("HOT")) == "A"

    def test_ripening_hot_is_A(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier("RIPENING", self._tag("HOT")) == "A"

    def test_entry_warming_without_radar_is_B(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier("ENTRY", self._tag("WARMING", honesty=None)) == "B"

    def test_entry_no_tag_is_B(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier("ENTRY", None) == "B"

    def test_ran_late_gives_no_tier(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier("RAN_LATE", self._tag("HOT")) is None

    def test_none_stage_gives_no_tier(self):
        from engine.china_narrative_tags import ab_tier
        assert ab_tier(None, self._tag("HOT")) is None

    def test_validated_radar_confirmer_is_A(self):
        from engine.china_narrative_tags import ab_tier
        tag = self._tag(level="WARMING", honesty="validated")
        assert ab_tier("ENTRY", tag) == "A"

    def test_partial_radar_confirmer_is_A(self):
        from engine.china_narrative_tags import ab_tier
        tag = self._tag(level=None, honesty="partial")
        assert ab_tier("ENTRY", tag) == "A"

    def test_weak_radar_confirmer_without_hot_is_B(self):
        from engine.china_narrative_tags import ab_tier
        tag = self._tag(level=None, honesty="weak")
        assert ab_tier("ENTRY", tag) == "B"

    def test_2024plus_only_radar_confirmer_without_hot_is_B(self):
        from engine.china_narrative_tags import ab_tier
        tag = self._tag(level=None, honesty="2024+-only")
        assert ab_tier("ENTRY", tag) == "B"


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — Degradation guards
# ═══════════════════════════════════════════════════════════════════════════════

class TestDegradation:
    """Missing artifacts must return empty dicts without crashing."""

    def test_narrative_heat_none_closes(self):
        from engine.china_narrative_tags import narrative_heat
        h = narrative_heat(None, {"b": {}}, {"b2": {}}, None)
        assert h == {}

    def test_narrative_heat_empty_closes(self):
        from engine.china_narrative_tags import narrative_heat
        h = narrative_heat(pd.DataFrame(), {"b": {}}, {}, None)
        assert h == {}

    def test_name_tags_all_none(self):
        from engine.china_narrative_tags import name_tags
        t = name_tags({}, None, None, None)
        assert t == {}

    def test_name_tags_empty_heat_no_memberships(self):
        from engine.china_narrative_tags import name_tags
        t = name_tags({}, {}, {}, None)
        assert t == {}


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — Live verification (requires local parquet files)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not (ROOT / "data" / "china_search" / "closes.parquet").exists(),
    reason="requires local closes.parquet",
)
class TestLiveExemplars:
    """End-to-end pipeline health on the real artifacts — NOT a market oracle.

    What this block may assert (durable, market-independent):
      · the exemplar tickers stay covered — present in name_tags at all;
      · the basket the program was designed around stays computable in heat,
        with its members actually covered by closes.parquet;
      · every live record is well-formed (keys, types, breadth in [0,1]);
      · level agrees with the pre-registered thresholds on real data.

    What it may NOT assert: that any particular basket is *hot today*.  The
    original block pinned `rel20 > 0` on ths_synbio ("was +17.8pp at design
    time").  rel20 is a 20-day return relative to CSI300 — it changes sign
    routinely, and on 2026-07-25 ths_synbio was -11.22pp with 0.0 breadth,
    which is a legitimate cold basket, not a defect.  Only 21 of 259 live
    baskets qualify at all on a typical day, so "this basket is HOT" is a
    coin-flip on market weather dressed as a code contract; data/china_search/
    closes.parquet is committed and advanced nightly, so such an assertion
    turns CI red on a market move.  A cold basket is a null, and a null never
    fails a build (CLAUDE.md §Epistemics).

    Threshold *logic* is unit-tested on synthetic fixtures in
    TestNarrativeHeatThresholds above; this block only checks that the same
    rule holds when the real pipeline runs.
    """

    def _build_live(self):
        """Build live heat + tags from local data files."""
        from engine.china_narrative_tags import build_narrative_tags
        return build_narrative_tags()

    @pytest.mark.parametrize("ticker", ["300725.SZ", "688306.SS"])
    def test_exemplar_ticker_stays_covered(self, ticker):
        """The exemplar tickers must still resolve an entry in name_tags.

        A ticker is emitted when it has EITHER a qualifying theme OR a radar
        join, so this survives a cold tape — it goes red when coverage is lost
        (dropped from the basket membership files, or missing from
        closes.parquet), which is the real failure mode.
        """
        result = self._build_live()
        tag = result["tags"].get(ticker)
        assert tag is not None, (
            f"{ticker} must appear in name_tags — lost basket membership or "
            f"closes.parquet coverage")
        assert (tag.get("theme") is not None) or (tag.get("radar") is not None), (
            f"{ticker} tag carries neither a theme nor a radar join: {tag!r}")
        # Shape is fixed even when every field is a null (cold basket).
        for key in ("theme", "theme_zh", "basket_id", "level", "rel20",
                    "breadth", "source", "n_members", "n_covered", "radar"):
            assert key in tag, f"{ticker} tag missing key {key!r}"
        if tag.get("level") is not None:
            assert tag["level"] in ("HOT", "WARMING")
            assert isinstance(tag["rel20"], float)
            assert 0.0 <= tag["breadth"] <= 1.0

    def test_live_heat_levels_match_preregistered_thresholds(self):
        """Every live heat record's level must follow the pre-registered gate.

        The durable replacement for the old `rel20 > 0` assertion: it holds in
        any market state, and it is a census over all baskets rather than one
        cherry-picked name, so a silent threshold or comparison drift on real
        data cannot hide behind a basket that happens to be hot.
        """
        from engine.china_narrative_tags import (
            HOT_BREADTH_THRESHOLD, HOT_REL20_THRESHOLD,
            WARM_BREADTH_THRESHOLD, WARM_REL20_THRESHOLD,
        )
        heat = self._build_live()["heat"]
        assert heat, "live heat is empty — the narrative pipeline produced nothing"

        for bid, rec in heat.items():
            rel20, breadth, level = rec["rel20"], rec["breadth"], rec["level"]
            assert isinstance(rel20, float) and np.isfinite(rel20), (
                f"{bid}: rel20 must be a finite float, got {rel20!r}")
            assert 0.0 <= breadth <= 1.0, f"{bid}: breadth out of range: {breadth}"
            assert rec["n_covered"] <= rec["n_members"], (
                f"{bid}: n_covered {rec['n_covered']} > n_members {rec['n_members']}")

            if rel20 >= HOT_REL20_THRESHOLD and breadth >= HOT_BREADTH_THRESHOLD:
                expected = "HOT"
            elif rel20 >= WARM_REL20_THRESHOLD and breadth >= WARM_BREADTH_THRESHOLD:
                expected = "WARMING"
            else:
                expected = None
            assert level == expected, (
                f"{bid}: rel20={rel20} breadth={breadth} should grade {expected!r}, "
                f"got {level!r}")

        levels = {lv: sum(1 for r in heat.values() if r["level"] == lv)
                  for lv in ("HOT", "WARMING", None)}
        print(f"\n[LIVE] heat census: {len(heat)} baskets — "
              f"HOT={levels['HOT']} WARMING={levels['WARMING']} "
              f"unqualified={levels[None]}")

    def test_live_print_exemplar_values(self, capsys):
        """Print live values for both exemplars to the report."""
        result = self._build_live()
        tags   = result["tags"]

        for ticker in ("300725.SZ", "688306.SS"):
            tag = tags.get(ticker) or {}
            print(
                f"[LIVE] {ticker}: basket={tag.get('basket_id')!r} "
                f"name={tag.get('theme')!r} level={tag.get('level')!r} "
                f"rel20={tag.get('rel20')} breadth={tag.get('breadth')} "
                f"source={tag.get('source')!r}"
            )
        print(f"[LIVE] n_baskets={result['n_baskets']} n_tagged={result['n_tagged']} as_of={result['as_of']}")

    def test_heat_dict_has_synbio_basket(self):
        """ths_synbio must stay computable in heat, with its members covered.

        The presence + coverage half of the original test — a real contract:
        it goes red if the basket loses its membership file or its members drop
        out of closes.parquet.  The `rel20 > 0` half was deleted (see the class
        docstring): whether Synthetic Biology is outperforming today is market
        weather, and it was -11.22pp when this suite was repaired.
        """
        result = self._build_live()
        heat = result["heat"]
        assert "ths_synbio" in heat, (
            "ths_synbio (Synthetic Biology) must appear in heat — "
            "active members must resolve in closes.parquet")
        rec = heat["ths_synbio"]
        assert rec["source"] == "THS"
        assert rec["n_members"] > 0, "ths_synbio has no members"
        assert rec["n_covered"] == rec["n_members"], (
            f"ths_synbio coverage gap: {rec['n_covered']}/{rec['n_members']} "
            f"members found in closes.parquet")
        print(f"\n[LIVE] ths_synbio: rel20={rec['rel20']}pp, "
              f"breadth={rec['breadth']}, level={rec['level']!r}, "
              f"covered={rec['n_covered']}/{rec['n_members']}")


if __name__ == "__main__":
    import pytest as _pt
    raise SystemExit(_pt.main([__file__, "-v"]))
