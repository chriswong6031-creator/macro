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

LIVE vs VALIDATION data basis (W2.7 / pillar D6):
  • The VALIDATION path (scripts/validate_business_cycle.py) is now point-in-time where
    it can be: it (a) calibrates the operating point LEAVE-ONE-RECESSION-OUT (each
    recession scored by a rule chosen on the OTHERS — no in-sample headline), and
    (b) reads INITIAL-RELEASE (never-revised) values for the legs that have local ALFRED
    vintages (VINTAGE_SERIES; currently ICSA/UMCSENT leading, PAYEMS/INDPRO coincident)
    so the backtest sees what was knowable. Legs with no vintage coverage stay on revised
    data and are flagged revised=True in the calibration artifact — measured leads on
    those legs remain an upper bound.
  • The LIVE nowcast keeps LATEST-REVISED data (use_vintage=False). That is CORRECT for
    now-casting: today you want the best current estimate of last month, not the noisy
    first print. Only the backtest needs the first print, to avoid look-ahead.
  • Publication lag is now a per-leg schedule (PUB_LAG_M) applied SYMMETRICALLY on both
    paths (macro-regime-6), replacing the old asymmetric "0 live / uniform 1 in harness".
  • The live recession threshold is resolved by an explicit, logged order: a
    version-matched + fresh calibration JSON wins; otherwise the config default is used
    and a warning is logged (macro-regime-miss). The old code silently preferred the JSON.
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

# --- publication-lag table (macro-regime-6 fix, W2.7) ------------------------
# Per-leg release lag in MONTHS from a series' reference month to the month it first
# becomes public. Applied SYMMETRICALLY on both the live and the validation paths from
# THIS single table (replacing the old asymmetric "0 live / uniform 1 in the harness"
# handling). Daily/weekly legs (SPY/curve/HY/claims) are knowable intramonth → lag 0.
# For natively-monthly legs the number is the whole-month floor of the real release
# schedule (a May reference figure published in June is not knowable IN May → lag 1):
#
#   leg           series        real release schedule                       lag_m
#   ------------  ------------  ------------------------------------------  -----
#   mfg hours     AWHMAN        Employment Situation, ~1st Fri of next mo     1
#   init claims   ICSA          weekly (Thu), intramonth-knowable             0
#   permits       PERMIT        New Residential Construction, ~mid next mo    1
#   cap orders    NEWORDER      Durable Goods, ~26th of next mo               1
#   equities      SPY           daily, intramonth-knowable                    0
#   HY spread     BAMLH0A0HYM2  daily, intramonth-knowable                    0
#   curve slope   T10Y3M        daily, intramonth-knowable                    0
#   sentiment     UMCSENT       final ~end of same mo, but revised → treat    1
#   payrolls      PAYEMS        Employment Situation, ~1st Fri of next mo     1
#   real income   W875RX1       Personal Income, ~end of next mo              1
#   mfg+trade     CMRMTSPL      Manufacturing & Trade, ~2 mo delay            2
#   ind prod      INDPRO        G.17, ~mid next mo                            1
#   unemp dur     UEMPMEAN      Employment Situation, ~1st Fri of next mo     1
#   inv/sales     ISRATIO       Manufacturing & Trade, ~2 mo delay           2
#   C&I loans     BUSLOANS      H.8, monthly aggregate ~early next mo         1
#   prime rate    MPRIME        moves with the Fed, knowable within month     0
#   CPI services  CUSR0000SAS   CPI, ~mid next mo                             1
#
# The base `lag_m` argument (from the calibration harness) is ADDED to this per-leg
# floor, so a keyed run can still stress a uniform extra lag on top of the schedule.
PUB_LAG_M = {
    "AWHMAN": 1, "ICSA": 0, "PERMIT": 1, "NEWORDER": 1, "SPY": 0,
    "BAMLH0A0HYM2": 0, "T10Y3M": 0, "UMCSENT": 1,
    "PAYEMS": 1, "W875RX1": 1, "CMRMTSPL": 2, "INDPRO": 1,
    "UEMPMEAN": 1, "ISRATIO": 2, "BUSLOANS": 1, "MPRIME": 0, "CUSR0000SAS": 1,
}

# --- vintage (initial-release) coverage (G2 fix, W2.7) -----------------------
# Store-name -> FRED series id that backs an ALFRED initial-release lookup
# (collectors.fred.as_of_series). Only the legs with a local vintage matrix appear
# here; a leg absent from this map is scored on REVISED data in the validation path
# and is flagged revised=True in the calibration artifact. The live nowcast always
# uses latest-revised data (that is correct for now-casting) regardless of this map.
VINTAGE_SERIES = {
    "ICSA": "ICSA", "UMCSENT": "UMCSENT",   # leading legs with vintages
    "PAYEMS": "PAYEMS", "INDPRO": "INDPRO",  # coincident legs with vintages
}

_CAL_PATH = lambda: config.data_dir() / "regime" / "business_cycle_calibration.json"

# calibration artifact schema version — bumped whenever the calibration method or the
# operating-point contract changes, so the live threshold-override guard can refuse a
# stale/foreign JSON (macro-regime-miss fix, W2.7).
CALIBRATION_VERSION = "w2.7-loro-v1"


# --- component → monthly series ----------------------------------------------
def _vintage_monthly(name: str) -> pd.Series | None:
    """Initial-release (never-revised) month-end series for a leg with ALFRED coverage.

    Reads the FIRST-published value per reference period from the local vintage matrix
    (collectors.fred.initial_release) — the leak-free input a point-in-time backtest
    should see, instead of the latest-revised value the live store keeps. Returns None
    when the leg has no vintage coverage or the matrix is absent (caller then falls back
    to the revised store series and flags the leg revised=True)."""
    sid = VINTAGE_SERIES.get(name)
    if sid is None:
        return None
    try:
        from collectors import fred as _fred  # local import: collector is heavy/optional
    except Exception:  # noqa: BLE001
        return None
    s = _fred.initial_release(sid)
    if s is None or len(s) == 0:
        return None
    s = pd.to_numeric(s, errors="coerce").dropna()
    if s.empty:
        return None
    # period index (month-start) -> month-end to match the store path
    m = s.copy()
    m.index = pd.to_datetime(m.index) + pd.offsets.MonthEnd(0)
    return m.groupby(m.index).last().sort_index()


def _component_monthly(group: str, name: str, column: str, lag_m: int = 0,
                       use_vintage: bool = False) -> pd.Series | None:
    """One component as a month-end series. Daily/weekly inputs (equities, claims,
    spreads) collapse to the monthly MEAN (the CB convention for the S&P 500 leg);
    natively-monthly inputs take the month's value.

    Publication lag (macro-regime-6): natively-monthly legs are shifted forward by
    ``PUB_LAG_M[name] + lag_m`` months — the per-leg release schedule (May payrolls
    aren't knowable in May) PLUS any uniform extra lag the caller stresses. The per-leg
    floor is applied on BOTH the live and the validation paths from the same table, so
    the handling is symmetric. Daily/weekly legs are knowable within the month (per-leg
    lag 0) and unshifted.

    Vintage (G2): when ``use_vintage`` is set and the leg has ALFRED coverage
    (VINTAGE_SERIES), the monthly LEVEL is taken from the initial-release matrix so the
    backtest sees what was first published, not later revisions. The live nowcast passes
    use_vintage=False and keeps latest-revised data (correct for now-casting)."""
    src = _vintage_monthly(name) if use_vintage else None
    if src is not None:
        m = src
        monthly_native = True  # vintage legs are all natively monthly
    else:
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
    if monthly_native:
        shift = int(PUB_LAG_M.get(name, 0)) + int(lag_m)
        if shift:
            m = m.shift(shift)
    return m.dropna() if len(m) else None


def _causal_z(s: pd.Series, lookback: int, min_p: int) -> pd.Series:
    """Rolling z-score (causal) — the CB inverse-volatility standardization."""
    mu = s.rolling(lookback, min_periods=min_p).mean()
    sd = s.rolling(lookback, min_periods=min_p).std()
    return (s - mu) / sd.replace(0, np.nan)


def _leg_contributions(legs: list, cfg: dict, lag_m: int = 0,
                       use_vintage: bool = False) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    """Per-leg standardized monthly contributions + sign-adjusted levels, on a shared
    month-end index. A positive series uses a log change (≈ % change, scale-stable);
    a series that can cross zero (the curve spread) uses a plain difference.

    ``use_vintage`` routes vintage-covered legs through the initial-release matrix (G2)."""
    lookback, min_m = cfg["z_lookback_m"], cfg["z_min_months"]
    contribs: dict[str, pd.Series] = {}
    levels: dict[str, pd.Series] = {}
    for group, name, col, sign in legs:
        x = _component_monthly(group, name, col, lag_m=lag_m, use_vintage=use_vintage)
        if x is None or len(x) < min_m + 2:
            continue
        chg = np.log(x).diff() if bool((x > 0).all()) else x.diff()
        contribs[name] = sign * _causal_z(chg, lookback, min_m)
        levels[name] = sign * x
    if not contribs:
        return None, None
    return pd.DataFrame(contribs), pd.DataFrame(levels)


def tier_index(legs: list, cfg: dict, min_legs: int = 2, lag_m: int = 0,
               use_vintage: bool = False) -> pd.DataFrame | None:
    """Build one tier: a rebased cumulative-standardized index plus its 6-month
    momentum (red), EMA trend (blue), diffusion (breadth) and live leg count."""
    contribs, levels = _leg_contributions(legs, cfg, lag_m=lag_m, use_vintage=use_vintage)
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


def cycle_frame(cfg: dict | None = None, lag_m: int = 0,
                use_vintage: bool = False) -> pd.DataFrame | None:
    """Monthly frame: per-tier index/mom6/trend/diffusion + the coincident/lagging
    ratio (itself a classic leading read) + the NBER recession flag (ground truth).

    `lag_m` applies an EXTRA uniform publication lag on top of the per-leg PUB_LAG_M
    schedule (both applied symmetrically live and in the harness). ``use_vintage``
    routes vintage-covered legs through the initial-release matrix for the point-in-time
    backtest; the live path leaves it False (latest-revised = correct for now-casting).
    The NBER truth column is never lagged and never vintaged."""
    cfg = cfg or config.load()["engine"]["business_cycle"]
    tiers = {k: tier_index(v, cfg, lag_m=lag_m, use_vintage=use_vintage) for k, v in TIERS.items()}
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
            # Causal rebase (macro-regime-5): anchor to the FIRST-VALID value of the
            # ratio's own history, which is fixed the moment that first month exists and
            # never moves as later data arrives — so appending months cannot rewrite the
            # historical level. (The old `ratio.iloc[0]` after a full-frame dropna picked
            # whatever the earliest surviving row happened to be; still a constant, but its
            # identity shifted when leg coverage changed. The derived cl_ratio_mom6 is a
            # difference and thus scale-invariant either way — this fixes the LEVEL so any
            # future consumer that charts cl_ratio sees a real-time-consistent line.)
            anchor = float(ratio.iloc[0])
            cl = 100.0 * ratio / anchor if anchor else pd.Series(dtype=float)
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


# max age (days) before a calibration JSON is considered stale for the LIVE override.
# The operating point is calibrated against ~decade-spaced NBER recessions, not intraday
# data, so it does not need frequent refreshing — but an artifact older than this (or one
# with no timestamp) should not silently drive the live signal without a re-run.
_CAL_MAX_AGE_DAYS = 400


def _resolve_signal_cfg(cfg: dict, cal: dict) -> tuple[dict, dict]:
    """Explicit, LOGGED resolution order for the live recession threshold
    (macro-regime-miss fix). Returns (resolved_cfg, resolution_meta).

    Order:
      1. Use the calibration-JSON operating point IF it is (a) version-matched to
         CALIBRATION_VERSION and (b) fresh (generated_at within _CAL_MAX_AGE_DAYS).
      2. Otherwise fall back to the config default and LOG A WARNING naming the reason —
         the old code silently preferred the JSON with no version/staleness check, so a
         hand-edited or stale artifact could drive the live "recession signal on/off"
         invisibly.
    The harness always passes an explicit cfg and never hits this path."""
    sig_cal = cal.get("signal") if cal else None
    meta = {"threshold_source": "config_default", "reason": None,
            "calibration_version": cal.get("version") if cal else None,
            "calibration_generated_at": cal.get("generated_at") if cal else None}
    if not sig_cal:
        meta["reason"] = "no calibration signal block"
        return cfg, meta
    ver = cal.get("version")
    if ver != CALIBRATION_VERSION:
        meta["reason"] = (f"calibration version {ver!r} != expected "
                          f"{CALIBRATION_VERSION!r} — using config default")
        log.warning("business_cycle: %s", meta["reason"])
        return cfg, meta
    gen = cal.get("generated_at")
    age_days = None
    if gen:
        try:
            now = pd.Timestamp.now(tz="UTC").tz_localize(None)
            age_days = (now - pd.Timestamp(gen).tz_localize(None)).days
        except Exception:  # noqa: BLE001 — unparseable stamp is treated as stale
            age_days = None
    if age_days is None:
        meta["reason"] = "calibration has no parseable generated_at — using config default"
        log.warning("business_cycle: %s", meta["reason"])
        return cfg, meta
    if age_days > _CAL_MAX_AGE_DAYS:
        meta["reason"] = (f"calibration is {age_days}d old (> {_CAL_MAX_AGE_DAYS}d) — "
                          "using config default; re-run validate_business_cycle")
        log.warning("business_cycle: %s", meta["reason"])
        return cfg, meta
    # fresh + version-matched → the calibrated operating point wins
    meta.update({"threshold_source": "calibration", "reason": "version-matched + fresh",
                 "calibration_age_days": age_days})
    return dict(cfg, signal=dict(cfg["signal"], **sig_cal)), meta


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
    """The leading/coincident momentum + phase clock computed at a given EXTRA uniform
    lag (stacked on the per-leg PUB_LAG_M schedule) — used to emit an optional SHADOW
    reading beside the live one when config sets a differing shadow_lag_m (transparency
    hook for any publication-lag transition)."""
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
    """Latest tier readings, the 3-D's recession-signal state, the cycle phase, and the
    OUT-OF-SAMPLE (LORO) lead/false-positive stats (from the calibration JSON). Degrades
    to a minimal dict if the store has no data, so the run never crashes.

    Publication lag is the per-leg PUB_LAG_M schedule applied symmetrically on live and
    validation paths; `live_lag_m` (default 0) is an extra uniform lag on top. The live
    recession threshold is resolved via `_resolve_signal_cfg` (calibration if
    version-matched + fresh, else config default with a logged warning; macro-regime-miss)
    and the resolution is surfaced as `calibration_resolution`. Explicit `frame`/`cfg`
    (the validation harness) bypass the resolver and the shadow."""
    live_frame_supplied = frame is not None
    cfg = cfg or config.load()["engine"]["business_cycle"]
    cal = _load_calibration()
    # Explicit, LOGGED threshold resolution (macro-regime-miss): the calibration operating
    # point drives the live signal ONLY if it is version-matched + fresh, else the config
    # default is used with a warning. The harness passes an explicit cfg and never uses cal.
    if not live_frame_supplied:
        cfg, cal_resolution = _resolve_signal_cfg(cfg, cal)
    else:
        cal_resolution = {"threshold_source": "explicit_cfg", "reason": "harness-supplied cfg"}
    # `live_lag_m` is now an EXTRA uniform lag stacked ON TOP of the per-leg PUB_LAG_M
    # schedule (which already carries each leg's real publication lag symmetrically on
    # both paths). It defaults to 0 — the per-leg table is the publication lag; a nonzero
    # value stress-shifts everything further. The harness records the extra lag used.
    live_lag_m = int(cfg.get("live_lag_m", 0))
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

    # Optional legacy SHADOW reading — only emitted if config still sets shadow_lag_m to a
    # value that differs from the live extra lag (default: both 0, so no shadow). Kept as a
    # transparency hook for any future lag-transition, not as a standing artifact.
    shadow = None
    if not live_frame_supplied and shadow_lag_m != live_lag_m:
        leg = _phase_at_lag(cfg, shadow_lag_m)
        if leg is not None:
            leg["is_shadow"] = True
            leg["note"] = ("shadow phase clock at extra lag_m={} (vs live extra lag_m={}); the "
                           "live reading above uses the per-leg PUB_LAG_M publication schedule."
                           .format(shadow_lag_m, live_lag_m))
            shadow = leg
    lag_passport = {
        "basis": "per_leg_schedule",
        "extra_uniform_lag_m": live_lag_m,
        "per_leg_lag_m": dict(PUB_LAG_M),
        "symmetric": True,
        "note": ("Publication lag is a per-leg schedule (PUB_LAG_M) applied symmetrically on "
                 "the live and validation paths (macro-regime-6). Daily leading legs "
                 "(SPY/curve/HY/claims) are knowable intramonth → lag 0; monthly hard data "
                 "carry their real release lag (1-2 months). `extra_uniform_lag_m` is any "
                 "additional uniform stress lag on top (default 0)."),
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
        "calibration_resolution": cal_resolution,
        "lag_passport": lag_passport,
        "shadow": shadow,
        "spark_recession": (_spark(frame["nber_recession"], dec=0)
                            if "nber_recession" in frame.columns else None),
        "caveat": caveat,
        "caveat_zh": caveat_zh,
    }
