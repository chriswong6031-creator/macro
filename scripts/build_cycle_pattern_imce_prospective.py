"""IMCE A5B nightly builder — data/cycle_pattern/imce_prospective_observation_v1.jsonl.

Reads the published, R2-hosted ``event_workspace.v1`` objects for the four
homebuilder issuers (DHI/PHM/KBH/TOL), and — after stamping/confirming
activation — appends one immutable decision-time IMCE observation packet
per qualifying post-activation earnings event through
``engine.cycle_pattern.imce_prospective``.

HONEST CLAIM (red-team N2 correction — an earlier draft of this docstring
and the workstream record overstated this as "no second reader
implementation", which was false the moment B3's fix landed): this module's
``_raw_fetch_workspace``/``_load_workspace_with_disposition`` IS a second
fetch implementation. It duplicates ``scripts.refresh_event_workspaces.
load_prior_workspace``'s base-URL resolution and manifest+workspace GET
sequence byte-for-byte, on purpose, because that existing reader is
deliberately fail-soft FOR ITS OWN callers (a flaky CDN must never block a
source-identical no-op rebuild) and therefore collapses "clean 404" and
"network error" into the same ``None`` — exactly the ambiguity B3 requires
this module to resolve (``found`` / ``not_published`` / ``fetch_failed``). A
prospective observation must never mint "the issuer had no event" out of
"the network was down." Two independent implementations of the SAME GET
sequence is a real, named drift risk: if the R2 layout, headers, or
base-URL resolution ever changes, both copies must be updated together, and
nothing here enforces that. The correct long-term fix is to lift a
disposition-aware fetch (or a ``raise_on_error``/mode parameter) INTO
``scripts/refresh_event_workspaces.py`` itself, so there is one
implementation with two calling conventions — deliberately NOT done in this
PR (that file is A5A's, out of this build's scope; the red-team review
authorized the duplication here rather than a cross-scope refactor). Future
consolidation should retire ``_raw_fetch_workspace`` in favor of that
lifted, shared implementation.

On ANY fetch_failed anywhere in a run, EVERY observation this run is
deferred (no row written, no activation stamped if this is the first run)
— the roster is fixed and every observation pools over the same four
tickers, so a failure on any one of them taints every pooled read equally;
the next nightly retries cleanly since nothing was written.

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

log = logging.getLogger("build_cycle_pattern_imce_prospective")

# Bounded candidate lookback: current + prior fiscal year, all four quarters.
# Mechanical/operational scan window only — never a construction choice. A
# missed nightly run is covered on the NEXT run because event_ids are
# content-addressed by (issuer, fiscal period), not by a "latest" pointer,
# and first-observation-wins makes a rediscovered event idempotent.
_CANDIDATE_YEARS_BACK = 1
_CANDIDATE_QUARTERS = (1, 2, 3, 4)


class _NotPublished(Exception):
    """A clean 404 (or an absent-generation manifest) — the event genuinely
    is not published yet. Distinct from any other fetch failure."""


def _raw_fetch_workspace(event_id: str, *, base_url: str | None = None) -> dict:
    """Fetch one workspace over HTTP, mirroring scripts.refresh_event_workspaces.
    load_prior_workspace's own base-URL resolution and GET sequence.

    Raises _NotPublished on a clean 404/absent-generation manifest. Raises
    any OTHER exception (network error, timeout, non-2xx, malformed JSON) on
    a genuine fetch failure — never returns None; disposition classification
    is the caller's job (_load_workspace_with_disposition), so a network
    outage can never be silently read as "this issuer had no event."
    """
    import os

    import requests

    from scripts.refresh_event_workspaces import _DEFAULT_PUBLIC_ORIGIN

    base = (base_url or os.environ.get("COMPANY_INTELLIGENCE_R2_BASE_URL", _DEFAULT_PUBLIC_ORIGIN)).strip().rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "mastermind-event-workspaces/1"}

    marker_resp = requests.get(f"{base}/event_workspaces/manifest.json", headers=headers, timeout=20)
    if marker_resp.status_code == 404:
        raise _NotPublished(f"{event_id}: manifest 404")
    marker_resp.raise_for_status()
    marker = marker_resp.json()
    generation_id = str((marker or {}).get("generation_id") or "")
    if not generation_id:
        raise _NotPublished(f"{event_id}: manifest carries no generation_id")

    workspace_resp = requests.get(
        f"{base}/event_workspaces/generations/{generation_id}/workspaces/{event_id}.json",
        headers=headers, timeout=20,
    )
    if workspace_resp.status_code == 404:
        raise _NotPublished(f"{event_id}: workspace 404 in generation {generation_id}")
    workspace_resp.raise_for_status()
    payload = workspace_resp.json()
    if not isinstance(payload, dict):
        raise ValueError(f"{event_id}: workspace payload is not a dict")
    return payload


def _load_workspace_with_disposition(event_id: str, *, fetch=None) -> tuple[dict | None, str]:
    """(workspace_or_None, disposition) in {"found", "not_published", "fetch_failed"}.

    *fetch* is injectable for tests (a stub raising _NotPublished for a clean
    404, any other exception for a network failure, or returning a dict for
    a hit) — production callers never pass it, always exercising the real
    HTTP path via _raw_fetch_workspace.
    """
    fetcher = fetch or _raw_fetch_workspace
    try:
        return fetcher(event_id), "found"
    except _NotPublished as exc:
        log.debug("%s: not published (%s)", event_id, exc)
        return None, "not_published"
    except Exception as exc:  # noqa: BLE001 — every other failure is fetch_failed, never silently absent
        log.info("%s: workspace fetch failed, classified fetch_failed (%s)", event_id, exc)
        return None, "fetch_failed"


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


def _latest_snapshot_at_or_before(workspaces: list[dict], cutoff_iso: str) -> dict | None:
    """The workspace with the LATEST source_available_at that is still
    <= cutoff_iso (PIT-knowability bound). None if no such snapshot exists.

    Calendar-quarter pooling-key alignment (red-team M5) is enforced
    downstream, inside engine.cycle_pattern.imce_prospective.per_issuer_state
    — this helper only bounds by PIT-knowability, exactly as before.
    """
    from engine.cycle_pattern.imce_prospective import parse_iso

    cutoff = parse_iso(cutoff_iso)
    best: dict | None = None
    best_dt = None
    for ws in workspaces:
        src = (ws.get("lifecycle") or {}).get("source_available_at")
        if not src:
            continue
        try:
            dt = parse_iso(src)
        except Exception:  # noqa: BLE001
            continue
        if dt > cutoff:
            continue
        if best_dt is None or dt > best_dt:
            best, best_dt = ws, dt
    return best


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
        "n_corrections": 0, "deferred_fetch_failed": [], "errors": [],
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
            lifecycle = trigger_ws.get("lifecycle") or {}
            decision_cutoff = lifecycle.get("source_available_at")
            event_id = trigger_ws.get("event_id")
            if not decision_cutoff or not event_id:
                continue

            # Activation law on the TRIGGER itself (builder-level fence; the
            # module ALSO enforces this independently on write — M7).
            try:
                if parse_iso(decision_cutoff) < parse_iso(activation_started_at):
                    log.info("%s %s: pre-activation trigger event skipped (%s < %s)",
                             trigger_ticker, event_id, decision_cutoff, activation_started_at)
                    continue
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"{event_id}: cutoff parse failed ({exc})")
                continue

            issuer_workspaces: dict[str, dict | None] = {
                t: _latest_snapshot_at_or_before(found.get(t, []), decision_cutoff) for t in ROSTER
            }

            try:
                packet = build_observation_packet(
                    trigger_ticker=trigger_ticker,
                    trigger_workspace=trigger_ws,
                    issuer_workspaces=issuer_workspaces,
                    activation_started_at=activation_started_at,
                )
                assert_no_outcome_fields(packet)
            except Exception as exc:  # noqa: BLE001
                log.error("%s %s: packet build failed (%s)", trigger_ticker, event_id, exc)
                summary["errors"].append(f"{event_id}: packet_build: {exc}")
                continue

            # M4: an event_id carries at most ONE observation, ever. Any
            # existing observation for this event_id (regardless of whether
            # decision_cutoff matches — an 8-K/A mints a NEW cutoff) routes
            # through the correction path, never a second append_observation.
            existing = find_observation_by_event_id(event_id)
            if existing is not None:
                if not packet_materially_differs(existing, packet, trigger_ticker):
                    summary["n_observations_noop"] += 1
                    continue
                already_corrected = any(
                    r.get("row_kind") == "correction"
                    and r.get("supersedes_observation_id") == existing.get("observation_id")
                    and (r.get("trigger") or {}).get("event_workspace_generation_id")
                        == packet.get("trigger", {}).get("event_workspace_generation_id")
                    for r in load_rows()
                )
                if already_corrected:
                    summary["n_observations_noop"] += 1
                    continue
                try:
                    old_gen = (existing.get("trigger") or {}).get("event_workspace_generation_id")
                    new_gen = packet.get("trigger", {}).get("event_workspace_generation_id")
                    append_correction(
                        superseded_observation_id=existing["observation_id"],
                        corrected_packet=packet,
                        reason=f"source revision detected: generation {old_gen} -> {new_gen}, derived state changed",
                        production=True,
                    )
                    summary["n_corrections"] += 1
                    log.info("%s %s: correction appended (material source revision)", trigger_ticker, event_id)
                except Exception as exc:  # noqa: BLE001
                    summary["errors"].append(f"{event_id}: correction_append: {exc}")
                continue

            try:
                _row, appended = append_observation(packet, production=True)
                if appended:
                    summary["n_observations_appended"] += 1
                    log.info("%s %s: observation appended (label=%s pooled_state=%s)",
                             trigger_ticker, event_id, packet["m_t"]["label"], packet["m_t"]["pooled_state"])
                else:
                    summary["n_observations_noop"] += 1
            except Exception as exc:  # noqa: BLE001
                log.error("%s %s: observation append failed (%s)", trigger_ticker, event_id, exc)
                summary["errors"].append(f"{event_id}: observation_append: {exc}")

    elapsed = time.time() - t0
    log.info(
        "imce_prospective: done in %.1fs — candidates=%d appended=%d noop=%d corrections=%d errors=%d",
        elapsed, summary["n_candidates"], summary["n_observations_appended"],
        summary["n_observations_noop"], summary["n_corrections"], len(summary["errors"]),
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
