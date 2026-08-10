"""engine.price_pressure.detect — residual shocks, harvested through the LSR seam.

Every number here comes out of ``engine.price_pressure.panel``'s re-export of
``scripts/research_liquidity_shock_reversal``:

    resid    = ret − sector_ex_self_peer(ret)          (LSR ``derive``)
    resid_z  = resid / rolling60σ(resid).shift(1)      (LSR ``derive``)
    eligible = ¬split_day ∧ close ≥ $5 ∧ ADVmed ≥ $5M ∧ σ known
    shock    = |resid_z| ≥ 3 ∧ volume ≥ 2× trailing median

The only construction this module ADDS is the t+60 ledger tail, and it is read
off LSR's OWN cumulative frame (``d["cum"]``, the log1p-residual cumsum) exactly
the way ``derive`` builds its t+1..t+21 horizons — an extension of the same
object, not a second definition of it.

`sd_t0` (the t0 residual σ) is recovered from the harvested row as
``resid / resid_z``: algebra on two frozen PIT columns rather than a second
rolling-σ pipeline that could drift from the first.

The other addition is ``peer_basis_mask`` — metadata about which BRANCH the LSR
peer helper took per cell, not a second peer construction (see its docstring).
Row order out of ``harvest`` is ascending (date, ticker, side) for storage
stability; the recency-first DISPLAY order (§9, review finding 11) is applied
where lists are emitted, never here.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure import panel as _panel
from engine.price_pressure.panel import (
    MIN_ADV_EVENT,
    MIN_PRICE,
    VOL_TRIGGER,
    Z_TRIGGER,
    derive,
    harvest_events,
)

log = logging.getLogger("price_pressure.detect")

#: Breadth companion threshold — the share of the eligible cross-section moving
#: |resid_z| ≥ 2 on a date.  A NUMBER, not a label: the ledger stores no shock
#: vocabulary at all (DNR:KILL-PARALLEL-SHOCK-CLASSIFIER).
BREADTH_Z = 2.0

#: The ledger tail beyond LSR's native horizons (masterplan §5).
TAIL_HORIZON = 60


def derive_frames(panel: dict[str, pd.DataFrame], data_dir: Path) -> dict:
    """LSR ``derive`` plus the t+60 tail. Returns LSR's own dict, extended.

    Extra keys: ``fwd[60]`` and ``sessions`` (the panel's DatetimeIndex).
    """
    d = derive(panel, Path(data_dir), min_price=MIN_PRICE, min_adv_event=MIN_ADV_EVENT)
    cum = d["cum"]
    d["fwd"][TAIL_HORIZON] = cum.shift(-TAIL_HORIZON) - cum
    d["sessions"] = pd.DatetimeIndex(cum.index)
    return d


def breadth_by_date(d: dict) -> pd.DataFrame:
    """Per-date panel breadth NUMBERS: eligible names, |z|≥2 share, shock count.

    ``panel_shock_count`` counts eligible names firing the full shock fence (both
    sides) on that date — the mechanical broad-selloff marker's raw input.  No
    day gets a name here; naming happens (fail-open) in the artifact, out of
    ``market_drivers`` vocabulary.
    """
    z, av, elig = d["f"]["resid_z"], d["f"]["abn_volume"], d["eligible"]
    zabs = z.abs()
    n_elig = elig.sum(axis=1)
    shock = elig & (zabs >= Z_TRIGGER) & (av >= VOL_TRIGGER)
    wide = elig & (zabs >= BREADTH_Z)
    out = pd.DataFrame({
        "panel_eligible_count": n_elig.astype("float64"),
        "panel_shock_count": shock.sum(axis=1).astype("float64"),
        "panel_share_z2": (wide.sum(axis=1) / n_elig.replace(0, np.nan)).astype("float64"),
    })
    out.index.name = "date"
    return out


def peer_basis_mask(d: dict, sectors: pd.Series, min_peers: int = 4) -> pd.DataFrame:
    """True where LSR's peer helper used the SECTOR ex-self value, False = market.

    ``sector_ex_self_peer`` silently backfills unlabelled names — and labelled
    names with fewer than ``min_peers`` priced sector peers — with the
    whole-universe mean.  On this panel that is ≥65% of names (§4.1), so an
    event row saying "peers implied −2.1%" would be false for most of the
    ledger.  This reproduces the helper's BRANCH CONDITION (not its arithmetic)
    so every row can disclose ``peer_basis``; ``tests/test_price_pressure.py``
    pins the reproduction by asserting that every False cell's peer value equals
    the whole-universe mean exactly, against the helper's own output.
    """
    ret = d["f"]["ret"]
    out = pd.DataFrame(False, index=ret.index, columns=ret.columns)
    lab = sectors.reindex(ret.columns).dropna()
    if lab.empty:
        return out
    for names in lab.groupby(lab).groups.values():
        names = list(names)
        n = ret[names].notna().sum(axis=1).to_numpy()
        out.loc[:, names] = np.repeat((n >= min_peers)[:, None], len(names), axis=1)
    return out & ret.notna()


def peer_shock_by_date(d: dict, sectors: pd.Series) -> pd.DataFrame:
    """Same-sector shock COUNT per (date, sector) — a plain co-move fact.

    Peer exhaustion/diffusion *mechanisms* are killed as signals
    (DNR:KILL-PSS-SR1/SR2/SR3); this is the count only, stored for context.
    """
    z, av, elig = d["f"]["resid_z"], d["f"]["abn_volume"], d["eligible"]
    shock = elig & (z.abs() >= Z_TRIGGER) & (av >= VOL_TRIGGER)
    lab = sectors.reindex(shock.columns)
    frames = {}
    for sec, names in lab.dropna().groupby(lab.dropna()).groups.items():
        frames[str(sec)] = shock[list(names)].sum(axis=1).astype("float64")
    if not frames:
        return pd.DataFrame(index=shock.index)
    out = pd.DataFrame(frames)
    out.index.name = "date"
    return out


def _empty_harvest(d: dict) -> pd.DataFrame:
    """The harvest frame's shape with zero rows.

    ``harvest_events`` was written for a five-year panel that always fires
    something, so its trailing ``pd.concat`` raises "No objects to concatenate"
    on a quiet window.  The research script is frozen, so the empty case is
    handled HERE rather than by editing it.
    """
    cols = ["date", "ticker", "side", *d["f"].keys(),
            *(f"fwd{h}" for h in d["fwd"])]
    out = pd.DataFrame({c: pd.Series(dtype="object" if c in ("ticker", "side") else "float64")
                        for c in cols})
    out["date"] = pd.Series(dtype="datetime64[ns]")
    return out


def harvest(d: dict, *, window: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """Every ±3σ high-volume shock (LSR ``harvest_events``), optionally windowed.

    The harvest runs over the WHOLE derived frame and is then filtered by date,
    so a nightly increment and the historical backfill produce byte-identical
    rows for any date they share — the parity the frozen base rates depend on.
    """
    try:
        ev = harvest_events(d)
    except ValueError:            # zero shocks anywhere — see _empty_harvest
        ev = _empty_harvest(d)
        ev["resid_sd"] = pd.Series(dtype="float64")
        return ev
    ev["date"] = pd.to_datetime(ev["date"])
    if window is not None and len(window):
        keep = set(pd.DatetimeIndex(window).normalize())
        ev = ev[ev["date"].dt.normalize().isin(keep)]
    ev = ev.sort_values(["date", "ticker", "side"], kind="stable").reset_index(drop=True)
    # sd_t0: algebra on the two frozen columns, never a second σ pipeline.
    with np.errstate(divide="ignore", invalid="ignore"):
        ev["resid_sd"] = ev["resid"] / ev["resid_z"].replace(0, np.nan)
    return ev


def eligible_mask(d: dict) -> pd.DataFrame:
    """The LSR eligibility fence, exposed for tests and coverage reporting."""
    return d["eligible"]


def constants() -> dict:
    """The frozen design constants, for the artifact's provenance block."""
    return {
        "z_trigger": float(Z_TRIGGER),
        "vol_trigger": float(VOL_TRIGGER),
        "min_price_usd": float(MIN_PRICE),
        "min_adv_event_usd": float(MIN_ADV_EVENT),
        "base_window_d": int(_panel.BASE_WIN),
        "news_window_calendar_days": int(_panel.NEWS_WINDOW_DAYS),
        "residual_basis": "equal-weighted same-sector ex-self peer return (LSR-P0)",
        "source": "scripts/research_liquidity_shock_reversal.py (imported, not copied)",
    }
