---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/china-alpha-masterplan-2026-08-19
model: fable
ended_because: complete
mission: >
  FABLE-00 China Alpha Intelligence reconciliation (Sol final 8-turn synthesis,
  operator-delivered 2026-08-19): adjudicate the Wave-0 censuses for the China
  program, rewrite/supersede the #5822 draft into one canonical China
  masterplan on its own vehicle branch (landed as documented successor #5953
  after the branch's claude/* rename closed #5822), mint the China execution
  workstream, and emit the first builder commissions. REVISED the same day per
  Sol's freeze-review verdict (architecture APPROVED / freeze artifact
  REVISE): the session-executed rival US G0 bundle and non-seat c0g draft
  were withdrawn in favor of the seat adjudication (#5933; canonical #5955
  US / #5943 CN), the GROK-CN verdicts were adopted as binding freeze inputs,
  the completion law hardened (merge = BUILT_NOT_PROVEN), a dated capability
  ledger added, and the PR-0D commission authored. No builder code, no
  runtime change. Freeze effective at Sol's final review.
state_before: >
  Sol's final masterplan and the FABLE handoff pack existed only as
  operator-delivered files. PR #5822 sat as an open 1,284-line draft with a
  two-axis architecture predating PASS-0/c0. The estate c0 adjudication
  (#5933) was armed but merge-blocked on an inherited fleet-wide red
  (symbol_directory, healed on main by #5936/#5937). GROK-G0 had never been
  dispatched (Wave-0 at 5/6). No China execution workstream existed; the
  candidate plane persisted zero intel_interest anatomy; no institutional
  visit collector existed anywhere.
changed:
  - path: research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md
    what: >
      canonical China masterplan — Sol's synthesis as base, plus §0-bis
      FABLE-00 reconciliation record (nine adjudications) with the program
      completion law, §0-ter Sol freeze-review revision record (six blockers
      resolved; GROK-CN verdicts adopted as binding freeze inputs), verified
      repo pins in §1, §1.10 dated capability ledger, §8.1/§8.2/§8.3
      settled acquisition verdicts, §13 execution states with commission
      pointers and BUILT_NOT_PROVEN gates, §15 DNR key list with the CN-F
      lobe gate, §17 stop conditions MET pending Sol's final review.
  - path: research/china_alpha_intelligence/PRESERVED_ARCHAEOLOGY_FROM_2026-08-17_DRAFT.md
    what: >
      verbatim extracts of the superseded draft's surviving detail (capability
      ledger, US-parity map, exact Tushare tables, vertical lobes, vendor map,
      priority matrix, feature grammar, failure-state taxonomy, asymmetry
      patterns, evidence anchors) with a reading map into the canonical plan.
  - path: research/china_alpha_intelligence/commissions/PR-0B_v4_telemetry.md
    what: builder commission — persist full intel_interest anatomy into the candidate plane, single-compute invariant, ordering-invariance tests.
  - path: research/china_alpha_intelligence/commissions/RIGHTS-0_source_entitlement_audit.md
    what: researcher commission — per-family Tushare/non-Tushare rights registry, audit-first, P1 source verdict.
  - path: research/china_alpha_intelligence/commissions/P1_institutional_visit_tape.md
    what: >
      builder commission — visit collector (asia lane, failure-isolated) +
      PIT store + provisional actor ontology (raw string + ontology version)
      + coverage-start semantics + dossier block + failure states, NO score;
      gated on RIGHTS-0; merge = BUILT_NOT_PROVEN, done only on real
      asia-close receipt + production dossier desktop/mobile proof.
  - path: research/china_alpha_intelligence/commissions/PR-0D_china_identity_extension.md
    what: >
      builder commission — Data OS master + GMI bridge China resolution ONLY
      (§0-ter.6 boundary: never the Earnings event adapter, no
      china_corporate_event.v1, primary-source route only per the #5947
      resolver NO-BUY); coordinate with WS:STOCK-IDENTITY.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: >
      new China execution workstream (program china-system) with wave graph
      g0→pr0a→{pr0b,rights0,pr0d}→p1→…, landmines/do_not_redo carrying the
      adopted CN-wave no-buys and the completion law.
  - path: agentos/decisions/DEC-CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE.md
    what: >
      the architecture-freeze decision (nine adjudications, supersession
      mechanics, boundary list; answer records the Sol revision pass and the
      seat-adjudicated G0 authority).
  - path: research/alpha_intelligence/ (deletions)
    what: >
      WITHDRAWN in the revision pass — the six censuses/G0/ files and the
      non-seat C0G_G0_ADJUDICATION_2026-08-19.md this session had authored
      were deleted per the #5933 seat's disposition request; canonical G0 =
      #5955 (US) + #5943 (CN), governing record =
      C0G_G0_SEAT_ADJUDICATION_2026-08-19.md (#5933), which preserves this
      bundle's unique value by citation. NOTE: this PR does NOT change
      WS-ALPHA-INTELLIGENCE-INTEGRATION.md — the c0g closure there is
      #5933's change (an earlier draft of this handoff wrongly listed it).
verified:
  - claim: AgentOS store validates with the new records present
    command: python3 scripts/agentos.py validate
    result: exit 0, 0 errors (229+ records; pre-existing warnings only)
  - claim: the candidate plane persists no intel_interest anatomy today (PR-0B gap)
    command: read engine/china_prophet_shadow.py:53-98,359-474 (no intel keys) vs engine/china_intel_interest.py:323-338 (full anatomy) and engine/china_board_rank.py:471-505 (compact board subset)
    result: full anatomy computed and dropped; plane carries zero intel fields
  - claim: no institutional visit collector exists anywhere in the repo
    command: grep -rliE "diaoyan|机构调研|institution.*visit|inst_visit|research_visit" --include="*.py" engine/ scripts/ config/ collectors/
    result: zero collector hits (prose mention only in research/)
  - claim: five prior censuses are merged main-state at their per-domain homes
    command: git ls-tree origin/main -- research/evidence_mesh/ research/alpha_intelligence/censuses/B0/ research/economic_propagation/ research/opportunity_evidence/ research/path_survival/
    result: A0/B0/D0/E0/F0 bundles present (#5912/#5911/#5913/#5914/#5915)
  - claim: China collectors run only in the asia lane
    command: read .github/workflows/asia-close.yml:1-40 and .github/workflows/daily.yml:372,632-634
    result: daily.yml excludes group asia and resets stray data/china* writes
unverified:
  - claim: our Tushare account tier covers stk_surv/fund_portfolio/hm_list
    what_would_verify: operator confirmation of the privilege page + the CN-A vendor letter (deliberately not probed with the token; anns_d ruled NOT_NEEDED by #5945)
  - claim: production freshness of data/ parquets cited in the G0 census
    what_would_verify: git ls-tree origin/main -- data/<store> from a full checkout or a later session (sparse worktree here)
unresolved:
  - "P1 source selection: bound to the RIGHTS-0 verdict (Tushare stk_surv vs exchange/cninfo primary)."
  - "PR-0D sequencing with WS:STOCK-IDENTITY (China/HK not-in-master gap, ~25% GMI node resolution) — coordinate before touching identity surfaces."
  - "Estate-side FABLE-A dispatch is a separate operator action under DEC:ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH — not a China-lane dependency."
next_actions:
  - "GATE: Sol's final freeze review of the revised #5953 head — no spawn before it clears."
  - "Then spawn PR-0B builder from research/china_alpha_intelligence/commissions/PR-0B_v4_telemetry.md and RIGHTS-0 researcher from RIGHTS-0_source_entitlement_audit.md in parallel; PR-0D builder from PR-0D_china_identity_extension.md in parallel, coordinated with WS:STOCK-IDENTITY."
  - "After RIGHTS-0's P1 verdict: spawn P1 from research/china_alpha_intelligence/commissions/P1_institutional_visit_tape.md."
  - "Completion law on every build wave: merge = BUILT_NOT_PROVEN; flip to done only on the recorded production receipt."
do_not_redo:
  - "Do not re-run any Wave-0 census — all slots are returned and adjudicated (c0 #5933; G0 by the seat packet on #5933: canonical #5955 US + #5943 CN; this PR's rival bundle was withdrawn)."
  - "Do not resurrect this session's withdrawn G0 bundle or non-seat c0g draft — the seat packet preserves its unique value by citation and names its defects (degenerate frontier recipe, inflated verified-event count)."
  - "Do not re-derive the Tushare entitlement matrix — GROK-CN-A (#5945) delivered it; RIGHTS-0 consumes it and covers only the residual (non-Tushare ToS, primary-route resolver rights, P1 verdict)."
  - "Do not re-run the resolver bake-off (#5947 NO-BUY), the supply-chain diligence (#5951 / DEC:CN-NO-SUPPLY-CHAIN-SEAT-PURCHASE), or the sector-clock census (#5950 Bio+EV only) — adopted as binding freeze inputs (masterplan §0-ter.4)."
  - "Do not re-census the remaining GROK-CN surfaces (#5944 SOE demand map, #5946 EIA map, #5949 priors table) — frozen source inputs for R2/R3/L1 per masterplan §1.8/§1.10."
  - "Do not mint a second China masterplan, candidate store, grader, or identity plane — masterplan §15 + WS do_not_redo."
  - "Do not build a Mesh runtime for P1 — boring-baseline ruling stands."
  - "Do not cite CN limit-alpha W1–W3 results (DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT stop-ship)."
danger_areas:
  - "Serving firewall: any Prophet score/rank/lane/board/entry/tier reaching an Intelligence serving input is the named authority leak."
  - "asia-close is C0 market-critical — new collectors register in the asia group; daily.yml resets stray china writes."
  - "Sparse worktrees: never git add a data/ diff; a write into an omitted tree truncates the committed artifact."
  - "engine/company_intelligence/events.py EVENT_STATES is a closed enum — a G-wave frontier is a derived view; editing the enum trips authority_changed fleet law."
  - "Beat/miss verdicts are contract-forbidden without a licensed consensus basis (event_workspace.py:272-278) — no China or US reinterpretation state may mint one."
prs: [5822, 5953]
decisions:
  - DEC:CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE
---

# Handoff — China Alpha Intelligence, FABLE-00 reconciliation session

A cold session starts here: read `research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md`
§0-bis, §0-ter, §1.10 and §16, then the commission file for the wave you are
picking up. The masterplan is the single canonical architecture; the
preserved-archaeology file is detail, not authority (§1.10 is the current
capability ledger). Estate-side coordination lives in
`WS:ALPHA-INTELLIGENCE-INTEGRATION` (c0 + c0g seat packets, both on #5933).
The freeze is effective only at Sol's final review of the revised #5953 head.
