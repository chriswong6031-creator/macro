"""Compact accession-aware disclosure context for Neural Web and Brain.

The private workbench keeps bounded source excerpts and redlines. Intelligence
consumers need a much smaller contract: which deterministic review prompts
triggered, which filing pair was compared, and whether an exact source trace is
available. This adapter intentionally strips excerpts, raw values, and source
URLs so a context read cannot become an entitlement bypass.
"""
from __future__ import annotations

from typing import Any, Mapping


def _bounded(value: Any, limit: int = 180) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _accession(reference: Any) -> str | None:
    return _bounded(reference.get("accession")) if isinstance(reference, Mapping) else None


def _report_date(reference: Any) -> str | None:
    return _bounded(reference.get("report_date")) if isinstance(reference, Mapping) else None


def compact_disclosure_context(
    company: Mapping[str, Any],
    *,
    max_findings: int = 4,
) -> dict[str, Any] | None:
    """Return a bounded, evidence-free disclosure summary or ``None``.

    Only triggered detector outcomes enter ``findings``. Clear and
    not-evaluable states remain represented through per-track coverage so
    absence of a prompt is never presented as a clean-company conclusion.
    """
    disclosure = company.get("disclosures")
    if not isinstance(disclosure, Mapping):
        return None
    tracks = disclosure.get("tracks")
    if not isinstance(tracks, list):
        return None

    compact_tracks: list[dict[str, Any]] = []
    triggered: list[dict[str, Any]] = []
    trace_available = False
    for raw_track in tracks[:2]:
        if not isinstance(raw_track, Mapping):
            continue
        status = str(raw_track.get("status") or "not_evaluable")
        prior = raw_track.get("prior_filing")
        current = raw_track.get("current_filing")
        comparison = raw_track.get("comparison")
        comparison = comparison if isinstance(comparison, Mapping) else {}
        coverage = comparison.get("coverage")
        coverage = coverage if isinstance(coverage, Mapping) else {}
        track_findings = comparison.get("findings")
        track_findings = track_findings if isinstance(track_findings, list) else []
        track_triggered = 0
        for raw_finding in track_findings:
            if not isinstance(raw_finding, Mapping) or raw_finding.get("state") != "triggered":
                continue
            track_triggered += 1
            receipts = raw_finding.get("evidence_receipts")
            if isinstance(receipts, list) and any(isinstance(item, Mapping) for item in receipts):
                trace_available = True
            labels = raw_finding.get("labels")
            labels = labels if isinstance(labels, Mapping) else {}
            why = raw_finding.get("why_flagged")
            why = why if isinstance(why, Mapping) else {}
            triggered.append(
                {
                    "detector": _bounded(raw_finding.get("detector_id")),
                    "priority": _bounded(raw_finding.get("priority")),
                    "review_level": _bounded(raw_finding.get("review_level")),
                    "title": _bounded(labels.get("en") or raw_finding.get("label_key")),
                    "form": _bounded(raw_track.get("form")),
                    "prior_accession": _bounded(raw_finding.get("prior_accession")),
                    "current_accession": _bounded(raw_finding.get("current_accession")),
                    "why_flagged": {
                        str(key)[:80]: _bounded(value, 160)
                        for key, value in list(why.items())[:6]
                    },
                    "display_only": True,
                }
            )
        compact_tracks.append(
            {
                "form": _bounded(raw_track.get("form")),
                "status": _bounded(status),
                "reason": _bounded(raw_track.get("reason")),
                "prior_accession": _accession(prior),
                "current_accession": _accession(current),
                "prior_report_date": _report_date(prior),
                "current_report_date": _report_date(current),
                "redlines_total": coverage.get("redlines_total"),
                "redlines_non_suppressed": coverage.get("redlines_non_suppressed"),
                "triggered_findings": track_triggered,
            }
        )

    return {
        "projection_id": _bounded(disclosure.get("projection_id"), 256),
        "as_of": _bounded((disclosure.get("clocks") or {}).get("as_of"))
        if isinstance(disclosure.get("clocks"), Mapping)
        else None,
        "coverage": dict(disclosure.get("coverage") or {})
        if isinstance(disclosure.get("coverage"), Mapping)
        else {},
        "tracks": compact_tracks,
        "findings": triggered[: max(0, int(max_findings))],
        "source_trace_available": trace_available,
        "basis": "accession_aware_sec_primary_document_comparison",
        "interpretation": "deterministic_text_change_review_prompt_not_management_intent",
        "authority": "context_only",
        "display_only": True,
    }


__all__ = ["compact_disclosure_context"]
