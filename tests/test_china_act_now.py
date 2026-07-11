"""tests/test_china_act_now.py — Pure-assembler tests for engine/china_act_now.py (W8-R3).

Tests:
  1. Lane mapping per urgency/reco vocab
  2. Baijiu dual-read fixture (reco=avoid + Trough/osc>0 => BOTH lanes with tape chip)
  3. Null-safety: no theme artifact; no forward_log
  4. No BUY-family words in bottoming lane strings
  5. Ordering determinism within lanes
  6. Dual-read (FT-R1): reduce row gets dual_chip set; both lanes retain the row
  7. Sector routing: urgency vocab matches cycles.py literals
  8. Empty inputs yield empty lanes with no crash
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.china_act_now import assemble_act_now  # noqa: E402

# ─────────────────────────────────────── helpers ──────────────────────────────

def _sector(ticker: str, urgency: str, tag: str = "", name: str | None = None,
            dir_: str = "up") -> dict:
    """Minimal sector card mirroring build_china._sector_cards() shape."""
    return {
        "ticker": ticker,
        "name": name or ticker,
        "label": "TEST",
        "state": "TEST",
        "dir": dir_,
        "entry": {"urgency": urgency, "tag": tag, "days_hi": None},
    }


def _theme_intel(buy: list, pullback: list, reduce: list) -> dict:
    """Minimal theme_intel dict."""
    return {
        "as_of": "2026-07-08",
        "themes": [],
        "act_now": {
            "buy": buy,
            "add_on_pullback": pullback,
            "reduce": reduce,
        },
    }


def _theme_item(id_: str, name: str, name_zh: str, score: int, reco: str,
                reco_en: str, reco_zh: str) -> dict:
    return {
        "id": id_, "name": name, "name_zh": name_zh,
        "score": score,
        "action": reco, "action_en": reco_en, "action_zh": reco_zh,
        "label": "dominant", "entry_quality": 1.0, "clean_entry": True,
        "reasons": [f"20d +10.0% vs CSI 300"],
    }


def _cycle_row(id_: str, name: str, kind: str, phase: str,
               osc_slope: float, pos: float = 0.3,
               rs_63d: float = -10.0, rs_rank: int = 15) -> dict:
    return {
        "date": "2026-07-08",
        "id": id_,
        "kind": kind,
        "name": name,
        "phase": phase,
        "osc_slope": osc_slope,
        "pos": pos,
        "rs_63d": rs_63d,
        "rs_rank": rs_rank,
        "signal": None,
        "above200d": False,
    }


# ─────────────────────────────────────── 1. lane mapping ─────────────────────

class TestLaneMapping:
    """Sector urgency vocab routes to the correct lane."""

    def test_now_sector_to_buy_now(self):
        s = [_sector("A", "now", "BUY NOW")]
        r = assemble_act_now(s, None, None)
        assert [x["id"] for x in r["lanes"]["buy_now"]] == ["A"]
        assert r["lanes"]["wait_pullback"] == []
        assert r["lanes"]["reduce_avoid"] == []

    def test_imminent_sector_to_buy_now(self):
        s = [_sector("B", "imminent")]
        r = assemble_act_now(s, None, None)
        assert "B" in [x["id"] for x in r["lanes"]["buy_now"]]

    def test_soon_sector_to_wait_pullback(self):
        # 'soon' means "cycle low due in ~N days — watch, don't front-run".
        # Design W8-R3: Buy Now = clean-entry (now/imminent only); soon → wait lane.
        s = [_sector("C", "soon", "WATCH")]
        r = assemble_act_now(s, None, None)
        assert "C" in [x["id"] for x in r["lanes"]["wait_pullback"]]
        assert "C" not in [x["id"] for x in r["lanes"]["buy_now"]]

    def test_caution_take_profits_to_reduce(self):
        # TAKE PROFITS has urgency='caution' in cycles.py (TOP WATCH state).
        # It must land in reduce_avoid, NOT wait_pullback.
        s = [_sector("TP", "caution", "TAKE PROFITS")]
        r = assemble_act_now(s, None, None)
        assert "TP" in [x["id"] for x in r["lanes"]["reduce_avoid"]], \
            "caution+TAKE PROFITS must route to reduce_avoid"
        assert "TP" not in [x["id"] for x in r["lanes"]["wait_pullback"]]

    def test_later_sector_to_wait_pullback(self):
        # 'later' (mid-cycle dip, not yet the cycle low) → wait_pullback
        s = [_sector("L", "later", "WAIT")]
        r = assemble_act_now(s, None, None)
        assert "L" in [x["id"] for x in r["lanes"]["wait_pullback"]]
        assert "L" not in [x["id"] for x in r["lanes"]["buy_now"]]
        assert "L" not in [x["id"] for x in r["lanes"]["reduce_avoid"]]

    def test_caution_dont_chase_to_wait_pullback(self):
        s = [_sector("D", "caution", "DON'T CHASE")]
        r = assemble_act_now(s, None, None)
        assert "D" in [x["id"] for x in r["lanes"]["wait_pullback"]]
        assert "D" not in [x["id"] for x in r["lanes"]["reduce_avoid"]]

    def test_hold_sector_to_wait_pullback(self):
        s = [_sector("E", "hold", "HOLD")]
        r = assemble_act_now(s, None, None)
        assert "E" in [x["id"] for x in r["lanes"]["wait_pullback"]]

    def test_caution_unconfirmed_to_reduce(self):
        # em-dash literal must match — same as cycles.py
        s = [_sector("F", "caution", "UNCONFIRMED — HIGH RISK")]
        r = assemble_act_now(s, None, None)
        assert "F" in [x["id"] for x in r["lanes"]["reduce_avoid"]]
        assert "F" not in [x["id"] for x in r["lanes"]["wait_pullback"]]

    def test_exit_sector_to_reduce(self):
        s = [_sector("G", "exit", "TAKE PROFITS")]
        r = assemble_act_now(s, None, None)
        assert "G" in [x["id"] for x in r["lanes"]["reduce_avoid"]]

    def test_avoid_sector_to_reduce(self):
        s = [_sector("H", "avoid", "AVOID")]
        r = assemble_act_now(s, None, None)
        assert "H" in [x["id"] for x in r["lanes"]["reduce_avoid"]]

    def test_sector_kind_chip(self):
        s = [_sector("X", "now")]
        r = assemble_act_now(s, None, None)
        assert r["lanes"]["buy_now"][0]["kind"] == "SECTOR"


class TestThemeLaneMapping:
    """Theme act_now items route to the correct lane."""

    def _theme(self, score=60, reco="accumulate"):
        return _theme_item("t1", "Semis", "半导体", score, reco, "ACCUMULATE", "加仓")

    def test_buy_theme_to_buy_now(self):
        ti = _theme_intel(buy=[self._theme(69)], pullback=[], reduce=[])
        r = assemble_act_now([], ti, None)
        assert len(r["lanes"]["buy_now"]) == 1
        assert r["lanes"]["buy_now"][0]["kind"] == "THEME"
        assert r["lanes"]["buy_now"][0]["score"] == 69

    def test_pullback_theme_to_wait_pullback(self):
        ti = _theme_intel(buy=[], pullback=[self._theme(60)], reduce=[])
        r = assemble_act_now([], ti, None)
        assert len(r["lanes"]["wait_pullback"]) == 1

    def test_reduce_theme_to_reduce_avoid(self):
        ti = _theme_intel(buy=[], pullback=[],
                          reduce=[_theme_item("t2","Solar","光伏",25,"avoid","AVOID","回避")])
        r = assemble_act_now([], ti, None)
        assert len(r["lanes"]["reduce_avoid"]) == 1

    def test_buy_sorted_score_desc(self):
        items = [
            _theme_item("a","A","A",40,"accumulate","ACCUM","加仓"),
            _theme_item("b","B","B",70,"accumulate","ACCUM","加仓"),
            _theme_item("c","C","C",55,"accumulate","ACCUM","加仓"),
        ]
        ti = _theme_intel(buy=items, pullback=[], reduce=[])
        r = assemble_act_now([], ti, None)
        scores = [x["score"] for x in r["lanes"]["buy_now"]]
        assert scores == sorted(scores, reverse=True), "buy_now must be score-desc"

    def test_reduce_sorted_score_asc(self):
        items = [
            _theme_item("a","A","A",35,"avoid","AVOID","回避"),
            _theme_item("b","B","B",20,"avoid","AVOID","回避"),
            _theme_item("c","C","C",27,"avoid","AVOID","回避"),
        ]
        ti = _theme_intel(buy=[], pullback=[], reduce=items)
        r = assemble_act_now([], ti, None)
        scores = [x["score"] for x in r["lanes"]["reduce_avoid"]]
        assert scores == sorted(scores), "reduce_avoid must be score-asc"


# ──────────────────────────────── 2. baijiu dual-read fixture ─────────────────

class TestBaijuiDualRead:
    """FT-R1: cn_baijiu in reduce AND bottoming_watch must appear in BOTH."""

    def _setup(self):
        # cn_baijiu in reduce (reco=avoid/trim)
        baijiu_reduce = _theme_item(
            "cn_baijiu", "Baijiu / Liquor", "白酒/白酒", 31,
            "avoid", "AVOID", "回避",
        )
        ti = _theme_intel(buy=[], pullback=[], reduce=[baijiu_reduce])
        # cn_baijiu in forward_log: Trough, osc_slope=+0.1 (R7 evidence)
        cycle = [_cycle_row("b-cn_baijiu", "Baijiu / Liquor", "basket",
                             "Trough", osc_slope=0.1, pos=0.3, rs_63d=-24.1)]
        return ti, cycle

    def test_baijiu_in_reduce_lane(self):
        ti, cycle = self._setup()
        r = assemble_act_now([], ti, cycle)
        ids_reduce = [x["id"] for x in r["lanes"]["reduce_avoid"]]
        assert "cn_baijiu" in ids_reduce

    def test_baijiu_in_bottoming_lane(self):
        ti, cycle = self._setup()
        r = assemble_act_now([], ti, cycle)
        ids_bot = [x["id"] for x in r["lanes"]["bottoming_watch"]]
        assert "b-cn_baijiu" in ids_bot

    def test_baijiu_dual_read_with_prefix_mismatch(self):
        """FT-R1: theme reduce id='cn_baijiu' and basket cycle id='b-cn_baijiu' must trigger dual_read.
        This is the real live scenario: forward_log basket rows use 'b-' prefix, theme ids do not.
        The assembler must strip 'b-' to normalize before intersection."""
        ti, cycle = self._setup()
        r = assemble_act_now([], ti, cycle)
        reduce_rows = {x["id"]: x for x in r["lanes"]["reduce_avoid"]}
        bot_ids = {x["id"] for x in r["lanes"]["bottoming_watch"]}
        # cn_baijiu (theme) must be in reduce
        assert "cn_baijiu" in reduce_rows, "theme reduce row must be present"
        # b-cn_baijiu (basket cycle) must be in bottoming
        assert "b-cn_baijiu" in bot_ids, "basket bottoming row must be present"
        # dual_read must be True on the reduce row (b- stripped for matching)
        row = reduce_rows["cn_baijiu"]
        assert row["dual_read"] is True, \
            "dual_read must fire when cycle id='b-cn_baijiu' matches theme id='cn_baijiu'"
        assert row["dual_chip_en"] is not None
        assert "洗盘" in (row["dual_chip_zh"] or "")

    def test_dual_read_when_ids_match(self):
        """When a reduce item's id appears in cycle rows, dual_read=True and chip is set."""
        reduce_item = _theme_item(
            "cn_test", "Test Basket", "测试", 28, "avoid", "AVOID", "回避",
        )
        ti = _theme_intel(buy=[], pullback=[], reduce=[reduce_item])
        cycle = [_cycle_row("cn_test", "Test Basket", "basket",
                             "Trough", osc_slope=0.5, pos=0.1)]
        r = assemble_act_now([], ti, cycle)
        reduce_rows = {x["id"]: x for x in r["lanes"]["reduce_avoid"]}
        bot_ids = {x["id"] for x in r["lanes"]["bottoming_watch"]}
        assert "cn_test" in reduce_rows, "reduce must contain cn_test"
        assert "cn_test" in bot_ids, "bottoming must contain cn_test"
        row = reduce_rows["cn_test"]
        assert row["dual_read"] is True
        assert row["dual_chip_en"] is not None
        assert row["dual_chip_zh"] is not None
        assert "洗盘" in row["dual_chip_zh"]

    def test_dual_read_not_merged(self):
        """The rows remain in BOTH lanes — never removed from either."""
        reduce_item = _theme_item(
            "cn_test", "Test Basket", "测试", 28, "avoid", "AVOID", "回避",
        )
        ti = _theme_intel(buy=[], pullback=[], reduce=[reduce_item])
        cycle = [_cycle_row("cn_test", "Test Basket", "basket",
                             "Trough", osc_slope=0.5, pos=0.1)]
        r = assemble_act_now([], ti, cycle)
        assert any(x["id"] == "cn_test" for x in r["lanes"]["reduce_avoid"])
        assert any(x["id"] == "cn_test" for x in r["lanes"]["bottoming_watch"])


# ─────────────────────────────── 3. null safety ───────────────────────────────

class TestNullSafety:
    def test_no_theme_intel(self):
        """None theme_intel → themes omitted + note + no crash."""
        r = assemble_act_now([], None, None)
        assert r["lanes"]["buy_now"] == []
        assert r["lanes"]["wait_pullback"] == []
        assert r["lanes"]["reduce_avoid"] == []
        assert any("theme" in n for n in r["notes"])

    def test_no_forward_log(self):
        """None cycle_rows → bottoming lane empty + note."""
        r = assemble_act_now([], None, None)
        assert r["lanes"]["bottoming_watch"] == []
        assert any("forward_log" in n for n in r["notes"])

    def test_empty_forward_log(self):
        """Empty list cycle_rows → bottoming empty, no note."""
        r = assemble_act_now([], None, [])
        assert r["lanes"]["bottoming_watch"] == []

    def test_no_crash_empty_sectors(self):
        r = assemble_act_now([], None, None)
        assert "lanes" in r

    def test_cycle_row_missing_osc_slope(self):
        """Rows with missing osc_slope are skipped (null-safe)."""
        rows = [{"id": "x", "kind": "sector", "name": "X", "phase": "Trough",
                 "osc_slope": None, "pos": 0.0, "rs_63d": 0.0, "rs_rank": 1}]
        r = assemble_act_now([], None, rows)
        assert r["lanes"]["bottoming_watch"] == []

    def test_cycle_row_non_trough_skipped(self):
        """Rows where phase != Trough are skipped."""
        rows = [_cycle_row("y", "Y", "sector", "Peak", osc_slope=5.0)]
        r = assemble_act_now([], None, rows)
        assert r["lanes"]["bottoming_watch"] == []

    def test_cycle_row_negative_slope_skipped(self):
        """Rows where osc_slope <= 0 are skipped (not turning)."""
        rows = [_cycle_row("z", "Z", "sector", "Trough", osc_slope=-1.0)]
        r = assemble_act_now([], None, rows)
        assert r["lanes"]["bottoming_watch"] == []


# ─────────────────── 4. no BUY-family words in bottoming lane ─────────────────

_BUY_RE = re.compile(r"\b(buy|entry|accumulate|enter)\b", re.IGNORECASE)

class TestBottomingLaneCopyLaw:
    """F1 / W8-R3 copy law: bottoming lane row fields must not contain buy-family words."""

    def _all_strings(self, row: dict) -> list[str]:
        """Return all string fields of a bottoming row."""
        fields = ["name", "tag", "reco", "reco_en", "reco_zh",
                  "dual_chip_en", "dual_chip_zh"]
        return [str(row.get(f) or "") for f in fields]

    def test_basket_row_no_buy_words(self):
        rows = [_cycle_row("b-test", "Test Basket", "basket", "Trough", osc_slope=2.0)]
        r = assemble_act_now([], None, rows)
        for row in r["lanes"]["bottoming_watch"]:
            for s in self._all_strings(row):
                assert not _BUY_RE.search(s), \
                    f"BUY-family word found in bottoming row field: {s!r}"

    def test_sector_row_no_buy_words(self):
        rows = [_cycle_row("801010", "Agriculture", "sector", "Trough", osc_slope=3.9)]
        r = assemble_act_now([], None, rows)
        for row in r["lanes"]["bottoming_watch"]:
            for s in self._all_strings(row):
                assert not _BUY_RE.search(s), \
                    f"BUY-family word found in bottoming row field: {s!r}"

    def test_mixed_rows_no_buy_words(self):
        rows = [
            _cycle_row("b-a", "Alpha Basket", "basket", "Trough", osc_slope=1.0),
            _cycle_row("801150", "Pharma", "sector", "Trough", osc_slope=8.3),
        ]
        r = assemble_act_now([], None, rows)
        for row in r["lanes"]["bottoming_watch"]:
            for s in self._all_strings(row):
                assert not _BUY_RE.search(s), \
                    f"BUY-family word found in bottoming row: {s!r}"


# ─────────────────────────────── 5. ordering determinism ─────────────────────

class TestOrdering:
    def test_buy_now_themes_before_sectors(self):
        """Themes appear before sectors in buy_now (themes sorted first, then sectors)."""
        ti = _theme_intel(
            buy=[_theme_item("t1", "Pharma", "医药", 69, "accumulate", "ACCUM", "加仓")],
            pullback=[], reduce=[],
        )
        sectors = [_sector("SEC1", "now")]
        r = assemble_act_now(sectors, ti, None)
        kinds = [x["kind"] for x in r["lanes"]["buy_now"]]
        assert kinds[0] == "THEME", "themes appear before sectors in buy_now"

    def test_bottoming_sorted_osc_desc(self):
        rows = [
            _cycle_row("a", "A", "sector", "Trough", osc_slope=1.0),
            _cycle_row("b", "B", "basket", "Trough", osc_slope=8.6),
            _cycle_row("c", "C", "sector", "Trough", osc_slope=3.5),
        ]
        r = assemble_act_now([], None, rows)
        slopes = [x["osc_slope"] for x in r["lanes"]["bottoming_watch"]]
        assert slopes == sorted(slopes, reverse=True), "bottoming must be osc_slope desc"

    def test_pull_themes_score_desc(self):
        items = [
            _theme_item("a","A","A",40,"accumulate","ACCUM","加仓"),
            _theme_item("b","B","B",74,"accumulate","ACCUM","加仓"),
        ]
        ti = _theme_intel(buy=[], pullback=items, reduce=[])
        r = assemble_act_now([], ti, None)
        scores = [x["score"] for x in r["lanes"]["wait_pullback"]]
        assert scores == sorted(scores, reverse=True)


# ─────────────────────── 6. all lane keys always present ─────────────────────

class TestLaneKeys:
    """All four lane keys are always present, even when empty."""

    def test_all_keys_present_on_empty(self):
        r = assemble_act_now([], None, None)
        assert set(r["lanes"]) == {"buy_now", "wait_pullback", "bottoming_watch", "reduce_avoid"}

    def test_all_keys_present_with_data(self):
        ti = _theme_intel(
            buy=[_theme_item("t1","X","X",60,"accumulate","ACCUM","加仓")],
            pullback=[], reduce=[],
        )
        r = assemble_act_now([_sector("S1","avoid")], ti,
                              [_cycle_row("b1","B1","basket","Trough",osc_slope=1.0)])
        assert set(r["lanes"]) == {"buy_now", "wait_pullback", "bottoming_watch", "reduce_avoid"}


# ──────────────────── 7. bottoming: both kinds accepted ──────────────────────

class TestBottomingKinds:
    def test_sector_kind_classified_sector(self):
        rows = [_cycle_row("801010", "Agriculture", "sector", "Trough", osc_slope=3.9)]
        r = assemble_act_now([], None, rows)
        assert r["lanes"]["bottoming_watch"][0]["kind"] == "SECTOR"

    def test_basket_kind_classified_basket(self):
        rows = [_cycle_row("b-cn_gold", "Gold Miners", "basket", "Trough", osc_slope=1.2)]
        r = assemble_act_now([], None, rows)
        assert r["lanes"]["bottoming_watch"][0]["kind"] == "BASKET"


# ─────────────────────────────── 8. as_of and notes ──────────────────────────

class TestAsOfAndNotes:
    def test_as_of_from_theme_intel(self):
        ti = _theme_intel(buy=[], pullback=[], reduce=[])
        ti["as_of"] = "2026-07-08"
        r = assemble_act_now([], ti, None)
        assert r["as_of"] == "2026-07-08"

    def test_as_of_none_when_no_theme(self):
        r = assemble_act_now([], None, None)
        assert r["as_of"] is None

    def test_note_on_absent_theme(self):
        r = assemble_act_now([], None, None)
        assert any("theme" in n for n in r["notes"])

    def test_note_on_absent_forward_log(self):
        r = assemble_act_now([], None, None)
        assert any("forward_log" in n for n in r["notes"])


# ─────────────────── 9. W8-R7 rider — basket_turn organ chips ───────────────

class TestBasketTurnOrganRider:
    """Basket-turn organ rider (W8-R7): organ chips added to bottoming_watch rows."""

    def _basket_turn(self, states: dict) -> dict:
        """Minimal basket_turn_cn.json artifact dict."""
        return {
            "schema": "basket_turn_cn.v1",
            "as_of": "2026-07-08",
            "baskets": {
                bid: {"state": state, "evidence": []}
                for bid, state in states.items()
            },
        }

    def test_organ_absent_when_basket_turn_none(self):
        """No organ chips when basket_turn=None."""
        rows = [_cycle_row("b-cn_baijiu", "Baijiu", "basket", "Trough", osc_slope=0.5)]
        r = assemble_act_now([], None, rows, basket_turn=None)
        row = r["lanes"]["bottoming_watch"][0]
        assert row["organ_state"] is None
        assert row["organ_chip_en"] is None

    def test_turning_organ_chip_added(self):
        """TURNING state in basket_turn adds organ chip to the bottoming row."""
        rows = [_cycle_row("b-cn_baijiu", "Baijiu", "basket", "Trough", osc_slope=0.5)]
        bt = self._basket_turn({"cn_baijiu": "TURNING"})
        r = assemble_act_now([], None, rows, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        assert len(bw) >= 1
        baijiu_rows = [row for row in bw if row["id"] == "b-cn_baijiu"]
        assert baijiu_rows, f"b-cn_baijiu not found in bottoming_watch: {[r['id'] for r in bw]}"
        assert baijiu_rows[0]["organ_state"] == "TURNING"
        assert "TURNING" in (baijiu_rows[0]["organ_chip_en"] or "")

    def test_confirmed_organ_chip_added(self):
        """CONFIRMED state in basket_turn adds organ chip."""
        rows = [_cycle_row("cn_semis", "Semis", "basket", "Trough", osc_slope=1.2)]
        bt = self._basket_turn({"cn_semis": "CONFIRMED"})
        r = assemble_act_now([], None, rows, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        semis_rows = [row for row in bw if row["id"] == "cn_semis"]
        assert semis_rows
        assert semis_rows[0]["organ_state"] == "CONFIRMED"
        assert "CONFIRMED" in (semis_rows[0]["organ_chip_en"] or "")

    def test_organ_adds_not_removes(self):
        """Existing forward_log row stays even when organ state is WASHED_OUT (not TURNING)."""
        rows = [_cycle_row("b-cn_baijiu", "Baijiu", "basket", "Trough", osc_slope=0.5)]
        bt = self._basket_turn({"cn_baijiu": "WASHED_OUT"})
        r = assemble_act_now([], None, rows, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        # Row should still be in the lane (not removed)
        assert any(row["id"] == "b-cn_baijiu" for row in bw)
        baijiu_rows = [row for row in bw if row["id"] == "b-cn_baijiu"]
        # WASHED_OUT gets organ_state but NOT the chip_en headline
        assert baijiu_rows[0]["organ_state"] == "WASHED_OUT"

    def test_organ_surfaces_new_turning_basket(self):
        """TURNING basket not in forward_log is surfaced as a new bottoming row."""
        # No cycle_rows (forward_log empty)
        bt = self._basket_turn({"cn_pharma": "TURNING"})
        r = assemble_act_now([], None, [], basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        pharma_rows = [row for row in bw if row["id"] == "cn_pharma"]
        assert pharma_rows, "TURNING basket should be surfaced as new bottoming row"
        assert pharma_rows[0]["organ_chip_en"] is not None
        assert "TURNING" in pharma_rows[0]["organ_chip_en"]

    def test_organ_no_buy_words_in_chip(self):
        """Organ chips must not contain buy/accumulate/enter words (F1 law)."""
        rows = [_cycle_row("b-cn_baijiu", "Baijiu", "basket", "Trough", osc_slope=0.5)]
        bt = self._basket_turn({"cn_baijiu": "TURNING"})
        r = assemble_act_now([], None, rows, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        banned = {"buy", "accumulate", "enter"}
        for row in bw:
            for field in ["organ_chip_en", "organ_chip_zh", "name", "reco", "reco_en"]:
                val = (row.get(field) or "").lower()
                for word in banned:
                    assert word not in val, (
                        f"Banned word {word!r} found in {field}: {val!r}"
                    )

    def test_dual_read_unaffected_by_organ(self):
        """Organ rider does not interfere with existing dual-read logic."""
        ti = _theme_intel(
            buy=[], pullback=[],
            reduce=[_theme_item("cn_baijiu", "Baijiu", "白酒", 30, "reduce", "REDUCE", "减仓")],
        )
        rows = [_cycle_row("b-cn_baijiu", "Baijiu", "basket", "Trough", osc_slope=0.5)]
        bt = self._basket_turn({"cn_baijiu": "TURNING"})
        r = assemble_act_now([], ti, rows, basket_turn=bt)
        # dual_read should still be set on the reduce_avoid row (FT-R1)
        ra = r["lanes"]["reduce_avoid"]
        baijiu_ra = [row for row in ra if row["id"] == "cn_baijiu"]
        assert baijiu_ra
        assert baijiu_ra[0]["dual_read"] is True
        # Both lanes should contain the row
        bw = r["lanes"]["bottoming_watch"]
        assert any(row["id"] in ("b-cn_baijiu", "cn_baijiu") for row in bw)


# ─────────────── 10. organ-rider enrichment (Fix 1/2) ────────────────────────

def _minimal_theme_intel_with_theme(tid: str, name: str, name_zh: str,
                                     score: int, rel20: float) -> dict:
    """theme_intel dict containing one theme in themes[], no act_now items."""
    return {
        "as_of": "2026-07-08",
        "themes": [{
            "id": tid, "name": name, "name_zh": name_zh,
            "score": score, "action": "hold", "action_en": "HOLD", "action_zh": "持有",
            "perf": {"20d": {"rel": rel20}},
        }],
        "act_now": {"buy": [], "add_on_pullback": [], "reduce": []},
    }


def _minimal_ths_baskets(bid: str, name: str, name_zh: str, rel20: float) -> dict:
    """ths_baskets {id: basket} dict for a single THS basket."""
    return {bid: {"id": bid, "name": name, "name_zh": name_zh,
                  "perf": {"20d": {"rel": rel20}}}}


class TestOrganRiderEnrichment:
    """Fix 1: organ-rider rows get name/name_zh/score/reco/rel20 from theme_intel or ths_baskets."""

    def _basket_turn(self, states: dict) -> dict:
        return {
            "schema": "basket_turn_cn.v1",
            "as_of": "2026-07-08",
            "baskets": {bid: {"state": st, "evidence": []} for bid, st in states.items()},
        }

    def test_cn_id_enriched_from_theme_intel(self):
        """organ-rider row with a cn_* id present in theme_intel.themes gets name/name_zh/score/rel20."""
        ti = _minimal_theme_intel_with_theme("cn_pharma", "Pharma", "医药", 72, 0.15)
        bt = self._basket_turn({"cn_pharma": "TURNING"})
        r = assemble_act_now([], ti, [], basket_turn=bt, ths_baskets=None)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "cn_pharma"]
        assert rows, "cn_pharma organ row must be surfaced"
        row = rows[0]
        assert row["name"] == "Pharma", f"expected name='Pharma', got {row['name']!r}"
        assert row["name_zh"] == "医药"
        assert row["score"] == 72
        assert abs((row["rel20"] or 0) - 0.15) < 1e-9
        assert row["organ_chip_en"] is not None

    def test_cn_id_enriched_reco_from_theme_intel(self):
        """organ-rider row gets reco_en/reco_zh when theme_intel has them."""
        ti = _minimal_theme_intel_with_theme("cn_semis", "Semis", "半导体", 65, 0.08)
        bt = self._basket_turn({"cn_semis": "CONFIRMED"})
        r = assemble_act_now([], ti, [], basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "cn_semis"]
        assert rows
        assert rows[0]["reco_en"] == "HOLD"
        assert rows[0]["reco_zh"] == "持有"

    def test_thsc_id_enriched_from_ths_baskets(self):
        """organ-rider row with a thsc* id gets name/name_zh/rel20 from ths_baskets."""
        ths = _minimal_ths_baskets("thsc309128", "Beer", "啤酒", 0.05)
        bt = self._basket_turn({"thsc309128": "TURNING"})
        r = assemble_act_now([], None, [], basket_turn=bt, ths_baskets=ths)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "thsc309128"]
        assert rows, "thsc309128 organ row must be surfaced"
        row = rows[0]
        assert row["name"] == "Beer"
        assert row["name_zh"] == "啤酒"
        assert abs((row["rel20"] or 0) - 0.05) < 1e-9

    def test_ths_id_enriched_from_ths_baskets(self):
        """ths_* ids also resolved from ths_baskets."""
        ths = _minimal_ths_baskets("ths_baijiu", "Baijiu", "白酒", -0.03)
        bt = self._basket_turn({"ths_baijiu": "CONFIRMED"})
        r = assemble_act_now([], None, [], basket_turn=bt, ths_baskets=ths)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "ths_baijiu"]
        assert rows
        assert rows[0]["name"] == "Baijiu"
        assert rows[0]["name_zh"] == "白酒"

    def test_unknown_id_falls_back_to_slug(self):
        """Unknown id falls back to slug as name, no crash."""
        bt = self._basket_turn({"unknown_xyz": "TURNING"})
        r = assemble_act_now([], None, [], basket_turn=bt, ths_baskets=None)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "unknown_xyz"]
        assert rows, "unknown id should still produce a row"
        assert rows[0]["name"] == "unknown_xyz"  # slug fallback

    def test_b_prefix_id_canonical_lookup(self):
        """b-cn_x id resolves name via canonical cn_x key in theme_intel."""
        ti = _minimal_theme_intel_with_theme("cn_gold", "Gold Miners", "黄金", 58, 0.20)
        bt = self._basket_turn({"b-cn_gold": "TURNING"})
        r = assemble_act_now([], ti, [], basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        rows = [row for row in bw if row["id"] == "b-cn_gold"]
        assert rows, "b-cn_gold row must be surfaced"
        assert rows[0]["name"] == "Gold Miners"

    def test_backward_compat_no_ths_baskets_kwarg(self):
        """Calling assemble_act_now without ths_baskets kwarg works (backward-compat)."""
        bt = self._basket_turn({"cn_pharma": "TURNING"})
        # Must not raise
        r = assemble_act_now([], None, [], basket_turn=bt)
        assert "lanes" in r


class TestOrganRiderDedup:
    """Fix 2: dedup hardening — b-/non-b- variants produce at most one row."""

    def _basket_turn(self, states: dict) -> dict:
        return {
            "schema": "basket_turn_cn.v1",
            "as_of": "2026-07-08",
            "baskets": {bid: {"state": st, "evidence": []} for bid, st in states.items()},
        }

    def test_bprefix_and_canonical_produce_one_row(self):
        """organ_state_map has both b-cn_x and cn_x mapped; only one row emitted."""
        # Both keys will be in the map after the canonical registration inside the organ block
        bt = self._basket_turn({"b-cn_x": "TURNING", "cn_x": "TURNING"})
        r = assemble_act_now([], None, [], basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        ids = [row["id"] for row in bw]
        # At most one of b-cn_x or cn_x should appear
        count = ids.count("b-cn_x") + ids.count("cn_x")
        assert count == 1, f"expected 1 row, got {count}: {ids}"

    def test_forward_log_row_and_organ_same_id_no_dup(self):
        """Basket already in forward_log (b-cn_x); organ also fires — no duplicate row."""
        cycle = [_cycle_row("b-cn_x", "X Basket", "basket", "Trough", osc_slope=1.0)]
        bt = self._basket_turn({"cn_x": "TURNING"})  # canonical (non-b) key
        r = assemble_act_now([], None, cycle, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        ids = [row["id"] for row in bw]
        count = ids.count("b-cn_x") + ids.count("cn_x")
        assert count == 1, f"expected 1 row (forward_log), got {count}: {ids}"

    def test_forward_log_row_takes_precedence(self):
        """When forward_log already has the row, the organ does not add a second row."""
        cycle = [_cycle_row("cn_y", "Y Basket", "basket", "Trough", osc_slope=2.5)]
        bt = self._basket_turn({"b-cn_y": "CONFIRMED"})
        r = assemble_act_now([], None, cycle, basket_turn=bt)
        bw = r["lanes"]["bottoming_watch"]
        ids = [row["id"] for row in bw]
        count = ids.count("cn_y") + ids.count("b-cn_y")
        assert count == 1, f"expected 1 row (forward_log), got {count}: {ids}"
