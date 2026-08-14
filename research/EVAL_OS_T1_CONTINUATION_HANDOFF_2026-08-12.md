> **COMPLETED 2026-08-14.** This is the historical parking record of 2026-08-12, landed
> verbatim below the line for the program's audit trail. The fix wave that closed it:
> B1/B2/B3 and M1–M4 all closed (B3 by CEO ruling — T1 runs in its own isolated
> `intelligence-registry` legacy job); the ledger waterfall's cross-program hop was
> deleted on measurement (6 of 7 live hops wrong or unearned); fail-closed now exits
> non-zero unconditionally on PR-plane blindness (DEC:EVAL-OS-BLINDNESS-EXITS-BY-PLANE
> records the data-plane cut); every stale shallow-clone churn figure below was
> re-measured on full history (synapse.yml: ~70 commits/14d, not 26). Session record:
> `agentos/handoffs/WS-EVAL-OS-T1-ENGINE-REGISTRY-2026-08-14.md`.

# Eval OS T1 (engine registry) — continuation handoff

**Date** 2026-08-12 · **Branch** `claude/eval-os-t1-engine-registry` (pushed, **no PR**) ·
**Base** `2232b988067` = the merged Eval-OS PR #5471 ·
**Status** NOT SHIPPABLE tonight. Substantially built, three adversarial rounds survived-and-failed,
stopped deliberately. This document is the cold-start record.

---

## 0. Read this first — why it stopped

Three build→verify rounds ran. Each round was reviewed by three independent adversarial lenses;
**all nine verdicts returned `refuted=true`.** The blocker count fell 4 → 3 → 2 and the
architecture converged, but two things made shipping tonight the wrong call:

1. **A blast-radius amplifier.** `scripts/run_ci_pack.py` returns on the FIRST non-zero step
   (`scripts/run_ci_pack.py:1206-1209`), and round 3 moved the two T1 steps to the FRONT of the
   always-on `neural-web` job (`.github/ci/legacy-jobs.yml:1687,1691`) to stop them going dark
   behind earlier reds. That trade is real but it inverts the risk: a T1 red now masks the
   constitution regression, the system-map test, the ETM registry integrity gate and six other
   suites — **for the whole fleet**. A step-level `if: always()` is not available
   (`run_ci_pack.py:56 ALLOWED_STEP_KEYS = {name, run, uses, with}`), so ordering is the only
   lever and neither ordering is safe. This needs its own decision, probably a separate job.
2. **Convergence was not monotone.** Round 3 fixed the failing fail-closed control and
   simultaneously shipped a test that structurally FORBIDS the guard's own fail-closed
   annotation (below). A surface this large — 378 engines, 5 finding codes, 165 tests — is a
   session chain, not a session.

The handoff's required deliverables are DONE and merged (PR #5471). T1 is *optional*
implementation from `research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md`. Nothing downstream is
blocked by parking it here, except T7/T8/T12 which depend on it by design.

---

## 1. A correction to the record — my own error

Round 2's design rested on "data/species/registry.json has ONE commit in its whole history,
therefore it is stable." A reviewer flagged that as a shallow-clone artifact. I verified and
agreed — and then **made the same error in the correction.**

I reported `config/synapse.yml` as "26 commits, ALL 26 inside the last 14 days (~1.9/day)" and
passed that to the builders, which enshrined it in `engine/intelligence_registry.py:34`.

Measured:

```
git rev-parse --is-shallow-repository   -> true
oldest reachable commit                  2026-08-09 16:41:43 +0000
newest                                   2026-08-12 19:27:49 -0700
reachable span                           3.41 days
```

So it is 26 commits in **3.41 days ≈ 7.6/day**, not 1.9/day. **The architectural conclusion is
unchanged and strengthened** — synapse.yml is four times more volatile than I claimed, so
"never pin a committed artifact by equality against it" holds a fortiori. But the rate is wrong
wherever it appears, and any *stability* claim derived from this clone's history is inadmissible.

**Rule for the next session: in this repo, `git log` counts are bounded by a 3.4-day shallow
clone. Never derive a churn or stability claim from them without `git fetch --unshallow` first.**

---

## 2. Done and verified

Commits: `34547e62a2d` → `7dc4a6740ec` → `352d537438b`. Tree clean.

- **Unit of account decided and implemented.** `engine_id = producer::owner_program`, giving
  **378 engines** over the 642 registered artifacts; the partition is total and disjoint, and the
  7 exclusions are DERIVED placeholder-producer tokens (`<MANUAL>`, `<HAND_MAINTAINED>`, …),
  not hand-authored.
- **Defect C-2 fixed.** `authority` ∈ {display, engine_input, user_ranking, gate_size} is
  DERIVED (from `tier`, `scored_path_surfaces`, and a one-hop consumer walk), not curated.
  `site-us-standouts` resolves to `user_ranking` and no longer reads as a decorative chip.
  `authority_evidence` names the rule and artifact that produced every value.
- **Defect C-1 reported.** Artifacts above `display` whose `qual_ladder_ref` is missing or
  unresolvable surface as `AUTHORITY_WITHOUT_EVIDENCE`. A ref resolving to a DIRECTORY is
  refused (`research/` → unresolved), so the backlog cannot be drained by pointing at a folder.
- **Nothing generated is committed.** `data/intelligence_registry.json` (26,330 lines) and
  `docs/MASTERMIND_INTELLIGENCE_REGISTRY.md` are deleted; `git ls-files` confirms. There is no
  drift guard and no `--check` equality mode, because there is nothing to drift against.
  Net diff across the rearchitecture: **−27,038 lines.**
- **Guard fails closed.** Partial blindness prints `COULD NOT LOOK — N input(s) unreadable` and
  names them on the summary line; `--strict` exits 1. An unreadable `config/synapse.yml` prints
  `NOT CHECKED` and exits 1 with no violation count.
- **Selftest 67/67, exit 0, with negative controls that bite.** Validators-accept-everything →
  `FAIL (20/67)`. C-1 derivation deleted → `FAIL (64/67)`, failing exactly the three C-1 controls.
- **165 tests pass**; `check_house_law_registry` (75 laws), `check_synapse_registry` (642, 0
  violations), `check_ci_trigger_closure`, `check_workflow_yaml` (82) all exit 0; 185 legacy jobs
  validate.
- **Corpus-append immunity proven by simulation.** Appending synthetic rows to a COPY of
  `data/qledger/claims.jsonl` leaves violations, engine count and all 222 findings identical.

---

## 3. Broken — fix these before any PR

Ordered by severity. Every one was reproduced by a reviewer with a command.

### BLOCKERS

**B1 — a test forbids the guard's own correct behaviour.**
`tests/test_check_intelligence_registry.py:195` (`test_annotation_volume_is_budgeted`) asserts
`len(warnings) == len(per_engine) + len(aggregated)`. The fail-closed `COULD NOT LOOK`
annotation (`scripts/check_intelligence_registry.py:761-765`) is an extra warning, so **any run
that is correctly blind fails this test.** The test encodes the bug the whole round was meant to
fix. Fix the budget to account for the blindness annotation; do not delete the annotation.

**B2 — an unparseable qledger store reads as "every desk has zero rows".**
`_load_qledger` (`scripts/build_intelligence_registry.py:178-200`) swallows per-line
`json.JSONDecodeError` and returns an empty mapping, which is indistinguishable from a
successfully-read store where no desk has rows. Same "could not look → looked and found nothing"
substitution as B1, on a different input. It must count parse failures and mark the input
INCOMPLETE.

**B3 — blast radius (see §0).** T1's two steps are first in the always-on `neural-web` job, and
`run_ci_pack.py` returns on the first non-zero step, so a T1 red masks nine sibling suites.
Recommended: give T1 **its own legacy job**, so neither ordering problem exists. Confirm the job
count stays under the narrow-diff ceiling afterwards (it was 185 with T1 folded in).

### MAJORS

**M1 — two tests assert on LIVE `config/synapse.yml` contents.**
`tests/test_check_intelligence_registry.py:329` asserts `excluded_ids` is non-empty; `:289`
asserts the live C-1 backlog is non-empty. Both red when a sibling PR changes synapse.yml — and
`:289` is perverse, because **draining the C-1 backlog is the stated deliverable**, so succeeding
reds the test. Move both to fixtures.
Note `:361` (`test_no_test_in_this_program_asserts_on_live_synapse_contents`) is supposed to
catch exactly this and does not: its needle set misses both call shapes.

**M2 — `ledger` waterfall rule 4 over-reaches.** `engine/intelligence_registry.py:562` hops
"EVEN CROSS-PROGRAM" to any consumer whose module path matches `/grade|ledger/i` and adopts that
module's ledger as the engine's own, producing wrong `ledger` and therefore wrong
`graded_by_design` on named live rows. Tighten the hop or demote its confidence.

**M3 — `graded_by_design` is still a filename heuristic**, and the disclosure understates it:
the docstring says "filename contains ledger" while the regex
(`engine/intelligence_registry.py:496 _LEDGER_PATH_RE`) matches anywhere in the path. Either make
the disclosure exact or drop the derived claim. It is currently right on 41 of 106 sampled rows.

**M4 — the fail-closed exit is a mode nothing runs.** CI invokes `--selftest` then the bare
guard; `--strict` is deliberately not passed, so a run blind on qual_ladder / species / claims /
article2 exits 0 and the job is green. Either run `--strict` in CI or stop describing fail-closed
as an enforced property.

### MINORS
`AUTHORITY_WITHOUT_EVIDENCE` — the law's primary deliverable — is the only finding code never
written to plain stdout (`check_intelligence_registry.py:743,757`), so C-1 detail lives only on
the annotation channel · an unparseable overlay or synapse crashes with a bare traceback instead
of the documented fail-closed summary · `_article2_modules()` converts any transient import
problem into "no article-2 modules", making the gate nondeterministic · the `unchecked` epistemic
null still counts as evidence in one C-1 path · stale self-descriptions reference a removed
`--proposals` mode.

---

## 4. Not started

`config/intelligence_registry_overlay.yml` curation. `output_class` is REQUIRED only for the 89
engines that trip the evaluation gate (authority > display, or any artifact in
{shadow, scored, confirmer}); the rest default to null with reason `not_required_display_only`.
Nobody has filled in those 89 yet. This is deliberate — the derivation had to be trustworthy
first.

---

## 5. Exact next command

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/eval-os-t1-engine-registry"
git fetch --unshallow            # §1 — do this BEFORE any churn/stability claim
git log --oneline -3             # expect 352d537438b at HEAD
python3 scripts/check_intelligence_registry.py --selftest    # expect 67/67, exit 0
python3 scripts/check_intelligence_registry.py               # expect 378 engines, 0 structural
python3 -m pytest tests/test_intelligence_registry.py tests/test_check_intelligence_registry.py -q
```

Then fix B1 → B2 → B3 → M1 in that order; B3 is a CI-topology decision, not a code fix, and
should probably be made by the operator or a session that owns `legacy-jobs.yml`.

Do **not** rebase this branch onto a moved main without re-running the full gate list; and do not
open a PR until B1–B3 and M1 are closed, because B3 in particular risks the fleet, not just this
branch.

---

## 6. What this cost, honestly

Three rounds, 22 agents, ~3.4M subagent tokens, ~4.5 hours wall clock, nine adversarial verdicts,
all refuted. The adversarial layer earned its cost several times over: it caught a scheduled
fleet-wide red, a guard that printed `0 integrity violation(s)` while blind, a C-1 gate that
cleared on any non-empty string, a test that forbade the guard's own correct behaviour, and two
separate incomplete-history errors — one of them mine (§1).

The lesson for the V1 plan: **T1 is the keystone and it is also the largest single task in the
plan.** `MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md` should be amended to split it — T1a the
derivation library, T1b the guard, T1c the CI wiring — because the CI wiring is where two of the
three rounds actually died, and it is independent of whether the derivation is correct.
