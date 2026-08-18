# V4-D2 — CANONICAL ONTOLOGY + PROBATION MAPPING (SPAWN HANDOFF)

**Wave:** `d2` of `WS:PROPHET-US-V4-RECOVERY`, executing **inside/with `WS:GMI-THEME-GRAPH`** (its paths, its ownership — wave-graph §4, owner map §1). Written by V4-D1 (2026-08-18) from the census at pin `5c1d82b928`. **RE-PIN at spawn; re-read `D1_THEME_SOURCE_AND_IDENTITY_CENSUS_2026-08-18.md` + `d1/*.json` first — D2 must never redo source archaeology.**
**Routing:** sonnet `builder` implements; opus `reviewer` red-teams; design not involved. Model routing + ROUTE registry law applies to every spawn.

## §0 Acceptance gates — "not done unless"

1. **Identity-grain repair:** graph company/membership planes join through `stock_identity` interfaces (company_id/security_id/identity epoch) instead of bare ticker strings; every projection row carries source-native id + canonical ids + join_method + refusal_reason; refusals preserved, never dropped. The two LIVE defects (reused-ticker GOLD member; IBIT ETF-as-company) are corrected **through the graph's own correction lineage** (evidence rows/correction records), never by silent parquet edits.
2. **Mapping breadth via PROBATION ONLY:** the 312 unmapped THS concepts, 268 Finviz local themes, and the crosswalk's 20 unmapped proxy-only baskets flow through `probation/proposals.jsonl` (open and document its schema — unopened in D1) with explicit adjudication records; **zero mechanical/fuzzy-label mappings** (W3A's ruling stands); un-adjudicated proposals stay probation, and "still unmapped" is a legal end-state.
3. **PIT membership discipline:** membership edges carry valid_from/valid_to + membership_vintage; no later-discovered member is backfilled into earlier dates; the CURRENT_SNAPSHOT_ONLY planes (crosswalk, THS graph grain) gain forward-only dated vintages from D2's first run (history begins at D2 — never reconstructed).
4. **Node/edge type extensions** only as masterplan §12.2 requires for gates 1–3 (typed, time-bounded, source+rights+confidence per edge); **no second graph, no ThemeState, no exposure-weights invention** (that plane has NO SOURCE — census §2; do not fabricate it).
5. **Rights gates untouched** (`config/theme_sources.yml` semantics; Finviz/THS stay internal-only pending the routed decision #1); `assert_public_emission_allowed()` still binds every emitter.
6. **Coverage delta measured against D1's frozen baselines:** re-run the D1 coverage harness — **committed at `research/prophet_v4/d1/build/`** (review B1 fix; self-contained from a checkout with `data/`+`site/` materialized) — post-D2 and report C6 shrinkage honestly; names that stay ungapped for lack of any lawful source are reported as such, never force-mapped. Two review riders bind: **(H3)** curated-basket history is DEGRADED-PIT (seed-constant added dates, unstamped removals) — D2 institutes REAL vintage/removal stamping from its first run so training-grade PIT begins; **(M7)** run the eligibility census D1 deferred (listing/ADR/ETF/micro-cap test over the C0 denominator) so the 73% gap number gains an eligibility-tested twin.
7. **Records:** GMI + V4 workstream rows updated in the same PR; agentos validates 0 errors; opus adversarial review (attacks: forced mappings, identity shortcuts, backfilled PIT, silent defect edits, rights drift, second-store creation) dispositioned pre-merge; ship loop to merged + verified.

## §1 What D1 hands you (do not re-derive)

The census + the `d1/` artifact set (8 matrices, `D1_field_mapping.md`, the committed `build/` harness): source families/roles (20 rows), taxonomy shapes + link inventory, coverage with closed denominators (C0=3227@08-07, C1=1508@08-12-STALE, C2=192, C3=831, C5=71, C6=2368), identity audit (ticker-keyed truth + hostile chains), PIT classes per source, feasibility verdicts (performance/velocity/breadth-price/diffusion are READY_AFTER_**YOU**), 28-row gap ledger (your priority queue, coverage-impact ordered).

## §2 Boundaries

GMI-owned paths ONLY (`engine/theme_graph/**`, `data/theme_graph/**`, config registries per GMI concurrence); no Prophet engine/UI/rank files; no Radar/EIOS/availability files; no `engine/neuralweb/thematic_state.py` (W3B's reconciliation target, not D2's); the owner surfaces stay owner-only. W3B (ThemeState) does NOT start inside D2 — `D1_D3_W3B_MERGE_ORDER_RECOMMENDATION.md` sequences it after D2 under GMI, pending Sol's adjudication.

## §3 Stop condition

Gates 1–7 green, PR merged, coverage delta reported, handoff written (next: W3B under GMI per the merge-order recommendation; D5 contract lane separately per `D1_D5_READINESS_RULING.md`). No auto-roll into W3B/D3/D5.
