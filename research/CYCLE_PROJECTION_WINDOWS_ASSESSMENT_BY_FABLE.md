# Cycle Projection Windows — assessment & program direction

Date: 2026-07-27 · Author: Fable main loop (operator-commissioned)
Companion PR: falsifier-surface reframe (cycle/markets/sector/country pages) + measurement.html → Calibration Lab.

## Operator direction being implemented

1. Falsifiers stop being front-facing user content. They stay fully alive in the
   background as the learning loop (tripwire engine, ledgers, calibration scorecards).
2. User surfaces present the best **current projection with the data available now** —
   windows of likely topping/bottoming, never claims of predicting the future — plus a
   daily read of the **actual current cycle state** (turns made, rotations underway).
3. Windows should tighten as corroborating signals accrue near a turn.

## Verdict on measurement.html: KEEP — it is the program, reframed

The page (now the **Calibration Lab**) is the only mechanism by which "windows get more
accurate over time" is engineering rather than marketing. Every ingredient the operator
asked for already reports here: turn precision/recall vs an independent oracle, cone
coverage vs nominal (the window-width feedback), Brier skill of directional labels,
hazard-model gate cells, the null library preventing re-mining of dead constructions,
and per-engine forward ledgers accruing live cohorts. Killing it would sever the loop.
What was wrong was its *identity* (self-refutation as the hero) and its CSS, not its
existence. Both are fixed in the companion PR; a cycle.html forward ledger is added so
the flagship page's own projections become gradeable the same way.

## What actually tightens windows (ranked, honest)

1. **Ship the D5-gated recalibrated cone (highest single lever).** Displayed windows
   still come from hand lerp constants; `data/cycle_ontology/cone_recalibration.json`
   already computes realized-error half-widths. The **forward-only multiplier** is the
   deployable number (the headline multiplier is polluted by chronically-overdue
   re-anchoring repaint — W2.4 finding). Gate: cone coverage on the forward-only slice
   reaching nominal on the live cohort. Until it clears, display-tier only.
2. **Hazard-model adoption is the "tightens as we approach" mechanism.** P(turn ≤ 1/3/6m)
   cells that PASS the W4.2 gate already ship on cards; the adoption-gap panel shows
   hazard columns rendered on zero other pages. Wiring hazard into sector/country card
   emphasis (display-tier, badge-honest) is cheap and is exactly "the window sharpens
   as the signal nears".
3. **Confirmation quality over prediction bravado.** Turn P/R for the projection layer
   is red, but *descriptive structure is measured and solid* (confirmed turns, phase
   clocks, risk clustering). The daily "has the turn already happened / is rotation
   underway" read is our strong product today — surfaces should lead with it, windows
   second, forecast-flavored copy nowhere (done in the companion PR).
4. **Note-freshness loop.** A fired tripwire now demotes to a quiet "read being
   updated" chip, with the live engine read authoritative. The background queue of
   fired-but-unre-authored notes lives in the Lab (grading closure section). Follow-up
   worth building: a small "notes awaiting re-author" counter in the Lab + a standing
   operator/main-loop cadence to re-author them. LLM law: re-authoring is analyst/
   adjudication work — never autonomous LLM signal origination.

## Predictor search (washout / mania / velocity / extension) — what is licensed

First-principles framing the operator asked for: bottoms are washout signatures
(capitulation breadth, volume exhaustion, downside-vol asymmetry), tops are mania
signatures (extension, participation narrowing, blow-off velocity). The gauntlet has
already adjudicated several constructions in this space — the registry rows bind:

- **KILLED as standalone timers:** down-volume envelope contraction (PSS-F1 — the
  near-low property is generic to new-low conditioning); semivariance RV_down/RV_up
  flip (PSS-F4 — later than the incumbent, though it uniquely cleared its mirror
  placebo); per-name outcome audition (PTT-W1a); election cycle standalone;
  cross-sectional commodity momentum. **Do not re-propose these constructions.**
- **OPEN and explicitly upgraded/retained lanes:**
  - **Incumbent × semivariance-asymmetry confluence** — F4 is on record as "the single
    best candidate for a future incumbent×asymmetry CONFLUENCE probe". This is the
    canonical washout probe to run next, as confluence, not standalone.
  - **Structure-measurement tailoring** (PTT-W1b reversion-by-scale) — upgraded under
    the timing ruler; W3 Prophet shadow is the evidence vehicle.
  - **Covariate expansion** (CPI masterplan): the binding constraint is information
    content, not mining machinery. The collinearity verdict showed our price-derived
    legs are one signal in three coats — new *channels* (breadth internals, credit,
    liquidity, policy calendar) are where a mania/washout ranker can actually come
    from. This is the first-principles answer: add orthogonal information, don't
    re-massage price.
- **Rule of the road:** display-tier context ships freely (nulls never block accrual);
  authority (rank/size/gate) only through pre-registered gates. "Not found yet" ≠
  "does not exist" — kills close constructions, not the search space.

## Explicitly deferred (needs its own prereg/adjudication)

- Applying recalibrated cone multipliers to displayed windows (item 1) — gated, not
  copy-edited into existence.
- Any new washout/mania family — each gets a charter + pre-registered falsifier via
  the experiments registry before code.
