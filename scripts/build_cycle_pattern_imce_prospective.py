"""IMCE A5B/A5C nightly builder — data/cycle_pattern/imce_prospective_observation_v1.jsonl.

Reads the published, R2-hosted ``event_workspace.v1`` objects for the four
homebuilder issuers (DHI/PHM/KBH/TOL), and — after stamping/confirming
activation — appends immutable decision-time IMCE observation/correction
packets for qualifying post-activation earnings events through
``engine.cycle_pattern.imce_prospective``.

IMCE A5C (Sol A5C directive, 2026-08-23, frozen spec D1/D3): the marker/
generation/workspace GET sequence — and the ordered source-revision chain
walk (frozen spec D2) — now live ONCE, in
``engine.neuralweb.company_intelligence_reader``. This module's
``_load_workspace_with_disposition`` is a thin disposition classifier over
that ONE shared implementation (``ci_reader.load_current_workspace`` for
the current-generation disposition scan, ``ci_reader.
read_all_event_source_revisions`` for the ordered-revision chain walk this
module's eligibility/replay logic needs — production incident addendum,
2026-08-23: ONE shared walk harvests EVERY candidate event's own history in
a single pass, replacing a per-candidate walk that independently re-walked
the same marker->predecessor chain once per event) — the former duplicate
GET implementation (``_raw_fetch_workspace``) is RETIRED; it no longer
exists in this file.

On ANY fetch_failed anywhere in a run — including a chain-integrity or
chain-read failure surfaced while resolving a found candidate's ordered
revision history — EVERY observation this run is deferred (no row written,
no activation stamped if this is the first run) — the roster is fixed and
every observation pools over the same four tickers, so a failure on any one
of them taints every pooled read equally; the next nightly retries cleanly
since nothing was written.

IMCE A5C eligibility/replay/contributor laws (Sol A5C directive, frozen
spec E/F/G): a candidate event's EARLIEST known source revision decides
eligibility, permanently — a correction can never move an event across the
activation boundary in either direction (E). The ONE immutable observation
is minted from the EARLIEST ELIGIBLE revision's own workspace, with
``decision_cutoff`` = that revision's own ``source_available_at`` — later,
materially different revisions accumulated between nightlies become ordered
correction rows in ascending source order; a cosmetic (non-materially-
different) regeneration produces no correction noise (F). A contributor's
state at a trigger's cutoff is the LATEST lawful revision of that
contributor's own event whose ``source_available_at <= cutoff`` — walking
the contributor's own chain, never a later correction used retrospectively
(G). When an event's chain cannot be established (a chain-integrity
failure), this module fails CLOSED — no observation, ever, for that
candidate this run (deferred, per the fetch_failed law above).

A5C safety law (Sol A5C review, 2026-08-23, item 1; hardened by the Opus
red-team BLOCKER-1 fix, same day): this builder reads the workspace it is
about to MINT AN OBSERVATION FROM (the earliest eligible revision — E/F
above) — its OWN ``lifecycle.state`` AND its issuer_release source row
``form`` — and passes BOTH through to ``append_observation`` as
``trigger_lifecycle_state``/``trigger_source_form`` — it never decides
safety itself; ``engine.cycle_pattern.imce_prospective`` is the sole
enforcement point (a builder-only check would be insufficient — see that
module's docstring). A refusal there is PER-CANDIDATE only: it does not join
``failed_ids`` (never defers the whole night), does not stamp/unstamp
activation, and does not block any other candidate in the same run; it is
counted separately in ``summary["n_observations_refused_unsafe_correction"]``.

Fail-open, house pattern (cf. scripts/build_cycle_pattern_state.py) for
everything EXCEPT the production-write gate itself: every input is guarded;
a missing/unreadable input degrades to a no-op run with a logged note, never
a crash.

Production-flag law (red-team M7): this builder is the ONLY caller
authorized to touch the production ledger, and it must say so explicitly.
``run(production=True)`` (equivalently ``--production`` on the CLI) is
required — a bare invocation refuses to write anything (activation included)
and reports why. The nightly step passes ``--production`` explicitly (see
scripts/ci/daily_engine_regional_desk_builders.sh's cl_misc()).

DAILY-ONLY: the single-writer forward-ledger discipline (CLAUDE.md "Ledgers:
nightly is the sole advancer of forward ledgers") means this builder runs in
daily.yml's cl_misc band only, never in a render/engine-render re-render
lane and never in the three-hour company-intelligence workflow that
publishes the source event_workspaces this module reads.

Run:  python -m scripts.build_cycle_pattern_imce_prospective --production
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.neuralweb import company_intelligence_reader as ci_reader  # noqa: E402

log = logging.getLogger("build_cycle_pattern_imce_prospective")

# Bounded candidate lookback: current + prior fiscal year, all four quarters.
# Mechanical/operational scan window only — never a construction choice. A
# missed nightly run is covered on the NEXT run because event_ids are
# content-addressed by (issuer, fiscal period), not by a "latest" pointer,
# and first-observation-wins makes a rediscovered event idempotent.
_CANDIDATE_YEARS_BACK = 1
_CANDIDATE_QUARTERS = (1, 2, 3, 4)


def _issuer_release_source_form(workspace: dict) -> str | None:
    """The bound filing's own SEC-assigned form ("8-K"/"8-K/A") off the
    workspace's issuer_release source row — A5C BLOCKER-1 (1c), the second
    fail-closed signal alongside lifecycle.state (see
    engine.cycle_pattern.imce_prospective.is_safe_original_source_form).
    None if the row or field is absent (fails closed downstream, never
    silently substituted for "8-K"). NEW-2 fix (Opus red-team round 2,
    2026-08-23): this reads the PUBLISHED value verbatim, which since that
    fix genuinely CAN be absent/None (the producer no longer manufactures
    "8-K" from nothing) — this function was already honest about that; it
    is the producer side that was fixed, not this reader."""
    for source in workspace.get("sources") or []:
        if isinstance(source, dict) and source.get("kind") == "issuer_release":
            form = source.get("form")
            return str(form) if form else None
    return None


# IMCE A5C (frozen spec D1/D3): the ONE shared reader implementation lives
# in engine.neuralweb.company_intelligence_reader. _NotPublished is an ALIAS
# of that module's own exception class — not a lookalike — so a stub raising
# ``b._NotPublished(...)`` in a test and the shared reader's real raise are
# the exact same, catchable-together exception identity. The former
# duplicate GET implementation (``_raw_fetch_workspace``) is RETIRED and no
# longer exists in this file (mutation-kill test: it must not be importable).
_NotPublished = ci_reader.WorkspaceChainNotPublished


def _load_workspace_with_disposition(event_id: str, *, fetch=None) -> tuple[dict | None, str]:
    """(workspace_or_None, disposition) in {"found", "not_published", "fetch_failed"}.

    *fetch* is injectable for tests (a stub raising _NotPublished for a clean
    404, any other exception for a network failure, or returning a dict for
    a hit) — production callers never pass it, always exercising the ONE
    shared reader implementation via ``ci_reader.load_current_workspace``.
    """
    fetcher = fetch or ci_reader.load_current_workspace
    try:
        return fetcher(event_id), "found"
    except _NotPublished as exc:
        log.debug("%s: not published (%s)", event_id, exc)
        return None, "not_published"
    except Exception as exc:  # noqa: BLE001 — every other failure is fetch_failed, never silently absent
        log.info("%s: workspace fetch failed, classified fetch_failed (%s)", event_id, exc)
        return None, "fetch_failed"


def harvest_event_revisions(event_ids) -> dict[str, list[dict]]:
    """Ordered (oldest -> newest) source revisions for EVERY one of
    *event_ids*, via ONE shared reader chain-walk (frozen spec D2(d)).

    Production incident addendum (2026-08-23): this REPLACES a former
    per-candidate walk (``_load_event_revision_history(event_id)``, called
    once per candidate in a loop) — a live measurement against the
    post-incident ~170-generation backfilled chain found a single-event
    walk cost 153 SECONDS; this builder was paying that ~8 times per run
    (~20 minutes of pure chain-walking against the ~67-minute nightly
    render budget). The walk is IDENTICAL for every candidate in one run —
    ``ci_reader.read_all_event_source_revisions`` fetches each generation's
    manifest exactly ONCE and extracts every requested event's own
    revisions from that SAME pass (was O(candidates x hops); now O(hops)).

    Raises on ANY chain-integrity or network failure — never silently
    returns a truncated or partial mapping; the caller treats any
    exception here exactly like a disposition-level fetch_failed for EVERY
    requested id (defers the whole run — E4 fail-closed). A module-level
    indirection point so tests can inject a stub the same way they already
    stub ``_fetch_all_candidates``."""
    return ci_reader.read_all_event_source_revisions(event_ids)


def _candidate_event_ids(ticker: str, company_id: str, today: date) -> list[str]:
    from engine.company_intelligence.events import FiscalPeriod, canonical_event_id

    ids: list[str] = []
    for year in range(today.year - _CANDIDATE_YEARS_BACK, today.year + 1):
        for q in _CANDIDATE_QUARTERS:
            try:
                fp = FiscalPeriod(year=year, quarter=q)
                ids.append(canonical_event_id(company_id, fp))
            except Exception as exc:  # noqa: BLE001 — a bad candidate is just skipped
                log.debug("%s: candidate %s-q%s rejected (%s)", ticker, year, q, exc)
    return ids


def _fetch_all_candidates(today: date) -> tuple[dict[str, list[dict]], dict[str, dict[str, str]]]:
    """ticker -> list of published workspaces found (any order); and
    ticker -> {event_id: disposition} for every candidate scanned."""
    from engine.company_intelligence.issuer_profiles import HOMEBUILDER_TICKERS, issuer_for_ticker

    found: dict[str, list[dict]] = {t: [] for t in HOMEBUILDER_TICKERS}
    dispositions: dict[str, dict[str, str]] = {t: {} for t in HOMEBUILDER_TICKERS}
    for ticker in HOMEBUILDER_TICKERS:
        issuer = issuer_for_ticker(ticker)
        if issuer is None:
            log.warning("%s: no registered issuer identity — skipped", ticker)
            continue
        for event_id in _candidate_event_ids(ticker, issuer.company_id, today):
            ws, disposition = _load_workspace_with_disposition(event_id)
            dispositions[ticker][event_id] = disposition
            if ws is not None:
                found[ticker].append(ws)
    return found, dispositions


def _latest_contributor_revision_at_or_before(
    ticker: str,
    found: dict[str, list[dict]],
    revision_histories: dict[str, list[dict]],
    cutoff_iso: str,
) -> dict | None:
    """G (frozen spec): the LATEST LAWFUL revision of *ticker* — across
    EVERY one of its own candidate events' own revision chains — whose
    source_available_at is <= cutoff_iso. Never uses a later correction
    retrospectively: only revisions individually at-or-before the cutoff are
    even considered. None if no such revision exists.

    Calendar-quarter pooling-key alignment (red-team M5) and denominator
    conformance are enforced downstream, inside
    engine.cycle_pattern.imce_prospective.per_issuer_state — this helper
    only bounds by PIT-knowability across the CHAIN, exactly as
    ``_latest_snapshot_at_or_before`` did across single current snapshots
    before A5C.
    """
    from engine.cycle_pattern.imce_prospective import parse_iso

    cutoff = parse_iso(cutoff_iso)
    best_ws: dict | None = None
    best_dt = None
    for candidate_ws in found.get(ticker, []):
        event_id = candidate_ws.get("event_id")
        for revision in revision_histories.get(event_id, []) or []:
            src = revision.get("source_available_at")
            if not src:
                continue
            try:
                dt = parse_iso(src)
            except Exception:  # noqa: BLE001
                continue
            if dt > cutoff:
                continue
            if best_dt is None or dt > best_dt:
                best_ws, best_dt = revision.get("workspace"), dt
    return best_ws


def run(production: bool = False) -> dict:
    """Returns a small summary dict (also useful for tests).

    production=False (the default — a bare invocation) refuses to touch the
    production ledger at all: it logs why and returns immediately, before
    ever calling ensure_activation or fetching a single candidate. Only the
    nightly step's explicit --production flag flows through to True.
    """
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    summary = {
        "production": production, "activated": False, "activation_started_at": None,
        "n_candidates": 0, "n_observations_appended": 0, "n_observations_noop": 0,
        "n_corrections": 0, "n_observations_refused_unsafe_correction": 0,
        "deferred_fetch_failed": [], "errors": [],
    }

    if not production:
        msg = "production flag not set — refusing to touch the production ledger (pass --production / run(production=True))"
        log.error(msg)
        summary["errors"].append(msg)
        return summary

    from engine.cycle_pattern.imce_prospective import (
        ROSTER,
        append_correction,
        append_observation,
        assert_no_outcome_fields,
        build_observation_packet,
        ensure_activation,
        find_observation_by_event_id,
        load_rows,
        packet_materially_differs,
        parse_iso,
    )

    today = date.today()

    # M7(c): fetch candidates BEFORE stamping activation — a first run whose
    # manifest read fails must not burn the activation clock on a night it
    # never actually observed anything.
    try:
        found, dispositions = _fetch_all_candidates(today)
    except Exception as exc:  # noqa: BLE001
        log.error("candidate discovery failed: %s", exc)
        summary["errors"].append(f"candidate_discovery: {exc}")
        return summary

    failed_ids = [
        event_id for per_ticker in dispositions.values()
        for event_id, disposition in per_ticker.items() if disposition == "fetch_failed"
    ]

    # IMCE A5C (frozen spec D2(c)/D2(d)/E4): for every FOUND candidate,
    # resolve its ordered source-revision chain BEFORE activation too — a
    # chain-integrity or network failure while walking history is exactly
    # the "network was down" ambiguity the fetch_failed law already exists
    # to catch, discovered one layer deeper (a broken chain link, or an
    # unbounded walk, is a hard failure, never a silent skip or truncation).
    #
    # Production incident addendum (2026-08-23): ONE shared walk
    # (harvest_event_revisions) covers EVERY candidate this run — the walk
    # itself is IDENTICAL regardless of which event_ids are requested, so
    # calling it once per candidate (the former shape) paid the SAME
    # marker->predecessor traversal repeatedly. A shared-walk failure is
    # classified fetch_failed for EVERY requested candidate at once — the
    # same outcome each one would have reached independently anyway, since
    # every per-event walk traverses the identical chain depth regardless
    # of where its own event happens to appear in it.
    candidate_event_ids = {
        str(ws["event_id"]) for per_ticker_found in found.values()
        for ws in per_ticker_found if ws.get("event_id")
    }
    revision_histories: dict[str, list[dict]] = {}
    if candidate_event_ids:
        try:
            revision_histories = harvest_event_revisions(candidate_event_ids)
        except Exception as exc:  # noqa: BLE001 - chain ambiguity is fetch_failed-equivalent for EVERY candidate
            log.info(
                "shared revision-history walk failed, classifying every candidate fetch_failed (%s)", exc,
            )
            failed_ids.extend(sorted(candidate_event_ids))

    if failed_ids:
        # Red-team N4: a deferral this important must be visible in the
        # Actions summary, not just the log — GitHub only parses "::" at
        # column 0, so this MUST be a bare print (never log.*, which
        # prefixes the line and makes GitHub silently drop it; flush=True
        # is load-bearing because stdout is block-buffered when piped).
        print(
            "::warning title=imce-prospective-deferred::"
            f"{len(failed_ids)} fetch_failed candidate(s), deferring ALL observations "
            f"this run (a network failure must never be minted as source absence): "
            f"{failed_ids}",
            flush=True,
        )
        log.warning(
            "imce_prospective: %d fetch_failed candidate(s) — deferring ALL observations "
            "this run (B3: a network failure must never be minted as source absence): %s",
            len(failed_ids), failed_ids,
        )
        summary["deferred_fetch_failed"] = failed_ids
        return summary

    n_candidates = sum(len(v) for v in found.values())
    summary["n_candidates"] = n_candidates
    log.info("imce_prospective: discovered %d published workspace(s) across %s (0 fetch failures)",
              n_candidates, list(found))

    try:
        activation = ensure_activation(production=True)
        summary["activated"] = True
        summary["activation_started_at"] = activation["activation_started_at"]
    except Exception as exc:  # noqa: BLE001 — never take the nightly down
        log.error("ensure_activation failed: %s", exc)
        summary["errors"].append(f"ensure_activation: {exc}")
        return summary

    activation_started_at = activation["activation_started_at"]

    for trigger_ticker in ROSTER:
        for trigger_ws in found.get(trigger_ticker, []):
            event_id = trigger_ws.get("event_id")
            if not event_id:
                continue
            revisions = revision_histories.get(event_id) or []
            if not revisions:
                # A candidate the disposition scan found, but the chain walk
                # surfaced nothing for — treat as nothing to observe this
                # run rather than guessing (should not occur on the real
                # nightly path: a successful "found" disposition read
                # already proves at least one revision exists).
                continue

            # BLOCKER-1 (Opus red-team, 2026-08-23): the chain walk's OWN
            # return order (oldest -> newest) is a construction detail of
            # read_event_source_revisions, not a guarantee this builder may
            # lean on for a PERMANENT eligibility decision — a caller-
            # injected or otherwise reordered revision list must not silently
            # decide eligibility off revisions[0]. Sort by
            # source_available_at FIRST; every downstream use (eligibility
            # AND replay, F1) reads from this ONE sorted list, never the raw
            # chain-order list again.
            ordered = sorted(
                (r for r in revisions if r.get("source_available_at")),
                key=lambda r: parse_iso(r["source_available_at"]),
            )
            if not ordered:
                summary["errors"].append(f"{event_id}: no revision carries a usable source_available_at")
                continue

            earliest = ordered[0]
            earliest_avail = earliest["source_available_at"]

            # E1/E2/E3 (frozen spec): the EARLIEST known revision's
            # source_available_at decides eligibility, PERMANENTLY — a
            # later correction can never move the event across the
            # activation boundary in either direction. This is also the
            # builder-level fence; the module ALSO enforces the activation
            # law independently on write (M7).
            try:
                if parse_iso(earliest_avail) < parse_iso(activation_started_at):
                    log.info(
                        "%s %s: permanently ineligible — earliest known revision (%s) predates "
                        "activation (%s)", trigger_ticker, event_id, earliest_avail, activation_started_at,
                    )
                    continue
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"{event_id}: activation_check: {exc}")
                continue

            # M4: an event_id carries at most ONE observation, ever.
            existing_obs = find_observation_by_event_id(event_id)
            anchor_observation_id = existing_obs.get("observation_id") if existing_obs else None
            last_recorded_packet = existing_obs

            # Idempotency across nightly runs (F1/F3 replay): which
            # revisions has THIS event already recorded — as the
            # observation, or as a correction? Only genuinely NEW revisions
            # (accumulated since the last nightly) are replayed below.
            recorded_generation_ids: set[str] = set()
            if existing_obs is not None:
                gen = (existing_obs.get("trigger") or {}).get("event_workspace_generation_id")
                if gen:
                    recorded_generation_ids.add(gen)
            for row in load_rows():
                if row.get("row_kind") != "correction":
                    continue
                if (row.get("trigger") or {}).get("event_id") != event_id:
                    continue
                gen = (row.get("trigger") or {}).get("event_workspace_generation_id")
                if gen:
                    recorded_generation_ids.add(gen)
                    row_gen_is_newer = last_recorded_packet is None or gen != (
                        last_recorded_packet.get("trigger") or {}
                    ).get("event_workspace_generation_id")
                    if row_gen_is_newer:
                        last_recorded_packet = row

            # F1: replay the SAME ascending-order list eligibility was
            # decided from above — never re-derived here (BLOCKER-1).
            for revision in ordered:
                gen_id = revision.get("generation_id")
                decision_cutoff = revision.get("source_available_at")
                if gen_id and gen_id in recorded_generation_ids:
                    continue  # already recorded in a prior nightly run

                revision_ws = revision.get("workspace") or {}
                # G (frozen spec): every OTHER roster ticker's contributor
                # state is the LATEST LAWFUL revision of ITS OWN chain
                # whose source_available_at <= THIS revision's own cutoff —
                # never a later correction used retrospectively.
                issuer_workspaces: dict[str, dict | None] = {
                    t: (
                        revision_ws if t == trigger_ticker
                        else _latest_contributor_revision_at_or_before(
                            t, found, revision_histories, decision_cutoff,
                        )
                    )
                    for t in ROSTER
                }

                try:
                    packet = build_observation_packet(
                        trigger_ticker=trigger_ticker,
                        trigger_workspace=revision_ws,
                        issuer_workspaces=issuer_workspaces,
                        activation_started_at=activation_started_at,
                    )
                    assert_no_outcome_fields(packet)
                except Exception as exc:  # noqa: BLE001
                    log.error("%s %s: packet build failed (%s)", trigger_ticker, event_id, exc)
                    summary["errors"].append(f"{event_id}: packet_build: {exc}")
                    if anchor_observation_id is None:
                        # BLOCKER-1: this WOULD have been the anchor (earliest
                        # eligible) mint — a build failure here must never
                        # let the loop fall through to mint from a LATER
                        # revision instead. Abandon this event for tonight
                        # (recorded above); the next nightly retries cleanly.
                        break
                    continue

                if anchor_observation_id is None:
                    # F2: THE one immutable observation, minted from the
                    # EARLIEST ELIGIBLE revision — safe-original by
                    # construction (WORLD STATE note).
                    try:
                        # A5C (Sol, 2026-08-23, item 1) + BLOCKER-1
                        # hardening (Opus red-team, same day): read THIS
                        # (the minting) revision's OWN lifecycle state AND
                        # its issuer_release source-row form, and pass both
                        # through untouched — the engine module decides
                        # safety, this builder never does.
                        trigger_lifecycle_state = (revision_ws.get("lifecycle") or {}).get("state")
                        trigger_source_form = _issuer_release_source_form(revision_ws)
                        row, appended = append_observation(
                            packet, production=True,
                            trigger_lifecycle_state=trigger_lifecycle_state,
                            trigger_source_form=trigger_source_form,
                        )
                        if appended:
                            summary["n_observations_appended"] += 1
                            anchor_observation_id = row["observation_id"]
                            last_recorded_packet = row
                            log.info(
                                "%s %s: observation appended (label=%s pooled_state=%s)",
                                trigger_ticker, event_id, packet["m_t"]["label"], packet["m_t"]["pooled_state"],
                            )
                        elif row is None:
                            # A5C refusal: no row of any kind was written.
                            # Per-candidate only — other candidates this run
                            # are unaffected, activation stays as already
                            # stamped above. Nothing else in this revision
                            # list may be processed without an anchoring
                            # observation.
                            summary["n_observations_refused_unsafe_correction"] += 1
                            break
                        else:
                            summary["n_observations_noop"] += 1
                            anchor_observation_id = row["observation_id"]
                            last_recorded_packet = row
                    except Exception as exc:  # noqa: BLE001
                        log.error("%s %s: observation append failed (%s)", trigger_ticker, event_id, exc)
                        summary["errors"].append(f"{event_id}: observation_append: {exc}")
                        break
                else:
                    # F3/F4: a later revision is an ordered correction only
                    # if it MATERIALLY differs from the last recorded state
                    # — a cosmetic regeneration produces no correction noise.
                    if last_recorded_packet is not None and not packet_materially_differs(
                        last_recorded_packet, packet, trigger_ticker,
                    ):
                        summary["n_observations_noop"] += 1
                        continue
                    try:
                        old_gen = (
                            (last_recorded_packet.get("trigger") or {}).get("event_workspace_generation_id")
                            if last_recorded_packet else None
                        )
                        new_gen = packet.get("trigger", {}).get("event_workspace_generation_id")
                        corr = append_correction(
                            superseded_observation_id=anchor_observation_id,
                            corrected_packet=packet,
                            reason=f"source revision detected: generation {old_gen} -> {new_gen}, derived state changed",
                            production=True,
                        )
                        summary["n_corrections"] += 1
                        last_recorded_packet = corr
                        log.info("%s %s: correction appended (material source revision)", trigger_ticker, event_id)
                    except Exception as exc:  # noqa: BLE001
                        summary["errors"].append(f"{event_id}: correction_append: {exc}")

    elapsed = time.time() - t0
    log.info(
        "imce_prospective: done in %.1fs — candidates=%d appended=%d noop=%d corrections=%d "
        "refused_unsafe_correction=%d errors=%d",
        elapsed, summary["n_candidates"], summary["n_observations_appended"],
        summary["n_observations_noop"], summary["n_corrections"],
        summary["n_observations_refused_unsafe_correction"], len(summary["errors"]),
    )
    return summary


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--production", action="store_true",
        help="Required to write the production ledger. The nightly cl_misc step passes this "
             "explicitly; a bare invocation without it is a safe no-op (refuses every write).",
    )
    args = ap.parse_args(argv)
    run(production=args.production)


if __name__ == "__main__":
    main()
