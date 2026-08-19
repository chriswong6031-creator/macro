"""engine/prophet_lab/sources.py — injectable-root readers for the Lab.

Every reader here takes its root as an explicit argument (a directory or file
path) so the whole projection is offline-testable against fixtures — no
reader resolves a production path by itself, and none of them import the
Radar detector/scoring stack.  This is the READ half of LAB-0 §1: filter,
join, decorate — never compute a detector formula, never read a forward
outcome, never write a store.

Radar envelope reading is a DELIBERATE REIMPLEMENTATION, not a reuse, of
``scripts/reconcile_entry_radar.py::read_spool_events``: that reader expects a
flat ``mastermind.entry_event.v1`` record per file, which is the exact W4
transport mismatch LAB-0 §6 R-LAB-1 is fixing (a sibling PR, files this
worktree may not touch).  :func:`read_radar_envelopes` reads the real
``entry_radar.events/v1`` ENVELOPE shape (``schema``/``pass_ts``/``events[]``)
that :func:`engine.entry_radar.live_ledger.build_event_payload` actually
writes, so the Lab does not inherit the bug and does not wait on its fix.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

log = logging.getLogger("macro.prophet_lab")

ENVELOPE_SCHEMA = "entry_radar.events/v1"
BASELINE_SCHEMA = "prophet_lab.observation_baseline/v1"


@dataclass(frozen=True)
class SpoolReadResult:
    """Read OUTCOME, not just directory presence (review S4/S7).

    ``configured`` — a root was given at all. ``dir_exists`` — that root is a
    real directory. ``envelopes`` — the successfully parsed
    ``entry_radar.events/v1`` objects. ``files_seen``/``envelopes_skipped`` —
    how many candidate files were found vs. how many of those (or the
    envelopes inside a list-shaped file) were torn/off-schema and dropped.  A
    schema drift that silently empties every envelope (S7's failure mode)
    shows up here as ``envelopes_skipped > 0`` with ``envelopes == []``,
    rather than as an indistinguishable "nothing to read" — the health block
    surfaces this directly instead of collapsing it into ``is_dir()``.
    """

    configured: bool
    dir_exists: bool
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    files_seen: int = 0
    envelopes_skipped: int = 0

    @property
    def readable(self) -> bool:
        """True once a real read pass actually happened (not just "dir exists")."""
        return self.dir_exists


# ---------------------------------------------------------------------------
# Radar live output — event spool envelopes
# ---------------------------------------------------------------------------
def read_radar_envelopes(spool_dir: Path | str | None) -> SpoolReadResult:
    """Every ``entry_radar.events/v1`` envelope under ``spool_dir``, plus outcome.

    Mirrors the production local-spool layout (one JSON object per file,
    ``EventSpool``/``NominationSpool`` — ``engine/entry_radar/spool.py``), but
    is tolerant of a fixture file holding a JSON array of envelopes too.  A
    torn or off-schema file (or list entry) is skipped and counted, never
    repaired or guessed at (house discipline,
    ``reconcile_entry_radar.read_spool_events``).
    """
    if spool_dir is None:
        return SpoolReadResult(configured=False, dir_exists=False)
    root = Path(spool_dir)
    if not root.is_dir():
        return SpoolReadResult(configured=True, dir_exists=False)
    out: list[dict[str, Any]] = []
    bad = 0
    files_seen = 0
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        files_seen += 1
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            bad += 1
            continue
        candidates = raw if isinstance(raw, list) else [raw]
        for env in candidates:
            if not isinstance(env, dict) or env.get("schema") != ENVELOPE_SCHEMA:
                bad += 1
                continue
            out.append(env)
    if bad:
        log.warning(
            "prophet_lab: %d spool object(s) under %s unreadable or off-schema (skipped)",
            bad, root,
        )
    return SpoolReadResult(
        configured=True, dir_exists=True, envelopes=out,
        files_seen=files_seen, envelopes_skipped=bad,
    )


def extract_events(
    envelopes: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Flatten envelope ``events[]`` into ``(deduped events, first_observed_at)``.

    ``first_observed_at[event_id]`` is the EARLIEST envelope ``pass_ts`` that
    carried that ``event_id`` (LAB-0 §4) — the only place "first observation"
    is derived.  The immutable ``mastermind.entry_event.v1`` record itself is
    never mutated to carry this transport fact; it is always read verbatim
    from whichever envelope is encountered (duplicates across passes must be
    byte-identical content for the same address per the append-only store —
    this reader does not re-validate that, it trusts the spool).
    """
    events_by_id: dict[str, dict[str, Any]] = {}
    first_observed: dict[str, str] = {}
    for env in envelopes:
        pass_ts = str(env.get("pass_ts") or "").strip()
        events = env.get("events")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, Mapping):
                continue
            event_id = str(event.get("event_id") or "").strip()
            if not event_id:
                continue
            events_by_id.setdefault(event_id, dict(event))
            if pass_ts and (
                event_id not in first_observed or pass_ts < first_observed[event_id]
            ):
                first_observed[event_id] = pass_ts
    return list(events_by_id.values()), first_observed


def earliest_pass_ts(envelopes: Iterable[Mapping[str, Any]]) -> str | None:
    """The earliest envelope ``pass_ts`` in the set, or ``None`` when empty."""
    stamps = [str(env.get("pass_ts") or "").strip() for env in envelopes]
    stamps = [s for s in stamps if s]
    return min(stamps) if stamps else None


def latest_envelope(envelopes: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The envelope with the greatest ``pass_ts`` (ties broken arbitrarily)."""
    best: Mapping[str, Any] | None = None
    best_ts = ""
    for env in envelopes:
        ts = str(env.get("pass_ts") or "").strip()
        if ts and ts >= best_ts:
            best_ts = ts
            best = env
    return best


def baseline_coverage_verified(
    envelopes: Iterable[Mapping[str, Any]], baseline: Mapping[str, Any] | None,
) -> bool:
    """S1, fail CLOSED: does the spool actually reach back to the baseline start?

    ``True`` only when a baseline exists, at least one envelope was read, AND
    the earliest surviving envelope's ``pass_ts`` is AT OR BEFORE
    ``baseline_started_at`` — i.e. there is no gap between "the operator says
    continuous coverage began here" and "the oldest evidence we can actually
    see". A spool that has aged out past the baseline start (retention,
    compaction, an empty/misconfigured root) POSTDATES the claimed start and
    fails this check, which the caller (``response.py``) turns into "treat
    the baseline as absent" — every row falls back to ``retrospective_seed``,
    never a false ``live_forward`` built on an unverifiable window.
    """
    if not baseline:
        return False
    started_at = str(baseline.get("baseline_started_at") or "")
    if not started_at:
        return False
    earliest = earliest_pass_ts(envelopes)
    if earliest is None:
        return False
    return earliest <= started_at


# ---------------------------------------------------------------------------
# Radar live output — episode ledger (nonterminal state, C1 board)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class EpisodeReadResult:
    """S5: lets a board tell "genuinely empty" apart from "unavailable"."""

    configured: bool
    available: bool
    episodes: list[Any] = field(default_factory=list)
    reason: str | None = None


def read_live_episodes(state_dir: Path | str | None) -> EpisodeReadResult:
    """``LiveEpisode`` records from the injected runtime state dir, plus outcome.

    Reuses ``engine.entry_radar.live_ledger.LiveEpisodeLedger`` — the
    canonical reader — rather than re-parsing ``episodes.json`` by hand.
    Imported lazily so a Lab test that never exercises this path does not pay
    for the full Radar detector stack import. ``available=False`` (with a
    named ``reason``) covers both "no state dir configured" and "state dir
    present but unreadable" — a caller (the C1 board, and the C1 component of
    the union board) must show "unavailable", never silently render as
    "nothing nonterminal today" (docstring promise this dataclass now makes
    structural rather than merely stated).
    """
    if state_dir is None:
        return EpisodeReadResult(configured=False, available=False, reason="not_configured")
    root = Path(state_dir)
    if not root.is_dir():
        return EpisodeReadResult(configured=True, available=False, reason="state_dir_absent")
    try:
        from engine.entry_radar.live_ledger import LiveEpisodeLedger  # noqa: PLC0415

        ledger = LiveEpisodeLedger.load(root)
        return EpisodeReadResult(configured=True, available=True, episodes=list(ledger.episodes))
    except Exception as exc:  # noqa: BLE001 — a bad state dir must not break the Lab
        log.warning("prophet_lab: live episode ledger at %s unreadable (%s)", root, exc)
        return EpisodeReadResult(configured=True, available=False, reason="unreadable")


# ---------------------------------------------------------------------------
# Prophet plan/index data
# ---------------------------------------------------------------------------
def read_prophet_index(index_path: Path | str | None) -> dict[str, Any]:
    """``site/prophet/index.json``-shaped dict, or ``{}`` when unreadable.

    Read-only, single artifact.  This module never writes to
    ``INDEX_PATH`` or any other Prophet store — the Lab has zero
    plan-origination/mutation authority (LAB-0 §1).
    """
    if index_path is None:
        return {}
    path = Path(index_path)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("prophet_lab: prophet index at %s unreadable (%s)", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def index_plans_by_ticker(index: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Group ``index["plans"]`` rows by ticker (``asset``), most-recent first.

    Ordering key mirrors ``scripts/build_prophet.py``'s own precedence for a
    "which plan is current" read: ``entry_date`` then ``signal_date`` then
    ``recorded_at``, all falling back to empty string (never guessed). Rows
    include BOTH open and closed plans — every plan the index published — so
    a caller (``boards._prophet_comparison``, review B1) can distinguish
    "currently active" from "closed" itself; this function does not decide
    that, it only orders.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    plans = index.get("plans")
    if not isinstance(plans, list):
        return out
    for plan in plans:
        if not isinstance(plan, Mapping):
            continue
        ticker = str(plan.get("asset") or plan.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        out.setdefault(ticker, []).append(dict(plan))
    for ticker, rows in out.items():
        rows.sort(
            key=lambda row: (
                str(row.get("entry_date") or ""),
                str(row.get("signal_date") or ""),
                str(row.get("recorded_at") or ""),
            ),
            reverse=True,
        )
    return out


# ---------------------------------------------------------------------------
# Ticker enrichment — reuse the existing Prophet board-read source, never a
# second one (LAB-0 §5: "existing board-read/stock-library enrichment").
# ---------------------------------------------------------------------------
def build_enrichment_library(library_root: Path | str | None) -> Any:
    """A ``LibraryIndex`` over ``library_root``, or ``None`` when not given.

    ``engine.prophet_board_read.LibraryIndex`` is the exact reader
    ``scripts/build_prophet.py`` already uses to join name/sector/spark onto
    every plan row.  Imported lazily to avoid a hard dependency on it for
    callers that never enrich (e.g. a fixture that supplies enrichment
    directly).  A caller with no reachable root gets ``None`` back — its
    ``.available`` is False either way, so every field resolves BLOCKED_DATA
    rather than raising.
    """
    if library_root is None:
        return None
    from engine.prophet_board_read import LibraryIndex  # noqa: PLC0415

    return LibraryIndex(library_root)


def read_observation_baseline(baseline_path: Path | str | None) -> dict[str, Any] | None:
    """The observation-baseline marker (LAB-0 §4), or ``None`` when absent/invalid.

    Absence is not an error — it is the honest starting state: with no
    baseline, EVERY event is ``retrospective_seed`` (fail-honest). A present
    file must declare ``schema == BASELINE_SCHEMA`` (review N2 — an
    unrecognised or missing schema is rejected rather than trusted blind) and
    carry ``baseline_started_at``; ``continuous_through`` is optional and,
    when given, bounds how far forward the "continuous coverage" claim is
    trusted — an event first observed after ``continuous_through`` cannot yet
    be certified live_forward either.
    """
    if baseline_path is None:
        return None
    path = Path(baseline_path)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("prophet_lab: observation baseline at %s unreadable (%s)", path, exc)
        return None
    if not isinstance(raw, dict):
        return None
    if str(raw.get("schema") or "") != BASELINE_SCHEMA:
        log.warning(
            "prophet_lab: observation baseline at %s carries schema %r (expected %r) — "
            "rejected, not trusted blind",
            path, raw.get("schema"), BASELINE_SCHEMA,
        )
        return None
    if not str(raw.get("baseline_started_at") or "").strip():
        log.warning("prophet_lab: observation baseline at %s missing baseline_started_at", path)
        return None
    return raw


__all__ = [
    "ENVELOPE_SCHEMA",
    "BASELINE_SCHEMA",
    "SpoolReadResult",
    "EpisodeReadResult",
    "read_radar_envelopes",
    "extract_events",
    "earliest_pass_ts",
    "latest_envelope",
    "baseline_coverage_verified",
    "read_live_episodes",
    "read_prophet_index",
    "index_plans_by_ticker",
    "build_enrichment_library",
    "read_observation_baseline",
]
