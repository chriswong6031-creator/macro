"""Intelligence OS operator panel — the Eval OS T1 + T4 estate, derived on demand.

WHAT THIS SURFACE IS. One row per intelligence ENGINE (the T1 unit of account: a
``producer::owner_program`` cell), carrying the adjudicated ``output_class`` and
``authority`` T1 assigned it, plus the worst OUTPUT HEALTH state T4 resolved across the
engine's artifacts. Drilling into an engine shows the full ``mastermind.output_health.v1``
record for each of its outputs — which plane decided the state, against which watermark,
with which reason codes.

WHAT IT IS NOT. It is a CENSUS and a HEALTH READ. There is no score, rank, weight, size,
promotion state or gate here, and none is computed: ``output_class`` is read from the T1
overlay and is ``null`` wherever no adjudication exists. A guessed class would be an
authority claim wearing a census's clothes, so the null is rendered as a null.

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

import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent

#: The two declared inputs whose change should invalidate a cached view: the artifact
#: census and the adjudication overlay. Mirrors scripts/build_intelligence_registry.py.
_SYNAPSE_REL = Path("config") / "synapse.yml"
_OVERLAY_REL = Path("config") / "intelligence_registry_overlay.yml"

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
#: key -> (stored_at_monotonic, view, registry). Memory only; see the module docstring.
_CACHE: dict[tuple, tuple[float, dict, dict]] = {}
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


def _derive(root: Path, force: bool) -> tuple[dict, dict, float, str]:
    """``(view, registry, compute_seconds, 'hit'|'miss')`` — the whole cache protocol.

    Keyed on the two declared inputs' mtimes as well as the root, so an edit to either
    is picked up immediately rather than after the TTL. A missing input keys as ``None``
    and the TTL alone governs — an absent overlay is a legitimate state, not an error.
    """
    key = (str(root), _mtime_ns(root / _SYNAPSE_REL), _mtime_ns(root / _OVERLAY_REL))
    with _LOCK:
        if not force:
            cached = _CACHE.get(key)
            if cached is not None and (time.monotonic() - cached[0]) < _TTL_S:
                return cached[1], cached[2], 0.0, "hit"
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
        elapsed = time.monotonic() - started
        _CACHE[key] = (time.monotonic(), view, registry)
        # One live root, and the key changes on every registry edit — without this the
        # dict would accumulate a 642-record view per nightly commit for the life of the
        # process.
        for stale in [k for k in _CACHE if k != key and k[0] == str(root)]:
            _CACHE.pop(stale, None)
        return view, registry, elapsed, "miss"


def _tally(rows: list[dict], key: str) -> dict[str, int]:
    """Count by *key*, with ``None`` folded into the literal ``"null"`` and never lost."""
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key)
        label = "null" if value is None else str(value)
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


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


def _engine_rows(view: dict, registry: dict) -> list[dict]:
    """One row per engine, folded from the T4 records and joined to the T1 engine cell."""
    by_engine: dict[str, list[dict]] = {}
    for record in view.get("outputs") or []:
        eid = record.get("engine_id") or UNREGISTERED_ENGINE_ID
        by_engine.setdefault(eid, []).append(record)

    cells = {
        str(row.get("engine_id")): row
        for row in (registry.get("engines") or [])
        if isinstance(row, dict)
    }
    for row in registry.get("excluded") or []:
        if isinstance(row, dict) and str(row.get("engine_id")) not in cells:
            cells[str(row.get("engine_id"))] = row

    rows = []
    for eid, records in sorted(by_engine.items()):
        cell = cells.get(eid) or {}
        counts = _tally(records, "state")
        rows.append(
            {
                "engine_id": eid,
                "owner_program": cell.get("owner_program"),
                "producer": cell.get("producer"),
                # T1's overlay is the ONLY source. A record's class and the cell's class
                # are the same adjudication; neither is inferred from the other's absence.
                "output_class": cell.get("output_class")
                or records[0].get("output_class"),
                "authority": cell.get("authority") or records[0].get("authority"),
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
        )
    return rows


def panel(root: Path | None = None, force: bool = False) -> dict[str, Any]:
    """The census + per-engine roll-up. Read-only; derived on demand; never persisted."""
    root = Path(root) if root is not None else _ROOT
    try:
        view, registry, elapsed, cache = _derive(root, force)
    except Exception as exc:  # noqa: BLE001
        # The two exit-flavored failures — T1's SynapseUnavailable and the T4 builder's
        # plain SystemExit for an unreadable config/synapse.yml — are already converted to
        # EstateUnavailable inside _derive, which is the only place that can tell them
        # apart. So this handler is an ordinary one: fail open like every sibling admin
        # panel, and never take the process down to report that a file was missing.
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    records = list(view.get("outputs") or [])
    summary = view.get("summary") or {}
    engines = _engine_rows(view, registry)
    reasons = sorted(
        (summary.get("reason_codes") or {}).items(), key=lambda kv: (-kv[1], kv[0])
    )
    return {
        "ok": True,
        "census": {
            "engines": len(engines),
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
            "by_authority": _tally(records, "authority"),
            "by_storage": _tally(records, "storage"),
            "by_dependency_bound": summary.get("by_dependency_bound") or {},
            "top_reason_codes": [{"code": c, "n": n} for c, n in reasons[:12]],
        },
        "engines": engines,
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
        view, registry, _elapsed, _cache = _derive(root, force=False)
    except Exception as exc:  # noqa: BLE001 — fail open; see panel()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    outputs = [
        r
        for r in (view.get("outputs") or [])
        if (r.get("engine_id") or UNREGISTERED_ENGINE_ID) == wanted
    ]
    if not outputs:
        known = sorted(
            {
                str(r.get("engine_id") or UNREGISTERED_ENGINE_ID)
                for r in (view.get("outputs") or [])
            }
        )
        return {
            "ok": False,
            "error": f"no engine {wanted!r} in the current estate",
            "known_ids_sample": known[:20],
        }

    cell = next(
        (
            row
            for row in (registry.get("engines") or []) + (registry.get("excluded") or [])
            if isinstance(row, dict) and str(row.get("engine_id")) == wanted
        ),
        {},
    )
    return {
        "ok": True,
        "engine": {
            "engine_id": wanted,
            "owner_program": cell.get("owner_program"),
            "producer": cell.get("producer"),
            "output_class": cell.get("output_class") or outputs[0].get("output_class"),
            "output_class_rationale": cell.get("output_class_reason"),
            "authority": cell.get("authority") or outputs[0].get("authority"),
            # Present only for a cell T1 EXCLUDED (placeholder producer, no code advances
            # it). Rendering the reason is what keeps "not graded" from reading as a
            # grade of zero.
            "excluded_reason": cell.get("reason"),
            "n_artifacts": len(outputs),
            "worst_state": worst_state(r.get("state") for r in outputs),
        },
        "outputs": sorted(outputs, key=lambda r: str(r.get("artifact_id"))),
    }
