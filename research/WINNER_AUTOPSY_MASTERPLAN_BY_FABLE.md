# Winner Autopsy Lab — masterplan (by Fable)

Date: 2026-07-07
Status: ADJUDICATED CHARTER — Wave 0 shipping in the same PR as this document.
Owner program: **long-hold** (this is a *department inside* the Long-Hold Thesis lobe, not a
new lobe — "Thesis lobe" as a standalone lobe is KILLED, `research/DO_NOT_REBUILD.md` §2).
Input docket: `research/MODERNA_STYLE_SPONSORSHIP_BREAKAWAY_RESEARCH.md` (Codex, 2026-07-07,
committed as-received alongside this plan).

---

## 0. Operator intent (verbatim reconstruction)

Start a top-down department in the long-hold lobe that **reverse-engineers why specific
stocks produced large alpha against cohort and index** (exemplar: MRNA 2026, +49pp vs XBI
over 21d, +126pp YTD vs XBI), builds a growing database of such winner case studies
(Codex research pulls in a fixed format), extracts the factors that *preceded* the run,
and uses them to spot the next one **before it begins**. Frontend visibility in the admin
panel under a Long-Hold subpage (which did not exist — it does now, §7).

## 1. Adjudication of the Codex docket

The docket is good raw material — ~60% adoptable, ~25% must be amended to comply with
standing law, ~15% is struck by prior rulings. Verdicts:

| Docket component | Verdict | Grounds |
|---|---|---|
| 5-stage anatomy (compressed prior → catalyst ladder → relative breakaway → liquidity confirmation → convexity) | **ADOPT** as descriptive vocabulary | new; no collision |
| Candidate gate §5.1 (excess-return + new-high + volume confirm) | **ADOPT** as detector v1 (price/volume core only) | PIT-clean, mechanical |
| Fused 100-point score §5.2 | **STRUCK** | positioning fusion ILLEGAL + Signal Commons R3 (no fused verdicts); replaced by per-axis states + AND-gate (thesis-funnel precedent, LH-R2) |
| Ownership/13F component (+10 pts) & `ownership_pressure` formula §4.1 | **STRUCK as positive signal** | NEXTL-U13 (nondelegable): 13F-as-positive-sponsorship proposes the opposite sign to three filed verdicts (esx_insider_sponsor 3-for-3 null @21d; insider_sponsor_lh F4 null @252d; smart_money contrarian/context-only). Survives as context display + crowding hazard only |
| Short-interest legs §4.3 | **DEFERRED with L10** | NEXTL-U19: PIT short interest unavailable (FINRA SI store has ONE settlement date); daily short volume ≠ short interest (docket itself concedes) |
| "Sponsorship" vocabulary | **RENAMED throughout** | NEXTL-U19 defers "sponsorship lifecycle grammar"; `sponsorship_state` (bottom_sensors, frozen §C3), the S1 HTF badge tooltip, and SLF-026 already use the word for three *different* things. This department never says "sponsorship" in shipped artifacts |
| Options convexity features §4.4 | **ADOPT forward-only** | per-ticker options history starts 2026-06 (polygon_gex accrual; thetadata per-ticker backfill never ran, `n_roots=0`). Historical fingerprints on options are structurally impossible; the columns join the census from 2026-06 onward, coverage-flagged, and accrue |
| Research-echo (analyst targets/revisions) §4.5 | **CASE-FILE ONLY + accruing surface** | no analyst-target surface exists in the repo (census confirmed NOT FOUND); `data/revisions/history.parquet` accrues from 2026-06-16. Qualitative research-echo lives in Codex case files with URLs; quantitative joins begin when the surface has depth |
| Entry logic §6 (digestion / continuation / failure reads) | **ADOPT as display vocabulary** on watch rows | display-only; no board chips, no ordering |
| Forward-validation labels §7.4 (clean-hold, blow-off, continuation) | **ADOPT** as episode outcome labels | |
| Implementation §7.1 as a standalone "Breakaway Desk" site page | **DEFERRED** | W0 ships admin-panel surface only; public site copy needs its own wave |

## 2. The core reframe: census first, cases second

Studying winners one at a time is **selection on the dependent variable** — every feature
you find in MRNA's rear-view has an unknown base rate among lookalikes that went nowhere.
The department is therefore built in three layers:

- **Layer 1 — Episode census (mechanical, complete).** Detector D (§4) runs over the full
  post-2014 history × the S&P-1500 PIT universe and harvests *every* relative-strength
  breakaway onset — the future winners AND the blow-offs, squeezes, and sector-beta
  mirages. Follow-through labels partition them. This is the statistical substrate; it is
  immune to winner-selection because it selects on the *entry condition*, not the outcome.
- **Layer 2 — Case library (annotated subset).** Operator-flagged winners get Codex
  deep-dives in a fixed machine-readable schema (`winner_case.v1`, §6): catalyst ladders
  with publication dates, mechanism narrative, hazards. Machines cannot extract this;
  Codex can. Every case must reconcile against Layer 1 (the engine computes the mechanical
  onset for the case ticker; a case whose ticker never triggers detector D is itself a
  finding — either the thresholds are wrong or the "winner" wasn't a breakaway).
- **Layer 3 — Fingerprint studies (descriptive → gated).** Two questions, in order of
  practical value: (a) at onset, what separates episodes that *kept going* from those that
  failed — this is the question a live watcher faces; (b) pre-onset, what separated
  eventual breakaway names from matched controls sampled the same calendar day. All
  descriptive/display-only until a distilled pairlet earns a pre-registered slot (§8).

The prospective scanner ("Breakaway Watch") is **the same detector D evaluated at today's
date** — one definition serves the backtest census and the live watchlist, so the live
surface is honest by construction.

## 3. Rulings (WA-R1..R10)

- **WA-R1 (no fused score).** No composite numeric score is emitted anywhere. Axes
  (relative breakaway, liquidity confirmation, options context, catalyst annotation) are
  separate fields; any candidate/watch state is a pure AND-conjunction of named
  conditions, mirroring `thesis_funnel` (LH-R2).
- **WA-R2 (ownership is context, never signal).** 13F / insider / smart-money / congress
  fields may appear on case files and episode rows as context columns flagged
  `context_only: true`. They never enter detector D, never enter a fingerprint aggregate
  as a positive-sign candidate, and the only permitted signal direction for crowding
  reads is de-escalation (NEXTL-U13, smart_money law).
- **WA-R3 (vocabulary).** Shipped names: `winner_autopsy` (department), `breakaway_watch`
  (live states), `winner_episodes` (census). The word "sponsorship" is forbidden in all
  new artifacts, fields, and UI copy. "Breakaway" here = relative-strength breakaway; the
  dormant `gap_hold_events()` in `engine/entry_primitives.py` (gap-based, appendix-locked)
  is unrelated and untouched.
- **WA-R4 (estimator laws).** Winner/control comparisons are time-matched by construction
  (controls sampled at the episode's own t0 date). Cross-case aggregates are reported
  split by year/era and cluster at the month level; naive episode-pooled inference is
  forbidden (DT-R14). History starts 2014 (post-2010 break; DT-R16 satisfied by
  construction). Survivorship stamps mandatory on every row; episodes whose forward
  window crosses the massive-store gap (2021-10-25 → 2025-01-02) carry
  `gap_leg_crossed=true` (calendar-continuity guard, #1528 precedent).
- **WA-R5 (display ceiling).** Everything in this department is display-only
  (`_display_only=True`, `horizon_role=hold_thesis`, `fdr_family=long_hold`,
  `scored_path_surfaces=[]`). Nothing feeds board ordering, alert triage, top-setups,
  push floor, or any Mastermind money path. Verdict-grade claims require a future
  pre-registered study at a declared ruler (§8); until then all tables are labeled
  descriptive.
- **WA-R6 (LLM boundary).** Codex/LLM output enters only as case-file *evidence with
  citations* (catalyst dates, mechanism narrative). All numerics are computed
  deterministically by the engine from repo data. LLMs originate no signals, scores, or
  escalations (house law).
- **WA-R7 (A2 one-way firewall).** Fingerprint features that belong to registered A2
  roster families (F1 fundamentals, F2 washout_tf, F3 expect_drift, F4 insider) are
  excluded from cross-case *aggregate* tables for episodes with t0 ≥ 2024-01-01 until the
  A2 analysis script commits (mirror of the Ruler-P ≤2023-12-31 discipline, LH-R14).
  Non-overlapping families (price/volume geometry, base compression, 8-K density,
  options-era columns) are unrestricted. In the other direction: **no A2 roster amendment
  may cite winner-autopsy output** before A2 freeze — that would be a laundered peek.
- **WA-R8 (hypothesis budget).** Wave 0 registers ZERO statistical hypotheses. LH-R12
  headroom is Σ=29/40; a future winner-autopsy pairlet (≤5 features, one ruler) may
  request slots only by explicit Fable/operator ruling after ≥8 annotated cases and one
  opus-reviewed fingerprint report.
- **WA-R9 (ledger law).** `breakaway_watch_history` advances nightly-only via
  `--write-history` (sole-advancer; `--smoke`+`--write-history` hard-exits, thesis-funnel
  precedent). Keep-FIRST per (ticker, snapshot_date).
- **WA-R10 (holdable-winner fence).** This department does not run the deferred
  B/HOLDABLE_WINNER replay on `missed_hold` labels (GAP-U13); its population is detector-D
  onsets, not gate fires. Any future join between winner episodes and gate-fire labels
  needs its own ruling.

## 4. Detector D — breakaway onset, v1 (frozen for the census; display thresholds)

All inputs are trading-day bars; benchmark = GICS sector ETF via
`data/breadth/ticker_sectors.parquet` + the `_GICS_ETF` map (grade_us_board precedent);
fallback benchmark = SPY with `benchmark_fallback=true`.

Candidate condition (all true on day t):
```text
liquid        : median_dollar_volume_20d >= 25_000_000
rel_breakaway : excess_21d >= +20pp  OR  excess_42d >= +25pp     (vs benchmark ETF)
new_high      : close >= max(close, prior 63 trading days)
vol_confirm   : dollar_volume_z21 >= 1.0  OR  dv_5d/dv_60d >= 1.5
```
Onset `t0` = first day the condition is true with no candidate day in the prior 63
trading days (episode cool-down; one episode per ticker per 63td window). The identical
function evaluated at the latest bar yields today's `breakaway_watch` states:
`breakaway` (in-window candidate), `emerging` (rel_breakaway true, awaiting confirm),
`digestion` / `continuation` / `failed` (post-onset reads per docket §6 vocabulary),
`none`.

Outcome labels per episode (matured horizons only, forward excess vs benchmark):
`fwd_excess_{21,63,126,252}d`, `clean_hold` (no close below t0 close before a new 63d
high), `blow_off` (≥50% of the trailing 21d impulse retraced within 21td),
`durable_winner` (fwd_excess_126d ≥ +15pp AND clean_hold), `failed` (fwd_excess_63d ≤
−10pp). Labels are v1-frozen descriptive definitions; changing them post-hoc requires an
amendment note in this file.

Controls: for each episode, ≤20 same-sector tickers, PIT-active
(`sp1500_pit_membership`), liquidity floor met, not in candidate state within ±21td of
t0, sampled at the same calendar date with the identical feature extraction.

## 5. Feature families (PIT tiers per census 2026-07-07)

- **Tier-1 historical (2014→):** price/volume geometry (base compression: drawdown from
  252d high at t0−21d, days below 200dma, RS-turn 21/63, dv_z, up/down dollar-volume,
  close-location value), annual+quarterly fundamentals (`asof_date`-gated), SUE
  (`eps_quarterly` + `earnings_8k_dates` for true announcement dates), 8-K catalyst
  density (`material_8k_events`, PIT `filing_date`), archetype history
  (`data/archetypes/history.parquet`, PIT `asof_date`).
- **Tier-2 accruing (joins begin at each surface's birth, coverage-flagged):** per-ticker
  GEX/IV (`data/polygon_gex/summary_*.parquet`, 2026-06→), options sensor state
  (`data/options_entry/state.parquet`), gex_structure_state (read-only consumption of
  `site/options_structure/gex_state/*.json`, #1816 — never re-emit a parallel regime),
  analyst revisions (`data/revisions/history.parquet`, 2026-06-16→), news sentiment,
  FINRA short volume, beneficial-ownership 13D/G.
- **Context-only (WA-R2):** quiver 13F (`ReportPeriod`+45d lag), insiders (`fileDate`
  PIT), smart_money, congress.

Known structural honesty limits, printed on every artifact: full-universe daily prices
gap 2021-10-25→2025-01-02 (massive store); dead-name coverage 415/1,083 (episodes on the
2,495-ticker long-hold price-resolution universe inherit its survivorship stamps);
options/revisions fingerprints are forward-accruing only — the operator's "did MRNA show
an options pattern months ago" question becomes answerable for the *next* MRNA, roughly
mid-2027 (clock registered).

## 6. Case library — `research/winners/`

- `research/winners/README.md` — schema spec `winner_case.v1` + operating loop.
- `research/winners/CODEX_WINNER_CASE_PROMPT.md` — the reusable operator prompt (fill
  TICKER/YEAR, paste to Codex, save output under `research/winners/cases/`).
- `research/winners/cases/<TICKER>_<YYYY>.md` — narrative + fenced `winner_case.v1` YAML
  (parsed by the engine; invalid YAML fails the build test).
- Seed case: `MRNA_2026.md`, distilled from the input docket.

## 7. Surfaces & wiring (Wave 0)

- `engine/winner_autopsy.py` — pure computation (detector, labels, controls, features,
  case-YAML reconcile). No I/O.
- `scripts/research/build_winner_autopsy.py` — `--backfill` (off-render, on-demand),
  default nightly mode (incremental watch states + panel JSON), `--write-history`
  (nightly sole-advancer append).
- Artifacts (all registered in `config/synapse.yml`, hold_thesis/long_hold/display):
  `data/research/winner_episodes.parquet`, `data/research/winner_autopsy_panel.json`
  (admin-readable summary), `data/research/breakaway_watch.parquet`,
  `data/research/breakaway_watch_history.parquet`, manifest.
- Registry ripple (3-file recipe): SIGNAL_BUS regen + count bump, hold_thesis allowlist
  in `tests/test_horizon_firewall.py`, `config/dag.yml` + `daily.yml` step (serial,
  non-fatal, `build_bottom_sensors` pattern).
- Admin: standalone nav tab **Long-Hold Lobe** (Neural Web group) — `admin/long_hold.py`
  + `GET /api/long_hold` + `RENDER.long_hold`; sections: thesis-funnel snapshot, label
  distribution, Winner Autopsy (cases, census, watch), long-hold evidence clocks.
  Read-only, JSON-only (no engine/scripts imports, no parquet reads in admin).
- Evidence clocks (`data/experiments/registry_seed.json`): first watch-ledger read
  2026-10-15; case-library ≥8-cases review 2026-09-15; options-era fingerprint depth
  2027-06-15.

## 8. Waves

- **W0 (this PR):** everything in §6–§7 + backfill artifact committed.
- **W1 (operator loop, no code):** accumulate 5–10 Codex cases across sectors/eras
  (biotech, software, industrial, consumer; include at least 2 *failed* breakaways as
  negative cases — the prompt supports `case_type: failed_breakaway`).
- **W2:** cross-case fingerprint report v1 (opus-reviewed; WA-R7 restrictions applied);
  candidate pairlet identified, NOT registered.
- **W3 (gated by WA-R8 ruling):** pre-registered Ruler-W pairlet study — winners vs
  matched controls at declared horizons, month-clustered, era-split; ≤5 hypotheses
  against LH-R12 headroom.
- **W4 (clocked 2027-06):** options/revisions-era fingerprints once Tier-2 surfaces have
  ≥12 months depth.
- **Deferred:** public site "Breakaway Desk" page; short-interest legs (with L10);
  sector-relative live column on the US board (would touch tactical surfaces — needs its
  own firewall ruling).

## 9. What would kill this

Printed for honesty: if the census shows onset-day features carry no discrimination
between durable winners and failures beyond liquidity/era (the likely null per repo
priors — staleness alpha null, half-lives all-null, FRESH-BUY refuted), the department
collapses to (a) an honest descriptive census + case library and (b) the live watchlist
as a *attention* surface with printed base rates. That outcome is still worth the build:
base rates on "how often does a +20pp/21d breakaway keep paying" are currently unknown
in-house and would discipline chase behavior by themselves.
