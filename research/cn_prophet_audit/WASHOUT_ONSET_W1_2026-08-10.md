# CN LIMIT-MOVE ALPHA — W-P0: washout / confluence-conditional FIRST-BOARD onset

**The program's original thesis, run for the first time.** Masterplan §10.1 (operator,
2026-08-10). Instrument: `research/cn_prophet_audit/washout_onset_w1.py`; frozen numbers:
`WASHOUT_ONSET_W1_2026-08-10.json` (8.4 MB).

**Tier: DISPLAY / AUDIT.** Nothing here ranks, sizes, gates or admits anything. No entry
book is implied and **no expectancy is quoted anywhere in this receipt** — W3-C's measured
law (the T+1 auction prices access by removing the fills) is untouched by this lane and
would bind the moment anyone tried to trade a cell below.

**Status honesty, recorded so no session re-litigates it.** This study had never been run
and has never failed. Every prior kill in this program is an ENTRY-family kill on
POST-IGNITION cohorts; the shipped onset model is ladder-conditioned (N ≥ 1). This lane
measures the *cold* universe — names with no board in the prior 20 sessions — and asks
what precedes the ladder's 0 → 1 step.

---

## §0 ACCEPTANCE GATES

| Gate | Status |
|---|---|
| Ore ledger, ≥ 12 untested variants | **19 items**, §11 |
| No board pooling; ChiNext 2020-08-24 split | main / chinext10 / chinext20 / star, never pooled |
| Era tables (2015 its own stress era) | §5, six eras, per board |
| Wilson 95% on every rate; THIN at n < 20; ranking floor 150 fit-core positives | every cell |
| Deterministic `TZ=UTC` double-run byte-identical JSON | **verified** (§9) |
| Frozen JSON beside the MD | `WASHOUT_ONSET_W1_2026-08-10.json` |
| Display-tier language; the CI-enforced authority word is absent | `scripts/check_validated_claims.py` clean |
| S7 law — every verify predicate keyed to a series that CAN move | 7 checks, each with a mutation probe; **one S7 defect caught and recorded** (§9) |
| §6.4 null-headline standard — era-preserving permutation + session bootstrap on every affirmative magnitude | §8, three permutation arms + bootstrap |
| Store-vintage + split stamps | §10 |

---

## §1 VERDICT IN SIX LINES

1. **The Terminal's own momentum confluence is a printed NULL as a standalone first-board
   state.** Golden Oracle long, main board, holdout: lift **1.01** (fit 0.96), and 1.00
   after volatility matching. The construction tested is *theirs, at their live settings*.
2. **Washout depth is the carrier.** A main-board name sitting ≥ 50% below its 250-session
   high prints a first board within 10 sessions **15.17%** of the time against a **7.04%**
   unconditional rate — **2.15×**, six eras out of six positive, permutation p = 0.
3. **That lift is not volatility.** Matching on (session × the name's own realised-vol
   decile) leaves it at **2.16×** — essentially untouched.
4. **The window twin is where the volatility lived.** The same state's "peak ≥ 1.5 × band
   within 10 sessions" lift looks *larger* raw (1.95×) but collapses to **1.52×** when
   vol-matched, and the sector-breadth state collapses from 2.17× to 1.35×. **The washout
   state's information is specific to the BOARD, not to large moves in general** — the
   opposite of what the raw window table suggests.
5. **The conjunction is real and partly compositional.** Deep washout × sector-wide washout
   breadth > 60%: raw **2.63×**, but the date-preserving permutation null sits at **1.40**
   (the state lives on already-hot sessions), so the honest within-session excess is
   **1.88×**; vol-matched 1.98×.
6. **The Prophet-shaped ranking works, and it works best inside the product's own state.**
   Within Golden-Oracle-long on main, ranking by 5-session run-up (desc) gives top-5
   day-weighted precision **16.84% vs 6.91%** random-within-state = **2.44×**, clustered
   t **14.36** over 570 holdout sessions (ChiNext-20: **2.92×**, t 11.15).

---

## §2 THE CONFLUENCE-DEFINITION PIN (provenance — these definitions are not ours)

Extracted from the Terminal product repo `/Users/chriswong/Documents/Cluade/charting-app`
and transcribed, not reinvented. Testing *their* construction is the point of the study.

| | |
|---|---|
| Product name | **Golden Oracle / 黄金神谕** |
| `indicator_id` | `confluence_rsimacd_stochrsi_mtf` |
| Engine tag | `python:signal_layer.confluence_v2@v2` |
| Oracle (params, 3D grouping, CB/CS) | `signal_layer/confluence.py` |
| GC v2 (2D legs, anticipation dot, ARM/CONFIRM) | `signal_layer/confluence_v2.py` |
| Flagship params hashed into every contract | `signal_layer/contracts.py` |

**Parameters (their "Pine default inputs (the live configuration)"):** RSI 14 (Wilder RMA,
**SMA-seeded**, not plain `ewm`) · RSI-based MACD = EMA(RSI,14) − EMA(RSI,60), signal
EMA(·,5) · StochRSI = stochastic **of the RSI(14)** over 14 bars, %K = SMA3, %D = SMA3 ·
OB/OS 80/20 · CONF_W 8 · BUY_RSI_MAX 65 · EXT_RSI 70 · REV_BARS 3 · warm-up gate ≥ 90
three-day bars.

**BUY (CB) fires** when the RSI-MACD line crosses above its signal, **and** a StochRSI
%K/%D bull cross happened within 8 bars, **and** (the prior closed weekly RSI-MACD is
bullish **or** %D dipped under 20 within 8 bars), **and** RSI(14) < 65.

**3D bar rule — session-grouped, NOT a calendar resample**, anchored to the symbol's first
listed session, bar labelled by its OPEN date, and **close-only** (no OHLCV aggregation at
all — their design goal so CN/HK names with daily closes get the full surface). Their own
docstring: `pandas resample("3B") … is WRONG` — it mis-splits real sessions around every
holiday. We fed full history, so `bar_anchor = 0`, their documented contract.

**2D bar rule — production really does use the calendar `resample("2B")`**, in
`confluence_v2.early_dots` and `_arm_event_daily`, and that 2D bear-cross leg is the sole
source of the shipped unified SELL marker. It carries the same holiday mis-split defect
their 3D docstring calls wrong; their own `research/master_indicator_fusion_lab.py`
prototypes an IPO-phased fix that is **not wired into `signal_layer/`**. We replicated
**production, defect included** — that is what "test their construction" means — and the
session-phased 2D variant is logged as ore (§11).

**Three declared deviations, all stricter or clearly labelled:**
- **Availability stamp.** Their 3D frame is *labelled* by each bar's OPEN date but computed
  through its CLOSE. Using the label as an availability timestamp would be a two-session
  lookahead, so every 3D and 2D quantity here is stamped on its bar's **close session** —
  the same discipline their own research module states in prose.
- **v2's `bear_block` / `strong_bull`** are omitted from the position-state form
  (`bear_block` is 2W-derived and their docstring says 2W never feeds live CB/CS). Ore.
- The **2D bullish** MACD cross is *our* mirror of their production bear leg and is
  labelled as ours, never presented as one of their definitions.

---

## §3 Q1 — FIRST-BOARD LIFT (holdout = locked test 2024-01-02 → 2026-06-12, H = 10)

Outcome: a tolerant limit-up close (v0's adjudicated PRIMARY definition, 0.2% cushion) in
T+1..T+10, on a bar with **no board in the prior 20 sessions**. The universe rate is the
unconditional cold-universe rate for the same board and split.

> **Band-label convention.** Bands are left-open / right-closed: a band written `> Y` starts
> strictly above Y, and one written `≤ Y` includes Y. This is stated because it is
> load-bearing for S4 — sector breadth is a ratio of small integer member counts, so exact
> ties at a boundary (3 of 5 members = 60.0%) are common rather than measure-zero, and a
> label reading "≥60" on a band that actually starts strictly above 60 would misdescribe a
> populated cell.

### main board (unconditional: fit 5.88% · holdout 7.04%)

| State | fit lift | **holdout lift** | holdout rate | Wilson 95% | n | date-clustered t | **vol-matched** |
|---|---|---|---|---|---|---|---|
| S6 deep washout × sector breadth >60% | 1.90 | **2.63** | 18.50% | 17.37–19.68 | 4,422 | 6.32 | **1.98** |
| S6 Oracle-long × dd ≤ −50% | 1.57 | **2.23** | 15.69% | 15.00–16.40 | 10,455 | 3.29 | **2.07** |
| S2 washout dd ≤ −50% | 1.72 | **2.15** | 15.17% | 14.65–15.71 | 17,302 | 7.38 | **2.16** |
| S4 sector breadth >60% | 1.28 | **1.93** | 13.57% | 13.12–14.03 | 21,517 | 8.58 | **1.67** |
| S5a vol-z20 > 2 | 1.39 | **1.65** | 11.60% | 11.31–11.88 | 46,486 | 15.88 | **1.35** |
| S3 > 120 sessions under the 200MA | — | 1.13 | — | — | 62,001 | — | 1.19 |
| **S1 Oracle CB within 3 bars** | 0.96 | **1.13** | 7.93% | — | 61,897 | 0.85 | 1.10 |
| **S1 Oracle LONG (their traded state)** | 0.96 | **1.01** | 7.14% | — | 308,251 | −1.03 | **1.00** |
| **S1 2D histogram rising** | 1.06 | 1.09 | 7.64% | — | 290,790 | 7.60 | — |
| **S1 anticipation dot within 3 bars** | 1.01 | 1.04 | 7.29% | — | 115,042 | −3.34 | — |
| *(lowest cell)* shallow dd × mid breadth | 0.83 | **0.53** | 3.71% | — | 14,357 | −6.11 | — |

The ordering is **monotone and physical**: shallow drawdown in a mildly washed sector is
the *least* likely first-board state (0.53×), deep drawdown in a broadly washed sector the
most (2.63×). That is a 5× spread across one pre-registered grid, inside one board, in the
holdout.

### ChiNext ±20% (unconditional: fit 1.98% · holdout 3.18%)

| State | fit lift | **holdout lift** | holdout rate | n | clustered t | vol-matched |
|---|---|---|---|---|---|---|
| S5a vol-z20 > 2 | 1.63 | **2.05** | 6.52% | 15,148 | 9.42 | **1.19** |
| S6 deep washout × breadth >60% | 1.24 | **1.92** | 6.11% | 3,357 | 3.16 | **1.62** |
| S6 Oracle-long × dd ≤ −50% | 1.38 | **1.84** | 5.84% | 7,582 | 4.78 | **1.59** |
| S2 washout dd ≤ −50% | 1.24 | **1.67** | 5.31% | 13,530 | 6.39 | **1.68** |
| **S1 Oracle CB within 3 bars** | 1.02 | 1.24 | 3.94% | 18,333 | 2.82 | 1.21 |
| **S1 Oracle LONG** | 1.04 | 1.15 | 3.66% | 91,087 | 4.22 | 1.12 |

Note ChiNext-20's vol-z state is the reverse of main's: raw 2.05× but only **1.19×**
vol-matched — on the wide-band board the volume surge is largely a volatility read.

---

## §4 Q2 — THE WINDOW TWIN, AND THE CONTROL THAT DECIDES THE READING

The blast-off window class beside the board, per board, band-relative (`0.8w` / `1.5w` of
that board's own limit width). **`peak_*` is a foresight upper bound** — W3-A measured that
half to 60% of threshold-touching windows give the touch back before any scheduled exit.

Raw, the window lifts look *bigger* than the board lifts, which invites the reading "this
is just a volatility state". Matching on (session × own realised-vol decile) shows the
opposite:

| main, holdout | first board | | peak ≥ 1.5×band | |
|---|---|---|---|---|
| | raw | **matched** | raw | **matched** |
| S2 dd ≤ −50% | 2.15 | **2.16** | 1.95 | **1.52** |
| S6 deep × breadth >60% | 2.63 | **1.98** | 2.98 | **1.58** |
| S4 breadth >60% | 1.93 | **1.67** | 2.17 | **1.35** |
| S5a vol-z > 2 | 1.65 | **1.35** | 1.66 | **1.11** |
| S3 >120 under-MA | 1.13 | **1.19** | 1.08 | **0.93** |
| S1 Oracle long | 1.01 | **1.00** | 0.99 | **0.93** |

**The structural finding.** Every window-class lift standardises substantially toward 1
under volatility matching; the deep-washout **board** lift does not move at all
(2.158 → 2.157). Whatever the washout state knows, it is about the discrete event of a
name jamming into its band — not about the name being a big mover. That is the shape the
operator's mechanism predicts (repricing too large for the band) and it is the single most
load-bearing number in this receipt.

The control is a strictly-subtractive disclosure: direct standardisation of the *non-state*
rate over (date × own-vol decile) strata, re-weighted to the state's composition. It can
only pull a lift toward 1; it can never manufacture one. It was added **after** the raw
lifts were seen and is declared as amendment **A2** in the script's pre-registration block.

---

## §5 ERA TABLES (main, first board, H = 10 — 2015 kept as its own stress era)

| Era | S2 dd ≤ −50% | S6 deep × breadth >60% |
|---|---|---|
| e1 2011–14 | 1.69 (7.64%, n 30,921) | 1.93 (8.74%, n 14,771) |
| e2 2015 mania | 1.42 (25.67%, n 11,479) | 1.55 (27.98%, n 9,633) |
| e3 2016–18 crackdown | 2.00 (7.89%, n 88,391) | 2.09 (8.23%, n 61,076) |
| e4 2019–21 revival | 1.60 (12.01%, n 27,368) | 1.73 (12.96%, n 3,726) |
| e5 2022–23 grind | 2.13 (11.53%, n 29,441) | 3.44 (18.62%, n 6,025) |
| **e6 2024–26 (holdout)** | **2.15 (15.17%, n 17,302)** | **2.63 (18.50%, n 4,422)** |

**Six eras out of six positive on both states**, spanning the 2015 mania, the 2016–18
crackdown and the 2022–23 grind. Absolute rates swing 4× across eras (7.6% → 25.7%) — the
era dial dominates the level, exactly as every prior wave measured — but the *direction* is
stable in every regime. Per W3-A/W3-B's standing reading: **direction is the finding,
magnitude is not.**

**Vendor-rich audit window (2026-06-15 → 2026-08-07, 19 sessions after embargo).**
Unconditional 12.01%; S2 dd ≤ −50% **1.57** (18.80%, n 1,755); the conjunction **1.26**
(15.17%, n 290); Oracle-long **0.83**. The audit arm is small and weakens the conjunction —
consistent with the reconciliation ledger's own warning that audit is always worse than
replay. It is printed, not averaged away.

---

## §6 Q3 — THE PROPHET-SHAPED RANKING (the scorer-uplift preview)

*Among names already IN a state on a session*, can the v0 feature battery rank the ones
that go on to board? Day-weighted top-K precision against random-within-state (which in
expectation is the state's own per-session base rate). **Both rank directions were
pre-registered and both are printed** — v0's directions were measured on ladder-conditioned
cohorts and a sign flip inside a washout state would be a finding, so a post-hoc direction
choice is visible as multiplicity rather than hidden as a result.

### main · inside Golden-Oracle-LONG · holdout · H = 10 · 570 sessions

| Feature | dir | K=5 precision | random-within-state | lift | clustered t |
|---|---|---|---|---|---|
| f3 run-up 5d | desc | **16.84%** | 6.91% | **2.44** | **14.36** |
| f7 dist from 52w low | desc | 16.70% | 6.91% | 2.42 | 14.84 |
| f1 vol-z20 | desc | 12.11% | 6.91% | 1.75 | 8.51 |
| f3 run-up 5d | **asc** | 10.56% | 6.91% | **1.53** | 6.67 |
| f8 consec up days | asc | 5.12% | 6.91% | 0.74 | −4.55 |
| f7 dist from 52w low | asc | 3.61% | 6.91% | 0.52 | −8.54 |

ChiNext-20, same state: f3 desc **2.92×** (t 11.15), f7 desc 2.10×, f1 desc 2.06×.

**Two readings, both honest.**
- The v0 directions **carry into the cold universe**: high run-up and distance from the
  52-week low rank first-board candidates at 2.4–2.9× within the state, on 570 holdout
  sessions with a clustered t in double digits. This is the scorer-uplift signal P-A will
  re-measure on the actual Prophet pick panel.
- **f3 is U-shaped, not monotone**: the descending arm lifts 2.44× *and* the ascending arm
  lifts 1.53×, so the *middle* of the run-up distribution is the least likely place to find
  a boarder. That only became visible because both directions were pre-registered.

**Inside the already-selective conjunction the features add much less.** Within main's deep
washout × sector-breadth (>60%) state (153 eligible holdout sessions): f1 desc 1.33× (t 3.61), f8
desc 1.21× (t 2.51), f4 sector heat desc 1.17× (t 1.90). The state has already done most of
the selection work; the battery's remaining ranking power there is modest.

---

## §7 S5b — CHIP STRUCTURE (coverage-bounded; NO out-of-sample arm)

`data/tushare/chips_hist.parquet` (cyq_perf `winner`) covers **2025-05-26 → 2026-08-07**,
287 sessions. That begins *inside* the locked test window and long after train and
calibration, so **these cells have no out-of-sample arm at all** and are
hypothesis-generating, never evidence.

main, holdout, first board H = 10 (unconditional 7.04%):

| Win-rate level | lift | | 20-session trajectory | lift |
|---|---|---|---|---|
| ≤ 20 | 0.77 | | ≤ −10 | 0.93 |
| 20–50 | 0.93 | | −10 → 0 | 0.97 |
| 50–80 | 1.16 | | 0 → +10 | 0.98 |
| > 80 | **1.58** | | > +10 | **1.40** |

**This contradicts the naive form of the accumulation story.** cyq_perf win-rate is high
when price sits above most of the chip distribution — i.e. when the name is *strong*, not
when it is being quietly accumulated at a low. The monotone reading here is momentum, not
hidden accumulation. The 筹码分布 concentration measures the operator actually named
(percentile spread, concentration ratio, the main chip peak migrating toward price) need a
**cyq_chips history that does not exist in this checkout** — so nothing about the
accumulation mechanism is decided by this table in either direction. Ore, §11.

---

## §8 NULL-HEADLINE BATTERY (§6.4 standard)

Exact permutation nulls in closed form — hypergeometric resampling of the state-label
allocation inside each block *is* the permutation distribution of that label, not an
approximation. 2,000 draws, seeded; null mean and SD printed beside every p-value so no
single draw is ever quoted against an unstated null spread (W3-B's review MAJOR).

**main · deep washout × sector breadth >60% · holdout · first board H=10 · observed 2.63**

| Arm | null mean | null SD | lift ÷ null | z | p (one-sided) |
|---|---|---|---|---|---|
| perm global | 0.998 | 0.055 | 2.63 | 29.6 | 0.000 |
| **perm era-preserving** | 1.000 | 0.054 | 2.63 | 30.3 | 0.000 |
| **perm date-preserving** | **1.396** | 0.057 | **1.88** | 21.5 | 0.000 |

Session bootstrap (2,000 date-resamples): lift 95% CI **[2.12, 3.06]**, share of draws with
lift ≤ 1 = **0.000**.

**Read the date-preserving arm, not the global one.** Its null mean is **1.40**, not 1.0 —
roughly 40% of the raw 2.63× is the state sitting on sessions whose board rate is already
elevated. The honest within-session cross-sectional excess is **1.88×**. Every affirmative
cell in the JSON now carries `lift_relative_to_this_null` on all three arms for exactly this
reason (amendment A2b).

The null set is selected **per (board × outcome family)**, and every headline state is
force-included at the first-board horizons whatever its lift. A flat top-N-by-lift selection
let one board's window cells crowd out every first-board cell on the first pass, which would
have left the headline magnitudes unpriced — **the receipt cannot quote a cell it did not
null.**

---

## §9 VERIFY BATTERY, DETERMINISM, AMENDMENTS

Eight checks, **all pass**, each carrying a **mutation probe** — the same predicate
re-evaluated on a deliberately corrupted input, or the structural reason its series can
move. A check that cannot fail is a defect, not a pass.

| Check | Result |
|---|---|
| `terminal_rma_parity` — vectorised Wilder RMA vs a literal transcription of their loop | max abs diff **1.4e-14**; probe: a 1e-3 perturbation is detected |
| `cold_universe_implies_ladder_zero` — the §5 lemma asserted, not assumed | every realised first board recomputed; **0 violations** |
| `no_lookahead_state_construction` — scale all prices 1.35× after a cut | **0** pre-cut rows change; probe: corrupting the **past** changes them, so the check can see a failure |
| `closure_tolerant_chain_recovers_rows` | the 21-day step rule recovers the CNY/National-Day windows the 10-day rule discards |
| `outcome_requires_complete_window` | 0 outcomes scored on an incomplete chain |
| `split_embargo_covers_max_horizon` | 20 sessions embargoed at every split boundary |
| `conditioned_rate_series_can_move` | the dd-band rate axis is live before any lift is read off it |
| `confluence_transcription_non_degenerate` — no oracle state is empty or always-on | shares 1.25–54.4%, warm coverage 100%; probe: breaking the 3D grouping, warm gate or weekly join collapses a share to 0/1 and this fires |

**Determinism:** two consecutive `TZ=UTC` runs at the same commit produce a byte-identical
JSON (`cmp` clean). No wall-clock, runtime or hostname enters the file.

**Amendments (declared, not silent).**
- **A1 — an S7 defect this battery caught in itself.** On the first run the embargo check
  read its session universe off the already-split-filtered frame, so "sessions after the
  last kept date" was 0 *by construction* and the predicate could not fail. It reported
  FALSE rather than a false PASS, which is how it surfaced. Verify-only: the embargo itself
  was always applied; only its audit was blind. No measured number changed.
- **A2 — two controls added after seeing the raw lifts**, both strictly subtractive: the
  volatility-matched arm (§4) and `lift_relative_to_this_null` on every permutation arm
  (§8). Neither can create an affirmative result; both can only weaken one.
- **A3 — transcription-sanity instrumentation, added after the S1 null was read (it forced
  the final run pair).** A null headline on a possibly mis-transcribed signal is not a null.
  The instrument now emits `confluence_transcription_sanity` — P(10-session cumulative
  return > 0) on-state vs off-state, a directional RATE with no book implied; max |edge|
  5.48pp across states×boards — plus the `confluence_transcription_non_degenerate` verify
  check above. Together they separate three statements that would otherwise collapse into
  one: "this construction does not select first boards" (what §S1 now says), "the
  transcription is broken" (excluded: states live, shares sane, tilt measurable), and "the
  oracle does not transfer to CN names" (excluded for direction, untested for selection).
  Verify-only + descriptive; no measured lift changed.
- **A4 — a provenance-stamp defect caught by the determinism gate itself.** Run 1 of the
  final pair stamped a `chips_commit` unreachable from the build head (the checkout moved
  mid-run while the branch was being staged). The measurement was unaffected — 8.7MB
  byte-identical across all runs, sole diff the stamp line — but a vintage stamp pointing
  outside the build's own history is polluted provenance. Fix: the instrument now refuses
  to write when any path-vintage stamp is not an ancestor of `build_head_sha`. The shipped
  JSON is the patched instrument's consecutive-run pair, byte-identical (`cmp` clean) and
  byte-identical to the pre-patch verification run.

**Multiplicity — the count is the disclosure, nothing is corrected away.** 8,760 Q1/Q2
cells · 1,882 era cells · 144 S5b cells · 59 states · 15 outcome classes · both rank
directions printed for every feature. Read any single cell against those counts. The
headline states are not the survivors of a search: S2/S4/S6 were pre-registered families
and the *ordering across their bands* — monotone in the holdout, 6/6 eras — is what carries
the reading, not any one cell's p-value.

---

## §10 UNIVERSE, SPLIT, VINTAGE

**Universe.** 1,842 curated names; 4,831,775 live bars 2011-01-01 → 2026-08-07; 60,141
tolerant limit-up closes; 4,119,723 cold bars; **4,005,053** cold rows analysed after
embargo.

> **SURVIVORSHIP + COVERAGE, stamped on every table above.** The 1,842-name store is
> **35.37% of active SH/SZ names, 0 of 329 BSE**, median cached cap 187.7 亿 against 37.85 亿
> for the omitted names, and **36.09% of canonicalised zt-pool names**. Delisted names are
> absent, so every rate here is measured on names that lived. **Every number in this receipt
> is a large-cap-slice statistic on survivors, and nothing in it supports a claim about
> small caps in either direction** — that remains a sampling-gap prior, never proven alpha.
> The full-A exact-plane re-run (reconciliation §8 item 4) is the gate to anything beyond
> display tier.

**Split** — reconciliation ledger §7, adopted verbatim: train 2011-01-01→2019-12-31 ·
calibration 2020-01-01→2023-12-31 · locked test 2024-01-02→2026-06-12 · vendor-rich audit
2026-06-15→2026-08-07. "Fit" above = train + calibration; "holdout" = locked test.

**Embargo — a disclosed extension.** The ledger mandates 10-session purges. A 10-session
purge cannot cover a 20-session outcome window, so the mandated 10 is kept as the floor and
widened to `max(10, max H) = 20`, applied uniformly so the H = 5/10/20 tables stay
comparable. The mandated-10 arm is printed as a sensitivity in
`split_and_embargo.embargo_sensitivity`.

**Closure-tolerant forward chain.** v0's 10-calendar-day pair rule, reused as a *step* rule,
truncates every open window market-wide at any exchange closure longer than 10 days — W3-A
measured 7 such closures and that truncated tail was the whole of its first-draft flagship
illusion. This lane pre-registers a 21-day step rule and prints the recovered-row receipt.
**That lesson is paid once and not re-paid here.**

**Basis.** `data/china_stocks_raw` is **back-adjusted** (L1's measured correction to v0's
"nominal" header). Adjustment preserves returns, so every indicator, drawdown, MA, volume
z-score and window return is unaffected; only the round-to-tick limit *price* is, and v0's
0.2% tolerance is the cushion for exactly that. Suspensions are zero-volume stale-price
placeholder rows, and every conditioning bar, outcome bar and chain step is live-gated.

**Event-tape vintage — stamped honestly, and made irrelevant by construction.** The
reconciliation ledger §3 describes a healed tape at 71,463 events and a Codex tape at
71,692. **Neither is the tape on main at this commit** — main carries the legacy store plus
nightly appends, and the named recovery branch `claude/cn-limit-phantom-recovery` carries
the 60,428-row legacy store, not the heal. This instrument therefore **does not consume the
tape as input at all**: it re-derives every event from `china_stocks_raw` with v0's tolerant
detector — the same basis every W1–W3 receipt used — and reports the tape only as an
independent cross-check. No tape-vintage ambiguity can move a number in this file. §11.1
(vintage is part of construction identity) is satisfied by construction rather than by
assertion.

---

## §11 ORE LEDGER — what this lane did NOT test

A null closes the **construction tested**, never the search space. Nineteen items are
carried in the JSON; the ones that most constrain the reading above:

1. **PRICE-LEVEL / TICK-GRANULARITY interaction with the tolerant rule — the named artifact
   risk for this receipt's own headline.** The headline state is deep drawdown, which is
   also a *low price* state, and the PRIMARY event definition rounds the limit to 0.01 then
   allows 0.2%. At a 2.00 price the tick is 0.5% of price — wider than the cushion — so the
   effective width is not constant across the price range, and a back-adjusted store's
   printed price is not the traded price. **This cannot be settled on this basis.** The
   exact-cent plane (reconciliation §5) settles it. Carried as a named, unquantified risk.
2. **PIT market-cap / price-level stratified arm** — the vol-matched control holds session
   and own-vol fixed but not size, price or liquidity, and the artifact above rides that
   same axis.
3. **The session-phased 2D bar** — their own research fix, not wired into production; a pure
   re-run may move every 2D number here.
4. **Confluence parameter relaxations** — nothing separates "this construction is null" from
   "this construction is null *at their live settings*". The neighbourhood was not scanned.
5. **Other momentum families entirely** (Trend Waves, Pulse, price MACD, ADX, squeeze).
6. **Other timeframes** (1D, 5D, weekly, their monthly investor-cycle gate).
7. **Washout rulers other than the 250-session high**; continuous rather than banded.
8. **Under-MA variants** (50/100/250, EMA, slope, distance-not-side, stacking).
9. **Sector breadth beyond a fixed depth share**; THS 題材 concepts instead of the coarse
   sector map; the current-membership caveat needs a PIT membership store that does not
   exist here.
10. **Accumulation footprints beyond vol-z in a low-vol base** — dry-up, up/down volume
    asymmetry, range compression, OBV. v0's f2 turnover remains impossible: no CN store here
    carries shares outstanding per date.
11. **Chip-distribution deepening** — the operator's named instrument; blocked on cyq_chips
    history.
12. **LHB (龙虎榜) and news conditioning** — the mechanism hypothesis is *news release after
    accumulation*, and nothing in this file observes news, 特停, inquiry letters, 减持 or LHB
    seats.
13. **Theme-relay and cross-band telemetry states.**
14. **The outcome class itself** — time-to-first-board as survival, the 20% board as its own
    class, multi-board runs from cold, soft-label cum/w.
15. **The cold-window length K = 20** — K ∈ {5, 60, 120} define different populations.
16. **Per-name effects** — whether any lift is a handful of repeat names.
17. **Full-universe F3 re-run**, 18. **suspension-aware confluence input**, 19. **an entry
    book on any surviving state** (W3-C's machinery exists; the auction would bind).

---

## §12 WHAT THIS DOES NOT ESTABLISH

- No cell here is a promotion, a gate, a ranker or a sizing input. **Display tier.**
- **No entry book is implied and no expectancy is quoted.** Any implied-entry return read
  off this file must first be re-priced open-anchored per W3-C, whose measured law is that
  the T+1 auction removes the fills.
- `peak_*` outcomes are a **foresight upper bound**, not an attainable exit.
- S4 breadth and f4 sector heat use **current** sector membership applied to 15 years of
  history; neither is a point-in-time sector statistic.
- S5b has **no out-of-sample arm at all**.
- Survivors-only, large-cap slice — see the §10 stamp.
- **A null on any state closes that construction only.** S1's null is a null *on the Golden
  Oracle at its live settings, as a standalone cold-universe first-board state*. It says
  nothing about momentum confluence in general, nothing about the Oracle's own product
  purpose, and — per the epistemics law — a factor that is null standalone is **retained as
  a confluence input**: S1 × S2 (2.23×, vol-matched 2.07×) is *stronger* than S2 alone on
  the same holdout, and the Oracle-long state is where the feature battery ranks best (§6).
