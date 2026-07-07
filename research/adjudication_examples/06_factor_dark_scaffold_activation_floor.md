# Factor Dark Scaffold — Activation Floor Before Any Clamp Wiring

**Source:** PR #1598 family (Factor Intelligence x Neural Web integration wave). Primary doc: `research/factor_intelligence/NW_INTEGRATION_ADJUDICATION_BY_FABLE.md`. **Status:** canonical (RUL-SUCC-8).

## What was asked

The Factor Intelligence program had shipped factor panel machinery (DNA class, style regime, synthetic twin, alibi share). The Neural Web integration docket asked: when may the factor de-escalation clamps actually fire? The dark scaffold (Lane E) was designed to hold the clamp wiring until the activation floor was met. The question was what constitutes a legally sufficient activation floor.

## What was decided (the holding)

- **RUL-NW6 (shadow-ledger floor before A3):** minimum 25 episode-clustered would-have-fired events spanning at least 3 calendar months (EI R6 convention), graded at the relevant hypothesis's own falsifier, THEN an explicit Fable ruling, before any clamp wiring. This is the named activation floor.
- **Dark scaffold behavior:** Lane E (`scripts/build_factor_deescalation_shadow.py`) refuses to run without a GATE-PASSED verdict artifact. The scaffold pre-commits the row schema for the would-have-fired shadow log but does not execute the clamp logic. Below the floor the scaffold runs and logs shadow events with `state='accruing'` — nothing fires on any live path.
- **Family BH withheld:** BH FDR across hypotheses H1-H5 is withheld until H4/H5 floors (estimated mid-2027); no GATE-PASSED verdict exists before then. The `BH-WITHHELD` chip is mandatory on factors.html; without it, a PRE-FDR INTERIM read could be mistaken for actionable.
- **Five hypotheses registered dark:** H1 (tech signal quality vs DNA class), H2 (stop-out rate vs alibi share), H3 (twin-bleed de-escalation), H4 (factor-decay exit), H5 (style-regime conditioning) — all registered with frozen falsifiers in the preregistration but DARK until individual floors are met and a GATE-PASSED artifact exists.
- **Lane E CI guard:** `scripts/check_factor_boundaries.py` asserts factor modules never write Article-2 paths (`alert_triage`, `board_ordering`, `top_setups`, `attention_queue`, `push_floor`). Static CI enforcement, not runtime.
- **`allowed_actions` is inert metadata:** the `allowed_actions` field in the state artifact is self-documentation only, never a behavior switch. The CI guard fails if any code outside the state builder and render/admin surfaces reads `allowed_actions`. Authority is granted only by graded probation via `constitution.grant_authority`, never by a JSON boolean.
- **Cross-job lag documented:** the nightly factor panel job commits AFTER the engine job; any de-escalation clamp reading runner-local panel files would read a file absent in the cortex job's tree. The dark scaffold reads only committed artifacts.

## Tier mapping under the succession bench

| Decision | decision_class | Tier | Decider |
|---|---|---|---|
| Establish 25-event/3-month activation floor | new rule touching A3 authority path | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| Ship dark scaffold (clamps inactive) | display-only infrastructure | **T0** (ROUTINE) | Opus alone |
| Block `allowed_actions` as behavior switch | authority guard (Article 2) | **T1** (CONSEQUENTIAL) | Opus + completed packet |
| Register H1-H5 dark (no clamp logic) | deferred with named floor conditions | **T0** (ROUTINE) | Opus alone |
| CI boundary guard wired | mechanical CI enforcement | **T0** (ROUTINE) | Ops; no packet required |

The activation floor rule (RUL-NW6) is T1 because it defines when a future adjudicator may approve A3-level authority (veto/downsize). Shipping the dark scaffold without clamp wiring is T0 — display-only infrastructure with no authority implications. Note: if a future session proposes to wire clamps without a GATE-PASSED artifact, that is T2 (scored-path behavior change).

## Lenses that did the work

- **Authority:** the central lens. The constitutional promotion path (DISPLAY to SHADOW to CONFIRMER to SCORED) requires graded probation at each rung; RUL-NW6 operationalizes the Shadow-stage floor with specific checkable numbers. Without this floor, the A3 clamp path would be open immediately on any favorable anecdote.
- **Statistics:** BH-WITHHELD chip prevents a family-level false discovery from being invisible before the BH run. The chip maps the statistical state onto the display surface honestly.
- **Build feasibility:** static CI guard catches any future code drift that would wire `allowed_actions` as a behavior switch. This is CI enforcement, not honor-system.
- **Collision:** cross-job lag (factor panel commits after engine) means runner-local panel files are absent in the cortex job's tree; the read-committed-artifact-only design avoids this class of failure.

## Citable holding

A de-escalation scaffold that reads only committed artifacts and refuses to fire clamp logic without a GATE-PASSED verdict artifact, backed by a named quantitative activation floor (25 episode-clustered events, at least 3 calendar months), is the legally sufficient form for shipping conditional authority features dark; the `allowed_actions` boolean in a state artifact must never become a behavior wire.

## Ruling IDs

RUL-NW6, RUL-NW7, RUL-NW9, RUL-NW10, RUL-NW11; RUL-SUCC-2 (T1 for A3-path decisions)
