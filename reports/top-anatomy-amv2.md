# Top Anatomy — AM-v2 report (anchor-distribution-matched controls)

Prereg: `research/top_anatomy/TOPA_AMV2_PREREG.md`, frozen at `011d9aae2f6` before any result
existed (plumbing `cf898eb74cb`, §7 operationalizations `58d04e11a0b`, results `db05162dc17` —
commit order verifiable on the branch). Display tier throughout; AVOID-not-SHORT permanently
(`DNR:KILL-DIRECTIONAL-SHORTING`); no AM-v2 claim is about today's market (frozen 2026-07-02
vintage, declared).

## §1 The answer, in three parts

1. **The instrument worked, everywhere it was tested.** The per-case-snapshot anchor caliper
   collapsed the case-vs-control anchor gap to 0.0 (worst panel by |point|: −0.0625
   [−0.25, 0.00]; widest CI: r63's [−0.50, +0.17]) against registered anchors of −2.25/−2.75,
   with all three signed validity clauses TRUE on every (construction × panel) at BOTH calipers
   — §3 states which clauses had teeth and which the caliper satisfies by construction. No
   escalation fired, no construction failed, and the adjudicator override phase-1 needed has no
   successor here: the governing arm was determined mechanically on all six
   (construction × panel) cells.
2. **The registered kill fires, at its registered grain.** B3 — the ore body's only jointly
   readable member — is `P1-NOT-SUPPORTED` under a VALID anchor+age-matched construction on the
   only floor-clearing disjoint panel (ATRZ: +1.530 [−0.884, +3.604], q=0.1165) and on the
   discovery cohort (+0.133 [−1.142, +1.040], q=0.455), with R63 dark (31 episodes vs the 100
   floor). The prereg's pre-written sentences therefore fire: for B3, *"B3's separation is
   anchor geometry, not anatomy"*; for the cluster, **"the ore-body anatomy claim is CLOSED on
   this tape as a cluster claim"** — B3 not confirmed under the clean instrument, F3 the
   matching variable and never separately gradeable, F1 undecided here (§4.3). CLOSED means the
   claim is not established on this tape; §4.1 prints the deciding cell's fragility receipts —
   `P1-NOT-SUPPORTED` is failure to confirm, not demonstrated absence. The kill is scoped:
   these constructions, this tape; out-of-time replication is the only reopening evidence, and
   the cluster's features remain display-tier confluence inputs (non-standalone ≠ worthless).
3. **B2 survives anchor matching — smaller and real.** On ATRZ disjoint, B2 is `P1-SUPPORTED`
   under AM2 (+1.499 [+0.473, +2.389], q=0.011) but falls OUTSIDE W2's duration-unmatched CI at
   0.38× its point — the registered below-but-supported branch: matched-design artifacts
   (duration and anchor jointly, plus re-draw noise) carry ~62% of W2's measured ATRZ magnitude
   (§4.2). The phase-1 §7.2 surface-copy revival **does not fire** (its AM-v2 trigger — B2
   `P1-NOT-SUPPORTED` on a floor-clearing disjoint panel — did not occur); the obligation is
   dormant, not retired, and W2b's descriptive tier copy stands untouched.

**What the verdict means for the motivating exemplars and the current regime** (prereg §6
coverage gate): the phase-0/W2 observations that motivated the ore body — topped episodes
looking *younger, fresher-high, faster-heating* than matched survivors on four panels — remain
real measurements; what dies is their reading as top anatomy. A topped episode measured at the
frozen {21,10,5} snapshots sits a median 1–2 sessions from its own 63d high, while an arbitrary
surviving extension day sits staler by 2.25 / 2.25 / 2.75 sessions (the registered F3 anchors,
signed case − control). F3's separation *is* that measurement geometry by construction. For B3 the
registered branch fires on anchor geometry because that is the rival AM-v2 tested — with
controls at like anchors the confirming legs do not clear their bars — but this wave's own
non-binding sampling arm locates B3's dependence in length-biased control sampling instead
(§5): both readings agree the leg is not established anatomy, and neither mechanism is proven.
For the
current regime nothing on any surface changes (Winner Health counts descriptive legs against
per-tier libraries and claims no anatomy), but the research-side reading changes now:
"younger/fresher/faster-heating" is not to be cited as top anatomy from this program while the
kill stands. Who is missing from the deciding evidence: the R63 panel (dark under AM2), and the
upper half of the case anchor distribution (§2) — the kill is a statement about near-63d-high
case snapshots, where the case MEDIAN sits (1–2 sessions), but the case census spans the full
distribution (p75 = 8/4/6), so it is not an estimate over the full case-set census.

## §2 Constructions, censuses, and walls

**Two variables move vs phase-1 DM** (caliper: prereg §1; seed: prereg §2 — both declared
pre-results): the hard anchor
caliper `|control days_since_63d_high − case days_since_63d_high| ≤ 2` applied per case
snapshot at NN time (the frozen matcher pairs per `episode_id@days_to_peak`), and the fresh
seed (20260811 → 20260812) governing the episode-first control draw and the bootstrap. DM↔AM2
contrasts therefore carry re-draw noise as well as the caliper, and are read as such throughout
(§4.1, §4.2). AM2 keeps DM's episode-age tercile stratum; AM2-AGEFREE drops it to give F1 its
only anchor-clean read. The ≤1 arm is computed everywhere as the registered escalation; six
plumbing operationalizations were appended to prereg §7 pre-results, none moving a registered
quantity.

Units, labeled (phase-1 §2 discipline): *case snapshot sets* = `matching.n_matched` /
`matching.n_cases` (a set = one `episode@days_to_peak` row; `n_dropped_no_control` counts sets
left unmatched by key+ticker+caliper jointly); *matched / eligible episodes* = `e1.n_episodes` /
`episodes.n_topped_e1_eligible` (this ratio is the printed match rate); *cell n* = matched
topped episodes surviving per-cell coverage; *cell peak-months* = distinct peak months among
the cell's own matched episodes (panel-level counts are equal or higher: 47/22/47 AM2,
47/29/47 AGEFREE).

| cell (caliper ≤2) | case-sets matched / total | matched / eligible episodes | cell n | cell peak-months | match rate | wall s |
|---|---|---|---|---|---|---|
| AM2 × primary | 2,017 / 4,233 | 1,405 / 3,407 | 894 | 45 | 0.41 · MATCH-STARVED | 190.0 |
| AM2 × r63_disjoint | 104 / 498 | 89 / 814 | 31 | 12 | 0.11 · MATCH-STARVED | 97.5 |
| AM2 × atrz_disjoint | 1,346 / 2,741 | 957 / 2,201 | 632 | 43 | 0.43 · MATCH-STARVED | 195.9 |
| AGEFREE × primary | 2,949 / 4,233 | 1,798 / 3,407 | 1,464 | 46 | 0.53 | 167.7 |
| AGEFREE × r63_disjoint | 234 / 498 | 177 / 814 | 99 | 24 | 0.22 · MATCH-STARVED | 96.0 |
| AGEFREE × atrz_disjoint | 1,958 / 2,741 | 1,202 / 2,201 | 1,001 | 47 | 0.55 | 196.8 |

Wave wall 950 s against the 12 h budget; no deferral. **The caliper's cost is match starvation,
and the floors do the honest work:** seven of nine registered cells carry MATCH-STARVED, and
the R63 disjoint panel is effectively unreadable under AM2 (31 episodes vs the 100 floor; 12
cell peak-months at the exact floor) — both its cells are `P1-UNDERPOWERED` and carry no
directional claim. **Who the caliper drops is not random:** it removes the whole upper half of
the case anchor distribution, not rare tails — matched case snapshots sit at anchor mean 2.50 /
1.45 / 2.30 (p75 = 3/2/2) versus the unrestricted case census at mean 6.99 / 3.92 / 5.64
(p75 = 8/4/6), with 52% / 79% / 51% of AM2 case-sets left unmatched. AM-v2's registered
estimates describe **near-63d-high case snapshots** — which is where the frozen pipeline
measures cases, and exactly the population the anchor rival is about — but they are not
estimates over the full case-set census. The phase-0 NASDAQ test-symbol and survivorship
disclosures carry forward unchanged.

## §3 Validity: the diagnostic, with its teeth stated

AM-v1's receipts, for contrast: controls pinned at exactly 0 (p25 = p75 = 0) under case anchors
at median 2.0/1.0/2.0 — the asymmetry REVERSED, and the magnitude-only boolean read "no
failure." AM-v2's signed diagnostic (episode-first-collapsed F3 gap, case − control), both arms:

| cell | ≤2 point [CI] | ≤1 point [CI] | anchor | valid (≤2 / ≤1) |
|---|---|---|---|---|
| AM2 × primary | −0.0625 [−0.25, 0.00] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AM2 × r63 | 0.00 [−0.50, +0.17] | 0.00 [0.00, +0.50] | −2.25 | TRUE / TRUE |
| AM2 × atrz | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.75 | TRUE / TRUE |
| AGEFREE × primary | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AGEFREE × r63 | 0.00 [0.00, +0.125] | 0.00 [0.00, 0.00] | −2.25 | TRUE / TRUE |
| AGEFREE × atrz | 0.00 [0.00, 0.00] | 0.00 [0.00, 0.00] | −2.75 | TRUE / TRUE |

**Which clauses could have failed, stated honestly:** the per-pair delta is the case value minus
the mean of its finite controls, and the caliper bounds every control's anchor within ±caliper
of the case's — so on the ≤2 arm, clause (b) (CI ⊂ (−2, +2)) holds **by construction**, and on
the ≤1 arm clauses (a) and (b) both do. The empirical content of the pass is: clause
(c) — no positive reversal, AM-v1's actual failure mode, which the caliper does NOT preclude
(controls could have clustered systematically fresher than cases inside the band); clause (a)
on the ≤2 arm (the point could have reached 2.0); and the near-degenerate concentration at
0.00 itself — which comes not from exact-anchor pairs (the realised per-pair |Δanchor| has
median 1.0 on all six cells; p75 1.0 except 2.0 on AM2 × r63) but from symmetry: residual gaps
sit on both sides of the case anchor and cancel in the per-pair control mean (the delta
definition above), and the episode-first median collapses what remains. The diagnostic's zero says the residual gaps are
unbiased, not that they are absent. The
residual asymmetry is at most 0.0625 sessions, 36× smaller than its panel's −2.25 anchor (the
other panels' residuals are exactly 0.00). `governing_arm` = the registered ≤2 caliper on all
six (construction × panel) cells, `escalated_to_the_tighter_arm = False`,
`construction_failure = False`. AM-v1's `collapsed_by_magnitude` boolean was dropped from the
AM-v2 artifacts; what remains is a prose field beside each diagnostic recording that the
magnitude-only reading was ruled NON-GOVERNING.

## §4 The registered answers (governing ≤2 arm)

| leg (declared) | AM2 primary | AM2 r63_disjoint | AM2 atrz_disjoint |
|---|---|---|---|
| `B3_rsi14_chg10` (+) | +0.133 [−1.142, +1.040] q=0.455 · NOT-SUPPORTED | +0.643 [−5.010, +6.798] q=0.284 · UNDERPOWERED | +1.530 [−0.884, +3.604] q=0.1165 · NOT-SUPPORTED |
| `B2_rsi14` (+) | +0.127 [−0.753, +0.955] q=0.455 · NOT-SUPPORTED | +3.351 [+0.130, +5.517] q=0.047 · UNDERPOWERED | **+1.499 [+0.473, +2.389] q=0.011 · SUPPORTED** |

| leg (declared) | AGEFREE primary | AGEFREE r63_disjoint | AGEFREE atrz_disjoint |
|---|---|---|---|
| `F1_episode_age` (−) | +2.667 [+1.250, +4.500] q=0.9998 · NOT-SUPPORTED | +3.000 [+2.000, +4.250] q=0.9998 · UNDERPOWERED (99 ep) | +1.000 [−0.250, +2.750] q=0.892 · NOT-SUPPORTED |

### §4.1 B3 — the kill, with the deciding cell's fragility printed

On ATRZ the point is direction-consistent (+1.530) and misses the registered bar (q=0.1165 vs
0.10 — a 0.0165 miss; CI spanning zero). Three receipts temper what the grade can mean, and
none changes it:

- the cell's CI **contains DM's +3.268** and **overlaps W2's [+2.80, +6.71]** — the point
  attenuation W2 +4.67 → DM +3.268 → AM2 +1.530 is a path of point estimates whose intervals
  are not separable at this wave's power, and the DM→AM2 step carries re-draw noise (§2) as
  well as the caliper;
- the same artifact's **ticker-clustered CI [+0.470, +2.721] excludes zero** on the declared
  side. The registered inference is the episode-peak-month block bootstrap, so the grade
  stands — and ticker clustering is nowhere a registered inference in this program. Under it,
  the CI clause of the grade would have flipped, and the artifact's exploratory table carries a
  ticker-side two-sided p of 0.003 for this cell — well inside any plausible bar. No
  ticker-based q exists (BH runs off the block-bootstrap p in both the engine and the harness),
  so no registered grade can be computed under ticker clustering; what the receipt does say is
  that the cell's fragility is not confined to the interval;
- per the program's own standard (W2 §3.1, phase-1 §4.3): only a CI that *excludes* the prior
  effect supports "shown absent." This cell supports **failure to confirm** — the registered
  kill's actual content — not demonstrated absence.

On the discovery cohort B3 is not supported (+0.133; ticker CI [−1.011, +0.728] agrees; the
block CI still contains DM's +0.429, so the cohort is unreadable-at-this-power rather than
shown-flat), and the
non-governing ≤1 escalation arm swings it NEGATIVE (−1.028 [−1.970, −0.239]) — a
caliper-to-caliper sign swing incompatible with a stable positive reading there. Nothing here
contradicts phase-1: DM alone had already killed B3-primary; AM-v2 removes the anchor rival
from the one panel where B3 had survived duration matching, and the registered branch fires on
the grades as declared.

### §4.2 B2 — supported and attenuated, with the artifact share decomposed in registered ratios

ATRZ: +1.499 inside its own CI floor at +0.473, q=0.011, era-stable (fade fence FALSE: |Δ|
1.38 / 2.22 / 2.15 by era), zero latest-era wrong-sign flags — but OUTSIDE W2's [+2.80, +4.79].
The registered same-design ratio is **0.38×** W2's unmatched point (the artifact's
`point_estimate_ratio_to_w2_anchor`; phase-1's DM measured **0.74×** on the same panel under
the same registered comparison). Read together: matched-design artifacts jointly carry ~62% of
W2's measured ATRZ magnitude; phase-1 attributed ~26 points of that to duration matching alone;
the further drop between the two registered ratios (0.74× → 0.38×) arrived with the caliper
**plus** the fresh seed and a smaller matched cohort (980 → 632 cell episodes), is un-CI'd, and
is not decomposed further — cross-design ratios (AM2/DM division) are banned, and none is
printed. R63: +3.351 sits inside W2's [+2.56, +5.25] (ratio 0.87) — but the cell is
UNDERPOWERED at 31 episodes and carries no directional claim; the comparison is printed because
it was registered, and it decides nothing. On the discovery cohort, B2 is **not supported under
AM2** (+0.127 [−0.753, +0.955], q=0.455) — a CI that still contains DM's +0.952, so the panel
is unreadable-at-this-power rather than shown-flat; its fade fence fires (0.64 → 0.27 → 0.26).
Phase-1's era-separation debt (§7.3 there) is **not discharged, only unreadable here** — it
transfers to any panel where B2 still stands.

### §4.3 F1 — the documented bias realized; undecided here, and honestly so

AGEFREE was registered with one-directional power: control ages skew young under anchor
matching, pushing the delta positive, against the declared negative direction. The age receipts
confirm the skew is large — these are **marginal medians of two different populations** (matched
case snapshots, n=2,949 on primary, vs distinct control days, n=2,529): case episode-age median
22.0 vs control 8.0 on primary (marginal gap +14.0 sessions; r63 +5.0; atrz +11.0). The paired
registered estimates are the table's (+2.667 / +3.000 / +1.000), landing where the bias points;
their ticker-clustered CIs exclude zero on the positive side on all three panels ([+1.625,
+3.750] / [+1.667, +4.000] / [+0.167, +1.500]) — consistent with the documented bias
DIRECTION, so these receipts cannot say the bias accounts for the size of the read. It grades
exactly as registered: NOT-SUPPORTED / UNDERPOWERED /
NOT-SUPPORTED, **UNINFORMATIVE-BY-DESIGN for the negative claim, never a kill.** What this wave can and cannot say about the instrument family:
the caliper-width lever barely moves F1 (≤1 / ≤2 / ≤4 arms: +2.896/+2.667/+2.875 on primary;
+3.000 flat on r63; +1.000/+1.000/+0.750 on atrz — a ≤0.25-session spread), but nothing in the
wave **measures the bias magnitude** — only its direction was documented. F1 is therefore
undecided here: uninformative without a quantified bias, with whether some other construction
could read it cleanly left open. This wave charters none (§7.5); out-of-time evidence comes
first.

### §4.4 Era receipts

Blocks are 2022-07→2023-10 / 2023-11→2025-02 / 2025-03→2026-06 (16/16/16 peak-months; r63 15
in era3). Zero latest-era wrong-sign flags on any registered cell, either arm. No
`P1-SUPPORTED-ERA-CAVEAT` was earned or needed.

## §5 Mechanism color and exploratory reads (never grades)

- **The sampling switch moves B3 on every panel — quoted in full because it touches the kill's
  own cell.** The non-binding day-weighted AM2 arm (prereg §5): B3-primary +0.831 [+0.003,
  +1.352] q=0.047 where episode-first AM2 measures +0.133 ns; **B3-atrz +1.994 [+0.821, +3.362]
  q=0.0005** where the registered episode-first cell is +1.530 ns; B3-r63 +2.037 [+0.153,
  +4.480] q=0.0235 where the registered cell is dark. Phase-1's caution carries verbatim: the
  switch also moves n (894 → 1,969 on primary) and control composition, so it **locates** the
  sampling dependence rather than proving it, and it is non-binding by prereg §5. The honest
  composite: under episode-first sampling WITH ANCHORS MATCHED — the registered design, which
  weights each surviving episode once — B3 clears no bar anywhere (under episode-first DM
  without the caliper, B3-atrz had cleared its bar at +3.268); under length-biased
  day-weighting it reads positive
  on all three panels even with anchors matched. B3's separation, where it exists, lives in
  giving long surviving episodes more weight, not in anchor geometry alone — consistent with
  phase-1's location of the same dependence under DM.
- **Pre-named exploratory read 1 — `E3f_rs_peak_lag` PERSISTS.** Under AM2 (anchor matched):
  primary −0.25 [−0.33, −0.125] q(2s)=0.095; atrz −1.33 [−2.00, −0.75] q(2s)=0.0025; r63 0.0
  ns. AGEFREE: atrz agrees (q=0.0012); its primary q=0.088 but the CI touches zero
  ([−0.417, 0.00]) — not separation under the program's own standard. Anchor matching does not
  remove E3f → anchor-independent structure, still capped EXPLORATORY-DISCOVERY. This is the
  one wrong-sign thread that survives every matched design run so far.
- **Pre-named exploratory read 2 — `F2_drawdown_in_episode` is MIXED.** Persists on primary
  (+0.0026 q=0.0012 under AM2; +0.0035 under AGEFREE) but VANISHES on AM2 × atrz (0.0, q=1.0;
  AGEFREE atrz +0.0009 q=0.004 is nonzero but ~4× under primary's value) — partially
  anchor-shadowed, panel-dependent.
- **Full-table scan (grain stated):** the scan asked one question of the full 36-feature tables
  in both constructions — is any feature wrong-signed with a CI excluding zero on all three
  panels? — and the answer is no (maximum 2/3: `F4_deepest_dip21_vs_max63`, whose r63 CI spans
  zero). Nearest adjacent pattern, noted without a claim: `A7_late_gain_share` under AGEFREE
  has a CI excluding zero on all three panels with a sign flip (−0.050 / +0.105 / −0.042; the
  r63 row is floor-dropped, `interpretable=False`) — the sign-unstable shape W2 §4 named. Read
  from the full tables, never survivor lists.

## §6 Instrument and gates

Branch `claude/topa-amv2-anchor-distribution`: prereg `011d9aae2f6` → plumbing+tests
`cf898eb74cb` (insertions +647 harness / +563 tests; suite 164 → 196 green under TZ=UTC) → §7
operationalizations `58d04e11a0b` → six artifacts + receipts `db05162dc17`. First artifact on
disk postdates both pre-results commits; the am2/primary **run process** started 47 s before
the §7-operationalizations commit landed (17:32:44 vs 17:33:31 PDT), which is why that one
summary records `git_sha=cf898eb74cb` and the pre-append `prereg_sha256` while the other five
record `58d04e11a0b` — the two commits differ only in §7 log text, every frozen section
byte-identical. `git diff origin/main -- engine/` = 0 lines at every commit. Mutation
spot-checks: disabling the caliper filter reds 4 tests; flipping validity clause (c) reds 4
tests; both reverted cleanly to HEAD. Determinism: `am2/r63_disjoint` re-run → exactly 3
differing leaves, all clock (`run_timestamp_utc`, `wall_seconds`, `wave_elapsed_seconds`);
every scientific value identical. The NaN-safe-emitter chip did not merge mid-wave; the
declared absorption path was not exercised.

## §7 Adjudication

1. **The ore-body question is answered on this tape, at its registered grain, with its deciding
   panel named.** The registered cluster sentence fires: **the ore-body anatomy claim is CLOSED
   on this tape as a cluster claim** — B3's separation is anchor geometry rather than anatomy
   (the pre-written B3 branch, fired on grades: NOT-SUPPORTED on ATRZ, the only floor-clearing
   disjoint panel, with R63 dark at 31 episodes; §4.1 prints the fragility receipts and the
   failure-to-confirm-not-absence rider; the branch names the rival AM-v2 tested, while §5's
   non-binding sampling arm locates B3's dependence in length-biased sampling instead — both
   readings agree the leg is not established anatomy, neither mechanism is proven); F3 is the
   matching variable and was never separately
   gradeable; F1 is undecided within this wave (§4.3). Per the ore law the kill closes these
   constructions on this tape; out-of-time replication (the store-refresh workstream) is the
   only evidence that can reopen it, and the cluster's features remain display-tier confluence
   inputs.
2. **Phase-1's §3.2 counterfactual closes, in both directions.** Under AM-v1's mechanical
   reading the ore body died a wave earlier — as an artifact of a reversed instrument — and
   **B2 would have died with it** (AM-v1's mechanical grades: B2 NOT-SUPPORTED on all three
   panels at −7.38 / −3.39 / −3.78), which AM-v2 now contradicts on ATRZ (+1.499 SUPPORTED).
   The override bought one wave and two corrections: the right attribution for the ore-body
   kill (a VALID instrument measuring ≈0 is a result; a reversed instrument measuring anything
   is not), and the survival of a leg the broken instrument would have executed.
3. **B2's gauntlet file gains its anchor-clean estimate** (the §7.3 debt from phase-1): ATRZ
   +1.499 [+0.473, +2.389], era-stable there, MATCH-STARVED caveat, 0.38× W2's unmatched point
   by the registered same-design ratio. Still absent before any promotion prereg: an answer to
   the ATRZ extension-shift rival (phase-1 §5.2), out-of-time evidence, and the era separation
   phase-1 required — not discharged by this wave, only unreadable on the discovery cohort
   (§4.2), so it transfers to the panels where B2 stands. Nothing promotes; display tier
   unchanged.
4. **No surface obligation fires.** The AM-v2 prereg narrowed phase-1 §7.2's revival trigger to
   B2 `P1-NOT-SUPPORTED` on a floor-clearing disjoint panel; ATRZ B2 is SUPPORTED, so the
   trigger did not occur. The obligation is **dormant, not retired** — out-of-time evidence
   that kills B2 would revive it. W2b's tiers count descriptive legs against per-tier libraries
   and claim no anatomy; no AM-v2 result touches any tier's copy.
5. **The program's remaining question is out-of-time, full stop.** Both measured
   counter-explanations (duration/length-bias; anchor geometry) are now instrumented on this
   tape. The first post-store-refresh wave re-reads vintage rosters and the exemplar census
   before anything else (unchanged charter). This wave charters no further construction on this
   tape — not because another is provably impossible (§4.3 leaves F1's readability open), but
   because the binding open question is evidence scope, and no on-tape construction can answer
   it.

## §8 Execution log

- 2026-08-12 — Six cells run inside the wall (950 s); all six (construction × panel) VALID at
  both calipers, governing arm ≤2 mechanically everywhere; registered grades and branch firings
  as §4/§7; report drafted from the six committed summaries with every decision-bearing number
  read directly from the artifacts before drafting.
- 2026-08-12 — G0.5 adversarial review (Opus): **NOT PRESENTABLE** — 6 blockers / 15 must-fix /
  5 nits, all applied in this revision. Every §2/§3/§4 number and exploratory row had
  reproduced exactly (reviewer re-derived all of them; suite re-run green); the blockers were
  adjudication-level: the seed was a second moved variable presented as one (BL-1 — DM↔AM2
  contrasts now carry the re-draw caveat); the artifact-share sentence mixed denominators and
  leaned on a banned cross-design ratio (BL-2 — restated in registered ratios only: 0.74× →
  0.38×, joint ~62%); the deciding B3 cell's fragility was undisclosed (BL-3 — CI contains
  DM's point and overlaps W2's, q missed by 0.0165, ticker-clustered CI excludes zero; the
  failure-to-confirm rider now leads §4.1); the pre-written branch was fired HARDENED and
  extended to legs it wasn't written for (BL-4 — restored to the registered grain); F1's
  closure overreached its evidence (BL-5 — "biases beyond use" withdrawn; caliper-invariance
  receipts printed; readability left open); and the prereg §6 exemplar-coverage clause was
  unmet (BL-6 — the §1 coverage paragraph). Must-fixes included the day-weighted arm quoted
  only where it flattered the story (now quoted on all three panels including the kill's own
  cell), the anchor-census scope statement (the caliper drops the upper half of the case anchor
  distribution), the B2-primary "dead" overstatement (CI contains DM's point), the undefined
  DISCHARGED-BY-RESULT status (now: dormant), clause-teeth disclosure in §3, and unit
  relabelings. Verification pass 2 commissioned on this revision.
- 2026-08-12 — G0.5 pass 2 (same reviewer, fresh eyes on the revision): all 26 pass-1 findings
  verified RESOLVED, every new number reproduced — verdict **NOT PRESENTABLE** on 1 blocker /
  7 must-fix / 4 nits, all introduced by the rewrite, all applied in this revision. The
  blocker: the new §1 coverage paragraph attributed B3's separation to measurement geometry
  while §5's own day-weighted receipts show B3 positive on all three panels WITH anchors
  matched — §1 and §7.1 now carry the reconciliation (the registered branch names the rival
  tested; the sampling arm locates the dependence; both agree the leg is not established
  anatomy, neither mechanism proven). Must-fixes: the 0.00 diagnostic explained by symmetry of
  residual gaps (realised per-pair |Δanchor| median 1.0), not exact-anchor pairs; the
  ticker-clustering counterfactual narrowed to the CI clause (no ticker-side q exists; ticker
  clustering is unregistered); B3-primary and the §5 episode-first claim given the same
  unreadable-at-this-power / with-anchors-matched riders the rest of the report uses; A7's
  "separates" wording (a sign-gated survivor-list term) replaced with the CI statement plus its
  r63 `interpretable=False` disclosure; the F1 bias sentence limited to direction (no magnitude
  is measured); §1's anchor-census clause now carries the full-distribution rider.
  Verification pass 3 commissioned.
- 2026-08-12 — G0.5 pass 3: all 12 pass-2 findings verified RESOLVED (registered tables
  byte-identical across all three drafts); **NOT PRESENTABLE** on 1 blocker / 0 must-fix /
  3 nits. The blocker: the pass-2 ticker sentence asserted "no ticker-side p is emitted" while
  the artifact's exploratory table carries `ticker_p_value = 0.003` for the deciding cell — the
  honest reading (now in §4.1) is that under ticker clustering the cell's fragility is not
  confined to the interval clause; no ticker-based q exists, so no registered grade can be
  computed under it. Nits: the signed-anchor magnitude phrasing, two pass-2 edit
  restatements deduped. Applied in this revision; final verification pass commissioned.
