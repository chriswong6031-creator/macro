---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d4-company-financial-bridge
model: fable
ended_because: complete
prs: [6123]
decisions: [DEC:D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT]
discoveries: []

mission: >
  D4 (Sol-authorized 2026-08-20, IRDM only): put the reviewed P00032
  government fact beside the canonical company-financial owner's latest
  usable IRDM truth in the existing dossier, with a lawful-comparability
  verdict that defaults closed. Display/context authority only. D5 not
  started.

state_before: >
  The IRDM company dossier carried Identity Atlas + award history (D2) and
  temporal truth (D3), but no company rail: the candidate's materiality
  block already recorded comparison_state not_comparable with reason
  exact_issuer_attributed_denominator_not_available, and no surface showed
  what Iridium reports through the canonical owner. event_workspace.v1 is
  AAPL-only by construction; the owner's closed per-ticker context API
  serves IRDM live.

changed:
  - path: templates/government-revenue-dossiers.js
    what: >
      New factory createGovernmentRevenueCompanyBridge (IRDM-only, atlas
      wiring idiom): GOVERNMENT FACT from the workspace P00032 event with
      the receipt selected by content_sha256 ==
      award_change.source_identity.content_sha256; COMPANY TRUTH from GET
      /api/company-intelligence/{ticker} (company_intelligence_context.v1,
      earnings_history/transcript-lineage fields only, score_overlay
      excluded, bounded 10s fetch timeout, fail-closed typed "Company
      packet unavailable", per-ticker success memo); COMPARISON as fixed
      closed-state copy (no ratio node on any input, zero arithmetic);
      RESEARCH QUESTION static bilingual watch copy. Site twin
      byte-identical.
  - path: templates/government_revenue.html.j2
    what: >
      Host section emitted only for ticker IRDM in
      renderCompanyCoverageInspector (the REACHABLE company render path —
      renderInspector's r.kind==='company' branch is dead code for real
      selections); bridgeUI wiring with workspaceEvents/workspaceComplete
      getters; hydration-aware loading-vs-unavailable distinction. +811
      baked bytes; fence unchanged at 303,104.
  - path: tests/test_government_revenue_company_bridge.py
    what: >
      27-test hostile suite (T1-T10 + review pins R2/R4/R5/R7/R9/R10/R12)
      driven by the committed fixture
      tests/fixtures/govrev_company_bridge/p00032_event.json and the REAL
      page helpers extracted from the template — zero moving-data reads.
  - path: .github/ci/legacy-jobs.yml
    what: >
      New MERGE-BINDING gate:code job govrev-company-bridge (pytest + node,
      fixture-only suite). The govrev family job unrun-government-revenue
      is if:false + gate:data (advisory data-health lane) and may not house
      law gates.
  - path: agentos/decisions/DEC-D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT.md
    what: Owner-preflight classification + static-closed comparison ruling.

verified:
  - claim: >
      Owner preflight: event_workspace.v1 is AAPL-only (single hardcoded
      producer scripts/refresh_event_workspaces.py, sole issuer builder
      apple_issuer()); the owner's context API serves IRDM live
      (available:true, generated_at 2026-08-20T06:52:58Z, latest_event
      cie_77ff210df9c064c3b2fe4aa1, FY2026 Q1, call 2026-04-23,
      claim_citations_pending true, anonymous 200).
    command: "scout census + curl GET https://www.mastermind-x.com/api/company-intelligence/IRDM (2026-08-20)"
  - claim: >
      Opus adversarial review (FAIL round) found 2 blockers + 4 majors —
      merge-gate darkness, eternal spinner, single-endpoint violation,
      award-snapshot receipt mismatch, first-paint slice, test vacuity —
      all repaired (R1-R13) with every executed probe pinned as a test; 27
      bridge tests + 130 combined targeted green; contract-delta 0;
      run_ci_pack validate clean; govrev-company-bridge confirmed in the
      gate=code set (122 jobs).
    command: "pytest tallies + run_ci_pack --validate-only + load_legacy_jobs(gate='code') probe, all quoted in PR #6123 body"
  - claim: >
      Pre-merge browser proof on the exact merged bytes (local bake, deep
      link ?mode=companies&item=company:IRDM): all four blocks render; the
      receipt href is the transactions receipt; company rail fail-closed
      typed unavailable with no spinner; comparison closed with no ratio;
      LMT dossier has NO bridge node and ZERO owner-API fetches; ZH clean
      (政府事实/拨款义务/延迟发现/2026年5月12日/公司数据包不可用/不可比/研究问题,
      zero 申报/证伪); no overflow 1280/768/375; bridge factory's only fetch
      is /api/company-intelligence/….
    command: "in-app browser JS probes on http://localhost:8931 (bake via build_site_only)"
  - claim: >
      Live after merge b5548ece927d: production checkout 6ca2f3529e5
      CONTAINS the merge; live government_revenue.html is 200 at 296,693
      bytes (byte-identical to the D4 bake) with companyBridge wiring —
      re-baked by the intraday govrev live lane, independent of render.yml;
      dossiers.js bytes at the prod checkout carry the factory; anonymous
      posture intact (module 401, bridge host hidden display:none with zero
      text — no misleading empty state, no spinner).
    command: "curl -w http/bytes + git merge-base --is-ancestor + git show 6ca2f3529e5:site/... + in-app browser on production"
  - claim: >
      CI on the PR head concluded green: fences + ci-authority success;
      ci.yml red once on an actions/checkout infra flake (early EOF /
      invalid index-pack / promisor fetch — tests never ran), rerun-failed
      → success. Merged on concluded checks; merge-queue-pilot X is
      red-by-design.
    command: "gh run view 32409011882 (failure log then rerun success)"

unverified:
  - "An operator-ENTITLED production browser session rendering both rails
    (module loads via cookie + live API packet in the company block) — the
    Chrome extension was not connected and credential entry is prohibited.
    Every input is individually live-proven (page bytes byte-identical to
    the browser-proved bake; module bytes at the prod checkout; owner API
    anonymous-200 with the real packet), so only the final entitled
    composition awaits an authenticated eyeball."
  - "The render.yml covering run 32420437089 (at the merge SHA) was still
    pending behind the single-label runner at session close — page BODIES
    are already live via the govrev live lane; the render only re-stamps
    ?v= hashes."

unresolved:
  - "The whole govrev test estate (builder/fence/UI/D2/D3 suites) rides
    unrun-government-revenue (if:false, gate:data) — advisory data-health
    only, NOT merge-binding. D4's suite escaped via a committed fixture +
    its own gate:code job; the family posture is a deliberate moving-data
    trade-off but D2/D3's law gates are as dark as D4's were. Candidate
    follow-up commission: fixture-freeze the law-critical D2/D3 families
    the same way."

next_actions:
  - "Sol: D4 acceptance review. D5 (program/mission/capability graph)
    remains unauthorized."
  - "Operator (optional): one entitled production eyeball of the IRDM
    dossier bridge (both rails + receipts/clocks visible)."

do_not_redo:
  - "Do not re-add a candidates.json fetch to the bridge — comparison is
    static-closed by DEC ruling; dynamic comparison state requires an
    owner-reviewed denominator-admission path in a future authorized wave."
  - "Do not render score_overlay-lineage fields on the company rail."
  - "Do not move the bridge suite back beside the family suites in
    unrun-government-revenue — it would silently leave the merge gate."
  - "Do not parse Earnings Wire HTML or copy company data under
    data/government_revenue/."

danger_areas:
  - "unrun-* jobs in legacy-jobs.yml are if:false + gate:data — a run: step
    added there satisfies contract-delta while never running on the merge
    gate. Check the OWNING JOB's gate before calling a suite wired."
  - "The dossiers module is tier-gated (anonymous 401): typeof checks make
    every factory fall back for anon — a factory must leave its host
    hidden/empty when absent, or anon pages show broken shells."
  - "renderInspector's r.kind==='company' branch is DEAD for real
    selections (all company paths route through
    renderCompanyCoverageInspector via selectRow) — but it still renders
    Atlas markup, parked one edit from resurrection. Wire company-inspector
    features into renderCompanyCoverageInspector."
  - "The govrev live lane re-bakes site/government_revenue.html intraday —
    page bodies can go live BEFORE render.yml concludes; verify live bytes
    against your bake, not against the render run's state."
---

# D4 — company financial truth bridge (close)

Case A on the v1 context plane: the canonical owner's closed per-ticker
API serves IRDM today, so the company rail consumes it read-only under the
owner's clocks; the richer event_workspace.v1 stays AAPL-only and D4 did
not fork or simulate it. No lawful denominator exists — comparison ships
closed (not_comparable, null ratio) and can only open through an
owner-reviewed denominator-admission path. The opus review earned its keep
again: the D4 suite would have shipped dark (gate:data holding pen) and
the receipt link pointed at the award snapshot instead of P00032's own
transaction receipt — both caught pre-merge and pinned as tests.
