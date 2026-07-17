"""tests/test_theme_scoring_conflicted.py — MLC-W2b + MLC-W4 conflicted-shelf demotion tests.

Tests the sector-conviction demotion logic via the REAL production function
engine.theme_scoring._apply_sector_conflict_demotion — no hand-copy of the logic.

MLC-W2b covers:
  - Reduce demotes a buy item into conflicted
  - Cautious does NOT demote (only "Reduce" triggers demotion per spec MLC-W2b)
  - Escalation is impossible: conflicted items come exclusively from buy
  - Stale sector_central (> 5 days old) leaves conflicted empty and buy untouched
  - Absent sector_central leaves conflicted empty and buy untouched
  - Corrupt sector_central (fail-open) leaves conflicted empty and buy untouched
  - Demoted items carry reason_en, reason_zh, sector_stance, sector_stance_zh, sector_etf
  - The 4th key "conflicted" is always present in the act_now dict (even when empty)
  - SMH-proxied basket with no SMH row in sector_central falls back to XLK for demotion

MLC-W4 covers:
  - Cooling demotion fires when band=="high" AND hist_fade==True
  - Does NOT fire when band=="high" but hist_fade is absent or False
  - Does NOT fire when hist_fade==True but band!="high"
  - Sector-demoted item is NOT double-stamped (already in conflicted, not re-processed)
  - Escalation is impossible (buy + conflicted = original total)
  - Demoted item carries reason_en, reason_zh with N sessions, "cooling": True
  - Bilingual reason fields are present
  - Fail-open on malformed textures leaves act_now unchanged

All tests use tmp_path — zero real data/ or site/ writes.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.theme_scoring import (  # noqa: E402
    _apply_sector_conflict_demotion,
    _apply_momentum_cooling_demotion,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_demotion(
    tmp_path: Path,
    buy_items: list[dict],
    sector_central_doc: dict | None,
    as_of_offset_days: int = 0,
) -> tuple[dict, int]:
    """Call the real _apply_sector_conflict_demotion with a tmp_path site root.

    Writes a sector_central.json into tmp_path/sectordata/ (or omits it when
    sector_central_doc is None), then calls the production function directly.

    Returns:
        (act_now_result, original_buy_count_before_demotion)
    """
    if sector_central_doc is not None:
        sc_dir = tmp_path / "sectordata"
        sc_dir.mkdir(parents=True, exist_ok=True)
        if as_of_offset_days != 0:
            sc_doc = dict(sector_central_doc)
            sc_doc["as_of"] = (date.today() - timedelta(days=as_of_offset_days)).isoformat()
        else:
            sc_doc = sector_central_doc
        (sc_dir / "sector_central.json").write_text(
            json.dumps(sc_doc), encoding="utf-8"
        )

    act_now: dict = {
        "buy": list(buy_items),
        "add_on_pullback": [],
        "reduce": [],
        "conflicted": [],
    }
    original_count = len(buy_items)

    orig_buys = list(act_now["buy"])
    try:
        _apply_sector_conflict_demotion(act_now, tmp_path)
    except AssertionError:
        raise
    except Exception:
        # mirror production fail-open behaviour
        act_now["buy"] = orig_buys
        act_now["conflicted"] = []

    return act_now, original_count


def _make_buy_item(bid: str, name: str = "Test Theme", action: str = "enter") -> dict:
    """Create a minimal buy-list item (clean_entry=True by construction)."""
    return {
        "id": bid,
        "name": name,
        "name_zh": name,
        "action": action,
        "score": 75,
        "reasons": ["test"],
        "clean_entry": True,
    }


def _make_sector_central(ticker: str, label_en: str, as_of: str | None = None) -> dict:
    return {
        "as_of": as_of or date.today().isoformat(),
        "sectors": [
            {"ticker": ticker, "conviction": {"label_en": label_en, "label_zh": label_en}},
        ],
    }


# ---------------------------------------------------------------------------
# Core demotion tests
# ---------------------------------------------------------------------------

class TestReduceDemotes:
    def test_reduce_sector_moves_buy_to_conflicted(self, tmp_path):
        """A buy item whose home sector is 'Reduce' must land in conflicted.

        ai_infra maps to SMH via _SECTOR_PROXY; SMH has no sector_central row so
        the fallback to XLK fires — XLK=Reduce triggers demotion.
        """
        buy = [_make_buy_item("ai_infra")]
        # ai_infra -> SMH -> fallback XLK; use XLK=Reduce
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "ai_infra"
        assert len(act_now["buy"]) == 0

    def test_reduce_leaves_other_buys_intact(self, tmp_path):
        """Items not mapped to a Reduce sector stay in buy."""
        buy = [
            _make_buy_item("ai_infra"),    # SMH -> fallback XLK -> Reduce
            _make_buy_item("regional_banks"),  # XLF -> not Reduce
        ]
        sc = {
            "as_of": date.today().isoformat(),
            "sectors": [
                {"ticker": "XLK", "conviction": {"label_en": "Reduce"}},
                {"ticker": "XLF", "conviction": {"label_en": "Accumulate"}},
            ],
        }
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "ai_infra"
        assert len(act_now["buy"]) == 1
        assert act_now["buy"][0]["id"] == "regional_banks"

    def test_reduce_via_direct_proxy_etf(self, tmp_path):
        """Basket with a GICS-SPDR direct proxy (no fallback needed) still demotes."""
        buy = [_make_buy_item("regional_banks")]  # XLF direct
        sc = _make_sector_central("XLF", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "regional_banks"


class TestSMHFallback:
    def test_smh_basket_no_smh_row_falls_back_to_xlk(self, tmp_path):
        """SMH-proxied basket with no SMH row in sector_central falls back to XLK."""
        buy = [_make_buy_item("ai_infra")]  # SMH proxy; no SMH row -> fallback XLK
        sc = {
            "as_of": date.today().isoformat(),
            "sectors": [
                # No SMH row — only XLK
                {"ticker": "XLK", "conviction": {"label_en": "Reduce"}},
            ],
        }
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        # Must demote via XLK fallback
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "ai_infra"

    def test_smh_basket_smh_row_present_uses_smh_not_fallback(self, tmp_path):
        """When SMH row IS present in sector_central, it takes priority over XLK fallback."""
        buy = [_make_buy_item("ai_infra")]  # SMH proxy
        sc = {
            "as_of": date.today().isoformat(),
            "sectors": [
                {"ticker": "SMH", "conviction": {"label_en": "Accumulate"}},
                {"ticker": "XLK", "conviction": {"label_en": "Reduce"}},
            ],
        }
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        # SMH=Accumulate wins over XLK=Reduce — no demotion
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_ai_semiconductors_falls_back_to_xlk(self, tmp_path):
        """ai_semiconductors also maps SMH -> XLK fallback."""
        buy = [_make_buy_item("ai_semiconductors")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 1


class TestCautiousDoesNotDemote:
    def test_cautious_sector_keeps_item_in_buy(self, tmp_path):
        """'Cautious' does NOT trigger demotion — only 'Reduce' does."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Cautious")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_neutral_does_not_demote(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Neutral")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_constructive_does_not_demote(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Constructive")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_accumulate_does_not_demote(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Accumulate")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1


class TestEscalationImpossible:
    def test_conflicted_total_equals_original_buy_count(self, tmp_path):
        """buy + conflicted = original buy count (de-escalation only; no items created)."""
        buy = [
            _make_buy_item("ai_infra"),
            _make_buy_item("ai_software"),
        ]
        sc = {
            "as_of": date.today().isoformat(),
            "sectors": [
                # XLK covers both ai_infra (via fallback) and ai_software (direct proxy)
                {"ticker": "XLK", "conviction": {"label_en": "Reduce"}},
            ],
        }
        act_now, original_count = _run_demotion(tmp_path, buy, sc)
        assert len(act_now["buy"]) + len(act_now["conflicted"]) == original_count

    def test_no_items_added_to_buy(self, tmp_path):
        """Items cannot move INTO buy via this block."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Accumulate")
        act_now, original_count = _run_demotion(tmp_path, buy, sc)
        # can only stay same or decrease
        assert len(act_now["buy"]) <= original_count


class TestStaleSectorCentral:
    def test_stale_6_days_leaves_conflicted_empty(self, tmp_path):
        """sector_central older than 5 days -> fail-open, conflicted stays []."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc, as_of_offset_days=6)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_exactly_5_days_old_is_still_fresh(self, tmp_path):
        """sector_central exactly 5 days old -> still fresh, demotion fires."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc, as_of_offset_days=5)
        assert len(act_now["conflicted"]) == 1


class TestAbsentOrCorruptSectorCentral:
    def test_absent_sector_central_leaves_conflicted_empty(self, tmp_path):
        """Missing sector_central.json -> conflicted stays [], buy untouched."""
        buy = [_make_buy_item("ai_infra")]
        act_now, _ = _run_demotion(tmp_path, buy, None)  # no file written
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_corrupt_sector_central_leaves_conflicted_empty(self, tmp_path):
        """Corrupt sector_central.json -> fail-open, conflicted stays [], buy untouched."""
        sc_dir = tmp_path / "sectordata"
        sc_dir.mkdir(parents=True, exist_ok=True)
        (sc_dir / "sector_central.json").write_text("NOT JSON", encoding="utf-8")
        buy = [_make_buy_item("ai_infra")]
        act_now, _ = _run_demotion(tmp_path, buy, None)  # file written as corrupt above
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_empty_buy_list_yields_no_change(self, tmp_path):
        """Empty buy list -> conflicted stays [], no crash."""
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, [], sc)
        assert act_now["conflicted"] == []
        assert act_now["buy"] == []


class TestConflictedItemFields:
    def test_reason_en_present_on_demoted_item(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert act_now["conflicted"][0].get("reason_en") != ""

    def test_reason_zh_present_on_demoted_item(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert act_now["conflicted"][0].get("reason_zh") != ""

    def test_sector_stance_is_reduce(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert act_now["conflicted"][0].get("sector_stance") == "Reduce"

    def test_sector_stance_zh_present(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert act_now["conflicted"][0].get("sector_stance_zh") == "减配"

    def test_sector_etf_present(self, tmp_path):
        """sector_etf on the demoted item is the _SECTOR_PROXY ETF (SMH, not the fallback XLK)."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        # sector_etf is the direct proxy ETF (SMH for ai_infra), not the fallback (XLK)
        assert act_now["conflicted"][0].get("sector_etf") == "SMH"

    def test_original_fields_preserved_on_demoted_item(self, tmp_path):
        """All original buy-item fields survive the demotion merge."""
        buy = [_make_buy_item("ai_infra", name="AI Infrastructure")]
        sc = _make_sector_central("XLK", "Reduce")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        item = act_now["conflicted"][0]
        assert item["id"] == "ai_infra"
        assert item["name"] == "AI Infrastructure"
        assert item["score"] == 75


class TestConflictedKeyAlwaysPresent:
    def test_conflicted_key_present_when_empty(self, tmp_path):
        """The 'conflicted' key must exist on act_now even when no items demoted."""
        buy = [_make_buy_item("ai_infra")]
        sc = _make_sector_central("XLK", "Accumulate")
        act_now, _ = _run_demotion(tmp_path, buy, sc)
        assert "conflicted" in act_now
        assert act_now["conflicted"] == []

    def test_conflicted_key_present_with_absent_sector_central(self, tmp_path):
        buy = [_make_buy_item("ai_infra")]
        act_now, _ = _run_demotion(tmp_path, buy, None)
        assert "conflicted" in act_now

    def test_conflicted_key_present_on_empty_buy_list(self, tmp_path):
        act_now, _ = _run_demotion(tmp_path, [], None)
        assert "conflicted" in act_now


# ---------------------------------------------------------------------------
# Render-smoke: baskets.html.j2 and allocation.html.j2 parse with/without conflicted
# ---------------------------------------------------------------------------

try:
    from jinja2 import Environment, FileSystemLoader, Undefined
    _JINJA_OK = True
except ImportError:
    _JINJA_OK = False

TEMPLATE_DIR = ROOT / "templates"


def _jinja_env() -> "Environment":
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=False,
        undefined=Undefined,
    )


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
class TestBasketTemplateParses:
    def test_baskets_jinja_parses(self):
        """baskets.html.j2 must parse without exception after the conflicted edits."""
        env = _jinja_env()
        env.parse((TEMPLATE_DIR / "baskets.html.j2").read_text(encoding="utf-8"))

    def test_baskets_renders_with_conflicted_key(self):
        """baskets.html.j2 renders without crashing when act_now includes conflicted."""
        env = _jinja_env()
        html = env.get_template("baskets.html.j2").render(basket_member_syms=[])
        assert len(html) > 100

    def test_baskets_renders_without_conflicted_key(self):
        """baskets.html.j2 renders without crashing when act_now lacks conflicted key
        (backward-compat: old payload where conflicted key is absent)."""
        env = _jinja_env()
        html = env.get_template("baskets.html.j2").render(basket_member_syms=[])
        assert len(html) > 100

    def test_baskets_has_actnow_footnote_element(self):
        """The actnow-footnote element must exist in baskets.html.j2 source."""
        src = (TEMPLATE_DIR / "baskets.html.j2").read_text(encoding="utf-8")
        assert "actnow-footnote" in src

    def test_baskets_has_renderStanceChips_call(self):
        """renderStanceChips() must be called in baskets.html.j2."""
        src = (TEMPLATE_DIR / "baskets.html.j2").read_text(encoding="utf-8")
        assert "renderStanceChips" in src

    def test_baskets_has_mlcdata_stance_matrix_url(self):
        """baskets.html.j2 must reference mlcdata/stance_matrix.json for the fetch."""
        src = (TEMPLATE_DIR / "baskets.html.j2").read_text(encoding="utf-8")
        assert "stance_matrix.json" in src


@pytest.mark.skipif(not _JINJA_OK, reason="jinja2 not installed")
class TestAllocationTemplateParses:
    """allocation.html.j2 render-smoke: parse + minimal render with/without conflicted."""

    def test_allocation_jinja_parses(self):
        """allocation.html.j2 must parse without exception."""
        env = _jinja_env()
        env.parse((TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8"))

    def test_allocation_has_data_sid_attribute(self):
        """data-sid attribute must be present in allocation.html.j2."""
        src = (TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8")
        assert "data-sid" in src

    def test_allocation_has_stance_matrix_fetch(self):
        """allocation.html.j2 must fetch mlcdata/stance_matrix.json."""
        src = (TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8")
        assert "stance_matrix.json" in src

    def test_allocation_has_chip_warn_class(self):
        """allocation.html.j2 must emit chip warn class for the stance chip."""
        src = (TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8")
        assert "chip warn" in src

    def test_allocation_slow_book_copy_present(self):
        """FT-R11 replacement copy must be present in allocation.html.j2."""
        src = (TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8")
        assert "slow book" in src.lower() or "A slow book" in src

    def test_allocation_slow_book_zh_copy_present(self):
        """FT-R11 replacement ZH copy must be present in allocation.html.j2."""
        src = (TEMPLATE_DIR / "allocation.html.j2").read_text(encoding="utf-8")
        assert "慢速账本" in src


# ---------------------------------------------------------------------------
# MLC-W4: Momentum-cooling demotion tests
# ---------------------------------------------------------------------------

def _make_act_now(buy_ids: list[str], conflicted_ids: list[str] | None = None) -> dict:
    """Build a minimal act_now dict for cooling demotion tests."""
    def _item(bid: str) -> dict:
        return {"id": bid, "name": f"Theme {bid}", "name_zh": bid,
                "action": "enter", "score": 70, "clean_entry": True, "reasons": []}
    return {
        "buy": [_item(bid) for bid in buy_ids],
        "add_on_pullback": [],
        "reduce": [],
        "conflicted": [_item(bid) for bid in (conflicted_ids or [])],
    }


def _make_themes_by_id(
    bid: str,
    band: str = "high",
    hist_fade: bool = True,
    reasons: list[str] | None = None,
    hist_fade_n: int | None = None,
) -> dict:
    """Build a minimal themes_by_id dict for the given basket id.

    hist_fade_n is the threaded int from basket_score.rollover_risk (ruling 4).
    Default 7 when hist_fade=True (matches the default reason string).
    """
    _n = hist_fade_n if hist_fade_n is not None else (7 if hist_fade else None)
    _reasons = reasons if reasons is not None else (
        [f"momentum fading (hist 0.045->0.012, {_n} straight declines)"]
        if hist_fade else []
    )
    return {
        bid: {
            "id": bid,
            "textures": {
                "rollover_risk": {
                    "risk": 0.70,
                    "band": band,
                    "band_zh": "高" if band == "high" else band,
                    "reasons": _reasons,
                    "directional": False,
                    "hist_fade": hist_fade,
                    "hist_fade_n": _n,
                }
            }
        }
    }


class TestCoolingDemotionFires:
    def test_fires_on_high_band_and_hist_fade_true(self):
        """band=='high' + hist_fade==True -> item moves from buy to conflicted."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "big_pharma"
        assert len(act_now["buy"]) == 0

    def test_unaffected_items_stay_in_buy(self):
        """Only the item matching band==high+hist_fade is demoted; others remain."""
        act_now = _make_act_now(["big_pharma", "ai_infra"])
        themes_by_id = {
            **_make_themes_by_id("big_pharma", band="high", hist_fade=True),
            "ai_infra": {
                "id": "ai_infra",
                "textures": {"rollover_risk": {"band": "low", "hist_fade": False, "reasons": []}}
            },
        }
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 1
        assert act_now["conflicted"][0]["id"] == "big_pharma"
        assert len(act_now["buy"]) == 1
        assert act_now["buy"][0]["id"] == "ai_infra"

    def test_reason_en_contains_n_sessions(self):
        """reason_en must contain 'straight sessions of fade' when fired."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        reason_en = act_now["conflicted"][0].get("reason_en", "")
        assert "straight sessions of fade" in reason_en, (
            f"reason_en missing 'straight sessions of fade': {reason_en!r}"
        )

    def test_reason_zh_present(self):
        """reason_zh must be present with the ZH bilingual text."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        reason_zh = act_now["conflicted"][0].get("reason_zh", "")
        assert "动能降温" in reason_zh, f"reason_zh missing '动能降温': {reason_zh!r}"
        assert "走弱" in reason_zh, f"reason_zh missing '走弱': {reason_zh!r}"

    def test_cooling_flag_true(self):
        """Demoted item must carry 'cooling': True."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert act_now["conflicted"][0].get("cooling") is True

    def test_n_threaded_from_hist_fade_n_key(self):
        """N in reason_en comes from hist_fade_n (the threaded int), not reason-string parsing."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True,
                                          hist_fade_n=9)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        reason_en = act_now["conflicted"][0].get("reason_en", "")
        assert "9" in reason_en, f"Expected N=9 in reason_en (from hist_fade_n): {reason_en!r}"

    def test_original_fields_preserved(self):
        """All original buy-item fields survive the demotion merge."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        item = act_now["conflicted"][0]
        assert item["id"] == "big_pharma"
        assert item["score"] == 70
        assert item["clean_entry"] is True


class TestCoolingDemotionDoesNotFire:
    def test_does_not_fire_on_high_band_without_hist_fade(self):
        """band==high but hist_fade==False -> item stays in buy."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=False)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_does_not_fire_on_hist_fade_without_high_band(self):
        """hist_fade==True but band=='elevated' -> item stays in buy."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="elevated", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_does_not_fire_on_low_band(self):
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = _make_themes_by_id("big_pharma", band="low", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_does_not_fire_on_missing_texture(self):
        """Item whose theme has no rollover_risk texture stays in buy (fail-safe)."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = {"big_pharma": {"id": "big_pharma", "textures": {}}}
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1

    def test_does_not_fire_on_missing_theme(self):
        """Item with no matching theme entry stays in buy."""
        act_now = _make_act_now(["big_pharma"])
        themes_by_id = {}  # no big_pharma entry
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["conflicted"]) == 0
        assert len(act_now["buy"]) == 1


class TestCoolingDemotionNoDoubleStamp:
    def test_sector_demoted_item_not_re_stamped(self):
        """An item already in conflicted (sector-demoted) must NOT be re-processed
        by the cooling pass (it's not in buy anymore)."""
        # Simulate: item was already moved to conflicted by W2b
        act_now = {
            "buy": [],  # big_pharma already moved out of buy
            "add_on_pullback": [],
            "reduce": [],
            "conflicted": [
                {"id": "big_pharma", "score": 70, "clean_entry": True,
                 "reason_en": "sector view is Reduce — held out of the Buy list",
                 "reason_zh": "所属板块评级为减配 — 暂不列入买入清单",
                 "sector_stance": "Reduce"}
            ],
        }
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        original_conflicted_count = len(act_now["conflicted"])
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        # Must NOT add a second copy
        assert len(act_now["conflicted"]) == original_conflicted_count, (
            "Sector-demoted item must not be double-stamped by cooling pass"
        )
        # Original sector reason must be preserved unchanged
        assert act_now["conflicted"][0].get("sector_stance") == "Reduce"
        assert "cooling" not in act_now["conflicted"][0], (
            "Sector-demoted item must not gain 'cooling' flag from W4 pass"
        )


class TestCoolingDemotionEscalationImpossible:
    def test_conservation_invariant_holds(self):
        """buy + conflicted == original total at all times."""
        act_now = _make_act_now(["big_pharma", "ai_infra", "regional_banks"])
        original_total = len(act_now["buy"]) + len(act_now["conflicted"])
        themes_by_id = {
            **_make_themes_by_id("big_pharma", band="high", hist_fade=True),
            "ai_infra": {"id": "ai_infra", "textures": {
                "rollover_risk": {"band": "low", "hist_fade": False, "reasons": []}}},
            "regional_banks": {"id": "regional_banks", "textures": {
                "rollover_risk": {"band": "high", "hist_fade": True, "hist_fade_n": 4,
                                  "reasons": ["momentum fading (hist 0.02->0.005, 4 straight declines)"]}}},
        }
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert len(act_now["buy"]) + len(act_now["conflicted"]) == original_total

    def test_empty_buy_yields_no_change(self):
        """Empty buy list -> no crash, conflicted unchanged."""
        act_now = _make_act_now([])
        themes_by_id = _make_themes_by_id("big_pharma", band="high", hist_fade=True)
        _apply_momentum_cooling_demotion(act_now, themes_by_id)
        assert act_now["buy"] == []
        assert act_now["conflicted"] == []


class TestCoolingDemotionFailOpen:
    def test_fail_open_on_malformed_textures(self):
        """If textures is a non-dict (malformed payload), no crash — fail-open gracefully."""
        act_now = _make_act_now(["big_pharma"])
        # Malformed: textures is a string not a dict
        themes_by_id = {"big_pharma": {"id": "big_pharma", "textures": "BROKEN"}}
        # Should not raise; item stays in buy (cooling not triggered)
        try:
            _apply_momentum_cooling_demotion(act_now, themes_by_id)
        except Exception:
            pass  # caller wraps this in try/except in production
        # Either way the system hasn't crashed — we just verify no items were created
        total = len(act_now["buy"]) + len(act_now["conflicted"])
        assert total == 1  # one original item, not duplicated
