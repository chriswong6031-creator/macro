"""scripts/build_capability_health.py — F13 V1 adapter for engine.capability_health.

THE ADAPTER, NOT THE CONTRACT. Every rule about what a capability's state MEANS lives in
the pure resolver :mod:`engine.capability_health`; this file only goes and looks, exactly
the way ``scripts/build_output_health.py`` relates to ``engine/output_health.py``.

RECEIPT SOURCES, PER TYPE
--------------------------
``output_health_artifact``
    Composed READ-ONLY off :func:`scripts.build_output_health.build` — the same public
    entry point ``admin/intelligence_os.py`` calls. Neither ``engine/output_health.py``
    nor ``scripts/build_output_health.py`` is edited by F13; this module only imports and
    reads their already-resolved view. The already-judged ``state``/``assessment_status``
    ride through verbatim (an ``output_health_artifact`` fact is an upstream VERDICT, not
    raw clocks — see the engine module's docstring on why that fold never re-derives it).
    ``corrupt``/``rights_blocked`` are correctly always ``False`` for this source type:
    output_health has no distinct "corrupt receipt" or "rights block" signal of its own
    (blindness is already fully expressed via ``state=None, assessment_status=
    could_not_look``), so there is nothing further to wire here.
``nightly_lane``
    Read from ``data/run_status.json``: a named key under ``sources`` (per-source
    ``status``/``checked_at``/``last_date``), or the literal ``__global__`` for the
    top-level ``last_run`` heartbeat. The collector status vocabulary
    (``collectors/base.py``'s ``FetchResult.status``: ok | stale | failed | dead |
    skipped | blocked) is mapped explicitly (repair 2026-09-04, findings C1/I5):
      ok      -> last_attempted = last_successful = checked_at (a genuine success)
      stale   -> an EXPLICIT ``state=stale`` (the collector's own declared staleness
                 call, not a re-derivation from our own stale_after_hours budget)
      failed/dead -> last_attempted = checked_at ONLY. data/run_status.json retains only
                 the LATEST row per source (no history), so there is no prior
                 last_successful to compare against — the honest fact is "attempted, no
                 prior success known", which the engine resolves to could_not_look, never
                 a fabricated degraded/stale guess.
      blocked -> ``rights_blocked=True`` (a known, expected limitation — bot-blocked,
                 paywalled — never conflated with a failure)
      skipped -> "no-attempt-fact": neither clock is supplied at all (the source was not
                 even consulted this run; the engine reads that as no_clock_evidence, not
                 a failure)
    ``__global__`` NEVER supplies ``last_successful`` — ``scripts/collect.py`` writes
    ``last_run`` unconditionally once the collect pass reaches that line, regardless of
    per-source outcome, so it can only ever prove an attempt, never a verified success.
    (No capability in the V1 seed cohort actually declares a ``__global__`` source any
    more — see ``config/capability_health.yml``'s comment on why one was removed from
    ``prophet_us`` in this same repair: a source that can NEVER contribute anything but
    could_not_look would permanently poison its capability under the worst-fold law.)

    ROUND-3 REPAIR (2026-09-06 independent review): ``last_date`` is NEVER mapped onto
    ``data_as_of`` here, in ANY status branch. ``last_date`` is
    ``collectors/base.py``'s group-MAX OBSERVATION date across a source's own stored
    series — not an as-of instant — and a healthy, live shape (fred's FEDTARMD FOMC
    projection series legitimately carries a `last_date` years in the future) was being
    branded corrupt (``clock_value_future_dated``) by the round-2 repair for exactly this
    reason: it published a real, honest lane's receipt as ``could_not_look`` forever. A
    ``nightly_lane`` receipt truthfully carries only last_attempted/last_successful (+ an
    explicit stale ``state``, ``rights_blocked``, or ``blind_reason``) — it never had
    as-of semantics, and ``config/capability_health.yml``'s ``nightly_lane`` declarations
    no longer claim ``data_as_of`` either. A capability that needs a real as-of instant
    declares an ``output_health_artifact`` source instead (``resolve_output_health``'s
    already-judged ``source_asof`` genuinely IS bound to a point-in-time read).
``provider_rung`` / ``sentinel_probe``
    Declared in the closed receipt-source vocabulary and accepted by registry
    validation, but NOT wired to a live fetch in this V1 build: none of the seed cohort's
    five capabilities declares one (see ``config/capability_health.yml``'s header
    comment for the two commission candidates dropped for lack of a verifiable receipt).
    Additive later, per the frozen commission's "5-8 entries is right; additive later".

FAILS CLOSED ON A BAD REGISTRY (repair finding C3). A malformed/missing/non-dict
``config/capability_health.yml``, a missing or empty ``capabilities`` key, a duplicate
capability id, or an unresolvable ``depends_on`` reference is a HARD BUILD ERROR
(:class:`RegistryError`): :func:`main` prints every problem via a bare
``::warning``/``::error`` (never a logger), exits non-zero, and WRITES NOTHING — a
silent zero-capability artifact would destroy whatever last-good state a prior run wrote.

WRITES ONE ARTIFACT. Deterministic, no network, no GH API. Default output path is
``data/capability_health/state.json`` under ``--root`` — the production nightly default.
``--out`` and ``--receipts-root`` exist so a sparse worktree or a test can point both the
destination and the receipt reads somewhere that is never ``data/`` or ``site/``; the
default ``data/`` path is refused outright in a sparse worktree unless ``--out`` is given
explicitly (repair finding M5) — a write into an omitted tree can truncate the committed
artifact once the branch merges.

Usage
-----
  python3 scripts/build_capability_health.py --summary
  python3 scripts/build_capability_health.py --out /tmp/state.json --receipts-root /tmp/rr
  python3 scripts/build_capability_health.py --now 2026-09-04T00:00:00+00:00 --json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from engine.capability_health import (  # noqa: E402
    REASON_UNKNOWN_COLLECTOR_STATUS,
    STATE_STALE,
    resolve_capability_health,
    validate_registry,
)
from lib.dataos.temporal import TemporalError, utc  # noqa: E402

REGISTRY_REL = Path("config") / "capability_health.yml"
DEFAULT_OUT_REL = Path("data") / "capability_health" / "state.json"
RUN_STATUS_REL = Path("data") / "run_status.json"

#: collectors/base.py FetchResult.status vocabulary (module docstring above has the full
#: mapping table).
_STATUS_OK = "ok"
_STATUS_STALE = "stale"
_STATUS_FAILED = "failed"
_STATUS_DEAD = "dead"
_STATUS_BLOCKED = "blocked"
_STATUS_SKIPPED = "skipped"
_KNOWN_STATUSES = frozenset({
    _STATUS_OK, _STATUS_STALE, _STATUS_FAILED, _STATUS_DEAD, _STATUS_BLOCKED,
    _STATUS_SKIPPED,
})

#: MINOR-4 repair: collectors/base.py's redactor scrubs credentials from
#: FetchResult.error for the collectors it wraps, but collect.py's OWN additive status
#: dicts (e.g. the "check_failed" shape read below) bypass that redactor entirely — the
#: raw `str(exc)` text can ride straight into a COMMITTED artifact
#: (data/capability_health/state.json). Capping length is a blast-radius bound, NOT a
#: redaction — it cannot scrub a leaked secret out of the first 300 characters, it only
#: limits how much of one (or of any other unbounded third-party text) ends up
#: committed. Real redaction remains upstream's job (collectors/base.py); this is
#: defense in depth for the paths that bypass it.
_RIGHTS_DETAIL_MAX_CHARS = 300


class RegistryError(RuntimeError):
    """The registry (or a capability entry) is structurally invalid.

    FAILS CLOSED (repair finding C3): a caller that catches this must refuse to write an
    artifact, never fall back to a silent zero-capability write that would destroy
    last-good state.
    """


def _load_yaml_text(path: Path) -> tuple[Any, str | None]:
    """``(parsed_doc_or_None, problem_or_None)`` — never silently returns ``None`` for
    both an unreadable file AND a genuinely empty one; the caller must be able to tell
    "could not read" from "read fine, contained nothing"."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"{path} is unreadable ({type(exc).__name__}: {exc})"
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return None, f"{path} is not valid YAML ({exc})"
    return doc, None


def _load_json(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def load_registry(root: Path) -> list[dict[str, Any]]:
    """The parsed, VALIDATED ``capabilities`` list.

    Raises :class:`RegistryError` — never returns a silent ``[]`` (repair finding C3) —
    on anything short of a well-formed, non-empty, schema-valid list: an unreadable or
    unparseable file, a non-mapping document, a missing/empty/non-list ``capabilities``
    key, a non-mapping entry, or any :func:`engine.capability_health.validate_registry`
    problem (unknown receipt-source type, missing ref, duplicate id, unresolvable
    ``depends_on``, ...).
    """
    path = root / REGISTRY_REL
    doc, problem = _load_yaml_text(path)
    if problem:
        raise RegistryError(problem)
    if not isinstance(doc, dict):
        raise RegistryError(f"{path} did not parse to a mapping (got {type(doc).__name__})")
    if "capabilities" not in doc:
        raise RegistryError(f"{path} has no 'capabilities' key")
    raw = doc.get("capabilities")
    if not isinstance(raw, list) or not raw:
        raise RegistryError(f"{path}'s 'capabilities' is empty or not a list")
    capabilities = [c for c in raw if isinstance(c, dict)]
    if len(capabilities) != len(raw):
        raise RegistryError(
            f"{path}'s 'capabilities' contains {len(raw) - len(capabilities)} "
            f"non-mapping entr(y/ies)"
        )
    problems = validate_registry(capabilities)
    if problems:
        raise RegistryError("; ".join(problems))
    return capabilities


def output_health_facts(
    root: Path, refs: list[str], *, now: datetime
) -> dict[str, dict[str, Any]]:
    """One fact per requested ``output_health_artifact`` id.

    Composed off :func:`scripts.build_output_health.build` — reads only, never edits
    output_health's own modules. A refused/missing/crashed build resolves every requested
    ref to ``readable=False`` rather than raising: a receipt source must never be able to
    take down the whole capability-health build.
    """
    if not refs:
        return {}
    from scripts import build_output_health as OH_BUILD  # noqa: PLC0415

    try:
        view = OH_BUILD.build(root, now=now, limit_artifacts=sorted(set(refs)))
    except SystemExit:
        return {ref: {"readable": False} for ref in refs}
    except Exception:  # noqa: BLE001 — a receipt source must never crash the build
        return {ref: {"readable": False} for ref in refs}

    by_id = {row.get("artifact_id"): row for row in view.get("outputs") or []}
    out: dict[str, dict[str, Any]] = {}
    for ref in refs:
        rec = by_id.get(ref)
        if rec is None:
            out[ref] = {"readable": False}
            continue
        out[ref] = {
            "readable": True,
            "corrupt": False,
            "state": rec.get("state"),
            "assessment_status": rec.get("assessment_status"),
            "data_as_of": rec.get("source_asof"),
        }
    return out


def nightly_lane_facts(receipts_root: Path, refs: list[str]) -> dict[str, dict[str, Any]]:
    """One fact per requested ``nightly_lane`` ref, from ``data/run_status.json``.

    See the module docstring's status-mapping table (repair findings C1/I5): ``ok`` is
    the only status that ever supplies ``last_successful``; ``failed``/``dead`` supply
    ``last_attempted`` alone (no fabricated success); ``blocked`` sets
    ``rights_blocked``; ``stale`` sets an explicit ``state``; ``skipped`` supplies no
    clock at all.

    MINOR-1 repair: a status OUTSIDE that six-value collectors/base.py vocabulary — or a
    source entry with NO ``status`` key at all — is real, live shape:
    ``scripts/collect.py``'s additive, non-Adapter steps (e.g. ``options_flow_creds``)
    write statuses of their own, such as ``check_failed``, straight into
    ``data/run_status.json["sources"]``. Previously this fell through to the same branch
    as ``failed``/``dead`` ("attempted, no prior success"), which reads as an honest
    attempt when it is actually an UNRECOGNIZED shape this adapter has no vocabulary
    for. It is now a typed ``blind_reason`` disclosure the engine surfaces verbatim
    (never silently downgraded to a generic no-clock-evidence/no-prior-success read, and
    never healthy).

    ROUND-3 repair (2026-09-06 independent review, item 1): ``entry.get("last_date")`` is
    read NOWHERE in this function any more, in ANY branch. It is
    ``collectors/base.py``'s group-MAX OBSERVATION date across a source's own stored
    series, never an as-of instant, and mapping it onto ``data_as_of`` branded a healthy
    lane (fred's real, legitimately-future FEDTARMD FOMC-projection ``last_date``)
    ``could_not_look`` forever. A ``nightly_lane`` fact now carries ONLY
    last_attempted/last_successful (+ an explicit stale ``state``, ``rights_blocked``, or
    ``blind_reason``) — never a ``data_as_of`` key.
    """
    doc = _load_json(receipts_root / RUN_STATUS_REL)
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(doc, dict):
        for ref in refs:
            out[ref] = {"readable": False}
        return out
    sources = doc.get("sources") if isinstance(doc.get("sources"), dict) else {}
    for ref in refs:
        if ref == "__global__":
            last_run = doc.get("last_run")
            out[ref] = (
                {"readable": False}
                if not last_run
                else {"readable": True, "corrupt": False, "last_attempted": last_run}
            )
            continue

        entry = sources.get(ref)
        if not isinstance(entry, dict):
            out[ref] = {"readable": False}
            continue

        status = str(entry.get("status") or "")
        checked_at = entry.get("checked_at")
        fact: dict[str, Any] = {"readable": True, "corrupt": False}

        if status == _STATUS_SKIPPED:
            # "no-attempt-fact": this run did not even consult this source. Neither
            # clock is supplied — the engine reads that as no_clock_evidence, never a
            # fabricated failure.
            out[ref] = fact
            continue

        if status == _STATUS_BLOCKED:
            fact["rights_blocked"] = True
            raw_detail = str(entry.get("error") or "collector reports 'blocked'")
            fact["rights_detail"] = raw_detail[:_RIGHTS_DETAIL_MAX_CHARS]
            if checked_at:
                fact["last_attempted"] = checked_at
            out[ref] = fact
            continue

        if status not in _KNOWN_STATUSES:
            # MINOR-1: an unrecognized (or entirely absent) collector status. Never
            # fabricate a clock reading for a shape this adapter does not understand —
            # disclose it by name so a reader sees exactly which status confused the
            # build, and let the engine resolve it to could_not_look via the typed
            # `blind_reason`, never a silent "attempted, no prior success".
            fact["blind_reason"] = (
                f"{REASON_UNKNOWN_COLLECTOR_STATUS}:{ref}:{status or '<missing>'}"
            )
            if checked_at:
                fact["last_attempted"] = checked_at
            out[ref] = fact
            continue

        if checked_at:
            fact["last_attempted"] = checked_at
            if status == _STATUS_OK:
                fact["last_successful"] = checked_at
            elif status == _STATUS_STALE:
                # The adapter itself ran cleanly (no exception) but its OWN
                # stale_after_days budget says the fetched content is old — the
                # collector's explicit call, honored directly rather than re-derived
                # from our own stale_after_hours.
                fact["state"] = STATE_STALE
            elif status in (_STATUS_FAILED, _STATUS_DEAD):
                # An attempt happened and did not succeed. data/run_status.json keeps
                # only the LATEST row per source (no history), so there is no prior
                # last_successful to compare against here — never invent one.
                pass
        out[ref] = fact
    return out


def gather_receipts(
    root: Path,
    capabilities: list[dict[str, Any]],
    *,
    now: datetime,
    receipts_root: Path,
) -> dict[str, list[dict[str, Any] | None]]:
    """Every declared receipt source, read exactly once per unique ref."""
    oh_refs: list[str] = []
    lane_refs: list[str] = []
    for cap in capabilities:
        for decl in cap.get("receipt_sources") or []:
            if not isinstance(decl, dict):
                continue
            typ, ref = decl.get("type"), decl.get("ref")
            if not isinstance(ref, str):
                continue
            if typ == "output_health_artifact":
                oh_refs.append(ref)
            elif typ == "nightly_lane":
                lane_refs.append(ref)

    oh_facts = output_health_facts(root, oh_refs, now=now)
    lane_facts = nightly_lane_facts(receipts_root, lane_refs)

    receipts: dict[str, list[dict[str, Any] | None]] = {}
    for cap in capabilities:
        cid = str(cap.get("id"))
        facts: list[dict[str, Any] | None] = []
        for decl in cap.get("receipt_sources") or []:
            if not isinstance(decl, dict):
                facts.append({"readable": False})
                continue
            typ, ref = decl.get("type"), decl.get("ref")
            if typ == "output_health_artifact":
                facts.append(oh_facts.get(ref, {"readable": False}))
            elif typ == "nightly_lane":
                facts.append(lane_facts.get(ref, {"readable": False}))
            else:
                # provider_rung / sentinel_probe / an unknown type — no live loader in
                # V1 (see module docstring). An absent fact reads as unreadable; the
                # resolver never invents a verdict for a source it cannot fetch.
                facts.append({"readable": False})
        receipts[cid] = facts
    return receipts


def build(
    root: Path,
    *,
    now: datetime,
    receipts_root: Path | None = None,
    previous: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Gather receipts and resolve. Reads only; writes nothing. Deterministic, no network.

    Raises :class:`RegistryError` (never returns) when the registry itself is invalid —
    the caller must not write an artifact in that case (repair finding C3).
    """
    capabilities = load_registry(root)
    rroot = receipts_root if receipts_root is not None else root
    receipts = gather_receipts(root, capabilities, now=now, receipts_root=rroot)
    return resolve_capability_health(
        capabilities=capabilities, receipts=receipts, previous=previous, now=now
    )


def load_previous(out_path: Path) -> dict[str, dict[str, Any]] | None:
    """The prior artifact's per-capability records, keyed by id — or ``None`` when the
    prior artifact is absent/unparseable/carries no ``capabilities`` list.

    Repair finding I6: :func:`main` previously never wired this at all, so the engine's
    ``transition`` diff was permanently ``{"prev_seen": False, "prev_state": None, ...}``
    on every run, even the second one.
    """
    doc = _load_json(out_path)
    if not isinstance(doc, dict):
        return None
    rows = doc.get("capabilities")
    if not isinstance(rows, list):
        return None
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            out[row["id"]] = row
    return out or None


def render_summary(view: dict[str, Any]) -> str:
    summary = view["summary"]
    lines = [
        f"capability health ({view['schema']}) — {summary['n_capabilities']} capabilities, "
        f"observed_at {view['generated']['observed_at']}",
        f"  state:      {summary['by_state']}",
        f"  assessment: {summary['by_assessment_status']}",
    ]
    if summary["reason_codes"]:
        top = sorted(summary["reason_codes"].items(), key=lambda kv: (-kv[1], kv[0]))[:12]
        lines.append("  top reason codes:")
        lines += [f"    {count:>5}  {code}" for code, count in top]
    return "\n".join(lines)


def _sparse_default_out_guard(root: Path) -> str | None:
    """Non-``None`` when writing the DEFAULT ``data/`` output path would be unsafe in a
    sparse worktree (repair finding M5). Never applies to an explicit ``--out`` — that is
    always allowed, on purpose (tests, evidence runs, CI pointing elsewhere).
    """
    try:
        from scripts.worktree_sparse import missing_dirs  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — the guard itself must never crash the build
        return None
    try:
        missing = missing_dirs(root)
    except Exception:  # noqa: BLE001
        return None
    if "data" in missing:
        return (
            f"refusing to write the default output path '{DEFAULT_OUT_REL}' in a sparse "
            f"worktree (missing top-level dirs: {sorted(missing)}) — a write into an "
            f"omitted tree can truncate the committed artifact once this branch merges. "
            f"Pass --out explicitly (e.g. a scratchpad path) or run "
            f"'python3 scripts/worktree_sparse.py full' first."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--receipts-root", type=Path, default=None,
        help="override where receipt files (data/run_status.json, ...) are read from "
             "— sparse worktrees / tests / evidence runs",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help="output artifact path; default <root>/data/capability_health/state.json "
             "(refused in a sparse worktree unless given explicitly)",
    )
    parser.add_argument(
        "--now", default=None,
        help="ISO instant to resolve against (offset-bearing); default now(UTC)",
    )
    parser.add_argument("--json", action="store_true", help="also print the full JSON view")
    parser.add_argument("--summary", action="store_true", help="print the summary only; skip the write")
    args = parser.parse_args(argv)

    # M4: validate --now is a real, TZ-AWARE instant BEFORE any output_health pass — a
    # naive/invalid --now must fail loudly HERE, not be silently swallowed by
    # output_health_facts' own except-Exception-returns-unreadable guard deep in build().
    if args.now is None:
        now = datetime.now(timezone.utc)
    else:
        try:
            now = datetime.fromisoformat(args.now)
        except ValueError as exc:
            print(
                f"::error title=capability_health::--now {args.now!r} is not a valid "
                f"ISO instant ({exc})", flush=True,
            )
            return 2
    try:
        now = utc(now)
    except TemporalError as exc:
        print(
            f"::error title=capability_health::--now {args.now!r} must be tz-aware "
            f"({exc})", flush=True,
        )
        return 2

    out_path = args.out if args.out is not None else (args.root / DEFAULT_OUT_REL)

    if args.out is None:
        guard = _sparse_default_out_guard(args.root)
        if guard:
            print(f"::error title=capability_health::{guard}", flush=True)
            return 2

    previous = load_previous(out_path)

    try:
        view = build(args.root, now=now, receipts_root=args.receipts_root, previous=previous)
    except RegistryError as exc:
        # C3: fail CLOSED. Print every problem (bare print, never a logger — the
        # GitHub-annotation law), exit non-zero, WRITE NOTHING.
        for problem in str(exc).split("; "):
            print(f"::warning title=capability_health_registry::{problem}", flush=True)
        print(
            "::error title=capability_health::registry is invalid — refusing to write "
            "an artifact (any last-good state is left untouched)", flush=True,
        )
        return 1

    if args.summary:
        print(render_summary(view))
        return 0

    text = json.dumps(view, indent=2, sort_keys=True, default=str)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp.write_text(text + "\n", encoding="utf-8")
    tmp.replace(out_path)

    print(render_summary(view))
    if args.json:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
