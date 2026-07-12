"""Mag-7 Regime Context Organ (mag7_regime.v1).

DISPLAY-ONLY / NOT VALIDATED — context organ, not a signal; ruling M7C-R2/R3.
Computes a daily regime snapshot for the seven mega-cap tech names (AAPL MSFT
NVDA AMZN GOOGL META TSLA) with:

  trend_state   — running_broad | running_narrow | turning_up | cooling |
                  rolling_over | down
  structure     — at_highs | recovering | drawdown
  run meter     — start date + session count + CW/SPY return since start
  k7            — count of members above 50/200 dma (trend/rs)
  member table  — weight, returns, relative-strength, MA booleans, contrib10
  generals      — coverage leaders + joiners
  tech_legs     — basket-relative performance vs SPY for contextual legs
  flow          — optional flow context from cohorts.parquet (fail-open, null
                  when FL-B artifact absent); see _compute_flow_block() for
                  pc_word thresholds (volume P/C ratio: call_tilted ≤ 0.75,
                  put_tilted ≥ 1.25, else balanced). NO direction language;
                  display-only (FC-R5 / FL-D).
  ledger        — data/mag7_regime/ledger.jsonl, one row per session,
                  idempotent by date

Inputs:
  data/baskets/ohlcv/<SYM>.parquet   member closes (column: close, Date index)
  store.read("yahoo", "SPY")         SPY closes for relative returns + CW index
  data/sp500_heatmap/reference.parquet  shares outstanding for mktcap weights
  site/stockdata/mtf_upturn.json     per-member MTF state (fail-open → null)
  data/massive_stock_day/MAGS.parquet  MAGS ETF reference (display-only)
  data/options_flow/cohorts.parquet  FL-B cohort flow store (fail-open → null
                                     when absent; columns: date, cohort_id,
                                     gross_premium_mn, net_premium_mn,
                                     pc_ratio, zerodte_share, n_members_covered,
                                     n_members)

Outputs:
  data/mag7_regime/latest.json       snapshot
  site/stockdata/mag7_regime.json    CDN-facing copy
  data/mag7_regime/ledger.jsonl      idempotent daily ledger
"""
from __future__ import annotations

import json
import logging
import math
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAG7: list[str] = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

_TECH_LEGS: list[dict] = [
    {"id": "mag7",             "en": "Mag 7",     "zh": "七巨头"},
    {"id": "ai_semiconductors","en": "AI chips",  "zh": "AI芯片"},
    {"id": "memory_storage",   "en": "Memory",    "zh": "存储"},
    {"id": "ai_software",      "en": "Software",  "zh": "软件"},
]

# basket-id → constituent tickers used to compute a quick equal-weight return
# for the tech_legs context (display-only; these approximate the basket).
_LEG_TICKERS: dict[str, list[str]] = {
    "mag7":             MAG7,
    "ai_semiconductors":["NVDA", "AMD", "AVGO", "QCOM", "MRVL"],
    "memory_storage":   ["MU", "WDC", "STX"],
    "ai_software":      ["MSFT", "GOOGL", "CRM", "NOW", "PLTR"],
}

_MAGS_STALE_BD = 5   # MAGS data older than this many business days → null


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(ts) -> str | None:
    try:
        if ts is None or (isinstance(ts, float) and math.isnan(ts)):
            return None
        return str(pd.Timestamp(ts).date())
    except Exception:  # noqa: BLE001
        return None


def _bd_since(ts) -> int | None:
    if ts is None:
        return None
    try:
        t = pd.Timestamp(ts)
        today = pd.Timestamp(date.today())
        return max(0, len(pd.bdate_range(t, today)) - 1)
    except Exception:  # noqa: BLE001
        return None


def _load_closes(sym: str, *, root: Path | None = None) -> pd.Series | None:
    """Load adjusted close series from data/baskets/ohlcv/<SYM>.parquet."""
    try:
        base = root or config.data_dir()
        p = base / "baskets" / "ohlcv" / f"{sym}.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index().astype(float)
        s.index = pd.to_datetime(s.index)
        return s
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: ohlcv load failed %s: %s", sym, e)
        return None


def _load_spy(*, root: Path | None = None) -> pd.Series | None:  # noqa: ARG001
    """Load SPY close series (mirrors baskets.py idiom)."""
    try:
        df = store.read("yahoo", "SPY")
        if df is None or "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index().astype(float)
        s.index = pd.to_datetime(s.index)
        return s
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: SPY load failed: %s", e)
        return None


def _load_mktcaps(closes_last: dict[str, float], *, root: Path | None = None) -> dict[str, float]:
    """Load mktcap weights from data/sp500_heatmap/reference.parquet.

    Returns dict[sym, cap_float] for symbols with valid shares data.
    Falls back to {} if the file is missing or all shares are None.
    """
    try:
        base = root or config.data_dir()
        p = base / "sp500_heatmap" / "reference.parquet"
        if not p.exists():
            return {}
        ref = pd.read_parquet(p)
        if "shares" not in ref.columns:
            return {}
        caps: dict[str, float] = {}
        for sym, row in ref.iterrows():
            shares = row.get("shares")
            if shares is None or pd.isna(shares):
                continue
            px = closes_last.get(sym)
            if px is None or pd.isna(px):
                continue
            caps[sym] = float(shares) * float(px)
        return caps
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: reference.parquet load failed: %s", e)
        return {}


def _load_mtf_state(sym: str, *, root: Path | None = None) -> str | None:
    """Load MTF upturn state for a single symbol; fail-open → None."""
    try:
        base = root or config.ROOT  # noqa: SIM108
        site_root = base / config.load()["storage"]["site_dir"]
        p = site_root / "stockdata" / "mtf_upturn.json"
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        tickers = data.get("tickers", {})
        entry = tickers.get(sym, {})
        return entry.get("state") or None
    except Exception:  # noqa: BLE001
        return None


def _load_mags(*, root: Path | None = None) -> dict | None:
    """Load MAGS ETF data for display chip. Returns None if stale (>5 bd)."""
    try:
        base = root or config.data_dir()
        p = base / "massive_stock_day" / "MAGS.parquet"
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            return None
        s = df["close"].dropna().sort_index().astype(float)
        s.index = pd.to_datetime(s.index)
        if s.empty:
            return None
        asof_ts = s.index[-1]
        bd = _bd_since(asof_ts)
        if bd is not None and bd > _MAGS_STALE_BD:
            log.info("mag7_regime: MAGS stale (%d bd) → null", bd)
            return None
        asof_str = _iso(asof_ts)
        return {"px": float(round(s.iloc[-1], 2)), "asof": asof_str}
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: MAGS load failed: %s", e)
        return None


def _safe_ret(series: pd.Series, n: int) -> float | None:
    """n-session log-price return; returns None if insufficient data."""
    try:
        s = series.dropna()
        if len(s) < n + 1:
            return None
        return float(round(s.iloc[-1] / s.iloc[-1 - n] - 1, 6))
    except Exception:  # noqa: BLE001
        return None


def _safe_sma(series: pd.Series, n: int) -> pd.Series | None:
    """Rolling simple moving average; returns None if not enough data."""
    try:
        s = series.dropna()
        if len(s) < n:
            return None
        return s.rolling(n, min_periods=n).mean()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# CW/EW composite index
# ---------------------------------------------------------------------------

def _build_composite(
    closes: dict[str, pd.Series],
    weights: dict[str, float],
) -> pd.Series:
    """Build a weighted daily-return composite index (starts at 1.0 on first day).

    Weights are renormalized over available symbols each day (handles missing
    data gracefully — day-specific weight normalisation).
    """
    # align all series to a common daily date grid
    aligned = pd.DataFrame({sym: closes[sym] for sym in closes if sym in weights})
    if aligned.empty:
        return pd.Series(dtype=float)
    aligned.index = pd.to_datetime(aligned.index)
    aligned = aligned.sort_index()

    w_vec = pd.Series({sym: weights[sym] for sym in aligned.columns})

    daily_ret = aligned.pct_change()
    # weighted sum of returns, normalizing each day by available weight
    wret = daily_ret.multiply(w_vec, axis=1)
    valid_w = aligned.notna().multiply(w_vec, axis=1).sum(axis=1)
    wret_daily = wret.sum(axis=1) / valid_w.replace(0, np.nan)
    wret_daily = wret_daily.fillna(0)

    # cumulative price index
    composite = (1 + wret_daily).cumprod()
    return composite.dropna()


# ---------------------------------------------------------------------------
# Core computations
# ---------------------------------------------------------------------------

def _compute_k7(closes: dict[str, pd.Series]) -> dict:
    """Count members above 50dma (trend) and 200dma (rs)."""
    trend = 0
    rs = 0
    for sym, s in closes.items():
        s = s.dropna()
        if len(s) >= 51:
            sma50 = s.rolling(50).mean().iloc[-1]
            if not pd.isna(sma50) and s.iloc[-1] > sma50:
                trend += 1
        if len(s) >= 201:
            sma200 = s.rolling(200).mean().iloc[-1]
            if not pd.isna(sma200) and s.iloc[-1] > sma200:
                rs += 1
    return {"trend": trend, "rs": rs}


def _compute_member_table(
    closes: dict[str, pd.Series],
    weights: dict[str, float],
    spy: pd.Series,
    *,
    cw_r10: float | None,
    mtf_states: dict[str, str | None],
) -> list[dict]:
    """Build per-member row for the members array."""
    rows = []
    # sum of positive contributions (for contrib10 share)
    pos_contribs: list[float] = []
    raw_rows: list[dict] = []
    for sym in MAG7:
        s = closes.get(sym)
        w = weights.get(sym, 1 / len(MAG7))
        r5 = _safe_ret(s, 5) if s is not None else None
        r10 = _safe_ret(s, 10) if s is not None else None
        r20 = _safe_ret(s, 20) if s is not None else None

        # relative strength vs SPY over 20d
        rs20: float | None = None
        if r20 is not None:
            spy_r20 = _safe_ret(spy, 20)
            if spy_r20 is not None:
                rs20 = round(r20 - spy_r20, 6)

        # MA booleans
        above50 = above200 = None
        if s is not None:
            sv = s.dropna()
            if len(sv) >= 51:
                sma50 = sv.rolling(50).mean().iloc[-1]
                above50 = bool(not pd.isna(sma50) and sv.iloc[-1] > sma50)
            if len(sv) >= 201:
                sma200 = sv.rolling(200).mean().iloc[-1]
                above200 = bool(not pd.isna(sma200) and sv.iloc[-1] > sma200)

        contrib10_raw = (w * r10) if (r10 is not None) else None
        if contrib10_raw is not None and contrib10_raw > 0:
            pos_contribs.append(contrib10_raw)

        raw_rows.append({
            "sym": sym,
            "w": round(w, 6),
            "r5": round(r5, 6) if r5 is not None else None,
            "r10": round(r10, 6) if r10 is not None else None,
            "r20": round(r20, 6) if r20 is not None else None,
            "rs20": round(rs20, 6) if rs20 is not None else None,
            "above50": above50,
            "above200": above200,
            "_contrib10_raw": contrib10_raw,
            "mtf": mtf_states.get(sym),
        })

    total_pos = sum(pos_contribs) if pos_contribs else 0.0
    use_contrib = (cw_r10 is not None) and (cw_r10 > 0) and (total_pos > 0)

    for row in raw_rows:
        c = row.pop("_contrib10_raw")
        if use_contrib and c is not None and c > 0:
            row["contrib10"] = round(c / total_pos, 4)
        else:
            row["contrib10"] = None
        rows.append(row)

    return rows


def _compute_structure(cw: pd.Series) -> dict:
    """Structure chip: dd from 252-session high + chip label."""
    try:
        if cw is None or len(cw) < 20:
            return {"dd_from_252d_high": None, "chip": "drawdown"}
        high252 = cw.rolling(min(252, len(cw)), min_periods=10).max().iloc[-1]
        cur = cw.iloc[-1]
        dd = float(round((cur / high252) - 1, 6)) if (high252 and not pd.isna(high252)) else None
        r20 = _safe_ret(cw, 20)
        if dd is None:
            chip = "drawdown"
        elif dd >= -0.03:
            chip = "at_highs"
        elif dd > -0.15 and r20 is not None and r20 > 0:
            chip = "recovering"
        else:
            chip = "drawdown"
        return {"dd_from_252d_high": dd, "chip": chip}
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: structure calc failed: %s", e)
        return {"dd_from_252d_high": None, "chip": "drawdown"}


def _compute_run(cw: pd.Series, spy: pd.Series) -> dict:
    """Run meter: start of consecutive CW > 20-session SMA streak."""
    result: dict[str, Any] = {"start": None, "sessions": 0, "cw_ret": None, "spy_ret": None}
    try:
        if cw is None or len(cw) < 21:
            return result
        sma20 = cw.rolling(20, min_periods=20).mean()
        above = (cw > sma20).astype(int)
        if above.iloc[-1] != 1:
            return result
        # find start of current streak
        streak_len = 0
        for i in range(len(above) - 1, -1, -1):
            if above.iloc[i] == 1:
                streak_len += 1
            else:
                break
        start_idx = len(cw) - streak_len
        start_ts = cw.index[start_idx]
        start_str = _iso(start_ts)
        cw_ret = _safe_ret(cw.iloc[start_idx:].reset_index(drop=True), streak_len - 1)
        # SPY return over same window
        spy_aligned = spy[spy.index >= start_ts]
        spy_ret = _safe_ret(spy_aligned, min(len(spy_aligned) - 1, streak_len - 1)) if len(spy_aligned) >= 2 else None
        result = {
            "start": start_str,
            "sessions": streak_len,
            "cw_ret": round(cw_ret, 6) if cw_ret is not None else None,
            "spy_ret": round(spy_ret, 6) if spy_ret is not None else None,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: run meter failed: %s", e)
    return result


def _compute_trend_state(
    cw: pd.Series,
    k7_trend: int,
) -> str:
    """trend_state — first-match rule from spec."""
    try:
        if cw is None or len(cw) < 21:
            return "cooling"
        sma20 = cw.rolling(20, min_periods=20).mean()
        r10 = _safe_ret(cw, 10)
        cur_above = bool((cw > sma20).iloc[-1]) if not pd.isna(sma20.iloc[-1]) else False
        up = (r10 is not None and r10 >= 0.02) and cur_above

        if up:
            # was up 10 sessions ago?
            if len(cw) >= 11:
                cw_10ago = cw.iloc[:-10]
                sma20_10ago = cw_10ago.rolling(20, min_periods=20).mean()
                r10_10ago = _safe_ret(cw_10ago, 10)
                above_10ago = (
                    bool((cw_10ago > sma20_10ago).iloc[-1])
                    if (len(sma20_10ago) > 0 and not pd.isna(sma20_10ago.iloc[-1]))
                    else False
                )
                up_10ago = (r10_10ago is not None and r10_10ago >= 0.02) and above_10ago
            else:
                up_10ago = False

            # when did it first become true in the last 5 sessions?
            if not up_10ago:
                # check if it became true within last 5 sessions
                first_true_in_5 = False
                for lag in range(1, 6):
                    if len(cw) <= lag:
                        break
                    cw_lag = cw.iloc[:-lag]
                    sma_lag = cw_lag.rolling(20, min_periods=20).mean()
                    r_lag = _safe_ret(cw_lag, 10)
                    above_lag = (
                        bool((cw_lag > sma_lag).iloc[-1])
                        if (len(sma_lag) > 0 and not pd.isna(sma_lag.iloc[-1]))
                        else False
                    )
                    up_lag = (r_lag is not None and r_lag >= 0.02) and above_lag
                    if not up_lag:
                        first_true_in_5 = True
                        break
                if first_true_in_5:
                    return "turning_up"

            if k7_trend >= 5:
                return "running_broad"
            return "running_narrow"

        # rolling_over: was up at some point in last 20 sessions?
        r10_now = _safe_ret(cw, 10)
        neg_down = r10_now is not None and r10_now <= -0.02
        below_sma = not cur_above
        if neg_down and below_sma:
            # was up at some point in last 20 sessions?
            was_up_recently = False
            for lag in range(1, 21):
                if len(cw) <= lag:
                    break
                cw_lag = cw.iloc[:-lag]
                sma_lag = cw_lag.rolling(20, min_periods=20).mean()
                r_lag = _safe_ret(cw_lag, 10)
                above_lag = (
                    bool((cw_lag > sma_lag).iloc[-1])
                    if (len(sma_lag) > 0 and not pd.isna(sma_lag.iloc[-1]))
                    else False
                )
                if (r_lag is not None and r_lag >= 0.02) and above_lag:
                    was_up_recently = True
                    break
            if was_up_recently:
                return "rolling_over"

        # down: CW < 200sma AND dd <= -15% AND NOT up
        if len(cw) >= 201:
            sma200 = cw.rolling(200, min_periods=200).mean()
            below_200 = bool((cw < sma200).iloc[-1]) if not pd.isna(sma200.iloc[-1]) else False
            dd_val = _compute_structure(cw)["dd_from_252d_high"]
            if below_200 and (dd_val is not None and dd_val <= -0.15) and not up:
                return "down"

        return "cooling"
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: trend_state calc failed: %s", e)
        return "cooling"


def _compute_generals(member_rows: list[dict], weights: dict[str, float]) -> dict:
    """Generals: coverage-weighted now list + top-2 joining candidates."""
    # filter rows with valid contrib10
    scored = [(r["sym"], r["contrib10"]) for r in member_rows if r.get("contrib10") is not None]
    scored.sort(key=lambda x: x[1], reverse=True)

    # smallest prefix covering >= 60% cumulative contrib10 weight, capped at 3
    now_syms: list[str] = []
    coverage = 0.0
    for sym, contrib in scored:
        if coverage >= 0.60 or len(now_syms) >= 3:
            break
        now_syms.append(sym)
        coverage += contrib

    # generals.joining: top-2 by 2-day contribution not already in now
    raw_2d: list[tuple[str, float]] = []
    for r in member_rows:
        sym = r["sym"]
        if sym in now_syms:
            continue
        w = weights.get(sym, 1 / len(MAG7))
        r5 = r.get("r5")
        r10 = r.get("r10")
        if r5 is not None and r10 is not None:
            approx_r2 = r5 - r10 / 2  # crude 2d proxy
        elif r5 is not None:
            approx_r2 = r5
        else:
            approx_r2 = 0.0
        raw_2d.append((sym, w * approx_r2))
    raw_2d.sort(key=lambda x: x[1], reverse=True)
    joining = [s for s, _ in raw_2d[:2]]

    return {
        "now": now_syms,
        "joining": joining,
        "coverage": round(coverage, 4),
    }


def _ret_word(r10_rel: float | None) -> str:
    if r10_rel is None:
        return "flat"
    if r10_rel >= 0.05:
        return "surging"
    if r10_rel >= 0.02:
        return "running"
    if r10_rel <= -0.05:
        return "falling hard"
    if r10_rel <= -0.02:
        return "falling"
    return "flat"


def _compute_tech_legs(
    spy: pd.Series,
    *,
    root: Path | None = None,
) -> list[dict]:
    """Quick equal-weight tech-leg comparison vs SPY."""
    spy_r10 = _safe_ret(spy, 10)
    spy_r20 = _safe_ret(spy, 20)
    results: list[dict] = []
    for leg in _TECH_LEGS:
        lid = leg["id"]
        tickers = _LEG_TICKERS.get(lid, [])
        r10_list = []
        r20_list = []
        for sym in tickers:
            s = _load_closes(sym, root=root)
            if s is not None:
                r10 = _safe_ret(s, 10)
                r20 = _safe_ret(s, 20)
                if r10 is not None:
                    r10_list.append(r10)
                if r20 is not None:
                    r20_list.append(r20)
        r10_avg = float(np.mean(r10_list)) if r10_list else None
        r20_avg = float(np.mean(r20_list)) if r20_list else None

        r10_rel = (round(r10_avg - spy_r10, 6) if (r10_avg is not None and spy_r10 is not None) else None)
        r20_rel = (round(r20_avg - spy_r20, 6) if (r20_avg is not None and spy_r20 is not None) else None)

        results.append({
            "id": lid,
            "en": leg["en"],
            "zh": leg["zh"],
            "r10_rel": r10_rel,
            "r20_rel": r20_rel,
            "word": _ret_word(r10_rel),
        })
    return results


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def _append_ledger(
    row: dict,
    *,
    root: Path | None = None,
) -> None:
    """Append one row to ledger.jsonl; idempotent by date."""
    try:
        base = root or config.data_dir()
        p = base / "mag7_regime" / "ledger.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        date_key = row.get("date")
        # read existing lines to check for duplicate date
        existing: list[str] = []
        if p.exists():
            existing = p.read_text().splitlines()
        for line in existing:
            try:
                obj = json.loads(line)
                if obj.get("date") == date_key:
                    log.debug("mag7_regime: ledger already has %s — skip", date_key)
                    return
            except Exception:  # noqa: BLE001
                pass
        with p.open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        log.info("mag7_regime: appended ledger row for %s", date_key)
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: ledger append failed: %s", e)


# ---------------------------------------------------------------------------
# cohort_flow.v1 forward ledger (FC-R5) — nightly, accrual only
# ---------------------------------------------------------------------------

_COHORT_FLOW_LEDGER_DIR = "cohort_flow_ledger"
_COHORT_FLOW_LEDGER_FILE = "ledger.jsonl"

# Cohort ids we record in the ledger (mag7 + the three basket cohorts).
_COHORT_FLOW_COHORTS: list[str] = [
    "mag7",
    "memory_storage",
    "ai_semiconductors",
    "ai_software",
]


def _append_cohort_flow_ledger(
    date_str: str,
    flow_rows: list[dict],
    *,
    root: Path | None = None,
) -> None:
    """Append one row per cohort to data/cohort_flow_ledger/ledger.jsonl.

    Idempotent by (date, cohort). Gated on COLLECT_LANE=nightly (house law:
    nightly is sole advancer of data/ forward ledgers).

    Schema per row: {date, cohort, tilt, pc_ratio, gross_mn}

    DOCTRINE: accrual only (FC-R5 / FL-D / FT-R9). This ledger grades NOTHING
    yet — registered as an expected-NULL forward meter. No direction language.
    """
    import os as _os
    lane = _os.environ.get("COLLECT_LANE", "") or _os.environ.get("US_LANE", "")
    if lane.lower() != "nightly":
        log.debug("mag7_regime: cohort_flow ledger skipped (COLLECT_LANE != nightly)")
        return

    if not flow_rows:
        return

    try:
        base = root or config.data_dir()
        p = base / _COHORT_FLOW_LEDGER_DIR / _COHORT_FLOW_LEDGER_FILE
        p.parent.mkdir(parents=True, exist_ok=True)

        # Load existing to check idempotency
        existing_keys: set[tuple] = set()
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    existing_keys.add((obj.get("date"), obj.get("cohort")))
                except Exception:  # noqa: BLE001
                    pass

        appended = 0
        with p.open("a") as fh:
            for row in flow_rows:
                key = (row.get("date"), row.get("cohort"))
                if key in existing_keys:
                    continue
                fh.write(json.dumps(row, default=str) + "\n")
                existing_keys.add(key)
                appended += 1

        if appended:
            log.info("mag7_regime: cohort_flow ledger appended %d rows for %s", appended, date_str)
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: cohort_flow ledger append failed: %s", e)


# ---------------------------------------------------------------------------
# Flow block (FC-R5 / FL-D) — fail-open, cohorts.parquet optional
# ---------------------------------------------------------------------------

# P/C ratio thresholds for tilt words (volume put/call ratio).
# call_tilted  : pc_ratio <= 0.75  (calls dominate by volume)
# put_tilted   : pc_ratio >= 1.25  (puts dominate by volume)
# balanced     : between 0.75 and 1.25
_FLOW_CALL_TILTED_THRESHOLD = 0.75
_FLOW_PUT_TILTED_THRESHOLD = 1.25
_FLOW_TILT_SESSIONS = 5  # look-back window for tilt_sessions count


def _pc_word(pc_ratio: float | None) -> str | None:
    """Return tilt word for a single session's P/C ratio; None if missing."""
    if pc_ratio is None or (isinstance(pc_ratio, float) and math.isnan(pc_ratio)):
        return None
    if pc_ratio <= _FLOW_CALL_TILTED_THRESHOLD:
        return "call_tilted"
    if pc_ratio >= _FLOW_PUT_TILTED_THRESHOLD:
        return "put_tilted"
    return "balanced"


def _compute_flow_block(
    *,
    cohort_id: str = "mag7",
    root: Path | None = None,
) -> dict | None:
    """Compute the optional flow block from data/options_flow/cohorts.parquet.

    Returns None when the file is absent (fail-open: panel unchanged).
    Returns a dict {asof, gross_mn, pc_word, tilt_sessions, coverage} when
    the file is present and the mag7 cohort row is found.

    P/C ratio = put volume / call volume (volume-based, not premium-based).
    pc_word thresholds:
      call_tilted  : pc_ratio <= 0.75
      put_tilted   : pc_ratio >= 1.25
      balanced     : else

    DOCTRINE: NO direction language beyond tilt words; NO score. Display-only
    (FC-R5 / FL-D). buy-vs-sell direction is approximate — size and call/put
    mix are the solid reads.
    """
    try:
        base = root or config.data_dir()
        p = base / "options_flow" / "cohorts.parquet"
        if not p.exists():
            return None

        df = pd.read_parquet(p)
        if df.empty:
            return None

        # Normalise date column
        if "date" not in df.columns:
            log.warning("mag7_regime: flow block: cohorts.parquet missing 'date' column")
            return None

        df = df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")

        # Filter to the mag7 cohort
        if "cohort_id" not in df.columns:
            log.warning("mag7_regime: flow block: cohorts.parquet missing 'cohort_id' column")
            return None

        mag7_rows = df[df["cohort_id"] == cohort_id]
        if mag7_rows.empty:
            return None

        # Latest row
        latest = mag7_rows.iloc[-1]
        asof = _iso(latest["date"])

        gross_mn: float | None = None
        try:
            raw = latest.get("gross_premium_mn")
            if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
                gross_mn = round(float(raw), 2)
        except Exception:  # noqa: BLE001
            pass

        pc_ratio_latest: float | None = None
        try:
            raw = latest.get("pc_ratio")
            if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
                pc_ratio_latest = float(raw)
        except Exception:  # noqa: BLE001
            pass

        tilt_word = _pc_word(pc_ratio_latest)

        # coverage: "X of 7"
        coverage: str | None = None
        try:
            n_cov = latest.get("n_members_covered")
            n_tot = latest.get("n_members")
            if n_cov is not None and n_tot is not None:
                coverage = f"{int(n_cov)} of {int(n_tot)}"
        except Exception:  # noqa: BLE001
            pass

        # zerodte_share
        zerodte: float | None = None
        try:
            raw = latest.get("zerodte_share")
            if raw is not None and not (isinstance(raw, float) and math.isnan(raw)):
                zerodte = round(float(raw), 4)
        except Exception:  # noqa: BLE001
            pass

        # tilt_sessions: count call_tilted in last N sessions
        recent = mag7_rows.tail(_FLOW_TILT_SESSIONS)
        tilt_sessions: int = 0
        for _, row in recent.iterrows():
            pc = row.get("pc_ratio")
            if _pc_word(pc) == "call_tilted":
                tilt_sessions += 1

        return {
            "asof": asof,
            "gross_mn": gross_mn,
            "pc_word": tilt_word,
            "tilt_sessions": tilt_sessions,
            "coverage": coverage,
            "zerodte_share": zerodte,
            "pc_ratio": round(pc_ratio_latest, 4) if pc_ratio_latest is not None else None,
        }
    except Exception as e:  # noqa: BLE001
        import traceback as _tb
        log.warning("mag7_regime: flow block failed: %s", e)
        log.debug("mag7_regime: flow block traceback: %s", _tb.format_exc())
        return None


# ---------------------------------------------------------------------------
# Main snapshot
# ---------------------------------------------------------------------------

def snapshot(root: str | Path | None = None) -> dict:
    """Compute the full Mag-7 Regime snapshot.

    Returns the payload dict AND writes:
      data/mag7_regime/latest.json
      site/stockdata/mag7_regime.json
    Appends to:
      data/mag7_regime/ledger.jsonl  (idempotent by date)

    Never raises — degrades gracefully on every store failure.
    """
    t0 = time.monotonic()
    _root: Path | None = Path(root) if root else None
    _data_root: Path = (_root / "data") if _root else config.data_dir()

    # --- load member closes ---
    closes: dict[str, pd.Series] = {}
    for sym in MAG7:
        s = _load_closes(sym, root=_data_root)
        if s is not None and len(s) >= 2:
            closes[sym] = s
        else:
            log.warning("mag7_regime: no close data for %s", sym)

    if not closes:
        log.error("mag7_regime: no member close data — returning empty payload")
        return {}

    # --- load SPY ---
    spy = _load_spy()
    if spy is None or spy.empty:
        log.warning("mag7_regime: SPY unavailable")
        spy = pd.Series(dtype=float)

    # --- mktcap weights ---
    closes_last = {sym: float(s.iloc[-1]) for sym, s in closes.items()}
    raw_caps = _load_mktcaps(closes_last, root=_data_root)

    weights_basis: str
    weights: dict[str, float]
    if raw_caps and any(raw_caps.get(sym) for sym in MAG7):
        total = sum(raw_caps.get(sym, 0) or 0 for sym in MAG7 if sym in closes)
        if total > 0:
            weights = {sym: (raw_caps.get(sym, 0) or 0) / total for sym in MAG7 if sym in closes}
            weights_basis = "polygon_mktcap"
        else:
            n = len(closes)
            weights = {sym: 1 / n for sym in closes}
            weights_basis = "equal_fallback"
    else:
        n = len(closes)
        weights = {sym: 1 / n for sym in closes}
        weights_basis = "equal_fallback"

    # --- build CW and EW composites ---
    cw_series = _build_composite(closes, weights)
    ew_weights = {sym: 1 / len(closes) for sym in closes}
    ew_series = _build_composite(closes, ew_weights)

    # --- as_of date ---
    as_of = _iso(cw_series.index[-1]) if not cw_series.empty else str(date.today())

    # --- CW window returns ---
    cw_ret_dict: dict[str, float | None] = {}
    for n, key in [(2, "r2"), (5, "r5"), (10, "r10"), (20, "r20")]:
        cw_ret_dict[key] = _safe_ret(cw_series, n)
    spy_r20 = _safe_ret(spy, 20) if not spy.empty else None
    cw_r20 = cw_ret_dict["r20"]
    cw_ret_dict["rel20"] = (
        round(cw_r20 - spy_r20, 6)
        if (cw_r20 is not None and spy_r20 is not None)
        else None
    )

    # EW returns
    ew_r10 = _safe_ret(ew_series, 10)
    ew_r20 = _safe_ret(ew_series, 20)

    # --- k7 ---
    k7 = _compute_k7(closes)

    # --- trend_state ---
    trend_state = _compute_trend_state(cw_series, k7["trend"])

    # --- structure ---
    structure = _compute_structure(cw_series)

    # --- run meter ---
    run = _compute_run(cw_series, spy)

    # --- MTF states ---
    mtf_states: dict[str, str | None] = {}
    for sym in MAG7:
        mtf_states[sym] = _load_mtf_state(sym, root=_root)

    # --- member table ---
    cw_r10 = cw_ret_dict["r10"]
    member_rows = _compute_member_table(
        closes,
        weights,
        spy,
        cw_r10=cw_r10,
        mtf_states=mtf_states,
    )

    # --- generals ---
    generals = _compute_generals(member_rows, weights)

    # --- MAGS chip ---
    mags_raw = _load_mags(root=_data_root)
    mags_payload: dict | None = None
    if mags_raw is not None:
        since_run_ret: float | None = None
        try:
            if run.get("start"):
                mags_p = _data_root / "massive_stock_day" / "MAGS.parquet"
                if mags_p.exists():
                    mags_df = pd.read_parquet(mags_p)
                    if "close" in mags_df.columns:
                        mags_s = mags_df["close"].dropna().sort_index().astype(float)
                        mags_s.index = pd.to_datetime(mags_s.index)
                        run_start = pd.Timestamp(run["start"])
                        mags_since = mags_s[mags_s.index >= run_start]
                        if len(mags_since) >= 2:
                            since_run_ret = round(
                                float(mags_since.iloc[-1] / mags_since.iloc[0]) - 1, 6
                            )
        except Exception:  # noqa: BLE001
            pass
        mags_payload = {
            "px": mags_raw["px"],
            "asof": mags_raw["asof"],
            "since_run": since_run_ret,
        }

    # --- spread20 ---
    r20_vals = [r["r20"] for r in member_rows if r.get("r20") is not None]
    spread20: dict[str, float | None]
    if r20_vals:
        spread20 = {
            "max": round(max(r20_vals), 6),
            "min": round(min(r20_vals), 6),
            "range": round(max(r20_vals) - min(r20_vals), 6),
        }
    else:
        spread20 = {"max": None, "min": None, "range": None}

    # --- tech_legs ---
    tech_legs = _compute_tech_legs(spy, root=_data_root)

    # --- flow block (FC-R5 / FL-D) — fail-open; None when FL-B artifact absent ---
    flow_block = _compute_flow_block(root=_data_root)

    # --- cohort_flow.v1 forward ledger (FC-R5) — accrual only, nightly-gated ---
    # Build ledger rows for all four cohorts (fail-open: missing rows → skipped).
    try:
        _flow_ledger_rows: list[dict] = []
        for _cid in _COHORT_FLOW_COHORTS:
            _fb = flow_block if _cid == "mag7" else _compute_flow_block(
                cohort_id=_cid, root=_data_root
            )
            if _fb is not None:
                _flow_ledger_rows.append({
                    "date": as_of,
                    "cohort": _cid,
                    "tilt": _fb.get("pc_word"),
                    "pc_ratio": _fb.get("pc_ratio"),
                    "gross_mn": _fb.get("gross_mn"),
                })
        _append_cohort_flow_ledger(as_of, _flow_ledger_rows, root=_data_root)
    except Exception as _ex:  # noqa: BLE001
        log.warning("mag7_regime: cohort_flow ledger build failed: %s", _ex)

    elapsed = round(time.monotonic() - t0, 2)
    log.info("[timing] mag7_regime.snapshot: %.2fs", elapsed)

    payload: dict = {
        "as_of": as_of,
        "weights_basis": weights_basis,
        "trend_state": trend_state,
        "structure": structure,
        "run": run,
        "k7": k7,
        "cw": {k: (round(v, 6) if v is not None else None) for k, v in cw_ret_dict.items()},
        "ew": {
            "r10": round(ew_r10, 6) if ew_r10 is not None else None,
            "r20": round(ew_r20, 6) if ew_r20 is not None else None,
        },
        "members": member_rows,
        "generals": generals,
        "spread20": spread20,
        "mags": mags_payload,
        "tech_legs": tech_legs,
        # FC-R5 / FL-D: optional flow context block. None when FL-B cohorts.parquet
        # absent (fail-open). NO direction language; display-only context chip.
        "flow": flow_block,
        "_timing_s": elapsed,
    }

    # --- write latest.json ---
    try:
        out_path = _data_root / "mag7_regime" / "latest.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("mag7_regime: wrote %s", out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: write latest.json failed: %s", e)

    # --- write site/stockdata copy ---
    try:
        site_root = _root / config.load()["storage"]["site_dir"] if _root else (
            config.ROOT / config.load()["storage"]["site_dir"]
        )
        sd_path = site_root / "stockdata" / "mag7_regime.json"
        sd_path.parent.mkdir(parents=True, exist_ok=True)
        sd_path.write_text(json.dumps(payload, indent=2, default=str))
        log.info("mag7_regime: wrote site copy %s", sd_path)
    except Exception as e:  # noqa: BLE001
        log.warning("mag7_regime: site/stockdata write failed: %s", e)

    # --- append ledger ---
    ledger_row = {
        "date": as_of,
        "trend_state": trend_state,
        "structure_chip": structure.get("chip"),
        "k7_trend": k7["trend"],
        "cw_r10": cw_r10,
        "generals": generals.get("now"),
    }
    _append_ledger(ledger_row, root=_data_root)

    return payload
