"""BTC cycle-thesis MONITOR — turns the halving/midterm-cycle conviction into something
*watched*, with pre-committed falsifiers, instead of just held on faith.

THE THESIS (owner's, and it's a defensible one — unlike the equity midterm claim):
BTC's bear leg has bottomed near the US midterm year for the last 3 cycles (−84% 2018,
−77% 2022, …2026?). The CAUSAL engine is the halving, not the calendar: every halving has
landed in a US *election* year (2012/2016/2020/2024), so the +12-18mo bull peak lands in the
post-election year and the ~12mo bear bottom lands in the midterm year. The political clock
is an amplifier (midterm Fed tightening) that currently rhymes with the halving clock. See
[[election-cycle-modulator]] (the equity sibling) and [[user-trades-conviction-low-n]].

This is a SOFT PRIOR (n=3 completed cycles). The honest risks aren't "it's noise" — the
mechanism is real and the effect is huge — they're (1) the cycle is DAMPENING as BTC
institutionalises (−84% → −77% → −52% so far), so the bottom may be shallower/mushier and not
scream "back up the truck"; and (2) the halving and political clocks can DESYNC (the halving
is block-based, ~4yr but drifting Nov→Jul→May→Apr). So this monitor's whole job is to print,
every day, whether the thesis is still ON TRACK and to FLAG THE MOMENT it starts breaking:
  • dampening  — is this bear much shallower than prior bears at the same phase?
  • timing     — are we early / in / overdue past the projected bottom window?
  • desync     — has the halving clock drifted away from the midterm window?
  • structure  — has price INVALIDATED the 1064/364 down-leg (new high before the bottom)?

TIMING + RISK CONTEXT ONLY — not a price target, not advice. Pure (price + config in, dict
out), never raises. Reuses the committed cycle config (vector.cycle_clock / cycle_phase_clock).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Projected-bottom window = last cycle TOP + the historical down-leg, bracketed. Observed
# down-legs were 364d (2017-top) and 378d (2021-top); center ~371d. We widen to a window so
# the chip reads as a zone, not false precision.
_WIN_LEAD_D = 360     # window opens this many days after the cycle top
_WIN_TRAIL_D = 430    # window closes this many days after the cycle top (past 378d + buffer)
# Dampening: flag when the current drawdown-from-peak is this much shallower than the mean of
# prior cycle bears (e.g. prior mean ~−80%, current −52% -> gap 28pp -> flagged).
_DAMPEN_GAP = 0.15
# Desync: flag when the structure-projected bottom and the midterm-election window diverge by
# more than this. They coincide this cycle (~Oct 2026 vs Nov 2026), so this stays green for now.
_DESYNC_MONTHS = 4.0
# A plausible bottoming drawdown — below this, "accumulate / scale-in" context can show (only
# ever CONTEXT, gated on being in the timing window too).
_BOTTOM_DD = 0.45


def _ts(x):
    return pd.Timestamp(str(x)[:10])


def _extreme(close: pd.Series, date: pd.Timestamp, kind: str, win: int = 21):
    """Price at a pivot: max (top) / min (bottom) within +/-win days of the recorded date,
    robust to the config date being a few days off the true extreme. None if out of range."""
    lo, hi = date - pd.Timedelta(days=win), date + pd.Timedelta(days=win)
    seg = close[(close.index >= lo) & (close.index <= hi)]
    if seg.empty:
        return None
    return float(seg.max() if kind == "top" else seg.min())


def monitor(close: pd.Series, cfg: dict | None = None, sig: pd.DataFrame | None = None,
            asof=None) -> dict:
    """Live cycle-thesis monitor. `cfg` = the `vector` config block (reads cycle_clock +
    cycle_phase_clock); `sig` (optional) = btc_signals.compute_all() so we can reuse the
    PIT 1064/364 structure status. Never raises."""
    try:
        return _monitor(close, cfg or {}, sig, asof)
    except Exception as e:  # noqa: BLE001 — monitor, never fatal
        log.warning("btc_cycle_thesis monitor failed: %s", e)
        return {"schema": "btc_cycle_thesis.v1", "ok": False, "degraded_reason": str(e)}


_DISCLAIMER = ("Halving-cycle thesis monitor — a SOFT prior (n=3 cycles). The halving is the "
               "durable anchor; the midterm alignment is downstream of it and can desync. "
               "Timing + risk context, never a price target or advice. De-risk = sizing.")


def _monitor(close: pd.Series, cfg: dict, sig, asof) -> dict:
    close = close.dropna()
    close.index = pd.to_datetime(close.index)
    close = close.sort_index()
    if len(close) < 200:
        return {"schema": "btc_cycle_thesis.v1", "ok": False, "degraded_reason": "short_history"}
    now = _ts(asof) if asof is not None else close.index[-1]
    px = float(close.loc[:now].iloc[-1])

    cc = cfg.get("cycle_clock") or {}
    cpc = cfg.get("cycle_phase_clock") or {}
    halvings = [_ts(d) for d in (cc.get("halving_dates") or [])]
    tops = [_ts(d) for d in (cpc.get("tops") or [])]
    bottoms = [_ts(d) for d in (cpc.get("bottoms") or [])]
    down_days = float(cpc.get("down_days", 364))

    # --- where we are ---------------------------------------------------------
    past_halvings = [h for h in halvings if h <= now]
    last_halving = past_halvings[-1] if past_halvings else None
    days_since_halving = int((now - last_halving).days) if last_halving is not None else None

    # current cycle peak = the most recent recorded top on/before now (PIT), priced from data
    past_tops = [t for t in tops if t <= now]
    peak_date = past_tops[-1] if past_tops else None
    peak_px = _extreme(close, peak_date, "top") if peak_date is not None else None
    if peak_px is None:                       # fallback: running ATH
        peak_px = float(close.loc[:now].cummax().iloc[-1])
    dd_from_peak = px / peak_px - 1.0 if peak_px else None

    # --- prior cycle bears (peak -> next bottom), measured from price ----------
    prior_bears = []
    for t in tops:
        nb = next((b for b in bottoms if b > t), None)
        if nb is None or nb > now:            # only COMPLETED bears (PIT)
            continue
        tp, bp = _extreme(close, t, "top"), _extreme(close, nb, "bottom")
        if tp and bp:
            prior_bears.append({"top": t.strftime("%Y-%m-%d"),
                                "bottom": nb.strftime("%Y-%m-%d"),
                                "depth": round(bp / tp - 1.0, 3),
                                "down_days": int((nb - t).days)})
    prior_mean = float(np.mean([b["depth"] for b in prior_bears])) if prior_bears else None

    # --- projected bottom window (structure-anchored on the current top) -------
    win_start = win_end = None
    if peak_date is not None:
        win_start = peak_date + pd.Timedelta(days=_WIN_LEAD_D)
        win_end = peak_date + pd.Timedelta(days=_WIN_TRAIL_D)
    in_window = bool(win_start is not None and win_start <= now <= win_end)
    # structure projection from btc_signals (PIT 1064/364), if available
    struct_pivot = struct_kind = struct_status = None
    if sig is not None and len(sig):
        row = sig[sig.index <= now]
        if len(row):
            r = row.iloc[-1]
            struct_pivot = r.get("cphase_next_pivot")
            struct_kind = r.get("cphase_next_kind")
            struct_status = r.get("cphase_status")

    # --- the falsifier flags --------------------------------------------------
    flags = []

    def add(key, level, en, zh):
        flags.append({"key": key, "level": level, "en": en, "zh": zh})

    # 1) dampening — only a FAIR comparison once we're at/past the projected bottom window.
    #    Mid-bear, a −52% vs prior −80% just means "not done yet", not a shallower cycle.
    past_or_in = bool(win_start is not None and now >= win_start)
    dampening = bool(past_or_in and dd_from_peak is not None and prior_mean is not None
                     and dd_from_peak > prior_mean + _DAMPEN_GAP)   # shallower (less negative)
    if dd_from_peak is not None and prior_mean is not None:
        if dampening:
            add("dampening", "watch",
                f"Bear is shallower than prior cycles ({dd_from_peak:.0%} vs ~{prior_mean:.0%} avg) — "
                f"institutionalisation may be compressing the cycle; the bottom could be mushier. "
                f"Don't wait for a −80% washout.",
                f"本轮回撤浅于以往（{dd_from_peak:.0%}，历史均值约 {prior_mean:.0%}）——机构化或在压缩周期，"
                f"底部可能不明显；不要等 −80% 的深跌。")
        elif past_or_in:
            add("dampening", "ok",
                f"Drawdown {dd_from_peak:.0%} vs ~{prior_mean:.0%} prior-bear avg — in line.",
                f"回撤 {dd_from_peak:.0%}，与历史熊市均值约 {prior_mean:.0%} 相当。")
        else:
            add("dampening", "ok",
                f"Drawdown {dd_from_peak:.0%} so far vs ~{prior_mean:.0%} prior-bear avg (bear still developing).",
                f"目前回撤 {dd_from_peak:.0%}，历史熊市均值约 {prior_mean:.0%}（熊市仍在发展中）。")

    # 2) timing vs the projected bottom window
    if win_start is None:
        time_status = "unknown"
    elif now < win_start:
        time_status = "early"
        d = int((win_start - now).days)
        add("timing", "ok", f"Pre-bottom: ~{d}d until the projected window opens "
            f"({win_start:%b %Y}). Scale in, don't lump in.",
            f"底部前：距预测窗口开启约 {d} 天（{win_start:%Y-%m}）。分批建仓，勿一次性。")
    elif in_window:
        time_status = "in_window"
        add("timing", "ok", f"In the projected bottom window ({win_start:%b %Y}–{win_end:%b %Y}) — "
            f"the accumulation zone if the thesis holds.",
            f"处于预测底部窗口（{win_start:%Y-%m} 至 {win_end:%Y-%m}）——若论点成立即为吸筹区。")
    else:
        # past the window
        recent_low = float(close.loc[win_start:now].min()) if win_start is not None else px
        still_falling = px <= recent_low * 1.03   # within 3% of the window's low = no clear bottom
        time_status = "overdue" if still_falling else "bottomed?"
        if still_falling:
            add("timing", "alert",
                f"OVERDUE: past the projected window ({win_end:%b %Y}) and still near the lows — "
                f"the cycle clock has slipped; re-examine the thesis.",
                f"超期：已过预测窗口（{win_end:%Y-%m}）且仍在低位附近——周期时钟已偏移；请重新审视论点。")
        else:
            add("timing", "ok", f"Window passed ({win_end:%b %Y}); price has lifted off the low — "
                f"a bottom may have formed on schedule.", f"窗口已过（{win_end:%Y-%m}）；价格已离开低点——底部或已如期形成。")

    # 3) structure invalidation (1064/364 down-leg broke its high before bottoming)
    if struct_status == "invalidated":
        add("structure", "alert",
            "Structure INVALIDATED: price broke the down-leg's reference high before bottoming — "
            "the 1064/364 count is off this cycle.",
            "结构已失效：价格在见底前突破下跌腿参考高点——本轮 1064/364 计数已偏离。")
    elif struct_status == "overdue":
        add("structure", "watch", "1064/364 down-leg is running long (overdue).",
            "1064/364 下跌腿运行偏长（超期）。")
    elif struct_status == "on_track":
        add("structure", "ok", "1064/364 down-leg on track.", "1064/364 下跌腿按节奏。")

    # 4) desync — structure-projected bottom vs the midterm-election window
    desync_months = None
    desync_flag = False
    if peak_date is not None:
        proj_bottom = peak_date + pd.Timedelta(days=int(down_days))
        # nearest US midterm year (Y%4==2) election ~ early November
        my = proj_bottom.year if proj_bottom.year % 4 == 2 else (
            proj_bottom.year + (2 - proj_bottom.year % 4) % 4)
        midterm_elec = pd.Timestamp(year=my, month=11, day=4)
        desync_months = round(abs((proj_bottom - midterm_elec).days) / 30.4, 1)
        desync_flag = bool(desync_months > _DESYNC_MONTHS)
        add("desync", "watch" if desync_flag else "ok",
            (f"Halving and political clocks DIVERGING (~{desync_months}mo apart) — trust the halving."
             if desync_flag else
             f"Halving and midterm clocks aligned this cycle (projected bottom ~{proj_bottom:%b %Y}, "
             f"midterm {midterm_elec:%b %Y})."),
            (f"减半与政治周期出现背离（相差约 {desync_months} 个月）——以减半为准。" if desync_flag else
             f"本轮减半与中期周期一致（预测底部约 {proj_bottom:%Y-%m}，中期 {midterm_elec:%Y-%m}）。"))

    # --- overall thesis status ------------------------------------------------
    levels = [f["level"] for f in flags]
    if "alert" in levels:
        thesis = "breaking"
    elif "watch" in levels:
        thesis = "watch"
    else:
        thesis = "intact"

    accumulate = bool(in_window and dd_from_peak is not None and dd_from_peak <= -_BOTTOM_DD
                      and struct_status != "invalidated")

    return {
        "schema": "btc_cycle_thesis.v1",
        "ok": True,
        "asof": now.strftime("%Y-%m-%d"),
        "price": round(px, 0),
        "last_halving": last_halving.strftime("%Y-%m-%d") if last_halving is not None else None,
        "days_since_halving": days_since_halving,
        "peak_date": peak_date.strftime("%Y-%m-%d") if peak_date is not None else None,
        "peak_price": round(peak_px, 0) if peak_px else None,
        "drawdown_from_peak": round(dd_from_peak, 3) if dd_from_peak is not None else None,
        "prior_bears": prior_bears,
        "prior_bear_mean": round(prior_mean, 3) if prior_mean is not None else None,
        "window_start": win_start.strftime("%Y-%m-%d") if win_start is not None else None,
        "window_end": win_end.strftime("%Y-%m-%d") if win_end is not None else None,
        "in_window": in_window,
        "time_status": time_status if win_start is not None else "unknown",
        "struct_next_pivot": struct_pivot, "struct_next_kind": struct_kind,
        "struct_status": struct_status,
        "desync_months": desync_months,
        "dampening": dampening,
        "accumulate": accumulate,
        "thesis_status": thesis,
        "flags": flags,
        "caveat_en": ("Soft prior, n=3 completed cycles. The halving is the causal anchor; the "
                      "midterm alignment is downstream and can desync. Scale in, size for −70% not "
                      "−50%, and pre-commit the exit (sell into the next pre-election bull)."),
        "caveat_zh": ("软先验，仅 3 个完整周期。减半是因果锚点；中期对齐是其下游、可能背离。分批建仓，"
                      "按 −70%（而非 −50%）设仓位，并预设退出（在下一个大选前牛市中卖出）。"),
        "disclaimer": _DISCLAIMER,
    }
