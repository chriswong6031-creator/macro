# K2-B — Institutional Manager Complex + Research Intent Contract Freeze

## Capability and boundary

K2-B supplies a deterministic, pointer-only vocabulary/compiler for describing institutional-manager observations. It is **BUILT_NOT_PROVEN** at the contract/fixture layer only. It creates no owner reader, store, scheduler, API, UI, ranking, gate, sizing, origination, or `ENTRY_OPEN` behaviour.

It adopts K1's pointer discipline: an observation carries only an owner-native `reference_id`, object id, accession, source URL, and publication/knowability clocks. It never copies an owner payload and never makes an evidence warehouse. The owner paths remain `engine/institutional_census/**`, ETF/ARK holdings, IBKR borrow, Theme Graph, Stock Identity and the ownership wire.

## Four-plane law

| Plane | Question it may describe | It may not become |
|---|---|---|
| Manager Research Intent | Did a discretionary research complex report a comparable preference? | fund flow, a recommendation, a score, or live flow |
| Fund Flow Pressure | Is a vehicle change consistent with mechanical subscriptions, redemptions or reconstitution? | manager conviction |
| Theme Capital Rotation | Is capital moving among members of one epoch-bound theme? | a cross-vintage preference comparison |
| Institutionalization / Saturation | What is observable about ownership breadth or concentration? | an entry/exit, crowding gate, or master score |

No plane is netted or automatically suppressed. The conditional-fusion exception in `DEC:PROPHET-ZERO-AUTHORITY-SUPERSEDED-BY-EARNED-CONDITIONAL-AUTHORITY` remains a separately governed future arena; K2-B grants it nothing.

## Identity, classification and clocks

`manager_complex_id` and `identity_epoch` identify a research complex at a declared epoch. A vehicle points to that pair, so multiple vehicles at one complex count once for independent-research-complex purposes. Classes are explicit: discretionary active, sector specialist, systematic, thematic/broad passive, overlay, leveraged/inverse, and synthetic/fund-of-funds. Only discretionary classes can contribute to the Manager Research Intent plane.

Shares outstanding has typed states `observed`, `absent`, and `unsupported`; absent and unsupported are never zero-filled. Mechanical flow is held in Fund Flow Pressure and compiles to `MECHANICAL_FLOW_NOT_INTENT`. Within-theme preference requires exactly equal theme identity and theme epoch. The campaign vocabulary is a closed linear sequence: `IDLE → INITIATED → ACCUMULATING → PAUSED → CLOSED`; a skipped or reversed transition is invalid.

Form 13F observations require report-period-end, filing, publication, and knowability clocks in order. Before knowability they compile as `NOT_KNOWABLE`; after their declared horizon they are `STALE`; rights-blocked observations are `RIGHTS_BLOCKED`. A 13F observation cannot claim `live_flow`. Corrections append a later event with an explicit superseded predecessor; they do not rewrite history.

## Reliability and authority

Reliability is a descriptive beta-binomial posterior keyed by complex × domain × horizon × action. Low-N observations shrink toward a declared prior. It has no oracle semantics and no cross-domain/horizon/action leakage.

### Legacy retrospective context is not K2-B reliability

`engine/manager_quality.py`, `engine/manager_trades.py`, and `engine/fund_followability.py` are adopted only as their existing legacy retrospective display/track-record context surfaces. Their quality grades, trade-history reliability read, and `follow_score` are not a prospective manager-complex × domain × horizon × action shrunk-reliability input; K2-B does not import, copy, normalize, or silently reinterpret them. This preserves their documented display-only/non-gate boundary and avoids creating a competing reliability owner. A future bridge requires a separate commission and point-in-time evaluation proof.

All authority axes are literal false: `can_rank`, `can_gate`, `can_size`, `can_originate`, and `can_open_entry`. Model prose and caller-injected vocabulary are rejected. Compilation is deterministic, in-memory, and reports `persistence: none`.

## Source-backed fixture and hostile coverage

`tests/fixtures/institutional_intelligence/source_backed_manager_intent_recipe.json` pins accession `0001398344-26-013841` with its SEC archive pointer and complete public/knowability clock chain. The same fixture carries a hostile passive-flow observation. The test contract proves epoch deduplication, class separation, typed missingness, no mechanical-to-intent laundering, theme-vintage binding, every legal campaign step plus invalid jump, 13F cutoff/stale/rights states, append/supersede lineage, low-N shrinkage, duplicate/corroboration and payload attacks, pointer-only K1 provenance, all-false authority, deterministic no-persistence compilation, and caller-vocabulary/identity-alias attacks.

## Reuse and non-adoption ledger

- Adopted: K1 pointer semantics; B0 manager-complex/vehicle distinction; B0 class taxonomy and 13F timing caveats; China four-model separation and its epoch-bound identity extension pattern.
- Not adopted: B0's proposed human roster or any people graph; a second 13F/ETF/ARK/borrow store; ETF shares-outstanding capture; live flow; a manager score; a future Conditional Fusion entry.
- Falsifier for a future adapter: a named owner-backed consumer can supply source/rights coverage and point-in-time replay receipts without copying owner payloads. That is a separate commission.
