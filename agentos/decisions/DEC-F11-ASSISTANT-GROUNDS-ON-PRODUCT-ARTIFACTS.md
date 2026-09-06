---
schema: agentos.decision.v1
key: F11-ASSISTANT-GROUNDS-ON-PRODUCT-ARTIFACTS
question: >
  What may an F11 research answer be grounded in, who owns recurring-brief
  scheduling, and what may a chat turn write back to a user Thesis?
answer: >
  Grounding is a closed list — shipped product artifacts, their Tier-2 receipts,
  and the caller's own objects. Repo internals stay forbidden on any
  public/subscriber surface except the existing env-only operator allowlist, and
  no model-emitted numeric confidence is allowed anywhere. Recurring briefs are a
  subscription over the EXISTING nightly (daily.yml) and weekly (weekly.yml) job
  owners; F11 mints no second scheduler, and a slot that cannot produce shows a
  typed degraded state in plain words. A chat turn may only propose an amendment
  row carrying amended_from and K1 EvidenceRef pointers; it may never edit a
  Thesis in place and may never originate a score. Email delivery is recorded as
  an unbuilt dependency (MO-PAID-085), not claimed.
rationale: >
  All three rows were DEFER-sequenced behind the Thesis-object vertical, so the
  risk was not building too little but building the wrong authority: a research
  corpus that quietly widens internals retrieval, a second per-user scheduler
  beside the nightly, or an assistant that edits a user's thesis. Freezing the
  contract as records now lets the later slices be implemented without re-opening
  A7, CXI-R23a or the DNR kills, and forces the unwired email path to be disclosed
  rather than assumed.
alternatives:
  - option: Let the research answer read research docs and engine source for depth
    why_not: >
      DNR:KILL-PUBLIC-INTERNALS forbids repo-internals retrieval on any
      public/subscriber surface; the sole exception is the env-only operator
      allowlist already implemented at engine/neuralweb/brain_gateway.py:406-424.
  - option: Give recurring briefs their own per-user scheduler (pg_cron or app timer)
    why_not: >
      A second scheduler duplicates the nightly job owner, splits failure
      disclosure across two systems, and makes staleness invisible; the ledger row
      itself names the existing job/event owners as the owner.
  - option: Let a chat turn update the thesis directly when the user says yes
    why_not: >
      In-place edits destroy immutable history and let an assistant author a
      published version; propose-plus-human-publish keeps A7 intact and keeps the
      version chain auditable via amended_from.
  - option: Claim email delivery because app/mailer.py exists
    why_not: >
      engine/portfolio_digest.py:5 states the send path is deliberately unwired and
      no mailer is imported; claiming delivery would fabricate a capability. It is
      recorded as the MO-PAID-085 dependency instead.
evidence:
  - "F00C ledger rows: research/market_intelligence_productization/MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv lines 102 (MO-PAID-031), 103 (MO-PAID-032), 107 (MO-PAID-054), 67 (MO-PAID-085), 105 (MO-PAID-047)"
  - "research/DO_NOT_REBUILD.md:64 DNR:KILL-PUBLIC-INTERNALS; research/DO_NOT_REBUILD.md:54 DNR:KILL-LLM-CONFIDENCE"
  - "engine/neuralweb/brain_gateway.py:346 internals tool set; :406-424 _internals_allowed(BRAIN_INTERNALS_ALLOWLIST); :3950 research-mode prompt branch; :1506-1512 authority=context_only"
  - "app/main.py:1376 /api/brain/chat; :1440 /api/brain/stream; :1089 /api/ask; mode gate accepting only chat|research near :1389"
  - "engine/neuralweb/constitution.py:95 A7_ORIGINATE; :106-107 Article 1 origination ban"
  - ".github/workflows/daily.yml:36-37 DST cron pair; :3236 build_session_digest; :3946 build_briefing; .github/workflows/weekly.yml:4 weekly cron"
  - "engine/portfolio_digest.py:5,15 send path deliberately unwired; app/mailer.py:342 send() exists but unwired"
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_POST_TIMEOUT_COMPLETION_ARCHITECTURE_2026-09-02.md:300-330 F11 host/tenancy/schema freeze"
  - "research/market_intelligence_productization/FABLE_A_K1_EVIDENCE_FOUNDATION_COMMISSION_WITH_AUTHENTICATED_MO_RIDER_2026-08-23.md:223-267 EvidenceRef/EvidenceBlock/EvidenceRecipe"
affects:
  - "WS:MARKET-OS"
  - "research/market_intelligence_productization/MARKET_ONTOLOGY_F11_POST_VERTICAL_CONTRACT_2026-09-06.md"
  - "engine/neuralweb/**"
confidence: high
reversibility: easy
decided_by: "session 7cd4fae1 (Meta-CEO B lane marketontology-b4-f11-post-vertical)"
decided_at: 2026-09-06
---

Body prose optional; the frontmatter above is the record.
