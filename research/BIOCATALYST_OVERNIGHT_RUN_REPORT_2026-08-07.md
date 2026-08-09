# BioCatalyst — overnight autonomous run report, 2026-08-07

Read `research/BIOCATALYST_OPERATOR_DECISIONS_2026-08-07.md` first. It contains the only two
things that need you. This report is the record of what happened.

---

## 1. What merged and went live

**All seven PRs from the earlier session merged**, `#4796` first as the digest binding required.
The fleet drained from 95 open PRs to 13.

| PR | Lane |
|---|---|
| 4796 | D0a design ruling + parity ledger + continuation handoff |
| 4810 | F0-delta reconciliation + closed-beta source manifest |
| 4814 | BC-O1a inert operational persistence + M0a policy |
| 4820 | B1S2a private bounded fixed-cohort transport (dark) |
| 4822 | N0a operating packet producer + N0b allowlisted reader |
| 4825 | v2 acceptance contract + trusted browser verifier |
| 4831 | D0b premium trial product |

**Main is green for BioCatalyst: `1061 passed, 0 failed`** (`-k biocatalyst`, 362s). That is the
authoritative baseline constant — note the selector differs from the pre-merge
`-k "biocatalyst or clinicaltrials"` runs (844–850).

**Live verification passed.** `https://www.mastermind-x.com/biocatalyst.html` is 200 and grew
**61,226 → 69,127 bytes**, carrying Trial Screen, Peer Matrix, Change Tape, `bci-facet`, and the
braid under its user-facing name `WHEN IT WAS TRUE · WHEN WE KNEW`. `biocatalyst.js` and `.css`
return **401** with `{"locked":true,"reason":"authentication_required"}` to anonymous callers —
that is the entitlement boundary working, not a break; only the HTML shell is public. The private
API still returns 401 with `private, no-store` and `Vary: Authorization`.

Not verified: the authenticated rendering. That needs credentials I do not have and must not
obtain.

## 2. What was built tonight — six PRs, all armed `merge-on-green`

| PR | Lane | Substance |
|---|---|---|
| 4937 | Signal-path strategy + autonomous run brief | The two-plane analysis and the ranked plan |
| 4944 | **Move 1** — BC-O1b forward store + M0a clock evaluator | 218 passed, 5 mutation pins |
| 4945 | **Move 2** — theme_clinical PIT rollup + coverage disclosure | Authority block verified untouched |
| 4940 | **Move 4** — sponsor→ticker candidate map | 30 candidate + 20 ambiguous, **0 admitted** |
| 4947 | Change Tape exact values + declared correction lineage | 5 mutation pins, backward compatible |
| 4946 | **Move 3** — B1S4 coverage-epoch machinery (dark) | Activates nothing; `app/` diff empty |

### Integration proof (run by this session, on an idle machine)

All six lanes merged into one scratch branch and the suite run once:

```
pytest tests/ -k biocatalyst -q -p no:randomly
1 failed, 1252 passed, 61460 deselected in 390.87s
```

Baseline on `origin/main` was **1061**. So **1252 = 1061 + 191 new tests, with zero cross-lane
regressions**. The six lanes compose.

The single failure is
`tests/test_biocatalyst_deploy.py::test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file`,
and it is an artifact of how the integration branch was built, not a lane defect: the
`legacy-jobs.yml` conflict was resolved by taking `origin/main`'s copy, which strips every lane's
test registration and leaves the new suites unowned. Each lane carries its own registration and
passes on its own branch. Cross-lane conflict surface across all six: **exactly one file**.

## 3. The finding that corrects my own strategy

I wrote that Move 1 was "not blocked", reasoning that trial outcome families are NCT-keyed and
need no ticker. **The identity half was right and the conclusion was wrong.**

The O1b build evaluated every family's entry gate against the real registry and found **no
family clock can open**, because every trial family's gate names
`clinicaltrials_gov_record_history`, which carries `production_ingest_allowed: false` and
`rights_state: operator_review_required_before_enable`. Verified independently on main:
**exactly 1 of 8** registered BioCatalyst sources is production-ingest-allowed.

I checked the identity gate, found it clear, and stopped — naming the first gate I checked rather
than the one that binds. Corrected in `research/BIOCATALYST_SIGNAL_PATH_STRATEGY_2026-08-07.md`.

**Nothing was opened, and that was right.** A clock over an un-ingestable source accrues nothing
while later reading as "accruing since 2026-08-07" — the exact fabrication this program exists to
prevent. The activation receipt is the authority, not the config file, so no edit can claim an
open clock.

**One operator act unblocks three families**, with no code change, and it is pinned by
`test_the_trial_families_would_open_once_their_source_is_eligible` rather than merely asserted.
See the decisions document.

## 4. Judgment calls I made, and the assumption behind each

1. **Scoped Move 2 to mechanism + honest coverage disclosure.** BioCatalyst covers 1–25 trials
   against ~500,000, so it cannot replace the theme store's numbers today. *Assumption:* a
   coverage figure reading at or near zero, printed honestly, is worth more than a PIT number
   that is not PIT.
2. **Shipped every sponsor→ticker row unadmitted.** *Assumption:* the house rule that an
   LLM-suggested identity link is a candidate until a human reviews it is binding on me, so I
   built a test that makes self-promotion fail rather than trusting myself not to.
3. **Held B1S2b (W1-A).** *Assumption:* inert deployment packaging for a transport that cannot be
   armed without an operator soak decision adds nothing you can use tonight.
4. **Did not build more Wave 4/5/6 surfaces.** *Assumption:* six parity rows already have shipped
   backends and no reachable surface; more surface is not more capability.
5. **Pushed the scheduled continuation from 04:12 to 07:30.** *Assumption:* it should continue
   from wherever I stop rather than duplicate work I was already doing.
6. **Took `origin/main`'s copy of `legacy-jobs.yml`** when integrating locally. *Assumption:* the
   resulting `test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file` failure
   is an artifact of my integration branch, not a lane defect — each lane carries its own
   registration and passes on its own branch.

## 5. Mistakes I made and corrected

- **Reused a squash-merged branch.** I kept committing to
  `claude/biocatalyst-remaining-waves-5704a2` after #4796 merged, orphaning the strategy doc and
  run brief. Re-shipped from fresh `origin/main` as #4937. The standing house law says never
  reuse a squash-merged branch; I broke it and caught it.
- **Corrupted a 3,000-line YAML** with a greedy regex over conflict markers, on a scratch branch.
  Diagnosed by checking `origin/main`'s copy parsed cleanly, therefore I had caused it. Correct
  method: take `git show origin/main:<file>` and re-apply.
- **Handed a full-suite regression gate to six parallel builders**, which became ~30 concurrent
  pytest processes at load 76–87 on 24 cores, and nearly misdiagnosed six healthy builders as
  hung. Measure the baseline once, hand it to builders as a constant, scope their gates narrowly.
  Applied for tonight's lanes; saved to memory.
- **Believed a contended baseline.** One builder reported `109 failed, 735 passed` where four
  independent measurements found 844–1061 passed and zero failures. Corrected on the PR so the
  record does not mislead a later reader.

## 6. Blocked, and honestly so — do not re-plan these

- **`B1S2c`** — operator arming + **14 continuous days** of soak. A calendar, not a task.
- **W3 identity** — needs an executable versioned PIT contract from a plane BioCatalyst does not
  own. Measured: 2 of 6 shared-plane adapters eligible.
- **`C2` / `MKT0` / `EST1`** — Capital Structure PIT, licensed market/options, licensed estimates.
  Contracts that do not exist.
- **`P3`** — deliberately unscheduled; first possible authority is shrink-only.
- **Forward accrual** — now known to be blocked on the Record History rights decision (§3).

## 7. The next three actions

1. **Make Decision 1** (enable Record History ingest after a rights review). Everything
   downstream is gated behind it and it costs one registry flag plus a review.
2. **Make Decision 2** or explicitly defer it (admit sponsor→ticker rows). Until then BC-P1
   post-selection context stays dark.
3. **Adopt the new Change Tape fields in the UI.** #4947 ships exact before/after values,
   source locators and declared correction lineage through the API, but no surface renders them
   yet — the D0b braid still drives its redline branch from the inferred `op === 'replace'`
   signal. That is a bounded, well-specified follow-up.

## 8. The honest bottom line

You asked whether this can produce signals or serve as a contextual layer for pharma picks.

**A contextual layer already exists and is already live** — `engine/theme_clinical.py`, which
aggregates trials to a theme, joins that theme to baskets, and feeds Mastermind, reaching price
with no per-company identity at all. It is correctly fenced: `is_context_only`, display-tier,
never scored, never folded into `fused_obs_z`.

**There is no authorized signal, and there will not be one before 2027 even in the best case.**
Forward accrual needs 12–24 months before a pre-registered test is possible, the retrospective
store is look-ahead-selected and cannot be cleaned, and the clock has not started because the
source is not enabled. Tonight's work built everything that makes starting it a one-flag
decision. It did not, and could not, start it.
