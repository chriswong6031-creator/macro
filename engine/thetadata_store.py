"""Reader over the ThetaData EOD historical store.

Store layout (T1 backfill, accumulates in ops worktree):
  {THETADATA_STORE}/eod/{ROOT}/{YYYY}.parquet
  {THETADATA_STORE}/oi/{ROOT}/{YYYY}.parquet
  {THETADATA_STORE}/greeks/{ROOT}/{YYYY}.parquet   (optional — vendor IV starts ~2015+)

EOD columns  : root, expiration, strike, right, date, open, high, low, close,
               volume, count, bid, ask
OI columns   : root, expiration, strike, right, date, open_interest
Greeks cols  : root, expiration, strike, right, date, bid, ask, underlying_price,
               delta, theta, vega, rho, epsilon, lambda, implied_vol, iv_error

OI TIMING LAW (LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE §8 ¶1):
  OPRA reports OI once per day at ~06:30 ET representing end-of-PREVIOUS-day positions.
  oi[t] = positions as of EOD t-1.  For any day-t signal, the correct OI input is
  oi[t-1] (i.e. shift(1) on the OI series).  Using same-day OI is a lookahead bug.
  doi_series() enforces this via pandas shift(1) BEFORE computing deltas.

STORE ROOT:
  resolve_thetadata_store() is THE canonical resolver (WP-RESOLVER): env
  THETADATA_STORE → lib.config data_dir()/thetadata_eod → the ops-host worktree
  store — every candidate existence- AND content-checked (must contain at least
  one of eod/, oi/, greeks/). An empty stub dir does NOT resolve: that is the
  exact shape of the options_witness 0/18 incident, where a GH runner resolved
  an empty repo-local store and published an all-suppressed artifact.
  store_root() remains as a back-compat wrapper (always returns a Path, may not
  exist — it warns when it doesn't); new callers should use the resolver.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# parquet load cache                                                            #
# --------------------------------------------------------------------------- #
# _PARQUET_CACHE: (tier, root, year_file_path_str) -> pd.DataFrame
#
# A full-universe run calls chain() for every (date, root) combination.
# Without caching, _load_parquets re-reads the year file on EVERY date within
# the same year, turning the run into O(dates × full reads). With this cache,
# each year file is read exactly once — O(roots × years × reads).
#
# Memory tradeoff: each cached DataFrame is the full year of one (tier, root)
# pair (typically a few MB for SPY eod; smaller for oi/greeks). At 3 tiers ×
# N roots × Y years the peak footprint is 3NY DataFrames in memory.  For a
# broad universe (hundreds of roots, 12 years) this can reach several GB; for
# typical backtests (tens of roots) it is comfortably under 1 GB.  Call
# clear_parquet_cache() to release all frames after a batch run.
_PARQUET_CACHE: dict[str, pd.DataFrame] = {}


def clear_parquet_cache() -> None:
    """Release all cached year-parquet DataFrames.

    Call after a full-universe batch run to reclaim memory.  Not needed for
    single-date queries or for tests (the fixture store is tiny).
    """
    _PARQUET_CACHE.clear()


# --------------------------------------------------------------------------- #
# store root resolution                                                         #
# --------------------------------------------------------------------------- #

# Canonical ops-host store path (the launchd theta-ops worktree). This constant
# lives HERE and only here — per-module copies of this path were the fragmented
# resolution that enabled the options_witness empty-store incident.
_OPS_WT_STORE = Path("/Users/chriswong/theta-ops-wt/data/thetadata_eod")

# A directory only counts as a store when at least one tier subdir is present.
_STORE_TIERS = ("eod", "oi", "greeks")


def _has_store_content(p: Path) -> bool:
    """True when `p` exists and contains at least one of eod/, oi/, greeks/.

    An empty stub directory (exists, no tier subdirs) does NOT count — resolving
    one silently yields empty frames everywhere downstream, which is the exact
    incident shape (options_witness published 0/18 themes from a stub store).
    """
    try:
        return p.is_dir() and any((p / t).is_dir() for t in _STORE_TIERS)
    except OSError:
        return False


def resolve_thetadata_store(required: bool = False,
                            purpose: str = "") -> Path | None:
    """THE canonical ThetaData store resolver (WP-RESOLVER) — single fallback chain.

    Chain (first content-bearing hit wins):
      1. THETADATA_STORE env — warns loudly when set but missing/stub, then
         falls through (a misconfigured env var must not silently win).
      2. lib.config data_dir()/thetadata_eod (the repo-local store / symlink).
      3. the ops-host worktree store (_OPS_WT_STORE).

    A candidate resolves only if it EXISTS and contains at least one of
    eod/, oi/, greeks/ (see _has_store_content).

    Args:
        required: when True and nothing resolves, raise RuntimeError naming
                  every path tried and the purpose. Builders that would
                  otherwise publish empty/suppressed artifacts should either
                  pass required=True or exit nonzero themselves on None.
        purpose:  short caller tag, included in every log line.

    Returns the resolved store root Path, or None (required=False only).
    """
    candidates: list[tuple[str, Path]] = []
    env = os.environ.get("THETADATA_STORE")
    if env:
        candidates.append(("env", Path(env)))
    try:
        from lib import config  # noqa: PLC0415
        candidates.append(("data_dir", config.data_dir() / "thetadata_eod"))
    except Exception:  # noqa: BLE001
        candidates.append(("data_dir", Path("data") / "thetadata_eod"))
    candidates.append(("ops-wt", _OPS_WT_STORE))

    tried: list[str] = []
    for source, path in candidates:
        if _has_store_content(path):
            log.info("thetadata_store: resolved store=%s source=%s purpose=%s",
                     path, source, purpose or "-")
            return path
        if source == "env":
            if not path.exists():
                log.warning(
                    "thetadata_store: THETADATA_STORE=%s is SET but the path does "
                    "not exist — ignoring the env override and falling through "
                    "(purpose=%s)", env, purpose or "-")
            else:
                log.warning(
                    "thetadata_store: THETADATA_STORE=%s exists but contains none "
                    "of eod/ oi/ greeks/ — empty stub, not a store; falling "
                    "through (purpose=%s)", env, purpose or "-")
        tried.append(f"{source}:{path}")

    log.error("thetadata_store: resolved store=NONE purpose=%s — tried %s",
              purpose or "-", ", ".join(tried))
    if required:
        raise RuntimeError(
            f"ThetaData store required (purpose={purpose or '-'}) but no path "
            f"resolves. Tried: {', '.join(tried)}. A path only resolves if it "
            f"exists and contains at least one of eod/, oi/, greeks/. Set "
            f"THETADATA_STORE or point the caller at a real store."
        )
    return None


def _default_store_root() -> Path:
    """Resolve the default store root: THETADATA_STORE env, else data/thetadata_eod."""
    env = os.environ.get("THETADATA_STORE")
    if env:
        return Path(env)
    # Try lib.config first; fall back to CWD-relative for hermetic tests
    try:
        from lib import config  # noqa: PLC0415
        return config.data_dir() / "thetadata_eod"
    except Exception:  # noqa: BLE001
        return Path("data") / "thetadata_eod"


# store_root() paths already warned about (once per process, not per read)
_WARNED_MISSING_ROOTS: set[str] = set()


def store_root(override: str | Path | None = None) -> Path:
    """Back-compat wrapper: always returns a Path, which may NOT exist.

    Downstream loaders return empty frames on a missing root, so this warns
    (once per path per process) when the result does not exist. New callers
    should use resolve_thetadata_store(), which fails loud instead of empty.
    """
    p = Path(override) if override is not None else _default_store_root()
    if not p.exists():
        key = str(p)
        if key not in _WARNED_MISSING_ROOTS:
            _WARNED_MISSING_ROOTS.add(key)
            log.warning(
                "thetadata_store.store_root: %s does not exist — parquet reads "
                "will silently return EMPTY frames; prefer "
                "resolve_thetadata_store() for fail-loud resolution", p)
    return p


# --------------------------------------------------------------------------- #
# low-level parquet loader (graceful on missing root/year)                     #
# --------------------------------------------------------------------------- #

def _load_parquets(tier: str, root: str, years: list[int] | None,
                   store: str | Path | None = None) -> pd.DataFrame:
    """Load all parquets for (tier, root), optionally filtered to `years`.
    Missing files are silently skipped (partial store is normal during backfill).

    Results are memoized in _PARQUET_CACHE keyed by the resolved file path string.
    This means consecutive chain() calls for different dates in the same year pay
    one disk read, not N reads.  Call clear_parquet_cache() after a batch run to
    release memory.

    Defensive dedup: full-row drop_duplicates() is applied to each parquet frame
    before caching.  This protects downstream consumers (Phase-B gate runs, backtest
    loops) against parquets written before the 2026-07-05 API-dedup fix landed in
    _normalize_eod_df.  Any rows dropped are logged at WARN level with a pointer to
    the repair script.  The cache stores the already-deduped frame so repeated calls
    pay the dedup cost only once per (tier, root, year) file.  Call
    clear_parquet_cache() after running the repair script to force fresh reads.
    """
    base = store_root(store) / tier / root
    if not base.exists():
        return pd.DataFrame()
    files = sorted(base.glob("*.parquet"))
    if years is not None:
        year_set = {str(y) for y in years}
        files = [f for f in files if f.stem in year_set]
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        key = str(f.resolve())
        if key in _PARQUET_CACHE:
            frames.append(_PARQUET_CACHE[key])
            continue
        try:
            df = pd.read_parquet(f)
            # Defensive dedup before caching: drop full-row duplicates introduced by the
            # ThetaData v3 API (see collectors/thetadata.py _normalize_eod_df docstring).
            # Parquets written before 2026-07-05 may contain duplicates; this ensures all
            # reads are clean regardless of when the file was written.
            n_before = len(df)
            df = df.drop_duplicates()
            n_dropped = n_before - len(df)
            if n_dropped > 0:
                log.warning(
                    "thetadata_store: %s/%s/%s — dropped %d full-row duplicates on load "
                    "(%d → %d rows); run scripts/repair_thetadata_dedup.py --apply to fix "
                    "the parquet on disk",
                    tier, root, f.name, n_dropped, n_before, len(df),
                )
            _PARQUET_CACHE[key] = df
            frames.append(df)
        except Exception as e:  # noqa: BLE001
            log.debug("skip %s: %s", f, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _normalise_date(df: pd.DataFrame, col: str = "date") -> pd.DataFrame:
    """Ensure the date column is a date-only string 'YYYY-MM-DD'."""
    if col not in df.columns:
        return df
    df = df.copy()
    df[col] = pd.to_datetime(df[col]).dt.date.astype(str)
    return df


# --------------------------------------------------------------------------- #
# public API                                                                    #
# --------------------------------------------------------------------------- #

def universe(date: str | None = None, store: str | Path | None = None) -> list[str]:
    """All roots with EOD data. If `date` supplied, only roots with at least one
    row on that date. Graceful on empty store."""
    base = store_root(store) / "eod"
    if not base.exists():
        return []
    roots = [p.name for p in sorted(base.iterdir()) if p.is_dir()]
    if date is None:
        return roots
    # Filter to roots that have a parquet for the year
    year = str(pd.Timestamp(date).year)
    result = []
    for r in roots:
        f = base / r / f"{year}.parquet"
        if f.exists():
            result.append(r)
    return result


def chain(date: str, root: str,
          store: str | Path | None = None) -> pd.DataFrame:
    """Per-contract frame for (date, root) joining eod + oi (+greeks/IV where present).

    Returns a DataFrame with columns:
      root, expiration, strike, right, date,
      open, high, low, close, volume, count, bid_eod, ask_eod,
      open_interest,                              (from oi, may be NaN)
      implied_vol, delta, theta, vega, rho,       (from greeks, may be NaN)
      iv_error                                    (from greeks, may be NaN)

    OI is NOT shifted here — chain() returns raw point-in-time data.
    Use doi_series() which applies the oi[t-1] law for signal construction.

    Returns empty DataFrame gracefully when root or year is absent.
    """
    year = pd.Timestamp(date).year
    years = [year]

    eod = _load_parquets("eod", root, years, store)
    if eod.empty:
        return pd.DataFrame()
    eod = _normalise_date(eod)
    eod = eod[eod["date"] == date].copy()
    if eod.empty:
        return pd.DataFrame()

    # rename bid/ask to avoid collision with greeks bid/ask
    if "bid" in eod.columns:
        eod = eod.rename(columns={"bid": "bid_eod", "ask": "ask_eod"})

    oi = _load_parquets("oi", root, years, store)
    if not oi.empty:
        oi = _normalise_date(oi)
        oi = oi[oi["date"] == date][
            ["root", "expiration", "strike", "right", "date", "open_interest"]
        ].copy()
        eod = eod.merge(oi, on=["root", "expiration", "strike", "right", "date"],
                        how="left")
    else:
        eod["open_interest"] = np.nan

    greeks = _load_parquets("greeks", root, years, store)
    if not greeks.empty:
        greeks = _normalise_date(greeks)
        greeks = greeks[greeks["date"] == date].copy()
        # greeks may have bid/ask for the bid-ask at greeks snapshot time — keep separately
        gcols = ["root", "expiration", "strike", "right", "date"]
        extra = [c for c in ("implied_vol", "iv_error", "delta", "theta",
                              "vega", "rho", "underlying_price")
                 if c in greeks.columns]
        if extra:
            eod = eod.merge(greeks[gcols + extra], on=gcols, how="left")
        else:
            for c in ("implied_vol", "iv_error", "delta", "theta", "vega", "rho"):
                eod[c] = np.nan
    else:
        for c in ("implied_vol", "iv_error", "delta", "theta", "vega", "rho"):
            eod[c] = np.nan

    return eod.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# ΔOI series with the oi[t-1] law                                              #
# --------------------------------------------------------------------------- #

def doi_series(root: str, put_call: str = "both",
               window: int = 5,
               store: str | Path | None = None) -> pd.DataFrame:
    """Per-date ΔOI (5-session default) for one root, aggregated over all strikes/expiries.

    OI TIMING LAW (cite: LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE §8 ¶1):
      OPRA reports OI at ~06:30 ET representing end-of-PREVIOUS-day positions.
      We shift(1) so that day-t's signal uses oi[t-1], not oi[t].
      Same-day OI in a day-t signal is a lookahead bug — see §8 ¶1.

    Args:
        root      : option root symbol (e.g. "SPY")
        put_call  : "C" (calls only), "P" (puts only), or "both"
        window    : rolling window for delta (default 5 sessions)
        store     : store root override

    Returns DataFrame indexed by date (str 'YYYY-MM-DD') with columns:
        total_oi  : total open interest across all active contracts
        doi_raw   : total_oi - total_oi.shift(window)  (window-session delta)
        doi_z     : doi_raw normalised by its 63-day rolling std (cross-time z)
    """
    oi_all = _load_parquets("oi", root, None, store)
    if oi_all.empty:
        return pd.DataFrame(columns=["date", "total_oi", "doi_raw", "doi_z"])

    oi_all = _normalise_date(oi_all)
    if put_call in ("C", "P"):
        oi_all = oi_all[oi_all["right"] == put_call]

    daily = (oi_all.groupby("date")["open_interest"].sum()
             .sort_index()
             .rename("total_oi"))

    # CRITICAL: shift(1) — OI at t is reported next morning, so it represents
    # EOD t-1 positions. Using oi[t] for day-t signals would be a lookahead.
    # We shift BEFORE computing the delta so that doi_raw[t] =
    #   oi_as_reported_on_t (=EOD t-1 position) - oi_as_reported_on_{t-window}
    # which is fully known by the start of session t. — LIVE_ORDER_FLOW §8 ¶1
    oi_shifted = daily.shift(1)  # oi[t-1] law

    doi_raw = oi_shifted - oi_shifted.shift(window)
    doi_z = doi_raw / doi_raw.rolling(63, min_periods=21).std()

    out = pd.DataFrame({"total_oi": oi_shifted, "doi_raw": doi_raw, "doi_z": doi_z})
    out.index.name = "date"
    return out.reset_index()


# --------------------------------------------------------------------------- #
# IV coverage                                                                   #
# --------------------------------------------------------------------------- #

def iv_coverage(store: str | Path | None = None) -> dict[str, dict]:
    """Per-root first/last date where greeks IV exists.

    Returns {root: {"first": "YYYY-MM-DD", "last": "YYYY-MM-DD", "n_dates": int}}.
    Empty dict when no greeks data is present at all.

    The vendor greeks history starts LATER than EOD/OI (vendor greeks were
    empty through at least 2015; the exact start year is visible in backfill
    logs as the first 'greeks rows>0' year).
    """
    base = store_root(store) / "greeks"
    if not base.exists():
        return {}
    result = {}
    for root_dir in sorted(base.iterdir()):
        if not root_dir.is_dir():
            continue
        root = root_dir.name
        frames = []
        for f in sorted(root_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(f, columns=["date", "implied_vol"])
                df = df[df["implied_vol"].notna() & (df["implied_vol"] > 0)]
                if not df.empty:
                    frames.append(_normalise_date(df)[["date"]])
            except Exception as e:  # noqa: BLE001
                log.debug("iv_coverage skip %s: %s", f, e)
        if not frames:
            continue
        all_dates = pd.concat(frames)["date"].unique()
        all_dates = sorted(all_dates)
        result[root] = {
            "first": all_dates[0],
            "last": all_dates[-1],
            "n_dates": len(all_dates),
        }
    return result


# --------------------------------------------------------------------------- #
# chain-provider factory (for refactored skew/ivspread validators)             #
# --------------------------------------------------------------------------- #

def make_chain_provider(
    store: str | Path | None = None,
    require_iv: bool = False,
) -> Callable[[str, str], pd.DataFrame | None]:
    """Return a chain-frame provider that matches the polygon_gex chain schema.

    The returned callable: provider(date_str, root) -> pd.DataFrame | None

    The returned frame has the columns the existing skew/ivspread engines expect:
      underlying, expiry, K, T, iv, delta, is_call, spot, oi, volume, asof

    IV (implied_vol) is sourced from the greeks tier when present; when absent
    and require_iv=False the iv column is NaN (allowing IV-free signals like ΔOI
    to still use this provider). When require_iv=True and IV is absent, returns None.

    NOTE on spot: the ThetaData EOD store has no separate underlying_price column
    in the eod tier; we derive spot from the volume-weighted mid strike (the strike
    at maximum total volume), which is an approximation. When greeks are present,
    underlying_price from the greeks tier is used as the authoritative spot.
    """
    def provider(date_str: str, root: str) -> pd.DataFrame | None:
        df = chain(date_str, root, store=store)
        if df.empty:
            return None

        # spot: prefer greeks underlying_price; fall back to volume-weighted strike
        if "underlying_price" in df.columns and df["underlying_price"].notna().any():
            spot = float(df["underlying_price"].dropna().median())
        else:
            total_vol = df.groupby("strike")["volume"].sum()
            spot = float(total_vol.idxmax()) if not total_vol.empty else float("nan")

        if np.isnan(spot) or spot <= 0:
            return None

        # map right → is_call
        df = df.copy()
        df["is_call"] = df["right"].str.upper() == "C"

        # compute T (years to expiry from this date)
        dt_date = pd.Timestamp(date_str)
        df["expiry"] = pd.to_datetime(df["expiration"]).dt.date.astype(str)
        df["T"] = (pd.to_datetime(df["expiry"]) - dt_date).dt.days / 365.0
        df["T"] = df["T"].clip(lower=0.0)

        # IV: from greeks tier if present; NaN otherwise
        if "implied_vol" in df.columns:
            df["iv"] = pd.to_numeric(df["implied_vol"], errors="coerce")
        else:
            df["iv"] = np.nan

        if require_iv and df["iv"].isna().all():
            return None

        # OI: raw point-in-time (caller applies oi[t-1] law at the signal level)
        df["oi"] = pd.to_numeric(df.get("open_interest", np.nan), errors="coerce")

        df["K"] = pd.to_numeric(df["strike"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        df["underlying"] = root
        df["spot"] = spot
        df["asof"] = date_str

        keep = ["underlying", "expiry", "K", "T", "iv", "delta", "is_call",
                "spot", "oi", "volume", "asof"]
        # delta may come from greeks; otherwise NaN
        if "delta" not in df.columns:
            df["delta"] = np.nan
        else:
            df["delta"] = pd.to_numeric(df["delta"], errors="coerce")

        return df[[c for c in keep if c in df.columns]].reset_index(drop=True)

    return provider
