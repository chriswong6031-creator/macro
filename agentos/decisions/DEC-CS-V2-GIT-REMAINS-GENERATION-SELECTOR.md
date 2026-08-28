---
key: CS-V2-GIT-REMAINS-GENERATION-SELECTOR
question: >
  The CS job writes an all-or-nothing local generation and best-effort pushes
  it. GH013 has rejected a legitimate generation while later nights landed.
  R2 holds verified bytes even when Git loses. Should V2 mint a new publication
  control plane, move the selector onto another existing plane, or keep Git?
answer: >
  Git remains the canonical compiled-generation selector for
  data/capital_structure/** and site/capital-structure-data. R2 remains the
  content-addressed evidence store. No new publication control plane. Push loss
  is a degraded publication state, not silent success. Identity
  (DEC:CS-V2-IDENTITY-DUAL-READ) must make re-derive reuse evidence IDs so a
  lost Git push cannot remint economics. CS-owned content-aware merge applies
  to source_manifest.jsonl conflicts; the market plane and global daily.yml
  concurrency stay untouched.
rationale: >
  House law forbids a second publication control plane. The existing company
  and shared publication machinery was not commissioned to own CS generations.
  GH013 is an org ruleset/Actions-bypass class, not an ingestion-path defect;
  later CS generations land because push_retry is best-effort and the ruleset
  is not a permanent block. Evidence already survives in R2. The load-bearing
  hole is identity under re-queue plus -X theirs wholesale-replace of the
  JSONL, both owned by W1, not by a new selector.
alternatives:
  - option: Make R2 the compiled-generation selector
    why_not: Would be a new selector path for projection/API/PIT, duplicating
      the Git generation the page and BioCatalyst adapter already bind.
  - option: Move CS publication onto a shared company publication plane now
    why_not: Out of scope; requires an operator ruling that this program does
      not own. Freeze keeps Git until that ruling exists.
  - option: Fail the CS job hard on GH013
    why_not: Would red a context-only lane for an org-admin ruleset and still
      would not publish. Keep non-fatal warning; report unpublished-in-Git in
      health after W1/W2.
evidence:
  - ".github/workflows/daily.yml CS push step git pull --rebase --autostash -X theirs origin main"
  - ".github/workflows/daily.yml push failure is ::warning non-fatal"
  - "storage.store_id mix at freeze: r2_shared 1258, r2_research 714"
  - "docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md Git generation plus R2 evidence"
  - "research/CAPITAL_STRUCTURE_INTELLIGENCE_V2_MASTERPLAN_2026-08-18.md §9"
affects:
  - "WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2"
  - "capital-structure-intelligence"
  - ".github/workflows/daily.yml"
  - "data/capital_structure/"
confidence: high
reversibility: costly
decided_by: cursor-grok-4.6
decided_at: 2026-08-18
review_by: 2026-08-25
superseded_by: DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE
---

SUPERSEDED 2026-08-18 by Sol AMEND of PR #5901. Proposed by Cursor Grok 4.6,
not Fable. Git as compiled-generation selector and "no new publication plane"
remain in force and are restated by the successor. The CS-owned push-time
content-aware merge of source_manifest.jsonl is withdrawn. See
`DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE`.
