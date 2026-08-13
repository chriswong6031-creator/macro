"""engine.prophet_plan_grades — benchmark-relative SIDECAR for the Prophet plan ledger.

WHY A SIDECAR AND NOT A COLUMN
------------------------------
``data/prophet/ledger.jsonl`` is an IMMUTABLE forward record: a row is a dated,
point-in-time claim, and the whole evidentiary value of a prediction ledger is that
nobody — including us — ever went back and edited it.  So this module does NOT add
fields to existing rows and does NOT rewrite the ledger.  It follows the house's own
Universal Scoreboard split (``engine/qledger.py``: ``claims.jsonl`` beside
``grades.jsonl``) and writes a separate append-only store,

    data/prophet/plan_grades.jsonl

joined to the ledger by ``id``, one row per ``(id, horizon)``.

THE DEFECT THIS CLOSES
----------------------
``stock_result_pct`` on the ledger is a RAW return.  A mean of +0.51% over
2026-03→07 says nothing about whether Prophet beat SPY or the name's sector — the
board grader (``scripts/grade_us_board.py``) has always graded against both, and the
surface carrying the public performance narrative was the one without a benchmark
(``research/MASTERMIND_PROPHET_EVAL_SPEC.md`` §7).

ONE PRICE BASIS OR NO ROW (the dangerous trap)
----------------------------------------------
The benchmark legs (SPY, the SPDR sector ETFs) are dividend-ADJUSTED.  Prophet's own
plan-management price loader falls through to the RAW breadth close caches for names
absent from the adjusted stores, so ``raw_name_return − adjusted_bench_return`` is
wrong across any split or dividend inside the window.  Every leg here therefore
resolves through :func:`engine.price_ladder.resolve_close` with
``allow_unadjusted=False`` — the ladder's own refusal switch.  A name with no
adjusted series ANYWHERE is REFUSED (a row with null metrics and a
``refusal_reason``), never priced off the raw cache and differenced against an
adjusted benchmark.  ``price_source`` and ``price_basis`` are stamped on every row so
an audit reads the basis off the row instead of trusting this docstring.

DIRECTION SIGNING (the silent-corruption trap)
----------------------------------------------
``excess_*`` and the excursion columns are SIGNED BY THE PLAN'S ``direction`` AT
WRITE TIME: a BEAR plan whose name falls 5% while SPY rises 2% has excess **+7pp**,
not −7pp.  ``engine/qledger.py`` stores a raw unsigned ``excess`` and that is exactly
why ``engine/qledger_validity.py`` had to declare V1
``SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS`` — pooling it across mixed directions
yields a large-t, meaningless number.  This store does not reproduce that defect.
The RAW tape legs (``name_ret_pct`` / ``bench_ret_pct`` / ``sector_ret_pct``) stay
UNSIGNED so a reader can always reconstruct the tape.

EXCURSIONS ARE CLOSE-ONLY, AND SAY SO
-------------------------------------
Every excursion column carries ``close`` in its NAME.  These are computed on the
close path only, so they UNDER-state true intraday MFE and MAE — an intraday spike
through the invalidation level that closed back inside is invisible here.  Do not
present ``mae_close_pct`` as a drawdown.  Same honesty discipline as
``grade_us_board._excess_close_path_mae``.

NIGHTLY IS THE SOLE ADVANCER (ledger law G0.2)
----------------------------------------------
:func:`append_plan_grades` gates on ``ledger_lane.nightly_advance_enabled()`` as its
FIRST statement, so an intraday or render lane returns 0 without opening a file.
``scripts/prophet_live_evaluator.py`` runs 80+ times a session and writes nothing
under ``data/``; that stays true — this module is imported only by
``scripts/build_prophet.py``, the nightly plan-ledger closer.

IDEMPOTENCE, AND THE ONE THING THAT MAY BE REWRITTEN
----------------------------------------------------
A ``(id, horizon)`` already carrying a PRICED grade is FROZEN — a re-run appends
nothing.  The single exception is a REFUSAL row (``price_basis`` null): a plan that
could not be priced tonight may be priced later (the adjusted store gains the name),
and a refusal is a statement about our data, not a graded claim about the market.  So
a refusal may be upgraded to a priced row; a priced row is never touched.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine import ledger_lane
from engine.grading import fill_index, load_dead_prices, resolve_series
from engine.price_ladder import is_adjusted, resolve_close

log = logging.getLogger(__name__)

SCHEMA = "prophet.plan_grades/v1"

#: Benchmark leg — the same one grade_us_board.py and the US full-population forward
#: grader mark against.  (Named without its module token on purpose: that store's
#: ZERO-AUTHORITY fence is a raw substring sweep over engine/ and scripts/, and a prose
#: mention here would read as a consumer.  This module imports nothing from it.)
BENCH = "SPY"

#: GICS sector -> SPDR sector ETF.  Mirrors scripts/grade_us_board.py's superset
#: (which itself mirrors engine/ai_desk.py plus the board's non-canonical spellings)
#: so the plan surface and the board surface can never disagree about a name's sector leg.
GICS_ETF = {
    "Energy": "XLE", "Information Technology": "XLK", "Technology": "XLK",
    "Financials": "XLF", "Health Care": "XLV", "Industrials": "XLI",
    "Consumer Discretionary": "XLY", "Consumer Staples": "XLP",
    "Utilities": "XLU", "Materials": "XLB", "Real Estate": "XLRE",
    "Communication Services": "XLC", "Communications": "XLC",
}

#: Fixed session horizons, per MASTERMIND_PROPHET_EVAL_SPEC.md §3, PLUS the plan's own
#: realised window.  "realized" is the row that answers "did this plan beat SPY", because
#: it spans exactly the window the ledger's own stock_result_pct spans.
SESSION_HORIZONS: tuple[int, ...] = (1, 3, 5, 10, 20)
REALIZED = "realized"

GRADE_KEY = ("id", "horizon")

#: Written as the first bytes of a fresh sidecar.  Documents every field AND the
#: direction-signing convention, matching data/prophet/ledger.jsonl's own '#' header.
SIDECAR_HEADER = """\
# prophet plan-grade SIDECAR — benchmark-relative grades for data/prophet/ledger.jsonl
# schema prophet.plan_grades/v1 · producer engine/prophet_plan_grades.py
# JOINED TO THE LEDGER BY `id`.  The ledger is an IMMUTABLE forward record and is never
# rewritten; this file carries everything the ledger's raw stock_result_pct cannot say.
# One row per (id, horizon).  A (id, horizon) with a priced grade is FROZEN forever; a
# REFUSAL row (price_basis null) may later be UPGRADED to a priced row and nothing else.
#
# Fields:
#   schema, id, asset, direction, direction_sign (+1 BULL/LONG, -1 BEAR/SHORT),
#   signal_date, close_date (copied from the ledger row, never recomputed),
#   horizon        — 1|3|5|10|20 forward SESSIONS, or "realized" (fill -> close_date,
#                    the same window the ledger's own stock_result_pct spans),
#   entry_date, exit_date, sessions_held (bars from fill to exit, inclusive of exit),
#   name_ret_pct, bench_ret_pct, sector_ret_pct        <- RAW TAPE, UNSIGNED
#   ledger_stock_result_pct — the ledger row's own raw number, copied verbatim on the
#                    "realized" row only, so the two can be compared without a join
#   ...
#   excess_vs_bench_pct, excess_vs_sector_pct          <- DIRECTION-SIGNED
#   mfe_close_pct, mae_close_pct                       <- DIRECTION-SIGNED, CLOSE-ONLY
#   mfe_close_excess_vs_bench_pct,
#   mae_close_excess_vs_bench_pct                      <- DIRECTION-SIGNED, CLOSE-ONLY
#   bench_symbol, sector_symbol, price_source, price_basis, refusal_reason, graded_at
#
# name_ret_pct IS NOT ledger.stock_result_pct, AND MUST NOT BE READ AS ONE.  The ledger's
#   number is measured from the PLAN'S ENTRY PRICE (a zone/limit level) on the plan's own
#   management clock.  name_ret_pct here is the TAPE from a NEXT-BAR FILL after
#   signal_date (engine.grading.fill_index, the same convention grade_us_board and
#   the US full-population forward grader use) to the bar at-or-before close_date.  Both
#   legs of every excess
#   are measured over EXACTLY those bars, which is the only construction that makes the
#   subtraction meaningful: differencing an entry-price-anchored name return against a
#   close-anchored benchmark would be a second basis mismatch dressed as an alpha.  The
#   ledger's own figure is carried as ledger_stock_result_pct so the gap is visible.
#
# DIRECTION-SIGNING CONVENTION (read this before pooling anything):
#   excess_vs_bench_pct  = direction_sign * (name_ret_pct - bench_ret_pct)
#   excess_vs_sector_pct = direction_sign * (name_ret_pct - sector_ret_pct)
#   direction_sign = +1 for BULL/LONG/BUY, -1 for BEAR/SHORT/SELL.
#   A BEAR plan whose name falls 5% while SPY rises 2% therefore reads +7.0, NOT -7.0.
#   POSITIVE ALWAYS MEANS "the plan was right relative to the benchmark", so the column
#   pools across directions.  engine/qledger.py stores an UNSIGNED excess and that is
#   precisely the defect engine/qledger_validity.py had to declare (V1,
#   SIGNED_EXCESS_POOLED_ACROSS_DIRECTIONS).  name_ret/bench_ret/sector_ret stay UNSIGNED
#   so the tape is always reconstructible from the row.
#
# EXCURSIONS ARE CLOSE-ONLY — NOT INTRADAY.  mfe_close_pct / mae_close_pct and their
#   _excess_vs_bench_ siblings are computed on the CLOSE path over (fill, exit] only, so
#   they UNDER-state true intraday MFE/MAE.  An intraday breach of the invalidation level
#   that closed back inside is INVISIBLE here.  mae_close_pct is NOT a drawdown figure.
#   mfe_close_* is >= 0 and mae_close_* is <= 0 by construction (the fill bar itself is
#   in the window as the 0 reference).
#
# ONE PRICE BASIS OR NO ROW.  Every leg (name, SPY, sector ETF) resolves through
#   engine.price_ladder.resolve_close(..., allow_unadjusted=False) — adjusted rungs only.
#   A name with no ADJUSTED series anywhere is REFUSED: one row, horizon="realized", all
#   metrics null, refusal_reason set, price_basis null.  It is NEVER priced off the raw
#   breadth cache and differenced against an adjusted benchmark.  price_basis is
#   "adjusted" on every priced row; a null price_basis means REFUSED, never zero.
#   Coverage is a property of the local price store: price_source names the exact rung.
#
# NIGHTLY IS THE SOLE ADVANCER (ledger law G0.2): append_plan_grades() gates on
#   ledger_lane.nightly_advance_enabled() as its FIRST statement.  Intraday lanes
#   (scripts/prophet_live_evaluator.py) write nothing here, as they write nothing under
#   data/ at all.
"""


# --------------------------------------------------------------------------- #
# direction
# --------------------------------------------------------------------------- #

_LONG = {"BULL", "LONG", "BUY", "UP"}
_SHORT = {"BEAR", "SHORT", "SELL", "DOWN"}


def direction_sign(direction: Any) -> int | None:
    """+1 for a long plan, -1 for a short plan, None for anything unrecognised.

    None is a REFUSAL, not a 0: an unsigned excess is exactly the number this store
    exists to not produce, so a plan whose direction we cannot read is named rather
    than silently graded long.
    """
    token = str(direction or "").strip().upper()
    if token in _LONG:
        return 1
    if token in _SHORT:
        return -1
    return None


# --------------------------------------------------------------------------- #
# store I/O
# --------------------------------------------------------------------------- #

def default_ledger_path(root: Any = None) -> Path:
    base = _data_root(root)
    return base / "prophet" / "ledger.jsonl"


def default_sidecar_path(root: Any = None) -> Path:
    base = _data_root(root)
    return base / "prophet" / "plan_grades.jsonl"


def _data_root(root: Any = None) -> Path:
    """The ``data/`` directory.  ``root`` is a REPO root (the house forward-grader idiom),
    so tests point it at a tmp_path and get ``<tmp>/data/...``."""
    if root is not None:
        return Path(root) / "data"
    from lib import config  # noqa: PLC0415 — lazy: importing this module must not read config
    return Path(config.data_dir())


def read_jsonl(path: Any) -> list[dict]:
    """Rows from a '#'-headed jsonl store; missing file -> []."""
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            rows.append(json.loads(stripped))
        except json.JSONDecodeError:
            log.warning("prophet_plan_grades: skipping unparseable line in %s", p)
    return rows


def graded_keys(path: Any) -> set[tuple[str, str]]:
    """``(id, horizon)`` already carrying a PRICED grade.  Refusals are deliberately
    NOT in this set — a refusal is a statement about our price store, not a graded
    claim, so it stays re-gradable."""
    return {
        (str(r.get("id")), str(r.get("horizon")))
        for r in read_jsonl(path)
        if r.get("price_basis")
    }


def append_plan_grades(rows: list[dict], path: Any = None) -> int:
    """Append sidecar rows.  Returns the number written, or 0.

    NIGHTLY IS THE SOLE ADVANCER — the lane gate is the FIRST statement, so an
    intraday or render lane returns 0 without opening a file (ledger law G0.2).

    Refusal rows that this call re-grades as PRICED are superseded in place: the file
    is rewritten with the stale refusal dropped.  Nothing else is ever rewritten.
    """
    if not ledger_lane.nightly_advance_enabled():
        log.info("prophet_plan_grades append gated — not the US nightly lane")
        return 0
    if not rows:
        return 0
    target = Path(path) if path is not None else default_sidecar_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    incoming = {(str(r.get("id")), str(r.get("horizon"))): r for r in rows}
    prior = read_jsonl(target)
    kept = [
        r for r in prior
        if r.get("price_basis")
        or (str(r.get("id")), str(r.get("horizon"))) not in incoming
    ]
    # never re-write a frozen priced row from an incoming duplicate
    frozen = {(str(r.get("id")), str(r.get("horizon"))) for r in kept if r.get("price_basis")}
    fresh = [r for key, r in incoming.items() if key not in frozen]
    if not fresh:
        return 0

    if len(kept) != len(prior) or not target.exists():
        body = SIDECAR_HEADER + "".join(
            json.dumps(r, allow_nan=False, default=str) + "\n" for r in [*kept, *fresh]
        )
        target.write_text(body, encoding="utf-8")
    else:
        if not target.read_text(encoding="utf-8").startswith("#"):
            target.write_text(SIDECAR_HEADER, encoding="utf-8")
        with target.open("a", encoding="utf-8") as fh:
            for r in fresh:
                fh.write(json.dumps(r, allow_nan=False, default=str) + "\n")
    return len(fresh)


# --------------------------------------------------------------------------- #
# sector lookup
# --------------------------------------------------------------------------- #

def load_sectors(root: Any = None) -> dict[str, str]:
    """``{ticker -> GICS sector}`` from ``data/breadth/ticker_sectors.parquet``.

    Empty dict when absent — a missing map costs the SECTOR leg and nothing else; the
    SPY leg is computed independently, exactly as grade_us_board.py does it.
    """
    path = _data_root(root) / "breadth" / "ticker_sectors.parquet"
    if not path.exists():
        return {}
    try:
        frame = pd.read_parquet(path)
        return {
            str(t): str(s)
            for t, s in zip(frame["ticker"], frame["sector"])
            if s is not None and str(s) not in ("", "None", "nan")
        }
    except Exception as exc:  # noqa: BLE001 — additive, never fatal
        log.warning("prophet_plan_grades: sector map read failed: %s", exc)
        return {}


# --------------------------------------------------------------------------- #
# price legs
# --------------------------------------------------------------------------- #

class _Leg:
    """One resolved, adjusted-basis close series plus its disclosed provenance."""

    __slots__ = ("series", "source", "reason")

    def __init__(self, series, source, reason):
        self.series = series
        self.source = source
        self.reason = reason

    @property
    def ok(self) -> bool:
        return self.series is not None and not self.series.empty


def resolve_adjusted_leg(
    ticker: str,
    *,
    data_dir: str | None = None,
    dead_prices: dict[str, pd.Series] | None = None,
    min_last: Any = None,
) -> _Leg:
    """One leg's close series on a strictly ADJUSTED basis, or a refusal with a reason.

    ``allow_unadjusted=False`` is the ladder's own refusal switch: it stops after the
    adjusted rungs rather than falling through to the raw close cache.  A resolved
    series is then extended with the 8-K dead-name terminal tail so a name that
    delists mid-window grades its loss instead of vanishing (survivorship).  A name
    present ONLY in the dead store is still refused — its basis is unknowable, and a
    row whose basis cannot be named is exactly what this function exists to prevent.

    ``min_last`` is LOAD-BEARING, not an optimisation.  The top adjusted rung
    (``data/baskets/ohlcv``) runs STALE — measured 2026-08-12 it stopped weeks short of
    several 2026-07 plan windows — and without ``min_last`` the ladder returns that
    stale series and every plan closing after it refuses for "no fillable bar", which
    reads as a coverage hole when it is really a rung-choice bug.  With ``min_last`` a
    rung that ends before the window is treated as a MISS and the walk continues to
    ``yahoo``, which carries the window on the SAME adjusted basis.
    """
    res = resolve_close(ticker, allow_unadjusted=False, data_dir=data_dir,
                        min_last=min_last)
    if not res.ok:
        return _Leg(None, None, res.reason or f"{ticker}: no adjusted price series")
    if is_adjusted(res.price_source) is not True:
        return _Leg(None, None,
                    f"{ticker}: ladder returned non-adjusted source {res.price_source!r}")
    live = res.series.dropna()
    extended = resolve_series(ticker, live, dead_prices=dead_prices)
    series = live if extended is None else extended
    source = res.price_source
    if extended is not None and len(extended) > len(live):
        source = f"{res.price_source}+edgar_dead_tail"
    return _Leg(series.sort_index(), source, None)


# --------------------------------------------------------------------------- #
# window arithmetic
# --------------------------------------------------------------------------- #

def _exit_pos_for_close_date(index: pd.DatetimeIndex, close_date, fill: int) -> int | None:
    """iloc of the last bar at-or-before ``close_date``; None when it is not strictly
    after the fill (a plan that closed before it could be filled is not gradable)."""
    try:
        dt = pd.Timestamp(close_date)
    except Exception:  # noqa: BLE001
        return None
    pos = int(np.searchsorted(index.values, np.datetime64(dt), side="right")) - 1
    if pos <= fill or pos >= len(index):
        return None
    return pos


def _pct(series: pd.Series, fill: int, exit_pos: int) -> float | None:
    p0 = float(series.iloc[fill])
    p1 = float(series.iloc[exit_pos])
    if not (np.isfinite(p0) and np.isfinite(p1)) or p0 <= 0:
        return None
    return (p1 / p0 - 1.0) * 100.0


def _close_path_excursions(
    name: pd.Series,
    bench: pd.Series | None,
    fill: int,
    exit_pos: int,
    sign: int,
) -> tuple[float | None, float | None, float | None, float | None]:
    """Direction-signed, CLOSE-ONLY excursions over ``(fill, exit_pos]``.

    Returns ``(mfe_close, mae_close, mfe_close_excess, mae_close_excess)`` in percent.
    The name-only pair is the signed cumulative close return; the excess pair is the
    signed close return minus the benchmark's over the same bars — the same bar-by-bar
    construction as ``grade_us_board._excess_close_path_mae``, with MFE added.

    These are CLOSE-ONLY and therefore UNDER-state true intraday excursions.
    """
    n0 = float(name.iloc[fill])
    if not np.isfinite(n0) or n0 <= 0:
        return None, None, None, None
    b0 = None
    if bench is not None:
        candidate = float(bench.iloc[fill])
        if np.isfinite(candidate) and candidate > 0:
            b0 = candidate

    best = worst = 0.0
    best_x = worst_x = 0.0 if b0 is not None else None
    for j in range(fill + 1, exit_pos + 1):
        nj = float(name.iloc[j])
        if not np.isfinite(nj):
            continue
        ret = sign * (nj / n0 - 1.0)
        best = max(best, ret)
        worst = min(worst, ret)
        if b0 is not None:
            bj = float(bench.iloc[j])
            if not np.isfinite(bj):
                continue
            exc = sign * ((nj / n0 - 1.0) - (bj / b0 - 1.0))
            best_x = max(best_x, exc)
            worst_x = min(worst_x, exc)
    return (
        best * 100.0,
        worst * 100.0,
        None if best_x is None else best_x * 100.0,
        None if worst_x is None else worst_x * 100.0,
    )


# --------------------------------------------------------------------------- #
# grading
# --------------------------------------------------------------------------- #

def _refusal_row(ledger_row: dict, reason: str, graded_at: str, sign: int | None) -> dict:
    """The row a plan we could not price still gets.  TRAP 5: 'could not price this
    plan' must APPEAR in the output — a missing row is indistinguishable from a plan
    that never existed, which is how survivorship enters a record."""
    return {
        "schema": SCHEMA,
        "id": ledger_row.get("id"),
        "asset": ledger_row.get("asset"),
        "direction": ledger_row.get("direction"),
        "direction_sign": sign,
        "signal_date": ledger_row.get("signal_date"),
        "close_date": ledger_row.get("close_date"),
        "horizon": REALIZED,
        "entry_date": None,
        "exit_date": None,
        "sessions_held": None,
        "ledger_stock_result_pct": ledger_row.get("stock_result_pct"),
        "name_ret_pct": None,
        "bench_ret_pct": None,
        "sector_ret_pct": None,
        "excess_vs_bench_pct": None,
        "excess_vs_sector_pct": None,
        "mfe_close_pct": None,
        "mae_close_pct": None,
        "mfe_close_excess_vs_bench_pct": None,
        "mae_close_excess_vs_bench_pct": None,
        "bench_symbol": BENCH,
        "sector_symbol": None,
        "price_source": None,
        "price_basis": None,
        "refusal_reason": reason,
        "graded_at": graded_at,
    }


def grade_plan(
    ledger_row: dict,
    *,
    data_dir: str | None = None,
    dead_prices: dict[str, pd.Series] | None = None,
    sectors: dict[str, str] | None = None,
    bench_leg: _Leg | None = None,
    sector_legs: dict[str, _Leg] | None = None,
    graded_at: str | None = None,
    horizons: tuple[int, ...] = SESSION_HORIZONS,
) -> list[dict]:
    """Grade one closed ledger row into sidecar rows — one per session horizon plus
    ``realized`` — or a single refusal row naming why it could not be priced."""
    stamp = graded_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    asset = str(ledger_row.get("asset") or "")
    sign = direction_sign(ledger_row.get("direction"))

    if not asset:
        return [_refusal_row(ledger_row, "ledger row carries no asset", stamp, sign)]
    if sign is None:
        return [_refusal_row(
            ledger_row,
            f"unrecognised direction {ledger_row.get('direction')!r} — excess cannot be signed",
            stamp, sign)]
    if not ledger_row.get("signal_date") or not ledger_row.get("close_date"):
        return [_refusal_row(ledger_row, "ledger row has no signal_date/close_date window",
                             stamp, sign)]

    # min_last = the plan's own close_date: a rung that stops before the plan closed is
    # a MISS, not a winner (see resolve_adjusted_leg).
    name = resolve_adjusted_leg(asset, data_dir=data_dir, dead_prices=dead_prices,
                                min_last=ledger_row.get("close_date"))
    if not name.ok:
        return [_refusal_row(ledger_row, f"name leg refused — {name.reason}", stamp, sign)]

    bench = bench_leg if bench_leg is not None else resolve_adjusted_leg(
        BENCH, data_dir=data_dir, dead_prices=dead_prices,
        min_last=ledger_row.get("close_date"))
    if not bench.ok:
        return [_refusal_row(ledger_row, f"benchmark leg refused — {bench.reason}",
                             stamp, sign)]

    sector_name = (sectors or {}).get(asset)
    sector_symbol = GICS_ETF.get(sector_name or "")
    sector_reason: str | None = None
    sector: _Leg | None = None
    if sector_symbol is None:
        sector_reason = (
            f"no sector ETF for {asset}: sector={sector_name!r} not in GICS_ETF")
    else:
        sector = (sector_legs or {}).get(sector_symbol)
        if sector is None:
            sector = resolve_adjusted_leg(sector_symbol, data_dir=data_dir,
                                          dead_prices=dead_prices,
                                          min_last=ledger_row.get("close_date"))
        if not sector.ok:
            sector_reason = f"sector leg {sector_symbol} refused — {sector.reason}"
            sector = None

    nser = name.series
    fill = fill_index(nser, ledger_row["signal_date"])
    if fill is None:
        return [_refusal_row(
            ledger_row,
            f"no fillable bar after signal_date {ledger_row['signal_date']} in the "
            f"adjusted series ({name.source})", stamp, sign)]

    bser = bench.series.reindex(nser.index).ffill()
    sser = sector.series.reindex(nser.index).ffill() if sector is not None else None

    realized_exit = _exit_pos_for_close_date(nser.index, ledger_row["close_date"], fill)
    if realized_exit is None:
        return [_refusal_row(
            ledger_row,
            f"close_date {ledger_row['close_date']} does not resolve to a bar after the "
            f"fill in the adjusted series ({name.source})", stamp, sign)]

    windows: list[tuple[str | int, int]] = [(REALIZED, realized_exit)]
    for h in horizons:
        pos = fill + int(h)
        if pos < len(nser):
            windows.append((int(h), pos))

    rows: list[dict] = []
    for horizon, exit_pos in windows:
        name_ret = _pct(nser, fill, exit_pos)
        bench_ret = _pct(bser, fill, exit_pos)
        sector_ret = _pct(sser, fill, exit_pos) if sser is not None else None
        mfe, mae, mfe_x, mae_x = _close_path_excursions(nser, bser, fill, exit_pos, sign)
        rows.append({
            "schema": SCHEMA,
            "id": ledger_row.get("id"),
            "asset": asset,
            "direction": ledger_row.get("direction"),
            "direction_sign": sign,
            "signal_date": ledger_row.get("signal_date"),
            "close_date": ledger_row.get("close_date"),
            "horizon": horizon,
            "entry_date": str(nser.index[fill].date()),
            "exit_date": str(nser.index[exit_pos].date()),
            "sessions_held": int(exit_pos - fill),
            # the ledger's own entry-price-anchored figure, verbatim, on the realized
            # row only — a different construction from name_ret_pct by design (header).
            "ledger_stock_result_pct": (
                ledger_row.get("stock_result_pct") if horizon == REALIZED else None),
            "name_ret_pct": _round(name_ret),
            "bench_ret_pct": _round(bench_ret),
            "sector_ret_pct": _round(sector_ret),
            # DIRECTION-SIGNED — see the sidecar header.
            "excess_vs_bench_pct": _round(
                None if (name_ret is None or bench_ret is None)
                else sign * (name_ret - bench_ret)),
            "excess_vs_sector_pct": _round(
                None if (name_ret is None or sector_ret is None)
                else sign * (name_ret - sector_ret)),
            "mfe_close_pct": _round(mfe),
            "mae_close_pct": _round(mae),
            "mfe_close_excess_vs_bench_pct": _round(mfe_x),
            "mae_close_excess_vs_bench_pct": _round(mae_x),
            "bench_symbol": BENCH,
            "sector_symbol": sector_symbol if sector is not None else None,
            "price_source": name.source,
            "price_basis": "adjusted",
            "refusal_reason": sector_reason,
            "graded_at": stamp,
        })
    return rows


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def grade_ledger(
    ledger_rows: list[dict],
    *,
    data_dir: str | None = None,
    root: Any = None,
    already: set[tuple[str, str]] | None = None,
    graded_at: str | None = None,
) -> list[dict]:
    """Grade every ledger row whose ``(id, horizon)`` is not already PRICED.

    Benchmark and sector legs are resolved once and shared across plans, so a 28-row
    backfill reads SPY one time rather than 28.
    """
    stamp = graded_at or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    dead = load_dead_prices()
    sectors = load_sectors(root)
    # Shared legs are resolved to the LATEST close_date in the batch, so a rung stale
    # for the newest plan is skipped for every plan (see resolve_adjusted_leg).
    horizon_end = max(
        (str(r.get("close_date")) for r in ledger_rows if r.get("close_date")),
        default=None)
    bench_leg = resolve_adjusted_leg(BENCH, data_dir=data_dir, dead_prices=dead,
                                     min_last=horizon_end)
    sector_legs: dict[str, _Leg] = {}
    for symbol in sorted(set(GICS_ETF.values())):
        sector_legs[symbol] = resolve_adjusted_leg(symbol, data_dir=data_dir,
                                                   dead_prices=dead,
                                                   min_last=horizon_end)

    seen = already or set()
    out: list[dict] = []
    for row in ledger_rows:
        rid = str(row.get("id") or "")
        if not rid:
            continue
        graded = grade_plan(
            row, data_dir=data_dir, dead_prices=dead, sectors=sectors,
            bench_leg=bench_leg, sector_legs=sector_legs, graded_at=stamp)
        out.extend(r for r in graded if (rid, str(r["horizon"])) not in seen)
    return out


def advance_plan_grades(
    root: Any = None,
    data_dir: str | None = None,
    ledger_path: Any = None,
    sidecar_path: Any = None,
) -> int:
    """Nightly hook: grade every not-yet-priced closed plan and append the sidecar.

    Returns the number of rows written (0 outside the nightly lane).  Never raises —
    a benchmark sidecar must never be able to fail the Prophet build.

    ``ledger_path``/``sidecar_path`` are handed in OUTRIGHT by the nightly caller, the
    same fail-CLOSED discipline ``build_prophet``'s legacy-shadow store uses: every
    ``bp.main()`` harness already redirects ``LEDGER_DIR``, and ``tests/conftest.py``
    arms ``COLLECT_LANE=nightly`` for every test, so a writer that resolved its own
    data dir would write the repo's REAL forward store from any such test.
    """
    try:
        ledger = Path(ledger_path) if ledger_path is not None else default_ledger_path(root)
        sidecar = (Path(sidecar_path) if sidecar_path is not None
                   else default_sidecar_path(root))
        ledger_rows = read_jsonl(ledger)
        already = graded_keys(sidecar)
        if not ledger_rows:
            return 0
        rows = grade_ledger(
            ledger_rows, data_dir=data_dir, root=root, already=already)
        written = append_plan_grades(rows, path=sidecar)
        refused = sorted({
            f"{r['id']} ({r['refusal_reason']})"
            for r in rows if not r.get("price_basis")
        })
        if refused:
            # TRAP 5 — an unpriceable plan is NAMED in the run's own output, never
            # silently absent.  Bare print, flush: a logger prefix would make GitHub
            # drop the annotation silently.
            print(
                "::warning title=prophet-plan-grades-unpriced::"
                f"{len(refused)} Prophet plan(s) could not be priced on a single "
                f"adjusted basis: {'; '.join(refused)}",
                flush=True,
            )
        log.info("prophet_plan_grades: wrote %d sidecar rows (%d plans refused)",
                 written, len(refused))
        return written
    except Exception as exc:  # noqa: BLE001 — additive, never fatal to the nightly
        log.warning("prophet_plan_grades: advance failed: %s", exc)
        return 0


def main(argv: list[str] | None = None) -> int:
    """Backfill/CLI entry point: ``python3 -m engine.prophet_plan_grades``.

    Honours the same nightly gate as the nightly hook — set ``COLLECT_LANE=nightly``
    to run a deliberate backfill.
    """
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=None,
                        help="repo root whose data/ holds the ledger + sidecar")
    parser.add_argument("--data-dir", default=None,
                        help="price store to resolve legs from (defaults to the repo's)")
    parser.add_argument("--sidecar-path", default=None,
                        help="explicit sidecar path (defaults to <root>/data/prophet/)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    written = advance_plan_grades(root=args.root, data_dir=args.data_dir,
                                  sidecar_path=args.sidecar_path)
    print(f"prophet_plan_grades: {written} row(s) written")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
