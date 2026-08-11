# Top Anatomy — Phase-1 Report: Anchor-Matched Re-Registration (`top_anatomy_p1`)

Research/display tier, zero scored authority; AVOID-not-SHORT (`DNR:KILL-DIRECTIONAL-SHORTING`); no
rank, no size, no gate, no exit rule; nothing here is a probability or a call. Prereg:
`research/top_anatomy/TOPA_PHASE1_PREREG.md`, frozen on this branch BEFORE any phase-1 number
existed (commit order is the proof; the append-only §7 log carries every post-freeze ruling).
Charter: `reports/top-anatomy-w2.md` §7.2 — decide the artifact-vs-anatomy status of the F1/F3/B3
ore body and of B2's duration-unmatched confirmations.

## §1 The answer (read first)

Two purpose-built control constructions ran against the frozen pipeline, each built to remove one
named counter-explanation. One answered its question; the other failed its own pre-declared
diagnostic — informatively.

1. **Duration and length-biased sampling are DISCHARGED as explanations for B2 and F3** (and for
   B3 on the wide tier only). With episode age matched and length weighting removed, `B2_rsi14`
   and `F3_days_since_63d_high` remain supported on the phase-0 cohort and the ATRZ disjoint
   cohort, and B2's estimates sit INSIDE W2's duration-unmatched CIs on both disjoint panels —
   the prereg's declared "artifacts do not explain W2's confirmation" branch.
2. **The anchor-geometry counter-explanation was NOT discharged — it was affirmatively measured,
   and it is large.** The AM arm's own diagnostic failed (the anchor asymmetry reversed instead of
   collapsing), which voids all nine AM cells as registered results, and the failure doubled as a
   controlled demonstration: moving a control's anchor by roughly two sessions of
   days-since-high moves the heat features by MORE than every registered effect size.
3. **No leg reaches P1-ROBUST** under the frozen synthesis rule (AM void; the R63 disjoint panel
   underpowered under DM). The decisive successor construction is now specified by the failure:
   **AM-v2 — controls matched to the case anchor-distance distribution, not pinned at zero** —
   chartered, not run, requiring its own prereg.

No phase-1 result changes any surface's authority, and no phase-1 claim is about today's market
(frozen 2026-07-02 vintage, declared).

## §2 Constructions, panels, and censuses

The ONLY moved variable is control selection/stratification (prereg §1): **AM** restricts control
candidates to fresh-high days (`days_since_63d_high == 0`) drawn episode-first (one per continued
episode, seeded); **DM** adds an episode-age tercile stratum to the frozen W4 key, also
episode-first. Everything downstream — features, snapshot collapse over {21,10,5}, episode-first
median, episode-peak-month bootstrap B=2000, seed 20260811 — is frozen. Panel censuses reproduce
phase-0 run-3 and both W2 DISJOINT panels exactly.

| cell | continued EXT days → restricted → candidates | matched / cases | n (episodes) | peak-months | match rate |
|---|---|---|---|---|---|
| AM × primary | 84,654 → 23,261 → 3,114 | 3,956 / 4,233 | 1,939 | 47 | 0.62 |
| AM × r63_disjoint | 9,275 → 2,745 → 880 | 337 / 498 | 144 | 28 | 0.30 · MATCH-STARVED |
| AM × atrz_disjoint | 133,775 → 34,567 → 3,651 | 2,606 / 2,741 | 1,271 | 46 | 0.62 |
| DM × primary | → 4,055 | 3,485 / 4,233 | 1,603 | 47 | 0.57 |
| DM × r63_disjoint | → 1,280 | 221 / 498 | 90 | 18 | 0.22 · MATCH-STARVED |
| DM × atrz_disjoint | → 4,261 | 2,130 / 2,741 | 980 | 43 | 0.56 |

Walls: 173 / 167 / 112 / 104 / 190 / 192 s — 938 s total against the 12 h budget; no deferral.

## §3 The governing fact: the AM construction failed, and the failure is the finding

**Discovery (logged append-only in prereg §7):** the prereg's §1 prose assumed the topped arm is
measured at its peak day. The FROZEN §2 pipeline — which §2 explicitly makes law — measures cases
at the {21,10,5} days-to-peak snapshots, where cases sit at a median `days_since_63d_high` of 1–2
(r63 disjoint: median 1.0, mean 3.9). Controls pinned at exactly 0 therefore sit CLOSER to fresh
highs than the cases they were matched to. The construction reversed the anchor asymmetry instead
of neutralizing it.

The pre-declared §1 clause governs: *"a non-collapse means the construction failed, and every AM
cell is then reported UNDERPOWERED-BY-CONSTRUCTION-FAILURE."* The signed diagnostic did not
collapse — it flipped:

| AM diagnostic (F3, topped − control) | phase-1 | anchor (W2/ph0) |
|---|---|---|
| primary | **+2.000** [+2.000, +2.500] | −2.250 |
| r63_disjoint | **+1.000** [+1.000, +1.750] | −2.250 |
| atrz_disjoint | **+2.000** [+1.000, +2.000] | −2.750 |

The summaries' `collapsed_by_magnitude=True` boolean is ruled NON-GOVERNING: it compares absolute
magnitudes only and is blind to the sign flip (adjudication entry, prereg §7). **All nine AM cells
are therefore UNDERPOWERED-BY-CONSTRUCTION-FAILURE** — the JSONs retain the mechanically-computed
`P1-NOT-SUPPORTED` grades that predate the ruling; this table is the adjudicated record. Their
computed deltas are printed below as measurements OF THE REVERSED design, never as registered
results:

| leg (declared) | AM primary | AM r63_disjoint | AM atrz_disjoint |
|---|---|---|---|
| `F1_episode_age` (−) | +4.250 [+3.123, +5.750] | +2.750 [+0.667, +4.750] | +3.250 [+2.000, +5.878] |
| `B3_rsi14_chg10` (+) | −7.405 [−8.482, −6.676] | −5.644 [−8.501, −2.855] | −4.489 [−6.514, −2.872] |
| `B2_rsi14` (+) | −7.379 [−8.000, −6.400] | −3.391 [−5.097, −1.636] | −3.777 [−4.833, −2.868] |

*(AM's F1 cells carry a second confound the draw itself creates: restricting controls to
fresh-high days selects young control moments — case age median 7 vs control 1 on r63 — so even a
working anchor match would leave AM-F1 unreadable there.)*

**The mechanism receipt.** The pre-registered tolerance sensitivity (`days_since_63d_high ≤ 2`)
shrinks the residual anchor gap, and every reversal shrinks with it: primary gap +2.00 → +1.75
moves B3 from −7.41 to −3.89 and B2 from −7.38 to −4.61; atrz gap +2.00 → +1.00 moves B3 −4.49 →
−2.01 and B2 −3.78 → −1.91. The AM deltas track the residual anchor gap, not the topped/continued
distinction. Read as measurement geometry, this is the wave's affirmative result: **roughly two
sessions of anchor proximity move RSI-family features by 2–7 points — larger than every
registered effect in this program.** The peak-anchor counter-explanation for the ore body is not
merely undischarged; it now has a measured scale, and any future construction that does not
control anchor distance to the case DISTRIBUTION cannot decide it.

## §4 The registered answers: duration-matched cells

| leg (declared) | DM primary | DM r63_disjoint | DM atrz_disjoint |
|---|---|---|---|
| `F3_days_since_63d_high` (−) | **−1.667 [−2.000, −1.250] q=0.0015 · SUPPORTED** | −2.125 [−5.000, −1.000] q=0.0005 · UNDERPOWERED | **−1.500 [−2.000, −1.000] q=0.0005 · SUPPORTED** |
| `B3_rsi14_chg10` (+) | +0.429 [−0.845, +1.717] q=0.284 · NOT-SUPPORTED | +4.885 [+3.028, +6.886] q=0.0005 · UNDERPOWERED | **+3.268 [+1.900, +4.971] q=0.0005 · SUPPORTED** |
| `B2_rsi14` (+) | **+0.952 [+0.110, +1.869] q=0.0248 · SUPPORTED** | +4.947 [+3.143, +6.755] q=0.0005 · UNDERPOWERED | **+2.885 [+1.981, +3.542] q=0.0005 · SUPPORTED** |

Readings, stated plainly:

1. **B2 survives duration matching.** Registered anchor comparison: both disjoint DM points sit
   INSIDE W2's duration-unmatched CIs — r63 +4.947 ∈ [+2.56, +5.25] (1.28× W2's point), atrz
   +2.885 ∈ [+2.80, +4.79] (0.74×) — the declared "duration/length-bias artifacts do not explain
   W2's confirmation" branch. On the phase-0 cohort, +0.952 against phase-0's unmatched +1.29
   (0.74×): supported, modestly attenuated. What this does NOT say: that B2 is anatomy — the §3
   anchor mechanism is larger than any of these effects and remains open.
2. **B3's discovery-cohort effect was the duration confound.** On primary, "accelerating heat"
   collapses to +0.43 (q=0.284) once age is matched: on the cohort where B3 was found, younger
   episodes accelerating explained it. It remains supported on the wide-tier disjoint cohort
   (+3.27) — tier heterogeneity again, now with a mechanism candidate eliminated on one tier.
3. **F3 survives duration matching on both readable panels** with its pre-declared caveat intact:
   DM controls sit at arbitrary anchors, so these cells cannot separate "genuinely fresher highs"
   from the §3 anchor geometry. They discharge duration for F3; they do not touch the anchor
   question.
4. **R63 disjoint is thin, not null.** All three legs show declared signs at q=0.0005 but n=90
   matched episodes misses the pre-registered 100 floor (match rate 0.22): UNDERPOWERED, no
   directional claim. The day-weighted sensitivity (n=399) is concordant on every leg (F3 −1.33 /
   B3 +2.88 / B2 +3.02), locating the thinness in the episode-first draw's intersection with a
   323-episode panel — the floor, not the data, withholds the grade. A future wave wanting this
   cell must widen the candidate draw, not lower the floor.

## §5 Era stratification and sensitivities

- **Era blocks** (panel property, identical across constructions): 2022-07..2023-10 /
  2023-11..2025-02 / 2025-03..2026-06 at 16/16/16 peak-months (r63: 15 in the last block), union
  verified against each panel. **Zero latest-era wrong-sign flags** — no ERA-CAVEAT modifier fired
  on any supported cell. **B2's era-fade fence reads `fades=False` on all six cells**: no
  monotone era-over-era decay on these panels. This does not contradict phase-0's own-panel fade
  fence (different matched designs); it records that the fade has no phase-1 echo. E4-style
  era/dvol sign-stability tables are in every summary.
- **NN cap 8** reproduces every registered cell to ~2 decimal places (matching depth is not
  load-bearing). **DM day-weighted** keeps all signs and significance (atrz F3 −1.25 / B3 +3.05 /
  B2 +2.01) — the switch to episode-first sampling changes power (§4.4), not conclusions, on the
  panels that were readable both ways. **AM tolerance ≤2** is §3's mechanism gradient. B=2000
  everywhere; nothing reduced.
- **Exploratory** (full 36-row tables in all six summaries, two-sided BH, EXPLORATORY-DISCOVERY
  cap): DM separating counts 4 / 0 / 9. AM counts of 21 / 0 / 13 are read as the population-shift
  signature of a failed construction — features disagreeing between fresh-high moments and
  near-high moments — not as 21 discoveries; nothing from a voided construction enters any
  discovery ledger.

## §6 Instrument and gates

Commit-order proof on `claude/topa-phase1-anchor-matched` (order preserved through one mid-wave
rebase): prereg freeze `eb5b87a0322` → plumbing `54d04f8cce6` → tests `07751721e75` → five result
commits → adjudication `5115d6c14b3`. `engine/top_anatomy.py` byte-identical to main at every
commit; all phase-1 logic is harness plumbing. Determinism: two cells (r63_disjoint×AM pre-rebase,
atrz_disjoint×DM post-rebase) re-run end-to-end and identical to float precision against the
committed artifacts. Suite 134 → 164 under TZ=UTC, green. Conformance greps for seed/B/q/family/
floors enforced at the lines logged in prereg §7. Deviations (all logged append-only, none
scientific): shared-checkout execution; read-only store mirror from the primary checkout; the DM
stratum implemented as a harness-level matcher pinned byte-equal to the frozen matcher when run
without a stratum — because per-stratum calls into the engine matcher would have RE-CUT the frozen
bin edges, an unregistered second moved variable; feature panels shared across constructions
within a panel (a construction selects controls; it never enters a feature value).

## §7 Adjudication

1. **AM-v2 is chartered as the decisive construction** (not run; requires its own prereg):
   controls matched to the case `days_since_63d_high` DISTRIBUTION (not pinned at zero), with the
   {21,10,5} snapshot geometry stated correctly in the prose, episode-first sampling retained, and
   the same signed diagnostic — which under a working match must collapse, not flip. Until AM-v2
   reports, every ore-body and B2 claim carries "anchor geometry undischarged" as a live rival.
2. **W2b (surface widening) is unaffected.** The Winner Health tiers count descriptive legs
   against per-tier libraries and claim no anatomy; nothing in phase-1 changes any tier's copy,
   and the heat leg's language stays descriptive.
3. **Gauntlet file, for whenever a promotion prereg exists:** B2 now carries duration-robustness
   on two cohorts (this wave) plus cross-tier confirmation (W2); it still lacks an anchor-clean
   estimate, an era receipt beyond fade-fence nulls, and any out-of-time evidence. Nothing
   promotes.
4. **Out-of-time replication stays the binding open question** for the whole program; the store
   refresh (#5319 workstream) is the unblocking event, and the first post-refresh wave re-reads
   vintage rosters and the exemplar census before anything else.

## §8 Execution log

- 2026-08-11 — prereg frozen pre-results; plumbing + 30 tests committed pre-results; six cells run
  inside the wall (938 s); adjudication rulings appended to prereg §7 (AM construction-failure
  re-grading, boolean non-governing, AM-v2 charter); this report drafted from the six committed
  summaries with grades/CIs/diagnostics spot-verified against the artifacts by the commissioning
  session; G0.5 adversarial review commissioned before presentation, corrections binding, with the
  reviewer directed to re-derive all 18 registered cells and both diagnostic families.
