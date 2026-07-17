"""engine/options_entry_state.py — display-tier options entry state fusion table.

RO-1 (OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE §2): builds a per-ticker snapshot
table by fusing LATEST per-ticker data from all available options sources.  This is a
**display-only raw-fields fusion table** — it contains no composite/score/rank columns
(RO-2 / Signal Commons R3) and no forward-return columns.  It is NOT a forward ledger;
the nightly rebuilds it idempotently from LATEST source rows.

Sources (all read-only):
  - data/polygon_gex/summary_<SYM>.parquet     → gamma_regime, dist_to_flip_pct,
                                                  magnet_up/down → wall distance pcts,
                                                  iv30, max_pain (if present),
                                                  net_vex (for vanna_hedge_5d),
  - data/polygon_gex/chains/{date}.parquet      → per-contract K/T/iv/oi/is_call/expiry/
                                                  gamma/delta/spot; engine/greeks.bs_greeks
                                                  computes vanna/charm from these fields
  - data/options_skew/snapshots.parquet         → skew + 5d change
  - data/options_ivspread/snapshots.parquet     → ivspread_rel + 5d change
  - data/options_flow/summary_<SYM>.parquet     → fresh_contracts, net_doi, doi_pc,
                                                  zerodte_share
  - site/flow/<SYM>.json                        → fresh_premium_mn (in new_positions)
  - engine/opex.py                              → opex_days
  - engine/gex_confirm.py                       → CONFIRM/NEUTRAL/CAUTION verdict
                                                  (structure lobe — reused, not reimplemented)

Columns emitted (per masterplan W-A acceptance gate):
  as_of, ticker, iv30,
  iv_rank_252, iv_rank_5d_chg   — STRUCTURALLY NULL until A9 IV-backfill PR (A9 ruling;
                                   emit columns as all-null; no "thin" here — architecturally
                                   absent, not missing data),
  ivspread_rel, ivspread_5d_chg,
  skew, skew_5d_chg,
  net_doi, doi_pc, fresh_contracts, fresh_premium_mn, zerodte_share,
  gamma_regime, gamma_regime_structurally_constant   — bool caveat per audit #29 (single-name
                                                       gamma_regime is structurally_constant
                                                       per name; this col documents the caveat),
  dist_to_flip_pct,
  wall_up_dist_pct, wall_down_dist_pct,
  max_pain_dist_pct              — null if max_pain absent,
  opex_days,                     — CALENDAR days to next monthly OPEX (3rd Friday).
                                   NAMING NOTE (RUL-OVC-8): opex_days here is CALENDAR days.
                                   engine/opex.py tag().td_to is TRADING days (opt_opex_days
                                   in the ledger stamp).  Both are kept; this column is
                                   display-only context; the stamp uses td_to for PIT accuracy.
  pin_risk                       — bool: opex_days<=5 AND gamma_regime=='long' AND
                                   min(wall_up_dist_pct, wall_down_dist_pct,
                                       max_pain_dist_pct) <= PIN_RISK_WALL_PCT (2.0%)
                                   THRESHOLD RATIONALE: 2% is approximately 1 ATM daily move
                                   on most large-caps; within this band dealer gamma/charm
                                   effects can mechanically pin or release spot at expiry,
  gex_confirm_verdict,
  evidence_quality               — 'full'/'partial'/'thin'/'stale' per-row freshness,
  src_gex_asof, src_skew_asof, src_ivspread_asof, src_flow_asof,

  W-OVC additions (RO-2 display-only, no composites):
  front7_charm_share             — |charm| OI-weighted notional share for expiries within
                                   7 calendar days, as fraction of total board.  Null when
                                   no chain data or zero total.  See _compute_chain_ovc().
  front7_gex_share               — |gamma| OI-weighted notional share for expiries within
                                   7 calendar days (same construction as front7_charm_share).
  signed_vanna_pressure          — net board-wide signed vanna notional (sum of
                                   sign×vanna×oi×mult×spot×pm, same dealer convention as
                                   engine/gex_engine.py: long-call +1, short-put +1).
                                   Display-only; the sign inherits the unobservable dealer
                                   convention (audit #29).
  vanna_hedge_5d                 — −net_vex × iv30_5d_chg from the summary store.
                                   net_vex = net signed vanna-dollar exposure (from
                                   summary_{SYM}.parquet); iv30_5d_chg = latest iv30 minus
                                   iv30 5 summary rows ago (calendar days, not trading days).
                                   Null when < 5 summary rows available or net_vex absent.
  root_class                     — enum: index_etf | sector_etf | industry_etf | single_name.
                                   Derived from ROOT_CLASS_MAP (see below). Display-only context
                                   for front7_*_share interpretation (RUL-OVC-6 caveat: sign
                                   of front7_charm_share → RV is era-unstable within ETF class).

OI TIMING LAW (OPRA convention, matching existing column treatment in this file):
  Options OI is reported T+1 by OPRA — contracts traded on date t are reflected in the
  OI of the t+1 chain snapshot.  The chains/{date}.parquet stores carry the OI as-reported
  for that file date.  This module reads LATEST chain snapshot without additional shifting
  (matching existing behaviour for pin_risk/gex_confirm_verdict which also read the latest
  summary row).  For display context at render time this is appropriate; the PIT-stamping
  path in engine/options_stamp.py additionally applies strict date-≤-fire_date filtering
  so the ledger stamp always uses T−1 positions relative to fire date.

Missing/gitignored stores → null fields + evidence_quality='thin'.  NEVER raises on
missing stores; NEVER emits fake-neutral values for absent data.

FORBIDDEN: do NOT open data/us_board_ledger/retro_grades.parquet (A9 single-writer).
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import gex_confirm
from engine.greeks import bs_greeks

log = logging.getLogger(__name__)

# Pin-risk wall threshold (2.0% — see docstring).
PIN_RISK_WALL_PCT = 2.0

# Number of trading days for the "5d change" look-back.
LOOKBACK_TRADING_DAYS = 5

# Evidence-quality stale threshold: source as_of older than this many calendar days.
STALE_CALENDAR_DAYS = 3

# ── Root-class mapping (W-OVC, RUL-OVC-6) ────────────────────────────────────
# One place for the entire taxonomy. display-only — no signal/scoring use.
# Mandatory alongside front7_*_share (ETF-slice sign is era-unstable per robustness §3.2).
_INDEX_ETFS: frozenset[str] = frozenset({"SPY", "QQQ", "IWM", "DIA"})
_SECTOR_ETFS: frozenset[str] = frozenset({
    # 11 SPDR Select Sector ETFs
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
})
_INDUSTRY_ETFS: frozenset[str] = frozenset({
    "SMH", "SOXX", "XBI", "KRE", "ARKK",
    # Additional common industry ETFs (additive-only; never remove existing entries)
    "GDX", "GDXJ", "XOP", "XHB", "ITB", "IBB", "FXI", "EWZ", "EEM", "GLD", "SLV", "TLT",
    "HYG", "LQD", "JETS", "BITO",
})

# lookup function — single_name is the default for anything not in the above sets
def _root_class(ticker: str) -> str:
    """Return the root_class for a ticker: index_etf | sector_etf | industry_etf | single_name.

    Mapping is intentionally conservative and additive-only (never remove entries once live).
    New ETFs are added to _INDUSTRY_ETFS by default unless they fit a narrower category.
    """
    t = str(ticker).upper()
    if t in _INDEX_ETFS:
        return "index_etf"
    if t in _SECTOR_ETFS:
        return "sector_etf"
    if t in _INDUSTRY_ETFS:
        return "industry_etf"
    return "single_name"


# Multiplier and point-move factor matching engine/gex_engine.py convention
_CHAIN_MULT = 100.0   # US equity options: 100 shares per contract
_CHAIN_PM = 0.01      # per-1-point move in underlying dollar-dollar


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean(v: Any) -> Any:
    """Coerce numpy scalars and NaN/None to Python-native None / scalar.
    Safe for JSON and parquet storage."""
    if v is None:
        return None
    if isinstance(v, float) and (v != v):   # NaN check
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        v = float(v)
        return None if (v != v) else v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def _safe_float(x: Any) -> float | None:
    """Convert to float; return None on failure or NaN."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if (v != v) else v


def _opex_days_today() -> int | None:
    """Calendar days to the next monthly options expiry (3rd Friday)."""
    def _third_friday(y: int, m: int) -> _dt.date:
        d = _dt.date(y, m, 1)
        return d + _dt.timedelta(days=(4 - d.weekday()) % 7 + 14)
    today = _dt.date.today()
    tf = _third_friday(today.year, today.month)
    if tf < today:
        ny, nm = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        tf = _third_friday(ny, nm)
    return (tf - today).days


def _asof_staleness(asof_str: str | None, today: _dt.date | None = None) -> str:
    """Return 'stale' if asof_str is older than STALE_CALENDAR_DAYS, else 'fresh'."""
    if not asof_str:
        return "missing"
    if today is None:
        today = _dt.date.today()
    try:
        d = _dt.date.fromisoformat(str(asof_str)[:10])
        return "stale" if (today - d).days > STALE_CALENDAR_DAYS else "fresh"
    except (ValueError, TypeError):
        return "missing"


def _evidence_quality(
    gex_asof: str | None,
    skew_asof: str | None,
    ivspread_asof: str | None,
    flow_asof: str | None,
    today: _dt.date | None = None,
) -> str:
    """
    Classify evidence quality per RO-1:
      full    — all 4 sources present and fresh
      partial — at least 2 sources present and fresh
      thin    — 0 or 1 source present and fresh
      stale   — sources present but all stale / no non-null sources
    """
    statuses = [
        _asof_staleness(gex_asof, today),
        _asof_staleness(skew_asof, today),
        _asof_staleness(ivspread_asof, today),
        _asof_staleness(flow_asof, today),
    ]
    fresh_count = sum(1 for s in statuses if s == "fresh")
    stale_count = sum(1 for s in statuses if s == "stale")
    if fresh_count == 4:
        return "full"
    if fresh_count >= 2:
        return "partial"
    if stale_count > 0 and fresh_count == 0:
        return "stale"
    return "thin"


# ---------------------------------------------------------------------------
# W-OVC chain helpers
# ---------------------------------------------------------------------------

def _load_latest_chain_ovc(root: Path) -> tuple[_dt.date | None, dict[str, pd.DataFrame]]:
    """Load the latest chains/{date}.parquet ONCE and return (chain_date, {ticker: sub_df}).

    Called once per build_state invocation.  The per-ticker sub-frames are pre-filtered
    and numeric-coerced so the per-ticker loop in build_state does not re-read or re-parse
    the whole-market parquet ~350 times.

    Returns (None, {}) when no chain file exists or required columns are missing.
    """
    _OVC_REQUIRED = {"underlying", "K", "T", "iv", "oi", "is_call", "spot", "expiry"}
    chains_dir = root / "data" / "polygon_gex" / "chains"
    if not chains_dir.exists():
        return None, {}
    chain_files = sorted(chains_dir.glob("*.parquet"))
    if not chain_files:
        return None, {}
    latest_chain_path = chain_files[-1]
    try:
        chain_date_str = latest_chain_path.stem
        chain_date = _dt.date.fromisoformat(chain_date_str)
    except ValueError:
        log.debug("Cannot parse chain date from %s — skipping OVC", latest_chain_path.name)
        return None, {}
    try:
        cdf = pd.read_parquet(latest_chain_path)
    except Exception:
        log.debug("Cannot read chain %s — skipping OVC", latest_chain_path)
        return None, {}
    if cdf.empty or not _OVC_REQUIRED.issubset(set(cdf.columns)):
        log.debug("Chain %s empty or missing required OVC columns", latest_chain_path.name)
        return None, {}
    # Coerce numerics once, then split by underlying
    for col in ("K", "T", "iv", "oi", "spot"):
        cdf[col] = pd.to_numeric(cdf[col], errors="coerce")
    by_ticker: dict[str, pd.DataFrame] = {
        sym: grp.copy()
        for sym, grp in cdf.groupby("underlying", sort=False)
    }
    return chain_date, by_ticker


def _compute_chain_ovc_from_sub(
    sub: pd.DataFrame,
    chain_date: _dt.date,
) -> dict:
    """Compute W-OVC display columns from a pre-loaded per-ticker chain sub-frame.

    Called by build_state with frames produced by _load_latest_chain_ovc (loaded once for
    the whole board, then split by underlying).  This replaces the old _compute_chain_ovc
    which re-read the entire chain parquet once per ticker (~350 reads per build_state call).

    Returns dict with keys:
      front7_charm_share  — |charm| OI-weighted notional share for expiries ≤7 calendar
                             days from the chain date, as fraction of total board (0..1).
                             Null when chain absent or total board |charm| notional = 0.
      front7_gex_share    — |gamma| OI-weighted notional share for expiries ≤7 calendar
                             days (same construction as front7_charm_share).
      signed_vanna_pressure — net signed vanna notional across the full board (display).
      All keys always present; values are float | None.

    FORMULA (matches scripts/research/options_opex_vanna_charm_study.py):
      For each contract:
        dealer_sign = +1 for calls, -1 for puts  (long-call/short-put convention)
        vanna_notional = dealer_sign × vanna × oi × MULT × spot × PM
        charm_notional = dealer_sign × (charm / 365) × oi × MULT × spot
        gex_notional   = dealer_sign × gamma × oi × MULT × spot²  (but |·| for shares)

      front7_charm_share = sum(|charm_notional| where dte≤7) / sum(|charm_notional|)
      front7_gex_share   = sum(|gex_notional|  where dte≤7) / sum(|gex_notional|)
      signed_vanna_pressure = sum(vanna_notional) [full board, signed]

    OI TIMING (display-path note):
    This display path uses raw same-snapshot OI, consistent with the OI TIMING LAW in the
    module docstring (display context at render time; not a gate-feeding ledger primitive).
    The gate-feeding primitive in engine/options_stamp.py:_ovc_from_chain uses prior-day OI
    (shift(1) per contract) to match the frozen PIT-clean study construction.

    Null-safe: any per-contract failure (non-positive inputs to bs_greeks) silently
    produces NaN vanna/charm for that row; those rows are excluded from the sums.
    A zero total (all NaN or all-zero notionals) returns null for both shares.
    Never raises; coverage gaps → null fields, never crashes.
    """
    out: dict = {
        "front7_charm_share": None,
        "front7_gex_share": None,
        "signed_vanna_pressure": None,
    }
    if sub is None or sub.empty:
        return out

    # Compute calendar days to expiry from chain snapshot date
    def _dte(expiry_val) -> int | None:
        try:
            exp = pd.Timestamp(expiry_val).date()
            return (exp - chain_date).days
        except Exception:
            return None

    sub = sub.copy()
    sub["_dte"] = sub["expiry"].apply(_dte)

    # Compute vanna and charm per contract using bs_greeks
    vanna_list: list[float] = []
    charm_list: list[float] = []
    gamma_list: list[float] = []
    oi_list: list[float] = []
    spot_list: list[float] = []
    dte_list: list[int | None] = []
    is_call_list: list[bool] = []

    for _, row in sub.iterrows():
        S = row["spot"]
        K = row["K"]
        T = row["T"]
        sigma = row["iv"]
        oi = row["oi"]
        is_call = bool(row["is_call"])
        dte = row["_dte"]
        # bs_greeks returns NaN on degenerate inputs — that is the null-safe path
        try:
            _delta, gamma, vanna, charm = bs_greeks(S, K, T, sigma, is_call)
        except Exception:
            vanna, charm, gamma = float("nan"), float("nan"), float("nan")
        vanna_list.append(vanna)
        charm_list.append(charm)
        gamma_list.append(gamma)
        oi_list.append(float(oi) if oi is not None and not math.isnan(float(oi)) else float("nan"))
        spot_list.append(float(S) if S is not None and not math.isnan(float(S)) else float("nan"))
        dte_list.append(dte)
        is_call_list.append(is_call)

    n = len(vanna_list)
    if n == 0:
        return out

    va = np.array(vanna_list, dtype=float)
    ch = np.array(charm_list, dtype=float)
    gm = np.array(gamma_list, dtype=float)
    oi_arr = np.array(oi_list, dtype=float)
    sp_arr = np.array(spot_list, dtype=float)
    is_call_arr = np.array(is_call_list, dtype=float)

    # Dealer sign: +1 calls, -1 puts  (long-call/short-put convention, audit #29)
    sign_arr = np.where(is_call_arr, 1.0, -1.0)

    # charm notional: sign × (charm/365) × oi × MULT × spot  (per-day charm exposure)
    charm_notional = sign_arr * (ch / 365.0) * oi_arr * _CHAIN_MULT * sp_arr
    # gex notional: sign × gamma × oi × MULT × spot² (standard GEX dollar-gamma)
    gex_notional = sign_arr * gm * oi_arr * _CHAIN_MULT * sp_arr * sp_arr
    # vanna notional: sign × vanna × oi × MULT × spot × PM
    vanna_notional = sign_arr * va * oi_arr * _CHAIN_MULT * sp_arr * _CHAIN_PM

    # front-7 calendar-day mask
    dte_arr = np.array(
        [d if d is not None else -1 for d in dte_list], dtype=float
    )
    front7_mask = (dte_arr >= 0) & (dte_arr <= 7)

    abs_charm = np.abs(charm_notional)
    abs_gex = np.abs(gex_notional)

    # Null-safe sums (ignore NaN cells)
    total_abs_charm = float(np.nansum(abs_charm))
    front7_abs_charm = float(np.nansum(abs_charm[front7_mask]))
    total_abs_gex = float(np.nansum(abs_gex))
    front7_abs_gex = float(np.nansum(abs_gex[front7_mask]))
    total_signed_vanna = float(np.nansum(vanna_notional))

    if total_abs_charm > 0:
        out["front7_charm_share"] = round(front7_abs_charm / total_abs_charm, 6)
    if total_abs_gex > 0:
        out["front7_gex_share"] = round(front7_abs_gex / total_abs_gex, 6)
    if math.isfinite(total_signed_vanna):
        out["signed_vanna_pressure"] = round(total_signed_vanna, 2)

    return out


def _compute_vanna_hedge_5d(root: Path, ticker: str) -> float | None:
    """Compute vanna_hedge_5d = −net_vex × iv30_5d_chg from summary_{ticker}.parquet.

    iv30_5d_chg = latest iv30 minus iv30 from 5 rows earlier in the summary.
    Returns None when < 6 summary rows exist, net_vex is absent, or any required
    value is non-finite.

    SOURCE: data/polygon_gex/summary_{ticker}.parquet (net_vex + iv30 columns).
    This does NOT use the chain file — net_vex is the signed vanna-dollar aggregate
    already computed nightly by engine/gex_engine.py and written to the summary store.
    """
    summary_path = root / "data" / "polygon_gex" / f"summary_{ticker}.parquet"
    if not summary_path.exists():
        return None
    try:
        sdf = pd.read_parquet(summary_path)
    except Exception:
        return None
    if sdf.empty or len(sdf) < 6:
        return None
    if "net_vex" not in sdf.columns or "iv30" not in sdf.columns:
        return None
    # Latest row and the row 5 positions earlier (by DataFrame position, not calendar days)
    latest = sdf.iloc[-1]
    prior = sdf.iloc[-6]  # index -6 gives the row 5 steps before -1

    def _f(v) -> float | None:
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return None if (not math.isfinite(x)) else x

    net_vex = _f(latest.get("net_vex"))
    iv30_latest = _f(latest.get("iv30"))
    iv30_prior = _f(prior.get("iv30"))
    if net_vex is None or iv30_latest is None or iv30_prior is None:
        return None
    iv30_5d_chg = iv30_latest - iv30_prior
    return round(-net_vex * iv30_5d_chg, 6)


# ---------------------------------------------------------------------------
# Per-source loaders (all return None / empty dict on missing stores)
# ---------------------------------------------------------------------------

def _load_gex_summaries(root: Path) -> dict[str, dict]:
    """
    Load LATEST row per ticker from data/polygon_gex/summary_<SYM>.parquet files.
    Returns {ticker: {field: value, ...}}.  Empty dict on missing directory.
    """
    gex_dir = root / "data" / "polygon_gex"
    if not gex_dir.exists():
        log.debug("polygon_gex directory not found — treating as missing (CI environment)")
        return {}
    out: dict[str, dict] = {}
    for path in sorted(gex_dir.glob("summary_*.parquet")):
        sym = path.stem.replace("summary_", "")
        try:
            df = pd.read_parquet(path)
        except Exception:
            log.debug("Cannot read %s — skipping", path)
            continue
        if df.empty:
            continue
        row = df.iloc[-1]
        asof_val = str(row.name.date()) if hasattr(row.name, "date") else str(row.name)[:10]
        spot = _safe_float(row.get("spot"))
        magnet_up = _safe_float(row.get("magnet_up"))
        magnet_down = _safe_float(row.get("magnet_down"))
        max_pain_raw = _safe_float(row.get("max_pain"))
        # Compute wall distance pcts as abs((magnet - spot) / spot * 100)
        wall_up = (
            abs((magnet_up - spot) / spot * 100)
            if spot and spot != 0 and magnet_up is not None
            else None
        )
        wall_down = (
            abs((magnet_down - spot) / spot * 100)
            if spot and spot != 0 and magnet_down is not None
            else None
        )
        max_pain_dist = (
            abs((max_pain_raw - spot) / spot * 100)
            if spot and spot != 0 and max_pain_raw is not None
            else None
        )
        out[sym] = {
            "iv30": _clean(row.get("iv30")),
            "gamma_regime": str(row.get("gamma_regime")) if row.get("gamma_regime") is not None else None,
            "dist_to_flip_pct": _clean(row.get("dist_to_flip_pct")),
            "wall_up_dist_pct": _clean(wall_up),
            "wall_down_dist_pct": _clean(wall_down),
            "max_pain_dist_pct": _clean(max_pain_dist),
            "n_strikes": _clean(row.get("n_strikes")),
            "tier": str(row.get("tier")) if row.get("tier") is not None else None,
            # pass the full row dict for gex_confirm (needs spot, flip, etc.)
            "_raw_row": {c: _clean(row.get(c)) for c in df.columns},
            "asof": asof_val,
        }
    return out


def _load_skew_snapshots(root: Path) -> dict[str, dict]:
    """
    Load LATEST per-ticker skew and compute 5d change.
    Returns {ticker: {skew, skew_5d_chg, asof}}.
    """
    snap_path = root / "data" / "options_skew" / "snapshots.parquet"
    if not snap_path.exists():
        log.debug("options_skew/snapshots.parquet not found")
        return {}
    try:
        df = pd.read_parquet(snap_path)
    except Exception:
        log.debug("Cannot read options_skew/snapshots.parquet")
        return {}
    if df.empty:
        return {}
    # Sort by date and pick latest per underlying
    df = df.sort_values("date")
    out: dict[str, dict] = {}
    for ticker, grp in df.groupby("underlying", sort=False):
        grp_sorted = grp.sort_values("date")
        if grp_sorted.empty:
            continue
        latest = grp_sorted.iloc[-1]
        latest_skew = _safe_float(latest.get("skew"))
        asof_val = str(latest.get("asof") or latest.get("date") or "")[:10]
        # 5d change: need at least LOOKBACK_TRADING_DAYS+1 rows
        skew_5d_chg = None
        if len(grp_sorted) >= LOOKBACK_TRADING_DAYS + 1:
            old_row = grp_sorted.iloc[-(LOOKBACK_TRADING_DAYS + 1)]
            old_skew = _safe_float(old_row.get("skew"))
            if latest_skew is not None and old_skew is not None:
                skew_5d_chg = _clean(latest_skew - old_skew)
        out[str(ticker)] = {
            "skew": _clean(latest_skew),
            "skew_5d_chg": skew_5d_chg,
            "asof": asof_val,
        }
    return out


def _load_ivspread_snapshots(root: Path) -> dict[str, dict]:
    """
    Load LATEST per-ticker ivspread_rel and compute 5d change.
    Returns {ticker: {ivspread_rel, ivspread_5d_chg, asof}}.
    """
    snap_path = root / "data" / "options_ivspread" / "snapshots.parquet"
    if not snap_path.exists():
        log.debug("options_ivspread/snapshots.parquet not found")
        return {}
    try:
        df = pd.read_parquet(snap_path)
    except Exception:
        log.debug("Cannot read options_ivspread/snapshots.parquet")
        return {}
    if df.empty:
        return {}
    df = df.sort_values("date")
    out: dict[str, dict] = {}
    for ticker, grp in df.groupby("underlying", sort=False):
        grp_sorted = grp.sort_values("date")
        if grp_sorted.empty:
            continue
        latest = grp_sorted.iloc[-1]
        latest_val = _safe_float(latest.get("ivspread_rel"))
        asof_val = str(latest.get("asof") or latest.get("date") or "")[:10]
        ivspread_5d_chg = None
        if len(grp_sorted) >= LOOKBACK_TRADING_DAYS + 1:
            old_row = grp_sorted.iloc[-(LOOKBACK_TRADING_DAYS + 1)]
            old_val = _safe_float(old_row.get("ivspread_rel"))
            if latest_val is not None and old_val is not None:
                ivspread_5d_chg = _clean(latest_val - old_val)
        out[str(ticker)] = {
            "ivspread_rel": _clean(latest_val),
            "ivspread_5d_chg": ivspread_5d_chg,
            "asof": asof_val,
        }
    return out


def _load_flow_summaries(root: Path) -> dict[str, dict]:
    """
    Load LATEST per-ticker flow data from data/options_flow/summary_<SYM>.parquet
    plus site/flow/<SYM>.json for fresh_premium_mn.
    Returns {ticker: {fresh_contracts, net_doi, doi_pc, zerodte_share,
                       fresh_premium_mn, asof}}.
    """
    flow_dir = root / "data" / "options_flow"
    site_flow_dir = root / "site" / "flow"
    if not flow_dir.exists():
        log.debug("options_flow directory not found — treating as missing (CI environment)")
        return {}
    out: dict[str, dict] = {}
    for path in sorted(flow_dir.glob("summary_*.parquet")):
        sym = path.stem.replace("summary_", "")
        try:
            df = pd.read_parquet(path)
        except Exception:
            log.debug("Cannot read %s — skipping", path)
            continue
        if df.empty:
            continue
        row = df.iloc[-1]
        asof_val = str(row.name.date()) if hasattr(row.name, "date") else str(row.name)[:10]
        # Try to get fresh_premium_mn from site/flow/<SYM>.json
        fresh_premium_mn = None
        site_json = site_flow_dir / f"{sym}.json"
        if site_json.exists():
            try:
                jdata = json.loads(site_json.read_text())
                new_pos = jdata.get("new_positions") or {}
                fresh_premium_mn = _safe_float(new_pos.get("fresh_premium_mn"))
            except Exception:
                pass
        out[sym] = {
            "fresh_contracts": _clean(row.get("fresh_contracts")),
            "net_doi": _clean(row.get("net_doi")),
            "doi_pc": _clean(row.get("doi_pc")),
            "zerodte_share": _clean(row.get("zerodte_share")),
            "fresh_premium_mn": _clean(fresh_premium_mn),
            "asof": asof_val,
        }
    return out


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_state(root: str | Path | None = None) -> pd.DataFrame:
    """
    Build the options entry state snapshot table.

    Parameters
    ----------
    root : path-like, optional
        Repo root. Defaults to three levels above this file
        (engine/options_entry_state.py → engine/ → repo root).

    Returns
    -------
    pd.DataFrame
        One row per ticker with all columns per RO-1 spec.
        Missing/absent source stores produce null fields + evidence_quality='thin'.
        Never raises; never emits fake-neutral values.

    Notes
    -----
    FORBIDDEN: this function must NEVER open data/us_board_ledger/retro_grades.parquet
    (A9 single-writer boundary).  The no-ledger-write guard test validates this.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    root = Path(root)
    today = _dt.date.today()

    # Load all sources (fail-soft on each)
    gex_data = _load_gex_summaries(root)
    skew_data = _load_skew_snapshots(root)
    ivspread_data = _load_ivspread_snapshots(root)
    flow_data = _load_flow_summaries(root)

    # Load the latest chain parquet ONCE for the whole board (render-budget fix: avoids
    # re-reading the whole-market chain parquet ~350 times in the per-ticker loop).
    _chain_date, _chain_by_ticker = _load_latest_chain_ovc(root)

    opex_days = _opex_days_today()

    # Universe = union of all tickers found across all sources
    tickers = sorted(set(gex_data) | set(skew_data) | set(ivspread_data) | set(flow_data))
    if not tickers:
        log.info("No tickers found in any source — returning empty state table")
        tickers = []

    rows = []
    for ticker in tickers:
        gex = gex_data.get(ticker) or {}
        skew = skew_data.get(ticker) or {}
        ivspread = ivspread_data.get(ticker) or {}
        flow = flow_data.get(ticker) or {}

        src_gex_asof = gex.get("asof") or None
        src_skew_asof = skew.get("asof") or None
        src_ivspread_asof = ivspread.get("asof") or None
        src_flow_asof = flow.get("asof") or None

        eq = _evidence_quality(src_gex_asof, src_skew_asof, src_ivspread_asof, src_flow_asof, today)

        # ---- GEX-derived fields ----------------------------------------
        iv30 = gex.get("iv30")
        gamma_regime = gex.get("gamma_regime")
        dist_to_flip_pct = gex.get("dist_to_flip_pct")
        wall_up_dist_pct = gex.get("wall_up_dist_pct")
        wall_down_dist_pct = gex.get("wall_down_dist_pct")
        max_pain_dist_pct = gex.get("max_pain_dist_pct")

        # gamma_regime_structurally_constant: True when a gamma_regime value is present.
        # Audit #29: single-name gamma_regime is structurally constant per ticker
        # (the GEX resolver consistently categorises each name in the same regime
        # over the current ~19-day history).  This caveat column documents that
        # the gamma_regime value should not be interpreted as a time-varying signal.
        gamma_regime_structurally_constant = gamma_regime is not None

        # ---- iv_rank fields (STRUCTURALLY NULL until A9 IV-backfill PR) ---
        # A9 ruling: iv_rank_252 requires ~252 trading days of per-name IV history.
        # The backfill wave (W-E0 in OPTIONS_ALPHA_MASTERPLAN) has not yet shipped.
        # These columns are emitted as null with an architectural comment — this is
        # NOT a "thin" data quality classification; the columns are absent by design.
        iv_rank_252: float | None = None        # A9: structurally null until backfill PR
        iv_rank_5d_chg: float | None = None     # A9: structurally null until backfill PR

        # ---- gex_confirm verdict (reuse existing engine) -------------------
        gex_confirm_verdict: str | None = None
        if gex:
            raw_row = gex.get("_raw_row") or {}
            # Build the gex dict that gex_confirm.assess() expects (flat summary shape)
            gex_payload = {
                "tier": gex.get("tier"),
                "n_strikes": raw_row.get("n_strikes"),
                "gamma_regime": gamma_regime,
                "spot": raw_row.get("spot"),
                "gamma_flip": raw_row.get("gamma_flip"),
                "dist_to_flip_pct": dist_to_flip_pct,
                # gex_confirm expects call_wall / put_wall via vol_hole sigma shape;
                # we pass magnet_up/down as call/put wall equivalents from the summary
                "call_wall": raw_row.get("magnet_up"),
                "put_wall": raw_row.get("magnet_down"),
            }
            try:
                result = gex_confirm.assess(gex_payload, opex_days=opex_days)
                if result is not None:
                    gex_confirm_verdict = result.get("verdict")
            except Exception:
                log.debug("gex_confirm.assess failed for %s — setting verdict to None", ticker)

        # ---- pin_risk -------------------------------------------------------
        # Definition (threshold = PIN_RISK_WALL_PCT = 2.0%):
        #   opex_days is not None AND opex_days <= 5
        #   AND gamma_regime == 'long'
        #   AND at least one of (wall_up_dist_pct, wall_down_dist_pct, max_pain_dist_pct)
        #       is non-null AND <= PIN_RISK_WALL_PCT
        # The 2% threshold approximates ~1 typical ATM daily move; within this band
        # dealer charm/vanna effects can mechanically pin or release spot at expiry.
        pin_risk: bool | None = None
        if opex_days is not None and gamma_regime is not None:
            if opex_days <= 5 and gamma_regime == "long":
                wall_candidates = [
                    d for d in [wall_up_dist_pct, wall_down_dist_pct, max_pain_dist_pct]
                    if d is not None
                ]
                if wall_candidates:
                    pin_risk = bool(min(wall_candidates) <= PIN_RISK_WALL_PCT)

        # ---- W-OVC: chain-derived columns (fail-soft — null on missing chain) ---
        # front7_charm_share, front7_gex_share, signed_vanna_pressure (from latest chain)
        # Uses pre-loaded chain split (loaded once above) to avoid re-reading ~350×.
        _ticker_sub = _chain_by_ticker.get(ticker)
        ovc = (
            _compute_chain_ovc_from_sub(_ticker_sub, _chain_date)
            if (_ticker_sub is not None and _chain_date is not None)
            else {"front7_charm_share": None, "front7_gex_share": None, "signed_vanna_pressure": None}
        )
        front7_charm_share = ovc.get("front7_charm_share")
        front7_gex_share = ovc.get("front7_gex_share")
        signed_vanna_pressure = ovc.get("signed_vanna_pressure")

        # ---- W-OVC: vanna_hedge_5d (from summary net_vex × iv30 history) ----
        vanna_hedge_5d = _compute_vanna_hedge_5d(root, ticker)

        # ---- W-OVC: root_class --------------------------------------------------
        # display-only context for front7_*_share interpretation (RUL-OVC-6).
        # ETF-slice sign of front7_charm_share is era-unstable — root_class is mandatory
        # alongside any display use of the front7 columns.
        root_class: str = _root_class(ticker)

        # ---- as_of for the overall row: latest non-null source date --------
        source_dates = [
            d for d in [src_gex_asof, src_skew_asof, src_ivspread_asof, src_flow_asof]
            if d
        ]
        row_asof = max(source_dates) if source_dates else None

        rows.append({
            "as_of": row_asof,
            "ticker": ticker,
            "iv30": iv30,
            # iv_rank columns: A9 structurally null (see comment above)
            "iv_rank_252": iv_rank_252,
            "iv_rank_5d_chg": iv_rank_5d_chg,
            "ivspread_rel": ivspread.get("ivspread_rel"),
            "ivspread_5d_chg": ivspread.get("ivspread_5d_chg"),
            "skew": skew.get("skew"),
            "skew_5d_chg": skew.get("skew_5d_chg"),
            "net_doi": flow.get("net_doi"),
            "doi_pc": flow.get("doi_pc"),
            "fresh_contracts": flow.get("fresh_contracts"),
            "fresh_premium_mn": flow.get("fresh_premium_mn"),
            "zerodte_share": flow.get("zerodte_share"),
            "gamma_regime": gamma_regime,
            "gamma_regime_structurally_constant": gamma_regime_structurally_constant,
            "dist_to_flip_pct": dist_to_flip_pct,
            "wall_up_dist_pct": wall_up_dist_pct,
            "wall_down_dist_pct": wall_down_dist_pct,
            "max_pain_dist_pct": max_pain_dist_pct,
            "opex_days": opex_days,
            "pin_risk": pin_risk,
            "gex_confirm_verdict": gex_confirm_verdict,
            "evidence_quality": eq,
            "src_gex_asof": src_gex_asof,
            "src_skew_asof": src_skew_asof,
            "src_ivspread_asof": src_ivspread_asof,
            "src_flow_asof": src_flow_asof,
            # W-OVC additions (display-only, RO-2)
            "front7_charm_share": front7_charm_share,
            "front7_gex_share": front7_gex_share,
            "signed_vanna_pressure": signed_vanna_pressure,
            "vanna_hedge_5d": vanna_hedge_5d,
            "root_class": root_class,
        })

    if not rows:
        # Return empty DataFrame with correct schema
        return pd.DataFrame(columns=[
            "as_of", "ticker", "iv30", "iv_rank_252", "iv_rank_5d_chg",
            "ivspread_rel", "ivspread_5d_chg", "skew", "skew_5d_chg",
            "net_doi", "doi_pc", "fresh_contracts", "fresh_premium_mn", "zerodte_share",
            "gamma_regime", "gamma_regime_structurally_constant", "dist_to_flip_pct",
            "wall_up_dist_pct", "wall_down_dist_pct", "max_pain_dist_pct",
            "opex_days", "pin_risk", "gex_confirm_verdict", "evidence_quality",
            "src_gex_asof", "src_skew_asof", "src_ivspread_asof", "src_flow_asof",
            # W-OVC
            "front7_charm_share", "front7_gex_share", "signed_vanna_pressure",
            "vanna_hedge_5d", "root_class",
        ])

    df = pd.DataFrame(rows)
    log.info(
        "options_entry_state: built %d rows (full=%d, partial=%d, thin=%d, stale=%d)",
        len(df),
        (df["evidence_quality"] == "full").sum(),
        (df["evidence_quality"] == "partial").sum(),
        (df["evidence_quality"] == "thin").sum(),
        (df["evidence_quality"] == "stale").sum(),
    )
    return df
