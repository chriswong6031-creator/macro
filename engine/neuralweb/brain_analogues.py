"""engine.neuralweb.brain_analogues — US historical-analogue retrieval for the brain.

CLASSIFICATION: read-only retrieval helper for the Mastermind brain gateway.
This module holds the FUNCTION and its Anthropic tool schema only; the gateway
owns dispatch, the tool allowlist, and tier gating. Nothing here writes a file,
opens a socket, or calls an LLM.

SCHEMA: ``brain.analogues.v1`` (see the ``get_historical_analogues`` docstring
for the full key set).

TIER: display / context — DISPLAY-ONLY. This is retrieval, not scoring. It
answers "which dated days does the desk's own measured state most resemble, and
what did the tape do afterwards" and nothing else. It never emits a signal, a
rank, a size, a gate, a forecast, or a probability, and there is no fused regime
verdict or composite label anywhere on the output path — MSP-R2 kills fused
regime scorecards. The one number that is not a raw measured level is the
retrieval ``distance``, which is the sanctioned China precedent
(``scripts/build_china_analogs.py`` ships it): a distance over states the desk
already computes and already displays, with uniform post-z weights, no fitted
parameters, and therefore nothing that needs a promotion gauntlet. The engine
matches; the chat model narrates.

SUBSTRATE HAZARD — regime_history vs regime_vector
--------------------------------------------------
The regime substrate here is ``data/regime/regime_history.parquet`` (the full
daily history back to 1927, rewritten nightly by ``engine/run.py``). It is NOT
``data/regime/regime_vector.parquet``, which holds only the handful of most
recent rows; reaching for the vector when you want history is a #1026-class
hazard flagged in that module's own docstring and would silently collapse the
candidate pool to a few weeks while every other guard here still passed.

METHOD (mirrors scripts/build_china_analogs.py, extended to the US inputs)
-------------------------------------------------------------------------
Feature vector, 10 dimensions, uniform weight after z-scoring:

  z-scored (7)   growth_score, inflation_score, 2s10s level, 2s10s 63-obs
                 change, 10y3m level, log(VIX), breadth pct_above_200
  mismatch (3)   quad, liquidity, cycle — each mismatched category contributes
                 exactly 1.0 to the Euclidean distance

Distance: Euclidean over the combined vector.

Query = the latest COMPLETE day, i.e. the most recent date carrying every
feature. A partial final row is never matched on. When one of the inputs
publishes a day late — DGS10 and the FRED curve series routinely trail the
regime history by a session — the query degrades to yesterday's state STAMPED
HONESTLY rather than darkening the tool: ``asof`` names the day actually used
and a top-level ``query_lag_note`` appears (and appears ONLY then), which is the
market packet's per-section freshness idiom. The fallback is bounded: if no day
in the trailing ``QUERY_LAG_MAX_ROWS`` rows is complete, the substrate is broken
rather than merely late and the call fails soft.

Candidacy: a day is eligible only when EVERY feature is present on that exact
date — no imputation, no forward fill, so the eligible window is bounded by the
shortest input (VIX, 1990-01-02 onward on the live store). The window actually
searched is reported as ``coverage``; ``n_candidates`` is the number of days
compared after the time exclusion below.

Constraints (China constants, unchanged):
  - time exclusion: candidates must sit >= 120 calendar days before the query,
    so the answer is never "today looks like last month";
  - greedy diversity: skip a candidate within 60 calendar days of one already
    selected, so eight episodes are eight episodes and not one week sampled
    eight times.
  - "unknown" liquidity / cycle is treated as an ordinary category (it can only
    ever mismatch a known query value); an unknown or missing ``quad`` makes the
    row ineligible outright, exactly as the China engine has it.

Z-statistics are population stats over the whole eligible window, which does
mean the z of an episode is computed with knowledge of later days. That is
retrieval-only bookkeeping — it decides which dated rows to show, never a
forward number — and it is the shipped China idiom, so it is mirrored here
rather than re-litigated. The FORWARD paths are strictly point-in-time: each is
anchored to the first observation STRICTLY AFTER the episode date and reads only
observations after it, and an episode whose window runs off the end of history
reports None for that horizon while still appearing in the list.

FAIL-SOFT is the whole contract. This module is imported by the API process
(brain_gateway) and called on a request path, where pandas/pyarrow may be absent
from the venv and a dev checkout may have no ``data/`` at all. pandas is
imported lazily inside the build, the build is wrapped whole, and any failure
returns ``{"schema": ..., "error": "analogues_unavailable", "detail": ...}``.
It never raises.

CACHE: in-process, keyed on the (path, mtime) pair of every source file plus the
limit — a source that appears or vanishes changes the key as surely as an edited
one, because a missing file keys as None rather than being skipped. No TTL is
needed and none is used: the payload is a pure function of the files, reads no
clock, and persists nothing, so there is no clock reading to go stale.
"""
from __future__ import annotations

import copy
import logging
import math
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
SCHEMA = "brain.analogues.v1"
ERROR_CODE = "analogues_unavailable"

K = 12                      # nearest neighbours computed before the limit slice
MAX_LIMIT = 8               # episodes ever returned to the model
TIME_EXCLUSION_DAYS = 120   # calendar days before the query a candidate must sit
DIVERSITY_DAYS = 60         # calendar days between two selected episodes
SPREAD_CHANGE_OBS = 63      # observations back for the 2s10s change feature

# How far back the query may fall when the newest rows are incomplete. A FRED
# series publishing a session late is NORMAL and must degrade to a stamped
# "state as of yesterday"; nothing complete in this trailing window means the
# substrate is broken rather than late, which is a fail-soft.
QUERY_LAG_MAX_ROWS = 10

FWD_SPX_SESSIONS: tuple[int, ...] = (5, 20, 60)
FWD_LEVEL_SESSIONS = 20     # US10Y (bp) and VIX (points) horizon

DISCLAIMER = (
    "Historical pattern echoes — context only, never signals, forecasts, or "
    "probabilities. Small samples; the desk reads these as rhymes, not rules."
)

# Regime substrate. See the SUBSTRATE HAZARD note above: history, never vector.
_REGIME_REL = "data/regime/regime_history.parquet"

# Every file the payload depends on, in cache-key order. A file listed here but
# unused by a given build still belongs in the key (the VIX fallback).
_SOURCE_RELS: tuple[str, ...] = (
    _REGIME_REL,
    "data/breadth/breadth.parquet",
    "data/fred/T10Y2Y.parquet",
    "data/fred/T10Y3M.parquet",
    "data/fred/DGS10.parquet",
    "data/yahoo/_VIX.parquet",
    "data/fred/VIXCLS.parquet",
    "data/yahoo/_GSPC.parquet",
)

# (relative path, column) candidates, first resolvable wins.
_SRC_2S10S = (("data/fred/T10Y2Y.parquet", "spread_2s10s"),)
_SRC_10Y3M = (("data/fred/T10Y3M.parquet", "spread_10y3m"),)
_SRC_US10Y = (("data/fred/DGS10.parquet", "us10y"),)
_SRC_BREADTH = (("data/breadth/breadth.parquet", "pct_above_200"),)
_SRC_SPX = (("data/yahoo/_GSPC.parquet", "close"),
            ("data/yahoo/_GSPC.parquet", "close_price"))
_SRC_VIX = (("data/yahoo/_VIX.parquet", "close"),
            ("data/yahoo/_VIX.parquet", "close_price"),
            ("data/fred/VIXCLS.parquet", "vix_close"))

# Numeric (z-scored) feature columns, in vector order.
_Z_COLS: tuple[str, ...] = (
    "growth_score",
    "inflation_score",
    "spread_2s10s",
    "spread_2s10s_chg63",
    "spread_10y3m",
    "log_vix",
    "pct_above_200",
)
# Categorical mismatch columns, in vector order.
_CAT_COLS: tuple[str, ...] = ("quad", "liquidity", "cycle")

# A quad in this set (case-folded) makes the row ineligible.
_QUAD_NULLS = frozenset({"", "unknown", "none", "nan", "nat", "<na>"})

_CACHE: dict[tuple, dict] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 32


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _error(detail: str) -> dict:
    """The one shape every failure degrades to. Callers never see an exception."""
    return {"schema": SCHEMA, "error": ERROR_CODE, "detail": str(detail)[:200]}


def _r(value: Any, digits: int) -> float | None:
    """Round to `digits`, mapping None/NaN/inf to None (never a fake zero)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, digits)


def _cache_key(root: Path, limit: int) -> tuple:
    pairs: list[tuple[str, float | None]] = []
    for rel in _SOURCE_RELS:
        p = root / rel
        try:
            pairs.append((rel, p.stat().st_mtime))
        except OSError:
            pairs.append((rel, None))
    return (str(root), int(limit), tuple(pairs))


def _load_frame(path: Path, pd):
    """Read a parquet into a date-indexed, de-duplicated, sorted frame or None."""
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[-1] if isinstance(c, tuple) else c for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _load_series(root: Path, candidates: tuple, pd):
    """First (rel, column) pair that resolves to a non-empty numeric series."""
    for rel, col in candidates:
        df = _load_frame(root / rel, pd)
        if df is None or col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce").dropna().astype(float)
        if len(s):
            return s
    return None


def _cat_strings(series, pd):
    """Category column -> plain object array of stripped strings ('' for NA).

    The stores land these as Arrow-backed strings; normalising to python str up
    front keeps the mismatch comparison dtype-independent.
    """
    return series.astype(object).where(~pd.isna(series), "").map(
        lambda v: str(v).strip()
    )


# --------------------------------------------------------------------------- #
# Forward paths — PIT-anchored, off-history returns None
# --------------------------------------------------------------------------- #

def _anchor_slice(series, anchor):
    """Observations strictly after `anchor`, or None when PIT-unusable.

    None means: no series, the anchor predates the series start (anchoring to
    the first available observation would fabricate a return measured from a
    date years after the episode), or the anchor sits at/past the series end.
    """
    if series is None or len(series) == 0:
        return None
    if anchor < series.index.min():
        return None
    after = series.loc[series.index > anchor]
    if len(after) == 0:
        return None
    return after


def _fwd_log_return(series, anchor, sessions: int) -> float | None:
    after = _anchor_slice(series, anchor)
    if after is None or sessions >= len(after):
        return None
    start = float(after.iloc[0])
    end = float(after.iloc[sessions])
    if start <= 0 or end <= 0:
        return None
    return math.log(end / start)


def _fwd_level_change(series, anchor, sessions: int, scale: float = 1.0) -> float | None:
    after = _anchor_slice(series, anchor)
    if after is None or sessions >= len(after):
        return None
    return (float(after.iloc[sessions]) - float(after.iloc[0])) * scale


def _fwd_paths(anchor, spx, us10y, vix) -> dict:
    """The five forward numbers. A None horizon is reported, never dropped."""
    out: dict = {}
    for h in FWD_SPX_SESSIONS:
        out[f"spx_h{h}"] = _r(_fwd_log_return(spx, anchor, h), 4)
    # DGS10 is in percentage points; the desk reads rate moves in basis points.
    out[f"us10y_bp_h{FWD_LEVEL_SESSIONS}"] = _r(
        _fwd_level_change(us10y, anchor, FWD_LEVEL_SESSIONS, 100.0), 1
    )
    out[f"vix_pts_h{FWD_LEVEL_SESSIONS}"] = _r(
        _fwd_level_change(vix, anchor, FWD_LEVEL_SESSIONS), 2
    )
    return out


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def _build(root: Path, limit: int) -> dict:
    """Assemble the payload. Raises on any substrate problem; the public entry
    point converts every exception into the fail-soft error dict."""
    import numpy as np           # noqa: PLC0415 — lazy: API venv may lack it
    import pandas as pd          # noqa: PLC0415

    reg = _load_frame(root / _REGIME_REL, pd)
    if reg is None:
        raise FileNotFoundError("regime_history.parquet missing")
    needed = ("growth_score", "inflation_score", "quad", "liquidity", "cycle")
    missing = [c for c in needed if c not in reg.columns]
    if missing:
        raise KeyError(f"regime_history lacks {','.join(missing)}")
    if len(reg) == 0:
        raise ValueError("regime_history is empty")

    s_2s10s = _load_series(root, _SRC_2S10S, pd)
    s_10y3m = _load_series(root, _SRC_10Y3M, pd)
    s_vix = _load_series(root, _SRC_VIX, pd)
    s_breadth = _load_series(root, _SRC_BREADTH, pd)
    for name, s in (("2s10s", s_2s10s), ("10y3m", s_10y3m),
                    ("vix", s_vix), ("breadth", s_breadth)):
        if s is None:
            raise FileNotFoundError(f"{name} feature series unavailable")

    # Forward-path series (missing ones degrade to null horizons, not an error).
    s_spx = _load_series(root, _SRC_SPX, pd)
    s_us10y = _load_series(root, _SRC_US10Y, pd)

    idx = reg.index
    feat = pd.DataFrame(index=idx)
    feat["growth_score"] = pd.to_numeric(reg["growth_score"], errors="coerce")
    feat["inflation_score"] = pd.to_numeric(reg["inflation_score"], errors="coerce")
    # Exact-date alignment only. A forward fill here would quietly hand a stale
    # rate to a day the store has no observation for; an absent day is simply
    # not a candidate.
    feat["spread_2s10s"] = s_2s10s.reindex(idx)
    # diff() on the source series = 63 OBSERVATIONS back (never a calendar
    # window straddling holes), and it reads only the past.
    feat["spread_2s10s_chg63"] = s_2s10s.diff(SPREAD_CHANGE_OBS).reindex(idx)
    feat["spread_10y3m"] = s_10y3m.reindex(idx)
    feat["vix"] = s_vix.reindex(idx)
    feat["pct_above_200"] = s_breadth.reindex(idx)
    vix_pos = feat["vix"] > 0
    feat["log_vix"] = np.log(feat["vix"].where(vix_pos))

    for col in _CAT_COLS:
        feat[col] = _cat_strings(reg[col], pd)

    quad_ok = ~feat["quad"].str.lower().isin(_QUAD_NULLS)
    numeric_ok = feat[list(_Z_COLS)].notna().all(axis=1)
    eligible = feat.loc[quad_ok & numeric_ok & vix_pos.fillna(False)].copy()
    if len(eligible) == 0:
        raise ValueError("no eligible days after feature-presence filter")

    # Query = the latest COMPLETE day. A partial final row is never matched on
    # (that would mean comparing today's half-state against fully-featured
    # history), but a late-publishing input must not darken the tool either: the
    # query walks back to the newest complete day inside QUERY_LAG_MAX_ROWS and
    # the lag is disclosed in the payload. Beyond that window the substrate is
    # broken rather than late — fail soft.
    latest_row_date = idx.max()
    query_date = eligible.index.max()
    recent = idx[-QUERY_LAG_MAX_ROWS:]
    if query_date not in recent:
        raise ValueError(
            f"no complete state in the trailing {QUERY_LAG_MAX_ROWS} rows "
            f"(latest complete {query_date.date()}, history ends "
            f"{latest_row_date.date()})"
        )
    query = eligible.loc[query_date]
    # Set ONLY when the query is not the last row of history, so the model can
    # never read a lag note as decoration on a current reading.
    query_lag_note = None
    if query_date != latest_row_date:
        query_lag_note = (
            f"state as of {query_date.date()} — latest day with the full "
            f"feature set (history runs to {latest_row_date.date()})"
        )

    zmat = eligible[list(_Z_COLS)].to_numpy(dtype=float)
    # Population z over the whole eligible window (China idiom — retrieval
    # bookkeeping only, see METHOD note in the module docstring).
    mean = zmat.mean(axis=0)
    std = zmat.std(axis=0, ddof=0)
    std = np.where((std == 0) | ~np.isfinite(std), 1.0, std)   # degenerate guard
    zmat = (zmat - mean) / std

    q_cats = {c: str(query[c]) for c in _CAT_COLS}
    # Each mismatched category contributes exactly 1.0; the query's own
    # mismatch terms are 0 by construction, so squared mismatch == mismatch.
    cat_mm = np.stack(
        [(eligible[c].to_numpy(dtype=object) != q_cats[c]).astype(float)
         for c in _CAT_COLS],
        axis=1,
    )

    # Time exclusion, applied after the z-stats so the population is the whole
    # eligible window (not a window that shrinks with the exclusion).
    cutoff = query_date - pd.Timedelta(days=TIME_EXCLUSION_DAYS)
    pool_mask = (eligible.index <= cutoff).astype(bool)
    pool_idx = eligible.index[pool_mask]
    n_candidates = int(pool_mask.sum())

    q_pos = int(eligible.index.get_indexer([query_date])[0])
    q_vec = zmat[q_pos]

    episodes: list[dict] = []
    if n_candidates:
        pool_z = zmat[pool_mask]
        pool_mm = cat_mm[pool_mask]
        diffs = pool_z - q_vec
        dist = np.sqrt((diffs ** 2).sum(axis=1) + pool_mm.sum(axis=1))
        order = np.argsort(dist, kind="stable")

        selected: list[Any] = []
        for pos in order:
            if len(selected) >= K:
                break
            date = pool_idx[pos]
            if any(abs((date - sel).days) < DIVERSITY_DAYS for sel in selected):
                continue
            selected.append(date)
            row = eligible.loc[date]
            episodes.append({
                "date": str(date.date()),
                "distance": _r(dist[pos], 3),
                "quad": str(row["quad"]),
                "liquidity": str(row["liquidity"]),
                "cycle": str(row["cycle"]),
                "spread_2s10s": _r(row["spread_2s10s"], 2),
                "vix": _r(row["vix"], 2),
                "breadth_pct_above_200": _r(row["pct_above_200"], 2),
                "fwd": _fwd_paths(date, s_spx, s_us10y, s_vix),
            })
        episodes = episodes[:limit]

    payload: dict = {
        "schema": SCHEMA,
        "asof": str(query_date.date()),
        "coverage": f"{eligible.index.min().date()}–{eligible.index.max().date()}",
        "n_candidates": n_candidates,
        "query": {
            "date": str(query_date.date()),
            "quad": q_cats["quad"],
            "liquidity": q_cats["liquidity"],
            "cycle": q_cats["cycle"],
            "growth_z": _r(q_vec[_Z_COLS.index("growth_score")], 3),
            "inflation_z": _r(q_vec[_Z_COLS.index("inflation_score")], 3),
            "spread_2s10s": _r(query["spread_2s10s"], 2),
            "spread_10y3m": _r(query["spread_10y3m"], 2),
            "vix": _r(query["vix"], 2),
            "breadth_pct_above_200": _r(query["pct_above_200"], 2),
        },
        "episodes": episodes,
        "disclaimer": DISCLAIMER,
    }
    if query_lag_note:
        payload["query_lag_note"] = query_lag_note
    return payload


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def get_historical_analogues(root: Path, *, limit: int = 8) -> dict:
    """Dated historical episodes whose measured state most resembles today's.

    Returns (schema ``brain.analogues.v1``)::

        {"schema", "asof", "coverage", "n_candidates",
         "query":    {date, quad, liquidity, cycle, growth_z, inflation_z,
                      spread_2s10s, spread_10y3m, vix, breadth_pct_above_200},
         "episodes": [{date, distance, quad, liquidity, cycle, spread_2s10s,
                       vix, breadth_pct_above_200,
                       "fwd": {spx_h5, spx_h20, spx_h60,
                               us10y_bp_h20, vix_pts_h20}}, ...],
         "disclaimer",
         "query_lag_note": present ONLY when asof is not the last row of the
                           regime history — a late-publishing input degrades the
                           query to the newest COMPLETE day and says so, e.g.
                           "state as of 2026-07-28 — latest day with the full
                           feature set (history runs to 2026-07-29)"}

    ``coverage`` is the eligible window (first–last day on which every feature
    is present); ``n_candidates`` is how many of those days were actually
    compared, i.e. after the 120-calendar-day exclusion around the query.
    ``distance`` is retrieval metadata (smaller = closer in feature space), not
    a score, a rank, or any measure of certainty. ``fwd`` numbers are log returns
    (SPX), basis points (US10Y) and index points (VIX); a horizon running past
    the end of the stored series is ``None`` and the episode still appears.

    `limit` is clamped to 1..8. Deterministic, offline, and non-raising: any
    failure returns ``{"schema", "error": "analogues_unavailable", "detail"}``.
    """
    try:
        lim = int(limit)
    except (TypeError, ValueError):
        lim = MAX_LIMIT
    lim = max(1, min(MAX_LIMIT, lim))

    try:
        root = Path(root)
        key = _cache_key(root, lim)
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit is not None:
            return copy.deepcopy(hit)
        payload = _build(root, lim)
        # Only successes are cached: a transient read failure must not pin the
        # error dict until a source file happens to change.
        with _CACHE_LOCK:
            if len(_CACHE) > _CACHE_MAX:
                _CACHE.clear()
            _CACHE[key] = payload
        return copy.deepcopy(payload)
    except Exception as exc:  # noqa: BLE001 — fail-soft is the contract
        log.debug("brain_analogues: unavailable (%s: %s)", type(exc).__name__, exc)
        return _error(f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- #
# Anthropic tool schema (shape mirrors brain_market_intel.EVENTS_TOOL_SCHEMA)
# --------------------------------------------------------------------------- #
ANALOGUES_TOOL_SCHEMA: dict = {
    "name": "get_historical_analogues",
    "description": (
        "Look up dated historical episodes whose measured US macro state most "
        "resembled today's — the desk's growth and inflation readings, quad, "
        "liquidity and cycle labels, the 2s10s and 3m10y curve, VIX, and "
        "breadth — together with what the tape actually did next (S&P 500 log "
        "return over 5, 20 and 60 sessions; 10-year yield in basis points and "
        "VIX in points over 20 sessions). Call when the user asks what this "
        "setup looks like historically, when the market last looked like this, "
        "for precedents, analogues, or 'has this happened before'. This is "
        "DISPLAY-TIER CONTEXT ONLY: a handful of dated rhymes retrieved by "
        "feature-space distance, not a signal, forecast, base rate, or "
        "probability. Cite the dates, say the sample is small, and never turn "
        "these episodes into odds, a hit rate, or a recommendation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max episodes to return (1..8, default 8)",
            },
        },
        "required": [],
    },
}
