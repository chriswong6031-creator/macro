---
key: F12-PUBLIC-API-V0-ADMISSION-2026-09-06
question: >
  Does B ship a keyed public API in v0 — over which already-owned contracts,
  with what key, idempotency, response-separation, webhook and redistribution
  terms — given that no public producer exists, K1/K3/K5 are unaccepted,
  K2-C/K3-D are explicitly not accepted, and several upstream sources bar
  redistribution?
answer: >
  NO keyed public API in v0. MO-PAID-055 and MO-PAID-084 are REFUSED-IN-V0
  behind admission gate G1-G4; MO-PAID-056 + MO-DELTA-038 (single child) are
  REFUSED-IN-V0 for want of a canonical event/job transport owner;
  MO-DELTA-036 (idempotency) and MO-DELTA-037 (schema_version +
  inference_metadata) are CONTRACT-FROZEN and bind the first admitted public
  response; MO-DELTA-039 is SPLIT — computation confirmed absorbed by
  WS:MARKET-OS D1-D9, public exposure reclaimed by F12 and refused. Internal
  data rights never imply public redistribution rights. No second
  auth/tenant/job/event/secret/webhook-retry plane. No product code ships
  under this record.
rationale: >
  Three independent blockers each hold today. (1) No contract to sell: every
  analytic contract a public API would carry is unaccepted, and a public API
  is a versioned promise of stability we cannot yet keep. (2) The one safe
  egress class — a user reading their own data — is already reachable through
  the existing Supabase bearer spine (app/main.py:952, app/main.py:1044), so a
  key would be a second credential for the same principal on the same data,
  the exact MMX-004 divergent-identity failure that spine's docstring names.
  (3) No consumer exists (real_consumer NONE on all seven rows). A refusal
  with an objective, owner-assigned reopen gate terminates the rows; another
  DEFER would not. Every capability the refusal freezes for later projects
  over a named existing owner rather than a new plane.
alternatives:
  - option: Ship a narrow read-only keyed v0 over already-owned self-data
    why_not: >
      That payload is already authorized by require_user, so the key adds a
      second credential and no capability; the real want is bulk self-export
      (MO-PAID-086), a different row awaiting a data-export product spec.
  - option: Defer the seven rows again pending contract acceptance
    why_not: >
      DEFER is what these rows have carried since 2026-09-02; it produced
      re-litigation, not a decision. The reviewer rejects a deferral answer.
  - option: Ship signed outbound webhooks on a file-backed retry ledger
    why_not: >
      download_quota fails OPEN by design for a counter; fail-open on a
      delivery ledger duplicates a side effect inside the customer's system,
      and the retry/dedupe/secret state is the forbidden second plane.
  - option: Confirm MO-DELTA-039 wholly absorbed by D1-D9
    why_not: >
      D1-D9 owns product scenario computation, never public exposure; a bare
      absorption note would let a D-wave session ship publicly under an F12
      refusal.
  - option: Infer public redistribution rights from the estate's existing
      internal display/compute rights over the same sources
    why_not: >
      This is the authority hop the redistribution clause exists to forbid.
      R-1..R-4 (`MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md`)
      and `docs/QUAL_DATA_COMPLIANCE.md` scope each licence to display/derived
      use inside this product; none grants bulk or verbatim re-publication.
      Treating display rights as redistribution rights would breach those
      terms the moment any public payload carried the source, so every
      excluded source stays excluded absent separate affirmative evidence.
evidence:
  - "app/main.py:952 require_user (Supabase token; 'no second auth cache' — MMX-004)"
  - "app/main.py:1044 GET /api/account; app/billing.py:643 read_entitlement (called main.py:1021, main.py:1052)"
  - "engine/research_vault/download_quota.py:154 check_and_increment; docstring L20-32 entitlement fails CLOSED / counter fails OPEN loud"
  - "app/billing.py:1448,1456 stripe_events on_conflict=id — the existing dedupe owner"
  - "scripts/deploy/0004..0008 *.sql — macro's whole DDL ledger; no supabase/migrations tree exists"
  - "MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv rows for MO-DELTA-036/037/038/039, MO-PAID-055/056/084"
  - "WAVE_GRAPH_2026-08-23.json nodes ALPHA-K1 READY_TO_COMMISSION; ALPHA-K2/K3/K5 TODO"
  - "agentos/workstreams/WS-MARKET-OS.md:142 D1-D9 (scenarios, todo); E1-E3 (alerts/digest)"
  - "MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md:95,115,124,127 (BIS/R-1/R-2/R-3)"
  - "docs/QUAL_DATA_COMPLIANCE.md:23 (no raw-feed re-publication), :133 (no transcript full-text), §2.3 card panels"
  - "MARKET_ONTOLOGY_F00C_CLOSURE_SUMMARY_2026-09-02.md:55 — CRG R0 #6596 landed zero runtime; F12 gap untouched"
affects:
  - "WS:MARKET-OS"
  - "research/market_intelligence_productization/**"
  - "app/main.py"
  - "app/billing.py"
  - "engine/research_vault/download_quota.py"
confidence: high
reversibility: easy
decided_by: coo-fable (Meta-CEO B seat, Chairman override 2026-09-06)
decided_at: 2026-09-06
review_by: 2026-12-06
---

# DEC-F12-PUBLIC-API-V0-ADMISSION-2026-09-06

No keyed public API, no API keys, and no outbound webhooks ship in v0. The
admission gate G1-G4 (contract acceptance, tenancy scope, per-source rights
evidence, named consumer) is the only path to reopening MO-PAID-055/084/056
and MO-DELTA-038. MO-DELTA-036 and MO-DELTA-037 freeze forward contracts
(idempotency semantics; mandatory `schema_version` + `inference_metadata`)
that bind the first admitted public response regardless of when that is.
MO-DELTA-039 splits: its computation half is confirmed absorbed by
`WS:MARKET-OS D1-D9`; its public-exposure half is reclaimed by F12 and stays
refused under the same gate as MO-PAID-055. See the full ruling at
`research/market_intelligence_productization/MARKET_ONTOLOGY_F12_PUBLIC_API_ADMISSION_2026-09-06.md`
for the per-question rationale, the redistribution clause, the forbidden
second-plane table, and the frozen bilingual customer-facing copy.

## Admission gate G1-G4

- G1 — Contract: `ALPHA-K1` accepted in a recorded DEC, plus at least one of
  `ALPHA-K3` / `ALPHA-K5`. `K2-C` / `K3-D` excluded until separately accepted.
- G2 — Scope owner: the tenancy migration (B-F12-1 / `WS:MARKET-OS A2-A6`)
  merged and applied.
- G3 — Rights: a per-source redistribution evidence sheet covering every
  field in the proposed payload, fail-closed.
- G4 — Consumer: at least one named external consumer recorded in a
  commission.

Until all four hold, no session in any lane may propose, spec, or ship a
public/keyed endpoint, an outbound webhook, or an API key.
