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

**Operator/legal note:** distribution rights for third-party research are an operator/legal
responsibility. This system enforces *access control* (who may view/download, how many per
day) and *traceability* (per-user watermark); it does not adjudicate redistribution rights.

## 2. Resolved product decisions (operator, 2026-07-22)

| Fork | Decision |
|---|---|
| Anti-scrape | **Private stream + gated download.** Source PDFs in a PRIVATE R2 bucket (no public URL). Viewer streams bytes only through an authenticated, rate-limited API route. Download is a SEPARATE route enforcing the daily quota + per-user watermark + `Content-Disposition: attachment`. Kills the public-blob bypass; makes scraping authenticated, rate-limited, and traceable. (Honest limit: an in-browser viewer must receive renderable bytes, so a determined viewer can still save what they view — the DocSend-style page-image upgrade in §12 removes even that, and is the documented fast-follow.) |
| Access | **Public teaser list, paid viewing.** Anyone (incl. logged-out) sees Latest + Top Picks with our title + summary + institution + date (funnel/SEO). Opening the viewer OR downloading requires an active paid plan. |
| Downloads | **5/day** for `insider` ("Normal paid") · **20/day** for `pro`. `free`/anon = 0 (view+download blocked). |
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
- `summary_points` — array of 3–8 short bullets; falls back to `[]` (row shows "Summary pending").
- `top_pick` — boolean; also settable via the `top_picks/` subfolder. Editorial highlight of the REPORT (not a trade recommendation) — copy must never imply investment advice.
- `tags`, `tickers`, `desk`, `pages`, `language`, `source_filename` — optional.

Unknown fields are preserved but ignored. A sidecar that fails JSON parse → the PDF is still
ingested with all-fallback metadata and flagged `needs_metadata:true` (never dropped).

## 6. Catalog schema — `research_vault/catalog.json` (public-safe)

```json
{ "schema": "research_vault.catalog.v1", "generated_at": "…",
  "count": 128, "institutions": ["Bernstein","Goldman Sachs", …],
  "items": [
    { "id": "...", "title": "...", "institution": "Bernstein", "side": "sell",
      "desk": "Data Centers", "published_at": "...", "summary_points": [...],
      "tags": [...], "tickers": [...], "top_pick": true, "pages": 12,
      "needs_metadata": false } , … ] }
```
Body text is NOT in the catalog (search-only, §8). Items are sorted newest-first. `top_pick`
items also power the Top Picks rail. This file is the ONLY research artifact that carries
publicly-visible content; the PDFs themselves are never public.

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

## 8. Search corpus (FTS5) — reuse CXI machinery, SEPARATE db

Copy the FTS5 pattern from `engine/context_index/schema.py` (contentless FTS5 + triggers)
and the BM25 query + sanitizer from `engine/context_index/lexical.py` into
`engine/research_vault/corpus.py` writing a NEW `corpus.sqlite`. Columns: `body`, `title`,
`summary`, `institution` (weights title=4, summary=3, body=1). Facets (`institution`,
month/date) are indexed columns on a `documents` table → compound `WHERE` with the FTS
`MATCH`. **House law (CXI-R23):** never query the CXI databases from this public surface and
never add PDFs as CXI sources — this is a standalone corpus that only borrows the *code*.
The API loads `corpus.sqlite` from R2 into the VPS with a TTL cache (read-only queries).

## 9. Serving API + download gate (RV W2)  — `app/research.py` (mirror `app/hub.py`)

| Route | Auth | Behavior |
|---|---|---|
| `GET /api/research/catalog` | none | R2 read-through of `catalog.json`, 60s TTL cache, `{stale:true}` on refresh fail (hub.py idiom). |
| `GET /api/research/search?q=&institution=&from=&to=` | none | FTS query over `corpus.sqlite`; returns `{items:[…]}` (id/title/summary/institution/date/excerpt). Input sanitized (lexical.py sanitizer). Per-IP soft rate-limit. |
| `GET /api/research/view/{id}` | `require_user` + paid | Resolve tier; if not paid → 402. Stream PDF bytes from private bucket; `Content-Type: application/pdf`, `Content-Disposition: inline`, `Cache-Control: private, no-store`, `X-Robots-Tag: noindex`. Per-user+IP rate-limit (anti-scrape, e.g. ≤ N views/min). Does NOT consume the download quota. |
| `POST /api/research/download/{id}` | `require_user` + paid | Resolve tier → limit (insider 5 / pro 20 / else 0). `_check_and_increment_download_quota` (day-keyed, fail-open-LOUD; mirror `brain_gateway._check_and_increment_quota`). On exhaustion → **402** `{quota_exhausted:true, remaining:0, limit, tier, upgrade:"/plans.html"}`. On pass → watermark the PDF with `{email} · {UTC date} · Mastermind — not for redistribution` (pypdf+reportlab overlay; degrade to un-watermarked if libs absent), return with `Content-Disposition: attachment; filename=…`. |
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
