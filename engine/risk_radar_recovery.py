"""Risk Radar DE-ESCALATION — the "risk has peaked / the risk-off may be ending" read.

DISPLAY-ONLY · LEAF · NEVER RAISES. The mirror image of the rising-risk radar. It surfaces
ONLY after the radar has been genuinely hot, when two things line up:

  (a) RISK DERATING — the radar's own intensity has peaked and the pullback odds are rolling
      over (engine/risk_radar.trajectory; leak-free, from the same causal sub-score history); and
  (b) a LIQUIDITY TURN — the macro money tide is turning supportive: Fed net liquidity expanding
      (TGA drawdown / reserves rising), the Fed pricing or signalling cuts (incl. an emergency
      cut), the PBoC easing (RRR / LPR), or the global central-bank balance-sheet tide
      (Fed + ECB + BoJ) expanding.

When risk DERATES while liquidity is INJECTED, history says the risk-off is often nearing its
end — so we ILLUSTRATE that turn (a "↘ receding / TURN" panel on the .rrx card) rather than
leave the user staring at a still-red alert.

HONESTY (this never moves money on its own):
  • The rising radar earns the right to CAP Market State because its legs cleared a strict
    forward-lift bar. This recovery read has NOT been forward-tested to that bar yet, so it is
    a CONTEXT ILLUSTRATION only. It is wired in as a display-only sibling field on the radar
    view-model and DOES NOT relax the radar's one-directional score ceiling
    (engine/market_state._radar_override) — the guardrail stays intact.
  • The de-risk → re-risk response is SIZING: scale exposure back in deliberately, in tranches,
    keep stops, let price confirm. Never a single buy call.
  • BoJ has no isolated easing detector freely available, so it enters ONLY via the aggregate
    global central-bank tide (global_liquidity, which sums Fed+ECB+BoJ); the chip says so.
  • Every input is display-only context already on the page; every field degrades to absent,
    never crashes the build.

MARKET CHANNEL (added W1, RRX-R2..R7):
  • engine/risk_radar_market_catalysts.py adds 7 market-internal confirmation chips (C1–C7)
    plus a vol-instability veto (C8). Each chip is ACCRUING / display-only — not forward-tested
    yet. Forward-grading is managed by engine/risk_radar_recovery_audit.py on the rebound ruler
    pre-declared in research/RISK_RADAR_EXPANSION_MASTERPLAN_BY_FABLE.md §3.
  • turn_confirmed_full (new sibling key) = liquidity channel AND market channel confirmed.
    The existing turn_confirmed field is UNCHANGED for backward compat.
  • channels dict (new sibling key) exposes {liquidity, market, veto} booleans separately.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

log = logging.getLogger(__name__)


def _num(v):
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None   # drop NaN
    except (TypeError, ValueError):
        return None


def _recent(date_str: str | None, days: int = 60) -> bool:
    """True if an ISO date string is within `days` of today (for the 'fresh' catalyst flag)."""
    if not date_str:
        return False
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (date.today() - d).days <= days
    except (TypeError, ValueError):
        return False


def _us_latest() -> dict:
    """The US regime latest.json — canonical source of the Fed net-liquidity overlay + reaction
    function. The intl (CN/HK/CA) latests don't carry these, but the Fed is a GLOBAL liquidity
    driver (US rate shocks are the #1 external lead in every intl radar profile), so the intl
    recovery reads them from here. Never raises."""
    try:
        import json
        from lib import config
        p = config.data_dir() / "regime" / "latest.json"
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception as e:  # noqa: BLE001
        log.debug("recovery: US latest unavailable (%s)", e)
        return {}


# --- liquidity-injection catalysts -------------------------------------------------------------
def _market_catalysts(latest: dict | None = None) -> dict | None:
    """Lazy import of engine/risk_radar_market_catalysts. Returns the compute() dict or None on
    any failure. latest is passed for future context-gating but currently unused by compute().
    NEVER raises.

    Hot-path note: this function is called on both the intraday fast-path
    (build_risk_state.py → market_state.market_state_snapshot → assess) and the nightly path
    (engine/run.py).  compute() itself is read-only (no ledger writes) and the result is
    stripped from risk_state.json by _verdict_block's key whitelist, so no ledger or banner
    mutation occurs intraday.  The per-tick I/O cost is ~4 store.read calls (breadth/SPY/_VIX
    /FRED) plus rolling/EMA/pct_rank_window; acceptable on the current 4-core box given the
    intraday tick rate (~1/min), but operator should revisit if tick frequency increases.
    """
    try:
        from engine import risk_radar_market_catalysts as _rmc
        return _rmc.compute()
    except Exception as e:  # noqa: BLE001
        log.debug("recovery: market catalysts unavailable (%s)", e)
        return None


def _liquidity_catalysts(latest: dict, market: str = "us") -> list[dict]:
    """The supportive-liquidity legs that are firing right now, as display chips. All read the
    display-only context already on the page; each degrades to absent. `fresh` = a genuinely
    recent turn (drives the chip glow). For the intl radars (market != 'us') the Fed legs are read
    from the US regime latest (a global driver). NEVER raises."""
    latest = latest or {}
    # Fed net-liq + reaction function: the US latest has them; the intl latests don't, so fall back
    # to the US regime latest (the Fed is a global liquidity driver for CN/HK/CA too).
    fed_src = latest if (market == "us" or latest.get("fed_stance")) else _us_latest()
    cats: list[dict] = []

    # 1) Fed net liquidity (WALCL − RRP − TGA). 'expanding' = the 20d ROC is positive, i.e. the
    #    balance sheet is adding reserves and/or the Treasury is drawing its account down (TGA
    #    drop). engine/regime.py classifies this into latest['liquidity_overlay'].
    lo = fed_src.get("liquidity_overlay")
    if lo == "expanding":
        cats.append({
            "key": "fed_netliq", "icon": "💵", "region": "US", "fresh": True,
            "label_en": "Fed liquidity expanding", "label_zh": "美联储流动性扩张",
            "detail_en": "Net liquidity (WALCL − RRP − TGA) rising — TGA drawdown / reserves added.",
            "detail_zh": "净流动性（WALCL − RRP − TGA）上升 — TGA 回落／准备金注入。",
        })

    # 2) Fed policy easing / emergency cut — market pricing + reaction-function read (display-only;
    #    engine/fed_path.py + engine/fed_stance.py). A large cut count = the emergency-cut case.
    fs = fed_src.get("fed_stance") or {}
    fp = fed_src.get("fed_path") or {}
    cuts = _num(fs.get("implied_cuts_12m"))
    if cuts is None:
        cuts = _num(fp.get("implied_cuts_12m"))
    dovish = (fs.get("stance") == "dovish")
    easing_guide = ((fs.get("guidance") or "") == "easing")
    if dovish or easing_guide or (cuts is not None and cuts >= 1.5):
        big = cuts is not None and cuts >= 3
        if cuts is not None and cuts >= 1:
            det_en = f"Market prices ~{cuts:.0f} cut{'s' if cuts >= 2 else ''} over 12m — dovish reaction function."
            det_zh = f"市场为未来12个月定价约{cuts:.0f}次降息 — 鸽派反应函数。"
        else:
            det_en = "Dovish Fed guidance — policy turning supportive."
            det_zh = "美联储鸽派指引 — 政策转向宽松。"
        cats.append({
            "key": "fed_policy", "icon": "🏛", "region": "US",
            "fresh": bool(easing_guide or big),
            "label_en": "Fed easing — aggressive" if big else "Fed easing / cuts priced",
            "label_zh": "美联储宽松（大幅）" if big else "美联储宽松／降息定价",
            "detail_en": det_en, "detail_zh": det_zh,
        })

    # 3) PBoC easing (RRR / LPR / money-market) — engine/china_pboc_stance.py. Relevant to the
    #    global liquidity tide, not just China. Lazy import: it is a China leaf the US latest may
    #    not carry.
    try:
        from engine import china_pboc_stance
        pb = china_pboc_stance.snapshot()
    except Exception as e:  # noqa: BLE001
        log.debug("recovery: pboc stance unavailable (%s)", e)
        pb = None
    if pb and pb.get("stance") == "easing":
        moves = pb.get("last_moves") or []
        fresh = any(m.get("easing") and _recent(m.get("date")) for m in moves)
        rat = pb.get("rationale") or {}
        cats.append({
            "key": "pboc", "icon": "🇨🇳", "region": "CN", "fresh": bool(fresh),
            "label_en": "PBoC easing", "label_zh": "中国央行宽松",
            "detail_en": rat.get("en") or "RRR / LPR cuts — PBoC adding liquidity.",
            "detail_zh": rat.get("zh") or "降准／降息 — 央行注入流动性。",
        })

    # 4) Global central-bank balance-sheet tide (Fed + ECB + BoJ, USD-summed) — engine/
    #    global_liquidity.py. This is the ONLY freely-available read of BoJ liquidity, so the BoJ
    #    leg lives here (the chip says so). Lazy import (not wired into the US latest).
    try:
        from engine import global_liquidity
        gl = global_liquidity.snapshot()
    except Exception as e:  # noqa: BLE001
        log.debug("recovery: global liquidity unavailable (%s)", e)
        gl = None
    if gl and gl.get("state") == "expanding":
        accel = gl.get("accel")
        imp = (gl.get("impulse_pct") or {}).get("13w")
        imp_txt = f"+{imp}%" if isinstance(imp, (int, float)) and imp > 0 else (f"{imp}%" if imp is not None else "")
        cats.append({
            "key": "global_cb", "icon": "🌊", "region": "GLOBAL",
            "fresh": (accel == "accelerating"),
            "label_en": "Global CB liquidity expanding", "label_zh": "全球央行流动性扩张",
            "detail_en": f"Fed + ECB + BoJ balance-sheet tide {imp_txt} (13w), {accel}.".replace("  ", " "),
            "detail_zh": f"美欧日央行资产负债表 13周 {imp_txt}（{accel}）。",
        })

    return cats


# --- the assembled recovery read ---------------------------------------------------------------
def assess(latest: dict) -> dict | None:
    """The display-only recovery view-model attached to market_state.radar.recovery. Returns
    {'present': False} when there is nothing to show, the full dict when the risk-off looks to be
    peaking / receding, or None when there is no trajectory at all. NEVER raises."""
    try:
        rr = (latest or {}).get("risk_radar") or {}
        traj = rr.get("trajectory")
        if not traj:
            return None
        market = rr.get("market") or "us"   # 'us' | 'cn' | 'hk' | 'ca' (intl reads Fed legs globally)
        phase = traj.get("phase")
        reached = bool(traj.get("reached_risk"))
        cats = _liquidity_catalysts(latest, market)
        n_cat = len(cats)
        n_fresh = sum(1 for c in cats if c.get("fresh"))

        # Market-internal confirmation channel (W1, accruing — not yet forward-tested).
        # US-ONLY: the chips read US stores (S&P breadth, SPY, VIX term, HY OAS) — attaching
        # them to the CN/HK/CA radar latests would render US internals on intl cards
        # (assess() serves BOTH call sites in engine/market_state.py). Intl ports are a
        # W5 docket (masterplan §5); until then the intl market channel is N/A, not False.
        mkt = _market_catalysts(latest) if market == "us" else None

        # Show ONLY once there was genuine risk to recede FROM, and it is no longer rising — OR a
        # broad liquidity turn is underway while the radar sits at/just past its peak.
        present = (reached and phase in ("peaking", "receding")) or \
                  (reached and phase != "rising" and n_fresh >= 2)
        if not present:
            return {"present": False}

        # ONE risk voice per page (2026-07-02 incident): the radar publishes the
        # de-escalation verdict beside its scares (risk_radar.deescalation); this
        # panel is a DERIVATIVE of it, not an independent opinion. When the radar
        # says not eligible (dominant risk-off scare escalating / pullback odds
        # rising), the green "receding" presentation is suppressed — the panel may
        # still narrate what IS fading, never an all-clear. Absent block (older
        # artifact) degrades to the standalone behavior.
        deesc = rr.get("deescalation")
        suppressed = bool(deesc) and deesc.get("eligible") is False

        receding = (phase == "receding") and not suppressed
        peaking = (phase == "peaking") and not suppressed
        turn_confirmed = bool(receding and n_fresh >= 1)   # risk derating + liquidity injection (UNCHANGED)

        # Market channel: accruing, not yet forward-tested. On intl radars (mkt is None by
        # the scoping above) the channel is N/A: channels.market / turn_confirmed_full stay
        # None so the card can distinguish "not confirmed" from "not applicable".
        if market == "us":
            mkt_confirmed = bool(mkt and mkt.get("market_confirmed"))
            mkt_veto = bool(mkt and mkt.get("veto", {}).get("active"))
            # turn_confirmed_full requires BOTH liquidity AND market channels
            turn_confirmed_full = bool(turn_confirmed and mkt_confirmed)
        else:
            mkt_confirmed = mkt_veto = turn_confirmed_full = None
        channels = {
            "liquidity": bool(n_fresh >= 1),
            "market": mkt_confirmed,
            "veto": mkt_veto,
        }

        off = traj.get("off_peak") or 0.0
        vel = traj.get("velocity") or 0.0
        # Modest, illustrative 0-100 strength: distance off the peak + how fast it is falling +
        # how broad the liquidity turn is. Capped; never implies precision it doesn't have.
        strength = int(max(0, min(100, round(
            off * 3.0 + max(0.0, -vel) * 3.5 + n_cat * 11 + n_fresh * 6 + (14 if receding else 0)))))

        odds_now = _num(traj.get("odds_now"))
        odds_peak = _num(traj.get("odds_peak"))
        odds_delta = _num(traj.get("odds_delta"))
        days = int(traj.get("peak_days_ago") or 0)

        # ---- bilingual copy ----
        if suppressed:
            dom_en = rr.get("dominant_label_en") or (rr.get("dominant_scare") or "risk")
            dom_zh = rr.get("dominant_label_zh") or "风险"
            fading = (deesc or {}).get("receding_scare")
            if fading:
                head_en = f"Mixed: {fading} scare fading — {dom_en} still escalating"
                head_zh = f"分化：{fading} 风险消退 — {dom_zh}仍在升级"
            else:
                head_en = f"Not receding — {dom_en} still escalating"
                head_zh = f"风险未回落 — {dom_zh}仍在升级"
        elif turn_confirmed:
            head_en, head_zh = "Risk receding — liquidity turning supportive", "风险回落 — 流动性转向支持"
        elif receding:
            head_en, head_zh = "Risk receding — pullback odds rolling over", "风险回落 — 回撤概率见顶回落"
        else:
            head_en, head_zh = "Risk may be peaking", "风险或已见顶"

        # one-line sub headline with the concrete odds turn
        if suppressed:
            sub_en = (deesc or {}).get("reason") or "The dominant scare is still escalating."
            sub_zh = "主导风险仍在升级，回撤概率上行。"
        elif odds_now is not None and odds_peak is not None and odds_peak > odds_now:
            sub_en = (f"Pullback odds {round(odds_peak*100)}% → {round(odds_now*100)}% "
                      f"(peaked {days} day{'s' if days != 1 else ''} ago).")
            sub_zh = f"回撤概率 {round(odds_peak*100)}% → {round(odds_now*100)}%（{days} 日前见顶）。"
        elif peaking:
            sub_en = f"Pullback odds have stopped climbing (peaked {days} day{'s' if days != 1 else ''} ago)."
            sub_zh = f"回撤概率已停止攀升（{days} 日前见顶）。"
        else:
            sub_en = "The radar's intensity is rolling over."
            sub_zh = "雷达强度正见顶回落。"

        if suppressed:
            do_en = ("An older scare is fading but the dominant one is still escalating — this is "
                     "rotation, not recovery. No all-clear: keep the de-risked posture and stops.")
            do_zh = ("旧风险消退但主导风险仍在升级 — 这是轮动而非复苏。并非解除警报：维持降险仓位与止损。")
        elif turn_confirmed:
            do_en = ("The risk-off may be nearing its end. Begin scaling exposure back in tranches — "
                     "keep stops, let price confirm the low. Don't chase the first bounce.")
            do_zh = ("避险或已接近尾声。可分批逐步回补敞口 — 保留止损，待价格确认低点，切勿追逐首次反弹。")
        elif receding:
            do_en = ("Odds are rolling over but no liquidity catalyst yet. Stop forced de-grossing; "
                     "ready a buy plan and wait for a liquidity turn to confirm.")
            do_zh = ("概率回落，但尚无流动性催化。停止被动减仓；备好买入计划，待流动性转向确认。")
        else:
            do_en = ("Risk has stopped climbing. Don't de-gross into the hole — ready a buy list and "
                     "wait for the roll-over (and a liquidity turn) before adding.")
            do_zh = ("风险已停止攀升。勿在低位被动减仓 — 备好买入清单，待见顶回落（及流动性转向）再加仓。")

        caveat_en = ("Illustrative context, not a buy trigger. It reads the radar's own intensity "
                     "trajectory (leak-free) plus the display-only central-bank liquidity series; "
                     "unlike the alert legs it is not forward-tested yet, and risk can re-accelerate. "
                     "The de-risk → re-risk response is sizing, scaled in deliberately. BoJ enters "
                     "only via the aggregate global central-bank tide (no isolated BoJ feed).")
        caveat_zh = ("仅为示意性背景，并非买入信号。它读取雷达自身的强度轨迹（无未来函数）以及仅供展示的"
                     "央行流动性序列；不同于警报腿，此读数尚未经前瞻检验，风险可能再度加速。降险→回补的"
                     "应对是仓位管理、分批进行。日本央行仅通过全球央行总潮汐体现（无独立日本数据源）。")

        # RRX2 WA-3: mirror the drivers block (which scares faded / warm) from trajectory.
        # Old artifacts without a drivers key → None → template renders nothing.
        drivers = traj.get("drivers")

        return {
            "present": True,
            "phase": phase, "receding": receding, "peaking": peaking,
            # radar-derived gate (one risk voice): green suppressed while the
            # dominant scare escalates; mirrored for the template/bot to read
            "suppressed": suppressed, "deescalation": deesc,
            "turn_confirmed": turn_confirmed, "strength": strength,
            # --- W1 market-channel additions (sibling keys, never wrappers — RRX-R7) ---
            # market_confirmed_raw and market_confirmed are the raw chip outputs
            "market": mkt,
            "turn_confirmed_full": turn_confirmed_full,
            "channels": channels,
            # the odds turn + velocity (mirrored from the trajectory so the template reads one dict)
            "odds_now": odds_now, "odds_peak": odds_peak, "odds_delta": odds_delta,
            "peak_days_ago": days, "velocity": vel, "off_peak": off,
            "intensity": _num(traj.get("intensity")), "peak": _num(traj.get("peak")),
            # sparkline (pre-scaled in engine/risk_radar.trajectory)
            "spark": traj.get("spark"), "spark_pts": traj.get("spark_pts"),
            "spark_peak": traj.get("spark_peak"), "spark_last": traj.get("spark_last"),
            "spark_w": traj.get("spark_w"), "spark_h": traj.get("spark_h"),
            # catalysts
            "catalysts": cats, "n_catalysts": n_cat, "n_fresh": n_fresh,
            # RRX2 WA-3: drivers line (which scares faded / still warm); None on old artifacts
            "drivers": drivers,
            # copy
            "headline_en": head_en, "headline_zh": head_zh,
            "sub_en": sub_en, "sub_zh": sub_zh,
            "do_en": do_en, "do_zh": do_zh,
            "caveat_en": caveat_en, "caveat_zh": caveat_zh,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("risk_radar_recovery assess failed: %s", e)
        return None
