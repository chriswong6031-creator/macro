---
key: BIOCATALYST-CATALYST-RADAR
title: BioCatalyst Catalyst Radar — trial milestones and later regulatory tenants
objective: >
  Turn the proven BioCatalyst clinical truth plane into a watchable,
  correction-safe catalyst-event product without inventing outcomes or signals.
  Done for P1-1 means an entitled user can see nonzero Trial Milestone rows from
  the real production generation, understand date precision and revision or
  cancellation lineage, open the exact evidence receipts, and distinguish every
  typed failure/coverage state. Done for this workstream's initial arc means the
  catalyst-event spine is production-proven and ready to accept later lawful
  regulatory tenants without rebuilding identity, time, correction or evidence.
status: active
program: biocatalyst
repos: [macro]
owner: coo-fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - engine/biocatalyst/catalyst_events.py
  - app/biocatalyst.py
  - templates/biocatalyst.html.j2
  - templates/biocatalyst.js
  - templates/biocatalyst.css
  - site/biocatalyst.js
  - site/biocatalyst.css
  - tests/test_biocatalyst_catalyst_events.py
  - tests/test_biocatalyst_catalyst_radar.py
waves:
  - id: P1-0
    title: Post-P0 capability ledger, first-vertical adjudication and architecture freeze
    status: done
    pr: 6112
    next_action: >
      Done. P1-0 established the capability ledger, falsified the PDUFA-first
      prior on readiness evidence, froze P1-1 and returned ratification plus
      workstream-home authority to Sol.
  - id: P1-1
    title: Catalyst Radar — Trial Milestones vertical
    status: todo
    depends_on: [P1-0]
    next_action: >
      Execute research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md
      exactly: admitted CT.gov generation + record history -> deterministic
      catalyst-event projection -> one entitled API -> upgraded Trial Milestones
      Radar -> evidence drill-down -> real entitled production proof. Default
      horizon must be non-vacuous on the current cohort (frozen >=365-day design).
      Stop after this one vertical; do not start another tenant.
  - id: REGULATORY-TENANT
    title: Regulatory/PDUFA tenant on the proven catalyst-event spine
    status: todo
    depends_on: [P1-1]
    next_action: >
      Unauthorized. Requires a lawful prospective corporate-plane disclosure
      source contract, rights/ownership ruling and separate Sol commission.
      Drugs@FDA retrospective approvals cannot be relabeled as forward PDUFA.
decisions:
  - DEC:BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR
  - DEC:BIOCATALYST-P1-SOL-RATIFIES-TRIAL-MILESTONE-RADAR
discoveries: []
landmines:
  - >-
    The source supplies sponsor-submitted ClinicalTrials.gov primary/overall
    completion dates, often ESTIMATED. They are not topline-readout announcement
    dates. Front-facing copy and API names must say Trial Milestones.
  - >-
    The active source/launch soak closes 2026-08-26T02:00:00Z. P1-1 may read the
    admitted generation but may not mutate config/biocatalyst_sources.yml, the
    launch manifest, cohort/allowlists, collector cadence or launch-SLO verifier.
  - >-
    P0 route latency is proven lawful but material (roughly 4.5-7.9s). Reuse the
    request-local retained-generation seam from #6052; do not add process-lifetime
    caches or reopen ContractRegistry/bootstrap speculation.
  - >-
    Sponsor-to-issuer resolution is partial. Only reviewed_admitted mappings may
    resolve; every other row stays typed unresolved_sponsor. No fuzzy identity.
  - >-
    The default 90-day primary-completion-only cut is naturally empty on the live
    four-NCT cohort. P1-1 must use the frozen non-vacuous horizon/event-kind law
    rather than manufacturing fixtures as production proof.
do_not_redo:
  - "Do not reopen completed WS:BIOCATALYST-RECOVERY-V2 or call P1-1 recovery."
  - "Do not use data/clinicaltrials/trials.parquet as the product truth plane; it is a separate ticker-keyed altdata collector with no milestone dates."
  - "Do not call registry milestone dates approvals, outcomes, readout announcements or market signals."
  - "Do not add probability, materiality, score, rank, composite, gate, size or trade authority."
  - "Do not expand the four-NCT cohort, register the JV snapshot source, activate Drugs@FDA, add alerts/Neural Web/Prophet, build a company dossier or add cash/runway inside P1-1."
  - "Do not create a second clinical/regulatory store, event workspace, identity plane, correction plane or queue."
  - "Do not start the REGULATORY-TENANT wave because P1-1 merges; it needs a separate lawful-source and Sol authority decision."
artifacts:
  - research/BIOCATALYST_P1_RECHARTER_AND_FIRST_VERTICAL_ARCHITECTURE_2026-08-20.md
  - research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md
  - agentos/decisions/DEC-BIOCATALYST-P1-FIRST-VERTICAL-MILESTONE-RADAR.md
  - agentos/decisions/DEC-BIOCATALYST-P1-SOL-RATIFIES-TRIAL-MILESTONE-RADAR.md
next_action: >
  Dispatch exactly P1-1 from
  research/BIOCATALYST_P1_CONTINUATION_HANDOFF_2026-08-20.md after this records
  workstream lands. One principal builder owns source projection, API, useful
  Radar surface, evidence drill-down, tests, merge and real entitled production
  proof end to end. Stop after P1-1 and return to Sol. No later tenant or broader
  BioCatalyst parity/intelligence program is authorized.
---

## Boundary

This workstream is the canonical home for the post-P0 catalyst-event product
vertical only. Recovery V2 remains completed evidence; BPC-JV remains finite
snapshot onboarding/reconstruction; draft BCI remains a separate federation
candidate. The initial authority tier is deterministic facts and context.
