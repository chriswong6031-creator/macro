---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/d6b1-fms-coverage-vertical-20260825
model: fable
ended_because: complete
prs: ["#6447", "#6454", "#6478"]
decisions: []
discoveries: []
mission: >
  D6-B1 coverage-aware FMS implementation continuation (Chairman channel
  in-session ruling 2026-08-25, verbatim in this handoff's appendix): U4
  discovery accepted, official-union population law (FR bounded
  denominator/recovery + State current presentation + bounded DSCA
  observations -> transmittal dedupe -> government_fms_case.v1 -> explicit
  coverage manifest with reconciliation refusal -> ninth fms mode ->
  production proof), scope delivered 2026-01-01 -> claim-time.
state_before: >
  D6-B held at the U4 gate (PR #6420 merge bdc2b08d3da9). Carrier:
  ~/.claude-recovery/macro-d6b1 recovery clone (primary local clone git
  object reads kernel-blocked by iCloud-evicted packs). Claim pins:
  origin/main 43bfd1817656; freeze blob 4ed41deca82c + DEC blob
  71adba5e88c9 unchanged.
changed:
  - path: research/defense_intelligence/DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md
    what: >
      frozen implementation spec + §11b post-red-team amendments (13
      adjudicated repairs) + §11c PRODUCTION amendments (2026-08-26: State
      staged replay supersedes the live CLI leg and empty_valid; country
      precedence fall-through; push-race lane note).
  - path: research/defense_intelligence/evidence/fms_d6b1_full_scope_census_2026-08-25.json
    what: receipted planning census (267 FR docs, 57 in-scope originals, State/DSCA surveys, 70-case reconciliation).
  - path: data/government_revenue/fms_staged_objects/
    what: >
      staged official bytes: 14 DSCA articles + 26-13 certification PDF
      (browser clipboard-bridge, sha-frozen) AND the §6b State capture
      (state-listing.html + 10 articles + state_manifest.json, residential
      CLI with disclosed UA, sha-frozen).
  - path: collectors/fms_notifications.py + fms_notifications_live.py
    what: >
      frozen grammars + live acquisition; §6b staged-State replay
      (replay_staged_state_objects, stage-state capture CLI, transport
      cli_residential_staged); FR delivered-date denominator predicate
      shared with the population filter (#6454 heal).
  - path: engine/government_revenue/fms_cases.py + contracts/government_revenue/government_fms_case.v1.schema.json
    what: >
      graph builder with coverage manifest + FmsCoverageRefused gate;
      out_of_scope_originals; country precedence fall-through (§11c);
      state role current_presentation_staged; transport enum extended.
  - path: app/government_revenue.py + templates/site dossiers twins + government_revenue.html.j2 + workspace/metrics freshness + workflows (fms-acquire.yml; government-revenue-live.yml fms blocks; scripts/check_fms_bundle.py)
    what: ninth fms mode end to end (two entitled routes, frozen U5 EN/ZH strings, fms freshness plane).
  - path: .github/ci/legacy-jobs.yml + tests/test_ci_pack.py (PR #6454)
    what: >
      defense-rail-laws job (gate:code, scope:exclusive with the earned
      563-file closure) — the D6-B1 + D6-A law batteries were dark on
      every merge gate inside gate:data unrun-government-revenue; also the
      httpx2->httpx install fix and the #6376 qa_exchange closure widening.
  - path: tests/test_fms_notifications.py + tests/test_fms_ui.py + tests/fixtures/fms/**
    what: T1-T14 + B1-B14 + §11c C1-C3; staged-State laws; fixture staged capture + provenance.
verified:
  - claim: Battery green, merge-binding, and non-vacuous on the merge gate
    command: >
      ci run 32956302168 (PR #6478 head 205eca1d21) pack-7
      defense-rail-laws groups; local venv with the job's exact install line
    result: >
      D6-A 52 passed + FMS 86 passed IN CI (scoped plan: 22 changed files,
      13 declared exclusive, zero unowned paths); operator-directed
      job-by-job audits of runs 32941452226 / 32948446046 recorded every
      pack's job id, runner step, nonzero workload, and ci-gate's
      consumption of current-run fragments.
  - claim: Production acquisition + reconciliation (official-union law live)
    command: >
      fms-acquire runs 32940175991 (gate refusal by design), 32952963771
      (heal proven; push race), 32953625355 (published 9e777ad2145c),
      32961001544 (staged-State; published d90d63c782)
    result: >
      graph 66 cases = 57-transmittal FR denominator (0 unbuilt; 123
      out-of-scope FR-lag originals excluded BY NAME) + 9 web-only
      State-frontier cases; state_pm_bureau 10/10 staged articles,
      role current_presentation_staged, status ok; 73->83 receipts with R2
      strict readback incl. the 26-13 PDF; Singapore fallback-identity case
      minted; duplicate copies dedupe to one transmittal.
  - claim: Publish + served-bytes equality
    command: >
      government-revenue-live run 32964497323 (projection_only dispatch)
      -> commit 5d9628af92c2; ssh VPS sha256sum
    result: >
      site/government-revenue-data/fms-cases.json sha 9da7213f3d13...
      BYTE-IDENTICAL to canonical fms_case_graph.json in repo, served
      Caddy root, and production checkout f507a25aee6 (descendant of the
      publish); government-revenue-dossiers.js served == repo twin
      (389e7010e025...). Page re-baked 302,713 B (fence 303,104).
  - claim: Live canaries + hostile cases on production
    command: >
      ssh VPS /opt/macro-api/.venv/bin/python in-process invocation of
      gr.fms_cases()/gr.fms_case(); anonymous curl probes
    result: >
      total 66, authority display/context_only; 26-13 Kingdom of Saudi
      Arabia $9.0B dsca_and_fr stage congressional_notification delivered
      2026-01-30 (certification PDF observation bound); 26-27 Sweden $930M
      official date 2026-03-10 fr provenance; 26-23 Jordan $280M fr_only
      recovery web_presence false; 26-28 Japan present; no review-period
      arithmetic anywhere in the payload; malformed case key -> 422;
      anonymous: both API routes 401, twin locked:true with zero case
      bodies; workspace carries ONLY /freshness/fms; event plane mentions
      no fms (zero government_procurement_event.v2 rows).
  - claim: Rendered EN/ZH desktop + mobile
    command: Browser pane on https://www.mastermind-x.com/government_revenue.html
    result: >
      ninth tab live in EN ("FMS Congressional Notifications") and ZH
      ("FMS 国会通知", frozen U5 strings incl. the fallback status), active
      mode renders desktop + 375px mobile with the honest anonymous
      locked/empty presentation; authenticated inspector walkthrough not
      performed (D6-A Chairman sequencing precedent) — data-plane proof is
      the in-process invocation + served-bytes equality above.
unverified: []
unresolved:
  - >
    FENCE PRESSURE (Sol): page now bakes 302,713 B — headroom 391 bytes
    (was 522 pre-FMS-freshness). Any non-FMS data growth can breach
    303,104 alone; re-negotiation is a Sol decision.
  - >
    Sol's original "FR-only row cannot mint a case" acceptance line is
    SUPERSEDED BY DESIGN by the official-union ruling (FR recovery minting
    makes 26-23/26-28 canonical). Needs explicit Sol ratification.
  - >
    STATE EDGE VARIANCE (§11c root): state.gov serves datacenter runners
    (and the python-requests UA anywhere) challenge bytes parsing to zero.
    Consequences: the staged capture ages with the presentation (refresh
    lever = stage-state, residential); a genuinely-empty future State
    surface would need a deliberate law change (today it refuses).
  - >
    fms-acquire commit-back has NO push retry (faithful dod-budget mirror)
    and lost one race to the wire cadence; the live lane's publish gate
    only publishes on its own material collection or a
    projection_only/push trigger, so a token-pushed triad needs the
    projection_only dispatch. Lane-design question for Sol (retry loop
    would be a two-lane change).
  - >
    /government-revenue-data/ premium.enforced_early gap pre-exists (Free
    account + PAYWALL_ENABLED=0 could direct-fetch twins).
  - staleness/cadence for freshness.fms deferred pending a Sol cadence ruling.
  - shared graph validator duplicated 3x (build/app/metrics); consolidation later.
  - >
    starlette deprecation says "install httpx2" as its successor — the
    data job's install was normalized to httpx (working today); when the
    fleet migrates starlette/httpx2, defense-rail-laws' install line moves
    with it.
do_not_redo:
  - Do not re-run the planning census from scratch (receipted artifact).
  - Do not commit site/government_revenue.html from a carrier (live lane owns it); DO commit the dossiers.js twin (paired plain-copy law).
  - Do not add cross-case value aggregates, review-period logic, event.v2 rows, or any web-surface population assumption.
  - Do not bulk-backfill pre-2026 DSCA; do not point CI at live state.gov again (§6b).
  - Do not re-home the FMS/D6-A batteries into a gate:data job — merge-binding requires gate:code (defense-rail-laws).
danger_areas:
  - defense-rail-laws is scope:exclusive — a NEW import in either battery's closure must widen its paths (the closure-coverage test reds otherwise, by design).
  - fms-acquire shares the government-revenue-live concurrency group — never cancel its runs (hook-enforced).
  - Recovery-clone carriers need repo-local gh credential helper + users.noreply email or pushes hang/GH013-reject.
  - stage-state must run residentially; its zero-qualifying refusal is load-bearing (never bypass it to "just stage what's there").
next_actions:
  - Sol return posted on PR #6447 (pointer on #6404) with this packet; D6-C+ / D7+ remain UNAUTHORIZED; session ends.
---

## Appendix — D6-B1 continuation commission (verbatim)

D6-B1 — COVERAGE-AWARE FMS IMPLEMENTATION CONTINUATION
U4 discovery accepted: State + DSCA web surfaces are non-exhaustive.
Replace the old web-surface population assumption with the frozen official-union coverage law.
Scope is 2026-01-01 through claim-time current date only.
Build:
`Federal Register bounded denominator/recovery`
`+ State current presentation observations`
`+ DSCA historical observations`
`→ transmittal-number dedupe`
`→ canonical GovRev FMS records`
`→ explicit source/coverage manifest`
`→ existing ninth fms mode`
`→ production proof`.
Preserve B0 laws:

* highest v1 lifecycle authority is `congressional_notification`;
* review-period expiry advances nothing;
* estimated notification value is not funded value, award, backlog, revenue or cash;
* contractor prose cannot mint issuer identity;
* system-name similarity cannot mint D5 program identity;
* append-only corrections;
* no `award_change` abuse;
* no new general event store.

Required hostile cases now include:

* 26-23 Jordan: canonical notification present despite State/DSCA web absence;
* 26-28 Japan: post-cutover notification cannot disappear merely because the State web corpus omitted it;
* 26-27 Sweden: positive current web/official case;
* duplicate copy across source families produces one transmittal;
* FR publication lag cannot rewrite Congressional-delivery time;
* missing web page cannot become `VALID_EMPTY`;
* zero official denominator reconciliation cannot pass publication silently.

Do not start D6-C.
Stop after the FMS vertical is production-proven and return to Sol.
