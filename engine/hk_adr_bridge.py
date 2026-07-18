"""HK ADR Overnight Bridge — display-tier context organ (W1 data-plane).

Surfaces what US-listed ADRs/ETFs did AFTER the HK close, implying the next HK
session's open. DISPLAY-ONLY. Never originates a buy/sell signal or asserts an
edge. Accrues a forward ledger from day one so the brain gets labeled data.

Timezone alignment (critical):
    HK closes ~08:00 UTC (16:00 HKT = UTC+8).
    US markets close ~20:00–21:00 UTC (NYSE: 16:00 ET = UTC-4/UTC-5).
    For HK session date T:
        T's close = ~08:00 UTC on T (calendar date T in HK).
        The US close that IMPLIES the next HK open is the US close on the SAME
        calendar date T (NYSE closes ~20:00-21:00 UTC on T, which is AFTER HK
        closes at 08:00 UTC on T, and BEFORE T+1's HK open at 01:30 UTC on T+1).
    So: ADR close on calendar date T → implies HK open on session T+1.
    We compute: adr_pct = ADR(T).close / ADR(T-1).close - 1  (the US session
    T move that HK observes overnight).

ADR → HK mapping:
    Direct twins (same underlying company):
        BABA  ↔ 9988.HK  (Alibaba)
        BIDU  ↔ 9888.HK  (Baidu)
        JD    ↔ 9618.HK  (JD.com)
        PDD   ↔ 9961.HK  (Pinduoduo / PDD Holdings)
    No clean direct HK-listed ADR twin:
        0700.HK (Tencent)   → OTC TCEHY; thin/illiquid → group ETF proxy only
        3690.HK (Meituan)   → no US listing → group ETF proxy only
        1810.HK (Xiaomi)    → no US listing → group ETF proxy only
        1024.HK (Kuaishou)  → no US listing → group ETF proxy only
        0981.HK (SMIC)      → ADR delisted; sanctions risk → group ETF proxy only
    Group ETF proxies: KWEB (KraneShares CSI China Internet) + FXI (iShares China
        Large-Cap). Both labeled "proxy, no direct ADR" in output.

Context flag thresholds (DESCRIPTIVE ONLY — not a buy/sell call):
    gap_pct >= +3%  → strong_up
    gap_pct >= +1%  → up
    gap_pct >= -1%  → flat
    gap_pct >= -3%  → down
    gap_pct < -3%   → strong_down
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pandas as pd

from lib import config
from lib.hk_calendar import expected_last_session, is_session, last_session_on_or_before

log = logging.getLogger(__name__)


from engine.ledger_lane import asia_advance_enabled as _ledger_advance_enabled

# ---------------------------------------------------------------------------
# ADR → HK mapping
# ---------------------------------------------------------------------------

class _Pair(NamedTuple):
    hk_ticker: str       # e.g. "9988.HK"
    hk_name_en: str      # e.g. "Alibaba"
    hk_name_zh: str      # e.g. "阿里巴巴"
    adr_ticker: str      # e.g. "BABA" or "KWEB" (proxy)
    adr_source: str      # "direct" | "proxy"
    proxy_note: str      # "" for direct; human note for proxy

# Direct twins — same underlying company, percent moves are directly comparable
_DIRECT_PAIRS: list[_Pair] = [
    _Pair("9988.HK", "Alibaba", "阿里巴巴", "BABA", "direct", ""),
    _Pair("9888.HK", "Baidu",   "百度",     "BIDU", "direct", ""),
    _Pair("9618.HK", "JD.com",  "京东",     "JD",   "direct", ""),
    _Pair("9961.HK", "PDD",     "拼多多",   "PDD",  "direct", ""),
]

# Names with no clean direct ADR: use group ETF proxy (KWEB is preferred because
# it is tech/internet-heavy; FXI is broader large-cap; both are labeled "proxy").
# TCEHY (Tencent OTC) is explicitly excluded: thin/illiquid, not in yahoo store.
_PROXY_PAIRS: list[_Pair] = [
    _Pair("0700.HK", "Tencent",  "腾讯",   "KWEB", "proxy", "proxy, no direct ADR; Tencent OTC (TCEHY) too thin"),
    _Pair("3690.HK", "Meituan",  "美团",   "KWEB", "proxy", "proxy, no direct ADR"),
    _Pair("1810.HK", "Xiaomi",   "小米",   "KWEB", "proxy", "proxy, no direct ADR"),
    _Pair("1024.HK", "Kuaishou", "快手",   "KWEB", "proxy", "proxy, no direct ADR"),
    _Pair("0981.HK", "SMIC",     "中芯国际", "FXI", "proxy", "proxy, no direct ADR; ADR delisted"),
]

ALL_PAIRS: list[_Pair] = _DIRECT_PAIRS + _PROXY_PAIRS

# Group ETFs used for the composite
_ETF_TICKERS = ["KWEB", "FXI"]

# ---------------------------------------------------------------------------
# Gap context (purely descriptive thresholds)
# ---------------------------------------------------------------------------

_GAP_STRONG_UP  =  3.0   # pct
_GAP_UP         =  1.0
_GAP_FLAT_LO    = -1.0
_GAP_DOWN       = -3.0


def _gap_context(pct: float | None) -> str:
    """Map a percent gap to a descriptive context label (NOT a signal)."""
    if pct is None:
        return "unknown"
    if pct >= _GAP_STRONG_UP:
        return "strong_up"
    if pct >= _GAP_UP:
        return "up"
    if pct >= _GAP_FLAT_LO:
        return "flat"
    if pct >= _GAP_DOWN:
        return "down"
    return "strong_down"


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_adr(ticker: str, data_root: Path) -> pd.Series | None:
    """Load a daily close series for a US ADR/ETF.

    Primary source: data/yahoo/<ticker>.parquet (preferred; written by the nightly
    yahoo adapter + seeded by fetch_basket_extras.PROXIES).
    Fallback: data/massive_stock_day/<ticker>.parquet — used when the yahoo store
    lacks the ticker (e.g. KWEB before it was added to PROXIES). Column layout may
    differ; we search for 'close' or 'Close'.
    The same freshness gate applies to both sources: a stale fallback is visible as
    a degraded badge rather than silently wrong.
    Returns None on any error (fail-open design).
    """
    primary = data_root / "yahoo" / f"{ticker}.parquet"
    fallback = data_root / "massive_stock_day" / f"{ticker}.parquet"

    for path, source_label in [(primary, "yahoo"), (fallback, "massive_stock_day")]:
        if not path.exists():
            continue
        try:
            df = pd.read_parquet(path)
            # Normalise MultiIndex column header (yfinance bulk downloads)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            # Resolve close column: prefer lowercase 'close', accept 'Close'
            if "close" not in df.columns and "Close" in df.columns:
                df = df.rename(columns={"Close": "close"})
            if "close" not in df.columns:
                log.warning("hk_adr_bridge: no close column in %s for %s", source_label, ticker)
                continue
            df.index = pd.to_datetime(df.index).normalize()
            df = df.sort_index()
            if source_label == "massive_stock_day":
                log.info("hk_adr_bridge: %s loaded from fallback massive_stock_day (not in yahoo/)", ticker)
            return df["close"].dropna()
        except Exception as e:  # noqa: BLE001
            log.warning("hk_adr_bridge: failed to load ADR %s from %s: %s", ticker, source_label, e)
            continue

    log.warning("hk_adr_bridge: ADR parquet missing from both yahoo/ and massive_stock_day/: %s", ticker)
    return None


def _load_hk(ticker: str, data_root: Path) -> pd.Series | None:
    """Load a daily close series for an HK stock from data/hk_stocks/<ticker>.parquet.
    Returns None on any error."""
    try:
        p = data_root / "hk_stocks" / f"{ticker}.parquet"
        if not p.exists():
            log.warning("hk_adr_bridge: HK parquet missing: %s", p)
            return None
        df = pd.read_parquet(p)
        # Normalise column name — may have MultiIndex header from yfinance
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if "close" not in df.columns and "Close" in df.columns:
            df = df.rename(columns={"Close": "close"})
        df.index = pd.to_datetime(df.index).normalize()
        df = df.sort_index()
        return df["close"].dropna()
    except Exception as e:  # noqa: BLE001
        log.warning("hk_adr_bridge: failed to load HK %s: %s", ticker, e)
        return None


# ---------------------------------------------------------------------------
# Core: compute implied open gap for a single (HK session date, ADR pair)
# ---------------------------------------------------------------------------

def _adr_pct_on_date(adr_close: pd.Series, us_date: date) -> float | None:
    """
    Compute the ADR percent change on `us_date` (the US trading session that
    occurs AFTER the HK close on that calendar date).

    adr_pct = close(us_date) / close(prev_us_trading_date) - 1
    Returns None if either bar is missing.
    """
    ts = pd.Timestamp(us_date)
    if ts not in adr_close.index:
        return None
    # Find the prior available ADR bar (skip missing dates = holidays/weekends)
    idx = adr_close.index
    pos = idx.get_loc(ts)
    if pos < 1:
        return None
    prev_close = float(adr_close.iloc[pos - 1])
    curr_close = float(adr_close.iloc[pos])
    if prev_close <= 0:
        return None
    return (curr_close / prev_close - 1.0) * 100.0


def _best_adr_date(adr_series_map: dict[str, "pd.Series | None"],
                   target_date: date) -> "tuple[date, bool]":
    """Return the best ADR date to use and whether it is an exact match.

    Strategy:
    1. If any series has a bar on ``target_date``, return (target_date, True).
    2. Otherwise fall back to the most-recent bar date that is <= target_date
       across all series, return (that date, False).

    This prevents the off-by-one blank-out when the pipeline runs before the
    US-close step has committed the current-date bar: we surface the latest
    available overnight move (T-1) rather than returning null for everything.
    """
    ts_target = pd.Timestamp(target_date)
    # Check exact match first
    for s in adr_series_map.values():
        if s is not None and ts_target in s.index:
            return target_date, True
    # Fallback: latest available date <= target_date
    best: date | None = None
    for s in adr_series_map.values():
        if s is None or len(s) == 0:
            continue
        valid = s.index[s.index <= ts_target]
        if len(valid) == 0:
            continue
        candidate = valid.max().date()
        if best is None or candidate > best:
            best = candidate
    if best is not None:
        return best, False
    return target_date, False  # no data at all — caller handles None gaps


def _freshness_badge(series: pd.Series | None, expected: date) -> dict:
    """Staleness badge for an ADR series."""
    if series is None or len(series) == 0:
        return {"asof": None, "lag_days": None, "state": "dead"}
    asof = series.index.max().date()
    lag = max((expected - asof).days, 0)
    if lag <= 2:
        state = "fresh"
    elif lag <= 4:
        state = "slow"
    else:
        state = "stale"
    return {"asof": str(asof), "lag_days": lag, "state": state}


# ---------------------------------------------------------------------------
# Public API: snapshot
# ---------------------------------------------------------------------------

def snapshot(
    hk_session_date: date | None = None,
    data_root: Path | None = None,
    now: datetime | None = None,
) -> dict:
    """Compute the ADR bridge snapshot for a given HK session date.

    If `hk_session_date` is None, uses the most recently completed HK session.
    The ADR date used = hk_session_date (same calendar date; the US session that
    closes AFTER the HK close on that date, implying the NEXT HK session's open).

    Returns a dict with keys:
        display_only: True (always)
        hk_session_date: str — the HK session whose NEXT open is implied
        adr_date: str — the US trading date used
        expected_hk_session: str — from hk_calendar
        freshness_verdict: str — ok | degraded | stale
        names: list[dict] — per-bellwether implied-open
        composite: dict — group composite
        banner: dict | None — bilingual banner when degraded/stale
    """
    if now is None:
        now = datetime.now(timezone.utc)
    if data_root is None:
        data_root = config.data_dir()

    try:
        expected = expected_last_session(now)
    except Exception as e:  # noqa: BLE001
        log.error("hk_adr_bridge: calendar lookup failed: %s", e)
        expected = now.date()

    if hk_session_date is None:
        hk_session_date = expected

    # The US calendar date is the same calendar date as the HK session date.
    # HK closes at 08:00 UTC; US closes at ~20:00-21:00 UTC on the same date.
    # So the US close on `hk_session_date` is AFTER the HK close and BEFORE the
    # next HK open (01:30 UTC next calendar day) → implies next HK session's open.
    #
    # Off-by-one fix (2026-07-08): When the nightly pipeline runs at ~08:30 UTC on
    # date T+1, hk_session_date resolves to T (the completed HK session on T).  The
    # ADR data store contains the US close for T (written overnight by the US-close
    # step).  Requiring adr_date == hk_session_date is correct in that case.
    #
    # However, if the pipeline runs during the US trading session or before the US
    # close has been committed, the ADR store's latest bar is T-1, not T — causing
    # ALL bellwethers to show "ADR implied —" even though data is fresh (just one
    # session behind).  Fix: fall back to the most-recent ADR bar date that is <=
    # hk_session_date when the exact session-date bar is absent, so we always surface
    # the latest available overnight move rather than returning null.
    adr_date: date = hk_session_date

    # Load all ADR series we need (de-duped tickers)
    all_adr_tickers: set[str] = set()
    for pair in ALL_PAIRS:
        all_adr_tickers.add(pair.adr_ticker)

    adr_series: dict[str, pd.Series | None] = {}
    for ticker in all_adr_tickers:
        adr_series[ticker] = _load_adr(ticker, data_root)

    # Off-by-one fix: resolve the best available ADR date.  If the exact
    # hk_session_date bar exists in any series, use it (normal path).  Otherwise
    # fall back to the most-recent available bar date <= hk_session_date so we
    # always surface the latest overnight move rather than returning blanks.
    adr_date, _adr_date_exact = _best_adr_date(adr_series, hk_session_date)
    if not _adr_date_exact and adr_date != hk_session_date:
        log.info(
            "hk_adr_bridge: exact ADR bar for %s not found; using most-recent "
            "available date %s (off-by-one fallback — pipeline ran before US close "
            "was committed)", hk_session_date, adr_date
        )

    # Freshness: each ADR is fresh relative to the expected NYSE close
    # (we use the same lag thresholds as hk_freshness but against the ADR date)
    adr_freshness: dict[str, dict] = {
        ticker: _freshness_badge(s, expected)
        for ticker, s in adr_series.items()
    }

    # Per-name computation
    names: list[dict] = []
    all_direct_gaps: list[float] = []
    all_proxy_gaps: list[float] = []

    for pair in ALL_PAIRS:
        adr_s = adr_series.get(pair.adr_ticker)
        adr_pct = None
        missing_reason = None

        if adr_s is None:
            missing_reason = f"ADR {pair.adr_ticker} data unavailable"
        else:
            try:
                adr_pct = _adr_pct_on_date(adr_s, adr_date)
            except Exception as e:  # noqa: BLE001
                log.warning("hk_adr_bridge: pct calc failed for %s/%s: %s",
                            pair.hk_ticker, pair.adr_ticker, e)
            if adr_pct is None and missing_reason is None:
                missing_reason = f"ADR {pair.adr_ticker} bar missing for {adr_date}"

        # Disconnect flag: HK move AT/BEFORE adr_date vs ADR move on adr_date.
        # Use the HK bar at or before adr_date so historical snapshots compare
        # apples-to-apples (not latest-HK vs past-ADR, which would be a look-ahead
        # for any hk_session_date != today).
        disconnect_flag = False
        hk_last_pct: float | None = None
        try:
            hk_s = _load_hk(pair.hk_ticker, data_root)
            if hk_s is not None and len(hk_s) >= 2:
                adr_ts = pd.Timestamp(adr_date)
                # Find the HK bar at or before adr_date
                idx = hk_s.index
                valid = idx[idx <= adr_ts]
                if len(valid) >= 2:
                    curr_val = float(hk_s[valid[-1]])
                    prev_val = float(hk_s[valid[-2]])
                    if prev_val > 0:
                        hk_last_pct = (curr_val / prev_val - 1.0) * 100.0
                        if adr_pct is not None:
                            disconnect_flag = (hk_last_pct * adr_pct < 0)  # opposite signs
        except Exception as e:  # noqa: BLE001
            log.debug("hk_adr_bridge: HK last pct failed for %s: %s", pair.hk_ticker, e)

        entry: dict = {
            "hk_ticker": pair.hk_ticker,
            "hk_name_en": pair.hk_name_en,
            "hk_name_zh": pair.hk_name_zh,
            "adr_ticker": pair.adr_ticker,
            "adr_source": pair.adr_source,
            "proxy_note": pair.proxy_note,
            "implied_open_gap_pct": round(adr_pct, 2) if adr_pct is not None else None,
            "adr_move_pct": round(adr_pct, 2) if adr_pct is not None else None,
            "hk_last_move_pct": round(hk_last_pct, 2) if hk_last_pct is not None else None,
            "gap_context": _gap_context(adr_pct),
            "disconnect_flag": disconnect_flag,
            "missing_reason": missing_reason,
            "freshness": adr_freshness.get(pair.adr_ticker, {}),
        }
        names.append(entry)

        if adr_pct is not None:
            if pair.adr_source == "direct":
                all_direct_gaps.append(adr_pct)
            else:
                all_proxy_gaps.append(adr_pct)

    # Group composite: equal-weight average of direct pairs if available,
    # else fallback to proxy ETF average
    composite_pct: float | None = None
    composite_source: str = "none"
    if all_direct_gaps:
        composite_pct = round(sum(all_direct_gaps) / len(all_direct_gaps), 2)
        composite_source = "direct_average"
    elif all_proxy_gaps:
        composite_pct = round(sum(all_proxy_gaps) / len(all_proxy_gaps), 2)
        composite_source = "proxy_average"

    # ETF sub-composite (KWEB + FXI)
    etf_gaps: list[float] = []
    for ticker in _ETF_TICKERS:
        s = adr_series.get(ticker)
        if s is not None:
            pct = _adr_pct_on_date(s, adr_date)
            if pct is not None:
                etf_gaps.append(pct)
    etf_composite = round(sum(etf_gaps) / len(etf_gaps), 2) if etf_gaps else None

    composite = {
        "bellwether_implied_open_pct": composite_pct,
        "gap_context": _gap_context(composite_pct),
        "composite_source": composite_source,
        "n_direct": len(all_direct_gaps),
        "n_proxy": len(all_proxy_gaps),
        "etf_composite_pct": etf_composite,
        "etf_gap_context": _gap_context(etf_composite),
    }

    # Freshness verdict
    all_badges = list(adr_freshness.values())
    n_stale = sum(1 for b in all_badges if b["state"] in ("stale", "dead"))
    n_slow   = sum(1 for b in all_badges if b["state"] == "slow")
    if n_stale >= 2:
        freshness_verdict = "stale"
    elif n_stale == 1 or n_slow >= 2:
        freshness_verdict = "degraded"
    else:
        freshness_verdict = "ok"

    # Banner (bilingual) — only when degraded/stale
    banner = None
    if freshness_verdict in ("stale", "degraded"):
        stale_tickers = [t for t, b in adr_freshness.items()
                         if b["state"] in ("stale", "dead")]
        lag_parts = [f"{t}:{adr_freshness[t].get('lag_days', '?')}d"
                     for t in stale_tickers]
        lag_str = ", ".join(lag_parts) if lag_parts else "unknown"
        banner = {
            "en": (f"ADR bridge data {freshness_verdict} — "
                   f"stale: {lag_str}; implied gaps may be outdated"),
            "zh": (f"ADR 桥数据{freshness_verdict} — "
                   f"落后：{lag_str}；隐含跳空可能已过时"),
        }

    return {
        "display_only": True,
        "hk_session_date": str(hk_session_date),
        "adr_date": str(adr_date),
        "expected_hk_session": str(expected),
        "freshness_verdict": freshness_verdict,
        "adr_freshness": {t: b for t, b in adr_freshness.items()},
        "names": names,
        "composite": composite,
        "banner": banner,
        "note": ("context, not a signal / 参考，非买卖信号"),
    }


# ---------------------------------------------------------------------------
# Ledger: forward-grading for accrual
# ---------------------------------------------------------------------------

_LEDGER_DIR_REL = "hk_impulse"
_LEDGER_FILE    = "adr_bridge_ledger.jsonl"
_ORGAN_ID       = "hk_adr_bridge"


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
    """Write ledger atomically via temp-file + os.replace to avoid truncation on crash."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else "")
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".ledger_tmp_")
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


def _fire_id(hk_session_date: str, name: str) -> str:
    return f"{_ORGAN_ID}:{hk_session_date}:{name}"


def stamp(snap: dict, data_root: Path | None = None) -> int:
    """Append one row per (hk_session, name) for fires in this snapshot.
    Idempotent on fire_id. Returns number of rows appended. Never raises.

    Only executes the ledger append when _ledger_advance_enabled() is True
    (CN_LANE=asia env var, set by asia-close.yml only). The snapshot/display
    JSON may be produced in any lane; this guard keeps weekly.yml from
    accidentally appending duplicate ledger rows (house law: nightly sole advancer).
    """
    if not _ledger_advance_enabled():
        log.debug("hk_adr_bridge.stamp: ledger advance skipped (CN_LANE != asia)")
        return 0
    try:
        hk_session_date = snap.get("hk_session_date", "")
        adr_date = snap.get("adr_date", "")
        freshness_info = snap.get("adr_freshness", {})

        rows = load_ledger(data_root)
        existing_ids = {r.get("fire_id") for r in rows}

        appended = 0
        for entry in snap.get("names", []):
            name = entry.get("hk_ticker", "")
            fid = _fire_id(hk_session_date, name)
            if fid in existing_ids:
                continue  # idempotent: already stamped for this session+name

            # Only stamp if we have an actual gap value (not None)
            if entry.get("implied_open_gap_pct") is None:
                continue

            # Episode ID: daily sequence number (count of distinct hk_session_date)
            prior_sessions = {r.get("hk_session_date") for r in rows}
            prior_sessions.add(hk_session_date)
            episode_id = len(prior_sessions)

            adr_ticker = entry.get("adr_ticker", "")
            row = {
                "fire_id": fid,
                "organ": _ORGAN_ID,
                "hk_session_date": hk_session_date,
                "adr_date": adr_date,
                "name": name,
                "name_en": entry.get("hk_name_en", ""),
                "name_zh": entry.get("hk_name_zh", ""),
                "adr_ticker": adr_ticker,
                "adr_source": entry.get("adr_source", ""),
                "implied_open_gap_pct": entry.get("implied_open_gap_pct"),
                "adr_move_pct": entry.get("adr_move_pct"),
                "gap_context": entry.get("gap_context", "unknown"),
                "disconnect_flag": entry.get("disconnect_flag", False),
                "asof_freshness": freshness_info.get(adr_ticker, {}),
                "episode_id": episode_id,
                # Grade fields — filled later by grade()
                "actual_open_gap_pct": None,   # actual T+1 HK open vs prev close
                "followed": None,              # True = gap followed, False = faded
                "graded_at": None,
            }
            rows.append(row)
            existing_ids.add(fid)
            appended += 1

        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001 — ledger is additive, never fatal
        log.warning("hk_adr_bridge ledger stamp failed: %s", e)
        return 0


def grade(data_root: Path | None = None) -> dict:
    """Fill actual_open_gap_pct + followed for rows whose T+1 HK open is now available.

    For HK session date T, the actual open of T+1 is HK stock open on the NEXT session.
    followed = True when sign(actual_open_gap) == sign(implied_open_gap).
    Never raises.

    Like stamp(), only writes to the ledger in the asia-close lane (CN_LANE=asia).
    """
    if not _ledger_advance_enabled():
        log.debug("hk_adr_bridge.grade: ledger advance skipped (CN_LANE != asia)")
        return {"ok": True, "graded": 0, "note": "ledger advance disabled (not asia-close lane)"}
    try:
        rows = load_ledger(data_root)
        if not rows:
            return {"ok": True, "graded": 0, "note": "no rows"}

        if data_root is None:
            data_root = config.data_dir()

        # Load HK close series for all tickers we need
        hk_cache: dict[str, pd.Series | None] = {}
        tickers_needed = {r["name"] for r in rows if r.get("actual_open_gap_pct") is None}
        for ticker in tickers_needed:
            # We need OPEN prices for T+1; fall back to close series if open not available
            try:
                p = data_root / "hk_stocks" / f"{ticker}.parquet"
                if not p.exists():
                    hk_cache[ticker] = None
                    continue
                df = pd.read_parquet(p)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).normalize()
                df = df.sort_index()
                # Use open if available, else close as best approximation
                if "open" in df.columns:
                    hk_cache[ticker] = df["open"].dropna()
                elif "close" in df.columns:
                    hk_cache[ticker] = df["close"].dropna()
                else:
                    hk_cache[ticker] = None
            except Exception as e:  # noqa: BLE001
                log.debug("hk_adr_bridge grade: failed to load %s: %s", ticker, e)
                hk_cache[ticker] = None

        # Also need HK close for the prior session (denominator for actual gap)
        hk_close_cache: dict[str, pd.Series | None] = {}
        for ticker in tickers_needed:
            try:
                p = data_root / "hk_stocks" / f"{ticker}.parquet"
                if not p.exists():
                    hk_close_cache[ticker] = None
                    continue
                df = pd.read_parquet(p)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.index = pd.to_datetime(df.index).normalize()
                df = df.sort_index()
                if "close" in df.columns:
                    hk_close_cache[ticker] = df["close"].dropna()
                else:
                    hk_close_cache[ticker] = None
            except Exception as e:  # noqa: BLE001
                log.debug("hk_adr_bridge grade: close load failed %s: %s", ticker, e)
                hk_close_cache[ticker] = None

        graded = 0
        for r in rows:
            try:
                if r.get("actual_open_gap_pct") is not None:
                    continue  # already graded
                hk_session_date = pd.Timestamp(r["hk_session_date"])
                ticker = r["name"]

                # Find next HK session date
                next_date = hk_session_date.date() + timedelta(days=1)
                for _ in range(10):
                    if is_session(next_date):
                        break
                    next_date += timedelta(days=1)
                else:
                    continue  # couldn't find next session

                next_ts = pd.Timestamp(next_date)
                open_s = hk_cache.get(ticker)
                close_s = hk_close_cache.get(ticker)

                if open_s is None or close_s is None:
                    continue

                # Actual gap = open(T+1) / close(T) - 1
                if next_ts not in open_s.index:
                    continue
                if hk_session_date not in close_s.index:
                    continue

                prev_close = float(close_s[hk_session_date])
                next_open = float(open_s[next_ts])

                if prev_close <= 0:
                    continue

                actual_gap = (next_open / prev_close - 1.0) * 100.0
                implied_gap = r.get("implied_open_gap_pct")
                followed = None
                if implied_gap is not None and actual_gap is not None:
                    # followed = True when same sign (both positive, or both negative)
                    followed = bool(implied_gap * actual_gap > 0)

                r["actual_open_gap_pct"] = round(actual_gap, 2)
                r["followed"] = followed
                r["graded_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                graded += 1
            except Exception as e:  # noqa: BLE001
                log.debug("hk_adr_bridge grade row failed: %s", e)
                continue

        if graded:
            _write_ledger(rows, data_root)

        n_graded_total = sum(1 for r in rows if r.get("actual_open_gap_pct") is not None)
        n_followed = sum(1 for r in rows
                         if r.get("followed") is True)
        follow_rate = (round(n_followed / n_graded_total, 3)
                       if n_graded_total else None)

        return {
            "ok": True,
            "graded_this_run": graded,
            "n_rows_total": len(rows),
            "n_graded_total": n_graded_total,
            "follow_rate": follow_rate,
            "note": ("Live follow-rate (actual T+1 HK open vs implied ADR gap). "
                     "Accruing — thin until 20+ fires. Grade step is display-only context "
                     "accounting; not a promoted signal."),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def run(data_root: Path | None = None,
        now: datetime | None = None) -> dict:
    """One-shot: compute snapshot, stamp ledger, grade matured rows.
    Returns the snapshot dict. Never raises."""
    try:
        snap = snapshot(data_root=data_root, now=now)
        stamp(snap, data_root=data_root)
        grade(data_root=data_root)
        return snap
    except Exception as e:  # noqa: BLE001
        log.error("hk_adr_bridge.run crashed: %s", e)
        return {
            "display_only": True,
            "error": str(e),
            "freshness_verdict": "degraded",
            "names": [],
            "composite": {},
            "banner": {
                "en": "ADR bridge engine error — context unavailable",
                "zh": "ADR 桥引擎错误 — 参考上下文不可用",
            },
        }
