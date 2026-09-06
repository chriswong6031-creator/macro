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
      ok      -> last_attempted = last_successful = checked_at (a genuine success) —
                 UNLESS a ``stale_series`` row also names this ref's group (see the
                 ROUND-5 paragraph below): a genuinely frozen series then forces the
                 SAME explicit ``state=stale`` override the ``stale`` status gets one
                 bullet down, on top of the ok/fresh attempt+success clocks.
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

    ROUND-4 REVIEW FINDING, CORRECTED BY ROUND-5: the round-3 fix above stopped a real
    false-corrupt bug but, taken alone, left the nightly-lane DATA axis with NOTHING to
    say when a series is genuinely frozen. This docstring previously implied the
    group-max ``status`` mapping above was the complete data-freshness signal for this
    source type — that claim was FALSE for exactly the poisoned-group case round-3
    protects: ``age = today - group_max_last`` can never exceed a cadence budget for a
    group whose max is a forward-dated projection series (fred's FEDTARMD FOMC-dot-plot
    shape), so ``status`` can never read anything but "ok" for that GROUP even when one
    of its OTHER series (e.g. CPIAUCSL) has gone stale for months.

    ROUND-5 REPAIR (this repair, item 1): the honest per-series receipt already exists
    and is immune to the group-max poisoning. ``collectors/base.py``'s
    ``detect_stale_series``/``_write_stale_series`` write named rows to
    ``run_status.json``'s TOP-LEVEL ``stale_series`` array — explicitly "for the health
    surface" per that module's own docstring — one row per ``(group, series)`` pair:
    ``{group, series, last_obs, cadence_days, age_days, detected_at}``, each comparing
    ONE series' own last observation against ITS OWN cadence budget, never the group
    max. :func:`nightly_lane_facts` now joins a ref's matching ``stale_series`` rows by
    EXACT ``group == ref`` string match (fred's rows carry ``group: "fred"``, identical
    to the ``fred`` nightly_lane ref) and, for a ``status`` in {ok, stale}, forces an
    explicit ``state=stale`` fact carrying a ``state_detail`` evidence string naming the
    frozen series/last_obs/age_days (capped and reason-join-scrubbed by
    ``engine.capability_health``'s ``_cap_foreign_text`` boundary — the same one round-3
    item 4 already applies to ``blind_reason``/``rights_detail``). The ABSENCE of a
    matching ``stale_series`` row, combined with ``status=ok``, is what actually
    composes to "healthy" here: the OWNING collector's own staleness detector found
    nothing wrong on EITHER axis it knows how to check (group-max attempt/success via
    ``status``, AND per-series frozen-tail via ``stale_series``) — never a silent
    omission of the data-freshness check. A malformed ``stale_series`` row (not a dict,
    or missing/non-string ``group``) is skipped fail-safe and can never by itself brand
    a source corrupt; a row that DOES match the group but carries unparseable
    ``series``/``age_days``/``last_obs`` fields still forces the stale state — the JOIN
    (the group match) is what matters, and a row with messy detail fields must never
    silently read as though it had never matched at all.
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


def _stale_series_index(doc: Any) -> dict[str, list[dict[str, Any]]]:
    """``group`` -> every raw ``stale_series`` row naming that group.

    ROUND-5 repair (item 1): ``collectors/base.py``'s ``detect_stale_series``/
    ``_write_stale_series`` write named rows to ``run_status.json``'s top-level
    ``stale_series`` array explicitly "for the health surface" — one row per
    ``(group, series)`` pair, immune to the group-max ``last``/``status`` poisoning a
    forward-dated projection series (fred's FEDTARMD shape) causes (see this module's
    docstring, ROUND-5 paragraph). A malformed row — not a dict, or with a missing/
    non-string ``group`` — is skipped FAIL-SAFE here: it can never by itself brand a
    source corrupt. Only a row that genuinely NAMES a group is indexed at all; whether
    ITS OTHER fields are also clean is decided by :func:`_stale_series_detail`, not
    here — a row that matches the group must still force the stale state even when its
    remaining fields are messy (never silently dropped for that reason).
    """
    index: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(doc, dict):
        return index
    rows = doc.get("stale_series")
    if not isinstance(rows, list):
        return index
    for row in rows:
        if not isinstance(row, dict):
            continue
        group = row.get("group")
        if not isinstance(group, str) or not group:
            continue
        index.setdefault(group, []).append(row)
    return index


def _stale_series_detail(ref: str, rows: list[dict[str, Any]]) -> str:
    """One evidence-detail string naming every ``stale_series`` row joined onto *ref*.

    A row that matched the group but carries an unparseable/missing ``series``,
    ``age_days`` or ``last_obs`` still contributes a ``?`` placeholder for that field
    rather than being dropped outright — the JOIN (the group match) is what forces the
    stale state; a row with messy detail fields must never silently read as though it
    had never matched at all (round-5 repair, item 1). Capped again at the engine
    boundary (``engine.capability_health._cap_foreign_text``) before publication —
    this builder-side text is not itself length-bounded, matching the existing
    rights_detail precedent (MINOR-4: builder caps for its OWN known shape; the engine
    boundary is the one guarantee that holds for every adapter).
    """
    parts: list[str] = []
    for row in sorted(rows, key=lambda r: str(r.get("series") or "")):
        series = row.get("series")
        series_s = series if isinstance(series, str) and series else "?"
        age = row.get("age_days")
        age_s = str(age) if isinstance(age, (int, float)) and not isinstance(age, bool) else "?"
        last_obs = row.get("last_obs")
        last_obs_s = last_obs if isinstance(last_obs, str) and last_obs else "?"
        parts.append(f"{series_s} last_obs={last_obs_s} age_days={age_s}")
    return f"frozen-tail (stale_series) for {ref}: " + ", ".join(parts)


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

    ROUND-5 repair (item 1, see the module docstring's ROUND-5 paragraph for the full
    rationale): a ``status`` of ``ok``/``stale`` also gets joined against
    ``run_status.json``'s top-level ``stale_series`` array by exact ``group == ref``
    match. A match forces ``state=stale`` (already implied for ``status=stale``; new
    for ``status=ok``) plus a ``state_detail`` evidence string — this is the fact-level
    mechanism that lets a genuinely frozen series in an otherwise "ok" group be
    reported, since the group-max ``status`` alone can never see it.
    """
    doc = _load_json(receipts_root / RUN_STATUS_REL)
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(doc, dict):
        for ref in refs:
            out[ref] = {"readable": False}
        return out
    sources = doc.get("sources") if isinstance(doc.get("sources"), dict) else {}
    stale_index = _stale_series_index(doc)
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

        # ROUND-5 repair (item 1): join the honest PER-SERIES data-freshness receipt
        # onto a status=ok/stale ref. Restricted to these two statuses on purpose: a
        # stale_series row is only ever written off a SUCCESSFUL fetch (collectors/
        # base.py calls detect_stale_series after `frames = adapter.fetch(...)`
        # succeeds), so a persisted row surviving into a run where THIS ref's status
        # is failed/dead/blocked/skipped/unknown would be describing a PRIOR run's
        # frozen tail, not this one's — forcing an explicit stale verdict there could
        # silently downgrade what would otherwise be could_not_look (a worse, more
        # honest verdict for "attempted, no prior success" or a rights block) into a
        # milder stale. ok/stale is exactly the shape the round-4 review named: a
        # fresh, "healthy-looking" attempt/success clock pair that the group-max
        # `status` alone cannot tell apart from a genuinely frozen sibling series.
        if status in (_STATUS_OK, _STATUS_STALE):
            stale_rows = stale_index.get(ref)
            if stale_rows:
                fact["state"] = STATE_STALE
                fact["state_detail"] = _stale_series_detail(ref, stale_rows)
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
