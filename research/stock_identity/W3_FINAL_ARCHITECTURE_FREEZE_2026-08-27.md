# Bottom-Up Stock Identity & Expert Routing — W3→Final Architecture Freeze

**Frozen:** 2026-08-27  
**Chairman outcome:** prove and lawfully integrate the original Stock Identity / Expert Routing thesis, or kill it at its preregistered evidence bar.  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@cef4332d3682991e3e1c3d6160da17cd0a3a8f63` (`mastermind.sol_skillpack.v1`, v1.0.0, bootstrap-major 1 compatible).  
**Macro pickup base:** `5dad2bd413268ece0ac2c49e645142b2d449e57f`.  
**Binding research contract:** `research/STOCK_IDENTITY_EXPERT_ROUTING_MASTERPLAN_BY_FABLE.md` plus ratified `DEC:SI-METHOD-LAW-CHANNELS`.  
**Authority:** research/display only unless a later, separately preregistered promotion wave explicitly grants more. Prophet rank/gate/size/trade authority is NOT granted by this freeze.

## 1. Recovered thesis

The user job is not “pick the best indicator for each ticker.” It is:

> Understand how an individual traded security behaves, how that behavior changes across identity epochs, what kind of path episode it is experiencing, and which preserved entry-expert families have historically been informative in comparable structure — with visible abstention when the evidence is not estimable.

The machine job is to maintain point-in-time, correction-safe objects for:

1. **Instrument identity** — the traded listing, with ticker reuse/corporate-identity hygiene and explicit source lineage.
2. **Behavioral fingerprint** — interpretable, unit-free, PIT path statistics with coverage masks.
3. **Identity epoch** — a slow-changing behavioral regime whose boundary has a real knowable-from clock.
4. **Current state** — coarse bars-only path condition; context, never an outcome-selected routing key.
5. **Path-anchored episode** — an expert-independent reversal/opportunity window.
6. **Expert event** — a preserved `mastermind.entry_event.v1` family/provenance object owned by Live Entry Radar / canonical producer history, never flattened into one generic signal.
7. **Conditional fit** — localization quality measured on the preregistered ruler with honest episode/calendar-cluster N.
8. **Abstention** — a first-class output whenever identity, coverage, power, epoch stability, or fit separation is insufficient.
9. **Learning** — historical name-disjoint evaluation followed by real prospective shadow accrual on frozen definitions.

The moat is the combination of PIT security identity, long-run path fingerprints, behavior-change detection, preserved expert-family history, expert-independent episode/ruler measurement, and honest future evidence. Provenance is necessary but is not itself the intelligence product.

## 2. Binding no-rebuild / authority law

These are immutable unless Sol/Chairman explicitly supersede them in a new decision:

- **`DNR:KILL-OUTCOME-AUDITION` remains total.** A name may never choose an expert because that expert ranked best on that name's own historical outcomes, under the localization ruler or any other ruler.
- The only lawful personalization channels in the first arc are the ratified A/B/C channels:
  - **A:** one global cross-sectional map from measured fingerprint to expert fit, learned over names together and tested name-disjoint OOS;
  - **B:** behavioral-neighbor pooling in fingerprint space;
  - **C:** bounded empirical-Bayes own-name residual evidence with printed component N and `w=n/(n+k)`, never argmax.
- Ticker is continuity/memory, never a model feature or strategy key. Ticker-specific expert construction requires a new preregistration above A/B/C.
- No top-down sector/archetype label may become the selection/grouping key. Sector is a comparison baseline/diagnostic only.
- No second event store, replay framework, lifecycle, queue, grader or correction plane. W2's historical replay remains the bounded historical reconstruction already justified against R1; prospective expert truth comes from Live Entry Radar's canonical event path.
- Stock Identity never writes the Radar event store and never rewrites immutable `mastermind.entry_event.v1` events.
- `data/massive_stock_day` remains prohibited for behavioral math until adjustment/corporate-action semantics are independently proven.
- Reused tickers, issuer renames and cross-listings must remain instrument-hygiene-first. W1-A1's GOLD/Barrick correction is binding: sealed GOLD = Gold.com/A-Mark dealer; effective miner roster = `NEM AEM PAAS WPM AG B`; B is design-touched/nonconfirmatory.
- Class-P families are prospective only. Structural absence / not-yet-available / no-coverage / measured-zero are distinct states.
- All Stock Identity artifacts carry explicit zero authority unless a later promotion grants otherwise. A promising table does not change Prophet.

## 3. Current capability ledger

| Capability | State | Current truth |
|---|---|---|
| W0 archaeology + frozen research contract | `PROVEN_LIVE` | PR #5583 landed and §16 rulings were ratified. |
| W1 Identity Atlas v0 | `PROVEN_LIVE` | PR #5612 landed; sealed calibration/blind partitions, fingerprints, state tagger, path episodes, survivor-only census and dossiers exist. |
| W1-A1 identity correction | `PROVEN_LIVE` | PR #5660 landed; GOLD/Barrick interpretation repaired without rewriting sealed W1 measurements. |
| W2 expert replay/provenance | `PROVEN_LIVE` | PR #5643 landed; 31,119 era-pinned events / 34,491 attribution rows across 22 pilot names; all authority false. |
| Episode localization ruler | `NOT_BUILT` | No `ruler.py`, no executable C-LOC-R/C-LOC-D implementation on current main. |
| Estimability census / honest effective N | `NOT_BUILT` | Existing W1 census is descriptive coverage, not W3 fit-estimability law. |
| Dead Instrument Control Set | `NOT_BUILT` | W2 hard blocker remains: >=5 identity-resolved terminated U.S. instruments with fingerprint-compatible full adjusted OHLCV. |
| Identity epoch detector v1 | `NOT_BUILT` | Only provisional listing-to-date `epoch_0` exists. |
| PIT/final epoch dual fit views | `NOT_BUILT` | Requires W4. |
| Q1 power gate + confirmatory OOS fit | `NOT_BUILT` | No W5 carrier/result exists. |
| Behavioral neighborhoods / B pooling | `NOT_BUILT` | Reserved behind W5 consequence gate. |
| Channel-C EB residual operationalization | `NOT_BUILT` | Method law exists; no accepted production/research output. |
| Abstention contract | `SPEC_ONLY` | Frozen in masterplan; not yet a real fit/SIF output. |
| SIF v1 | `NOT_BUILT` | No current machine consumer exists outside Stock Identity research/build scripts. |
| Live Radar prospective expert feed | `PROVEN_LIVE` as owner substrate | Radar current owner records document real canonical envelopes and W5 durable reconciliation. Stock Identity has not yet consumed them. |
| Prospective Stock Identity shadow | `NOT_BUILT` | No qledger/current Evaluation OS enrollment, no frozen forward evidence clock. |
| Visible operator/research utility beyond W1 dossiers | `PARTIAL` | Dossiers are useful descriptively; no current integrated Stock Identity research view. |
| Downstream machine consumption | `DARK_OR_DISCONNECTED` | No app/API Stock Identity consumer is wired. |
| Prophet rank/gate authority | `REJECTED_BY_DESIGN` for this arc | Any future authority requires a separate promotion charter/gauntlet; this program cannot self-promote. |

## 4. Recovered statistical contract

### 4.1 Episode ruler

The ruler remains expert-independent and path-anchored. It measures episode localization, not generic long-horizon return. Required metrics are lead/lag, raw and ATR-normalized anchor distance, MAE, capture, false start, flooding, recall@tier, zone precision, relative order and consistency. Every family also prints the unconditional block: fires/name/year and episode-attribution rate. No fit claim exists without attribution rate.

Two and only two primary composites are graded:

- `C-LOC-R = recall@tier * zone_precision - lambda_fs * false_start_rate`
- `C-LOC-D = rank-normalized median ATR distance to anchor`, gated by recall floor and penalized for false starts.

`lambda_fs`, recall floor and any declared composite constants are set exactly once from `SI-SEALED-CAL-P1`, recorded with spec hashes, and never retuned after confirmatory outcome exposure.

### 4.2 Grain, dependence and N

- Grain/timeframe is always stratified; no cross-grain rank without a matched cadence control.
- Honest N is a pair: distinct path episodes plus distinct calendar clusters/blocks. Calendar-block bootstrap block length is at least the P90 episode duration; two-way name × calendar-block variance is reported alongside.
- Cluster concentration, top-three-cluster share, fires/year, attribution rate, joint-cell occupancy and feature availability must be printed before fit.
- Below preregistered floors is `UNESTIMABLE`, never zero/negative/null evidence.

### 4.3 Mandatory nulls/controls

1. Count/dwell-matched random fire placement.
2. Frozen naive comparators.
3. Global expert base-rate distinctiveness.
4. Equal-proximity comparison.
5. Name-permutation null for Channel A.
6. Grain/cadence null.
7. Dead-instrument survivorship control once the registered terminated-instrument substrate exists.

### 4.4 Primary questions and stopping law

- **Q1:** Does Channel A predict localization fit on held-out names? Primary metric = within-expert across-name Spearman between predicted and realized composite under name-blocked K-fold OOS. Both C-LOC-R and C-LOC-D are graded. Success uses the frozen intersection-union test against sector-label and name-shuffled baselines at alpha .05. Blind arm is separately reported.
- **Q2:** Do fingerprint neighborhoods transfer better than sector grouping? BH q=.10 with Q3 only.
- **Q3:** Does bounded Channel-C residual evidence add OOS value beyond A+B? BH q=.10 with Q2 only.
- **Q4:** Exemplars are descriptive coverage only and cannot rescue failed blind evidence.

Before Q1, the power simulator evaluates the post-exclusion grading pool. If power at the declared MDE is <0.50, Q1 is `NOT_RUN / ABSTAIN`; the program does not reinterpret underpower as a positive or null result.

The frozen §14.1 consequence matrix remains binding:

- Q1 fails both baselines -> expert-routing thesis stops; append a kill/DNR record. Descriptive identity/fingerprint/epoch work may remain with zero routing authority.
- Beats global/reference base but not sector-label map -> Channel A closes; only explicitly allowed bounded descriptive/shrinkage work may continue. B requires a new registered question.
- Pilot+blind aggregate passes but blind fails -> exemplar-scoped only; no pooling/product routing; widening the untouched blind arm by the registered procedure is the only regrade path.
- Blind passes -> GO to W6 operationalization.

## 5. Current blockers that must not be hidden

1. **Survivorship truth:** current allowed W1 planes do not retain enough ceased tapes. W2 registered the Dead Instrument Control Set as a hard PR-5/Q1 blocker. A new source act must provide >=5 identity-resolved terminated U.S. instruments with full adjusted OHLCV compatible with fingerprint/episode machinery, with rights/source/correction semantics and no relabelled live names.
2. **Epoch truth:** only `epoch_0` exists; any fit before W4 would violate the registered PIT-epoch contract.
3. **Effective-N truth:** W1's universe-wide v0 cluster component is degenerate and cannot be used as inferential effective N. W3 must produce an actual calendar-cluster/dependence census.
4. **Segmentation reliability:** the frozen `N=42` episode segmentation constant missed the 80% stability floor. It may remain the preregistered segmentation constant but earns no Channel-A predictive authority without the registered reliability treatment; W3 must print its sensitivity/coverage consequences rather than silently upgrading it.
5. **Prospective family maturity:** STARTER trio, amber-EARLY, Door-R and other Class-P families cannot be backfilled. Their eventual fit claims need true future observations from their first lawful availability.
6. **Consumer gap:** no current app/API/product consumer reads SIF or Stock Identity fit. Product integration is not complete merely because research artifacts exist.
7. **Autonomy transport:** current Autonomy V1 records state generic Slack `#agent-dispatch` has no worker/Fable receiver and Executive multi-seat/ASD dialogue is not yet production-proven. A Slack post is not a Fable claim. Program records may be commissioned now, but execution starts only on a real claimed principal-builder/Executive carrier.

## 6. Frozen W3→final wave graph

The program is persistent; implementation carriers are bounded. One independently useful capability per PR. Fable may split a wave further for collision/resource reasons but may not skip dependencies or change statistical law without Sol return.

### SI-W3A — Episode ruler engine

**Mission:** make the frozen localization ruler executable and deterministic without publishing expert-fit conclusions.

Deliver C-LOC-R/C-LOC-D component math, attribution/unconditional blocks, grain matching, null generators, spec hashing, sealed-calibration constant-setting once, synthetic/truncation invariance, and TrialLedger registration for any sweep. No blind fit table, no per-name expert choice, no Prophet paths.

**Exit:** deterministic fixtures + real pilot smoke reproduce metric identities; constants/inputs are sealed and hash-pinned; authority false.

### SI-W3B — Estimability and dependence census

**Mission:** determine which ticker×epoch×episode×expert questions can honestly be estimated before any confirmatory fit is opened.

Deliver episode/fire occupancy, calendar-cluster/effective-N diagnostics, concentration, attribution/flooding, feature/plane availability, grain coverage, `UNESTIMABLE` reasons, and the power-simulator input table. Refine dependence accounting without turning clusters into predictive features.

**Exit:** every candidate grading cell has explicit estimable/unestimable state and no fit score is shown.

### SI-W3S — Survivorship / Dead Instrument Control Set

**Mission:** close the W2 hard survivorship blocker on a separately preregistered source act.

First inventory current canonical data owners before acquiring anything. Reuse an existing adjusted historical plane if it now satisfies the contract. If none does, add only the minimum registered source adapter/snapshot required for >=5 terminated U.S. instruments; record instrument identity, terminal reason/date, known-at clocks, adjustment/corporate-action semantics, rights/source hash, corrections and coverage. Never create a second market-data platform.

**Exit:** >=5 terminated instruments pass the same fingerprint/episode math and are included as a control cohort; or the wave returns `BLOCKED_NO_LAWFUL_DATA`, which blocks W5 Q1 rather than substituting survivor-only evidence.

`SI-W3A`, `SI-W3B` and `SI-W3S` may overlap only after current-main/changed-path collision checks; W3B depends on the W3A metric schema but may stage independent non-fit census machinery.

### SI-W4A — Identity epoch detector v1

**Mission:** replace provisional `epoch_0` with a real behavior-change detector.

Use the preregistered trailing-252d fingerprint stepped ~21d, shrunk-Mahalanobis preceding-vs-trailing distance, persistence K, minimum-epoch law and explicit confirmation lag. Structural covariates annotate only.

Validate stationary-bootstrap false-boundary rate, synthetic-shift power, face cases, and ±20% threshold plateau. Freeze detector spec/thresholds before any W5 fit result.

**Exit:** each boundary has `start`, `knowable_from`, confidence, shifted features and continuous drift; no fit authority.

### SI-W4B — PIT/final epoch projection

**Mission:** make epoch semantics usable by the ruler/fit path without leakage.

Emit both `epoch_pit` and `epoch_final` views. Primary Q1-Q3 may grade only `epoch_pit`; `epoch_final` is diagnostic. Add truncation/replay tests proving future boundaries cannot relabel a past PIT row.

**Exit:** fit-ready cells are keyed to PIT epochs and the provisional `epoch_0` path is no longer silently used for confirmatory work.

### SI-W5P — Power gate and blind-arm finalization

**Mission:** decide whether the preregistered confirmatory read is runnable before opening Q1 outcomes.

Use W3B estimability/dependence plus W3S survivorship controls. Final blind size may only prefix-shrink or extend from the untouched clean pool using the frozen stratified seeded procedure. No hand swaps.

**Exit:** immutable `RUN_Q1` or `NOT_RUN_UNDERPOWERED/BLOCKED_SURVIVORSHIP` receipt with population hashes and no confirmatory metric table if not runnable.

### SI-W5Q — Confirmatory fit read

**Mission:** execute the frozen Q1-Q3 and descriptive Q4 once, without rescue tuning.

Use name-disjoint OOS, sealed calibration exclusion, PIT epochs, both composites, all mandatory nulls, honest N, block bootstrap, blind arm, survivorship cohort and frozen family specs. Print missing/unavailable/structural-zero separately.

**Exit:** exact immutable fit-read artifacts, all authority false, plus machine-readable consequence input. No implementation decision is inferred from visual appeal.

### SI-W5R — Sol adversarial adjudication / consequence gate

**Mission:** independently test leakage, identity hygiene, cluster dependence, cadence artifacts, multiple-testing law, baseline definitions, blind integrity and DNR compliance, then apply §14.1 mechanically.

Outcomes:
- `NO_GO_KILL_ROUTING` — append DO_NOT_REBUILD / blocklist law and stop routing waves;
- `ACCRUE_OR_REGRADE_ONLY` — only the exact registered blind/power remedy is allowed;
- `LIMITED_DESCRIPTIVE` — no pooling/routing authority;
- `GO_W6_DISPLAY_TIER` — only after blind success.

This gate is Sol-owned and is not delegable to the same builder that produced W5Q.

### SI-W6A — Accepted-channel operationalization

**Dependency:** `GO_W6_DISPLAY_TIER` only.

Operationalize only channels actually licensed by W5: global cross-sectional map, behavioral neighbors, bounded EB residual. Print component N, neighbor eligibility, overlap exclusions, shrinkage weights, instability, and null separation. No ticker outcome argmax and no sector-keyed fallback.

### SI-W6B — Abstention + SIF v1

Build `sif.v1` with current PIT epoch, fingerprint ref, state, drift, neighbors, conditional expert-response profile by episode type/tier, uncertainty/coverage and explicit abstain reasons. SIF does **not** publish a live future episode anchor/type that is unknowable at decision time. All authority false.

### SI-W6C — Real read-only consumers

Add two real consumers through current owner seams, not new authority planes:

1. **Machine consumer:** an existing stock-intelligence/context path may ingest SIF only if it asserts `authority.* == false`, fails closed on missing/unknown authority, and a differential test proves Prophet score/rank/gate/size/trade outputs are byte/semantic unchanged.
2. **Operator/research consumer:** a current research/calibration surface displays security identity, epoch drift, estimability, expert-family evidence and abstention with source clocks. It may help inspection and research prioritization but must not imply validation or actionability.

Exact owning paths are chosen only after fresh owner/collision archaeology at this wave; this freeze does not pre-empt another product owner.

**Exit:** one real security can be followed end-to-end from source identity/fingerprint/epoch -> SIF -> machine read -> visible operator read, including sparse/changed-identity/abstain states.

### SI-W7A — Prospective shadow enrollment

**Dependency:** accepted W6 display-tier outputs. Reuse Evaluation OS/qledger and the existing Radar W5 durable event path. Do not read the public transport prefix as a new truth store and do not mint a Stock Identity event ledger.

Register frozen model/spec hashes, start a real forward evidence clock, ingest future `mastermind.entry_event.v1` observations and future episode maturities/corrections, keep first observation semantics, preserve family first-availability, and maintain separate retrospective vs prospective pools.

### SI-W7B — Prospective accrual and abstention proof

Run the frozen SIF/routing profile in shadow with no incumbent influence. Measure coverage, abstention frequency/reasons, epoch changes, family availability, calibration drift, localization outcomes when mature, and operator/machine consumption. No peeking through preregistered maturity/sample floors; insufficient maturity = `ACCRUING`.

### SI-W8 — Final research/product ruling

When the preregistered future-data floors mature, Sol reviews the frozen prospective evidence plus production/consumer proof and issues one of:

- `NO_GO_KILL_ROUTING` — routing claim killed; preserve descriptive identity/epoch context only, zero expert-routing authority.
- `GO_DESCRIPTIVE_CONTEXT` — Stock Identity/SIF remains useful read-only context but earns no ranking/gating authority.
- `GO_PROMOTION_CANDIDATE` — evidence is strong enough to commission a **separate** promotion charter. This is not promotion itself.

Any Prophet influence beyond zero-authority context requires a new preregistration that explicitly confronts `DNR:KILL-OUTCOME-AUDITION`, current Evaluation OS promotion law, forward sample maturity and all current Prophet owner gates. No authority cascades from W8 automatically.

## 7. Failure / correction semantics

Every wave must preserve these distinctions rather than coerce them into scores:

`MEASURED_ZERO`, `STRUCTURAL_ABSENCE`, `NO_COVERAGE`, `NOT_YET_AVAILABLE`, `STALE`, `SOURCE_FAILED`, `IDENTITY_UNRESOLVED`, `UNESTIMABLE`, `EPOCH_UNSTABLE`, `CENSORED`, `ABSTAIN`.

Corrections never rewrite old decisions invisibly. The historical as-known view and corrected/final view remain separately reproducible where source corrections or later epoch confirmation change interpretation.

## 8. Final acceptance criteria

The program is complete only when all applicable criteria below are true, or when a preregistered kill makes a downstream criterion explicitly inapplicable:

1. **Truth:** PIT instrument identity/ticker-reuse hygiene is reproducible; sealed partitions/constants remain intact; accepted price planes are adjusted/correction-safe; terminated-instrument survivorship is either honestly covered or confirmatory routing is blocked.
2. **Ruler:** localization metrics/composites/nulls/grain controls are executable, deterministic, preregistered and independent of expert outcomes.
3. **Estimability:** every fit output prints honest episode/calendar-cluster N and `UNESTIMABLE`/abstain reasons; no degenerate cluster count is presented as effective N.
4. **Epochs:** real identity epochs exist with `knowable_from`; Q1-Q3 use PIT epochs only; truncation tests prove no future relabeling leakage.
5. **Science:** W5 power gate and Q1-Q3 execute exactly once when eligible; the frozen §14.1 consequence matrix is applied without outcome shopping; a negative result creates a durable kill.
6. **Method-law compliance:** no per-name outcome argmax, ticker key, top-down grouping key or disguised equivalent exists anywhere in code/artifacts/reports.
7. **Abstention:** sparse, unstable, not-yet-available and underpowered states visibly abstain; consumers interpret abstain as no adjustment, never negative/veto.
8. **Consumers:** on the GO/display path, at least one real machine consumer and one visible research/operator consumer read SIF through existing owner seams; sparse/failure/correction states are proven; Prophet outputs remain unchanged unless a later promotion separately authorizes influence.
9. **Prospective evidence:** W7 starts a real forward clock on frozen definitions, consumes canonical Radar events, separates prospective from retrospective evidence, accrues without peeking and survives correction/restart/replay tests.
10. **Learning:** prospective coverage, abstention, mature localization outcomes and identity/epoch drift are instrumented so the company can tell whether the system improves research/discovery rather than merely producing artifacts.
11. **Production/research proof:** each merged implementation is `BUILT_NOT_PROVEN` until real data traverses the real owner path to its named machine/operator consumer. Green CI alone never closes a wave.
12. **Final ruling:** Agent OS contains an explicit `NO_GO_KILL_ROUTING`, `GO_DESCRIPTIVE_CONTEXT`, or `GO_PROMOTION_CANDIDATE` decision with exact evidence hashes/eras, unresolved risks and the next lawful action. No ambiguous “promising” state is allowed.

## 9. Execution ownership

One sustained Fable COO/principal-builder owns day-to-day recovery, bounded child-wave routing, collision management, exact-head implementation review, production/research proof capture, null/kill discipline and Agent OS updates inside this freeze. Sol retains thesis/architecture, scientific-law changes, W5R/W8 adjudication, any no-rebuild exception and every authority/promotion decision.

Fable persistence does not permit a mega-branch. Every child wave must claim a concrete current carrier before it becomes `in_progress`; Slack delivery alone is never a claim. While Autonomy V1 lacks a proven worker receiver, the durable program packet may exist as `UNCLAIMED`, but no execution state may be manufactured.
