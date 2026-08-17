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

No single `stage` or `score` may replace these planes. The 25 non-negotiable laws of masterplan §5 are ratified verbatim and are binding on every V4 wave.

## 3. Frozen decision 1 — candidate episode identity

- Canonical unit is the **candidate episode** (masterplan §7): one security identity epoch × one structural anchor × one lifecycle; many expert events; many board observations; zero-or-one active plan lineage.
- `episode_id = pe:<security_id>:<identity_epoch>:<structural_anchor>:<generation>` — deterministic; **expert identity is never part of the episode ID** (experts attach as events).
- One active structural episode per identity epoch unless the episode contract explicitly re-arms (law 5). Re-arm only after a recorded terminal state + a new structural anchor or explicit re-arm law, with prior-episode linkage (`rearm_of`) and suppression receipts.
- Schema name frozen: **`prophet.candidate_episode/v1`** (fields per masterplan §7.7).
- Identity fields (security_id, company_id, identity_epoch) are **consumed from Stock Identity**, never minted inside Prophet.

## 4. Frozen decision 2 — four independent state fields

Frozen enums (masterplan §9.1); server-computed, never client-inferred:

- `episode_state`: `ACTIVE, RESOLVED, INVALIDATED, EXPIRED, ARCHIVED`
- `emergence_state`: `NONE, PROBE, 1D_TURN, 4H_TURN, 2D_PRECONFLUENCE, MULTI_EXPERT, DECAYING`
- `maturity_state`: `EARLY, FORMING, CONFIRMING, CONFIRMED, AGING`
- `availability_state`: `NOT_READY, APPROACHING_ENTRY, ENTRY_OPEN, WAIT_PULLBACK, RAN_DONT_CHASE, INVALIDATED, UNAVAILABLE_DATA`

User lanes derive from `availability_state` only: **Entry Open Now / Approaching Entry / Early Radar / Wait for Pullback / Ran — Don't Chase / Invalidated–Expired / All Candidates**. "Live Now" and "Setting Up" are retired labels. Maturity is displayed beside availability (`CONFIRMED · RAN`), never as the lane key.

## 5. Frozen decision 3 — deterministic buyability authority

- `ENTRY_OPEN` is computed only from deterministic current facts (masterplan §10.2). **Prohibited inputs:** intelligence score, Fusion rank, theme strength, earnings/alt-data evidence, LLM output, 3D maturity.
- Non-waivable blockers per §10.5; an unknown required input is itself a blocker (`UNAVAILABLE_DATA`), never a pass.
- Schema name frozen: **`prophet.entry_availability/v1`** (outputs per §10.3/10.6).
- Thresholds are era-stamped presentation/operation constants (`availability-v1-2026-08-17` lineage), mutation-tested; recalibration requires a preregistered same-tape study.
- Acceptance style frozen: mutation tests must prove a poisoned score/theme/3D signal **cannot** flip a row green (masterplan §23 rows "Green means buyable", "No feedback loop").

## 6. Frozen decision 4 — V3 shadow and V4 cutover

Ratified from masterplan §6.5/§19:

1. `us_prophet_v3` history is immutable; eras are never relabeled (law 19).
2. At operational cutover, `us_prophet_v4` becomes the default board definition; the frozen V3 algorithm continues prospectively as **`us_prophet_v3_legacy_shadow`** on the same tape; V3 never receives V4 availability/graph/ranking changes.
3. `us_prophet_v2_shadow` remains owned by Conditional Fusion until its race concludes; V4 does not touch it.
4. Cutover to "primary manual research experience" is gated by the ten conditions of §19.3 (operational gate) — predictive-alpha claims separately require the full §19.4 forward gauntlet.
5. Rollback is one definition switch back to the last accepted bundle and must not delete episodes, erase operator actions, restamp definitions, pool outcomes, or reset horizon clocks (§19.5).

## 7. Frozen decision 5 — all-candidate vs featured cohorts

- Nine authority steps stay distinct end to end: supported universe → research probes → technical candidate episodes → surfaced candidates → featured top-priority → entry-open → manually selected → plan-licensed → V3/model shadows.
- **No producer cap** (law 4): every qualified episode is stored, projected into `All Candidates` (complete, searchable, sortable, filterable), and graded. Featured shelf is a bounded UI projection only.
- Ledger cohorts frozen per masterplan §16.1; claim discipline per §16.2 (never quote one cohort's statistic as another's track record). Every board observation carries visibility/authority stamps (§16.3) so "was it visible when it won?" is answerable. This is the anti-TURN-WATCH clause: a card cap can never make the other names disappear from evaluation (§16.4).

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
4. **MP-1 reconciliation (new estate fact Sol's plan predates):** `research/migration_packets/MP-1-prophet-board.md` is a design-authority-ratified, gate-satisfied (G-A/G-B/G-C), unexecuted migration packet for the Prophet board page, prescribing a 7-cell plan-lifecycle ladder and the re-sourcing of the card population to the plan book. Ruling: **MP-1 composes with §9's four state fields — it does not compete.** The ladder is a *plan-lifecycle presentation* (post-entry view); `availability_state` remains the *board-lane truth* (pre/at-entry view). B3 ships the server contract; B5/E2 execute the page against MP-1's specification mapped onto the four state fields, with design-authority sign-off on the mapping, and MP-1's population re-source must be explicitly checked against `DNR:KILL-PROPHET-POP-MERGE` before execution (flagged by the experience archaeology; not assumed clear). MP-1's §9 banned vocabulary (no "stage/阶段" in user-facing strings) binds all V4 UI copy.
5. **Candidate-volume ruling confirmed sharper:** no producer cap exists to remove; the constraining authority is the admission gate chain (upstream confluence gate + `select_candidates` tier requirement). B1 therefore *adds preservation upstream* of the narrow chain; B3/B4 relocate the chain's authority. No wave "removes the cap."
6. **Vocabulary law:** the four colliding expert/stage vocabularies and same-name stores documented in `CURRENT_STATE_2026-08-17.md` §9 are binding disambiguation for every V4 handoff — prefix expert families with their system (Radar C2 vs Fusion C2), never infer era from `_v2` paths, never say bare "arena".

## 13. No-rebuild boundaries (binding reject list)

Any V4 PR that creates one of the following is rejected on sight (masterplan §6.4): a second theme graph; a second transcript/earnings store; a second candidate identity plane; a second cross-family ranker beside Conditional Fusion; a second market-data WebSocket owner; a second forward grader; a second publication truth; a new lifecycle database outside AgentOS; a backfilled intraday tape manufactured from EOD data.

## 14. Adversarial review protocol

Every V4 PR answers the 20 questions of masterplan §24 before merge; the acceptance-test matrix of §23 is the program-level proof ledger. Wave-level gates live in `WAVE_GRAPH_AND_MERGE_ORDER.md` and each wave's handoff.
