"""engine/falsifier_packet.py — A1 Falsifier Packet (LHB-W3).

Program: Long-Hold Thesis lobe.
Adjudication:
  research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md  (LHB-R2, R3)
  research/FALSIFIER_FIELD_BOOK_ADJUDICATION_BY_FABLE.md       (FFB-R2, R3, R5, R7, R9)

DISPLAY-ONLY. _display_only=True, horizon_role="hold_thesis".
This module MUST NOT feed board ordering, alert triage, top-setups gates,
or push floor (LHB-R2 / LH-R1 firewall). Raw enums are legal on the admin
Long-Hold page (Tier-3) and ONLY there.

ZERO hypothesis slots, ZERO fused scores, ZERO composite outputs.

=============================================================================
STATUS VOCABULARY (LHB-R3 — deterministic-escalation law)
=============================================================================

Exactly five values, no others:

  not_observed         — the observable exists and no deterioration has been
                         seen in the available evidence.
  no_break_observed    — one prior confirmed period with no break (slightly
                         stronger than not_observed: positive absence).
  challenged           — two consecutive filed periods show the same named
                         deterioration, OR a single filed event opens review.
                         State is sticky but reversible. NEVER auto-escalated
                         to broken by any sensor other than Item 1.03 or a
                         registered terminal event.
  broken               — AUTO-BROKEN ONLY from filed terminal events:
                           * 8-K Item 1.03 — bankruptcy/receivership; OR
                           * a filed primary-endpoint failure named in a
                             registered contract; OR
                           * a filed agreement termination explicitly named
                             in a registered contract.
                         No other trigger may produce broken. (LHB-R3)
  unverifiable         — evidence is stale (>400d since last computable
                         filing), missing entirely, or scope-contaminated.
                         Stale evidence → unverifiable, NEVER no_break_observed.

=============================================================================
STATUS MAPPING TABLE (deterministic, module-level)
=============================================================================

Source state                         → packet axis status
-------------------------------------------------------------------
Moat-falsifier sensor fired=True     → challenged
Moat-falsifier sensor fired=False    → no_break_observed
Moat-falsifier sensor coverage=missing → unverifiable

Thesis-funnel state:
  thesis_candidate_shadow            → not_observed  (no survival flags fire)
  watch_for_thesis                   → not_observed  (survival ok; piotroski gap)
  not_eligible (s2_moat_falsifier)   → challenged    (moat fire is the reason)
  not_eligible (s1_dilution)         → challenged    (dilution = capital break)
  not_eligible (s3_solvency)         → challenged    (solvency trigger)
  not_eligible (s4_coverage)         → unverifiable  (insufficient data)
  not_eligible (other)               → challenged    (conservative default)
  absent/unknown                     → unverifiable

Capital allocation delta:
  accretive                          → no_break_observed
  neutral                            → not_observed
  dilutive                           → challenged
  unavailable or None                → unverifiable

8-K item routing (A6 hard-stop bus) — archetype-blind in v1 (no per-ticker
registered archetypes yet — every event opens review; per LHB-W3 spec):
  Item 1.03 (bankruptcy/receivership)         → broken  (the ONLY auto-broken)
  Item 1.02 (material-agreement termination)  → challenged  (Named-contract review)
  Item 2.04 (acceleration/default)            → challenged  (Solvency review)
  Item 3.01 (listing failure)                 → challenged  (Financing review)
  Item 3.02 (actual issuance)                 → challenged  (Financing review)
  Item 4.02 (non-reliance/material weakness)  → challenged  (Evidence challenged)
  Item 5.02 (key departure)                   → challenged  (Succession review)

Evidence staleness:
  >400d since last computable filing           → unverifiable (never no_break_observed)

=============================================================================
ARCHETYPE CARDS (§D — from FALSIFIER_FIELD_BOOK_FOR_FABLE.md)
=============================================================================

Six hold archetypes × {patience, trim_review, exit_review, cadence}.
FFB-R3 amendments: TEVA excluded from recovery-speed prior (1,929-day outlier);
CVNA and OKTA are refusal-driven non-adjudications (FFB-R3 partition).
FFB-R9 card copy: margin compression magnitude does not separate outcomes;
inventory/RPO build requires a second independent demand-or-cash fact;
Item 5.02 and Form 4 never fire alone; acquisition/scope → unverifiable.

=============================================================================
A1 FIVE QUESTIONS (from brainstorm §A1)
=============================================================================

The packet header answers the five A1 questions as defined in
research/LONG_HOLD_LOBE_BRAINSTORM_FOR_FABLE.md §A1:

  1. Has the tactical entry clock expired?
  2. What was the latest fundamental confirmation date?
  3. Which predeclared falsifiers fired, and on what filing?
  4. Which required observables are overdue or unavailable?
  5. What is the next scheduled or event-driven evidence window?

=============================================================================
FFB-R2 COVERAGE COPY (verbatim — must appear in every packet header)
=============================================================================

"Advance review in 7 of 12 studied true breaks; 5 of 12 were visible only
coincident with the break. A6 is a hard-stop bus, not a lead generator."

=============================================================================
EXPECTATION-BURDEN AXIS
=============================================================================

Descriptive only. No implied growth, no CAGR, no targets. (LHB-R4 W3 lock)

EV/sales vs own 5-year filed range:
  ordinary   — below 80th percentile of own annual history
  stretched  — 80th to 95th percentile of own annual history
  extreme    — above 95th percentile of own annual history
  unverifiable — fewer than 3 datapoints or missing data

If a delivery_waterfall row exists for the ticker, the residual leg
(valuation/mix/accounting residual) is included as-is (display annotation
only — the label is inherited from the waterfall).

=============================================================================
USAGE
=============================================================================

  from engine.falsifier_packet import assemble_packet, ARCHETYPE_CARDS

  packet = assemble_packet(ticker, sources)
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
_HORIZON_ROLE: str = "hold_thesis"
_DISPLAY_ONLY: bool = True
_VERSION: str = "v1"
_SCHEMA: str = "falsifier_packet.v1"

# Stale-evidence threshold (LHB-R3: stale → unverifiable, never no_break_observed)
_STALE_EVIDENCE_DAYS: int = 400

# Valid status vocabulary (LHB-R3)
VALID_STATUSES: frozenset[str] = frozenset({
    "not_observed",
    "no_break_observed",
    "challenged",
    "broken",
    "unverifiable",
})

# FFB-R2 verbatim coverage copy — must appear in every packet header
_FFB_R2_COVERAGE_COPY: str = (
    "Advance review in 7 of 12 studied true breaks; 5 of 12 were visible only "
    "coincident with the break. A6 is a hard-stop bus, not a lead generator."
)

# A6 item routing table — archetype-blind in v1
# LHB-R3: only 1.03 → broken; all others → challenged with named review label
_A6_ITEM_ROUTING: dict[str, dict[str, str]] = {
    # Item → {status, review_label}
    "1.03": {"status": "broken",      "review_label": "Verified terminal-risk event"},
    "1.02": {"status": "challenged",  "review_label": "Named-contract review"},
    "2.04": {"status": "challenged",  "review_label": "Solvency review"},
    "3.01": {"status": "challenged",  "review_label": "Financing review"},
    "3.02": {"status": "challenged",  "review_label": "Financing review"},
    "4.02": {"status": "challenged",  "review_label": "Evidence challenged"},
    "5.02": {"status": "challenged",  "review_label": "Succession review"},
}

# Expectation-burden percentile thresholds
_BURDEN_STRETCHED_PCT: float = 80.0   # >= 80th → stretched
_BURDEN_EXTREME_PCT: float = 95.0     # >= 95th → extreme


# ---------------------------------------------------------------------------
# Archetype cards (§D — FFB field-guide copy)
# Columns: patience | trim_review | exit_review | cadence
# FFB-R3 amendments cited in comments.
# FFB-R9 card copy integrated.
# ---------------------------------------------------------------------------

ARCHETYPE_CARDS: list[dict[str, Any]] = [
    {
        # FFB-R9: margin compression magnitude does not separate outcomes; peer/context mandatory.
        "archetype": "quality_compounder",
        "label": "Quality compounder",
        "patience": (
            "Require two adjacent YoY gross-margin declines on comparable scope. "
            "Counter-sensors: margin-dollar expansion and positive comps both visible "
            "at trigger filings argue for patience. "
            "Peer-relative framing: challenge only when company-specific vs sector-common "
            "deterioration is distinguishable."
        ),
        "trim_review": (
            "Two consecutive YoY gross-margin declines with comparable scope AND "
            "no dollar-expansion counter-sensor at either trigger filing. "
            "Inventory-growth minus revenue-growth > 15 pp twice with cash conversion "
            "deterioration as independent corroboration."
        ),
        "exit_review": (
            "No auto-broken trigger available for this archetype (no legal terminal event). "
            "Only a filed Item 1.03 would move to broken. "
            "Challenged state remains reviewable until reversed by two recovery prints."
        ),
        # FFB-R3: TEVA (1,929d) excluded from recovery-speed prior.
        "cadence": (
            "Quarterly for gross-margin pilot (A2). Annual for moat sensors. "
            "Recovery clock: two-print symmetric confirmation. "
            "Field-book median true-break lead: 93.5d. False-alarm recovery: 552.5d median "
            "(excludes TEVA multi-year outlier per FFB-R3)."
        ),
        "field_book_cases": {
            "true_breaks": ["Under Armour 90d lead", "V.F. Corp 97d lead"],
            "false_alarms": ["Texas Roadhouse recovery 567d", "Ulta Beauty recovery 637d"],
        },
    },
    {
        # FFB-R9: Item 5.02 alone never fires; succession requires two FCF/share declines.
        "archetype": "owner_operator",
        "label": "Owner-operator / allocator",
        "patience": (
            "Item 5.02 alone does not fire (FFB-R9). "
            "Require two periods of declining FCF/share or actual share-count expansion "
            "after buybacks, plus a separate operating or leverage deterioration. "
            "Announced buyback dollars without actual share-count reduction do not qualify."
        ),
        "trim_review": (
            "Two annual post-acquisition-clean periods with negative FCF/share AND "
            "diluted share count expanding. "
            "Capital allocation delta = dilutive with independent operating deterioration."
        ),
        "exit_review": (
            "Item 1.03 bankruptcy → broken. "
            "Named filed agreement termination in a registered contract → broken. "
            "All others remain challenged."
        ),
        "cadence": (
            "Annual for FCF/share and share-count. "
            "Acquisition-scope refusal: first clean post-acquisition annual observation only. "
            "Field-book median true-break lead: 175.5d (2U 141d, Stitch Fix 210d)."
        ),
        "field_book_cases": {
            "true_breaks": ["2U 141d lead (Item 1.03 terminal)", "Stitch Fix 210d lead (anchor-sensitive)"],
            "false_alarms": ["Amazon FCF recovery 265d", "FedEx margin recovery 274d"],
        },
    },
    {
        # FFB-R9: dilution that extends runway is not a break signal.
        "archetype": "turnaround_distressed",
        "label": "Turnaround / distressed rerating",
        "patience": (
            "Two periods of worsening self-funding PLUS either less than four quarters "
            "of disclosed liquidity runway OR a repeated inventory/demand spread. "
            "Dilution that extends runway is NOT a negative signal (FFB-R9). "
            "Margin decline alone, high leverage alone: not sufficient."
        ),
        "trim_review": (
            "Item 2.04 (acceleration/default) opens solvency review → challenged. "
            "Two periods of inventory build plus cash burn and liquidity deterioration."
        ),
        "exit_review": (
            "Item 1.03 → broken (the only auto-terminal for this archetype). "
            "Item 2.04 opens solvency review but caps at challenged per LHB-R3."
        ),
        # FFB-R3: CVNA is refusal-driven non-adjudication (ADESA scope); TEVA 1,929d excluded.
        "cadence": (
            "Quarterly for inventory and cash. Event-driven for Item 2.04/1.03. "
            "Field-book median true-break lead: 81d (Hertz 0d coincident, Party City 162d). "
            "Note: Carvana was acquisition-refused (FFB-R3); TEVA excluded from recovery-speed prior (1,929d)."
        ),
        "field_book_cases": {
            "true_breaks": ["Party City 162d lead (Item 1.03 terminal)", "Hertz 0d coincident"],
            "false_alarms": ["Carvana (acquisition-refused per FFB-R3)", "Teva (1,929d — excluded from prior)"],
        },
    },
    {
        # FFB-R9: acquisition-contaminated RPO/margin → unverifiable.
        "archetype": "contracted_platform",
        "label": "Contracted / platform growth",
        "patience": (
            "Two sequential comparable RPO/backlog declines with cumulative decline "
            "of roughly 10% or more from the reference filing. "
            "Acquisition-contaminated corroboration → unverifiable, never challenged. "
            "Separate margin or CFO corroboration required when admissible (FFB-R9)."
        ),
        "trim_review": (
            "Item 1.02 (named-contract termination) opens Named-contract review → challenged. "
            "Two comparable RPO declines plus deteriorating conversion or collection quality."
        ),
        "exit_review": (
            "Item 1.03 → broken. "
            "Named filed agreement termination registered in the contract → broken. "
            "Item 1.02 → challenged (Named-contract review per A6 routing)."
        ),
        # FFB-R3: OKTA is refusal-driven non-adjudication (Auth0 scope).
        "cadence": (
            "Quarterly where RPO/backlog is filed. Immediate for Item 1.02. "
            "Field-book median true-break lead: 103.5d (Fastly 207d, Twilio 0d coincident). "
            "Note: Okta was acquisition-refused (FFB-R3)."
        ),
        "field_book_cases": {
            "true_breaks": ["Fastly 207d lead (anchor-sensitive)", "Twilio 0d coincident"],
            "false_alarms": ["Autodesk recovery 730d", "Okta (acquisition-refused per FFB-R3)"],
        },
    },
    {
        "archetype": "clinical_milestone",
        "label": "Clinical / milestone / pre-revenue",
        "patience": (
            "Date slip alone caps at review — never challenged from delay alone. "
            "Financing stress only when disclosed liquid resources reach the revised milestone "
            "with less than two quarterly filing cadences of runway remaining. "
            "Cash runway can distinguish financing risk from scientific risk; "
            "it cannot forecast efficacy."
        ),
        "trim_review": (
            "Filed primary-endpoint failure for a pre-registered endpoint → broken. "
            "A CRL is NOT automatically terminal (FFB-R9). "
            "Runway challenge: two quarterly cadences of liquid resources short of milestone."
        ),
        "exit_review": (
            "Filed predeclared primary-endpoint failure → broken (if ticker contract named it). "
            "Item 1.03 → broken. "
            "CRL → challenged only (review, not broken)."
        ),
        "cadence": (
            "Event-driven (endpoint results, FDA decisions). Quarterly for runway. "
            "Field-book median true-break lead: 0d (all three true breaks were coincident). "
            "False-alarm recovery: Axsome 284d, Immunomedics 422d."
        ),
        "field_book_cases": {
            "true_breaks": ["FibroGen 0d coincident", "Allakos 0d coincident"],
            "false_alarms": ["Axsome recovery 284d (approval)", "Immunomedics recovery 422d (approval)"],
        },
    },
    {
        # FFB-R9: absolute capex/revenue levels do not separate outcomes.
        "archetype": "cyclical_commodity",
        "label": "Cyclical / commodity-sensitive",
        "patience": (
            "Within-name +3 pp capex/revenue versus two years earlier as supply-build prior. "
            "Do not challenge until two comparable segment margin/return rollovers appear. "
            "Peer-common downcycles must remain visible rather than called company-specific. "
            "Absolute capex/revenue levels do not separate outcomes (FFB-R9)."
        ),
        "trim_review": (
            "Two comparable segment unit-margin deteriorations plus rising capital intensity. "
            "Revenue contraction with rising capex ratio AND a second solvency observation. "
            "Item 2.04 opens solvency review → challenged."
        ),
        "exit_review": (
            "Item 1.03 → broken. "
            "No absolute threshold auto-triggers broken for this archetype (FFB-R9 bar)."
        ),
        "cadence": (
            "Annual for capex/revenue and segment margins. Event-driven for Item 2.04/1.03. "
            "Field-book median true-break lead: 82d (Arch Coal 164d, U.S. Silica 0d coincident). "
            "False-alarm recovery: Micron 461d, Freeport 807d."
        ),
        "field_book_cases": {
            "true_breaks": ["Arch Coal 164d lead (Item 1.03 terminal)", "U.S. Silica 0d coincident"],
            "false_alarms": ["Micron recovery 461d", "Freeport recovery 807d"],
        },
    },
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today() -> date:
    return datetime.now(timezone.utc).date()


def _evidence_age_days(last_observation_date: str | None) -> int | None:
    """Return calendar days since last_observation_date (ISO YYYY-MM-DD), or None."""
    if not last_observation_date:
        return None
    try:
        d = date.fromisoformat(str(last_observation_date)[:10])
        return (date.today() - d).days
    except Exception:  # noqa: BLE001
        return None


def _is_stale(age_days: int | None) -> bool:
    """True if evidence is older than _STALE_EVIDENCE_DAYS or age is unknown."""
    if age_days is None:
        return True
    return age_days > _STALE_EVIDENCE_DAYS


def _coerce_status(raw: str | None) -> str:
    """Ensure a status value is in VALID_STATUSES; default to unverifiable."""
    if raw in VALID_STATUSES:
        return raw
    return "unverifiable"


# ---------------------------------------------------------------------------
# Sensor helpers: each returns one business_evidence axis sensor dict
# ---------------------------------------------------------------------------

def _sensor(
    name: str,
    status: str,
    last_observation_date: str | None,
    evidence_age_days: int | None,
    cadence_note: str,
    source_key: str,
) -> dict[str, Any]:
    """Build a single business_evidence sensor dict."""
    return {
        "name": name,
        "status": _coerce_status(status),
        "last_observation_date": last_observation_date,
        "evidence_age_days": evidence_age_days,
        "cadence_note": cadence_note,
        "source_key": source_key,
    }


# ---------------------------------------------------------------------------
# Moat-falsifier sensors → business_evidence axis
# ---------------------------------------------------------------------------

_MOAT_SENSOR_LABELS: dict[str, str] = {
    "margin_compression_despite_revenue_growth": "Gross-margin compression (moat)",
    "receivables_stretch": "Receivables stretch (moat)",
    "inventory_build": "Inventory build (moat)",
    "capital_intensity_rising": "Capital intensity rising (moat)",
}


def _moat_sensors_to_axis(
    moat_result: dict | None,
    asof_date: str | None,
) -> list[dict[str, Any]]:
    """Map moat_falsifiers result to business_evidence sensor entries.

    Mapping (per module docstring mapping table):
      fired=True  → challenged
      fired=False → no_break_observed
      coverage=missing → unverifiable
    Stale (>400d since asof_date) → unverifiable regardless of fired status.
    """
    sensors: list[dict[str, Any]] = []
    if not moat_result or not isinstance(moat_result, dict):
        for name, label in _MOAT_SENSOR_LABELS.items():
            sensors.append(_sensor(
                name=label,
                status="unverifiable",
                last_observation_date=None,
                evidence_age_days=None,
                cadence_note="Annual (statements.parquet)",
                source_key=f"moat_falsifiers.{name}",
            ))
        return sensors

    coverage = moat_result.get("sensor_coverage", "missing")
    fired_map: dict[str, bool] = moat_result.get("sensor_fired_map", {}) or {}
    # Individual sensor fired flags may also be top-level keys
    for name, label in _MOAT_SENSOR_LABELS.items():
        fired_raw = fired_map.get(name)
        if fired_raw is None:
            fired_raw = moat_result.get(name)  # direct key fallback

        age = _evidence_age_days(asof_date)
        stale = _is_stale(age)

        if coverage == "missing" or stale:
            status = "unverifiable"
        elif fired_raw is True:
            status = "challenged"
        elif fired_raw is False:
            status = "no_break_observed"
        else:
            # fired status unknown → unverifiable
            status = "unverifiable"

        sensors.append(_sensor(
            name=label,
            status=status,
            last_observation_date=asof_date,
            evidence_age_days=age,
            cadence_note="Annual (statements.parquet). Two-filing confirmation required for challenged→broken.",
            source_key=f"moat_falsifiers.{name}",
        ))
    return sensors


# ---------------------------------------------------------------------------
# Thesis funnel → business_evidence axis (one aggregate sensor)
# ---------------------------------------------------------------------------

def _funnel_to_sensor(funnel_state: dict | None) -> dict[str, Any]:
    """Map thesis_funnel state to a business_evidence sensor entry.

    Mapping (per mapping table):
      thesis_candidate_shadow → not_observed
      watch_for_thesis        → not_observed
      not_eligible (s4_coverage) → unverifiable
      not_eligible (s2_moat_falsifier, s1_dilution, s3_solvency, other) → challenged
      absent/None             → unverifiable
    """
    if not funnel_state or not isinstance(funnel_state, dict):
        return _sensor(
            name="Thesis funnel (survival gates)",
            status="unverifiable",
            last_observation_date=None,
            evidence_age_days=None,
            cadence_note="Daily (nightly build)",
            source_key="thesis_funnel.state",
        )

    state = funnel_state.get("state")
    asof = funnel_state.get("as_of")
    age = _evidence_age_days(asof)

    if _is_stale(age):
        status = "unverifiable"
    elif state in ("thesis_candidate_shadow", "watch_for_thesis"):
        status = "not_observed"
    elif state == "not_eligible":
        reason = funnel_state.get("state_reason", "")
        if reason == "s4_coverage":
            status = "unverifiable"
        else:
            # s1_dilution, s2_moat_falsifier, s3_solvency, or other
            status = "challenged"
    else:
        status = "unverifiable"

    return _sensor(
        name="Thesis funnel (survival gates)",
        status=status,
        last_observation_date=asof,
        evidence_age_days=age,
        cadence_note="Daily (nightly build). s1=dilution, s2=moat, s3=solvency, s4=coverage.",
        source_key="thesis_funnel.state",
    )


# ---------------------------------------------------------------------------
# Capital allocation → business_evidence axis
# ---------------------------------------------------------------------------

def _cap_alloc_to_sensor(cap_alloc: dict | None) -> dict[str, Any]:
    """Map capital_allocation_delta to a business_evidence sensor entry.

    Mapping (per mapping table):
      accretive    → no_break_observed
      neutral      → not_observed
      dilutive     → challenged
      unavailable  → unverifiable
      None / other → unverifiable
    """
    if not cap_alloc or not isinstance(cap_alloc, dict):
        return _sensor(
            name="Capital allocation delta",
            status="unverifiable",
            last_observation_date=None,
            evidence_age_days=None,
            cadence_note="Annual / quarterly (capital_allocation.py)",
            source_key="capital_allocation.delta",
        )

    delta = cap_alloc.get("capital_allocation_delta")
    asof = cap_alloc.get("as_of") or cap_alloc.get("asof")
    age = _evidence_age_days(asof)

    if _is_stale(age):
        status = "unverifiable"
    elif delta == "accretive":
        status = "no_break_observed"
    elif delta == "neutral":
        status = "not_observed"
    elif delta == "dilutive":
        status = "challenged"
    else:
        # unavailable, None, or unknown
        status = "unverifiable"

    return _sensor(
        name="Capital allocation delta",
        status=status,
        last_observation_date=asof,
        evidence_age_days=age,
        cadence_note="Annual share-count trend + quarterly buyback execution.",
        source_key="capital_allocation.delta",
    )


# ---------------------------------------------------------------------------
# Long-hold clocks → business_evidence axis
# ---------------------------------------------------------------------------

def _clocks_to_sensors(clocks_entry: dict | None) -> list[dict[str, Any]]:
    """Map long_hold_clocks entry to business_evidence sensor entries.

    Returns entry_clock and thesis_clock sensors.
    """
    sensors: list[dict[str, Any]] = []

    if not clocks_entry or not isinstance(clocks_entry, dict):
        sensors.append(_sensor(
            name="Entry clock (days since last buy/rebuy marker)",
            status="unverifiable",
            last_observation_date=None,
            evidence_age_days=None,
            cadence_note="Daily (signal_gate)",
            source_key="long_hold_clocks.entry_clock",
        ))
        sensors.append(_sensor(
            name="Thesis clock (days since latest positive fundamental delta)",
            status="unverifiable",
            last_observation_date=None,
            evidence_age_days=None,
            cadence_note="Annual (fundamentals_panel, period_end)",
            source_key="long_hold_clocks.thesis_clock",
        ))
        return sensors

    # entry_clock
    entry = clocks_entry.get("entry_clock") or {}
    entry_date = entry.get("date_last_fire") if isinstance(entry, dict) else None
    entry_age = _evidence_age_days(entry_date)
    if entry_date is None:
        entry_status = "unverifiable"
    elif _is_stale(entry_age):
        entry_status = "unverifiable"
    else:
        entry_status = "not_observed"  # clock present = no break, just an annotation

    sensors.append(_sensor(
        name="Entry clock (days since last buy/rebuy marker)",
        status=entry_status,
        last_observation_date=entry_date,
        evidence_age_days=entry_age,
        cadence_note="Daily (signal_gate). Annotates tactical entry recency only.",
        source_key="long_hold_clocks.entry_clock",
    ))

    # thesis_clock — positive fundamental confirmation date
    thesis = clocks_entry.get("thesis_clock") or {}
    thesis_date = thesis.get("period_end") if isinstance(thesis, dict) else None
    thesis_age = _evidence_age_days(thesis_date)
    if thesis_date is None:
        thesis_status = "unverifiable"
    elif _is_stale(thesis_age):
        thesis_status = "unverifiable"
    else:
        thesis_status = "not_observed"  # positive confirmation present

    sensors.append(_sensor(
        name="Thesis clock (days since latest positive fundamental delta)",
        status=thesis_status,
        last_observation_date=thesis_date,
        evidence_age_days=thesis_age,
        cadence_note="Annual (fundamentals_panel period_end). Absence = no positive confirmation in history.",
        source_key="long_hold_clocks.thesis_clock",
    ))
    return sensors


# ---------------------------------------------------------------------------
# A6 hard-stop bus: 8-K item routing
# ---------------------------------------------------------------------------

def _route_8k_items(
    events_rows: list[dict] | None,
) -> list[dict[str, Any]]:
    """Route material_8k_events rows per A6 routing table.

    In v1, routing is archetype-blind (no per-ticker registered archetypes yet);
    every routable event opens a review. Item 1.03 → broken; all others → challenged.
    The 'items' field may be a comma-separated list of item codes in a single row.

    Returns a list of A6 sub-block entries, one per routable event filing.
    Each entry:
      item_code, status, review_label, accession, filing_date, evidence_age_days
    """
    if not events_rows:
        return []

    results: list[dict[str, Any]] = []
    for row in events_rows:
        if not isinstance(row, dict):
            continue
        items_raw = row.get("items") or ""
        filing_date = row.get("filing_date") or row.get("date")
        accession = row.get("accession")
        age = _evidence_age_days(filing_date)

        # Items may be a comma-separated list (e.g. "1.01,1.02,2.04")
        item_codes = [x.strip() for x in str(items_raw).split(",") if x.strip()]
        for code in item_codes:
            routing = _A6_ITEM_ROUTING.get(code)
            if routing is None:
                continue  # item not in the A6 routing table
            results.append({
                "item_code": code,
                "status": routing["status"],
                "review_label": routing["review_label"],
                "accession": accession,
                "filing_date": filing_date,
                "evidence_age_days": age,
                "archetype_note": (
                    "v1: archetype-blind routing — every routable event opens review; "
                    "per-ticker registered archetypes are a future enhancement."
                ),
            })
    return results


# ---------------------------------------------------------------------------
# Expectation-burden axis
# ---------------------------------------------------------------------------

def _compute_ev_sales_percentile(
    statements_df: "pd.DataFrame | None",
    price: float | None,
    shares: float | None,
    net_debt: float | None,
) -> dict[str, Any]:
    """Compute EV/sales vs own 5-year filed history.

    Inputs:
      statements_df — ticker's statements.parquet slice (annual rows)
      price         — current price per share
      shares        — most recent shares outstanding
      net_debt      — most recent net debt (debt_lt + debt_cur - cash)

    Returns:
      {ev_sales_current, own_history_n, percentile, burden_label, note}

    burden_label:
      ordinary   — < 80th percentile of own history
      stretched  — 80-95th percentile
      extreme    — > 95th percentile
      unverifiable — <3 datapoints or missing
    """
    if statements_df is None or price is None:
        return {
            "ev_sales_current": None,
            "own_history_n": 0,
            "percentile": None,
            "burden_label": "unverifiable",
            "note": "Missing price or statements data",
        }

    try:
        import numpy as np
        import pandas as pd

        df = statements_df.copy()
        # Need revenue column
        if "revenue" not in df.columns:
            return {
                "ev_sales_current": None,
                "own_history_n": 0,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "No revenue column in statements",
            }

        # Drop rows with null revenue
        df = df[df["revenue"].notna() & (df["revenue"] > 0)].copy()

        # Current EV/sales
        if shares is None or net_debt is None:
            return {
                "ev_sales_current": None,
                "own_history_n": 0,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "Missing shares or net_debt for EV computation",
            }

        mktcap = price * shares
        ev = mktcap + net_debt
        if ev <= 0:
            return {
                "ev_sales_current": None,
                "own_history_n": 0,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "Negative or zero EV",
            }

        # Use latest revenue as denominator for current EV/sales
        if df.empty:
            return {
                "ev_sales_current": None,
                "own_history_n": 0,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "No revenue rows after filtering",
            }

        latest_rev = float(df.sort_values("fy").iloc[-1]["revenue"])
        if latest_rev <= 0:
            return {
                "ev_sales_current": None,
                "own_history_n": 0,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "Non-positive latest revenue",
            }

        ev_sales_current = ev / latest_rev

        # Historical EV/sales: for each annual row, approximate EV using filed financials only
        # We only have period-end data; we cannot reconstruct historical price here.
        # Use current EV/sales vs filed revenue range as proxy (documented limitation).
        # Compare current ratio to the distribution of revenue values normalized to current EV —
        # this is descriptive only, not a peer or forecast comparison.
        # Since we don't have historical prices, report vs own revenue history shape.
        rev_hist = df["revenue"].dropna().astype(float).tolist()
        n = len(rev_hist)
        if n < 3:
            return {
                "ev_sales_current": round(ev_sales_current, 2),
                "own_history_n": n,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": f"Fewer than 3 revenue datapoints (n={n}); cannot compute percentile",
            }

        # Compute EV/sales at each historical revenue using current EV as a constant
        # This is an approximation: EV shifts with price; we only have current price.
        # The note must disclose this is current-EV vs own revenue range.
        ev_sales_history = [ev / r for r in rev_hist if r > 0]
        if len(ev_sales_history) < 3:
            return {
                "ev_sales_current": round(ev_sales_current, 2),
                "own_history_n": n,
                "percentile": None,
                "burden_label": "unverifiable",
                "note": "Fewer than 3 positive revenue rows for percentile",
            }

        pct = float(np.mean(np.array(ev_sales_history) <= ev_sales_current) * 100)

        if pct >= _BURDEN_EXTREME_PCT:
            burden_label = "extreme"
        elif pct >= _BURDEN_STRETCHED_PCT:
            burden_label = "stretched"
        else:
            burden_label = "ordinary"

        return {
            "ev_sales_current": round(ev_sales_current, 2),
            "own_history_n": len(ev_sales_history),
            "percentile": round(pct, 1),
            "burden_label": burden_label,
            "note": (
                "Approximation: current EV vs own filed revenue range (no historical prices). "
                "Descriptive only — no implied growth, no target, no CAGR (LHB-R4 W3 lock). "
                "No peer comparison."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_ev_sales_percentile error for ticker: %s", exc)
        return {
            "ev_sales_current": None,
            "own_history_n": 0,
            "percentile": None,
            "burden_label": "unverifiable",
            "note": f"Computation error: {exc}",
        }


def _build_expectation_burden_axis(
    waterfall_row: dict | None,
    statements_df: "pd.DataFrame | None",
    price: float | None,
    shares: float | None,
    net_debt: float | None,
) -> dict[str, Any]:
    """Build the expectation_burden axis for one ticker.

    Descriptive only. No implied growth, no CAGR, no targets. (LHB-R4 W3 lock)
    """
    ev_sales = _compute_ev_sales_percentile(statements_df, price, shares, net_debt)

    # Delivery waterfall residual leg (if a non-refused row exists)
    waterfall_residual: dict | None = None
    if waterfall_row and isinstance(waterfall_row, dict):
        status = waterfall_row.get("status")
        if status == "ok":
            path = waterfall_row.get("path")
            if path == "pe_identity":
                residual_pct = waterfall_row.get("legs_pct__valuation_mix_accounting_residual")
            elif path == "ev_revenue":
                residual_pct = waterfall_row.get("legs_pct__ev_multiple_residual")
            else:
                residual_pct = None

            if residual_pct is not None:
                waterfall_residual = {
                    "path": path,
                    "residual_pct": round(float(residual_pct), 1),
                    "label": "valuation/mix/accounting residual (from A3 delivery waterfall)",
                    "note": (
                        "Display annotation only. This is the unexplained share of log-price "
                        "return after fundamental delivery legs. It is NOT a valuation target, "
                        "NOT an implied-growth claim, and NOT a sell signal."
                    ),
                }

    return {
        "ev_sales_vs_own_history": ev_sales,
        "delivery_waterfall_residual": waterfall_residual,
        "_display_only": True,
        "_horizon_role": _HORIZON_ROLE,
        "_note": (
            "Descriptive only. No implied growth, no CAGR, no targets, no peer valuation. "
            "LHB-R4 W3 lock: PR-N stays W3-locked behind G1 retest."
        ),
    }


# ---------------------------------------------------------------------------
# Five A1 questions
# ---------------------------------------------------------------------------

def _answer_a1_questions(
    business_sensors: list[dict],
    a6_events: list[dict],
    clocks_entry: dict | None,
    funnel_state: dict | None,
) -> dict[str, Any]:
    """Answer the five A1 questions from brainstorm §A1.

    Returns a dict with keys q1..q5.
    """
    # Q1: Has the tactical entry clock expired?
    entry_sensor = next(
        (s for s in business_sensors if s.get("source_key") == "long_hold_clocks.entry_clock"),
        None,
    )
    entry_date = None
    entry_days = None
    if clocks_entry and isinstance(clocks_entry, dict):
        ec = clocks_entry.get("entry_clock") or {}
        if isinstance(ec, dict):
            entry_date = ec.get("date_last_fire")
            entry_days = ec.get("days_since")
    if entry_date is None:
        q1 = "Entry clock: unverifiable — no buy/rebuy marker found."
    elif entry_days is not None and entry_days > _STALE_EVIDENCE_DAYS:
        q1 = f"Entry clock: expired — last fire {entry_date} ({entry_days}d ago, >{_STALE_EVIDENCE_DAYS}d)."
    else:
        q1 = f"Entry clock: active — last fire {entry_date} ({entry_days or 'unknown'}d ago)."

    # Q2: What was the latest fundamental confirmation date?
    thesis_sensor = next(
        (s for s in business_sensors if s.get("source_key") == "long_hold_clocks.thesis_clock"),
        None,
    )
    thesis_date = thesis_sensor.get("last_observation_date") if thesis_sensor else None
    thesis_age = thesis_sensor.get("evidence_age_days") if thesis_sensor else None
    if thesis_date is None:
        q2 = "Latest fundamental confirmation: unverifiable — no positive delta period found."
    else:
        q2 = (
            f"Latest fundamental confirmation: {thesis_date} "
            f"({thesis_age or 'unknown'}d ago). "
            f"Status: {thesis_sensor.get('status', 'unverifiable') if thesis_sensor else 'unverifiable'}."
        )

    # Q3: Which predeclared falsifiers fired, and on what filing?
    fired = [
        s for s in business_sensors
        if s.get("status") in ("challenged", "broken")
    ]
    a6_fired = [e for e in a6_events if e.get("status") in ("challenged", "broken")]
    if not fired and not a6_fired:
        q3 = "No falsifiers fired. All sensors at not_observed / no_break_observed."
    else:
        parts = []
        for s in fired:
            parts.append(
                f"{s['name']} → {s['status']} "
                f"(observed {s.get('last_observation_date', 'unknown')})"
            )
        for e in a6_fired:
            parts.append(
                f"8-K Item {e['item_code']} ({e['review_label']}) → {e['status']} "
                f"(filed {e.get('filing_date', 'unknown')}, accession {e.get('accession', 'unknown')})"
            )
        q3 = "Fired: " + "; ".join(parts) + "."

    # Q4: Which required observables are overdue or unavailable?
    overdue = [
        s for s in business_sensors
        if s.get("status") == "unverifiable"
    ]
    if not overdue:
        q4 = "All required observables have recent evidence."
    else:
        names = [s["name"] for s in overdue]
        q4 = f"Overdue or unavailable: {', '.join(names)}."

    # Q5: What is the next scheduled or event-driven evidence window?
    funnel_asof = None
    if funnel_state and isinstance(funnel_state, dict):
        funnel_asof = funnel_state.get("as_of")
    # Approximate: next quarterly filing ~90d from last moat sensor date
    moat_sensor = next(
        (s for s in business_sensors if "moat_falsifiers" in s.get("source_key", "")),
        None,
    )
    last_moat_date = moat_sensor.get("last_observation_date") if moat_sensor else None
    if last_moat_date:
        q5 = (
            f"Next evidence window: next quarterly filing after {last_moat_date}. "
            f"A6 events: immediate (any new EDGAR 8-K filing)."
        )
    else:
        q5 = "Next evidence window: next EDGAR filing (date unknown — observables currently unverifiable)."

    return {
        "q1_entry_clock_expired": q1,
        "q2_latest_fundamental_confirmation": q2,
        "q3_falsifiers_fired": q3,
        "q4_overdue_or_unavailable": q4,
        "q5_next_evidence_window": q5,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_packet(
    ticker: str,
    sources: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the A1 falsifier packet for one ticker.

    Parameters
    ----------
    ticker:
        The stock ticker symbol.
    sources:
        Pre-loaded data dict containing any of:
          moat_falsifiers_result   — dict from engine.moat_falsifiers.compute_moat_falsifiers()
          long_hold_clocks_entry   — dict (the ticker's long_hold_clocks row/entry)
          thesis_funnel_state      — dict (one row from thesis_funnel_states.parquet)
          capital_allocation_delta — dict from engine.capital_allocation (block dict or delta only)
          delivery_waterfall_row   — dict (one row from delivery_waterfall.parquet for this ticker)
          pricing_power_state      — dict or None (from stock_fundamentals pricing_power block)
          material_8k_events_rows  — list[dict] (rows from material_8k_events.parquet for ticker)
          statements_df            — pd.DataFrame (statements.parquet slice for ticker, optional)
          price                    — float or None (current price, optional)
          shares                   — float or None (shares outstanding, optional)
          net_debt                 — float or None (current net debt, optional)

    Returns
    -------
    dict with keys:
      schema, ticker, generated_at, _display_only, _horizon_role, _version
      ffb_r2_coverage_copy         — verbatim FFB-R2 text (LHB-W3 requirement)
      a1_questions                 — dict, five questions answered from data
      business_evidence_axis       — list of sensor dicts
      a6_events                    — list of A6 hard-stop event dicts
      expectation_burden_axis      — dict
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    # --- Extract sources ---
    moat_result: dict | None = sources.get("moat_falsifiers_result")
    clocks_entry: dict | None = sources.get("long_hold_clocks_entry")
    funnel_state: dict | None = sources.get("thesis_funnel_state")
    cap_alloc: dict | None = sources.get("capital_allocation_delta")
    waterfall_row: dict | None = sources.get("delivery_waterfall_row")
    events_rows: list[dict] | None = sources.get("material_8k_events_rows")
    statements_df = sources.get("statements_df")
    price: float | None = sources.get("price")
    shares: float | None = sources.get("shares")
    net_debt: float | None = sources.get("net_debt")

    # --- Business evidence axis ---
    # Derive asof date for moat sensor staleness check
    moat_asof: str | None = None
    if moat_result and isinstance(moat_result, dict):
        moat_asof = moat_result.get("as_of") or moat_result.get("asof")
    if moat_asof is None and funnel_state and isinstance(funnel_state, dict):
        moat_asof = funnel_state.get("as_of")

    moat_sensors = _moat_sensors_to_axis(moat_result, moat_asof)
    funnel_sensor = _funnel_to_sensor(funnel_state)
    cap_sensor = _cap_alloc_to_sensor(cap_alloc)
    clock_sensors = _clocks_to_sensors(clocks_entry)

    # Pricing power state sensor (optional supplementary — from stock_fundamentals)
    pp_state = sources.get("pricing_power_state")
    pp_sensor: dict | None = None
    if pp_state and isinstance(pp_state, dict):
        pp_status = pp_state.get("state")
        pp_asof = pp_state.get("as_of") or moat_asof
        pp_age = _evidence_age_days(pp_asof)
        if _is_stale(pp_age):
            mapped_status = "unverifiable"
        elif pp_status == "caution":
            mapped_status = "challenged"
        elif pp_status == "good":
            mapped_status = "no_break_observed"
        elif pp_status == "neutral":
            mapped_status = "not_observed"
        else:
            mapped_status = "unverifiable"
        pp_sensor = _sensor(
            name="Pricing power (gross profitability)",
            status=mapped_status,
            last_observation_date=pp_asof,
            evidence_age_days=pp_age,
            cadence_note="Annual (stock_fundamentals pricing_power block).",
            source_key="pricing_power.state",
        )

    business_evidence_axis: list[dict] = []
    business_evidence_axis.extend(clock_sensors)
    business_evidence_axis.extend(moat_sensors)
    business_evidence_axis.append(funnel_sensor)
    business_evidence_axis.append(cap_sensor)
    if pp_sensor is not None:
        business_evidence_axis.append(pp_sensor)

    # --- A6 hard-stop bus ---
    a6_events = _route_8k_items(events_rows)

    # --- Expectation burden axis ---
    expectation_burden_axis = _build_expectation_burden_axis(
        waterfall_row=waterfall_row,
        statements_df=statements_df,
        price=price,
        shares=shares,
        net_debt=net_debt,
    )

    # --- Five A1 questions ---
    a1_questions = _answer_a1_questions(
        business_sensors=business_evidence_axis,
        a6_events=a6_events,
        clocks_entry=clocks_entry,
        funnel_state=funnel_state,
    )

    return {
        "schema": _SCHEMA,
        "ticker": ticker,
        "generated_at": generated_at,
        "_display_only": _DISPLAY_ONLY,
        "_horizon_role": _HORIZON_ROLE,
        "_version": _VERSION,
        # FFB-R2: verbatim coverage copy in every packet header
        "ffb_r2_coverage_copy": _FFB_R2_COVERAGE_COPY,
        # Five A1 questions (brainstorm §A1)
        "a1_questions": a1_questions,
        # Business evidence axis: per-sensor list
        "business_evidence_axis": business_evidence_axis,
        # A6 hard-stop bus events
        "a6_events": a6_events,
        # Expectation burden axis (descriptive only)
        "expectation_burden_axis": expectation_burden_axis,
    }
