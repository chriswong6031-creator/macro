# Options Intelligence — Consolidated Masterplan & Program-Control Freeze (C0)

- **Original freeze:** 2026-08-28
- **Final current-state reconciliation:** 2026-08-30
- **Operation:** `options-intelligence-c0-consolidated-program-control-20260828-sol-001`
- **Carrier:** existing Macro PR #6604 only
- **Authority:** records/source law only; no runtime, scoring, ranking, sizing, trade, execution or Prophet authority
- **Decision:** `DEC:OPTIONS-INTELLIGENCE-C0-PROGRAM-CONTROL`
- **Continuation:** `agentos/handoffs/ADVANCED-DATA-OPTIONS-2026-08-28-options-intelligence-c0-program-control.md`

## 0. Current-state precedence

This document is the durable cross-workstream Options Intelligence program-control freeze. It is **not** a live status database. Current owner workstreams on Macro main own present-tense wave state and outrank historical status snapshots inside older C0 Git history.

The original C0 work proved the architecture did not need a fifth Options owner or another truth plane. Its later branch snapshot became stale because C0's own downstream adjudication succeeded: #6585 was independently reviewed, conditionally adopted and merged, and the Options Alpha owner advanced. The final #6604 release therefore preserves this masterplan/decision/handoff plus the authorized semantic-registry pointer, while leaving the four newer owner records untouched.

Historical facts are preserved, not laundered:
- #6585 was built out of order and without a lawful historical START;
- no retroactive START is minted;
- the original worker STOP/MAS-175 provenance remains evidence;
- later lawful adoption changes current capability state, not historical process truth.

## 1. Product thesis and completion model

Options Intelligence is not one score or one collector. It is a governed intelligence program spanning three user/machine jobs over one shared evidence substrate:

1. **Advanced Data Options (AD)** — settled EOD derivatives/off-exchange intelligence, exact source clocks, auditable receipts, and eventually calibrated bounded downstream contribution.
2. **Intraday Flow** — truthful current-session trader context: quotes, pulse, flow freshness, degradation and operator visibility. It does not originate a trade signal.
3. **Options Alpha (OA)** — live point-in-time exact-option/research-candidate workflow over existing evidence, with separately earned statistical authority and exact-option outcomes.
4. **Options Context Audit** — an independent audit/preregistration owner. It does not become a hidden AD/OA gate or a second context plane.

The end state remains **Truth + Intelligence + Product + Learning**. Code, CI, merge, a healthy file timestamp or a static dashboard does not equal completion.

## 2. Canonical owner / no-rebuild matrix

| Plane / job | Canonical owner | C0 law |
|---|---|---|
| ThetaData EOD options truth | existing ThetaData resolver/store + `WS:ADVANCED-DATA-OPTIONS` | One terminal/store/resolver; no Massive/Polygon options fallback or second truth store |
| Intraday options product/classification | existing Terminal + Macro live-flow owners / `WS:INTRADAY-FLOW-P0-RECOVERY` | No second intraday engine, WebSocket/store or duplicate classifier |
| Live-flow event evidence | existing `engine/live_flow.py` / event-stage path | Extend additive measured fields only under existing event identity |
| Options episode/campaign/outcome | existing options episode/campaign owners | Preserve old identities/rows; no replacement lifecycle ledger |
| Options candidate/calibration workflow | `WS:OPTIONS-ALPHA-INTELLIGENCE-RECOVERY` | Candidate/product authority remains separate from Attention/Salience |
| Context audit | `WS:OPTIONS-CONTEXT-AUDIT-PREREG-V2` | New v2 preregistration, never widen/evict/truncate v1 in place |
| Eval / evidence clock / promotion | existing Evaluation/qledger owners | No retrospective clock decoration; no C0-created promotion plane |
| Operator issue workflow | existing Options Issue Desk | No parallel trade/issue queue |
| Prophet | existing Prophet owner | C0 grants no new input/rank/size authority; current DNR rulings remain binding |
| Semantic program map | `config/mastermind_programs.yml` | Advisory canonical-doc pointer only; never runtime authority |

If a child concludes that another store, lifecycle, queue, score-control plane, identity system, watcher, ranker or execution path is required, it must return a typed architecture/authority decision request before building.

## 3. Current capability ledger

### Proven or accepted substrate

- **ThetaData T1 full-universe incremental cadence / AD-1T1:** `PROVEN_LIVE` and Sol-accepted. The old 0.104 coverage blocker is closed; accepted coverage evidence reached 0.9467.
- **AD-1 runtime / EOD brief:** `BUILT_NOT_PROVEN`. Producer/source work exists; end-to-end consumer/availability proof remains AD-1T2's job.
- **Intraday boot/OPEX repairs:** `PROVEN_LIVE` for the accepted boot/OPEX scope.
- **Intraday PR-4 live transport repair:** `BUILT_NOT_PROVEN`; one genuine current-session production dossier still owed.
- **Terminal polling/SSE options-flow presentation:** existing product capability; upstream freshness remains independently governed.
- **Prophet options input:** only the already-ratified bounded `gex_confirm_verdict` input may reach rank under its separate DNR amendment. C0 creates no wider fusion authority.

### Options Alpha

- **OA-0 architecture:** accepted/merged.
- **OA-1T plan #6576:** accepted/merged as plan/records only; it created no implementation START.
- **OA-1T implementation #6585:** implementation is now **MERGED / BUILT_NOT_PROVEN**. C3 independently performed the required line-level review, FS-4 `SAFE_UNDER_FREEZE` docket, exact-head/current-main proof and `scripts/**` authority acknowledgement. The byte-identical implementation carrier head `77f400630d8a47402f0fd71a8c23eec3d6822356` merged as `dbd654edb0fb47449b969b7dcb4fbafc2e0fe3ef`.
- **Natural-RTH ruler:** still open. OA-1T becomes `PROVEN_LIVE` only from a natural untouched RTH session emitting real measured evidence. Historical `--once --date`, replay or synthetic evidence is invalid proof.
- **FS-4:** code may exist, but `scoring.enabled=false` and the FS-5 kill/promotion gates remain binding. Merge does not confer statistical authority.
- **OA downstream candidate/UI/calibration/outcome waves:** dependency-held by current OA owner records and must use fresh operation identities.

### Context audit and retired rails

- Options Context Audit v1 remains honestly broken at its frozen complete-corpus boundary; the lawful successor is preregistration v2, not a timeout/cap/windowing patch.
- Massive/Polygon options sourcing is retired/rejected as canonical options truth.
- Legacy Flow Leaders repoint remains prohibited.
- Sparse-selector/W1A remains research-only/dark until separately adjudicated.
- Host-side disarmed/stale launchd inventory is not live simply because plist files exist.

## 4. Time, null, correction and identity laws

- Evidence is usable only at or after its true availability time. Later-settled OI/NBBO/Greeks may not be backfilled into an earlier decision as if known then.
- Missing/unknown stays null/unavailable, never zero or inferred health.
- Quote, pulse, live-flow, EOD, outcome and evaluation clocks remain distinct.
- Existing event/episode/campaign/outcome identities stay canonical; corrections append/retain history rather than rewriting it.
- Static product render, HTTP 200, file mtime, deployment time or green CI cannot launder stale source evidence into a live state.

## 5. Authority ladder

The following remain separate and cannot be collapsed:

`measurement -> descriptive context -> research candidate -> calibrated/evaluated family -> promotion proposal -> accepted downstream decision authority`.

C0 authorizes only architecture/program sequencing. LLM prose/sentiment cannot invent event identity, score, rank, sizing, entry/exit or trade authority. Current DNR decisions — including no fused positioning super-score and no unapproved LLM origination — remain binding.

## 6. Reconciled #6585 ruling

The permanent process record is:

1. #6585 was created out of order before the accepted plan-merge sequence and without a lawful historical START.
2. Sol explicitly refused to erase that history or create a retroactive START.
3. Replacement implementation was also disallowed; the correct path was conditional adoption of the existing artifact after stringent inspection.
4. Chairman written-spec approval was later located on #6573; #6576 plan merge stood; the remaining adoption gates were then executed by the C3 child.
5. C3 passed the independent review and frozen safety docket and merged the exact implementation unchanged.
6. Therefore the **current** state is `BUILT_NOT_PROVEN`, while the **historical** state remains “out-of-order implementation with no lawful historical START.” Both are true and must remain visible.

This is a governance precedent: process defects are not repaired by destroying useful lawful code, but successful output never retroactively legitimizes the forbidden route.

## 7. Current dependency graph

### Advanced Data

`AD-1T1 PROVEN_LIVE/accepted -> C0 canonical -> fresh AD-1T2 operation -> end-to-end AD-1 consumer/availability proof -> only then later AD waves`.

AD-1T2 is the exact next Advanced Data product dependency after C0, subject to fresh Runner-Fleet/M1 collision/admission checks. Broken R2 sync is not presumed a prerequisite absent new evidence.

### Intraday Flow

PR-4 remains a separate current-session proof lane. It must prove board-scoped quote coverage/freshness, current pulse semantics, naturally advancing canonical M1/R2 options flow, semantic `/api/status`/dead-man health, and actual served desktop+narrow behavior. Stop at the first causal failure and repair narrowly.

### Options Alpha

`OA-1T merged BUILT_NOT_PROVEN -> natural-RTH evidence -> lawful candidate composer/preregistered policy + AD-1T2 EOD availability -> product UI -> evaluation/promotion -> exact-option outcome/right-conditioned families only if separately authorized`.

Do not treat Attention/Salience as probability. Do not relabel the unsigned FS score directional. Do not infer exact-option outcomes from underlying/EOD/mid substitutes when NBBO is missing.

### Context Audit

V2 is independent and may proceed under a fresh bounded charter; it is not an AD-1 blocker and must not be smuggled into an unrelated recovery PR.

## 8. Release / child law

- C0 itself is records-only. Landing it does not START AD-1T2, Intraday proof, Context v2, OA natural-RTH proof or any implementation wave.
- Every future child needs a fresh operation key, lawful receiver assignment, reciprocal carrier/watch setup and separate START after action-time collision/source checks.
- `WAITING_CAPACITY` remains waiting capacity; placement/census prose cannot create a session or worker.
- One logical modifying operation stays on one carrier until reconciled.
- Green CI, merge and Slack delivery remain distinct from execution, production proof and final acceptance.

## 9. Current continuation

After C0 is on main:

1. **AD-1T2** may be commissioned as a fresh bounded product-proof operation after fresh Runner-Fleet/M1 checks.
2. **Intraday PR-4 dossier** continues under its existing owner as a separate product-proof lane.
3. **OA-1T natural-RTH proof** remains owed; do not manufacture it.
4. **Options Context Audit v2** may receive its own charter child.
5. Any OA downstream candidate/calibration/outcome work follows current OA dependencies and separate promotion law.

The four current workstream records on Macro main are the live-status index. This masterplan is the architecture/no-rebuild/dependency law that lets those owners cooperate without becoming one giant duplicated system.
