"""Global Sovereign Bond Scorecard — the international-bonds layer.

ADDITIVE / leaf module: imports nothing from the scoring core and nothing in the
scoring path imports it. Bonds is the largest asset class on earth, and yet the
dashboard read it US-first; this module widens the lens to the G10 sovereign
complex and the global yield "tide" that drives FX, global financial conditions
and cross-border duration flows.

For each major sovereign it computes, from free/official data already in the store:

  • 10y nominal yield LEVEL (the price of money)
  • curve SLOPE (10y − 2y where a 2y exists, else 10y − 3m interbank)
  • 63-business-day MOMENTUM of the 10y (Δbp) → rising / falling / stable
  • 1y and 5y rich/cheap z-score of the 10y vs its own history
  • the rate DIFFERENTIAL vs the US 10y (bp) — the FX carry/value anchor
  • a real yield where a clean linker exists (US TIPS today; others note "n/a")

…then aggregates a GDP-weighted GLOBAL 10y level + momentum ("is the global cost
of capital rising or falling?"), folds in EM hard-currency spreads (ICE BofA EM
OAS + the EMB ETF trend) and euro-area fragmentation, and hands the US-vs-world
rate differential to the FX board.

Cadence honesty: US / euro-area / Japan are DAILY (FRED, ECB, Japan MoF); the
UK / Canada / Australia / Switzerland legs are the OECD monthly long-rate series
(IRLTLT01…) and lag ~1 month — each row carries its `cadence` + `stale` flags so
the UI never implies a daily print it does not have. DISPLAY-ONLY context, never
scored, never an MRS leg.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.ird_velocity import velocity_fields_bp as _ird_velocity
from lib import store

log = logging.getLogger(__name__)

_TY = 252  # business days / yr

# --- the sovereign roster -----------------------------------------------------
# code -> spec. `gdp_w` = rough nominal-GDP weight (normalized over AVAILABLE legs)
# for the global aggregate. `src` tells the loader where each leg lives.
ROSTER: list[dict] = [
    {"code": "US", "en": "United States", "zh": "美国", "ccy": "USD", "gdp_w": 0.42,
     "cadence": "daily", "src": "frame",
     "y10": "us10y", "y2": "us2y", "short": "us3m", "real": "us10y_real"},
    {"code": "DE", "en": "Euro area (Bund)", "zh": "欧元区（德债）", "ccy": "EUR", "gdp_w": 0.22,
     "cadence": "daily", "src": "ecb",
     "y10": "ez_aaa_10y", "y2": "ez_aaa_2y", "short": None, "real": None},
    {"code": "JP", "en": "Japan", "zh": "日本", "ccy": "JPY", "gdp_w": 0.10,
     "cadence": "daily", "src": "jgb",
     "y10": "jgb_10y", "y2": "jgb_2y", "short": None, "real": None},
    {"code": "GB", "en": "United Kingdom", "zh": "英国", "ccy": "GBP", "gdp_w": 0.07,
     "cadence": "monthly", "src": "fred",
     "y10": "IRLTLT01GBM156N", "y2": None, "short": "IR3TIB01GBM156N", "real": None},
    {"code": "CA", "en": "Canada", "zh": "加拿大", "ccy": "CAD", "gdp_w": 0.06,
     "cadence": "monthly", "src": "fred",
     "y10": "IRLTLT01CAM156N", "y2": None, "short": "IR3TIB01CAM156N", "real": None},
    {"code": "AU", "en": "Australia", "zh": "澳大利亚", "ccy": "AUD", "gdp_w": 0.05,
     "cadence": "monthly", "src": "fred",
     "y10": "IRLTLT01AUM156N", "y2": None, "short": "IR3TIB01AUM156N", "real": None},
    {"code": "CH", "en": "Switzerland", "zh": "瑞士", "ccy": "CHF", "gdp_w": 0.03,
     "cadence": "monthly", "src": "fred",
     "y10": "IRLTLT01CHM156N", "y2": None, "short": None, "real": None},
]

# slope-state knots (pp); direction knot (bp over 63 bdays); stale tolerance (days)
SLOPE_INVERTED, SLOPE_FLAT, SLOPE_STEEP = 0.0, 0.25, 1.0
DIR_BP = 10.0
STALE_DAYS = {"daily": 12, "monthly": 75}


# --- small causal helpers -----------------------------------------------------
def _series(spec: dict, key_field: str, f: pd.DataFrame) -> pd.Series | None:
    """Load one leg as a clean float Series, from the frame or the parquet store."""
    key = spec.get(key_field)
    if not key:
        return None
    src = spec["src"]
    if src == "frame":
        if key in f.columns and not f[key].isna().all():
            return f[key].dropna()
        return None
    grp = {"ecb": "sovereign", "jgb": "sovereign", "fred": "fred"}[src]
    df = store.read(grp, key)
    if df is None or df.empty:
        return None
    return df.iloc[:, 0].astype(float).dropna()


def _align(s: pd.Series | None, idx: pd.DatetimeIndex, limit: int = 40) -> pd.Series | None:
    """Carry a (possibly monthly) series onto the business-day index so a 63-bday
    change is a uniform ~3-month read across daily and monthly legs alike."""
    if s is None or s.empty:
        return None
    return s.reindex(idx.union(s.index)).ffill(limit=limit).reindex(idx)


def _chg_bp(s: pd.Series, n: int = 63) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    v = (s.iloc[-1] - s.iloc[-1 - n]) * 100.0
    return float(v) if np.isfinite(v) else None


def _z(s: pd.Series, window: int) -> float | None:
    s = s.dropna()
    if len(s) < max(60, window // 4):
        return None
    w = s.iloc[-window:]
    sd = w.std()
    if not sd or not np.isfinite(sd):
        return None
    return float((s.iloc[-1] - w.mean()) / sd)


def _slope_state(slope: float | None) -> str | None:
    if slope is None:
        return None
    if slope < SLOPE_INVERTED:
        return "inverted"
    if slope < SLOPE_FLAT:
        return "flat"
    if slope < SLOPE_STEEP:
        return "normal"
    return "steep"


def _direction(chg_bp: float | None) -> str | None:
    if chg_bp is None:
        return None
    return "rising" if chg_bp > DIR_BP else ("falling" if chg_bp < -DIR_BP else "stable")


def _r(v, nd: int = 2):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


# --- per-country row ----------------------------------------------------------
def _country_row(spec: dict, f: pd.DataFrame, us_y10_last: float | None) -> dict | None:
    idx = f.index
    y10 = _align(_series(spec, "y10", f), idx)
    if y10 is None or y10.dropna().empty:
        return None
    y2 = _align(_series(spec, "y2", f), idx)
    short = _align(_series(spec, "short", f), idx)
    real = _align(_series(spec, "real", f), idx)

    lvl = float(y10.dropna().iloc[-1])
    last_ts = y10.dropna().index[-1]
    age = (idx[-1] - last_ts).days
    stale = age > STALE_DAYS.get(spec["cadence"], 30)

    # slope: prefer 10y-2y, else 10y-short(3m). carry the label so the UI is honest.
    slope, slope_basis = None, None
    if y2 is not None and not y2.dropna().empty:
        slope, slope_basis = lvl - float(y2.dropna().iloc[-1]), "2s10s"
    elif short is not None and not short.dropna().empty:
        slope, slope_basis = lvl - float(short.dropna().iloc[-1]), "10y-3m"

    chg = _chg_bp(y10)
    diff = (lvl - us_y10_last) * 100.0 if us_y10_last is not None else None
    # IRD-R13 velocity fields (shared ird_velocity grammar)
    vel = _ird_velocity(y10.dropna())
    return {
        "code": spec["code"], "en": spec["en"], "zh": spec["zh"], "ccy": spec["ccy"],
        "cadence": spec["cadence"], "stale": stale, "gdp_w": spec["gdp_w"],
        "y10": _r(lvl), "y2": _r(float(y2.dropna().iloc[-1])) if y2 is not None and not y2.dropna().empty else None,
        "slope": _r(slope), "slope_basis": slope_basis, "slope_state": _slope_state(slope),
        "chg_63d_bp": _r(chg, 0), "direction": _direction(chg),
        "z1y": _r(_z(y10, _TY), 2), "z5y": _r(_z(y10, _TY * 5), 2),
        "diff_vs_us_bp": _r(diff, 0),
        "real_10y": _r(float(real.dropna().iloc[-1])) if real is not None and not real.dropna().empty else None,
        # IRD-R13 velocity (basis-point changes of 10y level; window_days disclosed)
        "vel_5d_bp": vel["vel_5d_bp"],
        "vel_20d_bp": vel["vel_20d_bp"],
        "vel_20d_z": vel["vel_20d_z"],
        "vel_window_days": vel["window_days"],
        "_y10_lvl": lvl,
    }


# --- EM leg -------------------------------------------------------------------
def _em(f: pd.DataFrame) -> dict | None:
    oas = store.read("fred", "BAMLEMCBPIOAS")
    emb = store.read("yahoo", "EMB")
    if (oas is None or oas.empty) and (emb is None or emb.empty):
        return None
    out: dict = {}
    if oas is not None and not oas.empty:
        s = oas.iloc[:, 0].astype(float).dropna()
        out["em_oas"] = _r(float(s.iloc[-1]))
        w = s.iloc[-_TY * 5:]
        out["pctile"] = _r(float((w <= s.iloc[-1]).mean() * 100.0), 0)
        out["direction"] = _direction(_chg_bp(_align(s, f.index)))
    if emb is not None and not emb.empty and "close" in emb.columns:
        c = emb["close"].astype(float).dropna()
        if len(c) > 200:
            ma = c.rolling(200).mean()
            out["emb_trend"] = "up" if c.iloc[-1] > ma.iloc[-1] else "down"
            out["emb_chg_63d_pct"] = _r((c.iloc[-1] / c.iloc[-64] - 1.0) * 100.0, 1) if len(c) > 64 else None
    return out or None


# --- snapshot -----------------------------------------------------------------
def snapshot(f: pd.DataFrame) -> dict | None:
    """The Global Sovereign Bond Scorecard. `f` = engine.inputs.build_features()."""
    if f is None or f.empty:
        return None
    us = next((s for s in ROSTER if s["code"] == "US"), None)
    us_s = _align(_series(us, "y10", f), f.index) if us else None
    us_y10 = float(us_s.dropna().iloc[-1]) if us_s is not None and not us_s.dropna().empty else None

    rows = [r for r in (_country_row(s, f, us_y10) for s in ROSTER) if r is not None]
    if not rows:
        return None

    # GDP-weighted global aggregate over AVAILABLE legs (the global cost of capital)
    tot_w = sum(r["gdp_w"] for r in rows)
    avg_10y = sum(r["_y10_lvl"] * r["gdp_w"] for r in rows) / tot_w if tot_w else None
    chgs = [(r["chg_63d_bp"], r["gdp_w"]) for r in rows if r["chg_63d_bp"] is not None]
    avg_chg = (sum(c * w for c, w in chgs) / sum(w for _, w in chgs)) if chgs else None
    slopes = [r["slope"] for r in rows if r["slope"] is not None]
    avg_slope = float(np.mean(slopes)) if slopes else None
    g_dir = _direction(avg_chg)
    glob = {
        "avg_10y": _r(avg_10y), "avg_10y_chg_63d_bp": _r(avg_chg, 0),
        "direction": g_dir, "avg_slope": _r(avg_slope), "n": len(rows),
        "regime": (None if g_dir is None else
                   ("global yields rising" if g_dir == "rising" else
                    ("global yields falling" if g_dir == "falling" else "global yields stable"))),
    }

    # US vs the rest of the world (ex-US GDP-weighted) — the FX value/carry anchor
    exus = [r for r in rows if r["code"] != "US"]
    exus_w = sum(r["gdp_w"] for r in exus)
    exus_10y = (sum(r["_y10_lvl"] * r["gdp_w"] for r in exus) / exus_w) if exus_w else None
    us_premium_bp = (us_y10 - exus_10y) * 100.0 if (us_y10 is not None and exus_10y is not None) else None
    us_premium_dir = None
    if us_s is not None and exus:
        exus_avg = None
        parts = []
        for r in exus:
            s = _align(_series(next(x for x in ROSTER if x["code"] == r["code"]), "y10", f), f.index)
            if s is not None:
                parts.append((s, r["gdp_w"]))
        if parts and us_s is not None:
            num = sum(s * w for s, w in parts)
            den = sum(w for _, w in parts)
            exus_avg = num / den
            diff_series = (us_s - exus_avg).dropna()
            us_premium_dir = _direction(_chg_bp(diff_series))

    em = _em(f)

    # rank for the table: most ominous (deepest inversion) / highest-yield first is
    # not a "best" ordering — keep the canonical roster order, UI can re-sort.
    rows_clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]

    snap = {
        "as_of": str(f.index[-1].date()),
        "global": glob,
        "us_vs_world": {
            "us_10y": _r(us_y10), "exus_10y": _r(exus_10y),
            "us_premium_bp": _r(us_premium_bp, 0), "premium_direction": us_premium_dir,
        },
        "countries": rows_clean,
        "em": em,
    }
    snap["verdict_en"], snap["verdict_zh"] = _verdict(snap)
    snap["drivers_for"] = _drivers_for(snap)
    return snap


def history(f: pd.DataFrame) -> dict[str, pd.Series]:
    """{code: business-day-aligned 10y yield series} for the majors — for the chart."""
    out: dict[str, pd.Series] = {}
    for spec in ROSTER:
        s = _align(_series(spec, "y10", f), f.index)
        if s is not None and not s.dropna().empty:
            out[spec["code"]] = s
    return out


def _verdict(s: dict) -> tuple[str, str]:
    g = s["global"]
    uw = s["us_vs_world"]
    en, zh = [], []
    if g.get("regime"):
        reg = g["regime"]
        en.append(f"Global 10y avg {g['avg_10y']}% and {reg.replace('global yields ', '')} "
                  f"({g['avg_10y_chg_63d_bp']:+.0f}bp/3m) — "
                  + ("a global tightening/duration-bear impulse." if g['direction'] == 'rising'
                     else "an easing/duration-bull impulse." if g['direction'] == 'falling'
                     else "a stable global cost of capital."))
        zh.append(f"全球10年期均值 {g['avg_10y']}%，3个月 {g['avg_10y_chg_63d_bp']:+.0f}基点 — "
                  + ("全球收紧/久期偏空动能。" if g['direction'] == 'rising'
                     else "宽松/久期偏多动能。" if g['direction'] == 'falling' else "全球资金成本平稳。"))
    if uw.get("us_premium_bp") is not None:
        above = uw["us_premium_bp"] >= 0
        en.append(f"US 10y is {abs(uw['us_premium_bp']):.0f}bp {'above' if above else 'below'} the "
                  f"GDP-weighted rest of the world"
                  + (f" and {uw['premium_direction']}" if uw.get('premium_direction') else "")
                  + " — the dollar's rate-differential anchor.")
        zh.append(f"美国10年期较GDP加权的世界其余{'高' if above else '低'}{abs(uw['us_premium_bp']):.0f}基点"
                  + (f"，利差{ {'rising':'走阔','falling':'收窄','stable':'平稳'}.get(uw.get('premium_direction'),'') }" if uw.get('premium_direction') else "")
                  + " — 美元的利差之锚。")
    if s.get("em") and s["em"].get("em_oas") is not None:
        en.append(f"EM hard-currency OAS {s['em']['em_oas']}% ({s['em'].get('direction','')}).")
        zh.append(f"新兴市场硬通货利差 {s['em']['em_oas']}%（{ {'rising':'走阔','falling':'收窄','stable':'平稳'}.get(s['em'].get('direction'),'') }）。")
    return " ".join(en), "".join(zh)


def _drivers_for(s: dict) -> dict:
    """Hand-off to the FX board: the rate-differential read that anchors the dollar."""
    uw = s["us_vs_world"]
    return {
        "forex": {
            "us_premium_bp": uw.get("us_premium_bp"),
            "premium_direction": uw.get("premium_direction"),
            "note_en": "A widening US-vs-world 10y premium is a USD tailwind (rate-differential / "
                       "carry channel); a narrowing premium pressures the dollar.",
        },
    }


def _load_series_standalone(spec: dict, key_field: str) -> pd.Series | None:
    """Load a sovereign series without a pre-built frame (for inversion_board standalone calls).

    For 'frame'-sourced series (US), loads from FRED directly (DGS10/DGS2).
    For all other sources, uses the same store.read path as _series().
    """
    key = spec.get(key_field)
    if not key:
        return None
    src = spec["src"]
    if src == "frame":
        # US: map column aliases to FRED series ids
        _frame_to_fred = {
            "us10y": "DGS10", "us2y": "DGS2", "us3m": "DGS3MO",
            "us10y_real": "DFII10",
        }
        fred_id = _frame_to_fred.get(key)
        if not fred_id:
            return None
        df = store.read("fred", fred_id)
        if df is None or df.empty:
            return None
        return df.iloc[:, 0].astype(float).dropna()
    grp = {"ecb": "sovereign", "jgb": "sovereign", "fred": "fred"}[src]
    df = store.read(grp, key)
    if df is None or df.empty:
        return None
    return df.iloc[:, 0].astype(float).dropna()


def inversion_board() -> dict:
    """Curve inversion board for ROSTER sovereigns (IRD-R13 / W2 task).

    For each ROSTER country with sufficient data computes the 10y-2y (or 10y-3m) slope.
    Returns:
      n_inverted    : int — number of sovereigns with inverted yield curves
      n_total       : int — total sovereigns with data
      countries     : list[{cc, slope_bp, inverted, since_days}]
      synchronized  : bool — True if >=half of n_total are inverted
      built         : ISO timestamp
    """
    from datetime import datetime, timezone

    rows: list[dict] = []
    for spec in ROSTER:
        try:
            y10 = _load_series_standalone(spec, "y10")
            if y10 is None or y10.dropna().empty:
                continue
            y2 = _load_series_standalone(spec, "y2")
            short = _load_series_standalone(spec, "short")

            # Prefer 10y-2y; fall back to 10y-3m
            long_last = float(y10.dropna().iloc[-1])
            slope_bp: float | None = None
            if y2 is not None and not y2.dropna().empty:
                slope_bp = (long_last - float(y2.dropna().iloc[-1])) * 100.0
            elif short is not None and not short.dropna().empty:
                slope_bp = (long_last - float(short.dropna().iloc[-1])) * 100.0

            if slope_bp is None:
                continue

            inverted = slope_bp < 0.0

            # since_days: how many consecutive calendar days the curve has been inverted
            since_days: int | None = None
            if inverted:
                # build daily slope series to count consecutive inverted days
                # use same approach: only available if both legs present
                if y2 is not None and not y2.dropna().empty:
                    # align y2 onto y10 index (forward-fill up to 40d for monthly series)
                    y10_s = y10.dropna()
                    y2_s = y2.dropna()
                    aligned_idx = y10_s.index.union(y2_s.index).sort_values()
                    y10_a = y10_s.reindex(aligned_idx).ffill(limit=40).reindex(y10_s.index)
                    y2_a = y2_s.reindex(y10_s.index).ffill(limit=40)
                    slope_series = ((y10_a - y2_a) * 100.0).dropna()
                    if not slope_series.empty:
                        inverted_mask = slope_series < 0.0
                        # Count from the end while True
                        count = 0
                        for v in reversed(inverted_mask.values):
                            if v:
                                count += 1
                            else:
                                break
                        since_days = count

            rows.append({
                "cc": spec["code"],
                "slope_bp": round(slope_bp, 1),
                "inverted": inverted,
                "since_days": since_days,
            })
        except Exception:  # noqa: BLE001 — fail-open per country
            continue

    n_inverted = sum(1 for r in rows if r["inverted"])
    n_total = len(rows)
    synchronized = (n_inverted >= (n_total / 2)) if n_total > 0 else False

    return {
        "n_inverted": n_inverted,
        "n_total": n_total,
        "countries": rows,
        "synchronized": bool(synchronized),
        "built": datetime.now(timezone.utc).isoformat(),
    }
