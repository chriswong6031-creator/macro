# Prophet US Conditional Intelligence Fusion — VNext masterplan (by Fable)

**Date:** 2026-08-14 · **Status:** PR-0 — architecture / measurement / arena freeze. No live
ranking change. · **Program:** `WS:PROPHET-CONDITIONAL-FUSION` · **CEO ruling record:**
`DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY`
**Parents:** `research/PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` (the estate census +
bounded-authority ladder this program amends), `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`
(us_prophet_v1/v2), `research/US_BOARD_MEASUREMENT.md` (measurement canon),
`research/EVAL_OS_SITREP_2026-08-12.md` (evaluation standards + the honest baseline).
**Siblings (consumed, never duplicated):** PR #5578 Live Entry Radar · PR #5583 Bottom-Up Stock
Identity & Expert Routing.

---

## §0 The ruling, the acceptance gates, and what PR-0 is

### §0.1 The CEO ruling (2026-08-14), restated precisely

The blanket doctrine in `engine/us_board_rank.py` — that theme, sector turn, narrative, smart
money, insider, SUE, options/GEX, fundamental quality and the other contextual lobes sit under
**permanent** zero score authority (`ZERO_SCORE_AUTHORITY`, us_board_rank.py:430-455) — is
**no longer the intended end-state architecture**. The replacement law:

> **UNVALIDATED AT BIRTH → EARNED CONDITIONAL AUTHORITY.**
> No intelligence lobe receives automatic score authority. No lobe is permanently forbidden
> from score/rank authority merely because an earlier composite or interaction failed. A lobe
> may earn influence when point-in-time evidence shows it contributes incremental information
> in a defined context, horizon, setup species, or regime.

What the ruling does **NOT** authorize (its own text, binding on every wave):

- No restoration of the old additive `potential_score`, no "number of confirming desks"
  score, no everything-goes composite.
- No casual change to the live rank formula. **The deployed `us_prophet_v2` remains the
  CHAMPION until a challenger earns promotion** through the arena in §8 and the promotion
  gate in §8.6. The blanket *prohibition* is overruled immediately; live ranking changes
  still require evidence.
- The architectural correction is **from fixed global weights and blanket zero-authority to
  conditional evidence fusion with independently measurable experts** — not from "no
  composite" to "any composite".

### §0.2 Acceptance gates for THIS PR (PR-0) — "not done unless"

- **G0.1** Current end-to-end authority graph documented with file:line receipts (§2).
- **G0.2** Exact per-lobe authority table: candidate / score / rank / gate / display-only,
  with the code site that grants or denies each (§3).
- **G0.3** PIT history/coverage matrix per lobe, with history start dates and PIT-field
  verdicts (§4).
- **G0.4** Lineage/redundancy map: evidence families declared, shared-upstream edges named
  (§5).
- **G0.5** Current score pathology measured from the live ledgers, not asserted (§6).
- **G0.6** Outcome definitions frozen (§7) and modeling arena frozen (§8) **before** any
  challenger is trained — leaderboard rules may not move after results exist.
- **G0.7** Validation protocol frozen (§9), encoding the house estimator laws
  (`DNR:LAW-TIME-CLUSTERED-CI`, `DNR:LAW-ERA-SPLIT`, `DNR:KILL-OFFHORIZON-VERDICTS`).
- **G0.8** Interop contracts with #5578 and #5583 stated as consumed interfaces (§11); zero
  duplicated machinery.
- **G0.9** Explicit superseded-vs-intact ruling ledger (§12) — every standing kill this
  program touches is named by `DNR:<KEY>` with its LANDED disposition; the two row
  amendments ship in this PR with the regenerated compiled blocklists.
- **G0.10** Agent OS records minted (`WS:PROPHET-CONDITIONAL-FUSION`,
  `DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY`) + handoff;
  `python3 scripts/agentos.py validate` exits 0.
- **G0.11** Independent adversarial review (opus reviewer) run against the §16 attack list;
  every blocker resolved in this document before merge (§17).
- **G0.12** No engine, score, gate, template, or data-plane change in this PR (the DNR
  registry amendment + auto-regenerated compiled blocklists are the adjudication's own
  record-keeping, not a behavior change to any scored path). The one
  permitted exception class — "obviously missing telemetry that must begin accruing
  immediately" — is deliberately NOT exercised here; §13 names the fields and routes them to
  PR-1 within days, with the calendar cost stated.

### §0.3 What PR-0 is for

The purpose of PR-0 is to make the next implementation hard to fool. Everything below is
either a receipt (what exists today), a frozen rule (what the challenger will be judged by),
or a design commitment narrow enough to be attacked. The build starts in PR-1.

---

## §1 Why the blanket doctrine existed, and why it is being superseded

The zero-authority doctrine is not folklore; it has receipts, and the supersession must not
erase them:

1. **The conviction composite was measured anti-predictive at the top.** Published board
   order P@1 0.20 vs 0.60 re-ordered by residual alpha; `corr(board_position, excess_5d) =
   +0.07`; top-5 lift −13.7 points vs the board's own base rate
   (`research/US_BOARD_MEASUREMENT.md` §1). The ruling "order by edge, gate by timing, never
   the reverse" was earned, and `ZERO_SCORE_AUTHORITY` was its enforcement.
2. **Naive additive blends dilute.** The Phase-0 timing blend was reverted
   (`reports/setup-score-phase0.md`); `DNR:KILL-PROPHET-POP-MERGE` fenced blended
   conviction×timing ranking.
3. **Naive cross-market transport fails.** All four CN findings failed US transport
   (turnover monotone→bimodal, confirmation-negative→positive, membership-quality→crowding,
   relay-early→null; roadmap §5).
4. **Several lobes were killed as STANDALONE scored signals on deep panels**: SUE/PEAD (IC
   0.0006 deep, t_HAC 0.06), short interest (FDR-fail, "size in disguise"), naive insider
   net-$ (folklore), 13F-positive (opposite sign to filed verdicts), insider clusters
   (display-tier; do not survive BH-FDR)
   (`research/INTELLIGENCE_HUB_V2_RESEARCH.md` §4.3, V3 Phase-2 premise correction).

**What actually failed in every one of those episodes is a specific CONSTRUCTION**: a fixed
global weight, an unconditional standalone signal, an uncontrolled composite. What was never
tested — because the substrate to test it did not exist until the US Context Vector shipped
(2026-08-04) — is **conditional, incremental, interaction-aware contribution**: does lobe X
add information *given what Prophet already knows*, *in context C*, *at horizon H*? The
blanket doctrine collapsed "this construction failed" into "this information is forbidden",
which the house's own epistemics law ("a kill closes the specific construction tested, not
the search space") never licensed as a permanent state.

The strongest internal evidence that conditioning is the right axis: the four-for-four
transport failure above is itself a **conditionality result** — the same evidence means
different things in different markets/regimes. And the board's own history contains one
earned conditional promotion already: the v2 RECLAIM waiver (admission leg waived **when
basket peers are washed out at the ratified notch** — `research/RECLAIM_VETO_CONDITIONAL_PREREG.md`
§4 Arm P), which is precisely "evidence earns influence in a defined context".

The supersession therefore does not repeal the evidence; it repeals the *permanence* and the
*unconditionality* of the response to it.

---

## §2 Current Prophet US end-to-end authority graph (deliverable 1)

Census run 2026-08-14 against HEAD; live receipt used throughout:
`git show HEAD:site/factordata/us_standouts.json` — `as_of 2026-08-13`,
`board_definition us_prophet_v2`, 69 buy rows, 12 featured.

**Where it runs.** `.github/workflows/daily.yml:33-34` — cron pair `30 22 * * *` (18:30 ET
EDT) / `30 23 * * *` (EST), ET regime gate at `daily.yml:84`; engine job
`timeout-minutes: 300`. `scripts/build_stock_library.py` runs *inside* `build_site`
(`daily.yml:5096`), not as its own step.

```
NIGHTLY (daily.yml, 18:30 ET)
│
├─ engine/signal_gate.py  →  site/factordata/signal_gate.json          [CANDIDATE]
│    the confluence T1→T4 cascade; build_stock_library.py:604 names it
│    "the discovery board's PRIMARY buy gate". _cascade_elig() at
│    build_stock_library.py:1261 turns `eligible` into buy-lane membership.
│    Feeds verdict.{tier_cascade, ticks, provisional, eligible, above200,
│    weekly_bull, fresh_bars, fresh_bars_knowable, asof, last}
│
├─ engine/entry_signal.py (assess) → rec["entry_signal"]                [SCORE]
│    build_stock_library.py:3663-3666 → entry_sig map → row["entry_signal"]
│
├─ residual alpha (build_site per-ticker) → row["alpha"]                [SCORE]
│    build_stock_library.py:2674-2682 alpha_pt → :3415 rec["alpha"]
│
├─ engine/extension.py (extension_signals, whole-library panel)         [SCORE+GATE]
│    build_stock_library.py:3169 ext_map → :4882 row["ext_z"]
│
├─ engine/coiled.py (coiled / washout_ctx)                              [SCORE]
│    build_stock_library.py:3402 _coil_wash → :4949-4950 row["coiled"]
│
└─ engine/us_board_rank.py :: score_rows()   ← build_stock_library.py:5165-5173
   │
   ├─ SCORE_WEIGHTS (us_board_rank.py:175-181) — signal 30 / entry 25 /
   │  edge 25 / runway 10 / quality 10, sum pinned = 100
   │    · signal_value():537   ← verdict tier/provisional/ticks           [SCORE]
   │    · entry_value():563    ← entry_signal.status (FLAT on 5 statuses) [SCORE]
   │    · edge_value():626     ← alpha_percentiles():581 over the pool    [SCORE]
   │    · runway_value():637   ← ext_z / antichase_shadow_blocked         [SCORE]
   │    · quality_value():665  ← coiled.star/coiled/washout_ctx           [SCORE]
   │
   ├─ stage_for():725 → row["stage"] ∈ live/setting_up/ran/basing/blocked [RANK-GROUP]
   │    "DISPLAY-TIER ONLY — decides grouping, never membership, never
   │     score, never who is featured" (:736). Bucket IS the outer sort key.
   │
   ├─ SORT: (stage_rank, −prophet.score, ticker)  (:1136-1142)            [RANK]
   │    → row["score_rank"], row["display_rank"] (:1147-1148)
   │
   ├─ featured_shortfalls():890 → featured / featured_blocked_by          [GATE]
   │    status class first (:942-944), stage veto (:946-950), tier (:952),
   │    ticks (:958-962), provisional (:964), antichase (:967),
   │    ext_z > 2.0 (:984-986), alpha < 0 (:988-992), earnings blackout
   │    (:994-998), caps featured 12 / sector 4 (:1154-1157)
   │
   ├─ load_reversal_cohort():1555 ← site/basketdata/us_basket_turn.json
   │  + data/baskets/membership.json → row["reversal_member"]             [DISPLAY]
   ├─ stamp_themes():1838 ← data/baskets/{latest,membership}.json         [DISPLAY]
   └─ build_ran_rows():2017 → wide["ran"] (build_stock_library.py:5248)   [DISPLAY]

ARTIFACT  site/factordata/us_standouts.json
   (config/synapse.yml:2843-2877 — tier: display, weights: none,
    scored_path_surfaces: [board_ordering, top_setups])
   ├─ SITE  templates/dashboard.html.j2:15459+ (buy grid, stage labels)
   ├─ scripts/build_prophet.py:110 STANDOUTS_PATH → plan origination —
   │    plans sorted by "priority score desc" (:2185, :2192)              [RANK]
   ├─ scripts/grade_us_board.py --nightly (daily.yml:4024)
   │    → data/us_board_ledger/{snapshots.jsonl, retro_grades.parquet},
   │      site/factordata/us_board_track.json, us_board_outcomes.json;
   │      LANES = buy/watch/leaders/ran/laggards/laggard (:218)           [DISPLAY]
   └─ scripts/build_stock_board_v2.py → us_standouts_v2.json — SHADOW     [DISPLAY]

CONTEXT SPINE (parallel, zero authority)
   engine/us_context_vector.py → data/us_prophet_rank/candidates/YYYY-MM.parquet
     "Zero authority at birth. Nothing reads this store for scoring" (:10-12)
   └─ scripts/grade_us_prophet_candidates.py --nightly (daily.yml:6246)
        → engine/us_prophet_grades.py → data/us_prophet_rank/grades/YYYY-MM/
        zero-authority by charter — "confer no rank, gate, size, board or plan
        rights on anything" (grade_us_prophet_candidates.py:88)
```

**Live coverage receipt** (`ranking.component_coverage`, 2026-08-13 board): signal 58/69
nonzero, entry 64/69, edge 51/69, runway 66/69, quality 46/69. `stage_counts`: live 28 /
setting_up 31 / ran 8 / basing 1 / blocked 1.

**Stale era literal found in passing (route to PR-1a):** `scripts/build_prophet.py:2185/:2192` still discloses "us_prophet_v1 priority score" while `BOARD_DEFINITION` has been `us_prophet_v2` since 08-10 — a stale disclosure literal on one of the three surfaces a promotion changes.

**Decision-authority compression, confirmed.** The five scored inputs are the cascade
verdict, the entry status (flat — separates admissible from not, orders nothing), the
residual-alpha percentile, `ext_z`, and the coiled/washout read. Everything else on the row
is chips. Two lanes downstream of the artifact then *reuse* the priority number as rank
authority: plan origination (`build_prophet.py:2185`) and the top-setups surface — so a
promotion changes not one surface but three.

## §3 Exact lobe authority table (deliverable 2)

Authority classes: **CANDIDATE** (may nominate onto the board) · **SCORE** (contributes
points) · **RANK** (may reorder) · **GATE** (may block/demote/veto) · **DISPLAY-ONLY**
(on the row/artifact, no effect) · **ABSENT-FROM-BOARD** (produces data the board never
reads). `CV` = column(s) in the zero-authority candidates store
(`engine/us_context_vector.py::build_records`). `69/…` counts = presence on the live
2026-08-13 board's 69 buy rows.

| Lobe | Producer | CV column(s) | Authority today | Granted / denied at |
|---|---|---|---|---|
| Confluence cascade (T1–T4) | `engine/signal_gate.py` → `site/factordata/signal_gate.json` | `eligible, tier_cascade, tier_sub, ticks, fresh_bars, gate_*, htf_s1/s2, near_miss_reason` | **CANDIDATE + SCORE + GATE** | `build_stock_library.py:604`, `:1261`; `us_board_rank.py:537-559`, `:952-962` |
| Entry-timing gauge | `engine/entry_signal.py` | (via `stage`) | **SCORE (flat) + GATE + RANK-group** | `us_board_rank.py:563-565`, `:333-351`, `:942-950`, `:725-779` |
| Residual-alpha edge | build_site alpha → `build_stock_library.py:2674-2682` | `alpha`, `alpha_percentile` | **SCORE (25) + GATE** (featured floor) | `us_board_rank.py:568-634`, `:988-992` |
| Runway / extension | `engine/extension.py` | `ext_z` | **SCORE (10) + GATE** (parabolic veto) | `us_board_rank.py:637-662`, `:984-986` |
| Quality (coiled/washout ctx) | `engine/coiled.py` | — | **SCORE (10)** | `us_board_rank.py:665-674` |
| Washout lifecycle (weekly) | `engine/washout_turn.py` | — | **DISPLAY-ONLY** (`washout_active` 69/69) | not in `SCORE_WEIGHTS`; `build_stock_library.py:60` |
| Basket turn / reversal cohort | `engine/us_basket_turn.py` | — | **DISPLAY-ONLY** | `ZERO_SCORE_AUTHORITY` :449-454; refusal rationale :1564-1590; `authority.may_rank:false`; `config/synapse.yml:3276` |
| Early-turn starter tier | `engine/us_early_turn.py` | — | **ABSENT-FROM-BOARD** (only `prophet_bridge.py:2300` zone band, downstream) | no `us_board_rank` import; literal-duplication fence :1539-1545 |
| Leader pullback / reset | `engine/us_leader_pullback.py` | — | **ABSENT-FROM-BOARD** | its own header: "may_rank/gate/size/escalate = false. Nothing in the pick chain imports this module" |
| Theme lifecycle / in-favour | `scripts/build_baskets.py` → `data/baskets/{latest,membership}.json` | `theme_*` (9 cols) | **DISPLAY-ONLY** (`theme` chips 8/69) | `ZERO_SCORE_AUTHORITY` :442 (`theme`); :166, :1516, :1827-1835 |
| Foresight desk | `engine/foresight_score.py` et al. | `foresight_stage` | **ABSENT-FROM-BOARD** (CV only) | `us_context_vector.py:10-12` |
| Intelligence Hub | `engine/intel_hub.py` | — | **ABSENT-FROM-BOARD** — dependency runs the OTHER way (`intel_hub.py:845-850` reads `signal_gate.json`) | no import either direction |
| Sector turn | `engine/us_sector_rotation.py` | — | **DISPLAY-ONLY** (`sector_pulse` 35/69, `sector_rank` 69/69) | `ZERO_SCORE_AUTHORITY` :433 (`sector_turn`) |
| Relay position | `us_context_vector.py:422` (mirrors `prophet_doors._relay`) | `relay_count_3d, relay_position, relay_members_covered, relay_basket_id` | **ABSENT-FROM-BOARD** | CV zero-authority |
| Narrative | `engine/narrative_rotation.py` | — | **ABSENT-FROM-BOARD** | `ZERO_SCORE_AUTHORITY` :434 (`narrative`) |
| Smart money / 13F | `_smart_money` (`build_stock_library.py:2172-2174`) | — | **DISPLAY-ONLY** (`smartmoney_chip` 14/69) | `ZERO_SCORE_AUTHORITY` :438 |
| Insider | `engine/insider_intel.py` | `insider__*` (Context Snapshot dim) | **DISPLAY-ONLY** (`insider_net_mn/_buyers/_bps` 6/69) | `ZERO_SCORE_AUTHORITY` :439 |
| Congress | `engine/congress_entry.py` | — | **ABSENT-FROM-BOARD** (politics-channel frozenset only, `build_stock_library.py:5073-5085`) | no board read |
| SUE / earnings surprise | `sue_freshness_days()` (`build_stock_library.py:404`, `:2612`) | — | **DISPLAY-ONLY** (`sue_fresh_days` 14/69, `sue_z` 4/69) | `ZERO_SCORE_AUTHORITY` :440 |
| Analyst revisions | `engine/analyst_revisions.py` (`build_stock_library.py:2998-3002`) | — | **ABSENT-FROM-BOARD as a leg** — reaches only `composite` = `conviction_composite` = zero authority | :431 |
| 8-K / EDGAR events | EDGAR pipeline → `data/edgar/material_8k_events.parquet` | `eightk_recent_days` | **ABSENT-FROM-BOARD** (CV only) | `us_context_vector.py:586-618` |
| Government contracts | `scripts/build_government_revenue.py` | — | **ABSENT-FROM-BOARD** | channel literal only |
| Activist / 13D | `engine/activist.py` | — | **ABSENT-FROM-BOARD** | no board field |
| BioCatalyst | `scripts/build_biocatalyst.py` | — | **ABSENT-FROM-BOARD** | zero refs in board/builder |
| Options flow | `engine/options_flow.py` | `options__*` dims | **ABSENT-FROM-BOARD** | — |
| GEX / dealer positioning | `engine/gex_confirm.py`, `engine/gex_engine.py` | `options__gex` | **DISPLAY-ONLY** (`gex_confirm` 33/69) | `ZERO_SCORE_AUTHORITY` :441 (`options_gex`); `build_stock_library.py:236` "never in the score" |
| Short interest | FINRA backfill | `short_int__*` dims | **ABSENT-FROM-BOARD** | — |
| Transmission / macro chains | `engine/transmission_chains.py` | — | **ABSENT-FROM-BOARD** (separate lean gate `build_stock_library.py:3232-3233`) | — |
| Regime | `data/regime/latest.json` | `regime_*` (5 cols) | **ABSENT-FROM-BOARD-ROW** (artifact-level `gate_go` only) | CV zero-authority |
| Dispersion / factor state | `engine/dispersion.py` | `regime_dispersion_state` | **DISPLAY-ONLY** (artifact top-level; `factor_z` 69/69 on rows) | factor lobes via `quality_factor` :435 + `low_vol` :436; the dispersion STATE itself is in no constant — display-tier by absence of any reader |
| Liquidity / market cap | scan tier `engine/us_scan_universe.py` | `mdv20_usd`, `turnover_pctile_20d/60d` | **ABSENT-FROM-BOARD** for curated rows (US passes no `featured_extra`; HK does) | `us_board_rank.py:1042` (`featured_extra`, also :1059/:1117) |
| Blow-off / terminal risk | `engine/roc_blowoff.py` | — | **DISPLAY-ONLY** (`blowoff` 69/69; byte-identity pinned) | `ZERO_SCORE_AUTHORITY` :443-447 |
| Risk sizing | builder | — | **DISPLAY-ONLY** (69/69) | :437 |
| Conviction composite / setup | `engine/stock_score.py`, `engine/setups.py`, `engine/name_score.py` | — | **DISPLAY on board + GATE/tie-RANK on plan intake** (69/69) | board display: `conviction_composite` :431, `setup` :432; `name_score` overwrite `build_stock_library.py:4274-4318`; plan gate/rank/refusal `prophet_bridge.py:22-24`, `:32`, `:413` |
| Candidate-pool lanes | `engine/us_candidate_lanes.py` | `pool_*` (9 cols) | **DISPLAY-ONLY** | `us_candidate_lanes.py:22`, `:818`; `TestNoAuthorityLeak` |
| Filing forensics | `scripts/build_fundamental_forensics.py` | `forensics__*` scalars (bodies dropped, `STAMP_FORBIDDEN_COLUMNS:893-896`) | **ABSENT-FROM-BOARD** | `us_context_vector.py:957-973` |

### §3.1 Doctrine enforcement sites (what a promotion must formally amend)

- **Code:** `us_board_rank.py:48-51` ("context chips only"), `:430-455`
  (`ZERO_SCORE_AUTHORITY`, 14 entries), `:11-20` (the measured basis), `:1564-1590` — the
  **four-ruling refusal** that is the canonical shape any authority change must clear:
  (a) `sum(SCORE_WEIGHTS)==100` pinned twice in tests; (b) membership of the zero list;
  (c) the measured replacement of CN's leg by `edge`; (d) the artifact's own
  `authority.may_rank:false` + `config/synapse.yml` `may_rank:false, weights:none`.
  Closing sentence: "Promoting it to points is an orchestrator ruling on the scale
  question plus a synapse amendment — not a constant edit."
- **Artifacts:** `ranking.zero_score_authority` (:1427) and per-row
  `prophet.zero_score_authority` (:1099) both publish the 14 names nightly.
- **Registry:** `config/synapse.yml:2843-2877` (us_standouts: tier display, weights none,
  scored_path_surfaces [board_ordering, top_setups]), `:3262-3286` (us_basket_turn:
  may_rank false). The board consumes NO Neural Web graded states (zero synapse reads in
  `us_board_rank.py`).
- **Tests that pin the doctrine** (break on any lobe gaining score/rank):
  `tests/test_us_board_rank.py:89` weights-sum-100; `:126` zero-authority membership;
  `:131` no-forecast-claim copy; `:172/:216/:227/:234` entry-leg flatness family; `:1124`
  blocked-never-outranks-live; `:1153/:1179/:1187` ceiling + points reconstruction;
  `:1317` ranking block must publish the scoreless list; `:1392-1445` +
  `TestRunwayCoverageContract` coverage recomputation; `tests/test_roc_blowoff.py`
  byte-identity with/without `blowoff`; `tests/test_us_basket_turn.py:733-762` authority
  block + import fence; `tests/test_us_candidate_lanes.py::TestStoreSchema` +
  `TestNoAuthorityLeak`; `tests/test_us_context_vector_payload_containment.py`;
  `tests/test_us_prophet_grades.py:306` anti-fork; `tests/test_us_board_priority_ui.py`
  rendered stage contract. Plus `scripts/check_board_contradictions.py` invariant (d):
  declared sort order (stage monotone, score non-rising within stage, blocked never above
  live) — a challenger promotion must update this checker in the same PR or go red.

### §3.2 `name_score` adjudication input (roadmap §4.4, sharpened)

`engine/name_score.py` is a PARALLEL SCORER, not a `us_board_rank.py` input and not dead:
zero references in `us_board_rank.py`; output lands at `rec["conviction"]["potential"]`
(`build_stock_library.py:3724-3731`) and the nightly grader
(`data/name_score/us_calls.parquet`). It is already load-bearing in a side path:
`potential_score`/band overwrite `rec["conviction"]["score"]`/`["band"]`
(`build_stock_library.py:4274-4318`), and those published fields GATE and fallback
tie-RANK the plan-intake funnel (`prophet_bridge.py:22-24`, `:32`, `:413`; executable
live gate `:1147-1152`, `:1201-1206`, fallback order `:755-785`). Two facts matter for
this program: (a) it already
grants the US "event edge" (insider / SUE / revisions z) a ±35%/−30% multiplicative band
(`_EDGE_BLEND["US"] = (0.20, 0.70, 1.35)`, `name_score.py:117`) — so the estate is NOT
uniformly zero-authority for these lobes; authority varies by surface, and the stock-page
score already embeds what the board forbids; (b) it is G2 in the arena, so the rival
composite finally races the champion on one ruler.

### §3.3 Existing seams a shadow challenger uses (no doctrine change required)

1. `score_rows()` is already parameterized (`alpha_of=`, `featured_extra=`,
   `bottom_watch_stage=`, `reversal_cohort=` — us_board_rank.py:1041-1044); HK exercises
   two of them. A shadow scorer calls the SAME pass with a different selection axis
   without touching the live path.
2. The **R2 reversal-cohort pattern** (:1555-1714 + builder :5164-5173) is the
   house-canonical "new lobe: loaded in builder, passed in, stamped scoreless, coverage
   receipt published nightly" shape — the §13 accrual columns follow it.
3. Shadow-artifact precedents, all live at HEAD: `data/prophet/legacy_shadow/YYYY-MM/`
   (US Prophet shadow via `build_prophet.py`, idempotent day parts);
   `site/factordata/us_standouts_v2.json` (whole-board shadow, "never touches the live
   board"); `snapshots_v2.jsonl` sibling-file isolation (registry-pinned: "v2 rows never
   touch main retro_grades.parquet", `config/synapse.yml:665-704`). PR-3's shadow lane
   composes these three patterns.
4. The `priority_score_scorecard` (defined in `engine/prophet_miss_audit.py:1507`,
   reading FROM `engine/us_prophet_grades.py` — the dependency runs miss-audit→grades)
   is the existing forward-measurement surface (rank-IC, decile lift, thin-cohort refusals per
   `universe_tier` × `signal_class`) — challenger scores graded by the same ruler as the
   champion, no new grader.

### §3.4 Producer → artifact wiring appendix (receipts for §3's rows)

Compact census (producer entry point → committed artifact → writer), verified 2026-08-14:
washout `engine/washout_turn.py:827→site/stockdata/washout_turn.json` (hook
`build_baskets.py:732`); early-turn `us_early_turn.py:1076→prophet_bridge.py:4405` →
plan JSONs (`build_prophet.py:1801`); leader-pullback `us_leader_pullback.py:346` →
coverage writer `:394→site/anticipationdata/us_leader_pullback.json`; residual alpha
`residual_alpha.py:153→site/factordata/alpha.json` (`build_site.py:3746/:3754`);
extension `extension.py:223` → per-ticker stockdata (`build_stock_library.py:3475`);
forensics `build_fundamental_forensics.py:613` → R2-private `state.json.gz` +
`public_summary.json`; theme lifecycle `neuralweb/thematic_state.py:448` →
`data/neuralweb/theme_state.json` + State-of-Themes page + `theme_lanes.json`; foresight
`foresight_cascade.py:289→site/basketdata/foresight_cascade.json`; hub
`intel_hub.py:901→site/intel_hub/hub.json`; sector turn `subsector_rotation.py:175` →
`site/marketdata/subsector_turns.json`; basket turn
`us_basket_turn.py:921→site/basketdata/us_basket_turn.json`; relay
`us_context_vector.py:422` → candidates parquet (also Door-T recorded features);
narrative `narrative_flare.py:1094→site/narrativedata/flares.json`; smart money
`smart_money.py:792→site/smartmoney.json`; insider `insider_power.py:503` →
`site/data/<T>.insider.json` + `insider_intel.py:427` → smartmoney_desk; congress
`congress_members.py:137` → HTML only (no JSON artifact); SUE `sue.py:55` →
`equity_factors.py:104` → `site/factordata/factors.json` column; revisions
`analyst_revisions.py:104` → leader-radar artifact; 8-K magnitude
`eightk_magnitude.py:170→site/basketdata/eightk_magnitude.json` (raw:
`data/edgar/material_8k_events.parquet`); gov contracts
`government_revenue/metrics.py:1876` → `site/government-revenue-data/*`; activist/13D
`activist.py:89` + `special_situations.py:879` → `site/allocationdata/special_situations.json`;
biocatalyst `biocatalyst/packet_producer.py:544` → **R2-private object store** (site page
is a data-free shell — no committed data); options flow
`options_flow.py:310→site/flow/*`; GEX `gex_model.py:719` + `gex_state.py:538` →
`site/gex/*` + `data/gex/latest.json`; short interest `equity_factors.py:112` →
factors.json column + `crowding.py:83` fragility chip; transmission
`rate_inflation_transmission.py:578→data/transmission/latest.json` + chain state machine
`transmission_chains.py:1431→chain_state.json`; regime `regime.py:270→data/regime/latest.json`;
dispersion `dispersion.py:162→data/dispersion/regime.json`; liquidity
`liquidity_chip.py:78` → per-ticker stockdata.

## §4 PIT history / coverage matrix per lobe (deliverable 3)

Census run 2026-08-14 from the git tree (`git show HEAD:` / materialized parquet), with
currency-critical stores cross-checked against `origin/main` fetched 2026-08-14. Aug
coverage %s are over the 7,759 rows of `candidates/2026-08.parquet`.

### §4.0 HEADLINE — the keystone store is NOT ACCRUING

`data/us_prophet_rank/candidates/` holds **four stamped trading days total** — 2026-07-31
(2,933 rows × 167 cols) and 2026-08-05/06/07 (7,759 rows × 180 cols) — and **nothing
since 08-07, confirmed on `origin/main`**, while the board's own `snapshots.jsonl`
advanced through 08-13. The nightly is running; the context-vector append specifically
has not stamped for ~4 sessions beyond the known 08-08..08-11 outage window (Prophet US
availability program's root-caused incident). The writer is fail-soft by design (logs and
returns 0), which is exactly the "loud failure gets fixed, silent sibling stays dark"
shape. **Diagnosing and restoring this accrual is §13 item 0 and the single most urgent
action in the whole program** — every architecture decision downstream assumes this store
exists and grows.

### §4.1 One-screen matrix

| Lobe | Data home | History start (real evidence) | PIT field / basis | Verdict |
|---|---|---|---|---|
| Theme (wired) | `data/baskets/{membership,latest}.json`, `membership_history.parquet` | membership_history: **1 snapshot day** (2026-08-13) | `added`/`removed` dates in membership | **THIN** — wired (`theme_*`) but the PIT trail of theme STATE is days old; the CV store is its only nightly archive |
| Theme (research stores) | `data/themes*`, `theme_graph` | theme_graph birth_date 0/2,707 populated | inconsistent | DISPLAY-ONLY, unwired |
| Sector / basket turn | `data/us_basket_turn`, `sector_cycles`, `us_sector_rotation` | `sector_cycles/backfill.parquet` **2010-12-31→2026-06-30** | `as_of`/`date` mixed | DISPLAY-ONLY; deep backfill exists but unwired to CV |
| Narrative | `data/narrative*` | 2026-04 → | `date`/`fetch_date` | ABSENT from CV; raw ≤4 months |
| Smart money / 13F | `data/smart_money` (55 funds) + `data/quiver/sec13f*` (second, parallel feed) | period_end **2022-09-30→** | `filing_date`/`available_date` (correct 45d-lag pair) | **RICH raw, ABSENT from CV** — zero columns anywhere |
| Insider | `data/sec_insider/panel` (wired) | 2006q1 → **2026q1 ONLY** | `filing_date` | Wired but **DEAD ON ARRIVAL: `insider__absent` = 100% of Aug rows** — the panel collector stopped at Q1, so trailing-90d lookups from August find nothing |
| Congress | `data/quiver/congress*.parquet` | TransactionDate **2012-02-27→08-07**, ReportDate 2014→08-12 (correct PIT pair) | `ReportDate` vs `TransactionDate` | **RICH raw, ABSENT** — zero consumers |
| SUE / revisions | `data/edgar/sue_phase0.json` (study), `data/revisions` (2026-06-16→) | revisions ≈ 2 months | study note `filed<=asof` | ABSENT as CV column. ⚠ `sue_phase0.json` records a shallow-panel "WIRE — survives BH-FDR" verdict that the DEEP survivorship-clean panel later reversed (IC 0.0006, t_HAC 0.06 — hub V2 §4.3); the file must never be cited as a live GO |
| 8-K / EDGAR | `data/edgar` | filing-time events, per-filing store | `filing_date` | Wired (`eightk_recent_days`) — 8.6% Aug (event-sparse by nature) |
| Options / GEX | `data/polygon_gex`, `options_*` | chains 2026-06-15→, ~2-3×/wk | `asof`/session | Wired (`options__*`) — **94.4% absent** on Aug rows; era break 2026-08-07 |
| Short interest | `data/finra/short_interest.parquet` | history file: **2 settlements** (06-30, 07-31) | **`snapshot_not_pit` ALWAYS** — `context_api._short_int_dim` ignores the query date and returns the current snapshot; the history file is not read | Wired but **PIT-BROKEN by construction**; 81% absent |
| Foresight | `data/foresight` | ~June → | — | Wired (`foresight_stage`) — 6.8%→2.6% and shrinking; all stages text/fingerprint variants |
| Intelligence Hub | `data/intel_hub`, `data/hub` | snapshot-only | — | DISPLAY-ONLY, unwired to CV (→ §13.3) |
| Transmission | `data/transmission` | chains young | — | DISPLAY-ONLY, unwired |
| Washout / early-turn / tops | `data/washout_turn`, `top_anatomy` | top_anatomy **2022-07-18→2026-07-02** | `date`/session | Display; deep episode library exists for PIT reconstruction |
| Forensics / quality | `data/fundamental_forensics` (public summary; private state R2-only) | snapshot-only; **no historical replay** (refuses dates before its `generated_at`) | `normalized_projection_snapshot_not_pit` | Wired (`forensics__*`) — 18.6% Aug; backtestable never, accrues forward only |
| Capital structure | `data/capital_structure/discovery.parquet` | filing_date **2023-06-23→** | `filing_date` | Unwired; PIT-safe raw |
| Regime / macro | `data/regime`, `regime_history.parquet` | **1927-12-30→** | `as_of` (`recomputed_history` + `pit_live`) | Wired — RICH, 100% present (row-constant per night) |
| Dispersion / factor | `data/factordata` | **panel not in git at all** (host/R2-only) | theoretical | Wired column but **`factor__absent` = 100%** — dead even in production commits |
| Attention | `data/attention` — **not in git** (host/R2-only) | live on host only | `as_of` | Wired — 15.3% Aug on host; **zero on any clone/CI** |
| Personality | `data/research/personality_pit_labels.parquet` | **1962-01-02→2026-07-06**, 2.1M rows | `date` (pit_labels) | RICH depth, 22.1% Aug coverage (223-name universe) |
| Archetype | `data/archetypes/history.parquet` | **2009-08-28→**, 1,465 tickers | `asof_date` (pit_labels) | RICH depth, 18.9% Aug |
| Spine (NW) | `data/neuralweb/spine_index.parquet` | **1962-11-29→2026-08-14** | `as_of` | RICH depth, 23.3% present |
| BioCatalyst | `data/biocatalyst` | — | — | **ABSENT — all 35 tracked files are test fixtures; zero production data** |
| Prices (deep) | `data/massive_stock_day` (20,476 names, 2021-07→), `data/baskets/ohlcv` (2014→) | 2014/2021 → | session bars | RICH — the PIT-reconstruction substrate for F1/F2 experts |
| Graded outcomes | `data/us_board_ledger/retro_grades.parquet` | 2026-06-15→07-31; H∈{5,10,21} only, no 60d+ graded yet; two era boundaries + one disclosed null era | `as_of` + `price_basis` | The only outcome frame that exists today (4,077 rows) |

### §4.2 PIT integrity flags (binding on the arena)

1. **CV accrual stopped 08-07** (§4.0) — P0.
2. **`short_int__*` never PIT** — any historical use of the dimension is leakage by
   construction until `_short_int_dim` reads the history file; arena must exclude it from
   backtests entirely (forward-accrual only).
3. **`insider__*` starved upstream** (panel ends 2026q1) — the literal first-named lobe
   of the CEO ruling currently cannot be evaluated AT ALL on fresh data; collector repair
   is a §13 item and prerequisite to any insider claim.
4. **`factor`/`attention` host-only** — any CI-run or clone-run study silently sees zero
   coverage; arena reports must print per-dimension coverage so this cannot masquerade as
   a null result (evidence-guard-keyed-on-coverage, not on class).
5. **`sector__absent=False` over-credits** — the flag is always present while 3 of its
   sub-fields are 100% null; consumers must key on field-level non-null, never the flag.
6. **`data/edgar/statements.parquet` carries no filing timestamp** — latest-known
   restated financials; unusable for PIT joins as-is.
7. **Board-ledger era boundaries** (price_basis 08-06; options restamp 08-07; disclosed
   null era 08-03..08-06; plus the known 08-08..08-11 outage hole) — §7 era hygiene
   enumerates the handling; the 08-07→08-12 snapshot hole is the availability program's
   documented incident, not a new discovery.
8. **`latest.json`-only stores** (macro_context, top_maturation, dispersion/regime.json)
   have no history trail — reconstruction impossible; forward accrual only.
9. **The quiver bundle** (Congress, second 13F, insiders with `fileDate` populated only
   06-01→08-14, lobbying, gov contracts, patents) is rich, PIT-paired, and entirely
   unconsumed — the single largest unwired evidence mass in the estate.

## §5 Lineage / redundancy map (deliverable 4)

### §5.1 The evidence-family registry (v1, frozen for the first arena generation)

Every feature the fusion model ever sees belongs to **exactly one family** — enforced by
a uniqueness test over the registry, not by prose. A dual-role COLUMN gets a single home
plus, where the second hypothesis is wanted, an explicitly derived orthogonalized second
term registered separately (never a second membership): `ext_z` lives in F2 ONLY (F8's
crowding read of extension enters, if ever, as an F2-orthogonalized derivative); relay
lives in F3 ONLY (its price-derivation is provenance, not membership); theme heat lives
in F3 ONLY (the S-C crowding hypothesis on it is a §10.7 registered interaction, not an
F8 membership). Families are the unit of anti-double-count budgeting (§10.6) **at every
rung C1–C5**. PR-1 commits this as a machine-readable registry
(`research/prophet_fusion/families.yml`) carrying, per member: `family`,
`pit_status ∈ {pit, forward_only, snapshot_not_pit}` (the harness HARD-REFUSES
non-`pit` members in any backtest frame — short interest and forensics are
`snapshot_not_pit` today, §4.2), `coverage_floor` (registered default 0.50 non-absent on
the evaluation frame's board-adjacent rows, per-family overrides listed in the registry;
a family below floor abstains and may not be *reported on*), and
`max_staleness_sessions` (per §7 O6's abstention semantics). The table below is the
prose view; the YAML is the law.

| Family | Members (producer-typed) | Known internal redundancy / shared upstream |
|---|---|---|
| **F1 TECHNICAL-CONFLUENCE** | signal_gate cascade verdict (tier/ticks/htf/provisional), entry_signal status, cycle ladder state/label, washout_turn weekly lifecycle, coiled/washout_ctx, early-turn states, leader-pullback events, LER detector families (G0/C1–C5, via `entry_event.v1`), MWR | One MACD/StochRSI machinery family-wide; entry_signal and the cycle ladder read the same underlying state (`name_score._trigger` reads both); LER's C-detectors deliberately overlap terminal dots (its Expert Preservation ruling keeps them distinct anyway) |
| **F2 MOMENTUM-EXTENSION** | residual alpha, `total_return_z` (63d, leaders), composite momentum leg, RS measures, `off_high`, `ext_z` (single home — F8 sees only an F2-orthogonalized derivative, if ever) | **The canonical documented double-count**: `corr(alpha, composite.legs.momentum) = 0.984` (us_board_rank.py:1475 comment) — the momentum leg IS residual alpha under a new name; `total_return` vs alpha corr +0.37 |
| **F3 THEME-STRUCTURE** | basket membership, theme heat rank / reco / bull_days / clean_entry, sector turn, `us_basket_turn` states, relay position/count (single home), foresight stages, State of Themes, narrative rotation, Hub theme legs | ONE producer (`data/baskets/*`) feeds membership, chips, basket-turn cohorts AND relay windows; foresight joins baskets via one crosswalk and also feeds four NW theme organs; Hub's theme leg reads the same artifacts — agreement among these is one fact, not four |
| **F4 CATALYST-EVENT** | earnings proximity/blackout, post-earnings reaction, SUE, analyst revisions, 8-K recency/magnitude, government contracts, activist/13D, BioCatalyst, special situations | revisions already flow into `composite` (→ conviction display) and name_score's edge blend; SUE feeds name_score + board chips; earnings fields all derive from one `earnings_blackout.assess` pass |
| **F5 FLOW-POSITIONING** | options flow, GEX/dealer (polygon_gex → gex_confirm, `options__gex`), IV/skew/`opt_*` stamps, insider (one `sec_insider` panel → insider_intel chips + `insider__` dim + name_score edge blend + hub clusters), Congress, 13F smart money, FINRA short interest, turnover percentile | Options internals heavily cross-correlated (documented: charm/DOI kills cite trail-RV IC 0.5–0.6 confounds); the single insider panel reaches ≥3 surfaces — chips agreeing with the dim is self-agreement |
| **F6 MACRO-REGIME** | regime quad, vol regime, dispersion state, gate_go, transmission chain states, rates/liquidity/inflation states, factor/dispersion market state | **Row-constant per night** (one value for every name) — cross-sectionally degenerate BY CONSTRUCTION: lawful only as router/interaction axes (§10.2), never as cross-sectional rankers |
| **F7 QUALITY-FUNDAMENTAL** | forensics scalars, capital structure, fundamental quality receipts, PSQ stage, spine records | forensics scalar fields are the PIT-safe projection (paid bodies excluded at the store boundary); archetype/personality columns route through #5583's fingerprint interfaces, not raw |
| **F8 ATTENTION-CROWDING** | attention dim (log_views), news burst, crowding flags, turnover tail, blowoff risk | the S-C theme-heat-as-crowding read and any extension-as-crowding read enter ONLY as §10.7 registered interactions / F2-orthogonalized derivatives — never as second memberships; blowoff shares price-derivation with F2 (correlation reported in the §5.3 blocks) |

### §5.2 Composite-decomposition law (lineage edges that forbid votes)

- **Intelligence Hub**: `opportunity_score` / `composite_conviction` are NEVER ingested as
  features. Typed decomposed inputs only: leading-vs-lagging gap, lifecycle stage,
  edge-remaining, isolated/pre-consensus flag, per-feeder directions/strengths,
  signal-governor trust, contradiction intensity, source provenance. Rationale: the hub's
  own feeders (news / alt / radar / buy-board / policy) already overlap F1–F4 — hub
  agreement with Prophet is substantially self-agreement (its buy-board leg literally
  reads the board's population).
- **`conviction` / `composite_z` / `setup`**: measured anti-predictive as an ordering
  (US_BOARD_MEASUREMENT §1) — enter only decomposed to their legs (momentum leg → F2 with
  the 0.984 dedup; revisions leg → F4; vol leg → F8), never as the blended scalar.
- **`name_score`**: G2 baseline in the arena; its components (trigger/fuel/survive/
  tailwind/confidence/edge_mult) map to F1/F2/F8/F3/F6/F4+F5 respectively — as a FEATURE
  it is a composite and is decomposed, not ingested.
- **NW Context Snapshot dims**: enter as their typed fields (`<dim>__<field>`), family-
  routed per the table; `spine__records` and options non-scalars stay research-side.

### §5.3 Redundancy measurement plan (PR-2, pre-registered here)

Per family and cross-family on the candidates store + retro_grades frames: Spearman
correlation blocks; conditional mutual information estimates (feature ; outcome | Prophet
score) for the incremental question; cross-fitted residualization (feature vs
champion-score residuals); ablation battery (per-family leave-one-out ΔP@5 / Δtop-5
excess). Published as a committed research artifact so "N families agree" claims can be
audited against measured family overlap. Known-edge priors written above are asserted
from receipts today and re-measured then.

## §6 Current score pathology (deliverable 5)

Measured 2026-08-14 from the committed ledgers (scratch analysis only; nothing tracked was
modified). Population: `snapshots.jsonl` buy lanes carrying a `prophet` block — exactly 3
dates (08-07 v1 n=78; 08-12, 08-13 v2 n=70/71; N=219 scored rows), plus
`retro_grades.parquet` (4,077 rows, as_of 2026-06-15→07-31) for outcome joins. Every
number below carries its N; nothing here is a verdict.

### §6.1 The hard blocker: the live score has NEVER been graded (N=0)

Prophet-scored board dates = {2026-08-07, 08-12, 08-13}. Graded dates in
`retro_grades.parquet` end 2026-07-31. Intersection: **empty**. `data/us_prophet_rank/grades/`
does not exist at HEAD and the miss-audit scorecard reads `available: false, n_rows: 0` —
consistent with youth, not breakage: candidate stamps began 07-31/08-05 and the first H=10
maturation lands ~2026-08-24 (v1) / ~08-27 (v2), H=21 ~09-11. Consequence: **every
"does the score predict" read today is either the pre-prophet published order or a
labelled counterfactual replay** — and the arena's first honest champion read has a
calendar date, not an engineering date. (PR-1 verifies the first grade maturation
actually lands — §13.)

### §6.2 Compression and tie structure

Top-1 − median = 24–28.5 pts, but **top-1 − top-10 = 7.3–12.5 pts**: the top ten live
inside 8–13% of the scale. Median adjacent gap across the whole board 0.5–0.6 pts; in the
top 10, 4–6 of 9 adjacent gaps are <1 pt. The smallest non-degenerate leg increments are
2.5–4.0 pts, so **every sub-point ordering decision is made by the `edge` percentile
arithmetic alone**.

### §6.3 Effective ordering authority: two legs, not five

Exact variance decomposition of the 100-pt sum (points space, per day): signal 38–42%,
entry 25–28%, edge 20–25%, runway 6–9%, quality 4–6%. But the sharper cuts collapse it:

- **Entry is an admission switch, not a ranker**: 82–84% of v2 rows sit at the flat 1.0
  (ANTICIPATION v1, by design). Dropping the entire 25-pt entry leg leaves the top-10
  **identical** (Jaccard 1.00) on both v2 dates. Same for runway (60% of rows at 1.0;
  historically **dead 0/n on 8 of 20 board dates** during the calendar-mixing defect).
- **Dropping edge destroys the top-10** (Jaccard 0.25/0.33, mean |Δrank| ~12).
- Within the flat-entry cohort, ordering variance is edge ~49–51% + signal ~35–42%.
- Discreteness: (`signal`,`entry`,`quality`) realize only 24–25 distinct triples over
  70–71 rows; 75–77% of rows share a cell with ≥3 others and are ordered **inside the
  cell by edge alone**. `signal` realizes 5 values (T3 unobserved; `provisional` has
  fired on 0/219 rows ever); `quality` realizes 4 (126/219 at 0.4).

**The compression claim is confirmed in a stronger form than the ruling stated: nominal
authority is five legs; realized ordering authority is `edge` (continuous) + `signal`
(5-valued), with stage buckets doing the large-scale moves.**

### §6.4 Contextual estate: zero direct drive, and thinner on-board than the doctrine implies

No zero-authority scalar enters the score (confirmed — `score_rows` reads none of the 14
listed families; bystander correlations only, e.g. `conviction.composite_z` ρ 0.31 via
shared upstream state). More surprising: on the 08-07 board cross-section of the
candidates store (154 rows), `insider__absent` = **154/154**, `factor__absent` =
**154/154**, `options__absent` = 117/154, theme payload present only 41/154 — several
"shadow estate" dimensions are largely dark exactly where the board is. The estate's
*coverage on admitted names* is itself a §13 repair item; a fusion program that assumed
the store's 150 columns are live on board rows would be training on absence.

### §6.5 Churn is admission-churn; rank moves are bucket flips

Prophet-era transitions (n=2, read accordingly): board Jaccard 0.138 (08-07→08-12) and
0.270 (08-12→08-13); top-10 carryover 2–3/10; 20 of 25 distinct top-10 names appeared
exactly once; pre-prophet consecutive boards ran Jaccard 0.35–0.43, so ~60%-per-night
pool turnover predates the score. Attribution of the biggest rank moves: `HEI` +53 ranks
= exactly the −25 entry leg (live→ran); `TKO` −50 ranks on a score change of **+1.7 pts**
(stage flip); `ARR` −49 on +0.1; `TREX` −40 while its score FELL 2.5 — stage
reclassification, not evidence. `VAL`/`WBD` −36/−30 were the 08-08 entry-map re-valuation
itself (+16.25 pts by ruling, not by tape).

### §6.6 Does it predict? (counterfactual replays; loud-N)

- Replay of the LIVE v2 scorer over 17 graded historical boards (validated byte-exact on
  both v2 dates; 08-07 diverges by up to 16.3 pts = the v1→v2 entry re-valuation — two
  eras are NOT one score scale): H=5 rank-1–3 hit 0.600 (N=50) vs base 0.481; replay
  rank-IC median −0.018; **H=10 sign flips against the score** (rank-1–3 mean −0.85pp,
  N=49-ish cells, 7 dates); H=21 cells all N<100.
- The PUBLISHED pre-prophet order (what users saw): H=5 P@1 **0.333** (24 dates), top-3
  mean −0.59pp while ranks 26+ ran +0.88pp — **the published top was worse than its own
  tail at both short horizons**, corroborating US_BOARD_MEASUREMENT §1 on a wider frame.
- **The single most reportable shadow fact:** `alpha` — the one input the 25-pt edge leg
  reads — has NEGATIVE within-day rank correlation with forward excess on the graded
  buy-lane population at every horizon (−0.053 H=5 N=1,356; −0.084 H=10 N=767; −0.158
  H=21 N=194; positive on only 10/24, 5/17, 1/7 days). This is the pre-prophet
  population and thin at H=21 — not a verdict — but the champion's only continuous
  ranker pointing the wrong way on the only graded frame we own is exactly the kind of
  fact the arena exists to adjudicate, and G1 (pure-alpha) racing G0 will answer it
  cleanly.
- Ore signatures logged, not claimed (thin cells, era-contaminated): `opt_iv30` ρ +0.37/
  +0.56 (H=5/10, N=207/126, 7–13 days, spans the 08-07 options era break);
  `gex_confirm_verdict` 2.8pp group spread (N=230); `smartmoney_add` 2.2pp (N=590);
  `off_high` −0.19/−0.23 (H=10/21).

### §6.7 Fragility inventory

1. **Rank 1 is not the max score** — sort is (stage, −score): 08-12 max score 94.5 sat at
   rank 22; 08-13 max 90.7 at rank 29; the share of cross-bucket pairs where a
   lower-bucket row outscores a live row reached **56.5%** on 08-13. The board publishes
   an order a majority of its own cross-bucket score comparisons contradict — disclosed
   in the artifact (`score_scope_note`), but a real legibility pathology the §10.5
   explanation contract must answer better than a footnote.
2. **The edge zero-boundary floats nightly** (pool-relative percentile): the alpha level
   earning 0 moved −0.32 → −0.40 → −0.63 across three boards; identical alpha readings
   moved up to 0.82 pts on pool composition alone. Cross-night score comparability is
   weaker than the single number implies.
3. **47% of every board pays the ticks==2 freshness penalty** (102/219 rows), inside the
   known non-monotone freshness shape (1.00/1.00/0.85/1.00 at ticks 0/1/2/3+).
4. **Featured is a veto-filtered prefix, not a top-K**: worst-ranked featured row sat at
   rank 16 / 22 / 30 on the three boards.
5. **Store/ledger disagreement**: on 08-07 the candidates store's buy lane and the
   snapshot's buy lane disagree on 5 of ~78 names — the two "memories of the board" are
   not byte-identical; the arena joins must key on the snapshot (what shipped) and
   disclose the store delta.

### §6.8 What the pathology implies for the architecture (why §10 is shaped as it is)

The measured failure modes map one-to-one onto the design: sub-point tie-breaking by one
noisy percentile → multiple continuous heads + confidence (§10.3); bucket flips moving
names ±50 ranks on ±0 score → entry/actionability modeled separately from selection
(Layer D keeps stages, but the WHAT-score stops pretending to be the WHEN-score);
pool-relative floating zero → cross-sectional features normalized against FROZEN
reference distributions in the arena, with the pool-relative form kept only where the
product wants it; dark shadow dims on board rows → §13 coverage repair before any
training claim; never-graded champion → §8.4's honest baseline framing and the
calendar-gated first read.

---

## §7 Frozen outcome definitions (deliverable 7)

All heads grade against the existing rulers — no new outcome machinery is invented, because
`engine/us_prophet_grades.py` + `engine/grading.forward_metrics` already produce policy-free,
next-bar-fill, fixed-horizon marks and are pinned mark-for-mark against `grade_us_board`.

**O1 — Selection excess.** `excess_spy` at H ∈ {10, 21, 42, 63} sessions, next-session-close
fill, dividend-adjusted, from `data/us_prophet_rank/grades/`. Headline horizon per signal
class follows the chartered-horizon prereg (basing H=63, momentum H=10, other H=10 —
`data/us_prophet_rank/README.md`), which this program inherits unchanged. Every head is
*reported* at every horizon; the headline is fixed per class in advance
(`DNR:KILL-OFFHORIZON-VERDICTS` compliance).

**O2 — Directional hit.** `P(excess_spy > 0)` at the same horizons. Secondary to O1 — the
arena never optimizes hit rate alone (the measured edge is tail-concentrated: top-1 mean
excess +8.3% @21d at P@1 ≈ 0.44, US_BOARD_MEASUREMENT §3).

**O3 — Asymmetry tails.** From the grades store's `fwd_mfe` / `fwd_mdd` plus the excess
distribution: `P(excess > +10pp)` and `P(excess < −10pp)` at H=21/63;
`E[excess | excess > 0]` and `E[excess | excess < 0]`; MFE and MDD medians. The +10pp
threshold is frozen now, before any challenger sees data, as roughly the top-decile
magnitude of the measured H=21 excess distribution; the loser threshold mirrors the
established loser convention `excess < −3pp` at H=10 (roadmap §5 frame) for cross-study
comparability, with −10pp as the tail read.

**O4 — Entry quality.** Owned by Live Entry Radar's outcome definitions (#5578 §10):
forward return / MFE / MAE / time-to-positive / target-before-invalidation /
gap-through-invalidation / benchmark excess, with `false start` frozen as
`MAE ≥ 1.25×A0 before MFE ≥ 1.00×A0` within H=10. ("Distance from eventual local low" is
Stock Identity's `price_dist` construct, not an LER outcome — kept distinct.) This
program *consumes* those grades for the Entry head and defines NO rival entry outcome —
**the Entry head is therefore DEFERRED until LER grades exist**; until then Layer D's
entry mechanics run entirely on LER's live states, and the arena carries no Entry-head
metric (a deferred head is reported as deferred, never proxied — an earlier draft's
`fwd_mdd`-before-`fwd_mfe` stand-in was itself a rival outcome and is withdrawn).

**O5 — Fragility.** `P(excess_spy < −3pp)` at H=10 (the established loser rate) and
`P(excess_spy < −10pp)` at H=21 (the severe tail).

**O6 — Confidence calibration (the Confidence head's own ruler — a head with no ruler is
unfalsifiable and may not move rank).** Target: conditional coverage of the printed
asymmetry band — `P(realized excess ∈ [printed q10, printed q90])` per printed-confidence
decile, plus realized |forecast error| monotonicity across confidence deciles. A
Confidence head is WRONG when its high-confidence rows realize wider dispersion than
their printed band. Until O6 accrues enough to read, Confidence is display-only and
§10.4.4's rank-conservatism clause stays dark. **Abstention semantics (mechanical):**
"abstains rather than imputes" = the family contributes an explicit per-family
missingness indicator carried as a first-class model input (never a silent zero — a zero
contribution IS imputation at the neutral value), plus a declared `max_staleness_sessions`
per family in `families.yml` (13F, monthly FINRA settlements, 2–3×/wk options and daily
theme cannot share one staleness notion).

**Population.** Curated tier only. Scan-tier rows are never pooled with curated rows in any
training set or metric (store law, `data/us_prophet_rank/README.md` §two-tiers). The graded
population (board admission) is untouched by this entire program
(`DNR:KILL-PROPHET-POP-MERGE`).

**Era hygiene (binding).** Training and evaluation frames must: exclude the disclosed null
era 2026-08-03..08-06 (frozen-alpha incident — `data/us_board_ledger/README.md`, enforced by
`test_no_graded_rows_were_backfilled_into_a_disclosed_null_era`); carry `board_definition`
(us_prophet_v1 vs v2) and `selection_era` as STRATA (chosen over features: as features
they are row-constant per night and share F6's cross-sectional degeneracy; as strata they
fragment n — the fragmentation is the honest cost and is reported); respect the
`price_basis` era boundary (2026-08-06), the options chain-store era boundary
(2026-08-07), the v1→v2 score-scale break (§6.6 — replayed v1-era scores diverge up to
16.3 pts from published), **and the context-vector universe-widening break inside the
4-day frame** (08-05/06 ≈ 1,51x rows vs 08-07 = 4,737 — coverage percentages are
reported per stamp date, never pooled across this break). **Population enforcement:**
"curated only" joins on the candidates store's `tier == "curated"`; the grades store's
`universe_tier`/`signal_class` cohort columns are currently null by a named sibling-lane
debt (store README) — until they land (§13), class-conditional claims are impossible and
are not made.

---

## §8 The frozen modeling arena (deliverable 6)

### §8.1 Ladder

| Rung | Model | What it answers |
|---|---|---|
| **G0** | Live `us_prophet_v2` order (stage bucket, then priority score), replayed | the champion (replay diverges from what shipped in the v1 era — see G0′) |
| **G0′** | The actually-PUBLISHED historical order, read off `snapshots.jsonl` | what users saw — mandatory baseline, because the replayed G0 diverges from it by up to 16.3 pts on v1-era boards (§6.6) |
| **G1** | Residual-alpha ordering (pure `alpha` desc within admitted pool) | is the champion's non-edge machinery adding anything over its own selection axis? |
| **G2** | `name_score` `potential_score` ordering | the rival in-house composite, already load-bearing in the plan funnel, finally raced on one ruler (roadmap §4.4's unfinished adjudication) |
| **G3** | `us_prophet_v2` with the edge leg SIGN-FLIPPED | champion-repair baseline: §6.6 measured `alpha` NEGATIVE against forward excess on the only graded frame — if that holds, any challenger would be credited for fixing a one-leg bug; G3 prices the bug-fix directly |
| **G4** | `us_prophet_v2` with the edge leg REMOVED, weight redistributed pro-rata | champion-repair baseline: the deletion variant of the same question |
| **C1** | Independently normalized evidence-family model: one z/percentile per family (§5), equal or IC-sign weights, NO interactions, NO fitting beyond per-family normalization | does breadth of evidence help at all, before any cleverness? |
| **C2** | Regularized linear/logistic/ordinal stack over typed family features (elastic net; group-lasso at family granularity; monotonic signs where a family carries a filed directional verdict) | the honest fitted baseline every fancier model must beat |
| **C3** | Nonlinear date-grouped ranker (LightGBM LambdaMART / gradient-boosted ranking on date-grouped candidate sets — never IID row classification) | do interactions/nonlinearity pay? |
| **C4** | Conditional mixture-of-experts: C2/C3 plus router features (identity fingerprint, setup species, regime, dispersion, liquidity, catalyst proximity, crowding) interacting with family contributions | does CONTEXT-dependent weighting pay beyond global weights? |
| **C5** | Multi-head challenger: separate Selection / Asymmetry / Entry / Fragility heads + Confidence, composed by the §10.4 decision policy | does modeling the tails and separating WHEN from WHAT pay? |

**Complexity ladder law (frozen):** a rung ships to the shadow race only if its
INCREMENT over the **best surviving simpler rung** independently clears the CI + FDR bar
— not merely "beats the rung below" as a chain of hair-thin wins. Registered minimum
increment: ΔP@5 point estimate ≥ +3pp with date-blocked 95% CI excluding zero on the
primary tuple. Tie rule: if CI(C_k − C_j) overlaps CI(C_j − G0), **C_j ships** — the
simpler model wins ties by law. When a rung is skipped (depth-gated PR-4), "best
surviving simpler rung" resolves to the highest rung that actually ran. Complexity that
cannot explain its own improvement is discarded. Deep neural architecture is not
presumed necessary and is out of scope for the first arena generation entirely.

### §8.2 What "frozen" means

- Arena registration = model id + feature list (by family) + training window + hyperparameter
  grid, committed BEFORE outcome reads. Grid size is disclosed and small (DSR-style
  multiplicity honesty; the standards doc's killed-construction grounds).
- The live champion's constants never move as part of arena work.
- Challenger scores are stamped nightly into a **shadow** artifact (CN precedent:
  `data/prophet/legacy_shadow/`), never into the live board, the candidates store's scored
  columns, or any user surface.

### §8.3 Metrics (all reported; primaries bolded; the product question is the top of the board)

**Measured on the DEPLOYED COMPOSITION, not the raw score.** Every primary is computed on
the order the product would actually publish — the challenger's score substituted into
the SAME stage-bucketing, vetoes, and sort machinery (`(stage_rank, −score, ticker)`) the
champion uses — because §6.7.1 measured that a majority of cross-bucket raw-score
comparisons contradict the published order; a raw-score P@5 measures something no user
ever sees. Pure-score-order metrics are reported as diagnostics only. Two co-primary
surfaces ride with the board order: **featured-shelf precision/loser-rate** (the actual
action surface — a veto-filtered prefix, §6.7.4) and a **plan-origination delta report**
(build_prophet consumes the priority order — §2 names it as one of the three surfaces a
promotion changes).

**One primary tuple per rung (registered before any result exists):** the promotion
question is asked of exactly ONE (metric, horizon, class) tuple per rung — P@5 +
top-5 mean excess at the chartered headline horizon of the `momentum`/`other` class
(H=10) on the deployed composition, pooled over classes until the cohort columns land
(§7). Everything else in the list below is secondary or exploratory; **slices are
exploratory by construction and structurally barred from §8.6 promotion claims**.

**Identical candidate sets:** all rungs score the same date-grouped candidate sets;
abstention is expressed only through the Confidence field, never by removing a name from
the ranked set — a model that ranks an easier subpopulation has not beaten anything.
Coverage-matched metrics are published beside every comparison.

**Anti-gaming guards (registered):** beside every primary, each model's top-5 reports
ex-ante beta, realized vol, ADV, and sector-Herfindahl; a pre-registered non-inferiority
bound on top-5 sector concentration vs G0; and the primary must SURVIVE a
beta/size/vol-neutralized variant (reported side-by-side) — `excess_spy` alone is not
risk-adjusted, and in an up-tape a beta-ranker wins raw P@5 with zero information.

- **P@1, P@3, P@5**, P@10 (P(excess>0 | top-k), at the chartered headline horizon)
- **Top-5 mean and median excess** (the slugging read; the retro finding was precisely that
  the top slots were the broken part)
- Cross-sectional rank correlation (secondary; pooled IC alone is explicitly insufficient)
- **Large-winner capture rate**: share of realized top-decile-excess names that appeared in
  the model's top-10 that night
- **Large-loser rate**: share of the model's top-10 that landed below −10pp @21
- MFE / MDD medians for the top-10; expected shortfall (mean excess of the worst decile of
  top-10 picks)
- False-start rate (Entry head; LER definition once mature)
- Lead time vs the champion (sessions between challenger first-surfacing a name in top-K and
  champion doing so, for names both eventually surface)
- Turnover of the top-10 (day-over-day Jaccard) and implied cost sensitivity
- Calibration (reliability of P(excess>0) and tail probabilities, Brier)
- Every metric sliced: era / regime quad / dispersion state / sector / cap-liquidity bucket /
  setup species / signal class — **slices are reported with their n and never quoted without it**

**A challenger that improves pooled IC but degrades P@5 or the large-loser rate is a
failure for Prophet** — frozen as arena law.

### §8.4 Baselines' honest state

The champion currently has **no demonstrated selection alpha at fixed horizons** (Eval OS
sitrep §3.1: n=15 priced plans, every CI includes zero; plus the plan-record read isolates
management, not selection). The board-ledger read (§6) is the wider-n version of the same
question. The arena's job is therefore NOT "beat a proven champion" — it is "produce the
first challenger whose superiority is demonstrated under rules fixed in advance". The
50-episode floor (standards §4.7) applies to any external claim about the winner.

### §8.5 Data-depth honesty (what can be trained TODAY)

The arena has three frames, and the widest one is young:

1. **Wide-context PIT frame** — `data/us_prophet_rank/candidates/`: **four stamped
   trading days total** (2026-07-31, 08-05/06/07; §4.0 — accrual currently BROKEN and the
   first PR-1 action). Rich enough for coverage censuses and C1 smoke tests once
   restored; NOT rich enough to train C3/C4 honestly at the chartered horizons for
   months.
2. **Graded-board frame** — `data/us_board_ledger/retro_grades(.v2).parquet`, 2026-06-15→,
   with W3 evidence-stack confirmer fields from 06-30 (smartmoney_add, sue_fresh,
   news_burst, confluence_k) and options-state fields at 9–12% coverage. Supports C1/C2
   on the admitted population, with era stamps. Label: `survivorship = reconstructed
   curated universe; acceptable with disclosure`. ⚠ `insider_cluster` on this frame is a
   **train/serve skew**: the insider panel stopped at 2026q1 (§4.2.3), so a model
   trained on it finds the feature dead at serving time — excluded from training until
   the collector is repaired (the §8.3 train-vs-serve coverage diff enforces this class
   of exclusion generally: any feature whose serving coverage is <50% of its training
   coverage is excluded by default).
3. **Deep price/technical frame** — `data/massive_stock_day` (2021→, 20k names),
   `data/baskets/ohlcv` (2014→), EDGAR stores (8-K events, insider panel), polygon_gex
   chains (mid-June→). Supports multi-year PIT reconstruction for price/technical experts
   and a few event experts; most theme/foresight/hub state is snapshot-only history.
   Label: **`survivorship_biased: true`** pre-assigned NOW — this frame cannot prove
   survivorship-cleanliness (delisted-name handling unverified), and per §9.6 no
   promotion claim may rest on it.

Consequence, frozen into the sequence (§14): **PR-1 races G0/G1/G2/C1/C2 on frames 2–3 and
starts the missing accrual clocks; C3+ waits for depth.** The deep-history reconstruction of
any lobe must itself be PIT-clean (reconstructed from filing/event dates, never from mutable
latest.json files), and every reconstructed lobe carries a `reconstructed: true` provenance
flag in the arena so a skeptic can ablate it.

### §8.6 Promotion gate (frozen now, before any result exists)

A challenger may be proposed for promotion only when ALL hold:

1. Beats **every baseline rung — G0, G0′, G1, G2, and the champion-repair variants
   G3/G4 — and every simpler surviving challenger rung** on the registered primary tuple
   (§8.3), out-of-sample on the deployed composition, with each increment's date-blocked
   95% CI excluding zero (`DNR:LAW-TIME-CLUSTERED-CI` — block by date/month, never
   ticker-cluster alone) and the §8.1 minimum-increment/tie rules honored.
2. Does not degrade the large-loser rate or the top-10 expected shortfall (CI-supported
   non-inferiority).
3. Sign-stable across two half-splits of the evaluation window AND across
   `selection_era`-consistent strata (`DNR:LAW-ERA-SPLIT`). **Honesty note:** with one
   usable prophet-scored era today, the era-strata half of this condition is
   UNSATISFIABLE until a second graded era exists — the gate therefore cannot pass
   before then, and that is the intended reading, not a defect.
4. ≥ 50 graded episodes per headline cell it claims (standards §4.7); episode-level
   honest-N counted by distinct (name, admission-episode), not fire-days. **No
   `basing`-class claim is possible before H=63 grades exist** (zero H=42/63 rows today
   — §8.7); the basing headline stays dark until its chartered ruler has data.
4b. No promotion claim may rest on a frame carrying `survivorship_biased: true` (§8.5
   frame labels; §9.6).
5. Survives an adversarial review pass (a fresh reviewer attacking §16's list against the
   actual result artifacts).
6. Operator/CEO adjudication. Promotion changes `board_definition` (new era stamp,
   superseded stamp appended — the #4509 lesson), ships the §10.5 explanation surface, and
   arms the displaced champion as the new shadow (reverse race + tripwires), so demotion is
   one switch.

Interim, lawful sub-promotions below full rank authority (each its own prereg, unchanged
process): a lobe may earn a **featured prior**, a **capped score leg**, or a **demotion/veto
right** through the existing ladder — the ruling widens the ceiling, not the floor.

### §8.7 Power honesty (what the gate can actually detect today)

Registered so the gate is never decorative: gen-1's comparison surface is the rung set
(G0/G0′/G1/G2/G3/G4 + C1, then C2) × ONE primary tuple = **7 primary comparisons**, FDR
applied over model×metric×horizon on the secondary table (the registered integer
comparison count is published in PR-1b's report BEFORE outcomes are read; slices are
exploratory, uncounted, unclaimable). With ~24 usable date-blocks, the date-blocked SE of
ΔP@5 is ≈ 0.03–0.04, so §8.6.1 can detect roughly a **+10pp** P@5 improvement and
nothing smaller; the 50-episode floor (§8.6.4) is unreachable at H=21 today (top-5 of a
442-row H=21 frame ≈ 30 episodes), and H=42/63 have ZERO graded rows. The gate becomes
non-decorative at roughly **≥ 60 graded prophet-era dates** (minimum-usable-fold, §9.2)
and **≥ 50 top-K episodes at the headline horizon** — on current cadence a Q4-2026
conversation for H=10/21, later for H=63. Until then the arena publishes
distance-to-power beside every read (the signal-governor idiom: "need ≥N, have n").

---

## §9 Validation protocol (deliverable 8)

1. **PIT joins only, on the store's OWN availability field.** Context features join on
   `(stamp_date, ticker, board_definition)` from the candidates store; event features
   join on the availability timestamp the store itself carries (`filing_date` /
   `available_date` / `ReportDate` / vintage date). **Derived statutory lags are
   FORBIDDEN as join keys** — a fixed "45-day" or "2-business-day" lag is wrong exactly
   for the interesting cases (delinquent Form 4s, late/amended 13Fs). A store with no
   availability field is forward-accrual-only (§13), never lag-approximated. No
   today-known revision reaches a historical row; snapshot-only stores may not be
   joined historically at all.
1b. **Fold-scoped normalization.** Every normalization, percentile, winsorization, or
   reference distribution a feature pipeline uses is fit on the training fold only and
   carried forward frozen; no full-sample statistic may touch a feature (this binds
   §6.8's "frozen reference distributions" — frozen means fold-frozen, never
   whole-history).
2. **Walk-forward time splits** with purging and embargo ≥ the longest horizon graded in
   the fold, so overlapping outcome windows never straddle train/test.
   **Minimum-usable-fold rule (registered now):** after purge+embargo a fold must retain
   ≥ 60 distinct training dates and ≥ 10 distinct test dates, else the harness REFUSES
   the fold and says so — it never silently shrinks. Today's graded frame (24 dates,
   H≤21 only) cannot satisfy this at a 63-session embargo; that is a fact the arena
   reports (§8.7), not a parameter it bends.
3. **Date-grouped candidate sets.** Ranking models train and evaluate on within-date groups;
   IID row shuffling is forbidden.
4. **Era-aware evaluation** (§7 era hygiene): era stamps as strata; no pooled inference
   across the 2026-08-06 price-basis boundary or the options-store boundary without
   disclosure; the disclosed null era is excluded, not imputed.
5. **Name-disjoint validation + capacity budget + permutation null, from C3 upward.**
   Every rung with enough capacity to memorize names — C3, C4, C5, not just the router —
   carries all three Channel-A conditions from #5583 §2.3 verbatim: (i) **capacity
   budget** `p_eff ≤ N_names/10`, computed and PRINTED in every arena report; (ii)
   **name-disjoint OOS** (name-blocked K-fold primary; train names ∩ test names = ∅);
   (iii) **name-permutation null** (the result must die when names are shuffled within
   date groups). Rationale: C3's F7 inputs (archetype: 1,465 tickers; personality:
   223-name universe) are near-unique keys on a ~70-row board — an ensemble memorizes
   names without ever seeing `ticker`. Global fingerprint→expert-fit mapping,
   behavioral-neighbor pooling, and empirical-Bayes shrinkage are the ONLY lawful
   per-name mechanisms; per-ticker outcome argmax is `DNR:KILL-OUTCOME-AUDITION` and
   stays dead (its per-CLASS clause is confronted in §12).
6. **Survivorship — with a consequence, not just a label.** Curated-universe membership
   is reconstructed PIT where possible; the scan tier (never admitted, never pooled)
   exists precisely to count the invisible; any frame that cannot prove
   survivorship-cleanliness carries `survivorship_biased: true` in its artifact
   (pre-assigned per frame in §8.5), its numbers may not be quoted without the flag, and
   **no §8.6 promotion claim may rest on a flagged frame** (§8.6.4b).
7. **Costs/realism.** Next-session-close fills (already the grades-store fill rule);
   turnover and cost sensitivity reported for every challenger; no intraday assumptions.
8. **Multiplicity honesty — on the axis the leaderboard actually varies over.** Every
   arena generation registers its full INTEGER comparison count before outcomes are read;
   FDR is applied over **model × metric × horizon** (the leaderboard's axes — "family
   grain" BH-FDR applies separately to the §5.3 "lobe X adds information" table, which
   IS family-per-row); exactly one primary tuple per rung (§8.3); slices exploratory and
   promotion-barred; hyperparameter grids disclosed with their size and
   deflated-Sharpe-style haircuts applied; the §8.7 power table published beside every
   generation's results.
9. **Coverage tables.** Every training frame publishes per-family coverage; a family below
   its declared coverage floor abstains rather than imputes (#4485 null-never-false, at
   model scale).
10. **Estimability gate for conditioning axes** (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY`
    compliance): before any router axis is used, `engine.regime_conditioning_coverage.assess()`
    (or its successor) must return `estimable` for that axis on the training frame, and the
    router claim is registered with the interaction as the PRIMARY hypothesis. The 2026-08-05
    kill measured the family×regime interaction 3.8× smaller than the family main effect on
    the only multi-regime record then available — the router must beat that bar on estimable
    cells, not argue around it.

---

## §10 The proposed architecture (deliverable 9)

### §10.1 Layer A — the expert plane (mechanically distinct, independently graded)

Experts are **typed readers over existing producers** — no new signal engines, no forked
logic (`canonical producer → typed evidence → context vector / event bus → fusion model`).
Each expert: (a) belongs to exactly one evidence family (§5); (b) exposes typed features
with declared PIT semantics; (c) keeps its OWN standalone graded record (the existing
grading substrate: doors, name_score grader, hub track record, LER grades, board grades) so
its conditional contribution can always be decomposed back to "what did this expert know".
Mechanically different event families are never flattened into one "bullish" bit.

Family roster (details + receipts in §3/§4/§5): price/technical (confluence cascade,
washout lifecycle, early-turn, leader-pullback/reset, LER entry-event families, residual
alpha, extension/runway, momentum); theme/sector (basket lifecycle + heat rank, sector turn,
theme lifecycle, relay position, State of Themes, Foresight stages, Hub edge-remaining +
lifecycle + leading-vs-lagging gap); catalyst/fundamental (earnings proximity/SUE/revisions,
8-K, government contracts, activist/13D, BioCatalyst, fundamental forensics, capital
structure/quality); flow/positioning (options flow, GEX/dealer positioning, dark/flow
attention where available, institutional footprints, insider clusters, Congress, 13F, short
interest); macro/causal (regime vector, transmission chains, rates/liquidity/inflation
states, commodity linkage, factor/dispersion state).

### §10.2 Layer B — the contextual router

Routing features (context, never evidence): behavioral stock fingerprint + identity epoch
(#5583's interfaces, adopted wholesale), setup species / signal class, drawdown/trend state,
sector, theme-lifecycle position (early vs consensus), market regime quad, dispersion/
correlation state, volatility state, liquidity/market-cap bucket, catalyst proximity,
earnings state, extension/crowding, horizon.

Router laws (frozen): the three #5583 mechanisms only (global cross-sectional
fingerprint→expert-fit; behavioral-neighbor pooling; empirical-Bayes residual shrinkage);
no per-ticker outcome argmax; every routing cell gated on estimability (§9.10) and shrunk
toward the family prior at small n; router weights are versioned artifacts, frozen between
promotions, never fitted in place on the live path.

### §10.3 Layer C — the multi-head outcome model

Heads per §7's outcomes: **Selection** (probability AND magnitude of benchmark-relative
excess at the chartered horizons), **Asymmetry** (tail probabilities, conditional
upside/downside, MFE/MDD quantiles), **Entry** (LER-owned; WHEN, never WHAT),
**Fragility** (loser/severe-loser probability — negative evidence is first-class),
**Confidence** (epistemic: falls on stale evidence, missing inputs, weak historical
applicability, out-of-distribution context, high redundancy of supporting evidence, low
expert n, strong expert contradiction). Missing evidence ≠ negative evidence: absence
lowers Confidence, never Fragility.

### §10.4 Layer D — decision / ranking policy

The Board keeps ONE Priority number as the endpoint, not the model:

1. **Timing/actionability determines the stage/lane** (unchanged law — timing owns grouping,
   never within-group order; the stage buckets and their vetoes stay).
2. **Expected opportunity + asymmetry order the actionable population** — candidate form
   `U(H) = expected_excess(H) − downside_penalty − execution_cost`, with asymmetry retained
   explicitly (quantile terms), λ coefficients NOT frozen before the distribution study
   (PR-6 scope).
3. **Fragility can demote or warn** (a veto/haircut lane, mirroring the signal governor's
   de-escalation-only precedent).
4. **Confidence scales trust** — low-confidence rows rank conservatively and say so.
5. **Entry mechanics determine Starter/Add/Wait/Don't-Chase** — LER's surface, consumed.

### §10.5 The explanation contract (glass-box law, surviving form)

Better intelligence must produce a better explanation, not a more opaque number. Frozen
product contract for any surface the challenger ever reaches: Priority N, plus the head
sub-scores (Edge / Asymmetry / Entry / Risk / Confidence), plus "Why surfaced" (top
positive evidence attributions, by family, in plain words) and "Against" (top
negative/risk attributions). **Attribution is specified, not vibes:** method =
family-aggregated interventional TreeSHAP (or exact linear attribution at C1/C2) with a
FIXED background set; target = the calibrated head outputs (P(excess>0) / expected
excess), never the ranker margin (a LambdaMART margin is ordinal within a date group and
does not answer "why is this #1"); granularity = **family-level only** — feature-level
credit between siblings correlated at the documented ρ=0.984 is not identifiable and is
never printed; MoE attributions decompose across expert × router weight; and a
pre-registered **stability gate** (rank-correlation of family attributions across
bootstrap retrains ≥ a registered floor) must pass before any attribution reaches a
surface. A model that cannot meet this contract does not ship, whatever its metrics.
The plain-words layer binds to the existing banned-vocabulary CI checks;
falsifier/refutation vocabulary stays off user surfaces (operator 2026-07-27); nulls are
disclosed in plain words with Tier-2 receipts.

### §10.6 Anti-double-count law (mandatory, §5 is its registry)

Evidence enters the model by FAMILY, **at every rung C1–C5** (group-level regularization
or explicit family aggregation in C1/C2; feature-grouping constraints + family-level
permutation ablations in C3/C4/C5 — a rung with no family-budget mechanism may not run).
Correlated siblings share one family budget; `Hub bullish + Foresight bullish + Theme
bullish` is never three votes when they share upstream feeders —
the Hub contributes **typed decomposed inputs** (leading-vs-lagging gap, lifecycle,
edge-remaining, isolated/pre-consensus, feeder directions, governor trust, contradictions),
never its `opportunity_score` as an unquestioned scalar. For every candidate feature the
arena reports: standalone relationship, incremental vs current Prophet (cross-fitted
residualization), incremental vs its own family, temporal + regime stability, top-K effect,
adverse-tail effect. The question is always "what does this add that Prophet did not
already know?".

### §10.7 Pre-registered interaction hypothesis families (hypotheses, NOT rules)

The CEO list, registered here so later outcome reads are prereg'd, each with its nearest
standing fence named: stock turn × basket/sector turn (nearest: the ratified RECLAIM
waiver; distinct from `DNR:KILL-WASHOUT-TURN`'s 2W operator-seed construction); washed-out
stock × washed-out peers (the RECLAIM waiver's own axis, now as ordering evidence); early
theme lifecycle × modest stock RS; Foresight loading × price not yet confirmed; analyst
revisions × approaching earnings; insider/activist × low attention (distinct construction
from `DNR:KILL-INSIDER-T2`); options positioning × catalyst proximity; positive flow ×
reset/entry event; macro transmission chain × exposed industry; improving fundamentals ×
washed technical state; high theme heat × high extension/crowding as NEGATIVE asymmetry
(the S-C crowding finding, promoted to a tested interaction); multiple independent families
agreeing vs correlated siblings agreeing; contradiction intensity → false-start prediction.

---

## §11 Interoperability with the sibling programs (deliverable 10)

Recon run 2026-08-14. Both siblings are OPEN + `merge-on-green` (unmerged); their records
live on their own branches. **File-level collisions: none** — neither `owns_paths` set
touches `engine/us_board_rank.py`, `engine/us_context_vector.py`, `engine/name_score.py`,
or `data/us_prophet_rank/`; zero open PRs (of 32) touch those files either. Four adjacent
prophet PRs (#5541, #5540, #5533, #5506) share only `scripts/build_prophet.py` — a
merge-conflict-risk file at PR-7 (promotion touches origination ordering), not a scope
collision.

**The decisive finding: the fusion role is already pointed at by both siblings' own
contracts — #5583 defers Prophet-consuming routing to a gate this program now supplies,
and #5578 reserves entry-detector fusion (`F1_FUSION`) inside its OWN arena — and this
program is the cross-family consumer both boundaries describe.** (Rung-id
disambiguation: this arena's `G0…C5` ladder ids are unrelated to LER's
`G0_GREY_DOT@1…C5_BOTTOM_WATCH@1` detector ids — same letters, different registries;
every cross-reference spells the full LER id.)

### §11.1 PR #5578 — Live Entry Radar (consumed as the entry-expert plane)

- LER PR-0 freezes a detector arena (`research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md`
  §4): `G0_GREY_DOT@1` (champion), `C1_1D_LIVE_WASHOUT@1`, `C2_1D_TURN@1` (6 variants),
  `C3_1D_4H_RECOVERY@1`, `C4_MTF_TURN@1` (stratification only — never arms; re-cutting it
  as an arming interaction reopens `DNR:KILL-WASHOUT-TURN` by name), `C5_BOTTOM_WATCH@1` —
  and a reserved **`F1_FUSION`** id: *"Not in V1. Registered only after individual detector
  results exist; never champion by definition."*
- **Contract:** this program treats LER's detector families as DISTINCT ENTRY EXPERTS
  (never flattened — LER §18 A1's Expert Preservation ruling), consumed through its typed
  interfaces `mastermind.entry_event.v1` (append-only expert-event store, per-field
  `field_origin`) and `mastermind.live_entry_episode.v1`
  (`PROBING → ARMED → TURNING → CANDIDATE → INVALIDATED | EXPIRED | RESOLVED`), available
  from LER PR-2 onward. `research_priority` / `opportunity_score` fields on those records
  are ACCRUING-tier, not authority — the fusion model treats them as features to test, not
  votes to trust.
- **The Entry head (§10.3) is LER-fed**: entry-quality outcomes are LER's own definitions
  (§7 O4); this program builds no rival entry detector, no rival entry outcome, and does
  not register anything inside LER's arena. When entry-expert fusion results exist, they
  flow back through LER's own `F1_FUSION` registration — fusing entry detectors inside
  LER's arena is LER's slot, not a second one here. What THIS program fuses is
  cross-family (entry × selection × theme × catalyst × flow × macro), which no LER
  detector id claims.
- LER §8's internal "Structure/Leadership Model (context vector, not a gate)" is a prose
  naming collision only — it is NOT `engine/us_context_vector.py`; named here so future
  greps do not conflate them.

### §11.2 PR #5583 — Stock Identity & Expert Routing (consumed as the router substrate)

- **Method Law adopted wholesale** (its §2.3, Sol-ratified 2026-08-14): Channel A
  (global cross-sectional fingerprint→expert-fit map, capacity-budgeted, name-disjoint
  OOS), Channel B (behavioral-neighbor pooling, calendar-disjoint, precision-weighted),
  Channel C (empirical-Bayes per-name residual shrinkage, printed n) — pooling ladder
  `global base rate → A → B → C`; ticker is identity/memory, never a feature/key; no
  per-name outcome argmax, ever.
- **Interfaces consumed** (its §12, all display-tier/authority-false at birth):
  `stock_identity.fingerprint.v1`, `stock_identity.episode_catalog.v1`,
  `stock_identity.fit.v1`, `stock_identity.sif.v1` (per-name: current epoch + confidence,
  fingerprint ref, behavioral neighbors, expert response profile by episode type × tier,
  abstain conditions, provenance). The §10.2 router reads these; it never rebuilds a rival
  fingerprint/epoch/personality stack.
- **Its §12.4 promotion clause IS this program's entry gate**: *"Any Prophet-consuming
  routing influence = a separate PR behind: qledger-registered accrual history, the full
  evaluation-standards ladder (holdout → walk-forward → shadow → live-forward), an
  explicit prereg in the R4 shape, Article-2 perimeter compliance, and by-name
  confrontation of `DNR:KILL-OUTCOME-AUDITION` + `DNR:KILL-WASHOUT-TURN`."* This
  masterplan adopts those five conditions verbatim as additional preconditions on §8.6
  promotion — the CEO fusion ruling supplies the architectural authorization #5583
  deferred to; it does not waive the evidence conditions. The by-name confrontations
  live in §12 (per-name AND per-class halves of the audition kill) and §10.7
  (washout×turn construction distinction).
- **Contingency (frozen):** #5583's Q1 blind-arm consequence matrix is pass-or-stop with
  no B/C fallback ("do not soften these criteria after seeing results"). If Q1 fails vs
  both baselines, its program stops and Channel A closes — in that world the §10.2 router
  falls back to coarse context axes only (regime quad, dispersion state, setup species /
  signal class, liquidity bucket, catalyst proximity), all subject to the same §9.10
  estimability gate, and no fingerprint conditioning ships. The fusion arena (C1–C3) is
  deliberately independent of that outcome; only C4's identity axes are contingent.
- Sequencing per its §16.9: W1 (Identity Atlas v0, descriptive-only) launches on #5583's
  merge; no expert-fit result exists until its own gates pass. Fusion PR-5 therefore
  depends on #5583 W1 interfaces EXISTING, and on its Q1 outcome for fingerprint axes —
  reflected in §14.

### §11.3 Boundary statement (one sentence each)

- **LER owns**: entry-event detection, entry outcomes, entry-detector fusion (`F1_FUSION`),
  the entry surface.
- **Stock Identity owns**: fingerprints, epochs, episode catalogs, expert-fit maps, the
  routing method law.
- **This program owns**: cross-family conditional fusion and the meta-ranking of the US
  board — the consumer both siblings' contracts point at — plus the arena, outcome heads,
  and promotion machinery for it.
- **Agent OS**: `WS:PROPHET-CONDITIONAL-FUSION` owns the masterplan today (`owns_paths`
  lists in-repo paths only) and claims `research/prophet_fusion/`,
  `scripts/prophet_fusion_*`, and `data/us_prophet_rank/shadow/` at PR-1 when they
  exist — deliberately NOT `engine/us_board_rank.py` itself, which
  stays shared ground (heal lanes touch it; the program touches it only at PR-7 under its
  own adjudication). Same `p0: US_PROPHET_ENTRY_TIMING` as both siblings and
  `WS:PROPHET-US-ENTRY-TIMING` (whose `engine/prophet_*.py` glob is adjacent territory —
  coordinate at PR-7, where plan-origination ordering is touched).

---

## §12 Superseded vs intact (deliverable 12)

**Superseded by the CEO ruling (effective now, recorded in
`DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY`):**

1. **The blanket-permanent reading of `ZERO_SCORE_AUTHORITY`** (us_board_rank.py:430-455,
   its module-docstring rule "context chips only", and the store-level "zero authority"
   framing wherever it means *forever* rather than *at birth*). The list itself remains
   ACCURATE as a description of today's live score and stays in the artifact disclosure
   until a promotion changes it; what is repealed is its permanence.
2. **"One axis at a time, forever" as the ONLY promotion shape.** The roadmap §3
   bounded-authority ladder remains the lawful path for single-axis promotions, and is
   AMENDED to admit one additional promotion unit: a **versioned fusion model as a whole**
   (champion/challenger, §8.6). Without this amendment a 30-feature conditional model would
   need 30 sequential multi-month preregs — a permanent no wearing a gate's clothes (the
   exact failure mode the entry-map revision rule names).
3. **The glass-box law's LITERAL form** ("the priority score stays a sum of defensible
   legs") — superseded as the required *implementation*; SURVIVING as the §10.5 product
   contract (full attribution, versioned frozen parameters, revertibility, coverage
   abstention, forward grading from day one).
4. **Blanket-permanent readings of the family kills as information bans**: SUE, insider,
   smart-money/13F, options/GEX, short-interest, theme/sector-turn/narrative lobes are
   unvalidated-at-birth inputs eligible to EARN conditional influence through the arena.
   Every underlying construction kill stays closed (below).

**Intact — this program complies, and proposes no change:**

- `DNR:KILL-PROPHET-POP-MERGE` — graded population/membership untouched; fusion re-orders,
  never admits.
- `DNR:KILL-OUTCOME-AUDITION` — no per-name outcome argmax anywhere, router laws per #5583.
- `DNR:KILL-OFFHORIZON-VERDICTS` + chartered-horizon prereg — verdicts at registered rulers
  only.
- `DNR:KILL-LLM-ORIGINATION` / A7 — the fusion model is statistical; LLMs still originate
  nothing.
- `DNR:KILL-FRESH-TICKS-WINDOW` — admission window untouched (third-look kill stands).
- `DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` — its re-open condition IS this program's router
  gate (§9.10): estimability assessment + interaction-as-primary + fresh prereg.
- `DNR:LAW-TIME-CLUSTERED-CI`, `DNR:LAW-ERA-SPLIT`, `DNR:LAW-REVERSION-RULER`,
  `DNR:LAW-FAMILY-CLOSURE` — encoded in §9.
- `DNR:KILL-STAGE-WIN-GATE`, `DNR:HOLD-PSQ-TILT-CLOCK` — stage/EC constructions unchanged.
- `DNR:KILL-FORCED-CALLS`, `DNR:HOLD-IGNITION-SURFACES` — no un-gauntleted directional
  surface claims.
- Every PSS/fingerprint/LSR/etc. construction kill — closed constructions stay closed; a
  family re-enters only as a *different construction* through the arena with its kill named
  in the registration.
- Timing-owns-grouping ("order by edge, gate by timing, never the reverse") — Layer D keeps
  it; any challenger wanting to re-order across stages is a NEW adjudication this program
  does not request.

**Two rows AMENDED IN THIS PR** (registry §1's heading forbids even phase-0 *testing*
of listed constructions, so deferring the amendments would have made PR-1's arena work
unlawful; the registry's own convention — the adjudicating PR appends/amends its rows in
the same PR, compiled blocklists regenerated together — is followed here, with the CEO
ruling + the DEC record as the adjudication trail. DNR keeps kill authority; the DEC
records the choice; the row text is where the scope lives):

- `DNR:KILL-FUSED-COMPOSITE` — **Amendment 3** (in this PR): the AUTHORITY half is
  amended for exactly one construction — this program's conditional-fusion challenger —
  which may be built and TESTED at research/shadow tier under the §10.5 construction law
  and may take live authority only via §8.6. Every other scored path keeps the full
  prohibition. (Amendment-form precedent: the row's own dated-amendment history.
  Corrected reading vs an earlier draft: Amendment 2 struck the DISPLAY half and
  explicitly kept the authority half standing — it is precedent for the amendment FORM,
  not for the authority substance; the authority-half amendment's substance rests on the
  CEO ruling alone.)
- `DNR:KILL-POSITIONING-FUSION` — **Amendment 1** (in this PR): converts from permanent
  ban to unvalidated-at-birth FOR THIS ARENA ONLY; positioning families may be tested
  for earned conditional authority with their filed negative verdicts (short-interest
  FDR-fail; 13F sign) as priors to overcome, and `pit_status` fences binding (short
  interest is forward-accrual-only, §4.2). Fusing positioning keys into any OTHER
  signal or regime score remains ILLEGAL.

**Additional rows this program touches, dispositioned by name (all INTACT — compliance
stated):**

- `DNR:KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR` and `DNR:KILL-REGIME-SCORECARD` —
  INTACT. The fusion challenger is a stock meta-ranker, not a regime engine: F6 axes are
  CONSUMED from the existing `risk_radar → market_state → regime_vector` chain and enter
  only as router conditioning; no regime verdict, regime score, or tactical-allocation
  surface is fused or rebuilt. Positioning-keys-into-a-REGIME-score stays fully
  forbidden (the Amendment above is scoped to the stock-ranking arena).
- `DNR:KILL-ENTRY-21D-THESIS` — INTACT. That kill closed standalone entry-time theses
  (insider / macro / positioning) at 21d. §10.7's insider, options-positioning, and
  transmission hypotheses are conditional/interaction constructions at the SELECTION
  grain, not standalone entry-time signals; any arena registration of them at H=21
  names this row and states the construction difference, or does not run.
- `DNR:KILL-ONSET-FINGERPRINTS` (and the W4 volume-fingerprint sibling) — INTACT. No
  pre-onset winner-fingerprint claim anywhere: fusion conditions on CURRENT state; the
  fingerprint word in Layer B refers to #5583's behavioral identity interfaces, not
  onset prediction.
- `DNR:HOLD-WF-OPTIONS`, `DNR:HOLD-SHORT-INTEREST-LEGS`, `DNR:HOLD-PSS-CD1-CROWDING`,
  `DNR:HOLD-PSS-AF1-FINRA` — INTACT, holds respected: options W-F preconditions
  unchanged; short-interest legs deferred (and forward-accrual-only per `pit_status`);
  the PSS prospective charters' zero-authority accrual rules untouched — none of their
  exact constructions is re-cut here, and their manifests are not read by the arena.
- `DNR:KILL-OUTCOME-AUDITION`, **BOTH halves confronted by name**: the per-NAME half —
  no per-ticker outcome argmax; only #5583's three channels, with capacity budget +
  name-disjoint OOS + name-permutation null from C3 upward (§9.5). The per-CLASS half —
  the row's closing clause "W4 per-class gate profiles are UNLICENSED under both
  rulers" closed audition-DERIVED per-class GATE profiles (in-sample best-of-grid
  selection per class). §10.2's class conditioning is a different construction: a
  global regularized fit over registered class axes, estimability-gated (§9.10),
  name-disjoint-validated, shrunk toward the family prior, producing WEIGHTS that can
  never create a gate — and any per-class routing claim must clear its own registered
  question under the same two-ruler discipline. If a reviewer of any later wave finds a
  routing cell functioning as an audition-derived class gate, that cell is this row's
  construction and dies with it.

---

## §13 Telemetry gaps that should start accruing now (routed to PR-1, days away)

Every item follows the R2 reversal-cohort pattern (§3.3.2): additive column, zero
authority, coverage receipt, schema-union self-healing. PR-0 ships none of them (G0.12);
PR-1's first commit is this list. Cost of the routing decision: ~2–5 nightly stamps of
calendar delay per column — accepted to keep PR-0 pure-docs; the Eval OS law ("every week
we do not record is a week that cannot be reconstructed") is why PR-1 is scheduled in
days, not weeks.

0. **P0 — restore context-vector accrual** (§4.0): the store has stamped nothing since
   2026-08-07 while the board runs nightly. Diagnose the silent fail-soft path
   (`append_candidates` returns 0 on any refusal — lane gate, exception, or a commit-path
   omission), add a line-start `::warning` + a liveness check so the silent sibling can
   never go dark again, and verify the next nightly stamps. Chipped for immediate
   diagnosis (availability-program territory); PR-1 verifies the fix landed.
   Sub-items discovered by the same census: `insider` panel collector stopped at 2026q1
   (`insider__absent` 100% — repair before any insider claim); `_short_int_dim` must read
   the history file with the query date (it is `snapshot_not_pit` by construction today —
   until fixed, short interest is forward-accrual-only and excluded from every backtest);
   `factor`/`attention` host-only stores need either tracking or explicit
   coverage-printing so clone/CI studies cannot mistake absence for a null.
1. **The store's named debts** (`data/us_prophet_rank/README.md` §Named debts, roadmap §2
   sketch): `sue_z`, `catalyst_class`, `gex_state`, `flow_attention_z`,
   `short_vol_ratio`, `psq_stage`, `day3_mark_class` — the F4/F5 families' PIT columns.
2. **Computed-and-discarded confluence internals**: `stoch_ob` / `stoch_bear` /
   `macd_bear` (inline locals in `engine/confluence_tiers.py::cascade()` :504-507,
   currently only surviving as their OR-negation `not_topped`). ⚠ The module's own
   docstring records `macd_bear` as silently FAIL-OPEN on short-history names
   (`float(nan) < float(nan)` is False) — the stamp must carry the leg's NULL STATE
   beside its boolean, or bar-count masquerades as "not topped". Additive stamp with a
   MUTATION-TESTED byte-identity guard on the gate verdict (the store PR's fence forbade
   touching a scored-gate module; PR-1 does it with the test that proves the gate
   unchanged and proves the test can fail).
3. **Hub typed decomposition columns** (§5.2): `hub_edge_remaining`, `hub_lifecycle`,
   `hub_leading_gap`, `hub_isolated`, `hub_governor_trust`, `hub_contradictions` — the
   hub state is currently snapshot-only; without PIT accrual the Hub can never earn
   conditional authority under its own integration law.
4. **Board-row coverage repairs before any training claim** (§6.4): diagnose why
   `insider__absent` and `factor__absent` read 100% on the board cross-section (absence
   semantics vs data gap) and why the theme payload reaches only 27% of board-adjacent
   store rows vs 8/71 chips on the board itself; fix or document — a router trained on
   absence learns the absence.
5. **Verify the grades store's first maturation lands** (~2026-08-24 for v1 stamps,
   ~08-27 for v2; §6.1) and that `priority_score_scorecard` flips `available: true` —
   this is the champion's first-ever graded read and the arena's clock-start.
6. **`turnover_pctile_60d`** — data-blocked debt due to self-heal ~mid-Aug; verify it
   started populating, else escalate the volume-cache depth issue.
7. **Store/ledger reconciliation receipt** (§6.7.5): a nightly one-line check that the
   candidates store's buy lane and the snapshot's buy lane agree, with disagreements
   printed (`::warning`) rather than discovered at study time.
8. **Not gaps — disclosed warming/deferrals, do not "fix":** options-state columns at
   9–12% (store-gated coverage), tape-flow columns ~2% (weekly per-root cadence, first
   non-null ~Oct), `opt_iv_rank_252` (deferred by ruling A9), `terminal_state_clean15_126`
   (matures ~Jan 2027), foresight numeric confirmation (all stages currently
   text/fingerprint variants — disclose, per roadmap §4.2).
9. **LER `entry_event.v1` accrual** — owned by #5578 (its PR-2); this program consumes
   from first row and does not duplicate the store.

---

## §14 Implementation sequence PR-1→N (deliverable 11)

| PR | Content | Tier | Depends on |
|---|---|---|---|
| **PR-1a** | **Unconditional GO half:** the §13 accrual columns start stamping (schema-union, zero authority); §13.0 accrual-restoration verified (or executed if the chip wasn't picked up); `families.yml` committed (memberships + `pit_status` + coverage floors + staleness); arena harness SKELETON (label builder over the grades stores, fold machinery with the §9.2 refusal rule) | display-tier telemetry + research scaffolding | this PR merged |
| **PR-1b** | **Held half — lands only after PR-1a and the §8.7 preconditions are coded:** G0/G0′/G1/G2/G3/G4 + C1 raced on frames 2–3 (§8.5); report stamped `counterfactual_replay: true`, `horizons_available: [5,10,21]`, explicitly **non-promotion-bearing**; §8.3 metric table + §8.7 power/distance-to-power table frozen as JSON + doc | research | PR-1a |
| **PR-2** | C2 regularized family stack; redundancy matrices (correlation + conditional-MI estimates) published per family; cross-fitted incremental-vs-Prophet residualization harness; first "what does X add" table with BH-FDR at family grain | research | PR-1b |
| **PR-3** | Nightly shadow-scoring lane: challenger scores stamped to `data/us_prophet_rank/shadow/<model_id>/` (own dir, never the candidates store's scored columns; sibling-file isolation per the snapshots_v2 precedent); the shadow artifact carries an explicit `authority: {can_rank, can_size, can_gate, can_originate_signal, can_escalate} = false` stanza AND a `config/synapse.yml` entry from birth (per §3.1's four-ruling shape); forward race instrumentation + race report in the W0 miss-audit artifact; tripwires named | shadow | PR-2 |
| **PR-4** | C3 date-grouped ranker + ablations vs C2; runs only when frame depth clears the pre-declared floor (≥ 6 months of graded H=21 within one selection era, ≥50 episodes/cell on claimed slices) | research | PR-3 + depth |
| **PR-5** | Router v1 (C4): #5583 fingerprint/epoch interfaces consumed; estimability assessment per axis; name-disjoint validation | research | PR-4 + #5583 W1 interfaces |
| **PR-6** | Multi-head C5 + utility-policy study (λ distribution study; asymmetry heads); UI explanation-contract prototype (display-tier mock, no live surface) | research/display | PR-5 |
| **PR-7** | Promotion prereg for the leading challenger (if any survives §8.6.1–4) + DNR row amendments (§12) + operator/CEO adjudication packet | prereg | evidence |

Each PR is one session-chain wave; each updates the WS record + handoff. Nothing in the
sequence touches the live rank path until PR-7's adjudication says so.

## §15 GO/NO-GO recommendation for PR-1

**GO for PR-1a, unconditionally** — accrual clocks, accrual restoration, the family
registry, and the harness skeleton. The blocking risk is not modeling risk — it is
measurement debt: every week the §13 columns do not stamp is a week the
conditional-evidence questions stay unanswerable (the Eval OS sitrep's closing law).

**PR-1b (the baseline race) is GO only in its narrowed form**: counterfactual-replay
labelled, non-promotion-bearing, at the available horizons, with the §8.7 power table
beside it — a race on a replay against a never-graded champion, at horizons that are 50%
absent, is a calibration exercise and must say so. The adversarial review (§17) is the
source of this narrowing, and it is right: the cheapest world-class move available today
is to make the estate's evidence *joinable and graded* under frozen rules; the fancy
model earns its place later or not at all.

## §16 Required adversarial attacks (run before freeze; verdicts in §17)

1 leakage · 2 outcome audition · 3 correlated-evidence double-count · 4 nonstationarity/
regime dependence · 5 small-N expert weights · 6 survivorship · 7 sparse historical alt
data · 8 leaderboard overfitting · 9 top-K objective hacking · 10 missing/stale input
behavior · 11 score opacity · 12 collision with Prophet/LER/Identity programs · 13
resurrection of killed constructions under renamed features · 14 simpler-model
explanation · 15 does "better score" actually improve what the operator would have seen.

## §17 Adversarial review record (deliverable 13)

Independent adversarial review run 2026-08-14 (opus reviewer, the §16 attack list,
receipts spot-checked against code/data, sibling contracts verified on their branches).
Verdict on the draft: **11 BLOCKERS, 4 ADVISORIES, 10 receipt errors; "would not freeze
as written — conditions."** Every blocker and every receipt error was resolved in THIS
document before merge; dispositions:

| # | Attack | Draft verdict | Resolution (all landed in this PR) |
|---|---|---|---|
| 1 | Leakage | BLOCKER | §9.1 rewritten: joins on the store's own availability field, derived lags forbidden; §9.1b fold-scoped normalization law added; `pit_status` per member in `families.yml` with hard refusal of non-pit members in backtests (§5.1) |
| 2 | Outcome audition | BLOCKER | All three #5583 Channel-A conditions (capacity budget `p_eff ≤ N/10` printed, name-disjoint OOS, name-permutation null) adopted from **C3 upward** (§9.5); the per-CLASS clause of `DNR:KILL-OUTCOME-AUDITION` confronted by name with the construction distinction and a kill-on-sight rule for audition-shaped routing cells (§12) |
| 3 | Double-count | BLOCKER | One-column-one-family enforced by registry uniqueness test; relay→F3, `ext_z`→F2, theme-heat→F3 single homes; orthogonalized-derivative rule for second hypotheses; family budgets binding at every rung C1–C5 (§5.1, §10.6) |
| 4 | Nonstationarity | ADVISORY | Era treatment fixed as STRATA with the fragmentation cost named; §8.6.3's era half marked honestly unsatisfiable until a second graded era exists (§7, §8.6.3) |
| 5 | Small-N | BLOCKER | Minimum-usable-fold rule registered (≥60 train / ≥10 test dates, harness refuses); PR-1 split into 1a/1b with 1b non-promotion-bearing; no basing-class claim before H=63 grades exist (§9.2, §14, §8.6.4) |
| 6 | Survivorship | ADVISORY | Frames pre-labelled (frame 3 `survivorship_biased: true` now); flagged frames barred from promotion claims (§8.5, §8.6.4b, §9.6) |
| 7 | Sparse alt data | BLOCKER | Coverage floors declared in the registry (default 0.50, per-family overrides); below-floor families abstain AND may not be reported on; train-vs-serve coverage diff mandatory with a <50% default exclusion; `insider_cluster` named as a train/serve skew and excluded until the collector heals (§5.1, §8.5.2) |
| 8 | Leaderboard overfitting | BLOCKER | One primary tuple per rung; FDR over model×metric×horizon; slices exploratory and promotion-barred; registered integer comparison count; §8.7 power/MDE table published (detectable ≈ +10pp today; gate non-decorative at ≥60 graded dates / ≥50 top-K episodes) |
| 9 | Top-K hacking | BLOCKER | Primaries computed on the DEPLOYED composition; identical candidate sets across rungs (abstention via Confidence only); beta/vol/ADV/sector-Herfindahl beside every primary; sector-concentration non-inferiority; beta/size/vol-neutralized survival requirement (§8.3) |
| 10 | Missing/stale inputs | BLOCKER | O6 Confidence-calibration outcome defined (band coverage per confidence decile); Confidence display-only until O6 reads; abstention mechanized as first-class missingness indicators + per-family `max_staleness_sessions` (§7 O6) |
| 11 | Score opacity | ADVISORY | Attribution fully specified: family-aggregated interventional TreeSHAP, fixed background, calibrated-head target (never ranker margin), family-level only, registered stability gate (§10.5) |
| 12 | Program collisions | ADVISORY | O4 rival stand-in WITHDRAWN (Entry head deferred until LER grades exist); LER outcome vocabulary corrected; §12.4 quote's dropped parenthetical restored; "reserved twice" headline corrected to the accurate boundary statement; rung-id disambiguation added (§7 O4, §11) |
| 13 | Killed-construction resurrection | BLOCKER | The two row amendments LANDED IN THIS PR with regenerated blocklists (deferring them would have left PR-1 unlawful under §1's no-phase-0 heading); the self-exemption sentence deleted; the Amendment-2 precedent reading corrected (form, not substance); eight additional rows dispositioned by name (§12) |
| 14 | Simpler-model explanation | BLOCKER | Ladder law rewritten: per-increment CI+FDR significance vs the BEST simpler rung, +3pp registered minimum, simpler-wins tie rule; champion-repair baselines G3 (edge sign-flipped) and G4 (edge removed) added before any result exists (§8.1) |
| 15 | Operator value | BLOCKER | G0′ (the actually-published order) added as mandatory baseline; all primaries on the deployed stage/veto composition; featured-shelf precision/loser-rate co-primary; plan-origination delta report; pure-score metrics demoted to diagnostics (§8.1, §8.3) |

Receipt errors: all 10 corrected in place (ZERO_SCORE_AUTHORITY line cluster §3;
`featured_extra` :1373 dropped; scorecard module → `engine/prophet_miss_audit.py:1507`;
grades-charter quote → :88 paraphrase; corr comment :1475; confluence internals
:504-507 + the `macd_bear` NaN fail-open finding folded into §13.2; §12.4 parenthetical;
stale `us_prophet_v1` literal in `build_prophet.py:2185/:2192` logged in §2 and routed
to PR-1a). Agent OS records: `blast_radius` raised to `user_facing` (w7 changes the live
board), `owns_paths` trimmed to in-repo paths, DEC evidence now cites the commissioning
artifact. The reviewer's freeze conditions (1)–(10) are exactly the §17 table's landed
resolutions; the arena is frozen WITH them, not despite them.

---

# §18 — CHAIRMAN OVERRIDE, 2026-08-15: C1 IS THE CANONICAL US RANKER

**This section changes the program's central sequencing rule. It is dated, it names
what it supersedes, and it deletes nothing.** Every promotion-gate paragraph above
remains the historical record of what this program committed to before the override,
and §8's gate stays binding for everything the override does not name.

## §18.1 What the override says

The Chairman ruled on 2026-08-15 that the deterministic **C1 evidence-family fusion**
replaces `us_prophet_v2` as the canonical US board ranker **now**, without waiting for
the w7 promotion adjudication and without waiting for forward outcomes. The exact
pre-change v2 scorer is frozen and continues running with zero authority as
`us_prophet_v2_shadow`.

Shipped as `us_prophet_v3` (`engine/us_board_rank.py`, `engine/us_prophet_fusion.py`).

## §18.2 What is SUPERSEDED — the old language, preserved

Three commitments made above are overridden **for the rank path only**. They are quoted
here rather than edited in place, because a program that rewrites its own prior position
cannot be audited:

| Where | The prior commitment | Status |
|---|---|---|
| WS record `objective:` | "a promotion gate that the current `us_prophet_v2` champion must lose before any live ranking change ships" | **SUPERSEDED 2026-08-15** by Chairman override. Still binding for C2–C5 and every other rung. |
| WS `Scope boundary` | "Live rank path untouched until w7's adjudication." | **SUPERSEDED 2026-08-15.** The live rank path is C1 as of this PR. |
| §8 promotion gate | The champion/challenger arena decides what ships | **NARROWED, not repealed.** It no longer gates C1's adoption. It still gates every rung above C1 and every claim of forward predictive alpha. |

The override is a **product decision about which order to publish**, taken on the
strength of the glass-box construction and a visual acceptance review of the resulting
board. It is **not** a finding that C1 beat the champion on outcomes, and no artifact,
receipt or user-facing surface may say otherwise. `FUSION_SCORE_KIND` carries that
limit into the published artifact verbatim.

## §18.3 What did NOT change, deliberately

* **Selection.** Population, raw signal gate, admissible entry statuses, stage logic,
  execution safeguards, featured shortfalls, earnings/extension checks and caps are
  untouched. The same names are admitted on the same evidence.
* **`SELECTION_ERA`.** Still `anticipation-v1-2026-08-08`. The era names the SELECTION
  regime; a valuation/ordering change explicitly does not reset it, and bumping it here
  would restart the H=63 episode clock and re-create the unsatisfiable-gate trap the
  era's own ruling exists to prevent. The rank change is fenced by `BOARD_DEFINITION`,
  which is the fence built for it.
* **No C2.** PR-2 (#5700) established that C2 has **no lawful real-data folds** and
  **zero fitted coefficients**; 67 more graded dates are needed. Nothing here fits C2,
  relaxes §9.2's fold law, or manufactures a weight. C1 remains equal-weight by
  construction, which is exactly why it was adoptable without a fit.
* **The stage hierarchy.** The canonical order is `(stage_rank, −fusion_score, ticker)`.
  Entry/timing still decides whether and where a name is actionable; fusion decides only
  which interesting name rises inside that actionable state.

## §18.4 The prospective floor evaluation (the #5700 carry-forward, now implemented)

PR-2 registered the variance-floor amendment and explicitly left its **as-of-night** form
unimplemented, carrying it to PR-3. Production cannot use a whole-history coverage
decision — tonight's ranker would be consulting a member's coverage on nights that have
not happened — so the prospective form is implemented here, on both axes:

* **Presence**: share of TONIGHT's pool with a non-null oriented value ≥ 0.50.
* **Variance**: the registered rule (`min_distinct_values_per_date: 2`,
  `min_dates_with_variation_share: 0.50`) evaluated on a one-date frame, which collapses
  without loss to *a member votes tonight iff tonight's pool holds ≥ 2 distinct non-null
  oriented values for it*. No threshold was re-chosen and the floor was not tuned.
* **A date that cannot carry variation is excluded from the denominator, not counted as
  a failure.** A pool of one row is degenerate for every member; counting it would
  refuse the whole plane and stamp a legitimately tiny board as a degraded one.

Measured consequence, first live pool (2026-08-13, 69 buy rows): 7 of 8 members vote and
F1/F2/F4/F5/F8 are active. Under PR-1b's **whole-frame** floor the same registry admitted
only 6 members and F1 was absent (`tier_cascade` coverage 0.25 across the 24-date frame
vs ~1.00 on a live buy pool). The two frames genuinely disagree, which is the whole
reason the prospective form had to exist before adoption.

## §18.5 Honest limits of the shipped ranker

Named here because the acceptance artifact measures them and a reader should not have to
find them:

1. **Family count is not evidence count.** On the first live pool, `F8` handed 99% of
   rows the identical contribution and `F4` 97%. Both cleared the floors legitimately (a
   sparse-but-variable event flag is *meant* to pass — that is the registered acceptance
   test, and re-tuning the floor against this observation is forbidden by PR-2's
   `do_not_redo`). The practical consequence is that today's ordering work is done
   mostly by **F2**, then **F1** and **F5**. `research/prophet_fusion/
   FUSION_BOARD_COMPARISON.md` publishes the separation table every run.
2. **`insider_cluster` is serving-dead** (collector stopped at 2026q1). It is not
   pre-excluded; the variance floor stands it down on any night it is constant, and says
   so in the receipt.
3. **`gex_confirm_verdict` dropped on presence** (0.46 on the first live pool). F5 still
   votes through its other members.
4. **No forward evidence exists for this ranker.** The first `us_prophet_v3` grade
   matures at H=10 roughly ten sessions after the first fusion-ranked night.

## §18.6 Degradation, and why it changes the stamp

If the fusion plane cannot be built on a night, the board publishes under
`us_prophet_v2_fallback` with a `prophet.degradation` receipt naming the cause — it does
**not** quietly fall back inside the canonical stamp. The artifact's `rank_by` /
`board_definition`, the candidate-store stamp and the pool block all read the definition
the ROWS carry (`us_board_rank.published_definition`), never the module constant, so a
degraded night can never pool with a canonical one in any forward ledger.

## §18.7 What w3–w7 become

Forward arena work **continues unchanged as measurement**. It is no longer the production
blocker for C1; it is what will decide C2–C5 and any future claim of predictive alpha.
`us_prophet_v2_shadow` supplies the champion side of that race prospectively, from the
first night this ships.
