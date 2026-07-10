"""Build the Macro Weather Station page -> site/macro_context.html.

Reads (all fail-open with graceful empty states):
  data/neuralweb/world_state.json          — radar, regime, vol, breadth, liquidity, contradictions,
                                             rates_credit, global_regimes, liquidity_plumbing
  data/macro_snapshots/latest.json         — 48 labels grouped by domain (v1.1)
  data/macro_snapshots/transitions.jsonl   — label-flip history
  data/macro_snapshots/ledger.parquet      — per-(domain,field) history dots
  data/macro/fed_net_liquidity.parquet     — 90d netliq sparkline
  data/ofr_fsi/fsi.parquet                — 90d OFR FSI sparkline
  data/regime/market_state_history.parquet — 6-session ms_score micro bar

Writes:
  site/macro_context.html              — bilingual Macro Weather Station page
  data/macro_context/latest.json       — hub contract consumed downstream

Display/context tier only.  No scores, no signals, no Article-2 surfaces.
Usage: python -m scripts.build_macro_context
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_macro_context")

# ── Staleness thresholds ────────────────────────────────────────────────────
_STALE_WARN_DAYS = 2
_STALE_OLD_DAYS = 5

# ── Domain order (now includes intl) ────────────────────────────────────────
DOMAIN_ORDER = [
    "us", "market", "transmission", "fx", "bonds",
    "commodity", "china", "hk", "canada", "dispersion", "intl",
]

# Domain display labels
DOMAIN_LABELS: dict[str, tuple[str, str]] = {
    "us":           ("US Regime",           "美国周期"),
    "market":       ("Market State",        "市场状态"),
    "transmission": ("Rates Transmission",  "利率传导"),
    "fx":           ("FX / Dollar",         "外汇 / 美元"),
    "bonds":        ("Bonds & Credit",      "债券与信用"),
    "commodity":    ("Commodities",         "大宗商品"),
    "china":        ("China",               "中国"),
    "hk":           ("Hong Kong",           "香港"),
    "canada":       ("Canada",              "加拿大"),
    "dispersion":   ("Dispersion",          "离散度"),
    "intl":         ("International",       "国际"),
}

# Field-level labels (en, zh) — comprehensive set including v1.1 additions
FIELD_LABELS: dict[str, tuple[str, str]] = {
    # us
    "us_quad":                ("Quadrant",              "象限"),
    "us_transition_state":    ("Transition",            "转换状态"),
    "us_fused_risk":          ("Fused Risk",            "融合风险"),
    "us_vol_regime":          ("Vol Regime",            "波动率周期"),
    "us_risk_radar":          ("Risk Radar",            "风险雷达"),
    "us_rate_pressure":       ("Rate Pressure",         "利率压力"),
    "us_business_cycle_phase":("Business Cycle",        "商业周期"),
    "us_liquidity_quality":   ("Liquidity Quality",     "流动性质量"),
    "us_liquidity_overlay":   ("Liquidity",             "流动性"),
    "us_froth_band":          ("Froth / Fragility",     "泡沫/脆弱度"),
    "us_dislocation":         ("Dislocation",           "错位状态"),
    "us_gamma_regime":        ("Dealer Gamma",          "做市商Gamma"),
    "us_repricing_state":     ("Repricing Coherence",   "重定价一致性"),
    "us_vol_ts_state":        ("VIX Term Structure",    "VIX期限结构"),
    "us_vrp_state":           ("Vol Risk Premium",      "波动风险溢价"),
    "cross_asset_verdict":    ("Cross-Asset",           "跨资产"),
    # market
    "market_state_verdict":   ("Verdict",               "判定"),
    # transmission
    "yield_curve_regime":     ("Curve Regime",          "曲线周期"),
    "recession_risk":         ("Recession Risk",        "衰退风险"),
    # fx
    "usd_trend":              ("USD Trend",             "美元趋势"),
    "usd_regime":             ("USD Regime",            "美元周期"),
    "fx_risk":                ("FX Risk",               "外汇风险"),
    "real_rate_regime":       ("Real Rates",            "实际利率"),
    "fx_liquidity_dir":       ("Liquidity",             "流动性"),
    "fx_regime_radar":        ("FX Regime Radar",       "外汇局势雷达"),
    # bonds
    "bond_health_label":      ("Bond Health",           "债券健康"),
    "bond_cycle_phase":       ("Cycle Phase",           "周期阶段"),
    "bond_duration_bucket":   ("Duration Lean",         "久期倾向"),
    "bond_curve_lean":        ("Curve Trade",           "曲线交易"),
    # commodity
    "commodity_regime":       ("Regime",                "周期"),
    "commodity_favored":      ("Favored",               "偏好"),
    # china
    "china_quad":             ("Quadrant",              "象限"),
    "china_property_regime":  ("Property",              "房地产"),
    "china_fe_band":          ("Fear / Euphoria",       "恐惧/亢奋"),
    # hk
    "hk_quad":                ("Quadrant",              "象限"),
    "hk_risk_state":          ("Risk State",            "风险状态"),
    "hk_peg_state":           ("Peg State",             "联系汇率"),
    # canada
    "canada_quad":            ("Quadrant",              "象限"),
    "canada_overlay_state":   ("Overlay",               "叠加状态"),
    "canada_cycle_tag":       ("Cycle",                 "周期阶段"),
    # dispersion
    "dispersion_state":       ("State",                 "状态"),
    # intl
    "intl_au_quad":           ("Australia",             "澳大利亚"),
    "intl_ez_quad":           ("Eurozone",              "欧元区"),
    "intl_gb_quad":           ("UK",                   "英国"),
    "intl_in_quad":           ("India",                 "印度"),
    "intl_jp_quad":           ("Japan",                 "日本"),
    "intl_kr_quad":           ("Korea",                 "韩国"),
    "intl_tw_quad":           ("Taiwan",                "台湾"),
}

# Chip CSS class mapping (replaces hex color dict)
_CHIP_CLASS: dict[str, str] = {
    # quads
    "Q1": "c-q1", "Q2": "c-q2", "Q3": "c-q3", "Q4": "c-q4",
    # risk
    "risk-on": "c-up", "risk-off": "c-down",
    "Risk-on": "c-up", "Risk-off": "c-down",
    "RISK_OFF": "c-down", "RISK_ON": "c-up", "MIXED": "c-warn",
    # curves
    "bull_flattener": "c-up", "bull_steepener": "c-up",
    "bear_steepener": "c-warn", "bear_flattener": "c-down",
    # recession / health
    "low": "c-up", "mid": "c-warn", "high": "c-down",
    "healthy": "c-up", "mixed": "c-warn", "stressed": "c-down",
    # directions
    "headwind": "c-down", "tailwind": "c-up", "neutral": "c-muted",
    "diverge": "c-warn", "up": "c-up", "down": "c-down", "flat": "c-muted",
    # dispersion
    "lean_in": "c-up", "diversified": "c-info", "concentrated": "c-warn",
    # vol
    "normalizing": "c-up", "stress": "c-down", "elevated": "c-warn",
    "contango": "c-up", "backwardation": "c-warn",
    # general
    "caution": "c-warn", "watch": "c-warn", "calm": "c-muted",
    "QUIET": "c-up", "ARMED": "c-down",
    "pressure": "c-warn",
    "expanding": "c-up", "contracting": "c-down",
    "stress-expansion": "c-warn", "benign-expansion": "c-up",
    "em_crisis_capital_flight": "c-down",
    # bond compass
    "lean_long": "c-up", "lean_short": "c-down", "neutral-hollow": "c-muted",
    "steepener": "c-up", "flattener": "c-down",
    # china special
    "Neutral": "c-muted",
    "Deep contraction (easing)": "c-warn",
    # Goldilocks etc
    "Goldilocks": "c-q1", "Reflation": "c-q2",
    "Stagflation": "c-q3", "Growth-scare": "c-q4",
    # peg
    "weak-side (outflow)": "c-warn", "strong-side (inflow)": "c-up",
    # misc
    "short": "c-warn", "long": "c-up",
    "recovery": "c-up", "late": "c-warn",
    "Restrictive real yields": "c-down",
    "US growth premium": "c-info",
    "supportive": "c-up", "soft": "c-warn",
    "normal": "c-up",
    "lean-in": "c-up",
}

# Quad name map (en → zh) for quad chip labels
QUAD_NAMES_ZH: dict[str, str] = {
    "Goldilocks": "金发姑娘", "Reflation": "再通胀",
    "Stagflation": "滞胀", "Growth-scare": "增长恐慌",
}

# Liq/peg enum en→zh translation map (fix 6a)
LIQ_PEG_ZH: dict[str, str] = {
    "weak-side (outflow)": "弱方（资金流出）",
    "strong-side (inflow)": "强方（资金流入）",
    "weak-side": "弱方",
    "strong-side": "强方",
}

# Prose phrase en→zh translation for board/chips path (fix 6d)
PROSE_ZH: dict[str, str] = {
    "Restrictive real yields": "实际收益率偏紧",
    "Deep contraction (easing)": "深度收缩（宽松中）",
    "US growth premium": "美国增长溢价",
    "Goldilocks": "金发姑娘",
    "Reflation": "再通胀",
    "Stagflation": "滞胀",
    "Growth-scare": "增长恐慌",
}

# Country code → display name (en, zh) for intl rail
INTL_COUNTRY: dict[str, tuple[str, str]] = {
    "intl_au_quad": ("AU", "澳大利亚"),
    "intl_ez_quad": ("EZ", "欧元区"),
    "intl_gb_quad": ("GB", "英国"),
    "intl_in_quad": ("IN", "印度"),
    "intl_jp_quad": ("JP", "日本"),
    "intl_kr_quad": ("KR", "韩国"),
    "intl_tw_quad": ("TW", "台湾"),
}


# ── Utility helpers ──────────────────────────────────────────────────────────

def _chip_class(val: str | None) -> str:
    if val is None:
        return "c-muted"
    return _CHIP_CLASS.get(str(val), "c-info")


def _stale_class(source_asof: str | None, today: str) -> str:
    if not source_asof:
        return "stale-warn"
    try:
        delta = (date.fromisoformat(today) - date.fromisoformat(source_asof)).days
    except Exception:
        return "stale-warn"
    if delta <= _STALE_WARN_DAYS:
        return "stale-ok"
    if delta <= _STALE_OLD_DAYS:
        return "stale-warn"
    return "stale-old"


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        log.warning("could not read %s: %s", path, exc)
        return None


def _load_transitions(path: Path, n: int = 60) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        lines = path.read_text().splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if len(rows) >= n:
                break
    except Exception as exc:
        log.warning("could not read transitions.jsonl: %s", exc)
    return rows


def _spark_points(values: list[float], w: float, h: float) -> str:
    """Convert array of values to SVG polyline points string."""
    if len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn
    pts = []
    for i, v in enumerate(values):
        x = round(i / (len(values) - 1) * w, 1)
        y_norm = (v - mn) / rng if rng > 0 else 0.5
        y = round(h - y_norm * (h - 2) - 1, 1)  # 1px margin top/bottom
        pts.append(f"{x},{y}")
    return " ".join(pts)


def _netliq_spark(parquet_path: Path, days: int = 90) -> str:
    """90-day netliq sparkline points (w=140, h=32)."""
    try:
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        df = df.tail(days)
        if len(df) < 2:
            return ""
        vals = df["netliq_bn"].tolist()
        return _spark_points(vals, 140, 32)
    except Exception as exc:
        log.warning("fed_net_liquidity spark failed: %s", exc)
        return ""


def _ofr_fsi_spark(parquet_path: Path, days: int = 90) -> str:
    """90-day OFR FSI sparkline points (w=140, h=32)."""
    try:
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        df = df.tail(days)
        if len(df) < 2:
            return ""
        vals = df["fsi"].tolist()
        return _spark_points(vals, 140, 32)
    except Exception as exc:
        log.warning("OFR FSI spark failed: %s", exc)
        return ""


def _ms_history(parquet_path: Path) -> list[dict]:
    """Last 6 sessions of market_state_history as mini bar data."""
    try:
        import pandas as pd
        df = pd.read_parquet(parquet_path).tail(6)
        rows = []
        for _, r in df.iterrows():
            rows.append({
                "date": str(r.get("date", "")),
                "ms_score": int(r.get("ms_score", 0)),
                "ms_verdict": str(r.get("ms_verdict", "")),
            })
        return rows
    except Exception as exc:
        log.warning("market_state_history failed: %s", exc)
        return []


def _ledger_history(parquet_path: Path, domain: str, field: str, n: int = 8) -> list[dict]:
    """Last n ledger rows for a (domain, field) pair — for history dots."""
    try:
        import pandas as pd
        df = pd.read_parquet(parquet_path)
        sub = df[(df["domain"] == domain) & (df["field"] == field)].tail(n)
        rows = []
        prev = None
        for _, r in sub.iterrows():
            val = str(r.get("value", ""))
            changed = (prev is not None and val != prev)
            rows.append({
                "asof": str(r.get("asof", "")),
                "value": val,
                "changed": changed,
                "cls": _chip_class(val),
            })
            prev = val
        return rows
    except Exception:
        return []


# ── Section builders ─────────────────────────────────────────────────────────

def _build_hero(world_state: dict | None, snapshot: dict | None, regime_data: dict | None = None) -> dict:
    """Hero section: headline, score, radar spark, KPI chips."""
    ws = world_state or {}
    radar = ws.get("radar", {})
    recovery = radar.get("recovery", {})
    verdict = ws.get("verdict", {})
    regime = ws.get("regime", {})
    vol = ws.get("vol", {})
    breadth = ws.get("breadth", {})
    lp = ws.get("liquidity_plumbing", {})
    labels = (snapshot or {}).get("labels", {})
    rd = regime_data or {}

    # headline from radar recovery
    headline_en = recovery.get("headline_en") or "Macro regime loading"
    headline_zh = recovery.get("headline_zh") or "宏观周期加载中"

    # spark
    spark_pts = recovery.get("spark_pts", "")
    spark_w = recovery.get("spark_w", 96)
    spark_h = recovery.get("spark_h", 26)
    spark_peak = recovery.get("spark_peak", {})
    spark_last = recovery.get("spark_last", {})

    # score
    score = verdict.get("score", None)
    score_label_en = verdict.get("label_en", "")
    score_label_zh = verdict.get("label_zh", "")

    # quad chip
    quad = regime.get("quad", labels.get("us", {}).get("us_quad", ""))
    quad_name = regime.get("quad_name", "")
    quad_conf = regime.get("confidence", None)
    transition_state = regime.get("transition_state", "")
    liq_overlay = regime.get("liquidity_overlay", lp.get("overlay", ""))
    liq_quality = (regime.get("liquidity_quality") or {}).get("label", "")

    # VIX
    vix = vol.get("vix", None)
    vol_regime = vol.get("regime", "")

    # Breadth
    pct_above_200 = breadth.get("pct_above_200", None)
    n_members = breadth.get("n_members", 0)

    # Net liq
    netliq_bn = lp.get("netliq_bn", None)
    netliq_chg_65d = lp.get("netliq_chg_65d_bn", None)
    netliq_pctile = lp.get("netliq_pctile_expanding", None)

    # Radar
    radar_state = radar.get("state", "")
    dominant_scare = (ws.get("risk_radar_raw") or {}).get("dominant_label_en", "")

    # Repricing
    repricing_state = labels.get("us", {}).get("us_repricing_state", "")

    # Sub/caveat
    sub_en = recovery.get("sub_en", "")
    sub_zh = recovery.get("sub_zh", "")
    deesc = recovery.get("deescalation") or {}

    # HMM chip — sourced from regime/latest.json
    hmm_block = rd.get("regime_hmm") or {}
    hmm_modal_quad = hmm_block.get("modal_quad") or None
    hmm_regime_probs = hmm_block.get("regime_probs") or {}
    _hmm_hazard = hmm_block.get("hazard")
    _hmm_dwell = hmm_block.get("expected_dwell_months")
    _hmm_in_regime = hmm_block.get("time_in_regime_months")
    hmm_p_modal = round(hmm_regime_probs.get(hmm_modal_quad, 0), 2) if hmm_modal_quad else None
    hmm_hazard = round(_hmm_hazard, 2) if _hmm_hazard is not None else None
    hmm_dwell = _hmm_dwell
    hmm_in_regime = _hmm_in_regime

    return {
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        "sub_en": sub_en,
        "sub_zh": sub_zh,
        "score": score,
        "score_label_en": score_label_en,
        "score_label_zh": score_label_zh,
        "score_cls": "c-up" if (score or 0) >= 60 else ("c-warn" if (score or 0) >= 40 else "c-down"),
        "spark_pts": spark_pts,
        "spark_w": spark_w,
        "spark_h": spark_h,
        "spark_peak_x": (spark_peak or {}).get("x", 0),
        "spark_peak_y": (spark_peak or {}).get("y", 0),
        "spark_last_x": (spark_last or {}).get("x", 0),
        "spark_last_y": (spark_last or {}).get("y", 0),
        "quad": quad,
        "quad_name": quad_name,
        "quad_name_zh": QUAD_NAMES_ZH.get(quad_name, quad_name),
        "quad_conf": quad_conf,
        "quad_cls": f"c-{quad.lower()}" if quad else "c-muted",
        "transition_state": transition_state,
        "liq_overlay": liq_overlay,
        "liq_quality": liq_quality,
        "liq_cls": _chip_class(liq_quality or liq_overlay),
        "vix": round(vix, 2) if vix is not None else None,
        "vol_regime": vol_regime,
        "vol_cls": _chip_class(vol_regime),
        "pct_above_200": round(pct_above_200, 1) if pct_above_200 is not None else None,
        "n_members": n_members,
        "netliq_bn": round(netliq_bn, 0) if netliq_bn is not None else None,
        "netliq_chg_65d": round(netliq_chg_65d, 1) if netliq_chg_65d is not None else None,
        "netliq_pctile": round(netliq_pctile * 100) if netliq_pctile is not None else None,
        "radar_state": radar_state,
        "radar_cls": _chip_class(radar_state),
        "dominant_scare": dominant_scare,
        "repricing_state": repricing_state,
        "repricing_cls": _chip_class(repricing_state),
        "deesc_eligible": deesc.get("eligible", False),
        "deesc_reason": deesc.get("reason", ""),
        # HMM chip
        "hmm_modal_quad": hmm_modal_quad,
        "hmm_p_modal": hmm_p_modal,
        "hmm_hazard": hmm_hazard,
        "hmm_dwell": hmm_dwell,
        "hmm_in_regime": hmm_in_regime,
    }


def _build_risk_radar(world_state: dict | None, snapshot: dict | None) -> dict:
    """Risk radar section: 6 scares, drawdown ladder, trajectory, cycle context."""
    ws = world_state or {}
    raw = ws.get("risk_radar_raw") or {}
    radar = ws.get("radar", {})
    recovery = radar.get("recovery", {})

    scares = []
    for s in raw.get("scares", []):
        scares.append({
            "scare": s.get("scare", ""),
            "label_en": s.get("label_en", ""),
            "label_zh": s.get("label_zh", ""),
            "score": s.get("score", 0),
            "band": s.get("band", "calm"),
            "dominant": s.get("scare") == raw.get("dominant_scare"),
        })

    dp = raw.get("drawdown_prob") or {}
    trajectory = raw.get("trajectory") or {}

    # cycle context from radar lobe
    cycle = (ws.get("risk_radar_raw") or {})
    # Actually cycle_context is in the context_pack from risk_radar_raw
    cycle_ctx = None
    # Try to get from radar recovery which has all the right keys
    # Actually look in world_state directly
    # The cycle context is stored under risk_radar_raw.cycle_context per context_pack
    rr_raw_full = ws.get("risk_radar_raw") or {}
    cc = rr_raw_full.get("cycle_context") or {}
    if cc.get("show"):
        favor = cc.get("sector_bias", {}).get("favor", [])
        avoid = cc.get("sector_bias", {}).get("avoid", [])
        cycle_ctx = {
            "label_en": cc.get("label_en", ""),
            "label_zh": cc.get("label_zh", ""),
            "stat_en": cc.get("stat_en", ""),
            "stat_zh": cc.get("stat_zh", ""),
            "caveat_en": cc.get("caveat_en", ""),
            "caveat_zh": cc.get("caveat_zh", ""),
            "favor": favor,
            "avoid": avoid,
        }

    return {
        "scares": scares,
        "n_scares": len(scares),
        "dominant_label_en": raw.get("dominant_label_en", ""),
        "dominant_label_zh": raw.get("dominant_label_zh", ""),
        "radar_state": raw.get("state", ""),
        "dd_h5": dp.get("h5"),
        "dd_h10": dp.get("h10"),
        "dd_h21": dp.get("h21"),
        "dd_base_h5": dp.get("base_h5"),
        "dd_base_h10": dp.get("base_h10"),
        "dd_base_h21": dp.get("base_h21"),
        "dd_measure": dp.get("measure", ""),
        "trajectory_phase": trajectory.get("phase", ""),
        "trajectory_peak": trajectory.get("peak"),
        "trajectory_peak_days_ago": trajectory.get("peak_days_ago"),
        "trajectory_velocity": trajectory.get("velocity"),
        "trajectory_intensity": trajectory.get("intensity"),
        "deesc_eligible": (recovery.get("deescalation") or {}).get("eligible", False),
        "cycle_ctx": cycle_ctx,
    }


def _load_ledger_cache(ledger_path: Path | None, n: int = 8) -> dict:
    """Read ledger.parquet ONCE, sort by asof, and return a lookup dict.

    Returns {(domain, field): list[dict]} where each list has up to n rows
    (newest last), already sorted ascending by asof so .tail() is correct.
    """
    cache: dict[tuple[str, str], list[dict]] = {}
    if not ledger_path or not ledger_path.exists():
        return cache
    try:
        import pandas as pd
        df = pd.read_parquet(ledger_path)
        df = df.sort_values("asof")
        for (domain, field), grp in df.groupby(["domain", "field"]):
            rows_df = grp.tail(n)
            rows: list[dict] = []
            prev: str | None = None
            for _, r in rows_df.iterrows():
                val = str(r.get("value", ""))
                changed = (prev is not None and val != prev)
                rows.append({
                    "asof": str(r.get("asof", "")),
                    "value": val,
                    "changed": changed,
                    "cls": _chip_class(val),
                })
                prev = val
            cache[(str(domain), str(field))] = rows
    except Exception as exc:
        log.warning("ledger cache build failed: %s", exc)
    return cache


def _build_weather_board(
    snapshot: dict | None,
    today: str,
    ledger_cache: dict,
    transitions: list[dict],
) -> list[dict]:
    """Build domain-grouped chip rows with history dots and changed-today markers."""
    if not snapshot:
        return []
    labels = snapshot.get("labels", {})
    sources = snapshot.get("sources", {})

    # Domain → source asof
    _domain_asof: dict[str, str] = {}
    fragment_map = {
        "us": ["regime/latest"],
        "market": ["market_state"],
        "transmission": ["transmission"],
        "fx": ["forex"],
        "bonds": ["bond_health"],
        "commodity": ["commodity"],
        "china": ["china_regime"],
        "hk": ["hk_regime"],
        "canada": ["canada_regime"],
        "dispersion": ["dispersion"],
        "intl": ["intl_regime"],
    }
    for src_path, src_asof in sources.items():
        for domain, fragments in fragment_map.items():
            if any(f in src_path for f in fragments):
                if domain not in _domain_asof or (src_asof or "") > _domain_asof.get(domain, ""):
                    _domain_asof[domain] = src_asof or ""

    # "Changed today" set: (domain, field) pairs from today's transitions
    changed_today: set[tuple[str, str]] = set()
    for t in transitions:
        if t.get("asof", "") == today:
            changed_today.add((t.get("domain", ""), t.get("field", "")))

    board: list[dict] = []
    for domain in DOMAIN_ORDER:
        domain_labels = labels.get(domain, {})
        if not domain_labels:
            continue
        domain_en, domain_zh = DOMAIN_LABELS.get(domain, (domain.upper(), domain.upper()))
        src_asof = _domain_asof.get(domain)
        stale_cls = _stale_class(src_asof, today)
        chips: list[dict] = []
        for field, val in domain_labels.items():
            field_en, field_zh = FIELD_LABELS.get(field, (field, field))
            val_str = str(val) if val is not None else "—"
            if isinstance(val, list):
                val_str = ", ".join(str(v) for v in val)
            # History dots — from pre-built cache
            history = ledger_cache.get((domain, field), [])
            chips.append({
                "field": field,
                "field_en": field_en,
                "field_zh": field_zh,
                "val": val_str,
                "cls": _chip_class(val_str if not isinstance(val, list) else None),
                "null": val is None,
                "changed_today": (domain, field) in changed_today,
                "history": history,
            })
        board.append({
            "domain": domain,
            "domain_en": domain_en,
            "domain_zh": domain_zh,
            "asof": src_asof or "",
            "stale_cls": stale_cls,
            "chips": chips,
        })
    return board


def _build_global_quad_map(world_state: dict | None, snapshot: dict | None) -> dict:
    """4 region cards + intl 7-chip rail + dispersion tally."""
    ws = world_state or {}
    gr = ws.get("global_regimes") or {}
    labels = (snapshot or {}).get("labels", {})

    regions = []
    for mkt in ["us", "china", "hk", "canada"]:
        r = gr.get(mkt) or {}
        if not r:
            continue
        quad = r.get("quad", "")
        quad_name = r.get("quad_name", "")
        liq_overlay = r.get("liquidity_overlay", "")
        peg_state = r.get("peg_state") or ""
        regions.append({
            "market": mkt,
            "market_en": mkt.upper(),
            "market_zh": {"us": "美国", "china": "中国", "hk": "香港", "canada": "加拿大"}.get(mkt, mkt),
            "quad": quad,
            "quad_name": quad_name,
            "quad_name_zh": QUAD_NAMES_ZH.get(quad_name, quad_name),
            "quad_cls": f"q{quad[1]}" if quad and len(quad) == 2 else "q1",
            "confidence": r.get("confidence"),
            "cycle_tag": r.get("cycle_tag", ""),
            "liq_overlay": liq_overlay,
            "liq_overlay_zh": LIQ_PEG_ZH.get(liq_overlay, liq_overlay),
            "pending_quad": r.get("pending_quad"),
            "risk_state": r.get("risk_state"),
            "peg_state": peg_state,
            "peg_state_zh": LIQ_PEG_ZH.get(peg_state, peg_state),
        })

    # Intl chips from snapshot labels
    intl_labels = labels.get("intl", {})
    intl_chips = []
    for field, (code_en, country_zh) in INTL_COUNTRY.items():
        quad = intl_labels.get(field, "")
        if quad:
            quad_name = {"Q1": "Goldilocks", "Q2": "Reflation",
                         "Q3": "Stagflation", "Q4": "Growth-scare"}.get(quad, quad)
            intl_chips.append({
                "code_en": code_en,
                "country_zh": country_zh,
                "quad": quad,
                "quad_name": quad_name,
                "quad_name_zh": QUAD_NAMES_ZH.get(quad_name, quad_name),
                "quad_cls": f"q{quad[1]}" if quad and len(quad) == 2 else "c-muted",
            })

    # Quad distribution tally
    all_quads = [r["quad"] for r in regions if r["quad"]] + [c["quad"] for c in intl_chips if c["quad"]]
    quad_tally = {q: all_quads.count(q) for q in ["Q1", "Q2", "Q3", "Q4"]}

    dispersion_note_en = gr.get("dispersion_note", "")
    # Derive dynamic ZH dispersion note: count distinct quads across US/CN/HK/CA
    _region_quads = {r["quad"] for r in regions if r["quad"]}
    _n_distinct = len(_region_quads)
    dispersion_note_zh = f"美/中/港/加 呈现{_n_distinct}种不同象限" if _n_distinct > 1 else ""

    return {
        "regions": regions,
        "intl_chips": intl_chips,
        "quad_tally": quad_tally,
        "dispersion_note": dispersion_note_en,
        "dispersion_note_en": dispersion_note_en,
        "dispersion_note_zh": dispersion_note_zh,
    }


def _build_rates_liquidity(
    world_state: dict | None,
    regime_data: dict | None,
    data_dir: Path,
) -> dict:
    """Rates + liquidity panel."""
    ws = world_state or {}
    rc = ws.get("rates_credit") or {}
    lp = ws.get("liquidity_plumbing") or {}
    rd = regime_data or {}

    # Fed path — source from regime/latest.json (primary), fall back to rates_credit
    rd_fed_path = rd.get("fed_path") or {}
    rd_fed_stance = rd.get("fed_stance") or {}
    rc_fed_path = rc.get("fed_path") or {}

    policy_rate = rd_fed_path.get("policy_rate") or rc_fed_path.get("policy_rate")
    implied_cuts_6m = rd_fed_path.get("implied_cuts_6m")
    if implied_cuts_6m is None:
        implied_cuts_6m = rc_fed_path.get("implied_cuts_6m")
    market_vs_fed_bp = rd_fed_stance.get("market_vs_fed_bp")
    if market_vs_fed_bp is None:
        market_vs_fed_bp = rc_fed_path.get("market_vs_fed_bp")
    ntfs = rd_fed_path.get("ntfs") or rc_fed_path.get("ntfs")
    fed_stance = rc.get("verdict_en", "")

    # Yield curve — source from regime/latest.json yield_curve.shape first
    rd_yc = rd.get("yield_curve") or {}
    rd_shape = rd_yc.get("shape") or {}
    rd_slope = rd_shape.get("slope_2s10s") or {}

    # Rates state — from world_state.rates_transmission.state.rates
    rt_state = ((ws.get("rates_transmission") or {}).get("state") or {}).get("rates") or {}

    # curve_2s10s: regime/latest.json → yield_curve.shape.slope_2s10s.value
    curve_2s10s = rd_slope.get("value")
    if curve_2s10s is None:
        curve_2s10s = rt_state.get("curve_2s10s")
    # curve_2s10s_pctile
    curve_pctile = rd_slope.get("pctile")
    # real_10y: world_state.rates_transmission.state.rates.real_10y
    real_10y = rt_state.get("real_10y")
    # real_10y_pctile
    real_pctile = rt_state.get("real_10y_pctile")
    # curve_tp_adj: world_state.rates_transmission.state.rates.curve_tp_adj
    tp_adj = rt_state.get("curve_tp_adj")
    if tp_adj is None:
        tp_adj = rd_fed_path.get("curve_tp_adj")

    curve_regime = (ws.get("rates_transmission") or {}).get("curve_regime", "")

    # Bond compass
    bc = rc.get("bond_compass") or {}
    dur = bc.get("duration") or {}
    ct = bc.get("curve_trade") or {}
    compass_legs = []
    for leg in dur.get("legs", []):
        compass_legs.append({
            "label_en": leg.get("label_en", ""),
            "label_zh": leg.get("label_zh", ""),
            "state": leg.get("state", ""),
            "value": leg.get("value"),
        })
    bond_compass = {
        "duration_bucket": dur.get("bucket", ""),
        "duration_lean": dur.get("lean"),
        "conviction": dur.get("conviction"),
        "legs": compass_legs,
        "curve_lean": ct.get("lean_label", ""),
        "curve_rationale_en": ct.get("rationale_en", ""),
        "curve_rationale_zh": ct.get("rationale_zh", ""),
    }

    # Liquidity plumbing
    netliq_bn = lp.get("netliq_bn")
    netliq_chg_65d = lp.get("netliq_chg_65d_bn")
    netliq_chg_20d = lp.get("netliq_chg_20d_bn")
    netliq_pctile = lp.get("netliq_pctile_expanding")
    rrp_bn = lp.get("rrp_bn")
    rrp_state = lp.get("rrp_buffer_state", "")
    tga_bn = lp.get("tga_bn")
    quality_label = lp.get("quality_label", "")
    lp_summary = lp.get("summary", "")
    lp_asof = lp.get("asof", "")

    # Sparklines
    netliq_spark = _netliq_spark(data_dir / "macro" / "fed_net_liquidity.parquet")
    ofr_fsi_spark_pts = _ofr_fsi_spark(data_dir / "ofr_fsi" / "fsi.parquet")

    # OFR FSI last value
    ofr_fsi_val = None
    try:
        import pandas as pd
        fsi_df = pd.read_parquet(data_dir / "ofr_fsi" / "fsi.parquet")
        ofr_fsi_val = round(float(fsi_df["fsi"].iloc[-1]), 3)
    except Exception:
        pass

    return {
        # Rates
        "policy_rate": policy_rate,
        "implied_cuts_6m": implied_cuts_6m,
        "market_vs_fed_bp": market_vs_fed_bp,
        "ntfs": ntfs,
        "fed_stance": fed_stance,
        "curve_2s10s": curve_2s10s,
        "curve_pctile": curve_pctile,
        "real_10y": real_10y,
        "real_pctile": real_pctile,
        "tp_adj": tp_adj,
        "curve_regime": curve_regime,
        "bond_compass": bond_compass,
        # Liquidity
        "netliq_bn": round(netliq_bn) if netliq_bn is not None else None,
        "netliq_chg_65d": round(netliq_chg_65d, 1) if netliq_chg_65d is not None else None,
        "netliq_chg_20d": round(netliq_chg_20d, 1) if netliq_chg_20d is not None else None,
        "netliq_pctile": round(netliq_pctile * 100) if netliq_pctile is not None else None,
        "rrp_bn": round(rrp_bn, 1) if rrp_bn is not None else None,
        "rrp_state": rrp_state,
        "rrp_exhausted": rrp_state == "exhausted",
        "tga_bn": round(tga_bn) if tga_bn is not None else None,
        "quality_label": quality_label,
        "quality_cls": _chip_class(quality_label),
        "lp_summary": lp_summary,
        "lp_asof": lp_asof,
        "netliq_spark": netliq_spark,
        "ofr_fsi_spark": ofr_fsi_spark_pts,
        "ofr_fsi_val": ofr_fsi_val,
        "ofr_fsi_cls": "c-up" if (ofr_fsi_val or 0) < 0 else ("c-warn" if (ofr_fsi_val or 0) < 1 else "c-down"),
    }


def _build_headwind_tailwind(world_state: dict | None, snapshot: dict | None) -> dict:
    """Head/tailwind matrix: rates transmission + FX."""
    ws = world_state or {}
    rt = ws.get("rates_transmission") or {}
    fx = ws.get("fx_dollar") or {}
    labels = (snapshot or {}).get("labels", {})

    fx_tx = (fx.get("transmission") or {})
    dollar_desk = (fx.get("dollar_desk") or {})

    return {
        "rates": {
            "headwinds": rt.get("headwinds", []),
            "tailwinds": rt.get("tailwinds", []),
            "asof": rt.get("asof"),
            "state": rt.get("state", {}),
        },
        "fx": {
            "headwind_for": fx_tx.get("headwind_for", []),
            "tailwind_for": fx_tx.get("tailwind_for", []),
            "asof": fx.get("asof"),
            "trend": dollar_desk.get("trend", ""),
            "regime": labels.get("fx", {}).get("usd_regime", ""),
            "regime_radar": labels.get("fx", {}).get("fx_regime_radar", ""),
            "regime_radar_cls": _chip_class(labels.get("fx", {}).get("fx_regime_radar", "")),
        },
    }


def _coerce_transition_val(v: object) -> str:
    """Coerce a transition from/to value to a clean display string.

    Handles:
    - None → "—"
    - list/tuple → comma-joined
    - str that looks like a Python list repr → ast.literal_eval → comma-joined
    - anything else → str(v)
    """
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v)
    s = str(v).strip()
    if s.startswith("[") and s.endswith("]"):
        import ast
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple)):
                return ", ".join(str(x) for x in parsed)
        except Exception:
            pass
    return s


def _build_transitions_vm(transitions: list[dict], today: str) -> dict:
    """Group transitions by date, hot vs prior."""
    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in transitions:
        asof = t.get("asof", "")
        groups[asof].append(t)

    # Sort dates newest first
    sorted_dates = sorted(groups.keys(), reverse=True)
    date_groups = []
    today_count = 0
    for asof in sorted_dates:
        is_today = (asof == today)
        rows = groups[asof]
        if is_today:
            today_count = len(rows)
        formatted_rows = []
        for t in rows:
            domain = t.get("domain", "")
            field = t.get("field", "")
            from_val = _coerce_transition_val(t.get("from_value"))
            to_val = _coerce_transition_val(t.get("to_value"))
            if from_val == to_val:
                # formatting-only flip (e.g. list-repr normalization) — no real change
                if is_today:
                    today_count -= 1
                continue
            field_en, field_zh = FIELD_LABELS.get(field, (field, field))
            domain_en, domain_zh = DOMAIN_LABELS.get(domain, (domain.upper(), domain.upper()))
            formatted_rows.append({
                "asof": asof,
                "domain": domain,
                "domain_label_en": domain_en,
                "domain_label_zh": domain_zh,
                "field": field,
                "field_label_en": field_en,
                "field_label_zh": field_zh,
                "from_val": from_val,
                "to_val": to_val,
                "is_today": is_today,
            })
        if not formatted_rows:
            continue
        date_groups.append({
            "asof": asof,
            "is_today": is_today,
            "rows": formatted_rows,
        })

    return {
        "date_groups": date_groups,
        "today_count": today_count,
        "total": len(transitions),
    }


def _build_contradictions(world_state: dict | None) -> dict:
    """Contradiction census."""
    ws = world_state or {}
    co = ws.get("contradictions") or {}
    by_sev = co.get("by_severity") or {}
    return {
        "n": co.get("n", 0),
        "n_tension": by_sev.get("tension", 0),
        "n_note": by_sev.get("note", 0),
        "top_pair_ids": co.get("top_pair_ids", []),
        "note": co.get("note", ""),
        "cross_asset_verdict": (ws.get("verdict") or {}).get("cross_asset", {}).get("verdict") if isinstance(ws.get("verdict"), dict) else None,
        "n_divergences": (ws.get("intelligence") or {}).get("n_divergences"),
    }


def _build_view_model(
    snapshot: dict | None,
    world_state: dict | None,
    transitions: list[dict],
    today: str,
    data_dir: Path,
    regime_data: dict | None = None,
) -> dict:
    macro_context_id = (snapshot or {}).get("macro_context_id", "")
    asof = (snapshot or {}).get("asof", today)

    # 14-day transition count
    n_transitions_14d = 0
    if transitions:
        try:
            cutoff = (date.fromisoformat(today) - timedelta(days=14)).isoformat()
        except Exception:
            cutoff = ""
        n_transitions_14d = sum(1 for t in transitions if t.get("asof", "") >= cutoff)

    # headline (hub contract)
    labels = (snapshot or {}).get("labels", {})
    ws = world_state or {}
    radar = ws.get("radar", {})
    recovery = radar.get("recovery", {})
    headline_en = recovery.get("headline_en", "")
    headline_zh = recovery.get("headline_zh", "")
    if not headline_en:
        us_quad = labels.get("us", {}).get("us_quad", "")
        usd_trend = labels.get("fx", {}).get("usd_trend", "")
        bond_health = labels.get("bonds", {}).get("bond_health_label", "")
        headline_en = (
            f"US {us_quad} · USD {usd_trend} · Bonds {bond_health}"
            if (us_quad or usd_trend or bond_health) else "Macro context loading"
        )
        from engine.i18n import tr as _tr
        _zh_trend = {"up": "上行", "down": "下行", "flat": "走平"}.get(str(usd_trend)) or _tr(str(usd_trend)) or usd_trend
        _zh_health = {"healthy": "健康", "stressed": "承压", "deteriorating": "恶化"}.get(str(bond_health)) or _tr(str(bond_health)) or bond_health
        headline_zh = (
            f"美国{us_quad} · 美元{_zh_trend} · 债券{_zh_health}"
            if (us_quad or usd_trend or bond_health) else "宏观背景加载中"
        )

    # Read ledger once, sorted, into a cache dict — avoids N full parquet reads
    ledger_path = data_dir / "macro_snapshots" / "ledger.parquet"
    ledger_cache = _load_ledger_cache(ledger_path, n=8)

    hero = _build_hero(world_state, snapshot, regime_data=regime_data)
    risk_radar = _build_risk_radar(world_state, snapshot)
    weather_board = _build_weather_board(snapshot, today, ledger_cache, transitions)
    global_quad_map = _build_global_quad_map(world_state, snapshot)
    rates_liquidity = _build_rates_liquidity(world_state, regime_data, data_dir)
    headwind_tailwind = _build_headwind_tailwind(world_state, snapshot)
    transitions_vm = _build_transitions_vm(transitions, today)
    contradictions = _build_contradictions(world_state)
    ms_history = _ms_history(data_dir / "regime" / "market_state_history.parquet")

    return {
        # Hub contract keys (exact, unchanged)
        "asof": asof,
        "macro_context_id": macro_context_id,
        "n_transitions_14d": n_transitions_14d,
        "headline_en": headline_en,
        "headline_zh": headline_zh,
        # Page sections
        "today": today,
        "hero": hero,
        "risk_radar": risk_radar,
        "weather_board": weather_board,
        "global_quad_map": global_quad_map,
        "rates_liquidity": rates_liquidity,
        "headwind_tailwind": headwind_tailwind,
        "transitions_vm": transitions_vm,
        "contradictions": contradictions,
        "ms_history": ms_history,
        "snapshot_present": snapshot is not None,
        "world_state_present": world_state is not None,
    }


def main() -> int:
    root = config.ROOT
    data_dir = config.data_dir()
    today = date.today().isoformat()
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    snapshot = _load_json(data_dir / "macro_snapshots" / "latest.json")
    world_state = _load_json(data_dir / "neuralweb" / "world_state.json")
    regime = _load_json(data_dir / "regime" / "latest.json")
    transitions = _load_transitions(data_dir / "macro_snapshots" / "transitions.jsonl", n=60)

    if snapshot is None:
        log.warning("macro_snapshots/latest.json missing — rendering empty-state page")
    if world_state is None:
        log.warning("neuralweb/world_state.json missing — many sections will be empty")
    if regime is None:
        log.warning("regime/latest.json missing — rates panel and HMM chip will be empty")

    vm = _build_view_model(snapshot, world_state, transitions, today, data_dir, regime_data=regime)

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(root / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("macro_context.html.j2").render(
        vm=vm,
        built=built,
        today=today,
    )

    site = root / config.load()["storage"]["site_dir"]
    write_page(site / "macro_context.html", html)
    log.info("wrote %s/macro_context.html (%d KB)", site, len(html) // 1024)

    # Hub contract (exact keys preserved)
    hub_dir = data_dir / "macro_context"
    hub_dir.mkdir(parents=True, exist_ok=True)
    hub = {
        "asof": vm["asof"],
        "macro_context_id": vm["macro_context_id"],
        "n_transitions_14d": vm["n_transitions_14d"],
        "headline_en": vm["headline_en"],
        "headline_zh": vm["headline_zh"],
    }
    (hub_dir / "latest.json").write_text(json.dumps(hub, indent=2, ensure_ascii=False))
    log.info("wrote data/macro_context/latest.json — id=%s", vm["macro_context_id"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
