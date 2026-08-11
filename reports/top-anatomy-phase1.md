# Top Anatomy — Phase-1 Report: Anchor-Matched Re-Registration (`top_anatomy_p1`)

Research/display tier, zero scored authority; AVOID-not-SHORT (`DNR:KILL-DIRECTIONAL-SHORTING`); no
rank, no size, no gate, no exit rule; nothing here is a probability or a call. Prereg:
`research/top_anatomy/TOPA_PHASE1_PREREG.md`, frozen on this branch BEFORE any phase-1 number
existed (commit order is the proof; the append-only §7 log carries every post-freeze ruling and
correction). Charter: `reports/top-anatomy-w2.md` §7.2 — decide the artifact-vs-anatomy status of
the F1/F3/B3 ore body and of B2's duration-unmatched confirmations.

## §1 The answer (read first)

Two purpose-built control constructions ran against the frozen pipeline, each built to remove one
named counter-explanation. One answered its question; the other failed as an instrument — with the
failure itself adjudicated in the open (§3), because the pre-declared mechanical reading of its
diagnostic said otherwise.

1. **Duration matching is DISCHARGED as the explanation for B2 and F3 where the floors clear.**
   With episode age matched: `B2_rsi14` stays supported on the phase-0 cohort (+0.952) and on the
   ATRZ disjoint cohort (+2.885, inside W2's duration-unmatched CI — by a margin of 0.085 at its
   floor; §4.1); `F3_days_since_63d_high` stays supported on both — with the caveat attached at
   first mention that F3 *is* anchor distance, so its DM support cannot separate "genuinely
   fresher highs" from the anchor geometry in (2). The R63 disjoint panel misses the matched-
   episode floor and carries no directional claim (§4.4). `B3_rsi14_chg10` on the discovery
   cohort is explained by the length-biased-SAMPLING half of mechanism (2), not by age: switching
   control sampling back to day-weighted — age stratum still applied — restores B3 to +1.371
   (q=0.0045) on primary (§4.2).
2. **The anchor-geometry counter-explanation was NOT discharged, and the wave's own artifacts
   strengthen it.** The AM arm placed controls at exactly zero days-since-high against cases whose
   frozen snapshots sit at median 1–2 — reversing the asymmetry it existed to remove (§3). Its
   nine cells are adjudicated void as registered results, over a pre-declared mechanical reading
   that said "no failure" — the override, its grounds, and the registered kill it displaces are
   printed in §3.2, not footnoted. Meanwhile the DM arm's own full exploratory tables put two
   anchor-family features (`E3f_rs_peak_lag`, `F2_drawdown_in_episode`) among the most consistent
   wrong-sign replications in the program (3/3 panels each; §5.1) — the anchor rival is alive
   inside the "clean" construction too.
3. **No leg reaches P1-ROBUST** under the frozen synthesis rule (AM void; R63 disjoint
   underpowered under DM). The decisive successor construction is specified by the failure:
   **AM-v2 — controls matched to the case anchor-distance DISTRIBUTION, not pinned at zero** —
   chartered, not run, requiring its own prereg. Until it reports, the ore body's status is
   UNDECIDED, and under the pre-results mechanical reading it would already be dead (§3.2): that
   counterfactual is the measure of how much rides on AM-v2.

No phase-1 result changes any surface's authority, and no phase-1 claim is about today's market
(frozen 2026-07-02 vintage, declared).

## §2 Constructions, panels, and censuses

The ONLY moved variable is control selection/stratification (prereg §1): **AM** restricts control
candidates to fresh-high days (`days_since_63d_high == 0`) drawn episode-first (one per continued
episode, seeded); **DM** adds an episode-age tercile stratum to the frozen W4 key, also
episode-first (stratum edges, printed from the artifacts: primary [7, 27], r63 [1, 8], atrz
[5, 26] — on r63 the young tercile is "age ≤ 1", a coarseness the panel's thinness forces).
Everything downstream — features, snapshot collapse over {21,10,5}, episode-first median,
episode-peak-month bootstrap B=2000, seed 20260811 — is frozen. Panel censuses reproduce phase-0
run-3 and both W2 DISJOINT panels exactly.

Units, labeled (three different "n"s live in these artifacts): *case-sets* = matched case snapshot
sets (`matching.n_matched` / `n_cases`); *cell n* = matched topped episodes surviving per-cell
coverage (`floors.n_matched_topped_episodes_this_cell`); *match rate* = matched **episodes** over
topped-E1-eligible **episodes** (`e1.n_episodes` / `episodes.n_topped_e1_eligible`).

| cell | continued EXT days → restricted → candidates | matched / case-sets | matched / eligible episodes | cell n | peak-months | match rate |
|---|---|---|---|---|---|---|
| AM × primary | 84,654 → 23,261 → 3,114 | 3,956 / 4,233 | 2,097 / 3,407 | 1,939 | 47 | 0.62 |
| AM × r63_disjoint | 9,275 → 2,745 → 880 | 337 / 498 | 246 / 814 | 144 | 28 | 0.30 · MATCH-STARVED |
| AM × atrz_disjoint | 133,775 → 34,567 → 3,651 | 2,606 / 2,741 | 1,433 / 2,306 | 1,271 | 46 | 0.62 |
| DM × primary | → 4,055 | 3,485 / 4,233 | 1,946 / 3,407 | 1,603 | 47 | 0.57 |
| DM × r63_disjoint | → 1,280 | 221 / 498 | 180 / 814 | 90 | 18 | 0.22 · MATCH-STARVED |
| DM × atrz_disjoint | → 4,261 | 2,130 / 2,741 | 1,299 / 2,306 | 980 | 43 | 0.56 |

Walls, construction-major to match the table: AM 173 / 112 / 190 s, DM 167 / 104 / 192 s
(primary / r63 / atrz) — 938 s total against the 12 h budget; no deferral.

## §3 The governing fact: the AM instrument reversed its own asymmetry

### §3.1 The design discovery

The prereg's §1 prose assumed the topped arm is measured at its peak day. The FROZEN §2 pipeline —
which §2 explicitly makes law — measures cases at the {21,10,5} days-to-peak snapshots, where the
case-anchor `days_since_63d_high` distribution sits at median 2.0 / 1.0 / 2.0 with mean 6.99 /
3.92 / 5.64 (primary / r63 / atrz). AM's controls sit at exactly 0 (p25 = p75 = 0 — the
restriction is an equality). The construction therefore did not neutralize the anchor asymmetry;
it REVERSED it. Two further design receipts, both knowable without any estimate: the episode-first
fresh-high draw selects *young* control moments (control episode-age median 6 / 1 / 3 vs case
24 / 7 / 20 — a second manufactured asymmetry, which is why AM's F1 cells are unreadable even
under a working anchor match); and both asymmetries are properties of the frozen snapshot geometry
plus the restriction, not of any outcome.

### §3.2 The ruling, its pre-declared rival, and the registered kill it displaces

**What was declared pre-results, found what:** the plumbing commit (`54d04f8cce6`) declared a
magnitude-only operationalization of the §1 collapse clause (`p1_matching_diagnostic`, stated in
its docstring as the reading the adjudicator applies, pinned by a pre-results test whose failure
exemplar is a magnitude non-shrink). On the results it returned `collapsed_by_magnitude=True` and
`construction_failure=False` on all three AM panels — because the signed diagnostic, required by
the frozen prose to "collapse toward zero," instead passed THROUGH zero and out the other side:

| AM diagnostic (F3, topped − control) | phase-1 | anchor (W2/ph0) | reading |
|---|---|---|---|
| primary | **+2.000** [+2.000, +2.500] | −2.250 | flipped, 89% of anchor magnitude |
| r63_disjoint | **+1.000** [+1.000, +1.750] | −2.250 | flipped, 44% |
| atrz_disjoint | **+2.000** [+1.000, +2.000] | −2.750 | flipped, 73% |

**The ruling (post-results, disclosed as such):** the adjudicator voided all nine AM cells as
UNDERPOWERED-BY-CONSTRUCTION-FAILURE, overriding the mechanical reading. The override's grounds,
in order of weight: (i) the FROZEN prereg text — "collapse toward zero" — outranks the plumbing's
operationalization, and a sign flip to 44–89% of anchor magnitude is not a collapse toward zero on
any plain reading; (ii) the failure verdict is outcome-independent — §3.1's asymmetries are design
facts, so the instrument was measuring the wrong contrast before any estimate existed; (iii) the
reversal is not heat-specific: on primary AM, `B1_accel_r21` −0.110, `B4_newhigh63_rate21` −0.048,
`B5_upday_rate21` −0.030, `B6_max_up_streak21` −0.500, `A1_r21` −0.092, `A2_r63` −0.055 (all
q≈0.0005) while `A3_r126` +0.002 and `A4_r252` +0.038 — short-horizon down, long-horizon up is the
signature of comparing different lifecycle positions, not of "cooling before a top" (real cooling
would not move a max-up-streak count).

**What the ruling displaces — printed, because the flexibility ran toward preserving the ore
body:** under the mechanical reading, the artifacts' own grades stand (`P1-NOT-SUPPORTED` × 9,
`construction_failure=false`, `grade_with_construction_modifier=P1-NOT-SUPPORTED` in every AM
summary), and prereg §3's "Collapse is a result" clause delivers the registered headline verbatim:
*"the F1/F3/B3 separations are matching geometry, not anatomy."* The B2 branch would additionally
re-classify W2's B2 confirmation as matching artifact and make a W1/W2b surface-copy correction
MANDATORY (`b2_anchor_comparison.inside_w2_interval=false` on both disjoint AM summaries, ratios
−0.876 / −0.964 — the registered per-panel comparison, shown here because it is registered per
panel, not per construction). §7.2's "W2b is unaffected" therefore holds ONLY under this ruling.
The ruling is nonetheless made, because killing a family on an instrument that demonstrably
measures the reversed asymmetry would be an instrument verdict wearing a market verdict's clothes
— but it is made with its counterfactual on the table, and AM-v2 exists to remove the discretion.

**The adjudicated record** (mechanical grade carried BESIDE the ruling, never replaced — the
pre-results test pins exactly this):

| leg (declared) | AM primary | AM r63_disjoint | AM atrz_disjoint | mechanical grade | adjudicated state |
|---|---|---|---|---|---|
| `F1_episode_age` (−) | +4.250 [+3.123, +5.750] | +2.750 [+0.667, +4.750] | +3.250 [+2.000, +5.878] | P1-NOT-SUPPORTED ×3 | VOID — construction failure |
| `B3_rsi14_chg10` (+) | −7.405 [−8.482, −6.676] | −5.644 [−8.501, −2.855] | −4.489 [−6.514, −2.872] | P1-NOT-SUPPORTED ×3 | VOID — construction failure |
| `B2_rsi14` (+) | −7.379 [−8.000, −6.400] | −3.391 [−5.097, −1.636] | −3.777 [−4.833, −2.868] | P1-NOT-SUPPORTED ×3 | VOID — construction failure |

### §3.3 What the tolerance arm actually measured

The pre-registered tolerance sensitivity (`days_since_63d_high ≤ 2`) shrinks the residual anchor
gap and every reversal shrinks with it — but the three panels measured three different sub-session
steps with slopes that differ by ~6×, so this is monotone evidence of anchor leverage, not a
calibrated rate:

| panel | residual gap step | ΔB2 per step | ΔB3 per step |
|---|---|---|---|
| primary | 2.00 → 1.75 (0.25 sessions) | 2.774 | 3.511 |
| r63_disjoint | 1.00 → 0.667 (0.33) | 1.237 | 3.925 |
| atrz_disjoint | 2.00 → 1.00 (1.00) | 1.868 | 2.479 |

The largest measured move is 3.9 RSI-slope points over a one-third-session step — comparable in
magnitude to the largest registered effects in this program, measured over sub-session anchor
steps. The residual at gap 0 is UNMEASURED: a linear read-through crosses zero near the observed
gap on atrz and r63 but not on primary (which would extrapolate to a large positive residual), and
the tolerance switch also moves the matched pool (n_matched 3,956→3,997 / 337→334 / 2,606→2,568)
and control ages, so it is not a single-variable dial. What survives all of that: anchor proximity
has feature-scale leverage, and no construction that leaves a case-vs-control anchor gap
uncontrolled to the case DISTRIBUTION can decide the ore body. That is AM-v2's design requirement,
not a market claim.

## §4 The registered answers: duration-matched cells

**The DM stratification diagnostic — the receipt that DM is not the broken arm** (prereg §1: F1
printed, ungraded): DM-F1 collapses to +0.250 [0.000, +0.500] / −0.125 [−0.500, 0.000] / 0.000
[−0.500, +0.4375] against anchors −9.69 / −2.20 / −17.00 — absolute ratios 0.026 / 0.057 / 0.000.
The age stratum did its job to near-totality on all three panels.

| leg (declared) | DM primary | DM r63_disjoint | DM atrz_disjoint |
|---|---|---|---|
| `F3_days_since_63d_high` (−) | **−1.667 [−2.000, −1.250] q=0.0015 · SUPPORTED** | −2.125 [−5.000, −1.000] q=0.0005 · UNDERPOWERED | **−1.500 [−2.000, −1.000] q=0.0005 · SUPPORTED** |
| `B3_rsi14_chg10` (+) | +0.429 [−0.845, +1.717] q=0.284 · NOT-SUPPORTED | +4.885 [+3.028, +6.886] q=0.0005 · UNDERPOWERED | **+3.268 [+1.900, +4.971] q=0.0005 · SUPPORTED** |
| `B2_rsi14` (+) | **+0.952 [+0.110, +1.869] q=0.0248 · SUPPORTED** | +4.947 [+3.143, +6.755] q=0.0005 · UNDERPOWERED | **+2.885 [+1.981, +3.542] q=0.0005 · SUPPORTED** |

Readings, stated plainly:

1. **B2 survives duration matching where the floors clear — with the margins printed.** Registered
   anchor comparison: atrz DM +2.885 sits inside W2's [+2.80, +4.79] by a margin of 0.085 at the
   interval's floor, at 0.74× W2's point — a 26% attenuation that lands inside, not a clean
   midpoint hit. r63 DM +4.947 is inside [+2.56, +5.25] at 1.28× — but that cell is UNDERPOWERED
   and carries no directional claim, so the discharge headline rests on ATRZ and the phase-0
   cohort (+0.952 vs unmatched +1.29, 0.74×). The declared branch — "duration/length-bias
   artifacts do not explain W2's confirmation" — is met on the floor-clearing panels. What this
   does NOT say: that B2 is anatomy — the §3 anchor mechanism operates at feature scale and
   remains open, and §5.2's extension-shift rival applies to the same ATRZ cells.
2. **B3's discovery-cohort effect is explained by length-biased sampling, not by age.** On
   primary, B3 collapses to +0.429 (q=0.284) under DM — but the day-weighted sensitivity, with
   the AGE STRATUM STILL APPLIED and only the sampling switched back, restores it to +1.371
   [+0.393, +2.328] (q=0.0045, 2,148 episodes, 47 peak-months, floors met). The kill mechanism on
   the discovery cohort is therefore mechanism (2)'s sampling half: B3's phase-0 separation needed
   controls drawn day-weighted from long episodes. It remains supported on the wide-tier disjoint
   cohort (+3.268) under episode-first sampling — tier heterogeneity, with the responsible
   mechanism now isolated per tier.
3. **F3 survives duration matching on both readable panels**, carrying the §1 caveat: F3 is
   anchor distance, so under DM (controls at arbitrary anchors) these cells discharge duration
   only; on present evidence the leading rival for F3's separation is the anchor geometry itself.
4. **R63 disjoint is ungradeable, and nothing substitutes for the grade.** All three legs carry
   declared signs at q=0.0005, but 90 matched episodes miss the pre-registered 100 floor (match
   rate 0.22, MATCH-STARVED). The day-weighted arm reaches 240 episodes (2.7× — case-set counts
   399 vs 221 are a different unit) with the same signs — but that arm reinstates the very
   length-biased sampling DM exists to remove, so it substitutes for neither the floor nor the
   grade. Prereg §3 is explicit: UNDERPOWERED means no directional claim. A future wave wanting
   this cell must widen the episode-first draw, not lower the floor or lean on the biased arm.

## §5 Exploratory (full tables), era stratification, and sensitivities

1. **Read from the FULL per-feature tables (prereg §3 — the survivor lists are sign-gated and the
   draft of this report initially repeated the W2 mistake of citing them).** Full-table counts at
   q ≤ 0.10 with CI excluding zero, DM arm: primary 9, r63 9, atrz 13 (the survivor-list counts
   4 / 0 / 9 hide wrong-sign rows; r63's 9 qualifying rows are additionally all floor-dropped —
   `interpretable=False` — the same thinness as §4.4, stated rather than printed as "0"). The
   structure the survivor lists hid: **`E3f_rs_peak_lag` (declared +) replicates wrong-sign on
   3/3 DM panels** (−2.000 / −2.979 / −3.000, q ≤ 0.005, CIs excluding zero) and
   **`F2_drawdown_in_episode` (declared −) replicates wrong-sign on 3/3** (+0.0059 / +0.0120 /
   +0.0052, q ≤ 0.002), with `F4_deepest_dip21_vs_max63` wrong-sign on 2/3. Both 3/3 families are
   anchor-adjacent (recency of the relative-strength peak; drawdown position within the episode) —
   the most consistent replicating structure inside the "clean" DM arm is more anchor geometry,
   which strengthens §3's thesis from within the construction that was supposed to be free of it.
2. **A stated rival for the ATRZ supported cells:** on atrz DM the ENTIRE A-family separates
   positive alongside B2/B3 — A1 +0.0074, A2 +0.0184, A3 +0.0016 (q=0.014), A4 +0.0567, A5
   +0.5228, A6 +0.3015, A7 +0.0409, A8 +0.0685 (all others q ≤ 0.0012) — and only r126 is in the
   matching key. The supported heat legs on ATRZ may therefore be one broad extension/momentum
   shift rather than heat-specific anatomy; nothing in this wave separates those.
3. **Era stratification:** blocks 2022-07..2023-10 / 2023-11..2025-02 / 2025-03..2026-06 at
   16/16/16 peak-months (r63: 15 in the last), union verified. Zero latest-era wrong-sign flags —
   AND the flag's granularity should not be over-read: primary DM B2, the phase-0-cohort discharge
   cell, is not separable in any single stratum (era CIs [−0.750,+2.124] / [−0.034,+2.571] /
   [−0.424,+2.083]; high-dvol tercile [−0.693,+2.396] — all contain zero); its support is a
   pooled-panel result. The B2 era-fade fence (`fades_era_over_era`, strictly monotone by
   construction) does not fire on any of the six cells; the shape it is blind to is present —
   era3 < era2 on all three DM panels (0.718 < 1.617 / 3.896 < 5.179 / 2.457 < 3.143) and era3 <
   era1 on primary and r63 DM. Phase-0's own-panel fade fence is neither confirmed nor
   contradicted here (different matched designs); the latest-era softness is printed for AM-v2 to
   carry.
4. **Sensitivities:** NN cap 8 moves registered cells by up to 0.489 (atrz AM B3; atrz AM F1
   0.450; primary AM F1 0.375; and primary DM F3 by 0.333 — 20% of a headline SUPPORTED point),
   so matching depth is not entirely inert; no sign or grade changes. Day-weighted DM keeps signs
   and significance on the panels readable both ways EXCEPT primary B3 — where it flips the
   conclusion and is the §4.2 attribution (a sampling effect, not a power effect: n falls 25%
   while the point falls 69%). AM tolerance ≤2 is §3.3. B=2000 everywhere; nothing reduced.

## §6 Instrument and gates

Commit-order proof on `claude/topa-phase1-anchor-matched` (order preserved through one mid-wave
rebase): prereg freeze `eb5b87a0322` → plumbing `54d04f8cce6` → tests `07751721e75` → five result
commits → adjudication `5115d6c14b3`. The artifacts stamp the pre-rebase freeze sha
(`838aa5c49f1`, unreachable after the rebase); content identity is provable — `prereg_sha256` in
every summary matches the frozen file at `eb5b87a0322`. `engine/top_anatomy.py` is byte-identical
to origin/main and the branch touches zero files under `engine/`; the literal `git diff
origin/main -- engine/` is non-empty only through two unrelated options-market files other lanes
landed on main after the branch point. Determinism: two cells (r63_disjoint×AM pre-rebase,
atrz_disjoint×DM post-rebase) re-run end-to-end and identical to float precision against the
committed artifacts — builder-attested (a read-only review cannot re-run; the G0.5 pass verified
every printed number against the artifacts instead, finding zero transcription errors). Suite
134 → 164 under TZ=UTC, green. Conformance greps for seed/B/q/family/floors enforced at the lines
logged in prereg §7. Deviations (all logged append-only, none scientific): shared-checkout
execution; read-only store mirror from the primary checkout; the DM stratum implemented as a
harness-level matcher pinned byte-equal to the frozen matcher when run without a stratum — because
per-stratum calls into the engine matcher would have RE-CUT the frozen bin edges, an unregistered
second moved variable; feature panels shared across constructions within a panel (a construction
selects controls; it never enters a feature value).

## §7 Adjudication

1. **AM-v2 is chartered as the decisive construction and it is now MANDATORY before any ore-body
   conclusion hardens in either direction** (not run; requires its own prereg): controls matched
   to the case `days_since_63d_high` DISTRIBUTION (not pinned at zero) with the {21,10,5} snapshot
   geometry stated correctly, control episode-age asymmetry controlled or stratified (§3.1's
   second receipt), episode-first sampling retained, and the same signed diagnostic — which under
   a working match must collapse toward zero without flipping. The urgency is the §3.2
   counterfactual: under the pre-declared mechanical reading this wave already killed the ore
   body; the override that kept it alive is an adjudicator ruling, and AM-v2 exists to replace
   that discretion with an instrument.
2. **W2b (surface widening) proceeds — conditionally on the §3.2 ruling, and the condition is
   disclosed here.** Under the ruling, no phase-1 result touches any tier's copy: the Winner
   Health tiers count descriptive legs against per-tier libraries and claim no anatomy. Had the
   mechanical grades stood, the prereg's B2 branch would have made a surface-copy correction
   mandatory. If AM-v2 lands on the kill side, that correction obligation REVIVES and binds the
   then-live surface.
3. **Gauntlet file, for whenever a promotion prereg exists:** B2 now carries duration-robustness
   on two floor-clearing cohorts (this wave) plus cross-tier confirmation (W2); it still lacks an
   anchor-clean estimate (AM-v2), a single-stratum era separation on the phase-0 cohort (§5.3),
   an answer to the ATRZ extension-shift rival (§5.2), and any out-of-time evidence. Nothing
   promotes.
4. **Out-of-time replication stays the binding open question** for the whole program; the store
   refresh (#5319 workstream) is the unblocking event, and the first post-refresh wave re-reads
   vintage rosters and the exemplar census before anything else.

## §8 Execution log

- 2026-08-11 — prereg frozen pre-results; plumbing + 30 tests committed pre-results; six cells run
  inside the wall (938 s); adjudication rulings appended to prereg §7 (AM construction-failure
  re-grading, boolean non-governing, AM-v2 charter); report drafted from the six committed
  summaries with grades/CIs/diagnostics spot-verified against the artifacts.
- 2026-08-11 — G0.5 adversarial review (Opus): NOT PRESENTABLE — 5 blockers / 14 must-fix / 7
  nits. Zero transcription errors in the registered tables; every §3/§4 number reproduced exactly.
  The blockers were adjudication-level: the report cited sign-gated survivor lists (repeating the
  W2 mistake its own prereg §3 forbids — E3f/F2 wrong-sign 3/3 families were invisible); the
  construction-failure ruling was presented as the clause applying mechanically when the
  pre-declared mechanical reading in fact PASSED (override disclosed, grounded, and its displaced
  registered kill printed in §3.2 of this revision); the mechanism claim overstated measured
  gradients (restated over the actual sub-session steps with 6× slope spread); the DM-F1
  diagnostic family was absent (now leads §4); the B3-primary attribution said "duration" when the
  same summary's day-weighted arm proves it is the sampling half (corrected in §1.1/§4.2). All 14
  must-fix and 7 nits applied. Corrections binding on the earlier §8 entry and logged append-only
  in prereg §7.
