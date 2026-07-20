# MKT-D12A — SEO Director & Technical Foundation (companion to D12)

**Department:** Beacon (Organic Search & Public Pages)

**Status:** EXECUTING 2026-07-20 (Fable main-loop session). This docket records the
rulings and build lanes for the SEO work that D12 left unassigned: the technical
foundation of the *existing* ~200-page core estate, the Beacon control plane in the
admin panel, and the autonomous SEO Director loop. It does NOT touch D12's content
lanes (blog / Learning Center / calculators / toolkits = MKT-SEO-01…05, running in a
separate specialist session) nor the ticker-dossier estate (separate session,
expanding toward ~2,500 US names).

**Index coordination:** INDEX.md registration deferred (open PR #3092 edits INDEX.md;
same collision-avoidance as D12 header). Register D12A alongside D12 once #3092 lands.

---

## R-rulings (adjudicated this session)

- **R1 — Canonical host is `https://www.mastermind-x.com/`.** Ratified by #3040
  (apex → 301 → www). Before this program, every canonical, OG URL and all 1,472
  sitemap `<loc>` entries pointed at the apex — i.e. through a redirect. One shared
  constant `lib/seo.py::SITE_BASE`; all public-URL emitters import or match it.
  Falsifiable check: `grep -r "https://mastermind-x.com" site/ templates/` returns
  only prose mentions, never canonicals/sitemap/OG; SEO Director flags regressions
  weekly (`bad-host canonical` = critical).
- **R2 — Single-file sitemap stays for now; core coverage completes.** Only 12 of
  ~200 public core pages were listed (hand-seeded in #796). New deterministic
  builder (`lib/seo.py::build_core_sitemap`, invoked at the end of `build_site`)
  discovers `site/*.html` minus an explicit EXCLUDE set, preserves `/stocks/`
  entries (ticker lane's merger and this one are mutually preserving). The
  family-split sitemap **index** (D12 §10.3) remains MKT-SEO-01's lane — when the
  substrate session builds it, `build_core_sitemap` becomes the core-family feeder.
- **R3 — No hreflang, no /zh/ URLs (W1).** One bilingual URL is the shipped UX
  (dual-DOM `l-en`/`l-zh` spans, client-side flip, no server language routing) =
  D12 §10.9 option A. Meta stays EN plain text (`_seo_head` law). A dedicated
  Chinese estate is MKT-SEO-09, demand-gated.
- **R4 — Structured data W1 = honest minimum.** Organization + WebSite JSON-LD on
  the homepage only; **no SearchAction** (no public site-search endpoint exists —
  never fabricate), no ratings/FAQ/HowTo. Ticker Article JSON-LD untouched (D12
  §10.4). Article/Breadcrumb for blog/learn pages belongs to MKT-SEO-01.
- **R5 — SEO Director is deterministic-first.** The weekly loop audits, scores,
  trends and emits capped work orders; it commits ONLY `data/marketing/seo/`
  artifacts to main (codex-research commit-scope pattern). It never edits
  templates, engines or site pages. An LLM fix lane (draft PRs applying top work
  orders) is **phase 2**, requires operator go, and inherits the immune-system law:
  autonomous code changes ship as draft PRs, never direct merges.
- **R6 — Titles unchanged in W1.** PR B adds `_seo_head` include + `seo_title` /
  `seo_desc` / `seo_path` vars from the ratified copy table
  (`research/marketing_dockets/D12A_META_COPY.yaml`); existing `<title>` tags stay.
  Title testing/optimization is MKT-SEO-07's lane, driven by Search Console data.

## Build lanes (this session)

| PR | Lane | Model routing | Content |
|---|---|---|---|
| A | Technical foundation | sonnet builder, Fable spec/merge | SITE_BASE + www sweep, core-sitemap builder + one-shot regen, robots.txt, `llms.txt` + `brand-facts.json` (D12 §10.6 subset), homepage JSON-LD, tests |
| B | Meta rollout | Fable copy table → sonnet applies | `_seo_head` include + per-page seo vars across ~90 public templates; duplicate-meta removal; render test: every public page ships exactly one canonical + description |
| C | SEO Director | sonnet builder, **opus review** (trust-gate code) | `engine/marketing/seo_director.py` (audit → health score → work orders → history), `.github/workflows/seo-director.yml` (Sun 15:00 UTC cron + dispatch, gated on `vars.SEO_DIRECTOR_ENABLED`, dispatch bypasses gate) |
| D | Beacon control plane | **opus designer** (operator order: no sonnet on admin build) | Admin → Marketing → SEO: health/census/scorecard, sitemap + crawl-infra state, work orders, Director toggle + Run-now (repo-var + workflow-dispatch plumbing), Search Console slot in explicit **unavailable** state (§11.1: unknown ≠ zero) |

Artifact contracts (schemas `seo_audit.v1`, `seo_work_orders.v1`, `seo_scorecard.v1`,
`seo_history.jsonl`) are documented in `engine/marketing/seo_director.py` and
consumed by admin `marketing.seo()`.

## SEO Director operations

- **Cadence:** Sundays 15:00 UTC (off the nightly and Saturday batch lanes).
- **Toggle:** repo variable `SEO_DIRECTOR_ENABLED` — set from the admin SEO page
  (or `gh variable set`). Unset/false = scheduled runs dark; `workflow_dispatch`
  (admin "Run now" button) always works. Mirrors `AUTONOMY_PAUSED`/`CODEX_MODE`.
- **Output:** artifacts to `data/marketing/seo/` committed straight to main with
  the retry-rebase push loop; `::warning::` annotations on critical findings; the
  job never fails on findings (only on crash).

## Operator prerequisites / come-backs

1. **Google Search Console property verification** for www.mastermind-x.com (+ Bing
   Webmaster). Until credentials exist the admin GSC slot must show "not
   connected", never zeros (D12 §11.1). Then: MKT-SEO-07 ingestion.
2. **Ticker keyword pass** — after the stock-pages session completes its ~2,500-name
   universe: query-targeted titles/descriptions over dossiers, coordinated with
   that lane's templates. Deferred by operator order.
3. **Sitemap index migration** — when MKT-SEO-01 ships family sitemaps, fold
   `build_core_sitemap` into the index as the core feeder (R2).
4. **First live Director run** — flip `SEO_DIRECTOR_ENABLED=true` after PR C+D
   merge; verify first artifacts land and the admin page renders them.
5. **Phase 2 (LLM fix lane)** — operator go/no-go: weekly Director opens a draft PR
   applying top work orders (meta copy, alt text). Draft-PR-only, R5.

## Verification

- Foundation: `tests/test_seo_foundation.py` (host law, sitemap round-trip
  compatibility with the ticker merger, llms/brand-facts pairing);
  `check_template_site_sync` covers the new paired assets.
- Director: `tests/test_seo_director.py` (seeded-issue fixture site, severity
  mapping, score monotonicity, atomic writes, dry-run purity).
- Admin: `tests/test_admin_seo.py` (day-0 accruing state, seeded artifacts,
  corrupt-artifact fail-soft).
- Live: first scheduled run Sunday 2026-07-26 15:00 UTC; canonical spot-check via
  `curl -s https://www.mastermind-x.com/macro.html | grep canonical` after the
  first nightly re-render.
