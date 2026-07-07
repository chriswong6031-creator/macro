# Entry-Stack Expansion — Amendment 3: HTF Oscillator Motion + Non-Momentum Technicals (by Fable)

**Status:** RATIFIED 2026-07-06. Amends `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
(#1356) and rides on Amendments 1–2 (RUL-13..26).
**Provoked by:** operator directive 2026-07-06 — expand the entry stack with (a) additional
momentum-category factors (2W/1M StochRSI "HTF washout" variants, other MACD/RSI/StochRSI tweaks
or confluence pairings) and (b) additional non-momentum technicals and their confluences; first
principles, then test.
**Provenance:** 8-agent verified census (wf_eb240cc2: 6 sonnet lanes + 2 opus fact-checkers; both
corrections integrated) → Fable first-principles candidate book
(`research/entry_stack/A3_CANDIDATE_BOOK_DRAFT.md`, the brainstorm record) → 4 opus idea lenses +
4 opus red-team lenses (wf_817d5705). All four red-team verdicts: **SHIP-WITH-FIXES**; every
blocker and major is integrated below and marked ⟦RT⟧.
**New rulings:** RUL-27 through RUL-34. Prior rulings unchanged.

---

## A. What the census + red-team established (deltas beyond the A1/A2 record)

1. **The user's literal seed is a killed prior; its motion form is the live cell.** Multi-TF
   stoch washout DEPTH behind a fire = H1 FAIL (+3.5pp stop tax; `w2_deep ≈ 0 alone`); the
   state-level evidence (weekly TURN +19pp held21; deep×REVERSING +26pp; 4-TF turn count monotone;
   monthly only +4pp) points at **HTF motion, fire-conditional** — never adjudicated on the ESX
   tape. Sector-level standalone washout→turn triggers are NULL (Oracle P8 P-W1/S-W3 — different
   universe, return-alpha ruler); F7 weekly-turn is a WAVE6 near-miss on the blocked population
   that collapsed inside ¬bear_ctx; W8-A W-ARM failed OOS on the stale population; W8-B SHAKEN
   (weekly hist net-rising ingredient) SHIPPED. Full lattice in the candidate-book record.
2. **The gate already reads weekly STATE.** `confirm3 = (weekly RSI-MACD bullish) OR (3D stoch
   recently oversold)` (engine/confluence_tiers.py:195) — so weekly-state strata partially re-read
   the gate's own admission structure ⟦RT blocker → RUL-29⟧.
3. **Tape constants:** `not_topped` and `eligible` are ALL-TRUE on both frozen tapes — banned as
   strata ⟦RT⟧ (RUL-34). Live tape-native axes: tier × sub × ticks only.
4. **Promotion machinery is partially code-blocked:** true NC-2 eq_band (cand_price/dcl_price
   pivot) has no offline cache and `r1_estimate(entry_quality_bands=True)` raises without it; the
   63-bar close-min PROXY band-FE (the arm that nullified S-UR) is the only operative
   de-confounder ⟦RT blocker → RUL-28⟧. COILED-FIRE recall recompute remains deferred.
5. **S6 "Failed-Fire Fuel" is further along than any A3 doc assumed:** registered species,
   phase-0 PASSED OOS on baskets in both variants (failed2×COILED clean8_21 +4.29pp q=0.032
   m2d_s3d / +3.79pp q=0.080 base3d; below the ≥5pp floor → display-chip rung), status phase0 per
   monthly-review law. Serial-failure / nth-fire constructs are **S6's property** ⟦RT blocker⟧.
6. **Stale hygiene claims corrected ⟦RT⟧:** `mae21` IS live in EFFECT_OUTCOMES + BH panel
   (entry_strata_phase0.py:381/1074/1138) — Amendment 2 §C.1's "missing co-primary" is landed.
   Still real: (a) A2 families' declared_budget rows never materialized in trial_ledger.jsonl
   (`_register_all_families` not re-run); (b) W2 SUR/SLQ runners logged 0 trials.
7. **Monthly RSI-MACD is numerically unconverged on baskets:** EMA span-60 on ~150 monthly bars
   (2014+) leaves only ~30 usable bars — the monthly RSI-MACD rung is deep-panel-only; the
   baskets-legal monthly primitive is monthly StochRSI (converges in ~20 bars) ⟦RT blocker⟧.

---

## B. Rulings

### RUL-27 — Identity, scope, and marginals-first law

A3 rides inside Entry-Stack Expansion: `esx_*` families, frozen fire tape
(`gate_fires_{deep,baskets}.parquet`), RUL-9 grader, RUL-13 21d primaries (stop5 + mae21 +
zone_held_21/stop_vol_21 co-primaries), R1 date-FE estimator at frozen granularities, era tables,
survivor stamps, recall printed, reports under `research/entry_stack/`. US panels only
(deep + baskets); delisted-panel arms are struck ⟦RT⟧ — the delisted closes store is absent
offline and no A3 claim may cite it. **Marginals-first:** A3 registers exactly three interaction
families (C, D and the dose ladder B — the operator's confluence ask in its testable form);
all further non-momentum × momentum confluence pairings are deferred to a follow-up amendment
gated on A3 marginal survivors — interactions of nulls are not purchased.

### RUL-28 — Verdict-ceiling law (A3 families) ⟦RT blocker⟧

The 63-bar close-min NC-2-PROXY band-FE arm is **mandatory in every A3 primary read as a
KILL-ARM**: an effect that dies under proxy-FE is a proximity shadow — buried. An effect that
survives it is still **not CHIP-promotable**: CHIP promotion is BLOCKED for all A3 families until
the true eq_band (cand_price/dcl_price pivot) lands; the recomputed COILED-FIRE recall clause is
likewise deferred. A3 verdict vocabulary is capped at **DISPLAY-CANDIDATE / NULL / KILLED**.
DISPLAY-CANDIDATE = passed every decidable clause (CI-excluding-0 pooled, BH within family,
sign-stable ≥3/4 eras, survives the RUL-30 battery, ticker-half sign agreement on baskets) — it
may ship display/shadow surfaces only, and its CHIP case re-opens when eq_band lands.

### RUL-29 — Admission-leg law ⟦RT blocker⟧

For any family whose feature is computed on the weekly RSI-MACD series (A1; C's A1-interaction
form): the pooled read must include the gate admission-leg (`wbull` vs `fromos3`) as an FE
covariate, and the **operative verdict coefficient is the one measured within the ¬wbull
(fromos3-admitted) subset** — on the wbull-admitted subset a weekly flag re-reads the gate's own
confirm leg. The admission-leg decomposition table is mandatory in every A3 report that touches a
weekly feature.

### RUL-30 — De-confound battery (kill-only diagnostics)

Frozen battery; each element can only kill or downgrade, never upgrade ⟦RT: no silent FDR
inflation — BH runs over the declared family configs; diagnostics are pre-registered kill-arms⟧:

| Control | Applies to | Frozen definition |
|---|---|---|
| NC-2-proxy band-FE | ALL families | 63-bar close-min proximity proxy terciles as FE (shared harness helper, RUL-32) |
| Realized-vol-LEVEL tercile FE | vol/ATR-adjacent families (C, E, G) | `stock_technicals.realized_vol(close,63)` trailing cross-sectional terciles — the explicit H2 de-confound |
| ¬bear_ctx decomposition | bear-regime-correlated families (C, E, F, G) | WAVE6 F8 frozen def verbatim: index close below its 200MA on ≥70% of trailing 126d, as-of fire (wave6.py:132-134, 920-925) — the fixed-barrier artifact control |
| Pure-age covariate | F | bars since trailing 63d close-low as FE covariate — proves F is not H2 re-derived |
| Marginality-vs-A | B, C, D | A-flag main effects in the FE; interaction/dose coefficient is the only verdict read |
| Admission-leg | A1, C(A1-form) | RUL-29 |

### RUL-31 — HTF PIT + faithful-math law ⟦RT blocker integrated⟧

1. Every HTF feature uses the **last COMPLETED HTF bar whose known-date ≤ fire date** (the
   in-progress bar is excluded). Weekly = W-FRI resample with known-date mapping (reuse
   `engine/oracle/oscillators.resample_weekly_leakfree` / the `confluence_tiers._tf_bars`
   pattern). 2W and the H1 washout feature replicate the wave1.py H1 convention **verbatim**
   (builder pins the resolved convention in code with a known-answer fixture and logs it in the
   PR body; re-parameterization is banned). Monthly = month-end resample, known-date = last
   trading day of the month.
2. Math pinned: RSI-MACD = `confluence_tiers._rsi_macd` (EMA(RSI14,14)−EMA(RSI14,60), sig EMA5);
   StochRSI = `confluence_tiers._stoch_rsi_kd` (14/3/3, K&D, 0-100). **Never** `cycles.stoch_rsi`
   (K-only) and never price `macd_parts` — three co-existing implementations exist; conflation is
   a build error.
3. Monthly RSI-MACD runs **deep-panel-only** (EMA-60 convergence; §A.7). The registered monthly
   rung (A3m) is monthly **StochRSI** turn on both panels; deep-only monthly hist-rising is a
   named kill-only diagnostic.
4. Every per-fire feature is materialized by an explicit `compute_*_at_fires` step producing a
   fire-indexed Series before the `grade_fires(extra_columns=...)` join ⟦RT⟧; leak-audit section
   (shift audit + truncation-invariance fixture per primitive) is mandatory in the build PR.

### RUL-32 — Trial budgets, registration mechanics, hygiene ⟦RT integrated⟧

New families (program ceiling **165 → 201**):

| Family | Budget | Itemization (frozen at this ratification) |
|---|---|---|
| `esx_htf_turn` (A) | 12 | 3 rungs (A1 weekly hist-rising; A2 2W stoch turn = K>D ∧ K rising; A3m monthly stoch turn) × 2 panels × 2 reads (pooled-FE, ¬wbull-subset) |
| `esx_htf_turn_dose` (B) | 2 | ordinal n_turn_legs {0..3} × 2 panels; verdict read LOCKED until ≥1 A rung shows CI-excluding-0 (operative read); legs pre-declared collinear, weekly-dominant expectation |
| `esx_washout_x_turn` (C) | 8 | 2 interaction forms (H1-frozen 2W-D-min<25 × {A1, A2}) × 2 panels × 2 contrasts (deep∧turn vs deep∧¬turn; deep∧turn vs rest) |
| `esx_sub_x_turn` (D) | 2 | tape `sub` × A1 interaction coefficient × 2 panels; LOCKED behind A |
| `esx_decline_geometry` (E) | 4 | Herfindahl of \|negative daily log-returns\| over trailing 63 bars (min 8 down-days else NaN), fixed trailing cross-sectional terciles × 2 panels × 2 contrasts (flush-vs-grind; flush-vs-rest); two-sided |
| `esx_underwater` (F) | 4 | `time_underwater_series(close, 252)` — bars since trailing-252-bar max, SATURATING (bounded ≤ ~251, interim-peak resets possible — described accurately ⟦RT⟧); terciles × 2 panels × 2 contrasts; window=126 as named kill-only diagnostic; two-sided |
| `esx_vol_transition` (G) | 4 | vol_ts = realized_vol(5)/realized_vol(63); vol_falling = (vol_ts<1) ∧ (vol_ts < vol_ts 5 bars prior); × 2 panels × 2 contrasts (falling-vs-rest; falling-vs-elevated); pre-registered EXPECT-NULL |
| **Total new** | **36** | BH q≤0.10 per family; program summary printed per report |

Mechanics: the registration PR must (a) run `_register_all_families()` so the **A2 backfill** and
A3 declared_budget rows both materialize in `data/trial_ledger.jsonl` (budget field is `n` on
declared rows); (b) extract `compute_nc2_proximity_proxy` from run_w1_nc.py into the shared
harness so every A3 runner calls one audited implementation; (c) every A3 runner logs each trial
config via `led.log_trial()` (the W2 SUR/SLQ zero-logging gap may not recur).

### RUL-33 — Rejection record (citable; do not re-walk)

| Candidate | Disposition | Reason |
|---|---|---|
| esx_serial_fuel / esx_episode_spacing / nth-fire ordinal | **REJECTED — owned** | S6 Failed-Fire Fuel (registered species, phase0-PASSED OOS) owns the serial-failure construct; its pre-registered primary is the failed2×COILED interaction. A3 may not run a parallel family (RUL-11 spirit) |
| esx_second_test (double-bottom hold stratum) | **REJECTED — proximity shadow** | a held-above-prior-low band is a distance-to-low restatement; the NC-2-proxy arm that nullified S-UR's only positive form is the modal outcome; folklore closed by reasoning + S-UR corpse |
| esx_coil_range_at_fire (squeeze-state at fire) | **REJECTED — banned variant** | masterplan §3 F3 pre-registered the S-SQ family with the "arming" (state-without-release) variant BANNED; a state-at-fire family is that variant |
| esx_base_efficiency (Kaufman ER / choppiness absorbed-range) | **REJECTED** | Kaufman ER killed BY NAME in the §5b guard kill; choppiness is CHARTER "folklore/avoid", collinear with ER; the absorbed-vs-trending claim rides partially in E |
| esx_degree_alignment (weekly/monthly price higher-low structure) | **DEFERRED to A4** | genuinely untested cross-scale structure, but position-family confound profile; buy only if A survives (motion-before-structure sequencing) |
| esx_sub_x_ticks | **REJECTED — unpowered** | deep×ticks≥1 cell ≈ 740 fires on deep; NC-1 already ruled the ticks main effect |
| esx_div_fire (standalone divergence) | REJECTED at census | anti-validated: "div WITHOUT cohort is actively BAD" (DURABLE_BOTTOM:343) |
| New oscillator species (TSI/W%R/CCI/MFI/UO/Connors/DeMark/Ichimoku/Coppock/Aroon/SAR/Supertrend); price-MACD HTF variants | **DECLINED** | BOTTOM_CONFIDENCE Result 4 + KST collinearity ruling + faithful-math law; price-MACD variant declined on budget + faithful-math grounds (collinearity at cycle scale asserted-not-shown ⟦RT⟧ — recorded as untested, not falsified) |
| not_topped / eligible strata; tick-age × HTF interactions | **REJECTED — constants/unpowered** | RUL-34; §A.3 |

### RUL-34 — Tape-native axes

`not_topped` and `eligible` are constants on the frozen tapes; any family stratifying on them is
rejected at registration (a re-dump is out of A3 scope). The live tape-native axes are
tier × sub × ticks and date/ticker-derived columns only.

---

## C. Family cards (mechanism + expectation + kill line; definitions frozen in RUL-31/32)

**A — esx_htf_turn (flagship).** The gate's 2D/3D cross proves the daily-swing degree turned;
whether the cycle degree's oscillator has begun MOVING up (weekly/2W hist slope, monthly stoch
turn) is seller-exhaustion evidence at the scale that separates durable bottoms from trap
bounces — the H1 kill's own pointer, the SHAKEN chip's live ingredient, F7's near-miss, all
never adjudicated on eligible gate fires under the frozen grader. Adjacency: H1 (position, not
motion), F7 ¬bear_ctx collapse (we carry date-FE + proximity-FE + bear_ctx controls F7 lacked),
P8 sector nulls (different universe/ruler/role), W8-A OOS failure (approach-extrapolation on
stale crosses ≠ realized slope on fresh fires), H5 monthly-falling veto FAIL (opposite
direction/lane), trend/location guards + CT-LANE (price constructs; we run strata never filters).
Expectation: weekly rung strongest (state prior +19pp); 2W expect-weak (turn "catastrophically
late" case anatomy); monthly expect-weak (+4pp state prior). Kill line: RUL-28 decidable clauses;
nulls printed per rung.

**B — esx_htf_turn_dose.** Fire-conditional adjudication of the turn-count claim that already
ships display-only inside `bottom_confidence` tf_score (price-MACD basis, weights W=0.45 M=0.15,
never outcome-adjudicated) — cited as the incumbent display composite; A3 ships NO new composite
(RUL-25 honored; ordinal test only, esx_support_dose precedent, with the honest caveat that these
legs are same-source collinear unlike support_dose's).

**C — esx_washout_x_turn.** The operator's literal "2W StochRSI washout" seed in its only live
form: depth counts ONLY when the higher degree is also turning (state-level winner cell, deep ×
reversing +26pp). H1's frozen depth feature verbatim × A-turn flags; no age/calm ingredient (H2
firewall). Pre-registered expectation ⟦RT⟧: the raw interaction is the most proximity-exposed
claim in the book — expect the proxy-FE arm to bite hard; the marginality-vs-A read is the
meaningful one; thin cells likely (print n; n<400 pooled treatment ⇒ descriptive stamp).

**D — esx_sub_x_turn.** The only uncrossed validated-marginal tape interaction worth powering:
does the deep-sub (recent daily violence) stop penalty attenuate when the weekly degree is
turning? Expect-null probe; zero new compute beyond A's columns.

**E — esx_decline_geometry (non-momentum flagship).** Path SHAPE of the decline: flush
(few large down-days dominate the trailing 63-bar loss — forced supply that empties) vs grind
(loss spread evenly — voluntary distribution that persists). Scale-free (Herfindahl of loss
shares), no depth/age/amplitude ingredient — mechanically outside H1/H2/NC-2 constructs, but
proximity- and vol-correlated: full RUL-30 battery. Two-sided (flush-better predicted; grind
tail read honestly).

**F — esx_underwater.** Drawdown-EPISODE duration below the prior 252-bar peak (saturating
primitive, described accurately). Episode-structure vs H2's base-age: proven by the pure-age
covariate, or killed. Two-sided.

**G — esx_vol_transition (expect-null).** Vol term-structure MOTION (short-vol below long-vol
and falling) vs H2's killed vol LEVEL — settles whether any vol-family conditioning survives once
level is controlled. Registered expect-null; non-null = pooled BH-adjusted CI excluding 0 under
the full battery, replicated in sign on baskets (RUL-5 style).

---

## D. Execution plan (PR-sized; routed per CLAUDE.md)

- **PR-1 (this doc):** Amendment-3 + candidate-book record + FAMILY_BUDGETS additions +
  `_register_all_families` materialization (A2 backfill + A3 rows) + shared NC-2-proxy helper
  extraction + registry/lattice notes. Registration precedes every compute (RUL-5).
- **PR-2 (build):** `engine/entry_primitives.py` additions (HTF turn flags builder,
  decline_concentration, vol_ts) with leak fixtures (truncation-invariance per RUL-31.4) +
  `scripts/research/run_a3_htf.py` (families A/B/C/D) + `scripts/research/run_a3_struct.py`
  (families E/F/G), both cloning the run_w1_sts extra_columns pattern, both logging trials.
  Sonnet builds (`builder`), Opus reviews (`reviewer` — leak-safety + RUL-29/30/31 conformance).
- **Run (off-path, no PR):** phase0 studies on the frozen tapes, deep + baskets.
- **PR-3 (reports):** `research/entry_stack/A3_HTF_REPORT.md` + `A3_STRUCT_REPORT.md` in the
  W-report format (NC yardstick first table, effect tables, era × stratum, admission-leg +
  ¬bear_ctx decompositions, survivor stamps, nulls printed); Fable adjudication appended;
  graveyard/lattice updates; memory index update.

**Coordination:** S6/#1097 untouched (serial-fuel is theirs); durable-bottom W9 (cohort re-arm on
stale population) and wave9_rearm.py untouched; #1302 RS/anti-chase untouched; Oracle P9
washout-column build (sector panel) is a different surface; S-SQ release study remains the base
program's registered property. **Non-goals:** no new species; no gates; no new display composite;
no HK/CA; no CN port (CN-WASHOUT is validated CN-side but porting is bidirectionally suspect);
no re-dump of the fire tape; no exit work.

*Filed by Fable, 2026-07-06. Census wf_eb240cc2 (8 agents); ideation + red-team wf_817d5705
(8 opus agents, 4×SHIP-WITH-FIXES). The candidate-book record preserves the full brainstorm and
triage trail.*

---

## F. Adjudication (main-loop ruling, 2026-07-06)

Both phase0 studies ran on the frozen deep + baskets tapes (reports: `A3_HTF_REPORT.md`,
`A3_STRUCT_REPORT.md`). Two opus review lenses (overfit-statistics + deployment-doctrine,
wf_984c2fb8) checked the results before this ruling. All verdicts respect the RUL-28 ceiling
(DISPLAY-CANDIDATE / NULL / KILLED; CHIP promotion blocked until the true eq_band lands). One
grader, RUL-9; 21d primaries, RUL-13.

### F.1 Verdict table

| Family | Verdict | Key evidence |
|---|---|---|
| **E `esx_decline_geometry` (flush)** | **DISPLAY-CANDIDATE** | The cleanest result in the program. Flush-vs-rest stop5 −1.00pp (deep) / −2.34pp (baskets), both CI-excl-0; survives the FULL RUL-30 battery — nc2 proximity FE (−2.06/−3.35pp, *grows*) AND rv63 vol-level FE (−1.14/−2.85pp) — on BOTH panels; era-sign-stable 4/4 both; ticker-half agree both; mae21 co-primary confirms. Mechanically orthogonal to every shipped construct (no depth/age/proximity/cohort ingredient). |
| **F `esx_underwater`** | **ADVERSE-CONTEXT** (real, AVOID sign) | Statistically the strongest effect, but adverse: long-underwater = stop5 +2.35pp (deep) / +6.31pp (baskets) WORSE; all three co-primaries agree; survives the age63 pure-age kill-arm (so NOT H2 re-derived) and survives inside ¬bear_ctx (not a pure bear-regime artifact). A caution axis, never a buy signal — de-escalation-eligible only (LLM-de-escalation house law). |
| **A1 `esx_htf_turn` weekly** | **DISPLAY-CANDIDATE-CAVEATED** (baskets-only) | Operative ¬wbull stop5 −2.57pp, recall 74%, era 4/4, ticker-half agree, mae21 confirms; admission-leg decomposition (RUL-29) convincing — effect lives in the fromos3-admitted subset, not re-reading the gate's confirm3 weekly leg. BUT ~⅔ is proximity: nc2 FE attenuates to a thin −0.83pp residual (≈8% of the −10.1pp baskets proximity yardstick). NULL on deep (mega-caps rarely wash out; era-1 wrong-sign = the low-vol-bull "edge sleeps" pattern). Shadow observation only; no user chip until off-panel replication or eq_band. |
| **A3m `esx_htf_turn` monthly** | **NULL (by non-replication)** — overrides the report's mechanical DISPLAY-CANDIDATE | Wins on deep only (operative −2.40pp, survives nc2 −3.22pp, era 4/4) but was **pre-registered expect-weak** (+4pp monthly state prior vs +19pp weekly) and **fails the larger baskets OOS** (era 1/3, one era 0 fires, operative CI incl 0). Deep-only win on the survivor-biased panel where the monthly bar has 64y to converge, failing the decisive OOS, is the textbook overfit/survivorship signature. The report's grader has no non-replication clause; the adjudication supplies it. Held as a shadow observation; no verdict weight. |
| **A2 `esx_htf_turn` 2W** | **NULL** | Baskets operative −0.73pp is knife-edge (p=0.050) and the mae21 co-primary fails to confirm at the governed horizon (p=0.066); deep NULL. Consistent with the pre-registered "2W turn catastrophically late." |
| **B `esx_htf_turn_dose`** | **NULL / DESCRIPTIVE** | Monotone gradient real (baskets 23.2→20.6→18.5→**18.7**%; the leg-3 reversal is a confound tell) and the ordinal per-unit coef is CI-excl-0, but it is NOT proximity-de-confounded (no nc2 arm on the ordinal) and the legs are same-source collinear. Most parsimoniously the proximity gradient. Falsifier logged (F.3). Also partially re-measures the shipped `bottom_confidence` tf_score construct. |
| **C `esx_washout_x_turn`** | **KILLED** | The operator's literal 2W-washout × turn seed adds NEGATIVE marginal value once proximity is removed: nc2 kills contrast-i (−0.29pp CI incl 0) and the marginality interaction is adverse (+0.014 baskets / +0.024 deep). Re-confirms the H1 depth kill fire-conditionally. |
| **D `esx_sub_x_turn`** | **NULL** | Cross-panel SIGN flip on the interaction (baskets −0.0194 CI-excl-0 vs deep +0.0183 wrong-signed) — disqualifying for an expect-null probe. |
| **G `esx_vol_transition`** | **NULL (expect-null confirmed)** | Vol term-structure MOTION adds nothing once vol LEVEL is controlled: deep era 1/4, ticker-half DISAGREE. Settles the vol-family question. |

### F.2 What the program learned (headline)

1. **A genuinely new, cross-panel-replicated non-momentum dimension exists: decline path-SHAPE.**
   Flush-shaped declines (loss concentrated in few large down-days = forced supply that empties)
   give measurably better fresh-entry stops than grind-shaped declines (loss spread evenly =
   voluntary distribution that persists) — orthogonal to depth, age, proximity, and cohort, and
   the only A3 survivor of the full de-confound battery on both panels. This is E, and it is the
   deployable output of the program.
2. **The operator's literal "2W/1M StochRSI washout" seed is confirmed dead in its position form**
   and dead in its interaction form (C KILLED, A3m NULL-by-non-replication, A2 NULL) — but its
   **motion form survives on the broad tradeable universe** (A1 weekly-turn on baskets), mostly
   as a proximity restatement with a thin genuine turn-marginal. This is the honest resolution of
   the H1 lineage: cycle-scale *position* is dead; cycle-scale *weekly motion* carries a small
   real marginal on small/mid-caps that mega-caps do not show.
3. **The vol-family question is settled** (G): vol term-structure motion adds nothing over vol
   level. **The dose/HTF-confluence intuition** (B) is a proximity gradient, not a mechanism.
4. **RUL-29 (admission-leg) and RUL-30 (kill-arm battery) earned their keep:** the nc2 arm killed
   C and 2/3 of A1; the admission-leg decomposition proved A1 is not re-reading confirm3; the
   non-replication override caught the one place the mechanical grader over-promoted (A3m).

### F.3 Deployment ruling & clocks

- **Ship (separate W3 PR, nightly display-path, ≤+30s render benchmark GATE):** E `decline_geometry`
  as a **display-only** descriptor field (flush / mixed / grind, trailing-63-bar loss-Herfindahl
  tercile) on the `bottom_sensors` envelope + a shadow forward-ledger, mirroring the COILED-FIRE
  "display chip + forward-ledger, no rank/bonus change" ship-shape. EN/ZH descriptive framing, no
  translated `title=`, the word "validated" absent (CI-enforced), `is_display_only=True`. Frame as
  a decline-shape read, NOT an escalation.
- **Shadow-only (no user surface):** F `underwater` as an adverse/caution field feeding the
  de-escalation lane only; A1 weekly-turn (baskets) + A3m monthly-turn (deep) as shadow-ledger
  observations pending off-panel replication.
- **Buried:** C (KILLED); A2, B, D, G (NULL). Recorded in the graveyard so nobody re-walks them.
- **Falsifier logged for B:** re-run the ordinal dose with the nc2_band (+ rv63) FE kill-arm; the
  prediction is collapse to CI-incl-0 (as A1's bulk and every C arm did). If it does not collapse,
  B re-opens.
- **Come-back clocks:** (i) when the true eq_band (cand_price/dcl_price pivot) cache lands, re-run
  E, A1-baskets, A3m-deep through the real NC-2 marginality FE and re-open their CHIP cases
  (RUL-28); (ii) re-grade E's shadow ledger at the monthly review — if its live edge proves
  bear-regime-only (deep ¬bear_ctx was CI-incl-0), cap it to baskets; (iii) A1/A3m re-eval when a
  second era of forward fires accrues on the off-panel. **Interactions/confluences (esx_degree_alignment,
  A4) stay deferred (RUL-27): only E survived as a clean marginal, so only E-based confluences
  would be eligible in a follow-up amendment — interactions of nulls are not purchased.**

*Adjudicated by the main loop (Opus; Fable window exhausted), 2026-07-06. Reviews: 2 opus lenses
(wf_984c2fb8), convergent on E-ships/F-adverse/C-killed; the A3m NULL-by-non-replication override
adopts the overfit lens over the report's mechanical grader per house law.*
