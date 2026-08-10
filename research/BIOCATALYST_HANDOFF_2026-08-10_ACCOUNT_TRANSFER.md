# BioCatalyst — account-transfer handoff, 2026-08-10

**Read this first. It is the single document a new session needs.** Everything else is context.

| Field | Value |
|---|---|
| Written | 2026-08-10, by the session that ran the first live canary |
| Purpose | Move this program to a different account with zero loss of state |
| Prior docs | `BIOCATALYST_SIGNAL_PATH_STRATEGY_2026-08-07.md` (why), `BIOCATALYST_OVERNIGHT_RUN_REPORT_2026-08-07.md` (what), `BIOCATALYST_OPERATOR_RULING_2026-08-07.md` (authority), `BIOCATALYST_AUTONOMOUS_RUN_BRIEF_2026-08-07.md` (how to work) |

---

## 1. THE HEADLINE — the pipeline works end to end, and stopped exactly where it should

On 2026-08-10 the first ever live BioCatalyst canary poll ran on the production VPS. It:

- **fetched all four configured trials** from ClinicalTrials.gov,
- **parsed them** into `biocatalyst_trial_source_state.v1` records with real source timestamps,
  attribution, license class and modification disclosure,
- **mirrored them to R2 with verified receipts** at exactly the intended prefix:

```
biocatalyst/raw/clinicaltrials/v2/NCT04528082/cad07a79….json   18,895 bytes
biocatalyst/raw/clinicaltrials/v2/NCT05020236/6fefeb86….json   32,298 bytes
```

- then **refused to publish the generation** and dead-lettered it, ending `state: quarantined`.

**The operator's R2 credentials are proven working.** `r2_mirror_state: mirror_receipt_verified`.

### The publication refusal, and the leading hypothesis

`public/health.json` reports `observed_nct_count: 0` — that counts the **published** generation,
not the fetch. The fetch succeeded; publication was refused.

Leading hypothesis, from the recorded evidence and **NOT yet confirmed**:

- every fetched record carries `source_dataset_timestamp_raw: "2026-08-07T09:00:05"`
- `public/health.json` carries `freshness_budget_seconds: 7200` (2 hours)
- the run happened at `2026-08-10T05:52Z` — roughly **69 hours** after that dataset stamp

If publication enforces the freshness budget against the source dataset timestamp, a ~69-hour-old
stamp against a 2-hour budget explains the refusal exactly, and the system behaved correctly.

**Do not "fix" this by widening the budget until the cause is confirmed.** Two readings are open
and they have opposite remedies:

1. ClinicalTrials.gov genuinely publishes its dataset stamp on a multi-day cadence → the 2-hour
   budget is mis-specified for this source and should be re-derived from observed cadence.
2. The stamp means something other than "dataset freshness" → the budget is fine and the
   comparison is wrong.

**First action for the next session: read the publication code path and determine which.**
Start at `engine/biocatalyst/publication.py`, find where `freshness_budget_seconds` and
`source_dataset_timestamp_raw` are compared, and confirm or kill the hypothesis. The evidence is
all on the VPS under
`/var/lib/macro-biocatalyst/state/dead-letter/attempt_20260810T055235959556Z_b4e57dc858e6/`.

---

## 2. VPS STATE — exact, as of 2026-08-10T05:55Z

Host `root@146.190.142.17` (`ubuntu-s-mastermindx`). Reach it with:

```bash
ssh -i ~/.ssh/macro_dashboard_deploy_v2 root@146.190.142.17
```

Repo checkout is `/opt/macro`. Runtime is `/opt/macro-biocatalyst/current`.

### `/etc/macro-biocatalyst.env` — now fully configured, `0600 root:root`

| Key | State |
|---|---|
| `BIOCATALYST_R2_ENDPOINT` / `_BUCKET` / `_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` | **operator-supplied, verified working** |
| `BIOCATALYST_ENABLED` | `1` |
| `BIOCATALYST_HISTORY_ENABLED` | **`0`** — rights cleared by ruling, staged off until the canary is green |
| `BIOCATALYST_PROSPECTIVE_ENABLED` | `0` |
| `BIOCATALYST_CANARY_NCTS` | `NCT04528082,NCT05020236,NCT06602479,NCT07218380` |
| `BIOCATALYST_USER_AGENT` | `MastermindX-BioCatalyst/1.0 (biocatalyst@mastermind-x.com)` |

Backup of the pre-change file: `/etc/macro-biocatalyst.env.bak.20260810T054647Z`.

**Two traps found the hard way — both cost a failed run:**

1. **`BIOCATALYST_USER_AGENT` must contain an `@`.** `scripts/biocatalyst_worker.py:377` requires
   it — a contact **email**, not a URL. A URL-only UA fails `BIOCATALYST_USER_AGENT_INVALID`.
2. **`BIOCATALYST_CANARY_NCTS` must be sorted ascending.** `scripts/biocatalyst_worker.py:372`
   asserts `tuple(sorted(nct_ids)) == nct_ids`. An unsorted list fails
   `BIOCATALYST_CANARY_NCTS_INVALID`.

**`biocatalyst-setup.sh --verify-prereqs` passes on BOTH of those broken values.** It checks key
shapes, not the worker's own validation. Do not treat a green verify as proof the worker will
start. That gap is worth closing.

### `biocatalyst@mastermind-x.com` may not route — OPERATOR DECISION

The worker forces an email into the UA. A non-routing contact is worse than useless under the
source's terms, since the whole point is reachability. **Confirm that address routes, or replace
it.** Deliberately not set to the operator's personal Gmail — sending a personal address to a
government site in every request header was not a call to make unilaterally.

### Units — installed, DISABLED, never armed

```
macro-biocatalyst.service   static,   inactive
macro-biocatalyst.timer     disabled, inactive
```

Arming the timer is still **B1S2c**: an operator decision plus a fourteen-day soak. The canary
runs above were manual one-shots (`systemctl start macro-biocatalyst.service`), not arming.

---

## 3. REPOSITORY STATE

Main is green for BioCatalyst. Baseline: **`pytest tests/ -k biocatalyst` → 1061 passed** on
`origin/main` before this session's PRs. Hand that to builders as a constant; do not re-measure.

### Merged earlier (7 PRs)
`#4796` design ruling + parity ledger · `#4810` F0-delta + closed-beta manifest · `#4814` BC-O1a
persistence + M0a policy · `#4820` B1S2a bounded transport · `#4822` N0a producer + N0b reader ·
`#4825` v2 acceptance contract + browser verifier · `#4831` D0b premium trial product.

### Open and armed `merge-on-green` — verify state with `gh pr list`

| PR | Lane |
|---|---|
| 4937 | Signal-path strategy + autonomous run brief |
| 4940 | Sponsor→ticker candidate map |
| 4944 | BC-O1b forward store + M0a clock evaluator |
| 4945 | theme_clinical PIT rollup + coverage disclosure |
| 4946 | B1S4 coverage-epoch machinery (dark) |
| 4947 | Change Tape exact values + declared correction lineage |
| 4957 | B1S2b privileged deployment package |
| 4958 | Ruling execution (rights enable + 29 admissions) |
| 4959 | The operator ruling document |
| 5002 | Group B — four subsidiary admissions |

**They form a dependency chain**, roughly `4959 → 4940 → 4958 → 5002`, and **all BioCatalyst PRs
conflict on `.github/ci/legacy-jobs.yml`** because
`test_biocatalyst_deploy.py::test_biocatalyst_ci_uses_bounded_complete_lanes_with_no_unowned_test_file`
forces every new `test_biocatalyst_*.py` to be registered there. **Merge serially**: merge one,
fetch main, rebase the next, resolve that YAML block as a union taken from
`git show origin/main:<file>` — never with a regex over conflict markers.

At last check several were `merge-blocked` on a **fleet-wide** main red that is **not** ours:
zero BioCatalyst failures among the twelve failing suites (`exit_policy_study`, `nav_hover_bridge`,
`ob_mask_start_invariance`, `rendered_ticker_links`, `government_revenue_candidate_*`, …). Other
programs own those. The armed labels persist, so they merge when main greens.

---

## 4. WHAT THE OPERATOR STILL OWNS

1. **Confirm `biocatalyst@mastermind-x.com` routes**, or supply an address that does (§2).
2. **The 16 still-ambiguous sponsor rows.** 8 outside the declared universe, 3 renamed entities,
   and one each private / ADR-ambiguous / CRO / multi-match / joint-venture. Each needs a per-case
   call or an explicit ruling to leave them permanently unresolved. Group B (the 4 subsidiaries →
   DHR, RHHBY, JNJ, MRK) is already admitted in `#5002`.
3. **`B1S2c`** — arming the timer plus a fourteen-day soak. Not compressible.
4. **Bucket scoping.** `research` is shared with other lanes and R2 tokens scope to a bucket, not
   a prefix, so the BioCatalyst key can write all of `research`. Broader than the setup script
   intends. A dedicated bucket would match the token's blast radius to its job.

---

## 5. WHAT NO SESSION CAN FINISH — do not re-plan these

- **W3 identity** — needs an executable versioned point-in-time contract from a plane BioCatalyst
  does not own. Measured: 2 of 6 shared-plane adapters eligible.
- **`C2` / `MKT0` / `EST1`** — Capital Structure PIT, licensed market/options, licensed estimates.
  Contracts that do not exist.
- **`P3`** — deliberately unscheduled. First possible authority is shrink-only.

---

## 6. THE STRATEGIC PICTURE, IN FIVE LINES

- **A contextual layer already exists and is already live**, and it is *not* BioCatalyst:
  `engine/theme_clinical.py` aggregates trials to a theme, joins that theme to baskets, and feeds
  Mastermind — reaching price with **no per-company identity at all**.
- It is correctly fenced: `is_context_only`, display-tier, never scored, never folded into
  `fused_obs_z`.
- **There is no authorized signal, and there will not be one before 2027** even in the best case.
  Forward accrual needs 12–24 months before a pre-registered test is possible.
- The retrospective ClinicalTrials.gov store is **look-ahead-selected pre-2019 and cannot be
  cleaned**, which is why forward accrual is the only clean evidence this program will ever have.
- **No outcome-family clock is open, deliberately.** A clock over a source that is not yet
  collecting accrues nothing while later reading as "accruing since <date>" — the exact
  fabrication this program exists to prevent. Clocks open through an activation receipt, never a
  config edit.

---

## 7. FIRST THREE ACTIONS FOR THE NEXT SESSION

1. **Confirm or kill the freshness hypothesis** in `engine/biocatalyst/publication.py` (§1), using
   the dead-letter evidence on the VPS. Do not widen any budget before the cause is known.
2. **Land the open PR chain** serially (§3), rebasing each onto a green main.
3. **Re-run the canary** once the publication cause is fixed:
   `systemctl start macro-biocatalyst.service`, then read
   `/var/lib/macro-biocatalyst/public/health.json` — success looks like `observed_nct_count: 4`
   and a non-null `last_success_at`. Only after that is green should
   `BIOCATALYST_HISTORY_ENABLED` go to `1`, and only then does arming become a live question.
