# Live Entry Radar — Completion Architecture & Masterplan

**Date:** 2026-08-28  
**CEO owner:** Sol  
**Chairman authority:** Chris explicitly approved end-to-end completion and Fable/COO execution in the governing Sol conversation on 2026-08-28.  
**Workstream:** `WS:LIVE-ENTRY-RADAR`  
**Program:** `market-timing-intelligence`  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@e2092cb6235519ac7f50fb3aa50ec1c1a6f627c0`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap-major 1 compatible.  
**Macro architecture base:** `2299cbafe42568ef3b088911fc80d6373e5e270d`.  
**Status:** CHAIRMAN-APPROVED COMPLETION FREEZE / RECORDS-ONLY. This document changes no detector, runtime, R2 object, scheduler, quote plane, Prophet behavior, product page, Evaluation OS state, Slack runtime, Executive lifecycle or provider session by itself.

---

## 1. Completion outcome

Live Entry Radar is complete only when a U.S. equity researcher/operator can use a genuinely live tactical-entry discovery product that continuously surfaces early-entry formation with preserved expert identity, trustworthy point-in-time and transport clocks, visible degradation, research-priority provenance, prospective evidence and a real responsive browser surface.

The required real vertical is:

```text
canonical U.S. universe / lobe nominations / preserved Terminal expert artifacts
        -> existing Radar Probe Set
        -> frozen detector pack + exact detector identities
        -> existing quote/snapshot plane
        -> 5-minute RTH evaluator
        -> basis audit + state transitions + immutable expert events
        -> private canonical event spool
        -> existing W5 sole durable reconciler
        -> prospective forward ledger + existing Evaluation OS/qledger
        -> deterministic Research Priority
        -> safe product projection
        -> production entry_radar.html
        -> real desktop + narrow-browser user journey
```

Completion also requires the same lane to recover from a genuine dark gap without manual babysitting, retain warm cadence through a full natural RTH session, and make security/failure states visible rather than presenting silence as health.

### 1.1 Permanent separation from Prophet

Radar answers:

> Is an unusually attractive early entry **forming right now**, before full confirmation?

It does not answer Prophet's conviction question and does not replace the deterministic entry-availability/gating question.

Throughout this program:

- `engine/entry_signal.py`, `engine/prophet_*.py` and Prophet selection/gating authority remain untouched unless a later, separate Chairman-authorized promotion explicitly reopens them;
- Radar has no rank/gate/size/trade/`ENTRY_OPEN` authority over Prophet;
- promising Radar research never silently becomes Prophet behavior;
- no automatic trading is introduced.

---

## 2. Current canonical state at completion freeze

### 2.1 Capability ledger

| Capability | State | Current truth |
|---|---|---|
| PR-0 research contract / kill-registry law | `PROVEN_LIVE` as source law | #5578 merged; §18 append-only amendment law governs later changes. |
| Probe universe + enlistment bus | `PROVEN_LIVE` implementation foundation | #5625 merged. |
| Expert-event framework + exact G0 parity | `PROVEN_LIVE` implementation foundation | #5698 merged; expert identity preservation is binding. |
| C1-C5 detector specifications + PIT battery | `PROVEN_LIVE` implementation foundation | #5724 merged; published detector hashes are frozen. |
| 5-minute RTH evaluator | `BUILT_NOT_PROVEN` for final completion | #5768 merged and later commissioned; warm production cycles existed, but final full-RTH/dark-gap proof remains absent. |
| W4.1 transport correction / Lab commissioning | `PARTIAL` | #5929/#5995 merged; #6095 healed `ts_ms`; genuine 2026-08-20 envelope + warm Lab live-forward loop exist. |
| Dark-gap / cold-start recovery | `BROKEN` | A long dark gap can make the first pass exceed the 5-minute tick and 570-second service timeout. No accepted owner repair exists. |
| Full-natural-RTH cadence | `BUILT_NOT_PROVEN` | Warm ~5-minute cycles existed, but the program's full-RTH natural cadence gate remains unclosed. |
| Current quote/probe coverage | `DARK_OR_DISCONNECTED` | Last accepted commissioning receipt was 240/2979 usable on 2026-08-20; current RTH coverage is not durably evidenced. |
| Radar event-spool security | `BROKEN` until falsified | `DSC:RADAR-SPOOL-PUBLIC-R2` proved a guessable event envelope anonymously readable from the public R2 dev host; no Radar remediation carrier is accepted. |
| W5 historical/replay machinery | `PROVEN_LIVE` as merged research machinery | #5741/#5780/#5825 + W5.1 #5833 landed. |
| **W5 prospective production consumer** | **`DARK_OR_DISCONNECTED`** | Current `data/entry_radar/ledger_state.json` on 2026-08-27 says `WAITING_FOR_LIVE_SOURCE`, `spool_dir=null`, `observed_spool_events=0`, `forward_rows_total=0`, qledger registered=0. |
| W6 deterministic Research Priority implementation | `BUILT_NOT_PROVEN` | #5834 + #5845 are on main; methodology correction passed, but non-empty real developing-RTH acceptance is not canonically closed. |
| W7 outcome-calibrated Opportunity | `NOT_BUILT` | Must not be forced before honest prospective sample. |
| W8 reference UX + RIG | `PARTIAL` | Existing open PR #5737 is the sole carrier; independently reviewed reference only, not production UI. |
| W9 production UI | `NOT_BUILT` | No `templates/entry_radar.html.j2` exists on current main and no production Radar page is shipped. |
| Stock Identity / Expert Routing integration | `PARTIAL` external dependency | Radar records experts; Stock Identity owns per-security routing. Its W3+ program remains separately governed. |

### 2.2 Durable contradictions to supersede

The workstream's old global `next_action` still talks as though #5929 were open and W4.1 were awaiting merge. That is stale relative to later W4.1 commissioning records and #6095.

The important later truths are:

1. W4.1 was merged and genuinely commissioned on 2026-08-20.
2. Warm Lab `live_forward` evidence exists, but it does **not** prove the W5/Eval OS durable consumer is connected.
3. Current canonical W5 durable state is still `WAITING_FOR_LIVE_SOURCE` with no spool path.
4. W6 remains unaccepted because real non-empty developing-episode proof was deferred.
5. W8 remains an open reference carrier, and W9 does not exist.

This masterplan supersedes only the stale sequencing/next-action assumptions. It does not rewrite historical receipts or detector/research law.

---

## 3. Architecture freeze and no-rebuild boundaries

### 3.1 One canonical system per responsibility

The completion program extends existing owners and must not create:

- another quote plane;
- another Massive/WebSocket owner;
- another Radar event store;
- another R2 credential/client implementation;
- another W5 forward ledger;
- another Evaluation OS/qledger;
- another scheduler/timer for the same evaluator responsibility;
- another identity/event lineage system;
- another Prophet ranker/gate;
- another Stock Identity/expert-routing engine;
- another watcher/lifecycle/queue to coordinate the operators.

### 3.2 Frozen detector/event identity

Do not redesign detector formulas or hashes to fix infrastructure/product problems.

The currently registered identities remain authoritative:

- G0 `G0_GREY_DOT@1` / `9be89a8acc8b905c`
- C1 `C1_1D_LIVE_WASHOUT@1` / `f0bbd6cf3a6e2339`
- C2 `C2_1D_TURN@1` / `d8ba60a25cfa7400`
- C3 `C3_1D_4H_RECOVERY@1` / `d54dc1e55c4261c8`
- C4 `C4_MTF_TURN@1` / `dce21ac680233ee2`, context/stratification only and structurally unable to fire
- C5 `C5_BOTTOM_WATCH@1` / `13dec66345a0376c`
- F1 remains unbuilt/refusing unless separately specified under lawful research procedure.

Terminal expert families and Radar families remain separate candidate experts. Do not flatten amber EARLY, STARTER pending/failed, RE-ENTRY reclaim/repair, confirmed BUY/REBUY, G0 or C1-C5 into one generic `entry_signal` boolean.

### 3.3 Canonical clock law

The completion path must preserve distinct meanings:

- source/event `signal_ts`;
- source knowability `signal_known_ts`;
- evaluator/pass `pass_ts`;
- first transport observation derived from the earliest valid carrying envelope;
- product generation/as-of time;
- current quote/source timestamps and stale age;
- later correction/finality state.

A later observation cannot rewrite an earlier immutable event. A replay/backfill cannot be relabeled as prospective live-forward evidence. Missing, stale, unavailable, rights-blocked and malformed states never become a numeric zero or a clean non-fire.

### 3.4 Security boundary

Raw Radar event envelopes are research/evidence-plane objects, not anonymous public product payloads.

The accepted end-state is:

```text
Radar writer -> authenticated private evidence object
                    |
                    +-> authenticated Lab/W5 readers
                    +-> derived, allowlisted product projection
```

The structural security repair must reuse the accepted delivery/R2 credential owner. It may use a private bucket/prefix policy or an accepted delivery-plane mechanism, but it may not hide exposure by making keys less guessable while anonymous reads remain possible.

### 3.5 Product boundary

The production page consumes a safe derived read model. It never directly exposes or depends on raw evidence-spool URLs, private paths, credentials, source hashes that are inappropriate for the user tier, or unrestricted internal event payloads.

---

## 4. Product and experience architecture

### 4.1 Primary persona/job

A U.S. equity researcher wants to scan **what is forming now**, understand why each expert fired, distinguish provisional from confirmed evidence, judge freshness and false-start history, and decide what deserves attention before the conservative confirmed entry gate opens.

### 4.2 Five-second information order

The production Radar surface should answer, in this order:

1. **Is Radar healthy enough to trust right now?**
2. **What is forming / turning now?**
3. **Which expert generated each observation?**
4. **How strong is Research Priority and why?**
5. **What is missing, stale, contradictory or not yet measured?**

### 4.3 Required at-rest surface

Use the accepted W8 sister-language and RIG as a visual/interaction reference, not as a synthetic product payload.

Required content includes:

- Probe Set headline and coverage/freshness state;
- lifecycle ladder / current state;
- separate expert lanes;
- one card per `(ticker, expert)` rather than one flattened ticker card;
- ticker, price/change, source expert, lifecycle, provisional/confirmed state, signal/known freshness;
- current Research Priority when lawfully available, with provenance/decomposition accessible;
- false-start history preserved;
- component evidence and zone/invalidation when available;
- explicit stale/raw-basis/unavailable/degraded states;
- drawer for why-now, recovering component, structural strength, risk/asymmetry, other lobe evidence, sample/trustworthiness and path history where the owner fields exist;
- W7 Opportunity slot remains `NOT YET MEASURED` until W7 lawfully completes.

### 4.4 Responsive/accessibility acceptance

Production browser proof is required at minimum at:

- 1440 desktop;
- 1280 desktop;
- 1024 narrow desktop/tablet;
- 720 narrow boundary;
- 390 mobile.

Proof must cover EN and ZH, dark and light, keyboard focus, reduced motion, no horizontal document overflow, no card/overlay occlusion, and no page-origin console error.

W8's 2.2px overlay headroom at 1024 is not a production budget. Re-measure on the production font stack and preserve robust wrapping/reserve behavior.

---

## 5. Reliability and operational architecture

### 5.1 Warm cadence and cold recovery are separate gates

A healthy warm loop does not prove cold-start recovery.

**Warm gate:** during a full natural RTH session, the evaluator repeatedly completes within the expected cadence budget without overlapping service invocations, and every positive/negative/degraded cycle emits an honest health state.

**Cold gate:** after a genuine dark gap sufficient to lose warm caches/substrate locality, the canonical service autonomously reaches the first valid production envelope without manual timer stop/start, arbitrary resource inflation, hidden overlap or false health.

### 5.2 Required cold-start diagnosis

Before repair, instrument and measure phase time/memory/I/O for at least:

- source/slice discovery;
- pack load/build and inversion proof;
- quote snapshot loading/normalization;
- minute/path substrate loads;
- detector evaluation;
- ledger diff;
- spool write;
- product payload publish.

The repair should target the actual dominant phase. Acceptable patterns include reuse/caching of immutable or appropriately fingerprinted substrate, prewarming through the existing service owner, or a bounded bootstrap path. Do not solve by continually increasing `TimeoutStartSec` or memory ceilings without causal evidence.

### 5.3 Quote/probe coverage observability

Every production proof records:

- probe-set population;
- quote rows available;
- usable quote count/share;
- no-quote/stale/raw-basis/other refusal counts;
- basis-audit count/mismatch count;
- per-family availability;
- transition/event counts;
- pass duration;
- service overlap/timeout state.

Coverage changes are facts, not automatic model/ranking inputs.

---

## 6. Prospective evidence / Evaluation OS architecture

### 6.1 Existing W5 remains sole durable owner

`scripts/reconcile_entry_radar.py` stays the only writer of `data/entry_radar/**` and the only Radar callsite allowed to register the live-forward batch into qledger.

The completion repair must make the existing reconciler consume the same canonical private event spool the live writer actually produces. It must not add a second W5 reader/store.

### 6.2 W5 prospective completion vertical

Required proof:

```text
real RTH transition/event
  -> private entry_radar.events/v1 envelope
  -> existing read_spool_events validation/dedup
  -> LIVE_FORWARD forward.parquet row
  -> existing qledger register_batch
  -> durable ledger_state reports nonzero observed/live-forward totals
```

The receipt must pin event identity, earliest carrying envelope clock, forward-row address, qledger outcome and source generation without publishing private values/credentials.

A fixture, replay result, Lab board or hand-authored spool object does not satisfy this gate.

### 6.3 W6 Research Priority acceptance

Do not redesign RP1 because production evidence is missing.

W6 completes when a real developing-RTH population yields a non-empty Research Priority projection under the existing methodology and Sol confirms:

- unique-ticker current-snapshot population law;
- same-ticker measure coherence / fail-closed `snapshot_conflict` behavior;
- percentile-before-combine method remains unit-invariant;
- canonical `priority_value` and ordinal relationship;
- provenance/decomposition inspectable;
- missing/unrankable rows stay explicit;
- no outcome-conditioned retuning occurred;
- no Prophet authority leakage.

### 6.4 W7 Opportunity research

W7 is not a product-blocking excuse to fabricate probability.

It starts only after the frozen sample/readiness criteria are satisfied by real prospective evidence. It must preregister/calibrate against the accepted outcome law before inspecting the confirmatory answer and reach one scientific terminal state:

- accepted/calibrated research model eligible for the declared display tier;
- rejected/falsified construction;
- or explicitly still accruing because the preregistered minimum sample has not been reached.

The overall Radar program cannot claim final research acceptance while W7 is merely silently unbuilt. If W7 remains sample-gated, the durable closeout must say so and the production page must remain `NOT YET MEASURED` rather than implying an edge.

---

## 7. Stock Identity / Expert Routing boundary

Radar owns **expert discovery and event preservation**. It does not learn which expert is best for each security.

The separate `WS:STOCK-IDENTITY` program owns:

- identity epochs;
- path-anchored episode taxonomy;
- estimability/power;
- structure-measurement localization;
- per-security/per-neighborhood expert-routing research;
- abstention/SIF and its own prospective promotion law.

The integration boundary is read-only:

```text
Radar immutable expert event identity + clocks + provenance
                  -> Stock Identity consumer
```

Radar may expose a stable consumer contract/reference. It must not add per-ticker own-outcome expert selection, ticker-as-strategy keys, best-of-grid audition or adaptive routing. `DNR:KILL-OUTCOME-AUDITION` remains binding.

Do not edit the active Stock Identity completion carrier (#6529) from a Radar child wave. Any required contract change crossing its ownership returns to Sol for reconciliation.

---

## 8. Remaining wave graph

Each modifying child is one independently reviewable operation with a fresh stable operation key and one GitHub carrier. The sustained Fable COO may remain the same reasoning seat across waves, but a terminal child `STOP` closes that child watcher/thread. The next child starts with a new operation key and a fresh exact Slack thread.

### LER-C0 — records / program-control acceptance

**Mission:** land this completion freeze, Agent OS decision/handoff and repaired workstream state without claiming runtime/product completion.

**Completion:** records carrier accepted/merged; no implementation claim.

### LER-C1 — W4.2 private evidence transport security

**Mission:** make the canonical Radar event spool non-anonymous while preserving one writer, one accepted R2/client/credential family and all existing authenticated consumers.

**Required proof:** previously guessable envelope anonymous GET returns non-200; authenticated writer/readers work; no new R2 client/store; historical identity remains interpretable; public product payload does not expose raw evidence.

**Hold:** no detector/cadence redesign.

### LER-C2 — W4.3 cold-start + full-RTH reliability and current coverage

**Mission:** make one real dark-gap restart autonomously converge to the first valid envelope and then sustain a full natural RTH session at accepted warm cadence, with explicit current quote/probe coverage and all degradation states.

**Required proof:** cold-phase causal profile before code; no overlap; real full-RTH receipt; current coverage census; pack service resource proof; no arbitrary timeout-only fix.

### LER-C3 — W5.2 prospective Eval OS reconnect

**Mission:** connect the existing W5 sole durable reconciler to the canonical private Radar spool so one real current-session Radar event becomes a durable LIVE_FORWARD row and existing qledger claim.

**Required proof:** real event -> private spool -> `forward.parquet` -> qledger -> ledger state; idempotence, correction/time/null behavior; no second writer/client/scheduler.

**Dependency:** C1 implementation complete. C3 implementation may be built while C2 natural-time proof accrues if changed paths are disjoint, but final acceptance requires a genuine current RTH event on the final secure path.

### LER-C4 — W6.1 real Research Priority acceptance

**Mission:** close W6 on a non-empty real developing-RTH board without changing the frozen methodology unless a genuine defect is found.

**Dependency:** C2 + C3 production evidence.

**Sol gate:** final W6 acceptance is Sol-owned.

### LER-C5 — W8 reference reconciliation

**Mission:** reconcile and land the existing #5737 reference/RIG carrier on current main; do not create a replacement W8 branch/PR.

**Can run:** independently from C1-C4 because it is reference-only and changes disjoint paths, subject to fresh collision census.

**Completion:** reference artifact on main with static + real-Playwright RIG evidence; still no production-page claim.

### LER-C6 — W9 production product vertical

**Mission:** ship the actual production Entry Radar page using real Radar data and the accepted W8 information/interaction language.

**Dependency:** C2, C4, C5; C3 must be working for prospective evidence fields. W7 is not required to fabricate an Opportunity number; the slot remains honestly not measured.

**Required proof:** real data through the actual server/product path; desktop+narrow browser acceptance; EN/ZH, dark/light, degraded/empty/stale/raw-basis states; no private evidence leakage; no Prophet mutation.

### LER-C7 — W7 prospective Opportunity research

**Mission:** when preregistered sample readiness is met, build/adjudicate the outcome-calibrated Opportunity research under Evaluation OS law.

**Can run:** after C3 prospective accrual matures; may overlap C6 if its sample gate is satisfied and paths are disjoint.

**Sol gate:** scientific acceptance/promotion is Sol-owned.

### LER-C8 — integrated production + research acceptance

**Mission:** prove one real current-session input crosses the final production lane and close the original program honestly.

Required integrated proof:

```text
real current RTH input
 -> existing quote/substrate owner
 -> evaluator
 -> private spool
 -> W5/Eval OS
 -> Research Priority
 -> production page
```

plus:

- genuine dark-gap recovery receipt;
- full natural RTH cadence;
- current quote/probe coverage;
- anonymous spool refusal;
- real desktop/narrow browser proof;
- forward evidence state;
- W7 final scientific state or explicit still-accruing gate;
- Stock Identity handoff boundary;
- zero Prophet authority change.

---

## 9. Fable COO operating model

Fable is justified as the sustained principal COO because this program crosses live runtime, delivery/security, evidence/research and product acceptance and requires repeated collision reconciliation across a long-running workstream.

Fable does **not** receive one giant implementation PR.

Fable may:

- maintain the completion ledger against current truth;
- sequence dependency-feasible child waves;
- use bounded Codex/Claude/Sonnet/mechanical workers for low-ambiguity child tasks;
- review returned worker work before sending it to Sol;
- perform current-main collision census before every modifying child;
- continue architecture-preserving repair inside a current child without Chairman micromanagement.

Fable must return to Sol for:

- architecture/owner change;
- security boundary ambiguity;
- new persistent truth/control/identity/event/queue/store plane;
- detector/hash/spec change;
- Prophet/rank/gate/size/trade authority;
- W6 or W7 scientific acceptance/promotion;
- unresolved source-rights/PIT/correction/null conflict;
- destructive migration or effect-unknown modification;
- final program acceptance.

---

## 10. Dialogue / watcher law for this program

The canonical Worker Presence `turn_watch_v1` architecture is not yet production-proven at this freeze. Therefore program dialogue uses only a temporary non-authoritative exact-thread watcher/wait mechanism where the active reasoning surfaces support one.

For **every child operation**:

1. create one exact top-level Slack handoff with a stable child operation key;
2. COO replies `ACK <operation_key>` in that exact thread before work;
3. both Sol and COO read the full thread;
4. both sides arm an available exact-thread watcher/wait bridge and return a `WATCH_ARMED` receipt naming mechanism/cadence/trigger and terminal shutdown behavior;
5. COO posts only `PROGRESS`, `BLOCKED`, `DECISION_REQUEST` or `RESULT` for that child in the same thread;
6. after every nonterminal COO return, COO re-arms its watcher;
7. Sol never leaves a nonterminal return hanging: Sol sends `RULING`, `CONTINUE` or `REQUEST_REPAIR`, names the same child operation, and instructs COO to re-arm after its next nonterminal return;
8. on accepted terminal completion, Sol sends `STOP — <child operation>` / `SOL ACCEPTED`, explicitly states the child is terminal, commands COO to stop work and disarm its watcher, and Sol disables its own temporary watcher;
9. watcher shutdown failure is reported as `WATCH_STOP_FAILED`; the child remains terminal and the leftover watcher may not originate another action;
10. a new child wave uses a new operation key and new exact Slack carrier/thread.

Temporary watcher behavior owns attention only. It owns no Job/Attempt/Worker lifecycle, retry, completion, authority, provider selection or durable semantic cursor.

---

## 11. Program completion law

Live Entry Radar is finally accepted only when all four dimensions are true.

### Truth

- current, rights-safe, correction-safe input sources;
- exact expert/event identities;
- trustworthy source/known/transport clocks;
- private evidence boundary;
- honest current coverage and degradation.

### Intelligence

- deterministic Research Priority accepted on real developing episodes;
- prospective Eval OS evidence connected;
- false starts retained;
- W7 either lawfully adjudicated or explicitly still accruing without fake authority;
- Stock Identity consumer boundary preserved.

### Product

- actual production `entry_radar.html` exists and is usable;
- real content, empty, stale, unavailable, raw-basis and degraded states work;
- desktop/narrow/mobile, EN/ZH, dark/light and accessibility pass;
- no raw/private evidence leaks.

### Learning

- full-RTH and dark-gap operational receipts exist;
- prospective outcomes are accruing through canonical W5/qledger;
- instrumentation shows coverage/cadence/failures;
- future promotion decisions can be replayed against point-in-time evidence.

Green CI, a merged PR, one warm live pass, a Slack delivery, an Operator Lab board or a reference mockup cannot individually satisfy this completion law.

---

## 12. Exact next action

After this records carrier is accepted, start **LER-C1 — W4.2 private evidence transport security** with the sustained Fable COO. W8 #5737 reconciliation may proceed as an independent sibling only after the same COO proves path/authority disjointness and uses a separate child operation key/carrier.

Do not start W9 merely because W8 lands. Do not close W6 without its real non-empty production acceptance. Do not treat the current W5 `WAITING_FOR_LIVE_SOURCE` ledger as healthy. Do not reopen Prophet.
