"""scripts/build_index_leadership.py — the Index Leadership layer for subsectors.html.

A DECOUPLED post-pass: reads the four ALREADY-COMMITTED confluence boards
(subsector_confluence[.|_nasdaq|_russell].json + basket_confluence.json), their
per-group OHLC sidecars (site/subsectorohlc*/), and the index / style ETF parquets,
then writes ``site/marketdata/index_leadership.json`` — consumed client-side by
subsectors.js to render the RISING-STAR strip, the leadership-driver ratios, and the
per-tab RUNNING / COILING lists.

Because it reads committed artefacts (never re-runs the heavy T1-T4 confluence engine),
it is safe + cheap to call from the render lane (build_site) on every build. Additive,
never fatal. See engine/index_leadership.py for the honesty contract (display-only,
cross-sectional over 4 tabs, not scored).
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine import index_leadership as il
from lib import config

log = logging.getLogger(__name__)

OUT_JSON = "marketdata/index_leadership.json"

# tab → representative index ETF · confluence board JSON · OHLC sidecar dir · file-key prefix ·
# the array key inside the board · bilingual label.
TABS = {
    "subsectors": {"rep": "SPY", "json": "marketdata/subsector_confluence.json",
                   "ohlc": "subsectorohlc", "prefix": "", "groups": "subsectors",
                   "label": ("S&P 500", "标普500")},
    "nasdaq": {"rep": "QQQ", "json": "marketdata/subsector_confluence_nasdaq.json",
               "ohlc": "subsectorohlc_nasdaq", "prefix": "", "groups": "subsectors",
               "label": ("Nasdaq-100", "纳斯达克100")},
    "russell": {"rep": "IWM", "json": "marketdata/subsector_confluence_russell.json",
                "ohlc": "subsectorohlc_russell", "prefix": "", "groups": "subsectors",
                "label": ("Russell-2000", "罗素2000")},
    "baskets": {"rep": None, "json": "marketdata/basket_confluence.json",
                "ohlc": "subsectorohlc", "prefix": "b-", "groups": "baskets",
                "label": ("Thematic Baskets", "主题篮子")},
}

# leadership-driver ratios: (numerator, denominator, key, EN/ZH label, EN/ZH read when the ratio
# is RISING, EN/ZH read when FALLING). These are the observable "why leadership sits here" reads.
DRIVERS = [
    ("RSP", "SPY", "breadth", ("Breadth of leadership", "领导广度"),
     ("equal-weight ÷ cap-weight", "等权 ÷ 市值加权"),
     ("broadening — the average stock is leading (healthy)", "扩散——普通个股在领跑（健康）"),
     ("narrowing — leadership concentrating in mega-caps (fragile)", "收窄——领导集中于超大盘（脆弱）")),
    ("IWM", "SPY", "size", ("Small ÷ large cap", "小盘 ÷ 大盘"),
     ("IWM ÷ SPY", "IWM ÷ SPY"),
     ("small-caps leading — risk-on / reflationary", "小盘领涨——风险偏好/再通胀"),
     ("large-caps leading — defensive / late-cycle", "大盘领涨——防御/周期后段")),
    ("IWF", "IWD", "style", ("Growth ÷ value", "成长 ÷ 价值"),
     ("IWF ÷ IWD", "IWF ÷ IWD"),
     ("growth leading — duration bid / disinflation", "成长领涨——久期偏好/去通胀"),
     ("value leading — rates / reflation", "价值领涨——利率/再通胀")),
    ("XLK", "RSP", "tech", ("Tech ÷ broad market", "科技 ÷ 大盘"),
     ("XLK ÷ RSP (equal-weight)", "XLK ÷ RSP（等权）"),
     ("tech leadership — mega-cap / duration bid", "科技领导——超大盘/久期偏好"),
     ("ex-tech broadening — rotation out of tech", "非科技扩散——资金轮出科技")),
]

# The macro CAUSE behind the observed leadership ratios — answering the user's "is it quads?
# rates? liquidity?". Maps the slow growth×inflation quad (engine.regime → regime_timeline.json)
# to the EXPECTED size/style/tech tilt (evidence base: engine.playbook). An ODDS-TILT + veto,
# not a rule — the codebase's own backtests find no stable monthly cross-sector edge from quad
# alone (momentum-persistence is the reliable part), so the page shows it as context to compare
# against what is ACTUALLY leading, never as a signal.
REGIME_TILT = {
    "Q1": {"name": ("Goldilocks", "金发女孩"), "axes": ("growth↑ · inflation↓", "增长↑ · 通胀↓"),
           "tilt": ("growth ≥ value, long-duration tech can lead (disinflation); broadens if liquidity expands",
                    "成长≥价值，长久期科技可领涨（去通胀）；流动性扩张则广度扩散")},
    "Q2": {"name": ("Reflation", "再通胀"), "axes": ("growth↑ · inflation↑", "增长↑ · 通胀↑"),
           "tilt": ("value / cyclicals & small-caps lead, ex-tech broadening (rising rates cap duration)",
                    "价值/周期与小盘领涨，非科技扩散（利率上行压制久期）")},
    "Q3": {"name": ("Stagflation", "滞胀"), "axes": ("growth↓ · inflation↑", "增长↓ · 通胀↑"),
           "tilt": ("large-cap defensive, value > growth, ex-tech (rising real rates hurt duration) — historically the weakest quad",
                    "大盘防御，价值>成长，非科技（实际利率上行伤久期）——历史上最弱象限")},
    "Q4": {"name": ("Deflation / growth-scare", "通缩 / 增长恐慌"), "axes": ("growth↓ · inflation↓", "增长↓ · 通胀↓"),
           "tilt": ("large-cap quality & defensives; growth / duration can bid late if real rates fall",
                    "大盘优质与防御；若实际利率下行，成长/久期后段可获买盘")},
}
_LIQ_MOD = {
    "expanding": (" · liquidity expanding supports small-caps & broadening (risk-on)",
                  " · 流动性扩张支撑小盘与广度（风险偏好）"),
    "contracting": (" · liquidity contracting favors large-cap & narrowing (risk-off)",
                    " · 流动性收缩利好大盘与收窄（避险）"),
}


def _clean(o):
    if isinstance(o, np.generic):
        o = o.item()
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _read_json(p: Path):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return None


def _market_state() -> dict | None:
    """The canonical US market-state snapshot (engine.market_state → data/market_state/
    latest.json): {verdict, color, score, label_*, headline_*, asof}. The macro backdrop
    the COILING (counter-trend bottoming) list must respect — bottoming into a risk-off
    tape is the riskiest trade there is."""
    return _read_json(config.data_dir() / "market_state" / "latest.json")


def _macro_severity(ms: dict | None) -> str | None:
    if not ms:
        return None
    c, v = (ms.get("color") or "").lower(), (ms.get("verdict") or "").upper()
    if c == "red" or "RISK_OFF" in v:
        return "risk_off"
    if c == "yellow" or v in ("MIXED", "NEUTRAL"):
        return "mixed"
    if c == "green" or "RISK_ON" in v:
        return "risk_on"
    return None


def _regime_context(site: Path) -> dict | None:
    """The slow growth×inflation quad backdrop (engine.regime → site/regime_timeline.json)
    mapped to the EXPECTED leadership tilt — the macro CAUSE to compare against the observed
    ratios. Distinct from the fast market-state tape (`macro`): the quad can be Goldilocks
    while the tape is risk-off. Odds-tilt, not a rule (see REGIME_TILT)."""
    d = _read_json(site / "regime_timeline.json")
    if not d:
        return None

    def _last(k):
        v = d.get(k) or []
        return v[-1] if v else None

    quad = _last("quad")
    if quad not in REGIME_TILT:
        return None
    liq = (_last("liq") or "").lower()
    m = REGIME_TILT[quad]
    mod = _LIQ_MOD.get(liq, ("", ""))
    return {
        "quad": quad, "name_en": m["name"][0], "name_zh": m["name"][1],
        "axes_en": m["axes"][0], "axes_zh": m["axes"][1],
        "growth": _last("g"), "inflation": _last("i"), "conf": _last("conf"),
        "liquidity": liq or None, "as_of": _last("dates"),
        "tilt_en": m["tilt"][0] + mod[0], "tilt_zh": m["tilt"][1] + mod[1],
    }


def _etf_close(ticker: str) -> pd.Series | None:
    p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    if "close" not in df:
        return None
    s = df["close"].dropna()
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _sidecar_close(site: Path, ohlc_dir: str, fname: str) -> pd.Series | None:
    """Load the close column out of a committed OHLC sidecar (§7 chart contract:
    bars = [[date, o, h, l, close, dollar_vol], ...])."""
    d = _read_json(site / ohlc_dir / f"{fname}.json")
    if not d:
        return None
    idx, vals = [], []
    for b in d.get("bars") or []:
        if len(b) >= 5 and b[4] is not None:
            idx.append(b[0])
            vals.append(float(b[4]))
    if len(vals) < 6:
        return None
    return pd.Series(vals, index=pd.to_datetime(idx)).sort_index()


def _composite(closes: list[pd.Series]) -> pd.Series | None:
    """Equal-weight normalised composite of a set of close series (the baskets tab has no
    single index ETF, so its 'index return' is the average of its baskets)."""
    norm = []
    for c in closes:
        c = c.dropna()
        if len(c) >= 30 and float(c.iloc[0]) != 0:
            norm.append(c / float(c.iloc[0]))
    if not norm:
        return None
    return pd.concat(norm, axis=1).sort_index().mean(axis=1).dropna()


def compute(site: Path) -> dict | None:
    """Assemble the index_leadership payload from committed artefacts. None if the boards
    are missing entirely."""
    tab_reps: dict[str, dict] = {}
    tab_breadth: dict[str, float | None] = {}
    tab_partic: dict[str, float | None] = {}
    tab_out: dict[str, dict] = {}
    as_of = None
    spy = _etf_close("SPY")  # coil rs-hold benchmark for the baskets tab
    macro = _market_state()
    macro_sev = _macro_severity(macro)  # 'risk_on' | 'mixed' | 'risk_off' | None
    member_map: dict[str, list] = {}  # 'tab:key' -> frozen member tickers (forward track-record)

    for tab, cfg in TABS.items():
        board = _read_json(site / cfg["json"])
        if not board or not board.get("ok"):
            continue
        as_of = as_of or board.get("as_of")
        groups = board.get(cfg["groups"]) or []

        gi: dict[str, dict] = {}
        closes: list[pd.Series] = []
        closes_by_key: dict[str, pd.Series] = {}
        for g in groups:
            key = g.get("key")
            if not key or not g.get("chart_key"):
                continue
            close = _sidecar_close(site, cfg["ohlc"], cfg["prefix"] + key)
            if close is None:
                continue
            closes.append(close)
            closes_by_key[key] = close
            member_map[f"{tab}:{key}"] = [m.get("ticker") for m in (g.get("members") or [])
                                          if isinstance(m, dict) and m.get("ticker")]
            reg, entry = g.get("regime") or {}, g.get("entry") or {}
            gi[key] = {
                "hz": il.horizon_returns(close),
                "label": g.get("label"), "sector": g.get("sector"),
                "regime_state": reg.get("state"), "regime_side": reg.get("side"),
                "rs_60d": reg.get("rs_60d"), "entry_tier": entry.get("tier"),
                "above200": entry.get("above200"), "n_priced": g.get("n_priced") or g.get("n_members"),
            }
        if not gi:
            continue

        within = il.within_tab_rotation(gi)
        # representative index return: the ETF (index tabs) or the equal-weight composite (baskets).
        rep_close = _etf_close(cfg["rep"]) if cfg["rep"] else _composite(closes)
        tab_reps[tab] = il.horizon_returns(rep_close)
        tab_breadth[tab] = il.breadth_thrust(closes)
        tab_partic[tab] = within["participation"]["frac_improving"]

        # Phase 2 — confirm each COILING (RRG 'improving') candidate against the higher
        # timeframe: run the multi-factor coil assessment and DROP the ones that are only a
        # bounce inside a confirmed weekly / 2-week / monthly downtrend (stage='knife').
        # Phase 3 — the MACRO backdrop veto: bottoming is counter-trend, so a risk-off broad
        # tape holds coils back — no 'primed' call against a risk-off market, a score haircut,
        # and a macro_caution flag ("let washouts confirm before buying").
        coil_bench = rep_close if cfg["rep"] else spy
        coiled, n_knife = [], 0
        for e in within["coiling"][:20]:
            ca = il.coil_assess(closes_by_key.get(e["key"]), bench=coil_bench)
            if ca and ca["stage"] == "knife":
                n_knife += 1
                continue
            if ca and macro_sev == "risk_off":
                ca = {**ca, "macro_caution": True,
                      "stage": "coiling" if ca["stage"] == "primed" else ca["stage"],
                      "coil_score": round(max(0.0, ca["coil_score"] - 10.0), 1)}
            coiled.append({**e, "coil": ca} if ca else e)
        coiled.sort(key=lambda e: (e.get("coil") or {}).get("coil_score", -1.0), reverse=True)

        tab_out[tab] = {
            "label": list(cfg["label"]),
            "rising": within["rising"][:12],
            "coiling": coiled[:12], "coil_filtered": n_knife,
            "participation": within["participation"],
        }

    if not tab_reps:
        return None

    cross = il.cross_tab_leadership(tab_reps, tab_breadth, tab_partic)
    for tab, c in cross["tabs"].items():
        tab_out[tab].update(c)

    # rising-star "why": the legs (return / breadth / participation) contributing most.
    rs_tab = cross["rising_star"]
    why = []
    if rs_tab:
        legs = [("return acceleration", "return_accel", tab_out[rs_tab]["z_return"]),
                ("breadth thrust", "breadth", tab_out[rs_tab]["z_breadth"]),
                ("broad participation", "participation", tab_out[rs_tab]["z_participation"])]
        why = [{"leg": name, "z": z} for name, _k, z in sorted(legs, key=lambda x: x[2], reverse=True) if z > 0]

    # leadership-driver ratios.
    px = {t: _etf_close(t) for t in {"SPY", "QQQ", "IWM", "RSP", "IJH", "IWF", "IWD", "XLK"}}
    ratios = []
    for num, den, key, lab, sub, hi, lo in DRIVERS:
        r = il.ratio_read(px.get(num), px.get(den))
        if r is None:
            continue
        rising = (r.get("mom20") or 0) >= 0
        ratios.append({
            "key": key, "label_en": lab[0], "label_zh": lab[1], "sub_en": sub[0], "sub_zh": sub[1],
            "read_en": (hi[0] if rising else lo[0]), "read_zh": (hi[1] if rising else lo[1]),
            "rising": rising, **r,
        })

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "ok": True, "generated_utc": generated, "as_of": as_of,
        "weights": {"return": 0.40, "breadth": 0.30, "participation": 0.30},
        "rising_star": ({"tab": rs_tab, "label": tab_out[rs_tab]["label"],
                         "las": tab_out[rs_tab]["las"], "why": why} if rs_tab else None),
        "leader_now": ({"tab": cross["leader_now"], "label": tab_out[cross["leader_now"]]["label"],
                        "rs_ratio": tab_out[cross["leader_now"]]["rs_ratio"]} if cross["leader_now"] else None),
        "macro": ({"severity": macro_sev, "verdict": macro.get("verdict"), "color": macro.get("color"),
                   "score": macro.get("score"), "label_en": macro.get("label_en"),
                   "label_zh": macro.get("label_zh"), "asof": macro.get("asof")} if macro else None),
        "regime": _regime_context(site),
        "tabs": tab_out,
        "drivers": {
            "ratios": ratios,
            "note_en": ("Observable leadership ratios — the measurable 'why', not a regime label. "
                        "RSP/SPY is the cleanest broad-vs-narrow gauge: rising = the average stock is "
                        "participating (healthy); falling = leadership narrowing to mega-cap tech (fragile)."),
            "note_zh": ("可观测的领导比率——可量化的“为什么”，而非状态标签。RSP/SPY 是最干净的广度与集中度指标："
                        "上升=普通个股在参与（健康）；下降=领导收窄至超大盘科技（脆弱）。"),
        },
        "notes": ("Leadership Acceleration Score (LAS) ranks the four universes by whose leadership is "
                  "ACCELERATING most — z(return-accel)·0.40 + z(breadth-thrust)·0.30 + z(participation)·0.30, "
                  "cross-sectional over the tabs. RUNNING = already leading & accelerating (RRG 'leading'). "
                  "COILING = laggards turning up (RRG 'improving') that PASS a multi-factor coil confirmation "
                  "(graded RSI divergence, multi-timeframe turn, volatility contraction, RS-hold, deterioration "
                  "easing, above-rising-trend) AND survive a weekly / 2-week / monthly downtrend veto — a bounce "
                  "inside a confirmed higher-timeframe bear is dropped (stage='knife'), not shown as 'about to "
                  "run'. In a RISK-OFF broad-market backdrop (engine.market_state) coils are additionally held "
                  "back — no 'primed' call, a score haircut, a macro-caution flag. A 4-point z-score is noisy — "
                  "raw legs shown. DISPLAY-ONLY rotation-timing / watchlist ordering (bottom-timing is a "
                  "drawdown lever, not return-alpha); confirm before acting."),
        "_member_map": member_map,
    }


def build(site: Path | None = None, generated_utc: str | None = None) -> int:
    """Render-lane entrypoint (build_site). Recomputes from committed artefacts + writes the
    JSON. Returns 1 on success, 0 on skip. Never raises (additive, never fatal)."""
    site = site or (config.ROOT / config.load()["storage"]["site_dir"])
    try:
        payload = compute(site)
    except Exception as e:  # noqa: BLE001
        log.error("index_leadership compute failed: %s", e)
        return 0
    if not payload:
        log.warning("index_leadership: no confluence boards found — skipped")
        return 0

    # Forward TRACK-RECORD (additive, degrade-safe): log today's RUNNING / COILING calls with
    # their FROZEN member baskets, then grade every matured past call — the read becomes
    # falsifiable. Context-only; verdict stays 'accruing' until a horizon matures + clears the
    # Newey-West bar. member_map is server-side only (popped so it never bloats the client JSON).
    member_map = payload.pop("_member_map", {}) or {}
    try:
        from engine import index_leadership_track as track
        asof = payload.get("as_of") or None
        n_log = track.snapshot(payload, member_map, today=asof)
        payload["track_record"] = track.compute(today=asof)
        tp = config.data_dir() / "index_leadership" / "track_record.json"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(json.dumps(payload["track_record"], indent=2))
        log.info("index_leadership track: +%d snapshots, %d days, verdict=%s", n_log,
                 payload["track_record"].get("n_days"), payload["track_record"].get("verdict"))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("index_leadership track record failed: %s", e)

    out = site / OUT_JSON
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(_clean(payload), separators=(",", ":"), allow_nan=False))
    rs = (payload.get("rising_star") or {}).get("tab")
    log.info("index_leadership: rising star = %s · %d tabs · as_of %s",
             rs, len(payload.get("tabs", {})), payload.get("as_of"))
    return 1


def main() -> dict:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    n = build()
    return {"ok": bool(n)}


if __name__ == "__main__":
    main()
