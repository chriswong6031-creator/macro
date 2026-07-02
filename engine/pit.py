"""Point-in-time (PIT) truth-layer accessor — audit #5 #14 #16 #39, masterplan W1a.

The live feature frame (engine/inputs.py) stamps every FRED series on its native
*reference* index (the month/week the data describes) and forward-fills. For monthly
econ prints that publish weeks later, this bakes a look-ahead into every historical
row: the growth/inflation axes "know" a payrolls or CPI print on the 1st of the month
when it was not published until ~the first Friday of the *next* month (#5, timing
leak), and they read the *latest-revised* value rather than the number that was on the
screen at the time (#14, revision leak).

This module is the SHADOW accessor that produces a leak-free frame. It never touches
the live path. `series(name, as_of, basis)` returns a daily business-day series a
real-money backtest can trust as genuinely as-of:

  basis='reference'  -> current live behaviour: native reference stamping, ffill.
                        Byte-identical to inputs.put() for the same series. The
                        control leg for the leakage-tax diff.
  basis='latest'     -> latest-revised finals, reference-stamped, ffill. (Same
                        numbers as 'reference' for the local store — the store only
                        keeps revised finals — but the accessor keeps the axis
                        distinct so a future revised-vs-initial study can split them.)
  basis='release'    -> the LEAK-FREE frame. For each historical business day d it
                        carries the value that was actually AVAILABLE on d:
                          * vintaged series (ALFRED matrix): the latest vintage whose
                            realtime_start <= d (initial release, revision-free), via
                            an as-of join on realtime_start. A period is never visible
                            before it was first published.
                          * non-vintaged series: the reference-stamped value shifted
                            forward to its MODELLED release date (static schedule
                            priors in config `pit.release_lags`, documented per series;
                            learned lags accrue via engine.pit_lag_recorder).

Design invariants (see tests/test_pit_accessor.py):
  * A value is NEVER visible on the release frame before its realtime_start (vintaged)
    or its modelled release date (non-vintaged). This is the whole point.
  * The 'reference' basis reproduces inputs.put() exactly (backward-compat control).
  * No fork of the axis math: engine.inputs.build_features(pit_basis=..., pit_as_of=...)
    routes the *same* put() through this accessor, so axes/regime run unchanged.
"""
from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

Basis = Literal["release", "reference", "latest"]

# --------------------------------------------------------------------------- #
# FRED series-id <-> live-frame column, and which live columns each vintaged
# series feeds. The vintage matrix is keyed by FRED series-id (PAYEMS, ...); the
# live frame and the release-lag calendar are keyed by column name (payrolls,...).
# --------------------------------------------------------------------------- #
# ALFRED-vintaged FRED series present (or expected) in data/fred_vintage/vintages.parquet,
# mapped to the live-frame column engine/inputs.py stamps them into. Only the
# revision-prone econ prints are vintaged — market data (rates/OAS/VIX/FX) is never
# revised and is deliberately excluded (collectors/fred.DEFAULT_VINTAGE_SERIES).
VINTAGED_SID_TO_COL: dict[str, str] = {
    "PAYEMS": "payrolls",
    "INDPRO": "indpro",              # also feeds industrial_prod alias
    "M2SL": "us_m2",
    "WEI": "wei",
    "GDPNOW": "gdpnow",
    "RECPROUSM156N": "recession_prob",
    "THREEFYTP10": "term_premium_10y",
    "SAHMREALTIME": "sahm",
    "STICKCPIM157SFRBATL": "sticky_cpi",
    "CORESTICKM157SFRBATL": "core_sticky_cpi",
    "FLEXCPIM157SFRBATL": "flex_cpi",
    "MEDCPIM158SFRBCLE": "median_cpi",
    "CPIAUCSL": "headline_cpi",
    "CPILFESL": "core_cpi",
    "PCEPI": "headline_pce",
    "PCEPILFE": "core_pce",
    "PPIFIS": "ppi_final_demand",
    "PPIFES": "ppi_core",
    "ECIALLCIV": "eci_comp",
    "ECIWAG": "eci_wages",
    "STLFSI4": "stlfsi",
    "UMCSENT": "umich_sentiment",
    "MICH": "umich_infl_exp",
    "ICSA": "initial_claims",
    "IC4WSA": "initial_claims_4wk",
    "CCSA": "continued_claims",
}
COL_TO_VINTAGED_SID: dict[str, str] = {c: s for s, c in VINTAGED_SID_TO_COL.items()}

# --------------------------------------------------------------------------- #
# Static release-lag priors (business days from the reference-period END to the
# modelled first-release date). Used by the 'release' basis for NON-vintaged
# series, and as the documented fallback bound. Each entry is a defensible prior;
# learned lags (engine.pit_lag_recorder) refine these going forward.
#
# lag_bd  : business days after reference-period end that the print publishes.
# cadence : reference cadence, informs where "period end" is anchored.
# note    : provenance of the prior.
# --------------------------------------------------------------------------- #
DEFAULT_RELEASE_LAGS: dict[str, dict] = {
    # --- monthly BLS/BEA/Fed econ prints (these ARE vintaged; lags here document
    #     the prior and serve as a fallback if a vintage row is missing) ---
    "payrolls":       {"lag_bd": 5,  "cadence": "M", "note": "BLS Employment Situation ~first Friday of following month (~3 bd after month end)"},
    "indpro":         {"lag_bd": 11, "cadence": "M", "note": "Fed G.17 Industrial Production ~day 15-17 of following month"},
    "headline_cpi":   {"lag_bd": 8,  "cadence": "M", "note": "BLS CPI ~day 10-13 of following month"},
    "core_cpi":       {"lag_bd": 8,  "cadence": "M", "note": "BLS CPI ~day 10-13 of following month"},
    "cpi_core_services": {"lag_bd": 8, "cadence": "M", "note": "BLS CPI detail, same release as CPI"},
    "cpi_shelter":    {"lag_bd": 8,  "cadence": "M", "note": "BLS CPI detail, same release as CPI"},
    "headline_pce":   {"lag_bd": 20, "cadence": "M", "note": "BEA Personal Income & Outlays ~day 26-30 of following month (~1 month lag)"},
    "core_pce":       {"lag_bd": 20, "cadence": "M", "note": "BEA PCE ~day 26-30 of following month; the Fed's target series"},
    "ppi_final_demand": {"lag_bd": 9, "cadence": "M", "note": "BLS PPI ~day 11-14 of following month (day before/after CPI)"},
    "ppi_core":       {"lag_bd": 9,  "cadence": "M", "note": "BLS PPI ~day 11-14 of following month"},
    "sticky_cpi":     {"lag_bd": 9,  "cadence": "M", "note": "Atlanta Fed sticky CPI, released with the BLS CPI it is built from"},
    "core_sticky_cpi": {"lag_bd": 9, "cadence": "M", "note": "Atlanta Fed core-sticky CPI, released with BLS CPI"},
    "flex_cpi":       {"lag_bd": 9,  "cadence": "M", "note": "Atlanta Fed flexible CPI, released with BLS CPI"},
    "median_cpi":     {"lag_bd": 9,  "cadence": "M", "note": "Cleveland Fed median CPI, released with/after BLS CPI"},
    "umich_sentiment": {"lag_bd": 0, "cadence": "M", "note": "UMich final ~end of reference month (prelim mid-month); conservative 0 bd after month end"},
    "umich_infl_exp": {"lag_bd": 0,  "cadence": "M", "note": "UMich inflation expectations, released with sentiment"},
    "sahm":           {"lag_bd": 5,  "cadence": "M", "note": "Sahm real-time rule, released with the unemployment rate (Employment Situation)"},
    "recession_prob": {"lag_bd": 45, "cadence": "M", "note": "NY Fed 12-mo-ahead recession prob, ~6-week publication lag on the reference month"},
    # --- quarterly ---
    "eci_comp":       {"lag_bd": 20, "cadence": "Q", "note": "BLS Employment Cost Index ~1 month after quarter end"},
    "eci_wages":      {"lag_bd": 20, "cadence": "Q", "note": "BLS ECI wages ~1 month after quarter end"},
    "gdpnow":         {"lag_bd": 0,  "cadence": "M", "note": "Atlanta Fed GDPNow nowcast, ~real-time (updated within days); 0 bd is a conservative bound"},
    # --- weekly ---
    "initial_claims":   {"lag_bd": 5,  "cadence": "W", "note": "DOL weekly jobless claims, Thursday for the week ending prior Saturday (~5 bd)"},
    "initial_claims_4wk": {"lag_bd": 5, "cadence": "W", "note": "4-week moving avg, same DOL release"},
    "continued_claims": {"lag_bd": 10, "cadence": "W", "note": "continued claims lag initial by one week (~1 extra week)"},
    "wei":            {"lag_bd": 4,  "cadence": "W", "note": "NY Fed Weekly Economic Index ~Thursday for the week ending prior Saturday"},
    "term_premium_10y": {"lag_bd": 3, "cadence": "D", "note": "ACM term premium, ~2-3 bd publication lag on daily data"},
    "stlfsi":         {"lag_bd": 6,  "cadence": "W", "note": "St. Louis Financial Stress Index, weekly ~Thursday for prior week"},
    "us_m2":          {"lag_bd": 20, "cadence": "M", "note": "Fed H.6 money stock ~4th Tuesday of following month"},
}


# --------------------------------------------------------------------------- #
# Config plumbing
# --------------------------------------------------------------------------- #
def _release_lags(use_learned: bool = True) -> dict[str, dict]:
    """Merge, in ascending precedence: static priors < learned lags (accrued by
    engine.pit_lag_recorder, keyed by FRED series-id) < config overrides (explicit,
    always win). Learned lags refine the coarse priors as the first-party release
    calendar accrues; they never silently override an explicit config value."""
    out = {k: dict(v) for k, v in DEFAULT_RELEASE_LAGS.items()}
    if use_learned:
        try:
            from engine.pit_lag_recorder import learned_lags
            learned = learned_lags(min_obs=6)  # need a few periods before trusting
            for sid, stat in learned.items():
                col = VINTAGED_SID_TO_COL.get(sid)
                if col is None:
                    continue
                med = stat.get("median_lag_days")
                if med is None:
                    continue
                # convert calendar-day median lag to a business-day lag prior (~5/7)
                out.setdefault(col, {})
                out[col]["lag_bd_learned"] = round(med * 5.0 / 7.0, 1)
                out[col]["n_learned_periods"] = stat.get("n_periods")
        except Exception:  # noqa: BLE001 — learned lags are best-effort
            pass
    try:
        cfg = config.load().get("pit", {}).get("release_lags", {}) or {}
    except Exception:  # noqa: BLE001 — config always loadable, but be defensive
        cfg = {}
    for k, v in cfg.items():
        out.setdefault(k, {}).update(v)
    return out


_VINTAGE_CACHE: dict[str, pd.DataFrame | None] = {}


def _vintages() -> pd.DataFrame | None:
    """Load and cache the ALFRED vintage matrix (idempotent within a process)."""
    if "df" not in _VINTAGE_CACHE:
        try:
            from collectors.fred import load_vintages
            _VINTAGE_CACHE["df"] = load_vintages()
        except Exception as e:  # noqa: BLE001
            log.warning("PIT: could not load vintages: %s", e)
            _VINTAGE_CACHE["df"] = None
    return _VINTAGE_CACHE["df"]


def clear_cache() -> None:
    """Drop the cached vintage frame (tests inject synthetic matrices)."""
    _VINTAGE_CACHE.clear()


def has_vintage(col: str, vintages: pd.DataFrame | None = None) -> bool:
    """True if the live-frame column `col` has ALFRED vintage coverage on disk."""
    sid = COL_TO_VINTAGED_SID.get(col)
    if sid is None:
        return False
    v = vintages if vintages is not None else _vintages()
    return bool(v is not None and not v.empty and (v["series"] == sid).any())


# --------------------------------------------------------------------------- #
# Availability construction
# --------------------------------------------------------------------------- #
def release_availability(col: str, vintages: pd.DataFrame | None = None) -> pd.Series:
    """The leak-free AVAILABILITY series for a live-frame column, indexed by the date
    each period's value first became known (realtime_start for vintaged series; the
    modelled release date for non-vintaged). Value = the initial-release print.

    This is the raw, un-reindexed availability stream. `series(basis='release')`
    reindexes it onto the business-day grid with ffill so a backtest reads, on every
    day d, the most recent value published on or before d.
    """
    sid = COL_TO_VINTAGED_SID.get(col)
    v = vintages if vintages is not None else _vintages()
    if sid is not None and v is not None and not v.empty:
        sub = v[v["series"] == sid]
        if not sub.empty:
            # Initial release per period, stamped at its realtime_start (first-published
            # date). Collapse to one row per realtime_start keeping the latest period
            # released that day (handles rare same-day multi-period releases).
            s = (sub.sort_values(["realtime_start", "period"])
                    .drop_duplicates(subset="realtime_start", keep="last"))
            out = pd.Series(s["value"].to_numpy(),
                            index=pd.to_datetime(s["realtime_start"].to_numpy()))
            return out[~out.index.duplicated(keep="last")].sort_index()
    # non-vintaged (or vintage missing): shift the reference-stamped series to its
    # modelled release date using the static lag calendar.
    return _modelled_release(col)


def _reference_series(col: str) -> pd.Series | None:
    """The reference-stamped series exactly as the live path reads it from the store.
    Mirrors engine.inputs._fred(): first column of the FRED parquet for this sid.
    Falls back to None if the column is not a plain FRED store series."""
    sid = COL_TO_VINTAGED_SID.get(col)
    if sid is None:
        # try to resolve via the config series map (col -> sid)
        try:
            fmap: dict[str, str] = {}
            for grp in config.load()["fred"]["series"].values():
                fmap.update(grp)
            # invert: column -> sid
            inv = {c: s for s, c in fmap.items()}
            sid = inv.get(col)
        except Exception:  # noqa: BLE001
            sid = None
    if sid is None:
        return None
    df = store.read("fred", sid)
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].dropna()
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _period_end(idx: pd.DatetimeIndex, cadence: str) -> pd.DatetimeIndex:
    """Map a reference timestamp to the END of the period it describes. FRED stamps
    monthly/quarterly series on the period START (day 1); the release comes after the
    period END, so we roll forward before applying the business-day lag."""
    if cadence == "M":
        return idx + pd.offsets.MonthEnd(0)
    if cadence == "Q":
        return idx + pd.offsets.QuarterEnd(0)
    # weekly/daily: FRED weekly series are stamped on the week-ending date already,
    # daily on the observation date — the stamp IS the period end.
    return idx


def _modelled_release(col: str) -> pd.Series:
    """Shift a reference-stamped series to its modelled first-release date via the
    static lag calendar. release_date = period_end + lag_bd business days."""
    ref = _reference_series(col)
    if ref is None or ref.empty:
        return pd.Series(dtype=float)
    lags = _release_lags()
    spec = lags.get(col)
    if spec is None:
        # unknown series: assume it was available on its reference stamp (no shift).
        # Loud-ish: a series routed through 'release' with no lag prior is a config gap.
        log.debug("PIT: no release-lag prior for %s — assuming reference availability", col)
        return ref
    cadence = spec.get("cadence", "M")
    lag_bd = int(spec.get("lag_bd", 0))
    pend = _period_end(pd.DatetimeIndex(ref.index), cadence)
    rel = pend + (lag_bd * pd.offsets.BDay())
    out = pd.Series(ref.to_numpy(), index=rel)
    # a later reference period can, under a fixed lag, map before an earlier one only
    # if the source period grid is irregular; keep the last value per release date.
    return out[~out.index.duplicated(keep="last")].sort_index()


# --------------------------------------------------------------------------- #
# Public accessor
# --------------------------------------------------------------------------- #
def series(name: str, as_of: pd.Timestamp | str | None = None,
           basis: Basis = "release", index: pd.DatetimeIndex | None = None,
           ffill_limit: int | None = None,
           vintages: pd.DataFrame | None = None) -> pd.Series:
    """Point-in-time series for a live-frame column `name`.

    Parameters
    ----------
    name : live-frame column (e.g. "payrolls", "core_cpi", "wei").
    as_of : if set, truncate the returned series to values knowable on/before this
        date (a hard as-of cut on top of the basis). None = full history.
    basis :
        'release'  -> leak-free availability frame (default). Vintaged: as-of join on
                      realtime_start. Non-vintaged: reference shifted to modelled
                      release date. This is the frame a real-money backtest reads.
        'reference'-> native reference stamping + ffill (reproduces inputs.put()).
        'latest'   -> latest-revised finals, reference-stamped (currently == store).
    index : business-day grid to reindex onto. None = the series' own release/
        reference dates (no reindex).
    ffill_limit : ffill limit when `index` is supplied (mirrors inputs.put()).

    Returns a pd.Series indexed by availability date (or `index` if supplied). Empty
    if the column has no resolvable source.
    """
    if basis == "release":
        raw = release_availability(name, vintages=vintages)
    elif basis in ("reference", "latest"):
        # both read the local store's reference-stamped finals (the store keeps only
        # latest-revised values); the axis is kept distinct for a future split.
        raw = _reference_series(name)
        if raw is None:
            raw = pd.Series(dtype=float)
    else:
        raise ValueError(f"unknown basis {basis!r}")

    if as_of is not None:
        raw = raw[raw.index <= pd.Timestamp(as_of)]

    if index is None:
        return raw
    if raw.empty:
        return pd.Series(np.nan, index=index)
    # reindex onto the business-day grid, ffill so day d carries the last value known
    # by d (matches inputs.put()'s union-reindex-ffill contract).
    union = index.union(raw.index)
    s = raw.reindex(union)
    if ffill_limit is not None:
        s = s.ffill(limit=ffill_limit)
    else:
        s = s.ffill()
    return s.reindex(index)


def coverage_report(vintages: pd.DataFrame | None = None) -> dict:
    """Which live-frame columns have vintage coverage vs fall back to the release-lag
    calendar. Used by the shadow harness metadata and to flag store gaps."""
    v = vintages if vintages is not None else _vintages()
    present = set(v["series"].unique()) if (v is not None and not v.empty) else set()
    vintaged, calendar, gaps = [], [], []
    for sid, col in VINTAGED_SID_TO_COL.items():
        if sid in present:
            vintaged.append(col)
        else:
            gaps.append(f"{col} ({sid})")
    for col in _release_lags():
        if col not in vintaged:
            calendar.append(col)
    return {
        "vintaged_columns": sorted(vintaged),
        "calendar_columns": sorted(calendar),
        "vintage_store_gaps": sorted(gaps),
        "n_vintaged_series_on_disk": len(present),
    }
