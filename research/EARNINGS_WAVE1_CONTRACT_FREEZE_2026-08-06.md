# Earnings / Company Event Suite — Wave 1 contract freeze and Wave 0 status ledger

**Status:** Wave 0 delivered; Wave 1 producer contract FROZEN as of 2026-08-06.

**Supersedes:** the immediate ordering in
[the remaining-build handoff](./EARNINGS_COMPANY_EVENT_SUITE_REMAINING_BUILD_HANDOFF_FOR_CLAUDE_2026-08-06.md)
§6 Wave 0 only. That handoff remains the execution sequence; the
[2026-08-01 architecture docket](./COMPANY_EVENT_INTELLIGENCE_SPINE_AND_PREMIUM_IR_SUITE_BUILD_DOCKET_2026-08-01.md)
remains architecture authority. This file exists because §9 of the handoff
requires the producer contract to be frozen **before** parallel builders start a
row, and the R0-D golden corpus surfaced five questions that were genuinely open.

---

## 1. Why this file exists

The corpus is a benchmark. A benchmark is only meaningful against a fixed
contract, and building it exposed five places where the existing estate has two
answers. Each is adjudicated below with the docket section that decides it.

**None of these are new architecture.** In four of five cases the 2026-08-01
docket already fixes the answer and the shipped code simply diverges from it.
That is the finding: Wave 1 is an adapter-and-conformance job, not a design job.

---

## 2. The five frozen answers

### Q1 — Canonical identity is ISSUER-keyed, not listing-keyed

**Frozen: `(issuer_id, fiscal_year, fiscal_quarter)`.**

Docket §4.2 already rules this and the shipped code contradicts it:

| Docket §4.2 rule | Shipped behavior |
|---|---|
| 1. `company_id` identifies the legal issuer | — |
| 2. `security_id` identifies a listed security or share class | — |
| 3. **`ticker` is an alias with `valid_from`/`valid_to`, never a durable key** | both schemes key on ticker |
| 4. Dual classes (GOOG/GOOGL) share an issuer, remain distinct securities | mint two event ids |
| 6. **Events attach to the reporting entity**; market reactions attach to securities | events attach to the listing |

`stable_event_id` (`engine/company_intelligence/contracts.py:214-223`) hashes
`f"{ticker}|{year}|Q{quarter}"`, and `event_key`
(`engine/earnings_narrative/contracts.py:265-266`) is `f"{ticker}/{transcript_id}"`.
Both start from the ticker, so one issuer event under two listings mints two
logical events.

The corpus makes this measurable rather than arguable: **36 cases** (`share_class`
16 + `dual_listing` 20) span sibling symbols, and a test proves they do. Under
listing-keying those 36 inflate issuer coverage and theme breadth **by
construction** — which the handoff §Wave 1 acceptance forbids in as many words
("issuer/listing/share-class mapping cannot inflate coverage or theme breadth").

**What Wave 1A builds:** a canonical `company_event.v1` keyed on
`(company_id, fiscal_period)` per docket §4.4, plus a **bidirectional adapter** to
both existing ids. Old immutable objects are not rewritten — that is explicit in
handoff §Wave 1.3. `cie_…` and `TICKER/2026Q1` become *aliases* that resolve to
one canonical event.

**Correction-stability is already free.** `stable_event_id` deliberately excludes
`call_date` from its hash, so a provider re-dating a call does not fork identity.
Preserve that property; the corpus pins it by re-minting every id with
`call_date="1999-01-01"` and asserting no change.

### Q2 — Canonical filing key is `(cik, accession)`

**Frozen: `(cik, accession)`.** The corpus's position is adopted.

The two EDGAR readers today share **exactly `{ticker}`** — computed by the corpus
replay suite, not asserted from prose:

| Reader | Captures | Missing |
|---|---|---|
| `collectors/edgar_earnings_8k.py:242-248` | `ticker, cik, filing_date, acceptance_datetime, items` | **no accession at all** |
| `engine/marketing/edgar_earnings_wire.py:148-159` | `cik, accession` internally; emits `id=f"{ticker}-{accession}"`, `accession` | **emits no cik**, no `filing_date`, and `when` is wall-clock-at-processing, not a source timestamp |

Neither field set is a superset of the other, so the two planes cannot be joined
today at all.

**What Wave 1B builds:** extend `edgar_earnings_8k` to capture `accessionNumber`
— SEC's submissions JSON already exposes it parallel-array-indexed with
`form`/`filingDate`/`acceptanceDateTime`/`items`, and
`edgar_earnings_wire.py:899` already reads that exact field name when confirming
Item 2.02, so the shape is proven. Extend `edgar_earnings_wire` to emit `cik` and
a **source** acceptance timestamp.

**Do not** join on `(cik, filing_date)` with a tolerance window. The handoff's
acceptance requires "availability timestamps prove no consumer outran the source";
a fuzzy date join cannot support that claim, and amendments would collapse into
their originals.

### Q3 — Per-claim receipts; the event-level flag becomes DERIVED

**Frozen: per-claim.** `claim_citations_pending` stops being a stored assertion
and becomes a computed property of the claim set.

Docket §4.1 defines `event_claim.v1` as carrying its own `evidence_spans`, and
§4.5 states the rule plainly: the span is the fundamental receipt, and *every*
citation — article, Brain answer, topic cluster, relationship edge, guidance
comparison — must resolve through it. A single event-level boolean cannot express
"nine claims cited, one not".

Today it is a hard v1 invariant: `validate_context` raises unless it is exactly
`True` (`engine/company_intelligence/contracts.py:501-502`), set literally at
`views.py:461`. **v1 is not to be changed** — the corpus pins that invariant, and
a v1 context with `False` must still raise.

**What Wave 1C builds:** a v2 projection where each claim carries either an exact
receipt or a **typed absence**, and the event-level field is derived
(`pending == any(claim has no receipt)`). Handoff §Wave 1.8 is explicit that
document-level lineage must not be silently upgraded to span-level — a typed
absence is the compliant answer, not a fabricated receipt.

The corpus commits an `expected_v2_outcome` per case, and its distribution is the
grading key: `exact_receipt` 155, `typed_absence` 49, `duplicate_collapsed` 16,
`quarantined` 14. **49 typed absences is the number that matters** — if a Wave 1
implementation resolves materially more than 155 to `exact_receipt`, it is
manufacturing citations.

### Q4 — The fiscal label belongs to the EVENT

**Frozen: event.** Docket §4.4 places `fiscal_period` on the `company_event.v1`
envelope, alongside `company_id` and the `security_ids` list.

This follows from Q1: if events attach to the reporting entity (§4.2 rule 6), the
fiscal period is a property of that entity's reporting calendar, not of any one
listing's presentation of it. A dual-listed issuer publishing under two calendars
is a **document-level** presentation difference — the document revision records
which calendar it presented, the event keeps one fiscal identity.

The alternative fails Q1: per-document fiscal labels reintroduce two events for
one issuer quarter through the back door.

### Q5 — `corporate_intelligence_health.v1` is the typed enum; the rest get adapters

**Frozen target vocabulary** (docket §4.1 `corporate_intelligence_health.v1`,
handoff §Wave 7 operational acceptance):

```
ready | degraded | stale | partial | blocked_rights | empty
```

Five inline vocabularies exist today, none of them a shared enum — every one is a
repeated set-literal, which is why they drifted:

| Vocabulary | Values | Defined at |
|---|---|---|
| context `status` | ready, partial, stale, not_covered | `contracts.py:432` |
| manifest `status` | ready, degraded, empty | `contracts.py:623` |
| per-source `status` | present, metadata_only, missing | `contracts.py:338` |
| `source_completeness` block | present, metadata_only, missing, partial | `contracts.py:557` |
| health-replay `status` | empty, degraded, ready | `health.py:99,103,136-139` |

**Two of these are not status vocabularies at all.** Per-source and
`source_completeness` describe *source presence*, which is an orthogonal axis —
an event can be `ready` with a `missing` transcript. Those two stay as they are
and are **not** merged into the enum. Only the three genuine status vocabularies
(context, manifest, health-replay) converge.

`not_covered` maps to `empty`. `blocked_rights` **does not exist in code today** —
it is a Wave 7 value and must not be minted before there is a rights check that
can actually return it; a status value no code path can produce is a lie in a
dropdown.

---

## 3. Wave 0 status ledger

| Lane | PR | State |
|---|---|---|
| base — heal both `ci-pack-2` reds pinning the fleet | [#4774](https://github.com/chriswong6031-creator/macro/pull/4774) | open; proof run dispatched |
| R0-A — Qwen model alignment, preflight, fallback disclosure | [#4778](https://github.com/chriswong6031-creator/macro/pull/4778) | open, armed |
| R0-A2 — per-rung prompt bound for the 4096-token local window | [#4784](https://github.com/chriswong6031-creator/macro/pull/4784) | open, armed |
| R0-B — EDGAR sparse-checkout cone + attributable zero-emission | [#4780](https://github.com/chriswong6031-creator/macro/pull/4780) | open, armed |
| R0-C — sever the Prophet earnings split-brain, disclose the starved arm | [#4781](https://github.com/chriswong6031-creator/macro/pull/4781) | open, armed |
| R0-D — golden corpus (130 issuers / 234 difficult events / 17 classes) | [#4783](https://github.com/chriswong6031-creator/macro/pull/4783) | open, armed |
| ruling — freeze the PSQ hold-tilt promotion clock | [#4785](https://github.com/chriswong6031-creator/macro/pull/4785) | open, armed |

### Findings Wave 0 produced that no handoff predicted

1. **The local LLM context window is 4096 tokens**, and production sends ~24,000-char
   prompts. Over the limit the endpoint returns HTTP 200, `finish_reason: stop`, and
   **prose instead of JSON** — so R0-A's model-ID fix alone would still have sent every
   real transcript to DeepSeek. The binding constraint is `prompt + completion ≤ 4096`.
   Measured density varies ~1.4× between two samples of ordinary English (2.97 vs 4.19
   chars/token), so the bound is set at 8000 chars with headroom rather than tuned to the
   edge. The higher-quality fix — raising the server's `num_ctx` — is operator-only.
2. **The PSQ hold-tilt promotion is unfalsifiable, not merely unmet.** Its EC input is
   gitignored and absent on every deploy, so the leash has been pinned at 1.0 since it
   shipped and `_stage_tilt_demoted` (`engine/prophet_bridge.py:1538`) can never reach its
   `n_matured >= 30` floor. Frozen by `DNR:HOLD-PSQ-TILT-CLOCK`.
3. **`tests/test_prophet_stage_shadow.py` was strictly dark** — named by no `run:` step and
   matched by no path glob. It was the only guard on the forward shadow that arms that
   auto-demote clause. Now wired in both halves.
4. **A zero-emission marketing pass could not name its cause.** With zero candidates in the
   window the fail-closed skip record is never created, so `emitted=0 skipped=0
   quarantined=0` is byte-identical to a quiet reporting hour. Counting skips could never
   have carried the answer; universe state is now reported unconditionally.

---

## 4. Standing constraints for every Wave 1 builder

- **CI is an explicit namelist, not a glob.** A suite must be named in a
  `run: python -m pytest …` line in `.github/ci/legacy-jobs.yml` **and** its path
  matched by a glob in `.github/workflows/ci.yml`'s `on.pull_request.paths`.
  `tests/**` is deliberately not a catch-all. Both halves, every time — Wave 0
  found one strictly-dark suite guarding a promoted signal's falsifier.
- **Do not rewrite old immutable objects.** Adapters and a versioned convergence
  layer only (handoff §Wave 1.3).
- **A number without basis, units, period, and source is ABSENT, not guessed**
  (handoff §Wave 1.5). The corpus's 49 typed absences are the floor.
- **All Wave 1 output stays `context_only`.** No rank, size, gate, or escalation.
- **Zero new provider/model calls for unchanged document hashes** (handoff §Wave 1
  acceptance) — the corpus's per-fixture sha256 map is the mechanism.
