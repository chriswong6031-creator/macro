---
workstream: WS:LIVE-ENTRY-RADAR
session: claude/w5-confirmatory-replay
model: local
ended_because: complete

mission: >
  Run the definitive Live Entry Radar W5 Panel-A/B confirmatory replays after
  #5780 fixed the empty §7 control arm, read the refusal census first, report
  recovered pool sizes and §7 reads, re-check M14/M3, and ship the artifacts.

state_before: >
  PR #5780 (f8201036c139) was on main. No definitive w5_results_panel_*.json
  existed. The 2026-08-15 5-name smoke spent 81 looks with n_refusals=543 vs
  n_episodes=502 (void). Handoff
  agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-15-w5-control-matching.md left the
  full-panel run as the next action. DSC:REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP.

changed:
  - path: research/live_entry_radar/w5_results/w5_results_panel_A.json
    what: "Compact Panel-A confirmatory JSON (questions, tables, census
      summary). Production file had 1,292,516 refusal rows / 278MB; git copy
      keeps counts only. control_match_unavailable=0, n_episodes=7546."
  - path: research/live_entry_radar/w5_results/w5_results_panel_A.tables.csv
    what: "Panel-A flat tables including FIT C1/C2A with floors_met and
      uninformative_no_control_n."
  - path: research/live_entry_radar/w5_results/w5_results_panel_B.json
    what: "Compact Panel-B confirmatory JSON. control_match_unavailable=0,
      n_refusals=67534, n_episodes=212593. Q1 UNINFORMATIVE (M14), Q5
      PASS_SHAPED."
  - path: research/live_entry_radar/w5_results/w5_results_panel_B.tables.csv
    what: "Panel-B flat tables (G0/C5 primary+FIT, cohorts, regimes, C32)."
  - path: research/live_entry_radar/W5_CONFIRMATORY_RESULTS_2026-08-17.md
    what: "Human receipt: census, pool proxies, §7 reads, M14/M3."
  - path: data/trial_ledger.jsonl
    what: "Append-only full-panel looks (this tree's Panel A + sibling Panel B
      confirmatory hashes). Smoke 81 names_shard rows untouched."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W5 marked done at #5825 squash 0394d6e16407 (2026-08-17T10:08:44Z)."

verified:
  - claim: "Panel A control_match_unavailable count is 0 against 7546 episodes."
    command: "rg -c control_match_unavailable research/live_entry_radar/w5_results/w5_results_panel_A.json; python3 -c \"import json; print(json.load(open('research/live_entry_radar/w5_results/w5_results_panel_A.json'))['refusal_census_summary'])\""
    result: "0 matches; n_refusals=1292516 n_episodes=7546 control_match_unavailable=0"
  - claim: "Panel B control_match_unavailable count is 0 against 212593 episodes."
    command: "python3 -c \"import json; s=json.load(open('research/live_entry_radar/w5_results/w5_results_panel_B.json'))['refusal_census_summary']; print(s)\""
    result: "n_refusals=67534 n_episodes=212593 control_match_unavailable=0 by_reason g6_out_of_era=67496 no_staged_table=38"
  - claim: "Panel B attach added no matching refusals."
    command: "rg 'refusal\\(s\\) recorded on panel B' research/live_entry_radar/w5_results/replay_both.log"
    result: "gather print 67534 equals ledger n_refusals 67534"
  - claim: "M14 date_agreement is 0.6986 vs floor 0.90, so Q1 is UNINFORMATIVE."
    command: "python3 -c \"import json; print(json.load(open('research/live_entry_radar/w5_results/w5_results_panel_B.json'))['questions']['Q1']['verdict'], json.load(open('research/live_entry_radar/w5_results/w5_results_panel_B.json'))['questions']['Q1']['notes'])\""
    result: "UNINFORMATIVE; note names 69.86% vs 90% floor"
  - claim: "M3 eff_names on Panel-B TEST G0/C5 exceeds 8."
    command: "python3 -c \"import json; t=json.load(open('research/live_entry_radar/w5_results/w5_results_panel_B.json'))['tables']; print(t['primary_table_G0']['eff_names'], t['primary_table_G0']['floors_met'], t['primary_table_C5']['eff_names'], t['primary_table_C5']['floors_met'])\""
    result: "2310.82 True / 1536.77 True"
  - claim: "Q5 graded PASS_SHAPED with BH surviving."
    command: "python3 -c \"import json; q=json.load(open('research/live_entry_radar/w5_results/w5_results_panel_B.json'))['questions']['Q5']; print(q['verdict'], q['bh_survives'], q['primary']['stat'])\""
    result: "PASS_SHAPED True 13.434530490086045"
  - claim: "Confirmatory-receipt PR #5825 is merged on origin/main."
    command: "gh pr view 5825 --json state,mergedAt,mergeCommit --jq '{state,mergedAt,sha:.mergeCommit.oid}'; git log -1 --oneline origin/main"
    result: "MERGED 2026-08-17T10:08:44Z squash 0394d6e16407"

unverified:
  - claim: "The per-episode n_cell and k distributions (beyond the uninformative share)."
    what_would_verify: "Serialize ControlMatch.n_cell and len(controls) in _write_results / _summary_table on a future run. This run's JSON has zero n_cell keys."
  - claim: "§9 nc2_overlap at the 0.50 floor."
    what_would_verify: "A Q1 that clears M14, or an explicit overlap_share dump of the match_proximity=False arm. This run stored NaN on Q1/Q2/Q5."

unresolved:
  - "n_cell/k histograms were never written by the runner schema. Empty-cell share is the available proxy."
  - "Panel A and Panel B info_cutoffs differ (2026-08-16T01:23:09Z vs 2026-08-17T01:56:44Z) because sibling minute fetches appended the shared manifest during the A reruns. B does not use those minutes (G0/C5 staged tables)."
  - "Q2 TEST remains ACCRUING (n=1/6). The matched FIT tables are exploratory, not the confirmatory contrast."

next_actions:
  - "Optional: persist n_cell/k/overlap_share in _write_results so the next confirmatory dump carries pool histograms."
  - "W6 Research Priority and W8 UI reference (#5737 already open) are the next fresh commissionings."

do_not_redo:
  - "Do NOT convert the feature panel session column to datetime64 (still binding from the #5780 handoff)."
  - "Do NOT interpret the 81 2026-08-15 names_shard looks. They are ledger facts and void."
  - "Do NOT re-derive whether D1/D2 were real. This run is the production proof they are gone (0 control_match_unavailable on both panels)."
  - "Do NOT treat Q1 UNINFORMATIVE as a matching failure. It is the pre-registered M14 floor at 69.86%."

danger_areas:
  - "_attach_and_match still swallows Exception into control_match_unavailable. A new silent lookup bug would again look like data. Census-first remains the gate."
  - "A sparse worktree still truncates data/trial_ledger.jsonl on write. These runs used a FULL checkout."
  - "Sibling supervisors were restarting --panel A in a loop against the same cache; killing them was required so B could finish and so the manifest would stop growing."
  - "Do not git-add the 278MB per-row A census. Counts live in refusal_census_summary."

discoveries: ["DSC:REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP"]
---

## Continuation

The §7 control arm now matches. Panel A: 0 `control_match_unavailable` / 7,546
episodes; FIT empty-cell share ~47%. Panel B: 0 `control_match_unavailable` /
212,593 episodes; TEST G0 empty-cell share 33.6%, C5 13.3%. Q1 is UNINFORMATIVE
on M14 (69.86% < 90%). Q5 is PASS_SHAPED (+13.4 session G0 lead vs incumbent).
Q2 TEST is ACCRUING. Receipt:
`research/live_entry_radar/W5_CONFIRMATORY_RESULTS_2026-08-17.md`.
