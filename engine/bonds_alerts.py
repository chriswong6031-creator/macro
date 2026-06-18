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
