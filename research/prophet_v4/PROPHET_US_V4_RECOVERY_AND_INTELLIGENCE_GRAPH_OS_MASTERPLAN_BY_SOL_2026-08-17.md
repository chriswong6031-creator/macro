# PROPHET US V4 — RECOVERY, EARLY DISCOVERY & INTELLIGENCE GRAPH OS
## End-to-End Master Plan and Architecture Freeze for Fable, Principal Orchestrator

**Author:** Sol, AI CEO of Mastermind-X  
**Chairman:** Chris Wong  
**Primary orchestrator:** Fable  
**Canonical repository:** `mastermindx-market-intelligence/macro`  
**Architecture snapshot:** 2026-08-17  
**Observed `main` at snapshot:** `16874921e6380659933252b9abc77f45d86a2b22`  
**Program class:** P0, user-facing, research + production recovery  
**Proposed AgentOS key:** `PROPHET-US-V4-RECOVERY`  
**Proposed live board definition:** `us_prophet_v4`  
**Legacy comparison definitions:** immutable `us_prophet_v3` history plus prospective `us_prophet_v3_legacy_shadow`; existing `us_prophet_v2_shadow` remains owned by Conditional Fusion until its race closes  
**Authority at initial V4 launch:** manual-research/display authority; no autonomous trade origination or sizing

---

# 0. Executive order

Prophet US must stop behaving like a late confirmation board that calls already-extended stocks “Live Now.” It must become an early-discovery and present-entry operating system:

> **Surface by emergence. Gate by the trade available now. Rank by intelligence. Explain the evidence. Let the Chairman decide.**

The finished system must:

1. produce and visibly settle every owed U.S. market session;
2. observe a broad U.S. equity universe and preserve every meaningful candidate episode rather than discarding most names before they can be ranked;
3. surface 1D, 4H, 2D and other early turn evidence before the slow 3D cascade completes;
4. make current buyability a deterministic, correction-safe fact independent from technical maturity;
5. never show a green entry state for a stock that has already run beyond its valid zone;
6. rank candidates inside their current availability lane using a broad, explainable V4 intelligence vector;
7. draw thematic strength, micro-theme acceleration, peer propagation, earnings intelligence and alternative-data evidence from their canonical upstream systems;
8. grade all candidate episodes without contaminating the official track record of featured, manually selected or plan-licensed candidates;
9. keep the current V3 system alive only as a frozen same-tape shadow after V4 cutover;
10. learn prospectively through one Evaluation OS and one promotion gauntlet.

This is not a request to add another score to the current board. It is a controlled replacement of the product’s operating model while preserving the useful existing infrastructure, experts, stores, provenance and forward evidence.

---

# 1. Chairman intent recovery

## 1.1 The actual user job

The Chairman is not asking Prophet to make an autonomous final investment decision. The Chairman’s job is:

1. see a high-recall set of potentially important stocks **while the trade is still available**;
2. identify which names combine early technical ignition with unusually strong contextual, thematic, fundamental, catalyst or alternative-data evidence;
3. manually inspect the best candidates;
4. decide which deserve watch, starter entry, full research, pass or rejection;
5. learn whether the system is consistently surfacing future winners early enough to matter.

False positives are acceptable. Missing the move until a stock is already 10–20% above its turn is not acceptable.

## 1.2 The machine job

The machine must do the work a human cannot do consistently across thousands of securities:

- continuously monitor the supported universe;
- preserve every candidate episode and every expert event;
- calculate early multi-timeframe emergence;
- calculate current entry geometry and chase risk;
- resolve security identity, corporate actions, data vintages and corrections;
- measure sector, subsector, theme and micro-theme behavior;
- connect earnings, catalysts, suppliers, customers, peers and alternative-data lobes;
- rank the research queue without pretending missing evidence is negative evidence;
- expose exact reasons, receipts and nulls;
- evaluate every version prospectively.

## 1.3 The moat

The moat is not “a StochRSI scanner.” Public screeners already combine technical and fundamental filters; public charting products already provide indicator and watchlist alerts. The moat is the governed connection between:

- early technical episode detection;
- point-in-time entry availability;
- a living multi-label economic/theme graph;
- event and earnings intelligence;
- specialized alternative-data lobes;
- per-security expert routing;
- correction-safe provenance;
- same-tape forward evaluation;
- operator feedback and manual decisions.

The external product lesson is workflow, not imitation. Finviz demonstrates the usefulness of fast integrated technical/fundamental screening and group views. TradingView demonstrates symbol-independent watchlist alerts and technical-condition alerts. Koyfin demonstrates customizable watchlist views and integrated news, filings and transcripts. Theia and S&P demonstrate the value of a dynamic, multi-label theme hierarchy and theme-performance lens. Mastermind-X must lawfully build an original system over first-party, public, licensed or otherwise rights-safe data.

## 1.4 The 10/10 end-state

At 10:35 ET, 13:10 ET or after the close, the Chairman can open Prophet V4 and immediately know:

- which market session and quote time the board represents;
- whether every critical source is current;
- which stocks just produced a 1D dot, 4H turn, 2D pre-confluence, reset turn or other preserved expert event;
- which are **Entry Open Now**, which are approaching a zone, which need a pullback and which already ran;
- the trigger time and trigger price;
- the current price, zone, stop/invalidation and risk;
- how far the stock has traveled since the earliest signal;
- technical emergence and maturity as separate facts;
- the strongest themes and micro-themes attached to the stock;
- whether those themes are accelerating, broadening, diffusing or decaying;
- peer, supplier, customer and earnings read-through;
- the V4 intelligence priority, its component evidence and its coverage;
- every important null, stale input or correction;
- what action the Chairman previously took on the episode;
- how similar historical and forward episodes performed.

No candidate disappears because a presentation cap was reached. No low-coverage candidate is silently scored as weak. No late 3D confirmation can resurrect an invalid entry. No successful GitHub workflow can hide a stale production page.

---

# 2. Why the previous program failed

## 2.1 It solved mechanisms without closing the user outcome

The Aug. 14 outage exposed a recurring organizational failure: sessions fixed a scheduler mechanism, a liveness mechanism, a scorer, an artifact or a reference UI and then called the work finished without proving that the Chairman could complete the intended task in production.

Examples:

- PR #5723 separated the two DST cron concurrency groups and improved rescue classification, but explicitly did not recover the missed session.
- PR #5026 built TURN WATCH’s data plane and receipt, while the production page was deferred.
- PR #5768 built a sophisticated five-minute Radar evaluator, but shipped it staged and not armed.
- PR #5737 built a reference UI and explicitly did not create the production template or page.
- PR #5370 built early-entry geometry and chase decay, but deliberately left the main scored gate untouched.
- Fusion PR #5813 explicitly preserved availability issue #5742 as external debt and changed no production admission, gate or plan behavior.

Infrastructure, research and product were repeatedly counted as equivalent. They are not.

## 2.2 The current board collapses independent questions

The current product tries to compress at least four different questions into one stage and one priority:

1. Is a turn beginning?
2. How mature is the confirmation?
3. Is the trade buyable at the current price?
4. Is the company/theme/catalyst unusually interesting?

That collapse produces absurd states. A stock can be technically mature but no longer buyable. A stock can be early and buyable but not yet confirmed. A stock can have exceptional intelligence evidence but no valid entry. A stock can have a valid entry but sparse contextual evidence.

V4 must represent these as independent axes.

## 2.3 The board’s server and client semantics have drifted

Current `engine/prophet_bridge.py` no longer has the historical hard 12-name production cap; `N_CANDIDATES=None` and the bridge originates every row that passes its admission gate. The observed 10–20 names are therefore primarily the result of upstream eligibility/admission, active-episode behavior and presentation—not a remaining `N_CANDIDATES=12` constant.

At the same time, the dashboard JavaScript still has fallback logic that can classify `buy_soon` as “Live now / entry window is open,” while the current bridge’s authoritative admitted statuses exclude `buy_soon` and explicitly record that it graded poorly. This is a contract split: the browser can imply an entry state the server did not authorize.

V4 must publish one server-authoritative state contract. The browser renders it; it never re-infers it.

## 2.4 The slow cascade still exerts the wrong authority

The current bridge continues to require T1/T2/T3 when `tier_cascade` is present. Early systems were added beside this admission model rather than replacing its authority. Consequently:

- early evidence can exist but fail to reach the main action surface;
- mature 3D evidence can dominate after the best trade has passed;
- the current board can optimize confirmation rather than opportunity availability.

V4 must demote 3D from front-door buyability authority to a maturity and context expert.

## 2.5 Candidate admission and track record were conflated

The fear that admitting hundreds of candidates will ruin the track record is correct only if “candidate,” “featured,” “entry open,” “manual pick” and “plan” are treated as the same cohort.

They must not be.

The correct design grades every candidate episode but keeps separate denominators and claims for:

- all probes;
- all technical candidates;
- all surfaced candidates;
- featured/top-K candidates;
- entry-open candidates;
- manually selected candidates;
- plan-licensed candidates;
- each shadow definition.

High-recall retrieval can be intentionally noisy without making the official pick record meaningless.

## 2.6 Sparse intelligence was treated as a scoring problem instead of a truth problem

A large candidate universe will contain uneven coverage. Some names have rich options, insider, earnings, theme and alternative-data evidence; others have only price, identity and sector context.

The wrong responses are:

- exclude uncovered names;
- convert missing evidence to zero;
- invent a default positive edge;
- blend stale and current features;
- let higher data coverage masquerade as higher opportunity quality.

V4 needs explicit feature-family coverage, uncertainty and fallback behavior.

## 2.7 The theme and relationship systems are not yet a complete scoring substrate

The GMI Theme Graph W3A is real and substantial: it added a Finviz/THS local theme plane, point-in-time memberships, rights gates, capability rows and graph edges. But it intentionally shipped no ThemeState, no ranking authority and no user surface. Its workstream record is also stale: it still says it is waiting for an Aug. 15 scrape even though W3A merged after that refresh. W3B—the dynamic state layer needed by Prophet—has not surfaced as a merged PR.

Earnings Intelligence is also correctly being rebuilt as a central lobe, but its current workstream is still in E0, with E1 and E2 not yet live.

V4 must consume these systems when their contracts are stable without waiting for every future lobe to finish and without duplicating their truth.

---

# 3. Verified estate and capability ledger

This ledger is a starting snapshot. Fable must refresh it from a new worktree before any implementation PR.

| Capability | Verified evidence | Status | V4 ruling |
|---|---|---:|---|
| Current Prophet committed index | `site/prophet/index.json` showed `source_asof=2026-08-13` during the incident review | **BROKEN / stale at review** | Recover exact truth; never infer health from generated time |
| Aug. 14 outage detection | Issue #5742 open under `prophet-outage` | **BROKEN** | Close only with reader-visible settlement proof |
| DST cron sibling cancellation | PR #5723 merged | **BUILT, future proof incomplete** | Preserve distinct groups; fire-drill |
| Pages/git split awareness | Fusion workstream landmine and PR #5784 | **KNOWN, unresolved architecture debt** | One settlement manifest and one served bundle hash |
| Never-stale availability workstream | `WS-PROPHET-US-AVAILABILITY.md` active but stale relative to later PRs | **PARTIAL / ledger stale** | Reconcile, do not create a duplicate rescue plane |
| Current US ranker | `us_prophet_v3` / Fusion C1 | **LIVE ordering mechanics; alpha unproven** | Freeze as legacy shadow at V4 cutover |
| Conditional Fusion W3 | PR-3A #5813 merged; PR-3B next | **IN PROGRESS** | Continue separately; V4 consumes, does not hijack |
| Early-turn union | PR #5370 merged | **PARTIAL / private-beta defects** | Reuse evidence; close B-15/B-17/B-18/B-19 before authority |
| TURN WATCH engine/artifact | PR #5026 and `site/turn_watch/turn_watch.json` | **BUILT, stale/dark** | First production early desk can consume this |
| Live Entry Radar W0–W4 | #5578, #5625, #5698, #5724, #5768 | **BUILT_NOT_PROVEN; W4 unarmed** | Activate observation-only and preserve expert identities |
| Radar W5 | workstream says code on main but records unwritten; W5 row still todo | **PARTIAL / reconcile** | Do not call forward evidence live until records and acceptance close |
| Radar W6/W7 | research priority/outcome model | **NOT BUILT** | Fold into V4 evaluation sequence; no premature probability |
| Radar W8 | #5737 open draft/reference only | **SPEC/REFERENCE ONLY** | Review and use as design input, never call shipped |
| Radar W9 | production UI | **NOT BUILT** | Ship as a real vertical capability |
| Theme graph W3A | PR #5718 merged | **BUILT, display/internal plane** | Extend canonical graph; do not fork |
| Dynamic ThemeState / transmission | no W3B PR found; stale workstream | **NOT BUILT / unreconciled** | Required V4 substrate |
| Finviz local themes | 268 local themes; rights unresolved/internal-only in W3A | **PARTIAL** | Rights-safe internal context; no proprietary redistribution |
| S&P/Theia source | no repo implementation found | **NOT BUILT** | The source is Theia Insights/TIIC/TWI; procurement/rights before ingestion |
| Earnings Intelligence OS | E0 in progress; E1/E2 todo | **SPEC/BUILD IN PROGRESS** | Consume stable event workspace later |
| Stock Identity expert routing | W2 in progress, later waves todo | **PARTIAL** | Consume when ready; no rival routing stack |
| CN Prophet V4 precedent | PR #5754 | **PROVEN DESIGN PATTERN, CN only** | Reuse “rank by intelligence, gate by entry,” not CN-specific weights |
| Broad all-name grading precedent | PR #4555 | **BUILT HISTORICAL PATTERN** | Reuse cohort separation and Evaluation OS |
| Current hard production cap | bridge now has `N_CANDIDATES=None` | **REMOVED** | Do not waste a PR removing a cap that is already gone |
| All-candidate searchable product | none | **NOT BUILT** | Required |
| Manual gate instrumentation | fragmented/insufficient | **PARTIAL** | Required for learning loop |
| V4 learned ranker | none for US | **NOT BUILT** | Challenger only after deterministic V4 |
| Temporal heterogeneous graph model | none | **NOT BUILT** | Later shadow challenger after data maturity |

---

# 4. Product thesis and value model

## 4.1 Product thesis

Prophet V4 is a high-recall research and entry operating system, not a low-recall prediction list.

Its job is to make the valuable intersection visible:

> **early technical ignition × valid current entry × high contextual potential**

The system should be willing to show noisy early candidates, because the Chairman provides the final qualitative gate. It must not be willing to call stale, extended or invalid trades buyable.

## 4.2 User value

- See moves before confirmation has consumed the opportunity.
- Review a complete candidate field instead of a tiny opaque shortlist.
- Distinguish timing from business/theme potential.
- Avoid chasing mature signals.
- Understand exactly why a candidate ranks highly.
- Move from discovery to dossier, watch, starter plan or rejection quickly.
- Revisit prior decisions and learn from outcomes.

## 4.3 Machine value

- One canonical stream of candidate episodes.
- One preserved event vocabulary for entry experts.
- One correction-safe feature envelope.
- A broad set of resolved labels for ranking research.
- Operator actions attached to the same episode identity.
- A reusable V4 context projection for Prophet, Neural Web and future agents.

## 4.4 Research/signal value

- Measure lead time and buyability, not just eventual correctness.
- Compare early expert families on the same episodes.
- Evaluate intelligence families conditionally by coverage, regime and identity.
- Learn theme diffusion and peer propagation.
- Train listwise and graph challengers on point-in-time data.
- Preserve nulls, failure states and negative evidence.

## 4.5 Commercial and distribution value

A premium Prophet should feel like an institutional research desk:

- live, current and receipt-backed;
- broad but navigable;
- configurable views and filters;
- evidence drawers and peer/theme context;
- alerts on meaningful state transitions;
- credible track record segmented by what the system actually claimed.

## 4.6 Data moat

The durable asset is the time-indexed graph of:

- candidate episodes;
- expert events;
- entry availability;
- company/theme/peer relationships;
- earnings and catalysts;
- alternative-data evidence;
- operator decisions;
- corrections and outcomes.

A generic model can be copied. That governed longitudinal data plane is much harder to reproduce.

---

# 5. Non-negotiable product and intelligence laws

1. **Every owed session settles end to end.** A workflow, build or publish job is not success until the production reader shows the owed source session.
2. **No browser-derived authority.** Lifecycle, availability, buyability and score basis are calculated server-side and rendered byte-for-byte.
3. **Candidate is not pick.** Candidate intake never implies endorsement.
4. **No producer cap.** Preserve every qualified episode; cap only a UI projection.
5. **One active structural episode per identity epoch unless the episode contract explicitly re-arms.** Multiple experts attach to the same episode.
6. **3D confirmation is maturity, not permission to buy.**
7. **Entry availability outranks score.** A high intelligence score cannot waive extension, invalidation, stale quotes or excessive risk.
8. **Intelligence ranks inside availability lanes.**
9. **Missing is not zero.** Every absent family has a named null reason and coverage effect.
10. **Stale is not missing.** Stale evidence is separately marked and normally excluded from current scoring.
11. **No feedback loop.** A board output cannot return through an upstream “opportunity” score and rank itself.
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

---

# 6. Architecture freeze

## 6.1 The core decomposition

V4 has six independent planes:

| Plane | Question | Method | Initial authority |
|---|---|---|---|
| **Discovery** | Is anything beginning to change? | Deterministic preserved expert union | High-recall candidate intake |
| **Maturity** | How confirmed is the move? | Deterministic multi-timeframe evidence | Context/display |
| **Availability** | Is the trade valid at the current price? | Deterministic geometry, risk, freshness and invalidation | Binding green-entry gate |
| **Intelligence** | How interesting/potentially asymmetric is the name? | Evidence-family vector and explainable rank | Display ordering |
| **Uncertainty** | How complete and trustworthy is the evidence? | Coverage/freshness/quality contract | Binding disclosure and fallback |
| **Outcome** | What happened after the actual surface/entry time? | Evaluation OS, path-aware labels | Promotion evidence |

No single `stage` or `score` may replace these planes.

## 6.2 V4 operating maxim

> **Discovery may be noisy. Availability must be strict. Ranking must be explainable. Promotion must be earned.**

## 6.3 Canonical authority map

- **Live Entry Radar / Terminal entry stack** owns expert event production.
- **Stock Identity** owns identity epochs, behavioral fingerprints and lawful routing interfaces.
- **Theme Graph/TIL** owns company-theme relationships and theme state.
- **Earnings Intelligence OS** owns earnings events, facts, claims and relationship deltas.
- **Alternative-data lobes** own their source facts and PIT laws.
- **Conditional Fusion** owns cross-family ranking/fusion machinery.
- **Prophet V4** owns candidate episode intake, board lifecycle, deterministic entry availability, product projection and operator workflow.
- **Evaluation OS/QLedger** owns outcome labels and promotion evidence.
- **Existing publication/auth/queue/state planes** remain canonical.

## 6.4 No-rebuild boundaries

Fable must reject any PR that creates:

- a second theme graph;
- a second transcript or earnings event store;
- a second candidate identity plane when the canonical episode store can be extended;
- a second cross-family ranker beside Conditional Fusion;
- a second market-data WebSocket owner;
- a second forward grader;
- a second publication truth;
- a new lifecycle database outside AgentOS;
- a backfilled intraday tape manufactured from EOD data.

## 6.5 V3 retirement ruling

Historical `us_prophet_v3` rows remain immutable. At V4 cutover:

1. `us_prophet_v4` becomes the default board definition.
2. The frozen V3 algorithm re-runs on the same eligible tape as `us_prophet_v3_legacy_shadow`.
3. Existing `us_prophet_v2_shadow` continues only for the Conditional Fusion race until that workstream closes or explicitly retires it.
4. V3 never receives V4 availability, graph or ranking changes.
5. V3 remains accessible to evaluators and an admin comparison view, not the primary Chairman workflow.
6. Historical eras are never relabeled.

---

# 7. Canonical candidate episode plane

## 7.1 Why episode identity is the center

A ticker is not a candidate. A detector fire is not necessarily a new candidate. A stock may have many technical observations inside one structural reversal process.

The canonical unit is a **candidate episode**:

- one security identity epoch;
- one structural setup/anchor;
- many expert events;
- one lifecycle;
- many board observations;
- one set of eventual outcomes;
- zero or more operator actions;
- zero or one active plan lineage at a time.

This prevents duplicate rows, duplicate grading and misleading counts.

## 7.2 Universe layers

V4 must distinguish:

1. **Supported universe:** securities for which identity, prices and rights permit analysis.
2. **Research probe universe:** supported securities with a thematic, earnings, alt-data or technical precursor worth monitoring.
3. **Technical candidate universe:** securities with a preserved early expert event.
4. **Entry candidate universe:** candidates whose deterministic availability is approaching or open.
5. **Featured queue:** top research priorities projected for rapid review.
6. **Manual selection:** Chairman-marked watch, starter, full research or pass.
7. **Plan-licensed set:** candidates that satisfy the separate plan contract.

The producer stores every qualified episode. The UI may show a card subset and a searchable complete table.

## 7.3 Asset-type and hygiene policy

Do not mix structurally different instruments in one rank without explicit lanes.

Default V4 supported lanes:

- U.S. common stocks;
- ADRs;
- REITs;
- ETFs, separately labeled and filterable.

Preferred shares, warrants, rights, units, acquisition shells, OTC securities and malformed/reused-ticker histories are excluded from the default equity action lanes unless a dedicated contract admits them. They may remain in a separate research-only lane.

Every row requires:

- canonical security/company identity;
- identity epoch;
- active-listing state;
- corporate-action-adjusted price basis;
- minimum history or an explicit short-history null;
- quote/data freshness;
- liquidity/fillability facts;
- source and rights status.

## 7.4 Candidate intake is a union, not a score threshold

An episode may enter the candidate plane through any registered intake family:

### Technical-emergence intake
- G0 Grey Dot parity event;
- 1D StochRSI washed turn with RSI-MACD improvement;
- 4H turn;
- fresh 2D pre-confluence while 3D has not crossed;
- leader reset;
- structural pullback and pivot defense;
- basket/theme turn attached to a technically eligible member;
- other preserved Radar experts after registry admission.

### Contextual probe intake
- theme/micro-theme acceleration;
- earnings or guidance inflection;
- peer read-through;
- material alternative-data change;
- significant catalyst with a technically plausible setup.

Contextual probes do not become green entries without technical and availability facts.

## 7.5 No hard candidate cap

The old 12-row bridge cap is already removed. V4 must not reintroduce a hidden producer cap.

Projection rules:

- `All Candidates`: complete, searchable, sortable, paginated/virtualized;
- `Featured`: bounded UI shelf based on lane and priority;
- `New Today`: all newly opened episodes;
- `Needs Review`: user-specific unreviewed queue;
- alerts: state transitions, not only top-K rank.

Candidate volume is monitored as a product metric, not controlled by deleting evidence.

## 7.6 Episode creation and re-arm

A deterministic `episode_id` must include:

- canonical security ID;
- identity epoch;
- structural anchor ID/date;
- episode generation/version.

Expert identity is **not** part of the episode ID. Experts attach as events.

Re-arm is permitted only after a recorded terminal state and a new structural anchor or explicit re-arm law. The system must record:

- prior episode;
- reason for resolution/expiry/invalidation;
- new anchor;
- relationship to the prior episode;
- re-arm eligibility and suppression receipts.

## 7.7 Proposed contract: `prophet.candidate_episode/v1`

```json
{
  "schema": "prophet.candidate_episode/v1",
  "episode_id": "pe:security_epoch:anchor:version",
  "security_id": "sec:...",
  "company_id": "co:...",
  "ticker_at_observation": "XYZ",
  "identity_epoch": "ie:...",
  "opened_at": "2026-08-17T14:35:00Z",
  "opened_session": "2026-08-17",
  "intake_classes": ["technical_emergence", "theme_probe"],
  "structural_anchor": {
    "kind": "confirmed_pivot_low",
    "time": "2026-08-14T19:55:00Z",
    "price": 42.10,
    "basis": "adjusted",
    "source_receipt": "..."
  },
  "expert_events": ["ee:..."],
  "episode_state": "active",
  "terminal_reason": null,
  "rearm_of": null,
  "definition_era": "candidate-episode-v1",
  "created_by": "canonical_candidate_intake",
  "correction_state": "current"
}
```

---

# 8. Technical emergence and expert architecture

## 8.1 Preserve experts; do not flatten them

The existing Radar contract correctly preserves G0/C1–C5 expert identities. V4 consumes their event stream. It must never reduce them to one generic `entry_signal=true`.

Minimum expert families:

- **G0:** exact Grey Dot parity expert;
- **C1:** 1D washed-turn expert;
- **C2:** 4H/1D/2D multi-timeframe challengers, preserved by variant;
- **C3:** structural/pullback expert;
- **C4:** context-only expert;
- **C5/G0 nightly:** slow confirmation and nightly context;
- **Legacy 3D cascade:** preserved as maturity baseline;
- **TURN WATCH triggers:** daily dot, 2D-before-3D, basket turn, leader reset.

## 8.2 Early evidence must be visible before promotion

The product does not need to wait for an expert to prove predictive alpha before showing that the expert fired. It must clearly label authority:

- `OBSERVED`;
- `PROVISIONAL`;
- `CONFIRMED`;
- `RETRACTED`;
- `ACCRUING`;
- `PROMOTED`.

The Chairman accepts early noise. The system must provide the cost and uncertainty honestly.

## 8.3 Close the known early-lane defects

Before an early event can control a green entry or plan:

- **B-15:** open-bucket repaint must be prevented or correction-receipted;
- **B-16:** schema/version/manifest consistency must be closed;
- **B-17:** the measured naked-union roster and the shipped roster must be explicitly separated;
- **B-18:** deck/plan licensing invariants must be repaired and tested;
- **B-19:** dead-signal chase attachment must be impossible;
- lifecycle states such as confirming, aging, expired and re-armed must be reachable and tested;
- every relevant row must carry an admission/authority class.

## 8.4 Event contract

Every event needs:

- expert family and version;
- symbol identity and episode ID;
- event time;
- observation time;
- source bar close/knowability;
- provisional/confirmed/retracted state;
- indicator values and exact calculation source;
- price basis;
- field provenance;
- correction/revision lineage;
- no score or promotion claim unless separately authorized.

## 8.5 Intraday honesty

- Five-minute Radar uses the canonical market-data owner.
- Extended-hours treatment is explicit.
- Session-final partial bars are identified.
- No EOD reconstruction of intraday observations.
- Missing minutes produce a dark/null expert reading, not a fabricated event.
- A full RTH session must be observed before W4 is called operational.

---

# 9. Orthogonal lifecycle and board state

## 9.1 Do not use one linear stage

Publish four independent state fields:

### `episode_state`
`ACTIVE`, `RESOLVED`, `INVALIDATED`, `EXPIRED`, `ARCHIVED`

### `emergence_state`
`NONE`, `PROBE`, `1D_TURN`, `4H_TURN`, `2D_PRECONFLUENCE`, `MULTI_EXPERT`, `DECAYING`

### `maturity_state`
`EARLY`, `FORMING`, `CONFIRMING`, `CONFIRMED`, `AGING`

### `availability_state`
`NOT_READY`, `APPROACHING_ENTRY`, `ENTRY_OPEN`, `WAIT_PULLBACK`, `RAN_DONT_CHASE`, `INVALIDATED`, `UNAVAILABLE_DATA`

The primary board lanes are derived from `availability_state`, not maturity.

## 9.2 User-facing lanes

1. **Entry Open Now** — current executable price passes the deterministic availability contract.
2. **Approaching Entry** — fresh episode near the zone but not yet open.
3. **Early Radar** — early expert evidence; availability may be not ready.
4. **Wait for Pullback** — thesis/confirmation may be intact, but current price is too extended.
5. **Ran — Don’t Chase** — move has traveled beyond the allowed geometry.
6. **Invalidated/Expired** — kept for receipt and learning.
7. **All Candidates** — complete table across states.

“Live Now” must be retired as an ambiguous label. Green means only `ENTRY_OPEN`.

“Setting Up” must be retired or redefined as `APPROACHING_ENTRY`; a stock already above its zone cannot remain in it.

## 9.3 Maturity is shown beside availability

Examples:

- `EARLY · ENTRY OPEN`;
- `FORMING · APPROACHING`;
- `CONFIRMED · WAIT PULLBACK`;
- `CONFIRMED · RAN`;
- `EARLY · INVALIDATED`.

This removes the false assumption that later maturity is automatically more actionable.

---

# 10. Deterministic entry-availability and chase firewall

## 10.1 Binding principle

> A stock is buyable because the current trade geometry is valid—not because the signal is old, mature, high scoring or exciting.

## 10.2 Inputs

The availability engine may use only deterministic and current facts:

- current executable price and quote age;
- structural anchor and invalidation;
- entry zone;
- distance to zone;
- risk to invalidation;
- move since earliest trigger;
- move since anchor/reset low;
- ATR/volatility-normalized extension;
- gap behavior;
- recent velocity and parabolic extension;
- liquidity, spread and slippage;
- episode age;
- source health;
- corporate-action basis;
- session/extended-hours rules.

Intelligence, theme strength and alt-data scores are prohibited inputs.

## 10.3 Required outputs

- `availability_state`;
- `entry_open` boolean;
- `zone_low`, `zone_high`;
- `current_price_basis`;
- `distance_to_zone_pct`;
- `risk_to_invalidation_pct`;
- `move_since_first_trigger_pct`;
- `move_since_anchor_pct`;
- `extension_atr`;
- `chase_state`;
- `invalidation_price` and basis;
- `availability_reasons`;
- `availability_blockers`;
- `evaluated_at`;
- quote/source freshness;
- null reasons.

## 10.4 Initial deterministic geometry

Fable must not copy a universal 10% rule into every stock. The first contract should combine:

- structural-risk ceiling;
- price-zone relation;
- volatility-normalized extension;
- episode freshness;
- move since first event;
- gap/velocity protection;
- liquidity/fillability.

Thresholds are presentation/operation constants until evaluated. They are era-stamped and mutation-tested. Any later calibration requires a preregistered same-tape study.

## 10.5 Non-waivable blockers

A row cannot be `ENTRY_OPEN` when:

- current price is above the allowed zone/extension;
- structural invalidation has occurred;
- quote or critical price data is stale;
- risk to invalidation exceeds the lane ceiling;
- liquidity/fillability fails;
- corporate-action basis is ambiguous;
- the event was retracted;
- the episode expired;
- a required deterministic input is unknown.

No ranker, LLM, theme score, earnings score or 3D confirmation may waive these blockers.

## 10.6 Proposed contract: `prophet.entry_availability/v1`

```json
{
  "schema": "prophet.entry_availability/v1",
  "episode_id": "pe:...",
  "evaluated_at": "2026-08-17T15:10:00Z",
  "market_session": "2026-08-17",
  "state": "ENTRY_OPEN",
  "entry_open": true,
  "zone": {"low": 41.80, "high": 43.25, "basis": "adjusted"},
  "current_price": 42.70,
  "quote_age_seconds": 8,
  "invalidation": {"price": 40.95, "kind": "structural"},
  "risk_to_invalidation_pct": 4.10,
  "move_since_first_trigger_pct": 2.35,
  "move_since_anchor_pct": 1.43,
  "extension_atr": 0.48,
  "chase_state": "not_chased",
  "blockers": [],
  "reasons": ["inside_zone", "risk_within_limit", "fresh_quote"],
  "definition": "availability-v1-2026-08-17",
  "source_receipts": ["..."]
}
```

---

# 11. V4 intelligence vector

## 11.1 Ranking question

After availability is known, V4 asks:

> Among candidates in the same actionable/research lane, which deserve the Chairman’s attention first?

## 11.2 Family architecture

The V4 vector should support at least these independent evidence families:

1. **Theme and graph acceleration**
2. **Earnings, revisions and catalyst**
3. **Alternative data and positioning**
4. **Fundamental quality and financial trajectory**
5. **Relative strength and structural quality**
6. **Peer and supply-chain propagation**
7. **Scarcity, asymmetry and optionality**
8. **Fragility, crowding and risk**
9. **Security-specific expert fit** from Stock Identity when proven
10. **Market/regime context**

Technical emergence and current availability remain separate fields. They can define lane and provide explanatory features; they do not get blended into an opaque “quality probability.”

## 11.3 Broad base coverage

All valid technical candidates should receive a base evidence envelope from broadly available sources:

- price and structural context;
- sector/industry relative performance;
- market regime;
- liquidity/volatility;
- basic company identity;
- available theme memberships.

Richer theme, earnings and alt-data families extend the vector. They do not determine whether a row exists.

## 11.4 Missing-data law

Every family emits one of:

- `MEASURED`;
- `PARTIAL`;
- `STALE`;
- `NOT_APPLICABLE`;
- `UNAVAILABLE`;
- `ACCRUING`;
- `RIGHTS_BLOCKED`;
- `PRODUCER_DEGRADED`.

A missing family never emits `0`.

## 11.5 Coverage and uncertainty

Publish:

- total registered family weight;
- measured family weight;
- evidence coverage ratio;
- stale share;
- rights-blocked share;
- family disagreements;
- score uncertainty or interval;
- fallback basis.

The UI must show `High`, `Medium`, `Sparse` or `Accruing` coverage beside the priority.

## 11.6 Initial explainable priority

The initial live V4 rank must be deterministic and display-tier.

Recommended construction:

1. Convert each measured family output to an as-of-session cross-sectional percentile.
2. Use the governed Conditional Fusion registry for family roles, lineage and anti-double counting.
3. Cap any one family’s contribution.
4. Aggregate only measured families.
5. Calculate a raw priority and a conservative priority that reflects coverage/uncertainty.
6. Rank **inside availability lane** by conservative priority, then freshness, then deterministic ticker tie-break.
7. Rows below a minimum evidence floor remain visible with `PRIORITY ACCRUING`; they do not receive a fake precise score.
8. Publish all family contributions and exclusions.

No initial number should be described as probability, expected return or validated edge.

## 11.7 Proposed contract: `prophet.intelligence_vector/v1`

```json
{
  "schema": "prophet.intelligence_vector/v1",
  "episode_id": "pe:...",
  "asof": "2026-08-17T15:10:00Z",
  "definition": "us-prophet-v4-intel-v1",
  "families": {
    "theme_graph": {
      "status": "MEASURED",
      "percentile": 91.2,
      "value": 0.74,
      "fresh_asof": "2026-08-17",
      "receipts": ["..."]
    },
    "earnings": {
      "status": "ACCRUING",
      "percentile": null,
      "null_reason": "canonical_event_workspace_not_live"
    },
    "altdata_positioning": {
      "status": "UNAVAILABLE",
      "percentile": null,
      "null_reason": "no_eligible_source_for_security"
    }
  },
  "raw_priority": 82.4,
  "conservative_priority": 74.1,
  "coverage_ratio": 0.63,
  "coverage_band": "MEDIUM",
  "uncertainty": 0.18,
  "top_positive_contributors": ["theme_graph", "relative_strength"],
  "top_risks": ["crowding"],
  "prohibited_inputs_absent": ["board_rank", "manual_action", "future_return"]
}
```

---

# 12. Theme, subsector and micro-theme graph

## 12.1 Product outcome

Every candidate should inherit explainable context from every lawful relationship:

- sector;
- industry;
- subsector;
- major theme;
- micro-theme;
- curated basket;
- product/technology;
- customer;
- supplier;
- competitor;
- geographic and policy exposure;
- earnings/catalyst relationship.

The graph must answer:

- Which themes are accelerating now?
- Is performance broad or concentrated in one leader?
- Are early entry events diffusing across members?
- Are peers confirming the move?
- Which micro-theme is heating before the broad sector?
- Is the candidate leading, confirming or lagging its theme?
- Did an earnings event propagate to related companies?
- Is the movement real after volatility and benchmark normalization?

## 12.2 Canonical graph extension

Extend existing TIL/Theme Graph stores and `config/theme_crosswalk.yml`. Do not create another graph database merely for V4.

Initial node types:

- region;
- country;
- sector;
- industry;
- subsector;
- major theme;
- micro-theme;
- curated basket;
- company;
- security;
- product/technology;
- customer/supplier;
- event;
- earnings concept;
- policy/catalyst.

Initial edge types:

- `CONTAINS`;
- `MEMBER_OF`;
- `EXPOSED_TO`;
- `EXPRESSES`;
- `RELATED_TO`;
- `SUPPLIER_TO`;
- `CUSTOMER_OF`;
- `COMPETITOR_OF`;
- `BENEFITED_BY`;
- `THREATENED_BY`;
- `CONFIRMS`;
- `CONTRADICTS`;
- `READ_THROUGH_TO`.

Every edge needs source, rights, observed time, valid time, confidence/authority and correction lineage.

## 12.3 Multi-label membership

A company may belong to many themes. Membership may be:

- curated binary;
- provider classification;
- quantified exposure;
- inferred proposal;
- confirmed relation.

Never force a local source taxonomy into canonical IDs solely by text similarity or overlap. W3A correctly keeps Finviz local themes separate and places uncertain mappings in probation.

## 12.4 Theia/S&P source ruling

The Chairman’s remembered “S&P/Theia” source is real:

- S&P’s Thematics Dashboard uses Theia Insights’ multi-level TIIC hierarchy.
- Theia publicly describes 245 major themes, 3,200+ micro themes, multi-label company exposures and daily Theme Watch Indices across 200+ themes.

This is a valuable benchmark and potential licensed source. It is not permission to scrape or redistribute a proprietary taxonomy or constituent dataset.

Fable must create a source/procurement decision:

- public aggregate dashboard: benchmark/display research only under terms;
- licensed TIIC/TWI feed: canonical external classification/control source if purchased;
- no entitlement: build original classifications from lawful first-party/public sources and preserve Theia only as competitor methodology research.

## 12.5 Deterministic ThemeState v1

Before any neural model, ship point-in-time deterministic theme features.

### Performance
- 1D, 5D, 10D, 20D, 63D total return;
- excess return versus SPY;
- excess return versus sector;
- volatility-normalized return;
- drawdown and distance from high.

### Velocity and acceleration
- change in relative-strength slope;
- change in normalized return velocity;
- second difference/acceleration;
- acceleration persistence;
- inflection/changepoint probability as research context.

### Breadth
- share of valid members positive over each horizon;
- share above 20/50/200-day averages;
- share with rising relative strength;
- share with early expert events;
- share with entry-open episodes;
- new highs/new lows;
- member coverage and stale share.

### Diffusion and leadership
- number of participating members;
- number of participating subthemes;
- concentration/entropy of contribution;
- leader/median spread;
- laggard catch-up;
- small-cap/large-cap diffusion;
- cross-region confirmation.

### Flow and attention, where lawful
- volume/turnover acceleration;
- news/event density;
- earnings surprise diffusion;
- alternative-data corroboration;
- options/positioning context.

### Quality and stability
- membership vintage;
- small-N shrinkage;
- outlier-robust median/trimmed measures;
- source corroboration;
- rights and coverage state;
- theme half-life/decay.

## 12.6 Normalization laws

- Compare absolute and relative performance.
- Normalize by security/theme volatility.
- Use robust cross-sectional ranks and winsorized values.
- Publish equal-weight and exposure-weight views separately.
- Require point-in-time membership.
- Do not backfill a later-discovered member into earlier dates.
- Shrink or abstain on small member counts.
- Separate unavailable members from negative members.
- Detect corporate actions and reused-ticker contamination.

## 12.7 Proposed contract: `theme_state/v1`

```json
{
  "schema": "theme_state/v1",
  "theme_id": "theme:...",
  "asof": "2026-08-17T20:00:00Z",
  "membership_vintage": "2026-08-15",
  "member_count": 34,
  "priced_member_count": 31,
  "coverage": 0.912,
  "performance": {
    "excess_5d_vs_spy": 0.031,
    "excess_20d_vs_sector": 0.082,
    "vol_normalized_10d": 1.47
  },
  "dynamics": {
    "velocity": 0.68,
    "acceleration": 0.31,
    "persistence": 0.74,
    "decay_risk": 0.16
  },
  "breadth": {
    "positive_5d": 0.71,
    "rising_rs": 0.65,
    "early_event_share": 0.29,
    "entry_open_share": 0.12
  },
  "diffusion": {
    "subthemes_participating": 6,
    "leadership_entropy": 0.79,
    "leader_median_spread": 0.11
  },
  "authority": "display",
  "rights_state": "internal_allowed",
  "receipts": ["..."]
}
```

---

# 13. Earnings Intelligence integration

## 13.1 Ownership

Earnings Intelligence OS is the canonical owner. Prophet must not rebuild:

- calendars;
- transcript ingestion;
- event identity;
- company-event joins;
- claim extraction;
- earnings facts;
- peer relationship deltas.

## 13.2 V4 adapter

A thin, versioned adapter consumes stable Earnings Intelligence outputs and emits only Prophet-ready evidence:

- latest canonical event ID;
- event recency;
- reported-vs-expected facts;
- guidance direction and revisions;
- estimate/revision trajectory;
- management claim changes;
- transcript evidence links;
- post-event price/volume incorporation;
- peer/theme earnings diffusion;
- next catalyst;
- event correction/completeness state.

## 13.3 Authority

Deterministic facts may contribute to display ranking after PIT/freshness validation.

Model-extracted claims:

- must link to exact evidence;
- remain context/display initially;
- cannot originate a trade or create entry availability;
- cannot rank until replay and prospective promotion.

## 13.4 Dependency behavior

V4 core does not wait for EIOS completion.

Until a stable contract is live:

- the earnings family is `ACCRUING`;
- coverage is explicit;
- no default score is inserted;
- the board remains usable from technical, theme and other evidence.

---

# 14. Alternative-data intelligence hub integration

## 14.1 First task: authoritative census

The repo contains many alternative-data and contextual lobes but no single verified US “Alt Data Hub” owner was found in this archaeology. Fable must not invent one from memory.

Create an estate census of every potential family:

- producer and path;
- canonical identifier;
- source and rights;
- update cadence;
- PIT/knowability law;
- historical depth;
- current coverage;
- correction behavior;
- current authority;
- existing Evaluation OS registration;
- whether the family already enters Conditional Fusion.

Likely families include—but must be verified rather than assumed—short interest, insider activity, options/positioning, government revenue/procurement, capital structure, catalysts, bio events, filings, fundamentals, attention and other domain lobes.

## 14.2 Canonical evidence-family envelope

Every lobe adapter must emit:

```json
{
  "family_id": "short_interest",
  "security_id": "sec:...",
  "value": 0.42,
  "asof": "2026-08-12",
  "knowable_at": "2026-08-17T12:00:00Z",
  "captured_at": "2026-08-17T12:10:00Z",
  "freshness_state": "CURRENT",
  "coverage_state": "MEASURED",
  "quality_state": "PASS",
  "rights_state": "INTERNAL_ALLOWED",
  "null_reason": null,
  "source_receipts": ["..."],
  "definition": "..."
}
```

## 14.3 No universal coverage requirement

Alternative data is often sparse by design. The system must distinguish:

- not covered;
- not applicable;
- covered with neutral evidence;
- covered with positive evidence;
- covered with negative evidence;
- stale;
- degraded.

## 14.4 Conditional use

Some families may be useful only for:

- certain sectors;
- certain liquidity regimes;
- certain market caps;
- certain episode types;
- certain identity/behavioral clusters.

This is the proper role of Conditional Fusion and Stock Identity routing. Do not average every family over every stock.

## 14.5 No vague sentiment authority

Generic LLM sentiment, summaries or “bullishness” cannot rank a stock simply because text exists. Text-derived features must be specific, evidence-linked and evaluated, such as:

- guidance increase/decrease;
- demand wording change;
- capacity expansion;
- customer concentration change;
- procurement win;
- regulatory milestone;
- revision/correction.

---

# 15. Ranking and model system

## 15.1 V4 is a model system, not one monolith

### Stage 1 — deterministic high-recall retrieval
Union of preserved technical experts and contextual probes.

### Stage 2 — deterministic episode/lifecycle and buyability
Binding authority for `ENTRY_OPEN`, `WAIT_PULLBACK`, `RAN` and invalidation.

### Stage 3 — explainable V4 evidence rank
Family percentiles and conservative priority, display-tier.

### Stage 4 — learned listwise ranker challenger
XGBoost LambdaMART/`rank:ndcg` or equivalent, grouped by as-of session, trained on point-in-time episode rows.

### Stage 5 — conditional router/multi-head challenger
Regime, identity, coverage and episode-type routing; separate selection, asymmetry, fragility and confidence heads.

### Stage 6 — temporal heterogeneous graph challenger
HGT/TGN-style model over time-stamped nodes, relationships and events.

Each stage has its own definition, feature manifest, ledger and promotion gate.

## 15.2 Why listwise learning is appropriate later

The product’s question is not merely “will this stock go up?” It is “which candidates in today’s queue deserve the top positions?”

Learning-to-rank supports day/session query groups and top-K metrics such as NDCG. Official XGBoost documentation describes LambdaMART ranking grouped by query ID and `rank:ndcg`, including top-K pair construction. That matches the eventual research problem better than an ungrouped probability model.

It is still a challenger, not the first live V4.

## 15.3 Training unit

One training row is one candidate-episode observation at an exact as-of time.

Group/query ID:

- daily nightly model: market session;
- intraday model: decision timestamp bucket, only when enough real observations exist.

No random row split.

## 15.4 Labels

Labels are calculated from the **actual surface or valid-entry price**, never from the future trough.

Multi-head outcomes:

- future MFE and MAE;
- risk-normalized R;
- stop/invalidation survival;
- excess return versus SPY;
- H10/H21/H42/H63 outcomes;
- time to maximum favorable move;
- future entry availability duration;
- false bounce;
- fragility/correction;
- opportunity relevance grade.

A possible ordinal relevance label can be derived from preregistered path rules, but raw path outcomes remain stored.

## 15.5 Time-safe validation

- walk-forward/date-grouped folds;
- embargo/purge for overlapping outcome horizons;
- point-in-time feature and membership joins;
- frozen feature manifest;
- no tuning on forward race outcomes;
- independent shadow accrual;
- regime and coverage strata;
- era breaks on contract change.

## 15.6 Metrics

Operational/product:

- source-to-reader latency;
- early-event-to-surface latency;
- candidate volume;
- review burden;
- buyable-at-first-surface rate;
- chase rate;
- median distance from anchor;
- median lead versus V3.

Ranking:

- NDCG@10/@30;
- precision of strong outcomes at K;
- recall of future strong outcomes;
- rank IC and stability;
- sector/theme concentration;
- turnover;
- coverage-stratified performance.

Trade-path:

- MFE/MAE;
- R distribution;
- stop survival;
- false-bounce rate;
- excess return;
- tail loss;
- time to payoff.

Learning:

- manual watch/promote/reject rates;
- time to review;
- alert usefulness;
- feature coverage and drift;
- correction rate.

## 15.7 Initial learned-ranker gate

No learned ranker becomes live from a backtest alone. Promotion requires:

- point-in-time replay;
- date-grouped OOS;
- enough independent sessions and resolved episodes determined by pre-registered power analysis;
- no hidden coverage selection;
- forward shadow evidence;
- no material degradation in early-surface or chase metrics;
- adversarial review;
- Chairman/Sol adjudication.

## 15.8 Temporal graph challenger

The graph model is appropriate only after the deterministic graph is correct.

Candidate approaches:

- **Heterogeneous Graph Transformer:** typed nodes/edges and temporal encoding;
- **Temporal Graph Network:** sequences of time-stamped events and memory;
- simpler graph embeddings and message-passing baselines.

Potential tasks:

- predict theme acceleration continuation;
- rank candidate episodes;
- estimate peer read-through;
- detect emerging clusters.

Required preconditions:

- stable canonical identity;
- point-in-time memberships;
- sufficient graph snapshots/events;
- correction-safe event timestamps;
- deterministic graph-feature baseline;
- no rights ambiguity;
- estimability by node/edge type.

The graph model remains shadow until it beats deterministic and LambdaMART challengers prospectively under the same ruler.

---

# 16. Track record and forward ledger design

## 16.1 One episode, many cohorts

Every episode is graded once under common outcome rules and projected into cohorts.

Required cohorts:

- `probe_all`;
- `technical_candidate_all`;
- `surface_all`;
- `featured_top_k`;
- `entry_open_all`;
- `manual_watch`;
- `manual_promote`;
- `manual_reject`;
- `plan_licensed`;
- `us_prophet_v4`;
- `us_prophet_v3_legacy_shadow`;
- existing Fusion shadows;
- each model challenger.

## 16.2 Claim discipline

Examples:

- “Candidate recall” may use `technical_candidate_all`.
- “Featured precision” may use `featured_top_k`.
- “Chairman selections” may use `manual_promote`.
- “Prophet plan performance” may use `plan_licensed`.
- “V4 versus V3 ranking” must use same-tape rows and exact definitions.

Never quote one cohort’s attractive statistic as another cohort’s track record.

## 16.3 Visibility and authority stamps

Every board observation records:

- candidate present;
- surface visible;
- lane;
- position;
- featured state;
- entry state;
- score and coverage;
- model/definition;
- manual action;
- plan status.

This resolves whether a future winner was technically in a store but invisible to the operator.

## 16.4 No presentation-cap survivorship

All rows beyond the featured card shelf remain in `All Candidates` and in the ledger. A 40-card cap cannot make the other 791 TURN WATCH names disappear from evaluation.

## 16.5 Manual feedback

Store:

- viewed;
- opened dossier;
- marked watch;
- promoted;
- passed;
- rejected with reason;
- note;
- plan created.

Manual behavior is not automatically a training label. Operator selection creates exposure/position bias. Any use in learning must be separately debiased and preregistered.

---

# 17. Production experience architecture

## 17.1 One Prophet, several coherent views

Prophet V4 should present one product shell with linked views:

1. **Action Desk**
2. **Early Radar**
3. **All Candidates**
4. **Themes & Propagation**
5. **Track Record**
6. **Health & Receipts** for authorized operators

The Radar engine remains its own producing workstream. The product can consume its events without duplicating them.

## 17.2 Board header

Always show:

- market session;
- quote/evaluation time;
- source session;
- freshness status;
- current/degraded/stale/unavailable;
- number of all active episodes;
- number of new episodes;
- number entry-open;
- number approaching;
- number wait-pullback/ran;
- feature coverage summary;
- board/model definition;
- correction banner.

## 17.3 Card anatomy

Each card must show:

### Identity
- ticker/company;
- sector/subsector;
- top themes/micro-themes;
- asset type.

### Availability
- current price;
- zone;
- distance to zone;
- invalidation;
- risk;
- state and blockers.

### Timing
- earliest event/time/price;
- latest event;
- move since first event;
- 1D/4H/2D/3D timeline;
- maturity.

### Intelligence
- V4 priority;
- coverage band;
- top positive families;
- top risks;
- theme acceleration;
- catalyst/earnings state.

### Provenance
- source clock;
- provisional/corrected markers;
- nulls.

### Actions
- open dossier;
- watch;
- pass;
- reject;
- promote;
- create/open signal analysis.

## 17.4 Drawer/dossier

The detailed view should answer:

- Why did it enter the candidate plane?
- Why is the trade available or blocked?
- What happened since the first event?
- Which themes and peers are moving?
- What intelligence evidence is measured?
- What evidence is missing?
- What would invalidate the setup?
- What similar episodes occurred?
- What did the Chairman do?

## 17.5 All Candidates table

Required:

- search;
- multi-column sort;
- saved views;
- filters by lane, expert, theme, sector, asset type, score, coverage and freshness;
- complete row count;
- no client-only hidden authority;
- virtualized performance;
- export limited by rights and auth.

## 17.6 Alerts

Alert on transitions:

- new early event;
- `APPROACHING_ENTRY`;
- `ENTRY_OPEN`;
- `WAIT_PULLBACK`;
- re-entry;
- invalidation;
- material priority/theme acceleration change;
- stale/degraded source.

Alerts operate on a candidate/watchlist set and each symbol’s state independently. They must not depend on being featured top-K.

## 17.7 Mobile and desktop proof

Production acceptance includes:

- desktop wide;
- laptop;
- tablet;
- 390px mobile;
- no horizontal overflow;
- keyboard and screen-reader basics;
- stale/degraded/empty/partial/correction states;
- large candidate counts.

---

# 18. Availability, settlement and publication architecture

## 18.1 One settlement chain

For every owed NYSE session:

`owed_session → source_asof → computed_asof → artifact_asof → published_asof → reader_visible_asof`

The session is `SETTLED` only when `reader_visible_asof >= owed_session` and the served artifact hash matches the accepted build bundle.

## 18.2 Proposed `prophet.settlement_manifest/v1`

```json
{
  "schema": "prophet.settlement_manifest/v1",
  "owed_session": "2026-08-14",
  "source_asof": "2026-08-14",
  "computed_at": "2026-08-15T01:10:00Z",
  "board_definition": "us_prophet_v4",
  "candidate_count": 286,
  "artifact_hashes": {
    "candidate_store": "...",
    "board": "...",
    "index": "...",
    "theme_state": "..."
  },
  "publish": {
    "bundle_id": "...",
    "pages_deployment": "...",
    "git_archive_commit": null
  },
  "reader_proof": {
    "checked_at": "...",
    "served_bundle_id": "...",
    "source_asof": "2026-08-14",
    "status": "PASS"
  },
  "status": "SETTLED",
  "failures": []
}
```

## 18.3 Git and Pages roles must be explicit

The 2026-08-16 split proved that Git and Pages can disagree.

Fable must freeze one operational authority:

- the accepted build bundle and settlement manifest are the operational truth;
- Pages/served output is the user projection;
- Git is an archive/reproducibility projection unless the existing canonical store contract explicitly says otherwise.

Do not weaken fail-closed checkpoints. Instead, make every projection identify the same bundle hash and make disagreement loud.

## 18.4 Rescue

Rescue is:

- idempotent;
- budgeted;
- aware of queued/in-progress runs;
- aware of gate-skip successes;
- unable to overwrite newer sessions;
- unable to fabricate a missing PIT session;
- required to emit a receipt;
- required to verify the reader.

## 18.5 Aug. 14 recovery

Recover the exact session only from data lawfully knowable for Aug. 14. If exact reconstruction is impossible:

- publish an explicit unavailable/missing-session receipt;
- do not synthesize Aug. 14 using Aug. 17 knowledge;
- preserve the gap in the ledger.

## 18.6 Done bar

Availability is not done after one green night. It requires:

- a full market week;
- every listed fault injection;
- catch/heal/escalate within deadline;
- no human-discovered stale board;
- reader-visible proof;
- reconciliation of AgentOS status.

---

# 19. Migration and cutover

## 19.1 Parallel operation

Build V4 beside V3 until operational cutover.

- same source tape;
- same eligible universe snapshot where comparable;
- separate board definitions;
- separate rank columns;
- common episode/outcome plane;
- no mixed-era statistics.

## 19.2 Cutover sequence

1. Restore availability and settlement.
2. Ship canonical candidate episodes.
3. Ship server-authoritative lifecycle/availability.
4. Ship Early Radar/All Candidates product.
5. Activate Radar observation-only.
6. Ship V4 explainable priority.
7. Prove production over live sessions.
8. Make V4 default manual-research board.
9. Freeze V3 as legacy shadow.
10. Continue learned/model challengers.

## 19.3 Operational V4 cutover gate

V4 may replace V3 as the primary **manual research experience** before predictive alpha is proven when:

- freshness/settlement has passed the required live period;
- no browser/server state disagreement exists;
- every green row passes availability;
- stale/unknown input cannot become green;
- early events and corrections work in production;
- All Candidates is complete;
- manual actions persist;
- V3 same-tape shadow runs;
- rollback is tested;
- claims remain display/manual.

## 19.4 Predictive promotion gate

Any claim that V4 ranking has superior predictive edge requires the full forward gauntlet. Operational usability is not alpha proof.

## 19.5 Rollback

One definition switch returns the user to the last accepted board bundle. Rollback must not:

- delete V4 episodes;
- erase operator actions;
- restamp definitions;
- pool outcomes;
- reset horizon clocks.

---

# 20. Fable operating model

## 20.1 Fable’s role

Fable is principal orchestrator, not the worker for every PR.

Fable owns:

- intent preservation;
- estate archaeology;
- architecture and contract freeze;
- dependency/race coordination;
- wave decomposition;
- handoffs;
- adversarial review;
- production acceptance;
- durable memory.

Operators receive bounded missions. No operator receives this entire masterplan as “go build it.”

## 20.2 Authority precedence

1. Chairman’s directive and desired outcome.
2. This Sol architecture freeze.
3. Existing DNR decisions and canonical-owner contracts.
4. The approved wave handoff.
5. Existing implementation details.
6. Convenience.

Where existing code conflicts with the outcome, preserve history and migrate deliberately. Do not silently let legacy code overrule the product thesis.

## 20.3 Parallel lanes

After PR-0 freeze, Fable may run bounded lanes in parallel:

- **Lane A:** availability/settlement;
- **Lane B:** candidate episode and entry availability;
- **Lane C:** Radar activation/product;
- **Lane D:** theme graph/ThemeState;
- **Lane E:** intelligence-family adapters;
- **Lane F:** evaluation/ledger;
- **Lane G:** UI;
- **Lane H:** model challengers, only after substrates.

No two lanes may edit the same canonical authority without a written merge-order ruling.

## 20.4 Existing workstreams remain owners

- Conditional Fusion PR-3B continues.
- Live Entry Radar remains the entry-expert owner.
- GMI Theme Graph remains graph owner.
- EIOS remains earnings owner.
- Stock Identity remains routing owner.
- Availability workstream remains rescue owner.

The V4 umbrella records integration dependencies and acceptance; it does not duplicate their lifecycle stores.

---

# 21. Bounded build waves and PR plan

The numbering below is the V4 integration program’s numbering, not a rewrite of sibling workstream wave IDs.

## PHASE 0 — Freeze and reconcile

### V4-0A — Estate archaeology and architecture freeze
**Mission:** create the authoritative current-state packet and ratify this architecture on fresh `main`.

**Scope**
- inspect live site, served JSON, Pages deployment, Git artifacts and current main;
- reconcile recent PRs/workstreams;
- map exact stores, producers and consumers;
- resolve path ownership and merge order;
- create capability ledger and contract map;
- identify every stale AgentOS row;
- identify exact Theia/S&P source and rights status;
- freeze schema names and wave graph.

**Non-goals**
- no engine changes;
- no UI changes;
- no score tuning;
- no reopening killed research.

**Acceptance**
- `research/prophet_v4/CURRENT_STATE.md`;
- `CAPABILITY_LEDGER.md`;
- `ARCHITECTURE_FREEZE.md`;
- `CONTRACT_AND_OWNER_MAP.md`;
- `SOURCE_RIGHTS_REGISTRY.md`;
- `EXPERIENCE_REFERENCE_COMPOSITIONS.md`;
- wave handoffs;
- AgentOS validates;
- independent adversarial review;
- stop.

### V4-0B — AgentOS reconciliation
**Mission:** make durable state truthful without inventing a new tracker.

**Outcome**
- current statuses for Availability, Radar, Theme Graph, Earnings, Stock Identity and Fusion;
- explicit dependencies to V4;
- stale “waiting for Aug. 15” or “W0 in progress” records corrected from merged proof;
- one `WS-PROPHET-US-V4-RECOVERY.md`.

**Stop:** records only; no code.

---

## PHASE 1 — Truth and availability

### V4-A1 — Aug. 14 and current-session settlement recovery
**Mission:** close the actual stale-data incident, not merely its mechanism.

**Journey:** Chairman opens Prophet and sees an honest owed-session status.

**Acceptance**
- exact Aug. 14 reconstruction or explicit unrecoverable receipt;
- current latest owed session settled;
- production page/API proof;
- issue #5742 updated/closed only when truthful;
- no future knowledge in recovery.

### V4-A2 — Canonical settlement manifest
**Mission:** make reader-visible session settlement machine-verifiable.

**Acceptance**
- manifest contract;
- source/computed/published/reader clocks;
- bundle hashes;
- liveness and rescue read the manifest;
- mutation tests for wall-clock false freshness, gate-skip green and stale served bundle;
- visible health state.

### V4-A3 — Atomic publication and split-brain fence
**Mission:** prevent Pages, Git/archive and served JSON from silently representing different accepted bundles.

**Acceptance**
- one bundle ID across artifacts;
- publish refuses mixed bundle;
- reader reports mismatch;
- engine-push failure cannot look settled;
- successful Pages-only projection is explicit rather than hidden;
- real production proof.

### V4-A4 — Availability fire-drill week
**Mission:** prove never-stale behavior.

**Faults**
- pending cron supersede;
- gate-skip success;
- queued zombie;
- runner disk/full;
- push contention;
- stale source;
- partial artifact;
- Pages/git mismatch;
- rescue budget;
- source delayed/unavailable.

**Done:** full market week and all drills.

---

## PHASE 2 — Candidate and entry truth

### V4-B1 — Canonical candidate episode registry
**Mission:** preserve every qualified episode with deterministic identity and no producer cap.

**Acceptance**
- all registered expert fires map to episodes;
- no duplicate episode per structural anchor;
- re-arm rules;
- corrections;
- All Candidates machine projection;
- old cap shadow preserved only for historical comparison.

### V4-B2 — Entry-event correction hardening
**Mission:** close repaint, roster and schema defects before early evidence gains authority.

**Acceptance**
- B-15/B-16/B-17/B-18/B-19 disposition matrix;
- provisional→confirmed/retracted receipts;
- exact naked-union vs licensed-subset fields;
- no dead-signal chase;
- no fabricated intraday replay;
- existing expert hashes/parity preserved.

### V4-B3 — Orthogonal lifecycle contract
**Mission:** publish episode, emergence, maturity and availability independently.

**Acceptance**
- server contract;
- dashboard no longer infers;
- current `buy_soon` semantic conflict removed;
- all combinations tested;
- legacy rows mapped with explicit legacy basis;
- UI fixture proof.

### V4-B4 — Deterministic buyability/chase firewall
**Mission:** green only when the present trade is valid.

**Acceptance**
- zone/risk/extension/freshness/invalidation contract;
- ranker cannot waive;
- 3D cannot waive;
- mutation tests;
- real examples: early+open, confirmed+open, confirmed+ran, early+invalidated;
- production card proof.

### V4-B5 — Early Entry Desk MVP
**Mission:** finally expose existing TURN WATCH/early evidence to the Chairman.

**Minimum product**
- Early Radar lane;
- complete All Candidates table;
- trigger time/price;
- move since trigger;
- current availability;
- 1D/2D/3D evidence;
- nulls/freshness;
- manual watch/pass.

**Non-goal:** no learned ranking.

### V4-B6 — Radar observation-only activation
**Mission:** arm W4 without trade authority and measure a full RTH session.

**Acceptance**
- activation checklist;
- five-minute cadence;
- source/quote basis;
- lifecycle/re-arm;
- no authority leak into Prophet;
- health and stale states;
- full-session receipt.

### V4-B7 — Radar production UI and Prophet integration
**Mission:** complete W9 as a real product and connect it to V4 views.

**Acceptance**
- production `entry_radar.html`;
- auth;
- no copied reference-only claims;
- browser proof;
- link/embedded projection from Prophet;
- large candidate count;
- failure states.

---

## PHASE 3 — Evaluation and learning plane

### V4-C1 — Cohort-separated all-candidate ledger
**Mission:** grade everything without corrupting the pick record.

**Acceptance**
- required cohorts;
- common episode outcome;
- visibility/authority stamps;
- no presentation-cap survivorship;
- H10/21/42/63 and path metrics;
- era separation.

### V4-C2 — V3 legacy shadow
**Mission:** preserve the displaced system on the same tape.

**Acceptance**
- immutable V3 definition;
- prospective shadow rows;
- no V4 fields entering V3;
- same candidate eligibility comparison where lawful;
- existing V2 shadow unaffected;
- admin comparison.

### V4-C3 — Operator decision instrumentation
**Mission:** connect the Chairman’s real workflow to the episode.

**Acceptance**
- watch/pass/reject/promote/dossier/plan actions;
- timestamps and reason codes;
- no automatic training use;
- product analytics;
- correction-safe identity.

---

## PHASE 4 — Theme graph and broad intelligence

### V4-D1 — Theme-source and identity census
**Mission:** reconcile Finviz, curated baskets, THS, Citrini, S&P/Theia and every existing classification.

**Acceptance**
- exact sources and rights;
- coverage;
- taxonomy grain;
- PIT history;
- canonical/local/proposal roles;
- Theia procurement decision;
- no forced mappings.

### V4-D2 — Canonical ontology and probation mapping
**Mission:** extend the existing graph with required node/edge types.

**Acceptance**
- no second graph;
- typed/time-bounded edges;
- company/security identity;
- mapping proposals and adjudication;
- rights gate;
- corrections.

### V4-D3 — ThemeState v1
**Mission:** calculate real theme velocity, acceleration, breadth and diffusion.

**Acceptance**
- deterministic features;
- point-in-time memberships;
- robust normalization;
- small-N and coverage behavior;
- display projection;
- live examples across strong, weak, concentrated and broad themes.

### V4-D4 — Peer and transmission features
**Mission:** surface graph propagation.

**Acceptance**
- leader/laggard;
- peer event diffusion;
- supplier/customer read-through where evidence exists;
- earnings/theme propagation;
- no causal claim;
- receipts.

### V4-D5 — V4 intelligence-vector contract
**Mission:** create one canonical, missing-aware feature envelope for every episode.

**Acceptance**
- all family states;
- freshness/rights/coverage;
- anti-feedback tests;
- no board-derived inputs;
- broad baseline coverage;
- versioned feature manifest.

### V4-D6 — Earnings adapter
**Mission:** consume EIOS’s first stable event workspace and relationship outputs.

**Acceptance**
- no duplicate parser;
- exact event/company identity;
- facts/citations/corrections;
- null until ready;
- feature receipt.

### V4-D7 — Alternative-data family adapters
**Mission:** bring verified lobes into the common vector.

**Acceptance per family**
- source law;
- PIT law;
- coverage;
- freshness;
- nulls;
- rights;
- evaluation registration;
- no authority beyond registered tier.

---

## PHASE 5 — V4 ranking and product cutover

### V4-E1 — Explainable deterministic V4 priority
**Mission:** rank by intelligence inside present-entry lanes.

**Acceptance**
- Conditional Fusion is extended rather than duplicated;
- family percentiles/contributions;
- conservative priority and coverage;
- no buyability input/output loop;
- no fake precise score for sparse rows;
- same-tape replay;
- live board-order proof.

### V4-E2 — Prophet V4 primary experience
**Mission:** make V4 the Chairman’s default manual research board.

**Acceptance**
- full Action/Early/All/Theme/Track Record navigation;
- V4 definition and receipts;
- V3 shadow live;
- rollback;
- production browser proof;
- explicit manual authority.

### V4-E3 — Listwise ranker challenger
**Mission:** build a point-in-time LambdaMART/XGBoost ranking challenger.

**Acceptance**
- session query groups;
- walk-forward/purged folds;
- frozen labels/features;
- NDCG/recall/chase metrics;
- shadow only;
- feature attribution;
- reproducible model artifact.

### V4-E4 — Conditional router and multi-head challenger
**Mission:** learn when evidence families matter.

**Heads**
- research relevance;
- asymmetry;
- fragility;
- entry persistence;
- confidence.

**Acceptance**
- estimability by stratum;
- abstention;
- no per-name outcome audition;
- Stock Identity interfaces only;
- shadow.

### V4-E5 — Temporal heterogeneous graph challenger
**Mission:** test whether graph dynamics add forward value.

**Acceptance**
- deterministic baseline;
- HGT/TGN or justified alternative;
- temporal/heterogeneous ablations;
- rights-safe features;
- walk-forward;
- shadow;
- no production promotion.

### V4-E6 — Promotion gauntlet and V3 retirement ruling
**Mission:** decide earned authority.

**Acceptance**
- forward evidence;
- operational metrics;
- coverage/regime robustness;
- adversarial review;
- exact claims allowed/prohibited;
- Chairman/Sol ruling;
- durable memory.

---

# 22. Integration gates and critical path

## 22.1 V4 must not wait for every future lobe

Critical path to a useful product:

`A1 → A2/A3 → B1 → B3 → B4 → B5 → B6/B7 → C1/C2 → E1 → E2`

Theme/earnings/alt-data work can advance in parallel. E1 may launch with:

- technical/structure;
- broad sector/industry context;
- whatever theme evidence is current;
- explicit accruing/null families.

## 22.2 Graph/model path

`D1 → D2 → D3 → D4 → D5 → E1 → E3/E4 → E5 → E6`

## 22.3 Earnings path

EIOS E0/E1/E2 remains its own sequence. V4-D6 starts only after a stable consumer contract exists.

## 22.4 Fusion path

Conditional Fusion PR-3B→3D continues. V4-E1 must rebase/consume its accepted family registry and arena rather than editing around it.

---

# 23. Acceptance test matrix

| Failure/claim | Required proof |
|---|---|
| Board is current | production reader shows owed source session and accepted bundle |
| Green means buyable | every green row passes deterministic availability; poisoned score cannot change it |
| Early means early | PIT replay and live events show event before 3D confirmation |
| No repaint | provisional event confirms or retracts with receipt |
| All candidates preserved | store count equals complete UI/table projection; featured cap changes no ledger |
| Track record honest | cohort denominator and visibility stamps present |
| Missing not zero | mutation from null→0 fails |
| No feedback loop | injecting board output into upstream feature fails AST/runtime guards |
| Graph PIT | future membership mutation fails |
| Rights safe | unknown/unlicensed source fails closed |
| No duplicate graph/ranker/grader | path/import/owner census |
| V3 shadow clean | byte/feature firewall |
| Intraday honest | missing minute data cannot produce replay event |
| Browser/server parity | mutation of client fallback cannot change authoritative state |
| Split-brain loud | served hash mismatch creates outage/degraded status |
| Rollback safe | definition switch preserves episodes/actions/ledgers |
| Mobile usable | browser proof at relevant breakpoints |
| Manual workflow complete | real action persisted and visible on reopen |

---

# 24. Adversarial review questions for every PR

Fable must answer:

1. What new user or machine capability is independently usable?
2. Does the Chairman see it in production?
3. Did the PR fix an outcome or only add infrastructure?
4. Did it narrow the high-recall thesis?
5. Can any stale, unknown or extended row become green?
6. Can score or model output waive buyability?
7. Is any missing family treated as zero?
8. Is any source joined after its knowable time?
9. Is any provisional event silently erased?
10. Did the PR duplicate a canonical owner?
11. Did the browser derive authority?
12. Is a spec/reference/mockup being called shipped?
13. Did a UI cap delete evidence or bias evaluation?
14. Are cohorts/eras mixed?
15. Did a model train on future membership, corrections or outcomes?
16. Did manual feedback leak into labels?
17. Are rights and redistribution lawful?
18. Does the result survive real data, real auth and real browser execution?
19. What landmine/discovery must enter AgentOS?
20. What exact next bounded wave is now unlocked?

---

# 25. Failure states and defenses

## Data and availability
- stale source with fresh generated timestamp;
- successful no-op workflow;
- queued run supersede;
- push/deploy split;
- partial bundle;
- delayed vendor;
- quote gaps;
- correction after publish.

**Defense:** settlement manifest, bundle hash, reader proof, explicit degraded states.

## Identity
- reused ticker;
- symbol variant collision;
- ADR/common confusion;
- delisted member;
- split-adjustment mismatch;
- security/company dual-class duplication.

**Defense:** Stock Identity epoch, adjusted basis, identity gates.

## Candidate lifecycle
- duplicate detector episodes;
- dead event attached to current plan;
- never-expiring row;
- re-arm spam;
- hidden beyond-cap candidates.

**Defense:** episode identity, event edges, terminal/re-arm law, complete table.

## Entry availability
- 3D confirmation after a 15% run remains green;
- gap makes zone obsolete;
- stale quote;
- score waiver;
- invalidated pivot.

**Defense:** non-waivable deterministic firewall.

## Intelligence
- missing alt data becomes zero;
- rich coverage outranks quality;
- board feedback loop;
- double-counted families;
- stale theme membership;
- forced taxonomy mapping.

**Defense:** family registry, coverage/uncertainty, anti-lineage, PIT graph, probation.

## Evaluation
- only winners graded;
- top-K only stored;
- same session counted multiple times;
- era pooling;
- future trough labels;
- random split;
- manual selection bias.

**Defense:** all-episode ledger, same-tape cohorts, actual surface price, time splits, exposure stamps.

## Product
- reference UI mistaken for production;
- client stage divergence;
- too many cards;
- no search/filter;
- no failure states;
- unauthenticated data leak.

**Defense:** production vertical proof, server authority, complete table, auth tests.

---

# 26. Program completion standard

Prophet V4 is complete only when all four layers are real:

## Truth
- every owed session is settled or explicitly unavailable;
- source, quote, identity and correction states are trustworthy;
- rights are known;
- candidate and graph relationships are point-in-time.

## Intelligence
- early experts are preserved;
- present entry availability is deterministic;
- theme/earnings/altdata features are structured and missing-aware;
- ranking is explainable;
- challengers are evaluated honestly.

## Product
- the Chairman can see, filter, inspect and act on every candidate;
- green means buyable;
- early events arrive before slow confirmation;
- extended names are demoted;
- production works across states and devices.

## Learning
- all episodes are graded;
- cohorts are separate;
- V3 and model shadows accrue;
- operator actions are instrumented;
- promotion decisions use forward evidence.

---

# 27. Exact first Fable action

Fable starts **V4-0A only**.

Do not edit Prophet engines, Radar detectors, rankings or UI in the first session.

Fable must:

1. create a fresh worktree from current `origin/main`;
2. verify the live production artifact, source session, Pages deployment and repo artifact independently;
3. read the named workstreams and recent PRs;
4. inspect exact candidate, event, graph, evaluation, publication and auth contracts;
5. reconcile the current capability ledger;
6. resolve Theia/S&P as a source/rights decision;
7. freeze owners, schemas, lanes, cutover and wave graph;
8. obtain an independent adversarial review;
9. open one documentation PR;
10. stop and return the exact next handoff for V4-A1.

No one-shot build. No auto-roll to implementation.

---

# 28. Required Fable continuation handoff format

Every handoff must contain:

- **Observable mission**
- **Why it matters**
- **Authority and document precedence**
- **Verified `main`, production state and recent PRs**
- **Exact scope and owned paths**
- **Explicit non-goals**
- **Complete user journey**
- **Data contracts**
- **Time/knowability/correction/null behavior**
- **Deterministic, statistical and model-generated boundaries**
- **Failure states**
- **Ordered implementation sequence**
- **Acceptance tests**
- **Real production proof**
- **Stop condition**
- **Required durable-memory updates**
- **Exact continuation handoff**

A worker is never asked to “finish Prophet V4.”

---

# 29. Primary repository evidence

- `agentos/workstreams/WS-PROPHET-US-AVAILABILITY.md`
- `agentos/workstreams/WS-LIVE-ENTRY-RADAR.md`
- `agentos/workstreams/WS-PROPHET-CONDITIONAL-FUSION.md`
- `agentos/workstreams/WS-GMI-THEME-GRAPH.md`
- `agentos/workstreams/WS-EARNINGS-INTELLIGENCE-OS.md`
- `agentos/workstreams/WS-STOCK-IDENTITY.md`
- `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md`
- `research/PROPHET_BOARD_PRIORITY_ENGINE_MASTERPLAN_BY_FABLE.md`
- `research/GLOBAL_MARKET_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`
- `research/EARNINGS_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`
- `research/LIVE_ENTRY_RADAR_PR0_RESEARCH_CONTRACT.md`
- `engine/prophet_bridge.py`
- `templates/dashboard.html.j2`
- PRs #5026, #5370, #5395, #5578, #5593, #5604, #5625, #5698, #5700, #5718, #5723, #5724, #5737, #5754, #5768, #5784, #5813
- issue #5742

---

# 30. External primary research informing the architecture

- XGBoost official Learning to Rank documentation: LambdaMART, query groups, `rank:ndcg` and top-K pair construction.
- Rossi et al., *Temporal Graph Networks for Deep Learning on Dynamic Graphs*.
- Hu et al., *Heterogeneous Graph Transformer*.
- Adams and MacKay, *Bayesian Online Changepoint Detection*.
- S&P Dow Jones Indices, S&P Thematics Dashboard FAQ and Thematic Indices materials.
- Theia Insights, TIIC classification and Theme Watch Indices product documentation.
- TradingView official watchlist/technical alert documentation.
- Finviz official screener/groups/maps documentation.
- Koyfin official watchlist, views, news, filings and transcript documentation.

These sources inform system patterns. No proprietary code, text, taxonomy, constituents or assets are to be copied.

---

# 31. Final CEO ruling

The current Prophet US experience is not the standard to preserve. Its useful components—stores, expert calculations, provenance, Conditional Fusion, ledgers and UI language—are inputs to a controlled V4 migration.

The live standard becomes:

> **A complete, early and honest candidate field; strict present-entry truth; intelligence-ranked research priority; evidence and uncertainty visible; manual Chairman authority; prospective learning.**

Fable owns the end-to-end program and must refuse both failure modes:

- shrinking V4 back into a tiny late-confirmation shortlist;
- attempting a giant one-shot “superintelligence” build before truth, episodes, availability and evaluation are correct.

Dream at full scale. Deliver one independently useful vertical capability at a time.
