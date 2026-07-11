"""scripts/build_flow_leaders.py — Flow Leaders Desk nightly builder (FL W2).

Inputs (all absent-safe — honest nulls on miss):
  data/options_flow/summary_*.parquet      soft-spine: gross premium, net_premium_mn,
                                            zerodte_share, fresh_contracts
  data/tape_flow/daily/<ROOT>.parquet      tape-spine per name when present
  data/polygon_gex/chains/<date>.parquet   OI-confirmation (2 most-recent chain days)
  data/options_entry/state.parquet         gamma_regime per name
  site/stockdata/<T>.json                  tech/rs/high52w/rel_volume/obv/earnings/profile/valuation
  site/factordata/stock_personality.json   failed_breakout_trap, stair_step_leader
  site/stockdata/mtf_upturn.json           mtf_upturn state per ticker
  site/flowtracker/base.json               washout context (preferred); fallback computed

Outputs:
  site/flowleaders/leaders.json            schema flow_leaders.v1
  site/flow_leaders.html                   rendered from templates/flow_leaders.html.j2

Kill-switch: config flow_leaders.enabled: false → noindex stub, skip JSON.
Freshness SLA (FL-R15): flow store latest lag > 2 NYSE sessions → stale=true.
Data writes: COLLECT_LANE=nightly gate only.
Fail-soft: per-ticker exceptions are logged and skipped; always exits 0.
"""
from __future__ import annotations

import glob
import json
import logging
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader
from lib import config

log = logging.getLogger(__name__)

# ── ETFs excluded from boards A/B (routed to etf_strip) ──────────────────────
_ETF_SET = frozenset({
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "KRE", "XBI", "ARKK",
})

# ── COLLECT_LANE gate ─────────────────────────────────────────────────────────

def _nightly_lane() -> bool:
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


# ── Kill-switch stub ──────────────────────────────────────────────────────────

def _write_noindex_stub(site_root: Path) -> None:
    stub = (
        '<!DOCTYPE html><html lang="en"><head>'
        '<meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Flow Leaders (disabled)</title></head>'
        '<body><p>Flow Leaders is currently disabled.</p></body></html>'
    )
    (site_root / "flow_leaders.html").write_text(stub)
    log.info("build_flow_leaders: kill-switch active — wrote noindex stub")


# ── JSON serialiser ───────────────────────────────────────────────────────────

def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if not np.isfinite(float(obj)) else float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    # Handle pandas NA and NAType (pandas 1.0+ nullable integer/boolean NA)
    if obj is pd.NA or (hasattr(pd, "NaT") and obj is pd.NaT):
        return None
    try:
        # Catch pandas nullable scalar types (Int64, boolean, etc.)
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


# ── Summary parquet loaders ───────────────────────────────────────────────────

def _load_all_summaries(data_root: Path) -> dict[str, pd.DataFrame]:
    """Load data/options_flow/summary_<TICKER>.parquet for all tickers.

    Returns {ticker: DataFrame(date-indexed, ascending)}.
    """
    result: dict[str, pd.DataFrame] = {}
    pattern = str(data_root / "options_flow" / "summary_*.parquet")
    for path in sorted(glob.glob(pattern)):
        name = Path(path).stem[len("summary_"):]
        try:
            df = pd.read_parquet(path).sort_index()
            result[name] = df
        except Exception as e:  # noqa: BLE001
            log.debug("build_flow_leaders: summary %s unreadable: %s", name, e)
    return result


def _latest_summary_session(summaries: dict[str, pd.DataFrame]) -> str | None:
    """Return the latest session date string across all summaries, or None."""
    latest: str | None = None
    for df in summaries.values():
        if df.empty:
            continue
        idx = df.index[-1]
        s = str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
        if latest is None or s > latest:
            latest = s
    return latest


# ── Freshness SLA (FL-R15) ────────────────────────────────────────────────────

def _check_stale(latest_session: str | None) -> bool:
    """Return True when flow store lags the NYSE calendar by > 2 sessions."""
    if latest_session is None:
        return True
    try:
        from lib.nyse_calendar import trading_dates_between
        today = date.today()
        # Get recent NYSE sessions (last 10); count how many strictly after latest_session
        recent = trading_dates_between(
            date(today.year - 1, today.month, today.day),
            today,
        )
        after = [d for d in recent if str(d) > latest_session and d <= today]
        return len(after) > 2
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: stale check failed: %s", e)
        return False


# ── Tape flow loaders ─────────────────────────────────────────────────────────

def _load_tape_row(ticker: str, data_root: Path) -> pd.Series | None:
    """Load latest tape_flow daily row for a ticker. None if absent."""
    p = data_root / "tape_flow" / "daily" / f"{ticker}.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p).sort_index()
        if df.empty:
            return None
        return df.iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: tape_flow/%s unreadable: %s", ticker, e)
        return None


def _tape_ex0dte_net(tape_row: pd.Series | None) -> float | None:
    """Extract ex-0DTE net premium from tape DTE buckets (sum of ≥1d buckets)."""
    if tape_row is None:
        return None
    buckets = ["dte_1_7d", "dte_8_30d", "dte_31_90d", "dte_90p"]
    total = 0.0
    found = False
    for col in buckets:
        v = tape_row.get(col) if hasattr(tape_row, "get") else getattr(tape_row, col, None)
        if v is not None and not pd.isna(v):
            total += float(v)
            found = True
    return total if found else None


# ── Polygon GEX chain loaders ─────────────────────────────────────────────────

def _load_two_chain_days(data_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (chain_day_t, chain_day_t1) — the 2 most recent chain parquets.

    chain_day_t  = older of the two (flow day d)
    chain_day_t1 = newer (next day d+1 for OI confirmation)
    Returns (empty, empty) when fewer than 2 chain files exist.
    """
    pattern = str(data_root / "polygon_gex" / "chains" / "*.parquet")
    paths = sorted(glob.glob(pattern))
    if len(paths) < 2:
        return pd.DataFrame(), pd.DataFrame()
    try:
        d_t = pd.read_parquet(paths[-2])
        d_t1 = pd.read_parquet(paths[-1])
        return d_t, d_t1
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: chain load failed: %s", e)
        return pd.DataFrame(), pd.DataFrame()


# ── Options entry state ───────────────────────────────────────────────────────

def _load_options_entry(data_root: Path) -> dict[str, str | None]:
    """Return {ticker: gamma_regime} from data/options_entry/state.parquet."""
    p = data_root / "options_entry" / "state.parquet"
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
        if "ticker" not in df.columns or "gamma_regime" not in df.columns:
            return {}
        return dict(zip(df["ticker"].astype(str), df["gamma_regime"].astype(object)))
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: options_entry/state.parquet unreadable: %s", e)
        return {}


# ── Stockdata context ─────────────────────────────────────────────────────────

def _load_stockdata(ticker: str, site_root: Path) -> dict:
    p = site_root / "stockdata" / f"{ticker}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: stockdata/%s unreadable: %s", ticker, e)
        return {}


def _extract_stock_context(sd: dict, ticker: str) -> dict:
    """Pull required fields from stockdata JSON — graceful null on miss."""
    ctx: dict[str, Any] = {}

    tech = sd.get("tech") or {}
    trend = tech.get("trend") or {}

    # ribbon_up: ribbon state — True when moving avg stack is bullish
    ribbon_raw = trend.get("ribbon") or trend.get("ribbon_state")
    if isinstance(ribbon_raw, str):
        ctx["ribbon_up"] = ribbon_raw.lower() in ("bullish", "up", "above")
    elif isinstance(ribbon_raw, bool):
        ctx["ribbon_up"] = ribbon_raw
    else:
        ctx["ribbon_up"] = None

    # rs_1m
    rs = tech.get("rs") or {}
    rs_1m = rs.get("rs_1m")
    ctx["rs_1m"] = float(rs_1m) if rs_1m is not None and not pd.isna(rs_1m) else None

    # high52w_prox
    ctx["high52w_prox"] = _safe_float(tech, "high52w_prox")

    # rel_volume
    ctx["rel_volume"] = _safe_float(tech, "rel_volume")

    # obv_slope_up
    obv = tech.get("obv_slope") or tech.get("obv")
    if isinstance(obv, str):
        ctx["obv_slope_up"] = obv.lower() in ("up", "positive", "rising")
    elif isinstance(obv, (int, float)):
        ctx["obv_slope_up"] = bool(obv > 0)
    else:
        ctx["obv_slope_up"] = None

    # mktcap_bn
    profile = sd.get("profile") or {}
    mktcap = profile.get("mktcap_bn") or profile.get("market_cap_bn")
    ctx["mktcap_bn"] = float(mktcap) if mktcap is not None and not pd.isna(mktcap) else None

    # earnings.next_date → days_to_earnings
    earnings = sd.get("earnings") or {}
    next_date = earnings.get("next_date")
    if next_date:
        try:
            nd = pd.Timestamp(next_date).date()
            ctx["days_to_earnings"] = (nd - date.today()).days
        except Exception:  # noqa: BLE001
            ctx["days_to_earnings"] = None
    else:
        ctx["days_to_earnings"] = None

    # trailing_pe from valuation
    val = sd.get("valuation") or {}
    pe = val.get("trailing_pe") or val.get("pe_ttm")
    ctx["trailing_pe"] = float(pe) if pe is not None and not pd.isna(pe) else None

    return ctx


def _safe_float(d: dict, key: str) -> float | None:
    v = d.get(key)
    if v is None:
        return None
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


# ── Stock personality loader ──────────────────────────────────────────────────

def _load_personality(site_root: Path) -> dict[str, dict]:
    """Load site/factordata/stock_personality.json → {ticker: {...}}."""
    p = site_root / "factordata" / "stock_personality.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        tickers = d.get("tickers") or {}
        return {t: v for t, v in tickers.items() if isinstance(v, dict)}
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: stock_personality.json unreadable: %s", e)
        return {}


def _personality_flags(pers_rec: dict | None) -> tuple[bool | None, bool | None]:
    """Return (failed_breakout_trap, stair_step_leader) from a personality record."""
    if not pers_rec:
        return None, None
    labels = []
    # labels may be nested under base.chart_personality.labels
    base = pers_rec.get("base") or {}
    cp = base.get("chart_personality") or pers_rec.get("chart_personality") or {}
    labels = cp.get("labels") or []
    if not labels:
        return None, None
    fbt = "failed_breakout_trap" in labels
    ssl = "stair_step_leader" in labels
    return bool(fbt), bool(ssl)


# ── MTF Upturn loader ─────────────────────────────────────────────────────────

def _load_mtf_upturn(site_root: Path) -> dict[str, dict]:
    """Load site/stockdata/mtf_upturn.json → {ticker: {state, K, ...}}."""
    p = site_root / "stockdata" / "mtf_upturn.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        return d.get("tickers") or {}
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: mtf_upturn.json unreadable: %s", e)
        return {}


# ── Washout context loader ────────────────────────────────────────────────────

def _load_washout_ctx(site_root: Path) -> dict[str, dict]:
    """Load site/flowtracker/base.json and extract washout context per ticker."""
    p = site_root / "flowtracker" / "base.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
        leaders = d.get("leaders") or []
        out: dict[str, dict] = {}
        for rec in leaders:
            t = rec.get("ticker")
            if not t:
                continue
            out[t] = {
                "bb_lower_reclaim_days": rec.get("bb_lower_reclaim_days"),
                "drawdown_21d_pct":      rec.get("drawdown_21d_pct"),
                "recovery_begun":        rec.get("recovery_begun"),
            }
        return out
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: flowtracker/base.json unreadable: %s", e)
        return {}


# ── Weekly StochRSI (B2 contract) ─────────────────────────────────────────────

def _weekly_stochrsi_k_min3(ticker: str, data_root: Path, site_root: Path) -> float | None:
    """Min(StochRSI K over last 3 completed weekly bars).

    Load price from data/stocks/<T>.parquet or site/ohlc/<T>.json.
    Compute weekly closes, then per the engine.signal_quality._stoch_rsi_kd path.
    """
    # load daily closes
    series = _load_daily_close(ticker, data_root, site_root)
    if series is None or len(series) < 30:
        return None
    try:
        from engine.signal_quality import _stoch_rsi_kd  # type: ignore[attr-defined]
        # resample to weekly (FRI) — completed weeks only
        weekly = series.resample("W-FRI").last().dropna()
        if len(weekly) < 20:
            return None
        k_series, _ = _stoch_rsi_kd(weekly)
        k_clean = k_series.dropna()
        if len(k_clean) < 3:
            return None
        return float(k_clean.iloc[-3:].min())
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: weekly stochrsi for %s failed: %s", ticker, e)
        return None


def _load_daily_close(ticker: str, data_root: Path, site_root: Path) -> pd.Series | None:
    """Load daily close series from parquet or ohlc json. Returns ascending Series."""
    parq = data_root / "stocks" / f"{ticker}.parquet"
    if parq.exists():
        try:
            df = pd.read_parquet(parq)
            if "close" in df.columns:
                s = pd.to_numeric(df["close"], errors="coerce").dropna().sort_index()
                if len(s) >= 20:
                    return s
        except Exception:  # noqa: BLE001
            pass
    ohlc = site_root / "ohlc" / f"{ticker}.json"
    if ohlc.exists():
        try:
            raw = json.loads(ohlc.read_text())
            if isinstance(raw, list):
                df = pd.DataFrame(raw)
                c_col = "close" if "close" in df.columns else ("c" if "c" in df.columns else None)
                d_col = "date" if "date" in df.columns else None
                if c_col and d_col:
                    df[d_col] = pd.to_datetime(df[d_col], errors="coerce")
                    df = df.set_index(d_col).sort_index()
                    s = pd.to_numeric(df[c_col], errors="coerce").dropna()
                    if len(s) >= 20:
                        return s
            elif isinstance(raw, dict) and "c" in raw:
                dates = raw.get("dates") or raw.get("t") or []
                s = pd.Series(
                    pd.to_numeric(raw["c"], errors="coerce"),
                    index=pd.to_datetime(dates, errors="coerce"),
                ).dropna().sort_index()
                if len(s) >= 20:
                    return s
        except Exception:  # noqa: BLE001
            pass
    return None


# ── 2W oscillator helpers (uses engine/htf_oscillators.py) ───────────────────

def _load_2w_fields(ticker: str, data_root: Path, site_root: Path) -> dict:
    """Return 2W StochRSI and MACD-ETA for display context (FL-R7)."""
    null = {
        "stochrsi_2w_k": None,
        "stochrsi_2w_d": None,
        "stochrsi_2w_oversold": None,
        "macd_2w_state": None,
        "macd_2w_bars_to_cross": None,
        "macd_2w_bars_since": None,
        "htf_coverage": False,
    }
    series = _load_daily_close(ticker, data_root, site_root)
    if series is None:
        return null
    try:
        from engine.htf_oscillators import stochrsi_2w, macd_bars_to_cross_2w
        sr = stochrsi_2w(series)
        mc = macd_bars_to_cross_2w(series)
        return {
            "stochrsi_2w_k":        sr.get("k"),
            "stochrsi_2w_d":        sr.get("d"),
            "stochrsi_2w_oversold": sr.get("oversold"),
            "macd_2w_state":        mc.get("state"),
            "macd_2w_bars_to_cross": mc.get("bars_to_cross"),
            "macd_2w_bars_since":   mc.get("bars_since"),
            "htf_coverage":         sr.get("htf_coverage", False) or mc.get("htf_coverage", False),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("build_flow_leaders: 2w fields for %s failed: %s", ticker, e)
        return null


# ── Membership history builder ────────────────────────────────────────────────

def _build_membership_df(
    summaries: dict[str, pd.DataFrame],
    mktcap_map: dict[str, float],
    tape_rows: dict[str, pd.Series | None],
) -> pd.DataFrame:
    """Rebuild trailing membership table from summary parquets.

    Returns DataFrame with columns: session, ticker, in_top20, zerodte_excluded,
    net_prem_norm, net_premium_mn.
    """
    from engine.flow_leaders import normalized_impact_table

    rows: list[dict] = []
    sessions = sorted({
        str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
        for df in summaries.values()
        for idx in df.index
    })

    for session_str in sessions:
        # build per-session rows
        day_rows_list: list[dict] = []
        for ticker, df in summaries.items():
            # find row for this session
            try:
                ts = pd.Timestamp(session_str)
                if ts not in df.index:
                    continue
                row = df.loc[ts]
            except Exception:  # noqa: BLE001
                continue

            def _get(r, k):
                v = r.get(k) if hasattr(r, "get") else getattr(r, k, None)
                return None if (v is not None and isinstance(v, float) and pd.isna(v)) else v

            day_rows_list.append({
                "ticker": ticker,
                "net_premium_mn": _get(row, "net_premium_mn"),
                "premium_mn": _get(row, "premium_mn") or _get(row, "gross_premium_mn"),
                "zerodte_share": _get(row, "zerodte_share"),
                "signing_source": "minute_tick",
            })

        if not day_rows_list:
            continue

        day_df = pd.DataFrame(day_rows_list)

        # tape ex-0DTE overrides where available
        ex0dte: dict[str, float] = {}
        for ticker in day_df["ticker"].unique():
            tape_row = tape_rows.get(ticker)
            v = _tape_ex0dte_net(tape_row)
            if v is not None:
                ex0dte[ticker] = v

        try:
            enriched = normalized_impact_table(day_df, mktcap_map, ex0dte or None)
        except Exception as e:  # noqa: BLE001
            log.debug("build_flow_leaders: normalized_impact_table failed for %s: %s", session_str, e)
            continue

        for _, r in enriched.iterrows():
            rows.append({
                "session": session_str,
                "ticker": r["ticker"],
                "in_top20": bool(r.get("in_top20", False)),
                "zerodte_excluded": bool(r.get("zerodte_excluded", False)),
                "net_prem_norm": r.get("net_prem_norm"),
                "net_premium_mn": r.get("net_premium_mn"),
            })

    if not rows:
        return pd.DataFrame(columns=["session", "ticker", "in_top20", "zerodte_excluded",
                                      "net_prem_norm", "net_premium_mn"])
    return pd.DataFrame(rows)


# ── Per-ticker record builder ─────────────────────────────────────────────────

def _build_ticker_record(
    ticker: str,
    is_etf: bool,
    summaries: dict[str, pd.DataFrame],
    membership_df: pd.DataFrame,
    oi_confirmed_map: dict[str, bool | None],
    tape_rows: dict[str, pd.Series | None],
    options_entry_map: dict[str, str | None],
    personality_map: dict[str, dict],
    mtf_upturn_map: dict[str, dict],
    washout_ctx_map: dict[str, dict],
    data_root: Path,
    site_root: Path,
    as_of: str,
    stale: bool,
) -> dict:
    """Build the full per-ticker record for leaders.json."""
    from engine.flow_leaders import (
        recurrence_count,
        flow_recur_leg,
        flow_z,
        ts_breadth as _ts_breadth,
        flow_inflect as _flow_inflect,
        board_a_legs,
        board_b_legs,
        board_a_fire,
        board_b_fire,
        earnings_window as _earnings_window,
        vol_trade_flag,
        protective_put_flag,
        gamma_caution as _gamma_caution,
        UPTURN_WATCH_STATE,
    )

    summary_df = summaries.get(ticker)
    tape_row = tape_rows.get(ticker)

    # signing_source
    signing_source = "tape" if tape_row is not None else "minute_tick"

    # Flow history series (gross premium for z-score; net for inflection)
    gross_hist: pd.Series = pd.Series(dtype=float)
    net_hist: pd.Series = pd.Series(dtype=float)
    if summary_df is not None and not summary_df.empty:
        for col in ("premium_mn", "gross_premium_mn"):
            if col in summary_df.columns:
                gross_hist = summary_df[col].dropna().astype(float)
                break
        if "net_premium_mn" in summary_df.columns:
            net_hist = summary_df["net_premium_mn"].dropna().astype(float)

    # Recurrence count and leg (for non-stale sessions)
    ticker_membership = (
        membership_df[membership_df["ticker"] == ticker]
        if not membership_df.empty else pd.DataFrame()
    )
    recur_count: float | None = None
    recur_leg: bool | None = None
    if not stale and not ticker_membership.empty:
        try:
            rc_series = recurrence_count(ticker_membership)
            recur_count = rc_series.get(ticker)
            rl_series = flow_recur_leg(ticker_membership)
            raw_rl = rl_series.get(ticker)
            recur_leg = None if pd.isna(raw_rl) else bool(raw_rl)
        except Exception as e:  # noqa: BLE001
            log.debug("build_flow_leaders: recurrence for %s failed: %s", ticker, e)

    # normalized net_prem absolute for tie-breaking
    net_prem_norm_abs: float | None = None
    if not ticker_membership.empty and "net_prem_norm" in ticker_membership.columns:
        last_val = ticker_membership.sort_values("session")["net_prem_norm"].dropna()
        if not last_val.empty:
            net_prem_norm_abs = abs(float(last_val.iloc[-1]))

    # Flow z-score (A2)
    fz = flow_z(gross_hist) if len(gross_hist) > 0 else None

    # OI confirmation (A3/B6)
    oi_conf = oi_confirmed_map.get(ticker)

    # ts_breadth (A4) — tape source only
    ts_brd_val = _ts_breadth(tape_row)
    ts_brd_chip = ts_brd_val  # integer count or None

    # Flow inflection (B5)
    inflect_result = _flow_inflect(net_hist) if len(net_hist) > 0 else {"inflected": None, "days_since_inflection": None}
    days_since_inflection = inflect_result.get("days_since_inflection")

    # Stockdata context
    sd = {}
    stock_ctx: dict[str, Any] = {
        "ribbon_up": None, "rs_1m": None, "high52w_prox": None,
        "rel_volume": None, "obv_slope_up": None, "mktcap_bn": None,
        "days_to_earnings": None, "trailing_pe": None,
    }
    if not is_etf:
        sd = _load_stockdata(ticker, site_root)
        stock_ctx = _extract_stock_context(sd, ticker)

    # Personality flags
    pers_rec = personality_map.get(ticker)
    failed_breakout_trap, stair_step_leader = _personality_flags(pers_rec)

    # MTF Upturn
    mtu_rec = mtf_upturn_map.get(ticker) or {}
    mtf_upturn_state = mtu_rec.get("state")

    # 2W oscillator fields (display)
    tw_fields = _load_2w_fields(ticker, data_root, site_root) if not is_etf else {
        "stochrsi_2w_k": None, "stochrsi_2w_d": None, "stochrsi_2w_oversold": None,
        "macd_2w_state": None, "macd_2w_bars_to_cross": None, "macd_2w_bars_since": None,
        "htf_coverage": False,
    }

    # B4 htf_cross_near chip: DISPLAY ONLY — apply ≤2-bar ETA gate (FL-R7 B4 note)
    htf_cross_near: bool | None = None
    mc_state = tw_fields.get("macd_2w_state")
    mc_btc = tw_fields.get("macd_2w_bars_to_cross")
    mc_bsc = tw_fields.get("macd_2w_bars_since")
    if mc_state == "crossed":
        htf_cross_near = True
    elif mc_state == "approaching" and mc_btc is not None:
        htf_cross_near = bool(mc_btc <= 2)

    # Weekly StochRSI K min over 3 bars (B2)
    weekly_stochrsi_k_min3 = _weekly_stochrsi_k_min3(ticker, data_root, site_root) if not is_etf else None

    # rsi_stack_oversold (B2 alternative — from stockdata if present)
    rsi_stack_oversold: bool | None = None
    if not is_etf:
        tech = sd.get("tech") or {}
        rsi_stack = tech.get("rsi_stack_oversold")
        if isinstance(rsi_stack, bool):
            rsi_stack_oversold = rsi_stack
        elif isinstance(rsi_stack, str):
            rsi_stack_oversold = rsi_stack.lower() == "true"

    # Washout context (B1)
    wctx = washout_ctx_map.get(ticker)

    # Gamma regime
    gamma_regime = options_entry_map.get(ticker)

    # De-escalation flags (FL-R12)
    earn_win = _earnings_window(stock_ctx.get("days_to_earnings"))
    vol_trade = vol_trade_flag(tape_row)
    prot_put = protective_put_flag(tape_row)
    gam_caut = _gamma_caution(gamma_regime)

    # 0DTE chip (FL-R4)
    zerodte_dominated: bool = False
    if summary_df is not None and not summary_df.empty and "zerodte_share" in summary_df.columns:
        from engine.flow_leaders import ZERODTE_MAX
        last_z = summary_df["zerodte_share"].dropna()
        if not last_z.empty:
            zerodte_dominated = bool(float(last_z.iloc[-1]) > ZERODTE_MAX)

    # Board A/B legs
    a_legs = board_a_legs(
        recur_leg=recur_leg,
        flow_z_val=fz,
        oi_confirmed=oi_conf,
        ts_breadth_val=ts_brd_val,
        ribbon_up=stock_ctx.get("ribbon_up"),
        rs_1m=stock_ctx.get("rs_1m"),
        high52w_prox=stock_ctx.get("high52w_prox"),
        rel_volume=stock_ctx.get("rel_volume"),
        obv_slope_up=stock_ctx.get("obv_slope_up"),
        failed_breakout_trap=failed_breakout_trap,
    )
    b_legs = board_b_legs(
        washout_ctx=wctx,
        weekly_stochrsi_k_min3=weekly_stochrsi_k_min3,
        rsi_stack_oversold=rsi_stack_oversold,
        mtf_upturn_state=mtf_upturn_state,
        htf_cross_near=htf_cross_near,
        flow_inflect_val=inflect_result,
        oi_confirmed=oi_conf,
        rel_volume=stock_ctx.get("rel_volume"),
        obv_slope_up=stock_ctx.get("obv_slope_up"),
        failed_breakout_trap=failed_breakout_trap,
    )

    fire_a = board_a_fire(a_legs)
    fire_b = board_b_fire(b_legs)

    rec: dict[str, Any] = {
        "ticker": ticker,
        "as_of": as_of,
        "signing_source": signing_source,
        "signing_note": "direction ~-soft (FL-R3)" if signing_source == "minute_tick" else "tape-signed (Lee-Ready; magnitude leads direction, FL-R3)",
        # Sort quantities
        "recurrence_count": recur_count,
        "net_prem_norm_abs": net_prem_norm_abs,
        "days_since_inflection": days_since_inflection,
        # Flow metrics
        "flow_z": fz,
        "ts_breadth_count": ts_brd_chip,
        "zerodte_dominated": zerodte_dominated,
        # OI confirmation
        "oi_confirmed": oi_conf,
        # Board A legs (tri-state)
        "A1_flow_recur": a_legs.A1_flow_recur,
        "A2_flow_z_hot": a_legs.A2_flow_z_hot,
        "A3_oi_confirmed": a_legs.A3_oi_confirmed,
        "A4_ts_breadth": a_legs.A4_ts_breadth,
        "A5_price_leader": a_legs.A5_price_leader,
        "A6_near_high": a_legs.A6_near_high,
        "A7_vol_confirm": a_legs.A7_vol_confirm,
        "A8_not_trap": a_legs.A8_not_trap,
        "K_a": a_legs.K,
        "n_avail_a": a_legs.n_avail,
        # Board B legs (tri-state)
        "B1_washout_recent": b_legs.B1_washout_recent,
        "B2_oversold_osc": b_legs.B2_oversold_osc,
        "B3_turn_organ": b_legs.B3_turn_organ,
        "B4_htf_cross_near": b_legs.B4_htf_cross_near,
        "B5_flow_inflect": b_legs.B5_flow_inflect,
        "B6_oi_confirmed": b_legs.B6_oi_confirmed,
        "B7_vol_confirm": b_legs.B7_vol_confirm,
        "B8_not_trap": b_legs.B8_not_trap,
        "K_b": b_legs.K,
        "n_avail_b": b_legs.n_avail,
        # Fire flags
        "fire_a": fire_a,
        "fire_b": fire_b,
        # Context fields
        "stair_step_leader": stair_step_leader,
        "failed_breakout_trap": failed_breakout_trap,
        "mtf_upturn_state": mtf_upturn_state,
        "gamma_regime": gamma_regime,
        "days_to_earnings": stock_ctx.get("days_to_earnings"),
        "trailing_pe": stock_ctx.get("trailing_pe"),
        "mktcap_bn": stock_ctx.get("mktcap_bn"),
        "rs_1m": stock_ctx.get("rs_1m"),
        "high52w_prox": stock_ctx.get("high52w_prox"),
        "rel_volume": stock_ctx.get("rel_volume"),
        # De-escalation flags (FL-R12)
        "de_escalation": {
            "earnings_window": earn_win,
            "vol_trade": vol_trade,
            "protective_put": prot_put,
            "gamma_caution": gam_caut,
        },
        # 2W display fields (FL-R7 — display only, never sort key or fire-qualifying)
        "stochrsi_2w_k": tw_fields.get("stochrsi_2w_k"),
        "stochrsi_2w_d": tw_fields.get("stochrsi_2w_d"),
        "stochrsi_2w_oversold": tw_fields.get("stochrsi_2w_oversold"),
        "macd_2w_state": tw_fields.get("macd_2w_state"),
        "macd_2w_bars_to_cross": tw_fields.get("macd_2w_bars_to_cross"),
        "macd_2w_bars_since": tw_fields.get("macd_2w_bars_since"),
        "htf_coverage": tw_fields.get("htf_coverage"),
    }
    return rec


# ── Main build ────────────────────────────────────────────────────────────────

def build(
    data_root: Path | None = None,
    site_root: Path | None = None,
    tpl_root: Path | None = None,
) -> dict:
    """Build leaders.json + render flow_leaders.html. Returns payload dict."""
    cfg = config.load()
    fl_cfg = cfg.get("flow_leaders") or {}

    if data_root is None:
        data_root = config.data_dir()
    if site_root is None:
        site_root = config.ROOT / cfg["storage"]["site_dir"]
    if tpl_root is None:
        tpl_root = config.ROOT / "templates"

    site_root.mkdir(parents=True, exist_ok=True)
    out_dir = site_root / "flowleaders"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not fl_cfg.get("enabled", True):
        _write_noindex_stub(site_root)
        return {}

    as_of = datetime.now(timezone.utc).isoformat()

    # ── Load all summary parquets ─────────────────────────────────────────────
    summaries = _load_all_summaries(data_root)
    if not summaries:
        log.warning("build_flow_leaders: no summary parquets found — writing cold-start payload")

    # ── Determine universe ────────────────────────────────────────────────────
    # flow_universe = names in summaries ∩ US single names (excludes ETFs from boards)
    all_flow_names = set(summaries.keys())
    etf_names = all_flow_names & _ETF_SET
    board_names = sorted(all_flow_names - _ETF_SET)

    log.info(
        "build_flow_leaders: %d flow names (%d board candidates, %d ETFs)",
        len(all_flow_names), len(board_names), len(etf_names),
    )

    # ── Freshness SLA ─────────────────────────────────────────────────────────
    latest_session = _latest_summary_session(summaries)
    stale = _check_stale(latest_session)
    if stale:
        log.warning("build_flow_leaders: flow store stale (latest=%s) — boards in stale state", latest_session)

    # ── Load supporting stores ────────────────────────────────────────────────
    tape_rows: dict[str, pd.Series | None] = {}
    for name in all_flow_names:
        tape_rows[name] = _load_tape_row(name, data_root)

    chain_t, chain_t1 = _load_two_chain_days(data_root)
    oi_confirmed_map: dict[str, bool | None] = {}
    if not chain_t.empty and not chain_t1.empty:
        try:
            from engine.flow_leaders import oi_confirm
            oi_series = oi_confirm(chain_t, chain_t1)
            oi_confirmed_map = oi_series.to_dict()
        except Exception as e:  # noqa: BLE001
            log.debug("build_flow_leaders: oi_confirm failed: %s", e)

    options_entry_map = _load_options_entry(data_root)
    personality_map = _load_personality(site_root)
    mtf_upturn_map = _load_mtf_upturn(site_root)
    washout_ctx_map = _load_washout_ctx(site_root)

    # ── Mktcap map from stockdata ─────────────────────────────────────────────
    mktcap_map: dict[str, float] = {}
    for name in board_names:
        sd = _load_stockdata(name, site_root)
        profile = sd.get("profile") or {}
        cap = profile.get("mktcap_bn") or profile.get("market_cap_bn")
        if cap is not None:
            try:
                mktcap_map[name] = float(cap)
            except (TypeError, ValueError):
                pass

    # ── Build membership history (for recurrence counting) ────────────────────
    board_summaries = {t: summaries[t] for t in board_names if t in summaries}
    membership_df = pd.DataFrame()
    if board_summaries and not stale:
        try:
            membership_df = _build_membership_df(board_summaries, mktcap_map, tape_rows)
        except Exception as e:  # noqa: BLE001
            log.warning("build_flow_leaders: membership build failed: %s", e)

    # ── Per-ticker records ────────────────────────────────────────────────────
    board_a_rows: list[dict] = []
    board_b_rows: list[dict] = []

    for ticker in board_names:
        try:
            rec = _build_ticker_record(
                ticker=ticker,
                is_etf=False,
                summaries=summaries,
                membership_df=membership_df,
                oi_confirmed_map=oi_confirmed_map,
                tape_rows=tape_rows,
                options_entry_map=options_entry_map,
                personality_map=personality_map,
                mtf_upturn_map=mtf_upturn_map,
                washout_ctx_map=washout_ctx_map,
                data_root=data_root,
                site_root=site_root,
                as_of=as_of,
                stale=stale,
            )
            # Route to board A (recurrence-sorted) and board B (inflection-sorted)
            # A row can appear on both boards
            board_a_rows.append(rec)
            board_b_rows.append(rec)
        except Exception as e:  # noqa: BLE001
            log.warning("build_flow_leaders: ticker %s failed (skipped): %s", ticker, e)

    # ── ETF strip ─────────────────────────────────────────────────────────────
    etf_strip: list[dict] = []
    for ticker in sorted(etf_names):
        sum_df = summaries.get(ticker)
        if sum_df is None or sum_df.empty:
            continue
        try:
            tape_row = tape_rows.get(ticker)
            last = sum_df.iloc[-1]
            def _g(r, k):
                v = r.get(k) if hasattr(r, "get") else getattr(r, k, None)
                return None if (isinstance(v, float) and pd.isna(v)) else v
            etf_strip.append({
                "ticker": ticker,
                "as_of": as_of,
                "signing_source": "tape" if tape_row is not None else "minute_tick",
                "net_premium_mn": _g(last, "net_premium_mn"),
                "premium_mn": _g(last, "premium_mn") or _g(last, "gross_premium_mn"),
                "zerodte_share": _g(last, "zerodte_share"),
            })
        except Exception as e:  # noqa: BLE001
            log.debug("build_flow_leaders: ETF strip %s failed: %s", ticker, e)

    # ── Sort boards ───────────────────────────────────────────────────────────
    # Board A: recurrence desc, ties broken by net_prem_norm_abs desc
    def _board_a_sort_key(r: dict) -> tuple:
        rc = r.get("recurrence_count")
        try:
            rc_float = float(rc) if rc is not None and rc is not pd.NA else None
        except (TypeError, ValueError):
            rc_float = None
        np_abs = r.get("net_prem_norm_abs")
        try:
            np_float = float(np_abs) if np_abs is not None and np_abs is not pd.NA else 0.0
        except (TypeError, ValueError):
            np_float = 0.0
        return (
            -rc_float if rc_float is not None else 1.0,
            -np_float,
        )

    board_a_rows.sort(key=_board_a_sort_key)
    # Board B: days_since_inflection asc (None last)
    def _board_b_sort_key(r: dict) -> float:
        dsi = r.get("days_since_inflection")
        try:
            return float(dsi) if dsi is not None and dsi is not pd.NA else 9999.0
        except (TypeError, ValueError):
            return 9999.0

    board_b_rows.sort(key=_board_b_sort_key)

    # Cold-start state
    from engine.flow_leaders import RECUR_MIN_HISTORY
    n_flow_sessions = len(sorted({
        str(idx.date()) if hasattr(idx, "date") else str(idx)[:10]
        for df in summaries.values()
        for idx in df.index
    }))
    cold_start = n_flow_sessions < RECUR_MIN_HISTORY

    # flow_z_live: any ticker with flow_z available
    flow_z_live = any(r.get("flow_z") is not None for r in board_a_rows)

    # tape_names: tickers with tape signing source
    tape_names = [
        ticker for ticker in all_flow_names
        if tape_rows.get(ticker) is not None
    ]

    payload: dict[str, Any] = {
        "schema": "flow_leaders.v1",
        "as_of": as_of,
        "stale": stale,
        "cold_start": cold_start,
        "direction_note": (
            "Net premium direction is ~-soft (approximate) for all sources "
            "until multi-session tape calibration extension passes (FL-R3). "
            "Magnitude leads direction."
        ),
        "coverage": {
            "n_universe": len(board_names),
            "n_flow_sessions": n_flow_sessions,
            "flow_z_live": flow_z_live,
            "tape_names": tape_names,
            "n_etfs": len(etf_strip),
        },
        "board_a": board_a_rows,
        "board_b": board_b_rows,
        "etf_strip": etf_strip,
        "cold_start_detail": {
            "n_sessions": n_flow_sessions,
            "required_for_recurrence": RECUR_MIN_HISTORY,
            "message": f"Recurrence accruing — {n_flow_sessions}/{RECUR_MIN_HISTORY} sessions" if cold_start else None,
        },
    }

    # ── Write leaders.json ────────────────────────────────────────────────────
    out_path = out_dir / "leaders.json"
    out_path.write_text(json.dumps(payload, separators=(",", ":"), default=_json_default))
    log.info(
        "build_flow_leaders: wrote %s (%d board candidates, %d bytes)",
        out_path, len(board_names), out_path.stat().st_size,
    )

    # ── Render HTML ───────────────────────────────────────────────────────────
    tpl_path = tpl_root / "flow_leaders.html.j2"
    if tpl_path.exists():
        try:
            env = Environment(loader=FileSystemLoader(str(tpl_root)), autoescape=False)
            tpl = env.get_template("flow_leaders.html.j2")
            rendered = tpl.render(flow_leaders=payload)
            html_out = site_root / "flow_leaders.html"
            html_out.write_text(rendered)
            log.info("build_flow_leaders: rendered %s", html_out)
        except Exception as e:  # noqa: BLE001
            log.warning("build_flow_leaders: HTML render failed: %s", e)
    else:
        log.info("build_flow_leaders: template %s absent — skipping HTML", tpl_path)

    return payload


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        result = build()
        if result:
            cov = result.get("coverage") or {}
            log.info(
                "build_flow_leaders: done. universe=%d, sessions=%d, stale=%s",
                cov.get("n_universe", 0),
                cov.get("n_flow_sessions", 0),
                result.get("stale"),
            )
    except Exception as e:  # noqa: BLE001
        log.error("build_flow_leaders: unexpected error: %s", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
