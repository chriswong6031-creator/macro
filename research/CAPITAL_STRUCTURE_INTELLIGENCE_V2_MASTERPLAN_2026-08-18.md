# Capital Structure Intelligence V2 — Masterplan and architecture freeze

Date: 2026-08-18
Status: architecture freeze pending Sol/Chairman acceptance of the **Sol AMEND**. **No implementation wave is authorized by this document.**
Repository: `mastermindx-market-intelligence/macro`
Program: `capital-structure-intelligence` (`authority_class: context_only`)
Executor: Cursor Grok 4.6 (this research PR and AMEND)
Owner seat: COO Fable (program owner, not the proposer of these rulings)
Acceptance: Sol / Chairman
Workstream: `WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2`

This document is the canonical V2 program of record. It recovers the original product thesis, reconciles it against current `origin/main`, audits the live estate, updates competitor and primary-source regulatory research, and freezes the ordered waves. It does not ship product code. Sol reviewed PR #5901 as **AMEND** (2026-08-18): product thesis accepted; W1 identity and publication hardened below. Do not reopen the accepted architecture listed in §17.

---

## 0. Recovered Chairman intent

The destination is a **time-indexed digital twin of each issuer's capital position** — financing pathways, dilution stack, funding need, and capital constraints — reconstructable as known to Mastermind at any requested historical instant.

It must answer, in this order:

1. What can this issuer issue **now**?
2. What does it need to fund, and by when?
3. What supply can realistically hit shareholders under defined price and document triggers?
4. What changed, and what activates or retires each path?
5. What does that imply for the investment, the company's catalysts, Neural Web, and — only after a separate promotion gauntlet — Prophet?

It is **not**:

- an SEC filing browser;
- another opaque dilution score;
- a screenshot clone of DilutionTracker or Dilutracker;
- a BioCatalyst-specific capital ledger;
- a Prophet-authoritative capital score.

The original 2026-08-01 docket already named this: a temporal accounting system that joins filings, amendments, effectiveness notices, pricing documents, later usage, cash, corporate actions, and market data **without confusing authorization with issuance**. PR #5792 recovered ingestion. Ingestion recovery is not product recovery. The original program stopped after observed filing-state projection.

---

## 1. Authority and precedence

When documents disagree, use this order and never mint a second truth plane:

1. Current production behavior and current `origin/main`.
2. Current house laws, ownership registries, and canonical contracts.
3. `docs/CAPITAL_STRUCTURE_INTELLIGENCE_CONTRACT.md`.
4. `research/CAPITAL_STRUCTURE_ISSUER_STATE_W3_BUILD_DOCKET.md`.
5. `research/CAPITAL_STRUCTURE_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md` for original intent.
6. PR #5792 and its production evidence for ingestion recovery.
7. This V2 handoff for the architectural objective.

Standing laws that bind this freeze:

- `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` — a run clock must not enter the identity of immutable content evidence.
- `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE` — overlapping jobs withhold a whole artifact family when a push would drop `origin/main` evidence; do not file-merge a hash-bound generation.
- `DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE` — this program does not rewrite global `daily.yml` concurrency.
- `DEC:AGENTOS-HOME-IS-MACRO` — Agent OS records live here; no second store.
- Contract: `capital_structure.event.v1` remains the temporary canonical event adapter. Do not silently claim `company_event.v1` (review_by 2026-10-01).
- BioCatalyst PIT seam: `engine.capital_structure.biocatalyst_pit_adapter` is a private reader of the CS owner, not a second ledger.
- `prophet_authority=false` through the deterministic product build.

---

## 2. Current-main impact audit

### 2.1 SHAs

| Label | SHA | Role |
|---|---|---|
| Sol audit (reference only) | `a49e448d024f641d48ebc3fa9c54bdcc4ddbd76a` | Baseline Sol named. Not frozen. |
| Worktree create | `e43ecd49b273` | `data: nightly timings oracle_offrender 2026-08-18` |
| Mid-session main | `791148b2b7d525917130489322c0a434c091d69d` | First CS-path impact check (empty). |
| Original freeze SHA (PR #5901 first head base) | `ec62e4981c10d1ce7d6379cb9475747d49f790f1` | First W0 freeze. Superseded as PR base by the AMEND rebase. |
| Sol AMEND reference | `71fbb0c68b63322d97c30aac0776ab7c83205642` | SHA Sol named at review. |
| **AMEND rebase SHA (current origin/main)** | **`ad1aa0a4ab3db659c3ac76834b2c07f5ff7b6ddc`** | Re-audit immediately before AMEND. `press-wire: tick 2026-08-19T02:45Z` |

Verified AMEND: `git fetch origin && git rev-parse origin/main` → `ad1aa0a4ab3d`. Branch `claude/cs-intel-v2-masterplan` rebased `--onto origin/main` with no conflicts. The only first-parent between Sol's `71fbb0c` and `origin/main` is that press-wire tick (`data/marketing/press_wire/*`). **CS producers, contracts, daily.yml CS jobs, append-only fence, and Agent OS schema did not move.** Unrelated main motion is not a reason to restart competitor or product research.

### 2.2 Impact classification `a49e448d..ec62e498`

Command:

```bash
git diff --stat a49e448d024f641d48ebc3fa9c54bdcc4ddbd76a..ec62e4981c10d1ce7d6379cb9475747d49f790f1 -- \
  collectors/sec_capital_structure.py engine/capital_structure \
  'scripts/*capital_structure*' 'contracts/capital_structure*' \
  app/capital_structure.py data/capital_structure \
  .github/workflows/daily.yml .github/runner-policy.yml \
  engine/research_vault/r2_store.py config/house_law_checks.yml \
  config/sector_intelligence_ownership.yml
```

**Result: empty.** No Capital Structure producer, contract, daily CS job, R2 store, house-law check, or BioCatalyst ownership file moved between Sol's SHA and the freeze SHA.

Intervening first-parent commits are **unrelated** (HK board fixture, chronicle spine, press-wire, whitehouse, nightly timings, marketing outbox, Prophet US ledgers, cortex, oracle-tm, entry-radar hermetic control, research_vault catalog, us-scan-tier). They do not change CS architecture, contracts, runtime assumptions, authority, or proof.

**Shared infrastructure that can alter CS but did not in this window:** `daily.yml` (concurrent collect remains possible; CS job still uses `git pull --rebase --autostash -X theirs`), `r2_store.py`, runner policy. The concurrent-collect landmine and `-X theirs` lost-update class remain live from `DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE` and `DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS`. They affect CS identity and Git publication design; they are not new since Sol's SHA.

**This freeze does not redo the research program because unrelated main moved.** Live row counts below are dated observations at freeze, not eternal contracts. Accruing datasets invalidate tests that rebuild a registered historical result from today's moving ledger.

### 2.3 Sol AMEND shared-infrastructure impact (`71fbb0c..ad1aa0a4`)

Path-scoped diff empty for CS producers. Shared infra that **does** change W1, already on main at Sol review and still current:

| Artifact | On `origin/main` | W1 consequence |
|---|---|---|
| `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE` | Canonical push-path law | W1 extends this fence; does not invent a second publication system |
| `config/append_only_artifacts.json` | Only `government-revenue` enrolled | CS is **not** yet a family. W1 adds `capital-structure` |
| `scripts/ci/append_only_base_fence.py` + `push_retry.sh` `push_append_only_fence` | Collect + govrev-live + backfill | CS job at `daily.yml:1332` still `-X theirs` **with no fence** |
| Collect vs CS staging | Collect **unstages** `data/capital_structure` (`daily.yml:649`) | Calling the fence from collect cannot protect CS |

Re-run the CS-path diff immediately before any later wave starts. If it is still empty, the freeze stands. If it is not, incorporate only architecture-affecting drift.

---

## 3. Verified current state

### 3.1 PR 1 ingestion recovery is closed

PR #5792 fixed the actual freeze: dedicated Capital Structure R2 `PutObject AccessDenied`; writable-store probing falls through; `ingestion_run.json` and `health.json` exist; selected work with zero durable progress fails the CS health gate; compiler generation time and source freshness are distinct; production showed retrieval → verified storage → manifest → compiler advancement.

Do not reopen this bug absent new evidence.

Current write target at freeze: `store_id=r2_research` (dedicated `r2_capital_structure` is still not the successful write store). Live mix of retained objects: **1258 manifests on `r2_shared`, 714 on `r2_research`**.

### 3.2 Throughput is healthy; information horizon is stale

Dated observation from worktree `data/capital_structure/` compiled ~2026-08-18T08:38Z, generation `as_of` 2026-08-18T07:58:19Z:

| Metric | Value |
|---|---|
| `source_manifest.jsonl` rows | 1972 |
| Unique accessions | 600 |
| Unique ticker values (incl. `?`) | 331 |
| Manifests with ticker `?` | 455 |
| Projection issuer records | 426 |
| Selected / retained / storage-deferred (latest run) | 200 / 200 / 0 |
| Pending / deferred / parked | 19018 / 18818 / 403 |
| Oldest pending first-seen | 2026-08-01T15:35:40Z |
| Latest retrieval | 2026-08-18T03:33:56Z |
| Latest filing date | **2026-07-31** |
| Filing-date span in ledger | 2026-05-04 … 2026-07-31 (16 dates) |
| Event versions / edges / review queue | 600 / **1** / 425 |
| Health verdict | `ok` / `durable verified source evidence advanced` |
| Projection `coverage.freshness` | `fresh` vs 30h SLA (`age_hours` 0.66) |

The queue is oldest-first with fair lane rotation and `max_filings=200`. The health/projection freshness fields measure **compiler/generation age**, not **information horizon**. A run that stores 200 May–July filings while 18 August filings wait can still print `fresh`. That equation is architecturally false.

### 3.3 Nightly compilers vs dark substrate

**In the `capital_structure` job tonight:** collect handoff verify → (share-count materialize **if** `CAPITAL_STRUCTURE_SHARE_COUNT_PUBLICATION_ENABLED == 'true'`, default false) → `compile_capital_structure_events` → `compile_capital_structure_document_terms` → `build_capital_structure_projection` → `check_capital_structure_health` → all-or-nothing local commit → best-effort push.

**Coded, not in `daily.yml`:**

- `scripts/compile_capital_structure_instrument_candidate_terms.py`
- `scripts/compile_capital_structure_registration_lifecycles.py`

**Coded, default-off, Git has no generations:** Company Facts authenticated collector; share-count v2 materialize/retain/head (`PUBLICATION_ENABLED` default false; V3/V4 migration default false; isolated R2 conformance harness unprovisioned). `data/capital_structure/companyfacts/` at freeze contains only `.companyfacts_publish.lock`.

Do not call sophisticated unused infrastructure live.

### 3.4 PIT seam to preserve

`engine.capital_structure.biocatalyst_pit_adapter` (`biocatalyst_capital_structure_pit_adapter.v1`, owner `capital_structure` in `config/sector_intelligence_ownership.yml`):

- accepts explicit SEC issuer identity and timezone-aware `as_of`;
- replays the verified owner generation;
- preserves correction timing;
- exposes **event state only**;
- explicitly does not provide normalized instruments, fully diluted supply, active overhang, offering ability, remaining capacity, cash/runway, financing probability, identity resolution, or model/signal authority.

Extend the canonical CS owner **beneath** this seam. Do not create a BioCatalyst-specific capital ledger.

### 3.5 Page and API today

Page (`templates/capital_structure.html.j2`): "Observed Filing State" desk. Hero still says "Loading observed filings." Explicitly does not calculate instruments, share-count expansion, cash timing, or financing forecasts. Nav: `_navlinks.html.j2` → `capital_structure.html`.

API (`app/capital_structure.py`): `/api/capital-structure/v1/{coverage,overview,issuers/resolve,issuers/{id},issuers/{id}/events}`. Reads only `projection.json`. Soft-mounted in `app/main.py`. Paid `site_full` always-on.

Projection `unavailable` (every issuer at freeze):

`active_instrument_overhang`, `cash_runway`, `financing_probability`, `fully_diluted_shares`, `instruments`, `normalized_terms`, `offering_ability`, `remaining_capacity`.

Neural Web: **zero** `engine/neuralweb` references to capital structure. Prophet flags on CS artifacts are all false. Program remains `context_only`.

---

## 4. Capability ledger (against freeze SHA)

Statuses used only as defined:

| Status | Meaning |
|---|---|
| `PROVEN_LIVE` | Running in production with dated proof |
| `BUILT_NOT_PROVEN` | Code and tests exist; not nightly or not proven in prod |
| `PARTIAL` | Live but missing a load-bearing piece of the claimed capability |
| `DARK_OR_DISCONNECTED` | Exists as code or flag, no consumer |
| `BROKEN` | Violates a standing law or produces a false invariant |
| `SPEC_ONLY` | Docketed, not built |
| `NOT_BUILT` | Required by V2, no implementation |
| `REJECTED_BY_DESIGN` | Must not be built |

| Capability | Status | Producer | Consumer | Contract / artifact | Runtime | Proof or why absent | Unlocks today | Next dependency |
|---|---|---|---|---|---|---|---|---|
| SEC discovery + daily-index coverage | `PROVEN_LIVE` | `collectors/sec_capital_structure.py` | same collector | `capital_structure.discovery/v1`, `index_coverage/v1` | Nightly `collect` | 600 complete accessions; 16 filing dates | Queue population | Live-tail overlay (W2) |
| Retrieval attempts + queue receipt | `PROVEN_LIVE` | same | same | `retrieval_attempt/v1`, `retrieval_queue_receipt.v1` | Nightly | pending 19018, oldest first-seen 2026-08-01 | Retry/parking | Work-class split (W2) |
| Verified R2 evidence store | `PROVEN_LIVE` | same | compilers, terms | `capital_structure/sec/sha256/{aa}/{sha256}` | Nightly; `r2_research` now, historical `r2_shared` | 1972 manifests; content_sha256 + object_key | Immutable bytes | Occurrence+bytes `evidence_id` (W1) |
| Source manifest ledger | `PARTIAL` | same | event compiler, projection | `capital_structure.source_manifest/v1` `data/capital_structure/source_manifest.jsonl` | Nightly | 1972 rows; `manifest_id` hashes retrieval clocks (`BROKEN` identity, see §8) | Pointers to bytes | W1 `evidence_id` + whole-generation fence |
| Ingestion run + health | `PROVEN_LIVE` | collector + `scripts/check_capital_structure_health.py` | CS job gate | `ingestion_run/v1`, `ingestion_health/v1` | Nightly | PR #5792; verdict `ok` 2026-08-18 | Fail-closed storage | Horizon fields (W2) |
| Event spine + PIT/correction | `PROVEN_LIVE` | `scripts/compile_capital_structure_events.py` | projection, BioCatalyst PIT | `capital_structure.event.v1` | Nightly | 600 versions; keep-first `available_at` | Observed filing events | Stop inheriting clocked `manifest_id` (W1) |
| Event edges | `PARTIAL` | same | projection | `capital_structure.event_edge.v1` | Nightly | **1 edge in production** vs 600 versions; LPTH 44 EFFECT/POS AM still unlinked | Almost no lifecycle graph | Registration lifecycle (W4) |
| Review queue | `PROVEN_LIVE` | same | projection | `capital_structure.review_item.v1` | Nightly; rebuildable, not a historical ledger | 425 items | Explicit defer | Resolver (W4/W5) |
| Direct document-term ledger | `PROVEN_LIVE` | `scripts/compile_capital_structure_document_terms.py` | none for capacity | `document_term_observation.v1` | Nightly `cs_terms` | Fee cells transcribed; no aggregate capacity | Evidence spans | Candidate terms + capacity (W4/W5) |
| Instrument candidate terms | `BUILT_NOT_PROVEN` | `scripts/compile_capital_structure_instrument_candidate_terms.py` | none nightly | candidate-term contracts | **Not in `daily.yml`** | Script exists | — | Wire after W1; no silent instrument promotion |
| Registration lifecycle compiler | `BUILT_NOT_PROVEN` | `scripts/compile_capital_structure_registration_lifecycles.py` | none nightly | registration lifecycle contracts | **Not in `daily.yml`** | Script exists | — | W4 capacity vertical |
| Company Facts authenticated generations | `DARK_OR_DISCONNECTED` | `collectors/sec_capital_structure_companyfacts.py` | share-count materializer | `companyfacts_*` | Collector exists; **no Git generations** | lockfile only | — | R2 conformance harness, then W6 |
| Share-count v2 observe/materialize/publish/head | `BUILT_NOT_PROVEN` | `scripts/materialize_capital_structure_share_counts.py` | gated publication | `share_count_ledger.v2` | `PUBLICATION_ENABLED` default false | Contract says pre-production; harness never run | — | Provider-proven R2; do not promote to selected O/S until then |
| Candidate instrument resolver | `SPEC_ONLY` | W3A docket | — | — | — | W3A still required | — | W5 |
| Corporate actions / split basis | `NOT_BUILT` | — | — | — | — | PRE 14A classified as `authorization_or_vote_candidate` only | — | W6 |
| Projection + public JSON twin | `PARTIAL` | `scripts/build_capital_structure_projection.py` | API, page, site twin | `projection_bundle.v1` | Nightly | 426 issuers; event-state only; 8 unavailable caps; freshness=compiler age | Ticker lookup of observed filings | W3 UX on honest states; W2 horizon |
| Page (Observed Filing State) | `PARTIAL` | `templates/capital_structure.html.j2` | humans | — | Rendered | Hero "Loading"; not a capital twin | Filing list | W3 |
| HTTP API | `PARTIAL` | `app/capital_structure.py` | dashboard, future NW | `/api/capital-structure/v1/*` | Soft-mounted | Reads projection only | Machine event-state | Extend, do not fork |
| BioCatalyst PIT adapter | `BUILT_NOT_PROVEN` | `engine.capital_structure.biocatalyst_pit_adapter` | BioCatalyst closed-beta | `biocatalyst_capital_structure_pit_read.v1` | Coded; event-only | Ownership YAML present; not a second plane | PIT event replay if owner generation available | Extend owner underneath |
| Neural Web typed CS context | `DARK_OR_DISCONNECTED` | — | — | — | No engine hits | Flags false | — | W7 after deterministic events |
| Prophet CS features | `REJECTED_BY_DESIGN` until gauntlet | — | — | `prophet_authority=false` | — | Program `context_only` | — | Per-feature gauntlet (W7) |
| Opaque overall CS / dilution score | `REJECTED_BY_DESIGN` | — | — | — | — | 2026-08-01 docket + this freeze | — | Never |
| Legacy `edgar_dilution` | `PROVEN_LIVE` | `collectors/edgar_dilution.py` | existing dilution feed | `data/edgar/dilution_events.parquet` | Nightly | Shadow only; no cutover | Compatibility | Keep shadow |
| Git CS generation publication | `PARTIAL` | `daily.yml` CS checkpoint + `push_retry.sh` | main selector | `data/capital_structure/**`, `site/capital-structure-data` | Best-effort; GH013 possible | Later nights can land; `-X theirs` can wholesale-replace JSONL; CS job has **no** `push_append_only_fence` | Compiled generation when push wins | W1 enroll CS in append-only fence; no new control plane |
| Source identity under re-observation | `BROKEN` (latent) | `engine/capital_structure/source_identity.py` | every downstream ID | `manifest_id_for` hashes full body incl. clocks | Masked by queue skip | See §8 | False uniqueness | **W1 (first implementation)** |
| LIVE_TAIL vs backlog work classes | `NOT_BUILT` | — | — | — | Oldest-first 200 | Horizon stale while throughput ok | — | W2 |
| Six-question capital twin state | `NOT_BUILT` | — | — | `capital_structure_state.v2` (this freeze) | — | Event-state projection only | — | W3–W6 |
| Global collect mutex | `REJECTED_BY_DESIGN` (for this program) | — | — | `DEC:COLLECT-MUTEX-CANNOT-LIVE-IN-ET-GATE` | Concurrent collect possible | Measured 2026-08-18 | — | Operator owns global orchestration |

---

## 5. Product thesis and value model

**V2 is a point-in-time issuer financing state machine and capital-supply intelligence system.**

It separates six questions that the current product and most dilution tools blur:

| # | Question | What it is | What it is not |
|---|---|---|---|
| 1 | **Authorization** | Securities/programs that exist on paper (shelf, S-1, warrants outstanding, authorized shares) | Permission to sell tomorrow |
| 2 | **Execution eligibility** | What can legally/operationally be used *now* (EFFECT, S-3/F-3 status, I.B.6 vs I.B.1, shareholder approval, listing) | Remaining dollars |
| 3 | **Remaining capacity** | Capacity under the relevant constraints (I.B.6 1/3 float, Nasdaq 20%, authorized-but-unissued, unsold shelf, ATM program size) | Expected dilution |
| 4 | **Economic supply** | Shares that could realistically reach the market under **named** price scenarios and document triggers | A single "overhang" number |
| 5 | **Funding need** | Cash/debt/catalyst obligations that create financing pressure | A probability of an offering |
| 6 | **Observed issuance** | What was actually sold, exercised, converted, exchanged, or retired | Authorization or remaining capacity |

Frozen laws:

- A shelf registration is never automatically "expected dilution."
- An EFFECT notice is never automatically "active financing capacity."
- Missing data is never zero.
- A model probability is never a filing fact.
- Capacity ≠ expected supply ≠ actual issuance.

**Value model (jobs, not screens):**

| Job | Who | Current product | V2 |
|---|---|---|---|
| What changed that matters? | Desk / Neural Web | Undifferentiated EDGAR-ish event list; 77 deferred, 425 review | Semantic capital-change events with fact IDs |
| Can they fund the next catalyst? | Issuer research | Unavailable | Funding-need family with refused-if-no-burn-basis |
| What can they issue this week? | Issuer research | Unavailable (`offering_ability`) | Eligibility + remaining capacity, or explicit unavailable |
| What hits the float if price goes to X? | Issuer research | Unavailable | Scenario supply from instrument state, not a score |
| What did they actually sell? | Audit / PIT | Partial (events, not usage) | Transaction family with provenance |
| Should Prophet de-escalate? | Later research | Forbidden | Individual shadow features, never one CS score |

Competitors sell ticker lookup + opaque risk. Mastermind's advantage is the evidence-chain twin plus PIT/correction. That is the product. Parity with competitor screens is a checklist, not the architecture.

---

## 6. Competitor research (refresh 2026-08-18)

Public surfaces only. No copy of code, copy, private data, proprietary scores, assets, hidden prompts, or brand identity. Competitor functionality is a **parity reference**, not the architecture.

### 6.1 DilutionTracker.com

- Primary marketing site returned **HTTP 500** on 2026-08-18 session fetch. Knowledge base at `knowledge.dilutiontracker.com` remained live.
- Documented jobs (2026-08-01 docket, still the public KB inventory): ticker dossier; completed offerings; pending S-1/registration; ATM / shelf / warrants / converts / ELOC; O/S chart; alerts; watchlists; IB-tier / "baby shelf" heuristic language in explainers.
- No public API documented in the 2026-08-01 study; 2026-08-18 refresh found none on the live KB.
- Third-party indexed pricing still conflicts (~$60–74/mo). Treat as unverified.
- **Do not encode legal rules from DilutionTracker explainers.** I.B.6, 415, 5635(d) come from SEC/Nasdaq primary sources (§7).

### 6.2 Dilutracker.com

- Live on 2026-08-18.
- Public docs: REST + MCP on paid plans; **24h filing lag** plus refresh credits; four opaque risk scores; toxic-term flags.
- Public pricing observed: Starter $59 / Pro $119 / Business $299.
- Reverse splits: **not observed** as a first-class public surface in the docs reviewed.
- Machine access is their differentiator. Mastermind already has an authenticated API seam; V2 extends it with state families, not a second API island.

### 6.3 Other public surfaces (parity only)

AskEdgar.io (filing retrieval/search). Smaller names (DilutionWatch, StockDilutionTracker) exist as thin trackers. None is an architecture source.

### 6.4 Jobs-to-be-done parity matrix

| Job | DilutionTracker (KB) | Dilutracker | Mastermind at freeze | V2 owner |
|---|---|---|---|---|
| Ticker dossier | Yes | Yes | Partial event dossier | W3 Capital Twin |
| New filings | Yes | Yes (lagged) | Oldest-first backlog; horizon stale | W2 live-tail + W3 desk |
| Pending offerings | Yes | Yes | Registration observed; not pending-vs-effective | W4 |
| Completed offerings | Yes | Yes | Not a transaction family | W4/W5 usage |
| Reverse splits | Yes (KB) | Not observed public | `NOT_BUILT` | W6 |
| Warrants | Yes | Yes | Candidate compiler dark; page unavailable | W5 |
| Converts / preferreds | Yes | Yes | Same | W5 |
| ATM | Yes | Yes | 424B5 often `classification_pending` | W4 |
| ELOC / equity line | Yes | Yes | Not modeled | W4 (CFI 116.21) |
| Shelf state | Yes | Yes | Form family only; no remaining capacity | W4 |
| Float / O/S | Yes | Yes | Share-count v2 default-off | W6 |
| Runway | Partial / inferred | Partial | Unavailable | W6 cash family |
| Alerts / watchlists | Yes | Yes | No CS-specific alerts | W3 desk subscriptions later |
| API / machine | Not documented | REST+MCP | Event-state API live | Extend `/api/capital-structure/v1` |
| Opaque overall score | IB-tier / heuristics | Four risk scores | Forbidden | `REJECTED_BY_DESIGN` |

Mastermind gap vs all of them: evidence-chain digital twin, six-question split, PIT/correction, no opaque score.

---

## 7. Regulatory research (primary sources)

Never encode a legal rule from a competitor explainer where an SEC or exchange primary source exists. The following are the definitions V2 capacity logic may use. **This is not legal advice.** Staff CFIs are staff positions, not Commission rules; proposed releases are not current law.

### 7.1 Form S-3 / F-3 Instruction I.B.6 (baby shelf)

Primary: [Form S-3](https://www.sec.gov/files/forms-3.pdf).

- Eligible issuer offering securities for cash, aggregate market value of **equity securities sold in primary offerings under this instruction during the 12 calendar months including this sale** ≤ **one-third of public float**.
- Public float: aggregate market value of voting and non-voting common equity held by non-affiliates, computed using **price at which the common equity was last sold, or average of bid and asked, within 60 days**.
- Instruction 2: derivative securities count the **underlying equity**, not the derivative's trading value.
- Registrant must be listed and not a shell (Form S-3 General Instruction I.B.6 + I.A. as applicable).

F-3 I.B.5 is the foreign private issuer analogue; model from the F-3 form text, not by aliasing S-3.

### 7.2 2026 SEC interpretations (CFI Securities Act Forms)

Official CFI page (verified 2026-08-18): [SEC Compliance and Disclosure Interpretations — Securities Act Forms](https://www.sec.gov/rules-regulations/staff-guidance/compliance-disclosure-interpretations/securities-act-forms).

| CFI | Date | Load-bearing rule for V2 |
|---|---|---|
| **116.22** | staff | I.B.6 cap is measured immediately prior to **takedown**, on the amount **offered**, not sold. Later takedowns count only actual sales of prior takedowns. |
| **116.23** | staff | Concurrent continuous offerings: **unsold offered amounts still count** against I.B.6. |
| **116.25** | staff | Concurrent I.B.3 resale used to evade I.B.6 **counts against I.B.6**. |
| **116.26** | **2026-03-19** | ATM prospectus supplement filed while I.B.1-eligible may **continue at that supplement's full amount** after a 10(a)(3) drop into I.B.6. Staff will not object. |
| **116.21** | staff | Primary ELOC at market-discount put = ATM under Rule 415(a)(4); I.B.6 ELOC max = **1/3 float at execution**. |

V2 must store CFI version + as-of date on every capacity calculation. A later CFI revision is a new compiler generation, not a rewrite of historical PIT reads.

### 7.3 Rule 415, EFFECT, amendments, 424B, resale vs primary

- **Rule 415(a)(4):** at-the-market offering definition (equity securities into an existing trading market at other than a fixed price).
- **Rule 415(a)(5):** three-year limitation on shelf.
- **EFFECT:** Notice of Effectiveness. Observing EFFECT is **authorization becoming effective**, not remaining capacity and not a sale.
- **RW / withdrawal:** retires the registration path. Must be a first-class lifecycle edge (today: almost no edges).
- **S-3/A, POS AM:** amendment lineage. POS AM can reopen or alter an already-effective statement; it is not a new shelf by itself.
- **Rule 424(b)(1)–(8):** prospectus-supplement clocks. 424B5 is the common ATM/takedown supplement; current compiler often emits `prospectus_event` / `classification_pending` (CLNN, CYTK, GOOGL at freeze).
- **Resale vs primary:** I.B.3 resale registration is not primary issuance capacity. CFI 116.25 forbids treating abusive concurrent resale as outside I.B.6.
- **Post-acceptance corrections:** SEC guide (2026-03-04) — original filing remains; amendment/correction is a later object. V2 already has this shape on the event spine (keep-first `available_at`). Do not delete historical evidence.

### 7.4 ATM and equity lines

- ATM: Rule 415(a)(4) + prospectus supplement program size + subsequent 424B usage + 10-Q/8-K sales disclosures. Program size ≠ remaining ≠ expected supply.
- ELOC: **not an SEC defined term**. Model from CFI 116.21 + the specific purchase agreement / registration statement. Do not invent a generic ELOC object that every equity line must fit.
- Pre-funded warrant: **not an SEC defined term**. Model as a warrant whose remaining exercise price is de minimis; I.B.6 Instruction 2 still counts underlying equity.

### 7.5 Warrants, converts, future-priced securities

Preserve as instrument state (quantity/principal, strike/conversion, fixed vs variable, floors, resets, price protection, blockers, share caps, exercisability, maturity, registration status, holder/counterparty if public, amendment lineage, source spans).

"Toxic" is a **disclosed term pattern** (reset, variable conversion, make-whole, extreme warrant coverage), never a score. `toxic_terms_detected` fires only on named term classes with fact IDs.

### 7.6 Nasdaq Rule 5635(d) — 20% issuance

Primary text recovered from SEC SRO orders [34-84287](https://www.sec.gov/files/rules/sro/nasdaq/2018/34-84287.pdf) and [34-88056](https://www.sec.gov/files/rules/sro/nasdaq/2020/34-88056.pdf) after the live Nasdaq rulebook timed out.

- Shareholder approval required for issuance at a price less than the **Minimum Price** of **20% or more** of common stock or voting power outstanding before the issuance (private placement / other than public offering).
- **Minimum Price:** lower of (i) closing price immediately preceding the binding agreement and (ii) average closing price of the five trading days immediately preceding the binding agreement (NOCP as defined in the rule).
- Public offering exception exists in the rule; V2 must not treat every registered sale as exempt without the offering's actual distribution facts.
- Share caps in the purchase agreement are **contractual**, distinct from 5635(d).

Post-2020 amendments were not independently re-verified against a live Nasdaq rulebook in this session. Wave 4 must re-read the then-current Rule 5635 before encoding. NYSE 312.03 is a sibling constraint for NYSE issuers; do not apply Nasdaq text to NYSE names.

### 7.7 Authorized shares, reverse splits, corporate-action dates

- Authorized-but-unissued is a charter constraint, usually from 10-K/10-Q cover, DEF 14A, or charter exhibit — not from S-3 capacity.
- Reverse splits: effective date is a **corporate-action clock**, not the proxy mailing date and not the 8-K announce date. Until W6, any split-adjusted share figure is unavailable, not silently adjusted.
- Serial-financing biotech: many EFFECT + POS AM pairs without edges (LPTH at freeze) are a **linkage** problem, not missing filings.

### 7.8 Proposed 2026 registered offering reform — watch only

**Release 33-11418 (2026-05-19), comments closed 2026-07-27, is PROPOSED ONLY.** It would materially change I.B.6. **Do not encode as current law.** Capacity calculations must name the rule vintage. A later adopting release is a new compiler version with its own `valid_from`.

---

## 8. Identity, idempotency, and concurrent observation

### 8.1 Audit result — DNR violation, currently masked

`manifest_id_for` (`engine/capital_structure/source_identity.py:136-141`) hashes the **entire manifest body except `manifest_id`**.

The schema **requires** `retrieval.retrieved_at` and `retrieval.first_seen_at` (`contracts/capital_structure_source_manifest.schema.json:72-78`).

The collector sets **both** to wall-clock `retained_at` after store+readback (`collectors/sec_capital_structure.py:1728-1737`).

Therefore **unchanged SEC bytes produce a new `manifest_id` on every successful re-retention.**

| Identity class | Current behavior | Required behavior |
|---|---|---|
| **Evidence identity** | Not first-class; clocks and interpretation sit inside `manifest_id` | Derived `evidence_id` over occurrence + retained bytes only (`DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES`) |
| **Retention / manifest identity** | Full-body hash including retrieval clocks — **unstable as evidence id** | Keep `manifest_id_for` as the interpretation-revision receipt. Do not weaken it. |
| **Observation / recheck** | Attempt rows exist; children have no attempt; post-readback clock is not on the row | Reuse `retrieval_attempts`; additive fields if needed. No second observation artifact. |
| **Run receipt** | `attempt_id` includes run clock — **correct** | Keep as operational, not content identity. |

`event_id` hashes a body that includes `manifest_ids` (`event_spine.py:469-471`), so the spine **inherits** clock contamination if a remint occurs.

Sequential re-observation is **masked** by `_eligible_complete_accessions` (`sec_capital_structure.py:1287-1313`): eligible + clean + valid `file_number_provenance` skips the accession. Concurrent `collect` jobs (measured possible; this program must not solve via `et_gate` mutex) can both select the same pending accession and mint two `manifest_id`s for the same bytes.

Tests in `tests/test_capital_structure_source_identity.py` do **not** assert same-bytes → same `manifest_id`.

This is the same forbidden construction as Filing Forensics Wave-2 (`DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`): artifact count measures our cadence, first-retention clocks become last-run clocks, consumers become O(store age).

### 8.2 Ruling — occurrence+bytes `evidence_id` (do not patch in this PR)

**DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES** supersedes **DEC:CS-V2-IDENTITY-DUAL-READ**.

Sol AMEND (2026-08-18): keep forward-only dual-read and no historical rewrite. Do **not** freeze the previously proposed v2 hash subset.

1. Do **not** rewrite historical `manifest_id`s or downstream PIT receipts.
2. Dual-read: v1 manifests continue to validate under the current full-body `manifest_id_for`. V2 introduces a derived `evidence_id` over immutable source occurrence + retained bytes: `key_format`, `source_system`, `submission_accession`, occurrence (`submission` or `{parent_content_sha256, byte_start, byte_end}`), `content_sha256`.
3. **Exclude** from evidence identity: retrieval/run clocks, file-number interpretation, ticker/aliases, parser state/version, normalized issuer mapping, `document_role`, `document_version`, physical storage namespace, `source_id`. Those may remain on the manifest as interpretation. A parser correction **must not remint** `evidence_id`.
4. Distinct source occurrences **must not collapse**: same bytes in two accessions stay two evidence ids; same bytes in two SGML sequences in one accession stay two evidence ids. Complete submission and each child document are distinct, with children carrying parent coordinates.
5. Canonical `first_known_at` is the **verified-retention clock** of the first observation of that `evidence_id` whose generation later became canonical. Git publication is the freeze event, not the timestamp (`DEC:CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK`). Per-attempt `attempted_at` and verified-retention `retained_available_at` are observation clocks. A delayed/competing observation with an earlier local timestamp **cannot** move a published PIT boundary backward.
6. Observation plane: start from existing `retrieval_attempts`. Add fields only if the current contract cannot represent successful re-observation of children. Do not mint a second observation artifact by convenience.
7. Do **not** add `merge=union` to `data/capital_structure/source_manifest.jsonl`. Do **not** content-aware-merge that file at push time. Publication is `DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE`.
8. Drop the unconditional durable W1 gate “concurrent merge = 1 evidence + 2 observations.” Mandatory proof: one canonical `evidence_id`, no duplicate economic event, no stale generation clobber.

Independently useful machine capability of W1: the same SEC occurrence cannot become two economic sources; interpretation correction cannot remint evidence; overlapping CS jobs cannot publish a mixed generation.

Hostile fixtures W1 must pin are listed in the identity DEC (same document two clocks; same bytes two accessions; two sequences in one accession; corrected file-number/issuer/parser; submission plus children; legacy v1; multiple valid v1 ids for one occurrence).

---

## 9. Publication / authority ruling

**DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE** supersedes **DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR**. The Git-selector boundary is **restated, not reopened.**

| Plane | Owner today | Ruling |
|---|---|---|
| Durable **evidence** | R2 content-addressed objects (`capital_structure/sec/sha256/…`) | Remains the evidence store. Split `r2_shared` / `r2_research` is a physical namespace, not a second truth. `storage.store_id` already records which. |
| Durable **compiled generation selector** | Git `data/capital_structure/**` + `site/capital-structure-data` after the CS checkpoint | **Git remains the canonical generation selector** until the operator explicitly moves it onto the existing company/shared publication plane. No new publication control plane. |
| Why later CS generations can land | Best-effort `push_retry.sh`; GH013 is a ruleset/Actions bypass on `refs/heads/main`, not an ingestion defect; later nights retry; rulesets are not permanently blocking every CS push | Treat push loss as a known degraded publication state, not silent success. |
| Valid R2 evidence + Git push loses | Bytes remain in R2; next checkout restores last Git ledger; accession can re-queue | W1 `evidence_id` must make re-derive **reuse** evidence IDs. Health must distinguish "retained in R2, unpublished in Git" from "not retained." |
| All-or-nothing local generation | Correct for a compiled checkpoint | Keep. Partial generations must not commit. A manifest merged after compile would no longer match that run's events/terms/projection/health. |
| `git pull --rebase --autostash -X theirs` | Can wholesale-replace `source_manifest.jsonl` (merge unspecified; not in `.gitattributes`) | W1: extend `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE`. On proof that `origin/main` contains source-ledger evidence this candidate would drop, **withhold the entire coherent CS generation**. Do not `merge=union`. Do not file-merge the JSONL at push time. Call the fence from the **capital_structure** job, not collect (collect unstages CS paths). |

GH013 rejecting a legitimate generation is an **org ruleset** problem (see `research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md` class). CS must be idempotent when Git loses. CS must not invent a second selector to work around GH013.

---

## 10. Time / PIT / correction architecture

Clock model (every selected fact carries the clocks that apply; unused clocks are explicit nulls, never inferred):

| Clock | Meaning | Who sets it |
|---|---|---|
| `economic_effective_at` | Filing period / corporate-action effective time / takedown measurement time | Source document or exchange notice |
| `sec_accepted_at` | SEC acceptance | EDGAR header |
| `sec_published_at` | SEC dissemination / index appearance | Index or submissions feed |
| `mastermind_first_seen_at` | Canonical first-known time of this **evidence_id** | Frozen at first Git publication of that evidence (W1). Never moved backward by a later local timestamp |
| `retrieved_at` / `attempted_at` | This retrieval attempt | Observation log (`retrieval_attempts.attempted_at`) |
| `retained_available_at` | Readback-verified R2 put | Collector after verify; per observation |
| `parser_available_at` | Compiler/parser version could emit this interpretation | Compiler generation |
| `correction_available_at` | Later parse, amendment, or SEC post-acceptance correction became visible | Correction event; **must not** travel back to filing time |
| `valid_from` / `valid_to` | State interval in the twin | State compiler |
| `generation_at` | Current compiled generation time | Projection/telemetry `as_of` |

Frozen semantics (already true on the event spine; extend, do not replace):

- Historical source evidence is **immutable** even if the current canonical interpretation is corrected.
- A later parse improvement, filing amendment, or SEC post-acceptance correction appears only at its `correction_available_at` / `parser_available_at`.
- PIT read at time T uses facts with `available_at ≤ T` and respects `valid_from`/`valid_to`.
- Keep-first `available_at` on the **event spine** remains first-seen of that event. Canonical `first_known_at` on **evidence** is a published PIT boundary: once on `origin/main` it cannot later move backward merely because a delayed/competing observation carried an earlier local timestamp.
- Supersession is an **edge** (`correction_of`, `amends`, `withdraws`, `effectuates`, `supersedes`), never a destructive rewrite.
- BioCatalyst adapter must keep replaying this law. New state families ride the same clocks.

Accruing ledgers: tests must not rebuild a registered historical result from today's moving JSONL. Registered research artifacts and live health invariants are different things (house precedent on freeze-SHA main).

---

## 11. Canonical state ontology — `capital_structure_state.v2`

Conceptual model. Reconstructable as known to Mastermind at a requested instant. Not "latest restated truth."

```text
IssuerTwin[as_of]
  identity          — CIK/issuer_id, ticker history, exchange, security master join
  share_basis       — issuer-reported O/S, selected O/S, public float, authorized/unissued,
                      split basis, contradictions
  registration      — shelves, S-1/F-1, EFFECT, expiry, amendments, primary vs resale,
                      ATM, ELOC, registered remaining, I.B.6 remaining, exchange/share caps
  instruments       — warrants, pre-funded, converts, preferreds, debt, units, earnouts
  cash_funding      — unrestricted/restricted cash where supportable, marketable-securities
                      policy, burn basis, maturities, commitments, going-concern, runway
                      scenarios, catalyst funding horizon
  transactions      — priced offerings, ATM usage, exercises, conversions, exchanges,
                      PIPEs, repurchases
  uncertainty       — conflicts, stale facts, missing denominator, unresolved instrument
                      identity, parser ambiguity, source correction, assumptions, confidence
  change_events     — typed deltas with fact IDs (see §14)
```

Every selected fact or calculation retains exact provenance (manifest_id / content_sha256 / source spans) and the clocks in §10.

`capital_structure.event.v1` remains the filing-event adapter. Twin state is a **compiler over** events + terms + (later) share observations + (later) instruments. It is not a second SEC store.

Null law: unavailable / contradictory / refused / not-covered are first-class. Missing ≠ 0.

---

## 12. Live-tail / recovery / backfill architecture

**DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG**

Do not merely increase `MAX_FILINGS`.

### 12.1 Work classes

| Class | Definition | SLO (freeze target; operator may tighten) | Starvation rule |
|---|---|---|---|
| `LIVE_TAIL` | Newly disseminated **material** filings whose `sec_published_at` is within the live window (proposed: last 36h, or since last successful live-tail watermark) | Latest material filing discovered ≤ 6h from SEC publication during a healthy night; retained and compiled in the next CS job that runs after discovery | **Cannot be starved by historical debt.** Dedicated quota first. |
| `RECOVERY` | Recent missed/failed/parked material filings (proposed: first-seen or published within 14d, not yet retained, or parked with retryable class) | Oldest recovery item age reported; drain before historical | Second quota |
| `HISTORICAL_BACKFILL` | Coverage debt older than recovery | Throughput metric only; no horizon claim | Fills remaining budget |

Material forms: the existing registration allowlist plus issuer-scoped reconciliation already in coverage_claim, **minus** known exclusions listed in telemetry. W2 may add a live-tail overlay for 8-K offering items and 424B5/B3 already in-policy; it must not silently expand to the excluded S-8/S-4/N-2 universe without a separate ruling.

### 12.2 Source-plane extension (narrowest)

Current discovery is the **SEC daily form index** (`collectors/sec_capital_structure.py`). That plane cannot see today's filings until the index publishes them, and the queue then places them behind 19k older pending rows.

Evaluate, in this order, as an **overlay on the same collector**, not a second store:

1. Existing daily index (keep as historical/recovery census and as the close-the-day proof).
2. SEC real-time / current submissions facility (`browse-edgar action=getcurrent` Atom, or the then-current EDGAR "latest filings" feed) **only** to enqueue `LIVE_TAIL` accessions that match the material allowlist.
3. Do not stand up a second complete-submission crawler, a second R2 key scheme, or a submissions-search product.

W2 chooses (2) only if (1) cannot meet the live-tail SLO. The freeze prefers the overlay; it does not implement it.

### 12.3 Quotas, retry, duplicates, backpressure

- Per-run budget stays bounded (today 200 is a rate-budget, not a product SLO). Proposed split: **live-tail ≥ 40% or all live-tail eligible, whichever is smaller; recovery next; historical last.** Exact integers are an implementation choice inside that law.
- Retry/parking: keep existing parked classes; live-tail failures escalate to recovery, not to the back of historical.
- Duplicate/concurrent: W1 identity makes double retrieve of the same bytes idempotent. W2 must still prefer not to fetch twice (queue claim / keep-first accession lock in the collector process). No global mutex.
- Correction discovery: EFFECT, POS AM, S-3/A, RW, 424B, 8-K on an already-retained file number join the live-tail class even if the original registration is historical.
- Backpressure: if R2 or Git publication is degraded, live-tail still **retains** evidence (R2) and reports unpublished-in-Git; it does not skip live-tail to "catch up" historical Git rows.
- Alerts: live-tail gap age > SLO; oldest recovery > 14d; selected>0 and retained=0 (already gated by #5792); GH013 / push lost with R2 retained.

### 12.4 Health fields (required)

A healthy information horizon reports at least:

- latest **discovered** material filing (`sec_published_at`, accession, form)
- latest **durably retained** material filing
- latest **compiled** material filing
- **age of live-tail gap** (now − latest discovered material in-window, or time since empty-window proof)
- oldest recovery item
- oldest historical item
- arrival rate (discovered/hour in-window)
- successful processing rate (retained/hour, compiled/hour)

`coverage.freshness: fresh` must not be computable from compiler `generated_at` alone. A run that stores 200 old filings while today's filings wait **must not** call the information horizon healthy.

---

## 13. Experience architecture

Two first-class workflows, **same canonical state**, no third header family (`templates/_site_nav.html.j2` + `_navlinks.html.j2`).

### 13.1 Market-wide Capital Changes Desk

Question: **What changed today / recently that matters?**

Semantic events, not undifferentiated EDGAR rows. Proposed vocabulary (deterministic; each requires evidence, see §14):

- new financing path
- EFFECT
- pricing
- ATM activated / expanded / used
- capacity materially changed
- warrant / convert reset
- resale unlocked
- shareholder approval / share-cap change
- reverse split
- O/S jump / reconciliation
- financing path withdrawn / expired
- overhang retired
- funding gap opened / closed
- source correction / conflict

Desk filters: live-tail vs recovery vs historical; classified vs deferred vs review; issuer; form family. Honest as-of: show **latest compiled material filing date**, not wall-clock "today," until W2 lands.

### 13.2 Issuer Capital Twin / Dossier

Top of page, **before** evidence tables, answers:

1. What changed?
2. Why does it matter?
3. What can management issue right now?
4. How much funding does it appear to need, and when?
5. What existing securities can become supply?
6. Which price / doc / date triggers matter?
7. What has actually been issued?
8. What is uncertain or contradictory?

Then evidence and calculations. Current "Observed Filing State" becomes the evidence strip, not the hero.

### 13.3 Failure-state matrix

Do not let "Loading" or blank cards substitute for an unavailable state.

| State | User-visible meaning | Machine | Forbidden substitute |
|---|---|---|---|
| `healthy_current` | Twin current vs live-tail SLO; enough facts for the answered questions | horizon ok + required families present | — |
| `stale` | Last compiled/retained material older than SLO | `live_tail_gap_age` | Showing compiler-fresh as current |
| `backlog_degraded` | Throughput ok, horizon stale (today's production) | pending historical starving tail | `verdict: ok` without horizon |
| `partial_coverage` | Some families present, listed unavailable remain unavailable | current projection | Hiding the eight unavailable caps |
| `source_unavailable` | R2/index/SEC miss | health fail-closed | Empty cards |
| `unresolved_instrument` | Candidate terms without resolver identity | review queue | Guessing a warrant count |
| `contradictory_share_basis` | Two O/S facts disagree | both shown | Picking one silently |
| `no_defensible_burn_basis` | Cash family refused | `cash_runway` unavailable | Implied 0 burn |
| `corporate_action_ambiguity` | Split/effective date unresolved | share figures unavailable | Silent adjust |
| `sec_correction` | Post-acceptance correction arrived | correction event at its clock | Rewriting the original row |
| `calculation_refused` | Inputs missing or contradictory | no number | 0 remaining capacity |
| `no_active_path` | Genuinely no live registration/instrument path **after** coverage is sufficient | explicit empty | "No data" vs "no path" confusion |

Hero copy at freeze ("Loading observed filings") is non-compliant with this matrix. W3 replaces it.

---

## 14. Intelligence / graph architecture (Neural Web)

Create **deterministic typed state and change events first.** Neural Web consumes them as context with causal pathways and exact fact IDs. Optional LLM synthesis may **explain** the deterministic state/delta. It may not invent facts, decide capacity, rank trades, or originate authority (constitution A7; program `context_only`).

Do not create a generic `company_event.v1` namespace in this program (contract review_by 2026-10-01). CS events stay `capital_structure.event.v1` (filings) plus `capital_structure.change.v2` (twin deltas).

### 14.1 Change-event vocabulary and fire criteria

Each event requires: issuer_id, valid_from, evidence fact_ids (manifest/content_sha256/spans), clocks, confidence, and a **null** if the criterion cannot be evaluated.

| Event | Deterministic criterion (minimum) | Evidence required | Does not fire when |
|---|---|---|---|
| `capital_state_changed` | Any other typed change in this table, or a documented catch-all for unclassified but material twin field change | Union of child evidence | Parser noise without a field change |
| `financing_capacity_increased` / `_decreased` | Remaining **registered** or I.B.6 or ATM program capacity changed beyond a registered materiality epsilon **and** both sides were evaluable | Registration + capacity calc receipts | Eligibility unknown; missing float (use `calculation_refused`) |
| `funding_gap_opened` / `_closed` | Funding-need vs cash/runway scenario crossed a named horizon (e.g. cash < committed uses before catalyst date) **and** burn basis is defensible | Cash facts + obligation facts | `no_defensible_burn_basis` |
| `dilution_overhang_increased` / `_decreased` | Economic-supply scenario at last close (or named price) changed | Instrument state + share basis | Instruments unavailable |
| `toxic_terms_detected` | Named term class present (variable conversion, reset, extreme coverage) in a **current** instrument | Source spans | Heuristic "looks toxic" |
| `resale_unlock_approaching` | Contractual or Rule 144 / registration resale date within a registered window | Agreement/registration dates | Guessed lockup |
| `warrant_exercise_zone_entered` | Last price ≥ strike (or cashless-exercise condition) for a currently exercisable warrant | Price as-of + warrant terms | Missing strike |
| `convert_reset_triggered` | Reset date/price condition met per indenture | Indenture spans + price | Missing floor/reset terms |
| `maturity_pressure_increased` | Debt/preferred/convert maturity entered a registered horizon | Instrument maturity | Unknown maturity |
| `capital_overhang_removed` | Instrument retired, expired, withdrawn, or converted with share issuance recorded as transaction | Lifecycle edge + transaction | EFFECT without retirement |

Neural Web lobe: context-only. Inputs are these events + twin snapshot IDs. No CS score. No Prophet authority.

---

## 15. Prophet / research authority

Keep `prophet_authority=false` through the deterministic product build. Never graduate one opaque "Capital Structure score."

Transparent **candidate** features (each is its own promotion decision):

| Feature | Sketch | Missingness |
|---|---|---|
| Funding runway / funding gap | Cash vs burn vs catalyst/maturity dates | Refuse if no burn basis |
| Execution-ready issuance capacity / mkt cap or float | Eligibility ∩ remaining capacity | Unavailable ≠ 0 |
| Dilutive overhang / float | Scenario supply at last close | Instruments required |
| Price-sensitive warrant/convert exposure | Delta-like scenario, not a Greek claim | Missing strike → unavailable |
| Reset / toxic-term severity | Count/notional of named classes | Not a 0–100 score |
| Maturity pressure | Notional due inside 90/180/365d | Unknown maturity excluded, not zeroed |
| Funded-through-catalyst | Boolean with named catalyst date | Catalyst unknown → unavailable |
| Financing hazard at defined horizons | Probability **only** after gauntlet | Display-tier hazard is not a probability |
| Recent overhang removal | `capital_overhang_removed` in window | — |
| Source freshness / coverage confidence | Live-tail gap, review fraction | — |

Each feature requires, before any authority:

- immutable PIT input snapshot
- exact definition
- missingness behavior
- confidence/coverage
- outcome definition
- event study
- leakage-safe walk-forward
- regime/cohort analysis
- calibration where probabilistic
- shadow period
- **individual** promotion decision

LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations.

---

## 16. Real-data reference compositions

Architecture validation against the freeze generation (`projection.as_of` 2026-08-18T07:58:19Z). **Every dossier below is event-state only.** The eight `unavailable` fields apply to all six. Gaps are classified, not fabricated.

Shared unavailable strip (all issuers):

`active_instrument_overhang`, `cash_runway`, `financing_probability`, `fully_diluted_shares`, `instruments`, `normalized_terms`, `offering_ability`, `remaining_capacity`.

### 16.1 Straightforward / automatic shelf — AIR (AAR CORP)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0000001750`, ticker AIR | Present |
| What changed | `automatic_shelf_registration_observed` | Present as filing event |
| Authorization | S-3ASR `0001104659-26-085644`, filing date 2026-07-22, lifecycle `filed` | Observed registration; **not** remaining WKSI capacity |
| Execution eligibility | ASR implies WKSI path **if** still eligible at takedown | **Unavailable** — no I.B.1 vs I.B.6 check, no EFFECT-needed (ASR is auto) encoded as eligibility |
| Remaining capacity | — | `calculation_refused` / `remaining_capacity` unavailable |
| Economic supply / instruments / cash / transactions | — | Unavailable |
| Uncertainty | Single classified event; coverage `partial` | Honest |

**Gap class:** automatic shelf observed ≠ executable ATM ≠ expected dilution. V2 W4 must not print a dollar remaining from an ASR without takedown math.

### 16.2 ATM-heavy / prospectus supplement — CLNN (Clene Inc.)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0001822791` | Present |
| Timeline | 424B5, 424B5, 8-K; latest 424B5 `0001437749-26-014937` filing 2026-05-05 | Present |
| What changed | `classification_pending` ×3 | **Deferred** — not "ATM activated" |
| Coverage | 3 events, 0 classified, 3 deferred, 3 review | Review-queue state |
| ATM remaining / usage | — | Unavailable; supplement observed, usage unknown |

**Gap class:** 424B5 is in the ledger and still not an ATM state machine. W4 must classify primary ATM supplement vs resale vs debt takedown from the document, not from the form number alone. GOOGL (`0001652044`, two 424B5, both pending) is the large-issuer analogue of the same gap.

### 16.3 Baby-shelf / I.B.6 candidate — QNCX (Quince Therapeutics)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0001662774` | Present |
| What changed | `registration_observed` | S-3 `0001193125-26-328769`, 2026-07-31, family `shelf`, subtype `registration_statement` |
| I.B.6 eligibility | — | **Unavailable** — no float, no 12-month primary sales, no listing/shell test |
| Remaining I.B.6 capacity | — | `calculation_refused` |
| First seen | 2026-08-01T15:38:11Z (early queue) vs filing 2026-07-31 | Horizon: this is near the current latest filing date, still not "today" |

**Gap class:** W4 encodes CFI 116.22/23/25/26 only when float + takedown history + primary vs resale are present; otherwise refused.

### 16.4 Warrant-heavy registration — WHK (WhiteHawk Income Corp)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0001921603` | Present |
| Authorization | S-1 `0001193125-26-215605`, 2026-05-11, `registration_observed` | One event |
| Evidence richness | **29 manifests** (1 complete, 1 primary, 1 filing_fee, **26 exhibits**) | Bytes retained |
| Instruments | — | Unavailable — exhibits not compiled to candidate terms in nightly |
| Overhang | — | Unavailable |

**Gap class:** the estate already paid to retain 26 exhibits. Nightly does not run `compile_capital_structure_instrument_candidate_terms`. W5 is compilation + resolver, not another collector.

### 16.5 Serial EFFECT / POS AM without a graph — LPTH (LightPath)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0000889971` | Present |
| Events | **44** classified (22 EFFECT + 22 POS AM complete submissions; 88 manifests) | Filing spam, not a lifecycle |
| Edges | Contributor to global **event_edges = 1** | `deferred_linkage` / missing exact linkage keys (review 44) |
| Latest | POS AM 2026-07-22 `0001437749-26-024176` | `post_effective_amendment_observed` repeated |
| Capacity / what is live | — | Cannot tell which statement is effective or remaining |

**Gap class:** this is the existence proof that event count ≠ twin. W4 lifecycle compiler + edges are the product; a longer EDGAR list is not.

JAGX (Jaguar Health, `0001585608`) is the toxic-financing *shape* analogue: EFFECT + EFFECT + S-1/A, review 3, still no instrument terms. Use JAGX in W5 toxic-term fixtures; do not label it toxic from the ticker.

### 16.6 Reverse-split / authorization vote / biotech-catalyst shape — EDBL (Edible Garden)

| Field | Freeze evidence | Twin section |
|---|---|---|
| Identity | `sec:cik:0001809750` | Present |
| Timeline | PRE 14A `authorization_or_vote_candidate` 2026-05-11 + S-3 `registration_observed` | Two families |
| Reverse split | PRE 14A observed | **Corporate-action effective date `NOT_BUILT`** — do not adjust O/S |
| Cash / catalyst funding | — | Unavailable |

**Gap class:** W6 must not treat proxy authorization as an effective split. W3 dossier shows "vote/authorization candidate" as a trigger, not as a completed capital action.

### 16.7 Cross-cutting identity gap

455 manifests carry ticker `?` (CIK-only). Identity resolution is a first-class twin field. Do not invent tickers. Join existing security-master planes; do not create a CS-only security master (`research/DO_NOT_REBUILD.md` sibling: stock-identity / security-master already exist).

---

## 17. Architecture freeze / no-rebuild boundaries

### 17.1 Preserve and extend

- Canonical SEC evidence store (content-addressed R2)
- Source manifests and exact receipts (after W1 `evidence_id` dual-read)
- Event spine and correction/PIT semantics
- Direct document-term ledger
- Instrument candidate-term **code and contracts** (wire; do not rewrite)
- Registration lifecycle **code and contracts** (wire in W4)
- Authenticated Company Facts / share-observation substrate (keep default-off until harness)
- Existing identity / security-master planes
- Existing auth
- Existing event/graph planes (CS change events are typed CS objects, not a new generic company-event bus)
- Existing R2 infrastructure (writable-store probe from #5792)
- Existing Capital Structure API and BioCatalyst PIT seam
- Existing Git publication plane (selector ruling in §9)
- Legacy `edgar_dilution` as shadow

### 17.2 Do not create

- Another SEC collector truth store
- Another share-count truth plane
- Another generic company-event namespace
- A BioCatalyst-specific capital ledger
- A Prophet-specific capital state
- Another auth layer
- Another lifecycle store (registration lifecycle compiler already exists)
- A new generic queue/control plane
- A new publication control plane
- `merge=union` on hash-bound `source_manifest.jsonl`
- Push-time content-aware merge of `source_manifest.jsonl` (Sol AMEND: withhold the coherent generation instead)
- A global `et_gate` collect mutex
- An opaque CS / dilution score
- Encoding Release 33-11418 as current law

### 17.3 Deterministic vs calculated vs model

| Class | Examples | Who may emit |
|---|---|---|
| Deterministic fact | Accession, form, EFFECT, content hash, fee-table cell, disclosed warrant count | Collector / term compiler |
| Deterministic calculation | I.B.6 remaining given float F and 12-month primary sales S; ATM remaining = program − disclosed usage | Capacity compiler with named inputs; refuse if any input missing |
| Scenario calculation | Shares from warrants if price = X | Instrument compiler; labeled scenario, not a forecast |
| Model-generated | 30-day offering probability; "toxic score" | **Forbidden** on product surfaces until a named feature survives the Prophet gauntlet. LLM may only narrate deterministic state |

---

## 18. Ordered vertical implementation waves

Not a 20-PR infrastructure staircase. Each wave ships an independently useful user or machine capability. **This PR is W0 only.**

| Wave | Capability it unlocks | Depends on |
|---|---|---|
| **W0** — this document | Architecture freeze for Sol/Chairman | — |
| **W1** — Evidence identity + whole-generation append-only fence | Same SEC occurrence cannot become two economic sources; interpretation correction cannot remint; overlapping CS jobs withhold rather than mix generations | W0 accepted |
| **W2** — Live-tail / recovery / historical split + horizon health | Today's material filings are not starved; health cannot call a July horizon "fresh" | W1 (do not scale retrieval on clocked IDs) |
| **W3** — Capital Changes Desk + Capital Twin UX | Discovery + issuer research on **honest states** from existing events/terms; no Loading hero | W1; W2 preferred for "today" but W3 can ship against an honest stale horizon |
| **W4** — Registration / capacity state | Authorization vs eligibility vs remaining capacity; EFFECT ≠ capacity; I.B.6/CFI/ATM/ELOC | W1; wire existing lifecycle compiler; primary-source rules §7 |
| **W5** — Instrument overhang | What existing securities can become supply; toxic terms as disclosed facts | W4 for registration status of instruments; nightly candidate terms |
| **W6** — Share basis + corporate actions + cash/funding | O/S/float/split basis; funding need; refuse without burn basis | Share-count v2 only after R2 harness; no second share plane |
| **W7** — Neural Web typed context + Prophet shadow features | NW consumes change events with fact IDs; Prophet features individually shadowed, `prophet_authority=false` | Deterministic families from W4–W6 |

W3 may start in parallel with W2 only if the desk labels horizon stale. W5 must not invent instruments from form numbers. W6 must not promote Company Facts to selected O/S while default-off. W7 must not ship a blended CS score.

---

## 19. First implementation handoff — Wave 1 only

**Do not execute this wave in the architecture session. Do not open a second PR for it until Sol/Chairman accept the amended W0.**

### 19.1 Mission

Make Capital Structure evidence identity lawful under `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` and overlapping CS publication lawful under `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE`, without rewriting historical `manifest_id`s, without a global daily.yml mutex, without `merge=union`, and without a push-time file merge of `source_manifest.jsonl`.

### 19.2 Why it matters

Live-tail (W2) will re-observe and race. Clocked `manifest_id`s remint economic sources. A post-compile merge of the source ledger would desynchronize events/terms/projection/health. Concurrent collect is a measured production shape. Identity plus whole-generation withhold is the prerequisite the AMEND selected.

### 19.3 Authority precedence

Same as §1. Identity: `DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES` (supersedes `DEC:CS-V2-IDENTITY-DUAL-READ`). Publication: `DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE` (supersedes `DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR`; Git selector restated). Fence law: `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE`. Union declined: `DSC:OVERLAPPING-DAILY-COLLECT-JOBS-LOSE-APPEND-ONLY-ROWS`.

### 19.4 Verified current state

- `manifest_id_for` hashes full body including required retrieval clocks (`source_identity.py:136-141`).
- `validate_manifest_ledger` hard-aborts same `manifest_id` with two bodies (`:154-170`).
- Collector sets `retrieved_at = first_seen_at = retained_at` wall clock after readback.
- Queue skip masks sequential remints; concurrent collect does not.
- `retrieval_attempts` columns: `attempt_id`, `accession`, `source_id`, `canonical_url`, `attempted_at`, `state`, `error`, `content_sha256`, `retrieval_lane`, `collection_scope`, `http_status`, `storage_operation`, `store_id`, `error_class`. No `evidence_id`; children have no attempt row.
- Collect unstages `data/capital_structure` (`daily.yml:649`); `push_append_only_fence` runs in collect (`:761`, `:787`) and **not** in the CS job (`:1332` `-X theirs` only).
- `config/append_only_artifacts.json` enrolls only `government-revenue`.
- Evidence bytes are already content-addressed and stable.

### 19.5 Exact scope

1. Derived `evidence_id` over occurrence + bytes. Dual-read validator: v1 `manifest_id_for` unchanged; `evidence_id` projected from row bytes. Do not subset-hash `manifest_id`.
2. Persist canonical `first_known_at` as the verified-retention clock of the first observation whose generation later became canonical. Git publication freezes that value; later observations do not move it backward. Do not call the stored timestamp a Git commit time (`DEC:CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK`).
3. Reuse `retrieval_attempts`. Add `observed_evidence_ids` and `retained_available_at` only as needed to represent successful re-observation, including children. No second observation artifact unless those additions fail.
4. Enroll a `capital-structure` family in `config/append_only_artifacts.json`. Member at minimum: `source_manifest.jsonl` `jsonl_prefix`. `withhold_paths`: `data/capital_structure`, `site/capital-structure-data`. Call `push_append_only_fence` from the **capital_structure** job push loop before `-X theirs`.
5. Hostile fixtures listed in the identity DEC.
6. Health: distinct **evidence count** vs **revision/manifest count** vs **observation count**. Idempotent re-observation must not revive the #5792 `selected>0 retained=0` false fail without a third progress term (`re_observed`).
7. Docs: contract amendment; this masterplan remains program of record.

### 19.6 Non-goals

- Live-tail / MAX_FILINGS / work-class split (W2)
- Page/API UX (W3)
- Capacity, instruments, share counts, cash (W4–W6)
- Neural Web / Prophet (W7)
- Global `daily.yml` concurrency rewrite
- Rewriting historical manifest IDs or PIT receipts
- `merge=union`
- Push-time content-aware merge of `source_manifest.jsonl`
- Moving publication off Git or inventing a second publication plane
- Enabling share-count publication
- Wiring instrument/lifecycle compilers
- Unconditional durable "1 evidence + 2 observations" as a W1 acceptance gate

### 19.7 User / machine journey

1. Night A retains occurrence X bytes B → `evidence_id` E, published `first_known_at` T0, observation O0, coherent CS generation G_A on Git.
2. Overlapping Night B retrieves the same occurrence. If publishing G_B would drop main's source-ledger evidence, **withhold G_B entirely**. R2 still holds B. Next run re-derives E, not a new id.
3. If Night B runs after G_A is on main and only re-observes: same E, same T0, new attempt row. PIT at T0 < t sees one source.
4. Parser later corrects file-number/issuer: same E, new `manifest_id` revision, `correction_available_at` is the correction clock.
5. Same bytes filed under two accessions remain two evidence ids.

### 19.8 Contracts

- Carry `evidence_id` (and child parent coordinates) on v2 rows so the key is checkable without R2. Do not invalidate v1 rows.
- Do not put retrieval clocks, file-number interpretation, ticker/aliases, parser version, issuer mapping, or storage namespace into the `evidence_id` preimage.
- Event compiler: historical `event_id`s unchanged (identity format 1, full-body hash). Post-W1 events stamp `version.identity_format: 2` and derive event-version identity from semantic state + `evidence_ids` + the correction chain, excluding `source.manifest_ids`, `evidence[].manifest_id`, and `point_in_time` clocks. Independent fresh compiles of the same occurrence+bytes+interpretation must share that post-W1 `event_id`.
- Closed bundle persist (`DEC:CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE`): re-observation appends zero rows; a revision appends the entire candidate bundle at the new accession-wide `document_version`, with every child pointing at the new complete-submission `manifest_id`. Classifier `changed` is diagnostic only.
- Queue receipt / health: evidence vs revision vs observation counts.

### 19.9 Time / null / correction

Four clocks, never collapsed: evidence identity (no clock); `attempted_at`; `retained_available_at`; canonical `first_known_at` (verified-retention clock frozen when that observation's generation becomes canonical — not a Git commit timestamp).
Corrections remain the event-spine path; W1 does not invent a new correction store.
Missing occurrence/byte fields fail closed (no evidence id), they do not mint a clocked id.

### 19.10 Deterministic / statistical / model boundaries

All W1 behavior is deterministic. No scores. No LLM. No capacity math.

### 19.11 Failure states

- Historical v1 row failing v1 hash → integrity error (unchanged).
- Proposed `evidence_id` that includes an excluded interpretation field → refuse (test).
- Same `evidence_id`, different retained bytes → new evidence linked by `correction_of`, never a silent rewrite.
- Multiple v1 `manifest_id`s for one occurrence → keep both v1 rows; project one `evidence_id`; do not delete.
- Proven drop of main's source-ledger evidence → withhold the whole CS family; do not publish a mixed generation.
- Push still losing to GH013 → warning already exists; W1 must not red the market plane.

### 19.12 Ordered build steps

1. Hostile fixtures (clocks, two accessions, two sequences, interpretation correction, submission+children, v1, multi-v1).
2. `evidence_id` function + dual-read validator. Leave `manifest_id_for` byte-identical.
3. Collector: compute `evidence_id`; skip remint; append observation on `retrieval_attempts`.
4. Freeze `first_known_at` only when the evidence is canonically published; never rewrite it backward.
5. Enroll CS family; wire `push_append_only_fence` in the CS job push loop.
6. Tests in 19.13.
7. Health counters including a re-observation progress term so idempotent nights do not look like #5792.
8. Contract + Agent OS update for W1 complete.
9. PR → CI → merge W1 only after W0 acceptance. **This architecture PR must not contain W1 code.**

### 19.13 Tests

- Same occurrence + bytes, two clocks → same `evidence_id`; published `first_known_at` frozen.
- Same bytes, two accessions → distinct `evidence_id`.
- Same bytes, two SGML sequences in one accession → distinct `evidence_id`.
- Corrected file-number/issuer/parser → same `evidence_id`, new `manifest_id`.
- Complete submission plus children → distinct ids; children carry parent coordinates.
- v1 golden rows still `validate_manifest_identity`.
- Re-observation does not increment unique evidence count.
- In-process keep-first may show one `evidence_id` from two mints; publication proof is one coherent generation (fence withhold), not a required pair of durable attempt rows.
- Event compiler: no second `event_id` for the same filing evidence.
- Health distinguishes evidence vs revisions vs observations.
- Regression: selected>0 retained=0 still fails when there is also no verified re-observation (#5792 must not regress).
- Fence fixture: a CS candidate that would drop main's `source_manifest.jsonl` prefix withholds `data/capital_structure` and `site/capital-structure-data`, not one file.

### 19.14 Production proof

After W1 merges and one CS job runs:

- Re-retrieve of an already-retained occurrence does not add a new `evidence_id`.
- Published `first_known_at` on that evidence is unchanged.
- Observation/attempt log can represent the recheck without a second observation plane.
- Unique evidence count does not jump by the remint.
- No rewrite of pre-W1 `manifest_id` strings in historical rows.
- CS family is enrolled; CS job calls the fence.

### 19.15 Stop condition

W1 is done when the proofs in 19.14 are true on production, tests in 19.13 are green on main, historical IDs are intact, and live-tail still has **not** started. Then stop and wait for the next authorized wave.

---

## 20. Acceptance / stop condition (this architecture session)

This AMEND session is complete when:

- [x] current main re-audited (`ad1aa0a4`; CS path empty vs Sol `71fbb0c`; press-wire only)
- [x] W1 uses the existing whole-generation append-only push fence rather than file-level merge (§9, §19)
- [x] evidence identity is correction-safe and occurrence-safe (§8)
- [x] Agent OS provenance is truthful (Cursor Grok 4.6 executor; COO Fable remains program owner)
- [x] no W1 production code exists
- [x] every meaningful existing CS component has a capability status (§4)
- [x] no duplicate canonical plane proposed (§17)
- [x] live-tail freshness architecturally separated from backlog (§12)
- [x] PIT/correction semantics exact (§10)
- [x] capacity ≠ expected supply ≠ actual issuance (§5, §11)
- [x] regulatory constraint logic has primary-source definitions (§7)
- [x] product supports discovery + issuer research, not ticker lookup alone (§13)
- [x] Neural Web has a typed context interface (§14)
- [x] Prophet remains non-authoritative with a promotion gauntlet (§15)
- [x] real-data examples demonstrate the architecture (§16)
- [x] first implementation wave bounded and independently useful (§19)

**Return PR #5901 green and STOP.** Do not start W1. Do not arm `merge-on-green`. Hand the PR back to Sol for architecture acceptance.

---

## 21. Agent OS citations minted with this PR

- `WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2`
- `DEC:CS-V2-EVIDENCE-IDENTITY-OCCURRENCE-BYTES` (supersedes `DEC:CS-V2-IDENTITY-DUAL-READ`)
- `DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE` (supersedes `DEC:CS-V2-GIT-REMAINS-GENERATION-SELECTOR`; Git selector restated)
- `DEC:CS-V2-LIVE-TAIL-SEPARATE-FROM-BACKLOG` (Sol-accepted; not reopened)
- `DEC:CS-V2-SIX-QUESTION-ONTOLOGY` (Sol-accepted; not reopened)
- `DSC:CS-MANIFEST-ID-HASHES-RETRIEVAL-CLOCKS`
- `DSC:CS-SOURCE-MANIFEST-UNSPECIFIED-MERGE` (so_what retargeted to the fence)
- `DSC:CS-THROUGHPUT-HEALTHY-HORIZON-STALE`
- `DSC:CS-INSTRUMENT-AND-LIFECYCLE-COMPILERS-NOT-NIGHTLY`
- `DSC:CS-EVENT-EDGES-NEAR-ZERO`
- `DEC:CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE`
- Handoff: `agentos/handoffs/CAPITAL-STRUCTURE-INTELLIGENCE-V2-2026-08-18.md`
- Standing law adopted: `DEC:APPEND-ONLY-BASE-FRESHNESS-IS-A-PUSH-PATH-FENCE`
