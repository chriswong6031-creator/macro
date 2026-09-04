---
key: ACTION-DASHBOARD-TIER1-TELEMETRY-DEMOTION
question: >
  When a live/runtime feature has useful phase, coverage, delay, liveness, or
  provisional-state information, may it claim a standalone above-fold module on
  an action dashboard merely because that telemetry is technically useful?
answer: >
  No. On an action dashboard, the primary decision object owns Tier 1 and the
  fold. Operational telemetry defaults to contextual object chips, an existing
  LENS/drilldown, or machine observability. A new standalone first-level module
  is allowed only when the information directly changes the user's primary
  decision, the PR names that user job, and real browser evidence shows that the
  primary answer remains dominant on desktop and narrow mobile in both themes and
  both languages. A DOM-presence test is never acceptance for new customer-facing
  acreage.
rationale: >
  macro PR #5786 made the CN Breathing Platform technically honest but promoted
  phase/coverage/session telemetry into a standalone strip immediately above
  "What to act on now". Its surface test then asserted that the strip existed,
  protecting an implementation detail rather than the primary stock-selection
  workflow. In production the block wrapped into a narrow grid item and consumed
  a large amount of prime viewport while adding little decision value. The
  binding Master Product Design System already requires one primary question to
  be answered above the fold, but that composition law was not translated into
  the local PR invariant. PR #6751 demotes the page-level strip while preserving
  the useful per-card live state and the underlying freshness/feed-floor honesty.
alternatives:
  - option: "Allow any live telemetry to occupy Tier 1 because freshness matters"
    why_not: >
      Freshness and liveness matter, but their importance does not imply a
      standalone module. Contextual placement preserves the information without
      displacing the action surface.
  - option: "Remove the CN live runtime layer entirely"
    why_not: >
      The per-name intraday state is useful and the feed-floor/fail-closed contract
      is correctness-critical. The defect is presentation hierarchy, not the live
      capability itself.
  - option: "Make CI automatically judge whether a dashboard looks good"
    why_not: >
      The canonical visual-evidence gate is deliberately mechanical and should
      remain so. It proves that reviewers have the required browser states; human
      product review still adjudicates taste and whether a module earns its space.
  - option: "Create a second visual-evidence or design-governance plane"
    why_not: >
      The repository already has the Master Product Design System,
      DESIGN_DOCTRINE, capture_page_evidence.py, and check_ui_visual_evidence.py.
      The correction belongs in those existing authority boundaries, not in a
      parallel lifecycle or evidence store.
evidence:
  - "macro#5786 — introduced #cn-prophet-live page strip and a test requiring its placement above the action board"
  - "macro#6751 — removes the page-level reveal path, detaches the legacy session carrier after caching its floor, and preserves card-local live state"
  - "research/MASTER_PRODUCT_DESIGN_SYSTEM_V1.md §9 — one primary question above the fold; 1440×900 permits the answer plus at most two supporting modules"
  - "scripts/check_ui_visual_evidence.py — canonical evidence-existence gate; explicitly not a taste judge"
  - "scripts/capture_page_evidence.py — canonical real-browser evidence collector; no-browser is not a pass"
affects:
  - macro
confidence: high
reversibility: easy
decided_by: "Chairman directive 2026-09-01; product/architecture adjudication by Sol"
decided_at: 2026-09-01
---

## Scope and supersession

This is a composition and acceptance ruling, not a new scoring authority, live-data
authority, monitoring plane, or evidence system. It does not weaken the CN Breathing
Platform's quote freshness, feed-floor, coverage publication, liveness, close-SLO, or
fail-closed contracts.

For `china_stocks.html`, this decision supersedes only the **presentation** language in
`research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md` that can be read as requiring
a standalone page-level phase/coverage/provisional-close strip or banner. The live
artifact may continue to publish those fields for observability and downstream
correctness. User-visible same-session state remains contextual on the affected stock
cards; machine liveness remains in the existing observability path.

## Acceptance consequence

For future action-dashboard work, a worker must review the page as a product, not merely
prove that new markup exists. If a proposed auxiliary module sits before the primary
action object, the review must answer all of the following before acceptance:

1. What user decision changes because this module is visible at rest?
2. Why can the information not live contextually on the object, in an existing
   drilldown/LENS, or only in machine observability?
3. Does the real browser composition keep the primary answer dominant at 1440×900 and
   reachable within one swipe at 390px?
4. Do dark/light and EN/ZH captures preserve the same hierarchy?
5. Is the automated test guarding the **user/product invariant**, rather than merely
   pinning the existence or DOM position of the implementation?

If those answers are absent, the module does not earn Tier-1 acreage.
