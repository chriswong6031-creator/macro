"""Nightly US entry-STATUS re-measurement — the evidence loop for the entry-value ladder.

PROPHET US ANTICIPATION §6.6.  The A2 patience-first entry map ships with **CN-ordered v1
constants** (``bounce_wait`` highest … ``buy_soon`` lowest), lifted from the China board's
own measured ordering (CN §2.3, 2026-08-04: ``bounce_wait`` 6.9% loser rate vs ``buy_now``
30.0%, n=257 CN episodes).  Those constants are provisional BY CONSTRUCTION — they are a
Chinese measurement wearing an American map.  This module is what replaces them with a US
number: it groups the US board's own graded episodes by the entry status they carried AT
STAMP TIME and reports, per status, what the tape then did.

It publishes into the nightly miss-audit artifact as ``entry_status_scorecard``, beside the
``priority_score`` block, so the ladder's evidence base is visible in days rather than
asserted once and left.

WHAT IT READS — and why not the W7 priority store
--------------------------------------------------
Source: ``data/us_board_ledger/retro_grades.parquet`` — the US board's retro grade ledger,
written by ``scripts/grade_us_board.py``.  Every row is one (board row, horizon) episode and
carries BOTH halves this measurement needs: ``entry_status`` (the ``entry_signal.status``
snapshotted on the admission day) and ``excess_spy`` (the forward mark).

The §6.6 charter named the W7 full-population store
(``data/us_prophet_rank/{candidates,grades}``) as the source.  MEASURED 2026-08-08, that
store cannot answer the question:

* ``grades/`` **has never been written** — no part exists on disk and none has ever been
  committed, so there are zero US forward marks in it (the nightly miss-audit's own
  forward log records ``priority_score_available: false`` on every row to date);
* ``candidates/`` **carries no entry-status column at all** — the status is only present as
  the already-MAPPED numeric leg ``prophet_entry``, which is (a) non-injective
  (``wait_pullback``/``later`` both 0.55; ``extended``/``topping``/``blocked``/``exit``/
  ``avoid`` all 0.0), so the status is not recoverable from it, and (b) stamped on the buy
  lane only (~2% of rows).

Reading a mapped value to re-derive the map is circular anyway.  The board ledger is also
the CLOSER parity match: CN §2.3 measured China's **board admissions**
(``data/china_standout_track/board.parquet``), not a full-population context store, so
measuring the US board ledger is the same instrument on the same kind of population.  When
a sibling lane stamps ``entry_signal.status`` into the W7 candidates store, that store
becomes a second, wider read of the same question — it does not replace this one.

RULER — REUSED, NEVER FORKED
----------------------------
This module grades NOTHING.  ``excess_spy`` is read exactly as ``scripts/grade_us_board.py``
wrote it, and that script computes every forward return through
:func:`engine.grading.forward_metrics` (next-bar fill, positional session horizons, excess
vs SPY) under the one-grader law.  A re-derivation here would be a second ruler wearing the
first one's name; there is no arithmetic in this module beyond counting and taking a median
of marks someone else made.

DEFINITIONS — STATED, because a loser rate is a definition before it is a number
--------------------------------------------------------------------------------
* **loser** — ``excess_spy <= 0``.  A flat mark counts as a LOSS.  That is the CN §2.3
  convention (``research/cn_prophet_audit/v1_loser_audit.py``), kept verbatim so the US and
  CN tables are comparable numbers rather than two similarly-named ones.
* **win** — ``excess_spy > 0``.  Loser and win are EXACT COMPLEMENTS by construction; both
  are printed because the CN table prints both, not because they are two observations.
* **median excess / mean excess** — over the same non-null marks, in the ledger's own unit
  (a fraction: 0.01 = +1%), never rescaled here.
* **thin** — a cell with fewer than :data:`THIN_MIN_N` marks is LABELLED thin and read as
  directional only.  It is still printed: a small honest cell is the state of the record,
  and hiding it would make an accruing cohort look like an absent one.

STRUCTURE — cohort -> horizon -> class, with NO POOLED TOP-LEVEL FIGURE
-----------------------------------------------------------------------
``by_cohort[lane]["10d"]["by_entry_status"][status]``.  The board's lanes (buy / watch /
leaders / laggards) are different populations selected under different rules; a pooled
"US loser rate" across them would be a number about the lane mix, not about the statuses.
So there is deliberately no top-level loser rate, win rate, or median for a reader to
misquote — the only top-level figures are COUNTS and DATES (coverage), which are facts
about the record rather than claims about it.

WRITES NOTHING / ZERO AUTHORITY
--------------------------------
This module has no writer, so it has no forward-ledger advance to gate: it is a pure read
folded into the miss-audit document, and the miss-audit's own artifact write is what carries
the nightly gate.  ``tests/test_us_entry_status_remeasure.py`` pins the absence of any write
call rather than trusting the docstring.  Nothing here confers rank, gate, size, board or
plan rights on anything; it is ops telemetry that an operator reads before choosing the next
set of map constants by hand.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
import math
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

SCHEMA = "us.entry_status_remeasure/v1"

#: The graded episode ledger.  Relative to the repo root, exactly as the miss-audit's other
#: source constants are, so a caller with a temp root reads the temp copy.
LEDGER_REL = "data/us_board_ledger/retro_grades.parquet"

#: The status snapshotted on the admission day — ``entry_signal.assess()["status"]`` as
#: ``scripts/grade_us_board.py`` lifted it onto the episode row.
STATUS_COLUMN = "entry_status"
#: The population split.  Board lanes are different selections, never pooled (see module
#: docstring).  A row with no lane is reported under ``unlaned`` rather than folded into
#: ``buy`` — calling it buy would assert an admission that was not measured.
COHORT_COLUMN = "lane"
#: The forward mark.  Benchmark-relative by choice: the CN table it must be comparable to is
#: CSI300-relative, and an absolute US return in a rising tape flatters every status equally.
EXCESS_COLUMN = "excess_spy"

#: Columns projected out of an ~87-column ledger.  Everything else is another study's.
LEDGER_COLUMNS = ("as_of", "horizon", COHORT_COLUMN, "ticker", STATUS_COLUMN, EXCESS_COLUMN)

#: The three columns without which there is no measurement.  Everything else in
#: :data:`LEDGER_COLUMNS` is OPTIONAL and degrades in place: no ``lane`` means one
#: ``unlaned`` cohort, no ``as_of`` means no date count.  The distinction matters because
#: the ledger's writer is a live file with its own lanes — a column renamed there must cost
#: the read that used it, never the whole table.
REQUIRED_COLUMNS = ("horizon", STATUS_COLUMN, EXCESS_COLUMN)

#: Mirrors ``scripts.grade_us_board.HORIZONS``.  RESTATED rather than imported: an ``engine``
#: module importing a ``scripts`` module inverts the dependency direction — the same reason
#: the full-population forward grader restates its sibling's ruler instead of importing it.
#: (That grader is named by ROLE here, never by module: its suite greps every module outside
#: its own allowlist for its literal name to pin its zero-authority fence, so a docstring
#: mention would register as a dependency this module does not have.)
#: Used only as the flat forward-log row's COLUMN SET, which must be stable across nights;
#: the block itself reports whatever horizons the ledger actually holds.
HORIZONS = (5, 10, 21, 63)

#: Below this many graded marks a cell is labelled thin and read as DIRECTIONAL ONLY.
#: A disclosure rule, not a gate — it labels cells, it never drops them.
THIN_MIN_N = 20

#: The statuses whose cells get a stable column in the flat forward log.  Fixed here so the
#: log is a plottable series rather than a table whose columns depend on tonight's data.
#: These are exactly the CN §2.3 table's rows — the ladder debate's own vocabulary.  The
#: BLOCK reports every status present in the ledger, including ones absent from this tuple.
LOG_STATUSES = ("bounce_wait", "wait_pullback", "hold", "buy_now", "partial", "buy_soon",
                "extended")

#: The lanes that get stable columns in the flat forward log.  BUY ONLY, deliberately: the
#: entry-value map decides ADMISSION, so the admitted cohort is the one whose series a
#: reader plots when they ask whether the constants are earning their place.  Every other
#: lane is in the artifact block in full — this is a plotting projection, not the table.
LOG_COHORTS = ("buy",)

LOSER_DEFINITION = (f"loser = {EXCESS_COLUMN} <= 0 (a FLAT mark counts as a loss); "
                    f"win = {EXCESS_COLUMN} > 0. The two are exact complements by "
                    f"construction — both are printed because the CN §2.3 table prints "
                    f"both, not because they are two independent observations")


# --------------------------------------------------------------------------- #
# JSON safety
# --------------------------------------------------------------------------- #

def _num(value: Any, digits: int = 5) -> float | None:
    """Round to a JSON-safe float, or ``None`` for anything non-finite.

    ``json.dumps`` emits a bare ``NaN``/``Infinity`` for those, which is INVALID JSON — one
    degenerate cell would make a strict reader reject the whole nightly artifact.  A null
    here means "not computable", never zero.
    """
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


# --------------------------------------------------------------------------- #
# store
# --------------------------------------------------------------------------- #

def ledger_path(root: Any) -> Path:
    """Absolute path of the graded episode ledger under ``root``."""
    return Path(root) / LEDGER_REL


def load_ledger(root: Any, degraded: list[dict] | None = None,
                *, columns: Iterable[str] | None = None) -> pd.DataFrame | None:
    """Read the graded episode ledger, projected.  ``None`` when it cannot be read.

    Fail-soft on every path: a missing or unreadable ledger degrades to a null block with a
    named reason, never an exception into the nightly.

    The projection is INTERSECTED with the file's real schema before the read rather than
    passed through blindly.  Passing an absent name to ``read_parquet(columns=...)`` raises,
    which would turn one renamed conditioning column into a null table — and the writing
    lane (``scripts/grade_us_board.py``) is live and under active change.  So an absent
    OPTIONAL column costs only the read that used it, while an absent
    :data:`REQUIRED_COLUMNS` member is reported BY NAME: a silently half-present join is
    the failure mode a status table can least afford.
    """
    deg = degraded if degraded is not None else []
    path = ledger_path(root)
    if not path.exists():
        deg.append({"input": LEDGER_REL, "severity": "expected",
                    "reason": "graded episode ledger absent — entry-status re-measurement "
                              "is null, not zero"})
        return None
    want = list(columns) if columns is not None else list(LEDGER_COLUMNS)
    try:
        import pyarrow.parquet as pq

        present = set(pq.ParquetFile(path).schema_arrow.names)
    except Exception as exc:  # noqa: BLE001 — a narrow ledger read must never kill the audit
        deg.append({"input": LEDGER_REL, "severity": "unexpected",
                    "reason": f"graded episode ledger unreadable: {exc} — entry-status "
                              f"re-measurement is null, not zero"})
        return None
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    if missing:
        deg.append({"input": LEDGER_REL, "severity": "unexpected",
                    "reason": f"ledger carries no {', '.join(missing)} column — the "
                              f"status/outcome join is not possible, so the table is null"})
        return None
    absent = [c for c in want if c not in present]
    if absent:
        deg.append({"input": LEDGER_REL, "severity": "expected",
                    "reason": f"ledger carries no {', '.join(absent)} column — the reads "
                              f"that used it degrade in place (no lane = one 'unlaned' "
                              f"cohort; no as_of = no date count); the table still stands"})
    try:
        frame = pd.read_parquet(path, columns=[c for c in want if c in present])
    except Exception as exc:  # noqa: BLE001
        deg.append({"input": LEDGER_REL, "severity": "unexpected",
                    "reason": f"graded episode ledger unreadable: {exc} — entry-status "
                              f"re-measurement is null, not zero"})
        return None
    return frame


# --------------------------------------------------------------------------- #
# legs
# --------------------------------------------------------------------------- #

def status_leg(sub: pd.DataFrame) -> dict:
    """One (cohort, horizon, entry-status) cell.

    ``n`` counts the episodes in the cell; ``n_excess`` counts the ones carrying a forward
    mark.  Every statistic is computed on ``n_excess``, and a cell with none of them is a
    printed null with a reason — an unmarked episode is a missing observation, never a zero
    excess and never a loss.
    """
    vals = pd.to_numeric(sub[EXCESS_COLUMN], errors="coerce").dropna()
    out: dict[str, Any] = {"n": int(len(sub)), "n_excess": int(len(vals))}
    if not len(vals):
        out.update({"loser_rate": None, "win_rate": None, "median_excess": None,
                    "mean_excess": None, "thin": True,
                    "null_reason": ("no episode in this cell carries a forward mark yet — "
                                    "not computable, which is not a 0% loser rate")})
        return out
    out.update({
        "loser_rate": _num((vals <= 0).mean(), 4),
        "win_rate": _num((vals > 0).mean(), 4),
        "median_excess": _num(vals.median()),
        "mean_excess": _num(vals.mean()),
        "thin": bool(len(vals) < THIN_MIN_N),
    })
    if out["thin"]:
        out["thin_reason"] = (f"{len(vals)} graded mark(s) — below the {THIN_MIN_N}-mark "
                              f"disclosure floor; DIRECTIONAL ONLY, not a measurement")
    return out


def horizon_leg(sub: pd.DataFrame, horizon: int) -> dict:
    """One cohort's read at one horizon: every entry status present, side by side.

    No cell is dropped for being thin and no status is merged into an "other" bucket — the
    shape of a still-accruing cohort IS the finding while the anticipation era matures.
    """
    marks = pd.to_numeric(sub[EXCESS_COLUMN], errors="coerce")
    statuses = sub[STATUS_COLUMN]
    out: dict[str, Any] = {
        "horizon_d": int(horizon),
        "n_episodes": int(len(sub)),
        "n_excess": int(marks.notna().sum()),
        "n_with_status": int(statuses.notna().sum()),
        "n_dates": int(sub["as_of"].nunique()) if "as_of" in sub.columns else None,
        "by_entry_status": {},
        "thin_statuses": [],
    }
    known = sub[statuses.notna()]
    if known.empty:
        out["null_reason"] = (
            f"no episode at this horizon carries an {STATUS_COLUMN} — the status/outcome "
            f"join is empty here, which is not a flat table")
        return out
    for status, part in known.groupby(known[STATUS_COLUMN].astype(str)):
        leg = status_leg(part)
        out["by_entry_status"][str(status)] = leg
        if leg.get("thin"):
            out["thin_statuses"].append(str(status))
    out["thin_statuses"] = sorted(out["thin_statuses"])
    n_unlabelled = int(len(sub) - len(known))
    if n_unlabelled:
        out["n_status_missing"] = n_unlabelled
        out["status_missing_note"] = (
            f"{n_unlabelled} episode(s) carry no {STATUS_COLUMN} and are EXCLUDED from the "
            f"status table rather than bucketed — an unknown status is not a status")
    return out


# --------------------------------------------------------------------------- #
# the block
# --------------------------------------------------------------------------- #

def scorecard(root: Any, degraded: list[dict] | None = None) -> dict:
    """The nightly ``entry_status_scorecard`` block (ANTICIPATION §6.6).

    Pure read.  Writes nothing, gates nothing, and returns strict-JSON-safe values on every
    path.  Fail-soft: a missing ledger produces a null block with a named reason.
    """
    deg = degraded if degraded is not None else []
    block: dict[str, Any] = {
        "schema": SCHEMA,
        "tier": "ops_telemetry",
        "authority": "none — read-only aggregation of an existing graded ledger; no rank, "
                     "gate, size, board, plan or user-facing consumer. The entry-value map "
                     "constants are revised BY HAND by an operator reading this table",
        "purpose": ("ANTICIPATION §6.6 — the evidence loop for the patience-first entry "
                    "ladder. The shipped v1 constants are the CN measured ordering; this "
                    "is the US measurement that revises them"),
        "source": LEDGER_REL,
        "graded_by": ("scripts.grade_us_board — engine.grading.forward_metrics (next-bar "
                      "fill, positional session horizons), excess vs SPY. Nothing is "
                      "regraded here: the marks are read exactly as that grader wrote them"),
        "definitions": {
            # KEYED ``loser_and_win``, not ``loser_rate``: no key outside ``by_cohort`` may
            # share a name with an outcome statistic, so "is there a pooled figure here?"
            # stays answerable by key name alone — by a reader, a flattener, or the suite's
            # own no-pooled-figure walk, which needs no exemption list as a result.
            "loser_and_win": LOSER_DEFINITION,
            "excess_unit": "fraction of price — 0.01 = +1.00%, in the ledger's own unit",
            "entry_status": (f"{STATUS_COLUMN} — entry_signal.status as snapshotted on the "
                             f"board-admission day, NOT re-derived tonight"),
            "cohort": (f"{COHORT_COLUMN} — the board lane the episode was admitted into. "
                       f"Lanes are different selections and are never pooled"),
            "thin": (f"a cell with fewer than {THIN_MIN_N} graded marks is labelled thin "
                     f"and read as directional only; it is still printed"),
        },
        "no_pooled_figure": (
            "there is deliberately no top-level loser rate, win rate or median excess. A "
            "figure pooled across lanes would describe the lane mix, not the statuses. The "
            "only top-level numbers here are counts and dates"),
        "w7_priority_store": (
            "the §6.6 charter named data/us_prophet_rank as the source. MEASURED "
            "2026-08-08: its grades/ subtree has never been written (zero forward marks) "
            "and its candidates/ store carries no entry-status column — only the already-"
            "mapped, non-injective prophet_entry leg, on the buy lane only. Reading a "
            "mapped value to re-derive the map is circular, so this block reads the board "
            "ledger, which is also the closer CN parity match (CN §2.3 measured board "
            "admissions). When a sibling lane stamps entry_signal.status into the W7 "
            "candidates store it becomes a second, wider read — not a replacement"),
        "cn_reference": {
            "note": ("the CN §2.3 ordering the shipped v1 constants encode, restated so the "
                     "US numbers below are read against what they are replacing. CN "
                     "episodes, CSI300-relative, H=10, n=257 — NOT a US measurement"),
            "source": "research/cn_prophet_audit/v1_loser_audit_results.json (2026-08-04)",
            # Same naming rule as ``definitions`` above: these are CHINA's numbers, so the
            # key must not read as one of this table's own outcome statistics.
            "cn_loser_rate_by_status": {
                "bounce_wait": 0.069, "wait_pullback": 0.0769, "hold": 0.1935,
                "extended": 0.2979, "buy_now": 0.30, "partial": 0.4138, "buy_soon": 0.4667},
        },
        "thin_min_n": THIN_MIN_N,
        "available": False,
    }
    frame = load_ledger(root, deg)
    if frame is None:
        block["null_reason"] = (f"{LEDGER_REL} unreadable or absent — see degraded. An "
                                f"absent ledger is not a null result")
        return block
    if frame.empty:
        block["null_reason"] = (
            f"{LEDGER_REL} holds no episodes yet — the entry-status table accrues with the "
            f"board ledger. An empty record is not a flat table")
        return block

    statuses = frame[STATUS_COLUMN]
    marks = pd.to_numeric(frame[EXCESS_COLUMN], errors="coerce")
    dates = sorted(str(d)[:10] for d in frame["as_of"].dropna().unique()) \
        if "as_of" in frame.columns else []
    cohorts = (frame[COHORT_COLUMN] if COHORT_COLUMN in frame.columns
               else pd.Series([None] * len(frame), index=frame.index))
    # COUNTS AND DATES ONLY — never an outcome statistic (see `no_pooled_figure`).
    block.update({
        "available": True,
        "coverage": {
            "n_episodes": int(len(frame)),
            "n_with_status": int(statuses.notna().sum()),
            "status_coverage_pct": _num(100.0 * float(statuses.notna().mean()), 2),
            "n_excess": int(marks.notna().sum()),
            "n_dates": len(dates),
            "as_of": {"first": (dates[0] if dates else None),
                      "last": (dates[-1] if dates else None)},
            "n_by_status": {str(k): int(v)
                            for k, v in statuses.value_counts(dropna=True).items()},
            "note": ("an episode with no entry status is EXCLUDED from the table rather "
                     "than bucketed; the count above is what that exclusion costs"),
        },
        "cohort_split": {
            "column": COHORT_COLUMN,
            "n_by_cohort": {str(k): int(v)
                            for k, v in cohorts.value_counts(dropna=True).items()},
            "n_unlaned": int(cohorts.isna().sum()),
            "note": ("board lanes are DIFFERENT POPULATIONS and are never pooled: every "
                     "statistic below is computed inside one lane. A row with no lane is "
                     "reported under 'unlaned', never folded into 'buy'"),
        },
        "horizons_present": sorted(int(h) for h in
                                   pd.to_numeric(frame["horizon"], errors="coerce")
                                   .dropna().unique()),
    })
    by_cohort: dict[str, Any] = {}
    for cohort, sub in frame.groupby(cohorts.fillna("unlaned").astype(str)):
        by_cohort[str(cohort)] = {
            f"{int(h)}d": horizon_leg(part, int(h))
            for h, part in sub.groupby(pd.to_numeric(sub["horizon"], errors="coerce"))
            if pd.notna(h)
        }
    block["by_cohort"] = by_cohort
    return block


# --------------------------------------------------------------------------- #
# flat forward-log row + human summary
# --------------------------------------------------------------------------- #

def row_fields(doc: Mapping[str, Any]) -> dict:
    """The block's headline cells, flattened for the nightly forward-log row.

    Compact and STABLE by design: the cohort/status/horizon column set is fixed by
    :data:`LOG_COHORTS`, :data:`LOG_STATUSES` and :data:`HORIZONS`, so the log is a series
    someone can plot rather than a table whose columns move with tonight's data.  Null-safe
    on every path, including a document with no block at all.
    """
    block = (doc.get("entry_status_scorecard") or {}) if isinstance(doc, Mapping) else {}
    by_cohort = block.get("by_cohort") or {}
    cov = block.get("coverage") or {}
    out: dict[str, Any] = {
        "entry_status_available": bool(block.get("available")),
        "entry_status_n_episodes": cov.get("n_episodes"),
        "entry_status_coverage_pct": cov.get("status_coverage_pct"),
        "entry_status_n_dates": cov.get("n_dates"),
    }
    for cohort in LOG_COHORTS:
        legs = by_cohort.get(cohort) or {}
        for h in HORIZONS:
            cell = legs.get(f"{h}d") or {}
            table = cell.get("by_entry_status") or {}
            for status in LOG_STATUSES:
                leg = table.get(status) or {}
                key = f"entry_status_{cohort}_{status}_{h}d"
                out[f"{key}_n"] = leg.get("n_excess")
                out[f"{key}_loser_rate"] = leg.get("loser_rate")
                out[f"{key}_median_excess"] = leg.get("median_excess")
    return out


def summary_lines(block: Mapping[str, Any] | None) -> list[str]:
    """Human lines for the nightly CLI summary.  Never raises on a null block."""
    block = block or {}
    if not block.get("available"):
        return [f"  entry_status: null — {block.get('null_reason') or 'not computed'}"]
    cov = block.get("coverage") or {}
    split = block.get("cohort_split") or {}
    lines = [f"  entry_status: {cov.get('n_episodes')} episode(s), "
             f"{cov.get('n_with_status')} carry a status "
             f"({cov.get('status_coverage_pct')}%) over {cov.get('n_dates')} date(s); "
             f"lanes {split.get('n_by_cohort') or 'NONE'}"]
    for cohort, legs in sorted((block.get("by_cohort") or {}).items()):
        lines.append(f"    [{cohort}]")
        for key, cell in sorted(legs.items(), key=lambda kv: cell_sort_key(kv[0])):
            if cell.get("null_reason"):
                lines.append(f"      {key}: null — {cell['null_reason']}")
                continue
            table = cell.get("by_entry_status") or {}
            body = " ".join(
                f"{status}:n={leg.get('n_excess')}/lose={leg.get('loser_rate')}"
                f"{'*' if leg.get('thin') else ''}"
                for status, leg in sorted(table.items()))
            lines.append(f"      {key}: {body or 'no status cell'}")
    lines.append(f"      (* = thin, fewer than {THIN_MIN_N} marks — directional only)")
    return lines


def cell_sort_key(key: str) -> int:
    """Sort ``"10d"`` numerically so a horizon ladder prints 5, 10, 21, 63 — not 10, 21, 5."""
    try:
        return int(str(key).rstrip("d"))
    except ValueError:
        return 1 << 30
