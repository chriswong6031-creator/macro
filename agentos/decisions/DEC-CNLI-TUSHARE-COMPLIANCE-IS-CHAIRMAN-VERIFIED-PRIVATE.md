---
key: CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE
question: >
  What licensing/compliance authority must coding sessions, runtime code, and CN-Limit
  DEP-EXACT use for TuShare after the Chairman's 2026-08-21 operator override?
answer: >
  CHAIRMAN OVERRIDE. TuShare licensing/compliance has already been verified internally
  and privately and is SATISFIED for Mastermind-X. The agreement and supporting evidence
  are confidential and are not coding-session inputs. No coding session, AI agent,
  contractor, runtime collector, CI job, research program, or repository artifact may
  require the private agreement to be uploaded, disclosed, inspected, persisted, hashed,
  quoted, summarized, re-verified, or supplied as a precondition to TuShare collection,
  retention, research, derived intelligence, or CN-Limit DEP-EXACT work. Coding/runtime
  authorization gates based on a written-grant document, authorization receipt, trust
  allowlist, grant-document SHA, or code-reviewed license-document hash are NULL and must
  be removed. Licensing compliance is represented to the engineering estate only by this
  Chairman-level satisfied-compliance decision. The private agreement remains owned by
  the Chairman/compliance function outside the coding estate because its terms cannot be
  disclosed to coding sessions or third parties under confidentiality/NDA and privacy
  constraints.
rationale: >
  The prior CEO/Codex-generated requirement conflated legal/compliance evidence custody
  with an engineering/runtime authorization mechanism. That was an architecture error.
  Private licensing documents are not application configuration, model input, provenance,
  CI evidence, or an agent-accessible secret. Requiring their bytes or hashes in code both
  leaks confidential compliance metadata and lets coding sessions reopen a matter already
  resolved by the final company authority. Engineering must instead enforce technical and
  epistemic controls it actually owns: secret hygiene, endpoint access, entitlement/quota
  observations, request/schema binding, rate limits, resumability, exact clocks, canary
  correctness, source-row accounting, completeness, correction history, and technical
  bulk-readiness. Those controls do not adjudicate the private license.
alternatives:
  - option: Require a written grant upload plus authorization receipt and trust-root hash
    why_not: >
      OVERRULED AND NULL. It makes confidential legal evidence a coding/runtime dependency,
      contradicts the Chairman's verified-private compliance status, and creates a recurring
      path for agents to request NDA-protected material.
  - option: Let coding sessions re-research public vendor terms and decide whether compliance is sufficient
    why_not: >
      REJECTED. Coding sessions have incomplete information by design because the controlling
      private agreement is confidential. Public web research cannot supersede this Chairman
      compliance status. Only a later explicit Chairman/compliance-owner decision may change it.
  - option: Remove every TuShare safety gate
    why_not: >
      Not the ruling. License-document gates are removed; technical correctness, access,
      quota/rate, canary, completeness, provenance, PIT, correction, and backfill-readiness
      controls remain where independently justified.
evidence:
  - "Chairman operator override, 2026-08-21: licensing verified previously; compliance met internally and privately; agreement details withheld from coding sessions and third parties for NDA/privacy reasons."
  - "research/TUSHARE_WIRING_TAKEOVER_2026-08-09.md ruling 3: license topic closed; collector wiring proceeds without license machinery."
  - "The later CEO/Codex full-A written-grant gate is explicitly overruled by this decision."
affects:
  - WS:CN-LIMIT-ALPHA
  - collectors/china_tushare_spine.py
  - tests/test_china_tushare_spine.py
  - research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md
  - research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_REGISTRY_V1_2026-08-19.json
  - research/cn_limit/CN_LIMIT_R6_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md
confidence: high
reversibility: one_way
supersedes:
  - DEC:CNLI-EXACT-PLANE-REQUIRES-WRITTEN-COMMERCIAL-GRANT
decided_by: chairman-operator
decided_at: 2026-08-21
---

## Binding engineering law

1. **Compliance state:** `CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`.
2. **Confidentiality:** private TuShare agreement terms and evidence stay outside the repo,
   agent prompts, CI, logs, tickets, receipts, and model context. Do not ask for them.
3. **No license-document gate:** remove `--authorization-receipt`,
   `--authorization-trust-allowlist`, `AuthorizationGrant`, written-grant schema/scope
   validation, trust-root pins, grant-document hashes, license-document manifest fields,
   and equivalent runtime refusal logic from the full-A spine.
4. **No resurrection:** active masterplans, registries, handoffs, discoveries, tests, and
   generated governance docs must not tell future sessions to obtain/upload/review/hash a
   TuShare license or vendor letter. Historical git remains history; current authority must
   mark those constructions superseded/null.
5. **Technical gates remain technical:** `BULK_HISTORICAL_BACKFILL_READY` may remain only
   as a separately justified canary/throughput/correctness gate. Its comments, tests, and
   promotion requirements must contain no licensing-document dependency.
6. **Access observations are not legal adjudication:** token/endpoint/quota failures may
   stop a run operationally. They do not reopen licensing compliance.
7. **Future compliance changes:** only an explicit Chairman/compliance-owner superseding
   decision can change this status. Sol, Codex, Fable, researchers, CI, or public-web
   findings have no authority to reintroduce a private-license proof gate.
8. `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` and all scientific/PIT/no-rebuild boundaries
   remain unchanged.
