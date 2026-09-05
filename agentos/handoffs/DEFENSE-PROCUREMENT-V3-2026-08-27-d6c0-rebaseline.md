---
workstream: WS:DEFENSE-PROCUREMENT-V3
session: claude/defense-procurement-v3-d6c0-rebaseline
model: fable
ended_because: complete
prs: []
decisions: []
discoveries:
  - DSC:GOVREV-SBIR-RAIL-IS-A-SHIPPED-COLLECTOR-ONLY-WAVE
  - DSC:GOVREV-PAGE-FENCE-PEAK-IS-THE-SAM-EVIDENCE-BAKE
  - DSC:OFFICIAL-SOURCE-403-TO-A-BARE-PROBE-CARRIES-NO-SIGNAL
mission: >
  D6-C0 rebaseline / architecture freeze, first child wave of the sustained Sol-COO Defense
  program-control operation `defense-procurement-v3-program-control-20260827-sol-coo-001`.
  Determine the strongest lawful next D6 official-source vertical from CURRENT main and freeze
  one bounded producer -> canonical truth -> real consumer -> production-proof wave.
  Records/research only; no runtime, product, data, or source mutation; returns HOLD-FOR-SOL.
state_before: >
  D0R-D4 closed. D5 closed for sequencing but BUILT_NOT_PROVEN (D5P entitled browser proof
  never happened). D6-A Budget PROVEN_LIVE. D6-B/FMS SOL ACCEPTED / PROVEN_LIVE with a binding
  official-union law (FR 36(b)(1) records are population authority; State/DSCA web presence is
  observational only; v1 stops at congressional_notification; estimated notification value is
  never funded value/award/backlog/revenue/cash). WS PARKED at the D6-B boundary. Dispatch pins
  Macro main d84468e41f40 and Skillpack Mastermind@d508e30c, both to be re-pinned at pickup.
changed:
  - path: research/defense_intelligence/DEFENSE_D6C0_REBASELINE_AND_ARCHITECTURE_FREEZE_2026-08-27.md
    what: >
      The D6-C0 rebaseline and architecture freeze. Carries the capability ledger for every
      remaining D6 rail, the owner/path/source/rights/PIT/correction/failure-state map, the
      positive-control table for every instrument used, the page-fence constraint, the
      withdrawn source-feasibility conclusion and what replaced it, rail selection under the
      D6-B official-union law, the single recommended vertical with its full proposed journey
      (contracts, four clocks, nulls, corrections, deterministic method, tests, production
      proof, Gate 0, non-goals, stop condition), the collision census, and the three
      conditions that would flip the recommendation.
  - path: agentos/discoveries/DSC-GOVREV-SBIR-RAIL-IS-A-SHIPPED-COLLECTOR-ONLY-WAVE.md
    what: >
      New discovery. The SBIR/STTR rail is fully built and fully registered yet has committed
      zero artifacts in 19 days, has zero product consumers, and has zero contract schema files
      against five contract names declared in code.
  - path: agentos/discoveries/DSC-GOVREV-PAGE-FENCE-PEAK-IS-THE-SAM-EVIDENCE-BAKE.md
    what: >
      New discovery. government_revenue.html swings ~38 KB between bake regimes; true headroom
      is 214 bytes at the SAM-evidence peak, not the ~25.9 KB visible at HEAD.
  - path: agentos/discoveries/DSC-OFFICIAL-SOURCE-403-TO-A-BARE-PROBE-CARRIES-NO-SIGNAL.md
    what: >
      New discovery/landmine. A bare HTTP probe cannot grade official-source feasibility,
      because dsca.mil and sec.gov — both collected in production — return the same 403.
  - path: agentos/workstreams/WS-DEFENSE-PROCUREMENT-V3.md
    what: >
      Projection only. Adds the D6-C0 wave entry at status hold_for_sol with its next_action;
      no change to any accepted wave's status or to owns_paths.
verified:
  - claim: Macro main re-pinned at 4ac1c60e408f, two commits ahead of the dispatch pin, neither touching Defense/GovRev.
    command: git fetch origin && git rev-parse origin/main && git log origin/main --oneline -3
    result: 4ac1c60e408f6cd36af5295444ac6f290942e33f; 61f2f7eeb8cb gh-quota shape 7; d84468e41f40 was the dispatch pin.
  - claim: The protected Sol Skillpack content is unchanged since the dispatch pin; only the Mastermind repo head moved.
    command: git diff --stat d508e30c865bd2425bb551650b71381b7eb6d4f8..origin/master -- docs/sol_skills/
    result: empty. Repo head is b901dee0272a99b8a1d60385848b99b7273e8261 on branch master; the two commits touch docs/superpowers, ops/executive_os, tests/test_c1_installer_control_config.py only.
  - claim: Zero of 37 open PRs touch any WS-DEFENSE-PROCUREMENT-V3 owns_paths entry.
    command: gh pr list --state open --limit 100 --json number,files --jq '[.[] | select((.files//[]) | map(.path) | any(test("government_revenue|defense_intelligence|dod_budget|fms_notifications|sbir_awards|DEFENSE_PROCUREMENT")))] | length'
    result: 0, verified twice against origin/main 4ac1c60e408f; instrument positive-controlled (PR 6587=3 files, 6586=4, 6585=8).
  - claim: All five SBIR data artifacts declared in synapse.yml and dag.yml are absent from git.
    command: git ls-files --error-unmatch data/government_revenue/sbir_award_observations.parquet (and the four siblings)
    result: all five ABSENT, against a positive control of 35 present fms_*/dod_budget_* artifacts in the same sparse tree.
  - claim: SBIR has no product consumer; only tests import the engine module.
    command: grep -rn 'sbir_progression' --include='*.py' . | grep -v '^./tests/'; grep -n sbir scripts/build_government_revenue.py app/government_revenue.py
    result: only a docstring reference inside collectors/sbir_awards.py itself; zero builder or app hits.
  - claim: SBIR declares five contracts in code and ships none as schema files.
    command: grep -n 'SCHEMA' collectors/sbir_awards.py | head; git ls-files contracts/ | grep -i sbir
    result: five names at collectors/sbir_awards.py:70-74; zero files, while the accepted FMS rail carries government_fms_case.v1.schema.json.
  - claim: The Government Revenue page fence has 214 bytes of headroom at its live-lane peak, not the 25,887 visible at HEAD.
    command: git log --format=%H -60 -- site/government_revenue.html then git show <sha>:site/government_revenue.html | wc -c
    result: peak 302,890 B at f5f11112da45 (SAM evidence); 302,713 B at 5d9628af92c2; HEAD 277,217 B at 8229cce709af; min 264,727 B; fence 303,104 at scripts/build_government_revenue.py:118.
  - claim: A bare HTTP 403 cannot grade official-source feasibility.
    command: curl -s -o /dev/null -w '%{http_code}' -A '<browser UA>' against each candidate and each known-collected source
    result: 403 from gao.gov, dote.osd.mil, dodig.mil, api.www.sbir.gov AND from dsca.mil and sec.gov which are collected in production; 200 from api.usaspending.gov, federalregister.gov/api, gao.gov/rss/reports.xml, example.com.
  - claim: D6-B/FMS is genuinely live now, not merely accepted on paper.
    command: git show HEAD:data/government_revenue/fms_projection_state.json and tail of fms_collection_receipts.jsonl
    result: 83 observations / 83 receipts, generated_at 2026-08-26T11:01:35Z, receipts carrying http_status 200 against state.gov release URLs.
unverified:
  - claim: SBIR.gov refuses this repository's actual collector, rather than merely refusing a bare developer-host probe.
    what_would_verify: >
      Reproduce the request from the self-hosted runner using the header discipline in
      collectors/fms_notifications_live.py:503-507, and read the resulting status and body.
      This is Gate 0 of the proposed wave and must be answered before any code is written.
  - claim: No open, machine-readable population authority exists for GAO bid-protest dockets.
    what_would_verify: >
      A search of GAO's published data offerings for a bulk export, documented API, or
      Federal-Register-class publication of protest dockets. The claim rests on filename and
      content greps of this repository plus four probed GAO URLs, not on an exhaustive review
      of GAO's own documentation; gao.gov/rss/reports.xml (200) carries reports, not dockets.
unresolved:
  - Why the SBIR rail is dark — a refusing source versus a never-activated collector are observationally identical from the repository, because the collector leaves ledger, activation state, and status untouched on source failure.
  - Whether the SBIR consumer should be a separate site/government-revenue-data read model or an off-page consumer; both are lawful under the fence and the choice is Sol's.
  - D5 remains BUILT_NOT_PROVEN pending a genuine entitled D5P browser journey. Untouched by this wave and nonblocking for sequencing.
next_actions:
  - Sol rules on the recommended vertical (complete SBIR/STTR from DARK_OR_DISCONNECTED to PROVEN_LIVE) or selects against it using one of the three flip conditions in §9 of the freeze document.
  - If SBIR is authorized, execute Gate 0 first — reproduce the SBIR.gov response from the runner with the FMS header discipline. If the source refuses under documented terms, record SBIR REJECTED_BY_DESIGN with evidence and return to Sol rather than retrying or failing over.
  - If Gate 0 passes, author the five contract schema files under contracts/government_revenue/ before any collection run.
  - Size any user-facing consumer against 302,890 B, never against the size at HEAD; prefer a consumer adding zero bytes to government_revenue.html.
  - Re-run the collision census against fresh origin/main immediately before opening the implementation carrier.
do_not_redo:
  - Do not redo #6447, #6454, #6478, #6480, #6485, or D6-B0. D6-B/FMS is Sol accepted and PROVEN_LIVE.
  - Do not re-derive the source/rights/PIT verdicts for the remaining rails. D0R already adjudicated them in research/defense_intelligence/D0R_SOURCE_RIGHTS_AND_PIT_REGISTRY.md — DoD contract announcements ADAPT join-only, DLA/DIBBS DEFER, DIU/AFWERX/OTA RESEARCH_ONLY, GAO BUILD, DOT&E BUILD, DoD/service IG ADAPT — and gate 6 of D0R_REMAINING_WORK.md already recorded the DSCA/GAO dockets as unverified at that close.
  - Do not record SBIR as NOT_BUILT. It is built, registered in synapse.yml, dag.yml, collect.py, append_only_artifacts.json and legacy-jobs.yml, and merely produces and feeds nothing.
  - Do not grade any candidate source with a bare curl probe and do not record a rail infeasible on a 403. That instrument fails its own positive control.
  - Do not conclude the page fence has ~25 KB of headroom from a reading at HEAD.
  - Do not propose a second Government Revenue, FMS, event, identity, budget, SEC, transcript, estimate, market-data, Neural Web, or Prophet plane; the completion map forbids all of them.
danger_areas:
  - site/government_revenue.html sits 214 bytes under RAW_HTML_BUDGET_BYTES at its live-lane peak while reading ~25.9 KB clear at HEAD. Byte-adding changes verified at the trough will fail intermittently on the next SAM evidence commit.
  - Registration is not production. synapse.yml, dag.yml, collect.py and a green CI suite are all satisfied by the SBIR rail, which has never persisted a row.
  - collectors/sbir_awards.py leaves ledger, activation state, and status unchanged on source failure, so a permanently failing source produces no alarm and no trace anywhere in the repository.
  - The D6-B official-union law is binding on rail selection, not only on FMS. A rail whose only population source is WAF-protected web is unlawful under it regardless of acquisition quality.
  - This worktree is sparse; data/, site/, mockups/ and verify_shots/ are not materialized. Writing into an omitted tree truncates the committed artifact. Nothing in this wave writes to any of them.
---

# D6-C0 — what a cold stranger needs to continue

## Where this wave leaves the program

The Defense Procurement V3 program is parked at the accepted D6-B boundary. This wave did not
move that boundary. It answered one question — which D6 official-source rail should be built
next — and froze the answer as a recommendation for Sol, plus three durable facts that were not
previously written down anywhere.

Nothing was mutated. No collector ran, no builder ran, no `data/` or `site/` path was touched,
no schema changed, no page fence moved. The only writes are this handoff, the freeze document,
three discovery records, and a projection-only wave entry on the workstream.

## The one instruction from the dispatch that changed the outcome

The dispatch said to census current owners first and not to assume any rail is `NOT_BUILT`
because the 2026-08-16 plan says so. That instruction is the reason this wave produced a real
finding rather than a restatement of the plan. The SBIR/STTR rail — listed in the plan among
the remaining rails — is in fact fully built and fully registered, and has been producing and
feeding nothing for nineteen days. A census that trusted the plan would have proposed building
it from scratch, on top of a collector that already exists.

## The recommendation in one paragraph

Complete the SBIR/STTR rail from `DARK_OR_DISCONNECTED` to `PROVEN_LIVE`. It is the only
remaining rail with a documented open machine-readable population authority, which is what the
binding D6-B official-union law requires; the higher-value adverse-event rails (GAO protest,
DOT&E, DoD/service IG) have no proven open population authority and would rest on
WAF-protected web as population, which that law forbids. SBIR needs no new source rights, no
new plane, and no new contract family — its producer and engine already exist and were
reviewed. Its investor value is the lowest of the candidate set, and the freeze document says
so plainly rather than overselling it; its value is graph value, as the earliest observable
evidence of industrial-base capability formation. Three named conditions would flip the
recommendation to GAO, and they are written out so Sol can rule against this cheaply.

## The two traps most likely to catch the next session

**The page fence reads clear and is not.** `site/government_revenue.html` shows roughly 25.9 KB
of headroom at HEAD and 214 bytes at its live-lane peak, because the `govrev: SAM opportunity
evidence` bake embeds about 25 KB the render-lane bake does not. A consumer sized against the
HEAD reading will pass every local check and blow `RAW_HTML_BUDGET_BYTES` on the next SAM
evidence commit. Size against 302,890 B, or add zero bytes to that page.

**A 403 from an official source proves nothing.** Grading candidate sources with a bare `curl`
produced a clean and entirely wrong story in this wave — GAO, DOT&E, DoDIG and SBIR all
refused, which looked like a feasibility verdict until the same probe was run against
`dsca.mil` and `sec.gov`, which this repository collects in production and which refuse
identically. The conclusion was withdrawn. Feasibility for a WAF-protected official source is
established by reproducing the request with the acquisition discipline in
`collectors/fms_notifications_live.py`, from the runner, and by nothing less.

## What is deliberately still open

Why the SBIR rail is dark is not established, and the freeze document does not pretend
otherwise. The collector leaves its ledger, activation state, and status untouched when the
source fails, so a permanently refusing source and a collector that never activated leave
identical traces — which is to say, none. That question is Gate 0 of the proposed wave and must
be answered from the runner before any code is written. If the source refuses under documented
terms, the lawful outcome is to record SBIR `REJECTED_BY_DESIGN` with evidence and return to
Sol; that closes a D6 rail honestly and is a legitimate wave outcome. A blind retry or failover
is forbidden.

D5 remains `BUILT_NOT_PROVEN` pending a genuine entitled D5P browser journey. This wave did not
touch it and it does not block sequencing.

## Authority boundary

This carrier is HOLD-FOR-SOL. It recommends one vertical and does not authorize it. No
implementation rail is self-authorized, D7 is not started, and no rank, gate, size, entry, or
execution authority is created or implied anywhere in it.
