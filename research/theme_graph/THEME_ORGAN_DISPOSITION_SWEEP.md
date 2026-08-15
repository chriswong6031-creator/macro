# GMI Theme Graph — Theme-Organ Disposition Sweep (W1a, 2026-08-11)

Purpose: make the no-parallel-organ gate (masterplan `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §0 G0.3) **enforceable against the full roster** — a per-organ ruling on what GMI may do with each existing theme/theme-adjacent module. The masterplan's §2.1 estimated "~25 modules"; this sweep censused **42 with full rows (+4 flagged in passing)**. Every future GMI wave PR must cite this doc when it touches or consumes any organ listed here; an organ not listed is out of bounds until a sweep addendum rows it.

Method & provenance: two independent censuses (snapshot-machinery; roster/synapse/consumers) run 2026-08-11 against origin/main, verified by grep/`git log` — facts from census, dispositions adjudicated in the program main loop. Synapse claims were checked against `config/synapse.yml` by both module-name AND artifact-key AND fence-text greps (keys are hyphenated; fences can live under a different entry than the module — see F1).

## Disposition vocabulary (rulings, binding on GMI waves)

- **CONSUME** — GMI may read the organ's OUTPUT as evidence/legs via the §5 contracts. Never modifies the organ; inherits the organ's own fences verbatim (a no-composite fence on a leg binds any GMI assembly of that leg). R-TIL-9: GMI assembles, never re-scores.
- **EXTEND (Wn)** — a chartered GMI wave extends this organ *through its owner's pipeline* (the only lawful write path). Scope limited to the named wave.
- **FENCE-OFF** — GMI neither feeds nor consumes it, with the reason stated (ordering path, LLM origination, retired).
- **DORMANT** — no production caller today; not a lawful GMI dependency until the owner revives and wires it. GMI never builds on an unwired organ (it has no live tape to grade against).

## Disposition table

| # | Module | Territory owner | Synapse status (verified) | Disposition | Binding condition |
|---|---|---|---|---|---|
| 1 | `engine/theme_scoring.py` | US theme analytics | No own entry; embeds into `site-baskets-json` (display, `scored_path_surfaces:[board_ordering]`) | **CONSUME** | W3 ThemeState reads its labels/scores as INPUT legs only. Its artifact is the roster's ONLY non-empty scored-path surface — GMI must never feed anything upstream of `theme_scoring` (would touch board_ordering). |
| 2 | `engine/theme_flow_rollup.py` | US theme analytics | Not registered | **DORMANT** | Sole caller is a research phase-0 script; no production tape. Owner revives first if wanted. |
| 3 | `engine/theme_crowding.py` | US theme analytics | Not registered (named in `great-company-trap` notes) | **CONSUME** | Down-size-only asymmetric texture; GMI may surface it as a leg but never invert it into a positive signal. |
| 4 | `engine/group_flow.py` | Group Reads | `site-basket-flow` (display, tactical_entry) | **CONSUME** | Via §5.1 Group Reads contract exactly; GMI never recomputes flow. |
| 5 | `engine/theme_tape.py` | US theme analytics | Not registered (pure join fn) | **CONSUME** | W5/W6 may cite its reconciled heat reads; join logic stays put. |
| 6 | `engine/themes_heatmap.py` + `finviz_themes/` | US taxonomy | Not registered; finviz extraction is one-shot 2026-06-27, zero builder | **CONSUME (era-labeled)** | W1b may use the Finviz map as crosswalk evidence ONLY with `as_of: 2026-06-27` era labels (G0.2); staleness disclosed wherever cited. |
| 7 | `engine/theme_discovery.py` | US theme discovery | Not registered (cited in `neuralweb-discovery-confluence` notes) | **CONSUME** | Its human-curated-in candidate pattern is the G0.6 template GMI taxonomy proposals must follow; GMI adds no second discovery radar. |
| 8 | `engine/theme_emergence.py` | Thematic Foresight Desk (TIL) | Not registered; writes `data/theme_emergence/log.jsonl` | **CONSUME** | Bottleneck-discovery evidence for edges (W4 SUPPLIES/ENABLES candidates), citation-only. |
| 9 | `engine/theme_fingerprint.py` | TIL W5a | Not registered (folds into `bottleneck.py`) | **CONSUME** | XBRL physical fingerprints = W4 edge evidence class; reuse, never re-extract. |
| 10 | `engine/company_theme_exposure/` (pkg) | Company exposure sidecar | Not in synapse; internal `AUTHORITY="context_only"` contract | **EXTEND (W2)** | Chartered §2.6.3: W2 extends THIS organ to three-axis/cross-market/edge-attached form through its own contracts. No parallel exposure organ, ever. |
| 11 | `engine/narrative_rotation.py` | Allocation brain | **No entry of any kind**; output lands in `site-allocation` (display, `scored_path_surfaces:[]`, owner `engine-fix`) | **FENCE-OFF** | GMI never feeds `allocate()`/`rank_themes()` or any ordering path (G0.3, G0.11) and never consumes its ordering output as graph evidence (consuming a ranker's ordering launders a rank into the graph). See F1 for the corrected fence citation. |
| 12 | `engine/theme_validation.py` | Allocation brain (overlay) | Not registered; sole consumer is `narrative_rotation` (mutates its in-memory ranks) | **FENCE-OFF** | Same fence as #11 — it is narrative_rotation's tie-break overlay; touching it is touching the ordering path. |
| 13 | `engine/theme_catalyst_binder.py` | US theme analytics | Not registered as producer | **DORMANT** | Orphan: zero production callers (built for a baskets.json catalyst field never wired). Owner decision to revive; noted F3. |
| 14 | `engine/theme_context.py` | Theme context producer | Not registered; own `data/` writes | **CONSUME** (W6 extend-candidate) | Today: read `theme_context.v1` as packet context. W6 may charter an extension for the THEMES packet block — separate ruling then. |
| 15 | `engine/theme_warn.py` | TIL leg (WARN velocity) | **Not registered** despite attempting a runtime synapse sidecar; in-file fence: never fold into `fused_obs_z` | **CONSUME** | Leg for W3 ThemeState; fence inherited verbatim. Registration drift noted F4 (owner's to fix). |
| 16 | `engine/theme_alerts.py` | US theme alerting | Not registered; writes `data/themes/alerts.jsonl` | **CONSUME** | Alert events = evidence rows only. GMI emits NO theme alerts of its own (owner keeps alerting; G0.5 forward-claim law). |
| 17 | `engine/theme_activity.py` | Divergence Radar (TIL) | Consumer of `altdata-feed`; no producer entry | **CONSUME** | `fused_obs_z` belongs to radar's IC harness — GMI reads it as a leg, never re-fuses (in-file fence family). |
| 18 | `engine/theme_adoption.py` | TIL W9 | `site-github-adoption` (display, all may_* false) | **CONSUME** | Named leg. |
| 19 | `engine/theme_downside_rs.py` | US theme analytics | Not registered | **DORMANT** | Orphan: zero callers anywhere. Noted F3. |
| 20 | `engine/theme_extension.py` | US theme analytics | Not registered | **CONSUME** | ATR "too hot" texture leg; display idiom preserved. |
| 21 | `engine/theme_revisions.py` | TIL T4 | Not registered | **CONSUME** | Revision-breadth leg. |
| 22 | `engine/theme_hiring.py` | TIL W7 | `hiring-velocity` + `site-hiring-intent` (display); fence: cert_velocity_z never into `fused_obs_z` | **CONSUME** | Named leg; fence inherited. `site-hiring-intent` has `consumers: []` — dormant output noted F5. |
| 23 | `engine/theme_trade_flows.py` | TIL W8 | 2 artifacts (display); fence: no composite across themes | **CONSUME** | Named leg; no-composite fence binds GMI assemblies. |
| 24 | `engine/theme_clinical.py` | TIL W10 | 2 artifacts (display); fence: never into `fused_obs_z` | **CONSUME** | Named leg. |
| 25 | `engine/theme_options_witness.py` | TIL W11 | 2 artifacts (display); fences: hazard-only, never bullish, positioning fusion ILLEGAL (NEXTL-U13) | **CONSUME** | Named leg; hazard framing preserved verbatim in any GMI surface. |
| 26 | `engine/theme_placebo.py` | TIL W6 grading | `theme-placebo-tape` (**shadow**; producer `scripts/grade_thematic.py`) | **EXTEND (W3)** | W3 consequence-window grading extends the TIL W6 pack through `grade_thematic.py`. R-TIL-6: every GMI hit-rate claim prints as EXCESS over this tape. |
| 27 | `engine/foresight_leadlag.py` | TIL W6 grading | `foresight-earliness-grades` (display; producer `grade_thematic.py`) | **EXTEND (W3)** | Same pack; earliness grading is the model for GMI expectation grading. |
| 28 | `engine/qledger_falsifier.py` | TIL W6 grading | `qledger-falsifier-evaluations` (**shadow**) | **EXTEND (W3)** | Same pack; falsifier auto-evaluation reused, never duplicated. |
| 29 | `engine/baskets.py` (+ `scripts/build_baskets.py`) | US baskets | `site-baskets-json` (display, `scored_path_surfaces:[board_ordering]`) | **EXTEND (W1a)** → CONSUME | W1a adds `--snapshot` membership side-car only (owner pipeline, additive). Thereafter membership is consumed read-only. |
| 30 | `engine/baskets_china.py` (+ `scripts/build_baskets_china_ths.py`) | CN baskets (china_*) | No own producer entry (known_extra_writers footnote under `site-baskets-json`) | **EXTEND (W1a)** → CONSUME | W1a revives the THS snapshot cadence through the owner's asia-lane pipeline. |
| 31 | `engine/basket_membership_pit.py` | CN baskets (china_*) | Data-plane module (not a bus artifact) | **EXTEND (W1a)** | W1a adds `SUITE_US` + parquet continuity + cadence stamps. Column set frozen; append-only preserved. |
| 32 | `collectors/china_ths_concepts.py` + `scripts/scrape_ths_concepts.py` + `scripts/seed_china_ths_baskets.py` | CN collectors (china_*) | Collector (not a bus artifact) | **EXTEND (W1a)** | Weekly receipted scrape wiring; `ThsTruncated` complete-or-fail preserved and formalized into receipt artifacts (G0.4). |
| 33 | `engine/cn_theme_tape.py` | CN themes | Not registered (folds into china dashboard) | **CONSUME** | W5 sensorium context; heat × Prophet why-not reads cited, never recomputed. |
| 34 | `engine/china_narrative_radar.py` (masterplan §2.1 called it `narrative_radar.py` — name corrected, F2) | CN themes | Not registered | **CONSUME** | CN narrative surface; W5 context only. |
| 35 | `engine/china_narrative_tags.py` | CN themes | Not registered | **CONSUME** | Per-name heat tags as evidence rows. |
| 36 | `engine/hk_narrative.py` | HK (china_* family) | Not registered | **CONSUME** | GDELT attention-shock context for regional legs. |
| 37 | `engine/thematic_desk.py` | LLM desk (QI) | `thematic-desk-theses` (**shadow**, POOL_DESKS) | **FENCE-OFF (as evidence)** | G0.6: LLM-originated theses never become graph evidence, edges, or state inputs. Coexists as a display neighbor; GMI cites only its *graded outcomes* via the qledger pack, never its live theses. |
| 38 | `engine/narrative_brain.py` | LLM desk | `site-narrative-brain` (display) | **FENCE-OFF (as evidence)** | Same G0.6 ruling as #37. |
| 39 | `engine/narrative_emergence.py` | US theme discovery | No own entry (named in `theme-state` notes) | **CONSUME** | Forming-narratives read as candidate context; ratification stays human (G0.6). |
| 40 | `engine/narrative_crossmarket.py` | Cross-market | Not registered | **CONSUME** | The closest existing cross-market read: W4's TRANSLATES_TO pilot must reconcile with it before shipping any cross-market edge surface (no parallel cross-market organ). |
| 41 | `engine/narrative_regime.py` | Retired family | Not registered; self-declared "FAMILY RETIRED", gate_multiplier permanently no-op | **FENCE-OFF (retired)** | Do not consume, do not revive. Display banner only, owner's museum piece. |
| 42 | `engine/qledger.py` + `engine/qledger_ui.py` | Universal Scoreboard (QI) | `qledger-claims` + `site-qledger-track-record` (**shadow**) | **CONSUME / COORDINATE (W3)** | GMI's expectation ledger must not duplicate the Universal Scoreboard. W3's charter decides the ledger home WITH the QI owner; until that ruling, no GMI claims ledger exists. |

**Flagged in passing (not rowed; owners' territory, GMI consumes normally through existing contracts):** `engine/china_basket_spine.py` (identifier-join library — W1b will use as a library), `engine/china_basket_turn.py` / `engine/us_basket_turn.py` (lifecycle state machines, registered `china-basket-turn-cn` / `us-basket-turn`; their states are lawful W3 legs; `china-basket-turn-cn` carries the FT-R1 fence quoted in F1), `engine/earnings_narrative/` (Group Reads earnings-evidence territory, consumed via §5.1).

## Findings (corrections + drift, recorded for the masterplan)

- **F1 — G0.3 fence citation corrected.** The fence text "Never reorders theme_scoring recos" exists verbatim in `config/synapse.yml` but belongs to the **`china-basket-turn-cn`** entry (owner `china-alpha`, FT-R1 note) — NOT to `narrative_rotation`, which has no synapse entry of any kind (its output artifact `site-allocation` is registered display-tier, `scored_path_surfaces: []`, and its own docstring declares "PURE/additive (never raise into a build)" but no recos fence). The masterplan G0.3 line previously attributed the fence to `narrative_rotation` at `synapse.yml:3227` — a line-number citation of the exact class the DNR citation law bans. Corrected in the masterplan this wave: the prohibition (GMI never feeds `narrative_rotation.allocate()`/`rank_themes()` or any ordering path, never consumes its ordering as evidence) now stands on the charter's own authority (G0.3 + G0.11), with `china-basket-turn-cn`'s FT-R1 cited by entry key as the house fence idiom for theme-ordering-adjacent artifacts.
- **F2 — Roster corrections.** True roster = 42 modules (this doc) vs §2.1's "~25": 10 theme-adjacent modules were missing (`thematic_desk`, `narrative_brain`, `narrative_emergence`, `narrative_crossmarket`, `narrative_flare`, `narrative_regime`, `china_narrative_tags`, `hk_narrative`, `qledger`, `qledger_ui`) plus 4 flagged. Name fix: §2.1's `narrative_radar.py` does not exist — the module is `china_narrative_radar.py`. (`narrative_flare.py` — per-ticker narrative witness organ, registered `narrative-first-coverage`/`stock-narrative-flares` — rows with the CONSUME family: per-ticker witness evidence for W4 edge candidates, fences inherited.)
- **F3 — Three orphaned organs.** `theme_catalyst_binder.py`, `theme_downside_rs.py` (zero callers), `theme_flow_rollup.py` (research-only caller) are built-but-unwired. Ore-law posture: constructions mapped, not killed — they stay DORMANT, owners decide revival; GMI never depends on an unwired organ.
- **F4 — `theme_warn.py` synapse drift.** The module attempts to load/write a synapse sidecar at runtime yet has no registration under any key (`theme_warn`, `warn_velocity`, `data/warn/` all absent). Pre-existing owner-side drift, out of GMI scope; surfaced for the owner program.
- **F5 — Dormant registered output.** `site-hiring-intent` is registered with `consumers: []` ("no in-repo reader yet") — a shipped leg nobody reads. Noted for TIL W7's owner; GMI W3 may become its first consumer, which would close the gap lawfully.

## Enforcement note

A GMI wave PR that touches an organ rowed EXTEND outside its named wave, feeds anything rowed FENCE-OFF, or depends on anything rowed DORMANT is **not done** (G0.3). Waves cite rows as `SWEEP:#<n>` in PR bodies. Additions to the roster (new theme organs shipped by owners after 2026-08-11) require a sweep addendum row before GMI consumes them.

---

## Addendum 1 — W3A re-census (2026-08-14; directive §19)

Method: full per-organ re-verification against `origin/main` @ 2026-08-14 (sonnet census lane +
main-loop adjudication). Methodology caveat that changed results: bare `git log --since=2026-08-11`
parses the date as *that day at the current wall-clock time-of-day* and silently drops same-day
morning commits — this census used explicit `--since="2026-08-11 00:00:00"`, which is how it
caught W1b's own 12:11pm commit as post-sweep drift. Original rows above are unedited (this doc
appends; corrections live here).

### Row corrections

- **#6 `engine/themes_heatmap.py` + `finviz_themes/` — STALE ROW, corrected.** The Finviz
  organ is NOT "one-shot 2026-06-27, zero builder": `scripts/fetch_finviz_themes.py` runs
  NIGHTLY in daily.yml (perf snapshot, lineage #715) with append-only PIT archival since #1213
  (`subsector_perf_history.jsonl` 29 session rows through 2026-08-13; `tree_history.jsonl`
  1 row asof 2026-07-05; session-stamped `asof`). The STRUCTURE remains manual-refresh-only
  (`--refresh-tree` reserved no-op; committed tree = declared source of record, verified
  content-identical to the 2026-06-27 extraction). Synapse: still unregistered (correct as-was).
  **New disposition: EXTEND (W3A) → CONSUME** — W3A implements the reserved `--refresh-tree` as
  a receipted, interlocked, atomic refresh contract in the OWNER collector plus a nightly
  advisory key-drift tripwire; thereafter GMI consumes the tree/PIT tape read-only.
  Blast-radius census for that refresh (consumers of `themes_tree.json`, all current-snapshot
  readers): `scripts/build_themes_heatmap.py`, `scripts/build_subsector_rotation.py` (+ DAG row
  `config/dag.yml:4239`), `scripts/build_oracle_timemachine.py`, `scripts/build_oracle_panel.py`
  (self-declared survivorship warning), `engine/fund_intelligence.py`,
  `engine/special_sits_intel.py`. `tree_history.jsonl` has ZERO readers today (write-only audit
  trail; `engine/subsector_rotation.py:386` explicitly disclaims reading it) — the W3A graph
  materializer becomes its first consumer.
- **#32 THS collector family — W1b condition discharged; cadence live-proof pending.** The
  seeder shape-collision fix named as W1b's entry ticket SHIPPED in `2ad4cbbd6e81` (2026-08-11
  12:11pm, +179 lines: two-sided `classify_snapshot_shape` + `MAX_AUTO_SHRINK=0.5` interlock) —
  7.5h after this sweep's census commit, so the original row predates it. Seeder remains
  deliberately unwired (manual-only, documented in asia-close.yml comments). First scheduled
  weekly scrape: Saturday 2026-08-15 UTC (receipts dir `data/baskets_china_ths/receipts/` is
  created by that first run — it does not exist yet, which is expected, not drift).
- **#10 `company_theme_exposure/` — EXTEND (W2) partially fired, W2 now CONCLUDED.** The probe
  (`scripts/probe_theme_exposure_axes.py`, 2026-08-12, research-only, off every workflow) ran
  against the prereg without touching the production package. Row's future tense is now past:
  W2's verdict (masterplan §11) governs; any production extension of this organ re-charters at
  W4 under the decomposed-annotation constraint. Disposition reverts to **CONSUME** until then.
- **#26/#27/#28 grading pack + #42 qledger — "EXTEND (W3)" now reads "EXTEND (W3B)".** The
  2026-08-14 CEO directive split W3 (masterplan §7); consequence grading is W3B's. No GMI
  contact yet (correct). #42 update: `engine/qledger.py` took 9 commits 2026-08-13→14 under the
  independent eval-os P0/P1 hardening thread (matched-control evidence contract, PIT-consistent
  replay clock, no-pooled-mixed-direction rule) — none GMI-related; the row's coordination
  posture ("W3 charter decides the ledger home WITH the QI owner; until then no GMI claims
  ledger exists") is unchanged and now binds W3B, which must re-read the eval-os state then.

### New rows (roster additions post-2026-08-11 or holes)

| # | Module | Territory owner | Synapse status (verified) | Disposition | Binding condition |
|---|---|---|---|---|---|
| 43 | `engine/group_pulse.py` | Group Reads | Not registered as own producer (writes `site/basketdata/pulse.json` via `build_baskets`) | **CONSUME** | Never rowed in the original table (a sweep hole, not new machinery — it predates the sweep). Consumption is governed by masterplan §5.1 exactly. Post-sweep drift: W-B G0-10 enforcement (#5439, 2026-08-12) added published denominators + `AGREEMENT_MIN_N=4` floor + arc refusal — GMI legs inherit those floors verbatim; and `engine/entry_radar/producers/baskets.py` (2026-08-14) is a new downstream consumer enforcing basket-fact-never-launders-to-single-name, a boundary GMI cohort reads must also respect. |
| 44 | `engine/theme_graph/` + `scripts/build_theme_graph.py` + `scripts/check_theme_graph_contracts.py` + `contracts/theme_graph/` + `config/theme_graph_identity_breaks.yml` | GMI (this program) | `theme-graph-{nodes,edges,evidence}` (display, six-false, `consumers: []`) | **EXTEND (W3A, W3B)** | The program's own spine (W1b, `2ad4cbbd6e81` — postdates the census). W3A extends: `kind=local_theme`, capability columns, rights module, probation queue, guard grammar. `consumers: []` is accurate today — W3C's cohort read becomes the first registered consumer. Identity breaks file gained ratified ABX/GOLD rows via #5632 (owner: baskets repair) — consumed as-is. |
| 45 | `scripts/probe_theme_exposure_axes.py` | GMI W2 (research artifact) | Not a bus artifact | **DORMANT (by design)** | One-shot research probe, zero workflow wiring, writes only `--out-dir`. Never a production dependency; re-runs only under a new prereg (2026-11 / 2027-02 re-probes). |
| 46 | `scripts/scrape_ths_weekly.py` + `contracts/baskets_china_ths/scrape_receipt.v1.schema.json` | CN collectors (china_*) | Collector + receipt contract (not bus artifacts) | **CONSUME** | W1a's own deliverable, shipped with the original sweep commit. GMI consumes receipts/side-cars read-only; the W3A THS concept nodes read `concept_map.json` (asof 2026-06-27) and inherit the weekly cadence's future updates through the owner pipeline. First live proof: Sat 2026-08-15 UTC. |

### Standing note for future waves

Crosswalk fact pinned during this re-census: `config/theme_crosswalk.yml` carries NO
finviz-branded field; `subsector_keys` values are TOP-LEVEL Finviz theme display names
(14 distinct; 0 of the 268 subtheme keys), flowing to `subsector_rotation.json` theme strings.
Any future subtheme-grain Finviz→canonical mapping is a curation act, never a mechanical join
through those names (masterplan §11 2026-08-14; G0.12).
