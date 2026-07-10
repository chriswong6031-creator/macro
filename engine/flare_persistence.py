"""engine/flare_persistence.py — per-stock flare persistence organ (NAR-R1..R10, W1).

DISPLAY-ONLY. Authority block: tier=display, may_rank=False, may_gate=False, may_size=False.

Reads raw measurable tape witnesses for each US ticker (no intel_hub composites —
NAR-R1/RUL-N2). Accumulates witness counts via Page-CUSUM (Lorden-optimal spike
vs takeover discrimination). States this wave: DORMANT | PRIMED | FADING.
ARMED / CONFIRMED-CANDIDATE are later-wave states — enum reserved, not implemented.

Witnesses (binary present/absent + magnitude, never weighted scores — FT-R3 shape):
  T1 altdata_convergence — >=3 channels on a HIGH-severity alert day (alerts.jsonl).
  T2 callprem           — net call premium z >= 2 vs own trailing 90d (median/MAD).
  T3 gex_flip           — GEX regime == long AND sign-flipped within trailing 10 sessions.
  T4 news_bull          — bull_ratio z >= 2 vs own trailing 90d (median/MAD).

NAR-R10: absent/stale store => witness absent + staleness printed; NEVER crash.

Artifacts:
  site/stockdata/flare_persistence.json  — sorted by state then s_plus
  data/flare_persistence/state_hist.parquet — PIT append-only (ticker, date, …)

Masterplan: research/NARRATIVE_IGNITION_MASTERPLAN_BY_FABLE.md §4.1 + §7 W1 row.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (display-tier — NAR §4 invariant)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

# ---------------------------------------------------------------------------
# Thresholds — FROZEN (pre-registration record, masterplan §4.1)
# Amendments require a new ruling; do NOT edit in place.
# ---------------------------------------------------------------------------

THRESHOLDS: dict[str, Any] = {
    # T1: altdata convergence — channels on a single HIGH-severity alert day
    "T1_MIN_CHANNELS": 3,
    "T1_SEVERITY": "high",
    # T2: call premium z — robust (median/MAD) against own 90d baseline
    "T2_Z_THRESHOLD": 2.0,
    "T2_BASELINE_DAYS": 90,
    "T2_MIN_OBS": 30,              # below this => young_series, witness absent
    # T3: GEX flip window (sessions)
    "T3_FLIP_WINDOW": 10,
    # T4: news bull_ratio z — robust (median/MAD) against own 90d baseline
    "T4_Z_THRESHOLD": 2.0,
    "T4_BASELINE_DAYS": 90,
    "T4_MIN_OBS": 30,
    # CUSUM: S+ = max(0, S+_prev + z_day - slack); fire threshold
    "CUSUM_SLACK": 0.5,            # k parameter: half-signal slack
    "CUSUM_FIRE_H": 5.0,           # h: threshold for PRIMED
    "CUSUM_FADING_DROP": 3.0,      # S+ decayed below this => FADING
    # PRIMED also requires >= this many witnesses present today
    "PRIMED_MIN_WITNESSES": 2,
    # Universe cap
    "UNIVERSE_CAP": 400,
    # Alert lookback for universe building (days)
    "ALERT_UNIVERSE_DAYS": 30,
}

# ---------------------------------------------------------------------------
# State enum values (ARMED/CONFIRMED-CANDIDATE reserved, not implemented)
# ---------------------------------------------------------------------------

STATE_DORMANT = "DORMANT"
STATE_PRIMED = "PRIMED"
STATE_FADING = "FADING"
# Reserved for later waves:
STATE_ARMED = "ARMED"
STATE_CONFIRMED_CANDIDATE = "CONFIRMED_CANDIDATE"

# ---------------------------------------------------------------------------
# Witness result shape
# ---------------------------------------------------------------------------


def _absent_witness(reason: str) -> dict:
    """NAR-R10: absent witness with reason (store missing/stale/young-series)."""
    return {"present": False, "magnitude": None, "stale": False, "reason": reason}


def _stale_witness(magnitude: float | None) -> dict:
    return {"present": False, "magnitude": magnitude, "stale": True, "reason": "stale"}


def _present_witness(magnitude: float | None) -> dict:
    return {"present": True, "magnitude": magnitude, "stale": False, "reason": None}


# ---------------------------------------------------------------------------
# Universe assembly
# ---------------------------------------------------------------------------


def _build_universe(data_root: Path, today: date) -> list[str]:
    """Build universe: mtf_upturn universe UNION alerts.jsonl trailing-30d tickers.

    Hard cap at THRESHOLDS['UNIVERSE_CAP']. Returns sorted list.
    """
    tickers: set[str] = set()

    # Part 1: mtf_upturn ALWAYS_INCLUDE (Mag7 + SPDRs + extra ETFs) + basket members
    try:
        from engine.mtf_upturn import ALWAYS_INCLUDE, _build_universe as _mtu_universe
        mtu_uni = _mtu_universe(data_root)
        tickers.update(mtu_uni.keys())
        tickers.update(ALWAYS_INCLUDE)
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence: mtf_upturn universe load failed: %s", e)
        # fallback: Mag7 only
        tickers.update({"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"})

    # Part 2: tickers appearing in alerts.jsonl within trailing 30d
    cutoff = today - timedelta(days=THRESHOLDS["ALERT_UNIVERSE_DAYS"])
    alerts_path = data_root / "altdata" / "alerts.jsonl"
    if alerts_path.exists():
        try:
            with alerts_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        ts_raw = row.get("ts", "")
                        ts_date = date.fromisoformat(ts_raw[:10]) if ts_raw else None
                        if ts_date and ts_date >= cutoff:
                            asset = row.get("asset", "").strip().upper()
                            if asset:
                                tickers.add(asset)
                    except (json.JSONDecodeError, ValueError):
                        continue
        except Exception as e:  # noqa: BLE001
            log.warning("flare_persistence: alerts.jsonl read failed: %s", e)
    else:
        log.warning("flare_persistence: alerts.jsonl absent at %s", alerts_path)

    # Apply cap — Mag7 get priority
    MAG7 = {"AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"}
    cap = THRESHOLDS["UNIVERSE_CAP"]
    if len(tickers) > cap:
        priority = sorted(t for t in tickers if t in MAG7)
        rest = sorted(t for t in tickers if t not in MAG7)
        combined = priority + rest
        tickers = set(combined[:cap])

    return sorted(tickers)


# ---------------------------------------------------------------------------
# T1 — altdata convergence
# ---------------------------------------------------------------------------


def _load_t1_index(data_root: Path) -> dict[str, dict[str, int]]:
    """Index alerts.jsonl as {ticker -> {date_str -> max_channel_count on HIGH days}}.

    Only counts HIGH-severity rows. Channel count = len(context.channels).
    """
    idx: dict[str, dict[str, int]] = {}
    alerts_path = data_root / "altdata" / "alerts.jsonl"
    if not alerts_path.exists():
        log.warning("flare_persistence T1: alerts.jsonl absent")
        return idx
    try:
        with alerts_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("severity", "").lower() != THRESHOLDS["T1_SEVERITY"]:
                    continue
                asset = row.get("asset", "").strip().upper()
                ts_raw = row.get("ts", "")
                if not asset or not ts_raw:
                    continue
                d_str = ts_raw[:10]
                channels = row.get("context", {}).get("channels", [])
                n_channels = len(channels)
                day_map = idx.setdefault(asset, {})
                if d_str not in day_map or n_channels > day_map[d_str]:
                    day_map[d_str] = n_channels
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence T1: alerts.jsonl read failed: %s", e)
    return idx


def _compute_t1(
    ticker: str,
    today: date,
    t1_index: dict[str, dict[str, int]],
) -> tuple[dict, int]:
    """Return (witness_dict, channel_count_today).

    magnitude = max channel count on any HIGH alert day for this ticker today.
    If no HIGH alert for this ticker today, present=False.
    """
    today_str = today.isoformat()
    day_map = t1_index.get(ticker, {})
    n_channels = day_map.get(today_str, 0)
    if n_channels >= THRESHOLDS["T1_MIN_CHANNELS"]:
        return _present_witness(float(n_channels)), n_channels
    return {"present": False, "magnitude": float(n_channels) if n_channels else None,
            "stale": False, "reason": "below_threshold" if n_channels else "no_alert"}, n_channels


# ---------------------------------------------------------------------------
# T2 — call premium z
# ---------------------------------------------------------------------------


def _robust_z(series: pd.Series, value: float) -> float | None:
    """Robust z-score: (value - median) / (MAD * 1.4826). Returns 0.0 if no dispersion."""
    arr = series.dropna().values
    if len(arr) == 0:
        return None
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    if mad > 1e-10:
        return float((value - med) / (mad * 1.4826))
    # fallback: std-based z; treat sub-epsilon std as zero
    std = float(np.std(arr))
    if std < 1e-10:
        return 0.0
    return float((value - med) / std)


def _compute_t2(
    ticker: str,
    today: date,
    data_root: Path,
) -> dict:
    """T2: net call premium z vs own trailing 90d baseline.

    Store: data/options_flow/summary_<TICKER>.parquet, column net_premium_mn.
    Index is datetime. PIT-safe: only use rows with date <= T-1 for baseline;
    today's row (if present) contributes the z reading.
    """
    p = data_root / "options_flow" / f"summary_{ticker}.parquet"
    if not p.exists():
        return _absent_witness("store_absent")
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        col = "net_premium_mn"
        if col not in df.columns:
            return _absent_witness("column_absent")
        # Determine today's value
        today_ts = pd.Timestamp(today)
        today_rows = df[df.index.date == today]
        if today_rows.empty:
            # No reading for today — check freshness
            last_date = df.index.max().date() if not df.empty else None
            if last_date is None or (today - last_date).days > 5:
                return _stale_witness(None)
            return _absent_witness("no_today_row")
        today_val = float(today_rows[col].iloc[-1])
        # Baseline: T-1 lookback, up to 90d
        cutoff = pd.Timestamp(today - timedelta(days=THRESHOLDS["T2_BASELINE_DAYS"]))
        baseline_rows = df[(df.index < today_ts) & (df.index >= cutoff)][col].dropna()
        if len(baseline_rows) < THRESHOLDS["T2_MIN_OBS"]:
            w = _absent_witness("young_series")
            w["magnitude"] = today_val
            return w
        z = _robust_z(baseline_rows, today_val)
        if z is None:
            return _absent_witness("zero_dispersion")
        if z >= THRESHOLDS["T2_Z_THRESHOLD"]:
            return _present_witness(round(z, 2))
        return {"present": False, "magnitude": round(z, 2), "stale": False, "reason": "below_threshold"}
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence T2 %s: %s", ticker, e)
        return _absent_witness("read_error")


# ---------------------------------------------------------------------------
# T3 — GEX flip
# ---------------------------------------------------------------------------


def _compute_t3(
    ticker: str,
    today: date,
    data_root: Path,
) -> dict:
    """T3: GEX regime == long AND sign-flipped within trailing FLIP_WINDOW sessions.

    Store: data/cboe/gex_<TICKER>.parquet, columns gamma_regime (str) + net_gex_bn (float).
    Flip = transition from 'short' to 'long' within the window.
    magnitude = net_gex_bn of today's row (display context).
    """
    p = data_root / "cboe" / f"gex_{ticker}.parquet"
    if not p.exists():
        return _absent_witness("store_absent")
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        today_ts = pd.Timestamp(today)
        # Use data up to and including today (PIT: today's CBoe GEX is observable same-day)
        df_pt = df[df.index <= today_ts]
        if df_pt.empty:
            return _absent_witness("no_data")
        # Check freshness
        last_date = df_pt.index.max().date()
        if (today - last_date).days > 5:
            return _stale_witness(None)
        # Require current regime = long
        if "gamma_regime" not in df_pt.columns:
            return _absent_witness("column_absent")
        cur_regime = str(df_pt["gamma_regime"].iloc[-1]).lower()
        if cur_regime != "long":
            return {"present": False, "magnitude": None, "stale": False, "reason": "not_long"}
        # Check flip within window: any row in last FLIP_WINDOW sessions was 'short'
        window = df_pt.iloc[-THRESHOLDS["T3_FLIP_WINDOW"]:]
        regimes = [str(v).lower() for v in window["gamma_regime"].values]
        flipped = "short" in regimes  # means transition from short -> long happened
        net_gex = float(df_pt["net_gex_bn"].iloc[-1]) if "net_gex_bn" in df_pt.columns else None
        if flipped:
            return _present_witness(round(net_gex, 3) if net_gex is not None else None)
        return {"present": False, "magnitude": net_gex, "stale": False, "reason": "no_recent_flip"}
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence T3 %s: %s", ticker, e)
        return _absent_witness("read_error")


# ---------------------------------------------------------------------------
# T4 — news bull ratio z
# ---------------------------------------------------------------------------


def _load_news_sentiment(data_root: Path) -> pd.DataFrame | None:
    """Load data/polygon/news_sentiment.parquet once; return or None."""
    p = data_root / "polygon" / "news_sentiment.parquet"
    if not p.exists():
        log.warning("flare_persistence T4: news_sentiment.parquet absent")
        return None
    try:
        df = pd.read_parquet(p)
        # snapshot_date is a string column; ensure consistent access
        return df
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence T4: news_sentiment load failed: %s", e)
        return None


def _compute_t4(
    ticker: str,
    today: date,
    news_df: pd.DataFrame | None,
) -> dict:
    """T4: bull_ratio z vs own trailing 90d baseline.

    Rows indexed by RangeIndex; columns: ticker, snapshot_date (str), bull_ratio.
    PIT-safe: baseline uses rows with snapshot_date < today.
    """
    if news_df is None:
        return _absent_witness("store_absent")
    try:
        t_rows = news_df[news_df["ticker"] == ticker].copy()
        if t_rows.empty:
            return _absent_witness("ticker_absent")
        # Parse snapshot_date to date
        t_rows = t_rows.copy()
        t_rows["_sd"] = pd.to_datetime(t_rows["snapshot_date"]).dt.date
        today_rows = t_rows[t_rows["_sd"] == today]
        if today_rows.empty:
            # Check freshness
            last_d = t_rows["_sd"].max()
            if (today - last_d).days > 5:
                return _stale_witness(None)
            return _absent_witness("no_today_row")
        today_val = float(today_rows["bull_ratio"].iloc[-1])
        # Baseline: T-1 and within 90d
        cutoff = today - timedelta(days=THRESHOLDS["T4_BASELINE_DAYS"])
        baseline = t_rows[(t_rows["_sd"] < today) & (t_rows["_sd"] >= cutoff)]["bull_ratio"].dropna()
        if len(baseline) < THRESHOLDS["T4_MIN_OBS"]:
            w = _absent_witness("young_series")
            w["magnitude"] = today_val
            return w
        z = _robust_z(baseline, today_val)
        if z is None:
            return _absent_witness("zero_dispersion")
        if z >= THRESHOLDS["T4_Z_THRESHOLD"]:
            return _present_witness(round(z, 2))
        return {"present": False, "magnitude": round(z, 2), "stale": False, "reason": "below_threshold"}
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence T4 %s: %s", ticker, e)
        return _absent_witness("read_error")


# ---------------------------------------------------------------------------
# CUSUM + state machine
# ---------------------------------------------------------------------------


def _witnesses_to_bitmap(witnesses: dict[str, dict]) -> int:
    """Return bitmask: T1=bit0, T2=bit1, T3=bit2, T4=bit3."""
    bits = 0
    if witnesses.get("T1", {}).get("present"):
        bits |= 1
    if witnesses.get("T2", {}).get("present"):
        bits |= 2
    if witnesses.get("T3", {}).get("present"):
        bits |= 4
    if witnesses.get("T4", {}).get("present"):
        bits |= 8
    return bits


def _count_present(witnesses: dict[str, dict]) -> int:
    return sum(1 for w in witnesses.values() if w.get("present"))


def _advance_cusum(
    s_plus_prev: float,
    n_present: int,
    trailing_mean: float,
    trailing_std: float,
) -> float:
    """Page-CUSUM S+ update. Masterplan §4.1: S+ = max(0, S+_prev + z_day - 0.5).

    z_day = (n_present_today - trailing_mean) / trailing_std; floor std at 0.5
    to avoid degenerate z on constant series.
    """
    std_floor = 0.5
    eff_std = max(trailing_std, std_floor)
    z_day = (n_present - trailing_mean) / eff_std
    return max(0.0, s_plus_prev + z_day - THRESHOLDS["CUSUM_SLACK"])


def _compute_state(
    s_plus: float,
    n_witnesses_present: int,
    prior_state: str,
) -> str:
    """State machine: DORMANT -> PRIMED -> FADING.

    PRIMED:  S+ >= CUSUM_FIRE_H AND n_witnesses_present >= PRIMED_MIN_WITNESSES.
    FADING:  (a) was PRIMED or FADING AND S+ >= CUSUM_FADING_DROP but PRIMED
                 conditions no longer met (s_plus < FIRE_H or witnesses < min), OR
             (b) was PRIMED AND S+ < CUSUM_FADING_DROP (same as before).
    DORMANT: s_plus < CUSUM_FADING_DROP AND PRIMED/FADING conditions not met.

    MAJOR fix: a PRIMED name that loses PRIMED conditions but retains
    s_plus >= CUSUM_FADING_DROP must land on FADING, not DORMANT.
    FADING with s_plus recovering >= FIRE_H and >= min witnesses re-enters PRIMED.
    """
    fire_h = THRESHOLDS["CUSUM_FIRE_H"]
    fading_drop = THRESHOLDS["CUSUM_FADING_DROP"]
    min_w = THRESHOLDS["PRIMED_MIN_WITNESSES"]

    # 1. PRIMED: full conditions met (from any prior state)
    if s_plus >= fire_h and n_witnesses_present >= min_w:
        return STATE_PRIMED

    # 2. FADING re-entry from PRIMED: S+ dropped below FADING_DROP (clear decay)
    if prior_state == STATE_PRIMED and s_plus < fading_drop:
        return STATE_FADING

    # 3. PRIMED conditions lost but S+ still >= FADING_DROP => FADING
    #    Covers: s_plus in [FADING_DROP, FIRE_H) or witnesses dropped below min
    #    while s_plus is still elevated.
    if prior_state in (STATE_PRIMED, STATE_FADING) and s_plus >= fading_drop:
        return STATE_FADING

    # 4. DORMANT: S+ < FADING_DROP (no sustained elevation)
    return STATE_DORMANT


# ---------------------------------------------------------------------------
# PIT history (append-only parquet)
# ---------------------------------------------------------------------------

_HIST_DIR = "flare_persistence"
_HIST_FILE = "state_hist.parquet"
_HIST_COLS = [
    "ticker", "date", "state", "s_plus",
    "witness_bitmap", "w_t1", "w_t2", "w_t3", "w_t4",
    "mag_t1", "mag_t2", "mag_t3", "mag_t4",
    "fetch_date",
]


def _hist_path(data_root: Path) -> Path:
    return data_root / _HIST_DIR / _HIST_FILE


def _load_hist(data_root: Path) -> pd.DataFrame:
    p = _hist_path(data_root)
    if not p.exists():
        return pd.DataFrame(columns=_HIST_COLS)
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("flare_persistence: hist load failed: %s", e)
        return pd.DataFrame(columns=_HIST_COLS)


def _append_hist(
    new_rows: list[dict],
    data_root: Path,
) -> None:
    """Append new_rows to state_hist.parquet. Idempotent per (ticker, date)."""
    if not new_rows:
        return
    p = _hist_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_hist(data_root)
    new_df = pd.DataFrame(new_rows, columns=_HIST_COLS)
    if existing.empty:
        combined = new_df
    else:
        # Dedup: keep existing rows, append only new (ticker, date) pairs
        existing_keys = set(
            zip(existing["ticker"].astype(str), existing["date"].astype(str))
        )
        new_df_filt = new_df[
            ~new_df.apply(
                lambda r: (str(r["ticker"]), str(r["date"])) in existing_keys, axis=1
            )
        ]
        combined = pd.concat([existing, new_df_filt], ignore_index=True)
    combined.to_parquet(p, index=False)


# ---------------------------------------------------------------------------
# Ledger-advance lane gate
# ---------------------------------------------------------------------------


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — mirrors mtf_upturn._ledger_advance_enabled exactly.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


# ---------------------------------------------------------------------------
# Prior CUSUM state loading
# ---------------------------------------------------------------------------


def _load_prior_states(data_root: Path, today: date | None = None) -> dict[str, dict]:
    """Return {ticker: {"s_plus": float, "state": str, "history": [n_present, ...]}} from hist.

    BLOCKER-2 fix: excludes rows where date == today (session date) so that a
    same-day rerun does not double-advance S+ off its own just-written output.
    Prior = most recent row with date < today.
    """
    hist = _load_hist(data_root)
    if hist.empty:
        return {}
    # Exclude today's rows so prior = last row with date < today
    if today is not None:
        today_str = today.isoformat()
        hist = hist[hist["date"].astype(str) != today_str]
    if hist.empty:
        return {}
    out: dict[str, dict] = {}
    for ticker, grp in hist.groupby("ticker"):
        grp = grp.sort_values("date")
        s_plus = float(grp["s_plus"].iloc[-1])
        state = str(grp["state"].iloc[-1])
        # Trailing n_present for mean/std computation: sum of bits set in bitmap
        n_present_hist = [bin(b).count("1") for b in grp["witness_bitmap"].astype(int)]
        out[str(ticker)] = {
            "s_plus": s_plus,
            "state": state,
            "n_present_hist": n_present_hist,
        }
    return out


# ---------------------------------------------------------------------------
# Main compute
# ---------------------------------------------------------------------------


def compute(
    data_root: Path | None = None,
    as_of: str | None = None,
) -> dict:
    """Compute flare_persistence.v1 for the full US universe.

    Returns the full site artifact. Never raises (NAR-R10 additive pattern).
    """
    try:
        return _compute_inner(data_root, as_of)
    except Exception as e:  # noqa: BLE001
        log.error("flare_persistence.compute crashed: %s", e)
        return {
            "schema": "flare_persistence.v1",
            "as_of": as_of or date.today().isoformat(),
            "universe_n": 0,
            "rows": [],
            "authority": AUTHORITY,
            "tier": "display",
            "error": str(e),
        }


def _compute_inner(data_root: Path | None, as_of: str | None) -> dict:
    t0 = time.time()

    from lib import config as _cfg
    if data_root is None:
        data_root = _cfg.data_dir()

    today = date.fromisoformat(as_of) if as_of else date.today()
    fetch_date_str = date.today().isoformat()

    # Load shared stores once
    t1_index = _load_t1_index(data_root)
    news_df = _load_news_sentiment(data_root)

    # Build universe
    universe = _build_universe(data_root, today)
    prior_states = _load_prior_states(data_root, today=today)

    rows_out: list[dict] = []
    hist_rows: list[dict] = []

    for ticker in universe:
        try:
            _process_ticker(
                ticker=ticker,
                today=today,
                fetch_date_str=fetch_date_str,
                data_root=data_root,
                t1_index=t1_index,
                news_df=news_df,
                prior_states=prior_states,
                rows_out=rows_out,
                hist_rows=hist_rows,
            )
        except Exception as e:  # noqa: BLE001 — NAR-R10: never crash pipeline
            log.warning("flare_persistence: %s compute failed: %s", ticker, e)

    # Append PIT history — ONLY on the nightly lane (COLLECT_LANE=nightly).
    # Intraday lanes (render.yml, earlyclose.yml) discard data/ writes per house law.
    if _ledger_advance_enabled():
        _append_hist(hist_rows, data_root)

    # Sort: PRIMED > FADING > DORMANT, then by s_plus desc
    _STATE_ORDER = {STATE_PRIMED: 0, STATE_FADING: 1, STATE_DORMANT: 2}
    rows_out.sort(key=lambda r: (_STATE_ORDER.get(r["state"], 9), -r["s_plus"]))

    elapsed = time.time() - t0
    n_primed = sum(1 for r in rows_out if r["state"] == STATE_PRIMED)
    n_fading = sum(1 for r in rows_out if r["state"] == STATE_FADING)
    log.info(
        "flare_persistence: universe=%d primed=%d fading=%d elapsed=%.1fs",
        len(universe), n_primed, n_fading, elapsed,
    )

    return {
        "schema": "flare_persistence.v1",
        "as_of": today.isoformat(),
        "fetch_date": fetch_date_str,
        "universe_n": len(universe),
        "elapsed_s": round(elapsed, 2),
        "rows": rows_out,
        "authority": AUTHORITY,
        "tier": "display",
        "thresholds_ref": "masterplan §4.1 — FROZEN pre-registration record",
    }


def _process_ticker(
    ticker: str,
    today: date,
    fetch_date_str: str,
    data_root: Path,
    t1_index: dict,
    news_df: pd.DataFrame | None,
    prior_states: dict,
    rows_out: list,
    hist_rows: list,
) -> None:
    """Compute per-ticker state and append to output lists."""
    # Compute witnesses
    t1_w, _t1_n = _compute_t1(ticker, today, t1_index)
    t2_w = _compute_t2(ticker, today, data_root)
    t3_w = _compute_t3(ticker, today, data_root)
    t4_w = _compute_t4(ticker, today, news_df)

    witnesses = {"T1": t1_w, "T2": t2_w, "T3": t3_w, "T4": t4_w}
    n_present = _count_present(witnesses)
    bitmap = _witnesses_to_bitmap(witnesses)

    # Retrieve prior CUSUM state
    prior = prior_states.get(ticker, {})
    s_plus_prev = prior.get("s_plus", 0.0)
    prior_state = prior.get("state", STATE_DORMANT)
    n_hist = prior.get("n_present_hist", [])

    # Compute trailing mean/std from history (sane floors)
    if len(n_hist) >= 3:
        trailing_mean = float(np.mean(n_hist))
        trailing_std = float(np.std(n_hist))
    else:
        # Cold start: assume uniform random (4 witnesses each p=0.5)
        trailing_mean = 2.0
        trailing_std = 1.0

    # Advance CUSUM
    s_plus = _advance_cusum(s_plus_prev, n_present, trailing_mean, trailing_std)

    # Compute state
    state = _compute_state(s_plus, n_present, prior_state)

    # Build output row
    def _mag(w: dict) -> float | None:
        return w.get("magnitude")

    row: dict[str, Any] = {
        "ticker": ticker,
        "state": state,
        "s_plus": round(s_plus, 3),
        "n_witnesses": n_present,
        "witnesses": witnesses,
        "as_of": today.isoformat(),
        "fetch_date": fetch_date_str,
    }
    rows_out.append(row)

    # PIT history row
    hist_rows.append({
        "ticker": ticker,
        "date": today.isoformat(),
        "state": state,
        "s_plus": round(s_plus, 3),
        "witness_bitmap": bitmap,
        "w_t1": int(t1_w.get("present", False)),
        "w_t2": int(t2_w.get("present", False)),
        "w_t3": int(t3_w.get("present", False)),
        "w_t4": int(t4_w.get("present", False)),
        "mag_t1": _mag(t1_w),
        "mag_t2": _mag(t2_w),
        "mag_t3": _mag(t3_w),
        "mag_t4": _mag(t4_w),
        "fetch_date": fetch_date_str,
    })


# ---------------------------------------------------------------------------
# Site artifact writer
# ---------------------------------------------------------------------------


def write_site_artifact(
    result: dict,
    site_root: Path | None = None,
) -> Path:
    """Write site/stockdata/flare_persistence.json. Returns written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "stockdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "flare_persistence.json"
    payload = json.dumps(result, separators=(",", ":"), default=str)
    out_path.write_text(payload + "\n", encoding="utf-8")
    log.info(
        "flare_persistence: wrote %s (%dKB, %d rows)",
        out_path, len(payload.encode()) // 1024, len(result.get("rows", [])),
    )
    return out_path
