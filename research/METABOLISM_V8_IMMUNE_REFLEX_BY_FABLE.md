# Metabolism v8 — Immune System & Reflex Arcs (the organism heals its environment and executes its own verdicts)

**Status:** RATIFIED design 2026-07-12; ships with this doc + three build waves.
**Owner program:** `autonomic-loop` (extends v4 First Breath, v5 Durability, v6 Lobe Genesis, v7 PR Audit).
**Operator directive (2026-07-12):** "continue working to add additional features and add robustness and enhanced upgrades to truly make this superintelligent."
**Method:** 4-lane parallel file:line census (revert / sensing / meta-learning / immune) + this Fable adjudication.

---

## 0. Executive ruling — the organism senses and plans, but its wires are dead

The census found a consistent pathology: at every point where the loop should ACT on its own
knowledge, the wire is cut. Four exhibits, all verified at file:line:

1. **The revert plan nobody executes.** `verify.py:147-176` emits a `revert_plan` dict
   (`action: git_revert`) on a clean-overfit fitness regression — and an exhaustive grep confirms
   NO code anywhere reads it. Merge is go-live (v7 ruling), but un-merge does not exist. The
   organism can ship a mistake and can *know* it shipped a mistake, and then does nothing.
2. **The CI-red detector wired to null.** `anomaly_monitor.py:376-399` has a `ci_red_streak`
   detector — permanently skipped because `config/metabolism_anomaly.yml:82` sets
   `ci_status_artifact: null`. Meanwhile, TODAY, two main-carried CI reds (blocklist drift +
   a missing test dep) blocked every PR in the repo for hours and THREE separate agents
   independently hand-built the same heal (#2416, #2434, #2435). A sentinel that reads main's
   check runs, classifies the red against known deterministic heal recipes, and opens ONE
   claimed heal PR would have fixed it in minutes with zero duplication.
3. **The verdict that never reaches the ladder.** `verify.py` FALSIFIER_TRIPPED outcomes and the
   lifecycle demotion ladder (`grade_demotion_ladder`, `verify.py:736-868`) are DISCONNECTED —
   the ladder counts `journal_breach()` rows that nothing automatically writes on a tripped
   falsifier. A lobe can fail repeatedly and never demote.
4. **The prior that cannot bite.** `dream.py` computes per-kind hit rates and injects them into
   prompts as *advisory text* (`propose.py:267-278`) — no deterministic code de-ranks a proposal
   class with a proven-bad record. The organism's own experience has no enforcement authority
   over its next idea. And the prior is recomputed from `trial_ledger.jsonl` each cycle — rotate
   the ledger and the organism forgets everything it learned.

**The ruling:** v8 closes the loop between knowing and doing, in three waves — an IMMUNE system
(sense environment sickness, heal known classes, claim the work), REFLEX arcs (execute the
organism's own verdicts: revert plans become revert PRs, tripped falsifiers reach the demotion
ladder, held taps escalate instead of rotting), and a META-LEARNING spine (durable outcome
priors with deterministic de-ranking authority). Everything stays inert behind `AUTONOMY_PAUSED`;
deterministic-first authority throughout (R-AUT-1: LLMs may only de-escalate).

---

## 1. Rulings

### Wave 1 — Immune system (R-V8-1 … R-V8-5)

**R-V8-1 — Main-red sentinel.** New lane (`engine/metabolism/immune.py` +
`scripts/metabolism_immune.py` + `.github/workflows/metabolism-immune.yml`, cron every 2h) reads
main's combined check-runs via `gh api`. A red REQUIRED check on main = an environment infection:
every PR in the repo is blocked. The sentinel classifies the red against a **recipe registry**
(`config/metabolism_immune.yml`) of known byte-deterministic heals:
  - `blocklist-drift` → `python3 scripts/compile_loop_blocklists.py` (detector: check_blocklist_drift.py)
  - `grader-manifest` → `python3 scripts/check_grader_manifest.py --regen` (fenced-grader hand-edit law respected: refuse if F1 doctrinal header would be stripped — see memory `grader-manifest-regen-strips-comments`; the recipe re-adds sha256 lines only)
  - `house-law-docs` → `python3 scripts/check_house_law_registry.py --emit-docs`
  - `template-site-sync` → `python -m scripts.check_template_site_sync --fix`
Recipe runs happen in a FRESH worktree off `origin/main`; the result ships as ONE heal PR per
infection. Unknown red classes → operator insight + Telegram, no auto-action. NEVER touches
IMMUTABLE paths; capability-broker fences apply to the lane like any other.

**R-V8-2 — Claim-marking (the three-agents lesson).** Before opening a heal PR the sentinel
appends a claim row to `data/metabolism/immune_claims.jsonl` (`{red_class, check_name, main_sha,
pr_number, ts}`) and COMMITS it in the heal PR itself. A fresh sentinel run (or any agent
following house law) consults claims first: an open claim with a live PR for the same red class
= skip. Claims expire when their PR closes/merges. This generalizes `data/metabolism/claims.jsonl`
(build-lane file claims, `metabolism_build.py:128-145`) to environment heals.

**R-V8-3 — Immune auto-merge is allowlist-only and armed-only.** A heal PR may be auto-merged by
the sentinel ONLY when ALL hold: (a) `AUTONOMY_PAUSED=false` (double-gated, exact-string), (b) the
red class is in the registry's `auto_merge_allowed` list (byte-deterministic regens only), (c) the
heal PR's CI is green at a fresh head SHA (same `_pr_ci_green_at_sha` discipline as the v7 merge
lane), (d) per-day cap `immune_max_automerge_per_day` (default 2, journal-durable counter — the
R-V5-1 lesson) not exhausted. Otherwise the PR waits for operator/watcher. Paused = sentinel still
SENSES and opens PRs as drafts + alerts, merges nothing.

**R-V8-4 — Lane-health sensors (the asia-close lesson).** The same sentinel run checks, via
`gh api`: (a) cron lanes whose latest run concluded `cancelled`/`timed_out` (the silent-death
class that froze asia data 8 days), (b) Actions queue saturation (runs queued > `queue_stuck_min`
minutes; TODAY's incident: 37 runs queued 45+ min), (c) self-hosted runner offline (any registered
runner with `status != online`), (d) key-pool partial degradation (>50% of pool keys cooling).
Each fires an operator insight + Telegram once per condition per day (dedup via journal); none
takes automatic action. These are pure sensors — display-tier, no gauntlet (context-accrual law).

**R-V8-5 — Wire the dead detector.** The sentinel writes its main-CI observation to
`data/metabolism/ci_status.json` and `config/metabolism_anomaly.yml` gets
`ci_status_artifact: data/metabolism/ci_status.json` — the existing `ci_red_streak` detector
(anomaly_monitor.py:376) comes alive with zero new detector code.

### Wave 2 — Reflex arcs (R-V8-6 … R-V8-9)

**R-V8-6 — Revert plans become revert PRs (bounded, never auto-merged in v8).** New
`scripts/metabolism_revert.py` (cron after VERIFY) scans `data/metabolism/verify/*.json` for
un-actioned `revert_plan` records: for each, it locates the squash-merge commit of the proposal's
PR (journal → PR number → merge SHA via `gh`), runs `git revert` in a fresh worktree, and opens a
**draft revert PR** carrying the DO_NOT_REBUILD row from the plan. Bounded: `max_open_revert_prs`
(default 2); journal-durable actioned-marker per proposal_id so a plan is actioned once. The
revert PR is NEVER auto-merged in v8 — merging reverts through the v7 audit+merge lanes is a
future ruling AFTER the audit gate has live mileage. Measurement-lens law preserved: only
`revert_plan`-action records (clean overfit) are actioned; `operator_tap` holds (regime/estimator
ambiguity) are untouchable by this lane.

**R-V8-7 — Falsifier→ladder bridge.** `scripts/metabolism_verify.py` (the lane), on writing a
FALSIFIER_TRIPPED outcome with clean-overfit triage, ALSO calls `verify.journal_breach(lobe_id,
...)` so `grade_demotion_ladder` counts it. One tripped falsifier = one counted breach row
(health-miss exclusion rules unchanged, R-V2-3). The demotion ladder finally has an automatic
feeder; its output remains docket-items-only (lifecycle never edits charters directly — unchanged).

**R-V8-8 — Held taps escalate instead of rotting.** `tap.py` safe-defaults are IMMUTABLE and
unchanged (`hold_for_review` stays `hold_for_review` — escalation NEVER executes a held plan).
New: the digest lane counts taps held > `tap_reping_days` (default 7) and re-pings the operator
(Telegram + insight); taps held > `tap_park_days` (default 21) park their proposal with an
`operator_tap_expired` insight so the docket is never silently infinite. Parking ≠ executing:
the held plan stays held; only its VISIBILITY escalates.

**R-V8-9 — Regression parks the construction.** On a clean-overfit FALSIFIER_TRIPPED, the verify
lane appends the construction to the build-lane claims file as a `parked_construction` row —
the build lane already consults claims, so the same lobe/sensor/kind construction cannot be
re-built while parked (release requires an ADJUDICATE grant, i.e. a fresh two-key decision).
This closes the census gap "nothing blocks future builds from the same construction."

### Wave 3 — Meta-learning spine (R-V8-10 … R-V8-12)

**R-V8-10 — Durable outcome-prior ledger.** `dream.py` gains an append-only
`data/metabolism/outcome_priors.jsonl`: one row per closed contract at close time
(`{proposal_id, kind, tier, lobe, sensors[], outcome, triage, ts}`). The preference prior is
computed from THIS ledger (all history), not from live `trial_ledger.jsonl` rows — rotating or
pruning the trial ledger no longer lobotomizes the organism. Backfill on first run from whatever
closed rows still exist.

**R-V8-11 — Deterministic de-rank authority (the prior gets teeth).** After the LLM ranks the
agenda, a deterministic post-pass in `agenda.py` applies floors from the outcome ledger: a
`(kind)` or `(lobe, sensor-family)` bucket with `n ≥ 5` and hit-rate `< 0.25` is DEMOTED to the
bottom of the agenda (never dropped — visibility preserved, nulls printed) with a
`prior_demoted: true` flag surfaced in the proposal record and admin console. This is
de-escalation-only authority, mirror-image of R-AUT-1: the deterministic floor may only demote
what the LLM ranked, never promote. Thresholds live in `config/metabolism_budget.yml`
(`prior_demote_min_n: 5`, `prior_demote_hit_rate: 0.25`).

**R-V8-12 — Per-sensor buckets + agenda recall parity.** The prior buckets extend from `kind`
to `(lobe, sensor)` so a killed sensor family suppresses lookalike proposals deterministically
(construction-scoped, consistent with kill-registry law: the SPECIFIC construction demotes; the
search space stays open — a demoted item is still visible and can be re-ranked up by a fresh
two-key adjudication). `agenda.py` additionally calls `recall.recall_lessons()` directly (parity
with PROPOSE) so the FAIL-floor lessons reach agenda ranking even if the orchestrator system
prompt is trimmed.

### Refusals (R-V8-13)

- No auto-merge of revert PRs (future ruling, needs v7 audit-gate mileage).
- No auto-heal for red classes outside the recipe registry — unknown reds are operator work.
- No dag-conformance auto-heal (regen requires judgment about which side drifted — census
  confirmed no `--fix` exists; building one is FORBIDDEN without a fresh ruling).
- Escalation never executes a held tap. Safe-default table in `tap.py` stays IMMUTABLE.
- The deterministic prior may only DEMOTE agenda items, never drop, never promote.
- No new LLM calls anywhere in v8 — every v8 lane is deterministic; the organism's judgment
  stays where it already is (PROPOSE/ADJUDICATE/AUDIT).

---

## 2. Build (three PRs, independently mergeable)

- **PR-V8A (immune):** `engine/metabolism/immune.py`, `scripts/metabolism_immune.py`,
  `.github/workflows/metabolism-immune.yml`, `config/metabolism_immune.yml`,
  anomaly-config wire (R-V8-5), claims file, tests (recipe classify / claim dedup / unknown-red
  insight / paused=draft-only / automerge allowlist+cap+fresh-SHA / lane-health sensors).
- **PR-V8B (reflex):** `scripts/metabolism_revert.py`, verify→ladder bridge, tap escalation in
  digest, parked-construction claims, tests (plan→draft-PR / bounded / actioned-once /
  tap-hold untouchable / breach bridging / park+release).
- **PR-V8C (meta):** outcome-prior ledger in `dream.py`, deterministic agenda post-pass,
  per-sensor buckets, recall parity, budget keys, tests (ledger durability / demote floor /
  never-drop / never-promote / construction-scoped bucket).

Sequencing: A, B, C are collision-free with open PRs (#2377/#2383 touch audit/build/merge only)
and with each other except B+C both touching verify-adjacent files — B owns `verify.py`,
C owns `dream.py`/`agenda.py`; no shared file. All lanes AUTONOMY_PAUSED double-gated where
side-effectful; all counters journal-durable; all failures Telegram-notified.
