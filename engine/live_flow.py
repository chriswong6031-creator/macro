"""engine/live_flow.py — intraday options-flow event engine (DISPLAY-TIER, hermetic).

Pure function: no network calls, no clock reads — every input is injected by the
caller (live_flow_poller.py).  Takes raw bulk_trade_quote call+put DataFrames for a
poll batch and produces three outputs per the FEED CONTRACT v1:

  events       — notable per-contract prints (premium floor or z252 gate)
  unusual_names — per-root running gross-premium vs EOD-252 baseline
  heat         — per-sector/group aggregates over ALL signed prints

EPISTEMIC LAWS (binding):
  • Display-tier only.  The words "signal" and "validated" must NOT appear in any
    user-facing string produced by this module.
  • Direction is soft — always "~buy" / "~sell" with signing_source="tape".
  • 0DTE prints are included and bucket-labeled; never highlighted or glorified.
  • "Unusual" is always a labeled heuristic, not a validated edge.
  • DEBRAND — no vendor or competitor names in any user-facing string.

Bucket functions and signing are IMPORTED from engine.tape_flow and
engine.flow_signing — never re-derived here.

Tide accumulator contract (day-state keys added by this module):
  market_tide_minutes  : {HH:MM → {ncp, npp, gross, vol}}  cumulative signed prem per minute
  sector_tide_minutes  : {group → {ncp, npp, gross, minutes: {HH:MM → {ncp, npp}}}}
  dte_tide_minutes     : {bucket → [{t, ncp, npp}]}         cumulative per DTE bucket per minute
  root_minutes         : {root → {HH:MM → {ncp, npp, vol}}} per-root cumulative minute series
  root_strikes         : {root → {strike → {call_prem, put_prem, vol}}}  day rollup
  root_expiries        : {root → {exp → {call_prem, put_prem, vol}}}     day rollup
  root_top_contracts   : {root → [{right, exp, strike, premium, vol, vol_gt_oi}x<=10]}
  sweep_events         : {(exp,strike,right) → [{ts, exchange}]}  pending sweep cluster

NCP / NPP convention (tide):
  ncp = cumulative net call premium: calls signed ~buy add (+), calls signed ~sell subtract (−).
  npp = cumulative net put premium:  puts  signed ~buy add (+), puts  signed ~sell subtract (−).
  Both are soft (signing_source=tape; direction is approximate, not directional advice).
  This is the standard Lee-Ready tape-signing convention accumulated intraday.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from engine import flow_signing
from engine.tape_flow import _dte_bucket, _moneyness_bucket, _compute_signed_moneyness
from engine.spotlight import GICS_TO_ETF
from engine.group_flow import _SECTOR_ZH

log = logging.getLogger(__name__)

# ── notability gate defaults ──────────────────────────────────────────────────
DEFAULT_ETF_FLOOR    = 1_000_000   # $ gross premium floor for ETF anchors
DEFAULT_NAME_FLOOR   = 250_000     # $ gross premium floor for single names

# "~buy" / "~sell" threshold: if ask-side share >= this, side="~buy"; if
# bid-side share >= this, side="~sell"; else "mixed".  60% threshold.
_SIDE_THRESHOLD = 0.60

# Max events retained in feed (contract: trailing 24h, cap 2000)
MAX_EVENTS = 2000

# GICS-sector name → canonical group label (for heat aggregation)
# ETFs map to "Index/ETF" / "指数/ETF"
_ETF_ANCHORS_SET = {
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "HYG",
    "XLF", "XLE", "XLU", "XLK", "XLV", "XLI", "XLB", "XLY",
    "XLP", "XLRE", "XLC", "KRE", "SMH", "XBI", "ARKK",
}

_ETF_GROUP    = "Index/ETF"
_ETF_GROUP_ZH = "指数/ETF"
_OTHER_GROUP    = "Other"
_OTHER_GROUP_ZH = "其他"


# ── sector mapping ────────────────────────────────────────────────────────────

def _root_to_group(root: str, names_sectors: dict[str, tuple[str, str]] | None = None
                   ) -> tuple[str, str]:
    """Return (group_en, group_zh) for a root symbol.

    Priority:
      1. Known ETF anchors → "Index/ETF"
      2. GICS sector from names_sectors (engine.equity_factors._names_sectors vocabulary)
         resolved via GICS_TO_ETF keys → canonical GICS sector + _SECTOR_ZH
      3. "Other" / "其他"
    """
    r = root.upper()
    if r in _ETF_ANCHORS_SET:
        return _ETF_GROUP, _ETF_GROUP_ZH
    if names_sectors:
        entry = names_sectors.get(r)
        if entry:
            _, sector = entry
            if sector and sector != "—":
                zh = _SECTOR_ZH.get(sector, sector)
                return sector, zh
    return _OTHER_GROUP, _OTHER_GROUP_ZH


def _load_names_sectors() -> dict[str, tuple[str, str]]:
    """Load name→(display_name, GICS_sector) map; returns {} on any error."""
    try:
        from engine.equity_factors import _names_sectors
        return _names_sectors()
    except Exception as e:  # noqa: BLE001
        log.debug("live_flow: names_sectors unavailable: %s", e)
        return {}


# ── signing helpers ───────────────────────────────────────────────────────────

def _sign_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Apply quote_rule_sign (Lee-Ready) to a bulk_trade_quote DataFrame.

    Uses prev_price within each contract (expiration, strike, right) to resolve
    mid-price ambiguity per the tick-fallback convention.  Returns df with 'sign'
    column added.
    """
    if df.empty:
        df = df.copy()
        df["sign"] = pd.Series(dtype=float)
        return df

    df = df.copy()
    for col in ("price", "bid", "ask", "size"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Filter obviously bad NBBO
    valid = (df["bid"].notna() & (df["bid"] > 0) &
             df["ask"].notna() & (df["ask"] >= df["bid"]))
    df = df[valid].copy()
    if df.empty:
        df["sign"] = pd.Series(dtype=float)
        return df

    contract_cols = [c for c in ("expiration", "strike", "right") if c in df.columns]
    if contract_cols and "trade_timestamp" in df.columns:
        df = df.sort_values(contract_cols + ["trade_timestamp"]).copy()
        df["_prev_price"] = df.groupby(contract_cols)["price"].shift(1)
    else:
        df["_prev_price"] = df["price"].shift(1)

    df["sign"] = flow_signing.quote_rule_sign(
        df["price"].to_numpy(),
        df["bid"].to_numpy(),
        df["ask"].to_numpy(),
        df["_prev_price"].to_numpy(),
    )
    df = df.drop(columns=["_prev_price"], errors="ignore")
    return df


# ── event-id helpers ─────────────────────────────────────────────────────────

def _event_id(session_date: str, root: str, exp: str, strike: float,
              right: str, batch_seq_max: Any) -> str:
    """Stable 16-char hex event id.

    Inputs: session_date, root, exp (YYYY-MM-DD), strike (float),
            right ("C"|"P"), batch_seq_max (max sequence in this batch for the
            contract — stable within a batch; ties to the specific print cluster).
    """
    key = f"{session_date}|{root.upper()}|{exp}|{strike:.3f}|{right.upper()}|{batch_seq_max}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]  # noqa: S324 — non-cryptographic id


# ── coalescing ────────────────────────────────────────────────────────────────

def _coalesce_batch(df: pd.DataFrame, session_date: str) -> pd.DataFrame:
    """Coalesce signed prints per contract within the poll batch.

    Groups by (expiration, strike, right) and computes:
      n_prints    — count of rows
      size        — total contracts
      premium     — sum(price * size * 100)
      avg_price   — premium-weighted average price
      ask_share   — fraction of premium from ask-side prints
      bid_share   — fraction of premium from bid-side prints
      seq_max     — max sequence (for event id stability)
      ts          — latest trade_timestamp in the batch for this contract
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["_premium_row"] = df["price"] * df["size"] * 100.0
    df["_ask_prem"] = df["_premium_row"] * (df["sign"] > 0).astype(float)
    df["_bid_prem"] = df["_premium_row"] * (df["sign"] < 0).astype(float)

    contract_cols = [c for c in ("expiration", "strike", "right") if c in df.columns]
    if not contract_cols:
        return pd.DataFrame()

    grp = df.groupby(contract_cols, as_index=False).agg(
        n_prints=("price", "count"),
        size=("size", "sum"),
        premium=("_premium_row", "sum"),
        ask_prem=("_ask_prem", "sum"),
        bid_prem=("_bid_prem", "sum"),
        avg_price=("price", "mean"),
        ts=("trade_timestamp", "max"),
        seq_max=("sequence", "max") if "sequence" in df.columns else ("price", "max"),
    ).copy()

    # Compute side
    total_prem = grp["premium"].clip(lower=0)
    ask_share = np.where(total_prem > 0, grp["ask_prem"] / total_prem, 0.0)
    bid_share = np.where(total_prem > 0, grp["bid_prem"] / total_prem, 0.0)
    side = np.where(ask_share >= _SIDE_THRESHOLD, "~buy",
                    np.where(bid_share >= _SIDE_THRESHOLD, "~sell", "mixed"))
    grp["side"] = side
    grp["ask_share"] = ask_share

    # Root column
    if "root" in df.columns:
        root_val = df["root"].iloc[0].upper() if not df["root"].empty else ""
        grp["root"] = root_val

    # Standardise expiration format
    if "expiration" in grp.columns:
        grp["expiration"] = pd.to_datetime(grp["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")

    return grp


# ── DTE / moneyness for a coalesced row ──────────────────────────────────────

def _enrich_contract_row(row: pd.Series, session_date: str,
                         oi_prev: pd.DataFrame | None,
                         contract_vol: dict | None = None,
                         prev_close: float | None = None) -> dict:
    """Compute dte, dte_bucket, mny_bucket, vol_gt_oi, zerodte from a coalesced row.

    contract_vol : cumulative day-volume dict keyed by (exp, strike, right) —
                   used for the vol_gt_oi check (FIX 1).  When None falls back
                   to the per-batch coalesced size (legacy behaviour).
    prev_close   : prior-session underlying close; used for real moneyness
                   bucketing (FIX 3).  None → 'unknown'.
    """
    exp_str = str(row.get("expiration", ""))
    try:
        exp_dt = pd.Timestamp(exp_str)
        sess_dt = pd.Timestamp(session_date)
        dte_val = max(int((exp_dt - sess_dt).days), 0)
    except Exception:  # noqa: BLE001
        dte_val = 0

    dte_bucket_val = str(_dte_bucket(pd.Series([dte_val])).iloc[0])
    zerodte = dte_bucket_val == "0d"

    # FIX 3 — honest moneyness via prior-session close
    mny_bucket_val = "unknown"
    if prev_close is not None and prev_close > 0:
        try:
            strike_val = float(row.get("strike", 0))
            right_val  = str(row.get("right", "C")).upper()[:1]
            if strike_val > 0:
                tmp = pd.DataFrame([{
                    "underlying_price": prev_close,
                    "strike": strike_val,
                    "right": right_val,
                }])
                signed_money = _compute_signed_moneyness(tmp)
                mny_bucket_val = str(_moneyness_bucket(signed_money).iloc[0])
        except Exception as e:  # noqa: BLE001
            log.debug("live_flow: moneyness compute failed: %s", e)
            mny_bucket_val = "unknown"

    # FIX 1 — vol_gt_oi: use cumulative day-volume from state, not per-batch size
    vol_gt_oi_val = None
    if oi_prev is not None and not oi_prev.empty:
        try:
            exp_norm = pd.to_datetime(exp_str, errors="coerce").strftime("%Y-%m-%d")
            right_norm = str(row.get("right", "C")).upper()[:1]
            strike_val = float(row.get("strike", 0))
            oi_match = oi_prev[
                (pd.to_datetime(oi_prev.get("expiration", pd.Series(dtype=str)),
                                errors="coerce").dt.strftime("%Y-%m-%d") == exp_norm) &
                (oi_prev.get("right", pd.Series(dtype=str)).astype(str).str.upper().str[:1] == right_norm) &
                (pd.to_numeric(oi_prev.get("strike", pd.Series(dtype=float)),
                               errors="coerce") == strike_val)
            ]
            if not oi_match.empty and "open_interest" in oi_match.columns:
                oi_val = float(oi_match["open_interest"].iloc[0])
                # FIX 1: use cumulative day volume from state (not per-batch coalesced size)
                contract_key = (exp_norm, strike_val, right_norm)
                if contract_vol is not None and contract_key in contract_vol:
                    cum_vol = float(contract_vol[contract_key])
                else:
                    # fallback: use the per-batch coalesced size
                    cum_vol = float(row.get("size", 0))
                vol_gt_oi_val = bool(cum_vol > oi_val)
        except Exception as e:  # noqa: BLE001
            log.debug("live_flow: vol_gt_oi check failed: %s", e)

    return {
        "dte": dte_val,
        "dte_bucket": dte_bucket_val,
        "mny_bucket": mny_bucket_val,
        "vol_gt_oi": vol_gt_oi_val,
        "zerodte": zerodte,
    }


# ── notability gate ───────────────────────────────────────────────────────────

def _is_notable(premium: float, root: str, baselines: dict | None,
                etf_floor: int, name_floor: int,
                etf_set: set[str]) -> tuple[bool, float | None, str]:
    """Return (notable, premium_z, baseline_source).

    Gates:
      1. premium >= floor (always available — floor varies by ETF vs name)
      2. OR premium_z >= 3 where root's data/tape_flow baseline is present
    baseline_source: "z252" | "floor"
    premium_z: float or None
    """
    floor = etf_floor if root.upper() in etf_set else name_floor
    prem_z: float | None = None
    source = "floor"

    if baselines and root.upper() in baselines:
        b = baselines[root.upper()]
        mean_val = b.get("mean")
        std_val  = b.get("std")
        if mean_val is not None and std_val is not None and float(std_val) > 0:
            prem_z = (premium - float(mean_val)) / float(std_val)
            source = "z252"
            if prem_z >= 3.0:
                return True, round(prem_z, 2), source

    if premium >= floor:
        return True, (round(prem_z, 2) if prem_z is not None else None), "floor"

    return False, (round(prem_z, 2) if prem_z is not None else None), source


# ── main engine ───────────────────────────────────────────────────────────────

def process_batch(
    calls_df: pd.DataFrame | None,
    puts_df: pd.DataFrame | None,
    session_date: str,
    batch_ts: str,
    prior_state: dict | None = None,
    oi_prev: pd.DataFrame | None = None,
    baselines: dict | None = None,
    etf_floor: int = DEFAULT_ETF_FLOOR,
    name_floor: int = DEFAULT_NAME_FLOOR,
    etf_anchors: list[str] | None = None,
    names_sectors: dict[str, tuple[str, str]] | None = None,
    prev_close: float | None = None,
) -> dict:
    """Process one poll batch → events, unusual_names, heat, updated state.

    Parameters
    ----------
    calls_df / puts_df : raw bulk_trade_quote output for this batch (may be None/empty).
    session_date       : "YYYY-MM-DD" — the trading day.
    batch_ts           : ISO8601Z timestamp for this batch (injected — no clock reads).
    prior_state        : dict from a previous cycle; keys:
                           emitted_ids   : set of already-emitted event ids for today
                           contract_vol  : {(exp,strike,right): cumulative_day_vol}
                           notability_history : {(exp,strike,right): n_cycles_notable}
                           seen_sequences : {(exp,strike,right): max_sequence_seen}
    oi_prev            : t-1 OI frame (columns: expiration, strike, right, open_interest).
    baselines          : {ROOT: {mean, std, n_obs, computed_asof}} from build_live_flow_baselines.
    etf_floor          : minimum premium for ETF anchors.
    name_floor         : minimum premium for single names.
    etf_anchors        : set of ETF root symbols.
    names_sectors      : {ticker: (name, GICS_sector)} — for group labeling.
    prev_close         : prior-session underlying close for honest moneyness (FIX 3).
                         None → mny_bucket='unknown'.

    Returns
    -------
    dict with keys: events, unusual_names, heat, state, meta_notes
    """
    etf_set: set[str] = set(s.upper() for s in (etf_anchors or _ETF_ANCHORS_SET))

    # Merge prior state or start fresh
    ps = prior_state or {}
    emitted_ids: set[str]            = set(ps.get("emitted_ids", set()))
    contract_vol: dict               = dict(ps.get("contract_vol", {}))
    notability_hist: dict            = dict(ps.get("notability_history", {}))
    # running root-level gross premium this session
    root_gross_today: dict[str, float] = dict(ps.get("root_gross_today", {}))
    # FIX 2 — per-contract max sequence seen (row-level dedup for overlapping windows)
    seen_sequences: dict             = dict(ps.get("seen_sequences", {}))

    # ── Tide accumulator state (persisted across cycles for day-cumulative values) ──
    # market_tide_minutes: {HH:MM → {ncp, npp, gross, vol}}
    market_tide_minutes: dict        = dict(ps.get("market_tide_minutes", {}))
    # sector_tide: {group → {ncp, npp, gross, group_zh, minutes: {HH:MM → {ncp, npp}}}}
    sector_tide: dict                = {k: dict(v) for k, v in ps.get("sector_tide", {}).items()}
    for grp in sector_tide:
        if "minutes" in sector_tide[grp]:
            sector_tide[grp]["minutes"] = dict(sector_tide[grp]["minutes"])
    # dte_tide: {bucket → {HH:MM → {ncp, npp}}}
    dte_tide: dict                   = {k: dict(v) for k, v in ps.get("dte_tide", {}).items()}
    # per-root minute series: {root → {HH:MM → {ncp, npp, vol}}}
    root_minutes: dict               = {k: dict(v) for k, v in ps.get("root_minutes", {}).items()}
    # per-root strike rollups: {root → {strike_str → {call_prem, put_prem, vol}}}
    root_strikes: dict               = {k: dict(v) for k, v in ps.get("root_strikes", {}).items()}
    # per-root expiry rollups: {root → {exp → {call_prem, put_prem, vol}}}
    root_expiries: dict              = {k: dict(v) for k, v in ps.get("root_expiries", {}).items()}
    # per-root top_contracts: {root → [{right, exp, strike, premium, vol, vol_gt_oi}]}
    root_top_contracts: dict         = {k: list(v) for k, v in ps.get("root_top_contracts", {}).items()}
    # sweep cluster tracking: {(exp, strike, right) key → [{ts_epoch, exchange}]}
    sweep_clusters: dict             = dict(ps.get("sweep_clusters", {}))

    # Names/sectors for group labeling
    ns = names_sectors if names_sectors is not None else _load_names_sectors()

    # ── 1. Combine + sign ─────────────────────────────────────────────────────
    frames = []
    for df, right_label in ((calls_df, "C"), (puts_df, "P")):
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            continue
        dfc = df.copy()
        if "right" not in dfc.columns:
            dfc["right"] = right_label
        frames.append(dfc)

    if not frames:
        return {
            "events": [],
            "unusual_names": [],
            "heat": [],
            "state": {
                "emitted_ids": emitted_ids,
                "contract_vol": contract_vol,
                "notability_history": notability_hist,
                "root_gross_today": root_gross_today,
                "seen_sequences": seen_sequences,
                "market_tide_minutes": market_tide_minutes,
                "sector_tide": sector_tide,
                "dte_tide": dte_tide,
                "root_minutes": root_minutes,
                "root_strikes": root_strikes,
                "root_expiries": root_expiries,
                "root_top_contracts": root_top_contracts,
                "sweep_clusters": sweep_clusters,
            },
            "meta_notes": ["batch empty — no prints"],
        }

    combined = pd.concat(frames, ignore_index=True)

    # FIX 2 — row-level sequence dedup before any accumulation.
    # For overlapping windows (time_window mode) and full-day re-pulls (full_day mode)
    # rows already processed in a previous cycle are identified by their sequence number
    # being <= the max sequence already seen for that contract.
    # This makes both overlap and idempotent re-pull safe.
    if "sequence" in combined.columns:
        contract_cols_dedup = [c for c in ("expiration", "strike", "right") if c in combined.columns]
        if contract_cols_dedup:
            # Vectorised key columns (avoid per-row .loc — SPY-scale frames are ~1M rows).
            seq_arr   = pd.to_numeric(combined["sequence"], errors="coerce")
            exp_key   = combined.get("expiration", pd.Series("", index=combined.index)).astype(str)
            stk_num   = pd.to_numeric(combined.get("strike", pd.Series(0.0, index=combined.index)),
                                      errors="coerce").fillna(0.0).astype(float)
            right_key = (combined.get("right", pd.Series("C", index=combined.index))
                         .astype(str).str.upper().str[:1])
            keys      = list(zip(exp_key, stk_num, right_key))
            # Drop rows whose sequence is <= the max already seen for that contract.
            if seen_sequences:
                max_seen_arr = pd.Series(
                    [seen_sequences.get(k) for k in keys], index=combined.index, dtype="float64")
                drop_mask = seq_arr.notna() & max_seen_arr.notna() & (seq_arr <= max_seen_arr)
                if drop_mask.any():
                    combined = combined[~drop_mask].copy()
                    keys     = [k for k, drop in zip(keys, drop_mask.to_numpy()) if not drop]
                    seq_arr  = seq_arr[~drop_mask]
        # Advance seen_sequences with the max surviving sequence per contract.
        if not combined.empty and "sequence" in combined.columns:
            surv = pd.DataFrame({"_k": keys, "_s": seq_arr.to_numpy()}).dropna(subset=["_s"])
            if not surv.empty:
                for k, s in surv.groupby("_k")["_s"].max().items():
                    if k not in seen_sequences or s > seen_sequences[k]:
                        seen_sequences[k] = float(s)

    combined = _sign_batch(combined)
    if combined.empty:
        return {
            "events": [],
            "unusual_names": [],
            "heat": [],
            "state": {
                "emitted_ids": emitted_ids,
                "contract_vol": contract_vol,
                "notability_history": notability_hist,
                "root_gross_today": root_gross_today,
                "seen_sequences": seen_sequences,
                "market_tide_minutes": market_tide_minutes,
                "sector_tide": sector_tide,
                "dte_tide": dte_tide,
                "root_minutes": root_minutes,
                "root_strikes": root_strikes,
                "root_expiries": root_expiries,
                "root_top_contracts": root_top_contracts,
                "sweep_clusters": sweep_clusters,
            },
            "meta_notes": ["batch empty after signing filter"],
        }

    # Root
    root = str(combined["root"].iloc[0]).upper() if "root" in combined.columns else "UNKNOWN"

    # Accumulate root gross premium for unusual_names
    combined["_prem_row"] = (combined["price"] * combined["size"] * 100.0).fillna(0.0)
    batch_root_gross = float(combined["_prem_row"].sum())
    root_gross_today[root] = root_gross_today.get(root, 0.0) + batch_root_gross

    # ── 2. Heat (group aggregates — ALL signed prints, not just notable) ──────
    group_en, group_zh = _root_to_group(root, ns)
    ask_mask = combined["sign"] > 0
    bid_mask  = combined["sign"] < 0
    gross_prem = float(combined["_prem_row"].sum())
    ask_prem   = float(combined.loc[ask_mask, "_prem_row"].sum())
    bid_prem   = float(combined.loc[bid_mask, "_prem_row"].sum())
    net_signed = ask_prem - bid_prem
    call_prem  = float(combined.loc[combined["right"].str.upper().str[:1] == "C", "_prem_row"].sum())
    call_share = (call_prem / gross_prem) if gross_prem > 0 else 0.0
    n_events_batch = int(len(combined))

    heat_row = {
        "group":             group_en,
        "group_zh":          group_zh,
        "gross_premium":     round(gross_prem, 0),
        "net_signed_premium_soft": round(net_signed, 0),
        "call_prem_share":   round(call_share, 4),
        "n_events":          n_events_batch,
        "top":               [],  # enriched by caller aggregating across roots
        "_root":             root,  # internal — stripped before output
    }

    # ── 3. Coalesce prints per contract ──────────────────────────────────────
    coalesced = _coalesce_batch(combined, session_date)
    if coalesced.empty:
        return {
            "events": [],
            "unusual_names": [_unusual_row(root, root_gross_today.get(root, 0.0),
                                           baselines)],
            "heat": [heat_row],
            "state": {
                "emitted_ids": emitted_ids,
                "contract_vol": contract_vol,
                "notability_history": notability_hist,
                "root_gross_today": root_gross_today,
                "seen_sequences": seen_sequences,
                "market_tide_minutes": market_tide_minutes,
                "sector_tide": sector_tide,
                "dte_tide": dte_tide,
                "root_minutes": root_minutes,
                "root_strikes": root_strikes,
                "root_expiries": root_expiries,
                "root_top_contracts": root_top_contracts,
                "sweep_clusters": sweep_clusters,
            },
            "meta_notes": [],
        }

    # ── 4. Accumulate cumulative day volume per contract ──────────────────────
    for _, row in coalesced.iterrows():
        contract_key = (
            str(row.get("expiration", "")),
            float(row.get("strike", 0)),
            str(row.get("right", "C")).upper()[:1],
        )
        contract_vol[contract_key] = (
            contract_vol.get(contract_key, 0.0) + float(row.get("size", 0))
        )

    # ── 4b. Tide accumulation (market, sector, DTE, per-root minute/strike/expiry) ─
    _accumulate_tide(
        combined=combined,
        root=root,
        group_en=group_en,
        group_zh=group_zh,
        batch_ts=batch_ts,
        session_date=session_date,
        market_tide_minutes=market_tide_minutes,
        sector_tide=sector_tide,
        dte_tide=dte_tide,
        root_minutes=root_minutes,
        root_strikes=root_strikes,
        root_expiries=root_expiries,
        sweep_clusters=sweep_clusters,
    )

    # ── 4c. Sweep-like detection on coalesced rows ────────────────────────────
    # Flags are attached to events in step 5.
    sweep_flags = _detect_sweeps(combined, sweep_clusters)

    # ── 5. Notability gate + event construction ───────────────────────────────
    new_events: list[dict] = []
    for _, row in coalesced.iterrows():
        premium = float(row.get("premium", 0.0))
        notable, prem_z, baseline_src = _is_notable(
            premium, root, baselines, etf_floor, name_floor, etf_set
        )
        if not notable:
            continue

        exp_str  = str(row.get("expiration", ""))
        strike   = float(row.get("strike", 0))
        right    = str(row.get("right", "C")).upper()[:1]
        seq_max  = row.get("seq_max", row.get("premium", premium))

        ev_id = _event_id(session_date, root, exp_str, strike, right, seq_max)

        # Dedup: same event id in same session = already emitted
        if ev_id in emitted_ids:
            continue

        contract_key = (exp_str, strike, right)
        n_cycles = notability_hist.get(contract_key, 0) + 1
        notability_hist[contract_key] = n_cycles
        repeated = n_cycles >= 2

        enrich = _enrich_contract_row(row, session_date, oi_prev,
                                       contract_vol=contract_vol,
                                       prev_close=prev_close)
        dte_val  = enrich["dte"]
        ts_val   = str(row.get("ts", batch_ts)) or batch_ts

        # Timestamp normalisation
        try:
            ts_parsed = pd.Timestamp(ts_val)
            if ts_parsed.tzinfo is None:
                ts_str = ts_parsed.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            else:
                ts_str = ts_parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:  # noqa: BLE001
            ts_str = batch_ts

        # Sweep-like heuristic flag (labeled — never described as "institutional")
        sweep_key = (exp_str, strike, right)
        is_swept = sweep_flags.get(sweep_key, False)

        event: dict = {
            "id":              ev_id,
            "ts":              ts_str,
            "root":            root,
            "group":           group_en,
            "group_zh":        group_zh,
            "right":           right,
            "exp":             exp_str,
            "strike":          round(strike, 3),
            "dte":             dte_val,
            "dte_bucket":      enrich["dte_bucket"],
            "mny_bucket":      enrich["mny_bucket"],
            "side":            str(row.get("side", "mixed")),
            "n_prints":        int(row.get("n_prints", 1)),
            "size":            int(row.get("size", 0)),
            "avg_price":       round(float(row.get("avg_price", 0.0)), 4),
            "premium":         round(premium, 0),
            "premium_z":       prem_z,
            "baseline_source": baseline_src,
            "vol_gt_oi":       enrich["vol_gt_oi"],
            "repeated":        repeated,
            "zerodte":         enrich["zerodte"],
            "signing_source":  "tape",
            # Additive: sweep-like heuristic label (>=3 prints, >=2 exchanges, <=2s span)
            "swept":           is_swept,
        }
        new_events.append(event)
        emitted_ids.add(ev_id)

    # ── 6. unusual_names ──────────────────────────────────────────────────────
    unusual = _unusual_row(root, root_gross_today.get(root, 0.0), baselines)
    unusual["top_contracts"] = _top_contracts(coalesced, max_n=3)

    # ── 6b. Persist per-root top_contracts (for ticker JSON) ─────────────────
    # Build from coalesced rows (all contracts this session have vol in contract_vol).
    _update_root_top_contracts(
        root=root,
        coalesced=coalesced,
        contract_vol=contract_vol,
        oi_prev=oi_prev,
        root_top_contracts=root_top_contracts,
        max_n=10,
    )

    return {
        "events": new_events,
        "unusual_names": [unusual],
        "heat": [heat_row],
        "state": {
            "emitted_ids": emitted_ids,
            "contract_vol": contract_vol,
            "notability_history": notability_hist,
            "root_gross_today": root_gross_today,
            "seen_sequences": seen_sequences,
            "market_tide_minutes": market_tide_minutes,
            "sector_tide": sector_tide,
            "dte_tide": dte_tide,
            "root_minutes": root_minutes,
            "root_strikes": root_strikes,
            "root_expiries": root_expiries,
            "root_top_contracts": root_top_contracts,
            "sweep_clusters": sweep_clusters,
        },
        "meta_notes": ["moneyness vs prior-session close (approx.)"],
    }


def _unusual_row(root: str, gross_today: float, baselines: dict | None) -> dict:
    """Build an unusual_name entry for `root`."""
    prem_z: float | None = None
    baseline_src = "none"
    n_obs = 0

    if baselines and root.upper() in baselines:
        b = baselines[root.upper()]
        mean_val = b.get("mean")
        std_val  = b.get("std")
        n_obs    = int(b.get("n_obs", 0))
        if mean_val is not None and std_val is not None and float(std_val) > 0:
            prem_z = round((gross_today - float(mean_val)) / float(std_val), 2)
            baseline_src = "eod252"

    return {
        "root":                root.upper(),
        "group":               "",       # filled by caller from group map
        "group_zh":            "",
        "gross_premium_today": round(gross_today, 0),
        "prem_z":              prem_z,
        "baseline_source":     baseline_src,
        "n_obs":               n_obs,
        "call_prem_share":     0.0,      # caller fills from heat data
        "top_contracts":       [],
    }


def _top_contracts(coalesced: pd.DataFrame, max_n: int = 3) -> list[dict]:
    """Return up to max_n contracts sorted by descending premium."""
    if coalesced.empty:
        return []
    top = coalesced.nlargest(max_n, "premium") if "premium" in coalesced.columns else coalesced.head(max_n)
    result = []
    for _, row in top.iterrows():
        result.append({
            "right":   str(row.get("right", "")).upper()[:1],
            "exp":     str(row.get("expiration", "")),
            "strike":  round(float(row.get("strike", 0)), 3),
            "premium": round(float(row.get("premium", 0)), 0),
        })
    return result


# ── 24h retention trim ────────────────────────────────────────────────────────

def trim_events(events: list[dict], cutoff_ts: str) -> list[dict]:
    """Remove events older than cutoff_ts (ISO8601Z).  Cap at MAX_EVENTS newest."""
    if not events:
        return []
    try:
        cutoff = pd.Timestamp(cutoff_ts).to_pydatetime()
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return events[:MAX_EVENTS]

    kept = []
    for ev in events:
        try:
            ts = pd.Timestamp(ev["ts"]).to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                kept.append(ev)
        except Exception:  # noqa: BLE001
            kept.append(ev)

    # Sort ts desc, cap
    kept.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return kept[:MAX_EVENTS]


# ── heat aggregator (cross-root) ─────────────────────────────────────────────

def aggregate_heat(heat_rows: list[dict]) -> list[dict]:
    """Merge per-root heat rows into per-group rows, sorting by gross_premium desc.

    Each input row has keys: group, group_zh, gross_premium, net_signed_premium_soft,
    call_prem_share, n_events, _root.
    Output rows omit _root; top=[{root, premium}x<=3] is filled from largest contributors.
    """
    if not heat_rows:
        return []

    from collections import defaultdict
    groups: dict[str, dict] = {}

    for row in heat_rows:
        gkey = str(row.get("group", _OTHER_GROUP))
        if gkey not in groups:
            groups[gkey] = {
                "group":       gkey,
                "group_zh":    str(row.get("group_zh", _OTHER_GROUP_ZH)),
                "gross_premium": 0.0,
                "net_signed_premium_soft": 0.0,
                "call_prem_share_num": 0.0,   # weighted numerator
                "n_events":    0,
                "contributors": [],
            }
        g = groups[gkey]
        gp = float(row.get("gross_premium", 0))
        g["gross_premium"] += gp
        g["net_signed_premium_soft"] += float(row.get("net_signed_premium_soft", 0))
        g["call_prem_share_num"] += float(row.get("call_prem_share", 0)) * gp
        g["n_events"] += int(row.get("n_events", 0))
        root = str(row.get("_root", "?"))
        g["contributors"].append((root, gp))

    result = []
    for g in groups.values():
        total_gp = g["gross_premium"]
        cps = (g["call_prem_share_num"] / total_gp) if total_gp > 0 else 0.0
        top = sorted(g["contributors"], key=lambda x: x[1], reverse=True)[:3]
        result.append({
            "group":              g["group"],
            "group_zh":           g["group_zh"],
            "gross_premium":      round(total_gp, 0),
            "net_signed_premium_soft": round(g["net_signed_premium_soft"], 0),
            "call_prem_share":    round(cps, 4),
            "n_events":           g["n_events"],
            "top":                [{"root": r, "premium": round(p, 0)} for r, p in top],
        })

    result.sort(key=lambda r: r["gross_premium"], reverse=True)
    return result


# ── Tide accumulation helpers ─────────────────────────────────────────────────

# DTE bucket order for dte_tide
_DTE_BUCKETS = ("0d", "1_7d", "8_30d", "31_90d", "90p")


def _minute_key(ts_val: Any, batch_ts: str) -> str:
    """Return America/New_York "HH:MM" string from a trade_timestamp value.

    Falls back to batch_ts on any parse failure.  All minute keys are in ET to
    align with the 9:30–16:00 RTH axis.
    """
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
    try:
        ts = pd.Timestamp(ts_val)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.astimezone(_ET).strftime("%H:%M")
    except Exception:  # noqa: BLE001
        pass
    try:
        ts = pd.Timestamp(batch_ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        return ts.astimezone(_ET).strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return "00:00"


def _accumulate_tide(
    combined: pd.DataFrame,
    root: str,
    group_en: str,
    group_zh: str,
    batch_ts: str,
    session_date: str,
    market_tide_minutes: dict,
    sector_tide: dict,
    dte_tide: dict,
    root_minutes: dict,
    root_strikes: dict,
    root_expiries: dict,
    sweep_clusters: dict,
) -> None:
    """Accumulate tide minute-buckets in-place from a signed combined DataFrame.

    Only NOVEL (sequence-deduped) rows should be passed here; called from
    process_batch after the dedup step.

    NCP / NPP convention:
      ncp = net call premium: calls sign>0 → +prem, calls sign<0 → -prem
      npp = net put premium:  puts  sign>0 → +prem, puts  sign<0 → -prem
    """
    if combined.empty:
        return

    # Minute key per row (vectorised)
    ts_col = combined["trade_timestamp"] if "trade_timestamp" in combined.columns \
        else pd.Series([batch_ts] * len(combined), index=combined.index)

    # Pre-compute per-row fields
    combined = combined.copy()
    combined["_prem"]        = combined["price"] * combined["size"] * 100.0
    combined["_signed_prem"] = combined["_prem"] * combined["sign"].fillna(0.0)
    combined["_right_norm"]  = combined["right"].astype(str).str.upper().str[:1]
    combined["_mkey"]        = ts_col.apply(lambda v: _minute_key(v, batch_ts))

    for mkey, grp in combined.groupby("_mkey"):
        mkey = str(mkey)
        g_prem        = float(grp["_prem"].sum())
        g_signed      = float(grp["_signed_prem"].sum())
        g_call_signed = float(grp.loc[grp["_right_norm"] == "C", "_signed_prem"].sum())
        g_put_signed  = float(grp.loc[grp["_right_norm"] == "P", "_signed_prem"].sum())
        g_vol         = int(grp["size"].sum())

        # Market tide
        m = market_tide_minutes.setdefault(mkey, {"ncp": 0.0, "npp": 0.0, "gross": 0.0, "vol": 0})
        m["ncp"]   += g_call_signed
        m["npp"]   += g_put_signed
        m["gross"] += g_prem
        m["vol"]   += g_vol

        # Sector tide
        sg = sector_tide.setdefault(group_en, {
            "group": group_en, "group_zh": group_zh, "ncp": 0.0, "npp": 0.0, "gross": 0.0,
            "minutes": {},
        })
        sg["group_zh"] = group_zh  # keep fresh
        sg["ncp"]   += g_call_signed
        sg["npp"]   += g_put_signed
        sg["gross"] += g_prem
        sm = sg["minutes"].setdefault(mkey, {"ncp": 0.0, "npp": 0.0})
        sm["ncp"] += g_call_signed
        sm["npp"] += g_put_signed

        # DTE tide — split by DTE bucket
        if "expiration" in grp.columns:
            try:
                sess_dt = pd.Timestamp(session_date)
                for dte_bkt, bkt_grp in grp.groupby(
                    grp["expiration"].apply(
                        lambda e: str(_dte_bucket(
                            pd.Series([max(int((pd.Timestamp(e) - sess_dt).days), 0)])
                        ).iloc[0])
                    )
                ):
                    bkt_str = str(dte_bkt)
                    db = dte_tide.setdefault(bkt_str, {})
                    dm = db.setdefault(mkey, {"ncp": 0.0, "npp": 0.0})
                    dm["ncp"] += float(bkt_grp.loc[bkt_grp["_right_norm"] == "C", "_signed_prem"].sum())
                    dm["npp"] += float(bkt_grp.loc[bkt_grp["_right_norm"] == "P", "_signed_prem"].sum())
            except Exception:  # noqa: BLE001
                pass

    # ── per-root minute series ────────────────────────────────────────────────
    rm = root_minutes.setdefault(root, {})
    for mkey, grp in combined.groupby("_mkey"):
        mkey = str(mkey)
        rcm = rm.setdefault(mkey, {"ncp": 0.0, "npp": 0.0, "vol": 0})
        rcm["ncp"] += float(grp.loc[grp["_right_norm"] == "C", "_signed_prem"].sum())
        rcm["npp"] += float(grp.loc[grp["_right_norm"] == "P", "_signed_prem"].sum())
        rcm["vol"] += int(grp["size"].sum())

    # ── per-root strike rollups ───────────────────────────────────────────────
    if "strike" in combined.columns:
        rs = root_strikes.setdefault(root, {})
        for stk, sgrp in combined.groupby(
            combined["strike"].apply(lambda s: str(round(float(s), 3)))
        ):
            sv = rs.setdefault(str(stk), {"call_prem": 0.0, "put_prem": 0.0, "vol": 0})
            sv["call_prem"] += float(sgrp.loc[sgrp["_right_norm"] == "C", "_prem"].sum())
            sv["put_prem"]  += float(sgrp.loc[sgrp["_right_norm"] == "P", "_prem"].sum())
            sv["vol"]       += int(sgrp["size"].sum())

    # ── per-root expiry rollups ───────────────────────────────────────────────
    if "expiration" in combined.columns:
        re = root_expiries.setdefault(root, {})
        for exp, egrp in combined.groupby(
            pd.to_datetime(combined["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
        ):
            exp = str(exp)
            if exp in ("NaT", "nat", ""):
                continue
            ev2 = re.setdefault(exp, {"call_prem": 0.0, "put_prem": 0.0, "vol": 0})
            ev2["call_prem"] += float(egrp.loc[egrp["_right_norm"] == "C", "_prem"].sum())
            ev2["put_prem"]  += float(egrp.loc[egrp["_right_norm"] == "P", "_prem"].sum())
            ev2["vol"]       += int(egrp["size"].sum())

    # ── sweep cluster update ──────────────────────────────────────────────────
    # Record raw prints (exchange, timestamp) per contract for sweep detection.
    if "expiration" in combined.columns and "exchange" in combined.columns:
        for _, row in combined.iterrows():
            exp_str   = str(pd.to_datetime(row.get("expiration", ""), errors="coerce").strftime("%Y-%m-%d"))
            strike_v  = float(row.get("strike", 0))
            right_v   = str(row.get("right", "C")).upper()[:1]
            exch      = str(row.get("exchange", ""))
            ts_v      = row.get("trade_timestamp", batch_ts)
            try:
                ts_epoch = pd.Timestamp(ts_v).timestamp()
            except Exception:  # noqa: BLE001
                ts_epoch = 0.0
            ckey = f"{exp_str}|{strike_v:.3f}|{right_v}"
            cluster = sweep_clusters.setdefault(ckey, [])
            cluster.append({"ts": ts_epoch, "exchange": exch})
            # Prune entries older than 60s to bound memory
            if len(cluster) > 500:
                cluster[:] = cluster[-500:]


def _detect_sweeps(combined: pd.DataFrame, sweep_clusters: dict) -> dict:
    """Return {contract_key: True} for contracts qualifying as sweep-like.

    A contract is sweep-like in this batch if, across all recorded prints
    (current batch + sweep_clusters state):
      - >= 3 prints
      - >= 2 distinct exchanges
      - all prints within a 2-second window

    Returns a mapping from (exp, strike, right) tuples (as str keys matching
    the format used in process_batch) to True.

    This is a LABELED HEURISTIC — not a directional indicator or edge claim.
    """
    if combined.empty or "exchange" not in combined.columns:
        return {}

    flags: dict = {}

    # Group by contract
    contract_cols = [c for c in ("expiration", "strike", "right") if c in combined.columns]
    if not contract_cols:
        return {}

    for keys, grp in combined.groupby(contract_cols):
        if isinstance(keys, (str, float)):
            keys = (keys,)
        exp_raw   = str(keys[0]) if len(keys) > 0 else ""
        strike_v  = float(keys[1]) if len(keys) > 1 else 0.0
        right_v   = str(keys[2]).upper()[:1] if len(keys) > 2 else "C"
        try:
            exp_str = pd.to_datetime(exp_raw, errors="coerce").strftime("%Y-%m-%d")
        except Exception:  # noqa: BLE001
            exp_str = exp_raw

        n_prints = len(grp)
        if n_prints < 3:
            continue

        exchanges = set(grp["exchange"].astype(str).tolist())
        if len(exchanges) < 2:
            continue

        # Check timestamp span <= 2s
        if "trade_timestamp" in grp.columns:
            try:
                ts_vals = pd.to_datetime(grp["trade_timestamp"], errors="coerce").dropna()
                if len(ts_vals) >= 3:
                    span = (ts_vals.max() - ts_vals.min()).total_seconds()
                    if span <= 2.0:
                        ckey = (exp_str, strike_v, right_v)
                        flags[ckey] = True
            except Exception:  # noqa: BLE001
                pass

    return flags


def _update_root_top_contracts(
    root: str,
    coalesced: pd.DataFrame,
    contract_vol: dict,
    oi_prev: "pd.DataFrame | None",
    root_top_contracts: dict,
    max_n: int = 10,
) -> None:
    """Rebuild top-contracts list for `root` from all coalesced data this session.

    Uses contract_vol (cumulative day vol) for the vol field.
    vol_gt_oi checked against oi_prev (t-1); None if OI unavailable.
    Stored in root_top_contracts[root] as a list sorted by premium desc.
    """
    if coalesced.empty:
        return

    existing = {
        (r["exp"], float(r["strike"]), r["right"]): r
        for r in root_top_contracts.get(root, [])
    }

    for _, row in coalesced.iterrows():
        exp_str  = str(row.get("expiration", ""))
        strike   = float(row.get("strike", 0))
        right    = str(row.get("right", "C")).upper()[:1]
        premium  = float(row.get("premium", 0.0))
        ckey     = (exp_str, strike, right)
        cum_vol  = float(contract_vol.get(ckey, row.get("size", 0)))

        # vol_gt_oi
        vgt: bool | None = None
        if oi_prev is not None and not oi_prev.empty:
            try:
                oi_match = oi_prev[
                    (pd.to_datetime(oi_prev.get("expiration", pd.Series(dtype=str)),
                                    errors="coerce").dt.strftime("%Y-%m-%d") == exp_str) &
                    (oi_prev.get("right", pd.Series(dtype=str)).astype(str).str.upper().str[:1] == right) &
                    (pd.to_numeric(oi_prev.get("strike", pd.Series(dtype=float)),
                                   errors="coerce") == strike)
                ]
                if not oi_match.empty and "open_interest" in oi_match.columns:
                    vgt = bool(cum_vol > float(oi_match["open_interest"].iloc[0]))
            except Exception:  # noqa: BLE001
                pass

        existing[ckey] = {
            "right":      right,
            "exp":        exp_str,
            "strike":     round(strike, 3),
            "premium":    round(premium, 0),
            "vol":        int(cum_vol),
            "vol_gt_oi":  vgt,
        }

    sorted_contracts = sorted(existing.values(), key=lambda c: c["premium"], reverse=True)
    root_top_contracts[root] = sorted_contracts[:max_n]


# ── Tide JSON builders ────────────────────────────────────────────────────────

def build_tide_current(
    session_date: str,
    asof: str,
    day_state: dict,
    spy_minute_prices: list[dict] | None = None,
) -> dict:
    """Build the tide_current.json payload from day_state.

    Output schema: live_flow.tide/v1
    {
      "schema": "live_flow.tide/v1",
      "asof": str,
      "session_date": str,
      "method": "ncp/npp=cumulative signed tape premium (Lee-Ready ~-soft)",
      "minutes": [{"t","ncp","npp","gross","vol"} sorted by t],
      "spy": [{"t","px"}] or [],
      "sectors": [{"group","group_zh","ncp","npp","gross","minutes":[{"t","ncp","npp"}]}],
      "top_net_impact": [{"root","net_prem_soft","gross"} x<=20],
    }
    """
    market_minutes = day_state.get("market_tide_minutes", {})
    sector_tide    = day_state.get("sector_tide", {})
    root_gross     = day_state.get("root_gross_today", {})
    root_minutes   = day_state.get("root_minutes", {})

    # Minutes series: cumulative NCP/NPP — convert per-minute deltas to cumulative
    sorted_keys = sorted(market_minutes.keys())
    cum_ncp = 0.0
    cum_npp = 0.0
    minutes_out: list[dict] = []
    for t in sorted_keys:
        m = market_minutes[t]
        cum_ncp += float(m.get("ncp", 0.0))
        cum_npp += float(m.get("npp", 0.0))
        minutes_out.append({
            "t":     t,
            "ncp":   round(cum_ncp, 0),
            "npp":   round(cum_npp, 0),
            "gross": round(float(m.get("gross", 0.0)), 0),
            "vol":   int(m.get("vol", 0)),
        })

    # Sectors
    sectors_out: list[dict] = []
    for grp, sd in sector_tide.items():
        sm = sd.get("minutes", {})
        sorted_sm = sorted(sm.keys())
        sec_cum_ncp = 0.0
        sec_cum_npp = 0.0
        sec_minutes: list[dict] = []
        for t in sorted_sm:
            dm = sm[t]
            sec_cum_ncp += float(dm.get("ncp", 0.0))
            sec_cum_npp += float(dm.get("npp", 0.0))
            sec_minutes.append({"t": t, "ncp": round(sec_cum_ncp, 0), "npp": round(sec_cum_npp, 0)})
        sectors_out.append({
            "group":    sd.get("group", grp),
            "group_zh": sd.get("group_zh", grp),
            "ncp":      round(float(sd.get("ncp", 0.0)), 0),
            "npp":      round(float(sd.get("npp", 0.0)), 0),
            "gross":    round(float(sd.get("gross", 0.0)), 0),
            "minutes":  sec_minutes,
        })
    sectors_out.sort(key=lambda s: abs(s["ncp"]) + abs(s["npp"]), reverse=True)

    # Top net impact: top 20 roots by |net_prem_soft| from root_minutes cumulative
    top_net: list[dict] = []
    for r, rmin in root_minutes.items():
        net_c = sum(v.get("ncp", 0.0) for v in rmin.values())
        net_p = sum(v.get("npp", 0.0) for v in rmin.values())
        net   = net_c + net_p
        gross = root_gross.get(r, 0.0)
        top_net.append({"root": r, "net_prem_soft": round(net, 0), "gross": round(gross, 0)})
    top_net.sort(key=lambda x: abs(x["net_prem_soft"]), reverse=True)
    top_net = top_net[:20]

    return {
        "schema":       "live_flow.tide/v1",
        "asof":         asof,
        "session_date": session_date,
        "method":       "ncp/npp=cumulative signed tape premium (Lee-Ready ~-soft)",
        "minutes":      minutes_out,
        "spy":          spy_minute_prices or [],
        "sectors":      sectors_out,
        "top_net_impact": top_net,
    }


def build_dte_tide_current(session_date: str, asof: str, day_state: dict) -> dict:
    """Build dte_tide_current.json payload from day_state.

    Output schema: live_flow.dte_tide/v1
    {
      "schema": "live_flow.dte_tide/v1",
      "asof": str,
      "buckets": {
        "0d":    [{"t","ncp","npp"} cumulative sorted by t],
        "1_7d":  [...],
        "8_30d": [...],
        "31_90d":[...],
        "90p":   [...],
      }
    }
    """
    dte_tide = day_state.get("dte_tide", {})
    buckets_out: dict = {}
    for bkt in _DTE_BUCKETS:
        bkt_minutes = dte_tide.get(bkt, {})
        sorted_keys = sorted(bkt_minutes.keys())
        cum_ncp = 0.0
        cum_npp = 0.0
        series: list[dict] = []
        for t in sorted_keys:
            dm = bkt_minutes[t]
            cum_ncp += float(dm.get("ncp", 0.0))
            cum_npp += float(dm.get("npp", 0.0))
            series.append({"t": t, "ncp": round(cum_ncp, 0), "npp": round(cum_npp, 0)})
        buckets_out[bkt] = series
    return {
        "schema":  "live_flow.dte_tide/v1",
        "asof":    asof,
        "buckets": buckets_out,
    }


def build_ticker_json(
    root: str,
    session_date: str,
    asof: str,
    day_state: dict,
    root_gross_today: dict | None = None,
    baselines: dict | None = None,
    names_sectors: dict | None = None,
    oi_prev: "pd.DataFrame | None" = None,
) -> dict:
    """Build tickers/{ROOT}.json payload from day_state.

    Output schema: live_flow.ticker/v1
    """
    root = root.upper()
    rmin  = day_state.get("root_minutes", {}).get(root, {})
    rstk  = day_state.get("root_strikes", {}).get(root, {})
    rexp  = day_state.get("root_expiries", {}).get(root, {})
    rtop  = day_state.get("root_top_contracts", {}).get(root, [])
    rg    = (root_gross_today or day_state.get("root_gross_today", {})).get(root, 0.0)

    # Per-root group labels
    ns_map = names_sectors or {}
    grp_en, grp_zh = _root_to_group(root, ns_map)

    # Day stats
    net_soft = sum(v.get("ncp", 0.0) + v.get("npp", 0.0) for v in rmin.values())
    total_vol = sum(v.get("vol", 0) for v in rmin.values())
    # call_share from strikes
    total_call = sum(s.get("call_prem", 0.0) for s in rstk.values())
    total_prem_stk = total_call + sum(s.get("put_prem", 0.0) for s in rstk.values())
    call_share = (total_call / total_prem_stk) if total_prem_stk > 0 else 0.0

    # prem_z from baselines
    prem_z = None
    baseline_source = "none"
    if baselines and root in baselines:
        b = baselines[root]
        m, s = b.get("mean"), b.get("std")
        if m is not None and s and float(s) > 0:
            prem_z = round((rg - float(m)) / float(s), 2)
            baseline_source = "eod252"

    # Cumulative minute series
    sorted_keys = sorted(rmin.keys())
    cum_ncp = 0.0
    cum_npp = 0.0
    minutes_out: list[dict] = []
    for t in sorted_keys:
        m = rmin[t]
        cum_ncp += float(m.get("ncp", 0.0))
        cum_npp += float(m.get("npp", 0.0))
        minutes_out.append({
            "t": t, "ncp": round(cum_ncp, 0), "npp": round(cum_npp, 0),
            "vol": int(m.get("vol", 0)),
        })

    # Strike ladder
    strikes_out: list[dict] = []
    for stk_str, sv in sorted(rstk.items(), key=lambda kv: float(kv[0])):
        strikes_out.append({
            "strike":     round(float(stk_str), 3),
            "call_prem":  round(sv.get("call_prem", 0.0), 0),
            "put_prem":   round(sv.get("put_prem", 0.0), 0),
            "vol":        int(sv.get("vol", 0)),
        })

    # Expiry bars
    expiries_out: list[dict] = []
    for exp, ev in sorted(rexp.items()):
        expiries_out.append({
            "exp":       exp,
            "call_prem": round(ev.get("call_prem", 0.0), 0),
            "put_prem":  round(ev.get("put_prem", 0.0), 0),
            "vol":       int(ev.get("vol", 0)),
        })

    return {
        "schema":       "live_flow.ticker/v1",
        "asof":         asof,
        "root":         root,
        "group":        grp_en,
        "group_zh":     grp_zh,
        "day": {
            "gross":           round(rg, 0),
            "net_soft":        round(net_soft, 0),
            "call_share":      round(call_share, 4),
            "n_events":        len(rtop),
            "prem_z":          prem_z,
            "baseline_source": baseline_source,
        },
        "minutes":       minutes_out,
        "strikes":       strikes_out,
        "expiries":      expiries_out,
        "top_contracts": rtop,
    }


def build_top_net_impact(day_state: dict, max_n: int = 20) -> list[dict]:
    """Return top max_n roots by |net_prem_soft| from root_minutes + root_gross_today."""
    root_minutes = day_state.get("root_minutes", {})
    root_gross   = day_state.get("root_gross_today", {})
    rows: list[dict] = []
    for r, rmin in root_minutes.items():
        net = sum(v.get("ncp", 0.0) + v.get("npp", 0.0) for v in rmin.values())
        gross = root_gross.get(r, 0.0)
        rows.append({"root": r, "net_prem_soft": round(net, 0), "gross": round(gross, 0)})
    rows.sort(key=lambda x: abs(x["net_prem_soft"]), reverse=True)
    return rows[:max_n]
