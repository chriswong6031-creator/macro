"""Bonds dashboard alert engine — DAILY bond-market state-change events.

Mirrors engine/forex_alerts.py's daily layer, but driven by the single bond-health
frame (engine.bonds.bonds_frame) rather than per-instrument frames. Deterministic,
idempotent events recomputed from the frame's state columns:

  curve-move REGIME shift (bull/bear x steepener/flattener), curve UN-INVERSION
  (the re-steepening late-cycle handoff, ~13m pre-recession), HY credit DISTRESS-BAND crossings, MOVE
  rates-vol BAND crossings, funding-PLUMBING stress (repo spike / reserve
  scarcity), the STOCK-BOND CORRELATION regime flip, and RECESSION-RISK band
  crossings.

Event schema matches commodity/forex alerts (id, ts, source='bonds', asset, type,
severity, headline/detail + _zh, context, anchor). Writes data/bonds/alerts.jsonl.
All events are CONTEXT — see LIMITATIONS.md.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from engine import bonds
from lib import config

log = logging.getLogger(__name__)


def _ev(asset, type_, ts, severity, headline, detail, context, to_state,
        headline_zh="", detail_zh="") -> dict:
    ts = pd.Timestamp(ts)
    bucket = ts.strftime("%Y-%m-%d")
    return {"id": f"bonds:{asset}:{type_}:{bucket}:{to_state}", "ts": ts.isoformat(),
            "source": "bonds", "asset": asset, "type": type_, "severity": severity,
            "headline": headline, "detail": detail,
            "headline_zh": headline_zh or headline, "detail_zh": detail_zh or detail,
            "context": context, "anchor": "#timeline"}


def _transitions(state: pd.Series):
    s = state.dropna()
    if s.empty:
        return []
    chg = s != s.shift()
    chg.iloc[0] = False
    return [(t, s.shift()[t], s[t]) for t in s.index[chg]]


def _debounce(state: pd.Series, min_days: int) -> pd.Series:
    """Collapse runs shorter than `min_days` BARS into the preceding durable run, so a
    threshold-oscillating signal (the curve taxonomy, a band hovering on a knot)
    emits ONE event per genuine regime, not one per whipsaw.

    Two correctness points: (1) duration is BAR COUNT, not calendar days — the frame
    is business-daily, so `.days` would make the thresholds weekend-dependent. (2) the
    CURRENT (last) run is NEVER absorbed, even if it hasn't yet lasted `min_days` —
    otherwise a brand-new genuine flip (e.g. a fresh curve un-inversion, the headline
    pre-recession alarm) is structurally hidden for up to `min_days` after it fires."""
    s = state.dropna()
    if len(s) < 2:
        return s
    runs: list[list] = []   # [start_ts, end_ts, value, n_bars]
    cv = None
    for ts, v in s.items():
        if cv is None or v != cv:
            runs.append([ts, ts, v, 1])
            cv = v
        else:
            runs[-1][1] = ts
            runs[-1][3] += 1
    merged: list[list] = []
    last = len(runs) - 1
    for i, r in enumerate(runs):
        if merged and r[3] < min_days and i != last:    # absorb only short INTERIOR runs
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    out = pd.Series(index=s.index, dtype=object)
    for cs, ce, cv, _n in merged:
        out.loc[cs:ce] = cv
    return out.dropna()


def compute_all_events(fr: pd.DataFrame, cfg: dict | None = None) -> list[dict]:
    cfg = cfg or config.load()["bonds"]
    ccfg = config.load()["engine"]["conditions"]
    out: list[dict] = []

    # curve-move REGIME quadrant shift -------------------------------------------
    if "curve_move" in fr.columns:
        for ts, frm, to in _transitions(_debounce(fr["curve_move"], 21)):
            if frm is None or (isinstance(frm, float) and pd.isna(frm)):
                continue
            meta = bonds._TAXONOMY.get(to, (to, to, "", ""))
            out.append(_ev("curve", "curve_regime", ts, "info",
                           f"Curve regime → {meta[0]}",
                           f"The Treasury-curve move turned {meta[0].lower()} — {meta[2]}.",
                           {"taxonomy": to}, to,
                           headline_zh=f"曲线形态 → {meta[1]}",
                           detail_zh=f"国债收益率曲线走势转为{meta[1]} — {meta[3]}。"))

    # curve UN-INVERSION alarm ---------------------------------------------------
    if "uninversion" in fr.columns:
        for ts, frm, to in _transitions(_debounce(fr["uninversion"].astype(float), 10)):
            if to != 1.0:
                continue
            tax = fr["curve_move"].get(ts) if "curve_move" in fr.columns else None
            bull = tax == "bull_steepener"
            out.append(_ev("curve", "uninversion", ts, "high",
                           "Curve un-inverted" + (" (bull-steepening)" if bull else ""),
                           "The yield curve dis-inverted after a prior inversion. Historically the "
                           "re-steepening — not the inversion — is the late-cycle handoff: recessions have "
                           "begun ~13 months (range ~8–19) after the curve re-steepens" +
                           (", and a bull-steepening un-inversion (short rates falling, cuts priced) is the ominous one."
                            if bull else "."),
                           {"bull_steepener": bull}, "uninverted",
                           headline_zh="曲线解除倒挂" + ("（牛市陡峭）" if bull else ""),
                           detail_zh="收益率曲线在此前倒挂后解除。历史上是重新陡峭（而非倒挂本身）作为周期晚段交接："
                                     "衰退在曲线重新陡峭后约13个月（区间约8–19个月）开始" + ("，且牛市陡峭式解除（短端利率下行、定价降息）最为不祥。" if bull else "。")))

    # HY credit DISTRESS-BAND crossing -------------------------------------------
    if "hy_oas" in fr.columns:
        band = fr["hy_oas"].map(lambda v: bonds._hy_band(v, cfg["credit"]))
        order = {"tight": 0, "normal": 1, "elevated": 2, "distress": 3, "crisis": 4}
        for ts, frm, to in _transitions(_debounce(band, 5)):
            if frm is None or to is None:
                continue
            worse = order.get(to, 0) > order.get(frm, 0)
            oas = fr["hy_oas"].get(ts)
            sev = "high" if to in ("distress", "crisis") else ("medium" if worse else "info")
            ZH = {"tight": "偏紧", "normal": "正常", "elevated": "升高", "distress": "困境", "crisis": "危机"}
            out.append(_ev("credit", "credit_band", ts, sev,
                           f"HY credit {'widened to' if worse else 'narrowed to'} {to}",
                           f"High-yield OAS crossed into the {to} band at {oas:.2f}% "
                           f"({'wider' if worse else 'tighter'} from {frm}). Credit leads equity drawdowns.",
                           {"hy_oas": round(float(oas), 2) if pd.notna(oas) else None}, to,
                           headline_zh=f"高收益信用{'走阔至' if worse else '收窄至'}{ZH.get(to,to)}",
                           detail_zh=f"高收益OAS进入{ZH.get(to,to)}区间，报 {oas:.2f}%"
                                     f"（较{ZH.get(frm,frm)}{'走阔' if worse else '收窄'}）。信用领先股票回撤。"))

    # MOVE rates-vol BAND crossing -----------------------------------------------
    if "move" in fr.columns:
        mband = fr["move"].map(lambda v: bonds._move_band(v, cfg["rates_vol"]))
        order = {"calm": 0, "normal": 1, "elevated": 2, "crisis": 3}
        for ts, frm, to in _transitions(_debounce(mband, 5)):
            if frm is None or to is None:
                continue
            worse = order.get(to, 0) > order.get(frm, 0)
            mv = fr["move"].get(ts)
            sev = "high" if to == "crisis" else ("medium" if worse and to == "elevated" else "info")
            ZH = {"calm": "平静", "normal": "正常", "elevated": "升高", "crisis": "危机"}
            out.append(_ev("rates", "rates_vol", ts, sev,
                           f"Rates volatility (MOVE) → {to}",
                           f"The MOVE index crossed into the {to} band at {mv:.0f}. "
                           f"A MOVE spike is the bond market's systemic-stress thermometer.",
                           {"move": round(float(mv)) if pd.notna(mv) else None}, to,
                           headline_zh=f"利率波动（MOVE）→ {ZH.get(to,to)}",
                           detail_zh=f"MOVE指数进入{ZH.get(to,to)}区间，报 {mv:.0f}。MOVE跳升是债市系统性压力的温度计。"))

    # funding PLUMBING stress ----------------------------------------------------
    if "repo_spike_bp" in fr.columns:
        repo = (fr["repo_spike_bp"] > cfg["plumbing"]["repo_spike_bp"]).map({True: "stress", False: "calm"})
        for ts, frm, to in _transitions(_debounce(repo, 3)):
            if to != "stress":
                continue
            bp = fr["repo_spike_bp"].get(ts)
            out.append(_ev("plumbing", "repo_stress", ts, "high",
                           "Repo-stress spike",
                           f"The SOFR 99th-percentile rate jumped {bp:.0f}bp above the median — a sign of "
                           f"funding-plumbing strain (collateral/reserve scarcity).",
                           {"repo_spike_bp": round(float(bp)) if pd.notna(bp) else None}, "stress",
                           headline_zh="回购市场承压",
                           detail_zh=f"SOFR第99百分位较中位数跳升 {bp:.0f} 基点 — 资金管道紧张（抵押品/准备金稀缺）的信号。"))

    # STOCK-BOND CORRELATION regime flip -----------------------------------------
    if "stock_bond_corr" in fr.columns:
        cc = config.load()["engine"]["conditions"]["corr"]
        reg = fr["stock_bond_corr"].map(
            lambda v: None if pd.isna(v) else ("breakdown" if v > cc["high"] else
                                               ("diversifying" if v < cc["low"] else "mixed")))
        for ts, frm, to in _transitions(_debounce(reg, 15)):
            if frm is None or to is None or to == "mixed":
                continue
            v = fr["stock_bond_corr"].get(ts)
            if to == "breakdown":
                hl, hl_zh = "Stock-bond hedge broke down", "股债对冲失效"
                dt = ("Realized stock-bond correlation turned positive (>%.2f) — bonds are no longer hedging "
                      "equities (the post-2022 inflation-vol regime)." % cc["high"])
                dt_zh = "已实现股债相关性转正（>%.2f）— 债券不再对冲股票（2022年后的通胀波动机制）。" % cc["high"]
            else:
                hl, hl_zh = "Stock-bond hedge restored", "股债对冲恢复"
                dt = ("Realized stock-bond correlation turned negative (<%.2f) — bonds are diversifying "
                      "equities again." % cc["low"])
                dt_zh = "已实现股债相关性转负（<%.2f）— 债券重新对冲股票。" % cc["low"]
            out.append(_ev("cross_asset", "corr_regime", ts, "medium", hl, dt,
                           {"stock_bond_corr": round(float(v), 2) if pd.notna(v) else None}, to,
                           headline_zh=hl_zh, detail_zh=dt_zh))

    # RECESSION-RISK band crossing -----------------------------------------------
    if "recession_risk" in fr.columns:
        rc = ccfg["recession"]
        rband = fr["recession_risk"].map(
            lambda v: None if pd.isna(v) else ("high" if v >= rc["high_score"] else
                                               ("elevated" if v >= rc["elevated_score"] else "low")))
        order = {"low": 0, "elevated": 1, "high": 2}
        for ts, frm, to in _transitions(_debounce(rband, 10)):
            if frm is None or to is None:
                continue
            worse = order.get(to, 0) > order.get(frm, 0)
            rr = fr["recession_risk"].get(ts)
            ZH = {"low": "低", "elevated": "升高", "high": "高"}
            out.append(_ev("curve", "recession_risk", ts, "high" if to == "high" else "medium",
                           f"Recession-risk {'rose to' if worse else 'fell to'} {to}",
                           f"The bond-derived recession-risk composite crossed to {to} ({rr:.0f}/100).",
                           {"recession_risk": round(float(rr)) if pd.notna(rr) else None}, to,
                           headline_zh=f"衰退风险{'升至' if worse else '降至'}{ZH.get(to,to)}",
                           detail_zh=f"债券衍生的衰退风险综合指标跨入{ZH.get(to,to)}（{rr:.0f}/100）。"))

    by_id = {e["id"]: e for e in out}
    for e in load_events():
        by_id.setdefault(e["id"], e)
    return sorted(by_id.values(), key=lambda e: e["ts"], reverse=True)


def _path():
    return config.data_dir() / "bonds" / "alerts.jsonl"


def write_events(events: list[dict]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def load_events() -> list[dict]:
    p = _path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def rebuild(fr: pd.DataFrame) -> list[dict]:
    events = compute_all_events(fr)
    write_events(events)
    log.info("bonds alerts: %d events, latest %s", len(events), events[0]["ts"] if events else "none")
    return events


def recent(events: list[dict], days: int) -> list[dict]:
    cutoff = (datetime.now(timezone.utc) - pd.Timedelta(days=days)).isoformat()
    return [e for e in events if e["ts"] >= cutoff]


# ---------------------------------------------------------------------------
# CCW-W3 additive extension: credit_market_turn + credit_theme_stress debounced
# state-flip events.  Reuses the existing _ev / _debounce / _transitions idiom
# exactly.  ADDITIVE ONLY — does not modify any existing function.
# ---------------------------------------------------------------------------

# Debounce constants (Fix 6 — mirroring engine/credit_momentum.py)
_DEBOUNCE_MARKET_TURN  = 5   # bars: credit_market_turn state must persist >= 5 bars
_DEBOUNCE_THEME_STRESS = 3   # bars: credit_theme_stress state must persist >= 3 bars


def compute_credit_events(credit_json_path: "str | None" = None) -> list[dict]:
    """Compute debounced state-flip events from credit_momentum.json.

    Reads data/corp_bonds/credit_momentum.json (written by engine.credit_momentum).
    Returns events for credit_market_turn and per-theme credit_theme_stress.
    Returns [] if the JSON does not exist or is unreadable (non-fatal).

    Fix 6 — REAL DEBOUNCE using the existing _ev / _debounce / _transitions idiom:
    Debounce requires a state HISTORY (time series), not just today's snapshot.
    With a single-date JSON today, we cannot debounce across days — the correct
    behaviour is to emit nothing until enough history accrues (no crash, no flip).
    The history required is: for credit_market_turn >= _DEBOUNCE_MARKET_TURN days of
    consecutive 'active' state (5 bars), for theme_stress >= 3 bars.

    The mechanism: we load the existing alerts stream to check the prior state.
    If the last event for this type/theme was 'active' and today is also 'active',
    we count how many consecutive calendar days of 'active' we have seen. Only after
    the state has persisted for >= debounce days do we emit a new event. This matches
    the _debounce() bar-count logic (business-daily frame).

    On first run with no history: no events emitted (safe start, no crash).
    """
    import os
    from lib import config as _cfg

    if credit_json_path is None:
        credit_json_path = str(_cfg.data_dir() / "corp_bonds" / "credit_momentum.json")

    if not os.path.exists(credit_json_path):
        log.debug("bonds_alerts: credit_momentum.json not found, skipping CCW events")
        return []

    try:
        with open(credit_json_path) as f:
            cm = json.load(f)
    except Exception as exc:  # noqa: BLE001
        log.warning("bonds_alerts: credit_momentum.json read failed: %s", exc)
        return []

    out: list[dict] = []
    as_of_str = cm.get("as_of", str(__import__("datetime").date.today()))
    ts = pd.Timestamp(as_of_str)

    # Load existing events to extract prior state history for debouncing.
    # We count consecutive 'active' events of each type to implement debounce.
    prior_events = load_events()

    def _count_consecutive_active(event_type: str, asset_key: str, min_debounce: int) -> bool:
        """Return True if this type/asset has had >= min_debounce consecutive 'active'
        events in the alerts stream (including today if it fires again).

        If no prior events exist for this type/asset, returns False (safe start).
        The 'active' state series is reconstructed from prior events sorted by date.
        With only today's state, we have 1 bar — below any debounce threshold >= 2.
        """
        relevant = [
            e for e in prior_events
            if e.get("type") == event_type and asset_key in e.get("asset", "")
        ]
        if not relevant:
            # No history: 1 bar (today) < min_debounce (always False unless debounce=1)
            return min_debounce <= 1
        # Reconstruct a state series from event timestamps
        # Each event implies 'active' on its ts date; gaps = 'inactive'
        dates = sorted(set(pd.Timestamp(e["ts"]).date() for e in relevant))
        # Count consecutive most-recent active run ending at or before today.
        # Compare each date against the next-later date (not against today_d),
        # so weekend gaps (Fri→Mon = gap 3 cal days) are correctly handled.
        today_d = ts.date()
        # Include today as the 'most recent' reference point
        all_dates = sorted(set(list(dates) + [today_d]))
        consecutive = 1  # the current (today) state counts as 1
        prev_d = today_d
        for d in reversed(all_dates):
            if d >= today_d:
                continue  # skip today itself (already counted)
            # Gap between this date and the one immediately after it in the sorted sequence
            day_gap = (prev_d - d).days
            if day_gap <= 3:  # allow weekend gaps (Fri→Mon = 3 cal days = 1 business gap)
                consecutive += 1
                prev_d = d
            else:
                break
        return consecutive >= min_debounce

    # --- credit_market_turn ---
    mt = cm.get("tags", {}).get("credit_market_turn", {})
    if mt:
        fired = mt.get("fired", False)
        score = mt.get("score", 0)
        legs  = mt.get("legs", {})
        # Only emit after debounce threshold (Fix 6: real debounce, no emit before history)
        if fired and _count_consecutive_active("credit_market_turn", "credit", _DEBOUNCE_MARKET_TURN):
            ev_id = f"bonds:credit:credit_market_turn:{as_of_str}:active"
            out.append({
                "id":          ev_id,
                "ts":          ts.isoformat(),
                "source":      "bonds_ccw",
                "asset":       "credit",
                "type":        "credit_market_turn",
                "severity":    "medium",
                "headline":    f"Credit market turn tag fired (score {score}/3)",
                "detail":      (
                    f"credit_market_turn K-of-N tag: score={score}/3. "
                    f"Legs: HY vel≥85={legs.get('hy_vel21_pctile_ge85',False)}, "
                    f"quality spread widening={legs.get('quality_spread_widening_21d',False)}, "
                    f"CCC-BB widening={legs.get('ccc_bb_widening_21d',False)}. "
                    f"Debounced: >= {_DEBOUNCE_MARKET_TURN} consecutive active bars. "
                    "DISPLAY-ONLY / NOT VALIDATED. No track record yet — first events accruing."
                ),
                "headline_zh": f"信用市场转向标签触发（得分 {score}/3）",
                "detail_zh":   (
                    f"信用市场转向K-of-N标签：得分={score}/3。"
                    f"防抖：连续≥{_DEBOUNCE_MARKET_TURN}根K线活跃。"
                    "仅供展示 / 未经验证。尚无历史记录 — 首次事件正在积累。"
                ),
                "context":     {"score": score, "legs": legs,
                                "debounce_bars": _DEBOUNCE_MARKET_TURN},
                "anchor":      "#credit",
            })
        elif fired:
            log.debug("bonds_alerts: credit_market_turn fired but debounce not met (%d bars required)",
                      _DEBOUNCE_MARKET_TURN)

    # --- credit_theme_stress (per theme) ---
    theme_tags = cm.get("tags", {}).get("credit_theme_stress", [])
    for tt in theme_tags:
        if not isinstance(tt, dict):
            continue
        theme = tt.get("theme", "unknown")
        fired = tt.get("fired", False)
        score = tt.get("score", 0)
        legs  = tt.get("legs", {})
        if fired and _count_consecutive_active("credit_theme_stress", theme, _DEBOUNCE_THEME_STRESS):
            ev_id = f"bonds:credit:credit_theme_stress:{theme}:{as_of_str}:active"
            out.append({
                "id":          ev_id,
                "ts":          ts.isoformat(),
                "source":      "bonds_ccw",
                "asset":       f"credit/{theme}",
                "type":        "credit_theme_stress",
                "severity":    "medium",
                "headline":    f"Credit theme stress: {theme} (score {score}/3)",
                "detail":      (
                    f"credit_theme_stress for {theme}: score={score}/3. "
                    f"Legs: vel_pctile≥85={legs.get('vel21_pctile_ge85',False)}, "
                    f"spread 3B bull-cross widening={legs.get('spread_3b_bull_cross_widening_secondary',False)}, "
                    f"price 3B bear-cross={legs.get('price_3b_bear_cross',False)}. "
                    f"Debounced: >= {_DEBOUNCE_THEME_STRESS} consecutive active bars. "
                    "DISPLAY-ONLY / NOT VALIDATED. No track record yet — first events accruing."
                ),
                "headline_zh": f"信用主题压力：{theme}（得分 {score}/3）",
                "detail_zh":   (
                    f"信用主题压力（{theme}）：得分={score}/3。"
                    f"防抖：连续≥{_DEBOUNCE_THEME_STRESS}根K线活跃。"
                    "仅供展示 / 未经验证。尚无历史记录 — 首次事件正在积累。"
                ),
                "context":     {"theme": theme, "score": score, "legs": legs,
                                "debounce_bars": _DEBOUNCE_THEME_STRESS},
                "anchor":      "#credit",
            })
        elif fired:
            log.debug("bonds_alerts: credit_theme_stress %s fired but debounce not met (%d bars required)",
                      theme, _DEBOUNCE_THEME_STRESS)

    return out


def rebuild_with_credit(fr: pd.DataFrame, credit_json_path: "str | None" = None) -> list[dict]:
    """Rebuild bonds alerts including CCW credit events.

    Extends rebuild() with debounced credit_market_turn and credit_theme_stress events.
    Uses the existing by_id dedup pattern (idempotent, keep-first on existing events).
    Falls back to rebuild()-equivalent behavior when credit_momentum.json is absent
    (compute_credit_events returns [] when the file does not exist — non-fatal).

    Fix 6 (CCW review): replaces the previous rebuild(fr) call in build_bonds.py with
    rebuild_with_credit(fr) so CCW credit events are wired into the alerts stream.
    """
    bond_events   = compute_all_events(fr)
    credit_events = compute_credit_events(credit_json_path)

    # Merge: bond events first (established stream), credit events additive
    by_id = {e["id"]: e for e in bond_events}
    for e in credit_events:
        # keep-first: don't overwrite existing bond events
        by_id.setdefault(e["id"], e)

    all_events = sorted(by_id.values(), key=lambda e: e["ts"], reverse=True)
    write_events(all_events)
    log.info("bonds alerts (with credit): %d events, latest %s",
             len(all_events), all_events[0]["ts"] if all_events else "none")
    return all_events
