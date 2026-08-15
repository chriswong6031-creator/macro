# P-B3 — persistence-robust certification: PREREGISTRATION (2026-08-15)

Status: **FROZEN BEFORE OUTCOME ACCESS.** This document is committed to git BEFORE any
P-B3 instrument exists and BEFORE any P-B3 outcome is read. The commit hash of this
file is the freeze proof once independent adversarial review passes. Any deviation
discovered during a later build is a NUMBERED AMENDMENT in that later receipt (the
P-B / P-B2 practice: what changed, why, what controls it) — never a silent re-choice
of estimand, null, cell, floor, gate, sign, or primary/corroborative assignment.

This session writes the preregistration only. **No study runner, no result JSON, no
outcome table, no new computation on the panel.** An independent adversarial review
happens after this PR exists. The certification run is a later session.

Authority: `none_research_display_only`. Nothing here ranks, sizes, gates, alerts,
trades, or feeds any production score. There is **NO P-B3 production ranker**.

Governing rulings, in order: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, then
`research/CN_LIMIT_ALPHA_RECONCILIATION_LEDGER_2026-08-09.md`, then the program home
`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md`, then
`DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`, then this file. No withdrawn W1–W3
artifact, number or receipt is cited as evidence.

Eval OS: no qledger claim is minted. Display-tier measurement. Any future
promotion-bearing consumer goes through the gauntlet and registers its own claims.

---

## §0 Relation to P-B2 — this is a new design, not a rewrite

P-B2 is **DONE**. Its shipped verdict stands and is not reopened:

> **NO DISCRIMINATOR AT THE PREREGISTERED BAR** — a calibration-governed null, not a
> measured absence of structure. 11 of 31 gated cells cleared G1–G5 and every one
> was downgraded by the frozen §6.3 family consequence.

This wave does **not** move P-B2 gates, floors, strata, or the §6.3 consequence. It
does **not** reinterpret that null as “structure after all.” It answers a
**different question** with a **different estimand and a different null**, which is
why it is a new preregistration rather than an in-place amendment.

House precedent (`DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE`;
`research/short_side/SP1_SHORT_PRESSURE_PREREG.md` §5B): supersession / a new prereg
is reserved for changes to the **design** — hypotheses, conditioners, horizons,
universe, controls, statistics, or the promotion bar. In-place amendment is for a
corrected factual gloss that does not move the design. P-B3 changes the estimand
and the certification null. That is a design change. P-B2’s prereg file is left
byte-untouched.

What P-B2 left **unresolved** (read from the frozen receipt and DSC only — not a
new outcome read):

- **DD-family indeterminacy.** The shift-placebo null is false for multi-year
  states (`DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`). DD20’s placebo excess
  fully reproduced the real excess; DD35 reproduced 29–43%. The lead-curve reading
  (P-B2 receipt §8) is a **persistent state, not a turn-on**. Whether that
  structure is state-timing information or persistent multi-year alignment is
  uncertified.
- **MA200 / QB / VZ structure.** Placebo-clean at the cell level (non-DD
  rejection rate 1/144 = 0.69%, inside the 2.5% bar) with holdout-consistent
  signed excess, but family-downgraded because they sat in (board, horizon)
  families the DD cells failed. The shift-placebo cannot be reused to certify
  them as timing, and P-B2 forbids reading a SUGGESTIVE inside a failed family
  as a weaker discriminator.

P-B2’s construction — within-session cross-sectional matched discrimination under
a long-horizon feature-shift null — stays closed. This wave does not rerun it.

---

## §1 The question

**PRIMARY.** Among the footprints P-B2 left unresolved, does a **lawful
within-name state transition** change the conditional probability of a first
tolerant limit-up close within the next H sessions, after session, board,
volatility, washout-carrier and name-propensity controls — or is the apparent
discrimination manufactured by persistent level membership / name propensity?

**CORROBORATIVE.** Under a randomization that **preserves** each feature’s
persistence, spell-duration distribution and name-level prevalence, and
**breaks** only the state-to-outcome timing relationship, is the observed
occupancy-to-outcome association unusual? Long-horizon feature shifting
(P-B2 §6.3, S ∈ {250, 500, 1000}) is **not** this null and is **not** reused
as a certification statistic.

**Mechanism, not a menu.** A surviving occupancy association that dies once
within-name propensity / state persistence is handled is **not** timing alpha.
A market-regime effect is **not** an instrument effect.

"First tolerant limit-up close" is W-P0’s `fb_H` verbatim, same detector, same
cold rule, same closure-tolerant completeness (`win_ok_H`). Never conflated: an
intraday touch, a generic big day, and a continuation board are different
objects and none of them is the label.

**Estimand scope, stated up front:**

- Design A is a **within-name transition** statement: does *this name*’s
  conditional board probability change around a lawful flip of F, versus a
  matched non-flip period of the same name.
- Design B is a **persistence-preserving occupancy-timing** statement: given
  this name’s spell lengths and prevalence, is the *when* of those spells
  aligned with outcomes more than a duration-preserving shuffle allows.
- Neither is a market-timing / regime claim. Session matching removes
  “boards cluster when the whole tape is washed out” by construction.
  Instrument verdicts are not market verdicts
  (`DEC:INSTRUMENT-VERDICT-IS-NOT-MARKET-VERDICT`).

---

## §2 Scope — exact cells, frozen, no shopping

Reopen **only** the structure P-B2 left unresolved, plus the companion cells
required to keep the frozen family comparison intact. **Do not reopen all 31
P-B2 gated cells. Do not introduce new footprints.**

**In-scope footprints** (P-B vocabulary, nothing else):

| Short | Column | Why in scope |
|---|---|---|
| DD20 | `dd_le_m20` | DD-family indeterminate; companion to DD35 (same `dd250` series) |
| DD35 | `dd_le_m35` | DD-family indeterminate; lead curve = persistent state, not turn-on |
| MA200 | `under_ma200` | Placebo-clean signed structure; reclaim anatomy |
| QB | `quiet_base` | Placebo-clean signed structure |
| VZ | `volz_gt1` | Placebo-clean signed structure; coincident-indicator stamp travels |

**In-scope boards:** `main`, `chinext20` — the two boards that were
verdict-eligible under P-B2 G1. **In-scope horizons:** H = 10 (primary),
H = 5 (secondary).

**Exact cell list (20 cells).** Every cell is footprint × board × horizon:

`{DD20, DD35, MA200, QB, VZ} × {main, chinext20} × {H10, H5}`.

Chinext20 DD cells that printed NULL in P-B2 are **in** this list. They are
companions for the family comparison, not a winners-only reopen of the 11
G1–G5 cells. Excluding them after seeing P-B2 would be cell-shopping.

**Explicitly out of scope:**

- CONF (`confluence_long`), CB (`cb_recent`), SECT (`sector_deep35_ge40`) —
  not the unresolved persistence structure. Chinext20 CONF H10 SUGGESTIVE is
  not reopened.
- `chinext10` — DESCRIPTIVE_ONLY by construction (zero HOLDOUT rows forever).
  **No ChiNext10 inferential resurrection.**
- `star` — P-B2 FIT-floor failure stands. The STAR floor is **unchanged**.
  A future STAR study needs its own preregistration; this file does not
  specify one.
- Banded gradients (`below_band`, `dur_band`, `sect35_band`, `volz_band`) —
  descriptive in P-B2, not reopened as verdict families.
- Any ninth footprint, pair, triple, grid, learned score, or China
  Intelligence composite.

---

## §3 Substrate, pins, labels, splits — inherited, not re-derived

One store, one panel: `data/china_stocks_raw` through W-P0’s own `build_panel()`
+ `attach_conditioners(panel, None)` (chips=None — S5b remains P-C), via import
of `research/cn_prophet_audit/washout_onset_w1.py` and P-B’s
`build_footprint_panel` / `derive_footprints` / `extract_events` from
`research/cn_prophet_audit/pb_case_decomposition.py`. **No third implementation
of any definition.** Window: W-P0’s own 2011-01-01 → 2026-08-07.

Pins, frozen as of this prereg’s authorship checkout (byte-identical to the
P-B2 receipt vintage):

- `washout_onset_w1.py` sha256 prefix `11ac61de71f0f595`
- `pb_case_decomposition.py` sha256 prefix `f42b0566beb60bec`
- P-B2 prereg `PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md` sha256 prefix
  `043a85d69f76ea86`

A later runner **refuses** on a pin mismatch. Inherited limits stamped on every
future receipt: back-adjusted basis; curated large-cap **survivor** slice;
current-membership sector map (irrelevant here — SECT is out of scope, but the
panel still carries it).

**Universes, labels, splits — P-B2 verbatim:**

- U0 = `cold` ∧ split assigned ∧ `dd250` finite. U1 = U0 ∧ `dd250 <= -0.20`.
- POSITIVE = `fb_H`; NEGATIVE = `win_ok_H` ∧ ¬`fb_H`; CENSORED = ¬`win_ok_H`.
  Censored rows enter neither class and are never scored as misses.
- FIT / HOLDOUT / AUDIT = W-P0’s `split` (EMBARGO_SESSIONS = 20). Gating
  reads FIT then HOLDOUT. AUDIT is descriptive, never gated.
- Boards never pooled; eras (`era_of`) never averaged.
- Verdict arm per footprint, inherited from P-B2 §5.5: DD20 → U0 / M0-class
  match; DD35 → U1 with the §5.3 carve-out (session × vol, not `dd_band` /
  `dur_band`); MA200, QB, VZ → U1 / M1-class. QB drops the vol-decile factor
  in both designs (inherited carve-out).

Measurability masks inherited from P-B2 §4: unmeasurable is never FALSE.
VZ coincident-indicator stamp (median arming lead 1 session, P-B §5) travels
with every VZ verdict; VZ is never described as an early precursor.

---

## §4 Design choice — A is primary, B is corroborative

**Both designs run. A is PRIMARY. B is CORROBORATIVE.** The assignment is
frozen here (`DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`). The later session
cannot swap them after seeing numbers.

### Why both, from frozen P-B2 / DSC evidence (no new table)

Three mechanism-distinct candidates were on the table:

1. **A only** — within-name transition contrast.
2. **B only** — persistence-preserving permutation null.
3. **Both**, with a declared primary.

**A only is rejected.** P-B2’s own lead-curve reading says DD35 is a
persistent state, not a turn-on. Multi-year spells imply few lawful onsets.
A-only can return INSUFFICIENT SUPPORT on the exact cells that created this
wave, and then the indeterminacy DSC named would remain. Occupancy-timing
(“being in the state at T changes P(board in T+1..T+H), even if onset was
years ago”) is a real hypothesis A can miss if it only sees flips.

**B only is rejected.** B can reject a persistence-valid occupancy null
without identifying transition-timing. P-B2’s MA200 anatomy is already a
**reclaim** (exit), which is a transition estimand. House law forbids calling
cross-sectional lift on a persistent state “timing” without this
certification; B-only would recertify occupancy and then invite that
mislabelling. Name propensity is the competing story the mission requires
tested; A is the direct within-name control.

**Both, A primary.** Timing’s cleanest estimand is the within-name flip.
That is the question this wave exists to ask. B is the DSC’s other named
falsifier — the null whose assumptions remain valid under persistent
features — and is the fallback that can still speak when transition N
fails. The joint disposition in §10 freezes what happens in every
A-status × B-status cell so the later run cannot shop the headline.

The later run may print a diagnostic long-horizon shift (S ∈ {250, 500,
1000}) **only** as a negative-control check that the DSC failure still
appears on DD. That diagnostic **gates nothing** and is **not** a
certification null.

---

## §5 Design A — within-name state-transition contrast (PRIMARY)

### §5.1 Lawful transition

On name *i*’s own live-session axis, after F is measurable, a **lawful
transition** at bar T is a flip of F that survives a dwell filter:

- **Onset** (FALSE→TRUE): F is FALSE for ≥ `DWELL_PRE` consecutive eligible
  sessions immediately before T, and TRUE at T.
- **Exit** (TRUE→FALSE): F is TRUE for ≥ `DWELL_PRE` consecutive eligible
  sessions immediately before T, and FALSE at T.

`DWELL_PRE` = **5** sessions for DD20, DD35, MA200, QB. `DWELL_PRE` = **2**
for VZ (P-B2 median arming lead is 1; a 5-session dwell would define a
different object than the coincident surprise). These constants are frozen
now so a later session cannot shorten VZ’s dwell after seeing N, or lengthen
DD’s dwell after seeing too many flickers.

One-bar flickers are not transitions. A bar that fails the measurability
mask breaks the dwell count (it does not count as FALSE).

### §5.2 Primary event and expected sign — frozen from published P-B2 structure

The primary edge is the edge P-B2’s **published signed structure** points
at. This is prior published evidence, not a P-B3 outcome. **The opposite
edge is a mechanism diagnostic and never gates.**

| Footprint | Published P-B2 signed structure (main · H10 · FIT, receipt table) | Primary A event | Frozen expected sign of A excess |
|---|---|---|---|
| DD20 | +1.043 pp in-state | ONSET of `dd_le_m20` | positive |
| DD35 | +2.954 pp in-state; lead curve flat-to-rising (not a turn-on) | ONSET of `dd_le_m35` | positive |
| MA200 | −2.747 pp under the line; deficit deepens toward ignition (reclaim) | EXIT of `under_ma200` | positive (board more likely after reclaim than after matched stay-under) |
| QB | −1.464 pp in quiet base | ONSET of `quiet_base` | negative |
| VZ | +1.406 pp; coincident stamp | ONSET of `volz_gt1` | positive |

A later session that flips MA200 to “onset-under” because the reclaim is
null, or flips DD to “exit” because onset is null, has shopped the edge.
That result does not exist.

DD’s expected-positive onset is **not** a prediction that A will certify.
The lead curve says the opposite shape. A NULL on DD onset with B
occupancy surviving is a coherent, pre-registered outcome (§10 row 2).

### §5.3 Treatment, label, control

- **Treatment anchor** = the transition bar T. Label = W-P0 `fb_H` at T.
  Censoring as §3. The transition uses only information through T.
- **Control class** (frozen, within the same name):
  - Onset footprints (DD20, DD35, QB, VZ): **stay-FALSE** — F remains FALSE,
    and no F-transition falls in `[T_ctrl − 10, T_ctrl + 10]`.
  - MA200 exit: **stay-TRUE** (stay-under) — F remains TRUE, and no exit
    falls in that same quiet-on-F window.
- **Eligibility of both anchors:** U-eligible on the footprint’s inherited
  verdict universe (U0 for DD20, U1 otherwise), F measurable, cold, split
  assigned, `win_ok_H` defined (censored dropped).
- **Board / era:** a name that changes board key across 2020-08-24 is two
  populations; FIT-era and HOLDOUT-era bars are never paired to each other.
  Control and treatment share `era_of`.
- **Session-regime:** control session is matched to treatment session on
  `era_of` and on a session-level washout bin (cross-sectional U1 fraction
  that day, terciles computed on FIT sessions only, applied forward). This
  is the regime control. A diagnostic that **drops** session-regime matching
  is printed and never gates (§8 M4).
- **Volatility:** same W-P0 `rv_rank` decile, except QB (inherited carve-out).
- **Carrier:** M1-class footprints also match `dd_band` (DD35 drops
  `dd_band` / `dur_band` — inherited carve-out).
- **Non-overlap:** control is ≥ H sessions from the treatment (outcome
  windows do not share a label bar) and ≥ 21 sessions away (`BLOCK_LEN`).
- **Tie-break (deterministic):** among surviving controls, closest vol
  decile, then closest session-count distance, then earlier session wins.
- **Unmatched treatments** are counted, never imputed. A cell whose
  unmatched-treatment fraction of distinct-name events exceeds **50%** is
  `NOT_EVALUABLE` on A — never NULL, never a verdict.

### §5.4 A estimator

ATT-weighted standardized difference of P(`fb_H`) on treatment vs matched
controls, aggregated over the matching strata of §5.3, weighted by the
treatment count. Honest-N on every cell: distinct-name transition events
first, then distinct names, then distinct sessions, then rows last.

Primary SE: two-way clustered (session-block of 21 + name), CGM form as
P-B2 §6.1, z = excess / se_2way, normal approximation stamped as such.
Gates use this z. A within-name permutation of treatment labels (diagnostic
only) is printed and never gates.

---

## §6 Design B — persistence-preserving null (CORROBORATIVE)

### §6.1 What is preserved, what is broken

For each name and each in-scope footprint F, segment the name’s measurable
eligible axis into contiguous **spells** (runs of F=TRUE and F=FALSE).

One permutation draw, **independently inside FIT and inside HOLDOUT**
(within-split, so holdout structure is not shuffled into FIT):

- keeps the **multiset of F=TRUE spell lengths** (duration distribution
  exact at the name × split grain)
- keeps the **total F=TRUE bar count** (name-level prevalence exact)
- fills residual bars with F=FALSE
- refuses to place a TRUE spell across a board-key change
- refuses to place F on a bar that fails F’s measurability mask

This breaks **when** the spells sit relative to outcomes. It does **not**
translate the entire path by 250/500/1000 sessions. That shift is the
null DSC proved false for persistent states and is not reused here.

### §6.2 Degrees-of-freedom refusal (the honest “this is a name constant”)

A name is **PERM-INERT** for F in a split when any of:

- fewer than **2** F=TRUE spells in that split, or
- the longest F=TRUE spell covers **> 70%** of the name’s eligible bars
  in that split.

Inert names are excluded from B’s contrast and counted. If the retained
(non-inert) names carry **< 50%** of that cell’s F=TRUE positive episodes,
B is `NOT_EVALUABLE` on that cell. That refusal is itself evidence the
association is name-level; it is recorded as such, not as a B-null and
not as certified occupancy.

### §6.3 B estimator

On each draw, recompute the **P-B2 matched excess** for that footprint’s
inherited verdict arm (M0/M1 strata, §3), using the permuted F and the
real labels. The null is the permutation distribution of that excess.
N_PERM = 2000. Two-sided p uses the (1+count)/(1+N_PERM) correction.
The **real** (unpermuted) F is the observed statistic.

B asks: given this persistence structure and these name prevalences, is
the observed state-to-outcome **timing** unusual?

Compute discipline: all permutation arithmetic on per-stratum
sufficient-statistic tables, never on rows, chunked over strata. The
naive whole-matrix draw is forbidden (P-B2 §12).

---

## §7 Controls that cannot be skipped

Every evaluable cell prints all four. A cell that “passes” A or B but
fails the control that applies is not certified (§8, §10).

1. **Session matching** — A: §5.3 session-regime bin. B: inherited P-B2
   session stratum. Dropping it is a diagnostic only (§8 M4).
2. **Board / era separation** — never pooled; ChiNext 2020-08-24 is a
   hard split; no ChiNext10 resurrection; STAR untouched.
3. **Volatility** — W-P0 `rv_rank` deciles, QB carve-out inherited.
4. **Washout carrier** — M1-class match as inherited. If A/B die once
   `dd_band` is held fixed (where the carve-out does not drop it), the
   cell is carrier-redundant, not instrument structure.
5. **Holdout discipline** — FIT gates first; HOLDOUT confirms; AUDIT
   never gates. B permutes within split.
6. **Two-way / date-aware clustering** — A uses CGM se_2way. B’s p is
   a within-split spell permutation, which already respects name
   structure; session dependence is handled by the inherited session
   stratum inside the recomputed excess.
7. **Honest N** — distinct names and distinct transition events (A) or
   distinct non-inert names and episodes (B) print first. Row counts
   are never presented as independent observations.
8. **Name propensity (explicit).** Two complementary readings, both
   required:
   - **Terciles:** names binned by FIT-only historical fraction of
     eligible bars with F=TRUE (past-only; never computed on HOLDOUT
     or on future bars). A’s treatment-episode share in the top tercile
     must be ≤ 60%, and if bottom+mid terciles each have ≥ 30 events
     they must agree in sign with the headline. Failure → stamp
     `PROPENSITY_CONCENTRATED`, cap at UNINFORMATIVE.
   - **Within-name demeaning (B):** recompute B after replacing F with
     F minus the name’s FIT-only prevalence (a residual occupancy). If
     raw B rejects and demeaned B does not (p > 0.10), the cell is
     `NAME_PROPENSITY` and the B status is NULL, not certified
     occupancy. A state relationship that disappears once within-name
     propensity / persistence is handled is **not** timing alpha.

---

## §8 Mechanism tests — four readings, named in advance

The receipt must classify each evaluable cell into exactly one of these
four, using the pre-registered evidence below. Do not call a regime
effect an instrument effect.

| Code | Mechanism | Evidence that supports it | Evidence that kills it |
|---|---|---|---|
| M1 | Persistent structural state genuinely changes conditional future-board probability | A CERTIFIED_TIMING, or B CERTIFIED_OCCUPANCY after the §7 demeaning control | Dies under propensity demeaning, or lives only when session-regime matching is dropped |
| M2 | Name propensity / persistent level alignment | Top-tercile concentration, B PERM-INERT majority, demeaned B dies | A survives inside bottom+mid terciles; demeaned B still rejects |
| M3 | Washout-carrier redundancy | A/B die under the inherited carrier match and live only when `dd_band` is dropped (where the carve-out does not already drop it) | Survives the inherited M1/carve-out match |
| M4 | Market / session regime timing | Lives only in the diagnostic that drops session-regime matching | Dies, or is unchanged, when session-regime matching is applied |

M4-only survival → cell verdict NULL, stamp `REGIME`. Not an instrument
effect, not a P-D input.

---

## §9 Inference, floors, gates

Frozen constants: SEED = **20260815**, N_PERM = 2000, N_BOOT_SESSION = 4000,
N_BOOT_NAME = 2000, BLOCK_LEN = 21, TZ=UTC. Byte-identical reruns. No
wall-clock value in receipts. New seed (not P-B2’s 20260814) because this
is a new study.

### §9.1 A floors (primary)

Board verdict-eligible: the P-B2 G1 board floors already passed by `main`
and `chinext20` — inherited, not re-shopped. `chinext10` / `star` stay out.

A cell is evaluable only if all of:

- ≥ **80** distinct-name primary-edge transition events in FIT in the
  retained matched sample
- ≥ **30** such events in HOLDOUT
- ≥ **40** distinct names in the FIT retained treatment set
- unmatched-treatment fraction ≤ 50%
- no single name > 40% of FIT treatment events (else `CONCENTRATED`,
  cap at UNINFORMATIVE)
- F prevalence among eligible bars of retained names ∈ [0.5%, 99.5%]

Anything failing prints `NOT_EVALUABLE` or `INSUFFICIENT_SUPPORT` (the
latter when the floor miss is N, the former when the contrast is
undefined). Never NULL.

### §9.2 A gates — CERTIFIED_TIMING requires ALL of

- **G1** floors met.
- **G2** FIT |z_2way| ≥ 2.81, sign = the §5.2 frozen expected sign.
- **G3** thinned-treatment FIT estimate (one treatment per name per
  non-overlapping H+21 window, deterministic earliest-in-window) has
  the same sign.
- **G4** sign agrees in ≥ 2/3 of measurable FIT eras (≥ 30 events in
  that era to be measurable).
- **G5** HOLDOUT: same sign as FIT AND one-sided z_2way ≥ 1.28 in the
  frozen expected direction, on HOLDOUT’s own CGM SE.
- **G6** §7 name-propensity tercile rule passes.

Opposite-edge diagnostics never enter these gates.

### §9.3 B floors and gates — CERTIFIED_OCCUPANCY requires ALL of

- B cell evaluable under §6.2 (retained non-inert names carry ≥ 50% of
  F=TRUE positive episodes; N_PERM completed).
- **G2B** FIT two-sided permutation p ≤ 0.005, observed excess sign
  equal to the P-B2 published sign for that footprint (DD/VZ positive,
  MA200/QB negative — occupancy sign, not the A-exit sign for MA200).
- **G5B** HOLDOUT: observed excess on the same side of the HOLDOUT
  permutation median as FIT, and one-sided p ≤ 0.10.
- **G6B** §7 within-name demeaning: demeaned B still rejects at p ≤ 0.10
  on FIT. Failure → B status NULL, stamp `NAME_PROPENSITY`.

B does not have an era-sign gate (spell counts per era are expected to
be thin for DD). Era tables are printed and never gate B.

### §9.4 What is not a gate

Holm-adjusted p inside each (board, horizon) family is a reference
column and changes no gate. Lead-style descriptive curves are not
re-run as a certification statistic. P-B2’s SUGGESTIVE bar is not
reused. No floor, stratum, dwell, inert-threshold or sign is re-shopped
after results.

---

## §10 Joint disposition, P-B2 preservation, P-D implication

Every in-scope cell receives one A status, one B status, and exactly one
headline verdict from this table. The later session does not invent a
fifth headline.

| A status | B status | Headline | Stamp | Timing language allowed? |
|---|---|---|---|---|
| CERTIFIED_TIMING | any evaluable | **CERTIFIED STRUCTURE** | `TIMING` | yes |
| CERTIFIED_TIMING | NOT_EVALUABLE / INSUFFICIENT (B-inert expected for short-spell F, e.g. VZ) | **CERTIFIED STRUCTURE** | `TIMING` | yes |
| NULL (A evaluable) | CERTIFIED_OCCUPANCY | **CERTIFIED STRUCTURE** | `OCCUPANCY_NOT_TRANSITION` | **no** — occupancy, not timing |
| INSUFFICIENT_SUPPORT or NOT_EVALUABLE | CERTIFIED_OCCUPANCY | **CERTIFIED STRUCTURE** | `OCCUPANCY_ONLY_A_UNDERPOWERED` | **no** |
| NULL | NULL | **NULL** | — | no |
| INSUFFICIENT / NOT_EVALUABLE | NULL | **NULL** | `A_SILENT_B_NULL` | no |
| INSUFFICIENT / NOT_EVALUABLE | INSUFFICIENT / NOT_EVALUABLE | **INSUFFICIENT SUPPORT** | — | no |
| CERTIFIED_TIMING with frozen sign | NULL, and B had df (§6.2 passed) on a long-spell footprint (DD20/DD35/MA200) | **UNINFORMATIVE** | `A_B_CONTRADICT` | no — instrument defect, not a rescue |
| any | any, but §8 lands on M4 only | **NULL** | `REGIME` | no |
| battery fail on that cell | — | **UNINFORMATIVE** | `BATTERY` | no |

**P-B2 is not rewritten.** The P-B3 receipt’s first result sentence is:

> P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR. The numbers
> below are P-B3 verdicts on a new estimand and a new null.

P-B3 may produce CERTIFIED STRUCTURE / NULL / UNINFORMATIVE /
INSUFFICIENT SUPPORT. It may not produce a P-B2 DISCRIMINATOR, may not
relabel a P-B2 SUGGESTIVE as certified, and may not cite P-B winners-only
anatomy as selection evidence.

### §10.1 Exact implication for P-D

- **CERTIFIED STRUCTURE** (either `TIMING` or either occupancy stamp) →
  eligible **INPUT** to the eventual P-D ablation arena. It is not
  production authority. P-D must still show incremental information over
  Prophet, over the washout carrier, and over name propensity, under
  P-D’s own preregistration. Gauntlet at promotion. No ranker is created
  here.
- **NULL** → record the null of **this** construction on that cell. The
  cell is not a P-D input. **Do not re-shop another placebo in the same
  session.** A later wave needs a genuinely new design or a new
  substrate (exact plane, P-C data), not a friendlier null on the same
  cells.
- **INSUFFICIENT SUPPORT** → not a P-D input and not a kill of the
  search space. Full-A re-measurement may re-ask under a new prereg.
- **UNINFORMATIVE** → instrument defect. Stop. Numbered amendment only
  if the defect is pre-outcome; post-outcome, do not heal the battery
  against the result.

If every in-scope cell is NULL or INSUFFICIENT SUPPORT, that is the
finding and it ships as such. Nothing is rescued by a new footprint, a
changed dwell, a widened floor, or a re-run at a friendlier horizon.

---

## §11 Adversarial battery — required negative controls

A check that cannot fail is a defect. `detected: false` anywhere voids
the receipt. Each control is paired with a mutation the instrument must
detect.

1. **Persistent-state null with no timing relation.** Synthetic F =
   name-level constant: 1 iff the name’s FIT-only median `dd250` ≤ −0.35,
   applied to every eligible bar of that name. A must be NOT_EVALUABLE
   or NULL (no within-name transitions, or none that survive dwell).
   B must be PERM-INERT / NOT_EVALUABLE. **Probe:** force this feature
   to flip once per name at a planted date and assert “no transitions”
   (must fire).
2. **Planted timing effect the new design must recover.** Dummy feature
   with short spells (length 3): FALSE→TRUE exactly 5 sessions before a
   random 5% of first-board events (seeded), else FALSE. A MUST produce
   G2-class |z| ≥ 2.81 in the planted direction on FIT (or the cell
   would have certified). B MUST reject its occupancy null at p ≤ 0.005.
   **Probe:** run the plant with labels shuffled (must not certify).
3. **Duration/prevalence-preserving permutation of the planted feature.**
   Apply §6.1 to the planted feature. A and B must fall back toward
   null (A |z| < 1.96 and B p > 0.10). **Probe:** assert the permuted
   plant is still certified (must fire).
4. **Mutation destroying true transition timing.** Take the planted
   transitions of (2) and move each by ± Uniform{20,…,60} sessions,
   clipped to eligible bars. A’s z on the mutated anchors must drop
   below 1.96. **Probe:** assert the mutated plant still meets G2
   (must fire).
5. **Carrier-only / regime placebo.** Feature = 1 for every name on a
   session whose cross-sectional U1 fraction is above the FIT-session
   median (a session-constant). After §5.3 session-regime matching, A
   must be NULL or NOT_EVALUABLE. If A certifies a session-constant
   feature after session matching, session matching is broken.
   **Probe:** drop session-regime matching and assert A is still null
   (must fire — the unmatched diagnostic should see the regime).
6. **Name-propensity control.** Feature = 1 iff the name’s FIT-only
   fraction of bars with `under_ma200` exceeds the cross-name FIT
   median, applied as a constant per name. A: no lawful transitions
   (FIT/HOLDOUT boundary flips are excluded). B: PERM-INERT. Neither
   may certify. **Probe:** assert this constant certifies on B
   (must fire).

The diagnostic long-horizon shift (S ∈ {250, 500, 1000}) may be run on
DD20/DD35 as a seventh **non-gating** check that the DSC failure still
appears. It is not a certification null and it is not a reason to
upgrade or downgrade any §10 headline.

---

## §12 Verification battery — every check paired with a mutation

Inherited in spirit from P-B2 §11; scoped to this design. A later
instrument implements these and refuses the receipt on any miss.

1. **label_identity** — `fb_H` matches the panel-re-derived next-board
   distance rule for H ∈ {5, 10}, same as P-B2. Probe: off-by-one the
   re-derivation.
2. **no_lookahead** — at fixed (ticker, T) whose feature lookbacks
   close before a cut, F and stratum values are bit-identical after
   post-cut scaling. Probe: scale a slab inside the pre-cut history.
3. **transition_dwell** — every admitted A event satisfies §5.1.
   Probe: admit a one-bar flicker.
4. **within_name_control** — every A control shares the treatment’s
   ticker. Probe: pair a control from a different name.
5. **edge_map_frozen** — primary events match §5.2; opposite-edge
   rows are absent from the gate table. Probe: swap MA200 to onset.
6. **split_permutation** — B never moves a FIT bar’s F into HOLDOUT
   or the reverse. Probe: permute across the split boundary.
7. **spell_length_preserved** — per name × split, the multiset of
   F=TRUE spell lengths is identical after each B draw. Probe: jitter
   one spell length.
8. **inert_exclusion** — PERM-INERT names are absent from B’s
   contrast and counted. Probe: force-include an inert name.
9. **censoring_partition** — eligible = pos + neg + censored; no
   censored row in any estimator. Probe: count censored as negative.
10. **board_era_disjointness** — no pooled board or era key.
    Probe: inject `ALL_BOARDS`.
11. **concentration_guard** — max single-name share of A treatment
    events printed; > 40% flags CONCENTRATED. Probe: duplicate one
    name’s treatments.
12. **propensity_past_only** — FIT terciles and FIT prevalences use
    no HOLDOUT or future bar. Probe: leak HOLDOUT occupancy into the
    FIT tercile.
13. **stop_ship_reference_scan** — P-B’s fragment-assembled token
    scan over instrument + receipts. Probe: inject a withdrawn token.
14. **pin_match** — W-P0 / P-B / this-prereg sha prefixes match §3.
    Probe: assert a mutated pin passes.
15. **no_shift_null_as_gate** — no receipt field used for a §10
    headline is the P-B2 S ∈ {250, 500, 1000} shift rejection rate.
    Probe: wire the shift rate into the headline function.
16. **pb2_sentence** — the receipt contains the §10 P-B2-preservation
    sentence verbatim. Probe: delete it.
17. **battery_can_fail** — each §11 control has `detected: true` on
    its probe. Probe: skip probe 2.

---

## §13 Boundaries — what this study may not touch

- Do not restore, re-grade, or cite any adjusted-plane W1–W3 artifact
  (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`).
- Do not use P-B winners-only anatomy as selection evidence. P-B2 is
  the comparison arm; this wave is the persistence-robust certification
  of what P-B2 left unresolved, not a second look at winners.
- Do not shop gates, floors, dwells, inert-thresholds, strata, signs,
  primary/corroborative assignment, or the §2 cell list after results.
- Do not build per-ticker expert selection (`DNR:KILL-OUTCOME-AUDITION`).
- Do not touch `engine/china_board_rank.py`, Prophet weights, featured
  admission, or any production candidate population. No cn_prophet_v4.
- Do not create a production score or ranker. Flagged-set diagnostics,
  if printed, are descriptive and end inside the receipt.
- Do not call cross-sectional lift on a persistent state “timing”
  without a `TIMING` stamp from §10. Occupancy stamps are occupancy.
- Do not import China Intelligence composite scores.
- Do not mint a forward ledger or a user-facing probability.
- Do not auto-roll into the certification run from the freeze session.
- Do not auto-roll into P-D from the certification session.

---

## §14 Result disposition — a null is a valid ship

If A and B both fail to certify the in-scope cells, that is the finding.
It closes **this** construction: within-name transition contrast plus
persistence-preserving occupancy calibration of these five footprints on
this substrate at these horizons. It does not close the search space
(market-timing/regime forms remain untested by construction; P-C; exact
plane; genuinely new footprints).

CERTIFIED STRUCTURE, if any, remains a display-tier fact about the
survivor large-cap slice on the tolerant plane. It authorizes a P-D
**input**, not a scorer.

---

## §15 Provenance, freeze proof, and what this PR does not contain

Outputs of **this** freeze session:

- this file
- `DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`
- workstream / program-home / handoff pointers that the prereg exists

Outputs this session **must not** produce: a study runner, a result
JSON, an outcome table, a new computation on `data/china_stocks_raw`.

Later-session outputs (after independent adversarial review): a
deterministic instrument that imports W-P0 + P-B by the §3 pins, a
receipt markdown, a receipt JSON, numbered amendments if any. SEED =
20260815; TZ=UTC; byte-identical reruns.

*Frozen 2026-08-15 by the P-B3 prereg-only session (WS:CN-LIMIT-ALPHA),
before any P-B3 outcome run and before any P-B3 instrument exists.
Independent adversarial review of this text is the next act. The
certification run is a later session.*
