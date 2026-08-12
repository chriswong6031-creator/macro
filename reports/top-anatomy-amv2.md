# Top Anatomy — AM-v2 report (anchor-distribution-matched controls)

Prereg: `research/top_anatomy/TOPA_AMV2_PREREG.md`, frozen at `011d9aae2f6` before any result
existed (plumbing `cf898eb74cb`, §7 operationalizations `58d04e11a0b`, results `db05162dc17` —
commit order verifiable on the branch). Display tier throughout; AVOID-not-SHORT permanently
(`DNR:KILL-DIRECTIONAL-SHORTING`); no AM-v2 claim is about today's market (frozen 2026-07-02
vintage, declared).

## §1 The answer, in three parts

1. **The instrument worked, first try, everywhere.** The per-case-snapshot anchor caliper
   collapsed the case-vs-control anchor gap to 0.0 (worst panel: −0.06 [−0.25, 0.00]) against
   registered anchors of −2.25/−2.75, with all three signed validity clauses TRUE on every
   (construction × panel) at BOTH calipers. No escalation fired, no construction failed, and the
   adjudicator override that phase-1 needed has no successor here — the governing arm was
   determined mechanically on all six cells. AM-v1's discretion is fully replaced.
2. **The registered kill fires: the ore body was anchor geometry, not anatomy.** B3 — the ore
   body's only jointly readable member — is `P1-NOT-SUPPORTED` under a VALID anchor+age-matched
   construction on the only floor-clearing disjoint panel (ATRZ: +1.530 [−0.884, +3.604],
   q=0.1165) and on the discovery cohort (+0.133 [−1.142, +1.040], q=0.455). Per the prereg §3
   pre-written branch, **the ore-body anatomy claim is CLOSED on this tape as a cluster claim.**
   The kill is scoped: this tape, matched-design constructions; out-of-time replication remains
   the program's open question, and B3 remains a display-tier confluence input (non-standalone ≠
   worthless).
3. **B2 survives anchor matching — smaller, real, and mostly matching-structure.** On ATRZ
   disjoint, B2 is `P1-SUPPORTED` under AM2 (+1.499 [+0.473, +2.389], q=0.011) but falls OUTSIDE
   W2's duration-unmatched CI at 0.38× its point: the registered below-but-supported branch —
   a real separation with a large artifact share now quantified. The phase-1 §7.2 surface-copy
   revival **does not fire** (it required `P1-NOT-SUPPORTED` on a floor-clearing disjoint
   panel); W2b's descriptive tier copy stands untouched.

## §2 Constructions, censuses, and walls

The ONLY moved variable vs phase-1 DM is the hard anchor caliper
`|control days_since_63d_high − case days_since_63d_high| ≤ 2` applied per case snapshot at NN
time (prereg §1; the frozen matcher pairs per `episode_id@days_to_peak`). AM2 keeps DM's
episode-age tercile stratum; AM2-AGEFREE drops it to give F1 its only anchor-clean read. The ≤1
arm is computed everywhere as the registered escalation; six plumbing operationalizations were
appended to prereg §7 pre-results, none moving a registered quantity.

Units, labeled (phase-1 §2 discipline): *case snapshot sets* = `matching.n_matched` /
`matching.n_cases` (a set = one `episode@days_to_peak` row; `n_dropped_no_control` counts sets
left unmatched by key+ticker+caliper jointly); *matched / eligible episodes* = `e1.n_episodes` /
`episodes.n_topped_e1_eligible` (this ratio is the printed match rate); *cell n* = matched topped
episodes surviving per-cell coverage.

| cell (caliper ≤2) | case-sets matched / total | matched / eligible episodes | cell n | peak-months | match rate | wall s |
|---|---|---|---|---|---|---|
| AM2 × primary | 2,017 / 4,233 | 1,405 / 3,407 | 894 | 45 | 0.41 · MATCH-STARVED | 190.0 |
| AM2 × r63_disjoint | 104 / 498 | 89 / 814 | 31 | 12 | 0.11 · MATCH-STARVED | 97.5 |
| AM2 × atrz_disjoint | 1,346 / 2,741 | 957 / 2,201 | 632 | 43 | 0.43 · MATCH-STARVED | 195.9 |
| AGEFREE × primary | 2,949 / 4,233 | 1,798 / 3,407 | 1,464 | 46 | 0.53 | 167.7 |
| AGEFREE × r63_disjoint | 234 / 498 | 177 / 814 | 99 | 24 | 0.22 · MATCH-STARVED | 96.0 |
| AGEFREE × atrz_disjoint | 1,958 / 2,741 | 1,202 / 2,201 | 1,001 | 47 | 0.55 | 196.8 |

Wave wall 950 s against the 12 h budget; no deferral. **The caliper's cost is match starvation,
and the floors do the honest work:** seven of nine registered cells carry MATCH-STARVED, and the
R63 disjoint panel is effectively unreadable under AM2 (31 episodes vs the 100 floor; 12
peak-months at the exact floor) — both its cells are `P1-UNDERPOWERED` and carry no directional
claim. Who is missing: the caliper preferentially drops cases whose anchor value has no
like-anchor control in the same key cell, so the matched cohort under-represents case snapshots
at rare anchor values; the phase-0 NASDAQ test-symbol and survivorship disclosures carry forward
unchanged.

## §3 Validity: the diagnostic the wave exists for

AM-v1's receipts, for contrast: controls pinned at exactly 0 (p25 = p75 = 0) under case anchors
at median 2.0/1.0/2.0 — the asymmetry REVERSED, and the magnitude-only boolean read "no failure."
AM-v2's signed diagnostic (episode-first-collapsed F3 gap, case − control), both arms:

| cell | ≤2 point [CI] | ≤1 point [CI] | anchor | valid (≤2 / ≤1) |
|---|---|---|---|---|
| AM2 × primary | −0.06 [−0.25, 0.00] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AM2 × r63 | 0.00 [−0.50, +0.17] | 0.00 [0.00, +0.50] | −2.25 | TRUE / TRUE |
| AM2 × atrz | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.75 | TRUE / TRUE |
| AGEFREE × primary | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AGEFREE × r63 | 0.00 [0.00, +0.125] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AGEFREE × atrz | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.75 | TRUE / TRUE |

All three clauses (|point| ≤ 1.0; CI ⊂ (−2.0, +2.0); no positive reversal with CI excluding
zero) are TRUE in every row; `governing_arm` = the registered ≤2 caliper on all six cells,
`escalated_to_the_tighter_arm = False`, `construction_failure = False`. The residual asymmetry
is at most 0.06 sessions against registered anchors 36–46× larger. The magnitude-only boolean is
still printed in each artifact for phase-1 continuity, labeled NON-GOVERNING.

## §4 The registered answers (governing ≤2 arm)

| leg (declared) | AM2 primary | AM2 r63_disjoint | AM2 atrz_disjoint |
|---|---|---|---|
| `B3_rsi14_chg10` (+) | +0.133 [−1.142, +1.040] q=0.455 · NOT-SUPPORTED | +0.643 [−5.010, +6.798] q=0.284 · UNDERPOWERED | +1.530 [−0.884, +3.604] q=0.1165 · NOT-SUPPORTED |
| `B2_rsi14` (+) | +0.127 [−0.753, +0.955] q=0.455 · NOT-SUPPORTED | +3.351 [+0.130, +5.517] q=0.047 · UNDERPOWERED | **+1.499 [+0.473, +2.389] q=0.011 · SUPPORTED** |

| leg (declared) | AGEFREE primary | AGEFREE r63_disjoint | AGEFREE atrz_disjoint |
|---|---|---|---|
| `F1_episode_age` (−) | +2.667 [+1.250, +4.500] q=0.9998 · NOT-SUPPORTED | +3.000 [+2.000, +4.250] q=0.9998 · UNDERPOWERED (99 ep) | +1.000 [−0.250, +2.750] q=0.892 · NOT-SUPPORTED |

Readings, stated plainly:

1. **B3 — the kill, with its texture printed.** On ATRZ the point is direction-consistent
   (+1.530) and misses the registered bar (q=0.1165 vs 0.10, CI spanning zero); the registered
   rule grades it NOT-SUPPORTED, and the pre-written branch fires on the only floor-clearing
   disjoint panel. The attenuation path is the story: W2's duration-unmatched +4.67 → DM's
   duration-matched +3.268 → AM2's anchor+duration-matched +1.530 ns. On the discovery cohort
   B3 is flatly gone (+0.133), and the non-governing ≤1 escalation arm swings it NEGATIVE
   (−1.028 [−1.970, −0.239]) — a caliper-to-caliper sign swing incompatible with stable positive
   anatomy. Nothing here contradicts phase-1: DM alone had already killed B3-primary; AM-v2
   removes the anchor rival from the one panel where B3 had survived duration matching.
2. **B2 — supported and attenuated, with the artifact share now measured.** ATRZ: +1.499 inside
   its own CI floor at +0.473, q=0.011, era-stable (fade fence FALSE: |Δ| 1.38 / 2.22 / 2.15 by
   era), zero latest-era wrong-sign flags — but OUTSIDE W2's [+2.80, +4.79] at ratio 0.38×, and
   below DM's +2.885 at 0.52× within the same panel family. The registered reading: anchor
   artifacts do not eliminate W2's confirmation, and they carry roughly half-to-two-thirds of
   its measured magnitude on this panel (0.38× vs W2's unmatched point; 0.52× vs the
   duration-matched point). R63: +3.351 sits inside W2's [+2.56, +5.25] (ratio 0.87) — but the
   cell is UNDERPOWERED at 31 episodes and carries no directional claim; the comparison is
   printed because it was registered, and it decides nothing. The discovery-cohort B2 dies under
   full matching (+0.127 ns; DM had +0.952 supported) — the phase-0 panel's B2, unlike ATRZ's,
   does not survive the anchor rival, and its fade fence fires (0.64 → 0.27 → 0.26).
3. **F1 — the documented bias realized; the leg leaves the testable set.** AGEFREE was
   registered with one-directional power: control ages skew young under anchor matching, pushing
   the delta positive, against the declared negative direction. The age receipts confirm the
   bias is large — case episode-age median 22.0 vs control 8.0 on primary (gap +14.0 sessions;
   r63 +5.0; atrz +11.0) — and the measured deltas land where the bias points (+2.667 / +3.000 /
   +1.000). Mechanical grades print as registered (NOT-SUPPORTED / UNDERPOWERED /
   NOT-SUPPORTED); per the pre-registered reading these are UNINFORMATIVE-BY-DESIGN for the
   claim, never a kill. The structural conclusion is the honest one: within the
   matching-instrument family, F1 has no clean read — a stratum absorbs it, and a caliper
   without a stratum biases it beyond use. F1's anchor-clean status is UNDECIDABLE here, and no
   AM-v3 is chartered for it: the remaining evidence that could move F1 is out-of-time, not
   another construction on this tape.
4. **Era receipts:** blocks are 2022-07→2023-10 / 2023-11→2025-02 / 2025-03→2026-06 (16/16/16
   peak-months; r63 15 in era3). Zero latest-era wrong-sign flags on any registered cell, either
   arm. No `P1-SUPPORTED-ERA-CAVEAT` was earned or needed.

## §5 Mechanism color and exploratory reads (never grades)

- **The sampling-half location replicates under anchor matching.** The non-binding day-weighted
  AM2 arm restores B3-primary to +0.831 [+0.003, +1.352] (q=0.047) where episode-first AM2
  measures +0.133 ns — the same switch phase-1 isolated under DM (+1.371). B3's phase-0
  appearance continues to require length-biased control sampling; it is absent under
  episode-first sampling with or without the anchor rival controlled.
- **Pre-named exploratory read 1 — `E3f_rs_peak_lag` PERSISTS.** Under AM2 (anchor matched):
  primary −0.25 [−0.33, −0.125] q(2s)=0.095; atrz −1.33 [−2.00, −0.75] q(2s)=0.0025; r63 0.0
  ns. AGEFREE agrees (primary q=0.088, atrz q=0.0012). Anchor matching does not remove it →
  anchor-independent structure, still capped EXPLORATORY-DISCOVERY. This is the one wrong-sign
  thread that survives every matched design run so far.
- **Pre-named exploratory read 2 — `F2_drawdown_in_episode` is MIXED.** Persists on primary
  (+0.0026 q=0.0012 under AM2; +0.0035 under AGEFREE) but VANISHES on AM2 × atrz (0.0, q=1.0;
  AGEFREE atrz +0.0009 q=0.004 is nonzero but an order of magnitude under primary) — partially
  anchor-shadowed, panel-dependent.
- **Full-table scan:** no feature is wrong-signed with a CI excluding zero on all three panels
  in either construction. `F4_deepest_dip21_vs_max63` is 3/3 by sign but 2/3 by CI (r63 spans
  zero). Read from the full 36-feature tables, never survivor lists.

## §6 Instrument and gates

Branch `claude/topa-amv2-anchor-distribution`: prereg `011d9aae2f6` → plumbing+tests
`cf898eb74cb` (harness +680 / tests +572; suite 164 → 196 green under TZ=UTC) → §7
operationalizations `58d04e11a0b` → six artifacts + receipts `db05162dc17`. First artifact on
disk postdates both pre-results commits. `git diff origin/main -- engine/` = 0 lines at every
commit. Mutation spot-checks: disabling the caliper filter reds 4 tests; flipping validity
clause (c) reds 4 tests; both reverted cleanly to HEAD. Determinism: `am2/r63_disjoint` re-run →
exactly 3 differing leaves, all clock (`run_timestamp_utc`, `wall_seconds`,
`wave_elapsed_seconds`); every scientific value identical. One disclosed stamp discontinuity:
the am2/primary process started between the two pre-results commits, so its summary records
`git_sha=cf898eb74cb` and the pre-append `prereg_sha256` while the other five record
`58d04e11a0b`; the two commits differ only in §7 log text, every frozen section byte-identical.
The NaN-safe-emitter chip did not merge mid-wave; the declared absorption path was not
exercised.

## §7 Adjudication

1. **The ore-body question is answered on this tape.** The registered kill sentence fires: the
   F1/F3/B3 wrong-sign cluster is matching geometry, not anatomy — B3 killed under a valid
   anchor+duration-matched instrument on the deciding panel, F3 dissolved into the instrument
   (it IS the anchor), F1 undecidable within the family and uninformative where readable. Per
   the ore law the kill closes these constructions on this tape; out-of-time replication (the
   store-refresh workstream) is the only evidence that can reopen it, and the cluster's features
   remain display-tier confluence inputs.
2. **Phase-1's §3.2 counterfactual closes.** Under AM-v1's mechanical reading the ore body
   died a wave earlier — as an artifact of a reversed instrument. The override bought one wave
   and the correct attribution: a VALID instrument measuring ≈0 is a result; a reversed
   instrument measuring anything is not. Same terminal verdict, right door.
3. **B2's gauntlet file gains its anchor-clean estimate** (the §7.3 debt from phase-1): ATRZ
   +1.499 [+0.473, +2.389], era-stable, MATCH-STARVED caveat, 0.38× W2's unmatched point.
   Still absent before any promotion prereg: an answer to the ATRZ extension-shift rival
   (phase-1 §5.2), out-of-time evidence, and an era separation on a panel where B2 still
   stands (the phase-0-cohort era question is moot — B2-primary is dead under full matching).
   Nothing promotes; display tier unchanged.
4. **No surface obligation fires.** The revival branch required B2 `P1-NOT-SUPPORTED` on a
   floor-clearing disjoint panel; ATRZ is SUPPORTED. W2b's tiers count descriptive legs against
   per-tier libraries and claim no anatomy; no AM-v2 result touches any tier's copy. The W1/W2b
   copy-correction obligation is now DISCHARGED-BY-RESULT unless out-of-time evidence reopens
   B2.
5. **The program's remaining question is out-of-time, full stop.** Both measured
   counter-explanations (duration/length-bias; anchor geometry) are now instrumented and
   answered on this tape. The first post-store-refresh wave re-reads vintage rosters and the
   exemplar census before anything else (unchanged charter). No AM-v3, no new construction on
   this tape is chartered.

## §8 Execution log

- 2026-08-12 — Six cells run inside the wall (950 s); all six (construction × panel) VALID at
  both calipers, governing arm ≤2 mechanically everywhere; registered grades and branch firings
  as §4/§7; report drafted from the six committed summaries with every decision-bearing number
  (validity diagnostics, all nine registered cells, both B2 comparisons, age receipts, era
  blocks, fade fences, day-weighted arm, pre-named exploratory rows, ≤1-arm rows quoted in §4)
  read directly from the artifacts before drafting.
