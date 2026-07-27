"""Frozen orthogonal terminality locator — prospective shadow lane.

This module operationalises the only retained result from PSS-F4H without
promoting F4 (or the replacement model) to decision authority:

    incumbent Stoch-RSI@derived-rung fire
        -> frozen orthogonal top-20% locator
        -> at most 15 sessions of observation
        -> first causal fresh-low rejection

The source incumbent events come from ``personality_gate_shadow``'s forward
ledger.  Every incumbent event is recorded, including below-threshold events,
so the prospective scorecard retains a real control group.  Selected events
open a shadow watch; they do not enter any ranker, sizer, gate, board, alert, or
trade ledger.

The two shallow boosted-tree hazards are served from a deterministic JSON tree
artifact.  No sklearn object is loaded in production.  SHA-256 checks bind the
model files to their manifest, and a mismatch makes the lane inert.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled
from lib import config

log = logging.getLogger(__name__)

LEDGER_SCHEMA = "personality_terminality_shadow.ledger/v1"
STATE_SCHEMA = "personality_terminality_shadow.v1"
MODEL_SCHEMA = "personality_terminality_shadow.model/v1"
TREE_SCHEMA = "frozen_hist_gradient_boosting/v1"
MODEL_ID = "pss_f4h_orthogonal_dev2022_v1"
SOURCE_AS_OF_FLOOR = "2026-07-26"
WATCH_HORIZON = 15
GRADE_HORIZON = 63
PROX_WINDOW = 31
DISPLAY_SESSIONS_AFTER_ACTION = 15

FEATURES = (
    "x_low60_dist",
    "x_roc20",
    "x_close_location",
    "x_lower_wick",
    "x_volume_ratio",
    "x_range_ratio",
    "x_down_share3",
    "x_rs5",
    "x_market_roc5",
    "x_sector_roc5",
    "x_terminal_recent",
    "x_price_rejection",
    "x_volume_exhaustion",
    "x_relative_turn",
    "x_systemic_repair",
)

SECTOR_ETF = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Financials": "XLF",
    "Health Care": "XLV",
    "Industrials": "XLI",
    "Information Technology": "XLK",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}


def _base(root: Path | None) -> Path:
    return (root if root is not None else config.data_dir()) / "personality_timing"


def artifact_dir(root: Path | None) -> Path:
    return _base(root) / "terminality_shadow_model_v1"


def source_ledger_path(root: Path | None) -> Path:
    return _base(root) / "gate_shadow.jsonl"


def ledger_path(root: Path | None) -> Path:
    return _base(root) / "terminality_shadow.jsonl"


def state_path(root: Path | None) -> Path:
    return _base(root) / "terminality_shadow_state.json"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_artifact(root: Path | None = None) -> dict | None:
    """Load and hash-verify the frozen numerical-only model artifact."""
    d = artifact_dir(root)
    mp = d / "manifest.json"
    try:
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        if manifest.get("schema") != MODEL_SCHEMA:
            raise ValueError(f"unexpected manifest schema {manifest.get('schema')!r}")
        if manifest.get("model_id") != MODEL_ID:
            raise ValueError(f"unexpected model id {manifest.get('model_id')!r}")
        if tuple(manifest.get("features") or ()) != FEATURES:
            raise ValueError("frozen feature order mismatch")
        models: dict[str, dict] = {}
        for key in ("near_low", "tail_safe"):
            spec = (manifest.get("models") or {}).get(key) or {}
            path = d / str(spec.get("path") or "")
            expected = spec.get("sha256")
            if not path.is_file() or not expected or _sha256(path) != expected:
                raise ValueError(f"{key} artifact missing or hash mismatch")
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc.get("schema") != TREE_SCHEMA:
                raise ValueError(f"{key} tree schema mismatch")
            if tuple(doc.get("features") or ()) != FEATURES:
                raise ValueError(f"{key} feature order mismatch")
            models[key] = doc
        return {"manifest": manifest, "models": models}
    except Exception as exc:  # noqa: BLE001 — a bad artifact makes the lane inert
        log.warning("personality_terminality_shadow: artifact rejected (%s)", exc)
        return None


def score_frozen_model(model: dict, values: dict[str, float]) -> float:
    """Evaluate one exported numerical HistGradientBoosting binary classifier."""
    features = tuple(model["features"])
    x = [float(values.get(name, np.nan)) for name in features]
    raw = float(model["baseline"])
    for tree in model["trees"]:
        node_i = 0
        while True:
            node = tree[node_i]
            if node["leaf"]:
                raw += float(node["value"])
                break
            value = x[int(node["feature"])]
            if math.isnan(value):
                go_left = bool(node["missing_left"])
            else:
                go_left = value <= float(node["threshold"])
            node_i = int(node["left"] if go_left else node["right"])
    # Stable inverse-logit.
    if raw >= 0:
        return 1.0 / (1.0 + math.exp(-raw))
    exp_raw = math.exp(raw)
    return exp_raw / (1.0 + exp_raw)


def score_locator(artifact: dict, values: dict[str, float]) -> tuple[float, float, float]:
    """Return (P near-low, P tail-safe, geometric-mean locator score)."""
    near = score_frozen_model(artifact["models"]["near_low"], values)
    safe = score_frozen_model(artifact["models"]["tail_safe"], values)
    return near, safe, math.sqrt(max(0.0, near) * max(0.0, safe))


def _lag(a: np.ndarray, k: int = 1) -> np.ndarray:
    out = np.full(len(a), np.nan)
    if k < len(a):
        out[k:] = a[:-k]
    return out


def _rolling_any(a: np.ndarray, n: int) -> np.ndarray:
    return (
        pd.Series(np.asarray(a, dtype=float))
        .rolling(n, min_periods=1)
        .max()
        .fillna(0.0)
        .to_numpy()
        > 0
    )


def _rolling_slope(a: np.ndarray, n: int) -> np.ndarray:
    x = np.arange(n, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())
    return (
        pd.Series(a, dtype=float)
        .rolling(n, min_periods=n)
        .apply(lambda y: float(np.dot(x, y - y.mean()) / denom), raw=True)
        .to_numpy()
    )


def _repair_state(x: np.ndarray) -> np.ndarray:
    s = pd.Series(x, dtype=float)
    ema5 = s.ewm(span=5, adjust=False, min_periods=5).mean().to_numpy()
    roc5 = s.pct_change(5).to_numpy()
    floor = pd.Series(roc5).shift(1).rolling(20, min_periods=10).min().to_numpy()
    return np.isfinite(ema5) & (x > ema5) & np.isfinite(floor) & (roc5 > floor)


def feature_arrays(
    ohlcv: pd.DataFrame,
    market_close: np.ndarray,
    sector_close: np.ndarray,
) -> dict[str, np.ndarray]:
    """Exact causal orthogonal feature block frozen by PSS-F4H."""
    op = ohlcv["open"].to_numpy(dtype=float)
    hi = ohlcv["high"].to_numpy(dtype=float)
    lo = ohlcv["low"].to_numpy(dtype=float)
    c = ohlcv["close"].to_numpy(dtype=float)
    vol = ohlcv["volume"].to_numpy(dtype=float)
    prior_low20 = pd.Series(lo).shift(1).rolling(20, min_periods=20).min().to_numpy()
    prior_high1 = _lag(hi)
    fresh_low = np.isfinite(prior_low20) & (lo <= prior_low20)
    bar_range = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        close_location = np.where(bar_range > 0, (c - lo) / bar_range, np.nan)
        lower_wick = np.where(
            bar_range > 0, (np.minimum(op, c) - lo) / bar_range, np.nan
        )
    bullish_rejection = (
        fresh_low
        & (c > op)
        & (close_location >= 0.65)
        & (lower_wick >= 0.20)
    )
    next_day_reclaim = (
        (_lag(fresh_low.astype(float)) == 1.0)
        & np.isfinite(prior_high1)
        & (c > prior_high1)
        & (c > op)
    )
    price_rejection = bullish_rejection | next_day_reclaim

    close_s = pd.Series(c)
    low60 = close_s.rolling(60, min_periods=60).min().to_numpy()
    roc20 = close_s.pct_change(20).to_numpy()
    roc20_floor = pd.Series(roc20).shift(1).rolling(20, min_periods=20).min().to_numpy()
    low10 = close_s.rolling(10, min_periods=10).min().to_numpy()
    low_slope = _rolling_slope(low10, 20)
    soft_terminal = (
        np.isfinite(low60)
        & (c <= 1.05 * low60)
        & np.isfinite(roc20_floor)
        & (roc20 > roc20_floor)
        & np.isfinite(_lag(low_slope, 20))
        & (low_slope > _lag(low_slope, 20))
    )
    terminal_recent = _rolling_any(soft_terminal, 5)

    previous_vol_median = (
        pd.Series(vol).shift(1).rolling(20, min_periods=20).median().to_numpy()
    )
    range_pct = np.where(c > 0, bar_range / c, np.nan)
    previous_range_median = (
        pd.Series(range_pct).shift(1).rolling(20, min_periods=20).median().to_numpy()
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        volume_ratio = vol / previous_vol_median
        range_ratio = range_pct / previous_range_median
    climax = fresh_low & ((volume_ratio >= 1.50) | (range_ratio >= 1.50))
    climax_recent = _rolling_any(climax, 5)
    ret = close_s.pct_change().to_numpy()
    down_vol = np.where(ret < 0, vol, 0.0)
    vol3 = pd.Series(vol).rolling(3, min_periods=3).sum().to_numpy()
    down3 = pd.Series(down_vol).rolling(3, min_periods=3).sum().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        down_share3 = down3 / vol3
    pressure_turn = (
        np.isfinite(_lag(down_share3, 3))
        & (_lag(down_share3, 3) >= 0.60)
        & (down_share3 <= 0.50)
    )
    volume_exhaustion = climax_recent | pressure_turn

    sector = np.asarray(sector_close, dtype=float)
    market = np.asarray(market_close, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        relative = np.log(c / sector)
        low60_dist = c / low60 - 1.0
    rs5 = relative - _lag(relative, 5)
    relative_turn = np.isfinite(rs5) & (rs5 > 0) & (rs5 > _lag(rs5, 3))
    systemic_repair = _repair_state(market) & _repair_state(sector)
    market_roc5 = pd.Series(market).pct_change(5).to_numpy()
    sector_roc5 = pd.Series(sector).pct_change(5).to_numpy()

    return {
        "x_low60_dist": low60_dist,
        "x_roc20": roc20,
        "x_close_location": close_location,
        "x_lower_wick": lower_wick,
        "x_volume_ratio": volume_ratio,
        "x_range_ratio": range_ratio,
        "x_down_share3": down_share3,
        "x_rs5": rs5,
        "x_market_roc5": market_roc5,
        "x_sector_roc5": sector_roc5,
        "x_terminal_recent": terminal_recent,
        "x_price_rejection": price_rejection,
        "x_volume_exhaustion": volume_exhaustion,
        "x_relative_turn": relative_turn,
        "x_systemic_repair": systemic_repair,
    }


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 — one corrupt row does not erase the book
            continue
    return rows


def _load_ohlcv(root: Path | None, sym: str) -> pd.DataFrame | None:
    p = (root if root is not None else config.data_dir()) / "baskets" / "ohlcv" / f"{sym}.parquet"
    try:
        d = pd.read_parquet(p)
        d = d[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        d.index = pd.DatetimeIndex(d.index).tz_localize(None)
        d = d[~d.index.duplicated(keep="last")].sort_index()
        return d if not d.empty else None
    except Exception as exc:  # noqa: BLE001
        log.debug("personality_terminality_shadow: %s OHLCV unavailable (%s)", sym, exc)
        return None


def _load_yahoo_close(root: Path | None, sym: str) -> pd.Series | None:
    p = (root if root is not None else config.data_dir()) / "yahoo" / f"{sym}.parquet"
    try:
        d = pd.read_parquet(p)
        col = "close" if "close" in d.columns else "close_price"
        s = d[col].dropna().astype(float)
        s.index = pd.DatetimeIndex(s.index).tz_localize(None)
        return s[~s.index.duplicated(keep="last")].sort_index()
    except Exception:  # noqa: BLE001
        return None


def _load_context(
    root: Path | None,
) -> tuple[pd.Series | None, dict[str, pd.Series], dict[str, str]]:
    data = root if root is not None else config.data_dir()
    market = _load_yahoo_close(root, "SPY")
    sectors = {
        name: close
        for name, etf in SECTOR_ETF.items()
        if (close := _load_yahoo_close(root, etf)) is not None
    }
    mapping: dict[str, str] = {}
    try:
        d = pd.read_parquet(data / "breadth" / "ticker_sectors.parquet")
        mapping = dict(zip(d["ticker"].astype(str), d["sector"].astype(str), strict=False))
    except Exception as exc:  # noqa: BLE001
        log.warning("personality_terminality_shadow: sector map unavailable (%s)", exc)
    return market, sectors, mapping


def _align_context(source: pd.Series, idx: pd.DatetimeIndex) -> np.ndarray:
    """Past-only alignment; never backfill from a future context observation."""
    return source.reindex(idx, method="ffill").to_numpy(dtype=float)


def _exact_pos(idx: pd.DatetimeIndex, date_text: str) -> int | None:
    pos = int(idx.searchsorted(pd.Timestamp(date_text)))
    if pos >= len(idx) or str(idx[pos].date()) != str(date_text)[:10]:
        return None
    return pos


def _grade(close: pd.Series, entry: dict | None) -> dict | None:
    if not entry:
        return None
    e = _exact_pos(pd.DatetimeIndex(close.index), str(entry.get("entry_date")))
    if e is None or e + GRADE_HORIZON >= len(close):
        return None
    px = float(entry["entry_px"])
    forward = close.iloc[e: e + GRADE_HORIZON + 1]
    fwd63 = (float(close.iloc[e + GRADE_HORIZON]) / px - 1.0) * 100.0
    mae63 = (float(forward.min()) / px - 1.0) * 100.0
    out: dict[str, Any] = {
        "fwd63": round(fwd63, 2),
        "mae63": round(mae63, 2),
        "prox": None,
        "td_to_trough": None,
        "timing_label": None,
    }
    if e >= PROX_WINDOW:
        local = close.iloc[e - PROX_WINDOW: e + PROX_WINDOW + 1].to_numpy(dtype=float)
        trough = float(local.min())
        tdt = int(np.argmin(local)) - PROX_WINDOW
        out["prox"] = round((px / trough - 1.0) * 100.0, 2)
        out["td_to_trough"] = tdt
        out["timing_label"] = (
            "called_low" if -2 <= tdt <= 5
            else "confirmed_reset" if tdt < -2
            else "early"
        )
    return out


def _score_source(
    source: dict,
    artifact: dict,
    root: Path | None,
    market: pd.Series,
    sectors: dict[str, pd.Series],
    ticker_sector: dict[str, str],
    observed_as_of: str,
) -> dict | None:
    sym = str(source.get("sym") or "")
    entry = source.get("tailored_entry") or {}
    x = _load_ohlcv(root, sym)
    if not sym or x is None:
        return None
    event_i = _exact_pos(x.index, str(entry.get("entry_date") or ""))
    if event_i is None:
        return None
    sector_source = sectors.get(ticker_sector.get(sym, ""), market)
    market_values = _align_context(market, x.index)
    sector_values = _align_context(sector_source, x.index)
    arrays = feature_arrays(x, market_values, sector_values)
    values = {
        name: (
            float(arrays[name][event_i])
            if np.isfinite(arrays[name][event_i])
            else float("nan")
        )
        for name in FEATURES
    }
    p_near, p_safe, score = score_locator(artifact, values)
    threshold = float(artifact["manifest"]["threshold"])
    selected = bool(score >= threshold)
    prospective_from = str(x.index[-1].date())
    row = {
        "schema": LEDGER_SCHEMA,
        "model_id": MODEL_ID,
        "authority": "shadow_only",
        "display_only": True,
        "source_as_of": str(source.get("as_of")),
        "observed_as_of": observed_as_of,
        "prospective_from": prospective_from,
        "sym": sym,
        "codex_asof": source.get("codex_asof"),
        "rung": source.get("tailored_rung"),
        "incumbent_entry": {
            "entry_date": str(entry["entry_date"]),
            "entry_idx": int(event_i),
            "entry_px": round(float(x["close"].iloc[event_i]), 4),
        },
        "features": {
            name: (round(value, 10) if math.isfinite(value) else None)
            for name, value in values.items()
        },
        "p_near_low": round(p_near, 10),
        "p_tail_safe": round(p_safe, 10),
        "locator_score": round(score, 10),
        "threshold": threshold,
        "selected": selected,
        "watch_horizon_sessions": WATCH_HORIZON,
        "watch_status": "watching" if selected else "not_selected",
        "remaining_sessions": WATCH_HORIZON if selected else None,
        "action": None,
        "incumbent_grade": None,
        "action_grade": None,
        "last_advanced_as_of": None,
        "note": (
            "Frozen orthogonal terminality locator. Research prioritization only; "
            "never ranks, sizes, gates, alerts, or authorizes an entry."
        ),
    }
    _advance_row(row, x, arrays, observed_as_of)
    return row


def _advance_row(
    row: dict,
    ohlcv: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    as_of: str,
) -> bool:
    """Monotonically advance one watch/action/grade lifecycle."""
    changed = False
    idx = ohlcv.index
    close = ohlcv["close"]
    entry = row.get("incumbent_entry") or {}
    event_i = _exact_pos(idx, str(entry.get("entry_date") or ""))
    if event_i is None:
        return False

    if row.get("incumbent_grade") is None:
        grade = _grade(close, entry)
        if grade is not None:
            row["incumbent_grade"] = grade
            changed = True

    if row.get("selected") and row.get("action") is None:
        prospective_i = _exact_pos(idx, str(row.get("prospective_from") or ""))
        start = max(event_i, prospective_i if prospective_i is not None else event_i)
        deadline = event_i + WATCH_HORIZON
        observed_stop = min(deadline, len(idx) - 1)
        if start <= observed_stop:
            hits = np.flatnonzero(arrays["x_price_rejection"][start: observed_stop + 1])
            if len(hits):
                action_i = start + int(hits[0])
                row["action"] = {
                    "entry_date": str(idx[action_i].date()),
                    "entry_idx": int(action_i),
                    "entry_px": round(float(close.iloc[action_i]), 4),
                    "delay_sessions": int(action_i - event_i),
                    "construction": "fresh_20d_low_rejection",
                }
                row["watch_status"] = "rejection_observed"
                row["remaining_sessions"] = 0
                changed = True
        if row.get("action") is None:
            remaining = max(0, deadline - (len(idx) - 1))
            if row.get("remaining_sessions") != remaining:
                row["remaining_sessions"] = remaining
                changed = True
            status = "expired" if len(idx) - 1 >= deadline else "watching"
            if row.get("watch_status") != status:
                row["watch_status"] = status
                changed = True

    if row.get("action") and row.get("action_grade") is None:
        grade = _grade(close, row["action"])
        if grade is not None:
            row["action_grade"] = grade
            changed = True
    if changed:
        row["last_advanced_as_of"] = as_of
    return changed


def _event_key(row: dict) -> tuple[str, str, str]:
    entry = row.get("incumbent_entry") or {}
    return (
        str(row.get("model_id") or MODEL_ID),
        str(row.get("sym") or ""),
        str(entry.get("entry_date") or ""),
    )


def _source_key(row: dict) -> tuple[str, str, str]:
    entry = row.get("tailored_entry") or {}
    return (MODEL_ID, str(row.get("sym") or ""), str(entry.get("entry_date") or ""))


def _needs_advance(row: dict) -> bool:
    if row.get("incumbent_grade") is None:
        return True
    if not row.get("selected"):
        return False
    if row.get("watch_status") == "watching":
        return True
    return bool(row.get("action")) and row.get("action_grade") is None


def _rewrite_ledger(root: Path | None, rows: list[dict]) -> None:
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    header = (
        f"# personality terminality shadow — schema {LEDGER_SCHEMA}\n"
        "# Keep-first incumbent rows; lifecycle fields advance monotonically on nightly.\n"
        "# Every incumbent is logged. Selected rows are 15-session research watches only.\n"
        "# NEVER ranks, sizes, gates, alerts, or authorizes an entry.\n"
    )
    body = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    fd, tmp = tempfile.mkstemp(dir=str(base), prefix=".terminality_shadow.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(header + (body + "\n" if body else ""))
        os.replace(tmp, ledger_path(root))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _display_row(row: dict, ohlcv: pd.DataFrame | None) -> dict | None:
    if not row.get("selected") or ohlcv is None:
        return None
    status = row.get("watch_status")
    if status == "watching":
        visible = True
    elif status == "rejection_observed" and row.get("action"):
        action_i = _exact_pos(ohlcv.index, row["action"]["entry_date"])
        visible = (
            action_i is not None
            and len(ohlcv) - 1 - action_i <= DISPLAY_SESSIONS_AFTER_ACTION
        )
    else:
        visible = False
    if not visible:
        return None
    action = row.get("action")
    return {
        "schema": STATE_SCHEMA,
        "model_id": MODEL_ID,
        "authority": "shadow_only",
        "display_only": True,
        "status": status,
        "event_date": (row.get("incumbent_entry") or {}).get("entry_date"),
        "prospective_from": row.get("prospective_from"),
        "score": row.get("locator_score"),
        "threshold": row.get("threshold"),
        "remaining_sessions": row.get("remaining_sessions"),
        "action_date": action.get("entry_date") if action else None,
        "action_delay_sessions": action.get("delay_sessions") if action else None,
        "copy": (
            "Research prioritization only. Waits for an observable fresh-low "
            "rejection; never changes entry, rank, or size."
        ),
    }


def _write_state(root: Path | None, state: dict) -> None:
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(base), prefix=".terminality_shadow_state.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1, default=str)
        os.replace(tmp, state_path(root))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Score new incumbent fires and advance the prospective shadow book."""
    try:
        as_of = as_of or pd.Timestamp.now("UTC").date().isoformat()
        gate_open = nightly_advance_enabled()
        artifact = load_artifact(root)
        existing = _load_jsonl(ledger_path(root))
        appended = advanced = score_failures = 0

        market, sectors, ticker_sector = _load_context(root)
        can_score = artifact is not None and market is not None
        if gate_open and can_score:
            seen = {_event_key(row) for row in existing}
            sources = [
                row for row in _load_jsonl(source_ledger_path(root))
                if row.get("fired_tailored")
                and row.get("tailored_entry")
                and str(row.get("as_of") or "") >= SOURCE_AS_OF_FLOOR
            ]
            for source in sources:
                if _source_key(source) in seen:
                    continue
                try:
                    row = _score_source(
                        source, artifact, root, market, sectors, ticker_sector, as_of
                    )
                except Exception as exc:  # noqa: BLE001 — per-event fail-open
                    log.debug(
                        "personality_terminality_shadow: score %s failed (%s)",
                        source.get("sym"), exc,
                    )
                    row = None
                if row is None:
                    score_failures += 1
                    continue
                existing.append(row)
                seen.add(_event_key(row))
                appended += 1

        if gate_open and existing and market is not None:
            for row in existing:
                if not _needs_advance(row):
                    continue
                x = _load_ohlcv(root, str(row.get("sym") or ""))
                if x is None:
                    continue
                sector_source = sectors.get(ticker_sector.get(str(row.get("sym")), ""), market)
                arrays = feature_arrays(
                    x, _align_context(market, x.index), _align_context(sector_source, x.index)
                )
                if _advance_row(row, x, arrays, as_of):
                    advanced += 1

        if gate_open and (appended or advanced):
            existing.sort(
                key=lambda row: (
                    (row.get("incumbent_entry") or {}).get("entry_date") or "",
                    row.get("sym") or "",
                )
            )
            _rewrite_ledger(root, existing)

        selected = [row for row in existing if row.get("selected")]
        statuses: dict[str, int] = {}
        for row in selected:
            status = str(row.get("watch_status") or "unknown")
            statuses[status] = statuses.get(status, 0) + 1
        latest_by_ticker: dict[str, dict] = {}
        for row in sorted(
            existing,
            key=lambda value: (
                (value.get("incumbent_entry") or {}).get("entry_date") or "",
                value.get("sym") or "",
            ),
        ):
            sym = str(row.get("sym") or "")
            latest_by_ticker[sym] = row
        per_ticker: dict[str, dict] = {}
        if artifact is not None:
            for sym, row in latest_by_ticker.items():
                if not row.get("selected") or row.get("watch_status") not in {
                    "watching", "rejection_observed",
                }:
                    continue
                x = _load_ohlcv(root, sym)
                display = _display_row(row, x)
                if display is not None:
                    per_ticker[sym] = display

        manifest = artifact["manifest"] if artifact else {}
        state = {
            "schema": STATE_SCHEMA,
            "model_id": MODEL_ID,
            "authority": "shadow_only",
            "display_only": True,
            "may_rank": False,
            "may_size": False,
            "may_gate": False,
            "may_alert": False,
            "as_of": as_of,
            "generated_utc": pd.Timestamp.now("UTC").isoformat(),
            "gate_open": gate_open,
            "artifact_ok": artifact is not None,
            "train_end": manifest.get("train_end"),
            "threshold": manifest.get("threshold"),
            "target_coverage": manifest.get("target_coverage"),
            "watch_horizon_sessions": WATCH_HORIZON,
            "ledger": {
                "incumbent_events": len(existing),
                "selected": len(selected),
                "not_selected": len(existing) - len(selected),
                "appended_today": appended,
                "advanced_today": advanced,
                "score_failures_today": score_failures,
                "statuses": statuses,
            },
            "per_ticker": per_ticker,
            "note": (
                "Frozen orthogonal PSS-F4H locator over incumbent tailored "
                "Stoch-RSI fires. Top-20% DEV threshold opens a 15-session shadow "
                "watch for a causal fresh-low rejection. F4 contributes no score. "
                "Research/display only; never ranks, sizes, gates, alerts, or "
                "authorizes an entry."
            ),
        }
        _write_state(root, state)
        if appended or advanced:
            log.info(
                "personality_terminality_shadow: +%d events, +%d lifecycle advances",
                appended, advanced,
            )
        return state
    except Exception as exc:  # noqa: BLE001 — additive shadow lane never breaks engine
        log.warning("personality_terminality_shadow update failed (%s)", exc)
        return None
