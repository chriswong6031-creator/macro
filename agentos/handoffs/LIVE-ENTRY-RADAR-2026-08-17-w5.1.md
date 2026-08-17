---
workstream: WS:LIVE-ENTRY-RADAR
session: claude/w5-1-control-pool-obs
model: local
ended_because: complete

mission: >
  Optional Handoff 3 / W5.1: persist n_cell, selected k, and overlap_share on
  the existing W5 summary surface so the next confirmatory dump can inspect
  control-pool quality directly. Serialization only.

state_before: >
  W5 confirmatory #5825 is on main. The 2026-08-17 durable handoff left
  n_cell/k histograms and NC-2 overlap (NaN on questions that never reached
  that stage) as unverified instrumentation debt. Matching itself is not in
  question (0 control_match_unavailable on both panels).

changed:
  - path: engine/entry_radar/replay/assembly.py
    what: "episode_row now copies ControlMatch.n_cell beside the already-serialized n_controls (selected k)."
  - path: engine/entry_radar/replay/confirmatory.py
    what: "_summary_table appends n_cell_{mean,median,min,max}, k_n_0..k_n_5, and overlap_share (mean of same_band_support). Null when the column is absent. Legacy keys and their values are unchanged."
  - path: tests/test_entry_radar_w5_battery.py
    what: "W5.1 section: frozen-match serialization, null-when-absent, zero overlap is defined, legacy numbers stable after n_cell is added, writer does not call match, already-produced synthetic match proof, look-count pin, sort_keys/CSV prefix stability."
  - path: agentos/workstreams/WS-LIVE-ENTRY-RADAR.md
    what: "W5.1 wave added in_progress; W6 left todo and unblocked by W5 still."

verified:
  - claim: "A frozen synthetic ControlMatch already produced by controls.match serializes n_cell=3, k=3, overlap_share=1.0, and rematching equals the original object."
    command: "venv python snippet: controls.match on tests.test_entry_radar_w5_battery._panel(); assembly.episode_row + confirmatory._summary_table; rematch == produced"
    result: "ControlMatch n_cell=3 controls=('CCC','BBB','DDD'); table k_n_3=1 overlap_share=1.0; match identical True. No TrialLedger look."
  - claim: "W5 battery including the new W5.1 tests is green, and sibling W5 CI-wired suites stay green."
    command: "python -m pytest tests/test_entry_radar_w5_battery.py tests/test_entry_radar_w5_gates.py tests/test_entry_radar_w5_data.py tests/test_entry_radar_w5_perf.py tests/test_entry_radar_w5_reconciler.py tests/test_entry_radar_w5_heartbeat.py -q"
    result: "74 passed (battery) + 173 passed (sibling W5 suites)"
  - claim: "run_all still spends only existing §13 cells on the synthetic Panel-A frame; _spend site count is unchanged at 19."
    command: "pytest tests/test_entry_radar_w5_battery.py::test_w51_run_all_look_count_is_unchanged"
    result: "spent == q2_primary, nc2_q2, regime_quiet_C2A, common_eligibility; src.count('_spend(')==19"

unverified:
  - claim: "Production Panel-A/B n_cell and k histograms."
    what_would_verify: "The next naturally occurring W5/W7 confirmatory dump after this merge. Do not rerun W5 solely to fill the new keys."

unresolved:
  - "Q1 remains UNINFORMATIVE on M14 (69.86% < 90%); W5.1 does not change that."
  - "Questions that never reach NC-2 still store nc2_overlap=NaN; the overlap diagnostic now lives on the summary tables instead."

next_actions:
  - "Do not rerun W5 confirmatory for prettier histograms."
  - "W6 Research Priority and W8 UI reference remain the next fresh commissionings."

do_not_redo:
  - "Do NOT convert the feature panel session column to datetime64."
  - "Do NOT interpret the 81 2026-08-15 names_shard looks."
  - "Do NOT change controls.match, CONTROL_K, M3, M14, NC-2, detectors, outcomes, or TrialLedger look accounting."
  - "Do NOT add a second results format."

danger_areas:
  - "A write into omitted data/ in a sparse worktree still truncates trial_ledger.jsonl. This PR does not write data/."
  - "_attach_and_match still swallows Exception into control_match_unavailable. Census-first remains the gate."
---

## Continuation

W5.1 is serialization-only. The next confirmatory JSON/CSV will carry
`n_cell_*`, `k_n_0..k_n_5`, and `overlap_share` on every existing summary
table. Matching bytes, look cells, and confirmatory statistics are unchanged.
Do not spend another W5 look to populate the new keys.
