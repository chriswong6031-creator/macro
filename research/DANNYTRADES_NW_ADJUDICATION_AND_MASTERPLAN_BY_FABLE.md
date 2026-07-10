# DannyTrades → Neural Web: adjudication and masterplan

Prepared by Fable, 2026-07-06. Adjudicates the external Codex docket
`research/DANNYTRADES_SWEEP_AND_NEURAL_WEB_UPGRADE_BY_CODEX.md` (committed
as-received alongside this file) against the repo's standing rulings and the
existing quantitative anchor `research/DANNYTRADES_PHASE0.md`.

Method: 10-lane Sonnet census (extension/no-chase, sponsorship/flow, vol boxes,
long-hold, price-memory, exit/trim, operator-DQ, NW architecture+rulings,
dispersion+data-prereqs, dannytrades wiring) + 1 Opus red-team of the docket
(fidelity/soundness/missing), then Fable adjudication.

Status: rulings of record DT-R1..DT-R12. Two builds authorized (DT-W1, DT-NW-1),
both display-only. Everything else is duplicate, forbidden, routed, or parked.

> **In plain English.** Danny made his money the honest way — picking a few big
> AI-era winners, concentrating, and refusing to churn — not from his paywalled
> indicators. We already rebuilt his indicator stack a while ago and tested it:
> used the way he uses it (buy the hot confluence), it has **no** edge; used
> **backwards** it works — when his composite runs hot the stock is usually
> extended and mean-reverts, and when his "whales" pile in the move is usually
> over. We already ship that inverted read live as a caution chip on every US
> stock page. Codex's plan mostly proposes rebuilding things we already have
> (extension flags, squeeze boxes, trim grids, operator ledgers) or things our
> standing laws forbid (fused flow scores, trade-instruction JSON). What
> survives: (1) re-test our chip's two findings on a survivorship-honest panel
> so we trust them more (or kill them honestly), (2) make the chip's state
> visible to the Neural Web so the committee can cite it, and (3) unblock the
> long-parked support-level ("price-memory") study inside the Entry Intelligence
> program, whose gate condition is now satisfied.

---

## 1. Verdict on the Codex docket

**Credit.** The narrative sweep is competent and epistemically careful: it
correctly reports the phase-0 significance ledger, rejects the near-99%
accuracy claim, rejects literal buy authority, and lands the right headline
("digest, don't copy"). The Adopt/Modify/Reject frame and display→shadow
authority targets are repo-compliant in spirit. Its read of the *wealth
mechanism* (concentration × right-tail selection × low churn × secular
tailwind, per Bessembinder skewness) is sound and matches our phase-0's own
"selection, not signal" conclusion.

**Three material fidelity defects (Opus red-team, confirmed):**

1. **The volume prerequisite is omitted.** The phase-0's explicit live-shipping
   blocker (only ~1 month of per-stock volume in `data/stocks/*.parquet`) gates
   5 of Codex's 7 upgrades and never appears in its build order. As written the
   plan is non-executable. (Resolved by ruling DT-R12: the massive store is now
   the sanctioned substrate, 2021-07-06+.)
2. **The strongest evidence is buried.** "Whales LEAVING → next-month bounce"
   (lift +0.022, cluster-bootstrap CI [+0.015, +0.029], excludes zero) is the
   cleanest directional result in the anchor, and whale-CHANGE fade at t −3.9 /
   p 0.0001 (monthly, non-overlapping) is the most robust number. Codex gives
   the former one line and never states the latter, while proposing a fresh
   "sponsorship proxy zoo" that re-opens settled science.
3. **The survivorship caveat is softened exactly where it bites.** The 114-name
   survivor panel *flatters mean-reversion* — i.e. inflates precisely the
   contrarian/bottoming direction Codex's flagship upgrades chase. The docket
   never restates this.

Plus two authority-smuggling findings: `invalid_if_below` (Upgrade 1) is a
stop-loss dressed as display; `max_add` / `no_chase_above` / `invalid_if`
(Upgrade 5) are sizing/execution parameters. Both violate display-only law in
JSON form.

**Duplication rate:** consistent with every prior Codex docket (~55–75%), the
build plan is ~75% duplicate/forbidden/blocked once censused. The docket was
also blind to the fact that the DannyTrades contrarian chip is **already live**
(`dt_contra` on every US stock page since the chip PRs; also basket-level
`danny.*` fields via `engine/basket_tape.py`) — it inherited the stale
"not wired into any live page" line from the phase-0 header (fixed this PR).

## 2. Census: the seven upgrades vs. what exists

| # | Codex upgrade | Already exists (status) | Ruling |
|---|---|---|---|
| 1 | Extension/no-chase engine + state JSON | `engine/extension.py` ext_z (live, ≥8 consumers); F3 anti-chase hard-gate **shadow** accruing (flip ≥2026-Q4, R-P2.1); `cycles.py` DON'T-CHASE tag (live); `stock_score._overextended` + spotlight never-reward-a-chase clamp (live); China `extension_read` (live); **`dt_contra` chip (live)**; SLF-010 killed "one more anti-chase flag" | **DT-R2**: engine KILLED as duplicate; thin NW registration of existing chip authorized (DT-NW-1) |
| 2 | `sponsorship_pressure_proxy` ensemble + decay/retail/uncertainty | `sponsorship_state` frozen §C3 (display); SRSS shadow (#1479); CN 主力 flow velocity (IC≈−0.008, display); ETF flow (ISI R3 display-only); 13F context-only; darkpool desk (display); CMF/OBV computed but **killed as confirmers (ESX RUL-1/H4)**; signed options flow **forbidden (RO-9)** | **DT-R3**: ensemble ILLEGAL (Signal Commons R3); **DT-R4**: honest replication of the settled whale result authorized instead (DT-W1) |
| 3 | 5-definition volatility-void box family | `engine/vol_squeeze.py` = defs 1+2 live (BBW+HVP dual gate, TTM Keltner); Danny `volatility_hole` already tested → null-as-buy; S-SQ species authorized post-Fable (RUL-P8) with **arming variant BANNED** (ESX §9); atr_pctile chip | **DT-R5**: family KILLED; def-4 + retest/false-break states parked behind S-SQ phase-0 |
| 4 | `big_leader_core_eligible` + passports | `thesis_funnel.py` AND-gate shadow (LH-R2-shaped); LH-R12 Σ-ceiling 29/40; hold-book overlap = standing CUT; LEADER_STARTER_SIZE = NO-GO; theme momentum IC≈0 | **DT-R6**: composite FORBIDDEN (LH-R2); passport CUT; theme flag REJECTED; leader-book idea routed to Mastermind |
| 5 | Support-ladder DCA policy object | `poc_proxy` computed (live in chip/basket_tape); `hold.py` invalidation levels; WAIT-GRID-1 (delay ladder ≠ price ladder); **price-memory bundle parked behind EI P1.3 (Signal Commons R2)** — P1.3 completed 2026-07-05 | **DT-R7**: policy object KILLED (authority smuggling + failed anchor evidence); price-memory phase-0 now DISPATCHABLE inside EI |
| 6 | Monthly trim & thesis-break desk | TRIM-GRID-1 (6 cells, descriptive); EXIT-GRID-1 regret ledger (15 cells); reduce-gate = board's only validated edge; RUL-F3.15 role taxonomy = charter-ready spec; L2 charter blocked (two-lobe cap); exit-crowding L4 ACCRUE | **DT-R8**: DEFER to L2 charter; monthly sponsorship-decay noted as candidate input contingent on DT-W1 |
| 7 | Churn-regret / conviction-hold ledger | L4 `action_ledger.jsonl` (accruing); DQ-2 harness (3 frozen contrasts, n≥25 floor, RUL-N8); W-EX exposure log (RUL-U6: zero stats); M3 regret card queued | **DT-R9**: DUPLICATE; behavioral vocabulary recorded for future L4 grading design; no build |

## 3. Rulings of record

- **DT-R1 (docket disposition).** The Codex docket is accepted as narrative
  synthesis and committed as-received. Its build plan is not adopted. **No new
  DannyTrades engine, lobe, or artifact family is chartered.** The useful
  residue ships as two small display-only builds (§4) and three routings (§5).
- **DT-R2 (no-chase engine).** `engine/extension_no_chase.py` and its builder /
  parquet / JSON are KILLED as duplicates (census col. 3 above; SLF-010
  precedent: "nothing left for this candidate to be"). The legal gap is a thin
  consolidation surface only → DT-NW-1. `invalid_if_below` and
  `nearest_support` keys are REJECTED: the former is a laundered stop-loss, the
  latter belongs to the price-memory bundle (DT-R7 routing). `no_chase_age`
  (= `bars_since_capit`, already computed in EI P2.5 research runs) belongs to
  the EI program if it ever ships live — not to a DannyTrades artifact.
- **DT-R3 (sponsorship ensemble).** `sponsorship_pressure_proxy` as an ensemble
  is the exact fused-escalating-composite shape Signal Commons R3 forbids.
  Its ingredients are independently dead or fenced: CMF/OBV/volume confirmers
  KILLED (ESX RUL-1/H4), ETF-flow alpha KILLED (ISI R3), signed options flow
  FORBIDDEN (RO-9), 13F context-only (45-day lag). `sponsorship_decay`,
  `retail_chase_proxy`, `sponsorship_uncertainty` are not chartered. The whale
  question itself is **settled science** (whale-change fade t −3.9; whales-
  leaving bounce CI excludes zero) — re-opening it as a fresh discovery family
  is REFUSED; the correct act is replication on an honest panel (DT-R4).
- **DT-R4 (DT-W1 authorized).** One pre-registered **replication** (LH-R13
  spirit: calibration, not discovery) of the two live chip reads on a
  survivorship-honest panel. Prereg frozen in §4.1. Display-only ceiling; the
  outcome rewrites the chip's printed caveat either way (including a kill).
- **DT-R5 (volatility voids).** The 5-definition family is KILLED as proposed:
  defs 1–2 duplicate `vol_squeeze.py`; the "inside/armed" state is the BANNED
  arming variant (ESX §9); def 3's volume-shelf leg is price-memory (DT-R7
  routing); the uncounted multiplicity (5 defs × 5 states × 4 roles × horizons
  × era splits with "family" undefined) is disqualifying on its face. Def 4
  (RV-collapse-after-drawdown conditioning) and the retest/false-break state
  extensions are PARKED as candidate S-SQ variants **behind** the already-
  authorized S-SQ phase-0 (RUL-P8, post-Fable queue) — clock-first: run the
  authorized study before inventing variants of it.
- **DT-R6 (big-leader eligibility).** The composite gate is FORBIDDEN (LH-R2:
  no fused admission verdicts). `concentration_passport` is already CUT
  (long-hold masterplan §5 hold-book overlap; it would also be a 4th passport
  object). `right_tail_theme_membership` is REJECTED: theme momentum IC≈0, and
  defining eligibility from names that already won formalizes survivorship into
  a feature (Bessembinder is descriptive, not ex-ante). `leader_liquidity_pass`
  / `survivable_drawdown_capacity` are NOT registered now; they may only enter
  as an LH roster amendment (mechanism + prereg, Σ≤40 ceiling, before the A2
  freeze). The portfolio-level concentration/leader-book idea is routed to the
  Mastermind repo (portfolio construction is out-of-repo by charter).
- **DT-R7 (support ladders / DCA).** The DCA policy object is KILLED:
  `max_add`, `no_chase_above`, `invalid_if` are trade instructions (authority
  smuggling), and the anchor's own pullback/DCA-adjacent evidence FAILED the
  gate (CI includes 0, payoff ≈0, tail worse). The level machinery (AVWAP/POC
  distance, volume shelves, gap maps, overhead supply, float turnover) stays
  governed by Signal Commons R2 — and R2's gate condition (EI P1.3 completion)
  **is now satisfied** (P1.3 complete 2026-07-05). The bundled phase-0 is
  hereby declared DISPATCHABLE **inside the EI program** as ONE family with one
  FDR budget. This adjudication registers the come-back; it does not run it.
- **DT-R8 (monthly trim desk).** DEFERRED in full to the future L2 Exit&Trim
  charter (two-lobe cap binding; RUL-F3.15 taxonomy is the spec of record;
  TRIM-GRID-1/EXIT-GRID-1 already cover the policy-replay surface). One note is
  carried to the L2 charter file: monthly-bar sponsorship-decay conditioning
  (faithful whale metric on the massive store) is a candidate trim-review
  input, **contingent on DT-W1 replicating**, and any such run registers
  through the R1 governor against the pooled replay family (N=37 at minimum)
  with RUL-F3.3 pre-outcome labels binding.
- **DT-R9 (operator ledger).** DUPLICATE of live infrastructure (L4 action
  ledger, DQ-2 contrasts, W-EX exposure log, EXIT-GRID-1 regret surface, M3
  card queued). The behavioral vocabulary (churn-regret / panic-sell /
  FOMO-chase / conviction-hold) is recorded here as candidate label taxonomy
  for the L4 grading-harness design wave at the n≥25 floor. No LLM may assign
  behavioral labels as data without that harness's own prereg.
- **DT-R10 (record hygiene).** The phase-0 header's "Not wired into any live
  page" was stale — the contrarian chip has been live on US stock pages (and
  the Canada builder degrades gracefully on its close-only universe). Corrected
  this PR. Anywhere the phase-0 is cited, the chip's live display-only status
  must be stated.
- **DT-R11 (architecture constraints).** (a) Any DannyTrades-derived number is
  display-only; the word "validated" only per BC-2 allowlist. (b) The measured
  momentum-dilution result (danny composite negatively correlated with 12-1
  momentum; blending drops mom IC 0.031 → 0.005) is a standing constraint: the
  composite must never be blended into any momentum ranker — it lives on the
  caution/extension side only. (c) The chip's graded band (extended/elevated/
  washed/neutral) is preferred over any new binary "do-not-chase" state — the
  decile monotonicity (Spearman −0.88) is the strength of the signal; do not
  binarize it.
- **DT-R12 (data substrate law).** `data/massive_stock_day/` (2021-07-06+,
  ~19k tickers, store-host/R2 only) is the ONLY sanctioned volume substrate for
  DannyTrades-family studies. No pre-2021 volume claims. All DT studies carry
  era-law framing and survivorship/coverage stamps. The phase-0's 1962–2026
  yfinance cache was a temporary local artifact and is not citable as a store.

## 4. Authorized builds (both display-only)

### 4.1 DT-W1 — survivorship-honest whale replication (PREREG, frozen here)

*Question.* Do the two live `dt_contra` chip reads replicate on a
survivorship-honest, era-law panel? Replication/calibration only — thresholds
and metrics are frozen at the settled study's values; nothing is tuned.

*Substrate.* `data/massive_stock_day/<T>.parquet` read directly from the store
host (main checkout); universe = S&P 500 PIT member-months
(`data/breadth/sp500_pit_membership.parquet`), window 2021-07-06 → latest
close. Names that exited/delisted mid-window are INCLUDED for their member
months (this is the point). Coverage stamps mandatory: n tickers, member-month
coverage %, count of dead/exited names included, gap handling (calendar-
continuity guard per the long-hold gap-crossing lesson — no positional windows
across per-ticker store holes).

*Metric.* `engine.dannytrades.whale_buy_fraction` on monthly bars
(`ME` resample, win=6, min-periods rule as shipped); `whale_chg` = 3-month
diff; forward returns non-overlapping (`fwd_1m`), exactly as
`scripts/dannytrades_whale.py`.

*Pre-registered tests (family `dt_replication`, m=4, BH q=0.10):*

| ID | Event (frozen) | Expected sign (from settled study) |
|---|---|---|
| H1 | whales entering: whale_chg > +10 | fwd_1m lift NEGATIVE (fade) |
| H2 | whales leaving: whale_chg < −10 | fwd_1m lift POSITIVE (bounce) |
| H3 | whale hot: level > 75 | fwd_1m lift NEGATIVE |
| H4 | whale-level deciles, monthly | mean fwd_1m monotone DECREASING (Spearman) |

Stats: ticker-cluster bootstrap CIs (reuse `_cluster_boot`), P(up) and mean-
return lifts vs. panel base rate. **Calibration controls mandatory** (EI law):
negative control (whale series permuted within ticker → all lifts ≈ 0, CI spans
0) and positive control (inject +2pp on masked rows → detected). A companion
descriptive block may reprint composite-score deciles at 63d (overlapping,
descriptive-only, labeled as such); it is NOT part of the FDR family.

*Verdict rules (frozen).* Per read: REPLICATED iff BH-surviving with CI
excluding zero at the settled sign; else FAILED. Consequences: the chip caveat
string (single source: `engine/dannytrades_chip.py`) is rewritten to cite the
honest-panel result per read. If H1 AND H2 AND H3 fail → the whale line is
dropped from the chip. If H4 fails → the extension band prints "unreplicated on
honest panel". Display-only regardless of outcome; no promotion path exists in
this prereg. Trials registered in `data/trial_ledger.jsonl`
(family=`dt_replication`, 4 rows) following the most recent study conventions;
registrations sequenced to avoid JSONL merge races.

*Execution.* Off-render research run on the store host. Builder = Sonnet;
mandatory Opus review of the study code + results (sign conventions checked
against the generated tables, not the agent's summary — Ruler-P lesson) before
Fable adjudicates the verdict.

### 4.2 DT-NW-1 — register the live chip as Neural Web tissue

*What.* Promotion, not invention (RUL-P5 pattern): expose the already-computed
per-ticker `dt_contra` state to the NW as a governed artifact.

- `scripts/build_dt_contra_state.py`: after the stock library build, aggregate
  per-ticker `dt_contra` (state ∈ {fade, bounce, neutral}, band, score_pct,
  whale, whale_chg) into `data/neuralweb/dt_contra_state.json` (small, committed):
  `{asof, universe_n, counts_by_state, states:[...]}` + the chip's caveat string
  verbatim.
- `config/synapse.yml` entry: tier=`display`, horizon_role=`context`,
  owner_program=`dannytrades`, nightly cadence, schema listed; regen
  `docs/SIGNAL_BUS.md` + bump the pinned synapse count in the SAME PR (CI law);
  declare the step in `config/dag.yml`.
- Tests: schema + state-enum test; no page/display changes in this PR.
- Authority: display context. The cortex may cite it to de-escalate (it is a
  calibrated key with a printed caveat); it may never originate, score, or
  escalate (constitution).

## 5. Routing ledger and clocks

| Item | Routed to | Action / clock |
|---|---|---|
| Price-memory bundled phase-0 (AVWAP/POC distance, shelves, gap maps, overhead supply, float turnover) | **EI program** (Signal Commons R2; gate condition met 2026-07-05) | Dispatch as ONE bundled phase-0 with one FDR budget; come-back 2026-07-20 — **CLOSED 2026-07-10: executed (EI-PM0, r4); PM2 SURVIVES (display-only), PM1/PM3 falsified, PM4 redundant, PM5 data_blocked** |
| Concentration / leader core book | Mastermind repo (portfolio construction) | Context note only; no clock |
| Monthly sponsorship-decay trim input | Future L2 Exit&Trim charter | Contingent on DT-W1 REPLICATED; R1 governor + pooled replay family |
| Void-box def 4 + retest/false-break states | S-SQ species (ESX) | Behind S-SQ phase-0 (already in post-Fable queue, RUL-P8) |
| Behavioral label vocabulary (churn/panic/FOMO/conviction) | L4 grading-harness design wave | At DQ-2 n≥25 floor (~come-back 2026-09-15 exposure-contrast clock) |
| Leader liquidity / drawdown-capacity flags | LH roster amendment path only | Before A2 freeze; consumes LH-R12 Σ≤40 ceiling; needs mechanism |
| DT-W1 verdict adjudication | Fable/operator | Same-day on results |

## 6. What we did NOT take from Danny (and why, in one line each)

- Buy-the-hot-confluence: phase-0 FAILED it; the inversion is the signal.
- Whale thresholds 35/50/75 as buy levels: hot whale = fade on our data.
- 99% volatility-hole accuracy: unverifiable promotion; our frozen version was
  null as a buy.
- Copying the concentrated book: selection-not-signal + survivorship; we don't
  ship conviction, we ship measured context.
- His churn-avoidance *behavior*: already institutionalized as slower exit
  horizons (TRIM/EXIT grids), the reduce-gate, and the long-hold firewall — we
  keep the idea, we just don't need a new ledger for it.

---

## 7. Amendment DT-W1a — verdicts of record (2026-07-06, same day)

DT-W1 ran same-day (PR #1736). The first pass REPLICATED H1/H2/H4 on the raw
basis, but the mandatory adversarial review **bounced** it: the ticker-cluster
bootstrap had no power against the calendar-time confound (panel monthly base
return −9.9%..+9.6%; effective independent N ≈ 60 months, not 591 tickers), and
the within-ticker permutation negative control was structurally powerless for
LEVEL tests (it preserves each ticker's whale-value multiset, so "whale>75"
keeps selecting winner tickers under the null — the builder's first-pass excuse
for the control anomaly had the sign backwards). The repair (time-controlled
primary basis: within-month demeaning + month-block bootstrap; level tests get
a within-month cross-ticker permutation control; real one-sided bootstrap
p-values; H4 verdict on the per-month cross-sectional Spearman per the frozen
rule, the builder-invented −0.3 threshold removed) left all four controls
clean and produced the verdicts of record:

| Test | Raw (superseded) | Time-controlled (primary) | Verdict |
|---|---|---|---|
| H1 entering→fade | −0.0333 [−0.0453,−0.0219] | −0.0062 [−0.0293,+0.0186] | **FAILED** |
| H2 leaving→bounce | +0.0445 [+0.0329,+0.0552] | +0.0119 [−0.0146,+0.0380] | **FAILED** |
| H3 hot>75→fade | −0.0092 [−0.0411,+0.0200] | +0.0262 [−0.0215,+0.0713] | **FAILED** |
| H4 level-decile monotone | pooled Spearman −0.8424 | per-month +0.0548 [−0.1059,+0.2035] | **FAILED** |

Reading: the raw contrarian lifts were ~85–90% calendar-month base rate — the
whale reads fire in months whose whole tape moved, and the pooled −0.84
monotonicity was cross-month base-rate variation, not within-month
differentiation. Scope note (binding, from the results doc): 2021-07+ is a
single bull regime with ~60 effective months — FAILED here means "does not
replicate time-controlled in this window"; it does not by itself overturn the
64-year evidence, which carries the survivorship caveat *and* (now flagged) the
same absent-time-control weakness.

**Consequences applied (frozen rules, §4.1):**

- H1∧H2∧H3 FAILED → the whale line is DROPPED from the chip: whale motion no
  longer resolves fade/bounce states and carries no directional label;
  accumulation values remain as descriptive data only (`whale`, `whale_chg`
  fields kept for schema stability of `dt_contra_state.json`).
- H4 FAILED → the extension band remains the sole state driver, downgraded to
  a weak-tilt display; the caveat (single source `_CAVEAT`, propagates to the
  DT-NW-1 synapse artifact automatically) now prints the two-panel status:
  64y survivor-panel Spearman −0.88 (no time control) / 2021+ time-controlled
  null. The word "Validated" was removed from the caveat.
- The committed `dt_contra_state.json` seed refreshes with the new states and
  caveat on the next nightly render (aggregator reads chip output).

**New rulings:**

- **DT-R13 (restoration path).** Whale-based directional claims may return
  only via a new prereg in which the 64-year panel survives month-block time
  control. Until then, any citation of the t≈−3.9 whale-change result must
  carry "computed without time control" alongside the survivorship caveat.
- **DT-R14 (time-control law).** Every future DannyTrades-family study — and
  any monthly/level-threshold event study on a regime-limited panel — must
  include a calendar-time control in its PRIMARY inference (within-month
  demeaning or month-block resampling) and a control design matched to the
  test type (time-permutation for change tests, cross-sectional permutation
  for level tests). Prereg lesson recorded: §4.1 lacked an insufficient-power
  outcome; future preregs must pre-declare a DEFERRED/UNDERPOWERED verdict
  path so a low-power null is distinguishable from a refutation.

**Follow-ups registered:**

- `engine/basket_tape.py` emits basket-level Danny-direction fields
  (`danny.buy/sell`, whale tier labels at his 35/50/75 thresholds) — a
  pre-existing display surface now inconsistent with DT-W1a. Review at next
  basket-tape touch: either relabel descriptive or attach the DT-W1a caveat.
- Optional (cheap, settles DT-R13): month-block re-run of the original
  64-year harness (`scripts/dannytrades_whale.py` + `/tmp/dtcache`-style
  panel). Un-clocked; runs only if someone wants the whale line back.

---

## 8. Amendment DT-W2 — 64-year settlement and family closure (2026-07-06, same day)

DT-W2 (PR #1751) settled DT-R13 by re-running the whale reads on the original
64-year, 112-name survivor panel with the DT-W1a time-controlled machinery
(prereg frozen at dispatch, recorded verbatim in the results doc). Verdicts of
record: **H2 (leaving-bounce), H3 (hot-fade), H4 (level monotonicity) FAILED**;
**H1 (whale-surge fade) survived pooled** (−0.0141, CI [−0.0252,−0.0031],
p=0.004, BH-survives, 775 months, all five controls clean, survives combined
8-test multiplicity).

The mandatory adversarial review then produced the decisive diagnostic: **H1 is
a pre-2010 phenomenon.** Era-split (disclosed in the results addendum):
significant 1962–1994 and 1995–2010, **null 2011–2026** (−0.0048, CI spans
zero, p=0.33; robust to within-era re-demeaning and median-year split), fragile
at the lower threshold edge (+8 fails), on a survivor panel that flatters the
fade direction — and the honest-panel test (DT-W1a H1) already failed.

**Rulings:**

- **DT-R15 (restoration DENIED; whale family CLOSED).** Pooled significance
  carried by dead eras does not restore a live directional surface. The DT-R13
  restoration path is closed. Re-opening requires the effect to clear the
  CI-excludes-zero rule WITHIN the modern era on a survivorship-honest panel —
  no clock is set; nothing accrues toward this automatically.
- **Consequence (b) applied (frozen at DT-W2 dispatch).** H4 failed on both
  panels → ALL directional tilt claims retired: `engine/dannytrades_chip.py` is
  now a descriptive positioning readout (extension percentile + accumulation
  level; state permanently "neutral"; enum kept for `dt_contra_state.json`
  schema stability). The DT-NW-1 synapse artifact inherits the caveat via its
  single-source import.
- **DT-R16 (era-split disclosure law).** Any multi-decade pooled verdict in
  this family — and any future restoration attempt — must print an era-split
  table alongside the pooled statistic; "SURVIVES (pooled)" may not appear
  without the modern-era row. (This generalizes: a pooled pass on a 60-year
  panel is a *regime-coverage* claim, and the claim must show its coverage.)

**Program state after §8:** the DannyTrades family is fully settled — engine
retained for research, chip descriptive-only, NW artifact live as descriptive
context, all directional claims retired with printed evidence, S-SQ/void-box
routing unaffected (vol-compression work proceeds under the ESX program on its
own evidence). The 2026-07-06 arc (ship → replicate → bounce → repair → settle
→ retire) is the reference example of [[ticker-cluster-bootstrap-time-confound]]
and the DT-R14 law working end-to-end.
