"""Short-pressure axes — DISPLAY-ONLY CONTEXT, printed legs, never a fused score.

WHAT THIS IS. Six short-side positioning axes read off the PIT short-interest
panel (scripts/backfill_finra_short_interest.py), the IBKR borrow panel
(collectors/ibkr_borrow.py) and the FINRA daily short-volume panel. Each axis is
returned SEPARATELY with its own coverage. Nothing here adds, weights, or ranks
them.

WHY NO COMPOSITE — this is a legal constraint, not a style preference:
  * "Positioning fusion (positioning keys fused into signal scores) | ILLEGAL"
    (DO_NOT_REBUILD, Signal Commons rulings 2026-07-05).
  * SM2-R3: "No composite across 13F/insider/short/options axes at any grain...
    No function may accept both a 13F metric and a short-derived metric
    (days_to_cover, si_change_pct) as combined inputs producing a single number."
  * "Short-side lobe as directional shorting | FORBIDDEN — AVOID-not-SHORT
    evidence only" (DO_NOT_REBUILD; NW rails+lobes 2026-07-06).
So the popular "high short interest + rising estimates + call skew = squeeze
candidate" recipe cannot be built here as one number. The compliant form is the
one below: print each axis, count how many agree, and say plainly that the
agreement is ungraded. A display-tier composite would additionally require the
PSI §3.1.2 construction law (printed legs, v0 equal weights, abstention, day-one
forward grading) — see research/short_side/SP1_SHORT_PRESSURE_PREREG.md, which
freezes that test. Until it reads out, this module states state, not stance.

DIRECTION, STATED HONESTLY. The cross-sectional literature runs one way: high
days-to-cover predicts LOW forward returns (Hong-Li-Ni-Scheinkman-Yan), and
expensive-to-borrow names underperform. The "squeeze" reading is the retail
inversion of a bearish base rate. This module therefore never renders high short
pressure as bullish. It also does not render it as a short recommendation — the
same literature (Muravyev-Pearson-Pollet 2025) finds the long/short version of
that edge is consumed by the borrow fee itself, which is precisely why an
avoid/de-risk lens is the honest use and a short book is not.

THREE MEASURED TRAPS, all guarded here:
  1. days_to_cover is capped at 999.99 when ADV rounds to 0 — 17.8% of all rows,
     so the raw column's p90 IS the sentinel. Percentiles here are computed on
     uncapped rows only.
  2. The feed is ~42% OTC, which carries nearly all the sentinels. Percentiles
     here are computed on exchange-listed rows only.
  3. Borrow fee is near-CONSTANT in our universe: median 0.35%, 18 of 1,519
     names at/above 1%, none above 20% (2026-08-05), against a full-file median
     of 1.10%. Z-scoring fee across our universe alone scores noise around a flat
     line, so fee is exposed as a rare-event FLAG with an absolute threshold,
     never as a percentile or z. Same structural-constancy trap already filed
     against single-name gamma_regime (audit #29).

PIT LAW. `asof_slice` joins on `knowable_date` (settlement + 10 days), never on
`settlement_date`. Joining on settlement date buys ~8 days of look-ahead because
FINRA disseminates about a week after the position date.
"""
from __future__ import annotations

import logging

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# Authority contract, read by the surface layer and asserted in tests.
AUTHORITY = {"tier": "display", "confidence_class": "descriptive",
             "may_rank": False, "may_size": False, "may_gate": False}

DTC_SENTINEL = 999.0
# Absolute fee thresholds, NOT percentiles — see trap 3 in the module docstring.
FEE_HTB_PCT = 1.0             # at/above this a name has stopped being general collateral
FEE_SEVERE_PCT = 5.0          # at/above this borrowing is genuinely scarce
MIN_CROSS_SECTION = 200       # below this the percentiles are not worth printing
# A ticker whose newest knowable settlement is older than this (settlements are
# bi-monthly, so ~45d spans two) has stopped being reported — delisted, renamed,
# or dropped. It is absent, not current. See asof_slice.
MAX_STALE_DAYS = 45

# Days-to-cover is short_shares / ADV. When ADV is tiny the ratio explodes into
# numbers that LOOK like extreme short pressure and are pure division artifact.
# Measured on the 2026-07-15 listed cross-section: of the 75 names with DTC >= 50,
# ALL 75 have ADV under 100k and their MEDIAN ADV is 36 shares a day. Restrict to
# ADV >= 100k and the distribution becomes sane — p50 2.94, p99 16.1, max 38.8.
# This trap is nastier than the 999.99 sentinel: the sentinel announces itself,
# these are plausible-looking numbers that would top any "most shorted" ranking.
MIN_ADV_SHARES = 100_000

_SI_PANEL = ("finra", "short_interest_panel.parquet")



def _read(group: str, fname: str) -> pd.DataFrame | None:
    p = config.data_dir() / group / fname
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("short_pressure: cannot read %s (%s)", p, e)
        return None


def load_si_panel() -> pd.DataFrame | None:
    return _read(*_SI_PANEL)


def load_borrow_panel() -> pd.DataFrame | None:
    """Per-date IBKR captures, concatenated. Reads only the trailing window — a
    display surface needs the latest snapshot, not years of borrow history."""
    from collectors import ibkr_borrow
    df = ibkr_borrow.load_panel(since=pd.Timestamp.today() - pd.Timedelta(days=30))
    return df if df is not None and not df.empty else None


def asof_slice(panel: pd.DataFrame, asof=None, max_stale_days: int = MAX_STALE_DAYS) -> pd.DataFrame:
    """Rows KNOWABLE at `asof` — the newest settlement per ticker whose
    `knowable_date` has passed. This is the only PIT-correct way to read the
    panel; `settlement_date` is the position date, not the publication date.

    STALENESS. "Newest settlement per ticker" alone is not enough: over an 8.5-year
    panel it resurrects every ticker that ever reported. Measured at asof
    2026-08-01 that returned 48,539 names when the newest settlement carries only
    ~22k — the difference is delisted and renamed symbols surfacing with readings
    years old, presented as current. Rows older than `max_stale_days` before the
    newest knowable settlement are dropped: a name that has stopped being reported
    is absent, not stale-but-live.
    """
    if panel is None or panel.empty:
        return pd.DataFrame()
    df = panel
    if asof is not None:
        cutoff = pd.Timestamp(asof)
        if "knowable_date" not in df.columns:
            raise KeyError("short_pressure: panel has no knowable_date — rebuild it "
                           "with scripts/backfill_finra_short_interest.py; joining on "
                           "settlement_date would be look-ahead")
        df = df[pd.to_datetime(df["knowable_date"]) <= cutoff]
    if df.empty:
        return df
    latest = (df.sort_values("settlement_date")
                .drop_duplicates(subset=["ticker"], keep="last"))
    newest = latest["settlement_date"].max()
    fresh = latest[latest["settlement_date"] >= newest - pd.Timedelta(days=max_stale_days)]
    return fresh.set_index("ticker")


def _thin_adv(snap: pd.DataFrame) -> pd.Series:
    """Names whose average daily volume is too small for days-to-cover to mean
    anything (trap 3). Missing ADV counts as thin — unknown liquidity cannot
    license a liquidity-normalised statistic."""
    if "avg_daily_vol" not in snap.columns:
        return pd.Series(False, index=snap.index)
    return ~(snap["avg_daily_vol"] >= MIN_ADV_SHARES).fillna(False)


def _pctile_basis(snap: pd.DataFrame) -> pd.Series:
    """Days-to-cover restricted to the rows a percentile may legitimately use:
    exchange-listed, not sentinel-capped, and liquid enough for the ratio to
    carry meaning (traps 1, 2 and 3)."""
    ok = snap["days_to_cover"].notna()
    if "is_listed" in snap.columns:
        ok &= snap["is_listed"].fillna(False)
    if "dtc_capped" in snap.columns:
        ok &= ~snap["dtc_capped"].fillna(False)
    else:
        ok &= snap["days_to_cover"] < DTC_SENTINEL
    ok &= ~_thin_adv(snap)
    return snap.loc[ok, "days_to_cover"]


def cross_section(asof=None, si_panel: pd.DataFrame | None = None,
                  borrow: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-ticker short-pressure axes as of `asof`. One row per ticker, one
    COLUMN per axis. Deliberately returns no summary column."""
    snap = asof_slice(si_panel if si_panel is not None else load_si_panel(), asof)
    if snap.empty:
        return pd.DataFrame()

    out = pd.DataFrame(index=snap.index)
    out["days_to_cover"] = snap["days_to_cover"].where(~snap.get("dtc_capped", False).fillna(False))
    out["dtc_capped"] = snap.get("dtc_capped", False)
    out["thin_adv"] = _thin_adv(snap)
    out["avg_daily_vol"] = snap.get("avg_daily_vol")
    out["si_change_pct"] = snap.get("si_change_pct")
    out["short_shares"] = snap.get("short_shares")
    out["settlement_date"] = snap.get("settlement_date")

    basis = _pctile_basis(snap)
    if len(basis) >= MIN_CROSS_SECTION:
        ranks = basis.rank(pct=True) * 100.0
        out["dtc_pctile"] = ranks.reindex(out.index).round(1)
    else:
        # Abstain rather than print a percentile computed on a thin cross-section.
        out["dtc_pctile"] = pd.NA
        log.info("short_pressure: %d usable rows < %d — dtc_pctile abstained",
                 len(basis), MIN_CROSS_SECTION)

    # days-to-cover CHANGE — newly computable now that a real panel exists. It
    # was listed as "raw ingredient only" because the store held 2 settlements.
    full = si_panel if si_panel is not None else load_si_panel()
    out["dtc_change"] = _dtc_change(full, snap, asof)

    # Borrow columns ALWAYS exist, null when there is no capture at/before `asof`
    # (the accrual starts 2026-08-05, so every historical date has none). Dropping
    # the columns instead would make every consumer AttributeError on exactly the
    # dates the panel is meant to support — absent data must read as null, not as
    # a missing schema.
    out["borrow_fee_pct"] = pd.NA
    out["borrow_htb"] = False
    out["borrow_severe"] = False
    out["avail_shares"] = pd.NA
    out["avail_unlimited"] = False

    bp = borrow if borrow is not None else load_borrow_panel()
    fee = _latest_borrow(bp, asof)
    if fee is not None and not fee.empty:
        out["borrow_fee_pct"] = pd.to_numeric(fee["fee_pct"].reindex(out.index), errors="coerce")
        out["borrow_htb"] = (out["borrow_fee_pct"] >= FEE_HTB_PCT).fillna(False)
        out["borrow_severe"] = (out["borrow_fee_pct"] >= FEE_SEVERE_PCT).fillna(False)
        out["avail_shares"] = fee["avail_shares"].reindex(out.index)
        out["avail_unlimited"] = fee["avail_unlimited"].reindex(out.index).fillna(False)
    return out


def _dtc_change(full: pd.DataFrame | None, snap: pd.DataFrame, asof) -> pd.Series:
    """Change in days-to-cover between the two most recent KNOWABLE settlements.
    Returns NaN where either endpoint is missing or sentinel-capped — a change
    computed against a 999.99 sentinel is a fiction, not a large move."""
    empty = pd.Series(index=snap.index, dtype=float)
    if full is None or full.empty or "knowable_date" not in full.columns:
        return empty
    df = full
    if asof is not None:
        df = df[pd.to_datetime(df["knowable_date"]) <= pd.Timestamp(asof)]
    if df.empty:
        return empty
    dates = sorted(df["settlement_date"].unique())
    if len(dates) < 2:
        return empty
    prev = df[df["settlement_date"] == dates[-2]].set_index("ticker")
    cur_dtc = snap["days_to_cover"].where(~snap.get("dtc_capped", False).fillna(False))
    prev_dtc = prev["days_to_cover"].where(~prev.get("dtc_capped", False).fillna(False))
    return (cur_dtc - prev_dtc.reindex(snap.index)).astype(float)


def _latest_borrow(bp: pd.DataFrame | None, asof) -> pd.DataFrame | None:
    """Most recent borrow snapshot at/before `asof`. The IBKR feed is captured
    same-day and never revised, so its own date needs no publication lag."""
    if bp is None or bp.empty:
        return None
    df = bp
    if asof is not None:
        df = df[pd.to_datetime(df["date"]) <= pd.Timestamp(asof)]
    if df.empty:
        return None
    return (df.sort_values("date").drop_duplicates(subset=["ticker"], keep="last")
              .set_index("ticker"))


def axes(ticker: str, asof=None, xs: pd.DataFrame | None = None) -> dict | None:
    """Printed legs for one name. Returns each axis with its own value and a
    plain-word reading. NO combined number, NO stance, NO recommendation.

    `agree_count` counts how many axes independently point the same way. It is a
    COUNT of printed legs, not a score: it is not weighted, not fitted, carries
    no authority, and is explicitly ungraded until SP1 reads out.
    """
    x = xs if xs is not None else cross_section(asof)
    if x is None or x.empty or ticker not in x.index:
        return None
    r = x.loc[ticker]

    legs: list[dict] = []

    def add(key, value, reading, elevated):
        legs.append({"axis": key, "value": value, "reading": reading,
                     "elevated": bool(elevated) if elevated is not None else None})

    dtc = _f(r.get("days_to_cover"))
    pct = _f(r.get("dtc_pctile"))
    if dtc is None:
        add("days_to_cover", None,
            "no usable reading — average volume too low to measure" if _b(r.get("dtc_capped"))
            else "not reported", None)
    elif _b(r.get("thin_adv")):
        # The number exists but means nothing: short_shares over a near-zero ADV.
        # `elevated=None` (unmeasurable), never True — this is the whole reason
        # the extreme tail of days-to-cover is an artifact rather than a signal.
        add("days_to_cover", round(dtc, 2),
            f"{dtc:.1f} days on paper, but volume is too thin for that to mean anything",
            None)
    else:
        add("days_to_cover", round(dtc, 2),
            f"{dtc:.1f} days of average volume to buy back"
            # capped at 99 BEFORE formatting: min(100, 99.9) still renders "100"
            # under %.0f, and "higher than 100% of names" is never true of a name
            # that is itself in the comparison set.
            + (f", higher than {min(pct, 99.0):.0f}% of comparable names" if pct is not None else ""),
            pct is not None and pct >= 80)

    chg = _f(r.get("dtc_change"))
    add("dtc_change", None if chg is None else round(chg, 2),
        "no prior settlement to compare" if chg is None else
        (f"cover burden up {chg:+.1f} days since the last report" if chg > 0
         else f"cover burden down {chg:+.1f} days since the last report"),
        chg is not None and chg > 0)

    sic = _f(r.get("si_change_pct"))
    add("si_change_pct", None if sic is None else round(sic, 2),
        "not reported" if sic is None else
        f"shares short {'up' if sic > 0 else 'down'} {abs(sic):.1f}% since the last report",
        sic is not None and sic > 0)

    fee = _f(r.get("borrow_fee_pct"))
    if fee is None:
        add("borrow_fee", None, "no borrow quote", None)
    elif fee >= FEE_SEVERE_PCT:
        add("borrow_fee", round(fee, 2), f"expensive to borrow at {fee:.1f}% a year", True)
    elif fee >= FEE_HTB_PCT:
        add("borrow_fee", round(fee, 2), f"costs {fee:.1f}% a year to borrow — above ordinary", True)
    else:
        add("borrow_fee", round(fee, 2), f"ordinary to borrow at {fee:.2f}% a year", False)

    av = _f(r.get("avail_shares"))
    add("availability", av,
        "lending supply not scarce" if _b(r.get("avail_unlimited")) or av is None
        else f"{av:,.0f} shares available to borrow", None)

    elevated = [l for l in legs if l["elevated"] is True]
    measured = [l for l in legs if l["elevated"] is not None]
    return {
        "ticker": ticker,
        "legs": legs,
        "agree_count": len(elevated),
        "measured_count": len(measured),
        "coverage_ok": len(measured) >= 2,
        "state": _state(len(elevated), len(measured)),
        "authority": dict(AUTHORITY),
        # The standing honesty line. Every surface renders this next to the legs.
        "grading_note": ("These readings are described, not scored. Whether they "
                         "predict anything here is being measured forward and has "
                         "not been answered yet."),
        "settlement_date": (str(pd.Timestamp(r["settlement_date"]).date())
                            if pd.notna(r.get("settlement_date")) else None),
    }


def _state(n_elev: int, n_meas: int) -> str:
    """Plain-word STATE, never a stance. No 'squeeze', no buy/sell verb — the
    axes are ungraded, so a directional verb here would be an uncomputed claim."""
    if n_meas < 2:
        return "not enough short-side data to describe"
    if n_elev == 0:
        return "short positioning is unremarkable"
    if n_elev == 1:
        return "one short-side reading stands out"
    return f"{n_elev} short-side readings stand out together"


def _f(v):
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _b(v) -> bool:
    try:
        return bool(v) and not pd.isna(v)
    except (TypeError, ValueError):
        return False
