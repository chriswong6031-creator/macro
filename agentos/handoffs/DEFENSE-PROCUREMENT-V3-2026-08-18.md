---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/defense-d1-recovery-proof
model: local
ended_because: complete
prs: []
decisions:
  - DEC:D0R-RED-TEAM-ADJUDICATION-2026-08-17
discoveries:
  - DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS
  - DSC:CANDIDATE-ID-RACE-BETWEEN-GOVREV-LANES
  - DSC:GOVREV-COOKIE-JSON-AND-BEARER-API-ARE-TWO-PLANES
  - DSC:GOVREV-MAY-ACTION-AUGUST-KNOWN-AT

mission: >
  Wait for government-revenue-live, perform the entitled cookie/bearer/UI
  production proof against the recovery generation, record mapping backlog
  and exact next action, then stop. Do not start D2. Do not merge #5424.

state_before: >
  D1 desk rescue #5836 was already on main. #5856 D1.1F PIT-safe agency was
  still open and merge-blocked. #5870 restored the collection generation the
  candidate projection was frozen against. #5873 recorded that waiting for the
  projection lane does not clear the ci-pack-6 red. #5876 recorded the same
  red as a candidate-id race between daily collection and the govrev fold.

changed:
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: >
      D1 next_action is now stale-write fence then receipt-bound re-baseline
      then #5856 rebase. Radar 48 is recorded as the coherent published count,
      not historical 22. D2 remains unauthorized.
  - path: agentos/handoffs/DEFENSE-PROCUREMENT-V3-2026-08-18.md
    what: Recovery-generation proof packet and remaining mapping backlog.

verified:
  - claim: >
      Production checkout fc9d58195e1 matches origin/main fc9d58195e16.
      Runner health commit field remains cd064848298.
    command: >
      curl -sS https://www.mastermind-x.com/api/health;
      git rev-parse --short=12 origin/main
    result: >
      health status=ok commit=cd064848298 checkout=fc9d58195e1;
      origin/main=fc9d58195e16
  - claim: >
      Recovery source #5870 (0e362f095f10) is an ancestor of the live checkout.
      Published projection clocks are still the 04:15Z fold.
    command: git merge-base --is-ancestor 0e362f095f10 origin/main; python3 reading candidate_projection_state.json
    result: ancestor yes; generated_at=2026-08-18T04:17:31.654847Z known_at=2026-08-18T02:42:13.240485Z
  - claim: >
      government-revenue-live push run 32112383533 concluded success after
      building and proving the candidate projection, then failed to publish.
    command: gh run view 32112383533 --json conclusion,jobs
    result: >
      conclusion=success; refresh 13m47s; annotation
      "could not publish complete evidence after 2 attempts; prior live
      projection remains authoritative"
  - claim: Scheduled tick 32113188277 did not republish (17-second success).
    command: gh run view 32113188277 --json conclusion,jobs,event
    result: event=schedule; refresh 07:59:08Z–07:59:25Z success
  - claim: >
      Entitled cookie candidates.json total 48 equals bearer
      /api/government-revenue/candidates total 48 equals UI Candidate Radar
      count 48, all on content_id grcq1-d7948adf2acbf728e9e48270 generated
      2026-08-18T04:17:31.654847Z.
    command: >
      Chrome-for-Testing profile /tmp/mm-d0r-cft on
      https://www.mastermind-x.com/government_revenue.html after reload;
      cookie fetch government-revenue-data/candidates.json; bearer fetch
      /api/government-revenue/candidates?limit=5; #countCandidates
    result: >
      cookie n=48 total=48; bearer 200 total=48; UI radar=48;
      queueSummary 48 exact-linked research candidates
  - claim: Change/Award tape is the complete governed 500-row workspace at the current cap.
    command: cookie workspace.json events.length; #countChanges; #countAwards; #queueSummary on Changes
    result: >
      500 / 500 / 500 / 500 covered records in this evidence cut;
      bundle grw2-df3a9860110d76a89dd9cc6b
  - claim: Compact-loading banner is hidden after complete hydrate.
    command: document.getElementById('workspaceDegraded').hidden
    result: true
  - claim: No entitled membership CTA is visible.
    command: querySelectorAll membership-plan anchors with display not none and not hidden
    result: membershipVisible=0
  - claim: Cookie-only /api/government-revenue/candidates remains 401 (auth semantics unchanged).
    command: fetch('/api/government-revenue/candidates?limit=1', {credentials:'same-origin'})
    result: 401
  - claim: Bearer /api/me is site_full (status=active, tier=unlimited, source=comp, role=authenticated).
    command: fetch /api/me with MDXAuth access token
    result: 200 those four fields; no email or user id recorded
  - claim: P00032 remains a May obligation discovered later, not an August catalyst and not revenue.
    command: cookie workspace event govws-a6c70850a9cbdce9fa3e7f3b plus inspector after selecting New obligation HC101319C0006
    result: >
      award_change.is_late_discovery=true; effective_at=2026-05-12;
      known_at=2026-08-12T23:50:04.442107Z; amounts[0]=federal_action_obligation
      18416666.66 USD; inspector "Money obligated", "federal action obligation",
      "— → 18416666.66", "action date — → 2026-05-12", action identity
      CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0
  - claim: Truly missing agency on P00032 remains Unspecified agency in the entitled facet.
    command: event.agency; #agencyFilter options after hydrate
    result: >
      agency name=null subagency=null;
      facet options All agencies and Unspecified agency
  - claim: No Python repr or [object Object] is visible in the entitled body.
    command: /toptier_agency/.test(document.body.innerText); includes('[object Object]')
    result: pyrepr=false; objObj=false
  - claim: Budget remains PROJECTION_MISSING. Opportunities remains SOURCE_UNAVAILABLE.
    command: click Budget / Opportunities tabs; #queueSummary and .empty-state
    result: >
      Budget summary PROJECTION_MISSING, copy names public P-1/R-1 PDFs and
      no request graph; Opportunities summary SOURCE_UNAVAILABLE, copy names
      SAM.gov rail with no observation
  - claim: Live reviewed graph is still defense19-v1. #5424 is still draft/open.
    command: >
      bearer candidate issuer_resolution_ref.graph_id;
      gh pr view 5424 --json state,isDraft
    result: recipient-graph:reviewed:2026-08-08:defense19-v1; {state:OPEN, isDraft:true}
  - claim: Mapping backlog is 21 on the same content_id. GE and BWXT remain mapping_needed.
    command: bearer /api/government-revenue/mapping-backlog?limit=50; candidate_queue.json mapping_backlog
    result: >
      total=21 content_id=grcq1-d7948adf2acbf728e9e48270;
      reason_codes partial_identifier_coverage=19
      exact_identifier_mapping_required=2 (GE, BWXT)
  - claim: #5856 D1.1F is still OPEN and merge-blocked. PIT-safe agency code is not on origin/main.
    command: gh pr view 5856 --json state,labels; rg _select_pit_snapshot_agency engine/government_revenue
    result: OPEN labels merge-on-green,merge-blocked; no PIT helper on main
  - claim: Candidate ledger was not hand-advanced. Published queue is 48 against ledger line_count 56.
    command: python3 reading candidate_projection_state.json ledger
    result: append_count=0 line_count=56 sha256 unchanged 065f3a4ac66cebe883910bc0b869bd07727455fa3761bdad1b5374ce1443445f

unverified:
  - claim: >
      P00032 displaying DoD / DISA from PIT-qualified snapshot evidence.
    what_would_verify: >
      Merge #5856 onto a receipt-bound generation, rebuild government-revenue-live
      to a published head, then re-read event govws-a6c70850a9cbdce9fa3e7f3b
      agency.name/subagency and the agency facet for DISA as a human string
  - claim: Agency facet containing real human department names (DoD, NASA, Navy) rather than only Unspecified agency.
    what_would_verify: Same #5856 live rebuild; current entitled facet only lists Unspecified agency because D1 coercion maps Python-dict agency.name strings to Unspecified
  - claim: A published government-revenue-live rebuild of the #5870 restored spine.
    what_would_verify: >
      A later government-revenue-live run whose commit lands new
      latest.json/workspace.json/candidate_queue.json on origin/main instead of
      the "prior live projection remains authoritative" warning

unresolved:
  - D1 is not accepted. The official-receipt → one canonical generation → PIT-safe event chain still has a generation break (live rebuild unpublished) and unexplained candidate identity (ledger 56 vs queue 48, 26 orphaned race ids).
  - #5856 cannot merge until ci-pack-7/ci-pack-11 inherited reds are gone and the head is rebased onto a healed, receipt-bound main.
  - D2 Identity Atlas remains unauthorized.
  - "#5424 defense20-v1 stays draft."

next_actions:
  - Fence government-revenue-live stale writes so a built projection cannot lose the publish to an unrelated main mover and silently keep the prior generation authoritative.
  - Receipt-bound re-baseline of the award spine, latest.json, workspace, and candidate ledger into one coherent generation. Do not hand-write ledger rows.
  - Rebase #5856 onto that generation, keep PIT-safe agency fallback plus source_field_presence, merge only when that head is green.
  - Repeat the entitled cookie = bearer = UI proof against the new content_id / generation, including P00032 DISA from PIT-qualified snapshot evidence.
  - Stop for SOL D1 accept. Do not start D2.

do_not_redo:
  - Do not start D2 or open DEFENSE_D2_IDENTITY_ATLAS_PILOT_HANDOFF.md as an implementation session.
  - Do not merge #5424 as part of recovery.
  - Do not change recipient mappings merely to make Radar or backlog counts nicer.
  - Do not build P-1/R-1, SAM, FMS, GAO, or other collectors.
  - Do not redesign Candidate Radar or raise the 500-event cap.
  - Do not change Prophet or Neural Web.
  - Do not remove known_at from immutable event identity.
  - Do not hand-advance candidate_ledger.jsonl or weaken the historical-candidate guard.
  - Do not treat the 04:18 collection/fold race, or Radar moving 22 → 48, as investment alpha.
  - Do not wait for the projection lane to clear ci-pack-6; DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS measured that wait as a no-op.

danger_areas:
  - Two overlapping daily.yml collect jobs can rewrite append-only award parquets and collection_receipts.jsonl.
  - candidate_id includes event_id which includes known_at, so a restated spine re-identifies already-issued rows.
  - government-revenue-live push_retry can exit 0 after a lost publish; green run ≠ new generation on main.
  - Cookie JSON 200 does not imply bearer /api/government-revenue 200.
  - Compact HTML can look complete at 2 rows; entitled hydrate is required before reading tab counts.
  - Writing into omitted sparse data/ truncates committed artifacts.
  - Do not commit cookies, Authorization headers, emails, or /tmp Chrome profiles.
---

D1 production proof of the currently served recovery generation is done.
Cookie = bearer = UI Candidate Radar = 48 on `grcq1-d7948adf2acbf728e9e48270`.
Change/Award tape = 500 on bundle `grw2-df3a9860110d76a89dd9cc6b`.
P00032 is still a May 12 obligation of $18,416,666.66 with August 12 known_at;
its agency is still null / Unspecified, because #5856 is not live.
D1 is not accepted. Next action is the government-revenue-live stale-write
fence, then a receipt-bound re-baseline, then #5856. Do not start D2.
