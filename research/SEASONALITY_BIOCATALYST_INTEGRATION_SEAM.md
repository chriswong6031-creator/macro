# Seasonality ⇄ BioCatalyst integration seam

**Status:** binding cross-program contract. Written 2026-08-01 in the Fable main
loop while both programs were mid-build, so neither side builds the other's thing.

**Programs.** `biopharma-seasonality-intelligence` (docket:
`SEASONAX_BIOPHARMA_SEASONALITY_INTELLIGENCE_BUILD_DOCKET_FOR_FABLE.md`) and
`biocatalyst-intelligence` (docket:
`BIOCATALYST_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md`,
§17 one-writer table).

---

## 1. Why this file exists

The seasonality program's **Clock 2 (biopharma catalyst time)** needs exactly the
object the BioCatalyst program is built to own: a bitemporal trial / regulatory
event with revision lineage and source provenance. Without a written seam, the
predictable failure is a second ClinicalTrials.gov collector — the specific thing
BioCatalyst §17.5 forbids ("No team creates a second writer because an upstream
contract is temporarily inconvenient").

The BioCatalyst one-writer table does not currently carry a row for the
seasonality program. §3 supplies the rows it should carry.

## 2. The good news: the two contracts already agree

Both programs converged independently on the same bitemporal discipline — an
`effective_at` for when a fact applies and a separate system-knowledge time that
can never precede ingestion. That makes the seam an adapter, not a redesign.

| `biopharma.event.v1` (`engine/seasonality/contracts.py`) | `BioCatalyst Trial Read Snapshot v1` (`contracts/biocatalyst/trial_snapshot.v1.schema.json`) |
|---|---|
| `event_id` | `snapshot_id` |
| `nct_id` | `nct_id` |
| `published_at` | `source_published_at` |
| `ingested_at` | `retrieved_at` |
| `known_at` | **`transaction_from`** — see §2.1 |
| `effective_at` | `source_effective_at` |
| `source_hash` | `canonical_content_sha256`, re-prefixed `sha256:` |
| `source_url` / `source_class` | resolved through `source_snapshot_ref` + `source_attribution` |
| `certainty` / `status` | `confidence`, `contradiction_state`, `coverage_class` |

### 2.1 The one real mismatch — do not paper over it

`biopharma.event.v1` enforces `ingested_at >= published_at` **and**
`known_at >= ingested_at`, fail-closed. The tempting mapping
`known_at ← knowledge_cutoff` **breaks this**: `knowledge_cutoff` describes the
source dataset's own cutoff, which routinely precedes our retrieval. Use
`transaction_from` (when the row entered our system), which is monotone with
respect to retrieval by construction.

The adapter **asserts** the invariant and **quarantines** a violating row with a
structured gap. It must never clamp, swap, or back-date a timestamp to make a row
validate — doing so manufactures exactly the leakage the contract exists to catch.

## 3. Ownership rows to add to the BioCatalyst §17.5 one-writer table

| Object / write lane | Canonical owner |
|---|---|
| Calendar-clock year panel, canonical seasonal curve, window family + selection-corrected statistics | Seasonality |
| `site/seasonalitydata/**` public artifacts and the seasonality methodology manifest | Seasonality |
| `neuralweb.biopharma_seasonality_state.v1` emission, and the seasonality forward outcome ledger | Seasonality |
| The read-side projection of BioCatalyst objects into `biopharma.event.v1` | Seasonality (consumer-side adapter, §4) |
| Trial / endpoint / site snapshot, regulatory application, catalyst date | **BioCatalyst** (unchanged) |
| ClinicalTrials.gov / AACT / FDA-family raw acquisition | **BioCatalyst** (unchanged) |
| Clinical forecast, comparable set, outcome label | **BioCatalyst** (unchanged) |

**Seasonality creates no security master.** Its Lane 1 price panel *reads*
`data/yahoo/*.parquet` and `data/universe/membership.parquet`; it writes no
security identity and no corporate action. That lane stays owned by the Market
Data / security-master registration pending in BioCatalyst B0.

## 4. The adapter, and why the consumer owns it

`engine/seasonality/event_clock.py` (unbuilt) will carry a thin adapter that reads
**only BioCatalyst's published contract files** under `contracts/biocatalyst/` and
its registered artifacts — never its internals, never its database, never its
collectors. Consumer-side ownership is deliberate: it lets BioCatalyst evolve its
internal representation freely, and it keeps the projection's failure modes inside
the program that depends on them.

Rules:

- read published artifacts through the synapse registry, declaring itself as a
  `consumers:` entry (enforced by `tests/test_synapse_read_gate.py`);
- validate every projected row with `validate_bitemporal_event`; quarantine, never
  coerce;
- an unresolved entity or a date conflict **abstains** — it does not guess;
- no causal wording: event-time association is "historically associated" unless a
  stronger design supports more.

## 5. What each side must not do

**Seasonality must not:** collect ClinicalTrials.gov, FDA, or AACT data; create a
second trial/catalyst store; assign clinical outcome labels; publish a probability
of approval; write into any `biocatalyst.*` path, `engine/biocatalyst/`,
`collectors/biocatalyst/`, `contracts/biocatalyst/`, or `config/biocatalyst_*.yml`.

**BioCatalyst must not:** build a calendar-seasonality engine, a seasonal curve,
or a window scanner; publish selection-corrected calendar statistics; write into
`engine/seasonality/` or `site/seasonalitydata/`.

**Neither may:** grant the other authority it has not separately earned. The
seasonality program's birth authority is fixed in code at `tier=shadow`,
`is_context_only=true` with every other authority boolean false
(`engine/seasonality/contracts.py`). Consuming a BioCatalyst event does not raise
it, and a BioCatalyst promotion does not travel to seasonality by adjacency.

## 6. Sequencing — what unblocks what

The calendar clock is **not** blocked on BioCatalyst. It runs on price history
alone and ships independently; that is why it is the first user-facing tranche.

The event clock is blocked, in this order:

1. BioCatalyst publishes a **registered, non-fixture** trial/catalyst artifact
   with real coverage (its B1/B1b lanes are the current work; the store on disk
   today is bounded synthetic fixtures);
2. seasonality builds the §4 adapter against that artifact and proves the §2.1
   invariant holds on real rows, with a quarantine count published, not hidden;
3. only then does event-relative statistics work begin (docket Lane 4), and only
   then can an event window claim an evidence tier.

A forward PDUFA / advisory-committee calendar remains absent repo-wide
(`engine/event_landmine.py` explicitly declines to carry one). Until BioCatalyst
supplies it, seasonality's event conditioning is limited to known-at-the-time
ClinicalTrials events, observed Phase-3 starts/halts, openFDA approvals and label
changes, and earnings — and the product says so rather than implying coverage it
does not have.

## 7. Shared surfaces to coordinate, not duplicate

Both programs touch `config/site_access.yml` and `app/deploy/Caddyfile` (the
default-deny serving boundary) and `config/synapse.yml` + `docs/SIGNAL_BUS.md`
(artifact registration). These are append-shaped files: conflicts are textual, not
semantic, and are resolved by keeping **both** programs' entries. Rebase on fresh
`origin/main` before merging rather than assuming a stale base is current.
