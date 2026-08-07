# Signal Episode Atlas — per-name event classes, conditioned base rates, and the door Prophet is missing

**Program tag: SEA. Status: DRAFT (this session). Operator directive 2026-08-05 (verbatim intent):**
stocks are not alike; the same crossover means different things at different depths, levels,
timeframes, and on different names/archetypes; assess each signal against the *matching*
historical episodes of the same class on the same name and cohort; align weekly turns with
3D/2D; fuse with the macro cause so the system can say *why now*; and make Prophet stop
missing the washout-turn class entirely.

## §0 ACCEPTANCE GATES (this program is not done unless)

1. **Event library exists and is PIT-honest**: `data/stock_events/events.parquet` — every
   canon RSI-MACD cross event (bull+bear) on completed 2B/3B/W-FRI grids for the US organ
   universe, with depth percentile at cross (trailing-10y, IHM estimator), level-vs-zero,
   washout-duration, MTF-alignment state at event, and forward outcomes filled ONLY for
   matured events. Deterministic re-derivation from price history — this is a MEASUREMENT
   artifact, never a call record; the file says so in its own metadata.
2. **Atlas receipts are hierarchical, not cherry-picked**: per-(name, class) base rates are
   shrunken toward (archetype, class) and (global, class) by event count — the statistically
   sound form of "not all stocks are alike." NO per-name indicator selection by backtest rank
   (that construction is the multiple-comparisons trap prior sessions correctly nulled).
3. **Live surfaces consume it**: the stock page shows the matching-episode receipt for the
   name's current event class (n, shrunken medians, cohort context, distinct-period count),
   and the MTF alignment state (2D/3D/W) is visible at a glance.
4. **Prophet records the class forward**: a Doors-style shadow lane (Door W) appends
   fully-aligned washout-turn candidates to a prospective-only ledger from merge night —
   zero authority, prereg frozen before first accrual.
5. **Nulls printed**: every receipt carries n and the survivorship + clustering caveats;
   promotion grading is pre-specified as date-blocked (no naive pooled t-stats later).

## §1 The evidence this program stands on (frozen 2026-08-05/06)

- **MCD miss** (`research/washout_turn_name_lane/MCD_MISS_EVIDENCE_2026-08-05.md`): weekly
  canon CB fired 07-31 at the 6.3rd pctile depth; zero consumers of weekly grain per name.
- **Blindness census (this session)**: of 117 names currently in WASHOUT_TURN/TURN_WATCH,
  **0 are on the (07-31) board, 8 are cascade-eligible, 109 are invisible to Prophet**. The
  highest-conviction sub-class — WASHOUT_TURN with 2D+3D+W all bullish — holds **65 names
  right now (ABT, BKNG, BSX, CME, CRM, GILD, HCA, ICE, INTU, …) and 61/65 are invisible.**
  The MCD miss is a live 61-name class, not an anecdote.
- **IHM precedent** (`engine/index_momentum.py`, 16,115-event ledger): the event model —
  grids × direction × depth-pctile-at-cross × velocity × quality tag (`washout_turn` /
  `trap_zone` / `ordinary`) — already exists at index grain with canon math and an
  append-only parquet. SEA is IHM generalized to name grain + outcomes + conditioning.
- **Archetype substrate** (`engine/stock_fundamentals.py` ARCHETYPES + `archetypes_history`
  PIT labels; stamped into `data/us_prophet_rank/candidates/`): the operator's cohort
  vocabulary (quality_compounder, dividend_defensive, cyclical, rate_sensitive, …) exists —
  with a **coverage hole (1,625/2,932 NaN, including MCD)** owned by fundamentals coverage.

## §2 Prior rulings this program must respect (verified against primary sources 2026-08-06)

- **Per-name OUTCOME-AUDITION tool selection — KILLED, two-ruler** (PTT-W1a/W1a_T; DNR §2
  row 69; `PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md` §6/§8): in-sample best-of-grid
  per name has zero OOS persistence at panel scale. The SAME ruling holds
  **structure-MEASUREMENT tailoring OPEN**, and its surviving arm (structure-derived rung,
  PTT-W1b-pure) accrues live today in `engine/personality_gate_shadow.py`. SEA is on the
  lawful side by construction: ONE frozen indicator family + frozen class taxonomy; per-name
  evidence enters only as an n-weighted shrinkage posterior with every component n printed.
  The name never chooses its indicator; its history moves a prior, auditable, never a claim.
- **Washout-depth × HTF-turn interaction on gate-fires — KILLED** (#1747 Amendment-3,
  `esx_washout_x_turn`, stop-tax/MAE ruler; trial-ledger family recorded): SEA ships NO
  entry-stack change, no gate covariate, no 2W entry leg. Door W (§4) is a prospective
  shadow RECORD in the Doors framework, zero authority, prereg-frozen.
- **Sector-ETF-grain standalone washout→turn as return-alpha — NULL** (Oracle P8 P-W1;
  S-W3 monthly underpowered-null; `ORACLE_GAUNTLET_P8_RESULTS.md`): different universe
  (11 SPDRs, not names), different math (StochRSI K/D, not RSI-MACD line depth), different
  claim (cross-sectional alpha, not class-conditional base-rate receipts). Cited, not
  re-litigated; SEA's washout lane stays watch-tier (#4657).
- **Era-pooled inference across the 2010 break — FORBIDDEN without era split** (DT-R16,
  #1751): every SEA event carries `era`; atlas cells report pooled AND post-2010; regime
  stamps mirror `oracle/episodes.py` axes (VIX pctile, SPY-vs-200d, memory._regime_bucket
  vocabulary) so cross-program joins stay coherent.
- **Pre-onset winner identification — closed** (DNR §2 fingerprint Layer-3, #3202:
  "nothing measurable today identifies the future winner pre-onset"): SEA claims
  class-conditional base rates for a fired event, never that an event identifies a winner.
- **Rotation × cycle-position entry-confluence — DON'T-TEST** (DNR §1 row 37): SEA builds
  no such confluence; align_class is momentum-grid agreement, not cycle-position.
- **Leader-veto loosening — measured anti-fix** (Prophet US audit): Door W adds a lane for
  names the cascade cannot see; it loosens no veto.
- **Supporting descriptive precedents**: MWR per-member base rates shipped as
  descriptive-only with an explicit no-signal-claim line (the SEA receipt follows that
  form); `reports/mwr_timeframe_personality.md` measured per-name "home rungs" as REAL but
  idiosyncratic (no class-level law; Spearman ≈ 0.035) — exactly the shape shrinkage
  handles and audition cannot; WAVE6 F7 (weekly-turn present) was sign-correct on all
  three panels yet ~3.5pp under the promotion bar — display-tier is its earned home today.

## §3 The event-class taxonomy (FROZEN at birth; small on purpose — every axis divides n)

For each event (a canon `rsi_macd` line×signal cross on a completed bar):

| Axis | Values | Note |
|---|---|---|
| grid | 2B · 3B · W-FRI | session-grouped 2B/3B (canon), calendar W-FRI; 1D excluded (noise at name grain) |
| direction | bull · bear | both recorded; bear events are context/sell-side study material |
| depth_class | washout (pctile ≤ 15) · deep (15–30) · mid (30–70) · high (≥ 70) | pctile of the LINE vs trailing-10y same-grid history (IHM estimator, ≥ 20 finite obs) |
| level | below_zero · above_zero | line sign at cross — washout crosses below zero ≠ continuation crosses above |
| washout_len_class | short (< 8 bars) · medium (8–26) · long (> 26) | completed bars since line was last ≥ 0 (0 → not_applicable for above_zero) |
| align_class | 0 · 1 · 2 | count of the OTHER two grids whose line > signal at the event bar |

Recorded per event (not class axes): exact depth_pctile, hist velocity (IHM `hist_vel3`),
StochRSI K/D, drawdown-from-52w-high, PIT archetype + sector at event date, forward returns
at the grid's horizons (W-FRI: 13w/26w; 2B/3B: 21/63 sessions) filled only when matured,
and SPY same-window returns for excess computation.

## §4 Architecture

- **W1 `engine/stock_events.py`** — extraction + nightly append. Universe = mtf_upturn
  universe; closes deepened via the #4663 prepend-splice reader. Backfill script (off
  render path) writes the full history once; the nightly hook appends only new completed
  bars' events and fills newly-matured outcomes (idempotent, keyed by
  (ticker, grid, date, direction)).
- **W2 `engine/event_atlas.py`** — aggregation + shrinkage. Per (class, horizon):
  global / archetype / sector / name cells; name posterior = EB shrinkage
  `w = n / (n + k)` toward archetype then global (k frozen = 12); every cell carries n and
  distinct-period counts. Artifact `data/stock_events/atlas.parquet` + per-name receipt fn.
- **W3 live wiring** — `build_stock_library` injects `rec["event_atlas"]` (current class of
  the name's latest live event per grid + matching-episode receipt + alignment state).
  Stock page renders the episode receipt beside the washout chip; notifier gains alignment
  count in the washout message. NO edits to `engine/washout_turn.py` (#4663 in flight).
- **W5 Door W** — `prophet_doors`-pattern shadow lane: nightly append of names entering
  (WASHOUT_TURN ∧ align_class=2) to `data/prophet_doors/door_w_ledger.jsonl` with the
  frozen feature block; prospective only; prereg doc frozen in the same PR.
- **W6 macro interaction study** — frozen-frame: for dividend_defensive +
  quality_compounder archetypes, W-FRI washout-class bull events conditioned on the rates
  regime (1Y yield weekly RSI-MACD falling vs rising at event date, FRED DGS1) — the
  operator's MCD cause hypothesis, tested WITH the interaction term
  ([[regime-conditional-claim-needs-the-interaction]]). Report either way; receipts only
  if the interaction is real.

## §5 Statistical honesty (baked into artifacts, not left to discipline)

- **Survivorship**: the universe is today's basket membership — backfilled events inherit
  survivorship. Disclosed in the parquet metadata and every atlas receipt
  (`universe_basis: "2026 membership (survivor-biased backfill)"`). Widening to
  massive_stock_day's full panel is a later, separately-adjudicated step.
- **Clustering**: events overlap in time within and across names. Receipts show
  `n_distinct_years` beside n; promotion-grade inference is pre-specified as date-blocked
  bootstrap (never pooled t on raw events).
- **No look-ahead**: depth pctile at event uses trailing window ONLY; forward returns only
  for matured events; archetype labels are PIT (`archetypes_history`), falling back to
  `archetype_unknown` (its own cohort) — never today's label projected backward
  ([[latest-row-receipt-for-a-transient-state-expires]] generalized).
- **The n problem is answered by pooling, not pretending**: a name with n=3 shows its
  3 episodes AND inherits its archetype's curve with the blend weight printed.

## §6 Wave status

- W1/W2/W3: THIS SESSION (build lane, Opus).
- W5 Door W + prereg: follow-on PR after W1-W3 merges.
- W6: RAN 2026-08-06 — **ship:false**. Conditional NULL; the interaction is SIGN-INVERTED
  (−3.36pp @13w excess, growth/semis side carries the falling-rate premium); the primary
  regime flag measures ~13-week rate momentum, not cycle direction (κ = −0.071 vs the 26w
  change). No rates-conditioned receipt ships. Full packet:
  `research/signal_episode_atlas/W6_RATES_DEFENSIVE_INTERACTION_2026-08-06.md`; registered
  in the trial ledger as family `sea_w6_rates_defensive_interaction` (6 configs). A future
  re-entry needs a regime measure that actually dates easing cycles + PIT cohort labels —
  fresh prereg required.
- W7 (adjacent, ships alongside W1-W3): light the DORMANT Oracle episode-analogues feed —
  `memory.find_analogues` was fully built with a fail-open reader in `live.py`, but its
  producer was scheduled nowhere, so `active_episodes[].analogues` has been permanently
  null in production. Additive appended-at-end nightly step per Oracle Constitution §V.
- W4 archetype coverage heal (MCD NaN): chipped to fundamentals-coverage owner.
- CN/HK lanes: after US ships (operator sequencing law).
