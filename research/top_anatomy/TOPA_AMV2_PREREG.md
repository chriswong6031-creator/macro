# TOPA AM-v2 Preregistration — Anchor-Distribution-Matched Controls (`top_anatomy_p1`, instrument v2)

Program: Top Anatomy (`research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md`; docket L1, display tier,
AVOID-not-SHORT permanently — `DNR:KILL-DIRECTIONAL-SHORTING`). This document is FROZEN before any
AM-v2 number exists; its §7 log is append-only (corrections are new entries, never edits).

Charter: `reports/top-anatomy-phase1.md` §7.1 — AM-v2 is MANDATORY before any ore-body conclusion
hardens in either direction. Phase-1's AM-v1 instrument REVERSED the asymmetry it was built to
remove (controls pinned at `days_since_63d_high == 0` while the frozen {21,10,5} snapshots put
case anchors at median 2.0/1.0/2.0, mean 6.99/3.92/5.64), a magnitude-only boolean blessed the
reversal, and nine cells were voided only by adjudicator override. AM-v2 exists to replace that
discretion with an instrument: controls matched to the case anchor DISTRIBUTION, control
episode-age asymmetry stratified, snapshot geometry stated correctly, and a SIGNED validity rule
that GOVERNS with a pre-registered escalation — so no override can be needed, whichever way it
falls.

## §0 The question

Is the wrong-sign ore body (topped episodes at their measured snapshots look *younger, fresher-high,
faster-heating* than matched surviving extension episodes) **anatomy**, or **anchor geometry** —
the mechanical consequence of measuring cases near their own 63d highs? Phase-1's DM arm already
discharged duration/length-bias for B2 and F3 where floors clear and located B3-primary's kill in
the sampling half. AM-v2 closes the remaining measured counter-explanation: anchor proximity.

## §1 The moved variable: anchor caliper on the frozen pairing granularity

The frozen matcher pairs **per case snapshot** (`case_id = episode_id@days_to_peak`,
`scripts/research_top_anatomy_phase0.py`; each of a case episode's {21,10,5} snapshot days is
matched independently, then deltas collapse episode-first). AM-v2 states its requirement at that
measurement level — the level AM-v1's prose got wrong:

**AM2 (primary construction).** Identical to phase-1 DM — frozen W4 key + episode-age tercile
stratum (same stratum construction, same edges recipe: cut within this construction's pooled
candidate set and printed), episode-first control draw (ONE seeded day per continued control
episode, drawn uniformly from ALL its continued-EXT days) — **plus ONE moved variable**: at NN
time, each case snapshot's control pool is additionally restricted by a hard anchor caliper
`|control days_since_63d_high − case days_since_63d_high| ≤ 2` sessions, both sides measured at
the days entering the feature delta. NN ordering itself is frozen (lexsort on |Δr126|, |Δrv63|;
≤4 NN). Nothing else moves: same episodes, races, features, snapshot collapse, bootstrap, floors.

**AM2-AGEFREE (secondary construction).** AM2 minus the age stratum: frozen W4 key + the same
per-case-snapshot anchor caliper, episode-first draw. Exists solely to give `F1_episode_age` its
only possible anchor-clean read (any age stratum absorbs F1; AM-v1's fresh-high restriction
manufactured young controls). **Bias direction documented pre-results:** low anchor values
correlate with young episode moments, and case anchors concentrate at 0–2, so AGEFREE control
ages will skew young; that pushes the F1 delta (case − control) toward zero/positive — AGAINST
the registered negative direction. AGEFREE F1 therefore has **one-directional power: SUPPORTED is
meaningful (survived despite adverse bias); non-support is UNINFORMATIVE-BY-DESIGN, never a kill.**
The case-vs-control age receipt (medians/quartiles) prints beside the cell.

**Signed validity rule (GOVERNS; per construction × panel).** The anchor diagnostic is the
episode-first-collapsed `F3_days_since_63d_high` gap (case − matched control), with the same
block-bootstrap CI as every registered cell. The construction is VALID on a panel iff:
(a) |point| ≤ 1.0 session; (b) the 95% CI lies within (−2.0, +2.0); and (c) **no reversal** — the
point is not positive with a CI excluding zero (positive = controls fresher than cases = AM-v1's
failure; a small negative residual is the original asymmetry shrunk, acceptable within (a)/(b)).
**Pre-registered escalation, not discretion:** if the ≤2-caliper arm fails validity on a panel,
the ≤1-caliper arm (always computed) GOVERNS that panel — its cells become the registered cells
there, under the same rule. If BOTH fail on a panel, the construction FAILED there: every
registered cell on that panel is graded normally AND carries
`UNDERPOWERED-BY-CONSTRUCTION-FAILURE` beside the grade (phase-1 carry law — carried beside,
never instead of), and no directional conclusion is drawn from it. There is no magnitude-only
boolean and no override path in this design.

## §2 Frozen from phase-0/W2/phase-1 (no re-derivation permitted)

- **Tape:** `data/massive_stock_day`, 2021-07-06 → 2026-07-02 (1,254 sessions), same frozen
  vintage, threaded through the #5319 guard with `--allow-stale` (declared: vintage is
  prereg-frozen; staleness disclosed, not hidden). Universe filter + NASDAQ test-symbol
  disclosure carry forward. **No AM-v2 claim is about today's market.**
- **Track:** W only. **Pipeline:** phase-0 §4.2 episodes / §4.3 races / 36 PIT features /
  {21,10,5} snapshot collapse, episode-first median, episode-peak-month block bootstrap
  **B = 2000**. Bin edges recomputed within each panel's own candidate pool (population-relative,
  as in W2/phase-1). **Seed: 20260812** (fresh — AM-v2's draws are new; declared before results).
- **Instrument:** `engine/top_anatomy.py` byte-frozen at main (`git diff origin/main -- engine/`
  empty at every AM-v2 commit). `scripts/research_top_anatomy_phase0.py` gains plumbing ONLY —
  `--p1-construction {am2,am2_agefree}` extending the existing flag, the caliper filter inside
  the harness-level matcher (`p1_matched_controls` extension; per-stratum engine calls would
  re-cut frozen bin edges and are still forbidden), cache identity stamps extended with the new
  construction keys + caliper value (present-and-equal hard-check), and summary emission —
  committed BEFORE any full-panel result. Feature panels rebuild per (arm × construction) as
  identity requires; repair+segmentation cache shared. If the NaN-safe-emitter chip (sibling
  session) merges mid-wave: absorb by rebase, re-run the determinism check (W2/#5319 procedure).
- **Store access:** read-only mirror from the primary checkout (phase-1 deviation, now declared
  up front).

## §3 Confirmatory hypotheses (declared BEFORE any AM-v2 number exists)

Registered ONLY where a construction can read the leg. Anchors quoted from
`reports/top-anatomy-w2.md` §3–§4, phase-0 run-3, and phase-1 §4 (DM):

| Leg | Direction | Registered in | Anchors (ph0 / R63 DISJ / ATRZ DISJ) |
|---|---|---|---|
| `B3_rsi14_chg10` | + | **AM2** | +1.42 / +2.23 [+0.85,+4.73] / +4.67 [+2.80,+6.71]; DM: +0.429 ns / UNDERPOWERED / +3.268 |
| `B2_rsi14` | + | **AM2** | +1.29 / +3.87 [+2.56,+5.25] / +3.92 [+2.80,+4.79]; DM: +0.952 / UNDERPOWERED / +2.885 |
| `F1_episode_age` | − | **AM2-AGEFREE** (one-directional power, §1) | −9.7 / −2.2 [−3.5,−1.0] / −17.0 [−21.8,−12.3] |

- **Cells:** AM2 {B3, B2} × 3 panels = 6, plus AGEFREE {F1} × 3 panels = 3 → **9 registered
  cells**, all printed with delta + CI + q regardless of outcome. `F3` is the matching variable in
  both constructions → validity diagnostic (§1), never graded. `F1` under AM2 is the
  stratification diagnostic (printed, ungraded — DM convention).
- **Multiplicity:** BH-FDR **q ≤ 0.10 within each (panel × construction) family — of exactly 2
  (AM2) and exactly 1 (AGEFREE)** — one-sided p in the declared direction off the same bootstrap
  draws.
- **Grades:** `P1-SUPPORTED` / `P1-NOT-SUPPORTED` / `P1-UNDERPOWERED` exactly as phase-1 §3,
  plus the §1 construction-failure carry and the AGEFREE one-directional-power reading.
- **Ore-body decision (pre-written, whichever way it falls):** B3 is the ore body's jointly
  readable member (F3 dissolves into the instrument; F1 rides AGEFREE). On each panel where AM2
  is VALID and floors clear: B3 `P1-SUPPORTED` → *"B3 survives anchor-distribution matching;
  with DM's duration discharge, both measured counter-explanations are discharged on this
  panel"*. B3 `P1-NOT-SUPPORTED` → *"B3's separation is anchor geometry, not anatomy"* — and if
  that holds on the floor-clearing disjoint panels, **the ore-body anatomy claim is CLOSED on
  this tape as a cluster claim** (the phase-1 §3 registered kill, now instrument-decided). The
  disjoint panels decide; phase-0 primary is supporting evidence, never the decider.
- **B2 anchor comparison (registered reading):** per disjoint panel, state whether AM2 B2 falls
  inside W2's CI ([+2.56,+5.25] R63 / [+2.80,+4.79] ATRZ). Inside → anchor artifacts do not
  explain W2's confirmation. Below-but-supported → partial artifact share as point ratio (same
  matched design; cross-design ratios banned). `P1-NOT-SUPPORTED` on a floor-clearing disjoint
  panel → W2's B2 confirmation is re-classified as matching artifact and **the phase-1 §7.2
  surface-copy correction obligation REVIVES and is executed in THIS wave** (W2b tier copy +
  W1 wherever it leans on B2).
- **Exploratory:** full 36-feature two-sided tables, both constructions, all panels, BH within
  family, capped EXPLORATORY-DISCOVERY, read from FULL tables only (never `separating` survivor
  lists). **Pre-named reads (still exploratory-capped):** do `E3f_rs_peak_lag` and
  `F2_drawdown_in_episode` — phase-1's 3/3 wrong-sign anchor-family replications inside the
  clean DM arm — vanish under anchor matching (→ anchor-geometry shadows) or persist
  (→ anchor-independent structure)?

## §4 Panels and scope

The three frozen panels: **PRIMARY** (phase-0 run-3 track-W), **R63 DISJOINT** (`r63 ≥ +0.35`),
**ATRZ DISJOINT** (`(c−MA200)/ATR63 ≥ 6`). Scope language frozen from phase-1 §4: AM-v2 decides
**artifact vs anatomy on the same 2022H2–2026 tape**; no out-of-time claim; no surface-authority
upgrade — a surviving leg is display-tier anatomy until a separate promotion prereg passes the
gauntlet.

## §5 Era stratification (MANDATORY), floors, sensitivities

- **Era blocks:** phase-1 §5 recipe verbatim — three contiguous calendar blocks of
  as-equal-as-possible peak-month counts per panel, edges printed; per-era point + CI beside
  every registered cell; `P1-SUPPORTED-ERA-CAVEAT` if the latest-era block is wrong-signed; B2
  fade fence printed on every B2 cell.
- **Floors (per cell):** ≥12 distinct peak-months; ≥100 matched topped episodes; match rate
  printed, <50% adds MATCH-STARVED. The caliper shrinks pools by construction — floors do the
  honest work; a floor miss is `P1-UNDERPOWERED`, never a redesign.
- **Sensitivities (printed, non-binding):** caliper ≤4 (loosen direction; ≤1 is NOT a
  sensitivity — it is the §1 registered escalation); NN cap 8; **AM2 day-weighted candidate
  sampling** — declared purpose: phase-1 located B3-primary's death in the sampling half
  (day-weighted restored +1.371 under DM); if day-weighted AM2 restores B3-primary while
  episode-first AM2 does not, that location replicates under anchor matching. Non-binding: it
  informs mechanism language only, never a grade.
- **Era features:** E3/E4 sign-stability machinery runs on every registered leg.

## §6 Wall, budget, and the report contract

Research wall 12 h off the render path (phase-1 measured 938 s for six runs; AM-v2 runs six:
2 constructions × 3 panels, sensitivities inside each run's wall). Artifacts:
`data/research/top_anatomy_p1_{panel}_{am2,am2_agefree}_summary.json`. Report:
`reports/top-anatomy-amv2.md`, which must LEAD with the §1 validity diagnostics (against AM-v1's
reversal receipts) before any registered number; then labeled-unit censuses (phase-1 §2
three-n discipline), registered tables with grades + carries, era receipts, honest episode-level
N, exploratory full-table reads, and adjudication with the §3 pre-written branches. G0.5
adversarial review (opus reviewer) is MANDATORY before presenting; the coverage gate applies
(lead with what the verdict means for the motivating exemplars and the current regime; name who
is missing from panels; the wave's make-or-break — the validity rule itself — gets red-teamed
first).

## §7 Append-only execution log

- 2026-08-12 — Prereg written and FROZEN before any AM-v2 result exists; committed with
  commit-order proof (this commit precedes all plumbing/results commits on the branch). Seed
  20260812, caliper ≤2 with registered ≤1 escalation, 9 registered cells, signed governing
  validity rule declared. Operator direction to proceed: "okay go" (2026-08-11, after phase-1 +
  W2b shipped).
