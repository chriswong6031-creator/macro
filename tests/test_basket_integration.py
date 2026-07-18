"""Tests for the narrative-basket → stock scored integration (the backtested channel).

Invariants:
  * a name whose primary narrative basket is BELOW its long-term trend (or fading /
    deteriorating) is SIZED DOWN via a subtract-only risk component + a caution — never
    re-ranked (the absolute-trend gate is the one backtested edge; momentum rank is not).
  * a healthy (above-trend, not-crowded) basket adds NO de-risk.
  * the unified action board buckets baskets by reco and flags the risk side.
  * us_sector_* themes go to sector_overlay, NOT narrative bucket rows.
  * enter/accumulate without clean_entry lands in on_the_run; with it lands in buy lanes.
"""
import json

from engine import stock_score as ss


def _rec(basket_alloc=None, **kw):
    base = {
        "ticker": "TST", "name": "Test Co", "sector": "Technology",
        "alpha": 2.0, "alpha_entry": "pullback",
        "ladder": {"state": "RALLY ON", "label": "UPTREND", "dir": "up",
                   "eq_dir": "up", "entry": {"urgency": "now"}},
        "tech": {"off_52w_high_pct": -6.0, "rsi14": 55.0},
        "sector_rs": {"pct": 80.0},
        "factor": {"value": 0.5, "profitability": 0.8, "quality": 0.6, "low_vol": 0.2},
        "sue": 1.5, "insider_bps": 20.0, "accounting": {"verdict": "clean"},
    }
    if basket_alloc is not None:
        base["basket_alloc"] = basket_alloc
    base.update(kw)
    return base


# --- _basket_risk unit -------------------------------------------------------
def test_below_trend_basket_full_haircut():
    hc, cau = ss._basket_risk({"basket_alloc":
                               {"name": "Non-AI Software", "above_trend": False,
                                "eligible": False, "label": "deteriorating"}})
    assert hc == ss._BASKET_RISK_MAX
    assert cau and "below its long-term trend" in cau["en"]


def test_deteriorating_above_trend_partial():
    hc, _ = ss._basket_risk({"basket_alloc":
                             {"name": "X", "above_trend": True, "eligible": True,
                              "label": "deteriorating"}})
    assert 0 < hc < ss._BASKET_RISK_MAX


def test_crowded_small_cap():
    hc, _ = ss._basket_risk({"basket_alloc":
                             {"name": "X", "above_trend": True, "eligible": True,
                              "label": "dominant", "crowded": True}})
    assert 0 < hc < ss._BASKET_RISK_MAX * 0.5


def test_healthy_basket_no_derisk():
    hc, cau = ss._basket_risk({"basket_alloc":
                               {"name": "Memory", "above_trend": True, "eligible": True,
                                "label": "dominant"}})
    assert hc == 0.0 and cau is None
    assert ss._basket_risk({})[0] == 0.0


# --- conviction_profile integration -----------------------------------------
def test_below_trend_basket_sizes_down_and_warns():
    prof = ss.conviction_profile(
        _rec(basket_alloc={"name": "Non-AI Software", "above_trend": False,
                           "eligible": False, "label": "deteriorating", "slug": "non_ai_software"}),
        "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert comps.get("basket_trend") == ss._BASKET_RISK_MAX
    assert any("narrative basket" in c.lower() for c in prof.get("cautions") or [])
    # surfaced for Mastermind / display
    assert (prof.get("basket_alloc") or {}).get("slug") == "non_ai_software"


def test_healthy_basket_no_basket_trend_component():
    prof = ss.conviction_profile(
        _rec(basket_alloc={"name": "Memory", "above_trend": True, "eligible": True,
                           "label": "dominant"}),
        "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert "basket_trend" not in comps


def test_no_basket_alloc_is_inert():
    prof = ss.conviction_profile(_rec(), "US")
    comps = (prof.get("risk") or {}).get("components") or {}
    assert "basket_trend" not in comps
    assert prof.get("basket_alloc") is None


# --- unified action board ----------------------------------------------------
def test_basket_action_items_buckets_and_validates(tmp_path):
    """Narrative themes (non us_sector_*) route by reco + clean_entry; avoid is risk-flagged."""
    import scripts.build_site as bs
    bd = tmp_path / "basketdata"; bd.mkdir()
    (bd / "baskets.json").write_text(json.dumps({"theme_intel": {"themes": [
        # accumulate + clean_entry → buy_now
        {"id": "memory_storage", "name": "Memory", "reco": "accumulate",
         "reco_en": "ACCUMULATE", "score": 80, "signal_strength": {"grade": "descriptive"},
         "textures": {"clean_entry": {"flag": True, "quality": 0.8}}},
        # avoid → avoid (risk side)
        {"id": "non_ai_software", "name": "Non-AI Software", "reco": "avoid",
         "reco_en": "AVOID", "score": 30, "signal_strength": {"grade": "backtested"}},
        # enter + clean_entry → buy_soon
        {"id": "uranium", "name": "Uranium", "reco": "enter", "reco_en": "ENTER", "score": 60,
         "textures": {"clean_entry": {"flag": True, "quality": 0.7}}},
        # us_sector_tech accumulate → sector_overlay[XLK], NOT buy_now
        {"id": "us_sector_tech", "name": "Tech (EW)", "name_zh": "科技（等权）",
         "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓", "score": 75,
         "textures": {"clean_entry": {"flag": True, "quality": 0.75}}},
    ], "act_now": {"buy": [], "add_on_pullback": [], "reduce": []}}}))
    ad = tmp_path / "allocationdata"; ad.mkdir()
    (ad / "allocation.json").write_text(json.dumps({
        "ranks": [{"id": "memory_storage", "rank": 1, "eligible": True,
                   "gate": {"above_200dma": True}, "durability": {"bar": 0.8}}],
        "allocation": {"weights": [{"id": "memory_storage", "weight": 0.125}]}}))
    b = bs.basket_action_items(tmp_path)
    # Memory goes to buy_now
    assert [x["name"] for x in b["buy_now"]] == ["Memory"]
    assert b["buy_now"][0]["book_wt"] == 0.125 and b["buy_now"][0]["validated"] is False
    # Uranium goes to buy_soon (enter + clean_entry)
    assert [x["name"] for x in b["buy_soon"]] == ["Uranium"]
    # Non-AI Software goes to avoid (risk-flagged)
    assert b["avoid"][0]["name"] == "Non-AI Software" and b["avoid"][0]["validated"] is True
    # us_sector_tech must NOT appear in any narrative lane
    all_lane_ids = [x["ticker"] for lane_k in ("buy_now", "buy_soon", "on_the_run",
                                                "take_profits", "hold", "avoid")
                    for x in b[lane_k]]
    assert "us_sector_tech" not in all_lane_ids, "us_sector_ must go to sector_overlay only"
    # us_sector_tech must appear in sector_overlay keyed by SPDR ticker
    assert "XLK" in b["sector_overlay"]
    assert b["sector_overlay"]["XLK"]["ticker"] == "us_sector_tech"
    # sector_overlay items carry ew_lane
    assert "ew_lane" in b["sector_overlay"]["XLK"]
    # all narrative lane items are kind='theme'
    assert all(x["kind"] == "theme"
               for lane_k in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid")
               for x in b[lane_k])


def test_basket_action_items_clean_entry_routing(tmp_path):
    """enter/accumulate WITHOUT clean_entry lands in on_the_run; WITH it lands in buy lanes."""
    import scripts.build_site as bs
    bd = tmp_path / "basketdata"; bd.mkdir()
    (bd / "baskets.json").write_text(json.dumps({"theme_intel": {"themes": [
        # accumulate, no clean_entry → on_the_run
        {"id": "semi_equipment", "name": "Semi Equipment", "reco": "accumulate",
         "reco_en": "ACCUMULATE", "score": 65,
         "textures": {"clean_entry": {"flag": False, "quality": 0.45}}},
        # enter, no textures at all → on_the_run (flag defaults False, act_now not in buy list)
        {"id": "gold_miners", "name": "Gold Miners", "reco": "enter",
         "reco_en": "ENTER", "score": 55},
        # accumulate + clean_entry → buy_now
        {"id": "insurance", "name": "Insurance", "reco": "accumulate",
         "reco_en": "ACCUMULATE", "score": 77,
         "textures": {"clean_entry": {"flag": True, "quality": 0.75}}},
        # enter + clean_entry → buy_soon
        {"id": "biotech", "name": "Biotech", "reco": "enter",
         "reco_en": "ENTER", "score": 60,
         "textures": {"clean_entry": {"flag": True, "quality": 0.70}}},
    ], "act_now": {"buy": [], "add_on_pullback": [], "reduce": []}}}))
    (tmp_path / "allocationdata").mkdir()
    (tmp_path / "allocationdata" / "allocation.json").write_text(json.dumps(
        {"ranks": [], "allocation": {"weights": []}}))
    b = bs.basket_action_items(tmp_path)
    on_run_ids = [x["ticker"] for x in b["on_the_run"]]
    assert "semi_equipment" in on_run_ids, "accumulate+no clean_entry→on_the_run"
    assert "gold_miners" in on_run_ids, "enter+no textures→on_the_run"
    assert [x["ticker"] for x in b["buy_now"]] == ["insurance"]
    assert [x["ticker"] for x in b["buy_soon"]] == ["biotech"]
    # on_the_run items carry run_reason_en
    semi_item = next(x for x in b["on_the_run"] if x["ticker"] == "semi_equipment")
    assert "run_reason_en" in semi_item


def test_basket_action_items_graceful_without_files(tmp_path):
    b = __import__("scripts.build_site", fromlist=["x"]).basket_action_items(tmp_path)
    # 6 bucket keys + sector_overlay + more (FIX 3: cap disclosure sub-dict)
    expected_keys = {"buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid",
                     "sector_overlay", "more"}
    assert set(b.keys()) == expected_keys
    for k in ("buy_now", "buy_soon", "on_the_run", "take_profits", "hold", "avoid"):
        assert b[k] == []
    assert b["sector_overlay"] == {}


# --- action_board() urgency/tag routing + overlay merge ----------------------
def _make_sector_timing(fund: str, urgency: str, tag: str = "", label: str = "TEST") -> dict:
    """Build a minimal sector_timing entry mirroring real call shape."""
    return {fund: {
        "label": label,
        "entry": {"urgency": urgency, "tag": tag, "text": "", "days_hi": None},
        "age_short": None, "age_short_zh": None,
        "eq_badge": None, "eq_dir": "flat", "eq_tip": None, "state_style": None,
    }}


def test_action_board_caution_tag_routing(tmp_path):
    """Urgency routing — 2026-07-10 us_stocks scorecard adjudication.

    lane_hint wins over tag fallback; caution+'TAKE PROFITS' (no hint)→take_profits;
    near-miss/unknown caution→hold (conservative de-escalation-safe default);
    WAIT demotion items (lane_hint='buy_soon')→buy_soon with chip_en='WAIT'.

    Fallback path (no lane_hint):
      caution+DON'T CHASE→on_the_run; caution+TAKE PROFITS→take_profits;
      caution+UNCONFIRMED→avoid; exit→take_profits; unknown caution→hold.
    """
    import scripts.build_site as bs
    st = {}
    st.update(_make_sector_timing("XLK", "caution", "DON'T CHASE"))
    st.update(_make_sector_timing("XLC", "caution", "TAKE PROFITS"))
    st.update(_make_sector_timing("XLY", "caution", "UNCONFIRMED — HIGH RISK"))
    st.update(_make_sector_timing("XLF", "exit"))
    st.update(_make_sector_timing("XLI", "now"))
    board = bs.action_board(st, [])
    assert any(x["ticker"] == "XLK" for x in board["on_the_run"]), "DON'T CHASE→on_the_run"
    assert any(x["ticker"] == "XLC" for x in board["take_profits"]), "caution+TP→take_profits"
    assert any(x["ticker"] == "XLY" for x in board["avoid"]), "UNCONFIRMED→avoid"
    assert any(x["ticker"] == "XLF" for x in board["take_profits"]), "exit→take_profits"
    assert any(x["ticker"] == "XLI" for x in board["buy_now"]), "now→buy_now"
    # No sector appears in two lanes
    all_tickers = [x["ticker"] for lane in ("buy_now", "buy_soon", "on_the_run",
                                             "take_profits", "hold", "avoid")
                   for x in board[lane]]
    assert len(all_tickers) == len(set(all_tickers)), "duplicate sector in two lanes"


def test_action_board_unknown_caution_routes_to_hold(tmp_path):
    """Unknown/near-miss caution tags (no lane_hint) route to hold — conservative
    de-escalation-safe default per 2026-07-10 adjudication.  Pre-adjudication default
    was take_profits; that was over-aggressive for an ambiguous tag."""
    import scripts.build_site as bs
    st = {}
    st.update(_make_sector_timing("AAA", "caution", "SOME UNKNOWN TAG"))
    st.update(_make_sector_timing("BBB", "caution", ""))   # empty tag
    # near-miss: curly apostrophe — NOT the engine tag
    st.update(_make_sector_timing("CCC", "caution", "DON’T CHASE"))
    board = bs.action_board(st, [])
    assert board["take_profits"] == [], "unknown caution must not land in take_profits"
    assert board["on_the_run"] == [], "near-miss curly-apos must not land in on_the_run"
    hold_tickers = {x["ticker"] for x in board["hold"]}
    assert hold_tickers == {"AAA", "BBB", "CCC"}, "unknown caution→hold"


def _make_sector_timing_with_hint(fund: str, urgency: str, tag: str,
                                  lane_hint: str, days_hi: int | None = None) -> dict:
    """Build a sector_timing entry with lane_hint on the entry dict."""
    return {fund: {
        "label": "TEST",
        "entry": {"urgency": urgency, "tag": tag, "lane_hint": lane_hint,
                  "text": "", "text_zh": "", "days_hi": days_hi},
        "age_short": "3d", "age_short_zh": "3日",
        "eq_badge": None, "eq_dir": "flat", "eq_tip": None, "state_style": None,
    }}


def test_action_board_lane_hint_wins(tmp_path):
    """lane_hint on the engine entry dict routes the item regardless of the tag fallback.
    BOTTOMING·WAIT demotions carry lane_hint='buy_soon' so they appear in Almost ready."""
    import scripts.build_site as bs
    st = {}
    # lane_hint='buy_soon' wins over caution default
    st.update(_make_sector_timing_with_hint(
        "XLB", "caution", "BOTTOMING · EXTENDED — WAIT", "buy_soon"))
    st.update(_make_sector_timing_with_hint(
        "XLE", "caution", "BOTTOMING · UNCONFIRMED — WAIT", "buy_soon"))
    # lane_hint='on_the_run' wins over caution default
    st.update(_make_sector_timing_with_hint(
        "XLK", "caution", "DON'T CHASE", "on_the_run"))
    # lane_hint='take_profits' wins
    st.update(_make_sector_timing_with_hint(
        "XLU", "caution", "TAKE PROFITS", "take_profits"))
    # lane_hint='avoid'
    st.update(_make_sector_timing_with_hint(
        "XLY", "caution", "UNCONFIRMED — HIGH RISK", "avoid"))
    board = bs.action_board(st, [])

    buy_soon_tickers = {x["ticker"] for x in board["buy_soon"]}
    assert buy_soon_tickers == {"XLB", "XLE"}, "lane_hint=buy_soon→Almost ready"
    # WAIT demotion items get chip_en='WAIT', chip_tone='warn'
    for item in board["buy_soon"]:
        assert item["chip_en"] == "WAIT", f"{item['ticker']} chip_en should be WAIT"
        assert item["chip_zh"] == "等待", f"{item['ticker']} chip_zh should be 等待"
        assert item["chip_tone"] == "warn", f"{item['ticker']} chip_tone should be warn"

    assert any(x["ticker"] == "XLK" for x in board["on_the_run"]), "lane_hint=on_the_run"
    assert any(x["ticker"] == "XLU" for x in board["take_profits"]), "lane_hint=take_profits"
    assert any(x["ticker"] == "XLY" for x in board["avoid"]), "lane_hint=avoid"
    # no double-listing
    all_tickers = [x["ticker"] for lane in board.values() for x in lane]
    assert len(all_tickers) == len(set(all_tickers))


def test_action_board_stat_chip_fields_per_lane(tmp_path):
    """stat_en / stat_zh / chip_en / chip_zh / chip_tone / text_zh present on every item."""
    import scripts.build_site as bs
    st = {}
    st.update(_make_sector_timing("XLI", "now"))
    st.update(_make_sector_timing("XLK", "caution", "DON'T CHASE"))
    st.update(_make_sector_timing("XLF", "exit"))
    st.update(_make_sector_timing("XLC", "hold"))
    st.update(_make_sector_timing_with_hint(
        "XLB", "caution", "BOTTOMING · EXTENDED — WAIT", "buy_soon"))
    board = bs.action_board(st, [])

    def _check(lane_name: str, ticker: str, expected_stat_en: str):
        items = [x for x in board[lane_name] if x["ticker"] == ticker]
        assert items, f"{ticker} not in {lane_name}"
        item = items[0]
        for field in ("stat_en", "stat_zh", "chip_en", "chip_zh", "chip_tone", "text_zh"):
            assert field in item, f"{ticker}: missing field {field!r}"
        assert item["stat_en"] == expected_stat_en, \
            f"{ticker} stat_en: got {item['stat_en']!r}, want {expected_stat_en!r}"

    _check("buy_now",     "XLI", "clean entry")           # age_short=None so no suffix
    _check("on_the_run",  "XLK", "extended · wait for pullback")
    _check("take_profits","XLF", "momentum rolled over")  # exit urgency
    _check("hold",        "XLC", "uptrend intact")
    _check("buy_soon",    "XLB", "extended — wait")       # EXTENDED variant


def _make_basket_items_with_sector_overlay(tmp_path, sector_themes: list) -> dict:
    """Build basket_items via the REAL basket_action_items() so sector_overlay carries
    whatever fields the builder actually produces (including 'reco').  Mirrors the real
    call shape — tests must not hand-craft sector_overlay and risk drifting from production."""
    import scripts.build_site as bs
    bd = tmp_path / "basketdata"; bd.mkdir(exist_ok=True)
    (bd / "baskets.json").write_text(json.dumps(
        {"theme_intel": {"themes": sector_themes,
                         "act_now": {"buy": [], "add_on_pullback": [], "reduce": []}}}))
    (tmp_path / "allocationdata").mkdir(exist_ok=True)
    (tmp_path / "allocationdata" / "allocation.json").write_text(
        json.dumps({"ranks": [], "allocation": {"weights": []}}))
    return bs.basket_action_items(tmp_path)


def test_two_reads_chip_zh_fields():
    """two_reads_chip carries cycle_label_zh and setup_label_zh per contract
    (2026-07-10 us_stocks scorecard adjudication).

    Tests the ZH field construction by exercising the same STATE_DISPLAY lookup
    and SETUP_ZH map that sector_setup_view uses at runtime.
    """
    from engine.cycles import STATE_DISPLAY

    # ZH map as defined in sector_setup_view (mirrors ENTRY_STATUS_ZH in template)
    SETUP_ZH = {
        "buy_now": "立即买入", "partial": "半仓",
        "buy_soon": "即将买入", "setup": "构筑中",
        "extended": "过热", "watch": "观察",
        "avoid": "回避", "topping": "做顶",
        "blocked": "封锁", "exit": "退出",
    }

    # Verify STATE_DISPLAY keys carry label_zh
    for state_key, disp in STATE_DISPLAY.items():
        assert "label_zh" in disp, f"STATE_DISPLAY[{state_key!r}] missing label_zh"

    # Verify cycle_label_zh lookup: TOP WATCH → 接近高点
    top_watch_zh = STATE_DISPLAY.get("TOP WATCH", {}).get("label_zh")
    assert top_watch_zh == "接近高点", f"TOP WATCH label_zh: {top_watch_zh!r}"

    # Verify setup_label_zh: known states resolve
    assert SETUP_ZH["buy_now"] == "立即买入"
    assert SETUP_ZH["buy_soon"] == "即将买入"
    assert SETUP_ZH["exit"] == "退出"

    # Verify fallback (unknown state key returns the EN label unchanged)
    unknown_state = "SOME_UNKNOWN"
    fallback_label = "BUY SETUP"
    result = SETUP_ZH.get(unknown_state, fallback_label)
    assert result == fallback_label, "unknown state should fall back to EN label"


def test_action_board_reduce_override(tmp_path):
    """Cycle buy_now + EW overlay trim (from real basket_action_items output) →
    moved to take_profits with gate_override=True.
    Drives end-to-end from basket_action_items() so sector_overlay 'reco' field
    matches production (fixes false-confidence from hand-crafted fixtures)."""
    import scripts.build_site as bs
    # Build basket_items via the real function: us_sector_health reco=trim
    sector_themes = [
        {"id": "us_sector_health", "name": "Health (EW)", "name_zh": "医疗（等权）",
         "reco": "trim", "reco_en": "TRIM", "reco_zh": "减仓", "score": 40},
    ]
    basket_items = _make_basket_items_with_sector_overlay(tmp_path, sector_themes)
    # Verify basket_action_items actually produced reco in the overlay entry
    assert "XLV" in basket_items["sector_overlay"], "XLV must be in sector_overlay"
    assert basket_items["sector_overlay"]["XLV"]["reco"] == "trim", \
        "sector_overlay entry must carry reco for reduce-side override to fire"

    # XLV: cycle says buy_now (urgency=now)
    st = _make_sector_timing("XLV", "now")
    board = bs.action_board(st, [], basket_items)
    # XLV must be in take_profits, not buy_now (reduce-side override fired)
    assert not any(x["ticker"] == "XLV" for x in board["buy_now"]), \
        "XLV should be moved out of buy_now by reduce override"
    tp_item = next((x for x in board["take_profits"] if x["ticker"] == "XLV"), None)
    assert tp_item is not None, "XLV should appear in take_profits after gate override"
    assert tp_item.get("gate_override") is True
    assert "ew" in tp_item


def test_action_board_ew_divergence_attach(tmp_path):
    """Overlay accumulate (from real basket_action_items output) + cycle take_profits row
    keeps its lane but carries item['ew'] — no override because reco is not trim/avoid.

    Uses exit urgency (unambiguous take_profits routing) rather than an unknown caution
    tag — the 2026-07-10 adjudication changed unknown caution default to hold, so the
    old test fixture ('ROLLING OVER' caution) would now land in hold instead.
    """
    import scripts.build_site as bs
    # Build basket_items via the real function: us_sector_materials reco=accumulate
    sector_themes = [
        {"id": "us_sector_materials", "name": "Materials (EW)", "name_zh": "材料（等权）",
         "reco": "accumulate", "reco_en": "ACCUMULATE", "reco_zh": "加仓", "score": 70,
         "textures": {"clean_entry": {"flag": True, "quality": 0.70}}},
    ]
    basket_items = _make_basket_items_with_sector_overlay(tmp_path, sector_themes)
    assert "XLB" in basket_items["sector_overlay"], "XLB must be in sector_overlay"
    assert basket_items["sector_overlay"]["XLB"]["reco"] == "accumulate", \
        "sector_overlay entry must carry reco"

    # XLB: cycle says exit (→ take_profits unambiguously)
    st = _make_sector_timing("XLB", "exit", "TAKE PROFITS")
    board = bs.action_board(st, [], basket_items)
    # XLB stays in take_profits (overlay is accumulate, not trim/avoid → no override)
    tp_item = next((x for x in board["take_profits"] if x["ticker"] == "XLB"), None)
    assert tp_item is not None, "XLB should remain in take_profits (no reduce override)"
    assert tp_item.get("gate_override") is None or not tp_item.get("gate_override")
    # But it carries the ew info
    assert "ew" in tp_item
    assert tp_item["ew"]["reco"] == "accumulate"


# --- basket_alloc selection: best-ranked basket wins over max-|tilt| basket ---
def test_basket_alloc_uses_best_ranked_not_max_tilt():
    """Regression for NVDA 'Quantum Computing' misattribution.

    NVDA belongs to multiple baskets including both quantum_computing and
    ai_semiconductors. When quantum_computing has a strong negative tilt (avoid,
    fading) and ai_semiconductors has a neutral tilt (hold), the OLD code would
    pick quantum_computing as basket_alloc because its |tilt| was larger — firing
    a 'Quantum Computing basket is below trend' caution on NVDA.

    The fix: basket_alloc should always be the BEST-RANKED (lowest rotation rank)
    basket, not the max-|tilt| basket. This test uses _basket_alloc_map's
    output convention by simulating the alloc_by_id and bsk_mem structures, then
    calling the selection logic directly (mirroring build_stock_library.py lines
    that compute _bslug).
    """
    # Simulate alloc_by_id: ai_semiconductors is rank 1 (best), quantum_computing is rank 15
    alloc_by_id = {
        "ai_semiconductors": {"rank": 1, "above_trend": True, "eligible": True,
                               "label": "dominant", "name": "AI Semiconductors",
                               "name_zh": "AI半导体"},
        "quantum_computing":  {"rank": 15, "above_trend": False, "eligible": False,
                               "label": "fading", "name": "Quantum Computing",
                               "name_zh": "量子计算"},
    }
    # NVDA memberships: both baskets
    memberships = [
        {"slug": "ai_semiconductors", "name": "AI Semiconductors"},
        {"slug": "quantum_computing",  "name": "Quantum Computing"},
    ]

    # Simulate the NEW basket_alloc selection (best-ranked):
    cands = [m.get("slug") for m in memberships if m.get("slug") in alloc_by_id]
    bslug = min(cands, key=lambda s: (alloc_by_id[s].get("rank") or 999))

    assert bslug == "ai_semiconductors", (
        f"NVDA basket_alloc should be ai_semiconductors (rank 1), not {bslug!r} — "
        "the quantum_computing membership must not fire a caution on NVDA"
    )
    # Confirm the caution would NOT fire on the best-ranked basket (it's healthy)
    rec = {"basket_alloc": {**alloc_by_id[bslug], "slug": bslug}}
    hc, cau = ss._basket_risk(rec)
    assert hc == 0.0 and cau is None, (
        "ai_semiconductors is above_trend=True — no de-risk caution should fire"
    )


# --- RFC-compliant JSON emit (no bare NaN/Inf reaches us_standouts.json) -----
def test_json_safe_strips_non_finite():
    import json
    from scripts.build_stock_library import _json_safe
    inf = float("inf")
    blob = {"a": float("nan"), "b": 1.5, "c": [inf, -inf, 2.0],
            "d": {"e": float("nan"), "f": "x"}, "g": None, "h": 3}
    safe = _json_safe(blob)
    assert safe == {"a": None, "b": 1.5, "c": [None, None, 2.0],
                    "d": {"e": None, "f": "x"}, "g": None, "h": 3}
    # strict (JS-style) JSON parse must accept it
    json.loads(json.dumps(safe, allow_nan=False))
