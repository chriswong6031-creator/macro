# SEO Supercharge Masterplan — public tier-preview estate + entity package

*Chartered 2026-08-03 by Fable (operator order 2026-08-02). Program home for the
post-outage SEO recovery's second phase: turn the gated dashboard estate into
public, crawlable, upgrade-walled pages (Unusual Whales model) and give Google an
unmistakable MastermindX entity. Supersedes nothing; builds on the ratified
tier-preview pattern (`docs/TIER_PREVIEW_PATTERN.md`, PR #3471).*

## §0 ACCEPTANCE GATES (every wave, "not done unless")

**Per reopened page (W1/W2):**
1. Anonymous `curl` of `https://www.mastermind-x.com/<page>` → **200**, self-canonical,
   NO `noindex` (header or meta), real above-the-fold content (preview slice +
   honest totals), upgrade wall visible for premium modules, controls INERT-not-hidden
   (`.gated`, pointer-events:none), bilingual EN/ZH copy on the wall.
2. `/premiumdata/<page>.json` (or the page's paid payload) → 403 anonymous via
   `curl -H 'X-Original-Uri: <path>' https://www.mastermind-x.com/api/paywall/check`
   (204 free for the shell). Server decides; no load-bearing client tier check.
3. Boundary edited in ALL mirrors in one PR: `app/regwall.py` + `app/deploy/Caddyfile`
   (every matcher list) + `config/site_access.yml`; `tests/test_site_access_boundary.py`
   + the `tier-gate` suite green LOCALLY (ci.yml may not run them on the PR's paths).
4. Page added to `sitemap.xml` in the same PR (verify the builder picks it up — see
   inventory answer on `lib/seo.py` discovery), and submitted via the weekly
   seo-director IndexNow step (automatic on next run).
5. Live verification post-merge: anonymous curl 200 + paywall-check probe + a
   Googlebot-UA fetch byte-comparable to a normal UA.
6. Render-lane law respected: pages that only bake on the render runner (e.g.
   special_situations) are never hand-baked locally; dispatch the scoped render.
7. NO edits to the tier catalog (collision: PRs #4176/#4185 "essential" tier
   migration in flight). Page classification uses existing classes only.

**Entity package (W0):**
8. Homepage H1 contains "MastermindX"; a blunt visible entity paragraph (EN+ZH)
   sits in the hero; `<title>` ≤ 70 chars, brand-first. Hero VISUALS untouched
   (operator vetoes: hero gradient identity, display faces, no motion changes).
9. JSON-LD upgraded in place: `WebSite` (name + `alternateName` ["Mastermind X",
   "Mastermind-X"]) + `Organization` (logo, url; `sameAs` ONLY for profiles that
   verifiably exist in repo config — never guessed; omit when unverified).
10. `/about.html` exists, public in ALL three boundary mirrors + sitemap, linked
    from the public chrome footer (family source only — `_public_chrome_*`;
    `tests/test_public_chrome.py` parity green), bilingual, and states: what
    MastermindX is, products, methodology pointer, research-vs-advice distinction
    (link disclaimer.html), contact (support.html), NO fabricated legal entity.
11. `python -m engine.marketing.seo_director --root .` after the sweep: the 12
    open work orders resolve or reduce with no new CRITICAL; health_score does
    not regress.

**Program-wide:**
12. No gated URL ever enters the sitemap. No page flips public without its
    premium modules walled (a full-content leak is a regression, not a win).
13. "validated" never appears in new user-facing copy (CI-guarded), and
    falsifier language stays off front surfaces (operator 2026-07-27).
14. Competitor names are not used in our page copy without an explicit operator
    ruling (house debrand law) — the W3 "vs" pages ship ONLY if the operator
    approves naming competitors.

## Why (evidence, 2026-08-02)

GSC (first real pull, run 30772281001): homepage indexed; 11/12 core pages
"Discovered – currently not indexed", never crawled; sitemap ingested clean
(2,219 URLs, 0 indexed). All meaningful historical impressions sat on pages that
are now GATED (baskets_china 63, special_situations 41, china_heatmap 7 — each
now 302 → `/?signin=1` + noindex to Googlebot = Google's soft-404 shape).
External footprint: ONE inbound link (greydeercapital.com). Brand SERP for
"mastermind-x.com"/"MastermindX" is owned by unrelated entities. Verdict: the
bottleneck is crawl demand + entity identity, not on-page hygiene (site audits
86/100). The only content Google ever rewarded is the content we hid.

## Adjudications (Fable, 2026-08-03)

- **A1 — Public shells, not login shells.** The ratified tier-preview pattern
  classifies shells `free_registered`. For the SEO estate this program promotes
  selected shells to ANONYMOUS-public. The paid payload stays server-gated.
  Conversion targets get the UW treatment: full page chrome, delayed/partial
  data free, premium modules blurred/locked with bilingual upgrade CTAs.
- **A2 — No subdomain split** (operator). www stays the single host for public
  + product pages; app.mastermind-x.com remains the terminal only.
- **A3 — No domain switch to mastermindx.ai.** Young domain mid-recovery; .ai is
  currently DOWN (525). Keep mastermind-x.com; when .ai is fixed, 301 it
  path-for-path into www. Never alternate.
- **A4 — Not every page opens.** Free users must get real value (operator), but
  per-page adjudication decides free vs walled modules. Default policy:
  market-context dashboards (China/HK/ETF/heatmaps/breadth) open with delayed or
  top-N-truncated data; signal-authority surfaces (graded calls, live options
  flow, entry/exit reads) stay premium behind the wall on an open page.
- **A5 — Ordering.** Demand-proven pages first (baskets_china, hk, etfs,
  china_heatmap), then the inventory's priority table. One pattern-setter PR
  first; fleet conversion only after its live verification.

## Waves

- **W0 (now):** this charter; inventory census (running); entity package
  (designer/opus); work-order hygiene sweep (builder/opus); apex path-preserving
  canonicalization check (from inventory answer C — fix in W1 PR if broken).
- **W1:** pattern-setter conversion — `baskets_china.html` (63 impressions =
  proven demand) as the reference anonymous tier-preview page: designer pins the
  free/walled split + wall design (reuse Special Situations shell idiom; terminal
  paywall lesson: CTAs in brand blue, never signal amber), Opus builder
  implements per `docs/TIER_PREVIEW_PATTERN.md`. Then hk.html + etfs.html +
  china_heatmap.html reusing the pinned pattern.
- **W2:** fleet conversion by inventory priority; sitemap grows page-by-page;
  weekly seo-director tracks indexed-count as the program KPI.
- **W3:** branded-search content (`/about` deep links, "what is MastermindX",
  pricing explainer). "vs competitor" pages HELD pending operator ruling (§0.14).
- **W4 (operator-gated, off-repo):** entity footprint — LinkedIn company,
  Crunchbase, Product Hunt, GitHub org, ONE canonical X account in Organization
  `sameAs`; fix mastermindx.ai (525) + 301 it; greydeercapital link stays.

## KPIs (weekly, from the now-live GSC pipeline)

indexed-count (URL Inspection core set + sitemap indexed total), impressions,
brand-query impressions ("mastermindx", "mastermind x"), clicks. Baseline
2026-08-02: 1/12 indexed, 128 impressions (all decayed gated-page tail), 0
brand, 0 clicks. First review: 2 weekly runs after W1 lands.

## Standing constraints

Tier-catalog freeze during #4176/#4185; render budget law (page bakes ride
render.yml scopes, never local); public repo — no credential/identity material
in committed artifacts (SA identity is masked on disk); GitHub quota discipline;
navigation source-of-truth law (footer/nav edits in family sources only).
