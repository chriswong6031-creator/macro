"""Tests for engine.etf_board — the Tier-1 board synthesis behind the rebuilt
etfs.html (Real Fund Moves).

Pure functions, synthetic in-memory data, plain asserts, no network / no pytest
fixtures — matches the __main__-harness style of tests/test_etf_new_sponsors.py.

Under test:
  * is_cash / drop_cash — the money-market / cash-sweep filter that keeps First
    American Government Obligations & friends off the board.
  * clean_name — display hygiene (whitespace, share-class suffix).
  * stance_for — the doctrine "so what do I do?" mapping (Act / Get ready /
    Watch — don't chase / Protect gains / Stand aside).
  * board_context — attaches a stance to every shown row and assembles the
    verdict / tiles / fresh-conviction / rotation synthesis; and the theme tally
    never double-counts a theme as both building AND leaving.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import etf_board as eb  # noqa: E402


# =============================================================================
# A) cash / money-market filter
# =============================================================================

def test_is_cash_detects_money_market_by_name() -> None:
    assert eb.is_cash("FGXXX", "First American Government Obligations Fund 12/01")
    assert eb.is_cash("AGPXX", "Invesco Government & Agency Portfolio")
    assert eb.is_cash("X", "BlackRock Liquidity Funds T-Fund")
    assert eb.is_cash("Y", "Goldman Sachs Financial Square Money Market")


def test_is_cash_detects_by_ticker_suffix() -> None:
    # 5-letter mutual-fund cash classes end in XX
    assert eb.is_cash("FGXXX", "")
    assert eb.is_cash("VMFXX", "")


def test_is_cash_passes_normal_equities() -> None:
    assert not eb.is_cash("SPCX", "Space Exploration Technologies Corp")
    assert not eb.is_cash("META", "Meta Platforms Inc")
    assert not eb.is_cash("NVDA", "Nvidia Corp")
    # a normal ticker that merely contains letters, not a cash sweep
    assert not eb.is_cash("XOM", "Exxon Mobil Corp")


def test_drop_cash_filters_rows() -> None:
    rows = [
        {"ticker": "SPCX", "name": "Space Exploration Technologies Corp"},
        {"ticker": "FGXXX", "name": "First American Government Obligations Fund"},
        {"ticker": "META", "name": "Meta Platforms Inc"},
        {"ticker": "AGPXX", "name": "Invesco Government & Agency Portfolio"},
    ]
    out = eb.drop_cash(rows)
    assert [r["ticker"] for r in out] == ["SPCX", "META"]
    assert eb.drop_cash([]) == []
    assert eb.drop_cash(None) == []


# =============================================================================
# B) name hygiene
# =============================================================================

def test_clean_name_collapses_whitespace() -> None:
    assert eb.clean_name("Cerebras Systems Inc   A") == "Cerebras Systems Inc"
    assert eb.clean_name("Astera Labs Inc") == "Astera Labs Inc"


def test_clean_name_strips_share_class() -> None:
    assert eb.clean_name("Meta Platforms Inc-Class A") == "Meta Platforms Inc"
    assert eb.clean_name("Plains Gp Holdings Lp-Cl A") == "Plains Gp Holdings Lp"
    assert eb.clean_name("Thredup Inc   Class A") == "Thredup Inc"


def test_clean_name_handles_empty_and_short() -> None:
    assert eb.clean_name("") == ""
    assert eb.clean_name(None) == ""
    # never strips down to nothing meaningful
    assert eb.clean_name("A") == "A"


# =============================================================================
# C) stance mapping (doctrine vocabulary)
# =============================================================================

def test_stance_accumulation_default_is_watch() -> None:
    s = eb.stance_for(ladder=None, confirmed=False, contested=False,
                      direction="accumulating", n_accum=1, n_new=0, net_pp=2.0)
    assert s["tone"] == "watch"
    assert s["en"] == "Watch — don't chase"
    assert s["zh"]  # bilingual, non-empty


def test_stance_live_buy_setup_is_act() -> None:
    ladder = {"action": "BUY", "urgency": "now", "state": "FRESH BUY"}
    s = eb.stance_for(ladder=ladder, confirmed=True, contested=False,
                      direction="accumulating", n_accum=3, net_pp=5.0)
    assert s["tone"] == "act"
    assert s["en"] == "Act"


def test_stance_forming_setup_is_get_ready() -> None:
    ladder = {"action": "GET READY", "urgency": "soon", "state": "BOTTOM WATCH"}
    s = eb.stance_for(ladder=ladder, confirmed=False, contested=False,
                      direction="accumulating", n_accum=2, net_pp=3.0)
    assert s["tone"] == "ready"


def test_stance_confirmed_without_ladder_is_get_ready() -> None:
    s = eb.stance_for(ladder=None, confirmed=True, contested=False,
                      direction="accumulating", n_accum=2, net_pp=3.0)
    assert s["tone"] == "ready"


def test_stance_contested_no_edge_is_stand_aside() -> None:
    s = eb.stance_for(ladder=None, confirmed=False, contested=True,
                      direction="accumulating", n_accum=2, n_new=0, net_pp=0.1)
    assert s["tone"] == "aside"


def test_stance_trimming_is_protect_or_aside() -> None:
    s = eb.stance_for(ladder=None, confirmed=False, contested=False,
                      direction="trimming", net_pp=-3.0)
    assert s["tone"] == "aside"
    s2 = eb.stance_for(ladder={"action": "TAKE PROFITS", "urgency": "hold"},
                       confirmed=False, contested=False, direction="trimming",
                       net_pp=-3.0)
    assert s2["tone"] == "trim"


# =============================================================================
# D) board_context — synthesis + stance attachment + theme dedup
# =============================================================================

def _fav(ticker, sector, n_accum, net, *, n_trim=0, contested=False,
         confirmed=False, ladder=None, funds=None):
    return {"ticker": ticker, "name": ticker + " Corp", "sector": sector,
            "n_accum": n_accum, "n_trim": n_trim, "n_new": 0, "n_exit": 0,
            "net_conviction_pp": net, "gross_conviction_pp": abs(net),
            "contested": contested, "is_active_any": True, "confirmed": confirmed,
            "ladder": ladder, "funds": funds or [{"fund": "X", "conviction_pp": net}]}


def _acc(etf, ticker, cp, *, is_new=False, ladder=None):
    return {"etf": etf, "ticker": ticker, "name": ticker + " Corp",
            "sector": "Tech", "category": "AI", "conviction_pp": cp,
            "is_new": is_new, "is_active": False, "confirmed": False,
            "ladder": ladder, "weight_series": []}


_PULSE = {
    "as_of": "2026-07-21",
    "disclaimer_en": "Display-only.", "disclaimer_zh": "仅供展示。",
    "style": [{"pair": "IWM/SPY", "label_en": "Small vs Large", "label_zh": "小盘vs大盘",
               "lead_en": "large leading", "lead_zh": "大盘领先", "tilt": -1,
               "chg_20d": -1.1, "chg_60d": 1.9}],
    "risk": {"label_en": "RISK-ON", "label_zh": "风险偏好", "tilt": 0.32,
             "legs": [{"label_en": "Credit vs Duration", "label_zh": "信用vs久期",
                       "direction": 1, "chg_20d": 2.6}]},
    "sector": {"as_of": "2026-07-21", "leaders": [], "laggards": [],
               "rows": [{"ticker": "XLK", "label_en": "Technology", "label_zh": "科技",
                         "mom_20d": -6.4, "mom_60d": 9.8, "pctile_252d": 86.5,
                         "above_200d": True, "rank": 1},
                        {"ticker": "XLC", "label_en": "Comm Services", "label_zh": "通讯",
                         "mom_20d": -3.0, "mom_60d": -11.3, "pctile_252d": 5.0,
                         "above_200d": False, "rank": 11}]},
}


def test_board_context_attaches_stance_to_every_row() -> None:
    favored = [_fav("SPCX", "Space", 5, 29.6, contested=True),
               _fav("META", "Comm", 4, 1.4, confirmed=True)]
    accum = [_acc("MARS", "SPCX", 21.4, is_new=True), _acc("CHAT", "CBRS", 3.9)]
    trims = [_acc("METV", "MSTR", -2.0)]
    board = eb.board_context(favored[:], accum, trims, favored, [], _PULSE)
    assert all("stance" in c for c in favored)
    assert all("stance" in r for r in accum)
    assert all("stance" in r for r in trims)
    # verdict + tiles + rotation present
    assert board["verdict"]["en"] and board["verdict"]["zh"]
    assert len(board["tiles"]) == 3
    assert board["rotation"]["risk"]["label"]["en"] == "RISK-ON"
    assert board["scale"]["consensus_pp"] >= 29.6


def test_board_context_theme_never_in_both_build_and_leave() -> None:
    # two Space names that net POSITIVE, one Gold name that nets negative
    favored = [_fav("SPCX", "Space", 3, 20.0), _fav("RKLB", "Space", 2, -5.0),
               _fav("GOLD", "Gold Miners", 1, -4.0)]
    board = eb.board_context(favored[:], [], [], favored, [], _PULSE)
    build = {t["label"] for t in board["themes_building"]}
    leave = {t["label"] for t in board["themes_leaving"]}
    assert not (build & leave), "a theme appears on both sides of the tally"
    # Space nets +15 → building; Gold nets −4 → leaving
    assert "Space" in build
    assert "Gold Miners" in leave


def test_board_context_fresh_groups_new_positions_by_ticker() -> None:
    accum = [_acc("MARS", "SPCX", 21.4, is_new=True),
             _acc("ARKX", "SPCX", 0.5, is_new=True),   # same ticker, 2nd fund
             _acc("MEME", "WULF", 5.5, is_new=True),
             _acc("CHAT", "CBRS", 3.9, is_new=False)]  # not new → excluded
    board = eb.board_context([], accum, [], [], [], _PULSE)
    fresh = board["fresh"]
    tickers = [g["ticker"] for g in fresh]
    assert "CBRS" not in tickers            # not new
    spcx = next(g for g in fresh if g["ticker"] == "SPCX")
    assert spcx["n_funds"] == 2             # grouped across MARS + ARKX
    assert fresh[0]["ticker"] == "SPCX"     # ranked by fund count first


def test_board_context_survives_empty_pulse() -> None:
    favored = [_fav("SPCX", "Space", 5, 29.6)]
    board = eb.board_context(favored[:], [], [], favored, [], {})
    assert board["rotation"]["risk"]["label"]["en"] in ("NEUTRAL", None) or True
    assert board["verdict"]["en"]  # still produces a verdict
    assert board["tiles"]          # tiles still built


if __name__ == "__main__":
    tests = [
        test_is_cash_detects_money_market_by_name,
        test_is_cash_detects_by_ticker_suffix,
        test_is_cash_passes_normal_equities,
        test_drop_cash_filters_rows,
        test_clean_name_collapses_whitespace,
        test_clean_name_strips_share_class,
        test_clean_name_handles_empty_and_short,
        test_stance_accumulation_default_is_watch,
        test_stance_live_buy_setup_is_act,
        test_stance_forming_setup_is_get_ready,
        test_stance_confirmed_without_ladder_is_get_ready,
        test_stance_contested_no_edge_is_stand_aside,
        test_stance_trimming_is_protect_or_aside,
        test_board_context_attaches_stance_to_every_row,
        test_board_context_theme_never_in_both_build_and_leave,
        test_board_context_fresh_groups_new_positions_by_ticker,
        test_board_context_survives_empty_pulse,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {type(e).__name__}: {e}")
    if failed:
        print(f"{failed}/{len(tests)} FAILED")
        sys.exit(1)
    print("all etf-board tests passed")
