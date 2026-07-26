"""Honest episode scoring shared by the four Track-record desks (US / CN / HK / CA).

WHY THIS MODULE EXISTS
----------------------
Before 2026-07-26 each desk scored its own board with its own conventions, and the
US desk's conventions were wrong in three ways that all pushed the headline UP:

  * entry was the close on the board's OWN as_of date — the bar the board is computed
    from, published that evening. Unbuyable. Worth +5.5pp of win rate and 69% of the
    reported average return.
  * "exit" was the latest close available today, so a pick's holding period was
    however many days happened to have elapsed since it surfaced — 1 to 17 sessions,
    pooled into one win rate.
  * a ticker's episode was anchored to its FIRST-EVER appearance, so a name that ran,
    left the board, and came back was still marked from the original date and sat in
    `onboard` (outside the win rate) forever.

THE THREE RULES THAT MAKE THE NUMBER HONEST
-------------------------------------------
1. **FORCED VERDICT AT MATURITY.** Every scored episode is resolved at exactly
   ``horizon`` forward sessions. A rule-based early exit (oscillator overbought, stop
   break) may fire EARLY; it may NEVER extend the horizon.

   This is not a stylistic choice — it is the whole design. The tempting alternative
   ("resolve when the thesis resolves: overbought = win, stop = loss, else still in
   flight") was measured on 2026-07-26 and reported 83.6% win / 5.05 profit factor.
   It was an artefact. The overbought leg fires WHEN PRICE RALLIES, so winners
   self-resolve in days while losers drift and sit unresolved forever. Measured on
   the US board: resolved episodes carried a +1.66% mean mark with 30% under water,
   unresolved ones −1.14% with 61% under water — a 2.8pp hole exactly where the
   losers went. The tell was that raising the overbought threshold 70→85 IMPROVED the
   win rate 76.8→85.5% while pushing 37%→62% of episodes into "in flight". A real
   edge does not improve when you count less of it.

   Any denominator conditioned on HOW a trade ended will do this. Resolve on time, or
   do not resolve at all.

2. **SYMMETRIC MATURITY GATE.** An episode is scored only once ``horizon`` forward
   bars EXIST for it. Younger episodes are counted and disclosed as in-flight, never
   silently dropped and never force-marked at a partial horizon. Exclusion by age is
   symmetric (it cannot know which way the trade went); exclusion by outcome is not.

3. **DATE-BLOCKED CONFIDENCE INTERVALS.** Episodes surfaced on the same board night
   are one bet, not N. Wilson-on-raw-n treats them as independent and reports an
   interval several times too narrow. ``date_block_ci`` resamples whole board days.
   ``n_board_days`` is emitted next to ``n_matured`` so the reader sees the effective
   sample, not the row count.

WHAT MAY DIFFER PER DESK (parameters, never structure)
------------------------------------------------------
  benchmark (SPY / CSI300 / HSI / TSX) · fill legality (A-share locked-limit days are
  unfillable) · headline metric (absolute P&L for US, benchmark excess for CN where
  beta dominates) · whether a rule-based early exit is enabled at all (CN runs
  fixed-horizon until the oscillator thresholds are refit for A-share volatility).

Grain, forced verdict, maturity gate, denominator, and CI method are IDENTICAL across
desks — two methodologies would mean two audit surfaces and no comparability.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

# Bootstrap settings. Seeded so a nightly re-render of unchanged inputs reproduces the
# same interval byte-for-byte (the render lane diffs artifacts; a wandering CI would
# churn the committed JSON every night for no reason).
BOOT_N = 2000
BOOT_SEED = 20260726

# Default forward horizon, in sessions. 10 ≈ two trading weeks. Chosen empirically on
# the US board 2026-07-26: at H=5 the board had NO edge (profit factor 0.99,
# expectancy −0.01%); at H=10 it had one (1.61, +0.97%). H=21 was unmeasurable — the
# record was 24 calendar days old and no episode had 21 forward bars.
DEFAULT_HORIZON = 10


# --------------------------------------------------------------------------- #
# episode construction
# --------------------------------------------------------------------------- #
def build_episodes(board_days: Mapping[str, Iterable[str]]) -> list[dict]:
    """Collapse a {board_date: {tickers}} history into CONTIGUOUS-RUN episodes.

    One episode = one uninterrupted stretch of board membership. A name that appears,
    drops off, and returns weeks later yields TWO episodes with two entries — not one
    record anchored to the first sighting (the bug this replaces: on 2026-07-26 the US
    ledger showed WAB as a single in-flight pick marked +12.2% from 2026-06-30, when
    WAB had been on the board for exactly one day in June and only returned on 07-23;
    the +12.2% was earned while the name was OFF the board).

    Returns dicts ``{ticker, entry_date, exit_date}`` with ``exit_date=None`` for runs
    still open on the most recent board. Order is by entry date, then ticker.
    """
    days = sorted(board_days)
    episodes: list[dict] = []
    prev: set[str] = set()
    open_runs: dict[str, str] = {}
    for d in days:
        cur = set(board_days[d])
        for tk in cur - prev:
            open_runs[tk] = d
        for tk in prev - cur:
            if tk in open_runs:
                episodes.append({"ticker": tk, "entry_date": open_runs.pop(tk), "exit_date": d})
        prev = cur
    for tk, entry in open_runs.items():
        episodes.append({"ticker": tk, "entry_date": entry, "exit_date": None})
    episodes.sort(key=lambda e: (e["entry_date"], e["ticker"]))
    return episodes


# --------------------------------------------------------------------------- #
# per-episode scoring
# --------------------------------------------------------------------------- #
_PENDING = {"entry": None, "entry_date": None, "n_avail": 0, "matured": False,
            "fill_pending": True, "exit": None, "pnl": None, "excess": None,
            "held": 0, "exit_reason": None, "mfe": None, "mae": None, "mark": None}


def score_from_fill(
    close: pd.Series,
    fill_date: Any,
    entry: float,
    horizon: int = DEFAULT_HORIZON,
    *,
    stop_level: float | None = None,
    early_exit: pd.Series | None = None,
    bench_close: pd.Series | None = None,
    include_fill_bar: bool = False,
) -> dict | None:
    """Walk one episode to its forced verdict from an ALREADY-DETERMINED fill.

    Split out from ``score_episode`` so each desk keeps the fill convention its market
    actually requires while sharing one scoring engine. The US desk fills at the next
    session's close; the CN desk fills at the T+1 OPEN (or an (H+L)/2 proxy) and must
    drop locked-limit bars, which are unfillable at any price. Those are real market
    differences. The horizon walk, the maturity gate, and the summary must not differ.

    ``close``       close series for the name (DatetimeIndex, ascending).
    ``fill_date``   the bar the position is opened on.
    ``entry``       the fill price (may differ from ``close[fill_date]``).
    ``stop_level``  absolute price; exits the first close BELOW it.
    ``early_exit``  optional bool Series on ``close``'s index; exits the first forward
                    bar where True. May only SHORTEN the hold, never extend it.
    ``bench_close`` optional benchmark for excess, measured over the SAME fill→exit
                    window so both legs share a basis.
    ``include_fill_bar``
                    whether the fill bar's OWN close counts as an exit opportunity.
                    False for a close-fill (you bought AT that close — it cannot also
                    be the exit). True for an intraday fill such as CN's T+1 open,
                    where the same session's close is a legitimate day-one exit.
                    Getting this wrong makes one desk hold a bar longer than the other
                    at nominally the same horizon, which quietly breaks comparability.
    """
    s = close.dropna()
    if s.empty or entry is None or not math.isfinite(entry) or entry <= 0:
        return None
    try:
        fill_ts = pd.Timestamp(fill_date)
    except Exception:  # noqa: BLE001
        return None
    i_fill = s.index.searchsorted(fill_ts, side="left")
    if i_fill >= len(s):
        return _PENDING.copy()

    fwd_all = s.iloc[i_fill:] if include_fill_bar else s.iloc[i_fill + 1:]
    n_avail = len(fwd_all)
    base = {
        "entry": float(entry),
        "entry_date": str(s.index[i_fill].date()),
        "n_avail": n_avail,
        "matured": n_avail >= horizon,
        "fill_pending": False,
    }
    if n_avail == 0:
        return {**base, "exit": None, "pnl": None, "excess": None, "held": 0,
                "exit_reason": None, "mfe": None, "mae": None, "mark": None}

    # Unrealised mark on whatever data exists — an in-flight row still shows a live
    # number in the popup, clearly labelled, so immature episodes stay VISIBLE rather
    # than hidden. It never enters the summary.
    mark = (float(fwd_all.iloc[-1]) / entry - 1.0) * 100.0
    if not base["matured"]:
        return {**base, "exit": None, "pnl": None, "excess": None,
                "held": n_avail, "exit_reason": None,
                "mfe": (float(fwd_all.max()) / entry - 1.0) * 100.0,
                "mae": (float(fwd_all.min()) / entry - 1.0) * 100.0,
                "mark": mark}

    # ── the forced verdict window: exactly `horizon` bars, never more ──────────
    fwd = fwd_all.iloc[:horizon]
    exit_px, held, reason = float(fwd.iloc[-1]), horizon, "horizon"
    exit_ts = fwd.index[-1]
    for n, (ts, p) in enumerate(fwd.items(), 1):
        p = float(p)
        if not math.isfinite(p):
            continue
        if stop_level is not None and p < stop_level:
            exit_px, held, reason, exit_ts = p, n, "stop", ts
            break
        if early_exit is not None and bool(early_exit.get(ts, False)):
            exit_px, held, reason, exit_ts = p, n, "target", ts
            break

    pnl = (exit_px / entry - 1.0) * 100.0
    excess = None
    if bench_close is not None:
        # Benchmark leg spans the SAME fill bar → exit bar window, by timestamp rather
        # than by offset arithmetic (the name and the benchmark can have different
        # holiday calendars, and include_fill_bar shifts the offset by one).
        b = bench_close.dropna()
        bi = b.index.searchsorted(s.index[i_fill], side="left")
        bj = b.index.searchsorted(exit_ts, side="left")
        if bi < len(b) and bj < len(b) and bj >= bi:
            b0, b1 = float(b.iloc[bi]), float(b.iloc[bj])
            if math.isfinite(b0) and b0 > 0 and math.isfinite(b1):
                excess = pnl - (b1 / b0 - 1.0) * 100.0

    return {**base, "exit": exit_px, "pnl": pnl, "excess": excess, "held": held,
            "exit_reason": reason,
            "mfe": (float(fwd.max()) / entry - 1.0) * 100.0,
            "mae": (float(fwd.min()) / entry - 1.0) * 100.0,
            "mark": mark}


def score_episode(
    close: pd.Series,
    signal_date: Any,
    horizon: int = DEFAULT_HORIZON,
    *,
    stop_level: float | None = None,
    early_exit: pd.Series | None = None,
    bench_close: pd.Series | None = None,
    fill_offset: int = 1,
) -> dict | None:
    """Score ONE episode with a NEXT-BAR-CLOSE fill (the US desk's convention).

    ``fill_offset=1`` is the only honest default: the board is computed FROM the
    signal bar's close and published that evening, so the signal bar is unbuyable.

    Return contract — three distinguishable outcomes, because conflating them corrupts
    the survivorship count (they were conflated once, and 22 episodes including DE and
    F were reported as unpriceable when their fills simply hadn't printed yet):
      * ``None``               — the name/date cannot be located. Only THIS is a
                                 genuine no-price (delisting) skip.
      * ``fill_pending=True``  — located, next bar hasn't printed. In flight.
      * ``matured=False``      — filled, fewer than ``horizon`` forward bars.
      * ``matured=True``       — scored; only these enter the summary.
    """
    s = close.dropna()
    if s.empty:
        return None
    try:
        sig = pd.Timestamp(signal_date)
    except Exception:  # noqa: BLE001 — unparseable date is a caller bug, not a crash
        return None
    i_sig = s.index.searchsorted(sig, side="left")
    if i_sig >= len(s):
        # Board date is beyond the price series entirely — the name stopped printing
        # before it ever surfaced. Genuinely unpriceable.
        return None
    i_fill = i_sig + fill_offset
    if i_fill >= len(s):
        return _PENDING.copy()
    entry = float(s.iloc[i_fill])
    if not math.isfinite(entry) or entry <= 0:
        return None
    return score_from_fill(s, s.index[i_fill], entry, horizon, stop_level=stop_level,
                           early_exit=early_exit, bench_close=bench_close)


# --------------------------------------------------------------------------- #
# confidence intervals
# --------------------------------------------------------------------------- #
def date_block_ci(
    values_by_date: Sequence[tuple[str, float]],
    stat: Callable[[np.ndarray], float],
    *,
    n_boot: int = BOOT_N,
    seed: int = BOOT_SEED,
    alpha: float = 0.05,
) -> tuple[float | None, float | None]:
    """95% CI by resampling WHOLE BOARD DAYS, not individual episodes.

    Episodes surfaced on the same night share the market's move, the desk's regime
    read, and the ranker's state — they are one bet. Resampling them independently
    (Wilson, or a naive iid bootstrap) understates the interval badly: on the US board
    2026-07-26 the effective sample behind 111 matured episodes was FIVE board dates.

    Returns (None, None) when fewer than 2 distinct dates exist — with one block there
    is nothing to resample and any interval would be a fabrication.
    """
    if not values_by_date:
        return None, None
    blocks: dict[str, list[float]] = {}
    for d, v in values_by_date:
        if v is not None and math.isfinite(v):
            blocks.setdefault(str(d), []).append(float(v))
    keys = [k for k in blocks if blocks[k]]
    if len(keys) < 2:
        return None, None
    arrs = [np.asarray(blocks[k], dtype=float) for k in keys]
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        pick = rng.integers(0, len(arrs), len(arrs))
        out[i] = stat(np.concatenate([arrs[j] for j in pick]))
    lo, hi = np.percentile(out, [alpha / 2 * 100, (1 - alpha / 2) * 100])
    return float(lo), float(hi)


def _win_pct(v: np.ndarray) -> float:
    return float((v > 0).mean() * 100.0) if len(v) else float("nan")


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def summarize(
    scored: Sequence[Mapping[str, Any]],
    *,
    metric: str = "pnl",
    n_inflight: int = 0,
    n_skipped: int = 0,
    horizon: int = DEFAULT_HORIZON,
) -> dict:
    """Aggregate matured episodes into the headline block.

    ``metric`` selects the scored quantity: ``"pnl"`` (absolute, the US headline) or
    ``"excess"`` (benchmark-relative, the CN headline — in A-shares beta dominates, so
    an absolute win rate mostly measures the index).

    A win is simply ``> 0``. There is deliberately NO dead band: the previous ±2% band
    with flats dropped from the denominator turned 86 up / 57 down / 72 flat into
    "60% win", where counting every resolved episode gives 40%. A band that removes a
    third of the sample from the denominator is the single least defensible knob on a
    track record, so this module does not have one.

    Win rate alone is never enough to act on — ``avg_win``/``avg_loss``/
    ``profit_factor``/``expectancy`` ship beside it so a 63% win rate with a 0.94
    payoff ratio cannot be mistaken for an edge.
    """
    rows = [r for r in scored if r.get("matured") and r.get(metric) is not None]
    n = len(rows)
    out: dict[str, Any] = {
        "metric": metric,
        "horizon": horizon,
        "n_matured": n,
        "n_inflight": int(n_inflight),
        "n_skipped_no_price": int(n_skipped),
        "n_board_days": len({str(r.get("board_date") or r.get("entry_date")) for r in rows}),
        "win_pct": None, "expectancy_pct": None, "median_pct": None,
        "avg_win_pct": None, "avg_loss_pct": None, "profit_factor": None,
        "ci_lo_pct": None, "ci_hi_pct": None,
        "exp_lo_pct": None, "exp_hi_pct": None,
        "median_hold": None, "capture": None,
    }
    if not n:
        return out

    v = np.array([float(r[metric]) for r in rows], dtype=float)
    wins, losses = v[v > 0], v[v <= 0]
    out["win_pct"] = round(_win_pct(v), 1)
    out["expectancy_pct"] = round(float(v.mean()), 2)
    out["median_pct"] = round(float(np.median(v)), 2)
    out["avg_win_pct"] = round(float(wins.mean()), 2) if len(wins) else None
    out["avg_loss_pct"] = round(float(losses.mean()), 2) if len(losses) else None
    if len(losses) and losses.sum() < 0:
        out["profit_factor"] = round(float(wins.sum() / abs(losses.sum())), 2)
    elif len(wins):
        out["profit_factor"] = None            # no losers yet — a ratio would be a lie

    pairs = [(str(r.get("board_date") or r.get("entry_date")), float(r[metric])) for r in rows]
    lo, hi = date_block_ci(pairs, _win_pct)
    out["ci_lo_pct"] = round(lo, 1) if lo is not None else None
    out["ci_hi_pct"] = round(hi, 1) if hi is not None else None
    elo, ehi = date_block_ci(pairs, lambda a: float(a.mean()))
    out["exp_lo_pct"] = round(elo, 2) if elo is not None else None
    out["exp_hi_pct"] = round(ehi, 2) if ehi is not None else None

    holds = [r["held"] for r in rows if r.get("held") is not None]
    if holds:
        out["median_hold"] = int(np.median(holds))
    caps = [r["pnl"] / r["mfe"] for r in rows
            if r.get("mfe") and r.get("pnl") is not None and abs(r["mfe"]) > 1e-9]
    if caps:
        out["capture"] = round(float(np.median(caps)), 2)
    mfes = [r["mfe"] for r in rows if r.get("mfe") is not None]
    maes = [r["mae"] for r in rows if r.get("mae") is not None]
    if mfes:
        out["mfe_median_pct"] = round(float(np.median(mfes)), 2)
    if maes:
        out["mae_median_pct"] = round(float(np.median(maes)), 2)
        out["mae_p10_pct"] = round(float(np.percentile(maes, 10)), 2)
    return out


def publish_state(summary: Mapping[str, Any], *, min_matured: int = 20,
                  min_board_days: int = 3) -> str:
    """`scored` once the sample can carry a headline, else `accruing`.

    Both gates matter and they are different questions: ``n_matured`` is how many
    trades resolved, ``n_board_days`` is how many INDEPENDENT bets that represents.
    111 episodes across 5 board dates is the second number's problem, not the first's.
    """
    if summary.get("win_pct") is None:
        return "accruing"
    if int(summary.get("n_matured") or 0) < min_matured:
        return "accruing"
    if int(summary.get("n_board_days") or 0) < min_board_days:
        return "accruing"
    return "scored"
