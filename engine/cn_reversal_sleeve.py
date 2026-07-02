"""CN Reversal Sleeve — the validated within-sector 3M reversal edge shipped at ITS OWN
product unit: a monthly-rebalanced, no-gate, equal-weight, small-per-name BASKET.

This is the product-unit reframe §W6-CN sequenced the whole CN wave to enable. The
validated A-share cross-sectional edge (research/CHINA_HK_STOCK_SIGNALS.md L98-123:
deepest-quintile 3-month within-sector reversal, ~790 names, 388 monthly rebalances,
+0.56%/mo excess, Sharpe 0.58, maxDD −37.6%, hit 56%) was buried as a 0.55 tiebreaker
in a daily act-now board that overlaps the edge 1/110 (research/CHINA_ENGINE_REASSESSMENT.md
Q1). It ships here instead as a portfolio, NOT stock tips.

CONSTRUCTION — faithful to the validated unit, no creativity (§W6-CN, Q1):
  * MONTHLY rebalance (last CN session of each month).
  * DEEPEST-QUINTILE within-sector 3-month reversal fuel (rev_z, the SAME machinery as
    engine.china_reversal — deeper relative dip = more mean-reversion fuel).
  * EQUAL-WEIGHT across the sleeve; small-per-name sizing guidance in the presentation.
  * NO confirmation / timing gates of ANY kind. Phase-0 verified every gate flips the edge
    negative: turn-confirmation → −0.29%/mo, maxDD −78.9%; quality floor → −0.21%/mo. The
    edge lives in the UNCONFIRMED dip. `assert_no_gate()` makes this a hard invariant.
  * Universe hygiene ONLY (responsibility screens, NOT alpha/quality filters): ST fail-closed,
    real-mktcap floor (sentinel-aware), the post-#791 ADV floor. Respects the append-only
    universe (the current plane is an UPPER BOUND — china_search historically deleted dropped
    names; all backcast stats carry the survivorship caveat, CN-2).

SLEEVE SIZING (§W6-CN, Q3): risk_radar_intl CN gross_factor as a SLEEVE-level size
multiplier (today ×0.90 caution) — validated forward-drawdown composite on EXTERNAL drivers,
so it does NOT cancel the contrarian edge. Never a per-name veto. Provenance (state, can_force,
as_of) is surfaced.

The forward ledger (engine.cn_reversal_sleeve_ledger via the builder) is the REAL track
record; the backcast here is reconstruction-on-the-current-plane, honestly labeled UPPER BOUND.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from engine.china_reversal import is_st

log = logging.getLogger(__name__)

# --- construction constants (faithful to the validated unit) ------------------------------
DEEPEST_QUINTILE = 0.20          # top 20% of within-sector reversal fuel = "deepest quintile"
WIN_DAYS = 63                    # ~3-month lookback (63 CN sessions), matches china_reversal
MIN_SECTOR = 6                   # drop thin sectors so a 2-name "sector" can't dominate
MCAP_FLOOR_YI = 30.0             # 亿 CNY; 30.0 EXACTLY is the CN-2 placeholder sentinel => unknown
BENCH_TICKER = "510300.SS"       # CSI300 ETF — the ONLY China excess benchmark (data/china)

# The validated reference numbers (research/CHINA_HK_STOCK_SIGNALS.md L98-123). The backcast
# is a DIFFERENT window (trailing ~24mo on the current upper-bound plane), so it should be the
# SAME ORDER OF MAGNITUDE, not identical — a wildly-off backcast is a bug, not a finding.
REFERENCE = {
    "excess_mo_pct": 0.56, "sharpe": 0.58, "maxdd_pct": -37.6, "hit_pct": 56.0,
    "n_rebalances": 388, "n_names": 790, "window": "1990→2026",
    "source": "research/CHINA_HK_STOCK_SIGNALS.md L98-123",
}

# ---- the no-gate invariant ----------------------------------------------------------------
# Any field whose presence would mean a confirmation / timing / quality gate leaked into
# membership. Phase-0 proved each of these FLIPS the edge negative. assert_no_gate() refuses
# to build if any appears in the construction params — a hard, testable guarantee that the
# sleeve is the validated no-gate unit and not a re-skinned act-now board.
_FORBIDDEN_GATE_FIELDS = frozenset({
    "confluence", "tier_cascade", "is_buyable", "buyable", "macd", "stochrsi",
    "turn_confirmation", "ret_5d", "quality_floor", "washout_gate", "market_healthy",
    "timing", "entry_ok", "fresh", "extension_gate", "above200", "weekly_bull",
})


def assert_no_gate(params: dict) -> None:
    """Hard invariant: NO confirmation / timing / quality gate may influence membership.

    Phase-0 measured every such gate flipping the validated edge negative (turn-confirmation
    −0.29%/mo maxDD −78.9%; quality floor −0.21%/mo). Membership is a pure function of
    within-sector reversal fuel + universe hygiene. Raises ValueError if a forbidden gate
    field is present and truthy — the tests assert this can never silently regress."""
    leaked = sorted(k for k in params if k.lower() in _FORBIDDEN_GATE_FIELDS and params[k])
    if leaked:
        raise ValueError(
            f"cn_reversal_sleeve: no-gate invariant violated — gate field(s) {leaked} would "
            "flip the validated edge negative (Phase-0). Membership must be reversal + hygiene only."
        )


# ---- universe hygiene (responsibility screens, NOT alpha filters) -------------------------
def _hygiene_ok(t: str, *, tkr_name_zh: dict, tkr_mktcap: dict, adv_by: dict,
                adv_floor_yi: float, screened: dict) -> bool:
    """Responsibility screens only (§W6-CN): ST fail-closed, real-mktcap floor (sentinel-aware),
    ADV floor. NOT quality/alpha filters — those forfeit the edge. Mutates `screened` counts."""
    if is_st(tkr_name_zh.get(t)):                        # ST / *ST / 退 — fail CLOSED
        screened["st"] += 1
        return False
    cap = tkr_mktcap.get(t)
    # sentinel-aware: 30.0 EXACTLY is the CN-2 "unknown" placeholder → do NOT drop on it.
    if cap is not None and cap != MCAP_FLOOR_YI and cap < MCAP_FLOOR_YI:
        screened["mcap"] += 1
        return False
    adv = adv_by.get(t)
    if adv is not None and adv < adv_floor_yi:           # proven illiquid only (missing passes)
        screened["adv"] += 1
        return False
    return True


def _rev_z_at(closes: pd.DataFrame, asof: pd.Timestamp, *, tkr_sector: dict,
              hygiene, win: int, min_sector: int) -> pd.DataFrame | None:
    """Within-sector 3M reversal fuel (rev_z) for every hygiene-passing name as of `asof`.

    IDENTICAL math to engine.china_reversal.reversal_watch: rev = how far BELOW the sector
    mean this name sits over `win` sessions; rev_z = sector-standardized, clipped ±3. NO gate.
    Returns a frame [ret, sector, rev, rev_z, sector_n] indexed by ticker, or None if too thin."""
    sl = closes.loc[:asof]
    if len(sl) < win + 5:
        return None
    r = sl.iloc[-1] / sl.iloc[-(win + 1)] - 1.0                    # trailing 3-month return
    d = pd.DataFrame({"ret": r})
    d["sector"] = [tkr_sector.get(t, "—") for t in d.index]
    d = d[d["ret"].notna() & (d["sector"] != "—")]
    d = d[[hygiene(t) for t in d.index]]                          # responsibility screens
    if d.empty:
        return None
    big = d.groupby("sector")["ret"].transform("count") >= min_sector
    d = d[big]
    if d.empty:
        return None
    d["rev"] = -(d["ret"] - d.groupby("sector")["ret"].transform("mean"))
    sd = d.groupby("sector")["rev"].transform("std").replace(0, np.nan)
    d["rev_z"] = (d["rev"] / sd).clip(-3, 3)
    d["sector_n"] = d.groupby("sector")["rev"].transform("count").astype(int)
    d = d[d["rev_z"].notna()]
    return d if not d.empty else None


def _deepest_quintile(d: pd.DataFrame, q: float = DEEPEST_QUINTILE) -> pd.Index:
    """The deepest-quintile members by rev_z (highest reversal fuel). EW membership — no
    per-name weighting beyond inclusion (the validated construction is equal-weight)."""
    k = max(1, int(round(len(d) * q)))
    return d.sort_values("rev_z", ascending=False).head(k).index


# ---- current membership -------------------------------------------------------------------
def current_membership(closes: pd.DataFrame, tkr_sector: dict, tkr_name: dict, *,
                       tkr_name_zh: dict | None = None, tkr_mktcap: dict | None = None,
                       adv_by: dict | None = None, adv_floor_yi: float = 0.5,
                       win: int = WIN_DAYS, min_sector: int = MIN_SECTOR,
                       asof=None) -> dict | None:
    """The sleeve's CURRENT deepest-quintile within-sector reversal membership (EW, no gate).

    Universe hygiene: ST fail-closed, sentinel-aware mktcap floor, ADV floor. Returns
    {as_of, n_universe, members[], sectors{}, screened{}} or None on thin/missing data.
    Best-effort: never raises on data problems."""
    assert_no_gate({"win": win, "min_sector": min_sector})       # invariant belt-and-braces
    if closes is None or closes.empty:
        return None
    tkr_name_zh = tkr_name_zh or {}
    tkr_mktcap = tkr_mktcap or {}
    adv_by = adv_by or {}
    closes = closes.sort_index()
    asof = pd.Timestamp(asof) if asof is not None else closes.index.max()
    screened = {"st": 0, "mcap": 0, "adv": 0}

    def hygiene(t):
        return _hygiene_ok(t, tkr_name_zh=tkr_name_zh, tkr_mktcap=tkr_mktcap, adv_by=adv_by,
                           adv_floor_yi=adv_floor_yi, screened=screened)

    d = _rev_z_at(closes, asof, tkr_sector=tkr_sector, hygiene=hygiene,
                  win=win, min_sector=min_sector)
    if d is None:
        return None
    members_idx = _deepest_quintile(d)
    ranks = d.groupby("sector")["rev"].rank(ascending=False)
    members = []
    for t in d.loc[members_idx].sort_values("rev_z", ascending=False).index:
        row = d.loc[t]
        members.append({
            "ticker": t, "name": tkr_name.get(t, t), "sector": row["sector"],
            "ret_3m": round(float(row["ret"]) * 100, 1),
            "rev_z": round(float(row["rev_z"]), 2),
            "sector_rank": int(ranks.get(t, 0)), "sector_n": int(row["sector_n"]),
            "mktcap_yi": (round(float(tkr_mktcap[t]), 0)
                          if t in tkr_mktcap and tkr_mktcap[t] != MCAP_FLOOR_YI else None),
            "weight": None,   # filled below — pure EW
        })
    if not members:
        return None
    w = round(1.0 / len(members), 4)
    for m in members:
        m["weight"] = w
    from collections import Counter
    sectors = dict(Counter(m["sector"] for m in members).most_common())
    return {
        "as_of": str(asof.date()), "n_universe": int(len(d)),
        "n_members": len(members), "members": members, "sectors": sectors,
        "screened": screened, "equal_weight": w,
        "construction": {"unit": "deepest_quintile_within_sector_3m_reversal",
                         "quintile": DEEPEST_QUINTILE, "win_days": win, "gate": "none",
                         "weighting": "equal", "rebalance": "monthly"},
    }


# ---- backcast (reconstruction on the current upper-bound plane) ---------------------------
def _month_end_sessions(index: pd.DatetimeIndex, months: int) -> list[pd.Timestamp]:
    """The last available CN session of each of the trailing `months` calendar months."""
    s = pd.Series(index, index=index)
    grp = s.groupby([index.year, index.month]).max()
    ends = sorted(grp.tolist())
    return ends[-(months + 1):]        # +1 so the first leg has a forward return to measure


def backcast(closes: pd.DataFrame, tkr_sector: dict, *, tkr_name_zh: dict | None = None,
             tkr_mktcap: dict | None = None, adv_by: dict | None = None,
             adv_floor_yi: float = 0.5, win: int = WIN_DAYS, min_sector: int = MIN_SECTOR,
             months: int = 24, bench: pd.Series | None = None) -> dict | None:
    """Reconstruct the sleeve's trailing `months` monthly rebalances on the CURRENT plane.

    UPPER BOUND (survivorship / CN-2 deletion caveat) — labeled as such everywhere. At each
    month-end: pick the deepest-quintile EW membership (same as live), hold to the next
    month-end, record the EW forward return and the CSI300 return over the same window. Emits
    a NAV series (sleeve vs CSI300) + summary stats (excess/mo, Sharpe, maxDD, hit). Returns
    None if fewer than ~4 legs mature. Best-effort, never raises."""
    if closes is None or closes.empty:
        return None
    tkr_name_zh = tkr_name_zh or {}
    tkr_mktcap = tkr_mktcap or {}
    adv_by = adv_by or {}
    closes = closes.sort_index()
    ends = _month_end_sessions(closes.index, months)
    if len(ends) < 5:
        return None
    screened = {"st": 0, "mcap": 0, "adv": 0}

    def hygiene(t):
        return _hygiene_ok(t, tkr_name_zh=tkr_name_zh, tkr_mktcap=tkr_mktcap, adv_by=adv_by,
                           adv_floor_yi=adv_floor_yi, screened=screened)

    legs = []
    for i in range(len(ends) - 1):
        t0, t1 = ends[i], ends[i + 1]
        d = _rev_z_at(closes, t0, tkr_sector=tkr_sector, hygiene=hygiene,
                      win=win, min_sector=min_sector)
        if d is None:
            continue
        members = list(_deepest_quintile(d))
        # EW forward return over [t0, t1] on the current plane (names with both prices)
        rets = []
        for t in members:
            try:
                p0, p1 = float(closes.at[t0, t]), float(closes.at[t1, t])
            except (KeyError, ValueError):
                continue
            if np.isfinite(p0) and np.isfinite(p1) and p0 > 0:
                rets.append(p1 / p0 - 1.0)
        if len(rets) < min_sector:
            continue
        sleeve_ret = float(np.mean(rets))
        bench_ret = None
        if bench is not None and t0 in bench.index and t1 in bench.index:
            b0, b1 = float(bench.at[t0]), float(bench.at[t1])
            if b0 > 0:
                bench_ret = b1 / b0 - 1.0
        legs.append({"t0": str(t0.date()), "t1": str(t1.date()), "n": len(rets),
                     "sleeve_ret": round(sleeve_ret, 4),
                     "bench_ret": round(bench_ret, 4) if bench_ret is not None else None,
                     "excess": round(sleeve_ret - bench_ret, 4) if bench_ret is not None else None})
    if len(legs) < 4:
        return None

    sr = np.array([l["sleeve_ret"] for l in legs], dtype=float)
    ex = np.array([l["excess"] for l in legs if l["excess"] is not None], dtype=float)
    have_bench = len(ex) == len(legs) and len(ex) > 0
    # NAV lines (start at 1.0), sleeve absolute + CSI300 absolute for the vs-line
    nav_sleeve, nav_bench = [1.0], [1.0]
    dates = [legs[0]["t0"]]
    for l in legs:
        nav_sleeve.append(round(nav_sleeve[-1] * (1.0 + l["sleeve_ret"]), 4))
        b = l["bench_ret"] if l["bench_ret"] is not None else 0.0
        nav_bench.append(round(nav_bench[-1] * (1.0 + b), 4))
        dates.append(l["t1"])

    def _maxdd(nav):
        arr = np.array(nav, dtype=float)
        peak = np.maximum.accumulate(arr)
        return float(((arr - peak) / peak).min())

    series = ex if have_bench else sr                       # grade excess when we have a bench
    mean_mo = float(series.mean())
    sd_mo = float(series.std(ddof=1)) if len(series) > 1 else 0.0
    sharpe = round(mean_mo / sd_mo * np.sqrt(12), 2) if sd_mo > 0 else None
    hit = float((series > 0).mean())
    return {
        "months": months, "n_legs": len(legs), "have_bench": have_bench,
        "graded_on": "csi300_excess" if have_bench else "absolute",
        "excess_mo_pct": round(mean_mo * 100, 2),
        "sharpe": sharpe,
        "maxdd_pct": round(_maxdd(nav_sleeve) * 100, 1),
        "hit_pct": round(hit * 100, 1),
        "nav": {"dates": dates, "sleeve": nav_sleeve, "csi300": nav_bench},
        "legs": legs,
        "caveat": ("RECONSTRUCTION on the current (upper-bound) plane — china_search historically "
                   "deleted dropped names' history (CN-2), so realized deletions/failures are "
                   "under-represented. The forward ledger is the real record."),
        "reference": REFERENCE,
    }
