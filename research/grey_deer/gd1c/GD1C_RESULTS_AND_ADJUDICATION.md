# GD-1C results and adjudication

**Workstream:** `WS:GREY-DEER-RISK-INTELLIGENCE`
**Preregistration freeze:** `fce7bfeb8c925748ed92b54a7b19901c3a9f35c1`
**Preregistration stamp:** `37ca71ecdd48`
**Design era:** 2016-01-04..2026-07-31
**Current-definition code identity:** base `cdf99c6203b6bd964d7fb5564452289ecfde90e8`, `engine/leadership_crack.py` blob `cb0a3f468ac1bf2267fb6d0ee57d378b293d3c0b`
**Authority granted:** none

## Verdict first

| Hypothesis | PRIMARY verdict | Applicable GD-5 build reopened? | Reason |
|---|---|---:|---|
| GD-H1 — duration × broken leadership | **BLOCKED** | No | Point-in-time cohort membership cannot be reconstructed across the design era. DGS10/DGS30 are also latest-revised local FRED files without first-available vintages. |
| GD-H2 — volatility acceleration conditional on fragility | **BLOCKED** | No | Point-in-time cohort membership cannot be reconstructed across the design era. The secondary current-membership lane is underpowered or fails discrimination/calibration on every endpoint. |

The commissioned `def_current_cf` substitute was completed. It produced **no
secondary PASS** and cannot replace the blocked primary lane. GD-5A/B/C remain
closed. This is a completed research wave with an adverse/blocking result, not
an unfinished numerical run.

## Preregistration topology proof

The registration commit contains only
`research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md` and predates the analysis
script and every outcome-bearing GD-1C artifact.

```text
freeze commit: fce7bfeb8c925748ed92b54a7b19901c3a9f35c1
commit time:   2026-08-19T21:38:16-07:00
tree SHA:      97b0bbc485d256ed6270f604c96a8fee0a0f21da
content SHA:   d197cfaab658924124c117246227dd17aae334938e0b3ba55fff3ddc264e3aed
stamp commit:  37ca71ecdd48
```

Verification commands:

```bash
git diff-tree --no-commit-id --name-only -r fce7bfeb8c925748ed92b54a7b19901c3a9f35c1
git show -s --format='%H%n%cI%n%T' fce7bfeb8c925748ed92b54a7b19901c3a9f35c1
git log --reverse --format='%H %cI %s' -- research/grey_deer/gd1c/
git show fce7bfeb8c925748ed92b54a7b19901c3a9f35c1:research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md | shasum -a 256
```

No `data/`, `site/`, design-era membership, rate, price, volatility, or outcome
value was read before the freeze and stamp commits.

## Primary PIT-membership adjudication

The primary test stops lawfully before fabricating rows:

1. The membership file's first tracked receipt is
   `29721d07084c0332e1c2b5387a32addc1863c395`, 2026-06-14.
2. The four Leadership Crack baskets were curated in 2026. Retrospective
   `added` fields, mostly 2023-05-09, are not first-known membership receipts.
3. There is no 2016–2022 versioned cohort, no per-member `available_at`, and no
   addition/removal lineage that can support PIT identity.
4. The DGS10/DGS30 files used by the secondary H1 lane have no ALFRED-style
   vintage or publication clock.

The primary lane therefore has zero guessed rows and zero promotion-bearing
episodes. The minimum lawful substitute and panel caveats are documented in
`GD1C_SOURCE_RIGHTS_AND_GAPS.md`.

## Secondary `def_current_cf` reconstruction

The research-only runner applies the current `leadership_crack.v1` definition
to truncated inputs without calling its writing `build()` path.

- Current active-member union: 42 names.
- Design-era reconstruction: 2,659 NYSE-session rows.
- Out-of-design August coverage: 13 rows through 2026-08-19.
- Every row carries lane, membership basis, definition/code identity, a
  content-addressed input-vintage ID, rate revision basis, member coverage, and
  quality state.
- Rates are labeled `latest_revised_no_available_at_secondary_only`.
- Current-definition member-pair coverage at candidate episodes averages 86%
  for GD-H1 and 87% for GD-H2; recent IPOs and current-membership survivorship
  are not hidden.

Full-design thresholds, selected using only rows through 2026-07-31:

| Threshold | Frozen value |
|---|---:|
| DGS10 three-session change, 80th percentile | +7 bp |
| DGS30 three-session change, 80th percentile | +7 bp |
| one-session change in SPY five-session realized variance, 80th percentile | 0.0000126566 |
| VIX level 80th-percentile baseline | 22.732 |
| SPY five-session realized-variance 80th-percentile baseline | 0.000113643 |

Fold thresholds were recomputed from training eras only. The values above are
the final full-design thresholds for out-of-design coverage, not inputs to held
era outcomes.

## Effective N and era integrity

Raw daily fires were collapsed to anchors separated by at least three complete
non-fire sessions. This turns 204 GD-H1 fires into 64 effective episodes and 220
GD-H2 fires into 75 effective episodes.

| Hypothesis | Endpoint | E1 2016–19 N/adverse | E2 2020–22 N/adverse | E3 2023–26H1 N/adverse |
|---|---|---:|---:|---:|
| GD-H1 | ≥3%, 1s | 13 / 0 | 26 / 3 | 25 / 1 |
| GD-H1 | ≥5%, 1s | 13 / 0 | 26 / 0 | 25 / 1 |
| GD-H1 | ≥3%, 3s | 13 / 3 | 26 / 7 | 25 / 4 |
| GD-H1 | ≥5%, 3s | 13 / 0 | 26 / 4 | 25 / 3 |
| GD-H2 | ≥3%, 1s | 18 / 0 | 30 / 2 | 27 / 1 |
| GD-H2 | ≥5%, 1s | 18 / 0 | 30 / 0 | 27 / 0 |
| GD-H2 | ≥3%, 3s | 18 / 1 | 30 / 4 | 27 / 4 |
| GD-H2 | ≥5%, 3s | 18 / 0 | 30 / 1 | 27 / 2 |

All secondary endpoint cells span three eras and include post-2020 rows. Only
GD-H1's ≥3%/3-session endpoint reaches the frozen `≥30 episodes, ≥12 adverse`
sample gate. That adequately powered secondary cell fails discrimination,
Brier, calibration, sign, false-alarm, and baseline gates.

## OOS discrimination and multiple testing

Leave-one-era-out predictions use training-only percentiles and calibrators,
with a three-session purge/embargo. AP uncertainty uses 2,000 chronological
episode-block bootstraps. BH controls all eight declared tests at q=0.10.

| Hypothesis | Endpoint | Raw fires | Effective N | Adverse N | Prevalence | OOS AP | AP / prev | 90% LB | BH q |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GD-H1 | ≥3%, 1s | 204 | 64 | 4 | 0.062 | 0.104 | 1.67 | 1.21 | 0.113 |
| GD-H1 | ≥5%, 1s | 204 | 64 | 1 | 0.016 | 0.020 | 1.25 | 0.88 | 0.751 |
| GD-H1 | ≥3%, 3s | 204 | 64 | 14 | 0.219 | 0.191 | 0.87 | 0.75 | 0.751 |
| GD-H1 | ≥5%, 3s | 204 | 64 | 7 | 0.109 | 0.098 | 0.90 | 0.77 | 0.751 |
| GD-H2 | ≥3%, 1s | 220 | 75 | 3 | 0.040 | 0.037 | 0.92 | 0.78 | 0.751 |
| GD-H2 | ≥5%, 1s | 220 | 75 | 0 | 0.000 | NA | NA | NA | NA |
| GD-H2 | ≥3%, 3s | 220 | 75 | 9 | 0.120 | 0.114 | 0.95 | 0.79 | 0.751 |
| GD-H2 | ≥5%, 3s | 220 | 75 | 3 | 0.040 | 0.041 | 1.02 | 0.81 | 0.751 |

The tempting row is GD-H1 ≥3%/1-session: its AP ratio and lower bound clear the
numeric AP gate. It still has only four adverse episodes, misses BH by a narrow
margin, has the wrong calibration/sign, produces four non-events in its worst
quarter, and loses to a simpler baseline. It is small-N noise under the frozen
decision rule, not a near-PASS.

## Calibration, lead, false alarms, and baselines

| Hypothesis | Endpoint | Brier skill half 1 | Brier skill half 2 | Calibration slope | Score slope halves | Lead median / p25 | Max non-events / qtr | Secondary source coverage | Best baseline AP |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GD-H1 | ≥3%, 1s | +0.0002 | +0.0003 | −0.44 | −0.05 / −0.16 | 1.0 / 1.0 | 4 | 100% | 0.159 |
| GD-H1 | ≥5%, 1s | −0.0021 | ~0.0000 | −1.87 | NA / −0.05 | 1.0 / 1.0 | 5 | 100% | 0.062 |
| GD-H1 | ≥3%, 3s | −0.0001 | ~0.0000 | −1.22 | −0.12 / +0.06 | 2.0 / 2.0 | 4 | 100% | 0.412 |
| GD-H1 | ≥5%, 3s | ~0.0000 | ~0.0000 | −2.24 | −0.09 / +0.04 | 3.0 / 2.5 | 5 | 100% | 0.327 |
| GD-H2 | ≥3%, 1s | +0.0005 | −0.0001 | −16.17 | −0.02 / +0.07 | 1.0 / 1.0 | 6 | 100% | 0.108 |
| GD-H2 | ≥5%, 1s | +0.0035 | NA | 0.00 (not estimable) | NA / NA | NA / NA | 6 | 100% | NA |
| GD-H2 | ≥3%, 3s | +0.0007 | −0.0004 | −1.35 | −0.15 / −0.01 | 3.0 / 2.0 | 5 | 100% | 0.184 |
| GD-H2 | ≥5%, 3s | +0.0003 | −0.0001 | −3.11 | −0.02 / +0.05 | 3.0 / 2.5 | 6 | 100% | 0.082 |

The source-coverage column describes non-null fields inside the secondary lane;
it does not mean PIT membership coverage. Primary PIT membership coverage is
not reconstructable and the temporal-integrity gate is false.

Every estimable calibration slope is outside 0.70–1.30. Expected sign fails in
at least one half for every endpoint. Leave-one-crisis-out slopes also fail the
frozen sign requirement: GD-H1 endpoint ranges include negative slopes
(−0.201..−0.103 for ≥3%/1s), while GD-H2's apparently positive 1-session crisis
omissions coexist with mixed split-half signs and only three adverse episodes.
All estimable lead distributions are future-positive by construction, but lead
alone does not rescue the failed sample, calibration, false-alarm, or temporal
gates.

## Gate-by-gate adjudication

| §12 gate | GD-H1 | GD-H2 |
|---|---|---|
| 100% PIT/source availability | **FAIL / BLOCKED** | **FAIL / BLOCKED** |
| ≥30 effective episodes, ≥12 adverse, ≥3 eras incl. post-2020 | Only ≥3%/3s clears in secondary | No endpoint clears |
| AP ≥1.25× prevalence, 90% LB >1.0× | Only underpowered ≥3%/1s clears numerically | No endpoint clears |
| Brier skill >0 both halves | Only underpowered ≥3%/1s clears by tiny margins | No endpoint clears |
| Calibration slope 0.70–1.30 | No | No |
| Split-half + leave-one-crisis-out sign stability | No | No |
| Median lead ≥1, p25 >0 | Yes where a true positive exists; not sufficient | Yes where a true positive exists; not sufficient |
| ≤2 non-event critical episodes/quarter | No; worst 4–5 | No; worst 5–6 |
| ≥80% required-source coverage | Secondary fields yes; primary membership no | Secondary fields yes; primary membership no |
| Within-family multiple-testing control | No endpoint q≤0.10 | No endpoint q≤0.10 |
| Nonredundant versus simple baseline | No endpoint beats best baseline AP | No endpoint beats best baseline AP |

No endpoint clears all gates. No hypothesis PASSes.

## August 2026 out-of-design coverage

August did not choose any threshold. Applying the full-design thresholds after
the fact:

- The current-definition counterfactual is `BROKEN` from 2026-07-07 onward.
  That is a reconstructed state, not proof of historical emission.
- GD-H1 fires on 2026-08-10; the subsequent current-cohort median residual is
  +2.24% at one session and +7.78% at three sessions — a non-event.
- GD-H1 fires again on 2026-08-18. The one-session current-cohort median
  residual is −4.78%: the ≥3% label prints, the ≥5% label does not. The
  three-session outcome is not mature at the cutoff.
- GD-H2 fires on 2026-08-03 and 2026-08-04; neither anchor produces a frozen
  adverse 1/3-session endpoint. It does **not** fire on 2026-08-18.
- VIX remains below the full-design 80th-percentile baseline during these rows.

This is the required motivating-incident coverage read: GD-H1 describes part of
the 2026-08-18 shape, but it also emits a recent non-event and does not possess a
lawful design-era PIT sample. GD-H2 misses the motivating session. Neither earns
promotion.

## Adversarial interpretation

The strongest pro-promotion story is that broken leadership plus a strict
three-session yield acceleration caught the August 18 cohort damage while VIX
was quiet. The design-era counterfactual breaks that story in four ways:

1. current members are a 2026-curated survivor/thematic panel, not PIT identity;
2. the only AP-looking 1-session cell has four adverse episodes and misses BH;
3. the adequately powered GD-H1 3-session/3% cell has AP below prevalence,
   negative Brier skill, negative calibration, and a much stronger baseline;
4. the same frozen H1 rule fired on August 10 without the adverse outcome.

For GD-H2, the motivating August 18 session is not even coverage-true under the
frozen acceleration threshold. A different volatility transform might be worth
future research, but selecting it now would be a post-outcome GD-H change and is
outside this preregistration.

## What would change the answer

The minimum reopening evidence is:

1. date-effective first-known membership history for all four cohort keys,
   including additions, removals, renames, delistings, and source clocks;
2. lawful first-available DGS10/DGS30 vintages for GD-H1;
3. a new preregistration if Fable/Sol changes the membership construction,
   episode definition, volatility transform, or hypotheses.

Do not substitute current index membership and call it PIT. Do not lower §12
gates. Do not tune on August 2026.

## Reproducibility and artifacts

Run from a full clean worktree:

```bash
python3 research/grey_deer/gd1c/GD1C_RECONSTRUCT_AND_TEST.py
python3 scripts/agentos.py validate
git status --short -- data site
```

Artifacts:

- `GD1C_RECONSTRUCTION_MANIFEST.json` — code/input identities, per-file
  digests, membership history, fold thresholds, and blocker;
- `GD1C_RECONSTRUCTION_ROWS.csv` — 2,672 labeled design + August rows;
- `GD1C_EPISODE_LEDGER.csv` — 556 endpoint-episode rows with effective-N,
  OOS probability, coverage, and calibrator receipt;
- `GD1C_GATE_SCORECARD.csv` — all eight endpoint gate records;
- `GD1C_INCIDENT_COVERAGE.csv` — out-of-design August read;
- `GD1C_RUN_RECEIPT.json` — verdict and artifact digests;
- `GD1C_SOURCE_RIGHTS_AND_GAPS.md` — named primary blockers and lawful minimum
  substitute.

The runner asserts that `data/` and `site/` are clean before and after execution.

## Explicit non-authority

**GD-1C grants no live market, Prophet, Portfolio, alert, ranking, sizing,
gating, or execution authority.**
