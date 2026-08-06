# W5.1 — `macd_bear` ratification packet (2026-08-05)

## §0 STATUS — this packet changes no gate

**Nothing here flips a gate, a board, an engine constant, or a config value.** It assembles
the evidence on one veto leg and lays out options. The W5 change itself stays sequenced
behind BOTH:

- **G0.2** — W0's nightly miss-audit artifact must exist and be green for **5 consecutive
  nightlies** before any W3+ scored change merges
  (`PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §G0.2); and
- **operator ratification** — `not_topped` is a scored admission gate, so G0.4's population
  fence applies: the live board's buy membership stays byte-identical until a flip is
  ratified.

The commissioner adjudicates; the operator ratifies. This document deliberately does **not**
recommend an option — §6 prices all four neutrally and §7 states what would have to be true
for each to be wrong.

**Tier of everything below:** measurement / research. Nothing here is user-facing, and the
falsifier framing in §7 stays research-side by standing order (operator 2026-07-27, #3821).

**Trial-ledger status: FIRST LOOK.** `data/trial_ledger.jsonl` (1,366 rows) carries no prior
veto-leg sweep family. This is the first registered look at this construction — unlike the
FRESH_TICKS packet, which turned out to be a third look. Stating which look it is, is the
discipline; this one is genuinely first.

**Artifacts.** Instrument `research/prophet_us_audit/veto_leg_isolation.py`; frozen results
`research/prophet_us_audit/veto_leg_isolation_results.json`; guard
`research/prophet_us_audit/test_veto_leg_isolation.py` (16 tests). Frozen-frame pin
`REPRO_ASOF = 2026-07-31`, universe = the three US closes caches as production reads them,
1,493 names × 777 sessions (2023-06-27 → 2026-07-31), 939,611 in-range name-days.

---

## §1 The pre-registered keep-rule and its failure, verbatim

From `research/signal_engine/VETO_LEG_AUDIT.md` (2026-07-22), §Design, pre-registered before
results:

> **Keep rule** (pre-registered): a leg earns its keep on a cell iff that cell stops out
> ≥ +3pp worse than `P`.

`P` = the cell the veto admits. Ruler: next-close fill, −5% intrabar-low hard stop, 20d
barrier; verdict metric = stop-out rate.

From the same file, §Verdicts per leg (by the pre-registered rule):

> - **`macd_bear` — FAILS its keep.** +0.8pp full-history; **−3.9pp (helps the wrong way)
>   since 2023**. Decade splits oscillate (1990s +5.0, 2000s −2.5, 2010s +1.2, 2020s −1.9) —
>   noise-level protection, never a stable ≥3pp margin. Cost: it vetoes **4.4×** more fires
>   than the gate admits (23,716 vs 5,339) — in the current window it blocks 83% of all
>   T2-shaped fires. The board's *de facto* primary gate is an unvalidated leg pointing the
>   wrong way this regime.
> - **`stoch_ob` — EARNS its keep** (+5.3pp full-history; the AMAT case). Recent inversion is
>   n=36, noted, not actionable.
> - **`stoch_bear` — fails the +3pp rule on the pooled population** (±0pp) **but must stay**
>   for T2 anyway: `long_bias` independently requires k3 ≥ d3 […]

And the same file's own recommendation, which the program has followed to date:

> 3. **Do not delete `macd_bear` from the scored cascade now.** It failed its keep-test, but
>    the decade oscillation says regime-dependence; the honest path is the forward shelf, not
>    a retroactive gate rewrite. Revisit with the shelf's matured ledger.

**Provenance finding carried forward from that audit, still binding:** the T1–T4 table in
`TIERED_CASCADE.md` was measured *without* the not-topped veto. The veto is a
post-measurement bolt-on (the AMAT extended-top guard). Its cost/benefit was never in the
tier table's evidence base.

---

## §2 The fail-open defect, and what it does and does not contaminate

### 2.1 The defect

`engine/confluence_tiers.py` l.323: `macd_bear = m3n < s3n`. On a warm-up bar both operands
are NaN, and `NaN < NaN` is `False` — so the leg reads **"not bearish"** where the honest
value is **"not knowable"**. The 3D RSI-MACD's measured warm-up is **232 daily bars**
(`LEG_WARMUP_BARS["m3_s3"]`); the floor that admitted names to the cascade was **200**
(pre-#4558) and is **159** today (#4558 made it `max` over the gating legs). The engine now
documents this against itself, l.76:

> `m3_s3` (3D RSI-MACD) · 232 · gates: nothing · short of it, TODAY: **veto `macd_bear` leg
> FAILS OPEN**

`#4558` **disclosed** the defect (`null_legs` now names every leg short of its warm-up) and
**widened** the affected band from [200, 232) to [159, 232). It did not repair the leg —
repair is a scored-module change and belongs to whichever option is ratified.

### 2.2 The direction is the opposite of the obvious guess — measured, not argued

Because the leg reads `False` on NaN, it **cannot fire** below 232 bars. So the fail-open
cannot manufacture a veto; it can only manufacture an **admission**.

| claim | measured |
|---|---|
| rows in the `SOLE:macd_bear` cohort sitting below the 232-bar warm-up | **0** of 45,115 |
| admitted (`eligible`) name-days inside the band, frozen frame | **10,823 of 70,972 = 15.25%** |
| same, on the pre-#4558 band [200, 232) | 5,125 = 7.22% |
| names with at least one band admission | 1,260 of 1,493 |

**So the cohort blocked by the leg is automatically clean, and the ADMITTED CONTROL is the
contaminated side** — rows let through on two evaluated legs plus one that never ran.

### 2.3 Contamination assessment — three populations, three different answers

**(a) The pre-registered VETO_LEG_AUDIT study: NOT CONTAMINATED.**
`research/signal_engine/veto_leg_audit.py` l.150-153 skips any fire whose `k3/d3/m3/s3` are
not all finite — *before* advancing the dedup anchor:

```python
m3n, s3n = float(m3_d.iloc[i]), float(s3_d.iloc[i])
if not all(np.isfinite(x) for x in (k3n, d3n, m3n, s3n)):
    continue
```

Every graded fire in that study had the 3D RSI-MACD computable. **The keep-rule failure in §1
was measured where the leg actually evaluates.** The commonly-stated form of this concern —
"the leg has never been tested as specified" — is not supported: on its own ruler and panel,
it was.

**(b) The LIVE BOARD: effectively not exposed, and bounded by a different floor.**
`signal_gate.gate()` is only called for a ticker that got a library record
(`scripts/build_stock_library.py` l.2841-2854), and `_one()` refuses a record below
`min_days = 300` for ordinary names (`EXTRAS_MIN_DAYS = 252` for curated extras, which get a
LIMITED record instead). **300 > 232 and 252 > 232**, so the library floor dominates the
cascade floor: no ordinary name has ever reached `cascade()` with the leg unevaluated.

The one live path that can is a **curated extra with a LIMITED record** — `gate()` still runs
on it, and the cascade blanks only below 159 bars. At `REPRO_ASOF`, of 449 curated extras,
exactly **one** sits in the [159, 232) band: **NAVN (188 bars)**. Everything else below the
extras floor is below 159, where no tier is computable at all.

**(c) The RETROSPECTIVE INSTRUMENTS: contaminated, measurably.** Anything that calls
`cascade()`/`tier_stream()` directly on a price series, with no library floor, carries band
admissions:

| instrument | exposure |
|---|---|
| this file, full frozen frame | 15.25% of admitted name-days |
| `label_grading_battery.py` (#4547) `CONTROL:eligible_admitted`, its own window | **623 of 18,625 = 3.3%** (146 names) |
| `engine/prophet_miss_audit.py` — the **W0 artifact G0.2 gates on** | filters at `ct.MIN_HISTORY` (159) and calls `ct.cascade` directly (l.1718/1925) — no 300-bar floor, so its "eligible today" cohort is wider than the live board's |

The last row is the one that matters procedurally: **the instrument G0.2 depends on grades a
population the live board would not admit.** That is not a reason to distrust the miss-audit's
misses; it is a reason to read its *admits* with the band split out.

### 2.4 Would the leg have vetoed those admissions? (bounded)

Re-computing the leg on yahoo-spliced history and reading it on the same dates, restricted to
rows where it is computable on the deep series and not on the production cache:

| | value |
|---|---|
| admitted band rows probed | 1,928 (249 names; max single name 1.2%) |
| would have read bearish | **1,468 = 76.1%** |
| positive control — warm rows, same shape (bars ≥ 232, stoch legs clean, tier reachable) | 44,786 / 104,605 = **42.8%** |
| **date-matched control** — same warm rows, restricted to the probe's own 140 sessions | 5,672 / 13,182 = **43.0%** |
| probe − date-matched | **+33.1pp** |

**Read.** The DIRECTION is supported: a large share of band admissions carried a 3D RSI-MACD
that was in fact bearish. The LEVEL is not transferable — the splice shifts the `3B` resample
phase, and the band is calendar-concentrated (each cache group traverses it in one window),
and the date-matched control shows a 33pp gap that those two effects can account for. The
**conservative floor**, applying the date-matched rate rather than the probe rate, is
**~4,657 of 10,823** band admissions (43.0%) that would have been vetoed.

### 2.5 The fail-open-corrected read of the leg itself

Restricting the control to rows where the leg genuinely evaluated (bars ≥ 232) barely moves
it, because the band's admissions are a modest and not-especially-different minority:

| H=10, full frame | n | per-name-first median (pp) |
|---|---|---|
| `CONTROL:admitted` (all) | 69,783 | −0.27 |
| `CONTROL:admitted` (macd3 evaluated) | 58,630 | −0.19 (**+0.08pp shift**) |
| `SOLE:macd_bear` vs control (all) | 44,395 | **−0.26** |
| `SOLE:macd_bear` vs control (macd3 evaluated) | 44,395 | **−0.34** |

**Verdict on the contamination question:** the naive slice was *not* "never measuring the
leg". Correcting for the fail-open moves the leg's measured separation from −0.26pp to
−0.34pp at H=10 — the same sign, the same order of magnitude, a slightly *larger* apparent
separation. **No prior result in this program is overturned by the fail-open.** What the
defect does overturn is the claim that the admitted control is a clean three-leg cohort: for
15% of its rows over this frame, it is a two-leg cohort wearing three legs' clothes.

---

## §3 The measured per-leg table — what the family-level null could not answer

**Why this measurement exists.** #4547 graded `not_topped:macd_bear_ONLY`, where ONLY means
leg-exclusive *within the not-topped triple* (`label_grading_battery.py` l.649-651:
`mb & ~ob & ~sb`). It does not require the rest of the cascade to pass, so most of its cohort
is name-days no tier would have claimed even with the veto switched off. A null on the FAMILY
is compatible with one leg helping and another hurting; a diluted per-leg label cannot
separate them either.

**The predicate used here.** `tier_stream` (l.566-583) gates as `if not not_topped: continue`
before any tier, so eligibility factorises exactly:
`eligible == not_topped & tier_reachable`, where
`tier_reachable = t1_fresh | t2_active | t3_active | t4_active` never reads the veto. Hence

> `SOLE[L] := L & ~sibling_a & ~sibling_b & tier_reachable`

is the cohort that is blocked, is blocked by `L` alone, and would be **admitted the moment
`L` is removed**.

**The factorisation is pinned, not asserted.** The instrument re-derives `not_topped` and
`eligible` from its inline legs for every name and compares cell-for-cell with
`tier_stream`: **1,493 names, 939,611 cells, 0 `not_topped` mismatches, 0 `eligible`
mismatches.** Its leg census also matches #4547's exactly (`stoch_ob` 244,829 · `stoch_bear`
387,619 · `macd_bear` 292,254 · in-range name-days 939,611 — all deltas 0), so the two
instruments are reading the same legs on the same frame. No dead legs.

### 3.1 Full frozen frame (2023-06-27 → 2026-07-31)

Per-name-first median excess, in pp. `Δ ctrl` = cohort minus `CONTROL:admitted`.
`dm` = day-demeaned (market-neutral) median; `Δ dm` = that column minus control's.

| cohort | n | names | **H10** pnf / Δ ctrl | Δ dm | **H21** pnf / Δ ctrl | Δ dm | **H63** pnf / Δ ctrl | Δ dm |
|---|---|---|---|---|---|---|---|---|
| `CONTROL:admitted` | 69,783 | 1,491 | −0.27 / — | — | −0.94 / — | — | −2.02 / — | — |
| `SOLE:stoch_ob` | 22,168 | 1,340 | −0.34 / **−0.07** | 0.00 | −1.25 / **−0.31** | +0.05 | −2.65 / **−0.63** | +0.11 |
| `SOLE:stoch_bear` | 5,323 | 981 | −0.07 / **+0.20** | +0.04 | −0.27 / **+0.67** | +0.33 | −2.35 / **−0.33** | +0.04 |
| `SOLE:macd_bear` | 44,395 | 1,477 | −0.53 / **−0.26** | −0.07 | −1.51 / **−0.57** | −0.02 | −2.54 / **−0.52** | **+0.59** |

Loser rate (excess vs SPY < −3pp) vs control: `stoch_ob` −0.1 / 0.0 / +0.5pp ·
`stoch_bear` −2.0 / −5.0 / −0.2pp · `macd_bear` **+1.2 / +0.8 / −1.2pp**.

### 3.2 #4547's own window (2026-01-15 → 2026-07-17), H=10 — for direct cross-reading

| cohort | n | pnf (pp) | Δ ctrl | loser % | Δ loser |
|---|---|---|---|---|---|
| `CONTROL:admitted` | 18,625 | +0.13 | — | 33.7 | — |
| `SOLE:stoch_ob` | 6,639 | −0.10 | −0.23 | 33.1 | −0.6 |
| `SOLE:stoch_bear` | 1,618 | +1.02 | **+0.89** | 26.8 | **−6.9** |
| `SOLE:macd_bear` | 13,386 | −0.48 | **−0.61** | 34.8 | +1.1 |
| *(#4547's `macd_bear_ONLY`, same window)* | *36,590* | *−0.07* | *−0.20* | *34.0* | *+0.3* |

The control row reproduces #4547's exactly (n=18,625, pnf +0.13, loser 33.7) — the two
instruments agree on the baseline and differ only in the cohort definition. **The
sole-blocker cohort separates ~3× harder than the leg-exclusive label** (−0.61pp vs −0.20pp):
the label instrument diluted the leg with rows no tier would ever have claimed.

### 3.3 Robustness — and the caveat that matters most

- **Half-split (H10, full frame):** `macd_bear` **no sign flip** (−0.65 / −0.19, gap 0.46);
  `stoch_ob` no flip; **`stoch_bear` FLIPS** (−0.17 / +0.48). Control no flip.
- **Onset-only** (first day of each contiguous run, low-overlap read, H10): `macd_bear`
  −0.35 vs control −0.24 = **−0.11pp** — same sign, roughly 40% of the pooled gap. Part of
  the pooled separation is run-length overlap.
- **Sector mix:** `SOLE:macd_bear` and the control are near-identical (max single sector 18.5%
  vs 19.1%, both Financials). This is not a sector call.
- **THE CAVEAT.** On the **day-demeaned** column the leg's separation largely vanishes:
  −0.07 / −0.02 / **+0.59** pp across H10/21/63 on the full frame, and −0.12 / −0.33 / −0.32
  on the recent window (that window is #4547's exactly at H=10 — 2026-01-15 → 2026-07-17 —
  and a truncation of it at H=21/63, since it ends where forward coverage ends: 2026-07-01 and
  2026-04-30). Compare the vs-SPY per-name column at −0.26 / −0.57 / −0.52. **Most of
  the blocked cohort's underperformance versus SPY is a date effect** — the cohort clusters
  on sessions when the whole universe trailed SPY — **not cross-sectional stock selection.**
  At H=63 on the full frame the demeaned column turns positive. `stoch_ob` shows the same
  pattern (demeaned Δ 0.00 / +0.05 / +0.11 — i.e. neutral-to-favourable).

### 3.4 Per-leg verdicts, stated from the printed numbers only

- **`macd_bear` — separates in the correct direction, at a magnitude the sibling instrument
  calls null, and mostly on the market-timing axis rather than the selection axis.** The
  cohort it alone blocks grades worse than the admitted control at every horizon (−0.26 /
  −0.57 / −0.52pp), sign-stable, no half-split flip, no sector concentration. But it is 0.26pp
  at the primary horizon — the same order of magnitude as the largest gap #4547 measured in
  the *opposite* direction (`max_edge_over_control_pp = 0.28`) and called a clean null, so it
  sits at that instrument's demonstrated noise floor; the onset-only cut halves it; and the demeaned column
  reduces it to ≈0 and flips it positive at H=63. **It does not clear the pre-registered
  ≥+3pp keep rule on that rule's own ruler, and it does not clear a selection-based bar on
  this one.**
- **`stoch_ob` — no measurable separation on this frame.** −0.07pp at H10; the H63 −0.63pp is
  the only sizeable figure and its demeaned twin is *positive* (+0.11). This is the leg
  VETO_LEG_AUDIT scored **+5.3pp EARNS its keep** on the stop-out ruler. The two rulers
  disagree about `stoch_ob` at least as sharply as they disagree about `macd_bear`.
- **`stoch_bear` — the one leg whose blocked cohort grades BETTER than the admitted control**
  (+0.20 / +0.67pp; +0.89pp and −6.9pp losers in #4547's window) — **but it sign-flips across
  the half-split and at H63, on the smallest cohort (n=5,323).** Not actionable; flagged
  because a family-level null would have hidden it entirely, which is exactly why per-leg
  isolation was run.

**The ruler disagreement is itself an exhibit.** VETO_LEG_AUDIT's ruler is stop-out rate under
a −5% intrabar stop / 20d barrier on a 231-name deep panel back to 1963. This packet's ruler
is forward excess versus SPY and versus the day median, H=10/21/63, on 1,493 names since
2023-06. On the first, `macd_bear` helps the wrong way (−3.9pp since 2023) and `stoch_ob`
earns its keep (+5.3pp). On the second, `macd_bear` separates weakly in the right direction
and `stoch_ob` does not separate at all. **Neither ruler is wrong; they measure different
things** (a tight-stop survival question vs a holding-period return question), and no
adjudication that cites one should be written as though the other agrees.

---

## §4 Forfeiture pricing — what removal buys and what it costs

Binding idiom (CN G0.7): a veto's removal is priced by **both** what it stops costing **and**
what it starts admitting. Removing `L` admits `SOLE[L]` and nothing else — the added cohort
in §3 *is* the forfeiture cohort, by the factorisation identity (pinned by test).

**Volume.** Removing `macd_bear` takes the board from 70,972 admitted name-days to 116,087 —
**+45,115, a 63.6% wider board** (91.3 → 149.4 names per session on average across 777
sessions; 1,480 of 1,493 names gain at least one admission). In #4547's window the widening is
18,625 → 32,011 (**+71.9%**).

**Grade of what gets added** (= `SOLE:macd_bear`, §3): worse than the control it joins at H10
and H21 on the per-name column (−0.26 / −0.57pp), with +1.2 / +0.8pp more losers; better on
losers at H63 (−1.2pp); ≈0 on the demeaned column throughout.

**Grade of the resulting board.**

| horizon | union board (no `macd_bear`) | control today | Δ pnf | Δ loser |
|---|---|---|---|---|
| H10 | n=114,178 · pnf −0.34 · loser 32.2 | n=69,783 · pnf −0.27 · loser 31.7 | **−0.07pp** | **+0.5pp** |
| H21 | n=111,473 · pnf −1.27 · loser 42.1 | n=68,120 · pnf −0.94 · loser 41.8 | **−0.33pp** | +0.3pp |
| H63 | n=101,887 · pnf −2.04 · loser 47.9 | n=62,127 · pnf −2.02 · loser 48.4 | −0.02pp | **−0.5pp** |

(Per-name-first medians are not additive across a merged cohort, which is why the union delta
is smaller than the added cohort's own delta.)

**Read.** Removal costs a board 64% larger for a per-name median 0.07–0.33pp worse at H10/H21
and indistinguishable at H63, with losers +0.5pp at H10 and −0.5pp at H63. **The price is
paid in board size and attention, not in a measurable degradation of outcome quality.**
Whether a 64% wider board is a cost or the point is a product judgement, not a statistical
one — and it is exactly the judgement §2.5 of the masterplan reserves to the operator.

**Standing constraints on any removal (DNR, checked by rule text):**

- **KILL-FUSED-SHIELD** — a fused shield / meta-router over buy-decision vetoes is FORBIDDEN.
  No option in §6 proposes one.
- **KILL-200DMA-RECLAIM-VETO-FLAT (2026-08-05)** — the *flat drop* of a US veto leg was
  REJECTED-ON-MEASUREMENT on this very program four days ago; revival requires a
  **regime-conditional** construction + fresh prereg + a `us_prophet_v1→v2` era stamp. Any
  option-(b) proposal inherits that shape requirement.
- **Leader pullback-reset** (RS63 ≥ 0.8, > 50dMA, fresh 2D cross, **NO veto**): n=938,
  **−1.50% / −2.12%**, 45.8% win (`RESULTS_2026-08-03.md` l.50). Removing the veto machinery
  wholesale measured negative on the leader cohort. **This packet does not propose wholesale
  veto loosening**; that construction is closed and the masterplan says so at l.13/l.198.

---

## §5 The operator's exhibits — illustration, and a correction

RKLB and ASTS are the operator's named space runners, cited as blocked identically and solely
by `macd_bear` (`why_not_receipts_2026-08-05.json`, #4554). **Two names are an illustration.
They carry no part of any verdict above, and they are curated extras outside the graded
universe entirely.**

Computed on their own series at both the frozen frame and the receipt's own date:

| | RKLB | ASTS |
|---|---|---|
| bars @ 2026-08-03 | 1,427 | 1,695 |
| `stoch_ob` / `stoch_bear` / `macd_bear` | F / F / **T** | F / F / **T** |
| `tier_reachable` (T1∨T2∨T3∨T4, veto-free) | **False** | **False** |
| would be admitted if `macd_bear` removed | **No** | **No** |
| sessions blocked by `macd_bear` alone, last 252 | 64 | 69 |
| sessions in the true sole-blocker cohort, last 252 | 22 | 32 |

**Correction to the exhibit as commissioned.** The receipt's `blocking_leg` field is the
**first failing gate in engine evaluation order** — the veto is checked before any cross,
freshness or RSI test, so the receipt necessarily reports it and cannot speak to what would
happen if the leg were removed. Its own plain-language line says so ("the tier is null
regardless of cross age"). On 2026-08-03 neither name reaches any tier with the veto switched
off: RKLB's 3D cross is 26 ticks old and its 2D buy 42 ticks old (FRESH_TICKS = 2), ASTS's are
19 and 29, and neither has a live T3/T4 projection. **Removing `macd_bear` would not have
surfaced either name that day.**

What is true, and is the honest form of the operator's complaint: both names spend a large
share of the year blocked by this leg and no other (64 and 69 of the last 252 sessions), and
both **do** enter the true sole-blocker cohort on a meaningful minority of days (22 and 32).
The leg is the binding refusal for these names much of the time — just not on the day the
receipt was cut.

---

## §6 Options — priced neutrally, no recommendation

Each option lists what it costs, what it risks, and what it requires procedurally. All four
sit behind G0.2 + operator ratification regardless.

### (a) Keep the leg as-is

- **Cost.** The board stays 64% smaller than the veto-free board, and the leg keeps refusing
  ~58 name-days per session that a tier would otherwise claim. The refusal is the *de facto*
  primary gate: it carries more exclusions than any other single admission rule.
- **Risk.** The keep-rule failure stays on the record unexecuted, which is a governance cost
  independent of the statistics — a pre-registered rule that fails and changes nothing
  weakens every future prereg in the program. VETO_LEG_AUDIT's own recommendation #3 chose
  this path in July, explicitly as a *hold pending forward evidence*; that shelf ledger is
  still the thing that has not accrued.
- **Requires.** Nothing. This is the status quo, and the status quo is what ships if no
  ratification is given.

### (b) Retire the leg (execute the keep-rule's own consequence)

- **Cost.** A 63.6% wider board at a per-name median 0.07–0.33pp worse (H10/H21) and +0.5pp
  losers at H10; indistinguishable at H63. Downstream: `us_board_rank` ordering, the featured
  strip, and every consumer sized against today's board volume all move at once.
- **Risk.** (1) The added cohort's separation is real but small and rests on the vs-SPY
  column; on the demeaned column it is ≈0, so the leg may be doing market-timing work whose
  loss shows up only in a drawdown regime this frame does not contain. (2) **DNR
  KILL-200DMA-RECLAIM-VETO-FLAT rejected a flat veto drop on this program on 2026-08-05** —
  a flat drop here is the same shape and inherits the same objection. (3) The
  leader-pullback-reset result (−1.50%) is the standing evidence against veto removal for the
  cohort that matters most commercially.
- **Requires.** Regime-conditional construction + fresh prereg + `us_prophet_v1→v2` era stamp
  (per that DNR row), an auto-revert tripwire on false-admit rate, and G0.4 population
  disclosure. A T2-only removal (leaving T1's §7 filter untouched) is the narrowest form and
  is what the masterplan's W5.1 text actually specifies.

### (c) Repair the fail-open first, then re-measure

- **Cost.** One scored-module change (`macd_bear` must return NULL, not `False`, below 232
  bars — the `null_legs` / PLTR "null-not-false" idiom already exists beside it) plus a
  decision about what a NULL leg means for admission: block, admit, or defer. Then a re-run of
  every instrument whose control carries band rows.
- **Risk.** **§2.3(a) and §2.5 both argue this option buys less than it appears to.** The
  pre-registered study already fenced NaN, so the keep-rule failure is not a fail-open
  artifact; and correcting the control here moves the leg's separation from −0.26 to −0.34pp
  — the same sign, slightly larger. The framing "the leg has never been tested as specified"
  is not supported by the evidence in this packet. The genuine value is procedural: it
  removes a known defect before a scored decision is taken on top of it, and it cleans the
  W0 miss-audit's admit side, which G0.2 gates on.
- **Requires.** Ratification as a scored-module change (it alters admission for the one live
  band name, NAVN, and for every replay instrument). It is the only option that is
  *prerequisite-shaped*: it can precede (a), (b) or (d) without foreclosing them.

### (d) Demote the leg to a recorded feature / ordering input

- **Cost.** The board widens exactly as in (b) — demotion removes the refusal — but the leg's
  information is retained as a rank or display input rather than discarded. Build cost is
  higher than (b): a new field through the cascade, the board row, and the candidates store,
  plus an ordering rule that must itself be justified.
- **Risk.** Ordering authority is authority. A demoted-but-ranking leg is `scored` under
  G0.1 and needs its own citation or prereg; shipping it as "just ordering" without one is the
  failure mode G0.1 exists to catch. It is also the option closest to **KILL-FUSED-SHIELD** —
  a *combining* rule over the three legs would be forbidden outright, so any implementation
  must keep the leg a standalone recorded field, never an input to a meta-gate.
- **Requires.** Explicit tier label per G0.1; if the field ever touches ordering, its own
  prereg and gate. The epistemics law supports the *retention* half without argument: a leg
  that is null as a standalone signal stays lawful as a confluence/recorded input, and
  display-tier accrual needs no gauntlet.

---

## §7 What would have to be true for each option to be wrong

Research-side falsifier framing. None of this language is user-facing, by standing order.

**(a) Keep is wrong if** the leg's separation is genuinely ≈0 on the axis that matters. The
demeaned column already says that at H10/H21 and says the *opposite sign* at H63. The check:
once W0's miss-audit has 5 green nightlies, the forward `SOLE:macd_bear` cohort should show a
demeaned per-name median indistinguishable from the admitted control at H10 and H21. If it
does, the refusal is buying nothing measurable and (a) is costing board coverage for free.

**(b) Retire is wrong if** the leg's protection is regime-conditional and this frame lacks
the regime. Two things would show it: the decade oscillation in §1 (1990s +5.0 → 2020s −1.9
on the stop ruler) is real regime dependence rather than noise; and the H63 demeaned column
(+0.59pp — the blocked cohort *outperforming* on a market-neutral basis over a quarter) is a
holding-period effect that a −5% stop ruler would score the other way. The check: split the
forward cohort by a pre-registered regime marker (VIX tercile or dispersion regime) before
removal, not after; if any regime shows the blocked cohort materially worse than control on
the demeaned column, a flat drop forfeits protection where it exists.

**(c) Repair-first is wrong if** it is procedural motion that changes no decision. §2.5
already shows the corrected read moves the leg's separation by 0.08pp, and §2.3(b) shows the
live board's exposure is one name. The check: state in advance which of (a)/(b)/(d) would
flip if the repaired numbers came back. If the honest answer is "none", (c) is a defect fix
worth doing on its own merits and should be argued that way — not as a precondition for the
ratification.

**(d) Demote is wrong if** the retained field never gets read, or gets read as authority
without a gate. Both are observable: a recorded field with no consumer after 60 sessions is a
field nobody needed, and a field that reaches ordering without its own prereg is a G0.1
violation. The check: name the consumer and its gate *in the same PR that adds the field*, or
ship it display-only and say so.

**And one falsifier for this packet itself.** Every number here rests on
`eligible == not_topped & tier_reachable`. That identity is re-derived per name and compared
cell-for-cell against `tier_stream` (1,493 names, 939,611 cells, 0 mismatches) and pinned by
`test_veto_leg_isolation.py`. If a future cascade change makes eligibility depend on the veto
in any way other than that conjunction — a veto-conditional tier, say — the sole-blocker
predicate stops being a counterfactual and every cohort above becomes a correlation. The
equality gate would go FAIL and the guard suite would go red; that is the intended alarm.

---

## Limitations

Frame is 2023-06-27 → 2026-07-31 (777 sessions) — one regime, and short for H=63 (the
horizon consumes 63 of them). `tier_stream`'s T1 uses the raw 3D cross rather than the live
board's §7 validated master, so the T1 slice of `tier_reachable` is a superset of the live
board's T1. Curated extras (RKLB, ASTS, NAVN) are outside the graded universe; §5 and §2.3(b)
compute them separately and say so. The deep probe's level is bounded, not estimated (§2.4).
Pooled cells double-count a name that sits in a cohort for weeks — the onset-only cut is
printed beside every headline for that reason. No sector-clustered standard errors; sector
mix is disclosed instead, and it is flat. Re-run:
`python3 research/prophet_us_audit/veto_leg_isolation.py`.
