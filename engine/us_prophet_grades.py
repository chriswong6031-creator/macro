"""Full-population forward grader over the US Context Vector store (PROPHET US §W7).

Grades **every stamped candidate row** — the whole analyzed universe, ~1,579 names a
night, not the ~12 that become plans — at **H=10 and H=21 sessions, excess vs SPY**, and
writes one grade row per (candidate, horizon) to
``data/us_prophet_rank/grades/YYYY-MM.parquet``.

WHY (operator order 2026-08-05)
-------------------------------
"That rule where we only introduce 6-12 picks to the board … isn't that an awful rule cuz
then we have less data to train on"; "we should be remembering the score that we give
picks, so that it can be logged into the ledger and so that we can later assess how robust
and correct our scoring system is."  The remembering half already accrues: the Context
Vector store (:mod:`engine.us_context_vector`, #4540) stamps every name nightly WITH the
``us_prophet_v1`` priority-score legs itemized per row.  This module is the OUTCOME half —
it turns that stamp log into a graded record, so the score can be measured against what the
tape actually did instead of asserted.

RULER — REUSED, NOT FORKED (one-grader law)
-------------------------------------------
Every return comes from :func:`engine.grading.forward_metrics`, the same function
``scripts/grade_us_board.py`` and ``scripts/grade_prophet_doors.py`` use:

* **next-bar fill** — entry is the close of the bar STRICTLY AFTER the stamp bar, so a
  score computed on tonight's close is filled at tomorrow's close.  No same-bar entry.
* **positional horizons** — H is an integer offset on the price index, and those parquets
  hold trading days only, so H=10 is ten SESSIONS, never ten calendar days.
* **excess vs SPY** = ``fwd_ret_H(name) - fwd_ret_H(SPY)``, with SPY reindexed onto the
  name's own calendar and forward-filled before it is graded.

:func:`grade_row` is a deliberate SIBLING of ``grade_prophet_doors.grade_flag`` rather than
an import of it (an engine module importing a ``scripts`` module would invert the
dependency direction).  ``tests/test_us_prophet_grades.py`` pins the two against each other
on the same inputs, so a drift in either fails the suite instead of shipping two sets of
numbers under one name — the same anti-fork discipline the US miss-audit's own caching
series reader carries against ``name_score_grader``.  (That audit is named by role rather
than by module here: its suite greps every other module for its literal name to pin its
own zero-authority fence, so a docstring mention would read as a dependency.)

POLICY-FREE
-----------
Fixed-horizon marks ONLY.  No stops, no exits, no hold rules, no sizing.  The candidate row
is being measured as an ORIGINATION+RANKING observation; layering an exit policy on top
would grade the policy instead.

ONE-GRADER LAW / IDEMPOTENCE
----------------------------
A graded ``(stamp_date, ticker, board_definition, horizon)`` is FROZEN and never regraded.
A re-run on the same night adds nothing.  Maturity is checked against the price panel
BEFORE any row is graded, so an unmatured horizon is simply absent this run and graded on a
later night — never marked short, never scored 0.

STORAGE — monthly parts, keyed by the GRADING RUN's month
---------------------------------------------------------
``grades/YYYY-MM.parquet`` where ``YYYY-MM`` is the month of ``graded_asof`` (the price
panel's own last bar), NOT of ``stamp_date``.  Grading is a monotone forward process, so
partitioning by run month means a nightly opens exactly ONE part and every earlier part is
byte-identical forever.  Partitioning by stamp month instead would rewrite the previous
month's part every night for ~3 weeks while its rows matured — roughly doubling the git
blob churn the candidates store's monthly layout exists to avoid.  Each row still carries
``stamp_date`` and ``mark_date``, so a study joins by stamp month regardless of which part
the row physically lives in.  Read through :func:`load_grades`; nothing outside this module
should glob the parts.

NIGHTLY IS THE SOLE ADVANCER.  :func:`append_grades` gates on
``ledger_lane.nightly_advance_enabled()`` as its FIRST statement — intraday and render
lanes discard ``data/`` writes anyway, so they must never advance a forward ledger.

ZERO AUTHORITY.  Outcomes here confer no rank, gate, size, board or plan rights on anything.
This is the measurement half of a display/telemetry program; every promotion path runs
through the masterplan's own preregistered gates.  Nothing may read this store for scoring.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from engine import ledger_lane
from engine import us_context_vector as ucv
from engine.grading import forward_metrics
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "us.prophet_grades/v1"

#: Same store root as the candidates it grades (``data/us_prophet_rank/``).
STORE_DIR = ucv.STORE_DIR
STORE_SUBDIR = "grades"

#: H=21 is the primary read (the horizon the doors prereg and US_BOARD_MEASUREMENT use);
#: H=10 is the fast companion that matures first, so a fresh cohort is not dark for a month.
HORIZONS = (10, 21)
BENCH = "SPY"

#: Freeze key.  ``board_definition`` participates for the same reason it does in the
#: candidates store: a definition change starts a fresh series instead of shadowing one.
GRADE_KEY = ("stamp_date", "ticker", "board_definition", "horizon")

#: The candidate columns the grader needs.  Projected at read time — the candidates store
#: is ~150 columns wide and this grader needs five of them, so a whole-frame read would
#: cost a hundred times the memory for nothing.
CANDIDATE_COLUMNS = ("stamp_date", "ticker", "board_definition")

_OBJECT_COLUMNS = ("stamp_date", "ticker", "board_definition", "fill_date", "mark_date",
                   "bench", "graded_asof", "schema")


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def _store_dir(root: Any = None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    return Path(base) / STORE_DIR / STORE_SUBDIR


def _part_path(graded_asof: str, root: Any = None) -> Path:
    """The monthly part a grading RUN belongs to (``YYYY-MM.parquet``).

    Keyed by the run's own as-of date, never by ``stamp_date`` — see the module docstring's
    storage note.  That is what makes every closed part byte-identical forever.
    """
    return _store_dir(root) / f"{str(graded_asof)[:7]}.parquet"


def load_grades(root: Any = None, *, months: Iterable[str] | None = None,
                columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Read the grade store as ONE frame — the only supported way to consume it.

    Mirrors :func:`engine.us_context_vector.load_candidates`: parts are concatenated in
    filename order (chronological), columns unify across parts, and ``months`` restricts to
    ``YYYY-MM`` run-month keys.  ``columns`` projects at the parquet level, so the
    idempotence check can read four key columns out of a store that is growing by ~66k rows
    a month without materialising the rest.

    A part that names a column the caller asked for and a part that does not are both
    handled: the projection is intersected per part and the union is reindexed at the end,
    so a column introduced in a later month reads back null for earlier months.
    """
    store = _store_dir(root)
    if not store.exists():
        return pd.DataFrame()
    wanted_months = {str(m) for m in months} if months is not None else None
    wanted_cols = [str(c) for c in columns] if columns is not None else None
    frames: list[pd.DataFrame] = []
    for part in sorted(store.glob("*.parquet")):
        if wanted_months is not None and part.stem not in wanted_months:
            continue
        try:
            frames.append(ucv._read_part(part, wanted_cols))
        except Exception as exc:  # noqa: BLE001 — one bad part must not blind the rest
            log.warning("us_prophet_grades: part %s unreadable (%s)", part.name, exc)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


#: Sentinel for a null ``board_definition`` inside a join key.  pandas does not reliably
#: match null keys across a merge, so both sides are normalised to a string before the
#: anti-join and the value never leaves this module.
_NULL_DEF = ""


def _key_frame(root: Any = None) -> pd.DataFrame:
    """Already-graded keys as a projected frame — the freeze set, columnar.

    Read as four columns out of a store growing by ~66k rows a month: after a year this is
    a few MB, where a Python set of tuples over the same rows would be ~100x that.
    """
    frame = load_grades(root, columns=list(GRADE_KEY))
    if frame.empty:
        return pd.DataFrame(columns=list(GRADE_KEY))
    frame = frame.dropna(subset=["stamp_date", "ticker", "horizon"]).copy()
    frame["stamp_date"] = frame["stamp_date"].astype(str).str.slice(0, 10)
    frame["ticker"] = frame["ticker"].astype(str)
    frame["board_definition"] = frame["board_definition"].fillna(_NULL_DEF).astype(str)
    frame["horizon"] = frame["horizon"].astype(int)
    return frame[list(GRADE_KEY)].drop_duplicates()


def graded_keys(root: Any = None) -> set[tuple]:
    """Every already-graded ``GRADE_KEY`` as a set of tuples (tests / ad-hoc reads).

    ``run()`` uses the frame form (:func:`_key_frame`) and an anti-join instead — same
    answer, but it never materialises one Python tuple per graded row.
    """
    frame = _key_frame(root)
    if frame.empty:
        return set()
    return {(r.stamp_date, r.ticker,
             (None if r.board_definition == _NULL_DEF else r.board_definition),
             int(r.horizon))
            for r in frame.itertuples(index=False)}


def _coerce_objects(frame: pd.DataFrame) -> pd.DataFrame:
    """Stable dtypes across parts — the candidates store's ``_coerce_nullable_objects``
    idiom, so an all-null column in one part cannot conflict with a typed one in another."""
    for column in _OBJECT_COLUMNS:
        if column in frame.columns:
            values = frame[column].astype(object)
            frame[column] = values.where(pd.notna(values), None)
    return frame


def append_grades(rows: list[dict], graded_asof: str, root: Any = None) -> int:
    """Append grade rows to the run month's part.  Returns that part's row count, or 0.

    NIGHTLY IS THE SOLE ADVANCER — the lane gate is the FIRST statement, so an intraday or
    render lane returns 0 without opening a file.

    Keep-FIRST on :data:`GRADE_KEY`: a key already in the part is never rewritten.  The
    caller's freeze set covers cross-part duplicates; this is the second belt, and it is
    what makes a same-night re-run a no-op even if the caller's set were empty.
    """
    if not ledger_lane.nightly_advance_enabled():
        log.info("us_prophet_grades append gated — not the US nightly lane")
        return 0
    if not rows or not graded_asof:
        return 0
    try:
        new = _coerce_objects(pd.DataFrame(rows))
        path = _part_path(graded_asof, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            prior = pd.read_parquet(path)
            columns = list(dict.fromkeys([*prior.columns, *new.columns]))
            combined = pd.concat(
                [prior.reindex(columns=columns), new.reindex(columns=columns)],
                ignore_index=True)
        else:
            combined = new
        combined = combined.drop_duplicates(subset=list(GRADE_KEY), keep="first")
        combined = _coerce_objects(combined)
        combined.to_parquet(path, index=False)
        return int(len(combined))
    except Exception as exc:  # noqa: BLE001 — a forward grader never breaks the nightly
        log.warning("us_prophet_grades append failed: %s", exc)
        return 0


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #

def load_bench(root: Any = None) -> pd.Series | None:
    """SPY dividend-adjusted closes from ``data/yahoo/SPY.parquet`` — the same per-ticker
    cache and benchmark ``grade_us_board`` and ``grade_prophet_doors`` grade against."""
    base = config.data_dir() if root is None else (Path(root) / "data")
    path = Path(base) / "yahoo" / f"{BENCH}.parquet"
    if not path.exists():
        return None
    try:
        frame = pd.read_parquet(path)
        series = frame["close"] if "close" in frame.columns else frame.iloc[:, 0]
        series.index = pd.to_datetime(series.index)
        return series.sort_index().dropna()
    except Exception as exc:  # noqa: BLE001
        log.warning("us_prophet_grades: bench read failed (%s)", exc)
        return None


def matured_horizons(index: pd.DatetimeIndex, stamp_date: Any,
                     horizons: tuple[int, ...] = HORIZONS) -> tuple[int, ...]:
    """Horizons the PANEL could possibly have matured for a stamp date.

    A NECESSARY condition, not the verdict.  H needs the fill bar (the first bar strictly
    after the stamp) plus H more bars; if the shared session calendar does not carry them,
    no individual name can, so the row is skipped without touching a price series.  This is
    what keeps the nightly cost proportional to the ~2 stamp dates that newly matured
    rather than to every ungraded row in the store (~35k forward_metrics calls a night
    otherwise).

    The per-name check inside :func:`grade_row` remains the authority: a name whose own
    series has holes stays pending here and grades on a later night.
    """
    if index is None or len(index) == 0:
        return ()
    try:
        stamp = pd.Timestamp(str(stamp_date)[:10])
    except Exception:  # noqa: BLE001
        return ()
    fill_pos = int(index.searchsorted(stamp, side="right"))   # first bar STRICTLY after
    if fill_pos >= len(index):
        return ()
    return tuple(h for h in horizons if fill_pos + h < len(index))


def grade_row(close: pd.Series, bench: pd.Series | None, stamp_date: Any,
              horizons: tuple[int, ...] = HORIZONS) -> dict[int, dict]:
    """``{H: mark}`` for every horizon MATURED for this candidate row.

    Sibling of ``scripts.grade_prophet_doors.grade_flag`` — same ruler
    (:func:`engine.grading.forward_metrics`), same next-bar fill, same SPY-on-the-name's-
    calendar excess.  ``tests/test_us_prophet_grades.py`` pins the two to identical output.
    An unmatured horizon is ABSENT from the result, never marked short.
    """
    out: dict[int, dict] = {}
    series = close.dropna() if close is not None else None
    if series is None or series.empty:
        return out
    if not isinstance(series.index, pd.DatetimeIndex):
        series = series.copy()
        series.index = pd.to_datetime(series.index)

    fwd = forward_metrics(series, stamp_date, horizons=horizons)
    if fwd.get("entry_price") is None:
        return out

    bench_aligned = bench.reindex(series.index).ffill() if bench is not None else None
    bench_fwd = (forward_metrics(bench_aligned, stamp_date, horizons=horizons)
                 if bench_aligned is not None else {})

    last_bar = series.index[-1]
    fill_pos = series.index.searchsorted(pd.Timestamp(fwd["fill_date"]), side="left")
    for horizon in horizons:
        ret = fwd.get(f"fwd_ret_{horizon}")
        if ret is None:
            continue
        if fill_pos + horizon >= len(series) or series.index[fill_pos + horizon] > last_bar:
            continue
        bench_ret = bench_fwd.get(f"fwd_ret_{horizon}")
        out[horizon] = {
            "horizon": int(horizon),
            "entry_price": round(float(fwd["entry_price"]), 6),
            "fill_date": fwd["fill_date"],
            "mark_date": str(series.index[fill_pos + horizon].date()),
            "fwd_ret": round(float(ret), 6),
            "bench": BENCH,
            "bench_ret": (round(float(bench_ret), 6) if bench_ret is not None else None),
            "excess_spy": (round(float(ret) - float(bench_ret), 6)
                           if bench_ret is not None else None),
            "fwd_mfe": (round(float(fwd[f"fwd_mfe_{horizon}"]), 6)
                        if fwd.get(f"fwd_mfe_{horizon}") is not None else None),
            "fwd_mdd": (round(float(fwd[f"fwd_mdd_{horizon}"]), 6)
                        if fwd.get(f"fwd_mdd_{horizon}") is not None else None),
        }
    return out


def load_candidate_keys(root: Any = None,
                        columns: Iterable[str] = CANDIDATE_COLUMNS) -> pd.DataFrame:
    """Identity columns of every stamped candidate row, through the store's own reader.

    Projected — :func:`engine.us_context_vector.load_candidates` takes ``columns`` for
    exactly this caller.  Globbing the parts here would break the candidates store's
    encapsulation rule ("nothing outside that module should know parts exist").
    """
    frame = ucv.load_candidates(root, columns=list(columns))
    if frame is None or frame.empty:
        return pd.DataFrame(columns=list(columns))
    return frame


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #

def run(root: Any = None, *, dry_run: bool = False,
        panel: pd.DataFrame | None = None,
        bench: pd.Series | None = None,
        horizons: tuple[int, ...] = HORIZONS) -> dict:
    """Grade every newly-matured (candidate row, horizon) pair.  Returns the run document.

    Never raises: a forward grader runs inside the nightly and must degrade to a disclosed
    null rather than take the build down with it.
    """
    doc: dict[str, Any] = {
        "schema": SCHEMA, "graded_asof": None, "n_candidates": 0, "n_stamp_dates": 0,
        "new_grades": 0, "appended": 0, "dry_run": bool(dry_run),
        "by_horizon": {h: 0 for h in horizons},
        "pending_immature": 0, "skipped_no_price": 0, "already_graded": 0,
        "rows": [], "degraded": [],
    }
    try:
        from engine import prophet_doors

        candidates = load_candidate_keys(root)
        doc["n_candidates"] = int(len(candidates))
        if candidates.empty:
            doc["note"] = ("no candidate rows stamped yet — the Context Vector store starts "
                           "accruing at its first nightly (prospective only, never backfilled)")
            return doc

        px = prophet_doors.load_universe(Path(root) if root is not None else None) \
            if panel is None else panel
        if px is None or px.empty:
            doc["degraded"].append({"input": "breadth close caches",
                                    "reason": "universe cache empty — nothing graded"})
            print("::warning title=us_prophet_grades::universe close cache empty; "
                  "no candidate row graded tonight", flush=True)
            return doc
        if not isinstance(px.index, pd.DatetimeIndex):
            px = px.copy()
            px.index = pd.to_datetime(px.index)
        px = px.sort_index()
        doc["graded_asof"] = str(px.index[-1].date())

        bench_series = load_bench(root) if bench is None else bench
        if bench_series is None:
            doc["degraded"].append({
                "input": f"data/yahoo/{BENCH}.parquet",
                "reason": "benchmark cache missing — excess_spy is null, absolute marks "
                          "still graded (a null excess is not a zero excess)"})
            print(f"::warning title=us_prophet_grades::{BENCH} cache missing; excess_spy "
                  "columns will be null for tonight's grades", flush=True)

        # Maturity is a property of the STAMP DATE on the shared session calendar, so it is
        # resolved once per date rather than once per row (~1,579 rows share each date).
        candidates = candidates.dropna(subset=["stamp_date", "ticker"]).copy()
        candidates["stamp_date"] = candidates["stamp_date"].astype(str).str.slice(0, 10)
        candidates["ticker"] = candidates["ticker"].astype(str)
        candidates["board_definition"] = (
            candidates["board_definition"].fillna(_NULL_DEF).astype(str)
            if "board_definition" in candidates.columns else _NULL_DEF)
        stamp_dates = sorted(candidates["stamp_date"].unique())
        doc["n_stamp_dates"] = len(stamp_dates)
        matured_by_date = {d: matured_horizons(px.index, d, horizons) for d in stamp_dates}

        # Explode candidate rows over the horizons the CALENDAR has matured, then anti-join
        # the freeze set.  Vectorized on purpose: the per-row price work below then touches
        # only rows that are both matured and ungraded (~2 stamp dates a night in steady
        # state), instead of every row the store has ever held.
        wanted_frames = []
        for horizon in horizons:
            dates = [d for d in stamp_dates if horizon in matured_by_date.get(d, ())]
            doc["pending_immature"] += int(
                candidates["stamp_date"].isin(
                    [d for d in stamp_dates if d not in dates]).sum())
            if not dates:
                continue
            wanted_frames.append(
                candidates.loc[candidates["stamp_date"].isin(dates),
                               list(CANDIDATE_COLUMNS)].assign(horizon=int(horizon)))
        todo = (pd.concat(wanted_frames, ignore_index=True) if wanted_frames
                else pd.DataFrame(columns=list(GRADE_KEY)))
        done = _key_frame(root)
        if not todo.empty and not done.empty:
            merged = todo.merge(done.assign(_done=1), on=list(GRADE_KEY), how="left")
            doc["already_graded"] = int(merged["_done"].notna().sum())
            todo = merged.loc[merged["_done"].isna(), list(GRADE_KEY)]

        new_rows: list[dict] = []
        for row in todo.itertuples(index=False):
            ticker = str(row.ticker)
            if ticker not in px.columns:
                doc["skipped_no_price"] += 1
                continue
            stamp = str(row.stamp_date)
            marks = grade_row(px[ticker], bench_series, stamp, (int(row.horizon),))
            mark = marks.get(int(row.horizon))
            if mark is None:
                # calendar matured but this NAME's own series has not (holes / late listing)
                doc["pending_immature"] += 1
                continue
            definition = (None if row.board_definition == _NULL_DEF
                          else str(row.board_definition))
            new_rows.append({
                "schema": SCHEMA, "stamp_date": stamp, "ticker": ticker,
                "board_definition": definition, "graded_asof": doc["graded_asof"],
                **mark})
            doc["by_horizon"][int(row.horizon)] = (
                doc["by_horizon"].get(int(row.horizon), 0) + 1)

        new_rows.sort(key=lambda r: (r["stamp_date"], r["ticker"], r["horizon"]))
        doc["new_grades"] = len(new_rows)
        doc["rows"] = new_rows
        if not dry_run:
            doc["appended"] = append_grades(new_rows, doc["graded_asof"], root)
        log.info("us_prophet_grades: candidates=%d dates=%d new=%d pending=%d no_price=%d",
                 doc["n_candidates"], doc["n_stamp_dates"], doc["new_grades"],
                 doc["pending_immature"], doc["skipped_no_price"])
    except Exception as exc:  # noqa: BLE001 — disclosed, never fatal
        log.warning("us_prophet_grades run failed: %s", exc)
        doc["degraded"].append({"input": "run", "reason": f"unexpected failure: {exc}"})
    return doc


def coverage(root: Any = None) -> dict:
    """Shape-only summary of the store — row/date counts per horizon.

    Read by the miss-audit's ``priority_score_scorecard`` so the scorecard can print how
    much record exists before it prints any statistic over it.
    """
    frame = load_grades(root, columns=["stamp_date", "horizon", "excess_spy"])
    out: dict[str, Any] = {"available": False, "n_rows": 0, "n_stamp_dates": 0,
                           "by_horizon": {}, "stamp_dates": {"first": None, "last": None}}
    if frame.empty:
        out["null_reason"] = ("no grade rows yet — the store accrues prospectively from the "
                              "first nightly after merge; H=10 rows mature ~11 sessions "
                              "after a stamp, H=21 rows ~22")
        return out
    dates = sorted(str(d) for d in frame["stamp_date"].dropna().unique())
    out.update({
        "available": True,
        "n_rows": int(len(frame)),
        "n_stamp_dates": len(dates),
        "stamp_dates": {"first": (dates[0] if dates else None),
                        "last": (dates[-1] if dates else None)},
    })
    for horizon, sub in frame.groupby("horizon"):
        out["by_horizon"][f"{int(horizon)}d"] = {
            "n_rows": int(len(sub)),
            "n_stamp_dates": int(sub["stamp_date"].nunique()),
            "n_excess_null": int(sub["excess_spy"].isna().sum()),
        }
    return out


def load_graded_frame(root: Any = None, *,
                      score_columns: Iterable[str] | None = None) -> pd.DataFrame:
    """Grades joined to the candidate row's stamped priority score — the scorecard's input.

    The join is the whole point of the pair of stores: the candidates store REMEMBERS the
    score the system gave a name on a night, this store records what that name then did,
    and only the join can say whether the score was right.  Read-only for both sides.

    ``score_columns`` extends the candidate projection (the itemized legs, lane, sector …).
    A candidate row with no stamped score joins with a null score — that is a MEASURED
    coverage fact (the builder computes the legs on the buy lane only, ~3% of rows), never
    a zero, and the scorecard reports it as coverage rather than imputing it.
    """
    grades = load_grades(root)
    if grades.empty:
        return grades
    wanted = list(dict.fromkeys([*CANDIDATE_COLUMNS, "prophet_score",
                                 *(score_columns or ())]))
    cands = ucv.load_candidates(root, columns=wanted)
    if cands is None or cands.empty:
        return grades.assign(prophet_score=pd.NA)
    cands = cands.drop_duplicates(subset=list(CANDIDATE_COLUMNS), keep="first")
    for frame in (grades, cands):
        for key in ("stamp_date", "ticker", "board_definition"):
            if key in frame.columns:
                frame[key] = frame[key].astype(object).where(frame[key].notna(), None)
    return grades.merge(cands, on=list(CANDIDATE_COLUMNS), how="left")


def summary_line(doc: Mapping[str, Any]) -> str:
    """One-line human summary for the nightly log / CLI."""
    return (f"us_prophet_grades asof={doc.get('graded_asof')} "
            f"candidates={doc.get('n_candidates')} dates={doc.get('n_stamp_dates')} "
            f"new={doc.get('new_grades')} pending={doc.get('pending_immature')} "
            f"no_price={doc.get('skipped_no_price')} appended={doc.get('appended')} "
            f"dry_run={doc.get('dry_run')}")
