# Personality-Tailored Timing — handoff charter (FOR the next Fable session)

Status: HANDOFF (not adjudicated). Written 2026-07-24 at operator request as Fable
limits ran out. Operator's ask, verbatim core: *"different stocks require different
uses of indicators … our current gating system for Prophet does treat them all the
same way … Should we be grouping stocks into groups or even assessing each stock's
personality singularly … always tailor fit does better than one size fits all …
figure out one stock completely … as long as we become best friends with this stock
and know all its quirks, we can much better predict what it's going to do."*

The receiving session should read: this file → §3 asset audit (every path) →
`MAG7_WASHOUT_REENTRY_PREREG.md` §2b/§2d → `STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md`
(results in full) → then execute §2. Do not build anything before the audit.

---

## §1. Fable's assessment (delivered to operator 2026-07-24; position of record)

**What is right.** Personality heterogeneity is real and OUR OWN data shows it three
ways this week: NVDA 37% vs TSLA 61% good-rate on the identical washout tool (MWR
§2b); idiosyncratic home timeframes (MCD 1W +2.22% vs 2W −0.03% — MWR §2d, where the
"MCD is flat" one-rung argument was formally retracted); trend-personality uplift
gradient across 1,623 names (chop −0.59% → strong-trend +0.58%). The first-principles
basis is also sound and already documented in the house personality playbook: type-
conditional flows (shareholder base, index membership, dealer hedging, float) persist,
and pattern trust is type-conditional in the literature. A uniform Prophet confluence
gate therefore provably under-serves some personality classes — the operator's
complaint is legitimate and measurable.

**The frame correction (the tailor's pattern block).** "Tailored vs one-size-fits-all"
is a false binary. The statistical resolution is PARTIAL POOLING (hierarchical
shrinkage): per-stock parameters shrunk toward personality-class priors, shrinkage set
by evidence quantity. A real tailor does not design from scratch per customer — they
start from a pattern block and adjust measurements. "Figure out one stock completely"
fails on arithmetic, not philosophy: one stock yields ~15–60 timing events across 12y,
and a tool grid of even 6 constructions cannot be uniquely identified from that —
per-name selection noise WILL dominate unless strength is borrowed from (a) the class,
(b) persistence across time-halves, (c) mechanism constraints. "Becoming best friends
with the stock" done honestly = accumulating the stock's PROFILE (facts that replicate
across sample halves), not memorizing its history. Note the operator's own JNJ
anecdote cuts both ways: he trades JNJ on 3D, our ladder says 1W is best — both rungs
are positive (+1.38 / +2.76), i.e. real personality signal, noisy rung selection.

**Expectation set.** This program improves conditional playbooks (washout entries,
earnings behavior, breakout trust) per name-class. It does not predict "what it does
tomorrow." That reframe was given to the operator and should be maintained.

## §1b. Operator's fuller thesis (second message) + Fable's UPDATED position

Operator's articulation, core: fixed-confluence Prophet is DOUBLY rigid (requires
alignment of two indicators at fixed timeframes — a name whose rhythm sits between
the pinned rungs can never align); market-level personality exists (HK names need 2W
washouts); the wardrobe extension — tailor multiple indicator FAMILIES per stock
("pants" = momentum/washout family; shirt/shoes/jacket = other families) and combine
for top/bottom reads; MCD's 30-year stationarity as the existence proof.

**Fable's position UPDATED on this exchange (genuine concession, on the record):**
the 15–60-events arithmetic objection applies to OUTCOME-AUDITION (backtest a grid,
keep the winner). The operator's method, properly read, is MEASUREMENT: a stock's
rhythm (dominant swing period, mean-reversion half-life, vol-cluster timescale,
trend persistence) is estimated from EVERY bar (~7,500 obs), not from dip outcomes —
well-powered, low-dimensional. Governing law for the whole program:

  **MEASURE THE STOCK, DON'T AUDITION THE WARDROBE.** Indicator settings are DERIVED
  mechanically from measured structure; historical signal events VALIDATE the derived
  setting (single hypothesis, cheap) and never SELECT among a grid. Multi-family
  outfits are projections of the SAME measured parameters (shared structure keeps
  dimensionality ~4-5, not 81 combos); an outfit-grid audition is the forbidden form.

  **Befriendability is a per-stock property**: codex carries a STATIONARITY score
  (split-era stability of measured parameters). Stationary names (MCD-class) earn
  bespoke fits; shape-shifters (META-2022, NVDA-across-eras) get class-fit + wider
  priors. "Know its quirks" includes knowing which names cannot be known.

## §2. W1 — THE DECISIVE STUDY: persistence-of-fit (run this first; everything else
is conditional on its answer)

The whole tailoring question reduces to one measurable: **is per-stock tool-fit
persistent out-of-sample, and at what altitude (name vs class vs global)?** —
now run as a HEAD-TO-HEAD of fitting METHODS (§1b):

- **W1a — audition-tailoring** (the original design below): in-sample best tool per
  name by outcome; the overfit-prone baseline.
- **W1b — structure-tailoring (the operator's method, formalized)**: per name,
  estimate structural parameters from BARS ONLY, no outcome peeking — dominant swing
  period (median peak-to-trough spacing of zigzag swings ≥1×ATR-normalized threshold,
  or spectral peak; pin ONE definition before running), AR(1)/OU mean-reversion
  half-life on 200d-detrended series, trend persistence (pct>200d), vol-cluster
  timescale. Map swing period → rung mechanically (choose the rung whose 14-bar
  oscillator window spans ≈ one full swing; pin the mapping formula before running).
  Grade the DERIVED tool out-of-sample, same ruler.
- Comparisons OOS: W1b vs W1a vs class-best vs global vs random. Fable's prediction
  (aligned with operator): W1b > W1a; if W1b also ≥ class, structure-fitting becomes
  the Prophet tailoring engine (W3/W4). Add stationarity score per name (split-era
  parameter drift) and report W1b performance stratified by it — the codex shrinkage
  weight comes from this column.

Pre-registered design (pin before running; amendments disclosed):
- Universe: all names in `data/baskets/ohlcv` with full 2014→2026 history (~1,623;
  reuse the filter in `scripts/research/mwr_phase1_conditioner_study.py`).
- Tool grid (SMALL, mechanism-diverse, pinned — this IS the multiplicity budget):
  {Stoch-RSI cross <20, RSI-MACD cross <0} × {3D, 1W, 2W} = 6 tools, constructions
  exactly as `engine/mag7_washout.py` (Wilder RSI base; reuse those functions).
- Split: fit 2014→2020-06, test 2020-07→2026 (era-split law DT-R16; also report the
  2021+ sub-split since the operator flags post-2020 dissimilarity).
- Per name: in-sample best tool by uplift (median sig fwd63 − own-baseline). Then OOS
  uplift of: (a) that tailored tool, (b) the global best tool (one-size), (c) the
  CLASS best tool (class = personality label from `personality_pit_labels.parquet`
  archetype/chart_primary — compose with the existing ontology, do NOT invent a new
  clustering first; fallback: vol×trend terciles), (d) a random tool (noise floor).
- Metrics: OOS uplift distributions (a)−(b), (a)−(c), (c)−(b); per-name tool-ranking
  Spearman across halves; fraction of names whose IS-best stays top-2 OOS.
- Inference: month-cluster bootstrap for anything pooled (signals cluster on market
  dates; names are not independent — DT-R14 ticker×time law).
- Pre-stated readings: tailored > class > global ⇒ operator's thesis earns per-name
  altitude → proceed §4 fully. class > global ≈ tailored ⇒ the altitude is the CLASS
  → build class profiles, per-name only as display. tailored ≤ random-ish ⇒ tool
  tailoring is noise; personality work stays at the setup-compat/context tier.
- Cost: one session, compute similar to the 07-24 panel scans (~minutes).

## §3. Asset audit — READ BEFORE BUILDING (compose, don't rebuild)

Existing personality estate (2026-07-07 program — ontology + labels + a compat
phase-0 already exist; the NEW thing the operator asks for is TIMING-tool tailoring,
which none of these cover):
- `research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md` (ontology + laws) ·
  `STOCK_PERSONALITY_FIELD_GUIDE.md` (measured behavior, 223-name corpus) ·
  `STOCK_PERSONALITY_OPERATOR_PLAYBOOK_BY_FABLE.md` (doctrine; display/context tier).
- `research/STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md` — 48 hypotheses, FDR family
  `stock_personality_compat`, two-way cluster bootstrap, survivorship-flagged. READ
  THE RESULT CELLS before designing anything; do not re-test its families.
- Stores: `data/research/personality_pit_labels.parquet` (2.1M ticker-days: chart /
  micro / archetype PIT labels — the class variable for §2c) ·
  `personality_compat_phase0.parquet` (64k rows) · `data/archetypes/history.parquet`.
- This week's MWR estate (the timing-evidence stream): prereg
  `MAG7_WASHOUT_REENTRY_PREREG.md` (§2b per-member, §2c environment, §2d timeframe
  ladder + Amendment 2 conditional-live) · `engine/mag7_washout*.py` ·
  `scripts/research/mwr_*.py` · reports `mwr_*.md` + `mag7_washout_scan.md`.
- Multi-TF infra to reuse: `engine/index_momentum.py` (1D/2B/3B/W RSI-MACD hybrid,
  stoch_rsi_kd, washout_turn tagging — per-carrier; extend rather than duplicate).
- Adjacent personality-ish machinery: Weinstein stage engines (PSQ promoted, PSF
  killed as win-gate — see registry), leader_radar lifecycle states, winner-autopsy
  episodes, `engine/tech_confluence.py` / `tech_catalog.py`.

Binding law (violations here have killed programs before):
- DNR §1: no LLM-originated signals; no positioning fusion; graded-board population
  contamination FORBIDDEN (any tailored lane stays out of `us_board_ledger`).
- DNR §2: "Per-ticker multi-label business-model exposure tags — DEFERRED, group-level
  taxonomy only" (TI-R2) — per-name TAGS need that ruling revisited; per-name TIMING
  profiles are a different object but cite the row. Election-cycle modulator-only row.
  MWR forced-call row + Amendment 2.
- DNR §3 rulers: ticker-cluster bootstrap without time control FORBIDDEN; era-pooling
  across 2010 break FORBIDDEN; 63d apparatus only at registered horizons (defensives
  likely need fwd126 — §2d found KO +6.67/JNJ +5.07 at 126; register the horizon).
- Epistemics: display-tier ships freely (profiles, codex cards, shadow lanes);
  AUTHORITY (gates/rank/size on Prophet) needs prereg + gauntlet + ruling. Operator
  override precedent exists (MWR Amendment 2; PRD Amendment 1) — if used again,
  record dissent + evidence, execute with a conditioner, keep kill-switches.

## §4. Roadmap after W1 (shape depends on §2's answer)

- **W2 — Personality Timing Codex (display-tier, ships freely at any W1 outcome):**
  per-name profile card = class assignment (existing labels) + the name-level facts
  that PERSISTED in W1 (home rung if stable, "washouts continue" NVDA-flags,
  fwd126-class flag, member-of-cohort notes). Artifact `data/personality_timing/
  codex.parquet` + synapse registration, display/context tier; feeds world_state as
  an honest-null lobe like mag7_washout. This is the "know its quirks" deliverable.
- **W3 — Prophet reconciliation, SHADOW FIRST:** parallel tailored-gate shadow lane
  (mirror `engine/mag7_washout_shadow.py` discipline): for names where the uniform
  confluence gate says NO but the name's class-tool says washout-entry (and vice
  versa), log hypothetical entries + grade. The uniform gate is DOUBLY rigid (two indicators AND fixed rungs must align — §1b). This MEASURES the operator's "we lose
  access to stocks where confluence isn't possible" claim — how many good entries
  does uniform Prophet miss, net of the bad ones tailoring would add? Promotion of
  any per-class gate profile into live Prophet = its own prereg + the contamination
  row respected (presentation/lane-tier, never the graded population).
- **W4 — per-class gate profiles** (only if W1 says class-altitude works): confluence
  recipe variants by personality class, shadow-compared, then ruling.
- **W5 — defensive-compounder washout gate** (pre-scoped in MWR §2d: MCD/JNJ-class @
  1W, fwd126 grading, own prereg with the 4-rung grid multiplicity counted).

## §5. Routing + acceptance gates for the next session

Routing per CLAUDE.md: main loop (Fable) adjudicates the W1 verdict; scan scripts are
mechanical-adjacent but statistical — build in main loop or via `builder` (Opus);
census sweeps may fan to sonnet `Explore` ONLY for non-code lookup. Not done unless:
(1) §3 audit visibly performed (cite what the setup-compat phase-0 concluded);
(2) W1 ruler pinned in the script header BEFORE results (MWR precedent);
(3) all three altitude comparisons reported with the month-cluster CIs, nulls printed;
(4) a one-page verdict lands in this file's §6 (append) + registry rows if anything
is killed/deferred; (5) memory updated (`mag7-forced-call-ignition-demotion` file
carries this week's arc; add a sibling `personality-timing-tailoring` memory).

## §6. W1 verdict — persistence-of-fit (Fable, executed 2026-07-25)

Ruler: `scripts/research/ptt_w1_persistence_of_fit.py` header, pinned and committed
PRE-RUN (535f4877fbd; trial-ledger family `personality_timing_w1`, config hash
`1e11abdf48022228`). Report: `reports/ptt_w1_persistence_of_fit.md`; panel artifact
`data/research/ptt_w1_panel.parquet` (1,300 eligible names, 109,974 TEST signals;
331 excluded by the ≥3+≥3-on-all-6-tools rule, incl. NVDA and PG — disclosed).
Measurement amendments A1/A2 (charter's zigzag AND spectral-peak swing-period
definitions BOTH degenerate at measurement stage — ATR normalization removes
cross-name variance; red spectra pin to the high-pass corner) were made and
disclosed PRE-OUTCOME; final W1b measurement = reversion-by-scale (per-rung
bar-return AR(1), derived rung = argmin ρ; distribution 1W 46% / 3D 31% / 2W 23%).

**1. The decisive answer: outcome-audition tailoring is NOISE (pre-stated reading
3 fires for W1a).** FIT-best tool lands in TEST top-2 at **33.2% vs 33.3% chance**;
per-name FIT↔TEST tool-rank Spearman median **−0.03** (49% positive); the audition
arm grades −0.29% OOS vs random floor −0.03% ((a)−(d) −0.26% [−0.79, +0.11]).
§1's arithmetic objection (15–60 events cannot identify a 6-tool grid) is
CONFIRMED at panel scale. Registry row appended (DO_NOT_REBUILD §2): audition-
derived per-name tool selection is a killed construction, anywhere.

**2. No class altitude exists in this evidence.** The pre-registered vol×trend
lens DEGENERATED — all 9 cells selected the same tool (S2W), so class ≡ global by
construction ((c)−(b) = 0.00 exactly). The archetype PIT secondary (118 covered
names) differentiated tools but moved +0.11% vs global (descriptive). W4
(per-class gate profiles) is UNLICENSED.

**3. Structure-tailoring (the operator's measurement method) is the only arm
above the random floor — direction consistent, magnitude unproven.** W1b-pure
(derived rung, S family, ZERO outcome input): +0.26% OOS; vs global +1.09%
[−0.32, +2.51]; vs W1a +0.55% [−0.32, +1.60]; vs random +0.30% [−0.50, +1.15];
same ordering on the 2021+ sub-split; fwd126 low-vol descriptive +0.34% vs global
−0.93%. Every CI includes 0 — the pre-stated bars for "W1b > W1a" and "W1b ≥
class" are NOT met; the engine seat is NOT yet earned. MCD is the mechanism
illustration (bars alone derive 1W — its §2d empirical home rung; W1b +3.54%
where audition chose M2W → −0.07%); TSLA is the honest countercase (derived 1W
−5.27% vs hindsight-best S2W +10.57%).

**4. One-size-fits-all also auditions poorly.** The global IS-best tool (S2W —
the MWR-family 2W stoch washout) decayed to −0.83% OOS, BELOW the random floor
point ((b)−(d) −0.80% [−1.75, +0.34]). Fit-decay is not a per-name disease; it is
what outcome-selection does at every altitude on this grid.

**5. Stationarity: real, and it hurts audition most.** W1a decays hardest on
shape-shifters (−1.08% vs −0.11% stationary tercile); the W1b gradient is humped
(+0.34/+0.51/+0.05) — the codex SHRINKAGE WEIGHT is NOT yet earned from this
column. no_reversion flag (all-ρ>0; 6% of names): W1b-pure +1.46% (descriptive
curiosity at n=78; ships as a codex flag, decides nothing).

**Rulings (all display/process tier; no authority created):**
- **R-W1-1 (KILL):** per-name outcome-audition tool selection — DNR §2 row, this
  PR. Closes the construction tested, not the search space.
- **R-W1-2 (PROCEED):** W2 Personality Timing Codex ships display-tier as
  chartered, carrying MEASURED structure only (ρ ladder, derived rung,
  stationarity_fit/full, no_reversion) — never audition-best tools (R-W1-1).
  `ptt_w1_panel.parquet` is the seed artifact.
- **R-W1-3 (PROCEED, shadow):** W3 Prophet tailored-gate shadow uses the
  W1b STRUCTURE-derived tool as its candidate (mirror `mag7_washout_shadow`
  discipline; display/accrual tier). W1's wide CIs are exactly what a forward
  shadow ledger resolves; audition-derived gates are barred by R-W1-1.
- **R-W1-4 (DEFER):** W4 per-class gate profiles — no class altitude in
  evidence; revisit only if W3's shadow or new labels produce one.
- **R-W1-5:** any promotion to authority (live Prophet gate/rank/size) remains
  prereg + gauntlet + operator ruling, unchanged.

Position of record (Fable): the operator's measurement frame survived its first
controlled test better than the audition form the house arithmetic condemned —
measurement beat audition on every point estimate, exactly as §1b predicted —
but nothing here clears a CI. The falsifiable next step is W3's forward shadow,
which accrues new evidence instead of re-slicing the same twelve years.

## §7. RULER AMENDMENT — bottom-picking, not hold-returns (operator correction
2026-07-25; BINDING on all further PTT grading)

Operator, verbatim core: *"are you assessing based on the accuracy of this signal in
picking bottoms? … our memory files specifically have this recorded — backtests on
the ability to find bottoms, NOT long-term hold success."* He is right, and the law
already existed: DO_NOT_REBUILD §3 — "63d factor apparatus applied to Oracle
reversion signals: WRONG RULER — score as reversion-capture (~20-25d time-exit)"
(#1458). Washout/bottom signals are reversion-class. The W1/census/panel PRIMARY
statistics ran on fwd63-excess (hold-return apparatus); timing metrics (adverse,
td_to_trough) were printed but carried no inferential weight. Corrections:

1. **Primary ruler set for ALL further PTT grading (pin before re-running):**
   - **MAE** (max adverse excursion, entry→trough within horizon) — primary;
   - **price proximity**: entry price vs local trough (±31td window) in %, and the
     "entered within Y% of the low" rate (report Y ∈ {3%, 5%});
   - **time proximity**: td_to_trough distribution; % within ±10td of trough;
   - **reversion-capture** per the Oracle law: entry → subsequent swing-high capture
     with ~20-25d time-exit (NOT 63d factor horizons);
   - fwd63-excess DEMOTED to secondary/confirmatory.
   - **Random-day nulls recomputed for EACH metric** (bottom-proximity has its own
     base rate in a rising tape — the 69%-class trap applies here too).
2. **Re-grade the existing estate under this ruler BEFORE any new verdicts**: the
   W1 arms (data + scripts all on main; cheap re-run), the MWR census, and the
   timeframe ladder. Note W1's verdicts are construction+RULER-scoped: the audition
   kill row stands as registered; a timing-ruler re-examination is a NEW
   pre-registerable question, not a revival of the killed construction.
3. **Expected discrimination**: proximity rulers are far tighter than fwd63 (3-month
   market noise ≈ ±8-10% swamps timing edges) — the wide W1 CIs may be ruler
   artifacts. Also expected: the census's adverse≈0 rows often fired 5-30td AFTER
   the trough — the re-grade must separate "calls the low" from "confirms the
   reset" (both useful; different products; different honest copy).
4. **MWR live gate**: Amendment-2 HIT/FAIL stays pinned for the live gate (no
   ruler churn mid-flight), BUT zero forward triggers are graded yet, so per prereg
   §1 an additive timing scorecard (MAE, proximity, reversion-capture) is lawful
   NOW on the shadow book — grade both rulers side-by-side and present both at the
   first forward ruling.
5. Sessions keep making this mistake (this is at least the second instance —
   #1458 precedent): the receiving session should add the wrong-ruler check to any
   new signal study header BEFORE choosing statistics.
