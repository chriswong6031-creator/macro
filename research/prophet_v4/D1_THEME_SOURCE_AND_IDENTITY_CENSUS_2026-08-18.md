# PROPHET US V4-D1 — THEME SOURCE AND IDENTITY CENSUS (2026-08-18)

**Pin:** `5c1d82b928` (origin/main, fetched 2026-08-18T02:22:18Z). **Wave class:** deterministic census; zero runtime/rank/ThemeState authority. **Machine artifacts:** `research/prophet_v4/d1/*.json` (each carries pin, reproduce commands, cohort stamps). **Method:** four routed workers (scout estate reconstruction; builder matrices; researcher external audits; drafter assembly) + orchestrator adjudication; every claim receipted; sparse-tree hazard eliminated by materializing `data/` + `site/` before any absence claim.

## 0. Headline truths

1. **The Chairman's concern is quantified: 73% of the candidate-store union (2,368 of 3,253 names) has NO thematic membership beyond structural sector/industry** (`coverage_matrix.json`, C6; split: 924 structural-only + 1,444 with no classification at all — the latter coinciding exactly with the scan tier, for which the store writes no `sector`). The denominator is the store's analyzed union, NOT an eligibility-tested universe — no listing/ADR/micro-cap test was applied in D1 (routed to D2's queue; adversarial finding M7). The thematic estate is real but concentrated: canonical themes + curated baskets + local provider planes cover the curated core and leave the scan tier almost untouched.
2. **The graph's company plane is ticker-string-keyed end to end** — every company node's `external_ids` is exactly `{"symbol": <ticker>}` (`identity_join_audit.json`). No `company_id`/`security_id`/epoch reaches graph membership today. The conceptual join *source member → company_id → security_id(s) → episode* does not exist yet; today it is *ticker string → theme*. This is D2's central repair.
3. **Two real data defects live in the graph now** (found by the hostile-identity audit, recorded as gap rows, NOT fixed in D1 per scope): the reused-ticker **GOLD** case (dealer tape vs Barrick-class issuer — the same defect class Stock Identity W1-A1 corrected in its own store) and **IBIT** (an ETF present as an operating-company member).
4. **No ThemeState store exists — but a ThemeState-SHAPED system already runs**: the Neural Web `thematic_state` lineage (`engine/neuralweb/thematic_state.py` → `data/neuralweb/theme_state.json`, 18 themes, dated `theme_phase_history.jsonl`). Any W3B/D3 build must supersede-or-extend it explicitly or the estate ends up with three theme-state vocabularies (see `D1_D3_W3B_MERGE_ORDER_RECOMMENDATION.md`).
5. **Coverage ≠ rights**: the two richest dynamic planes (Finviz, THS) are `rights_class: unresolved` → internal-only for new emissions; only `mastermind_curated` is `direct_display_ok`. A high-coverage public ThemeState cannot be built lawfully from Finviz/THS today (4 RIGHTS_DECISION_REQUIRED items routed, §7).

## 1. Cohort denominators (closed, stamped — `coverage_matrix.json`)

| Cohort | Count | Session stamp | Notes |
|---|---|---|---|
| C0 supported-universe union | 3,227 | 2026-08-07 (curated+scan union) | the broadest closed roster the candidate store carries |
| C1 latest lawful candidate store | 1,508 | **2026-08-12 — STALE** (store stalled with the outage) | scan-tier only at that stamp |
| C2 served Prophet population | 192 | source_asof 2026-08-13 (STALE server board) | plans' tickers |
| C3 TURN WATCH complete triggers | 831 | 2026-08-13 | triggered + beyond_cap, NOT the 40-card deck |
| C4 Radar probe universe | UNKNOWN | — | no materialized Radar artifact at pin (W4 unarmed); recorded, not fabricated |
| C5 featured/top | 71 | 2026-08-14 | current board featured population |
| C6 thematic-gap population | **2,368 (73%)** | derived | C0∪C1 names with structural-only classification — the D2 queue seed |

## 2. Source families and adjudicated taxonomy roles

Full rows: `d1/source_family_matrix.json` (merged: builder-computed coverage + scout/drafter descriptive fields). Roles are FROZEN adjudications:

| Family | Role | Key facts |
|---|---|---|
| Per-row sector/industry strings + 11 `us_sector_*` pseudo-baskets + `config/sector_legs.json` + `ticker_sectors.parquet` (`build_sector_map.py`) | STRUCTURAL_CLASSIFICATION | broad, single-hierarchy, NO_HISTORY PIT class; the upstream origin of the per-row sector string is UNTRACED (gap row); **rights UNRESOLVED (review H4): 1,503/1,515 `ticker_sectors` rows are third-party GICS (`gics_sp500/400/600`) with no `config/theme_sources.yml` registry row — routed as rights decision #5, never assumed house-public** |
| 18 crosswalk TIL themes (`config/theme_crosswalk.yml` v3) | CANONICAL_HOUSE_THEME | 13 with `primary_basket_id` (the ONLY reverse-safe basket relation), 5 honest nulls; `citrini_basket_ids: []` everywhere; CURRENT_SNAPSHOT_ONLY (hand-versioned file) |
| Finviz local themes (`ltheme:finviz:*`, 268) | LOCAL_PROVIDER_THEME | 2,365 membership edges; own vintage receipt 942 attempted / 0 refused (latest-nightly-delta scope only); dated history exists (`subsector_perf_history.jsonl`, `tree_history.jsonl`) → OBSERVED_PIT_FROM_START_DATE; rights UNRESOLVED (internal-only); **0 of 268 are canonically mapped — every one of the 61 local→canonical expressions is THS-side** (review finding M4) |
| THS concepts (`ltheme:ths:*`, 373) | LOCAL_PROVIDER_THEME | 312 still unmapped to canonical (breadth outside the canonical layer, NOT a fuzzy-match target); CURRENT_SNAPSHOT_ONLY at graph grain (CN suite has its own history parquet); rights UNRESOLVED |
| Curated baskets — US 38 true baskets (49 minus 11 structural pseudo) + regional suites (CA 16, CN 22, CN-THS 237, HK 17, INTL 17) | CURATED_BASKET | **RECONSTRUCTED_PIT — DEGRADED** (review H3: 95% of `added` dates are the 2023-05-09 curator seed constant; removals largely unstamped — the verified GOLD removal carries no `removed` — so past-date reconstruction largely returns today's roster); `direct_display_ok`; a basket is NOT a theme unless `primary_basket_id` says so — the crosswalk's own `unmapped_baskets` list yields 20 proxy-basket-only gap rows |
| Theia, S&P/Kensho | PROVIDER_CLASSIFICATION_OPTION | commented registry stubs only; zero ingestion; Theia DEC re-verified and STANDS (no new evidence; six-row gap matrix in `d1_research` scratch + §6) |
| `data/theme_graph/probation/proposals.jsonl` | PROBATION_MAPPING | the only lawful local→canonical promotion path; schema unopened in D1 (flagged for D2) |
| `site/marketdata/subsector_rotation.json` + `themes_heatmap.json` | OWNER_SURFACE_ONLY | grandfathered Finviz surfaces; field-mapped (§5); its live artifact is itself a PIT hostile exemplar: `asof 2026-08-13` vs `generated_utc 2026-08-17 23:53` |
| Act-Now board (`site/basketdata/action_board.json`) | OWNER_SURFACE_ONLY | curated-basket taxonomy, `direct_display_ok`; NOT field-mapped in D1 (named gap for D3) |
| Neural Web `thematic_state` lineage | OWNER_SURFACE_ONLY (pre-existing ThemeState-shaped system) | 18-theme vocabulary; `theme_phase_history.jsonl` is bitemporal + hash-chained → OBSERVED_PIT; reconciliation owed by W3B (§ruling doc) |
| `group_pulse` | OWNER_SURFACE_ONLY (derived) | participation episodes OVER basket membership; excluded from membership coverage |
| Company Theme Exposure (`engine/company_theme_exposure/`) | OWNER_SURFACE_ONLY (derived projection) | **membership projection, not exposure weights** (`contracts.py`: "not a thematic score"; items = theme_id/basket_id/mapping_qualifier; authority `context_only`); artifact R2-only, absent on disk → coverage UNKNOWN. **The company↔theme exposure-WEIGHTS plane still does not exist** — W3A's honest null stands (native path: XBRL segment-axis work, in progress elsewhere) |
| Citrini | UNVERIFIED_REFERENCE | **CITRINI_OPERATOR_HELD_ONLY** — CITR-2 (definitions-only) ruling permits committing definitions; nothing is committed; feeds permanently closed; no registry row; `data/citrini/` absent |

Taxonomy shapes + the cross-taxonomy link inventory (61 local→canonical expressions, 237 THS basket→ltheme edges, 312 unmapped THS, crosswalk join fields): `d1/taxonomy_grain_matrix.json`.

## 3. Coverage truths (`coverage_matrix.json`)

- Union order (frozen for incrementality): canonical crosswalk → curated baskets → finviz ltheme → ths ltheme → structural. Raw AND incremental reported per source × cohort; multi-label density preserved (never deduped); rights-usable split (`internal / public_display / rights_blocked`) sums to raw per cell by construction.
- The scan tier is the desert: C1 (scan-only stamp) shows near-zero non-structural coverage — group-A/B exemplar pools came back with ONE qualifying name each, an honest finding. Thematic coverage concentrates precisely in the names the old gate already selected (C5) — the anti-pattern V4 exists to break.
- C3 (TURN WATCH, 831) is the first early-pool denominator ever measured against the thematic estate.

## 4. Identity truths (`identity_join_audit.json`)

- Graph membership joins are `join_method=ticker_string` at best confidence today. Resolution-receipt scope (review M8): the 942/0 vintage receipt is Finviz's and covers the latest nightly delta only; the curated-basket and THS planes carry NO resolution receipts at all — a refusal there is structurally invisible today, which is itself a D2 repair item.
- Six hostile chains covering five case classes recorded: GOOG/GOOGL (one issuer, two securities — two graph rows, correctly distinct), BRK-B dot/dash convention, GOLD reused-ticker (LIVE defect), B renamed-issuer/corporate-action case, IBIT ETF-as-company (LIVE defect). **GOLD root cause corrected by review H2:** `data/baskets/membership.json` is ALREADY CORRECT (12 members, GOLD in `omitted` per #5632); the stale carriers are `membership_history.parquet` (08-13 snapshot: GOLD present, no `removed`; B absent) + `snapshots/2026-08-13.json` + the theme-graph builder that consumed them. Failed canonical resolutions are FINDINGS — no resolver was minted (scope law).
- Stock Identity's plane (`sec:`/`co:`/epochs) exists and is the designated join target; nothing in the theme estate consumes it yet.

## 5. Owner-surface reconciliation (What-To-Act-On-Now)

Field-level mapping (every field, `d1_research/D1_field_mapping.md`, summarized): `perf{1D..YTD}` → performance family = **REUSE**; the REAL velocity/acceleration primitives are the turn-engine z-fields (`impulse_z/accel_z/curve_z/trend_z/today_z`, `engine/subsector_turn.py:517-767`) = **TRANSFORM** (formulas are prior art; PIT replay absent); the top-level `accel`/`z_accel` is a *different formula wearing the same name* = **REJECT** as a V4 primitive (the exact trap §13 warned about, now receipted); `breadth{...}` = **TRANSFORM** but computed same-day-only (no PIT history — cannot train on it); `emerging_score`/`bottom_score`/`top_score`/`rs_*_v2` composites = **REJECT** (bespoke, unpromoted); identity/labels = OWNER_ONLY. The surface stays the owner's; V4/GMI consume formulas as prior art, never the artifact as ThemeState.

## 6. External taxonomies

- **Citrini:** `CITRINI_OPERATOR_HELD_ONLY` (verdict + receipts in §2 row; the $50k/yr subscription is real but operator-held; committing definitions is ALREADY permitted by CITR-2 — this is an operator delivery gap, not a rights question).
- **Theia:** `DEC:PROPHET-V4-THEIA-SOURCE-RIGHTS` re-verified, STANDS; six-capability gap matrix shows nothing blocks V4; exposure-weights is a native-build gap, not a Theia dependency.
- **S&P/Kensho:** public methodology only; systematic constituent ingestion = unopened procurement question.

## 7. Rights decisions routed (not taken here)

1. Finviz "derived display" tier (unresolved; blocks any PUBLIC ThemeState derived from Finviz; W6 named as forcing point). 2. Citrini definitions commit (permitted, undelivered — operator). 3. Theia TIIC/TWI license (Chairman option, no urgency). 4. Kensho constituent ingestion (unopened). 5. **Structural GICS classification** (review H4: `ticker_sectors.parquet` is 99% third-party GICS with no registry row — public-display right unproven). Until 1 and 5 resolve, ThemeState built on Finviz/THS is **internal/display-context only** and even structural-sector public display rests on an unreviewed assumption.

## 8. ThemeState feasibility — ADJUDICATED verdicts (facts in `d1/theme_state_feasibility.json`)

| Feature family | Verdict (final) | Grounding |
|---|---|---|
| Performance (1D/5D/10D/20D/63D, excess vs SPY/sector, vol-norm, drawdown) | **READY_AFTER_D2** | needs PIT membership joins at issuer grain (D2) + OHLCV PIT verification (flagged: `data/baskets/ohlcv/` unverified in D1). **H3 rider on all D2-gated families:** curated-basket history is RECONSTRUCTED_PIT-DEGRADED (seed-constant added dates, unstamped removals) — training-grade PIT membership begins only after D2 institutes real vintage/removal stamping; anything computed on today's history is display-context, not trainable |
| Velocity/acceleration/persistence | **READY_AFTER_D2** | same inputs as performance; owner-surface z-formulas are prior art, PIT replay absent |
| Breadth — SPLIT (adjudication refines the builder's single NO_SOURCE): price-participation breadth (positive share, MA participation, rising RS, new highs/lows) | **READY_AFTER_D2** | member-level OHLCV + PIT membership — same substrate as performance |
| Breadth — expert-event participation share | **READY_AFTER_RADAR** | no materialized event artifact (W4 unarmed); LER wall forbids desk reuse pre-promotion |
| Breadth — entry-open participation share | **READY_AFTER_RADAR** (+ requires B4's availability engine) | `ENTRY_OPEN` does not exist as a computed fact yet |
| Diffusion/leadership (participants, subthemes, concentration, entropy, leader/median, cap diffusion) | **READY_AFTER_D2** | member-level returns + membership; cross-region confirmation additionally needs regional-suite alignment (later) |
| Propagation — earnings diffusion | **READY_AFTER_EIOS** | one golden event ≠ coverage |
| Propagation — peer/supply-chain | **NO_SOURCE** | no supply-chain plane exists anywhere in the estate (confirmed absence) |
| Propagation — altdata corroboration | per-family per the 0A registry states | insider PRODUCER_DEGRADED etc. |
| Quality/stability (membership vintage, small-N shrinkage, coverage/stale shares) | **READY_NOW** | computable from existing stores today |

**Net:** ThemeState v1's core (performance/velocity/breadth-price/diffusion) is one wave away — D2's identity+membership repair — NOT blocked on any purchase; its event-aware limbs wait on Radar/B4/EIOS; nothing is READY_NOW except quality/stability metadata.

## 9. Gap ledger

28 seed rows (`d1/mapping_gap_ledger.json`): 20 proxy-basket-only (the crosswalk's own unmapped_baskets), 2 contradictory (GOLD, IBIT — live graph defects), 1 join-failure, 2 rights-blocked, 1 no-PIT, 1 stale-source, 1 untraced-origin (per-row sector string; `gap_type` aligned per review M5), prioritized by coverage impact. C6's 2,368-name population is the volume behind them. **Owner routing (review M6):** the two live defects sit in GMI-owned `data/theme_graph/`; per the 0B sibling-record law this census ROUTES them (D2 executes inside GMI and corrects through graph lineage, updating GMI's record in its own PR) rather than editing `WS-GMI-THEME-GRAPH.md` from a V4 wave.

## 11. Adversarial review (attached; all findings dispositioned in this PR)

Fresh-context opus reviewer ran the commission's §24 battery — all 32 verdicts + **6 exact recomputations** (C0/C1/C3/C5/C6 counts, coverage cells with density stats, the 20-row proxy set, the 2,806-node identity sweep, the EXPRESSES link census, incremental-sums-to-union). Every headline number reproduced exactly. Findings: **1 BLOCKER** (reproduce arrays pointed at uncommitted scratch — harness now committed under `d1/build/` + `d1/D1_field_mapping.md`), **4 HIGH** (structural PIT contradiction; GOLD root-cause misattribution — the curated doc was already correct, the stale carriers are the history parquet/snapshot + graph builder; curated-basket RECONSTRUCTED_PIT downgraded to DEGRADED; structural-family rights de-inflated + routed as decision #5), **8 MEDIUM** (artifact-count, THS plane conflation, feasibility supersession marker, the Finviz 0/268 truth, gap-type bucket, GMI routing, denominator eligibility caveat, refusal-receipt scope), **7 LOW** (path/typo/language/envelope/count fixes). Verdict: safe to open; canonical-receipt status required the B1/H1–H4 repairs, which this PR carries.

## 10. Completion standard check (§25)

Truth ✔ (sources + both clocks measured; snapshot-vs-PIT classed from artifact contents). Identity ✔ (grain measured; ticker-keyed truth + live defects named). Rights ✔ (registry read; 4 decisions routed). Coverage ✔ (closed denominators C0–C6; raw/incremental/rights-split). Gaps ✔ (ledger + C6 queue). Buildability ✔ (feasibility verdicts + three rulings). No-rebuild ✔ (roles pin what is owner-surface/prior-art vs canonical; no second graph, no ThemeState, no resolver minted).
