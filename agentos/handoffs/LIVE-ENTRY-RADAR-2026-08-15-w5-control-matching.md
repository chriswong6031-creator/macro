---
workstream: WS:LIVE-ENTRY-RADAR
session: priceless-kowalevski-24ef1a
model: opus
ended_because: complete

mission: >
  Confirm and fix a reported defect in W5's §7 control matching:
  `scripts/entry_radar_replay.py::_ctx_session_rows` could not match the feature panel
  `build_match_context` builds, so every episode fell into the
  `control_match_unavailable` refusal branch. Scoped as its own results-changing PR,
  explicitly NOT folded into the parallel performance work on `_attach_and_match`.

state_before: >
  W5's machinery landed on main at PR-5b (#5741, 6de557a73f96, 2026-08-15T11:39Z);
  PR-5a froze the prereg. The pre-merge red-team receipt
  (research/live_entry_radar/w5_results/PRE_MERGE_REVIEW_DISPOSITIONS.md) records
  "Results seen: NONE". The defect was reported from a sibling session shipping a pure
  performance refactor of `_attach_and_match` (#5775), which proved byte-identical
  outputs on BOTH panel dtypes precisely because old and new code fail the same way on
  the real one. `build_match_context` had no test; `panels.session_calendar` had zero
  callers in the replay stack.

changed:
  - path: scripts/entry_radar_replay.py
    what: "Added `_session_key` (the panel's canonical `datetime.date` spelling).
      `_ctx_session_rows` now keys on it and handles an object OR datetime64 column
      explicitly instead of assuming `pd.Timestamp`. `build_match_context` normalizes
      the `session` column once at the seam, passes `panels.session_calendar(spy)` to
      `attach_session_positions` so §7 offsets count TRADING sessions rather than slots
      between decision sessions, refuses with `ReplayRefusal` when the panel resolves 0
      of N decision sessions, prints a `::warning` on partial resolution, and returns
      `sessions_resolvable`/`sessions_total` in the context."
  - path: tests/test_entry_radar_w5_data.py
    what: "Six tests under a new §7 control-matching section, all built THROUGH
      `feature_panel.build_feature_rows` rather than hand-rolled: the canonical-spelling
      pin, the object-dtype regression pin (whose last assertion IS the pre-fix
      expression, so it cannot go vacuous), the datetime64 shape, the still-refuses-an-
      absent-session pin, the bench-calendar wiring pin (sparse decision sessions 20
      trading sessions apart, plus the `eligible_pool` law-level assertion), and the
      zero-resolvable refusal."
  - path: research/live_entry_radar/W5_CONTROL_MATCHING_DEFECT_2026-08-15.md
    what: "New. The §7-aware justification: both defects, the evidence and its limits,
      why the column stays `date` rather than becoming datetime64, the recurrence guard,
      and what must still be run."
  - path: agentos/discoveries/DSC-REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP.md
    what: "New discovery record."

verified:
  - claim: "The production builder emits an object `session` column of `datetime.date`,
      and the pre-fix Timestamp key matches zero rows on it."
    command: "python3 -c \"...feature_panel.build_feature_rows(...); panel =
      feature_panel.cross_sectionalize(rows); print(panel['session'].dtype,
      (panel['session'] == pd.Timestamp(sessions[0])).sum(), (panel['session'] ==
      sessions[0]).sum())\" (full snippet in the receipt doc §2)"
    result: "object / 0 / 1 — pandas 3.0.3, at 65f9669f"
  - claim: "A real replay ran and its Panel-B refusal count exceeds its episode count."
    command: "git show HEAD:data/trial_ledger.jsonl | grep '\"family\": \"entry_radar\"'"
    result: "82 rows 2026-08-15T09:01-09:33Z: 1 declared_budget (n=253) + 81
      `source: w5_replay` looks, ALL carrying names_shard [NVDA,KO,JPM,MSFT,XOM]; the
      Panel-B row reads n_refusals=543 against n_episodes=502"
  - claim: "No definitive W5 confirmatory output exists on this host."
    command: "find /Users/chriswong -name 'w5_results_panel_*.json'; grep -rl
      control_match_unavailable /Users/chriswong/Documents/Cluade /Users/chriswong/.claude"
    result: "both empty"
  - claim: "The new tests fail on the pre-fix code (mutation controls, both defects)."
    command: "restore `mask = column == pd.Timestamp(key)`, then
      `attach_session_positions(features)`, running the -k subset after each"
    result: "2 failed for D1; 1 failed for D2 with `assert 2 == 400` — the pre-fix map
      held 2 entries for sessions 20 trading sessions apart, so the offset read 1"
  - claim: "The radar suite is green with the fix in place."
    command: "python3 -m pytest $(ls tests/test_entry_radar_*.py | tr '\\n' ' ') -q"
    result: "1375 passed, 3 skipped"

unverified:
  - claim: "Panel-A behaves like Panel-B under the fix."
    what_would_verify: "The definitive Panel-A replay, which has never been run. D1 is
      input-independent (the mask is all-False for every session on every universe), so
      the defect certainly applied to Panel-A; the SIZE of the recovered control pools
      is unmeasured on both panels."
  - claim: "The §9 proximity-shadow overlap diagnostic behaves at its 0.50 floor."
    what_would_verify: "A replay with non-empty pools — the diagnostic has never seen
      one."

unresolved:
  - "The definitive Panel-A/Panel-B confirmatory replays are unrun. Every §7-matched
    read is UNPRODUCED, not merely unverified."
  - "The 81 smoke looks of 2026-08-15T09:19-09:33Z were spent against a dead control
    path. They are append-only ledger facts and must stay; they are void for
    interpretation. The §13 budget itself is undamaged — shard-restricted looks ride
    `names_shard` in the config, so a full-panel run spends its own cells and a true
    re-run of the same universe dedups."

next_actions:
  - "Run the definitive replays from a FULL checkout with data/ materialized (§13/M17
    names the execution site; a sparse tree would truncate data/trial_ledger.jsonl):
    `python3 scripts/entry_radar_replay.py --cache-dir <vendor cache> --panel both`."
  - "Read the refusal census first. A census at or near 100%, or any refusal count >=
    the episode count, means the instrument is broken again — diagnose before reading a
    single result."
  - "Report the recovered control-pool sizes (n_cell distribution, k distribution, the
    §9 overlap share) alongside the §7 reads, since none of them has ever been observed
    non-empty."
  - "Re-check the M14 row-16 >=90% G0-date-agreement floor and the M3 effective-N floor
    against real pools."

do_not_redo:
  - "Do NOT convert the feature panel's `session` column to datetime64. It was
    considered and rejected: `controls.ControlMatch.session` is annotated `date` and is
    populated straight from `candidate_row['session']`, so converting changes the §7
    result object's own type and its serialized shape — a frozen-output change, not a
    repair. The declared conversion boundary is `attach_session_positions`, documented
    as returning `dict[pd.Timestamp, int]`."
  - "Do NOT re-derive whether the reported defect is real. It is, and it is
    input-independent; the reproduction, the ledger receipt, and both mutation controls
    are in research/live_entry_radar/W5_CONTROL_MATCHING_DEFECT_2026-08-15.md §2 and §5."
  - "Do NOT look for corrupted published W5 results. None were ever produced — the
    pre-merge receipt records 'Results seen: NONE' and no w5_results_panel_*.json exists
    on the host."
  - "`assembly.q5_pairs` and `ruler._month_key` were checked and are NOT affected by the
    dtype defect — both already convert defensively (`pd.Timestamp(r['session'])`,
    `pd.to_datetime`). They DID read the wrong session-position map, which this PR
    fixes at the single shared source."

danger_areas:
  - "The refusal branch in `_attach_and_match` catches bare `Exception` per episode. Any
    lookup defect inside it becomes a data row, not an error. The new zero-resolvable
    `ReplayRefusal` guards the session lookup specifically; the vendor-plane branch above
    it has no equivalent structural guard."
  - "`date` vs `pd.Timestamp` is invisible to type checkers here: `Timestamp` subclasses
    `datetime` subclasses `date`, so `isinstance(Timestamp(...), date)` is True while
    `date == Timestamp` is False. Route every session that crosses the panel boundary
    through `_session_key`."
  - "Running the W5 suite or the replay in a SPARSE worktree: `panels.sector_of` reads
    data/universe/membership.parquet, and any write into an omitted tree TRUNCATES the
    committed artifact. The new tests avoid this by monkeypatching the panel/sector
    readers, so they run in a sparse tree; the replay itself does not."
  - "Collecting all of tests/ in a sparse tree raises INTERNALERROR from
    scripts/check_validated_claims.py (missing allowlist under an omitted tree). Run the
    radar files by name instead — that is a sparse artifact, not a regression."

prs: [5777]
discoveries: ["DSC:REFUSAL-BRANCH-HIDES-A-DEAD-LOOKUP"]
---

## Continuation

The §7 control arm has never produced a single matched control in W5's history. That is
the one sentence a resuming session needs: this was not a degradation from a working
state, and there is no prior result to compare against. The first replay run after this
PR is the first one whose control arm is capable of returning anything.

The two defects were one failure mode at two altitudes. `_ctx_session_rows` was
unit-testable and untested; `build_match_context` had no test at all. The primitives
were correct — `tests/test_entry_radar_w5_data.py` already asserted that a bench
calendar must override the panel's own — but nothing tested the wiring between them,
and `panels.session_calendar` had zero callers. When adding to this stack, test the
seam, not only the primitive.

The PR body carries the same evidence table as the receipt doc, so a reviewer who reads
only GitHub gets the mutation controls and the honest limits of the ledger corroboration
(the 5 smoke names span 5 sectors, so their CEM cells would have been empty regardless —
the deterministic reproduction is the proof, the census is corroboration).
