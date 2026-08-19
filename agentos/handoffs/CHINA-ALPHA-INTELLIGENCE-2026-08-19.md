---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/china-alpha-masterplan-2026-08-19
model: fable
ended_because: complete
mission: >
  FABLE-00 China Alpha Intelligence reconciliation (Sol final 8-turn synthesis,
  operator-delivered 2026-08-19): complete the missing GROK-G0 census,
  adjudicate all six Wave-0 censuses for the China program, rewrite/supersede
  the #5822 draft into one canonical China masterplan on its own vehicle
  branch (landed as documented successor #5953 after the branch's claude/*
  rename closed #5822), mint the China execution workstream, and emit the
  first builder commissions. No builder code, no runtime change.
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
      FABLE-00 reconciliation record (nine adjudications), verified repo pins
      in §1 (board/ruler/candidate-plane/estate state), §8.1 Tushare audit
      state, §13 execution states with commission pointers, §15 DNR key list,
      §17 stop conditions marked MET.
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
    what: builder commission — visit collector (asia lane) + PIT store + actor resolution + dossier block + failure states, NO score; gated on RIGHTS-0.
  - path: research/alpha_intelligence/censuses/G0/
    what: >
      six GROK-G0 census files, US/estate-scoped (event clock + contract
      census, casebook, frontier spec draft, reaction geometry input matrix,
      academic review, open questions — return packet renamed
      G0_OPEN_QUESTIONS_US_ESTATE.md to avoid the add/add collision with
      PR #5943's China-scoped G0 bundle in the same directory). Wave-0 now
      6/6, the G0 slot double-covered by two complementary returns.
  - path: research/alpha_intelligence/C0G_G0_ADJUDICATION_2026-08-19.md
    what: >
      c0g adjudication — both G0 returns accepted (this PR's US/estate bundle
      + #5943's China-scoped bundle, ruled complementary in §2-bis); frontier
      view ruling; estate wave c0g closed.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: new China execution workstream (program china-system) with wave graph g0→pr0a→{pr0b,rights0}→p1→… and landmines/do_not_redo.
  - path: agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md
    what: wave c0g marked done (G0 returned + adjudicated); artifacts and next_action updated.
  - path: agentos/decisions/DEC-CHINA-ALPHA-INTELLIGENCE-ARCHITECTURE-FREEZE.md
    what: the architecture-freeze decision (nine adjudications, supersession mechanics, boundary list).
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
  - claim: casebook INFERRED rows' price magnitudes (18 of 48 rows are class-demonstration only)
    what_would_verify: repo-native event replay against price stores once the Earnings owner commissions a G-wave casebook rebuild
  - claim: our Tushare account tier covers stk_surv/fund_portfolio/anns_d/hm_list
    what_would_verify: RIGHTS-0 audit + operator confirmation of the account plan (deliberately not probed with the token)
  - claim: production freshness of data/ parquets cited in the G0 census
    what_would_verify: git ls-tree origin/main -- data/<store> from a full checkout or a later session (sparse worktree here)
unresolved:
  - "P1 source selection: bound to the RIGHTS-0 verdict (Tushare stk_surv vs exchange/cninfo primary)."
  - "PR-0D sequencing with WS:STOCK-IDENTITY (China/HK not-in-master gap, ~25% GMI node resolution) — coordinate before touching identity surfaces."
  - "Estate-side FABLE-A dispatch is a separate operator action under DEC:ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH — not a China-lane dependency."
next_actions:
  - "Spawn PR-0B builder from research/china_alpha_intelligence/commissions/PR-0B_v4_telemetry.md (parallel-safe now)."
  - "Spawn RIGHTS-0 researcher from research/china_alpha_intelligence/commissions/RIGHTS-0_source_entitlement_audit.md (parallel-safe now)."
  - "After RIGHTS-0's P1 verdict: spawn P1 from research/china_alpha_intelligence/commissions/P1_institutional_visit_tape.md."
  - "PR-0D (China identity extension) may run in parallel, coordinated with WS:STOCK-IDENTITY."
do_not_redo:
  - "Do not re-run any Wave-0 census — all six are returned and adjudicated (c0 #5933 + c0g this PR; the G0 slot has TWO complementary returns)."
  - "Do not re-derive the Tushare entitlement matrix — GROK-CN-A (#5945) delivered it; RIGHTS-0 consumes it and covers only the residual (non-Tushare ToS, resolver rights, P1 verdict)."
  - "Do not re-census the GROK-CN wave surfaces (#5943-#5951: China G0, Tushare rights, resolver bake-off, SOE demand map, EIA map, supply-chain diligence, sector clocks, priors table) — route each to its consuming wave boundary per masterplan §1.8."
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
§0-bis and §16, then the commission file for the wave you are picking up. The
masterplan is the single canonical architecture; the preserved-archaeology file
is detail, not authority. Estate-side coordination lives in
`WS:ALPHA-INTELLIGENCE-INTEGRATION` (c0 packet #5933 + c0g packet this PR).
