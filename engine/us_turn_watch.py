"""engine/us_turn_watch.py — the TURN WATCH desk data plane (ANTICIPATION §6.9 R8).

WHAT THIS IS
------------
A nightly DECK of US names whose EARLIEST mechanical turn evidence fired inside the
last `TRIGGER_LOOKBACK_SESSIONS` sessions, each row carrying the operator's own manual
review checklist PRE-COMPUTED.

Operator reframe that commissioned it (`research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md`
§6.9 R8, 2026-08-08): *"if we get the signal early, I do the holistic review myself — but
if we don't surface them, names reach my desk up 10-15% and I chase."*  The operator IS
the second-stage filter.  So this surface optimises **RECALL and CONTEXT DENSITY, not
precision**.  A row here is not a candidate, not a plan, not a pick — it is a name whose
earliest evidence tier moved, printed next to enough context that a human can decide in
seconds whether to look harder.  Most rows will go nowhere.  That is the design, not a
defect, and every surface that renders this must say so.

AUTHORITY: **display tier, zero scored authority** (§6.0 / G0.6 form).  This module ranks
nothing that is graded, gates nothing, sizes nothing, and escalates nothing.  It does not
add to, remove from or reorder any `act_now` lane, board population, rank or gate.  The
`context_score` it emits is a DISPLAY-ONLY sort key — see :func:`context_score` — and is
labelled non-authoritative everywhere it is published.  A null never blocks a row: a
missing column is printed as `null` beside a plain-word reason, never as `0`/`False`
(the PLTR `above200` narration-gap precedent).

THE TRIGGER UNION (a name enters on ANY of the four, within the lookback)
------------------------------------------------------------------------
(a) ``dot_1d`` — the DOT SIGNATURE on the DAILY series: StochRSI %K crosses above %D,
    %D was below `OS` (20) within the last `DOT_WASHED_WINDOW` (8) sessions, and the daily
    RSI-MACD histogram is rising.  This is §6.9's "earliest mechanical evidence" leg and
    the engine-side form of the grey-dot promotion in §6.8(b).
(b) ``pre_confluence_2d`` — a FRESH 2D RSI-MACD cross-up (within `FRESH_TICKS` 2D-ticks)
    while the 3D RSI-MACD has NOT yet crossed (3D histogram still below zero).  The 3D
    ``bars_to_cross`` is printed on the row, so "pre-confluence" is QUANTIFIED rather than
    asserted — the operator sees "~1.8 bars to cross" instead of a silent absence.
(c) ``basket_turn`` — membership of any basket whose `engine.us_basket_turn` lifecycle
    state is TURNING or CONFIRMED.  Cohort evidence, read from that organ's committed
    artifact/ledger; this module computes no basket state of its own.
(d) ``leader_reset_turn`` — the leader-pullback reset (§6.8(d) lane 2, the NVDA/AVGO-class
    catcher): a high-RS name in an intact uptrend takes a shallow controlled retrace, the
    daily stochastic resets, and turns back up.  Sourced from `engine.us_leader_pullback`
    when that organ (R4) is present, else from the MINIMAL INLINE signature below.

WHY THE INDICATOR HELPERS ARE IMPORTED, NOT FORKED
--------------------------------------------------
`_stoch_rsi_kd`, `_rsi_macd`, `_xup`, `_since`, `_tf_bars`, `_to_daily` and
`_completed_resample` are imported from `engine.confluence_tiers` even though they are
private there.  That is deliberate and ordered by the R8 brief: a forked copy of the
house StochRSI/RSI-MACD would drift from the cascade the deck is supposed to ANTICIPATE,
and the deck's whole claim ("the slow tier has not admitted this yet") is only meaningful
if both sides read the same instrument.  The known cost of a private-helper import is
that it carries its owner's ERA into this artifact, so the era travels WITH the numbers:
every artifact stamps ``anchor_era`` (confluence_tiers.ANCHOR_ERA) and
``indicator_source`` so a future amendment there is dated here rather than silent.

RUNTIME
-------
The nightly budget is law.  `compute_deck` measures its own wall clock and publishes it
as ``runtime_seconds``; a run that exceeds `RUNTIME_WARN_SECONDS` prints a bare
line-start ``::warning`` (this module runs inside an Actions step via
`scripts/build_turn_watch.py`, so it is NOT annotation-exempt).  `universe_limit` gives
the caller a DETERMINISTIC subset lever (alphabetical by ticker, disclosed in the
artifact) if the desk ever outgrows its slot; it is unset by default.

VOICE
-----
User-facing strings are windows-not-certainties (`DISCLOSURE`, `AUTHORITY`, `NOISE_NOTE`)
and carry zh siblings in :data:`LEXICON` for the page that ships next session under the
design lane.  Falsifier/refutation vocabulary is never used here (operator 2026-07-27).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.confluence_tiers import (  # house instrument — imported, never forked (see docstring)
    ANCHOR_ERA,
    CONF_W,
    FRESH_TICKS,
    OS,
    _completed_resample,
    _rsi_macd,
    _stoch_rsi_kd,
    _tf_bars,
    _to_daily,
    _xup,
    cascade,
)

log = logging.getLogger(__name__)

SCHEMA = "us_turn_watch.v1"
#: Selection era this deck belongs to (§6.2 stamp law — a population change is dated).
SELECTION_ERA = "anticipation-v1-2026-08-08"
#: Where the indicator legs come from, published so the era above travels with the numbers.
INDICATOR_SOURCE = "engine.confluence_tiers"

# ── universe ────────────────────────────────────────────────────────────────────────────
#: Store ladder.  ``yahoo`` is the deck universe (R8 brief); the later rungs exist so the
#: acceptance replay can measure a name that has price history but no yahoo store file
#: (ADAM is the live example — it lives only under ``baskets/ohlcv``).  A name reached
#: through a later rung is OUTSIDE the nightly deck universe and is stamped as such.
STORE_LADDER: tuple[str, ...] = ("yahoo", "stocks", "baskets/ohlcv")
DECK_STORE = "yahoo"
#: Minimum daily closes to be graded here (R8 brief).  Above `confluence_tiers.MIN_HISTORY`
#: (159) on purpose: below 200 bars the 200dMA context column is unknowable, and this deck
#: is a CONTEXT surface — a row whose context is mostly null helps nobody.  The names it
#: excludes are the §6.3 B4 young-name shelf's business, not this deck's.
MIN_BARS = 200
#: Store files that are not single US equities a desk reviews: index proxies (``_GSPC``),
#: FX/futures (``DX-Y.NYB``, ``USDSGD_X``, ``GC_F``) and crypto pairs (``BTC-USD``).
#
# The `_X`/`_F` suffixes are this store's safe-stem encoding of Yahoo's `=X` (FX) and `=F`
# (futures) — 21 futures contracts and the FX crosses. They belong to the commodities lane,
# not to a single-name turn desk, and the suffix match is EXACT so `PL_F` (platinum futures)
# leaves while `PL` (Planet Labs, a live deck row) stays.
#
# The crypto/FX exclusion is not cosmetic.  Those tapes trade 24/7, so on 2026-08-08 five of
# them (BTC-USD, ETH-USD, SOL-USD, USDIDR_X, USDSGD_X) already carried an 08-08 bar while all
# 726 equities ended 08-07 — and a `max()` session stamp over the universe read the whole
# deck as a session fresher than the tape it actually computes on.  That is the G0.2 fail-open
# shape verbatim (6 of 3,029 panel members reaching a later date flipped the board's `delayed`
# badge to false while the majority stayed frozen).  Both halves are closed: these names leave
# the universe, AND the session stamp below is majority-based with the max disclosed beside it.
_UNIVERSE_SKIP_PREFIXES = ("_",)
_UNIVERSE_SKIP_CHARS = (".", "=", "^")
_UNIVERSE_SKIP_SUFFIXES = ("-USD", "-EUR", "-GBP", "_X", "_F")

# ── triggers ────────────────────────────────────────────────────────────────────────────
#: A trigger counts for admission while it fired within this many trailing sessions.
TRIGGER_LOOKBACK_SESSIONS = 5
#: (a) %D must have been below OS within this many trailing DAILY sessions.
DOT_WASHED_WINDOW = 8
TRIGGER_IDS = ("dot_1d", "pre_confluence_2d", "basket_turn", "leader_reset_turn")
#: The basket lifecycle states that flag their members (R8 brief).
BASKET_TURN_STATES = ("TURNING", "CONFIRMED")

# ── (d) minimal inline leader-pullback reset signature ─────────────────────────────────
# SWAP-IN PLAN: `engine/us_leader_pullback.py` is R4 of the same run order and was still in
# flight when this shipped, so leg (d) soft-imports it (see `_leader_source`) and falls back
# to the signature below.  When R4 lands, the fallback stays as the documented default only
# until its organ exposes one of `_LEADER_ENTRY_POINTS`; the artifact stamps
# ``leader_pullback_source`` on every run, so which one is live is never a guess.  Nothing
# else in this module changes — the swap is one import site.
#
# The inline signature is deliberately the WEAKEST honest form of §6.8(d) lane 2: high
# relative strength, an intact uptrend, a SHALLOW controlled retrace (not a washout), a
# reset daily stochastic, and a turn back up.  It claims nothing about forward outcome —
# R4's replay is what will measure that.
LEADER_RS_WINDOW = 126          # relative-strength lookback vs the benchmark
LEADER_RETRACE_WINDOW = 63      # the "controlled retrace" is measured off this high
LEADER_RETRACE_MIN = 0.03       # shallower than this is not a pullback, it is noise
LEADER_RETRACE_MAX = 0.25       # deeper than this is a washout — lane (a)/(c)'s business
LEADER_RESET_MAX = 30.0         # daily %D must have reset below this inside DOT_WASHED_WINDOW
#: Candidate entry points on the R4 organ, tried in order (first callable wins).
_LEADER_ENTRY_POINTS = ("reset_turn_stream", "reset_turn_series", "reset_turn", "stream")

# ── context ─────────────────────────────────────────────────────────────────────────────
BASE_WINDOW = 252               # "52w" high for off-high / base depth / base age
REL_WINDOW = 20                 # relative-strength window vs the benchmark, in sessions
MA_WINDOW = 200
BENCHMARK = "SPY"

# ── deck ────────────────────────────────────────────────────────────────────────────────
DECK_CAP = 40
#: Slots each trigger lane is guaranteed inside the cap before the rest fills by score.
#
# MEASURED REASON THIS EXISTS (2026-08-08, first full run: 721 graded, 364 triggered).  A
# pure `context_score` top-40 held 2 `dot_1d` rows and ZERO `leader_reset_turn` rows — the
# first leader row sat at rank 41 — because two of the score's terms (`washout`, `base`) are
# washout-shaped by construction, and a leader-pullback name is SHALLOW by definition and can
# never compete on them.  A cap that silently deletes an entire lane is not a recall surface,
# and §6.8(d)'s standing doctrine is explicit that no single lane is the answer ("the battery
# is the answer").  So the floor is structural, disclosed in `coverage.lane_floor` and
# `coverage.deck_by_trigger`, and applied BEFORE the score fills the remainder.  It changes
# what is VISIBLE, never what is claimed — every row still carries its own context score and
# the same non-authoritative label.
LANE_FLOOR = 5
RUNTIME_WARN_SECONDS = 480.0    # 8 min — the nightly budget for this desk is < 10 min

DISCLOSURE = (
    "Names whose earliest turn evidence moved in the last "
    f"{TRIGGER_LOOKBACK_SESSIONS} sessions, with the review checklist pre-computed. "
    "These are windows, not certainties — most will not become anything, and the deck "
    "is built for recall, so it surfaces early and noisily on purpose."
)
DISCLOSURE_ZH = (
    f"最近 {TRIGGER_LOOKBACK_SESSIONS} 个交易日内出现最早期转向迹象的个股，并预先算好复核清单。"
    "这些是观察窗口，不是确定结论——大多不会走成什么；本清单以“不漏看”为目标，"
    "因此刻意提前、也刻意嘈杂。"
)
AUTHORITY = (
    "Display tier, zero scored authority. Nothing here ranks, gates or sizes a graded "
    "position; the context score orders the deck for reading only."
)
AUTHORITY_ZH = (
    "仅供展示，无任何评分权重。此处内容不参与任何持仓的排序、准入或仓位；"
    "情境分只用于本清单的阅读排序。"
)
NOISE_NOTE = (
    "Built for recall: a trigger firing is evidence that something moved, not evidence "
    "that it will keep moving. The slow tier column says what the confirmation cascade "
    "thinks right now — often 'not yet', which is the point."
)
NOISE_NOTE_ZH = (
    "以“不漏看”为设计目标：触发只说明有迹象发生，并不说明会延续。"
    "“慢层”一栏显示确认级联当前的判断——常常是“尚未”，这正是本清单的意义。"
)

#: EN/ZH lexicon for the page that ships next session (design lane).  House convention is
#: small per-surface EN/ZH pairs co-located with the surface (`templates/_prophet_card.html.j2`
#: `_VEN`/`_VZH`, `dashboard.html.j2` `ENTRY_STATUS_EN`/`ENTRY_STATUS_ZH`); this data plane
#: carries its own so the page never has to invent vocabulary for engine states.
LEXICON: dict[str, dict[str, str]] = {
    "dot_1d": {"en": "Daily turn dot", "zh": "日线转向点"},
    "pre_confluence_2d": {"en": "2D crossed, 3D not yet", "zh": "2日已交叉，3日尚未"},
    "basket_turn": {"en": "Group turning", "zh": "板块转向中"},
    "leader_reset_turn": {"en": "Leader reset", "zh": "龙头回踩重置"},
    "washed": {"en": "Washed out", "zh": "深度洗盘"},
    "pinned_low": {"en": "Pinned low", "zh": "长期低位钝化"},
    "turning": {"en": "Turning", "zh": "转向中"},
    "not_yet": {"en": "Not yet", "zh": "尚未"},
    "watching": {"en": "Watching", "zh": "观察中"},
    "TURNING": {"en": "Turning", "zh": "转向中"},
    "CONFIRMED": {"en": "Confirmed", "zh": "已确认"},
}

#: Plain-word names for the confirmation cascade's blocking legs — the "why Prophet hasn't
#: admitted it yet" cell.  Keys are the leg ids emitted on every row.
BLOCKER_LEXICON: dict[str, dict[str, str]] = {
    "stoch_overbought": {"en": "3D stochastic already high", "zh": "3日随机指标已偏高"},
    "stoch_bear_cross": {"en": "3D stochastic still rolled over", "zh": "3日随机指标仍在下行"},
    "macd_below_signal": {"en": "3D momentum still below its signal", "zh": "3日动能仍低于信号线"},
    "stoch_3d_not_crossed": {"en": "3D stochastic has not crossed up recently",
                             "zh": "3日随机指标近期未金叉"},
    "no_deep_or_weekly_confirm": {"en": "no washout or weekly confirmation",
                                  "zh": "缺少洗盘或周线确认"},
    "rsi_too_hot": {"en": "3D RSI already hot", "zh": "3日 RSI 已偏热"},
    "macd_2d_not_crossed": {"en": "2D momentum has not crossed up", "zh": "2日动能尚未金叉"},
    "below_200dma": {"en": "below its 200-day average (the earliest tier needs it above)",
                     "zh": "低于 200 日均线（最早一级需站上均线）"},
}


# ---------------------------------------------------------------------------
# Store access
# ---------------------------------------------------------------------------

def _safe_stem(ticker: str) -> str:
    return ticker.replace("/", "_")


def load_close(ticker: str, data_root: Path,
               ladder: tuple[str, ...] = STORE_LADDER) -> tuple[pd.Series | None, str | None]:
    """Load one name's daily close, walking the store ladder.

    Returns ``(series, store)``; ``(None, None)`` when no rung carries a usable frame.
    A rung that exists but has no readable ``close`` falls through rather than returning a
    frame the caller cannot use (same contract as `us_basket_turn._load_close`).
    """
    stem = _safe_stem(ticker)
    for sub in ladder:
        p = data_root / sub / f"{stem}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
            if "close" not in df.columns or df.empty:
                continue
            s = df["close"].astype(float)
            s.index = pd.to_datetime(df.index)
            s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
            if s.empty:
                continue
            return s, sub
        except Exception as e:  # noqa: BLE001 — one unreadable file never kills the deck
            log.debug("load_close(%s) from %s/: %s", ticker, sub, e)
            continue
    return None, None


def universe(data_root: Path, limit: int | None = None) -> list[str]:
    """The graded deck universe: every plain ticker under ``data/<DECK_STORE>/``.

    Index proxies (``_GSPC``) and FX/futures store files (``DX-Y.NYB``) are excluded — they
    are not names a desk reviews.  The bar-count floor is applied later, per name, because
    it needs the frame.  ``limit`` takes the first N ALPHABETICALLY: a deterministic subset,
    never a sample, and disclosed in the artifact when used.
    """
    d = data_root / DECK_STORE
    if not d.exists():
        print(f"::warning title=us-turn-watch::price store {d} not found "
              f"— the deck is EMPTY for this run", flush=True)
        return []
    out = []
    for p in sorted(d.glob("*.parquet")):
        stem = p.stem
        if stem.startswith(_UNIVERSE_SKIP_PREFIXES):
            continue
        if stem.endswith(_UNIVERSE_SKIP_SUFFIXES):
            continue
        if any(ch in stem for ch in _UNIVERSE_SKIP_CHARS):
            continue
        out.append(stem)
    return out[:limit] if limit else out


# ---------------------------------------------------------------------------
# Trigger streams (per-day booleans — one vectorized pass serves live AND replay)
# ---------------------------------------------------------------------------

def _month_bars(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Completed monthly bars. ``ME`` on modern pandas, ``M`` on the legacy alias."""
    for rule in ("ME", "M"):
        try:
            v, k = _completed_resample(c, rule)
            if len(v):
                return v, k
        except Exception as e:  # noqa: BLE001
            log.debug("_month_bars(%s): %s", rule, e)
    return pd.Series(dtype="float64"), pd.Series(dtype="datetime64[ns]")


def dot_signature(close: pd.Series) -> pd.Series:
    """(a) The DOT SIGNATURE, per daily bar.

    Daily StochRSI %K crosses above %D, %D was below `OS` within the last
    `DOT_WASHED_WINDOW` sessions, and the daily RSI-MACD histogram is rising.

    Every leg is a trailing-window read on the DAILY series alone — no resampling — so this
    stream is exactly point-in-time on every interior day, with none of the incomplete-tail
    caveat the 2D/3D legs carry.
    """
    k, d = _stoch_rsi_kd(close)
    cross = _xup(k, d)
    washed = d.rolling(DOT_WASHED_WINDOW).min() < OS
    m, s = _rsi_macd(close)
    h = m - s
    rising = (h - h.shift(1)) > 0
    return (cross & washed & rising).fillna(False).astype(bool)


def pre_confluence_2d(close: pd.Series, market: str = "US") -> tuple[pd.Series, pd.Series]:
    """(b) Fresh 2D RSI-MACD cross while the 3D has NOT crossed — plus the 3D bars-to-cross.

    Returns ``(fired, btc3)``: a daily boolean stream and a daily float stream of the 3D
    RSI-MACD projected bars-to-cross (``-h3/slope3``, NaN unless the histogram is below zero
    and rising — the only regime in which a projection to an up-cross means anything).

    BASIS CAVEAT (inherited from `confluence_tiers.tier_stream`): the 2D/3D grids are
    absolute-session-anchored, so bucket EDGES do not move with the caller's slice, but the
    TRAILING bucket is still incomplete on the day it is read.  Interior days of a
    full-series pass therefore read a bucket that had not closed yet on that day.  A replay
    that needs the honest point-in-time read must truncate the series at each day before
    calling (the `prophet_stage_shadow` pattern) — :func:`first_deck_entry` does exactly that.
    """
    di = close.index
    sm, smk = _tf_bars(close, 2, market)
    m2, s2 = _rsi_macd(sm)
    mb2 = _xup(m2, s2)
    mb2_d = _to_daily(mb2.fillna(False), smk, di, "event")

    ss3, sk3 = _tf_bars(close, 3, market)
    m3, s3 = _rsi_macd(ss3)
    h3 = m3 - s3
    slope3 = h3 - h3.shift(1)
    btc3 = (-h3 / slope3).where((h3 < 0) & (slope3 > 0))
    h3_d = _to_daily(h3, sk3, di)
    btc3_d = _to_daily(btc3, sk3, di)

    # "fresh": the 2D cross is <= FRESH_TICKS 2D-ticks old, measured on the 2D grid, which is
    # the same yardstick the cascade's T2 uses. `_to_daily(..., "event")` stamps the cross on
    # the daily bar of its own bucket's known-date, so counting 2D known-dates strictly after
    # that bar and at-or-before today gives the tick age POINT-IN-TIME (the <=-today bound is
    # the interior-day leak `_ticks_since_vec` documents — without it every interior day
    # counts future buckets and never looks fresh). Both counts are searchsorted rather than
    # a per-day scan: the naive form is O(days x buckets) and 740 names of it does not fit the
    # nightly budget.
    kvv = pd.to_datetime(pd.Series(smk).to_numpy()).values
    di_vals = di.values
    cross_pos = np.maximum.accumulate(
        np.where(mb2_d.to_numpy().astype(bool), np.arange(len(di)), -1))
    has_cross = cross_pos >= 0
    cross_dates = di_vals[np.maximum(cross_pos, 0)]
    ticks = (np.searchsorted(kvv, di_vals, side="right")
             - np.searchsorted(kvv, cross_dates, side="right"))
    fresh = has_cross & (ticks <= FRESH_TICKS)
    not_crossed_3d = (h3_d < 0).fillna(False).to_numpy().astype(bool)
    fired = pd.Series(fresh & not_crossed_3d, index=di)
    return fired.astype(bool), btc3_d


def leader_reset_turn(close: pd.Series, benchmark: pd.Series | None) -> pd.Series:
    """(d) The MINIMAL INLINE leader-pullback reset signature — see the swap-in note above.

    High relative strength over `LEADER_RS_WINDOW` vs the benchmark, price above its 200dMA
    (uptrend intact), a controlled retrace from the `LEADER_RETRACE_WINDOW` high inside
    [`LEADER_RETRACE_MIN`, `LEADER_RETRACE_MAX`], the daily %D reset below `LEADER_RESET_MAX`
    within `DOT_WASHED_WINDOW` sessions, and %K turning up through %D today.

    Returns an all-False stream (never a null that reads as a verdict) when the benchmark is
    unavailable — the caller records ``leader_reset_turn`` as unevaluated in that case.
    """
    di = close.index
    false_s = pd.Series(False, index=di)
    if benchmark is None or benchmark.empty:
        return false_s
    bench = benchmark.reindex(di).ffill()
    r_name = close / close.shift(LEADER_RS_WINDOW) - 1.0
    r_bench = bench / bench.shift(LEADER_RS_WINDOW) - 1.0
    rs_leader = (r_name - r_bench) > 0

    ma = close.rolling(MA_WINDOW).mean()
    uptrend = close > ma

    hi = close.rolling(LEADER_RETRACE_WINDOW).max()
    retrace = 1.0 - (close / hi)
    controlled = (retrace >= LEADER_RETRACE_MIN) & (retrace <= LEADER_RETRACE_MAX)

    k, d = _stoch_rsi_kd(close)
    reset = d.rolling(DOT_WASHED_WINDOW).min() < LEADER_RESET_MAX
    turn = _xup(k, d)

    return (rs_leader & uptrend & controlled & reset & turn).fillna(False).astype(bool)


def _leader_source() -> tuple[Any | None, str]:
    """Soft-import the R4 leader-pullback organ. Returns ``(callable_or_None, source_id)``."""
    try:
        from engine import us_leader_pullback as organ  # type: ignore  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — absent on this base is the EXPECTED path
        return None, "inline_minimal_v1"
    for name in _LEADER_ENTRY_POINTS:
        fn = getattr(organ, name, None)
        if callable(fn):
            return fn, f"engine.us_leader_pullback:{name}"
    return None, "inline_minimal_v1 (organ present, no known entry point)"


def _leader_stream(close: pd.Series, benchmark: pd.Series | None) -> tuple[pd.Series, str]:
    fn, src = _leader_source()
    if fn is not None:
        try:
            out = fn(close, benchmark)
            if isinstance(out, pd.Series):
                return out.reindex(close.index).fillna(False).astype(bool), src
            log.debug("us_turn_watch: %s returned %s, not a Series", src, type(out))
        except Exception as e:  # noqa: BLE001 — a sibling organ never kills the deck
            log.debug("us_turn_watch: %s raised %s — falling back inline", src, e)
        src = f"inline_minimal_v1 (fallback from {src})"
    return leader_reset_turn(close, benchmark), src


# ---------------------------------------------------------------------------
# Context columns
# ---------------------------------------------------------------------------

def _f(x: Any, nd: int = 2) -> float | None:
    """Round to a JSON-safe float, or None. Never emits NaN/inf into an artifact."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


def _trailing_true(mask: np.ndarray) -> int:
    """Consecutive True values ending at the last element (0 when the last is False)."""
    n = 0
    for v in mask[::-1]:
        if not bool(v):
            break
        n += 1
    return n


def htf_washout(close: pd.Series) -> dict[str, Any]:
    """Higher-timeframe washout state on the MONTHLY and 2W StochRSI.

    Per timeframe: ``pinned_low`` (%D below `OS` at the last completed bar),
    ``sessions_pinned`` (consecutive DAILY sessions on which the mapped %D has been below
    `OS`), and ``turning`` (%K above %D and crossed up within `CONF_W` native bars).

    Each leg is None-with-a-reason when the history cannot support it — never False.
    """
    di = close.index
    out: dict[str, Any] = {}
    for label, bars in (("monthly", _month_bars(close)),
                        ("w2", _completed_resample(close, "2W-FRI"))):
        v, kn = bars
        cell: dict[str, Any] = {"pinned_low": None, "sessions_pinned": None,
                                "turning": None, "null_reason": None}
        try:
            if len(v) < 20:
                cell["null_reason"] = f"needs 20 {label} bars, has {len(v)}"
                out[label] = cell
                continue
            k, d = _stoch_rsi_kd(v)
            if not bool(pd.notna(d.iloc[-1])):
                cell["null_reason"] = f"{label} StochRSI not knowable yet ({len(v)} bars)"
                out[label] = cell
                continue
            d_daily = _to_daily(d, kn, di)
            pinned_daily = (d_daily < OS).fillna(False).to_numpy().astype(bool)
            crossed = _xup(k, d).fillna(False).to_numpy().astype(bool)[::-1]
            recent = int(np.argmax(crossed)) if crossed.any() else None
            cell["pinned_low"] = bool(d.iloc[-1] < OS)
            cell["sessions_pinned"] = int(_trailing_true(pinned_daily))
            cell["turning"] = bool(
                bool(k.iloc[-1] >= d.iloc[-1]) and recent is not None and recent <= CONF_W
            )
        except Exception as e:  # noqa: BLE001
            cell["null_reason"] = f"{label} washout read failed: {e}"
        out[label] = cell
    return out


def base_context(close: pd.Series) -> dict[str, Any]:
    """Off-high, base depth and base age — three DIFFERENT readings, not one repeated.

    ``off_52w_high_pct``  TODAY's distance below the trailing `BASE_WINDOW` high.
    ``base_depth_pct``    the DEEPEST close since that high was printed — how deep the base
                          the name is climbing out of actually got.
    ``base_age_sessions`` sessions since that high, i.e. how long the base has been building.
    """
    out = {"off_52w_high_pct": None, "base_depth_pct": None, "base_age_sessions": None}
    try:
        w = close.tail(BASE_WINDOW)
        if len(w) < 30:
            return out
        hi = float(w.max())
        if not np.isfinite(hi) or hi <= 0:
            return out
        hi_pos = int(np.argmax(w.to_numpy()))
        since = w.iloc[hi_pos:]
        out["off_52w_high_pct"] = _f((float(w.iloc[-1]) / hi - 1.0) * 100.0)
        out["base_depth_pct"] = _f((float(since.min()) / hi - 1.0) * 100.0)
        out["base_age_sessions"] = int(len(w) - 1 - hi_pos)
    except Exception as e:  # noqa: BLE001
        log.debug("base_context: %s", e)
    return out


def reset_low(close: pd.Series, window: int = REL_WINDOW) -> dict[str, Any]:
    """The reset low the row is trading off — the STRUCTURE anchor, not price-at-signal-time.

    Reported because a sibling receipt (PR #5007) measured the zone mechanism moving
    entry-vs-low from 7.26% to 2.29%: a late signal stops implying a late PRICE when the plan
    waits at a band instead of chasing the close.  This cell is the cheap half of that — the
    anchor and today's distance from it — so the R3 entry-zone builder has a structure low to
    build a band from and the operator can see how far a row has already run off its reset.

    It is NOT a buy zone and does not claim to be one: no band, no chase-above, no size.
    Returns ``{reset_low, reset_low_date, off_reset_low_pct, window}``; all None when unknowable.
    """
    out: dict[str, Any] = {"reset_low": None, "reset_low_date": None,
                           "off_reset_low_pct": None, "window": int(window)}
    try:
        w = close.tail(window)
        if len(w) < 5:
            return out
        lo = float(w.min())
        if not np.isfinite(lo) or lo <= 0:
            return out
        out["reset_low"] = _f(lo, 4)
        out["reset_low_date"] = str(pd.Timestamp(w.index[int(np.argmin(w.to_numpy()))]).date())
        out["off_reset_low_pct"] = _f((float(close.iloc[-1]) / lo - 1.0) * 100.0)
    except Exception as e:  # noqa: BLE001
        log.debug("reset_low: %s", e)
    return out


def rel_strength_pp(close: pd.Series, benchmark: pd.Series | None,
                    window: int = REL_WINDOW) -> float | None:
    """N-session return minus the benchmark's, in percentage points. None when unknowable."""
    if benchmark is None or benchmark.empty or len(close) <= window:
        return None
    try:
        b = benchmark.reindex(close.index).ffill()
        if len(b.dropna()) <= window:
            return None
        rn = float(close.iloc[-1]) / float(close.iloc[-1 - window]) - 1.0
        rb = float(b.iloc[-1]) / float(b.iloc[-1 - window]) - 1.0
        return _f((rn - rb) * 100.0)
    except Exception as e:  # noqa: BLE001
        log.debug("rel_strength_pp: %s", e)
        return None


def ma_distance_pct(close: pd.Series, window: int = MA_WINDOW) -> float | None:
    """Distance above/below the N-day average in %. **None, never False/0, when unknowable**
    (the PLTR `above200` narration-gap precedent: an unknowable average must not read as
    'below its 200-day average')."""
    if len(close) < window:
        return None
    try:
        ma = float(close.rolling(window).mean().iloc[-1])
        if not np.isfinite(ma) or ma <= 0:
            return None
        return _f((float(close.iloc[-1]) / ma - 1.0) * 100.0)
    except Exception as e:  # noqa: BLE001
        log.debug("ma_distance_pct: %s", e)
        return None


def slow_tier_cell(close: pd.Series, btc3: float | None,
                   market: str = "US") -> dict[str, Any]:
    """"What the slow tier says NOW" — the why-not receipt, computed live.

    This cell is the R5 why-not receipt in the deck's own row: the confirmation cascade's
    verdict today, the legs that are BLOCKING it by name, and how many 3D bars the momentum
    projection is from crossing.  It is what turns "Prophet hasn't admitted it yet" from a
    silence into a printed reason.
    """
    cell: dict[str, Any] = {
        "tier": None, "sub": None, "ticks": None, "eligible": False, "not_topped": None,
        "bars_to_cross_3d": _f(btc3), "blocking": [], "s1": False, "s2": False,
        "above_200dma": None, "null_legs": {}, "evaluated": False,
    }
    try:
        v = cascade(close, market=market)
    except Exception as e:  # noqa: BLE001 — cascade never raises, but never trust that here
        log.debug("slow_tier_cell cascade: %s", e)
        return cell
    cell.update(
        tier=v.get("tier"), sub=v.get("sub"), ticks=v.get("ticks"),
        eligible=bool(v.get("eligible")), not_topped=v.get("not_topped"),
        s1=bool((v.get("htf") or {}).get("s1")), s2=bool((v.get("htf") or {}).get("s2")),
        above_200dma=v.get("above200"), null_legs=v.get("null_legs") or {},
        evaluated=bool(v.get("evaluated", True)),
    )

    # Blocking legs, by name. The cascade publishes `not_topped` as a single boolean and its
    # warmup nulls, but not WHICH leg refused — so the three veto legs and the tier-eligibility
    # legs are re-read here off the same instrument (same helpers, same anchor era).
    blockers: list[str] = []
    try:
        c = close.dropna()
        di = c.index
        last = len(di) - 1
        ss3, sk3 = _tf_bars(c, 3, market)
        k3, d3 = _stoch_rsi_kd(ss3)
        m3, s3 = _rsi_macd(ss3)
        from engine.confluence_tiers import BUY_RSI_MAX, OB, _since  # noqa: PLC0415
        from engine.technicals import rsi as _rsi  # noqa: PLC0415
        k3_d = _to_daily(k3, sk3, di).iloc[last]
        d3_d = _to_daily(d3, sk3, di).iloc[last]
        m3_d = _to_daily(m3, sk3, di).iloc[last]
        s3_d = _to_daily(s3, sk3, di).iloc[last]
        if float(k3_d) >= OB or float(d3_d) >= OB:
            blockers.append("stoch_overbought")
        if float(k3_d) < float(d3_d):
            blockers.append("stoch_bear_cross")
        if float(m3_d) < float(s3_d):
            blockers.append("macd_below_signal")

        sb3 = _xup(k3, d3)
        recent3 = _to_daily((_since(sb3) <= CONF_W).fillna(False), sk3, di).fillna(False)
        if not bool(recent3.iloc[last]):
            blockers.append("stoch_3d_not_crossed")
        fromos3 = _to_daily((d3.rolling(CONF_W).min() < OS).fillna(False), sk3, di).fillna(False)
        wk = c.resample("W-FRI").last().dropna()
        wm, ws = _rsi_macd(wk)
        wbull = (wm >= ws).shift(1).reindex(di, method="ffill").fillna(False)
        if not (bool(fromos3.iloc[last]) or bool(wbull.iloc[last])):
            blockers.append("no_deep_or_weekly_confirm")
        r14 = _to_daily(_rsi(ss3, 14), sk3, di).iloc[last]
        if bool(pd.notna(r14)) and float(r14) >= BUY_RSI_MAX:
            blockers.append("rsi_too_hot")

        sm, smk = _tf_bars(c, 2, market)
        m2, s2 = _rsi_macd(sm)
        h2_last = _to_daily(m2 - s2, smk, di).iloc[last]
        if bool(pd.notna(h2_last)) and float(h2_last) < 0:
            blockers.append("macd_2d_not_crossed")
        if cell["above_200dma"] is False:
            blockers.append("below_200dma")
    except Exception as e:  # noqa: BLE001
        log.debug("slow_tier_cell blockers: %s", e)
    # An ADMITTED name has no why-not. Publishing legs beside a live tier reads as "T2, but
    # blocked" — which is false, and this cell's entire job is to answer "why has the
    # confirmation tier not taken this yet". The legs are still visible on their own fields
    # (`above_200dma`, `not_topped`); only the BLOCKING claim is withheld.
    cell["blocking"] = [] if cell["eligible"] else blockers
    return cell


# ---------------------------------------------------------------------------
# Context score (DISPLAY-ONLY sort key)
# ---------------------------------------------------------------------------

#: The published formula, verbatim, so the artifact carries its own definition.
CONTEXT_SCORE_FORMULA = (
    "context_score = 100 x (0.30*recency + 0.20*breadth + 0.15*washout + 0.15*base "
    "+ 0.10*cohort + 0.10*proximity), each term in [0,1]. "
    "recency = 1 - days_since_newest_DATED_trigger/LOOKBACK (group-turn is a state, not a "
    "dated event, and is excluded from this term). "
    "breadth = triggers_fired/4. "
    "washout = 0.6*monthly_pinned_low + 0.4*two_week_pinned_low. "
    "base = min(|base_depth_pct|, 50)/50. "
    "cohort = 1.0 CONFIRMED / 0.6 TURNING / 0 none. "
    "proximity = 1 if the slow tier is already live, else "
    "max(0, 1 - bars_to_cross_3d/4) when that projection exists. "
    "An unknowable term contributes 0 and is NAMED in context_score_nulls."
)
CONTEXT_SCORE_LABEL = (
    "Non-authoritative. A reading order for this deck only — not a rank, not a score, "
    "not an input to any graded lane."
)
CONTEXT_SCORE_LABEL_ZH = (
    "非权威指标。仅用于本清单的阅读排序——不是排名、不是评分，也不进入任何评级流程。"
)


def context_score(row: dict[str, Any]) -> tuple[float, list[str]]:
    """The display-only sort key. Returns ``(score, nulls)``; see `CONTEXT_SCORE_FORMULA`.

    Every unknowable term contributes ZERO and is named in ``nulls``, so a row that sorts low
    because its context could not be read is distinguishable from one that sorts low because
    its context was read and was thin.  That distinction is the whole reason the null list
    is published beside the number.
    """
    nulls: list[str] = []

    fired = [t for t in TRIGGER_IDS if (row.get("triggers", {}).get(t) or {}).get("fired")]
    # RECENCY reads the name's OWN dated evidence only. `basket_turn` is a STATE, not a dated
    # event — its days_since is 0 for as long as the group holds the state — so counting it
    # here would hand every member of a turning basket full recency and let a name that did
    # nothing itself outrank one whose dot printed yesterday. The group's contribution lives
    # in the cohort term, where it belongs.
    dated = [t for t in fired if t != "basket_turn"]
    ds = [d for d in ((row["triggers"][t] or {}).get("days_since") for t in dated)
          if d is not None]
    if ds:
        recency = max(0.0, 1.0 - (min(ds) / float(TRIGGER_LOOKBACK_SESSIONS)))
    else:
        recency = 0.0
        nulls.append("recency: group-turn state only — no dated per-name event")
    breadth = len(fired) / float(len(TRIGGER_IDS))

    htf = row.get("htf_washout") or {}
    mo, w2 = htf.get("monthly") or {}, htf.get("w2") or {}
    washout = 0.0
    if mo.get("pinned_low") is None:
        nulls.append("washout.monthly: " + str(mo.get("null_reason") or "not knowable"))
    elif mo["pinned_low"]:
        washout += 0.6
    if w2.get("pinned_low") is None:
        nulls.append("washout.2w: " + str(w2.get("null_reason") or "not knowable"))
    elif w2["pinned_low"]:
        washout += 0.4

    depth = (row.get("base") or {}).get("base_depth_pct")
    if depth is None:
        base = 0.0
        nulls.append("base: depth not knowable")
    else:
        base = min(abs(float(depth)), 50.0) / 50.0

    bstate = (row.get("basket") or {}).get("turn_state")
    cohort = 1.0 if bstate == "CONFIRMED" else (0.6 if bstate == "TURNING" else 0.0)

    slow = row.get("slow_tier") or {}
    if slow.get("eligible"):
        proximity = 1.0
    else:
        btc = slow.get("bars_to_cross_3d")
        if btc is None:
            proximity = 0.0
            nulls.append("proximity: no 3D cross projection")
        else:
            proximity = max(0.0, 1.0 - float(btc) / 4.0)

    score = 100.0 * (0.30 * recency + 0.20 * breadth + 0.15 * washout
                     + 0.15 * base + 0.10 * cohort + 0.10 * proximity)
    return round(float(score), 2), nulls


# ---------------------------------------------------------------------------
# Basket / cohort context
# ---------------------------------------------------------------------------

def _read_membership(data_root: Path) -> dict[str, dict]:
    p = data_root / "baskets" / "membership.json"
    if not p.exists():
        print("::warning title=us-turn-watch::membership.json not found "
              "— every row's group column is NULL for this run", flush=True)
        return {}
    try:
        raw = json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"::warning title=us-turn-watch::membership.json unreadable ({e}) "
              f"— every row's group column is NULL for this run", flush=True)
        return {}
    return {bid: b for bid, b in (raw.get("baskets") or {}).items()
            if not bid.startswith(("cn_", "hk_", "ca_"))}


def _read_basket_turn(data_root: Path, site_root: Path) -> dict[str, dict]:
    """Per-basket lifecycle state from `engine.us_basket_turn`'s committed artifact.

    Artifact first (``site/basketdata/us_basket_turn.json``), ledger second — this module
    computes NO basket state of its own; it reads that organ or prints nothing.
    """
    out: dict[str, dict] = {}
    p = site_root / "basketdata" / "us_basket_turn.json"
    try:
        if p.exists():
            raw = json.loads(p.read_text())
            for bid, b in (raw.get("baskets") or {}).items():
                out[bid] = {"state": b.get("state"), "days_in_state": b.get("days_in_state"),
                            "data_session": b.get("data_session"), "source": "artifact"}
            return out
    except Exception as e:  # noqa: BLE001
        log.debug("_read_basket_turn artifact: %s", e)
    try:
        from engine.us_basket_turn import load_ledger  # noqa: PLC0415
        rows = load_ledger(data_root)
        for r in rows:
            bid = r.get("basket_id")
            if bid:
                out[bid] = {"state": r.get("state"), "days_in_state": r.get("days_in_state"),
                            "data_session": r.get("date"), "source": "ledger"}
    except Exception as e:  # noqa: BLE001
        log.debug("_read_basket_turn ledger: %s", e)
    if not out:
        print("::warning title=us-turn-watch::no us_basket_turn state readable "
              "— the group-turn trigger is UNEVALUATED for this run", flush=True)
    return out


def _basket_index(membership: dict[str, dict]) -> dict[str, list[str]]:
    """ticker -> [basket_id, ...] over currently-active members."""
    idx: dict[str, list[str]] = {}
    for bid, b in membership.items():
        for m in (b.get("members") or []):
            if m.get("removed") is not None or not m.get("ticker"):
                continue
            idx.setdefault(m["ticker"], []).append(bid)
    return idx


def _basket_rel(membership: dict[str, dict], closes: dict[str, pd.Series],
                benchmark: pd.Series | None) -> dict[str, float | None]:
    """Each basket's `REL_WINDOW`-session EW level return minus the benchmark's, in pp.

    Levels are built with `us_basket_turn.ew_level_from_closes` — the same point-in-time
    dated-membership construction that organ classifies on — so the group column and the
    group's turn state are reading the same tape.  DEVIATION, disclosed: member closes here
    come from THIS module's store ladder (yahoo first), while that organ's ladder is
    stocks-then-baskets/ohlcv.  Both stores are nightly-refreshed from the same collectors;
    a basket whose members split across the two can differ in the last decimal of this
    DISPLAY-ONLY number.  It is never compared to that organ's numbers, only shown beside them.
    """
    out: dict[str, float | None] = {}
    try:
        from engine.us_basket_turn import active_members, ew_level_from_closes  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        log.debug("_basket_rel import: %s", e)
        return out
    for bid, b in membership.items():
        try:
            lvl = ew_level_from_closes(active_members(b), closes)
            out[bid] = rel_strength_pp(lvl, benchmark) if not lvl.empty else None
        except Exception as e:  # noqa: BLE001
            log.debug("_basket_rel(%s): %s", bid, e)
            out[bid] = None
    return out


def apply_cap(rows: list[dict[str, Any]], cap: int = DECK_CAP,
              lane_floor: int = LANE_FLOOR) -> tuple[list[dict], list[dict]]:
    """Cap the deck WITHOUT deleting a lane. Returns ``(deck, beyond_cap)``.

    ``rows`` must already be sorted by context score, descending.  Each trigger lane first
    claims up to ``lane_floor`` of its own highest-scoring rows (a lane with fewer firing
    names claims fewer — the floor is a ceiling on the guarantee, never padding); the
    remaining slots then fill strictly by score.  The returned deck is re-sorted by score so
    the reading order is still one number, and the floor is disclosed in the artifact.

    ``lane_floor`` is clamped so four lanes can never overrun a small cap.
    """
    if cap <= 0:
        return [], list(rows)
    floor = min(max(0, lane_floor), max(1, cap // max(1, len(TRIGGER_IDS))))
    taken: set[str] = set()
    order: list[dict] = []
    for tid in TRIGGER_IDS:
        n = 0
        for r in rows:
            if n >= floor or len(order) >= cap:
                break
            if r["ticker"] in taken or tid not in r.get("triggers_fired", []):
                continue
            taken.add(r["ticker"])
            order.append(r)
            n += 1
    for r in rows:
        if len(order) >= cap:
            break
        if r["ticker"] in taken:
            continue
        taken.add(r["ticker"])
        order.append(r)
    order.sort(key=lambda r: (-float(r.get("context_score") or 0.0), r["ticker"]))
    return order, [r for r in rows if r["ticker"] not in taken]


def _pick_basket(bids: list[str], membership: dict[str, dict],
                 turn: dict[str, dict]) -> str | None:
    """The row's PRIMARY group: a turning/confirmed basket first, then the most specific one.

    Sector baskets (``us_sector_*``) are the fallback of last resort — "Technology
    (Equal-Weight), 74 names" is a true statement about NVDA and a nearly useless one.
    """
    if not bids:
        return None
    turning = [b for b in bids if (turn.get(b) or {}).get("state") in BASKET_TURN_STATES]
    pool = turning or bids
    themed = [b for b in pool if not b.startswith("us_sector_")] or pool

    def size(b: str) -> int:
        return len([m for m in (membership.get(b, {}).get("members") or [])
                    if m.get("removed") is None])

    return sorted(themed, key=lambda b: (size(b), b))[0]


# ---------------------------------------------------------------------------
# Per-name evaluation
# ---------------------------------------------------------------------------

def evaluate(ticker: str, close: pd.Series, *, benchmark: pd.Series | None = None,
             basket_ctx: dict[str, Any] | None = None, market: str = "US",
             store: str | None = None) -> dict[str, Any]:
    """One deck row: the trigger union plus the whole pre-computed checklist. Never raises.

    ``basket_ctx`` carries the cohort columns the caller resolved once for the whole run
    (``{"basket_id","name","name_zh","turn_state","days_in_state","rel_20d_pp","sector",
    "fired_date"}``); pass None and the group columns publish as null.
    """
    row: dict[str, Any] = {
        "ticker": ticker, "store": store, "bars": int(len(close)),
        "asof": str(close.index[-1].date()) if len(close) else None,
        "close": _f(close.iloc[-1], 4) if len(close) else None,
        "in_deck_universe": store == DECK_STORE,
        "triggers": {}, "triggers_fired": [], "evaluated": True, "null_notes": [],
    }
    try:
        di = close.index
        dates = [str(d.date()) for d in di]

        dot = dot_signature(close)
        pre, btc3_stream = pre_confluence_2d(close, market)
        lead, lead_src = _leader_stream(close, benchmark)
        row["leader_pullback_source"] = lead_src
        if benchmark is None or benchmark.empty:
            row["null_notes"].append(
                f"{BENCHMARK} benchmark unavailable — leader-reset trigger and every "
                "relative-strength column are unevaluated, not False")

        streams = {"dot_1d": dot, "pre_confluence_2d": pre, "leader_reset_turn": lead}
        for tid, s in streams.items():
            arr = s.to_numpy().astype(bool)
            idx = np.where(arr)[0]
            last_i = int(idx[-1]) if len(idx) else None
            days_since = (len(di) - 1 - last_i) if last_i is not None else None
            unevaluated = (tid == "leader_reset_turn"
                           and (benchmark is None or benchmark.empty))
            row["triggers"][tid] = {
                "fired": bool(days_since is not None
                              and days_since < TRIGGER_LOOKBACK_SESSIONS),
                "last_date": dates[last_i] if last_i is not None else None,
                "days_since": days_since,
                "evaluated": not unevaluated,
            }

        bc = basket_ctx or {}
        b_state = bc.get("turn_state")
        b_fired = b_state in BASKET_TURN_STATES
        row["triggers"]["basket_turn"] = {
            "fired": bool(b_fired),
            "last_date": bc.get("fired_date") if b_fired else None,
            # A basket state is a STATE, not a dated event: the organ's ledger begins
            # 2026-08-07, so days_since is 0 while the state holds and null otherwise.
            # It is never back-dated to manufacture an earlier surfacing date.
            "days_since": 0 if b_fired else None,
            "evaluated": bool(bc.get("turn_state_evaluated", True)),
            "state": b_state,
            "days_in_state": bc.get("days_in_state"),
        }

        row["triggers_fired"] = [t for t in TRIGGER_IDS if row["triggers"][t]["fired"]]
        row["htf_washout"] = htf_washout(close)
        row["base"] = base_context(close)
        row["reset"] = reset_low(close)
        row["rel_20d_pp"] = rel_strength_pp(close, benchmark)
        row["ma200_distance_pct"] = ma_distance_pct(close)
        btc3_last = btc3_stream.iloc[-1] if len(btc3_stream) else None
        row["slow_tier"] = slow_tier_cell(close, btc3_last, market)
        row["basket"] = {
            "basket_id": bc.get("basket_id"), "name": bc.get("name"),
            "name_zh": bc.get("name_zh"), "turn_state": b_state,
            "days_in_state": bc.get("days_in_state"), "rel_20d_pp": bc.get("rel_20d_pp"),
            "sector": bc.get("sector"), "sector_name": bc.get("sector_name"),
        }
        score, nulls = context_score(row)
        row["context_score"] = score
        row["context_score_nulls"] = nulls
    except Exception as e:  # noqa: BLE001 — one bad name never kills the deck
        log.warning("us_turn_watch: %s evaluation failed: %s", ticker, e)
        row["evaluated"] = False
        row["null_notes"].append(f"evaluation failed: {e}")
        row["context_score"] = 0.0
        row["context_score_nulls"] = ["row not evaluated"]
    return row


# ---------------------------------------------------------------------------
# The deck
# ---------------------------------------------------------------------------

def _session_stamp(closes: dict[str, pd.Series],
                   benchmark: pd.Series | None) -> tuple[str | None, str | None, str | None]:
    """The deck's data session — **majority-based, never `max()`**.

    Returns ``(data_session, max_session, note)``.  ``data_session`` is the session the
    MAJORITY of the graded universe last printed; ``max_session`` is the newest bar anywhere;
    ``note`` is a plain-word disclosure when they differ.

    A `max()` stamp fails OPEN: one instrument reaching a later date makes the whole surface
    read fresh while the tape it computes on is behind.  That is G0.2's measured defect (6 of
    3,029 panel members flipped `delayed` to false on a frozen board, 2026-08-06) and it
    reproduced here on the first full run — five 24/7 crypto/FX tapes carried an 08-08 bar
    against 726 equities at 08-07.  The majority stamp cannot fail that way, and the max is
    published beside it so a genuinely advancing universe is still visible.
    """
    from collections import Counter  # noqa: PLC0415
    dates: list[str] = []
    for s in closes.values():
        try:
            if len(s):
                dates.append(str(pd.Timestamp(s.index[-1]).date()))
        except Exception:  # noqa: BLE001, S112
            continue
    if not dates:
        if benchmark is not None and len(benchmark):
            b = str(pd.Timestamp(benchmark.index[-1]).date())
            return b, b, "no graded names — session taken from the benchmark"
        return None, None, "no graded names and no benchmark — session is unknown"
    counts = Counter(dates)
    session = counts.most_common(1)[0][0]
    newest = max(dates)
    note = None
    if newest != session:
        ahead = counts[newest]
        note = (f"{ahead} of {len(dates)} graded names print a newer bar ({newest}); the "
                f"deck is stamped {session}, the session the majority of the tape reaches")
    return session, newest, note


def compute_deck(data_root: Path | None = None, site_root: Path | None = None, *,
                 universe_limit: int | None = None, cap: int = DECK_CAP,
                 lane_floor: int = LANE_FLOOR, market: str = "US") -> dict[str, Any]:
    """Build the whole deck. Never raises; returns the artifact dict.

    Schema (published; the page ships next session under the design lane):

    ``schema`` ``as_of`` ``data_session`` ``selection_era`` ``anchor_era``
    ``indicator_source`` ``disclosure``/``_zh`` ``authority``/``_zh`` ``noise_note``/``_zh``
    ``lexicon`` ``blocker_lexicon`` ``context_score``{``formula``,``label``,``label_zh``}
    ``triggers``  the four trigger ids and their EN/ZH labels
    ``coverage``  {universe, graded, skipped_short_history, deck, beyond_cap, universe_limit,
                   basket_states_read, benchmark}
    ``runtime_seconds``
    ``deck``      the capped, context-score-sorted rows (schema per :func:`evaluate`)
    ``beyond_cap`` the tickers that triggered but did not make the cap, in sort order
    """
    t0 = time.time()
    from lib import config as _cfg  # noqa: PLC0415
    root = data_root if data_root is not None else _cfg.data_dir()
    site = site_root if site_root is not None else _cfg.site_dir()

    bench, _ = load_close(BENCHMARK, root, ladder=(DECK_STORE,))
    membership = _read_membership(root)
    turn = _read_basket_turn(root, site)
    turn_evaluated = bool(turn)
    bidx = _basket_index(membership)

    tickers = universe(root, universe_limit)
    closes: dict[str, pd.Series] = {}
    stores: dict[str, str] = {}
    short: list[str] = []
    for tk in tickers:
        s, st = load_close(tk, root, ladder=(DECK_STORE,))
        if s is None:
            continue
        if len(s) < MIN_BARS:
            short.append(tk)
            continue
        closes[tk] = s
        stores[tk] = st or DECK_STORE

    # Group columns, resolved once for the whole run.
    brel = _basket_rel(membership, closes, bench)

    rows: list[dict[str, Any]] = []
    for tk in sorted(closes):
        bids = bidx.get(tk, [])
        primary = _pick_basket(bids, membership, turn)
        sector = next((b for b in bids if b.startswith("us_sector_")), None)
        tstate = (turn.get(primary) or {}) if primary else {}
        ctx = {
            "basket_id": primary,
            "name": (membership.get(primary) or {}).get("name") if primary else None,
            "name_zh": (membership.get(primary) or {}).get("name_zh") if primary else None,
            "turn_state": tstate.get("state"),
            "days_in_state": tstate.get("days_in_state"),
            "fired_date": tstate.get("data_session"),
            "rel_20d_pp": brel.get(primary) if primary else None,
            "sector": sector,
            "sector_name": (membership.get(sector) or {}).get("name") if sector else None,
            "turn_state_evaluated": turn_evaluated,
        }
        row = evaluate(tk, closes[tk], benchmark=bench, basket_ctx=ctx, market=market,
                       store=stores.get(tk))
        if row.get("triggers_fired"):
            rows.append(row)

    rows.sort(key=lambda r: (-float(r.get("context_score") or 0.0), r["ticker"]))
    deck, beyond = apply_cap(rows, cap, lane_floor)

    session, max_session, session_note = _session_stamp(closes, bench)

    elapsed = round(time.time() - t0, 2)
    if elapsed > RUNTIME_WARN_SECONDS:
        print(f"::warning title=us-turn-watch-runtime::deck took {elapsed}s "
              f"(> {RUNTIME_WARN_SECONDS}s) over {len(closes)} graded names — "
              f"consider universe_limit", flush=True)

    return {
        "schema": SCHEMA,
        "as_of": session or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        # MAJORITY session, never the universe max — see `_session_stamp`. `max_session` is
        # published beside it so an advancing tape stays visible without being able to
        # manufacture freshness for the rows that did not advance.
        "data_session": session,
        "max_session": max_session,
        "session_note": session_note,
        "selection_era": SELECTION_ERA,
        "anchor_era": ANCHOR_ERA,
        "indicator_source": INDICATOR_SOURCE,
        "disclosure": DISCLOSURE, "disclosure_zh": DISCLOSURE_ZH,
        "authority": AUTHORITY, "authority_zh": AUTHORITY_ZH,
        "noise_note": NOISE_NOTE, "noise_note_zh": NOISE_NOTE_ZH,
        "lexicon": LEXICON,
        "blocker_lexicon": BLOCKER_LEXICON,
        "context_score": {"formula": CONTEXT_SCORE_FORMULA,
                          "label": CONTEXT_SCORE_LABEL,
                          "label_zh": CONTEXT_SCORE_LABEL_ZH},
        "triggers": {t: LEXICON[t] for t in TRIGGER_IDS},
        "trigger_lookback_sessions": TRIGGER_LOOKBACK_SESSIONS,
        "coverage": {
            "universe": len(tickers),
            "graded": len(closes),
            "skipped_short_history": len(short),
            "min_bars": MIN_BARS,
            "triggered": len(rows),
            "deck": len(deck),
            "beyond_cap": len(beyond),
            "cap": cap,
            "lane_floor": lane_floor,
            "triggered_by_trigger": {t: sum(1 for r in rows if t in r["triggers_fired"])
                                     for t in TRIGGER_IDS},
            "deck_by_trigger": {t: sum(1 for r in deck if t in r["triggers_fired"])
                                for t in TRIGGER_IDS},
            "universe_limit": universe_limit,
            "basket_states_read": len(turn),
            "benchmark": BENCHMARK if bench is not None else None,
        },
        "runtime_seconds": elapsed,
        "deck": deck,
        "beyond_cap": [r["ticker"] for r in beyond],
    }


def write_artifact(artifact: dict[str, Any], site_root: Path | None = None) -> Path:
    """Write ``site/prophet/turn_watch.json``."""
    if site_root is None:
        from lib import config as _cfg  # noqa: PLC0415
        site_root = _cfg.site_dir()
    out_dir = site_root / "prophet"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "turn_watch.json"
    out.write_text(json.dumps(artifact, separators=(",", ":"), default=str) + "\n",
                   encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# Acceptance replay (§6.9 R8) — DESCRIPTIVE ONLY, writes nothing
# ---------------------------------------------------------------------------

def first_deck_entry(ticker: str, close: pd.Series, *, benchmark: pd.Series | None,
                     sessions: int = 120, market: str = "US") -> dict[str, Any]:
    """When would this name FIRST have entered the deck, and when did the slow tier admit it?

    Walks the last ``sessions`` daily bars, TRUNCATING the series at each day before every
    read, so the 2D/3D legs see the incomplete trailing bucket they actually had that day
    (the `prophet_stage_shadow` pattern; a full-series pass would hand every interior day a
    bucket that had not closed yet).  Writes nothing — a replayed date is evidence for a
    receipt, never a ledger row.

    Trigger (c) (group turn) is ABSENT from this replay by construction and said so on the
    return: `us_basket_turn`'s forward ledger begins 2026-08-07, so there is no honest
    historical basket state to read, and back-filling one would manufacture the very
    earliness the replay is meant to measure.  The dates below are therefore the union of
    (a), (b) and (d) only — a LOWER bound on the deck's surfacing date.

    TWO comparisons are returned, because the literal one is boundary-sensitive:

    * ``first_trigger_*`` — the FIRST deck entry anywhere in the window.  When
      ``first_trigger_at_window_start`` is true the name was already triggering before the
      window opened, so that date is a floor imposed by the window, not a measurement.
    * ``paired_trigger_*`` — the LAST deck entry at-or-before the confirmation date.  A tight
      lower bound, and usually ~1 session: `pre_confluence_2d` fires by construction on the
      bar before the 3D crosses, so the last trigger before a T2 is nearly always adjacent.
      Quoting this alone UNDERSTATES the desk and is kept precisely so it cannot be hidden.
    * ``leg_trigger_*`` — **the number that answers the operator's question.**  The FIRST deck
      entry inside the up-leg the confirmation happened on, where the leg starts at the low
      the `% off 20-day low` column is itself measured against (the minimum close in the 20
      sessions preceding the confirmation).  Trigger and confirmation are then measured off
      the SAME low, in the same move: "the desk had this at +6% while the confirmation tier
      took it at +15%" is a statement about one event, not two unrelated ones.

    Returns a dict; every field is None-with-a-note when it could not be measured.
    """
    out: dict[str, Any] = {
        "ticker": ticker, "sessions": int(sessions),
        "window_start": None, "first_trigger_at_window_start": None,
        "trigger_dates": [], "trigger_count": 0,
        "first_trigger_date": None, "first_trigger_ids": [],
        "off_20d_low_pct_at_trigger": None,
        "paired_trigger_date": None, "paired_trigger_ids": [],
        "off_20d_low_pct_at_paired_trigger": None, "paired_lead_sessions": None,
        "leg_low_date": None, "leg_trigger_date": None, "leg_trigger_ids": [],
        "off_20d_low_pct_at_leg_trigger": None, "leg_lead_sessions": None,
        "first_confirm_date": None, "first_confirm_tier": None,
        "off_20d_low_pct_at_confirm": None, "lead_sessions": None,
        # The board admits on ANY eligible tier, but T3/T4 are themselves projections — the
        # "confirmation" the operator waits on is a CROSSED tier. Both are reported so the
        # comparison cannot be accused of picking the flattering denominator.
        "first_any_tier_date": None, "first_any_tier": None,
        "off_20d_low_pct_at_any_tier": None, "lead_sessions_any_tier": None,
        "note": "triggers (a) dot_1d + (b) pre_confluence_2d + (d) leader_reset_turn only; "
                "(c) group-turn has no ledger history before 2026-08-07. "
                "confirm = first CROSSED tier (T1/T2); cascade awards no T1 without an "
                "explicit take_date, so in practice it is the first T2",
    }
    try:
        c = close.dropna()
        if len(c) < MIN_BARS + 5:
            out["note"] = f"only {len(c)} daily bars — below the {MIN_BARS}-bar deck floor"
            return out
        di = c.index
        start = max(MIN_BARS, len(di) - int(sessions))
        out["window_start"] = str(di[start].date())
        low20 = c.rolling(20).min()

        def off_low(i: int) -> float | None:
            lo = low20.iloc[i]
            if not bool(pd.notna(lo)) or float(lo) <= 0:
                return None
            return _f((float(c.iloc[i]) / float(lo) - 1.0) * 100.0)

        fires: list[tuple[int, list[str]]] = []
        for i in range(start, len(di)):
            w = c.iloc[: i + 1]
            b = benchmark.reindex(w.index).ffill() if benchmark is not None else None
            fired: list[str] = []
            if bool(dot_signature(w).iloc[-1]):
                fired.append("dot_1d")
            pre, _btc = pre_confluence_2d(w, market)
            if bool(pre.iloc[-1]):
                fired.append("pre_confluence_2d")
            lead, _src = _leader_stream(w, b)
            if bool(lead.iloc[-1]):
                fired.append("leader_reset_turn")
            if fired:
                fires.append((i, fired))
                if out["first_trigger_date"] is None:
                    out["first_trigger_date"] = str(di[i].date())
                    out["first_trigger_ids"] = fired
                    out["off_20d_low_pct_at_trigger"] = off_low(i)
                    out["first_trigger_at_window_start"] = bool(i - start <= 2)
            if out["first_confirm_date"] is None or out["first_any_tier_date"] is None:
                v = cascade(w, market=market)
                if v.get("eligible"):
                    if out["first_any_tier_date"] is None:
                        out["first_any_tier_date"] = str(di[i].date())
                        out["first_any_tier"] = v.get("tier")
                        out["off_20d_low_pct_at_any_tier"] = off_low(i)
                    if out["first_confirm_date"] is None and v.get("tier") in ("T1", "T2"):
                        out["first_confirm_date"] = str(di[i].date())
                        out["first_confirm_tier"] = v.get("tier")
                        out["off_20d_low_pct_at_confirm"] = off_low(i)
        out["trigger_dates"] = [str(di[i].date()) for i, _ in fires]
        out["trigger_count"] = len(fires)

        # PAIRED: the last deck entry at-or-before the admission that actually happened.
        # The first-in-window entry is a floor imposed by the window; this is the lead the
        # desk would have given on THAT event, measured against the same 20-day low.
        if out["first_confirm_date"] and fires:
            cpos = int(di.get_indexer([pd.Timestamp(out["first_confirm_date"])])[0])
            before = [(i, ids) for i, ids in fires if i <= cpos]
            if before:
                pi, pids = before[-1]
                out["paired_trigger_date"] = str(di[pi].date())
                out["paired_trigger_ids"] = pids
                out["off_20d_low_pct_at_paired_trigger"] = off_low(pi)
                out["paired_lead_sessions"] = int(cpos - pi)

            # LEG: the first deck entry inside the up-leg the confirmation happened on.
            # The leg starts at the low the `% off 20-day low` column is itself measured
            # against, so trigger and confirmation are read off the SAME low in the SAME
            # move. This is the comparison that answers "would I have seen it before the
            # run" — `paired` above is adjacent by construction and understates the desk.
            lo_win = c.iloc[max(0, cpos - 19): cpos + 1]
            if len(lo_win):
                lpos = int(cpos - (len(lo_win) - 1 - int(np.argmin(lo_win.to_numpy()))))
                out["leg_low_date"] = str(di[lpos].date())
                in_leg = [(i, ids) for i, ids in fires if lpos <= i <= cpos]
                if in_leg:
                    li, lids = in_leg[0]
                    out["leg_trigger_date"] = str(di[li].date())
                    out["leg_trigger_ids"] = lids
                    out["off_20d_low_pct_at_leg_trigger"] = off_low(li)
                    out["leg_lead_sessions"] = int(cpos - li)

        def _lead(when: str | None) -> int | None:
            if not (out["first_trigger_date"] and when):
                return None
            a = int(di.get_indexer([pd.Timestamp(out["first_trigger_date"])])[0])
            b2 = int(di.get_indexer([pd.Timestamp(when)])[0])
            return int(b2 - a) if a >= 0 and b2 >= 0 else None

        out["lead_sessions"] = _lead(out["first_confirm_date"])
        out["lead_sessions_any_tier"] = _lead(out["first_any_tier_date"])
        if out["first_trigger_date"] and not out["first_confirm_date"]:
            out["note"] += "; the confirmation tier never admitted it in this window"
        elif not out["first_trigger_date"]:
            out["note"] += "; no trigger fired in this window"
    except Exception as e:  # noqa: BLE001
        out["note"] = f"replay failed: {e}"
    return out


def run(data_root: Path | None = None, site_root: Path | None = None, *,
        universe_limit: int | None = None) -> dict[str, Any]:
    """Nightly entry point: compute the deck and write the artifact."""
    art = compute_deck(data_root, site_root, universe_limit=universe_limit)
    p = write_artifact(art, site_root)
    log.info("us_turn_watch: wrote %s (%d rows, %d triggered, %.1fs)",
             p, len(art["deck"]), art["coverage"]["triggered"], art["runtime_seconds"])
    return art


def _main(argv: list[str] | None = None) -> int:  # pragma: no cover — CLI
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=None,
                    help="deterministic alphabetical universe subset (disclosed in artifact)")
    ap.add_argument("--replay", nargs="+", metavar="TICKER",
                    help="acceptance replay for these names (writes nothing)")
    ap.add_argument("--sessions", type=int, default=120)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    from lib import config as _cfg
    root = _cfg.data_dir()
    if args.replay:
        bench, _ = load_close(BENCHMARK, root, ladder=(DECK_STORE,))
        for tk in args.replay:
            s, st = load_close(tk, root)
            if s is None:
                print(f"{tk}: no store file on any rung of {STORE_LADDER}")
                continue
            r = first_deck_entry(tk, s, benchmark=bench, sessions=args.sessions)
            print(f"{tk} [{st}] trigger={r['first_trigger_date']} "
                  f"({','.join(r['first_trigger_ids']) or '-'}) "
                  f"off20low={r['off_20d_low_pct_at_trigger']}  "
                  f"confirm={r['first_confirm_date']} ({r['first_confirm_tier']}) "
                  f"off20low={r['off_20d_low_pct_at_confirm']}  lead={r['lead_sessions']}")
        return 0

    art = run()
    print(f"deck={len(art['deck'])} triggered={art['coverage']['triggered']} "
          f"graded={art['coverage']['graded']} runtime={art['runtime_seconds']}s")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
