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

    Returns a dict with all leg values, K, state, raw_state, htf_coverage.

    htf_coverage: True when the series has enough bars for weekly AND 2W MACD to be
    non-NaN (effective floor ~350 daily bars for 2W, ~245 for weekly). When False,
    UPTURN_CONFIRMED is structurally unreachable for this symbol (requires an HTF
    cross), and absence of w_macd/w2_macd cross should NOT be read as bearish — it is
    a data-length limitation. Display this flag in U3 so the dashboard does not
    misrepresent absence-of-signal as a bearish signal.
    """
    # Compute legs
    d_macd = _leg_d_macd(close)
    d3_conf = _leg_d3_confluence(close)
    w_macd_status = _leg_w_macd(close)
    w_macd_cross = (w_macd_status == "cross")
    w2_macd = _leg_w2_macd(close)
    month_phase = _monthly_phase(close)

    # HTF coverage flag: assess whether the 2W MACD can be non-NaN.
    # Weekly MACD needs ~35 weekly bars (~245 daily); 2W needs ~35 2W bars (~350 daily).
    # Use the biweekly bar count as the binding constraint (stricter).
    try:
        biweekly = _biweekly_close(close)
        w2_hist = _price_macd_hist(biweekly).dropna()
        htf_coverage = len(w2_hist) >= W2_MACD_CROSS_WINDOW + 1
    except Exception:
        htf_coverage = False

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
        "raw_state": raw_state,  # pre-hysteresis state (used for held-counter tracking)
        "k": k,
        "legs": {
            "d_macd": d_macd,
            "d3_confluence": d3_conf,
            "w_macd": w_macd_status,  # "cross" | "approaching" | "none"
            "w2_macd": w2_macd,
        },
        "monthly_phase": month_phase,
        "htf_coverage": htf_coverage,
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
    max_bar_date: str | None = None  # max last-bar date across loaded symbols (for as_of)

    # Track "since" date — last date state changed TO current state.
    # NOTE: "since" is nightly-anchored — it reads from the nightly ledger, so in
    # intraday builds (COLLECT_LANE != nightly) it may lag the true transition by up to
    # one session. This is documented/acceptable for a display-tier field.
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
        # Track max across all loaded symbols — used for computed_asof below
        if max_bar_date is None or sym_asof > max_bar_date:
            max_bar_date = sym_asof

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

        # Hysteresis sessions held tracking.
        # Increment whenever state is CONFIRMED but raw_state is not (i.e. hysteresis is
        # actively holding the state). This is the correct invariant regardless of which
        # legs are set — avoids prior bug where a persistent cross leg kept new_held at 0
        # and allowed indefinite CONFIRMED hold past the HYSTERESIS_SESSIONS cap.
        raw_state = result["raw_state"]
        if state == "UPTURN_CONFIRMED" and raw_state != "UPTURN_CONFIRMED":
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
                "htf_coverage": result["htf_coverage"],
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
                "htf_coverage": result["htf_coverage"],
            }

    # Determine as_of from bar dates.
    # Use max_bar_date tracked during the main loop — no redundant re-loads of 4
    # hardcoded symbols. Falls back to date.today() only when universe is empty.
    computed_asof = as_of
    if computed_asof is None:
        if max_bar_date is not None:
            computed_asof = max_bar_date
        else:
            log.warning("mtf_upturn: universe empty — falling back to date.today() for as_of")
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
# CN lane — universe assembly, price loading, ledger, compute, artifact writer
# ---------------------------------------------------------------------------

# CN ledger gating: write only in the asia lane (mirrors CNPL-R8).
_CN_LEDGER_DIR = "mtf_upturn_cn"
_CN_LEDGER_FILE = "ledger.jsonl"

# CN universe cap (budget constraint — W8-R7)
CN_UNIVERSE_CAP = 400

DISCLOSURE_CN = (
    "Expected-NULL forward meter (CN lane). Per-stock K-of-N construction accrues "
    "display-tier; same legs/thresholds as US organ (TS-R3/TS-R4). "
    "Promotion question for CN analog earliest 2027 (mirrors US TS-R3/TS-R4 ruling). "
    "Prior sector-level standalone washout-to-turn constructions printed NULL "
    "(Oracle P8 P-W1/S-W3; DO_NOT_REBUILD §2 'Washout x turn'); this is a "
    "different construction (per-stock granularity, no washout seed)."
)


def _cn_ledger_advance_enabled() -> bool:
    """True only when running in the asia engine lane (CN_LANE=asia)."""
    return os.environ.get("CN_LANE", "").lower() == "asia"


def _cn_ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _CN_LEDGER_DIR / _CN_LEDGER_FILE


def _cn_stamp_ledger(
    transition_rows: list[dict],
    data_root: Path | None = None,
) -> int:
    """Append CN state-transition rows. Asia-lane-only (CN_LANE=asia gate).

    Idempotent: keep-first per (session, symbol).
    """
    if not _cn_ledger_advance_enabled():
        log.debug("mtf_upturn_cn._cn_stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    if not transition_rows:
        return 0
    try:
        p = _cn_ledger_path(data_root)
        existing_rows: list[dict] = []
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line:
                    try:
                        existing_rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        existing = {(r.get("symbol"), r.get("session")) for r in existing_rows}
        appended = 0
        for t in transition_rows:
            key = (t.get("symbol"), t.get("session"))
            if key in existing:
                continue
            existing_rows.append(t)
            existing.add(key)
            appended += 1
        if appended:
            p.parent.mkdir(parents=True, exist_ok=True)
            content = "\n".join(json.dumps(r, default=str) for r in existing_rows)
            if content:
                content += "\n"
            fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".cn_ledger_tmp_")
            try:
                with os.fdopen(fd, "w") as fh:
                    fh.write(content)
                os.replace(tmp, p)
            except Exception:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("mtf_upturn_cn._cn_stamp_ledger failed: %s", e)
        return 0


def _cn_load_prior_states(data_root: Path | None = None) -> dict[str, dict]:
    """Load previous CN session states from ledger for hysteresis."""
    p = _cn_ledger_path(data_root)
    if not p.exists():
        return {}
    rows: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not rows:
        return {}
    prior: dict[str, dict] = {}
    for row in reversed(rows):
        sym = row.get("symbol")
        if sym and sym not in prior:
            prior[sym] = {
                "state": row.get("state", "NONE"),
                "sessions_held": row.get("hysteresis_sessions_held", 0),
            }
    return prior


def _cn_load_close(
    sym: str,
    data_root: Path | None = None,
    panel: "pd.DataFrame | None" = None,
) -> "pd.Series | None":
    """Load CN daily close for sym.

    Priority order (R6.md §1 fallback chain):
    1. data/china_stocks_raw/<sym>.parquet (per-ticker OHLCV — primary)
    2. data/china_search/closes.parquet panel column (tracked; works in
       worktrees/CI since it is git-tracked)

    Returns a DatetimeIndex-indexed float Series or None if < MIN_DAILY_BARS.
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()

    # Path 1: per-ticker parquet in china_stocks_raw
    raw_path = root / "china_stocks_raw" / f"{sym}.parquet"
    if raw_path.exists():
        try:
            df = pd.read_parquet(raw_path)
            df.index = pd.to_datetime(df.index)
            col = "close" if "close" in df.columns else None
            if col is None:
                for c in df.columns:
                    if "close" in c.lower():
                        col = c
                        break
            if col:
                s = df[col].astype(float).dropna().sort_index()
                if len(s) >= MIN_DAILY_BARS:
                    return s
        except Exception as e:
            log.debug("cn_load_close raw_path failed for %s: %s", sym, e)

    # Path 2: closes.parquet panel column
    if panel is not None and sym in panel.columns:
        try:
            s = panel[sym].dropna().sort_index()
            s = s.astype(float)
            if len(s) >= MIN_DAILY_BARS:
                return s
        except Exception as e:
            log.debug("cn_load_close panel failed for %s: %s", sym, e)
        return None

    # Try loading panel from disk as last resort
    panel_path = root / "china_search" / "closes.parquet"
    if panel_path.exists():
        try:
            _panel = pd.read_parquet(panel_path)
            _panel.index = pd.to_datetime(_panel.index)
            if sym in _panel.columns:
                s = _panel[sym].dropna().sort_index().astype(float)
                if len(s) >= MIN_DAILY_BARS:
                    return s
        except Exception as e:
            log.debug("cn_load_close panel_path failed for %s: %s", sym, e)

    return None


def _build_cn_universe(
    data_root: Path | None = None,
) -> dict[str, list[str]]:
    """Assemble the CN universe: board buy + ripening + THS act-now theme members.

    Priority order (deduped, capped at CN_UNIVERSE_CAP):
    1. Board buy tickers (ENTRY + RAN_LATE from china_standouts.json)
    2. Ripening tickers (READY + BASING from ripening shelf)
    3. THS theme members of act-now themes (from baskets.json theme_intel.act_now.buy)

    Returns {ticker: [source_tag, ...]}.
    """
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    site_cfg = config.load().get("storage", {})
    site_dir = Path(site_cfg.get("site_dir", "site"))

    ticker_sources: dict[str, list[str]] = {}

    def _add(tickers: list[str], tag: str) -> None:
        for t in tickers:
            t = t.strip()
            if not t:
                continue
            ticker_sources.setdefault(t, [])
            if tag not in ticker_sources[t]:
                ticker_sources[t].append(tag)

    # 1. Board buy + ripening from china_standouts.json
    # Primary path: site/factordata/china_standouts.json (written by build_china_library.main())
    # Fallback: site/chinastockdata/china_standouts.json (legacy path compatibility)
    standouts_path = site_dir / "factordata" / "china_standouts.json"
    if not standouts_path.exists():
        standouts_path = site_dir / "chinastockdata" / "china_standouts.json"
    if standouts_path.exists():
        try:
            sd = json.loads(standouts_path.read_text())
            buy_tickers = [r.get("ticker") for r in (sd.get("buy") or []) if r.get("ticker")]
            _add([t for t in buy_tickers if t], "board_buy")
            rip_tickers = [r.get("ticker") for r in (sd.get("ripening") or []) if r.get("ticker")]
            _add([t for t in rip_tickers if t], "ripening")
            rip_fall = [r.get("ticker") for r in (sd.get("ripening_falling") or []) if r.get("ticker")]
            _add([t for t in rip_fall if t], "ripening_falling")
        except Exception as e:
            log.warning("_build_cn_universe: standouts read failed: %s", e)
    else:
        log.debug("_build_cn_universe: china_standouts.json absent — board tickers skipped")

    # 2. THS theme members for act-now themes (from baskets.json)
    baskets_path = site_dir / "chinabasketdata" / "baskets.json"
    if baskets_path.exists() and len(ticker_sources) < CN_UNIVERSE_CAP:
        try:
            bd = json.loads(baskets_path.read_text())
            ti = bd.get("theme_intel") or {}
            an = ti.get("act_now") or {}
            act_now_ids: set[str] = set()
            for item in (an.get("buy") or []):
                iid = item.get("id")
                if iid:
                    act_now_ids.add(iid)
            # THS baskets with matching id
            baskets_ths_path = site_dir / "chinabasketdata" / "baskets_ths.json"
            if baskets_ths_path.exists() and act_now_ids:
                ths_data = json.loads(baskets_ths_path.read_text())
                for basket in (ths_data.get("baskets") or []):
                    bid = basket.get("id", "")
                    if bid in act_now_ids:
                        for m in (basket.get("members") or []):
                            sym = m.get("symbol", "").strip()
                            if sym:
                                _add([sym], f"ths_{bid}")
            # Also include curated baskets in act-now
            for basket in (bd.get("baskets") or []):
                if basket.get("id") in act_now_ids:
                    for m in (basket.get("members") or []):
                        sym = m.get("symbol", "").strip()
                        if sym:
                            _add([sym], f"basket_{basket['id']}")
        except Exception as e:
            log.warning("_build_cn_universe: baskets read failed: %s", e)

    # Cap at CN_UNIVERSE_CAP (priority: board_buy first, then ripening, then theme)
    if len(ticker_sources) > CN_UNIVERSE_CAP:
        # Sort by priority: board_buy first, ripening second, theme third
        def _priority(item: tuple) -> int:
            tags = item[1]
            if "board_buy" in tags:
                return 0
            if "ripening" in tags or "ripening_falling" in tags:
                return 1
            return 2
        sorted_items = sorted(ticker_sources.items(), key=_priority)
        ticker_sources = dict(sorted_items[:CN_UNIVERSE_CAP])

    return ticker_sources


def compute_cn(
    data_root: Path | None = None,
    as_of: str | None = None,
    panel: "pd.DataFrame | None" = None,
) -> dict:
    """Compute mtf_upturn_cn.v1 for the CN universe.

    Returns the full site artifact. Never raises (additive pattern).
    """
    try:
        return _compute_cn_inner(data_root, as_of, panel)
    except Exception as e:  # noqa: BLE001
        log.error("mtf_upturn_cn.compute_cn crashed: %s", e)
        return {
            "schema": "mtf_upturn_cn.v1",
            "as_of": as_of or date.today().isoformat(),
            "universe_n": 0,
            "skipped_n": 0,
            "members": {},
            "cohort": {"confirmed": [], "watch": []},
            "authority": AUTHORITY,
            "tier": "display",
            "disclosure": DISCLOSURE_CN,
            "error": str(e),
        }


def _compute_cn_inner(
    data_root: Path | None,
    as_of: str | None,
    panel: "pd.DataFrame | None",
) -> dict:
    t0 = time.time()

    universe = _build_cn_universe(data_root)
    prior_states = _cn_load_prior_states(data_root)

    # Lazily load closes panel once — reused across all fallbacks
    if panel is None:
        from lib import config
        root = data_root if data_root is not None else config.data_dir()
        panel_path = root / "china_search" / "closes.parquet"
        if panel_path.exists():
            try:
                panel = pd.read_parquet(panel_path)
                panel.index = pd.to_datetime(panel.index)
                log.debug("mtf_upturn_cn: loaded closes panel (%d rows x %d cols)",
                          len(panel), len(panel.columns))
            except Exception as e:
                log.warning("mtf_upturn_cn: panel load failed: %s", e)
                panel = None

    universe_n = 0
    skipped_n = 0
    members_out: dict[str, Any] = {}
    transition_rows: list[dict] = []
    confirmed_list: list[str] = []
    watch_list: list[str] = []
    max_bar_date: str | None = None

    for sym, source_tags in sorted(universe.items()):
        close = _cn_load_close(sym, data_root, panel)
        if close is None:
            skipped_n += 1
            log.debug("mtf_upturn_cn: skipped %s (insufficient data)", sym)
            continue

        universe_n += 1
        sym_asof = str(close.index[-1].date())
        if max_bar_date is None or sym_asof > max_bar_date:
            max_bar_date = sym_asof

        prior = prior_states.get(sym, {})
        prior_state = prior.get("state", "NONE")
        prior_held = prior.get("sessions_held", 0)

        try:
            result = _compute_symbol(sym, close, prior_state, prior_held)
        except Exception as e:
            log.debug("mtf_upturn_cn: %s compute failed: %s", sym, e)
            continue

        state = result["state"]
        k = result["k"]
        raw_state = result["raw_state"]

        if state == "UPTURN_CONFIRMED":
            confirmed_list.append(sym)
        elif state == "UPTURN_WATCH":
            watch_list.append(sym)

        # Hysteresis held counter
        if state == "UPTURN_CONFIRMED" and raw_state != "UPTURN_CONFIRMED":
            new_held = prior_held + 1
        else:
            new_held = 0

        # Output record for all non-NONE states
        if state != "NONE":
            members_out[sym] = {
                "state": state,
                "k": k,
                "legs": result["legs"],
                "monthly_phase": result["monthly_phase"],
                "htf_coverage": result["htf_coverage"],
                "sources": source_tags,
            }
            transition_rows.append({
                "session": sym_asof,
                "symbol": sym,
                "state": state,
                "k": k,
                "legs": result["legs"],
                "sources": source_tags,
                "hysteresis_sessions_held": new_held,
            })

    computed_asof = as_of
    if computed_asof is None:
        if max_bar_date is not None:
            computed_asof = max_bar_date
        else:
            log.warning("mtf_upturn_cn: universe empty — falling back to date.today()")
            computed_asof = date.today().isoformat()

    # Stamp forward ledger (asia-lane only)
    _cn_stamp_ledger(transition_rows, data_root)

    elapsed = time.time() - t0
    log.info(
        "mtf_upturn_cn: universe=%d skipped=%d confirmed=%d watch=%d elapsed=%.1fs",
        universe_n, skipped_n, len(confirmed_list), len(watch_list), elapsed,
    )

    if elapsed > 90:
        log.warning(
            "mtf_upturn_cn: elapsed %.1fs > 90s budget — consider reducing universe "
            "(board_buy=%d priority names; reduce theme members if needed)",
            elapsed,
            sum(1 for tags in universe.values() if "board_buy" in tags),
        )

    return {
        "schema": "mtf_upturn_cn.v1",
        "as_of": computed_asof,
        "universe_n": universe_n,
        "skipped_n": skipped_n,
        "elapsed_s": round(elapsed, 2),
        "members": members_out,
        "cohort": {
            "confirmed": sorted(confirmed_list),
            "watch": sorted(watch_list),
        },
        "authority": AUTHORITY,
        "tier": "display",
        "disclosure": DISCLOSURE_CN,
    }


def write_cn_site_artifact(
    result: dict,
    site_root: Path | None = None,
) -> Path:
    """Write site/chinastockdata/mtf_upturn_cn.json. Returns written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "chinastockdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "mtf_upturn_cn.json"

    payload = json.dumps(result, separators=(",", ":"), default=str)
    out_path.write_text(payload + "\n", encoding="utf-8")
    log.info("mtf_upturn_cn: wrote %s (%dKB)", out_path, len(payload.encode()) // 1024)
    return out_path


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
