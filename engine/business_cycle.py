"""Conference-Board-style business-cycle model: Leading / Coincident / Lagging.

This module is ADDITIVE. It runs alongside engine/conditions.py and the split-half-
validated growth/inflation quad (engine/regime.py) and never alters them. Where the
conditions `recession_risk` score BLENDS leading (curve, credit) and concurrent
(Sahm) signals into one number, this module keeps the three tiers SEPARATE so the
lead-lag SEQUENCE is readable — the thing that actually anticipates a turn:

    Leading rolls over  ->  (months later) Coincident peaks  ->  Lagging confirms last

Construction (Conference-Board method, adapted to the repo's causal idioms):
  • Each component's month-to-month change is standardized by its own causal rolling
    volatility (the CB "standardization factor" = 1/std, so no single noisy series
    dominates). Counter-cyclical legs (jobless claims, unemployment duration,
    inventory/sales, credit spread) are sign-flipped so every tier is pro-cyclical.
  • The standardized contributions are averaged over the AVAILABLE legs per month
    (a missing/short leg drops out of the mean — same renorm discipline as
    conditions.py) and cumulated into a tier index, rebased to 100.
  • Red line  = the index's 6-month momentum (CB "6-month change").
    Blue line  = an EMA trend of that momentum.
    Diffusion  = share of legs rising over 6 months (CB breadth, 0..100).

Recession signal = the CB "3 D's": Depth + Duration (leading 6-month momentum below
a threshold) AND Diffusion (<= 50, broad weakening), held for N months to cut
whipsaws. The threshold is in THIS index's own units and is CALIBRATED against NBER
dates by scripts/validate_business_cycle.py — NOT borrowed from CB's published -4.3%
(a different index's scaling). The measured lead time and false-positive count are
shipped WITH the signal (loaded from the calibration JSON), never implied.

HONESTY: there are only ~7 modern US recessions (≈3 inside FRED's 1997+ point-in-time
vintage window), so the effective sample is tiny and any tuned rule is overfit-prone.
This is a recession-RISK timeline, not a crash oracle. See
research/BUSINESS_CYCLE_MODEL.md and reports/business-cycle-validation.md.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# Component spec per tier: (store_group, store_name, column, sign).
# sign +1 = pro-cyclical (rises in expansion); -1 = counter-cyclical, flipped so the
# tier index rises in expansion. SPY/spread/HY-OAS/UMich/PAYEMS/INDPRO are REUSED
# from series the repo already collects; the rest were added for this model.
LEADING = [
    ("fred", "AWHMAN", "mfg_hours", +1),          # avg weekly hours, manufacturing
    ("fred", "ICSA", "initial_claims", -1),        # initial jobless claims (invert)
    ("fred", "PERMIT", "building_permits", +1),    # housing units authorized
    ("fred", "NEWORDER", "cap_goods_orders", +1),  # nondefense cap-goods orders ex-air
    ("yahoo", "SPY", "close", +1),                 # equities (S&P 500 proxy)
    ("fred", "BAMLH0A0HYM2", "hy_oas", -1),        # HY credit spread (invert) ~ leading credit
    ("fred", "T10Y3M", "spread_10y3m", +1),        # yield-curve slope (the NY-Fed spread)
    ("fred", "UMCSENT", "umich_sentiment", +1),    # consumer expectations proxy
]
COINCIDENT = [
    ("fred", "PAYEMS", "payrolls", +1),
    ("fred", "W875RX1", "real_income_ex_transfer", +1),
    ("fred", "CMRMTSPL", "mfg_trade_sales", +1),
    ("fred", "INDPRO", "industrial_prod", +1),
]
LAGGING = [
    ("fred", "UEMPMEAN", "unemp_duration", -1),    # avg unemployment duration (invert)
    ("fred", "ISRATIO", "inventory_sales", -1),    # inventories/sales (invert)
    ("fred", "BUSLOANS", "ci_loans", +1),          # commercial & industrial loans
    ("fred", "MPRIME", "prime_rate", +1),          # bank prime rate
    ("fred", "CUSR0000SAS", "cpi_services", +1),   # CPI services
]
TIERS = {"leading": LEADING, "coincident": COINCIDENT, "lagging": LAGGING}

_CAL_PATH = lambda: config.data_dir() / "regime" / "business_cycle_calibration.json"


# --- component → monthly series ----------------------------------------------
def _component_monthly(group: str, name: str, column: str, lag_m: int = 0) -> pd.Series | None:
    """One component as a month-end series. Daily/weekly inputs (equities, claims,
    spreads) collapse to the monthly MEAN (the CB convention for the S&P 500 leg);
    natively-monthly inputs take the month's value.

    `lag_m` shifts natively-MONTHLY series forward by N months — the publication lag
    a point-in-time backtest needs (May payrolls aren't knowable in May). It is 0 on
    the live path (the store already holds only released data) and set by the
    validation harness. Daily/weekly legs are knowable within the month, so unshifted."""
    df = store.read(group, name)
    if df is None or column not in df.columns:
        return None
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    if s.empty:
        return None
    per_month = s.groupby(s.index.to_period("M")).size().median()
    monthly_native = not (per_month and per_month > 1.5)
    g = s.resample("ME")
    m = (g.last() if monthly_native else g.mean()).dropna()
    if monthly_native and lag_m:
        m = m.shift(int(lag_m))
    return m.dropna() if len(m) else None


def _causal_z(s: pd.Series, lookback: int, min_p: int) -> pd.Series:
    """Rolling z-score (causal) — the CB inverse-volatility standardization."""
    mu = s.rolling(lookback, min_periods=min_p).mean()
    sd = s.rolling(lookback, min_periods=min_p).std()
    return (s - mu) / sd.replace(0, np.nan)


def _leg_contributions(legs: list, cfg: dict, lag_m: int = 0) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Per-leg standardized monthly contributions + sign-adjusted levels, on a shared
    month-end index. A positive series uses a log change (≈ % change, scale-stable);
    a series that can cross zero (the curve spread) uses a plain difference."""
    lookback, min_m = cfg["z_lookback_m"], cfg["z_min_months"]
    contribs: dict[str, pd.Series] = {}
    levels: dict[str, pd.Series] = {}
    for group, name, col, sign in legs:
        x = _component_monthly(group, name, col, lag_m=lag_m)
        if x is None or len(x) < min_m + 2:
            continue
        chg = np.log(x).diff() if bool((x > 0).all()) else x.diff()
        contribs[name] = sign * _causal_z(chg, lookback, min_m)
        levels[name] = sign * x
    if not contribs:
        return None, None
    return pd.DataFrame(contribs), pd.DataFrame(levels)


def tier_index(legs: list, cfg: dict, min_legs: int = 2, lag_m: int = 0) -> pd.DataFrame | None:
    """Build one tier: a rebased cumulative-standardized index plus its 6-month
    momentum (red), EMA trend (blue), diffusion (breadth) and live leg count."""
    contribs, levels = _leg_contributions(legs, cfg, lag_m=lag_m)
    if contribs is None:
        return None
    avail = contribs.notna().sum(axis=1)
    comp = contribs.mean(axis=1).where(avail >= min_legs)   # renormalized over available legs
    first = comp.first_valid_index()
    if first is None:
        return None
    level = (cfg["rebase"] + comp.loc[first:].fillna(0.0).cumsum()).reindex(contribs.index)
    w = int(cfg["roc_window_m"])
    mom6 = level - level.shift(w)
    trend = mom6.ewm(span=int(cfg["trend_smooth_m"]), min_periods=1).mean()
    # diffusion: share of legs whose sign-adjusted level rose over the window
    sixm = levels - levels.shift(int(cfg["diffusion_window_m"]))
    navail = sixm.notna().sum(axis=1)
    diffusion = (100.0 * (sixm > 0).sum(axis=1) / navail.replace(0, np.nan))
    return pd.DataFrame({"index": level, "mom6": mom6, "trend": trend,
                         "diffusion": diffusion, "n_legs": avail})


def cycle_frame(cfg: dict | None = None, lag_m: int = 0) -> pd.DataFrame | None:
    """Monthly frame: per-tier index/mom6/trend/diffusion + the coincident/lagging
    ratio (itself a classic leading read) + the NBER recession flag (ground truth).

    `lag_m` applies a publication lag to natively-monthly inputs for point-in-time
    backtests; it stays 0 on the live path. The NBER truth column is never lagged."""
    cfg = cfg or config.load()["engine"]["business_cycle"]
    tiers = {k: tier_index(v, cfg, lag_m=lag_m) for k, v in TIERS.items()}
    tiers = {k: v for k, v in tiers.items() if v is not None}
    if "leading" not in tiers:
        return None
    idx = pd.DatetimeIndex(sorted(set().union(*[t.index for t in tiers.values()])))
    out = pd.DataFrame(index=idx)
    for tname, t in tiers.items():
        for c in ("index", "mom6", "trend", "diffusion", "n_legs"):
            out[f"{tname}_{c}"] = t[c].reindex(idx)
    if "coincident" in tiers and "lagging" in tiers:
        ratio = (out["coincident_index"] / out["lagging_index"].replace(0, np.nan)).dropna()
        if not ratio.empty:
            cl = 100.0 * ratio / ratio.iloc[0]
            out["cl_ratio"] = cl.reindex(idx)
            out["cl_ratio_mom6"] = out["cl_ratio"] - out["cl_ratio"].shift(int(cfg["roc_window_m"]))
    rec = _component_monthly("fred", "USREC", "nber_recession")
    if rec is not None:
        out["nber_recession"] = (rec.reindex(idx).fillna(0) > 0).astype(int)
    return out


def recession_signal(frame: pd.DataFrame | None, cfg: dict | None = None) -> pd.DataFrame | None:
    """The CB 3 D's on the LEADING tier: Depth+Duration (6-month momentum below the
    calibrated threshold) AND Diffusion (<= the breadth cutoff), held for N months."""
    cfg = cfg or config.load()["engine"]["business_cycle"]
    if frame is None or "leading_mom6" not in frame.columns:
        return None
    s = cfg["signal"]
    depth = frame["leading_mom6"] < float(s["roc_threshold"])       # NaN -> False (safe)
    breadth = frame["leading_diffusion"] <= float(s["diffusion_max"])
    raw = (depth & breadth)
    k = int(s["min_consecutive_m"])
    held = (raw.astype(int).rolling(k).sum() >= k) if k > 1 else raw
    return pd.DataFrame({"depth": depth, "breadth": breadth, "raw": raw,
                         "signal": held.fillna(False).astype(bool)})


# --- snapshot for latest.json + the macro panel ------------------------------
def _load_calibration() -> dict:
    p = _CAL_PATH()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001 — calibration is optional context
            return {}
    return {}


def _phase(lead_mom: float | None, coin_mom: float | None) -> tuple[str, str]:
    """Four-phase cycle clock from the leading & coincident momentum signs."""
    if lead_mom is None or coin_mom is None:
        return ("unknown", "未知")
    lead_up, coin_up = lead_mom > 0, coin_mom > 0
    if lead_up and coin_up:
        return ("expansion", "扩张")
    if not lead_up and coin_up:
        return ("slowdown", "放缓")
    if not lead_up and not coin_up:
        return ("contraction", "收缩")
    return ("recovery", "复苏")


def _spark(s: pd.Series, n: int = 372, dec: int = 2) -> list:
    # ~31 years of months so the mini-chart spans 2001 / 2008 / 2020 — you can see the
    # leading line dive ahead of each NBER band (the whole point of the panel).
    return [round(float(x), dec) if pd.notna(x) else None for x in s.iloc[-n:]]


def _f(v) -> float | None:
    return None if v is None or pd.isna(v) else float(v)


def _phase_at_lag(cfg: dict, lag_m: int) -> dict | None:
    """The leading/coincident momentum + phase clock computed at a given publication
    lag — used to emit the legacy (unlagged) SHADOW reading beside the live one so the
    lag-fix's effect on the phase clock is transparent for one cycle (audit #39)."""
    fr = cycle_frame(cfg, lag_m=lag_m)
    if fr is None or fr.empty or "leading_mom6" not in fr.columns:
        return None
    lm = fr["leading_mom6"].dropna()
    cm = fr["coincident_mom6"].dropna() if "coincident_mom6" in fr.columns else pd.Series(dtype=float)
    lead = float(lm.iloc[-1]) if len(lm) else None
    coin = float(cm.iloc[-1]) if len(cm) else None
    ph_en, ph_zh = _phase(lead, coin)
    return {"lag_m": lag_m, "leading_mom6": lead, "coincident_mom6": coin,
            "phase": {"label": ph_en, "label_zh": ph_zh}}


def business_cycle_snapshot(frame: pd.DataFrame | None = None, cfg: dict | None = None) -> dict:
    """Latest tier readings, the 3-D's recession-signal state, the cycle phase, and
    the MEASURED lead/false-positive stats (from the calibration JSON). Degrades to a
    minimal dict if the store has no data, so the run never crashes.

    The live frame is built at `live_lag_m` (default 1) so the signal fires on the SAME
    publication-lag frame its calibration and advertised lead/FP stats were measured on
    (audit #39). The pre-fix unlagged reading is carried as `shadow` for one cycle so the
    phase-clock flip is transparent. Explicit `frame`/`cfg` (the harness) bypass this."""
    live_frame_supplied = frame is not None
    cfg = cfg or config.load()["engine"]["business_cycle"]
    cal = _load_calibration()
    # the calibrated operating point (scripts/validate_business_cycle.py) WINS over the
    # config defaults for the live signal — so the panel fires on the measured threshold,
    # not a placeholder. The harness passes explicit cfgs, so it is unaffected.
    if cal.get("signal"):
        cfg = dict(cfg, signal=dict(cfg["signal"], **cal["signal"]))
    live_lag_m = int(cfg.get("live_lag_m", 1))
    shadow_lag_m = int(cfg.get("shadow_lag_m", 0))
    frame = cycle_frame(cfg, lag_m=live_lag_m) if frame is None else frame
    if frame is None or frame.empty:
        return {"available": False}
    sig = recession_signal(frame, cfg)

    # Each tier reports its OWN freshest TRUSTWORTHY reading: the leading tier (daily
    # S&P/curve legs) runs to the current month, but the coincident/lagging hard data
    # lag 1-2 months — so the global last row would show a 1-leg coincident. Anchor on
    # the last month where the tier has >= min_legs live components (the leg count
    # ships in the snapshot as the honesty flag for a ragged edge).
    def _last_valid_row(tname: str, min_legs: int = 2):
        nlegs = frame[f"{tname}_n_legs"]
        ok = frame.index[(nlegs >= min_legs) & frame[f"{tname}_mom6"].notna()]
        if not len(ok):  # fall back to any month with a momentum value
            s = frame[f"{tname}_mom6"].dropna()
            ok = s.index
        return (frame.loc[ok[-1]], ok[-1]) if len(ok) else (None, None)

    tiers_out: dict[str, dict] = {}
    for tname in ("leading", "coincident", "lagging"):
        if f"{tname}_mom6" not in frame.columns:
            continue
        trow, tdate = _last_valid_row(tname)
        if trow is None:
            continue
        mom = _f(trow.get(f"{tname}_mom6"))
        tiers_out[tname] = {
            "asof": str(tdate.date()),
            "index": _f(trow.get(f"{tname}_index")),
            "mom6": mom,
            "trend": _f(trow.get(f"{tname}_trend")),
            "diffusion": _f(trow.get(f"{tname}_diffusion")),
            "n_legs": None if pd.isna(trow.get(f"{tname}_n_legs")) else int(trow.get(f"{tname}_n_legs")),
            "direction": (None if mom is None else ("rising" if mom > 0 else "falling")),
            "spark_mom6": _spark(frame[f"{tname}_mom6"]),       # red line (momentum)
            "spark_trend": _spark(frame[f"{tname}_trend"]),     # blue line (smoothed trend)
            "spark_index": _spark(frame[f"{tname}_index"]),
        }
    asof = tiers_out.get("leading", {}).get("asof", str(frame.index[-1].date()))

    # recession-signal state + how long it has been in force
    sig_state: dict = {"available": sig is not None}
    if sig is not None:
        on = bool(sig["signal"].iloc[-1])
        run = sig["signal"][::-1]
        months_active = int((run.cumprod() if on else (~run).cumprod()).sum())
        fired_on = None
        if on:
            off = sig["signal"][~sig["signal"]]
            start = off.index[-1] if len(off) else sig.index[0]
            fired = sig["signal"].loc[start:]
            fired = fired[fired]
            fired_on = str(fired.index[0].date()) if len(fired) else asof
        sig_state.update({
            "state": "on" if on else "off",
            "label": "recession signal active" if on else "no recession signal",
            "label_zh": "衰退信号已触发" if on else "无衰退信号",
            "months_active": months_active,
            "fired_on": fired_on,
            "conditions": {
                "depth": bool(sig["depth"].iloc[-1]),
                "breadth": bool(sig["breadth"].iloc[-1]),
                "diffusion_max": float(cfg["signal"]["diffusion_max"]),
                "roc_threshold": float(cfg["signal"]["roc_threshold"]),
            },
        })

    lead_mom = tiers_out.get("leading", {}).get("mom6")
    coin_mom = tiers_out.get("coincident", {}).get("mom6")
    ph_en, ph_zh = _phase(lead_mom, coin_mom)

    def _last_valid(col: str):
        if col not in frame.columns:
            return None
        s = frame[col].dropna()
        return s.iloc[-1] if len(s) else None

    cl_mom = _last_valid("cl_ratio_mom6")
    rec_last = _last_valid("nber_recession")
    measured = cal.get("measured") if cal else None
    # the honest caveat travels with every snapshot
    caveat = ("Effective sample is tiny (~7 modern US recessions, ~3 point-in-time) — "
              "a recession-RISK timeline, not a crash oracle. Lead times are measured "
              "against NBER dates; see the validation report.")
    caveat_zh = ("有效样本极小（现代美国衰退约 7 次，可点对点回溯约 3 次）——这是衰退"
                 "“风险”时间线，并非崩盘预言。领先时长以 NBER 日期为准，详见验证报告。")

    # Lag passport + SHADOW legacy reading (audit #39): the live signal now fires at the
    # calibrated publication lag; the pre-fix unlagged phase clock is emitted beside it so
    # the flip (contraction<->recovery on the leading momentum sign) is transparent. Skipped
    # when an explicit frame is supplied (the validation harness passes its own).
    shadow = None
    if not live_frame_supplied and shadow_lag_m != live_lag_m:
        leg = _phase_at_lag(cfg, shadow_lag_m)
        if leg is not None:
            leg["is_shadow"] = True
            leg["note"] = ("legacy pre-fix reading at lag_m=0 (unlagged monthly legs); the live "
                           "reading above now fires at the CALIBRATED lag_m={} so it matches the "
                           "advertised lead/FP stats. Retire after one nightly cycle confirms "
                           "stability.".format(live_lag_m))
            shadow = leg
    lag_passport = {
        "basis": "measured",
        "live_lag_m": live_lag_m,
        "calibrated_lag_m": (measured or {}).get("calibration_lag_m", 1),
        "leak_removed": bool(live_lag_m >= 1),
        "note": ("Live monthly legs shifted by live_lag_m so the signal fires on the same "
                 "publication-lag frame the 5.7m-lead/3-FP stats were calibrated on (audit #39). "
                 "Daily leading legs (SPY/curve/HY) are knowable intramonth and unshifted."),
    }

    return {
        "available": True,
        "asof": asof,
        "tiers": tiers_out,
        "cl_ratio_mom6": _f(cl_mom),
        "recession_signal": sig_state,
        "recession_now": (None if rec_last is None else bool(rec_last)),
        "phase": {"label": ph_en, "label_zh": ph_zh},
        "measured": measured,
        "calibrated": bool(measured),
        "lag_passport": lag_passport,
        "shadow": shadow,
        "spark_recession": (_spark(frame["nber_recession"], dec=0)
                            if "nber_recession" in frame.columns else None),
        "caveat": caveat,
        "caveat_zh": caveat_zh,
    }
