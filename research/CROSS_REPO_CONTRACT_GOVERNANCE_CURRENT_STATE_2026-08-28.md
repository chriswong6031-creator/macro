# Cross-Repository Contract Governance — Current-State Census — 2026-08-28

## Scope and authority

This is the R0 current-state reconciliation for the existing semantic program `cross-repo-contract-governance`.

It updates the historical `research/CROSS_REPO_CONTRACT_BOUNDARY_AUDIT_2026-08-11.md` against current repository truth. The historical audit remains evidence and must not be rewritten to pretend it was current.

Current pins at R0 branch creation:

| Repository | Default branch | Audited head |
|---|---|---|
| Macro | `main` | `24ccea3fe482ab97c415db387f272b34c4852ed3` |
| Mastermind Terminal | `master` | `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea` |
| Mastermind Portfolio | `master` | `97f85ce5b84030faf4d291f988a1c642fb15e80a` |

Protected Sol Skillpack was loaded from Portfolio `master@97f85ce5b84030faf4d291f988a1c642fb15e80a`, `mastermind.sol_skillpack.v1` / `1.0.0` / bootstrap major `1`.

The company status vocabulary is used exactly: `PROVEN_LIVE`, `BUILT_NOT_PROVEN`, `PARTIAL`, `DARK_OR_DISCONNECTED`, `BROKEN`, `SPEC_ONLY`, `NOT_BUILT`, `REJECTED_BY_DESIGN`.

No `PROVEN_LIVE` claim below is inferred merely from merge/CI. Where this census did not obtain a current exact production receipt, the state remains below `PROVEN_LIVE`.

## Executive corrections to the 2026-08-11 audit

### Correction A — Portfolio Prophet is not absent

Current Portfolio contains `portfolio/prophet_feed.py`, which reads Macro's `vendor/macro/site/prophet/index.json` under schema `prophet.index/v1` and is consumed by current Portfolio intake/conviction paths.

The defect is formal contract registration, imported-state identity, authority declaration and current production attestation — not absence of an adapter.

**Current state: `BUILT_NOT_PROVEN`.**

### Correction B — authoritative `/api/pfolio/*` fail-open code was repaired

The current Portfolio `app/auth.py` documents and implements the authoritative-VPS fail-closed bearer boundary: all `/api/pfolio/*` methods require the operator bearer on the authoritative public VPS, missing bearer configuration blocks the surface, and authoritative startup refuses unsafe configuration.

This current code truth supersedes the old audit's source-code finding. This census did not independently exercise the present production origin with a real authorized/unauthorized request pair.

**Current state: `BUILT_NOT_PROVEN`.**

## Complete major seam ledger

### CRG-L01 — Macro per-name intelligence -> Terminal

**Producer:** Macro per-name stockdata and associated producer artifacts.  
**Canonical owner:** Macro for upstream intelligence meaning.  
**Consumer:** Terminal `ingest/pull_macro_intel.py` -> `terminal/public/data/<SYM>.intel.json` -> Terminal research/copilot/UI consumers.  
**Schema/version:** consumer output `intel/v1`; producer inputs include stockdata plus factordata blocks.  
**Source clock:** producer `asof` plus sub-block clocks; Terminal derives stale under its current configured ruler.  
**Null behavior:** absent optional source blocks are omitted, not fabricated.  
**Correction behavior:** latest snapshot is replaced by later producer truth; current bridge does not expose a unified correction generation.  
**Auth/privacy:** some factordata inputs are paid/internal and are resolved local-first; the public output is a trimmed Terminal projection.  
**Authority transfer:** Macro intelligence meaning remains upstream; Terminal owns the consumer transform/presentation.  
**Fallback:** R2/network failures preserve last-good local data.  
**Deployment proof:** implementation and nightly wiring exist; this census has no exact-current producer->import->actual-consumer production receipt.  
**Actual consumer:** Terminal UI/research assistant paths.  
**State:** `PARTIAL`.

Gap: the live wire contract is defined mostly inside ingest code/tests rather than one formal producer-owned versioned contract + consumer conformance fixture package; last-good bytes can remain readable after a failed current refresh without one canonical import receipt making that obvious.

### CRG-L02 — Macro market risk -> Terminal

**Producer:** Macro `risk_state.v1` / `market_state.v1`.  
**Owner:** Macro for source risk/context semantics.  
**Consumer:** Terminal `ingest/pull_macro_risk.py` -> `market_risk/v1` -> market-risk presentation.  
**Schema/version:** source variant `risk_state.v1` or `market_state.v1`; Terminal output `market_risk/v1`.  
**Source clock:** `nightly_asof` or `asof`.  
**Null behavior:** richer component fields are absent when the web-served source variant cannot provide them.  
**Correction:** later source replaces the current snapshot; no common cross-repo correction receipt.  
**Auth/privacy:** display/context projection.  
**Authority:** output declares display-only; no sell authority should transfer.  
**Fallback:** failed fetch/local read leaves existing output intact.  
**Proof:** implementation exists; no fresh exact-head production import/consumer receipt in this census.  
**Actual consumer:** Terminal risk chip/context surfaces.  
**State:** `PARTIAL`.

### CRG-L03 — Macro basket washout -> Terminal fenced admission

**Producer:** Macro `basket_washout_state.v1`.  
**Owner:** Macro owns washout evidence/state.  
**Consumer:** Terminal `ingest/pull_macro_washout.py` -> `washout_state/v1` -> `signal_layer.washout_override` and the fenced signal/admission path.  
**Source clock:** Macro `as_of`, converted to Terminal stale sessions.  
**Null behavior:** no source leaves existing output intact; absent/nonqualifying name means no qualifying override.  
**Correction:** later producer state replaces the current bridge snapshot.  
**Auth/privacy:** public/served trimmed cohort state.  
**Authority:** **contract contradiction** — bridge prose/flag says display-only, while a real Terminal deterministic admission consumer exists. The correct authority statement is Macro evidence ownership + explicit Terminal-owned fenced consequence, with no broader rank/size/trade transfer.  
**Fallback:** last-good output may remain.  
**Proof:** implementation/tests exist; authority boundary itself is wrong.  
**Actual consumer:** Terminal signal/admission machinery, not merely display.  
**State:** `BROKEN`.

### CRG-L04 — Macro opportunity timeline -> Terminal

**Producer:** Macro opportunity timeline builder/publication.  
**Owner:** Macro for opportunity event meaning.  
**Consumer:** Terminal opportunity importer and related user surfaces.  
**Schema/version:** `opportunity_timeline.v1`.  
**Source clock:** producer as-of/publication cadence.  
**Null behavior:** omitted symbols differ from explicit empty arrays under the existing importer semantics.  
**Correction:** later timeline publication supersedes earlier current state while receipts remain separate from verdict semantics.  
**Auth/privacy:** evidence/context path.  
**Authority:** no implicit trade authority.  
**Fallback:** producer and consumer are both capable of keeping last-complete data while a current attempt fails.  
**Proof:** merge/unit behavior exists; no current exact-head cadence/import/actual-consumer proof obtained here.  
**State:** `PARTIAL`.

### CRG-L05 — Macro options/Prophet routes -> Terminal

**Producer:** Macro options/Prophet API and R2/publication surfaces.  
**Owner:** Macro for upstream options/Prophet semantics and private Issue Desk authority.  
**Consumer:** Terminal endpoint maps/BFF/flow surfaces.  
**Schema/version:** multiple current route/artifact contracts.  
**Source clock:** route/artifact-specific.  
**Null/correction/fallback:** independently implemented per route.  
**Auth/privacy:** private review/write surfaces must remain API/authorized; public evidence stays read-only.  
**Authority:** Terminal presentation/consumer logic does not acquire upstream private review authority.  
**Proof:** functional current integrations exist; route/schema/freshness ownership is duplicated in hand-maintained maps.  
**Actual consumer:** Terminal options/flow product.  
**State:** `PARTIAL`.

### CRG-L06 — Macro billing/entitlements -> Terminal

**Producer/authority:** Macro canonical billing and entitlement state.  
**Consumer:** Terminal same-origin BFF/store/gates/settings.  
**Schema:** account/plan/status response contract.  
**Source clock:** verification/refresh time rather than a market clock.  
**Null behavior:** Terminal now distinguishes unverified/unavailable from verified free.  
**Correction:** account changes invalidate/reverify rather than trusting a life-of-shell cached answer.  
**Auth/privacy:** Supabase/session -> canonical Macro entitlement; Terminal never owns billing truth.  
**Authority:** Terminal gate fails closed on unverified entitlement; stale same-owner state may be displayable without newly granting capability.  
**Fallback:** same-owner stale-last-good can support honest display while gate remains conservative.  
**Proof:** recent consumer hardening exists; no current exact-head real account outage/upgrade production dossier obtained in this census.  
**State:** `BUILT_NOT_PROVEN` for the current strengthened contract boundary.

### CRG-L07 — Macro imported code/state -> Portfolio

**Producer:** Macro `main` + Macro published artifacts.  
**Owner:** Macro for imported modules/artifacts.  
**Consumer:** Portfolio `data_layer/macro_refresh.py`, `vendor/macro` / `vendor/macro_src`, `brain/`, `portfolio/`, and related readers.  
**Schema/version:** many artifact-specific schemas; imported Python modules additionally couple to a repository revision.  
**Source clock:** artifact-native clocks plus Git revision.  
**Null behavior:** individual readers fail soft/freeze/advisory under their own rules.  
**Correction:** managed checkout can advance to newer `origin/main`; no one imported-generation identity currently binds all reads in a Portfolio run.  
**Auth/privacy:** production symlink/local checkout and optional remote identity; credentials stay server-side.  
**Authority:** importability does not transfer market/portfolio authority.  
**Fallback:** last-good checkout/artifacts can remain.  
**Proof:** real machinery exists.  
**Critical gap:** current Portfolio decisions/runs are not universally attributable to one exact resolved Macro revision/generation + contract generation + correction identity.  
**State:** `PARTIAL`.

### CRG-L08 — Macro Prophet -> Portfolio

**Producer:** Macro Prophet `site/prophet/index.json`.  
**Owner:** Macro Prophet.  
**Consumer:** Portfolio `portfolio/prophet_feed.py`, then Portfolio intake/conviction flow.  
**Schema/version:** `prophet.index/v1`.  
**Source clock:** top-level `asof` plus `_signal_date`/plan geometry clocks.  
**Null behavior:** absent/malformed/stale feed becomes inert; no plan means no fabricated geometry.  
**Correction:** process cache reloads when the artifact changes; later producer artifact becomes current.  
**Auth/privacy:** vendored/read-only context.  
**Authority:** current adapter describes Prophet as additive candidate source + plan geometry, not direct sizing/trade authority; downstream gate still owns decisions.  
**Fallback:** fail-open/inert on feed absence rather than manufacturing a veto or buy.  
**Proof:** current adapter and real consumers exist. Portfolio `config/contracts.yml` remains an old consumer registry that does not formally register this live adapter; no current production dossier is present.  
**State:** `BUILT_NOT_PROVEN`.

### CRG-L09 — Macro Neural Web -> Portfolio

**Producer:** Macro `engine/neuralweb/mastermind_context.py` -> `neural_web_mastermind_context.v1`.  
**Owner:** Macro Neural Web for context publication.  
**Consumer:** Portfolio `brain/neural_web_context.py`, then prompt/decision consumers.  
**Schema/version:** `neural_web_mastermind_context.v1`.  
**Source clock:** top-level/lobe as-of and freshness.  
**Null behavior:** absent/malformed/stale source should be inert.  
**Correction:** later producer artifact replaces current context; lobe freshness is evaluated independently.  
**Auth/privacy:** vendored context artifact.  
**Producer authority:** current Macro source states all five authority booleans FALSE and every field context-only.  
**Consumer conflict:** Portfolio source contains default-ON prompt context behavior and a default decision mode of `shrink`, while `config/authority_map.yml` describes `MASTERMIND_NW_DECISION` as dark/default-off and future arming gated.  
**Fallback:** current consumer can become inert for stale/malformed context, but defaults can exceed the producer/governance contract before that point.  
**Proof:** the contradiction is visible on current code; no data accident may be treated as an authority guarantee.  
**State:** `BROKEN`.

### CRG-L10 — Portfolio public snapshot -> Macro

**Producer:** Portfolio `bridge/macro_snapshot.py`.  
**Owner:** Portfolio for paper-book source truth and public-safe projection; Macro for its public rendering consumer.  
**Consumer:** Macro public Mastermind page.  
**Schema/version:** `mastermind_snapshot.v1`.  
**Source clock:** top-level `generated_at`, per-book `as_of`.  
**Null behavior:** missing/unreadable individual book is omitted; performance errors fail soft.  
**Correction:** later build replaces the public snapshot.  
**Auth/privacy:** explicit public key whitelists exist for positions/pending orders and intended public-safe payload.  
**Authority:** paper/display accountability only, not broker/trade authority.  
**Fallback:** publication failure leaves the previous Macro file readable.  
**Ownership defect:** current publication code resolves the Macro working tree and commits/rebases/pushes Macro `main` from Portfolio.  
**Proof:** payload builder exists; publication ownership is not acceptable as the long-run contract boundary.  
**State:** `PARTIAL` payload / `BROKEN` publication ownership.

### CRG-L11 — Portfolio Neural Web feedback -> Macro -> Portfolio acknowledgement

**Producer:** Portfolio `bridge/nw_feedback.py`.  
**Owner:** Portfolio for bounded governance feedback; Macro Neural Web for its derived summary/context consumer.  
**Consumer:** Macro Neural Web, then bounded Portfolio reflection/ack path.  
**Schema/version:** `mastermind_nw_feedback.v3` plus Macro derived feedback summary contract.  
**Source clock:** rolling event windows + publication generation.  
**Null behavior:** missing/corrupt ledgers yield bounded absent/zero/empty states depending on block; builder is fail-soft.  
**Correction:** later public feedback replaces current snapshot.  
**Auth/privacy:** explicitly public; source code bans dollar values, sizes, secrets, tickers/IDs/raw ledger prose and caps/sanitizes bounded text.  
**Authority:** governance feedback/context, no autonomous portfolio/trading authority.  
**Fallback:** build/push failures can leave old feedback in place.  
**Proof:** strong payload/privacy contract exists; it still rides the broken direct-Macro-working-tree publication mechanism.  
**State:** `PARTIAL`.

### CRG-L12 — Portfolio operational key/cost exports -> Macro

**Producer:** Portfolio operational ledgers/state.  
**Owner:** Portfolio for source operational state; Macro for its admin/read consumer.  
**Consumer:** Macro `data/mastermind/{cost_summary.json,key_events.jsonl,key_pool_status.json}` readers.  
**Schema/version:** mixed; `key_pool_status` has an explicit schema, `key_events` is currently a filtered ledger copy rather than a closed projection contract.  
**Source clock:** source event `ts`, current pool generation, rolling 14-day export window.  
**Null behavior:** missing/empty source skips export; failures are non-fatal.  
**Correction:** later export replaces current derived state; event file is regenerated from the retained window.  
**Auth/privacy:** `data/` not being HTTP-served does not make it private if committed to a public repository.  
**Authority:** operational/admin visibility only.  
**Fallback:** old committed bytes remain when export/push fails.  
**Critical defects:** Portfolio directly stages/commits/pushes Macro `main`; `key_events.jsonl` lacks a closed field/value whitelist and currently keeps whole accepted source lines after time filtering.  
**State:** `BROKEN`.

### CRG-L13 — direct Terminal -> Portfolio

**Producer/consumer:** none required by current architecture.  
**Current proof:** no current direct API/import/schema contract is needed to establish the existing products; Terminal Conviction Book, Macro descriptive portfolio context, and Mastermind paper books are distinct.  
**Authority:** no direct transfer exists.  
**State:** `REJECTED_BY_DESIGN` under the 2026-08-28 architecture freeze.

A future direct seam requires a concrete user/machine job, current archaeology, no-duplicate-system proof and a new Sol ruling. The absence of a direct bridge is not itself a defect.

### CRG-L14 — Portfolio authoritative `/api/pfolio/*` operator boundary

**Producer/owner:** Portfolio internal Supabase-backed operator surface.  
**Consumer:** authorized operator/programmatic client.  
**Schema:** route-specific API contract.  
**Clock:** request-time authorization.  
**Null behavior:** no bearer on authoritative instance is a refusal/misconfiguration, not anonymous access.  
**Correction:** credential configuration changes take effect through existing service configuration/restart law.  
**Auth/privacy:** separate operator bearer plane; do not merge it into Macro/Terminal subscriber entitlement.  
**Authority:** bearer authorizes the operator surface only.  
**Fallback:** local non-authoritative development remains separately defined.  
**Proof:** current source hardens the boundary and startup; present production request proof was not independently collected here.  
**State:** `BUILT_NOT_PROVEN`.

## Current priority seam ledger

| ID | Seam | State | Priority | Why now |
|---|---|---:|---:|---|
| CRG-01 | Neural Web authority -> Portfolio | `BROKEN` | P0 | Consumer defaults can exceed producer/governance authority. |
| CRG-02 | Macro imported-state identity -> Portfolio | `PARTIAL` | P0 | Portfolio decisions cannot always be traced to one exact imported Macro generation. |
| CRG-03 | Portfolio -> Macro publication ownership | `BROKEN` | P0 | Producer currently impersonates consumer repo working tree and writes Macro `main`. |
| CRG-04 | Prophet -> Portfolio formal contract/proof | `BUILT_NOT_PROVEN` | P1 | Real adapter exists; governance registry and production dossier lag reality. |
| CRG-05 | washout -> Terminal admission authority | `BROKEN` | P1 | Real decision-bearing consumer contradicts display-only transport language. |
| CRG-06 | Terminal import receipts/formal schemas | `PARTIAL` | P1 | Last-good behavior can conceal stopped current publication/import. |
| CRG-07 | shared tier/route fixtures | `PARTIAL` | P2 | Multiple implementations can drift without producer-owned conformance vectors. |
| CRG-08 | reverse snapshot/feedback correction proof | `PARTIAL` | P2 | Product contracts need real success/failure/correction proof after ownership repair. |

## No-rebuild ruling

Cross-Repository Contract Governance is not a runtime component. It must not become:

- a service or gateway in the data path;
- a release/merge gate;
- a lifecycle database;
- a contract-status queue;
- a scheduler/retry/watcher system;
- a second semantic registry;
- a second artifact registry that competes with producer contracts/Synapse;
- a second auth/identity/publication/evidence/correction plane.

The target relationship is always:

`producer owner -> versioned meaning -> existing transport -> consumer conformance -> import/publication receipt -> real consumer`.

## Collision state at R0 start

- no existing Agent OS `WS:CROSS-REPO-CONTRACT-GOVERNANCE` record was found;
- no open Macro PR titled/matching Cross-Repository Contract Governance was found before R0 branch creation;
- no existing `cross-repo` / `contract-governance` Macro branch was found;
- current Portfolio movement since the prior census is concentrated in Executive/Slack/operating-surface work and did not modify the critical Portfolio seam files identified above;
- Terminal head is unchanged from the prior census pin;
- Macro has moved heavily in unrelated programs and therefore every child must still re-run a fresh path/owner/open-PR collision census before writing.

## Exact closure order

1. R0 durable home / no-runtime architecture / census / principal commission.
2. CRG-NW-AUTHORITY-V1.
3. CRG-MACRO-IMPORT-IDENTITY-V1.
4. CRG-PORTFOLIO-PUBLICATION-V1, beginning with architecture/first owned vertical rather than a transport mega-migration.
5. CRG-PROPHET-PORTFOLIO-V1.
6. CRG-TERMINAL-WASHOUT-AUTHORITY-V1.
7. Remaining Terminal formal-contract/import-receipt verticals.
8. Shared generated semantic fixtures/route descriptors.
9. Reverse publication stale/correction/privacy production dossiers.
10. Semantic registry/system-map and Agent OS closeout.

## Production proof law

Every eventual `PROVEN_LIVE` seam must preserve a receipt containing at minimum:

- exact producer revision/object generation;
- schema/version/compatibility identity;
- producer/source clock;
- publication/import attempt and result;
- exact consumer revision/release;
- imported/publication time;
- null/stale/error state;
- correction/replay identity when applicable;
- actual product/machine consumer;
- authority consequence;
- auth/privacy result.

The receipt must exercise the real path. CI, fixtures, PR merge, Linear status, Slack delivery and Executive `QUEUED` admission are distinct and insufficient substitutes.

## R0 capability truth

R0 itself is `SPEC_ONLY` until its records/research carrier merges. Even after merge R0 changes organizational recoverability only. It does not fix a seam or prove Fable execution.

The post-R0 dependency is one **actual claimed** Fable principal carrier. The organizational packet may exist before that claim; it must remain explicit that `UNCLAIMED != executing`.