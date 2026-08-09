# Script import-pin burn-down — continuation handoff (2026-08-09)

Continues PR #5046 (`guard(scripts): pin check/ci entry scripts to their own repo
root + regression teeth`), which fixed the 13 CI-guard-family members and left a
**426-entry shrink-only baseline** at `tests/fixtures/script_import_pin_baseline.txt`
covering the wider `scripts/**` population.

## §0 State

| | |
|---|---|
| Shipped | **425 files** across 8 PRs — #5053 #5054 #5056 #5057 #5058 #5060 #5072 #5075 |
| Remaining in the arbiter's affected set | **15** = #5046's own 13 + the 2 grader files below |
| Baseline fixture | **untouched** — still lands with #5046, which was open at hand-off |

The pin, applied after the stdlib imports and before the first top-level repo import:

```python
_ROOT = Path(__file__).resolve().parent.parent   # parents[2] under scripts/<subdir>/
sys.path.insert(0, str(_ROOT))
```

Waves 1–6 were mechanical (a codemod); wave 7 carried the judgment calls; wave 8
picked up an entry script that landed mid-flight from #5071.

## §1 What is LEFT — three items, in order

### 1. Prune the baseline to empty (blocked on #5046 merging)

`tests/fixtures/script_import_pin_baseline.txt` does not exist on main yet, so
nothing in waves 1–8 touches it. **T2 is shrink-only**, so the fixed files simply
drop out of the regenerated set and no wave can break it. Once #5046 merges:

```bash
python3 tests/test_check_script_import_pinning.py --emit-baseline > /tmp/b.txt
diff tests/fixtures/script_import_pin_baseline.txt /tmp/b.txt
```

Write the regenerated list back. **Never extend it** — if a path appears that is
not already there, pin that file instead (that is exactly what wave 8 did). When
the file reaches zero entries, delete it *and* the T2 baseline-read fallback in
the same PR, updating `test_unpinned_entry_scripts_only_shrink` accordingly;
otherwise leave an empty file with T2 enforcing emptiness.

Regenerating against a repo that lacks the arbiter: the classifier derives
`REPO_ROOT` from its own location, so load it out-of-tree and rebind
`REPO_ROOT` / `BASELINE_PATH` rather than committing a copy.

### 2. Two grader files need OPERATOR ratification — do NOT self-serve (R-AUT-7)

```
scripts/grade_thematic.py          (backed out of wave 4, #5057)
scripts/sample_qledger_placebo.py  (backed out of wave 6, #5060)
```

Both are fitness-producing graders whose SHA-256 is registered in
`config/grader_manifest.yml`. Adding the pin drifts the hash and hard-reds
`grader-manifest` plus `tests/test_metabolism_v2{a,b,c}` — this really happened
(wave 4 `ci-pack-2`, wave 6 `ci-pack-2` **and** `ci-pack-3`).

**R-AUT-7** (`research/AUTONOMIC_LOOP_MASTERPLAN_BY_FABLE.md:63`) makes any grader
hash drift a **T2 quarantine event**: OLD-vs-NEW grader over the frozen replay
corpus, fitness delta printed, **operator ratification**.
`docs/HOUSE_LAW_CI_GUARD_SUITE.md` calls it the highest-leverage fence in the
Metabolism — it exists so the loop cannot rewrite its own scoreboard.

A `sys.path` pin cannot change grading arithmetic. That is not the point: *"this
change to the scoreboard is safe"* is precisely the judgment R-AUT-7 reserves for
a human. An agent picking these up unilaterally defeats the fence. The operator
path is:

```bash
python3 scripts/check_grader_manifest.py --regen
```

then inspect the fitness delta vs the frozen replay corpus and ratify in the PR
body, committing the script and the manifest together.

The other three registered graders (`engine/foresight_leadlag.py`,
`engine/theme_placebo.py`, `engine/qledger_falsifier.py`) are outside
`scripts/**` and were never in scope.

### 3. Eighty-one `# noqa: E402` comments sit on the wrong physical line

Waves 1–7 anchored the noqa to the **closing** line of a parenthesised import.
E402 is reported at a logical line's *start*, so a noqa on the closing paren does
not suppress it. **Inert today** — this repo configures no flake8/ruff, so E402 is
not enforced — and deliberately not fixed by force-pushing seven armed PRs through
a starved runner pool. Wave 8 (#5075) already uses the correct anchor. Sweep the
other 81 in the same PR as item 1. Rule: anchor to line 1 when that line can carry
a comment (single-line, or ends with `(`); a backslash continuation cannot, so
fall back to the last line there.

## §2 Things that will bite the next session

- **Adjacent deletions in the baseline fixture CONFLICT.** Verified with
  `git merge-tree`: two branches deleting adjacent contiguous blocks of that file
  do not auto-merge. Prune it in ONE PR, not in parallel waves. (This is why waves
  1–8 touch only `scripts/**` and leave the fixture alone — it made all eight
  independent and conflict-free.)
- **A wrong pin depth satisfies the arbiter.** `_strong_pin` only proves the
  inserted value is *derived from* `__file__`; `parent` instead of `parent.parent`
  passes T1/T2 and still pins the wrong directory. T3 covers only the guard
  family. Gate any bulk change by executing each module's top-level prefix up to
  and including its pin and asserting `sys.path[0]` **is** the repo root.
- **Seven in-function inserts are kept ON PURPOSE** and must not be "cleaned up":
  `audit_qbus.py` (`args.root`), `build_market_structure_page.py` ×2,
  `build_options_command.py`, `build_stage_analysis_page.py` ×2 (a caller-supplied
  `root` parameter), and `research/dump_gate_fires.py` (`data_root`, not a repo
  root at all). The module pin does not replace these; deleting them is a
  behaviour change.
- **Main moves under you.** `scripts/audit_prophet_plan_chronology.py` arrived from
  #5071 mid-burn-down and was *not* in the 426-entry fixture, so it would have made
  T2 fail as an ADDED entry the moment #5046 landed. Re-run the arbiter against
  current main before declaring the baseline empty.

## §3 Bugs the burn-down turned up (all repaired, all real)

- `scripts/append_digest_issue.py` **executed a decoy repo's code** under a hostile
  `PYTHONPATH`; it and `scripts/audit_macro.py` both went **rc=1 → rc=0** run bare
  with no decoy at all — they were already broken.
- `scripts/btc_gate_attribution_phase0.py` pinned `.claude/worktrees/zen-volhard-77003f`,
  a worktree that no longer exists.
- `scripts/commodity_xsec_carry_phase0.py` hardcoded the **primary checkout**, so
  running it from any worktree imported and wrote to the wrong tree.
- `scripts/research/dt_r14_time_control.py` pinned `/private/tmp/esx-ssq`, and built
  `_DATA` from it.
- `scripts/china_policy_events_fc.py` used `Path(".")` — every data path and the
  `sys.path` entry followed the caller's CWD.

All four broken roots were repaired **in place** (the existing variable made
`__file__`-derived) rather than by adding a second `_ROOT` beside them, so the data
and report paths built from them were repointed too. That is a deliberate behaviour
change in each case, called out in #5072's body; in all four the prior behaviour was
broken.

## §4 Not in scope, do not adopt

The base-side `ci-pack-0` red (`tests/test_earnings_seasons.py::…assert 'stale' ==
'ready'`, a fixture date bomb) blocked every armed head including #5046 during this
work. It was owned by four separate heal lanes (#5064, #5065, #5073, #5036) and
landed on main as `c7a834c199b` — all eight waves were rebased onto the healed base
rather than patched. A stale-base red heals by rebase, not by fixing.
