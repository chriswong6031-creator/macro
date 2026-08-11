# TOPA Phase-1 Preregistration — Anchor-Matched Re-Registration (`top_anatomy_p1`)

**Status:** FROZEN at commit time of this file, BEFORE any phase-1 number exists. Commit order on
branch `claude/topa-phase1-anchor-matched` is the proof. Amendments are append-only entries in §7 —
the frozen sections are never edited.

Display/research tier, zero scored authority. AVOID-not-SHORT permanently
(`DNR:KILL-DIRECTIONAL-SHORTING`): nothing downstream of this wave is a probability, rank, size,
gate, or exit rule. Constitution: `research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md` (G0 gates bind; G0.5
adversarial review REQUIRED before the report is presented). Charter:
`reports/top-anatomy-w2.md` §7.2 — phase-1 exists to decide the artifact-vs-anatomy status of the
F1/F3/B3 ore body and of B2's duration-unmatched confirmations.

## §0 The question

W2 left one decidable question on the table. The ore body — `F1_episode_age`,
`F3_days_since_63d_high`, `B3_rsi14_chg10` — replicates on all four W2 panels at q ≤ 0.01, and
`B2_rsi14` is W2-CONFIRMED on both arms. But two **mechanical counter-explanations were named in
phase-0, never discharged, and SCALE with the disjoint construction**:

1. **Peak-anchor artifact.** Topped episodes are measured at their peak day; the peak day is
   near-definitionally a fresh 63d high. Controls are arbitrary EXT days sitting some distance past
   their last high. F3's "topped = fresher highs" — and any feature correlated with proximity to a
   local high (B2, B3) — could be produced by the anchor asymmetry alone.
2. **Length-biased, day-weighted control sampling.** Every qualifying EXT day of every continued
   episode is a control candidate, so long episodes are overrepresented in the candidate pool.
   Older-looking controls are what that sampling produces on its own — F1's "topped = younger"
   could be pure sampling geometry. Separately, B2/B3's heat effects were estimated with
   **episode duration unmatched** (W2 report §3 caveat): "topped just younger, and younger = hotter"
   remains a live confound for the heat legs.

Phase-1 re-registers the four legs under two purpose-built control constructions, each of which
removes one named mechanism while holding everything else frozen. If the effects survive, the
artifact stories die. If they collapse, the collapse is the finding and the ore body is
re-classified as matching geometry. Either answer is a result; both get printed.

## §1 The moved variable: two control constructions

Everything about the pipeline is frozen (§2). The ONLY thing phase-1 changes is how control
observations are selected/stratified. Two constructions, run separately:

**AM — anchor-matched.** Control candidate days are restricted to **fresh-high days**: continued-
episode EXT days with `days_since_63d_high == 0` (the same rolling-63d closing-high definition the
F3 feature uses; tolerance sensitivity in §5). Candidate sampling is **episode-first**: ONE
qualifying day per continued episode, drawn with the frozen seed, before NN matching. Both groups
are then measured at like anchors — topped at its peak day (itself a fresh-high day by
construction), control at a fresh-high day it went on to survive. AM discharges mechanism (1)
(anchor asymmetry) AND mechanism (2)'s sampling half (episode-first draw kills length weighting).
Under AM, `F3` is the matching variable: its topped−control delta MUST collapse toward zero, and
that collapse is the **matching diagnostic** (printed, ungraded — a non-collapse means the
construction failed, and every AM cell is then reported UNDERPOWERED-BY-CONSTRUCTION-FAILURE).

**DM — duration-matched.** The frozen W4 matching key gains an **episode-age tercile** stratum
(age measured at the anchor day; tercile edges cut within each panel's pooled candidate set —
topped peak-days plus control candidate days — and printed). Candidate sampling is episode-first
(same seeded one-day-per-episode draw), so mechanism (2) is fully discharged; mechanism (1) is NOT
discharged in DM (controls remain arbitrary-anchor EXT days) and every DM `F3` cell carries that
caveat inline. Under DM, `F1` is (coarsely) the matching variable: its delta is printed, ungraded,
as the stratification diagnostic.

Neither construction re-derives anything else: same episodes, same races, same features, same
snapshot collapse, same bootstrap, same floors as §2.

## §2 Frozen from phase-0 run-3 and W2 (no re-derivation permitted)

- **Tape:** `data/massive_stock_day`, span 2021-07-06 → **2026-07-02** (1,254 sessions), the SAME
  frozen vintage as phase-0/W2, threaded through the #5319 guard with `--allow-stale` (declared
  here: the vintage is prereg-frozen; staleness is disclosed, not hidden). Universe filter and the
  NASDAQ test-symbol disclosure carry forward unchanged. **No phase-1 claim is about today's
  market**; out-of-time replication remains parked until the store refresh lands.
- **Track:** W only (registration track, unadjusted prints + sanity-segmented identities).
- **Pipeline:** §4.2 episodes (gap ≤ 21 merge), §4.3 races (−20% from running peak vs +15%, ≤250
  sessions), 36 PIT features in 6 families, W4 NN matching (quarter × r126-quintile × rv63-tercile
  × dvol-tercile, ≤4 NN), episode-first median collapse over the {21,10,5} snapshots,
  episode-peak-month block bootstrap **B = 2000**, ≥12 distinct peak-month floor, feature coverage
  floor, min-finite-controls rule. Bin edges recomputed within each panel's own candidate pool
  (population-relative by construction, as in W2). **Seed: 20260811** (fresh — phase-1's draws are
  new; declared before results).
- **Instrument:** `engine/top_anatomy.py` byte-frozen at main (`git diff origin/main -- engine/`
  empty at every phase-1 commit). `scripts/research_top_anatomy_phase0.py` gains plumbing ONLY —
  `--p1-construction {am,dm}` and `--p1-panel {primary,r63_disjoint,atrz_disjoint}` (or equivalent
  spelled flags), cache identity stamps extended with the construction key (present-and-equal
  hard-check, exactly as `ext_variant` was added in W2), and phase-1 summary emission — committed
  BEFORE any full-panel result. Feature panels are episode-anchored (W2 finding) and rebuild
  per (arm × construction) as their identity requires; the repair+segmentation panel cache is
  shared. If the NaN-safe-emitter chip (sibling session) merges mid-wave, absorb by rebase and
  re-run the determinism check — the W2/#5319 procedure.

## §3 Confirmatory hypotheses (declared BEFORE any phase-1 number exists)

Four legs, one-sided in their phase-0/W2 observed directions, each registered ONLY in the
construction(s) that can test it. Anchors quoted from `reports/top-anatomy-w2.md` §3–§4 and
phase-0 run-3.

| Leg | Direction | Registered in | Anchors (ph0 / R63 DISJ / ATRZ DISJ) |
|---|---|---|---|
| `F1_episode_age` | − (topped younger) | **AM** (DM: diagnostic, ungraded) | −9.7 / −2.2 [−3.5,−1.0] / −17.0 [−21.8,−12.3] |
| `F3_days_since_63d_high` | − (fresher highs) | **DM** (AM: diagnostic, ungraded) | −2.25 / −2.25 [−2.75,−1.75] / −2.75 [−3.25,−2.06] |
| `B3_rsi14_chg10` | + (accelerating heat) | **AM and DM** | +1.42 / +2.23 [+0.85,+4.73] / +4.67 [+2.80,+6.71] |
| `B2_rsi14` | + (hotter) | **AM and DM** | +1.29 / +3.87 [+2.56,+5.25] / +3.92 [+2.80,+4.79] |

- **Cells:** 3 registered legs per construction (AM: F1,B3,B2; DM: F3,B3,B2) × 2 constructions ×
  3 panels (§4) = **18 registered cells**, all printed with delta + CI + q regardless of outcome.
- **Multiplicity:** BH-FDR **q ≤ 0.10 within each (panel × construction) family of exactly 3**,
  one-sided p in the declared direction read off the same block-bootstrap draws (the frozen
  machinery's one-sided convention).
- **Grades (per cell):** `P1-SUPPORTED` (declared sign AND q ≤ 0.10 AND floors met) /
  `P1-NOT-SUPPORTED` (floors met, criteria unmet — including wrong sign) / `P1-UNDERPOWERED`
  (any floor unmet; no directional claim).
- **Leg synthesis (declared now, so the report cannot invent it):** a leg is **P1-ROBUST** iff
  P1-SUPPORTED in its registered construction(s) on BOTH W2 disjoint panels (for B3/B2, that means
  supported under BOTH AM and DM on both disjoint panels; a leg supported under one construction
  only is **P1-CONSTRUCTION-DEPENDENT**, named per construction). The phase-0 primary panel is
  supporting evidence, never the decider — the generalization cohorts decide.
- **B2 anchor comparison (registered reading, not a grade):** for each disjoint panel, state
  whether the phase-1 B2 estimate falls inside W2's duration-unmatched CI ([+2.56,+5.25] R63 /
  [+2.80,+4.79] ATRZ). Inside → duration/anchor artifacts do not explain W2's confirmation.
  Below-but-supported → partial artifact share, quantified as the point-estimate ratio (per panel,
  same matched design — cross-design ratios remain banned). NOT-SUPPORTED → W2's B2 confirmation is
  re-classified as matching artifact, and W1/W2b surface copy inherits that correction as a
  MANDATORY follow-up.
- **Collapse is a result:** if the ore body goes NOT-SUPPORTED under AM, the registered conclusion
  is "the F1/F3/B3 separations are matching geometry, not anatomy" — that sentence (or its
  survival converse) is the report's headline, whichever way the data falls.
- **Exploratory:** the full 36-feature table runs under both constructions on all panels,
  two-sided BH within family, capped at EXPLORATORY-DISCOVERY. Read from the FULL per-feature
  tables — never from `separating` survivor lists (W2 lesson, memory
  `sign-gated-survivor-lists-hide-wrong-sign-replications`).

## §4 Panels and scope

Three panels, all frozen-tape, all previously constructed (no new cohort definitions):

1. **PRIMARY** — phase-0 run-3 track-W panel (2,154 episodes / 47 peak-months): the cohort the ore
   body was discovered on.
2. **R63 DISJOINT** — W2's `r63≥+0.35` disjoint panel (323 episodes / 39 peak-months).
3. **ATRZ DISJOINT** — W2's `(c−MA200)/ATR63≥6` disjoint panel (1,409 episodes / 47 peak-months).

Scope language (frozen): phase-1 decides **artifact vs anatomy on the same 2022H2–2026 tape**. It
does not test out-of-time transfer, and no phase-1 result upgrades any surface's authority — a
P1-ROBUST leg is still display-tier anatomy until a separate promotion prereg takes it through the
gauntlet.

## §5 Era stratification (MANDATORY), floors, sensitivities

- **Era blocks:** each panel's peak-months are split into **three contiguous calendar blocks with
  as-equal-as-possible peak-month counts**; edges are computed per panel and PRINTED in the
  summary. Every registered cell reports per-era point estimates + CIs alongside the pooled cell.
  **Grade modifier (declared):** a P1-SUPPORTED cell whose latest-era block point estimate is
  wrong-signed is graded `P1-SUPPORTED-ERA-CAVEAT`. Additionally print the phase-0 fence check on
  every B2 cell: does the magnitude fade era over era?
- **Floors (per cell):** ≥12 distinct peak-months (inherited); **≥100 matched topped episodes**
  (NEW — AM's fresh-high restriction shrinks control pools; a cell below either floor is
  P1-UNDERPOWERED, printed, no directional claim). **Match-rate printed** per cell (fraction of
  topped episodes retaining ≥1 valid control after restriction); <50% adds a MATCH-STARVED caveat
  to the cell regardless of grade.
- **Sensitivities (printed, non-binding):** AM fresh-high tolerance `days_since_63d_high ≤ 2`
  (primary is `== 0`); NN cap 8 (primary is the frozen ≤4); DM with day-weighted (W2-style)
  candidate sampling, printed for continuity so the sampling-switch's own contribution is visible.
- **Era features:** E3/E4 stratification machinery (the harness's existing era / dvol-tercile sign
  stability) runs on every registered leg — the W2 omission is not repeated.

## §6 Wall, deferral, and the report contract

- **Wall:** 12 h total compute across all six (panel × construction) runs. If exceeded, emit what
  concluded with a deferral note naming the unrun cells (the W2 deferral convention); a partial
  wave presents partial cells as partial — never silently.
- **Determinism:** each summary re-runnable to float precision from the frozen inputs; the G0.5
  reviewer independently re-derives a declared subset (at minimum: all 18 registered cells) before
  the report is PRESENTABLE.
- **Report:** `reports/top-anatomy-phase1.md`, drafted only after all six runs conclude, red-teamed
  under G0.5 (adversarial pass on the CONCLUSION per the adjudication coverage gate — including the
  motivating-exemplar/current-regime read-through), corrections applied with append-only trails
  here (§7) and in masterplan §11. All 18 cells + diagnostics + era blocks printed at equal
  prominence; failures never demoted to footnotes.
- **Artifacts:** `data/research/top_anatomy_p1_<panel>_<construction>_summary.json` (or a single
  combined summary with per-cell blocks — builder's choice, declared in the first plumbing commit),
  committed with the report.

## §7 Append-only execution log

- **2026-08-11 — FROZEN.** This prereg committed on `claude/topa-phase1-anchor-matched` before any
  phase-1 number exists; harness carries no `--p1-*` path yet (plumbing lands in the next commits,
  still pre-results). Anchors transcribed from `reports/top-anatomy-w2.md` §3–§4 (B2 +3.87
  [+2.56,+5.25] / +3.92 [+2.80,+4.79]; F1 −2.2/−17.0; F3 −2.25/−2.75; B3 +2.23/+4.67 on the two
  disjoint panels) and phase-0 run-3 (F1 −9.7, F3 −2.25, B3 +1.42, B2 +1.29). Sibling chip
  (NaN-safe summary emitters) in flight in a separate session; absorption procedure declared in §2.
- **2026-08-11 — RESULTS READ + ADJUDICATION** (append-only; frozen sections untouched). Execution:
  6/6 cells inside the wall (938 s total vs 12 h), plumbing `54d04f8cce6` + tests `07751721e75`
  precede every result commit (order preserved through the builder's mid-wave rebase), determinism
  re-run on two cells to float precision, suite 134 → 164 under TZ=UTC. **Builder deviations
  accepted and logged:** (a) executed in the commissioning session's checkout — the branch was
  already checked out there, so a second worktree was impossible (procedural, no scientific
  content); (b) `--data-root` pointed at the primary checkout's store mirror, read-only, because
  this worktree's `data/` is empty; (c) the DM stratum is a harness-level matcher
  (`p1_matched_controls`) rather than per-stratum calls into `ta.matched_controls`, because
  per-stratum calls would RE-CUT the frozen bin edges — an unregistered second moved variable; a
  test pins it byte-equal to the frozen matcher when run without a stratum; (d) feature panels are
  shared across constructions within a panel (a construction selects controls; it never enters a
  feature value; identity = EXT variant).
- **2026-08-11 — DISCOVERY + GOVERNING RULING.** §1's AM prose presumed case measurement at the
  peak day; the FROZEN §2 pipeline measures cases at the {21,10,5} days-to-peak snapshots, where
  case `days_since_63d_high` sits at median 1–2. Controls pinned at `F3 == 0` therefore sit CLOSER
  to fresh highs than the cases — the anchor asymmetry REVERSED, not neutralized. Signed AM
  diagnostics: +2.000 / +1.000 / +2.000 (primary / r63 / atrz) against anchors −2.25 / −2.25 /
  −2.75 — non-collapse. Per §1's pre-declared clause the AM construction FAILED, and ALL NINE AM
  cells are adjudicated **UNDERPOWERED-BY-CONSTRUCTION-FAILURE** (the summary JSONs retain the
  mechanically-computed NOT-SUPPORTED grades, which predate this ruling; the report's table is the
  adjudicated record). The builder-emitted magnitude-only `collapsed_by_magnitude=True` is ruled
  NON-GOVERNING — it is blind to the sign flip; the signed diagnostic governs. The AM tolerance
  gradient is admitted as DIAGNOSTIC-LAYER mechanism evidence only (primary residual gap
  +2.00→+1.75 moved B3 −7.41→−3.89 and B2 −7.38→−4.61; atrz +2.00→+1.00 moved B3 −4.49→−2.01 and
  B2 −3.78→−1.91): roughly two sessions of anchor proximity move the heat features by MORE than
  every registered effect size, so the peak-anchor counter-explanation is LIVE AND LARGE — not
  merely undischarged. **AM-v2 chartered** (successor construction, NOT run here, requires its own
  prereg): controls matched to the case F3 DISTRIBUTION rather than pinned at zero, with the
  snapshot geometry stated correctly.
- **2026-08-11 — DM VERDICTS (stand as computed) + SYNTHESIS.** B2: P1-SUPPORTED on primary
  (+0.952 [+0.110,+1.869] q=0.0248) and atrz_disjoint (+2.885 [+1.981,+3.542] q=0.0005);
  UNDERPOWERED on r63_disjoint (n=90 vs the 100 floor; +4.947 [+3.143,+6.755] declared-sign
  q=0.0005; the day-weighted sensitivity at n=399 is concordant — the floor, not the data,
  withholds the grade). F3: P1-SUPPORTED primary (−1.667) + atrz (−1.500), UNDERPOWERED r63
  (−2.125), each carrying the pre-declared anchor-artifact caveat. B3: P1-NOT-SUPPORTED on primary
  (+0.429, q=0.284 — on the discovery cohort the duration confound explains B3), P1-SUPPORTED on
  atrz (+3.268), UNDERPOWERED r63 (+4.885). Registered B2 anchor comparison: DM points sit INSIDE
  W2's duration-unmatched CIs on BOTH disjoint panels (0.94× / 0.74× of W2's points) → the
  declared "duration/length-bias artifacts do not explain W2's confirmation" branch. Era: ZERO
  latest-era wrong-sign flags; B2 era-fade fence `fades=False` on all six cells. Leg synthesis
  under the frozen rule: **NO leg reaches P1-ROBUST** (AM void; r63_disjoint underpowered under
  DM). Headline, in the freeze's own terms: the duration/length-bias half of the artifact story is
  DISCHARGED for B2/F3 (and for B3 on the wide tier only); the anchor-geometry half is
  affirmatively measured as sufficient-magnitude and passes, decidable, to AM-v2.
