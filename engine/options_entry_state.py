"""engine/options_entry_state.py — display-tier options entry state fusion table.

RO-1 (OPTIONS_NW_ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE §2): builds a per-ticker snapshot
table by fusing LATEST per-ticker data from all available options sources.  This is a
**display-only raw-fields fusion table** — it contains no composite/score/rank columns
(RO-2 / Signal Commons R3) and no forward-return columns.  It is NOT a forward ledger;
the nightly rebuilds it idempotently from LATEST source rows.

Sources (all read-only):
  - data/polygon_gex/summary_<SYM>.parquet     → gamma_regime, dist_to_flip_pct,
                                                  magnet_up/down → wall distance pcts,
                                                  iv30, max_pain (if present)
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
  opex_days,
  pin_risk                       — bool: opex_days<=5 AND gamma_regime=='long' AND
                                   min(wall_up_dist_pct, wall_down_dist_pct,
                                       max_pain_dist_pct) <= PIN_RISK_WALL_PCT (2.0%)
                                   THRESHOLD RATIONALE: 2% is approximately 1 ATM daily move
                                   on most large-caps; within this band dealer gamma/charm
                                   effects can mechanically pin or release spot at expiry,
  gex_confirm_verdict,
  evidence_quality               — 'full'/'partial'/'thin'/'stale' per-row freshness,
  src_gex_asof, src_skew_asof, src_ivspread_asof, src_flow_asof.

Missing/gitignored stores → null fields + evidence_quality='thin'.  NEVER raises on
missing stores; NEVER emits fake-neutral values for absent data.

FORBIDDEN: do NOT open data/us_board_ledger/retro_grades.parquet (A9 single-writer).
"""
from __future__ import annotations

import datetime as _dt
import glob
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import gex_confirm
from engine.opex import expiration_days

log = logging.getLogger(__name__)

# Pin-risk wall threshold (2.0% — see docstring).
PIN_RISK_WALL_PCT = 2.0

# Number of trading days for the "5d change" look-back.
LOOKBACK_TRADING_DAYS = 5

# Evidence-quality stale threshold: source as_of older than this many calendar days.
STALE_CALENDAR_DAYS = 3


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

        # gamma_regime_structurally_constant: True when GEX data is present.
        # Audit #29: single-name gamma_regime is structurally constant per ticker
        # (the GEX resolver consistently categorises each name in the same regime
        # over the current ~19-day history).  This caveat column documents that
        # the gamma_regime value should not be interpreted as a time-varying signal.
        gamma_regime_structurally_constant = bool(gex)

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
