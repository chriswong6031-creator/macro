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
                         oi_prev: pd.DataFrame | None) -> dict:
    """Compute dte, dte_bucket, mny_bucket, vol_gt_oi, zerodte from a coalesced row."""
    exp_str = str(row.get("expiration", ""))
    try:
        exp_dt = pd.Timestamp(exp_str)
        sess_dt = pd.Timestamp(session_date)
        dte_val = max(int((exp_dt - sess_dt).days), 0)
    except Exception:  # noqa: BLE001
        dte_val = 0

    dte_bucket_val = str(_dte_bucket(pd.Series([dte_val])).iloc[0])
    zerodte = dte_bucket_val == "0d"

    # Moneyness — unknown without underlying_price
    mny_bucket_val = "atm"  # default

    # vol_gt_oi
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
                contract_vol = float(row.get("size", 0))
                vol_gt_oi_val = bool(contract_vol > oi_val)
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
    oi_prev            : t-1 OI frame (columns: expiration, strike, right, open_interest).
    baselines          : {ROOT: {mean, std, n_obs, computed_asof}} from build_live_flow_baselines.
    etf_floor          : minimum premium for ETF anchors.
    name_floor         : minimum premium for single names.
    etf_anchors        : set of ETF root symbols.
    names_sectors      : {ticker: (name, GICS_sector)} — for group labeling.

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
            },
            "meta_notes": ["batch empty — no prints"],
        }

    combined = pd.concat(frames, ignore_index=True)
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

        enrich = _enrich_contract_row(row, session_date, oi_prev)
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
        }
        new_events.append(event)
        emitted_ids.add(ev_id)

    # ── 6. unusual_names ──────────────────────────────────────────────────────
    unusual = _unusual_row(root, root_gross_today.get(root, 0.0), baselines)
    unusual["top_contracts"] = _top_contracts(coalesced, max_n=3)

    return {
        "events": new_events,
        "unusual_names": [unusual],
        "heat": [heat_row],
        "state": {
            "emitted_ids": emitted_ids,
            "contract_vol": contract_vol,
            "notability_history": notability_hist,
            "root_gross_today": root_gross_today,
        },
        "meta_notes": [],
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
