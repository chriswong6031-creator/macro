# BioCatalyst — autonomous overnight run brief

**You are the session this brief was written for.** The operator is asleep and instructed:
do **not** ask questions, do **not** wait for approval, work continuously to the end, and leave
everything they need to review in the repo. Make every judgment call yourself, write the
assumption down, and keep going. Never stop early to check in. If something is genuinely
blocked, record why in the final report and move to the next item — do not idle.

## 0 — Load context before touching anything

Read `CLAUDE.md` and `AGENTS.md`. Then read, in this order:

1. `research/BIOCATALYST_SIGNAL_PATH_STRATEGY_2026-08-07.md` — **most important.** Why the
   program is stuck and the four ranked moves that unstick it.
2. `research/BIOCATALYST_CONTINUATION_HANDOFF_2026-08-06_CLAUDE.md` — operational state.
3. `research/BIOCATALYST_PARITY_LEDGER_2026-08-06.md` — the 32-row completion denominator.
4. `research/BIOCATALYST_REMAINING_BUILD_WAVES_HANDOFF_FOR_CLAUDE_2026-08-06.md` — canonical wave map.
5. `research/DO_NOT_REBUILD.md` — standing kills. `DNR:KILL-PHASE3-START-WEIGHT` is live and binding.

If these are not on `main` yet, fetch them:
`git fetch origin claude/biocatalyst-remaining-waves-5704a2` then
`git show origin/claude/biocatalyst-remaining-waves-5704a2:<path>`.

## 1 — Land the open work first

Seven PRs are open, all already reviewed with evidence in their bodies:

| PR | Lane |
|---|---|
| 4796 | design ruling + parity ledger + handoff + strategy (docs only) |
| 4810 | F0-delta reconciliation + closed-beta source manifest |
| 4814 | BC-O1a inert operational persistence + M0a policy |
| 4820 | B1S2a private bounded fixed-cohort transport (dark) |
| 4822 | N0a operating packet producer + N0b allowlisted reader |
| 4825 | v2 acceptance contract + trusted browser verifier |
| 4831 | D0b premium trial product (Screen/facets, Peer Matrix, Change Tape, primitives) |

**MERGE ORDER IS SERIAL AND THIS IS STRUCTURAL, NOT STYLISTIC.**
`tests/test_biocatalyst_deploy.py::test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file`
forces every new `test_biocatalyst_*.py` to be registered in `.github/ci/legacy-jobs.yml` before
it can merge, so every bio lane is compelled to edit the same few lines and **all bio PRs
conflict there**. Local integration proved that block is the *only* cross-lane conflict —
everything else merges clean and the lanes compose (1024 passed vs an 844 baseline, zero
cross-lane regressions).

Procedure: merge one → `git fetch origin main` → rebase the next onto main → resolve that YAML
block as a **union** of test paths (never with a regex over conflict markers; a greedy pattern
corrupted the 3,000-line file once already — take `git show origin/main:<file>` and re-apply) →
push → let checks re-run → repeat.

**#4796 goes first.** It touches no CI file, and #4825's v2 manifest binds the design ruling by
content digest (`design_adjudication_sha256: 33f81f44b7df1f9c2eb7d37ccbeb3b52de762335f9cf902c3ec491dca9493240`,
verified byte-for-byte). Until #4796 is on main, #4825 correctly emits
`product_acceptance_v2.design_adjudication_pending_base`. Heal by rebasing after #4796 lands —
**never** weaken the binding or vendor a copy of the ruling.

Merge only on CONCLUDED checks. The known-spurious "Workers Builds: macro" red X is ignorable.
Do not `--admin` merge to outrun CI. If the runner queue is saturated (it was ~104 deep), arm
`merge-on-green` and move on to §2 rather than idling — the sweeper will land them.

## 2 — Then build, in this order

Full rationale is in the strategy doc; do not re-derive it.

**Move 1 — `BC-O1b` + `M0a` family activation. START THE FORWARD CLOCK. Highest priority.**
Not blocked. Trial outcome families are NCT-keyed and need no ticker. The retrospective store is
look-ahead-contaminated and cannot be cleaned, so forward accrual is the only clean evidence this
program will ever have — every day of delay pushes the earliest promotion date out by a day.
Extend the shipped `BC-O1a` substrate (`engine/biocatalyst/operational_store.py`, PR 4814) with
append-only homes for feature snapshots, forecasts, outcomes, model registrations, evaluation
manifests and contribution traces. Reuse O1a's single-writer, idempotency, correction-lineage and
replay semantics — do not build a second store. Open each family's clock only when its frozen
policy + eligible inputs + writer all exist. Never backfill a "first seen".

**Move 2 — Feed `theme_clinical` from BioCatalyst's PIT plane. Cheapest real win.**
Needs no identity work. `engine/theme_clinical.py` is live and already reaches Neural Web and
Mastermind, but its store is top-100-per-sponsor, look-ahead-selected pre-2019, phase-as-of-ingest.
Supply it point-in-time, correction-aware counts/phase distributions instead. **Keep its authority
block exactly as is** — `is_context_only: True`, "display-tier; never scored", never folded into
`fused_obs_z`. This improves the evidence; it promotes nothing.

**Move 3 — `B1S4` coverage expansion with recorded denominators.** 25 trials → theme scale in
measured epochs, each binding one `discovery_scope.v1`, immutable run + coverage-epoch receipts,
and a recorded coverage denominator with known exclusions. A coverage claim is earned by the
denominator, never by the breadth of a query string.

**Move 4 — A reviewed sponsor→ticker map for the 70 healthcare names**
(`us_sector_health` 59, `obesity_glp1` 14, `big_pharma` 10, `managed_care` 9 — distinct 70).
NOT a general PIT identity service: a bounded curated PR-reviewed lookup with effective intervals,
provenance and an ambiguity review queue. Lawful under W3-C's reviewed-admission rule in a way an
inferred join is not. Unlocks `BC-P1` post-selection context only — BioCatalyst explains a name
*after* Prophet selects it, and never originates or reorders a candidate.

Also open and worth doing if time allows: the Change Tape API cannot serve `before_value` /
`after_value` or a JSON pointer (see the handoff §5) — extend
`engine/biocatalyst/change_tape.py`, the read-model contract, and `app/biocatalyst.py` together,
remembering the tape is served from a **pre-published artifact**, so the publication path changes too.

## 2a — You are NOT alone on this machine. Plan for contention.

A sibling autonomous run, `govrev-autonomous-buildout` (Government Revenue Foresight), fires
**four minutes before you** on the same host. Other sessions run too. This matters concretely,
and the previous session lost time to exactly this:

- **The self-hosted GitHub Actions runners share this host.** Heavy local fan-out slows the whole
  fleet's CI, which slows your own merges. Measured on 2026-08-06: load average **76–87 on 24
  cores**, ~30 concurrent pytest processes, and **104 queued workflow runs**.
- **Do not run the full suite repeatedly, and never hand it to N parallel builders.**
  `pytest tests/ -k "biocatalyst or clinicaltrials"` takes **766 s solo** and inflates far past
  that under contention. Measure the baseline **once yourself**, hand builders the number as a
  constant, scope each builder to the narrowest gate that can see its own regression, and run the
  full suite **once** at integration time. The known-good baseline is **844 passed**.
- **Quiet agents are not stuck agents.** Silence under a long mandated command looks identical to
  a hang. Before diagnosing a stall, check `ps aux | grep -c "[p]ytest"` and `uptime`, and read
  the tail of the agent transcript for a blocked Bash call. A previous session nearly killed six
  healthy builders on this mistake.
- **A contended run can produce a bogus baseline.** One builder reported `109 failed, 735 passed`
  on a tree where three independent measurements found 844–850 passed and zero failures. If a
  regression count looks alarming, re-measure on a quiet machine before believing it.
- **Never cancel or re-run someone else's in-flight `render`, `engine-render` or `daily`** to
  unblock yourself. A long job inside its timeout is not a wedged job.

## 3 — Hard fences (violating any of these fails the work)

- A0/A1 authority. Nothing may originate probabilities, rankings, signals, scores, sizing or
  escalation. Prophet remains the selection owner.
- NCT-only facts do **not** authorize issuer/ticker/sponsor/security joins by inference.
- `DNR:KILL-PHASE3-START-WEIGHT`: ClinicalTrials.gov Phase-3 START is killed as a **scored**
  catalyst leg. Display/context tier only.
- No source activation, no service/timer start, no R2 or production-pointer mutation, no
  prospective-ledger accrual without a verified gate, no alerts/exports, no Prophet wiring.
- Falsifier/refutation language is never front-facing. "validated" in user copy is CI-enforced.
- Model routing: Opus builds and reviews; Sonnet only for mechanical non-code fan-out.
- Ship loop: fresh worktree off `origin/main`, `claude/*` branch, commit → push → PR →
  `gh pr edit <n> --add-label merge-on-green`. Never force-push. Never bare `git stash`.

## 4 — Do NOT do this

Do not build more Wave 4/5/6 product surfaces. Six parity rows already have shipped, tested
backends and no user-reachable surface. More dossiers and lenses against a plane with ~0 coverage
add surface, not capability.

## 5 — Leave this for the operator

Write `research/BIOCATALYST_OVERNIGHT_RUN_REPORT_<date>.md` and commit it, containing:
what merged, what you built and its PR numbers, what you attempted and abandoned **with the
reason**, every judgment call you made and the assumption behind it, anything that needs an
operator decision or credential, and the exact next three actions. Report failures with counts.
If a lane is only partially done, revert or clearly fence the unverified part so nothing looks
finished that isn't.

## 6 — Cannot be finished by any session (do not re-plan these)

- `B1S2c` — operator arming decision + **14 continuous days** of soak. A calendar, not a task.
- `W3` identity — needs an executable versioned PIT contract from a plane BioCatalyst does not
  own. Measured: 2 of 6 shared-plane adapters eligible.
- `C2` / `MKT0` / `EST1` — Capital Structure PIT, licensed market/options, licensed estimates.
  Contracts that do not exist.
- `P3` — deliberately unscheduled. First possible authority is shrink-only.
