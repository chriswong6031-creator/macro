"""engine/mtf_upturn.py — per-stock multi-timeframe upturn-confluence organ (TS-R3/TS-R4).

DISPLAY-ONLY. Authority block: tier=display, horizon_role=context/21d,
may_rank/gate/size/escalate = false.

Produces site/stockdata/mtf_upturn.json (schema: mtf_upturn.v1).
Forward ledger: data/mtf_upturn/ledger.jsonl (nightly-only, COLLECT_LANE gate).

Registered as an expected-NULL forward meter. Prior sector-level standalone
washout-to-turn constructions printed NULL (Oracle P8 P-W1/S-W3;
DO_NOT_REBUILD §2 'Washout × turn'); this is a different construction
(per-stock granularity, MACD/StochRSI K-of-N, no washout seed) shipped
display-tier; grading unit is the catalyst-day cohort (DT-R14), pre-declared
ruler 21d excess-vs-SPY; promotion question earliest 2027.

The 3D leg reuses signal_quality.signal_frame verbatim (house definition).
The weekly/2W legs reuse engine/htf_durability._biweekly_close for the
epoch-anchored PIT-safe 2W resampler.

DISPLAY-TIER LAW: no buy/act-now verbs. Fade base rate context is provided.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.htf_durability import _biweekly_close  # PIT-safe 2W resampler
from engine.signal_quality import signal_frame  # house 3D MACD+StochRSI (REUSE VERBATIM)
from engine.technicals import rsi  # Wilder RSI

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant — matches synapse registration)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

DISCLOSURE = (
    "Expected-NULL forward meter. Prior sector-level standalone washout-to-turn "
    "constructions printed NULL (Oracle P8 P-W1/S-W3; DO_NOT_REBUILD §2). "
    "Per-stock K-of-N construction accrues display-tier; grading unit = catalyst-day cohort "
    "(DT-R14); ruler = 21d excess-vs-SPY; promotion question earliest 2027."
)

# T+1 flip context (policy shock program, display law)
FADE_BASE_RATE = "58% fade at T+1 (n=26)"

# ---------------------------------------------------------------------------
# Universe constants
# ---------------------------------------------------------------------------

MAG7 = frozenset(["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"])

SPDR_SECTORS = frozenset([
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLP", "XLY",
    "XLU", "XLB", "XLRE", "XLC",
])

EXTRA_ETFS = frozenset(["SPY", "QQQ", "SOXX", "SMH"])

ALWAYS_INCLUDE = MAG7 | SPDR_SECTORS | EXTRA_ETFS

MIN_DAILY_BARS = 120  # skip if fewer than this

# ---------------------------------------------------------------------------
# Leg thresholds (FROZEN — amendments must go through TS-R3/TS-R4 ruling)
# ---------------------------------------------------------------------------

# daily MACD(12,26,9) histogram cross above 0 within last N sessions
D_MACD_WINDOW = 5

# weekly MACD cross window (completed weekly bars)
W_MACD_CROSS_WINDOW = 3
W_MACD_APPROACH_THRESHOLD = 0.20  # within 20% of zero on hist scale

# 2W MACD cross window (completed 2W bars)
W2_MACD_CROSS_WINDOW = 2

# K thresholds
STATE_WATCH_K = 2
STATE_CONFIRMED_K = 3  # AND (w_macd cross OR w2_macd)
HYSTERESIS_SESSIONS = 2  # CONFIRMED stays while K>=2 for up to 2 extra sessions

# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

_LEDGER_DIR = "mtf_upturn"
_LEDGER_FILE = "ledger.jsonl"


def _ledger_advance_enabled() -> bool:
    """True only when running in the nightly engine lane.

    Gate: COLLECT_LANE=nightly — mirrors basket_turn_watch.stamp_ledger pattern exactly.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _LEDGER_DIR / _LEDGER_FILE


def _load_ledger(data_root: Path | None = None) -> list[dict]:
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".mtf_upturn_ledger_tmp_")
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


def _stamp_ledger(
    transition_rows: list[dict],
    data_root: Path | None = None,
) -> int:
    """Append state-transition rows. Nightly-only (COLLECT_LANE gate).
    Idempotent: keep-first per (session, symbol).
    """
    if not _ledger_advance_enabled():
        log.debug("mtf_upturn._stamp_ledger: skipped (COLLECT_LANE != nightly)")
        return 0
    if not transition_rows:
        return 0
    try:
        rows = _load_ledger(data_root)
        existing = {(r.get("symbol"), r.get("session")) for r in rows}
        appended = 0
        for t in transition_rows:
            key = (t.get("symbol"), t.get("session"))
            if key in existing:
                continue
            rows.append(t)
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("mtf_upturn._stamp_ledger failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# Price loading
# ---------------------------------------------------------------------------

def _load_close(sym: str, data_root: Path | None = None) -> pd.Series | None:
    """Load daily close for sym. Priority: ohlcv/ -> stocks/ -> yahoo/.

    Returns a DatetimeIndex-indexed float Series or None if <MIN_DAILY_BARS.
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()

    def _try_ohlcv() -> pd.Series | None:
        p = root / "baskets" / "ohlcv" / f"{sym}.parquet"
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            return df["close"].astype(float)
        except Exception:
            return None

    def _try_stocks() -> pd.Series | None:
        p = root / "stocks" / f"{sym}.parquet"
        if not p.exists():
            return None
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            return df["close"].astype(float)
        except Exception:
            return None

    def _try_yahoo() -> pd.Series | None:
        from lib import config as _cfg
        # yahoo is under ROOT, not data_root
        yp = _cfg.ROOT / "data" / "yahoo" / f"{sym}.parquet"
        if not yp.exists():
            return None
        try:
            df = pd.read_parquet(yp)
            df.index = pd.to_datetime(df.index)
            # yahoo col is "close" (confirmed from inspection)
            col = "close" if "close" in df.columns else "close_price"
            return df[col].astype(float)
        except Exception:
            return None

    s = _try_ohlcv()
    if s is None:
        s = _try_stocks()
    if s is None:
        s = _try_yahoo()
    if s is None:
        return None
    s = s.dropna().sort_index()
    if len(s) < MIN_DAILY_BARS:
        return None
    return s


# ---------------------------------------------------------------------------
# MACD helpers (standard price MACD, 12/26/9)
# ---------------------------------------------------------------------------

def _price_macd_hist(c: pd.Series) -> pd.Series:
    """Standard price MACD(12,26,9) histogram."""
    ema12 = c.ewm(span=12, min_periods=12).mean()
    ema26 = c.ewm(span=26, min_periods=26).mean()
    line = ema12 - ema26
    sig = line.ewm(span=9, min_periods=9).mean()
    return line - sig


# ---------------------------------------------------------------------------
# Leg computation
# ---------------------------------------------------------------------------

def _leg_d_macd(close: pd.Series) -> bool:
    """Daily MACD(12,26,9) histogram crossed above 0 within last D_MACD_WINDOW sessions."""
    hist = _price_macd_hist(close)
    hist = hist.dropna()
    if len(hist) < D_MACD_WINDOW + 1:
        return False
    window = hist.iloc[-(D_MACD_WINDOW + 1):]
    # cross: any bar in window where hist > 0 AND prior bar <= 0
    for i in range(1, len(window)):
        if window.iloc[i] > 0 and window.iloc[i - 1] <= 0:
            return True
    return False


def _leg_d3_confluence(close: pd.Series) -> bool:
    """3D MACD+StochRSI confluence — reuse signal_frame from signal_quality VERBATIM.

    Returns True if the last 3D bar shows CB (buy signal) or revBuy (reversal buy),
    matching the house definition exactly.
    """
    sf = signal_frame(close)
    if sf.empty:
        return False
    # CB or revBuy on last available 3D bar
    last = sf.iloc[-1]
    return bool(last.get("CB", False)) or bool(last.get("revBuy", False))


def _leg_w_macd(close: pd.Series) -> str:
    """Weekly MACD status: 'cross' | 'approaching' | 'none'.

    cross: MACD(12,26,9) hist crossed above 0 within last W_MACD_CROSS_WINDOW
           completed weekly bars.
    approaching: hist < 0 AND rising for >=3 weekly bars AND within 20% of 0
                 (approaching does NOT count toward K — display context only).
    none: neither.

    Uses completed weekly bars (W-FRI resample).
    """
    weekly = close.resample("W-FRI").last().dropna()
    if len(weekly) < W_MACD_CROSS_WINDOW + 2:
        return "none"
    hist = _price_macd_hist(weekly).dropna()
    if len(hist) < W_MACD_CROSS_WINDOW + 1:
        return "none"

    # Check cross within last W_MACD_CROSS_WINDOW completed bars
    window = hist.iloc[-(W_MACD_CROSS_WINDOW + 1):]
    for i in range(1, len(window)):
        if window.iloc[i] > 0 and window.iloc[i - 1] <= 0:
            return "cross"

    # Check approaching: hist<0, rising 3 bars, within 20% of zero range
    if len(hist) >= 4:
        h = hist.dropna()
        rising = (h.iloc[-1] < 0 and
                  h.iloc[-1] > h.iloc[-2] > h.iloc[-3])
        if rising:
            # within 20% of zero: |hist[-1]| < 20% of |min(hist over last 20 bars)|
            recent_range = h.iloc[-20:].abs().max()
            if recent_range > 0 and abs(float(h.iloc[-1])) < W_MACD_APPROACH_THRESHOLD * recent_range:
                return "approaching"

    return "none"


def _leg_w2_macd(close: pd.Series) -> bool:
    """2W MACD hist crossed above 0 within last W2_MACD_CROSS_WINDOW completed 2W bars.

    Uses _biweekly_close (epoch-anchored PIT-safe resampler from htf_durability).
    """
    biweekly = _biweekly_close(close)
    if len(biweekly) < W2_MACD_CROSS_WINDOW + 2:
        return False
    hist = _price_macd_hist(biweekly).dropna()
    if len(hist) < W2_MACD_CROSS_WINDOW + 1:
        return False

    window = hist.iloc[-(W2_MACD_CROSS_WINDOW + 1):]
    for i in range(1, len(window)):
        if window.iloc[i] > 0 and window.iloc[i - 1] <= 0:
            return True
    return False


def _monthly_phase(close: pd.Series) -> str:
    """Monthly phase from cycles._tf_state pattern — display context only.

    Returns a string like 'macd_pos/falling' or 'macd_neg/approaching_up'.
    Uses monthly (M) resampled close.
    """
    try:
        monthly = close.resample("ME").last().dropna()
        if len(monthly) < 10:
            return "insufficient_history"
        hist = _price_macd_hist(monthly).dropna()
        if len(hist) < 4:
            return "insufficient_history"
        last_h = float(hist.iloc[-1])
        prev_h = float(hist.iloc[-2])
        macd_pos = last_h > 0
        rising = last_h > prev_h
        prefix = "macd_pos" if macd_pos else "macd_neg"
        suffix = "rising" if rising else "falling"
        return f"{prefix}/{suffix}"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Per-symbol compute
# ---------------------------------------------------------------------------

def _compute_symbol(
    sym: str,
    close: pd.Series,
    prior_state: str | None,
    prior_sessions_held: int,
) -> dict:
    """Compute all legs + state for a single symbol.

    prior_state: the previous session's state (for hysteresis).
    prior_sessions_held: how many sessions the prior state has been held post-first-drop
                         (for hysteresis countdown).

    Returns a dict with all leg values, K, state.
    """
    # Compute legs
    d_macd = _leg_d_macd(close)
    d3_conf = _leg_d3_confluence(close)
    w_macd_status = _leg_w_macd(close)
    w_macd_cross = (w_macd_status == "cross")
    w2_macd = _leg_w2_macd(close)
    month_phase = _monthly_phase(close)

    # K = count of TRUE among {d_macd, d3_confluence, w_macd cross only, w2_macd}
    # 'approaching' does NOT count
    k = sum([d_macd, d3_conf, w_macd_cross, w2_macd])

    # Raw state assignment
    raw_state = "NONE"
    if k >= STATE_CONFIRMED_K and (w_macd_cross or w2_macd):
        raw_state = "UPTURN_CONFIRMED"
    elif k >= STATE_WATCH_K:
        raw_state = "UPTURN_WATCH"

    # Hysteresis: CONFIRMED stays while K>=2 for up to HYSTERESIS_SESSIONS extra sessions
    state = raw_state
    if (prior_state == "UPTURN_CONFIRMED"
            and raw_state != "UPTURN_CONFIRMED"
            and k >= STATE_WATCH_K
            and prior_sessions_held < HYSTERESIS_SESSIONS):
        state = "UPTURN_CONFIRMED"

    return {
        "state": state,
        "k": k,
        "legs": {
            "d_macd": d_macd,
            "d3_confluence": d3_conf,
            "w_macd": w_macd_status,  # "cross" | "approaching" | "none"
            "w2_macd": w2_macd,
        },
        "monthly_phase": month_phase,
    }


# ---------------------------------------------------------------------------
# Universe assembly
# ---------------------------------------------------------------------------

def _build_universe(data_root: Path | None = None) -> dict[str, list[str]]:
    """Return {symbol: [basket_id, ...]} for the full universe.

    Includes all US basket members + ALWAYS_INCLUDE (Mag7, SPDRs, ETFs).
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    mp = root / "baskets" / "membership.json"

    ticker_baskets: dict[str, list[str]] = {}

    if mp.exists():
        try:
            raw = json.loads(mp.read_text())
            baskets = raw.get("baskets") or {}
            for bid, basket in baskets.items():
                for m in (basket.get("members") or []):
                    if m.get("removed") is not None:
                        continue
                    tk = (m.get("ticker") or "").strip().upper()
                    if tk:
                        ticker_baskets.setdefault(tk, []).append(bid)
        except Exception as e:
            log.warning("mtf_upturn: membership.json load failed: %s", e)

    # Ensure ALWAYS_INCLUDE are present
    for sym in ALWAYS_INCLUDE:
        if sym not in ticker_baskets:
            basket_ids: list[str] = []
            if sym in MAG7:
                basket_ids.append("mag7")
            if sym in SPDR_SECTORS:
                basket_ids.append("spdr_sector")
            if sym in EXTRA_ETFS:
                basket_ids.append("index_etf")
            ticker_baskets[sym] = basket_ids

    return ticker_baskets


# ---------------------------------------------------------------------------
# Prior-state ledger for hysteresis
# ---------------------------------------------------------------------------

def _load_prior_states(data_root: Path | None = None) -> dict[str, dict]:
    """Load previous session states from ledger for hysteresis computation.

    Returns {symbol: {"state": str, "sessions_held": int}}.
    The "sessions_held" counts how many sessions the state has been held
    since it first could have dropped (used for CONFIRMED hysteresis).
    """
    rows = _load_ledger(data_root)
    if not rows:
        return {}
    # Most recent row per symbol
    prior: dict[str, dict] = {}
    for row in reversed(rows):
        sym = row.get("symbol")
        if sym and sym not in prior:
            prior[sym] = {
                "state": row.get("state", "NONE"),
                "sessions_held": row.get("hysteresis_sessions_held", 0),
            }
    return prior


# ---------------------------------------------------------------------------
# Main compute
# ---------------------------------------------------------------------------

def compute(
    data_root: Path | None = None,
    as_of: str | None = None,
) -> dict:
    """Compute mtf_upturn.v1 for the full US universe.

    Returns the full site artifact. Never raises (additive pattern).
    """
    try:
        return _compute_inner(data_root, as_of)
    except Exception as e:  # noqa: BLE001
        log.error("mtf_upturn.compute crashed: %s", e)
        return {
            "schema": "mtf_upturn.v1",
            "as_of": as_of or date.today().isoformat(),
            "universe_n": 0,
            "skipped_n": 0,
            "tickers": {},
            "cohort": {"confirmed": [], "watch": []},
            "authority": AUTHORITY,
            "tier": "display",
            "error": str(e),
        }


def _compute_inner(data_root: Path | None, as_of: str | None) -> dict:
    t0 = time.time()

    universe = _build_universe(data_root)
    prior_states = _load_prior_states(data_root)

    universe_n = 0
    skipped_n = 0
    tickers_out: dict[str, Any] = {}
    transition_rows: list[dict] = []
    confirmed_list: list[str] = []
    watch_list: list[str] = []

    # Track "since" date — last date state changed TO current state
    # We read from ledger: if prior state == current state, carry forward "since"
    prior_since: dict[str, str] = {}
    for row in _load_ledger(data_root):
        sym = row.get("symbol")
        if sym and row.get("state") not in (None, "NONE"):
            prior_since.setdefault(sym, row.get("session", ""))

    for sym, basket_ids in sorted(universe.items()):
        close = _load_close(sym, data_root)
        if close is None:
            skipped_n += 1
            log.debug("mtf_upturn: skipped %s (insufficient data)", sym)
            continue

        universe_n += 1

        # as_of = last bar date from the series (UTC-date law)
        sym_asof = str(close.index[-1].date())
        if as_of is None:
            # Use max bar date across universe (set after first symbol)
            pass

        prior = prior_states.get(sym, {})
        prior_state = prior.get("state", "NONE")
        prior_held = prior.get("sessions_held", 0)

        try:
            result = _compute_symbol(sym, close, prior_state, prior_held)
        except Exception as e:
            log.debug("mtf_upturn: %s compute failed: %s", sym, e)
            continue

        state = result["state"]
        k = result["k"]

        # Compute "since"
        if state == "NONE":
            since_date = None
        elif state == prior_state:
            since_date = prior_since.get(sym, sym_asof)
        else:
            since_date = sym_asof

        # Hysteresis sessions held tracking
        if state == "UPTURN_CONFIRMED" and prior_state == "UPTURN_CONFIRMED" and result["legs"].get("w_macd") != "cross" and not result["legs"].get("w2_macd"):
            # We're in hysteresis hold — increment sessions held
            new_held = prior_held + 1
        else:
            new_held = 0

        # State transition — record in ledger if state is non-NONE
        if state != "NONE":
            confirmed_list.append(sym) if state == "UPTURN_CONFIRMED" else watch_list.append(sym)

            # Only include in tickers output if state != NONE, plus always include ALWAYS_INCLUDE
            row_out = {
                "state": state,
                "k": k,
                "legs": result["legs"],
                "monthly_phase": result["monthly_phase"],
                "since": since_date,
                "basket_ids": basket_ids,
            }
            tickers_out[sym] = row_out

            # Record ledger transition
            transition_rows.append({
                "session": sym_asof,
                "symbol": sym,
                "state": state,
                "k": k,
                "legs": result["legs"],
                "baskets": basket_ids,
                "hysteresis_sessions_held": new_held,
            })
        elif sym in ALWAYS_INCLUDE:
            # Always include in output even if NONE
            tickers_out[sym] = {
                "state": "NONE",
                "k": k,
                "legs": result["legs"],
                "monthly_phase": result["monthly_phase"],
                "since": None,
                "basket_ids": basket_ids,
            }

    # Determine as_of from bar dates
    computed_asof = as_of
    if computed_asof is None:
        # Derive from actual data — find max last-bar date across sampled symbols
        # Use a quick scan of a few key symbols
        for sym in ["SPY", "AAPL", "MSFT", "QQQ"]:
            c = _load_close(sym, data_root)
            if c is not None:
                d = str(c.index[-1].date())
                if computed_asof is None or d > computed_asof:
                    computed_asof = d
        if computed_asof is None:
            computed_asof = date.today().isoformat()

    # Stamp forward ledger (nightly-only)
    _stamp_ledger(transition_rows, data_root)

    elapsed = time.time() - t0
    log.info(
        "mtf_upturn: universe=%d skipped=%d confirmed=%d watch=%d elapsed=%.1fs",
        universe_n, skipped_n, len(confirmed_list), len(watch_list), elapsed,
    )

    return {
        "schema": "mtf_upturn.v1",
        "as_of": computed_asof,
        "universe_n": universe_n,
        "skipped_n": skipped_n,
        "elapsed_s": round(elapsed, 2),
        "tickers": tickers_out,
        "cohort": {
            "confirmed": sorted(confirmed_list),
            "watch": sorted(watch_list),
        },
        "authority": AUTHORITY,
        "tier": "display",
        "disclosure": DISCLOSURE,
        "fade_base_rate": FADE_BASE_RATE,
    }


# ---------------------------------------------------------------------------
# Site artifact writer
# ---------------------------------------------------------------------------

_MAX_BYTES = 500_000  # 500KB cap


def write_site_artifact(
    result: dict,
    site_root: Path | None = None,
) -> Path:
    """Write site/stockdata/mtf_upturn.json. Returns written path.

    If payload exceeds 500KB, prune NONE-state non-ALWAYS_INCLUDE tickers
    (they were excluded above, but belt-and-suspenders check).
    """
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "stockdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mtf_upturn.json"

    payload = json.dumps(result, separators=(",", ":"), default=str)
    if len(payload.encode()) > _MAX_BYTES:
        log.warning(
            "mtf_upturn: payload %dKB > 500KB cap — pruning NONE-state tickers",
            len(payload.encode()) // 1024,
        )
        pruned = dict(result)
        pruned["tickers"] = {
            sym: v for sym, v in result.get("tickers", {}).items()
            if v.get("state") != "NONE" or sym in ALWAYS_INCLUDE
        }
        payload = json.dumps(pruned, separators=(",", ":"), default=str)

    out_path.write_text(payload + "\n", encoding="utf-8")
    log.info("mtf_upturn: wrote %s (%dKB)", out_path, len(payload.encode()) // 1024)
    return out_path
