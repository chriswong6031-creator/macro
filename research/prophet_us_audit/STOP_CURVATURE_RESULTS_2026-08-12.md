# Stop-curvature context study — results (2026-08-12)

> **ADJUDICATED 2026-08-12 by the commissioning main loop (ANTICIPATION lane).** Charter §7's
> mandatory Opus reviewer pass is complete, its four ship-blocking findings are incorporated,
> and the repairs were verified at source rather than accepted on report. **Verdict: the
> five-form family is CLOSED on a definition-validity null — no promotion, no engine change,
> no rank/size consequence, and no display copy follows.** The display-tier watch surface
> keeps shipping under §6.6 word budgets with plain-word null disclosure, per charter §0.
>
> **What the null is, precisely.** The chartered family never reached the tape: no form could
> see the operator's own motivating receipts, so each was disqualified ex ante by G5 and
> correctly received no outcome row. That is a statement about the CONSTRUCTIONS, not about
> the market — the load-bearing §R9f fact (34.9% of stop confirms land within ±2 sessions of
> the ±10-session local low vs a 15.7% null) is untouched and the search space stays open.
> **"Not found yet" ≠ "does not exist."** The open question this hands forward is not "which
> form next" — anything outside the enumerated five is a NEW charter — but what the operator
> was actually reading when they described "arching up off the histogram low", because at
> both exemplars the 1D histogram was making a fresh low on the confirm bar itself, under
> both this house's serialization and textbook MACD(12,26,9).
>
> **On the withdrawn magnitude claim (§4).** The main loop answers §9.1 **no**: R4b's kill
> stands, its published −11.4pp anchor stands unchanged, and this study corrects neither. The
> three lens rows are unregistered exploratory reads that license nothing. The magnitude
> question is a live ore-ledger row requiring its own pre-registration — weighting rule, lens
> definition, and CI declared in advance — before it may touch a published number. Recording
> why this mattered: the first draft's headline was itself an instance of the trap this
> program memorialized in the parent's §RT, reached the same way (one estimator, chosen after
> the fact, on a substituted lens). The house rule earned here is that a promotion gate must
> not be settled by an author's choice among defensible estimators, which is now enforced in
> the script — G3's quintile leg requires all four to clear.
>
> **What round 1 changed.** The **core G5 result survived unchanged** — the reviewer
> recomputed the exemplar arithmetic from the raw parquet without importing this study,
> confirmed both dates resolve to the correct break bars, and proved the trailing-min
> exclusion rule is verdict-neutral (K1 FALSE across w ∈ {10,15,21} × {excl, incl} at both
> exemplars). Four repairs were required and are applied: a **withdrawn magnitude claim**
> (§4), a **factual correction about K2** (§0, §3.2, §7.1), **five surviving mutations** now
> covered (§6), and a **hard abort** replacing a silent "disqualified" on an unresolvable
> exemplar (§2.5). Every withdrawal is marked in place rather than quietly deleted.

**Charter (binding):** `research/prophet_us_audit/STOP_CURVATURE_CHARTER_2026-08-11.md`
**Parent:** `research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md` (§R4/R4b, §R9, §RT)
**Script:** `research/prophet_us_audit/stop_curvature_study.py`
**Frozen tables:** `research/prophet_us_audit/stop_curvature_study_results.json` (`RC.*`)
**Guard suite:** `research/prophet_us_audit/test_stop_curvature_study.py` (22 tests)

Every number below is emitted by the script and reproducible with one command. Nothing is
hand-copied:

```
python3 research/prophet_us_audit/stop_curvature_study.py
```

---

## §0 Headline

**All five chartered forms (K1–K5) fail the G5 exemplar-coverage gate and are disqualified
ex ante. No outcome row was read for any of them.**

They do not all fail for the same reason, and the differences are the useful part:

- **K1 and K3** fail on the **level** fact: both require the histogram to sit **above** its
  trailing minimum, and at both motivating confirms the 1D MACD-RSI histogram was making a
  **fresh trailing low** — it was not arching up off one.
- **K2 does not reference the trailing minimum at all.** At **May-19 its curvature condition
  PASSES** (mean second difference **+0.027014** ≥ 0); what disqualifies it is the
  anti-staircase clause (3 negative first differences, limit 1). At Jan-07 both clauses
  fail. So second-difference curvature was *not* refuted by the fresh-low fact at the
  flagship exemplar — it was refuted by the monotonicity side-condition the charter attached
  to it.
- **K4 and K5** fail on the **3D leg at Jan-07** (`m3_bull` FALSE), not on the histogram at
  all. Both cover May-19.

This is a **definition-validity null, not a tape null.** The charter's forms were not tested
against the market and found wanting; they were tested against their own motivating receipts
and found not to describe them. The distinction matters for what happens next (§7).

---

## §1 Acceptance gates — verdicts

| # | Gate | Verdict |
|---|---|---|
| 0 | **Parity gate** (recomputed series reproduces the replay's stored columns) | **PASS — 12,940/12,940 on BOTH legs**: `hist_rising` (ordering) and `close` (level) |
| 1 | **G5 runs first**, ordering auditable in the script's own output | **PASS** — outcomes physically sealed; `vault.reads` snapshot at G5 close = 0 |
| 2 | **PIT leak test** that can FAIL | **PASS** — all 12,940 rows, worst deviation `0.000e+00` |
| 3 | **R9d battery** (fixed −8%, 2ATR, entry-distance quintiles) | **RUN — all three**, but on the control lens and as **UNREGISTERED EXPLORATORY** (§4); no chartered form survived G5 to be tested, and the quintile lens is a **substitute** for the charter's entry-distance lens |
| 4 | **Coverage floor ≥5%** | Evaluated per form (§5); K2 fails at 0.59%, K1/K3/K4/K5 clear |
| 5 | **G2/G3/G4 printed per form** | **NOT EVALUATED for any form** — every form is disqualified at G5, and the charter forbids reading an outcome row for a disqualified form |
| 6 | **Nulls printed, not hidden** | Five ore-ledger rows in §3; no variant hunting (§7) |
| 7 | **STLD-excluded sensitivity row** | Implemented in `RC.primary`; emits no rows because no form reached the primary table |
| 8 | **Substrate bounds restated** | `RC.substrate` (§8) — no re-windowing |
| 9 | **Every number reproducible** | Yes — single command above. **One exception, flagged in place**: the +0.5-shift demonstration in §2.1 is a red-team construction, not a script output (independently reproduced, marked where it appears) |

Gate 5 is the one place this study departs from the shape the brief anticipated, and the
departure is the charter's own design rather than missing work: charter §1 says a form that
misses either exemplar "is disqualified **ex ante** — before its outcome row is read", and
the brief repeats it ("gets no outcome row"). With all five disqualified, `RC.primary`,
`RC.windowgrid`, `RC.forward` and `RC.r9d` are structurally empty. They are emitted anyway,
with a `(none)` row, so the absence is visible rather than silent.

---

## §2 What the gates proved before any outcome was read

### 2.1 Parity — `RC.parity`

The stops frame carries point-in-time flags only, so K1–K3 required the 1D histogram path to
be recomputed. It was recomputed through the parent's own loader
(`early_admission_bakeoff.load_ohlc`) and the same engine primitive `NameData` used
(`engine.signal_quality._rsi_macd`), against the same frozen store the parent ran on
(`/Users/chriswong/actions-runner-2/_work/macro/macro/data/...`, unchanged since 2026-08-10).

| leg | compared | matches | verdict |
|---|---|---|---|
| 1D MACD-RSI histogram → `hist_rising` (**ordering**) | 12,940 | **12,940 (100%)** | **PASS** (blocking) |
| price series → stored `close` (**level**, worst \|Δ\| `0.000e+00`) | 12,940 | **12,940 (100%)** | **PASS** (blocking) |
| 3D `macd ≥ sig`, **session-anchored** → `m3_bull` | 12,940 | **12,940 (100%)** | matches stored |
| 3D `macd ≥ sig`, **first-timestamp phased** proxy → `m3_bull` | 12,940 | 12,859 (99.37%) | 81 rows diverge |

**Why two blocking legs.** `hist_rising` is a strict-*ordering* predicate — invariant under
any positive affine transform of the histogram — so on its own it pins the replay's ordering
but not its levels, while K1 (`hist < 0`, `hist > tmin`) and K3 (normalized recovery) are
level-dependent. A uniformly shifted histogram would pass the ordering leg untouched and
still move K1's coverage: a +0.5 shift takes K1 from **22.85% → 20.61%** while `hist_rising`
still reproduces on **12,786/12,786** rows. The `close` leg supplies the level identity the
ordering leg cannot; together they establish series identity, and the first draft
over-claimed by resting on the ordering leg alone.

*(Red-team R5. The +0.5 figure is a demonstration constructed by the reviewer, not an output
of this script — it is reproduced above from an independent recomputation on the same frame,
and is the one number in this document that a plain re-run does not print.)*

### 2.2 K4 is NOT deferred — and the charter's phase premise needed correcting

Charter §2 flagged K4 as possibly deferred because "3D grids currently inherit the
confluence_v2 first-timestamp phase defect", and the build brief assumed the stored `m3_bull`
column was the phased one. **Neither holds macro-side.** `engine/signal_quality._tf_grid`
has bucketed on the absolute session calendar since `ANCHOR_ERA=sq-abs-session-2026-08-06`
(`engine/session_anchor.py`), so the stored `m3_bull` **already is** the session-anchored
recomputation — proved, not assumed, by row 2 above (independent rebuild, 12,940/12,940).

The R4.hl_phase defect is real but lives in charting-app's `confluence_v2`, which is what
produces the *confirm events*, not this column.

Row 4 is a **proxy, not a measurement of that defect**. The real defect is a pandas
`resample` whose business-day bin edges anchor to the series' first timestamp; this study
rebuilds the leg with positional bucketing (`position_in_this_series // 3`). The two share
the property under test — the bucket a date lands in depends on the caller's leading history
— but the pandas version *also* mis-splits buckets spanning market holidays, which
positional bucketing cannot reproduce. So **81/12,940 rows (0.63%) is a lower-bound
indication of the phasing class' footprint on this frame, not a quantification of the
charting-app defect**; measuring that requires importing charting-app's own module, which is
out of scope here. What the proxy does establish is that the two phases **agree at both
exemplars**, so the phase question is **not material to K4's verdict** on this frame —
which is what charter §4.6 asked for either way. (Red-team R5; the first draft said
"quantifies it for the first time", which over-claimed.)

### 2.3 PIT — `RC.pit`

Two legs, both able to fail, both run before any table froze:

| leg | scope | violations | worst deviation |
|---|---|---|---|
| (a) 1D histogram truncation identity over `[T−23, T]` | **ALL 12,940 rows** | 0 | `0.000e+00` |
| (b) 3D bucket-last knowability ≤ confirm bar | ALL 12,940 rows | 0 | — |

Leg (a) recomputes the histogram on `close[:T+1]` and demands the full-series values match;
any step reaching past `T` moves them. Leg (b) demands every 3D value's knowability session
(bucket **last**, never the open label) sit at or before the confirm bar. The guard suite
plants both defects and requires both legs to red (§6).

### 2.4 Ordering — `RC.g5.ordering`

The outcome columns (`near_low_stop`, `gap`, `argmin_date`, `fwd10`, `fwd21`) are **removed
from the working frame** at load and held in an `OutcomeVault` that raises `OutcomeSealError`
on any read before G5 concludes. Reads before unseal: **0**. The seal caught a real violation
during the build — the frame-reconciliation table was printing the 34.9% base rate before G5,
and a base rate is an outcome like any other. That table now emits after the unseal.

The receipt prints a **snapshot of `vault.reads`** taken at G5's close, not a hard-coded
zero. The enforcement was always genuine; the earlier receipt was tautological, which is the
one thing a receipt may never be.

### 2.5 An unresolvable exemplar ABORTS — it is not a G5 failure

G5 carries this study's entire load, and two states that mean opposite things looked
identical in the first draft: *"the lens does not see this chart"* (the finding) and *"we
could not find this chart"* (a broken run). An unresolved exemplar became `None`, fell
through `all(...)` as False, and would have printed **"DISQUALIFIED ex ante"** — so a store
gap, a ticker rename or a shifted holiday could manufacture precisely this five-form null
with no diagnostic.

It now raises `ExemplarUnresolved` before any form is evaluated. This did not fire on this
run — every exemplar cell is a genuine boolean and the receipts carry real numerics — but
absence of evidence must never be able to render as evidence of absence in the gate the
whole result rests on. Covered by `test_g5_aborts_when_an_exemplar_cannot_be_resolved`.
(Red-team R4.)

---

## §3 G5 — the finding, and the five ore-ledger rows

### 3.1 The gate — `RC.g5`

| form | STLD 2026-05-19 | STLD 2026-01-07 | G5 |
|---|---|---|---|
| K1 off-the-trailing-min (`w=15`) | FALSE | FALSE | **FAIL** |
| K2 curvature proper (`m=3`) | FALSE | FALSE | **FAIL** |
| K3 normalized recovery (`θ=0.30, w=15`) | FALSE | FALSE | **FAIL** |
| K4 3D-bull at confirm (session-anchored) | TRUE | **FALSE** | **FAIL** |
| K5 = K1 OR K4 | TRUE | **FALSE** | **FAIL** |

### 3.2 Why — `RC.g5.receipt`

| ticker | confirm | hist[T] | hist[T−1] | hist[T−2] | tmin(w=15, excl. T) | reading |
|---|---|---|---|---|---|---|
| STLD | 2026-05-19 | −2.6464 | −2.2161 | −1.9723 | −2.2161 | **at/below — fresh low** |
| STLD | 2026-01-07 | −1.5277 | −1.0647 | −1.1056 | −1.4591 | **at/below — fresh low** |
| STLD | 2026-06-18 *(narrative only)* | −2.5989 | −1.4289 | −1.0450 | −1.4289 | at/below — fresh low |

**K1 and K3** require the bar **above** its trailing minimum; at both exemplars it is below.
**K4** is TRUE at May-19 (the half of the receipt the charter quoted) but **FALSE at
Jan-07** — the charter's §1 table never claimed otherwise; it gave a 3D reading only for
May-19. **K5** inherits K4's Jan-07 miss because K1 misses there too.

**K2 is the exception, and it is the most useful row in this artifact.** K2 never references
`tmin` — it is a pure second-difference test with an anti-staircase side-condition — so the
fresh-low fact does not touch it:

| exemplar | mean 2nd difference | curvature clause | negative 1st diffs (limit 1) | staircase clause | K2 |
|---|---|---|---|---|---|
| 2026-05-19 | **+0.027014** | **PASSES** | 3 | FAILS | FALSE |
| 2026-01-07 | −0.134176 | fails | 2 | FAILS | FALSE |

So at the flagship exemplar, **second-difference curvature is present and the charter's own
monotonicity side-condition is what rejects it.** "Curvature proper passed at May-19 and
died on the staircase clause" is a materially different handover fact from "everything died
on the fresh low", and a successor charter that inherited the latter would wrongly conclude
second-difference curvature had been tested and refuted there. (This correction came from
the red-team; the first draft of this doc stated the wrong version. It is now pinned by
`test_k2_dies_on_the_STAIRCASE_clause_at_may19_not_on_the_fresh_low`.)

Two details worth the reviewer's attention:

- **No parameter cell rescues any form.** `RC.grid` prints the full grid (K1 `w∈{10,15,21}`,
  K2 `m∈{3,5}` under **both** readings of the charter's ambiguous "over the last m bars",
  K3 `θ∈{0.15,0.30} × w∈{10,15,21}`, K4 both phases, K5). **Every cell reads FALSE at both
  exemplars** except the K4/K5 cells, which read TRUE at May-19 and FALSE at Jan-07. This is
  reported as a property of the enumerated grid, not as a search — no cell is promotable
  regardless (charter §4.4).
- **The cells that fire on an STLD exemplar mostly fire on the wrong one.** `RC.grid`'s
  narrative column shows K1 at `w=21` TRUE at **Jun-18** — the stop that worked (−8.9%
  fwd10) — while K1 is FALSE at both bottom prints. K4 and K5, the two forms that *did*
  cover May-19, also fire at Jun-18. Charter §1 tunes no lens to reject Jun-18 and
  discrimination is what §3's outcomes would have measured, so this decides nothing on its
  own; it is printed because a reviewer will look for it and should not have to recompute it
  by hand.

### 3.3 Definition-validity probe (unregistered) — is this about the series, or the bar? — `RC.g5.crosscheck`

If every enumerated form misses, a successor charter needs to know whether the miss is a
property of the house MACD-RSI series (`_rsi_macd` = MACD of RSI) or of the daily bar itself.
Textbook MACD(12,26,9) on close, at the same three dates:

| ticker | confirm | hist[T] | tmin(w=15, excl. T) | reading |
|---|---|---|---|---|
| STLD | 2026-05-19 | −2.5787 | −1.9715 | at/below — fresh low |
| STLD | 2026-01-07 | −1.0317 | −0.8596 | at/below — fresh low |
| STLD | 2026-06-18 | −2.8064 | −1.0714 | at/below — fresh low |

**The rival serialization behaves the same.** The daily histogram — either flavour — was at a
fresh low at both motivating confirms.

**This is a probe, not a neutral receipt** — its "reading" column applies **K1's own**
above-trailing-min test to a series the charter never registered, so it has a verdict shape
and it is unregistered. It reads no outcome column and classifies no cohort, and it
**licenses nothing and pre-decides nothing**. Its one job is to hand a successor charter the
level fact — both serializations sat at a fresh low here — before it picks a substrate.
Actually testing this series requires its own pre-registration. Note also that this probe
speaks only to K1/K3's level axis: it says nothing about K2, which reads no level at all
(§3.2). (Red-team R5; the first draft called this a neutral receipt.)

### 3.4 Ore-ledger rows (the family's entry; the constructions close, the family stays open)

| form | primary cell | coverage | G5 | disposition |
|---|---|---|---|---|
| **K1** off-the-trailing-min | `w=15` | 22.85% (2,921 / 239 names) | FAIL (F/F) | CLOSED — cannot see either exemplar |
| **K2** curvature proper | `m=3` | 0.59% (75 / 64 names) | FAIL (F/F) | CLOSED — and would have failed G1 anyway (0.59% < 5%, the named R4b trap) |
| **K3** normalized recovery | `θ=0.30, w=15` | 9.06% (1,158 / 237 names) | FAIL (F/F) | CLOSED — cannot see either exemplar |
| **K4** 3D-bull carry | session-anchored | 75.55% (9,660 / 240 names) | FAIL (T/F) | CLOSED — covers May-19, misses Jan-07 |
| **K5** K1 OR K4 | `w=15` OR 3D-bull | 83.93% (10,731 / 240 names) | FAIL (T/F) | CLOSED — inherits K4's Jan-07 miss |

Coverage is lens geometry, not tape: it is what the form *sees*, not what happened after. It
is therefore printed for disqualified forms without violating the ex-ante rule.

---

## §4 Risk-equalization battery — `RC.r9d.control`

Charter §4.2 calls this "where the verdict lives", and the brief requires all three lenses.
With no chartered form surviving G5 there was nothing new to equalize, so the battery was
re-pointed at the parent's **already-published** R4b strict split (`hist_rising`).

**Status of this block — read before the numbers.** The **RAW row is machinery validation**
and carries weight. The **three lens rows are UNREGISTERED EXPLORATORY**: charter §4.2
registered this battery to test a *curvature* lift, not to re-read `hist_rising`, so they are
three unregistered outcome reads on the frozen frame. **They license nothing and correct no
published number.**

| lens | TRUE near-low% | FALSE near-low% | spread | retained | status |
|---|---|---|---|---|---|
| **RAW** (real structure stops) | 23.64% | 35.02% | **−11.38pp** | 1.00× | **machinery validation** |
| A — fixed −8% (n=18,640 synthetic) | 23.17% | 35.20% | −12.03pp | +1.06× | unregistered |
| B — 2×ATR14 (n=38,195 synthetic) | 21.48% | 30.28% | −8.81pp | +0.77× | unregistered |
| C — break-depth quintiles | — | — | **estimator-dependent, see below** | — | unregistered |

**1. The battery is live.** Its RAW row reproduces the parent's published R4b figure
independently and to the decimal (−11.38pp vs −11.4pp published; 23.64% vs 23.6%) from a
separately recomputed histogram. A battery that could not reproduce a known number would be
worth nothing on an unknown one. This row is legitimate and stands.

**2. The magnitude question is OPEN — an earlier draft of this doc claimed it was settled,
and that claim is WITHDRAWN.** The withdrawn claim was that "two-thirds of R4b's deficit is
stop-width arithmetic", resting on lens C reading −3.80pp (0.33×). Four independent problems,
each sufficient on its own:

| # | problem | evidence |
|---|---|---|
| i | **Estimator artifact.** −3.80pp is the *unweighted* mean of the *kept* cells, and it is the single most extreme of four defensible estimators. | `RC.r9d.control.estimators`: kept/unweighted −3.80 (0.33×), kept/**cohort-weighted −6.34 (0.56×)**, all/weighted −7.62 (0.67×), all/unweighted −8.02 (0.70×). Three of the four read **"survives this lens"** under this study's own G3 threshold. |
| ii | **Wrong lens.** Charter §4.2 specifies **entry-distance** quintiles; the parent bins on `entry_vs_low` ("stop DISTANCE held roughly fixed"). This binned on **break depth** at the trigger bar — not stop width — so "stop-width arithmetic" misattributed what was held fixed. The substitution was disclosed; the label was not. | `early_admission_bakeoff.py:1222-1230` |
| iii | **Over-control.** Break depth is outcome-correlated: cell near-low rate falls monotonically **42.53% → 36.88% → 36.53% → 31.99% → 26.67%**. A hard break is mechanically likelier to *be* the window low, so conditioning on it strips label variance from every cohort, real or spurious. | `RC.r9d.control.cells`, right-hand column |
| iv | **No uncertainty, and it lands inside the published interval.** The parent publishes −11.4pp **[−19.2, −2.8]**. Every estimate (−3.80 … −8.02) sits *inside* that interval. No CI was computed; the kept cells hold 94 of 110 TRUE events, and the two dropped cells (q0 −20.38pp n=9, q1 −8.33pp n=7) are the two **most negative**. | `RC.r9d.control.cells` |

Also: lenses A and B retain 1.06× and 0.77× — both read "survives". Under the charter's own
G3 the control scores 2/3, which is a **G3 FAIL, not a demonstration that the deficit is
arithmetic**.

**Adjudicated position.** The R4b **kill stands** — the sign never flips across any lens or
estimator, and R4b's rarity (0.9%) and forward-tape legs are independent of all of this. Its
**magnitude is NOT corrected**: the charter's −11.4pp anchor stands unchanged. Whether the
stop-distance channel inflates it is an **open question needing its own pre-registration**
(weighting rule, lens definition, and CI declared in advance). That is an ore-ledger row, not
a correction.

Lens A/B anchors are disclosed translations, not charter terms: the parent's fixed-% and ATR
stops were anchored to an episode *entry*, and this frame has no entries, so they anchor to
the trailing 21-session max close.

---

## §5 Coverage and grids

`RC.coverage` and `RC.grid` print in full. Coverage on the pre-declared primary cells:
K1 22.85%, K2 0.59%, K3 9.06%, K4 75.55%, K5 83.93%; unavailable rows: **0** for every form
(no window ran short on this frame). Note K4/K5 sit at 76–84% coverage — a lens that fires on
four of five stops is close to a description of the base rate, which is context a reviewer
should hold when reading any future 3D-carry proposal.

Frame reconciliation (`RC.frame`), printed so nothing is silently re-windowed:

| frame | n | names | near-low% |
|---|---|---|---|
| all replayed confirms | 12,940 | 242 | 35.02% |
| **R4b frame (`full_window` & non-addon) — PRIMARY** | **12,786** | **240** | **34.92%** |

The R4b frame is the one the parent's 34.9% base, its month-cluster CIs and its 110/12,786
strict-form coverage were all read on; every gate here is read on it.

---

## §6 Guard suite — the gates can fail

`test_stop_curvature_study.py`, 22 tests, wired into the existing `prophet US audit guards`
step (no new CI job). It is a mutation suite: each of this study's self-reporting gates has
its claimed defect planted, and must go red.

- parity gate reds on one flipped stored flag, and on an unresolvable row (never a silent drop)
- PIT leg (a) reds on a planted centred (forward-looking) feature — the parent's own retraction class
- PIT leg (b) reds on a 3D state stamped knowable after its bar
- `OutcomeVault` raises before unseal; a refused read is not counted as a read
- the two 3D grid phases are pinned as genuinely different computations, so §2.2's
  reconciliation is not a guaranteed zero

**The suite's first version over-claimed, and the correction is worth recording.** It said
G5 was "pinned in the PASS direction". It was pinned all-TRUE and all-FALSE — and `all` and
`any` agree on every uniform input, so mutating the gate's `all(...)` to `any(...)` left the
suite green. That mutation is not cosmetic: **K4 and K5's real verdicts are MIXED** (TRUE at
May-19, FALSE at Jan-07), so under `any` both clear G5, take outcome rows, and this study's
headline inverts to "two forms proceed to the tape". Four further mutations also survived —
`MIN_CELL_N` 20→0, `G3_LIFT_RETAINED` 0.5→0.0 (the entire R9d battery had zero coverage),
and `NEAR_TOL_PRIMARY` 2→5 / `K1_W_PRIMARY` 15→3 (the tests read the constants they checked,
so they followed the mutation).

All five are now covered and verified red: the mixed-verdict case is pinned, the battery has
its own tests, and the pre-declared cells are asserted against **literals** transcribed from
the charter text. The general lesson, which generalizes past this file: *a mutation survives
when every test feeds the code inputs on which the mutant and the original agree.*

Synthetic frames only; the real-store receipts are `skipif`'d on the absence of `data/` and
have never-skipping synthetic twins, matching the `test_price_ladder.py` pattern.

---

## §7 What this licenses, and what stays open

**Licenses nothing.** No promotion, no mechanical effect on stop handling, no rank/size
consequence, no engine change. Charter §0's display-tier "flush watch → re-entry watch"
surface ships under §6.6 word budgets regardless of this verdict and now carries the honest
null.

**The family stays open.** "Not found yet" ≠ "does not exist" (house epistemics law). What
closed is five specific constructions, on one axis: they do not describe their own motivating
receipts. What did **not** happen here — deliberately — is any search for a form that would
pass. Charter §2's last line makes any form outside the enumerated five a NEW charter, and
the brief forbids hunting for a passing variant. None was run.

For whoever writes the successor charter, the load-bearing facts this study can hand over:

1. The daily MACD histogram (house MACD-RSI **and** textbook 12/26/9) was at a **fresh low**
   at both motivating confirms. Any successor form built on the daily histogram's *level*
   relative to its own recent low — K1 and K3's axis — will miss the same two receipts.
   **This does NOT extend to second-difference curvature:** K2 reads no level, its curvature
   clause **passes** at May-19 (+0.027014), and it fails there only on the charter's
   anti-staircase side-condition (§3.2). A successor charter that wants to test curvature
   proper should treat the side-condition, not the fresh-low fact, as the thing that
   rejected it — and note that K2's primary cell also fires on only 0.59% of confirms, so
   the side-condition is what makes it a rare lens.
2. The 3D leg carries May-19 and not Jan-07, so no 3D-bull-at-confirm construction covers
   both either.
3. The parent's load-bearing fact is untouched by all of this: **34.9% of confirms mark local
   lows vs a 15.7% random-session null** (2.2×). The product question — *which* stops those
   are, knowably, at the confirm close — remains open and unanswered.
4. An honest possibility the reviewer should weigh: the operator's visual form may not be a
   1D-histogram construction at all. Nothing here establishes that, and this study does not
   propose a replacement — that is the successor charter's job, and the receipts above are
   what it should start from.

---

## §8 Substrate bounds (restated, parent N4–N6) — `RC.substrate`

- Price window: the ohlcv store's ~2014+ coverage.
- Pre-store events dropped: **18,137 C0 / 7,202 C2** — dropped, **never relocated**.
- Exposure: **2,658.7 name-years**.
- Survivorship: 241-name deep-history store universe; names that delisted before the store
  existed are absent, so outcome columns carry survivorship tint. Printed, not hidden.
- Breadth features are **not** used here, so the post-2023 basket bound does not bind.
- 3D anchor era: `sq-abs-session-2026-08-06`.
- This study re-windows nothing. Frame, base and null are the parent's.

**Disclosure (charter §3):** this is one pre-registered pass on already-frozen tape that has
been outcome-read by R4/R8/R9 for *other* lenses. The curvature family had never been
auditioned on it, and after this pass it still has not been — the family was stopped at the
definition gate, before the tape. The confirmatory tier remains forward accrual (charter §6),
and forward outranks frozen.

---

## §9 Open questions for the red-team and the adjudicating main loop

1. **The R4b magnitude question (§4) — ANSWERED: no.** An earlier draft asked whether
   −3.8pp should replace −11.4pp as G2's magnitude anchor. It should not, and that claim is
   withdrawn: −3.8pp is the most extreme of four defensible estimators (the cohort-weighted
   reading of the same cells is −6.34pp and reads "survives"), it was measured on a
   substituted and outcome-correlated binning variable, and every estimate falls inside the
   parent's published [−19.2, −2.8]. **The charter's −11.4pp anchor stands unchanged.**
   Whether the stop-distance channel inflates it is open and needs its own pre-registration.
2. **Lens A/B anchor choice (§4).** Trailing 21-session max close, as the entry-free
   translation of the parent's entry-anchored stops. Better anchor available?
3. **K2's wording ambiguity.** "Mean second difference over the last `m` bars" admits m-diffs
   or m-bars; both are implemented and printed, and both read FALSE at both exemplars, so the
   G5 verdict does not turn on it. Confirm the reading for the record.
4. **Charter §2's K4 dependency clause is now factually stale** (§2.2): session-anchored
   recomputation was available, and the stored column already was it. Worth correcting in the
   charter's own text so a future reader does not re-defer K4.
5. **Does the operator's form want a different substrate entirely?** (§7.4) Explicitly out of
   scope here; flagged, not answered.
