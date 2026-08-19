---
workstream: WS:ALPHA-INTELLIGENCE-INTEGRATION
session: claude/alpha-intel-c0-adjudication
model: fable
ended_because: complete
mission: >
  Waves c0 AND c0g of the Alpha Intelligence Expansion (FABLE-00 seat, same
  session): c0 delta-checked PASS-0 against fresh origin/main, adjudicated the
  five Wave-0 censuses, and set the FABLE-A dispatch conditions; c0g (operator
  re-dispatch after the G0 returns landed) adjudicated the three-way G0 return
  set — US G0 #5955, CN-G0 #5943, and the #5822->#5953 rival US copy with its
  embedded non-seat c0g draft — plus a pasted PARTIAL academic return.
state_before: >
  PASS-0 merged (#5910) with pin 47aaa6036846; five censuses had returned and
  merged (A0 #5912, B0 #5911, D0 #5913, E0 #5914, F0 #5915) but none was
  adjudicated; G0 outstanding; #5894 and #5902 had merged since the pin,
  clearing two PASS-0 wait-conditions; FIF-1R3 (#5889) and FF-1P2 (#5898)
  freezes unchanged; #5924 had recut V4-B5 (B5A/B5B) and minted Radar W4.1.
changed:
  - path: research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md
    what: >
      c0 adjudication packet — delta since the PASS-0 pin; B0 accepted with
      perishability CLOSED on fresh receipts (no emergency capture clock
      anywhere); E0/D0/F0 accepted with named conditions on their K-waves;
      FABLE-A CONDITIONAL GO with a 9-point binding amendment rider (from an
      adversarial review that found one blocker + four majors in A0's
      recommendation); updated safe/wait lane table.
  - path: agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md
    what: >
      wave c0 marked done; wave c0g (G0 adjudication) added; landmines
      refreshed (#5894 occupation cleared, Radar/Prophet-Lab occupation added,
      A0 boring-baseline flip condition made binding); next_action updated.
  - path: agentos/decisions/DEC-ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH.md
    what: >
      new DEC — FABLE-A dispatches contract-first with the c0 §5.1 amendment
      rider; physical mesh store gated on an operator-decidable flip condition
      (named committed consumer over >=3 owner_stores); FIF leg fixture-only
      until Sol rules.
  - path: research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md
    what: >
      c0g seat packet — US G0 #5955 ACCEPTED canonical with six conditions
      (clock-direction correction, per-source-clock gap, FIF-7 overlap named,
      casebook candidates-only, supplement committed, B&T magnitude caveat);
      CN-G0 #5943 ACCEPTED (adapter delta sharpened to three identity-plane
      sites); venue ruling; #5953 rival copy non-canonical, preserved by
      citation, disposition requested; K4-G preconditions frozen in §6.
  - path: research/alpha_intelligence/censuses/G0_SUPPLEMENTARY_US_ACADEMIC_RETURN_AS_RECEIVED_2026-08-19.md
    what: >
      the Grok lane's pasted PARTIAL academic return committed verbatim as a
      supplementary receipt — PRIMARY-verified abstracts for ~15 papers #5955
      tags INFERRED, plus the SEC 8-K/10-Q/Reg G legal clock; provenance header
      sets tag-precedence rules.
  - path: agentos/decisions/DEC-ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL.md
    what: >
      new DEC — Earnings OS event truth is venue-neutral; no
      china_corporate_event.v1, no independent G lane; CN adapter is one
      Earnings-owner identity-plane wave post-E2 referencing Stock Identity.
  - path: agentos/discoveries/DSC-EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION.md
    what: >
      new DSC — the two-clock collapse is structural (generated_at derived from
      observed_at; both seeded with source_available_at from SEC
      acceptance_datetime); source_available_at is the CORRECT clock; frontier
      cannot be derived from lifecycle pairs; real gap = per-source clock
      projection (sources[] carry no clocks, SourceDocument defines them).
verified:
  - claim: worktree pinned to fresh origin/main at session start
    command: git fetch origin && git rev-list --count HEAD..origin/main
    result: "0 behind / 0 ahead at fe313751eeef"
  - claim: five census bundles are merged main-state
    command: git log --oneline -- research/evidence_mesh/ research/alpha_intelligence/censuses/B0/ research/economic_propagation/ research/path_survival/ research/opportunity_evidence/
    result: "#5912 / #5911 / #5913 / #5915 / #5914 merge commits present"
  - claim: P1 IBKR borrow capture is accruing (B0 could not verify)
    command: git ls-tree origin/main --name-only -- data/ibkr_borrow/daily/
    result: 9 dated parquets 2026-08-05..08-17; weekday gaps 08-11 and 08-14
  - claim: P2 sponsor ETF holdings capture is accruing at scale
    command: git ls-tree -r origin/main --name-only -- data/etf_holdings/ | wc -l
    result: 3,445 files
  - claim: P5 yfinance analyst storage is dated-append, not overwrite
    command: grep -n "concat\|Appends a row" collectors/yf_analyst.py
    result: concat at :305; append-per-snapshot_date contract at :408-431
  - claim: A0 §5's symbol-directory join branch is contract-forbidden
    command: grep -n "listing_sec_identity_binding_eligible" contracts/symbol_directory/symbol_directory_completion_receipt.v1.schema.json
    result: "const: false (reviewer receipt, line 195)"
  - claim: the agentos store validates with the three new/updated records
    command: python3 scripts/agentos.py validate
    result: exit 0 (run pre-PR; CI carries the authoritative copy)
  - claim: the two US G0 copies are different censuses, not a fork
    command: comm -12 on sorted-unique non-blank added lines per same-named file (opus audit, gh pr diff 5955 vs 5822)
    result: "shared lines 0/2/1/1/1 across five files; all sha256 pairs differ; the 2 'shared' clock-census lines are markdown separators"
  - claim: US G0's live-generation claims hold in production
    command: curl of public R2 manifest + workspace evt_cik0000320193_2026q3_results.json (opus audit)
    result: "HTTP 200; 22,437 B; sha256 dbd50e5c…81197 matches manifest; lifecycle triple-equality confirmed"
  - claim: the clock collapse is structural and source_available_at is the correct clock
    command: read event_workspace_build.py:150,449 + scripts/refresh_event_workspaces.py:352,362-363
    result: "generated_at derived from observed_at; both observed_at and source_available_at seeded from filing acceptance_datetime"
  - claim: CN-G0's 快报-unused finding holds
    command: git grep preliminary.parquet origin/main; git grep yjkb origin/main
    result: "writers only in collectors/china_preannounce.py; engine reads forecast.parquet only (china_special_situations.py:552)"
unverified:
  - claim: the five census bundles' row-level casebook citations say what the censuses claim
    what_would_verify: opening the ~24 winner-case files D0 cites and E0's 154 case files (deferred; aggregate counts verified)
  - claim: production VPS/R2 state matches the committed artifacts read here
    what_would_verify: VPS-side reads (sparse worktree; out of this session's scope)
unresolved:
  - "No commission files exist for the K3-E / K3-D contract waves ruled READY, nor for K4-G — operator/Sol author them; K4-G must carry the seat packet §6 preconditions verbatim."
  - "Sol rulings pending: FIF-1R3 (#5889) and FF-1P2 STOP (#5898) — unchanged freezes."
  - "FIF-7 two-owner overlap ('event workspace packet' / 'market reaction' in the FIF masterplan :1672-1685 vs Earnings G-lane routing) — named, parked at the K4-G commission gate; do not resolve silently."
  - "#5953 disposition request (drop or re-home its censuses/G0/ six + embedded C0G draft) — that lane responds; if it lands unchanged, the seat packet governs canonicity."
next_actions:
  - "Operator: dispatch FABLE-A with the c0 §5.1 rider appended verbatim."
  - "Next session (K1 adjudication): receive FABLE-A's K1 packet; check the rider was honored clause-by-clause before accepting any freeze."
  - "Watch #5955 and #5943 to merge (armed by the seat post-acceptance); the G0 content is main-state only after they land."
do_not_redo:
  - "Do not re-adjudicate the five Wave-0 censuses — c0 verdicts and conditions are in the c0 packet; delta-check open-PR/freeze state instead."
  - "Do not re-verify lane-B perishability — closed with git-tree receipts in c0 §3.1; the only live follow-ups are owner-routed (collector gap-hardening, ARK/ProShares ToS side quests)."
  - "Do not treat A0's recommendation as dispatch-ready without the §5.1 rider — its §5 join branch is contract-forbidden and its adoption inventory is incomplete (reviewer findings F1/F2)."
  - "Do not route holdability/path metrics through the Prophet Operator Lab — zero-authority projection surface (DEC:PROPHET-LAB-B5A-RECUT); that leak is named in c0 §4.3."
  - "Do not re-adjudicate the G0 returns — the c0g seat packet carries the verdicts; the #5953-embedded C0G_G0_ADJUDICATION is a superseded non-seat draft, never the record."
  - "Do not 'fix' source_available_at on event_workspace.v1 — it is the one correct clock; the derived fields are observed_at/generated_at (DSC:EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION)."
  - "Do not mint china_corporate_event.v1 or an independent G lane (DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL)."
danger_areas:
  - "Radar live-transport plane: #5929 (armed) and #5925 (unarmed) collide on engine/entry_radar/live_pack.py — Radar owner's matter; F-lane reads only."
  - "engine/altdata_models.py Quiver 13F kernel carries ReportPeriod look-ahead — routed to its owner; a K2-B builder must not grow or silently inherit it."
  - "F0's forward_rows_total=0 data-basis finding expires when #5929 lands and the Radar spool starts accruing — K4 re-reads it."
prs: [5933]
decisions:
  - DEC:ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH
  - DEC:ALPHA-INTEL-EARNINGS-EVENT-TRUTH-IS-VENUE-NEUTRAL
discoveries:
  - DSC:EVENT-WORKSPACE-CLOCKS-COLLAPSE-BY-CONSTRUCTION
---

# c0 + c0g session handoff

Cold-stranger path: read the c0 packet
(`research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md`) — the delta,
five census verdicts with K-wave conditions, the FABLE-A amendment rider, and
the lane table — then the c0g seat packet
(`research/alpha_intelligence/C0G_G0_SEAT_ADJUDICATION_2026-08-19.md`) — the
three-way G0 ruling, the venue DEC, the clock DSC, and the frozen K4-G
preconditions. PASS-0 remains the estate baseline; c0 supersedes its §5–§7 lane
rulings where they differ; c0g supersedes both on the G lane.
