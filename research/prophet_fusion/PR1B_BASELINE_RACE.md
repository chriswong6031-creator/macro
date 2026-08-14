# Prophet US Conditional Fusion — PR-1b: the baseline race

**Program:** `research/PROPHET_CONDITIONAL_FUSION_MASTERPLAN_BY_FABLE.md` (§8.1 ladder,
§8.3 metrics, §8.5 data depth, §8.7 power, §9 validation, §14 row PR-1b).
**Machine table:** `research/prophet_fusion/pr1b_baseline_race/report.json`
(`schema: prophet_fusion.pr1b_race.v1`).
**Runner:** `python3 -m scripts.prophet_fusion_race --out research/prophet_fusion/pr1b_baseline_race`
**Suite:** `tests/test_prophet_fusion_race.py`

> This is a counterfactual replay on a survivorship-flagged frame at horizons that are 50% absent; it is a calibration exercise and is non-promotion-bearing (§14, §15).

`counterfactual_replay: true` · `non_promotion_bearing: true` · `survivorship_biased: true`
· `horizons_available: [5, 10, 21]` · authority stanza all-false.

Nothing here ranks, sizes, gates, originates a signal, or escalates. No rung is promoted,
proposed for promotion, or eligible for promotion: §8.6.3's era-strata condition is
unsatisfiable with one graded era, §8.6.4b bars any claim resting on a
survivorship-flagged frame, and §9.2's folds were refused rather than manufactured. The
correct verb throughout is **leads on the replay frame**.

---

## §0 What to read first, in one paragraph

Seven rungs raced on the graded-board frame. **Every 95% CI on the registered primary
tuple includes zero** — on 24 graded dates nothing separates from anything, which is
what §8.7 said would happen. The two readable shapes are: (1) the two **champion-repair**
baselines, G3 (edge leg sign-flipped) and G4 (edge leg deleted), carry the highest point
estimates of the seven, in the direction §6.6's alpha finding predicted — but G4's lead
is materially a tie-break artifact (see §7) and G3's CI vs the published order runs
−0.027 to +0.296; (2) **C1, the breadth-of-evidence rung, does not lead the champion
replay** on this frame, and its own ablation says only one of its four families is doing
distinguishable work. The most decision-relevant output of this exercise is not a
leaderboard at all — it is the measured **minimum detectable ΔP@5 of ~17.4pp**, which is
1.7× the ~10pp §8.7 registered in advance, and the receipts in §12 about which stores
disagree with each other. Seven of the 24 dates carry no frozen board payload, so the
apples-to-apples window every rung shares is **15 nights**.

---

## §1 The frame — and the three that are not it

**Raced: §8.5 frame 2, the graded-board frame, alone.** Frames are never pooled.

| | |
|---|---|
| Source | `data/us_board_ledger/retro_grades.parquet` via `scripts.prophet_fusion_labels.build_labels(frame_name="board_ledger")` |
| Champion inputs | `data/us_board_ledger/snapshots.jsonl` — the FROZEN published board payloads |
| Dates | 24 (2026-06-15 → 2026-07-31) |
| Candidates | 2,251 distinct (date, ticker) |
| Horizons | 5 (2,251 rows) · 10 (1,382) · 21 (442) · **42 (0)** · **63 (0)** |
| Population | The admitted board population, unsplit. `universe_tier` is present-but-all-null, so it is NOT called curated — it is reported as unsplit |
| Disclosed null era | 2026-08-03..08-06 excluded by the labels module, not imputed |
| `price_basis` | POOLED by explicit flag across `<null>` / `unverified_pre_20260806` / `adjusted` / `unadjusted` → the frame is tagged **exploratory** and promotion-barred (§9.4). Splitting 24 dates across four bases leaves no readable cell; the honest cost is the tag, not a hidden split |

**Frame 3 (deep price history) is REFUSED for this race,** and the refusal is a printed
result, not an omission:

- **No champion existed before 2026-06.** G0, G0′, G3 and G4 are replays or reads of a
  board that did not exist — four of the seven rungs are undefined there. A race missing
  its own baselines is not a race.
- `survivorship_biased: true` is **pre-assigned** to that frame in §8.5; §9.6 bars any
  promotion claim resting on it.
- **G2's input does not reach back**: `data/name_score/us_calls.parquet` starts
  2026-06-29.
- §8.3's identical-candidate-set law would break by construction — the deep frame's
  population is the whole investable universe, not an admitted board, and
  `DNR:KILL-PROPHET-POP-MERGE` keeps those populations apart.

**Frame 1 (the candidates store) appears only as a coverage exhibit** — it races nothing.
See §13.

---

## §2 The replay-validation gate (§6.6)

G0 is a replay of **today's** scorer over historical payloads, so the first question is
whether the replay reproduces a board whose published score we still hold. The v2-era
snapshots carry their own `prophet.score`, the five `prophet.points` and
`prophet.alpha_percentile`, which is the truth this is checked against — over the pool
that was actually scored (the buy lane), because the edge percentile is pool-relative.

| Date | `board_definition` | rows | max &#124;Δscore&#124; | byte-exact | per-leg max Δ |
|---|---|---|---|---|---|
| 2026-08-07 | `us_prophet_v1` | 78 | **16.3** | no | entry 16.25; all four others 0.0 |
| 2026-08-12 | `us_prophet_v2` | 70 | **0.0** | **yes** | all 0.0 |
| 2026-08-13 | `us_prophet_v2` | 71 | **0.0** | **yes** | all 0.0 |

Stage assignments and alpha percentiles also match exactly on all three dates
(0 mismatches).

The 08-07 divergence is the receipt §6.6 predicted, to the decimal: **16.3 points, all of
it in the entry leg**, the v1→v2 entry re-valuation. Two eras are not one score scale. A
v1 mismatch is a receipt; a v2 mismatch would be a defect, and the CLI refuses to emit
results when no v2 board reproduces byte-exact (mutation-tested: moving the signal weight
30.0 → 31.0 produces `ReplayValidationRefusal` and no report).

The replay calls `engine.us_board_rank`'s own functions — `verdict_for`, `signal_value`,
`entry_value`, `alpha_percentiles`, `edge_value`, `runway_value`, `quality_value`,
`stage_for` — so a future re-tune of any constant moves the replay in lockstep instead of
silently forking from it. `engine/us_board_rank.py` was not modified by this PR.

**Known limit, named:** the replay resolves the gate verdict through `verdict_for`, which
falls back to the row's embedded `signal` blob because the snapshot carries no separate
signal-gate map. That module's own docstring records the two copies legitimately
disagreeing (8 of 69 buy rows on 2026-08-12). A residual per-row mismatch on some future
date would be attributable there first.

---

## §3 The seven rungs, and what each refused

Every rung ranks the **identical per-date candidate set** — the label frame's own
(date, ticker) pairs (§8.3). No rung drops a NAME; a rung missing its input for a DATE
refuses that whole date and is listed. Pairwise comparisons are paired on common dates
and print their n. Candidate-set equality is machine-verified in the report
(`exhibits.candidate_sets_identical.ok = true`).

| Rung | Construction | Dates raced | Refused |
|---|---|---|---|
| **G0** | Champion legs (30/25/25/10/10) over the frozen payload; sort `(stage_rank, −score, ticker)` | 17 | 7 — no frozen payload (2026-06-15..06-24) |
| **G0′** | Lane-major then published position, off the ledger's own `lane`/`position`. Lane map disclosed: `buy 0, watch 1, leaders 2, laggards 3`. Deployed by construction | 24 | 0 |
| **G1** | `alpha` descending, ticker tiebreak | 24 | 0 |
| **G2** | `conviction.potential.score` off the frozen payload (the PUBLISHED name_score) | 17 | 7 — no frozen payload |
| **G3** | G0 with **−alpha** fed through the same `alpha_percentiles`/`edge_value` machinery | 17 | 7 — no frozen payload |
| **G4** | `(30·signal + 25·entry + 10·runway + 10·quality) × (100/75)` | 17 | 7 — no frozen payload |
| **C1** | Per-member within-date percentile of the sign-oriented value → per-family mean → equal-weight mean of present families | 24 | 0 |

The 7 refused dates are the whole of 2026-06-15..06-24: `snapshots.jsonl` begins
2026-06-30, so the champion's own inputs cannot be reconstructed for them without
re-deriving from today's stores — which would be leakage, not a replay (§9.1).

**Within a raced date, a missing leg input resolves through the champion's OWN
fail-closed rule** (unknown extension earns 0 runway; a cleared tier earns 0 signal) and
is disclosed per-leg per-date in `replay_leg_availability`. That is the behaviour that
shipped, and the race reports it rather than smoothing it away.

### Pool disclosure (§6.7.2)

G0/G3/G4 recompute the pool-relative edge percentile over **the raced candidate set**
(all lanes), not the buy lane, because §8.3 forbids a rung from ranking a different
population than its rivals. That is the same arithmetic on a different pool, and the
difference is real — §6.7.2 measured the zero-boundary moving on pool composition alone.
The validation in §2 therefore runs on the PUBLISHED pool and this race does not claim to
reproduce published scores on the graded window (where no published prophet score exists
at all — §6.1, N=0).

---

## §4 Headline — H=10, deployed composition, classes POOLED

Registered primary tuple, published before any outcome cell in `report.json` (asserted as
a byte offset by the suite): **P@5 + top-5 mean excess, H=10 sessions, deployed
composition `(stage_rank, −score, ticker)`, classes pooled** — one tuple per rung, seven
registered comparisons.

**Classes are pooled because they cannot be split**: the grades store's
`universe_tier`/`signal_class` cohort columns are null by a named sibling-lane debt (§7
population enforcement), so class-conditional claims are impossible on this frame and
none is made.

### 4.1 On the 15 common dates (apples-to-apples)

The rungs do not all race the same nights. This table puts every rung on the
intersection.

| Rung | P@1 | P@3 | **P@5** | P@10 | **top-5 mean** | top-5 median | large-loser (top-10, <−3pp) | Spearman | large-winner capture | distinct-score ratio |
|---|---|---|---|---|---|---|---|---|---|---|
| G0 | 0.467 | 0.533 | 0.493 | 0.527 | **+0.06pp** | +0.08pp | 0.373 | +0.007 | 0.143 | 0.845 |
| G0′ | 0.467 | 0.489 | 0.440 | 0.473 | **−1.39pp** | −0.63pp | 0.440 | −0.001 | 0.128 | 1.000 |
| G1 | 0.333 | 0.467 | 0.440 | 0.487 | **−0.45pp** | −0.71pp | 0.393 | −0.043 | 0.126 | 0.885 |
| G2 | 0.538 | 0.533 | 0.477 | 0.510 | **+0.18pp** | −0.88pp | 0.403 | −0.041 | 0.152 | 0.565 |
| **G3** | 0.667 | 0.633 | **0.568** | 0.556 | **+1.26pp** | +0.16pp | **0.303** | +0.019 | 0.145 | 0.862 |
| **G4** | 0.600 | 0.578 | **0.560** | 0.520 | −0.14pp | −0.63pp | 0.353 | +0.017 | 0.129 | **0.422** |
| C1 | 0.333 | 0.489 | 0.453 | 0.493 | −0.51pp | −1.56pp | 0.393 | −0.034 | 0.156 | 0.883 |

### 4.2 On each rung's own dates (n printed)

| Rung | P@5 | top-5 mean | n dates with a measured H=10 | dates refused by the DEPLOYED cell |
|---|---|---|---|---|
| G0 | 0.493 | +0.06pp | 15 | 0 |
| G0′ | 0.435 | −1.55pp | 17 | 0 |
| G1 | 0.440 | −0.45pp | 15 | 7 |
| G2 | 0.477 | +0.18pp | 15 | 0 |
| G3 | 0.568 | +1.26pp | 15 | 0 |
| G4 | 0.560 | −0.14pp | 15 | 0 |
| C1 | 0.453 | −0.51pp | 15 | 7 |

**Why G1 and C1 refuse 7 dates in the DEPLOYED cell even though they race 24.** G1, G2
and C1 have no stage of their own — §8.3's deployed composition substitutes their score
into the CHAMPION's bucketing, which they borrow from the G0 adapter, which needs a
frozen payload. On the 7 dates that have none there is no stage to borrow, so those
dates leave the deployed cell and are named in `composition_unavailable_dates`. Filling
the missing rank with a constant would have published a RAW ordering under the DEPLOYED
label — the one comparison §8.3 says must never be blurred. G0′ keeps all its dates
because it IS the deployed order rather than a score substituted into one.

*(This was a real defect in the first cut of this race and is recorded rather than
quietly corrected: `pandas.Series.where` treats a `pd.NA` condition as False, so the
null stage ranks were being assigned bucket 0. It moved G1's headline P@5 from a
raw-contaminated 0.424 to 0.440 and C1's from 0.447 to 0.453, and it is now pinned by
`test_a_date_with_no_computable_stage_is_dropped_from_the_deployed_cell`.)*

### 4.3 Deltas vs BOTH anchors — date-blocked paired bootstrap (B=2000, seed 20260814)

`DNR:LAW-TIME-CLUSTERED-CI`: dates are the block, resampled with replacement; the
statistic is the mean per-date difference.

| Rung | vs | ΔP@5 | 95% CI | excl. 0 | Δtop-5 mean | 95% CI | excl. 0 | n common |
|---|---|---|---|---|---|---|---|---|
| G1 | G0 | −0.053 | [−0.147, +0.053] | no | −0.51pp | [−2.06, +1.00] | no | 15 |
| G1 | G0′ | +0.000 | [−0.160, +0.160] | no | +0.94pp | [−1.49, +3.32] | no | 15 |
| G2 | G0 | −0.017 | [−0.123, +0.077] | no | +0.12pp | [−2.24, +2.25] | no | 15 |
| G2 | G0′ | +0.037 | [−0.103, +0.187] | no | +1.57pp | [−0.94, +4.17] | no | 15 |
| G3 | G0 | **+0.074** | [−0.050, +0.199] | no | +1.20pp | [−1.57, +3.98] | no | 15 |
| G3 | G0′ | **+0.128** | [−0.027, +0.296] | no | +2.65pp | [−0.56, +6.11] | no | 15 |
| G4 | G0 | +0.067 | [−0.027, +0.174] | no | −0.20pp | [−1.28, +0.93] | no | 15 |
| G4 | G0′ | +0.120 | [−0.040, +0.293] | no | +1.26pp | [−1.23, +3.94] | no | 15 |
| C1 | G0 | −0.040 | [−0.133, +0.053] | no | −0.58pp | [−2.06, +1.01] | no | 15 |
| C1 | G0′ | +0.013 | [−0.133, +0.147] | no | +0.88pp | [−1.41, +3.21] | no | 15 |

**Every interval includes zero.** §8.1's registered minimum increment (ΔP@5 ≥ +3pp with
the CI excluding zero) is met by no rung against either anchor.

---

## §5 Secondary horizons — reported, not headlined

H=5 and H=21 are secondary by the §8.3 prereg. H=21 is **flagged thin**: 442 rows on the
whole frame and only **7 dates** carry an H=21 grade.

| Rung | H=5 P@5 (n=17–24) | H=5 top-5 mean | H=21 P@5 (n=7) | H=21 top-5 mean | H=21 large-loser (<−10pp) |
|---|---|---|---|---|---|
| G0 | 0.518 | −0.05pp | 0.514 | +2.23pp | 0.100 |
| G0′ | 0.442 | −0.57pp | 0.536 | +1.41pp | 0.133 |
| G1 | 0.435 | −0.60pp | 0.429 | −0.46pp | 0.114 |
| G2 | 0.518 | +0.17pp | 0.571 | +0.95pp | 0.186 |
| G3 | 0.529 | +0.01pp | 0.571 | +2.87pp | 0.143 |
| G4 | 0.541 | −0.45pp | 0.543 | +1.50pp | 0.159 |
| C1 | 0.400 | −1.18pp | 0.429 | −1.88pp | 0.114 |

**H=42 and H=63: ZERO graded rows.** Printed as explicit nulls in `report.json`, never
omitted and never proxied by a neighbouring horizon. No `basing`-class claim is possible
until H=63 has a ruler with data (§8.6.4).

**H=5 has no registered large-loser threshold** (`FRAGILITY_BY_HORIZON` registers only
H=10 at −3pp and H=21 at −10pp), so that cell is null rather than handed H=10's number.

---

## §6 Tails, MFE and MDD — with the basis named

`top-10 MFE / MDD medians @H=10, deployed`, with coverage:

| Rung | MFE median | MFE coverage | MDD median | MDD coverage | expected shortfall (worst decile of top-10) |
|---|---|---|---|---|---|
| G0 | +4.11pp | 0.88 | −3.86pp | 0.88 | −11.10pp |
| G0′ | +3.19pp | 0.62 | −4.20pp | 0.71 | −12.55pp |
| G1 | +3.68pp | 0.88 | −3.91pp | 0.88 | −11.20pp |
| G2 | +4.46pp | 0.87 | −4.29pp | 0.87 | −12.92pp |
| G3 | +4.77pp | 0.86 | −3.29pp | 0.86 | −11.55pp |
| G4 | +4.32pp | 0.87 | −3.61pp | 0.87 | −11.53pp |
| C1 | +3.63pp | 0.88 | −3.92pp | 0.88 | −10.81pp |

> **`mdd_basis = mae_close_excess_spy`. This is NOT a true intrabar maximum drawdown.**
> On this frame `mdd` resolves to a **close-based maximum adverse excursion measured on
> closes against SPY**. It understates a real MDD by exactly the intraday range it cannot
> see, and it is an EXCESS series, not a price drawdown. Every `MDD median` above is that
> quantity and nothing else. (PR-1a review advisory A1, closed here by naming the
> resolved column in `report.json` rather than by changing the number.)

---

## §7 Tie structure — and how much of the table is the alphabet

`(stage_rank, −score, ticker)` breaks ties alphabetically. On a compressed score that is
a real ordering authority, so it is measured rather than assumed.

| Rung | distinct-score ratio (mean/date) | dates with top-5 boundary ties | P@5 alphabetic | P@5 random-tiebreak min / max | spread |
|---|---|---|---|---|---|
| G0 | 0.853 | 0 | 0.493 | — | — |
| G0′ | 1.000 | 0 | 0.435 | — | — |
| G1 | 0.882 | 2 | 0.440 | — | — |
| G2 | 0.541 | 5 | 0.477 | 0.477 / 0.493 | 0.017 |
| G3 | 0.866 | 0 | 0.568 | — | — |
| **G4** | **0.449** | **11** | 0.560 | **0.520 / 0.613** | **0.093** |
| C1 | 0.883 | 2 | 0.453 | 0.453 / 0.453 | 0.000 |

(B=200 random tie-breaks, seed 20260816; triggered for C1 always plus any rung with
boundary ties on ≥3 dates — so G2, G4 and C1 were re-run and the rest were not.)

**The load-bearing row is G4.** Deleting the edge leg leaves the entry leg — which the
ANTICIPATION-v1 ladder made **flat at 1.0 across all five admissible statuses** — so G4's
score collapses onto a 0.42 distinct-score ratio and its top-5 boundary is decided by the
tiebreak on 11 of 15 dates. Its headline 0.560 could have been anywhere in
**[0.520, 0.613]** on a different tiebreak. G4's point estimate is not a clean reading of
the deletion hypothesis; it is partly an artifact of which tickers sort first.

C1's spread is exactly 0.000 despite ties on 2 dates: its tied groups sit entirely inside
or entirely outside the top-5, so the alphabet is not doing work there.

---

## §8 Permutation floor (exploratory) and BH-FDR

### 8.1 Ordering-vs-random floor

Within-date score shuffle, B=1000, seed 20260815; statistic = top-5 mean excess @H=10
deployed. **This is NOT §9.5's name-permutation null** (that binds C3+ and shuffles NAMES
against a fitted model to prove it did not memorize them). This asks only "is this order
better than an arbitrary order of the same names?" — a floor, claimable for nothing.

| Rung | observed | null mean | null sd | one-sided p |
|---|---|---|---|---|
| G0 | +0.06pp | −0.07pp | 0.90pp | 0.436 |
| G0′ | −1.55pp | +0.45pp | 1.02pp | **0.974** |
| G1 | −0.45pp | +0.05pp | 0.85pp | 0.711 |
| G2 | +0.18pp | −0.12pp | 0.92pp | 0.371 |
| G3 | +1.26pp | −0.13pp | 0.92pp | **0.067** |
| G4 | −0.14pp | −0.24pp | 0.90pp | 0.426 |
| C1 | −0.51pp | +0.06pp | 0.84pp | 0.747 |

G3 is the only rung within sight of the floor, and it does not clear 0.05. **G0′ at
p=0.974** says the published order's top-5 sat below 97% of random orderings of the same
names on this frame — the same shape §6.6 reported from the published-order read, on a
narrower window and with the floor attached.

### 8.2 BH-FDR over the secondary table

Axis: model × metric × horizon × composition, against the G0 anchor. **227 tests, 2
rejected** at α=0.05 (hand-rolled Benjamini-Hochberg; per-cell p from a paired
date-blocked mean difference with a two-sided normal approximation, disclosed):

| Rung | metric | H | composition | p | p adj | reject |
|---|---|---|---|---|---|---|
| G2 | large-loser rate top-10 | 21 | raw | 0.0001 | 0.0100 | **yes** |
| G0′ | P@3 | 5 | deployed | 0.0001 | 0.0100 | **yes** |
| G2 | large-loser rate top-10 | 21 | deployed | 0.0010 | 0.0524 | no |
| G0′ | P@5 | 5 | deployed | 0.0012 | 0.0524 | no |
| C1 | P@3 | 5 | deployed | 0.0012 | 0.0524 | no |

Both survivors are secondary cells on the thin end of the frame (H=21 has 7 dates; the
H=5 cells are off the headline horizon). §8.3 registers ONE primary tuple per rung, and
the two primary cells are excluded from this table **by prereg, not by result**.

---

## §9 C1 — is this one family, several independent families, or correlated siblings?

### 9.1 Who actually voted

Coverage floor 0.50 non-null on the frame. The floors decided; nothing was pre-excluded
for looking weak or kept for looking strong.

**Raced (6 members, 4 families):**

| Column | Family | Sign | Coverage | Sign source |
|---|---|---|---|---|
| `alpha` | F2 | + | 1.000 | registry F2.residual_alpha — the axis the champion's edge leg reads. §6.6's NEGATIVE measurement is an outcome and is not a sign source |
| `off_high` | F2 | + | 1.000 | registry F2.relative_strength semantics — nearer zero is nearer the high |
| `sue_fresh` | F4 | + | 0.663 | registry F4.sue_surprise — PEAD's a-priori direction. Carries the binding `sue_phase0.json` reversal warning |
| `smartmoney_add` | F5 | + | 0.663 | registry F5.smart_money_board_chip — 13F ADD direction |
| `insider_cluster` | F5 | + | 0.663 | registry F5.insider_panel — ≥2 insider BUYERS |
| `news_burst` | F8 | + | 0.663 | PR-1b filed adjudication — **the weakest a-priori sign in the set, named as such** |

**Dropped by the coverage floor:** `tier_cascade` (0.250) → F1 loses its only candidate;
`gex_confirm_verdict` (0.209).

**Families absent, with reasons that are not interchangeable:**

| Family | Status |
|---|---|
| F1 TECHNICAL-CONFLUENCE | no surviving member — `tier_cascade` at 25% coverage |
| F3 THEME-STRUCTURE | **absent from frame** — the frozen payload carries no theme/basket/relay evidence column (`sector` is identity; `donor_*` are page-level constants) |
| F6 MACRO-REGIME | **STRUCTURALLY EXCLUDED, not missing** — row-constant per night; measured in §14 |
| F7 QUALITY-FUNDAMENTAL | **absent from frame** — the only F7-adjacent column is `archetype`, which §5.1 routes through #5583's fingerprint interfaces, never raw; no a-priori ordinal direction is filed for a nominal category and reading one off this frame's outcomes would be an audition |

**Options columns are present and left OUT of C1 v1** (22 `opt_*` columns): no single
a-priori member direction is filed for them, and picking signs from this frame's outcomes
is the audition §8.2/§9.8 forbids. §6.6's `opt_iv30` signature is logged-not-claimed and
is not a filed direction.

**Family coverage per row** — 1,493 rows carry all four families; **758 rows carry
exactly one (F2)**. Those 758 are the whole of 2026-06-15..06-24, before the W3
evidence-stack columns existed. **On 7 of 24 dates, C1 IS an alpha/off-high blend and
nothing more**, and any read of C1 that ignores that is reading two different models
averaged together.

Duplicate collapse: 0 members collapsed (no two oriented percentile vectors were
identical).

### 9.2 Leave-one-family-out (H=10, deployed)

| Family removed | ΔP@5 (base − without) | 95% CI | Δtop-5 mean |
|---|---|---|---|
| F2 MOMENTUM-EXTENSION | **−0.040** | [−0.133, +0.067] | −0.10pp |
| F4 CATALYST-EVENT | +0.013 | [−0.040, +0.054] | −0.38pp |
| F5 FLOW-POSITIONING | +0.027 | [+0.000, +0.067] | +0.13pp |
| F8 ATTENTION-CROWDING | **+0.000** | [+0.000, +0.000] | +0.00pp |

Read the signs carefully: a **negative** Δ means C1 scored *better without that family*.
**F2 is the only family whose removal improves C1**, by 4.0pp of P@5 (CI still spanning
zero) — the same direction as §6.6's alpha finding and as G1's own position in §4.

**F8's LOFO delta is exactly zero, on every date, with a CI of [0.000, 0.000].** That is
not a rounding artifact and it is worth stating plainly: `news_burst` fires True on
**19 of 1,493** measured rows, so its within-date percentile is a near-constant, and
adding a per-date constant to a mean cannot reorder anything. The 19 True rows never
crossed a top-5 boundary. The coverage
floor let F8 in on non-null share (0.663 — the Falses are measured negatives) and the
tape shows it cast no distinguishing vote. **A coverage floor measures presence, not
cross-sectional variance**, and this is the frame's demonstration of the gap.

### 9.3 Single-family-only rankers (each family alone)

| Family alone | P@5 | top-5 mean | top-5 median | large-loser | Spearman |
|---|---|---|---|---|---|
| F2 | 0.440 | −0.08pp | −1.65pp | 0.373 | **−0.082** |
| F4 | 0.453 | −1.25pp | −1.09pp | 0.424 | +0.010 |
| F5 | **0.467** | −0.34pp | −0.97pp | 0.402 | **+0.073** |
| F8 | 0.447 | −0.74pp | −1.33pp | 0.416 | +0.075 |

(15 dates each — the deployed composition, same window as §4.1.)

### 9.4 Incremental over the champion replay (partial Spearman | G0)

Rank-residual partial correlation within date: rank every series inside the night, regress
the family rank and the outcome rank on the G0-replay rank, correlate the residuals;
date-blocked bootstrap CI over nights.

| Family | ρ vs outcome | 95% CI | n dates | partial ρ &#124; G0 | 95% CI |
|---|---|---|---|---|---|
| F2 | **−0.076** | [−0.138, −0.011] | 17 | **−0.083** | [−0.154, −0.007] |
| F4 | +0.010 | [−0.047, +0.063] | 12 | +0.012 | [−0.049, +0.066] |
| F5 | **+0.073** | [+0.020, +0.128] | 15 | **+0.074** | [+0.017, +0.130] |
| F8 | +0.075 | [−0.011, +0.163] | 6 | +0.078 | [−0.014, +0.174] |

Two intervals exclude zero on the exploratory table: **F2 negative** and **F5 positive**,
and in both cases conditioning on the champion replay barely moves the estimate — what
they carry, the champion is not carrying. F8's read is on **6 dates** and is unreadable.
Every cell here is exploratory and promotion-barred (§8.3).

### 9.5 Own-family conditioning (families with ≥2 surviving members)

| Member | Family | ρ vs outcome | partial ρ &#124; siblings | 95% CI |
|---|---|---|---|---|
| `alpha` | F2 | −0.061 | −0.031 | [−0.104, +0.045] |
| `off_high` | F2 | −0.075 | −0.055 | [−0.131, +0.018] |
| `insider_cluster` | F5 | +0.031 | +0.034 | [−0.031, +0.098] |
| `smartmoney_add` | F5 | +0.050 | +0.051 | [−0.004, +0.111] |

No member's incremental-over-its-siblings interval excludes zero. Inside F2, `alpha` and
`off_high` each lose about half their (negative) correlation when conditioned on the
other — they are partly the same reading, which is what §5.1's F2 redundancy note says
they should be. Inside F5, `insider_cluster` and `smartmoney_add` barely move each other:
those two are close to independent, and F5's §9.4 signal is not one member wearing two
hats.

### 9.6 Family × family per-date Spearman

| | F2 | F4 | F5 | F8 |
|---|---|---|---|---|
| **F2** | 1.00 | +0.245 | −0.131 | −0.103 |
| **F4** | +0.245 | 1.00 | −0.037 | −0.024 |
| **F5** | −0.131 | −0.037 | 1.00 | +0.105 |
| **F8** | −0.103 | −0.024 | +0.105 | 1.00 |

### 9.7 The answer to the section's question

On this frame, as raced: **not one family, not four independent ones — one family (F5)
doing distinguishable work, one (F2) pointing the wrong way, one (F4) at zero, and one
(F8) cross-sectionally degenerate.** The cross-family correlations are small (|ρ| ≤ 0.25),
so the four are not correlated siblings *of each other*; the redundancy that matters here
is **within** F2. C1's equal-weight construction spends a quarter of its vote on a family
whose LOFO says it subtracts 4.0pp and a quarter on a family that does literally nothing.
That is an argument about C1's WEIGHTS, which is exactly the question C2 is registered to
ask — and it is not an argument that breadth of evidence fails, because the breadth here
is four families of which two are unreadable.

> `insider_cluster` carries §8.5's **train/serve skew** warning: the panel collector
> stopped at 2026q1, so a model trained on it finds the feature dead at serving time. It
> is raced here because C1 is an unfitted glass-box vote on a frozen historical frame,
> and the skew is printed beside the number rather than the column being silently
> pre-excluded. Any FITTED rung must exclude it until the collector is repaired.

---

## §10 §8.7 power — the most decision-relevant table in this document

Written into `report.json` **before** any outcome cell (byte-offset asserted by the
suite).

| | |
|---|---|
| Registered comparisons | **7** (the rung set × one primary tuple) |
| Primary tuple | P@5 + top-5 mean excess, H=10, deployed composition, classes pooled |
| FDR axis | model × metric × horizon on the SECONDARY table; primaries exempt by prereg |
| Slices | exploratory by construction, structurally barred from any §8.6 claim |
| Date-blocks per rung | G0 17 · G0′ 24 · G1 24 · G2 17 · G3 17 · G4 17 · C1 24 (H=10 measured: 15/17/17/15/15/15/17) |
| **Observed date-blocked SE of ΔP@5** | **0.049 – 0.089** across the ten challenger-vs-anchor pairs |
| **Implied minimum detectable ΔP@5** | **≈ 0.174 (17.4pp)** = 1.96 × the largest observed SE |
| §8.7 registered expectation | SE ≈ 0.03–0.04, i.e. detect ≈ +10pp and nothing smaller |

**The measured SE is 1.2–2.2× the registered one, so the smallest readable ΔP@5 on this
frame is ~17.4pp, not ~10pp.** §8.1's registered minimum increment is +3pp. The gate is
therefore roughly **six times** less sensitive than the increment it is meant to
adjudicate. That is the single number a later generation should carry forward.

### Distance to power ("need ≥N, have n")

- **Need ≥60 graded prophet-era dates** (minimum-usable-fold, §9.2) — **have 24** graded
  board dates, and **zero of them carry a published prophet score** (§6.1: the live score
  has never been graded, N=0). Every G0 number in this document is a replay.
- **Need ≥50 top-K episodes at the headline horizon** (§8.6.4) — H=10 has **17 graded
  dates**, an upper bound of **85 top-5 slots** before episode de-duplication (distinct
  name × admission episode is smaller, often much smaller, because names persist on the
  board night to night).
- **Need a SECOND graded selection era** for §8.6.3's era-strata condition — there is
  one. That half of the gate is **unsatisfiable today**, the gate cannot pass before then,
  and that is the intended reading, not a defect.
- **Need H=42/63 rows** for any basing-class claim — there are **none**.

### The §9.2 fold refusal, verbatim

> `fold 0 refused (§9.2 minimum-usable-fold): 0 train dates after purge+embargo (minimum 60) and 4 test dates (minimum 10), at horizon=21 embargo=21 over 24 distinct dates. The harness refuses the fold; it never silently shrinks one.`

Usable folds: **0**. **No fold was manufactured.** Every number in this document is an
in-sample descriptive read of a frozen frame, which is what a non-promotion-bearing
calibration exercise is allowed to be.

---

## §11 Per-date table — H=10, deployed, `P@5 / top-5 mean excess (pp)`

| date | n | G0 | G0′ | G1 | G2 | G3 | G4 | C1 |
|---|---|---|---|---|---|---|---|---|
| 2026-06-15 | 97 | — | 0.60 / +0.06 | — | — | — | — | — |
| 2026-06-16 | 95 | — | 0.20 / −5.59 | — | — | — | — | — |
| 2026-06-17 | 113 | — | — | — | — | — | — | — |
| 2026-06-18 | 107 | — | — | — | — | — | — | — |
| 2026-06-22 | 117 | — | — | — | — | — | — | — |
| 2026-06-23 | 115 | — | — | — | — | — | — | — |
| 2026-06-24 | 114 | — | — | — | — | — | — | — |
| 2026-06-30 | 70 | 0.60 / +6.94 | 0.60 / +5.90 | 0.80 / +7.99 | 0.60 / +3.43 | 0.40 / −1.87 | 0.60 / +1.46 | 0.60 / +5.02 |
| 2026-07-01 | 75 | 0.80 / +2.99 | 1.00 / +6.36 | 0.40 / −2.01 | 0.60 / +0.55 | 0.80 / +4.27 | 0.80 / +2.41 | 0.40 / −2.01 |
| 2026-07-02 | 60 | 0.40 / −3.05 | 0.60 / +1.78 | 0.40 / −1.34 | 0.60 / −0.30 | 0.60 / −1.15 | 0.40 / −2.34 | 0.40 / −1.34 |
| 2026-07-06 | 56 | 0.40 / −4.88 | 0.40 / −2.77 | 0.80 / +1.83 | 0.60 / −4.10 | 0.40 / −7.70 | 0.40 / −7.85 | 0.80 / +1.83 |
| 2026-07-09 | 56 | 0.40 / −0.26 | 0.60 / +0.08 | 0.20 / −0.12 | 0.40 / −2.40 | 0.40 / −0.26 | 0.40 / −0.26 | 0.60 / +1.53 |
| 2026-07-10 | 66 | 0.80 / +3.83 | 0.60 / +3.07 | 0.80 / +2.60 | 0.80 / +3.49 | 1.00 / +3.49 | 1.00 / +3.49 | 0.80 / +2.60 |
| 2026-07-14 | 66 | 1.00 / +9.19 | 0.80 / +1.12 | 0.80 / +2.77 | 0.60 / +8.62 | 0.80 / +10.30 | 0.80 / +8.07 | 0.80 / +7.07 |
| 2026-07-15 | 64 | 0.40 / −3.23 | 0.60 / −1.75 | 0.40 / −1.09 | 0.40 / +0.41 | 0.40 / −2.79 | 0.20 / −4.32 | 0.40 / −1.09 |
| 2026-07-17 | 75 | 0.40 / −1.21 | 0.20 / −8.93 | 0.40 / −0.61 | 0.40 / −2.83 | 0.60 / −0.27 | 0.40 / −0.46 | 0.40 / −1.74 |
| 2026-07-20 | 80 | 0.60 / +0.73 | 0.20 / −5.54 | 0.40 / −0.30 | 0.80 / +3.00 | 0.80 / +5.89 | 0.60 / +0.48 | 0.40 / −0.73 |
| 2026-07-21 | 83 | 0.40 / −1.26 | 0.60 / −2.59 | 0.20 / −2.06 | 0.20 / +0.01 | 0.40 / +1.60 | 0.40 / −1.17 | 0.20 / −1.55 |
| 2026-07-24 | 79 | 0.60 / +4.47 | 0.20 / −4.25 | 0.60 / +5.70 | 0.20 / −6.66 | 0.20 / −3.15 | 0.60 / +4.82 | 0.60 / +4.47 |
| 2026-07-27 | 79 | 0.20 / −4.64 | 0.20 / −3.56 | 0.00 / −7.86 | 0.20 / +0.79 | 0.80 / +10.67 | 0.40 / −4.50 | 0.00 / −7.83 |
| 2026-07-28 | 151 | 0.20 / −2.93 | 0.00 / −6.07 | 0.40 / −3.86 | 0.50 / +6.31 | 0.67 / +6.21 | 0.80 / +1.99 | 0.20 / −8.30 |
| 2026-07-29 | 144 | 0.20 / −5.76 | 0.00 / −3.73 | 0.00 / −8.40 | 0.25 / −7.64 | 0.25 / −6.31 | 0.60 / −3.87 | 0.20 / −5.61 |
| 2026-07-30 | 147 | — | — | — | — | — | — | — |
| 2026-07-31 | 142 | — | — | — | — | — | — | — |

Nine dates carry no H=10 grade at all (2026-06-17..06-24 and 07-30/07-31 — the tail has
not matured). Seven carry no frozen payload, which costs G0/G2/G3/G4 the date outright
and costs G1/C1 their DEPLOYED cell for it (§4.2). Only G0′ scores 2026-06-15/06-16, and
the intersection every rung shares is the 15 dates §4.1 uses.
**A leaderboard built on 15 nights is a leaderboard built on 15 nights**, and the spread
of individual cells above (from −8.93pp to +10.67pp on one rung-date) is the honest
picture of how much any of these means.

---

## §12 Receipts on the stores themselves

### 12.1 Store/ledger delta (§6.7.5)

Raced rows absent from the frozen payload: **0**. Payload rows not raced: **19** across
the 17 overlapping dates (1–5 per date, concentrated on 07-28..07-31). These are the label
builder's `(date, ticker, horizon)` dedupe of a name sitting in two lanes on one night —
one outcome, not two. The arena joins on the SNAPSHOT (what shipped) and discloses the
delta rather than reconciling it silently.

### 12.2 G2 cross-check — the two memories of `name_score` DISAGREE

Joining the board's published `conviction.potential.score` to
`data/name_score/us_calls.parquet` on `(date, ticker)`:

| date | n joined | exact match | match rate | max &#124;Δ&#124; |
|---|---|---|---|---|
| 2026-06-30 | 70 | 20 | **0.286** | 51 |
| 2026-07-01 | 75 | 17 | **0.227** | 99 |
| 2026-07-02 | 60 | 15 | **0.250** | 55 |

**A one-session lag was tested and rejected**: the same-date join is the best match on
every date tried (2026-06-30 / 07-01 / 07-31 — the ±6-day sweep on 07-31 gives 0.297
same-date vs 0.110–0.145 at every offset). So roughly three quarters of names disagree,
by up to the full 0-100 range, between the board's published potential and the store's
own row for the same day.

This does **not** move G2: G2 races the PUBLISHED board value, which is what the product
actually showed. It says the two writes of one producer are not the same series, and that
**a future rung reading the STORE would be racing a different quantity than G2 does
here**. Filed as a §6.7.5-class provenance fact for the owning lane.

### 12.3 `name_score` PIT-append receipt

`git show <sha>:data/name_score/us_calls.parquet` into a temp file, then assert
`max(date) <= the commit's own date`:

| commit | commit date (UTC) | rows | max date in file | verdict |
|---|---|---|---|---|
| `0324e0c7a012` | 2026-08-14 | 88,056 | 2026-08-14 | APPEND-ONLY as of this commit |
| `44c90f8f547c` | 2026-08-13 | 86,361 | 2026-08-13 | APPEND-ONLY as of this commit |

**Both PIT-OK.** A note on how this receipt was nearly wrong: the first implementation
compared against the committer's LOCAL date and flagged `0324e0c7a012` as a violation. The
nightly commits at ~23:00 PDT carry the NEXT UTC session date in their rows — and in their
own subject line, "engine: regime update 2026-08-14". The comparison is now normalized to
UTC, and the false positive is recorded here because a PIT receipt that cries wolf is
worse than none.

---

## §13 Frame-1 coverage exhibit (races nothing)

| stamp | rows | tiers |
|---|---|---|
| 2026-07-31 | 2,933 | curated 1, **null 2,932** |
| 2026-08-05 | 1,513 | scan 1,513 |
| 2026-08-06 | 1,509 | scan 1,509 |
| 2026-08-07 | 4,737 | curated 1,717 · scan 3,020 |
| 2026-08-12 | 1,508 | scan 1,508 |

- **`data/us_prophet_rank/grades/` does not exist.** Not "is empty" — the directory is
  not materialized at all, and it has **zero matured rows**. Frame 1 has no outcomes to
  race against, at any horizon, today. That is a §8.7 fact and it is printed rather than
  inferred.
- **The 2026-08-08 .. 2026-08-13 gap is printed as a gap.** No stamp exists for those
  dates and nothing here backfills one — a backfilled context vector is a snapshot join
  wearing a historical date (§9.1). The gap is the measurement.
- **Universe-widening break** (§7 era hygiene): 08-05/06 carry scan rows only, 08-07
  carries 1,717 curated. Coverage is reported PER STAMP DATE and never pooled across it.
- 2026-08-12 is a stamp the masterplan's §8.5 census did not have (it recorded four); it
  carries scan rows only.

---

## §14 F6 row-constancy — measured, not asserted

§5.1 calls F6 cross-sectionally degenerate by construction. This frame agrees, on every
column and every date:

| column | dates with a measured value | dates row-constant | max distinct values inside one date |
|---|---|---|---|
| `quad_hard_label` | 16 | 24 | **1** |
| `vol_regime` | 16 | 24 | **1** |
| `rate_pressure` | 14 | 24 | **1** |
| `fused_risk_label` | 16 | 24 | **1** |
| `risk_radar_state` | 16 | 24 | **1** |
| `dispersion_state` | 21 | 24 | **1** |
| `regime_vector_degraded` | 16 | 24 | **1** |

A column with one distinct value per night cannot ORDER names inside that night. F6 is
**structurally excluded** from C1, which is a different fact from a family whose columns
the frame does not carry — and the report keeps them apart.

---

## §15 What this race does NOT answer

1. **Whether the champion has selection alpha.** It has never been graded (§6.1, N=0).
   Every G0 number here is a replay of today's constants over historical inputs, on a
   window where the board was ordering by `bottoming-alignment` and `confluence`.
2. **Whether G3/G4's shape survives.** Both sit inside their CIs, both lean on 15 nights,
   and G4's specifically leans on a tiebreak (§7). "The edge leg may be pointing the wrong
   way" is a HYPOTHESIS that §6.6 raised and this race did not close.
3. **Whether breadth of evidence pays.** C1 raced four families of which one is
   cross-sectionally degenerate and one is absent-in-all-but-name; §8.1's C1 question
   ("does breadth help at all") cannot be answered by a vote with two readable voters.
4. **Anything class-conditional.** The cohort columns are null (§7).
5. **Anything at H=42/63.** Zero rows.
6. **Anything about serving-time behaviour** for `insider_cluster` (collector stopped
   2026q1) or the options columns (9–12% coverage, no filed directions).

## §16 Reproducing this

```
python3 -m scripts.prophet_fusion_race --out research/prophet_fusion/pr1b_baseline_race
python3 -m pytest tests/test_prophet_fusion_race.py tests/test_prophet_fusion_families.py \
                  tests/test_prophet_fusion_arena.py tests/test_prophet_fusion_labels.py -q
```

`report.json` carries **no wall-clock stamp** on purpose: two runs of the same CLI over
the same repo produce byte-identical JSON, which is the reproducibility receipt (pinned by
`TestDeterminism`). Seeds: bootstrap 20260814, permutation 20260815, tie-break 20260816.
Runtime ≈ 8 minutes.

---

## Adjudication (main loop)

Written by the commissioning session (Fable main loop) after reading §2–§12. Every
sentence below is bounded by §10's power table: the smallest readable ΔP@5 on this frame
is ~17.4pp, every primary CI includes zero, and the frame is a survivorship-flagged
counterfactual replay of a single selection era. These are architectural triage answers,
not verdicts.

**1. Does the current live priority formulation add anything over simpler baselines?**
Directionally yes over the order users actually saw, and modestly over its own selection
axis — the replayed champion (G0: P@5 0.493, top-5 +0.06pp) sits above the published
order (G0′: 0.440, −1.39pp) and pure alpha (G1: 0.440, −0.45pp) on every point estimate —
but no delta clears its CI, and the most damning read is G0′'s permutation floor:
**the order users saw is indistinguishable from a within-night shuffle (p = 0.974)**.
The champion's machinery is not demonstrably adding anything; it is also not
demonstrably the problem. The problem has a name (see 2).

**2. Is the alpha/edge leg helping or hurting?** Four constructions that share no
machinery point the same way at H=10: G3 (sign-flip) leads every top-of-board metric
(P@1 0.667, P@5 0.568, top-5 +1.26pp, best large-loser 0.303, the only rung whose
permutation floor approaches significance at p = 0.067); G4 (deletion) is second; G1
(pure alpha) ties for last; and inside C1 the F2 family is the only one whose
partial-ρ | G0 CI excludes zero *on the negative side* (−0.083 [−0.154, −0.007]) and the
only one whose leave-one-out REMOVAL helps (+4.0pp). This replicates §6.6's alpha
shadow fact through the deployed composition rather than a raw correlation. It is still
one era, 15 nights, inside the CI — **a hypothesis strengthened, not a finding closed**.
The correct next act is prospective, not surgical: no production change is authorized or
proposed here (`DNR:KILL-FUSED-COMPOSITE` amendments and §8.6 both stand).

**3. Do G3/G4 materially improve the champion construction?** G3 is the strongest thing
this race produced and the natural first shadow. G4's apparent strength is partly an
artifact this race caught red-handed: deleting the edge leg collapses score dispersion
(distinct-score ratio 0.422), and 200 random tie-breaks swing its P@5 across
[0.520, 0.613] — §7's answer to "how much of the table is the alphabet". G4 still
earns a shadow slot as the cheaper repair, with its tie-band carried beside it.

**4. Does name_score contain useful ordering information?** At the very top, some: G2
posts the best non-repair P@1 (0.538) and a positive top-5 mean (+0.18pp) with the
board's own composite — consistent with its funnel role — but it decays by P@5, its
Spearman is negative, and §12.2's store/published divergence (22–29% agreement) means
"name_score" is currently two different quantities depending on where you read it. Keep
G2 in the arena; do not consume it as a feature (it stays a forbidden composite); the
store divergence goes to the owning lane as its own finding.

**5. Does C1 improve top-of-board selection after anti-double-count controls?** No.
C1 (0.453) trails G0, G3 and G4, and §9 shows why with unusual clarity: of the four
families that voted, F2 points the wrong way, F4 contributes zero, F8 is
cross-sectionally degenerate (19 fires in 1,493 rows — presence is not variance), and
only F5 does distinguishable positive work (+0.074 [+0.017, +0.130] partial | G0).
Equal-weight breadth over this frame's readable evidence is two voters wide. Per the
commission: C1 not beating G3/G4 is a valid and useful result — **complexity is not
escalated on the program's name**; C2's registered question (weights) inherits exactly
this table.

**6. Where does any apparent improvement come from?** One family's sign, not breadth
and not correlated double-counting: cross-family |ρ| ≤ 0.25 (§9.6), so the C1 voters are
not siblings of each other; the load-bearing redundancy is *within* F2 (alpha ↔ the
champion's edge leg — the registry's documented 0.984 edge). The improvement G3/G4
exhibit is entirely the F2 story read through the champion's own composition. F5 is the
only independent second thread, small and thin.

### Recommendation — what enters prospective shadow accrual next (PR-3 lane)

Register for nightly shadow scoring against G0/G0′ under the frozen arena, zero
authority, prereg'd before the first stamped night: **G3** (edge sign-flip; the primary
hypothesis), **G4** (edge deletion; the cheap repair, tie-band disclosed), **C1 as
raced** (the breadth control), and **C1−F2** (the ablation §9.2 already prices at
+4.0pp — registered now so it cannot be accused of being outcome-selected later).
Nothing else: C2 stays gated behind PR-2's redundancy matrices; no fitted rung is
lawful on a frame whose fold machinery refuses (§10). The §8.6 gate is untouched; the
first honest forward read arrives when the §8.7 distance-to-power lines close, on the
accruing post-PR-1a candidates store.
