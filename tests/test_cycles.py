"""Cycle engine tests on synthetic fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import (  # noqa: E402
    _MACD_APPROACH_MAX_BARS,
    _EQ_BEARISH, _EQ_BULLISH, _eq_freshness, _eq_grade, _eq_proximity, analyze,
    bottom_confidence, bottom_confidence_fields, market_vix_context, washout,
    cycle_state, early_signals, entry_quality, entry_quality_fields, entry_timing,
    find_troughs, ladder_state, mtf_snapshot, signal_age, signal_age_fields,
    STATE_DISPLAY, _overextended,
)

IDX = pd.bdate_range("2020-01-01", periods=520)


def synth_cycles(period: int = 40, crest_at: float = 0.5, n: int = 520) -> pd.Series:
    """Sawtooth-ish cycles with adjustable crest position + uptrend + noise."""
    rng = np.random.default_rng(3)
    t = np.arange(n)
    phase = (t % period) / period
    cyc = np.where(phase < crest_at, phase / crest_at, (1 - phase) / (1 - crest_at))
    price = 100 * np.exp(0.0004 * t) * (1 + 0.06 * cyc) + rng.normal(0, 0.15, n)
    return pd.Series(price, index=pd.bdate_range("2020-01-01", periods=n))


def test_trough_spacing() -> None:
    c = synth_cycles(period=40)
    troughs = find_troughs(c)
    gaps = np.diff([c.index.get_loc(t) for t in troughs])
    assert 30 <= np.median(gaps) <= 50, f"median gap {np.median(gaps)}"


def test_translation_right() -> None:
    c = synth_cycles(period=40, crest_at=0.75)
    st = cycle_state(c)
    assert st["translation"] == "right", st["translation"]


def test_translation_left() -> None:
    c = synth_cycles(period=40, crest_at=0.25)
    st = cycle_state(c)
    assert st["translation"] == "left", st["translation"]


def test_failed_cycle_flag() -> None:
    c = synth_cycles(period=40)
    # force a break below the last cycle low
    c.iloc[-3:] = c.min() * 0.95
    st = cycle_state(c)
    assert st["failed_cycle"] is True


def test_ladder_states_sane() -> None:
    c = synth_cycles(period=40)
    st = ladder_state(cycle_state(c), mtf_snapshot(c))
    assert st["state"] in ("BOTTOM WATCH", "TURN SIGNALED", "FRESH BUY", "RALLY ON",
                           "TOP WATCH", "ROLLING OVER", "DECLINE", "COUNTERTREND BOUNCE")
    assert -100 <= st["score"] <= 100
    assert st["why"] and st["next"]


def test_macd_cross_eta_is_bounded_and_in_days() -> None:
    """The MACD "days to cross" ETA is a short-horizon extrapolation, not a
    runaway countdown: it must never exceed the near-term bar cap (the old
    clip-to-99 surfaced an absurd "≈99d to ↑cross" on COIN's 3-Day card), and
    it must be reported in trading days, not raw timeframe bars."""
    bar_days = {"D": 1, "3D": 3, "W": 5, "M": 21}
    seen_eta = False
    for seed in range(60):
        r = np.random.default_rng(seed)
        n = int(r.integers(220, 1100))
        t = np.arange(n)
        price = (100 * np.exp(0.0003 * t) * (1 + 0.05 * np.sin(t / r.uniform(8, 60)))
                 + r.normal(0, 0.4, n).cumsum())
        s = pd.Series(np.abs(price) + 5, index=pd.bdate_range("2018-01-01", periods=n))
        mtf = mtf_snapshot(s, "crypto" if seed % 2 else "equity")
        for tf, st in mtf.items():
            btc = st.get("macd_bars_to_cross") if st else None
            dtc = st.get("macd_days_to_cross") if st else None
            approaching = st and (st.get("macd_approaching_up") or st.get("macd_approaching_dn"))
            if btc is None:
                assert not approaching and dtc is None
                continue
            seen_eta = True
            assert approaching, f"{tf}: ETA set without an approaching flag"
            assert 0 < btc <= _MACD_APPROACH_MAX_BARS, f"{tf}: bars {btc} over cap"
            assert dtc == round(btc * bar_days[tf]), f"{tf}: days {dtc} != bars*{bar_days[tf]}"
    assert seen_eta, "fixture never exercised an approaching cross"


def test_decline_on_breakdown() -> None:
    c = synth_cycles(period=40)
    c.iloc[-15:] = np.linspace(float(c.iloc[-16]), float(c.min() * 0.85), 15)
    st = ladder_state(cycle_state(c), mtf_snapshot(c))
    assert st["state"] in ("DECLINE", "ROLLING OVER"), st["state"]


def test_signal_age_detects_recent_cross() -> None:
    """A series engineered to flip its state in the last few bars should report
    a small, non-capped age and name the state it switched away from."""
    c = synth_cycles(period=40)
    cur = ladder_state(cycle_state(c), mtf_snapshot(c))["state"]
    age = signal_age(c, cur)
    assert age, "signal_age returned empty on a 520-bar series"
    assert 0 <= age["days"] <= 45
    # synthetic data isn't a 45-day-stable trend, so it should find a real cross
    assert age["capped"] is False
    assert age["prev_state"] is not None and age["prev_state"] != cur


def test_signal_age_contract_holds() -> None:
    """Whatever the lookback, the two branches stay self-consistent: a capped
    result reports exactly max_lookback days with no prior state/date; an
    uncapped one reports an in-range age, a different prior state, and a date."""
    c = synth_cycles(period=40)
    cur = ladder_state(cycle_state(c), mtf_snapshot(c))["state"]
    for lb in (1, 3, 45):
        age = signal_age(c, cur, max_lookback=lb)
        assert age, f"empty at max_lookback={lb}"
        if age["capped"]:
            assert age["days"] == lb
            assert age["prev_state"] is None and age["date"] is None
        else:
            assert 0 <= age["days"] < lb
            assert age["prev_state"] is not None and age["prev_state"] != cur
            assert age["date"] is not None


def test_signal_age_thin_history() -> None:
    """Under the history floor, signal_age bows out cleanly (no crash)."""
    c = synth_cycles(period=40, n=120)
    assert signal_age(c, "FRESH BUY") == {}


def test_signal_age_fields_prose() -> None:
    fresh = signal_age_fields("FRESH BUY", 80,
                              {"days": 3, "capped": False, "prev_state": "TURN SIGNALED",
                               "date": "2026-06-05"})
    assert "3 trading days ago" in fresh["age_line"]
    assert "3天前" in fresh["age_short_zh"] or "3天前" in fresh["age_line_zh"]
    assert fresh["strength"] == "strong" and "+80" in fresh["age_line"]
    today = signal_age_fields("FRESH BUY", 80, {"days": 0, "capped": False,
                                                "prev_state": None, "date": "2026-06-13"})
    assert "today" in today["age_line"] and today["age_short"] == "today"
    capped = signal_age_fields("RALLY ON", 55, {"days": 45, "capped": True,
                                                "prev_state": None, "date": None})
    assert "45+" in capped["age_line"] and "established" in capped["age_line"]


def test_analyze_attaches_age() -> None:
    res = analyze(synth_cycles(period=40))
    lad = res["ladder"]
    assert "age_days" in lad and "age_line" in lad and "age_short" in lad
    assert lad["state"] in lad["age_line"] or \
        any(w in lad["age_line"] for w in ("BUY", "UPTREND", "TOPPING", "BOTTOM",
                                           "DOWNTREND", "HIGH", "LOW", "BOUNCE"))


def test_eq_proximity_peaks_near_the_low() -> None:
    """The dominant lever: proximity must peak just above the pivot and decay as
    price runs away — and a broken pivot (below the low) is discounted."""
    f = _eq_proximity
    assert f(0.01, True) > f(0.10, True) > f(0.20, True)   # nearer the low = higher
    assert f(0.02, True) >= 0.9                              # sweet spot near 1
    assert f(-0.10, True) <= 0.2                             # deep below pivot = knife
    # short side mirrors: 'near the high' (small negative pct) scores high
    assert f(-0.01, False) > f(-0.10, False)
    # the curve must be CONTINUOUS — no cliff at any breakpoint (esp. -0.03)
    xs = [x / 1000 for x in range(-90, 260)]
    for a, b in zip(xs, xs[1:]):
        assert abs(f(b, True) - f(a, True)) < 0.05, f"jump near {b:.3f}"


def test_eq_grade_bands() -> None:
    assert _eq_grade(75)[0] == "strong"
    assert _eq_grade(-45)[0] == "solid"
    assert _eq_grade(20)[0] == "light"
    assert _eq_grade(5)[0] == "minimal"


def test_eq_sign_anchored_to_state() -> None:
    """The score's SIGN must follow the ladder state, never contradict it."""
    c = synth_cycles(period=40)
    cyc = cycle_state(c)
    mtf = mtf_snapshot(c)
    early = early_signals(c, cyc, mtf)
    reg = {"regime": "neutral"}
    for st in _EQ_BULLISH:
        eq = entry_quality(c, cyc, mtf, early, reg, state=st)
        assert eq and eq["score"] >= 0, f"{st} should be >=0, got {eq}"
    for st in _EQ_BEARISH:
        eq = entry_quality(c, cyc, mtf, early, reg, state=st)
        assert eq and eq["score"] <= 0, f"{st} should be <=0, got {eq}"


def test_eq_every_state_classified() -> None:
    """Every displayed ladder state is bullish or bearish (no silent fallback)."""
    for st in STATE_DISPLAY:
        assert st in _EQ_BULLISH or st in _EQ_BEARISH, f"{st} unclassified"


def test_eq_thin_history_bows_out() -> None:
    c = synth_cycles(period=40, n=120)
    assert entry_quality(c, cycle_state(c) or {"x": 1}, {"D": {}}, {}, {"regime": "neutral"}) == {}


def test_eq_fields_and_analyze() -> None:
    fields = entry_quality_fields({"score": 58.0, "pct_from_low": 4.2})
    assert fields["eq_dir"] == "up" and "+58" in fields["eq_badge"]
    assert "drawdown" in fields["eq_tip"] and "return forecast" in fields["eq_tip"]
    neg = entry_quality_fields({"score": -40.0, "pct_from_low": 1.0})
    assert neg["eq_dir"] == "down" and neg["eq_badge"].startswith("▼")
    res = analyze(synth_cycles(period=40))
    assert "eq_score" in res["ladder"] and -100 <= res["ladder"]["eq_score"] <= 100


# ----------------------------------------------------- extension / late-cross ----

def _extended_snapshot(rsi_d: float, rsi_3: float, rsi_w: float,
                       above_ma10: bool = True, weekly_cross: bool = False,
                       dc_phase: str = "stretched", dc_day: int = 68,
                       curl_dn: bool = False) -> tuple[dict, dict]:
    """SNDK-shaped cycle+mtf snapshot: a late, stretched daily cycle that printed
    a swing low and reclaimed the 10-day average with the daily MACD just crossed
    up — i.e. the cand-confirmed buy path. The RSI levels are the knob under test.
    `dc_phase`/`dc_day` select cycle position; `curl_dn` arms the daily roll-over
    flag (the HWM case: late, not overbought, but momentum already turning down)."""
    cyc = {
        "dc_day": dc_day, "dc_band": (36, 42), "dc_early": 12, "dc_phase": dc_phase,
        "last_dcl": "2026-03-01", "dcl_price": 527.33,
        "cand_dcl": "2026-05-18", "cand_price": 1333.01, "cand_swing": True, "cand_age": 18,
        "cand_depth_pct": 9.0,
        "translation": "right", "failed_cycle": False, "failed_age": None,
        "swing_low": True, "above_ma10": above_ma10, "ma10_rising": True,
        "ic_week": 45, "ic_band": (16, 26), "ic_phase": "overdue", "ic_failed": False,
        "n_troughs": 5,
    }

    def tf(rsi: float, cross_up: bool = False, mcurl_dn: bool = False) -> dict:
        return {"rsi14": rsi, "rsi5": rsi, "stoch": 55.0, "macd_pos": True,
                "macd_cross_up": cross_up, "macd_cross_dn": False,
                "macd_approaching_up": False, "macd_approaching_dn": False,
                "macd_curl_up": False, "macd_curl_dn": mcurl_dn, "macd_bars_to_cross": None,
                "stoch_cross_up": False, "stoch_cross_dn": False}

    mtf = {"D": tf(rsi_d, cross_up=True, mcurl_dn=curl_dn), "3D": tf(rsi_3),
           "W": tf(rsi_w, cross_up=weekly_cross)}
    return cyc, mtf


def test_extension_gate_routes_overbought_buy_to_top_watch() -> None:
    """The SNDK case: a stretched, extended fresh-cross that's overbought across
    all timeframes must NOT read as a buy — it routes to TOP WATCH ('don't chase')."""
    cyc, mtf = _extended_snapshot(71, 82, 81)
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TOP WATCH", lad["state"]
    assert lad["score"] <= 0, lad["score"]
    assert lad["entry"]["tag"] == "DON'T CHASE", lad["entry"]
    assert "chase" in lad["why"].lower() and "lagging" in lad["why"].lower()
    assert "missed" in lad["entry"]["text"].lower()


def test_extension_gate_fires_on_higher_tf_only() -> None:
    """Daily not yet >70 but BOTH 3-day and weekly overbought is still a late
    entry into an exhausted bigger trend — the gate fires on the HTF clause."""
    cyc, mtf = _extended_snapshot(64, 82, 81)
    assert ladder_state(cyc, mtf)["state"] == "TOP WATCH"


def test_extension_gate_also_catches_fresh_buy() -> None:
    """With the weekly turned (bull regime) the same overbought setup would be a
    full FRESH BUY ('BUY NOW') — the gate must catch that too, not only the
    weekly-unconfirmed TURN SIGNALED."""
    clean_cyc, clean_mtf = _extended_snapshot(52, 58, 55, weekly_cross=True)
    assert ladder_state(clean_cyc, clean_mtf)["state"] == "FRESH BUY"  # sanity
    cyc, mtf = _extended_snapshot(71, 82, 81, weekly_cross=True)
    assert ladder_state(cyc, mtf)["state"] == "TOP WATCH"


def test_extension_gate_spares_a_clean_buy() -> None:
    """A fresh turn with room to run (RSI mid-range) is left as the buy setup."""
    cyc, mtf = _extended_snapshot(54, 60, 57)
    assert ladder_state(cyc, mtf)["state"] in ("TURN SIGNALED", "FRESH BUY")


def test_turn_signaled_text_not_self_contradictory_above_ma() -> None:
    """Fix A: when price has ALREADY reclaimed the 10-day average, the TURN
    SIGNALED copy must not tell the user to wait for it to 'close back above' —
    that contradiction was the lag the SNDK card exposed. The genuine pre-reclaim
    case keeps the original 'buy on the reclaim' copy."""
    # a NON-stretched reclaim is the genuine partial-now entry (HALF SIZE); the copy
    # must not tell the user to wait for a reclaim they have already done.
    cyc, mtf = _extended_snapshot(54, 60, 57, above_ma10=True,
                                  dc_phase="in_band", dc_day=40)
    above = entry_timing("TURN SIGNALED", cyc, mtf)
    assert above["tag"] == "HALF SIZE", above
    assert "closes back above" not in above["text"]
    assert "already in" in above["text"]
    cyc_below, _ = _extended_snapshot(40, 45, 48, above_ma10=False,
                                      dc_phase="in_band", dc_day=40)
    below = entry_timing("TURN SIGNALED", cyc_below, mtf)
    assert below["tag"] == "BUY SOON"


def test_cycle_top_rollover_veto_demotes_late_curl_down() -> None:
    """The HWM bug: a LATE (not stretched) cand-confirmed buy whose daily momentum
    is already curling down — NOT overbought (RSI 62) so the old gate missed it —
    must be demoted to TOP WATCH / 'don't chase', never urgency='now'."""
    cyc, mtf = _extended_snapshot(62, 60, 58, above_ma10=True,
                                  dc_phase="approaching_band", dc_day=35, curl_dn=True)
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TOP WATCH", lad["state"]
    assert lad["entry"]["urgency"] != "now", lad["entry"]
    assert lad["entry"]["tag"] == "DON'T CHASE", lad["entry"]


def test_cycle_top_stretched_reclaim_is_buy_soon_not_now() -> None:
    """The ECG day-93 case: a reclaim this far past the cycle band is an UNCONFIRMED
    new cycle — entry must be 'imminent' (buy on confirmation), never 'now'."""
    for state in ("FRESH BUY", "TURN SIGNALED"):
        cyc, mtf = _extended_snapshot(57, 58, 56, above_ma10=True,
                                      dc_phase="stretched", dc_day=93)
        e = entry_timing(state, cyc, mtf)
        assert e["urgency"] == "imminent", (state, e)
        assert e["tag"] == "BUY SOON", (state, e)


def test_cycle_top_htf_down_cross_blocks_now() -> None:
    """A higher-timeframe (3-day/weekly) confirmed down-cross blocks a fresh 'now'
    buy even when the daily looks fine (the NVDA/MYRG case)."""
    cyc, mtf = _extended_snapshot(55, 56, 54, above_ma10=True,
                                  dc_phase="approaching_band", dc_day=33)
    mtf["3D"]["macd_cross_dn"] = True            # higher TF rolled over
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TOP WATCH", lad["state"]
    assert lad["entry"]["urgency"] != "now", lad["entry"]


def test_eq_freshness_decays_for_a_late_cross() -> None:
    """Fix C: a fresh up-cross near the low keeps full freshness, but the SAME
    fresh cross once price is already extended above the low is a chase and must
    be discounted — it used to score identically and wash out the proximity
    penalty (the SNDK +48% case). Staleness still stacks on top; the short side
    mirrors; default pct keeps the old near-pivot behaviour (back-compat)."""
    d_up = {"macd_pos": True}
    near = _eq_freshness(d_up, 0, False, True, pct=0.01)
    far = _eq_freshness(d_up, 0, False, True, pct=0.30)
    assert near == 1.0, near
    assert far <= 0.45 and near > far, (near, far)
    assert _eq_freshness(d_up, 0, False, True) == 1.0          # default pct → unchanged
    assert _eq_freshness(d_up, 40, False, True, pct=0.01) < near  # staleness still bites
    d_dn = {"macd_pos": False}
    assert _eq_freshness(d_dn, 0, False, False, pct=-0.01) > \
        _eq_freshness(d_dn, 0, False, False, pct=-0.30)
def test_bottom_confidence_confluence_and_gating() -> None:
    full = {"D": {"macd_cross_up": True}, "3D": {"macd_cross_up": True},
            "W": {"macd_cross_up": True}, "M": {"macd_cross_up": True}}
    none = {"D": {}, "3D": {}, "W": {}, "M": {}}
    eq = {"long": 80.0}
    # full multi-TF confluence => no discount (bc == entry quality)
    assert bottom_confidence(full, eq, "FRESH BUY")["score"] == 80.0
    # zero confluence => the floor (0.55 x long)
    assert abs(bottom_confidence(none, eq, "FRESH BUY")["score"] - 44.0) < 0.1
    # confluence only DISCOUNTS, never inflates
    assert bottom_confidence(none, eq, "FRESH BUY")["score"] <= eq["long"]
    # non-bottoming states get no bottom-confidence at all
    assert bottom_confidence(full, eq, "RALLY ON") == {}
    assert bottom_confidence(full, eq, "TOP WATCH") == {}
    # counter-trend bounce is capped into the high-risk band
    assert bottom_confidence(full, {"long": 95.0}, "COUNTERTREND BOUNCE")["score"] <= 30
    # a missing monthly bar renormalises (no silent cap, no crash)
    bc = bottom_confidence({"D": {"macd_cross_up": True}, "3D": {}, "W": {"macd_cross_up": True}},
                           eq, "TURN SIGNALED")
    assert 0 < bc["score"] <= 80 and bc["monthly_avail"] is False
    # fields render a per-timeframe line + a grade
    f = bottom_confidence_fields(bottom_confidence(full, eq, "FRESH BUY"))
    assert "Weekly ✓" in f["bc_line"] and f["bc_grade"] == "strong"


def test_washout_knife_tempers_bottom_confidence() -> None:
    full = {"D": {"macd_cross_up": True}, "3D": {"macd_cross_up": True},
            "W": {"macd_cross_up": True}, "M": {"macd_cross_up": True}}
    eq = {"long": 80.0}
    # a deeply-stretched-below-200dma, still-falling series => high knife
    n = 260
    falling = pd.Series([100 * (1 - 0.0016 * i) for i in range(n)],
                        index=pd.bdate_range("2021-01-01", periods=n))
    wo_fall = washout(falling, {"above_ma10": False})
    assert wo_fall["knife"] >= 0.6 and wo_fall["pct_below_200d"] < -8 and wo_fall["level"] in ("elevated", "high")
    # the knife TEMPERS (discounts) bottom_confidence vs the same setup with no washout
    bc_clean = bottom_confidence(full, eq, "FRESH BUY")["score"]
    bc_knife = bottom_confidence(full, eq, "FRESH BUY", wo=wo_fall)["score"]
    assert bc_knife < bc_clean                       # washout only discounts, never boosts
    # reclaiming (above the 10-day) is a much milder knife than still-falling
    wo_reclaim = washout(falling, {"above_ma10": True})
    assert wo_reclaim["knife"] < wo_fall["knife"]
    # fields surface a knife-risk caution at elevated/high severity
    flds = bottom_confidence_fields(bottom_confidence(full, eq, "FRESH BUY", wo=wo_fall))
    assert flds.get("bc_knife") in ("elevated", "high") and "washout" in flds["bc_knife_line"].lower()
    # an above-trend series => no knife, no temper
    up = pd.Series([100 * (1 + 0.001 * i) for i in range(n)],
                   index=pd.bdate_range("2021-01-01", periods=n))
    assert washout(up, {"above_ma10": True}).get("knife", 0) == 0
    # market VIX context: a calm-then-spike series flags panic
    vix = pd.Series([15] * 300 + [45] * 5, index=pd.bdate_range("2020-01-01", periods=305))
    assert market_vix_context(vix)["panic"] is True


def test_fresh_weekly_cross_vetoes_take_profits() -> None:
    """The XLV 2026-06 misfire: a daily-overbought buy that the extension gate would route to
    TOP WATCH / 'DON'T CHASE' must instead read RALLY ON / HOLD when the WEEKLY (investor-cycle)
    MACD has JUST crossed up and the weekly itself isn't yet overbought — a fresh weekly cross is
    the START of a multi-month up-leg, so daily strength is the launch thrust, not a top."""
    cyc, mtf = _extended_snapshot(72, 66, 63, weekly_cross=True)   # daily 72 hot, weekly 63 + fresh cross
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "RALLY ON", lad["state"]
    assert lad["entry"]["urgency"] == "hold", lad["entry"]        # board → hold, NOT take_profits
    assert "investor-cycle" in lad["why"]
    # the glance-level reconciliation sentence is emitted so the daily chips can't read as a conflict
    assert lad.get("synthesis_line") and "weekly investor cycle just turned up" in lad["synthesis_line"]


def test_take_profits_stands_without_a_fresh_weekly_cross() -> None:
    """No fresh weekly cross → the genuine daily-overbought 'don't chase' read survives."""
    cyc, mtf = _extended_snapshot(72, 66, 63, weekly_cross=False)
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TOP WATCH", lad["state"]
    assert lad["entry"]["urgency"] == "caution", lad["entry"]


def test_weekly_cross_while_weekly_overbought_does_not_veto() -> None:
    """A weekly cross with the weekly already overbought (RSI≥70) is NOT early — no veto."""
    cyc, mtf = _extended_snapshot(72, 80, 81, weekly_cross=True)   # weekly hot (81)
    assert ladder_state(cyc, mtf)["state"] == "TOP WATCH"


# ── De-escalation gate: below-MA10 TURN SIGNALED + rollover_veto / overextended ──

def _below_ma10_turn_signaled_snapshot(rsi_d: float = 48.0,
                                       curl_dn: bool = True,
                                       approaching_dn: bool = False,
                                       stoch: float = 55.0) -> tuple[dict, dict]:
    """Snapshot that fires the bug branch: late cycle, swing low in, price BELOW the
    10-day average (above_ma10=False). curl_dn/approaching_dn arm daily rollover so
    rollover_veto fires when combined with late=True. stoch knob exercises the
    _overextended() oscillator path."""
    cyc = {
        "dc_day": 38, "dc_band": (36, 42), "dc_early": 12, "dc_phase": "in_band",
        "last_dcl": "2026-06-01", "dcl_price": 4.20,
        "cand_dcl": "2026-07-02", "cand_price": 4.20, "cand_swing": True, "cand_age": 1,
        "cand_depth_pct": 8.7,
        "translation": "right", "failed_cycle": False, "failed_age": None,
        "swing_low": True, "above_ma10": False, "ma10_rising": False,
        "ic_week": 12, "ic_band": (16, 26), "ic_phase": "in_band", "ic_failed": False,
        "n_troughs": 3,
    }
    mtf = {
        "D": {"rsi14": rsi_d, "rsi5": rsi_d, "stoch": stoch,
              "macd_pos": True, "macd_cross_up": False, "macd_cross_dn": False,
              "macd_approaching_up": True, "macd_approaching_dn": approaching_dn,
              "macd_curl_up": False, "macd_curl_dn": curl_dn,
              "macd_bars_to_cross": 2.0,
              "stoch_cross_up": False, "stoch_cross_dn": False},
        "3D": {"rsi14": 50.0, "rsi5": 50.0, "stoch": 50.0,
               "macd_pos": False, "macd_cross_up": False, "macd_cross_dn": False,
               "macd_approaching_up": False, "macd_approaching_dn": False,
               "macd_curl_up": False, "macd_curl_dn": False, "macd_bars_to_cross": None,
               "stoch_cross_up": False, "stoch_cross_dn": False},
        "W": {"rsi14": 45.0, "rsi5": 45.0, "stoch": 40.0,
              "macd_pos": False, "macd_cross_up": False, "macd_cross_dn": False,
              "macd_approaching_up": False, "macd_approaching_dn": False,
              "macd_curl_up": False, "macd_curl_dn": False, "macd_bars_to_cross": None,
              "stoch_cross_up": False, "stoch_cross_dn": False},
    }
    return cyc, mtf


def test_below_ma10_turn_signaled_with_rollover_veto_does_not_buy() -> None:
    """512760.SS pathology (2026-07-02): price −8.7% off high, above_ma10 flipped
    False, rollover_veto=True (daily MACD curling down + late in cycle).
    The bug produced urgency='imminent' / BUY SOON — must now be de-escalated to
    urgency='caution' so the action-board bucketer places it in take_profits/hold,
    NOT buy_soon. State label (TURN SIGNALED / BOTTOMING) is intentionally preserved."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(curl_dn=True)
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", (
        f"expected TURN SIGNALED got {lad['state']!r} — bug path may have changed")
    entry = lad["entry"]
    assert entry["urgency"] not in ("now", "imminent", "soon"), (
        f"entry still maps to buy bucket: urgency={entry['urgency']!r}  tag={entry['tag']!r}")
    assert entry["urgency"] == "caution", entry
    assert "WAIT" in entry["tag"], entry
    # state label preserved: still says BOTTOMING at the display layer
    assert lad["label"] == "BOTTOMING", lad["label"]


def test_below_ma10_turn_signaled_with_stoch_overextended_does_not_buy() -> None:
    """Same de-escalation fires via the _overextended(mtf) oscillator path even
    when rollover_veto is False — a very high 3D StochRSI (>80) should trigger it."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(curl_dn=False, approaching_dn=False)
    # force 3D StochRSI overbought so _overextended(mtf) returns True
    mtf["3D"]["stoch"] = 85.0
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", lad["state"]
    entry = lad["entry"]
    assert entry["urgency"] not in ("now", "imminent", "soon"), entry
    assert "WAIT" in entry["tag"], entry


def test_below_ma10_turn_signaled_clean_bottom_still_buys() -> None:
    """Guard: a genuine fresh non-extended bottom below the 10-day average
    (rollover_veto=False, oscillators mid-range) MUST still get urgency='imminent'
    (BUY SOON). The fix must be discriminating — not a blanket suppression."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(curl_dn=False, approaching_dn=False,
                                                   rsi_d=42.0, stoch=45.0)
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", lad["state"]
    entry = lad["entry"]
    assert entry["urgency"] in ("imminent", "soon"), (
        f"clean bottom was suppressed — urgency={entry['urgency']!r}  tag={entry['tag']!r}")
    assert "BUY" in entry["tag"], entry


def test_below_ma10_near_low_daily_rollover_only_gets_unconfirmed_not_extended() -> None:
    """XLK profile: price near cycle low, oscillators deeply oversold (D/3D StochRSI=3),
    _overextended(mtf)=False. Gate fires via daily macd_curl_dn + late-cycle
    (rollover_veto=True via daily path), NOT via oscillator overextension.
    This is the copy-defect case: the old code unconditionally labelled the entry
    'EXTENDED / 已过热' even though oscillators were oversold, not overbought.
    Asserts: (a) urgency='caution' (still de-escalated), (b) tag/text uses the
    'momentum rolling over / UNCONFIRMED' variant and does NOT contain
    'EXTENDED', '过热', or 'overheated'."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(curl_dn=True, approaching_dn=False,
                                                   rsi_d=38.0, stoch=3.0)
    # Confirm oscillators are oversold (not overbought) — _overextended must be False
    mtf["3D"]["stoch"] = 3.0  # deeply oversold on the 3-day too

    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", (
        f"expected TURN SIGNALED got {lad['state']!r}")
    entry = lad["entry"]

    # (a) de-escalated to caution (not a buy-bucket urgency)
    assert entry["urgency"] == "caution", (
        f"expected caution, got urgency={entry['urgency']!r}  tag={entry['tag']!r}")
    assert entry["urgency"] not in ("now", "imminent", "soon"), entry

    # (b) copy is the 'unconfirmed / momentum rolling over' variant —
    # must NOT claim 'EXTENDED' or 'overheated' for an oversold ticker
    assert "WAIT" in entry["tag"], (
        f"expected WAIT in tag, got {entry['tag']!r}")
    for forbidden in ("EXTENDED", "过热", "overheated"):
        assert forbidden not in entry["tag"], (
            f"tag falsely claims '{forbidden}' for an oversold ticker: {entry['tag']!r}")
        assert forbidden not in entry.get("tag_zh", ""), (
            f"tag_zh falsely claims '{forbidden}': {entry.get('tag_zh')!r}")
        assert forbidden not in entry.get("text", ""), (
            f"text falsely claims '{forbidden}': {entry.get('text', '')[:120]!r}")
        assert forbidden not in entry.get("text_zh", ""), (
            f"text_zh falsely claims '{forbidden}': {entry.get('text_zh', '')[:120]!r}")


# ── _overextended() OSC-EXEMPT-BELOW guard (post-washout range-compression fix) ──
# Mirrors the RALLY ON→TOP WATCH StochRSI-saturation fix at cycles.py:1006-1014.
# Guard: when ext_pct is not None AND <= _EG_OSC_EXEMPT_BELOW (default -10.0), the
# StochRSI-overbought and RSI14-cap oscillator legs are suppressed.  The stretch leg
# (ext_pct >= +30%) and None-ext_pct callers are unaffected.

def _osc_exempt_mtf(d_stoch: float, rsi14: float, t3_stoch: float = 30.0) -> dict:
    """Minimal mtf fixture for _overextended() unit tests."""
    return {
        "D": {"stoch": d_stoch, "rsi14": rsi14},
        "3D": {"stoch": t3_stoch, "rsi14": 50.0},
    }


def test_overextended_washed_out_bounce_not_flagged() -> None:
    """Case 1 (600519.SS pathology): D.stoch=83 > 80, rsi14=55, pct=-12.5 → NOT
    overextended after fix. Range-compression post-washout saturates StochRSI but
    price is still deep below the 200dma — oscillator leg must be suppressed."""
    mtf = _osc_exempt_mtf(d_stoch=83.0, rsi14=55.0)
    assert not _overextended(mtf, ext_pct=-12.5), (
        "washed-out bounce with D.stoch=83/pct=-12.5 must NOT be overextended")


def test_overextended_genuinely_extended_still_flagged() -> None:
    """Case 2: D.stoch=85, ext_pct=+8 (above 200dma) → STILL overextended.
    Price is not below the exemption threshold, so oscillator leg fires normally."""
    mtf = _osc_exempt_mtf(d_stoch=85.0, rsi14=55.0)
    assert _overextended(mtf, ext_pct=8.0), (
        "genuinely extended name (D.stoch=85, pct=+8) must still be flagged")


def test_overextended_osc_exempt_boundary_at_threshold() -> None:
    """Case 3a: hot RSI (rsi14=70 > 62) with ext_pct=-10.0 exactly (== threshold)
    → EXEMPT (<=). The boundary is inclusive on the exempt side."""
    mtf = _osc_exempt_mtf(d_stoch=50.0, rsi14=70.0)
    assert not _overextended(mtf, ext_pct=-10.0), (
        "ext_pct=-10.0 (== threshold) must exempt the RSI oscillator leg")


def test_overextended_osc_not_exempt_just_above_threshold() -> None:
    """Case 3b: same hot RSI (rsi14=70) with ext_pct=-9.9 (just above threshold)
    → NOT exempt, RSI14 cap fires normally → overextended=True."""
    mtf = _osc_exempt_mtf(d_stoch=50.0, rsi14=70.0)
    assert _overextended(mtf, ext_pct=-9.9), (
        "ext_pct=-9.9 (above threshold) must NOT exempt the RSI14 cap leg")


def test_overextended_none_ext_pct_still_fires() -> None:
    """Case 4: ext_pct=None with D.stoch=83 → still overextended (legacy behaviour
    preserved for close-only callers like ladder_state's de-escalation gate)."""
    mtf = _osc_exempt_mtf(d_stoch=83.0, rsi14=50.0)
    assert _overextended(mtf, ext_pct=None), (
        "ext_pct=None must NOT exempt oscillators — legacy caller behaviour unchanged")


def test_overextended_stretch_leg_fires_regardless() -> None:
    """Case 5: ext_pct=+35 (>= stretch_block=30) → overextended=True even when
    oscillators are mild. The stretch leg is independent of the osc-exempt guard."""
    mtf = _osc_exempt_mtf(d_stoch=30.0, rsi14=40.0)
    assert _overextended(mtf, ext_pct=35.0), (
        "stretch leg (ext_pct=+35 >= 30) must fire regardless of oscillator values")


# ── Below-MA10 de-escalation gate: widened to HTF curl-down (2026-07-14) ──────
# Regression for 512760.SS (China semis ETF): 3D MACD curling down with no
# completed cross, price below 10-day, BUY SOON printed — gate must now fire on
# _htf_curl_dn even when rollover_veto is False (no completed cross) and daily
# is not yet rolling over on its own.

def test_below_ma10_htf_curl_dn_only_fires_gate() -> None:
    """512760.SS regression (2026-07-14): 3D macd_curl_dn=True, no 3D/W
    macd_cross_dn (rollover_veto=False), daily not rolling over — gate must
    still fire via _htf_curl_dn and produce BOTTOMING · UNCONFIRMED — WAIT
    with urgency='caution'."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(
        curl_dn=False, approaching_dn=False, rsi_d=48.0, stoch=45.0
    )
    # Arm 3D curl-down only — no completed cross anywhere.
    mtf["3D"]["macd_curl_dn"] = True
    # Confirm the gate fires NOT via rollover_veto (daily path is clean, no HTF cross).
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", (
        f"expected TURN SIGNALED, got {lad['state']!r}")
    entry = lad["entry"]
    assert entry["urgency"] == "caution", (
        f"3D curl-down must de-escalate to caution; got urgency={entry['urgency']!r}  "
        f"tag={entry['tag']!r}")
    assert entry["tag"] == "BOTTOMING · UNCONFIRMED — WAIT", (
        f"expected BOTTOMING · UNCONFIRMED — WAIT, got {entry['tag']!r}")
    # Diagnostic copy must say 'rolling over', not 'crossed down' (no completed cross).
    assert "rolling over" in entry.get("text", ""), (
        f"text must reference 'rolling over' for curl-only case: {entry.get('text', '')[:120]!r}")
    assert "掉头向下" in entry.get("text_zh", ""), (
        f"text_zh must reference '掉头向下' for curl-only case: {entry.get('text_zh', '')[:120]!r}")
    # Must NOT claim 'crossed down' (that is reserved for htf_rollover branch).
    assert "crossed down" not in entry.get("text", ""), (
        f"curl-only case must not say 'crossed down': {entry.get('text', '')[:120]!r}")


def test_below_ma10_no_3d_key_does_not_gate_on_curl() -> None:
    """Short-series safety: when mtf has no '3D' key, _htf_curl_dn resolves to
    False via .get() on {} — a clean bottom must still return urgency='imminent'
    (BUY SOON), not be suppressed by a missing-key artefact."""
    cyc, mtf = _below_ma10_turn_signaled_snapshot(
        curl_dn=False, approaching_dn=False, rsi_d=42.0, stoch=45.0
    )
    del mtf["3D"]   # simulate a short series where the 3D timeframe has no data
    lad = ladder_state(cyc, mtf)
    assert lad["state"] == "TURN SIGNALED", lad["state"]
    entry = lad["entry"]
    assert entry["urgency"] in ("imminent", "soon"), (
        f"no-3D-key clean bottom must not be suppressed; got urgency={entry['urgency']!r}  "
        f"tag={entry['tag']!r}")
    assert "BUY" in entry["tag"], (
        f"no-3D-key clean bottom must still show a BUY tag; got {entry['tag']!r}")


if __name__ == "__main__":
    for fn in [test_trough_spacing, test_translation_right, test_translation_left,
               test_failed_cycle_flag, test_ladder_states_sane, test_decline_on_breakdown,
               test_signal_age_detects_recent_cross, test_signal_age_contract_holds,
               test_signal_age_thin_history, test_signal_age_fields_prose,
               test_analyze_attaches_age, test_eq_proximity_peaks_near_the_low,
               test_eq_grade_bands, test_eq_sign_anchored_to_state,
               test_eq_every_state_classified, test_eq_thin_history_bows_out,
               test_eq_fields_and_analyze,
               test_extension_gate_routes_overbought_buy_to_top_watch,
               test_extension_gate_fires_on_higher_tf_only,
               test_extension_gate_also_catches_fresh_buy,
               test_extension_gate_spares_a_clean_buy,
               test_turn_signaled_text_not_self_contradictory_above_ma,
               test_eq_freshness_decays_for_a_late_cross,
               test_bottom_confidence_confluence_and_gating,
               test_washout_knife_tempers_bottom_confidence,
               test_fresh_weekly_cross_vetoes_take_profits,
               test_take_profits_stands_without_a_fresh_weekly_cross,
               test_weekly_cross_while_weekly_overbought_does_not_veto,
               test_below_ma10_turn_signaled_with_rollover_veto_does_not_buy,
               test_below_ma10_turn_signaled_with_stoch_overextended_does_not_buy,
               test_below_ma10_turn_signaled_clean_bottom_still_buys,
               test_below_ma10_near_low_daily_rollover_only_gets_unconfirmed_not_extended,
               test_overextended_washed_out_bounce_not_flagged,
               test_overextended_genuinely_extended_still_flagged,
               test_overextended_osc_exempt_boundary_at_threshold,
               test_overextended_osc_not_exempt_just_above_threshold,
               test_overextended_none_ext_pct_still_fires,
               test_overextended_stretch_leg_fires_regardless,
               test_below_ma10_htf_curl_dn_only_fires_gate,
               test_below_ma10_no_3d_key_does_not_gate_on_curl]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all cycle tests passed")
