"""Participation lobe — "whose money controls the tape" (W2 of China System Program).

Authority: context_only (CN-SYS-R1).  No scores, ranks, gates, or origination.

INPUT PLANE AND SOURCE DECISIONS
=================================
All inputs degrade to null + a named data_gaps entry on missing stores (CN-SYS-R4).

Turnover
--------
Primary: ``data/china_margin/daily_trade.parquet`` column ``margin_trade_amt`` (2014-02→).
  This is total SSE+SZSE market turnover as collected via the margin daily-trade API
  (unit: 亿 CNY per day).  It is the best available daily market-level total-turnover
  series in the store group: the breadth store has count-based adv/dec (no amount),
  sector files carry double-counted sub-segment amounts, and the tushare run_log is empty.
  z-scores computed over 20d and 60d rolling windows (min_periods 10/30).

Margin
------
``data/china_margin/balance.parquet`` columns:
  • ``margin_total`` — total financing balance (亿 CNY), 2010-03→ (market-level aggregate).
  • ``fin_pct_float`` — margin balance as % of float market-cap (pre-computed ratio).
  Neither per-name balance history (7-day window only) nor a cross-name aggregate from
  the detail store is used.  margin_to_mcap = fin_pct_float.

Limit breadth
-------------
Preferred: ``data/china_microstructure/limit_tape.parquet`` (W1 parallel build).
Fallback when absent: ``data/china_flows/limit_breadth.parquet`` columns ``zt`` (ZT count)
  and ``seal_rate`` (% seals held at close).  Window is ~30 days; backfilled rows use null
  for this leg and record the gap.

Southbound (Hong Kong → mainland)
----------------------------------
``data/china_connect/southbound.parquet`` column ``net`` (净买入, 万 CNY). 2014-11→.

Northbound: DEAD post-2024-08-16 (standing kill SLF-050).  We never treat a zero as a
live northbound reading.  Pre-2024-08 history may inform backfilled rows; those rows are
stamped with a data_gaps entry.  We do NOT read northbound.parquet as a live leg.

ETF flows
----------
``data/china_flows/etf_shares.parquet`` — ~5-week history (census-flagged); per-fund
share counts are unit-incommensurable across funds.  We use *per-fund share-change
z-scores* (5d rolling mean ÷ 5d std), then take the cross-fund median.  NEVER a raw sum.
Nullable: absent or empty → null + gap entry.

QVIX
-----
``data/china_qvix/qvix300.parquet`` column ``close``.  Available 2019-12-23→.
Critical: QVIX has *inverted* semantics vs US VIX — China's positive return-vol
correlation means a HIGH QVIX level co-occurs with SELLING, not fear of rising prices.
Following china_signals.qvix_regime convention we z-score QVIX vs its own 60d and
flag elevated z as a stress indicator (not a contrarian buy).  qvix_z is stored raw;
the participation risk classification uses the z-score direction.

Broker RS
----------
Sector ``data/china_sectors/801780.parquet`` (非银行金融 — non-bank financial, which
includes securities brokers) vs CSI 300 proxy ``data/china/510300.SS.parquet`` close.
20-day rolling RS = rolling sum of daily log returns (broker) minus (CSI300).
Available from ~2012 for broker sector, ~2007 for 510300.

REGIME / WHO_CONTROLS CLASSIFICATION
=====================================
Rule-based thresholds (all documented here; no ML):

  Participation regime
  --------------------
  dormant             turnover_z20 < -0.5 AND margin_chg_5d <= 0 AND zt_breadth <= 2%
  institutional_acc.  turnover_z20 in [-0.5, 0.5] AND southbound_z > 0.5
                      AND broker_rs > 0 (quiet accumulation with smart money)
  retail_ignition     turnover_z20 > 0.5 AND zt_breadth > 3%
                      AND margin_chg_5d <= median (retail, not leveraged yet)
  margin_acceleration turnover_z20 > 1.0 AND margin_chg_5d > 0 AND fin_pct_float rising
  broad_mania         turnover_z20 > 2.0 AND zt_breadth > 5% AND margin_chg_5d > 0
  distribution        turnover_z20 > 0.5 AND southbound_z < -0.5 AND broker_rs < 0
                      (offshore/smart selling into retail excitement)
  forced_deleveraging margin_chg_5d < -1% (absolute drop in balance > 1% in 5d) AND
                      turnover_z20 > 0 (forced not voluntary — volume stays up)
  unclear             all other combinations

  Who controls
  ------------
  retail              turnover_z20 > 1.0 AND zt_breadth > 3% AND southbound_z <= 0
  institutional       broker_rs > 0.5 AND turnover_z20 < 0.5
  margin              margin_chg_5d > 0 AND fin_pct_float > 3.5
  state_proxy         southbound_z < -1.0 AND turnover_z20 < 0
                      (unusual pattern: falling turnover + SB selling = state funds dominate)
  offshore            southbound_z > 1.0 AND broker_rs < 0
  mixed               no single leg dominates
  unclear             data_gaps prevent classification

  Risk
  ----
  fire_sale           forced_deleveraging regime OR qvix_z > 2.0
  frothy              broad_mania OR margin_acceleration AND fin_pct_float > 4.0
  normal              retail_ignition OR institutional_accumulation OR distribution
  low                 dormant

CONTRADICTIONS
==============
Tracked as a list of dict rows:  {a, b, detail}.  Examples:
  • turnover hot (z > 1) while zt_breadth cold (< 1%) — volume without breadth
  • southbound buying while broker_rs negative — HK flows vs domestic smart money split
  • margin accelerating while qvix elevated — leveraged during stress

FALSIFIERS
==========
Not produced here (belong to the cycle phase lobe W3).  W2 produces evidence[]/
contradictions[] consumed by the spine in W6.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
REGIME_VALUES = (
    "dormant",
    "institutional_accumulation",
    "retail_ignition",
    "margin_acceleration",
    "broad_mania",
    "distribution",
    "forced_deleveraging",
    "unclear",
)
WHO_CONTROLS_VALUES = ("retail", "institutional", "margin", "state_proxy", "offshore", "mixed", "unclear")
RISK_VALUES = ("low", "normal", "frothy", "fire_sale")

_TURNOVER_Z_HOT = 1.0
_TURNOVER_Z_WARM = 0.5
_TURNOVER_Z_COLD = -0.5
_ZT_BREADTH_MANIA = 5.0        # % of universe at limit-up during mania
_ZT_BREADTH_IGNITION = 3.0    # % threshold for retail ignition
_ZT_BREADTH_DORMANT = 2.0     # % ceiling for dormant
_MARGIN_DELEVERAGE_PCT = -1.0  # 5d balance change < -1% = forced deleveraging
_FIN_PCT_FROTHY = 4.0          # fin_pct_float > 4% = frothy leverage
_FIN_PCT_MARGIN_CTRL = 3.5    # fin_pct_float > 3.5% = margin dominated
_SB_Z_HOT = 1.0
_SB_Z_COLD = -0.5
_SB_Z_VERY_COLD = -1.0
_BROKER_RS_HOT = 0.5
_QVIX_PANIC_Z = 2.0

# --------------------------------------------------------------------------- #
# Data loaders (each degrades to null + gap entry)
# --------------------------------------------------------------------------- #
_ROOT = os.path.join(os.path.dirname(__file__), "..", "data")


def _data_path(*parts: str) -> str:
    return os.path.join(_ROOT, *parts)


def _load_turnover() -> tuple[pd.Series, list[str]]:
    """Return daily turnover series (亿 CNY) + any gap labels."""
    gaps: list[str] = []
    path = _data_path("china_margin", "daily_trade.parquet")
    if not os.path.exists(path):
        gaps.append("turnover:china_margin/daily_trade.parquet absent")
        return pd.Series(dtype=float, name="turnover_total"), gaps
    df = pd.read_parquet(path)
    if "margin_trade_amt" not in df.columns or df["margin_trade_amt"].isna().all():
        gaps.append("turnover:margin_trade_amt column missing or all-null")
        return pd.Series(dtype=float, name="turnover_total"), gaps
    s = df["margin_trade_amt"].rename("turnover_total").copy()
    s.index = pd.to_datetime(s.index)
    return s, gaps


def _load_margin() -> tuple[pd.DataFrame, list[str]]:
    """Return market-level margin DataFrame + gaps.

    Returns columns: margin_balance (margin_total from balance.parquet),
                     fin_pct_float, margin_chg_5d (% change in margin_total over 5d).
    Note: per-name history is 7-day window only — NOT used.
    """
    gaps: list[str] = []
    path = _data_path("china_margin", "balance.parquet")
    if not os.path.exists(path):
        gaps.append("margin:china_margin/balance.parquet absent")
        return pd.DataFrame(), gaps
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    out = pd.DataFrame(index=df.index)
    if "margin_total" in df.columns:
        out["margin_balance"] = df["margin_total"]
        out["margin_chg_5d"] = df["margin_total"].pct_change(5) * 100
    else:
        gaps.append("margin:margin_total column missing")
        out["margin_balance"] = np.nan
        out["margin_chg_5d"] = np.nan
    if "fin_pct_float" in df.columns:
        out["margin_to_mcap"] = df["fin_pct_float"]
    else:
        gaps.append("margin:fin_pct_float column missing")
        out["margin_to_mcap"] = np.nan
    return out, gaps


def _load_limit_breadth() -> tuple[pd.Series, list[str]]:
    """Return zt_breadth pct + gaps.

    Prefers data/china_microstructure/limit_tape.parquet (W1).
    Falls back to data/china_flows/limit_breadth.parquet.
    """
    gaps: list[str] = []

    # W1 preferred path
    ms_path = _data_path("china_microstructure", "limit_tape.parquet")
    if os.path.exists(ms_path):
        df = pd.read_parquet(ms_path)
        df.index = pd.to_datetime(df.index)
        if "limit_up_breadth_pct" in df.columns:
            s = df["limit_up_breadth_pct"].rename("zt_breadth")
            return s, gaps
        gaps.append("limit_breadth:limit_tape.parquet present but limit_up_breadth_pct missing")

    # Fallback: china_flows/limit_breadth.parquet
    fb_path = _data_path("china_flows", "limit_breadth.parquet")
    if os.path.exists(fb_path):
        df = pd.read_parquet(fb_path)
        df.index = pd.to_datetime(df.index)
        if "zt" in df.columns and "seal_rate" in df.columns:
            # Approximate breadth: zt_count is raw count; we don't have universe_n here.
            # Use seal_rate as a proxy for zt breadth (% of ZT names that held seal).
            # We record this as zt_breadth (seal_rate, %) and flag the approximation.
            gaps.append(
                "limit_breadth:W1 limit_tape absent; using china_flows/limit_breadth.parquet "
                "seal_rate as zt_breadth proxy (~30d window only); backfilled rows use null"
            )
            s = df["seal_rate"].rename("zt_breadth")
            return s, gaps

    gaps.append(
        "limit_breadth:neither china_microstructure/limit_tape.parquet "
        "nor china_flows/limit_breadth.parquet present"
    )
    return pd.Series(dtype=float, name="zt_breadth"), gaps


def _load_southbound() -> tuple[pd.Series, list[str]]:
    """Return southbound net (万 CNY) + gaps.

    NORTHBOUND IS DEAD post-2024-08-16 (standing kill SLF-050).  We never read it as live.
    """
    gaps: list[str] = []
    path = _data_path("china_connect", "southbound.parquet")
    if not os.path.exists(path):
        gaps.append("southbound:china_connect/southbound.parquet absent")
        return pd.Series(dtype=float, name="southbound_net"), gaps
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    if "net" not in df.columns:
        gaps.append("southbound:net column missing")
        return pd.Series(dtype=float, name="southbound_net"), gaps
    gaps.append(
        "northbound:DEAD post-2024-08-16 (SLF-050); never read as live; "
        "pre-2024-08 rows exist but not used as live signals"
    )
    return df["net"].rename("southbound_net"), gaps


def _load_etf_flows() -> tuple[pd.Series, list[str]]:
    """Return cross-fund median share-change z-score + gaps.

    Per-fund share-change z-scores (5d): history is ~5 weeks (census-flagged).
    Raw cross-fund sum is forbidden (unit-incommensurable).
    """
    gaps: list[str] = []
    path = _data_path("china_flows", "etf_shares.parquet")
    if not os.path.exists(path):
        gaps.append("etf_flows:china_flows/etf_shares.parquet absent")
        return pd.Series(dtype=float, name="etf_share_chg"), gaps
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    if df.empty or len(df) < 2:
        gaps.append("etf_flows:etf_shares.parquet too short (<2 rows)")
        return pd.Series(dtype=float, name="etf_share_chg"), gaps

    gaps.append(
        "etf_flows:history ~5 weeks only (census-flagged); per-fund z-scores used "
        "(NOT raw sum — unit-incommensurable across funds)"
    )
    # Per-fund daily share change
    chg = df.diff()
    # 5d rolling z-score per fund
    roll_mean = chg.rolling(5, min_periods=2).mean()
    roll_std = chg.rolling(5, min_periods=2).std()
    z = (chg - roll_mean) / roll_std.replace(0, np.nan)
    # Cross-fund median z
    median_z = z.median(axis=1).rename("etf_share_chg")
    return median_z, gaps


def _load_qvix() -> tuple[pd.Series, list[str]]:
    """Return QVIX close (China VIX, inverted semantics vs US) + gaps.

    Available 2019-12-23→.  z-scored vs own 60d for the risk assessment.
    """
    gaps: list[str] = []
    path = _data_path("china_qvix", "qvix300.parquet")
    if not os.path.exists(path):
        gaps.append("qvix:china_qvix/qvix300.parquet absent")
        return pd.Series(dtype=float, name="qvix"), gaps
    df = pd.read_parquet(path)
    df.index = pd.to_datetime(df.index)
    if "close" not in df.columns:
        gaps.append("qvix:close column missing")
        return pd.Series(dtype=float, name="qvix"), gaps
    gaps.append("qvix:available 2019-12-23+; pre-2020 rows use null")
    return df["close"].rename("qvix"), gaps


def _load_broker_rs() -> tuple[pd.Series, list[str]]:
    """Return 20d rolling RS of broker sector vs CSI 300 + gaps.

    Broker proxy: data/china_sectors/801780.parquet (非银行金融).
    CSI 300 proxy: data/china/510300.SS.parquet (close).
    RS = 20d cumulative log-return difference (broker - CSI300).
    """
    gaps: list[str] = []
    broker_path = _data_path("china_sectors", "801780.parquet")
    csi_path = _data_path("china", "510300.SS.parquet")

    if not os.path.exists(broker_path):
        gaps.append("broker_rs:china_sectors/801780.parquet absent")
        return pd.Series(dtype=float, name="broker_rs"), gaps
    if not os.path.exists(csi_path):
        gaps.append("broker_rs:china/510300.SS.parquet absent")
        return pd.Series(dtype=float, name="broker_rs"), gaps

    broker = pd.read_parquet(broker_path)
    broker.index = pd.to_datetime(broker.index)
    if "close" not in broker.columns:
        gaps.append("broker_rs:801780.parquet missing close column")
        return pd.Series(dtype=float, name="broker_rs"), gaps

    csi = pd.read_parquet(csi_path)
    csi.index = pd.to_datetime(csi.index)
    # Handle multi-level columns
    if isinstance(csi.columns, pd.MultiIndex):
        if "close" in csi.columns.get_level_values(-1):
            csi = csi.xs("close", axis=1, level=-1)
            if isinstance(csi, pd.DataFrame):
                csi = csi.iloc[:, 0]
        else:
            gaps.append("broker_rs:510300.SS.parquet close column not found in MultiIndex")
            return pd.Series(dtype=float, name="broker_rs"), gaps
    else:
        if "close" not in csi.columns:
            gaps.append("broker_rs:510300.SS.parquet missing close column")
            return pd.Series(dtype=float, name="broker_rs"), gaps
        csi = csi["close"]

    # Align and compute 20d cumulative log-return RS
    br_ret = np.log(broker["close"] / broker["close"].shift(1))
    csi_ret = np.log(csi / csi.shift(1))
    # Align on common dates
    aligned = pd.DataFrame({"broker": br_ret, "csi": csi_ret}).dropna(how="all")
    rs = (aligned["broker"] - aligned["csi"]).rolling(20, min_periods=10).sum()
    rs.name = "broker_rs"
    return rs, gaps


# --------------------------------------------------------------------------- #
# Z-score helper
# --------------------------------------------------------------------------- #
def _zscore(s: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    if min_periods is None:
        min_periods = max(5, window // 3)
    m = s.rolling(window, min_periods=min_periods).mean()
    sd = s.rolling(window, min_periods=min_periods).std()
    return ((s - m) / sd.replace(0, np.nan)).rename(f"{s.name}_z{window}")


# --------------------------------------------------------------------------- #
# Regime classifiers
# --------------------------------------------------------------------------- #
def _classify_regime(row: pd.Series) -> str:
    """Single-row participation regime classification (rule-based)."""
    tz20 = row.get("turnover_z20", np.nan)
    tz60 = row.get("turnover_z60", np.nan)  # noqa: F841 — available for future refinement
    mc5 = row.get("margin_chg_5d", np.nan)
    fpt = row.get("margin_to_mcap", np.nan)
    ztb = row.get("zt_breadth", np.nan)
    sbz = row.get("southbound_z", np.nan)
    brrs = row.get("broker_rs", np.nan)

    # Forced deleveraging: margin drops fast AND (volume elevated OR volume missing)
    # The 2015-H1 crash had circuit-breaker halts — volume goes NEGATIVE z, not positive.
    # Allow forced_deleveraging when margin drops sharply even if turnover is depressed.
    if _notna(mc5) and mc5 < _MARGIN_DELEVERAGE_PCT:
        # Strong deleveraging signal: > -5% (e.g. 2015-H2 crash) fires even with low volume
        if mc5 < -5.0:
            return "forced_deleveraging"
        # Moderate: require at least positive turnover (forced selling into volume)
        if _notna(tz20) and tz20 > 0:
            return "forced_deleveraging"

    # Need at least turnover to proceed beyond unclear
    if not _notna(tz20):
        # Margin-only path: can classify margin_acceleration without turnover if signal is strong
        if _notna(mc5) and _notna(fpt):
            if mc5 > 1.0 and fpt > _FIN_PCT_FROTHY:
                return "margin_acceleration"
        return "unclear"

    zt_hot = _notna(ztb) and ztb > _ZT_BREADTH_MANIA
    zt_ignition = _notna(ztb) and ztb > _ZT_BREADTH_IGNITION
    zt_missing = not _notna(ztb)  # backfill rows have no zt data
    margin_rising = _notna(mc5) and mc5 > 0
    fpt_elevated = _notna(fpt) and fpt > _FIN_PCT_FROTHY
    sb_hot = _notna(sbz) and sbz > _SB_Z_HOT
    sb_cold = _notna(sbz) and sbz < _SB_Z_COLD
    broker_pos = _notna(brrs) and brrs > 0

    # Broad mania: everything hot (when breadth available)
    if tz20 > _TURNOVER_Z_HOT * 2 and zt_hot and margin_rising:
        return "broad_mania"

    # Broad mania: margin proxy path (when zt_breadth absent, e.g. backfill)
    # 2015-H1 type: turnover very hot + margin racing + leverage extreme
    if tz20 > _TURNOVER_Z_HOT * 2 and zt_missing and margin_rising and fpt_elevated:
        return "broad_mania"

    # Margin acceleration: turnover warm/hot + margin rising + leverage elevated
    if tz20 > _TURNOVER_Z_WARM and margin_rising and fpt_elevated:
        return "margin_acceleration"

    # Margin acceleration: even at moderate turnover if leverage is expanding fast
    # Captures the early 2015-H1 ramp where turnover was mid-range but margin surging
    if _notna(mc5) and mc5 > 2.0 and _notna(fpt) and fpt > 3.0 and tz20 > _TURNOVER_Z_COLD:
        return "margin_acceleration"

    # Distribution: smart money selling into retail excitement
    if tz20 > _TURNOVER_Z_WARM and sb_cold and (_notna(brrs) and brrs < 0):
        return "distribution"

    # Retail ignition: turnover picking up + ZT breadth rising, not yet leveraged
    if tz20 > _TURNOVER_Z_WARM and zt_ignition and not margin_rising:
        return "retail_ignition"

    # Institutional accumulation: quiet + smart money inflows
    if _TURNOVER_Z_COLD <= tz20 <= _TURNOVER_Z_WARM and sb_hot and broker_pos:
        return "institutional_accumulation"

    # Dormant: low turnover, no margin growth, no ZT activity
    if tz20 < _TURNOVER_Z_COLD:
        zt_dormant = zt_missing or ztb <= _ZT_BREADTH_DORMANT
        if not margin_rising and zt_dormant:
            return "dormant"

    return "unclear"


def _classify_who_controls(row: pd.Series) -> str:
    tz20 = row.get("turnover_z20", np.nan)
    ztb = row.get("zt_breadth", np.nan)
    sbz = row.get("southbound_z", np.nan)
    brrs = row.get("broker_rs", np.nan)
    fpt = row.get("margin_to_mcap", np.nan)
    mc5 = row.get("margin_chg_5d", np.nan)
    data_gaps = row.get("_n_gaps", 0)

    # If critical legs are all null → unclear
    if not _notna(tz20) and not _notna(sbz) and not _notna(brrs):
        return "unclear"

    retail = _notna(tz20) and tz20 > _TURNOVER_Z_HOT and \
             _notna(ztb) and ztb > _ZT_BREADTH_IGNITION and \
             (not _notna(sbz) or sbz <= 0)

    institutional = _notna(brrs) and brrs > _BROKER_RS_HOT and \
                    _notna(tz20) and tz20 < _TURNOVER_Z_WARM

    margin_ctrl = _notna(mc5) and mc5 > 0 and \
                  _notna(fpt) and fpt > _FIN_PCT_MARGIN_CTRL

    # State proxy: falling turnover + SB selling (offshore/SB being the outflow indicator)
    state_proxy = _notna(sbz) and sbz < _SB_Z_VERY_COLD and \
                  _notna(tz20) and tz20 < 0

    offshore = _notna(sbz) and sbz > _SB_Z_HOT and \
               _notna(brrs) and brrs < 0

    signals = sum([retail, institutional, margin_ctrl, state_proxy, offshore])
    if signals == 0:
        return "mixed"
    if signals > 1:
        return "mixed"
    if retail:
        return "retail"
    if institutional:
        return "institutional"
    if margin_ctrl:
        return "margin"
    if state_proxy:
        return "state_proxy"
    if offshore:
        return "offshore"
    return "mixed"


def _classify_risk(row: pd.Series) -> str:
    regime = row.get("regime", "unclear")
    qvix_z = row.get("qvix_z", np.nan)
    fpt = row.get("margin_to_mcap", np.nan)

    if regime == "forced_deleveraging" or (_notna(qvix_z) and qvix_z > _QVIX_PANIC_Z):
        return "fire_sale"

    if regime == "broad_mania":
        return "frothy"
    if regime == "margin_acceleration" and _notna(fpt) and fpt > _FIN_PCT_FROTHY:
        return "frothy"

    if regime in ("dormant",):
        return "low"

    return "normal"


def _build_evidence(row: pd.Series) -> list[str]:
    ev: list[str] = []
    tz20 = row.get("turnover_z20", np.nan)
    sbz = row.get("southbound_z", np.nan)
    mc5 = row.get("margin_chg_5d", np.nan)
    fpt = row.get("margin_to_mcap", np.nan)
    brrs = row.get("broker_rs", np.nan)
    ztb = row.get("zt_breadth", np.nan)
    qvix_z = row.get("qvix_z", np.nan)

    if _notna(tz20):
        ev.append(f"turnover_z20={tz20:.2f}")
    if _notna(sbz) and sbz > _SB_Z_HOT:
        ev.append(f"southbound_net z={sbz:.2f} (hot inflow)")
    if _notna(mc5) and mc5 > 0:
        ev.append(f"margin_chg_5d={mc5:.2f}% (rising)")
    if _notna(fpt):
        ev.append(f"fin_pct_float={fpt:.2f}%")
    if _notna(brrs) and brrs > 0:
        ev.append(f"broker_rs={brrs:.4f} (positive, sector leading)")
    if _notna(ztb) and ztb > _ZT_BREADTH_IGNITION:
        ev.append(f"zt_breadth={ztb:.1f}% (elevated)")
    if _notna(qvix_z):
        ev.append(f"qvix_z={qvix_z:.2f} (inverted-semantics: high=stress)")
    return ev


def _build_contradictions(row: pd.Series) -> list[dict[str, str]]:
    cx: list[dict[str, str]] = []
    tz20 = row.get("turnover_z20", np.nan)
    ztb = row.get("zt_breadth", np.nan)
    sbz = row.get("southbound_z", np.nan)
    brrs = row.get("broker_rs", np.nan)
    mc5 = row.get("margin_chg_5d", np.nan)
    qvix_z = row.get("qvix_z", np.nan)

    # Volume hot but no breadth
    if _notna(tz20) and tz20 > _TURNOVER_Z_HOT and _notna(ztb) and ztb < 1.0:
        cx.append({
            "a": f"turnover_z20={tz20:.2f} (hot)",
            "b": f"zt_breadth={ztb:.1f}% (cold)",
            "detail": "volume concentrated; narrow breadth — likely sector-specific, not broad participation"
        })

    # SB buying vs broker RS divergence
    if _notna(sbz) and sbz > _SB_Z_HOT and _notna(brrs) and brrs < 0:
        cx.append({
            "a": f"southbound_z={sbz:.2f} (inflow)",
            "b": f"broker_rs={brrs:.4f} (negative)",
            "detail": "HK/offshore buying but domestic broker sector underperforming CSI300 — cross-market split"
        })

    # Margin accelerating into stress
    if _notna(mc5) and mc5 > 0 and _notna(qvix_z) and qvix_z > _QVIX_PANIC_Z:
        cx.append({
            "a": f"margin_chg_5d={mc5:.2f}% (rising)",
            "b": f"qvix_z={qvix_z:.2f} (elevated stress, inverted semantics)",
            "detail": "leverage increasing during high-vol/stress period — late-cycle risk"
        })

    # SB cold while turnover hot (distribution pattern)
    if _notna(sbz) and sbz < _SB_Z_COLD and _notna(tz20) and tz20 > _TURNOVER_Z_WARM:
        cx.append({
            "a": f"southbound_z={sbz:.2f} (outflow)",
            "b": f"turnover_z20={tz20:.2f} (hot)",
            "detail": "offshore selling into retail-driven volume — potential distribution"
        })

    return cx


def _notna(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, float) and np.isnan(v):
        return False
    return True


# --------------------------------------------------------------------------- #
# Main build function
# --------------------------------------------------------------------------- #
def build_tape(backfill: bool = False) -> pd.DataFrame:
    """Build the participation tape DataFrame.

    Parameters
    ----------
    backfill : bool
        When True all rows are stamped backfill=True and rows before the first
        forward-accrual date carry per-row data_gaps indicating partial input coverage.

    Returns
    -------
    DataFrame with columns matching the §5 frozen schema contract:
        date, turnover_total, turnover_z20, turnover_z60, margin_balance,
        margin_chg_5d, margin_to_mcap, southbound_net, southbound_z,
        etf_share_chg (nullable), zt_breadth, failed_seal_ratio (nullable),
        qvix, qvix_z, broker_rs,
        regime, who_controls, risk,
        data_gaps (list, serialised as pipe-delimited string in parquet),
        backfill (bool).
    """
    all_gaps: list[str] = []

    # --- load all planes ---
    turnover, t_gaps = _load_turnover()
    margin_df, m_gaps = _load_margin()
    zt_s, zt_gaps = _load_limit_breadth()
    sb_s, sb_gaps = _load_southbound()
    etf_s, etf_gaps = _load_etf_flows()
    qvix_s, qvix_gaps = _load_qvix()
    broker_rs, br_gaps = _load_broker_rs()

    all_gaps = t_gaps + m_gaps + zt_gaps + sb_gaps + etf_gaps + qvix_gaps + br_gaps
    for g in all_gaps:
        log.info("data_gap: %s", g)

    # --- z-scores ---
    tz20 = _zscore(turnover, 20, 10).rename("turnover_z20")
    tz60 = _zscore(turnover, 60, 30).rename("turnover_z60")
    sbz = _zscore(sb_s, 60, 20).rename("southbound_z")
    qvix_z = _zscore(qvix_s, 60, 20).rename("qvix_z")

    # --- align on union index ---
    frame = pd.DataFrame({
        "turnover_total": turnover,
        "turnover_z20": tz20,
        "turnover_z60": tz60,
        "southbound_net": sb_s,
        "southbound_z": sbz,
        "etf_share_chg": etf_s,
        "zt_breadth": zt_s,
        "qvix": qvix_s,
        "qvix_z": qvix_z,
        "broker_rs": broker_rs,
    })

    # Add margin columns
    if not margin_df.empty:
        for col in ["margin_balance", "margin_chg_5d", "margin_to_mcap"]:
            frame[col] = margin_df[col] if col in margin_df.columns else np.nan
    else:
        frame["margin_balance"] = np.nan
        frame["margin_chg_5d"] = np.nan
        frame["margin_to_mcap"] = np.nan

    # failed_seal_ratio: comes from W1 limit_tape if present
    frame["failed_seal_ratio"] = np.nan
    ms_path = _data_path("china_microstructure", "limit_tape.parquet")
    if os.path.exists(ms_path):
        lt = pd.read_parquet(ms_path)
        lt.index = pd.to_datetime(lt.index)
        if "failed_up_seal_count" in lt.columns and "limit_up_count" in lt.columns:
            fsr = (lt["failed_up_seal_count"] / lt["limit_up_count"].replace(0, np.nan))
            frame["failed_seal_ratio"] = fsr

    # Sort index
    frame = frame.sort_index()

    # Drop rows where EVERYTHING is null (pre-data dates)
    key_cols = ["turnover_total", "margin_balance", "southbound_net", "qvix"]
    non_null_mask = frame[key_cols].notna().any(axis=1)
    frame = frame[non_null_mask].copy()

    # --- per-row classification ---
    # Count null legs for who_controls clarity
    leg_cols = ["turnover_z20", "margin_chg_5d", "southbound_z", "zt_breadth", "broker_rs", "qvix_z"]
    frame["_n_gaps"] = frame[leg_cols].isna().sum(axis=1)

    regimes = []
    who_controls_list = []
    risks = []
    evidence_list = []
    contradiction_list = []
    row_gaps_list = []

    for dt, row in frame.iterrows():
        # Build per-row gaps
        row_gaps: list[str] = []
        for col in ["turnover_z20", "southbound_z", "zt_breadth", "qvix_z", "broker_rs", "etf_share_chg"]:
            if pd.isna(row.get(col, np.nan)):
                row_gaps.append(f"{col}:null on {dt.date()}")
        # Northbound dead note on all rows
        row_gaps.append("northbound:DEAD post-2024-08-16 SLF-050")

        regime = _classify_regime(row)
        who = _classify_who_controls(row)

        regime_row = row.copy()
        regime_row["regime"] = regime
        risk = _classify_risk(regime_row)

        ev = _build_evidence(row)
        cx = _build_contradictions(row)

        regimes.append(regime)
        who_controls_list.append(who)
        risks.append(risk)
        evidence_list.append(ev)
        contradiction_list.append(cx)
        row_gaps_list.append(row_gaps)

    frame["regime"] = regimes
    frame["who_controls"] = who_controls_list
    frame["risk"] = risks
    # Store evidence/contradictions/data_gaps as pipe-delimited strings for parquet
    frame["evidence"] = ["|".join(e) for e in evidence_list]
    frame["contradictions"] = [str(c) for c in contradiction_list]
    frame["data_gaps"] = ["|".join(g) for g in row_gaps_list]
    frame["backfill"] = backfill

    # Drop internal helper
    frame = frame.drop(columns=["_n_gaps"])

    # Final column ordering per §5 schema
    cols_ordered = [
        "turnover_total", "turnover_z20", "turnover_z60",
        "margin_balance", "margin_chg_5d", "margin_to_mcap",
        "southbound_net", "southbound_z",
        "etf_share_chg",
        "zt_breadth", "failed_seal_ratio",
        "qvix", "qvix_z",
        "broker_rs",
        "regime", "who_controls", "risk",
        "data_gaps", "backfill",
        "evidence", "contradictions",
    ]
    # Only keep columns that exist
    cols_ordered = [c for c in cols_ordered if c in frame.columns]
    # Add any extras at end
    for c in frame.columns:
        if c not in cols_ordered:
            cols_ordered.append(c)
    frame = frame[cols_ordered]

    log.info(
        "build_tape: %d rows, %d all-session gaps, regime value_counts=%s",
        len(frame),
        len(all_gaps),
        frame["regime"].value_counts().to_dict() if not frame.empty else {},
    )
    return frame


def latest_snapshot(tape: pd.DataFrame) -> dict:
    """Return the latest-row dict for site JSON output.

    Includes evidence[], contradictions[], data_gaps[] as proper lists.
    """
    if tape.empty:
        return {"error": "empty tape", "authority": {"tier": "context_only"}}
    row = tape.iloc[-1].copy()
    date_str = tape.index[-1].strftime("%Y-%m-%d") if hasattr(tape.index[-1], "strftime") else str(tape.index[-1])

    # Deserialize pipe-delimited fields
    def _split(v: Any) -> list:
        if isinstance(v, str) and v:
            return v.split("|")
        return []

    snap: dict = {"date": date_str, "authority": {"tier": "context_only"}}
    for col in ["turnover_z20", "turnover_z60", "margin_balance", "margin_chg_5d",
                "margin_to_mcap", "southbound_net", "southbound_z",
                "etf_share_chg", "zt_breadth", "failed_seal_ratio",
                "qvix", "qvix_z", "broker_rs", "regime", "who_controls", "risk"]:
        v = row.get(col, None)
        if isinstance(v, float) and np.isnan(v):
            snap[col] = None
        elif isinstance(v, (np.floating, np.integer)):
            snap[col] = float(v)
        else:
            snap[col] = v

    snap["evidence"] = _split(row.get("evidence", ""))
    snap["contradictions_raw"] = row.get("contradictions", "")  # keep raw str
    snap["data_gaps"] = _split(row.get("data_gaps", ""))
    snap["backfill"] = bool(row.get("backfill", False))
    return snap
