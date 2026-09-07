# Market Ontology F12 — Public API v0 admission ruling (2026-09-06)

## 0. Scope and what this record does not do

This is a records-only ruling. It ships **no code, no routes, no DDL, no live surface, no template, no nav entry, no stylesheet**. It closes seven ledger rows (MO-PAID-055, MO-PAID-084, MO-PAID-056, MO-DELTA-036, MO-DELTA-037, MO-DELTA-038, MO-DELTA-039) with either a terminal refusal (gated on named reopen conditions), a frozen forward contract, or a split disposition. Nothing here is reachable as a product surface; it is reached the way every other Market Ontology record is reached — by path on `origin/main`.

## 1. Facts of record (with file:line)

| Capability | Existing owner (file:line) |
|---|---|
| Authentication / identity | `app/main.py:952` `require_user()` → delegates to `app.paywall._resolve_identity`; docstring: "No second auth cache is minted here — two divergent identity paths was the MMX-004 finding." |
| Entitlement / tier | `app/billing.py:643` `read_entitlement(user_id)`; consumed at `app/main.py:1021` (`/api/me`) and `app/main.py:1052` (`/api/account`) |
| Authenticated read surface that exists today | `app/main.py:1044` `GET /api/account` (tier, plan_label, status, features, current_period_end, prefs) |
| Metering an authenticated data egress | `engine/research_vault/download_quota.py:154` `check_and_increment(user_id, tier, root=None, now=None, lifetime=False) -> tuple[bool, dict]`; info = `{tier, remaining, limit, used, period, resets_at}`; docstring L20-32: entitlement fails CLOSED, counter fails OPEN but LOUD; `LIMITS` L41 `{free:0, essential:0, pro:10}` |
| Idempotency / event dedupe precedent | `app/billing.py:1448` (`GET stripe_events?id=eq.…`) and `app/billing.py:1456` (`POST stripe_events?on_conflict=id`) — inbound Stripe durable event-id ledger |
| DDL ledger (only place a key table could live) | `scripts/deploy/0004_analytics.sql` … `scripts/deploy/0008_trade_memory.sql` — hand-applied, highest number today is 0008; no `supabase/migrations/` or `db/migrations/` tree exists |
| Contract acceptance state | Wave-graph nodes: `ALPHA-K1 = READY_TO_COMMISSION`, `ALPHA-K2/K3 = TODO`, `ALPHA-K5 = TODO`; fresher ledger (2026-09-02): `MO-PAID-055.source_rights` = "K2-C/K3-D contracts explicitly NOT accepted", `MO-DELTA-036.source_rights` = "K1/K3/K5 contracts not accepted" |
| Scenario/portfolio computation owner | `agentos/workstreams/WS-MARKET-OS.md:142` `id: D1-D9` — "Portfolio Brief v3, Risk Packet, Holdings Map, visible risk sections, and scenarios", `status: todo`, `depends_on: [A2-A6, B1B-B6]` |
| Event/feed owner (earliest webhook substrate) | `WS-MARKET-OS.md` `id: E1-E3` — "My Market Overview, personalized change feed, alerts, and digest", `depends_on: [C1-C6, D1-D9]` |
| Rights rulings (named exclusions) | `MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md:115` R-1 Case-Shiller, `:124` R-2 Freddie PMMS, `:127` R-3 NAR, `:~131` R-4 card panels, `:95` BIS attribution-only (`config.yml:4082`) |
| Wire/transcript redistribution limits | `docs/QUAL_DATA_COMPLIANCE.md:23` (§1.2 — "redistribution limits honored (no raw-feed re-publication). Ticker-tagged headlines only"), `:81` (§2.4), `:133` (§4.5 — "Full-text bodies must not be re-published") |
| CRG R0 precedent | `MARKET_ONTOLOGY_F00C_CLOSURE_SUMMARY_2026-09-02.md:55` — "#6596 (CRG R0) landed zero runtime … its own DEC forbids becoming traffic middleman. All 13 F12 rows citing it keep their states; the F12 gap is real and untouched." |

## 2. (a) Is there a v0 public API at all

Answer: NO. No keyed public API is admitted in v0. `MO-PAID-055` closes REFUSED-IN-V0 with a named admission gate (G1-G4, see below) — a terminal refusal, not a re-deferral of the question. The refusal is scoped: it forbids a keyed, externally-authenticated, machine-readable surface projecting estate analytics. It does not touch the existing internal, session-authenticated routes (`/api/account`, `/api/me`, `/api/ask`, `/api/brain/*`, `/api/billing/*`), which continue unchanged.

Rationale: Three independent facts each individually block admission, and all three hold today. (1) There is no contract to sell: every analytic contract a public API would carry is unaccepted — K1/K3/K5 (`MO-DELTA-036.source_rights`), and K2-C/K3-D explicitly not accepted (`MO-PAID-055.source_rights`); wave-graph nodes `ALPHA-K1/K2/K3/K5` are `READY_TO_COMMISSION`/`TODO`. A public API is a versioned promise of stability; publishing an unaccepted contract converts an internal shape into a customer-visible commitment we cannot yet keep, and retracting it is one-way. (2) The safe egress class needs no key: the only payload with no third-party redistribution exposure is data the caller already owns and already sees — their account/entitlement and their own portfolio/watchlist — already served by the existing bearer-token spine (`app/main.py:952`, `:1044`). The keyed question therefore separates cleanly from the access question: nothing a user may safely fetch requires a key, so minting keys buys new secret-lifecycle risk with no capability the product lacks. (3) There is no consumer: `real_consumer` is `NONE` on all seven rows. Admitting a surface with zero named counterparties commits a later wave to permanent compatibility obligations for a user set of zero.

Rejected alternative: "Ship a narrow read-only v0 over already-owned self-data (account + own portfolio), keyed." Rejected because the key adds nothing: that payload is already authorized by `require_user`, so a key would be a second credential for the same principal on the same data — precisely the "two divergent identity paths" failure `app/main.py:952` names (MMX-004). The genuine want behind it is bulk self-export, which is `MO-PAID-086` (DEFER — needs a data-export product spec); solving it with an API key is scope-smuggling. A second rejected alternative, "defer again pending contract acceptance," is rejected explicitly: DEFER is what these rows have carried since 2026-09-02 and it produced no decision, only re-litigation. A refusal with an objective, owner-assigned reopen gate is terminal for wave B and binding on later waves; a DEFER is neither.

## 3. (b) Key issuance and revocation

Answer: No API keys are issued in v0. `MO-PAID-084` closes REFUSED-IN-V0, gated on MO-PAID-055 (it cannot precede the surface it authenticates). The ruling freezes the forward key contract now, so a later wave implements rather than redesigns. Principal: a key is an alternate credential for an existing Supabase principal, verified through the same plane `app/main.py:952` `require_user` already uses (`app.paywall._resolve_identity`). No second auth path, no second identity cache. Storage: only a salted hash of the key may be stored, and only in the existing Supabase project whose DDL ledger is `scripts/deploy/000N_*.sql`. No second secret store, no new vault, no env-file key registry, no KV. Entitlement: a key's rights are read from `app/billing.py:643` `read_entitlement` at request time — never copied onto the key row (entitlement drift is an F12 danger area). Scoping: keys are user-scoped until the tenancy migration (packet B-F12-1 / `WS:MARKET-OS A2-A6`) merges; on merge, scope becomes tenant-scoped through that owner, never a new tenant plane. This stands whether or not tenancy slips — macro's DDL ledger tops out at `0008`, so "tenancy 0014" is not present in this repo today. Revocation: a state flip on the existing row, effective on the next request, with no cached bypass; a revoked key returns the copy from the "Customer-facing copy" section, never a silent 200.

Rationale: freezing the key contract now — principal, storage, entitlement, scoping, revocation — lets a later wave implement directly against this record instead of re-deriving it, while keeping every piece projected over an existing owner rather than a new plane.

Rejected alternative: "Issue keys now so the surface can be built against them later." Rejected: an unused live credential is pure downside — a leak surface with no traffic to justify it — and the scope semantics (user vs tenant) are unresolved until tenancy lands, so keys minted now would need re-scoping, which is a migration on secrets.

## 4. (c) Idempotency-key semantics

Answer: `MO-DELTA-036` closes CONTRACT-FROZEN (not DEFER, not refused): v0 exposes no public write, so there is no v0 surface — but the semantics are fixed now and bind the first admitted public write. The contract projects over the existing dedupe owner, `app/billing.py:1448/1456` (`stripe_events`, `on_conflict=id`); no new webhook-retry DB, no second truth store.

Frozen semantics — "two identical Idempotency-Key requests produce one side effect": Key scope = `(principal, operation, Idempotency-Key)`. The same key from a different principal is a different key and never returns another principal's response (cross-tenant leakage is an F12 danger area). First writer wins, durably: the first request records the key with a hash of its request body in the same transaction as its side effect, using the existing unique-constraint/`on_conflict` pattern. Concurrency is resolved by the database constraint, never an in-process lock. Identical replay (same key, same body hash) performs no second side effect and returns the stored first response, byte-identical, with the same status. Conflicting replay (same key, different body hash) is a typed conflict state — never a silent second side effect, never a silent first-response echo. Retention is a fixed, published window; after expiry the key is unknown and a replay is a new request — disclosed in the developer copy, never left ambiguous (idempotency ambiguity is an F12 danger area). A missing Idempotency-Key on a write is rejected, never treated as "unique by default".

Rationale: the semantics mirror the existing durable dedupe owner rather than inventing a new one, and the fail-closed retention/conflict rules keep replay unambiguous for any future public write.

Rejected alternative: "File-backed idempotency ledger mirroring `download_quota`'s state files." Rejected: `download_quota` fails OPEN on ledger I/O error by design (docstring L20-32 — availability wins for a counter). Fail-open on an idempotency ledger converts an I/O blip into a duplicated customer-visible side effect. The two postures are opposite on purpose; the correct precedent is the transactional `stripe_events` pattern.

## 5. (d) schema_version and inference_metadata

Answer: YES, mandatory, frozen now. `MO-DELTA-037` closes CONTRACT-FROZEN. No external response may ever ship without both separation fields; the field law binds from the first admitted response. `schema_version` — an explicit version string on every external response envelope. Absent = non-conforming, must not ship. `inference_metadata` — an object separating what was measured from what was inferred, carrying at minimum: origin class (measured / derived / model-assisted), the as-of timestamp of the underlying observation, the identifiers of the sources it was computed from, and — when a value is absent — a plain-word `null_reason`. Nulls are printed, never hidden and never fabricated: an unavailable value is present as an explicit null with its `null_reason`, never omitted and never back-filled with a stale or estimated number. No LLM-originated signals: `inference_metadata` may only disclose how a value was produced. A model may never originate a score, rank, or escalation in any external payload (standing gate).

Rationale: unversioned or unlabeled responses are exactly how a compatibility break becomes a customer incident, and the separation of measured vs. inferred is the standing epistemics gate applied to an external surface.

Rejected alternative: "Add versioning later, at the first breaking change." Rejected: unversioned responses are what turn a compatibility break into a customer incident; the field costs nothing to reserve and cannot be added retroactively without breaking the clients it was meant to protect (schema compatibility is an F12 danger area).

## 6. (e) Webhooks

Answer: OUT. `MO-PAID-056` and `MO-DELTA-038` (the adjudicated single child) both close REFUSED-IN-V0, gated strictly after MO-PAID-055.

Rationale: Outbound delivery is not one capability but three durable state machines — signature/secret material, retry state, delivery dedupe. F12 do_not_redo forbids a webhook retry DB, a second job/event queue, and a second secret store by name, so all three would have to project over canonical owners — and no canonical outbound event/job transport owner exists to project over (`MO-PAID-056.current_owner` names one only in the abstract; the earliest real event producer is `WS:MARKET-OS E1-E3`, `status: todo`). Building the transport first would be the forbidden second plane. There is also no registered external URL to deliver to (`real_consumer: NONE`), and the only signature precedent in the estate is inbound (`app/billing.py:1448/1456`), which proves dedupe but not delivery.

Rejected alternative: "Ship signed outbound webhooks over a file-backed retry ledger reusing the `download_quota` state-dir pattern." Rejected on the same asymmetry as §4: `download_quota` fails open by design; a delivery ledger that fails open re-sends, and a duplicated webhook is a customer-visible side effect inside the customer's system, where we cannot repair it.

## Redistribution clause

**Being allowed to use data inside our product does not make us allowed to hand that data to someone else.** Our internal rights are rights *to compute and display*. They are not rights to redistribute. No public interface, now or later, may pass through a value we merely hold a display licence for. A source appears in a public response only when we hold written evidence that redistributing it is permitted; **if the evidence is missing, the source is excluded** — not investigated later, excluded now.

Named exclusions (binding on any future v1 payload), each with its basis:

| Excluded from any public response | Basis |
|---|---|
| S&P Dow Jones Case-Shiller as published via FRED (CSUSHPISA) | R-1, `MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md:115` — display/derived only, "no bulk redistribution of the underlying S&P DJI dataset" |
| Freddie Mac PMMS (MORTGAGE30US) via FRED | R-2, same doc `:124` — same posture as R-1 |
| NAR-derived series (any) | R-3, same doc `:127` — NAR terms bar storage in a retrieval system, so no NAR-derived value exists to expose; `DSC-NAR-TERMS-BAR-STORAGE-NOT-ONLY-REDISTRIBUTION` |
| BIS credit-gap / DSR strip | same doc `:95` — attribution-only licence (`config.yml:4082`); an interface response cannot carry the attribution the licence requires the way a page can |
| Wire-feed items from Benzinga / Tiingo / Marketaux / Finnhub / Alpha Vantage | `docs/QUAL_DATA_COMPLIANCE.md:23` — "no raw-feed re-publication", ticker-tagged headlines only, no article bodies |
| Earnings-call transcripts (FMP or equivalent) | `docs/QUAL_DATA_COMPLIANCE.md:133` — paid-subscription ToS, "Full-text bodies must not be re-published"; derived fields only, and only inside the product |
| Card / transaction panels | `docs/QUAL_DATA_COMPLIANCE.md` §2.3 (affirmed binding by R-4) — excluded as deliberate policy, typed ABSENT |
| Any Market Ontology proprietary code, text, data, or asset | standing charter gate |

Positive rule: a future public payload may carry only values the estate itself computes from public inputs, carrying attribution where a licence requires it, never a verbatim or bulk reproduction of a licensed upstream series.

Answer: (f) YES — v0 (and every later version) carries a binding redistribution clause. Internal rights to compute and display a source are not, and never become, rights to hand that source to a third party through a public interface. The clause above is the standing rule; the table names every source it currently excludes and why.

Rationale: The estate's contracts with FRED-published, NAR-derived, BIS, and wire/transcript providers were negotiated for display inside this product, not for redistribution through a second interface we would control — `MARKET_ONTOLOGY_F01_R5R6_SOURCE_CENSUS_AND_RIGHTS_RULINGS_2026-09-04.md` records each licence's actual scope (R-1..R-4), and none of them grants bulk or verbatim re-publication. Treating a display licence as a redistribution licence would expose the company to a contract breach the moment a single public response carried one of those values, and that exposure would be invisible until an actual complaint — so the rule is fail-closed by source rather than reviewed per endpoint: a source with no affirmative redistribution evidence is excluded now, not flagged for later review. This also answers who bears the burden: the burden is on the evidence existing, not on a complaint arriving.

Rejected alternative: "Ship without a named exclusions table and rely on field-level legal review at endpoint-design time, whenever v1 is specified." Rejected because it converts a source-rights question this record can answer today (R-1..R-4 and `QUAL_DATA_COMPLIANCE.md` already state each provider's terms) into a recurring judgment call made by whichever future session designs the endpoint — the same re-litigation pattern this record exists to close for the other six questions. A second rejected alternative, "infer redistribution rights from the fact that display rights were granted," is rejected outright: it is the exact authority hop this clause exists to forbid, named explicitly in the Admission gate and the DEC do_not_redo list.

## 7. (g) MO-DELTA-039 disposition

Answer: SPLIT. Confirm one half, reclaim the other. This is the packet's one substantive correction and the reviewer should check it first. Computation half — CONFIRMED absorbed by `WS:MARKET-OS D1-D9`. D1-D9 is "Portfolio Brief v3, Risk Packet, Holdings Map, visible risk sections, and scenarios" (`WS-MARKET-OS.md:142`), which is exactly the analyze/impact/scenario computation D039 projects over. Public-exposure half — RECLAIMED by F12 and REFUSED under the same gate as MO-PAID-055. D1-D9 owns product scenario surfaces; it does not own, and has never been granted, public exposure. Left as a bare "ABSORBED-BY", the row lets a later D-wave session ship a public scenario endpoint as a D1-D9 sub-item while F12 has refused exactly that — an authority hop through an absorption note. The split closes it.

Rationale: see Answer above — computation ownership and public-exposure authority are two different grants, and only the first was ever made.

Rejected alternative: "Confirm absorption wholesale and drop the row from F12." Rejected for the hop above: absorption of a computation must never silently transfer exposure authority.

## Forbidden second planes and the owner each capability projects over

| Forbidden by name (F12 do_not_redo, charter 9.2) | The existing owner a v0/v1 capability projects over instead |
|---|---|
| second auth plane / second identity cache | `app/main.py:952` `require_user` → `app.paywall._resolve_identity` (MMX-004: two divergent identity paths) |
| second tenant plane | the tenancy migration owned by packet B-F12-1 / `WS:MARKET-OS A2-A6`; user-scoped until it merges |
| second job queue | none exists to project over → no capability requiring one is admitted |
| second event queue | none exists; earliest real event producer is `WS:MARKET-OS E1-E3` (`status: todo`) |
| second API truth store | `app/billing.py:643` `read_entitlement` for rights; the existing Supabase project for state |
| webhook retry DB | none exists → webhooks refused in v0 (§6) |
| second secret store | the existing Supabase project only, DDL ledger `scripts/deploy/000N_*.sql` (highest today: `0008`) |
| collaboration state plane | out of scope for this ruling entirely |
| public redistribution rights inferred from internal data rights | forbidden outright — see Redistribution clause |
| metering, when admitted | `engine/research_vault/download_quota.py:154` `check_and_increment` — entitlement fails CLOSED, counter fails OPEN and loud (docstring L20-32); reuse this precedent, do not mint a second meter |

## Customer-facing copy (frozen)

| Situation | EN | ZH |
|---|---|---|
| Developer/API page, today | We don't offer a public interface yet. When we do, you'll be able to create and turn off your own keys from your account page. | 我们目前还没有对外开放的接口。开放之后，你可以在账户页面自行创建和停用密钥。 |
| Key not valid | This key isn't valid. Create a new one on your account page. | 该密钥无效。请在账户页面创建一个新的密钥。 |
| Key turned off | This key was turned off. Create a new one on your account page. | 该密钥已停用。请在账户页面创建新的密钥。 |
| Plan doesn't cover it | Your plan doesn't include this data. See plans to upgrade. | 你的方案不包含这项数据。查看方案以升级。 |
| Allowance used up | You've used today's requests. Your allowance resets at midnight UTC. | 你已用完今天的请求次数。额度将在世界时零点重置。 |
| A value is missing | Not available yet — we don't have this figure for this date. | 暂无数据 — 这个日期的数字我们还没有。 |
| A figure can't be sent through the interface | Some figures we show on the site can't be sent through the interface, because the provider's terms don't allow it. | 站内显示的部分数字无法通过接口提供，因为数据提供方的条款不允许。 |
| Repeat request already handled | We already handled this request. Here's the same answer we gave the first time — nothing was done twice. | 这个请求我们已经处理过了。这里返回的是第一次的相同结果 — 没有重复执行。 |

## Admission gate G1-G4

All four must hold; any one unmet keeps the refusal.

- G1 — Contract. `ALPHA-K1` (EvidenceRef / EvidenceBlock / EvidenceRecipe) accepted in a recorded DEC, and at least one of `ALPHA-K3` / `ALPHA-K5` accepted. `K2-C` and `K3-D` remain excluded until separately accepted. Today: 2026-09-02 ledger records K1/K3/K5 not accepted; wave graph 2026-08-23 has K1 `READY_TO_COMMISSION`, K3/K5 `TODO`.
- G2 — Scope owner. The tenancy migration (B-F12-1 / `WS:MARKET-OS A2-A6`) merged and applied, so a key row has a lawful owner scope. Until then keys would be user-scoped only.
- G3 — Rights. A per-source redistribution evidence sheet covering every field in the proposed payload. Fail closed: a field whose source carries no affirmative redistribution evidence is excluded, and the named exclusions above are never eligible.
- G4 — Consumer. At least one named external consumer recorded in a commission. Today: `real_consumer: NONE` on all seven rows.

Standing prohibition: until G1-G4 all hold, no session in any lane may propose, spec, or ship a public/keyed endpoint, an outbound webhook, or an API key — including as a sub-item of `WS:MARKET-OS D1-D9` or `E1-E3`.

## Ledger dispositions

| id | new `next_bounded_child` | new `adjudication_notes` |
|---|---|---|
| MO-PAID-055 | REFUSED IN V0 — no keyed public API admitted; reopens only when admission gate G1-G4 all hold | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · terminal refusal, not a deferral · gate G1 contract + G2 tenancy scope + G3 per-source rights + G4 named consumer · admissible no earlier than wave MARKET-OS-C |
| MO-PAID-084 | REFUSED IN V0 — no keys issued; forward contract frozen (Supabase principal, hashed secret in the existing project, entitlement read live, user-scoped until tenancy) | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · gated on MO-PAID-055; no second secret store, no second auth plane (app/main.py:952) · admissible no earlier than wave MARKET-OS-C, and not before MO-PAID-055 |
| MO-PAID-056 | REFUSED IN V0 — outbound webhooks out of scope; no canonical event/job transport owner exists to project over | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · retry/dedupe/secret state would be the forbidden second plane (F12 9.2) · admissible no earlier than wave MARKET-OS-E, and not before MO-PAID-055 |
| MO-DELTA-038 | REFUSED IN V0 with MO-PAID-056 (single adjudicated child) — signature/retry/dedupe stay folded and stay refused | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · fold with MO-PAID-056 preserved · admissible no earlier than wave MARKET-OS-E, and not before MO-PAID-055 |
| MO-DELTA-036 | CONTRACT FROZEN — no v0 surface; semantics bind the first admitted public write, projected over the existing stripe_events dedupe pattern | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · scope (principal, operation, key); first-writer-wins in the same transaction; identical replay returns the stored first response; different body under the same key is a typed conflict; no new webhook-retry DB (app/billing.py:1448/1456) · admissible with MO-PAID-055, wave MARKET-OS-C |
| MO-DELTA-037 | CONTRACT FROZEN — schema_version and inference_metadata are mandatory on every external response from the first one | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · nulls printed with a plain-word reason, never omitted, never fabricated; no model-originated scores · admissible with MO-PAID-055, wave MARKET-OS-C |
| MO-DELTA-039 | SPLIT — computation half CONFIRMED absorbed by WS:MARKET-OS D1-D9; public-exposure half RECLAIMED by F12 and refused under the MO-PAID-055 gate | DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06 · absorption of a computation never transfers public-exposure authority · computation wave MARKET-OS-D (WS-MARKET-OS.md:142); public exposure not before MO-PAID-055 |

## Record: DEC:F12-PUBLIC-API-V0-ADMISSION-2026-09-06

See `agentos/decisions/DEC-F12-PUBLIC-API-V0-ADMISSION-2026-09-06.md` for the durable decision record (question, answer, rationale, alternatives rejected, evidence, affects, confidence, reversibility).
