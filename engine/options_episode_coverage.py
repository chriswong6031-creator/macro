"""Bound and classify the unlabelled H+60 options-episode population.

WHY THIS EXISTS.  ``data/options_signal_episode/outcomes_h60.jsonl`` is an
append-only ledger of *derived* labels, and ``derive_h60_outcome`` deliberately
returns non-persisted ``pending`` dicts for every condition it cannot freeze
reproducibly.  Pending rows are never appended (that rule is preregistered in
``research/options_estate/OPTIONS_SIGNAL_EPISODE_SESSION_OUTCOMES_PREREG.md``),
so an episode that never resolves simply *never appears* in the outcome ledger.
Nothing in the estate bounded, censused, or alerted on that difference: the
builder tallies ``pending_reasons`` into a run summary that is printed and
discarded, so a permanently-growing hole in the labelled population was
invisible.

Measured 2026-08-13 on the live estate: 1,206 episodes, 969 outcome rows, and
**237 episodes with no H+60 row at all** — 15.9%-23.5% of every session.  That
set is not random.  It decomposes cleanly into two classes with completely
different remedies, which is the whole reason this module classifies rather
than just counts:

``no_admissible_price_source``
    The ticker has no admissible receipt-bound intraday parquet, so
    ``_price_snapshot`` returns ``(None, None)`` and every episode for that
    ticker is pending ``missing_price_receipt`` forever.  Measured: 223 of the
    237 (94.1%), spanning 26 tickers that have **never** received a single
    complete label.  This is a universe-reconciliation defect, not a
    measurement limit: ``build_polygon_intraday._universe()`` is
    ``data/stocks/*.parquet`` plus the ``config.yahoo`` ETF groups, and 25 of
    those 26 tickers are in neither.  The options flow detector mints episodes
    for a universe the price lane does not cover.

``source_dependent_pending``
    The ticker demonstrably *is* labellable, so the pending is per-episode —
    cadence alignment, bar gaps, vendor delay.  Measured: 14 of the 237 (5.9%;
    AMD 12, SOXX 1, VRT 1), all anchored in the 18:00Z hour, i.e. exactly the
    ``aligned_exit_crosses_session_close`` condition that an hourly source
    produces when the cadence-aligned exit rounds up to the 20:00Z close.

WHY THE SPLIT IS LOAD-BEARING.  Class one is fixable by collecting the missing
tickers and is *wrong* to accept; class two is protected by the prereg line
"no cadence-dependent condition is frozen as terminal" and cannot be persisted
without a new preregistered causal contract.  Reporting a single "20% pending"
number hides both facts and invites the wrong remedy for 94% of the backlog.

THE SURVIVORSHIP POINT.  Readers must not treat ``outcomes_h60.jsonl`` as the
episode population.  The 26 unlabelled tickers are a coherent slice — recent
listings and high-beta AI/datacenter names (SMCI, CRWV, NBIS, ASTS, LITE,
COHR, ARM, OKLO, RKLB, TLN) whose common property is *lacking deep price
history*, which is the very thing the intraday universe keys on.  The labelled
population is therefore biased toward established deep-history mega-caps.

This module is pure: no filesystem, no clock, no network.  The caller supplies
``now`` and the already-parsed ledger rows.  ``scripts/audit_options_episode_
outcome_coverage.py`` is the I/O shell that emits the census and the tripwires.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from engine.options_signal_episode import HORIZON_MINUTES

CENSUS_SCHEMA = "options.signal_episode_outcome_coverage_census/v1"

#: The horizon clock has not yet elapsed.  Transient and entirely expected for a
#: freshly minted episode; never a defect and never counted against a bound.
IMMATURE_CLASS = "horizon_not_matured"

#: The ticker has never produced a complete label.  Structural: no admissible
#: price source exists, so no future run of the current lane can resolve it.
STRUCTURAL_GAP_CLASS = "no_admissible_price_source"

#: The ticker is demonstrably labellable, so this episode is pending for a
#: per-episode, source-dependent reason (cadence alignment, bar gap, delay).
SOURCE_DEPENDENT_CLASS = "source_dependent_pending"

UNLABELLED_CLASSES = (IMMATURE_CLASS, STRUCTURAL_GAP_CLASS, SOURCE_DEPENDENT_CLASS)

# --- Declared bounds -------------------------------------------------------
# Preregistered in research/options_estate/
# OPTIONS_EPISODE_OUTCOME_COVERAGE_ADJUDICATION_2026-08-13.md.  These are
# thresholds on the *matured* population only: an immature episode is not a
# hole.  Warn levels are set below the measured 2026-08-13 state deliberately —
# the current 19.7% is a real defect and must be loud from the first run, not
# normalised by a threshold drawn around it.  Fail levels are set above it so
# an already-known defect does not red the nightly lane it is reported by.
WARN_MATURED_UNLABELLED_SHARE = 0.10
FAIL_MATURED_UNLABELLED_SHARE = 0.30

# The accepted-forever class carries a much tighter bound: it is the only class
# the adjudication permits to persist, so growth in it is the signal that the
# acceptance is no longer safe.
WARN_SOURCE_DEPENDENT_SHARE = 0.03
FAIL_SOURCE_DEPENDENT_SHARE = 0.10

# The census is a bounded artifact, in the same spirit as the ledger-bound
# audit: an unbounded list of every affected episode would grow with the estate
# and stop being readable exactly when it matters most.
MAX_CENSUS_TICKERS = 64
MAX_CENSUS_SESSIONS = 32


class CoverageCensusError(RuntimeError):
    """An input row was not shaped like an episode or outcome ledger row."""


def _as_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise CoverageCensusError(f"{field} must be a non-empty ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise CoverageCensusError(f"{field} is not ISO-8601: {value!r}") from exc
    if parsed.tzinfo is None:
        raise CoverageCensusError(f"{field} must carry a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _share(numerator: int, denominator: int) -> float:
    """Shares are reported against the matured denominator, never the estate.

    A zero denominator yields 0.0 rather than a null so a tripwire comparison
    can never silently short-circuit on ``None``.
    """
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def labellable_tickers(outcomes: Iterable[Mapping[str, Any]],
                       episodes_by_id: Mapping[str, Mapping[str, Any]]) -> set[str]:
    """Tickers with at least one COMPLETE H+60 row anywhere in the estate.

    Completeness is the only honest ledger-side proof that a ticker has an
    admissible price source.  A terminal-incomplete row is NOT proof: both of
    its reasons (``decision_after_session_close``, ``horizon_crosses_session_
    close``) are pure clock facts derived without consuming a single price
    observation, so a ticker with nothing but terminal rows has demonstrated
    nothing about its source.  Measured: ASTS, SNOW, ARM and DDOG each carry
    terminal rows and zero complete rows, and all four are in the structural
    gap — counting terminal rows as evidence would have misclassified them.
    """
    found: set[str] = set()
    for row in outcomes:
        if row.get("status") != "complete":
            continue
        episode = episodes_by_id.get(str(row.get("episode_id") or ""))
        if episode is None:
            continue
        ticker = episode.get("ticker")
        if isinstance(ticker, str) and ticker:
            found.add(ticker)
    return found


def classify_unlabelled_episode(
    episode: Mapping[str, Any],
    *,
    now: datetime,
    labellable: frozenset[str] | set[str],
    priced_tickers: frozenset[str] | set[str] | None = None,
) -> str:
    """Assign one unlabelled episode to a declared class.

    ``priced_tickers`` is the ground-truth mode: the set of tickers that
    actually have an admissible ``<T>.parquet`` + ``.receipt.json`` pair on the
    nightly host.  When it is supplied it decides the structural class outright.
    When it is absent (CI, any checkout without the mutable intraday cache) the
    classifier falls back to ledger-only inference via ``labellable``.  The two
    modes are reported separately in the census so a reader always knows which
    question was answered.
    """
    available = _as_utc(episode.get("available_at"), "episode.available_at")
    if now < available + timedelta(minutes=HORIZON_MINUTES):
        return IMMATURE_CLASS
    ticker = episode.get("ticker")
    if not isinstance(ticker, str) or not ticker:
        raise CoverageCensusError("episode.ticker must be a non-empty string")
    covered = priced_tickers if priced_tickers is not None else labellable
    return SOURCE_DEPENDENT_CLASS if ticker in covered else STRUCTURAL_GAP_CLASS


def _tripwires(*, matured: int, matured_unlabelled: int, source_dependent: int,
               structural_gap: int, gap_ticker_count: int) -> list[dict[str, Any]]:
    """Evaluate the declared bounds.  Order is severity-first, then declaration."""
    unlabelled_share = _share(matured_unlabelled, matured)
    dependent_share = _share(source_dependent, matured)
    fired: list[dict[str, Any]] = []

    def add(identifier: str, level: str, observed: float, threshold: float,
            message: str) -> None:
        fired.append({
            "id": identifier,
            "level": level,
            "observed": observed,
            "threshold": threshold,
            "message": message,
        })

    if unlabelled_share > FAIL_MATURED_UNLABELLED_SHARE:
        add("matured_unlabelled_share", "error", unlabelled_share,
            FAIL_MATURED_UNLABELLED_SHARE,
            f"{matured_unlabelled}/{matured} matured episodes carry no H+60 label "
            f"({unlabelled_share:.1%}); outcomes_h60.jsonl is not the episode population")
    elif unlabelled_share > WARN_MATURED_UNLABELLED_SHARE:
        add("matured_unlabelled_share", "warning", unlabelled_share,
            WARN_MATURED_UNLABELLED_SHARE,
            f"{matured_unlabelled}/{matured} matured episodes carry no H+60 label "
            f"({unlabelled_share:.1%}); outcomes_h60.jsonl is not the episode population")

    if dependent_share > FAIL_SOURCE_DEPENDENT_SHARE:
        add("source_dependent_share", "error", dependent_share,
            FAIL_SOURCE_DEPENDENT_SHARE,
            f"{source_dependent}/{matured} matured episodes are source-dependent pending "
            f"({dependent_share:.1%}); the accepted-forever class has outgrown its bound")
    elif dependent_share > WARN_SOURCE_DEPENDENT_SHARE:
        add("source_dependent_share", "warning", dependent_share,
            WARN_SOURCE_DEPENDENT_SHARE,
            f"{source_dependent}/{matured} matured episodes are source-dependent pending "
            f"({dependent_share:.1%}); the accepted-forever class has outgrown its bound")

    if gap_ticker_count > 0:
        add("structural_price_source_gap", "warning", float(gap_ticker_count), 0.0,
            f"{gap_ticker_count} ticker(s) have never produced a complete H+60 label "
            f"({structural_gap} episode(s)); these are outside the intraday price "
            f"universe and no future run of the current lane can resolve them")
    return fired


def build_coverage_census(
    episodes: Sequence[Mapping[str, Any]],
    outcomes: Sequence[Mapping[str, Any]],
    *,
    now: datetime,
    priced_tickers: Iterable[str] | None = None,
    max_tickers: int = MAX_CENSUS_TICKERS,
    max_sessions: int = MAX_CENSUS_SESSIONS,
) -> dict[str, Any]:
    """Census the labelled/unlabelled split and evaluate the declared bounds.

    The returned artifact is bounded: ticker and session breakdowns are capped
    and any truncation is reported explicitly under ``truncated`` rather than
    silently dropped, because a census that quietly elides rows reads as
    "covered everything" when it did not.
    """
    if now.tzinfo is None:
        raise CoverageCensusError("now must be timezone-aware")
    now = now.astimezone(timezone.utc)

    episodes_by_id: dict[str, Mapping[str, Any]] = {}
    for episode in episodes:
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise CoverageCensusError("episode.episode_id must be a non-empty string")
        episodes_by_id[episode_id] = episode

    complete = 0
    terminal_incomplete = 0
    labelled_ids: set[str] = set()
    for row in outcomes:
        episode_id = row.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            raise CoverageCensusError("outcome.episode_id must be a non-empty string")
        labelled_ids.add(episode_id)
        if row.get("status") == "complete":
            complete += 1
        else:
            terminal_incomplete += 1

    labellable = labellable_tickers(outcomes, episodes_by_id)
    priced = set(priced_tickers) if priced_tickers is not None else None
    evidence_mode = "price_source" if priced is not None else "ledger_inference"

    class_counts = {name: 0 for name in UNLABELLED_CLASSES}
    gap_by_ticker: dict[str, int] = {}
    gap_sessions: dict[str, set[str]] = {}
    dependent_by_ticker: dict[str, int] = {}
    unlabelled_by_session: dict[str, int] = {}
    episodes_by_session: dict[str, int] = {}

    for episode_id, episode in episodes_by_id.items():
        session = str(episode.get("session_date") or "")
        episodes_by_session[session] = episodes_by_session.get(session, 0) + 1
        if episode_id in labelled_ids:
            continue
        klass = classify_unlabelled_episode(
            episode, now=now, labellable=labellable, priced_tickers=priced,
        )
        class_counts[klass] += 1
        if klass == IMMATURE_CLASS:
            continue
        ticker = str(episode["ticker"])
        unlabelled_by_session[session] = unlabelled_by_session.get(session, 0) + 1
        if klass == STRUCTURAL_GAP_CLASS:
            gap_by_ticker[ticker] = gap_by_ticker.get(ticker, 0) + 1
            gap_sessions.setdefault(ticker, set()).add(session)
        else:
            dependent_by_ticker[ticker] = dependent_by_ticker.get(ticker, 0) + 1

    total = len(episodes_by_id)
    immature = class_counts[IMMATURE_CLASS]
    structural_gap = class_counts[STRUCTURAL_GAP_CLASS]
    source_dependent = class_counts[SOURCE_DEPENDENT_CLASS]
    matured_unlabelled = structural_gap + source_dependent
    matured = total - immature

    ranked_gap = sorted(gap_by_ticker.items(), key=lambda kv: (-kv[1], kv[0]))
    ranked_dependent = sorted(dependent_by_ticker.items(), key=lambda kv: (-kv[1], kv[0]))
    ranked_sessions = sorted(unlabelled_by_session.items(), key=lambda kv: kv[0])

    census: dict[str, Any] = {
        "schema": CENSUS_SCHEMA,
        "computed_at": _iso(now),
        "evidence_mode": evidence_mode,
        "totals": {
            "episodes": total,
            "labelled": len(labelled_ids & set(episodes_by_id)),
            "labelled_complete": complete,
            "labelled_terminal_incomplete": terminal_incomplete,
            "unlabelled": immature + matured_unlabelled,
            "matured": matured,
            "matured_unlabelled": matured_unlabelled,
        },
        "classes": dict(class_counts),
        "shares": {
            "matured_unlabelled_share": _share(matured_unlabelled, matured),
            "structural_gap_share": _share(structural_gap, matured),
            "source_dependent_share": _share(source_dependent, matured),
        },
        "structural_gap_tickers": [
            {
                "ticker": ticker,
                "episodes": count,
                "sessions": sorted(gap_sessions.get(ticker, ())),
            }
            for ticker, count in ranked_gap[:max_tickers]
        ],
        "source_dependent_tickers": [
            {"ticker": ticker, "episodes": count}
            for ticker, count in ranked_dependent[:max_tickers]
        ],
        "by_session": [
            {
                "session_date": session,
                "episodes": episodes_by_session.get(session, 0),
                "matured_unlabelled": count,
            }
            for session, count in ranked_sessions[:max_sessions]
        ],
        "bounds": {
            "warn_matured_unlabelled_share": WARN_MATURED_UNLABELLED_SHARE,
            "fail_matured_unlabelled_share": FAIL_MATURED_UNLABELLED_SHARE,
            "warn_source_dependent_share": WARN_SOURCE_DEPENDENT_SHARE,
            "fail_source_dependent_share": FAIL_SOURCE_DEPENDENT_SHARE,
            "max_census_tickers": max_tickers,
            "max_census_sessions": max_sessions,
        },
        "truncated": {
            "structural_gap_tickers": max(0, len(ranked_gap) - max_tickers),
            "source_dependent_tickers": max(0, len(ranked_dependent) - max_tickers),
            "by_session": max(0, len(ranked_sessions) - max_sessions),
        },
    }
    census["tripwires"] = _tripwires(
        matured=matured,
        matured_unlabelled=matured_unlabelled,
        source_dependent=source_dependent,
        structural_gap=structural_gap,
        gap_ticker_count=len(gap_by_ticker),
    )
    census["ok"] = not any(item["level"] == "error" for item in census["tripwires"])
    return census
