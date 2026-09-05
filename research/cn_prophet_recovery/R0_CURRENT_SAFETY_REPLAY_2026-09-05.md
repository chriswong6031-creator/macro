# China Prophet R0 — immutable current safety replay

Status: `RESULT / DRAFT-HOLD / EFFECT_NONE`

Operation: `cn-prophet-r0-current-safety-replay-20260905-sol-001`

Canonical carrier: Macro issue #6866 and Slack root `C0BSBM78V1N/1788585650.083679`

Source: Macro `3cd4bd489ef567d86bbcf516b03f6d79062d67bb`, tree `24f2ce890dcb837e80b5cb710e29f3995ff05b1b`

## Result

The current 41.5% win rate and −0.88% mean excess return are real outcomes for the
served China shelf, but they are **not evidence that V4 Intelligence ordering
failed**. Every persisted V4 bake used the coverage-atomic V3 fallback. There are
zero daily rows—and therefore zero matured rows—with the required treatment basis
`intel_interest_then_v3_score`.

The discriminating R4 comparison is consequently unavailable:

- effective live order: `cn_prophet_v3_score` / `V3_FALLBACK`;
- V4 Intelligence treatment: `n=0`;
- all-board-date V4 versus frozen-V3 post-cap comparison: 310 versus 310 daily rows,
  with zero ticker-set or rank deltas;
- ledger-as-of comparison: 286 versus 286 daily rows, also zero deltas;
- current R4 metric in committed audit: absent;
- nightly R4 consumer/warning path: contract-disconnected;
- authorized serving effect: `NONE`.

R4's current shelf-median metric has no power on this population. A value of zero
would be fabricated: no V4-ordered treatment exists to compare. The lawful current
verdict is `R4_SOURCE_MISSING_OR_MALFORMED` plus
`NOT_ESTIMABLE_ZERO_TREATMENT`, not breach, no-breach, or revert.

## Immutable inputs

The replay reads all dependencies with `git cat-file` at the pinned revision. It
does not read omitted sparse-checkout data, today's filesystem prices, or live
network prices. The machine receipt records every source blob:

- current ledger, board, entry latch, candidate PIT store, audit artifact;
- ranker, grader, audit, tripwire, and China builder source;
- 152 unique security-price blobs and the CSI300 `510300.SS` benchmark blob.

The 152 security-price blobs alone contain 23,331,479 bytes. Their individual Git
object IDs are retained in the receipt so a later correction cannot silently alter
the replay.

## Episode, duplicate, and carry-forward accounting

The production episode rule is reproduced exactly: one episode is one contiguous
run across stored board observations. Daily persistence is not treated as a new
recommendation.

| Quantity | Replayed |
|---|---:|
| V4 daily rows through ledger board date 2026-09-03 | 286 |
| Contiguous V4 episode admissions | 172 |
| Public current-ledger rows | 172 |
| Carry-forward daily materializations | 114 |
| Episodes materialized on more than one board date | 69 |
| V3-shadow episode admissions | 172 |
| V3-shadow public-ledger rows | 172 |
| Live-only/control-only/ledger-only episode keys | 0 / 0 / 0 |

The receipt includes every episode's admission date, ticker, daily membership dates,
materialization count, and next absence date. This kills both duplicate-day inflation
and the opposite error of collapsing a later re-entry into a ticker's first-ever
appearance.

## Entry, exit, and benchmark replay

For every one of the 172 emitted rows, the replay located the immutable point-in-time
entry latch, proved its first post-board fill date, and preserved the published basis.
For each of the 65 matured episodes it then independently walked exactly ten sessions
from the latched T+1 fill, selected the matching CSI300 timestamps, and recomputed the
absolute and benchmark-relative return.

| Check | Exact matches |
|---|---:|
| Admission/episode identity | 172 / 172 |
| T+1 fill date | 172 / 172 |
| Latched entry after published rounding | 172 / 172 |
| Ten-session exit | 65 / 65 |
| Absolute P&L | 65 / 65 |
| CSI300 excess | 65 / 65 |
| Candidate clocks later than decision date | 0 |

The deterministic replay reproduces the published aggregate:

| Metric | Result |
|---|---:|
| Matured rows | 65 |
| Independent recommendation cohorts | 4 |
| Win rate | 41.5% |
| Mean excess vs CSI300 | −0.88% |
| Median excess vs CSI300 | −2.27% |
| Date-blocked win-rate interval | 20.7%–70.4% |
| Date-blocked mean-excess interval | −3.71%–+2.39% |

The four cohorts are 2026-08-18 (23 rows), 2026-08-19 (14), 2026-08-20
(13), and 2026-08-21 (15). Sixty-five rows are descriptive observations, not
65 independent trials.

## Ordering and coverage accounting

Every current board date requests `intel_interest_then_v3_score`, but every one
persists `effective_order_basis=cn_prophet_v3_score`,
`order_mode=v3_coverage_fallback`,
`fallback_reason=incomplete_intel_interest_coverage`, and
`intel_coverage_complete=false`.

| Board date | Ranked candidates | Intelligence measured | Unavailable | V4 daily rows | Candidate `featured` | V4 − featured |
|---|---:|---:|---:|---:|---:|---:|
| 2026-08-18 | 1,635 | 0 | 1,635 | 23 | 23 | 0 |
| 2026-08-19 | 1,641 | 0 | 1,641 | 20 | 20 | 0 |
| 2026-08-20 | 1,640 | 1,636 | 4 | 24 | 24 | 0 |
| 2026-08-21 | 1,642 | 1,638 | 4 | 22 | 22 | 0 |
| 2026-08-24 | 1,636 | 1,632 | 4 | 21 | 21 | 0 |
| 2026-08-25 | 1,641 | 1,637 | 4 | 23 | 23 | 0 |
| 2026-08-26 | 1,638 | 1,634 | 4 | 30 | 24 | 6 |
| 2026-08-27 | 1,633 | 1,629 | 4 | 31 | 24 | 7 |
| 2026-08-28 | 1,627 | 1,623 | 4 | 24 | 24 | 0 |
| 2026-08-31 | 1,629 | 1,625 | 4 | 24 | 24 | 0 |
| 2026-09-01 | 1,629 | 1,625 | 4 | 24 | 24 | 0 |
| 2026-09-03 | 1,623 | 1,619 | 4 | 20 | 20 | 0 |
| 2026-09-04 | 1,630 | 1,626 | 4 | 24 | 0 | 24 |

Before caps, the effective ordering is the V3 `score_rank` by construction and
source law; its effective-V3 rank delta is zero across 21,244 ranked candidate rows.
The requested Intelligence pre-cap delta is deliberately null. Coverage-atomic law
makes an Intelligence rank undefined when any ranked name is uncovered, and sorting
only the covered names would manufacture a treatment. After admission/caps, the
independently persisted live and shadow rows remain identical on all 310 rows.

This rules the amendment's alternatives as follows:

- `V3_FALLBACK`: proven;
- `CAP_OR_ADMISSION_MADE_ORDER_IRRELEVANT`: not the cause—the order was already V3
  before lane partition or caps;
- `SHADOW_PROJECTION_DEFECT`: not supported—the two independently keyed board and
  ledger populations reconcile; their identity is expected under fallback;
- `MIXED`: not supported as the cause of the matured result.

## R4 producer-to-consumer trace

| Plane | Current state |
|---|---|
| `engine/cn_v3_tripwires.py` R4 spec | `BUILT` |
| Same-input nightly R4 measurement | `NOT_BUILT / CONTRACT_DISCONNECTED` |
| `data/cn_prophet_audit/latest.json` | fresh as of 2026-09-04, but R4 field/payload absent |
| Warning/proposal emission | `DARK_OR_DISCONNECTED` |
| Automatic revert actuator | does not exist; current law is operator warning/proposal |
| Serving change | `NONE / NOT_AUTHORIZED` |

`engine/cn_prophet_audit.py` neither imports the tripwire module nor writes its
metric. The minimal later seam is therefore the existing audit owner: consume the
existing tripwire spec, write the same-input metric and complete provenance, and emit
the governed warning/proposal. That seam must fail closed when treatment is empty or
malformed. It must not become an autonomous revert actuator; any serving change is a
separate Sol/Chairman-authorized operation.

## Descriptive decomposition

These cells are diagnostics, not promotion evidence. All share only four independent
date blocks.

### By cohort

| Admission date | n | Win | Mean excess | Median excess |
|---|---:|---:|---:|---:|
| 2026-08-18 | 23 | 13.0% | −4.855% | −5.214% |
| 2026-08-19 | 14 | 78.6% | +2.389% | +3.177% |
| 2026-08-20 | 13 | 61.5% | +2.392% | +2.708% |
| 2026-08-21 | 15 | 33.3% | −0.669% | −3.788% |

### By board-rank bucket

| Rank | n | Win | Mean excess | Median excess |
|---|---:|---:|---:|---:|
| 1–6 | 16 | 25.0% | −3.241% | −5.773% |
| 7–12 | 20 | 40.0% | −0.839% | −1.417% |
| 13–24 | 29 | 51.7% | +0.396% | +2.162% |

### By entry status

| Status | n | Win | Mean excess |
|---|---:|---:|---:|
| `bounce_wait` | 38 | 28.9% | −2.651% |
| `hold` | 12 | 25.0% | −3.552% |
| `buy_now` | 5 | 80.0% | +3.398% |
| `partial` | 5 | 80.0% | +5.513% |
| `wait_pullback` | 5 | 100.0% | +8.332% |

### By V3-score quartile

| Score quartile | n | Win | Mean excess |
|---|---:|---:|---:|
| Q1 low | 17 | 58.8% | +0.452% |
| Q2 | 16 | 31.2% | −1.136% |
| Q3 | 16 | 50.0% | +0.192% |
| Q4 high | 16 | 25.0% | −3.108% |

The pattern is heterogeneous but is not a refit license. In particular, the weak
top-rank/high-score cell is a hypothesis for the governed challenger study, not
authority to change a weight or gate from four nights.

### Sector, theme, cluster, and Intelligence availability

The largest sector weights are Basic Materials and Industrials at 13/65 (20.0%)
each; sector HHI is 0.1485. The largest theme cell is unavailable theme metadata at
23/65 (35.4%); theme HHI is 0.1450. The largest recommendation-date block is also
23/65 (35.4%). Full sector, theme, sector×theme correlation-cluster, and component
tables are in the machine receipt.

Thirty-seven matured rows come from the pre-Intelligence/unavailable cohorts and
28 carry measured Intelligence components. Their mean excess is −2.114% versus
+0.752%, respectively. This is not a V4 ordering comparison: all 65 were ranked by
V3, and availability is perfectly entangled with recommendation date. Unavailable
components remain JSON null; none are coerced to zero.

## Chronology and identity caveat

The 65 matured rows have zero board-versus-candidate lane mismatches and all
decision clocks are on or before the decision date. They do not support an input
chronology or identity explanation for the current loss.

The broader current store does expose a forward accounting risk:

- 13 daily rows through the ledger date disagree with the exact-date candidate
  snapshot's lane on 2026-08-26/27;
- those become nine distinct in-flight episode admissions after carry-forward
  collapse;
- across every current board date, the mismatch is 37 rows because all 24 persisted
  2026-09-04 V4 rows disagree with the exact-date candidate snapshot, which contains
  zero `featured` rows;
- the current schema has no generation ID that can prove which candidate
  materialization produced those board rows.

This is `ACCOUNTING_OR_IDENTITY_DEFECT: FORWARD_RISK_PRESENT_NOT_CURRENT_MATURED_CAUSE`.
It does not rewrite or disqualify the 65 matured outcomes. It does mean a later wave
must bind board rows to an exact candidate generation before the nine in-flight
episodes mature, rather than guessing which same-date materialization is canonical.

## Cause ledger

| Classification | Ruling |
|---|---|
| `INPUT_CHRONOLOGY_DEFECT` | not supported for the 65 matured outcomes |
| `ACCOUNTING_OR_IDENTITY_DEFECT` | forward risk present; not the current matured cause |
| `ADMISSION_FAILURE` | not identified; no same-input admission control and only four cohorts |
| `V4_ORDERING_FAILURE` | not estimable; zero Intelligence-ordered treatment |
| `CONCENTRATION_FAILURE` | descriptive risk, not causal proof |
| `ADVERSE_SAMPLE / NOT_IDENTIFIED` | supported current ruling |
| `MIXED` | not supported as a causal label |

The negative result survives exact price and benchmark replay. The current evidence
does not identify whether it is an admission weakness, an adverse four-night sample,
or a mixture of market/regime effects. It does identify what it is not: an observed
V4 Intelligence ordering failure.

## Reproduction and hostile checks

From a Macro checkout containing this script:

```bash
python3 research/cn_prophet_recovery/r0_current_safety_replay.py \
  --source-ref 3cd4bd489ef567d86bbcf516b03f6d79062d67bb \
  --output research/cn_prophet_recovery/r0_current_safety_replay_results.json
python3 -m pytest -q tests/test_cn_prophet_recovery_r0.py
```

The hostile suite rejects carry-forward inflation, mismatched candidate populations,
rank mismatches, missing-R4-as-no-breach, fewer than 60 comparable treatment rows,
future decision clocks, null-to-zero Intelligence coercion, any live effect, and a
negative fallback result mislabeled as V4 ordering failure.

## Boundary and next owner

This R0 result changes no ranking, admission, threshold, UI, store, workflow, audit,
tripwire, serving definition, or production artifact. It does not merge or release
the held chronology candidate in PR #6567. It does not propose a new control plane.

Return to Sol with:

1. current outcome: `NEGATIVE_REAL_IMMATURE`;
2. effective ordering: `V3_FALLBACK`;
3. V4 ordering effect: `NOT_ESTIMABLE_ZERO_TREATMENT`;
4. runtime safety: `R4_ACTION_PATH_DISCONNECTED`;
5. next adjudication: preserve #6567 for R1, then repair/evaluate the existing R4
   seam in R2 under a fresh explicit operation; no serving change is authorized here.
