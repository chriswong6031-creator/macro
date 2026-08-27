---
key: DEFENSE-PROCUREMENT-V3
title: Defense Procurement & Industrial Base Intelligence OS V3
objective: >
  Freeze a financial-alpha defense architecture, then implement it as bounded
  waves D0R through D20 over the existing Government Revenue substrate. Done for
  D0R = current-state truth, driver taxonomy, historical casebook method,
  source/rights/PIT registry, graph/contract freeze, golden universe, real-data
  experience architecture, and exact D1-D4 handoffs exist; no production mutation.
status: awaiting_review
program: government-revenue-foresight
repos: [macro, terminal, mastermind]
owner: coo-fable
class: research
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - research/DEFENSE_PROCUREMENT_INTELLIGENCE_OS_V3_FINANCIAL_ALPHA_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md
  - research/DEFENSE_PROCUREMENT_D0R_FINANCIAL_ALPHA_RECONNAISSANCE_HANDOFF_2026-08-16.md
  - research/defense_intelligence/
  - engine/government_revenue/
  - app/government_revenue.py
  - scripts/build_government_revenue.py
  - scripts/build_government_revenue_candidates.py
  - templates/government_revenue.html.j2
  - templates/government-revenue-candidate-radar.js
  - templates/government-revenue-dossiers.js
  - collectors/dod_budget.py
  - collectors/dod_budget_live.py
  - contracts/government_revenue/
waves:
  - id: D0R
    title: Financial-alpha reconnaissance and architecture freeze
    status: done
    pr: [5814, 5819]
    next_action: >
      D0R accepted on #5819. Do not reopen Gate 5 as a D0R architecture gap.
      Historical corpus remains mandatory before any alpha promotion.
  - id: D1
    title: Production truth and signed-in product rescue
    status: done
    pr: [5836, 5885, 5882, 5856]
    depends_on: [D0R]
    next_action: >
      Done — Sol accepted D1 (D2 was authorized and executed on top of it).
      Radar 48 remains coverage truth, never new alpha.
  - id: D1.1
    title: Agency semantic recovery
    status: done
    pr: [5856]
    depends_on: [D1]
    next_action: >
      Done/accepted. D1.1F live-proven on #5856. P00032 renders Department of
      Defense / Defense Information Systems Agency from receipt-backed PIT
      evidence.
  - id: D2
    title: Defense Identity Atlas vertical slice
    status: done
    pr: [5932, 5997, 6004, 6008]
    depends_on: [D1.1]
    next_action: >
      Done — accepted after the D2P production close (2026-08-20 entitled-
      journey proof; see
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-20-d2p-production-close.md).
      The operational closure chain is FOUR PRs, not #5932 alone: #5932
      (defense21-v1 graph, digest 93171ba0e6f7…, + Identity Atlas
      artifact/product, two-round opus adversarial review), #5997
      (republish-proof heal: distinct-id census + ledger-issuance-frontier
      discriminator), #6004 (candidate-accounting closure: B2 non-issuance
      manifest refused on evidence; vintage-bound excuse self-retired), #6008
      (unissued candidates self-retire via nightly; B2 manifest unloadable).
      Five BWXT chains reviewed; MMACD85DT5D5 / PM7HBL2KDX46 / URJ3CAC3MSH8
      refused (see DEC:D2-BWXT-EXACT-ADMISSION-GE-STAYS-UNRESOLVED); GE and
      SPR stay not_asserted by design. Remaining mapping_needed pilots: GE.
      #5424 is superseded by defense21-v1 — do not merge, revive, or recut.
      Graph republish law: DSC:GRAPH-REPUBLISH-RETIMES-EVERY-CANDIDATE-CLOCK.
      Reliability follow-up (NOT a D3 prerequisite): the publisher-vintage
      lag has no alarm — nothing notices a publisher that stops firing
      (DSC:GOVREV-PUBLISHER-VINTAGE-LAG-IS-THE-ONLY-TRACE).
  - id: D3
    title: Temporal event v3 and Change Tape
    status: done
    pr: [6048, 6059]
    depends_on: [D2]
    next_action: >
      Done — Sol authorized 2026-08-20 and the bounded charter shipped the
      same day: typed rail failure_state (source_unavailable /
      projection_missing) emitted by the workspace read-model, dual-clock
      tape rows + Late-discovery chip, inspector Clocks block with the
      NAMED-NULL source-publication row, receipt-bound before/after +
      successor line from prior_source_identity, budget mode's eternal
      "loading" retired. Additive only — event contract stays v2
      (DEC:D3-TEMPORAL-V3-IS-ADDITIVE); frozen spec
      research/defense_intelligence/DEFENSE_D3_TEMPORAL_CONTRACT_AND_CHANGE_TAPE_SPEC.md.
      Opus adversarial review found a real blocker (the first cut destroyed
      the already-working module PROJECTION_MISSING verdict) — repaired same
      PR chain: the real module's HTTP-receipt status is authoritative, the
      typed fallback applies only when no module exists. #6059 fitted the
      page under a ratcheted 296 KiB raw-byte budget after the D3 markup
      left 65 bytes of headroom. All four D3 families production-proven
      (browser proof 2026-08-20). ACCEPTED by Sol 2026-08-20 (D4 authorized
      on the D3 close).
  - id: D4
    title: Company financial truth bridge
    status: done
    pr: [6123, 6173, 6192]
    depends_on: [D3]
    next_action: >
      Done — Sol accepted 2026-08-21. Shipped under Sol's IRDM-only charter
      in #6123 and provenance-hardened in #6173. D4P entitled production
      proof CLOSED 2026-08-21 on the real signed-in route
      government_revenue.html?mode=companies&item=company:IRDM. Production
      rendered GOVERNMENT FACT P00032 for exactly $18,416,666.66, effective
      2026-05-12, first known 2026-08-12, late discovery. The rendered
      official-receipt target was selected by exact
      content_sha256=2a07ba19681a3c9d07f69b3316850b4646db48a8075d2ea8375755e112d02bab,
      byte-equal to award_change.source_identity.content_sha256; the decoy
      award receipt carried a different sha. One actual authenticated GET
      /api/company-intelligence/IRDM completed 200 (no D4 fetch storm and no
      D4 console/request error), and COMPANY TRUTH rendered the successful
      packet state, never Company packet unavailable. Live owner packet:
      company_intelligence_context.v1, generated_at
      2026-08-21T06:53:16Z, latest_event
      cie_77ff210df9c064c3b2fe4aa1, FY2026 Q1 / call 2026-04-23. Live
      procurement workspace: government_procurement_workspace.v2,
      generated_at 2026-08-21T06:52:47.804099+00:00; P00032 event
      govws-a6c70850a9cbdce9fa3e7f3b. The first production pass exposed one
      real D4 defect: the rendered source-status line leaked metadata-only
      score_overlay lineage. #6192 removed that forbidden lineage at the
      rendering boundary, pinned it with a captured failing regression, and
      merged concluded-green as 7b6e5d126e7a; public-render run 32482669089
      completed green and production /api/health reported checkout
      7b6e5d126e7. Post-deploy proof has zero rendered score_overlay lineage;
      COMPARISON remains not_comparable, with zero denominator-value nodes
      and zero ratio nodes. Responsive proof: 1280x900 EN desktop inspector
      in-bounds with no horizontal overflow; 768x1024 EN mobile sheet
      in-bounds with no horizontal overflow; 375x812 ZH mobile sheet
      localized (政府事实 / 公司披露 / 不可比) and in-bounds with no horizontal
      overflow. LMT negative: no D4 bridge host and zero
      /api/company-intelligence/LMT fetches. Anonymous negative: D4 module
      and workspace JSON each 401 authentication_required/locked; page 200
      exposes one hidden empty bridge host only. Return to Sol for final D4
      acceptance. D5 remains unauthorized and unstarted.
  - id: D5R
    title: Program/mission/capability/product graph architecture freeze (research only)
    status: done
    depends_on: [D4]
    next_action: >
      DONE — Sol ACCEPTED D5R 2026-08-23 (accepted chain = #6209 + #6219 +
      #6247; authorization receipt = macro PR #6247 comment 5384728488).
      D5R core architecture merged on #6209 and PASSED Sol review (D5R.1
      six-repair consistency close merged on #6219). D5R.2 was the FINAL
      CONTRACT-REPRESENTABILITY SEAL (Sol 2026-08-22): seventeen-key
      top-level skeleton with reference JSON, program_capability_links,
      program_event_links (exact event-identity+hash pointer; census at
      D5R.2 time — NO Virginia Block VI v2 event existed on main 7e00f874;
      historical fact, re-censused at D5 start),
      review_coverage with the four-state derivation law, milestone
      date/window XOR preimage, logical-id + revision law, frozen dossier
      bundle + five-key program_link shapes, fixtures A-I with computed
      sha12 ids, adversarial representability review to YES. Owner
      adjudication and Virginia pilot remain frozen — do not reopen.
      Handoffs:
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-22-d5r1-docs-consistency.md,
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-22-d5r2-representability-seal.md.
  - id: D5
    title: Program, mission, capability, and product graph (implementation)
    status: done
    depends_on: [D5R]
    next_action: >
      CLOSED FOR PROGRAM SEQUENCING (Chairman amendment 2026-08-24; Sol
      ruling macro PR #6355 comment 5395051048). Capability remains
      BUILT_NOT_PROVEN: the entitled live-route walkthrough (D5P) never
      occurred and is DEFERRED / NONBLOCKING by explicit Chairman
      direction — a sequencing waiver, NOT a proof upgrade. Do not
      relabel PROVEN_LIVE; do not fabricate a browser receipt. The prior
      clause making authenticated D5P the next prerequisite is superseded
      AS A SEQUENCING GATE ONLY; the evidence gap itself remains durable,
      and D5P should still be executed when an authenticated browser
      session exists. Implementation is merged: full vertical on PR 6312
      (merge 57ab8b9130b0) — frozen contracts, program_ontology.py
      loader + derivations, propose/curate admission with evidence +
      conflict/override lifecycles, REAL Virginia pilot admitted (graph
      program-ontology:reviewed:2026-08-23:virginia-pilot, 14 admitted /
      1 rejected / 6 coverage rows, all evidence byte-receipted),
      program_dossier composer (gpd1-dcacffc7799b8448285bc19e) + site
      twins on BOTH build paths, workspace program_link (IRDM P00032
      derives the exact reviewed_none hostile-null shape), mode=programs
      surface EN/ZH within the 296 KiB ratchet, T1-T17 gate-code battery
      (181 passed), opus adversarial review repaired. Non-browser
      post-merge receipts hold: /api/health restarted at the merge SHA,
      covering render run 32637298811 success, VPS-served twins
      byte-identical to committed canonical, anonymous negative (both
      twins 401, locked treatment, zero Virginia leakage), local
      1440/820/390 EN + ZH crops committed. D5P blocker context:
      claude-in-chrome list_connected_browsers = [] on 2026-08-23 twice
      and 2026-08-24 twice; credential entry is prohibited, proof is
      never simulated. Handoff:
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-23-d5-implementation.md.
  - id: D6-A
    title: DoD P-1/R-1 budget rail activation (official source expansion, first rail)
    status: done
    depends_on: [D5]
    next_action: >
      Sol-authorized 2026-08-24 (macro PR #6355 comment 5395051048) under
      the Chairman sequencing amendment. Activate the EXISTING budget
      plane — no new budget system: official Comptroller FY2027 P-1/R-1
      acquisition → existing canonical R2 object store
      (content-addressed, readback-proven) → receipt-bound deterministic
      extraction → append-only source triad → government_budget_program_graph.v1
      → existing Budget & Programs API/UI consumer → production proof.
      Frozen design:
      research/defense_intelligence/DEFENSE_D6A_BUDGET_RAIL_DESIGN_2026-08-24.md.
      Source census 2026-08-24: the Comptroller host MIGRATED —
      comptroller.defense.gov now 403s (Akamai, no redirect);
      comptroller.war.gov is the live official host (already
      allowlisted); current cycle is the FY2027 President's Budget
      (FY2027_p1.pdf sha256 b8d5248257590856ee33ddb1b401ec2efcdfea219c05b5bc8ea1068d9000d0a6,
      FY2027_r1.pdf sha256 1aa8846edb69d4c3a54e03b383b0cabb77f93433162b8139ab8cbb55bcc7882a).
      Semantic firewall unchanged (request ≠ appropriation ≠ obligation ≠
      revenue); authority stays display/evidence-only; D5 v1
      budget_program_keys stays const []. DELIVERED 2026-08-24 on the
      carrier PR #6377 chain (+ dispatch lane #6378 merged): real runner
      acquisition run 32764547804 (canary sha256s byte-identical to the
      pinned census, R2 content-addressed write + strict readback proven),
      committed triad 94ab73114336 (2 receipts / 2,172 lines, generation
      dod-budget-401e0479c00c449c3b4bd7e0), graph builds+validates locally
      (grbg1-125cd95cc0e78c5f459c1ad2, 2,143 programs), opus adversarial
      review FAIL→repaired (e0095c1299f1; component-leak + E-7 blockers
      fixed with mutation-proven tests). Carrier PR #6377 MERGED
      2026-08-24T23:10:48Z as 2cfc5c73bd09 (head 49b3eb82c29b, CI runs
      32769121453 + 32784681614 SUCCESS). PRODUCTION PROOF COMPLETE
      2026-08-25T00:29Z: government-revenue-live run 32788159575 SUCCESS
      published the graph twins in commit da305fa5a5e2 (descendant of the
      merge; both twins sha256 a889ca79b967…, content_id
      grbg1-125cd95cc0e78c5f459c1ad2, 2,143 programs / 2,172 lines /
      2,172 edges); /api/health commit=2cfc5c73bd0 checkout=6af1ccd17c0
      (descendant of da305fa5a5e2); in-process production handlers served
      budget-programs total 2143 and both canaries (P-1 Virginia line 6
      FY27 disc/total 8,402,316,000 qty FY25 1/FY26 2/FY27-total 2; R-1
      0604558N New Design SSN FY27 237,103,000, no invented quantities)
      byte-consistent with the committed receipt-bound triad rows;
      Caddy-served /opt/macro/site.served/government-revenue-data/
      budget-program.json sha-identical to the canonical generation;
      anonymous probes all locked (API 401 missing bearer token; site
      twin 401 locked:true). No authenticated-browser walkthrough
      performed or required (Chairman sequencing amendment). D6-A =
      done / SOL ACCEPTED / PROVEN_LIVE (2026-08-25, macro #6385 comment
      5404403124, protected Sol Skillpack
      Mastermind@4d323d03e4151449a4b76abfdfefca1d56825fde). Unresolved
      rulings in that acceptance: (1) parser-generation retraction is a
      BINDING PRECONDITION before any parser-version bump — no future
      parser generation ships until generation scoping/tombstones are
      frozen; (2) FY2026 sub-cells stay unrepresented — no enum widening
      authorized; (3) E-7 all-null RATIFIED (computed implicit zero stays
      forbidden); (4) NSBDF zero-numbered-line partitions accepted as a
      named coverage/grain gap, verification-only. Handoff:
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-24-d6a-budget-rail.md.
  - id: D6-B0
    title: FMS congressional-notification source migration + stage/contract architecture freeze
    status: done
    depends_on: [D6-A]
    next_action: >
      Sol-authorized 2026-08-25 in the D6-A acceptance ruling (macro
      #6385 comment 5404403124): research/source-architecture wave ONLY.
      DELIVERED 2026-08-25 (PR #6404, merge accc1a3a353f, final head
      ab846bcbae83, CI 32875040030 success); ACCEPTED BY SOL 2026-08-25
      (macro #6404 comment 5416302430 — the durable GitHub acceptance
      receipt; Sol's contents-API write was 403-refused, the comment IS
      the record). The FREEZE
      (research/defense_intelligence/DEFENSE_D6B_FMS_SOURCE_AND_STAGE_ARCHITECTURE_FREEZE_2026-08-25.md)
      closes every commissioned decision: source boundary (State
      PM-Bureau current surface for cases notified ≥2026-02-26 per EO
      14383, both boundary statements receipted verbatim; DSCA
      landing+Library history; FR as supplementary certification record
      — 8 sha256-receipted census fetches, transport matrix proven:
      state.gov CLI-200-deterministic, dsca.mil/media.defense.gov CLI-403
      browser-only); identity = fms:transmittal:<yy-nn> with frozen
      label-detection grammar, deterministic URL-path fallback, and
      conflicted mis-key guard; SAMM-grounded six-stage namespace with
      v1 proving ONLY congressional_notification and time NEVER
      advancing stage; estimated_notification_value amount law with
      cross-case aggregation forbidden; four-clock law (State-era
      notification date null unless FR join); append-only correction law
      grounded first-party (State edits posts in place — modified_time
      5 months post-publication; DSCA Library preserves CNVn correction
      versions); canonical owner = GovRev-owned FMS rail
      (DEC:FMS-CANONICAL-OWNER-IS-GOVREV-FMS-RAIL — event.v2 rejected on
      identity-seed evidence, its event_id seed requires award_key);
      consumer = ninth bounded fms mode on government_revenue.html
      (28,890 B measured headroom under the 303,104 fence, ≤8,192 B
      shell delta); two-plane failure states mapped to canonical
      spellings; golden canaries 26-13 (DSCA Saudi PAC-3 $9.0B) + 26-27
      (State Sweden HIMARS $930M) + hostile stage-hold with zero
      review-period arithmetic; fourteen merge-binding kill tests;
      real-data reference composition. Opus adversarial review FAILed
      the draft (5 blockers) — all repaired in c2cd79f96d3e before Sol.
      Five unresolveds RULED BY SOL in the acceptance (comment
      5416302430): U1 CLOSED/NONBLOCKING (C5.7 re-read first-party —
      review-period expiry is permission to offer an LOA, never
      evidence one exists; v1 computes/stores/renders ZERO
      review-period arithmetic; current C5.7 byte/SHA receipt required
      as build evidence before implementation mutation); U2 PILOT ONLY
      (full current State surface + exactly DSCA 26-13; NO bulk DSCA
      backfill in D6-B; coverage metadata must disclose pilot-only
      history); U3 FR JOIN REQUIRED IN V1 (exact-transmittal
      supplementary join; FR never mints/advances a case; 26-27
      official_notification_date = 2026-03-10 from FR 2026-07237 / 91
      FR 19115 on successful join; missing FR ⇒ null, never inferred);
      U4 BOUNDARY SWEEP = MERGE GATE (2026-02-06→2026-02-26 inclusive,
      independent official 36(b)(1) denominator, classifications
      dsca_only/state_only/both/absent_from_both; absent_from_both ⇒
      HOLD-FOR-SOL); U5 EN/ZH PRODUCTION VOCABULARY FROZEN in the
      acceptance table (typography may change, meaning may not). D6-B
      implementation AUTHORIZED by the same comment. D6-C+ and D7+
      remain UNAUTHORIZED. D5 remains BUILT_NOT_PROVEN (D5P deferred,
      nonblocking; never relabel).
  - id: D6-B
    title: FMS real vertical — official-union acquisition, immutable observations, government_fms_case.v1, ninth fms mode, production proof
    status: done
    depends_on: [D6-B0]
    claim: claude/d6b1-fms-coverage-vertical-20260825 (Fable session, D6-B1 continuation claimed 2026-08-25; carrier is a ~/.claude-recovery clone because the local primary clone's git object reads are kernel-blocked by iCloud-evicted pack files)
    next_action: >
      D6-B1 DONE + PRODUCTION-PROVEN (2026-08-26). Carriers #6447
      (merged b9c6dd775f2a), #6454 (denominator heal + defense-rail-laws
      merge-gate repair, merged bff1e60f1ffd), #6478 (§11c State staged
      replay + country fall-through, merged 98f8c389dbc8). Live: graph
      d90d63c782 (66 cases, 57/57 denominator, 9 web-only State-frontier
      cases), publish 5d9628af92c2, served twins byte-identical, VPS
      in-process canaries 26-13/26-27/26-23 + anonymous 401 + zero
      event.v2 rows, EN/ZH desktop+mobile rendered. Full receipts:
      agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-26-d6b1-fms-vertical.md.
      Sol return posted on #6447. D6-C+ / D7+ UNAUTHORIZED. The
      superseded historical text follows for context ONLY:
      (historical) D6-B1 coverage-aware continuation 2026-08-25. The U4
      HOLD was RELEASED by the D6-B1 continuation commission (Chairman
      channel, in-session relay 2026-08-25; full text preserved in the
      D6-B1 continuation handoff): the U4 discovery is ACCEPTED —
      State+DSCA web surfaces are non-exhaustive — and the old
      web-surface population assumption is REPLACED by the frozen
      official-union coverage law. Scope 2026-01-01→claim-time. Build:
      FR bounded denominator/recovery + State current presentation
      observations + DSCA historical observations → transmittal-number
      dedupe → canonical GovRev FMS records → explicit source/coverage
      manifest → existing ninth fms mode → production proof. Under
      D6-B1, FR may RECOVER (mint) a case that is absent from both web
      surfaces — hostile case: 26-23 Jordan must be canonically present
      despite State/DSCA web absence; 26-28 Japan must not disappear
      because the State corpus omits it; 26-27 Sweden stays the
      positive web case. All B0 laws preserved: stage authority stops
      at congressional_notification; review-period expiry advances
      nothing; estimated_notification_value never award/backlog/
      revenue/cash; contractor prose mints no issuer identity; system
      similarity mints no D5 link; append-only corrections; no
      award_change abuse; no new general event store. New mandatory
      hostile cases: cross-family duplicate → one transmittal; FR
      publication lag cannot rewrite congressional-delivery time;
      missing web page never VALID_EMPTY; zero official denominator
      reconciliation cannot pass publication silently. Prior U4-hold
      evidence stands (fms_cutover_sweep_2026-08-25.json +
      fms_u4_fr_denominator_2026-08-25.json; step-2 re-receipts incl.
      SAMM C5.7 sha b98a113875f4). Stop after the FMS vertical is
      production-proven and return to Sol. D6-C+ and D7+ remain
      UNAUTHORIZED. D5 unchanged (BUILT_NOT_PROVEN).
landmines:
  - "Live page is government_revenue.html (underscore). government-revenue.html 404s."
  - "Access (site_full / 401 locked) is independent of epistemics (display/context_only). Do not conflate them."
  - "Reviewed recipient graph on HEAD is defense21-v1 as of #5932 (defense19 rows byte-preserved). #5424 defense20-v1 is CLOSED/superseded by defense21-v1 — do not merge, revive, or recut it (Sol, D4 charter 2026-08-20)."
  - "government-revenue-live can build-and-prove a projection and still fail to publish; prior live projection stays authoritative until commit complete evidence projection lands (run 32112383533 did not publish; run 32177051815 did)."
  - "Radar 48 is the coherent published queue, not 26 new awards. Ledger line_count is append-only audit and is not required to equal Radar."
  - "Session worktrees are sparse by default. Never write into omitted data/ — that truncates the committed artifact."
  - "DNR:LAW-REVIEWED-MANIFEST-CENSUS — a reviewed recipient graph cannot re-time itself."
  - "SPR is not a live issuer (Boeing close 2025-12-08; absent from Stock Identity universe)."
  - "government_revenue.html has a ratcheted RAW_HTML_BUDGET_BYTES fence (296 KiB since #6059). Template growth ships INLINE in the page — bake locally (scripts/build_government_revenue._write_site_projection) before merging template edits, or the shared render lane fails at the govrev step. D3's first cut left 65 bytes of headroom."
  - "The real createGovernmentRevenueBudget module EXISTS in government-revenue-dossiers.js (BSD grep hides it — use grep -a). Its HTTP-receipt status is authoritative; the typed freshness.budget fallback applies only when no module loaded."
do_not_redo:
  - "Do not start original D0. V2/D0 remain historical records only."
  - "Do not implement collectors, schemas, UI, Neural Web, or Prophet members in D0R."
  - "Do not create a second SEC, transcript, estimate, price, options, theme, identity, tenant, Neural Web, or Prophet plane."
  - "Do not treat GovTribe/GovCon capture parity as the product north star."
  - "Do not grant rank, gate, size, entry, or execution authority."
  - "Do not treat SPR as a live golden ticker."
  - "Do not invent 60 VERIFIED_CASE primaries."
  - "Do not merge, revive, or recut #5424 — superseded by defense21-v1 (#5932). Do not start D3 until Sol authorizes it."
  - "Do not rewrite collector awarding_agency hashes to flatten nested USAspending objects."
  - "Do not assert Candidate Radar must equal historical 22. Prove cookie = bearer = UI for the live content_id."
  - "Do not hand-advance the candidate ledger. Do not change recipient mappings to make counts nicer."
  - "Do not re-baseline. Do not revive an et_gate mutex."
decisions:
  - DEC:D5-OWNER-IS-GOVREV-ONTOLOGY-PLUS-COMPOSED-DOSSIER
  - DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN
  - DEC:D0R-RED-TEAM-ADJUDICATION-2026-08-17
  - DEC:D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
  - DEC:D11F-PIT-SAFE-AGENCY-FALLBACK
  - DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE
  - DEC:GOVREV-CANDIDATE-PROOF-GATE-ARMED
  - DEC:GOVREV-EVENT-IDENTITY-KEEPS-THE-KNOWN-AT-FOLD
  - DEC:GOVREV-CANDIDATE-LEDGER-STAYS-APPEND-ONLY
discoveries:
  - DSC:DOD-COMPTROLLER-HOST-MIGRATED-TO-WAR-GOV
  - DSC:GOVREV-COMPACT-TEASER-IS-THE-LIVE-DEFAULT
  - DSC:GOVREV-MAY-ACTION-AUGUST-KNOWN-AT
  - DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
  - DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS
  - DSC:CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES
  - DSC:GOVREV-CANDIDATE-RADAR-STAYS-LOCKED-AFTER-SITE-FULL-200
  - DSC:GOVREV-AGENCY-STRINGIFY-IS-COLLECTOR-THEN-ACTION-OMIT
next_action: >
  D6-B is DONE and PRODUCTION-PROVEN (2026-08-26) under the D6-B1
  coverage-aware continuation — see the D6-B wave entry and the
  2026-08-26 d6b1-fms-vertical handoff for the receipt packet; awaiting
  Sol's acceptance of the return on #6447. D6-C+ / D7+ remain
  UNAUTHORIZED. (historical) The U4 hold was released — the U4 discovery is accepted
  and the population law is now the official union (FR bounded
  denominator/recovery + State current + DSCA historical observations,
  transmittal dedupe, explicit source/coverage manifest), scope
  2026-01-01→claim-time. See the D6-B wave entry for the full D6-B1
  law. Original Sol authorization macro #6404 comment 5416302430;
  U4-hold evidence research/defense_intelligence/evidence/
  fms_cutover_sweep_2026-08-25.json. Continuation claimed by
  claude/d6b1-fms-coverage-vertical-20260825. D6-A is done / Sol-accepted /
  PROVEN_LIVE (#6385 comment 5404403124). D6-B0 architecture freeze is
  done / Sol-accepted (#6404 comment 5416302430; U1–U5 all ruled — see
  the D6-B0 wave entry). D6-C+, D7+, GAO, DOT&E, IG and every later
  defense rail remain UNAUTHORIZED. D5 is CLOSED FOR PROGRAM
  SEQUENCING (Chairman amendment 2026-08-24; Sol ruling macro PR #6355
  comment 5395051048): capability remains BUILT_NOT_PROVEN, the
  authenticated D5P walkthrough is DEFERRED / NONBLOCKING, and it must
  never be relabeled PROVEN_LIVE without a real entitled browser
  proof. #5424 stays closed/superseded by defense21-v1.
  Publisher-vintage alarm and fixture-freezing the D2/D3 law suites out of
  the unrun-government-revenue holding pen remain separate follow-ups — do
  not fold them into the D5R close.
---

## Context

V3 architecture and the D0R handoff merged in #5803 (`455284b7beae`). D0R
closed on #5819 (`0d10acdd`) and was accepted; Gate 5 stays honest-labeled
(6 VERIFIED_CASE + 61 RESEARCH_CANDIDATE) and is not alpha validation.
D1 entitled-desk rescue merged as #5836. D1 closure on main: #5885 append-only
stale-base fence (`694c081975bf`), #5882 `GOVREV_CANDIDATE_PROOF_FATAL=1`
(`120f77a7e8e4`), #5856 PIT-safe receipt-strict agency (`19b009fceca6`).
Live run 32177051815 on `19b009fceca6` built, proved, and published.
Canonical D1 contract:
`research/defense_intelligence/DEFENSE_D1_PRODUCTION_TRUTH_AND_PRODUCT_RESCUE_HANDOFF.md`.

D2 closed operationally on #5932 + #5997 + #6004 + #6008 and was
production-proven 2026-08-20 (D2P): production checkout `f69f224c972` serves
graph `recipient-graph:reviewed:2026-08-19:defense21-v1` (digest
`93171ba0e6f7286de02e0918ef85be7db80df3f6b7fd8eb3d47e7e8e4adfa843`), atlas
`gria1-4eeaa88c8cbabfaa800fc67d` (graph_status ready), bundle
`grw2-a0f56dbca09da2a4d0363ca1`, candidate queue
`grcq1-3ff9ecc9633f3d667840f43f` (62), mapping backlog 21; candidate
accounting 124 emitted lines / 70 distinct ids / 8 quarantined (2026-08-10
manifest) / 62 queued / 0 unaccounted. P00032 stays DoD / DISA, obligation
18416666.66, effective 2026-05-12, known_at 2026-08-12, late discovery, IRDM.
Proof record:
`agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-20-d2p-production-close.md`.
