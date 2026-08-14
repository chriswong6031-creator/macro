# STOCK IDENTITY / EXPERT ROUTING — PR-0 ARCHAEOLOGY MAP

**Program:** Bottom-Up Stock Identity & Expert Routing (commissioned by operator/Sol handoff, 2026-08-13).
**Companion contract:** `research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md` (the frozen research contract; this file is the evidence base).
**Status:** PR-0 — archaeology + research architecture only. No production code, no engine changes, no Prophet/Radar/Terminal behavior change.

Provenance discipline: citations tagged `[radar-wt]` come from the **unmerged** Live Entry Radar PR-0 branch (`worktree-live-entry-radar-95b9ce`, PR #5578) — a frozen proposal awaiting merge, not ratified house law. Everything else cites `origin/main` at `3aca89ac958` (2026-08-13) or the named repo. Census method: five parallel read-only lanes (prior-work, governance/kill-registry, detector taxonomy, interfaces, data substrate) + direct main-loop reads of the Radar contract. `scripts/context_index_query.py` reported `[NOT INDEXED]` for this worktree; lanes fell back to `rg`/`git log` sweeps per CXI-R19's advisory status.

---

## §1. What question each prior program actually tested

The handoff requires, per prior project: (1) question actually tested, (2) reusable artifacts, (3) what was killed and exactly why, (4) whether the rejection falsifies the bottom-up thesis, (5) contracts to respect. Summary table, then detail.

| Program | Question actually tested | Status | Falsifies bottom-up thesis? |
|---|---|---|---|
| Personality-Tailored Timing (PTT) W1 | Per-name **fitting-method** head-to-head: outcome-audition vs structure-derivation | Audition KILLED (two-ruler); structure arm POSITIVE, OPEN | **No — partially affirms it** (see §2) |
| Stock Personality (R-SP*) | Do fixed hand-built personality **categories** shift fire outcomes? | Shipped display-tier; 48-cell compat Phase-0 ALL NULL | No — tested top-down categories, not learned individuals |
| Personality Signal Suite (PSS) | Do hand-engineered per-name **feature timers** work standalone? | 7+1 constructions killed; codex + shadows shipped | No — killed specific feature recipes, not the search space |
| Signal Episode Atlas (SEA) | Same-name/same-class historical episode base rates as **context** | SHIPPED 2026-08-06, display-tier | No — affirms per-name evidence via shrinkage; grouping key still pre-defined |
| Setup-Species | Taxonomy of **signals** (not stocks) + registry/grading infra | Infra shipped; many species falsified individually | No — different axis (signal taxonomy) |
| Entry Intelligence | **Pooled** feature separability on the entry funnel | Active, different altitude | No — explicitly not per-stock |
| Bottom-Confidence | General multi-TF drawdown/durability scorer | Shipped, validated | Neutral — reusable primitive |
| Live Entry Radar (PR-0) | Standardized candidate-entry event discovery + recording | Unmerged PR #5578 | No — reserves this program by name as its downstream |

### 1.1 Personality-Tailored Timing — the load-bearing precedent

`research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md`. The operator's original directive is this program's thesis one generation ago, verbatim: *"different stocks require different uses of indicators … figure out one stock completely … as long as we become best friends with this stock and know all its quirks, we can much better predict what it's going to do"* (`:6-9`).

W1 ran the decisive head-to-head of **fitting methods**:

- **W1a — outcome audition**: in-sample best-of-6-tool grid per name → **noise, killed under BOTH rulers**. FIT-best in TEST top-2: 33.2% vs 33.3% chance under fwd63; 35.0% vs 33.3% under the corrected bottom-picking (timing) ruler (`:207`, `:328`). Registered as `DNR:KILL-OUTCOME-AUDITION` (`research/DO_NOT_REBUILD.md` §2): *"per-name timing-tool selection by in-sample outcome audition is KILLED two-ruler at n=1,300 names / 109,974 TEST signals (zero OOS persistence; per-name 'home rungs' are ruler-dependent — 5/7 defensives flip)"*; *"any audition-derived per-name gate/rank/size anywhere is this row's construction."*
- **W1b — structure tailoring**: derive tool/rung mechanically from bars-only measured structure (swing period, mean-reversion half-life, trend persistence), never peeking at outcomes to select → **the only arm above the random floor, CI-clean on timing metrics**: U_MAE +0.41pp [+0.13, +1.16]; proximity +5.87pp [+3.51, +6.43] vs random (`:321-322`, `:339`). The kill row itself records the carve-out: *"structure-MEASUREMENT tailoring (PTT-W1b reversion-by-scale, S-family at derived rung) stays OPEN and is UPGRADED under the timing ruler."*
- **Class altitude**: vol×trend terciles and the fundamentals archetype both **failed to separate** from global/random (`:214-218`, `:332-335`). W4 (per-class gate profiles) is **UNLICENSED, unconditionally, under both rulers** — the source states it twice with no conditional attached (`:218` "(per-class gate profiles) is UNLICENSED"; `:344` "W4 stays unlicensed" after the ruler swap; correction per adversarial review finding 22 — an earlier draft of this document glossed the unlicensing as conditional, which the source does not support). No formal kill row exists; what remains honestly open is that only *pre-defined* grouping variables were ever tested — grouping **discovery** is untested, and any per-class profile construction (including the masterplan's Channel A) requires its own affirmative demonstration before use (masterplan §2.3, §14.1).

Governing law issued by that program, binding here: **"MEASURE THE STOCK, DON'T AUDITION THE WARDROBE. Indicator settings are DERIVED mechanically from measured structure; historical signal events VALIDATE the derived setting… and never SELECT among a grid"** (`:64-68`).

Reusable: `data/research/ptt_w1_panel.parquet` / `ptt_w1t_panel.parquet` (1,300 names, 109,974 TEST signals); `scripts/research/ptt_w1_persistence_of_fit.py`, `ptt_w1_timing_regrade.py`; the §7 timing-ruler methodology (U_MAE, proximity, td_to_trough, per-metric random-day nulls).

### 1.2 Stock Personality

`research/STOCK_PERSONALITY_MASTERPLAN_BY_FABLE.md` (+ `STOCK_PERSONALITY_SETUP_COMPAT_PHASE0.md`, `STOCK_PERSONALITY_FIELD_GUIDE.md`, operator playbook). Built a **fixed, deterministic closed-set cascade** — 9 chart labels (R-SP4, `engine/path_personality.py`), 5 microstructure labels (R-SP5), reuse of the 13-bucket fundamentals archetype — then tested whether the personality cell **as of the fire date** shifts board/gate fire outcomes vs proper controls across 48 pre-registered cells. Result 2026-07-07: *"No FDR survivors — all null (pre-committed expected outcome; descriptive card unchanged)"* (`SETUP_COMPAT_PHASE0.md:174`). Not a DNR kill — a pre-committed null on those categories at those sample sizes; the forward ledger (`data/stock_personality/forward_ledger.parquet`, clock 2026-12-15) is the open accrual path.

Reusable: `engine/stock_personality.py` (authority header: *"tier=display, confidence_class=descriptive, may_rank/size/gate=False"*, `:20`), `engine/path_personality.py`, `data/research/personality_pit_labels.parquet` (2.1M ticker-days of PIT labels), `data/archetypes/history.parquet`, the Field Guide's measured per-label fingerprint tables. The `setup_compatibility()` function (`engine/stock_personality.py:1056-1109`) — *"DERIVED display only (R-SP18): recomputed, never stored as truth"* — is the seam the Radar contract names as this program's natural describe-side consumer.

Judgment: top-down category→outcome testing. Its null does not touch learn-individual-first; it constrains re-use of those particular label sets as routing keys.

### 1.3 Personality Signal Suite

`research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md`. Downstream of the PTT kill and explicitly constrained by it (§1 `:37-53`). Shipped: per-name measurement codex (`data/personality_timing/codex.parquet`, PR #3460), Prophet tailored-gate **shadow** (`engine/personality_gate_shadow.py`, PR #3583), terminality shadow, W-LAB audit. Killed: W-SIG families F1–F4 (down-vol envelope, overnight/intraday split, residual reset, semivariance asymmetry) and SR1–SR3 (+F4-repair) as standalone entry-timers — `DNR:KILL-PSS-F1..F4`, `KILL-PSS-SR1/SR2/SR3` — with each row explicitly retaining the measurement as a codex descriptor / confluence-candidate input and inviting *"a genuinely new preregistered species"*. W-CONF (multi-family confluence) is **moot** — zero standalone survivors to combine — and the "Router (C20)" concept (tool-selection gate; the nearest ancestor of "expert routing") was consequently never built (`PSS_WSIG_SHORTLIST_BY_FABLE.md:148`, `:286`).

Prospective-only holds RH1/CR1/CD1/AF1 (`DNR:HOLD-PSS-RH1/CR1/CD1/AF1`): frozen constructions, zero authority, one read after maturity floor — do not disturb.

### 1.4 Signal Episode Atlas

`research/SIGNAL_EPISODE_ATLAS_MASTERPLAN_BY_FABLE.md` (shipped 2026-08-06, PRs #4684/#5125). Operator directive: *"stocks are not alike; the same crossover means different things at different depths, levels, timeframes, and on different names/archetypes"* (`:3-7`). Mechanism: frozen event-class taxonomy (grid × direction × depth-pctile × level × washout-length × align) over `engine/stock_events.py` (389,799 events, 700 names) + `engine/event_atlas.py`; per-name evidence enters **only** as an n-weighted EB shrinkage posterior toward archetype → global (`w = n/(n+k)`, k=12) with every component n printed (`:111-114`). Its own legal note: *"SEA is on the lawful side by construction: ONE frozen indicator family + frozen class taxonomy … The name never chooses its indicator"* (`:55-58`). W6 (rates × defensive-archetype) ran and closed ship:false — conditional null, sign-inverted.

Reusable and directly load-bearing here: the event store, the atlas engine, and the shrinkage-with-printed-n receipt pattern. Limitation: grouping/shrinkage key is still the **pre-existing** fundamentals archetype — never a discovered behavioral neighborhood.

### 1.5 Setup-Species, Entry Intelligence, Bottom-Confidence, adjacent organs

- **Setup-Species** (`research/SETUP_SPECIES_MASTERPLAN_BY_FABLE.md`): taxonomy of **signals**, not stocks; the program's registry/ledger/promotion infrastructure (`engine/species_registry.py`, `engine/grading.py`, `engine/qledger.py`, `engine/cohort_metrics.py`, `data/species/registry.json`) is the substrate any new evidence family registers into rather than rebuilds. Its §3.2 "stock archetypes v2" and cohort context reuse GICS/archetype — top-down again.
- **Entry Intelligence** (`research/ENTRY_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`, `research/entry_intel/`): pooled separability across the board's entry funnel — deliberately the opposite altitude. Its `P1_2B_TAXONOMY_EXTENSION_SPEC.md` is the house's fully-worked prereg exemplar (family ID, BH-FDR trial ledger, frozen thresholds, append-only status), reused as a template.
- **Bottom-Confidence** (`research/BOTTOM_CONFIDENCE.md`): shipped, validated, general multi-TF drawdown/durability scorer — a reusable primitive for episode labeling, not evidence either way on per-name routing.
- **Adjacent per-name display organs** (boundaries stated in their own docstrings, per `[radar-wt]` Track B §7): `engine/washout_turn.py` (weekly washout→turn watch, canon math, kill-boundary recorded in charter), `engine/mtf_upturn.py` (TS-R3 K-of-N multi-TF upturn, registered expected-NULL), `engine/basket_turn_cohort.py` (expected-NULL forward meter precedent for humble registration). DRL/price-pressure: reactive cross-sectional shock detector, authority all-false, standing refusal to become an entry system — no construction overlap.
- **Golden Oracle regime-block forensic** (`research/GOLDEN_ORACLE_REGIME_BLOCK_FORENSIC_2026-08-10.md`): diagnostic record — three confluence engines share the "oracle" vocabulary and *"routinely disagree on the same chart"*; not a personality program, but the canonical citation for "UI label ≠ detector identity."

### 1.6 Live Entry Radar (sibling, unmerged)

`[radar-wt] research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md` (PR #5578; W1–W9 all todo; zero engine code). Radar discovers and records standardized candidate-entry events; its §18 Amendment A1.2 (operator-directed, 2026-08-13) is the **direct commissioning boundary for this program**:

- Terminal's entry-event families (raw grey/early-dot; washout-promoted amber EARLY; STARTER awaiting/failed; RE-ENTRY trend-reclaim/block-repair; confirmed BUY/REBUY) plus Radar's C1–C5 are *"candidate experts, not synonyms"* — never flattened into one `entry_signal` boolean.
- Events land in an append-only **`mastermind.entry_event.v1`** store: `event_id, producer, detector_id, family, subtype, stage, quality, context, signal_ts, signal_known_ts, source_identity{source_hash, signal_era, detector_spec_hash}, scored_authority, family_first_available/family_era, field_origin ∈ {emitter_verbatim, radar_derived}` per field, typed promotion/de-dup edges.
- *"Radar does not expand into stock classification, personality modeling, per-stock strategy optimization, or adaptive routing. A separate Stock Identity / Expert Routing program (future; deliberately not created here) will test which event families best localize opportunities per security and identity epoch"* — with explicit notice of `DNR:KILL-OUTCOME-AUDITION` and the structure-measurement carve-out as *"the lawful path."*
- The operator's motivating visual observation (KRUS/MCK/NVDA/REGN/YELP) is recorded there as *"display-tier, not a validated claim — and explicitly weaker than the standing null … a 5-name visual read standing against KILL-OUTCOME-AUDITION's n=1,300 measured null."*

This program adopts that division of labor as its starting interface contract (masterplan §12), noting Radar PR-0 is not yet merged.

---

## §2. Does any prior rejection falsify the bottom-up thesis?

**No prior result falsifies it — but one binds its method hard.** Three findings, stated at their exact scope:

1. **`DNR:KILL-OUTCOME-AUDITION` binds the METHOD, not the thesis.** Per-name selection of timing tools by in-sample outcome ranking has zero OOS persistence at panel scale — **under both a forward-return ruler and a bottom-picking/timing ruler**. The two-ruler scope matters: *switching the ruler to localization does not, by itself, escape this kill.* Any construction where a name's own outcome ranking picks its expert is dead on arrival. What the kill row leaves OPEN, by name, is structure-measurement tailoring: per-name adaptation flowing through measured path structure, validated (not selected) by historical events — the arm that measured CI-clean positive.
2. **The affirmative half already exists.** PTT-W1b is direct, CI-clean evidence that measured per-name structure carries real information for timing-tool assignment (U_MAE +0.41pp, proximity +5.87pp vs random). The bottom-up thesis is not starting from zero; it is the licensed continuation of the one arm that survived.
3. **The grouping question was never tested in the bottom-up direction.** Every prior grouping key was a pre-defined taxonomy (9 chart labels, 5 micro labels, 13 archetypes, GICS sectors, vol×trend terciles) — and none of them separated as a routing variable. A repo-wide sweep found **zero prior attempts** at unsupervised/discovered grouping over measured per-stock structural parameters. "Categories emerge from learned fingerprints" is genuinely untested — the class-altitude nulls constrain the old keys, not discovery itself.

Standing warnings that shape (not falsify) the design: `DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` (the per-family×regime reliability grid died with most axes UNESTIMABLE from coverage, and the interaction 3.8× smaller than the family main effect — check estimability before building the per-security analogue); the Stock Personality 48-cell null (small conditional cells at ~2026-07 sample sizes mostly cannot separate); SEA W6 (a plausible interaction sign-inverted on test). And one process precedent with operator provenance: *"you just going and directly doing backtesting is wasting time and tokens on something that we haven't even developed and haven't studied in depth enough to understand"* (memory: `understanding-before-backtest`, on this exact program family) — the PR sequence must put descriptive understanding before fit grading.

---

## §3. Kill-registry compliance table

Rows this program must confront by name (full text in `research/DO_NOT_REBUILD.md`; scope readings verified against the underlying study docs):

| Key | Scope for this program |
|---|---|
| `DNR:KILL-OUTCOME-AUDITION` | Binding method constraint (§2.1). Any per-name expert selection by own-outcome ranking = this row's construction. Structure-measurement tailoring = the recorded open seam. |
| `DNR:KILL-PSS-F1/F2/F3/F4` (+`-REPAIR`) | Four hand-built standalone per-name timers dead; each measurement retained as codex descriptor / confluence input. Do not re-test them as standalone timers; reading them as fingerprint FEATURES is the retained use. |
| `DNR:KILL-PSS-SR1/SR2/SR3` | Exact stress-response constructions closed; new constructions require fresh prereg. |
| `DNR:HOLD-PSS-RH1/CR1/CD1/AF1` | Frozen prospective charters — do not touch, do not read early. |
| `DNR:KILL-WASHOUT-TURN` | HTF washout-position × turn interaction layered on gate fires, dead (proximity shadow, NC-2). Binds any washout/turn-shaped construction consumed from Radar's C-family; promotion attempts must re-confront it by name. |
| `DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` (+`KILL-REGIME-SCORECARD`, `KILL-COMPOSITE-REGIME-RELIABILITY-MONITOR`) | Family×regime reliability grid dead at the regime axis: interaction ≪ main effect, axes unestimable. Direct analogue warning → mandatory coverage/estimability census before any ticker×epoch×episode×expert cell claims. |
| `DNR:KILL-ONSET-FINGERPRINTS`, `KILL-VOLUME-FINGERPRINTS` | Specific onset/volume fingerprint constructions dead (tautological / onset-bar artifact); volume descriptors display-tier only. Fingerprint feature choices must avoid re-minting these as predictive features. |
| `DNR:KILL-STAGE-WIN-GATE`, `KILL-FRESH-BUY-EDGE`, `KILL-ENTRY-21D-THESIS`, `KILL-PRIMED-DIRECTIONAL-GATE`, `KILL-200DMA-RECLAIM-VETO-FLAT`, `KILL-FRESH-TICKS-WINDOW` | Entry-stack gate/rank constructions dead — none may be resurrected as "routing" outputs. |
| `DNR:KILL-BD4-SPECIES` | BD-4 species parked (sign-reversed). |
| `DNR:KILL-SLOT-PRERESERVATION` | This archaeology census earns **no** hypothesis slots; every downstream hypothesis clears its own gate (≥8 cases + fingerprint + explicit ruling). |
| `DNR:KILL-PROPHET-POP-MERGE`, `KILL-FORCED-CALLS` | No data-lane merge into Prophet's graded board; no un-gauntleted directional calls on signal surfaces. Routing output stays display/shadow-tier until promoted. |
| `DNR:LAW-REVERSION-RULER` | Reversion-capture signals are scored on a reversion ruler (~20-25d time-exit), not the 63d factor apparatus — congruent with this program's localization-first ruler. |
| `DNR:LAW-ERA-SPLIT`, `LAW-TIME-CLUSTERED-CI`, `LAW-FAMILY-CLOSURE`, `LAW-R1M-ESTIMATOR` | Estimator laws: no era-pooled inference across the 2010 break; time-clustered (month-cluster) bootstrap mandatory (ticker-only clustering is anti-conservative); one single-construction kill never closes a family; estimator hygiene. |

---

## §4. Canonical expert taxonomy census

Resolved by a dedicated census lane across both repos (Macro at `origin/main`; `charting-app` read-only). Headline resolution: **UI labels do not map 1:1 to detectors** — the grey dot is one producer with four consumers; "STARTER" is a licensing layer on top of an admission union; "RE-ENTRY" is two unrelated mechanisms; and the grey dot itself has **two parallel implementations** (Macro + Terminal) that may disagree at bucket boundaries.

### 4.1 Mechanism → producer map (entry-relevant families)

| UI label / family | Producer (authoritative) | Authority today | Historical replayability |
|---|---|---|---|
| **Raw grey dot** (anticipation) | `engine/signal_quality.py:159-232` `signal_frame` → `early` column: `stochBullCross(k,d) & min(D,8)<20 & rising 2D RSI-MACD hist (prior CLOSED 2D bar) & (weeklyBull|fromOS) & rsi14<65` on the 3D grid | Display-only (`early_markers[]` in `site/signals/<T>.json`; `signal_gate` `sub="early"` ANTICIPATION, never `take`) | Recomputable (pure function of close); no dedicated ledger |
| **Grey dot, Terminal twin** | `charting-app/signal_layer/confluence_v2.py:351-383` `early_dots` — same construction, independently coded; 2D bucketing = `resample("2B")` vs Macro's absolute-anchor `_tf_grid` (divergence risk, unverified) | Display; capped 40 in model slice | Recomputed per API request; no store. `[radar-wt]` pins G0 on this emitter with locked-spec fallback |
| **Washout-promoted amber EARLY** | Terminal promotion of the dot in washout context (`[radar-wt]` Track A; `bottom_watches[kind="early_dot"]` union) | Display | **Zero history before Terminal `935389d4` 2026-08-11** (`family_first_available`) — prospective-only as a distinct family |
| **STARTER (admission)** | `engine/us_early_turn.py:845-918` `union_admission` (leg A `early_dot` = the grey-dot column; leg B `relaxed_cross` = 3D StochRSI cross, both K,D<20, confirmed by 1D MACD-RSI within 5-10 sessions) + `assess_early_turn` `:1076-1223`: fire = signature ∧ licensing context (basket ∈ {WASHED_OUT,BASING,TURNING} OR leader-pullback ∈ {PULLBACK,RESET_TURN}) → `stage="EARLY"`, `plan_licensed=True`, era `union-admission-v1-2026-08-11` | Display/admission-class — "never touches the scored gate, a tier, or a rank" | Signature recomputable; the **licensing context needs historical basket/leader state** — PIT reconstruction unverified (open question for the fit engine) |
| **STARTER zone lifecycle** (pending/failed/converted) | `engine/prophet_bridge.py:2376-2461` `evaluate_entry_zone`: stance ∈ {accumulate, wait, starter}; zone state ∈ {none, live, filled, expired, converted}; washout-class zone unfilled at expiry **converts** to starter (V-recoveries don't revisit) | Display; plan JSONs immutable | Overlay recomputed nightly from frozen plan + tape; plans are append-only publication records |
| **Confirmed BUY / REBUY** | `engine/signal_quality.py:797-949` `analyze` / `engine/canon.py:446-502` `confluence_signals`: `CB = macdBullCross & recentStochBull(≤8) & (weeklyBull|fromOS) & rsi14<65`; buy-filter = bearish-divergence veto + reclaim-and-hold → take/block/pending | **Scored** (`take` → `signal_gate.TAKE`, Standout boards); validated cut: avg max DD −23.7%→−15.5% (110 held-out) | **STORED**: `data/signal_archive/track_record.parquet` (append-only, key=(ticker,date,type), maturation columns) |
| **T1–T4 confluence cascade** | `engine/confluence_tiers.py:385-620` `cascade`; `ANCHOR_ERA="abs-session-2026-08-06"`, `FRESH_TICKS=2`, `BUYABLE_TIERS=(T1,T2,T3)` | **Scored** — gates Standout boards | Recomputable via `tier_stream()`; T2–T4 per-bar history not separately persisted |
| **RE-ENTRY sense 1 — Door R (re-arm / trend reclaim)** | `engine/prophet_doors.py` Door R: trend intact (above200 ∧ weekly_bull), master cross stale 3–15 ticks, 2D leg re-crosses up on a COMPLETED bucket while 3D StochRSI constructive | Shadow-accrual only, zero production authority | **Prospective-only by charter** — "no historical backfill; every row is a real forward call" |
| **RE-ENTRY sense 2 — reclaim waiver ("block repair")** | `engine/signal_quality.py` `ReclaimWaiver`/`washout_qualifier` (~`:385-514`): a buy whose ONLY failing leg is the 200d reclaim is admitted when the name's basket peer group is washed-out at notch 20 (era `us_prophet_v2`) | Converts block → take (ratified US policy) | Re-derivable — the state artifact is committed nightly |
| **Bottom Watch** | Label read off the cycle ladder (`engine/us_board_rank.py:698-770` `is_bottom_watch`), **not its own detector math**; the Terminal's `bottom_watch` events (LER C5 port target) = `[terminal] confluence_v2` washout context W1∧(W2a∨W2b)∧W3 | Display | Terminal events in artifact; Macro label recomputable |
| **Weekly washout→turn organ** | `engine/washout_turn.py` (per-name weekly-grid confluence, canon math, completed W-FRI bars only; built for the MCD-class miss) | Display-only | **STORED**: `data/washout_turn/ledger.jsonl` (nightly transitions-only) |
| **Turn Watch deck** | `engine/us_turn_watch.py` `compute_deck` — triggers `dot_1d`, `pre_confluence_2d`, `basket_turn`, `leader_reset_turn` | Display, `LANE_FLOOR=5` | No fire ledger; nightly artifact only |
| **GC v2 keeper / recipe / structure legs** | `[terminal] signal_layer/confluence_v2.py::build_v2`: keeper (reclaim-and-hold + bearish-div, take/block/pending), recipe 0-100 (washout 25 + rs_inflection 20 + anti_chase 20 + structure 15 + volume 10 + monthly 10, hard vetoes), structure leg = `rsi_bull_div_40d | macd_hist_bull_div_40d | failed_breakdown_20d/60d | bollinger_reclaim` — **the failed-breakdown/reclaim detector family** | Display/graded, "NEVER a hard gate" (score-not-gate law) | Per-request computation, no persistence located; recipe legs cite `harness/e_factors.py` — **source lab not found in either repo** |
| **ARM/CONFIRM sell stream** | `[terminal] confluence_v2.py:399-487`: ARM = 2D RSI-MACD bear-cross at 3D K/D≥75 OR 3D stoch bear-cross from ≥80; CONFIRM = daily close below last confirmed radius-3 swing low within 15 sessions | Display warnings; CONFIRM fires the user-facing SELL pill | Forward-walked; no store located |
| **Oscillator core (one lineage)** | `[terminal] terminal/lib/pine.ts::FLAGSHIP_PINE` (owner Pine v6) ported at `engine/canon.py` (SMA-seeded RMA, `adjust=False`) — RSI-MACD = `EMA(RSI14,14) − EMA(RSI14,60)`, signal `EMA(·,5)`; StochRSI 14/3/3, bands 80/20 | — | **Two incompatible RSI families live in Macro** (`canon` vs `technicals.rsi` bare-ewm) — indicator-core law (`[radar-wt]` Track B §1): pin ONE named family per module, never mix |
| **Golden-vector conformance oracle** | `engine/canon.py::confluence_signals` → `scripts/export_signal_contracts.py` → `site/factordata/contracts/golden_signals.json`; `[terminal] signal_layer/golden_gate.py::check_symbol` diffs against it | Conformance test, not a signal; currently `pass=False` **by design** (Terminal engine is TV-anchored) | Fixed-window vectors (2015–2024, 3 symbols) |
| **SEA event store** | `engine/stock_events.py` + `engine/event_atlas.py` (§1.4) | Zero authority | **STORED, bar-by-bar replayable**: `data/stock_events/events_backfill.parquet` + `live/YYYY-MM.parquet` (keep-FIRST idempotent, outcomes matured in place) |

### 4.2 Promotion DAG (shared substrates)

- `signal_frame.early` → {grey-dot display; `union_admission` leg; bake-off C2s/C2r/C3; `signal_gate` anticipation tier}. **One producer, four consumers.**
- `signal_quality.analyze`/`_buy_filter` → {BUY/REBUY markers; `signal_gate.gate()` take/pending; `track_record.parquet`; hold-anchor selection}. STARTER's zone conversion is a sibling state machine on the same plan object, not downstream of `analyze()`.
- `confluence_tiers.cascade` is imported (not forked) by `us_turn_watch` and `us_early_turn` — anticipation deck cannot disagree with the slow tier by construction.
- Terminal's `confluence_v2` layer shares **no code** with Macro's engine — same-formula, separately-coded (silent-fork hazard is the standing lesson; parity enforced only at the base-oracle layer via golden vectors, **not** for tiers/STARTER/keeper/recipe/early_dots).

### 4.3 Replayability verdict (drives masterplan §8 expert-fit scope)

- **Historically fit-measurable now (stored or cleanly recomputable):** confirmed BUY/REBUY/SELL/CUT (ledgered + matured); grey dot (recompute, either implementation, era-pinned); T1–T4 (recompute via `tier_stream`); SEA event classes (stored); weekly washout-turn (ledgered from organ ship date; recomputable earlier); reclaim waiver (re-derivable); Terminal bottom-watch events (artifact + locked-spec fallback).
- **Prospective-only (no legitimate history):** washout-promoted amber EARLY as a distinct family (born 2026-08-11); Door R re-arm (charter forbids backfill); Turn Watch deck fires; GC v2 keeper/recipe scores; Radar C1–C2 LIVE-state detectors (minute reconstruction per `[radar-wt]` §5, else live-forward only); anything touching ephemeral lobe nominations.
- **Conditional:** STARTER admission — signature replayable; the basket/leader licensing context requires PIT reconstruction of basket state (unverified; PR-2-equivalent must resolve or classify STARTER-as-licensed prospective-only, while treating its **signature** as replayable).

### 4.4 Census answers

- **A. Where computed:** both repos, two transport models — Macro nightly batch (`site/signals/<T>.json` schema 1.3.0, `site/factordata/*_standouts.json`) and charting-app's own FastAPI backend (`api/main.py`) computing its independent port per request, reading Macro's `data/stocks` deep store directly (`MACRO_REPO` env). The Terminal frontend only renders; no client-side JS math.
- **B. DAG:** §4.2. — **C. Ledgers:** §4.1/§4.3. — **D. Episode stores:** SEA (equity, in-scope); `engine/options_signal_episode.py` + options market-memory episodes (out of scope); `data/vector/reentry_ledger.jsonl` is the **BTC macro-override** re-entry ledger, not the equity RE-ENTRY (do not conflate).
- **E. "Live Entry Radar" / C1–C5:** the literal name exists **only** in the unmerged `[radar-wt]` PR-0 (its C1–C5 arena, §1.6). A shipped `#entry-radar` UI exists in `baskets_china.html.j2:897` — **China basket-grain**, unrelated. Macro's `research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md` defines **C0–C4** research constructions (C2s = "THIS is the operator's grey dot"); research-only IDs, never artifact fields; winners graduated into `union_admission` (C1→`relaxed_cross`, C2→`early_dot`). Stored study episodes: `research/prophet_us_audit/early_admission_bakeoff_episodes.parquet` (240 names, ~2,659 name-years).

### 4.5 Census uncertainties (carried into the masterplan as PR-2-equivalent work items)

1. STARTER→ADD lifecycle: only `STAGE_EARLY` is ever assigned in code; `STAGE_CONFIRMING/CONFIRMED` exist as constants + display copy with no assignment path found — "full BUY becomes the ADD" is stated intent, not wired behavior.
2. No cross-repo parity contract exists for tiers/STARTER/keeper/recipe/early_dots (only base-oracle golden vectors) — Macro-vs-Terminal grey-dot twins may diverge at 2D bucket boundaries (`_tf_grid` vs `resample("2B")`); unverified.
3. GC v2 recipe's cited source lab (`harness/e_factors.py`, `harness/x_exits.py`) not found in either repo.
4. T2–T4 per-bar history not persisted anywhere (recompute-only).
5. Historical basket/leader state availability for STARTER licensing-context replay: unresolved.

---

## §5. Interfaces and authority rails

### 5.1 The three "oracle" engines (never conflate)

Per `research/GOLDEN_ORACLE_REGIME_BLOCK_FORENSIC_2026-08-10.md:19-27`:

| # | Engine | Location | Role |
|---|---|---|---|
| 1 | **Terminal Golden Oracle** | `[terminal] signal_layer/confluence.py` + `confluence_v2.py` → `terminal/public/data/<SYM>.slice.json` | Produces the Terminal chart markers (the operator's visual vocabulary) |
| 2 | Macro buy-filter chain | `engine/signal_quality.py` → `engine/signal_gate.py` → `engine/confluence_tiers.py` | Prophet US/CN/HK gate; independent implementation; **routinely disagrees with #1 on the same chart** |
| 3 | Macro display leaf | `engine/canon.py:421 confluence_signals` | Display-only, feeds `engine/master_brain.py` |

Also unrelated despite the name: `engine/oracle/` = Oracle **Rotation**/Red Queen research package with its own `personality.py` and `episodes.py` and its own gauntlet — a third "personality" and a second "episodes" namespace. See §7 disambiguation.

### 5.2 Prophet consumption seams (current)

- Nightly: `.github/workflows/daily.yml` → `scripts/build_prophet.py` (reads `site/factordata/us_standouts.json`, originates `prophet.trade_plan/v1`, sole nightly ledger advancer; every output `authority_tier='display'`; *"No signal, score, or escalation originates from an LLM in this pipeline"*).
- Intraday: `prophet-live.yml` → `engine/prophet_live/live_states.py` (VPS 5-min; zero `data/` writes).
- Gate chain: `scripts/build_stock_library.py` → `signal_gate` → `confluence_tiers` → `us_standouts.json` → `prophet_bridge.originate_plans`.
- **Per-ticker conditioning today**: `engine/stock_personality.py::setup_compatibility()` (display-only, derived, recomputed never stored) — read by the stock library; **not** imported by any gate/bridge module. `engine/oracle/personality_context.py` is a second, independent display consumer (R-SP19).
- Program-registry seam: `config/mastermind_programs.yml` licenses **`market-timing-intelligence → feeds_context_to → [prophet-us, neural-web]`** while denying it Prophet decision authority (verified at the `market-timing-intelligence` block, `:1976` ff.; an earlier draft's `:938-939` cite pointed at a different program's `consumes_from` — corrected per review finding 23e; cite the program KEY, not line numbers, per house law) — the pre-existing lane this program registers under.
- Mastermind side: `[mastermind] portfolio/prophet_feed.py` reads `site/prophet/index.json` as additive-only discovery (sizes nothing, gates nothing). Boundary audit `research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md` — finding F-09 (authority booleans published false but consumer defaults differ) is the standing precedent for "a new evidence input silently gaining authority it wasn't granted." Read before any cross-repo artifact design.

### 5.3 Authority rails binding a routing layer

- **Constitution** (`engine/neuralweb/constitution.py`): Article 1 — origination ban, `A7_ORIGINATE` unconditionally refused; Article 2 — scored-path perimeter = `config/synapse.yml meta.article2_surfaces` (`alert_triage, board_ordering, top_setups, attention_queue, push_floor`) — any influence on these requires ≥ shadow-with-track-record tier; Article 3 — evidence floors (sample floors, Wilson CI lower-bound lift > 1.25, freshness lapse).
- **Evaluation standards** (`research/MASTERMIND_EVALUATION_STANDARDS.md`): Display → Accruing (`engine/qledger.py` registered claims, pre-declared horizon) → Validated (pre-registered gates at declared horizon on held-out/live-forward). "Validated" language CI-enforced (`scripts/check_validated_claims.py`).
- **Look budgets**: `engine/trial_ledger.py` (`log_trial`, `log_declared_budget`) — the house look-ledger every sweep must register into (RUL-32 precedent).
- **Prereg templates**: `research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md` (shape: provenance → frozen claims → evidence cells → inference → floors → consequence matrix → clock → append-only grading log); `research/entry_intel/P1_2B_TAXONOMY_EXTENSION_SPEC.md` (worked example).
- **Radar path partition** (`[radar-wt]` §16, mirrored here): never touch `engine/entry_signal.py`, `engine/signal_gate.py`, `engine/confluence_tiers.py`, `engine/signal_quality.py`, `engine/prophet_*.py` (WS:PROPHET-US-ENTRY-TIMING territory), `engine/washout_turn.py`, `engine/mtf_upturn.py`; non-interference is mechanical (`git diff --stat` clean on those paths in every PR).

---

## §6. Historical data substrate census

Census note: the census lane read `data/` from the main checkout's materialized store (this worktree is sparse with no `data/` tree); "as of" ≤ 2026-08-12.

### 6.1 Price history planes

| Plane | Universe | Adjustment | Depth | Fit for fingerprints? |
|---|---|---|---|---|
| `data/stocks/*.parquet` | 229 curated US names | TR-adjusted (`auto_adjust=True`) | Deep (KO→1962, 16,236 rows; NVDA→1999) — close/high/low/volume, **no open** | **Yes — primary, with a structural exception**: gap features (masterplan F6) need `open` and are therefore unbuildable on this plane — excluded from the metric block per masterplan §4 law (vi), never masked (review finding 8) |
| `data/baskets/ohlcv/*.parquet` | 2,519 basket names | Adjusted (fetch_basket_ohlcv) | Deep OHLCV; PIT `[added,removed)` membership via `engine/basket_index.py` | **Yes** (KRUS, YELP live here) |
| `data/massive_stock_day/*.parquet` | ~19,133 whole-market | **RAW — no adjustment layer found**; splits uncorrected (NVDA 2021 prints ≈ 828 vs 2026 ≈ 195) | ~2021-07+ only; gappy backfill (471/~1,254 days; `max_missing_run_weekdays: 832`) | **No** for any MA/drawdown/gap math across splits until the downstream `split_adjusted_raw` transform is traced |
| CN adjusted / CN raw / HK | 1,604 / 1,592 / 159 | adjusted vs deliberate raw plane (never mixed) | CN→1991 PoC | Out of v0 scope (§16.8) |
| Delisted | `data/edgar/dead_name_prices.parquet` 415/1,083 names (38.3%), post-2021-07 only, stamped "UPPER BOUND"; `data/breadth/_closes_delisted.parquet` 199 names close-only→1962 | — | — | Partial — disclosure mandatory |

Canonical accessor: `lib/store.py` (`read/last_date/upsert`, outlier-quarantine 8σ). PIT index membership with real join/leave dates: `data/breadth/sp500_pit_membership.parquet` (1,255 rows) + `sp1500_pit_membership.parquet` (3,286 rows) — the survivorship-stratification substrate.

### 6.2 Pilot-name membership facts

MCK, NVDA, REGN, KO, WMT, MCD, GOLD, NEM: in `data/stocks` (deep, adjusted). KRUS, YELP: in `data/baskets/ohlcv` only. BABA, AEM, PAAS, WPM, AG: in `config.yml extra_tickers` (incl. the named Gold-Miners/Silver sleeves at `config.yml:2849/:2869`) and in raw `massive_stock_day`, but **deep TR-adjusted store presence unverified** — a PR-1 data gate. Only KRUS sits outside every curated/index universe mechanism (not S&P1500-eligible, not in `extra_tickers`) while still having deep basket history.

### 6.3 Corporate events, ticker identity, survivorship

- **Earnings**: `data/earnings/earnings.parquet` = forward calendar + trailing ~4 quarters of surprises for 1,364 names — **no deep historical earnings-date archive exists**; earnings-response fingerprint features need new backfill (off-path).
- **Adjustment conventions**: per-name equity stores ship TR-adjusted only; the dual-basis convention (`close` vs `close_price`) exists only in the macro `yahoo` group.
- **Ticker-identity hygiene is a live failure class** (memory TRAP_FAMILIES "Ticker identity"): reused tickers splice a different company's history "born clean" (ECHO/SATS; also SPWR, RPT, CAMP/NP/WOLF, EA); acks silence alarms without migrating downstream ledgers; keep-first tier merges pick dead columns; index-exit ≠ death (172/1,083 "dead" names still trade). Mitigations that exist and must be consulted on every per-ticker join: `config.yml quality.reused_ticker_acks` / `ticker_key_migrations` / `breadth.ticker_fixups`, `config/delisted_symbols.yml` (disclosure ledger, never deletion, with successor tickers), `lib/symbol_aliases.py`, `engine/ledger_identity.py`, `scripts/audit_reused_tickers.py`.

### 6.4 Replay / PIT infrastructure that already exists

- **R1 Rule-Replay rail** (`research/rule_replay/R1_CHARTER.md`, `engine/rule_replay.py`, backing tape `data/replay/replay_boarded.parquet` 146MB + per-year parquets, fire-anchored `episode_id = TICKER_YYYY-Www`): the general, **pre-registration-gated** (content-hash before any run) replay harness over the production fire tape, pooled into `TrialLedger fdr_family='replay'`. Its **vintage-stamp schema** (`price_plane_id, adjustment_mode, universe_as_of, frame, survivorship_biased, coverage_frac, dead_name_coverage_pct, era_law_cohort`) is the house convention every replay study carries. **Law: extend R1 or explicitly justify a parallel harness — never silently duplicate.**
- `engine/provisional_replay.py` — truncate-at-day-D reproduction of live board state (repaint/flicker measurement); general mechanism, audit-born.
- `engine/pit.py` — leak-free vintage accessor, **macro series only**; no equity-price PIT-vintage analog exists (equity stores are nightly-overwritten adjusted planes — vintage discipline for equity replay comes from recomputation + era pinning, not stored vintages).
- One-off backfill pattern (manual host runs, gitignored heavy output, small manifest committed): `backfill_massive_stock_day.py`, `backfill_china_limit_tape.py`, `build_dead_name_prices.py`, `build_stock_personality.py` ("NOT a nightly job").

### 6.5 Per-ticker behavioral stats already computed

- **`engine/path_personality.py`** — causal/PIT-safe-by-construction per-ticker feature library (value at t identical with or without future rows): trend persistence (20/60/126d), slope stability (126d), pullback stats, breakout counts/rates (63d), gap share + event-gap concentration (252d), wick share, reversal half-life, extreme-bar frequency, dollar-ADV, autocorr sign. APIs: `features()` snapshot + `feature_series()` full series. Backfill store: `data/research/personality_pit_labels.parquet` (2.1M ticker-days) via `scripts/build_stock_personality.py` (on-demand CLI).
- `engine/path_risk_signals.py` — Ulcer Index family (drawdown *quality*), NATR, HVR compress/expand, mass bulge.
- `engine/entry_primitives.py` — BBWP, Amihud illiquidity, Corwin-Schultz spread estimator (reused, not copied, by path_personality).
- Efficiency-ratio math exists in several modules (btc_signals, compression_signals, impulse, master_brain, tech_catalog, velocity) but is not wired per-equity; Hurst exists only at theme level. Macro-sensitivity betas per name: `engine/stock_macro_sensitivity.py`; sector-neutral momentum: `engine/residual_alpha.py`.

### 6.6 Compute law

Render budget is constitutional (`HOUSE-U6`, `docs/NEURAL_WEB_CASE_LAW.md:3203-3218`): heavy compute never enters `daily.yml`/`render.yml`/`engine-render.yml`. Sanctioned homes for this program's replay/backfill: a `workflow_dispatch` self-hosted lane with its own concurrency group (the `backfill.yml` `pipeline-batch` pattern, 120min) or manual store-host runs publishing heavy artifacts to R2 with a small committed manifest (`scripts/publish_r2.py` pattern).

---

## §7. Vocabulary disambiguation (mandatory — three collisions already live)

| Term | Existing senses | This program's usage |
|---|---|---|
| **personality** | (1) `engine/stock_personality.py` + R-SP label cascade (market-timing-intelligence); (2) `engine/oracle/personality.py` + `personality_context.py` (Red Queen); (3) the killed `personality_timing_w1`/PSS construction family | **Avoided entirely.** This program says *identity* / *behavioral fingerprint*. |
| **episode** | (1) options-PIT H+60 outcome episodes (`options-pit` lanes); (2) `engine/oracle/episodes.py` (Red Queen); (3) Radar `mastermind.live_entry_episode.v1` (detector-anchored lifecycle) | *Identity episode* = **path-anchored** reversal/reset window from the episode catalog (masterplan §7). Always qualified; store namespaced `data/stock_identity/`. |
| **species** | Setup-Species = taxonomy of signals/setups | Not used for stocks. Discovered stock groupings are called *behavioral neighborhoods*. |
| **oracle / Golden Oracle** | Three engines (§5.1) + `engine/oracle/` rotation package | Only ever cited with its qualified name. |
| **identity (ticker)** | Memory trap cluster "Ticker identity" = symbol-reuse/delisting hygiene (reused tickers, zombie prints, keep-first merges) | Behavioral identity is unrelated; the data layer must still apply the symbol-hygiene traps (masterplan §9). |
| **expert** | Radar A1.2: recorded entry-event families as candidate experts | Adopted verbatim from Radar's contract — an *expert* is a recorded event family with preserved provenance. |

---

## §8. Contracts binding this program (compressed)

1. **Display-tier is free; authority is gauntleted** (`DEC:GAUNTLET-GATES-PROMOTION-NOT-BUILD`). Fingerprints, catalogs, fit tables, SIF artifacts ship display-tier; any rank/size/gate influence requires the full promotion ladder.
2. **No per-name outcome audition** (`DNR:KILL-OUTCOME-AUDITION`); per-name adaptation flows through measured structure; events validate, never select.
3. **Estimator laws**: era-split (2010 break), month-cluster bootstrap, per-name-first aggregation, family closure, honest episode-N.
4. **Coverage before conditioning** (`DNR:KILL-PER-SIGNAL-FAMILY-RELIABILITY` lesson): estimability census precedes any conditional-cell design.
5. **No hypothesis-slot pre-reservation** (`DNR:KILL-SLOT-PRERESERVATION`).
6. **Prophet/Radar path partition** (§5.3) — mechanical clean-diff obligation.
7. **Radar interop**: consume `mastermind.entry_event.v1` (post-merge, post-PR-2); never write into Radar; `family_first_available`/`field_origin` honesty consumed as-is; Radar PR-0 is unmerged — treat as proposed, revalidate at PR-1.
8. **Constitution**: Articles 1–3; LLMs never originate signals/scores/escalations anywhere in this program.
9. **Language law**: no user-facing "validated"; falsifier/refutation language never front-facing; tiers named, never explained.
10. **Understanding before backtest** (operator precedent): descriptive atlas precedes fit grading in the PR sequence.
11. **Agent OS**: workstream + handoff records per `agentos/README.md`; program key resolves in `config/mastermind_programs.yml` (`market-timing-intelligence`, Radar precedent).
12. **Ship loop**: worker-done = commit → push → PR → `merge-on-green` → `ci_handoff.py`; no build wave from PR-0 (explicit operator stop condition).
