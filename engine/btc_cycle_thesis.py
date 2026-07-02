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
# PUBLIC: the W4 staged re-entry (engine/btc_overrides.py) keys its tranche
# spine off these same constants — ONE source of truth for "the projected window".
WIN_LEAD_D = 360      # window opens this many days after the cycle top
WIN_TRAIL_D = 430     # window closes this many days after the cycle top (past 378d + buffer)
_WIN_LEAD_D = WIN_LEAD_D
_WIN_TRAIL_D = WIN_TRAIL_D
# Pivot-staleness tolerance: reuse _extreme()'s ±21d pivot-date window (the existing,
# pre-committed imprecision allowance for hand-recorded config pivots — NOT a new knob).
_PIVOT_SLACK_D = 21
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

    # --- halving-anchored bottom window (W2 falsifier repair, masterplan N8) ---
    # The halving is the thesis's CAUSAL anchor, so the falsifiers must be able to
    # measure against it. Window derived purely from the OBSERVED halving→next-bottom
    # gaps of completed prior cycles (PIT: only bottoms known by `now`): bracket =
    # [min gap, max gap], projection = median gap. Pre-committed structure, zero
    # invented constants — NOT tuned to fire. With the shipped config this gives
    # gaps 777/889/924d → window ≈ Jun 6 – Oct 31 2026, projection ≈ Sep 26 2026 —
    # so the timing falsifier can escalate INSIDE the 2026 gate window (the old
    # peak-anchored window closed ~37 days after the gate self-releases).
    halving_gaps = []
    for j, h in enumerate(halvings):
        nxt_h = halvings[j + 1] if j + 1 < len(halvings) else None
        nb = next((b for b in sorted(bottoms) if b > h), None)
        if nb is not None and nb <= now and (nxt_h is None or nb < nxt_h):
            halving_gaps.append(int((nb - h).days))
    h_win_start = h_win_end = h_proj_bottom = None
    if last_halving is not None and halving_gaps:
        h_win_start = last_halving + pd.Timedelta(days=min(halving_gaps))
        h_win_end = last_halving + pd.Timedelta(days=max(halving_gaps))
        h_proj_bottom = last_halving + pd.Timedelta(days=int(np.median(halving_gaps)))
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

    # HALVING-clock escalation (W2, N8): if the causal clock's own window has closed —
    # `now` past [last halving + max observed halving→bottom gap] — and price still sits
    # at the lows, the timing flag escalates NOW rather than waiting for the later
    # peak-anchored bracket. Two-stage by design: WATCH past the halving clock's worst
    # historical case, ALERT past the peak-anchored trail (the existing rule above).
    halving_overdue = False
    if (h_win_end is not None and now > h_win_end
            and time_status in ("early", "in_window")):
        h_low = float(close.loc[min(h_win_start, now):now].min())
        halving_overdue = bool(px <= h_low * 1.03)   # same 3% no-lift-off convention as above
        if halving_overdue:
            flags[:] = [f for f in flags if f["key"] != "timing"]
            add("timing", "watch",
                f"Halving clock OVERDUE: past the halving-anchored window "
                f"({h_win_start:%b %Y}–{h_win_end:%b %Y}, worst historical gap) and still near "
                f"the lows — the causal clock has slipped even though the peak-anchored window "
                f"({win_start:%b %Y}–{win_end:%b %Y}) is still open. Watch closely.",
                f"减半时钟超期：已过减半锚定窗口（{h_win_start:%Y-%m} 至 {h_win_end:%Y-%m}，历史最长间隔）"
                f"且仍在低位附近——因果时钟已偏移，尽管峰值锚定窗口（{win_start:%Y-%m} 至 "
                f"{win_end:%Y-%m}）仍未关闭。需密切关注。")

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

    # 4) desync — the HALVING-anchored projected bottom vs the midterm-election window.
    #    (W2 repair, masterplan N8: the old detector projected from the cycle TOP
    #    (+down_days) — it never referenced the halving it claims to test, and both the
    #    top and the election are fixed dates, so it was a cycle-constant that could
    #    never fire. Now anchored on the actual halving (vector.cycle_clock.halving_dates)
    #    via the observed halving→bottom gaps — it measures real halving-calendar drift.)
    desync_months = None
    desync_flag = False
    if h_proj_bottom is not None:
        # nearest US midterm election (Y%4==2, ~early November) in EITHER direction —
        # the old round-up-only pick mis-measured a January projection by ~3.7 years.
        candidates = [pd.Timestamp(year=y, month=11, day=4)
                      for y in range(h_proj_bottom.year - 3, h_proj_bottom.year + 4)
                      if y % 4 == 2]
        midterm_elec = min(candidates, key=lambda e: abs((h_proj_bottom - e).days))
        desync_months = round(abs((h_proj_bottom - midterm_elec).days) / 30.4, 1)
        desync_flag = bool(desync_months > _DESYNC_MONTHS)
        add("desync", "watch" if desync_flag else "ok",
            (f"Halving and political clocks DIVERGING (halving-anchored bottom ~{h_proj_bottom:%b %Y} "
             f"vs midterm {midterm_elec:%b %Y}, ~{desync_months}mo apart) — trust the halving."
             if desync_flag else
             f"Halving and midterm clocks aligned this cycle (halving-anchored bottom "
             f"~{h_proj_bottom:%b %Y}, midterm {midterm_elec:%b %Y})."),
            (f"减半与政治周期出现背离（减半锚定底部约 {h_proj_bottom:%Y-%m}，中期 {midterm_elec:%Y-%m}，"
             f"相差约 {desync_months} 个月）——以减半为准。" if desync_flag else
             f"本轮减半与中期周期一致（减半锚定底部约 {h_proj_bottom:%Y-%m}，中期 {midterm_elec:%Y-%m}）。"))

    # 5) pivot-staleness alarm (W2, masterplan N8): nothing previously detected that the
    #    hand-recorded config pivots had gone stale vs a LIVE extreme. If the phase clock
    #    claims we are PAST a top (last pivot = a top) yet price has set its running
    #    all-time-high close more than the pivot tolerance AFTER that recorded top, the
    #    anchor is dead — every phase/percent read downstream is fiction until config.yml
    #    (vector.cycle_phase_clock.tops) is updated. Markup legs are exempt: new ATHs are
    #    the EXPECTED behavior there, and the next top is only recordable in hindsight.
    pivot_stale = False
    past_bottoms = [b for b in bottoms if b <= now]
    last_bottom = max(past_bottoms) if past_bottoms else None
    if peak_date is not None and (last_bottom is None or peak_date > last_bottom):
        hist = close.loc[:now]
        ath_date = hist.idxmax()
        pivot_stale = bool(ath_date > peak_date + pd.Timedelta(days=_PIVOT_SLACK_D))
        if pivot_stale:
            add("pivot_staleness", "alert",
                f"STALE PIVOT REGISTRY: price set its all-time-high close on {ath_date:%Y-%m-%d}, "
                f"after the last recorded cycle top ({peak_date:%Y-%m-%d}) — the configured pivots "
                f"no longer describe the tape. Update vector.cycle_phase_clock.tops; every "
                f"phase/timing read is unreliable until then.",
                f"枢轴登记已过期：价格于 {ath_date:%Y-%m-%d} 创下历史最高收盘，晚于最后记录的周期顶部"
                f"（{peak_date:%Y-%m-%d}）——配置的枢轴已无法描述行情。请更新 "
                f"vector.cycle_phase_clock.tops；在此之前所有阶段/时点读数均不可靠。")

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
        # halving-anchored lens (W2, N8): derived from observed halving→bottom gaps
        "halving_window_start": h_win_start.strftime("%Y-%m-%d") if h_win_start is not None else None,
        "halving_window_end": h_win_end.strftime("%Y-%m-%d") if h_win_end is not None else None,
        "halving_proj_bottom": h_proj_bottom.strftime("%Y-%m-%d") if h_proj_bottom is not None else None,
        "halving_bottom_gaps_d": halving_gaps,
        "halving_overdue": halving_overdue,
        "pivot_stale": pivot_stale,
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
