"""IMCE A5B nightly builder — data/cycle_pattern/imce_prospective_observation_v1.jsonl.

Reads the published, R2-hosted ``event_workspace.v1`` objects for the four
homebuilder issuers (DHI/PHM/KBH/TOL) via the SAME canonical public-origin
reader ``scripts.refresh_event_workspaces.load_prior_workspace`` already
uses (no new store, no second reader implementation), and — after
stamping/confirming activation — appends one immutable decision-time IMCE
observation packet per qualifying post-activation earnings event through
``engine.cycle_pattern.imce_prospective``.

Fail-open, house pattern (cf. scripts/build_cycle_pattern_state.py): every
input is guarded; a missing/unreadable input degrades to a no-op run with a
logged note, never a crash. This builder NEVER writes in reconstruction
mode — it is the sole production writer of the ledger.

DAILY-ONLY: the single-writer forward-ledger discipline (CLAUDE.md "Ledgers:
nightly is the sole advancer of forward ledgers") means this builder runs in
daily.yml's cl_misc band only, never in a render/engine-render re-render
lane and never in the three-hour company-intelligence workflow that
publishes the source event_workspaces this module reads.

Run:  python -m scripts.build_cycle_pattern_imce_prospective
"""
from __future__ import annotations

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


def _fetch_all_candidates(today: date) -> dict[str, list[dict]]:
    """ticker -> list of published workspaces found (any order)."""
    from engine.company_intelligence.issuer_profiles import HOMEBUILDER_TICKERS, issuer_for_ticker
    from scripts.refresh_event_workspaces import load_prior_workspace

    found: dict[str, list[dict]] = {t: [] for t in HOMEBUILDER_TICKERS}
    for ticker in HOMEBUILDER_TICKERS:
        issuer = issuer_for_ticker(ticker)
        if issuer is None:
            log.warning("%s: no registered issuer identity — skipped", ticker)
            continue
        for event_id in _candidate_event_ids(ticker, issuer.company_id, today):
            try:
                ws = load_prior_workspace(event_id)
            except Exception as exc:  # noqa: BLE001 — network/parse failure degrades to absent
                log.info("%s %s: workspace fetch failed (%s)", ticker, event_id, exc)
                ws = None
            if ws is not None:
                found[ticker].append(ws)
    return found


def _latest_snapshot_at_or_before(workspaces: list[dict], cutoff_iso: str) -> dict | None:
    """The workspace with the LATEST source_available_at that is still
    <= cutoff_iso (PIT-knowability bound). None if no such snapshot exists."""
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


def run() -> dict:
    """Returns a small summary dict (also useful for tests)."""
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from engine.cycle_pattern.imce_prospective import (
        ROSTER,
        append_correction,
        append_observation,
        assert_no_outcome_fields,
        build_observation_packet,
        ensure_activation,
        find_observation,
        load_rows,
    )

    summary = {"activated": False, "activation_started_at": None, "n_candidates": 0,
               "n_observations_appended": 0, "n_observations_noop": 0, "n_corrections": 0, "errors": []}

    try:
        activation = ensure_activation()
        summary["activated"] = True
        summary["activation_started_at"] = activation["activation_started_at"]
    except Exception as exc:  # noqa: BLE001 — never take the nightly down
        log.error("ensure_activation failed: %s", exc)
        summary["errors"].append(f"ensure_activation: {exc}")
        return summary

    activation_started_at = activation["activation_started_at"]
    today = date.today()

    try:
        found = _fetch_all_candidates(today)
    except Exception as exc:  # noqa: BLE001
        log.error("candidate discovery failed: %s", exc)
        summary["errors"].append(f"candidate_discovery: {exc}")
        return summary

    n_candidates = sum(len(v) for v in found.values())
    summary["n_candidates"] = n_candidates
    log.info("imce_prospective: discovered %d published workspace(s) across %s", n_candidates, list(found))

    for trigger_ticker in ROSTER:
        for trigger_ws in found.get(trigger_ticker, []):
            lifecycle = trigger_ws.get("lifecycle") or {}
            decision_cutoff = lifecycle.get("source_available_at")
            event_id = trigger_ws.get("event_id")
            if not decision_cutoff or not event_id:
                continue

            # Activation law on the TRIGGER itself.
            try:
                from engine.cycle_pattern.imce_prospective import parse_iso
                if parse_iso(decision_cutoff) < parse_iso(activation_started_at):
                    log.info("%s %s: pre-activation trigger event skipped (%s < %s)",
                             trigger_ticker, event_id, decision_cutoff, activation_started_at)
                    continue
            except Exception as exc:  # noqa: BLE001
                summary["errors"].append(f"{event_id}: cutoff parse failed ({exc})")
                continue

            existing = find_observation(event_id, decision_cutoff)

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

            if existing is not None:
                # Source-correction detection: same (event_id, decision_cutoff)
                # key already observed — a differing source sha256 means the
                # published workspace has been revised (new generation) since
                # our last observation. The original packet is NEVER rewritten;
                # a linked correction row is appended instead, once.
                old_sha = (existing.get("trigger") or {}).get("source_document_sha256")
                new_sha = (packet.get("trigger") or {}).get("source_document_sha256")
                if old_sha and new_sha and old_sha != new_sha:
                    already_corrected = any(
                        r.get("row_kind") == "correction"
                        and r.get("supersedes_observation_id") == existing.get("observation_id")
                        and (r.get("trigger") or {}).get("source_document_sha256") == new_sha
                        for r in load_rows()
                    )
                    if not already_corrected:
                        try:
                            append_correction(
                                superseded_observation_id=existing["observation_id"],
                                corrected_packet=packet,
                                reason=f"source revision detected: sha256 {old_sha} -> {new_sha}",
                            )
                            summary["n_corrections"] += 1
                            log.info("%s %s: correction appended (source revision)", trigger_ticker, event_id)
                        except Exception as exc:  # noqa: BLE001
                            summary["errors"].append(f"{event_id}: correction_append: {exc}")
                else:
                    summary["n_observations_noop"] += 1
                continue

            try:
                _row, appended = append_observation(packet)
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


def main() -> None:
    run()


if __name__ == "__main__":
    main()
