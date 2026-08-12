# Stop-curvature context study — results (2026-08-12)

> **DRAFT — PENDING RED-TEAM.** Charter §7 makes an Opus reviewer pass mandatory before this
> doc lands, and verdict adjudication belongs to the commissioning main loop. Nothing here is
> adjudicated. No promotion, no engine change, no display copy follows from this document in
> its current state.

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

The reason is a single fact about the substrate, and it is not a statistical one: at BOTH
motivating confirms the 1D MACD-RSI histogram was making a **fresh trailing low** — it was
not arching up off one. The curvature family as enumerated cannot classify the chart the
hypothesis came from, so under charter §1 it never reaches the tape.

This is a **definition-validity null, not a tape null.** The charter's forms were not tested
against the market and found wanting; they were tested against their own motivating receipts
and found not to describe them. The distinction matters for what happens next (§7).

---

## §1 Acceptance gates — verdicts

| # | Gate | Verdict |
|---|---|---|
| 0 | **Parity gate** (recomputed histogram reproduces stored `hist_rising`) | **PASS — 12,940/12,940 exact** |
| 1 | **G5 runs first**, ordering auditable in the script's own output | **PASS** — outcomes physically sealed; 0 reads before unseal |
| 2 | **PIT leak test** that can FAIL | **PASS** — all 12,940 rows, worst deviation `0.000e+00` |
| 3 | **R9d battery** (fixed −8%, 2ATR, entry-distance quintiles) | **RUN — all three**, on the control lens (§4); no chartered form survived G5 to be tested |
| 4 | **Coverage floor ≥5%** | Evaluated per form (§5); K2 fails at 0.59%, K1/K3/K4/K5 clear |
| 5 | **G2/G3/G4 printed per form** | **NOT EVALUATED for any form** — every form is disqualified at G5, and the charter forbids reading an outcome row for a disqualified form |
| 6 | **Nulls printed, not hidden** | Five ore-ledger rows in §3; no variant hunting (§7) |
| 7 | **STLD-excluded sensitivity row** | Implemented in `RC.primary`; emits no rows because no form reached the primary table |
| 8 | **Substrate bounds restated** | `RC.substrate` (§8) — no re-windowing |
| 9 | **Every number reproducible** | Yes — single command above |

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
| 1D MACD-RSI histogram → `hist_rising` | 12,940 | **12,940 (100%)** | **PASS** (blocking) |
| 3D `macd ≥ sig`, **session-anchored** → `m3_bull` | 12,940 | **12,940 (100%)** | matches stored |
| 3D `macd ≥ sig`, **first-timestamp phased** → `m3_bull` | 12,940 | 12,859 (99.37%) | 81 rows diverge |

### 2.2 K4 is NOT deferred — and the charter's phase premise needed correcting

Charter §2 flagged K4 as possibly deferred because "3D grids currently inherit the
confluence_v2 first-timestamp phase defect", and the build brief assumed the stored `m3_bull`
column was the phased one. **Neither holds macro-side.** `engine/signal_quality._tf_grid`
has bucketed on the absolute session calendar since `ANCHOR_ERA=sq-abs-session-2026-08-06`
(`engine/session_anchor.py`), so the stored `m3_bull` **already is** the session-anchored
recomputation — proved, not assumed, by row 2 above (independent rebuild, 12,940/12,940).

The R4.hl_phase defect is real but lives in charting-app's `confluence_v2`, which is what
produces the *confirm events*, not this column. Row 3 quantifies it for the first time: a
first-timestamp-phased rebuild of the same leg disagrees on **81/12,940 rows (0.63%)**, and
on the exemplars it agrees (both read the same at May-19 and Jan-07). So on this frame the
phase defect is **not material to K4's verdict** — a finding the charter asked for either
way (§4.6).

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

K1/K2/K3 all require the bar to be **above** its trailing minimum. At both exemplars it is
below. K4 is TRUE at May-19 (the half of the receipt the charter quoted) but **FALSE at
Jan-07** — the charter's §1 table never claimed otherwise; it gave a 3D reading only for
May-19. K5 inherits K4's Jan-07 miss because K1 misses there too.

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

### 3.3 Cross-check receipt — is this about the series, or about the bar? — `RC.g5.crosscheck`

If every enumerated form misses, a successor charter needs to know whether the miss is a
property of the house MACD-RSI series (`_rsi_macd` = MACD of RSI) or of the daily bar itself.
Textbook MACD(12,26,9) on close, at the same three dates:

| ticker | confirm | hist[T] | tmin(w=15, excl. T) | reading |
|---|---|---|---|---|
| STLD | 2026-05-19 | −2.5787 | −1.9715 | at/below — fresh low |
| STLD | 2026-01-07 | −1.0317 | −0.8596 | at/below — fresh low |
| STLD | 2026-06-18 | −2.8064 | −1.0714 | at/below — fresh low |

**The rival serialization behaves the same.** The daily histogram — either flavour — was at a
fresh low at both motivating confirms. This is a receipt on three already-public exemplars:
it defines no form, classifies no cohort, reads no outcome, and licenses nothing. Its only
job is to stop a successor charter from re-running this study with `_rsi_macd` swapped for
MACD(12,26,9) and expecting a different G5.

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
With no chartered form surviving G5 there was nothing new to equalize, so the battery was run
on the parent's **already-published** R4b strict split (`hist_rising`) as machinery
validation. That lens' outcome is public (23.6% vs 35.0%, −11.4pp), so re-reading it
auditions no new construction.

| lens | TRUE near-low% | FALSE near-low% | spread | retained | reads as |
|---|---|---|---|---|---|
| **RAW** (real structure stops) | 23.64% | 35.02% | **−11.38pp** | 1.00× | baseline |
| **A — fixed −8%** (n=18,640 synthetic triggers) | 23.17% | 35.20% | −12.03pp | +1.06× | survives |
| **B — 2×ATR14** (n=38,195 synthetic triggers) | 21.48% | 30.28% | −8.81pp | +0.77× | survives |
| **C — break-depth quintiles** (3/5 usable) | — | — | **−3.80pp** | **+0.33×** | **COLLAPSES — stop-width arithmetic** |

Two things follow, and the second is a **new finding about the parent, not about this
family**:

1. **The battery is live.** Its RAW row reproduces the parent's published R4b figure
   independently and to the decimal (−11.38pp here vs −11.4pp published, 23.64% vs 23.6%,
   from a separately recomputed histogram). A battery that could not reproduce a known number
   would be worth nothing on an unknown one.
2. **Two-thirds of R4b's strict-form deficit is stop-width arithmetic.** Holding break depth
   (`close/stop_level − 1`) fixed within quintiles shrinks the −11.4pp deficit to −3.8pp —
   the same collapse the parent's §R9d found for its §R8 features, now visible on the R4b
   result itself. The kill stands (the sign never flips, and R4b also failed on rarity and
   forward tape), but its **magnitude was inflated** by the stop-distance channel. If the
   parent's −11.4pp is cited anywhere as a magnitude anchor — including in this charter's own
   G2 ("a promotable positive form should be of comparable magnitude") — that anchor is
   roughly 3× too large. **This is the item most in need of red-team attention.**

Lens definitions are disclosed translations, not charter terms: the parent's fixed-% and ATR
stops were anchored to an episode *entry*, and this frame has no entries, so lenses A and B
anchor to the trailing 21-session max close. A reviewer who disagrees with that anchor should
say so — the lens C result does not depend on it.

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
- **G5 is pinned in the PASS direction too**: a planted name that genuinely arches on both
  exemplar dates must CLEAR G5, so "all five missed" is a measurement and not a stuck switch
- the two 3D grid phases are pinned as genuinely different computations, so §2.2's
  reconciliation is not a guaranteed zero

Synthetic frames only; the one real-store receipt is `skipif`'d on the absence of `data/` and
has a never-skipping synthetic twin, matching the `test_price_ladder.py` pattern.

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
   relative to its own recent low will miss the same two receipts.
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

1. **The R4b magnitude correction (§4).** Is −3.8pp (break-depth-conditioned) the number that
   should anchor G2 in any successor charter, rather than −11.4pp? This changes what
   "comparable magnitude" means for a future positive form.
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
