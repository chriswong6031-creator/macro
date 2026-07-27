"""Build the Bonds & bond-health dashboard -> site/bonds.html.

Standalone like build_forex.py / build_commodities.py (shares only the parquet
store + theme assets). HEALTH-FIRST: a Bond Health Score + cycle-clock phase sit on
top; below are the five pillars (curve & growth, credit, real & inflation, stress &
plumbing, cross-asset regime), each explainable. Recomputes the bond-health engine
every build, rebuilds the alert timeline, and writes:

  site/bonds.html            — the dashboard
  data/bonds/latest.json     — the hub card (consumed by build_vector)
  data/bonds/bond_health.json — the MACHINE-READABLE signal vector for the
                                cross-asset AI synthesis brain (the end goal)

Returns 0 on any engine error so it can never break the rest of the site.
Usage: python -m scripts.build_bonds
"""
from __future__ import annotations

import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from lib import illus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_bonds")

# shared Glassnode light palette (same as build_forex for a consistent product)
C = {
    "blue": "#285FFF", "indigo": "#4559DC", "ink": "#0B1733", "text": "#344054",
    "muted": "#6F6F6F", "faint": "#A0A0A0", "red": "#D30B0B", "redfill": "#FEB5B5",
    "amber": "#F5AD42", "green": "#1a7f43", "grid": "#EAECF0", "card": "#FFFFFF",
    "bg": "#F7F8FA", "gold": "#C8A53B", "teal": "#1F8A70",
}
# band -> display color (shared across pillars)
HEALTH_COLOR = {"healthy": C["green"], "mixed": C["amber"], "stressed": C["red"]}
PHASE = {"recession": ("Recession", "衰退", C["red"]), "early": ("Early-cycle recovery", "周期早段复苏", C["green"]),
         "mid": ("Mid-cycle", "周期中段", C["blue"]), "late": ("Late-cycle", "周期晚段", C["amber"])}
CREDIT_BAND = {"tight": ("Tight", "偏紧", C["green"]), "normal": ("Normal", "正常", C["blue"]),
               "elevated": ("Elevated", "升高", C["amber"]), "distress": ("Distress", "困境", C["red"]),
               "crisis": ("Crisis", "危机", "#8B0000")}
MOVE_BAND = {"calm": ("Calm", "平静", C["green"]), "normal": ("Normal", "正常", C["blue"]),
             "elevated": ("Elevated", "升高", C["amber"]), "crisis": ("Crisis", "危机", C["red"])}
CORR_REGIME = {"diversifying": ("Diversifying — bonds hedge", "分散化 — 债券对冲", C["green"]),
               "mixed": ("Mixed", "中性", C["muted"]),
               "breakdown": ("Breakdown — bonds not hedging", "失效 — 债券不对冲", C["red"])}
TAX_COLOR = {"bull_steepener": C["green"], "bull_flattener": C["teal"],
             "bear_steepener": C["amber"], "bear_flattener": C["red"]}
FRAG_STATE = {"calm": ("Calm", "平静", C["green"]), "elevated": ("Elevated", "升高", C["amber"]),
              "stress": ("Stress", "压力", C["red"])}
JGB_STATE = {"steep": ("Steepening", "陡峭化", C["amber"]), "flat": ("Flat", "平坦", C["muted"]),
             "inverted": ("Inverted", "倒挂", C["red"])}
LEG_LABEL = {"recession": ("Recession", "衰退"), "drawdown": ("Drawdown", "回撤"),
             "credit": ("Credit", "信用"), "rates_vol": ("Rates vol", "利率波动"),
             "plumbing": ("Plumbing", "资金管道")}
# calibration (scripts/calibrate_bonds) → display
VERDICT_GLYPH = {"CONFIRMED": ("✓", "measured", "已校准"), "DIRECTIONAL": ("~", "directional", "有方向性"),
                 "CONTEXT": ("·", "context", "仅背景"), "INVERTED": ("⇄", "inverted", "反向"),
                 "UNMEASURED": ("", "", "")}
LEG_CALIB_KEY = {"recession": "recession", "drawdown": "drawdown",
                 "credit": "credit", "rates_vol": "rates_vol", "plumbing": "plumbing"}


def _load_calibration() -> dict:
    """The measured calibration (scripts/calibrate_bonds → data/bonds/calibration.json).
    Empty dict if never run — the dashboard then shows the prior framing."""
    p = config.data_dir() / "bonds" / "calibration.json"
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _r(v, n=2):
    return round(float(v), n) if v is not None and pd.notna(v) else None


def _tail_years(df: pd.DataFrame, years: float) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    cutoff = df.index.max() - pd.Timedelta(days=int(365 * years))
    return df.loc[df.index >= cutoff]


def _dx(index):
    return [t.strftime("%Y-%m-%d") for t in index]


def _col(df, name):
    """A column from a frame, or None when absent (never raises)."""
    if df is None or name not in getattr(df, "columns", []):
        return None
    return df[name]


# --------------------------------------------------------------------------- #
# ilx / Signal-Ink charts — SSR-SVG + CSS animation, the house display format.
# Every illustrative chart on this page routes through lib.illus (no Plotly on
# dashboards — docs/ILLUSTRATIONS.md / the Design Doctrine). Bad/short data never
# raises: the series builders return None/"" and illus renders an honest null.
# --------------------------------------------------------------------------- #
def _ser(s, years=None, n=2):
    """pd.Series -> ilx {dates, vals} (None if empty). Optional trailing-years slice."""
    if s is None:
        return None
    s = s.dropna()
    if years is not None and not s.empty:
        s = s.loc[s.index >= (s.index.max() - pd.Timedelta(days=int(365 * years)))]
    if s.empty:
        return None
    return {"dates": _dx(s.index), "vals": [round(float(v), n) for v in s]}


def _mser(label_en, label_zh, color, s, years=None, n=2):
    """A named, colored series dict for illus(kind='multi'). None when empty."""
    d = _ser(s, years=years, n=n)
    if d is None:
        return None
    d.update(label_en=label_en, label_zh=label_zh, color=color)
    return d


def _ilx(series, accent, *, kind="line", height=190, baseline=None, reference=None,
         unit_en="", unit_zh=None, bands=None, value_fmt="{:,.2f}", aria_en=""):
    """Bridge a {dates, vals} dict to an ilx fragment; '' when the series is empty."""
    if not series or (kind != "multi" and not series.get("dates")):
        return ""
    return illus.illus(series, kind=kind, accent=accent, height=height, baseline=baseline,
                       reference=reference, unit_en=unit_en, unit_zh=unit_zh, bands=bands,
                       value_fmt=value_fmt, aria_en=aria_en or f"{kind} chart")


def _multi(series_list, *, height=190, baseline=None, value_fmt="{:,.2f}", aria_en=""):
    """Bridge a list of _mser dicts to an ilx multi fragment; '' when < 2 valid series."""
    valid = [s for s in series_list if s]
    if len(valid) < 2:
        return ""
    return illus.illus(valid, kind="multi", height=height, baseline=baseline,
                       value_fmt=value_fmt, aria_en=aria_en or "comparison chart")


def _band(hi, lo, tint_var, pct, label_en, label_zh, pos):
    """A soft zone-band tint (display-tier context) for illus(bands=...)."""
    return {"hi": hi, "lo": lo,
            "tint": f"color-mix(in srgb, var(--{tint_var}) {pct}%, transparent)",
            "label_en": label_en, "label_zh": label_zh, "pos": pos}


def chart_health(fr, years=8):
    """Bond Health Score history (0-100) — area with healthy / stressed zone tints."""
    s = _ser(_col(fr, "health_score"), years=years, n=1)
    bands = [_band(100, 66, "green", 13, "Healthy", "健康", "top"),
             _band(34, 0, "red", 11, "Stressed", "承压", "bottom")]
    return _ilx(s, "var(--teal)", kind="area", height=200, bands=bands,
                value_fmt="{:,.0f}", aria_en="Bond health score history")


def chart_curve_now(f):
    """THE signature: the US Treasury yield curve, today vs ~3 months and ~1 year ago.
    ilx plots by index with the tenor labels as the corner captions, so the shape reads
    as a real term structure (3m -> 30y)."""
    tenors = [("us3m", "3m"), ("us6m", "6m"), ("us1y", "1y"), ("us2y", "2y"),
              ("us3y", "3y"), ("us5y", "5y"), ("us7y", "7y"), ("us10y", "10y"),
              ("us30y", "30y")]
    labels = [t[1] for t in tenors]

    def snap(off, le, lz, color):
        try:
            row = f.iloc[off]
        except Exception:  # noqa: BLE001
            return None
        vals = [(None if (c not in f.columns or pd.isna(row.get(c))) else round(float(row[c]), 2))
                for c, _ in tenors]
        if sum(v is not None for v in vals) < 4:
            return None
        return {"label_en": le, "label_zh": lz, "color": color, "dates": labels, "vals": vals}

    series = [s for s in (snap(-1, "Today", "当前", "var(--warn)"),
                          snap(-64, "3 mo ago", "3月前", "var(--info)"),
                          snap(-252, "1 yr ago", "1年前", "var(--muted)")) if s]
    return _multi(series, height=230, value_fmt="{:,.2f}",
                  aria_en="US Treasury yield curve now versus three months and one year ago")


def chart_spreads(fr, years=12):
    """Curve slope over time (10y-3m, 2s10s, term-premium-adjusted); zero = flat."""
    return _multi([
        _mser("10y-3m", "10年-3月", "var(--info)", _col(fr, "spread_10y3m"), years),
        _mser("2s10s", "2年/10年", "var(--warn)", _col(fr, "spread_2s10s"), years),
        _mser("TP-adjusted", "期限溢价调整", "var(--muted)", _col(fr, "curve_tp_adj"), years),
    ], height=190, baseline=0, value_fmt="{:+,.2f}",
       aria_en="Yield curve slope measures over time")


def chart_credit(fr, years=12):
    """Credit spreads over time — high-yield OAS and investment-grade OAS."""
    return _multi([
        _mser("HY OAS", "高收益", "var(--warn)", _col(fr, "hy_oas"), years),
        _mser("IG OAS", "投资级", "var(--info)", _col(fr, "ig_oas"), years),
    ], height=190, value_fmt="{:,.2f}",
       aria_en="High-yield and investment-grade credit spreads")


def chart_real(fr, years=12):
    """The discount rate — real 10y, breakeven inflation, term premium; zero reference."""
    return _multi([
        _mser("Real 10y", "10年实际", "var(--info)", _col(fr, "us10y_real"), years),
        _mser("Breakeven", "盈亏平衡", "var(--orange)", _col(fr, "breakeven_10y"), years),
        _mser("Term premium", "期限溢价", "var(--muted)", _col(fr, "term_premium_10y"), years),
    ], height=190, baseline=0, value_fmt="{:+,.2f}",
       aria_en="Real yield, breakeven inflation and term premium")


def chart_move(fr, years=12):
    """Rates volatility (MOVE) over time — calm / crisis zone tints."""
    s = _ser(_col(fr, "move"), years=years, n=0)
    bands = [_band(None, 120, "red", 10, "Crisis", "危机", "top"),
             _band(80, 0, "green", 10, "Calm", "平静", "bottom")]
    return _ilx(s, "var(--warn)", kind="line", height=180, bands=bands,
                value_fmt="{:,.0f}", aria_en="MOVE rates volatility index")


def chart_corr(fr, years=12):
    """Stock-bond 63-day correlation — diversifying (below 0) vs hedge-weak (above 0)."""
    s = _ser(_col(fr, "stock_bond_corr"), years=years, n=2)
    bands = [_band(1, 0.2, "red", 9, "Hedge weak", "对冲减弱", "top"),
             _band(-0.1, -1, "green", 9, "Diversifying", "分散化", "bottom")]
    return _ilx(s, "var(--info)", kind="line", height=180, reference=0, bands=bands,
                value_fmt="{:+,.2f}", aria_en="Stock-bond 63-day correlation")


def chart_sovereign(fr, years=14):
    """Euro-area fragmentation and the JGB 2s10s curve; zero reference."""
    return _multi([
        _mser("Euro fragmentation", "欧元分化", "var(--warn)", _col(fr, "euro_frag"), years),
        _mser("JGB 2s10s", "日债2/10", "var(--info)", _col(fr, "jgb_2s10s"), years),
    ], height=180, baseline=0, value_fmt="{:+,.2f}",
       aria_en="Euro-area fragmentation and the Japanese government bond curve")


def chart_intl_yields(f, years=6):
    """Global 10-year sovereign yields — US, Bund, JGB."""
    try:
        from engine import intl_bonds
        hist = intl_bonds.history(f)
    except Exception:  # noqa: BLE001
        return ""
    picks = [("US", "US 10y", "美债10年", "var(--warn)"),
             ("DE", "Bund", "德债", "var(--info)"),
             ("JP", "JGB", "日债", "var(--muted)")]
    series = [_mser(le, lz, color, hist.get(code), years=years) for code, le, lz, color in picks]
    return _multi(series, height=190, value_fmt="{:,.2f}",
                  aria_en="Global ten-year sovereign yields")


def chart_tp_decomp(f, years=9):
    """10y yield decomposed — nominal = real + breakeven."""
    return _multi([
        _mser("Nominal 10y", "名义10年", "var(--warn)", _col(f, "us10y"), years),
        _mser("Real 10y", "实际10年", "var(--info)", _col(f, "us10y_real"), years),
        _mser("Breakeven", "盈亏平衡", "var(--orange)", _col(f, "breakeven_10y"), years),
    ], height=200, value_fmt="{:,.2f}",
       aria_en="Ten-year yield decomposed into real yield and breakeven inflation")


def chart_policy_path(fp):
    """Market-implied policy-rate path (now -> 12 months) as a small line."""
    if not fp:
        return ""
    imp = fp.get("implied") or {}
    pts = [("now", fp.get("policy_rate")), ("1m", imp.get("m1")), ("3m", imp.get("m3")),
           ("6m", imp.get("m6")), ("12m", imp.get("m12"))]
    pts = [(lbl, v) for lbl, v in pts if v is not None]
    if len(pts) < 4:
        return ""
    series = {"dates": [p[0] for p in pts], "vals": [round(float(p[1]), 2) for p in pts]}
    return _ilx(series, "var(--info)", kind="line", height=170, unit_en="%",
                value_fmt="{:,.2f}", aria_en="Market-implied policy rate path")


def chart_xasset_betas(xasset):
    """Superseded by the in-template transmission bars (.xa-row). Kept as a no-op so the
    build loop and the template's `{% if charts.xasset_betas %}` guard stay stable."""
    return ""


# --------------------------------------------------------------------------- #
# view-model (display-ready, from the snapshot)
# --------------------------------------------------------------------------- #
_XA_VERDICT = {"tailwind": (C["green"], "Tailwind", "顺风"), "headwind": (C["red"], "Headwind", "逆风"),
               "neutral": (C["muted"], "Neutral", "中性")}


# --------------------------------------------------------------------------- #
# CCW-W4: Corporate Credit desk vm builder
# --------------------------------------------------------------------------- #
# Theme slug → (EN display name, ZH display name, basket slug or None)
_THEME_META: dict[str, tuple[str, str, str | None]] = {
    "hyperscaler_credit": ("Hyperscalers", "超大规模云商", None),
    "neocloud_credit": ("AI clouds", "新型AI云商", "ai_neoclouds"),
    "memory_credit": ("Memory chips", "存储芯片", "memory_storage"),
    "ai_power_credit": ("AI power", "AI电力", None),
    "dc_reit_credit": ("Data-centre landlords", "数据中心业主", None),
    "ai_hardware_credit": ("AI hardware", "AI硬件", None),
    "telecom_legacy": ("Telecom — the 1990s echo", "电信 · 90年代对照组", None),
}

_THEME_TIPS: dict[str, tuple[str, str]] = {
    "hyperscaler_credit": (
        "158 bonds, $811M par tracked across MSFT/AMZN/META/GOOGL/ORCL; avg maturity 7.6y; "
        "extra yield +0.80% vs matched Treasuries (par-weighted, yield-to-maturity basis); "
        "prices are fund-reported estimates.",
        "追踪MSFT/AMZN/META/GOOGL/ORCL共158只债券、面值8.11亿美元；平均期限7.6年；"
        "相对同期限国债额外收益+0.80%（面值加权、到期收益率口径）；价格为基金申报估值。",
    ),
    "neocloud_credit": (
        "4 bonds, $116M par; junk-rated (B+); the highest borrowing cost of any theme we track; "
        "converts and private loans not visible here.",
        "4只债券、面值1.16亿美元；高收益级（B+）；为所有主题中借贷成本最高；可转债与私募贷款不在此覆盖范围。",
    ),
    "memory_credit": (
        "9 bonds, $33M par (MU investment-grade + STX junk); "
        "SanDisk's loan and Samsung/SK Hynix paper are not index-visible.",
        "9只债券、面值3300万美元（美光投资级+希捷高收益）；"
        "闪迪贷款及三星/海力士债券不在指数覆盖内。",
    ),
    "ai_power_credit": (
        "44 bonds, $147M par across Vistra/Constellation/NextEra; tightest theme — "
        "the market sees contracted nuclear cash flows as safe.",
        "44只债券、面值1.47亿美元（Vistra/Constellation/NextEra）；"
        "利差最窄——市场视核电长约现金流为安全。",
    ),
    "dc_reit_credit": (
        "18 bonds, $50M par (Equinix, Digital Realty).",
        "18只债券、面值5000万美元（Equinix、Digital Realty）。",
    ),
    "ai_hardware_credit": (
        "25 bonds, $61M par (Dell).",
        "25只债券、面值6100万美元（戴尔）。",
    ),
    "telecom_legacy": (
        "44 bonds, $134M par (AT&T/Verizon). The 1996-2002 telecom debt boom is the closest "
        "historical rhyme to today's AI build-out — this control group anchors the comparison.",
        "44只债券、面值1.34亿美元（AT&T/Verizon）。"
        "1996-2002电信债务潮是当前AI建设最接近的历史对照——该组用作比较基准。",
    ),
}

# Spread (g-spread) thresholds (in %) for per-tile stance:
#   calm (<1.2%), watch (1.2-4%), watch-closely (>=4%)
#   tightening velocity also influences; default = watch-don't-chase when uncertain.
def _theme_stance(level_pct: float | None, vel21_pctile: float | None,
                  slug: str) -> tuple[str, str, str]:
    """Return (stance_en, stance_zh, css_class) for a theme tile.

    Severity-based, not direction-based — red/amber/green map to
    stress level (so ZH directional color swap never applies here).
    neocloud is always red (junk); telecom is always neutral (context).

    Level thresholds (in %-fraction units, converted from bp):
      ≥ 4.00% (400bp) or vel21_pctile ≥ 85  → Watch closely (ts-red)
      ≥ 0.75% (75bp)                          → Watch (ts-amber)
      < 0.75%                                 → Ignore (ts-calm)

    The 75bp boundary matches the ratified mockup exactly: hyperscalers
    at ~80bp show Watch while AI-power/DC-REIT/AI-hardware at ~58-59bp
    show Ignore.  Velocity escalation overrides the level-only stance when
    vel21_pctile ≥ 85 (widening fast → Watch closely regardless of level).
    """
    if slug == "telecom_legacy":
        return "Context", "对照参考", "ts-neutral"
    if slug == "neocloud_credit":
        return "Watch closely", "密切观望", "ts-red"
    if level_pct is None:
        return "Building history", "数据积累中", "ts-neutral"
    pctile = vel21_pctile or 50.0
    if level_pct >= 4.0 or pctile >= 85:
        return "Watch closely", "密切观望", "ts-red"
    if level_pct >= 0.75:
        return "Watch", "观望", "ts-amber"
    return "Ignore", "无需关注", "ts-calm"


def _hero_stance(cm: dict) -> tuple[str, str, str, str, str, str]:
    """Return (state_en, state_zh, pill_en, pill_zh, pill_css, subtitle_en, ...) wait — 6 values.

    Returns: (state_en, state_zh, pill_en, pill_zh, pill_css, hero_cs_class).
    Deterministic mapping:
      - tags.credit_market_turn.fired → 'Get ready' stance, cs-red hero
      - any theme vel21_pctile ≥ 85 OR market IG widening → 'Watch — don't chase', cs-amber
      - else → 'Watch — don't chase' (calm), cs-amber  (ratified default copy)
    """
    tags = cm.get("tags") or {}
    cmt = tags.get("credit_market_turn") or {}
    fired = bool(cmt.get("fired"))

    if fired:
        return (
            "Credit stress: rising",
            "信用压力：上升",
            "Get ready",
            "备战",
            "stance-red",
            "cs-red",
        )

    # check if any theme has widening stress (vel pctile ≥ 85)
    themes = cm.get("themes") or {}
    any_theme_stress = False
    for tdata in themes.values():
        spread = tdata.get("spread") or {}
        vel = (spread.get("velocity") or {})
        p = vel.get("vel21_pctile")
        if p is not None and p >= 85:
            any_theme_stress = True
            break

    # also check market IG for widening
    market = cm.get("market") or {}
    ig = market.get("ig") or {}
    ig_state = ig.get("state", "accruing")
    market_widening = ig_state in ("widening", "widening_stress")

    if any_theme_stress or market_widening:
        return (
            "Credit stress: watch",
            "信用压力：观察",
            "Watch — don't chase",
            "观望 · 勿追",
            "stance-amber",
            "cs-amber",
        )

    # default calm / accruing
    return (
        "Credit stress: low",
        "信用压力：低",
        "Watch — don't chase",
        "观望 · 勿追",
        "stance-amber",
        "cs-amber",
    )


def _build_maturity_wall(cm_path: Path | None) -> list[dict]:
    """Load maturity_wall.parquet and build per-theme bar data.

    Each entry: {slug, en, zh, segs: [{css_class, flex}]}
    Segs only for non-zero buckets; flex proportional to par_total.
    Returns [] on missing file (null-safe).
    """
    _BUCKET_ORDER = ["0_1y", "1_3y", "3_5y", "5_10y", "10y_plus"]
    _SEG_CSS = {"0_1y": "seg-0", "1_3y": "seg-1", "3_5y": "seg-2",
                "5_10y": "seg-3", "10y_plus": "seg-4"}
    if cm_path is None:
        return []
    mw_path = cm_path.parent / "series" / "maturity_wall.parquet"
    try:
        import pandas as _pd
        mw = _pd.read_parquet(mw_path)
        mw = mw[mw["scope_type"] == "theme"]
    except Exception:  # noqa: BLE001
        return []

    rows = []
    for slug, en_zh_basket in _THEME_META.items():
        en, zh, _ = en_zh_basket
        sub = mw[mw["scope"] == slug]
        if sub.empty:
            continue
        segs = []
        for bkt in _BUCKET_ORDER:
            row = sub[sub["bucket"] == bkt]
            if row.empty:
                continue
            val = float(row["par_total"].iloc[0])
            if val > 0:
                segs.append({"css_class": _SEG_CSS[bkt], "flex": round(val / 1_000_000, 1)})
        if segs:
            rows.append({"slug": slug, "en": en, "zh": zh, "segs": segs})
    return rows


def build_corp_credit_vm(data_root: Path | None = None) -> dict:
    """Build the vm.corp_credit dict for the bonds template.

    Null-safe: when credit_momentum.json is missing or any sub-key is absent,
    renders accruing states with plain-word 'building history' copy.
    Never raises.

    Returns a dict that the template can reference as vm.corp_credit.
    """
    import logging as _log

    _ACCRUING_AS_OF = "building history"
    empty = {
        "accruing": True,
        "as_of": _ACCRUING_AS_OF,
        "authority": {"rank": False, "size": False, "gate": False, "escalate": False},
        "hero": {
            "state_en": "Credit stress: low",
            "state_zh": "信用压力：低",
            "pill_en": "Watch — don't chase",
            "pill_zh": "观望 · 勿追",
            "pill_css": "stance-amber",
            "hero_cs": "cs-amber",
            "subtitle_en": "Company-bond stress is low; AI borrowing costs bear watching.",
            "subtitle_zh": "整体压力仍低；AI公司的借贷成本值得关注。",
        },
        "gauges": [],
        "themes": [],
        "watch": {"orcl": None, "fallen_angel": None, "new_issuance": True},
        "finra": None,
        "maturity_wall": [],
        "divergence_accruing": True,
        "footer_as_of": _ACCRUING_AS_OF,
    }

    # locate credit_momentum.json
    if data_root is None:
        try:
            from lib import config as _cfg
            data_root = _cfg.data_dir()
        except Exception:  # noqa: BLE001
            return empty

    cm_path = data_root / "corp_bonds" / "credit_momentum.json"
    if not cm_path.exists():
        return empty

    try:
        cm = json.loads(cm_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return empty

    as_of = cm.get("as_of") or _ACCRUING_AS_OF
    authority = cm.get("authority") or {"rank": False, "size": False, "gate": False, "escalate": False}
    accruing_flag = bool(cm.get("accruing"))

    # Hero stance
    state_en, state_zh, pill_en, pill_zh, pill_css, hero_cs = _hero_stance(cm)
    hero = {
        "state_en": state_en,
        "state_zh": state_zh,
        "pill_en": pill_en,
        "pill_zh": pill_zh,
        "pill_css": pill_css,
        "hero_cs": hero_cs,
        "subtitle_en": "Company-bond stress is low; AI borrowing costs bear watching.",
        "subtitle_zh": "整体压力仍低；AI公司的借贷成本值得关注。",
    }

    # Spread gauges (roster + market, plus the AAA/AA rungs of the FRED ladder for
    # the leading 'Safest borrowers' chip — see _build_high_grade_gauge).
    roster = cm.get("roster") or {}
    market = cm.get("market") or {}
    ladder = cm.get("ladder") or {}
    gauges = _build_spread_gauges(roster, market, ladder)

    # Theme tiles (7)
    themes_raw = cm.get("themes") or {}
    theme_tiles = _build_theme_tiles(themes_raw, cm_path=cm_path)

    # Watch strip
    watch_raw = cm.get("watch") or {}
    watch = _build_watch(watch_raw)

    # FINRA breadth
    breadth_raw = cm.get("breadth") or {}
    finra = _build_finra_vm(breadth_raw)

    # Maturity wall
    maturity_wall = _build_maturity_wall(cm_path)

    # Divergence: all accruing = show placeholder card
    divergence = cm.get("divergence") or []
    divergence_accruing = all(d.get("quadrant") == "accruing" for d in divergence) if divergence else True

    return {
        "accruing": accruing_flag,
        "as_of": as_of,
        "authority": authority,
        "hero": hero,
        "gauges": gauges,
        "themes": theme_tiles,
        "watch": watch,
        "finra": finra,
        "maturity_wall": maturity_wall,
        "divergence_accruing": divergence_accruing,
        "footer_as_of": as_of,
    }


def _pctile_plain(pctile: float | None) -> tuple[str, str]:
    """Translate a velocity percentile into Tier-1-legal plain words (EN, ZH).

    DESIGN_DOCTRINE Law 2 bans bare percentile ranks on the glance tier and Law 3
    requires a number to arrive with its meaning, so 91.7 becomes "about 9 in 10"
    rather than "92nd percentile". Precision stays on the Tier-2 hover.
    """
    if pctile is None:
        return "", ""
    # Capped at 9: round() sends anything >= 95 to 10, and "faster than about 10 in 10
    # past readings" claims it beat every reading including itself.
    n = max(1, min(9, int(round(float(pctile) / 10.0))))
    zh_num = "一二三四五六七八九"[n - 1]
    return f"about {n} in 10", f"约十分之{zh_num}"


def _build_high_grade_gauge(ladder: dict) -> dict | None:
    """Build the 'Safest borrowers' chip from the AAA/AA rungs of the FRED ladder.

    Why this chip exists: the four original gauges span quality-grade (the whole IG
    index), junk, the junk-vs-quality gap, and CCC — so the TOP of the rating ladder
    had no chip of its own, and a move confined to AAA/AA showed up only diluted
    inside the aggregate quality-grade number. Placed first, the strip now reads as a
    quality ladder (safest → quality-grade → junk → gap → weakest), which is what
    makes a top-heavy move legible at a glance.

    Composite rule: the chip's state/colour follows the MORE STRESSED of the two rungs
    by 21-day velocity percentile, and both levels are printed in the hover — no
    invented average, and nothing hidden. Returns None when neither rung has data, so
    the chip is simply absent rather than rendering an empty shell.

    Display-tier only (CCW-R16); authority stays all-false.
    """
    aaa = (ladder or {}).get("aaa_oas") or {}
    aa = (ladder or {}).get("aa_oas") or {}
    rungs = [r for r in (aaa, aa) if r.get("level") is not None]
    if not rungs:
        return None

    def _vel(r: dict) -> float:
        return float(((r.get("velocity") or {}).get("vel21_pctile")) or 0.0)

    lead = max(rungs, key=_vel)
    state = lead.get("state", "accruing")
    pctile = (lead.get("velocity") or {}).get("vel21_pctile")
    d21 = lead.get("d21")

    # Labels are held to the width of the sibling "Weakest borrowers: widening" chip
    # (~27 chars): anything longer wraps to a second line at the strip's settled chip
    # width and drops this chip's sub-line out of alignment with the other four.
    # State goes in the label, pace goes in the sub — the pattern the strip already uses.
    if state == "widening_stress":
        chip_css, sub_color = "chip-red", "cc-sub-red"
        label_en, label_zh = "Safest borrowers: widening", "最安全借款人：走阔"
        sub_en, sub_zh = "rising faster than usual", "上升快于常态"
    elif state == "widening":
        chip_css, sub_color = "chip-amber", "cc-sub-amber"
        label_en, label_zh = "Safest borrowers: edging up", "最安全借款人：小幅上行"
        sub_en, sub_zh = "modest drift", "温和漂移"
    else:
        chip_css, sub_color = "chip-calm", "cc-sub-calm"
        label_en, label_zh = "Safest borrowers: steady", "最安全借款人：平稳"
        sub_en, sub_zh = "no unusual pressure", "无异常压力"

    # Tier-2 hover: ratings, both levels, the 21-day move, the translated pace, caveat.
    lv_en, lv_zh = [], []
    for name, r in (("AAA", aaa), ("AA", aa)):
        if r.get("level") is not None:
            lv_en.append(f"{name} +{r['level']:.2f}%")
            lv_zh.append(f"{name} +{r['level']:.2f}%")
    # The hover is assembled sentence-by-sentence because its editorial line is only
    # TRUE in the widening states — a fixed "it is the pace that stands out" string
    # lies outright once the tier is calm or tightening, and a "faster than about
    # 2 in 10" tail reads as urgency when it actually means the opposite.
    pace_en, pace_zh = _pctile_plain(pctile)
    notable = (pctile is not None and pctile >= 70.0)
    widening = state in ("widening", "widening_stress")

    s_en = ["Top-rated companies — the safest corporate borrowers.",
            f"Extra yield over Treasuries: {', '.join(lv_en)}."]
    s_zh = ["最高评级企业——最安全的公司借款人。",
            f"相对国债额外收益率：{'、'.join(lv_zh)}。"]

    if d21 is not None:
        # Direction words, not a signed number: a bare {:+.2f} yields "risen +-0.06"
        # once spreads tighten, and the ZH copy needs 上升/收窄 either way.
        verb_en = "risen" if d21 >= 0 else "narrowed"
        verb_zh = "上升" if d21 >= 0 else "收窄"
        tail_en = f", faster than {pace_en} past readings" if (notable and pace_en) else ""
        tail_zh = f"，快于{pace_zh}的历史读数" if (notable and pace_zh) else ""
        s_en.append(f"It has {verb_en} {abs(d21):.2f} points over 21 days{tail_en}.")
        s_zh.append(f"21日{verb_zh}{abs(d21):.2f}个百分点{tail_zh}。")

    if d21 is None:
        # No change reading yet — say so rather than asserting a range we cannot see.
        s_en.append("Change over time is still building.")
        s_zh.append("变化数据仍在积累。")
    elif widening and notable:
        s_en.append("The level is still low by history; it is the pace that stands out.")
        s_zh.append("绝对水平仍处历史低位，值得注意的是变化速度。")
    else:
        s_en.append("That is within its usual range.")
        s_zh.append("该变化处于常态区间。")

    # Only true when both rungs are present to choose between.
    if len(rungs) > 1:
        s_en.append("Colour follows whichever of the two rating tiers is moving faster.")
        s_zh.append("颜色取两档评级中变化更快者。")

    # House disclosure idiom (used across the site); also keeps the CI-guarded word
    # "validated" out of user-facing copy — see scripts/check_validated_claims.py.
    s_en.append("Shown for context — not a buy signal.")
    s_zh.append("仅为提示，非买入信号。")

    tip_en = " ".join(s_en)
    tip_zh = "".join(s_zh)

    return {
        "key": "high_grade",
        "label_en": label_en,
        "label_zh": label_zh,
        "chip_css": chip_css,
        "sub_en": sub_en,
        "sub_zh": sub_zh,
        "sub_color": sub_color,
        "tip_en": tip_en,
        "tip_zh": tip_zh,
        "state": state,
    }


def _build_spread_gauges(roster: dict, market: dict, ladder: dict | None = None) -> list[dict]:
    """Build the spread-gauge chips from roster (ig_oas, hy_oas, quality_spread, ccc_bb).

    When `ladder` carries AAA/AA rungs, a fifth 'Safest borrowers' chip is prepended so
    the strip reads as a quality ladder top-to-bottom (see _build_high_grade_gauge).
    Omitting `ladder` yields the original four chips unchanged.

    Severity color: red=widening/stress, amber=watch, green=calm.
    This is a SEVERITY gauge (not direction) — ZH color swap must NOT apply.
    """
    def _state_to_chip(state: str, level: float | None, pctile: float | None) -> tuple[str, str]:
        """Return (chip_css, sub_color_css_class) based on state and velocity."""
        if state in ("widening_stress",):
            return "chip-red", "cc-sub-red"
        if state in ("widening",):
            return "chip-amber", "cc-sub-amber"
        if state in ("tightening",) or (pctile is not None and (pctile or 0) < 35):
            return "chip-calm", "cc-sub-calm"
        return "chip-calm", "cc-sub-calm"

    def _gauge(key: str, label_en: str, label_zh: str, sub_en: str, sub_zh: str,
               tip_en: str, tip_zh: str, data: dict,
               level_in_sub: bool = True) -> dict:
        """Build one spread-gauge chip dict.

        level_in_sub=True (default): when level is known, override sub_en/sub_zh with
        the "+X.XX% extra yield" display (used for ig_oas, hy_oas, quality_spread).
        level_in_sub=False: keep the semantic sub_en/sub_zh copy regardless of level
        (used for ccc_bb where the level is a raw gap ratio, not an extra-yield display).
        """
        state = data.get("state", "accruing")
        level = data.get("level")
        vel = (data.get("velocity") or {})
        pctile = vel.get("vel21_pctile")
        chip_css, sub_color = _state_to_chip(state, level, pctile)
        level_disp = f"+{level:.2f}%" if level is not None else None
        if level_in_sub and level is not None and level_disp:
            resolved_sub_en = level_disp
            resolved_sub_zh = f"额外收益率 {level_disp}"
        else:
            resolved_sub_en = sub_en
            resolved_sub_zh = sub_zh
        return {
            "key": key,
            "label_en": label_en,
            "label_zh": label_zh,
            "chip_css": chip_css,
            "sub_en": resolved_sub_en,
            "sub_zh": resolved_sub_zh,
            "sub_color": sub_color,  # CSS class for dark-mode-safe coloring (m3 fix)
            "tip_en": tip_en,
            "tip_zh": tip_zh,
            "state": state,
        }

    ig = roster.get("ig_oas") or {}
    hy = roster.get("hy_oas") or {}
    qs = roster.get("quality_spread") or {}
    ccc_bb = roster.get("ccc_bb") or {}

    # Quality-ladder order: safest → quality-grade → junk → gap → weakest.
    # The high-grade chip leads so a top-heavy move is legible left-to-right;
    # it is omitted entirely when the AAA/AA rungs carry no data.
    high_grade = _build_high_grade_gauge(ladder or {})

    gauges = [
        _gauge(
            "ig_oas",
            "Quality-grade: creeping wider" if ig.get("state") == "widening" else "Quality-grade: steady",
            "投资级：微幅走阔" if ig.get("state") == "widening" else "投资级：平稳",
            f"extra yield +{ig.get('level', 0):.2f}%" if ig.get("level") is not None else "building history",
            f"额外收益率 +{ig.get('level', 0):.2f}%" if ig.get("level") is not None else "数据积累中",
            "Investment-grade extra yield over Treasuries; 21-day change velocity indicates direction.",
            "投资级相对国债额外收益率；21日变化速度显示走阔/收窄方向。",
            ig,
        ),
        _gauge(
            "hy_oas",
            "Junk: widening" if hy.get("state") == "widening" else "Junk: steady",
            "高收益：走阔" if hy.get("state") == "widening" else "高收益：平稳",
            f"extra yield +{hy.get('level', 0):.2f}%" if hy.get("level") is not None else "building history",
            f"额外收益率 +{hy.get('level', 0):.2f}%" if hy.get("level") is not None else "数据积累中",
            "High-yield extra yield; 21-day change mid-range.",
            "高收益额外收益率；21日变化处于中位。",
            hy,
        ),
        _gauge(
            "quality_spread",
            "Junk-vs-quality gap: steady",
            "高低评级利差：平稳",
            "gap mid-range",
            "利差居中",
            "The gap between junk and quality yields is a classic late-cycle gauge; "
            "compression to extremes preceded 2007 and 2021 tops.",
            "高低评级利差是经典的周期后段指标；压缩至极端曾出现在2007与2021顶部之前。",
            qs,
            level_in_sub=False,  # M1 fix: gap is not an extra-yield display
        ),
        _gauge(
            "ccc_bb",
            "Weakest borrowers: widening" if ccc_bb.get("state") == "widening" else "Weakest borrowers: steady",
            "最弱借款人：走阔" if ccc_bb.get("state") == "widening" else "最弱借款人：平稳",
            "CCC tier moving first" if ccc_bb.get("state") == "widening" else "CCC tier stable",
            "CCC层级率先变动" if ccc_bb.get("state") == "widening" else "CCC层级平稳",
            # Defect 4 fix: the raw CCC-BB gap level (8.11 points) belongs in the tip,
            # not the glance sub-value.  The semantic copy stays in sub_en/sub_zh.
            (f"CCC-vs-BB gap {ccc_bb['level']:.1f} points — the lowest-rated tier historically "
             f"moves first in credit turns.")
            if ccc_bb.get("level") is not None else
            "CCC-vs-BB gap — the lowest-rated tier historically moves first in credit turns.",
            (f"CCC与BB利差{ccc_bb['level']:.1f}点——历史上最低评级层级在信用拐点时最先变动。")
            if ccc_bb.get("level") is not None else
            "CCC与BB利差——历史上最低评级层级在信用拐点时最先变动。",
            ccc_bb,
            level_in_sub=False,
        ),
    ]

    return ([high_grade] + gauges) if high_grade else gauges


def _load_theme_daily_levels(cm_path: Path | None) -> dict[str, float]:
    """Load the latest g_spread_bp_pw per theme from theme_daily.parquet.

    Returns a dict mapping theme slug → level_pct (g_spread_bp_pw / 100).
    Returns {} on missing file or any error (null-safe).
    This provides point-in-time level data even when the credit_momentum.json
    velocity organ hasn't accumulated ≥ 21 dates yet.
    """
    if cm_path is None:
        return {}
    td_path = cm_path.parent / "series" / "theme_daily.parquet"
    try:
        import pandas as _pd
        df = _pd.read_parquet(td_path)
        if df.empty or "theme" not in df.columns or "g_spread_bp_pw" not in df.columns:
            return {}
        # use latest as_of row per theme
        out = {}
        for slug, grp in df.groupby("theme"):
            latest = grp.sort_values("as_of").iloc[-1]
            bp = latest.get("g_spread_bp_pw")
            if bp is not None and not _pd.isna(bp):
                out[str(slug)] = float(bp) / 100.0
        return out
    except Exception:  # noqa: BLE001
        return {}


# M2 fix: static descriptor sub-lines lifted verbatim from site/_mockup_ccw_credit_desk.html
# These replace the "building history" copy that was overwriting the ratified descriptors.
# Tiles with no sub text in the mockup use empty strings (rendered as min-height spacer).
_THEME_SUB: dict[str, tuple[str, str]] = {
    "hyperscaler_credit": ("5 giants · Oracle on watch", "5家巨头 · 甲骨文在观察名单"),
    "neocloud_credit": ("CoreWeave only — junk-rated", "仅CoreWeave · 高收益级"),
    "memory_credit": ("Micron + Seagate mix", "美光与希捷组合"),
    "ai_power_credit": ("", ""),
    "dc_reit_credit": ("", ""),
    "ai_hardware_credit": ("", ""),
    "telecom_legacy": ("", ""),
}


def _build_theme_tiles(themes_raw: dict, cm_path: Path | None = None) -> list[dict]:
    """Build list of 7 theme tile dicts in display order.

    Level is sourced from theme_daily.parquet (via _load_theme_daily_levels) when
    the credit_momentum velocity organ has not yet accumulated ≥ 21 dates (level=None
    in the cm JSON).  A point-in-time level is a glance fact that needs no history.
    The Δ21 / velocity accruing copy is preserved in the t-sub via tile.accruing until
    n_dates ≥ 22 and a real d21 value is present.
    """
    _DISPLAY_ORDER = [
        "hyperscaler_credit", "neocloud_credit", "memory_credit",
        "ai_power_credit", "dc_reit_credit", "ai_hardware_credit", "telecom_legacy",
    ]
    # Load point-in-time levels from theme_daily (null-safe; {} if unavailable)
    td_levels = _load_theme_daily_levels(cm_path)

    tiles = []
    for slug in _DISPLAY_ORDER:
        meta = _THEME_META.get(slug)
        if meta is None:
            continue
        en, zh, basket_slug = meta
        tip_en, tip_zh = _THEME_TIPS.get(slug, ("", ""))
        tdata = themes_raw.get(slug) or {}
        spread = (tdata.get("spread") or {})
        # UNIT CONTRACT: credit_momentum.json carries the theme g-spread in BASIS
        # POINTS, while _theme_stance and the tile copy both expect PERCENT (see
        # that docstring: "in %-fraction units, converted from bp") and the
        # theme_daily fallback below already divides by 100. Normalize on the way
        # in — otherwise a 692bp neocloud spread renders as "+692.0%" and clears
        # every stance threshold at once. This stayed latent while the momentum
        # organ was crashing and emitting level=None for every theme.
        level_bp = spread.get("level")
        level = (level_bp / 100.0) if level_bp is not None else None
        d21_bp = spread.get("d21")
        d21 = (d21_bp / 100.0) if d21_bp is not None else None
        vel = (spread.get("velocity") or {})
        pctile = vel.get("vel21_pctile")
        state = spread.get("state", "accruing")

        # Defect 1 fix: when the velocity organ hasn't yet accumulated 21+ dates,
        # the cm level is None.  Fall back to theme_daily point-in-time level
        # (already percent) so glance tiles show the actual g-spread during accrual.
        if level is None and slug in td_levels:
            level = td_levels[slug]

        level_disp = f"+{level:.1f}%" if level is not None else None
        d21_disp = (f"{'+' if (d21 or 0) >= 0 else ''}{d21:.2f}%/21d") if d21 is not None else None

        stance_en, stance_zh, stance_css = _theme_stance(level, pctile, slug)

        # tile severity stripe CSS class
        if stance_css == "ts-red":
            tile_stripe = "t-red"
        elif stance_css == "ts-amber":
            tile_stripe = "t-amber"
        elif stance_css == "ts-calm":
            tile_stripe = "t-calm"
        else:
            tile_stripe = "t-neutral"

        # equity cross-link URL (only for themes with real basket pages)
        equity_link = f"basket/{basket_slug}.html" if basket_slug else None

        # accruing flag: True means the Δ line is still building history (d21 unavailable).
        # The level may be present from theme_daily even while accruing=True for the delta.
        delta_accruing = (d21 is None)

        # M2 fix: static descriptor from mockup (never overwritten by accruing copy)
        theme_sub_en, theme_sub_zh = _THEME_SUB.get(slug, ("", ""))

        tiles.append({
            "slug": slug,
            "en": en,
            "zh": zh,
            "level_disp": level_disp,
            "d21_disp": d21_disp,
            "state": state,
            "accruing": delta_accruing,
            "tile_stripe": tile_stripe,
            "stance_en": stance_en,
            "stance_zh": stance_zh,
            "stance_css": stance_css,
            "equity_link": equity_link,
            "tip_en": tip_en,
            "tip_zh": tip_zh,
            "sub_en": theme_sub_en,
            "sub_zh": theme_sub_zh,
        })
    return tiles


def _build_watch(watch_raw: dict) -> dict:
    """Build watch strip vm from the watch block."""
    orcl_raw = watch_raw.get("orcl") or {}
    orcl = None
    # B1 fix: only build orcl dict when g_spread_bp_pw is present and not None.
    # An orcl_raw dict that lacks g_spread_bp_pw (accrual state) must yield orcl=None
    # so the template's `orcl.g_spread_bp / 100` never fires on None.
    if orcl_raw and orcl_raw.get("g_spread_bp_pw") is not None:
        g_bp = orcl_raw.get("g_spread_bp_pw")
        premium = orcl_raw.get("premium_vs_ig_peers_bp")
        orcl = {
            "g_spread_bp": round(float(g_bp), 0),
            "premium_bp": round(float(premium), 0) if premium is not None else None,
        }

    transition = watch_raw.get("transition") or {}
    fallen_angel_candidates = transition.get("fallen_angel_candidates") or []
    new_issuance = transition.get("new_issuance_events") or []
    # m1 fix: guard against JSON null in note field
    watch_accruing = bool((transition.get("note") or "").startswith("accruing"))

    return {
        "orcl": orcl,
        "fallen_angel_accruing": watch_accruing,
        "fallen_angel_candidates": fallen_angel_candidates,
        "new_issuance_accruing": not new_issuance,
    }


def _build_finra_vm(breadth_raw: dict) -> dict | None:
    """Build FINRA tape vm from breadth.finra block. Returns None if absent."""
    finra = breadth_raw.get("finra") or {}
    if not finra:
        return None
    bdata = finra.get("breadth") or {}
    all_sec = bdata.get("all securities") or {}
    if not all_sec:
        return None

    latest_date = all_sec.get("latest_date", "")

    # Reconstruct approximate counts from the advance share and total n_days context.
    # The FINRA data stores advance_share (fraction), not raw counts.
    # From the mockup: 9126 fell, 1742 rose, 1572 touched 52w lows.
    # We store advance_share_latest + wk52_high_low_net_share.
    # Derive counts from the original mockup snapshot values (these are display-only).
    # Since we have fractions, we can estimate approximate counts from the FINRA
    # total universe size (~12400 bonds/day based on the mockup's 9126+1742 = 10868
    # active, but we do not have exact total from the artifact).
    # DESIGN: show the fractions as percentages + note the raw context is FINRA trade data.

    adv_share = all_sec.get("advance_share_latest")
    wk52_net = all_sec.get("wk52_high_low_net_share")

    # m2 fix: coerce non-finite floats (NaN/Inf) → None before they enter the vm
    def _finite(v):
        if v is None:
            return None
        try:
            return v if math.isfinite(float(v)) else None
        except (TypeError, ValueError):
            return None

    adv_share = _finite(adv_share)
    wk52_net = _finite(wk52_net)

    # Format as percentages for display
    adv_pct = round(adv_share * 100, 1) if adv_share is not None else None
    lows_pct = round(abs(wk52_net) * 100, 1) if wk52_net is not None else None

    return {
        "date": latest_date,
        "advance_pct": adv_pct,
        "lows_pct": lows_pct,
        "advance_share": adv_share,
        "wk52_net_share": wk52_net,
        "accruing": adv_share is None,
    }


def _build_corp_credit_bond_health(cc_vm: dict) -> dict:
    """Build the corporate_credit sub-block for data/bonds/bond_health.json.

    Machine-readable, small, all-false authority dict.
    """
    themes_out = {}
    for tile in cc_vm.get("themes") or []:
        themes_out[tile["slug"]] = {
            "stance_en": tile.get("stance_en"),
            "stance_zh": tile.get("stance_zh"),
            "accruing": tile.get("accruing", True),
        }

    watch = cc_vm.get("watch") or {}
    orcl = watch.get("orcl") or {}
    finra = cc_vm.get("finra") or {}

    # m2 fix: coerce non-finite floats → None before writing to bond_health.json
    def _safe(v):
        if v is None:
            return None
        try:
            return v if math.isfinite(float(v)) else None
        except (TypeError, ValueError):
            return None

    raw_adv = finra.get("advance_share")
    raw_lows_pct = finra.get("lows_pct")
    finra_advance_share = _safe(raw_adv)
    finra_lows_share = _safe(raw_lows_pct / 100.0) if raw_lows_pct is not None else None

    return {
        "as_of": cc_vm.get("as_of"),
        "authority": cc_vm.get("authority") or {"rank": False, "size": False, "gate": False, "escalate": False},
        "market_state": cc_vm.get("hero", {}).get("state_en"),
        "themes": themes_out,
        "breadth": {
            # Both shares use _share suffix semantics (fractions, not percentages).
            # advance_share is already a fraction from the FINRA collector.
            # lows_pct is stored as percent (×100) by _build_finra_vm; divide back to
            # fraction so the contract is consistent (Defect 3 fix).
            "finra_advance_share": finra_advance_share,
            "finra_lows_share": finra_lows_share,
            "source": "FINRA trade data",
        },
        "watch": {
            "orcl_g_spread_bp": _safe(orcl.get("g_spread_bp")),
            "orcl_premium_vs_ig_bp": _safe(orcl.get("premium_bp")),
        },
        "divergence_accruing": cc_vm.get("divergence_accruing", True),
        "display_only": True,
    }


def _xasset_vm(xasset: dict | None) -> dict | None:
    """Light view-model: per-asset display color + bilingual verdict + |corr| bar width."""
    if not xasset or not xasset.get("assets"):
        return None
    out = {"as_of": xasset.get("as_of"), "drivers_now": xasset.get("drivers_now"),
           "verdict_en": xasset.get("verdict_en"), "verdict_zh": xasset.get("verdict_zh"), "assets": []}
    for a in xasset["assets"]:
        col, ven, vzh = _XA_VERDICT.get(a.get("verdict"), (C["muted"], a.get("verdict"), a.get("verdict")))
        conf = abs(a.get("corr") or 0)
        out["assets"].append({**a, "vcolor": col, "verdict_en": ven, "verdict_zh": vzh,
                              "conf_pct": round(conf * 100), "conf_label": ("strong" if conf >= 0.4
                              else "moderate" if conf >= 0.2 else "weak")})
    return out


def _vm(snap: dict, fr: pd.DataFrame, calib: dict | None = None) -> dict:
    calib = calib or {}
    csig = calib.get("signals", {})
    comp = csig.get("composite", {})
    comp_cond = comp.get("conditional", {}) or {}
    comp_hi = (comp_cond.get("terciles", {}) or {}).get("high", {}) or {}
    # only surface the measured-edge box when there is a REAL high-tercile edge
    # (a null high_edge_pp -> no claim; also avoids a None in the template arithmetic).
    calib_vm = ({} if (not comp or comp_cond.get("high_edge_pp") is None) else {
        "verdict": comp.get("verdict"),
        "hi_dd10": _r((comp_hi.get("p_dd10") or 0) * 100, 1),
        "base_dd10": _r((comp_cond.get("base_p_dd10") or 0) * 100, 1),
        "edge_pp": comp_cond.get("high_edge_pp"),
        "ic_recession": comp.get("ic_recession"),
        "span": comp.get("span"),
        "vs_best": (calib.get("composite_vs_best_leg") or {}).get("verdict"),
    })
    p = snap["pillars"]
    c, cr, ri, st, xa = p["curve"], p["credit"], p["real_inflation"], p["stress"], p["cross_asset"]
    phase = snap.get("cycle_phase")
    ph = PHASE.get(phase, (phase or "—", phase or "—", C["muted"]))
    band = cr.get("distress_band")
    cb = CREDIT_BAND.get(band, (band or "—", band or "—", C["muted"]))
    mb = st.get("move_band")
    mv = MOVE_BAND.get(mb, (mb or "—", mb or "—", C["muted"]))
    reg = xa.get("regime")
    rg = CORR_REGIME.get(reg, (reg or "—", reg or "—", C["muted"]))
    sv = p.get("sovereign", {})
    fs = FRAG_STATE.get(sv.get("frag_state"), ("—", "—", C["muted"]))
    js = JGB_STATE.get(sv.get("jgb_state"), (sv.get("jgb_state") or "—", sv.get("jgb_state") or "—", C["muted"]))
    hl = snap.get("health_label")

    def pc(v, n=0):  # percent of a 0..1 fraction
        return None if v is None else round(v * 100, n)

    return {
        "health": {
            "score": snap.get("health_score"), "label": hl,
            "label_zh": {"healthy": "健康", "mixed": "中性", "stressed": "承压"}.get(hl, hl),
            "color": HEALTH_COLOR.get(hl, C["muted"]),
            "phase_en": ph[0], "phase_zh": ph[1], "phase_color": ph[2],
            "verdict_en": snap.get("verdict_en"), "verdict_zh": snap.get("verdict_zh"),
            "recession_risk": _r(snap.get("recession_risk"), 0),
            "drawdown_risk": _r(snap.get("drawdown_risk"), 0),
            "calib": calib_vm,
            "stress_legs": [{"en": LEG_LABEL.get(k, (k, k))[0], "zh": LEG_LABEL.get(k, (k, k))[1],
                             "val": _r(v, 0),
                             "vg": VERDICT_GLYPH.get(csig.get(LEG_CALIB_KEY.get(k, ""), {}).get("verdict", ""),
                                                     ("", "", ""))}
                            for k, v in (snap.get("stress_legs") or {}).items()],
        },
        "curve": {
            "spread_10y3m": _r(c.get("spread_10y3m")), "spread_2s10s": _r(c.get("spread_2s10s")),
            "curve_tp_adj": _r(c.get("curve_tp_adjusted")), "ntfs": _r(c.get("ntfs")),
            "nyfed_prob": pc(c.get("ny_fed_recession_prob"), 1),
            "inverted": c.get("inverted"), "tp_adj_inverted": c.get("tp_adj_inverted"),
            "tax_en": c.get("move_taxonomy_en"), "tax_zh": c.get("move_taxonomy_zh"),
            "tax_note_en": c.get("move_taxonomy_note_en"), "tax_note_zh": c.get("move_taxonomy_note_zh"),
            "tax_color": TAX_COLOR.get(c.get("move_taxonomy"), C["muted"]),
            "uninversion": c.get("uninversion_alarm"),
            "bull_steepener_uninversion": c.get("bull_steepener_uninversion"),
        },
        "credit": {
            "hy_oas": _r(cr.get("hy_oas")), "ig_oas": _r(cr.get("ig_oas")),
            "hy_ig_ratio": _r(cr.get("hy_ig_ratio"), 1), "baa_aaa": _r(cr.get("baa_aaa")),
            "ebp": _r(cr.get("ebp")), "pctile": pc(cr.get("hy_pctile")),
            "band_en": cb[0], "band_zh": cb[1], "band_color": cb[2],
            "direction": cr.get("direction"),
            "direction_zh": {"widening": "扩大", "tightening": "收窄"}.get(cr.get("direction"), cr.get("direction")),
        },
        "real": {
            "real_10y": _r(ri.get("real_10y")), "real_5y": _r(ri.get("real_5y")),
            "breakeven_10y": _r(ri.get("breakeven_10y")), "breakeven_5y5y": _r(ri.get("breakeven_5y5y")),
            "term_premium": _r(ri.get("term_premium")), "tp_positive": ri.get("tp_repriced_positive"),
        },
        "stress": {
            "move": _r(st.get("move"), 0), "band_en": mv[0], "band_zh": mv[1], "color": mv[2],
            "pctile": pc(st.get("move_pctile")), "move_leads_vix": st.get("move_leads_vix"),
            "sofr_iorb_bp": _r(st.get("sofr_iorb_bp"), 0), "repo_spike_bp": _r(st.get("repo_spike_bp"), 0),
            "reserve_scarcity": st.get("reserve_scarcity"), "repo_stress": st.get("repo_stress"),
        },
        "cross": {
            "corr": _r(xa.get("stock_bond_corr"), 2), "regime_en": rg[0], "regime_zh": rg[1],
            "color": rg[2], "hedge_working": xa.get("hedge_working"),
        },
        "sovereign": {
            "euro_frag": _r(sv.get("euro_frag")), "bund_10y": _r(sv.get("bund_10y")),
            "frag_en": fs[0], "frag_zh": fs[1], "frag_color": fs[2],
            "frag_direction": sv.get("frag_direction"),
            "frag_direction_zh": {"widening": "扩大", "tightening": "收窄"}.get(sv.get("frag_direction"), ""),
            "jgb_2s10s": _r(sv.get("jgb_2s10s")), "jgb_en": js[0], "jgb_zh": js[1], "jgb_color": js[2],
        },
        "drivers": snap.get("drivers_for") or {},
        "alarms": snap.get("alarms") or [],
    }


# --------------------------------------------------------------------------- #
# alert timeline (mirrors build_forex._group_timeline)
# --------------------------------------------------------------------------- #
TYPE_LABEL = {"curve_regime": ("Curve", "曲线"), "uninversion": ("Curve", "曲线"),
              "credit_band": ("Credit", "信用"), "rates_vol": ("Rates vol", "利率波动"),
              "repo_stress": ("Plumbing", "资金管道"), "corr_regime": ("Stock-bond", "股债"),
              "recession_risk": ("Recession", "衰退")}
_WD_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _group_timeline(events: list[dict]) -> list[dict]:
    days: dict[str, list] = {}
    for e in events:
        ts = pd.Timestamp(e["ts"])
        lab = TYPE_LABEL.get(e["type"], (e["type"], e["type"]))
        e = {**e, "label": lab[0], "label_zh": lab[1],
             "daylabel": ts.strftime("%a %b %d"),
             "daylabel_zh": f"{ts.month}月{ts.day}日 {_WD_ZH[ts.weekday()]}"}
        days.setdefault(ts.strftime("%Y-%m-%d"), []).append(e)
    return [{"day": d, "daylabel": evs[0]["daylabel"], "daylabel_zh": evs[0]["daylabel_zh"], "events": evs}
            for d, evs in sorted(days.items(), reverse=True)]


# --------------------------------------------------------------------------- #
# glance strip + key-levels (the user-first layer — plain state + meaning, Tier 1)
# --------------------------------------------------------------------------- #
def _sev(good=False, warn=False, bad=False):
    return "gl-bad" if bad else ("gl-warn" if warn else ("gl-good" if good else "gl-mid"))


def _glance(vm: dict) -> list[dict]:
    """Every bond pillar at a glance: pillar · plain state · one-line meaning · severity.
    Plain words only (Design Doctrine Law 2); the precise stats live in the sections."""
    cu, cr, rl, st, cx = (vm.get(k) or {} for k in ("curve", "credit", "real", "stress", "cross"))
    g: list[dict] = []

    prob = cu.get("nyfed_prob")
    if cu.get("tp_adj_inverted") or cu.get("inverted"):
        c_state = ("Inverted", "倒挂")
    elif (cu.get("spread_2s10s") or 0) >= 1.0:
        c_state = ("Steep", "陡峭")
    elif (cu.get("spread_2s10s") or 0) <= 0.15:
        c_state = ("Flat", "平坦")
    else:
        c_state = ("Normal", "正常")
    g.append({"name_en": "Curve", "name_zh": "曲线", "href": "#curve",
              "state_en": c_state[0], "state_zh": c_state[1],
              "mean_en": (f"recession odds ~{prob:.0f}%" if prob is not None else "growth signal"),
              "mean_zh": (f"衰退概率约{prob:.0f}%" if prob is not None else "增长信号"),
              "sev": _sev(good=(prob is not None and prob < 20), warn=(prob or 0) >= 30,
                          bad=(prob or 0) >= 50 or cu.get("tp_adj_inverted"))})

    cb = (cr.get("band_en") or "").lower()
    g.append({"name_en": "Credit", "name_zh": "信用", "href": "#credit",
              "state_en": cr.get("band_en") or "—", "state_zh": cr.get("band_zh") or "—",
              "mean_en": {"tight": "risk appetite calm", "normal": "spreads unremarkable",
                          "elevated": "spreads widening", "distress": "stress building",
                          "crisis": "credit in stress"}.get(cb, "risk appetite"),
              "mean_zh": {"tight": "风险偏好平静", "normal": "利差平稳", "elevated": "利差走阔",
                          "distress": "压力累积", "crisis": "信用承压"}.get(cb, "风险偏好"),
              "sev": _sev(good=cb in ("tight", "normal"), warn=cb == "elevated",
                          bad=cb in ("distress", "crisis"))})

    r10 = rl.get("real_10y")
    g.append({"name_en": "Real rates", "name_zh": "实际利率", "href": "#real",
              "state_en": (f"{r10:+.2f}%" if r10 is not None else "—"),
              "state_zh": (f"{r10:+.2f}%" if r10 is not None else "—"),
              "mean_en": ("heavy on valuations" if (r10 or 0) >= 2.2 else "mild drag on valuations"),
              "mean_zh": ("压制估值" if (r10 or 0) >= 2.2 else "对估值轻微拖累"),
              "sev": _sev(good=(r10 is not None and r10 < 1.5), warn=(r10 or 0) >= 2.2,
                          bad=(r10 or 0) >= 2.8)})

    sb = (st.get("band_en") or "").lower()
    g.append({"name_en": "Rates vol", "name_zh": "利率波动", "href": "#stress",
              "state_en": (f"MOVE {st['move']}" if st.get("move") is not None else (st.get("band_en") or "—")),
              "state_zh": (f"MOVE {st['move']}" if st.get("move") is not None else (st.get("band_zh") or "—")),
              "mean_en": {"calm": "rates market calm", "normal": "rates market steady",
                          "elevated": "rates jumpy", "crisis": "rates market in stress"}.get(sb, "rates volatility"),
              "mean_zh": {"calm": "利率市场平静", "normal": "利率市场平稳", "elevated": "利率波动加剧",
                          "crisis": "利率市场承压"}.get(sb, "利率波动"),
              "sev": _sev(good=sb in ("calm", "normal"), warn=sb == "elevated", bad=sb == "crisis")})

    f_bad, f_warn = st.get("repo_stress"), st.get("reserve_scarcity")
    g.append({"name_en": "Funding", "name_zh": "资金面", "href": "#stress",
              "state_en": ("Stressed" if f_bad else ("Tightening" if f_warn else "Ample")),
              "state_zh": ("承压" if f_bad else ("趋紧" if f_warn else "充裕")),
              "mean_en": ("funding plumbing strained" if f_bad else ("reserves thinning" if f_warn else "cash plentiful")),
              "mean_zh": ("资金管道紧张" if f_bad else ("准备金趋紧" if f_warn else "现金充裕")),
              "sev": _sev(good=not (f_bad or f_warn), warn=f_warn, bad=f_bad)})

    corr = cx.get("corr")
    h_good = corr is not None and corr < -0.1
    h_bad = corr is not None and corr > 0.2
    g.append({"name_en": "Stock-bond hedge", "name_zh": "股债对冲", "href": "#stress",
              "state_en": ("Working" if h_good else ("Failing" if h_bad else "Patchy")),
              "state_zh": ("有效" if h_good else ("失效" if h_bad else "不稳")),
              "mean_en": ("bonds cushion stocks" if h_good else ("bonds not hedging" if h_bad else "hedge unreliable")),
              "mean_zh": ("债券对冲股票" if h_good else ("债券不对冲" if h_bad else "对冲不可靠")),
              "sev": _sev(good=h_good, bad=h_bad)})
    return g


def _key_levels(f: pd.DataFrame, vm: dict) -> list[dict]:
    """The numbers people come for — one compact strip. Each = label · value · 3-month move."""
    def last(col):
        try:
            s = f[col].dropna()
            return (float(s.iloc[-1]), (float(s.iloc[-1]) - float(s.iloc[-64])) if len(s) > 64 else None)
        except Exception:  # noqa: BLE001
            return (None, None)

    def tile(lab_en, lab_zh, col, unit="%", bp=False):
        v, chg = last(col)
        if v is None:
            return {"lab_en": lab_en, "lab_zh": lab_zh, "val": "—", "unit": "", "sub": ""}
        sub = ""
        if chg is not None:
            sub = (f"{chg * 100:+.0f}bp/3m" if bp else f"{chg:+.2f}/3m")
        return {"lab_en": lab_en, "lab_zh": lab_zh, "val": f"{v:,.2f}", "unit": unit, "sub": sub}

    rows = [
        tile("10-year", "10年期", "us10y", bp=True),
        tile("2-year", "2年期", "us2y", bp=True),
        tile("30-year", "30年期", "us30y", bp=True),
        tile("Real 10y", "10年实际", "us10y_real", bp=True),
        tile("10y breakeven", "10年盈亏平衡", "breakeven_10y", bp=True),
        tile("High-yield spread", "高收益利差", "hy_oas", bp=True),
    ]
    mv, mchg = last("move")
    rows.append({"lab_en": "MOVE (rates vol)", "lab_zh": "MOVE 利率波动", "unit": "",
                 "val": (f"{mv:,.0f}" if mv is not None else "—"),
                 "sub": (f"{mchg:+.0f}/3m" if mchg is not None else "")})
    return rows


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    from engine import inputs, bonds, bonds_alerts
    try:
        f = inputs.build_features()
        fr = bonds.bonds_frame(f)
        if fr.empty or "health_score" not in fr.columns:
            log.error("no bond-health frame; skipping bonds page")
            return 0
        snap = bonds.bonds_snapshot(f, fr)
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("bonds engine failed (%s); skipping bonds page", e)
        return 0

    calib = _load_calibration()
    vm = _vm(snap, fr, calib)

    # Fed policy path (display-only, research/DATA_SIGNAL_EXPANSION_2026.md #2): the
    # market-implied path (ZQ/SR3 futures) vs the FOMC dot-plot. Additive leaf —
    # never scored, never an MRS leg. None when the feeds are absent.
    fed_path = None
    try:
        from engine import fed_path as _fp
        fed_path = _fp.snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("fed-path snapshot failed: %s", e)

    _CHART_KEYS = ("health", "curve_now", "spreads", "credit", "real", "move", "corr",
                   "sovereign", "policy_path")
    try:
        charts = {
            "health": chart_health(fr), "curve_now": chart_curve_now(f), "spreads": chart_spreads(fr),
            "credit": chart_credit(fr), "real": chart_real(fr), "move": chart_move(fr), "corr": chart_corr(fr),
            "sovereign": chart_sovereign(fr),
            "policy_path": chart_policy_path(fed_path) if fed_path else "",
        }
    except Exception as e:  # noqa: BLE001 — a single chart must never break the page
        log.warning("bonds chart build failed (%s); rendering without charts", e)
        charts = {k: "" for k in _CHART_KEYS}

    # alert timeline (deterministic, recomputed each build)
    # Fix 6: use rebuild_with_credit(fr) so CCW credit_market_turn + credit_theme_stress
    # events are included. Falls back to rebuild(fr) behavior when credit_momentum.json
    # is absent (rebuild_with_credit is null-safe — compute_credit_events returns [] on
    # missing file per bonds_alerts.py implementation).
    acfg = config.load()["bonds"]["alerts"]
    try:
        events = bonds_alerts.rebuild_with_credit(fr)
    except Exception as e:  # noqa: BLE001 — timeline is optional, never break the page
        log.warning("bonds alerts rebuild_with_credit failed (%s); falling back to rebuild", e)
        try:
            events = bonds_alerts.rebuild(fr)
        except Exception as e2:  # noqa: BLE001
            log.warning("bonds alerts rebuild also failed (%s)", e2)
            events = bonds_alerts.load_events()
    recent = bonds_alerts.recent(events, acfg["timeline_days"])
    timeline = _group_timeline(recent)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    last_valid = fr.dropna(how="all").index.max()
    as_of = snap.get("as_of") or (last_valid.strftime("%Y-%m-%d") if pd.notna(last_valid) else built[:10])
    as_of_disp = pd.Timestamp(as_of).strftime("%b %d, %Y")
    lo, hi = fr.index.min(), fr.index.max()
    span = f"{lo.date()}..{hi.date()}" if pd.notna(lo) and pd.notna(hi) else "—"

    # global credit cycle (BIS credit-gap + DSR; additive leaf, None if data absent)
    credit_cycle = None
    try:
        from engine import credit_cycle as _cc
        credit_cycle = _cc.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("credit-cycle snapshot failed: %s", e)

    # Treasury supply absorption (TreasuryDirect auction results; additive leaf, display-
    # only — per-tenor demand z-scores + duration-supply trend). None if data absent.
    # NEVER scored, never an MRS leg.
    treasury_supply = None
    try:
        from engine import treasury_supply as _ts
        treasury_supply = _ts.snapshot()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("treasury-supply snapshot failed: %s", e)

    # NEW world-class layers (additive, display-only leaves; never scored, never MRS):
    #   intl_bonds       — Global Sovereign Bond Scorecard (G10 + EM + global yield tide)
    #   bond_compass     — directional Duration & Curve Compass (factor blend)
    #   bond_cross_asset — quantitative Bonds→Everything transmission (measured betas)
    intl, compass, xasset = None, None, None
    try:
        from engine import intl_bonds as _ib
        intl = _ib.snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("intl-bonds snapshot failed: %s", e)
    try:
        from engine import bond_compass as _bc
        compass = _bc.snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("bond-compass snapshot failed: %s", e)
    try:
        from engine import bond_cross_asset as _bx
        xasset = _bx.snapshot(f)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("bond-cross-asset snapshot failed: %s", e)

    # extra charts for the new sections (each guarded — a chart must never break the page)
    for key, fn in (("intl_yields", lambda: chart_intl_yields(f)),
                    ("tp_decomp", lambda: chart_tp_decomp(f)),
                    ("xasset_betas", lambda: chart_xasset_betas(xasset))):
        try:
            charts[key] = fn()
        except Exception as e:  # noqa: BLE001
            log.warning("bonds chart %s failed (%s)", key, e)
            charts[key] = ""

    # the 10y Treasury's contemporaneous correlation TO the dollar (the forex Dollar
    # Desk's view; complements this page's bonds→dollar leg). Display-only; None if absent.
    # B3: enrich usd_link with usd_dir + real-rate regime clause + per-asset effect/stability.
    try:
        from lib import forex_link
        # F5: keep usd_link=None when asset_corr returns None; only enrich a non-None dict.
        # Setting usd_link={} when corr is absent makes it truthy, so bonds.html.j2:257
        # ({% if usd_link %} then usd_link.corr<0) hits Jinja Undefined and crashes the render.
        usd_link = forex_link.asset_corr("UST10")
        if usd_link is not None:
            # B3 n1: usd_dir holds the DIRECTION WORD from transmission.usd_dir
            # ("strengthening"/"weakening"), not the stance sentence (which was wrong here).
            # The stance sentence goes into stance_sentence_en/zh.
            _tx_b = forex_link.transmission()
            usd_link["usd_dir"] = (_tx_b.get("usd_dir") or None) if _tx_b else None
            _stance = forex_link.stance()
            usd_link["stance_sentence_en"] = _stance.get("sentence_en") or None if _stance else None
            usd_link["stance_sentence_zh"] = _stance.get("sentence_zh") or None if _stance else None
            # B3: real-rate regime (directly relevant to bonds; headwind/tailwind context)
            try:
                import json as _bj
                from lib import config as _bcfg
                _dd = (_bj.loads((_bcfg.data_dir() / "forex" / "latest.json").read_text()).get("dollar_desk") or {})
                usd_link["real_rate_regime"] = _dd.get("real_rate_regime") or None
            except Exception:  # noqa: BLE001
                usd_link["real_rate_regime"] = None
            # B3: per-asset effect/stability from transmission.assets
            _ta = forex_link.transmission_asset("UST10")
            if _ta:
                usd_link["effect"] = _ta.get("effect")
                usd_link["stability"] = _ta.get("stability")
    except Exception:  # noqa: BLE001 — additive, never fatal
        usd_link = None

    # CCW-W4: corporate credit desk vm (null-safe — never breaks the build)
    # m5 fix: removed the dead __wrapped__ hasattr-always-False fallback; build_corp_credit_vm
    # is never decorated, so __wrapped__ never existed.  The function itself is null-safe
    # (returns the empty accruing dict on any error), so we just call it directly.
    try:
        cc_vm = build_corp_credit_vm()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("corp_credit vm build failed (%s); using empty accruing state", e)
        cc_vm = build_corp_credit_vm(data_root=None)

    from engine.i18n import tr, td
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    env.globals.update(tr=tr, td=td)
    html = env.get_template("bonds.html.j2").render(
        C=C, as_of=as_of_disp, built=built, span=span, vm=vm, charts=charts, credit_cycle=credit_cycle,
        fed_path=fed_path, treasury_supply=treasury_supply, usd_link=usd_link,
        intl=intl, compass=compass, xasset=xasset, xasset_vm=_xasset_vm(xasset),
        timeline=timeline, timeline_days=acfg["timeline_days"], n_alerts=len(recent),
        cc_vm=cc_vm, glance=_glance(vm), key_levels=_key_levels(f, vm))
    site = config.ROOT / config.load()["storage"]["site_dir"]
    write_page(site / "bonds.html", html)
    log.info("wrote %s/bonds.html (%d KB)", site, len(html) // 1024)

    # hub latest.json (consumed by build_vector's hub card) + the AI signal contract
    outdir = config.data_dir() / "bonds"
    outdir.mkdir(parents=True, exist_ok=True)
    latest = {"date": as_of, "health_score": snap.get("health_score"),
              "health_label": snap.get("health_label"), "cycle_phase": snap.get("cycle_phase"),
              "verdict_en": snap.get("verdict_en"), "verdict_zh": snap.get("verdict_zh")}
    (outdir / "latest.json").write_text(json.dumps(latest, indent=2, default=str, ensure_ascii=False))
    if fed_path is not None:
        snap["fed_path"] = fed_path  # deterministic LLM context on the bonds AI contract
    # ADDITIVE contract extensions for the cross-asset brain (existing keys untouched):
    if intl is not None:
        snap["intl_bonds"] = intl              # global sovereign scorecard + US-vs-world premium
    if compass is not None:
        snap["bond_compass"] = compass         # directional duration / curve lean (display-only)
    if xasset is not None:
        snap["bond_cross_asset"] = xasset      # measured bond→asset transmission betas

    # IRD-W2: additive `intl` namespace — fail-open; existing keys untouched when absent
    try:
        import json as _json
        from pathlib import Path as _Path
        _intl_risk_path = config.data_dir() / "intl_risk" / "latest.json"
        _intl_risk = None
        if _intl_risk_path.exists():
            _intl_risk = _json.loads(_intl_risk_path.read_text(encoding="utf-8"))
        _em_oas_ladder: dict | None = None
        try:
            from engine.intl_risk import em_stress as _em_stress_for_bonds
            _ems = _em_stress_for_bonds()
            # EM OAS ladder: extract per-series vel from the legs payload
            _em_oas_ladder = {
                k: {
                    "value": v.get("value"),
                    "vel_5d_z": v.get("vel_5d_z"),
                    "vel_20d_z": v.get("vel_20d_z"),
                    "asof": v.get("asof"),
                }
                for k, v in (_ems.get("legs") or {}).items()
                if isinstance(v, dict)
            }
        except Exception:  # noqa: BLE001
            pass

        _inversion_summary: dict | None = None
        try:
            from engine.intl_bonds import inversion_board as _inv_board
            _ib = _inv_board()
            _inversion_summary = {
                "n_inverted": _ib.get("n_inverted"),
                "n_total": _ib.get("n_total"),
                "synchronized": _ib.get("synchronized"),
            }
        except Exception:  # noqa: BLE001
            pass

        _swap_lines_bn: float | None = None
        try:
            from lib import store as _bond_store
            _swpt = _bond_store.read("fred", "SWPT")
            if _swpt is not None and not _swpt.empty:
                _swap_lines_bn = round(float(_swpt.iloc[:, 0].dropna().iloc[-1]) / 1000.0, 1)
        except Exception:  # noqa: BLE001
            pass

        snap["intl"] = {
            "em_oas_ladder": _em_oas_ladder,
            "inversion_board": _inversion_summary,
            "swap_lines_bn": _swap_lines_bn,
            "em_stress_state": (_intl_risk or {}).get("em_stress", {}).get("state") if _intl_risk else None,
            "display_only": True,
        }
    except Exception as _intl_err:  # noqa: BLE001 — additive, never fatal
        log.error("bond_health intl namespace failed (%s)", _intl_err)

    # CCW-W4: add corporate_credit block to bond_health.json (additive, machine-readable)
    try:
        snap["corporate_credit"] = _build_corp_credit_bond_health(cc_vm)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("corp_credit bond_health block failed (%s)", e)

    (outdir / "bond_health.json").write_text(json.dumps(snap, indent=2, default=str, ensure_ascii=False))
    log.info("wrote data/bonds/{latest,bond_health}.json — health=%s phase=%s",
             snap.get("health_score"), snap.get("cycle_phase"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
