# W3 re-cut — the forward race after the override

*`WS:PROPHET-CONDITIONAL-FUSION` · re-cut 2026-08-15, after
[`DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER`](../../agentos/decisions/DEC-PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER.md)
made C1 the canonical US ranker and PR #5753 shipped it.*

## §0 — Why this is a re-cut and not a continuation

W3 was chartered to race a *challenger* C1 against the *deployed champion* `us_prophet_v2`
by replaying the champion's scorer beside a shadow C1. Every noun in that sentence has
since moved:

| | chartered W3 | actual world after #5753 |
|---|---|---|
| production authority | `us_prophet_v2` | **`us_prophet_v3`** (C1) |
| challenger | C1, replayed in shadow | — C1 *is* the board |
| champion side | reconstructed by replaying the v2 scorer | **stamped nightly by production** as `prophet_shadow` |
| what W3 must build | two scorers and a join | **nothing** — the substrate already ships |

So the single largest line item in the old W3 — stand up a second scorer and keep it in
step with production — is **deleted, not deferred**. Production already writes both
orders onto one row every night (`prophet.score`/`display_rank` for canonical C1;
`prophet_shadow.score`/`score_rank` for `us_prophet_v2_shadow`), against one grading
pass and one candidate population. W3 re-cut consumes that; it does not rebuild it.
Reconstructing the retired scorer separately is now a **defect**, not a task: a second
replay could drift from what production actually stamped, and any divergence would be
unattributable between the ranker and the replay.

## §1 — What the race is FOR

It is **not** a horse race with a promotion prize. The shadow is retired and cannot be
promoted back — restoring it as canonical would require a real defect, not a better
score ([`DEC:PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER`](../../agentos/decisions/DEC-PROPHET-FUSION-IS-THE-CANONICAL-US-RANKER.md)).
Naming the purpose honestly changes what gets built:

1. **Guardrail.** The override shipped on three structural properties (unfitted,
   glass-box, order-only), explicitly *not* on outcome evidence. The race is how we
   would find out if that trade made the board materially worse. It is a **tripwire on
   a decision already taken**, not a re-litigation of it.
2. **Accrual.** C1 has no forward record at all — the first `us_prophet_v3` H=10 grade
   matures ~10 sessions after the first fusion night. The race *is* the record being
   built. Every night that accrues is a night the eventual promotion-gate claim can
   draw on.
3. **Structural description.** Which families actually order names, and whether that
   holds as coverage moves. Descriptive, publishable now, and — per
   [`DEC:FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION`](../../agentos/decisions/DEC-FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION.md)
   — **gating and reweighting nothing in this wave**.

## §2 — Lane A: the forward race (accrue now, read later)

**Substrate.** One row per (date, ticker), already stamped: canonical rank and score,
shadow rank and score, stage, entry status, and the ticker-level graded outcome the
existing grader produces. Per
[`DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW`](../../agentos/decisions/DEC-PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW.md)
the two orders are two columns on one row, not two keyed populations — valid precisely
because the population, the outcome and the grader are shared and the shadow holds no
authority.

**Pre-registration — frozen in [`W3_RACE_PREREG.md`](W3_RACE_PREREG.md) before any
forward outcome read (PR-3A).** The bullets below are the charter; the freeze file
is the decision. Do not inspect C1-vs-shadow outcomes until that file is the law.

* **Horizons**: the existing maturation law, unchanged. H=10 first, H=63 for episodes.
  No early reads, no new horizon invented for this race.
* **Metric**: rank-IC of each order against the graded ticker-level outcome, plus
  top-N (N=30) excess vs the same benchmark the board ledger already uses. Both
  computed identically for both columns — the comparison is only meaningful because
  nothing differs but the rank.
* **Honest-N**: reported in **distinct episodes**, never fires or dates. Dates are
  cross-sectionally correlated; a 60-name board on one night is one observation of the
  regime, not 60.
* **Blocking**: date-blocked; where a p-value is quoted it keys on **t**, not the
  normal approximation, and both are printed. At the tens-of-date-blocks scale the
  normal approximation runs roughly half the honest p and has already manufactured a
  rejection once in this program's history.
* **Decision rule**: this wave has **no promotion arm**. The only registered decision is
  the guardrail: if the shadow leads canonical C1 on the registered metric at the
  registered horizon with an honest-N over the registered floor, that opens an
  **investigation** with its own record — it does **not** auto-revert the board, and it
  is **not** grounds to fit C2.
* **Not gradeable yet, and say so**: until the sample matures the surface reports
  "N nights accrued, first lawful read at \<date\>" and prints no comparison. A number
  printed early is read as a verdict no matter how it is captioned.

**Standing fence.** Rank deltas and first-night orderings are **not** alpha evidence.
`FUSION_SCORE_KIND` remains the epistemic boundary: C1 is an unfitted equal-weight
breadth-of-evidence ordering, not a calibrated return forecast.

## §3 — Lane B: which families actually order names

The published separation table (rows, distinct values, modal contribution, modal share)
is necessary but **not sufficient**, and the first live pool shows why. Leave-one-family-out
displacement over the same 69-row board — recompute C1 with one family removed, holding
the admitted member set fixed, and compare the resulting canonical order:

| family | mean \|Δrank\| | max | rows moved | top-30 churn | ties at modal |
|---|--:|--:|--:|--:|--:|
| F1_TECHNICAL_CONFLUENCE | 5.86 | 20 | 62 | 2 | 48% |
| F2_MOMENTUM_EXTENSION | 4.72 | 20 | 60 | 1 | 4% |
| F5_FLOW_POSITIONING | 2.32 | 11 | 57 | 1 | 74% |
| F4_CATALYST_EVENT | 0.58 | 12 | 16 | 0 | 97% |
| F8_ATTENTION_CROWDING | 0.12 | 4 | 5 | 0 | 99% |

Two things follow, and neither is visible in the separation table alone:

1. **Tie-share misranks ordering contribution.** F1 sits at 48% ties and F2 at 4% (56
   distinct values over 69 rows), so the separation table reads F2 as much the more
   discriminating family. LOFO says the opposite: removing **F1** moves the order most.
   A family with few distinct values can still be the largest mover when its splits are
   wide and land where the pool is dense. Tie-share is a **proxy**; displacement is the
   thing itself.
2. **F4 and F8 are near-constant, not constant.** Removing F4 still moves 16 rows (max
   12 ranks); removing F8 moves 5 (max 4). So dropping them ad hoc would *not* be a
   no-op — which is an argument against the drop that does not depend on any principle,
   only on arithmetic. It is also exactly what a sparse-but-variable event flag is
   registered to look like.

**Instrument.** LOFO is computable from the shipped plane with no new machinery —
`us_prophet_fusion.aggregate()` already takes `family_keys`, so the measure is
`aggregate(members, admitted, family_keys=FAMILY_KEYS - {F})` re-ranked by the same
canonical key. It is deterministic, unfitted, and touches no outcome, which is what
lets it publish at display tier immediately.

**Nightly accrual**: one row per (date, family) carrying rows-with-contribution,
distinct values, modal contribution and share, dispersion, and the LOFO displacement
triple (mean, max, rows moved, top-30 churn).

**Fence.** These diagnostics **gate nothing and reweight nothing** in this wave. A
family is admitted by the presence and variance floors — feature-only law, evaluated
as-of-night, blind to outcomes and blind to the resulting order. Discrimination is a
description of coverage on a night. Collapsing the two is precisely how a floor gets
re-tuned against an ordering it produced.

## §4 — Lane C: does the structure drift as coverage moves?

The open question the first pool **cannot** answer: is F4/F8 near-constancy a property
of these families or of this night? One board is one observation, and the program
already has the counter-example that makes the question real — `tier_cascade` (F1) is
**absent** across the frozen 24-date frame (presence 0.25) and **active** live (~1.00),
same code and same thresholds, different frame. Admissibility is frame-dependent, so
discrimination will be too.

Accrue nightly, from the fusion receipt that already ships: families active/abstaining,
members voting, members stood down with the measured presence/variance that refused
them, and rows scored/unscored. Read as a **time series** — a family whose displacement
is near zero every night for a quarter is a different fact from one that is near zero
tonight, and only the first is a registry question worth acting on. Neither is a floor
re-tune.

## §5 — What changes, and whether a PR is needed

**A PR is needed for the records; the build is the next wave.** Splitting them keeps
this session's acceptance from silently becoming a feature wave.

*This PR — the adjudications and this re-cut. Independent of the first-night result,
which is why they ship without waiting for it:*

| path | change |
|---|---|
| `research/prophet_fusion/W3_SHADOW_RACE_RECUT.md` | this document |
| `agentos/decisions/DEC-PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW.md` | new — adjudication B |
| `agentos/decisions/DEC-FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION.md` | new — adjudication A |

*The acceptance record — separate PR, because it cannot be written until the first
fusion nightly exists:*

| path | change |
|---|---|
| `agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md` | w2b closed; `unresolved` items resolved into the two decisions; `next_action` → W3 lane A |
| `agentos/handoffs/PROPHET-CONDITIONAL-FUSION-<date>.md` | the acceptance record |
| `research/prophet_fusion/FUSION_BOARD_COMPARISON.md` | regenerated over the first v3 pool |

*Build (next wave, NEITHER PR):*

| path | change |
|---|---|
| `engine/us_prophet_fusion.py` | `lofo_displacement(members, admitted)` — deterministic, no outcomes |
| `engine/us_board_rank.py` | extend the fusion receipt with the per-family diagnostic triple |
| nightly accrual | one row per (date, family); one row per (date) for coverage |
| `research/prophet_fusion/W3_RACE_PREREG.md` | the §2 pre-registration, **frozen in PR-3A** before the first lawful read |
| display tier | the diagnostic table; the race surface stays "not gradeable yet, N nights accrued" |

**Explicitly not in scope, at any point in W3:** fitting C2 (the fold law is unchanged —
#5700 found zero lawful folds, 67 graded dates short), re-tuning the presence/variance
floors, dropping a family on a diagnostic, bumping `SELECTION_ERA`, granting the shadow
any rank/gate/plan authority, pooling v2 and v3 forward records, or describing an order
comparison as alpha proof.

## §6 — Honest limits

* The race has **no promotion arm**, so it cannot "win". Reporting it as a contest
  would misstate what it is.
* The first lawful read is bounded by maturation, not by instrumentation. Building the
  diagnostics faster does not make the race readable sooner.
* LOFO measures contribution to **this** order on **this** pool. It is not a claim
  about a family's predictive value, and it must never be read as one — a family could
  move the order a great deal and move it wrongly.
* Lane B and Lane C publish immediately; **Lane A does not**, and the discipline that
  keeps them apart is the whole reason the pre-registration is written before the data
  arrives.
