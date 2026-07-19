# MKT-D10 — Workshop W1: Free Public Tools as Lead Magnets

**Department:** Workshop (products) · **Priority: P3** · **Status: W1 SHIPPED 2026-07-19** — free screener page (`templates/confluence_screener.html.j2` + `scripts/build_confluence_screener.py`, gated rows omitted server-side, baked in the tech_lab offrender job) + `/movers.html` + og:image share-cards (`engine/marketing/share_cards.py`, PIL, fingerprint-cached, ~46ms/card one-time bake) on Beacon dossiers + both new pages. CTAs = TODO(D07) seam (untagged `app.mastermind-x.com`). Come-back: first nightly bakes pages + ~1,500 ticker cards; W2 = D07 tagged links + ZH theme names upstream.
**Charter:** id=`products` ("Intelligence Products & Public Tools", wave 3, 12 chartered engines — stubs).

## Why

Guerrilla law: give away a genuinely useful free tool, earn the follow/bookmark/backlink, upsell the trial. TrendSpider's free-scanner pages and Beacon's ~1,500 SEO dossiers (#2980/#3000/#3017) prove the pattern in-house. Workshop W1 ships two small free tools that are *shareable objects* (each post-able and each a landing surface), not a product suite.

## Deliverables — W1

1. **Public confluence screener (lite):** a free page derived from `site/tech_lab.html#combos` — today's top 3 active combos with train/test win rates printed + the `active_now` tickers for ONE combo (the rest blurred behind the trial CTA). Static, nightly-rendered, honest stats. This is the shareable proof-object for signal posts.
2. **Daily movers page share-cards:** every Beacon dossier + a small `/movers` page gets an og:image share-card (reuse `chart_render` branding) so links posted by D02 unfurl beautifully. Static og:image generation is cheap at render time if batched — respect the render budget (only regenerate on data change, fingerprint-cached).
3. Both pages carry tagged CTAs via D07's link builder; both registered in the site nav where the design doctrine allows (check `docs/DESIGN_DOCTRINE.md`; these are public surfaces → `designer` agent + frontend-design skill mandatory).

## Acceptance

- Both pages render nightly inside budget; screenshot taste gate passes; share-card unfurl verified (og:image + twitter:card meta present and correctly sized); blurred-tier gating actually hides the data in the DOM (not CSS-only blur over live text).

## Traps

- **Epistemics:** free tier shows real, honest numbers or nothing — a teaser must never show inflated stats. "Validated" ban applies.
- CSS-blur over real data is a fake gate (view-source leaks it) — omit the gated rows server-side.
- Bilingual law: EN/ZH like every public page; no translated text in `title=` attributes (CI-guarded).
