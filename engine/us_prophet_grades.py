"""Full-population forward grader over the US Context Vector store (PROPHET US §W7).

Grades **every stamped candidate row** — the whole analyzed universe, not the ~12 that
become plans — across the **H=10/21/42/63 session ladder, excess vs SPY**, writing one grade
row per (candidate, horizon) to ``data/us_prophet_rank/grades/YYYY-MM/YYYY-MM-DD.parquet``.

Every row carries two conditioning columns so the record can be read as the several
different populations it actually is, and never as one pooled number:

* ``universe_tier`` — CURATED (fully analyzed, board-admissible) vs SCAN (seen and stamped
  over the widened universe, never board-admitted; roadmap §4.5);
* ``signal_class`` — BASING vs MOMENTUM vs OTHER, mapped from the board's existing cycle
  vocabulary, because a basing pick and a momentum pick are different bets and a single
  10-session headline grades the wait instead of the call (operator ruling 2026-08-05).

WHY (operator order 2026-08-05)
-------------------------------
"That rule where we only introduce 6-12 picks to the board … isn't that an awful rule cuz
then we have less data to train on"; "we should be remembering the score that we give
picks, so that it can be logged into the ledger and so that we can later assess how robust
and correct our scoring system is."  The remembering half already accrues: the Context
Vector store (:mod:`engine.us_context_vector`, #4540) stamps every name nightly WITH the
board priority-score legs itemized per row.  This module is the OUTCOME half —
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

STORAGE — month-grouped DAILY parts, keyed by the GRADING RUN
-------------------------------------------------------------
``grades/YYYY-MM/YYYY-MM-DD.parquet`` where the date is ``graded_asof`` (the price panel's
own last bar), NOT ``stamp_date``.  Two decisions, both forced by measurement:

* **Keyed by the RUN, not the stamp.**  Grading is a monotone forward process, so a nightly
  touches exactly one part and every earlier part is frozen.  Stamp-keying would reopen the
  previous month's part every night for ~3 weeks while its rows matured.  Each row still
  carries ``stamp_date`` and ``mark_date``, so a study joins by stamp month regardless of
  which part the row physically lives in.
* **Day grain inside a month directory, not one monthly file.**  A parquet cannot be
  appended in place, so a single monthly file is REWRITTEN nightly and git stores a whole
  new blob each time — cost ``S x (N+1)/2`` per month.  That was tolerable at the original
  scale (1,579 names x 2 horizons).  It is not at the scale this module now targets: the
  H=42/63 ladder doubles the rows and the scan tier (roadmap §4.5) multiplies the names by
  ~6.5.  MEASURED on a real-shaped month: curated-only 1.14 GB/yr, with the scan tier
  **6.30 GB/yr**.  A new file per run costs exactly the store's own size — 0.10 and
  0.57 GB/yr respectively, an **11x reduction at both scales** — and makes "every earlier
  part is byte-identical forever" absolute rather than merely usual.  The month directory
  keeps the ``months=`` filter and the monthly grouping intact.

Read through :func:`load_grades`; nothing outside this module should glob the parts.

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

#: The HORIZON LADDER.  H=10/21 are the incumbent reads (H=21 is what the doors prereg and
#: US_BOARD_MEASUREMENT use; H=10 matures first, so a fresh cohort is not dark for a month).
#: H=42/63 were added by operator ruling 2026-08-05: basing-class picks ("they take time to
#: base... but our board only measures for 10 day results??" — VALE/NEM) are structurally
#: punished by a 10-session headline, and the metals-cycle intuition is 3-5 months, so H=63
#: covers a quarter.  Adding maturities changes NOTHING else: same ruler, same freeze key,
#: same idempotency.  A longer horizon simply matures later and appears on a later night.
HORIZONS = (10, 21, 42, 63)
BENCH = "SPY"

#: Freeze key.  ``board_definition`` participates for the same reason it does in the
#: candidates store: a definition change starts a fresh series instead of shadowing one.
GRADE_KEY = ("stamp_date", "ticker", "board_definition", "horizon")

#: The candidate columns the grader needs.  Projected at read time — the candidates store
#: is ~150 columns wide and this grader needs a handful, so a whole-frame read would cost
#: a hundred times the memory for nothing.  That matters more once the scan tier lands:
#: ~8.7k rows a night instead of ~1,579 (roadmap §4.5).
CANDIDATE_COLUMNS = ("stamp_date", "ticker", "board_definition")

# --- cohort discriminator (scan tier, roadmap §4.5; operator-ratified 2026-08-05) --------
#: The column that says whether a stamped row is a CURATED name (fully analyzed, eligible
#: for board admission) or a SCAN name (seen and stamped over the widened ~8.7k universe,
#: NEVER board-admitted).  A sibling lane owns writing it into the candidates store; this
#: module only reads it and carries it onto every grade row, so the scorecard can report
#: the two cohorts separately and never pool them.
#:
#: RESOLVED BY NAME, THEN VALIDATED BY VALUE.  The column did not exist when this grader
#: was written, so it is resolved against a short list of unambiguous names and then
#: CHECKED: the values must fall inside :data:`COHORTS` or the resolution is rejected.
#: A name-only match could silently mis-cohort every row against a column that happens to
#: share a name; a value check cannot.  Whatever happens is recorded in the run document
#: (``discriminator``), so the outcome is never invisible — a store with no discriminator
#: grades exactly as before with a null cohort and a printed warning, never a silent pool.
DISCRIMINATOR_CANDIDATES = ("universe_tier", "scan_tier")
DISCRIMINATOR_COLUMN = "universe_tier"      # the name this module writes onto grade rows
COHORT_CURATED = "curated"
COHORT_SCAN = "scan"
COHORTS = (COHORT_CURATED, COHORT_SCAN)

# --- signal class (operator ruling 2026-08-05: basing picks vs a 10-day headline) --------
#: A basing-class pick and a momentum-class pick are two different bets measured by one
#: ruler today.  The operator: *"they take time to base... but our board only measures for
#: 10 day results??"*  This maps the board's EXISTING cycle vocabulary
#: (``engine.cycles.STATE_DISPLAY`` — internal state on the left, display label on the
#: right) onto a three-way class, so the record can show basing at H=42/63 beside momentum
#: at H=10/21.  NOTHING NEW IS STAMPED: the labels already exist on the board row.
#:
#: The split is "not moving yet" vs "already moving":
#:   * BOTTOM WATCH / TURN SIGNALED — the name is forming a base; the thesis needs TIME.
#:   * FRESH BUY / RALLY ON / CONFIRMING TURN — the move has fired; H=10 is a fair read.
#:   * everything else is not a long-side entry class at all.
#: An unmapped label is ``other`` with the ORIGINAL label preserved on the row
#: (``signal_label``), never dropped — a vocabulary that grows must be visible in the
#: store, not silently absorbed into a bucket.
CLASS_BASING = "basing"
CLASS_MOMENTUM = "momentum"
CLASS_OTHER = "other"
SIGNAL_CLASSES = (CLASS_BASING, CLASS_MOMENTUM, CLASS_OTHER)

SIGNAL_CLASS_BY_LABEL: dict[str, str] = {
    # --- basing: the base is still forming; a 10-session mark grades the wait, not the call
    "BOTTOM WATCH": CLASS_BASING,       "NEARING A LOW": CLASS_BASING,
    "TURN SIGNALED": CLASS_BASING,      "BOTTOMING": CLASS_BASING,
    # --- momentum: the move has already fired
    "FRESH BUY": CLASS_MOMENTUM,        "BUY ZONE": CLASS_MOMENTUM,
    "RALLY ON": CLASS_MOMENTUM,         "UPTREND": CLASS_MOMENTUM,
    "CONFIRMING TURN": CLASS_MOMENTUM,  "TURN IN PROGRESS": CLASS_MOMENTUM,
    # --- other: not a long-side entry class
    "DECLINE": CLASS_OTHER,             "DOWNTREND": CLASS_OTHER,
    "TOP WATCH": CLASS_OTHER,           "NEARING A HIGH": CLASS_OTHER,
    "ROLLING OVER": CLASS_OTHER,        "TOPPING": CLASS_OTHER,
    "COUNTERTREND BOUNCE": CLASS_OTHER, "UNCONFIRMED TURN": CLASS_OTHER,
}

#: PRE-REGISTERED class -> chartered horizon map.  **FIXED BEFORE ANY LONG-HORIZON DATA
#: MATURES**, which is the entire point: "grade each class at the horizon that flatters it,
#: chosen after seeing the results" is the exact sin this map exists to make impossible.
#: ADJUDICATED as proposed (Fable commissioner, 2026-08-05); every horizon in the ladder is graded and
#: reported for every class regardless, so nothing is hidden — this only fixes which
#: horizon is the class's HEADLINE read before anyone can see which one wins.
CHARTERED_HORIZON = {
    CLASS_BASING:   {"primary": 63, "supporting": 21},
    CLASS_MOMENTUM: {"primary": 10, "supporting": 21},
    CLASS_OTHER:    {"primary": 10, "supporting": 21},
}

#: The label column carrying the cycle state.  Resolved + VALIDATED exactly like the cohort
#: discriminator: a name match alone is never trusted, the values must intersect
#: :data:`SIGNAL_CLASS_BY_LABEL`.  The candidates store does not carry it yet — the live
#: board ROW does, as its ``label``/``state`` fields — so until a sibling lane stamps it
#: into the PIT store, every row classes as ``other`` with the absence DISCLOSED, never
#: presented as a measured "other".  (The board artifact is named by role, not by path:
#: this module never reads it, and a path literal here would register as a consumer of an
#: artifact it does not consume.)
SIGNAL_LABEL_CANDIDATES = ("cycle_state", "cycle_label", "label", "state")

_OBJECT_COLUMNS = ("stamp_date", "ticker", "board_definition", "fill_date", "mark_date",
                   "bench", "graded_asof", "schema", DISCRIMINATOR_COLUMN,
                   "signal_class", "signal_label")


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def _store_dir(root: Any = None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    return Path(base) / STORE_DIR / STORE_SUBDIR


def _part_path(graded_asof: str, root: Any = None) -> Path:
    """The part a grading RUN writes: ``grades/YYYY-MM/YYYY-MM-DD.parquet``.

    Keyed by the run's own as-of date, never by ``stamp_date``, and grouped by month.  A
    nightly therefore writes a NEW file and rewrites nothing — see the module docstring's
    storage note for why the day grain replaced a single monthly file once the horizon
    ladder and the scan tier multiplied the row count.
    """
    day = str(graded_asof)[:10]
    return _store_dir(root) / day[:7] / f"{day}.parquet"


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
    # ``YYYY-MM/YYYY-MM-DD.parquet`` — sorted() over the relative path is chronological
    # because both grains are zero-padded ISO.
    for part in sorted(store.glob("*/*.parquet")):
        if wanted_months is not None and part.parent.name not in wanted_months:
            continue
        try:
            if wanted_cols is None:
                frames.append(pd.read_parquet(part))
            else:
                try:
                    frame = pd.read_parquet(part, columns=wanted_cols)
                except Exception:  # noqa: BLE001 — column absent from an older part
                    frame = pd.read_parquet(part)
                frames.append(frame.reindex(columns=wanted_cols))
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


def classify_signal(label: Any) -> tuple[str, str | None]:
    """``label -> (signal_class, preserved_label)``.

    Case- and whitespace-insensitive against :data:`SIGNAL_CLASS_BY_LABEL`.  An unmapped
    non-empty label returns ``("other", <the original label>)`` — the label is PRESERVED on
    the grade row so a vocabulary that grows is visible in the store rather than silently
    absorbed.  A missing label returns ``("other", None)``, which the run document
    distinguishes from a measured "other" via the resolver's disclosure.
    """
    if label is None or label != label:          # None / NaN
        return CLASS_OTHER, None
    text = str(label).strip()
    if not text:
        return CLASS_OTHER, None
    return SIGNAL_CLASS_BY_LABEL.get(text.upper(), CLASS_OTHER), text


def resolve_signal_labels(frame: pd.DataFrame) -> dict:
    """Which candidate column carries the cycle label — resolved and VALIDATED.

    Same discipline as :func:`resolve_discriminator`: a name match is never trusted on its
    own, the column's values must intersect the known vocabulary or the resolution is
    rejected.  Returns a disclosure dict the caller puts in the run document.
    """
    out: dict[str, Any] = {"column": None, "available": False, "n_by_class": {},
                           "n_unmapped_labels": 0,
                           "candidates_tried": list(SIGNAL_LABEL_CANDIDATES)}
    if frame is None or frame.empty:
        out["reason"] = "no candidate rows to inspect"
        return out
    present = [c for c in SIGNAL_LABEL_CANDIDATES if c in frame.columns]
    if not present:
        out["reason"] = (
            f"the candidates store carries none of {list(SIGNAL_LABEL_CANDIDATES)} — the "
            "board's cycle label (BOTTOMING / UPTREND / …) lives on the board ROW today, "
            "not in the PIT store, and stamping it there belongs to the store's own lane. "
            "Every grade row is stamped signal_class='other' with a NULL signal_label, and "
            "the scorecard reports the class split as UNAVAILABLE rather than claiming "
            "every pick is 'other'")
        return out
    for column in present:
        mapped = frame[column].map(lambda v: classify_signal(v)[0])
        labels = frame[column].map(lambda v: classify_signal(v)[1])
        known = int(((mapped != CLASS_OTHER) & labels.notna()).sum())
        if not known:
            continue
        out.update({
            "column": column, "available": True,
            "n_by_class": {str(k): int(v) for k, v in
                           mapped.value_counts(dropna=True).to_dict().items()},
            "n_unmapped_labels": int(((mapped == CLASS_OTHER) & labels.notna()).sum()),
        })
        out["reason"] = (f"resolved from column '{column}'; values validated against the "
                         f"cycle vocabulary ({len(SIGNAL_CLASS_BY_LABEL)} known labels)")
        if out["n_unmapped_labels"]:
            out["reason"] += (f"; {out['n_unmapped_labels']} row(s) carry a label outside "
                              f"that vocabulary — classed 'other' with the label preserved")
        return out
    out["reason"] = (
        f"column(s) {present} are present but hold no label inside the cycle vocabulary — "
        "resolution REJECTED rather than trusted on the name alone; every grade row is "
        "stamped signal_class='other'")
    return out


def normalize_cohort(value: Any) -> str | None:
    """A discriminator value reduced to :data:`COHORTS`, or None if it is neither.

    Case- and whitespace-insensitive.  Anything outside the vocabulary is None — an
    unrecognised cohort is a stated null, never quietly folded into ``curated``.
    """
    text = str(value).strip().lower() if value is not None and value == value else ""
    return text if text in COHORTS else None


def resolve_discriminator(frame: pd.DataFrame) -> dict:
    """Which candidate column carries the curated/scan cohort — resolved and VALIDATED.

    Returns a disclosure dict: ``{column, available, n_by_cohort, n_unrecognised,
    reason}``.  ``column`` is None when nothing resolved, and ``reason`` always says why
    in plain words.  The caller stamps the result onto every grade row and puts the whole
    dict in the run document, so a store whose sibling lane has not landed the column yet
    grades exactly as before with a null cohort — disclosed, never silently pooled.

    A name match alone is not enough: the resolved column's values must fall inside
    :data:`COHORTS`, or it is rejected.  Otherwise a column that merely shares a name
    would mis-cohort every row in the store and nothing would say so.
    """
    out: dict[str, Any] = {"column": None, "available": False, "n_by_cohort": {},
                           "n_unrecognised": 0, "candidates_tried": list(
                               DISCRIMINATOR_CANDIDATES)}
    if frame is None or frame.empty:
        out["reason"] = "no candidate rows to inspect"
        return out
    present = [c for c in DISCRIMINATOR_CANDIDATES if c in frame.columns]
    if not present:
        out["reason"] = (
            "the candidates store carries none of "
            f"{list(DISCRIMINATOR_CANDIDATES)} — the scan-tier discriminator has not "
            "landed yet (a sibling lane owns writing it). Every grade row is stamped with "
            "a NULL cohort and the scorecard reports one unsplit cohort, which it labels "
            "as such rather than calling it 'curated'")
        return out
    for column in present:
        values = frame[column].map(normalize_cohort)
        counts = values.value_counts(dropna=True).to_dict()
        if not counts:
            continue
        out.update({
            "column": column, "available": True,
            "n_by_cohort": {str(k): int(v) for k, v in counts.items()},
            "n_unrecognised": int(values.isna().sum()),
        })
        out["reason"] = (f"resolved from column '{column}'; values validated against "
                         f"{list(COHORTS)}")
        if out["n_unrecognised"]:
            out["reason"] += (f"; {out['n_unrecognised']} row(s) carry a value outside "
                              f"that vocabulary and are stamped with a null cohort")
        return out
    out["reason"] = (
        f"column(s) {present} are present but hold no value inside {list(COHORTS)} — "
        "resolution REJECTED rather than trusted on the name alone; every grade row is "
        "stamped with a null cohort")
    return out


def load_candidate_keys(root: Any = None,
                        columns: Iterable[str] = CANDIDATE_COLUMNS) -> pd.DataFrame:
    """Identity + cohort columns of every stamped candidate row, via the store's reader.

    Projected — :func:`engine.us_context_vector.load_candidates` takes ``columns`` for
    exactly this caller.  Globbing the parts here would break the candidates store's
    encapsulation rule ("nothing outside that module should know parts exist").

    The discriminator and cycle-label candidates are requested alongside the identity
    columns; a name the store does not carry simply reads back null, so this costs nothing
    before those columns land and needs no code change after they do.
    """
    wanted = list(dict.fromkeys([*columns, *DISCRIMINATOR_CANDIDATES,
                                 *SIGNAL_LABEL_CANDIDATES]))
    frame = ucv.load_candidates(root, columns=wanted)
    if frame is None or frame.empty:
        return pd.DataFrame(columns=wanted)
    # a column the store has never held reads back all-null; drop those so the resolvers
    # see only columns that actually carry something.
    for column in (*DISCRIMINATOR_CANDIDATES, *SIGNAL_LABEL_CANDIDATES):
        if column in frame.columns and frame[column].isna().all():
            frame = frame.drop(columns=[column])
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
        "by_horizon": {h: 0 for h in horizons}, "by_cohort": {}, "by_signal_class": {},
        "discriminator": {"column": None, "available": False},
        "signal_labels": {"column": None, "available": False},
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

        # Cohort discriminator (roadmap §4.5): curated names vs the widened scan tier.
        # Resolved and validated once per run, then carried onto every grade row so the
        # scorecard can report the two populations separately — never pooled.
        row_keys = list(zip(candidates["stamp_date"], candidates["ticker"],
                            candidates["board_definition"]))
        disc = resolve_discriminator(candidates)
        doc["discriminator"] = disc
        if disc["available"]:
            # ``Series.map`` turns a None return into NaN, and ``NaN or "unsplit"`` is
            # NaN (NaN is truthy) — so an unrecognised cohort would key the counters as
            # nan and reach the row as a float. normalize_cohort only ever returns a str
            # from COHORTS or None, so this coercion is exact.
            cohort_by_key = {
                key: (value if isinstance(value, str) else None)
                for key, value in zip(
                    row_keys, candidates[disc["column"]].map(normalize_cohort))}
        else:
            cohort_by_key = {}
            print("::warning title=us_prophet_grades::scan-tier cohort discriminator "
                  f"unresolved — {disc.get('reason')}", flush=True)

        # Signal class (operator ruling 2026-08-05): basing vs momentum, from the board's
        # EXISTING cycle vocabulary. Nothing new is stamped anywhere.
        sig = resolve_signal_labels(candidates)
        doc["signal_labels"] = sig
        if sig["available"]:
            class_by_key = dict(zip(
                row_keys, candidates[sig["column"]].map(classify_signal)))
        else:
            class_by_key = {}
            print("::warning title=us_prophet_grades::signal-class labels unresolved — "
                  f"{sig.get('reason')}", flush=True)

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
            row_key = (stamp, ticker, str(row.board_definition))
            cohort = cohort_by_key.get(row_key)
            signal_class, signal_label = class_by_key.get(row_key, (CLASS_OTHER, None))
            new_rows.append({
                "schema": SCHEMA, "stamp_date": stamp, "ticker": ticker,
                "board_definition": definition, "graded_asof": doc["graded_asof"],
                DISCRIMINATOR_COLUMN: cohort, "signal_class": signal_class,
                "signal_label": signal_label, **mark})
            doc["by_horizon"][int(row.horizon)] = (
                doc["by_horizon"].get(int(row.horizon), 0) + 1)
            key = cohort or "unsplit"
            doc["by_cohort"][key] = doc["by_cohort"].get(key, 0) + 1
            doc["by_signal_class"][signal_class] = (
                doc["by_signal_class"].get(signal_class, 0) + 1)

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
    frame = load_grades(root, columns=["stamp_date", "horizon", "excess_spy",
                                       DISCRIMINATOR_COLUMN, "signal_class"])
    out: dict[str, Any] = {"available": False, "n_rows": 0, "n_stamp_dates": 0,
                           "by_horizon": {}, "by_cohort": {}, "by_signal_class": {},
                           "horizon_ladder": list(HORIZONS),
                           "chartered_horizon": CHARTERED_HORIZON,
                           "stamp_dates": {"first": None, "last": None}}
    if frame.empty:
        out["null_reason"] = ("no grade rows yet — the store accrues prospectively from the "
                              "first nightly after merge; H=10 rows mature ~11 sessions "
                              "after a stamp, H=21 rows ~22")
        return out
    dates = sorted(str(d) for d in frame["stamp_date"].dropna().unique())
    cohorts = frame[DISCRIMINATOR_COLUMN]
    out.update({
        "available": True,
        "n_rows": int(len(frame)),
        "n_stamp_dates": len(dates),
        "stamp_dates": {"first": (dates[0] if dates else None),
                        "last": (dates[-1] if dates else None)},
        "by_cohort": {str(k): int(v) for k, v in cohorts.value_counts(
            dropna=True).to_dict().items()},
        "n_cohort_null": int(cohorts.isna().sum()),
        "by_signal_class": {str(k): int(v) for k, v in frame["signal_class"].value_counts(
            dropna=True).to_dict().items()},
    })
    if out["n_cohort_null"]:
        out["cohort_null_note"] = (
            f"{out['n_cohort_null']} row(s) carry no curated/scan cohort — they were "
            "graded before the scan-tier discriminator landed in the candidates store. "
            "They are reported as one unsplit population, never folded into 'curated'")
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
    disc = doc.get("discriminator") or {}
    sig = doc.get("signal_labels") or {}
    cohorts = doc.get("by_cohort") or {}
    classes = doc.get("by_signal_class") or {}
    cohort_txt = (" ".join(f"{k}={v}" for k, v in sorted(cohorts.items()))
                  if cohorts else "none")
    class_txt = (" ".join(f"{k}={v}" for k, v in sorted(classes.items()))
                 if classes else "none")
    return (f"us_prophet_grades asof={doc.get('graded_asof')} "
            f"candidates={doc.get('n_candidates')} dates={doc.get('n_stamp_dates')} "
            f"new={doc.get('new_grades')} pending={doc.get('pending_immature')} "
            f"no_price={doc.get('skipped_no_price')} appended={doc.get('appended')} "
            f"cohorts[{cohort_txt}] classes[{class_txt}] "
            f"discriminator={disc.get('column') or 'UNRESOLVED'} "
            f"labels={sig.get('column') or 'UNRESOLVED'} "
            f"dry_run={doc.get('dry_run')}")
