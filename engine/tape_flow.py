"""engine/tape_flow.py — per-name daily signed options-flow features from trade+NBBO.

T2a implementation: aggregate-then-discard from ThetaData trade_quote endpoint.
Raw trade rows are NEVER persisted; only derived features are written to disk.
Raw-tape retention today is a byte-count manifest only (written by
scripts/build_tape_flow_daily — no raw bytes are kept anywhere, R2 included);
the raw-plane implementation is tracked as WP-TAPE-TRUTH in
research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md.

## Signing provenance law (LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE §8.2)
Every feature carries signing_source="tape" (Lee-Ready quote rule on NBBO).
Mixed-source aggregates are FORBIDDEN — this module only produces tape-signed features.
Calibration status: agreement=0.8848 (bar 0.75), net-sign recovery=0.80 (bar 0.75)
— both bars met (THETADATA_PROBE.md §4.3 / §4.6 Fable adjudication 2026-07-04).

## Bulk endpoint discovery (THETADATA_PROBE.md §1.4 + live probe 2026-07-04)
trade_quote accepts wildcard expiration AND strike when right is specified as
"call" or "put". Wildcard right= returns HTTP 400 "Invalid right: *".
Implementation: two requests per root-day (call + put), streamed and aggregated
on the fly, raw rows discarded after aggregation.

## Feature schema
One row per (root, date):
  Core signed premium:
    ask_side_call_premium, bid_side_call_premium  ($ gross, by side)
    ask_side_put_premium,  bid_side_put_premium
    net_signed_premium     (ask_side_* - bid_side_* across all, in dollars)
    signed_contract_volume (ask-side contracts minus bid-side contracts)

  Delta-notional flow (nullable pre-greeks-coverage, typically pre-2017):
    signed_delta_notional  (sum of sign × size × delta × underlying_price)

  DTE buckets (net_signed_premium + volume_share):
    dte_0d_{net_premium,vol_share}
    dte_1_7d_{net_premium,vol_share}
    dte_8_30d_{net_premium,vol_share}
    dte_31_90d_{net_premium,vol_share}
    dte_90p_{net_premium,vol_share}

  Moneyness buckets:
    money_itm_{net_premium,vol_share}          (abs_moneyness < 0, i.e. ITM)
    money_atm_{net_premium,vol_share}          (abs_moneyness ≤ 5%)
    money_near_otm_{net_premium,vol_share}     (5% < abs_moneyness ≤ 15%)
    money_far_otm_{net_premium,vol_share}      (abs_moneyness > 15%)

  vol_gt_oi flag:
    vol_gt_oi_share   (fraction of contract-expiry pairs where volume > oi[t-1])

  Counts and gross:
    n_trades, n_contracts, gross_premium

  Z-scores (trailing 252 sessions, min 60; null until history accrues):
    <col>_z252 for every numeric feature above

  Metadata:
    root, date, signing_source="tape", generated_utc

## OI timing law
oi[t-1] is used for vol_gt_oi: OI published at ~06:30 ET represents EOD t-1
positions (LIVE_ORDER_FLOW_BRAINSTORM_BY_FABLE §8 ¶1). Same-day OI comparison
is a lookahead bug and is rejected here.

## Delta-null pre-greeks
chain() from thetadata_store may return no greeks columns (NaN delta) for dates
before the greeks backfill coverage. In that case signed_delta_notional is null.
Premium features are always computed regardless.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from engine import flow_signing

log = logging.getLogger(__name__)

# Signing source stamped on every output row (mixed-source aggregates forbidden §8.2)
SIGNING_SOURCE = "tape"

# Z-score look-back window (sessions) and minimum history
ZSCORE_WINDOW = 252
ZSCORE_MIN_PERIODS = 60

# Moneyness bucket boundaries (|moneyness| = |price/underlying - 1|)
MONEY_ATM_BAND = 0.05    # ≤ 5% = ATM
MONEY_NEAR_OTM = 0.15    # 5%–15% = near-OTM


# ─── signing helpers ──────────────────────────────────────────────────────────

def _sign_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Apply Lee-Ready quote rule (flow_signing.quote_rule_sign) per contract.

    Input columns required: price, bid, ask, size, trade_timestamp,
                            strike, expiration, right, root
    Output: df with added 'sign' column (+1 buy / -1 sell / 0 mid-uncertain).
    The quote rule only needs price, bid, ask — no prev_price needed at the
    per-trade level (we use the tick-fallback when exactly at mid).
    """
    if df.empty:
        df = df.copy()
        df["sign"] = pd.Series(dtype=float)
        return df

    df = df.copy()

    # Build prev_price within each contract (needed for mid-price tick fallback)
    # Contract key: (expiration, strike, right)
    contract_key = ["expiration", "strike", "right"]
    available_keys = [c for c in contract_key if c in df.columns]
    if available_keys and "trade_timestamp" in df.columns:
        df = df.sort_values(available_keys + ["trade_timestamp"])
        df["_prev_price"] = df.groupby(available_keys)["price"].shift(1)
    else:
        df = df.sort_values("trade_timestamp") if "trade_timestamp" in df.columns else df
        df["_prev_price"] = df["price"].shift(1)

    signs = flow_signing.quote_rule_sign(
        df["price"].to_numpy(),
        df["bid"].to_numpy(),
        df["ask"].to_numpy(),
        df["_prev_price"].to_numpy() if "_prev_price" in df.columns else None,
    )
    df["sign"] = signs
    df = df.drop(columns=["_prev_price"], errors="ignore")
    return df


# ─── DTE / moneyness categorizers ────────────────────────────────────────────

def _dte_bucket(dte: pd.Series) -> pd.Series:
    """Assign DTE bucket label per row."""
    buckets = pd.cut(
        dte,
        bins=[-1, 0, 7, 30, 90, np.inf],
        labels=["0d", "1_7d", "8_30d", "31_90d", "90p"],
        right=True,
    )
    return buckets


def _moneyness_bucket(signed_money: pd.Series) -> pd.Series:
    """Assign moneyness bucket label.

    signed_money is signed moneyness: for calls positive = OTM, negative = ITM;
    for puts the sign convention is flipped (see _compute_signed_moneyness).
    A positive signed_money value means the option is OTM (strike is beyond ATM),
    a negative value means ITM.

    Buckets:
      ITM:       signed_money < -MONEY_ATM_BAND  (in-the-money, > 5% past ATM)
      ATM:       |signed_money| <= MONEY_ATM_BAND (within 5% of ATM)
      near_OTM:  MONEY_ATM_BAND < signed_money <= MONEY_NEAR_OTM (5-15% OTM)
      far_OTM:   signed_money > MONEY_NEAR_OTM (> 15% OTM)
    """
    conds = [
        signed_money < -MONEY_ATM_BAND,
        signed_money.abs() <= MONEY_ATM_BAND,
        (signed_money > MONEY_ATM_BAND) & (signed_money <= MONEY_NEAR_OTM),
        signed_money > MONEY_NEAR_OTM,
    ]
    choices = ["itm", "atm", "near_otm", "far_otm"]
    result = np.select(conds, choices, default="atm")
    return pd.Series(result, index=signed_money.index)


def _compute_signed_moneyness(df: pd.DataFrame) -> pd.Series:
    """Compute signed moneyness relative to ATM.

    For CALLS:  signed_money = strike/underlying - 1
                (positive = OTM = strike above spot, negative = ITM)
    For PUTS:   signed_money = underlying/strike - 1
                (positive = OTM = strike below spot, negative = ITM)
    Returns NaN when underlying_price or strike is unavailable.
    """
    if "underlying_price" not in df.columns or "strike" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    ulp = pd.to_numeric(df["underlying_price"], errors="coerce")
    stk = pd.to_numeric(df["strike"], errors="coerce")
    mask = (ulp > 0) & stk.notna() & (stk > 0)
    result = pd.Series(np.nan, index=df.index)

    right_col = df.get("right", pd.Series("C", index=df.index))
    is_put = right_col.astype(str).str.upper().str[:1] == "P"

    # Calls: positive when OTM (strike > underlying)
    call_mask = mask & ~is_put
    result.loc[call_mask] = stk.loc[call_mask] / ulp.loc[call_mask] - 1.0

    # Puts: positive when OTM (underlying > strike)
    put_mask = mask & is_put
    result.loc[put_mask] = ulp.loc[put_mask] / stk.loc[put_mask] - 1.0

    return result


# ─── core aggregation ────────────────────────────────────────────────────────

def aggregate_day(
    calls: pd.DataFrame,
    puts: pd.DataFrame,
    trade_date: date | str,
    root: str,
    oi_prev: pd.DataFrame | None = None,
    greeks_chain: pd.DataFrame | None = None,
) -> dict:
    """Aggregate one root-day trade+NBBO into signed-flow features.

    Parameters
    ----------
    calls : raw trade_quote DataFrame for calls (from collector), may be empty.
    puts  : raw trade_quote DataFrame for puts (from collector), may be empty.
    trade_date : the trading date for this batch.
    root  : option root symbol (e.g. "KRE").
    oi_prev : EOD OI DataFrame for date t-1 (oi[t-1] law); columns include
              (expiration, strike, right, open_interest). None → vol_gt_oi_share null.
    greeks_chain : EOD greeks chain for trade_date; columns include
                   (expiration, strike, right, delta, underlying_price). None → delta null.

    Returns
    -------
    dict with all feature columns (values are Python scalars or None).
    All raw input rows are DISCARDED after aggregation (T2a law).
    """
    trade_date_str = str(trade_date)[:10]
    trade_date_obj = pd.Timestamp(trade_date_str).date()

    result: dict = {
        "root": root.upper(),
        "date": trade_date_str,
        "signing_source": SIGNING_SOURCE,
    }

    # ── 1. Combine calls and puts, require minimum columns ────────────────────
    frames = []
    for side_df, right_label in ((calls, "C"), (puts, "P")):
        if side_df is None or side_df.empty:
            continue
        df = side_df.copy()
        # Ensure right column is normalized to "C"/"P"
        if "right" in df.columns:
            df["right"] = df["right"].astype(str).str.upper().str[:1]
        else:
            df["right"] = right_label
        frames.append(df)

    if not frames:
        # No data at all — return null-filled row
        _fill_nulls(result)
        return result

    trades = pd.concat(frames, ignore_index=True)

    # Coerce numeric columns
    for col in ("price", "bid", "ask", "size"):
        if col in trades.columns:
            trades[col] = pd.to_numeric(trades[col], errors="coerce")

    # Sanity filter: require valid NBBO (bid > 0, ask >= bid)
    trades = trades[(trades["bid"] > 0) & (trades["ask"] >= trades["bid"])].copy()

    if trades.empty:
        _fill_nulls(result)
        return result

    # ── 2. Apply quote-rule signing ───────────────────────────────────────────
    trades = _sign_trades(trades)
    # sign ∈ {-1, 0, +1}; sign > 0 = ask-side (buyer-initiated); sign < 0 = bid-side

    # ── 3. Parse trade timestamp for DTE computation ──────────────────────────
    if "trade_timestamp" in trades.columns:
        trades["_ts"] = pd.to_datetime(trades["trade_timestamp"], errors="coerce")
    else:
        trades["_ts"] = pd.NaT

    # Parse expiration
    if "expiration" in trades.columns:
        exp_dt = pd.to_datetime(trades["expiration"], errors="coerce")
        trades["_dte"] = (exp_dt - pd.Timestamp(trade_date_obj)).dt.days.clip(lower=0)
    else:
        trades["_dte"] = np.nan

    # ── 4. Compute moneyness ──────────────────────────────────────────────────
    # Try to get underlying_price from greeks_chain via join
    if greeks_chain is not None and not greeks_chain.empty and "underlying_price" in greeks_chain.columns:
        # Merge underlying_price onto trades by (expiration, strike, right)
        merge_cols = [c for c in ("expiration", "strike", "right") if c in trades.columns and c in greeks_chain.columns]
        if merge_cols:
            ulp_df = greeks_chain[merge_cols + ["underlying_price"]].drop_duplicates(subset=merge_cols)
            # Normalize expiration in greeks for merge
            if "expiration" in ulp_df.columns:
                ulp_df["expiration"] = pd.to_datetime(ulp_df["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
            if "expiration" in trades.columns:
                trades["_exp_str"] = pd.to_datetime(trades["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
                merge_cols_adj = [c if c != "expiration" else "_exp_str" for c in merge_cols]
                ulp_df = ulp_df.rename(columns={"expiration": "_exp_str"})
                trades = trades.merge(ulp_df[merge_cols_adj + ["underlying_price"]], on=merge_cols_adj, how="left")
            else:
                trades = trades.merge(ulp_df, on=merge_cols, how="left")
    elif "underlying_price" not in trades.columns:
        trades["underlying_price"] = np.nan

    trades["_signed_money"] = _compute_signed_moneyness(trades)
    trades["_money_bucket"] = _moneyness_bucket(trades["_signed_money"])
    trades["_dte_bucket"] = _dte_bucket(trades["_dte"])

    # ── 5. Compute premium per trade ──────────────────────────────────────────
    # Premium = price × size × 100 (standard option multiplier)
    trades["_premium"] = trades["price"] * trades["size"] * 100.0
    trades["_is_call"] = trades["right"].str.upper().str[:1] == "C"
    trades["_is_ask_side"] = trades["sign"] > 0
    trades["_is_bid_side"] = trades["sign"] < 0

    # ── 6. Core signed premium aggregates ────────────────────────────────────
    ask_call = trades[trades["_is_call"] & trades["_is_ask_side"]]["_premium"].sum()
    bid_call = trades[trades["_is_call"] & trades["_is_bid_side"]]["_premium"].sum()
    ask_put  = trades[~trades["_is_call"] & trades["_is_ask_side"]]["_premium"].sum()
    bid_put  = trades[~trades["_is_call"] & trades["_is_bid_side"]]["_premium"].sum()

    result["ask_side_call_premium"] = float(ask_call)
    result["bid_side_call_premium"] = float(bid_call)
    result["ask_side_put_premium"]  = float(ask_put)
    result["bid_side_put_premium"]  = float(bid_put)
    result["net_signed_premium"]    = float((ask_call - bid_call) + (ask_put - bid_put))
    result["signed_contract_volume"] = float(
        trades[trades["_is_ask_side"]]["size"].sum() -
        trades[trades["_is_bid_side"]]["size"].sum()
    )

    # ── 7. Gross stats ────────────────────────────────────────────────────────
    result["n_trades"]       = int(len(trades))
    result["n_contracts"]    = int(
        trades[["expiration", "strike", "right"]].drop_duplicates().shape[0]
        if all(c in trades.columns for c in ("expiration", "strike", "right"))
        else 0
    )
    result["gross_premium"]  = float(trades["_premium"].sum())

    # ── 8. Delta-notional signed flow ─────────────────────────────────────────
    if greeks_chain is not None and not greeks_chain.empty and "delta" in greeks_chain.columns:
        # Join per-contract delta onto trades
        merge_cols = [c for c in ("expiration", "strike", "right") if c in trades.columns and c in greeks_chain.columns]
        if merge_cols:
            delta_df = greeks_chain[merge_cols + ["delta", "underlying_price"]].drop_duplicates(subset=merge_cols)
            if "expiration" in delta_df.columns:
                delta_df["expiration"] = pd.to_datetime(delta_df["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
            if "_exp_str" in trades.columns:
                merge_cols_adj = [c if c != "expiration" else "_exp_str" for c in merge_cols]
                delta_df = delta_df.rename(columns={"expiration": "_exp_str"})
                trades_d = trades.merge(delta_df[merge_cols_adj + ["delta"]], on=merge_cols_adj, how="left")
            else:
                if "expiration" in trades.columns:
                    trades["_exp_str"] = pd.to_datetime(trades["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
                    merge_cols_adj = [c if c != "expiration" else "_exp_str" for c in merge_cols]
                    delta_df = delta_df.rename(columns={"expiration": "_exp_str"})
                    trades_d = trades.merge(delta_df[merge_cols_adj + ["delta"]], on=merge_cols_adj, how="left")
                else:
                    trades_d = trades.merge(delta_df, on=merge_cols, how="left")

            has_delta = trades_d["delta"].notna().any() if "delta" in trades_d else False
            if has_delta:
                d = trades_d["delta"].to_numpy(float)
                sz = trades_d["size"].to_numpy(float)
                sgn = trades_d["sign"].to_numpy(float)
                # underlying_price from greeks merge (already joined above if available)
                if "underlying_price" in trades_d.columns:
                    ulp = trades_d["underlying_price"].to_numpy(float)
                else:
                    ulp = np.ones(len(trades_d))
                ulp = np.where(np.isnan(ulp) | (ulp <= 0), 1.0, ulp)
                delta_notional = float(np.nansum(sgn * sz * 100.0 * d * ulp))
                result["signed_delta_notional"] = delta_notional
            else:
                result["signed_delta_notional"] = None
        else:
            result["signed_delta_notional"] = None
    else:
        result["signed_delta_notional"] = None

    # ── 9. DTE bucket features ────────────────────────────────────────────────
    total_vol = trades["size"].sum()
    for bucket_label, col_prefix in [
        ("0d",     "dte_0d"),
        ("1_7d",   "dte_1_7d"),
        ("8_30d",  "dte_8_30d"),
        ("31_90d", "dte_31_90d"),
        ("90p",    "dte_90p"),
    ]:
        mask = trades["_dte_bucket"] == bucket_label
        sub = trades[mask]
        ask_sub = sub[sub["_is_ask_side"]]["_premium"].sum()
        bid_sub = sub[sub["_is_bid_side"]]["_premium"].sum()
        result[f"{col_prefix}_net_premium"]  = float(ask_sub - bid_sub)
        result[f"{col_prefix}_vol_share"]    = float(
            sub["size"].sum() / total_vol if total_vol > 0 else 0.0
        )

    # ── 10. Moneyness bucket features ─────────────────────────────────────────
    for bucket_label, col_prefix in [
        ("itm",      "money_itm"),
        ("atm",      "money_atm"),
        ("near_otm", "money_near_otm"),
        ("far_otm",  "money_far_otm"),
    ]:
        mask = trades["_money_bucket"] == bucket_label
        sub = trades[mask]
        ask_sub = sub[sub["_is_ask_side"]]["_premium"].sum()
        bid_sub = sub[sub["_is_bid_side"]]["_premium"].sum()
        result[f"{col_prefix}_net_premium"] = float(ask_sub - bid_sub)
        result[f"{col_prefix}_vol_share"]   = float(
            sub["size"].sum() / total_vol if total_vol > 0 else 0.0
        )

    # ── 11. vol_gt_oi_share ───────────────────────────────────────────────────
    # For each contract on this day, compare volume to oi[t-1].
    # OI timing law: oi_prev must be the OI published before this trading day
    # (= EOD t-2, published morning of t-1), i.e. oi[t-1].
    result["vol_gt_oi_share"] = _vol_gt_oi(trades, oi_prev)

    # ── 12. T2a required features (P2.1 spec) ────────────────────────────────
    # volume: total contracts traded
    result["volume"] = float(trades["size"].sum())

    # signed_pc_ratio: signed put $ / signed call $ (gate-gated; negative = call-leaning)
    # Computed from the already-computed ask/bid premium sides above.
    _net_call_sp = result["ask_side_call_premium"] - result["bid_side_call_premium"]
    _net_put_sp  = result["ask_side_put_premium"]  - result["bid_side_put_premium"]
    result["signed_pc_ratio"] = (
        round(_net_put_sp / _net_call_sp, 4) if _net_call_sp != 0.0 else None
    )

    # zerodte_share: volume fraction for DTE=0
    result["zerodte_share"] = result.get("dte_0d_vol_share")

    # dte_quality_share: 8–90d volume fraction (institutional positioning window)
    # = sum of dte_8_30d_vol_share + dte_31_90d_vol_share
    _dte_8_30  = result.get("dte_8_30d_vol_share") or 0.0
    _dte_31_90 = result.get("dte_31_90d_vol_share") or 0.0
    result["dte_quality_share"] = round(float(_dte_8_30 + _dte_31_90), 4)

    # short_dated_otm_call_share: OTM calls (DTE 1–30d) volume fraction
    # Uses existing dte_1_7d and dte_8_30d buckets filtered to near/far OTM calls.
    _otm_call_mask = (
        (trades["right"].str.upper().str[:1] == "C") &
        (trades["_money_bucket"].isin(["near_otm", "far_otm"])) &
        (trades["_dte"] >= 1) & (trades["_dte"] <= 30)
    )
    _otm_call_vol = float(trades.loc[_otm_call_mask, "size"].sum())
    result["short_dated_otm_call_share"] = (
        round(_otm_call_vol / total_vol, 4) if total_vol > 0 else None
    )
    # Stamp underlying source for this feature
    result["underlying_source"] = (
        "greeks_store" if (
            greeks_chain is not None and not greeks_chain.empty
            and "underlying_price" in greeks_chain.columns
        ) else "none"
    )
    result["underlying_price"] = (
        float(greeks_chain["underlying_price"].dropna().iloc[0])
        if (greeks_chain is not None and not greeks_chain.empty
            and "underlying_price" in greeks_chain.columns
            and greeks_chain["underlying_price"].dropna().shape[0] > 0)
        else None
    )

    # block_share: top-decile trade-size share of volume
    if len(trades) > 10:
        _p90 = float(trades["size"].quantile(0.90))
        _block_vol = float(trades.loc[trades["size"] >= _p90, "size"].sum())
        result["block_share"] = round(_block_vol / float(total_vol), 4) if total_vol > 0 else 0.0
    else:
        result["block_share"] = None

    # trade_count alias (n_trades already set; add canonical name)
    result["trade_count"] = result["n_trades"]

    # Drop helper columns (T2a: aggregate-then-discard)
    # (trades DataFrame goes out of scope here — only result dict persists)

    return result


def _vol_gt_oi(trades: pd.DataFrame, oi_prev: pd.DataFrame | None) -> float | None:
    """Fraction of contracts where day volume > oi[t-1].

    Returns None if oi_prev is unavailable (can't compute without prior OI).
    oi[t-1] law: oi_prev must already be the correct prior-day OI (caller's responsibility).
    """
    if oi_prev is None or oi_prev.empty:
        return None

    contract_cols = [c for c in ("expiration", "strike", "right") if c in trades.columns]
    if not contract_cols:
        return None

    # Aggregate volume per contract
    vol_per = trades.groupby(contract_cols)["size"].sum().reset_index().rename(columns={"size": "vol"})

    # Normalize OI expiration format for merge
    oi = oi_prev.copy()
    if "expiration" in oi.columns:
        oi["expiration"] = pd.to_datetime(oi["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "expiration" in vol_per.columns:
        vol_per["expiration"] = pd.to_datetime(vol_per["expiration"], errors="coerce").dt.strftime("%Y-%m-%d")

    # Keep only relevant OI columns
    oi_cols = [c for c in contract_cols if c in oi.columns] + ["open_interest"]
    oi = oi[oi_cols].dropna(subset=["open_interest"])
    if oi.empty:
        return None

    merged = vol_per.merge(oi, on=[c for c in contract_cols if c in oi.columns], how="inner")
    if merged.empty:
        return None

    gt_flag = merged["vol"] > merged["open_interest"]
    return float(gt_flag.mean())


def _fill_nulls(result: dict) -> None:
    """Fill all feature keys with None when no trades are available.

    Covers both the legacy scalar/bucket keys and the P2.1 extension keys so
    that every path through aggregate_day() returns a dict with the full column
    set regardless of whether any trades were present.
    """
    scalar_keys = [
        "ask_side_call_premium", "bid_side_call_premium",
        "ask_side_put_premium",  "bid_side_put_premium",
        "net_signed_premium", "signed_contract_volume",
        "signed_delta_notional",
        "n_trades", "n_contracts", "gross_premium", "vol_gt_oi_share",
        # P2.1 extension keys
        "volume", "signed_pc_ratio", "zerodte_share", "dte_quality_share",
        "short_dated_otm_call_share", "trade_count", "block_share",
        "underlying_price",
    ]
    for k in scalar_keys:
        result[k] = None

    # underlying_source defaults to "none" (string sentinel) on empty days
    result["underlying_source"] = "none"

    for bucket_prefix in ("dte_0d", "dte_1_7d", "dte_8_30d", "dte_31_90d", "dte_90p"):
        result[f"{bucket_prefix}_net_premium"] = None
        result[f"{bucket_prefix}_vol_share"]   = None

    for bucket_prefix in ("money_itm", "money_atm", "money_near_otm", "money_far_otm"):
        result[f"{bucket_prefix}_net_premium"] = None
        result[f"{bucket_prefix}_vol_share"]   = None


# ─── numeric feature columns (for z-scoring) ─────────────────────────────────

def _numeric_feature_cols() -> list[str]:
    """Return all numeric feature column names that receive z-score companions."""
    cols = [
        "ask_side_call_premium", "bid_side_call_premium",
        "ask_side_put_premium",  "bid_side_put_premium",
        "net_signed_premium", "signed_contract_volume",
        "signed_delta_notional",
        "gross_premium", "vol_gt_oi_share",
        "n_trades", "n_contracts",
    ]
    for bucket_prefix in ("dte_0d", "dte_1_7d", "dte_8_30d", "dte_31_90d", "dte_90p"):
        cols += [f"{bucket_prefix}_net_premium", f"{bucket_prefix}_vol_share"]
    for bucket_prefix in ("money_itm", "money_atm", "money_near_otm", "money_far_otm"):
        cols += [f"{bucket_prefix}_net_premium", f"{bucket_prefix}_vol_share"]
    return cols


# ─── z-score computation ──────────────────────────────────────────────────────

def add_zscores(df: pd.DataFrame, window: int = ZSCORE_WINDOW,
                min_periods: int = ZSCORE_MIN_PERIODS) -> pd.DataFrame:
    """Add <col>_z252 columns for every numeric feature column.

    Trailing rolling z-score (252 sessions, min 60 prior rows).
    Null when fewer than min_periods history rows exist.
    DataFrame must be sorted by date ascending.

    COVERAGE NOTE: z-scores populate as history accrues. During the initial
    backfill (2021→ per T2a roadmap), early rows will show null z-scores
    until ≥60 sessions accumulate per root.
    """
    df = df.copy()
    df = df.sort_values("date").reset_index(drop=True)
    for col in _numeric_feature_cols():
        if col not in df.columns:
            df[f"{col}_z252"] = np.nan
            continue
        series = pd.to_numeric(df[col], errors="coerce")
        roll_mean = series.rolling(window, min_periods=min_periods).mean()
        roll_std  = series.rolling(window, min_periods=min_periods).std()
        # Avoid division by zero (std=0 → z=0 instead of NaN)
        z = (series - roll_mean) / roll_std.replace(0, np.nan)
        df[f"{col}_z252"] = z
    return df


# ─── upsert helpers ───────────────────────────────────────────────────────────

def upsert_feature_row(existing: pd.DataFrame, new_row: dict) -> pd.DataFrame:
    """Idempotent upsert: replace (or append) the row for new_row['date'].

    Always recomputes z-scores after upsert (z-scores are derived; not stored
    raw so they always reflect the full history in the parquet).
    """
    new_df = pd.DataFrame([new_row])
    date_val = str(new_row.get("date", ""))[:10]

    if existing.empty:
        combined = new_df
    else:
        # Drop any existing row for this date, then append
        mask = existing["date"].astype(str).str[:10] != date_val
        combined = pd.concat([existing[mask], new_df], ignore_index=True)

    combined = combined.sort_values("date").reset_index(drop=True)
    combined = add_zscores(combined)
    return combined
