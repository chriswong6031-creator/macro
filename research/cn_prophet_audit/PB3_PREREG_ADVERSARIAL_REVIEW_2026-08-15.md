# P-B3 prereg — independent adversarial review (2026-08-15)

Status: **FREEZE AMEND** on the freeze-commit text. **A1–A8 APPLIED** in the
same PR (2026-08-15 amend session) — see the tick list below. Do not run the
certification. Do not merge. Do not arm `merge-on-green`. Cheap re-review
ticks each A# against the amended prereg; the run is a later session.

---

## Amendments applied (2026-08-15) — cheap re-review tick list

Applied to `research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md`
as numbered pre-outcome amendments (§16). No runner, no result JSON, no
outcome table. A-primary / B-corroborative was not reopened. DEC assignment
text did not repeat a shopping path and was left untouched.

| # | Required close | In prereg? | Where to tick |
|---|---|---|---|
| A1 | §5.2 points at §10 row 3 / row 4 only; no timing language; row 2 is not the DD occupancy fallback | YES | §5.2 |
| A2 | Most-specific row wins; first-match forbidden; row 1 is `CERTIFIED_TIMING \| B CERTIFIED_OCCUPANCY or B not computed` and excludes B NULL; B NULL + A CERTIFIED_TIMING on DD20/DD35/MA200 is only row 8 | YES | §10 matching rule + table row 1 |
| A3 | Occupancy headline is **CERTIFIED OCCUPANCY**, not STRUCTURE; “timing” deleted from §6.3; P-D treats occupancy as a named covariate, not a timing family | YES | §6.3, §10 table rows 3–4, §10.1, §14 |
| A4 | No-merge spell-sequence shuffle; residual-fill of TRUE lengths only forbidden; `false_spell_length_preserved` + `no_true_spell_merge` | YES | §6.1, §12.7a, §12.7b |
| A5 | Coarse-df names (≤2 long spells / two-longest >70% / <20 legal placements) are PERM-INERT; <50% retained-episode refusal expected on DD, not certified occupancy | YES | §6.2 |
| A6 | G6B is DSC’s cross-name path assignment, not `F − p_i`; plant still rejects; name-constant must not certify | YES | §7.8, §9.3 G6B, §11.2, §11.6 |
| A7 | M3 `NOT_APPLICABLE` on DD20/DD35; non-null DD headline carries `CARRIER_SERIES`; not incremental to the washout carrier | YES | §8, §10, §10.1 |
| A8 | chinext20 · H5 honesty gloss; ATT = P-B2 §6 pp excess not Cohen d; session-regime terciles specified (FIT-session cuts, clip, ties lower) | YES | §0, §5.3, §5.4 |

Re-review reads the amended clauses, not this tick list, as evidence.

Reviewer did not write the freeze. No P-B3 outcome was computed. Frozen P-B2
receipt / JSON were opened only to audit the “unresolved cells” claim. Pins
checked on this checkout: `washout_onset_w1.py` `11ac61de71f0f595`,
`pb_case_decomposition.py` `f42b0566beb60bec`, P-B2 prereg
`043a85d69f76ea86` — match prereg §3. PR #5729 file list is prereg + DEC +
WS/handoff/program-home pointers; no runner, no result JSON, no outcome table.

Subject: `research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md`
at freeze commit `6419ca5ed5744d562b7c22093b52065502f802f3`.
Decision: `DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`.
Governing: `DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`,
`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`, `DNR:KILL-OUTCOME-AUDITION`,
`WS:CN-LIMIT-ALPHA`, `CN-LIMIT-ALPHA-2026-08-14` handoff.

---

## Disposition

**FREEZE AMEND** — Design A as a within-name transition estimand is a lawful
primary and is specified well enough to implement. Design B, the A×B headline
table, and the name-propensity control are **not** safe to run as written.
The freeze is not invalid in the FREEZE FAILS sense (A still answers the
timing question DSC named). It is not FREEZE STANDS: several clauses, if left
in place, let the later session quote occupancy as timing on the exact cells
that created the wave, or implement a “persistence-preserving” null that can
re-create a long-horizon relocation.

`DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`’s reopen path is **not** triggered.
That path required showing A’s floors are structurally unmeetable on DD
*and* that B can be restated as timing without the occupancy-as-timing
misread. This review did not count transitions (forbidden). A-primary stays.
B cannot be restated as timing — that is the point of the amendments.

---

## Scorecard (required questions)

| # | Question | Verdict |
|---|---|---|
| 1 | A silent on persistent DD, B still quoted as “timing”? A×B table un-shoppable? | **FAIL** |
| 2 | B preserves duration / prevalence / persistence, or can it reintroduce a long-horizon shift? | **FAIL** |
| 3 | Name-propensity: vanish-after-persistence ⇒ not timing, with a test that can fail? | **FAIL** |
| 4 | Transition N floor, and UNINFORMATIVE / INSUFFICIENT SUPPORT when A has no flips? | **PASS** |
| 5 | C4-like / washout-carrier / regime timing mislabeled as instrument timing? | **WEAK** |
| 6 | Adversarial battery complete, and each control can fail? | **WEAK** |
| 7 | Scope creep outside the 20 / ChiNext10 / STAR / new footprints? | **PASS** |
| 8 | Rewrite P-B2, or winners-only anatomy as selection? | **WEAK** |
| 9 | P-D “eligible input, not production authority”; no same-session placebo re-shop? | **PASS** (load-bearing text is present; occupancy-as-input needs A3) |
| 10 | Freeze-before-outcomes: result JSON / runner / outcome table in this PR? | **PASS** |
| 11 | Estimand before outcomes? Matching specified enough to implement without shopping? | **WEAK** |
| 12 | Fabricated `known_at` / adjusted-plane W1–W3 / Prophet? | **PASS** |

---

## 1. A silent + B quoted as timing — FAIL

The table tries to forbid the word “timing” on occupancy rows, then hands the
later session three ways to ignore that.

**Wrong-row pointer (load-bearing).** §5.2:

> A NULL on DD onset with B occupancy surviving is a coherent, pre-registered
> outcome (§10 row 2).

§10 row 2 is:

> CERTIFIED_TIMING | NOT_EVALUABLE / INSUFFICIENT … | **CERTIFIED STRUCTURE**
> | `TIMING` | **yes**

The coherent DD outcome the prose describes is row 3 (A NULL, B
CERTIFIED_OCCUPANCY → `OCCUPANCY_NOT_TRANSITION`, timing **no**) or row 4
(A INSUFFICIENT / NOT_EVALUABLE, B CERTIFIED_OCCUPANCY →
`OCCUPANCY_ONLY_A_UNDERPOWERED`, timing **no**). Row 2 is the VZ-style
rescue: A certified, B inert, **timing language allowed**. A later session
that follows the §5.2 citation — the sentence that exists specifically to
pre-register the motivating DD case — is instructed to stamp TIMING on
occupancy-only DD. That is the Q1 attack succeeding by the freeze’s own
cross-reference.

**First-match swallows the contradiction row.** §10 row 1 is
`CERTIFIED_TIMING | any evaluable → TIMING`. Row 8 is `CERTIFIED_TIMING |
NULL, B had df on DD20/DD35/MA200 → UNINFORMATIVE / A_B_CONTRADICT`.
“Any evaluable” includes B NULL. The table does not say first-match,
last-match, or most-specific. First-match never reaches row 8. A certified
+ B null on a long-spell footprint can be sold as TIMING.

**Shared headline.** Occupancy-only and transition-certified cells both
print **CERTIFIED STRUCTURE**. The stamp is the only distinction. P-D
§10.1 then treats “either `TIMING` or either occupancy stamp” as the same
eligible input. Combined with §6.3’s own sentence —

> B asks: … is the observed state-to-outcome **timing** unusual?

— a later session can quote “certified structure” / “state-to-outcome
timing” on A-silent DD without ever using the forbidden word as a stamp.
The A×B table is therefore shoppable.

This is exactly the path DEC rejected B-only for, reconstructed as
A-primary + A-silent + B-speaks.

---

## 2. B persistence preservation — FAIL

§6.1 keeps the multiset of **F=TRUE** spell lengths and the TRUE bar count,
then “fills residual bars with F=FALSE”. It does **not**:

- keep the F=FALSE duration multiset;
- forbid two TRUE spells from abutting (merge → one longer spell, which
  `spell_length_preserved` would then have to fail — or a sloppy runner
  would “preserve” the merged multiset by construction);
- refuse names whose legal placements are a coarse relocation of one or two
  multi-year blocks.

A name with two TRUE spells of a few hundred sessions, longest ≤ 70% of
eligible bars, is **not** PERM-INERT under §6.2. Relocating those blocks
inside the split is a long-horizon feature move with a handful of degrees
of freedom — the transformation `DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`
already proved does not break DD–outcome alignment. B can then reject (or
fail to reject) for the same false-null reason P-B2’s S ∈ {250, 500, 1000}
shift did.

DSC’s named alternatives were (i) within-name **transition** contrasts
(Design A) and (ii) **cross-name assignment** permutations that preserve
each feature’s persistence path. §6.1 is a third object: within-name spell
relocation. For long-spell DD it is the defeated shift in costume unless
coarse-df names are declared inert and TRUE spells cannot merge.

§12 check 7 only asserts the TRUE-length multiset. That does not detect
FALSE-duration destruction or a merge that the placer then treats as the
new target multiset.

---

## 3. Name-propensity test that can fail — FAIL

The law is stated correctly:

> A state relationship that disappears once within-name propensity /
> persistence is handled is **not** timing alpha. (§7.8, §1)

A’s tercile rule can fail (`PROPENSITY_CONCENTRATED` → UNINFORMATIVE). A
itself is a within-name contrast, so a relationship that is only
cross-name will not certify on A. That half is real.

B’s half is vacuous as specified. G6B:

> recompute B after replacing F with F minus the name’s FIT-only
> prevalence (a residual occupancy).

B’s estimator is the **P-B2 matched excess**, which requires a binary
in-state / out-of-state class. For binary F, `F − p_i` is `1 − p_i` on
TRUE bars and `−p_i` on FALSE bars. Any threshold at 0 reconstructs F
exactly (for `p_i ∈ (0, 1)`). The “demeaned” matched excess **is** the
raw excess. G6B then cannot fail. §11.6’s name-constant feature is a
different object (PERM-INERT by construction) and does not rescue G6B on
the real, non-constant footprints.

A check that cannot fail is a defect by the prereg’s own §11 sentence.
Occupancy certification on DD can therefore print `CERTIFIED_OCCUPANCY`
without ever having tested name propensity.

---

## 4. Transition support census — PASS

§9.1 freezes: ≥ 80 distinct-name primary-edge events in FIT (retained
matched), ≥ 30 HOLDOUT, ≥ 40 distinct FIT names, unmatched-treatment
fraction ≤ 50%, single-name share ≤ 40%, prevalence ∈ [0.5%, 99.5%].
Floor miss on N → `INSUFFICIENT_SUPPORT`; undefined contrast →
`NOT_EVALUABLE`; never NULL. §11.1 requires A NOT_EVALUABLE or NULL on a
name-constant feature. UNINFORMATIVE is reserved for instrument defects
(`A_B_CONTRADICT`, `BATTERY`), which is the right split.

Residual: the review did not verify those floors are meetable on DD. The
prereg already treats INSUFFICIENT SUPPORT as a valid ship. No amend.

---

## 5. Carrier / regime mislabeled as instrument timing — WEAK

M4-only → NULL / `REGIME`, not a P-D input. Session-regime matching is
declared; dropping it is diagnostic only. Battery 5 plants a
session-constant. That side is specified.

The hole is the DD series itself. P-B2 §5.3 already carved DD35 out of
`dd_band` / `dur_band` because it **is** the washout-depth series. P-B3
inherits that carve-out (§3, §5.3, §7.4). M3 therefore **cannot fire on
DD35** (“where the carve-out does not already drop it”). DD20 is M0 and
never matches `dd_band`. A CERTIFIED_TIMING stamp on DD is a statement
about the carrier series, not about an instrument beyond the carrier.
§8 M1 will still classify that as “persistent structural state genuinely
changes conditional future-board probability.” True, and easy to quote
as instrument timing. Amend: DD20/DD35 M3 = `NOT_APPLICABLE`; any DD
headline must carry `CARRIER_SERIES` so P-D cannot treat it as incremental
to the washout carrier.

---

## 6. Adversarial battery — WEAK

All six required negative controls are present (§11.1–§11.6), each with a
probe, plus `detected: false` voids the receipt. The list matches the
brief: persistent-state null; planted timing; duration-preserving
permutation of the plant; mutation destroying transition timing;
carrier-only / regime placebo; name-propensity constant.

Weaknesses, not absences:

- §11.1 / §11.5 probe English is inverted (“assert X (must fire)”). A
  later builder can implement the assertion instead of the detection.
- §11.3’s “fall back toward null” inherits §6.1’s merge / coarse-df hole.
  If the permutation can clump length-3 plants into a longer occupied
  block, the plant need not die.
- G6B cannot fail (Q3), so the name-propensity *control on real F* is not
  in the battery — only a name-constant synthetic is.
- No probe that a two-spell multi-year feature remains PERM-INERT or
  NOT_EVALUABLE (the DSC false-null case).

---

## 7. Scope creep — PASS

Exact 20: `{DD20, DD35, MA200, QB, VZ} × {main, chinext20} × {H10, H5}`.
CONF / CB / SECT closed, including chinext20 CONF H10 SUGGESTIVE.
`chinext10` DESCRIPTIVE_ONLY, no inferential resurrection. STAR floor
unchanged, no STAR prereg hidden here. No ninth footprint, pair, triple,
grid, or China Intelligence composite. Chinext20 DD NULLs are in as
companions — that is anti-shopping, not creep.

---

## 8. P-B2 rewrite / winners-only selection — WEAK

P-B2 prereg file is untouched. §10 requires the receipt’s first sentence
to preserve **NO DISCRIMINATOR AT THE PREREGISTERED BAR**. P-B winners-only
anatomy is forbidden as selection (§13). Expected signs and the MA200
EXIT edge are taken from **P-B2’s published signed structure**, frozen so
the later session cannot flip the edge. That is sequential prereg, not a
P-B2 rewrite.

Honesty nit on “unresolved,” from the frozen P-B2 receipt only:

- DD-family indeterminacy and the 11/31 G1–G5 then family-downgrade
  match receipt §5–§6 and DSC. Honest.
- Non-DD placebo rejection 1/144 = 0.69% matches. Honest.
- **chinext20 · H5 passed calibration** (1/48 = 2.08% < 2.5%). QB and VZ
  there are SUGGESTIVE that missed G3/G4/G5, not family-downgraded
  DISCRIMINATORs. §0’s sentence “family-downgraded because they sat in
  (board, horizon) families the DD cells failed” is false for that
  family. Including the cells is still lawful (they are in the 20). The
  gloss must not say they were calibration-blocked.

“§10 row 2” in §5.2 is a P-B3-internal cite error, not a P-B2 rewrite
(see Q1).

---

## 9. P-D implication — PASS, with A3 required

§10.1 is load-bearing and explicit: CERTIFIED STRUCTURE is eligible
**input**, not production authority; P-D must still show incremental
information over Prophet, the washout carrier, **and** name propensity;
NULL is not a P-D input; **do not re-shop another placebo in the same
session**; INSUFFICIENT SUPPORT is not a kill of the search space;
UNINFORMATIVE stops. Gauntlet at promotion. No ranker here.

The remaining leak is that occupancy-only and TIMING share one headline
and one P-D eligibility sentence. Close it with A3. Do not weaken the
no-reshop rule.

---

## 10. Freeze-before-outcomes — PASS

PR #5729 changed five files: the prereg, the DEC, WS-CN-LIMIT-ALPHA, the
2026-08-15 handoff, and the program-home P-B3 row. No
`pb3_*.py`, no result JSON, no outcome table. §15 forbids those in this
session. This review adds only this file and a WS pointer that the freeze
does **not** clear the run.

---

## 11. Estimand and matching — WEAK

Estimands are declared in §1 before any P-B3 number: A = within-name
transition; B = persistence-preserving occupancy association. Labels,
universes, splits, boards, and inherited M0/M1 arms are P-B2 verbatim.
A’s control class, quiet window, non-overlap, deterministic tie-break,
and unmatched-treatment refusal are implementable.

Gaps that force a later session to choose (i.e. shop):

- “ATT-weighted **standardized** difference” vs P-B2’s matched excess in
  pp. P-B2 §6 uses “standardized excess” as a name for that pp difference.
  Say so, or a builder ships Cohen’s d.
- Session-regime terciles: FIT-only cuts applied forward — good PIT —
  but no rule for HOLDOUT values outside the FIT range (clip to edge)
  and no statement that the tercile is over FIT **sessions**, one row per
  session.
- G6B residual occupancy, as in Q3, is not an algorithm.
- §6.1 placement algorithm, as in Q2, is not an algorithm.

---

## 12. known_at / adjusted plane / Prophet — PASS

No `known_at` fabrication path. Propensity terciles and prevalences are
FIT-only, past-only (§7.8, §12.12). Session-regime cuts are FIT-only
applied forward. Features at T use information through T (§5.3).
`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` is the first governing ruling;
no W1–W3 artifact is cited as evidence. Substrate is `data/china_stocks_raw`
through pinned W-P0 / P-B imports. Back-adjusted basis is stamped as an
inherited limit, not laundered as exact-plane authority.
`DNR:KILL-OUTCOME-AUDITION` is in §13. Prophet weights,
`engine/china_board_rank.py`, featured admission, and `cn_prophet_v4` are
forbidden. No production score.

---

## Required pre-outcome amendments

These are numbered so the later receipt can cite them as A1–A8 if they
land before any outcome. Quote is the frozen text. Replacement is the
minimum that closes the attack. Do not “improve” signs, cells, floors,
or the A-primary assignment while making these edits.

### A1 — Kill the §5.2 → §10 row 2 pointer

**Quote (§5.2):**

> A NULL on DD onset with B occupancy surviving is a coherent,
> pre-registered outcome (§10 row 2).

**Replace with:**

> A NULL on DD onset with B occupancy surviving is a coherent,
> pre-registered outcome (§10 row 3: `OCCUPANCY_NOT_TRANSITION`).
> A INSUFFICIENT_SUPPORT / NOT_EVALUABLE on DD with B occupancy
> surviving is §10 row 4 (`OCCUPANCY_ONLY_A_UNDERPOWERED`). Neither
> row may use timing language. §10 row 2 is reserved for
> CERTIFIED_TIMING with B inert (short-spell F) and must not be cited
> as the DD occupancy fallback.

### A2 — §10 matching rule, most-specific wins

**Quote (§10, immediately before the table, or as a new sentence after
the table header):** the table is a list of rows with no collision rule.

**Add:**

> Apply the **most specific matching row**. A row that names a stamp,
> a footprint class (long-spell vs short-spell), or an M4/battery
> override beats a row that says “any evaluable.” First-match is
> forbidden. In particular, row 1 must read `CERTIFIED_TIMING | B
> CERTIFIED_OCCUPANCY or B not computed` and must not include B NULL;
> B NULL + A CERTIFIED_TIMING on DD20/DD35/MA200 is only row 8
> (`UNINFORMATIVE` / `A_B_CONTRADICT`).

### A3 — Occupancy may not share the TIMING headline or the P-D sentence

**Quote (§10 table, rows 3–4 headline column):** `CERTIFIED STRUCTURE`
on occupancy stamps. **Quote (§6.3):** “state-to-outcome **timing**.”
**Quote (§10.1):** “CERTIFIED STRUCTURE (either `TIMING` or either
occupancy stamp) → eligible INPUT.”

**Replace with:**

- Headlines: `CERTIFIED_TIMING` → **CERTIFIED TIMING**; occupancy
  stamps → **CERTIFIED OCCUPANCY**. Do not print CERTIFIED STRUCTURE
  on an occupancy-only cell.
- §6.3 last sentence: “is the observed occupancy-to-outcome
  **association** unusual?” — delete “timing.”
- §10.1: TIMING-stamped cells are eligible P-D **timing-family**
  inputs. Occupancy-stamped cells are eligible only as named occupancy
  covariates, and P-D must still beat name propensity and the washout
  carrier. A later session that quotes occupancy as timing has
  violated this prereg regardless of headline.

### A4 — B is a no-merge spell-sequence shuffle

**Quote (§6.1 bullet list).**

**Replace the placement rule with:**

> One draw, independently inside FIT and inside HOLDOUT, **shuffles the
> existing sequence of contiguous TRUE and FALSE spells** on that
> name × split (or an equivalent placement that (i) keeps the multiset
> of TRUE spell lengths, (ii) keeps the multiset of FALSE spell
> lengths, (iii) keeps the TRUE bar count, (iv) places a ≥ 1-bar FALSE
> separator between every pair of TRUE spells so they cannot merge,
> (v) refuses a TRUE spell across a board-key change, (vi) refuses F
> on a bar that fails F’s measurability mask). Residual-fill that
> only preserves TRUE lengths is forbidden — it can clump TRUE spells
> into a longer occupied block and reintroduce a long-horizon shift.

Add §12 checks: `false_spell_length_preserved` and `no_true_spell_merge`.
Probes: jitter a FALSE length; force two TRUE spells to abut.

### A5 — Coarse-df names are PERM-INERT

**Quote (§6.2):** inert if `< 2` TRUE spells or longest TRUE spell
`> 70%` of eligible bars.

**Add (do not relax the existing two bullets):**

> A name is also PERM-INERT when it has fewer than **3** F=TRUE spells
> in that split, **or** the two longest TRUE spells together cover
> `> 70%` of eligible bars, **or** the number of distinct legal
> placements of its TRUE-spell multiset under A4 is `< 20`. Two
> multi-year blocks are a shift, not a persistence-preserving null.
> Count these names. If retained non-inert names carry `< 50%` of the
> cell’s F=TRUE positive episodes, B is `NOT_EVALUABLE` (already
> stated) — that refusal is expected on DD and is not a B-null and
> not certified occupancy.

### A6 — G6B must be a test that can fail

**Quote (§7.8 / §9.3 G6B):** “replacing F with F minus the name’s
FIT-only prevalence.”

**Replace with one frozen algorithm (do not leave a menu):**

> **G6B (name-path assignment).** Inside each board × split, reassign
> each retained name’s **entire** F path (the A4 spell sequence, un-
> shuffled) to another retained name, uniformly, without replacement,
> independently of outcomes. Recompute the P-B2 matched excess on the
> reassigned paths. N_ASSIGN = 2000, same seed stream offset from
> N_PERM. If raw B rejects at G2B and the assignment-null one-sided p
> on FIT is `> 0.10`, the cell is `NAME_PROPENSITY` and B status is
> NULL. This is DSC’s cross-name assignment permutation. It is not
> `F − p_i`. `F − p_i` thresholded at 0 reconstructs binary F and is
> forbidden as a gate.

§11.6 stays (name-constant must not certify). Add a probe: on the
§11.2 planted feature, G6B must still reject (the plant is timing, not
name identity). On the §11.6 constant, G6B / B must not certify.

### A7 — DD is the carrier series

**Add to §8 / §10 stamps:**

> M3 is `NOT_APPLICABLE` on DD20 and DD35 (inherited carve-out: the
> footprint *is* the `dd250` series). Any DD headline that is not
> NULL / INSUFFICIENT / UNINFORMATIVE carries stamp `CARRIER_SERIES`
> in addition to TIMING or OCCUPANCY. P-D may not treat a
> `CARRIER_SERIES` cell as incremental information over the washout
> carrier.

### A8 — Honesty gloss on chinext20 · H5

**Quote (§0):** “family-downgraded because they sat in (board, horizon)
families the DD cells failed.”

**Replace with:**

> MA200 / QB / VZ were placebo-clean at the cell level (non-DD
> rejection 1/144 = 0.69%). On main · H10, main · H5, and chinext20 ·
> H10 they sat inside families the DD cells failed, so P-B2’s §6.3
> consequence downgraded every DISCRIMINATOR in those families.
> **chinext20 · H5 passed calibration** (1/48 = 2.08%); QB and VZ
> there are SUGGESTIVE that missed G3/G4/G5, not family-downgraded
> DISCRIMINATORs. They remain in the 20 as the frozen board × horizon
> companions, not because calibration blocked them.

Also replace “ATT-weighted standardized difference” (§5.4) with
“ATT-weighted matched difference in P(`fb_H`), in percentage points,
the P-B2 §6 excess; not a Cohen d.” And specify session-regime
terciles: one U1-fraction per FIT session; HOLDOUT / AUDIT values clip
to the FIT min/max cut; ties at a cut go to the lower tercile.

---

## Residual risks (do not block the amend)

- A’s ≥ 80 / ≥ 30 transition floors may be thin on multi-year DD. That
  is already a pre-registered INSUFFICIENT SUPPORT, not a defect.
- VZ `DWELL_PRE = 2` is a different object from the other footprints;
  the coincident stamp already travels. Do not lengthen it after N.
- B has no era-sign gate. Accepted, as written, for thin DD spells.
- Holm inside (board, horizon) is reference-only. Do not promote it
  after results.
- Survivor large-cap slice and back-adjusted basis remain inherited
  limits on every future receipt. Exact-plane re-measurement is a
  different wave.
- This review did not implement, dry-run, or peek at any P-B3 statistic.

---

## What happens next

A later session (not this one) writes A1–A8 into the prereg as
**numbered pre-outcome amendments**, keeps A primary / B corroborative,
and does not add a runner in the same act if the amend PR is still the
freeze PR. Independent review of the amended text is cheap and should
happen. The certification run is a third session. P-D stays closed.

*Reviewer: independent adversarial pass on PR #5729, 2026-08-15.
No certification was run.*
