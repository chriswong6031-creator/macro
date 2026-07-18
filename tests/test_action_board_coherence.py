"""Tests for action-board coherence fixes (FIX 1/2/3):

  FIX 1 — conflicted demotion: themes in act_now.conflicted must route to
           on_the_run (not buy_now/buy_soon) and carry conflict_chip_en.

  FIX 2 — EW-vs-cycle disclosure: when EW overlay direction and cycle lane
           direction disagree (buy vs reduce, either way) and gate_override
           did NOT fire, the sector item carries ew_two_reads.

  FIX 3 — cap 12 + more counts: >12 items in a bucket → 12 returned +
           correct more count recorded in buckets["more"][bucket].

  COHERENCE — for a synthetic mixed payload: no theme that is buy-side on the
           us_stocks board appears in act_now reduce-side; every direction
           conflict on sector rows carries ew_two_reads or gate_override.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scripts.build_site as bs  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_baskets(tmp_path: Path, themes: list, conflicted: list | None = None,
                   buy: list | None = None) -> None:
    bd = tmp_path / "basketdata"
    bd.mkdir(exist_ok=True)
    act_now = {
        "buy": buy or [],
        "add_on_pullback": [],
        "reduce": [],
        "conflicted": conflicted or [],
    }
    (bd / "baskets.json").write_text(json.dumps(
        {"theme_intel": {"themes": themes, "act_now": act_now}}
    ))


def _write_alloc(tmp_path: Path, ranks: list | None = None) -> None:
    ad = tmp_path / "allocationdata"
    ad.mkdir(exist_ok=True)
    (ad / "allocation.json").write_text(json.dumps(
        {"ranks": ranks or [], "allocation": {"weights": []}}
    ))


def _sector_timing(fund: str, urgency: str, tag: str = "", label: str = "TEST") -> dict:
    return {fund: {
        "label": label,
        "entry": {"urgency": urgency, "tag": tag, "text": "", "days_hi": None},
        "age_short": None, "age_short_zh": None,
        "eq_badge": None, "eq_dir": "flat", "eq_tip": None, "state_style": None,
    }}


# ---------------------------------------------------------------------------
# FIX 1 — conflicted demotion
# ---------------------------------------------------------------------------

def test_conflicted_sector_reduce_routes_to_on_the_run_not_buy(tmp_path):
    """A theme with clean_entry.flag=True that is in act_now.conflicted (sector-Reduce)
    must land in on_the_run, NOT buy_now, and must carry conflict_chip_en."""
    _write_baskets(
        tmp_path,
        themes=[
            # This would normally route to buy_now (accumulate + clean_entry True)
            {"id": "cybersecurity", "name": "Cybersecurity", "reco": "accumulate",
             "reco_en": "ACCUMULATE", "score": 72,
             "textures": {"clean_entry": {"flag": True, "quality": 0.80}}},
        ],
        conflicted=[
            # Sector-Reduce demotion (W2b)
            {"id": "cybersecurity", "name": "Cybersecurity",
             "reason_en": "sector view is Reduce — held out of the Buy list",
             "reason_zh": "所属板块评级为减配 — 暂不列入买入清单",
             "sector_stance": "Reduce", "sector_etf": "XLK"},
        ],
    )
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)

    # Must NOT be in buy_now
    buy_ids = [x["ticker"] for x in b["buy_now"]]
    assert "cybersecurity" not in buy_ids, "conflicted theme must not land in buy_now"

    # Must be in on_the_run
    run_ids = [x["ticker"] for x in b["on_the_run"]]
    assert "cybersecurity" in run_ids, "conflicted theme must route to on_the_run"

    item = next(x for x in b["on_the_run"] if x["ticker"] == "cybersecurity")
    # Must carry conflict_chip_en (warn chip text)
    assert "conflict_chip_en" in item, "conflict_chip_en must be set on demotion"
    assert item["conflict_chip_en"] == "sector says Reduce"
    assert "conflict_chip_zh" in item
    assert "conflict_reason_en" in item


def test_conflicted_cooling_routes_to_on_the_run(tmp_path):
    """Momentum-cooling demotion (W4) produces chip 'momentum cooling'."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "biotech", "name": "Biotech", "reco": "accumulate",
             "reco_en": "ACCUMULATE", "score": 65,
             "textures": {"clean_entry": {"flag": True, "quality": 0.75}}},
        ],
        conflicted=[
            {"id": "biotech", "name": "Biotech",
             "reason_en": "momentum cooling — 3 straight sessions of fade",
             "reason_zh": "动能降温 — 连续3日走弱",
             "cooling": True},
        ],
    )
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)

    assert "biotech" not in [x["ticker"] for x in b["buy_now"]]
    run_item = next((x for x in b["on_the_run"] if x["ticker"] == "biotech"), None)
    assert run_item is not None
    assert run_item.get("conflict_chip_en") == "momentum cooling"
    assert run_item.get("conflict_chip_zh") == "动能降温"


def test_conflicted_does_not_affect_reduce_side_themes(tmp_path):
    """A theme already on the reduce side (trim/avoid) is unaffected by conflicted lookup
    — conflicted only gates buy-lane routing."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "legacy_media", "name": "Legacy Media", "reco": "avoid",
             "reco_en": "AVOID", "score": 20},
        ],
        conflicted=[],
    )
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)
    assert any(x["ticker"] == "legacy_media" for x in b["avoid"])


# ---------------------------------------------------------------------------
# FIX 3 — cap 12 + more counts
# ---------------------------------------------------------------------------

def test_cap_12_and_more_count_avoid(tmp_path):
    """When >12 themes route to avoid, only 12 are returned and more['avoid'] = N-12."""
    n_themes = 15
    themes = [
        {"id": f"avoid_th_{i}", "name": f"Avoid Theme {i}", "reco": "avoid",
         "reco_en": "AVOID", "score": i}
        for i in range(n_themes)
    ]
    _write_baskets(tmp_path, themes=themes)
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)

    assert len(b["avoid"]) == 12, f"Expected 12, got {len(b['avoid'])}"
    assert b["more"]["avoid"] == n_themes - 12, (
        f"Expected more['avoid']={n_themes-12}, got {b['more']['avoid']}"
    )


def test_cap_12_and_more_count_buy_now(tmp_path):
    """When >12 themes route to buy_now, only 12 are returned and more['buy_now'] is correct."""
    n_themes = 14
    themes = [
        {"id": f"bn_th_{i}", "name": f"Buy Theme {i}", "reco": "accumulate",
         "reco_en": "ACCUMULATE", "score": i,
         "textures": {"clean_entry": {"flag": True, "quality": 0.80}}}
        for i in range(n_themes)
    ]
    _write_baskets(tmp_path, themes=themes)
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)

    assert len(b["buy_now"]) == 12
    assert b["more"]["buy_now"] == n_themes - 12


def test_no_more_when_under_cap(tmp_path):
    """When a bucket has <= 12 items, more count is 0."""
    _write_baskets(tmp_path, themes=[
        {"id": "alpha", "name": "Alpha", "reco": "avoid", "reco_en": "AVOID", "score": 5},
    ])
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)
    assert b["more"]["avoid"] == 0
    assert b["more"]["buy_now"] == 0


# ---------------------------------------------------------------------------
# FIX 2 — EW-vs-cycle ew_two_reads on sector rows
# ---------------------------------------------------------------------------

def test_ew_two_reads_fires_when_ew_buy_cycle_reduce(tmp_path):
    """EW overlay on_the_run (buy-side) + cycle take_profits (reduce-side) and no
    gate_override → ew_two_reads attached to the sector item."""
    # Build a sector_overlay with XLE reco=accumulate, clean_entry=False → ew_lane=on_the_run
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_energy", "name": "Energy (EW)", "name_zh": "能源（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓",
             "score": 55,
             # ce_flag=False so ew_lane="on_the_run" (buy-side)
             "textures": {"clean_entry": {"flag": False, "quality": 0.45}}},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    # Verify sector_overlay has XLE in on_the_run EW lane
    assert "XLE" in basket_items["sector_overlay"]
    assert basket_items["sector_overlay"]["XLE"]["ew_lane"] == "on_the_run"

    # Cycle: XLE at exit (→ take_profits, reduce-side)
    st = _sector_timing("XLE", "exit", label="ROLLING OVER")
    board = bs.action_board(st, [], basket_items)

    xle_item = None
    for lane in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        for item in board[lane]:
            if item.get("ticker") == "XLE":
                xle_item = item
                found_lane = lane
                break

    assert xle_item is not None, "XLE must be in some lane"
    # gate_override must NOT have fired (EW is buy-side, not trim/avoid)
    assert not xle_item.get("gate_override"), "gate_override must not fire when EW is buy-side"
    # ew_two_reads must be attached (EW=on_the_run buy-side, cycle=take_profits reduce-side)
    assert "ew_two_reads" in xle_item, (
        f"ew_two_reads must be set (XLE in {found_lane}); "
        f"ew_lane={xle_item.get('ew_lane')}"
    )
    ewtr = xle_item["ew_two_reads"]
    assert "cycle_label_en" in ewtr
    assert "ew_label_en" in ewtr
    assert "cycle_label_zh" in ewtr
    assert "ew_label_zh" in ewtr


def test_ew_two_reads_does_not_fire_when_both_reduce(tmp_path):
    """When EW is also reduce-side, gate_override fires and ew_two_reads must NOT be set."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_health", "name": "Health (EW)", "name_zh": "医疗（等权）",
             "reco": "trim", "reco_en": "TRIM", "reco_zh": "减仓",
             "label": "TRIM", "label_zh": "减仓",
             "score": 40},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    assert "XLV" in basket_items["sector_overlay"]
    # Cycle: XLV now → buy_now; EW trim → gate_override fires → take_profits
    st = _sector_timing("XLV", "now", label="RALLY ON")
    board = bs.action_board(st, [], basket_items)

    tp_items = [x for x in board["take_profits"] if x.get("ticker") == "XLV"]
    assert tp_items, "XLV should be in take_profits after gate_override"
    assert tp_items[0].get("gate_override") is True
    # No ew_two_reads when gate_override fired
    assert "ew_two_reads" not in tp_items[0], (
        "ew_two_reads must not be set when gate_override fired"
    )


def test_ew_two_reads_does_not_fire_when_directions_agree(tmp_path):
    """When EW and cycle agree (both buy-side), no ew_two_reads chip."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_tech", "name": "Tech (EW)", "name_zh": "科技（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓",
             "score": 75,
             "textures": {"clean_entry": {"flag": True, "quality": 0.80}}},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    assert "XLK" in basket_items["sector_overlay"]
    # EW ew_lane=buy_now (accumulate+clean_entry); cycle now → buy_now too
    st = _sector_timing("XLK", "now", label="RALLY ON")
    board = bs.action_board(st, [], basket_items)

    xlk_item = None
    for lane in board:
        if lane in ("notable", "more"):
            continue
        for item in (board[lane] if isinstance(board[lane], list) else []):
            if item.get("ticker") == "XLK":
                xlk_item = item
                break

    assert xlk_item is not None
    assert "ew_two_reads" not in xlk_item, "ew_two_reads must not appear when directions agree"


# ---------------------------------------------------------------------------
# COHERENCE contract
# ---------------------------------------------------------------------------

def test_coherence_no_buy_side_buy_reduce_conflict(tmp_path):
    """Coherence: no theme that appears in buy-side lanes on the action board
    (buy_now / buy_soon / on_the_run from basket_items) also appears in the
    act_now reduce bucket.  Conflicted items must NOT be in buy lanes."""
    # Build a mixed payload: one conflicted item, one clean buy, one reduce
    _write_baskets(
        tmp_path,
        themes=[
            # Conflicted (would-be buy_now, demoted by sector-Reduce)
            {"id": "semis", "name": "Semis", "reco": "accumulate",
             "reco_en": "ACCUMULATE", "score": 70,
             "textures": {"clean_entry": {"flag": True, "quality": 0.80}}},
            # Clean buy
            {"id": "cloud", "name": "Cloud", "reco": "accumulate",
             "reco_en": "ACCUMULATE", "score": 80,
             "textures": {"clean_entry": {"flag": True, "quality": 0.90}}},
            # Reduce
            {"id": "biotech", "name": "Biotech", "reco": "trim",
             "reco_en": "TRIM", "score": 30},
        ],
        conflicted=[
            {"id": "semis", "name": "Semis",
             "reason_en": "sector view is Reduce — held out of the Buy list",
             "reason_zh": "所属板块评级为减配",
             "sector_stance": "Reduce", "sector_etf": "XLK"},
        ],
    )
    _write_alloc(tmp_path)
    b = bs.basket_action_items(tmp_path)

    buy_side_ids = set(
        x["ticker"] for lane in ("buy_now", "buy_soon")
        for x in b[lane]
    )
    # semis must NOT be in buy lanes
    assert "semis" not in buy_side_ids, "conflicted theme must not appear in buy lanes"
    # cloud must be in buy_now
    assert "cloud" in buy_side_ids

    # semis must be in on_the_run and carry conflict_chip_en
    run_item = next((x for x in b["on_the_run"] if x["ticker"] == "semis"), None)
    assert run_item is not None, "conflicted item must be in on_the_run"
    assert run_item.get("conflict_chip_en"), "conflict_chip_en must be set"


def test_coherence_sector_direction_conflicts_carry_ew_two_reads_or_gate_override(tmp_path):
    """For every sector item in the action board where EW and cycle directions disagree,
    the item must carry either gate_override=True or ew_two_reads."""
    # XLV: EW=on_the_run (accumulate, no ce) vs cycle=take_profits (exit)
    # XLE: EW=buy_now (accumulate, ce) vs cycle=avoid (unknown urgency "other")
    # XLK: EW=on_the_run vs cycle=on_the_run (agree) — no chip expected
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_health", "name": "Health (EW)", "name_zh": "医疗（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓", "score": 55,
             "textures": {"clean_entry": {"flag": False}}},
            {"id": "us_sector_energy", "name": "Energy (EW)", "name_zh": "能源（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓", "score": 60,
             "textures": {"clean_entry": {"flag": True, "quality": 0.75}}},
            {"id": "us_sector_tech", "name": "Tech (EW)", "name_zh": "科技（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓", "score": 80,
             "textures": {"clean_entry": {"flag": False}}},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    # XLV EW=on_the_run; cycle=take_profits (exit) — disagree, no gate_override
    # XLE EW=buy_now; cycle=avoid (unknown urgency) — disagree, no gate_override
    # XLK EW=on_the_run; cycle=on_the_run (DON'T CHASE) — agree, no chip
    st = {}
    st.update(_sector_timing("XLV", "exit", label="ROLLING OVER"))
    st.update(_sector_timing("XLE", "unknown_urge", label="UNKNOWN"))
    st.update(_sector_timing("XLK", "caution", "DON'T CHASE", label="EXTENDED"))
    board = bs.action_board(st, [], basket_items)

    all_sector_items: dict[str, dict] = {}
    for lane in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        for item in board[lane]:
            if item.get("kind") == "sector":
                all_sector_items[item["ticker"]] = item

    _BUY_SIDE = {"buy_now", "buy_soon", "on_the_run"}
    _RED_SIDE = {"take_profits", "avoid"}

    for ticker, item in all_sector_items.items():
        ew_lane = item.get("ew_lane", "")
        cycle_lane = next(
            ln for ln in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid")
            if any(x.get("ticker") == ticker for x in board[ln])
        )
        ew_buy = ew_lane in _BUY_SIDE
        ew_red = ew_lane in _RED_SIDE
        cyc_buy = cycle_lane in _BUY_SIDE
        cyc_red = cycle_lane in _RED_SIDE
        direction_conflict = (ew_buy and cyc_red) or (ew_red and cyc_buy)
        if direction_conflict:
            has_disclosure = item.get("gate_override") or item.get("ew_two_reads")
            assert has_disclosure, (
                f"{ticker}: EW={ew_lane}, cycle={cycle_lane} disagree but neither "
                f"gate_override nor ew_two_reads is set"
            )


# ---------------------------------------------------------------------------
# Review fixes — sector-row conflict lift + ZH cycle label
# ---------------------------------------------------------------------------

def test_sector_row_lifts_conflict_fields_from_ew_overlay(tmp_path):
    """A us_sector_* basket demoted by W2b (act_now.conflicted) must surface its
    demotion receipt ON the rendered sector row itself — conflict_chip_en/zh and
    conflict_reason_en/zh lifted from the EW overlay to the top-level item
    (MLC-R7: the conflict may not hide inside the ew dict)."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_realestate", "name": "Real Estate (EW)",
             "name_zh": "房地产（等权）", "reco": "accumulate",
             "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓", "score": 60,
             "textures": {"clean_entry": {"flag": True, "quality": 0.9}}},
        ],
        conflicted=[
            {"id": "us_sector_realestate", "name": "Real Estate (EW)",
             "reason_en": "sector view is Reduce — held out of the Buy list",
             "reason_zh": "所属板块评级为减配 — 暂不列入买入清单",
             "sector_stance": "Reduce", "sector_etf": "XLRE"},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    ov = basket_items["sector_overlay"].get("XLRE")
    assert ov is not None and ov.get("conflict_chip_en"), \
        "overlay item must carry the demotion chip"

    st = _sector_timing("XLRE", "now", label="BUY ZONE")
    board = bs.action_board(st, [], basket_items)

    xlre = None
    for lane in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        for item in board[lane]:
            if item.get("ticker") == "XLRE":
                xlre = item
    assert xlre is not None, "XLRE sector row must render"
    # Receipt lifted to the top-level sector item (rendered by ab_sector_row)
    assert xlre.get("conflict_chip_en") == ov["conflict_chip_en"]
    assert xlre.get("conflict_chip_zh")
    assert xlre.get("conflict_reason_en") == ov["conflict_reason_en"]
    assert xlre.get("conflict_reason_zh")


def test_ew_two_reads_cycle_label_zh_is_chinese(tmp_path):
    """The ew_two_reads ZH cycle label must come from STATE_DISPLAY (real Chinese),
    not fall back to the English label (EN-in-ZH leak class)."""
    _write_baskets(
        tmp_path,
        themes=[
            {"id": "us_sector_energy", "name": "Energy (EW)", "name_zh": "能源（等权）",
             "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓",
             "label": "ACCUMULATE", "label_zh": "加仓", "score": 55,
             "textures": {"clean_entry": {"flag": False, "quality": 0.45}}},
        ],
    )
    _write_alloc(tmp_path)
    basket_items = bs.basket_action_items(tmp_path)

    from engine.cycles import STATE_DISPLAY
    st = _sector_timing("XLE", "exit", label=STATE_DISPLAY["DECLINE"]["label"])
    st["XLE"]["state"] = "DECLINE"   # ladder state key drives the ZH lookup
    board = bs.action_board(st, [], basket_items)

    xle = None
    for lane in ("take_profits", "avoid", "hold", "on_the_run", "buy_now", "buy_soon"):
        for item in board[lane]:
            if item.get("ticker") == "XLE":
                xle = item
    assert xle is not None and "ew_two_reads" in xle
    zh = xle["ew_two_reads"]["cycle_label_zh"]
    assert zh == STATE_DISPLAY["DECLINE"]["label_zh"], f"expected real ZH, got {zh!r}"
    # And it must actually contain CJK, not the EN fallback
    assert any("一" <= ch <= "鿿" for ch in zh)
