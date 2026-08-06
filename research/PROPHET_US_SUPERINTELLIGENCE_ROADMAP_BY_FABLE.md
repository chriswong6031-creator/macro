# PROPHET US SUPERINTELLIGENCE — ROADMAP (BY FABLE)

**Date:** 2026-08-04 · **Trigger:** operator directive after the Trend Intelligence program
shipped ("audit again from a new perspective — we have built a lot and not a lot of it is
deeply wired into Prophet; make it a world-class institutional stock signaling
superintelligence, connected to the Neural Web"). **Parents:**
`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` (the funnel repair — W0–W6,
all seven PRs merged 2026-08-04; its §0 gates inherited unchanged) and, as the sibling
architecture this roadmap deliberately rhymes with,
`research/PROPHET_CN_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` (PR #4517) + the CN Loser
Intelligence R-slate — several of whose MEASURED verdicts port here as ready-made studies.

The first program fixed the funnel: winners are now sighted, converted, narrated, and
counted. This roadmap is the layer ABOVE it: what Prophet US becomes when the rest of the
dashboard's organs are wired into it as JOINABLE EVIDENCE — composed, graded, and narrated —
rather than as forty artifacts that can only be joined by hand at audit time.

---

## §0 Fast-track evidence doctrine (inherited verbatim from the CN roadmap, now house law for both markets)

1. **Retro stand-in first.** Every candidate wiring is tested the day it is proposed against
   a FROZEN US frame. We hold three: the 526-matured postmortem episode frame
   (`data/prophet_postmortem/`), the graded board history (`data/us_board_ledger/
   retro_grades.parquet`, 2,282 rows × 85 cols), and the W0 runner frame (top-150 exclusion
   audit, regenerated nightly). Stand-in verdicts land in hours.
2. **Out-of-era corroboration second** — the #4506 pattern (12 months of committed caches,
   thousands of events, half-split robustness, seven-second runtime).
3. **Forward races confirm, never block.** Ratified changes go live with the displaced
   definition grading in parallel and named tripwires; W0 prints the race nightly.
4. **Coverage debts are named, not waited on.** Where a store lacks PIT depth (short
   interest, options-flow history at name grain, theme-rank archive), the collector starts
   accruing NOW and the analysis states its caveat instead of stalling.

## §1 What "institutional-grade" means for a US momentum-and-catalyst tape, concretely

Eight information layers a top US desk systematically exploits, mapped to what this repo
already owns. The pattern that should embarrass us (it did in the audit, twice): almost
every layer is COLLECTED nightly and consumed by nothing in the pick chain.

| Layer | The edge | What we have | Wired into Prophet US? |
|---|---|---|---|
| L1 Catalyst/event intelligence | Earnings, guidance, 8-K materiality, activist stakes, gov contracts, biotech events — the US tape is CATALYST-driven | earnings feed (W4), `eightk_magnitude`, `activist`/`beneficial_ownership`, gov-revenue issuer receipts (PLTR!), BioCatalyst, `analyst_revisions`, SUE | **Partial** — W4 context fields + blackout veto; Door E chartered; everything else display-islands |
| L2 Flow & positioning | Options dealer positioning, flow attention, short interest, institutional footprints | `options_gex` (zero-authority), `agg_trend` dealer gamma, options-flow-attention, OIP program, FINRA short-vol (prospective charter), insider/congress/13F (context-only by kill) | **No** — zero pick-chain consumers |
| L3 Theme relay microstructure | Leader→follower sequencing inside an igniting theme; being EARLY in the relay, not merely "in a hot theme" | member maps + subsector_rotation give the relay clock; CN measured relay POSITION as the monotone separator (#4506: early −1.17pp/46% vs late −5.32pp/36%) while theme-heat LEVEL does not separate | **First wiring now** — Door T records relay features from birth (§4.1) |
| L4 Validated timing core | The confluence cascade family + washout machinery | signal_quality/confluence_tiers, washout_watch, MWR, bottom ledger | **Yes** (the record) |
| L5 Regime adaptation | Dispersion vs correlation, risk state, when continuation beats reversion | `dispersion_regime` (prints "lean_in — selection pays", display-only), gate_go, market_state, vol_regime | **Partial** — W5.3 chartered, passport-gated |
| L6 Risk architecture | Evidence-aware exits/sizing, catastrophe avoidance | exit study (H=10 record basis), PSQ leash, antichase shadow, earnings blackout; PSI program owns the portfolio layer (fence) | **Partial** |
| L7 Supply-chain foresight | Bottleneck → customer-capex → revision-breadth cascades that LEAD theme price moves | **The Thematic Foresight Desk already exists** (`scripts/build_foresight.py`, T1 bottleneck × T2 capex × T4 revision-breadth → per-theme STAGE; worked case = the June-2024 HBM call) | **No** — not even the new Theme Tape reads it |
| L8 Fundamental quality receipts | Issuer-verified fundamentals, capital structure, forensic accounting flags | fundamental forensics (attested receipts), capital_structure, fundamentals collectors | **No** — context islands |

The superintelligence is not a new model. It is these eight layers COMPOSED — each behind
its own graded evidence, each narrated, with a learning loop that turns every loss and every
miss into the next measurement automatically. Two structural principles carry over intact
from the CN adjudications and this repo's kill registry:

- **Glass-box law / no composite blend, ever.** Every authority is a bounded, individually
  revertible leg earned through its own adjudication (the conviction composite measured
  anti-predictive; DNR:KILL-PROPHET-POP-MERGE forbids blended rankings; PSF killed stage-as-win-gate). The
  priority score stays a sum of defensible legs; new axes join it one at a time or not at all.
- **Confirmation is not free.** CN-RC0 measured confirmation as negatively priced at entry
  timing; the US operator independently ratified T2-above-T1 in 2026-07. §5 re-measures this
  on the US frame — if it replicates, the anticipation tiers (T3, and T4's lawful display
  path) deserve more surfacing weight than the confirmation tiers, not less.

## §2 The keystone: a US Context Vector on a full-universe PIT store (sensory cortex)

The single highest-leverage build in this roadmap, and the direct US mirror of CN P-SI-2.
Tonight, every organ writes its own artifact shape; joining evidence to outcomes is
archaeology (the audit took a day of hand-joins; the CN flow battery took a session). The
fix is one nightly per-name context block, assembled in `build_stock_library` where
`sig_verdict` already computes for all ~1,579 names, stamped onto a full-universe US PIT
candidate store (extending the existing `prophet_stage_shadow` store or a sibling
`us_prophet_rank/candidates.parquet` — final home per the current-state census), so every
future study joins it point-in-time:

```
context = {
  theme:   {memberships, heat_rank, relay_count_3d, relay_position, foresight_stage},
  event:   {days_to_report, post_earnings_move, sue_z, eightk_recent_days, catalyst_class},
  flow:    {turnover_pctile_60d, gex_state, flow_attention_z, short_vol_ratio?},
  quality: {alpha_pctile, psq_stage, archetype/personality dims (Context Snapshot reuse)},
  regime:  {dispersion_state, gate_go, market_quad, vol_regime},
  risk:    {ext_z, antichase_flag, in_blackout, day3_mark_class}
}
```

Zero authority at birth. Census facts that fix the design (2026-08-04):
- **Home:** `data/us_prophet_rank/candidates.parquet`, mirroring CN's store (4,412 rows ×
  88 cols over its first 3 nights; full-universe INCLUDING ineligible names; itemized
  priority-score legs per row). The US has NO equivalent today — `prophet_stage_shadow`
  holds only an aggregate summary.json; `retro_grades` is admission-gated, not
  universe-gated.
- **Assembly reuse:** `engine/neuralweb/context_api.py` (`context_frame`) already computes
  11 PIT dimensions (personality, archetype, regime, sector, factor, attention, insider,
  short_int, options, spine, forensics) — research-side by design, ONE production consumer
  (trade_memory). The nightly assembly calls it rather than re-deriving (canonical-source
  law), benchmarked first: it computes per-call, so the build measures cost on 1,579 names
  and subsets dimensions if needed rather than silently thinning.
- **Stamping-coverage repair rides along:** on `retro_grades`, the options columns are
  9–12% populated, `opt_net_signed_prem_5d_z`/`opt_crowding_flag` are 0% (schema present,
  never populated) and `species_id`/`archetype` are dead — the context-vector build either
  populates or retires them (carried-columns law), never leaves schema that lies.

Its value is that the ENTIRE dashboard's knowledge becomes joinable evidence the night it
ships — and every ledger this program already runs (doors, bottom ledger, board ledger,
postmortem) inherits it by join key.

## §3 The bounded-authority ladder (US queue, in evidence order)

Each axis follows the theme_timing precedent exactly: retro stand-in → out-of-era
corroboration → operator-ratified BOUNDED authority (a capped score leg or a featured
prior, never a hidden blend) → displaced-definition shadow + named tripwire.

Queue AFTER the §5 stand-ins re-ranked it (original CN-inspired order is superseded by the
measured US verdicts):

1. **Cross-age / FRESH_TICKS extension** — §5 S-B's within-window gradient (fresh 0-tick
   worst, 2-tick best) promotes this from "one of the W5 knobs" to the front of the queue:
   the prereg tests whether outcomes keep improving at ticks 3–4 (currently excluded).
2. **Foresight stage** (L7) — retro join of the Foresight Desk's per-theme STAGE history to
   the episode frame; then a Theme Tape column + Door T feature, then the ladder.
3. **Catalyst-class prior** (L1) — Door E's thesis; ladder entry only via its own prereg.
4. **Relay position** — demoted by S-D's null on generic breakouts; survives ONLY as a
   Door-T forward question on its own fire class (features recorded from birth, §4.1).
5. **Turnover percentile** — re-scoped by S-A to the RISK/SIZING context lane (bimodal on
   US, not a loser veto); 60d-spec re-run when the volume cache deepens (~mid-Aug).
6. **Crowding flag** (curated-membership + turnover-tail CONTEXT, never a veto) — S-C's
   inversion makes this a risk chip, adjudicated as display first.
7. **Options-flow axes** (L2) — a US flow battery mirroring CN's, seeded by the two
   REGISTERED W-E1/OPEX survivors (`S-VANNA-RELIEF`, `S-FRONT-CHARM` — already stamped on
   retro_grades as `opt_vanna_relief`/`opt_front7_charm_share`, thin coverage) with the
   kills fenced (DOI DEAD; signed-charm refuted; charm-cushion rejected). Only battery
   survivors queue.
8. **Dispersion sizing** (L5) — already chartered as W5.3; passport must first earn
   `survives: true` (its artifact currently says false — respected).

## §4 First wirings (shipping now, in this program's opening PRs)

### 4.1 Door T relay instrumentation (before the ledger matures — zero-cost, high-leverage)
The doors merged today and accrue from tonight. Every Door T flag gains recorded features
(NOT fire conditions — fire definitions stay frozen per the prereg): `relay_count_3d`,
`relay_position` (fraction of theme members already broken out), `turnover_pctile_60d`,
`foresight_stage` (null until L7 wiring lands). The promotion read gains, for free, the
power to test the CN relay finding on US forward data. A prereg ADDENDUM (recorded-features
list, no gate changes) ships with the code.

### 4.2 Foresight Desk → Theme Tape (display; the anticipation the operator asked for)
The Theme Tape answers "what is the board doing with the hot theme's members." The Foresight
Desk answers the PRIOR question — "which themes are LOADING before price confirms" (its HBM
case led the theme move). Census: `engine/foresight_cascade.py`, 10-value STAGE enum,
18 themes covered, and it ALREADY feeds several NW theme organs (thematic_state,
theme_pathways, theme_thesis, special_sits_intel) — the tape join is natural, not novel.
Today's read: Medical Devices / Nuclear / Rare Earths / Ag at PRECIPICE-variants, AI Semis
RE-RATING — and ZERO numerically-confirmed stages (all text/fingerprint variants), which the
tape must disclose in plain words, not dress up. Wiring: a foresight-stage glyph on covered
Theme Tape rows + a "loading, not yet moving" row-class for desk-staged themes ahead of
heat rank. Display-tier, nulls disclosed. (Found in passing, chipped: the desk's health
block prints `t1_fingerprint: DARK 0/18` while two themes carry fingerprint-variant stages
— a stale health leg to reconcile.)

### 4.3 US flow battery + frozen-frame stand-ins (§5) — research artifacts, hours-class.

### 4.4 name_score adjudication (an existing rival composite must not stay unmeasured)
`engine/name_score.py` is a shipped multiplicative buy-readiness composite
(trigger×fuel×survive×tailwind×confidence×edge_mult). The census sharpened this from
"unmeasured" to "live and load-bearing while unmeasured":
- The board's displayed `conviction.score` IS name_score's `potential_score` — a
  backward-compat overwrite (`score_timing` → `c["score"]`, build_stock_library
  ~3183-3223) that survives to this day; the plan-intake FILTER's `score>=60` caution leg
  therefore keys on this timing screen too (W1 changed the SORT, not the filter).
- A grader already exists and runs nightly (`engine/name_score_grader.py`;
  `data/name_score/us_calls.parquet`: 69,602 calls, 33 dates, 2,989 tickers) — and its
  `grade()`/`scorecard()` outputs are consumed by NOTHING in production. First read-only
  run: 21d rank-IC −0.057 on a thin 2-IC-date sample; 63d still accruing.
Actions: (1) wire the grader's scorecard into the W0 miss-audit artifact (ops-tier, zero
authority — a self-grading organ nobody reads is unrun-suite rot in signal form); (2) the
frozen-frame P@k benchmark vs priority-score and alpha orderings; (3) the already-chartered
W1 follow-up prereg (do the band/score intake filters forfeit board winners?) now names
this key explicitly. Then adjudicate: demote, mine legs for the ladder, or keep display
with its measured card printed.

### 4.5 Universe widening, scan-tier only
`build_polygon_universe` already maintains ~8.7k names with sector + cap for the charting
app. Charter (not build yet): a liquidity-floored SCAN tier — context vector + miss-audit
coverage over the widened set, board ADMISSION untouched (curated universe stays the
population; DNR:KILL-PROPHET-POP-MERGE). "See everything, admit selectively." The CRCL incident becomes
structurally impossible: an off-index runner would at minimum be SEEN and counted missed.

## §5 Frozen-frame stand-ins — RUN, results frozen alongside

Instruments + numbers: `research/prophet_us_audit/superintelligence_standins.py` +
`superintelligence_standins_results.json`. Frame: `retro_grades.parquet` buy-lane H=10, 403
episodes / 243 names, 2026-06-16..07-16 (the pre-cascade-gate era — the frame ENDS the day
the cascade inclusion gate began; a finding in itself: era fragmentation means tier context
had to be RECOMPUTED PIT via `tier_stream`, which is §2's argument in one sentence).
Loser := excess_spy < −3pp at H=10; base 25.8% / median +1.81pp. All exploratory; era + n
caveats binding.

- **S-A Turnover — CN result does NOT port cleanly; US axis is BIMODAL.** Own-20d volume
  percentile (the 60d CN spec is data-blocked: the volume cache holds only ~51 sessions,
  backfilled 2026-05-19 — debt named, cache self-heals to 60d depth ~mid-Aug): ≥p90 band
  shows the WORST loser rate (33.3% vs 24.7% below-median, CN-directional) AND the best
  date-demeaned median (+2.37pp vs +0.23) — fat both tails (n=30 band, suggestive-only).
  Verdict: on US this is a VARIANCE axis, not a loser veto → routed to the risk/sizing
  context lane, not admission. Re-run at 60d spec when the cache deepens.
- **S-B Confirmation pricing — sign OPPOSITE to CN, provisional.** Cascade-eligibility at
  admission separates strongly even in this old-gate era: eligible-day admissions 15.6%
  loser / +0.52pp demeaned (n=109) vs not-eligible-that-day 29.6% / +0.21 (n=294) — an
  independent, backward-looking confirmation that the cascade gate earns its centrality.
  WITHIN eligible admissions, outcome IMPROVES with cross age: ticks 0 → 20.8% loser /
  +0.10 demeaned; ticks 1 → 10.0% / +0.92; ticks 2 → 11.5% / +3.04 (n=53/30/26). Where CN
  measured confirmation as negatively priced, the US trending tape paid for a cross that
  held 1–2 ticks. Direct consequence: the W5.2 FRESH_TICKS prereg must test whether the
  gradient EXTENDS past the current 2-tick boundary (the excluded ticks-3/4 cohort) or
  peaks at it — this stand-in makes that the single most interesting gate question in the
  program. (Zero T2/T3/T4 admissions in-frame is historically correct — those paths began
  with the 07-16 gate; the tier split re-runs on the post-07-16 frame as it matures.)
- **S-C Curated membership — CN result INVERTS on US.** Members 35.9% loser / −0.94pp
  demeaned (n=103) vs non-members 22.3% / +0.57 (n=300). US curated baskets are AI/
  tech-tilted; in this era membership proxied CROWDING (the CN HOT-theme-42% analogue +
  the US sector_headwind postmortem, agreeing). Verdict: membership joins the context
  vector as a crowding/risk flag, NOT a quality prior; any Door T promotion must beat
  this crowding drag explicitly (its prereg baselines already require it).
- **S-D Relay-position backtest (the #4506 US port) — NULL on this construction.**
  14,427 fresh-63d-high events across 310 curated-basket names, 2023-10..2026-07, PIT
  membership honored, outcome = fwd-10s excess vs day median: early-relay (≤0.33) median
  +0.49pp vs late-relay (≥0.67) +0.64pp; early-minus-late delta −0.11pp / −0.43pp across
  halves — no separation, sign opposite to CN and economically nil. CN's separator was
  measured on CHASE-class events (limit-day extremes), not generic breakouts; the US
  analogue of that class is what Door T's instrumented forward flags will test on its own
  fire distribution. Expectation set honestly: no free relay lunch on generic US breakouts.
  (Background fact: all bands carry +0.45..+0.64pp — event-level momentum persistence is
  mildly positive US-wide in this period.)

Meta-verdict: FOUR of four CN findings failed naive transport (turnover monotone→bimodal;
confirmation-negative→confirmation-positive; membership-quality→membership-crowding;
relay-early→null). The two markets share the DOCTRINE and the SPINE, never the
coefficients — which is precisely why §3's ladder runs per-market stand-ins before any
axis touches authority, and why the context vector matters more than any single axis.

## §6 Neural Web integration (both directions, lawful, mirroring CN P-SI-5)

- **Prophet → NW:** US Prophet artifacts register with honest grades — miss-audit
  (ops-telemetry), door ledgers (shadow-accrual), track ledgers (graded records), tripwire
  states — as `config/synapse.yml` ARTIFACT entries (588 exist; the field contract is
  path/format/producer/owner/cadence/schema/tier/consumers, integrity-checked by
  check_synapse_registry) inside the existing Prophet lobe per the Trade Memory ruling: no
  new lobe, and artifact registration is unaffected by the lobe cap. The brain answers
  "why isn't PLTR featured tonight" from artifacts (Theme Tape why-nots, plan pulses, door
  states), never from vibes. (Census caught a governance anomaly, chipped for operator
  audit: replaying `roster_governor`'s own filter over `lobe_charters.yml` counts 75
  active display+shadow charters against the configured `max_active_nonscored_lobes: 66`
  — the cap is still cited as binding while its artifact reads above it.)
- **NW → Prophet:** graded cross-lobe context (liquidity regime, global beta, seasonality
  shadow-lobe state) enters ONLY through the §3 ladder like any other axis. A7 stands: the
  LLM narrates and de-escalates; it never originates, scores, or escalates.
- **Chat:** the Live Market State Packet gains the US board block (Theme Tape counts, door
  tallies, race states) so Mastermind explains picks AND absences bilingually.
- **Metabolism:** the autonomous build loop's Prophet docket receives W6's machine-drafted
  prereg candidates (from miss-audit + postmortem deltas) — machine proposes, operator
  adjudicates, nothing hot-patches (budget cap per R-V4-2 unchanged).

## §7 Cross-market spine discipline (one schema family, two markets)

CN and US context vectors MUST stay one schema family with market-specific axes — a shared
`context_vector` contract note co-adjudicated with the CN program (its lane owns CN files;
this lane owns US files; the contract doc is joint). Divergent shapes here would repeat the
THS side-car shape-contamination lesson within our own walls.

## §8 What this roadmap does NOT do

No composite/black-box score (glass-box law). No LLM-originated signals (A7). No forced
leadership calls (row 117). No conviction×timing blends or graded-population changes (row
49). No per-name outcome audition (row 69). No pre-onset winner-fingerprint claims (rows
114-115) — context axes are cross-sectional conditioning, promoted only through preregs. No
CN-side edits (sibling lane owns them). No portfolio-layer surfaces (PSI owns them). W5
gate adjudications remain sequenced behind W0's five green nightlies.

## §9 Ship order

| Step | Content | Tier |
|---|---|---|
| Now (this PR set) | Roadmap + §5 stand-in results + Door T relay instrumentation (4.1) | research / shadow-features |
| Next | Foresight→Theme Tape (4.2) + name_score scorecard (4.4) | display / research |
| Then | US Context Vector on the PIT store (§2) — after the census fixes its home | display/ledger |
| Then | US flow battery (L2) → ladder queue by ranked verdicts | research |
| Gated | Ladder promotions one axis at a time; W5 after G0.2; scan-tier universe after operator nod | scored (each own prereg) |

*Related: PROPHET_CN_SUPERINTELLIGENCE_ROADMAP (sibling), PROPHET_TRADE_MEMORY (episode
memory + Context Snapshot canon), THEMATIC_FORESIGHT_DESK (L7), OIP masterplan (L2),
US_BOARD_MEASUREMENT (measurement canon), PROPHET_DOORS_PREREG (amended by 4.1).*
