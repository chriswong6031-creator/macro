"""Intelligence OS operator panel — Eval OS T1/T4/T7/T8, derived on demand.

WHAT THIS SURFACE IS. One row per intelligence ENGINE (the T1 unit of account: a
``producer::owner_program`` cell), carrying the adjudicated ``output_class`` and
``authority`` T1 assigned it, plus the worst OUTPUT HEALTH state T4 resolved across the
engine's artifacts. Drilling into an engine shows the full ``mastermind.output_health.v1``
record for each of its outputs — which plane decided the state, against which watermark,
with which reason codes. A1 adds one derived evidence disposition per engine and the five
global CEO bands, carrying T1 owner lifecycle/semantics, T4 trust, and qledger evidence only
where an existing owner binding resolves.

WHAT IT IS NOT. There is no numeric evidence score, performance rank, weight, size,
promotion service or gate here. ``output_class`` is read from T1 and is ``null`` wherever no
adjudication exists. A guessed class would be an authority claim wearing a census's clothes,
so the null is rendered as a null. Qledger readiness is measurement evidence only; the
existing species/prereg/gauntlet owners remain the sole source of validation authority.

NOTHING IS EVER WRITTEN. Not a cache file, not a snapshot, not a "last known good".
The whole view is re-derived from ``config/synapse.yml``, the T1 overlay and the estate
itself, and lives only in this process's memory (:data:`_CACHE`) for :data:`_TTL_S`
seconds. There is no stable input to pin a committed health artifact against — the
registry alone took 69 commits in a trailing fortnight — so a persisted copy would be a
second source of truth that goes wrong quietly. Same law as the T4 CLI it calls.

REFLECTIVITY. Nothing about the estate is enumerated here. Engines, artifacts, classes
and authorities all arrive from the derivation; an engine added to ``synapse.yml``
tonight appears on this page tomorrow with no edit to this file, and one removed
disappears. The only hand-written vocabulary is the state ORDER
(:data:`STATE_SEVERITY`), which is the T4 precedence ladder, not a fact about the estate.

``trust_mtime`` IS ALWAYS FALSE HERE, AND THE DEPLOYED PLANE IS THE REASON, NOT THE
EXCEPTION. A file's mtime is freshness evidence only where the PRODUCER is the sole
writer of that file, and on the VPS it is not: ``app/deploy/update.sh`` deploys with
``git fetch && git reset --hard``, so every file git rewrites is stamped with the PULL
time. A deploy or a rollback would therefore restamp the tree and make the 63 artifacts
that declare an SLA but no watermark read "fresh" — an entire class of frozen stores
reporting current because somebody deployed. The developer-checkout hazard is the same
shape (``git status`` sweeps, Finder visits and ``reflog expire`` restamp mtimes,
measured across the fleet pinning 137 of 143 DEAD worktrees as "fresh"), which is why
this panel admits write-time evidence on NO plane. Those artifacts stay
``could_not_look``/``partial`` with ``write_time_untrusted`` — the honest answer, and a
standing argument for declaring a watermark rather than for trusting a clock nobody
controls. The T4 CLI keeps ``--trust-mtime`` for an operator on a plane whose mtimes
really are producer-owned; nothing in this module can set it.
"""
from __future__ import annotations

import math
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from admin.evidence_status import (
    EVIDENCE_STATUS_ORDER,
    build_ceo_view,
    derive_evidence_status,
    qledger_family_for_cell,
)

_ROOT = Path(__file__).resolve().parent.parent

#: The two declared inputs whose change should invalidate a cached view: the artifact
#: census and the adjudication overlay. Mirrors scripts/build_intelligence_registry.py.
_SYNAPSE_REL = Path("config") / "synapse.yml"
_OVERLAY_REL = Path("config") / "intelligence_registry_overlay.yml"
_QUAL_LADDER_REL = Path("config") / "qual_ladder.yml"
_SPECIES_REL = Path("data") / "species" / "registry.json"
_ARTICLE2_REL = Path("scripts") / "check_synapse_reads.py"

# Existing qledger owner stores whose movement changes A1 evidence. These are cache inputs,
# not a copied store: the payload still comes from the owner read APIs below.
_QLEDGER_CLAIMS_REL = Path("data") / "qledger" / "claims.jsonl"
_QLEDGER_GRADES_REL = Path("data") / "qledger" / "grades.jsonl"
_QLEDGER_CLOCK_DIR_REL = Path("data") / "qledger" / "evidence_clock_start"
_QLEDGER_CONTROL_CLOCK_DIR_REL = Path("data") / "qledger" / "control_evidence_clock_start"

#: Seconds a derived view is served before it is re-derived. The estate moves on a
#: nightly cadence, so this is about not re-walking 642 artifacts for every click, not
#: about hiding a change: the mtime keys below evict the moment either input is edited.
_TTL_S = 300.0

#: The T4 precedence ladder, worst first — NOT an opinion about severity, but the order
#: engine/output_health.py resolves in (§7): a missing output outranks a stale one,
#: which outranks a degraded one. ``null`` is last because "we could not determine it"
#: is not a health verdict at all and must never outrank one that is.
STATE_SEVERITY: tuple[str | None, ...] = (
    "unavailable",
    "stale",
    "degraded",
    "healthy",
    None,
)

#: The bucket for artifacts that are in synapse but in no T1 engine cell (T1 exclusions —
#: hand-maintained files, placeholder producers). They are NEVER dropped: an artifact
#: nobody owns is exactly the kind of thing an operator census exists to surface, and a
#: silent omission would make the page's own count a lie. Engine ids are
#: ``producer::owner_program``, so this parenthesized label cannot collide with one.
UNREGISTERED_ENGINE_ID = "(no engine cell)"

# --- in-process cache --------------------------------------------------------
#: key -> (stored_at_monotonic, view, registry, evidence_by_engine). Memory only.
_CACHE: dict[tuple, tuple[float, dict, dict, dict]] = {}
#: One derivation at a time. The T4 builder warms module-level read caches, so two
#: concurrent builds would interleave two snapshots into one answer — and the admin
#: server is threaded.
_LOCK = threading.RLock()


class EstateUnavailable(RuntimeError):
    """The estate could not be derived — raised where the failure can still be NAMED.

    Both underlying failures exit the process by design: the T1 builder raises
    ``scripts.build_intelligence_registry.SynapseUnavailable`` (a ``SystemExit``
    SUBCLASS) and the T4 builder raises a plain ``SystemExit`` when
    ``config/synapse.yml`` is unreadable. That is right for a CLI and wrong for a request
    handler, so :func:`_derive` converts both into this ordinary exception at the one
    place that knows which is which — and the entry points below fail open on a plain
    ``except Exception`` instead of a blanket ``except SystemExit`` that would also
    swallow a deliberate interpreter shutdown.
    """


def _mtime_ns(path: Path) -> int | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def _trust_mtime() -> bool:
    """ALWAYS False on the admin plane — a deployed mtime is a git-transport clock.

    Not an environment question: ``app/deploy/update.sh`` updates the VPS with
    ``git reset --hard``, so a deployed file's mtime is when the pull touched it. See the
    module docstring; the operator opt-in lives on the T4 CLI's ``--trust-mtime``.
    """
    return False


def _receipt_tree_mtime_key(path: Path) -> tuple[tuple[str, int, int], ...] | None:
    """Names, mtimes and sizes for existing owner receipt files under *path*.

    A directory mtime changes when a receipt is added or removed, but not when an
    existing receipt's bytes change in place.  The cache must see both operations.
    """
    if not path.exists():
        return None
    rows: list[tuple[str, int, int]] = []
    for child in sorted(path.rglob("*")):
        if child.is_file():
            stat = child.stat()
            rows.append((child.relative_to(path).as_posix(), stat.st_mtime_ns, stat.st_size))
    return tuple(rows)


def _evidence_mtime_key(root: Path) -> tuple[Any, ...]:
    """Owner-store facts that invalidate the in-process A1 projection."""
    return (
        _mtime_ns(root / _QLEDGER_CLAIMS_REL),
        _mtime_ns(root / _QLEDGER_GRADES_REL),
        _receipt_tree_mtime_key(root / _QLEDGER_CLOCK_DIR_REL),
        _receipt_tree_mtime_key(root / _QLEDGER_CONTROL_CLOCK_DIR_REL),
    )


def _synapse_dependency_mtime_key(root: Path) -> tuple[Any, ...] | None:
    """Mutable repo paths whose identity T1 derives from the Synapse document."""
    try:
        import yaml  # noqa: PLC0415 — only loaded when the panel is actually derived

        document = yaml.safe_load((root / _SYNAPSE_REL).read_text(encoding="utf-8"))
        artifacts = document.get("artifacts") if isinstance(document, dict) else None
    except (OSError, UnicodeError, ValueError, yaml.YAMLError):
        return None
    producers = {
        str(row.get("producer") or "")
        for row in (artifacts or {}).values()
        if isinstance(row, dict)
    }
    qual_refs = {
        str(row.get("qual_ladder_ref") or "").strip()
        for row in (artifacts or {}).values()
        if isinstance(row, dict)
    }
    producer_keys: list[tuple[str, int | None]] = []
    for producer in sorted(p for p in producers if p):
        rel = Path(producer)
        # Placeholder/absolute/traversal tokens remain T1's concern; this cache key
        # never stats outside the commissioned root.
        if rel.is_absolute() or ".." in rel.parts:
            producer_keys.append((producer, None))
            continue
        producer_keys.append((producer, _mtime_ns(root / rel)))

    prereg_keys: list[tuple[str, int | None]] = []
    for ref in sorted(r for r in qual_refs if r):
        rel = Path(ref)
        if rel.is_absolute() or ".." in rel.parts:
            prereg_keys.append((ref, None))
            continue
        # T1 resolves a ref either as a qual-ladder key or as a repo file. The
        # ladder file has its own key below; this stat catches a referenced repo
        # file appearing, disappearing or changing without a Synapse edit.
        prereg_keys.append((ref, _mtime_ns(root / rel)))
    return (tuple(producer_keys), tuple(prereg_keys))


def _t1_evidence_mtime_key(root: Path) -> tuple[Any, ...]:
    """Every mutable local input that can change T1 evidence semantics."""
    return (
        _mtime_ns(root / _QUAL_LADDER_REL),
        _mtime_ns(root / _SPECIES_REL),
        _mtime_ns(root / _ARTICLE2_REL),
        _synapse_dependency_mtime_key(root),
    )


def _jsonl_candidate_count(path: Path) -> tuple[int | None, str | None]:
    """Count owner-reader candidate lines; parsing remains with the owner API."""
    if not path.exists():
        return None, None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"{path.name} is unreadable: {type(exc).__name__}: {exc}"
    return sum(1 for line in lines if line.strip() and not line.lstrip().startswith("#")), None


def _read_status_worse(current: str, candidate: str) -> str:
    rank = {"ok": 0, "partial": 1, "could_not_look": 2, "unreadable": 2, "error": 3}
    return candidate if rank.get(candidate, 3) > rank.get(current, 3) else current


def _parse_iso_timestamp(value: Any, *, require_timezone: bool) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    return not require_timezone or parsed.tzinfo is not None


def _positive_int(value: Any) -> bool:
    """JSON booleans are integers in Python, but never lawful horizons."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number_or_none(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _valid_claim_row(row: Any, qledger_owner: Any) -> bool:
    """Minimum historical qledger claim identity needed by the owner readers.

    This deliberately does not rerun today's registration gate over old rows: that gate
    has tightened over time and some lawful historical claims are retained as rejected
    or legacy evidence. It only refuses rows that cannot name a claim, family, ruler or
    observable scope at all.
    """
    if not isinstance(row, dict):
        return False
    scope = row.get("scope")
    family = row.get("claim_family") or row.get("desk")
    scope_type = scope.get("type") if isinstance(scope, dict) else None
    scope_key = scope.get("key") if isinstance(scope, dict) else None
    direction = row.get("direction")
    unit = row.get("horizon_unit")
    return (
        _nonempty_string(row.get("claim_id"))
        and _nonempty_string(row.get("desk"))
        and _nonempty_string(family)
        and _parse_iso_timestamp(row.get("asof"), require_timezone=False)
        and isinstance(scope, dict)
        and isinstance(scope_type, str)
        and scope_type in qledger_owner.SCOPE_TYPES
        and _nonempty_string(scope_key)
        and type(direction) is int
        and direction in qledger_owner.DIRECTIONS
        and _positive_int(row.get("horizon_d"))
        and (
            unit is None
            or (isinstance(unit, str) and unit in qledger_owner.HORIZON_UNITS)
        )
        and isinstance(row.get("timestamp_quality"), str)
        and row.get("timestamp_quality") in qledger_owner.TIMESTAMP_QUALITY
    )


def _valid_grade_row(row: Any, qledger_owner: Any) -> bool:
    """Minimum semantic shape shared by legacy and explicit-clock grade rows."""
    if not isinstance(row, dict):
        return False
    required_metrics = ("subject_ret", "bench_ret", "control_ret", "excess", "hit")
    unit = row.get("horizon_unit")
    version = row.get("clock_version")
    market = row.get("clock_market")
    legacy_basis = version is None and unit is None and market is None
    explicit_basis = (
        version == qledger_owner.CLOCK_V1
        and isinstance(unit, str)
        and unit in qledger_owner.HORIZON_UNITS
        and (
            market is None
            or (
                isinstance(market, str)
                and market in qledger_owner.CLOCK_MARKET_SUPPORT
            )
        )
    )
    return (
        _nonempty_string(row.get("claim_id"))
        and _positive_int(row.get("horizon_d"))
        and _parse_iso_timestamp(row.get("graded_at"), require_timezone=True)
        and all(key in row for key in required_metrics)
        and all(
            _finite_number_or_none(row.get(key))
            for key in ("subject_ret", "bench_ret", "control_ret", "excess")
        )
        and (row.get("hit") is None or type(row.get("hit")) is bool)
        and (legacy_basis or explicit_basis)
    )


def _valid_clock_receipt(clock: Any, family: str) -> bool:
    if not isinstance(clock, dict):
        return False
    return (
        str(clock.get("claim_family") or "") == family
        and _parse_iso_timestamp(
            clock.get("first_prospective_registration_utc"), require_timezone=True
        )
        and _positive_int(clock.get("declared_horizon_d"))
        and str(clock.get("horizon_unit") or "") in {"trading_days", "calendar_days"}
    )


def _load_evidence_providers(root: Path, registry: dict) -> dict[str, dict]:
    """Read existing qledger owners for concretely bound T1 cells; never write.

    Every other engine remains on T1's owner-native lifecycle/semantic evidence. An
    unreadable qledger store is represented as ``could_not_look`` rather than passed to
    qledger's missing-file-as-empty compatibility reader and mislabeled zero evidence.
    """
    from engine import qledger, qledger_desk_adapter  # noqa: PLC0415

    adapter_families = qledger_desk_adapter.known_families()
    bindings: dict[str, tuple[str, str]] = {}
    for cell in registry.get("engines") or []:
        if not isinstance(cell, dict):
            continue
        family = qledger_family_for_cell(cell, adapter_families)
        if not family:
            continue
        binding = (
            f"direct:qledger:{family}"
            if str(cell.get("ledger") or "").startswith("qledger:")
            else f"adapter:{family}"
        )
        bindings[str(cell.get("engine_id"))] = (family, binding)

    if not bindings:
        return {}

    claims_path = root / _QLEDGER_CLAIMS_REL
    if not claims_path.exists():
        return {
            engine_id: {
                "kind": "qledger",
                "binding": binding,
                "family": family,
                "read_status": "could_not_look",
                "clock_start": None,
                "readiness": {},
                "error": f"{_QLEDGER_CLAIMS_REL} is absent",
            }
            for engine_id, (family, binding) in bindings.items()
        }

    read_status = "ok"
    read_errors: list[str] = []
    claims_candidates, claims_error = _jsonl_candidate_count(claims_path)
    if claims_error:
        read_status = "unreadable"
        read_errors.append(claims_error)
    else:
        try:
            claims_rows = qledger.load_claims(root)
        except Exception as exc:  # noqa: BLE001 — owner read failed; carry blindness
            read_status = "unreadable"
            read_errors.append(f"claims owner read failed: {type(exc).__name__}: {exc}")
        else:
            if claims_candidates != len(claims_rows):
                read_status = "partial"
                read_errors.append(
                    f"claims.jsonl has {claims_candidates - len(claims_rows)} "
                    f"unparseable candidate line(s) of {claims_candidates}"
                )
            invalid_claims = sum(
                not _valid_claim_row(row, qledger) for row in claims_rows
            )
            if invalid_claims:
                read_status = _read_status_worse(read_status, "partial")
                read_errors.append(
                    f"claims.jsonl has {invalid_claims} semantically invalid "
                    f"owner row(s) of {len(claims_rows)}"
                )

    grades_path = root / _QLEDGER_GRADES_REL
    grades_candidates, grades_error = _jsonl_candidate_count(grades_path)
    if grades_error:
        read_status = _read_status_worse(read_status, "unreadable")
        read_errors.append(grades_error)
    elif grades_candidates is not None:
        try:
            grades_rows = qledger.load_grades(root)
        except Exception as exc:  # noqa: BLE001 — owner read failed; carry blindness
            read_status = _read_status_worse(read_status, "unreadable")
            read_errors.append(f"grades owner read failed: {type(exc).__name__}: {exc}")
        else:
            if grades_candidates != len(grades_rows):
                read_status = _read_status_worse(read_status, "partial")
                read_errors.append(
                    f"grades.jsonl has {grades_candidates - len(grades_rows)} "
                    f"unparseable candidate line(s) of {grades_candidates}"
                )
            invalid_grades = sum(
                not _valid_grade_row(row, qledger) for row in grades_rows
            )
            if invalid_grades:
                read_status = _read_status_worse(read_status, "partial")
                read_errors.append(
                    f"grades.jsonl has {invalid_grades} semantically invalid "
                    f"owner row(s) of {len(grades_rows)}"
                )

    if read_status in {"unreadable", "error"}:
        error = "; ".join(read_errors) or "qledger owner store is unreadable"
        return {
            engine_id: {
                "kind": "qledger",
                "binding": binding,
                "family": family,
                "read_status": read_status,
                "clock_start": None,
                "readiness": {},
                "error": error,
            }
            for engine_id, (family, binding) in bindings.items()
        }

    families = sorted({family for family, _binding in bindings.values()})
    try:
        from engine import qledger_evidence_clock  # noqa: PLC0415
        from scripts.grade_qledger import compute_promotion_readiness  # noqa: PLC0415

        readiness = compute_promotion_readiness(root, families=families)
        providers: dict[str, dict] = {}
        for engine_id, (family, binding) in bindings.items():
            family_status = read_status
            family_errors = list(read_errors)
            clock_start = qledger_evidence_clock.read_start(family, root=root)
            safe_family = "".join(
                ch if (ch.isalnum() or ch in "-_") else "_" for ch in family
            )
            clock_path = root / _QLEDGER_CLOCK_DIR_REL / f"{safe_family}.json"
            if clock_path.exists() and not _valid_clock_receipt(clock_start, family):
                family_status = _read_status_worse(family_status, "unreadable")
                family_errors.append(
                    f"evidence clock receipt {clock_path.name} is unreadable or malformed"
                )
                clock_start = None
            provider = {
                "kind": "qledger",
                "binding": binding,
                "family": family,
                "read_status": family_status,
                "clock_start": clock_start,
                "readiness": readiness.get(family) or {},
            }
            if family_errors:
                provider["error"] = "; ".join(family_errors)
            providers[engine_id] = provider
        return providers
    except Exception as exc:  # noqa: BLE001 — admin reads fail open, but name the blind owner
        return {
            engine_id: {
                "kind": "qledger",
                "binding": binding,
                "family": family,
                "read_status": "error",
                "clock_start": None,
                "readiness": {},
                "error": f"{type(exc).__name__}: {exc}",
            }
            for engine_id, (family, binding) in bindings.items()
        }


def _derive(root: Path, force: bool) -> tuple[dict, dict, dict, float, str]:
    """``(view, registry, evidence, seconds, 'hit'|'miss')`` — cache protocol.

    Keyed on T1 identity/semantic inputs and owner evidence receipts as well as the root,
    so their movement is picked up immediately rather than after the TTL. A missing input
    keys as ``None``; absence remains a fact for the owner resolver to interpret.
    """
    key = (
        str(root),
        _mtime_ns(root / _SYNAPSE_REL),
        _mtime_ns(root / _OVERLAY_REL),
        *_t1_evidence_mtime_key(root),
        *_evidence_mtime_key(root),
    )
    with _LOCK:
        if not force:
            cached = _CACHE.get(key)
            if cached is not None and (time.monotonic() - cached[0]) < _TTL_S:
                return cached[1], cached[2], cached[3], 0.0, "hit"
        # Imported HERE, not at module scope: admin/*.py is imported wholesale by the
        # server and by the import smoke suite, and this pulls in yaml, the T1 registry
        # builder and the pure resolver. Keeping it lazy leaves module import free of
        # both the dependency and build_output_health's sys.path insertion.
        # The repo root is put on the path against THIS file's location, not the process
        # cwd: the admin server is started from more than one place, and `scripts` is a
        # package only when the root is importable.
        if str(_ROOT) not in sys.path:
            sys.path.insert(0, str(_ROOT))
        from scripts.build_intelligence_registry import (  # noqa: PLC0415
            SynapseUnavailable,
        )
        from scripts.build_output_health import build_with_registry  # noqa: PLC0415

        started = time.monotonic()
        try:
            view, registry = build_with_registry(
                root, now=datetime.now(timezone.utc), trust_mtime=_trust_mtime()
            )
        except SynapseUnavailable as exc:
            # T1's own sentinel — an artifact census that could not be loaded. Caught
            # BEFORE SystemExit because it is a subclass of it.
            raise EstateUnavailable(f"SynapseUnavailable: {exc}") from exc
        except SystemExit as exc:
            # The T4 builder's plain exit for an unreadable/unparseable config/synapse.yml.
            raise EstateUnavailable(f"SystemExit: {exc}") from exc
        evidence = _load_evidence_providers(root, registry)
        elapsed = time.monotonic() - started
        _CACHE[key] = (time.monotonic(), view, registry, evidence)
        # One live root, and the key changes on every registry edit — without this the
        # dict would accumulate a 642-record view per nightly commit for the life of the
        # process.
        for stale in [k for k in _CACHE if k != key and k[0] == str(root)]:
            _CACHE.pop(stale, None)
        return view, registry, evidence, elapsed, "miss"


def _tally(rows: list[dict], key: str) -> dict[str, int]:
    """Count by *key*, with ``None`` folded into the literal ``"null"`` and never lost."""
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        label = "null" if value is None else str(value)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _noncanonical_evidence() -> dict[str, Any]:
    """Explicitly withhold T7/T8 semantics from a registry-gap output group."""
    return {
        "evidence_status": None,
        "evidence_reason_codes": ["not_canonical_t1"],
        "evidence_refs": [],
        "evidence_provider": None,
        "evidence_ruler": None,
        "evidence_basis": None,
        "evidence_maturity": None,
        "evidence_coverage": None,
    }


def worst_state(states) -> str | None:
    """The most severe state in *states* per :data:`STATE_SEVERITY`.

    An unknown state sorts WORST rather than best: a vocabulary this page has not learned
    yet must announce itself, never hide behind ``healthy``.
    """
    worst: str | None = None
    worst_rank = len(STATE_SEVERITY)
    for state in states:
        try:
            rank = STATE_SEVERITY.index(state)
        except ValueError:
            rank = -1
        if rank < worst_rank:
            worst, worst_rank = state, rank
    return worst


def _engine_rows(view: dict, registry: dict, evidence_by_engine: dict) -> list[dict]:
    """One row per engine, folded from the T4 records and joined to the T1 engine cell."""
    canonical_cells = [
        row for row in (registry.get("engines") or []) if isinstance(row, dict)
    ]
    # T1 is the unit of account. Seed every canonical cell before folding T4 so a
    # zero-output failure remains visible as Degraded instead of disappearing.
    by_engine: dict[str, list[dict]] = {
        str(row.get("engine_id")): []
        for row in canonical_cells
        if str(row.get("engine_id") or "")
    }
    for record in view.get("outputs") or []:
        eid = record.get("engine_id") or UNREGISTERED_ENGINE_ID
        by_engine.setdefault(eid, []).append(record)

    cells = {
        str(row.get("engine_id")): row
        for row in canonical_cells
    }
    canonical_ids = set(cells)
    for row in registry.get("excluded") or []:
        if isinstance(row, dict) and str(row.get("engine_id")) not in cells:
            cells[str(row.get("engine_id"))] = row

    rows = []
    for eid, records in sorted(by_engine.items()):
        cell = cells.get(eid) or {}
        counts = _tally(records, "state")
        row = {
                "engine_id": eid,
                "canonical_t1": eid in canonical_ids,
                "owner_program": cell.get("owner_program"),
                "producer": cell.get("producer"),
                # T1's overlay is the ONLY source. Never backfill its explicit null from
                # a downstream T4 record, even if contradictory bytes reach this seam.
                "output_class": cell.get("output_class"),
                "authority": cell.get("authority")
                or (records[0].get("authority") if records else None),
                "n_artifacts": len(records),
                "worst_state": worst_state(r.get("state") for r in records),
                "state_counts": counts,
                # THE ROLL-UP MUST NOT RENDER GREEN OVER BLINDNESS. `worst_state` folds
                # only REAL verdicts — a null is "we could not determine it" and correctly
                # never outranks one — so an engine whose one readable output is healthy
                # and whose other seven were unreadable folded to a green row with nothing
                # on it to say so. The count is derivable from `state_counts`, but a
                # number the surface has to remember to derive is a number it will forget:
                # hoisted to a top-level field so the row cannot be drawn without it.
                "n_blind": counts.get("null", 0),
            }
        if eid in canonical_ids:
            row.update(derive_evidence_status(cell, records, evidence_by_engine.get(eid)))
        else:
            row.update(_noncanonical_evidence())
        rows.append(row)
    status_rank = {status: rank for rank, status in enumerate(EVIDENCE_STATUS_ORDER)}
    return sorted(
        rows,
        key=lambda row: (
            status_rank.get(str(row.get("evidence_status")), len(status_rank)),
            str(row.get("engine_id")),
        ),
    )


def panel(root: Path | None = None, force: bool = False) -> dict[str, Any]:
    """The census + per-engine roll-up. Read-only; derived on demand; never persisted."""
    root = Path(root) if root is not None else _ROOT
    try:
        view, registry, evidence_by_engine, elapsed, cache = _derive(root, force)
    except Exception as exc:  # noqa: BLE001
        # The two exit-flavored failures — T1's SynapseUnavailable and the T4 builder's
        # plain SystemExit for an unreadable config/synapse.yml — are already converted to
        # EstateUnavailable inside _derive, which is the only place that can tell them
        # apart. So this handler is an ordinary one: fail open like every sibling admin
        # panel, and never take the process down to report that a file was missing.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    records = list(view.get("outputs") or [])
    summary = view.get("summary") or {}
    engines = _engine_rows(view, registry, evidence_by_engine)
    canonical_engines = [row for row in engines if row.get("canonical_t1")]
    reasons = sorted(
        (summary.get("reason_codes") or {}).items(), key=lambda kv: (-kv[1], kv[0])
    )
    return {
        "ok": True,
        "census": {
            "engines": len(engines),
            "canonical_engines": len(canonical_engines),
            "noncanonical_output_groups": len(engines) - len(canonical_engines),
            "artifacts": len(records),
            # "Assessed" means Eval OS could actually LOOK, not that it liked what it
            # saw. The gap between this and `artifacts` is the observer-blindness count,
            # and it is the number a census must never round away.
            "outputs_assessed": sum(
                1 for r in records if r.get("assessment_status") != "could_not_look"
            ),
            "by_state": summary.get("by_state") or {},
            "by_assessment_status": summary.get("by_assessment_status") or {},
            "by_output_class": _tally(records, "output_class"),
            "by_evidence_status": _tally(canonical_engines, "evidence_status"),
            "by_authority": _tally(records, "authority"),
            "by_storage": _tally(records, "storage"),
            "by_dependency_bound": summary.get("by_dependency_bound") or {},
            "top_reason_codes": [{"code": c, "n": n} for c, n in reasons[:12]],
        },
        "engines": engines,
        "ceo_view": build_ceo_view(canonical_engines),
        "generated": {
            "observed_at": (view.get("generated") or {}).get("observed_at"),
            "root_mode": (view.get("generated") or {}).get("root_mode"),
            "compute_seconds": round(elapsed, 2),
            "cache": cache,
            "trust_mtime": _trust_mtime(),
        },
    }


def engine_detail(engine_id: str, root: Path | None = None) -> dict[str, Any]:
    """One engine's T1 cell plus the FULL T4 record for each of its outputs."""
    root = Path(root) if root is not None else _ROOT
    wanted = str(engine_id or "")
    try:
        view, registry, evidence_by_engine, _elapsed, _cache = _derive(root, force=False)
    except Exception as exc:  # noqa: BLE001 — fail open; see panel()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    registry_rows = (registry.get("engines") or []) + (registry.get("excluded") or [])
    cell = next(
        (
            row
            for row in registry_rows
            if isinstance(row, dict) and str(row.get("engine_id")) == wanted
        ),
        None,
    )
    outputs = [
        r
        for r in (view.get("outputs") or [])
        if (r.get("engine_id") or UNREGISTERED_ENGINE_ID) == wanted
    ]
    if not outputs and cell is None:
        known = sorted(
            {
                str(r.get("engine_id") or UNREGISTERED_ENGINE_ID)
                for r in (view.get("outputs") or [])
            }
            | {
                str(row.get("engine_id"))
                for row in registry_rows
                if isinstance(row, dict) and str(row.get("engine_id") or "")
            }
        )
        return {
            "ok": False,
            "error": f"no engine {wanted!r} in the current estate",
            "known_ids_sample": known[:20],
        }

    cell = cell or {}
    canonical_t1 = any(
        isinstance(row, dict) and str(row.get("engine_id")) == wanted
        for row in (registry.get("engines") or [])
    )
    engine = {
            "engine_id": wanted,
            "canonical_t1": canonical_t1,
            "owner_program": cell.get("owner_program"),
            "producer": cell.get("producer"),
            "output_class": cell.get("output_class"),
            "output_class_rationale": cell.get("output_class_reason"),
            "authority": cell.get("authority")
            or (outputs[0].get("authority") if outputs else None),
            "ledger": cell.get("ledger"),
            "ledger_evidence": cell.get("ledger_evidence"),
            "graded_by_design": cell.get("graded_by_design"),
            "graded_by_design_evidence": cell.get("graded_by_design_evidence"),
            "graded_by_design_source": cell.get("graded_by_design_source"),
            "declared_horizon": cell.get("declared_horizon"),
            "validation_state": cell.get("validation_state"),
            "validation_state_evidence": cell.get("validation_state_evidence"),
            "evidence_ref": cell.get("evidence_ref"),
            # Present only for a cell T1 EXCLUDED (placeholder producer, no code advances
            # it). Rendering the reason is what keeps "not graded" from reading as a
            # grade of zero.
            "excluded_reason": cell.get("reason"),
            "n_artifacts": len(outputs),
            "worst_state": worst_state(r.get("state") for r in outputs),
        }
    if canonical_t1:
        engine.update(derive_evidence_status(cell, outputs, evidence_by_engine.get(wanted)))
    else:
        engine.update(_noncanonical_evidence())
    return {
        "ok": True,
        "engine": engine,
        "outputs": sorted(outputs, key=lambda r: str(r.get("artifact_id"))),
    }
