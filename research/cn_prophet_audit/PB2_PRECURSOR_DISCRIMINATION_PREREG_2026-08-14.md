# P-B2 — matched precursor discrimination: PREREGISTRATION (2026-08-14)

Status: **FROZEN BEFORE OUTCOME ACCESS.** This document is committed to git BEFORE the
first outcome run of the P-B2 instrument; the commit order in history is the proof that
every definition, threshold, stratum, gate and disposition rule below preceded the
result. Any deviation discovered during the build is a NUMBERED AMENDMENT in the result
receipt (the P-B §10 practice: what changed, why, what controls it) — never a silent
re-choice. Seeing a result and then changing a matching rule, a stratum, a floor, a
gate or the feature list is the exact failure mode this document exists to prevent.

Pre-freeze review: this design was adversarially red-teamed BEFORE freezing (opus
reviewer, 2026-08-14; 4 blockers + 11 majors found and incorporated — the permutation
design effect, quiet-control right-truncation, unmeasurable-as-FALSE mixing, and
stratum-degeneracy refusals below all come from that round). Design sizing facts cited
below come from the PUBLISHED W-P0 receipt (`WASHOUT_ONSET_W1_2026-08-10.json`) and
P-B receipt — prior published evidence, not P-B2 outcome access.

Authority: `none_research_display_only`. Nothing here ranks, sizes, gates, alerts,
trades, or feeds any production score. There is **NO P-B2 production ranker** — the
flagged-set diagnostics of §10 are descriptive and end inside the receipt.

Governing rulings, in order: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` (the tolerant
detector on the back-adjusted store is pattern-tier substrate, not the exact legal-
limit plane; the reopen chain is untouched by this study), then
`research/CN_LIMIT_ALPHA_RECONCILIATION_LEDGER_2026-08-09.md`, then the program home
`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`. P-B's §9 ore ledger reserves
"THE COMPARISON ARM … an INFERENTIAL study … needs a PREREGISTRATION" — this is that
preregistration. No withdrawn W1–W3 artifact, number or receipt is cited as evidence
anywhere in this study (instrument-scanned, `stop_ship_reference_scan`).

Eval OS: no qledger claim is minted. This is a retrospective display-tier study making
no forward directional claim; `evidence_ref` registration binds above display tier
only. Any future promotion-bearing consumer goes through the gauntlet and registers
its own claims.

---

## §1 The question

**PRIMARY.** Among lawful cold A-share name-date states on the W-P0 panel, which of
the already-frozen P-B footprint families carry information about a **first tolerant
limit-up close within the next H = 10 of the name's own sessions** — beyond session,
board, volatility and (in the M1 arm) the washout carrier itself?

**SECONDARY.** The same at H = 5.

**TWO-SPEED.** At what lead time before a realized first board does each footprint
become more prevalent than in matched quiet controls (§9)?

"First tolerant limit-up close" is W-P0's `fb_H` outcome verbatim: the tolerant
detector (`close >= round(prev_close*(1+w),2)*(1-0.002)`, W-P0 L986) on the name's own
live-session axis, with W-P0's closure-tolerant completeness rule (`win_ok_H`,
MAX_STEP_GAP_DAYS = 21). Never conflated: an intraday touch, a generic big day, and a
continuation board after a prior board are different physical objects and none of them
is the label. The cold rule (no tolerant board in the prior 20 sessions INCLUDING the
anchor, W-P0 L990) guarantees every positive is a genuine 0→1 ignition (W-P0 §5
lemma: every such first board is ladder-0).

**Estimand scope, stated up front (this bounds every verdict below):** all strata are
within-session, so every P-B2 verdict is a **within-session cross-sectional**
statement — does the footprint separate names on the same tape on the same day. A NULL
here says nothing about market-wide or regime-timing information in the same family
(a "boards cluster when the whole tape is washed out" mechanism is removed by the
session stratum by construction). Instrument verdicts are not market verdicts.

What P-B2 adds over what exists: W-P0 Q1 measured **unmatched** state-vs-universe
onset rates; P-B measured winners-only anatomy with **no comparison arm**. P-B2 is
the matched, incremental, split-disciplined discrimination study both reserved.

## §2 Substrate and universes

One store, one panel: `data/china_stocks_raw` through W-P0's own `build_panel()` +
`attach_conditioners(panel, None)` (chips=None — S5b is P-C territory), reached by
import of `research/cn_prophet_audit/washout_onset_w1.py` and reuse of P-B's
`build_footprint_panel` / `derive_footprints` / `extract_events` from
`research/cn_prophet_audit/pb_case_decomposition.py`. **No third implementation of any
definition.** Window: W-P0's own 2011-01-01 → 2026-08-07. Both source files are
pinned by sha256 and by the P-B line-pin table pattern; a pin mismatch refuses the
run.

Inherited limits stamped on every receipt: back-adjusted basis (tolerant-detector
cohort, not exchange-exact legal limits); curated large-cap **survivor** slice (~35%
of SH/SZ, delisted names absent — nothing generalizes to small caps or the delisted);
current-membership sector map applied to 15 years of history.

**Anchor universes** (a row = one (ticker, session) panel bar):

- **U0 (cold at-risk):** `cold` = TRUE, `split` assigned (W-P0's embargoed split
  column; rows outside a split are excluded and counted), `dd250` finite (the `na`
  dd-band — under 200 bars of history — is excluded and counted).
- **U1 (washout at-risk):** U0 ∧ `dd250 <= -0.20`.

Boards are W-P0's four populations (`main`, `chinext10` pre-2020-08-24, `chinext20`
on/after, `star`), **never pooled**; eras are W-P0's `era_of`, never averaged. No
anchor thinning in the primary estimator; the dependence this creates is handled by
§6 (block/cluster inference + thinned sensitivity), with honest-N always in rows AND
episodes AND names AND sessions.

## §3 Labels — frozen outcome columns, censoring never scored

For H ∈ {10 primary, 5 secondary}, read W-P0's own columns:

- **POSITIVE:** `fb_H` = TRUE.
- **NEGATIVE:** `win_ok_H` = TRUE ∧ `fb_H` = FALSE.
- **CENSORED:** `win_ok_H` = FALSE. Censored rows enter NEITHER class, are counted
  per board × split **and per footprint F-class** (differential censoring by footprint
  is the bias this makes visible), and are never scored as misses.

This is an exact partition (`fb_H ⊆ win_ok_H` by construction; §11 check 1). The
count of rows where a board is visible inside a broken window (re-derived next-board
distance ≤ H but `win_ok_H` FALSE) is printed as a censoring diagnostic; if it
exceeds 1% of positives on any board the receipt must discuss it. For every
DISCRIMINATOR verdict the receipt prints the coarse Manski robustness line: the
matched excess recomputed under "all censored F=TRUE rows positive" and "all
negative" bounds, and whether the sign survives.

**Episode identity.** Every positive row's episode key is its realized board
(ticker, date of the first `lu` after T, re-derived on the panel axis and verified
against `fb_H`). Distinct-episode counts are the honest event N everywhere. By
W-P0's ladder-0 lemma every positive row's board is a cold-eve event under P-B's
`extract_events`; the overlap count is printed as a cross-check.

**Design-effect fact (from the published W-P0/P-B receipts):** one episode generates
~10 positive anchor rows at H=10 (measured 10.2 on main FIT: 91,131 U1 positive rows
over ~8,900 episodes). Row-level inference is therefore anticonservative by ~√10 and
is NEVER used for gating — §6 and §8 are built around this fact.

## §4 Feature families — the frozen P-B vocabulary, nothing else

The eight P-B booleans, read at the anchor via P-B's `derive_footprints`, verbatim:
`dd_le_m20` (DD20), `dd_le_m35` (DD35), `under_ma200` (MA200), `confluence_long`
(CONF), `cb_recent` (CB), `sector_deep35_ge40` (SECT), `quiet_base` (QB), `volz_gt1`
(VZ). Plus the four frozen banded gradients as SECONDARY descriptive families (no
verdicts): `below_band`, `dur_band`, `sect35_band`, `volz_band`.

- **No unconstrained feature mining.** No new features, no ninth footprint, no
  learned score, no pair/triple/grid search. P-D owns conjunction stacking; W-P0's
  S6 conjunction masks are NOT re-read here.
- **Measurability masks (frozen — unmeasurable is never FALSE).** P-B's boolean
  derivation codes missing as FALSE; leaving that in the F=FALSE class would
  estimate the counterfactual from a mixture of measured negatives and unmeasurables
  (6.61% of panel rows have UNKNOWN sector alone). A row enters footprint F's
  analysis only if F is measurable on it: SECT — `sector != "UNKNOWN"` ∧
  `sect35_band != "na"`; VZ — `volz_band != "na"`; QB — `isfinite(rv_rank)`;
  MA200 — `isfinite(ma200)`; DD20/DD35/depth/duration — `dd250` finite (already
  U-eligibility); below-gradient — `isfinite(ma200)`; CONF/CB — treated measurable
  on all U rows (their indicator warmup is covered by the 200-bar dd-finiteness
  floor; declared approximation). Exclusion counts printed per footprint × board ×
  split; §11 check `missing_not_false` guards it.
- **Coincident-indicator stamp (frozen):** VZ (median arming lead 1 session) and CB
  (median 5) are near-coincident indicators, not early precursors (P-B §5). Any
  verdict on them carries this stamp; they are never described as "precursors".
- **Evaluability:** DD20 is constant-TRUE in U1 → verdict from M0 on U0 (its
  all-TRUE degeneracy in U1 is exactly §11 check 7's all-TRUE probe). DD35 and the
  depth/duration gradients carry the §5.3 carve-outs. All others evaluable in both
  arms.

## §5 Design — stratified matched comparison, two arms

The estimator is W-P0's own `volatility_matched` direct standardization, extended:
within each stratum compare the positive-rate among F=TRUE rows to the positive-rate
among F=FALSE rows, aggregate over strata weighted by the F=TRUE row count (the
ATT-weighted standardized difference):

- obs(F) = Σ_z k_F1(z) / Σ_z n_F1(z) over strata with n_F1>0 and n_F0>0
- exp(F) = Σ_z n_F1(z)·[k_F0(z)/n_F0(z)] / Σ_z n_F1(z) over the same strata
- **matched excess (pp)** = 100·(obs − exp); **matched lift** = obs/exp (lift is
  suppressed and only the excess printed when exp < 0.5% absolute — ratio
  instability floor; exp is always printed beside any lift).

**§5.1 ARM M0 — base match.** Universe U0. Strata = session × own-vol decile
(W-P0's `rv_rank` deciles + stratum 10 = unmeasurable, exactly `volatility_matched`).
Board is a hard subset, not a stratum. DD depth, duration, MA200, SECT are NOT
matched away — M0 answers whether the carrier and each footprint discriminate at
all, holding session and own-vol regime fixed. Liquidity/size matching is omitted
with reason: on a back-adjusted store, cross-name turnover ranks inherit per-name
adjustment factors and are not a lawful liquidity measure (full-A `daily_basic` is
the future fix); the vol-decile stratum is the only wildness control M0 claims.

**§5.2 ARM M1 — washout-carrier match.** Universe U1. Strata = session × vol decile
× `dd_band` (d1/d2/d3) × `dur_band` (t0..t3): among similarly washed-out names on
the same tape at the same depth and duration, does F still separate boarders?

**§5.3 Carve-out rule (frozen).** A footprint is never evaluated inside strata built
from its own underlying series, where "series" includes shared parents: `dd250` and
`dd_dur` both descend from the same rolling 250-session high, so the DD/duration
family is ONE series for carve-out purposes. QB (a function of `rv_rank`) drops the
vol-decile factor in BOTH arms (its measurability mask, §4, still excludes
rv-unmeasurable rows). DD35 in M1 drops BOTH `dd_band` and `dur_band` (strata:
session × vol) — its M1 estimand is "incremental depth information over session and
own-vol among washed-out names". The depth gradient and the duration gradient in M1
likewise drop both factors. VZ (volume z) keeps the vol-decile stratum — realised
return-vol and volume surprise are distinct series; a no-vol-stratum sensitivity is
printed beside it. §11 check 8 asserts the applied map.

**§5.4 S-arm — same-sector sensitivity.** M1 strata × sector, non-SECT-family
footprints only (SECT and `sect35_band` excluded), FIT only, sensitivity table only.
Never citable for SECT's own incremental value; thin cells refuse.

**§5.5 Verdict arm per footprint (frozen):** DD20 → M0. DD35, depth/duration
gradients → M1-with-carve-out (gradients get no verdicts — descriptive). MA200,
CONF, CB, SECT, QB, VZ → M1. M0 reported beside every M1 verdict; S-arm gates
nothing.

**§5.6 Retention diagnostics and refusal (frozen — strata are sparse at these
densities; measured mean M1 occupancy 3.9 rows/stratum on main FIT, 1.4 on chinext20
FIT, <1 on star).** Contrast-bearing strata (n_F1>0 ∧ n_F0>0) are a non-random,
density-biased subset, and the exp leg collapses first. Per footprint × board ×
split × arm the receipt prints: retained fraction of F=TRUE rows AND of F=TRUE
positive episodes; retained fraction of F=FALSE rows; and the W-weighted composition
of retained vs full F=TRUE mass over each stratum factor. **REFUSAL: a cell
retaining < 50% of its F=TRUE positive episodes is NOT_EVALUABLE** — never NULL,
never a verdict. A verdict whose retained F=TRUE mass is > 80% in a single dd_band
is labelled "(band-local: dX)" — MA200 and SECT are near-determined by depth
(97%/73% presence in d3), so their M1 verdicts are expected to be band-local and
must say so.

## §6 Inference — market-time first, then name structure

Frozen constants: SEED = 20260814, N_BOOT_SESSION = 4000, N_BOOT_NAME = 2000,
N_BOOT_ROW = 2000, N_PERM = 2000 (diagnostic only), BLOCK_LEN = 21 sessions,
THIN_STEP = 10, LEAD_CURVE_B = 1000. TZ=UTC; byte-identical reruns.

1. **Primary SE — two-way clustered (CGM).** Three bootstrap SEs of the matched
   excess, all computed on per-stratum sufficient-statistic tables (never rows):
   se_session (session-block bootstrap, blocks of BLOCK_LEN consecutive sessions,
   block count preserved — blocks longer than H absorb the ~10× episode-overlap
   design effect), se_name (name-cluster bootstrap via weighted-row bincount), and
   se_row (row bootstrap, printed only as the design-effect denominator).
   **se_2way = sqrt(se_session² + se_name² − se_row²)**; if the radicand is ≤ 0,
   se_2way = max(se_session, se_name) and the cell is flagged `cgm_degenerate`.
   Gates use z = excess / se_2way with the normal approximation, stamped as such;
   the §6.3 placebo calibration is the empirical guard on that approximation.
2. **Permutation (DIAGNOSTIC ONLY — stamped anticonservative).** The within-stratum
   fixed-margin permutation is printed for reference and never gates: its null
   treats each row as an independent draw while one episode contributes ~10 positive
   rows (§3), understating the null SD by ~√10. Where computed, it recomputes the
   FULL standardized excess per draw (exp moves with every draw — never held
   fixed), reports both tails, and uses the (1+count)/(1+N_PERM) correction.
   §11 check `permutation_recomputes_exp` guards the first property.
3. **Placebo-feature calibration (the measured false-positive guard).** Shift the
   entire footprint panel forward by S ∈ {250, 500, 1000} sessions along each
   name's own axis — preserving within-name persistence, cross-sectional prevalence
   and session structure, breaking only the alignment with outcomes — and run the
   full primary battery per shift. The receipt reports the realized rejection rate
   at the G2 bar over shifts × footprints × boards. **Frozen consequence: if the
   placebo rejection rate at the G2 bar exceeds 5× nominal (i.e. > 2.5%) in a
   (board, horizon) family, every DISCRIMINATOR in that family downgrades to
   SUGGESTIVE and the receipt states that the inference machinery failed its own
   calibration.**
4. **Thinned-anchor sensitivity.** Keep every THIN_STEP-th eligible session per
   name (deterministic phase = the name's first eligible row; non-overlapping
   windows at H=10 ⇒ ≤1 positive row per episode). The thinned point estimate's
   sign is gate G3.
5. **Honest N** on every cell: rows, episodes, names, sessions, per class. Session
   and episode counts print FIRST; row counts are never presented as independent
   observations.

## §7 Splits and eras — W-P0's frozen discipline, adopted verbatim

W-P0's `split` column (EMBARGO_SESSIONS = 20): **FIT** = train (2011→2019) +
calibration (2020→2023); **HOLDOUT** = locked test (2024-01-02 → 2026-06-12);
**AUDIT** = 2026-06-15 → 2026-08-07, reported separately, descriptive, never gated.
G1–G4 read FIT; G5 reads HOLDOUT; nothing else gates. Era tables on every lift;
boards never pooled, eras never averaged.

## §8 Verdict gates — frozen before any outcome is read

Floors (G1), per board × horizon, on the verdict arm's universe:

- board verdict-eligible: ≥ 200 distinct positive episodes in FIT AND ≥ 60 in
  HOLDOUT; else every footprint on that board is **DESCRIPTIVE_ONLY**.
- **Frozen expectations from the published receipts (stated now so no floor is
  re-shopped later):** `chinext10` is DESCRIPTIVE_ONLY **by construction** — the
  board key exists only before 2020-08-24, so it has zero HOLDOUT rows, forever.
  `star` is expected to fail the FIT floor (~72 U1 FIT positive episodes measured
  from the W-P0 receipt). The realistic gated-verdict ceiling is therefore
  **≤ 8 footprints × 2 boards (main, chinext20) × 2 horizons = 32**, not 64. On
  star, DD20's M0 cell sits near the floor while every M1 footprint is
  DESCRIPTIVE_ONLY — an arm-dependent asymmetry that is coherent and stated here so
  the receipt does not read as inconsistent.
- footprint evaluable in a cell: measurability mask applied (§4); ≥ 50 F=TRUE
  positive episodes in FIT **in the retained matched sample**; ≥ 30 retained rows
  in each F-class; retained-episode fraction ≥ 50% (§5.6); F prevalence within the
  retained sample ∈ [0.5%, 99.5%]. Anything failing prints **NOT_EVALUABLE** (a
  dead feature prints NOT_EVALUABLE, never NULL).
- era measurable: ≥ 50 positive episodes in that era. G4's strictness varies by
  board and is accepted as-is: ~5 measurable FIT eras on main (≥4 must agree at
  the 2/3 rule), 2 on chinext20 (unanimity).

**DISCRIMINATOR** requires ALL of:

- **G1** floors met.
- **G2** FIT |z_2way| ≥ 2.81 (two-sided p ≤ 0.005 under the stamped normal
  approximation on the CGM SE).
- **G3** thinned-anchor FIT estimate has the same sign as the full estimate.
- **G4** matched-excess sign agrees in ≥ 2/3 of measurable FIT eras.
- **G5** HOLDOUT: same sign as FIT AND one-sided z_2way ≥ 1.28 (p ≤ 0.10) in the
  FIT direction, on HOLDOUT's own CGM SE (27 session blocks — the z-form is used
  precisely because a 27-block percentile CI is too lumpy to gate).

**SUGGESTIVE**: G1 met, FIT |z_2way| ≥ 1.96, but fails ≥ 1 of G3/G4/G5. **NULL**:
G1 met and neither. A cell whose F=TRUE positive **episodes** are > 40% from a
single name is CONCENTRATED and caps at SUGGESTIVE. The §6.3 placebo consequence
overrides everything: a family that fails calibration has no DISCRIMINATOR.

**Multiplicity accounting:** ≤ 32 gated verdicts (frozen expectation above). The
protection is the G2–G5 conjunction; Holm-adjusted p within each (board, horizon)
family is printed as a reference column and changes no gate. No gate, floor,
stratum or family is re-shopped after results.

## §9 Two-speed lead-curve battery (secondary, descriptive)

Events: P-B's own `extract_events` cohort (cold-eve first boards, `in_cohort`).
Frozen lead grid ℓ ∈ {1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60}; frozen narrative
windows: ignition [1,5], approach [6,20], structural [21,60].

- **Case anchor at lead ℓ:** the event name's panel bar exactly ℓ sessions before
  the board (own axis), kept only if U1-eligible at that bar; per-ℓ exclusion
  counts and cohort N printed ON the curve. **Known mechanical break, stated now:**
  coldness at ℓ ≤ 20 is implied by the event's own cold eve (COLD_LOOKBACK_K = 20),
  so cold-exclusions are ~0 through ℓ=20 and jump at ℓ=21 — exactly the
  [6,20]→[21,60] window boundary. No comparison across that boundary may be made on
  the full-cohort curve; the boundary is a COLD_LOOKBACK_K artifact.
- **Quiet control rows:** same-session U1 rows with a **complete 60-session forward
  chain** — 60 consecutive forward panel steps each within MAX_STEP_GAP_DAYS = 21
  (new machinery, pinned; there is no frozen `win_ok_60` column) — and no tolerant
  board within those 60 sessions. A row whose remaining tape cannot prove 60 quiet
  sessions is EXCLUDED AND COUNTED, never admitted: the next-board-distance
  sentinel (no future board ⇒ distance = BIG) would otherwise admit every
  end-of-data row as "verified quiet" — right-truncation enriching the control arm.
  §11 check `control_completeness` guards this.
- **Statistic:** standardized excess prevalence of F among case anchors vs quiet
  controls, strata = M1's with §5.3 carve-outs; pointwise **session-block bootstrap
  95% CI** (B = LEAD_CURVE_B) — no permutation p anywhere on the curves; the
  battery is descriptive and gates nothing.
- **Composition control:** the constant-cohort curve (events eligible at EVERY grid
  ℓ) is printed ONLY for MA200, CONF, CB, SECT, QB, VZ. It is NOT interpretable for
  DD20/DD35/depth/duration — U1-eligibility at every lead IS the DD condition, so
  their constant-cohort curves are tautologically flat — and is not printed for
  them (stated here so its absence is not read as an omission).
- FIT and HOLDOUT separately; boards never pooled.

## §10 Flagged-set diagnostics (descriptive, explicitly not a ranker)

Per board × split on the verdict arm's universe: precision P(fb_10 | F=TRUE),
capture P(F=TRUE | fb_10), flag rate P(F=TRUE), per-session flagged-count
median/IQR. No threshold is tuned, nothing is combined or ranked, no per-name
selection exists (`DNR:KILL-OUTCOME-AUDITION` respected), and no number here may be
quoted as a strategy result.

## §11 Verification battery — every check paired with a mutation it must detect

A check that cannot fail is a defect; `detected: false` anywhere voids the receipt.

1. **label_identity**: `fb_H == win_ok_H ∧ (panel-re-derived next-board distance ≤
   H)` exactly, for H ∈ {5,10,20}, scoped to rows with T+H inside the panel window;
   the count of positives whose board bar falls outside `WINDOW_END` is printed and
   must be 0. Probe: off-by-one the re-derivation.
2. **no_lookahead (fixed anchors)**: rebuild a name subset with all bars after a
   cut scaled ×1.35 (three cuts spanning the history); at fixed (ticker, anchor)
   rows whose feature lookbacks close before the cut, every footprint and stratum
   value is bit-identical; labels may move only on the window-crossing set, EXCEPT
   detector-rounding flips (`round(pc*(1+w),2)` is scale-dependent) which are
   counted and reported separately rather than voiding the receipt. Probe: scale a
   slab INSIDE the pre-cut history (must move features).
3. **stratum_outcome_independence**: stratum keys byte-identical after permuting
   labels within (board, session). Probe: leak the label into the stratum key.
4. **cold_universe**: recompute the prior-20 quiet rule on a sample of U rows
   (including the anchor bar itself); plant a board 5 sessions back (must eject)
   and 25 back (must survive). Probe: assert the 25-back plant ejected.
5. **censoring_partition**: eligible = positives + negatives + censored exactly,
   per board × split; censored counted per F-class; no censored row in any
   estimator. Probe: count censored as negative.
6. **board_era_disjointness**: no pooled board or era key in any table. Probe:
   inject an `ALL_BOARDS` row.
7. **feature_liveness**: every verdict cell has both F-classes populated per G1; a
   zeroed column AND an all-TRUE column must both surface as NOT_EVALUABLE, never
   as NULL. Probes: zero a column; force a column all-TRUE.
8. **carveout_applied**: strata actually used per footprint match the frozen §5.3
   map. Probe: flip a map entry.
9. **concentration_guard**: per-cell max single-name share of positive EPISODES
   printed; > 40% flags CONCENTRATED. Probe: duplicate one name's positive rows.
10. **placebo_sensitivity**: the §6.3 placebo battery must be able to see a real
    leak — a synthetic footprint planted equal to the label on a subsample must
    reject far above nominal UNSHIFTED and fall back to ~nominal under the shifts.
    Probe: run the planted footprint with shift 0 asserted as calibrated (must
    fire).
11. **missing_not_false**: for each footprint, the analyzed F=FALSE class contains
    zero rows failing that footprint's measurability mask (§4). Probe: re-admit
    unmeasurable rows.
12. **control_completeness** (§9): zero admitted quiet controls with an incomplete
    60-session forward chain. Probe: admit them.
13. **permutation_recomputes_exp**: the diagnostic permutation's exp moves across
    draws. Probe: hold exp fixed (p must change materially).
14. **stop_ship_reference_scan**: P-B's fragment-assembled token scan over
    instrument + receipts. Probe: inject a withdrawn token.
15. **detector_vs_zt_pool**: recall of the tolerant detector on vendor pool rows
    (recall-only, partial vendor). Probe: switch off 5% of detector flags.
16. **provenance (A4/A5)**: every store stamp an ancestor of the build head; refuse
    on a moved checkout; shallow-graft stamps relabelled
    `SHALLOW_BOUNDARY_UNRESOLVED`. Probe: assert a non-ancestor stamp passes (must
    not).
17. **lead_anchor_position**: case anchor at ℓ is exactly the event bar minus ℓ on
    the name's axis, sampled. Probe: off-by-one ℓ.

## §12 Provenance, determinism, pins, compute discipline

`base_sha`/`build_head_sha`, store commits (`raw_store_commit`, `members_commit`,
`st_snapshot_commit`, `zt_pool_commit`), `w1_sha256` AND `pb_sha256` pins with
P-B-style line-pin tables for every imported symbol; ancestry-guarded before either
receipt file is written. SEED = 20260814; TZ=UTC; byte-identical reruns; no
wall-clock value in receipts. **Compute discipline (frozen):** all permutation and
bootstrap arithmetic runs on per-stratum sufficient-statistic tables
`(n_F1, k_F1, n_F0, k_F0)` computed once — never on rows — with draw loops chunked
over strata (~5k-stratum blocks); the naive whole-matrix draw at M1's stratum count
(~340k strata × N draws) is a multi-GB allocation and is forbidden. Outputs:
`research/cn_prophet_audit/pb2_precursor_discrimination.py`,
`PB2_PRECURSOR_DISCRIMINATION_2026-08-14.json`,
`PB2_PRECURSOR_DISCRIMINATION_2026-08-14.md` (every table carries honest-N and its
refusal counts; a "what this does NOT establish" section is mandatory and must
include the §1 cross-sectional-estimand scope).

## §13 Boundaries — what this study may not touch

- No edit to `engine/china_board_rank.py` scoring, featured admission, Prophet
  weights, user-facing priority, or any production candidate population. No
  cn_prophet_v4. The first production evolution is a future fork under its own
  preregistration after the exact-plane gates.
- No new data store, no competing expert-event store (`mastermind.entry_event.v1`
  is Live Entry Radar's), no per-security expert routing (Stock Identity's), no
  outcome audition (`DNR:KILL-OUTCOME-AUDITION`).
- No import of China Intelligence composite scores (opportunity_score /
  conviction): display constructions; raw evidence producers only, each re-earning
  incremental value under its own preregistration.
- No forward ledger, no picks surface, no user-facing probability. The exact-plane
  reopen chain is unmodified.

## §14 Result disposition — a null is a valid ship

If the footprints mostly fail these gates against matched controls, that is the
finding and it ships as such: the receipt says so plainly, the program home's P-B2
row records it, and nothing is rescued by a new feature, a changed match, a widened
floor or a re-run at a friendlier horizon. Per the ore law a null closes THIS
construction — **within-session cross-sectional matched discrimination** of these
eight footprints on this substrate at these horizons — not the search space (market-
timing/regime forms of the same families are untested here by construction; deeper
lawful data: P-C; conjunctions: P-D; exact plane: the reopen chain). DISCRIMINATOR
verdicts, if any, remain display-tier facts about the survivor large-cap slice on
the tolerant plane; they authorize the next research wave, not a scorer.

*Frozen 2026-08-14 by the P-B2 orchestrating session (WS:CN-LIMIT-ALPHA), after
adversarial pre-freeze review and before any outcome run. Instrument, receipts and
any amendments follow in later commits of the same PR.*
