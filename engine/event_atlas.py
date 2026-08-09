"""engine/event_atlas.py — Signal Episode Atlas W2: aggregation + shrinkage (sea.v1).

DISPLAY / MEASUREMENT tier.  Authority block all-false — this module ranks
nothing, gates nothing, sizes nothing, escalates nothing.  Program:
`research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md` (§2 prior rulings,
§5 statistical honesty).

WHAT THIS IS — AND WHAT IT DELIBERATELY IS NOT
----------------------------------------------
"Not all stocks are alike" is expressed here as an EMPIRICAL-BAYES SHRINKAGE
POSTERIOR, never as per-name indicator selection.  Ranking indicator variants
per name on limited n manufactures results (multiple comparisons; DNR §2 row 69
PTT-W1a two-ruler zero-OOS), so the construction is inverted: ONE frozen
indicator family, ONE frozen class taxonomy, and the name's own history enters
only with weight ``n / (n + k)`` toward its archetype and then the global cell.
The name never chooses its indicator; the atlas quantifies how much the name's
own history is allowed to move the prior — and prints every component n so the
blend is auditable rather than assertable.

Era-pooled inference across the 2010 break is forbidden (DT-R16 #1751): every
cell reports the POOLED read and the POST-2010 sub-cell side by side, and a
sign divergence between them is surfaced as ``era_note``.

Cell key (masterplan §3, frozen)::

    (grid, direction, depth_class, level, washout_len_class, align_class, horizon)

Grains: global · archetype · sector · name.  The site artifact carries COHORT
grains only (global + archetype) for size control; per-name receipts are
computed inline by consumers through :func:`receipt` / :func:`live_state`, so
there is no cross-artifact ordering dependency.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import stock_events as se

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block (invariant)
# ---------------------------------------------------------------------------

AUTHORITY = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
}

SCHEMA = "event_atlas.v1"
LIVE_STATE_SCHEMA = "event_atlas.live_state.v1"

# ---------------------------------------------------------------------------
# Frozen constants
# ---------------------------------------------------------------------------

#: Class axes of a cell (grid/direction/horizon are carried separately).
CLASS_AXES: tuple[str, ...] = ("depth_class", "level", "washout_len_class", "align_class")

#: Horizon column names per grid.
GRID_HORIZONS: dict[str, tuple[str, ...]] = {
    "W": ("13w", "26w"),
    "2B": ("21s", "63s"),
    "3B": ("21s", "63s"),
}

#: Shrinkage constants — FROZEN (masterplan §4: k = 12 toward the archetype).
#: The archetype cell is itself shrunk toward global first, so a thin archetype
#: cannot masquerade as a strong prior for the name.
K_NAME = 12
K_ARCH = 50

#: "live-fresh": the latest event is within this many COMPLETED bars of the
#: grid's last completed bar.  Older than that it is history, not a live read.
LIVE_FRESH_BARS = 3

#: Caveat strings — masterplan §5, carried verbatim in every receipt so the
#: honesty travels with the number instead of living in a doc nobody opens.
CAVEAT_SURVIVORSHIP = (
    "Survivorship: the universe is today's basket membership — backfilled events "
    "inherit survivorship. Disclosed in the artifact metadata "
    "(universe_basis: \"2026 membership (survivor-biased backfill)\"). Widening to "
    "the full panel is a later, separately-adjudicated step."
)
CAVEAT_CLUSTERING = (
    "Clustering: events overlap in time within and across names. n_distinct_years "
    "is printed beside n; promotion-grade inference is pre-specified as "
    "date-blocked bootstrap (never pooled t on raw events)."
)
CAVEAT_ERA = (
    "Era: inference pooled across the 2010 regime break is forbidden (DT-R16 "
    "#1751) — every cell reports the post-2010 sub-cell beside the pooled read."
)
CAVEAT_AUTHORITY = (
    "Measurement tier: a deterministic derivation from price history, not a call "
    "record. Class-conditional base rates only — never pre-onset winner "
    "identification. Ranks nothing, gates nothing, sizes nothing."
)

_EMPTY_CELL: dict[str, Any] = {
    "n": 0, "n_events": 0, "n_names": 0, "n_distinct_years": 0,
    "med": None, "mean": None, "win": None,
    "n_exc": 0, "med_exc": None, "mean_exc": None, "win_exc": None,
}


# ---------------------------------------------------------------------------
# Events access (cached — a receipt per ticker must not re-read the library)
# ---------------------------------------------------------------------------

_CACHE: dict[str, Any] = {"key": None, "df": None}
#: Cohort work is SHARED across names — the global/archetype/sector cells of a
#: class are identical for every name in it, and `build_stock_library` asks for
#: ~700 receipts per run. Without this the per-name receipt re-scans the whole
#: library three times per grid (measured 0.13s/name → ~90s on the render path).
#: Both caches hang off the events fingerprint and are dropped whenever it moves.
_SLICE_CACHE: dict[tuple, Any] = {}


def _fingerprint(data_root: Path | None) -> tuple:
    paths = [se.backfill_path(data_root)]
    d = se.live_dir(data_root)
    if d.exists():
        paths += sorted(d.glob("*.parquet"))
    out = []
    for p in paths:
        try:
            st = p.stat()
            out.append((str(p), int(st.st_mtime_ns), int(st.st_size)))
        except OSError:
            continue
    return tuple(out)


def events(data_root: Path | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """The full event library, memoised on (path, mtime, size) of every part."""
    key = (str(data_root), _fingerprint(data_root))
    if not refresh and _CACHE["key"] == key and _CACHE["df"] is not None:
        return _CACHE["df"]
    df = se.load_events(data_root)
    _CACHE["key"], _CACHE["df"] = key, df
    _SLICE_CACHE.clear()
    return df


def clear_cache() -> None:
    _CACHE["key"], _CACHE["df"] = None, None
    _SLICE_CACHE.clear()


# ---------------------------------------------------------------------------
# Cell statistics
# ---------------------------------------------------------------------------

def _pct(v: Any, nd: int = 1) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return round(f * 100.0, nd) if np.isfinite(f) else None


def _stats_from_arrays(
    raw: np.ndarray,
    exc: np.ndarray | None,
    tickers: np.ndarray,
    years: np.ndarray,
    mask: np.ndarray,
) -> dict:
    """The one aggregation kernel — pure numpy, no frame slicing.

    Frame-level boolean slicing copies all ~35 columns for every cell; a receipt
    asks for dozens of cells per name and `build_stock_library` asks for ~700
    receipts, so the copy is the whole cost.  Every caller funnels here.
    """
    out = dict(_EMPTY_CELL)
    out["n_events"] = int(mask.sum())
    if out["n_events"] == 0:
        return out
    m = mask & np.isfinite(raw)
    out["n"] = int(m.sum())
    if out["n"] == 0:
        return out
    vals = raw[m]
    out["n_names"] = int(len(np.unique(tickers[m])))
    out["n_distinct_years"] = int(len(np.unique(years[m])))
    out["med"] = _pct(float(np.median(vals)))
    out["mean"] = _pct(float(np.mean(vals)))
    out["win"] = round(float((vals > 0).mean()) * 100.0, 1)
    if exc is not None:
        me = mask & np.isfinite(exc)
        out["n_exc"] = int(me.sum())
        if out["n_exc"]:
            e = exc[me]
            out["med_exc"] = _pct(float(np.median(e)))
            out["mean_exc"] = _pct(float(np.mean(e)))
            out["win_exc"] = round(float((e > 0).mean()) * 100.0, 1)
    return out


def cell_stats(df: pd.DataFrame, horizon: str, mask: np.ndarray | None = None) -> dict:
    """Aggregate one cell for one horizon.  MATURED rows only — never imputed.

    ``n`` is the matured count BEHIND the statistics; ``n_events`` is the raw
    membership including still-open windows, so a cell that is mostly immature
    reads as such instead of looking thin for no stated reason.
    """
    if df is None or len(df) == 0:
        return dict(_EMPTY_CELL)
    raw_col, exc_col = f"fwd_{horizon}", f"exc_{horizon}"
    if raw_col not in df.columns:
        return dict(_EMPTY_CELL)
    base = np.ones(len(df), dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    raw = pd.to_numeric(df[raw_col], errors="coerce").to_numpy(dtype=float)
    exc = (pd.to_numeric(df[exc_col], errors="coerce").to_numpy(dtype=float)
           if exc_col in df.columns else None)
    years = pd.to_datetime(df["date"]).dt.year.to_numpy()
    return _stats_from_arrays(raw, exc, df["ticker"].to_numpy(), years, base)


def _era_split(df: pd.DataFrame, horizon: str) -> dict:
    """Pooled cell + the post-2010 sub-cell (DT-R16 — never pooled silently)."""
    pooled = cell_stats(df, horizon)
    post = cell_stats(
        df[df["era"] == "post2010"] if (df is not None and not df.empty) else df,
        horizon,
    )
    return {"pooled": pooled, "post2010": post}


def _mask(df: pd.DataFrame, grid: str, direction: str, class_key: dict) -> pd.DataFrame:
    """Rows of ``df`` in one (grid, direction, class) cell.  Axes left as None
    in ``class_key`` are not constrained (a partially-specified class is a
    legitimate coarser question, not an error)."""
    if df is None or df.empty:
        return df
    m = (df["grid"] == grid) & (df["direction"] == direction)
    for axis in CLASS_AXES:
        want = class_key.get(axis)
        if want is None:
            continue
        col = df[axis]
        if axis == "align_class":
            m &= col.astype("Int64") == int(want)
        else:
            m &= col.astype(str) == str(want)
    return df[m]


class _ClassSlice:
    """Numpy view of ONE class cell, built once and reused for every grain.

    Global / archetype / sector / name cells are all boolean masks over the same
    slice, so the expensive part (isolating the class) happens once per class per
    library version instead of once per name per grain.
    """

    __slots__ = ("n", "ticker", "year", "arch", "sector", "post2010", "raw", "exc")

    def __init__(self, sub: pd.DataFrame, horizons: tuple[str, ...]):
        self.n = int(len(sub))
        self.ticker = sub["ticker"].to_numpy() if self.n else np.array([])
        self.year = (pd.to_datetime(sub["date"]).dt.year.to_numpy()
                     if self.n else np.array([]))
        self.arch = (sub["archetype_at_event"].astype(str).to_numpy()
                     if self.n else np.array([]))
        self.sector = sub["sector"].astype(str).to_numpy() if self.n else np.array([])
        self.post2010 = ((sub["era"].astype(str) == "post2010").to_numpy()
                         if self.n else np.array([], dtype=bool))
        self.raw: dict[str, np.ndarray] = {}
        self.exc: dict[str, np.ndarray] = {}
        for h in horizons:
            self.raw[h] = (
                pd.to_numeric(sub[f"fwd_{h}"], errors="coerce").to_numpy(dtype=float)
                if self.n and f"fwd_{h}" in sub.columns else np.array([])
            )
            self.exc[h] = (
                pd.to_numeric(sub[f"exc_{h}"], errors="coerce").to_numpy(dtype=float)
                if self.n and f"exc_{h}" in sub.columns else np.array([])
            )

    def all_mask(self) -> np.ndarray:
        return np.ones(self.n, dtype=bool)

    def stats(self, horizon: str, mask: np.ndarray) -> dict:
        if self.n == 0 or horizon not in self.raw or len(self.raw[horizon]) == 0:
            return dict(_EMPTY_CELL)
        exc = self.exc.get(horizon)
        return _stats_from_arrays(
            self.raw[horizon],
            exc if (exc is not None and len(exc) == self.n) else None,
            self.ticker, self.year, mask,
        )


def _class_slice(
    data: pd.DataFrame, grid: str, direction: str, class_key: dict
) -> _ClassSlice:
    """The class slice, cached ONLY for the memoised library frame.

    The cache key is the library fingerprint, so it is only valid for the frame
    that fingerprint describes.  A caller that hands in its OWN frame (tests, a
    what-if over a filtered library) must never receive a slice built from a
    different one — identity is the check, and it is cheap.
    """
    cacheable = data is _CACHE["df"] and _CACHE["key"] is not None
    token = (_CACHE["key"], grid, direction,
             tuple(str(class_key.get(a)) for a in CLASS_AXES))
    if cacheable:
        hit = _SLICE_CACHE.get(token)
        if hit is not None:
            return hit
    sub = _mask(data, grid, direction, class_key)
    sl = _ClassSlice(
        sub if sub is not None else pd.DataFrame(),
        GRID_HORIZONS.get(str(grid), ()),
    )
    if cacheable:
        _SLICE_CACHE[token] = sl
    return sl


def aggregate(
    df: pd.DataFrame,
    grain: str = "global",
) -> dict[tuple, dict]:
    """Every non-empty cell at one grain → ``{cell_key: {horizon: era_split}}``.

    ``grain`` ∈ global · archetype · sector · name.  The cell key is the frozen
    tuple ``(grain_value, grid, direction, depth_class, level,
    washout_len_class, align_class)``; horizons live inside the value so both
    horizons of one class share their membership counts.
    """
    if df is None or df.empty:
        return {}
    grain_col = {
        "global": None,
        "archetype": "archetype_at_event",
        "sector": "sector",
        "name": "ticker",
    }[grain]
    group_cols = (["grid", "direction", *CLASS_AXES]
                  if grain_col is None else [grain_col, "grid", "direction", *CLASS_AXES])
    out: dict[tuple, dict] = {}
    for key, g in df.groupby(group_cols, sort=True, dropna=False):
        key = key if isinstance(key, tuple) else (key,)
        grid = key[0] if grain_col is None else key[1]
        cell: dict[str, Any] = {}
        for h in GRID_HORIZONS.get(str(grid), ()):
            cell[h] = _era_split(g, h)
        full_key = key if grain_col is not None else ("__global__", *key)
        out[full_key] = cell
    return out


# ---------------------------------------------------------------------------
# Shrinkage
# ---------------------------------------------------------------------------

def _weight(n: int, k: int) -> float:
    n = int(n or 0)
    return 0.0 if n <= 0 else float(n) / float(n + k)


def _blend_stat(child: float | None, n_child: int, parent: float | None, k: int) -> float | None:
    """``w*child + (1-w)*parent`` with ``w = n/(n+k)``; degrades to whichever leg exists."""
    if child is None:
        return parent
    if parent is None:
        return child
    w = _weight(n_child, k)
    return round(w * float(child) + (1.0 - w) * float(parent), 1)


def blend_cell(child: dict, parent: dict, k: int) -> dict:
    """Shrink a child cell toward a parent cell on every reported statistic."""
    n = int(child.get("n") or 0)
    n_exc = int(child.get("n_exc") or 0)
    return {
        "med": _blend_stat(child.get("med"), n, parent.get("med"), k),
        "mean": _blend_stat(child.get("mean"), n, parent.get("mean"), k),
        "win": _blend_stat(child.get("win"), n, parent.get("win"), k),
        "med_exc": _blend_stat(child.get("med_exc"), n_exc, parent.get("med_exc"), k),
        "mean_exc": _blend_stat(child.get("mean_exc"), n_exc, parent.get("mean_exc"), k),
        "win_exc": _blend_stat(child.get("win_exc"), n_exc, parent.get("win_exc"), k),
        "w": round(_weight(n, k), 3),
        "w_exc": round(_weight(n_exc, k), 3),
        "n_child": n,
        "k": k,
    }


def _era_note(pooled: dict, post: dict, n_post: int | None = None) -> str | None:
    """Surface a POOLED-vs-POST-2010 sign divergence in words (DT-R16).

    ``n_post`` is the support behind the post-2010 read.  A blended posterior
    carries no ``n`` of its own — its evidence is the cell it leans on — so the
    caller passes it; a raw cell supplies its own.  A note with no n would be
    the divergence asserted rather than shown.
    """
    a, b = pooled.get("med"), post.get("med")
    if a is None or b is None:
        return None
    if (float(a) > 0) == (float(b) > 0):
        return None
    n = n_post if n_post is not None else post.get("n")
    sign = "negative" if float(b) < 0 else "positive"
    return f"post-2010 reads {sign} on n={int(n or 0)}"


# ---------------------------------------------------------------------------
# Receipt
# ---------------------------------------------------------------------------

def receipt(
    ticker: str,
    grid: str,
    direction: str,
    class_key: dict,
    *,
    df: pd.DataFrame | None = None,
    data_root: Path | None = None,
    archetype: str | None = None,
    sector: str | None = None,
) -> dict:
    """The matching-episode receipt for one (name, class) — hierarchical, auditable.

    Two-stage shrinkage (masterplan §4)::

        arch_post = blend(archetype_cell, global_cell, k=50)
        name_post = blend(name_cell,      arch_post,   k=12)

    Every component's ``n`` travels with the number, both eras are reported, and
    the survivorship + clustering caveats are attached verbatim — a receipt that
    cannot be audited is an assertion.
    """
    data = events(data_root) if df is None else df
    class_key = {k: class_key.get(k) for k in CLASS_AXES}
    out: dict[str, Any] = {
        "ticker": ticker,
        "grid": grid,
        "direction": direction,
        "class_key": class_key,
        "taxonomy_version": se.TAXONOMY_VERSION,
        "tier": "display",
        "authority": dict(AUTHORITY),
        "k_name": K_NAME,
        "k_arch": K_ARCH,
        "horizons": {},
        "caveats": {
            "survivorship": CAVEAT_SURVIVORSHIP,
            "clustering": CAVEAT_CLUSTERING,
            "era": CAVEAT_ERA,
            "authority": CAVEAT_AUTHORITY,
        },
    }
    if data is None or data.empty:
        out["reason"] = "no_event_library"
        return out

    name_rows = data[data["ticker"] == ticker]
    if archetype is None:
        archetype = (
            str(name_rows["archetype_at_event"].iloc[-1])
            if len(name_rows) else "archetype_unknown"
        )
    if sector is None:
        sector = str(name_rows["sector"].iloc[-1]) if len(name_rows) else "sector_unknown"
    out["archetype"] = archetype
    out["sector"] = sector

    sl = _class_slice(data, grid, direction, class_key)
    base = sl.all_mask()
    m_arch = (sl.arch == str(archetype)) if sl.n else base
    m_sect = (sl.sector == str(sector)) if sl.n else base
    m_name = (sl.ticker == ticker) if sl.n else base

    for h in GRID_HORIZONS.get(str(grid), ()):
        blocks = {}
        for era in ("pooled", "post2010"):
            era_mask = base if era == "pooled" else (sl.post2010 if sl.n else base)
            g_cell = sl.stats(h, base & era_mask)
            a_cell = sl.stats(h, m_arch & era_mask)
            s_cell = sl.stats(h, m_sect & era_mask)
            n_cell = sl.stats(h, m_name & era_mask)
            arch_post = blend_cell(a_cell, g_cell, K_ARCH)
            name_post = blend_cell(n_cell, arch_post, K_NAME)
            blocks[era] = {
                "global": g_cell,
                "archetype": a_cell,
                "sector": s_cell,
                "name": n_cell,
                "arch_post": arch_post,
                "name_post": name_post,
                "n_global": g_cell["n"],
                "n_archetype": a_cell["n"],
                "n_sector": s_cell["n"],
                "n_name": n_cell["n"],
            }
        block = dict(blocks["pooled"])
        block["post2010"] = blocks["post2010"]
        post = blocks["post2010"]
        # The n quoted is the deepest post-2010 cell the posterior actually
        # leans on: the name's own when it has one, else its cohort's.
        n_post = post["n_name"] or post["n_archetype"] or post["n_global"]
        block["era_note"] = _era_note(
            blocks["pooled"]["name_post"], post["name_post"], n_post
        )
        out["horizons"][h] = block
    return out


# ---------------------------------------------------------------------------
# Live state — what the surfaces consume
# ---------------------------------------------------------------------------

def live_state(
    ticker: str,
    close: pd.Series | None = None,
    *,
    df: pd.DataFrame | None = None,
    data_root: Path | None = None,
) -> dict | None:
    """Per-grid latest event + freshness + current alignment + the class receipt.

    ``close`` may be passed by a caller that already holds the daily series
    (``build_stock_library._one``) — re-loading it there would be pure waste.
    Returns None when the name has no readable history.  Never raises.
    """
    try:
        return _live_state_inner(ticker, close, df, data_root)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("event_atlas.live_state(%s) failed: %s", ticker, e)
        return None


def _live_state_inner(
    ticker: str,
    close: pd.Series | None,
    df: pd.DataFrame | None,
    data_root: Path | None,
) -> dict | None:
    if close is None:
        close = se._load_close(ticker, data_root)
    if close is None or len(close) < se.MIN_DAILY_BARS:
        return None
    data = events(data_root) if df is None else df
    name_rows = data[data["ticker"] == ticker] if (data is not None and not data.empty) else None

    daily = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    out: dict[str, Any] = {
        "schema": LIVE_STATE_SCHEMA,
        "ticker": ticker,
        "as_of": str(daily.index[-1].date()),
        "taxonomy_version": se.TAXONOMY_VERSION,
        "tier": "display",
        "grids": {},
    }
    align_now = 0
    bull_now: dict[str, bool | None] = {}
    bars_index: dict[str, pd.DatetimeIndex] = {}

    for g in se.GRIDS:
        bars = se.grid_series(daily, g)
        if bars is None or len(bars) < se.MIN_DEPTH_OBS:
            bull_now[g] = None
            continue
        line, sig = se._line_sig(bars)
        if len(line) == 0:
            bull_now[g] = None
            continue
        bars_index[g] = line.index
        last_bull = bool(line.iloc[-1] > sig.iloc[-1])
        bull_now[g] = last_bull
        if last_bull:
            align_now += 1

    out["align_now"] = align_now
    out["bull_now"] = bull_now

    if name_rows is None or name_rows.empty:
        out["reason"] = "no_events_for_name"
        return out

    for g in se.GRIDS:
        rows = name_rows[name_rows["grid"] == g]
        if rows.empty:
            continue
        latest = rows.sort_values("date").iloc[-1]
        idx = bars_index.get(g)
        bars_since = None
        if idx is not None and len(idx):
            pos = int(idx.searchsorted(pd.Timestamp(latest["date"]), side="right")) - 1
            if pos >= 0:
                bars_since = int(len(idx) - 1 - pos)
        # Native Python types only — this dict is JSON-serialised straight into
        # the per-stock record, and a numpy scalar there is a json.dumps failure
        # (or a silently stringified "2") rather than a value.
        class_key = {
            a: (_i(latest[a]) if a == "align_class" else str(latest[a]))
            for a in CLASS_AXES
        }
        out["grids"][g] = {
            "date": str(pd.Timestamp(latest["date"]).date()),
            "direction": str(latest["direction"]),
            "depth_pctile": _f(latest.get("depth_pctile")),
            "depth_class": str(latest["depth_class"]),
            "level": str(latest["level"]),
            "washout_len": _i(latest.get("washout_len")),
            "washout_len_class": str(latest["washout_len_class"]),
            "align_class": _i(latest.get("align_class")),
            "era": str(latest.get("era") or ""),
            "regime_bucket": str(latest.get("regime_bucket") or ""),
            "archetype_at_event": str(latest.get("archetype_at_event") or "archetype_unknown"),
            "bars_since": bars_since,
            "live_fresh": bool(bars_since is not None and bars_since <= LIVE_FRESH_BARS),
            "bull_now": bull_now.get(g),
            "receipt": receipt(
                ticker, g, str(latest["direction"]), class_key,
                df=data, data_root=data_root,
                archetype=str(latest.get("archetype_at_event") or "archetype_unknown"),
                sector=str(latest.get("sector") or "sector_unknown"),
            ),
        }
    return out


def _f(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _i(v: Any) -> int | None:
    f = _f(v)
    return None if f is None else int(f)


# ---------------------------------------------------------------------------
# Site artifact — COHORT grains only (per-name receipts are computed inline)
# ---------------------------------------------------------------------------

def _key_str(key: tuple) -> str:
    return "|".join(str(x) for x in key)


def build_atlas(
    df: pd.DataFrame | None = None,
    data_root: Path | None = None,
    *,
    min_n: int = 5,
    refresh_cache: bool = False,
) -> dict:
    """Cohort-grain atlas payload for `site/stockdata/event_atlas.json`.

    Global + archetype grains only.  Per-name receipts are computed inline by
    consumers via :func:`receipt` / :func:`live_state`, so this artifact carries
    no ordering dependency on the per-name build.

    ``min_n`` drops cells with fewer than that many EVENTS from the shipped file
    (2.2MB → 1.6MB at the default 5).  Nothing is hidden by it: the full library
    is on disk and :func:`receipt` reads it directly, so the artifact is a
    convenience index, not the source of truth — and the floor is stamped into
    the payload as ``min_cell_events`` so a reader can see it.

    ``refresh_cache`` forces a re-read of the parts — the nightly hook builds the
    atlas immediately after appending, and a same-second write can land inside
    the mtime fingerprint's resolution.
    """
    t0 = time.time()
    data = events(data_root, refresh=refresh_cache) if df is None else df
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "taxonomy_version": se.TAXONOMY_VERSION,
        "tier": "display",
        "authority": dict(AUTHORITY),
        "universe_basis": se.UNIVERSE_BASIS,
        "masterplan": "research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md",
        "caveats": {
            "survivorship": CAVEAT_SURVIVORSHIP,
            "clustering": CAVEAT_CLUSTERING,
            "era": CAVEAT_ERA,
            "authority": CAVEAT_AUTHORITY,
        },
        "shrinkage": {"k_name": K_NAME, "k_arch": K_ARCH},
        "min_cell_events": int(min_n),
        "class_axes": list(CLASS_AXES),
        "grid_horizons": {k: list(v) for k, v in GRID_HORIZONS.items()},
        "cells": {"global": {}, "archetype": {}},
    }
    if data is None or data.empty:
        payload["as_of"] = None
        payload["n_events"] = 0
        payload["elapsed_s"] = round(time.time() - t0, 2)
        return payload

    payload["as_of"] = str(pd.Timestamp(data["date"].max()).date())
    payload["n_events"] = int(len(data))
    payload["n_names"] = int(data["ticker"].nunique())

    for grain in ("global", "archetype"):
        cells = aggregate(data, grain)
        bucket = payload["cells"][grain]
        for key, horizons in cells.items():
            emit = {}
            for h, split in horizons.items():
                if int(split["pooled"]["n_events"] or 0) < min_n:
                    continue
                emit[h] = {
                    "pooled": split["pooled"],
                    "post2010": split["post2010"],
                    "era_note": _era_note(split["pooled"], split["post2010"]),
                }
            if emit:
                bucket[_key_str(key)] = emit
    payload["n_cells"] = sum(len(v) for v in payload["cells"].values())
    payload["elapsed_s"] = round(time.time() - t0, 2)
    return payload


def write_site_artifact(atlas: dict, site_root: Path | None = None) -> Path:
    """Write `site/stockdata/event_atlas.json`.  Returns the written path."""
    from lib import config
    if site_root is None:
        site_root = config.ROOT / config.load()["storage"]["site_dir"]
    out_dir = site_root / "stockdata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "event_atlas.json"
    body = json.dumps(atlas, separators=(",", ":"), default=str)
    out_path.write_text(body + "\n", encoding="utf-8")
    log.info("event_atlas: wrote %s (%dKB)", out_path, len(body.encode()) // 1024)
    return out_path
