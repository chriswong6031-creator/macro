"""engine/oracle/ratio_lens.py — Ratio Lens pairwise ratio intelligence organ (RL-R1).

Oracle-owned display-tier organ. Computes a frozen, curated registry of ratio
pairs over a 3-level taxonomy, printing level / pace / stretch / anchor /
washout states with numerator-vs-denominator decomposition in absolute returns.

AUTHORITY block (RL-R1 / RL-R8): display-tier, all may_* False.
DISCLOSURE: expected-null forward ledger (RL-R9); Tier-M survivorship watermark
on basket pairs (RL-R5); oscillator outputs watermarked "not characterized on
ratio inputs — descriptive" (masterplan §VII).

State assignment (RL-R8):
  EXTENDED   — |z252| >= 2
  BASING     — washout + weekly_mom_turn (StochRSI washout cross-up)
  NO_ANCHOR  — anchor.status == "no_anchor" (after above checks)
  TRENDING   — default

Stances (DESIGN_DOCTRINE):
  EXTENDED  -> "Watch — don't chase"
  BASING    -> "Get ready — needs a trigger"
  NO_ANCHOR -> "Trend, not rope — don't fade it"
  TRENDING  -> "Ride, don't add late"

Provenance note: ETF legs use lib.store.read('yahoo', sym) 'close' column, which
is dividend-adjusted total return. ETF ratios are therefore total-return ratios —
printed as provenance per RL-R12.

Pure compute — no I/O side effects beyond reads. Caller is
scripts/build_oracle_ratio_lens.py.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import logging
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority + disclosure (RL-R1 / RL-R8)
# ---------------------------------------------------------------------------

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

DISCLOSURE: str = (
    "Display-tier only. All may_* authority flags are False. "
    "Forward ledger pre-registered as EXPECTED NULL (RL-R9) — states are context "
    "until proven otherwise via a registered gauntlet. "
    "Tier-M basket pairs carry a survivorship watermark: series begin at "
    "seed_date 2023-05-09 (max of member store coverage and seed date); "
    "no pre-seed reconstruction ships (RL-R5). "
    "Oscillator outputs carry watermark: 'not characterized on ratio inputs — "
    "descriptive' (masterplan §VII). "
    "ETF legs use dividend-adjusted close (total-return proxy); ETF ratios are "
    "therefore effectively total-return ratios (RL-R12 provenance). "
    "Correlations-not-causation framing: ratio moves are decomposed into legs' "
    "absolute returns — no routing, no locus ranking, no causal claim (RL-R3). "
    "The word 'validated' does not appear on these surfaces."
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEED_DATE = pd.Timestamp("2023-05-09")  # RL-R5 basket pair earliest start

# Stat windows
Z63_WINDOW = 63
Z252_WINDOW = 252
PCT3Y_WINDOW = 756   # 3 years of trading days (min 252)
PCT3Y_MIN = 252

# Anchor (RL-R6)
ANCHOR_WINDOW = 504  # OLS window in bars
ANCHOR_MIN = 252     # minimum bars required
BOOTSTRAP_BLOCKS = 500
BOOTSTRAP_BLOCK_SIZE = 21
BOOTSTRAP_SEED = 42
ANCHOR_MAX_HL_DAYS = 252  # half-life must be < 252d to print

# Pace windows (in bars)
PACE_1W = 5
PACE_1M = 21
PACE_3M = 63

# Dead-band for shape label (RL-R4)
SHAPE_DEAD_BAND = 0.25

# Leg correlation window (RL-R16)
LEG_CORR_WINDOW = 126
SHARED_TIDE_THRESHOLD = 0.85

# Drift note (RL-R6 / RL-R7)
DRIFT_SESSIONS = 20

# Weekly StochRSI
STOCHRSI_PERIOD = 14

# Forbidden keys (enforced by inline guard before returning payload)
FORBIDDEN_KEYS: frozenset[str] = frozenset({
    "beneficiary", "casualty", "shelter", "front_run",
    "buy", "direction", "forecast", "predicted", "target",
    "expected_return", "rank", "score", "recommendation",
})

# ---------------------------------------------------------------------------
# State machine (RL-R8)
# ---------------------------------------------------------------------------

_STATES = ("EXTENDED", "BASING", "NO_ANCHOR", "TRENDING")

_STANCE_EN: dict[str, str] = {
    "EXTENDED": "Watch — don't chase",
    "BASING":   "Get ready — needs a trigger",
    "NO_ANCHOR": "Trend, not rope — don't fade it",
    "TRENDING": "Ride, don't add late",
}
_STANCE_ZH: dict[str, str] = {
    "EXTENDED": "观望——不要追高",
    "BASING":   "做好准备——等待触发",
    "NO_ANCHOR": "这是趋势不是橡皮筋——不要逆势",
    "TRENDING": "顺势持有——不要追加迟仓",
}


def _assign_state(z252: float | None, washout: bool, weekly_mom_turn: bool,
                  anchor_status: str) -> str:
    """State assignment — reads ONLY (z252, washout, weekly_mom_turn, anchor_status).

    Tests enforce pace/velocity are NOT parameters of this function (RL-R8 / m12).
    """
    if z252 is not None and abs(z252) >= 2.0:
        return "EXTENDED"
    if washout and weekly_mom_turn:
        return "BASING"
    if anchor_status == "no_anchor":
        return "NO_ANCHOR"
    return "TRENDING"


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def _load_registry(data_root: Path) -> dict:
    p = data_root / "oracle" / "ratio_pairs.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _registry_hash(registry: dict) -> str:
    """SHA-256 of canonical JSON of pairs + taxonomy (RL-R2)."""
    obj = {
        "pairs": registry["pairs"],
        "taxonomy": registry["taxonomy"],
    }
    canonical = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# ETF series loader
# ---------------------------------------------------------------------------

def _etf_close(sym: str, data_root: Path) -> pd.Series | None:
    """Load ETF close from data/yahoo/{sym}.parquet via lib.store pattern."""
    import sys
    sys.path.insert(0, str(data_root.parent))
    from lib import store as _store
    df = _store.read("yahoo", sym)
    if df is None or df.empty:
        log.warning("ETF close missing: %s", sym)
        return None
    if "close" not in df.columns:
        log.warning("ETF %s has no 'close' column (cols=%s)", sym, list(df.columns))
        return None
    s = df["close"].dropna()
    return s if not s.empty else None


# ---------------------------------------------------------------------------
# Basket EW level builder (mirrors engine/baskets._ew_level, RL-R5)
# ---------------------------------------------------------------------------

def _basket_ew_level(basket_id: str, membership: dict, ohlcv_dir: Path) -> pd.Series | None:
    """Build equal-weight rebased level for a basket.

    Uses live members' parquets in data/baskets/ohlcv. Members with no parquet
    are skipped (missing). Series starts at max(first common bar, SEED_DATE).
    RL-R5: never reconstruct pre-seed.
    """
    basket_def = membership.get(basket_id)
    if basket_def is None:
        log.warning("basket_id not found in membership: %s", basket_id)
        return None

    members = [m for m in basket_def.get("members", []) if not m.get("removed")]
    if not members:
        log.warning("basket %s: no active members", basket_id)
        return None

    closes: dict[str, pd.Series] = {}
    for m in members:
        ticker = m["ticker"]
        p = ohlcv_dir / f"{ticker}.parquet"
        if not p.exists():
            log.debug("basket %s: missing parquet for %s", basket_id, ticker)
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns:
                continue
            s = df["close"].dropna()
            if not s.empty:
                closes[ticker] = s
        except Exception as exc:  # noqa: BLE001
            log.warning("basket %s: failed to load %s: %s", basket_id, ticker, exc)

    if len(closes) < 2:
        log.warning("basket %s: fewer than 2 tickers available", basket_id)
        return None

    # Build common daily index across all tickers
    all_idx = closes[list(closes.keys())[0]].index
    for s in closes.values():
        all_idx = all_idx.union(s.index)
    all_idx = all_idx.sort_values()

    # Apply PIT membership mask
    mask = pd.DataFrame(False, index=all_idx, columns=list(closes.keys()))
    for m in members:
        t = m["ticker"]
        if t not in closes:
            continue
        added = pd.Timestamp(m.get("added", "2000-01-01"))
        removed_raw = m.get("removed")
        a = all_idx >= added
        if removed_raw:
            a = a & (all_idx < pd.Timestamp(removed_raw))
        mask[t] = a

    # Build return frame
    rets_dict = {}
    for t, s in closes.items():
        aligned = s.reindex(all_idx)
        rets_dict[t] = aligned.pct_change()

    rets = pd.DataFrame(rets_dict)

    # EW daily return of active members
    ew = rets.where(mask).mean(axis=1)

    # Clip to seed_date (RL-R5: never pre-seed)
    ew = ew[ew.index >= SEED_DATE]
    if ew.empty or ew.dropna().empty:
        return None

    first = ew.first_valid_index()
    if first is None:
        return None

    lvl = pd.Series(np.nan, index=ew.index, dtype=float)
    lvl.loc[first:] = (1.0 + ew.loc[first:].fillna(0.0)).cumprod()
    return lvl.dropna()


# ---------------------------------------------------------------------------
# Ratio series computation
# ---------------------------------------------------------------------------

def _compute_log_ratio(num_lvl: pd.Series, den_lvl: pd.Series) -> pd.Series | None:
    """Inner-join, compute L = ln(num) - ln(den), rebased to 0 at eff_start.
    NO forward fill per RL-R7 / RL-R5.
    """
    # Inner join: only common bars, no forward-fill
    combined = pd.DataFrame({"num": num_lvl, "den": den_lvl}).dropna(how="any")
    if combined.empty:
        return None
    ln_ratio = np.log(combined["num"]) - np.log(combined["den"])
    ln_ratio = ln_ratio - ln_ratio.iloc[0]  # rebase to 0 at eff_start
    return ln_ratio


# ---------------------------------------------------------------------------
# Rolling z-score
# ---------------------------------------------------------------------------

def _rolling_z(series: pd.Series, window: int, min_obs: int | None = None) -> float | None:
    """Z-score of last value vs trailing {window}-bar distribution."""
    min_periods = min_obs if min_obs is not None else window
    if len(series) < min_periods:
        return None
    tail = series.iloc[-window:]
    if len(tail) < min_periods:
        return None
    mu = float(tail.mean())
    sigma = float(tail.std(ddof=1))
    if sigma == 0 or np.isnan(sigma):
        return None
    return float((series.iloc[-1] - mu) / sigma)


# ---------------------------------------------------------------------------
# Pace computation (RL-R7)
# ---------------------------------------------------------------------------

def _pace(series: pd.Series, bars: int) -> float | None:
    """ΔL over {bars} bars, expressed per-week (÷ bars × 5)."""
    if len(series) <= bars:
        return None
    delta = float(series.iloc[-1] - series.iloc[-1 - bars])
    return delta / bars * 5.0  # per-week rate


def _pace_trend(p1w: float | None, p1m: float | None) -> str | None:
    """Descriptive pace trend (RL-R7): fading / building / steady.
    DESCRIPTIVE — never an input to state assignment.
    """
    if p1w is None or p1m is None:
        return None
    if p1m == 0:
        return "steady"
    if abs(p1w) < 0.5 * abs(p1m) and (p1w * p1m >= 0):
        return "fading"
    if abs(p1w) > 1.5 * abs(p1m):
        return "building"
    return "steady"


# ---------------------------------------------------------------------------
# Move shape label (RL-R4)
# ---------------------------------------------------------------------------

def _shape_label(leg_a_ret: float | None, leg_b_ret: float | None) -> str | None:
    """RL-R4 shape label with dead-band k=0.25."""
    if leg_a_ret is None or leg_b_ret is None:
        return None
    a, b = leg_a_ret, leg_b_ret
    stronger = a if abs(a) >= abs(b) else b
    weaker   = b if abs(a) >= abs(b) else a
    # opposite signs OR weaker is within dead-band of stronger
    if stronger == 0:
        return "mixed"
    if (a * b < 0) or (abs(weaker) < SHAPE_DEAD_BAND * abs(stronger)):
        return "one_sided"
    if a > 0 and b > 0:
        return "shared_tide_up"
    if a < 0 and b < 0:
        return "shared_tide_down"
    return "mixed"


# ---------------------------------------------------------------------------
# Anchor (RL-R6)
# ---------------------------------------------------------------------------

def _anchor_ols(series: pd.Series) -> dict:
    """OLS of ΔL_t on (L_{t-1} - mean L) over trailing ANCHOR_WINDOW bars.

    Returns anchor dict with status + (optionally) half_life, ci_low, ci_high.
    Circular block bootstrap (block=21, n=500, seed=42) for CI of b.
    Half-life prints ONLY if b<0, CI excludes 0, CI-upper half-life < 252d.
    Otherwise status = "no_anchor" with no half_life key.
    """
    if len(series) < ANCHOR_MIN:
        return {"status": "no_anchor", "note": f"insufficient bars (need {ANCHOR_MIN})"}

    tail = series.iloc[-ANCHOR_WINDOW:]
    L = tail.values.astype(float)
    mean_L = float(np.mean(L))
    dL = np.diff(L)            # ΔL_t (length n-1)
    L_lag = L[:-1] - mean_L   # L_{t-1} - mean_L (demeaned)

    # OLS: dL = a + b * L_lag
    if np.std(L_lag) == 0:
        return {"status": "no_anchor", "note": "zero variance in L_lag"}

    X = np.column_stack([np.ones(len(L_lag)), L_lag])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            coef, _, _, _ = np.linalg.lstsq(X, dL, rcond=None)
        except Exception:  # noqa: BLE001
            return {"status": "no_anchor", "note": "OLS failed"}

    b_hat = float(coef[1])

    # Block bootstrap CI
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(dL)
    b_boots: list[float] = []
    block = BOOTSTRAP_BLOCK_SIZE
    n_blocks = max(1, n // block)
    starts = list(range(0, n - block + 1))  # valid block start positions

    for _ in range(BOOTSTRAP_BLOCKS):
        # circular block bootstrap
        idx_blocks = rng.choice(len(starts), size=n_blocks, replace=True)
        boot_idx: list[int] = []
        for bi in idx_blocks:
            start = starts[bi]
            boot_idx.extend(range(start, min(start + block, n)))
        boot_idx = boot_idx[:n]
        dL_b = dL[boot_idx]
        Ll_b = L_lag[boot_idx]
        Xb = np.column_stack([np.ones(len(dL_b)), Ll_b])
        if np.std(Ll_b) < 1e-12:
            continue
        try:
            cb, _, _, _ = np.linalg.lstsq(Xb, dL_b, rcond=None)
            b_boots.append(float(cb[1]))
        except Exception:  # noqa: BLE001
            continue

    if len(b_boots) < 50:
        return {"status": "no_anchor", "note": "bootstrap failed"}

    ci_low  = float(np.percentile(b_boots, 2.5))
    ci_high = float(np.percentile(b_boots, 97.5))

    # Print half-life ONLY if b<0, CI excludes 0, CI-upper half-life < 252d (RL-R6)
    if b_hat < 0 and ci_high < 0:
        hl_point = -np.log(2) / b_hat
        hl_upper = -np.log(2) / ci_low  # ci_low is most-negative → shortest hl
        if hl_upper < ANCHOR_MAX_HL_DAYS and hl_point > 0:
            return {
                "status": "anchored",
                "b": round(b_hat, 6),
                "half_life": round(hl_point, 1),
                "ci_low":    round(ci_low, 6),
                "ci_high":   round(ci_high, 6),
                "half_life_ci_upper": round(hl_upper, 1),
            }

    return {
        "status": "no_anchor",
        "b": round(b_hat, 6),
        "ci_low":  round(ci_low, 6),
        "ci_high": round(ci_high, 6),
        "note": "b not significantly negative or half-life > 252d",
    }


# ---------------------------------------------------------------------------
# Weekly StochRSI on L (RL-R7 / RL-R8)
# ---------------------------------------------------------------------------

def _weekly_stochrsi(L_daily: pd.Series, period: int = STOCHRSI_PERIOD) -> dict:
    """Weekly-resample L, compute StochRSI(14).

    Washout flag: K < 20 then crosses above D (K > D after K was < 20).
    Returns dict with k, d, washout (bool), weekly_mom_turn (bool),
    and oscillators_watermark.
    """
    watermark = "not characterized on ratio inputs — descriptive"

    if L_daily is None or len(L_daily) < period * 2 + 5:
        return {
            "k": None, "d": None,
            "washout": False, "weekly_mom_turn": False,
            "oscillators_watermark": watermark,
        }

    # Resample to weekly (last bar of each week)
    try:
        L_w = L_daily.resample("W-FRI").last().dropna()
    except Exception:  # noqa: BLE001
        return {
            "k": None, "d": None,
            "washout": False, "weekly_mom_turn": False,
            "oscillators_watermark": watermark,
        }

    if len(L_w) < period + 3:
        return {
            "k": None, "d": None,
            "washout": False, "weekly_mom_turn": False,
            "oscillators_watermark": watermark,
        }

    # RSI of L_w changes
    delta = L_w.diff().dropna()
    if len(delta) < period:
        return {
            "k": None, "d": None,
            "washout": False, "weekly_mom_turn": False,
            "oscillators_watermark": watermark,
        }

    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = (100 - 100 / (1 + rs)).fillna(50)

    # StochRSI: (RSI - min_RSI) / (max_RSI - min_RSI) over period
    rsi_min = rsi.rolling(period).min()
    rsi_max = rsi.rolling(period).max()
    rng = (rsi_max - rsi_min).replace(0, np.nan)
    stoch_k = ((rsi - rsi_min) / rng * 100).fillna(50)
    stoch_d = stoch_k.rolling(3).mean()

    if stoch_k.empty or stoch_d.empty:
        return {
            "k": None, "d": None,
            "washout": False, "weekly_mom_turn": False,
            "oscillators_watermark": watermark,
        }

    k_now  = float(stoch_k.iloc[-1])
    d_now  = float(stoch_d.iloc[-1]) if not pd.isna(stoch_d.iloc[-1]) else None
    k_prev = float(stoch_k.iloc[-2]) if len(stoch_k) >= 2 else None

    # Washout: K currently < 20 (oversold)
    washout = k_now < 20

    # Weekly momentum turn: K was < 20 and now crossed above D
    weekly_mom_turn = False
    if (k_prev is not None and d_now is not None and
            k_prev < 20 and k_now > d_now):
        weekly_mom_turn = True

    return {
        "k": round(k_now, 2),
        "d": round(d_now, 2) if d_now is not None else None,
        "washout": washout,
        "weekly_mom_turn": weekly_mom_turn,
        "oscillators_watermark": watermark,
    }


# ---------------------------------------------------------------------------
# Per-pair record builder
# ---------------------------------------------------------------------------

def _leg_return(level: pd.Series, bars: int) -> float | None:
    """Absolute log return of a level series over trailing {bars} bars."""
    s = level.dropna()
    if len(s) <= bars:
        return None
    return float(np.log(s.iloc[-1]) - np.log(s.iloc[-1 - bars]))


def _drift_note(z252_series: pd.Series) -> str | None:
    """If z252 moved in one direction for >= 20 consecutive sessions, return note."""
    if z252_series is None or len(z252_series) < DRIFT_SESSIONS + 1:
        return None
    # Check last DRIFT_SESSIONS sessions for monotone direction
    recent = z252_series.dropna().iloc[-DRIFT_SESSIONS - 1:]
    if len(recent) < DRIFT_SESSIONS + 1:
        return None
    diffs = recent.diff().dropna().iloc[-DRIFT_SESSIONS:]
    if len(diffs) < DRIFT_SESSIONS:
        return None
    if (diffs > 0).all():
        return f"persistent one-way move — {DRIFT_SESSIONS} sessions"
    if (diffs < 0).all():
        return f"persistent one-way move — {DRIFT_SESSIONS} sessions"
    return None


def _compute_pair_record(
    pair: dict,
    num_lvl: pd.Series,
    den_lvl: pd.Series,
    kind: str,
) -> dict:
    """Compute all fields for a single pair record."""
    pair_id = pair["id"]

    # Log ratio series (inner-join, no forward-fill)
    L = _compute_log_ratio(num_lvl, den_lvl)
    if L is None or L.empty:
        return {
            "id": pair_id,
            "error": "could not compute ratio series (insufficient common bars)",
            "eff_start": None,
        }

    eff_start = L.index[0].date().isoformat()

    # Leg absolute log returns for 1w/1m (after inner-join)
    num_aligned = num_lvl.reindex(L.index).dropna()
    den_aligned = den_lvl.reindex(L.index).dropna()

    def _leg_ret(s: pd.Series, bars: int) -> float | None:
        s2 = s.dropna()
        if len(s2) <= bars:
            return None
        return round(float(np.log(s2.iloc[-1]) - np.log(s2.iloc[-1 - bars])), 6)

    leg_num_1w = _leg_ret(num_aligned, PACE_1W)
    leg_num_1m = _leg_ret(num_aligned, PACE_1M)
    leg_num_3m = _leg_ret(num_aligned, PACE_3M)
    leg_den_1w = _leg_ret(den_aligned, PACE_1W)
    leg_den_1m = _leg_ret(den_aligned, PACE_1M)
    leg_den_3m = _leg_ret(den_aligned, PACE_3M)

    # Z-scores
    z63  = _rolling_z(L, Z63_WINDOW)
    z252 = _rolling_z(L, Z252_WINDOW)
    z63  = round(z63, 3)  if z63  is not None else None
    z252 = round(z252, 3) if z252 is not None else None

    # Percentile 3y
    pct_3y: float | None = None
    if len(L) >= PCT3Y_MIN:
        win = L.iloc[-PCT3Y_WINDOW:] if len(L) >= PCT3Y_WINDOW else L
        if len(win) >= PCT3Y_MIN:
            rank = (win < L.iloc[-1]).sum() / len(win)
            pct_3y = round(float(rank) * 100, 1)

    # Pace
    p1w = _pace(L, PACE_1W)
    p1m = _pace(L, PACE_1M)
    p3m = _pace(L, PACE_3M)
    pt  = _pace_trend(p1w, p1m)

    # Shape label (1w and 1m)
    shape_1w = _shape_label(leg_num_1w, leg_den_1w)
    shape_1m = _shape_label(leg_num_1m, leg_den_1m)

    # Anchor (RL-R6)
    anchor = _anchor_ols(L)

    # StochRSI washout (RL-R7 / RL-R8)
    stochrsi = _weekly_stochrsi(L)
    washout       = stochrsi["washout"]
    weekly_mom_turn = stochrsi["weekly_mom_turn"]

    # Drift note
    # Build rolling z252 series to detect drift
    def _rolling_z_series(s: pd.Series, window: int) -> pd.Series:
        mu = s.rolling(window).mean()
        sd = s.rolling(window).std(ddof=1)
        return (s - mu) / sd.replace(0, np.nan)

    z252_series = _rolling_z_series(L, Z252_WINDOW)
    drift_note = _drift_note(z252_series)

    # Leg correlation (RL-R16)
    leg_corr_126: float | None = None
    shared_tide_chip: bool = False
    if len(num_aligned) >= LEG_CORR_WINDOW and len(den_aligned) >= LEG_CORR_WINDOW:
        num_ret = np.log(num_aligned).diff().dropna().iloc[-LEG_CORR_WINDOW:]
        den_ret = np.log(den_aligned).diff().dropna().iloc[-LEG_CORR_WINDOW:]
        common = pd.DataFrame({"a": num_ret, "b": den_ret}).dropna()
        if len(common) >= 30:
            corr_val = float(common["a"].corr(common["b"]))
            if not np.isnan(corr_val):
                leg_corr_126 = round(corr_val, 4)
                shared_tide_chip = corr_val > SHARED_TIDE_THRESHOLD

    # State (RL-R8) — args are ONLY (z252, washout, weekly_mom_turn, anchor_status)
    anchor_status = anchor.get("status", "no_anchor")
    state = _assign_state(z252, washout, weekly_mom_turn, anchor_status)

    # Pace note (descriptive, NEVER "pre-reversion" language — RL-R8)
    pace_note: str | None = None
    if state == "EXTENDED" and pt == "fading":
        pace_note = f"extended, and the move's pace is fading"
    elif state == "EXTENDED" and pt == "building":
        pace_note = f"extended, and the move's pace is still building"
    elif pt is not None:
        pace_note = f"pace is {pt}"

    # Watermark for Tier-M basket pairs (RL-R5)
    watermark: str | None = None
    if kind == "basket":
        watermark = (
            "Tier-M: basket series start at seed_date 2023-05-09; "
            "hindsight-curated membership; survivorship present — "
            "descriptive context, not a backtest."
        )

    # Assemble record
    record: dict[str, Any] = {
        "id": pair_id,
        "num": pair["num"],
        "den": pair["den"],
        "kind": kind,
        "name_en": pair["name_en"],
        "name_zh": pair["name_zh"],
        "reads_as_en": pair["reads_as_en"],
        "reads_as_zh": pair["reads_as_zh"],
        "eff_start": eff_start,
        "n_bars": len(L),
        "overlap_names": pair.get("overlap_names", []),
        "yield_flag": pair.get("yield_flag", False),
        "traded_ref": pair.get("traded_ref", []),
        "provenance": (
            "ETF legs: dividend-adjusted close (total-return proxy). "
            "Basket legs: equal-weight PIT membership rebase. "
            "Inner-join only; no forward-fill (RL-R7)."
        ) if kind == "etf" else (
            "Basket legs: equal-weight PIT membership rebase, seed_date 2023-05-09. "
            "Inner-join only; no forward-fill (RL-R7)."
        ),
        "level_last": round(float(L.iloc[-1]), 6),
        "legs": {
            "num": {
                "id": pair["num"],
                "ret_1w": round(leg_num_1w, 6) if leg_num_1w is not None else None,
                "ret_1m": round(leg_num_1m, 6) if leg_num_1m is not None else None,
                "ret_3m": round(leg_num_3m, 6) if leg_num_3m is not None else None,
            },
            "den": {
                "id": pair["den"],
                "ret_1w": round(leg_den_1w, 6) if leg_den_1w is not None else None,
                "ret_1m": round(leg_den_1m, 6) if leg_den_1m is not None else None,
                "ret_3m": round(leg_den_3m, 6) if leg_den_3m is not None else None,
            },
        },
        "decomp": {
            "shape_1w": shape_1w,
            "shape_1m": shape_1m,
        },
        "z63":    z63,
        "z252":   z252,
        "pct_3y": pct_3y,
        "pace": {
            "1w": round(p1w, 6) if p1w is not None else None,
            "1m": round(p1m, 6) if p1m is not None else None,
            "3m": round(p3m, 6) if p3m is not None else None,
            "pace_trend": pt,
        },
        "anchor": anchor,
        "stochrsi_weekly": stochrsi,
        "drift_note": drift_note,
        "leg_corr_126": leg_corr_126,
        "shared_tide_chip": shared_tide_chip,
        "state": state,
        "stance_en": _STANCE_EN[state],
        "stance_zh": _STANCE_ZH[state],
        "pace_note": pace_note,
    }
    if watermark is not None:
        record["watermark"] = watermark
    if "overlap_names" in pair and pair["overlap_names"]:
        record["overlap_pct_note"] = (
            f"Overlap: {', '.join(pair['overlap_names'])} — O≈8.3% (RL-R16, printed)"
        )

    return record


# ---------------------------------------------------------------------------
# Decomposition tree (RL-R3 / §4)
# ---------------------------------------------------------------------------

def _build_tree(pair_records: list[dict], registry: dict) -> dict:
    """Per taxonomy parent: children's 1w/1m absolute EW-basket returns side-by-side.

    Absolute returns ONLY — no dispersion stats, no ranking, no routing fields (RL-R3).
    """
    taxonomy = registry.get("taxonomy", {})
    tree: dict[str, Any] = {}

    # Collect all basket-level absolute returns by basket ID
    basket_rets: dict[str, dict] = {}
    for rec in pair_records:
        if rec.get("kind") == "basket":
            for leg_key in ("num", "den"):
                lid = rec.get(leg_key) or (rec.get("legs") or {}).get(leg_key, {}).get("id")
                if lid and lid not in basket_rets:
                    legs = rec.get("legs", {})
                    leg_data = legs.get(leg_key, {})
                    basket_rets[lid] = {
                        "ret_1w": leg_data.get("ret_1w"),
                        "ret_1m": leg_data.get("ret_1m"),
                    }

    # Build tree by parent
    us_market = taxonomy.get("us_market", {})
    for group_name, children in us_market.items():
        group_data: list[dict] = []
        for child_id in children:
            entry: dict = {"id": child_id}
            if child_id in basket_rets:
                entry["ret_1w"] = basket_rets[child_id].get("ret_1w")
                entry["ret_1m"] = basket_rets[child_id].get("ret_1m")
            else:
                entry["ret_1w"] = None
                entry["ret_1m"] = None
                entry["note"] = "no pair data available for this node"
            group_data.append(entry)
        tree[group_name] = {
            "children": group_data,
            "note": "absolute returns only — no dispersion gate, no ranking, no routing (RL-R3)",
        }

    return tree


# ---------------------------------------------------------------------------
# Forbidden key guard (inline, before returning payload)
# ---------------------------------------------------------------------------

def _assert_no_forbidden_keys(obj: Any, path: str = "") -> None:
    """Recursive walk asserting none of FORBIDDEN_KEYS appear anywhere.

    Skips the 'authority' top-level block (meta-flags like may_rank are
    structural AUTHORITY keys, not data fields subject to the banned-key fence).
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            # Skip the authority block — may_rank/may_gate/etc are structural
            if path == "" and k == "authority":
                continue
            k_lower = k.lower()
            for fk in FORBIDDEN_KEYS:
                if fk in k_lower:
                    raise ValueError(
                        f"FORBIDDEN key '{k}' found at path '{path}.{k}' — "
                        f"remove it (RL-R8 / contract)"
                    )
            _assert_no_forbidden_keys(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _assert_no_forbidden_keys(item, f"{path}[{i}]")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute(
    data_root: Path,
    as_of: str | None = None,
) -> dict:
    """Compute ratio lens artifact.

    Parameters
    ----------
    data_root:
        Path to repo data/ directory. Must contain oracle/ratio_pairs.json,
        yahoo/*.parquet (ETF legs), baskets/membership.json, baskets/ohlcv/*.parquet.
    as_of:
        ISO date string (YYYY-MM-DD). Defaults to today.

    Returns
    -------
    dict — ratio_lens.v1 payload (forbidden-key clean).
    """
    as_of_str = as_of or date.today().isoformat()

    registry = _load_registry(data_root)
    reg_hash = _registry_hash(registry)

    # Load basket membership
    membership_path = data_root / "baskets" / "membership.json"
    if not membership_path.exists():
        log.warning("membership.json not found at %s", membership_path)
        membership: dict = {}
    else:
        raw_membership = json.loads(membership_path.read_text(encoding="utf-8"))
        membership = raw_membership.get("baskets", {})

    ohlcv_dir = data_root / "baskets" / "ohlcv"

    pairs_config = registry.get("pairs", [])
    pair_records: list[dict] = []

    for pair in pairs_config:
        pair_id  = pair["id"]
        num_sym  = pair["num"]
        den_sym  = pair["den"]
        kind     = pair["kind"]

        log.info("[ratio_lens] computing pair %s (%s/%s)", pair_id, num_sym, den_sym)

        try:
            if kind == "etf":
                num_lvl = _etf_close(num_sym, data_root)
                den_lvl = _etf_close(den_sym, data_root)
            elif kind == "basket":
                num_lvl = _basket_ew_level(num_sym, membership, ohlcv_dir)
                den_lvl = _basket_ew_level(den_sym, membership, ohlcv_dir)
            else:
                log.warning("unknown kind=%s for pair %s", kind, pair_id)
                pair_records.append({"id": pair_id, "error": f"unknown kind={kind}"})
                continue

            if num_lvl is None:
                pair_records.append({
                    "id": pair_id, "kind": kind,
                    "error": f"num leg missing: {num_sym}",
                })
                continue
            if den_lvl is None:
                pair_records.append({
                    "id": pair_id, "kind": kind,
                    "error": f"den leg missing: {den_sym}",
                })
                continue

            rec = _compute_pair_record(pair, num_lvl, den_lvl, kind)
            pair_records.append(rec)

        except Exception as exc:  # noqa: BLE001
            log.warning("pair %s failed: %s", pair_id, exc, exc_info=True)
            pair_records.append({"id": pair_id, "error": str(exc)})

    # Decomposition tree
    tree = _build_tree(pair_records, registry)

    # Count implicit claims (n_pairs × n_states × 2 horizons)
    n_valid = sum(1 for r in pair_records if "error" not in r)
    implicit_claim_count = n_valid * len(_STATES) * 2

    payload: dict[str, Any] = {
        "schema": "ratio_lens.v1",
        "as_of": as_of_str,
        "registry_hash": reg_hash,
        "authority": AUTHORITY,
        "disclosure": DISCLOSURE,
        "pairs": pair_records,
        "tree": tree,
        "implicit_claim_count": implicit_claim_count,
    }

    # Inline forbidden-key guard before returning
    _assert_no_forbidden_keys(payload)

    return payload


# ---------------------------------------------------------------------------
# State function signature assertion (for tests: RL-R8 / m12)
# ---------------------------------------------------------------------------

def _state_fn_signature_check() -> bool:
    """Return True if _assign_state has no pace/velocity parameter."""
    sig = inspect.signature(_assign_state)
    params = set(sig.parameters.keys())
    bad = {p for p in params if "pace" in p.lower() or "velocity" in p.lower()}
    return len(bad) == 0
