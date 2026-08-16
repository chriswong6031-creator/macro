---
workstream: WS:PROPHET-CONDITIONAL-FUSION
title: Prophet Conditional Fusion — deep audit and W3 build handoff
date: 2026-08-16
session: prophet-fusion-deep-audit-w3-build-plan
model: codex
ended_because: complete
prs: ["#5807"]
repo: mastermindx-market-intelligence/macro
main_at_audit: 021553985cbe6bf950413c7cb10fc302d05a9633
mission: >
  Reconcile the real post-W2B state of Prophet Conditional Fusion, identify stale records
  versus real blockers, harden the W3 design before prospective outcome data exists, and
  leave an implementation-grade sequence that a cold new session can execute without
  re-litigating settled C1 decisions or contaminating the forward race.
state_before: >
  C1/us_prophet_v3 is live-accepted (Pages artifact of run 31913143619; #5784). W2
  machinery merged as #5700 but the workstream still labelled w2 in_progress. W3 is
  NOT built. Durable paired-race N is 0 because no candidates-store commit has landed
  since #5769 and the first accepted v3 board was Pages-only after engine push failure.
changed:
  - path: agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-W3-BUILD-HANDOFF.md
    what: "Durable post-W2B deep-audit handoff: reconciled W2/W2B/C1 status, stale vs
      real blockers, W3A-W3D sequence, prereg requirements, and do-not-redo. This
      follow-up makes the record schema-valid (model/ended_because enums plus the
      required verified/unverified/next_actions blocks) without changing the audit body."
verified:
  - claim: W2 machinery PR #5700 is merged
    command: "gh pr view 5700 --json state,mergeCommit"
    result: "MERGED 2026-08-15T01:18:37Z as 6adf8b7287856c7ac02e3a71cbb26a0c5771cae7"
  - claim: workstream YAML still labels w2 in_progress after that merge
    command: "rg -n 'id: w2' -A3 agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md"
    result: "status: in_progress under id: w2; w2b is already done"
  - claim: #5769 already shipped the prophet_shadow_* store family
    command: "gh pr view 5769 --json state,mergeCommit"
    result: "MERGED 2026-08-16T02:43:09Z as 0233445657e8a6e40f3f5260d9cad7af4bb3e456"
  - claim: DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY already exists
    command: "test -f agentos/decisions/DEC-US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY.md"
    result: "present; the remaining work is citing it from the workstream, not minting it"
  - claim: #5705 already replaced settlement+10 calendar days with the 8th NYSE session
    command: "gh pr view 5705 --json state,mergeCommit"
    result: "MERGED 2026-08-15T07:44:38Z as 7811075a4dedd3172176866e0d588f83a3b6dc41"
  - claim: Fusion registry/arena still carry the retired +10-calendar refusal
    command: "rg -n 'BACKTEST_LAWFUL_STATUSES|settlement \\+ 10' scripts/prophet_fusion_arena.py research/prophet_fusion/families.yml"
    result: "BACKTEST_LAWFUL_STATUSES = frozenset({PIT_OK}); families.yml still says
      knowable_date (= settlement + 10 calendar days) and BACKTEST ADMISSION DEFERRED"
  - claim: families.yml still declares bare canonical columns as champion_baseline
    command: "rg -n -A16 '^champion_baseline:' research/prophet_fusion/families.yml"
    result: "prophet_score, score_rank, display_rank, featured, and the ten prophet_*
      leg columns remain under a timeless champion_baseline list"
  - claim: no candidates-store commit has landed since #5769
    command: "git log --oneline 0233445657e8a6e40f3f5260d9cad7af4bb3e456..origin/main -- data/us_prophet_rank/candidates/"
    result: "empty. Latest candidates-path commit on origin/main is 071017a30b99
      (2026-08-14), before #5769. W3 durable paired-race N remains 0."
unverified:
  - claim: the first post-merge nightly's Pages board still matches the 14/14 acceptance
    what_would_verify: "re-fetch the Pages artifact of run 31913143619; already closed
      by agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-ACCEPTANCE.md"
  - claim: C2 still needs 91 graded dates / 67 more than held
    what_would_verify: "re-run the #5700 C2 harness against the current graded frame;
      the 24/91 figure is a dated distance receipt, not re-measured in this session"
unresolved:
  - "W3 is not built. Start PR-3A only: AgentOS reconciliation, definition-aware
    baseline semantics, #5705 PIT integration, and freeze W3_RACE_PREREG.md before
    any forward outcome read."
  - "Registry baseline-role drift: bare champion_baseline names the wrong semantic
    object on a v3 row (DSC:CHAMPION-BASELINE-COLUMNS-CARRY-THE-CHALLENGER)."
  - "No durable post-#5769 paired stamp yet. Do not backfill the Pages-only night."
  - "#5742 availability/push contention remains external; keep the fail-closed
    checkpoint fence."
  - "Workstream landmine still carries pre-#5769 task_8c904665 / shadow-legs-null
    wording. Reconcile in W3A; do not copy shadow values into canonical prophet_*."
  - "C2 commissioning is data-gated, not a code project. Do not rebuild #5700."
next_actions:
  - "PR-3A only, in a fresh session after this record lands: reconcile AgentOS
    status/landmines/decisions (w2 done/#5700; cite DEC:US-SHADOW; drop stale
    task_8c904665 landmine)."
  - "Make baseline roles definition-aware in research/prophet_fusion/families.yml
    and pin the role-swap mutation in tests."
  - "Reconcile pit_settlement with #5705 in families.yml + prophet_fusion_arena.py
    + tests; keep shallow-depth caveats."
  - "Write research/prophet_fusion/W3_RACE_PREREG.md with a numeric honest-N floor
    and an unambiguous adverse tripwire. Do not inspect forward outcome deltas."
  - "Stop after PR-3A. PR-3B is a later session."
do_not_redo:
  - "Do not re-litigate C1 adoption. us_prophet_v3 is canonical."
  - "Do not copy prophet_shadow legs into canonical prophet_* columns on v3."
  - "Do not create a second board-definition row for the shadow."
  - "Do not stamp shadow on a degraded us_prophet_v2_fallback night."
  - "Do not backfill the lost Pages-only v3 night into the candidates store."
  - "Do not count retries of one as_of as independent nights."
  - "Do not rebuild C2 or relax the fold law."
  - "Do not build a second v2 scorer or a second grader for W3."
  - "Do not weaken #5742's fail-closed checkpoint fence."
  - "Do not bump SELECTION_ERA for the C1 rank change."
danger_areas:
  - "prophet_score historically meant the v1/v2 heuristic and now means C1 on v3.
    Always pair with board_definition. Shadow values live under prophet_shadow_*."
  - "A board can ship via Pages while failing to reach git. W3 counts durable paired
    stamps, not what a browser served."
  - "Retries of a stale session are not new observations. Key by session/as_of."
  - "Live C1 extracts several members from the board row that the candidates store
    does not preserve in the same raw form. Never answer 'what C1 used tonight'
    from a candidates-only replay."
  - "This file's body is the W3 charter. It is not W3_RACE_PREREG.md and does not
    freeze the numeric honest-N floor or the tripwire. Do not read outcomes from it."
---

# 0. Executive verdict

**The live C1 product milestone is complete; the Conditional Fusion program is not.**

The correct program state is:

- W0 / PR-0: done (#5593)
- W1 / PR-1a: done (#5604)
- W1b / PR-1b: done (#5667)
- W2 / PR-2 machinery: done (#5700), despite stale AgentOS `w2: in_progress`
- W2b / Chairman override + live C1: done (#5753 + live acceptance #5784)
- W3: todo — build has not landed
- W4-W7: todo and depth/dependency gated

**Do not reopen C1 adoption.** `us_prophet_v3` is the canonical US ranker by settled decision.
W3 is a prospective guardrail, structural diagnostics, and coverage-drift program. It has no
promotion/reversion arm.

The immediate objective is not another model. It is to make the forward evidence plane
correct, durable, semantically unambiguous, and impossible to over-read.

# 1. Reconciled truth: what changed after the prior handoffs

## 1.1 W2 is merged; its `in_progress` status is stale bookkeeping

PR #5700 merged as `6adf8b7287856c7ac02e3a71cbb26a0c5771cae7`. It delivered the C2
machinery, redundancy/estimability analysis, variance-floor law, and governed family table.
The real-frame C2 fit correctly refused because the 24-date graded frame cannot satisfy the
frozen fold law; 91 graded dates are required for the first lawful fold, 67 more than were
held at that measurement.

The workstream YAML still labels W2 `in_progress`. Correct this to `done`, but preserve the
separate fact that **real C2 commissioning is data-gated and has not happened**.

## 1.2 W2B live acceptance is complete

The first authoritative post-merge nightly, run 31913143619, built a canonical
`us_prophet_v3` board over 71 rows and passed the 14-item live acceptance surface:
canonical definition stamps, fusion receipt, same-row `us_prophet_v2_shadow`, no silent
fallback, no degradation, and zero unscored rows.

This accepted the ranker, not the session freshness or git delivery path.

## 1.3 The old “shadow legs are still broken” item is already resolved

PR #5769 merged as `0233445657e8a6e40f3f5260d9cad7af4bb3e456` and made the retired v2
scorer accrue under its own explicit 13-column family:

- `prophet_shadow_definition`
- `prophet_shadow_score`
- `prophet_shadow_score_rank`
- `prophet_shadow_{signal,entry,edge,runway,quality}`
- `prophet_shadow_{signal,entry,edge,runway,quality}_points`

The canonical `prophet_*` five-leg columns deliberately remain null on v3 because C1 does not
have the retired five-leg decomposition. That null is the correct attribution, not a bug.

The 2026-08-16 acceptance handoff and the workstream landmine still carry the pre-#5769
“task_8c904665 / shadow legs go null” wording. Those records are stale and must be
reconciled in W3A rather than acted on.

## 1.4 The more dangerous baseline-semantics drift is still real

`research/prophet_fusion/families.yml` still declares these as `champion_baseline`:

- `prophet_score`
- `score_rank`
- `display_rank`
- `featured`
- the ten `prophet_{leg}` / `_points` columns

That vocabulary was true when v2 was champion. On a v3 row:

- `prophet_score` = canonical C1 fusion score
- `score_rank` / `display_rank` = canonical C1 rank
- `featured` is the published board result under canonical order
- canonical five-leg columns are null
- retired v2 score/rank/legs live under `prophet_shadow_*`

A null announces a missing quantity. A column whose meaning silently changed is worse.
**W3 must fix the registry semantics before reading a forward race.**

Do not solve this by copying shadow values into the old canonical columns. That would
permanently misattribute v2 arithmetic to v3 in an append-only store.

## 1.5 Short-interest producer law is fixed, but Fusion still carries the old refusal

PR #5705 merged as `7811075a4dedd3172176866e0d588f83a3b6dc41` and replaced the unsafe
`settlement + 10 calendar days` rule with the 8th NYSE session after settlement, floored by
stored `knowable_date` and by `capture_date`.

But current Fusion records/code are still stale:

- `families.yml` still describes +10 calendar days and says backtest admission is deferred.
- `scripts/prophet_fusion_arena.py` still has `BACKTEST_LAWFUL_STATUSES = {pit}` and
  explicitly excludes `pit_settlement` for the already-fixed reason.

This is an integration residue, not a reason to reopen #5705. Reconcile it in W3A. Keep the
separate depth warning: the committed historical series is shallow and should not be allowed
to masquerade as inferential depth merely because the PIT status becomes lawful.

## 1.6 W3 durable paired-race N is still zero

#5769 created the correct shadow columns, but as of this audit there have been **no commits**
to `data/us_prophet_rank/candidates/` since #5769. The accepted v3 night built and published
to Pages, but the engine failed the checkpoint/push path; the candidate-ledger day was lost.

Therefore:

- do not count the Pages-only acceptance run as a W3 forward-race observation;
- do not backfill it;
- do not count repeated builds of the same `as_of` as multiple sessions;
- W3’s first prospective observation begins with the first **durably committed**
  `us_prophet_v3` candidate stamp that also carries non-null
  `prophet_shadow_definition=us_prophet_v2_shadow` and `prophet_shadow_score_rank` on the
  canonical buy population.

# 2. The main design improvement: split W3 into four bounded subwaves

Treat the existing W3 re-cut as the charter and split implementation into PR-3A through
PR-3D. Do not make one giant W3 PR.

## PR-3A — semantic reconciliation + preregistration

**Purpose:** make it impossible for later code to read the wrong columns or choose a rule
after seeing outcomes.

No forward outcome comparison is allowed in this PR.

### Required changes

1. **Reconcile AgentOS/workstream truth.**
   - `w2: done`, with #5700 recorded.
   - keep `w2b: done`.
   - keep `w3: todo` until instrumentation is actually live-accepted.
   - add `DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY` to workstream decisions.
   - remove/supersede the stale `task_8c904665` landmine; record #5769 as the resolution.
   - keep #5742 as external availability debt, not Fusion logic debt.
   - carry the real unresolved items only.

2. **Make baseline roles definition-aware in `families.yml`.**

   Recommended shape:

   - `published_ranker_output` — canonical published score/rank fields, interpreted under
     `board_definition`.
   - `retired_shadow_output` — `prophet_shadow_*`, valid only when
     `board_definition=us_prophet_v3` and shadow definition is `us_prophet_v2_shadow`.
   - `legacy_v2_decomposition` — the ten canonical leg columns, valid on historical v1/v2
     and explicit fallback rows, null by design on v3.
   - `published_board_output` — `featured` and other board consequences that are not a
     shadow comparator.

   If schema compatibility requires retaining `champion_baseline`, make it a
   definition-keyed mapping instead of one timeless list. The W3 reader must never infer
   comparator identity from a bare column name.

3. **Reconcile short-interest PIT integration.**
   - update stale +10-calendar prose to #5705’s current producer law;
   - admit `pit_settlement` to backtest-lawful statuses only after the existing #5705
     tests/receipts are referenced;
   - preserve shallow-depth and basis-mixing caveats;
   - do not claim short interest is estimable merely because it is PIT-lawful.

4. **Create `research/prophet_fusion/W3_RACE_PREREG.md` before any result read.**

   The current re-cut still has underspecified decision details. The prereg must freeze:

   - population: same canonical buy population, paired row only;
   - canonical side: `prophet_score` / `score_rank` on `board_definition=us_prophet_v3`;
   - comparator side: `prophet_shadow_score` / `prophet_shadow_score_rank` with
     `prophet_shadow_definition=us_prophet_v2_shadow`;
   - explicit exclusion of degraded/fallback nights;
   - start boundary: first durable post-#5769 paired stamp, not the override date;
   - horizons: H=10 first; H=63 only where the existing class/episode law requires it;
   - exact outcome column and benchmark for every metric;
   - exact sign convention for rank-IC so “higher is better” is unambiguous;
   - top-N definition (`N=30`) and how ties are handled;
   - exact honest-N floor. The re-cut says “registered floor” but does not currently
     provide a numeric floor; it must be fixed before outcomes are read;
   - exact adverse-tripwire rule: which metric is primary, whether the secondary metric
     is confirmatory or a non-inferiority condition, and what confidence criterion opens
     an investigation;
   - temporal-dependence treatment for overlapping H=10 outcomes. Date pairing alone
     handles cross-sectional correlation but not overlap across adjacent sessions. Freeze
     the session-block/HAC treatment now and keep the t-referenced instrument; never fall
     back to a normal approximation because N is small;
   - missing-session law: gaps remain gaps; no historical reconstruction of shadow ranks;
   - one grader only: both rank columns join the same ticker-level grade row;
   - no promotion arm, no automatic reversion, no C2 trigger.

### Recommended statistical shape (proposal, not yet ratified)

Use one primary adverse tripwire rather than an after-the-fact OR across several metrics.
A clean choice is the paired H=10 delta in date-level rank-IC, with top-30 mean excess as a
secondary safety read. Require an adverse confidence interval, not a point-estimate lead,
and account for H=10 overlap across nearby dates. This is a recommendation to freeze in
PR-3A; it is not existing program law until the prereg says so.

### PR-3A acceptance

- no outcome metric printed or inspected;
- AgentOS validates;
- registry tests prove v3 canonical and v2 shadow roles cannot be swapped;
- backtest PIT tests pin the #5705 rule and still refuse snapshot/forward-only features;
- `W3_RACE_PREREG.md` contains a numeric read floor and unambiguous tripwire;
- no live rank/gate/featured/plan behavior changes.

# 3. PR-3B — exact structural diagnostics (Lane B + Lane C substrate)

**Purpose:** measure what moves the C1 order and whether its evidence plane is healthy,
without using outcomes.

## 3.1 Implement exact LOFO, not tie-share proxies

The authoritative diagnostic is leave-one-family-out displacement with the admitted member
set held fixed.

For every family, record at least:

- rows carrying a family contribution;
- distinct exact family-score values;
- modal value and modal share;
- dispersion;
- mean absolute rank displacement;
- max absolute rank displacement;
- rows moved;
- top-30 churn.

### Load-bearing rules

- Hold the original admission/floor decision fixed. Removing F4 must not cause another
  member or family to be re-admitted/rejected.
- Preserve the canonical order key: stage bucket first, then scored-before-unscored, then
  ablated score, then ticker. Do not compare raw fusion-score order while ignoring stage.
- Preserve null semantics. If ablation leaves a row with no family, it becomes unscored;
  never coerce to zero.
- Use exact in-memory family scores, not the 2-decimal display contribution, when computing
  displacement.
- Tie-share remains a descriptive field only. The first live read already proved it can
  misrank actual ordering contribution.

## 3.2 Extend the floor receipt into a full member census

Current `Admission` keeps detailed measurements for dropped members but does not expose the
same coverage/variation measurements for admitted members. Lane C is better if every member
has a nightly row:

- member
- family
- status: voting / below_presence / vote_inert / collapsed_duplicate / absent
- non-null coverage
- distinct-value count
- variation share
- threshold used
- source/staleness basis where available

This makes “near threshold and drifting” observable before it becomes a stand-down event.
It is outcome-blind and therefore safe to publish immediately.

## 3.3 Extend the board-level fusion receipt

Add structural diagnostics to the board’s existing fusion receipt, but **do not add new
persistent writes to the engine critical path**. The engine may compute/stamp the compact
receipt; durable W3 history should be committed by the already-separated Prophet ledger job.

The receipt should include:

- full member census;
- family LOFO diagnostics;
- active/abstaining families;
- rows scored/unscored;
- exact floor version/thresholds;
- a construction/schema version for W3 diagnostics.

## 3.4 Tests/mutations

At minimum:

1. Removing F1 changes order on a planted split even when F1 has high tie share.
2. A near-constant event family can pass the feature-only variance floor yet have small
   LOFO displacement; the two concepts stay separate.
3. Recomputing floors after removing a family reds a test.
4. Ignoring stage buckets reds a test.
5. Null-as-zero reds a test.
6. A degraded/fallback board produces no W3 shadow structural observation.
7. Outcome columns injected into the input cannot affect LOFO output.
8. Row input order does not affect diagnostics.
9. Exact full-model rank reconstructed by the diagnostic path matches published canonical
   rank before any ablation.

# 4. PR-3C — prospective paired forward ledger (Lane A) + nightly wiring

**Purpose:** create the durable C1-vs-v2-shadow record without a second scorer and without a
second grader.

## 4.1 Source planes

### Lane A — candidates store + one shared grader

Use:

- `data/us_prophet_rank/candidates/`
- `data/us_prophet_rank/grades/` through `engine.us_prophet_grades.load_grades`

Filter paired rows to:

- `board_definition == us_prophet_v3`
- canonical `prophet_score` and `score_rank` non-null
- `prophet_shadow_definition == us_prophet_v2_shadow`
- `prophet_shadow_score` and `prophet_shadow_score_rank` non-null
- same `stamp_date`, ticker, population and shared outcome row

Do **not** create a second v2 replay. Production already stamped the comparator.

Do **not** create a second outcome row for the shadow. The decision accepting paired-row grain
is conditional on one shared population and one shared ticker-level outcome.

### Lane B/C — committed board artifact + fusion receipt

Use the same committed session’s actual v3 board/fusion receipt for structural diagnostics.
Do not reconstruct all live C1 members from the candidates store: the store currently carries
some but not every raw member exactly as `extract_members()` consumed it. Examples:

- candidates has `alpha`, `tier_cascade`, `gex_confirm_verdict`, `sue_z`;
- live C1 also consumes `off_high`, the derived `sue_fresh`, `smartmoney_add`,
  `insider_cluster`, and `news_burst` from the board/graded-board plane.

A candidates-only LOFO replay would therefore risk becoming a different ranker. The safe
pattern is: compute exact structural diagnostics in the live fusion pass, stamp them in the
receipt, then accrue that compact receipt after the committed board is available.

## 4.2 Durable W3 store

Recommended sibling-file layout:

```text
data/us_prophet_rank/w3/
  paired/YYYY-MM/YYYY-MM-DD.parquet
  family/YYYY-MM/YYYY-MM-DD.parquet
  coverage/YYYY-MM/YYYY-MM-DD.parquet
  status.json
```

Use daily immutable parts like the existing grade store. Earlier parts are never rewritten.
Key rows by the observation they actually represent, not workflow run IDs.

Suggested paired-row fields:

- `stamp_date`, `ticker`, `board_definition`
- `selection_era`, `anchor_era`, `stage`
- canonical score/rank
- shadow definition/score/rank
- `horizon`, outcome, benchmark, fill/mark dates, `graded_asof`
- source artifact fingerprint / registry version

Suggested family-row fields:

- `stamp_date`, family, active/abstaining
- rows contributing, distinct values, mode/share, dispersion
- LOFO mean/max/rows-moved/top30-churn
- construction/registry fingerprint

Suggested coverage-row fields:

- `stamp_date`, member, family, status
- coverage, variation share, thresholds, reason

## 4.3 Workflow placement

Wire W3 accrual into `.github/workflows/daily.yml` inside the existing
`us_prophet_ledgers` job, **after `grade_us_prophet_candidates --nightly` and before the
job’s commit step**.

Why this placement is better:

- that job already exists specifically to keep forward ledgers off the engine’s fragile
  critical path;
- it checks out committed main after engine/scan work;
- it already owns the Prophet forward-grade store and nightly-only lane sentinel;
- a W3 failure can red/alert its own measurement job without changing the live board;
- no new engine-side git write or push race is introduced.

Keep the writer nightly-only, idempotent, and append-only.

## 4.4 Liveness and gap receipt

W3 must distinguish four states:

1. `paired_accrued` — valid v3 + shadow row exists and is durably committed;
2. `unmatured` — pair exists but requested horizon has no grade yet;
3. `degraded_or_unpaired` — fallback/no shadow; excluded by law;
4. `session_missing` — expected session never reached the durable store.

Do not turn 3 or 4 into zero returns, ties, or replayed rows.

A retry of the same `stamp_date` is the same session, not another observation. Keep-first by
`(stamp_date, board_definition, ticker[, horizon])`; if a different payload attempts to
rewrite a frozen key, fail loudly and print both fingerprints.

# 5. PR-3D — live acceptance and display surface

PR-3D closes W3 instrumentation only after one real post-merge nightly proves all three
lanes write correctly.

## Immediate structural acceptance (does not wait for H=10 maturity)

On the first successful durable paired v3 night:

- candidate buy rows carry canonical v3 score/rank and v2-shadow score/rank;
- off-board rows keep shadow fields null;
- fallback night behavior remains excluded/no shadow;
- family LOFO and member census persist for the same `stamp_date`;
- board `as_of`, candidate `stamp_date`, and structural ledger date agree;
- no duplicate session from retries;
- W3 store is committed by the Prophet ledger job;
- no rank/gate/featured/plan consumer imports the W3 store.

That same night can finally close the inherited **§13.0 live-accrual closure** if the fresh
curated stamp and schema-union checks pass.

## Forward-race display before lawful read

Until the preregistered maturity + N floor is satisfied, the user-visible/research surface
must print only status such as:

- paired sessions accrued: N
- matured H=10 sessions: N
- first paired stamp: date / pending
- first lawful read: date / pending
- missing/degraded sessions: N + reasons

It must **not print rank-IC deltas, top-30 alpha deltas, p-values, or a “leader.”**

Lane B/C structural tables can publish immediately because they do not use outcomes. Label
them structural/order diagnostics, not predictive evidence.

# 6. Open debts after reconciliation — prioritized

## P0 — blocks a trustworthy W3 read

1. **W3 prereg underspecification.** Numeric honest-N floor and exact adverse-tripwire rule
   are not yet frozen. Fix before reading outcomes.
2. **Registry baseline-role drift.** Bare `champion_baseline` names the wrong semantic object
   on v3. Fix before W3 reader code.
3. **No durable post-#5769 paired stamp yet.** This is an accrual condition, not something to
   synthesize.
4. **#5742 availability/push contention.** External to Fusion logic but it destroys sample
   accrual. Keep the fail-closed checkpoint fence; do not make W3 “green” by weakening it.

## P1 — should ride W3A / first live acceptance

5. **Short-interest Fusion integration residue.** Producer fixed by #5705; arena/registry
   still describe and enforce the retired refusal.
6. **`sue_z` registry re-home.** `us_context_vector` now stamps `sue_z`, but the registry
   correctly waited for a real post-PR-1a stored row. After the first durable stamp proves
   the column exists, re-home it; do not create a phantom membership before then.
7. **Acceptance/workstream document drift.** Latest records contradict #5769 and #5705.
   The next durable handoff must supersede/reconcile, not merely append another stale list.

## P2 — broader program-quality debts, not C1 blockers

8. **Insider collector serving-dead.** `insider_cluster` cannot support a fresh-data claim
   while the collector is stopped at 2026q1. Repair producer and require observed fresh
   accrual before removing `serving_dead`.
9. **`turnover_pctile_60d`.** Current context-vector code still stamps it as `None`; do not
   assume “mid-Aug self-heal” happened merely because time passed. Either wire the now-deep
   source or keep it explicitly unavailable.
10. **F3 theme/relay coverage.** The registry records theme payload below floor and relay dark
    on the measured frame. W3 Lane C should show whether this changes; fix producer coverage
    before any router claim learns “missingness” as a theme state.
11. **Cycle/signal-class telemetry.** The grader’s class split is only meaningful once the
    candidates store actually carries the cycle vocabulary. This becomes important before
    class-conditional C3/C4/C5 claims.
12. **PR-1a advisories A3/A4/A5/A7 and other explicit carry-forwards.** Re-census them rather
    than blindly copying old handoff prose; close what later PRs already resolved.

# 7. C2 is a data checkpoint, not the next code project

Do not rebuild C2. #5700 already shipped the machinery and proved it on synthetic depth.

At the first date where the frozen fold law becomes satisfiable:

- run the existing C2 harness unchanged;
- preserve the registered grid, nonnegative constraints, feature-family budget, PIT gates,
  t-referenced family table and multiplicity law;
- compare C2 against C1 and every required simpler rung only on lawful folds;
- if the first fold still refuses because the real frame/embargo differs from the old date
  forecast, report the new distance-to-depth; do not relax the fold law.

The earlier measurement was 24 graded dates held / 91 needed. That number is a distance
receipt, not a calendar promise.

# 8. W4-W7 buildout after W3

## W4 — C3 date-grouped ranker

Do not start merely because W3 code is complete. Require the masterplan depth gate:

- >= 6 months of graded H=21 inside one compatible selection era;
- >= 50 episodes per claimed cell;
- lawful C2 comparison surface available;
- date-grouped training;
- name-disjoint OOS, capacity budget and name-permutation null from C3 upward.

Recommended workstream correction: make W4 depend not only on `w3` but also on a lawful real
C2 commissioning checkpoint. It will probably be naturally satisfied by W4’s deeper data
floor, but the dependency should be explicit.

## W5 — C4 contextual router

Only after W4 + Stock Identity interface/depth gates.

- consume Stock Identity fingerprint/epoch interfaces; do not build a rival identity stack;
- every routing axis must pass estimability;
- no per-ticker or per-class outcome audition;
- global mapping / behavioral-neighbor pooling / empirical-Bayes shrinkage only;
- F6 macro state is a router/context axis, never a cross-sectional family vote.

## W6 — C5 multi-head

Selection, asymmetry, fragility, confidence, and Entry only where the sibling ruler is mature.
Do not proxy an unavailable Entry head with another label. Keep utility-policy work separate
from model fitting and keep explanation output mechanically tied to actual family/head inputs.

## W7 — promotion/adjudication for rungs above C1

The promotion gate now applies to C2-C5 and claims of predictive alpha. It does not re-open
C1 adoption.

Any proposed higher rung must still clear:

- every baseline + every simpler surviving rung;
- time-aware confidence/non-inferiority laws;
- era stability;
- >=50 episode floors on claims;
- survivorship restrictions;
- adversarial review;
- operator/CEO adjudication;
- reversible champion/shadow handoff and new board-definition stamp.

# 9. What “better” means for this program

The highest-value improvement is not more model complexity. It is stricter separation of
five planes that had begun to blur:

1. **Authority plane** — C1 live rank, only.
2. **Comparator plane** — v2 shadow, zero authority, explicit names.
3. **Structural plane** — LOFO/coverage/floor diagnostics, outcome-blind.
4. **Outcome plane** — one shared grader, forward-only.
5. **Governance plane** — prereg, read floors, promotion/investigation rules.

If those stay separate, later C2-C5 work becomes much harder to fool.

Specific hardening principles:

- semantic names beat inherited “champion” vocabulary;
- pair the two rankers on one row and one outcome, never two reconstructed populations;
- make missed sessions first-class data, never backfill them;
- key history by session/as-of, not workflow run;
- freeze source fingerprints on derived W3 parts;
- use exact LOFO displacement, not distinct-count/tie-share as a substitute;
- measure admitted-member coverage as well as failures so drift is visible before an outage;
- keep durable writes in `us_prophet_ledgers`, not the engine critical path;
- never let a display comparison become an alpha claim by proximity or wording;
- never let C2/C3 depth pressure weaken the already-frozen fold/episode laws.

# 10. Do-not-redo / do-not-break

- Do not re-litigate C1 adoption.
- Do not restore the additive `potential_score`, desk-count confirmation score, or any
  unconditional everything-goes composite.
- Do not copy `prophet_shadow` legs into canonical `prophet_*` columns on v3.
- Do not create a second board-definition row for the shadow; paired-row grain is settled.
- Do not stamp shadow on a degraded `us_prophet_v2_fallback` night.
- Do not backfill the lost Pages-only v3 night into the candidates store.
- Do not count retries/re-renders of one `as_of` as independent nights.
- Do not retune the presence/variance floors because F4/F8 have low LOFO displacement.
- Do not treat LOFO as predictive importance.
- Do not read order deltas as alpha evidence.
- Do not fit C2 on an unlawful fold or invent a smaller fold because the date clock is slow.
- Do not build a second v2 scorer for W3.
- Do not build a second grader for the shadow.
- Do not weaken #5742’s fail-closed checkpoint fence to improve workflow color.
- Do not bump `SELECTION_ERA` for the C1 rank change; the settled design moved
  `BOARD_DEFINITION` only.
- Do not let W3 data stores acquire rank/gate/size/plan consumers.
- Do not trust sparse-worktree red failures in suites that require `site/`/`data/` until the
  checkout is materialized; #5769 documented this exact trap.

# 11. Danger areas a new session must actively defend

## 11.1 Same word, different product

`prophet_score` historically meant the v1/v2 heuristic and now means C1 on v3. Always pair
with `board_definition`. Shadow values have explicit `prophet_shadow_*` names from #5769.

## 11.2 Same site night, different persistence outcome

A board can ship via Pages while failing to reach git. Production visibility does not imply a
forward-ledger observation. W3 counts durable paired stamps, not what a browser happened to
serve.

## 11.3 Same as-of, multiple workflow runs

Retries of a stale session are not new regime observations. Key by session/as-of and freeze
the first lawful part.

## 11.4 Structural importance vs predictive importance

A family can move many ranks and be predictively bad; a family can barely move this night and
be conditionally useful elsewhere. W3 Lane B/C is descriptive. Only Lane A uses outcomes,
under preregistration.

## 11.5 Current board artifact does not equal historical training plane

Live C1 extracts several members directly from the board row. The candidates store does not
preserve every one in the same raw form. Never silently use an incomplete candidates-only
replay to answer “what C1 used tonight.”

# 12. Exact next-session mission

**Start PR-3A only. Do not auto-roll into PR-3B in the same session.**

Read in this order:

1. `agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md`
2. `agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-16-ACCEPTANCE.md`
3. `agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-15-SHADOW-ACCRUAL.md`
4. `research/prophet_fusion/W3_SHADOW_RACE_RECUT.md`
5. `research/prophet_fusion/families.yml`
6. `scripts/prophet_fusion_arena.py`
7. `engine/us_prophet_fusion.py`
8. `engine/us_board_rank.py`
9. `engine/us_context_vector.py`
10. `.github/workflows/daily.yml` `us_prophet_ledgers`
11. PR #5705 and PR #5769 bodies/decisions

Then execute:

1. Reconcile AgentOS status/landmines/decisions.
2. Repair definition-aware baseline semantics in `families.yml` and tests.
3. Reconcile `pit_settlement` with #5705 in registry + arena + tests.
4. Write/freeze `W3_RACE_PREREG.md`, including the numeric honest-N floor, exact primary
   tripwire, temporal-overlap method, start boundary and no-backfill law.
5. Run the relevant registry/arena/AgentOS suites and mutation controls.
6. Open PR-3A and stop. Do not inspect forward outcome deltas from any newly arrived v3
   pairs while writing the prereg.

After PR-3A is merged, a fresh session may start PR-3B.

# 13. PR-3A exit packet template

The next session should return:

```text
PR-3A VERDICT: PASS / HOLD
main-at-start: <sha>
PR: <number> / <merge sha or held>

RECONCILED
- w2 status: done (#5700)
- #5769 shadow-store item: resolved
- #5705 short-interest law: reconciled / still held with reason
- stale acceptance/workstream text: corrected

W3 PREREG
- paired start boundary: <exact rule>
- primary horizon: <rule>
- primary metric + sign: <rule>
- secondary metric: <rule>
- honest-N floor: <numeric rule>
- temporal dependence method: <rule>
- investigation trigger: <rule>
- degraded/missing session law: <rule>
- promotion arm: NONE

TESTS
- registry role swap mutation: killed
- pit_settlement old +10-calendar regression: killed
- snapshot/forward-only PIT refusal: green
- AgentOS validate: 0 errors

FORWARD RESULTS READ: NO
NEXT: PR-3B structural diagnostics
```

# 14. Cold-stranger summary

Prophet Conditional Fusion is not an unfinished live-ranker project anymore: C1 is already
the canonical live US ranker and passed first-live acceptance. The unfinished work is the
measurement and higher-rung program around it.

The previous records contain two stale carry-forwards that can mislead a new operator. First,
#5769 already fixed the v2 shadow-store gap by adding explicit `prophet_shadow_*` columns;
do not “fix” the canonical null legs. Second, #5705 already repaired the short-interest
knowability law, but Fusion’s registry and arena still carry the old +10-calendar refusal and
need integration cleanup.

The remaining serious semantic defect is `families.yml` calling bare canonical columns the
“champion baseline” even though v3 repointed them to C1. Fix that before W3 reads anything.
The W3 re-cut itself is a charter, not the build. Its prereg is also incomplete in one
load-bearing way: it refers to a registered honest-N floor and registered metric/tripwire
without yet freezing all numeric/decision details. Freeze those now, while durable paired
W3 N is still zero.

Build W3 as four bounded subwaves: 3A semantics+prereg; 3B exact outcome-blind LOFO and full
coverage census; 3C paired forward ledger using the existing candidates store plus the one
shared grader, wired into `us_prophet_ledgers`; 3D first-live instrumentation acceptance and
status display. Keep structural diagnostics separate from alpha evidence, keep missed nights
as gaps, and do not add another scorer or grader.

C2 code is already built and must simply wait for lawful depth; W4-C3 waits for deeper data,
then W5 router consumes Stock Identity, W6 adds multi-heads, and W7 governs promotion of
rungs above C1. The program gets better by making the evidence/authority boundaries harder,
not by accelerating model complexity before the prospective record exists.
