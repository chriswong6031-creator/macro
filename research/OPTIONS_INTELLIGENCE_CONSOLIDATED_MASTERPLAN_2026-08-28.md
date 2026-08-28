# Options Intelligence — Consolidated Masterplan & Program-Control Freeze (C0)

- **Date:** 2026-08-28
- **Operation key:** `options-intelligence-c0-consolidated-program-control-20260828-sol-001`
- **Carrier:** one records-only Macro PR, `HOLD-FOR-SOL`, do not merge without an explicit Sol release on the operation thread.
- **Author seat:** Fable principal COO (sustained), commissioned by Sol CEO under the live Chairman directive to complete Options Intelligence end-to-end.
- **Pins at authoring:** Macro main `afe173f6f46cb2ddd2de9fa5843fc31ab8eabe26` (Sol's observed `ba270c60c1fe…` is a verified ancestor; delta is nightly `[skip ci]` data/immune traffic). Terminal master `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea` (exact match to dispatch pin). Protected Skillpack `Mastermind@038d1271b98e88b24e039c1ce4127d6503945845`, `mastermind.sol_skillpack.v1` 1.0.1 (verified: `docs/sol_skills/*` frontmatter `skillpack_version: 1.0.1`; commit is current Mastermind remote HEAD).
- **Decision record:** `DEC:OPTIONS-INTELLIGENCE-C0-PROGRAM-CONTROL`. **Continuation handoff:** `agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-28-options-intelligence-c0-program-control.md`.

This document is the single consolidated Options Intelligence architecture/masterplan and program-control freeze. It consolidates **records**; it moves no runtime. It deliberately supersedes nothing by deletion: every earlier masterplan keeps its historical authority for what it defined, and §7 pins how their vocabularies map. Where records disagree, §14 preserves the disagreement instead of normalizing it.

---

## §0 Executive summary

Three user/machine jobs, three owners, one shared substrate — and the substrate already exists. Nothing in this program requires a new truth plane, and the census (§3, §5) found **no unlawful duplicate plane in either repo**. The program's next moves are: prove the EOD consumer path (AD-1T2), prove the intraday live path (Intraday PR-4 dossier), and lawfully reconcile the out-of-order Options Alpha implementation (#6585) — all three parallelizable now (§9). The single highest-risk organizational defect found is that the Options Alpha workstream record did not know its own architecture carrier had merged (#6573) nor that #6576/#6585 exist; this carrier repairs that truthfully without minting a retroactive START (§8, §10).

Recommendation requiring a Sol ruling: **adopt #6585 under the §10 conditions** (merge plan #6576 first; adjudicate the §11 FS-4 docket; then release the #6585 hold; natural-RTH proof stays owed by a lawfully commissioned successor child).

## §1 Authority, pins, precedence

1. Live Chairman directive: complete Options Intelligence end-to-end under Sol CEO + sustained COO execution.
2. Hard freeze (Sol dispatch, restated): ThetaData = canonical options truth. One Theta Terminal. One canonical store/resolver. Terminal retains intraday producer/classifier authority (reading pinned in §14-d). No second live-flow DB, collector, WebSocket, event/campaign lifecycle, outcome ledger, score-control plane, identity plane, Issue Desk, Prophet ranker, queue or scheduler. Massive/Polygon options remains retired. No silent Flow Leaders repoint. Existing authority kills remain binding.
3. Precedence: current Agent OS owners + DNR/source decisions **outrank** stale handoff prose and stale masterplan status logs. Where this document's census found the two diverging, §14 lists the divergence and the governing record.
4. Agent OS is a knowledge plane (invariant I1). This masterplan gates nothing at runtime; it freezes what records SAY and what sequencing IS, and it commissions children only through Sol dispatch (§13).

## §2 The three jobs and the shared substrate

| Job | Owner workstream | What it is | What it is NOT |
|---|---|---|---|
| **Advanced Data Options (AD)** | `WS:ADVANCED-DATA-OPTIONS` | Settled EOD derivatives/off-exchange anticipation + risk intelligence; auditable, correctable, eventually calibrated and bounded into Prophet | An intraday engine; a Prophet ranker; a fused super-score |
| **Intraday Flow** | `WS:INTRADAY-FLOW-P0-RECOVERY` | Live situational desk: truthful quotes/pulse/flow health and trader-facing current-session state | A signal originator; a training corpus writer |
| **Options Alpha (OA)** | `WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY` | Live PIT exact-option/research-candidate workflow over canonical evidence, with separately earned statistical authority | A second collector/lifecycle/score plane; a relabeled unsigned score |

Shared substrate, **one owner each, never collapsed**: ThetaData/Terminal truth → existing live-flow event path → existing options episode/campaign/outcome owners → existing Evaluation/qledger/promotion law → existing product consumers. The fourth active workstream, `WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2`, is a separate adjudication owner (context-audit honesty) and is **not** an AD-1 blocker.

## §3 Consolidated capability ledger

States: `PROVEN_LIVE / BUILT_NOT_PROVEN / PARTIAL / DARK_OR_DISCONNECTED / BROKEN / SPEC_ONLY / NOT_BUILT / REJECTED_BY_DESIGN`. Every row names its receipt. "Uncensused" is printed where true — a null is disclosed, never hidden.

| # | Capability | State | Receipt |
|---|---|---|---|
| 1 | ThetaData T1 EOD store + full-universe incremental cadence (AD-1T1) | **PROVEN_LIVE** | PR #6267 (merge `787787f93c8e`) production packet issuecomment-5419508761; two consecutive natural sessions (D1 08-24, D2 08-25), coverage 0.9467 ≥ 0.90; WS row `WS-ADVANCED-DATA-OPTIONS.md` AD-1T1 |
| 2 | AD-1 Daily EOD Options Intelligence Brief, end-to-end (producer → brief → consumer product) | **BUILT_NOT_PROVEN** | Runtime merged #5872 (`661ad5d291aa`); ThetaData cutover #6253 (`a45ac6f58e63`); consumer path is AD-1T2's to prove (WS row AD-1T1, "AD-1 remains BUILT_NOT_PROVEN") |
| 3 | `site/options_intel_brief.json` → `build_options_command` product chain | **BUILT_NOT_PROVEN** | Sole writer `scripts/build_options_intel_brief.py:70`; sole consumer `scripts/build_options_command.py:183`; natural store-bearing product session not yet accepted (AD-1T2) |
| 4 | Intraday Flow board truthful boot/degraded render (PR-1) | **PROVEN_LIVE** | #6014 (`d5de4e627794`); production RTH browser proof 2026-08-20T13:32/13:34Z, 116 rows, zero console errors (WS row PR-1) |
| 5 | OPEX clock correction (PR-2) | **PROVEN_LIVE** | #6073 (`b90011f5d37d`); served `phase=mid_cycle`, false 0d/quad phrase absent, descendant checkout receipt (WS row PR-2) |
| 6 | Live quote/pulse/flow transport + semantic health (PR-4) | **BUILT_NOT_PROVEN** | #6105 merged (`364b85973517`); `DEC:INTRADAY-FLOW-PR4-MERGED-PRODUCTION-ACCEPTANCE-OWED`; owes one genuine current-session five-plane dossier (§12 C2) |
| 7 | `com.mastermind.liveflow` M1→R2 live-flow plane | **PARTIAL** | Plane exists and is the canonical producer (Macro `ops/launchd/com.mastermind.liveflow.plist` → `scripts/live_flow_poller.py` → `engine/live_flow.py`); PR-3 receipt found it DEGRADED (meta.asof age 186h, 08-20); PR-4 recovered it through the runbook; current-session freshness unproven until C2 |
| 8 | Terminal flow read proxy (polling + SSE) | **PROVEN_LIVE** | `terminal/lib/flowSource.ts`, `terminal/app/api/flow/route.ts`, `terminal/app/api/flow/stream/route.ts` at `b1b21a17`; SSE-by-design, 15s poll/20s heartbeat, entitlement-gated (`hasLiveOptions`); serves production today; upstream freshness is capability 7's problem, not this proxy's |
| 9 | OA architecture (campaign+calibration freeze) | **SPEC_ONLY** | #6573 MERGED (head `1c5e395e1c00`, merge `d84468e41f40`): 861-line design spec + `DEC:OPTIONS-ALPHA-CAMPAIGN-CALIBRATION-ARCHITECTURE` + new WS record. No accepted implementation |
| 10 | OA-1T measured trade+NBBO microstructure (plan) | **SPEC_ONLY** | #6576 OPEN (head `2becc23a87c8`), plan frozen, "no implementation started by this PR"; exact-head fences+CI green |
| 11 | OA-1T measured trade+NBBO microstructure (implementation) | **BUILT_NOT_PROVEN** (unadopted, out-of-order) | #6585 OPEN/DRAFT (head `77f400630d8a`), HOLD-FOR-SOL, MERGEABLE; faithfully implements the #6576 freeze (census: all 8 files covered by plan or tests); **no lawful historical START** — adjudication in §10 |
| 12 | Options episode/campaign/outcome ledgers | **PARTIAL** | `engine/options_signal_episode.py` (docstring: "permanent, zero-authority learning seam") owns `data/options_signal_episode/episodes.jsonl` + `outcomes_h60.jsonl`; `engine/options_signal_campaign.py` owns nightly campaign revision/outcome ledgers; `DSC:OPTIONS-ALPHA-DEAD-UI-MASKS-LIVE-EVIDENCE-ESTATE` attests a live evidence estate; no product consumer yet (OA-1C is dependency-held) |
| 13 | FS-1…FS-3 unsigned flow-event family | **PARTIAL** | Exists with `data/flow_signals/gate.json`; unsigned, non-directional by law; FS-5 calibration gauntlet not complete (OA-2 CLOSED) |
| 14 | FS-4 trainer + calibrated scorer | **DARK_OR_DISCONNECTED** (deliberate) | Code SHIPPED per `research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md:384`; scoring held dark by live kill-switch `config/flow_score.yml:22-26` (`scoring.enabled: false`); frozen by `research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md:513-521`; promotion barred by OA do_not_redo ("merely because trainer/scorer code exists") — see §11 docket |
| 15 | Terminal Options Alpha UI surface | **DARK_OR_DISCONNECTED** | `DSC:OPTIONS-ALPHA-DEAD-UI-MASKS-LIVE-EVIDENCE-ESTATE`: dead surface over a live evidence estate; recovery is OA-1C-TERMINAL, dependency-held |
| 16 | Options Context Audit v1 (full-corpus) | **BROKEN** | `DSC:OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL`: O(N) construction dies on TimeoutStartSec=180/CPUQuota=50% before the frozen 4,096 refusal; byte-pinned v1; lawful repair is prereg v2 only |
| 17 | Options Context Audit v2 preregistration | **NOT_BUILT** | `WS-OPTIONS-CONTEXT-AUDIT-PREREG-V2` wave V2-PREREG-CHARTER `status: todo` since 2026-08-22 |
| 18 | Prophet options input | **PROVEN_LIVE**, deliberately bounded to ONE key | Exactly `gex_confirm_verdict` in C1 fusion, lawful solely via `DNR:KILL-POSITIONING-FUSION` Amendment 1 (WS-ADVANCED-DATA-OPTIONS landmine); any wider fusion **REJECTED_BY_DESIGN** |
| 19 | Massive/Polygon options sourcing | **REJECTED_BY_DESIGN** (retired) | `DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA` (Chairman ruling 2026-08-22); 403 entitlement receipts re-proven twice (`DSC:AD-OPTIONS-CHAIN-ENTITLEMENT-REGRESSION`); polygon_gex estate preserved append-only as legacy evidence |
| 20 | Legacy Flow Leaders lane | **REJECTED_BY_DESIGN** (repoint prohibited) | Chairman/CEO architecture ruling (Sol C0 ledger item 5): no repoint of the retired Massive/Polygon-era flow lane onto ThetaData; fail closed, preserve history; lawful successor capability = AD-9 consuming Terminal-owned flow |
| 21 | Host-side Studio intraday options launchd fleet (15 units) | **DARK_OR_DISCONNECTED** (deliberate) | Not loaded (launchctl probes, AD-0 ledger §2.3); disarmed-by-default pending the AD-9 ruling; PR-4's incident authority did not settle fleet ownership |
| 22 | Sparse selector / W1A | **DARK_OR_DISCONNECTED** (research-only) | AD do_not_redo: do not resurrect before AD-9; W1A-A/B modules test-only, zero consumers |
| 23 | Terminal IV/term-structure snapshot plane (`mastermind.opts/v1`) | **PARTIAL — runtime state uncensused** | Terminal `ingest/collect_options.py` collects ATM/term-structure/smile from yfinance/CBOE, writes `<SYM>.opts.json`; a second options-data-collection path outside the flow/lifecycle domain; adjudication owed (§12 C5). Printed here rather than hidden: whether it currently runs, and its rights posture, were not censused in C0 |
| 24 | AD-2 … AD-15 waves | **SPEC_ONLY / NOT_BUILT** | Defined only in the AD masterplan §13 (`research/ADVANCED_DATA_OPTIONS_EOD_DARK_POOL_INTELLIGENCE_OS_MASTERPLAN_2026-08-17.md:762-971`); no dedicated implementation docs; AD-2 explicitly CLOSED until AD-1 production acceptance |

## §4 Value model

- **User value.** (a) EOD: an options intelligence brief a non-specialist can act on inside the existing Options Workspace (`site/options.html` via `build_options_command`) — anticipation and risk context with honest no-signal states. (b) Intraday: a desk that is truthful under degradation — a trader always sees the board or an honest degraded label, never a confident lie. (c) OA: a research-candidate workflow (exact option, exact clocks, abstention) replacing the dead surface with the live evidence estate.
- **Machine value.** Bounded Prophet confluence (today: exactly one key, §3-18); AD-8 Sector/Neural-Web consumers; AD-9 confirmation/contradiction bridge over intraday truth; AD-10 watchlist/portfolio material-change intelligence. All promotion-gated; display tier ships freely, authority is earned (gauntlet law).
- **Research/signal value.** The episode/campaign/outcome ledgers are a PIT-correct, append-only options learning corpus that cannot be reconstructed retroactively (point-in-time OI is permanent; missing sessions stay missing). FS family + prereg gauntlets convert it into separately earned statistical authority — or into honest kills.
- **Distribution value.** Site pages (macro dashboard), Terminal app (entitlement-gated live flow via SSE), R2 artifact families (`live_flow/*`, `options_hub/*`, `options_structure/*`) already published by Macro builders and consumed cross-product.
- **Commercial value.** `hasLiveOptions` entitlement already gates the live flow stream — options intelligence is a paid-tier differentiator and retention surface; OA's candidate workflow deepens it without a brokerage/execution liability (OA-5 explicitly reuses the Issue Desk, no trade authority).
- **Data-moat value.** One licensed Theta Terminal + the ~60GB T1 store under daily incremental maintenance + PIT episode/outcome history + correction-safe receipts = an accruing asset with a time moat: a competitor starting today cannot buy the history or the correction provenance. The moat compounds nightly at near-zero marginal cost; protecting its identity (one store, one resolver, keep-first) is therefore a commercial law, not just a hygiene rule.

## §5 Ownership / no-rebuild matrix

| Plane | Canonical owner (repo/path) | Runs on | May NOT be rebuilt as |
|---|---|---|---|
| Options truth (EOD chains/OI/greeks/trade+NBBO) | ThetaData via `collectors/thetadata.py`; store resolved ONLY by `engine/thetadata_store.resolve_thetadata_store()` | One Theta Terminal, M1 host (`com.macro.theta-terminal`) | Second terminal, second store path, store copy between runners, repo-stub resolution |
| EOD brief producer | Macro `scripts/build_options_intel_brief.py` (sole writer of `site/options_intel_brief.json`) | Nightly / theta-m1 lane | A second brief writer or a parallel "options summary" artifact |
| EOD product composer | Macro `scripts/build_options_command.py` → `site/options.html` | Render lane | A second Options product shell (Sol C0 ledger item 1) |
| Live flow producer/classifier | Macro `scripts/live_flow_poller.py` + `engine/live_flow.py` under `ops/launchd/com.mastermind.liveflow.plist` | M1 host → R2 | Second poller/collector/WebSocket/live-flow DB (`WS-INTRADAY-FLOW` do_not_redo) |
| Live flow read path | Terminal `terminal/lib/flowSource.ts` (+ `/api/flow`, `/api/flow/stream`) | Terminal product | A Terminal-side producer; a second stream semantics |
| Episode/outcome ledger | Macro `engine/options_signal_episode.py` (`options.signal_episode/v1`) | Nightly only | Rival grader/ledger; forked identities (OA landmine) |
| Campaign ledger | Macro `engine/options_signal_campaign.py` (`options.signal_campaign/v2`) | Nightly only | Second campaign lifecycle |
| Score authority | FS family under `config/flow_score.yml` kill-switch + Evaluation/qledger promotion law | — | Generic Options super-score; relabeled directional score (OA-4 law) |
| Prophet coupling | `gex_confirm_verdict` in C1 fusion only | Prophet engine | Any wider positioning fusion (`DNR:KILL-POSITIONING-FUSION` outside Amendment 1) |
| Issue Desk | `options.issue_desk/v1` | Existing | Parallel issue queue / trade manager / brokerage path (OA-5 law) |
| Context audit | `WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2` owned paths | systemd timer (decoupled from W2C) | Shadow validator with a larger cap; recoupling into trusted-context publication |
| M1 runner capacity | `WS:RUNNER-FLEET-RESILIENCE` W4: exactly `daily.yml collect_tail` on `actions-runner-2/m1-nightly-2` + label `theta-m1` | M1 host | Generic `macstudio` on M1 (rejected by design; 49 such jobs censused unlawful there) |
| Portfolio/watchlist coupling | AD-10 (future, dependency-held) | — | Any pre-AD-10 portfolio authority |

**Cross-repo authority note (preserved reading, §14-d):** the Sol freeze says "Terminal retains intraday producer/classifier authority." Code reality: the producer/classifier **code** lives in the Macro repo and runs on the M1 host; the Terminal repo is a read-side proxy. The reading this document pins (for Sol ratification): "Terminal" names the **product domain** whose intraday truth is the `com.mastermind.liveflow` plane — the freeze's operative content is that intraday classification stays on that one plane, is not duplicated, and is not migrated into EOD lanes or new engines. No file moves under this reading.

## §6 Source clocks, nulls, corrections, rights, authority ladder

- **Clocks.** T1 store S/D-day identity (snapshot-date vs data-date, receipts carry both); 04:30 PT store fires; 18:30 PT sentinel anchor evaluations (K4); nightly is the sole advancer of forward ledgers (house law) — episode/campaign ledgers are nightly-only; live plane: 15s SSE server poll / 20s heartbeat, `meta.asof` age semantics with DEGRADED verdicts (PR-3 receipt shape); OPEX calendar clamped to last observation (PR-2); legacy estate capture lease `LEASE_END_ET_HOUR=3` (`DEC:AD1C01-CAPTURE-LEASE-REPLACES-SAME-DAY`); PIT discipline: never backfill later-settled OI/NBBO into an earlier decision (OA do_not_redo).
- **Nulls.** `board_state=INSUFFICIENT_COVERAGE` is an honest product state, not a failure to hide; `mode=no_data` may never be reported healthy; missing is null/unavailable, never zero; one healthy plane may not launder a stale sibling (Intraday landmine); `vendor_empty` masking of dead roots is a NAMED open finding (AD-1T1 F2 — six roots, WBS/BLD/URG/RHHBY/NVR/FI), not silently repaired.
- **Corrections.** Keep-first immutability on measured Parquet columns (#6576 freeze); first-writer quality rule on the legacy estate (HEALTHY immutable, PARTIAL replaceable under strict conditions — `DEC:AD1C0-FIRST-WRITER-QUALITY-RULE`); supersession by record, never deletion (agentos law); retirement never deletes evidence (Sol review on #5830); permanent gaps stay permanent (PIT OI).
- **Rights.** ThetaData license: ONE terminal instance. Cboe delayed-quote pages expressly prohibit automated extraction — not a fallback. Massive/Polygon: not entitled for option chains (403 receipts) and retired as an options source. Terminal IV plane (yfinance/CBOE) rights posture: **unreviewed — named in §3-23, adjudicated by C5.** R2 redistribution of derived artifacts is the established pattern.
- **Authority ladder.** Chairman → Sol CEO → COO (this seat) → workstream owners → child sessions. Data authority: ThetaData canonical (`DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`). Direction authority: `DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-SALIENCE-MECHANICS-AND-DIRECTION` (Q_oi+Q_skew same-sign both ≥0.50 with D_salience ≥0.60; GEX originates no direction). Score authority: gauntlet/promotion law; display tier ships freely; the LLM never originates signals/scores (`KILL-LLM-ORIGINATION`, Neural Web A7). Kill authority: DNR registry (§8-DNR list). Execution authority: fleet hooks + Mastermind control_plane — never this document (I1).

## §7 Naming concordance (org plane ↔ research plane)

The organizational layer (Agent OS, Sol dispatches, PR titles) and the research layer (masterplans) use different wave vocabularies. Both are real; **the org-plane names are canonical for sequencing going forward**; research-plane names remain historical aliases. No renumbering of either.

| Org plane (canonical) | Research plane (alias) | Note |
|---|---|---|
| AD-0…AD-15 (`WS:ADVANCED-DATA-OPTIONS`) | Same names, defined in AD masterplan §13 | Identical vocabulary; sub-waves AD-1P0/AD-1C0/AD-1C0.1/AD-1T0/AD-1T1/AD-1T2 exist only in the WS record |
| OA-0, OA-1T-MACRO/TERMINAL, OA-1C-MACRO/TERMINAL, OA-2…OA-5 (`WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY`) | `research/OPTIONS_ALPHA_MASTERPLAN.md` §5 waves W0–W5 | The OA-x scheme (born with #6573, 2026-08-27) is canonical; W0–W5 predates the recovery architecture. Lowercase `oa0`/`oa1t` appear in PR titles |
| PR-1…PR-4 (`WS:INTRADAY-FLOW-P0-RECOVERY`) | `research/LIVE_FLOW_PRODUCTION_ROADMAP_BY_FABLE.md` P0–P6 | PR-x are recovery waves (PR = pull-request-shaped wave, an accident of naming); P0–P6 is the older production roadmap phasing |
| FS-1…FS-5 (`research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md`) | Same | FS-4 = trainer+calibrated scorer wave (shipped code, dark scoring); FS-5 = the calibration gauntlet OA-2 completes |

**Registry note (fifth-owner, NOT changed in C0):** `config/mastermind_programs.yml:1880-1882` currently names `research/OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` canonical for the options program, while the AD masterplan self-declares "governing north star" — a conflict predating C0. Recommendation: Sol ratifies THIS document as the program-control home and a follow-up records child updates the registry pointer. Editing `config/mastermind_programs.yml` here would widen the carrier beyond the four contracted owners, so it is returned to Sol instead (contract: "If a fifth durable owner must change, return the exact need before widening").

## §8 Current collision ledger

1. **#6576 (plan, OPEN `2becc23a87c8`) / #6585 (implementation, OPEN DRAFT `77f400630d8a`) / #6593 (records, OPEN DRAFT `66a214d2dcdf`).** #6585 implements #6576's frozen plan faithfully (census: 8 files — 4 implementation all inside the plan's freeze list, 4 tests; one benign divergence: `scripts/live_flow_poller.py` named in the plan scope but needing no change). #6585 was built **before** the explicit #6576-merge START gate: no lawful historical START exists, the prior OA worker received terminal SOL STOP, and #6593's body flags it verbatim as "OA-1T: implementation #6585 exists while plan #6576 is still open/unmerged and the canonical Slack carrier has no pickup ACK or START. MAS-175 = Unmapped Execution / HOLD-FOR-SOL." Adjudication: §10.
2. **C0 carrier ↔ #6576 textual conflict (certain).** Both edit `agentos/workstreams/WS-OPTIONS-ALPHA-INTELLIGENCE-RECOVERY.md`. #6593 does NOT collide (its workstream edits are WS-RATES-INFLATION-COMMAND and WS-STOCK-DOSSIER-LIVE-QUOTE — verified by file list). Recommended sequencing: **C0 merges first** (it records ground truth), then #6576 rebases its WS edit onto the repaired record (its plan document is untouched by C0).
3. **#6585 authority-path note.** Its diff touches `scripts/ops_train_flow_score.py`, which is inside the CI-authority `scripts/**` inventory — the merging session must expect `authority_changed=true` ship-loop semantics; no `.github/**` or `.claude/hooks/**` paths are touched.
4. **Terminal carriers.** #422 (one SSE producer per feed key) touches the shared flow resolver/stream — already fenced by the OA-1T-TERMINAL wave row ("reconcile all open PRs touching the shared Flow resolver/stream, including Terminal PR #422 while open"); #429 (quote demand planning) is quote-side, no options-truth collision. No Options-truth carrier is open on Terminal.
5. **Terminal IV snapshot plane** (`ingest/collect_options.py`, `mastermind.opts/v1`): second options-data-collection code path outside the flow/lifecycle domain; not a live collision with #6576/#6585 scope; adjudication owed (C5) under the one-truth freeze.
6. **Program-registry conflict** (§7 note): canonical-home pointer vs this consolidation — returned to Sol.
7. **Pre-existing agentos validate red (NOT C0's).** `agentos/handoffs/BREATHING-PLATFORM-2026-08-28-completion-commission.md` carries 7 schema errors on current main (missing `danger_areas`; `model: GPT-5.6 Sol` not in enum; `ended_because: commissioned_next_child` not in enum; four `verified[]` entries without `command`). This blocks the literal "scripts/agentos.py validate green" acceptance clause for ANY carrier until repaired. C0 introduces zero new errors and does not silently widen into the fifth file; the repair need is returned to Sol here.
8. **AD-1T0 stale next_action** ("Next: Sol decision on a spine-cadence wave…") — resolved by AD-1T1's PROVEN_LIVE receipt; repaired truthfully in this carrier (bounded edit, history preserved).
9. **DNR rows binding this program:** `DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION`, `DNR:KILL-DOI-FAMILY`, `DNR:KILL-SKEW-DECELERATION`, `DNR:HOLD-WF-OPTIONS` (registry); plus decision-layer kills carried by OA law: `KILL-LLM-ORIGINATION`, `KILL-FUSED-COMPOSITE`, `KILL-POSITIONING-FUSION` (+ Amendment 1 arena), `HOLD-THETA-TAPE`, `KILL-CHARM-NARRATIVES`, `KILL-OFFHORIZON-VERDICTS`. All remain binding; C0 creates no exception to any of them.

## §9 Frozen dependency graph (verified) — parallel vs held lanes

Sol's A→Q graph, verified against the census and encoded with repo-true names. **Parallelizable NOW** (no shared mutable surface, subject to §12 packet fences): **A, B, C, plus the independent side lanes C4 (context-audit v2 charter) and C5 (IV-plane adjudication).** Everything else is dependency-held.

| Lane | Content | Gate it waits on | Parallel now? |
|---|---|---|---|
| A | **AD-1T2**: natural store-bearing ThetaData → intel brief → existing Options Workspace production acceptance | AD-1T1 PROVEN_LIVE ✅ (satisfied 08-25) | **YES** |
| B | **Intraday PR-4 proof**: genuine current-session quote+pulse+M1/R2 flow+health+browser dossier | #6105 merged ✅; shared-host care with A (both touch the M1 host; B is read/observe against the liveflow lane, A exercises the theta lane — different launchd families, no shared write path; the packet fences name the one shared risk: host load during proof windows) | **YES** |
| C | **OA-1T reconciliation**: adjudicate #6576/#6585 sequencing/adoption (§10); records + merges only | Sol ruling on this C0 RESULT | **YES** (ruling-gated, no runtime) |
| D | OA-1T-TERMINAL (render measured microstructure; Attention ≠ probability) | Accepted Macro observation contract (C complete incl. natural-RTH proof owed) | held |
| E | AD-2 correction-safe receipts/null/lifecycle/supersession | AD-1 production acceptance (A) | held |
| F | OA-1C-MACRO candidate composer (`options.alpha_candidate_feed/v1`) | **A accepted + C accepted** (AD-1T2 + OA-1T-Macro), plus preregistered candidate-formation policy | held |
| G | AD-3 / AD-4 off-exchange reality + confluence | E | held |
| H | AD-5 shadow Prophet consumer (actual delta stays zero) | E (+ gauntlet law) | held |
| I | AD-6 + OA-2/OA-3 prospective outcomes/calibration + exact-option NBBO lifecycle under existing Evaluation/episode/outcome owners | F (and OA-2 additionally FS-5 lawfulness; OA-3 extends the existing lifecycle owner with a reviewed contract version) | held |
| J | OA-4 separately preregistered right-conditioned directional family | OA-2 + OA-3; explicit `DNR:KILL-POSITIONING-FUSION` scope ruling before any fusing test begins; unsigned FS never relabeled | held |
| K | AD-7 bounded Prophet activation | Calibrated forward evidence (I); extension/tradeability upstream gates | held |
| L | AD-8 Sector + Neural Web consumers | K-adjacent display first, authority gauntleted | held |
| M | AD-9 Terminal Intraday Bridge (confirmation/contradiction/precedes/no-info over the canonical intraday plane) — lawful successor to retired Flow Leaders | Sol AD-9 ruling (also gates Studio-fleet ownership, §3-21) | held |
| N | AD-10 Watchlist/Portfolio material-change intelligence | M-adjacent + AD acceptance chain | held |
| O | AD-11…AD-14 short/borrow, insider, institutional, expectations-gap | Own PIT/rights clocks; after core chain | held |
| P | OA-5 promoted signal → existing Options Issue Desk | OA-1C-TERMINAL + OA-4 promotion gates | held |
| Q | AD-15 vendor/data upgrade | Only if earlier production evidence proves a named information gap | held |

**Program completion law (frozen):** done ≠ "store healthy" ≠ "PR merged" ≠ "UI renders". Done = **Truth + Intelligence + Product + Learning**: fresh/correction-safe rights-safe data; useful typed/calibrated intelligence with abstention; coherent EOD+intraday+candidate workflows on real production paths; prospective evidence showing what adds information and what stays shadow/killed.

## §10 Adjudication: adopt or reject #6585 (recommendation to Sol)

**Recommendation: ADOPT, under five conditions — without rewriting its out-of-order history.**

Facts (census-verified): #6585 delivers exactly what #6576 froze — measurement inserted pre-`_sign_batch()` at `engine/live_flow.py:674`, additive `options.trade_nbbo_microstructure/v1` event block (not a new store), additive keep-first Parquet columns, +857 lines of tests; implementation base pinned at `d84468e41f40` (the OA-0 merge); MERGEABLE against current main; its own body declares BUILT_NOT_PROVEN. It was built without a lawful START; the worker has received terminal SOL STOP; #6593 flags it as MAS-175 Unmapped Execution.

Why adopt rather than reject:
1. Sol's own C0 ledger forbids "creat[ing] a replacement implementation carrier" — rejection therefore strands OA-1T-MACRO entirely (the only lawful implementation home would be a new carrier that is itself forbidden).
2. The artifact is faithful to the frozen plan (§8-1). Discarding a verified-faithful artifact to punish its provenance converts a process defect into a capability loss while the process defect is already fully recorded and sanctioned (SOL STOP; MAS-175; this document; the WS repair).
3. Adoption ≠ retroactive START. The records state, permanently: no lawful START existed. Sol's adoption act, if granted, accepts the artifact **on inspection**, prospectively — the deviation stays a deviation in every record that mentions it.

Conditions of adoption (all five before hold release):
- **A1.** #6576 merges FIRST (plan before implementation — lawful order restored prospectively; also resolves the C0↔#6576 WS-file rebase, §8-2).
- **A2.** The §11 FS-4 preflight docket is adjudicated with receipts posted on #6585.
- **A3.** Exact-head hosted CI green at `77f400630d8a` (or its trivially rebased successor; any content change voids this recommendation and returns to Sol).
- **A4.** The merging session acknowledges the `scripts/**` authority-path semantics (§8-3) and owns the PR to merged-and-verified per fleet law.
- **A5.** Post-merge state is recorded as OA-1T-MACRO = BUILT_NOT_PROVEN; the natural-RTH production proof remains owed and runs only under a lawfully commissioned child (fresh key/thread/watcher, §13) — the proof is NOT part of adoption.

If Sol instead rules REJECT: close #6585 unmerged with a records note, keep #6576 as the frozen plan, and return to Sol for an explicit new-carrier authorization (which the current ledger forbids — i.e., rejection requires Sol to also amend the no-replacement-carrier rule; this consequence is stated so the choice is made with its full cost visible).

## §11 FS-4 preflight adjudication docket

FS-4 (trainer + calibrated scorer) is shipped code held dark by `config/flow_score.yml` (`scoring.enabled: false`), frozen by `research/OPTIONS_ALPHA_FLOW_SCORE_AMENDMENT.md`, with promotion barred by OA do_not_redo. The #6576/#6585 work adds measurement columns adjacent to FS-4's feature space. **The docket can conclude only "safe under the freeze" or "blocked" — it cannot amend the freeze.** Items, each answered with a receipt before #6585's hold is released (condition A2):

- **D1.** Does the #6585 diff touch `config/flow_score.yml`, any scoring-enable path, or any consumer of `scoring.enabled`? Expected NO; verify by diff inspection, receipt = file list + grep.
- **D2.** Do the additive Parquet columns preserve keep-first immutability and leave every existing column's semantics byte-identical? Receipt = schema diff + the plan's freeze language.
- **D3.** Does the `scripts/ops_train_flow_score.py` change alter frozen FS-4 trainer/scorer behavior in any way beyond carrying the new measurement columns? Receipt = line-level diff review.
- **D4.** Is any NaN-backfill promotion pathway opened (features present-in-schema but absent-in-history being fillable)? OA do_not_redo makes NaN-filled promotion unlawful; receipt = explicit statement of how absent-history rows behave.
- **D5.** Reaffirm in the adoption ruling: `scoring.enabled` stays `false` through OA-1T; enablement belongs exclusively to FS-5's preregistered gauntlet (OA-2) plus current DNR scope review (`KILL-FUSED-COMPOSITE`, `KILL-POSITIONING-FUSION`); ambiguity requires explicit DNR adjudication, not inference (OA-2 wave row law).

## §12 First bounded child commission packets

Durable rule (§13) applies to every packet: fresh operation key, fresh Slack thread, fresh reciprocal watcher, explicit ACK/START handshake. None of these children is Fable-by-default. Each packet below is the freeze; the dispatching ruling may narrow but not silently widen it.

### C1 — AD-1T2: production-prove the EOD consumer path
- **Route:** `build` → `builder` (Sonnet). **WHY NOT FABLE:** the spec, store, producer, consumer, and acceptance matrix all exist and are frozen; this is disciplined execution + dossier assembly — Sonnet-draft + Opus/main-loop-review fully recovers quality (fails the Fable gate). An Opus `reviewer` red-teams the dossier before return.
- **Repos/paths:** Macro. Read: `engine/thetadata_store.py`, `scripts/build_options_intel_brief.py`, `scripts/build_options_command.py`, `daily.yml` theta-m1 jobs. Writes: records + (only if a named defect requires it) bounded producer/consumer repairs returned to Sol before widening.
- **Non-goals:** No AD-2. No universe shrink. No T1 re-proof (do_not_redo: AD-1T1 is PROVEN_LIVE). No runner-topology change (any orchestration need → re-read `WS:RUNNER-FLEET-RESILIENCE` W4 and return to Sol; generic macstudio on M1 stays rejected). No R2-sync repair unless evidence proves it prerequisite.
- **Journey:** natural nightly session → brief built from the canonical store at ≥0.90 coverage → `build_options_command` serves the brief-backed Options Workspace → live verification of the served page.
- **Clocks/nulls/corrections:** S/D-day identity in receipts; 04:30 PT fire; 18:30 PT sentinel; `board_state` honesty (INSUFFICIENT_COVERAGE is a lawful outcome, never gate-shopped); F2 dead-root masking named if encountered, not silently fixed; keep-first store discipline untouched.
- **Failure states:** coverage <0.90 on a natural session → honest report + causal analysis, no forced re-runs to manufacture a pass; store-host unreachable → BLOCKED with receipts.
- **Tests/proof:** existing suites stay green; production proof = two consecutive natural scheduled sessions serving the brief-backed product, receipts at parquet + served-page level.
- **Stop:** PASS dossier returned to Sol, or first causal failure named with evidence. Never both repair-and-accept in one act without Sol review.

### C2 — Intraday PR-4: the owed current-session production dossier
- **Route:** `debug` → `debugger` (Opus). **WHY:** falsification-first verification of a live system with stop-at-first-causal-failure semantics and high temptation toward health-laundering (the exact failure `DSC:INTRADAY-FLOW-AGE-HEALTH-CAN-HIDE-EMPTY-BOARD` records); Opus-tier skepticism is the requirement. **WHY NOT FABLE:** the acceptance matrix is frozen in the WS record; judgment is in the matrix, not the executor.
- **Repos/paths:** Macro + the live host + served site. Proof surfaces: board-scoped `live/intraday_quotes.json` coverage + source freshness; current-session pulse mode/coverage; `com.mastermind.liveflow` M1/R2 plane advancing naturally; semantic `/api/status` + dead-man; served desktop+narrow browser journey with lawful live/degraded labels.
- **Non-goals:** No Studio-fleet re-arm (disarmed pending AD-9). No AD-9 settlement. No second engine. Narrow causal repairs only within the workstream's owned paths, each recorded.
- **Failure states:** a fallback render, HTTP 200, young mtime, fixture, or green CI is NOT proof (WS do_not_redo verbatim); one healthy plane never launders a sibling.
- **Proof/stop:** one genuine current-session dossier covering all five planes → separate records closeout; or stop at first causal failure with the narrow repair + receipts.

### C3 — OA-1T reconciliation execution (gated on the Sol §10 ruling)
- **Route:** `build` → `builder` (Sonnet). **WHY NOT FABLE:** post-ruling this is mechanical carrier sequencing: merge #6576, post §11 docket receipts, release/merge #6585 per ruling, land the records closeout on the OA workstream. All judgment happens in the ruling itself.
- **Sequencing:** C0 merges first (§8-2) → #6576 rebase+merge → docket receipts on #6585 (A2) → hold release per Sol → #6585 merge (A3/A4) → records closeout recording BUILT_NOT_PROVEN + proof-owed (A5).
- **Non-goals:** No natural-RTH proof execution (that is a later, separately keyed child). No edits to #6585's content (any content change voids §10 and returns to Sol). No FS-4 enablement of any kind.
- **Stop:** carriers merged + records closed, or BLOCKED on a named check/conflict.

### C4 — Options Context Audit preregistration v2 charter
- **Route:** `analysis` → `analyst` (Opus). **WHY:** a preregistration is a statistical commitment device — bound-sizing against the ~25k-row/48MiB owner capacity, refusal semantics, and future-NYSE boundary design are promotion-law judgment where a cheap draft risks quietly weakening the v1 refusal honesty. **WHY NOT FABLE:** single-owner, bounded, fully reviewable against `research/options_estate/OPTIONS_CONTEXT_AUDIT_LEDGER_BOUND_ADJUDICATION_2026-08-13.md` §7.
- **Non-goals (binding, from WS do_not_redo):** no `_MAX_REFERENCES` widening; no v1 edits; no timeout/CPU raises as substitutes; no owner windowing/eviction (`DNR:KILL-OPTIONS-CONTEXT-AUDIT-OWNER-EVICTION`); no shadow validator; no recoupling into trusted-context publication; charter only — implementation is its own later PR.
- **Stop:** prereg packet returned for review as its own PR.

### C5 — Terminal IV-plane adjudication (`ingest/collect_options.py`)
- **Route:** `analysis` → `analyst` (Opus). **WHY:** the deliverable is a rights + architecture recommendation under the one-truth freeze (keep as display-tier separate job / retire / fold into ThetaData), i.e. decision support for Sol; census steps are embedded but the output is judgment. **WHY NOT FABLE:** bounded single-plane question.
- **Scope:** runtime state (does it run today, where, feeding what), rights posture of yfinance/CBOE sourcing (Cboe automated-extraction prohibition is already established for delayed-quote pages — determine whether this path is covered), consumer census of `<SYM>.opts.json`, and a recommendation. **No mutation.**
- **Stop:** recommendation packet to Sol.

## §13 Program-control rules (durable)

1. **Every independent child gets a fresh operation key, a fresh Slack thread, and a fresh reciprocal watcher setup** (both sides post truthful WATCH_ARMED receipts naming mechanism, baseline, cadence, trigger, duplicate suppression, and disarm behavior). Slack delivery alone is never ACK/START; an explicit ACK and a separate START with re-pinned heads are mandatory; work product returns on the child's own thread as BLOCKED / DECISION_REQUEST / RESULT.
2. **No retroactive STARTs, ever.** An artifact built outside its gate is adjudicated on inspection (as §10 does) and its history is preserved verbatim in the records; it is never re-papered.
3. **Records carriers for program control are HOLD-FOR-SOL** (DRAFT, literal "do not merge", no auto-release, no merge-on-green); ordinary child implementation carriers follow standard fleet completion law (one session owns commit → merge → live verification).
4. **One owner per plane** (§5). A child that believes a second plane is required returns a DECISION_REQUEST; it never builds first.
5. **Naming:** org-plane wave names (§7) are canonical in all new records; research aliases may be cited as `(alias: …)`.
6. **Nulls printed:** every capability claim in program records uses the §3 state vocabulary; "uncensused" is written where true.
7. This document is amended only by a successor records carrier under a fresh Sol operation key; drift found later is repaired by record, not by editing history.

## §14 Disagreements preserved (deliberately not normalized)

- **(a)** Sol C0 ledger: AD footer "has historically lagged its own wave row." Census 2026-08-28: footer and wave rows are currently consistent; the one live staleness was AD-1T0's "Next: Sol decision on a spine-cadence wave" (resolved by AD-1T1) — repaired in this carrier. Both statements stand for their times.
- **(b)** OA-0 approval state: WS record (pre-repair) said "Chairman reviews the written architecture spec… until written-spec approval, do not create an implementation plan"; the WS body simultaneously said "The Chairman approved the campaign+calibration architecture and exact experience/contract freeze in chat"; Sol's C0 ledger says "OA-0 architecture was accepted/merged in #6573." Governing record (precedence §1-3): Sol's ledger. The repair records acceptance via #6573 while preserving that the written-spec-review gate language existed and that #6576/#6585 proceeded against it out of order.
- **(c)** Context-audit corpus size: WS objective says "~25,000 rows / 48 MiB previously reviewed"; `DSC:OPTIONS-CONTEXT-AUDIT-V1-TIMEOUT-PRECEDES-4096-REFUSAL` says the corpus was 3,897 rows at audit death. Both true at their clocks (reviewed capacity bound vs corpus size at failure); v2 sizes to the capacity bound.
- **(d)** "Terminal retains intraday producer/classifier authority" (Sol freeze) vs code reality (producer code in Macro repo, M1 host; Terminal repo is a read proxy with no `/api/status` and no producer). Pinned reading in §5 awaits Sol ratification; no file moves either way.
- **(e)** Canonical program home: `config/mastermind_programs.yml` → `OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md` vs AD masterplan self-claim vs this consolidation. Returned to Sol (§7 registry note).
- **(f)** OA-0 merge identity: Sol ledger cites `d84468e…` (the merge commit on main); GitHub cites #6573 head `1c5e395e1c00`. Same event, two lawful SHAs; both recorded.
- **(g)** FS-4 "SHIPPED" (`research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md:384`) vs FS-4 dark (`config/flow_score.yml` kill-switch): shipped code, deliberately dark scoring. Not a contradiction once the two claims' objects (code vs authority) are separated — recorded so nobody "fixes" either side.
- **(h)** Acceptance clause "agentos validate green" vs pre-existing 7-error red on main from a non-owner file (§8-7). C0 satisfies "introduces zero errors"; literal green needs the fifth-file repair returned to Sol.
- **(i)** Sol dispatch pinned Macro main `ba270c60…`; C0 executed against its descendant `afe173f6…` (ancestry verified). Recorded; no action.

## §15 Acceptance self-report (to be finalized at RESULT)

- Heads re-pinned at return: recorded in the RESULT post on the operation thread.
- `scripts/agentos.py validate`: zero errors introduced by this carrier (pre-existing §8-7 red named; command receipts in the handoff).
- Exact-head hosted CI/fences: receipt recorded on the PR at RESULT time.
- Changed-file/collision census: §8; the only carrier collision is #6576 (sequencing pinned §8-2).
- Independent adversarial architecture review: executed by an Opus `reviewer` against this document before RESULT; findings and dispositions recorded in the PR.
- No duplicate plane created: this carrier is records-only; §5 matrix reaffirmed.
- Disagreements preserved: §14.
- Carrier state at return: one exact-head Macro PR, DRAFT, HOLD-FOR-SOL, unmerged, awaiting Sol `CONTINUE / REQUEST_REPAIR / STOP`.
