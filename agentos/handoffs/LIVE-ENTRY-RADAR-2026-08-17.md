---
workstream: WS:LIVE-ENTRY-RADAR
session: claude/w5-confirmatory-replay + claude/w6-research-priority + claude/w6-rp1-sol-corrections
model: local
ended_because: blocked

mission: >
  ADDENDUM W6-SOL-CORRECTION: fix only the Sol review blockers on the RP1
  ranker (unit-invariant submeasures, canonical priority_value, name-snapshot
  population, real-input receipt, C3 seam + pinned hashes) without starting
  W7/W9 and without examining outcome-conditioned results. Restore W5.1
  Agent OS after the #5834 squash clobber. Return a new head for Sol re-review.
  ADDENDUM W6: implement RP1 Research Priority and open one PR for Sol review.
  W5 original: Run the definitive Live Entry Radar W5 Panel-A/B confirmatory
  replays after #5780 fixed the empty §7 control arm, read the refusal census
  first, report recovered pool sizes and §7 reads, re-check M14/M3, and ship
  the artifacts.

state_before: >
  ADDENDUM W6: W5 done on main (#5825/#5827). W6 was todo. No open W6 collision
  (W8 #5737 only). PR-0 scoring doctrine and W4 live evaluator already merged.
  W5 original: PR #5780 (f8201036c139) was on main. No definitive
  w5_results_panel_*.json existed. The 2026-08-15 5-name smoke spent 81 looks
  with n_refusals=543 vs n_episodes=502 (void). Handoff
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
    what: "W5 marked done at #5825 squash 0394d6e16407 (2026-08-17T10:08:44Z).
      ADDENDUM W6: W6 in_progress, not done; next_action is Sol review."
  - path: research/live_entry_radar/W6_RP1_POLICY.md
    what: "ADDENDUM W6: frozen RP1 equal-Borda ordinal policy, written before ranking code."
  - path: engine/entry_radar/research_priority.py
    what: "ADDENDUM W6: pure deterministic RP1 ranker."
  - path: engine/entry_radar/live_eval.py
    what: "ADDENDUM W6: projection-seam wiring; payload research_priority board."
  - path: engine/entry_radar/live_ledger.py
    what: "ADDENDUM W6: durable research_priority stays null; W6 is payload-ephemeral."
  - path: tests/test_entry_radar_w6_priority.py
    what: "ADDENDUM W6: adversarial battery plus recovery-tape live seam."
  - path: research/live_entry_radar/W6_RP1_RECEIPT_2026-08-17.md
    what: "ADDENDUM W6: real-input proof (WASH C1/C2, VSHAPE G0/C5 seam, STALE/SHORT abstentions)."
  - path: .github/ci/legacy-jobs.yml
    what: "ADDENDUM W6: name the W6 suite in the existing entry-radar CI step."
  - path: engine/entry_radar/research_priority.py
    what: "ADDENDUM W6-SOL-CORRECTION: percentile each submeasure first; canonical
      priority_value; ordinal from that value; unique-ticker snapshot population
      projected onto every expert row."
  - path: tests/test_entry_radar_w6_priority.py
    what: "ADDENDUM W6-SOL-CORRECTION: scale/unit invariance, clone-variant
      population invariance, C3 live-seam, pinned W3 spec hashes."
  - path: research/live_entry_radar/W6_RP1_POLICY.md
    what: "ADDENDUM W6-SOL-CORRECTION: post-Sol-review methodological note; no
      outcome-conditioned inspection."
  - path: research/live_entry_radar/W6_RP1_REAL_INPUT_RECEIPT_2026-08-17.md
    what: "ADDENDUM W6-SOL-CORRECTION: genuine real-store pre-merge receipt via
      live_pack.build_pack + live_eval.run_pass. Not the W4 synthetic LivePack."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "ADDENDUM W6-SOL-CORRECTION: restore W5.1 done (#5833) without dropping
      W6 in_progress."

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
  - claim: "ADDENDUM W6: RP1 adversarial battery is green."
    command: "/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python3 -m pytest tests/test_entry_radar_w6_priority.py -q"
    result: "29 passed"
  - claim: "ADDENDUM W6: Prophet paths are untouched vs origin/main."
    command: "git diff origin/main --stat -- engine/entry_signal.py engine/prophet_*.py"
    result: "empty"
  - claim: "ADDENDUM W6-SOL-CORRECTION: W6 adversarial battery including Sol blockers is green."
    command: "/Users/chriswong/Documents/Cluade/Macro Dashboard/.venv/bin/python3 -m pytest tests/test_entry_radar_w6_priority.py -q"
    result: "33 passed"
  - claim: "ADDENDUM W6-SOL-CORRECTION: real-store build_pack + run_pass receipt exists and did not plant episodes."
    command: "rg -n 'pack_hash=6b9c818ba764de71|No episodes were planted' research/live_entry_radar/W6_RP1_REAL_INPUT_RECEIPT_2026-08-17.md"
    result: "real frames as_of 2026-08-13; empty ACCRUING board; planted-episode denial present"
  - claim: "ADDENDUM W6-SOL-CORRECTION: W5.1 wave row is restored and W6 remains in_progress."
    command: "rg -n 'id: W5.1|id: W6' -A6 agentos/workstreams/WS-LIVE-ENTRY-RADAR.md"
    result: "W5.1 status done pr 5833; W6 status in_progress"

unverified:
  - claim: "The per-episode n_cell and k distributions (beyond the uninformative share)."
    what_would_verify: "Serialize ControlMatch.n_cell and len(controls) in _write_results / _summary_table on a future run. This run's JSON has zero n_cell keys."
  - claim: "§9 nc2_overlap at the 0.50 floor."
    what_would_verify: "A Q1 that clears M14, or an explicit overlap_share dump of the match_proximity=False arm. This run stored NaN on Q1/Q2/Q5."
  - claim: "ADDENDUM W6: live VPS payload will emit rankable RP1 rows once ENTRY_RADAR_LIVE_ENABLE is armed on a session that actually develops episodes."
    what_would_verify: "Post-merge commissioning against the real live/entry_radar.json after a developing RTH pass."
  - claim: "ADDENDUM W6-SOL-CORRECTION: a developing RTH pass on the real probe set will emit a non-empty name-snapshot RP1 board."
    what_would_verify: "The real-input receipt uses the Radar evaluator on real daily frames plus agreeing reconstructed quotes. Full RTH commissioning remains a later gate."

unresolved:
  - "ADDENDUM W6-SOL-CORRECTION: Sol has not yet re-reviewed the RP1 correction head. W6 is not done."
  - "ADDENDUM W6: Sol has not yet reviewed the RP1 PR against the outcome/authority firewall. W6 is not done."
  - "n_cell/k histograms were never written by the runner schema. Empty-cell share is the available proxy."
  - "Panel A and Panel B info_cutoffs differ (2026-08-16T01:23:09Z vs 2026-08-17T01:56:44Z) because sibling minute fetches appended the shared manifest during the A reruns. B does not use those minutes (G0/C5 staged tables)."
  - "Q2 TEST remains ACCRUING (n=1/6). The matched FIT tables are exploratory, not the confirmatory contrast."

next_actions:
  - "ADDENDUM W6-SOL-CORRECTION: Sol re-reviews PR #5845 against the three ranking-law blockers plus C3 seam, pinned hashes, real-input receipt, and W5.1 Agent OS restore."
  - "ADDENDUM W6: Do not mark W6 done at this correction merge; live-payload commissioning still follows."
  - "Do not start W7 or W9."
  - "Optional: persist n_cell/k/overlap_share in _write_results so the next confirmatory dump carries pool histograms."
  - "W8 UI reference remains #5737 (still ACCRUING / Best · unranked until W6 exists in production)."

do_not_redo:
  - "ADDENDUM W6-SOL-CORRECTION: Do NOT inspect W5 outcome tables to choose or retune RP1. The Sol corrections are methodological only."
  - "ADDENDUM W6: Do NOT fit RP1 weights to W5 Q5 G0 earliness or Panel-B H=10 excess."
  - "ADDENDUM W6: Do NOT put Research Priority in live_pack.py or the durable episode ledger."
  - "ADDENDUM W6: Nested payload keys must not contain forbidden tokens rank/score (use ordinal, priority_index, population_n, abstention)."
  - "Do NOT convert the feature panel session column to datetime64 (still binding from the #5780 handoff)."
  - "Do NOT interpret the 81 2026-08-15 names_shard looks. They are ledger facts and void."
  - "Do NOT re-derive whether D1/D2 were real. This run is the production proof they are gone (0 control_match_unavailable on both panels)."
  - "Do NOT treat Q1 UNINFORMATIVE as a matching failure. It is the pre-registered M14 floor at 69.86%."

danger_areas:
  - "ADDENDUM W6: FORBIDDEN_KEY_TOKENS is a substring match. unranked_reason / rankable_n fail liveness. research_priority as a key is inert; nested keys are not exempted by that name."
  - "ADDENDUM W6: quote-only run_pass on the W4 pack does not arm C1; recovery_tape + builder is the live-seam proof. Do not treat an empty live board as a ranker failure."
  - "_attach_and_match still swallows Exception into control_match_unavailable. A new silent lookup bug would again look like data. Census-first remains the gate."
  - "A sparse worktree still truncates data/trial_ledger.jsonl on write. These runs used a FULL checkout."
  - "Sibling supervisors were restarting --panel A in a loop against the same cache; killing them was required so B could finish and so the manifest would stop growing."
  - "Do not git-add the 278MB per-row A census. Counts live in refusal_census_summary."

discoveries: ["DSC:REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP"]
prs: [5825, 5827, 5833, 5834, 5845]
---

## Continuation

The §7 control arm now matches. Panel A: 0 `control_match_unavailable` / 7,546
episodes; FIT empty-cell share ~47%. Panel B: 0 `control_match_unavailable` /
212,593 episodes; TEST G0 empty-cell share 33.6%, C5 13.3%. Q1 is UNINFORMATIVE
on M14 (69.86% < 90%). Q5 is PASS_SHAPED (+13.4 session G0 lead vs incumbent).
Q2 TEST is ACCRUING. Receipt:
`research/live_entry_radar/W5_CONFIRMATORY_RESULTS_2026-08-17.md`.

## ADDENDUM W6 — Research Priority (not done)

RP1 is a deterministic equal-Borda attention ordinal on the live evaluator
projection seam. Policy `research/live_entry_radar/W6_RP1_POLICY.md`. Receipt
`research/live_entry_radar/W6_RP1_RECEIPT_2026-08-17.md`. Durable ledger
`research_priority` stays null. Prophet untouched. Sol reviews the PR against
the frozen outcome/authority firewall. After merge, commission the live
payload before marking W6 done. Do not start W7.

## ADDENDUM W6-SOL-CORRECTION — ranking-law blockers (not done)

#5834 squash-merged while Sol's review was BLOCKED. This follow-up keeps the
W6 architecture and firewalls and corrects only: (1) percentile each
submeasure before combining; (2) ordinal from canonical `priority_value`;
(3) unique-ticker snapshot population with projection onto every expert row;
(4) a genuine real-store `run_pass` receipt; (5) C3 live-seam + pinned spec
hashes; (6) restore W5.1 in `WS-LIVE-ENTRY-RADAR.md` without dropping W6
`in_progress`. Methodological only — no outcome-conditioned inspection.
Do not start W7 or W9. Sol re-reviews the new head.
