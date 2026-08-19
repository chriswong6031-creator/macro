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

COMMISSIONING PREP (day-2, LAB-0 §6): :func:`resolve_radar_spool` teaches
this reader the SAME R2-first-else-local backend ladder the Radar spool
WRITER uses, via the one Radar import this package makes at all —
``engine.entry_radar.spool`` (a stdlib/``contracts.py``-only leaf, never the
detector/scoring stack ``live_ledger``/``challengers``/``detectors`` pull in
— see ``RADAR_EVENT_SPOOL_PREFIX`` below for why that constant is restated
rather than imported from ``live_ledger``). This module still runs no
detector formula, reads no forward outcome, and writes no store — the R2
calls are reads only, same as everything else here.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from engine.entry_radar import spool as radar_spool
from engine.prophet_lab.timeparse import earliest_instant_string, parse_instant

log = logging.getLogger("macro.prophet_lab")

ENVELOPE_SCHEMA = "entry_radar.events/v1"
BASELINE_SCHEMA = "prophet_lab.observation_baseline/v1"

#: Radar's own event-spool key PREFIX (``engine.entry_radar.live_ledger.EVENT_SPOOL_PREFIX``),
#: restated as a literal string for the same reason ``_TERMINAL_STATES``/
#: ``_LEDGER_FILE`` below are restated rather than imported: ``live_ledger.py``
#: pulls Radar's challengers/detectors fan-out (~150 unrelated engine files,
#: CI ci-pack-10 finding, 2026-08-19) into the closure of every consumer that
#: reaches it, which this leaf reader must not inherit. ``engine.entry_radar.spool``
#: (imported below, for the R2-first read seam only) is the one Radar module
#: this reader DOES import — it is a stdlib/``contracts.py``-only leaf with
#: none of that fan-out — but ``live_ledger`` itself stays off limits.
#: ``tests/test_prophet_lab.py::test_reader_honors_the_real_event_spool_prefix_shape``
#: cross-checks this literal against the real constant.
RADAR_EVENT_SPOOL_PREFIX = "live_flow/entry_radar_events"


@dataclass(frozen=True)
class SpoolReadResult:
    """Read OUTCOME, not just directory presence (review S4/S7).

    ``configured`` — a root was given at all. ``dir_exists`` — that root is a
    real directory (or, for the R2 backend, that the LIST call itself
    succeeded — see ``backend`` below). ``envelopes`` — the successfully
    parsed ``entry_radar.events/v1`` objects. ``files_seen``/
    ``envelopes_skipped`` — how many candidate files/objects were found vs.
    how many of those (or the envelopes inside a list-shaped file) were
    torn/off-schema and dropped.  A schema drift that silently empties every
    envelope (S7's failure mode) shows up here as ``envelopes_skipped > 0``
    with ``envelopes == []``, rather than as an indistinguishable "nothing to
    read" — the health block surfaces this directly instead of collapsing it
    into ``is_dir()``.

    ``backend`` (day-2 commissioning-prep addition, LAB-0 §6) — which
    transport actually resolved: ``"r2"``, ``"local"``, or ``"unconfigured"``.
    Mirrors the exact ladder the Radar spool WRITER uses
    (``engine.entry_radar.spool.NominationSpool._put``: R2 when credentials
    exist, else a local dir). ``error`` — set when R2 was attempted and the
    LIST call itself failed (a credential/permission/network problem): fail
    CLOSED and VISIBLE, never an empty-board-as-if-clean, per LAB-0 §6's
    explicit requirement. ``error`` can be set even when ``backend=="local"``
    — that is the R2-failed-but-a-local-fallback-succeeded case; the failure
    stays visible in the health block even though a board could still be
    built from the fallback data.
    """

    configured: bool
    dir_exists: bool
    envelopes: list[dict[str, Any]] = field(default_factory=list)
    files_seen: int = 0
    envelopes_skipped: int = 0
    backend: str = "unconfigured"
    error: str | None = None

    @property
    def readable(self) -> bool:
        """True once a real read pass actually happened (not just "dir exists")."""
        return self.dir_exists


# ---------------------------------------------------------------------------
# Radar live output — event spool envelopes
# ---------------------------------------------------------------------------
def _parse_envelope_blob(raw_bytes: bytes) -> tuple[list[dict[str, Any]], int]:
    """Parse one spool object's raw bytes to ``(envelopes, skipped-count)``.

    Shared by the local-dir and R2 readers so the schema/skip discipline
    (S4/S7 — a torn or off-schema object is skipped and counted, never
    repaired or guessed at) is defined exactly once.  Tolerant of a file/
    object holding a JSON array of envelopes, matching the local reader's
    long-standing fixture-friendliness.
    """
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [], 1
    candidates = raw if isinstance(raw, list) else [raw]
    out: list[dict[str, Any]] = []
    bad = 0
    for env in candidates:
        if not isinstance(env, dict) or env.get("schema") != ENVELOPE_SCHEMA:
            bad += 1
            continue
        out.append(env)
    return out, bad


def read_radar_envelopes(spool_dir: Path | str | None) -> SpoolReadResult:
    """Every ``entry_radar.events/v1`` envelope under ``spool_dir``, plus outcome.

    LOCAL-DIR ONLY — always reports ``backend in ("local", "unconfigured")``,
    never ``"r2"``. Mirrors the production local-spool layout (one JSON
    object per file, ``EventSpool``/``NominationSpool`` —
    ``engine/entry_radar/spool.py``), but is tolerant of a fixture file
    holding a JSON array of envelopes too. Use :func:`resolve_radar_spool`
    for the full R2-first-else-local backend ladder; this function stays the
    pure, dependency-free local reader it always was (every existing
    fixture/unit test targets it directly).
    """
    if spool_dir is None:
        return SpoolReadResult(configured=False, dir_exists=False, backend="unconfigured")
    root = Path(spool_dir)
    if not root.is_dir():
        return SpoolReadResult(configured=True, dir_exists=False, backend="local")
    out: list[dict[str, Any]] = []
    bad = 0
    files_seen = 0
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        files_seen += 1
        try:
            raw_bytes = path.read_bytes()
        except OSError:
            bad += 1
            continue
        envs, skipped = _parse_envelope_blob(raw_bytes)
        out.extend(envs)
        bad += skipped
    if bad:
        log.warning(
            "prophet_lab: %d spool object(s) under %s unreadable or off-schema (skipped)",
            bad, root,
        )
    return SpoolReadResult(
        configured=True, dir_exists=True, envelopes=out,
        files_seen=files_seen, envelopes_skipped=bad, backend="local",
    )


def _read_radar_envelopes_from_r2(
    s3: Any, prefix: str, *, bucket: str | None = None,
) -> SpoolReadResult:
    """R2 backend read: list every object under ``prefix``, parse each.

    Fail-CLOSED and VISIBLE (LAB-0 §6): a LIST failure (credential,
    permission, or network) is never swallowed into an empty-and-clean
    result — it comes back as ``dir_exists=False`` with a named ``.error``,
    the same visible-not-silent discipline ``read_observation_baseline``
    already uses (``BaselineReadResult.error``). A per-OBJECT GET failure is
    a smaller, more ordinary event (matches a torn local file) and is simply
    counted in ``envelopes_skipped`` — if EVERY object fails to GET, that
    already surfaces as ``envelopes_skipped > 0`` with ``envelopes == []``
    (S7's existing visibility guarantee), so a second special case is not
    needed for that path.
    """
    try:
        keys = radar_spool.list_r2_keys(s3, prefix, bucket=bucket)
    except Exception as exc:  # noqa: BLE001 — must surface, never raise into the API's 500 path
        log.warning(
            "prophet_lab: R2 spool list under %s failed (%s: %s)",
            prefix, type(exc).__name__, exc,
        )
        return SpoolReadResult(
            configured=True, dir_exists=False, backend="r2",
            error=f"r2_list_failed: {type(exc).__name__}: {exc}",
        )
    out: list[dict[str, Any]] = []
    bad = 0
    files_seen = 0
    for key in sorted(keys):
        files_seen += 1
        try:
            blob = radar_spool.get_r2_object_bytes(s3, key, bucket=bucket)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "prophet_lab: R2 spool object %s unreadable (%s: %s)",
                key, type(exc).__name__, exc,
            )
            bad += 1
            continue
        envs, skipped = _parse_envelope_blob(blob)
        out.extend(envs)
        bad += skipped
    if bad:
        log.warning(
            "prophet_lab: %d R2 spool object(s) under %s unreadable or off-schema (skipped)",
            bad, prefix,
        )
    return SpoolReadResult(
        configured=True, dir_exists=True, envelopes=out,
        files_seen=files_seen, envelopes_skipped=bad, backend="r2",
    )


def resolve_radar_spool(
    local_dir: Path | str | None,
    *,
    s3: Any = None,
    prefix: str = RADAR_EVENT_SPOOL_PREFIX,
) -> SpoolReadResult:
    """R2-first backend resolution — the SAME ladder the Radar spool WRITER
    uses (``engine.entry_radar.spool.NominationSpool._put``: R2 when
    credentials exist, else a local directory), never a second, divergent
    one (LAB-0 §6, day-2 commissioning prep).

    ``s3`` is injectable (tests supply a fake client, same convention as
    ``NominationSpool(s3=...)`` in ``tests/test_entry_radar_w4_lane.py``);
    production leaves it ``None`` and this function resolves the real R2
    client itself via :func:`engine.entry_radar.spool.r2_client_for_read`
    ONLY when :func:`engine.entry_radar.spool.r2_credentials_present`
    (never builds a client just to find out credentials are absent).

    Ladder:

    1. R2 credentials present (or an ``s3`` object is injected) -> read R2.
       On success, ``backend="r2"``. On a LIST failure, fail closed: if a
       local dir is ALSO configured, fall back to it (mirroring the
       writer's own R2-then-local behavior) but keep the R2 failure VISIBLE
       via ``.error`` even though the fallback succeeded; with no local dir
       configured, return the R2 failure directly (``backend="r2"``,
       ``dir_exists=False``, ``.error`` set) — never silently empty.
    2. No R2 (no credentials, no injected client) -> :func:`read_radar_envelopes`
       against ``local_dir`` (``backend in ("local", "unconfigured")``).
    """
    client = s3
    if client is None and radar_spool.r2_credentials_present():
        client = radar_spool.r2_client_for_read()
    if client is not None:
        result = _read_radar_envelopes_from_r2(client, prefix)
        if result.error and local_dir is not None:
            fallback = read_radar_envelopes(local_dir)
            return replace(fallback, backend="local", error=result.error)
        return result
    return read_radar_envelopes(local_dir)


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

    Temporal correctness amendment (day-2 reconciliation): "earliest" is
    decided by parsed INSTANT (:func:`engine.prophet_lab.timeparse.parse_instant`),
    never by comparing the ``pass_ts`` strings directly — see
    ``timeparse.py``'s module docstring for the measured lexicographic-compare
    failure this replaces. An envelope whose ``pass_ts`` does not parse to a
    tz-aware instant can never win "earliest" for an event_id; if EVERY
    envelope carrying an event_id is unparseable, that event_id is simply
    absent from ``first_observed_at`` (the same outcome as never having been
    observed at all — the caller's existing "no known first observation"
    branch already handles that honestly).
    """
    events_by_id: dict[str, dict[str, Any]] = {}
    first_observed: dict[str, str] = {}
    first_observed_instant: dict[str, Any] = {}
    for env in envelopes:
        pass_ts = str(env.get("pass_ts") or "").strip()
        pass_instant = parse_instant(pass_ts) if pass_ts else None
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
            if pass_instant is None:
                continue
            current = first_observed_instant.get(event_id)
            if current is None or pass_instant < current:
                first_observed_instant[event_id] = pass_instant
                first_observed[event_id] = pass_ts
    return list(events_by_id.values()), first_observed


def earliest_pass_ts(envelopes: Iterable[Mapping[str, Any]]) -> str | None:
    """The ORIGINAL ``pass_ts`` string whose parsed INSTANT is earliest.

    ``None`` when no envelope carries a parseable ``pass_ts``. Temporal
    correctness amendment: this used to be ``min()`` over the raw strings,
    which is only correct when every string shares the same UTC-offset
    notation — see ``timeparse.py``'s module docstring. Wired through
    :func:`engine.prophet_lab.timeparse.earliest_instant_string` (review
    round 2, N1) rather than re-implementing the same "earliest by parsed
    instant" scan a second time in this module.
    """
    raw_stamps = (str(env.get("pass_ts") or "").strip() for env in envelopes)
    return earliest_instant_string(raw for raw in raw_stamps if raw)


def latest_envelope(envelopes: Iterable[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The envelope whose ``pass_ts`` parses to the greatest INSTANT.

    Ties keep the LAST envelope encountered at that instant (preserves the
    prior ``>=`` tie-break direction). An envelope with an unparseable
    ``pass_ts`` can never be "latest" — it is skipped, never favored by a
    lexicographic accident. ``None`` when no envelope parses at all.
    """
    best: Mapping[str, Any] | None = None
    best_instant: Any = None
    for env in envelopes:
        raw = str(env.get("pass_ts") or "").strip()
        instant = parse_instant(raw) if raw else None
        if instant is None:
            continue
        if best_instant is None or instant >= best_instant:
            best_instant = instant
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

    Temporal correctness amendment: the "at or before" comparison is now an
    INSTANT comparison via :func:`engine.prophet_lab.timeparse.parse_instant`,
    never a raw string compare (see ``timeparse.py``'s module docstring for
    the measured failure mode). An unparseable or naive ``baseline_started_at``
    fails CLOSED (``False``) — the same fail-honest default as a missing one.
    """
    if not baseline:
        return False
    started = parse_instant(baseline.get("baseline_started_at"))
    if started is None:
        return False
    earliest = earliest_pass_ts(envelopes)
    earliest_instant = parse_instant(earliest) if earliest else None
    if earliest_instant is None:
        return False
    return earliest_instant <= started


# ---------------------------------------------------------------------------
# Radar live output — episode ledger (nonterminal state, C1 board)
# ---------------------------------------------------------------------------
#: §13's three TERMINAL states verbatim (``engine.entry_radar.detectors.TERMINAL_STATES``),
#: restated as plain strings rather than imported. This module reads exactly
#: three fields off an episode record (``detector_id``, ``ticker``, ``state``)
#: to answer one question — "is this unit's CURRENT episode nonterminal" — and
#: does not need the full ``LiveEpisode`` dataclass, its §13 validation
#: machinery, or the Radar detector stack that machinery transitively pulls
#: in to answer it. Measured: importing ``engine.entry_radar.live_ledger`` for
#: this alone pulled ~150 unrelated engine/*.py files into the closure of
#: every consumer that reaches this module (CI ci-pack-10 finding, 2026-08-19)
#: — Radar's OWN pre-existing internal fan-out (challengers/detectors reach
#: the US board/stock-scoring engine subsystem), not anything this package
#: needs. Reading the three fields directly keeps the Lab's own promise
#: (LAB-0 §1: a projection layer, never a second detector stack) honest at
#: the IMPORT level, not just the call level.
_TERMINAL_STATES = frozenset({"INVALIDATED", "EXPIRED", "RESOLVED"})

#: The runtime ledger's own file name (``engine.entry_radar.live_ledger._LEDGER_FILE``),
#: restated for the same reason as ``_TERMINAL_STATES`` above.
_LEDGER_FILE = "episodes.json"


@dataclass(frozen=True)
class EpisodeSummary:
    """The three fields this package reads off one ``LiveEpisode`` record."""

    episode_id: str
    ticker: str
    detector_id: str
    state: str

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES


@dataclass(frozen=True)
class EpisodeReadResult:
    """S5: lets a board tell "genuinely empty" apart from "unavailable"."""

    configured: bool
    available: bool
    episodes: list[EpisodeSummary] = field(default_factory=list)
    reason: str | None = None


def read_live_episodes(state_dir: Path | str | None) -> EpisodeReadResult:
    """Episode summaries from the injected runtime state dir, plus outcome.

    Reads ``episodes.json`` directly (the exact file
    ``engine.entry_radar.live_ledger.LiveEpisodeLedger.save()`` writes) rather
    than going through that class — see ``_TERMINAL_STATES`` above for why. A
    torn or off-shape record is skipped, never guessed at, mirroring the house
    discipline elsewhere in this package. ``available=False`` (with a named
    ``reason``) covers "no state dir configured", "state dir present but
    unreadable", and "the file does not parse" — a caller (the C1 board, and
    the C1 component of the union board) must show "unavailable", never
    silently render as "nothing nonterminal today".
    """
    if state_dir is None:
        return EpisodeReadResult(configured=False, available=False, reason="not_configured")
    root = Path(state_dir)
    if not root.is_dir():
        return EpisodeReadResult(configured=True, available=False, reason="state_dir_absent")
    path = root / _LEDGER_FILE
    if not path.is_file():
        # No episodes recorded yet is a legitimate, available, empty ledger —
        # distinct from a missing/misconfigured state_dir.
        return EpisodeReadResult(configured=True, available=True, episodes=[])
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("prophet_lab: live episode ledger at %s unreadable (%s)", path, exc)
        return EpisodeReadResult(configured=True, available=False, reason="unreadable")
    if not isinstance(raw, dict):
        log.warning("prophet_lab: live episode ledger at %s is not an object", path)
        return EpisodeReadResult(configured=True, available=False, reason="unreadable")
    episodes: list[EpisodeSummary] = []
    for row in raw.get("episodes") or ():
        if not isinstance(row, Mapping):
            continue
        episode_id = str(row.get("episode_id") or "").strip()
        ticker = str(row.get("ticker") or "").strip()
        detector_id = str(row.get("detector_id") or "").strip()
        state = str(row.get("state") or "").strip()
        if not (episode_id and ticker and detector_id and state):
            continue
        episodes.append(EpisodeSummary(
            episode_id=episode_id, ticker=ticker, detector_id=detector_id, state=state,
        ))
    return EpisodeReadResult(configured=True, available=True, episodes=episodes)


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


@dataclass(frozen=True)
class BaselineReadResult:
    """Review round 2, S4: distinguishes a MALFORMED marker from a genuinely
    ABSENT one. Both used to collapse into the same ``None`` — a health-block
    consumer could not tell "the operator has not provisioned a baseline yet"
    apart from "one exists but is broken" (e.g. a naive/unparseable
    ``baseline_started_at``), which matters because the second case is an
    operator error worth surfacing by name, not silent absence.
    """

    baseline: dict[str, Any] | None
    error: str | None = None


def read_observation_baseline(baseline_path: Path | str | None) -> BaselineReadResult:
    """The observation-baseline marker (LAB-0 §4), plus a named failure reason.

    Absence is not an error — it is the honest starting state: with no
    baseline, EVERY event is ``retrospective_seed`` (fail-honest); a call with
    no configured path (or nothing on disk) returns ``BaselineReadResult(None)``
    with no ``error`` at all. A PRESENT-but-broken file rejects to ``baseline=
    None`` the same as before (the fail-closed DIRECTION is unchanged) but now
    also names WHY via ``.error``:

    * ``schema_not_an_object`` — the JSON parsed but isn't a ``{...}``.
    * ``unreadable_or_invalid_json`` — the file could not be read or parsed.
    * ``schema_mismatch`` — ``schema`` is missing or not ``BASELINE_SCHEMA``
      (review N2 — an unrecognised schema is rejected, not trusted blind).
    * ``missing_baseline_started_at`` — the required field is absent/blank.
    * ``naive_or_unparseable_started_at`` (review round 2, S4) — the field is
      present but does not parse to a tz-aware instant via
      :func:`engine.prophet_lab.timeparse.parse_instant` — validated HERE, at
      read time, rather than only failing later inside every comparison that
      happens to touch it, so a malformed marker is distinguishable from a
      genuine spool-coverage gap in the health block
      (``observation_baseline_error``) instead of both reading as an
      unexplained "not verified".

    ``continuous_through`` (optional) is NOT read-time validated here — an
    unparseable value there already fails closed correctly inside
    ``observation.classify_observation`` itself (a present-but-broken upper
    bound must reject, never silently act as "no upper bound"), and that
    per-event check is the more precise place to name it.
    """
    if baseline_path is None:
        return BaselineReadResult(baseline=None)
    path = Path(baseline_path)
    if not path.is_file():
        return BaselineReadResult(baseline=None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("prophet_lab: observation baseline at %s unreadable (%s)", path, exc)
        return BaselineReadResult(baseline=None, error="unreadable_or_invalid_json")
    if not isinstance(raw, dict):
        return BaselineReadResult(baseline=None, error="schema_not_an_object")
    if str(raw.get("schema") or "") != BASELINE_SCHEMA:
        log.warning(
            "prophet_lab: observation baseline at %s carries schema %r (expected %r) — "
            "rejected, not trusted blind",
            path, raw.get("schema"), BASELINE_SCHEMA,
        )
        return BaselineReadResult(baseline=None, error="schema_mismatch")
    started_at = raw.get("baseline_started_at")
    if not str(started_at or "").strip():
        log.warning("prophet_lab: observation baseline at %s missing baseline_started_at", path)
        return BaselineReadResult(baseline=None, error="missing_baseline_started_at")
    if parse_instant(started_at) is None:
        log.warning(
            "prophet_lab: observation baseline at %s carries a naive or unparseable "
            "baseline_started_at (%r) — rejected, fail closed",
            path, started_at,
        )
        return BaselineReadResult(baseline=None, error="naive_or_unparseable_started_at")
    return BaselineReadResult(baseline=raw)


__all__ = [
    "ENVELOPE_SCHEMA",
    "BASELINE_SCHEMA",
    "RADAR_EVENT_SPOOL_PREFIX",
    "SpoolReadResult",
    "EpisodeReadResult",
    "EpisodeSummary",
    "BaselineReadResult",
    "read_radar_envelopes",
    "resolve_radar_spool",
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
