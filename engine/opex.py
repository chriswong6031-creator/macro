"""engine/opex.py — OPEX / quad-witching calendar seasonality (dealer-flow, no OI needed).

The ONE dealer-flow idea that is fully validatable on decades of price history with ZERO
options open-interest: the monthly options-expiration cycle. Large dealer gamma rolls off
on the 3rd-Friday expiration, and the structure of that roll-off has historically shaped
the days around it (pinning into expiration, a vol/återflow release the week AFTER, and
elevated activity on the quarterly quad-witching). Because it needs only an expiration
CALENDAR + an index price series, it sidesteps the un-backfillable single-name OI limit
entirely — and it is measured here, not assumed.

This module (a) tags each trading day with its position in the OPEX cycle and (b) measures
the realized forward-return / forward-vol edge of each phase over the full history, with an
honest Newey-West t-stat and sub-period sign check. The snapshot reports the CURRENT phase
plus the MEASURED edge for that phase — clearly labelled CONTEXT (a thin, widely-known
calendar tilt), never a stand-alone buy/sell. Causal: tags use only the calendar; the edge
is computed in-sample for display, and gated by significance before it claims anything.

See engine/vol_regime.py (the vol-surface regime), engine/options_desk.py (the desk reads).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from engine.validation import newey_west_tstat

# expiration-week window (trading days relative to the 3rd-Friday expiration day, td=0):
OPEX_WEEK_LO = -4          # Mon..Fri of expiration week
POST_LO, POST_HI = 1, 5    # the week AFTER expiration (the documented soft drift)
QUAD_MONTHS = (3, 6, 9, 12)


def _third_friday(y: int, m: int) -> date:
    d = date(y, m, 1)
    first_fri = 1 + ((4 - d.weekday()) % 7)     # weekday: Mon=0..Fri=4
    return date(y, m, first_fri + 14)


def expiration_days(index: pd.DatetimeIndex) -> pd.Series:
    """Map each month's 3rd-Friday expiration to the last trading day <= that Friday in
    `index` (handles holidays e.g. Good Friday). Returns a Series of those trading days
    flagged is_quad. Causal — purely calendar-derived."""
    idx = pd.DatetimeIndex(sorted(set(index)))
    years = range(idx[0].year, idx[-1].year + 1)
    rows = {}
    for y in years:
        for m in range(1, 13):
            fri = pd.Timestamp(_third_friday(y, m))
            on_or_before = idx[idx <= fri]
            if len(on_or_before):
                rows[on_or_before[-1]] = (m in QUAD_MONTHS)
    return pd.Series(rows, dtype=bool).sort_index()


def tag(index: pd.DatetimeIndex) -> pd.DataFrame:
    """Per-trading-day OPEX-cycle tags: td_since (trading days since last expiration),
    td_to (to next), the phase label, and is_quad/in_opex_week/in_post_opex flags."""
    idx = pd.DatetimeIndex(sorted(set(index)))
    pos = {t: i for i, t in enumerate(idx)}
    exp = expiration_days(idx)
    exp_pos = np.array([pos[t] for t in exp.index])
    out = pd.DataFrame(index=idx)
    n = len(idx)
    i_all = np.arange(n)
    # nearest expiration position at/below and above each day
    prev_idx = np.searchsorted(exp_pos, i_all, side="right") - 1
    next_idx = np.searchsorted(exp_pos, i_all, side="left")
    td_since = np.where(prev_idx >= 0, i_all - exp_pos[np.clip(prev_idx, 0, len(exp_pos) - 1)], np.nan)
    td_to = np.where(next_idx < len(exp_pos), exp_pos[np.clip(next_idx, 0, len(exp_pos) - 1)] - i_all, np.nan)
    out["td_since"] = td_since
    out["td_to"] = td_to
    in_week = (td_to <= -OPEX_WEEK_LO) & (td_to >= 0) | (td_since == 0)
    out["in_opex_week"] = in_week
    out["in_post_opex"] = (td_since >= POST_LO) & (td_since <= POST_HI)
    # quad flag attaches to the cycle whose expiration is the nearest PAST one
    quad_vals = exp.to_numpy()
    out["is_quad_cycle"] = np.where(prev_idx >= 0, quad_vals[np.clip(prev_idx, 0, len(quad_vals) - 1)], False)
    out["phase"] = np.where(out["in_opex_week"], "opex_week",
                            np.where(out["in_post_opex"], "post_opex", "mid_cycle"))
    return out


# --------------------------------------------------------------------------- #
# measured edge per phase
# --------------------------------------------------------------------------- #
def seasonality(close: pd.Series, fwd_days: int = 5) -> dict:
    """Measured forward `fwd_days`-day return + forward realized vol by OPEX phase over the
    whole history, with a Newey-West t-stat (overlapping windows) and a pre/post-2010 sign
    check. Returns per-phase stats + a significance verdict. In-sample (display context)."""
    close = close.dropna().astype(float)
    if len(close) < 500:
        return {"available": False}
    t = tag(close.index)
    fwd = close.pct_change(fwd_days, fill_method=None).shift(-fwd_days) * 100
    fwd_rv = (close.pct_change(fill_method=None).rolling(fwd_days).std().shift(-fwd_days)
              * np.sqrt(252) * 100)
    df = pd.concat([t["phase"], t["is_quad_cycle"], fwd.rename("fwd"),
                    fwd_rv.rename("rv")], axis=1).dropna(subset=["fwd"])
    base = float(df["fwd"].mean())
    half = df.index[len(df) // 2]
    out = {"available": True, "fwd_days": fwd_days, "base_fwd_pct": round(base, 3),
           "n": int(len(df)), "phases": {}}
    for ph in ("opex_week", "post_opex", "mid_cycle"):
        sub = df[df["phase"] == ph]
        if len(sub) < 60:
            continue
        excess = sub["fwd"] - base
        nw = newey_west_tstat(excess.to_numpy(), lags=max(2, fwd_days))
        s1 = np.sign(df[(df["phase"] == ph) & (df.index < half)]["fwd"].mean() - base)
        s2 = np.sign(df[(df["phase"] == ph) & (df.index >= half)]["fwd"].mean() - base)
        out["phases"][ph] = {
            "mean_fwd_pct": round(float(sub["fwd"].mean()), 3),
            "excess_pct": round(float(excess.mean()), 3),
            "fwd_vol": round(float(sub["rv"].mean()), 2) if sub["rv"].notna().any() else None,
            "t_hac": nw.get("t"), "n": int(len(sub)),
            "sign_stable": bool(s1 == s2 and s1 != 0),
            "significant": bool(nw.get("t") is not None and abs(nw["t"]) >= 2.0 and s1 == s2),
        }
    # quad-witching week vol bump (context)
    qw = df[(df["phase"] == "opex_week") & (df["is_quad_cycle"])]
    if len(qw) >= 40 and qw["rv"].notna().any():
        out["quad_week_fwd_vol"] = round(float(qw["rv"].mean()), 2)
    return out


def snapshot(close: pd.Series) -> dict:
    """Current OPEX phase + the MEASURED edge for it (context). None-safe."""
    close = close.dropna().astype(float) if close is not None else None
    if close is None or len(close) < 500:
        return {"available": False}
    t = tag(close.index)
    last = t.iloc[-1]
    seas = seasonality(close)
    phase = last["phase"]
    ph_stats = (seas.get("phases") or {}).get(phase, {})
    read = None
    if ph_stats.get("significant"):
        ex = ph_stats["excess_pct"]
        read = (f"{phase.replace('_', ' ')}: historically {'+' if ex >= 0 else ''}{ex:.2f}% "
                f"excess fwd-{seas['fwd_days']}d return (t={ph_stats['t_hac']}, n={ph_stats['n']}).")
    else:
        read = (f"{phase.replace('_', ' ')}: no statistically robust calendar edge "
                "measured (display context).")
    return {
        "available": True, "phase": phase,
        "td_since_opex": None if pd.isna(last["td_since"]) else int(last["td_since"]),
        "td_to_opex": None if pd.isna(last["td_to"]) else int(last["td_to"]),
        "in_opex_week": bool(last["in_opex_week"]),
        "is_quad_cycle": bool(last["is_quad_cycle"]),
        "read": read, "phase_stats": ph_stats,
        "doctrine": ("OPEX calendar seasonality — a thin, widely-known dealer-flow tilt "
                     "measured on price history (no OI). Context only, never a buy/sell."),
    }
