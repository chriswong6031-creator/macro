# Macro Release Intelligence (MRI) — Masterplan

Prepared by Fable (main loop), 2026-07-07. Program: `macro-release-intel`.
Status: ratified charter + phased build plan. Display-only program; nothing here
touches a scored surface until the pre-registered forward gates in §7 pass.

## 0. Executive ruling

We build a system that, before each official US data release (CPI first, NFP
second), produces OUR OWN projection of the print with quantile bands and a
confidence read; compares it against an honest benchmark set (naive prior,
trailing trend, Cleveland Fed nowcast, market-implied when available); states
the surprise skew (which side of the benchmark set we sit, in units of
historical surprise dispersion); captures the actual first print when it lands
(ALFRED initial release, not the revised series); scores itself in public on an
append-only forward ledger; and publishes the whole object as display-only
regime context for the Neural Web — the inflation prints feed the inflation
axis of the quad, the labor prints feed the growth axis, and the policy
backdrop join (fed_path market-vs-dots gap, fed_stance, catalyst_tone guidance,
next FOMC) tells the reader what the print means for the Fed's forward path.

What this program is NOT (standing kills honored, §2): not an equity-direction
signal, not an entry conditioner, not an event-risk conviction dampener, not an
LLM-originated forecast.

## 1. Boundary — what already exists (census 2026-07-07)

- `engine/macro_surprise.py` (news W1, #1306): POST-print surprise cards vs
  revised prior / trailing trend / 3-5y z. LEAF, display-only. No projection,
  no consensus, no PIT. MRI extends this lane; does not replace it.
- `engine/event_calendar.py`: CPI/PPI/NFP/GDP/PCE/FOMC/claims/ISM dates from
  the FRED release-dates API with static CY2026 fallback. Reused as-is.
- ALFRED vintage infra (`collectors/fred.py:fetch_vintages`, `engine/pit.py`,
  `data/fred_vintage/vintages.parquet`): initial prints on disk today —
  CPIAUCSL/CPILFESL 1997→ (353 prints), PAYEMS 1997→ (354), PCEPI/PCEPILFE
  2000→, PPIFIS/PPIFES + sticky/median/flex CPI 2014→, ICSA/IC4WSA/CCSA 2009→.
  Backtest is feasible offline from the committed parquet.
- Real-activity nowcast (`engine/conditions.py` labor_nowcast): claims + Indeed
  + Treasury DTS withheld taxes + SF-Fed news sentiment → label only. The
  withheld-tax series is the closest existing NFP-bridge input; no quantitative
  model connects it to the print. MRI builds that model.
- Fed machinery: `engine/fed_path.py` (ZQ/SR3 vs FEDTARMD dots, gap_bp),
  `engine/fed_stance.py` (hawkish/neutral/dovish), `engine/catalyst_tone.py`
  (FOMC statement digests), `data/policy/intel.json` (Warsh/Bessent substrate,
  policy_intent_desk). MRI joins these read-only into `policy_backdrop`.
- NW integration surface: `config/synapse.yml` registry + CI guards
  (synapse_registry, dag_conformance, signal-bus doc regen), display-tier
  authority law (all five authority booleans False), cortex `read_artifact`,
  Mastermind auto-manifest via `external_consumers: [mastermind:context]`.
- In-flight collisions: PR #1635 (R5 macro context rail) is OPEN/CONFLICTING and
  owns `world_state.py` / `mastermind_context.py` / `ask_brain.py` deltas.
  PR #1758 ships a ZORI/Redfin housing HF product (conditioning phase-0 NULL).

## 2. Adjudication against standing kills (MRI-R1..R10)

- **MRI-R1 (scored-surprise kill honored).** DATA_SIGNAL_EXPANSION_2026 item #1
  SKIPPED "macro surprise" as a scored signal: no free PIT consensus, surprises
  absorbed at the print, Citi ESI ≈ −0.04 corr to S&P. MRI does not re-open
  that: it makes NO claim that release surprises predict equity returns. Its
  product is the regime/axis context and the Fed-path read. Any future claim of
  market-direction edge requires a new pre-registered study — not this program.
- **MRI-R2 (entry stack ban).** `esx_macro_release` is NULL 8/8, exhausted.
  Nothing in MRI may condition entries, fire chips, or touch the entry stack.
- **MRI-R3 (no conviction dampener).** Pre-FOMC drift is dead post-2016 and the
  announcement premium is positive. Calendar proximity and projected surprise
  never dampen or scale any score. `impact` stays display tier.
- **MRI-R4 (origination ban).** Projections are deterministic statistical
  models over PIT data. The LLM layer may only narrate calibrated fields and
  de-escalate; it may never originate or adjust a projection, skew, or
  confidence value.
- **MRI-R5 (consensus honesty).** We do not fake street consensus. The
  comparison object is a labeled `benchmark_set`: `naive_prior`,
  `trailing_3m`, `ar_model`, `cleveland_nowcast` (CPI family, forward-accruing
  only), `market_implied` (come-back C-2). Every UI/artifact string says
  "benchmark", never "consensus", until a true consensus source is wired.
- **MRI-R6 (PIT law).** Training/eval on ALFRED initial prints (`pit_vintage`).
  Input legs without vintages are declared `revision_optimistic` per leg in the
  artifact and the prereg. Cleveland nowcast history begins at our first
  collection date — no retroactive benchmark backfill.
- **MRI-R7 (display-only + gates).** Tier `display`, `horizon_role: context`,
  `scored_path_surfaces: []`, all authority booleans False. The word
  "validated" is banned from all MRI user-facing copy until §7 forward gates
  pass (CI-enforced repo-wide).
- **MRI-R8 (ledger law).** `data/release_forecast/forward_ledger.jsonl` is
  advanced only by the nightly lane. Intraday/backtest lanes never write it.
- **MRI-R9 (era law).** All historical accuracy tables era-split at 2010 and
  additionally report the 2021+ inflation-era slice. Monthly prints are
  non-overlapping; weekly claims stats use block-aware errors.
- **MRI-R10 (collision law).** No edits to `engine/neuralweb/world_state.py`,
  `mastermind_context.py`, or `ask_brain.py` while PR #1635 is open. NW
  visibility v1 = synapse registration + `external_consumers:
  [mastermind:context]` + cortex `read_artifact`. The dedicated world_state
  lobe + summarizer is come-back C-1 after #1635 resolves.

## 3. Design

### 3.1 Release set v1

| Release | Target variable | Model class | Institutional anchor |
|---|---|---|---|
| CPI (headline, core) | MoM % (SA) | component nowcast | Cleveland Fed daily CPI nowcast |
| NFP (payrolls) | MoM change, thousands | labor bridge | claims/ADP payroll bridges (SF Fed / street practice) |
| Claims (weekly) | level | short AR + seasonal | — (auto-scored, feeds NFP bridge) |

PCE/PPI/retail sales are v1.1 expansions (come-back C-4) — PCE is largely
derivable from CPI+PPI components and should reuse the CPI machinery.

### 3.2 CPI component nowcast (engine/release_forecast.py)

Legs, each PIT-stamped: energy (weekly retail gasoline GASREGW + WTI pass-through),
core persistence (sticky/median/flex CPI momentum, AR on core MoM),
shelter (CPI shelter momentum; ZORI lead once #1758 lands — read-only reuse),
pipeline (PPI final demand / core momentum), food (PPI food legs where free).
Combine by regularized regression fit walk-forward on ALFRED initial prints;
never refit inside the evaluation fold. Output: point + p10/p25/p50/p75/p90
from empirical residual quantiles of the walk-forward errors.

### 3.3 NFP labor bridge

Legs: initial+continued claims averaged over the survey reference week (the
week containing the 12th), withheld-tax YoY (Treasury DTS, already collected),
ADP private payrolls print (released the Wednesday before NFP; ALFRED vintages
if available, else `revision_optimistic` declared), Indeed postings trend
(display-only leg — copyrighted), AWHMAN momentum. Same walk-forward protocol
and quantile output as CPI.

### 3.4 Confidence and surprise skew

- `confidence ∈ [0,1]`: percentile of current predictive-interval width vs
  history × input-completeness fraction (how many legs have reported for the
  reference period). Both components published separately too.
- `surprise_skew`: (our point − benchmark_set median) / σ of trailing 24
  realized surprises for that release. Sign = direction we lean vs benchmarks;
  magnitude in surprise-sigmas. Plus `skew_tag ∈ {hotter, inline, cooler}` with
  ±0.35σ inline band (frozen in prereg).

### 3.5 Release-day capture + scoreboard

Nightly job (already after US close): if a tracked release printed today, pull
the ALFRED initial print, join the frozen T-1 projection from the forward
ledger, record: actual, our point + interval, each benchmark, realized surprise
vs each, interval coverage hit, skew-direction hit. Scoreboard aggregates per
release type: MAE vs each benchmark, p10–p90 coverage, skew hit-rate with
Wilson CI, n — nulls printed, never hidden.

### 3.6 Artifact contract (`release_forecast.v1`)

```json
{
  "schema": "release_forecast.v1",
  "asof": "2026-07-07T02:10:00Z",
  "display_only": true,
  "authority": {"can_score": false, "can_size": false, "can_trade": false},
  "upcoming": [{
    "release": "cpi", "period": "2026-06", "release_date": "2026-07-15",
    "days_to": 8, "target": "mom_sa_pct",
    "projection": {"point": 0.28, "p10": 0.13, "p25": 0.21, "p50": 0.28,
                    "p75": 0.35, "p90": 0.44},
    "confidence": 0.62, "input_completeness": 0.78,
    "benchmark_set": {"naive_prior": 0.24, "trailing_3m": 0.26,
                       "ar_model": 0.27, "cleveland_nowcast": 0.31,
                       "market_implied": null},
    "surprise_skew": {"sigma": 0.4, "tag": "hotter",
                       "vs": "benchmark_median"},
    "pit": {"basis": "pit_vintage", "revision_optimistic_legs": ["adp"]},
    "regime_axis": "inflation",
    "policy_backdrop": {"fed_stance": "hawkish", "gap_bp": -12,
      "implied_cuts_12m": 0.5, "next_fomc": "2026-07-29",
      "guidance_direction": "neutral"}
  }],
  "last_scored": [ "...release-day capture rows..." ],
  "scoreboard_ref": "data/release_forecast/scoreboard.json"
}
```

### 3.7 What the Neural Web does with it (usage spec)

Allowed (display/context): cortex reads it via `read_artifact` and may cite it
in the nightly memo ("CPI prints in 3 sessions; our projection leans hotter
than benchmarks by 0.4σ with policy stance hawkish — inflation-axis risk is
asymmetric"); Mastermind receives the compact manifest row (annotate-only);
the regime page shows which quad axis each upcoming release feeds; the W6
transmission study gives DESCRIPTIVE historical context for what same-sign
surprises did to rates/USD/quad-posterior — a weather report, not a trade.
Future LLM synthesis layers read `policy_backdrop` + projection + scoreboard
as one object (that is the point of the join).

Forbidden: sizing, entry gating, score dampening, board ordering, alert triage,
any Article-2 surface; kernel cells only via the standard quarterly FDR batch
(earliest 2026-10) and only if forward n has accrued.

## 4. Waves and PRs

- **PR-A (W0+W1, this PR)**: masterplan + prereg + data spine — config.yml
  FRED additions (GASREGW, JTSJOL, ADP series id verified at build time,
  UNRATE promoted from on-the-fly to collected), vintage_series additions where
  ALFRED supports them, Cleveland nowcast collector (fail-open, keyless,
  append-only daily snapshots), tests.
- **PR-B (W2)**: `engine/release_forecast.py` (CPI + NFP models, quantiles,
  confidence, skew) + walk-forward backtest harness
  `research/release_forecast/backtest_release_forecast.py` + results report
  (MAE tables vs baselines, era-split, coverage) + contract tests. Opus stats
  review before merge.
- **PR-C (W3)**: `scripts/build_release_forecast.py` nightly producer +
  forward ledger + scoreboard + release-day capture + `daily.yml`/`dag.yml`
  wiring + synapse registrations + SIGNAL_BUS regen + admin lobe description +
  policy_backdrop join. Contract + authority tests.
- **PR-D (W4)**: UI — "Release Radar" section on macro.html (projection vs
  benchmark set vs prior, interval cone, skew chip, countdown, scoreboard +
  track record). Bilingual EN/ZH, no translated `title=`, theme.js law.
- **PR-E (W5)**: pre-registered DESCRIPTIVE transmission study — realized
  surprise (sign×size, PIT) → next-1/5/21-session moves in 10y yield, 2s10s,
  broad dollar, SPY, sector RS, and quad_vector posterior shift; era-split;
  published as `release_playbook.json` display table. No gates, no signal.
  Opus stats review before merge.

Come-backs: **C-1** world_state lobe + macro_weather/mastermind summarizer +
ask_brain routing after #1635 resolves. **C-2** market-implied distribution
adapter (Kalshi/prediction-market read API) as a benchmark_set member — EXECUTED
(#1876 Kalshi collector + PR-I join; see §9.1). **C-3**
kernel-cell registration at the 2026-10 FDR batch iff forward n ≥ gate. **C-4**
PCE/PPI/retail-sales expansion. **C-5** true consensus feed if a licensed
source ever lands (drop "benchmark" labels only then).

## 5. Data acquisition notes

New FRED series (all keyless-capable): GASREGW (weekly retail gasoline),
JTSJOL (JOLTS openings, context leg), ADP national employment (id verified at
build: ADP* family), UNRATE + RSAFS promoted to collected config (currently
fetched ad-hoc by macro_surprise). Cleveland Fed inflation nowcast: public
endpoint discovered at build time from the indicators page; collector caches
raw payload, appends daily snapshot rows keyed (asof_date, target_month,
series); fail-open with 12h TTL; storage `data/cleveland_nowcast/nowcast.parquet`.
No paid data anywhere in v1 (house W6 paid-data SKIP-ALL honored).

## 6. Falsifiers / kill criteria

- Walk-forward MAE fails to beat `naive_prior` for a release type over the
  full era-split table → that release ships benchmark-only (honest null card:
  "our model adds nothing over naive here"), model leg retired, no iteration
  past 2 pre-registered spec attempts (anti-mining).
- Forward ledger after 12 prints: skew-direction hit-rate Wilson LB < 0.5 AND
  MAE ≥ naive → demote artifact to benchmark-only mode; masterplan updated;
  DO_NOT_REBUILD row appended if the family is closed.
- Interval coverage p10–p90 outside [70%, 95%] after 12 prints → intervals
  recalibrated once (isotonic on walk-forward errors); if still outside after
  12 more, quantile claims dropped from UI.
- Cleveland endpoint breaks ≥30 days → leg marked DARK on the card (foresight
  health pattern), never silently stale.

## 7. Forward gates (pre-registered; graduation, not authority change)

Per release type, evaluated only on the forward ledger (no backtest rows):
n ≥ 12 prints AND MAE < naive_prior MAE AND skew hit-rate Wilson LB > 0.5.
Passing grants a "graduated" badge on the card and permits a proposal (new
adjudication, not automatic) for confirmer-tier registration. Failing prints
the null. Nothing about these gates changes authority booleans — that would be
a separate program with its own gauntlet.

## 8. Ops

Producer runs in the nightly engine lane after collect (release capture needs
same-night FRED/ALFRED refresh; ALFRED vintage fetch requires FRED_API_KEY —
already injected in daily.yml). Compute is trivial (a few monthly series);
render-budget impact ≈ 0. All writes fail-open; a dead collector degrades the
card, never the build.

## 9. Codex "Economic Release Replication Machine" adjudication (2026-07-07 second wave)

Source: research/ECONOMIC_RELEASE_REPLICATION_MACHINE.md (Codex, doc-only
handoff). Verdict: the doc is the institutional-architecture layer this
program was pointed at; roughly 40% was already built by waves A-E on the
same day, and the deltas below are adopted into THIS program. Rulings:

- **MRI-R11 (no parallel system).** Codex's "Macro Release Lab" as a separate
  structure (engine/release_lab/, data/release_lab/) is REJECTED — same-lane
  duplication. Every adopted capability lands inside macro-release-intel's
  existing paths (engine/release_forecast*, data/release_forecast/,
  site/macrodata/release_forecast.json). The Codex doc is a design source,
  not a second program.
- **MRI-R12 (Cleveland history basis).** The Cleveland nowcast daily paths
  backfilled from the public endpoint carry obs_date as published; they may
  be used in DESCRIPTIVE comparison tables labeled "as re-served by the
  Cleveland endpoint". PIT-graded statistics keep the first_seen_asof rule
  from MRI-R6 unchanged.
- **MRI-R13 (gates).** Codex's consensus-relative gates are re-pointed at the
  benchmark set (no consensus feed exists — MRI-R5 stands). The §7 forward
  gates are pre-registered and UNCHANGED. Adopted as supplementary REPORTED
  (non-binding) diagnostics: interval_60 coverage vs [50%,75%], grade vs
  first release AND vs latest revision separately, and market-reaction
  usefulness. Codex's maturity horizons (18-24 CPI / 24-36 NFP prints)
  are adopted as display copy ("earned-trust horizon"), not as gates.
- **MRI-R14 (committee discipline).** Model-committee ensembling with learned
  weights is DEFERRED until forward-ledger maturity; until then one frozen
  spec per target (§6 anti-mining). Codex's own "weights must not be
  optimized until enough frozen observations" is made binding.
- **MRI-R15 (surprise distribution).** p_hot/p_cold/p_inline computed
  deterministically from our walk-forward residual distribution relative to
  the benchmark median (±0.35σ inline band from §3.4). No new authority; a
  restatement of existing quantiles.
- **MRI-R16 (market-implied prior).** collectors/prediction_markets.py
  (exists; Polymarket Gamma, keyless, append-only snapshots) fills
  benchmark_set.market_implied where a matching CPI/jobs event trades.
  Market-expectation CONTEXT only: never fused into the model point
  (prior-blending REJECTED — a model that ingests the market prior cannot
  detect a stale market prior), never a gate.
- **MRI-R17 (reaction layer).** A per-release "expected market sensitivity"
  chip is adopted as a DESCRIPTIVE join of release_playbook cells with the
  current regime label. The conditional reaction-function regression is
  deferred until playbook n grows; positioning inputs are FORBIDDEN
  (Signal Commons: positioning fusion illegal).
- **MRI-R18 (paid data).** PriceStats/Manheim-paid/LinkUp/Revelio/ADP-paid
  all SKIP (house W6 paid-data SKIP-ALL). Public Manheim mid-month value is
  a possible future keyless collector pending a licensing read.
- **Spec-attempt ledger.** Adding the shelter stock-adjustment leg (Codex
  §5.2, fed by the merged #1758 ZORI product) is pre-registered as spec
  attempt #2 of 2 for BOTH cpi_core and cpi_headline (§6 anti-mining).
  If attempt #2 fails its target's kill rule, that target goes
  benchmark-only; there is no v3 without a program-level adjudication.

Adopted build waves: **PR-F** ledger schema v2 (release_id/prediction_id/
inputs_hash/horizon_hours; dual grading first-vs-latest; EOD h0/h1 market-
reaction fields on scored rows; weekly claims target for ledger velocity;
engine module split for parallel component work). **PR-G** CPI component
upgrade (shelter stock-adjustment leg with lease-reset smoothing and
shrink-to-BLS-momentum divergence guard; per-component contrib_pp; known/
proxy/residual weight-share decomposition driving confidence v2; backtest
v2 re-run with full legs). **PR-H** NFP decomposition (private/government
split, AHE + hours as v2 targets, birth-death prior table from published
BLS CES tables, JOLTS leg, revisions-risk field). **PR-I** market-implied
benchmark + surprise_distribution + sensitivity chip. **PR-K** UI v2
(component breakdown, known/residual bar, market-implied row, sensitivity).

### 9.1 Second-wave reconciliation (2026-07-07, Fable main loop)

The same external doc was independently adjudicated twice on 2026-07-07 (this
file §9 via #1877, and a parallel Fable lane whose branch predated #1877 —
closed PR #1879). The verdicts CONVERGED on every major call: no parallel
system, benchmark honesty, committee/ensemble deferral to ledger maturity,
component attribution + market-implied benchmark as adopted deltas. This
section reconciles the second lane's remainder into canonical numbering.

- **MRI-R19 (attribution law).** Component contributions (PR-G) are the
  linear model's own exact decomposition (coef × z-value, in pp), published
  as-is with the residual share printed. They may never be manually adjusted,
  re-weighted for narrative, or hidden when unflattering.
- **MRI-R20 (quirk law).** Release-quirk flags are deterministic calendar
  facts with citations (CPI annual weight-update/seasonal-revision print; CPI
  health-insurance reset window; NFP CES benchmark + population-control
  print; claims holiday weeks; 4-vs-5-week survey gaps). They annotate
  uncertainty on the card; they never shift the point, intervals, or skew.
  Strike/weather flags require a free feed (come-back C-7). Build wave:
  PR-G/PR-K.
- **§6 application — claims (evidence attached).** The second lane ran the
  weekly-claims walk-forward offline from committed ICSA vintages
  (research/release_forecast/CLAIMS_BACKTEST.md). Its ridge spec (attempt 1)
  FAILED naive_prior (MAE 40.8k vs 28.7k full window; 24.0 vs 14.8 2021+).
  The #1877 frozen IC4WSA spec (attempt 2) was evaluated under the same
  protocol: MAE 43.9k vs naive 27.9k (full window); 17.7k vs 14.8k (2021+) —
  FAILED on both arms. Per §6, claims mode = benchmark_only, enforced in the
  producer. Benchmarks (naive_prior, trailing_4w, ar_model) are graded on the
  forward ledger either way — 52 prints/yr of ledger velocity is the point,
  not the model point. There is no attempt 3 without a program-level adjudication.
- **Market-implied sources.** MRI-R16 stands; #1876 adds a Kalshi
  release-ladder collector (KXCPI / KXPAYROLLS / KXJOBLESSCLAIMS, first-seen
  snapshots, implied_median only — implied_mean REJECTED as
  tail-assumption-dishonest on an open-ended ladder). PR-I joins whichever
  source has a matching market; context only, never fused (MRI-R16).
- **Naming.** The second lane's "Package F/F1..F4" labels are retired in
  favor of this file's PR-F..PR-K wave names; its Kalshi collector is PR-I
  groundwork.

**PR-I shipped (2026-07-07).** MRI-R15/R16/R17/R20 implemented in this wave.
Units decisions: KXCPI strikes are headline MoM % (used as-is); KXPAYROLLS and
KXJOBLESSCLAIMS strikes are raw counts normalized ÷1,000 to match artifact
thousands convention (cited in `_read_market_implied` comment referencing
`collectors/kalshi_releases.py _SERIES_CONFIG`). cpi_core always returns None
(no KXCPI market for core; headline never proxied for core per MRI-R16).
Sensitivity thresholds derived from `research/release_playbook/results/playbook_v1.json`
(era='all', regime=None, outcome='dgs10_bp', horizon='h1', hot+cold buckets):
CPI max-abs mean = 3.27 bp (cold) → tag='medium'; NFP max-abs mean = 3.88 bp
(hot) → tag='high'; claims = null (no playbook data, fail-open honest).
Tercile-style cuts: low <2 bp, medium 2–3.5 bp, high ≥3.5 bp. Quirk flags:
five calendar rules implemented — `cpi_weight_update` (Jan CPI), `cpi_health_insurance_reset`
(Apr+Oct CPI prints since Oct 2023), `nfp_benchmark_revision` (Jan NFP),
`nfp_five_week_gap` (pure calendar: 35-day gap between reference Saturdays),
`claims_holiday_week` (period-end Saturday within ±3 days of New Year's/Jul 4/
Thanksgiving/Christmas). All flags are pure annotations; none alter point/
intervals/skew. Come-back C-2 marked EXECUTED in §4.
