# PROPHET US V4 — CONTRACT AND OWNER MAP (V4-0A)

**Pinned main:** `fc0557bb0873` (2026-08-17). Every canonical owner V4 consumes, the exact contract surface, and the paths no V4 wave may duplicate. Companion: `ARCHITECTURE_FREEZE.md` §9–11 (the rulings), `WAVE_GRAPH_AND_MERGE_ORDER.md` (who may touch what, when).  
**Cell F reconciliation:** 2026-08-23 — D5 preserves Context Vector unchanged, requires canonical B1 runtime identity, and emits no placeholder family for an unbuilt adapter.

## 1. Owner table

| Authority | Owner (workstream) | Contract surface at pin | V4 consumes via | Never duplicated |
|---|---|---|---|---|
| Expert-event production | `WS:LIVE-ENTRY-RADAR` | `engine/entry_radar/entry_events.py` — `mastermind.entry_event.v1` (append-only; NO `episode_id` field, list frozen — B1 join-key ruling required, freeze §3); the RUNTIME episode ledger `engine/entry_radar/live_ledger.py` (`mastermind.live_entry_episode.v1`, ephemeral, expert-keyed — see freeze §3 grain reconciliation); experts G0/C1–C5 per PR-0 contract §3–4; durable forward store `data/entry_radar/forward.parquet` via `scripts/reconcile_entry_radar.py --nightly` | V4-B1 episode intake maps registered expert fires → **canonical V4 candidate episodes**. Radar's live episode may be referenced as Radar context but is never renamed/aliased into `prophet.candidate_episode/v1`; V4-B6/B7 activation/product per wave-graph §4.3 | detector logic, event minting, the Radar runtime episode ledger, F1_FUSION, or any surrogate B1 lifecycle |
| **Exact issuer/security/listing identity** (added 2026-08-18, Sol D2A ruling) | Data OS spine — no registered workstream at this pin (`lib/dataos/identity.py` allocator + `scripts/build_security_master.py` producer; DOS-1.1/1.2 landed 08-12/08-13) | `data/reference/security_master.parquet` + `vendor_aliases.parquet` (`ISS:`/`SEC:`/bare `<CC>-<MIC>-<CODE>[.N]`), read exclusively through `lib.dataos.identity.VendorAliasTable`; `config/identity_seams.yml` is the seam registry | V4-D2A's bridge (`engine/theme_graph/identity_resolution.py` → `data/theme_graph/identity_resolution.parquet`) is its FIRST REAL CONSUMER, projecting GMI company-kind nodes onto it; later D2B/D3 lineage work reads the same side-car | a second exact-identity allocator/master. **Issuer axis (V4-D2B1, 2026-08-19, #5965):** `issuer_id` is now a true economic-issuer id — one issuer across share classes where SEC-registrant CIK evidence groups them (era `issuer_semantic_correction_v1`; migration receipts `data/reference/issuer_migrations.parquet`; issuer table `data/reference/issuer_master.parquet`; typed `issuer_state` refusals) — and the `_receipt.json` authority line is decomposed (`identity_authority: canonical_exact_identity`; signal/ranking/trade: none), retiring the stale `display_only` prose the earlier note in this row described. `WS:STOCK-IDENTITY` (row below) is explicitly NOT this authority — see its updated row. |
| Identity epochs / behavioral fingerprints (NOT exact-identity authority — see row above) | `WS:STOCK-IDENTITY` | `engine/stock_identity/` interfaces (`stock_identity.*`); W1 Atlas v0 (#5612) + W1-A1 correction (#5660); W2 replay in flight | `security_id`/`company_id`/`identity_epoch` fields of `prophet.candidate_episode/v1`; later E4 routing via its Method Law channels | any rival fingerprint/epoch/personality stack; **and, since 2026-08-18, any claim to be the estate's exact issuer/security/listing identity authority** — that authority is the Data OS spine (row above); this WS stays scoped to behavioral/expert-routing identity |
| Company–theme relationships & theme state | `WS:GMI-THEME-GRAPH` | `engine/theme_graph/{store,materialize,capability,identity,identity_resolution,local_sources,probation,rights}.py`; stores `data/theme_graph/{nodes,edges,capability,evidence,identity_resolution}.parquet` + `probation/proposals.jsonl`; `config/theme_sources.yml` + `engine/theme_graph/rights.py` emission gate; `config/theme_crosswalk.yml` | V4-D2..D4 extend in/with the GMI lane; ThemeState is GMI-owned. **D5 emits no `theme.theme_state` family envelope until the canonical ThemeState source contract and a lawful D5 adapter exist.** Readiness may be `ACCRUING` outside the evidence envelope, but legacy Context Vector theme fields are never substituted as current Theme truth. GMI topology ids remain deliberately distinct from Data OS ids; `identity_resolution.py` is the bridge, not a second allocator | a second graph or theme truth store; a second exact-identity allocator; a Prophet-local ThemeState; a synthetic D5 Theme placeholder |
| Earnings events/facts/claims | `WS:EARNINGS-INTELLIGENCE-OS` | runtime/canonical event-workspace surface owned by Earnings; broader issuer coverage remains owner truth | V4-D6 is the first preferred thin D5 adapter **after canonical B1 exists**, selecting only allowlisted owner fields and preserving source refs/clocks/rights/missingness | calendars, transcripts, event identity, claim extraction, or a Prophet-local earnings store |
| Cross-family ranking/fusion machinery | `WS:PROPHET-CONDITIONAL-FUSION` | `engine/us_prophet_fusion.py`; machine registry `research/prophet_fusion/families.yml`; one feature/member has one anti-double-count family home; registry itself grants no authority | V4-E1 executes as the accepted Fusion lineage after its owner gates. **D5 does not create rank families or votes. Only explicit bindings to accepted Fusion members/versions may make a D5 owner-native observation eligible for E1.** | a second cross-family ranker; treating D5 evidence-family/semantic-head/source-root presence as votes; edits around the Fusion owner |
| **Prophet engine files (`engine/prophet_*.py`, incl. `prophet_bridge.py`, `prophet_arena.py`, `prophet_live/`)** | **`WS:PROPHET-US-ENTRY-TIMING`** (registered `owns_paths: engine/prophet_*.py`; cross-confirmed by `WS:LIVE-ENTRY-RADAR` §"Prophet is untouchable" and `DEC:LER-SEPARATE-SYSTEM-NOT-PROPHET-CHANGE`) | the bridge/arena/live-states surfaces §2 describes | V4 B2/B3/B4 execute as **joint work under that workstream** (wave-graph §4.1); it is in this WS's `depends_on` | unilateral V4 edits to `engine/prophet_*.py` |
| Outcome labels / promotion evidence | Evaluation OS / QLedger (`WS:EVAL-OS-MEASUREMENT-LAW`, which registers `engine/qledger.py`; siblings `WS:EVAL-OS-OUTPUT-HEALTH`, `WS:EVAL-OS-T1-ENGINE-REGISTRY`) | `engine/qledger.py` claim/grade substrate; board/all-name grade stores; plan ledger | V4-C1 cohorts project from the common episode outcome; E3–E6 learned challengers/promotion use the same evaluation plane | a second forward grader; an alternate scoreboard; offline metric treated as production promotion |
| Rescue/liveness (availability response) | `WS:PROPHET-US-AVAILABILITY` | `scripts/prophet_rescue.py` + `.github/workflows/prophet-rescue.yml`; nightly-liveness sibling | V4-A-lane reconciles + extends with the settlement manifest; manifest becomes what liveness/rescue READ | a second rescue plane or detection stack |
| Candidate episodes, lifecycle, availability, D5 projection, product projection, operator workflow | **`WS:PROPHET-US-V4-RECOVERY` (this program)** | contracts: `prophet.candidate_episode/v1` (B1), `prophet.entry_availability/v1` (B4), `prophet.intelligence_vector/v1` (D5), `prophet.settlement_manifest/v1` (A2) | D5 runtime **consumes** B1 episode identity; it never mints another lifecycle. B4 lane is orthogonal and binding. | a second candidate identity plane; aliasing `mastermind.live_entry_episode.v1`; a ticker/date episode; a D5-owned Context Vector fork |
| Publication/auth/queue/state planes | existing platform owners | existing Git/site/VPS/tier surfaces | V4-A2/A3 make the settlement manifest + bundle hash the machine-verifiable spine every projection carries | a second publication truth |

## 2. Prophet engine estate V4 migrates — **REGISTERED to `WS:PROPHET-US-ENTRY-TIMING` where the path matches `engine/prophet_*.py`**

| Component | Path (writer) | Role today | V4 disposition |
|---|---|---|---|
| Bridge / admission | `engine/prophet_bridge.py` | originates board rows | authority migrates to episode registry (B1) + lifecycle (B3) + availability (B4); 3D cascade demoted to maturity expert |
| Entry-status semantics (prior art B4 MUST reconcile) | `engine/entry_signal.py` — `assess()` buy-zone/chase/stop/null discipline | existing per-ticker availability semantics | B4 unifies-or-supersedes explicitly; a second parallel availability truth is rejected |
| Candidate pool partition (prior art B5/C1 MUST reconcile) | `engine/us_candidate_lanes.py` — `us_candidate_pool_v1` | existing lossless all-candidate partition | All-Candidates (B5) and cohorts (C1) extend this plane, never build a rival partition |
| Origination doors (prior art B1 MUST reconcile) | `engine/prophet_doors.py` — `prophet_doors/v1` | preregistered intake-door precedent | B1 maps doors→intake classes; never discards their prereg/evidence |
| Settlement instrumentation (prior art A2 MUST reconcile) | `scripts/freshness_sentinel.py` | reader-visible settlement receipts | A2 manifest extends the sentinel receipts; both instruments read one truth |
| Reconstruction provenance (A1 MUST use) | `engine/prophet_integrity.py` | existing reconstructed-session law | A1 uses it, never re-derives it |
| Board ranker | `engine/us_board_rank.py` | ranks + stamps served board | V3 path frozen at cutover (C2); V4 deterministic rank = E1 after its owner gates |
| **Context vector** | `engine/us_context_vector.py` → `data/us_prophet_rank/candidates/YYYY-MM.parquet` (PIT, keep-first, schema-union) | nightly sensory/history/research spine, zero authority | **REUSE UNCHANGED. D5 v1 adds zero columns and owns no mutation here.** D5 may carry an exact `context_vector_ref` to an existing observation. Historical Context Vector rank/board outputs remain prohibited D5 evidence. |
| Early-turn union | `engine/us_early_turn.py` + bridge wiring | early-turn watch deck | B2 dispositions known defects before authority |
| TURN WATCH | `engine/us_turn_watch.py`, `scripts/build_turn_watch.py` → `site/turn_watch/turn_watch.json` | early desk data plane | B5 consumes; ownership lands in this WS |
| Legacy shadow (plan grain) | `engine/prophet_bridge.py` legacy shadow store | v2 shadow plan rows | precedent for C2's V3 legacy shadow |
| Execution-policy arena | `engine/prophet_arena.py` | frozen entry/execution policy challengers | untouched by V4 rank work |
| Live states plane | `engine/prophet_live/live_states.py` | intraday detection, ungraded | B4 successor authority for “entry validity now” |

## 3. Contract quick-reference (frozen names, reconciled by Cell F)

- `prophet.candidate_episode/v1` — canonical durable candidate episode identity plane (B1). Owner: V4. **Mandatory parent identity for runtime D5.**
- `mastermind.live_entry_episode.v1` — Entry Radar operational detector lifecycle. Owner: Radar. **Not an alias or substitute for B1.**
- `prophet.entry_availability/v1` — deterministic buyability (B4). Owner: V4. Intelligence/Fusion cannot flip `ENTRY_OPEN`.
- `prophet.intelligence_vector/v1` — episode-scoped missing-aware evidence read-model (D5). Owner: V4. **Separate from Context Vector; all D5 rank/gate/size/origination/ENTRY_OPEN authority false.**
- `theme_state/v1` — deterministic theme dynamics. Owner: GMI lane. An unbuilt Theme adapter emits no D5 family envelope.
- `prophet.settlement_manifest/v1` — session settlement spine (A2). Owner: V4 A-lane, read by liveness/rescue.
- `mastermind.entry_event.v1` — existing Radar event contract. Owner: Radar. V4 reads, never writes.
- `us.prophet_grades/v1` — existing all-name grade parts. Owner: Evaluation plane. V4-C1 projects cohorts from it.

### 3.1 D5 family/readiness law

- **adapter or specialist contract unbuilt** → family absent from `evidence_families[]`; readiness may be reported outside the envelope;
- **adapter built, applicable object absent/degraded/not covered** → lawful family envelope may carry the orthogonal coverage/freshness/rights/identity state plus typed `ABSENT` observation;
- **genuinely not applicable** → `NOT_APPLICABLE` only when source-contract-grounded;
- **measured neutral** → requires positive owner measurement under a named neutral/measured-negative definition;
- missing/not-covered/rights-blocked/stale/producer-degraded observations abstain from current E1 eligibility; they never become zero votes.

### 3.2 Deterministic E1 consumption boundary

The deterministic baseline remains **rank inside the B4 availability lane**, never rank-to-availability feedback. E1 may consume from D5 only an owner-native decision-admissible observation explicitly bound to an accepted Conditional Fusion member/version and only under that registry's PIT, coverage, staleness, era, direction, transform and anti-double-count law.

D5 semantic heads, family presence/counts, source/provider/root counts, dependence-group counts, explanation facts, coverage itself, unregistered facts, reconstructed/after-cut evidence and model-generated narrative do not rank merely because D5 can display them. Learned E3/E4/E5 challengers remain shadow-only until E6 separately promotes them.

Exact examples and baseline: `research/prophet_v4/flagship_cells/CELL_F_D5_CANDIDATE_REFERENCE_COMPOSITIONS_AND_E1_BASELINE_2026-08-23.md`.

## 4. Consumers (who reads V4's outputs)

- **Dashboard/product pages** (server-stage contract; browser renders byte-for-byte — no client inference after B3).
- **Liveness/rescue instruments** (read the settlement manifest from A2 on).
- **Evaluation OS** (episode outcomes → cohort ledgers → promotion gauntlet).
- **Neural Web / Mastermind chat** (product artifacts only, per CXI-R23 — chat context reads served artifacts, never repo internals).
- **Conditional Fusion / V4-E1** (only explicit accepted member bindings, never implicit D5 votes; same-tape comparison and deterministic baseline first).
