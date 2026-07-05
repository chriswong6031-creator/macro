# Oracle Turn Asymmetry — Assessment & Masterplan (by Fable)

**Program:** Oracle Turn Asymmetry (OTA) — turn Oracle's rotation detection into asymmetric, member-level buy opportunities with measured error rates, and upgrade the evidence system so it can *see* the edge the operator trades by eye.
**Status:** DRAFT masterplan, authored 2026-07-05 from the operator's brainstorming brief. No wave dispatched yet.
**Owner:** Fable (main loop) — generation, pre-registration, adjudication. Opus — red-team/stats review. Sonnet — harness builds, screens, data grind. Cheap LLMs — spec milling inside the grammar. Operator — tape journal, replay labels, risk decisions.
**Binding law:** `research/ORACLE_CONSTITUTION.md` (phase system, truth-in-labeling, evidence stamps). This plan adds tracks and vocabulary; it does not weaken any existing gate.
**Relationship to other programs:** extends [Oracle](ORACLE_MASTERPLAN_BY_FABLE.md) (rotation lobe); consumes Entry Intelligence's replay harness when P0 lands (EI #1302); feeds Neural Web (bus artifact + kernel cells + the earned-authority path, Neural Web constitution Article 3); does not touch Factor Intelligence (#1357) — its per-name factor context may later join as a de-escalation veto, per its own charter.

---

## Part I — First-principles assessment: is the methodology correct, and is it blinding us?

### 1.1 What the record actually says (read it precisely)

The operator's brief argues: *"confirmation only comes once the sector has run its course… of course we can't buy on confirmation, we buy on the turn, before the crowd."* Checked against the program's own adjudications, this is not a disagreement — **it is the program's own headline finding**:

- P3 R1 (verbatim): *"the edge concentrates at the earliest, noisiest detection tier and is gone by confirmation. Detection speed is the product; confirmation is description, not forecast."* Both confirmed-tier primaries were NULL; the sole 109-trial FDR survivor was **onset entry** (`ep_in_onset_21d`, +0.62%).
- P8 cond_a: entering *after* acceleration has begun is significantly **negative** — the front-run thesis proven from the loss side.
- The live compound basin is exactly the turn: **A15** (weekly washout × ≥2 opposite-complex outflow-onset nodes) passed the OOS gauntlet with a 27-year flat-magnitude edge (+1.42/+1.07/+1.25/+1.12% per era; dev +1.35% → holdout +1.19%, placebo p=0.000). **A17** is its higher-octane modern-regime variant (modern OOS: dev 2015-20 +2.50% → held-out 2021+ **+5.05% / 85% hit**).

So the system already believes what the operator believes. The real question is sharper: **why does the measured edge look like a ~+1% tilt when the operator's lived experience is high-win-rate asymmetric trades?** The answer is that the evidence machinery measures a *different object* than the operator trades. Five structural blindspots follow.

> **In plain English:** Oracle already found that the money is at the turn, not at confirmation — the backtest and your instinct agree. The gap is that the backtest measures "buy the whole sector ETF at every turn signal, hold exactly 3 months, take the average," while you trade "the best stocks inside the sector, entered near an obvious invalidation level, cut fast when wrong, ridden when right." Averages of the first object are small even when the second object is very profitable. We must make the machine measure the second object.

### 1.2 The five structural blindspots

**B1 — Condition vs trigger conflation.** P3's headline tests treated episode *states* as entry *triggers* ("buy because state=confirmed"). Human rotation trading uses states as **conditions** and times entry with separate **triggers** (washout turn, pullback reset, breakout). The factory's own data proves the frame: participation-state-as-trigger is dead across every family (rounds 1–2, n≥290 cells), while trigger×condition compounds (washout trigger × flow-displacement condition) are the only live basin (A9/A15/A17). Consequence: **"confirmed-tier NULL" means "confirmation is not a trigger," not "confirmed rotations are untradeable."** Nobody has tested *dip-buying inside a confirmed episode* (condition=episode active, trigger=member/sector pullback reset). That family is unmeasured, not falsified.

**B2 — The measurement vocabulary cannot see asymmetry.** The Oracle harness computes fixed-horizon endpoint means and hit rates only (`scripts/oracle_screen.py:381-399`). Confirmed absent *from the Oracle evaluation harness*: MFE/MAE, stops, R-multiples, exit policy, path measures, vol-adjustment, drawdown (evaluation-machinery audit, 12-item gap list). Two killers:
  - A turn entry's defining property is a **near, structural invalidation** (the washout low). A +0.45% pooled 63d mean is fully consistent with, e.g., 60%+ of entries never trading 1 ATR below entry while winners run 2–4R. The current vocabulary literally cannot express that fact.
  - **Horizon mismatch:** median Tier-S episode lasts **17 sessions** (atlas p50; p75=25, p90=36 — right-skewed). For the *median* episode, ~46 of a 63d endpoint's sessions fall after the episode has ended — post-episode noise averaged into the grade. The trade the operator takes ends when the rotation ends, not at day 63.
  - The repo already owns the right vocabulary: `engine/grading.py` — `terminal_state()` barrier race (STOPPED / DEAD_MONEY / CUSHIONED / CLEAN_LIFTOFF), `forward_metrics()` with `fwd_mfe/fwd_mdd` at 5/10/21/63/126. It is wired to every stock program and to **zero** Oracle events.

**B3 — Node-level ETF measurement dilutes the tradeable object.** The operator "buys their members." A sector ETF's return is leaders + laggards + dead weight averaged; rotation alpha concentrates in leading members (dispersion within a turning sector routinely dwarfs the sector move). Today Oracle is fully decoupled from the member machinery: no surface consumes episode states for stock entries (fusion inventory — `scripts/build_subsector_confluence.py` double-gates on §7 subsector BUY/SELL states, not Oracle episodes). The joins exist (`data/oracle/rotation_groups.json` → `data/baskets/membership.json` → tickers; PIT filter `data/breadth/sp1500_pit_membership.parquet`), the stock triggers exist (T1–T3 confluence, COILED/STAR, W-ARM), the stop-aware grader exists. The fusion is unbuilt.

**B4 — The false-kill machinery.** The gauntlet is engineered against false positives; its false-**negative** rate at realistic effect sizes is high, and kills read as facts:
  - *Power:* cond_b showed +1.14% increment at n=194 and was verdicted "NULL as registered." The harness's own printout shows the problem twice over: the reported CI half-width (±4.3%) and the boot-p (≈0.24) imply standard errors that differ by ~2× (an unreconciled inconsistency — clustering/design-effect handling), and under *any* reconciliation the power to detect a true +1% at that n was well under one-half. "Not proven at low power" and "absent" are different claims; the vocabulary has no word for the difference (W4.2 mechanizes the fix: reconcile the SE computation, then print MDE@80% on every verdict).
  - *Era gate:* ≥3/4 eras with era-1=1999-2014 structurally executes modern-regime edges (A17 was killed once this way, correction on record) and anything on 2021+ columns (breadth/cohesion/turnover — coverage memo) can never pass. The gate is right for timeless claims and wrong as a universal floor; the labeled modern track it needs is designed but unbuilt.
  - *Pooling:* pooled nulls coexist with real conditional structure (XLE washouts +1.79% vs +0.45% pooled; routing survivors are high-VIX-only). Pooled NULL ≠ conditional NULL; per-cell claims need registration, but the *reporting* of pooled nulls as family verdicts trains us to stop looking.
  - House law already exists for this (`oos-fail-regime-change-vs-overfit`: scrutinize kills as hard as promotions); it is not yet mechanized in the verdict vocabulary.

**B5 — The detection ladder is blur-compressed at exactly the moment that matters.** Onset→confirmed conversion is **99.7%** (749→747, atlas) and confirmation has two paths — Path A "onset held 5 more sessions," Path B a cohesion spike that can confirm *same-day* (`engine/oracle/episodes.py:496-508`). So "confirmed" carries ~zero incremental information — it is onset+0–5d by construction, i.e., *late by precisely the amount that kills the edge* (+0.62% at onset → ≈0 at confirmed). Meanwhile the real quality question — **which onsets are false starts (34–38% by the 5d measure) vs real turns** — has no discriminator. The FSM tells you *that* something is turning with a 1-in-3 false-start rate; it does not tell you *which* turns are worth risk. That classifier is the single most direct "reduce noise / reduce false positives" build available, and the training set (749 Tier-S + 5,653 Tier-M episodes with full panel/graph/analogue context) already exists.

### 1.3 What the methodology gets right (and must not be weakened)

Pre-registration before results; mining made legal by counting (trial ledger + params-hash identity); placebo nulls matched on timing/regime; OOS gauntlets; forward accrual from day 1; truth-in-labeling; the LLM firewall (specs, never evaluation code; the mechanical screen is the sole judge — round-1's A4 "mirage" and confabulated mechanisms proved why). **The operator's challenge is not answered by loosening any of this.** Every fix below *adds measurement vocabulary, tracks, and expression layers* under the same discipline. Rigor wasn't the mistake; measuring the wrong object was.

### 1.4 Verdict

- **Is the methodology "currently correct to do"?** The epistemics are correct and unusually honest. The *measurement model* is incomplete in five specific, fixable ways (B1–B5), each documented from the program's own artifacts.
- **Is rigid backtesting causing us to be blindsided?** Partially, yes — with receipts: A17 was wrongly killed once (corrected); the round-1/2 "participation basin dead across every era" verdict was partly an artifact of 2021+ column coverage; cond_b's "NULL" is a power statement misread as an absence statement; the confirmed/onset distinction was tested as if informative when it is 99.7% degenerate; and a 63d endpoint grades 17-session episodes. None of these are fraud — they are vocabulary limits. The system cannot currently *represent* the trade the operator makes, so it cannot find it, validate it, or hand it to Neural Web.

---

## Part II — The asymmetric-entry thesis, stated formally

**Definition.** An asymmetric buy opportunity is an entry where (a) a *structural invalidation* sits near — the washout low / turn-bar low — so the loss branch is small and known in advance; (b) an *arming condition* says fuel exists for the win branch (opposite-complex displacement: money must come from somewhere — the operator's own mechanism, now A15's engine); (c) expression is at the **member** level where dispersion pays; and (d) the exit follows the episode (exhaustion state / trailing structure), not a calendar.

**The temporal ladder** (each rung already has an evidence row):

| Rung | What it is | Evidence today |
|---|---|---|
| 1. Washout | weekly capitulation condition (`washout_w`) | standalone: NULL pooled (P8) — a condition, not a trigger |
| 2. Turn trigger | K-over-D upcross, `cohesion_rebuild`, member re-ignition | cohesion_rebuild-as-primary: weak (R3 fence); **× flow-stress: live (A15/A17/A9)** |
| 3. Onset | acceleration detected (accel_z ladder) | +0.62%/21d, sole FDR survivor; false-start 34–38% |
| 4. Confirmed | onset + 0–5 sessions | ≈0. Information-dead (99.7% conversion) |
| 5. Exhaustion | counter-acceleration | exit-side onset edge +0.50%/5d (display-with-edge) |

**The buy zone is rungs 1–3**, sized by rung-2 quality and rung-B1 conditions, stopped at rung-1/2 structure, exited toward rung 5. Everything in Part III exists to measure, filter, and productize this ladder — then hand it to Neural Web with earned authority.

> **In plain English:** buy fear (washout) only when the money has somewhere to come *from* (the other complex is bleeding), enter on the actual turn bar in the *strongest members*, put the stop just under the turn low, and get out when the rotation's own engine (acceleration) dies — not on a fixed date. Each piece of that sentence already has data behind it; what's missing is the harness that measures the whole sentence at once.

---

## Part III — The program

Seven waves. Each is display-first, pre-registered where verdicts are claimed, and lands its nulls in print. Heavy compute stays off the render path; nightly additions are small artifacts.

### W0 — The Asymmetry Re-Grade (measurement first; no new signals) — THE KEYSTONE

Re-grade the **entire existing event catalog** with stop-aware, path-aware metrics so we can finally see the object the operator trades:
- Events: 749 Tier-S episode onsets (IN and OUT separately), P8 washout entries (639), A15 fires (2,351), A9 (438), A17 (262), the 6 surviving routing cells, `ep_in_onset` events. All PIT dates already exist.
- **W0.1 — close-to-close pass (cheap, first):** `terminal_state()` barrier race + `forward_metrics()` (MFE/MAE) as they exist. Honesty label: `engine/grading.py` is **close-only** (`forward_metrics(close, …)`), so W0.1 R-multiples are close-to-close approximations that *understate* intraday MFE/MAE — printed as such on every table. Vol-scaled barriers (stop/targets in σ-units from close-vol) replace the ±5%/+8% stock constants, which are mis-scaled for sector ETF vol.
- **W0.2 — intraday-true pass (real plumbing, honest cost):** add OHLC for the 11 Tier-S ETFs (Massive store / raw yahoo OHLC — NOT the dividend-adjusted close parquets) + an intraday-aware barrier grader variant (ATR20-based R-units, stop = entry-structure low). This is *new* machinery, not a reuse — costed as its own PR. The operator's "stop just under the turn low" thesis is only truly measurable here.
- **Exit variants (M2 law):** the **episode-relative exit** fills at the exhaustion *detection* bar (next open after the flag confirms — PIT-clean), and every table prints the exhaustion **detection-lag distribution** next to it: the FSM confirms exhaustion only after ≥3-of-5 counter-accelerating sessions, so this exit is structurally 3–5 sessions late and its R-multiples are a **floor** relative to the operator's reflex exit. A faster registered variant — raw `accel_z_5d` sign-flip, no confirmation wait — is graded alongside (PIT-clean; noisier; the speed/whipsaw trade-off measured, not assumed).
- Deliverable: **the Asymmetry Atlas** — R-multiple and MFE/MAE distributions per event family × sector × regime (VIX/SPY strata) × era; win-rate-at-stop-policy tables; time-under-water. Pure description, display-only, no claims.
- Decision value: this single wave answers "does asymmetric opportunity already exist in data Oracle produces?" If A15 events show (illustratively) ≥60% of entries never hitting −1R while median MFE ≥ +2R, the operator's thesis is confirmed *in the existing data* and W2/W6 build on fact; if not, we learn the asymmetry lives only at member level and W2 becomes the load-bearing test.
- Cost: W0.1 small (offline, existing grader); W0.2 a bounded build (OHLC feed + grader variant). **Sonnet build, Opus stats review.**

### W1 — The Onset-Quality Discriminator (noise & false-positive reduction)

Build the classifier the FSM is missing: **which turns deserve risk.**
- Label (pre-registered, one primary): terminal-state good-set membership {CUSHIONED, CLEAN_LIFTOFF} from W0's episode-relative grade — with `false_start_5d` and `da_21d>0` as secondaries.
- Features at onset day only (PIT): panel block (accel_z_5d, washout_w, stochrsi levels, persistence, vel spread), flow block (opposite/same-complex outflow-onset counts and density — the A15 engine), graph block (lead-lag leader status, routing-cell context, edge stability), memory block (kNN analogue median outcome + envelope width), regime block (vix_pctile, spy_above_200d, tlt), 2021+ columns allowed but **fenced into the modern model only** (coverage law).
- Method: simple, monotone-constrained models (logistic / shallow GBM), purged walk-forward CV, era-aware splits; Tier-S model (1998→) and modern model (2021→) trained and reported separately. Report AUC, calibration, and — the deliverable that matters — **precision/recall tables at operating points** ("keep the top 40% of onsets → false-start rate drops from 36% to X%, edge per kept event rises to Y").
- Ship: `onset_quality` 0–100 on every live episode + watchlist row in `oracle_state.json`, descriptive class, error rates printed inline (Oracle constitution §III). No gate anywhere until gauntleted. **This is deterministic scoring — no LLM origination (Oracle constitution §I firewall; Neural Web constitution Article 1).**
- Skeptic's gate (pre-registered): the score must beat two nulls OOS — (i) shuffled labels, (ii) a 2-feature baseline (accel_z_5d + vix_pctile alone). If it can't beat the 2-feature baseline, ship the baseline honestly instead.

### W2 — Member Transmission (the money step)

Test the operator's actual trade: **sector turn as condition, member trigger as entry.**
- Design: for each armed sector event (A15 fire; onset with quality ≥ threshold), take members (rotation_groups → membership.json, PIT-filtered), enter on the first member-level trigger within K sessions (T1–T3 confluence cascade; COILED/STAR bonus; W-ARM re-arm), stop per the stock programs' spine barriers, grade with `terminal_state`/`clean8_21`/`stop5`/MFE-MAE.
- The three ablations that make it science (all pre-registered): (a) same members, random-day entries (timing placebo); (b) same member triggers *without* the sector condition (trigger-alone baseline — the incremental value of Oracle is THIS delta); (c) sector condition + random members (member-selection ablation — leaders vs average). The claim "Oracle context adds asymmetry" lives or dies on (b).
- **Confound law for (b), pre-committed (the P3-R2 lesson at member level):** armed-sector member entries fire in bursts — many members of one sector trigger the same week, and A15 fires cluster in rotation regimes — so raw event counts wildly overstate effective n, and the member trigger is itself correlated with the sector condition by construction (both key off the same rotation). Therefore (b) must be judged against a **regime/timing-matched placebo** (not an unconditional resample) with a **block/cluster bootstrap** (cluster = sector-event), and effective n is printed on every table. A delta that only clears a weak unconditional null is a mirage, refused exactly as the 28 routing cells were.
- Era law honesty: member-level verdicts ride the Massive store boundary (2021-07-06→, per EI P0 ERA LAW) — W2 is **modern-track by construction** and is labeled so. Dependency: EI's replay harness (P0, in flight); if delayed, W2 pilots on the store directly with the same golden-test discipline, never on mixed yahoo/Massive conventions (the recurring hazard).
- Output: the **Member Transmission Report** + a promotable compound family ("sector-armed member entries") with its own registration.

### W3 — Grammar v2 + steered recipe rounds (widen what is expressible, then mine it — counted)

Reviewed grammar additions (constitution II — each is a versioned, reviewed change; params-hash already carries grammar version):
1. `sequence`: A then B within N sessions (washout *then* turn *then* onset — today only simultaneous AND exists);
2. `cooldown`: suppress re-fires within N sessions (today adjacent-day duplicates pollute event sets);
3. cross-tier join (Tier-S condition × Tier-M trigger and vice versa);
4. member-breadth columns lifted to node level (e.g. fraction of members with fresh T1–T3 cross — computed in panel build, off render path);
5. episode-relative exits for evaluation (`exit_on: exhaustion`) so screens can grade the trade shape W0 defines.
Then run steered brainstorm rounds (the round-3 lesson: steering works) at three registered families: **F-DIP** (dip-buying *inside* active/confirmed episodes — the B1 blindspot), **F-DEST** (routing-destination entries: buy the historical sink complex's members when the source complex breaks — uses the 6 surviving cells + lead-lag graph), **F-SEQ** (full-ladder sequences). Every spec counted in the trial ledger as today; promotion floor unchanged for the timeless track.

### W4 — Evidence-system upgrade (the false-kill fixes; constitutional amendments)

1. **Modern-regime track** (already designed in the A17 correction, unbuilt): labeled track with modern sub-period consistency + within-modern OOS + pre-committed regime rationale. Main gate untouched.
2. **Power-aware verdict vocabulary**: every NULL verdict must print achieved power at the registered effect size (or the minimum detectable effect at 80% power); introduce the explicit class **UNDERPOWERED-ACCRUING** distinct from NULL. (cond_b would today read "UNDERPOWERED-ACCRUING, +1.14%, MDE@80%=+2.1%," which is the truth.)
3. **Era-gate insufficient-history awareness**: compounds on 2021+ columns are auto-routed to the modern track instead of silently failing 3/4 eras (coverage memo fix path).
4. **Kill review law, mechanized**: any KILL of a compound with positive point estimate and sub-50% power is auto-queued for one re-registration when accrued n doubles (symmetric skepticism, from `oos-fail-regime-change-vs-overfit`).
5. **Cross-market replication harness**: port the panel/episode/compound machinery to CN/HK (data exists; china-alpha + hk-canada programs own the domain knowledge). Same mechanism tested on structurally different tapes = the strongest cheap out-of-universe test AND an n-multiplier for slow-accruing families. Each market its own registration; agreement reported, never pooled silently — **with the caveat that agreement must be shown to be independent structure, not a correlated echo**: the cross-market correlation of the underlying events is printed next to every agreement claim (CN A-shares' partial decoupling from US flows is what makes the test informative; where events co-move, the "replication" is discounted accordingly).

### W5 — The operator lane (who brainstorms the factors — answered)

The P9 funnel already has three sources: Fable mechanism batches, cheap-LLM spec mills, and the system's own anomaly harvester + detection-miss ledger (nightly step 14). This wave adds the missing fourth — **the operator** — and formalizes ownership:
1. **Tape journal**: a 60-second structured capture for live observations ("rotation I can see") — date, nodes, what was seen, would-buy members, invalidation level — appended to `hypothesis_inbox.jsonl` as `type: operator_tape` (PIT-stamped, same review flow as the other collectors).
2. **Replay labeling sessions**: the Time Machine (subsector_rotation.html) becomes a labeling instrument — periodic sessions where the operator replays historical windows *blind to outcomes* and marks "I'd buy here / I'd skip this." Labels land in the inbox; Fable extracts separating features (what did marked-buys have that skips lacked?) and converts them to registered specs. **This is how eyeball skill becomes machine features — and it is falsifiable in both directions** (if the labels don't separate outcomes, that is printed too; if they do, the features join W1).
3. **Detection-miss review cadence**: the miss ledger (>2σ RS moves with no active episode) is reviewed in the same batch — every miss is either an FSM tuning case or a new-column hypothesis.
4. **Ownership table** (standing): Fable = factor book owner + adjudicator (mechanism-first batches; converts inbox → specs); Opus = red-team every gauntlet + every kill; Sonnet = harnesses/screens; cheap LLMs = spec milling within grammar (never judging); the system = surprise collection; **operator = tape + labels + the final risk decision** (LLMs never originate signals; the operator's capital, the operator's call — the machine's job is honest odds, printed).

### W6 — The Rotation Turn Desk (product + Neural Web wiring)

The user-facing and brain-facing expression, display-first:
- **Surface**: per armed sector — ladder rung, onset_quality score with error bars, the A15/A17 condition state, destination-complex context (routing + lead-lag), analogue base rates, and the **member buy-list** (trigger state, structural stop level, R-multiple base rates from W0/W2, liquidity floor) — bilingual, watermark law respected, "validated" word absent until earned (CI enforces).
- **Neural Web**: new bus artifact `oracle_turn_desk.json` (synapse-registered, envelope-stamped, staleness-contracted); every desk candidate gets a forward-ledger row from day 1; grades flow through the spine index into **kernel cells** (`family=oracle_turn`, per-regime × horizon) so Wilson lower bounds accrue mechanically; authority follows the Neural Web constitution — **display → shadow → confirmer → scored, one rung at a time, Wilson-gated**; the cond_b/A15 promotion (a registered P3-style shot once Tier-L n matures) is the named event that can lift Oracle from initiator-class toward confirmer (Oracle constitution §VI).
- The Mastermind directive stays temper-only (Oracle constitution §III R4); any board-ordering influence is a money-path surface change (Neural Web constitution Article 2) requiring the constitutional promotion path. Nothing here auto-promotes. Ever.

### W7 — Qualitative fusion (honest lanes only)

The operator asked how to backtest "so many qualitative and quantitative factors." The first-principles answer: **you don't backtest what you can't reconstruct point-in-time — you forward-test it under counting rules.** Three lanes:
- **Lane Q1 (archival-PIT text)**: news/policy/THS archives *we already collect with timestamps* may be backtested inside their archive window only, under timestamp law — **and the features themselves must be computable as-of-t**: a current-model recompute over old text (today's sentiment model, today's entity map) is a PIT trap even on honestly-timestamped archives, and demotes the factor to Lane Q2 (QI program owns the parser; features enter as filters on quant events).
- **Lane Q2 (non-reconstructable qualitative)** — narrative "feel," policy anticipation, cross-asset stories: registered as **filters** on the turn desk (never standalone signals), graded purely on the forward ledger, promoted only via Wilson bounds through the kernel. No retro-fitting, no exceptions — a qualitative backtest with hindsight-written labels is leakage wearing a suit.
- **Lane Q3 (operator judgment)**: captured by W5 and converted to mechanical features — at which point it becomes Lane-1/2 material.
FDR discipline: qualitative filters form their own registered trial family with a proposal budget (the metabolism pattern from Neural Web W7b), so "adding one more story" stays counted.

---

## Part IV — Backtesting doctrine for the many-factor problem (standing)

1. **Slot structure kills combinatorics**: every hypothesis is `condition × trigger × filter × exit` — four registered slots. Rounds explore ONE slot at a time against frozen others (round-3/4 proved steering > breadth). No free-form factor soup.
2. **Two evidence lanes**: reconstructable-PIT factors → historical event studies + gauntlet; non-reconstructable → forward ledger + kernel Wilson bounds. A composite's claim class = its weakest member's lane.
3. **Policy metrics are primary for entry claims** (terminal states, R-multiples, MFE/MAE, episode-relative exits); endpoint means remain for comparability. A claim of "asymmetry" may ONLY cite policy metrics.
4. **Power printed on every verdict**; UNDERPOWERED-ACCRUING ≠ NULL; kills with positive point estimates auto-queue for re-registration at 2× n (W4.4).
5. **Tracks, not weakened gates**: timeless (4-era) / modern (2021→, own OOS discipline) / member (Massive-era) — each labeled on every surface, per the watermark law.
6. **Cross-market replication before celebration**: any promoted US family runs the CN/HK port as its robustness echo (agreement printed, divergence investigated as regime information).
7. **Symmetric skepticism is law**: every KILL gets the same red-team the promotions get (Opus), with the stationarity assumption stated out loud (house memory `oos-fail-regime-change-vs-overfit`).

---

## Part V — Sequencing, cost, risks

**Order:** W0 → W1 → (W2 ∥ W3) → W4 → (W5 ∥ W6) → W7. W0 is one session and unblocks everything (W1 labels, W2 baselines, W6 base rates). W5.1 (tape journal) can ship day 1 — it's a collector.
**Render budget:** all study compute is offline/research-lane; nightly additions are the onset_quality field, the desk artifact, and W3 panel columns (bounded; measured before merge per render-budget law).
**Dependencies:** W2 leans on EI P0 replay harness (in flight) + Massive store; W4.5 leans on CN/HK panel ports (china-alpha/hk-canada programs consulted, not bypassed); W6 kernel wiring follows Neural Web synapse/envelope contracts.
**Top risks, pre-registered as questions:** (1) W0 may show sector-level asymmetry is thin and ALL asymmetry is member-level — acceptable, W2 carries it; (2) member-era lock (2021→) means the money claim is modern-track — labeled, and cross-market replication (W4.5) is the compensating breadth; (3) operator labels may not separate outcomes — printed either way, that is the experiment; (4) the desk must not become an implicit gate before authority is earned — Article-2 surface list audited in review each wave.

**The falsifiable core, stated once:** *if turn-timed, flow-armed, member-expressed entries with structural stops do NOT show a materially better R-multiple/terminal-state profile than their three ablations, the operator's thesis fails in data and we will print that.* The program is designed to be able to lose — that is what makes a win meaningful.

---

## §Status log
- 2026-07-05 — **W1b SHIPPED — PRINTED NULL under the operator's reversion yardstick too** (registered pre-computation; reversion21 label = absolute fwd_ret_21>0, base 0.68): M1 mean LOEO AUC 0.4836, null p 0.715 — G-A FAIL. Onset-quality closed under BOTH rulers; discrimination question moves to W2 (member level). **W5.1 SHIPPED (#1483):** operator tape journal CLI + review-inbox integration (4th hypothesis source live; adjudication stripped a fabricated sample row — the journal holds real observations only).
- 2026-07-05 — **W1 SHIPPED — PRINTED NULL.** The onset-quality discriminator found NO signal: 16 pre-registered PIT onset-day features (incl. the flow-displacement counts), LOEO over 4 eras with 63-session purge, 200-permutation null — chosen model mean AUC 0.4887 (p=0.68); the 2-feature baseline itself 0.4439; G-C operating-point lifts within noise. Verdict per pre-bound vocabulary: no onset_quality score ships; W2 member transmission conditions on RAW A15/onset events. Review: Opus audit caught a dead feature (maturity flag wired as F15) and G-C test-threshold contamination — both fixed, protocol rerun to completion, verdict unchanged; independent protocol checker CLEAN. Interpretation: at the SECTOR level, which onsets win appears not to be encoded in onset-day panel state at this n — discrimination must come from member-level structure (W2), the A15 condition itself (already the strongest known filter), or richer signal columns (masterplan open queue: options/IV/GEX). Mid-session operator rulings ([[backtest-horizon-swing-2-4-weeks]], [[oracle-reversion-metric-reframe]]: ~21d absolute reversion-capture is the house yardstick, 63d = wrong ruler) postdate this wave's pos63 primary label; a W1b rerun under the reversion-capture label is the operator's call (expectations low — sub-0.5 AUCs on all labels incl. rot21 secondaries).
- 2026-07-05 — **W0.2 SHIPPED → W0 COMPLETE.** Intraday-true pass: one-shot unadjusted-OHLC store (12 ETFs, 1998→, gitignored + manifest), H/L barrier grader (explicit short-side touch mirroring), regrade of the exact W0.1 row population (11,800 rows, frozen σ20). Concordance verdict: **the W0.1 shape survives calibration** — overall 9.5% of matured rows change terminal state; intraday finds more stops everywhere (+1 to +7pp); at 63d stops eat some winners (a15|pos63: win 58.2%→~55.7%, median R +0.61→~+0.51, stopped 27%→~33%) while at 21d intraday target-touches IMPROVE win rates (+3pp); close-only MAE understated by ~0.09R at p50 (upper-bounded by dividend-drag basis note). Review: audit caught G1 gate as a hard-coded PASS and G2 on the wrong price basis (both now enforce + abort), MAE basis disclosure added; independent recompute CLEAN. Countersigned. NEXT: W1 onset-quality discriminator (MUST re-pin vintage targets first; slice by dedup_variant).
- 2026-07-05 — **W0.1 SHIPPED** (spec pre-registered → Sonnet build → Opus adversarial audit + independent numeric recomputation [clean: 257/257 a15 events reproduced exactly] → fix round [short-side excess sign blocker; session-based dedup; routing_6 gated to p3b survivor cells] → adjudicator countersign). Deliverables: `scripts/oracle_asymmetry_regrade.py` (31 tests), `research/oracle_asymmetry/W0_1_events_graded.csv` (~12k rows), `research/ORACLE_ASYMMETRY_ATLAS_W01.md`. Fidelity gate ±5% amendment countersigned with W1 re-pin requirement. W0.2 (intraday-true OHLC pass) next; per scout, source = fresh raw yahoo OHLC pull (12 ETFs, auto_adjust=False H/L) + massive_stock_day cross-check 2021+.
- 2026-07-05 — Masterplan authored (Fable) from operator brainstorming brief; grounded in P3/P8/compound-gauntlet adjudications + mechanics/evaluation/fusion censuses (this session). Opus red-team pass applied pre-merge (verdict REVISE-THEN-PROCEED, no blockers): W0 split into close-to-close W0.1 vs intraday-true W0.2 (grader is close-only; ATR needs new OHLC plumbing), exhaustion-exit detection lag (3–5 sessions) priced as a lagged-fill floor + raw accel_z sign-flip variant, cond_b power claim replaced with the SE-inconsistency finding + MDE law, W2 ablation (b) hardened with regime/timing-matched placebo + cluster bootstrap + effective-n law, constitution citations disambiguated (Oracle §§ vs Neural Web Articles), Q1 as-of-t feature-computation requirement, cross-market echo caveat. No waves dispatched. Next action: operator read → W0 dispatch.
