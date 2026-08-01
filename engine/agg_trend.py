"""Aggregate greek trend — the whole book's dealer exposure, one number per session.

Program of record: charting-app ``docs/VOLLAND_PARITY_PLAN_2026-08-01.md`` §5 (W2)
and ``docs/MARKET_STRUCTURE_CORE_MASTERPLAN_2026-08-01.md``.

What this is
------------
``engine/options_hub.compute_gex`` answers "where is exposure concentrated **today**".
This answers "how big is it **relative to its own history**" — the question a single
session can never answer. A −$6bn net gamma print means nothing until you know the
book has run between −$18bn and +$9bn over nine years.

Volland ships this as "Aggregate Greek Trend" over roughly five to six months of
history. We hold ThetaData EOD greeks and open interest from **2017**, so the same
chart over the same math covers multiple volatility regimes — 2018's Volmageddon,
2020, 2022 — instead of one. That depth is the advantage; the chart is parity.

Method
------
For every session ``d`` in the greeks store:

1. join greeks[d] to open interest[d] on (expiration, strike, right);
2. keep contracts with OI > 0 — the same filter ``compute_gex`` applies;
3. price every row at **that session's own spot**, never today's;
4. convert to dealer dollars via :func:`engine.exposure_math.dealer_exposures`;
5. sum across the whole book.

Step 3 is the one that is easy to get wrong and impossible to see afterwards: a
gamma series computed with a fixed spot drifts with the level of the index rather
than the positioning, and looks entirely plausible while doing it.

OI timing law
-------------
The OI parquet for session ``d`` is what OPRA reports for ``d``, which represents
end-of-``d-1`` positions. Joining greeks[d] to oi[d] is therefore already the
"greeks today, positions as of last night" pairing the hub uses — no extra shift.

Honesty
-------
Tier B (``docs/MARKET_STRUCTURE_CORE_MASTERPLAN_2026-08-01.md`` §4.1): the dealer
sign convention is an assumption, so the *level* is a model output. The *shape*
over time — where today sits in its own distribution — is far more robust than the
level, because the sign assumption is constant across the series and cancels in the
percentile. Consumers should lead with the percentile, not the dollar figure.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.exposure_math import EXPOSURE_UNITS, dealer_exposures, usable_quote

log = logging.getLogger(__name__)

__all__ = [
    "GREEKS",
    "SCHEMA",
    "GREEK_COLUMNS",
    "daily_aggregates",
    "build_trend_payload",
    "merge_history",
]

SCHEMA = "options_hub.aggtrend/v1"

#: Greeks published in the trend, in the order the Terminal offers them.
GREEKS = ("gamma", "delta", "vanna", "charm", "vega")

#: Compact per-greek series keys. The payload ships one row per session per root;
#: short keys keep a nine-year SPY series around 100KB rather than 300KB.
GREEK_COLUMNS = {
    "gamma": "g",
    "delta": "dl",
    "vanna": "vn",
    "charm": "ch",
    "vega": "vg",
}

#: Columns read from the greeks store. Selecting explicitly keeps a 170MB year
#: parquet from expanding into gigabytes of unused higher-order greeks.
_GREEK_READ_COLS = [
    "expiration", "strike", "right", "date", "underlying_price",
    "implied_vol", "delta", "gamma", "vanna", "charm", "vega",
]

_OI_READ_COLS = ["expiration", "strike", "right", "date", "open_interest"]

#: ATM band for the session IV summary — ±5% of spot, the same width the vol
#: payload's 30-day ATM uses.
_ATM_BAND = 0.05


def _normalise_dates(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("date", "expiration"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.date.astype(str)
    return out


def daily_aggregates(greeks: pd.DataFrame, oi: pd.DataFrame) -> pd.DataFrame:
    """One row per session: whole-book dealer exposure in dollars.

    Parameters
    ----------
    greeks, oi : pandas.DataFrame
        Multi-session frames from the ThetaData EOD store. Both must carry
        ``date``/``expiration``/``strike``/``right``; ``greeks`` additionally
        carries ``underlying_price`` and the per-share greeks.

    Returns
    -------
    pandas.DataFrame
        Indexed 0..n, columns ``date, spot, n_contracts, oi_total, atm_iv`` and
        one dollar column per greek in :data:`GREEKS`. Empty inputs give an empty
        frame with the right columns rather than raising — this runs unattended
        across 400 roots and one bad root must not sink the batch.
    """
    cols = ["date", "spot", "n_contracts", "oi_total", "atm_iv", *GREEKS]
    if greeks is None or greeks.empty or oi is None or oi.empty:
        return pd.DataFrame(columns=cols)

    g = _normalise_dates(greeks)
    o = _normalise_dates(oi)
    if "date" not in g.columns or "date" not in o.columns:
        return pd.DataFrame(columns=cols)

    g["strike"] = pd.to_numeric(g["strike"], errors="coerce")
    o["strike"] = pd.to_numeric(o["strike"], errors="coerce")
    g["right"] = g["right"].astype(str).str.upper()
    o["right"] = o["right"].astype(str).str.upper()

    o = o[["date", "expiration", "strike", "right", "open_interest"]]
    m = g.merge(o, on=["date", "expiration", "strike", "right"], how="inner")
    m["open_interest"] = pd.to_numeric(m["open_interest"], errors="coerce").fillna(0.0)
    # Data-quality gate, shared with compute_gex: positive open interest and a
    # real implied vol. See engine/exposure_math.MIN_QUOTED_IV — a single 0DTE
    # at-the-money quote at iv=0.0001 was worth −$1.1tn of "hedging requirement"
    # before this existed, and a nine-year distribution is exactly where such an
    # outlier does the most damage: it sets the range every other day is read
    # against.
    m = m[usable_quote(
        pd.to_numeric(m.get("implied_vol", np.nan), errors="coerce"),
        m["open_interest"],
    )]
    if m.empty:
        return pd.DataFrame(columns=cols)

    # Session spot: the median underlying_price across the chain. A chain carries
    # one print per contract and they agree, but the median is immune to a single
    # bad row in a way that .iloc[0] is not.
    spot_by_date = (
        m.groupby("date")["underlying_price"].median().rename("spot")
    )
    m = m.merge(spot_by_date, on="date", how="left")
    m = m[np.isfinite(m["spot"]) & (m["spot"] > 0)]
    if m.empty:
        return pd.DataFrame(columns=cols)

    supplied = {
        name: pd.to_numeric(m[name], errors="coerce").to_numpy(float)
        for name in GREEKS
        if name in m.columns
    }
    exposures = dealer_exposures(
        is_call=(m["right"] == "C").to_numpy(),
        oi=m["open_interest"].to_numpy(float),
        spot=m["spot"].to_numpy(float),
        **supplied,
    )
    for name, arr in exposures.items():
        m[f"_x_{name}"] = arr

    agg_spec: dict[str, tuple[str, str]] = {
        "spot": ("spot", "first"),
        "n_contracts": ("open_interest", "size"),
        "oi_total": ("open_interest", "sum"),
    }
    for name in exposures:
        agg_spec[name] = (f"_x_{name}", "sum")

    out = m.groupby("date", as_index=False).agg(**agg_spec)

    # ATM IV per session — the ±5% band's median implied vol. Included because the
    # spot-vol relationship cards need vol and spot from the SAME source frame;
    # taking IV from a second store would let the two disagree by a session.
    if "implied_vol" in m.columns:
        atm = m[(m["strike"] / m["spot"] - 1.0).abs() <= _ATM_BAND]
        iv = (
            atm.groupby("date")["implied_vol"].median().rename("atm_iv").reset_index()
            if not atm.empty
            else pd.DataFrame(columns=["date", "atm_iv"])
        )
        out = out.merge(iv, on="date", how="left")
    else:
        out["atm_iv"] = np.nan

    for name in GREEKS:
        if name not in out.columns:
            out[name] = np.nan
    out = out.sort_values("date").reset_index(drop=True)
    return out[cols]


def merge_history(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """Union two aggregate frames, newer rows winning on a date collision.

    Incremental rebuilds re-derive the tail (open interest for recent sessions can
    still be revised), so the new frame is authoritative wherever the two overlap.
    """
    if old is None or old.empty:
        return new.sort_values("date").reset_index(drop=True)
    if new is None or new.empty:
        return old.sort_values("date").reset_index(drop=True)
    both = pd.concat([old, new], ignore_index=True)
    both = both.drop_duplicates(subset=["date"], keep="last")
    return both.sort_values("date").reset_index(drop=True)


def _stats(values: np.ndarray) -> dict | None:
    """Distribution summary for one greek's full history, plus today's percentile."""
    v = values[np.isfinite(values)]
    if v.size < 2:
        return None
    last = float(values[-1]) if np.isfinite(values[-1]) else None
    pctile = float((v < values[-1]).mean() * 100.0) if last is not None else None
    return {
        "mean": round(float(v.mean()), 4),
        "sd": round(float(v.std(ddof=1)), 4),
        "min": round(float(v.min()), 4),
        "p05": round(float(np.percentile(v, 5)), 4),
        "p50": round(float(np.percentile(v, 50)), 4),
        "p95": round(float(np.percentile(v, 95)), 4),
        "max": round(float(v.max()), 4),
        "last": round(last, 4) if last is not None else None,
        "pctile": round(pctile, 1) if pctile is not None else None,
        "n": int(v.size),
    }


def build_trend_payload(df: pd.DataFrame, root: str, asof: str) -> dict:
    """Render the aggregate frame into the published ``options_hub.aggtrend/v1``.

    Series values are **$bn**; ``spot`` is a price and ``atm_iv`` a fraction.
    ``stats`` summarises the FULL series per greek, so the Terminal can draw a
    historical-average reference and state today's percentile without shipping a
    second pass over the data.
    """
    if df is None or df.empty:
        return {
            "schema": SCHEMA,
            "asof": asof,
            "root": root,
            "since": None,
            "n_days": 0,
            "units": {g: EXPOSURE_UNITS[g] for g in GREEKS},
            "series": [],
            "stats": {},
        }

    d = df.sort_values("date").reset_index(drop=True)
    series: list[dict] = []
    for row in d.itertuples():
        rec: dict[str, object] = {"d": row.date}
        spot = getattr(row, "spot", None)
        if spot is not None and np.isfinite(spot):
            rec["s"] = round(float(spot), 4)
        iv = getattr(row, "atm_iv", None)
        if iv is not None and np.isfinite(iv):
            rec["iv"] = round(float(iv), 4)
        for greek, key in GREEK_COLUMNS.items():
            val = getattr(row, greek, None)
            if val is not None and np.isfinite(val):
                rec[key] = round(float(val) / 1e9, 4)
        series.append(rec)

    stats = {}
    for greek in GREEKS:
        if greek in d.columns:
            s = _stats(d[greek].to_numpy(float) / 1e9)
            if s is not None:
                stats[greek] = s

    return {
        "schema": SCHEMA,
        "asof": asof,
        "root": root,
        "since": str(d["date"].iloc[0]),
        "n_days": int(len(d)),
        "units": {g: EXPOSURE_UNITS[g] for g in GREEKS},
        "series": series,
        "stats": stats,
    }


def cache_path(cache_dir: str | Path, root: str) -> Path:
    return Path(cache_dir) / f"{root.upper()}.parquet"


def read_cache(cache_dir: str | Path, root: str) -> pd.DataFrame | None:
    p = cache_path(cache_dir, root)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:  # noqa: BLE001
        log.warning("agg_trend: unreadable cache %s — %s", p, exc)
        return None


def write_cache(cache_dir: str | Path, root: str, df: pd.DataFrame) -> Path:
    p = cache_path(cache_dir, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(p, index=False)
    return p
