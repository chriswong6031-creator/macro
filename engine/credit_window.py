"""Credit issuance window — DISPLAY-ONLY, NEVER-SCORED gate for new bond deals.

Mirrors engine/ipo_radar.py's window_context() pattern: a coincident read of
whether borrowers can place new bonds RIGHT NOW, built from market-wide spread
and rates-vol series that the F01 credit-axis owners already read (read-only,
no re-ingest, no writes, no network).

Two lanes: high-yield (HY OAS) and investment-grade (IG OAS) borrowers. Each
lane reads three inputs: where today's spread sits in its own 1-year range
(spread_range), the recent move in that spread (spread_drift), and rates
volatility (rates_vol, MOVE index — shared, identical value in both lanes).

NOTHING here is a scored signal, nothing here feeds any axis/regime/allocation,
and no issuer identity, par amount, or notional is ever touched — this module
reads only market-wide index series and performs no join of any kind.
`SCORED = False` is asserted by tests/test_credit_window.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from lib import config

# Invariant marker read by tests: this layer must never become a scored input.
SCORED = False

N_EXPECTED = 3
MIN_INPUTS = 2              # fewer than 2 readable inputs -> "not_evaluable"
RANGE_WINDOW = 252          # ~1 year of observations
DRIFT_WINDOW = 21
MIN_HISTORY = 60            # fewer observations than this -> percentile is not readable
                             # (a "past year" percentile off a handful of rows is not a
                             # past-year claim; the input renders "unknown" instead — MAJOR 5)
STALE_DAYS = 10              # an input whose latest observation is this many calendar
                             # days behind "now" is too old to back a confident read — MAJOR 6
FRED_HY, FRED_IG = "BAMLH0A0HYM2", "BAMLC0A0CM"
MOVE_TICKER = "MOVE"
RANGE_OPEN_PCT, RANGE_SHUT_PCT = 33.0, 66.0   # percentile of today's OAS in its 1y range
DRIFT_OPEN_BP, DRIFT_SHUT_BP = -15.0, 25.0    # 21-obs change in OAS, basis points
MOVE_OPEN_PCT, MOVE_SHUT_PCT = 40.0, 75.0     # percentile of MOVE in its own 1y range
_BAND_WIDTH_UNBOUNDED = 1.0e6                 # sentinel "wide" width for open/shut bands


# --------------------------------------------------------------------------- #
# local, injectable-root loaders (mirrors engine/credit_momentum.py's shape;
# does NOT import its private _load_archive_merged so root stays injectable
# for fixture tests without touching the real data dir)
# --------------------------------------------------------------------------- #
def _load_fred_merged(fred_id: str, root: Path) -> pd.Series | None:
    fred_path = root / "fred" / f"{fred_id}.parquet"
    arch_path = root / "archive" / f"{fred_id}.parquet"
    live: pd.Series | None = None
    arch: pd.Series | None = None
    for path, tag in [(fred_path, "live"), (arch_path, "archive")]:
        if path.exists():
            try:
                df = pd.read_parquet(path)
                df.index = pd.to_datetime(df.index)
                df = df.sort_index()
                s = df.iloc[:, 0].dropna().astype(float)
                if tag == "live":
                    live = s
                else:
                    arch = s
            except Exception:  # noqa: BLE001
                continue
    if live is None and arch is None:
        return None
    if arch is not None and live is not None:
        return live.combine_first(arch).sort_index().dropna()
    s = live if live is not None else arch
    return s.sort_index().dropna()  # type: ignore[union-attr]


def _load_move(root: Path) -> pd.Series | None:
    path = root / "yahoo" / f"{MOVE_TICKER}.parquet"
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if "close" not in df.columns:
            return None
        df.index = pd.to_datetime(df.index)
        return df["close"].astype(float).dropna().sort_index()
    except Exception:  # noqa: BLE001
        return None


def _pct_rank_last(s: pd.Series, window: int) -> float | None:
    tail = s.tail(window)
    if len(tail) < MIN_INPUTS or len(tail) < MIN_HISTORY:
        return None
    last = float(tail.iloc[-1])
    return float((tail <= last).mean() * 100.0)


def _drift_bp(s: pd.Series, window: int) -> float | None:
    tail = s.tail(window + 1)
    if len(tail) < window + 1:
        return None
    # OAS series are already in percentage points; 1pp = 100bp
    return float((tail.iloc[-1] - tail.iloc[0]) * 100.0)


def _as_of(s: pd.Series | None) -> str | None:
    if s is None or not len(s):
        return None
    ts = s.index[-1]
    try:
        return pd.Timestamp(ts).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _is_stale(as_of_str: str | None, now: datetime | None = None) -> bool:
    """True when the input's most recent observation is more than STALE_DAYS
    calendar days behind "now" — a year-stale series must not back a confident
    open/shut read (MAJOR 6)."""
    if as_of_str is None:
        return False
    try:
        as_of_ts = datetime.strptime(as_of_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return False
    ref = now or datetime.now(timezone.utc)
    return (ref - as_of_ts) > timedelta(days=STALE_DAYS)


# --------------------------------------------------------------------------- #
# public functions
# --------------------------------------------------------------------------- #
def input_state(key: str, value: float | None) -> str:
    """-> "open" | "neutral" | "shut" | "unknown"."""
    if value is None:
        return "unknown"
    v = float(value)
    if key == "spread_range":
        if v <= RANGE_OPEN_PCT:
            return "open"
        if v <= RANGE_SHUT_PCT:
            return "neutral"
        return "shut"
    if key == "rates_vol":
        if v <= MOVE_OPEN_PCT:
            return "open"
        if v <= MOVE_SHUT_PCT:
            return "neutral"
        return "shut"
    if key == "spread_drift":
        if v <= DRIFT_OPEN_BP:
            return "open"
        if v < DRIFT_SHUT_BP:
            return "neutral"
        return "shut"
    return "unknown"


def segment_state(states: list[str]) -> tuple[str, int, bool]:
    n = sum(1 for s in states if s != "unknown")
    if n < MIN_INPUTS:
        return "not_evaluable", n, True
    n_open = sum(1 for s in states if s == "open")
    n_shut = sum(1 for s in states if s == "shut")
    low_conf = n < N_EXPECTED
    if n_open >= 2 and n_open > n_shut:
        return "open", n, low_conf
    if n_shut >= 2 and n_shut > n_open:
        return "shut", n, low_conf
    return "neutral", n, low_conf


def _band_width(key: str, state: str) -> float:
    """Width of the current band, in the input's own units, for change-line
    normalisation. Only the neutral band has a genuine, bounded width; the
    open/shut bands are unbounded on their outward side, so a value deep
    inside either is given a sentinel-wide width and is never chosen as the
    input "closest to flipping" (MAJOR 4 — this must read `state`, and the
    rates_vol band must use its own MOVE_* constants, not spread_range's)."""
    if state != "neutral":
        return _BAND_WIDTH_UNBOUNDED
    if key == "spread_range":
        return RANGE_SHUT_PCT - RANGE_OPEN_PCT  # 33.0
    if key == "rates_vol":
        return MOVE_SHUT_PCT - MOVE_OPEN_PCT  # 35.0
    if key == "spread_drift":
        return DRIFT_SHUT_BP - DRIFT_OPEN_BP  # 40.0
    return 1.0


def _next_threshold(key: str, state: str) -> tuple[float, str, str] | None:
    """-> (threshold, to_state, direction) for the nearest boundary this input
    could cross, or None if the input is unknown."""
    if key in ("spread_range", "rates_vol"):
        open_pct = RANGE_OPEN_PCT if key == "spread_range" else MOVE_OPEN_PCT
        shut_pct = RANGE_SHUT_PCT if key == "spread_range" else MOVE_SHUT_PCT
        if state == "open":
            return open_pct, "neutral", "up"
        if state == "shut":
            return shut_pct, "neutral", "down"
        if state == "neutral":
            return shut_pct, "shut", "up"
        return None
    if key == "spread_drift":
        if state == "open":
            return DRIFT_OPEN_BP, "neutral", "up"
        if state == "shut":
            return DRIFT_SHUT_BP, "neutral", "down"
        if state == "neutral":
            return DRIFT_SHUT_BP, "shut", "up"
        return None
    return None


def _choose_change(inputs: list[dict], segment: str) -> dict | None:
    """Pick the input closest to a boundary crossing whose crossing would
    ACTUALLY flip the reported segment state (BLOCKER 3) — a per-input
    threshold that does not move the segment majority is not "what would
    change this read", it is noise, so it must never be surfaced."""
    states = [i["state"] for i in inputs]
    candidates = []
    for idx, inp in enumerate(inputs):
        if inp["state"] == "unknown" or inp["value"] is None:
            continue
        nxt = _next_threshold(inp["key"], inp["state"])
        if nxt is None:
            continue
        threshold, to_state, direction = nxt
        trial_states = list(states)
        trial_states[idx] = to_state
        trial_segment, _, _ = segment_state(trial_states)
        if trial_segment == segment:
            continue  # flipping this input alone would not flip the segment
        width = _band_width(inp["key"], inp["state"]) or 1.0
        dist = abs(float(inp["value"]) - threshold) / width
        candidates.append({
            "dist": dist,
            "input": inp["key"], "to_state": to_state,
            "threshold": threshold, "current": inp["value"],
            "direction": direction, "segment_to": trial_segment,
        })
    if not candidates:
        return None
    best = min(candidates, key=lambda c: c["dist"])
    best.pop("dist")
    return best


def _segment(key: str, hy_or_ig_series: pd.Series | None, move_series: pd.Series | None) -> dict:
    spread_range = _pct_rank_last(hy_or_ig_series, RANGE_WINDOW) if hy_or_ig_series is not None else None
    spread_drift = _drift_bp(hy_or_ig_series, DRIFT_WINDOW) if hy_or_ig_series is not None else None
    rates_vol = _pct_rank_last(move_series, RANGE_WINDOW) if move_series is not None else None

    spread_as_of = _as_of(hy_or_ig_series)
    move_as_of = _as_of(move_series)

    # A stale underlying series cannot back a confident read (MAJOR 6): treat
    # its inputs as unreadable rather than silently rendering a fresh-looking
    # verdict off year-old data.
    if _is_stale(spread_as_of):
        spread_range = None
        spread_drift = None
    if _is_stale(move_as_of):
        rates_vol = None

    inputs = [
        {"key": "spread_range", "value": spread_range, "unit": "pct_rank",
         "state": input_state("spread_range", spread_range), "as_of": spread_as_of},
        {"key": "spread_drift", "value": spread_drift, "unit": "bp_21",
         "state": input_state("spread_drift", spread_drift), "as_of": spread_as_of},
        {"key": "rates_vol", "value": rates_vol, "unit": "pct_rank",
         "state": input_state("rates_vol", rates_vol), "as_of": move_as_of},
    ]
    states = [i["state"] for i in inputs]
    state, n_inputs, low_confidence = segment_state(states)

    rail = None
    if inputs[0]["state"] != "unknown":
        rail = {"pos_pct": round(float(spread_range), 1), "easy_pct": RANGE_OPEN_PCT}

    return {
        "key": key, "state": state, "n_inputs": n_inputs, "n_expected": N_EXPECTED,
        "low_confidence": low_confidence, "inputs": inputs, "rail": rail,
        "change": _choose_change(inputs, state),
    }


def window_state(root: str | Path | None = None) -> dict:
    r = Path(root) if root is not None else Path(config.data_dir())
    hy = _load_fred_merged(FRED_HY, r)
    ig = _load_fred_merged(FRED_IG, r)
    move = _load_move(r)

    hy_seg = _segment("hy", hy, move)
    ig_seg = _segment("ig", ig, move)

    as_of_candidates = [
        i["as_of"] for seg in (hy_seg, ig_seg) for i in seg["inputs"] if i["as_of"]
    ]
    as_of = max(as_of_candidates) if as_of_candidates else None

    return {
        "SCORED": False,
        "as_of": as_of,
        "research_only": True,
        "calendar": {"available": False, "reason": "no_upcoming_deal_calendar_source"},
        "note": (
            "Coincident read of the conditions issuers face. It describes whether new "
            "bond deals can be placed NOW; it does not forecast, and it is never scored."
        ),
        "segments": [hy_seg, ig_seg],
    }
