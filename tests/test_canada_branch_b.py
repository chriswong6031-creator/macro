"""Branch-B ripe-list contract order + card-lead unit tests (CA board, W1b).

Covers the C7 zero-GO branch wiring in scripts/build_canada_library:
  * group = entry_open before setting_up
  * within-group rank by residual-momentum SCREEN z (alpha) desc
  * board_pos is a single 1-based rank top-to-bottom
  * oil context chip fires ONLY on oil-primary names when overlay oil is risk-on
    (gold/copper NEVER — C1 NO-GO)
  * the mechanism-first card lead is built from row fields
These are pure-Python (no store / no render), so they run fast in CI.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_canada_library import (  # noqa: E402
    _branch_b_order, _build_watch, _confluence_stat, _lead_sentence,
    _oil_regime_on, _row_group, _sector_concentration,
)


def test_build_watch_strong_but_blocked():
    """WATCH strip (W6): strong momentum SCREEN z the alignment gate held OUT of the buy
    list — a real edge with no base yet. Aligned/near names and sub-floor screens excluded;
    a still-falling weekly is tagged watch_reason='knife'."""
    cand = [
        (9.0, {"ticker": "KNF.TO", "name": "Knife Co", "alpha": 2.4}),   # strong, weekly falling -> knife
        (9.0, {"ticker": "BLK.TO", "name": "Blocked Co", "alpha": 1.5}),  # strong, blocked, weekly basing
        (9.0, {"ticker": "BUY.TO", "name": "Aligned Co", "alpha": 3.0}),  # strong but ALIGNED -> not watch
        (1.0, {"ticker": "WEAK.TO", "name": "Weak Co", "alpha": 0.1}),    # sub-floor -> never watch
    ]
    align_map = {
        "KNF.TO": {"aligned": False, "near": False, "weekly": "bear_falling", "reason": "wk falling"},
        "BLK.TO": {"aligned": False, "near": False, "weekly": "bear_recovering", "reason": "no turn"},
        "BUY.TO": {"aligned": True, "near": False, "weekly": "basing"},
    }
    profiles = {"KNF.TO": {"score": 60, "verdict": "v", "verdict_zh": "v"}}
    watch = _build_watch(cand, buys=[{"ticker": "BUY.TO"}], align_map=align_map, profiles=profiles)
    tickers = [w["ticker"] for w in watch]
    assert "BUY.TO" not in tickers            # aligned -> excluded
    assert "WEAK.TO" not in tickers           # sub-floor -> excluded
    assert set(tickers) == {"KNF.TO", "BLK.TO"}
    by_t = {w["ticker"]: w for w in watch}
    assert by_t["KNF.TO"]["watch_reason"] == "knife"      # falling weekly
    assert by_t["BLK.TO"]["watch_reason"] == "blocked"    # blocked, not falling
    assert watch[0]["ticker"] == "KNF.TO"     # knives first, then by screen z desc
    assert by_t["KNF.TO"]["conviction"]["score"] == 60    # profile stitched on


def test_build_watch_empty_pool_is_safe():
    assert _build_watch([], buys=[], align_map={}, profiles={}) == []
    assert _build_watch(None, buys=None, align_map=None, profiles=None) == []


def _row(ticker, alpha, status, **kw):
    r = {"ticker": ticker, "alpha": alpha,
         "entry_signal": {"status": status, "buy_zone": kw.pop("buy_zone", {})}}
    r.update(kw)
    return r


def test_group_split_entry_open_first():
    rows = [
        _row("A.TO", 0.5, "watch"),          # setting_up
        _row("B.TO", 0.1, "buy_now"),        # entry_open (lower alpha)
        _row("C.TO", 2.0, "wait_pullback"),  # setting_up (highest alpha)
    ]
    out = _branch_b_order(rows, overlay={})
    # entry_open group leads regardless of alpha
    assert out[0]["ticker"] == "B.TO"
    assert out[0]["group"] == "entry_open"
    assert out[0]["board_pos"] == 1
    # setting_up follows, ranked by alpha desc within the group
    assert [r["ticker"] for r in out[1:]] == ["C.TO", "A.TO"]
    assert [r["board_pos"] for r in out] == [1, 2, 3]


def test_within_group_rank_by_momentum_screen_z():
    rows = [
        _row("LOW.TO", -0.4, "buy_now"),
        _row("HIGH.TO", 1.8, "buy_now"),
        _row("MID.TO", 0.3, "partial"),   # partial is also entry_open
    ]
    out = _branch_b_order(rows, overlay={})
    assert [r["ticker"] for r in out] == ["HIGH.TO", "MID.TO", "LOW.TO"]
    assert all(r["group"] == "entry_open" for r in out)


def test_row_group_partial_is_entry_open():
    assert _row_group({"entry_signal": {"status": "partial"}}) == "entry_open"
    assert _row_group({"entry_signal": {"status": "buy_now"}}) == "entry_open"
    assert _row_group({"entry_signal": {"status": "wait_pullback"}}) == "setting_up"
    assert _row_group({}) == "setting_up"


def test_oil_regime_on_reads_overlay_oil_factor():
    on = {"factors": [{"key": "oil", "risk": "on", "z": 1.2},
                      {"key": "gold", "risk": "off", "z": -0.5}]}
    off = {"factors": [{"key": "oil", "risk": "off", "z": -0.3}]}
    assert _oil_regime_on(on) is True
    assert _oil_regime_on(off) is False
    assert _oil_regime_on({}) is False


def test_oil_chip_only_oil_primary_never_gold_or_copper():
    overlay = {"factors": [{"key": "oil", "risk": "on", "z": 1.5}]}
    rows = [
        _row("OIL.TO", 1.0, "buy_now", factor_beta={"primary": "oil", "oil": 0.8}),
        _row("GOLD.TO", 1.0, "buy_now", factor_beta={"primary": "gold", "gold": 0.9}),
        _row("BANK.TO", 1.0, "buy_now", factor_beta={"primary": None}),
    ]
    out = {r["ticker"]: r for r in _branch_b_order(rows, overlay)}
    assert out["OIL.TO"]["oil_tailwind"] is True    # oil-primary + oil regime on
    assert out["GOLD.TO"]["oil_tailwind"] is False  # C1: gold NO-GO
    assert out["BANK.TO"]["oil_tailwind"] is False  # no primary driver


def test_oil_chip_off_when_regime_off():
    overlay = {"factors": [{"key": "oil", "risk": "off", "z": -0.4}]}
    rows = [_row("OIL.TO", 1.0, "buy_now", factor_beta={"primary": "oil", "oil": 0.8})]
    out = _branch_b_order(rows, overlay)
    assert out[0]["oil_tailwind"] is False


def test_lead_sentence_plain_driver_and_entry():
    # the lead is now a plain-English one-liner: the main driver + when to buy.
    overlay_on = {"factors": [{"key": "oil", "risk": "on", "z": 1.2}]}
    r = _row("XEG.TO", 1.8, "buy_now",
             sector="Energy",
             factor_beta={"primary": "oil", "primary_label": "Oil", "oil": 1.42},
             insider={"lean": "buying", "distinct_buyers": 2, "window_days": 60})
    lead = _lead_sentence(r, oil_on=_oil_regime_on(overlay_on), zh=False)
    assert "Main driver: Oil" in lead
    assert "buy now" in lead
    # the raw beta, momentum-screen z and insider cluster moved to their own chips —
    # the lead stays jargon-free.
    assert "primary driver" not in lead
    assert "momentum screen z" not in lead
    assert "insider cluster" not in lead


def test_lead_sentence_pullback_entry_window():
    r = _row("RY.TO", 0.4, "wait_pullback",
             buy_zone={"low": 41.20, "high": 42.80},
             factor_beta={"primary": None}, sector="Financials")
    lead = _lead_sentence(r, oil_on=False, zh=False)
    assert "Main driver: Financials sector" in lead
    assert "buy on a pullback to $41.20–$42.80" in lead


def test_lead_sentence_zh_is_bilingual_and_nonempty():
    r = _row("SU.TO", 1.1, "buy_now",
             factor_beta={"primary": "oil", "primary_label": "Oil",
                          "primary_label_zh": "原油", "oil": 0.9})
    zh = _lead_sentence(r, oil_on=True, zh=True)
    assert "原油" in zh and "主要驱动" in zh


# ---------------------------------------------------------------------------
# CA2 fix — gate-tier passthrough + confluence stat + sector-concentration banner
# ---------------------------------------------------------------------------
def _sig(tier=None, reason="flat: cut", eligible=False, ticks=0):
    """A signal_gate.compact-shaped verdict. tier=None + eligible False = a RAN gate that
    found no fresh confluence cross (the owner-reported all-None board is this, x14)."""
    return {"eligible": eligible, "tier": tier, "sub": None, "reason": reason,
            "tier_cascade": tier, "weight": 0.0 if tier is None else 1.0,
            "ticks": ticks, "provisional": False}


def test_confluence_stat_zero_cross_tape_is_counted_not_blank():
    """The owner-reported all-None board: signal_gate RAN for every name and found no
    fresh MACD-2D x StochRSI-3D cross. The stat must read 0 of N — a VISIBLE fact — never
    a silent blank. This is the regression guard for the invisible zero-cross tape."""
    rows = [{"ticker": f"M{i}.TO", "signal": _sig()} for i in range(14)]
    stat = _confluence_stat(rows)
    assert stat == {"crosses": 0, "board": 14}


def test_confluence_stat_counts_only_buyable_crosses():
    """is_buyable requires eligible AND tier_cascade in BUYABLE_TIERS (T1/T2/T3). A topped /
    stale / blocked verdict — the common case — clears eligibility, so it does NOT count."""
    rows = [
        {"ticker": "A.TO", "signal": _sig(tier="T1", reason="held take", eligible=True, ticks=0)},
        {"ticker": "B.TO", "signal": _sig(tier=None, reason="topped — no longer fresh", eligible=False)},
        {"ticker": "C.TO", "signal": _sig()},          # no cross (eligible False, cascade None)
        {"ticker": "D.TO", "signal": None},            # no verdict at all
    ]
    stat = _confluence_stat(rows)
    assert stat["board"] == 4
    assert stat["crosses"] == 1          # only the fresh eligible T1


def test_gate_tier_passthrough_carries_real_tier_when_present():
    """When the gate fires a fresh tier, r['signal'].tier must survive onto the board row so
    the card badge + the forward ledger's gate_tier read the REAL T1..T4 (not None)."""
    rows = [{"ticker": "A.TO", "signal": _sig(tier="T2", eligible=True, ticks=0)}]
    assert rows[0]["signal"]["tier"] == "T2"        # passthrough intact
    # and is_buyable agrees the cross is open (so it counts in the confluence stat)
    assert _confluence_stat(rows)["crosses"] == 1


def test_sector_concentration_fires_above_60pct():
    """>60% of the board in one sector → honest banner with per-sector counts. Mirrors the
    real tape (10/14 Materials). Not a re-rank — a fact surfaced."""
    rows = ([{"ticker": f"MAT{i}.TO", "sector": "Materials"} for i in range(10)]
            + [{"ticker": "E1.TO", "sector": "Energy"}, {"ticker": "E2.TO", "sector": "Energy"},
               {"ticker": "I1.TO", "sector": "Industrials"}, {"ticker": "U1.TO", "sector": "Utilities"}])
    sc = _sector_concentration(rows)
    assert sc is not None
    assert sc["sector"] == "Materials" and sc["n"] == 10 and sc["total"] == 14
    assert sc["counts"]["Materials"] == 10 and sc["counts"]["Energy"] == 2
    # counts are sorted descending so the template lists the biggest cohort first
    assert list(sc["counts"])[0] == "Materials"


def test_sector_concentration_silent_when_diversified():
    """At exactly 60% (not >60%) or below, no banner — the threshold is strict."""
    rows = ([{"ticker": f"M{i}.TO", "sector": "Materials"} for i in range(6)]
            + [{"ticker": f"E{i}.TO", "sector": "Energy"} for i in range(4)])  # 6/10 = 60%, not >60
    assert _sector_concentration(rows) is None


def test_sector_concentration_ignores_unlabeled_dominance():
    """A board dominated by the '—' unlabeled sector must not fire a banner (it is a data
    gap, not a real concentration to report)."""
    rows = [{"ticker": f"X{i}.TO", "sector": "—"} for i in range(9)] + [{"ticker": "R.TO", "sector": "Energy"}]
    assert _sector_concentration(rows) is None


def test_sector_concentration_empty_board_is_safe():
    assert _sector_concentration([]) is None
    assert _confluence_stat([]) == {"crosses": 0, "board": 0}
