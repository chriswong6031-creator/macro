# PROPHET US V4 — ARCHITECTURE FREEZE (V4-0A)

**Frozen by:** Fable (COO, principal orchestrator), session 2026-08-17
**Authority:** Chairman directive → `PROPHET_US_V4_RECOVERY_AND_INTELLIGENCE_GRAPH_OS_MASTERPLAN_BY_SOL_2026-08-17.md` (same directory) → existing DNR/canonical-owner contracts → AgentOS workstreams + merged source → `FABLE_HANDOFF_PROPHET_US_V4_0A_2026-08-17.md`
**Sol's snapshot main:** `16874921e6380659933252b9abc77f45d86a2b22`
**Repinned execution main (this freeze):** `fc0557bb0873f51db5ccbab4b043b26bbc9bb670` (2026-08-17T06:04:45-05:00)
**Workstream:** `WS:PROPHET-US-V4-RECOVERY` · **Board definition:** `us_prophet_v4`
**Repin deltas that matter:** see §12 (estate moved between Sol's snapshot and execution; notably Live Entry Radar W5 records closed via #5825/#5827 on the morning of 2026-08-17).

---

## 1. The frozen thesis

> **Surface by emergence. Gate by the trade available now. Rank by intelligence. Explain the evidence. Let the Chairman decide.**

Operating maxim (masterplan §6.2): **Discovery may be noisy. Availability must be strict. Ranking must be explainable. Promotion must be earned.**

V4 is a controlled migration of the operating model — not a scoring patch to the current board. Initial authority is manual-research/display; no autonomous trade origination or sizing.

## 2. Six independent planes (ratified, masterplan §6.1)

| Plane | Question | Initial authority |
|---|---|---|
| Discovery | Is anything beginning to change? | High-recall candidate intake |
| Maturity | How confirmed is the move? | Context/display |
| Availability | Is the trade valid at the current price? | **Binding green-entry gate** |
| Intelligence | How interesting/asymmetric is the name? | Display ordering |
| Uncertainty | How complete/trustworthy is the evidence? | **Binding disclosure and fallback** |
| Outcome | What happened after surface/entry? | Promotion evidence |

No single `stage` or `score` may replace these planes. The 25 non-negotiable laws of masterplan §5 are ratified and reproduced here verbatim so every wave handoff carries them (quality does not travel by pointer):

1. **Every owed session settles end to end.** A workflow, build or publish job is not success until the production reader shows the owed source session.
2. **No browser-derived authority.** Lifecycle, availability, buyability and score basis are calculated server-side and rendered byte-for-byte.
3. **Candidate is not pick.** Candidate intake never implies endorsement.
4. **No producer cap.** Preserve every qualified episode; cap only a UI projection.
5. **One active structural episode per identity epoch** unless the episode contract explicitly re-arms. Multiple experts attach to the same episode.
6. **3D confirmation is maturity, not permission to buy.**
7. **Entry availability outranks score.** A high intelligence score cannot waive extension, invalidation, stale quotes or excessive risk.
8. **Intelligence ranks inside availability lanes.**
9. **Missing is not zero.** Every absent family has a named null reason and coverage effect.
10. **Stale is not missing.** Stale evidence is separately marked and normally excluded from current scoring.
11. **No feedback loop.** A board output cannot return through an upstream "opportunity" score and rank itself.
12. **No future leakage.** Membership, features, labels, corrections and events are joined by knowable time.
13. **No silent repaint.** Provisional expert events must either become confirmed or emit a correction/retraction event.
14. **No fake intraday replay.** 1D-live/4H/minute behavior cannot be reconstructed from EOD closes.
15. **No mixed-vintage score.** A row either meets its family freshness/availability contract or publishes explicit degraded basis.
16. **No graph fork.** Extend TIL/Theme Graph/Stock Identity; do not create another company-theme truth store.
17. **No earnings fork.** Consume Earnings Intelligence OS; do not rebuild transcripts, calendars or event facts inside Prophet.
18. **No alternate grader.** Reuse Evaluation OS, QLedger and existing episode rulers.
19. **No cross-era pooling.** Every definition, score, gate and feature schema is era-stamped.
20. **No LLM signal authority at birth.** Model-extracted claims and summaries can supply cited context; they cannot rank or gate until replay and forward promotion.
21. **Rights before use.** Publicly visible dashboards do not grant rights to copy constituent data, taxonomies or histories.
22. **Manual authority is explicit.** The initial V4 is a research queue for Chairman review, not an autonomous trading system.
23. **One independently useful capability per PR.**
24. **Production proof beats green CI.**
25. **The current V3 is frozen, not rewritten.** V4 replaces the live experience; V3 remains same-tape shadow evidence.

## 3. Frozen decision 1 — candidate episode identity

- Canonical unit is the **candidate episode** (masterplan §7): one security identity epoch × one structural anchor × one lifecycle; many expert events; many board observations; zero-or-one active plan lineage.
- `episode_id = pe:<security_id>:<identity_epoch>:<structural_anchor>:<generation>` — deterministic; **expert identity is never part of the episode ID** (experts attach as events).
- One active structural episode per identity epoch unless the episode contract explicitly re-arms (law 5). Re-arm only after a recorded terminal state + a new structural anchor or explicit re-arm law, with prior-episode linkage (`rearm_of`) and suppression receipts.
- Schema name frozen: **`prophet.candidate_episode/v1`** (fields per masterplan §7.7).
- Identity fields (security_id, company_id, identity_epoch) are **consumed from Stock Identity**, never minted inside Prophet.
- **Grain reconciliation with the existing Radar episode ledger (adversarial-review CRITICAL, dispositioned):** Radar already ships a RUNTIME episode ledger — `engine/entry_radar/live_ledger.py:168` `compute_episode_id(ticker, detector_id, variant, first_armed_at)`, per-(ticker, detector, variant) EPHEMERAL operational state under `/var/lib/macro-live/`, explicitly "not the durable evidence store" (`live_ledger.py:10-14`). V4's `pe:` plane is per-(security identity epoch, structural anchor) DURABLE candidate identity — a different grain and a different lifetime. B1 therefore **extends and joins; it never rebuilds or absorbs the Radar ledger**, and this paragraph is why B1 does not violate §13's "no second candidate identity plane" reject rule.
- **B1 precondition (join-key gap):** `mastermind.entry_event.v1` carries NO `episode_id` and its 21-field list is frozen (`engine/entry_radar/entry_events.py:292-314,595-598`). Before B1 executes, a merge-order ruling (wave-graph §4) must name the join owner: either Radar ships `entry_event.v2` with episode linkage (Radar WS owns that change), or B1 documents a deterministic reconstruction join on `(ticker, detector_id, signal_ts)` in its contract. B1 must not improvise this.

## 4. Frozen decision 2 — four independent state fields

Frozen enums (masterplan §9.1); server-computed, never client-inferred:

- `episode_state`: `ACTIVE, RESOLVED, INVALIDATED, EXPIRED, ARCHIVED`
- `emergence_state`: `NONE, PROBE, 1D_TURN, 4H_TURN, 2D_PRECONFLUENCE, MULTI_EXPERT, DECAYING`
- `maturity_state`: `EARLY, FORMING, CONFIRMING, CONFIRMED, AGING`
- `availability_state`: `NOT_READY, APPROACHING_ENTRY, ENTRY_OPEN, WAIT_PULLBACK, RAN_DONT_CHASE, INVALIDATED, UNAVAILABLE_DATA`

User lanes derive from `availability_state`: **Entry Open Now / Approaching Entry / Early Radar / Wait for Pullback / Ran — Don't Chase / Invalidated–Expired / All Candidates**. "Live Now" and "Setting Up" are retired labels. Maturity is displayed beside availability (`CONFIRMED · RAN`), never as the lane key. Two lane rulings the enum list alone under-determines (adversarial review, dispositioned):

- **`UNAVAILABLE_DATA` disposition:** it maps to no primary action lane by design — a row in this state is NEVER green, always remains visible in All Candidates with an explicit data-unavailable chip and named null reasons, and is counted in the board header's degraded/coverage summary. B3/B5 handoffs finalize its rendering; hiding it or defaulting it into an action lane are both violations.
- **Invalidated/Expired is the one documented two-plane lane:** it renders `availability_state = INVALIDATED` ∪ `episode_state ∈ {INVALIDATED, EXPIRED}` — kept for receipt and learning, per masterplan §9.2(6).

**Prior lifecycle authority (must compose, not re-decide):** `research/PROPHET_RULING_J9C_J10_LIFECYCLE_CELLS.md` already deleted the unreachable CONFIRMING/CONFIRMED stage constants (`engine/us_early_turn.py:960-963` names the ruling), established **`lifecycle_state` as the public plan-lifecycle vocabulary**, and produced the #5506 producer MP-1's gate G-A keys on. B3's four state fields compose with `lifecycle_state` — availability/emergence/maturity govern the pre/at-entry board truth; `lifecycle_state` (MP-1's ladder) governs the plan lifecycle view. B3's handoff writes the explicit field mapping and does not re-adjudicate what J.9(c) settled.

## 5. Frozen decision 3 — deterministic buyability authority

- `ENTRY_OPEN` is computed only from deterministic current facts (masterplan §10.2). **Prohibited inputs:** intelligence score, Fusion rank, theme strength, earnings/alt-data evidence, LLM output, 3D maturity.
- Non-waivable blockers per §10.5; an unknown required input is itself a blocker (`UNAVAILABLE_DATA`), never a pass.
- Schema name frozen: **`prophet.entry_availability/v1`** (outputs per §10.3/10.6).
- Thresholds are era-stamped presentation/operation constants (`availability-v1-2026-08-17` lineage), mutation-tested; recalibration requires a preregistered same-tape study.
- Acceptance style frozen: mutation tests must prove a poisoned score/theme/3D signal **cannot** flip a row green (masterplan §23 rows "Green means buyable", "No feedback loop").

## 6. Frozen decision 4 — V3 shadow and V4 cutover

Ratified from masterplan §6.5/§19:

1. `us_prophet_v3` history is immutable; eras are never relabeled (masterplan §6.5(6); law 19 separately forbids cross-era pooling).
2. At operational cutover, `us_prophet_v4` becomes the default board definition; the frozen V3 algorithm continues prospectively as **`us_prophet_v3_legacy_shadow`** on the same tape; V3 never receives V4 availability/graph/ranking changes.
3. `us_prophet_v2_shadow` remains owned by Conditional Fusion until its race concludes; V4 does not touch it.
4. Cutover to "primary manual research experience" is gated by the ten conditions of §19.3 (operational gate) — predictive-alpha claims separately require the full §19.4 forward gauntlet.
5. V3 remains reachable post-cutover via an **admin comparison view** (masterplan §6.5(5)) — C2 ships that surface as part of its acceptance; it is never the primary Chairman workflow.
6. Rollback is one definition switch back to the last accepted bundle and must not delete episodes, erase operator actions, restamp definitions, pool outcomes, or reset horizon clocks (§19.5).

## 7. Frozen decision 5 — all-candidate vs featured cohorts

- Nine authority steps stay distinct end to end: supported universe → research probes → technical candidate episodes → surfaced candidates → featured top-priority → entry-open → manually selected → plan-licensed → V3/model shadows.
- **No producer cap** (law 4): every qualified episode is stored, projected into `All Candidates` (complete, searchable, sortable, filterable), and graded. Featured shelf is a bounded UI projection only.
- Ledger cohorts frozen per masterplan §16.1; claim discipline per §16.2 (never quote one cohort's statistic as another's track record). Every board observation carries visibility/authority stamps (§16.3) so "was it visible when it won?" is answerable. This is the anti-TURN-WATCH clause: a card cap can never make the other names disappear from evaluation (§16.4).
- **Visibility-regime rule (adversarial review, dispositioned):** new V4 surfaces (B5's Early Desk onward) accrue in candidate-episode cohorts under their own definitions and are NEVER merged into `us_prophet_v3` board cohorts (`DNR:KILL-PROPHET-POP-MERGE` also binds); any change to the v3 board's OWN visible population mints an era/definition boundary, or C1 must partition on a visibility-regime stamp — pre-B5 and post-B5 v3 claims may not pool silently under one `board_definition`.

## 8. Frozen decision 6 — missing/coverage behavior

- Family status vocabulary frozen: `MEASURED, PARTIAL, STALE, NOT_APPLICABLE, UNAVAILABLE, ACCRUING, RIGHTS_BLOCKED, PRODUCER_DEGRADED`. A missing family never emits 0 (law 9); stale is not missing and is excluded from current scoring by default (law 10).
- Every family row publishes as-of + knowable/captured times, source receipts, quality, coverage, and null reason (envelope per masterplan §14.2).
- Priority publishes **both** raw and conservative values plus coverage ratio/band (`HIGH/MEDIUM/SPARSE/ACCRUING`); sparse rows show `PRIORITY ACCRUING` rather than a fake precise score. High coverage must not masquerade as high quality.
- Earnings family launches as `ACCRUING` until a stable EIOS contract exists (§13.4); V4 launch does not wait for EIOS.

## 9. Frozen decision 7 — canonical graph and earnings ownership

- **Theme Graph/TIL (GMI workstream)** owns company-theme relationships and theme state. V4 extends the existing stores and `config/theme_crosswalk.yml`; **no second graph** (law 16). Node/edge type extensions per masterplan §12.2; multi-label membership with probation mapping per §12.3 (no forced text-similarity mappings).
- **ThemeState v1 is deterministic and point-in-time** (§12.5–12.7; schema frozen as `theme_state/v1`) and lands in the graph owner's lane (V4-D3), not as a Prophet-local fork.
- **Earnings Intelligence OS** owns earnings events/facts/claims; V4 gets a thin versioned adapter (V4-D6) after a stable consumer contract; no transcript/calendar/event rebuild inside Prophet (law 17).
- **Stock Identity** owns identity epochs and routing interfaces; **Live Entry Radar/Terminal stack** owns expert-event production (G0/C1–C5 identities preserved, never flattened to one boolean — §8.1); **Evaluation OS/QLedger** owns outcome labels; no alternate grader (law 18).

## 10. Frozen decision 8 — ranking owner and anti-feedback boundary

- **Conditional Fusion owns cross-family ranking/fusion machinery.** V4-E1 extends the governed Fusion registry (family roles, lineage, anti-double-counting); building a second cross-family ranker is prohibited (§6.4). Fusion PR-3B→3D continues independently; V4 rebases onto its accepted registry rather than editing around it (§22.4). V4 waves are forbidden from widening PR-3B.
- Initial live V4 rank is deterministic, display-tier, explainable (§11.6): measured-family cross-sectional percentiles → capped contributions → raw + conservative priority → rank **inside availability lane** by conservative priority, then freshness, then deterministic ticker tie-break. No number is described as probability/expected return/validated edge.
- **Anti-feedback boundary (law 11):** board outputs (rank, lane, featured state, manual actions, plan status) can never re-enter any upstream feature. Enforcement is a required acceptance test (AST/runtime guard — §23 "No feedback loop"). `prohibited_inputs_absent` is a published field of `prophet.intelligence_vector/v1`.
- Schema name frozen: **`prophet.intelligence_vector/v1`** (§11.7). Model sequence frozen as staged challengers only (§15): deterministic → listwise LambdaMART (session query groups) → conditional router/multi-head → temporal heterogeneous graph (HGT/TGN) → promotion gauntlet (§15.7). No learned ranker touches production ordering before the gauntlet.

## 11. Frozen decision 9 — settlement manifest and served-bundle authority

- Settlement chain frozen (§18.1): `owed_session → source_asof → computed_asof → artifact_asof → published_asof → reader_visible_asof`; a session is `SETTLED` only when the **production reader** shows the owed source session AND the served artifact hash matches the accepted bundle.
- Schema name frozen: **`prophet.settlement_manifest/v1`** (§18.2).
- Authority ruling (§18.3): the **accepted build bundle + settlement manifest are operational truth**; Pages/served output is the user projection; Git is the archive/reproducibility projection. Every projection must identify the same bundle ID; disagreement is loud (outage/degraded state), never silent. Fail-closed checkpoints are not weakened.
- Rescue law (§18.4): idempotent, budgeted, aware of queued/in-flight runs and gate-skip successes, unable to overwrite newer sessions or fabricate a missing PIT session, receipt-emitting, reader-verifying. `scripts/prophet_rescue.py` remains the sole auto-redispatcher (existing fleet law); V4-A-lane work reconciles with it rather than creating a second rescue plane.
- Aug-14 recovery (§18.5): reconstruct only from lawfully knowable Aug-14 data, else publish an explicit missing-session receipt; never synthesize from later knowledge.

## 12. Repin deltas and reconciliation rulings (Sol snapshot `1687492` → execution main `fc0557bb`)

Full delta table: `CURRENT_STATE_2026-08-17.md` §11. Rulings taken at repin:

1. **Radar W5 is closed** (#5825/#5827, morning of 2026-08-17) — Sol's "records unwritten; PARTIAL/reconcile" row is superseded. W5's forward-evidence substrate is available to the B/C lanes; its verdicts stand as recorded (Q1 UNINFORMATIVE, Q5 PASS_SHAPED, Q2 ACCRUING) and confer no new authority.
2. **The availability incident is not historical — it is live at freeze time** (no checkpoint since 08-14; engine job failed on the last real-compute run; #5742 open). V4-A1 is therefore an active-incident recovery, and its handoff carries the live state inline.
3. **Serving-authority precision:** the user projection is the **VPS (mastermind-x.com, git-pull every ~3 min)**; GitHub Pages and R2 are mirrors — Pages deliberately lags Prophet paths by up to one cycle by design (`daily.yml:5046-5092`), and the 08-16 night proves the fence can fail in the other direction (Pages newer than git, mechanics unresolved from source). §11's ruling stands with this reading: accepted bundle + settlement manifest = operational truth; VPS = primary projection; Pages/R2 = mirrors; every projection carries the same bundle ID; disagreement is loud.
4. **MP-1 reconciliation (new estate fact Sol's plan predates):** `research/migration_packets/MP-1-prophet-board.md` is a design-authority-ratified, unexecuted migration packet for the Prophet board page, prescribing a 7-cell plan-lifecycle ladder and the re-sourcing of the card population to the plan book. **Gate status corrected by adversarial review: G-B (`.mx-ladder` in `theme.css:1940`) and G-C (frozen R3 crop set, light/dark/zh/390w) are satisfied; G-A is NOT** — the producer (#5506, `build_prophet.py:2482-2484`) merged 2026-08-14 ~17h AFTER the last published checkpoint, so `HEAD:site/prophet/index.json` carries no `lifecycle_state`/`lifecycle_counts`, and it cannot until V4-A1 lands the first recovered nightly (law 24: production proof beats merged code). **B5 therefore depends on A1's published artifact.** Ruling otherwise stands: MP-1 composes with §9's four state fields — the ladder is the *plan-lifecycle presentation* (post-entry view, `lifecycle_state` per the J.9(c) ruling); `availability_state` remains the *board-lane truth*. B3 ships the server contract; B5/E2 execute the page against MP-1 mapped onto the four state fields with design-authority sign-off, and MP-1's population re-source must be explicitly checked against `DNR:KILL-PROPHET-POP-MERGE` before execution. MP-1's §9 banned vocabulary (no "stage/阶段" in user-facing strings) binds all V4 UI copy.
5. **Candidate-volume ruling confirmed sharper:** no producer cap exists to remove; the constraining authority is the admission gate chain (upstream confluence gate + `select_candidates` tier requirement). B1 therefore *adds preservation upstream* of the narrow chain; B3/B4 relocate the chain's authority. No wave "removes the cap."
6. **Vocabulary law:** the colliding expert/stage vocabularies and same-name stores documented in `CURRENT_STATE_2026-08-17.md` §9 are binding disambiguation for every V4 handoff — prefix expert families with their system (Radar C2 vs Fusion C2), never infer era from `_v2` paths, never say bare "arena". Two additions from review: Radar's `AVAILABILITY_STATES` (`engine/entry_radar/contracts.py:106`) means *input readability* (confirmed/provisional/stale/unavailable) — a DIFFERENT fact from V4's `availability_state` (*can I buy it*); and the §8 family-status vocabulary must carry an explicit mapping to Fusion's existing terms (`absent_from_frame` → `UNAVAILABLE`; Fusion's `STRUCTURALLY EXCLUDED` — e.g. F6_MACRO_REGIME, row-constant and cross-sectionally degenerate — maps to `NOT_APPLICABLE` as a *rank family* and may only re-enter as a router/interaction axis, never as a fillable percentile).
7. **DNR confrontations opened by adversarial review (binding gates on the named waves; the registry, not this file, is the compliance surface):**
   - **`DNR:KILL-FUSED-COMPOSITE`** — Amendment 3 licenses exactly ONE fused-composite construction (the Fusion challenger under the Fusion masterplan, research/shadow tier). V4-E1's conservative-priority ordering engages this row. **Before E1 spawns**, an explicit adjudication must either establish E1 as that same construction's lineage (a Fusion-registry extension under `WS:PROPHET-CONDITIONAL-FUSION`) or append a further amendment with regenerated blocklists. Display-tier framing alone does not clear it (`DNR:HOLD-FACTOR-UNIVERSE-WIDENING` precedent: a board tiebreak is rank authority).
   - **`DNR:KILL-POSITIONING-FUSION`** — Amendment 1 confines positioning keys to the Fusion arena ONLY; fusing them into any other score remains illegal. The V4 vector's positioning/short-interest/crowding families (masterplan §11.2 families 3 and 8) therefore enter ONLY under the Fusion-registry lineage of the ruling above, or stay display/context. `DNR:HOLD-SHORT-INTEREST-LEGS` also binds. D7's positioning adapters register this confrontation by name.
   - **`DNR:KILL-WASHOUT-TURN` + Radar PR-0 fence ("depth remains context, never a requirement or monotone bonus")** — `emergence_state` is DESCRIPTIVE display vocabulary. `MULTI_EXPERT`/`2D_PRECONFLUENCE` confer no monotone ranking bonus and no availability authority; emergence depth is a prohibited rank input exactly as intelligence is a prohibited availability input.
   - **`DNR:KILL-LLM-ORIGINATION` / `DNR:KILL-LLM-FRAME-TAGS`** — law 20's "until replay and forward promotion" clock operates UNDER these rows, not over them: model-extracted text features remain display-only until the registry rows themselves are amended through adjudication. The house law stands: LLMs may only de-escalate calibrated keys.
   - **`DNR:KILL-NIGHTLY-HARD-GATE`** — A3's "publish refuses mixed bundle" must be implemented as LOUD DISCLOSURE (mismatch → outage/degraded state on the reader), never as a fail-dark publish gate that reverts `if: always()`. A3's handoff cites this row.
   - **`DNR:KILL-FRESH-TICKS-WINDOW`** — `FRESH_TICKS=2` is pinned with named mirrors (incl. `us_board_rank.py:84`); B3/B4 carry invariance receipts when relocating gate authority — changing it is an amendment, not a refactor.
   - **`DNR:KILL-PROPHET-POP-MERGE`, second clause** ("any change to the graded-board population from the trigger lane"): the lawful form is explicit — B1's episode plane and every V4 cohort accrue on the `data/us_prophet_rank/` side; the graded `data/us_board_ledger/` population is untouched until cutover mints the separate `us_prophet_v4` definition. No V4 wave modifies the v3 graded population.
   - **`DNR:KILL-OUTCOME-AUDITION`** — E4/E6 confront it by name per the Stock Identity masterplan's requirement for any Prophet-consuming routing.
   - **`DNR:KILL-OFFHORIZON-VERDICTS`** — C1's H10/H42 horizons are off the (5,21,63) grader rungs; per-claim horizon declaration through QLedger's mechanism is required, not silent new rungs.
   - **`HOLD-IGNITION-SURFACES` honest-null** — the featured shelf has a cap but NO floor: a dead tape publishes an honestly small/empty shelf, never a forced top-K.

## 13. No-rebuild boundaries (binding reject list)

Any V4 PR that creates one of the following is rejected on sight (masterplan §6.4): a second theme graph; a second transcript/earnings store; a second candidate identity plane; a second cross-family ranker beside Conditional Fusion; a second market-data WebSocket owner; a second forward grader; a second publication truth; a new lifecycle database outside AgentOS; a backfilled intraday tape manufactured from EOD data.

**This list is a summary, NOT the compliance surface.** `research/DO_NOT_REBUILD.md` (and its compiled blocklists) remains the registry of record; every V4 wave handoff greps it and confronts engaged rows BY NAME (§12.7 lists the confrontations already opened; wave-graph §4.9 makes the gate standing).

## 14. Adversarial review protocol

Every V4 PR answers the 20 questions of masterplan §24 before merge; the acceptance-test matrix of §23 is the program-level proof ledger. Wave-level gates live in `WAVE_GRAPH_AND_MERGE_ORDER.md` and each wave's handoff.
