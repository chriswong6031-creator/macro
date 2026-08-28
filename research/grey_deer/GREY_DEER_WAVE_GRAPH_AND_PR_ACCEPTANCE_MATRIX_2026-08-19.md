# Grey Deer — Wave Graph, PR Plan, Acceptance Matrix, and Collision Fences

**Date:** 2026-08-19
**Purpose:** Mechanical execution index for Fable. This file does not supersede the architecture freeze or Fable command packet.

---

# 1. Wave table

| ID | Capability | Repo | Primary owner | Depends on | Initial authority | One-PR end state |
|---|---|---|---|---|---|---|
| GD-0A | Durable program + decisions + semantic registration | Macro | Fable | none | records only | Fresh session can discover exact Grey Deer law/next action |
| GD-1A | PIT prereg + source-clock census | Macro research | Grok | GD-0A for merge; may execute parallel | research | Outcome-blind hash-pinned protocol exists |
| GD-1B | Existing-organ replay + Prophet counterfactual | Macro research | Grok | GD-1A | research | Exact incident timeline and null/positive findings |
| GD-2 | Settled envelope + three-answer Macro hero | Macro | Fable-directed builder | GD-0A | display/advisory | Real settled session visible in production |
| GD-3 | Live provisional envelope | Macro/VPS | Fable-directed builder | GD-2 | display/advisory | Real intraday change visible with latency receipt |
| GD-4A | CN/HK forward-ledger liveness repair | Macro | bounded builder | GD-0A | operational truth | Real Asia close advances ledger once |
| GD-4B | China Prophet board-health observation | Macro | bounded builder | current live board | display only | Real board-wide damage state visible |
| GD-4C | PBOC liquidity-composition read | Macro | bounded builder | PBOC collector | display/context | Zero-op vs drain/rollover/support is distinguishable |
| GD-5A | Duration shock expert | Macro shadow | Grok→builder | GD-1B | shadow | PIT replay + forward accrual begins |
| GD-5B | Crowded-winner liquidation expert | Macro shadow | Grok→builder | GD-1B | shadow | Distinct crash species accrues |
| GD-5C | Repair expert | Macro shadow | Grok→builder | GD-1B | shadow | Repair impulse/broadening/confirmation forward state |
| GD-6A | U.S. Prophet market-eligibility sidecar | Macro | bounded builder | GD-2 + US board contract | shadow | Raw board unchanged; hypothetical actions accrue |
| GD-6B | China Prophet market-eligibility sidecar | Macro | bounded builder | GD-2 + GD-4B | shadow | Raw CN board unchanged; hypothetical actions accrue |
| GD-7A | Temporary China new-entry protection | Macro | Fable | GD-6B + explicit Chairman activation | temporary operator safety | Real admitted exposed candidate visibly withheld |
| GD-8A | Grey Deer alert integration | Macro | bounded builder | GD-3 | display/notify | Real transition produces one deduped alert |
| GD-8B | Terminal envelope mirror | Terminal | bounded builder | GD-3 | presentation | Same Macro bundle ID visible in Terminal |
| GD-9A | Portfolio envelope shadow adapter | Mastermind | bounded builder | GD-3 | shadow | Real envelope consumed, zero book mutation |
| GD-10 | Portfolio market-truth cutover | Mastermind | Fable | GD-9A + prospective proof + Sol/Chairman | decision-bearing | Portfolio consumes Macro truth + rollback proven |
| GD-11 | Promotion/learning scorecard | Macro + consumers | Fable | all accruing waves | evaluation | Matured alerts/policies have calibration/capital utility |

---

# 2. Parallelism rules

### Safe parallel after GD-0A

- GD-1A/GD-1B research
- GD-2 settled product
- GD-4A China ledger repair
- GD-4B board health
- GD-4C PBOC context

These do not share authority paths if scoped correctly.

### Safe parallel after GD-2/GD-4B

- GD-3 live envelope
- GD-5 research/shadow expert implementation after GD-1B
- GD-6A/6B sidecar shadow
- GD-8A alert design

### Must not parallelize authority changes without Fable coordination

- GD-7 temporary policy with any Prophet admission/ranking PR;
- GD-10 Portfolio cutover with any independent Portfolio market-risk/posture arming;
- Signal Bus/CI/workflow changes that collide with current control-plane PRs.

---

# 3. Future PR acceptance cards

## PR card — GD-0A

**Mission:** durable architecture discoverability.
**Changed categories:** research, AgentOS, semantic registry, generated map.
**No:** runtime, workflow, CI, site, data.
**Proof:** AgentOS 0 errors; generated system map check; fresh grep/navigation resolves one canonical program.
**Reviewer:** Sol.

## PR card — GD-1A

**Mission:** outcome-blind prereg and clocks.
**Changed categories:** research only.
**Proof:** prereg hash, clock ledger, rights/gap table.
**Reviewer:** Fable + independent researcher.

## PR card — GD-1B

**Mission:** replay and counterfactual.
**Changed categories:** research outputs only.
**Proof:** reproducible manifest; adversarial review; no runtime.
**Reviewer:** Fable, Sol on architecture implications.

## PR card — GD-2

**Mission:** settled user-facing semantic repair.
**Changed categories:** pure composer, settled builder, contract, Synapse, Macro render, tests.
**Proof:** real settled session on production browser at breakpoints.
**Reject if:** JSON exists but hero/drawer not live.

## PR card — GD-3

**Mission:** live provisional state.
**Changed categories:** existing live plane only.
**Proof:** real intraday source→browser measured latency; durable data tree unchanged.
**Reject if:** new quote owner/scheduler appears.

## PR card — GD-4A

**Mission:** Asia ledger advances.
**Proof:** real settled run + one new row + idempotent rerun + heartbeat.
**Reject if:** env var changed without reproducing root cause.

## PR card — GD-4B

**Mission:** board-wide stress visible.
**Proof:** real live board aggregate; mutation cannot change rank/admission.

## PR card — GD-4C

**Mission:** PBOC composition readable.
**Proof:** official bulletins → typed current state; zero-op ample-liquidity test.

## PR card — GD-5A/B/C

**Mission:** one shadow expert each.
**Proof:** PIT backtest/replay + forward ledger begins + no authority.
**Reject if:** expert ships together with policy authority.

## PR card — GD-6A/B

**Mission:** sidecar shadow.
**Proof:** board hash identity; exact raw board byte/digest parity; sidecar counterfactual starts.
**Reject if:** raw board population/order changes.

## PR card — GD-7A

**Mission:** temporary China new-entry safety.
**Proof:** real admitted candidate withheld from actionable projection but present raw/all-ranked; counterfactual retained.
**Authority:** explicit Chairman activation.
**Reject if:** automatic exit or blanket rank rewrite.

## PR card — GD-8A

**Mission:** alerts.
**Proof:** one real transition, one deduped notification, correction/expiry handled.

## PR card — GD-8B

**Mission:** Terminal mirror.
**Proof:** same bundle ID as Macro; stale state honest; no local recompute.

## PR card — GD-9A

**Mission:** Portfolio shadow.
**Proof:** real envelope imported, diff receipt, zero book mutation.

## PR card — GD-10

**Mission:** Portfolio cutover.
**Proof:** real book-policy path, stale fail-safe, rollback, prospective shadow evidence.
**Authority:** Sol + Chairman.

## PR card — GD-11

**Mission:** learning.
**Proof:** matured real observations/actions visible; no empty scorecard theatre.

---

# 4. Path fences

## Macro — Grey Deer-owned candidate paths

Until exact implementation archaeology changes the names, Grey Deer may own:

```text
research/grey_deer/**
engine/risk_envelope.py
scripts/build_risk_envelope.py
scripts/build_live_risk_envelope.py
site/riskdata/risk_envelope.json
site/live/risk_envelope.json
contracts/...risk_envelope...
agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
agentos/decisions/DEC-RISK-*.md
agentos/handoffs/GREY-DEER-*.md
```

UI-specific owned paths are assigned per PR only after reference/archaeology. Do not pre-claim broad templates directories.

## Explicit foreign-owner paths

Grey Deer does not own:

```text
engine/entry_radar/**
research/live_entry_radar/**
engine/prophet_lab/**
research/prophet_v4/** except a narrowly referenced Grey Deer adapter doc if explicitly assigned
engine/china_board_rank.py
engine/us_board_rank.py
engine/prophet_bridge.py raw ranking/admission semantics
Mastermind Executive OS authority/worker/scheduler paths
Terminal chart/quote ownership internals
```

A later Grey Deer consumer edit to a foreign-owner path requires a wave-specific handoff and owner review; it does not become Grey Deer-owned globally.

---

# 5. Current collision fences as of 2026-08-19

### Macro #5925

Do not touch `engine/entry_radar/live_pack.py` until accepted/merged/reconciled.

### Macro #5929

Do not touch its Radar transport/reconciler paths. Grey Deer live work consumes the result later.

### Macro #5928

Do not insert Grey Deer behavior into Prophet Lab API.

### Macro #5954

Do not edit `.github/ci/legacy-jobs.yml` or `scripts/run_ci_pack.py` from Grey Deer until this control-plane PR is resolved and Grey Deer rebases.

### Macro #5948

Do not edit `backfill.yml` from Grey Deer.

### Terminal #418/#419

Avoid shared generic e2e files; use dedicated Grey Deer tests.

### Mastermind #66/#72/#84

Avoid Executive OS constitutional/authority/harness paths.

---

# 6. Authority checkpoints

| Checkpoint | Who can approve | What changes |
|---|---|---|
| GD-0 architecture landing | Sol | Durable records only |
| GD-2/3 display semantics | Sol | User product presentation, no capital authority |
| GD-5 expert shadow | Fable + Sol architecture review | Research/shadow only |
| GD-6 sidecar shadow | Sol | Counterfactual only |
| GD-7 temporary China policy | **Chairman** after Sol/Fable readiness | New-entry actionability |
| Earned new-entry authority | **Chairman** after frozen gauntlet | Persistent policy authority |
| Size authority | **Chairman** after separate gate | Suggested/portfolio constraints |
| Portfolio cutover GD-10 | **Sol + Chairman** | Decision-bearing market-truth source |
| Automatic exit | Not available in V1 | Requires future new architecture ruling |

---

# 7. Definition/era rules

Every material change to:

- hazard transition rules;
- policy scope/action;
- vulnerability classification;
- Prophet eligibility construction;
- forecast model;
- repair definition;

mints a new version/definition and forward cohort. Historical rows are never relabeled to make a new construction look seasoned.

---

# 8. Release/rollback rules

Every live behavior PR must name:

- feature flag or kill switch where appropriate;
- last accepted contract version;
- rollback procedure;
- whether rollback changes only serving behavior or also stops forward accrual;
- how in-flight policy/episode history remains queryable.

Rollback must not delete ledgers, re-stamp eras, rewrite Prophet boards or erase policy counterfactuals.

---

# 9. Program “done” definition

Grey Deer is not complete until all four are true:

### Truth

Fresh, PIT/correction/right-safe market inputs and honest staleness.

### Intelligence

Named hazard species, transmission, vulnerability, repair and calibrated forward evidence.

### Product

Coherent three-answer experience; Prophet actionability; Terminal/Portfolio parity; all failure states.

### Learning

Evidence that the system improves drawdown/expected-shortfall/customer decision quality without unacceptable false alarms or upside destruction.
