# Research Vault — masterplan (RV W0)

Status: CHARTERED (operator intake 2026-07-22). Product owner: operator.
Working name: **Research Vault** (page `research_vault.html`; ZH 研报库). Slug/namespace:
`research_vault` everywhere (avoids the taken `research/` build-dir, the internal
`research_factory` pipeline, the `reports.html` blog, and `about-research.html`).

## 1. What this is

A gated vault + feed of third-party buy-side / sell-side research PDFs. PDFs arrive
~hourly from an upstream engine, are ingested, indexed (full-text), and hosted behind a
beautiful in-browser viewer. Public visitors browse a teaser list (our title + point-form
summary + institution + date); paid subscribers view PDFs and download a metered number
per day. A **Latest** feed and an editorially-highlighted **Top Picks** rail.

This is a **display-tier content surface**. It ships NO signals, scores, escalations, or
allocations — the gauntlet/epistemics promotion law does not apply. It DOES obey: the
`validated`-word ban (CI-enforced), the user-first design doctrine, bilingual EN/ZH, and
the paywall/quota entitlement law (server enforces; client chrome is decorative).

The `validated`-word ban binds **our copy, not the notes we mirror** (amended 2026-07-27,
#3770). BC-2 governs what the platform asserts; reported speech from a named external
author has no artifact of ours to cite — "the June CPI print validated two likely sources
of ongoing disinflation" is ordinary economics English. The third-party text *sinks* on
`site/research/*.html`, `site/research/index.html` and the baked catalog in
`site/research_vault.html` are therefore skipped structurally by `_THIRD_PARTY_PAGES` in
`scripts/check_validated_claims.py`; every platform-authored string on those pages lives
in `templates/research_*.j2`, which stays scanned with no exemption. If a mirrored quote
ever reds the gate, the sink is unmapped — extend `_THIRD_PARTY_PAGES` (and
`tests/test_validated_claims_thirdparty.py`), never the allowlist. Precipitating incident:
the 2026-07-27 nightly render red-lined main and every open PR's ci-pack-0.

**Operator/legal note:** distribution rights for third-party research are an operator/legal
responsibility. This system enforces *access control* (who may view/download, how many per
day) and *traceability* (per-user watermark); it does not adjudicate redistribution rights.

## 2. Resolved product decisions (operator, 2026-07-22)

| Fork | Decision |
|---|---|
| Anti-scrape | **Private stream + gated download.** Source PDFs in a PRIVATE R2 bucket (no public URL). Viewer streams bytes only through an authenticated, rate-limited API route. Download is a SEPARATE route enforcing the daily quota + per-user watermark + `Content-Disposition: attachment`. Kills the public-blob bypass; makes scraping authenticated, rate-limited, and traceable. (Honest limit: an in-browser viewer must receive renderable bytes, so a determined viewer can still save what they view — the DocSend-style page-image upgrade in §12 removes even that, and is the documented fast-follow.) |
| Access | **Public teaser list, paid viewing.** Anyone (incl. logged-out) sees Latest + Top Picks with our title + summary + institution + date (funnel/SEO). Opening the viewer OR downloading requires an active paid plan. |
| Downloads | ~~**5/day** for `insider` ("Normal paid") · **20/day** for `pro`.~~ `free`/anon = 0 (view+download blocked). **AS SHIPPED (W2) + AMENDED 2026-07-26:** reading is PRO-only, so `insider` = 0 (browse-and-teaser tier) · `pro` = **10/day** · `pro` on a **lifetime grant** (comp row, no period end) = **50/day**. `engine/research_vault/download_quota.py` `LIMITS`/`LIFETIME_LIMITS` are the source of truth. |
| Ingestion | **R2 dropzone + JSON sidecar** (§5). No Dropbox (none exists; would be net-new SDK+OAuth — deferred adapter). |

## 3. Architecture (data flow)

```
upstream engine ──drops──▶  R2 inbox (private)         hourly GHA job          macro-api (VPS, FastAPI)
  <id>.pdf + <id>.json      research_inbox/            scripts.ingest_research   app/research.py router
                                     │                       │                         │
                                     ▼                       ▼                         ▼
                        (1) list new objects   (2) extract text (pdftotext)   PUBLIC (unauth, TTL-cached from R2):
                                                (3) normalize sidecar           GET /api/research/catalog
                                                (4) promote PDF ──▶ R2 vault    GET /api/research/search   (FTS body/title/summary)
                                                    (PRIVATE bucket, creds)     PAID (auth + plan):
                                                (5) upsert catalog.json ─▶ R2   GET /api/research/view/{id}      (stream, inline, rate-limited)
                                                (6) upsert corpus.sqlite ─▶ R2  POST /api/research/download/{id} (quota 5/20 + watermark + attachment)
                                                                                GET  /api/research/quota         (remaining today)
        nightly render ──bakes──▶ research_vault.html (SSR teaser list for SEO + instant paint)
                                   client hydrates the live catalog on load (hourly-fresh Latest/Top Picks)
```

Two machines: ingestion runs on GitHub Actions (self-hosted Mac Studio); the API runs on
the VPS. They communicate only through R2. The API reads private objects server-side via
boto3 GET with credentials — never a public URL.

## 4. Storage layout

**R2 — private bucket `mastermindx-research`** (operator creates; no public/r2.dev binding;
reuses the existing account access key via env `R2_RESEARCH_BUCKET`):
- `research_inbox/<id>.pdf` + `research_inbox/<id>.json` — the dropzone the upstream writes to.
- `research_inbox/top_picks/…` — OPTIONAL alternative top-pick routing (sidecar `top_pick:true` is the primary signal; a `top_picks/` subfolder is also honored).
- `research_vault/<id>.pdf` — promoted canonical source PDF (served only via the gated API).
- `research_vault/catalog.json` — the list metadata (public-safe fields; §6).
- `research_vault/corpus.sqlite` — FTS5 search index (title+summary+body; §8).
- `research_inbox/_processed/<id>.json` — ingest receipts (idempotency; move-after-process).

**Repo (git-tracked):**
- `data/research_vault/catalog.json` — last-published catalog snapshot (committed by the ingest job's push lane) so the nightly render can SSR-bake without R2 at render time.
- `engine/research_vault/…` — pure engine (ingest, sidecar schema, corpus builder, watermark).
- `scripts/build_research_vault.py`, `scripts/ingest_research.py` — CLI entrypoints.
- `templates/research_vault.html.j2`, `site/research_vault.html` — the page.
- `app/research.py` — the FastAPI router.

**API VPS state:** `/var/lib/macro-api/research_download_quota/dl_{uid}_{YYYY-MM-DD}.json`
(mirrors the brain quota ledger dir).

## 5. Sidecar metadata contract — `research_vault.sidecar.v1`  ⟵ DELIVERABLE for the other engine

Each PDF `<id>.pdf` dropped in `research_inbox/` is accompanied by `<id>.json`:

```json
{
  "schema": "research_vault.sidecar.v1",
  "id": "bernstein-2026-07-21-dc-pipeline",
  "title": "Data Center Pipeline Probabilities — Separating credible developers from PowerPoints",
  "institution": "Bernstein",
  "desk": "Data Centers",
  "side": "sell",
  "published_at": "2026-07-21T14:00:00Z",
  "summary_points": [
    "Only 33% (135GW) of the 500GW nameplate pipeline is credible.",
    "Hyperscalers control 42% of credible capacity; top-10 developers hold 60%.",
    "Texas dominates the pipeline (93GW) but completes only 29% vs Louisiana 88%."
  ],
  "tags": ["ai", "datacenters", "capex"],
  "tickers": ["EQIX", "DLR"],
  "top_pick": true,
  "pages": 12,
  "language": "en",
  "source_filename": "bernstein_dc_pipeline.pdf"
}
```

Field rules (the ingester is defensive — every field except the PDF itself has a fallback):
- `id` — optional; if absent, derived as `slug(institution)-YYYY-MM-DD-slug(title)[:40]` and de-duplicated.
- `title` — REQUIRED for a good row; falls back to the PDF's embedded title, then the filename.
- `institution` — REQUIRED for the facet; falls back to `"Unknown"` (flagged for backfill).
- `side` — `buy` | `sell` | `independent`; default `sell`.
- `published_at` — ISO-8601; falls back to the object's R2 upload time.
- `summary_points` — array of 3–8 short bullets; falls back to `[]` (row shows "Summary pending"). **The fallback is provisional, not a verdict — see §5c.**
- `top_pick` — boolean; also settable via the `top_picks/` subfolder. Editorial highlight of the REPORT (not a trade recommendation) — copy must never imply investment advice.
- `tags`, `tickers`, `desk`, `pages`, `language`, `source_filename` — optional.

Unknown fields are preserved but ignored. A sidecar that fails JSON parse → the PDF is still
ingested with all-fallback metadata and flagged `needs_metadata:true` (never dropped).

### 5b. Engine-MEASURED metadata (RV W1-A, added 2026-07-26) — `engine/research_vault/probe.py`

The sidecar is a set of upstream **claims**. Anything we can compute from the bytes we are
already holding is a **measurement**, and a measurement wins. Audit that motivated this:
across the first 60 ingested documents, `pages`, `desk`, `tags` and `tickers` were empty on
**every single row** — `pages` because the ingester only ever read `sidecar.pages` while the
PDF sat in memory beside it, and the other three because the upstream never sends them.
`needs_metadata` reported 0/60 throughout, because it only inspects title/institution/bad-JSON.

| field | source | notes |
|---|---|---|
| `pages` | pypdf → poppler `pdfinfo` | **overrides** `sidecar.pages`; falls back to the claim only when unmeasurable |
| `content_sha256`, `byte_size` | `hashlib`/`len` | always available; duplicate EVIDENCE (see below) |
| `char_count`, `word_count` | `pdftotext` output | depth proxies |
| `text_layer` | derived | `full` / `thin` / `none` / `unavailable` — see the four-state rule below |
| `pdf_creator`, `pdf_producer` | Info dict | publishing-house fingerprint; useful when `institution` fell back to `Unknown` |
| `pdf_created_at`, `pdf_modified_at` | Info dict, ISO-8601 | an INDEPENDENT check on `published_at`, which otherwise silently falls back to the R2 upload time |

Rules that are load-bearing, not stylistic:

- **Unknown is `None`/`''`, never `0`.** A null page count must not read as a zero-page document.
- **`text_layer` keeps four states.** `unavailable` means `pdftotext` is missing or crashed (a
  HOST fault — install poppler); `none` means the extractor ran and found nothing (an
  image-only PDF, invisible to body search); `thin` is below readable density; `full` is a real
  text layer. `extract_pdf_text() or ""` at the call site collapses the first two, which would
  hide a broken runner behind a plausible-looking document property.
- **`content_sha256` is evidence, NOT a gate.** Idempotency keys on the source object key, so
  the same report re-dropped under a different filename is a new object and gets its own row.
  We report the collision and ingest both — skipping on a hash match would freeze the
  original bad metadata forever, since receipts make re-ingestion the only repair path.
- **The hourly lane installs only `boto3 pyyaml`,** so pypdf (a soft dep declared for the
  download watermark) is ABSENT in production and the `pdfinfo` rung is the one that actually
  runs. Both rungs are covered by tests against a real PDF; they must agree on the page count.
- **`first_page_text` is deliberately NOT stored.** `body` is truncated at the tail, so page 1
  is always inside the row we already keep; downstream extractors read it via
  `probe.first_page(body)`. A column would duplicate ~4KB per row in a file the API pulls
  whole on every corpus refresh.
- **`language` is NOT a measurement.** `sidecar.normalize` defaults it to `"en"`, so it is a
  declared field carried through to the catalog — excluded from the coverage report below
  precisely because it would always read 100%. Measuring the script from the body text is a
  follow-on, not a claim we make today.

### 5c. The sidecar is written in TWO PHASES — re-read it (RV W1-B, added 2026-07-28)

The upstream desk writes the sidecar's **identity** fields (`title`, `institution`, `side`,
`published_at`) when the PDF lands, then fills `summary_points` once its summarizer finishes.
The hourly cron routinely reads the object *between* the two writes. Because ingest is
receipt-idempotent, whichever phase we happened to catch was then frozen **forever**.

Audit that motivated this — replaying the catalog's own git history across 74 hourly snapshots:

| | |
|---|---|
| rows stuck on `summary_points: []` | **63 of 236** (the public "Summary pending") |
| transitions `[] → filled`, ever | **0** |
| fill rate by batch | 07-24 `50/50` · 07-26 `53/56` · 07-27 06:54 `5/14` · 07-27 17:54 `3/23` |

The last batch was uploaded 00:44–00:48 UTC and ingested at 00:54 — three of twenty-three had
been summarized by then. Freshness, not document quality, predicted the hole.

`ingest._refresh_sidecars` closes it: each run re-reads the sidecar of any catalog row still
missing `summary_points` / `tags` / `tickers` / `desk` and folds in what has since arrived.

Rules that are load-bearing, not stylistic:

- **Fill-only, never overwrite.** A field we already hold is left exactly as it is, so the
  pass can only ADD information. That is what makes it safe hourly and idempotent.
- **Candidacy keys on `summary_points` ALONE, not on all four fields.** `desk`/`tags`/
  `tickers` are empty on EVERY document because no producer writes them (§6b exists to report
  exactly that), so an all-fields gate is never satisfied — every in-window row would be
  re-fetched every hour forever, ~236 wasted GETs/hour, the opposite of a self-quiescing
  pass. `summary_points` is the one field with a real producer and so the only honest
  liveness signal; the other three are still filled opportunistically when a fetch happens,
  they just cannot keep a row alive.
- **The pass runs AFTER the ingest loop.** `upsert_item` does a whole-ROW replace, so a
  report re-dropped under a second filename carrying the SAME explicit sidecar `id` would
  overwrite a just-recovered summary with that second sidecar's still-empty one — shipping
  "Summary pending" while the run reported `summaries_recovered=1`, and flapping hourly.
- **Dates are parsed, not sliced.** A bare `[:10]` on a non-ISO `"07/28/2026"` sorts below
  any `2026-…` cutoff and would silently exclude that row from every future refresh;
  `sidecar.date_part` returns `''` instead, and an unusable date is treated as IN scope.
  A cap likewise sorts undated rows FIRST — `_reindex` puts them last, and they are exactly
  the half-written rows this pass exists for.
- **Identity and measured fields are out of scope.** `title` has by then been through
  `title.resolve` + `_repair_titles` and must never regress to the raw sidecar string;
  `pages` is MEASURED (§5b) and outranks the claim; `published_at` must never move under a
  published row.
- **`normalize()` is called for its COERCION only** — bullet clamp, ticker upper-casing,
  non-string drops. Every field it invents outside the four is discarded.
- **Bounded by age, not just by count.** A sidecar still empty after `REFRESH_LOOKBACK_DAYS`
  (14) was never summarized upstream rather than raced; polling it hourly forever would grow
  per-run GETs without bound as the vault does. `REFRESH_MAX` (500) is the second bound, and
  a cap that bites prints a `::warning` — a silent truncation would read as full coverage.
- **The `{doc_id → pdf_key}` map comes from the receipts**, which `_processed_index` was
  already reading in full, so the pass costs no extra listing. The public catalog carries no
  source key; the receipt is the only way back from a row to its inbox object.
- **The coverage tripwire (§6b) stays the standing check.** This pass makes `summary_points`
  recoverable; it does not make `tags`/`tickers` appear if no producer ever writes them.
- **`_resync_corpus_summaries` closes the skew the refresh would otherwise make permanent.**
  `run()` writes the catalog BEFORE it publishes the corpus, so a failed publish strands
  bullets in the catalog with a blank corpus `summary` — and that row is no longer a refresh
  candidate, so search would rank it on stale text forever. The resync is local-only (one
  query, no store reads), runs every pass, and warns when it finds anything: a non-zero count
  means a PREVIOUS run's corpus publish did not land.

## 6. Catalog schema — `research_vault/catalog.json` (public-safe)

```json
{ "schema": "research_vault.catalog.v1", "generated_at": "…",
  "count": 128, "institutions": ["Bernstein","Goldman Sachs", …],
  "items": [
    { "id": "...", "title": "...", "institution": "Bernstein", "side": "sell",
      "desk": "Data Centers", "published_at": "...", "summary_points": [...],
      "tags": [...], "tickers": [...], "top_pick": true, "pages": 12,
      "language": "en", "needs_metadata": false } , … ] }
```
Body text is NOT in the catalog (search-only, §8). Items are sorted newest-first. `top_pick`
items also power the Top Picks rail. This file is the ONLY research artifact that carries
publicly-visible content; the PDFs themselves are never public.

The item field list is declared in `engine/research_vault/catalog.py::_ITEM_FIELDS` and
MIRRORED in `scripts/build_research_vault.py` (the SSR bake projects its own copy) — a test
asserts the two tuples stay identical. Only public-safe fields belong here: the measured
technical facts of §5b (hash, byte size, producer strings, text-layer state) live in the
corpus, which is server-side, not in the catalog, which is the one public artifact.

### 6b. Coverage tripwire — `catalog.coverage()`

`needs_metadata` cannot see the fields it appears to guard, so the hourly CLI prints a
per-field fill rate over the final catalog and emits `::warning::` for any field that is
empty on **all** items — the standing state that a contract field exists and no producer
ever writes it. Covered fields: `summary_points`, `desk`, `tags`, `tickers`, `pages`.
Excluded and why: the identity fields all have fallbacks so they are populated by
construction; `top_pick`/`needs_metadata` mean something when `False`; `language` is
defaulted (§5b). **Presence of a schema field is not coverage of it** — widening the
contract before wiring a producer just yields a wider schema with the same holes.

Everything here is a WARNING, never a failure: the hourly job's contract is that no single
bad document blocks the batch, and that holds equally for a document we merely learned
something unflattering about.

## 7. Ingestion pipeline (RV W1)  — `scripts/ingest_research.py` + `engine/research_vault/ingest.py`

Hourly. Mirrors `btc-live.yml` cron + `earlyclose.yml` R2-secrets block; runs on
`[self-hosted, macstudio-light]` (needs poppler `pdftotext`, already used by
`collectors/hk_cbbc_sld.py`). Steps, all idempotent + never-raise-per-item:
1. List `research_inbox/*.pdf` not present in `research_inbox/_processed/`.
2. For each: fetch pdf+sidecar (boto3 GET, private bucket), validate/normalize sidecar (§5).
3. Extract body text via `pdftotext -layout` (30s timeout; graceful empty on failure) — copy `collectors/hk_cbbc_sld.py:184-217`.
4. Promote PDF → `research_vault/<id>.pdf` (private).
5. Upsert catalog row + FTS corpus row (title/summary/body/institution/date).
6. Write receipt `research_inbox/_processed/<id>.json`; publish catalog.json + corpus.sqlite to R2; commit `data/research_vault/catalog.json` to the repo (salvage-push lane).

### 7b. A runner label is not a dependency guarantee (incident 2026-07-30 → 08-01)

At ~13Z on 2026-07-30 the `macstudio-light` label moved to mac-builder-3 (an M1) which had
no poppler. `shutil.which("pdftotext")` failed in every hourly run for two days. The
pipeline degraded exactly as §5b designed — empty `body`, honest `text_layer='unavailable'`
— and then **wrote a receipt for each document**, and receipts make re-ingestion impossible
by design (§7). A two-day TOOLING outage therefore became permanent damage to the published
corpus: **127 of 514 corpus rows** were bodyless when the host was healed — invisible to
body search, and served to the Mastermind Pro full-report reader as excerpt-only under a
note claiming the full text was "not reachable right now".

The lesson generalizes past poppler: **a fail-soft that writes a receipt is not fail-soft,
it is a permanent write.** Where a degraded ingest is recorded as done, the degradation must
be prevented, not merely disclosed.

Three-part fix (shipped 2026-08-01):

- **`research-ingest.yml` preflight gate — the one FAIL-CLOSED step in a never-raise lane.**
  Between the pip install and the ingest step, a missing `pdftotext` prints an `::error` and
  exits 1. No receipts are written, the PDFs stay in the inbox and retry next hour, and the
  outage shows as a red lane instead of silently maimed documents. Costs one `command -v`.
- **`ingest._reextract_bodies` — the THIRD published-row repair** (sibling to
  `_repair_titles` and `_refresh_sidecars`, §5c), and the only path back to a receipted row. Each run
  re-fetches the vault PDF of up to `REEXTRACT_MAX` (50) candidates, re-runs `pdftotext`,
  and re-stamps the measured columns. Load-bearing rules: candidacy reads the CORPUS, not
  the catalog (`text_layer` is server-side by §6); `text_layer='unavailable'` rows come
  first (user-visibly broken) and `text_layer IS NULL` rows (pre-probe, never measured)
  after; **fill-only for `body`** — a row that already has text keeps it byte-for-byte, so
  a stamping pass can never rewrite published text; facts are ALWAYS stamped (except an
  UNKNOWN one — writing the probe's `None` over a `pages` the row already carries deletes a
  fact instead of correcting it), which re-classifies a scan to `'none'` and **is** the
  quiescence mechanism; a missing vault PDF
  leaves the row completely untouched (absence of the object is not evidence about the
  document); and a still-dead extractor aborts the whole pass at the FIRST candidate, since
  no row may be re-stamped from an extraction that did not run. A cap that bites prints a
  `::warning`, on the §5c precedent.
- **Honest state for consumers.** `corpus.get_document` now projects `text_layer` (the one
  measured column in `DOCUMENT_FIELDS`), and the brain's full-report path picks its
  disclosure from it: `'none'` → "this is a scanned/image-only PDF, the excerpt is all the
  text there is"; `'unavailable'`/`''`/no row → the existing "not reachable right now".
  Same empty body, two different truths — promising a retry that can never deliver is as
  dishonest as declaring a temporary outage permanent.

**OCR verdict — not needed, and NOT here if it ever is.** As of 2026-08-01 the corpus holds
**zero** `text_layer='none'` documents: every bodyless row was the host fault above, which
is why re-extraction (not OCR) is the correct repair and why the 127 rows heal for free.
If genuinely scan-only PDFs ever appear, the designated home is the **MarketDesk extractor's
Marker parse lane on the M1** (§14 already runs Marker over the archive) — off the render
path, artifacts to R2 — **never** the hourly ingest lane: OCR is minutes-per-document
compute inside a 15-minute job that must stay a light hourly cron.

## 8. Search corpus (FTS5) — reuse CXI machinery, SEPARATE db

Copy the FTS5 pattern from `engine/context_index/schema.py` (contentless FTS5 + triggers)
and the BM25 query + sanitizer from `engine/context_index/lexical.py` into
`engine/research_vault/corpus.py` writing a NEW `corpus.sqlite`. Columns: `body`, `title`,
`summary`, `institution` (weights title=4, summary=3, body=1). Facets (`institution`,
month/date) are indexed columns on a `documents` table → compound `WHERE` with the FTS
`MATCH`. **House law (CXI-R23):** never query the CXI databases from this public surface and
never add PDFs as CXI sources — this is a standalone corpus that only borrows the *code*.
The API loads `corpus.sqlite` from R2 into the VPS with a TTL cache (read-only queries).

**Schema v2 (2026-07-26)** adds the §5b measured columns to `documents`. They are metadata
only and are NOT in the FTS table: `first_page_text` would duplicate `body` postings, and
indexing the provenance strings would silently reweight every BM25 score.

The migration is the load-bearing part. `_restore_corpus` pulls the published corpus from R2
at the start of every run, and `CREATE TABLE IF NOT EXISTS` is a no-op against it — so new
columns declared only in the DDL would leave the live database on v1 while every INSERT named
a v2 column, raising `OperationalError` inside `_ingest_one`'s catch-all and reporting **every
document as "failed"** with no other symptom. Therefore: the v2 columns are declared exactly
once (`corpus._V2_COLUMNS`) and applied only through `ALTER TABLE` in `_migrate()`, which runs
on every open and is idempotent. `upsert` also builds its column list from the columns the
database actually has, so a partially-failed migration still ingests. Tests cover the v1→v2
path, row/FTS preservation, migration idempotency, and fresh-vs-migrated column parity.

## 9. Serving API + download gate (RV W2)  — `app/research.py` (mirror `app/hub.py`)

| Route | Auth | Behavior |
|---|---|---|
| `GET /api/research/catalog` | none | R2 read-through of `catalog.json`, 60s TTL cache, `{stale:true}` on refresh fail (hub.py idiom). |
| `GET /api/research/search?q=&institution=&from=&to=` | none | FTS query over `corpus.sqlite`; returns `{items:[…]}` (id/title/summary/institution/date/excerpt). Input sanitized (lexical.py sanitizer). Per-IP soft rate-limit. |
| `GET /api/research/view/{id}` | `require_user` + paid | Resolve tier; if not paid → 402. Stream PDF bytes from private bucket; `Content-Type: application/pdf`, `Content-Disposition: inline`, `Cache-Control: private, no-store`, `X-Robots-Tag: noindex`. Per-user+IP rate-limit (anti-scrape, e.g. ≤ N views/min). Does NOT consume the download quota. |
| `POST /api/research/download/{id}` | `require_user` + paid | Resolve tier → limit (~~insider 5 / pro 20~~ → AS SHIPPED + AMENDED 2026-07-26: insider 0 / pro 10 / pro-on-a-lifetime-grant 50 / else 0). `_check_and_increment_download_quota` (day-keyed, fail-open-LOUD; mirror `brain_gateway._check_and_increment_quota`). On exhaustion → **402** `{quota_exhausted:true, remaining:0, limit, tier, upgrade:"/plans.html"}`. On pass → watermark the PDF with `{email} · {UTC date} · Mastermind — not for redistribution` (pypdf+reportlab overlay; degrade to un-watermarked if libs absent), return with `Content-Disposition: attachment; filename=…`. |
| `GET /api/research/quota` | `require_user` | `{tier, remaining, limit, used, resets_at}` for the button UI. Read-only (no increment). |

**Tier resolution:** reuse `engine.neuralweb.brain_gateway._resolve_tier(user_id)` (fail-safe
→ `free` when `user_entitlements` absent). Before Stripe #3178 lands, everyone resolves
`free` ⇒ view/download blocked ⇒ correct default. After #3178, `insider`/`pro` activate. No
hard dependency on #3178 merging.

**Why the blob attack fails:** source PDFs live only in the PRIVATE bucket (no r2.dev host).
The client has no PDF URL — only `/api/research/view` and `/api/research/download`, both
`require_user`+paid, both rate-limited, download additionally quota-metered. Caddy routes
`/api/research/*` to macro-api and has NO static rule for the PDFs. The download button is
disabled client-side past quota AND the server rejects with 402 regardless of the button —
so a scripted POST past the limit is refused server-side. Viewing yields renderable bytes
(unavoidable for any viewer); §12 removes even that via page-image rendering.

## 10. The page + PDF viewer (RV W3)  — flagship design surface

`templates/research_vault.html.j2` + `scripts/build_research_vault.py`. Mirror the reports
stack for the build wiring; but the visual bar is **flagship** (billion-dollar-SaaS), so the
design is `designer`/main-loop work (frontend-design skill + DESIGN_DOCTRINE first), not a
mechanical port. Composition:
- **Hero** — glass, aurora, plain-word verdict ("N new institutional reports this week · M highlighted"). Glance-tier: state + plain stance, no jargon.
- **Top Picks rail** — highlighted cards (editorial highlight; framed as notable *research*, never a trade call).
- **Filter bar** — facet chips (`.aff` idiom) for institution + month + side, plus a free-text search box (`.tbl-filter` idiom) wired to `/api/research/search` (debounced; searches title/summary/BODY).
- **Latest feed** — result cards: institution · our title · point-form summary · date · side badge · top-pick badge. SSR-baked snapshot (SEO) + client-hydrated from live catalog (freshness).
- **PDF viewer** — a popup modal cloning the **auth-overlay** modal (`site/theme.js:800-991`: glass card, focus-trap, `html`-level scroll-lock, scale+translate entry, mobile bottom-sheet, reduced-motion guard). pdf.js (vendored into `site/vendor/pdfjs/`, not yet present) renders bytes from `/api/research/view/{id}`. Download button reflects `/api/research/quota` (live remaining), disables at 0 / for non-paid with an Upgrade CTA. Beautiful page-turn + load animation.
- Bilingual `t()`; nav entry in the Research mega-menu (`_navlinks.html.j2`). CI: title-i18n, nav-mega, nav-gap, template/site-sync.

## 11. Compliance checklist (house law)

- No `validated` in user-facing text (CI `check_validated_claims.py`). No internal state/study names, no raw slugs, no untranslated stats in glance copy.
- Not investment advice — footer disclaimer (reuse report_base footer copy); Top Picks framed as highlighted research.
- Bilingual EN/ZH throughout; no `t()`/CJK in `title=`/attributes (title-i18n gate); `t()` spans never inside attributes.
- Display-tier only; gauntlet N/A (no signals). LLMs never originate content here — summaries come from the upstream engine, not generated at render.

## 12. Wave plan

| Wave | Deliverable | Routing | Depends on |
|---|---|---|---|
| **W0** | This masterplan | main loop | — |
| **W1** | Ingestion spine: sidecar schema, `ingest_research.py`, corpus builder, catalog, hourly workflow, R2 private-bucket wiring | `builder` (Opus) | W0 |
| **W2** | Serving API + download gate (`app/research.py`, quota ledger, watermark, Caddy route) — SECURITY-CRITICAL | main loop builds gate + `builder` for plumbing; `reviewer` red-teams | W1 contracts |
| **W3** | Flagship page + pdf.js viewer modal + search/filter UI | `designer` (Opus) leads; `builder` implements spec | W1 (catalog) + W2 (view/download) |
| **W4** *(deferred)* | `research_feed` NW context lobe (AI-brief chip: "N new reports today") | `builder` | operator roster-cap raise (`metabolism_budget.yml` full) |
| **W5** *(deferred)* | DocSend-style page-image rendering (removes viewer-scrape entirely) | `builder` | W2/W3 shipped |

Each wave = its own branch off fresh `origin/main` → PR → same-day squash-merge (auto-finish).

## 13. Operator dependencies (surface early)

1. **Create private R2 bucket** `mastermindx-research` (no public/r2.dev binding). Set env
   `R2_RESEARCH_BUCKET=mastermindx-research` on (a) the GHA ingestion workflow secrets and
   (b) the macro-api VPS. Existing account access key/secret work across buckets.
2. **Upstream contract:** the other engine writes `<id>.pdf`+`<id>.json` (§5) to
   `research_inbox/`. Top picks via `top_pick:true` or the `top_picks/` subfolder.
3. **New Python deps** (soft): `pypdf`, `reportlab` (watermark; degrade gracefully if absent),
   `pdfminer.six` optional fallback to `pdftotext`.
4. **Tiers:** paid gating activates when Stripe #3178 (`user_entitlements`) lands; before that
   the vault correctly blocks all view/download as `free`.
5. **NW lobe (W4)** needs a `max_active_nonscored_lobes` cap raise (roster full).

## 14. W6 — Research-Paper Alpha program (CHARTERED 2026-07-23, not started)

Operator intent (2026-07-23): MarketDesk history reaches back to **February 2026**; the
archive backfill captures everything (PDFs + MarketDesk summaries + Marker markdown)
precisely so a longitudinal study becomes possible. Charter, to be masterplanned in its
own W0 when opened:

- **Corpus:** every archived paper Feb-2026→now (PDF in the vault bucket; Marker markdown
  on the extractor host; sidecars carry institution/desk/date/top-pick).
- **Extraction layer:** a local LLM on the operator's PC (Qwen-class or stronger) reads each
  paper's markdown against a FROZEN prompt schema and emits per-paper systematized fields:
  recommendation level, sentiment by topic, macro outlook, conviction language, named
  tickers/sectors, key numbers. Extractions are **offline research features, versioned with
  the prompt hash** — data for studies, NEVER wired as live signals (house law: LLMs may
  not originate signals/scores/escalations; A7 ORIGINATE ban).
- **Study families (each needs its own prereg before any authority claim):**
  (a) paper sentiment / recommendation levels vs subsequent market & sector price paths —
  including the contrarian construction (do aggregate sell-side sentiment extremes mark
  tops/bottoms?); (b) per-institution track records by topic/desk (who is actually good at
  what); (c) keyword/theme lead-lag vs realized moves; (d) factor drift Feb→now.
- **Epistemics (binding):** everything ships display-tier freely (e.g. an institution
  scorecard page); ANY promotion to rank/size/gate authority passes the gauntlet with
  pre-registered gates; nulls printed. Short history = ONE regime slice — expect small-N
  ceilings; never era-pool a longer archive later without an era split.
- **Dependencies:** backfill complete; Marker markdown coverage; PC LLM runner + frozen
  prompt schema; a paper→price join layer (tickers/sectors to returns at t+N).
