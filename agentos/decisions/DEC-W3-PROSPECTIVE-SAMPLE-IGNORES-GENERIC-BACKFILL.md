---
key: W3-PROSPECTIVE-SAMPLE-IGNORES-GENERIC-BACKFILL
question: >
  Does DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT (#5878) authorize a
  reconstructed Prophet session to enter the W3 paired race as a prospective
  observation?
answer: >
  No. #5878 governs general Prophet outage/product recovery. It does not silently
  turn a reconstructed historical session into a W3 prospective race observation.
  W3_RACE_PREREG's missing-session law remains the W3 sample law: gaps remain
  gaps; Pages/reconstructed sessions do not enter the race. A session is admitted
  to W3 based on what W3 observed on its first natural opportunity.
  session_missing and degraded_or_unpaired are terminal W3 race dispositions.
  The only lawful maturation is unmatured → paired_accrued when a shared H=10
  grade later fills. Generic product backfill may proceed under #5878 without
  altering W3's prospective sample.
rationale: >
  W3 is a frozen prospective measurement program, not a product-availability
  ledger. #5878 deliberately writes reconstructed rows into the forward ledger
  unmarked so the published track record can recover from infrastructure
  outages. That is the right rule for the product. It is the wrong rule for a
  preregistered race whose start boundary is the first durably committed
  post-#5769 paired candidates-store stamp and whose honest-N grain is distinct
  matured H=10 sessions observed as they happened. If a later reconstruction
  could upgrade a session_missing or degraded_or_unpaired receipt, W3 would
  silently harvest look-ahead from inputs that have since advanced — the accepted
  cost #5878 recorded for the product ledger, and exactly the contamination the
  W3 freeze forbids. The fence lives in W3's own sessions.jsonl history rather
  than a second global provenance system, and it does not require the general
  forward ledger to grow a reconstructed flag.
alternatives:
  - option: Let #5878 unmarked reconstructed rows enter W3 like any other candidate stamp
    why_not: >
      Collapses the W3 sample into the product ledger. The prereg's "no backfill /
      Pages-only nights are not sessions" clause would become unenforceable the
      first time a force-majeure reconstruction landed in the candidates store.
  - option: Require the general forward ledger to grow an origination_disclosure / reconstructed flag and have W3 filter on it
    why_not: >
      The operator declined that flag in #5878. Building a competing global
      provenance system to undo that choice is out of scope. W3 can keep its own
      first-opportunity history without forcing the product ledger to mark rows.
  - option: Leave session_missing as an in-memory status.json pointer with no durable history
    why_not: >
      That is the PR-3C hole. A rewritten status.json cannot stop a later nightly
      from treating a reconstructed stamp as a new observation. Terminal
      dispositions have to be append-only.
evidence:
  - "research/prophet_fusion/W3_RACE_PREREG.md §0 / §2 / Missing-session law: gaps remain gaps; no reconstruction; Pages-only nights are not sessions; start boundary is the first durably committed post-#5769 paired stamp."
  - "agentos/decisions/DEC-FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT.md — #5878 merged 2026-08-18: reconstructed rows enter the forward ledger unmarked. Scope is infrastructure-outage product recovery, not W3 race admission."
  - "PR-3C #5839 wrote liveness names including session_missing but only walked stamps already present in the candidates store, so a required absent session never left a durable receipt and a later backfill could accrue."
affects:
  - "WS:PROPHET-CONDITIONAL-FUSION"
  - "engine/us_prophet_w3.py"
  - "data/us_prophet_rank/w3/"
  - "DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-18
---

## What this does not change

#5878 remains standing for Prophet product recovery. `us-board-frozen-alpha-2026-08`
stays disclosed and not backfillable. This record does not add a reconstructed flag
to the general forward ledger and does not authorize Pages-only W3 backfill.
