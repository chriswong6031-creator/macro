"""HK CBBC / Warrant Leverage Map engine — display-tier context organ.

Surfaces HK's most distinctive microstructure: retail-leverage froth and
issuer-hedging "magnet" zones. Dense outstanding CBBC call levels near spot =
forced-sell cascade risk when spot touches the mandatory call price.

DISPLAY-ONLY. No buy/sell signals; no scoring. "Magnet" and "froth" are
descriptive labels — they accrue context, not edges.

Outputs (per bellwether underlying):
  bull_bear_ratio         — outstanding bull CBBC / outstanding bear CBBC
                            (>1 = retail positioning skewed bull; descriptive)
  bull_outstanding        — total bull CBBC outstanding (contracts)
  bear_outstanding        — total bear CBBC outstanding (contracts)
  total_outstanding       — bull + bear total
  leverage_state          — descriptive label (see _LEVERAGE_STATES)
  data_note               — honest caveat string (e.g. "call level not available")

W2 ADDITIONS — magnet cluster fields (per-underlying):
  magnet_below            — True when dense bull-CBBC calls cluster just below spot
                            (mandatory-call fires on down-touch → forced issuer-sell)
  magnet_above            — True when dense bear-CBBC calls cluster just above spot
                            (mandatory-call fires on up-touch → forced issuer-buy)
  nearest_magnet_pct      — distance to nearest magnet cluster as % of spot
                            (negative = below spot / bull magnet, positive = above)
  magnet_clusters         — list of cluster dicts [{level, side, outstanding_sum,
                              n_contracts, distance_pct}] sorted by |distance_pct|
  call_level_coverage     — fraction of outstanding CBBCs with a known call price
                            (honest: partial coverage is labelled, not hidden)

Sign-correctness invariant (critical):
  Bull-CBBC call price < spot at issuance (magnet BELOW spot).
  Bear-CBBC call price > spot at issuance (magnet ABOVE spot).
  distance_pct = (call_price / spot) - 1
    → negative for bull magnets (below spot)
    → positive for bear magnets (above spot)
  magnet_below flags the bull-CBBC side (negative distance_pct, dense cluster).
  A sign error here inverts the organ and produces the opposite policy read.

Bellwether universe (matches adr_bridge):
  9988.HK  Alibaba / 阿里巴巴
  0700.HK  Tencent / 腾讯
  3690.HK  Meituan / 美团
  9618.HK  JD.com  / 京东
  1810.HK  Xiaomi  / 小米
  9888.HK  Baidu   / 百度
  1024.HK  Kuaishou / 快手
  0981.HK  SMIC    / 中芯国际
  HSI      Hang Seng Index (index CBBCs)
  HSTECH   Hang Seng Tech Index (index CBBCs)

Freshness: degrades visibly (banner + null fields) when the store is missing
or stale. Never raises; never crashes the nightly render.

Forward ledger: data/hk_impulse/cbbc_ledger.jsonl
  One row per (date, underlying) when CN_LANE=asia.
  Fields: date, underlying, bull_bear_ratio, leverage_state, asof_freshness,
          magnet_below, magnet_above, nearest_magnet_pct, call_level_coverage.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

from engine.ledger_lane import asia_advance_enabled as _ledger_advance_enabled


# ---------------------------------------------------------------------------
# Bellwether mapping
# ---------------------------------------------------------------------------

class _Bellwether(NamedTuple):
    underlying_code: str   # as it appears in the CBBC short name (e.g. "HSI")
    hk_ticker: str         # e.g. "9988.HK" or "^HSI"
    name_en: str
    name_zh: str
    is_index: bool         # True for HSI/HSTECH (index CBBCs)


# The underlying_code is what appears after '#' in the CBBC short name
# Verified from live data: 'CT#HSI  RC2709C' → HSI, 'CT#HKEX RC2610A' → HKEX
_BELLWETHERS: list[_Bellwether] = [
    # HK-listed tech bellwethers (by underlying_code in CBBC names, verified)
    _Bellwether("BABA", "9988.HK", "Alibaba",  "阿里巴巴", False),
    _Bellwether("TENCENT", "0700.HK", "Tencent", "腾讯", False),
    _Bellwether("TEN", "0700.HK",  "Tencent",  "腾讯",    False),   # alternate abbrev
    _Bellwether("700",  "0700.HK",  "Tencent",  "腾讯",    False),
    _Bellwether("MEITUAN", "3690.HK", "Meituan", "美团",  False),
    _Bellwether("MEIT", "3690.HK", "Meituan",  "美团",    False),
    _Bellwether("JD",   "9618.HK",  "JD.com",   "京东",    False),
    _Bellwether("JDCOM", "9618.HK", "JD.com",  "京东",    False),
    _Bellwether("XIAOMI", "1810.HK", "Xiaomi",  "小米",   False),
    _Bellwether("XIAO",  "1810.HK", "Xiaomi",  "小米",    False),
    _Bellwether("BAIDU", "9888.HK", "Baidu",   "百度",    False),
    _Bellwether("BIDU",  "9888.HK", "Baidu",   "百度",    False),
    _Bellwether("KWSHOU","1024.HK",  "Kuaishou","快手",    False),
    _Bellwether("KUAI",  "1024.HK",  "Kuaishou","快手",    False),
    _Bellwether("SMIC",  "0981.HK",  "SMIC",    "中芯国际",False),
    # Index CBBCs (large volumes)
    _Bellwether("HSI",   "^HSI",     "HSI",     "恒生指数",True),
    _Bellwether("HSTE",  "^HSTECH",  "HSTECH",  "恒生科技",True),
    _Bellwether("HKEX",  "0388.HK",  "HKEx",    "港交所",  False),
]

# Canonical output ticker → deduplicated list of underlying codes to match
_TICKER_TO_CODES: dict[str, list[str]] = {}
_TICKER_META: dict[str, tuple[str, str, bool]] = {}
for _bw in _BELLWETHERS:
    _TICKER_TO_CODES.setdefault(_bw.hk_ticker, []).append(_bw.underlying_code.upper())
    _TICKER_META[_bw.hk_ticker] = (_bw.name_en, _bw.name_zh, _bw.is_index)

# Ordered list of tickers for output (deterministic display order)
_OUTPUT_TICKERS: list[str] = [
    "^HSI", "^HSTECH",
    "0700.HK", "9988.HK", "9618.HK", "3690.HK",
    "1810.HK", "9888.HK", "1024.HK", "0981.HK",
    "0388.HK",
]

# ---------------------------------------------------------------------------
# Leverage state labels (descriptive only)
# ---------------------------------------------------------------------------

_LEVERAGE_STATES = frozenset([
    "bull_skew_froth",   # bull outstanding >> bear (bull:bear > 3)
    "bull_skew",         # bull outstanding > bear (bull:bear 1.5-3)
    "balanced",          # roughly equal (bull:bear 0.67-1.5)
    "bear_skew",         # bear outstanding > bull (bull:bear 0.33-0.67)
    "bear_skew_froth",   # bear outstanding >> bull (bull:bear < 0.33)
    "no_data",           # store missing / zero outstanding
])

_FROTH_THRESHOLD   = 3.0   # ratio > this → froth label
_SKEW_THRESHOLD    = 1.5   # ratio > this (but <= froth) → skew label


def _leverage_state(bull: int, bear: int) -> str:
    if bull == 0 and bear == 0:
        return "no_data"
    if bear == 0:
        return "bull_skew_froth"
    if bull == 0:
        return "bear_skew_froth"
    ratio = bull / bear
    if ratio > _FROTH_THRESHOLD:
        return "bull_skew_froth"
    if ratio > _SKEW_THRESHOLD:
        return "bull_skew"
    if ratio >= (1.0 / _SKEW_THRESHOLD):
        return "balanced"
    if ratio >= (1.0 / _FROTH_THRESHOLD):
        return "bear_skew"
    return "bear_skew_froth"


# ---------------------------------------------------------------------------
# Magnet cluster computation (W2 — the flagship feature)
# ---------------------------------------------------------------------------

# Cluster bucket width as fraction of spot (2% bands)
_CLUSTER_BUCKET_PCT = 0.02

# "Dense" threshold: a cluster must hold >= this fraction of total outstanding
# for its side to qualify as a magnet
_MAGNET_DENSITY_THRESHOLD = 0.15

# Proximity threshold: only clusters within this % of spot are flagged as magnets
_MAGNET_PROXIMITY_PCT = 0.10  # 10% band around spot


def _compute_magnet_clusters(
        cbbc_with_calls: pd.DataFrame,
        spot: float,
) -> dict:
    """Compute call-level magnet clusters for one underlying given spot price.

    Parameters
    ----------
    cbbc_with_calls : DataFrame with columns:
        stock_code, call_price (float), bull_bear ('bull'|'bear'),
        outstanding (int)
    spot : float — current spot price of the underlying

    Returns a dict with keys:
        magnet_below         bool
        magnet_above         bool
        nearest_magnet_pct   float | None  (distance from spot, signed %)
        magnet_clusters      list[dict]
        call_level_coverage  float  (0..1)
        total_outstanding_with_call  int
        total_outstanding_without_call  int

    Sign invariant (CRITICAL — must be honoured here):
        distance_pct = (call_price / spot) - 1
        Bull CBBC call < spot → distance_pct < 0  → magnet BELOW spot (forced sell)
        Bear CBBC call > spot → distance_pct > 0  → magnet ABOVE spot (forced buy)

    Fail-open: empty DataFrame or spot=0 → returns null/empty cluster dict.
    """
    null_result: dict = {
        "magnet_below": False,
        "magnet_above": False,
        "nearest_magnet_pct": None,
        "magnet_clusters": [],
        "call_level_coverage": 0.0,
        "total_outstanding_with_call": 0,
        "total_outstanding_without_call": 0,
    }

    if cbbc_with_calls.empty or spot is None or spot <= 0:
        return null_result

    # Normalise column types defensively
    df = cbbc_with_calls.copy()
    df["call_price"] = pd.to_numeric(df["call_price"], errors="coerce")
    df["outstanding"] = pd.to_numeric(df["outstanding"], errors="coerce").fillna(0).astype(int)

    with_call   = df[df["call_price"].notna() & (df["call_price"] > 0)]
    without_call = df[df["call_price"].isna() | (df["call_price"] <= 0)]

    n_with    = int(with_call["outstanding"].sum())
    n_without = int(without_call["outstanding"].sum())
    total     = n_with + n_without
    coverage  = round(n_with / total, 4) if total > 0 else 0.0

    if with_call.empty:
        result = dict(null_result)
        result["call_level_coverage"] = coverage
        result["total_outstanding_with_call"] = n_with
        result["total_outstanding_without_call"] = n_without
        return result

    # Compute signed distance_pct for each CBBC with a known call price
    # distance_pct = (call_price / spot) - 1
    # Bull CBBC: call < spot → distance_pct < 0  (magnet below)
    # Bear CBBC: call > spot → distance_pct > 0  (magnet above)
    with_call = with_call.copy()
    with_call["distance_pct"] = (with_call["call_price"] / spot) - 1.0

    # Bucket by _CLUSTER_BUCKET_PCT-wide band.
    # bucket_idx = floor(distance_pct / bucket_width)  (signed integer).
    # math.floor toward -inf for negative values — correct: a call at -0.01 of spot
    # lands in bucket -1 (i.e. the band [-0.02, 0.00]), not bucket 0.
    bw = _CLUSTER_BUCKET_PCT
    with_call["bucket"] = with_call["distance_pct"].apply(
        lambda x: math.floor(x / bw))

    # Aggregate by bucket
    cluster_rows: list[dict] = []
    for bucket, grp in with_call.groupby("bucket"):
        bucket_center_pct = (bucket + 0.5) * bw
        outstanding_sum   = int(grp["outstanding"].sum())
        n_contracts       = len(grp)
        # Characterise: if >50% of contracts in bucket are bull → bull bucket
        bull_out  = int(grp[grp["bull_bear"] == "bull"]["outstanding"].sum())
        bear_out  = int(grp[grp["bull_bear"] == "bear"]["outstanding"].sum())
        side = "bull" if bull_out >= bear_out else "bear"
        cluster_rows.append({
            "bucket":          int(bucket),
            "distance_pct":    round(bucket_center_pct * 100, 2),  # in % units
            "level_approx":    round(spot * (1 + bucket_center_pct), 2),
            "side":            side,
            "outstanding_sum": outstanding_sum,
            "n_contracts":     n_contracts,
            "bull_outstanding": bull_out,
            "bear_outstanding": bear_out,
        })

    # Sort by proximity to spot (|distance_pct| ascending)
    cluster_rows.sort(key=lambda r: abs(r["distance_pct"]))

    # Identify magnets: clusters near spot with high density
    total_with_call_out = n_with
    magnet_below = False
    magnet_above = False
    nearest_below_pct: float | None = None
    nearest_above_pct: float | None = None

    for cl in cluster_rows:
        dist_pct_raw = cl["distance_pct"] / 100.0  # back to fraction
        if abs(dist_pct_raw) > _MAGNET_PROXIMITY_PCT:
            continue  # outside proximity band
        density = cl["outstanding_sum"] / total_with_call_out if total_with_call_out > 0 else 0
        if density < _MAGNET_DENSITY_THRESHOLD:
            continue  # not dense enough

        # Sign determines side (sign-correct: negative = below spot = bull magnet)
        if dist_pct_raw < 0 and cl["side"] == "bull":
            magnet_below = True
            if nearest_below_pct is None or abs(dist_pct_raw) < abs(nearest_below_pct):
                nearest_below_pct = cl["distance_pct"]  # already in % units, negative
        elif dist_pct_raw > 0 and cl["side"] == "bear":
            magnet_above = True
            if nearest_above_pct is None or abs(dist_pct_raw) < abs(nearest_above_pct):
                nearest_above_pct = cl["distance_pct"]  # positive

    # nearest_magnet_pct: the closer of the two (by |distance|), signed
    nearest_magnet_pct: float | None = None
    candidates = []
    if nearest_below_pct is not None:
        candidates.append(nearest_below_pct)
    if nearest_above_pct is not None:
        candidates.append(nearest_above_pct)
    if candidates:
        nearest_magnet_pct = min(candidates, key=abs)

    # Keep only clusters within proximity band for output (limit to top-10 by proximity)
    output_clusters = [
        cl for cl in cluster_rows
        if abs(cl["distance_pct"] / 100.0) <= _MAGNET_PROXIMITY_PCT
    ][:10]

    return {
        "magnet_below":                  magnet_below,
        "magnet_above":                  magnet_above,
        "nearest_magnet_pct":            round(nearest_magnet_pct, 2) if nearest_magnet_pct is not None else None,
        "magnet_clusters":               output_clusters,
        "call_level_coverage":           coverage,
        "total_outstanding_with_call":   n_with,
        "total_outstanding_without_call":n_without,
    }


# ---------------------------------------------------------------------------
# Price-store spot lookup
# ---------------------------------------------------------------------------

# Bellwether HK ticker → price-store key mapping
# The price store uses Yahoo Finance ticker format
_SPOT_KEYS: dict[str, str] = {
    "^HSI":    "^HSI",
    "^HSTECH": "^HSTECH",
    "0700.HK": "0700.HK",
    "9988.HK": "9988.HK",
    "9618.HK": "9618.HK",
    "3690.HK": "3690.HK",
    "1810.HK": "1810.HK",
    "9888.HK": "9888.HK",
    "1024.HK": "1024.HK",
    "0981.HK": "0981.HK",
    "0388.HK": "0388.HK",
}


def _load_spot_prices(data_root: Path | None = None) -> dict[str, float]:
    """Load last-close spot prices from the price store for bellwether tickers.

    Uses the same price-store pattern as hk_adr_bridge:
      HK equities: data/hk_stocks/<ticker>.parquet (column 'Close' or 'close')
      Indices (^HSI, ^HSTECH): data/hk/<ticker>.parquet (from hk_prices collector)

    Returns {} on any failure (fail-open: spot is optional for magnet %).
    """
    if data_root is None:
        data_root = config.data_dir()

    spots: dict[str, float] = {}
    for ticker, key in _SPOT_KEYS.items():
        try:
            # Equity path: data/hk_stocks/0700.HK.parquet
            # Index path:  data/hk/^HSI.parquet
            if key.startswith("^"):
                p = data_root / "hk" / f"{key}.parquet"
            else:
                p = data_root / "hk_stocks" / f"{key}.parquet"
            if not p.exists():
                continue
            df = pd.read_parquet(p)
            # Column may be 'Close', 'close', or a MultiIndex — handle both
            close_col = None
            for col in ("Close", "close", "Adj Close", "adj_close"):
                if col in df.columns:
                    close_col = col
                    break
            if close_col is None or df.empty:
                continue
            last_px = df[close_col].dropna().iloc[-1]
            if last_px > 0:
                spots[ticker] = float(last_px)
        except Exception:  # noqa: BLE001
            pass

    return spots


# ---------------------------------------------------------------------------
# Engine: per-underlying aggregation
# ---------------------------------------------------------------------------

def _underlying_matches(underlying_code: str, code_list: list[str]) -> bool:
    """True if the underlying_code from the XLSX matches any target code.

    Requires exact-match OR that the XLSX code starts with a target code
    (handles minor suffix variants from different issuers).

    We do NOT allow c.startswith(uc) (the reverse arm) because it causes
    short fragments to match multiple bellwethers — e.g. "B" would match
    both "BABA" (Alibaba 9988.HK) and "BAIDU" (Baidu 9888.HK), summing
    unrelated warrants into the wrong bellwether totals.

    Minimum token length guard: codes shorter than 2 chars are rejected to
    prevent single-letter fragments from sweeping large fractions of the
    universe.
    """
    uc = str(underlying_code or "").upper().strip()
    if len(uc) < 2:
        return False
    return any(uc == c or uc.startswith(c) for c in code_list if c)


def _aggregate_for_ticker(cbbc_df: pd.DataFrame,
                           ticker: str,
                           call_levels_df: pd.DataFrame | None = None,
                           spot: float | None = None) -> dict:
    """Aggregate CBBC outstanding for one output ticker.

    Returns a dict with bull_outstanding, bear_outstanding, total, ratio,
    leverage_state, data_note, and W2 magnet fields.

    Parameters
    ----------
    cbbc_df         : Latest outstanding DataFrame from W1 daily XLSX
    ticker          : Output ticker (e.g. '^HSI', '0700.HK')
    call_levels_df  : Optional call-level DataFrame from SLD PDFs (W2)
                      Columns: stock_code, call_price, bull_bear, outstanding, ...
    spot            : Current spot price for the underlying (for magnet %)
    """
    codes = _TICKER_TO_CODES.get(ticker, [])
    name_en, name_zh, is_index = _TICKER_META.get(ticker, (ticker, ticker, False))

    # W2 magnet null defaults
    _null_magnets: dict = {
        "magnet_below": False,
        "magnet_above": False,
        "nearest_magnet_pct": None,
        "magnet_clusters": [],
        "call_level_coverage": 0.0,
        "total_outstanding_with_call": 0,
        "total_outstanding_without_call": 0,
    }

    if cbbc_df.empty:
        return {
            "ticker": ticker, "name_en": name_en, "name_zh": name_zh,
            "is_index": is_index, "bull_outstanding": None, "bear_outstanding": None,
            "total_outstanding": None, "bull_bear_ratio": None,
            "leverage_state": "no_data",
            "data_note": "store empty",
            **_null_magnets,
        }

    # Match by underlying_code (best-effort name extraction from short_name)
    mask = cbbc_df["underlying_code"].apply(
        lambda uc: _underlying_matches(uc, codes))
    sub = cbbc_df[mask].copy()

    if sub.empty:
        return {
            "ticker": ticker, "name_en": name_en, "name_zh": name_zh,
            "is_index": is_index, "bull_outstanding": 0, "bear_outstanding": 0,
            "total_outstanding": 0, "bull_bear_ratio": None,
            "leverage_state": "no_data",
            "data_note": f"no CBBC found for {codes}",
            **_null_magnets,
        }

    bull_rows = sub[sub["bull_bear"] == "bull"]
    bear_rows = sub[sub["bull_bear"] == "bear"]
    bull_out = int(bull_rows["outstanding"].sum())
    bear_out = int(bear_rows["outstanding"].sum())
    total    = bull_out + bear_out

    if total == 0:
        ratio = None
    elif bear_out == 0:
        ratio = None  # infinite — displayed as "—" in UI
    else:
        ratio = round(bull_out / bear_out, 2)

    state = _leverage_state(bull_out, bear_out)

    # ---------------------------------------------------------------------------
    # W2: join call-levels and compute magnet clusters
    # ---------------------------------------------------------------------------
    magnet_data = dict(_null_magnets)
    call_level_sourced = False

    if call_levels_df is not None and not call_levels_df.empty:
        # Join outstanding sub with call_levels on stock_code
        cl = call_levels_df[["stock_code", "call_price"]].copy()
        cl["stock_code"] = cl["stock_code"].astype(str)
        sub_joined = sub.copy()
        sub_joined["stock_code"] = sub_joined["stock_code"].astype(str)
        merged = sub_joined.merge(cl, on="stock_code", how="left")

        n_with_call = int((merged["call_price"].notna() & (merged["call_price"] > 0)).sum())
        if n_with_call > 0:
            call_level_sourced = True
            if spot is not None and spot > 0:
                magnet_data = _compute_magnet_clusters(merged, spot)
            else:
                # No spot — can still report coverage but not magnet %
                n_without = int(
                    (merged["call_price"].isna() | (merged["call_price"] <= 0)).sum())
                t = n_with_call + n_without
                magnet_data["call_level_coverage"] = round(n_with_call / t, 4) if t > 0 else 0.0
                magnet_data["total_outstanding_with_call"] = int(
                    merged.loc[merged["call_price"].notna(), "outstanding"].sum())
                magnet_data["total_outstanding_without_call"] = int(
                    merged.loc[merged["call_price"].isna(), "outstanding"].sum())

    # Build honest data_note
    if call_level_sourced:
        cov = magnet_data.get("call_level_coverage", 0.0)
        if cov >= 0.95:
            data_note = "outstanding qty + mandatory call price from SLD PDFs"
        elif cov >= 0.5:
            data_note = f"call price coverage {cov:.0%} (partial SLD PDF coverage)"
        else:
            data_note = f"call price coverage {cov:.0%} — low SLD coverage; magnets may be incomplete"
    else:
        data_note = "outstanding qty from daily XLSX; mandatory call price not yet in SLD store"

    return {
        "ticker": ticker,
        "name_en": name_en,
        "name_zh": name_zh,
        "is_index": is_index,
        "bull_outstanding": bull_out,
        "bear_outstanding": bear_out,
        "total_outstanding": total,
        "bull_bear_ratio": ratio,
        "leverage_state": state,
        "n_cbbc_contracts": len(sub),
        "data_note": data_note,
        **magnet_data,
    }


# ---------------------------------------------------------------------------
# Freshness check
# ---------------------------------------------------------------------------

def _freshness_verdict(latest_trade_date: str | None) -> str:
    """Simple freshness verdict for the CBBC store."""
    if not latest_trade_date:
        return "dead"
    try:
        # trade_date may be DDMMYYYY or YYYYMMDD
        if re.match(r"^\d{8}$", latest_trade_date):
            try:
                td = datetime.strptime(latest_trade_date, "%d%m%Y").date()
            except ValueError:
                td = datetime.strptime(latest_trade_date, "%Y%m%d").date()
        else:
            return "dead"
    except Exception:
        return "dead"
    lag = (date.today() - td).days
    if lag <= 2:
        return "fresh"
    if lag <= 4:
        return "slow"
    return "stale"


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

_LEDGER_DIR_REL = "hk_impulse"
_LEDGER_FILE    = "cbbc_ledger.jsonl"
_ORGAN_ID       = "hk_cbbc"


def _ledger_path(data_root: Path | None = None) -> Path:
    if data_root is None:
        data_root = config.data_dir()
    return data_root / _LEDGER_DIR_REL / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else "")
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".cbbc_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def stamp_ledger(snap: dict, data_root: Path | None = None) -> int:
    """Append one ledger row per underlying in this snapshot.

    Gated by CN_LANE=asia (house law: nightly sole advancer).
    Idempotent on (date, underlying). Never raises.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_cbbc.stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    try:
        today_str = str(snap.get("as_of_trade_date", date.today().isoformat()))
        rows = load_ledger(data_root)
        existing = {(r.get("date"), r.get("underlying")) for r in rows}
        appended = 0
        for entry in snap.get("bellwethers", []):
            underlying = entry.get("ticker", "")
            key = (today_str, underlying)
            if key in existing:
                continue
            row = {
                "date": today_str,
                "underlying": underlying,
                "name_en": entry.get("name_en", ""),
                "bull_bear_ratio": entry.get("bull_bear_ratio"),
                "leverage_state": entry.get("leverage_state", "no_data"),
                "bull_outstanding": entry.get("bull_outstanding"),
                "bear_outstanding": entry.get("bear_outstanding"),
                "total_outstanding": entry.get("total_outstanding"),
                "asof_freshness": snap.get("freshness", "unknown"),
                # W2 magnet fields
                "magnet_below": entry.get("magnet_below", False),
                "magnet_above": entry.get("magnet_above", False),
                "nearest_magnet_pct": entry.get("nearest_magnet_pct"),
                "call_level_coverage": entry.get("call_level_coverage", 0.0),
            }
            rows.append(row)
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("hk_cbbc.stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Main engine entry point
# ---------------------------------------------------------------------------

def run(data_root: Path | None = None) -> dict:
    """Build the CBBC leverage map snapshot.

    Returns a dict with:
      as_of_trade_date, freshness, bellwethers (list), banner (dict|None),
      display_only (always True).

    Stamps the forward ledger when CN_LANE=asia.
    Never raises.
    """
    try:
        from collectors.hk_cbbc import load_latest, store_status
        status = store_status(data_root)
        cbbc_df = load_latest("cbbc", data_root)
        freshness = _freshness_verdict(status.get("latest_trade_date"))

        # W2: load call-levels from SLD PDF store (fail-open if not yet available)
        call_levels_df: pd.DataFrame | None = None
        sld_coverage: dict = {}
        try:
            from collectors.hk_cbbc_sld import load_call_levels, sld_store_status
            call_levels_df = load_call_levels(data_root)
            sld_coverage   = sld_store_status(data_root)
            if call_levels_df.empty:
                call_levels_df = None
        except Exception as e:  # noqa: BLE001
            log.warning("hk_cbbc: SLD call-levels unavailable (%s) — W1 mode", e)

        # W2: load spot prices from price store (fail-open)
        spot_prices = _load_spot_prices(data_root)

        # Banner when data is stale or missing
        banner = None
        if freshness in ("stale", "dead") or cbbc_df.empty:
            banner = {
                "en": f"CBBC data {freshness} — leverage map unavailable",
                "zh": f"牛熊证数据{('落后' if freshness == 'stale' else '缺失')}，杠杆图不可用",
            }

        bellwethers = []
        for ticker in _OUTPUT_TICKERS:
            spot = spot_prices.get(ticker)
            entry = _aggregate_for_ticker(cbbc_df, ticker,
                                          call_levels_df=call_levels_df,
                                          spot=spot)
            bellwethers.append(entry)

        snap = {
            "as_of_trade_date": status.get("latest_trade_date", ""),
            "freshness": freshness,
            "bellwethers": bellwethers,
            "banner": banner,
            "cbbc_total_contracts": status.get("cbbc_rows", 0),
            "dw_total_contracts": status.get("dw_rows", 0),
            "sld_call_levels_in_store": sld_coverage.get("call_levels_in_store", 0),
            "display_only": True,
        }

        # Stamp forward ledger (gated by CN_LANE=asia)
        stamp_ledger(snap, data_root)

        return snap

    except Exception as e:  # noqa: BLE001 — never crash the nightly render
        log.error("hk_cbbc engine failed: %s", e)
        return {
            "as_of_trade_date": "",
            "freshness": "dead",
            "bellwethers": [],
            "banner": {
                "en": "CBBC engine error — data unavailable",
                "zh": "牛熊证引擎错误，数据不可用",
            },
            "cbbc_total_contracts": 0,
            "dw_total_contracts": 0,
            "display_only": True,
        }
