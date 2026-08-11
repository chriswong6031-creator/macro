"""WINNER HEALTH — nightly maturation read for extended US winners (DISPLAY TIER).

WHAT THIS IS. The nightly half of TOP ANATOMY W1
(`research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md` §5-W1). It answers one question
about a name a human already owns: *has this move changed character?* — and
answers it in groups, in plain words, beside the historical record of runs that
looked like it. The surface contract it produces is `winner_health.v1`, pinned in
`research/top_anatomy/W1_SURFACE_DESIGN_SPEC.md` §5 and rendered by
`templates/winner_health.html.j2`.

TIER AND AUTHORITY. Display tier, ZERO scored authority — inherited wholesale
from `engine.top_anatomy`, whose functions do every piece of the derivation here.
Nothing in this module ranks, gates, sizes or escalates. The four states are
GROUPS, not a ladder of conviction; the order inside a group is trailing
six-month gain, which is a fact about the past and is disclosed as one. This is
the AVOID-not-SHORT lobe: there is no exit rule, no short side, and no forward
claim anywhere in it (`DNR:KILL-DIRECTIONAL-SHORTING`).

WHERE THE CONSTANTS COME FROM. The nine leg thresholds are FROZEN in
`data/top_anatomy/thresholds.json`, cut by `scripts/export_top_anatomy_library.py`
from the Phase-0 library as the P90/P10 of each feature over the runs that KEPT
GOING. The nightly READS them; it never re-cuts them. That is the whole point:
a threshold that re-fits itself every night would quietly re-define what "showing
wear" means while the copy above it stayed the same.

WHAT IS NEW HERE AND WHAT IS NOT. Nothing about the underlying construction is
new: identity segments, the §3 floors, the §4.1 EXT mask, §4.2 episodes and the
§4.6 features are `engine.top_anatomy` verbatim. What this module adds is (a) an
incremental trailing panel so the read fits in a nightly budget, (b) the nine
display heuristics that turn frozen feature values into plain-word legs, (c) the
four-state grouping, and (d) the analog memory — a k-nearest-neighbour lookup
into the Phase-0 library on shape and age alone.

INSTRUMENT VERDICTS ARE NOT MARKET VERDICTS. `breaking` means the two structural
legs both fired on this tape. It is not a claim that a move is over, and no copy
derived from it may say so. The surface's terminal stance is "worth a review".

THE `breaking` BOUND, AND THE MEMBERSHIP RULING THAT ANSWERS IT. `breaking`
requires `drawdown_from_high` (F2 <= -0.10), and F2 is BOUNDED by the §4.1 EXT
definition it is conditioned on: a day is only EXT while its close is at or above
0.90 x its trailing-252 maximum, which pins the close within ~10% of the episode's
running peak in almost every case. Measured on the Phase-0 library: 10 of 33,598
sampled EXT days clear -0.10 (0.030%), and the minimum F2 in the whole library is
-0.1000. Conditioned on being IN the band, the terminal state was bounded away by
the very condition that defined the population — a name cannot be seen leaving
through a window that only shows the inside.

The trigger is NOT re-cut to fix that (a display heuristic that re-tunes itself
until a group is non-empty is exactly the failure this program exists to avoid).
The MEMBERSHIP is widened instead, by operator ruling: the board is every name
with at least one EXT day in the trailing `MEMBERSHIP_WINDOW_SESSIONS`, and a name
that is recently-but-not-currently EXT is eligible for `breaking` and nothing
else — if it does not qualify it drops off, because none of the other three states
is true of a name that has already left. Names still IN the band run the same four
states they always did, on the same frozen thresholds. The night a name falls out
of the band is exactly the night its give-back becomes readable, and that is the
night this board has something to say about it.

Purity: pandas/numpy + `engine.top_anatomy`. Every entry point takes explicit
roots, so the module imports and runs against a synthetic store with no repo data
present.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from engine import top_anatomy as ta

__all__ = [
    "STANDING_LAW", "LEGS_PROVENANCE", "SCHEMA", "PANEL_TRAILING_SESSIONS",
    "MEMBERSHIP_WINDOW_SESSIONS",
    "LEG_ORDER", "COUNTING_LEGS", "MAX_LEGS", "BREAKING_LEAD_LEGS",
    "KNN_K", "THIN_ANALOG_N",
    "build_panel", "load_thresholds", "load_library", "load_us_stock_metadata",
    "classify", "order_legs", "build_context", "null_context", "ledger_lane_armed",
    "append_forward_log",
]

SCHEMA = "winner_health.v1"

#: House lobe convention (`engine/neuralweb/mastermind_context.py`): the payload
#: carries its own standing law so a downstream reader — the chat brain
#: included — cannot pick the numbers up without the constraint attached.
STANDING_LAW = (
    "Winner Health is DISPLAY TIER with zero scored authority: nothing here ranks, "
    "gates, sizes or escalates anything, and the four states are groups, never a "
    "ranking. This is the AVOID-not-SHORT lobe — it is entry-side avoidance and "
    "review context for a position already owned, never a sell, short, trim or exit "
    "instruction, and there is no directional bear position anywhere in the program. "
    "Library counts are what similar past runs DID — history, not forecasts, and not "
    "probabilities. There is NO MODEL here and no probability anywhere: the legs are "
    "descriptive facts about a name's own behaviour, and only `updown_volume` is a "
    "researched discriminator (registered, MID lead-time, sign-stable across eras and "
    "terciles) — the other eight carry no such status and must never be described as "
    "researched, predictive or calibrated. A state is an instrument reading on this "
    "tape, never a verdict on the market. Promotion of anything here to authority "
    "requires its own pre-registered gauntlet and an operator ruling."
)

#: Machine-readable scoping of the leg family (coordinator ruling, prereg §5
#: decision rules). Carried in the payload for downstream readers — the chat
#: brain included — and never rendered: the surface states these legs as plain
#: descriptive facts and says nothing about their research status either way.
LEGS_PROVENANCE = {
    "watch_leg": "updown_volume",
    "watch_leg_basis": "registered · MID lead-time · sign-stable across eras and terciles",
    "other_legs": "descriptive facts about the name's own behaviour — not researched "
                  "discriminators, not predictors, not calibrated",
    "model": None,
    "probabilities": False,
}

# ── panel ─────────────────────────────────────────────────────────────────────
#: Trailing sessions kept per name. The §3 history floor consumes the first 260
#: bars, so the longest episode this panel can SEE is `trailing − 261` sessions.
#:
#: Sized against the LIBRARY's own age distribution, because `F1_episode_age` and
#: `F2_drawdown_in_episode` are both kNN dimensions: a nightly window that clips
#: episodes the library did not clip would match today's names against neighbours
#: measured on a different scale. Measured on the Phase-0 library (33,598 sampled
#: EXT days over 5,930 episodes): episode age has a P90 of 92, a P99 of 185 and a
#: MAXIMUM of 332 sessions. 760 leaves 499 sessions of visible episode — past the observed
#: maximum — while 420 would have left 159 and left-censored more than a tenth of
#: the board. The extra rows are close to free: the panel build is dominated by
#: opening 20k files, not by their length. Guarded by
#: `test_default_window_covers_the_library_age_distribution`.
#:
#: An episode older than the window is still LEFT-CENSORED: its age is a lower
#: bound, so the (context-only) `episode_age` leg is suppressed on those names
#: rather than printing a number that is wrong.
PANEL_TRAILING_SESSIONS = 760
STORE_REL = "massive_stock_day"
PANEL_CACHE_REL = "top_maturation/_panel_cache"
_CACHE_VERSION = 2
#: Harness pre-filter (`build_panel_w`) — a STRICT SUPERSET of the §3 floors, so a
#: name is dropped only when it can never clear a floor on any day. Held identical
#: to the library's so the two populations are the same population.
_MIN_BARS = 261

# ── board membership ──────────────────────────────────────────────────────────
#: Trailing sessions over which one EXT day buys a place on the board (operator
#: ruling). A name is a CANDIDATE iff it printed at least one EXT day in this
#: window; a name that is EXT *today* runs the full state machine unchanged, and a
#: name that is only RECENTLY EXT is eligible for `breaking` and nothing else — if
#: it does not qualify as breaking it simply drops off, because no other state has
#: an honest reading for a name that has already left the band ("still running" is
#: false, and "showing wear" would understate it).
#:
#: 21 is not a new number: `engine.top_anatomy.EPISODE_GAP_MAX` already merges two
#: EXT runs separated by <= 21 non-EXT sessions into ONE §4.2 episode. So this
#: window is exactly the stretch the episode grammar still calls the same run —
#: the board simply stops pretending the run ended the day the band was left.
MEMBERSHIP_WINDOW_SESSIONS = 21

# ── legs ──────────────────────────────────────────────────────────────────────
#: Spec §4.3 fixed key order. NOT a severity ranking — the same two legs must read
#: in the same order on every row and every night.
LEG_ORDER: tuple[str, ...] = (
    "rs_peak_lag", "rs_decel", "effort_result", "updown_volume", "vol_asymmetry",
    "late_verticality", "dip_unreclaimed", "below_50d", "drawdown_from_high",
    "episode_age",
)
#: `episode_age` is CONTEXT ONLY and never counts toward a state — a long run is
#: not a worn one.
COUNTING_LEGS: tuple[str, ...] = tuple(k for k in LEG_ORDER if k != "episode_age")
MAX_LEGS = 3
#: §4.3 AMENDMENT (design authority, 2026-08-10): on a `breaking` row these two
#: legs lead, in the order `classify` reads them, and the remaining slot fills by
#: the frozen key order. They sit 8th and 9th in that order, so on a busy row the
#: MAX_LEGS cap truncated BOTH — measured on the real tape, every one of the 39
#: terminal rows printed three legs and not one of them was the give-back or the
#: lost 50-day line that made the row terminal. A state's own evidence may never
#: be truncated off its own row. This is a DISPLAY order only: `classify` is
#: untouched, the counting set is untouched, and no other state re-orders.
BREAKING_LEAD_LEGS: tuple[str, ...] = ("below_50d", "drawdown_from_high")
THINNING_LEGS = 3          # L >= 3 -> thinning
BELOW_50D_MIN_SESSIONS = 3
DRAWDOWN_FROM_HIGH_TRIGGER = -0.10
DIP_TRIGGER_FRAC = 0.95    # the >=5% intra-episode dip F5 tracks
MA_SLOW = 50

# ── analog memory ─────────────────────────────────────────────────────────────
KNN_K = 40                 # distinct EPISODES, not days (spec §5 note 6)
THIN_ANALOG_N = 12
KNN_DIMS = ("r126", "r63", "late_gain_share", "episode_age", "rv_ratio",
            "drawdown_in_episode")
_KNN_FEATURES = ("A3_r126", "A2_r63", "A7_late_gain_share", "F1_episode_age",
                 "C2_rv21_over_rv63", "F2_drawdown_in_episode")
#: Candidate days pulled before collapsing to distinct episodes. An episode
#: contributes at most `span/5` sampled days, so 40x is a safe ceiling.
_KNN_CANDIDATES = KNN_K * 40

SPARK_POINTS = 63
LIBRARY_REL = "top_anatomy/library.parquet"
THRESHOLDS_REL = "top_anatomy/thresholds.json"
LATEST_REL = "top_maturation/latest.json"
LOG_REL = "top_maturation_log/us_maturation.jsonl"

#: Baskets whose members are a GICS sector rather than a theme. The tomography
#: block is titled "how much of each THEME is aging" and its bar width is the size
#: of the group, so an 80-name sector bar would swamp every real theme.
_NON_THEME_BASKET_PREFIXES = ("us_sector_",)
_NON_US_BASKET_PREFIXES = ("cn_", "hk_", "ca_")

_LOG: Callable[[str], None] = lambda msg: print(msg, flush=True)  # noqa: E731


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# the incremental trailing panel
# ══════════════════════════════════════════════════════════════════════════════
def _split_adjust(close: pd.Series) -> pd.Series:
    """The house split repair, imported lazily so this module stays importable.

    `scripts.replay_standout_pipeline.split_adjust` is THE repair the Phase-0
    library was built through; re-implementing it here would let the nightly and
    the library disagree about what a price is. Absent (a trimmed checkout), the
    fallback is the identity — stated in the diagnostics, never silent.
    """
    from scripts.replay_standout_pipeline import split_adjust  # noqa: PLC0415
    return split_adjust(close)


def _repair_tail(df: pd.DataFrame, trailing: int) -> pd.DataFrame | None:
    """One ticker's raw bars -> the repaired trailing panel legs.

    TRUNCATE FIRST, then repair. The harness fits the split factor to the FULL
    series because it studies the full series; here every in-window quantity is a
    RATIO (r126, the near-high term, the moving averages, every feature), so a
    factor that is right up to a constant across the window is exactly as correct
    and costs a fraction of the time. The two absolute-level users — the §3 price
    and liquidity floors — read `raw_close`/`raw_dvol`, the as-printed prints,
    which the repair never touches. `split_day` marks the factor STEP DAY, which
    is ineligible.

    The pre-filter is the harness's (`build_panel_w`) and is still a STRICT
    SUPERSET of the §3 floors — evaluated on the window rather than on all
    history, which can only ever keep MORE of what a trailing read can use: a name
    that clears a floor today clears it on the window by construction.
    """
    if df is None or len(df) < _MIN_BARS or "close" not in df.columns:
        return None
    df = df[~df.index.duplicated(keep="last")].sort_index().tail(trailing)
    raw_c = pd.to_numeric(df["close"], errors="coerce")
    raw_v = (pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns
             else pd.Series(np.nan, index=df.index))
    px = raw_c.dropna()
    if px.empty or float(px.max()) < ta.MIN_CLOSE:
        return None
    dv21 = (px * raw_v.reindex(px.index)).rolling(21, min_periods=21).median()
    if not (dv21.max() >= ta.MIN_MEDIAN_DVOL21):
        return None
    try:
        factor = (px / _split_adjust(px)).reindex(df.index).ffill().bfill()
    except Exception:  # noqa: BLE001 — an unrepairable series is still readable
        factor = pd.Series(1.0, index=df.index)
    return pd.DataFrame({
        "close": raw_c / factor,
        "volume": raw_v * factor,
        "raw_close": raw_c,
        "raw_dvol": raw_c * raw_v,
        "split_day": factor.diff().fillna(0.0).abs() > 1e-9,
    }).dropna(subset=["close"])


def _cache_paths(cache_dir: Path) -> tuple[Path, Path]:
    return cache_dir / "index.json", cache_dir / "bars.parquet"


def _read_cache(cache_dir: Path, trailing: int) -> tuple[dict, pd.DataFrame | None]:
    idx_p, bars_p = _cache_paths(cache_dir)
    if not idx_p.exists() or not bars_p.exists():
        return {}, None
    try:
        idx = json.loads(idx_p.read_text())
    except Exception:  # noqa: BLE001
        return {}, None
    if idx.get("version") != _CACHE_VERSION or int(idx.get("trailing", -1)) != int(trailing):
        return {}, None
    try:
        bars = pd.read_parquet(bars_p)
    except Exception:  # noqa: BLE001
        return {}, None
    return idx.get("tickers") or {}, bars


def build_panel(data_root: Path, *, cache_dir: Path | None = None,
                trailing: int = PANEL_TRAILING_SESSIONS,
                limit: int | None = None,
                log: Callable[[str], None] | None = None,
                ) -> tuple[dict[str, pd.DataFrame], dict]:
    """The trailing wide panel of identity segments, incrementally cached.

    The cache is keyed on each source parquet's `(mtime_ns, size)`: a file the
    store did not touch is never re-read or re-repaired. Nothing is inferred from
    a file's CONTENT being unchanged — only from the filesystem saying so — and a
    cache written for a different `trailing` (or an older cache layout) is thrown
    away rather than mixed.

    Returns `(panel, diag)`; `panel` maps `close|volume|raw_close|raw_dvol|
    split_day` to wide frames whose COLUMNS ARE IDENTITY SEGMENTS.
    """
    say = log or _LOG
    t0 = time.time()
    store = Path(data_root) / STORE_REL
    if not store.is_dir():
        raise FileNotFoundError(f"massive_stock_day store not found at {store}")
    files = sorted(store.glob("*.parquet"))
    if limit is not None:
        files = files[:limit]

    cache_dir = Path(cache_dir) if cache_dir is not None else None
    cached_idx: dict = {}
    cached_bars: pd.DataFrame | None = None
    if cache_dir is not None:
        cached_idx, cached_bars = _read_cache(cache_dir, trailing)

    want: dict[str, tuple[int, int]] = {}
    for p in files:
        try:
            st = p.stat()
        except OSError:
            continue
        want[p.stem] = (int(st.st_mtime_ns), int(st.st_size))

    reuse = {tk for tk, state in want.items()
             if list(cached_idx.get(tk, ())) == [state[0], state[1]]}
    if cached_bars is None or cached_bars.empty:
        reuse = set()
    stale = [p for p in files if p.stem not in reuse]
    say(f"panel: {len(files)} source files · {len(reuse)} cache hits · "
        f"{len(stale)} to read")

    frames: list[pd.DataFrame] = []
    if reuse and cached_bars is not None:
        keep = cached_bars[cached_bars["ticker"].isin(reuse)]
        if not keep.empty:
            frames.append(keep)
    n_read = n_kept = 0
    for p in stale:
        n_read += 1
        try:
            df = pd.read_parquet(p, columns=["close", "volume"])
        except Exception:  # noqa: BLE001 — one torn vendor file must not blind the read
            continue
        rep = _repair_tail(df, trailing)
        if rep is None or rep.empty:
            continue
        n_kept += 1
        rep = rep.reset_index()
        rep.columns = ["date", *rep.columns[1:]]
        rep.insert(0, "ticker", p.stem)
        frames.append(rep)
    if not frames:
        raise RuntimeError("panel: no readable tickers in the store")

    bars = pd.concat(frames, ignore_index=True)
    bars["date"] = pd.to_datetime(bars["date"])
    for c in ("close", "volume", "raw_close", "raw_dvol"):
        bars[c] = pd.to_numeric(bars[c], errors="coerce").astype("float32")
    bars["split_day"] = bars["split_day"].fillna(False).astype(bool)
    t_scan = time.time() - t0

    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            idx_p, bars_p = _cache_paths(cache_dir)
            bars.to_parquet(bars_p, index=False, compression="zstd")
            idx_p.write_text(json.dumps({
                "version": _CACHE_VERSION, "trailing": int(trailing),
                "written_utc": _now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tickers": {tk: list(want[tk]) for tk in
                            sorted(set(bars["ticker"].unique()) & set(want))},
            }))
        except Exception as e:  # noqa: BLE001 — a cache that cannot be written is not fatal
            say(f"panel: cache write failed ({e}) — next run rebuilds cold")

    # Identity segments, then widen. The segmentation RULE is
    # `ta.identity_segment_bounds` — the same one the library was built through —
    # but it is applied as a LABEL on the long frame and pivoted, rather than by
    # materialising 8k per-ticker frames and concatenating 8k Series: at this
    # width the dict-of-Series construction, not the rule, is the whole cost.
    bars = bars.sort_values(["ticker", "date"], kind="stable", ignore_index=True)
    calendar = pd.DatetimeIndex(sorted(bars["date"].unique()))
    seg = np.empty(len(bars), dtype=object)
    n_split = 0
    for tk, g in bars.groupby("ticker", sort=False):
        pos = g.index.to_numpy()
        spans = ta.identity_segment_bounds(pd.DatetimeIndex(g["date"]), calendar)
        if len(spans) <= 1:
            seg[pos] = tk
            continue
        n_split += 1
        for k, (s, e) in enumerate(spans):
            seg[pos[s:e + 1]] = f"{tk}#{k}"
    bars["segment"] = seg

    panel: dict[str, pd.DataFrame] = {}
    for col in ("close", "volume", "raw_close", "raw_dvol", "split_day"):
        fr = bars.pivot(index="date", columns="segment", values=col)
        panel[col] = fr.reindex(calendar)
    panel["split_day"] = panel["split_day"].fillna(False).astype(bool)
    cols = panel["close"].columns
    for col in panel:
        if list(panel[col].columns) != list(cols):
            panel[col] = panel[col].reindex(columns=cols)

    diag = {
        "n_source_files": len(files),
        "n_cache_hits": len(reuse),
        "n_files_read": n_read,
        "n_tickers_kept": int(bars["ticker"].nunique()),
        "n_tickers_split": n_split,
        "n_segments": int(panel["close"].shape[1]),
        "n_sessions": int(panel["close"].shape[0]),
        "trailing_sessions": int(trailing),
        "scan_seconds": round(t_scan, 2),
    }
    say(f"panel: {diag['n_tickers_kept']} tickers -> {diag['n_segments']} segments x "
        f"{diag['n_sessions']} sessions in {t_scan:.1f}s")
    return panel, diag


# ══════════════════════════════════════════════════════════════════════════════
# frozen constants
# ══════════════════════════════════════════════════════════════════════════════
def load_thresholds(data_root: Path) -> dict:
    """The frozen leg thresholds. Missing/unreadable -> `{}` (every leg goes dark)."""
    p = Path(data_root) / THRESHOLDS_REL
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def load_library(data_root: Path) -> pd.DataFrame | None:
    """The analog library. Missing -> None (every row renders `no match`, honestly)."""
    p = Path(data_root) / LIBRARY_REL
    if not p.exists():
        return None
    try:
        lib = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return None
    need = {*KNN_DIMS, "ticker", "episode_id", "fell_back_hard_63",
            "remaining_upside", "post_peak_dd_126"}
    if not need <= set(lib.columns):
        return None
    return lib.dropna(subset=list(KNN_DIMS)).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
# per-name detail — everything the leg sentences need, computed once per name
# ══════════════════════════════════════════════════════════════════════════════
def _episode_shape(seg_close: np.ndarray) -> dict:
    """Running-peak geometry of one episode: the high, the open dip, the past dips.

    Mirrors `engine.top_anatomy._feature_frame`'s F5 walk exactly (a dip opens at
    a close <= 0.95 x the running peak and closes when the peak is regained), so
    the words on the surface can never disagree with the feature that fired them.
    """
    n = len(seg_close)
    if n == 0:
        return {}
    peak_i = 0
    in_dip = False
    completed: list[tuple[float, int]] = []      # (depth as a positive fraction, sessions)
    dip_low = math.inf
    for i in range(n):
        if seg_close[i] >= seg_close[peak_i]:
            if in_dip:
                depth = 1.0 - (dip_low / float(seg_close[peak_i])) if seg_close[peak_i] else np.nan
                completed.append((float(depth), int(i - peak_i)))
                in_dip = False
            peak_i = i
            dip_low = math.inf
        elif seg_close[i] <= DIP_TRIGGER_FRAC * seg_close[peak_i]:
            in_dip = True
            dip_low = min(dip_low, float(seg_close[i]))
        elif in_dip:
            dip_low = min(dip_low, float(seg_close[i]))
    hi = float(seg_close[peak_i])
    tail = seg_close[peak_i:]
    return {
        "peak_i": int(peak_i),
        "episode_high": hi,
        "sessions_since_peak": int(n - 1 - peak_i),
        "open_dip_depth": (float(1.0 - float(np.nanmin(tail)) / hi)
                           if hi > 0 and tail.size else np.nan),
        "completed_dips": completed,
        "typical_pullback": (float(np.median([d for d, _ in completed]))
                             if completed else np.nan),
        "typical_reclaim": (float(np.median([s for _, s in completed]))
                            if completed else np.nan),
    }


def _name_detail(bars: pd.DataFrame, eqw: pd.Series, ep_start, ep_end,
                 ep_left_censored: bool, *, off_band: bool = False) -> dict:
    """Per-name numbers the leg sentences substitute, all point-in-time.

    `off_band` marks a name that printed an EXT day inside the membership window
    but is NOT EXT today. Those names have no episode row at today's date, so
    `engine.top_anatomy.feature_library` leaves `F2_drawdown_in_episode` null by
    design — it never claims a value off its own grid. The high-water measure
    itself is still perfectly defined (a run's peak does not stop existing the day
    the band is left), so it is continued forward here under `f2_off_band`, using
    the SAME formula `_feature_frame` uses — close over the episode-anchored
    running max, minus one — over the SAME series this row's spark and
    `episode_high` are drawn from. The key is set ONLY when `off_band` is true, so
    a currently-EXT name can never pick up a locally-derived F2 and its state
    machine stays bit-identical.
    """
    c = pd.to_numeric(bars["close"], errors="coerce")
    c = c[c.notna()]
    v = pd.to_numeric(bars["volume"], errors="coerce").reindex(c.index) if "volume" in bars else None
    if v is not None:
        v = v.where(v > 0)
    cv = c.to_numpy(dtype=float)
    n = len(cv)
    out: dict[str, Any] = {"episode_left_censored": bool(ep_left_censored)}

    # relative strength vs the PIT equal-weight median index (E-family's own rs)
    if eqw is not None and len(eqw):
        ew = pd.to_numeric(eqw, errors="coerce").reindex(c.index)
        rs = c / ew.replace(0.0, np.nan)
        rs_peak63 = rs.rolling(63, min_periods=63).max()
        last_rs, last_pk = float(rs.iloc[-1]), float(rs_peak63.iloc[-1])
        out["rs_left_frac"] = (last_rs / last_pk) if (np.isfinite(last_pk) and last_pk > 0) else np.nan
    else:
        out["rs_left_frac"] = np.nan

    # volume: 21-session mean against its own three-month (63-session) mean
    if v is not None:
        m21 = v.rolling(21, min_periods=21).mean()
        m63 = v.rolling(63, min_periods=63).mean()
        out["vol_vs_3m"] = float(m21.iloc[-1] / m63.iloc[-1] - 1.0) if (
            np.isfinite(m63.iloc[-1]) and m63.iloc[-1] > 0) else np.nan
        ret = c / c.shift(1) - 1.0
        dv = c * v
        su = dv.where(ret > 0, 0.0).where(ret.notna()).rolling(21, min_periods=21).sum()
        sd = dv.where(ret < 0, 0.0).where(ret.notna()).rolling(21, min_periods=21).sum()
        ratio = su / sd.replace(0.0, np.nan)
        out["updown_below_one_21"] = int((ratio.tail(21) < 1.0).sum())
    else:
        out["vol_vs_3m"] = np.nan
        out["updown_below_one_21"] = 0

    # the 50-day line: current below-streak, and whether an earlier one exists
    ma50 = c.rolling(MA_SLOW, min_periods=MA_SLOW).mean()
    below = (c < ma50).fillna(False).to_numpy(dtype=bool)
    streak = 0
    for i in range(n - 1, -1, -1):
        if not below[i]:
            break
        streak += 1
    out["below_50d_streak"] = int(streak)
    ep_pos = c.index.get_indexer([ep_start])[0] if ep_start is not None else 0
    ep_pos = int(ep_pos) if ep_pos >= 0 else 0
    prior = below[ep_pos:max(ep_pos, n - streak)]
    run, earlier = 0, False
    for flag in prior:
        run = run + 1 if flag else 0
        if run >= BELOW_50D_MIN_SESSIONS:
            earlier = True
            break
    out["below_50d_first_stretch"] = not earlier

    # episode geometry
    shape = _episode_shape(cv[ep_pos:])
    out.update({f"ep_{k}": val for k, val in shape.items()})
    out["episode_start"] = (pd.Timestamp(c.index[ep_pos]).date().isoformat()
                            if n else None)
    peak_abs = ep_pos + int(shape.get("peak_i", 0))
    out["episode_high_date"] = (pd.Timestamp(c.index[peak_abs]).date().isoformat()
                                if n else None)
    out["episode_high"] = shape.get("episode_high")
    if off_band:
        hi = shape.get("episode_high")
        out["f2_off_band"] = (float(cv[-1]) / float(hi) - 1.0) if (
            n and hi and float(hi) > 0) else np.nan

    # price sessions that still rose while relative strength was already fading
    out["_close"] = c
    return out


def _up_sessions(c: pd.Series, n: int) -> int:
    """How many of the last `n` sessions closed higher than the one before."""
    if n <= 0 or len(c) < 2:
        return 0
    d = c.diff().tail(int(n))
    return int((d > 0).sum())


# ══════════════════════════════════════════════════════════════════════════════
# the nine legs (+ one context leg)
# ══════════════════════════════════════════════════════════════════════════════
def _pct(x: float, dp: int = 0) -> str:
    return f"{abs(x) * 100:.{dp}f}"


def _leg(key: str, en: str, zh: str, tip_en: str | None = None,
         tip_zh: str | None = None) -> dict:
    leg = {"key": key, "words_en": en, "words_zh": zh}
    if tip_en:
        leg["tip_en"] = tip_en
        if tip_zh:
            leg["tip_zh"] = tip_zh
    return leg


def _fire_legs(f: Mapping[str, Any], d: Mapping[str, Any], thr: Mapping[str, Any],
               lib_age: np.ndarray | None,
               ) -> tuple[list[dict], list[str], dict | None]:
    """Every firing leg, in the spec §4.3 key order, with the numbers substituted.

    Copy is VERBATIM from spec §4.3 — the builder substitutes numbers and nothing
    else. Where a substituted number would make the pinned sentence FALSE (a
    volume ratio that is negative, a "first such stretch" that is not the first,
    a "typical pullback" this run has never had), the leg still fires — the state
    machine must not move because a sentence is awkward — but its Tier-2 hover is
    omitted. The template guards on `tip_en`, so the glance words stand alone.
    """
    legs: list[dict] = []
    fired: list[str] = []

    def val(name: str) -> float:
        x = f.get(name)
        try:
            x = float(x)
        except (TypeError, ValueError):
            return float("nan")
        return x

    def cut(name: str) -> float:
        x = (thr.get("thresholds") or {}).get(name)
        return float(x) if x is not None else float("nan")

    # 1 ── rs_peak_lag
    e3, c_e3 = val("E3f_rs_peak_lag"), cut("rs_peak_lag_p90")
    if np.isfinite(e3) and np.isfinite(c_e3) and e3 >= c_e3:
        fired.append("rs_peak_lag")
        n = int(round(e3))
        m = _up_sessions(d["_close"], n)
        legs.append(_leg(
            "rs_peak_lag",
            f"lagging the market for {n} sessions",
            f"已跑输大盘 {n} 个交易日",
            (f"Its strength versus the market peaked {n} sessions ago — the price "
             f"kept rising through {m} of them.") if n > 0 else None,
            (f"它相对大盘的强度在 {n} 个交易日前见顶 —— 其中有 {m} 天股价仍在上涨。")
            if n > 0 else None))

    # 2 ── rs_decel
    e5, c_e5 = val("E5f_rs_decel"), cut("rs_decel_p10")
    if np.isfinite(e5) and np.isfinite(c_e5) and e5 <= c_e5:
        fired.append("rs_decel")
        left = d.get("rs_left_frac", float("nan"))
        ok = np.isfinite(left) and 0.0 < left <= 1.0
        x = f"{left * 100:.0f}%" if ok else None
        legs.append(_leg(
            "rs_decel", "leadership fading", "领涨地位减弱",
            (f"Its edge over the market is still positive but shrinking — about "
             f"{x} of the peak edge is left.") if ok else None,
            (f"它相对大盘仍有优势，但正在收窄 —— 目前只剩下峰值优势的约 {x}。") if ok else None))

    # 3 ── effort_result
    d4, c_d4 = val("D4_ppe_chg21"), cut("effort_result_p10")
    if np.isfinite(d4) and np.isfinite(c_d4) and d4 <= c_d4:
        fired.append("effort_result")
        vx, r21 = d.get("vol_vs_3m", float("nan")), val("A1_r21")
        ok = np.isfinite(vx) and vx > 0 and np.isfinite(r21)
        x, y = _pct(vx), (f"{r21 * 100:.0f}" if np.isfinite(r21) else None)
        legs.append(_leg(
            "effort_result", "more volume, less progress", "量增价滞",
            (f"Volume is running {x}% above its own three-month average while the "
             f"price gained {y}% — buyers are working harder for less.") if ok else None,
            (f"成交量比自身三个月均量高出 {x}%，但股价只涨了 {y}% —— 买方付出更多，"
             f"换来的却更少。") if ok else None))

    # 4 ── updown_volume
    d3, c_d3 = val("D3_updown_dvol_ratio21"), cut("updown_volume_p10")
    if np.isfinite(d3) and np.isfinite(c_d3) and d3 <= c_d3:
        fired.append("updown_volume")
        nn, mm = int(d.get("updown_below_one_21", 0)), 21
        legs.append(_leg(
            "updown_volume", "selling days now heavier", "下跌日成交更重",
            (f"Down-day volume has outweighed up-day volume in {nn} of the last "
             f"{mm} sessions.") if nn > 0 else None,
            (f"最近 {mm} 个交易日中，有 {nn} 天的下跌日成交量超过了上涨日。") if nn > 0 else None))

    # 5 ── vol_asymmetry
    c3, c_c3 = val("C3_semivol_ratio63"), cut("vol_asymmetry_p90")
    if np.isfinite(c3) and np.isfinite(c_c3) and c3 >= c_c3:
        fired.append("vol_asymmetry")
        c2 = val("C2_rv21_over_rv63")
        ok = np.isfinite(c2) and c2 > 1.0
        x = f"{c2:.1f}" if ok else None
        legs.append(_leg(
            "vol_asymmetry", "swings getting wider", "波动明显放大",
            (f"The daily range is {x}× its own three-month normal, and the widening "
             f"is happening on down days.") if ok else None,
            (f"日内波幅是自身三个月常态的 {x} 倍，而且放大主要发生在下跌日。") if ok else None))

    # 6 ── late_verticality
    a7, c_a7 = val("A7_late_gain_share"), cut("late_verticality_p90")
    if np.isfinite(a7) and np.isfinite(c_a7) and a7 >= c_a7:
        fired.append("late_verticality")
        r21 = val("A1_r21")
        ok = np.isfinite(r21) and r21 > 0 and 0.0 < a7 < 1.0
        x = f"{r21 * 100:.0f}" if ok else None
        y = f"{(a7 / (1.0 - a7)) * 5.0:.1f}" if ok else None
        legs.append(_leg(
            "late_verticality", "went vertical late", "末段加速拉升",
            (f"Gained {x}% in 21 sessions — about {y}× the pace it kept for the rest "
             f"of this run.") if ok else None,
            (f"21 个交易日内上涨 {x}% —— 约为本轮行情其余时间节奏的 {y} 倍。") if ok else None))

    # 7 ── dip_unreclaimed
    if bool(f.get(ta.F5_UNRECLAIMED_COL)):
        fired.append("dip_unreclaimed")
        depth = d.get("ep_open_dip_depth", float("nan"))
        since = int(d.get("ep_sessions_since_peak") or 0)
        reclaim = d.get("ep_typical_reclaim", float("nan"))
        ok = np.isfinite(depth) and depth > 0 and since > 0 and np.isfinite(reclaim)
        x, m = _pct(depth), (f"{reclaim:.0f}" if np.isfinite(reclaim) else None)
        legs.append(_leg(
            "dip_unreclaimed", "dip not bought back", "回调未被买回",
            (f"Fell {x}% {since} sessions ago and has not regained that level; earlier "
             f"dips in this run were recovered within {m} sessions.") if ok else None,
            (f"{since} 个交易日前下跌 {x}%，至今未收复该位置；本轮之前的每次回调都在 "
             f"{m} 个交易日内被买回。") if ok else None))

    # 8 ── below_50d
    streak = int(d.get("below_50d_streak") or 0)
    if streak >= BELOW_50D_MIN_SESSIONS:
        fired.append("below_50d")
        first = bool(d.get("below_50d_first_stretch"))
        legs.append(_leg(
            "below_50d", "lost its 50-day line", "跌破 50 日均线",
            (f"Closed below its 50-day average for {streak} straight sessions — the "
             f"first such stretch in this run.") if first else None,
            (f"已连续 {streak} 个交易日收于 50 日均线之下 —— 本轮行情中首次出现。")
            if first else None))

    # 9 ── drawdown_from_high
    f2 = val("F2_drawdown_in_episode")
    if not np.isfinite(f2):
        # Off-band names only (see `_name_detail`): the library feature is null
        # off its own grid, and the continued high-water measure stands in. For a
        # currently-EXT name this key is absent, so nothing changes.
        f2 = float(d.get("f2_off_band", float("nan")))
    if np.isfinite(f2) and f2 <= DRAWDOWN_FROM_HIGH_TRIGGER:
        fired.append("drawdown_from_high")
        x = _pct(f2)
        typ = d.get("ep_typical_pullback", float("nan"))
        hi_d = d.get("episode_high_date")
        ok = np.isfinite(typ) and typ > 0 and hi_d
        y = _pct(typ) if ok else None
        legs.append(_leg(
            "drawdown_from_high", f"{x}% off its high", f"距高点回落 {x}%",
            (f"Down {x}% from the closing high set on {hi_d}, against a typical "
             f"pullback of {y}% during this run.") if ok else None,
            (f"较 {hi_d} 的收盘高点回落 {x}%，而本轮行情期间的典型回调幅度为 {y}%。")
            if ok else None))

    # 10 ── episode_age (CONTEXT ONLY — never appended to `fired`)
    f1, c_f1 = val("F1_episode_age"), cut("episode_age_p90")
    age_leg = None
    if (np.isfinite(f1) and np.isfinite(c_f1) and f1 >= c_f1
            and not d.get("episode_left_censored")):
        months = max(1, int(round(f1 / 21.0)))
        start = d.get("episode_start")
        p = None
        if lib_age is not None and lib_age.size:
            p = int(min(9, max(1, round(10.0 * float((lib_age < f1).mean())))))
        ok = start is not None and p is not None
        age_leg = _leg(
            "episode_age", f"running {months} months", f"已运行 {months} 个月",
            (f"This run started {start}, {int(f1)} sessions ago — longer than {p} in "
             f"10 runs of this kind in the library.") if ok else None,
            (f"本轮行情起于 {start}，至今 {int(f1)} 个交易日 —— 比资料库中十分之 {p} 的"
             f"同类行情都长。") if ok else None)
    return legs, fired, age_leg


def order_legs(legs: Sequence[Mapping[str, Any]], state: str) -> list[dict]:
    """Render order for one row's legs — frozen §4.3 order, except `breaking`.

    Spec §4.3 pins the key order so the same two legs read the same way on every
    row and every night, and it is explicitly NOT a severity ranking. That holds
    everywhere except the terminal state, where the cap and the order collided:
    `below_50d` and `drawdown_from_high` are the two legs `classify` requires for
    `breaking`, they sit last in the frozen order, and MAX_LEGS then cut them off
    the very rows they had just defined.

    So a `breaking` row leads with its own evidence and fills what is left from
    the frozen order. The order INSIDE the lead pair is the order `classify`
    reads them in, not a ranking between them. Every other state is untouched.
    """
    rows = [dict(g) for g in legs]
    if state != "breaking":
        return rows
    by_key = {g.get("key"): g for g in rows}
    lead = [by_key[k] for k in BREAKING_LEAD_LEGS if k in by_key]
    return lead + [g for g in rows if g.get("key") not in BREAKING_LEAD_LEGS]


def classify(fired: Sequence[str]) -> str:
    """The four states. `breaking` needs STRUCTURE, never a bare oscillator cross.

    L counts only the nine counting legs. The terminal state additionally requires
    both structural legs — the 50-day line lost AND a real give-back from the run's
    own high — so a name cannot be called "character changed" on volatility and
    volume alone. This is the inherited `sector_signals` invariant.
    """
    s = set(fired)
    L = len(s & set(COUNTING_LEGS))
    if "below_50d" in s and "drawdown_from_high" in s:
        return "breaking"
    if L >= THINNING_LEGS:
        return "thinning"
    if L >= 1:
        return "extended_watch"
    return "extended_healthy"


# ══════════════════════════════════════════════════════════════════════════════
# analog memory
# ══════════════════════════════════════════════════════════════════════════════
def _analog(vec: np.ndarray, lib: Mapping[str, np.ndarray], base_ticker: str,
            drawdown_pct: int, track: str) -> dict | None:
    """kNN over the library on shape and age — never the company, never its sector.

    Neighbours are ranked by euclidean distance on the six standardised dimensions,
    every segment of the SAME base ticker is excluded (a name is not its own
    analog), and the k nearest DISTINCT EPISODES are kept — one day per episode.
    `n` is therefore an episode-level honest N, which is the number the card
    prints and the number the honest-N floor is measured against.
    """
    if not np.all(np.isfinite(vec)):
        return None
    X = lib["X"]
    if X.shape[0] == 0:
        return None
    mask = lib["ticker"] != base_ticker
    if not mask.any():
        return None
    idx_all = np.flatnonzero(mask)
    d2 = ((X[idx_all] - vec) ** 2).sum(axis=1)
    take = min(_KNN_CANDIDATES, d2.size)
    cand = idx_all[np.argpartition(d2, take - 1)[:take]]
    cand = cand[np.argsort(((X[cand] - vec) ** 2).sum(axis=1), kind="stable")]

    seen: set = set()
    picked: list[int] = []
    for i in cand:
        ep = lib["episode_id"][i]
        if ep in seen:
            continue
        seen.add(ep)
        picked.append(int(i))
        if len(picked) >= KNN_K:
            break
    if not picked:
        return None
    sel = np.asarray(picked)
    fell = lib["fell"][sel]
    n = int(sel.size)
    k = int(fell.sum())

    gain = lib["gain"][sel][~fell]
    gain = gain[np.isfinite(gain)]
    # The card attributes this number to the runs that CARRIED ON, so it is the
    # median of that arm only. A non-positive median would contradict the sentence
    # it renders inside; the field goes null and the template drops the clause.
    med_gain = float(np.median(gain)) if gain.size else None
    if med_gain is not None and med_gain <= 0:
        med_gain = None

    dd = lib["dd"][sel][fell]
    dd = dd[np.isfinite(dd)]
    med_dd = float(np.median(dd)) if dd.size else None
    if med_dd is not None and med_dd >= 0:
        med_dd = None

    return {"n": n, "topped_63td": k, "median_further_gain": med_gain,
            "median_drop_from_high": med_dd, "track": track}


def _library_arrays(lib: pd.DataFrame) -> dict:
    """Standardise the six dimensions once, on the library's own moments."""
    X = lib[list(KNN_DIMS)].to_numpy(dtype=np.float64)
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    return {
        "X": (X - mu) / sd, "mu": mu, "sd": sd,
        "ticker": lib["ticker"].to_numpy(dtype=object),
        "episode_id": lib["episode_id"].to_numpy(dtype=object),
        "fell": lib["fell_back_hard_63"].to_numpy(dtype=bool),
        "gain": lib["remaining_upside"].to_numpy(dtype=np.float64),
        "dd": lib["post_peak_dd_126"].to_numpy(dtype=np.float64),
        "age": lib["episode_age"].to_numpy(dtype=np.float64),
    }


# ══════════════════════════════════════════════════════════════════════════════
# names, baskets, backdrop
# ══════════════════════════════════════════════════════════════════════════════
def load_us_stock_metadata(data_root: Path) -> dict[str, str]:
    """Ticker -> company name for every US name the house carries METADATA for.

    This is BOTH the display-name source and the instrument filter (operator
    ruling, run-1): `massive_stock_day` is an instrument tape, not a stock
    universe, so it lawfully carries ETPs and ETNs — a leveraged VIX ETN cleared
    the extension screen in run-1 and printed as somebody's "winner". Every row
    here is an index constituent, i.e. a common stock with a name and a sector, so
    intersecting the board roster with this table removes the whole ETP/ETN family
    without a hand-maintained deny-list that would rot.

    Sources, unioned: `data/universe/membership.parquet` (active rows) and the
    three breadth `constituents.parquet` tables — the same tables
    `engine.equity_factors._names_sectors` reads.

    NOTE this is an S&P-1500-shaped universe: a US common stock outside those
    indices has no house metadata and is therefore off the board. That is the
    ruling's accepted cost; the count that was screened is printed on the page and
    the count that was excluded is printed in the artifact.
    """
    out: dict[str, str] = {}
    p = Path(data_root) / "universe" / "membership.parquet"
    if p.exists():
        try:
            m = pd.read_parquet(p)
            if "active" in m.columns:
                m = m[m["active"].fillna(True).astype(bool)]
            for _, row in m.iterrows():
                tk = str(row.get("ticker", "")).strip().upper()
                if tk:
                    out.setdefault(tk, str(row.get("name") or tk))
        except Exception:  # noqa: BLE001
            pass
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        cp = Path(data_root) / grp / "constituents.parquet"
        if not cp.exists():
            continue
        try:
            meta = pd.read_parquet(cp)
        except Exception:  # noqa: BLE001
            continue
        for t, row in meta.iterrows():
            tk = str(t).strip().upper()
            nm = row.get("name") if hasattr(row, "get") else None
            if tk:
                out.setdefault(tk, str(nm) if nm else tk)
    return out


def _load_names_zh() -> dict[str, str]:
    """Ticker -> Chinese company name (`config/us_names_zh.json`), or `{}`."""
    try:
        from collectors.us_names_zh import load_names_zh  # noqa: PLC0415
        return load_names_zh() or {}
    except Exception:  # noqa: BLE001
        return {}


def _zh_lookup(names: Mapping[str, str], ticker: str) -> str | None:
    if not names or not ticker:
        return None
    t = str(ticker).strip().upper()
    return names.get(t) or names.get(t.replace("-", ".")) or names.get(t.replace(".", "-"))


def _load_us_themes(data_root: Path) -> dict[str, dict]:
    """US THEME baskets from `data/baskets/membership.json`.

    Non-US baskets and the `us_sector_*` GICS aggregates are both dropped: the
    block is "how much of each THEME is aging", and its bar width is the size of
    the group, so a sector with 80 members would swamp every real theme.
    """
    p = Path(data_root) / "baskets" / "membership.json"
    try:
        raw = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, dict] = {}
    for bid, b in (raw.get("baskets") or {}).items():
        if bid.startswith(_NON_US_BASKET_PREFIXES) or bid.startswith(_NON_THEME_BASKET_PREFIXES):
            continue
        members = [str(m.get("ticker", "")).upper()
                   for m in (b.get("members") or [])
                   if isinstance(m, dict) and not m.get("removed")]
        if members:
            out[bid] = {"name": b.get("name") or bid, "name_zh": b.get("name_zh"),
                        "members": members}
    return out


#: The page's one-line macro backdrop, INJECTED by the builder — never read here.
#:
#: The index-scope froth instrument is firewalled by its own suite's
#: `test_firewall_not_referenced_by_scoring_engines`, which lets exactly two modules under
#: `engine/` name it — the instrument itself and `engine/run.py` (wiring) — and puts
#: every display read in the site-builder layer instead (`scripts/build_site.py`
#: holds the sanctioned view helper). That firewall exists so a market-scope gauge
#: can never leak into a per-name derivation, which is precisely the mistake this
#: module would be making: the backdrop is CONTEXT printed beside the board and has
#: no part in any state, leg or threshold here.
#:
#: So the read moved OUT of `engine/` to `scripts/build_top_maturation.py`, the same
#: layer `build_site.py` occupies, and arrives through this parameter. Laundering the
#: literal (building the path from fragments to slip past the token scan) would have
#: passed the test while keeping the exact dependency the firewall forbids.
_EMPTY_BACKDROP = {"froth_quadrant": None, "stage3_count": None}


def _rendered_ticker_pages(repo_root: Path | None) -> frozenset[str]:
    """Tickers whose `/stocks/<T>.html` page actually shipped.

    A row links only to a page that EXISTS: one dead link fails the whole site
    publish, and an href to a page that was never built is exactly that.
    """
    if repo_root is None:
        return frozenset()
    try:
        import sys  # noqa: PLC0415
        sys.path.insert(0, str(repo_root))
        from lib.pages import rendered_ticker_pages  # noqa: PLC0415
        return rendered_ticker_pages(Path(repo_root) / "site")
    except Exception:  # noqa: BLE001
        return frozenset()


# ══════════════════════════════════════════════════════════════════════════════
# the nightly read
# ══════════════════════════════════════════════════════════════════════════════
def build_context(data_root: Path, *, out_root: Path | None = None,
                  repo_root: Path | None = None,
                  trailing: int = PANEL_TRAILING_SESSIONS,
                  asof: str | None = None, limit: int | None = None,
                  macro_backdrop: Mapping[str, Any] | None = None,
                  log: Callable[[str], None] | None = None) -> tuple[dict, dict]:
    """The full `winner_health.v1` context, plus timing/coverage diagnostics."""
    say = log or _LOG
    t0 = time.time()
    data_root = Path(data_root)
    out_root = Path(out_root) if out_root is not None else data_root

    panel, pdiag = build_panel(data_root, cache_dir=out_root / PANEL_CACHE_REL,
                               trailing=trailing, limit=limit, log=say)
    close = panel["close"]
    volume = panel.get("volume")
    dvol = ((close * volume).reindex_like(close)
            if volume is not None and not volume.empty
            else pd.DataFrame(np.nan, index=close.index, columns=close.columns))
    floors = {"raw_close_df": panel.get("raw_close"),
              "raw_dollar_vol_df": panel.get("raw_dvol"),
              "split_day_df": panel.get("split_day")}
    floors = {k: (v if v is not None and not v.empty else None) for k, v in floors.items()}

    t_mask = time.time()
    elig = ta.eligibility_mask(close, dvol, **floors)
    eqw = ta.equal_weight_median_index(close, elig, min_names=20)
    ext = ta.extended_mask(close, dvol, **floors)
    episodes = ta.extract_episodes(ext, close)
    say(f"masks: {int(ext.to_numpy().sum())} EXT days · {len(episodes)} episodes "
        f"in {time.time() - t_mask:.1f}s")

    # The instrument filter (operator ruling). The MASKS, the index and the
    # features above are computed on the WHOLE tape on purpose: the equal-weight
    # median index the RS legs are measured against — and therefore the frozen
    # thresholds cut from the library — is a whole-market object, so narrowing the
    # panel first would silently re-base every relative-strength number. The
    # roster is narrowed here, at the display boundary, and nowhere earlier.
    meta = load_us_stock_metadata(data_root)
    if not meta:
        raise RuntimeError(
            "US stock metadata unavailable (data/universe/membership.parquet and the "
            "breadth constituent tables are all missing or unreadable) — the board "
            "cannot tell a company from an exchange-traded product, so it does not print")

    last_day = close.index.max()
    today = ext.loc[last_day] if last_day in ext.index else pd.Series(dtype=bool)
    live = close.loc[last_day].notna() if last_day in close.index else pd.Series(dtype=bool)

    # BOARD MEMBERSHIP (operator ruling). A name is a CANDIDATE iff it printed at
    # least one EXT day in the trailing `MEMBERSHIP_WINDOW_SESSIONS`. Candidates
    # split two ways and are treated differently on purpose:
    #   · EXT TODAY      -> the full four-state machine, unchanged.
    #   · RECENTLY EXT   -> eligible for `breaking` and NOTHING else. If it does
    #                       not qualify, it drops off the board entirely.
    # The asymmetry is the honest one. The EXT definition pins a close within ~10%
    # of its trailing-252 max, so `drawdown_from_high` (F2 <= -0.10) is almost
    # unreachable while a name is still IN the band — the terminal state was
    # bounded away by the very condition it was conditioned on. The night a name
    # falls out of the band is precisely the night that measure becomes readable.
    # Showing any OTHER state for a name that has left would be worse than
    # dropping it: "still running" would be false, and "showing wear" would call a
    # departure a wobble.
    live_now = live.fillna(False)
    ext_now = today.fillna(False).reindex(live_now.index, fill_value=False) & live_now
    window = ext.tail(MEMBERSHIP_WINDOW_SESSIONS)
    ext_recent = (window.fillna(False).any(axis=0).reindex(live_now.index, fill_value=False)
                  & live_now)
    off_band_mask = ext_recent & ~ext_now
    raw_ext = sorted(ext_now.index[ext_now])
    raw_off = sorted(off_band_mask.index[off_band_mask])
    raw_board = raw_ext + raw_off
    ext_segments = [s for s in raw_board if ta.segment_ticker(s).upper() in meta]
    off_band_segments = {s for s in raw_off if ta.segment_ticker(s).upper() in meta}
    excluded = [ta.segment_ticker(s).upper() for s in raw_board
                if ta.segment_ticker(s).upper() not in meta]
    screened = sorted({ta.segment_ticker(s).upper() for s in close.columns} & set(meta))
    say(f"extended on {pd.Timestamp(last_day).date()}: {len(ext_segments)} candidate "
        f"segments ({len(ext_segments) - len(off_band_segments)} EXT today, "
        f"{len(off_band_segments)} recently EXT — breaking-only) · {len(excluded)} "
        f"non-stock instruments excluded, {len(screened)} names screened")

    # features — EXT segments only, the latest day only (never all 36 x all names)
    bars_by_seg: dict[str, pd.DataFrame] = {}
    for s in ext_segments:
        c = close[s]
        c = c[c.notna()]
        if c.empty:
            continue
        d = {"close": c}
        if volume is not None and not volume.empty and s in volume.columns:
            d["volume"] = volume[s].reindex(c.index)
        bars_by_seg[s] = pd.DataFrame(d)
    asof_days = pd.DataFrame({"segment": list(bars_by_seg),
                              "date": [last_day] * len(bars_by_seg)})
    t_feat = time.time()
    feats = (ta.feature_library(bars_by_seg, eqw, asof_days, episodes=episodes)
             if bars_by_seg else pd.DataFrame())
    say(f"features: {len(feats)} rows in {time.time() - t_feat:.1f}s")

    thr = load_thresholds(data_root)
    lib_df = load_library(data_root)
    lib = _library_arrays(lib_df) if lib_df is not None and len(lib_df) else None
    track = str((thr.get("track") or "W"))
    drawdown_pct = int(thr.get("fell_back_hard_drawdown_pct") or 20)
    horizon_td = int(thr.get("fell_back_hard_horizon_td") or 63)

    names_zh = _load_names_zh()
    themes = _load_us_themes(data_root)
    have_pages = _rendered_ticker_pages(repo_root)

    ep_by_seg = {seg: g for seg, g in episodes.groupby("segment", sort=False)} \
        if not episodes.empty else {}
    feat_by_seg = {r["segment"]: r for _, r in feats.iterrows()} if len(feats) else {}
    lib_age = lib["age"] if lib is not None else None

    states: dict[str, list[dict]] = {k: [] for k in
                                     ("extended_healthy", "extended_watch", "thinning",
                                      "breaking")}
    by_ticker_state: dict[str, str] = {}
    ledger_rows: list[dict] = []
    n_censored = 0
    n_off_band_kept = 0
    n_off_band_dropped = 0
    t_rows = time.time()
    for seg in ext_segments:
        f = feat_by_seg.get(seg)
        if f is None:
            continue
        bars = bars_by_seg.get(seg)
        if bars is None or bars.empty:
            continue
        eps = ep_by_seg.get(seg)
        ep_start = ep_end = None
        if eps is not None and not eps.empty:
            cur = eps[(eps["start"] <= last_day) & (eps["end"] >= last_day)]
            row_ep = (cur.iloc[-1] if not cur.empty else eps.iloc[-1])
            ep_start, ep_end = row_ep["start"], row_ep["end"]
        c_idx = bars.index
        censored = bool(ep_start is not None and len(c_idx)
                        and pd.Timestamp(ep_start) <= pd.Timestamp(c_idx[0]))
        n_censored += int(censored)
        off_band = seg in off_band_segments
        d = _name_detail(bars, eqw, ep_start, ep_end, censored, off_band=off_band)

        legs, fired, age_leg = _fire_legs(f, d, thr, lib_age)
        state = classify(fired)
        if off_band:
            # The breaking-only rule. A name that has left the band and does not
            # read as `breaking` is not demoted to a gentler group — it leaves the
            # board, because none of the other three states is true of it.
            if state != "breaking":
                n_off_band_dropped += 1
                continue
            n_off_band_kept += 1
        # `episode_age` is context, so it is never allowed to put a wear mark on a
        # row whose group header says nothing has slipped.
        if age_leg is not None and state != "extended_healthy":
            legs = legs + [age_leg]
        # Order BEFORE the cap — the whole point of the §4.3 amendment is that a
        # terminal row's own evidence survives the truncation.
        legs = order_legs(legs, state)[:MAX_LEGS]

        base = ta.segment_ticker(seg)
        c = d["_close"]
        spark = [round(float(x), 4) for x in c.tail(SPARK_POINTS).to_numpy(dtype=float)]
        vec = None
        if lib is not None:
            raw = np.array([float(f.get(k, np.nan)) for k in _KNN_FEATURES], dtype=np.float64)
            vec = (raw - lib["mu"]) / lib["sd"]
        analog = (_analog(vec, lib, base, drawdown_pct, track)
                  if (lib is not None and vec is not None) else None)

        r126 = float(f.get("A3_r126")) if pd.notna(f.get("A3_r126")) else None
        r21 = float(f.get("A1_r21")) if pd.notna(f.get("A1_r21")) else None
        f2 = float(f.get("F2_drawdown_in_episode")) if pd.notna(
            f.get("F2_drawdown_in_episode")) else None
        f1 = float(f.get("F1_episode_age")) if pd.notna(f.get("F1_episode_age")) else None
        row = {
            "ticker": base,
            "name": meta.get(base),
            "name_zh": _zh_lookup(names_zh, base),
            "href": f"/stocks/{base}.html" if base in have_pages else None,
            "r126": r126,
            "r21": r21,
            "days_in_episode": int(f1) if f1 is not None else None,
            "state": state,
            "spark": spark,
            "episode_high": (round(float(d["episode_high"]), 4)
                             if d.get("episode_high") else None),
            "legs": legs,
            "analog": analog,
        }
        states[state].append(row)
        by_ticker_state[base] = state
        ledger_rows.append({
            "asof": pd.Timestamp(last_day).date().isoformat(),
            "ticker": base, "segment": seg, "state": state,
            # Which membership arm this row came in on — a grader has to be able
            # to separate "was extended and broke" from "had already left".
            "off_band": bool(off_band),
            # `legs` is what the ROW SHOWS — frozen key order, capped at MAX_LEGS
            # (spec §4.3), so it can and does omit the legs that decided the
            # state: `below_50d` and `drawdown_from_high` sit last in that order
            # and are the first to be truncated on a busy row. `fired` is the
            # uncapped counting set `classify` actually read. A ledger that stored
            # only the display list would be ungradeable — you could not tell why
            # a row was terminal — so both are kept.
            "legs": [g["key"] for g in legs],
            "fired": list(fired),
            "r126": r126, "r21": r21, "dd_from_high": f2,
            "analog_n": (analog or {}).get("n"),
            "analog_topped": (analog or {}).get("topped_63td"),
        })
    say(f"rows: {sum(len(v) for v in states.values())} built in {time.time() - t_rows:.1f}s")

    # G-B: inside a group the order is trailing six-month gain — a FACT, not a rank.
    for key in states:
        states[key].sort(key=lambda r: (r["r126"] is None, -(r["r126"] or 0.0)))

    theme_counts = []
    for bid, b in themes.items():
        hits = {t: by_ticker_state[t] for t in b["members"] if t in by_ticker_state}
        if not hits:
            continue
        theme_counts.append({
            "basket": b["name"], "basket_zh": b.get("name_zh"),
            "extended": len(hits),
            "watch": sum(1 for s in hits.values() if s == "extended_watch"),
            "thinning": sum(1 for s in hits.values() if s == "thinning"),
            "breaking": sum(1 for s in hits.values() if s == "breaking"),
        })
    theme_counts.sort(key=lambda t: -t["extended"])

    def _ym(x) -> str | None:
        return str(x)[:7] if x else None

    ctx = {
        "schema": SCHEMA,
        "_STANDING_LAW": STANDING_LAW,
        "_LEGS_PROVENANCE": LEGS_PROVENANCE,
        "asof": asof or _now_utc().date().isoformat(),
        "data_last_day": pd.Timestamp(last_day).date().isoformat(),
        # POST-INTERSECTION screen count: the US names the board could have
        # printed, not the raw instrument-file count.
        "universe_n": len(screened),
        "extended_n": int(sum(len(v) for v in states.values())),
        "null_state": False,
        "macro_backdrop": dict(macro_backdrop) if macro_backdrop else dict(_EMPTY_BACKDROP),
        "library": {
            "track": track,
            "window_start": _ym(thr.get("window_start")),
            "window_end": _ym(thr.get("window_end")),
            "horizon_td": horizon_td,
            "drawdown_pct": drawdown_pct,
        },
        "states": states,
        "theme_counts": theme_counts,
    }
    diag = {
        **pdiag,
        "n_us_stock_metadata": len(meta),
        "n_screened_post_intersection": len(screened),
        "n_extended_pre_intersection": len(raw_ext),
        "n_board_candidates_pre_intersection": len(raw_board),
        "membership_window_sessions": int(MEMBERSHIP_WINDOW_SESSIONS),
        # post-intersection candidates, split by membership arm. The currently-EXT
        # arm is never filtered, so `extended_n - n_off_band_on_board` must equal
        # `n_current_ext_candidates` — the executable form of "names still in the
        # band run the same state machine they always did".
        "n_current_ext_candidates": len(ext_segments) - len(off_band_segments),
        "n_off_band_candidates": len(off_band_segments),
        "n_off_band_on_board": int(n_off_band_kept),
        "n_off_band_dropped": int(n_off_band_dropped),
        "n_excluded_non_stock_instruments": len(excluded),
        "excluded_instruments": sorted(set(excluded)),
        "n_extended": ctx["extended_n"],
        "per_state": {k: len(v) for k, v in states.items()},
        "n_episode_left_censored": int(n_censored),
        "n_with_analog": sum(1 for v in states.values() for r in v if r.get("analog")),
        "library_rows": int(len(lib_df)) if lib_df is not None else 0,
        "thresholds_present": bool(thr.get("thresholds")),
        "n_themes": len(theme_counts),
        "total_seconds": round(time.time() - t0, 2),
        "ledger_rows": ledger_rows,
    }
    say(f"context built in {diag['total_seconds']:.1f}s — {ctx['extended_n']} on the "
        f"board, {diag['per_state']} · recently-EXT: {n_off_band_kept} entered as "
        f"breaking, {n_off_band_dropped} dropped")
    return ctx, diag


def null_context(reason: str, *, asof: str | None = None) -> dict:
    """The honest-null payload. `null_state` means the READ did not land — never
    'nothing is extended', which is a data finding the state lists carry."""
    return {
        "schema": SCHEMA,
        "_STANDING_LAW": STANDING_LAW,
        "_LEGS_PROVENANCE": LEGS_PROVENANCE,
        "asof": asof or _now_utc().date().isoformat(),
        "null_state": True,
        "null_reason": reason,
        "states": {"extended_healthy": [], "extended_watch": [], "thinning": [],
                   "breaking": []},
    }


# ══════════════════════════════════════════════════════════════════════════════
# forward log (ignition_audit mechanics)
# ══════════════════════════════════════════════════════════════════════════════
def ledger_lane_armed() -> bool:
    """True only on a ledger-advancing collect lane (`COLLECT_LANE=nightly`).

    House law: nightly is the SOLE advancer of `data/` forward ledgers. The render
    lanes rebuild the page from the committed artifact and must not append — the
    log is idempotent-by-(asof, ticker) with FIRST-WRITER-WINS, so an off-lane
    append would permanently displace the nightly row. Sibling gate:
    `engine.ignition_audit.ledger_lane_armed`.
    """
    lane = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return lane.lower() == "nightly"


def append_forward_log(rows: Iterable[Mapping[str, Any]], out_root: Path) -> int:
    """Append tonight's maturation rows to the forward log. Off-lane calls no-op."""
    try:
        if not ledger_lane_armed():
            return 0
        rows = [dict(r) for r in rows]
        if not rows:
            return 0
        p = Path(out_root) / LOG_REL
        p.parent.mkdir(parents=True, exist_ok=True)
        existing: list[dict] = []
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    existing.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    continue
        seen = {(r.get("asof"), r.get("ticker")) for r in existing}
        added = [r for r in rows if (r.get("asof"), r.get("ticker")) not in seen]
        if not added:
            return 0
        existing.extend(added)
        p.write_text("\n".join(json.dumps(r, separators=(",", ":"), default=str)
                               for r in existing) + "\n")
        return len(added)
    except Exception:  # noqa: BLE001 — a ledger problem never fails the read
        return 0
