# Media Network — automated publication estate (masterplan, docket D14)

**Program:** Agentic Media / Media Network · **Author:** Fable · **Date:** 2026-07-25 · **Status:** CHARTERED
**Umbrella:** `AGENTIC_MEDIA_PROGRAM_BY_FABLE.md` (AM-R1 provenance, AM-R4 transformation, AM-R7 measurement, AM-R9 monetization)
**Extends:** the D12 free estate (`scripts/build_free_content.py`, `content/seo/blog/*.md`, `templates/seo_article.html.j2`, `/blog/` already in `app/regwall.py` PUBLIC_PREFIXES + all Caddy matchers); Beacon SEO Director (`engine/marketing/seo_director.py`, weekly 0–100 audit); Search Console ingestion (#3160); Research Vault (`data/research_vault/catalog.json`, per-report SEO pages `scripts/build_research_pages.py`); Chronicle packs (sibling masterplan).

Goal: turn the 6-post hand-written blog into an **automated daily publication** that earns search traffic, backlinks, owned audience, and subscription leads — then, only when earned, additional genuinely distinct publications. The operator's Zerohedge observation is adopted as design: one strong publication per brand, one primary X account per publication, aggregation done *with* attribution rather than masked.

## §0 ACCEPTANCE GATES

**W1 (press engine + first two desks) not done unless:** 10 consecutive generated articles (mixed desks) each pass the full validator suite (§5) with zero manual edits; every aggregation piece names + links its primary source above the fold and contains ≥40% our-value content by section (our data, chronicle context, added analysis — measured structurally, not vibes); every article carries the byline/AI-disclosure block + standing not-investment-advice footer; `python -m scripts.build_free_content --check` green (drift law); posts render on `/blog/` with correct JSON-LD Article, RSS updated, sitemap merged; zero regwall/Caddy edits needed (staying under `/blog/`); generation runs off the render path on its own workflow with an explicit per-day token budget + circuit breaker; a kill switch (`PRESS_PUBLISH_ENABLED` repo variable) dark-ships the whole lane.
**W2 (cadence + measurement) not done unless:** 2 weeks at target cadence with zero validator overrides; Search Console rows flowing per URL into the D12 adapter store; Beacon weekly score not degraded vs pre-launch baseline; per-desk scorecards (sessions, impressions, CTR, email captures, D07-tagged trial attributions) rendering in admin.
**Any spin-out publication (W4+) not done unless:** its §7 earn-gates are met AND operator ratifies name/brand/domain AND its masthead carries "A Mastermind Media publication" + AI-disclosure policy page AND regwall/Caddy dual-mirror is edited for any new prefix (recon: `app/regwall.py:60` + Caddyfile not-path matcher lists) — never silently behind the regwall.

## 1. The three desks (start with two, add the third when Chronicle W1 lands)

| Desk | Content | Source spine | Cadence target | The honest wedge |
|---|---|---|---|---|
| **The Brief** (aggregation, attributed) | 300–600w: what happened, why it matters, what to watch — on the day's 3–5 most attention-worthy market stories | breaking/news desks + movers + chronicle short pack + our engine stats | 2–3/day (W1: 1–2) | speed + our-data receipts; every piece links its sources prominently (Techmeme/Axios idiom, AM-R4) |
| **Research Desk** (institutional coverage) | "What the street is telling clients": single-report coverage + weekly cross-report synthesis ("5 banks on positioning this week"), stance map by institution | vault catalog `summary_points` (public on our site) + chronicle medium pack; minimal quotation | 1/day + 1 weekly synthesis | **nobody else automates this because nobody else has the vault**; each piece links the vault landing page (`/research/<slug>.html`) → Pro funnel |
| **Editorial** (original thesis) | 900–1,500w original pieces: named theses with mechanism, falsifier, and scheduled review; monthly "state of the story" epoch pieces | chronicle medium/long packs + engine surfaces; best pieces promoted to site Research Reports | 2–3/week | receipts-culture longform; the only desk allowed a strong voice, and it grades itself in public |

Explicitly **not** built (DNR via AM-R1/AM-R4): a Zerohedge-rewrite lane that paraphrases third-party articles wholesale ("masked original content"); scaled programmatic "is $X a buy" article farms (guerrilla doctrine §2.4 already rejects; Google scaled-content-abuse names it); any desk that publishes engine signals as advice (plain-word stance + disclosure law carries over).

## 2. Why this earns traffic (and the failure it avoids)

Search rewards what the March-2024+ policy era punishes elsewhere: original data, first-party expertise, consistent publication identity. We have original data nobody else publishes (engine stats, vault coverage, receipts). The failure mode to avoid is the 2024–26 graveyard of AI content sites: high-volume derivative text, no identity, no proof-of-work → deindexed as scaled content abuse. Every desk's design forces the differentiator into the piece structurally (§0 W1 gate: ≥40% our-value content).

## 3. Identity + disclosure

Byline: **"Mastermind Research Desk — AI-assisted, human-supervised."** A standing `/blog/editorial-policy.html` page states the pipeline honestly (automated drafting, deterministic validators, operator oversight, correction policy) — in 2026 this is a differentiator, and it is also what Google News' sponsorship/editorial-disclosure rules and our own receipts culture demand. Corrections append visibly (errata block), never silent-edit — same law as chronicle epochs.

## 4. Pipeline (`engine/press/`)

`desk_planner.py` (deterministic: pick today's stories/reports from source spines; dedupe vs published ledger) → `writer.py` (LLM per desk: prompt = desk contract + chronicle pack + source facts + house style; Opus for Editorial, cheapest-passing for Brief per AM-R6) → `validators.py` (§5) → emits `content/seo/blog/<date>-<slug>.md` with the **existing frontmatter contract** (slug/family/title/description/published/updated/related/cta — `scripts/build_free_content.py:_validate` unchanged) → existing builder renders site/blog/ + RSS + sitemap → publish workflow commits (press lane owns `content/seo/blog/`, off the nightly render path exactly like the D12 estate today). Ledger: `data/press/published.jsonl` (append-only: id, desk, sources[], validator_report, urls) — the receipts + dedup spine.

## 5. Validator suite (the anti-slop gate, all deterministic)

fact-anchor check (every number/quote in the draft must appear in the supplied source facts — the chronicle/no-originated-numbers law applied to press); quote-length lint (≤2 short attributed quotes per piece, AM-R4); source-attribution structure check (Brief: source link above the fold; Research: vault landing link present); similarity radar vs last 30 days of our own posts AND vs the source text (close-paraphrase detector — shingle overlap vs source above threshold = hard fail); banned-lexicon + advice-lexicon (Sentinel lists); disclosure block present; cheese-test voice validator (v3 port); length/structure budget per desk. Validator failures quarantine the draft (never auto-retry-until-pass on the same model — regenerate max twice, then drop the slot; a thin day beats a padded one).

## 6. Distribution

Native-first on X: each piece becomes a value-complete post (the stat/chart/claim in-post), link in reply/card — per the reach-suppression + $0.20/link-post API reality. The flagship desk account carries Brief/Editorial shares; the Research Desk gets its own X account only at S3 of the persona ladder. Personas cite pieces asynchronously when genuinely on-beat (radar-enforced: never the same link across accounts in 24h). RSS ships day one (already in the builder); newsletter digest joins the D07/lifecycle lane later (owned audience).

## 7. Spin-out gates (second publication, the .co/.info/.org replacement)

A new publication (own name/brand, possibly own domain) may be chartered only when ALL hold: flagship estate ≥ threshold (e.g. 50k organic sessions/mo sustained 2 months, Search Console-verified); a desk has a coherent standalone identity (e.g. zh-language market wire; options/vol daily) whose audience demonstrably differs; operator ratifies name + budget; AM-R1 masthead disclosure. New domains start with honest zero authority — that cost is accepted consciously, for brand reasons, never for evasion (the evasion motive is DNR'd). Cap: ≤3 publications through 2026.

## 8. Monetization

Subscriptions first (Research Desk → vault Pro funnel is the designed lead path; D07 UTM attribution measures it). Ads deferred per AM-R9 (≥100k sessions/mo + operator ruling; YMLY/MFA risk printed). Affiliate/creator syndication per D11 when ratified.

## 9. Waves

| Wave | Ships |
|---|---|
| **W1** | `engine/press/` planner+writer+validators, Brief + Research desks at W1 cadence, publish workflow + kill switch, published ledger, admin Press panel (drafts/quarantine/scorecards read-only) |
| **W2** | Cadence to target, per-desk scorecards + Search Console wiring, weekly ops report in admin |
| **W3** | Editorial desk (needs Chronicle W1 narratives), Research Reports promotion path, newsletter digest |
| **W4+** | Spin-out per §7 gates; zh-language desk evaluation |

## 10. Risks (printed)

- **Cold-start**: a 6-post blog has ~zero authority; expect months of thin search traffic. The Research Desk is the differentiated wager (unique corpus) and X-native distribution carries the interim. Scorecards make "it's not working" cheap to see; kill gates per desk at 12 weeks.
- **LLM cost**: bounded by per-day budget + circuit breaker; Brief on cheap models, Opus only where the validator suite demands it.
- **Vault dependency**: Research Desk inherits vault ingestion health (hourly lane) + the open MarketDesk licensing flag (umbrella §8) — coverage-from-summaries keeps us in standard commentary norms regardless.
- **Google policy drift**: Beacon weekly audit is the tripwire; any manual action = immediate cadence freeze + operator escalation (runbook line in W1).
