# Breathing Platform Completion Masterplan — 2026-08-28

**Status:** ARCHITECTURE FROZEN FOR COMPLETION. Chairman-approved completion program.  
**Owning workstream:** `WS:BREATHING-PLATFORM`.  
**Program:** `prophet-us`.  
**Current procedural pin:** protected `mastermindx-market-intelligence/Mastermind@038d1271b98e88b24e039c1ce4127d6503945845`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap-major 1 compatible.  
**Current Macro archaeology base:** `ba270c60c1fe825f2e9fce1fcf507b7272a67b63`.  
**Supersedes for completion sequencing only:** the stale completion path in `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` and the 2026-08-15 continuation. The original research remains historical evidence; this document does not rewrite its already-accepted truths or reopen CN/platform expansion waves.

---

## 0. Executive outcome

The Breathing Platform is complete only when the U.S. product behaves like a continuously alive signal system rather than a nightly batch page:

1. **During the session**, the existing live plane continuously refreshes market state and Prophet-Live state without creating a second signal authority.
2. **At the U.S. close**, the canonical close-pass path observes the real session close, evaluates essentially the full canonical U.S. universe, publishes the same-session provisional board, and makes that board browser-visible by the **16:15 ET product SLO**.
3. **After the close**, later canonical inputs may revise the provisional view, while the nightly remains the canonical settlement/forward-ledger authority.
4. **Every surface states the truth of its own clock.** A fresh same-session board must not imply that an independent stale/empty Prophet-Live strip is fresh; a stale/nightly board must never inherit a fresh provisional stamp; an ahead-of-calendar armed pack must never look healthy.
5. **Failure is visible and useful.** Missing, stale, empty, partial, invalid-tip and provider-degraded states fail dark or visibly degrade; they never masquerade as healthy current signal.
6. **Completion is empirical:** three consecutive genuine NYSE sessions after the last relevant production-changing merge must pass the close → candidate → reader ruler, coverage law, browser truth law and availability/permanence law.

The end-state is not “more infrastructure.” It is a user opening Mastermind near or after the close and seeing a current, high-coverage, honest U.S. signal experience whose clocks, provisional status and degraded states match reality.

---

## 1. Product thesis and value model

### 1.1 Primary user job

A U.S. equities user should be able to answer, within seconds:

- What changed **today**?
- Which names became actionable or materially closer to action **this session**?
- Are tonight's picks based on today's completed close or older evidence?
- Is the live Prophet plane healthy, stale, empty or unavailable?
- Is this board provisional, confirmed, behind, or market-closed?
- Can I trust that the board's visible freshness claim refers to the data that produced the cards?

### 1.2 Machine/intelligence job

The machine must:

- preserve one canonical Prophet admission/gate authority;
- observe same-session close truth without waiting for the full nightly chain;
- separate **candidate computation**, **transport visibility**, **live-strip health**, **armed-pack basis**, and **nightly settlement** as independent clocks;
- make every omitted/unavailable name attributable;
- preserve point-in-time correction and no-lookahead law;
- generate production receipts that distinguish where latency or darkness actually occurred.

### 1.3 Moat

The moat is the union of:

- exact same-session market truth;
- a continuously observed live signal plane;
- deterministic close-pass membership using the production gate rather than an approximation;
- explicit provenance/clock separation;
- reader-visible honest degraded states;
- production receipts that make freshness and causality measurable across days.

A fast page with stale source truth is not Breathing. A perfect provenance layer with no same-session user value is not Breathing either.

---

## 2. Current capability ledger at the architecture freeze

| Capability | State | Current truth |
|---|---|---|
| W-L0 truth repairs | `PROVEN_LIVE` / accepted historical foundation | Append semantics, hysteresis, price-basis law, sentinel surfaces and dormant honesty were shipped in prior waves and are not reopened here. |
| W-L1 provisional board product | `PROVEN_LIVE` as machinery, not final program acceptance | Publisher → R2 → VPS mirror → `board_state` CAS → identity-guarded client exists. The client refuses mismatched/stale board state rather than painting a lie. |
| Host-native close clock | `BUILT_NOT_PROVEN` for final SLO bar | `com.macro.closepass` and the host runner are deployed; replay/kickstart proof exists, but the final three natural sessions are not accepted. |
| Same-session close coverage | `PARTIAL` | Last durable exact breadth proof remains the 2026-08-14 post-#5746 replay: 1,684 / 1,763 = 95.5% evaluable; 58 corporate-action names darked, 19 genuinely barless. A current natural-session denominator is still owed. |
| W-ACCEPT ruler | `BROKEN` / open | Pre-2026-08-28 history does not contain three consecutive accepted close→candidate→reader sessions. Aug 17 hard-failed; Aug 18–25 lost the required Prophet-Live carrier; Aug 26 lacks a durable evening ruler row in canonical evidence. |
| Prophet-Live publication plane | `PROVEN_LIVE` for the Aug-26 silent-freeze class, but currently `PARTIAL` at program level | #6464/#6470/#6482/#6483 restored and proved publication/dead-man behavior. Aug 27 then exposed fresh-empty/global-dark and ahead-pack monitoring gaps. |
| D12 invalid/future pack tip | `BUILT_NOT_PROVEN` | #6554 now quarantines malformed, non-session and not-yet-completed final bars before **both** pack-tip selection and gate admission. Natural post-merge pack/evaluator/dead-man proof is still required. |
| Empty-state / ahead-pack sentinel truth | `BUILT_NOT_PROVEN` | #6569 merged the fresh-but-empty `prophet_live` streak breach and `pack_ahead_of_calendar` fence. Natural production proof is still required. |
| Board freshness plain-language UX | `BUILT_NOT_PROVEN` unless separately production-receipted | #6532 removes the misleading repeated signal bucket date and makes the U.S. board state `Data through <as_of>` / delayed truth plainly. Browser production acceptance belongs this program. |
| Prophet permanence net | `BUILT_NOT_PROVEN` | #6534 extends existing sentinel/liveness/rescue instruments and adds post-publish acceptance; it requires natural scheduled production proof rather than CI-only acceptance. |
| B1 candidate-episode intake | adjacent owner, `BUILT_NOT_PROVEN`/natural acceptance path | #6562 repaired the natural B1 ndarray receipt-hash crash. Breathing consumes its availability state only; it does not own B1 semantics. |
| W-L2 armed-level breadth | `PARTIAL` | Old measurement was highly budget-limited. Process fan-out already exists; the remaining question is whether current valid verified level coverage is materially constrained by budget after D12 correctness. |
| Tactical live-entry alerts | `PROVEN/ACTIVE` under another owner | `WS:LIVE-ENTRY-RADAR` is the separate tactical detector/evidence/alert product. Breathing must not recreate it. |

### 2.1 Critical correction from Aug 27

The completion plan may not assume that a fresh artifact clock means a healthy signal surface. On 2026-08-27 the Prophet-Live evaluator could publish fresh passes with an empty top-level `states` map while refusing a poisoned armed pack as `stale_pack`; the sentinel still reported the live surface healthy. #6569 closes the grader-side hole, but final completion must prove that repair naturally.

Therefore **freshness is a vector, not one timestamp**.

---

## 3. Architecture freeze — no-rebuild boundaries

These boundaries are binding for every child wave.

### 3.1 Canonical close truth

- The Mac-side canonical close store remains first authority when it contains the correct same-session bar.
- The existing Massive grouped-daily/snapshot fallback may fill the same-session close only under the already-accepted session-identity, case-sensitive ticker and corporate-action guards.
- Store-bar-wins remains binding.
- A same-session split/dividend ambiguity darks the name; it is never “repaired” by splicing a convenient raw close.
- `WS:MASSIVE-STOCK-DAY-R2-COHERENCE` owns the stock-day collector/publication plane. Breathing consumes; it does not rebuild that owner.

### 3.2 Close-pass compute

- Compute remains on the Mac/host-native lane where the canonical store and production gate live.
- No VPS-side canonical board engine.
- No second ranker, second signal gate, or local approximation of Prophet membership.
- The provisional board may only compute/disclose the score legs it can actually stand behind; no renormalization or imputation of omitted legs.

### 3.3 Publication and transport

- Full provisional board: existing `live/us_board_provisional.json` path.
- Browser projection: existing `board_state` key on the evaluator-owned `live/prophet_live.json` document.
- `close_pass_mirror` remains a transport/projection tool, never a ranker or signal engine.
- It never creates the Prophet-Live document.
- Exactly **two** lawful writers remain on `live/prophet_live.json`: the Prophet-Live evaluator and the close-pass CAS annotation path. No third writer.

### 3.4 Prophet-Live / armed-pack authority

- `WS:PROPHET-US-AVAILABILITY` owns publication, liveness, pack basis and D12 production acceptance.
- #6554's quarantine occurs before both stamp selection and gate submission; no stamp-only “fix.”
- Shared `armed_pack` calendar-neutral semantics and China semantics are not changed by Breathing.
- Manual `prophet-live.yml` dispatch while the VPS primary timer can publish remains forbidden because it can create a second live writer.

### 3.5 Reader truth

- `_bsQualify` remains the identity/freshness firewall. Fix payloads, never weaken the guard to make a demo paint.
- The board's `Data through` clock is the clock of the board data/cards, not a signal-bucket date.
- Independent live-strip health must remain independently visible/degraded.
- A stale/empty live strip must not silently inherit the healthy semantic meaning of a fresh board.

### 3.6 Monitoring

Extend existing instruments only:

- `freshness_sentinel.py` for outside-GitHub/live reader truth;
- `check_nightly_liveness.py` for GitHub/nightly failure-domain truth;
- `prophet_rescue.py` for the accepted bounded rescue policy;
- post-publish acceptance from #6534.

No fourth monitor registry, retry daemon or liveness control plane.

### 3.7 Scheduling and resources

- GitHub cron is not an accepted product clock for close-pass delivery.
- No new Massive WebSocket for this lane.
- No arbitrary timeout/memory inflation standing in for causal performance work.
- Throughput changes must name the measured bottleneck and preserve parity/edge verification.

---

## 4. Multi-clock freshness contract

Breathing uses one explicit vector of clocks. No layer may collapse them into one generic `fresh` claim.

| Clock | Owner | Meaning | Failure behavior |
|---|---|---|---|
| `session` / exchange calendar | canonical NYSE calendar | Which market session is legally current/completed | Calendar unknown => indeterminate/dark; never guess from wall clock alone. |
| close source session | close-pass source adapter | Session represented by store/Massive close | Wrong/missing session => name or pass cannot claim same-session value. |
| `close_observed_at` | close-pass receipt | First instant the accepted session close is actually available to this pass | Missing => ruler row cannot pass. |
| `first_candidate_at` | close-pass publisher/receipt | First accepted provisional board built from that close | Missing => no candidate; fail. |
| `first_user_visible_at` | reader-measured sentinel/client artifact | First instant an entitled reader can consume the same-session state | Missing => fail; never reconstruct from R2 timestamps. |
| board `as_of` / `Data through` | board payload | Data vintage of the cards currently shown | Must match cards/source; delayed state says so plainly. |
| `board_state.generated_at` / `valid_until` | close-pass projection | Provisional projection validity window | Expired/mismatched => client paints nothing provisional. |
| Prophet-Live `meta.pass_ts` / quote clock | live evaluator | Liveness of the independent intraday state plane | Stale => explicit live degradation/breach. |
| Prophet-Live `states` non-vacuity | live evaluator + sentinel | Whether a fresh pass actually contains a usable state population | Repeated in-window empty => breach; fresh timestamp alone is insufficient. |
| armed-pack `as_of` / `completed_through` | Availability | Pack evidence basis | Future/non-session/malformed tip never enters gate; ahead pack breaches. |
| nightly `source_asof` / board record | nightly Prophet | Canonical settlement record | Stale nightly is an Availability problem, not permission for provisional lane to redefine canon. |
| sentinel heartbeat | sentinel | Observer itself is alive | Missing/old heartbeat is independently graded by the opposite failure domain. |

### 4.1 The key UI rule

A fresh close-pass board and a stale/empty Prophet-Live strip are allowed to coexist **only if the product says so truthfully**.

The correct semantic result is not to hide the fresh board, and not to call the whole page healthy. The board may remain “Tonight's picks / Data through today” while the independent live strip is visibly unavailable/degraded and monitoring is red. Each statement must refer to its own clock.

---

## 5. Experience architecture — real states

### 5.1 During RTH before the close

- Nightly board remains the board of record.
- Existing live strips/risk context refresh on their own clocks.
- No invented “computing tonight's picks” state.
- Any live-plane degradation is visible on the affected live surface and monitors.

### 5.2 16:00 ET → provisional publication

1. Host-native close-pass fires from the existing scheduler.
2. It waits only for causally required session-close truth under the frozen source rules.
3. It evaluates the canonical universe.
4. It publishes the full provisional board.
5. Mirror lands the full board on the served plane and CAS-annotates `board_state` into the current evaluator document.
6. Browser identity guard compares the provisional board identity against the rendered cards.
7. On match and within validity, the board flips to the existing provisional “Tonight's picks” state.
8. Reader measurement records the first instant the same-session value is actually available.

Hard product gate: **first user-visible same-session board no later than 16:15 ET** on an accepted normal session.

### 5.3 Provisional ahead state

- The board itself says `Data through <same-session-date>`.
- The provisional stamp describes status relative to the nightly record, not data health of every other page component.
- Independent Prophet-Live health may be live or degraded; the page must not conflate them.

### 5.4 Nightly confirmation

- Nightly remains sole canonical settlement/forward-ledger advancer.
- Provisional vs nightly reconciliation produces the existing confirmation/adjustment/drop receipt.
- Provisional ornament disappears when the board becomes the record.

### 5.5 Behind / missed close-pass

- No stale provisional stamp.
- Last confirmed board remains visible with its actual vintage.
- The product says the early update did not land, using the already-approved quiet honesty pattern.
- Monitoring identifies the causal lane separately.

### 5.6 Empty/stale Prophet-Live with a fresh board

- Fresh board may remain if its own identity/clock is valid.
- Prophet-Live strip is explicitly degraded/unavailable; no fresh-empty false green.
- Sentinel/permanence instrumentation must agree with the degraded state.
- This combined browser state is a required final acceptance composition.

### 5.7 Market closed

- Last confirmed board is shown with market-closed copy.
- No false repair/caution semantics.
- No live quote advice when there is no live market.

---

## 6. Data, null, correction and authority law

### 6.1 Universe and identity

- Use the canonical U.S. universe already consumed by the production gate.
- Ticker identity remains vendor-case-sensitive at the Massive join boundary.
- No duplicate universe loader to make coverage look better.

### 6.2 Coverage accounting

Every canonical universe member must end in exactly one accountable class for the close-pass receipt:

- evaluated;
- corporate-action dark;
- no same-session close;
- identity/join refusal;
- source unavailable;
- deterministic gate/input refusal;
- other explicitly typed causal exclusion.

**100% accounted** is mandatory. For a normal accepted session, **≥95% evaluable same-session coverage** is the current production floor, because that bar has already been demonstrated in replay. Any lower natural session is a failed acceptance row unless a separately recorded market-wide/source-wide exception is adjudicated by Sol.

### 6.3 Nulls

- Missing is not zero.
- Unchecked/unverified armed level is not an armed level.
- Empty state population is not healthy.
- Missing `first_user_visible_at` is not estimated.
- Unknown calendar/source state degrades rather than guesses.

### 6.4 Corrections

- Same-session provisional output may be revised by the canonical later inputs/nightly path.
- The provisional lane does not back-write durable forward ledgers.
- Historical acceptance timestamps are append-only first-observation facts; later success does not rewrite a missed first visibility.

### 6.5 Deterministic vs statistical/model authority

- Close-pass membership and all final board authority here are deterministic production-gate derivations.
- Armed-edge verification is deterministic and fail-closed.
- Alert precision/promotions remain under their own registered prospective evidence law.
- LLM/model narrative has zero authority to originate, rank, gate, size or override Prophet trades in this program.

---

## 7. W-L2 redefinition — breadth outcome, not old implementation instructions

The old instruction “parallelize/raise the arming budget + alerts” is stale as an implementation packet.

### 7.1 Already superseded

- Process fan-out already exists in `build_prophet_live_pack.py`.
- Publication/liveness alerts now belong the Availability/permanence instruments.
- Tactical entry alerts belong `WS:LIVE-ENTRY-RADAR`.

### 7.2 Remaining Breathing question

After D12 is naturally proven correct, measure the current armed-level population:

- canonical universe count;
- fresh usable series count;
- names that want a probe;
- board vs cross probe candidates;
- verified armed levels by class;
- withheld/unverified levels;
- `invalid_series_tip`;
- stale series;
- deadline/cap classes;
- per-phase elapsed time and worker count;
- live evaluator population using those levels.

Then ask one product question:

> Is valid verified armed-level breadth materially limiting the same-session Breathing experience or machine observability?

If **no**, close the old W-L2 implementation idea by supersession with evidence. If **yes**, commission one bottleneck-specific throughput wave. That wave may improve locality, work partitioning, scheduling or an identified algorithmic hot path, but may not weaken parity/edge verification or simply inflate budgets until the nightly becomes unsafe.

---

## 8. Completion wave graph

Every modifying child wave is independently useful and gets its own operation key. Fable may stay principal/program-control across the thread, but implementation routing is chosen per child wave.

### C0 — Current production truth + acceptance recovery

**Type:** read-only archaeology / production proof recovery.  
**Goal:** establish the exact post-#6554/#6569/#6534 production state and recover the real Aug-26/Aug-27 close-pass ruler if it exists.

Required output:

- exact current `main` and deployed source identity;
- Aug-26 and Aug-27 ruler rows or explicit missing fields;
- Aug-27 combined board/live-strip browser state;
- current close-pass universe coverage receipt;
- current D12 and empty-state sentinel production state;
- current permanence-net natural proof state;
- a capability ledger and exact first causal gap.

**No code modification in C0.** A discovered code defect returns to Sol before effect.

### C1 — Natural Availability/D12/permanence acceptance

**Type:** production acceptance, usually no-code.  
**Goal:** on the first natural post-merge session, prove #6554/#6569/#6534 through the real pack/evaluator/sentinel paths.

Must show:

- `completed_through` = canonical last completed session;
- pack `as_of` is a real completed session ≤ bound;
- any invalid series tips are explicit non-verdicts and never enter the gate;
- evaluator does not globally dark as `stale_pack` from an impossible tip;
- repeated in-window fresh-empty state cannot stay green;
- sentinel/permanence net correctly grade the live system;
- no second writer/manual dispatch used to force proof.

A failure names the causal owner. Breathing does not absorb Availability code unless current ownership is explicitly transferred.

### C2 — Conditional Breathing causal repair

**Spawn only if C0/C1 produces a Breathing-owned failed row.**

Examples of legitimate causes:

- host-native close lane still starts too late for a causal reason;
- close source waits on the wrong dependency;
- close-pass candidate compute exceeds the SLO due a measured hot path;
- mirror/reader propagation loses the board despite healthy existing dependencies;
- client truth state misrepresents the board/live-strip vector.

One cause → one repair → production proof. No speculative bundle.

### C3 — W-L2 current breadth census

**Type:** measurement/read-only first.  
**Goal:** replace the 2026-08-15 `91/1761` memory with a current, classed, timing-attributed armed-level census under D12-correct input law.

Return one of:

- `W-L2 RESOLVED BY SUPERSESSION` — missing levels are intrinsic/typed and not materially limiting product/machine value; or
- `W-L2 MATERIAL GAP` — named budget/hot-path class materially excludes valid candidates, with a before/after target for one bounded repair.

### C4 — Conditional armed-breadth throughput repair

Only after C3 demonstrates a material causal gap. Preserve edge verification, parity and fail-closed publication.

Required proof:

- same real input before/after;
- level coverage by class;
- wall/CPU/memory breakdown;
- mutation that proves the optimized path does not admit an unverified level;
- no nightly cap regression;
- first natural pack proof.

### C5 — Browser truth + degraded-state acceptance

**Goal:** prove the actual product composition rather than individual JSON artifacts.

Required real/controlled states:

1. current provisional same-session board + healthy Prophet-Live;
2. current provisional board + stale/empty Prophet-Live;
3. missed close-pass / last confirmed board;
4. post-nightly confirmed board;
5. weekend/holiday.

At minimum verify desktop and narrow mobile; EN/ZH; both themes when a changed visual path is involved. Browser proof must confirm the cards, stamp, `Data through` clock, independent live degradation and no horizontal overflow/identity mismatch.

### C6 — W-ACCEPT three-session ruler

This is the final product acceptance clock.

**Streak reset rule:** any merge/deploy that can materially affect close observation, candidate computation, board publication/mirror, `board_state`, reader qualification, armed-pack basis, or the relevant live/degraded-state semantics resets the consecutive-session streak. Records-only changes do not.

Each of three consecutive natural NYSE sessions must record:

- session;
- `close_observed_at`;
- `first_candidate_at`;
- `first_user_visible_at`;
- close→candidate and candidate→visible decomposition;
- hard gate `first_user_visible_at <= 16:15 ET`;
- canonical universe / evaluated / typed exclusions;
- coverage ≥95% evaluable and 100% accounted;
- board `as_of` / visible `Data through` agreement;
- Prophet-Live pass/quote/non-vacuity and armed-pack basis state;
- sentinel/permanence verdicts;
- desktop+narrow browser proof that the same-session value is actually visible;
- no hidden manual dispatch/second writer used to manufacture the result.

Three green rows with no relevant reset between them completes W-ACCEPT.

### C7 — Durable closeout

Only after C1/C3/C5 and C6 are satisfied or explicitly superseded by evidence:

- set `WS:BREATHING-PLATFORM` done;
- mark each wave with exact PR/proof receipts;
- write one final Agent OS handoff with the final capability ledger;
- record any residual as a separate owner/workstream item rather than keeping Breathing falsely open;
- terminally STOP the COO child operation and disarm both watchers;
- no next child wave is authorized by the STOP.

---

## 9. Acceptance and falsifier matrix

| Failure | Expected honest behavior | Owner |
|---|---|---|
| Same-session close missing for a name | Name excluded with typed reason; no fake today close | Breathing close-source path |
| Same-session corp action ambiguity | Name darked | Breathing close-source path |
| Massive unavailable | Use valid store bar where present; typed gap elsewhere; no source substitution | Breathing consumes / Massive owner repairs source |
| Host close lane stale/unprepared | No candidate; alert/receipt; W-ACCEPT fails | Breathing |
| Provisional board published but mirror fails | Full-board artifact may exist but reader visibility fails; W-ACCEPT fails | Breathing transport |
| `prophet_live.json` absent/unparseable | Mirror never creates it; live plane degrades; no third writer | Availability |
| Prophet-Live pass fresh but `states={}` repeatedly | Explicit breach/degraded live strip; never green from timestamp alone | Availability/sentinel (#6569) |
| Armed pack ahead/non-session/malformed | Name quarantined before gate; ahead pack breaches sentinel | Availability (#6554/#6569) |
| Board identity differs from rendered cards | `_bsQualify` paints no provisional state | Reader guard |
| Board itself stale | Visible delayed/last-confirmed state with actual date | Board UX |
| Board fresh, live strip stale | Board remains truthful; live strip explicitly degraded; overall health is not falsely green | Shared experience composition |
| Sentinel blind/stale | Opposite-domain heartbeat grade surfaces observer failure | Availability/permanence |
| Queue/cron delay | Host-native close clock remains primary; do not move back to GitHub cron | Breathing |
| Resource pressure | Measure causal phase; do not solve with arbitrary standing inflation | Owning wave |

The program fails its completion bar if any falsifier can make the product look current while its own stated source/clock is stale or empty.

---

## 10. Collision map and owner boundaries

### `WS:PROPHET-US-AVAILABILITY`
Owns Prophet-Live publication, armed-pack basis, D12 natural acceptance, liveness/dead-man, rescue and permanence-net behavior. Breathing may require/prove these capabilities; it does not silently transfer them.

### `WS:PROPHET-US-V4-RECOVERY`
Owns V4 candidate/product/intelligence architecture and deterministic Availability integration. No second ranker, episode store, availability semantic or publication truth in Breathing.

### `WS:PROPHET-US-ENTRY-TIMING`
Owns held-out entry-timing research. Breathing does not retune Prophet selection/gating because a delivery SLO misses.

### `WS:LIVE-ENTRY-RADAR`
Owns the distinct 5-minute tactical entry detector/evidence/alert system. W-L2 does not recreate its alerts.

### `WS:MASSIVE-STOCK-DAY-R2-COHERENCE`
Owns stock-day acquisition/public-generation atomicity. Breathing uses existing same-session close semantics only.

### Current PR collision observation at freeze

At Macro base `ba270c60...`, searches found no open PR whose title/body directly matched `close_pass`, `prophet_live`, or `massive_stock_day`. This is a pickup-time observation only; every modifying child wave must re-run collision checks against current main/open PRs before editing.

---

## 11. Operator model and routing

### Principal program-control route

`ROUTE: Fable + Claude Code / equivalent sustained repo surface`  
`WHY: The completion program spans close-pass production receipts, Availability/D12/permanence, Massive source seams, multi-clock browser truth and several days of natural acceptance. The first task is architecture-sensitive state reconciliation, not ordinary feature coding.`  
`WHY FABLE: The current production truth changed repeatedly within one session (#6554, #6562, #6569); the principal must continuously adjudicate boundaries across Breathing vs Availability vs Radar vs Massive and carry the full acceptance thesis across natural sessions. A bounded ordinary worker is appropriate for later frozen implementation slices, but not for program-control continuity.`

Fable is **not** authorized to personally absorb every implementation PR. After each return, Sol routes the next bounded child mission to the least-scarce capable worker. Typical pattern:

- Fable: principal archaeology, integration adjudication, sustained production acceptance;
- Terra/Sonnet/Codex: normal bounded engineering once the cause is frozen;
- Opus: difficult bounded debugging/adversarial review;
- Luna/mechanical: fixtures/repetitive changes;
- Sol: architecture, rulings, PR review, final acceptance.

---

## 12. Sol ↔ COO dialogue and watcher protocol

The program-control Slack thread is a transport/hot-state carrier only. It does not own Job/Attempt/Worker lifecycle or implementation truth.

Rules:

1. One parent program thread may remain the communication locus, but **each independent child wave gets a fresh stable operation key** and fresh pickup/continuation setup.
2. The initial commission is `OPEN_PICKUP` until the Chairman assigns the exact COO receiver. No worker self-claims from retrieved Slack text.
3. Once assigned, the receiver immediately posts pickup ACK naming the exact operation key and receiver, reads the complete thread/canonical packet, arms the exact-thread continuation watcher, emits a truthful `WATCH_ARMED` receipt, then separately states execution start when the gate is clear.
4. Sol arms its own exact-thread temporary condition watcher after the thread exists.
5. Worker `BLOCKED`, `DECISION_REQUEST`, `RESULT` are nonterminal until Sol posts one explicit edge in the same thread: `SOL CONTINUE`, `SOL RULING / CONTINUE`, `SOL REQUEST_REPAIR`, or terminal `SOL ACCEPTED / STOP` / `SOL STOP`.
6. After every nonterminal return, the worker re-arms its watcher after its next return; Sol preserves its own continuation path.
7. Terminal STOP means the child wave is terminal, the worker stops, both temporary watchers are disarmed, no further reply is required unless shutdown fails, and no next child is authorized.
8. `WATCH_STOP_FAILED` is reported truthfully without reopening terminal work.
9. A new child wave requires new operation identity, fresh collision reconciliation, commission/pickup and watcher setup. An old watcher never originates the next wave.

The host-native temporary watcher is attention behavior only. It may detect a reply; it may not create a new work wave, merge, retry, reroute or claim completion.

---

## 13. Final definition of done

The Breathing Platform workstream closes only when all of the following are true:

### Truth

- same-session close source is correct, session-identified and corporate-action safe;
- D12 is naturally production-proven;
- stale/empty/ahead live states cannot stay green;
- every universe member is accounted and normal-session evaluable coverage is at least 95%.

### Intelligence/product

- close-pass uses the real production gate and honest partial scoring law;
- valid provisional board is browser-visible by 16:15 ET;
- board vs live-strip clocks are independently truthful;
- W-L2 breadth is either causally repaired or closed by evidence-backed supersession;
- nightly settlement remains canonical.

### Reliability

- permanence instruments observe the real surfaces and observer heartbeat;
- no third writer, second monitor plane, WebSocket or VPS board engine exists;
- no acceptance proof relies on a manual second writer or inferred reader timestamp.

### Product experience

- desktop+narrow browser proves same-session value and degraded states;
- `Data through`, provisional/confirmed/behind/closed semantics refer to the actual cards;
- a user cannot reasonably interpret stale independent source state as fresh because an adjacent board is current.

### Empirical acceptance

- three consecutive natural NYSE sessions after the last relevant production-changing merge pass every C6 ruler row.

### Durability

- Agent OS workstream/handoff reflects the final state;
- GitHub PR/proof receipts are exact;
- all child watchers receive explicit STOP and are disarmed;
- the next fresh Sol session needs no chat transcript to understand the ruling.

That is the completion boundary. Anything less is `PARTIAL`, `BUILT_NOT_PROVEN`, or a separately owned residual—not “done.”
