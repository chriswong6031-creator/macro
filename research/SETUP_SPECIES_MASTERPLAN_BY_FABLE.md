# Setup-Species Masterplan — the Entry-Quality Moat

> **Authored by Fable, 2026-07-03**, at the owner's request, synthesizing three fixed inputs:
> (1) the owner's directive this session — *"our strength is identifying clear bottoms, the
> beginnings of sector rotations, and mean reversion … great entries with low drawdown risk and
> low dead-capital risk — not true exogenous alpha; backtesting must assess short, medium, AND
> long-term returns because some signals only suit short rotational holds"*;
> (2) the external "Investment Signal Moat" brainstorm (setup species / rejection memory /
> regime trust / explanation memory / outcome learning);
> (3) `research/US_STOCKS_FRONTRUN_AND_FEEDER_INTEGRATION_AUDIT_FOR_FABLE.md` (Opus, 2026-07-03).
>
> Drafted, then **six-lens adversarially red-teamed (41 agents) with 32 upheld findings applied**
> — including corrections to this doc's own first draft (a false OOS-replication claim, an
> inoperative multiple-testing rule, and a species whose "differentiator" was a falsified
> predicate). The red-team record lives with the wave-0 PR.
>
> This document is the **canonical program doc**. Wave sessions treat the Constitution (§1),
> the graveyard (§1.6), and the pre-registered gates as fixed inputs — a runner session may
> not soften gates, add or redefine metrics mid-wave, or "improve" the objective. Status
> accrues in §8.
>
> **Companion docs (read before any wave):** `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md`
> (measurement constitution + falsified ledger), `research/ENTRY_QUALITY.md`,
> `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md`,
> `research/BASING_AFTER_CONFLUENCE_PROBLEM_AUDIT_FOR_FABLE.md`,
> `research/ENGINE_FIX_MASTERPLAN.md` §W6-US (Buy Board 2.0 shadow; its flip criterion is
> "v2's measured precision@k ≥ live" — a **legacy, return-axis** criterion honored for that
> artifact only; see §1.3).

---

## 0. TL;DR

**In plain English:** we are not going to hunt for more indicators, and we are not going to
pretend we can pick which stock beats its sector. The repo's own large-sample study already
showed where our edge lives: buying close to a durable low, just as it turns, gets a *much
softer worst case* (avg 63-day drawdown −7.0% near the low vs −10.5% chasing) — but it does
**not** predict which name runs furthest. So the product is a machine that finds **great
entries** — clear bottoms, the first days of a sector rotation, stretched rubber bands
snapping back — and proves, with its own ledger, that those entries keep you out of
disasters and out of dead money. Every signal becomes a named **setup species** with a
mechanism story, entry/rejection rules, the regimes it trusts, and a forward ledger that
grades it. Every *rejected* signal becomes a prediction we also grade — so the gates
themselves learn. That closed loop — species → ledger → learned trust — is the moat.

*(Honesty note on the headline numbers: the 54,030 samples are 110 surviving deep-history
names at a weekly step; overlapping windows mean effective n is far below 54k and both arms
are survivor-priced, so the −7.0%/−10.5% delta is a survivor-flattered bound. A PIT re-run
on the post-W0.6 full-universe panel is registered in the experiments registry.)*

Five decisions define the program:

1. **The Safety-Net Objective (§1.1).** Signals are graded per-fire on a mutually-exclusive
   terminal-state partition (stopped / dead-money / cushioned / clean-liftoff) plus MAE-MFE,
   at **all of 5/10/21/63d** — never on round-trip returns, never on beat-buy-and-hold.
   Each species declares ONE **horizon class** (rotational or positional), frozen at
   registration, and is judged on its own class.
2. **Split the honesty contracts (§1.3).** "Timing must not claim return-alpha" stays law.
   "Timing must therefore be display-only" is over-generalized and is repealed: validated
   entry-quality levers MAY earn *surfacing/ordering* power on the entry-quality axes, via
   the established bonus→ledger→gate promotion ladder — with flip criteria on the
   constitution axes, not on return precision.
3. **Species, not indicators (§3).** Every live signal gets a registry entry: mechanism,
   who-is-selling/who-buys, evidence stack, rejection rules, archetype scope, regime scope,
   horizon class, adjacent-falsified-ideas list, and regression fixtures. Unregistered
   signals cannot rank.
4. **The rejection ledger is half-built — finish it (§5.2).** `engine/track_record.py`
   already logs and grades blocked buy-markers (it is dormant for an operational reason:
   its store is gitignored and cannot survive CI checkout — §5.2 fixes storage first).
   Upstream rejections (screens, tier cutoffs, near-misses) vanish ungraded today; we
   extend the ledger so **every rejection is a falsifiable prediction**, and gates get
   quarterly P&L attribution (what each gate saves vs what it blocks), against a closed
   rejection-reason taxonomy (Appendix A).
5. **Regime trust is consumed, not modeled (§3.4, §5.4).** All the regime axes already
   exist machine-readable (quad_vector, regime_one, risk_radar, vol_regime, MRS). We
   aggregate them into one stamped `regime_vector`, stamp it on every new ledger row, and
   *learn* per-species trust multipliers from outcome cells — under hard numeric episode
   floors (§5.4), because regimes are episodes, not rows. No new macro model; the one new
   categorical state (rate pressure) is fully defined in §3.4.

What we explicitly will NOT do (§6): alternative data, analyst-PDF ingestion, "AI opinion"
as the product, any idea in the graveyard (§1.6), and any HK generalization without its own
gate battery (HK inverts every US bottom mechanism tested so far).

---

## 1. The Constitution

### 1.1 The Safety-Net Objective

**Ruling (the owner's, formalized):** this system's job is **capital-efficient entry into
durable bottoms, rotation beginnings, and mean-reversion snaps** — the safety net is built
by the entry itself (low drawdown, low dead-capital), not by exit management or by picking
secular winners. Selection-alpha claims stay quarantined behind the existing IC/FDR
firewalls; they are a *tiebreak*, never the product.

**The per-fire terminal-state partition (primary verdict object).** Every fire resolves,
per horizon window, into exactly one of:

```
STOPPED     — hit −5% before +5%                       (the false bottom)
DEAD_MONEY  — never hit ±8% and sits < +5% at the read (capital parked)
CUSHIONED   — hit +5% before −5%, but no liftoff       (safe, modest)
CLEAN_LIFTOFF — hit the class liftoff barrier before −5% (the prize)
```

Named liftoff parameterizations (one definition, used everywhere):
- **`clean15_126`** — +15% before −5% within 126 trading days → the **positional** class
  promotion metric (126d is therefore a mandatory spine horizon).
- **`clean8_21`** — +8% before −5% within 21 trading days → the **rotational** class
  promotion metric.

Context metrics printed beside the partition, never gates by themselves: MAE / MFE at each
of 5/10/21/63d; **cushion incidence** — the % of ALL fires cushioned by day k ∈ {5,10,21},
a cumulative-incidence statistic with stop-out as the competing risk (**never** a median
over reachers — a species must not "improve" cushion speed by stopping out its slow fires;
if a central tendency is quoted it appears only beside the reach rate and n); post-cushion
breakeven-breach rate (did price return through entry after +5% — the honest version of
"a breakeven stop could be armed"); multi-horizon benchmark-relative returns (**context,
never the verdict**); recall / entry premium / lead vs labeled durable-bottom events, so
precision can never be bought by silence.

Barrier races inherit the research harness's close-basis sequential convention; the
high/low tie rule is pre-registered NOW (conservative: **stop wins on a straddle bar**)
since it becomes binding the day full-universe high/low history is wired into the spine.

**The horizon-class law (the owner's multi-horizon mandate, made structural and
fork-proof):**
- Every species declares `horizon_class ∈ {rotational, positional}` — **one** primary
  class, **frozen at registration**. "Both" is disallowed for new species (it doubles
  promotion chances); the other class's grid is printed as context only.
- Tier-A species inherit the class their validation gates actually used: the COILED-family
  gates were `clean15`-based → **positional-primary** (S1, S2); species claiming
  rotation-window economics register rotational-primary and are gated on `clean8_21`.
- A class change or addition is a **new species-version**: it consumes a registered trial,
  restarts that version's ledger, and takes a §8 row. No silent reclassification.
- Every wave report prints the FULL horizon grid for both classes (cheap), but promotion
  keys ONLY on the declared class — the grid is for the owner's eyes, not for endpoint
  shopping.

**Banned verdict metrics (inherited, still law):** round-trip trade-sim returns, equity-curve
drawdown of a trade sim, beat-buy-and-hold, precision without recall, pooled rates without
fire counts and per-name majorities, single-regime evidence, medians-over-reachers for any
first-passage statistic, and **precision@k as a flip verdict for species surfaces**
(return-axis and recall-blind on variable-width boards).

**In plain English:** we grade every signal like an entry coach, not a fund manager. Each
trade ends in exactly one bucket: stopped out, dead money, safe-but-modest, or clean
liftoff. A rotational signal is judged on the 3-week race, a positional one on the 6-month
race — declared up front, in writing, so nobody picks the flattering yardstick after seeing
the results. A signal built for a 2-week rotation can never again be killed for failing a
3-month test it never claimed.

### 1.2 Measurement law (how every number is produced)

- **One grader (target state, not current fact).** Today only `track_record` routes through
  `grading.forward_metrics`; `board_ledger` uses only the thin fill/next-bar helpers;
  `grade_us_board` and `qledger` carry private forward-return code; `china_standout_track`
  is deliberately CN-native. **W0.1 makes `engine/grading.py` the one grader** via explicit
  per-ledger migrations (§5.1) — market-native fill conventions preserved (CN T+1 HL2 +
  locked-limit exclusion; HK suspension rule; US next-bar close). The spine does not
  flatten markets; it centralizes primitives.
- **Never §7 marker dates as anchors; never same-bar fills** (the measured +5.7pp/10d
  phantom edge — it flatters exactly the mean-reversion signals this program ships).
- **Survivorship, honestly bounded.** PIT index membership exists
  (`data/breadth/sp1500_pit_membership.parquet`) but member *prices* pre-~2025 are covered
  only by the ~224 deep-history names, and the one-grader's as-of machinery accrues from
  2026-06-13. Therefore: (i) any pre-2025 member-level cohort/breadth measurement must
  print per-date member-price coverage (% of PIT members priced) and carry a
  `survivor_priced` stamp (the US analogue of the ex-US `no_dead_name_store` bound);
  (ii) where feasible, recover delisted-member prices (the `validate_reversal_nonsurvivor`
  pattern — and persist the cache; /tmp is not a data plane); (iii) promotions re-confirm
  on the post-W0.6 full-universe panel as it matures. The live nightly US board grader
  currently prices via survivor-biased closes and self-stamps "delisted names invisible" —
  **W0.1 closes this** by routing it through `grading.resolve_series`/as-of panels.
- **Multiple testing — the operative rule** (proportion metrics can't be "DSR'd", so the
  control is explicit): (1) every species×class phase-0 registers its full config grid in
  the trial ledger (`log_declared_budget` / `@register_trials`) before first run;
  (2) each primary-metric pp-spread gets an **episode-clustered p-value** (block bootstrap
  over fire episodes, blocks ≥ the longest forward window); (3) each wave report applies
  **Benjamini–Hochberg across the wave's FULL registered family** (m taken from the trial
  ledger so it cannot be understated), and promotion additionally requires **q ≤ 0.10** on
  top of the existing ≥5pp / n≥300-per-side / both-halves-sign-stable / per-name-majority
  battery; (4) `walk_forward`'s `_mt_bump` (capped at 16 trials) does **not** satisfy this
  program and must not be cited as its multiplicity control; (5) deflated-Sharpe applies
  only to legs that legitimately produce a return series (e.g. the S13 sleeve, HK/CA
  batteries) — nowhere the verdict is a proportion.
- **Regime-cell scans** additionally require the winning cell's spread to beat the 95th
  percentile of a permutation null (episode-block shuffle of cell labels) — see §5.4.
- **The wait-cost law.** Any species whose entry follows a confirmation/arming event prints
  its **entry premium vs the raw-bar baseline** beside every rate (the repo measured the
  confirmation wait itself as the entire 11pp stop-out oracle gap — waits must be priced,
  never assumed free).
- **Pre-registration:** hypotheses are registered with a mechanism story BEFORE first run
  (§4 is the initial register); failed = permanently closed in §8. Effective-n honesty
  (distinct dates, episode clustering) printed beside every rate.

### 1.3 The honesty-contract amendment

Current contracts in `bottom_radar.py`, `sector_bottom.py`, `basket_score.py`,
`narrative_rotation.py` read: timing has ~0/negative return-IC → *display-only, must not
touch selection rank*. The diagnosis is right; the remedy over-reaches (the FRONTRUN audit's
A2). Amendment, applied per-engine only when its lever earns it through the ladder:

> "MUST NOT rank or size for forward RETURN (validated: negative return-IC). MAY contribute
> graded surfacing/ordering weight on the ENTRY-QUALITY axes (terminal-state partition /
> MAE / cushion incidence), strictly via the bonus→forward-ledger→earned-weight ladder,
> with its grades published."

Promotion mechanics under this program:
- Nothing flips by decree. The ladder (display chip → ledger fields → graded bonus → gate
  weight) with pre-registered flip criteria remains the only path.
- **Flip criteria key on §1.1 axes at the species' declared class** — challenger
  matches-or-beats incumbent on stop-out AND dead-money AND cushion incidence (Wilson
  lower bound, episode-clustered n floor) — returns printed as context. The criterion is
  recorded in the registry's `ledger_binding.flip_criteria` at species birth.
- The **Buy Board 2.0 precision@k flip is honored as a pre-registered LEGACY criterion**,
  scoped to us_standouts_v2 vs the live standouts board only — it is NOT the template.
  (It is also structurally hostile to this program: the same measurement found every
  timing key net-negative on precision@k — an entry-quality board would lose a return-axis
  flip even while winning on every safety-net axis. The tension is noted for the owner;
  this program's surfaces flip on this program's axes.)
- **Gate-weight promotion** (the top rung) additionally requires the BOARD-level forward
  ledger (§5.1 rollup) to reproduce the claimed entry-quality spread at the species'
  horizon class — event-panel evidence alone caps a lever at graded-bonus (the #812 lesson:
  the only board-level test of timing-as-drawdown-reducer failed; board-level claims need
  board-level receipts).

### 1.4 Ship-shape law

Bonuses, never hard gates (a COILED hard gate recalls 7.35% of durable bottoms — gates gut
recall; the one standing exception is hygiene: ST/ADV/staleness screens). New bonuses are
sized against the `blend_sorted` 0..1 scale (one cascade tier ≈ `tier_frac`) or they
silently dominate/vanish. Every new data path registers with the sentinel commit step's
git-add set (#1026) **and must not be gitignored** — the CI runner's clean wipes ignored
files, so an ignored "persistent" store silently never accrues (this is precisely why
`track_record` lay dormant). Anything on the nightly path respects the ~67-minute render
budget and the one-build lag. New ledger appends obey keep-FIRST PIT discipline and the
correct collection lane (asia-lane rules for CN).

### 1.5 Per-market law

US is the primary panel. CN ports carry the single-macro-regime caveat and their own gate
battery (CN COILED re-grades when a second regime accrues). **HK is the standing adversarial
market — it gets NOTHING by default** (COILED inverts, G6a inverts, STAR is HK's worst
cell); any HK claim needs its own pre-registered gates. CA follows the ripe-list contract.
The China lesson generalizes and is central to this program: **the mean-reversion edge dies
when you gate it** — `cn_reversal_sleeve.assert_no_gate()` exists because every timing/
confirmation gate flipped a validated +0.56%/mo edge negative. Every species in §4 must
phase-0 its own gates rather than assume confirmation helps.

### 1.6 The graveyard (binding — re-derivation is an automatic wave failure)

Closed, with sources; the registry's `adjacent_falsified` field points here.

| dead idea | verdict source |
|---|---|
| Pre-cross "aged quiet base" / calm-VCP arming (H2) — wrong sign, worst stop-outs in program | WAVE1 §2 |
| Volume dry-up / OBV-div / up-down ratio / capitulation-spike as positive filters (H4) | WAVE1 §2 |
| Raw washout depth as a boost (H1) — works only through the cohort lens | WAVE1 §2, BOTTOM_CONFIDENCE P2 |
| Trap-context vetoes; failed-fire ("cried wolf") veto — **inverted in-sample: serial failure looked like MR fuel** (see S6 for the honest read) | WAVE1/2 |
| BASED chip as operationalized — the state (low extension since cross ∧ ¬launched ∧ ¬broken) is byte-identical to surviving-to-day-j; zero selection content | WAVE5 |
| RETEST marker **as parameterized in WAVE5 §3** — missed tightened non-inferiority by 0.19/0.60pp; a differently-parameterized retest remains open, not falsified | WAVE5 |
| Shallow-dip preference (0/8 promote; shallow side LOSES) | WAVE6 §3 |
| C-LOCKOUT serial gate (stops, not gates, cap knife damage) | WAVE7 prereg §8 |
| Trend/location guards per-event (ATR-contraction, higher-low, rising-50MA…) — exposure artifact | CONFLUENCE_TUNING §5b |
| Exit/cut rules (whipsaw manufacture); EMA8 = tail-flag only | CONFLUENCE_TUNING §8 |
| Timing as return-alpha; timing as board-level MAE reducer (#812); anticipation/bottom-radar as SIZING; leader ⅓-starter | ENGINE_FIX status, ANTICIPATION_ENGINE_DESIGN |
| Defensive-rotation → vol-shock lead (all 7 variants); EPU/GPR scored leg; cycle turn-timing as shipped | DEFENSIVE_ROTATION, NEWS_FEED audit |
| Net-liquidity expand/contract gate on the long book; 52w-high×volume breakout alpha | NOVEL_IDEAS §3 |
| A-share momentum; CN quality floors on reversal (they HURT); CN subsector-state gating (#754); turnover-surge narrative (#1051) | CHINA_HK_STOCK_SIGNALS et al. |
| HK: residual momentum, southbound-Δ, COILED, G6a, and every US bottom mechanism tested | WAVE3/6, HK_CANADA masterplan |
| US residual momentum as modern-era alpha (DSR ≈ 0.001, Sharpe −0.29 modern era) — context leg only | reports/residual-alpha-phase0 |
| Politician-trades feed (dead); pre-FOMC event-risk score | memory/event_calendar doctrine |
| **A3 washout×turn interaction** (`esx_washout_x_turn`) — the operator's literal 2W-StochRSI-washout × HTF-turn seed; KILLED as a proximity shadow with adverse marginality interaction; re-confirms the H1 depth kill fire-conditionally | ENTRY_STACK Amendment 3 §F |
| **A3 HTF-turn 2W/monthly rungs** (`esx_htf_turn` A2/A3m) — A2 NULL (knife-edge, mae21 co-primary fails); A3m monthly NULL-by-non-replication (deep-only win, fails baskets OOS, pre-registered expect-weak) | ENTRY_STACK Amendment 3 §F |
| **A3 HTF turn-count dose** (`esx_htf_turn_dose`) — monotone but NOT proximity-de-confounded (leg-3 non-monotone tell); re-measures shipped bottom_confidence tf_score; falsifier logged | ENTRY_STACK Amendment 3 §F |
| **A3 sub×turn** (`esx_sub_x_turn`) & **vol term-structure motion** (`esx_vol_transition`, expect-null) — cross-panel interaction sign flip / vol MOTION adds nothing over vol LEVEL | ENTRY_STACK Amendment 3 §F |

*A3 SURVIVORS (display-candidates, not graveyard): **E `esx_decline_geometry`** (flush-vs-grind path shape — the one clean cross-panel full-battery survivor) and **F `esx_underwater`** (real but ADVERSE — de-escalation context only). **A1 `esx_htf_turn` weekly** = DISPLAY-CANDIDATE-CAVEATED, baskets-only, mostly proximity. All CHIP-blocked until eq_band (RUL-28).*

**In plain English:** we've already paid tuition on these. The registry forces every new
species to name its nearest dead neighbor and say why it is mechanically different — before
any compute is spent.

---

## 2. What we already have (the asset map)

The 2026-07-03 ten-agent survey (gating/scoring, outcome tracking, regime, cohort/breadth,
ledgers, stock context, research verdicts, data plane, CN/HK/CA transfer, + adversarial
critic) established that this program is ~70% **wiring**, not building:

**Validated levers (the species seeds):** proximity-to-low as the dominant drawdown lever +
freshness as staleness penalty (`engine.cycles.entry_quality`, calibrated); multi-TF
turn-confluence as the durability axis with washout-depth as knife-temper
(`bottom_confidence`); **COILED sector-cohort washout** (+6.7–7.5pp clean15, −5.5pp
stop-out, dead-money halved; monotone in cohort fraction; shipped US+CN as graded bonus —
CN channel: `engine.coiled` → `build_china_library._cn_bonus` → `blend_sorted`);
**COILED-FIRE C2** union trigger (recall 14.2 vs 12.4, lead 3d vs 6d; shipped as
chip+ledger); **G6a donor-unwind** rotation context (+5.8–6.0pp clean15, US-only,
chip+ledger); STAR bullish-divergence co-condition (stop relief only WITH cohort);
dislocation Fed-put switch (the **median-drawdown clause is the only robust one**; hit-rate
arms are n=37 vs n=10 episodes — context); GATE0 ladder extremes; T1–T4 cascade with
held-out stop-out rates; CN 3M within-sector reversal sleeve (no-gate invariant);
**sector-neutral 1M reversal on the US deep panel** (full-history IC −0.046, t −9.5;
modern-era decayed — the S13 seed, `research/RESIDUAL_ALPHA_MOMENTUM.md`); insider (lone
FDR survivor) + revisions in the US event-edge blend.

**Infrastructure to extend (not rebuild):** `engine/grading.py` (the honest-grading
convention module — see §1.2 for who actually routes through it today); `engine/qledger.py`
(claims+grades substrate, promotion ladder, 7,937 claims — desk/family granularity, NOT
for per-name row volume, §5.2); three board ledgers (US 5/10/21d retro+nightly; HK/CA
5/10/21/63d; CN the fill-realism gold standard with auto-stratifying `_slice_table`);
`engine/track_record.py` (logs take AND block — dormant: gitignored store, §5.2);
`engine/coiled.py` `cohort_fractions` (generic: any ticker→metric, ticker→cohort maps);
`basket_member_context` (within-cohort RS rank — display-only, snapshot-only);
`subsector_confluence` (T1–T4 run on every member of every cohort — the per-member detail
never aggregated; its GROUP-level states already feed the Buy Board 2.0 shadow via
`group_context`, so W0.4 adds the member-share aggregation, not a new consumer channel);
`stock_fundamentals._archetype()` (6-bucket fundamentals archetype, display-only); the
regime stack (quad_vector contract, regime_one fused gate + RISK_STATE_GROSS, risk_radar
with forward ledger — its `favor_entries`/`cap_leadership` directives are carried onto
regime_one's fused verdict but **acted on by no stock-board or species surface**;
vol_regime additive-value-gate pattern; transmission driver×sector IC matrix); validation
kit (purged CV, trial ledger, BH-FDR, stop-aware walk-forward, foresight_shadow
counterfactual FDR grading); experiments registry + admin tab with come-back alerts.

**Data plane:** S&P 1500 universe with PIT membership (membership is PIT; member *prices*
are not — §1.2); EDGAR statements 1,334 names × 6 FY (annual; quarterly entries exist in
the companyfacts payload but extraction requires a one-time paced re-crawl, not a filter
flip); analyst EPS revisions 1,512 names with PIT archive accruing since 2026-06-16; FINRA
SI + daily short volume; earnings dates + surprise history (bot-wall staleness caveat);
entitled massive.com whole-market daily OHLCV flat files — **a rolling ~2025→present
window with no persistence today**: it must be captured urgently into a durable store
(§7 W0.6) and it serves the *forward* ledger and current-state coverage (daily/3D now,
weekly as depth accrues; NOT deep multi-TF backtests); 154 FRED series incl. real rates
with ALFRED vintages (key still an open item).

**The two-brains diagnosis (accepted prior, from the FRONTRUN audit):** the validated
timing/bottoming brain is quarantined to display or orphaned; the board is ranked by a
FDR-dead selection brain; the one feeder→rank channel (basket tailwind = trailing 20d
relative return) points backwards. This program is the corrective: it re-founds surfacing
on the validated brain, under the amended contract, graded on the constitution.

**In plain English:** almost every part this plan needs already exists somewhere in the
building — a cohort engine, honest graders, forward ledgers, a fundamentals classifier, a
full regime instrument panel, and a pile of validated entry levers. They've just never been
bolted together, and the strongest ones were locked in display-only rooms. This program is
mostly plumbing, with a strict lab protocol for the few genuinely new parts.

---

## 3. The ontology (the registry and its dimensions)

### 3.1 The species registry (W0.3)

`data/species/registry.json` + `engine/species_registry.py`. One entry per species-version:

```
species_id, version, name
validation_status   — phase0 | accruing | validated | falsified | retired
deployment_status   — unshipped | chip | ledger_fields | graded_bonus | gate_weight
mechanism           — who is selling, why they exhaust, who the next buyer is, why now
horizon_class       — rotational | positional  (ONE, frozen; change = new version + trial)
evidence_stack      — the conditions, each tagged {arming | trigger | context}
rejection_rules     — each tagged with the expected failure mode it prevents
archetype_scope     — stock archetypes where the mechanism applies / is hostile
regime_scope        — at birth: hypothesized supportive/hostile states; plus the species'
                      pre-registered learnable projection (≤2 axes, ≤6 cells — §5.4)
market_scope        — US / CN / CA (HK only via its own battery)
adjacent_falsified  — pointers into §1.6 + one line each on the mechanical difference
fixtures            — named regression cases that must stay excluded/included
                      (JNJ/AMAT chase-exclusion, MCD/KO based-late, Tencent trap, …)
ledger_binding      — {ledger, since, flip_criteria (§1.3 template)}
gating              — {come_back_on, cadence, maturation}   ← data-/accrual-gated species
trial_count         — multiplicity bookkeeping (mirrors the trial ledger)
```

Lifecycle: `validation_status` moves only at the monthly review (falsified/retired are
terminal and take a §8 row); `deployment_status` moves only via §1.3 flip criteria.

**Experiments-tab mirror (additive, never clobbering):** the registry writer merges into
`data/experiments/registry_seed.json` following the existing additive-entry convention —
key `species-<species_id>`, `kind: species_phase0`, `what` from name+mechanism,
`come_back_on/cadence/maturation` from `gating`, status map {phase0→registered,
accruing→accruing, validated→proven, falsified/retired→closed}. Only mirror-owned entries
are ever touched (the seed file is hand-curated source of truth for everything else).

Seeded at birth with the already-validated species (COILED, C2, G6a, T1–T4, CN
washout/EXT_PENALTY, CN reversal sleeve, dislocation switch) so the registry is *true on
day one* — not aspirational.

**In plain English:** a species card is a baseball card for a trade setup: what mistake the
market is making, what proves it, what disproves it, which stocks and weather it works in,
and its live batting average — with a rule that no setup plays unless it has a card, and no
card gets to change its own scoring rules after the season starts.

### 3.2 Stock archetypes (v2 of the existing classifier — not a new fork)

Extend `stock_fundamentals._archetype()` (6 buckets, display-only, cross-sectionally
relative) into the conditioning object species need:

- **New buckets** from data already on hand: secular-growth / broken-growth (rev & EPS CAGR
  from `_multiyear` — computed, never wired), rate-sensitive (per-name rate beta from
  `factor_betas.json`), commodity-sensitive (oil beta), financial (sector-keyed — EDGAR
  ratios are unreliable for banks), distressed (Altman zone), cyclical (sector + earnings
  variance).
- **Anchored thresholds** (absolute, not purely cross-sectional z's) so an archetype is
  stable through time; plus a persisted **historical archetype series** on the PIT panel.
- **Phase-0 before any scope-gating:** measure archetype-conditional outcome tables on the
  constitution axes. Archetypes enter species scopes only where the conditional spread is
  real — otherwise they stay card context. Naming stays "stock archetype" (vs "setup
  species") to avoid collisions.

### 3.3 Cohort context (the peer engine, W0.4)

Metrics that are one aggregation away **for the ~500 sector-mapped priced names** (each
member's T1–T4 gate and washout state are already computed; nothing sums them). Full
PIT-membership granularity is the W1.5+ target state, gated on data coverage — not the
W0.4 deliverable:

- `peer_washout_pct` — share of cohort members in multi-TF washout;
- `peer_reclaim_pct` — share reclaiming (fresh cross / 10dMA reclaim) — the *second
  derivative* of a bottom;
- `peer_macd_turn_pct` — share with fresh T1–T3 crosses.

Coverage law (pre-registered): a cohort metric is computed only where ≥70% of members have
computable state; every `peer_*` field is stamped with `coverage_pct` + n_covered/n_members;
below-threshold cohorts emit **null, never a partial percentage**.

Plus the genuinely novel discriminator the owner's thesis implies:

- **Rubber-Band Score** — the knife-vs-cohort-liquidation classifier: z of the target's
  drawdown within its cohort's *current* drawdown distribution × cohort cohesion
  (`group_flow` pairwise-corr change) × `peer_washout_pct`. High cohort washout + target
  drawdown *typical for the cohort* + rising cohesion = liquidation rubber band (buy
  candidate); target drawdown *extreme vs cohort* + low cohort washout = idiosyncratic
  knife (species-specific rejection). Echoes the validated finding that a lone washout
  skews trap while cohort washout is the sole gate-passing arming condition.

Shipped as chips + ledger fields first, per §1.4.

### 3.4 The regime vector (W0.5)

A thin aggregator — **consume, don't model** — published as `latest['regime_vector']` and
persisted daily to a **new file** `data/regime/regime_vector.parquet` (NOT an extension of
`regime_history.parquet`: four files by that name exist across data/regime, hk_regime,
china_regime, canada_regime — silent wrong-file appends are a real hazard).

| axis | source (existing) |
|---|---|
| growth/inflation quad | `quad_vector` (p, confidence, transition_momentum) |
| rate pressure | **defined here** (the program's one new categorical state): `rate_pressure ∈ {relief, neutral, pressure, panic}` — base state from DFII10 63d change (reuse `rate_inflation_transmission.real10y_chg63`) at pre-registered cut points ≤−25bp relief / −25..+25bp neutral / >+25bp pressure; escalated to `panic` when the radar rates-scare sub-score ≥ its LOUD tier; 2-consecutive-day hysteresis on all transitions; if either input carries a degraded/freshness bit the state publishes **null** and the row records `regime_vector_degraded=true` (never a default state). Cut points ship as named constants; vocabulary registers with `regime_coherence`. |
| liquidity | regime_one liquidity + `liquidity_quality` |
| risk appetite / stress | MRS + risk_radar state + `favor_entries` / `cap_leadership` |
| volatility | vol_regime 4-state + ts_slope |
| sector rotation | subsector_confluence sides + donor-unwind state |
| breadth | pct_above_50/200 + global breadth leg |
| de-escalation | radar deescalation verdict + dislocation Fed-put switch |

**Stamping rules (per-market, honoring §1.5):**
- `grade_us_board` + `track_record` rows: US regime_vector as primary stamp.
- `board_ledger` (HK/CA) and `china_standout_track` rows: their own market's regime state
  as primary, PLUS the US vector as an explicitly-labeled context column
  (`us_regime_vector`) — justified by the validated global-factors-drive-HK finding; any
  trust learned from US-vector cells on Asia rows promotes only through that market's own
  gate battery.
- Asia-lane stampers load the last COMMITTED vector (never recompute mid-lane); every
  stamp carries `vector_asof` + `staleness_hours` so stale stamps are cell-excludable.
- Rows that slip through unstamped are backfilled ONLY from the persisted daily vector for
  dates it covers (PIT-safe by construction), never reconstructed from latest-state
  sources; the residual unstamped count prints in the scoreboards.
- Letter-level honesty: `track_record` already stamps a per-name price regime
  (`regime_at_entry` — SMA200 bull/bear/choppy); that stays as its own differently-named
  axis. What no ledger stamps today is the shared MACRO vector — that is what W0.5 adds.
- `regime_history.parquet` is non-PIT (recomputed each run); historical backfills of
  regime stamps may seed **display-only hypothesis priors, never learned multipliers**
  (§5.4) — learning uses live-stamped rows only.

**In plain English:** we already have gauges for rates, liquidity, fear, breadth, and
rotation. We're not building a new weather model — we're putting all the gauges on one
instrument panel, stamping the panel's reading on every trade we log, and letting the
ledger tell us, species by species, which weather each setup actually flies in. The one
gauge we build ourselves (rate pressure) is fully specified above, down to its cut points.

---

## 4. The species book (initial pre-registered slate)

Format per species: **status → mechanism → what's already proven → what's open → gates**.
The external brainstorm's ten species are mapped; five are re-founded on validated
machinery, three are feasibility-gated on data work, two are deferred/dissolved. Five new
species are added from our own findings, plus the US mean-reversion sleeve the owner's
directive demands. Trial counts for all phase-0s register in the trial ledger. **Every
gated/armed species prints its wait-cost (entry premium vs raw-bar baseline) per §1.2.**

### Tier A — validated core, promote through the ladder (no new science needed)

**In plain English (Tier A):** these four already passed hard tests. The work is promotion
paperwork and honest bookkeeping — moving them from "interesting chip on a card" to "thing
that actually orders the board," one graded step at a time.

**S1 · Cohort Capitulation Reversal** *(= brainstorm #2; = COILED/STAR/C2 — VALIDATED, SHIPPED)*
Horizon: **positional** (inherits its validation gates' class — clean15-based).
The flagship. Open items are promotion mechanics, not validity: (a) graduate the cohort
fraction from half-tier bonus to a graded first-class surfacing input as its forward
ledger matures — flip criteria pre-registered on the §1.3 constitution-axis template
(Buy Board 2.0's return-axis criterion is legacy, not precedent); (b) widen cohort
coverage beyond the ~500 sector-mapped names — interim cheap widening (PIT-mapping names
that already have price history but no subsector map) in W1; full widening in W1.5, gated
on the W0.6 store (§7); (c) regime-cell learning — the edge sleeps in low-vol bull legs
(measured); stamped from W0.5 onward, learnable only under §5.4 floors.

**S2 · Donor-Funded Bottom** *(new name for G6a leader-cracking — VALIDATED chip, US-only)*
Horizon: **rotational** (its economics are the rotation window). Mechanism: rotations are
*funded* — capital leaving a cracking leader cohort is the marginal buyer of washed-out
laggards. Wave task: promote from chip to graded context via its accruing ledger; join
with S1 (cracking-donor × cohort-washout cells); explicitly NOT ported to HK (inverts).

**S3 · De-escalation Window** *(new species from validated pieces)*
Horizon: rotational. Mechanism: the highest-asymmetry entries cluster where a risk-off
episode is *ending* — sellers exhausted at the index level with the policy backstop
intact. Honest framing: this does not predict the shock; it detects the exhaustion of the
reaction to it — the *measurable* form of front-running the recovery leg. Evidence stack:
radar `deescalation.eligible` + trajectory receding + dislocation Fed-put switch as the
*conditioner* on S1/S5 fires. Validated pieces: put-present dislocations 63d hit 70.3%
(n=37 episodes) vs 40.0% (n=10) put-absent — **context**; the median-drawdown improvement
is the only robust clause and is S3's load-bearing prior.
Phase-0 (W1, an explicit retro-derivation — stamped history won't exist for months):
(i) rebuild the daily historical de-escalation/dislocation state series via risk_radar's
full-history subscore path through the pure trajectory/deescalation functions, joined with
the dislocation put-present series; (ii) recompute historical C2 fires from prices (the
wave-2/4 method); (iii) stamp rows `derivation='retro-recomputed'` with the not-PIT caveats
pre-registered (Tier-B flow legs inert in deep history; current-vintage calibration), and
an **Opus reconstruction check** that retro states match the live payload on the overlap
window before any stratification is read — if it fails, S3 moves to W3+.
Verdict gates (pre-registered): the confounder-controlled read, not the pooled spread —
(a) VIX-percentile-stratified within-bucket spreads are the primary table; (b) ATR-scaled
barriers run co-primary with fixed −5/+15 (de-escalation cells are elevated-vol by
construction; fixed-barrier rates are unreadable across cells — the W6 F8 lesson);
(c) a benchmark-relative re-read controls the index mean-reversion leg. Promotion requires
the spread to survive (a) and agree in sign across (b)'s two barrier schemes. Reported
beside the battery: entry premium above the episode trough and days-from-radar-peak-severity
— statistics, not gates, so the owner can audit whether these entries are early or merely
less late. Adjacent-falsified: defensive-rotation vol-shock lead (this species makes no
vol-prediction claim; it conditions entries on the *back* of the episode) — and the
vol-matching in gate (a) is exactly what that graveyard entry proved load-bearing.

**S4 · Two-Clock Re-Arm** *(= FRONTRUN Cluster D fix; BASING successor — pre-scoped, hard)*
Horizon: rotational. Mechanism: sector confirmation arrives on a slow clock after
constituent entry freshness expired; **the sector-confirmation event is the sole
hypothesized new information** — an external fact the aged name's own chart cannot supply.
Design honesty (the WAVE5 collision, addressed head-on): "low-extension-since-cross ∧
not-broken" is the falsified BASED predicate (co-extensive with survival-to-j; zero
selection content). It is retained ONLY as a **launch-hygiene exclusion** (keep JNJ/AMAT
out), NOT as selection content. S4 lives or dies on the event's marginal value.
Phase-0 comparators (mandatory, same calendar bar, same fire set): (a) a P2-style
survival-matched control — all constituents surviving ¬launched∧¬broken to that bar,
entered regardless of sector event — isolating the event's content from survival
selection; (b) the natural fresh-re-fire counterfactual — WAVE5 measured that 77.6% of
basing windows self-heal via a fresh incumbent re-fire; measure that fraction inside S4's
event windows and score the re-arm cell only on the non-self-healing remainder. Promotion
requires beating BOTH at the §1.2 bootstrap standard. Wait-cost printed per §1.2. If the
event adds nothing over survival + self-healing, S4 is closed and the two-clock problem is
declared a UI/labeling problem, not an entry problem.

**S5 · Coiled-Cohort Thrust Frontrun** *(= brainstorm #10 inverted to be EARLY, not chasing)*
Horizon: rotational. Mechanism: breadth thrusts are preceded by *member-level* turn
evidence spreading through a washed-out cohort. Arming legs, each with its own
falsified-neighbor note and a **per-leg ablation** against the validated COILED baseline
(`in_washout_ctx ∧ sector cohort ≥ 0.40`):
- `peer_washout_pct` high — H6-validated (the safe leg);
- `peer_reclaim_pct` rising — the *second derivative* leg; nearest falsified neighbor is
  WAVE5's BASED≡survival collapse, so the reclaim predicate must be a turn event (fresh
  cross / 10dMA reclaim), provably not co-extensive with time-passing;
- cohort vol-compression — **nearest falsified neighbor is H2 itself** (calm base, wrong
  sign, worst stop-outs); aggregation is a cosmetic difference until proven otherwise —
  this leg enters ONLY if its ablation shows clean-liftoff spread on top of
  washout-breadth without a stop-out tax, else it is dropped and closed.
Frontrun falsifiability (pre-registered before W2 runs): define (a) the cohort thrust
event (threshold stated in the prereg) and (b) the subsector_confluence confirmed side
flip; metric = median trading days from first `forming` stamp to each, episode-clustered,
full distribution printed; **promotion requires forming to lead (b) by ≥3 trading days
median** — otherwise S5 is recorded as "confirmation relabeling, not frontrun" and closed.
Forming and confirmed are graded as SEPARATE fire cohorts on the full constitution axes;
every wave report prints the forming-vs-confirmed split side by side (the wait-cost law).

### Tier B — new science, cheap phase-0 on existing panels

**In plain English (Tier B):** four fresh ideas we can test this quarter on data we already
own: buy the sector's beaten-up group when the market's darlings crack; check whether a
stock that "cried wolf" twice is actually coiled; watch for quiet relative strength before
the chart turns; and a US version of the China "buy the most-punished names in each
sector, monthly, no second-guessing" sleeve. Each is pre-registered with kill criteria —
half of these will probably die, and that's the system working.

**S6 · Failed-Fire Fuel** *(novel — honest restatement after red-team audit)*
Horizon: rotational. Mechanism: a name whose own trigger stopped out 2+ times in 180d may
be *late-stage washout* — serial failure as seller-persistence marker. Evidence status,
stated exactly: the failed2 inversion is **sign-stable but in-sample only** — wave-1
stocks panel +1.8pp (base3d) / +3.2pp (m2d_s3d), below the +5pp bar; the wave-2
"replication" recomputed the identical 12,797-fire stocks panel and never touched the OOS
basket panel; **within STAR the increment is a wash** (40.66 vs 41.58) — nobody has built
OR validated the species. Phase-0 therefore: run on the OOS basket panel (wave-2 machinery
already produces its fire parquets); the pre-registered PRIMARY claim is the **interaction
marginal** — (failed2 × COILED) vs COILED alone — since the nearest measured cell is
adverse; the standalone inversion is a secondary sanity read. Expectations set low; a
clean kill is a fine outcome (it also closes the graveyard row properly).

**S7 · Relative-Strength-Before-Price** *(= brainstorm #3 — genuinely open, two-sided)*
Horizon: positional. Mechanism: institutions accumulate before price confirms; RS *slope
vs cohort* turns up while price still bases. Adjacent evidence, honestly (three entries):
(a) WAVE1's rs_low — RS-vs-SPY at fresh 126d lows on these same panels was mildly positive
but ticker-unstable, and H6∧rs_low was dilutive (36.8 vs 39.3 H6-only) — weak evidence
**in the opposite direction** (low RS cleaned more); mechanical difference: S7 is RS slope
vs cohort, not RS level vs market; (b) the residual-momentum family — US mom_res fails
modern-era DSR, HK dead; difference: S7 is a washout-fire stratifier, not a cross-sectional
ranking; (c) BOTTOM_CONFIDENCE R4 restated honestly as *semi-supportive* (orthogonal
context helps; more oscillators don't). Registration is **two-sided**: the in-house prior
weakly favors LOW/deteriorating RS within washout — both signs are admissible outcomes,
and the promotion bar is beating the rs_low stratum baseline on the same panels, not
beating zero. Requires W0.4 to persist within-cohort RS rank as a *series* first.

**S9 · Bad-News Immunity** *(= brainstorm #4 — narrowed to the measurable core)*
Horizon: rotational. Mechanism: when expectations are washed out, bad news stops making
new sellers — the *reaction*, not the news, is the signal. Narrowed to earnings events
first (cleanest timestamps; surprise history exists): negative-surprise × non-negative
2-day reaction × washout state → forward constitution axes. Adjacent evidence:
`pead_sue_pit` — the repo's only measured earnings-event object — found drift mildly
positive-in-SUE (weak, FDR-fail); S9's claim is confined to the washout × muted-reaction
cell and must beat the unconditional negative-SUE baseline. Wider news-tone version gated
on W0.6 coverage widening + the tone feed's own validation. Falsified neighbor: EPU
keyword uncertainty (dead) — difference: per-name event *reaction*, not macro keyword
counts.

**S13 · US Within-Sector Reversal Sleeve** *(the owner's named strength, restored — a
product-unit species, not a gated trigger)*
Horizon: rotational (monthly rebalance). Mechanism: within-sector overreaction — the CN
sleeve's construction ported honestly: monthly, deepest-quintile within-sector reversal
fuel (test both 3M per CN and 1M per the US evidence), equal-weight, hygiene-only screens,
**assert_no_gate-style invariant** (the §1.5 law: gates killed the CN edge; the phase-0
tests whether that holds for US too rather than assuming it either way). In-repo seed:
sector-neutral 1M reversal IC −0.046 (t −9.5) full-history on the deep panel — with
pre-registered kill criteria carried from the same study: modern-era decay (2002–26
IC −0.011, t −2.4) and the 2024–26 mega-cap sign flip. Runs NOW on the existing deep panel
with the PIT restriction + recovered delisted names (do NOT wait for W0.6 — the flat files
serve the forward ledger, not this backtest). Adjacent-falsified: timing-as-return-alpha
(difference: monthly *portfolio unit*, not a per-name act-now overlay — the same carve-out
the CN sleeve enjoys); H1 depth-as-boost (difference: cross-sectional quintile portfolio,
not a board bonus). As a product-unit species it is graded on the safety-net axes PLUS
sleeve-level excess-vs-SPY (the CN-2 pattern), survivorship caveat carried. Supportive
open residue: W7 measured the below-200MA blocked population net-POSITIVE under stops on
all panels — the deep-loser cohort is not the poison the 200MA bar assumes.

### Tier C — fundamentals species, gated on the W0.6 data extensions

**In plain English (Tier C):** three ideas that need better fundamentals plumbing first —
margins turning before the story does, companies actually shrinking their share count into
a washout, and rate-sensitive names snapping back when real rates stop rising. The
collectors get built now; the science runs when the data is deep enough, on dates already
written into the registry.

**S8 · Revision-Deceleration Bottom** *(= brainstorm #6)* — revisions PIT archive starts
2026-06-16; a proper backtest needs accrual (~2 quarters) or a reconstructed vintage
proxy. W0.6 adds estimate dispersion + revenue revisions NOW so the archive fattens.
Phase-0 (registry `gating.come_back_on` carries the date): revision-impulse second
derivative × washout × post-cut price reaction as fire stratifier.
**S10 · Margin-Inflection Reclaim** *(= brainstorm #5)* — requires the quarterly EDGAR
extraction (one-time paced re-crawl, ~1,334 names — a dedicated backfill job, not a drip
ride-along; completion date → `gating.come_back_on`). Then: margin-direction-change ×
washout × reclaim, positional, archetype-scoped (consumer/industrial/retail first;
financials excluded — tag unreliability).
**S11 · Buyback-Floor Washout** *(= brainstorm #8)* — same payload extension; keys on
*realized share-count decline*, never announcements; CN precedent keeps buybacks a capped
confirmer; debt-funded buybacks are the named failure mode.
**S12 · Rate-Relief Duration Rebound** *(= brainstorm #9)* — rate-sensitive-archetype
washout fires stratified by the §3.4 `rate_pressure` state (relief cells). Adjacent-
falsified now includes **the net-liquidity gate** (its killer property — episode-scale
effective n — is inherited here), so the phase-0 gate carries a hard clause: ≥8 distinct
rate-relief episodes with ≥1 outside 2020-21, or the wave does not run. The "rates falling
because growth is dying" confound is separated via the growth axis (the species claims
rate *relief*, not rate *panic*).

### Deferred / dissolved

**Brainstorm #1 (Fresh Washout Compounder Reclaim)** — dissolved into S1 × archetype-scope
(quality/defensive-compounder cells of the S1 ledger); the WHEN machinery is identical,
only the WHO differs. **Brainstorm #7 (Broken Growth Repair)** — DEFERRED: needs
archetype-v2 growth buckets + quarterly fundamentals + the strongest rejection memory;
highest seduction risk; revisit after two quarters of ledger accrual. **The brainstorm's
alt-data tier** — out of scope (§6).

---

## 5. The moat systems

### 5.1 Outcome Spine v2 (W0.1 — the keystone)

**In plain English:** one honest scoring machine for every market's ledger, measuring the
things the owner actually cares about — worst dip, time to safety, dead money, clean
liftoff — at 1-week to 6-month checkpoints, with the survivorship holes patched and every
number produced the same way everywhere.

Five explicit sub-tasks, each with an acceptance check (split into per-ledger PRs so a
partial wave can't report the spine as done):
1. **Primitives** — extend `grading.forward_metrics` with `fwd_mfe_H`, the terminal-state
   partition (`stop_out` / `dead_money` / `cushioned` / `clean_liftoff` with the
   `clean15_126` + `clean8_21` parameterizations ported from the research harness),
   cushion incidence, post-cushion breakeven-breach, horizons {5,10,21,63,126}. Also wire
   `sp1500_pit_membership.parquet` into `grading.as_of_panel` as the pre-2026-06-13
   membership source (today the survivorship law names a file the grader never reads).
2. **grade_us_board** — delete its private forward-return/MAE code and route through
   `forward_metrics` (before/after parity check on existing grades); add the 63d lane;
   route price lookups through `grading.resolve_series`/as-of panels and retire the
   self-stamped "delisted names invisible" survivorship caveat.
3. **qledger** — migrate its private `_fwd_ret` to grading fill semantics; its entry
   convention changes from asof to next-bar — the grade-history discontinuity is stamped,
   never silent. Plus `register_batch()` (§5.2) before any volume increase.
4. **board_ledger (HK/CA)** — rewrite `grade()`'s inner loop to consume `forward_metrics`
   (schema-union stamps; suspension rule preserved).
5. **china_standout_track** — add the new axes as CN-native computations on top of
   `_t1_fill` (explicitly NOT inherited; T+1 HL2 + locked-limit rules preserved); new
   `_slice_table` stratifier columns (species_id, archetype, regime cells).

Plus: **species_id is stamped on every TAKEN fire row at emit time** (signal_gate /
board-builder), mirroring the near-miss stamping — the registry's `ledger_binding` names
the ledger; the emit-time stamp names the row. **Lead-time metric** (name-level), defined:
trading days between first surfacing (species fire or board appearance) and run start
(= the entry's clean-liftoff barrier first being hit); negative = surfaced after the run
began. (S5 additionally requires the cohort-level variant defined in its entry.)
**Species-cell rollup**, buildable as specified: nightly aggregation into per-(species ×
archetype × regime-axis-marginal × horizon-class) scoreboards — regime cells are per-axis
MARGINALS in v0 (joint cells only for pre-registered pairs per §5.4); archetype/regime
dims are nullable, populated forward from W0.5 stamps and current `_archetype()` v1,
backfilled after W0.7's PIT series lands; scoreboard rows print only at the
episode-clustered n floor.

### 5.2 The rejection / near-miss ledger (W0.2)

Three moves, smallest first — destination store: the `track_record` parquet + board
ledgers (NOT qledger: its `register()` re-reads the whole claims file per call — already
~2,800 calls/day against 4.5MB; near-miss volume would go quadratic. qledger stays at
desk/family granularity; W0.1 adds `register_batch()` and migrates the loop-callers
anyway):
1. **Make the store durable, then schedule.** `track_record`'s parquet is gitignored —
   which is *why* it never accrued (CI checkout wipes it). Migrate to a git-tracked
   append-only store (the `us_board_ledger/snapshots.jsonl` pattern) or un-ignore with a
   size tripwire in the audit suite; add the explicit sentinel `git add`; THEN wire
   `scripts/build_track_record.py` into the daily lane after `build_signal_quality`.
2. **Capture upstream rejections against a CLOSED taxonomy (Appendix A).** At
   `signal_gate`/board-builder level, log *near-misses* — candidates failing exactly one
   condition from the taxonomy — with `primary_rejection_reason`, stamped with
   regime_vector + species_id + archetype. Current truth, market by market: HK already
   appends its watch strip including knife-demotes (add the omitted `knife_z` magnitude
   to the appended schema); the CA watch strip (block_reason) is never appended — append
   it; US near-misses at signal_gate level are the genuinely new capture. board_ledger
   dedupes (date,ticker) keep-first — naive re-appends are silently dropped; extend the
   schema union, don't re-append.
3. **Grade rejections as predictions.** Same spine, same horizons. Quarterly output:
   **gate P&L attribution** — per gate: pp of stop-out saved vs pp of clean-liftoff
   blocked (count-fair, per-fire, recall printed) → verdicts {correct / too-strict /
   regime-dependent}; loosening/tightening proposals go to the monthly review as
   pre-registered candidates (human approves; nothing auto-tunes).

Pre-registered hypothesis the ledger must encode from birth: **rejection ≠ blacklist** —
the failed2 evidence (in-sample; §4 S6) suggests some rejection cohorts may OUTPERFORM
their accepted siblings. That is a finding, not a bug; it feeds S6.

Statistical honesty: this ledger is also the program's power multiplier — near-miss
cohorts are natural controls sharing time, sector, and regime with fires, which is what
makes gate attributions estimable at all.

**In plain English:** today, when the system says "no," the no vanishes. Tomorrow, every
"no" is written down with its reason — from a fixed menu, so the reasons mean the same
thing forever — and three months later we check: did the no save us money, or did it cost
us a winner? Gates that keep costing winners get put on notice — with receipts.

### 5.3 Explanation memory (W2+)

Extend the ai_desk theses ledger (already: reasoning + falsifier + daily directional
grading) with **driver attribution**: post-outcome, a grader LLM pass answers "was the
stated mechanism the realized one?" → verdicts {right-for-right-reason, right-wrong-reason,
wrong-regime-changed, wrong-missing-data, wrong-overfit}, plus confidence calibration
(Brier via the existing validation kit). Applies to species-card "why" texts and committee
memos. Cheap (a grading pass over an existing ledger), high leverage (it is the check that
keeps the narrative layer honest), explicitly display/meta — it never scores names.

### 5.4 Regime trust (W1→W4, under hard floors)

The learned layer, pre-committed numerically so it cannot become the program's own
overfitting engine:
- **Honest n = distinct regime EPISODES** (contiguous same-cell runs, 180d purge-separated
  per the WAVE2 precedent), never row counts. A trust multiplier is estimable only for
  cells with **≥20 episodes AND ≥5 episodes in each time-half**.
- Each species pre-registers a **coarse learnable projection: ≤2 axes, ≤6 cells**, named
  in the registry at birth. All other cells are display-only scoreboard context, forever.
- The FULL cell scan registers as trials; a winning cell must beat the 95th percentile of
  an episode-block permutation null (§1.2).
- Historical/backfilled stamps seed display-only priors; **learning uses live-stamped rows
  only** (regime_history is non-PIT).
- Sequencing honesty: stamping starts at W0.5, so the W4 checkpoint is a **data-readiness
  review** — per pre-registered cell: current episode count + projected earliest-learnable
  date. No multiplier is estimated at W4.
- First zero-model wins ship earlier and honestly: W1 wires the radar's `favor_entries` /
  `cap_leadership` / `deescalation` directives (currently carried on regime_one's fused
  verdict but acted on by nothing downstream) into species display context — the first
  *acting* consumer of directives the repo already computes daily.

### 5.5 The product surface (W4)

- **Species cards** on the boards: species name + evidence-stack chips (arming/trigger/
  context, each green/grey) + regime-trust chip + primary invalidation + per-species
  ledger stats **at the species' declared horizon class** (a rotational species shows its
  21d partition + cushion incidence; a positional one shows clean15_126 + 63d MAE —
  never one hard-coded metric set for all). Honest accruing labels. i18n dual-span law;
  no t() in attributes.
- **Species pages** (per species): mechanism, scopes, live fires, near-miss cohort, ledger
  curves, falsified-neighbor notes — the brainstorm's "setup page", powered by real ledgers.
- **Rejection dashboard** (admin first): weekly rejections by reason, rejection accuracy,
  gate P&L attribution table.
- **Armed-Cohort view** (the FRONTRUN N1 re-founding, staged): a "forming → confirmed"
  cohort strip fed by S5, with constituent entry-states — shipped as a *parallel view*
  first, **flipping when its forward ledger matches-or-beats the incumbent board on
  stop-out, dead-money, and cushion incidence at the rotational horizons (5/10/21d)**,
  pre-registered in `ledger_binding` before the parallel view ships; returns reported as
  context. Surface law (the wait-cost law at the UI layer): *label ordering is an
  entry-quality claim* — `confirmed` may not rank or display above `forming` unless its
  per-label ledger stop-out/cushion is measurably superior; default presentation shows
  both labels with their per-label stats. The ranked board is not deleted; it is
  out-evolved on this program's axes or it stays.

---

## 6. What we will NOT build (de-scope, binding until revisited)

Alternative data (job postings, web traffic, app rankings, social sentiment, patents) —
Phase-3/4 at best, after the core loop grades; full analyst-report ingestion — revisions
metadata only; "AI opinion" as the product — the AI layer explains and grades, species and
ledgers decide; a new macro model — §3.4 consumes existing gauges (rate_pressure is a
categorical read of existing series, not a model); a fourth board-ledger variant — spine
extension only; intraday machinery — no US intraday history exists (hourly bars only if a
species specifically needs them); auto-tuning gates — all promotions/demotions pass human
review with pre-registered criteria; HK anything by default (§1.5); everything in §1.6.

---

## 7. Waves & delegation

Model routing (standing): **Fable** = architecture, adjudication, wave gate-keeping;
**Opus** = wave preplans, red-teams, judged reviews, reconstruction checks; **Sonnet** =
engine/harness code, collectors, wiring; **Haiku** = mechanical sweeps, backfills, data
pulls.

**Governance mechanics:** the owner is final arbiter of gate disputes; red-team verdicts
attach to the §8 row. W0.3 creates `research/species/`; every wave ships
`<wave>_PREREG.md` before its runs and `<wave>_REPORT.md` after, beside this doc's §8 row
(`date | wave | verdict | PR# | artifacts`). "Ship record" = the §8 row plus the registry
`deployment_status` change it authorizes. Wave reports carry an explicit leak-audit
section (fill rule, known-date mapping, any forward-looking element enumerated).

### W0 — Foundations (staged dispatch — parallel PRs must not race the append-only ledgers)

**Stage A (parallel; no ledger append-path edits):**
| id | task | tier |
|---|---|---|
| W0.1a | `grading.py` primitives (sub-task 1 of §5.1) + PIT membership wiring | Sonnet |
| W0.5a | regime_vector aggregator + `data/regime/regime_vector.parquet` daily persistence + `latest[]` publication + rate_pressure constants | Sonnet, **Opus review** (stamped definitions are irreversible ledger history) |
| W0.3 | Species registry v0 + seed with validated species + experiments-tab additive mirror + `research/species/` | Sonnet |
| W0.4 | Cohort metrics v0 over the ~500 sector-mapped priced names: peer_washout/reclaim/macd-turn % + Rubber-Band Score + within-cohort RS-rank *series* persistence (S7 dependency), coverage_pct stamps, chips+ledger-field payloads (display-only) | Sonnet |
| W0.6 | Data plane: (a) **massive stock_day capture — URGENT-ONCE** (rolling entitlement window; earliest days first; derived per-ticker store published to R2 with an audit_r2 freshness anchor + thin git manifest — the transient download cache is NOT the store); (b) estimate dispersion + revenue revisions in `equity_revisions._one`; (c) quarterly EDGAR extraction as a dedicated paced batch re-crawl (~1,334 names; completion date → S10/S11 `gating.come_back_on`); (d) Polygon news widening in tiers (120→500→1500) behind a runtime budget line, or demand-driven (names with a fresh fire/near-miss) | Haiku→Sonnet |
| W0.7 | Archetype v2: new buckets + anchored thresholds + PIT historical series + conditional-outcome phase-0 | Sonnet, Opus review |

**Stage B (after Stage A merges; ONE serialized PR per ledger):** thread the new grading
columns AND the regime_vector stamp AND species_id/archetype fields into each ledger's
append path together — `track_record` (incl. the §5.2 storage migration), `grade_us_board`
(incl. survivorship fix + parity check), `board_ledger`, `china_standout_track`, `qledger`
(incl. `register_batch`) — so no ledger ever appends a row schema a sibling PR is about to
re-freeze (keep-FIRST makes merge-order damage permanent).

**Stage C:** W0.2 near-miss capture (Appendix A taxonomy; HK knife_z field; CA watch-row
appends; US signal_gate near-misses) — dispatched only after Stage B lands for its target
ledgers.

### W1 — First promotions & cheap stratifications
S3 retro-derivation + gated phase-0 (Opus reconstruction check; fallback to W3 if it
fails); **S13 US reversal-sleeve phase-0** (pure re-read of existing deep panel — cheapest
science in the program); S6 OOS-basket phase-0 (interaction-marginal primary); S1 interim
coverage widening (already-priced unmapped names only); regime-directive display wiring
(favor_entries/deescalation as species context); tailwind lead-lag inversion (FRONTRUN N3
— one function, opposite calibration) with before/after lead-time measurement.

### W1.5 — Coverage widening (gated)
Full-PIT cohort granularity, gated on: (a) the W0.6 massive-derived store existing and
passing its freshness tripwire; (b) per-TF warm-up depth verified per name (daily/3D now;
weekly as ~300-bar depth accrues; monthly honestly unavailable for years — coverage_pct
will say so).

### W2 — Rotation frontrunning
S5 member-breadth coiling with per-leg ablations + the cohort lead gate; S4 two-clock
re-arm with its survival-matched + self-healing comparators; S2 promotion per its ledger;
explanation-memory grading pass v0.

### W3 — New-science species
S7 RS-slope-vs-cohort (two-sided registration); S9 bad-news immunity (earnings-reaction
core). Gates per constitution; falsified → closed in §8.

### W4 — Product surface + data-readiness review
Species cards/pages (per-class metrics), rejection dashboard, Armed-Cohort parallel view
(flip criteria per §5.5); regime-trust **data-readiness review** (episode counts +
earliest-learnable dates per pre-registered cell — no multipliers estimated).

### W5+ — Data-matured species & first learned cells
S8 (revisions archive maturity), S10/S11 (post-EDGAR-re-crawl), S12 (episode-floor
clause); quarterly gate-P&L review #1; first regime-trust cells that clear §5.4 floors;
first species promotions/demotions through the ladder.

**Standing loops** (cheap, scheduled): daily — ledgers accrue + species cells roll up;
weekly — near-miss/rejection triage in admin; monthly — species review (promote/demote/
split/tighten/loosen proposals, human-approved; lifecycle transitions per §3.1); quarterly
— walk-forward + regime-sliced re-reads + trial-ledger/FDR audit + gate P&L attribution.

---

## 8. Status log (accrues; newest first)

| date | wave | verdict | PR# | artifacts |
|---|---|---|---|---|
| 2026-07-04 | W2-explmem | SHIPPED (v0 scaffold) — explanation-memory driver-attribution grader (§5.3): deterministic 6-verdict map {right-for-right-reason / right-wrong-reason / wrong-regime-changed / wrong-missing-data / wrong-overfit / wrong-undetermined} from machine-checkable fields (direction-hit × falsifier-fired × PIT regime-change × degraded-input), Brier calibration over (conviction, realized_hit) pairs, DISPLAY/META artifact site/qledger/explanation_memory.json — NEVER scores names (§5.3). LLM mechanism-narrative matching is the documented v1. Currently 0/837 theses matured (all 8 desk ledgers status=open, check_by ~2026-10) → artifact emits honest zeros + status='accruing'; auto-activates as theses mature. 20 tests (each verdict path forced). W2 STATE: the wave is a maturation/construction boundary — S2 promotion + this grading both gate on ledger/thesis accrual (~Aug–Oct); S5/S4 need dedicated cohort-reconstruction harnesses (S5's cheap vol-compression ablation is underpowered within COILED by construction, 188/169<300) | #1266 | engine/explanation_memory.py, scripts/build_explanation_memory.py, site/qledger/explanation_memory.json |
| 2026-07-04 | W1.5 | SHIPPED — full-PIT cohort granularity, gates verified: (a) massive store LIVE at 20,476 tickers × 5y (deep-history 2021→2026 backfill complete; R2 topped up incl. the manifest coverage anchor); (b) per-TF warm-up inherent (every state fn returns None below its depth — washout_ctx ≥308 bars — and coverage_pct says so; weekly ~250 bars still thin, monthly honestly unavailable, exactly as §7 predicted). Cohort price loading falls back to the massive store behind the adjusted stores, with a HARD SPLIT GUARD (closes are RAW day-aggregate prints; any ±ln(1.8) close-to-close jump → not-covered — split-suspect names stay honestly uncovered, never poisoned into fabricated capitulations); the "already-priced" widening filter extends to every massive-store name | this PR | engine/cohort_metrics.py, tests/test_cohort_metrics.py |
| 2026-07-04 | W1-S3 | **MOVED TO W3+ per the pre-registered fallback — W1 CLOSED** (all six slate items resolved: S13 passed regime-scoped, S6 passed sub-5pp, S1 widening + regime wiring shipped, tailwind superseded, S3 deferred by rule). S3's reconstruction check has a ZERO-day overlap window (radar forward_log: 7 days of states, no de-escalation verdicts ever logged) — retro-deriving unverifiable history is the exact hazard the gate prohibits. ENABLING FIX: deescalation_eligible/reason + dislocation_active now logged per forward_log row; the overlap window accrues from today and the W3 check becomes decidable ~2026-10 | this PR | engine/risk_radar_audit.py, data/species/registry.json |
| 2026-07-04 | W1-S6 | **Phase-0 PASSED (both variants) — display-chip candidacy only (sub-5pp)** | this PR | prereg'd + trial-ledger'd (m=2); OOS basket panel regenerated by the UNMODIFIED wave-2 harness (reproduced the audited 102,433-fire / COILED 6,842 panel exactly). failed2×COILED on clean8_21: **+4.29pp q=0.032 (m2d_s3d) / +3.79pp q=0.080 (base3d)**, n floors met, halves positive, per-name majority 52–53%; failed2 side also stops out LESS within COILED (−4.9pp). Standalone failed2 = liftoff bought with stop-outs → interaction-only, as registered. OOS stronger than in-sample (+1.8/+3.2 → +3.8/+4.3pp). **Below the ≥5pp promotion floor** → bottom ladder rung only; graveyard's cried-wolf veto now dead in both directions | this PR | research/species/{W1_S6_PREREG.md, W1_S6_REPORT.md, w1_s6_analysis.py, _s6_phase0_out.json} |
| 2026-07-04 | W1-tailwind | **CLOSED — SUPERSEDED, no run** (orchestrator ruling; monthly review to ratify). The §7 W1 item "tailwind lead-lag inversion (FRONTRUN N3) with before/after lead-time" is resolved by the W9 verdicts (#1143/#1149): (i) the trailing 20d-rel-return tailwind axis is DEMOTED from rank (negative tercile spreads, **sign-unstable across ticker/time halves on BOTH the 23,368-fire deep panel and the 42,198-fire OOS basket panel**); (ii) sign-instability in one direction refutes the mirrored direction — the naive lead-lag inversion is the same measurement flipped, so running it would re-derive a refuted construction (§1.6: automatic wave failure); (iii) the EARLY-state form of N3 (bottoming-breadth instead of trailing return) already shipped as W9-A `sector_capitulating` (sign-stable −2.7pp/−3.5pp stop-out, SAFETY_ONLY display) — which is S1's cohort-washout mechanism, accruing on the ledger with §5.1 lead-time metrics. Nothing left for a separate inversion wave to measure | — | W9 evidence: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8, PRs #1143/#1149 |
| 2026-07-04 | W1-eng | SHIPPED — the W1 engineering pair: (i) **S1 interim coverage widening** — cohort sector map 429 → 1,501 names (already-priced only, per §7; GICS→cohort vocabulary translation so widened names JOIN sibling cohorts — raw strings agreed only 147/428; unknown-tier members stay None so peer_macd_turn_pct is coverage-gated, never mechanically diluted); (ii) **regime-directive display wiring** — the species experiments-tab mirror now carries a live `regime_context` line (rate_pressure/quad/vol/radar/favor_entries/cap_leadership/deescalation + vector asof) from the persisted daily vector, display-only, refreshed on change. NOTE: verified NO vector-accrual incident — the first post-#1102 nightly was simply still in flight; seam proven end-to-end locally | this PR | engine/cohort_metrics.py, engine/species_registry.py |
| 2026-07-04 | W1-S13 | **Phase-0 PASSED (3M construction) — REGIME-SCOPED** | this PR | prereg committed before run; sleeve excess PIT-era +0.49%/mo, HAC t 2.49, **DSR 0.991 (m=2 from trial ledger) SURVIVES**, boot Sharpe CI [0.13,0.81]; modern era +0.34%/mo DSR 0.908 marginal → K1 pass; **K2 TRIGGERED: 2024–26 −11.8%/yr (t −2.42)** — mega-cap-dominance hostile cell measured AND LIVE (no surface may imply current tradability); 1M variant CLOSED (modern DSR 0.760); K3 clean (ADBE 3.1%); K4 IC −0.011 matches seed. Safety-net grid printed (clean8_21 stop-out 38.5% — the safety net is the SLEEVE, per-name overlay stays falsified). Survivorship bound 69.4% coverage → positives optimistic; re-confirm on massive panel before promotion past display. research/species/{W1_S13_PREREG.md, W1_S13_REPORT.md, _s13_phase0_out.json}, scripts/s13_reversal_phase0.py |
| 2026-07-04 | **W0.2 Stage C SHIPPED — W0 COMPLETE** | Near-miss capture live on all three target markets against the CLOSED Appendix-A taxonomy (now hosted as `grading.REJECTION_TAXONOMY`; both capturing ledgers validate at append — unknown reasons null/reject loudly). US: signal_gate annotates EXACTLY-ONE-condition failures (not_topped_veto / freshness_expired; two-failure cases are plain rejections) → `track_record` NEAR_MISS_TYPE rows via `log_near_misses()`, stamped like fires and matured under the one grader ("grade rejections as predictions"); hygiene_screen captured-never-graded. CA: watch strip appends for the FIRST time (knife→knife_demote; alignment-blocked rows = null reason + block_reason text — no taxonomy row exists; §8 + monthly review to extend). HK: knife_z + reason now PERSIST (the old passthrough was silently dropped by the `_SCHEMA` reindex). Pre-registered from birth: **rejection ≠ blacklist** (S6 controls). 13 new tests, 188 green. Built inline (lean mode). **W0 is now fully shipped; next: the W1 slate (S13 US reversal-sleeve phase-0 first — cheapest science), per §7** | #1193 | engine/grading.py, engine/signal_gate.py, engine/track_record.py, engine/board_ledger.py, scripts/build_stock_library.py, scripts/build_canada.py, scripts/build_hk_library.py |
| 2026-07-04 | **W0 Stage B COMPLETE** | All five serialized ledger PRs merged (a #1139, b #1142, c #1147, d #1151, e #1180). Every ledger now threads: one-grader/CN-native spine axes + §3.4 regime stamps (US primary on US ledgers; own-market-null-documented + us_* context on HK/CA/CN) + species_id/archetype nullable cols. Next per §7: **Stage C (W0.2 near-miss capture — Appendix A closed taxonomy; US signal_gate new, CA watch-strip append, HK add knife_z WITHOUT re-appending)**, then the W1 slate (S13 phase-0 first) | — | this row |
| 2026-07-04 | W0-StageB-e | SHIPPED — qledger on batched I/O + the stamped fill discontinuity: `register_batch()` (ONE store read + ONE append per batch; register() is O(file)/call at ~2,800 calls/day — loop-callers migrated: communique_diff, placebo sampler; two one-shot tape scripts left as-is, documented), `_fwd_ret` asof→NEXT-BAR entry (exit anchored at fill; never grades a shortened window) with the discontinuity STAMPED per §5.1.3 — grade rows carry fill_convention+entry_fill_date, legacy rows read asof_legacy and are never rewritten, track_record prints the split; §3.4 US-vector PIT stamps at registration (lru-cached per asof) + nightly fill-null-only backfill + residual unstamped count. Built inline by orchestrator (lean mode, owner-approved); 111 tests green (10 new) | #1180 | engine/qledger.py, engine/communique_diff.py, scripts/sample_qledger_placebo.py, scripts/grade_qledger.py |
| 2026-07-04 | W0.6a | Massive stock_day FULL BACKFILL **COMPLETE** — entire entitlement window 2025-01-02 → 2026-07-02 captured (~370 trading days, 14,906 tickers, 0 failed days across resumed runs; survived resume-state poisoning, disk-full, and two process kills — resumable state machinery proved itself). Initial R2 publish launched; `massive_stock_day` added to daily.yml publish_r2 --dirs (audit_r2 coverage anchor was pre-wired in #1107); thin git manifest + backfill state committed | — | data/massive_stock_day/ (R2), data/massive_stock_day/_manifest.json, .github/workflows/daily.yml |
| 2026-07-03 | W0-StageB-d | SHIPPED — china_standout_track CN-NATIVE spine axes: terminal_state_clean15_126/clean8_21 + fwd_mfe_{5,10,21,63} + post_cushion_breach computed from the T+1 HL2 fill w/ locked-limit exclusion (fill sanctity verified 3 ways: zero grading.fill_index routes, fill-bar excluded from windows, locked rows all-null) — barrier CONSTANTS shared from grading so definitions agree cross-market; `fill_basis="t1_hl2"` provenance col; us_* context stamps + PIT backfill + n_unstamped; own-market regime = documented NULL (china_run overwrites regime_history — non-PIT); species_id null (CN-WASHOUT+CN-REVERSAL both bind → ambiguous, documented). Adversarial review APPROVE (mutation-tested: reintroducing the B-a cushioned-then-stopped bug fails the new test; partition agrees with grading.terminal_state on 5 hand paths; dtype coercion set enumerated complete). fwd_mfe {5,10,21,63} confirmed per red-team-corrected §5.1, not a deviation | #1151 | engine/china_standout_track.py, tests/test_china_standout_track.py |
| 2026-07-03 | W0-StageB-c | SHIPPED — board_ledger (HK/CA) on the one grader: grade() consumes `forward_metrics` (parity exact — `grade_next_bar_return` is a literal alias); 7 spine cols; SUSPENSION rule preserved (verified byte-identical + suspended rows stay all-null); own-market regime stamp = documented NULL (hk_run/canada_run overwrite regime_history each run — non-PIT; `_OWN_REGIME_NOTE`); US vector as `us_*` context cols + vector_asof/staleness_hours, append-time stamp + grade-time null-only PIT backfill + n_unstamped in scorecard. Adversarial review APPROVE + hardening: pandas-3.x float64/object dtype fragility eliminated (`_coerce_object_cols` at both assembly points; review's repro'd TypeError on string writes into all-NaN parquet cols), legacy-schema test frozen to true pre-stamp 10 cols, both grader test files wired into ci.yml (neither was CI-covered) | #1147 | engine/board_ledger.py, tests/test_board_ledger.py, .github/workflows/ci.yml |
| 2026-07-03 | W0-StageB-b | SHIPPED — grade_us_board on the one grader: private `_fwd_ret`/`_close_path_mae` deleted → `grading.forward_metrics` (parity verified: harness embeds the DELETED code byte-for-byte, max_abs_diff=0 across 6 metrics/950 rows — old `_pos_after` ≡ `fill_index` algebraically); 63d lane; survivorship routed through `resolve_series`+`load_dead_prices` (honest degradation: `dead_store_active:false` + n_recovered=0 while the weekly dead-price crawl accrues — 15/1,083 resolved today); US regime_vector PIT stamps + legacy backfill; species_id null (15 species bind us_board_ledger → ambiguous by design). Adversarial review APPROVE; cosmetic fixes: merge semantics honestly relabeled keep-FRESH (deterministic re-grade; PIT log is snapshots.jsonl), fwd_mfe per-horizon sparsity documented. Schema 38→58 cols; runtime 5.9s | #1142 | scripts/grade_us_board.py, tests/test_grade_us_board.py |
| 2026-07-03 | W0-StageB-a | SHIPPED — track_record ledger threaded: parquet un-ignored (+ scripts/audit_sizes.py tripwire, wired in daily.yml), builder scheduled after build_signal_quality, spine cols (fwd_mfe_5..126, terminal_state_clean15_126/clean8_21, post_cushion_breach), regime_vector stamp via new PIT `get_vector_for_date` (carry-forward staleness; §3.4 unstamped-count printed), species_id/archetype nullable. Adversarial review caught + fixed a cushioned-then-stopped mislabeling → `grading.post_cushion_breach()` primitive (identical scan to cushion_incidence). Schema 30→48 cols, keep-FIRST verified | #1139 | engine/track_record.py, engine/grading.py, engine/regime_vector.py, scripts/audit_sizes.py, .github/workflows/daily.yml |
| 2026-07-03 | W0.6c | EDGAR quarterly backfill COMPLETE — 54,853 ticker-quarters, 1,331/1,331 tickers, FY2009–2027, 0 failures; store committed; S10/S11 `gating.come_back_on` → 2026-07-03 (gate cleared) | — | data/edgar/statements_quarterly.parquet, data/species/registry.json |
| 2026-07-03 | W0.6a | Massive stock_day FULL backfill LAUNCHED (resumable, earliest-first from 2025-01-02; smoke-run resume-state poisoning caught → `--force` restart; disk-full at 1GiB free root-caused to 312 stale agent worktrees → 146 removed, 268GiB freed). publish_r2 wiring after completion | — | data/massive_stock_day/ (store), scripts/backfill_massive_stock_day.py |
| 2026-07-03 | W0.7 | MERGED after 6-lens review — 4 blocking findings fixed by ruling: (i) history.parquet PIT overclaim honest-relabeled (labels non-PIT for beta/sector-driven buckets — display-only priors, never scope-gates; empirical 0/1331 tickers vary sector/betas); (ii) §2.2 table corruption fixed (broken_growth duplicate removed; commodity_sensitive = 0 fires, errata'd); (iii) rebuild entrypoint added (scripts/build_archetype_history.py, on-demand, unscheduled); (iv) CSS pills for 7 new buckets + `_GROWTH_ARCH` += {secular_growth, broken_growth} (preserves inflation_label for reclassified names) + precedence drift-guard test | #1105 | engine/stock_fundamentals.py, engine/stock_macro_sensitivity.py, templates/stock.html.j2, scripts/build_archetype_history.py |
| 2026-07-03 | W0.5a | MERGED after adjudication + 6-lens review — **RULING (a): spec letter wins, panic threshold 68.0 → 78.0** (radar LOUD tier = `_ALERT_FROM`="elevated" = `_DEFAULT_BANDS` 78.0); review fixes: vacuous `is True or 1` degraded asserts, escalation-trigger + null-gap hysteresis tests, `deescalation_trajectory` read path (was silently always-None), liquidity primary path → `fused_risk.gate.liquidity`, vol vocabulary corrected to actual `_regime_label` tokens | #1102 | engine/regime_vector.py, engine/regime_coherence.py, data/regime/regime_vector.parquet (accrues via nightly `git add data/`) |
| 2026-07-03 | handoff | Session handoff written (account switch); next: review #1102/#1105, run massive+EDGAR backfills, Stage B | — | research/species/HANDOFF_2026-07-03.md |
| 2026-07-03 | W0.6 | SHIPPED — massive stock_day capture machinery (smoke-tested, earliest 2025-01-02; FULL BACKFILL STILL TO RUN, ~4h, window rolls), revisions dispersion (revenue drift structurally unavailable in yfinance — documented), EDGAR quarterly script (10-name validation; full ~9min run pending), Polygon tier-1 500 | #1107 | collectors/massive_stock_day.py, scripts/backfill_massive_stock_day.py, scripts/backfill_edgar_quarterly.py |
| 2026-07-03 | W0.7 | BUILT — 13-bucket archetype v2 (8 anchored) + PIT history (1,331 tickers FY2009–25) + phase-0 report (single-regime caveat); **PR HELD for orchestrator review** | #1105 | engine/stock_fundamentals.py, data/archetypes/history.parquet, research/species/W0_7_ARCHETYPE_REPORT.md |
| 2026-07-03 | W0.4 | SHIPPED — cohort metrics v0 display-only: peer_washout/reclaim/macd_turn %, Rubber-Band Score, coverage law, RS-rank series (S7 dep); 1.9s runtime; live read: mean peer_washout 0.71 | #1104 | engine/cohort_metrics.py, data/cohort_metrics/ |
| 2026-07-03 | W0.3 | SHIPPED — species registry v0, 17 species seeded truthfully, experiments-tab additive mirror (idempotent) | #1103 | engine/species_registry.py, data/species/registry.json |
| 2026-07-03 | W0.5a | BUILT — regime_vector aggregator + rate_pressure + null-on-degraded + coherence registration; **PR HELD: adjudicate panic threshold 68.0 (shipped) vs LOUD 78.0 (§3.4 letter) before merge** | #1102 | engine/regime_vector.py, data/regime/regime_vector.parquet |
| 2026-07-03 | W0.1a | SHIPPED — grading spine primitives: fwd_mfe, terminal-state partition (clean15_126/clean8_21, straddle→stop), cushion incidence (competing-risk), PIT membership in as_of_panel | #1100 | engine/grading.py |
| 2026-07-03 | program birth | Masterplan authored (Fable), 6-lens red-team (32 upheld findings applied), merged | #1097 | this doc |

---

## Appendix A — The near-miss rejection taxonomy (closed set)

"Near-miss" = a candidate failing **exactly one** row of this table at evaluation time.
Adding or renaming a reason requires a §8 status row + monthly-review sign-off — never a
silent enum append by a runner. Each reason is anchored to the code that emits it today.

| reason | emitting gate / builder | failure mode it prevents |
|---|---|---|
| `freshness_expired` | signal_gate FRESH_TICKS window | chasing an aged cross |
| `not_topped_veto` | signal_gate not-topped check | buying into a topped oscillator |
| `tier_cutoff` | confluence_tiers T4-excluded / below-tier | weak-confluence entries |
| `extension_demote` | anti-chase EXT_PENALTY / extension-since-cross | buying the blast-off (JNJ/AMAT) |
| `knife_demote` | HK `_falling_knife_demote` quintile (port to US/CA) | catching structural knives |
| `sector_cap_displaced` | board sector-concentration cap | crowding one cohort |
| `board_rank_cutoff` | blend_sorted position below board width | the marginal card |
| `hygiene_screen` | ST/ADV/staleness/mcap screens | untradeable names (NOT graded as predictions — hygiene is not a forecast) |
| `event_blackout` | earnings-proximity exclusions (where wired) | binary event risk |
| `cohort_null` | §3.3 coverage law (coverage_pct < 70%) | pretending we can see a cohort we can't |

*The moat, restated: anyone can compute an oscillator. What compounds is the loop — named
species with mechanism stories, graded on the safety-net axes at every horizon they claim,
with every rejection graded too, in the regimes stamped on every row — so that a year from
now the system doesn't just fire signals; it knows, with receipts, which species to trust,
where, and when.*
